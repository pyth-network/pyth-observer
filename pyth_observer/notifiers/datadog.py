from .notification import NotificationBase

import aiohttp

from loguru import logger

from datadog_api_client import ApiClient, Configuration
from datadog_api_client.v1.api.authentication_api import AuthenticationApi
from datadog_api_client.v1.api.events_api import EventsApi
from datadog_api_client.v1.model.event_create_request import EventCreateRequest


class Notifier(NotificationBase):
    """
    Notify datadog via its events API
    """

    def __init__(self, _unused):
        self.configuration = Configuration()

    async def notify(self, error):
        title, details = error.get_event_details()

        tags = [f"symbol:{error.symbol}", f"error_code:{error.error_code}", f"network:{error.network}"]
        if error.publisher_key is not None:
            tags.append(f"publisher:{error.publisher_name}")

        body = EventCreateRequest(
            title=title,
            text="\n".join(details),
            tags=tags,
        )

        with ApiClient(self.configuration) as api_client:
            api_instance = EventsApi(api_client)
            api_instance.create_event(body=body)
