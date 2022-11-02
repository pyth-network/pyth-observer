import datetime
import time
from dataclasses import dataclass
from typing import Any, Dict, TypedDict

import pytz
from loguru import logger
from pythclient.pythaccounts import PythPriceStatus
from pythclient.solana import SolanaPublicKey

from pyth_observer.calendar import HolidayCalendar

ConfigDict = Dict[str, Any]


class CrosschainPrice(TypedDict):
    price: float
    conf: float
    publish_time: int  # UNIX timestamp


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
    coingecko_price: float
    coingecko_update: float
    crosschain_price: Dict[str, Any]


class PriceFeedCheck:
    state: PriceFeedState

    def __init__(self, state: PriceFeedState, _config: ConfigDict = {}):
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

    def log_entry(self) -> str:
        result = "passed" if self.run() else "failed"

        return f"Check {result}: {self.__class__.__name__} for {self.state.symbol}"


class PriceFeedCoinGeckoCheck(PriceFeedCheck):
    """
    Price feed, if trading, must not be too far from Coingecko's price.
    """

    def __init__(self, state: PriceFeedState, config: ConfigDict):
        super().__init__(state)

        self.max_deviation: int = config["max_deviation"]  # Percentage
        self.max_staleness: int = config["max_staleness"]  # Seconds

    def run(self) -> bool:
        super().run()

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


class PriceFeedConfidenceIntervalCheck(PriceFeedCheck):
    """
    Price feed's confidence interval, if trading, must be greater than zero
    """

    def __init__(self, state: PriceFeedState, _config: ConfigDict):
        super().__init__(state)

    def run(self) -> bool:
        super().run()

        # Skip if not trading
        if self.state.status != PythPriceStatus.TRADING:
            return True

        # Pass if confidence interval is greater than zero
        if self.state.confidence_interval_aggregate > 0:
            return True

        # Fail
        return False


class PriceFeedCrossChainOnlineCheck(PriceFeedCheck):
    """
    Price feed, if trading, must have published a price at the price service no
    more than `max_staleness` seconds ago.
    """

    max_staleness: int  # Seconds

    def __init__(self, state: PriceFeedState, config: ConfigDict):
        super().__init__(state)

        self.max_staleness = config["max_staleness"]

    def run(self) -> bool:
        super().run()

        # Skip if no crosschain price
        if not self.state.crosschain_price:
            return True

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


class PriceFeedCrossChainDeviationCheck(PriceFeedCheck):
    """
    Price feed must not be too far away from its corresponding at the price service.
    """

    max_deviation: int  # Percentage
    max_staleness: int  # Seconds

    def __init__(self, state: PriceFeedState, config: ConfigDict):
        super().__init__(state)

        self.max_deviation = config["max_deviation"]
        self.max_staleness = config["max_staleness"]

    def run(self) -> bool:
        super().run()

        # Skip if no crosschain price
        if not self.state.crosschain_price:
            return True

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


class PriceFeedOnlineCheck(PriceFeedCheck):
    """
    Price feed must be online
    """

    max_slot_distance: int

    def __init__(self, state: PriceFeedState, config: ConfigDict):
        super().__init__(state)

        self.max_slot_distance = config["max_slot_distance"]

    def run(self) -> bool:
        super().run()

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
