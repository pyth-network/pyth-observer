import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Protocol, runtime_checkable
from zoneinfo import ZoneInfo

from pythclient.calendar import is_market_open
from pythclient.pythaccounts import PythPriceStatus
from pythclient.solana import SolanaPublicKey

PUBLISHER_EXCLUSION_DISTANCE = 25

PUBLISHER_CACHE = {}


@dataclass
class PublisherState:
    publisher_name: str
    symbol: str
    asset_type: str
    public_key: SolanaPublicKey
    status: PythPriceStatus
    aggregate_status: PythPriceStatus
    slot: int
    aggregate_slot: int
    latest_block_slot: int
    price: float
    price_aggregate: float
    confidence_interval: float
    confidence_interval_aggregate: float


PublisherCheckConfig = Dict[str, str | float | int | bool]


@runtime_checkable
class PublisherCheck(Protocol):
    def __init__(self, state: PublisherState, config: PublisherCheckConfig):
        ...

    def state(self) -> PublisherState:
        ...

    def run(self) -> bool:
        ...

    def error_message(self) -> dict:
        ...


class PublisherWithinAggregateConfidenceCheck(PublisherCheck):
    def __init__(self, state: PublisherState, config: PublisherCheckConfig):
        self.__state = state
        self.__max_interval_distance: int = int(config["max_interval_distance"])

    def state(self) -> PublisherState:
        return self.__state

    def run(self) -> bool:
        # Skip if not trading
        if self.__state.status != PythPriceStatus.TRADING:
            return True

        # Skip if aggregate is not trading
        if self.__state.aggregate_status != PythPriceStatus.TRADING:
            return True

        # Skip if confidence interval is zero
        if self.__state.confidence_interval == 0:
            return True

        # Pass if publisher slot is far from aggregate slot
        distance = abs(self.__state.slot - self.__state.aggregate_slot)
        if distance > PUBLISHER_EXCLUSION_DISTANCE:
            return True

        diff = self.__state.price - self.__state.price_aggregate
        intervals_away = abs(diff / self.__state.confidence_interval_aggregate)

        # Pass if price diff is less than max interval distance
        if intervals_away < self.__max_interval_distance:
            return True

        # Fail
        return False

    def error_message(self) -> dict:
        diff = self.__state.price - self.__state.price_aggregate
        intervals_away = abs(diff / self.__state.confidence_interval_aggregate)
        return {
            "msg": f"{self.__state.publisher_name} price is {intervals_away} times away from confidence.",
            "type": "PublisherWithinAggregateConfidenceCheck",
            "publisher": self.__state.publisher_name,
            "symbol": self.__state.symbol,
            "publisher_price": f"{self.__state.price} ± {self.__state.confidence_interval}",
            "aggregate_price": f"{self.__state.price_aggregate} ± {self.__state.confidence_interval_aggregate}",
        }


class PublisherConfidenceIntervalCheck(PublisherCheck):
    def __init__(self, state: PublisherState, config: PublisherCheckConfig):
        self.__state = state
        self.__min_confidence_interval: int = int(config["min_confidence_interval"])

    def state(self) -> PublisherState:
        return self.__state

    def run(self) -> bool:
        # Skip if not trading
        if self.__state.status != PythPriceStatus.TRADING:
            return True

        # Pass if publisher slot is far from aggregate slot
        distance = abs(self.__state.slot - self.__state.aggregate_slot)
        if distance > PUBLISHER_EXCLUSION_DISTANCE:
            return True

        # Pass if confidence interval is greater than min_confidence_interval
        if self.__state.confidence_interval > self.__min_confidence_interval:
            return True

        # Fail
        return False

    def error_message(self) -> dict:
        return {
            "msg": f"{self.__state.publisher_name} confidence interval is too tight.",
            "type": "PublisherConfidenceIntervalCheck",
            "publisher": self.__state.publisher_name,
            "symbol": self.__state.symbol,
            "price": self.__state.price,
            "confidence_interval": self.__state.confidence_interval,
        }


class PublisherOfflineCheck(PublisherCheck):
    def __init__(self, state: PublisherState, config: PublisherCheckConfig):
        self.__state = state
        self.__max_slot_distance: int = int(config["max_slot_distance"])
        self.__abandoned_slot_distance: int = int(config["abandoned_slot_distance"])

    def state(self) -> PublisherState:
        return self.__state

    def run(self) -> bool:
        market_open = is_market_open(
            self.__state.asset_type.lower(),
            datetime.now(ZoneInfo("America/New_York")),
        )

        if not market_open:
            return True

        distance = self.__state.latest_block_slot - self.__state.slot

        # Pass if publisher slot is not too far from aggregate slot
        if distance < self.__max_slot_distance:
            return True

        # Pass if publisher has been inactive for a long time
        if distance > self.__abandoned_slot_distance:
            return True

        # Fail
        return False

    def error_message(self) -> dict:
        distance = self.__state.latest_block_slot - self.__state.slot
        return {
            "msg": f"{self.__state.publisher_name} hasn't published recently for {distance} slots.",
            "type": "PublisherOfflineCheck",
            "publisher": self.__state.publisher_name,
            "symbol": self.__state.symbol,
            "publisher_slot": self.__state.slot,
            "aggregate_slot": self.__state.aggregate_slot,
        }


class PublisherPriceCheck(PublisherCheck):
    def __init__(self, state: PublisherState, config: PublisherCheckConfig):
        self.__state = state
        self.__max_aggregate_distance: int = int(config["max_aggregate_distance"])  # %
        self.__max_slot_distance: int = int(config["max_slot_distance"])  # Slots

    def state(self) -> PublisherState:
        return self.__state

    def run(self) -> bool:
        # Skip if aggregate status is not trading
        if self.__state.aggregate_status != PythPriceStatus.TRADING:
            return True

        # Skip if not trading
        if self.__state.status != PythPriceStatus.TRADING:
            return True

        # Skip if publisher is too far behind
        slot_diff = abs(self.__state.slot - self.__state.aggregate_slot)
        if slot_diff > self.__max_slot_distance:
            return True

        # Skip if published price is zero
        if self.__state.price == 0:
            return True

        deviation = (self.ci_adjusted_price_diff() / self.__state.price_aggregate) * 100

        # Pass if deviation is less than max distance
        if deviation <= self.__max_aggregate_distance:
            return True

        # Fail
        return False

    def error_message(self) -> dict:
        deviation = (self.ci_adjusted_price_diff() / self.__state.price_aggregate) * 100
        return {
            "msg": f"{self.__state.publisher_name} price is too far from aggregate price.",
            "type": "PublisherPriceCheck",
            "publisher": self.__state.publisher_name,
            "symbol": self.__state.symbol,
            "publisher_price": f"{self.__state.price} ± {self.__state.confidence_interval}",
            "aggregate_price": f"{self.__state.price_aggregate} ± {self.__state.confidence_interval_aggregate}",
            "deviation": f"{deviation:.2f}%",
        }

    # Returns the distance between the aggregate price and the closest side of the publisher's confidence interval
    # Returns 0 if the aggregate price is within the publisher's confidence interval.
    def ci_adjusted_price_diff(self) -> float:
        price_only_diff = abs(self.__state.price - self.__state.price_aggregate)
        return max(price_only_diff - self.__state.confidence_interval, 0)


class PublisherStalledCheck(PublisherCheck):
    def __init__(self, state: PublisherState, config: PublisherCheckConfig):
        self.__state = state
        self.__stall_time_limit: int = int(
            config["stall_time_limit"]
        )  # Time in seconds
        self.__abandoned_time_limit: int = int(config["abandoned_time_limit"])
        self.__max_slot_distance: int = int(config["max_slot_distance"])

    def state(self) -> PublisherState:
        return self.__state

    def run(self) -> bool:
        market_open = is_market_open(
            self.__state.asset_type.lower(),
            datetime.now(ZoneInfo("America/New_York")),
        )

        if not market_open:
            return True

        distance = self.__state.latest_block_slot - self.__state.slot

        #  Pass when publisher is offline because PublisherOfflineCheck will be triggered
        if distance >= self.__max_slot_distance:
            return True

        publisher_key = (self.__state.publisher_name, self.__state.symbol)
        current_time = int(time.time())
        previous_price, last_change_time = PUBLISHER_CACHE.get(
            publisher_key, (None, None)
        )

        if previous_price is None or self.__state.price != previous_price:
            PUBLISHER_CACHE[publisher_key] = (self.__state.price, current_time)
            return True

        time_since_last_change = current_time - last_change_time
        if time_since_last_change > self.__stall_time_limit:
            if time_since_last_change > self.__abandoned_time_limit:
                return True  # Abandon this check after the abandoned time limit
            return False

        return True

    def error_message(self) -> dict:
        return {
            "msg": f"{self.__state.publisher_name} has been publishing the same price for too long.",
            "type": "PublisherStalledCheck",
            "publisher": self.__state.publisher_name,
            "symbol": self.__state.symbol,
            "price": self.__state.price,
            "stall_duration": f"{int(time.time()) - PUBLISHER_CACHE[(self.__state.publisher_name, self.__state.symbol)][1]} seconds",
        }


PUBLISHER_CHECKS = [
    PublisherWithinAggregateConfidenceCheck,
    PublisherConfidenceIntervalCheck,
    PublisherOfflineCheck,
    PublisherPriceCheck,
    PublisherStalledCheck,
]
