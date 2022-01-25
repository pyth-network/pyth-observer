from datetime import datetime, timedelta
from collections import defaultdict
from typing import List, Dict, Optional

from loguru import logger


from pythclient.pythaccounts import (
    PythPriceAccount,
    PythPriceStatus,
    PythPriceInfo,
)

from .notification import (
    SlackNotification,
    LoggerNotification,
)

from .events import (
    ValidationEvent,
    price_validators,
    price_account_validators,
)

logger.enable("pythclient")

MAX_SLOT_DIFFERENCE = 25


class Price:
    def __init__(
        self,
        slot=None,
        aggregate=None,
        product_attrs=None,
        publishers: Optional[Dict] = None,
    ):
        self.slot: Optional[int] = slot

        # Mapping of PythPriceComponent's latest_price_info attribute
        self.quoters: Dict[str, PythPriceInfo] = {}

        # Mapping of PythPriceComponent's last_aggregate_price_info attribute
        self.quoter_aggregates: Dict[str, PythPriceInfo] = {}

        # PythPriceAccount's aggregate_price_info
        self.aggregate: PythPriceInfo = aggregate

        self.product_attrs: dict = product_attrs

        self._publishers = publishers or {}

    def publisher_name(self, publisher_key: str) -> str:
        return self._publishers.get(
            publisher_key.lower(),
            publisher_key.lower(),
        )

    def is_aggregate_publishing(self) -> bool:
        """
        Is the aggregate price currently updating? Returns false if the aggregate price is not
        updating for any reason (e.g., too few active publishers).
        """
        return self.aggregate.price_status == PythPriceStatus.TRADING

    def is_publishing(self, publisher_key: str) -> bool:
        """
        Is a publisher publishing for a given symbol?
        """
        publisher_aggregate = self.quoter_aggregates.get(publisher_key)

        if publisher_aggregate is None:
            return False

        slot_diff = self.slot - publisher_aggregate.slot

        return all(
            [
                publisher_aggregate.price_status == PythPriceStatus.TRADING,
                publisher_aggregate.confidence_interval != 0,
                slot_diff < MAX_SLOT_DIFFERENCE,
            ]
        )


class PriceValidator:
    """
    If the publisher key is not specified, monitor prices for all publishers.
    """

    def __init__(
        self,
        key: Optional[str] = None,
        network: Optional[str] = None,
        symbol: Optional[str] = None,
    ):
        self.publisher_key = key
        self.symbol = symbol
        self.network = network
        self.last_updated_slot: Optional[int] = None
        self.events = defaultdict(dict)

    def update_slot(self, slot: Optional[int]) -> None:
        """
        Update the `last_updated_slot` attribute
        """
        if slot is None:
            return
        if self.last_updated_slot is None or slot > self.last_updated_slot:
            self.last_updated_slot = slot

    def update_events(self, event) -> None:
        if event.unique_id not in self.events:
            self.events[event.unique_id] = {
                "last_notified": None,
                "skipped": 0,
            }

        self.events[event.unique_id].update({
            'instance': event,
        })

    def verify_price_account(
        self, price_account: PythPriceAccount
    ) -> Optional[List[ValidationEvent]]:
        self.update_slot(price_account.slot)

        errors = []
        for validator in price_account_validators:
            check = validator(
                publisher_key=None,
                price_account=price_account,
                network=self.network,
                symbol=self.symbol,
            )
            if check.is_valid() is False:
                self.update_events(check)
                errors.append(check)
        return errors

    def verify_price(
        self, price: Price, include_noisy=False
    ) -> Optional[List[ValidationEvent]]:
        """
        Verify all published prices
        """
        self.update_slot(price.slot)

        errors = []

        for publisher_key in price.quoters:
            # When a publisher key is defined, skip any publishers that don't match
            if self.publisher_key is not None and publisher_key != self.publisher_key:
                continue

            is_active = price.is_publishing(publisher_key)

            if is_active and publisher_key in price.quoter_aggregates:
                for price_validator in price_validators:
                    check = price_validator(
                        publisher_key=publisher_key,
                        price=price,
                        network=self.network,
                        symbol=self.symbol,
                    )
                    if include_noisy is False and check.is_noisy():
                        continue
                    if check.is_valid() is False:
                        self.update_events(check)
                        errors.append(check)
        return errors

    async def notify(self, events, **kwargs):
        """
        Send notifications for erroneous events.

        A few useful kwargs:

            slack_webhook_url: for alerting via slack
            notification_mins: number of minutes between sending nearly identical alerts.
        """
        if kwargs.get("slack_webhook_url"):
            notifier = SlackNotification(kwargs["slack_webhook_url"])
        else:
            notifier = LoggerNotification()

        for event in events:
            event_data = self.events[event.unique_id]
            snooze = kwargs.get("notification_mins", 0)
            last_notified = event_data.get('last_notified')

            # If a notification has been sent in the past, check if this
            # notification should be skipped or not.
            if last_notified is not None:
                send_notification_time = last_notified + timedelta(minutes=snooze)

                if event.creation_time < send_notification_time:
                    logger.debug(
                        "Skipped notification on {} created {} last notification {}",
                        event.unique_id,
                        event.creation_time,
                        last_notified,
                    )
                    # Increment the skipped counter
                    self.events[event.unique_id]["skipped"] += 1
                    continue

            # Set the last notification time and reset the skipped counter
            self.events[event.unique_id].update({
                "skipped": 0,
                "last_notified": datetime.now(),
            })
            await notifier.notify(event)
