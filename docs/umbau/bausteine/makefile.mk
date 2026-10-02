einrichten: venv
	git config core.hooksPath .githooks
	git config blame.ignoreRevsFile .git-blame-ignore-revs

venv:
	uv venv --python-preference only-managed --python $$(cat .python-version)
	uv pip install -r requirements.txt -r requirements-dev.txt
	.venv/bin/playwright install chromium

pruefen:
	.venv/bin/python scripts/pruefleiter.py --voll

schnell:
	.venv/bin/python scripts/pruefleiter.py --schnell

stand:
	.venv/bin/python scripts/stand.py

golden-aufnehmen:
	.venv/bin/python scripts/golden_aufnehmen.py
