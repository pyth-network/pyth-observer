import datetime
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, List, cast

import pytz
from loguru import logger
from pyth_observer.calendar import HolidayCalendar
from pyth_observer.crosschain import CrosschainPrice
from pyth_observer.checks import Config
from pythclient.pythaccounts import PythPriceStatus
from pythclient.solana import SolanaPublicKey


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
    coingecko_price: Optional[float]
    coingecko_update: Optional[int]
    crosschain_price: CrosschainPrice


class PriceFeedCoinGeckoCheck:
    """
    Price feed, if trading, must not be too far from Coingecko's price.
    """

    def __init__(self, state: PriceFeedState, config: Config):
        self.state = state
        self.max_deviation: int = int(config["max_deviation"])  # Percentage
        self.max_staleness: int = int(config["max_staleness"])  # Seconds

    def run(self) -> bool:
        # Skip if no CoinGecko price
        if not self.state.coingecko_price or not self.state.coingecko_update:
            return True

        # Skip if stale CoinGecko price
        if self.state.coingecko_update + self.max_staleness < time.time():
            return True

        # Skip if not trading
        if self.state.status != PythPriceStatus.TRADING:
            return True

        deviation = (
            abs(self.state.price_aggregate - self.state.coingecko_price)
            / self.state.coingecko_price
        )

        # Pass if deviation is less than max deviation
        if deviation < self.max_deviation:
            return True

        # Fail
        return False


class PriceFeedConfidenceIntervalCheck:
    """
    Price feed's confidence interval, if trading, must be greater than zero
    """

    def __init__(self, state: PriceFeedState, config: Config):
        self.state = state
        self.min_confidence_interval: int = int(config["min_confidence_interval"])

    def run(self) -> bool:
        # Skip if not trading
        if self.state.status != PythPriceStatus.TRADING:
            return True

        # Pass if confidence interval is greater than zero
        if self.state.confidence_interval_aggregate > self.min_confidence_interval:
            return True

        # Fail
        return False


class PriceFeedCrossChainOnlineCheck:
    """
    Price feed, if trading, must have published a price at the price service no
    more than `max_staleness` seconds ago.
    """

    def __init__(self, state: PriceFeedState, config: Config):
        self.state = state
        self.max_staleness: int = int(config["max_staleness"])

    def run(self) -> bool:
        # Skip if publish time is zero
        if not self.state.crosschain_price["publish_time"]:
            return True

        is_market_open = HolidayCalendar().is_market_open(
            self.state.asset_type,
            datetime.datetime.now(tz=pytz.timezone("America/New_York")),
        )

        # Skip if not trading hours (for equities)
        if not is_market_open:
            return True

        staleness = int(time.time()) - self.state.crosschain_price["publish_time"]

        # Pass if current staleness is less than `max_staleness`
        if staleness < self.max_staleness:
            return True

        # Fail
        return False


class PriceFeedCrossChainDeviationCheck:
    """
    Price feed must not be too far away from its corresponding at the price service.
    """

    def __init__(self, state: PriceFeedState, config: Config):
        self.state = state
        self.max_deviation: int = int(config["max_deviation"])
        self.max_staleness: int = int(config["max_staleness"])

    def run(self) -> bool:
        # Skip if not trading
        if self.state.status != PythPriceStatus.TRADING:
            return True

        is_market_open = HolidayCalendar().is_market_open(
            self.state.asset_type,
            datetime.datetime.now(tz=pytz.timezone("America/New_York")),
        )

        # Skip if not trading hours (for equities)
        if not is_market_open:
            return True

        staleness = int(time.time()) - self.state.crosschain_price["publish_time"]

        # Skip if price is stale
        if staleness > self.max_staleness:
            return True

        deviation = (
            abs(self.state.crosschain_price["price"] - self.state.price_aggregate)
            / self.state.price_aggregate
        ) * 100

        # Pass if price isn't higher than maxium deviation
        if deviation < self.max_deviation:
            return True

        # Fail
        return False


class PriceFeedOnlineCheck:
    """
    Price feed must be online
    """

    def __init__(self, state: PriceFeedState, config: Config):
        self.state = state
        self.max_slot_distance: int = int(config["max_slot_distance"])

    def run(self) -> bool:
        is_market_open = HolidayCalendar().is_market_open(
            self.state.asset_type,
            datetime.datetime.now(tz=pytz.timezone("America/New_York")),
        )

        # Skip if market is not open
        if not is_market_open:
            return True

        # Skip if not trading
        if self.state.status != PythPriceStatus.TRADING:
            return True

        distance = abs(self.state.slot - self.state.slot_aggregate)

        # Pass if distance is less than max slot distance
        if distance < self.max_slot_distance:
            return True

        # Fail
        return False


PRICE_FEED_CHECKS = [
    PriceFeedCoinGeckoCheck,
    PriceFeedCrossChainDeviationCheck,
    PriceFeedCrossChainOnlineCheck,
    PriceFeedOnlineCheck,
]
