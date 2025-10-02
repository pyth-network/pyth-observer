import random
import time
from unittest.mock import patch

import pytest
from pythclient.market_schedule import MarketSchedule
from pythclient.pythaccounts import PythPriceStatus
from pythclient.solana import SolanaPublicKey

from pyth_observer.check.publisher import (
    PUBLISHER_CACHE,
    PriceUpdate,
    PublisherPriceCheck,
    PublisherStalledCheck,
    PublisherState,
)


def make_publisher_state(
    pub_slot: int,
    pub_price: float,
    pub_conf: float,
    agg_slot: int,
    agg_price: float,
    agg_conf: float,
    asset_type: str = "Crypto",
    symbol: str = "Crypto.BTC/USD",
) -> PublisherState:
    return PublisherState(
        publisher_name="publisher",
        symbol=symbol,
        asset_type=asset_type,
        schedule=MarketSchedule("America/New_York;O,O,O,O,O,O,O;"),
        public_key=SolanaPublicKey("2hgu6Umyokvo8FfSDdMa9nDKhcdv9Q4VvGNhRCeSWeD3"),
        status=PythPriceStatus.TRADING,
        aggregate_status=PythPriceStatus.TRADING,
        slot=pub_slot,
        aggregate_slot=agg_slot,
        latest_block_slot=agg_slot,
        price=pub_price,
        price_aggregate=agg_price,
        confidence_interval=pub_conf,
        confidence_interval_aggregate=agg_conf,
    )


def test_publisher_price_check():
    def check_is_ok(
        state: PublisherState, max_aggregate_distance: int, max_slot_distance: int
    ) -> bool:
        return PublisherPriceCheck(
            state,
            {
                "max_aggregate_distance": max_aggregate_distance,
                "max_slot_distance": max_slot_distance,
            },
        ).run()

    # check triggering threshold for price difference
    state1 = make_publisher_state(1, 100.0, 2.0, 1, 110.0, 1.0)
    assert check_is_ok(state1, 10, 25)
    assert not check_is_ok(state1, 6, 25)


class TestPublisherStalledCheck:
    @pytest.fixture(autouse=True)
    def setup(self):
        """Clear cache and time simulation before each test"""
        PUBLISHER_CACHE.clear()
        self.current_time = int(time.time())
        yield
        PUBLISHER_CACHE.clear()

    def simulate_time_pass(self, seconds: float) -> float:
        self.current_time += seconds
        return self.current_time

    def setup_check(
        self,
        state: PublisherState,
        stall_time_limit: int = 5,
        abandoned_time_limit: int = 25,
        max_slot_distance: int = 25,
        noise_threshold: float = 1e-4,
        min_noise_samples: int = 10,
    ) -> PublisherStalledCheck:
        check = PublisherStalledCheck(
            state,
            {
                "stall_time_limit": stall_time_limit,
                "abandoned_time_limit": abandoned_time_limit,
                "max_slot_distance": max_slot_distance,
                "noise_threshold": noise_threshold,
                "min_noise_samples": min_noise_samples,
            },
        )

        # Seed the cache with the publisher state
        PUBLISHER_CACHE[(state.publisher_name, state.symbol)].append(
            PriceUpdate(int(self.current_time), state.price)
        )

        return check

    def run_check(self, check: PublisherStalledCheck, seconds: float, expected: bool):
        with patch("time.time", new=lambda: self.simulate_time_pass(seconds)):
            assert check.run() == expected

    def test_exact_stall_fails_check(self):
        state_a = make_publisher_state(1, 100.0, 2.0, 1, 100.0, 1.0)
        check_a = self.setup_check(state_a, stall_time_limit=5)
        self.run_check(check_a, 5, True)  # Should pass as it hits the limit exactly

        PUBLISHER_CACHE.clear()
        state_b = make_publisher_state(1, 100.0, 2.0, 1, 100.0, 1.0)
        check_b = self.setup_check(state_b, stall_time_limit=5)
        self.run_check(check_b, 6, False)  # Should fail as it exceeds the limit

        PUBLISHER_CACHE.clear()
        state_c = make_publisher_state(1, 100.0, 2.0, 1, 100.0, 1.0)
        check_c = self.setup_check(state_c, stall_time_limit=5)
        self.run_check(check_c, 2, True)  # Initial check should pass
        state_c.price = 105.0  # Change the price
        self.run_check(check_c, 3, True)  # Should pass as price changes
        state_c.price = 100.0  # Change back to original price
        # Simulate a stall -- send the same price repeatedly.
        self.run_check(check_c, 2, True)
        state_c.price = 100.0
        self.run_check(check_c, 2, True)
        state_c.price = 100.0
        self.run_check(check_c, 2, True)
        state_c.price = 100.0
        self.run_check(
            check_c, 2, False
        )  # Should fail since we breached the stall time limit

        PUBLISHER_CACHE.clear()
        state_c = make_publisher_state(1, 100.0, 2.0, 1, 100.0, 1.0)
        check_c = self.setup_check(state_c, stall_time_limit=5)
        self.run_check(check_c, 2, True)  # Initial check should pass
        state_c.price = 105.0  # Change the price
        self.run_check(check_c, 3, True)  # Should pass as price changes
        state_c.price = 100.0  # Change back to original price
        self.run_check(check_c, 4, True)  # Should pass as price changes
        self.run_check(
            check_c, 8, False
        )  # Should fail as price stalls for too long after last change

        # Adding a check for when the publisher is offline
        PUBLISHER_CACHE.clear()
        state_d = make_publisher_state(1, 100.0, 2.0, 1, 100.0, 1.0)
        state_d.latest_block_slot = 25
        state_d.slot = 0
        check_d = self.setup_check(state_d, 5, 25, 25)
        self.run_check(check_d, 10, True)  # Should pass as the publisher is offline

    def test_artificially_noisy_stall_fails_check(self):
        """Test detection of stalls with artificial noise"""
        state = make_publisher_state(1, 100.0, 2.0, 1, 100.0, 1.0)
        check = self.setup_check(state, stall_time_limit=50, min_noise_samples=10)

        # Add prices with small artificial noise, exceeding stall_time_limit and min_noise_updates
        for seconds in range(0, 55, 5):
            noise = state.price * (
                1e-6 * (random.random() - 0.5)
            )  # Random noise within ±1e-4%
            state.price = 100.0 + noise
            # Should fail after 50 seconds and 10 samples
            self.run_check(check, 30, seconds < 55)

    def test_normal_price_movement_passes_check(self):
        """Test that normal price movements don't trigger stall detection"""
        state = make_publisher_state(1, 100.0, 2.0, 1, 100.0, 1.0)
        check = self.setup_check(state, stall_time_limit=50, min_noise_samples=10)

        # Add prices with significant variations to simulate real
        # price movements, exceeding stall_time_limit and min_noise_updates
        for seconds in range(0, 55, 5):
            state.price = 100.0 + (seconds * 0.001)  # 0.1% change each time
            self.run_check(check, 30, True)  # Should always pass

    def test_redemption_rate_passes_check(self):
        """Test that redemption rates are always allowed to be static"""
        state = make_publisher_state(
            1,
            100.0,
            2.0,
            1,
            100.0,
            1.0,
            asset_type="Crypto Redemption Rate",
            symbol="Crypto.FUSDC/USDC.RR",
        )
        check = self.setup_check(state, int(self.current_time))

        # Should pass even after long period without changes
        self.run_check(check, 3600, True)  # 1 hour
