import asyncio
import hashlib
import os

import aiohttp
from loguru import logger

headers = {"Content-Type": "application/json"}


async def send_zenduty_alert(alert_identifier, message, resolved=False, summary=""):
    url = f"https://www.zenduty.com/api/events/{os.environ['ZENDUTY_INTEGRATION_KEY']}/"
    # Use a hash of the alert_identifier as a unique id for the alert.
    # Take the first 32 characters due to length limit of the api.
    entity_id = hashlib.sha256(alert_identifier.encode("utf-8")).hexdigest()[:32]

    alert_type = "resolved" if resolved else "critical"

    data = {
        "alert_type": alert_type,
        "message": message,
        "summary": summary,
        "entity_id": entity_id,
    }

    async with aiohttp.ClientSession() as session:
        max_retries = 30
        retries = 0
        while retries < max_retries:
            async with session.post(url, json=data, headers=headers) as response:
                if 200 <= response.status < 300:
                    return response  # Success case, return response
                elif response.status == 429:
                    retries += 1
                    if retries < max_retries:
                        sleeptime = min(30, 2**retries)
                        logger.error(
                            f"Received 429 Too Many Requests for {alert_identifier}. Retrying in {sleeptime} s..."
                        )
                        await asyncio.sleep(
                            sleeptime
                        )  # Backoff before retrying, wait upto 30s
                    else:
                        logger.error(
                            f"Failed to send Zenduty event message for {alert_identifier} after {max_retries} retries."
                        )
                        return response  # Return response after max retries
                else:
                    response_text = await response.text()
                    logger.error(
                        f"{response.status} Failed to send Zenduty event message for {alert_identifier}: {response_text}"
                    )
                    return response  # Non-retryable failure
