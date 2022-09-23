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


        
        body = EventCreateRequest(
            title=title,
            text="\n".join(details),
            tags=[
                "test:jayant",
            ],
        )

        with ApiClient(self.configuration) as api_client:
            api_instance = EventsApi(api_client)
            response = api_instance.create_event(body=body)


    async def test_notify(self):
        print("HERE")
        body = EventCreateRequest(
            title="test event",
            text="\n".join(["a", "b"]),
            tags=[
                "test:jayant",
            ],
        )

        with ApiClient(self.configuration) as api_client:
            api_instance = EventsApi(api_client)
            response = api_instance.create_event(body=body)

            print(response)
