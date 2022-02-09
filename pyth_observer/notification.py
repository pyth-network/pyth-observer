#!/usr/bin/env python3
import datetime

import aiohttp
import pytz
from loguru import logger


class Notification:
    def get_footer(self, error):
        """
        A footer for longer form messages
        """
        now = datetime.datetime.now(tz=pytz.UTC)
        nowtime = now.isoformat(sep=" ", timespec="seconds")
        return [
            f"Network: {error.network}",
            f"Last seen {nowtime}",
        ]

    async def notify(self, error) -> None:
        raise NotImplementedError


class LoggerNotification(Notification):
    """
    Do nothing notification, just log to stderr
    """

    async def notify(self, error):
        title, details = error.get_event_details()

        logger.error(
            "{} on {}: {} - {}",
            error.error_code,
            error.network,
            title,
            ", ".join(details),
        )


class SlackNotification(Notification):
    """
    Notify slack via a webhook url
    """

    def __init__(self, webhook_url):
        self.url = webhook_url

    async def notify(self, error):
        title, details = error.get_event_details()
        alert_color = getattr(error, "alert_color", "#f3c744")

        details.extend(
            self.get_footer(error),
        )

        data = {
            "attachments": [
                {
                    "color": alert_color,
                    "blocks": [
                        {
                            "type": "header",
                            "text": {
                                "type": "plain_text",
                                "text": title,
                            },
                        },
                        {
                            "type": "divider",
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "\n".join(details),
                            },
                        },
                    ],
                },
            ],
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(self.url, json=data) as response:
                try:
                    response.raise_for_status()
                except Exception as exc:
                    logger.exception(exc)
                    return

                logger.error("Sent to slack: {}", title)
