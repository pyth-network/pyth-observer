from .notification import NotificationBase

import aiohttp

from loguru import logger

from datadog_api_client import ApiClient, Configuration
from datadog_api_client.v1.api.authentication_api import AuthenticationApi


class Notifier(NotificationBase):
    """
    Notify datadog via its events API
    """

    def __init__(self):
        self.configuration = Configuration()

    async def notify(self, error):
        title, details = error.get_event_details()

        body = EventCreateRequest(
            title=title,
            text=details,
            tags=[
                "test:jayant",
            ],
        )

        with ApiClient(self.configuration) as api_client:
            api_instance = EventsApi(api_client)
            response = api_instance.create_event(body=body)
