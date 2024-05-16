import asyncio
import json
import os
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any, Awaitable, Dict, List

from loguru import logger
from prometheus_client import Gauge

from pyth_observer.check import Check, State
from pyth_observer.check.price_feed import PRICE_FEED_CHECKS, PriceFeedState
from pyth_observer.check.publisher import PUBLISHER_CHECKS, PublisherState
from pyth_observer.event import DatadogEvent  # Used dynamically
from pyth_observer.event import LogEvent  # Used dynamically
from pyth_observer.event import TelegramEvent  # Used dynamically
from pyth_observer.event import ZendutyEvent  # Used dynamically
from pyth_observer.event import Event
from pyth_observer.zenduty import send_zenduty_alert

assert DatadogEvent
assert LogEvent
assert TelegramEvent
assert ZendutyEvent


class Dispatch:
    """
    Load configuration for each check/state pair, run the check, and run
    notifiers for the checks that failed.
    """

    def __init__(self, config, publishers):
        self.config = config
        self.publishers = publishers
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
        if "ZendutyEvent" in self.config["events"]:
            self.open_alerts_file = os.environ["OPEN_ALERTS_FILE"]
            self.open_alerts = self.load_alerts()

    def load_alerts(self):
        try:
            with open(self.open_alerts_file, "r") as file:
                return json.load(file)
        except FileNotFoundError:
            return {}  # Return an empty dict if the file doesn't exist

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

                if event_type == "ZendutyEvent":
                    # Add failed check to open alerts
                    alert_identifier = (
                        f"{check.__class__.__name__}-{check.state().symbol}"
                    )
                    state = check.state()
                    if isinstance(state, PublisherState):
                        alert_identifier += f"-{state.publisher_name}"
                    self.open_alerts[alert_identifier] = datetime.now().isoformat()

        await asyncio.gather(*sent_events)

        # Check open alerts and resolve those that are older than 2 minutes
        if "ZendutyEvent" in self.config["events"]:

            # Write open alerts to file to ensure persistence
            with open(self.open_alerts_file, "w") as file:
                json.dump(self.open_alerts, file)

            to_remove = []
            current_time = datetime.now()
            for identifier, last_failure in self.open_alerts.items():
                if current_time - datetime.fromisoformat(last_failure) >= timedelta(
                    minutes=2
                ):
                    logger.debug(f"Resolving Zenduty alert {identifier}")
                    response = await send_zenduty_alert(
                        alert_identifier=identifier, message=identifier, resolved=True
                    )
                    if response and 200 <= response.status < 300:
                        to_remove.append(identifier)

            for identifier in to_remove:
                del self.open_alerts[identifier]

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
