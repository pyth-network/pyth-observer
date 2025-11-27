import asyncio
import os
import sys
from typing import Any, Dict

import click
import yaml
from loguru import logger
from prometheus_client import start_http_server

from pyth_observer import Observer, Publisher
from pyth_observer.health_server import start_health_server
from pyth_observer.models import ContactInfo


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
    "--prometheus-port",
    help="Port number for Prometheus metrics endpoint",
    envvar="PROMETHEUS_PORT",
    default="9001",
)
def run(
    config: str, publishers: str, coingecko_mapping: str, prometheus_port: str
) -> None:
    config_: Dict[str, Any] = yaml.safe_load(open(config, "r"))  # type: ignore[assignment]
    # Load publishers YAML file and convert to dictionary of Publisher instances
    publishers_raw: list[Dict[str, Any]] = yaml.safe_load(open(publishers, "r"))  # type: ignore[assignment]
    publishers_: Dict[str, Publisher] = {
        publisher["key"]: Publisher(
            key=publisher["key"],
            name=publisher["name"],
            contact_info=(
                ContactInfo(**publisher["contact_info"])
                if "contact_info" in publisher
                else None
            ),
        )
        for publisher in publishers_raw
    }
    coingecko_mapping_: Dict[str, Any] = yaml.safe_load(open(coingecko_mapping, "r"))  # type: ignore[assignment]
    observer = Observer(
        config_,
        publishers_,
        coingecko_mapping_,
    )

    start_http_server(int(prometheus_port))

    async def main() -> None:
        asyncio.create_task(start_health_server())
        await observer.run()

    asyncio.run(main())


logger.remove()
logger.add(
    sys.stdout,
    serialize=(not os.environ.get("DEV_MODE")),
    level=os.environ.get("LOG_LEVEL", "INFO"),
)
