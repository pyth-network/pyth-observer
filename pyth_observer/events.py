from typing import TypedDict

from datadog_api_client.api_client import AsyncApiClient as DatadogAPI
from datadog_api_client.v1.model.event_alert_type import EventAlertType
from datadog_api_client.configuration import Configuration as DatadogConfig
from datadog_api_client.v1.api.events_api import EventsApi as DatadogEventAPI
from datadog_api_client.v1.model.event_create_request import (
    EventCreateRequest as DatadogAPIEvent,
)
from loguru import logger

from pyth_observer.checks import Check


class Context(TypedDict):
    network: str


class Event:
    check: Check

    def __init__(self, check: Check, context: Context):
        self.check = check
        self.context = context

    async def send(self):
        raise RuntimeError("Not implemented")


class DatadogEvent(Event):
    async def send(self):
        event = DatadogAPIEvent(
            aggregation_key=f"{self.check.__class__.__name__}-{self.check.state.symbol}",
            title=f"{self.check.__class__.__name__} failed on {self.check.state.symbol}",
            text=self.check.error_message(),
            tags=[
                f"network:{self.context['network']}",
                f"symbol:{self.check.state.symbol}",
                f"check:{self.check.__class__.__name__}",
            ],
            alert_type=EventAlertType.WARNING,
            source_type_name="my_apps",
        )

        # This assumes that DD_API_KEY and DD_SITE env. variables are set. Also,
        # using the async API makes the events api return a coroutine, so we
        # ignore the pyright warning.
        async with DatadogAPI(DatadogConfig()) as api:
            response = await DatadogEventAPI(api).create_event(
                body=event
            )  # pyright: ignore

            if response.status != "ok":
                raise RuntimeError(
                    f"Failed to send Datadog event (status: {response.status})"
                )


class LogEvent(Event):
    async def send(self):
        logger.warning(self.check.error_message())


class SlackEvent(Event):
    pass
