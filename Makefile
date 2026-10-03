PYTHON_VERSION := $(shell cat .python-version)

.PHONY: venv
venv:
	python$(PYTHON_VERSION) -m venv .venv
	.venv/bin/pip install -q -r requirements-dev.txt
	git config blame.ignoreRevsFile .git-blame-ignore-revs

.PHONY: einrichten
einrichten: venv
	git config core.hooksPath .githooks

.PHONY: schnell
schnell:
	.venv/bin/python scripts/pruefleiter.py --schnell

.PHONY: pruefen
pruefen:
	.venv/bin/python scripts/pruefleiter.py --voll

.PHONY: stand
stand:
	.venv/bin/python scripts/stand.py
