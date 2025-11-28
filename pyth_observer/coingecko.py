from typing import Any, Dict

from loguru import logger
from pycoingecko import CoinGeckoAPI
from requests.exceptions import HTTPError
from throttler import throttle


# CoinGecko free API limit: 10-50 (varies) https://www.coingecko.com/en/api/pricing
# However prices are updated every 1-10 minutes: https://www.coingecko.com/en/faq
# Hence we only have to query once every minute.
@throttle(rate_limit=1, period=10)
async def get_coingecko_prices(
    symbol_to_ticker: Dict[str, str],
) -> Dict[str, Dict[str, Any]]:
    ticker_to_symbol = {v: k for k, v in symbol_to_ticker.items()}
    ids = list(ticker_to_symbol.keys())

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

    return {ticker_to_symbol[x]: prices[x] for x in prices}
