from pythclient.pythaccounts import PythPriceStatus
from pythclient.solana import SolanaPublicKey

from pyth_observer.check.price_feed import PriceFeedOfflineCheck, PriceFeedState


def test_price_feed_offline_check():
    state = PriceFeedState(
        symbol="Crypto.BTC/USD",
        asset_type="Crypto",
        public_key=SolanaPublicKey("2hgu6Umyokvo8FfSDdMa9nDKhcdv9Q4VvGNhRCeSWeD3"),
        status=PythPriceStatus.TRADING,
        latest_block_slot=100,
        latest_trading_slot=105,
        price_aggregate=1000.0,
        confidence_interval_aggregate=10.0,
        coingecko_price=1005.0,
        coingecko_update=0,
        crosschain_price={"price": 1003.0, "conf": 10.0, "publish_time": 123},
    )

    assert PriceFeedOfflineCheck(
        state, {"max_slot_distance": 10, "abandoned_slot_distance": 100}
    ).run()
    assert not PriceFeedOfflineCheck(
        state, {"max_slot_distance": 2, "abandoned_slot_distance": 100}
    ).run()
