import os
from typing import Dict, Literal, Protocol, TypedDict, cast

import aiohttp
from datadog_api_client.api_client import AsyncApiClient as DatadogAPI
from datadog_api_client.configuration import Configuration as DatadogConfig
from datadog_api_client.v1.api.events_api import EventsApi as DatadogEventAPI
from datadog_api_client.v1.model.event_alert_type import EventAlertType
from datadog_api_client.v1.model.event_create_request import EventCreateRequest
from dotenv import load_dotenv
from loguru import logger

from pyth_observer.check import Check
from pyth_observer.check.publisher import PublisherCheck
from pyth_observer.models import Publisher

load_dotenv()


class Context(TypedDict):
    network: str
    publishers: Dict[str, Publisher]


class Event(Protocol):
    check: Check
    context: Context

    async def send(self):
        ...


class DatadogEvent(Event):
    def __init__(self, check: Check, context: Context):
        self.check = check
        self.context = context

    async def send(self):
        # Publisher checks expect the key -> name mapping of publishers when
        # generating the error title/message.
        text = self.check.error_message()

        # An example is: PriceFeedOfflineCheck-Crypto.AAVE/USD
        aggregation_key = f"{self.check.__class__.__name__}-{self.check.state().symbol}"

        if self.check.__class__.__bases__ == (PublisherCheck,):
            # Add publisher key to the aggregation key to separate different faulty publishers
            # An example would be: PublisherPriceCheck-Crypto.AAVE/USD-9TvAYCUkGajRXs....
            aggregation_key += "-" + self.check.state().public_key.key

        event = EventCreateRequest(
            aggregation_key=aggregation_key,
            title=text.split("\n")[0],
            text=text,
            tags=[
                "service:observer",
                f"network:{self.context['network']}",
                f"symbol:{self.check.state().symbol}",
                f"check:{self.check.__class__.__name__}",
            ],
            alert_type=EventAlertType.WARNING,
            source_type_name="my_apps",
        )

        # Cast the event to EventCreateRequest explicitly because pyright complains that the previous line returns UnparsedObject | Unknown | None
        event = cast(EventCreateRequest, event)

        # This assumes that DD_API_KEY and DD_SITE env. variables are set. Also,
        # using the async API makes the events api return a coroutine, so we
        # ignore the pyright warning.

        server_variables = {"site": os.environ["DATADOG_EVENT_SITE"]}
        api_key = {"apiKeyAuth": os.environ["DATADOG_EVENT_API_KEY"]}
        config = DatadogConfig(api_key=api_key, server_variables=server_variables)

        async with DatadogAPI(config) as api:
            response = await DatadogEventAPI(api).create_event(
                body=event
            )  # pyright: ignore

            if response.status != "ok":
                raise RuntimeError(
                    f"Failed to send Datadog event (status: {response.status})"
                )


LogEventLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class LogEvent(Event):
    def __init__(self, check: Check, context: Context):
        self.check = check
        self.context = context

    async def send(self):
        # Publisher checks expect the key -> name mapping of publishers when
        # generating the error title/message.
        text = self.check.error_message()

        level = cast(LogEventLevel, os.environ.get("LOG_EVENT_LEVEL", "INFO"))
        logger.log(level, text.replace("\n", ". "))


class TelegramEvent(Event):
    def __init__(self, check: PublisherCheck, context: Context):
        self.check = check
        self.context = context

    async def send(self):
        text = self.check.error_message()
        publisher_key = self.check.state().public_key.key
        publisher = self.context["publishers"].get(publisher_key, None)
        # Ensure publisher is not None and has contact_info before accessing telegram_chat_id
        chat_id = (
            publisher.contact_info.telegram_chat_id
            if publisher is not None and publisher.contact_info is not None
            else None
        )

        if chat_id is None:
            logger.warning(
                f"Telegram chat ID not found for publisher key {publisher_key}"
            )
            return

        telegram_api_url = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage"
        message_data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(telegram_api_url, json=message_data) as response:
                if response.status != 200:
                    response_text = await response.text()
                    raise RuntimeError(
                        f"Failed to send Telegram message: {response_text}"
                    )
