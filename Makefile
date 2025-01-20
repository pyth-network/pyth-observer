_targets := setup python-version pyenv-info test cover lint run clean
.PHONY: help $(_targets)
.DEFAULT_GOAL := help

version-python: ## Echos the version of Python in use
	python --version

help:
	@echo Targets: $(_targets)
	@false

setup:
	poetry install

python-version:
	@which python
	@python --version

pyenv-info: setup
	poetry env info

test: setup
	poetry run pytest

cover: setup
	poetry run pytest \
	    --cov=pyth_observer \
	    --cov-report=html \
	    --cov-report=term

lint: setup lint.python lint.yaml

lint.python:
	poetry run isort pyth_observer/
	poetry run black pyth_observer/
	poetry run pyright pyth_observer/
	poetry run pyflakes pyth_observer/

lint.yaml:
	yamllint .

run: setup
	poetry run pyth-observer -l debug --network devnet

clean:
	poetry env remove --all
	rm -rf htmlcov
