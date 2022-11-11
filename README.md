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
