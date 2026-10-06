"""Notbremse in der Zeitreihe der Geräteseite (Datenkonzept Geräteradar, Schritt 1).

Das Rechenweg-Panel nennt den Zeitraum seiner Zahl mit demselben Etikett wie
die Karten (1&1: „Kosten über 36 Monate“) und schreibt Monatsnamen deutsch,
auch unter englischem Locale. Gerendert aus dem Bestand vom 2026-10-03; der
Bezugstag kommt aus dem Bestand, nie vom heutigen Datum.
"""

from __future__ import annotations

import locale
import re

import pytest
from bestand_pfad import abbild
from bs4 import BeautifulSoup

from telco_radar.config import load_config
from telco_radar.report.html import render_site

DEUTSCHE_MONATE = {
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
}
DATUM = re.compile(r"\b\d{1,2}\. ([A-Za-zä]+) \d{4}\b")


@pytest.fixture(scope="module")
def gerendert(tmp_path_factory):
    """Seite und Fragment, gerendert unter dem C-Locale (englische Monatsnamen)."""
    wurzel = tmp_path_factory.mktemp("notbremse-zr")
    vorher = locale.setlocale(locale.LC_TIME)
    locale.setlocale(locale.LC_TIME, "C")
    try:
        render_site(wurzel / "site", abbild(wurzel), load_config(wurzel))
    finally:
        locale.setlocale(locale.LC_TIME, vorher)
    seite = (wurzel / "site" / "geraete.html").read_text(encoding="utf-8")
    fragment = (wurzel / "site" / "data" / "geraete-zeitreihe.html").read_text(
        encoding="utf-8"
    )
    return seite, BeautifulSoup(fragment, "html.parser")


def _panels(fragment: BeautifulSoup) -> list[tuple[str, BeautifulSoup]]:
    """(Anbieter, Inhalt) je Rechenweg-Vorlage des Fragments."""
    return [
        (v["data-anb"], BeautifulSoup(v.decode_contents(), "html.parser"))
        for v in fragment.select("template[data-anb]")
    ]


def test_panel_von_eins_und_eins_nennt_36_monate(gerendert):
    _, fragment = gerendert
    etiketten: dict[str, set] = {"1&1": set(), "o2": set()}
    for anbieter, inhalt in _panels(fragment):
        etikett = inhalt.select_one(".gr-zr-plabel")
        if anbieter in etiketten and etikett is not None:
            etiketten[anbieter].add(etikett.get_text(strip=True))
    assert etiketten["1&1"], "keine Rechenweg-Panels von 1&1 im Bestand"
    falsch = sorted(etiketten["1&1"] - {"Kosten über 36 Monate"})
    assert not falsch, (
        f"Kosten über 36 Monate: erwartet im Panel von 1&1, steht {falsch}"
    )


def test_panel_von_o2_bleibt_bei_24_monaten(gerendert):
    """Gegenprobe: die aufgeteilte Preisform trägt weiter 24 Monate."""
    _, fragment = gerendert
    etiketten = {
        etikett.get_text(strip=True)
        for anbieter, inhalt in _panels(fragment)
        if anbieter == "o2" and (etikett := inhalt.select_one(".gr-zr-plabel"))
    }
    assert etiketten == {"Kosten über 24 Monate"}, etiketten


def test_monatsnamen_sind_deutsch_auch_unter_englischem_locale(gerendert):
    seite, fragment = gerendert
    panel = {
        m
        for _, inhalt in _panels(fragment)
        for m in DATUM.findall(inhalt.get_text(" "))
    }
    assert "Oktober" in panel, f"Monatsname: erwartet „Oktober“ im Panel, steht {panel}"
    monate = panel | set(DATUM.findall(fragment.get_text(" ")))
    monate |= set(DATUM.findall(BeautifulSoup(seite, "html.parser").get_text(" ")))
    assert monate <= DEUTSCHE_MONATE, f"Monatsname nicht deutsch: {monate}"
