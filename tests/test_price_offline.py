from pyth_observer.events import PriceFeedOffline
from pythclient.pythaccounts import PythPriceInfo, PythPriceStatus


class MockPythProductAccount:
    def __init__(self, product_attrs):
        self.attrs = product_attrs


class MockPriceAccount:
    def __init__(self, current_slot, aggregate_price_info_slot, aggregate_price_info_status, product_attrs):
        self.slot = current_slot
        self.aggregate_price_info = PythPriceInfo(0, 0, aggregate_price_info_status, aggregate_price_info_slot, 0)
        self.product = MockPythProductAccount(product_attrs)


def check_price_offline(current_slot, aggregate_price_info_slot, aggregate_price_info_status, product_attrs, expected_str):
    pa = MockPriceAccount(current_slot, aggregate_price_info_slot, aggregate_price_info_status, product_attrs)
    network = "mainnet"
    symbol = "ZZZT"

    t = PriceFeedOffline(None, 0, pa, network, symbol)
    result = t.is_valid()

    if not result:
        title, details = t.get_event_details()
        print(title, details)

    if expected_str:
        assert not result
        assert title == expected_str
    else:
        assert result


def test_price_offline():
    trading = PythPriceStatus.TRADING
    unknown = PythPriceStatus.UNKNOWN

    product_attrs = {'asset_type': 'Crypto', 'symbol': 'Crypto.BCH/USD', 'quote_currency': 'USD',
                     'description': 'BCH/USD', 'generic_symbol': 'BCHUSD', 'base': 'BCH'}

    # aggregate slot > 25 behind current latest slot
    check_price_offline(27, 1, trading, product_attrs,
                        "ZZZT price feed is offline (has not updated its price in > 25 slots OR status is unknown)")

    # aggregate trading status is != trading
    check_price_offline(1, 1, unknown, product_attrs,
                        "ZZZT price feed is offline (has not updated its price in > 25 slots OR status is unknown)")

    # no event if aggregate slot is <= 25 current latest slot and status is trading
    check_price_offline(1, 1, trading, product_attrs, None)
