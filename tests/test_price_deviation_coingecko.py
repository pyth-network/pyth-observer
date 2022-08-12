from pyth_observer.events import PriceDeviation, PriceDeviationCoinGecko
from pythclient.pythaccounts import PythPriceInfo, PythPriceStatus
from pyth_observer.prices import Price


class MockPythProductAccount:
    def __init__(self, product_attrs):
        self.attrs = product_attrs


class MockPriceAccount:
    def __init__(self, aggregate_price, current_slot, aggregate_price_info_slot, aggregate_price_info_status, product_attrs):
        self.slot = current_slot
        self.aggregate_price_info = PythPriceInfo(
            aggregate_price, 0, aggregate_price_info_status, aggregate_price_info_slot, 0)
        self.product = MockPythProductAccount(product_attrs)


def check_price_deviation_coingecko(aggregate_price, coingecko_price, product_attrs, expected_str):
    pa = MockPriceAccount(aggregate_price, 0, 0, PythPriceStatus.TRADING, product_attrs)
    network = "mainnet"
    symbol = "ZZZT"

    # coingecko_price["last_updated_at"] must be > coingecko_price_last_updated_at otherwise price is stale and it will be considered as valid
    validation = PriceDeviationCoinGecko(None, None, pa, network, symbol, {'usd': coingecko_price, 'last_updated_at': 2}, 1)
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


def test_price_deviation_coingecko():
    product_attrs = {'asset_type': 'Crypto', 'symbol': 'Crypto.BCH/USD', 'quote_currency': 'USD',
                     'description': 'BCH/USD', 'generic_symbol': 'BCHUSD', 'base': 'BCH'}

    check_price_deviation_coingecko(100, 100, product_attrs, None)

    # > 5%
    check_price_deviation_coingecko(100, 110, product_attrs, "ZZZT is more than 5% off from CoinGecko")
