import json
import os

from pycoingecko import CoinGeckoAPI


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

cg = CoinGeckoAPI()


def get_coingecko_symbol_to_id_mapping():
    with open(f'{ROOT_DIR}/coingecko_mapping.json') as json_file:
        data = json.load(json_file)

    return data


mapping = get_coingecko_symbol_to_id_mapping()


def get_coingecko_prices(symbols):
    ids = [mapping[x]["api"] for x in mapping if x in symbols]
    prices = cg.get_price(ids=ids, vs_currencies='usd')
    return prices


def get_coingecko_api_id(symbol):
    return mapping[symbol]['api'] if symbol in mapping else None


def get_coingecko_market_id(symbol):
    return mapping[symbol]['market'] if symbol in mapping else None
