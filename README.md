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

| **Name**                                    | **Default** | **Description**                                          |
| ------------------------------------------- | ----------- | -------------------------------------------------------- |
| `PYTH_OBSERVER_SLACK_WEBHOOK_URL`           | None        | URL of the Slack incoming webhook for notifications      |
| `PYTH_OBSERVER_PRICE_DEVIATION_THRESHOLD`   | 6           | Percentage between the published price and aggregate     |
| `PYTH_OBSERVER_TWAP_VS_AGGREGATE_THRESHOLD` | 10          | Max TWAP and Aggregate prices should be apart            |
| `PYTH_OBSERVER_STOP_PUBLISHING_MIN_SLOTS`   | 600         | Min slots before stop-publishing alert fires             |
| `PYTH_OBSERVER_STOP_PUBLISHING_MAX_SLOTS`   | 1000        | Max slots behind a stop-publishing alert fires on        |
| `PYTH_OBSERVER_PRICE_DEVIATION_COINGECKO`   | 5           | Percentage between aggregate price and CoinGecko price   |
| `PYTH_OBSERVER_PRICE_DEVIATION_CROSSCHAIN`  | 5           | Percentage between aggregate price and cross-chain price |

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

## Build automation

To help with both automated builds and documenting the exact build process,
there is a Makefile and a github actions Continuous Integration job.

The github action will run on each commit pushed to confirm that all tests
are passing and there are no style-guide issues.

The Makefile provides several convenience functions:

| **Command**   | **Description**                                            |
| ------------- | ---------------------------------------------------------- |
| `make lint`   | Checks the code for style-guide and syntax issues          |
| `make test`   | Runs the internal unit test suite                          |
| `make cover`  | Runs the test suite, but also generates a report of the code coverage |
| `make run`    | Runs the pyth observer on devnet, logging to stderr        |

## Notification modules

The pyth observer ships with two sample notification modules, one for logging
to stderr and one for sending to slack.  One or more instances of the
available notifier modules can be selected from the commandline using the
`--notifier`` commandline arg.

The default is to use the `logger` module unless there is a
`--slack-webhook-url`, in which case it defaults to using the `slack` module.

More than one notification module can be enabled simultaneously and each
module can loaded multiple times (useful if you want to notify more than one
slack channel)

| **Notifier Module**               | **Module Args**                                             |
| --------------------------------- | ----------------------------------------------------------- |
| `pyth_observer.notifiers.logger`  | none                                                        |
| `pyth_observer.notifiers.slack`   | The URL of the Slack incoming webhook for this notification |

The args to pass to the notifier module are separated from the module name with
an equals ("=") sign

e.g:
```shell
./observer.py --network=testnet --notifier=pyth_observer.notifiers.slack=https://hooks.slack.com/services/T0GPR2P4K/B02J164R5MF/XYZ123LMAOZOMGBBQWTF
```

## Writing custom notifiers

The pyth observer is intended to be flexible and allow you to integrate with
any monitoring, alerting or logging system you might be using.

The name of the notifier that is passed to the ``--notifier`` arg is a full
python module path, which is then loaded using the normal Python search
process.  The two included implementations can be used as a starting points
for writing custom notifiers.

Each module has a `Notifier` class inside it, which is instantiated for each
separate mention from a ``--notifier`` arg - with any args passed on the
command line passed into the object initializer.

Adding a new `Foo` notifier can be as simple as dropping a file ``Foo.py``
into this directory and then adding ``--notifier=Foo=optionalargs`` to the
commandline you start ``./observer.py`` with.
