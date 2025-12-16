import random
import time
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from pythclient.market_schedule import MarketSchedule
from pythclient.pythaccounts import PythPriceStatus
from pythclient.solana import SolanaPublicKey

from pyth_observer.check.publisher import (
    PUBLISHER_CACHE,
    PriceUpdate,
    PublisherOfflineCheck,
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
        state: PublisherState, max_aggregate_distance: float, max_slot_distance: int
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


class TestPublisherOfflineCheck:
    """Test suite for PublisherOfflineCheck covering various scenarios."""

    def make_state(
        self,
        publisher_slot: int,
        latest_block_slot: int,
        schedule: MarketSchedule | None = None,
        publisher_name: str = "test_publisher",
        symbol: str = "Crypto.BTC/USD",
    ) -> PublisherState:
        """Helper to create PublisherState for testing."""
        if schedule is None:
            schedule = MarketSchedule("America/New_York;O,O,O,O,O,O,O;")
        return PublisherState(
            publisher_name=publisher_name,
            symbol=symbol,
            asset_type="Crypto",
            schedule=schedule,
            public_key=SolanaPublicKey("2hgu6Umyokvo8FfSDdMa9nDKhcdv9Q4VvGNhRCeSWeD3"),
            status=PythPriceStatus.TRADING,
            aggregate_status=PythPriceStatus.TRADING,
            slot=publisher_slot,
            aggregate_slot=latest_block_slot - 5,
            latest_block_slot=latest_block_slot,
            price=100.0,
            price_aggregate=100.0,
            confidence_interval=1.0,
            confidence_interval_aggregate=1.0,
        )

    def make_check(
        self,
        state: PublisherState,
        max_slot_distance: int = 10,
        abandoned_slot_distance: int = 100,
    ) -> PublisherOfflineCheck:
        """Helper to create PublisherOfflineCheck with config."""
        return PublisherOfflineCheck(
            state,
            {
                "max_slot_distance": max_slot_distance,
                "abandoned_slot_distance": abandoned_slot_distance,
            },
        )

    def run_check_with_datetime(
        self,
        check: PublisherOfflineCheck,
        check_datetime: datetime,
        expected: bool | None = None,
    ) -> bool:
        """Run check with mocked datetime and optionally assert result."""
        with patch("pyth_observer.check.publisher.datetime") as mock_datetime:
            mock_datetime.now.return_value = check_datetime
            result = check.run()
            if expected is not None:
                assert result is expected
            return result

    def test_market_closed_passes_check(self):
        """Test that check passes when market is closed."""
        # Market schedule that's always closed (C = closed)
        closed_schedule = MarketSchedule("America/New_York;C,C,C,C,C,C,C;")
        state = self.make_state(
            publisher_slot=100,
            latest_block_slot=200,
            schedule=closed_schedule,
        )
        check = self.make_check(state, max_slot_distance=10, abandoned_slot_distance=50)

        # Should pass regardless of slot distance when market is closed
        assert check.run() is True

    def test_market_open_within_max_distance_passes(self):
        """Test that check passes when slot distance is within max_slot_distance."""
        state = self.make_state(publisher_slot=100, latest_block_slot=105)
        check = self.make_check(
            state, max_slot_distance=10, abandoned_slot_distance=100
        )

        assert check.run() is True

    def test_market_open_exceeds_max_distance_fails(self):
        """Test that check fails when slot distance exceeds max_slot_distance but not abandoned."""
        state = self.make_state(publisher_slot=100, latest_block_slot=120)
        check = self.make_check(
            state, max_slot_distance=10, abandoned_slot_distance=100
        )

        assert check.run() is False

    def test_market_open_exceeds_abandoned_distance_passes(self):
        """Test that check passes when slot distance exceeds abandoned_slot_distance."""
        state = self.make_state(publisher_slot=100, latest_block_slot=250)
        check = self.make_check(
            state, max_slot_distance=10, abandoned_slot_distance=100
        )

        assert check.run() is True

    def test_boundary_at_max_slot_distance(self):
        """Test boundary condition at max_slot_distance."""
        state = self.make_state(publisher_slot=100, latest_block_slot=110)
        check = self.make_check(
            state, max_slot_distance=10, abandoned_slot_distance=100
        )

        assert check.run() is False

    def test_boundary_below_max_slot_distance(self):
        """Test boundary condition just below max_slot_distance."""
        state = self.make_state(publisher_slot=100, latest_block_slot=109)
        check = self.make_check(
            state, max_slot_distance=10, abandoned_slot_distance=100
        )

        assert check.run() is True

    def test_boundary_at_abandoned_slot_distance(self):
        """Test boundary condition at abandoned_slot_distance."""
        state = self.make_state(publisher_slot=100, latest_block_slot=200)
        check = self.make_check(
            state, max_slot_distance=10, abandoned_slot_distance=100
        )

        # Distance is exactly 100, which is not > 100, so should fail
        assert check.run() is False

    def test_boundary_above_abandoned_slot_distance(self):
        """Test boundary condition just above abandoned_slot_distance."""
        state = self.make_state(publisher_slot=100, latest_block_slot=201)
        check = self.make_check(
            state, max_slot_distance=10, abandoned_slot_distance=100
        )

        # Distance is 101, which is > 100, so should pass (abandoned)
        assert check.run() is True

    def test_different_configurations(self):
        """Test with different configuration values."""
        state = self.make_state(publisher_slot=100, latest_block_slot=150)

        # Test with larger max_slot_distance - distance is 50, which is < 60, so should pass
        check1 = self.make_check(
            state, max_slot_distance=60, abandoned_slot_distance=200
        )
        assert check1.run() is True

        # Test with smaller abandoned_slot_distance - distance is 50, which is > 40, so should pass (abandoned)
        check2 = self.make_check(
            state, max_slot_distance=10, abandoned_slot_distance=40
        )
        assert check2.run() is True

    def test_zero_distance_passes(self):
        """Test that zero slot distance passes the check."""
        state = self.make_state(publisher_slot=100, latest_block_slot=100)
        check = self.make_check(
            state, max_slot_distance=10, abandoned_slot_distance=100
        )

        assert check.run() is True

    def test_market_schedule_variations(self):
        """Test with different market schedule patterns."""
        # Test with weekday-only schedule (Mon-Fri open)
        weekday_schedule = MarketSchedule("America/New_York;O,O,O,O,O,C,C;")
        state = self.make_state(
            publisher_slot=100,
            latest_block_slot=120,
            schedule=weekday_schedule,
        )
        check = self.make_check(
            state, max_slot_distance=10, abandoned_slot_distance=100
        )

        # Test on a Monday (market open) - should fail because market is open and distance exceeds max
        monday_open = datetime(
            2024, 1, 15, 14, 0, 0, tzinfo=ZoneInfo("America/New_York")
        )
        self.run_check_with_datetime(check, monday_open, expected=False)

        # Test on a Sunday (market closed) - should pass because market is closed
        sunday_closed = datetime(
            2024, 1, 14, 14, 0, 0, tzinfo=ZoneInfo("America/New_York")
        )
        self.run_check_with_datetime(check, sunday_closed, expected=True)

    def test_market_opening_detects_offline_publisher(self):
        """Test that when market opens, an offline publisher triggers the check."""
        # Use a weekday-only schedule (Mon-Fri open, weekends closed)
        weekday_schedule = MarketSchedule("America/New_York;O,O,O,O,O,C,C;")
        # Create a state where publisher is offline (slot distance exceeds max)
        state = self.make_state(
            publisher_slot=100,
            latest_block_slot=120,
            schedule=weekday_schedule,
        )
        check = self.make_check(
            state, max_slot_distance=10, abandoned_slot_distance=100
        )

        # First, verify market closed - should pass even with offline publisher
        market_closed_time = datetime(
            2024, 1, 14, 23, 59, 59, tzinfo=ZoneInfo("America/New_York")
        )  # Sunday night (market closed)
        self.run_check_with_datetime(check, market_closed_time, expected=True)

        # Now market opens - check should fire because publisher is offline
        # Distance is 20, which exceeds max_slot_distance of 10
        market_open_time = datetime(
            2024, 1, 15, 0, 0, 0, tzinfo=ZoneInfo("America/New_York")
        )  # Monday morning (market open)
        self.run_check_with_datetime(check, market_open_time, expected=False)
