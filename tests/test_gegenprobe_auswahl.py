"""Gewählte Option im Konfigurationsbild, gegen das DOM der echten Anbieterseiten
(Gegenprobe vom 21.11.2026, ``tests/fixtures/gegenprobe_auswahl``): je Anbieter zählt
nur die gewählte Kachel oder eine Zusammenfassung der Wahl. Lokal, ohne Netz."""

from __future__ import annotations

import copy
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
    "vodafone-2.html.gz": {"Gerät": True, "Tarif": True},
    "1-1-1.html.gz": {"Gerät": True, "Speicher": True, "Raten": True},
    "1-1-2.html.gz": {"Gerät": True, "Tarif": True, "Raten": True},
}
"""Vodafone nennt auf der Tarifseite den Speicher nicht als Wahl (nur in der
Überschrift), 1&1 den Speicher erst auf der Produktseite: beide Seiten werden
gestapelt. Ein Merkmal ohne Auswahl und ohne benannten Block fehlt im Ergebnis."""


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
    assert g.get("Speicher") is not True and g.get("Raten") is not True


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
    assert g.get("Raten") is not True and g.get("Tarif") is not True


VARIANTEN = {
    "512": (
        "Speicher",
        lambda s: s.update(sku_id=s["sku_id"].replace("256gb", "512gb")),
    ),
    "1tb": ("Speicher", lambda s: s.update(sku_id=s["sku_id"].replace("256gb", "1tb"))),
    "36": ("Raten", lambda s: s.update(laufzeit_monate=36)),
    "12": ("Raten", lambda s: s.update(laufzeit_monate=12)),
}


@pytest.mark.parametrize("variante", sorted(VARIANTEN))
@pytest.mark.parametrize("name", sorted(ERWARTET))
def test_andere_option_als_die_gewaehlte_zaehlt_nie(chromium, name, variante):
    """Prüfer PR 204 Runde 3 (flip): dieselbe Seite, ein Bündel mit anderem Speicher
    oder anderen Raten; die Seite zeigt die gewählte Option, nicht die des Bündels."""
    merkmal, aendere = VARIANTEN[variante]
    fall = FAELLE[name]
    satz = copy.deepcopy(fall["satz"])
    aendere(satz)
    s = _seite(chromium, name)
    try:
        g = bild.gewaehlte(s, satz, tuple(fall["anker"]), tuple(fall["nur"]))
    finally:
        s.close()
    assert g.get(merkmal) is not True


def _aufnahme(chromium, name: str, aendere) -> bild.Aufnahme:
    fall = FAELLE[name]
    satz = copy.deepcopy(fall["satz"])
    aendere(satz)
    s = _seite(chromium, name)
    try:
        return bild.aufnehme(s, satz, tuple(fall["anker"]) or None, tuple(fall["nur"]))
    finally:
        s.close()


def test_o2_datenblatt_mit_allen_varianten_ist_keine_wahl(chromium):
    """Prüfer: die o2-Seite zeigt 256 GB gewählt, das Datenblatt nennt alle Größen."""
    a = _aufnahme(
        chromium,
        "o2-1.html.gz",
        lambda s: s.update(sku_id=s["sku_id"].replace("256gb", "512gb")),
    )
    assert "Speicher" not in a.zeigt
    assert a.befund["Speicher"].startswith("gewählt: ")


def test_telekom_werbetext_ab_tarif_s_ist_keine_wahl(chromium):
    """Prüfer: gewählt ist MagentaMobil L, ein Werbetext nennt „ab MagentaMobil S“."""
    a = _aufnahme(
        chromium, "telekom-1.html.gz", lambda s: s.update(tarif_name="MagentaMobil S")
    )
    assert "Tarif" not in a.zeigt


SATZ = {
    "id": "buendel--test--apple-iphone-17-256gb-schwarz--o2-mobile-l--24m",
    "sku_id": "apple-iphone-17-256gb-schwarz",
    "tarif_name": "O2 Mobile L mit 150 GB+ (24 Mon.)",
    "laufzeit_monate": 24,
    "geraet_monatsrate": 40.0,
}
ANKER = ("Dein Angebot", "einmalig gesamt")
PREISKASTEN = (
    "<aside><h2>Dein Angebot</h2><p>Gerät monatlich: 40,00 €</p>"
    "<p>einmalig gesamt: 7,99 €</p></aside>"
)
ALT = f"""<html><body style="margin:0;font:16px sans-serif">
<h1>Apple iPhone 17</h1><p>Speicher: 256 GB</p>
<div role="radiogroup"><button role="radio" aria-checked="false">256 GB</button>
<button role="radio" aria-checked="true">512 GB</button></div>
<p>Tarif: O2 Mobile L</p><p>Ratenzahlung: 24 Monate</p>{PREISKASTEN}</body></html>"""
FREMD = f"""<html><body style="margin:0;font:16px sans-serif">
<div style="height:1500px"></div><h1>Apple iPhone 17</h1><p>Speicher: <b>256 GB</b></p>
<p>Tarif: O2 Mobile L</p><p>Ratenzahlung: 24 Monate</p>
<div style="border:2px solid red;width:400px">Allnet Flat S: 49,99 €/Mon.</div>
{PREISKASTEN}<div style="height:1500px"></div></body></html>"""
WORT = f"""<html><body style="margin:0;font:16px sans-serif">
<h1>Apple iPhone 17</h1><p>Speicher: 256 GB</p>
<div role="radiogroup"><button role="radio" aria-checked="false">MagentaMobil S</button>
<button role="radio" aria-checked="true">MagentaMobil Start</button></div>
<p>Ratenzahlung: 24 Monate</p>{PREISKASTEN}</body></html>"""


def _html(chromium, html: str, satz: dict = SATZ) -> bild.Aufnahme:
    s = chromium.new_page(viewport={"width": 1440, "height": 1000})
    s.set_content(html)
    try:
        return bild.aufnehme(s, satz, ANKER)
    finally:
        s.close()


def test_alte_zeile_ueberstimmt_die_gewaehlte_kachel_nicht(chromium):
    """Prüfer: gewählt ist 512 GB (aria-checked), „Speicher: 256 GB“ ist veraltet."""
    a = _html(chromium, ALT)
    assert "Speicher" not in a.zeigt
    assert a.befund["Speicher"] == "gewählt: 512 GB"


def test_zweiter_monatspreis_im_ausschnitt_unterhalb_des_fensters(chromium):
    """Prüfer: der fremde Monatspreis liegt erst im gerollten Ausschnitt."""
    assert bild.WIDERSPRUCH in _html(chromium, FREMD).ohne


def test_tarifstufe_ist_ein_ganzes_wort(chromium):
    """Prüfer: „MagentaMobil S“ ist nicht „MagentaMobil Start“."""
    a = _html(chromium, WORT, dict(SATZ, tarif_name="MagentaMobil S"))
    assert "Tarif" not in a.zeigt
