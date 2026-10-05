import importlib
import sys
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL / "tools"))
loeschen = importlib.import_module("kommentare_loeschen")
kommentare = sys.modules["waechter_kommentare"]

VORHER = (
    "#!/usr/bin/env python3\n"
    "# -*- coding: utf-8 -*-\n"
    '"""Modul."""\n'
    "\n"
    "import os  # noqa: F401\n"
    "\n"
    "# Zehn statt sieben: ein ausgefallener Lauf\n"
    "GRENZE = 10  # Minuten\n"
    "\n"
    "\n"
    "def f(a):\n"
    "    werte = [\n"
    "        a,  # erster\n"
    "        # zweiter folgt\n"
    "        2,\n"
    "    ]\n"
    "    try:\n"
    "        return werte\n"
    "    except Exception:  # noqa: BLE001 - ein Bild kippt keinen Lauf\n"
    "        return None  # pragma: no cover - der echte Pfad\n"
)
NACHHER = (
    "#!/usr/bin/env python3\n"
    '"""Modul."""\n'
    "\n"
    "import os  # noqa: F401\n"
    "\n"
    "GRENZE = 10\n"
    "\n"
    "\n"
    "def f(a):\n"
    "    werte = [\n"
    "        a,\n"
    "        2,\n"
    "    ]\n"
    "    try:\n"
    "        return werte\n"
    "    except Exception:  # noqa: BLE001\n"
    "        return None\n"
)


def test_loescht_wissen_und_laesst_schalter_und_shebang_stehen():
    ergebnis = loeschen.loesche(VORHER, "scripts/a.py", WURZEL)
    assert ergebnis.text == NACHHER
    assert ergebnis.geloescht == 7
    assert kommentare.freie_kommentare(ergebnis.text, "scripts/a.py") == []


def test_datei_ohne_freie_kommentare_bleibt_bytegleich():
    ergebnis = loeschen.loesche(NACHHER, "scripts/a.py", WURZEL)
    assert (ergebnis.text, ergebnis.geloescht) == (NACHHER, 0)


def test_geloeschter_kommentar_zwischen_importen_laesst_keine_leerzeile():
    vorher = "import os\n\n# Wissen\nimport sys\n\nx = os, sys\n"
    ergebnis = loeschen.loesche(vorher, "scripts/a.py", WURZEL)
    assert ergebnis.text == "import os\nimport sys\n\nx = os, sys\n"


def test_umsortierte_importe_bleiben_in_ihrer_reihenfolge():
    vorher = "import sys\n\n# Wissen\nimport os\n\nx = os, sys\n"
    ergebnis = loeschen.loesche(vorher, "scripts/a.py", WURZEL)
    assert ergebnis.text == "import sys\n\nimport os\n\nx = os, sys\n"


def test_geaenderter_syntaxbaum_scheitert(monkeypatch):
    monkeypatch.setattr(
        loeschen, "formatiere", lambda text, pfad, wurzel, importe: "x = 2\n"
    )
    with pytest.raises(loeschen.SyntaxbaumGeaendert, match="a.py"):
        loeschen.loesche("x = 1  # eins\n", "scripts/a.py", WURZEL)


@pytest.mark.parametrize(
    ("kommentar", "bleibt"),
    [
        ("# noqa: E402", "# noqa: E402"),
        ("# noqa: ANN002, ANN003", "# noqa: ANN002, ANN003"),
        ("# noqa: B018 - nur Dokumentationsbezug", "# noqa: B018"),
        ("# noqa: keep loop simple", "# noqa"),
        (
            "# type: ignore[assignment]  # noqa: E501",
            "# type: ignore[assignment]",
        ),
        ("# siehe mypy: Doku", None),
        ("# Hinweis: ruff: disable[E501] nie nutzen", None),
        ("# -*- coding: utf-8 -*-", None),
        ("# fmt: Hinweis[Der Tarif gilt nur bis Ende Oktober]", None),
        ("# ruff: Der # ruff: Tarif # ruff: gilt", None),
        ("# isort: weil=Grund", None),
        ("# type: ignore[Der Tarif gilt]", "# type: ignore"),
        ("# noqa: E501  # pragma: no cover", "# noqa: E501"),
        ("# fmt: off", "# fmt: off"),
        ("# ruff: disable[E501]", "# ruff: disable[E501]"),
        ('# mypy: disable-error-code="misc"', '# mypy: disable-error-code="misc"'),
    ],
)
def test_neuer_kommentar(kommentar, bleibt):
    assert loeschen.neuer_kommentar(kommentar) == bleibt


def test_shebang_nur_in_der_ersten_zeile_erlaubt():
    text = "#!/usr/bin/env python3\nx = 1\n#!/usr/bin/env python3\n"
    frei = [(3, "#!/usr/bin/env python3")]
    assert kommentare.freie_kommentare(text, "scripts/a.py") == frei


@pytest.mark.parametrize(
    ("pfad", "kopf"),
    [
        ("src/paket/a.py", "#!/usr/bin/env python3"),
        ("tests/test_a.py", "#!/usr/bin/python3"),
        ("scripts/a.py", "#!Achtung: Preis immer netto"),
        ("tools/a.py", "#!/bin/sh"),
    ],
)
def test_shebang_nur_fuer_python_unter_scripts_und_tools(pfad, kopf):
    assert kommentare.freie_kommentare(f"{kopf}\nx = 1\n", pfad) == [(1, kopf)]
    ergebnis = loeschen.loesche(f"{kopf}\nx = 1\n", pfad, WURZEL)
    assert ergebnis.text == "x = 1\n"


def _projekt(tmp_path, monkeypatch, befunde):
    monkeypatch.setattr(loeschen.kommentarwissen, "befunde", lambda wurzel: befunde)
    (tmp_path / "scripts").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    datei = tmp_path / "scripts/a.py"
    datei.write_text(VORHER, encoding="utf-8")
    return datei


def test_main_schreibt_und_meldet_unveraenderten_syntaxbaum(
    tmp_path, monkeypatch, capsys
):
    datei = _projekt(tmp_path, monkeypatch, [])
    assert loeschen.main(["--wurzel", str(tmp_path)]) == 0
    assert datei.read_text(encoding="utf-8") == NACHHER
    zeile = "scripts/a.py: 7 Kommentare, Syntaxbaum unverändert"
    assert capsys.readouterr().out.splitlines() == [zeile]


def test_main_trocken_schreibt_nichts(tmp_path, monkeypatch):
    datei = _projekt(tmp_path, monkeypatch, [])
    assert loeschen.main(["--wurzel", str(tmp_path), "--trocken"]) == 0
    assert datei.read_text(encoding="utf-8") == VORHER


def test_main_loescht_nichts_ohne_uebernommenes_kommentarwissen(
    tmp_path, monkeypatch, capsys
):
    datei = _projekt(tmp_path, monkeypatch, ["ohne Protokoll: scripts/a.py"])
    assert loeschen.main(["--wurzel", str(tmp_path)]) == 1
    assert datei.read_text(encoding="utf-8") == VORHER
    assert "ohne Protokoll: scripts/a.py" in capsys.readouterr().out


def test_main_meldet_geaenderten_syntaxbaum_rot(tmp_path, monkeypatch, capsys):
    datei = _projekt(tmp_path, monkeypatch, [])
    monkeypatch.setattr(
        loeschen, "formatiere", lambda text, pfad, wurzel, importe: "x = 2\n"
    )
    assert loeschen.main(["--wurzel", str(tmp_path)]) == 1
    assert datei.read_text(encoding="utf-8") == VORHER
    assert "Syntaxbaum geändert, nicht geschrieben" in capsys.readouterr().out
