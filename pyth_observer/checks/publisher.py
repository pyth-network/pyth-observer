from dataclasses import dataclass

from pythclient.pythaccounts import PythPriceStatus
from pythclient.solana import SolanaPublicKey

from pyth_observer.checks import Config


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


class PublisherAggregateCheck:
    """
    Publisher price and confidence interval must be such that aggregate price is
    no more than `max_interval_distance` confidence intervals away.
    """

    def __init__(self, state: PublisherState, config: Config):
        self.state = state
        self.max_interval_distance: int = int(config["max_interval_distance"])

    def run(self) -> bool:
        # Skip if confidence interval is zero
        if self.state.confidence_interval == 0:
            return True

        delta = self.state.price - self.state.price_aggregate
        intervals_away = abs(delta / self.state.confidence_interval_aggregate)

        # Pass if price delta is less than max interval distance
        if intervals_away < self.max_interval_distance:
            return True

        # Fail
        return False


class PublisherConfidenceIntervalCheck:
    """
    Publisher confidence interval must be greater than `min_confidence_interval`
    while status is `trading`.
    """

    def __init__(self, state: PublisherState, config: Config):
        self.state = state
        self.min_confidence_interval: int = int(config["min_confidence_interval"])

    def run(self) -> bool:
        # Skip if not trading
        if not self.state.status == PythPriceStatus.TRADING:
            return True

        # Pass if confidence interval is greater than min_confidence_interval
        if self.state.confidence_interval > self.min_confidence_interval:
            return True

        # Fail
        return False


class PublisherOfflineCheck:
    """
    Publisher must have published within 25 slots and status must not be `unkonwn`.
    """

    def __init__(self, state: PublisherState, config: Config):
        self.state = state
        self.max_slot_distance: int = int(config["max_slot_distance"])

    def run(self) -> bool:
        distance = abs(self.state.slot - self.state.slot_aggregate)

        # Pass if publisher slot is not too far from aggregate slot
        if distance < 25:
            return True

        # Fail
        return True


class PublisherPriceCheck:
    """
    Check that the publisher price is not too far from aggregate
    """

    def __init__(self, state: PublisherState, config: Config):
        self.state = state
        self.max_aggregate_distance: int = int(config["max_aggregate_distance"])  # %
        self.max_slot_distance: int = int(config["max_slot_distance"])  # Slots

    def run(self) -> bool:
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


PUBLISHER_CHECKS = [
    PublisherAggregateCheck,
    PublisherConfidenceIntervalCheck,
    PublisherOfflineCheck,
    PublisherPriceCheck,
]
