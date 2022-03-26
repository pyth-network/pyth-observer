import asyncio

from asyncio_throttle import Throttler
from loguru import logger
from pythclient.pythclient import PythClient

from pyth_observer import get_key, get_solana_urls
from pyth_observer.price_account_observer import PriceAccountObserver
from pyth_observer.publisher_price_observer import PublisherPriceObserver


async def main():
    network = "testnet"
    program_key = get_key(network=network, type="program", version="v2")
    mapping_key = get_key(network=network, type="mapping", version="v2")
    http_url, ws_url = get_solana_urls(network=network)

    throttler = Throttler(rate_limit=6, period=3)

    async with PythClient(
        solana_endpoint=http_url,
        solana_ws_endpoint=ws_url,
        first_mapping_account_key=mapping_key,
        program_key=program_key,
    ) as client:
        observers = []

        for product in await client.get_products():
            async with throttler:
                price_accounts = await product.get_prices()

            for _, price_account in price_accounts.items():
                observers.append(PriceAccountObserver(client, throttler, price_account).run())
                observers.append(PublisherPriceObserver(client, throttler, price_account).run())

        await asyncio.gather(*observers)




asyncio.run(main())
