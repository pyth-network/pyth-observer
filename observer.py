#!/usr/bin/env python3
import os
import sys
import json
import argparse

from aiohttp import ClientConnectorError
import asyncio
from loguru import logger

from pythclient.pythclient import PythClient
from pythclient.exceptions import SolanaException

from pythclient.ratelimit import RateLimit
from pyth_observer import get_solana_urls, get_key
from pyth_observer.prices import Price, PriceValidator

logger.enable("pythclient")
RateLimit.configure_default_ratelimit(overall_cps=5, method_cps=3, connection_cps=3)


def get_publishers(network):
    """
    Get the mapping of publisher key --> names.
    """
    try:
        with open("publishers.json") as _fh:
            json_data = json.load(_fh)
    except (OSError, ValueError, TypeError, FileNotFoundError):
        logger.error("problem loading publishers.json only keys will be printed")
        json_data = {}
    return {key: name for name, key in json_data.get(network, {}).items()}


async def main(args):
    program_key = get_key(network=args.network, type="program", version="v2")
    mapping_key = get_key(network=args.network, type="mapping", version="v2")
    http_url, ws_url = get_solana_urls(network=args.network)

    publishers = get_publishers(args.network)

    async with PythClient(
        solana_endpoint=http_url,
        solana_ws_endpoint=ws_url,
        first_mapping_account_key=mapping_key,
        program_key=program_key if args.use_program_accounts else None,
    ) as c:

        validators = {}

        logger.info(
            "Starting pyth-observer against {}: {}", args.network, http_url
        )
        while True:
            try:
                await c.refresh_all_prices()
            except (ClientConnectorError, SolanaException) as exc:
                logger.error("{} refreshing prices: {}", exc.__class__.__name__, exc)
                asyncio.sleep(0.4)
                continue

            logger.trace("Updating product listing")
            try:
                products = await c.get_products()
            except (ClientConnectorError, SolanaException) as exc:
                logger.error("{} refreshing prices: {}", exc.__class__.__name__, exc)
                asyncio.sleep(0.4)
                continue

            for product in products:
                errors = []
                symbol = product.symbol

                if symbol not in validators:
                    # TODO: If publisher_key is not None, then only do validation for that publisher
                    validators[symbol] = PriceValidator(
                        key=args.publisher_key,
                        network=args.network,
                        symbol=symbol,
                    )

                prices = await product.get_prices()

                for _, price_account in prices.items():
                    price = Price(
                        slot=price_account.slot,
                        aggregate=price_account.aggregate_price_info,
                        product_attrs=product.attrs,
                        publishers=publishers,
                    )
                    price_account_errors = validators[symbol].verify_price_account(
                        price_account=price_account,
                    )
                    if price_account_errors:
                        errors.extend(price_account_errors)

                    for price_comp in price_account.price_components:
                        # The PythPublisherKey
                        publisher = price_comp.publisher_key.key

                        price.quoters[publisher] = price_comp.latest_price_info
                        price.quoter_aggregates[
                            publisher
                        ] = price_comp.last_aggregate_price_info

                    # Where the magic happens!
                    price_errors = validators[symbol].verify_price(
                        price=price, include_noisy=args.include_noisy_alerts
                    )
                    if price_errors:
                        errors.extend(price_errors)

                # Send all notifications for a given symbol pair
                await validators[symbol].notify(
                    errors,
                    slack_webhook_url=args.slack_webhook_url,
                    notification_mins=args.notification_snooze_mins,
                )
            await asyncio.sleep(0.4)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-l",
        "--log-level",
        action="store",
        type=str.upper,
        choices=["INFO", "WARN", "ERROR", "DEBUG", "TRACE"],
        default="ERROR",
    )
    parser.add_argument(
        "-n",
        "--network",
        action="store",
        choices=["devnet", "mainnet", "testnet"],
        default="devnet",
    )
    parser.add_argument(
        "-k",
        "--publisher-key",
        help="The public key for a single publisher to monitor for",
    )
    parser.add_argument(
        "-u",
        "--use-program-accounts",
        action="store_true",
        default=False,
        help="Use getProgramAccounts to get all pyth data",
    )
    parser.add_argument(
        "--slack-webhook-url",
        default=os.environ.get("PYTH_OBSERVER_SLACK_WEBHOOK_URL"),
        help="Slack incoming webhook url for notifications. This is required to send alerts to slack",
    )
    parser.add_argument(
        "--notification-snooze-mins",
        type=int,
        default=0,
        help="Minutes between sending notifications for similar erroneous events",
    )
    parser.add_argument(
        "-N",
        "--include-noisy-alerts",
        action="store_true",
        default=False,
        help="Include alerts which might be excessively noisy when used for all publishers",
    )
    args = parser.parse_args()

    logger.remove()
    logger.add(sys.stderr, level=args.log_level)
    try:
        asyncio.run(main(args=args))
    except KeyboardInterrupt:
        logger.info("Exiting on CTRL-c")
