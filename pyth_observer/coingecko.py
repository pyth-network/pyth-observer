import json
import os

from aiocoingecko import AsyncCoinGeckoAPISession
from pycoingecko import CoinGeckoAPI
from asyncio_throttle import Throttler

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

def get_coingecko_symbol_to_id_mapping():
    with open(f'{ROOT_DIR}/coingecko_mapping.json') as json_file:
        data = json.load(json_file)

    return data


symbol_to_id_mapping = get_coingecko_symbol_to_id_mapping()
api_to_symbol_mapping = {symbol_to_id_mapping[x]['api']: x for x in symbol_to_id_mapping}

throttler = Throttler(rate_limit=1, period=1)

async def get_coingecko_prices(symbols):
    ids = [symbol_to_id_mapping[x]["api"] for x in symbol_to_id_mapping if x in symbols]

    async with AsyncCoinGeckoAPISession() as client:
        async with throttler:
            prices = await client.get_price(ids=",".join(ids), vs_currencies='usd')
    # remap to symbol -> prices
    prices_mapping = {api_to_symbol_mapping[x]: prices[x] for x in prices}

    return prices_mapping


def get_coingecko_market_id(symbol):
    return symbol_to_id_mapping[symbol]['market'] if symbol in symbol_to_id_mapping else None
