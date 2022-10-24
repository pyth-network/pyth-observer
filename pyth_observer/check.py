import datetime
from dataclasses import dataclass
from typing import Any, Dict
from loguru import logger

import pytz
from pythclient.pythaccounts import PythPriceStatus
from pythclient.solana import SolanaPublicKey

from pyth_observer.calendar import HolidayCalendar

ConfigDict = Dict[str, Any]


@dataclass
class PriceFeedState:
    symbol: str
    asset_type: str
    public_key: SolanaPublicKey
    status: PythPriceStatus
    slot: int
    slot_aggregate: int
    price_aggregate: float
    confidence_interval_aggregate: float


class PriceFeedCheck:
    state: PriceFeedState

    def __init__(self, state: PriceFeedState, config: ConfigDict = {}):
        self.state = state

    def run(self) -> bool:
        """
        Run the check and return whether in passed
        """
        raise RuntimeError("Not implemented")

    def metadata(self) -> dict:
        """
        Generate check metadata for alerting
        """
        raise RuntimeError("Not implemented")

    def log_entry(self) -> str:
        result = "passed" if self.run() else "failed"

        return f"Check {result}: {self.__class__.__name__} for {self.state.symbol}"


class PriceFeedCoinGeckoCheck(PriceFeedCheck):
    """
    Price feed must not be too far away from CoinGecko.
    """

    # TODO

    def __init__(self, state: PriceFeedState, _config: ConfigDict):
        super().__init__(state)

    def run(self) -> bool:
        return True


class PriceFeedCrossChainOfflineCheck(PriceFeedCheck):
    """
    Price feed must be available at the price service.
    """

    # TODO

    def __init__(self, state: PriceFeedState, _config: ConfigDict):
        super().__init__(state)

    def run(self) -> bool:
        return True


class PriceFeedCrossChainDeviationCheck(PriceFeedCheck):
    """
    Price feed must not be too far away from the equivalent at the price service.
    """

    # TODO

    def __init__(self, state: PriceFeedState, _config: ConfigDict):
        super().__init__(state)

    def run(self) -> bool:
        return True


class PriceFeedOfflineCheck(PriceFeedCheck):
    """
    Price feed must have been updated within `max_slot_distance` slot and status must not be `unknown`.
    """

    max_slot_distance: int

    def __init__(self, state: PriceFeedState, config: ConfigDict):
        super().__init__(state)

        self.max_slot_distance = config["max_slot_distance"]

    def run(self) -> bool:
        calendar = HolidayCalendar()
        delta = abs(self.state.slot - self.state.slot_aggregate)
        trading = self.state.status == PythPriceStatus.TRADING
        market_open = calendar.is_market_open(
            self.state.asset_type,
            datetime.datetime.now(tz=pytz.timezone("America/New_York")),
        )

        if delta > 25 or not trading:
            if market_open:
                return False

        return True


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
        Run the check and return whether in passed
        """
        raise RuntimeError("Not implemented")

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
        distance = abs(self.state.slot - self.state.slot_aggregate)

        if distance > 25:
            return False

        return True


class PublisherPriceCheck(PublisherCheck):
    """
    Publisher price must be within `max_aggregate_distance`% of aggregate price.
    """

    max_aggregate_distance: int
    max_slot_distance: int

    def __init__(self, state: PublisherState, config: ConfigDict):
        super().__init__(state)

        self.max_aggregate_distance = config["max_aggregate_distance"]
        self.max_slot_distance = config["max_slot_distance"]

    def run(self) -> bool:
        logger.debug(
            f"{self.__class__.__name__} for {self.state.symbol} on {self.state.public_key}"
        )
        logger.debug(self.state)

        price_delta = abs(self.state.price - self.state.price_aggregate)
        slot_delta = abs(self.state.slot - self.state.slot_aggregate)

        # Ignore check if publisher isn't trading
        if self.state.status != PythPriceStatus.TRADING:
            return True

        # Ignore check if publisher is too far behind
        if slot_delta > self.max_slot_distance:
            return True

        if self.state.price_aggregate == 0:
            return True

        deviation = (price_delta / self.state.price_aggregate) * 100

        if deviation > self.max_aggregate_distance:
            return False

        return True
