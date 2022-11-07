from pythclient.pythaccounts import PythPriceStatus
from pythclient.solana import SolanaPublicKey

from pyth_observer.check.price_feed import PriceFeedAggregateCheck, PriceFeedState


def test_price_feed_aggregate_check():
    state = PriceFeedState(
        symbol="Crypto.BTC/USD",
        asset_type="Crypto",
        public_key=SolanaPublicKey("2hgu6Umyokvo8FfSDdMa9nDKhcdv9Q4VvGNhRCeSWeD3"),
        status=PythPriceStatus.TRADING,
        slot_aggregate_attempted=100,
        slot_aggregate=105,
        price_aggregate=1000.0,
        confidence_interval_aggregate=10.0,
        coingecko_price=1005.0,
        coingecko_update=0,
        crosschain_price={"price": 1003.0, "conf": 10.0, "publish_time": 123},
    )

    assert PriceFeedAggregateCheck(state, {"max_slot_distance": 10}).run()
    assert not PriceFeedAggregateCheck(state, {"max_slot_distance": 2}).run()
