#
#
#

all:
	echo No default target - try ve, test, lint, run
	false

# COVER_PERCENT:=60

# FIXME:
# - depends on python > 3.6 (bad news for RHEL7 /and/ RHEL8)
# - Add a check for correct version and fail fast

ve: ve/pyvenv.cfg
ve/pyvenv.cfg: requirements.txt
	python3 -m venv ve
	. ve/bin/activate; pip install -r requirements.txt

test: ve
	. ve/bin/activate; pytest

cover: ve
	. ve/bin/activate; pytest \
	    --cov=pyth_observer \
	    --cov-report=html \
	    --cov-report=term
# 	    --cov-fail-under=$(COVER_PERCENT)

lint: lint.python
#lint: lint.yaml - argh, RHEL is too old to do this by default

lint.python: ve
	. ve/bin/activate; flake8 observer.py pyth_observer/

lint.yaml:
	yamllint .

run: ve
	. ve/bin/activate; python3 ./observer.py -l debug --network devnet

clean:
	rm -rf ve htmlcov
