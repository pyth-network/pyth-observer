import requests

from throttler import throttle


# We have an attester that sends the prices to wormhole to be verified.
# Currently it sends prices to wormhole every one minute, due to costs.
# We can increase the frequency of the attester once we're live on pythnet.
@throttle(rate_limit=1, period=60)
async def get_crosschain_prices(cluster):
    price_feed_ids = requests.get(
        f"https://xc-{cluster}.pyth.network/api/price_feed_ids"
    ).json()
    query_params = "ids[]=" + "&ids[]=".join(price_feed_ids)
    latest_price_feeds = requests.get(
        f"https://xc-{cluster}.pyth.network/api/latest_price_feeds?{query_params}"
    ).json()
    # return a dictionary of id -> {price, conf, expo} for fast lookup
    return {
        data["id"]: {
            "price": int(data["price"]) * 10 ** data["expo"],
            "conf": int(data["conf"]) * 10 ** data["expo"],
            "publish_time": data["publish_time"],
            "prev_publish_time": data["prev_publish_time"],
        }
        for data in latest_price_feeds
    }
