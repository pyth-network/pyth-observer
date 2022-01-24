import pytest
from pyth_observer.events import TWAPvsAggregate
from pythclient.pythaccounts import TwEmaType, PythPriceType, PythPriceInfo, PythPriceStatus
from typing import List, Dict, Tuple, Optional, Any


class MockPriceAccount:
    def __init__(self):
        self.derivations: Dict[TwEmaType, int] = {}
        self.exponent = 0
        self.aggregate_price = 0
        self.price_type = PythPriceType.PRICE
        self.slot = 1
        self.aggregate_price_info = PythPriceInfo(0, 0, PythPriceStatus.TRADING, 0, 0)


def check_average(twap, aggregate, exponent, expected_str):
    price = 1234
    pa = MockPriceAccount()
    network = "mainnet"
    symbol = "ZZZT"

    pa.derivations[TwEmaType.TWAPVALUE] = 49132540
    pa.exponent = exponent
    pa.aggregate_price = aggregate * 10**exponent

    t = TWAPvsAggregate(None, price, pa, network, symbol)
    result = t.is_valid()

    if not result:
        title, details = t.get_event_details()
        print(title, details)

    if expected_str:
        assert not result
        assert title == expected_str
    else:
        assert result

def test_averages():
    # within 10%
    check_average(49132540, 48121502, 3, None)
    # outside 10%
    check_average(49132540, 43121502, 3, "ZZZT Aggregate is 14% different than TWAP")
    # 0.0 aggregate happens occasionally when a publisher publishes bad data
    check_average(49132540, 0.0, 3, None)
