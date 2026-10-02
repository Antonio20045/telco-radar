PYTHON_VERSION := $(shell cat .python-version)

.PHONY: venv
venv:
	python$(PYTHON_VERSION) -m venv .venv
	.venv/bin/pip install -q -r requirements-dev.txt
