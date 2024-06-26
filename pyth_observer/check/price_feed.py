import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Protocol, runtime_checkable
from zoneinfo import ZoneInfo

import arrow
from pythclient.calendar import is_market_open
from pythclient.pythaccounts import PythPriceStatus
from pythclient.solana import SolanaPublicKey

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
    crosschain_price: Optional[CrosschainPrice]


PriceFeedCheckConfig = Dict[str, str | float | int | bool]


@runtime_checkable
class PriceFeedCheck(Protocol):
    def __init__(self, state: PriceFeedState, config: PriceFeedCheckConfig):
        ...

    def state(self) -> PriceFeedState:
        ...

    def run(self) -> bool:
        ...

    def error_message(self) -> dict:
        ...


class PriceFeedOfflineCheck(PriceFeedCheck):
    def __init__(self, state: PriceFeedState, config: PriceFeedCheckConfig):
        self.__state = state
        self.__max_slot_distance: int = int(config["max_slot_distance"])
        self.__abandoned_slot_distance: int = int(config["abandoned_slot_distance"])

    def state(self) -> PriceFeedState:
        return self.__state

    def run(self) -> bool:
        market_open = is_market_open(
            self.__state.asset_type.lower(),
            datetime.now(ZoneInfo("America/New_York")),
        )

        # Skip if market is not open
        if not market_open:
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

    def error_message(self) -> dict:
        distance = self.__state.latest_block_slot - self.__state.latest_trading_slot
        return {
            "msg": f"{self.__state.symbol} is offline (either non-trading/stale). Last update {distance} slots ago.",
            "type": "PriceFeedOfflineCheck",
            "symbol": self.__state.symbol,
            "latest_trading_slot": self.__state.latest_trading_slot,
            "block_slot": self.__state.latest_block_slot,
        }


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

    def error_message(self) -> dict:
        return {
            "msg": f"{self.__state.symbol} is too far from Coingecko's price.",
            "type": "PriceFeedCoinGeckoCheck",
            "symbol": self.__state.symbol,
            "pyth_price": self.__state.price_aggregate,
            "coingecko_price": self.__state.coingecko_price,
        }


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

    def error_message(self) -> dict:
        return {
            "msg": f"{self.__state.symbol} confidence interval is too low.",
            "type": "PriceFeedConfidenceIntervalCheck",
            "symbol": self.__state.symbol,
            "confidence_interval": self.__state.confidence_interval_aggregate,
        }


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

        market_open = is_market_open(
            self.__state.asset_type.lower(),
            datetime.now(ZoneInfo("America/New_York")),
        )

        # Skip if not trading hours (for equities)
        if not market_open:
            return True

        # Price should exist, it fails otherwise
        if not self.__state.crosschain_price:
            return False

        # Skip if publish time is zero
        if not self.__state.crosschain_price["publish_time"]:
            return True

        staleness = (
            self.__state.crosschain_price["snapshot_time"]
            - self.__state.crosschain_price["publish_time"]
        )

        # Pass if current staleness is less than `max_staleness`
        if staleness < self.__max_staleness:
            return True

        # Fail
        return False

    def error_message(self) -> dict:
        if self.__state.crosschain_price:
            publish_time = arrow.get(self.__state.crosschain_price["publish_time"])
        else:
            publish_time = arrow.get(0)

        return {
            "msg": f"{self.__state.symbol} isn't online at the price service.",
            "type": "PriceFeedCrossChainOnlineCheck",
            "symbol": self.__state.symbol,
            "last_publish_time": publish_time.format("YYYY-MM-DD HH:mm:ss ZZ"),
        }


class PriceFeedCrossChainDeviationCheck(PriceFeedCheck):
    def __init__(self, state: PriceFeedState, config: PriceFeedCheckConfig):
        self.__state = state
        self.__max_deviation: int = int(config["max_deviation"])
        self.__max_staleness: int = int(config["max_staleness"])

    def state(self) -> PriceFeedState:
        return self.__state

    def run(self) -> bool:
        # Skip if does not exist
        if not self.__state.crosschain_price:
            return True

        # Skip if not trading
        if self.__state.status != PythPriceStatus.TRADING:
            return True

        market_open = is_market_open(
            self.__state.asset_type.lower(),
            datetime.now(ZoneInfo("America/New_York")),
        )

        # Skip if not trading hours (for equities)
        if not market_open:
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

    def error_message(self) -> dict:
        # It can never happen because of the check logic but linter could not understand it.
        price = (
            self.__state.crosschain_price["price"]
            if self.__state.crosschain_price
            else None
        )
        return {
            "msg": f"{self.__state.symbol} is too far at the price service.",
            "type": "PriceFeedCrossChainDeviationCheck",
            "symbol": self.__state.symbol,
            "price": self.__state.price_aggregate,
            "price_at_price_service": price,
        }


PRICE_FEED_CHECKS = [
    PriceFeedCoinGeckoCheck,
    PriceFeedCrossChainDeviationCheck,
    PriceFeedCrossChainOnlineCheck,
    PriceFeedOfflineCheck,
]
