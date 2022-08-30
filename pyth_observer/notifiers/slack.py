# Notify slack via a webhook url
#

from .notification import NotificationBase

import aiohttp

from loguru import logger


class Notifier(NotificationBase):
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
