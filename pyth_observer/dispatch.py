import asyncio
import json
import os
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any, Awaitable, Dict, List

from loguru import logger

from pyth_observer.check import Check, State
from pyth_observer.check.price_feed import PRICE_FEED_CHECKS, PriceFeedState
from pyth_observer.check.publisher import PUBLISHER_CHECKS, PublisherState
from pyth_observer.event import DatadogEvent  # Used dynamically
from pyth_observer.event import LogEvent  # Used dynamically
from pyth_observer.event import TelegramEvent  # Used dynamically
from pyth_observer.event import Context, Event, ZendutyEvent
from pyth_observer.metrics import metrics
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

    def __init__(self, config, publishers, disable_telegram=False):
        self.config = config
        self.publishers = publishers
        self.disable_telegram = disable_telegram
        if "ZendutyEvent" in self.config["events"]:
            self.open_alerts_file = os.environ["OPEN_ALERTS_FILE"]
            self.open_alerts = self.load_alerts()
            # below is used to store events to later send if mutilple failures occur
            # events cannot be stored in open_alerts as they are not JSON serializable.
            self.delayed_events = {}

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
        context = Context(
            network=self.config["network"]["name"], publishers=self.publishers
        )

        current_time = datetime.now()
        for check in failed_checks:
            for event_type in self.config["events"]:
                if event_type == "TelegramEvent" and self.disable_telegram:
                    continue
                event: Event = globals()[event_type](check, context)

                if event_type in ["ZendutyEvent", "TelegramEvent"]:
                    alert_identifier = self.generate_alert_identifier(check)
                    alert = self.open_alerts.get(alert_identifier)
                    if alert is None:
                        self.open_alerts[alert_identifier] = {
                            "type": check.__class__.__name__,
                            "window_start": current_time.isoformat(),
                            "failures": 1,
                            "last_window_failures": None,
                            "sent": False,
                        }
                    else:
                        alert["failures"] += 1
                    self.delayed_events[f"{event_type}-{alert_identifier}"] = event
                    continue  # Skip sending immediately for ZendutyEvent or TelegramEvent

                sent_events.append(event.send())

        await asyncio.gather(*sent_events)

        metrics.update_alert_metrics(self.open_alerts)

        if "ZendutyEvent" in self.config["events"]:
            await self.process_zenduty_events(current_time)

    def check_price_feed(self, state: PriceFeedState) -> List[Check]:
        failed_checks: List[Check] = []
        total_checks = 0
        passed_checks = 0

        for check_class in PRICE_FEED_CHECKS:
            config = self.load_config(check_class.__name__, state.symbol)

            if config["enable"]:
                total_checks += 1
                check = check_class(state, config)

                with metrics.time_operation(
                    metrics.check_execution_duration, check_type=check_class.__name__
                ):
                    check_passed = check.run()

                if check_passed:
                    passed_checks += 1
                else:
                    failed_checks.append(check)

        if total_checks > 0:
            success_rate = passed_checks / total_checks
            metrics.check_success_rate.labels(
                check_type="price_feed", symbol=state.symbol
            ).set(success_rate)

        return failed_checks

    def check_publisher(self, state: PublisherState) -> List[Check]:
        failed_checks: List[Check] = []
        total_checks = 0
        passed_checks = 0

        for check_class in PUBLISHER_CHECKS:
            config = self.load_config(check_class.__name__, state.symbol)

            if config["enable"]:
                total_checks += 1
                check = check_class(state, config)

                with metrics.time_operation(
                    metrics.check_execution_duration, check_type=check_class.__name__
                ):
                    check_passed = check.run()

                if check_passed:
                    passed_checks += 1
                else:
                    failed_checks.append(check)

        if total_checks > 0:
            success_rate = passed_checks / total_checks
            metrics.check_success_rate.labels(
                check_type="publisher", symbol=state.symbol
            ).set(success_rate)

        return failed_checks

    def load_config(self, check_name: str, symbol: str) -> Dict[str, Any]:
        config = deepcopy(self.config["checks"]["global"][check_name])

        if symbol in self.config["checks"]:
            if check_name in self.config["checks"][symbol]:
                config |= self.config["checks"][symbol][check_name]

        return config

    # Zenduty Functions
    def generate_alert_identifier(self, check):
        alert_identifier = f"{check.__class__.__name__}-{check.state().symbol}"
        state = check.state()
        if isinstance(state, PublisherState):
            alert_identifier += f"-{state.publisher_name}"
        return alert_identifier

    def check_zd_alert_status(self, alert_identifier, current_time):
        alert = self.open_alerts.get(alert_identifier)
        if alert is not None:
            # Reset the failure count if 5m has elapsed
            if current_time - datetime.fromisoformat(
                alert["window_start"]
            ) >= timedelta(minutes=5):
                alert["window_start"] = current_time.isoformat()
                alert["last_window_failures"] = alert["failures"]
                alert["failures"] = 0

    async def process_zenduty_events(self, current_time):
        to_remove = []
        to_alert = []

        for identifier, info in self.open_alerts.items():
            self.check_zd_alert_status(identifier, current_time)
            check_config = self.config["checks"]["global"][info["type"]]
            alert_threshold = check_config.get("alert_threshold", 5)
            resolution_threshold = check_config.get("resolution_threshold", 3)
            # Resolve the alert if raised and failed < $threshold times in the last 5m window
            resolved = False
            if (
                info["last_window_failures"] is not None
                and info["last_window_failures"] <= resolution_threshold
            ):
                logger.debug(f"Resolving Zenduty alert {identifier}")
                resolved = True

                if info["sent"]:
                    response = await send_zenduty_alert(
                        identifier, identifier, resolved=True
                    )
                    if response and 200 <= response.status < 300:
                        to_remove.append(identifier)
                        metrics.alerts_sent_total.labels(
                            alert_type=info["type"], channel="zenduty"
                        ).inc()
                else:
                    to_remove.append(identifier)
            # Raise alert if failed > $threshold times within the last 5m window
            # or if already alerted and not yet resolved.
            # Re-alert at the start of each hour but not more often.
            elif (
                info["failures"] >= alert_threshold or (info["sent"] and not resolved)
            ) and (
                not info.get("last_alert")  # First alert - send immediately
                or (  # Subsequent alerts - send at the start of each hour
                    current_time - datetime.fromisoformat(info["last_alert"])
                    > timedelta(minutes=5)
                    and current_time.minute == 0  # Only alert at the start of each hour
                )
            ):
                logger.debug(f"Raising Zenduty alert {identifier}")
                self.open_alerts[identifier]["sent"] = True
                self.open_alerts[identifier]["last_alert"] = current_time.isoformat()
                for event_type in ["ZendutyEvent", "TelegramEvent"]:
                    key = f"{event_type}-{identifier}"
                    event = self.delayed_events.get(key)
                    if event:
                        to_alert.append(event.send())
                        metrics.alerts_sent_total.labels(
                            alert_type=info["type"],
                            channel=event_type.lower().replace("event", ""),
                        ).inc()

        # Send the alerts that were delayed due to thresholds
        await asyncio.gather(*to_alert)

        # Remove alerts that have been resolved
        for identifier in to_remove:
            if self.open_alerts.get(identifier):
                del self.open_alerts[identifier]
            for event_type in ["ZendutyEvent", "TelegramEvent"]:
                key = f"{event_type}-{identifier}"
                if self.delayed_events.get(key):
                    del self.delayed_events[key]

        metrics.update_alert_metrics(self.open_alerts)

        with open(self.open_alerts_file, "w") as file:
            json.dump(self.open_alerts, file)
