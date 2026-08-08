"""„Wer hat einen Hebel, den wir nicht haben?" (report/luecken.py).

Der teuerste Fehler dieser Ansicht waere ein falsches „Vodafone hat das
nicht" bei etwas, das es gibt: es kostet mehr Vertrauen als zehn richtige
Eintraege einbringen, und es faellt genau der Person auf, die die Seite
benutzt. Deshalb prueft die Haelfte dieser Datei, dass die Seite SCHWEIGT,
wo sie nichts weiss.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from telco_radar.report import luecken

LABELS = {"ki": "KI & Assistenten", "entertainment": "Entertainment",
          "gaming": "Gaming", "fintech": "Fintech"}


def _bestand():
    return [
        {"theme": "entertainment", "operator": "Deutsche Telekom",
         "url": "https://a.test/1", "headline": "Telekom bündelt Disney+"},
        {"theme": "entertainment", "operator": "Orange", "url": "https://a.test/2"},
        {"theme": "entertainment", "operator": "Free", "url": "https://a.test/3"},
        {"theme": "ki", "operator": "Deutsche Telekom", "url": "https://a.test/4",
         "headline": "Telekom bringt KI-Phone"},
        {"theme": "ki", "operator": "SK Telecom", "url": "https://a.test/5"},
        {"theme": "gaming", "operator": "Reliance Jio", "url": "https://a.test/6"},
    ]


def _eigene(**hebel):
    return luecken.EigeneHebel(
        markt="Vodafone Deutschland", direktvergleich="Deutsche Telekom",
        hebel={k: dict(v, key=k) for k, v in hebel.items()})


# ------------------------------------------------------- die eine Regel

def test_ohne_gepflegte_liste_gibt_es_keine_luecken():
    """Zwoelf weisse Flecken zu behaupten, die niemand geprueft hat, waere
    schlimmer als gar keine Ansicht."""
    v = luecken.bauen(_bestand(), LABELS, luecken.EigeneHebel())
    assert v["aktiv"] is False
    assert v["flecken"] == []


def test_offen_ist_kein_weisser_fleck():
    v = luecken.bauen(_bestand(), LABELS,
                      _eigene(entertainment={"wir_haben": "offen", "stand": ""}))
    assert v["flecken"] == []
    zeile = next(z for z in v["vergleich"] if z["key"] == "entertainment")
    assert zeile["zustand"] == luecken.OFFEN


def test_nein_ohne_datum_gilt_als_offen():
    """Eine undatierte Aussage ueber ein Portfolio ist nach drei Monaten
    keine Aussage mehr."""
    v = luecken.bauen(_bestand(), LABELS,
                      _eigene(entertainment={"wir_haben": "nein", "stand": ""}))
    assert v["flecken"] == []


def test_gepflegtes_nein_wird_zum_weissen_fleck():
    v = luecken.bauen(_bestand(), LABELS, _eigene(
        entertainment={"wir_haben": "nein", "stand": "2026-08-08"}))
    assert [f["key"] for f in v["flecken"]] == ["entertainment"]
    assert v["flecken"][0]["n_wettbewerber"] == 3


def test_ein_einzelner_wettbewerber_ist_kein_fleck():
    """Einer ist ein Einzelfall, zwei sind eine Bewegung."""
    v = luecken.bauen(_bestand(), LABELS,
                      _eigene(gaming={"wir_haben": "nein", "stand": "2026-08-08"}))
    assert v["flecken"] == []


def test_gepflegtes_ja_erscheint_mit_beispiel_und_datum():
    v = luecken.bauen(_bestand(), LABELS, _eigene(
        ki={"wir_haben": "ja", "beispiel": "Perplexity im Tarif",
            "stand": "2026-08-08"}))
    zeile = next(z for z in v["vergleich"] if z["key"] == "ki")
    assert zeile["zustand"] == luecken.JA
    assert zeile["eigenes"] == "Perplexity im Tarif"
    assert zeile["stand"] == "2026-08-08"
    assert v["flecken"] == []


# ------------------------------------------------------------ Sortierung

def test_der_staerkste_fleck_steht_oben():
    v = luecken.bauen(_bestand(), LABELS, _eigene(
        entertainment={"wir_haben": "nein", "stand": "2026-08-08"},
        ki={"wir_haben": "nein", "stand": "2026-08-08"}))
    assert [f["key"] for f in v["flecken"]] == ["entertainment", "ki"]


# ---------------------------------------------------------- Direktvergleich

def test_direktvergleich_nennt_den_beleg_des_gegners():
    v = luecken.bauen(_bestand(), LABELS, _eigene(
        ki={"wir_haben": "nein", "stand": "2026-08-08"}))
    zeile = next(z for z in v["gegner_hebel"] if z["key"] == "ki")
    assert zeile["gegner_hat"] is True
    assert "KI-Phone" in zeile["gegner_beispiel"]
    assert zeile["gegner_url"] == "https://a.test/4"


def test_direktvergleich_laesst_leere_zeilen_weg():
    """Ein Hebel, den weder der Gegner noch wir belegt haben, ist keine
    Zeile - er ist die Abwesenheit von Information."""
    v = luecken.bauen(_bestand(), LABELS, luecken.EigeneHebel(
        direktvergleich="Deutsche Telekom"))
    assert all(z["key"] in ("ki", "entertainment") for z in v["gegner_hebel"])


# --------------------------------------------------------- Konfiguration

def test_die_ausgelieferte_datei_ist_leer_aber_gueltig():
    """Sie steht bewusst auf `offen`: zum Zeitpunkt des Einbaus kannte
    niemand hier das Vodafone-Portfolio belastbar. Das ist die Anwendung der
    eigenen Regel, kein Versaeumnis der Mechanik."""
    eigene = luecken.lade_eigene_hebel(Path(__file__).resolve().parents[1])
    assert eigene.markt and eigene.direktvergleich
    assert len(eigene.hebel) == 12
    assert eigene.erfasst == 0
    assert all(eigene.zustand(k) == luecken.OFFEN for k in eigene.hebel)


def test_fehlende_datei_legt_nichts_lahm(tmp_path):
    assert luecken.lade_eigene_hebel(tmp_path).hebel == {}


def test_die_seite_sagt_wenn_sie_unvollstaendig_ist():
    v = luecken.bauen(_bestand(), LABELS, _eigene(
        ki={"wir_haben": "ja", "beispiel": "x", "stand": "2026-08-08"},
        gaming={"wir_haben": "offen", "stand": ""}))
    assert v["unvollstaendig"] is True
    assert v["n_erfasst"] == 1 and v["n_hebel"] == 2
