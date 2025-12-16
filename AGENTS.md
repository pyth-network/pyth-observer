# Repository Guidelines

## Project Structure & Modules
- Core code lives in `pyth_observer/`: CLI entrypoint in `cli.py`, check logic under `check/`, alert dispatchers in `dispatch.py`, event types in `event.py`, and HTTP probes in `health_server.py`.
- Supporting assets and defaults: sample configs (`sample.config.yaml`, `sample.publishers.yaml`, `sample.coingecko.yaml`), Dockerfile for container builds, and helper scripts in `scripts/` (e.g., `build_coingecko_mapping.py`).
- Tests are in `tests/` and mirror module names (`test_checks_price_feed.py`, `test_checks_publisher.py`).

## Setup, Build & Run
- Use Python 3.11 with Poetry 2.x. Suggested bootstrap: `poetry env use $(which python)` then `poetry install`.
- Common Make targets: `make setup` (install deps), `make run` (devnet run), `make test`, `make cover`, `make lint`, `make clean`.
- Direct commands: `poetry run pyth-observer --config sample.config.yaml --publishers sample.publishers.yaml --coingecko-mapping sample.coingecko.yaml` to run locally; add `-l debug` for verbose logs.
- CoinGecko mapping: `poetry run python scripts/build_coingecko_mapping.py -o my_mapping.json` and compare with `-e sample.coingecko.yaml` before replacing defaults.

## Testing Guidelines
- Framework: `pytest`. Quick check with `poetry run pytest`; coverage report via `make cover` (writes `htmlcov/`).
- Keep tests colocated under `tests/` with `test_*` naming. Prefer async tests for async code paths and mock network calls.
- Add regression tests alongside new checks or dispatch paths; include sample config fragments when useful.

## Coding Style & Naming
- Auto-format with `black` and import order via `isort` (run together with `make lint`). Lint also runs `pyright` and `pyflakes`.
- Target Python 3.11; favor type hints on public functions and dataclasses/models. Use snake_case for functions/variables, PascalCase for classes, and uppercase for constants.
- Keep config keys consistent with existing YAML samples; avoid hard-coding secrets—read from env vars.

## Commit & PR Practices
- Follow the existing Conventional Commit style (`fix:`, `chore:`, `refactor!:`, etc.) seen in `git log`.
- PRs should summarize behavior changes, link issues, and include reproduction or validation steps (commands run, configs used). Add screenshots only when output formatting changes.
- Keep diffs small and focused; update sample config or docs when user-facing options change.

## Configuration & Security Notes
- Sensitive values (API keys, tokens) must be supplied via environment variables; never commit them. Use `.env` locally and document new keys in `README.md`.
- For deployments, wire liveness/readiness probes to `GET /live` and `GET /ready` on port 8080.
