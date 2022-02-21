# Pyth Observer

Observe pyth data on-chain and apply some basic sanity checking on the
published data.

## Developer Setup

### Requirements
- Python 3.7
- https://pypi.org/project/pythclient/ library at [pyth-client-py](https://github.com/pyth-network/pyth-client-py).

Create a virtual environment and install all dependencies:

    pushd $(pwd)
    python3 -m venv ve
    . ve/bin/activate

Install the pyth-observer dependencies:

```shell
pip install -r requirements.txt
```

### Unit Tests

Run the unit tests by running `pytest` from the repository root.

## Environment Variables

| **Name**                                    | **Default** | **Description**                                        |
| ------------------------------------------- | ----------- | ------------------------------------------------------ |
| `PYTH_OBSERVER_SLACK_WEBHOOK_URL`           | None        | URL of the Slack incoming webhook for notifications    |
| `PYTH_OBSERVER_PRICE_DEVIATION_THRESHOLD`   | 6           | Percentage between the published price and aggregate   |
| `PYTH_OBSERVER_TWAP_VS_AGGREGATE_THRESHOLD` | 10          | Max TWAP and Aggregate prices should be apart          |
| `PYTH_OBSERVER_STOP_PUBLISHING_MIN_SLOTS`   | 600         | Min slots before stop-publishing alert fires           |
| `PYTH_OBSERVER_STOP_PUBLISHING_MAX_SLOTS`   | 1000        | Max slots behind a stop-publishing alert fires on      |
| `PYTH_OBSERVER_PRICE_DEVIATION_COINGECKO`   | 5           | Percentage between aggregate price and CoinGecko price |

## Running

By default, pyth observer only logs to stderr:

```shell
./observer.py -l debug --network=mainnet
```

Use the `trace` log level to see exactly what is going on.

To send alerts to slack, you need to create an app and get the [incoming webhook url](https://api.slack.com/messaging/webhooks). Export it as the variable `PYTH_OBSERVER_SLACK_WEBHOOK_URL`:

```shell
export PYTH_OBSERVER_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T0GPR2P4K/B02J164R5MF/XYZ123LMAOZOMGBBQWTF
```
