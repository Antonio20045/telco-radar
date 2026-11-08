"""Das Paar-Bild ist kein Beleg eines Tarifs (Ziel 1d, 08.11.2026), an der Seite.

Ein Bild gehört zum Paar (Modell, Anbieter), nicht zu einer Preiszeile; welchen Tarif es
zeigt, ist maschinell nicht feststellbar. Darum zeigt die Seite es nie: ohne
bestätigende Preiszeile steht je Anbieter der Vermerk „Für diese Kombination liegt noch
kein Screenshot vor“, kein Bild, kein Link, keine Paar-Quote. Feste Daten, nie das
heutige Datum (CLAUDE.md Regel 7). Die Seite wird mit `render_site` gebaut (kleiner
Bestand aus `test_geraete_buendel_kopf_zeitraum`), danach wird das DOM gelesen.
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
    zeigt kein Bild, nur den Vermerk je Anbieter (nichts Fremdes als Ersatz)."""
    zone = seite.select_one("#gr-bnd-gruppe .gr-beleg-paare")
    assert zone.select("img, details, a") == []
    assert "zeigt nicht jeden Tarif" not in seite.get_text(" ", strip=True)
    assert seite.select_one("#gr-belegquote") is None
    assert seite.select("details.gr-belege") == []
    namen = [b.get_text(strip=True) for b in seite.select(".gr-beleg-anbieter")]
    assert sorted(namen) == sorted(MIT_BILD + OHNE_BILD)


def test_jeder_anbieter_ohne_zeilenbild_bekommt_den_sichtbaren_vermerk(seite):
    """ "Kein Preis" und "kein Bild" sind unterscheidbar, nichts erfunden."""
    zeilen = seite.select("#gr-bnd-gruppe .gr-beleg-paare li.gr-beleg-paar")
    je_anbieter = {
        z.select_one(".gr-beleg-anbieter").get_text(strip=True): z for z in zeilen
    }
    assert sorted(je_anbieter) == sorted(MIT_BILD + OHNE_BILD)
    for z in je_anbieter.values():
        keins = z.select_one(".gr-beleg-keins")
        assert keins.get_text(strip=True).startswith(
            "Für diese Kombination liegt noch kein Screenshot vor."
        )
        assert not keins.has_attr("hidden")
        assert z.select("details, img, a") == []
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


def test_lager_traegt_die_paarzeile_fuer_den_modellwechsel(lager):
    """app.js übernimmt `.gr-beleg-paare` aus dem Lager (wie die Fehlliste)."""
    paare = lager.select(f'.gr-bnd-lager[data-modell="{MODELL}"] .gr-beleg-paare')
    assert len(paare) == 1


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


def test_im_browser_steht_je_anbieter_der_vermerk_ohne_bild(site, chromium):
    """Sichtbar gezählt wie ein Leser, 1440 und 390 px: Vermerke, kein Bild."""
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
                keins = s.locator(
                    "#gr-bnd-gruppe .gr-beleg-paar:visible .gr-beleg-keins"
                )
                assert keins.count() >= 1, breite
                for i in range(keins.count()):
                    assert keins.nth(i).is_visible(), breite
                assert s.locator("#gr-bnd-gruppe .gr-beleg-paare img").count() == 0
                assert s.evaluate("document.documentElement.scrollWidth") <= breite, (
                    breite
                )
            finally:
                ctx.close()
    finally:
        httpd.shutdown()
