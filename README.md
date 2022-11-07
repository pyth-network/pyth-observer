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
