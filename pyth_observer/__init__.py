import asyncio
import os
from typing import Any, Dict, Tuple

from base58 import b58decode
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

from pyth_observer.checks.price_feed import PriceFeedState
from pyth_observer.checks.publisher import PublisherState
from pyth_observer.coingecko import get_coingecko_prices
from pyth_observer.crosschain import (
    CrosschainPrice,
    CrosschainPriceObserver as Crosschain,
)
from pyth_observer.dispatch import Dispatch

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
        self.dispatch = Dispatch(config, publishers)
        self.publishers = publishers
        self.pyth_client = PythClient(
            solana_endpoint=config["network"]["http_endpoint"],
            solana_ws_endpoint=config["network"]["ws_endpoint"],
            first_mapping_account_key=config["network"]["first_mapping"],
        )
        self.pyth_throttler = Throttler(
            rate_limit=int(config["network"]["request_rate_limit"]),
            period=float(config["network"]["request_rate_period"]),
        )
        self.crosschain = Crosschain(self.config["network"]["crosschain_endpoint"])
        self.crosschain_throttler = Throttler(rate_limit=1, period=1)
        self.coingecko_mapping = coingecko_mapping

    async def run(self):
        while True:
            logger.info("Running checks")

            products = await self.get_pyth_products()
            coingecko_prices, coingecko_updates = await self.get_coingecko_prices()
            crosschain_prices = await self.get_crosschain_prices()

            for product in products:
                # Skip tombstone accounts with blank metadata
                if "base" not in product.attrs:
                    continue

                if not product.first_price_account_key:
                    continue

                # For each product, we build a list of price feed states (one
                # for each price account) and a list of publisher states (one
                # for each publisher).
                states = []
                price_accounts = await self.get_pyth_prices(product)
                crosschain_price = crosschain_prices[
                    b58decode(product.first_price_account_key.key).hex()
                ]

                for _, price_account in price_accounts.items():
                    if not price_account.aggregate_price_status:
                        raise RuntimeError("Price account status is missing")

                    if not price_account.aggregate_price_info:
                        raise RuntimeError("Aggregate price info is missing")

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
                            coingecko_price=coingecko_prices.get(product.attrs["base"]),
                            coingecko_update=coingecko_updates.get(
                                product.attrs["base"]
                            ),
                            crosschain_price=crosschain_price,
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

                await self.dispatch.run(states)

            logger.debug("Sleeping...")
            await asyncio.sleep(5)

    async def get_pyth_products(self):
        logger.debug("Fetching Pyth product accounts...")

        async with self.pyth_throttler:
            return await self.pyth_client.get_products()

    async def get_pyth_prices(self, product):
        logger.debug("Fetching Pyth price accounts...")

        async with self.pyth_throttler:
            return await product.get_prices()

    async def get_coingecko_prices(self):
        logger.debug("Fetching CoinGecko prices...")

        data = await get_coingecko_prices(self.coingecko_mapping)
        prices: Dict[str, float] = {}
        updates: Dict[str, int] = {}  # Unix timestamps

        for symbol in data:
            prices[symbol] = data[symbol]["usd"]
            updates[symbol] = data[symbol]["last_updated_at"]

        return (prices, updates)

    async def get_crosschain_prices(self) -> Dict[str, CrosschainPrice]:
        return await self.crosschain.get_crosschain_prices()
