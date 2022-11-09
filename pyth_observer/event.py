import os
from typing import Dict, Literal, Protocol, TypedDict, cast

from datadog_api_client.api_client import AsyncApiClient as DatadogAPI
from datadog_api_client.configuration import Configuration as DatadogConfig
from datadog_api_client.v1.api.events_api import EventsApi as DatadogEventAPI
from datadog_api_client.v1.model.event_alert_type import EventAlertType
from datadog_api_client.v1.model.event_create_request import (
    EventCreateRequest as DatadogAPIEvent,
)
from loguru import logger

from pyth_observer.check import Check
from pyth_observer.check.price_feed import PriceFeedCheck
from pyth_observer.check.publisher import PublisherCheck


class Context(TypedDict):
    network: str
    publishers: Dict[str, str]


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
        if self.check.__class__.__bases__ == (PublisherCheck,):
            text = cast(PublisherCheck, self.check).error_message(
                self.context["publishers"]
            )
        elif self.check.__class__.__bases__ == (PriceFeedCheck,):
            text = cast(PriceFeedCheck, self.check).error_message()
        else:
            raise RuntimeError("Invalid check")

        event = DatadogAPIEvent(
            aggregation_key=f"{self.check.__class__.__name__}-{self.check.state().symbol}",
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
        if self.check.__class__.__bases__ == (PublisherCheck,):
            text = cast(PublisherCheck, self.check).error_message(
                self.context["publishers"]
            )
        elif self.check.__class__.__bases__ == (PriceFeedCheck,):
            text = cast(PriceFeedCheck, self.check).error_message()
        else:
            raise RuntimeError("Invalid check")

        level = cast(LogEventLevel, os.environ.get("LOG_EVENT_LEVEL", "INFO"))

        logger.log(level, text.split("\n")[0])
