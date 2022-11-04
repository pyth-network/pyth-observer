from typing import Dict, TypedDict

from loguru import logger
from pycoingecko import CoinGeckoAPI
from requests.exceptions import HTTPError
from throttler import throttle


class Symbol(TypedDict):
    api: str
    market: str


# CoinGecko free API limit: 10-50 (varies) https://www.coingecko.com/en/api/pricing
# However prices are updated every 1-10 minutes: https://www.coingecko.com/en/faq
# Hence we only have to query once every minute.
@throttle(rate_limit=1, period=60)
async def get_coingecko_prices(mapping: Dict[str, Symbol]):
    inverted_mapping = {mapping[x]["api"]: x for x in mapping}
    ids = [mapping[x]["api"] for x in mapping]

    try:
        prices = CoinGeckoAPI().get_price(
            ids=ids, vs_currencies="usd", include_last_updated_at=True
        )
    except (ValueError, HTTPError) as exc:
        logger.exception(exc)
        logger.error(
            "CoinGecko API call failed - CoinGecko price comparisons not available."
        )
        prices = {}

    # remap to symbol -> prices
    prices_mapping = {inverted_mapping[x]: prices[x] for x in prices}
    return prices_mapping
