import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Protocol, runtime_checkable
from zoneinfo import ZoneInfo

from loguru import logger
from pythclient.market_schedule import MarketSchedule
from pythclient.pythaccounts import PythPriceStatus
from pythclient.solana import SolanaPublicKey


@dataclass
class PriceUpdate:
    """Represents a single price with its timestamp (epoch seconds)."""

    timestamp: int
    price: float


PUBLISHER_EXCLUSION_DISTANCE = 25
PUBLISHER_CACHE_MAX_LEN = 30
"""Roughly 30 mins of updates, since the check runs about once a minute"""

PUBLISHER_CACHE = defaultdict(lambda: deque(maxlen=PUBLISHER_CACHE_MAX_LEN))
"""
Cache that holds tuples of (price, timestamp) for publisher/feed combos as they stream in.
Entries longer than `PUBLISHER_CACHE_MAX_LEN` are automatically pruned.
Used by the PublisherStalledCheck to detect stalls in prices.
"""


@dataclass
class PublisherState:
    publisher_name: str
    symbol: str
    asset_type: str
    schedule: MarketSchedule
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
    def __init__(self, state: PublisherState, config: PublisherCheckConfig) -> None:
        ...

    def state(self) -> PublisherState:
        ...

    def run(self) -> bool:
        ...

    def error_message(self) -> Dict[str, Any]:
        ...


class PublisherWithinAggregateConfidenceCheck(PublisherCheck):
    def __init__(self, state: PublisherState, config: PublisherCheckConfig) -> None:
        self.__state = state
        self.__max_interval_distance: float = float(config["max_interval_distance"])

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

        # Skip if confidence interval aggregate is zero
        if self.__state.confidence_interval_aggregate == 0:
            return True

        intervals_away = abs(diff / self.__state.confidence_interval_aggregate)

        # Pass if price diff is less than max interval distance
        if intervals_away < self.__max_interval_distance:
            return True

        # Fail
        return False

    def error_message(self) -> Dict[str, Any]:
        diff = self.__state.price - self.__state.price_aggregate
        if self.__state.confidence_interval_aggregate == 0:
            intervals_away = abs(diff)
        else:
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
    def __init__(self, state: PublisherState, config: PublisherCheckConfig) -> None:
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

    def error_message(self) -> Dict[str, Any]:
        return {
            "msg": f"{self.__state.publisher_name} confidence interval is too tight.",
            "type": "PublisherConfidenceIntervalCheck",
            "publisher": self.__state.publisher_name,
            "symbol": self.__state.symbol,
            "price": self.__state.price,
            "confidence_interval": self.__state.confidence_interval,
        }


class PublisherOfflineCheck(PublisherCheck):
    def __init__(self, state: PublisherState, config: PublisherCheckConfig) -> None:
        self.__state = state
        self.__max_slot_distance: int = int(config["max_slot_distance"])
        self.__abandoned_slot_distance: int = int(config["abandoned_slot_distance"])

    def state(self) -> PublisherState:
        return self.__state

    def run(self) -> bool:
        market_open = self.__state.schedule.is_market_open(
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

    def error_message(self) -> Dict[str, Any]:
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
    def __init__(self, state: PublisherState, config: PublisherCheckConfig) -> None:
        self.__state = state
        self.__max_aggregate_distance: float = float(
            config["max_aggregate_distance"]
        )  # %
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
        if self.__state.price == 0 or self.__state.price_aggregate == 0:
            return True

        deviation = (self.ci_adjusted_price_diff() / self.__state.price_aggregate) * 100

        # Pass if deviation is less than max distance
        if deviation <= self.__max_aggregate_distance:
            return True

        # Fail
        return False

    def error_message(self) -> Dict[str, Any]:
        if self.__state.price_aggregate == 0:
            deviation = self.ci_adjusted_price_diff()
        else:
            deviation = (
                self.ci_adjusted_price_diff() / self.__state.price_aggregate
            ) * 100

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
    def __init__(self, state: PublisherState, config: PublisherCheckConfig) -> None:
        self.__state = state
        self.__stall_time_limit: int = int(
            config["stall_time_limit"]
        )  # Time in seconds
        self.__abandoned_time_limit: int = int(config["abandoned_time_limit"])
        self.__max_slot_distance: int = int(config["max_slot_distance"])

        from pyth_observer.check.stall_detection import (  # noqa: deferred import to avoid circular import
            StallDetector,
        )

        self.__detector = StallDetector(
            stall_time_limit=self.__stall_time_limit,
            noise_threshold=float(config["noise_threshold"]),
            min_noise_samples=int(config["min_noise_samples"]),
        )

    def state(self) -> PublisherState:
        return self.__state

    def run(self) -> bool:
        market_open = self.__state.schedule.is_market_open(
            datetime.now(ZoneInfo("America/New_York")),
        )

        if not market_open:
            return True

        distance = self.__state.latest_block_slot - self.__state.slot

        # Pass for redemption rates because they are expected to be static for long periods
        if self.__state.asset_type == "Crypto Redemption Rate":
            return True

        #  Pass when publisher is offline because PublisherOfflineCheck will be triggered
        if distance >= self.__max_slot_distance:
            return True

        current_time = int(time.time())

        publisher_key = (self.__state.publisher_name, self.__state.symbol)
        updates = PUBLISHER_CACHE[publisher_key]

        # Only cache new prices, let repeated prices grow stale.
        # These will be caught as an exact stall in the detector.
        is_repeated_price = updates and updates[-1].price == self.__state.price
        cur_update = PriceUpdate(current_time, self.__state.price)
        if not is_repeated_price:
            PUBLISHER_CACHE[publisher_key].append(cur_update)

        # Analyze for stalls
        result = self.__detector.analyze_updates(list(updates), cur_update)
        logger.debug(f"Stall detection result: {result}")

        self.__last_analysis = result  # For error logging

        # If we've been stalled for too long, abandon this check
        if result.is_stalled and result.duration > self.__abandoned_time_limit:
            return True

        return not result.is_stalled

    def error_message(self) -> Dict[str, Any]:
        stall_duration = f"{self.__last_analysis.duration:.1f} seconds"
        return {
            "msg": f"{self.__state.publisher_name} has been publishing the same price of {self.__state.symbol} for {stall_duration}",
            "type": "PublisherStalledCheck",
            "publisher": self.__state.publisher_name,
            "symbol": self.__state.symbol,
            "price": self.__state.price,
            "stall_type": self.__last_analysis.stall_type,
            "stall_duration": stall_duration,
            "analysis": asdict(self.__last_analysis),
        }


PUBLISHER_CHECKS = [
    PublisherWithinAggregateConfidenceCheck,
    PublisherConfidenceIntervalCheck,
    PublisherOfflineCheck,
    PublisherPriceCheck,
    PublisherStalledCheck,
]
