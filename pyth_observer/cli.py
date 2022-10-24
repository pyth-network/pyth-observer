import asyncio
import yaml
import os
import sys

import click
from loguru import logger

from pyth_observer import Observer


@click.command()
def run():
    config = yaml.safe_load(open("config.yaml", "r"))
    publishers = yaml.safe_load(open("publishers.yaml", "r"))
    publishers_inverted = {v: k for k, v in publishers.items()}
    observer = Observer(config, publishers_inverted)

    asyncio.run(observer.run())
    pass


logger.remove()
logger.add(
    sys.stdout,
    serialize=(not os.environ.get("DEV_MODE")),
    level=os.environ.get("LOG_LEVEL", "INFO"),
)
