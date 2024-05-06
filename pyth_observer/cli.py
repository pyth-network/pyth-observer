import asyncio
import os
import sys

import click
import yaml
from loguru import logger
from prometheus_client import start_http_server

from pyth_observer import Observer


@click.command()
@click.option(
    "--config",
    help="Path to YAML/JSON file with general config",
    envvar="CONFIG",
    required=True,
)
@click.option(
    "--publishers",
    help="Path to YAML/JSON file with publisher name-key associations",
    envvar="PUBLISHERS",
    required=True,
)
@click.option(
    "--coingecko-mapping",
    help="Path to YAML/JSON file with Coingecko mappings",
    envvar="COINGECKO_MAPPING",
    required=True,
)
@click.option(
    "--telegram-mapping",
    help="Path to YAML/JSON file with publisher key-Telegram chat ID mappings",
    envvar="TELEGRAM_MAPPING",
    required=False,
)
@click.option(
    "--prometheus-port",
    help="Port number for Prometheus metrics endpoint",
    envvar="PROMETHEUS_PORT",
    default="9001",
)
def run(config, publishers, coingecko_mapping, telegram_mapping, prometheus_port):
    config_ = yaml.safe_load(open(config, "r"))
    publishers_ = yaml.safe_load(open(publishers, "r"))
    publishers_inverted = {v: k for k, v in publishers_.items()}
    coingecko_mapping_ = yaml.safe_load(open(coingecko_mapping, "r"))
    telegram_mapping_ = (
        yaml.safe_load(open(telegram_mapping, "r")) if telegram_mapping else {}
    )
    observer = Observer(
        config_, publishers_inverted, coingecko_mapping_, telegram_mapping_
    )

    start_http_server(int(prometheus_port))

    asyncio.run(observer.run())


logger.remove()
logger.add(
    sys.stdout,
    serialize=(not os.environ.get("DEV_MODE")),
    level=os.environ.get("LOG_LEVEL", "INFO"),
)
