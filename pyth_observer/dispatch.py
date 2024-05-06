import asyncio
from copy import deepcopy
from typing import Any, Awaitable, Dict, List

from prometheus_client import Gauge

from pyth_observer.check import Check, State
from pyth_observer.check.price_feed import PRICE_FEED_CHECKS, PriceFeedState
from pyth_observer.check.publisher import PUBLISHER_CHECKS, PublisherState
from pyth_observer.event import DatadogEvent  # Used dynamically
from pyth_observer.event import LogEvent  # Used dynamically
from pyth_observer.event import TelegramEvent  # Used dynamically
from pyth_observer.event import Event

assert DatadogEvent
assert LogEvent
assert TelegramEvent


class Dispatch:
    """
    Load configuration for each check/state pair, run the check, and run
    notifiers for the checks that failed.
    """

    def __init__(self, config, publishers, telegram_mapping=None):
        self.config = config
        self.publishers = publishers
        self.telegram_mapping = telegram_mapping
        self.price_feed_check_gauge = Gauge(
            "price_feed_check_failed",
            "Price feed check failure status",
            ["check", "symbol"],
        )
        self.publisher_check_gauge = Gauge(
            "publisher_check_failed",
            "Publisher check failure status",
            ["check", "symbol", "publisher"],
        )

    async def run(self, states: List[State]):
        # First, run each check and store the ones that failed
        failed_checks: List[Check] = []

        for state in states:
            if isinstance(state, PriceFeedState):
                failed_checks.extend(self.check_price_feed(state))
            elif isinstance(state, PublisherState):
                failed_checks.extend(self.check_publisher(state))
            else:
                raise RuntimeError("Unknown state")

        # Then, wrap each failed check in events and send them
        sent_events: List[Awaitable] = []
        context = {
            "network": self.config["network"]["name"],
            "publishers": self.publishers,
            "telegram_mapping": self.telegram_mapping or {},
        }

        for check in failed_checks:
            for event_type in self.config["events"]:
                event: Event = globals()[event_type](check, context)

                sent_events.append(event.send())

        await asyncio.gather(*sent_events)

    def check_price_feed(self, state: PriceFeedState) -> List[Check]:
        failed_checks: List[Check] = []

        for check_class in PRICE_FEED_CHECKS:
            config = self.load_config(check_class.__name__, state.symbol)
            check = check_class(state, config)
            gauge = self.price_feed_check_gauge.labels(
                check=check_class.__name__,
                symbol=state.symbol,
            )

            if config["enable"]:
                if check.run():
                    gauge.set(0)
                else:
                    failed_checks.append(check)
                    gauge.set(1)

        return failed_checks

    def check_publisher(self, state: PublisherState) -> List[Check]:
        failed_checks: List[Check] = []

        for check_class in PUBLISHER_CHECKS:
            config = self.load_config(check_class.__name__, state.symbol)
            check = check_class(state, config)
            gauge = self.publisher_check_gauge.labels(
                check=check_class.__name__,
                symbol=state.symbol,
                publisher=self.publishers.get(state.public_key, state.public_key),
            )

            if config["enable"]:
                if check.run():
                    gauge.set(0)
                else:
                    gauge.set(1)
                    failed_checks.append(check)

        return failed_checks

    def load_config(self, check_name: str, symbol: str) -> Dict[str, Any]:
        config = deepcopy(self.config["checks"]["global"][check_name])

        if symbol in self.config["checks"]:
            if check_name in self.config["checks"][symbol]:
                config |= self.config["checks"][symbol][check_name]

        return config
