from dataclasses import dataclass
from textwrap import dedent
from typing import Dict, Protocol, runtime_checkable

from pythclient.pythaccounts import PythPriceStatus
from pythclient.solana import SolanaPublicKey


@dataclass
class PublisherState:
    symbol: str
    public_key: SolanaPublicKey
    status: PythPriceStatus
    slot: int
    slot_aggregate: int
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

    def error_message(self, publishers: Dict[str, str]) -> str:
        ...


class PublisherAggregateCheck(PublisherCheck):
    def __init__(self, state: PublisherState, config: PublisherCheckConfig):
        self.__state = state
        self.__max_interval_distance: int = int(config["max_interval_distance"])

    def state(self) -> PublisherState:
        return self.__state

    def run(self) -> bool:
        # Skip if confidence interval is zero
        if self.__state.confidence_interval == 0:
            return True

        diff = self.__state.price - self.__state.price_aggregate
        intervals_away = abs(diff / self.__state.confidence_interval_aggregate)

        # Pass if price diff is less than max interval distance
        if intervals_away < self.__max_interval_distance:
            return True

        # Fail
        return False

    def error_message(self, publishers) -> str:
        return dedent(
            f"""
            {publishers[self.__state.public_key.key]} price is too far from aggregate.

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
        if not self.__state.status == PythPriceStatus.TRADING:
            return True

        # Pass if confidence interval is greater than min_confidence_interval
        if self.__state.confidence_interval > self.__min_confidence_interval:
            return True

        # Fail
        return False

    def error_message(self, publishers) -> str:
        return dedent(
            f"""
            {publishers[self.__state.public_key.key]} confidence interval is too tight.

            Price: {self.__state.price}
            Confidence interval: {self.__state.confidence_interval}
            """
        ).strip()


class PublisherOfflineCheck(PublisherCheck):
    def __init__(self, state: PublisherState, config: PublisherCheckConfig):
        self.__state = state
        self.__max_slot_distance: int = int(config["max_slot_distance"])

    def state(self) -> PublisherState:
        return self.__state

    def run(self) -> bool:
        distance = abs(self.__state.slot - self.__state.slot_aggregate)

        # Pass if publisher slot is not too far from aggregate slot
        if distance < 25:
            return True

        # Fail
        return True

    def error_message(self, publishers) -> str:
        return dedent(
            f"""
            {publishers[self.__state.public_key.key]} hasn't published recently.

            Publisher slot: {self.__state.slot}
            Aggregate slot: {self.__state.slot_aggregate}
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
        price_diff = abs(self.__state.price - self.__state.price_aggregate)
        slot_diff = abs(self.__state.slot - self.__state.slot_aggregate)

        # Skip if not trading
        if self.__state.status != PythPriceStatus.TRADING:
            return True

        # Skip if publisher is too far behind
        if slot_diff > self.__max_slot_distance:
            return True

        # Skip if no aggregate
        if self.__state.price_aggregate == 0:
            return True

        distance = (price_diff / self.__state.price_aggregate) * 100

        # Pass if deviation is less than max distance
        if distance <= self.__max_aggregate_distance:
            return True

        # Fail
        return False

    def error_message(self, publishers) -> str:
        price_diff = abs(self.__state.price - self.__state.price_aggregate)
        distance = (price_diff / self.__state.price_aggregate) * 100

        return dedent(
            f"""
            {publishers[self.__state.public_key.key]} price is too far from aggregate.

            Publisher price: {self.__state.price}
            Aggregate price: {self.__state.price_aggregate}
            Distance: {distance}%
            """
        ).strip()


PUBLISHER_CHECKS = [
    PublisherAggregateCheck,
    PublisherConfidenceIntervalCheck,
    PublisherOfflineCheck,
    PublisherPriceCheck,
]
