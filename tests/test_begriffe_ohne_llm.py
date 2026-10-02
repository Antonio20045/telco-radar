"""Die Module, die `report/` aus `analyze/` liest, laden weder LLM noch Netz."""

import subprocess
import sys

import pytest

_VERBOTEN = ("httpx", "requests", "telco_radar.analyze.llm")


@pytest.mark.parametrize(
    "modul",
    [
        "telco_radar.analyze.begriffe",
        "telco_radar.analyze.themen_store",
        "telco_radar.analyze.diff_db",
        "telco_radar.analyze.ctm",
        "telco_radar.geraete_model",
        "telco_radar.report.thema",
        "telco_radar.report.wettbewerb",
    ],
)
def test_modul_laedt_kein_llm_und_kein_netz(modul):
    pruefung = (
        "import importlib, sys\n"
        f"importlib.import_module({modul!r})\n"
        f"print(','.join(m for m in {_VERBOTEN!r} if m in sys.modules))\n"
    )
    ergebnis = subprocess.run(
        [sys.executable, "-c", pruefung], capture_output=True, text=True, check=True
    )
    assert ergebnis.stdout.strip() == ""
