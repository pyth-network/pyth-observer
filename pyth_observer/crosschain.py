import time
from typing import Dict, TypedDict

import requests
from aiohttp import ClientSession
from loguru import logger
from more_itertools import chunked
from throttler import throttle


class CrosschainPrice(TypedDict):
    price: float
    conf: float
    publish_time: int  # UNIX timestamp
    snapshot_time: int  # UNIX timestamp


class CrosschainPriceObserver:
    def __init__(self, url):
        self.url = url
        self.valid = self.is_endpoint_valid()

    def is_endpoint_valid(self) -> bool:
        try:
            return requests.head(self.url).status_code == 200
        except requests.ConnectionError:
            logger.error("failed to connect to cross-chain api")
            return False

    @throttle(rate_limit=1, period=1)
    async def get_crosschain_prices(self) -> Dict[str, CrosschainPrice]:
        async with ClientSession(
            headers={"content-type": "application/json"}
        ) as session:
            price_feed_ids_url = f"{self.url}/api/price_feed_ids"

            async with session.get(price_feed_ids_url) as response:
                price_feed_ids = await response.json()

            price_feeds = []

            for ids in chunked(price_feed_ids, 25):
                price_feeds_url = f"{self.url}/api/latest_price_feeds"

                # aiohttp does not support encoding array params using PHP-style `ids=[]`
                # naming, so we encode it manually and append to the URL.
                query_string = "?" + "&".join(f"ids[]={v}" for v in ids)
                async with session.get(
                    price_feeds_url + query_string,
                ) as response:
                    price_feeds += await response.json()

        # Return a dictionary of id -> {price, conf, expo} for fast lookup
        return {
            data["id"]: {
                "price": int(data["price"]["price"]) * 10 ** data["price"]["expo"],
                "conf": int(data["price"]["conf"]) * 10 ** data["price"]["expo"],
                "publish_time": data["price"]["publish_time"],
                "snapshot_time": int(time.time()),
            }
            for data in price_feeds
        }
