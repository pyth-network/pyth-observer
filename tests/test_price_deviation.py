from pythclient.pythaccounts import PythPriceInfo, PythPriceStatus

from pyth_observer.events import PriceDeviation
from pyth_observer.prices import Price


def check_price_deviation(
    publisher_price, publisher_status, aggregate_price, aggregate_status, expected_str
):
    network = "mainnet"
    symbol = "ZZZT"
    publisher_key = "pubkey"

    aggregate = PythPriceInfo(
        raw_price=aggregate_price,
        raw_confidence_interval=1,
        price_status=aggregate_status,
        slot=1,
        exponent=-1,
    )

    price = Price(1, aggregate, publishers={publisher_key: "pubname"})

    quoter_aggregate = PythPriceInfo(
        raw_price=publisher_price,
        raw_confidence_interval=1,
        price_status=publisher_status,
        slot=1,
        exponent=-1,
    )
    price.quoter_aggregates[publisher_key] = quoter_aggregate

    quoter_latest = PythPriceInfo(
        raw_price=0,
        raw_confidence_interval=1,
        price_status=publisher_status,
        slot=1,
        exponent=-1,
    )
    price.quoters[publisher_key] = quoter_latest

    validation = PriceDeviation(publisher_key, price, None, network, symbol)
    # Set the firing threshold to 10% for testing
    validation.threshold = 10
    result = validation.is_valid()

    if not result:
        title, details = validation.get_event_details()
        print(title, details)

    if expected_str:
        assert not result
        assert title == expected_str
    else:
        assert result


def test_price_deviation():
    trading = PythPriceStatus.TRADING
    unknown = PythPriceStatus.UNKNOWN

    check_price_deviation(100, trading, 100, trading, None)

    # > 10%
    check_price_deviation(
        111, trading, 100, trading, "PUBNAME price is 11% off on ZZZT"
    )
    check_price_deviation(89, trading, 100, trading, "PUBNAME price is 11% off on ZZZT")

    # No event if either status is != trading
    check_price_deviation(111, trading, 100, unknown, None)
    check_price_deviation(111, unknown, 100, trading, None)
