Pyth Observer
=============

Observe pyth data on-chain and apply some basic sanity checking on the published data.


Developer Setup
---------------

This requires the not yet public [pyth-client-py](https://github.com/pyth-network/pyth-client-py) library. Create a virtual environment and install all dependencies:

    pushd $(pwd)
    python3 -m venv ve
    . ve/bin/activate

Clone the `pyth-client-py` library and add it into the virtualenv:

    git clone https://github.com/pyth-network/pyth-client-py.git
    cd pyth-client-py
    python setup.py install
    cd ..

Install the pyth-observer dependencies:

    pip install -r requirements.txt


Environment Variables
---------------------

|                **Name**                  | **Default** |                  **Description**                     |
|------------------------------------------|-------------|------------------------------------------------------|
| `PYTH_OBSERVER_SLACK_WEBHOOK_URL`        |     None    | URL of the Slack incoming webhook for notifications  |
| `PYTH_OBSERVER_PRICE_DEVIATION_THRESHOLD`|     6       | Percentage between the published price and aggregate |
| `PYTH_OBSERVER_TWAP_VS_AGGREGATE_THRESHOLD` |  10      | Max TWAP and Aggregate prices should be apart        |
| `PYTH_OBSERVER_STOP_PUBLISHING_MIN_SLOTS` |    600     | Min slots before stop-publishing alert fires         |
| `PYTH_OBSERVER_STOP_PUBLISHING_MAX_SLOTS` |    1000    | Max slots behind a stop-publishing alert fires on    |


Running
-------

By default, pyth observer only logs to stderr:

    ./observer -l debug --network=mainnet

Use the `trace` log level to see exactly what is going on.

To send alerts to slack, you need to create an app and get the [incoming webhook url](https://api.slack.com/messaging/webhooks). Export it as the variable `PYTH_OBSERVER_SLACK_WEBHOOK_URL`:

    export PYTH_OBSERVER_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T0GPR2P4K/B02J164R5MF/XYZ123LMAOZOMGBBQWTF
