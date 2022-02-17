from pyth_observer.events import PublisherPriceFeedOffline
from pythclient.pythaccounts import PythPriceInfo, PythPriceStatus
from pyth_observer.prices import Price


def check_publisher_price_offline(current_slot, publisher_slot, publisher_status, product_attrs, expected_str):
    network = "mainnet"
    symbol = "ZZZT"
    publisher_key = "pubkey"

    price = Price(current_slot, product_attrs=product_attrs, publishers={publisher_key: "pubname"})

    quoter_aggregate = PythPriceInfo(
        raw_price=0,
        raw_confidence_interval=1,
        price_status=publisher_status,
        slot=5,
        exponent=-1
    )
    price.quoter_aggregates[publisher_key] = quoter_aggregate

    publisher_latest = PythPriceInfo(
        raw_price=0,
        raw_confidence_interval=1,
        price_status=publisher_status,
        slot=publisher_slot,
        exponent=-1
    )
    price.quoters[publisher_key] = publisher_latest

    validation = PublisherPriceFeedOffline(publisher_key, price, None, network, symbol)
    # Set the firing threshold to 10% for testing
    result = validation.is_valid()

    if not result:
        title, details = validation.get_event_details()
        print(title, details)

    if expected_str:
        assert not result
        assert title == expected_str
    else:
        assert result


def test_publisher_price_offline():
    trading = PythPriceStatus.TRADING
    unknown = PythPriceStatus.UNKNOWN

    product_attrs = {'asset_type': 'Crypto', 'symbol': 'Crypto.BCH/USD', 'quote_currency': 'USD',
                     'description': 'BCH/USD', 'generic_symbol': 'BCHUSD', 'base': 'BCH'}

    # publisher slot > 25 behind current latest slot
    check_publisher_price_offline(27, 1, trading, product_attrs,
                                  "pubkey ZZZT price feed is offline (has not updated its price in > 25 slots OR status is unknown)")

    # publisher trading status is != trading
    check_publisher_price_offline(1, 1, unknown, product_attrs,
                                  "pubkey ZZZT price feed is offline (has not updated its price in > 25 slots OR status is unknown)")

    # no event if publisher slot is <= 25 current latest slot and status is trading
    check_publisher_price_offline(1, 1, trading, product_attrs, None)
