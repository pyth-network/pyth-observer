import time
from unittest.mock import patch

from pythclient.pythaccounts import PythPriceStatus
from pythclient.solana import SolanaPublicKey

from pyth_observer.check.publisher import (
    PUBLISHER_CACHE,
    PublisherPriceCheck,
    PublisherStalledCheck,
    PublisherState,
)


def make_state(
    pub_slot: int,
    pub_price: float,
    pub_conf: float,
    agg_slot: int,
    agg_price: float,
    agg_conf: float,
) -> PublisherState:
    return PublisherState(
        publisher_name="publisher",
        symbol="Crypto.BTC/USD",
        asset_type="Crypto",
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
    state1 = make_state(1, 100.0, 2.0, 1, 110.0, 1.0)
    assert check_is_ok(state1, 10, 25)
    assert not check_is_ok(state1, 6, 25)


def test_publisher_stalled_check():
    current_time = time.time()

    def simulate_time_pass(seconds):
        nonlocal current_time
        current_time += seconds
        return current_time

    def setup_check(state, stall_time_limit):
        check = PublisherStalledCheck(state, {"stall_time_limit": stall_time_limit})
        PUBLISHER_CACHE[(state.publisher_name, state.symbol)] = (
            state.price,
            current_time,
        )
        return check

    def run_check(check, seconds, expected):
        with patch("time.time", new=lambda: simulate_time_pass(seconds)):
            assert check.run() == expected

    PUBLISHER_CACHE.clear()
    state_a = make_state(1, 100.0, 2.0, 1, 100.0, 1.0)
    check_a = setup_check(state_a, 5)
    run_check(check_a, 5, True)  # Should pass as it hits the limit exactly

    PUBLISHER_CACHE.clear()
    state_b = make_state(1, 100.0, 2.0, 1, 100.0, 1.0)
    check_b = setup_check(state_b, 5)
    run_check(check_b, 6, False)  # Should fail as it exceeds the limit

    PUBLISHER_CACHE.clear()
    state_c = make_state(1, 100.0, 2.0, 1, 100.0, 1.0)
    check_c = setup_check(state_c, 5)
    run_check(check_c, 2, True)  # Initial check should pass
    state_c.price = 105.0  # Change the price
    run_check(check_c, 3, True)  # Should pass as price changes
    state_c.price = 100.0  # Change back to original price
    run_check(check_c, 4, True)  # Should pass as price changes
    run_check(
        check_c, 8, False
    )  # Should fail as price stalls for too long after last change
