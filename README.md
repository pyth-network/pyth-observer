# Pyth Observer

Observe Pyth on-chain price feeds and run sanity checks on the data.

## Usage

Container images are available at https://gallery.ecr.aws/pyth-network/observer.

To run Observer locally, make sure you have a recent version of [Poetry](https://python-poetry.org) installed and run:

```sh
$ poetry install
$ poetry run pyth-observer
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

- `ZendutyEvent`
  - `ZENDUTY_INTEGRATION_KEY` - Integration key for Zenduty service API integration
  - `OPEN_ALERTS_FILE` - Path to local file used for persisting open alerts

### Zenduty Alert Thresholds
By default: 
- Zenduty alert will fire if a check fails 5 or more times within 5 minutes.
- The alert will be resolved if the check failed < 4 times within 5 minutes.
- Checks run approximately once per minute.
- These thresholds can be overridden per check type in config.yaml
  - `zenduty_alert_threshold`: number of failures in 5 minutes >= to this value trigger an alert
  - `zenduty_resolution_threshold`: number of failures in 5 minutes <= this value resolve the alert

## Finding the Telegram Group Chat ID

To integrate Telegram events with the Observer, you need the Telegram group chat ID. Here's how you can find it:

1. Open [Telegram Web](https://web.telegram.org).
2. Navigate to the group chat for which you need the ID.
3. Look at the URL in the browser's address bar; it should look something like `https://web.telegram.org/a/#-1111111111`.
4. The group chat ID is the number in the URL, including the `-` sign if present (e.g., `-1111111111`).

Use this ID in the `publishers.yaml` configuration to correctly set up Telegram events.

