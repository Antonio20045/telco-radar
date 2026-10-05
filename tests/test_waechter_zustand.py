"""Stufe 0: ein Modul in ``ZUSTANDSFREI`` hat keinen veränderlichen Modulzustand."""

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
zustand = importlib.import_module("waechter_zustand")

ALTER_STAND = (
    "import logging\n"
    "log = logging.getLogger(__name__)\n"
    "TRANSPORT: object | None = None\n"
    "_FALLBACKS: dict[str, str] = {}\n"
    "_DEAD = set()\n"
    "def budget():\n"
    "    global _BUDGET\n"
    "    _BUDGET = 1\n"
)

ERLAUBT = (
    "import logging\n"
    "from collections.abc import Callable\n"
    "log = logging.getLogger(__name__)\n"
    'URL = "https://x.invalid"\n'
    "_FATAL = frozenset({400, 402})\n"
    "WARTEN = (1, 2, 3)\n"
    "GRENZE = 60 * 5\n"
    "ANDERE = URL\n"
    "Client = Callable[[str], str]\n"
    "class Sitzung:\n"
    "    zaehler: dict = {}\n"
)


def test_alter_stand_von_llm_ist_rot():
    funde = zustand.zustand_in(ALTER_STAND)
    assert [f.split()[-1] for f in funde] == [
        "TRANSPORT",
        "_FALLBACKS",
        "_DEAD",
        "_BUDGET",
    ]


def test_konstanten_log_und_klassen_sind_gruen():
    assert zustand.zustand_in(ERLAUBT) == []


def test_kleingeschriebene_bindung_ist_rot():
    assert zustand.zustand_in("cache = 1\n") == ["Zeile 1 bindet cache"]


def test_modulzustand_meldet_die_datei_und_uebergeht_fehlende(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text(ALTER_STAND, encoding="utf-8")
    monkeypatch.setattr(zustand, "ZUSTANDSFREI", ("a.py", "fehlt.py"))
    rot = zustand.modulzustand(tmp_path)
    assert len(rot) == 4
    assert rot[0].startswith("a.py: Zeile 3 bindet TRANSPORT")


def test_llm_steht_in_zustandsfrei():
    assert "src/telco_radar/analyze/llm.py" in zustand.ZUSTANDSFREI
