#!/usr/bin/env python3
import datetime

import pytz


class NotificationBase:
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

    def __init__(self, param):
        if param is not None:
            raise ValueError("Basic Notification takes no parameters")

    async def notify(self, error) -> None:
        raise NotImplementedError
