import datetime
import time
from dataclasses import dataclass
from textwrap import dedent
from typing import Dict, Optional, Protocol, runtime_checkable

import arrow
import pytz
from pythclient.pythaccounts import PythPriceStatus
from pythclient.solana import SolanaPublicKey

from pyth_observer.calendar import HolidayCalendar
from pyth_observer.crosschain import CrosschainPrice


@dataclass
class PriceFeedState:
    symbol: str
    asset_type: str
    public_key: SolanaPublicKey
    status: PythPriceStatus
    latest_block_slot: int
    latest_trading_slot: int
    price_aggregate: float
    confidence_interval_aggregate: float
    coingecko_price: Optional[float]
    coingecko_update: Optional[int]
    crosschain_price: CrosschainPrice


PriceFeedCheckConfig = Dict[str, str | float | int | bool]


@runtime_checkable
class PriceFeedCheck(Protocol):
    def __init__(self, state: PriceFeedState, config: PriceFeedCheckConfig):
        ...

    def state(self) -> PriceFeedState:
        ...

    def run(self) -> bool:
        ...

    def error_message(self) -> str:
        ...


class PriceFeedOfflineCheck(PriceFeedCheck):
    def __init__(self, state: PriceFeedState, config: PriceFeedCheckConfig):
        self.__state = state
        self.__max_slot_distance: int = int(config["max_slot_distance"])
        self.__abandoned_slot_distance: int = int(config["abandoned_slot_distance"])

    def state(self) -> PriceFeedState:
        return self.__state

    def run(self) -> bool:
        is_market_open = HolidayCalendar().is_market_open(
            self.__state.asset_type,
            datetime.datetime.now(tz=pytz.timezone("America/New_York")),
        )

        # Skip if market is not open
        if not is_market_open:
            return True

        distance = abs(
            self.__state.latest_block_slot - self.__state.latest_trading_slot
        )

        # Pass if distance is less than max slot distance
        if distance < self.__max_slot_distance:
            return True

        # Pass if price has been stale for a long time
        if distance > self.__abandoned_slot_distance:
            return True

        # Fail
        return False

    def error_message(self) -> str:
        distance = self.__state.latest_block_slot - self.__state.latest_trading_slot
        return dedent(
            f"""
            {self.__state.symbol} is offline (either non-trading/stale).
            It is not updated for {distance} slots.

            Latest trading slot: {self.__state.latest_trading_slot}
            Block slot: {self.__state.latest_block_slot}
            """
        ).strip()


class PriceFeedCoinGeckoCheck(PriceFeedCheck):
    def __init__(self, state: PriceFeedState, config: PriceFeedCheckConfig):
        self.__state = state
        self.__max_deviation: int = int(config["max_deviation"])  # Percentage
        self.__max_staleness: int = int(config["max_staleness"])  # Seconds

    def state(self) -> PriceFeedState:
        return self.__state

    def run(self) -> bool:
        # Skip if no CoinGecko price
        if not self.__state.coingecko_price or not self.__state.coingecko_update:
            return True

        # Skip if stale CoinGecko price
        if self.__state.coingecko_update + self.__max_staleness < time.time():
            return True

        # Skip if not trading
        if self.__state.status != PythPriceStatus.TRADING:
            return True

        deviation = (
            abs(self.__state.price_aggregate - self.__state.coingecko_price)
            / self.__state.coingecko_price
        )

        # Pass if deviation is less than max deviation
        if deviation < self.__max_deviation:
            return True

        # Fail
        return False

    def error_message(self) -> str:
        return dedent(
            f"""
            {self.__state.symbol} is too far from Coingecko's price.

            Pyth price: {self.__state.price_aggregate}
            Coingecko price: {self.__state.coingecko_price}
            """
        ).strip()


class PriceFeedConfidenceIntervalCheck(PriceFeedCheck):
    def __init__(self, state: PriceFeedState, config: PriceFeedCheckConfig):
        self.__state = state
        self.__min_confidence_interval: int = int(config["min_confidence_interval"])

    def state(self) -> PriceFeedState:
        return self.__state

    def run(self) -> bool:
        # Skip if not trading
        if self.__state.status != PythPriceStatus.TRADING:
            return True

        # Pass if confidence interval is greater than zero
        if self.__state.confidence_interval_aggregate > self.__min_confidence_interval:
            return True

        # Fail
        return False

    def error_message(self) -> str:
        return dedent(
            f"""
            {self.__state.symbol} confidence interval is too low.

            Confidence interval: {self.__state.confidence_interval_aggregate}
            """
        ).strip()


class PriceFeedCrossChainOnlineCheck(PriceFeedCheck):
    def __init__(self, state: PriceFeedState, config: PriceFeedCheckConfig):
        self.__state = state
        self.__max_staleness: int = int(config["max_staleness"])

    def state(self) -> PriceFeedState:
        return self.__state

    def run(self) -> bool:
        # Skip if not trading
        if self.__state.status != PythPriceStatus.TRADING:
            return True

        # Skip if publish time is zero
        if not self.__state.crosschain_price["publish_time"]:
            return True

        is_market_open = HolidayCalendar().is_market_open(
            self.__state.asset_type,
            datetime.datetime.now(tz=pytz.timezone("America/New_York")),
        )

        # Skip if not trading hours (for equities)
        if not is_market_open:
            return True

        staleness = int(time.time()) - self.__state.crosschain_price["publish_time"]

        # Pass if current staleness is less than `max_staleness`
        if staleness < self.__max_staleness:
            return True

        # Fail
        return False

    def error_message(self) -> str:
        publish_time = arrow.get(self.__state.crosschain_price["publish_time"])

        return dedent(
            f"""
            {self.__state.symbol} isn't online at the price service.

            Last publish time: {publish_time.format('YYYY-MM-DD HH:mm:ss ZZ')}
            """
        ).strip()


class PriceFeedCrossChainDeviationCheck(PriceFeedCheck):
    def __init__(self, state: PriceFeedState, config: PriceFeedCheckConfig):
        self.__state = state
        self.__max_deviation: int = int(config["max_deviation"])
        self.__max_staleness: int = int(config["max_staleness"])

    def state(self) -> PriceFeedState:
        return self.__state

    def run(self) -> bool:
        # Skip if not trading
        if self.__state.status != PythPriceStatus.TRADING:
            return True

        is_market_open = HolidayCalendar().is_market_open(
            self.__state.asset_type,
            datetime.datetime.now(tz=pytz.timezone("America/New_York")),
        )

        # Skip if not trading hours (for equities)
        if not is_market_open:
            return True

        staleness = int(time.time()) - self.__state.crosschain_price["publish_time"]

        # Skip if price is stale
        if staleness > self.__max_staleness:
            return True

        deviation = (
            abs(self.__state.crosschain_price["price"] - self.__state.price_aggregate)
            / self.__state.price_aggregate
        ) * 100

        # Pass if price isn't higher than maxium deviation
        if deviation < self.__max_deviation:
            return True

        # Fail
        return False

    def error_message(self) -> str:
        return dedent(
            f"""
            {self.__state.symbol} is too far at the price service.

            Price: {self.__state.price_aggregate}
            Price at price service: {self.__state.crosschain_price['price']}
            """
        ).strip()


PRICE_FEED_CHECKS = [
    PriceFeedCoinGeckoCheck,
    PriceFeedCrossChainDeviationCheck,
    PriceFeedCrossChainOnlineCheck,
    PriceFeedOfflineCheck,
]
