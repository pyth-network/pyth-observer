import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Protocol, runtime_checkable
from zoneinfo import ZoneInfo

from pythclient.market_schedule import MarketSchedule
from pythclient.pythaccounts import PythPriceStatus
from pythclient.solana import SolanaPublicKey


@dataclass
class PriceFeedState:
    symbol: str
    asset_type: str
    schedule: MarketSchedule
    public_key: SolanaPublicKey
    status: PythPriceStatus
    latest_block_slot: int
    latest_trading_slot: int
    price_aggregate: float
    confidence_interval_aggregate: float
    coingecko_price: Optional[float]
    coingecko_update: Optional[int]


PriceFeedCheckConfig = Dict[str, str | float | int | bool]


@runtime_checkable
class PriceFeedCheck(Protocol):
    def __init__(self, state: PriceFeedState, config: PriceFeedCheckConfig) -> None:
        ...

    def state(self) -> PriceFeedState:
        ...

    def run(self) -> bool:
        ...

    def error_message(self) -> Dict[str, Any]:
        ...


class PriceFeedOfflineCheck(PriceFeedCheck):
    def __init__(self, state: PriceFeedState, config: PriceFeedCheckConfig) -> None:
        self.__state = state
        self.__max_slot_distance: int = int(config["max_slot_distance"])
        self.__abandoned_slot_distance: int = int(config["abandoned_slot_distance"])

    def state(self) -> PriceFeedState:
        return self.__state

    def run(self) -> bool:
        market_open = self.__state.schedule.is_market_open(
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

    def error_message(self) -> Dict[str, Any]:
        distance = self.__state.latest_block_slot - self.__state.latest_trading_slot
        return {
            "msg": f"{self.__state.symbol} is offline (either non-trading/stale). Last update {distance} slots ago.",
            "type": "PriceFeedOfflineCheck",
            "symbol": self.__state.symbol,
            "latest_trading_slot": self.__state.latest_trading_slot,
            "block_slot": self.__state.latest_block_slot,
        }


class PriceFeedCoinGeckoCheck(PriceFeedCheck):
    def __init__(self, state: PriceFeedState, config: PriceFeedCheckConfig) -> None:
        self.__state = state
        self.__max_deviation: float = float(config["max_deviation"])  # Percentage
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

        # Skip if CoinGecko price is zero
        if self.__state.coingecko_price == 0:
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

    def error_message(self) -> Dict[str, Any]:
        return {
            "msg": f"{self.__state.symbol} is too far from Coingecko's price.",
            "type": "PriceFeedCoinGeckoCheck",
            "symbol": self.__state.symbol,
            "pyth_price": self.__state.price_aggregate,
            "coingecko_price": self.__state.coingecko_price,
        }


class PriceFeedConfidenceIntervalCheck(PriceFeedCheck):
    def __init__(self, state: PriceFeedState, config: PriceFeedCheckConfig) -> None:
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

    def error_message(self) -> Dict[str, Any]:
        return {
            "msg": f"{self.__state.symbol} confidence interval is too low.",
            "type": "PriceFeedConfidenceIntervalCheck",
            "symbol": self.__state.symbol,
            "confidence_interval": self.__state.confidence_interval_aggregate,
        }


PRICE_FEED_CHECKS = [
    PriceFeedCoinGeckoCheck,
    PriceFeedConfidenceIntervalCheck,
    PriceFeedOfflineCheck,
]
