#!/usr/bin/env python3
"""
Script to build CoinGecko mapping file from Pyth Hermes API and CoinGecko API.

This script:
1. Fetches all price feeds from Pyth Hermes API
2. Extracts base symbols (especially for Crypto assets)
3. Gets CoinGecko coin list
4. Matches using Pyth description (most reliable) and symbol matching
5. Generates the mapping file with warnings for non-100% matches
"""

import json
import sys
import time
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

import requests
from loguru import logger
from pycoingecko import CoinGeckoAPI

# Configure logger
logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
)

HERMES_API_URL = "https://hermes.pyth.network/v2/price_feeds"
COINGECKO_API = CoinGeckoAPI()

# Known mappings for validation only (not used in matching logic)
# Format: Pyth symbol -> CoinGecko ID
KNOWN_MAPPINGS = {
    "Crypto.BTC/USD": "bitcoin",
    "Crypto.ETH/USD": "ethereum",
    "Crypto.USDT/USD": "tether",
    "Crypto.USDC/USD": "usd-coin",
    "Crypto.BNB/USD": "binancecoin",
    "Crypto.SOL/USD": "solana",
    "Crypto.XRP/USD": "ripple",
    "Crypto.DOGE/USD": "dogecoin",
    "Crypto.ADA/USD": "cardano",
    "Crypto.AVAX/USD": "avalanche-2",
    "Crypto.DOT/USD": "polkadot",
    "Crypto.MATIC/USD": "matic-network",
    "Crypto.LINK/USD": "chainlink",
    "Crypto.UNI/USD": "uniswap",
    "Crypto.ATOM/USD": "cosmos",
    "Crypto.LTC/USD": "litecoin",
    "Crypto.BCH/USD": "bitcoin-cash",
    "Crypto.XLM/USD": "stellar",
    "Crypto.ALGO/USD": "algorand",
    "Crypto.VET/USD": "vechain",
    "Crypto.ICP/USD": "internet-computer",
    "Crypto.FIL/USD": "filecoin",
    "Crypto.TRX/USD": "tron",
    "Crypto.ETC/USD": "ethereum-classic",
    "Crypto.EOS/USD": "eos",
    "Crypto.AAVE/USD": "aave",
    "Crypto.MKR/USD": "maker",
    "Crypto.COMP/USD": "compound-governance-token",
    "Crypto.YFI/USD": "yearn-finance",
    "Crypto.SNX/USD": "havven",
    "Crypto.SUSHI/USD": "sushi",
    "Crypto.CRV/USD": "curve-dao-token",
    "Crypto.1INCH/USD": "1inch",
    "Crypto.ENJ/USD": "enjincoin",
    "Crypto.BAT/USD": "basic-attention-token",
    "Crypto.ZRX/USD": "0x",
    "Crypto.MANA/USD": "decentraland",
    "Crypto.SAND/USD": "the-sandbox",
    "Crypto.GALA/USD": "gala",
    "Crypto.AXS/USD": "axie-infinity",
    "Crypto.CHZ/USD": "chiliz",
    "Crypto.FLOW/USD": "flow",
    "Crypto.NEAR/USD": "near",
    "Crypto.FTM/USD": "fantom",
    "Crypto.HBAR/USD": "hedera-hashgraph",
    "Crypto.EGLD/USD": "elrond-erd-2",
    "Crypto.THETA/USD": "theta-token",
    "Crypto.ZIL/USD": "zilliqa",
    "Crypto.IOTA/USD": "iota",
    "Crypto.ONE/USD": "harmony",
    "Crypto.WAVES/USD": "waves",
    "Crypto.XTZ/USD": "tezos",
    "Crypto.DASH/USD": "dash",
    "Crypto.ZEC/USD": "zcash",
    "Crypto.XMR/USD": "monero",
    "Crypto.ANC/USD": "anchor-protocol",
    "Crypto.APE/USD": "apecoin",
    "Crypto.ATLAS/USD": "star-atlas",
    "Crypto.AUST/USD": "anchorust",
    "Crypto.BETH/USD": "binance-eth",
    "Crypto.BRZ/USD": "brz",
    "Crypto.BUSD/USD": "binance-usd",
    "Crypto.C98/USD": "coin98",
    "Crypto.COPE/USD": "cope",
    "Crypto.CUSD/USD": "celo-dollar",
    "Crypto.FIDA/USD": "bonfida",
    "Crypto.FTT/USD": "ftx-token",
    "Crypto.GMT/USD": "stepn",
    "Crypto.GOFX/USD": "goosefx",
    "Crypto.HXRO/USD": "hxro",
    "Crypto.INJ/USD": "injective-protocol",
    "Crypto.JET/USD": "jet",
    "Crypto.LUNA/USD": "terra-luna-2",
    "Crypto.LUNC/USD": "terra-luna",
    "Crypto.MER/USD": "mercurial",
    "Crypto.MIR/USD": "mirror-protocol",
    "Crypto.MNGO/USD": "mango-markets",
    "Crypto.MSOL/USD": "msol",
    "Crypto.ORCA/USD": "orca",
    "Crypto.PAI/USD": "parrot-usd",
    "Crypto.PORT/USD": "port-finance",
    "Crypto.RAY/USD": "raydium",
    "Crypto.SBR/USD": "saber",
    "Crypto.SCNSOL/USD": "socean-staked-sol",
    "Crypto.SLND/USD": "solend",
    "Crypto.SNY/USD": "synthetify-token",
    "Crypto.SRM/USD": "serum",
    "Crypto.STEP/USD": "step-finance",
    "Crypto.STSOL/USD": "lido-staked-sol",
    "Crypto.TUSD/USD": "true-usd",
    "Crypto.USTC/USD": "terrausd",
    "Crypto.VAI/USD": "vai",
    "Crypto.XVS/USD": "venus",
    "Crypto.ZBC/USD": "zebec-protocol",
}


def normalize_symbol(symbol: str) -> str:
    """Normalize symbol - only remove suffixes separated by / or -."""
    original = symbol.upper().strip()
    # Only remove suffixes if they're separated by / or -
    for suffix in ["-USD", "/USD", "-USDT", "/USDT", "-USDC", "/USDC"]:
        if original.endswith(suffix):
            return original[: -len(suffix)].strip()
    return original


def is_non_canonical(coin_id: str, coin_name: str) -> bool:
    """Check if coin is bridged/peg/wrapped (non-canonical)."""
    text = (coin_id + " " + coin_name).lower()
    return any(
        term in text
        for term in ["bridged", "peg", "wrapped", "wormhole", "binance-peg", "mapped-"]
    )


def normalize_text(text: str) -> str:
    """Normalize text for matching (remove separators, lowercase)."""
    return (
        text.lower().replace("-", "").replace("_", "").replace(" ", "").replace("/", "")
    )


def match_by_description(
    description: str, coins: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Match coin using Pyth description (most reliable method).
    Description format: "COIN_NAME / US DOLLAR" or similar.
    """
    if not description:
        return None

    # Extract words from description (e.g., "UNISWAP / US DOLLAR" -> ["uniswap"])
    # Get the first significant word (usually the coin name)
    desc_parts = description.upper().split("/")[0].strip()  # Get part before "/"
    desc_words = [
        w.replace("-", "").replace("_", "").lower()
        for w in desc_parts.replace("-", " ").split()
        if len(w) > 2 and w.lower() not in ["usd", "us", "dollar", "euro", "eur", "and"]
    ]

    # Also create combined version for multi-word matches (e.g., "USD COIN" -> "usdcoin")
    desc_combined = "".join(desc_words)

    # First pass: find exact matches (prefer canonical)
    canonical_matches = []
    non_canonical_matches = []

    for coin in coins:
        coin_id_norm = normalize_text(coin["id"])
        coin_name_norm = normalize_text(coin["name"])
        is_non_can = is_non_canonical(coin["id"], coin["name"])

        # Check exact word match with coin ID (most reliable)
        for word in desc_words:
            if word == coin_id_norm:
                if is_non_can:
                    non_canonical_matches.append(coin)
                else:
                    # Return immediately for canonical exact match
                    return coin

        # Check combined description match
        if desc_combined == coin_id_norm:
            if is_non_can:
                non_canonical_matches.append(coin)
            else:
                canonical_matches.append(coin)

        # Check if coin name matches
        if coin_name_norm in desc_combined or any(
            word == coin_name_norm for word in desc_words
        ):
            if is_non_can:
                non_canonical_matches.append(coin)
            else:
                canonical_matches.append(coin)

    # Return first canonical match, or first non-canonical if no canonical found
    if canonical_matches:
        return canonical_matches[0]
    if non_canonical_matches:
        return non_canonical_matches[0]

    return None


def score_coin(symbol: str, coin: Dict[str, Any], description: str = "") -> float:
    """Score a coin match. Higher is better."""
    coin_id = coin["id"].lower()
    coin_name = coin["name"].lower()
    symbol_lower = symbol.lower()

    # Heavy penalty for non-canonical coins
    if is_non_canonical(coin_id, coin_name):
        base = 0.1
    else:
        base = 1.0

    # Penalty for generic names (name == symbol)
    if coin_name == symbol_lower:
        base *= 0.3

    # Bonus if description matches
    if description:
        desc_norm = normalize_text(description)
        coin_id_norm = normalize_text(coin_id)
        if coin_id_norm in desc_norm:
            return base + 0.5
        coin_name_norm = normalize_text(coin_name)
        if coin_name_norm in desc_norm:
            return base + 0.3

    # Similarity bonus
    similarity = SequenceMatcher(None, symbol_lower, coin_name).ratio()
    return base * (0.5 + similarity * 0.5)


def find_coingecko_match(
    pyth_base: str,
    coin_lookup: Dict[str, Any],
    description: str = "",
) -> Tuple[Optional[str], float, str]:
    """Find the best CoinGecko match for a Pyth base symbol.

    Returns:
        Tuple of (coin_id, confidence_score, match_type)
    """
    normalized = normalize_symbol(pyth_base)

    # Strategy 1: Exact symbol match
    if normalized in coin_lookup["by_symbol"]:
        coins = coin_lookup["by_symbol"][normalized]

        if len(coins) == 1:
            return coins[0]["id"], 1.0, "exact_symbol"

        # Try description matching first (most reliable)
        desc_match = match_by_description(description, coins)
        if desc_match:
            return desc_match["id"], 1.0, "exact_symbol"

        # Score all coins and pick best
        best_coin = None
        best_score = -1.0

        for coin in coins:
            score = score_coin(normalized, coin, description)
            if score > best_score:
                best_score = score
                best_coin = coin

        if best_coin:
            return best_coin["id"], 1.0, "exact_symbol"

    # Strategy 2: Fuzzy match on symbol and coin ID
    best_coin = None
    best_score = 0.0

    for coin in coin_lookup["all_coins"]:
        coin_symbol = coin["symbol"].upper()
        coin_id = coin["id"].upper()

        # Check exact match with coin ID first (most reliable)
        if normalized == coin_id:
            return coin["id"], 1.0, "fuzzy_symbol"

        # Check similarity with both symbol and ID, prefer ID matches
        symbol_score = SequenceMatcher(None, normalized, coin_symbol).ratio()
        id_score = SequenceMatcher(None, normalized, coin_id).ratio()

        # Use the better of the two scores, with slight preference for ID matches
        score = max(symbol_score, id_score * 1.01)  # 1% bonus for ID matches

        if score > best_score and score >= 0.7:
            best_score = score
            best_coin = coin

    if best_coin:
        # If we found an exact ID match, return 100% confidence
        if normalized == best_coin["id"].upper():
            return best_coin["id"], 1.0, "fuzzy_symbol"
        return best_coin["id"], best_score, "fuzzy_symbol"

    return None, 0.0, "no_match"


def validate_known_mappings(
    mapping: Dict[str, str], coin_lookup: Dict[str, Any]
) -> Tuple[bool, List[str]]:
    """Validate that known mappings match the generated mapping."""
    errors = []

    for symbol, expected_id in KNOWN_MAPPINGS.items():
        if symbol in mapping:
            actual_id = mapping[symbol]
            if actual_id != expected_id:
                expected_coin = coin_lookup["by_id"].get(expected_id, {})
                actual_coin = coin_lookup["by_id"].get(actual_id, {})
                expected_name = expected_coin.get("name", expected_id)
                actual_name = actual_coin.get("name", actual_id)

                errors.append(
                    f"❌ VALIDATION FAILED: {symbol} mapped to '{actual_id}' ({actual_name}) "
                    f"but expected '{expected_id}' ({expected_name})"
                )

    return len(errors) == 0, errors


def get_pyth_price_feeds() -> List[Dict[str, Any]]:
    """Fetch all price feeds from Pyth Hermes API."""
    logger.info(f"Fetching price feeds from {HERMES_API_URL}...")
    try:
        response = requests.get(HERMES_API_URL, timeout=30)
        response.raise_for_status()
        feeds = response.json()
        logger.info(f"Fetched {len(feeds)} price feeds from Hermes API")
        time.sleep(1)  # Rate limit protection
        return feeds
    except Exception as e:
        logger.error(f"Failed to fetch price feeds from Hermes API: {e}")
        sys.exit(1)


def get_coingecko_coin_list() -> Dict[str, Any]:
    """Fetch CoinGecko coin list and create lookup dictionaries."""
    logger.info("Fetching CoinGecko coin list...")
    try:
        coins = COINGECKO_API.get_coins_list()
        logger.info(f"Fetched {len(coins)} coins from CoinGecko")
        time.sleep(1)  # Rate limit protection

        by_id = {coin["id"]: coin for coin in coins}
        by_symbol = {}
        for coin in coins:
            symbol_upper = coin["symbol"].upper()
            if symbol_upper not in by_symbol:
                by_symbol[symbol_upper] = []
            by_symbol[symbol_upper].append(coin)

        return {"by_id": by_id, "by_symbol": by_symbol, "all_coins": coins}
    except Exception as e:
        logger.error(f"Failed to fetch CoinGecko coin list: {e}")
        sys.exit(1)


def get_hermes_prices(symbol_to_feed_id: Dict[str, str]) -> Dict[str, float]:
    """Get latest prices from Hermes API for mapped symbols."""
    logger.info("Fetching prices from Hermes API...")
    hermes_prices = {}

    try:
        # Get price updates for all feeds in batches
        feed_ids = list(symbol_to_feed_id.values())
        batch_size = 50

        for i in range(0, len(feed_ids), batch_size):
            batch = feed_ids[i : i + batch_size]
            query_string = "?" + "&".join(f"ids[]={feed_id}" for feed_id in batch)
            url = f"{HERMES_API_URL.replace('/price_feeds', '/updates/price/latest')}{query_string}"

            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            for feed_data in data.get("parsed", []):
                feed_id = feed_data.get("id")
                price_info = feed_data.get("price", {})
                if price_info:
                    price_str = price_info.get("price", "0")
                    expo = price_info.get("expo", 0)
                    try:
                        price = int(price_str)
                        # Convert to actual price: price * 10^expo
                        actual_price = price * (10**expo)
                        if actual_price > 0:
                            hermes_prices[feed_id] = actual_price
                    except (ValueError, TypeError):
                        continue

            time.sleep(1)  # Rate limit protection - wait 1s after each batch

        logger.info(f"Fetched {len(hermes_prices)} prices from Hermes API")
    except Exception as e:
        logger.warning(f"Failed to fetch Hermes prices: {e}")

    return hermes_prices


def get_coingecko_prices(mapping: Dict[str, str]) -> Dict[str, float]:
    """Get prices from CoinGecko for mapped coins."""
    logger.info("Fetching prices from CoinGecko...")
    coingecko_prices = {}

    try:
        # Get unique coin IDs
        coin_ids = list(set(mapping.values()))

        # CoinGecko API can handle up to ~1000 IDs at once, but let's batch to be safe
        batch_size = 200
        for i in range(0, len(coin_ids), batch_size):
            batch = coin_ids[i : i + batch_size]
            prices = COINGECKO_API.get_price(
                ids=batch, vs_currencies="usd", include_last_updated_at=False
            )

            for coin_id, price_data in prices.items():
                if "usd" in price_data:
                    coingecko_prices[coin_id] = price_data["usd"]

            time.sleep(2)  # Rate limit protection - wait 1s after each batch

        logger.info(f"Fetched {len(coingecko_prices)} prices from CoinGecko")
    except Exception as e:
        logger.warning(f"Failed to fetch CoinGecko prices: {e}")

    return coingecko_prices


def validate_prices(
    mapping: Dict[str, str],
    pyth_feeds: List[Dict[str, Any]],
    max_deviation_percent: float = 10.0,
) -> Tuple[List[str], List[str], Dict[str, Dict[str, float]]]:
    """
    Validate prices by comparing Hermes and CoinGecko prices.
    Returns tuple of (warnings, price_mismatch_symbols, price_details) for significant price differences.
    price_details is a dict mapping symbol to {'hermes_price': float, 'coingecko_price': float, 'deviation': float}
    """
    warnings = []
    price_mismatch_symbols = []
    price_details = {}

    # Map symbols to feed IDs
    symbol_to_feed_id = {}
    for feed in pyth_feeds:
        attrs = feed.get("attributes", {})
        if attrs.get("asset_type") == "Crypto":
            symbol = attrs.get("symbol", "")
            if symbol and symbol in mapping:
                symbol_to_feed_id[symbol] = feed.get("id")

    if not symbol_to_feed_id:
        return warnings, price_mismatch_symbols, price_details

    # Get prices from both sources
    hermes_prices = get_hermes_prices(symbol_to_feed_id)
    coingecko_prices = get_coingecko_prices(mapping)

    # Compare prices
    compared = 0
    mismatches = 0
    for symbol, coin_id in mapping.items():
        feed_id = symbol_to_feed_id.get(symbol)

        if feed_id is None:
            continue

        hermes_price = hermes_prices.get(feed_id)
        cg_price = coingecko_prices.get(coin_id)

        # Skip if either price is missing
        if not hermes_price or not cg_price:
            continue

        # Skip if CoinGecko price is 0 (coin might not be actively traded)
        if cg_price <= 0:
            continue

        compared += 1
        deviation = abs(hermes_price - cg_price) / cg_price * 100

        # Only warn if deviation is significant and price is meaningful
        if deviation > max_deviation_percent and cg_price >= 0.01:
            mismatches += 1
            warnings.append(
                f"⚠️  {symbol} ({coin_id}): Price mismatch - Hermes: ${hermes_price:,.5f}, "
                f"CoinGecko: ${cg_price:,.5f} (deviation: {deviation:.2f}%)"
            )
            price_mismatch_symbols.append(symbol)
            price_details[symbol] = {
                "hermes_price": hermes_price,
                "coingecko_price": cg_price,
                "deviation": deviation,
            }
            logger.warning(
                f"  Price mismatch: {symbol} ({coin_id}) - "
                f"Hermes: ${hermes_price:,.5f} | CoinGecko: ${cg_price:,.5f} | "
                f"Deviation: {deviation:.2f}%"
            )

    if compared > 0:
        logger.info(f"Compared prices for {compared} symbols")
        if mismatches > 0:
            logger.warning(
                f"Found {mismatches} price mismatches (deviation > {max_deviation_percent}%)"
            )

    return warnings, price_mismatch_symbols, price_details


def build_mapping(
    validate_prices_flag: bool = False, max_deviation: float = 10.0
) -> Tuple[
    Dict[str, str], Dict[str, float], List[str], List[str], Dict[str, Dict[str, float]]
]:
    """Build the CoinGecko mapping from Pyth feeds.

    Returns:
        Tuple of (mapping, confidence_scores, warnings, price_mismatch_symbols, price_details)
        price_details maps symbol to {'hermes_price': float, 'coingecko_price': float, 'deviation': float}
    """
    pyth_feeds = get_pyth_price_feeds()
    coin_lookup = get_coingecko_coin_list()

    # Extract Crypto symbols with base and descriptions
    crypto_data = {}
    for feed in pyth_feeds:
        attrs = feed.get("attributes", {})
        if attrs.get("asset_type") == "Crypto":
            symbol = attrs.get("symbol", "")
            base = attrs.get("base", "")
            quote_currency = attrs.get("quote_currency", "")

            if quote_currency != "USD":
                continue

            if symbol and base:
                if symbol not in crypto_data:
                    crypto_data[symbol] = {
                        "base": base,
                        "description": attrs.get("description", ""),
                    }

    logger.info(f"Found {len(crypto_data)} unique Crypto symbols quoted in USD")

    # Build mapping
    mapping = {}
    confidence_scores = {}  # Track confidence scores for each symbol
    warnings = []

    for symbol in sorted(crypto_data.keys()):
        base = crypto_data[symbol]["base"]
        description = crypto_data[symbol]["description"]
        api_id, score, match_type = find_coingecko_match(base, coin_lookup, description)

        if api_id:
            mapping[symbol] = api_id
            confidence_scores[symbol] = score
            if score < 1.0:
                warnings.append(
                    f"⚠️  {symbol}: Match confidence {score:.2%} ({match_type}) - "
                    f"matched to '{api_id}'"
                )
        else:
            warnings.append(f"❌ {symbol}: No match found in CoinGecko")

    # Validate against known mappings
    is_valid, validation_errors = validate_known_mappings(mapping, coin_lookup)
    if not is_valid:
        logger.error("\n" + "=" * 60)
        logger.error(
            "VALIDATION FAILED: Known mappings do not match generated mappings!"
        )
        logger.error("=" * 60)
        for error in validation_errors:
            logger.error(error)
        logger.error("\nThis indicates the matching algorithm needs improvement.")
        logger.error(
            "Please fix the matching logic before using the generated mapping."
        )
        return mapping, confidence_scores, warnings + validation_errors, []

    logger.info("✓ Validation passed: All known mappings match generated mappings")

    # Validate prices if requested
    price_mismatch_symbols = []
    price_details = {}
    if validate_prices_flag:
        price_warnings, price_mismatch_symbols, price_details = validate_prices(
            mapping, pyth_feeds, max_deviation
        )
        warnings.extend(price_warnings)

    return mapping, confidence_scores, warnings, price_mismatch_symbols, price_details


def load_existing_mapping(file_path: str) -> Dict[str, str]:
    """Load existing mapping file if it exists."""
    try:
        with open(file_path, "r") as f:
            content = f.read().strip()
            if content.startswith("{"):
                data = json.loads(content)
                # Handle both old format (dict) and new format (string)
                if data and isinstance(list(data.values())[0], dict):
                    # Convert old format to new format
                    return {
                        k: v.get("api", v.get("market", "")) for k, v in data.items()
                    }
                return data
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, (KeyError, IndexError)):
        logger.warning(f"Could not parse existing mapping file {file_path}")
    return {}


def compare_mappings(
    new_mapping: Dict[str, str], existing_mapping: Dict[str, str]
) -> List[str]:
    """Compare new mapping with existing and return differences."""
    differences = []
    all_symbols = set(list(new_mapping.keys()) + list(existing_mapping.keys()))

    for symbol in all_symbols:
        new_entry = new_mapping.get(symbol)
        existing_entry = existing_mapping.get(symbol)

        if new_entry and existing_entry:
            if new_entry != existing_entry:
                differences.append(
                    f"  {symbol}: Changed from '{existing_entry}' to '{new_entry}'"
                )
        elif new_entry and not existing_entry:
            differences.append(f"  {symbol}: New entry -> '{new_entry}'")
        elif existing_entry and not new_entry:
            differences.append(f"  {symbol}: Removed (was '{existing_entry}')")

    return differences


def main() -> int:
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Build CoinGecko mapping file from Pyth Hermes API"
    )
    parser.add_argument(
        "-o",
        "--output",
        default="coingecko_mapping.json",
        help="Output file path (default: coingecko_mapping.json)",
    )
    parser.add_argument(
        "-e", "--existing", help="Path to existing mapping file to compare against"
    )
    parser.add_argument(
        "--no-validate-prices",
        action="store_true",
        help="Skip price validation (by default, prices are validated)",
    )
    parser.add_argument(
        "--max-price-deviation",
        type=float,
        default=1.0,
        help="Maximum price deviation percentage to warn about (default: 1.0%%)",
    )
    args = parser.parse_args()

    logger.info("Starting CoinGecko mapping generation...")

    existing_mapping = {}
    if args.existing:
        existing_mapping = load_existing_mapping(args.existing)
        if existing_mapping:
            logger.info(
                f"Loaded {len(existing_mapping)} existing mappings from {args.existing}"
            )

    (
        mapping,
        confidence_scores,
        warnings,
        price_mismatch_symbols,
        price_details,
    ) = build_mapping(
        validate_prices_flag=not args.no_validate_prices,
        max_deviation=args.max_price_deviation,
    )

    # Check if validation failed
    validation_failed = any("VALIDATION FAILED" in w for w in warnings)
    if validation_failed:
        logger.error("\nExiting with error code due to validation failures.")
        return 1

    # Filter out symbols with low confidence (< 1.0) or price mismatches
    excluded_symbols = set()
    excluded_low_confidence = []
    excluded_price_mismatch = []

    # Find symbols with confidence < 1.0
    for symbol, score in confidence_scores.items():
        if score < 1.0:
            excluded_symbols.add(symbol)
            excluded_low_confidence.append(symbol)

    # Find symbols with price mismatches
    for symbol in price_mismatch_symbols:
        excluded_symbols.add(symbol)
        excluded_price_mismatch.append(symbol)

    # Create filtered mapping (only high confidence, no price mismatches)
    filtered_mapping = {
        symbol: coin_id
        for symbol, coin_id in mapping.items()
        if symbol not in excluded_symbols
    }

    # Log excluded entries for manual review
    if excluded_low_confidence or excluded_price_mismatch:
        logger.warning("\n" + "=" * 60)
        logger.warning("EXCLUDED ENTRIES (for manual review):")
        logger.warning("=" * 60)

        if excluded_low_confidence:
            logger.warning(
                f"\n⚠️  Low confidence matches (< 100%) - {len(excluded_low_confidence)} entries:"
            )
            for symbol in sorted(excluded_low_confidence):
                coin_id = mapping.get(symbol, "N/A")
                score = confidence_scores.get(symbol, 0.0)
                logger.warning(f"  {symbol}: {coin_id} (confidence: {score:.2%})")

        if excluded_price_mismatch:
            logger.warning(
                f"\n⚠️  Price mismatches - {len(excluded_price_mismatch)} entries:"
            )
            for symbol in sorted(excluded_price_mismatch):
                coin_id = mapping.get(symbol, "N/A")
                if symbol in price_details:
                    details = price_details[symbol]
                    hermes_price = details["hermes_price"]
                    cg_price = details["coingecko_price"]
                    deviation = details["deviation"]
                    logger.warning(
                        f"  {symbol} ({coin_id}): "
                        f"Hermes: ${hermes_price:,.5f} | "
                        f"CoinGecko: ${cg_price:,.5f} | "
                        f"Deviation: {deviation:.2f}%"
                    )
                else:
                    logger.warning(f"  {symbol}: {coin_id}")

        # Output excluded entries as JSON for easy manual addition
        excluded_mapping = {
            symbol: mapping[symbol] for symbol in excluded_symbols if symbol in mapping
        }
        if excluded_mapping:
            excluded_file = args.output.replace(".json", "_excluded.json")
            with open(excluded_file, "w") as f:
                json.dump(excluded_mapping, f, indent=2, sort_keys=True)
            logger.warning(
                f"\n📝 Excluded entries saved to {excluded_file} for manual review"
            )
        logger.warning("=" * 60 + "\n")

    # Output results
    logger.info(f"\n{'=' * 60}")
    logger.info(f"Generated mapping for {len(mapping)} symbols")
    if excluded_symbols:
        logger.info(
            f"Excluded {len(excluded_symbols)} entries (low confidence or price mismatch)"
        )
        logger.info(f"Final mapping contains {len(filtered_mapping)} symbols")
    logger.info(f"{'=' * 60}\n")

    # Compare with existing if provided
    if existing_mapping:
        differences = compare_mappings(filtered_mapping, existing_mapping)
        if differences:
            logger.info(f"Found {len(differences)} differences from existing mapping:")
            for diff in differences:
                logger.info(diff)
            logger.info("")

    # Print warnings (excluding excluded entries from warnings count)
    other_warnings = [
        w
        for w in warnings
        if not any(symbol in w for symbol in excluded_symbols)
        and "VALIDATION FAILED" not in w
    ]
    if other_warnings:
        logger.warning(f"Found {len(other_warnings)} other warnings:")
        for warning in other_warnings:
            logger.warning(warning)
        logger.info("")

    # Output JSON (only high confidence, no price mismatches)
    with open(args.output, "w") as f:
        json.dump(filtered_mapping, f, indent=2, sort_keys=True)

    logger.info(f"✓ Mapping saved to {args.output}")

    # Summary
    fuzzy_matches = len(excluded_low_confidence)
    no_matches = len([w for w in warnings if "No match found" in w])
    exact_matches = len(filtered_mapping)

    logger.info(f"\nSummary:")
    logger.info(f"  Total symbols processed: {len(mapping)}")
    logger.info(f"  Included in final mapping: {exact_matches} (exact matches only)")
    logger.info(f"  Excluded - low confidence: {fuzzy_matches}")
    logger.info(f"  Excluded - price mismatch: {len(excluded_price_mismatch)}")
    logger.info(f"  No matches found: {no_matches}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
