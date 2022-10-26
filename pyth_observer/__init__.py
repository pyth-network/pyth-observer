import asyncio
import json
import os
from typing import Any, Dict, Tuple

import yaml
from loguru import logger
from pythclient.pythclient import PythClient
from pythclient.solana import (
    SOLANA_DEVNET_HTTP_ENDPOINT,
    SOLANA_DEVNET_WS_ENDPOINT,
    SOLANA_MAINNET_HTTP_ENDPOINT,
    SOLANA_MAINNET_WS_ENDPOINT,
    SOLANA_TESTNET_HTTP_ENDPOINT,
    SOLANA_TESTNET_WS_ENDPOINT,
)
from throttler import Throttler

from pyth_observer.check import PriceFeedState, PublisherState
from pyth_observer.coingecko import get_coingecko_prices
from pyth_observer.dispatch import Dispatch

from .dns import get_key  # noqa

PYTHTEST_HTTP_ENDPOINT = "https://api.pythtest.pyth.network/"
PYTHTEST_WS_ENDPOINT = "wss://api.pythtest.pyth.network/"
PYTHNET_HTTP_ENDPOINT = "https://pythnet.rpcpool.com/"
PYTHNET_WS_ENDPOINT = "wss://pythnet.rpcpool.com/"

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_solana_urls(network) -> Tuple[str, str]:
    """
    Helper for getting the correct urls for the PythClient
    """
    mapping = {
        "devnet": (SOLANA_DEVNET_HTTP_ENDPOINT, SOLANA_DEVNET_WS_ENDPOINT),
        "testnet": (SOLANA_TESTNET_HTTP_ENDPOINT, SOLANA_TESTNET_WS_ENDPOINT),
        "mainnet": (SOLANA_MAINNET_HTTP_ENDPOINT, SOLANA_MAINNET_WS_ENDPOINT),
        "pythtest": (PYTHTEST_HTTP_ENDPOINT, PYTHTEST_WS_ENDPOINT),
        "pythnet": (PYTHNET_HTTP_ENDPOINT, PYTHNET_WS_ENDPOINT),
    }
    return mapping[network]


class Observer:
    def __init__(self, config: Any, publishers: Any, coingecko_mapping: Any):
        self.config = config
        self.publishers = publishers
        self.coingecko_mapping = coingecko_mapping

    async def run(self):
        async with PythClient(
            solana_endpoint=self.config["network"]["http_endpoint"],
            solana_ws_endpoint=self.config["network"]["ws_endpoint"],
            first_mapping_account_key=self.config["network"]["first_mapping"],
        ) as pyth:
            pyth_rate_limit = Throttler(rate_limit=10, period=1)
            coingecko_rate_limit = Throttler(rate_limit=1, period=60)
            dispatch = Dispatch(self.config, self.publishers)

            while True:
                logger.info("Running checks")

                async with pyth_rate_limit:
                    await pyth.refresh_all_prices()

                async with pyth_rate_limit:
                    products = await pyth.get_products()

                async with coingecko_rate_limit:
                    data = await get_coingecko_prices(self.coingecko_mapping)
                    coingecko_prices: Dict[str, float] = {}
                    coingecko_updates: Dict[str, int] = {}  # Unix timestamps

                    for symbol in data:
                        coingecko_prices[symbol] = data[symbol]["usd"]
                        coingecko_updates[symbol] = data[symbol]["last_updated_at"]

                for product in products:
                    # Skip tombstone accounts with blank metadata
                    if "base" not in product.attrs:
                        continue

                    async with pyth_rate_limit:
                        price_accounts = await product.get_prices()

                    states = []

                    for _, price_account in price_accounts.items():
                        states.append(
                            PriceFeedState(
                                symbol=product.attrs["symbol"],
                                asset_type=product.attrs["asset_type"],
                                public_key=price_account.key,
                                status=price_account.aggregate_price_status,
                                slot=price_account.valid_slot,
                                slot_aggregate=price_account.aggregate_price_info.pub_slot,
                                price_aggregate=price_account.aggregate_price_info.price,
                                confidence_interval_aggregate=price_account.aggregate_price_info.confidence_interval,
                                coingecko_price=coingecko_prices.get(
                                    product.attrs["base"]
                                ),
                                coingecko_update=coingecko_updates.get(
                                    product.attrs["base"]
                                ),
                            )
                        )

                        for component in price_account.price_components:
                            states.append(
                                PublisherState(
                                    symbol=product.attrs["symbol"],
                                    public_key=component.publisher_key,
                                    confidence_interval=component.latest_price_info.confidence_interval,
                                    confidence_interval_aggregate=component.last_aggregate_price_info.confidence_interval,
                                    price=component.latest_price_info.price,
                                    price_aggregate=price_account.aggregate_price_info.price,
                                    slot=component.latest_price_info.pub_slot,
                                    slot_aggregate=component.last_aggregate_price_info.pub_slot,
                                    status=component.latest_price_info.price_status,
                                )
                            )

                    dispatch.run(states)

                logger.debug("Sleeping for 10 seconds")
                await asyncio.sleep(10)
