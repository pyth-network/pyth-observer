from dataclasses import dataclass
from typing import Any, Dict

from loguru import logger
from pythclient.pythaccounts import PythPriceStatus
from pythclient.solana import SolanaPublicKey

ConfigDict = Dict[str, Any]


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


class PublisherCheck:
    state: PublisherState

    def __init__(self, state: PublisherState, _config: ConfigDict = {}):
        self.state = state

    def run(self) -> bool:
        """
        Run the check and return whether it passed
        """
        return True

    def metadata(self) -> dict:
        """
        Generate check metadata for alerting
        """
        raise RuntimeError("Not implemented")

    def log_entry(self, publishers: Dict[str, str]) -> str:
        result = "passed" if self.run() else "failed"
        publisher = publishers[str(self.state.public_key)]

        return f"Check {result}: {self.__class__.__name__} for {self.state.symbol} ({publisher}/{self.state.public_key.key[0:7]})"


class PublisherAggregateCheck(PublisherCheck):
    """
    Publisher price and confidence interval must be such that aggregate price is
    no more than `max_interval_distance` confidence intervals away.
    """

    max_interval_distance: int

    def __init__(self, state: PublisherState, config: ConfigDict):
        super().__init__(state)

        self.max_interval_distance = config["max_interval_distance"]

    def run(self) -> bool:
        super().run()

        delta = self.state.price - self.state.price_aggregate

        if self.state.confidence_interval != 0:
            intervals_away = abs(delta / self.state.confidence_interval_aggregate)

            if intervals_away > self.max_interval_distance:
                return False

        return True


class PublisherConfidenceIntervalCheck(PublisherCheck):
    """
    Publisher confidence interval must be greater than `min_confidence_interval`
    while status is `trading`.
    """

    min_confidence_interval: int

    def __init__(self, state: PublisherState, config: ConfigDict):
        super().__init__(state)

        self.min_confidence_interval = config["min_confidence_interval"]

    def run(self) -> bool:
        super().run()

        is_positive = self.state.confidence_interval > self.min_confidence_interval
        is_trading = self.state.status == PythPriceStatus.TRADING

        if is_trading and not is_positive:
            return False

        return True


class PublisherOfflineCheck(PublisherCheck):
    """
    Publisher must have published within 25 slots and status must not be `unkonwn`.
    """

    max_slot_distance: int

    def __init__(self, state: PublisherState, config: ConfigDict):
        super().__init__(state)

        self.max_slot_distance = config["max_slot_distance"]

    def run(self) -> bool:
        super().run()

        distance = abs(self.state.slot - self.state.slot_aggregate)

        if distance > 25:
            return False

        return True


class PublisherPriceCheck(PublisherCheck):
    """
    Check that the publisher price is not too far from aggregate
    """

    def __init__(self, state: PublisherState, config: ConfigDict):
        super().__init__(state)

        self.max_aggregate_distance: int = config["max_aggregate_distance"]  # %
        self.max_slot_distance: int = config["max_slot_distance"]  # Slots

    def run(self) -> bool:
        super().run()

        price_delta = abs(self.state.price - self.state.price_aggregate)
        slot_delta = abs(self.state.slot - self.state.slot_aggregate)

        # Skip if not trading
        if self.state.status != PythPriceStatus.TRADING:
            return True

        # Skip if publisher is too far behind
        if slot_delta > self.max_slot_distance:
            return True

        # Skip if no aggregate
        if self.state.price_aggregate == 0:
            return True

        distance = (price_delta / self.state.price_aggregate) * 100

        # Pass if deviation is less than max distance
        if distance <= self.max_aggregate_distance:
            return True

        # Fail
        return False
