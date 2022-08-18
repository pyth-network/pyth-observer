import os
import json

import requests

from throttler import throttle


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_crosschain_symbol_to_pubkey_mapping():
    with open(f"{ROOT_DIR}/crosschain_mapping.json") as json_file:
        data = json.load(json_file)

    return data


symbol_to_pubkey_mapping = get_crosschain_symbol_to_pubkey_mapping()

# We have an attester that sends the prices to wormhole to be verified. Currently it sends prices to wormhole every one minute, due to costs. We can increase the frequency of the attester once we're live on pythnet.
@throttle(rate_limit=1, period=60)
async def get_crosschain_prices():
    query_params = "ids[]=" + "&ids[]=".join(symbol_to_pubkey_mapping.values())
    x = requests.get(
        f"https://prices.devnet.pyth.network/api/latest_price_feeds?{query_params}"
    )
    # return a dictionary of id -> {price, conf, expo} for fast lookup
    return {
        data["id"]: {
            "price": int(data["price"]) * 10 ** data["expo"],
            "conf": int(data["conf"]) * 10 ** data["expo"],
            "publish_time": data["publish_time"],
            "prev_publish_time": data["prev_publish_time"],
        }
        for data in x.json()
    }
