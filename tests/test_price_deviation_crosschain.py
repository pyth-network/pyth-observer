from pyth_observer.events import PriceDeviationCrosschain
from pythclient.pythaccounts import PythPriceInfo, PythPriceStatus


class MockPythProductAccount:
    def __init__(self, product_attrs):
        self.attrs = product_attrs


class MockPriceAccount:
    def __init__(
        self,
        aggregate_price,
        current_slot,
        aggregate_price_info_slot,
        aggregate_price_info_status,
        product_attrs,
    ):
        self.slot = current_slot
        self.aggregate_price_info = PythPriceInfo(
            aggregate_price,
            0,
            aggregate_price_info_status,
            aggregate_price_info_slot,
            0,
        )
        self.product = MockPythProductAccount(product_attrs)


def check_price_deviation_crosschain(
    aggregate_price,
    crosschain_price,
    crosschain_conf,
    crosschain_publish_time,
    crosschain_prev_publish_time,
    product_attrs,
    expected_str,
):
    pa = MockPriceAccount(aggregate_price, 0, 0, PythPriceStatus.TRADING, product_attrs)
    network = "mainnet"
    symbol = "ZZZT"

    validation = PriceDeviationCrosschain(
        None,
        None,
        pa,
        network,
        symbol,
        None,
        None,
        {
            "price": crosschain_price,
            "conf": crosschain_conf,
            "publish_time": crosschain_publish_time,
            "prev_publish_time": crosschain_prev_publish_time,
        },
    )
    # Set the firing threshold to 5% for testing
    validation.threshold = 5
    result = validation.is_valid()

    if not result:
        title, details = validation.get_event_details()
        print(title, details)

    if expected_str:
        assert not result
        assert title == expected_str
    else:
        assert result


def test_price_deviation_crosschain():
    product_attrs = {
        "asset_type": "Crypto",
        "symbol": "Crypto.BCH/USD",
        "quote_currency": "USD",
        "description": "BCH/USD",
        "generic_symbol": "BCHUSD",
        "base": "BCH",
    }

    check_price_deviation_crosschain(100, 100, 1, 1, 0, product_attrs, None)

    # stale publish time
    check_price_deviation_crosschain(100, 100, 1, 1, 1, product_attrs, None)

    # > 5%
    check_price_deviation_crosschain(
        10,
        100,
        1,
        1,
        0,
        product_attrs,
        "Cross-chain ZZZT is more than 5 confidence intervals away from Solana ZZZT",
    )
