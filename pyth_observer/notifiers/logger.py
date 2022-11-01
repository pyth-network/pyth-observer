#
# A simple notifier that just logs to the logging framework

from loguru import logger

from .notification import NotificationBase


class Notifier(NotificationBase):
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
