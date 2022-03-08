#
# A simple notifier that just logs to the logging framework

from .notification import NotificationBase

from loguru import logger


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
