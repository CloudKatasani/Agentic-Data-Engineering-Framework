PY ?= python3

install:
	$(PY) -m venv .venv && .venv/bin/pip install -r requirements.txt pytest

run:
	.venv/bin/python -m adpe serve

demo:
	.venv/bin/python -m adpe demo --domain utilities --stack example-a

suite:
	.venv/bin/python -m adpe suite

test:
	.venv/bin/python -m pytest -q

.PHONY: install run demo suite test
