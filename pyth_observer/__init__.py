from typing import Tuple

from pythclient.solana import (
    SOLANA_DEVNET_WS_ENDPOINT,
    SOLANA_DEVNET_HTTP_ENDPOINT,
    SOLANA_TESTNET_WS_ENDPOINT,
    SOLANA_TESTNET_HTTP_ENDPOINT,
    SOLANA_MAINNET_WS_ENDPOINT,
    SOLANA_MAINNET_HTTP_ENDPOINT,
)

from .dns import get_key  # noqa

PYTHTEST_HTTP_ENDPOINT = "https://api.pythtest.pyth.network/"
PYTHTEST_WS_ENDPOINT = "wss://api.pythtest.pyth.network/"
PYTHNET_HTTP_ENDPOINT = "https://pythnet.rpcpool.com/"
PYTHNET_WS_ENDPOINT = "wss://pythnet.rpcpool.com/"


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
