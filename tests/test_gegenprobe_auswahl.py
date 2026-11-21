"""Gewählte Option im Konfigurationsbild, gegen das DOM der echten Anbieterseiten
(Gegenprobe vom 21.11.2026, ``tests/fixtures/gegenprobe_auswahl``): je Anbieter zählt
nur die gewählte Kachel oder eine Zusammenfassung der Wahl. Lokal, ohne Netz."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from telco_radar.collect.geraete import gegenprobe_bild as bild

ORDNER = Path(__file__).parent / "fixtures" / "gegenprobe_auswahl"
FAELLE = json.loads((ORDNER / "faelle.json").read_text(encoding="utf-8"))
ALLE = ["Gerät", "Speicher", "Tarif", "Raten"]
ERWARTET = {
    "telekom-1.html.gz": dict.fromkeys(ALLE, True),
    "o2-1.html.gz": dict.fromkeys(ALLE, True),
    "congstar-1.html.gz": dict.fromkeys(ALLE, True),
    "saturn-mediamarkt-telekom-netz-1.html.gz": dict.fromkeys(ALLE[:3], True),
    "vodafone-1.html.gz": {"Gerät": True, "Speicher": True, "Raten": True},
    "vodafone-2.html.gz": {"Gerät": True, "Speicher": False, "Tarif": True},
    "1-1-1.html.gz": {"Gerät": True, "Speicher": True},
    "1-1-2.html.gz": {"Gerät": True, "Tarif": True, "Raten": True},
}
"""Vodafone nennt auf der Tarifseite den Speicher nur in der Überschrift (keine Wahl),
1&1 die Raten erst auf der Tarifseite: beide Seiten werden gestapelt."""


def _seite(chromium, name: str):
    s = chromium.new_page(viewport={"width": 1440, "height": 1000})
    s.set_content(gzip.decompress((ORDNER / name).read_bytes()).decode("utf-8"))
    return s


def _gewaehlt(s, name: str) -> dict[str, bool]:
    fall = FAELLE[name]
    return bild.gewaehlte(s, fall["satz"], tuple(fall["anker"]), tuple(fall["nur"]))


@pytest.mark.parametrize("name", sorted(ERWARTET))
def test_gewaehlte_option_je_anbieter(chromium, name):
    s = _seite(chromium, name)
    try:
        assert _gewaehlt(s, name) == ERWARTET[name]
    finally:
        s.close()


def test_telekom_kachel_ohne_aria_checked_ist_nicht_gewaehlt(chromium):
    s = _seite(chromium, "telekom-1.html.gz")
    try:
        s.evaluate(
            """() => document.querySelectorAll('[aria-checked="true"]')
              .forEach(e => e.setAttribute('aria-checked', 'false'))"""
        )
        g = _gewaehlt(s, "telekom-1.html.gz")
    finally:
        s.close()
    assert g["Speicher"] is False and g["Raten"] is False


def test_congstar_ohne_gesetzte_auswahl_zaehlt_keine_kachel(chromium):
    s = _seite(chromium, "congstar-1.html.gz")
    try:
        s.evaluate(
            """() => { document.querySelectorAll('input').forEach(e => {
              e.checked = false; e.removeAttribute('checked'); });
              document.querySelectorAll('[aria-checked="true"]')
              .forEach(e => e.setAttribute('aria-checked', 'false')); }"""
        )
        g = _gewaehlt(s, "congstar-1.html.gz")
    finally:
        s.close()
    assert g["Raten"] is False and g["Tarif"] is False
