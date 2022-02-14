import json
import requests
import os

from ratelimit import limits, RateLimitException, sleep_and_retry

from pycoingecko import CoinGeckoAPI


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

ONE_MINUTE = 60
MAX_CALLS_PER_MINUTE = 50

cg = CoinGeckoAPI()


def get_coingecko_symbol_to_id_mapping():
    with open(f'{ROOT_DIR}/coingecko_mapping.json') as json_file:
        data = json.load(json_file)

    return data


@sleep_and_retry
@limits(calls=MAX_CALLS_PER_MINUTE, period=ONE_MINUTE)
def get_coingecko_prices(mapping, symbols):
    ids = [mapping[x] for x in mapping if x in symbols]
    prices = cg.get_price(ids=ids, vs_currencies='usd')
    return prices
