"""Das Paar-Bild ist kein Beleg eines Tarifs (Ziel 1d, 08.11.2026), an der Seite.

Ein Bild gehört zum Paar (Modell, Anbieter), nicht zu einer Preiszeile; welchen Tarif es
zeigt, ist maschinell nicht feststellbar. Darum zeigt die Seite es nie: kein Bild, kein
Link, keine Paar-Quote.

Antonio, 12.12.2026: bestätigt KEINE Preiszeile des Modells ein Bild, steht hier auch
der Vermerk nicht mehr - acht Zeilen „Für diese Kombination liegt noch kein Screenshot
vor“ unter dem Graphen sagen zusammen nichts. Der Vermerk je Anbieter OHNE Bild steht,
sobald ein Anbieter des Modells ein Zeilenbild hat; genau dort prüft ihn
`test_beleg_position` (o2 mit Bild, die übrigen mit Vermerk und Grund). Diese Datei
prüft den anderen Fall: Paar-Bilder da, keine belegte Zeile - nichts als die Zeilen.

Feste Daten, nie das heutige Datum (CLAUDE.md Regel 7). Die Seite wird mit `render_site`
gebaut (kleiner Bestand aus `test_geraete_buendel_kopf_zeitraum`), danach wird das DOM
gelesen.
"""

from __future__ import annotations

import json
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


def test_paar_bild_steht_nie_als_beleg_auf_der_seite(seite):
    """Telekom und o2 haben ein Paar-Bild im Manifest, aber keinen Bildsatz: die Seite
    zeigt kein Bild, keinen Link, keine Quote - nichts Fremdes als Ersatz."""
    gruppe = seite.select_one("#gr-bnd-gruppe")
    assert gruppe.select("img, details.gr-belege, a[href*='releases']") == []
    assert "zeigt nicht jeden Tarif" not in seite.get_text(" ", strip=True)
    assert seite.select_one("#gr-belegquote") is None
    assert seite.select("details.gr-belege") == []
    assert seite.select(".gr-beleg-anbieter") == []


def test_ohne_eine_belegte_zeile_steht_keine_belegliste(seite, lager):
    """Kein Anbieter des Modells hat ein Zeilenbild: weder Liste noch Vermerk, auf
    der Seite und im Lager. Gegenprobe: die Bündelzeilen des Modells stehen."""
    assert seite.select("#gr-bnd-gruppe .gr-beleg-paare") == []
    assert seite.select(".gr-beleg-keins") == []
    modell = lager.select_one(f'.gr-bnd-lager[data-modell="{MODELL}"]')
    assert modell.select(".gr-beleg-paare") == []
    assert modell.select(".gr-bnd"), "Gegenprobe: das Modell hat Bündelzeilen"
    assert "liegt noch kein Screenshot vor" not in seite.get_text(" ", strip=True)
    assert "ohne Beleg" not in seite.get_text(" ", strip=True)


def test_keine_zeile_traegt_einen_beleg_link_oder_vermerk(lager, seite):
    """Muss 2: kein Zeilenlink ohne Preisbezug, weder im Lager noch auf der Seite."""
    zeilen = lager.select(".gr-bnd") + seite.select(".gr-bnd")
    assert zeilen, "Gegenprobe: die Fixture hat Bündelzeilen"
    for z in zeilen:
        assert z.select("a[href*='releases']") == []
        assert z.select(".gr-kk-marke--beleg, .gr-kk-marke--ohnebeleg") == []
        assert "Screenshot" not in z.get_text()
        assert "ohne Beleg" not in z.get_text()


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


def test_paar_ohne_belastbaren_preis_zaehlt_nicht(tmp_path):
    g = paarfunktion(tmp_path, {f"belege-{HEUTE}": [_bild("o2")]})
    modell = {"id": MODELL, "zeilen_band": [karte("o2", "X", 24, preis=False)]}
    assert anzeige(modell["zeilen_band"][0])["belastbar"] is False
    assert g["paarbelege"](modell) == []


def test_manifest_json_der_fixture_ist_lesbar(site):
    """Gegenprobe zur Fixture: das Manifest steht wirklich im Bestand."""
    pfad = site.parent / "data" / "state" / MANIFEST_NAME
    assert len(json.loads(pfad.read_text(encoding="utf-8"))["belege"]) == 2


def test_im_browser_steht_ohne_belegte_zeile_keine_belegstelle(site, chromium):
    """Sichtbar gezählt wie ein Leser, 1440 und 390 px: kein Bild, kein Vermerk.

    Bis zum 12.12.2026 standen hier die Vermerke je Anbieter. Dass sie sichtbar
    stehen, SOBALD ein Anbieter ein Bild hat, zählt `test_beleg_kombi` im Browser;
    hier hat kein Anbieter eines, und dann bleibt die Stelle leer - Gegenprobe:
    die Fehlliste der Anbieter steht an derselben Stelle sichtbar da."""
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
                assert s.locator("#gr-bnd-gruppe .gr-beleg-keins").count() == 0, breite
                assert s.locator("#gr-bnd-gruppe .gr-beleg-paare").count() == 0, breite
                assert s.locator("#gr-bnd-gruppe img").count() == 0, breite
                fehlliste = s.locator("#gr-bnd-gruppe .gr-anb-fehlliste:visible")
                assert fehlliste.count() == 1, breite
                assert s.evaluate("document.documentElement.scrollWidth") <= breite, (
                    breite
                )
            finally:
                ctx.close()
    finally:
        httpd.shutdown()
