"""Beleg je Paar (Ziel 1d, Nachbesserung 05.11.2026), geprüft an der gerenderten Seite.

Ein Bild gehört zum Paar (Modell, Anbieter), nicht zu einer Preiszeile; welchen Tarif
es zeigt, ist maschinell nicht feststellbar. Darum: kein Link an Preiszeilen, ein
sichtbarer Link je Anbieter auf der Seite, eine Quote in Paaren. Feste Daten, nie das
heutige Datum (CLAUDE.md Regel 7). Die Seite wird mit `render_site` gebaut (kleiner
Bestand aus `test_geraete_buendel_kopf_zeitraum`), danach wird das DOM gelesen.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest
import test_geraete_buendel_kopf_zeitraum as kopf_zeitraum
from bs4 import BeautifulSoup
from test_geraete_browser_fixture import HEUTE

from telco_radar.beleg_manifest import MANIFEST_NAME, baue_manifest, schreibe
from telco_radar.beleg_regeln import dateiname
from telco_radar.report import geraete_belege
from telco_radar.report.geraete_preisstand import anzeige
from telco_radar.report.html import render_site

MODELL = kopf_zeitraum.MODELL
baue_bestand = kopf_zeitraum._baue

TAG = date.fromisoformat(HEUTE)
SATZ = re.compile(
    r"^Screenshot der Angebotsseite vom \d{1,2}\. [A-Za-zä]+ \d{4} "
    r"\(zeigt nicht jeden Tarif\)$"
)
MIT_BILD = ("Telekom", "o2")
OHNE_BILD = ("congstar", "Vodafone")


def _bild(anbieter_id: str) -> str:
    return dateiname(MODELL, anbieter_id, TAG)


def _lies(pfad: Path) -> BeautifulSoup:
    return BeautifulSoup(pfad.read_text(encoding="utf-8"), "html.parser")


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    """Die Seite mit Bildern für o2 und Telekom, nicht für congstar und Vodafone."""
    site = baue_bestand(tmp_path_factory.mktemp("beleg_paar"))
    wurzel = site.parent
    anhaenge = {f"belege-{HEUTE}": [_bild("telekom"), _bild("o2")]}
    schreibe(wurzel / "data" / "state" / MANIFEST_NAME, baue_manifest(anhaenge, TAG))
    render_site(site, wurzel / "data" / "reports")
    return site


@pytest.fixture(scope="module")
def seite(site) -> BeautifulSoup:
    return _lies(site / "geraete.html")


@pytest.fixture(scope="module")
def lager(site) -> BeautifulSoup:
    return _lies(site / "data" / "geraete-buendel.html")


def test_sichtbare_links_je_anbieter_mit_bild_auf_der_echten_seite(seite):
    """Muss 1: die Links stehen im sichtbaren Teil, nicht im versteckten Lager."""
    paare = seite.select("#gr-bnd-gruppe .gr-beleg-paare details.gr-belege--paar")
    assert len(paare) == len(MIT_BILD)
    for p in paare:
        assert SATZ.match(p.summary.get_text(strip=True)), p.summary
        assert p.find_parent(class_="gr-bnd-lager") is None
        bild = p.select_one("img")
        assert f"/belege-{HEUTE}/{MODELL}__" in bild["data-src"]
    namen = [b.get_text(strip=True) for b in seite.select(".gr-beleg-anbieter")]
    assert sorted(namen) == sorted(MIT_BILD + OHNE_BILD)


def test_paar_ohne_bild_bekommt_sichtbaren_vermerk_ohne_link(seite):
    """Auflage 1: "kein Preis" und "kein Bild" sind unterscheidbar, nichts erfunden."""
    zeilen = seite.select("#gr-bnd-gruppe .gr-beleg-paare li")
    je_anbieter = {
        z.select_one(".gr-beleg-anbieter").get_text(strip=True): z for z in zeilen
    }
    assert sorted(je_anbieter) == sorted(MIT_BILD + OHNE_BILD)
    for anbieter in OHNE_BILD:
        z = je_anbieter[anbieter]
        assert z.select_one(".gr-beleg-fehlt").get_text(strip=True) == (
            "kein Screenshot vorhanden"
        )
        assert z.select("details, img, a") == []
    for anbieter in MIT_BILD:
        assert je_anbieter[anbieter].select(".gr-beleg-fehlt") == []
    assert "ohne Beleg" not in seite.get_text(" ", strip=True)


def test_bild_oeffnet_in_der_seite_nicht_als_download(seite):
    """Kein Link auf das Release-Asset (Download): das Bild liegt im Aufklapper."""
    zone = seite.select_one(".gr-beleg-paare")
    assert zone.select("a") == []
    assert zone.select("details img[data-src]")


def test_keine_zeile_traegt_einen_beleg_link_oder_vermerk(lager, seite):
    """Muss 2: kein Zeilenlink ohne Preisbezug, weder im Lager noch auf der Seite."""
    zeilen = lager.select(".gr-bnd") + seite.select(".gr-bnd")
    assert zeilen, "Gegenprobe: die Fixture hat Bündelzeilen"
    for z in zeilen:
        assert z.select("a[href*='releases']") == []
        assert z.select(".gr-kk-marke--beleg, .gr-kk-marke--ohnebeleg") == []
        assert "Screenshot" not in z.get_text()
        assert "ohne Beleg" not in z.get_text()


def test_lager_traegt_die_paarzeile_fuer_den_modellwechsel(lager):
    """app.js übernimmt `.gr-beleg-paare` aus dem Lager (wie die Fehlliste)."""
    paare = lager.select(f'.gr-bnd-lager[data-modell="{MODELL}"] .gr-beleg-paare')
    assert len(paare) == 1


def test_quote_zaehlt_paare_mit_neutralem_wortlaut(seite):
    """Muss 3 und Sollte 6: Paare, genau dieser Satz, keine Warnfarbe."""
    absatz = seite.select_one("#gr-belegquote")
    assert absatz.get_text(strip=True) == (
        "Für 2 von 4 Gerät-Anbieter-Paaren liegt ein Screenshot der Angebotsseite vor."
    )
    assert "gr-basis--duenn" not in absatz.get("class", [])
    assert "Preisen" not in absatz.get_text()


def karte(anbieter: str, tarif: str, laufzeit: int, *, preis: bool = True) -> dict:
    return {
        "anbieter": anbieter,
        "tarif": tarif,
        "belastbar": preis,
        "laufzeit_monate": laufzeit,
        "gesamt": 900.0 if preis else None,
        "zustand": "neu",
    }


class Umgebung:
    """Mimt die Jinja-Umgebung, die `installiere` mit `env.globals` füllt."""

    def __init__(self) -> None:
        self.globals: dict = {}


def paarfunktion(tmp_path: Path, bilder: dict[str, list[str]]):
    schreibe(tmp_path / MANIFEST_NAME, baue_manifest(bilder, TAG))

    env = Umgebung()
    geraete_belege.installiere(env, tmp_path, [{"date": HEUTE}])
    return env.globals


def test_24_und_36_raten_desselben_tarifs_zaehlen_einmal(tmp_path):
    g = paarfunktion(tmp_path, {f"belege-{HEUTE}": [_bild("o2")]})
    modell = {
        "id": MODELL,
        "zeilen_band": [karte("o2", "Allnet XS", 24), karte("o2", "Allnet XS", 36)],
        "zeilen_ohne_band": [karte("o2", "Flat", 24), karte("Telekom", "S", 24)],
    }
    paare = g["paarbelege"](modell)
    assert [p["anbieter"] for p in paare] == ["o2", "Telekom"]
    assert paare[0]["beleg"] and paare[1]["beleg"] is None
    q = g["belegquote"]([modell])
    assert (q["mit"], q["gesamt"]) == (1, 2)


def test_paar_ohne_belastbaren_preis_zaehlt_nicht(tmp_path):
    g = paarfunktion(tmp_path, {f"belege-{HEUTE}": [_bild("o2")]})
    modell = {"id": MODELL, "zeilen_band": [karte("o2", "X", 24, preis=False)]}
    assert anzeige(modell["zeilen_band"][0])["belastbar"] is False
    assert g["paarbelege"](modell) == []
    assert g["belegquote"]([modell])["satz"] == ""


def test_unlesbare_belegliste_behauptet_keine_quote(tmp_path):
    (tmp_path / MANIFEST_NAME).write_text("{kaputt", encoding="utf-8")

    env = Umgebung()
    assert geraete_belege.installiere(env, tmp_path, [{"date": HEUTE}])
    modell = {"id": MODELL, "zeilen_band": [karte("o2", "X", 24)]}
    q = env.globals["belegquote"]([modell])
    assert q["gesamt"] == 1 and q["satz"] == ""


def test_manifest_json_der_fixture_ist_lesbar(site):
    """Gegenprobe zur Fixture: das Manifest steht wirklich im Bestand."""
    pfad = site.parent / "data" / "state" / MANIFEST_NAME
    assert len(json.loads(pfad.read_text(encoding="utf-8"))["belege"]) == 2


def test_im_browser_sichtbar_und_oeffnet_das_bild(site, chromium):
    """Sichtbar gezählt wie ein Leser: Zeilen im Layout, Klick lädt das Bild."""
    import functools
    import http.server
    import threading

    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(site)
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        for breite in (1440, 390):
            ctx = chromium.new_context(viewport={"width": breite, "height": 900})
            try:
                s = ctx.new_page()
                url = f"http://127.0.0.1:{httpd.server_address[1]}/geraete.html"
                s.goto(url, wait_until="domcontentloaded")
                zeilen = s.locator("#gr-bnd-gruppe .gr-beleg-paare summary")
                assert zeilen.count() == len(MIT_BILD)
                for i in range(zeilen.count()):
                    assert zeilen.nth(i).is_visible(), breite
                assert s.locator(".gr-bnd-lager .gr-beleg-paare:visible").count() == 0
                fehlt = s.locator("#gr-bnd-gruppe .gr-beleg-fehlt")
                assert fehlt.count() == len(OHNE_BILD), breite
                for i in range(fehlt.count()):
                    assert fehlt.nth(i).is_visible(), breite
                    assert fehlt.nth(i).inner_text() == "kein Screenshot vorhanden"
                assert s.locator("#gr-belegquote").is_visible()
                zeilen.first.click()
                bild = s.locator("#gr-bnd-gruppe .gr-beleg-paare details[open] img")
                s.wait_for_function(
                    "document.querySelector('#gr-bnd-gruppe details[open] img')"
                    ".hasAttribute('src')"
                )
                assert bild.get_attribute("src").startswith("https://"), breite
                assert s.evaluate("document.documentElement.scrollWidth") <= breite, (
                    breite
                )
            finally:
                ctx.close()
    finally:
        httpd.shutdown()
