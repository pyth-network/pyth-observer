from dataclasses import dataclass
from textwrap import dedent
from typing import Dict, Protocol, runtime_checkable

from pythclient.pythaccounts import PythPriceStatus
from pythclient.solana import SolanaPublicKey

PUBLISHER_EXCLUSION_DISTANCE = 25


@dataclass
class PublisherState:
    publisher_name: str
    symbol: str
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

    def error_message(self) -> str:
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

    def error_message(self) -> str:
        diff = self.__state.price - self.__state.price_aggregate
        intervals_away = abs(diff / self.__state.confidence_interval_aggregate)

        return dedent(
            f"""
            {self.__state.publisher_name} price not within aggregate confidence.
            It is {intervals_away} times away from confidence.

            Symbol: {self.__state.symbol}
            Publisher price: {self.__state.price} ± {self.__state.confidence_interval}
            Aggregate price: {self.__state.price_aggregate} ± {self.__state.confidence_interval_aggregate}
            """
        ).strip()


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

    def error_message(self) -> str:
        return dedent(
            f"""
            {self.__state.publisher_name} confidence interval is too tight.

            Symbol: {self.__state.symbol}
            Price: {self.__state.price}
            Confidence interval: {self.__state.confidence_interval}
            """
        ).strip()


class PublisherOfflineCheck(PublisherCheck):
    def __init__(self, state: PublisherState, config: PublisherCheckConfig):
        self.__state = state
        self.__max_slot_distance: int = int(config["max_slot_distance"])
        self.__abandoned_slot_distance: int = int(config["abandoned_slot_distance"])

    def state(self) -> PublisherState:
        return self.__state

    def run(self) -> bool:
        distance = self.__state.latest_block_slot - self.__state.slot

        # Pass if publisher slot is not too far from aggregate slot
        if distance < self.__max_slot_distance:
            return True

        # Pass if publisher has been inactive for a long time
        if distance > self.__abandoned_slot_distance:
            return True

        # Fail
        return False

    def error_message(self) -> str:
        distance = self.__state.latest_block_slot - self.__state.slot
        return dedent(
            f"""
            {self.__state.publisher_name} hasn't published recently for {distance} slots.

            Symbol: {self.__state.symbol}
            Publisher slot: {self.__state.slot}
            Aggregate slot: {self.__state.aggregate_slot}
            """
        ).strip()


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

        price_diff = abs(self.__state.price - self.__state.price_aggregate)
        deviation = (price_diff / self.__state.price_aggregate) * 100

        # Pass if deviation is less than max distance
        if deviation <= self.__max_aggregate_distance:
            return True

        # Fail
        return False

    def error_message(self) -> str:
        price_diff = abs(self.__state.price - self.__state.price_aggregate)
        deviation = (price_diff / self.__state.price_aggregate) * 100

        return dedent(
            f"""
            {self.__state.publisher_name} price is too far from aggregate price.

            Symbol: {self.__state.symbol}
            Publisher price: {self.__state.price} ± {self.__state.confidence_interval}
            Aggregate price: {self.__state.price_aggregate} ± {self.__state.confidence_interval_aggregate}
            Deviation: {deviation}%
            """
        ).strip()


PUBLISHER_CHECKS = [
    PublisherWithinAggregateConfidenceCheck,
    PublisherConfidenceIntervalCheck,
    PublisherOfflineCheck,
    PublisherPriceCheck,
]
