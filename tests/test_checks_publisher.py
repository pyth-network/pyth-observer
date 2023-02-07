from pythclient.pythaccounts import PythPriceStatus
from pythclient.solana import SolanaPublicKey

from pyth_observer.check.publisher import PublisherPriceCheck, PublisherState


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
