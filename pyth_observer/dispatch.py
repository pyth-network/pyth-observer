import asyncio
from typing import Any, Awaitable, Dict, List

from pyth_observer.check import Check, State
from pyth_observer.check.price_feed import PRICE_FEED_CHECKS, PriceFeedState
from pyth_observer.check.publisher import PUBLISHER_CHECKS, PublisherState
from pyth_observer.event import DatadogEvent  # Used dynamically
from pyth_observer.event import LogEvent  # Used dynamically
from pyth_observer.event import Event

assert DatadogEvent
assert LogEvent


class Dispatch:
    """
    Load configuration for each check/state pair, run the check, and run
    notifiers for the checks that failed.
    """

    def __init__(self, config, publishers):
        self.config = config
        self.publishers = publishers

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

            if config["enable"] and not check.run():
                failed_checks.append(check)

        return failed_checks

    def check_publisher(self, state) -> List[Check]:
        failed_checks: List[Check] = []

        for check_class in PUBLISHER_CHECKS:
            config = self.load_config(check_class.__name__, state.symbol)
            check = check_class(state, config)

            if config["enable"] and not check.run():
                failed_checks.append(check)

        return failed_checks

    def load_config(self, check_name: str, symbol: str) -> Dict[str, Any]:
        config = self.config["checks"]["global"][check_name]

        if symbol in self.config["checks"]:
            if check_name in self.config["checks"][symbol]:
                config |= self.config["checks"][symbol][check_name]

        return config
