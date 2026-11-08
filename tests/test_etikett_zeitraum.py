"""Karte f46f3357: kein Etikett und keine Spalte nennt bei 36 Geräteraten „36 Monate“.

Die Summe eines Bündels mit 36 Raten enthält 24 Tarifmonate und 36 Geräteraten
(Datenkonzept Geräte 5.3). „Kosten über 36 Monate“ war ein Beschriftungsfehler,
keiner der Rechnung. Gegen den alten Stand rot: das Etikett, die Spaltenköpfe des
Exports und alle Texte der Seite sagten „36 Monate“; die neue Spalte
„Tarifmonate in der Summe“ gab es nicht. Die Gegenprobe steht in jedem Test: bis
24 Monate bleibt es bei „24 Monate“.
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

import pytest
from test_laufzeit_vergleich import SOLL, ansicht

from telco_radar.report import geraete_export
from telco_radar.report.geraete_tco_karten import label_der_leitzahl
from telco_radar.report.geraete_zeitraum_wort import zeitraum_text

BEIDES = "24 Tarifmonate und 36 Geräteraten"


@pytest.fixture(scope="module")
def g(tmp_path_factory):
    return ansicht(tmp_path_factory.mktemp("etikett"))


def test_der_zeitraum_nennt_tarifmonate_und_geraeteraten():
    assert zeitraum_text(36) == BEIDES
    assert zeitraum_text(36, 24) == BEIDES
    assert zeitraum_text(24) == "24 Monate"
    assert zeitraum_text(12, 24) == "12 Monate"
    assert zeitraum_text(36, 36) == "36 Monate"
    assert zeitraum_text(None) == "eine nicht gemessene Laufzeit"


def test_das_etikett_der_leitzahl_sagt_nie_36_monate_bei_24_tarifmonaten():
    assert label_der_leitzahl(36) == f"Kosten über {BEIDES}"
    assert label_der_leitzahl(36, 24) == f"Kosten über {BEIDES}"
    assert label_der_leitzahl(24) == "Kosten über 24 Monate"
    assert label_der_leitzahl(36, 36) == "Kosten über 36 Monate"
    assert label_der_leitzahl(None) != label_der_leitzahl(36)


def _export(g, tmp_path: Path) -> list[dict]:
    info = geraete_export.schreibe_exporte(
        tmp_path, [], [], None, tco=g["tco"]["export"]
    )
    text = (tmp_path / info["tco"]["datei"]).read_text(encoding="utf-8-sig")
    return list(csv.DictReader(io.StringIO(text), delimiter=";"))


def test_die_exportspalte_nennt_den_tarifzeitraum(g, tmp_path):
    zeilen = [z for z in _export(g, tmp_path) if z["Art"] == "Bündel"]
    kopf = geraete_export.SPALTE_UEBER_LAUFZEIT
    assert "Tarifmonate" in kopf and "Geräteraten" in kopf, kopf
    assert "Bündellaufzeit" not in kopf
    zeitraum36 = [z for z in zeilen if z["Leitzahl-Zeitraum Monate"] == "36"]
    assert zeitraum36, "die Fixture trägt keine 36er-Zeile - der Test prüfte nichts"
    for z in zeitraum36:
        assert z[kopf] != "" and z[geraete_export.SPALTE_UEBER_24] == "", z
        assert z[geraete_export.SPALTE_TARIFMONATE] == "24", z
    for z in zeilen:
        if z["Leitzahl-Zeitraum Monate"] == "24":
            assert z[geraete_export.SPALTE_UEBER_24] != "" and z[kopf] == "", z
            assert z[geraete_export.SPALTE_TARIFMONATE] == "24", z


def test_der_export_aendert_keine_zahl(g, tmp_path):
    """Dieselben Beträge je Anbieter wie vor der Änderung (`SOLL` der Fixture)."""
    zeilen = [z for z in _export(g, tmp_path) if z["Art"] == "Bündel"]
    gelesen: dict = {}
    for z in zeilen:
        betrag = geraete_export.leitzahl_aus_zeile(z)
        assert betrag, z
        lz = int(z["Laufzeit Monate"]) if z["Anbieter"] != "1&1" else 24
        gelesen.setdefault(lz, {})[z["Anbieter"]] = float(betrag.replace(",", "."))
    assert gelesen == SOLL


def test_die_preisart_des_radar_exports_nennt_den_tarifzeitraum():
    preisart = geraete_export._preisart_netz
    zeile = {"status": "vergleichbar", "laufzeit": 36, "monate": 36}
    assert preisart(zeile, {}) == f"Kosten über {BEIDES}"
    zeile = {"status": "vergleichbar", "laufzeit": 12, "monate": 24}
    assert preisart(zeile, {}) == "Kosten über 24 Monate · 12 Raten"


def _alle_texte(g) -> str:
    return json.dumps(g, ensure_ascii=False, default=str)


def test_kein_text_der_ansicht_nennt_36_monate_als_zeitraum(g):
    """Etiketten, Antwortsatz, Graphen, Rechenweg, Delta-Sätze und Radar: überall
    steht für die 36er-Zahl beides, nirgends „über 36 Monate“."""
    text = _alle_texte(g)
    falsch = re.findall(
        r".{30}(?<!Geräteraten)(?<!Tarif)(?<!zusammen\))\s[Üü]ber 36 Monate.{20}", text
    )
    assert not falsch, falsch[:5]
    assert BEIDES in text, "kein 36er-Etikett in der Ansicht - der Test prüfte nichts"
    paar36 = next(
        p for p in g["zeitreihe"]["paare"] if p["laufzeit"] == 36 and p["band"] == "xs"
    )
    assert f"Kosten über {BEIDES}" in paar36["graph_beschriftung"]
    assert f"Kosten über {BEIDES}" in paar36["antwort_html"]
