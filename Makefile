PY ?= python3

install:
	$(PY) -m venv .venv && .venv/bin/pip install -r requirements.txt pytest

run:
	.venv/bin/python -m adef serve

demo:
	.venv/bin/python -m adef demo --domain utilities --stack example-a

suite:
	.venv/bin/python -m adef suite

test:
	.venv/bin/python -m pytest -q

.PHONY: install run demo suite test
