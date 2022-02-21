import json
import os

from pycoingecko import CoinGeckoAPI


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

cg = CoinGeckoAPI()


def get_coingecko_symbol_to_id_mapping():
    with open(f'{ROOT_DIR}/coingecko_mapping.json') as json_file:
        data = json.load(json_file)

    return data


symbol_to_id_mapping = get_coingecko_symbol_to_id_mapping()
api_to_symbol_mapping = {symbol_to_id_mapping[x]['api']: x for x in symbol_to_id_mapping}


def get_coingecko_prices(symbols):
    ids = [symbol_to_id_mapping[x]["api"] for x in symbol_to_id_mapping if x in symbols]
    prices = cg.get_price(ids=ids, vs_currencies='usd')
    # remap to symbol -> prices
    prices_mapping = {api_to_symbol_mapping[x]: prices[x] for x in prices}
    return prices_mapping


def get_coingecko_market_id(symbol):
    return symbol_to_id_mapping[symbol]['market'] if symbol in symbol_to_id_mapping else None
