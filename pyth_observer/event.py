import os
from typing import Dict, Protocol, TypedDict, cast

import aiohttp
from datadog_api_client.api_client import AsyncApiClient as DatadogAPI
from datadog_api_client.configuration import Configuration as DatadogConfig
from datadog_api_client.v1.api.events_api import EventsApi as DatadogEventAPI
from datadog_api_client.v1.model.event_alert_type import EventAlertType
from datadog_api_client.v1.model.event_create_request import EventCreateRequest
from dotenv import load_dotenv
from loguru import logger

from pyth_observer.alert_utils import generate_alert_identifier
from pyth_observer.check import Check
from pyth_observer.check.publisher import PublisherCheck, PublisherState
from pyth_observer.models import Publisher
from pyth_observer.zenduty import send_zenduty_alert

load_dotenv()


class Context(TypedDict):
    network: str
    publishers: Dict[str, Publisher]


class Event(Protocol):
    check: Check
    context: Context

    async def send(self) -> None:
        ...


class DatadogEvent(Event):
    def __init__(self, check: Check, context: Context) -> None:
        self.check = check
        self.context = context

    async def send(self) -> None:
        # Publisher checks expect the key -> name mapping of publishers when
        # generating the error title/message.
        event_content = self.check.error_message()
        event_title = event_content["msg"]
        event_text = ""
        for key, value in event_content.items():
            event_text += f"{key}: {value}\n"

        # An example is: PriceFeedOfflineCheck-Crypto.AAVE/USD
        aggregation_key = f"{self.check.__class__.__name__}-{self.check.state().symbol}"

        if self.check.__class__.__bases__ == (PublisherCheck,):
            # Add publisher key to the aggregation key to separate different faulty publishers
            # An example would be: PublisherPriceCheck-Crypto.AAVE/USD-9TvAYCUkGajRXs....
            aggregation_key += "-" + self.check.state().public_key.key

        event = EventCreateRequest(
            aggregation_key=aggregation_key,
            title=event_title,
            text=event_text,
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


class LogEvent(Event):
    def __init__(self, check: Check, context: Context) -> None:
        self.check = check
        self.context = context

    async def send(self) -> None:
        # Publisher checks expect the key -> name mapping of publishers when
        # generating the error title/message.
        event = self.check.error_message()
        with logger.contextualize(**event):
            logger.info(event["msg"])


class TelegramEvent(Event):
    def __init__(self, check: Check, context: Context) -> None:
        self.check = check
        self.context = context
        self.telegram_bot_token = os.environ["TELEGRAM_BOT_TOKEN"]

    async def send(self) -> None:
        if self.check.__class__.__bases__ == (PublisherCheck,):
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

            telegram_api_url = (
                f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            )

            formatted_message = ""
            for key, value in text.items():
                formatted_message += (
                    f"*{key.capitalize().replace('_', ' ')}:* {value}\n"
                )

            message_data = {
                "chat_id": chat_id,
                "text": formatted_message,
                "parse_mode": "Markdown",
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    telegram_api_url, json=message_data
                ) as response:
                    if response.status != 200:
                        response_text = await response.text()
                        logger.error(
                            f"Failed to send Telegram message: {response_text}"
                        )


class ZendutyEvent(Event):
    def __init__(self, check: Check, context: Context) -> None:
        self.check = check
        self.context = context

    async def send(self) -> None:
        event_details = self.check.error_message()
        summary = ""
        for key, value in event_details.items():
            summary += f"{key}: {value}\n"

        alert_identifier = generate_alert_identifier(self.check)
        state = self.check.state()
        if isinstance(state, PublisherState):
            symbol = (
                self.check.state().symbol.replace(".", "-").replace("/", "-").lower()
            )
            cluster = (
                "solana-mainnet-beta"
                if self.context["network"] == "mainnet"
                else self.context["network"]
            )
            publisher_key = state.public_key.key
            summary += f"https://pyth.network/metrics?price-feed={symbol}&cluster={cluster}&publisher={publisher_key}\n"

        logger.debug(f"Sending Zenduty alert for {alert_identifier}")
        await send_zenduty_alert(
            alert_identifier=alert_identifier, message=alert_identifier, summary=summary
        )
