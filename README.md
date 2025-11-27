# Pyth Observer

Observe Pyth on-chain price feeds and run sanity checks on the data.

## Usage

Container images are available at https://github.com/pyth-network/pyth-observer/pkgs/container/pyth-observer

To run Observer locally, you will need: 
- Python 3.11 ([pyenv](https://github.com/pyenv/pyenv) is a nice way to manage Python installs, and once installed will automatically set the version to 3.11 for this project dir via the `.python-version` file).
- [Poetry] v2.1.4 (https://python-poetry.org), which handles package and virtualenv management. 

Install dependencies and run the service:
```sh
$ poetry env use $(which python) # point Poetry to the pyenv python shim
$ poetry install
$ poetry run pyth-observe --config sample.config.yaml --publishers sample.publishers.yaml --coingecko-mapping sample.coingecko.yaml
```

Use `poetry run pyth-observer --help` for documentation on arguments and environment variables.

To run tests, use `poetry run pytest`.

## Configuration

See `sample.config.yaml` for configuration options.

Event types are configured via environment variables:

- `DatadogEvent`

  - `DATADOG_EVENT_SITE` - Division where Datadog account is registered
  - `DATADOG_EVENT_API_KEY` - API key used to send requests to Datadog API

- `LogEvent`
  - `LOG_EVENT_LEVEL` - Level to log messages at

- `TelegramEvent`
  - `TELEGRAM_BOT_TOKEN` - API token for the Telegram bot
  - `OPEN_ALERTS_FILE` - Path to local file used for persisting open alerts

- `ZendutyEvent`
  - `ZENDUTY_INTEGRATION_KEY` - Integration key for Zenduty service API integration
  - `OPEN_ALERTS_FILE` - Path to local file used for persisting open alerts

### Alert Thresholds
- Alert thresholds apply to ZendutyEvent and TelegramEvent (resolution only applies to zenduty)
- Checks run approximately once per minute.
- These thresholds can be overridden per check type in config.yaml
  - `alert_threshold`: number of failures in 5 minutes >= to this value trigger an alert (default: 5)
  - `resolution_threshold`: number of failures in 5 minutes <= this value resolve the alert (default: 3)

## Finding the Telegram Group Chat ID

To integrate Telegram events with the Observer, you need the Telegram group chat ID. Here's how you can find it:

1. Open [Telegram Web](https://web.telegram.org).
2. Navigate to the group chat for which you need the ID.
3. Look at the URL in the browser's address bar; it should look something like `https://web.telegram.org/a/#-1111111111`.
4. The group chat ID is the number in the URL, including the `-` sign if present (e.g., `-1111111111`).

Use this ID in the `publishers.yaml` configuration to correctly set up Telegram events.

## Health Endpoints

The Observer exposes HTTP endpoints for health checks, suitable for Kubernetes liveness and readiness probes:

- **Liveness probe**: `GET /live` always returns `200 OK` with body `OK`.
- **Readiness probe**: `GET /ready` returns `200 OK` with body `OK` if the observer is ready, otherwise returns `503 Not Ready`.

By default, these endpoints are served on port 8080. You can use them in your Kubernetes deployment to monitor the application's health.
