"""Issue #125, Ergänzung: was neben Bild und Legende für die Händlerreihen mitzieht.

- Ein Händlerpunkt ist klickbar (`data-anb`/`data-m`); `_rechenwege_html` muss
  ihm eine Rechenweg-Vorlage liefern, sonst öffnet der Klick nichts.
- `ueberholt_html` nennt einen Händler, dessen Preise eine belegte Lücke
  überholt hat, statt ihn stumm wegzulassen.
- Die drei Händleretiketten sind gleich grau: kein Etikett darf tiefer stehen als
  die Linie des nächsten Anbieters darunter (Stand 13.11.2026, S26 Ultra 256 · M ·
  24: das Etikett „· Vodafone-Netz“ stand an der Linie „· Telekom-Netz“).
"""

from __future__ import annotations

import html
import re

import pytest
import test_zeitreihe_haendler_1114 as abnahme
from test_geraete_zeitreihe_ansicht import baue

from telco_radar.report import geraete_zeitreihe as gz
from telco_radar.report.geraete_zeitreihe_legende import ueberholt_html

HAENDLER = abnahme.HAENDLER

ENDWERTE = {
    "Telekom": 2587.0,
    "Vodafone": 2182.0,
    "o2": 2126.0,
    "congstar": 1746.0,
    "1&1": 1712.0,
    HAENDLER[1]: 1566.0,
    HAENDLER[0]: 1386.0,
}


def test_rechenweg_vorlage_fuer_den_haendlerpunkt(tmp_path):
    root, state = baue(tmp_path)
    abnahme._mit_haendler(state, HAENDLER[0])
    paar = abnahme._paar_block(abnahme._ansicht(root, state))
    vorlagen = {
        html.unescape(a)
        for a in re.findall(r"<template data-anb='([^']*)'", paar["rechenweg_html"])
    }
    assert HAENDLER[0] in vorlagen, vorlagen


def test_ueberholt_nennt_den_haendler():
    modell = {"belegte_luecken": {HAENDLER[2]: {"kurz": "nicht mehr im Sortiment"}}}
    mess = {HAENDLER[2]: {"2026-11-10": {}}}
    text = html.unescape(ueberholt_html(modell, mess, {}))
    assert f"{HAENDLER[2]} · nicht mehr im Sortiment" in text, text


def _serien() -> dict:
    tage = ("2026-11-10", "2026-11-12", "2026-11-13")
    return {a: [(t, wert) for t in tage] for a, wert in ENDWERTE.items()}


def _belege() -> dict:
    return {
        a: (f"https://example.de/{i}", "2026-11-13") for i, a in enumerate(ENDWERTE)
    }


@pytest.mark.parametrize("breit", [True, False], ids=["breit", "schmal"])
def test_kein_etikett_unter_der_linie_des_naechsten(breit):
    svg = gz._svg(_serien(), breit, _belege(), None, laufzeit=24)
    linie = {
        html.unescape(a): float(cy)
        for cy, a in re.findall(
            r"<circle class='gr-zr-punkt gr-zr-ende' cx='[^']*' cy='([-0-9.]+)'"
            r"[^>]*data-anb='([^']*)'",
            svg,
        )
    }
    etikett = {}
    for m in re.finditer(
        r"<text class='gr-zr-name'[^>]*\by='([-0-9.]+)'[^>]*>(.*?)</text>", svg
    ):
        name = html.unescape(re.sub(r"<tspan[^>]*>.*?</tspan>", "", m.group(2)))
        etikett[name.strip()] = float(m.group(1)) - 4
    folge = sorted(linie, key=linie.get)
    assert set(folge) == set(ENDWERTE), folge
    for oben, unten in zip(folge, folge[1:], strict=False):
        assert etikett[oben] <= linie[unten], (
            f"Etikett {oben} (y {etikett[oben]}) steht unter der Linie von "
            f"{unten} (y {linie[unten]})"
        )
