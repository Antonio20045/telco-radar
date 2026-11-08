"""Beleg je Preisposition (Ziel 1d): ein Bild hängt nur an der Zeile, die es zeigt.

Fail-closed: ein Beleg mit abweichendem Gerät oder Tarif wird abgelehnt, ein Paar mit
gleich teuren Positionen, mit neuerem Abruf oder ohne Klick-Messung bekommt keine Zeile
mit Bild. Feste Daten, nie das heutige Datum (CLAUDE.md Regel 7). Die Seite wird mit
``render_site`` gebaut und als DOM gelesen.
"""

from __future__ import annotations

import functools
import http.server
import json
import threading
from datetime import date, timedelta
from pathlib import Path

import pytest
import test_geraete_buendel_kopf_zeitraum as kopf_zeitraum
from bs4 import BeautifulSoup
from test_geraete_browser_fixture import HEUTE

from telco_radar.analyze import beleg_position as schluessel
from telco_radar.beleg_manifest import MANIFEST_NAME, baue_manifest, schreibe
from telco_radar.beleg_regeln import dateiname
from telco_radar.report import geraete_zeilenbelege as zeilen
from telco_radar.report.html import render_site

MODELL = kopf_zeitraum.MODELL
TAG = date.fromisoformat(HEUTE)
GESTERN = TAG - timedelta(days=1)
VERMERK = "Kein Screenshot zu genau dieser Zeile."
ID_O2 = "a" * 64
ID_TK_1 = "b" * 64
ID_TK_2 = "c" * 64
ID_CS = "d" * 64


def _satz(anbieter, tarif, tarif_id, laufzeit, rate, beleg_id, sku=None, tag=HEUTE):
    return {
        "id": f"buendel--{anbieter.lower()}--{tarif_id}--{laufzeit}--{beleg_id[:4]}",
        "sku_id": sku or "apple-iphone-17-pro-256gb-ohne-farbe",
        "anbieter": anbieter,
        "tarif_name": tarif,
        "tarif_id": tarif_id,
        "tarif_id_guete": "hoch",
        "tarif_monatlich": 24.99,
        "tarif_bindung_monate": 24,
        "geraet_zuzahlung": 1.0,
        "geraet_monatsrate": rate,
        "laufzeit_monate": laufzeit,
        "anschlusspreis": 0.0,
        "zustand": "neu",
        "rabatte": [],
        "quelle_url": f"https://example.de/{anbieter.lower()}",
        "abgerufen_am": tag,
        "first_seen": tag,
        "last_verified": tag,
        "quelle_art": "klick",
        "beleg_id": beleg_id,
        "beleg_status": "offen",
    }


def _bild(anbieter_id: str, tag: date = TAG) -> str:
    return dateiname(MODELL, anbieter_id, tag)


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    """o2: eindeutig (ein Satz). Telekom: zwei gleich teure Sätze. congstar: Bild von
    gestern, Satz von heute. Vodafone: Bild, aber keine Klick-Messung."""
    site = kopf_zeitraum._baue(tmp_path_factory.mktemp("beleg_position"))
    wurzel = site.parent
    state = wurzel / "data" / "state"
    farbe = "apple-iphone-17-pro-256gb-orange"
    saetze = [
        _satz("o2", "O2 Mobile Klein", "o2:klein", 24, 18.0, ID_O2),
        _satz("Telekom", "MagentaMobil S", "tk:klein", 24, 12.0, ID_TK_1),
        _satz("Telekom", "MagentaMobil S", "tk:klein", 24, 12.0, ID_TK_2, sku=farbe),
        _satz("congstar", "Allnet Flat XS", "cs:klein", 24, 15.0, ID_CS),
    ]
    vodafone = json.loads((state / "geraete_tco.json").read_text(encoding="utf-8"))
    vodafone = [b for b in vodafone["buendel"] if b["anbieter"] == "Vodafone"]
    (state / "geraete_tco.json").write_text(
        json.dumps({"updated": HEUTE, "buendel": [*saetze, *vodafone], "sim_only": []}),
        encoding="utf-8",
    )
    anhaenge = {
        f"belege-{HEUTE}": [_bild("o2"), _bild("telekom"), _bild("vodafone")],
        f"belege-{GESTERN.isoformat()}": [_bild("congstar", GESTERN)],
    }
    schreibe(state / MANIFEST_NAME, baue_manifest(anhaenge, TAG))
    render_site(site, wurzel / "data" / "reports")
    return site


@pytest.fixture(scope="module")
def seite(site) -> BeautifulSoup:
    return BeautifulSoup(
        (site / "geraete.html").read_text(encoding="utf-8"), "html.parser"
    )


@pytest.fixture(scope="module")
def lager(site) -> BeautifulSoup:
    return BeautifulSoup(
        (site / "data" / "geraete-buendel.html").read_text(encoding="utf-8"),
        "html.parser",
    )


def _text(element) -> str:
    """Der Text eines Elements samt ``<template>``-Inhalt."""
    return "".join(element.find_all(string=True)).strip()


def _paare(seite: BeautifulSoup) -> dict[str, object]:
    """Die Paar-Einträge im sichtbaren Teil der Seite, je Anbieter."""
    return {
        li.select_one(".gr-beleg-anbieter").get_text(strip=True): li
        for li in seite.select("#gr-bnd-gruppe > .gr-beleg-paare > li.gr-beleg-paar")
    }


def _anzahl(lager: BeautifulSoup) -> dict[str, int]:
    je_anbieter: dict[str, int] = {}
    for z in lager.select(".gr-bnd"):
        je_anbieter[z["data-anbieter"]] = je_anbieter.get(z["data-anbieter"], 0) + 1
    return je_anbieter


def test_die_eindeutige_zeile_steht_im_paar_eintrag_mit_ihrem_bild(lager, seite):
    """Positiv: o2 hat einen Satz; jede o2-Zeile steht im sichtbaren Paar-Eintrag
    mit Tarif, Raten und Preis, das Bild gehört genau zu ihr."""
    n_o2 = _anzahl(lager)["o2"]
    assert n_o2, "Gegenprobe: die Fixture hat o2-Zeilen"
    zeilen = _paare(seite)["o2"].select(".gr-beleg-zeile details.gr-belege--zeile")
    assert len(zeilen) == n_o2
    for z in zeilen:
        assert (
            f"/belege-{HEUTE}/{_bild('o2')}"
            in z.select_one("img[data-src]")["data-src"]
        )
        titel = _text(z.summary)
        assert "O2 Mobile Klein" in titel
        assert "24 Raten" in titel
        assert "Zuordnung über die Messung" in titel
        assert "€" in titel


def test_unklare_zuordnung_zeigt_kein_zeilenbild_sondern_den_grund(lager, seite):
    """Fail-closed: gleich teure Sätze (Telekom), neuerer Abruf als das Bild (congstar)
    und fehlende Klick-Messung (Vodafone) ergeben nie ein Bild an einer Zeile, obwohl
    die Paare ein Seiten-Bild haben; der Paar-Eintrag nennt die Zahl und den Grund."""
    paare = _paare(seite)
    n = _anzahl(lager)
    gruende = {
        "Telekom": schluessel.GRUND_GLEICHSTAND,
        "congstar": schluessel.GRUND_BESTAND_NEUER,
        "Vodafone": schluessel.GRUND_KEIN_KLICKSATZ,
    }
    for anbieter, grund in gruende.items():
        assert n[anbieter], f"Gegenprobe: Zeilen für {anbieter}"
        li = paare[anbieter]
        assert li.select("details, img, .gr-beleg-zeile") == []
        text = li.select_one(".gr-beleg-keins").get_text(strip=True)
        assert text == (
            f"Für diese Kombination liegt noch kein Screenshot vor. ({grund})"
        )


def test_quote_nennt_je_anbieter_zeilen_nicht_paare(lager, seite):
    """Die Seite zählt Zeilen je Anbieter, ehrlich auch bei 0, und sagt, dass die
    Zuordnung über die Messung läuft und das Bild nur die Preisfelder zeigt."""
    n = _anzahl(lager)
    satz = seite.select_one("#gr-zeilenquote").get_text(strip=True)
    erwartet = (
        "Preiszeilen mit eigenem Screenshot, Zuordnung über die Messung "
        "(aus dem Bild allein nicht ablesbar): "
        f"congstar 0 von {n['congstar']} · o2 {n['o2']} von {n['o2']} · "
        f"Telekom 0 von {n['Telekom']} · Vodafone 0 von {n['Vodafone']}; "
        f"zusammen {n['o2']} von {sum(n.values())}."
    )
    assert satz == erwartet
    assert "Paaren" not in satz
    assert "Tarif und Laufzeit stimmen" not in satz


def test_paar_nennt_seine_zeilen_mit_bild(lager, seite):
    n_o2 = _anzahl(lager)["o2"]
    o2 = _paare(seite)["o2"]
    assert len(o2.select(".gr-beleg-zeile")) == n_o2
    assert o2.select_one(".gr-beleg-keins").has_attr("hidden")


def test_fragment_traegt_keine_zeilenbilder_an_der_buendelliste(lager):
    """Die Bündelliste ist von der Seite genommen: dort steht kein Zeilenbild."""
    assert (
        lager.select(".gr-bnd details.gr-belege, .gr-bnd .gr-beleg-zeilenfehlt") == []
    )


ZEILE = "#gr-bnd-gruppe .gr-beleg-zeile:not([hidden]) details.gr-belege--zeile"
OFFEN = "#gr-bnd-gruppe .gr-belege--zeile[open] img"
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360f8cfc0f01f0005000201a5f645400000000049454e44ae426082"
)


def _pruefe_breite(chromium, adresse: str, breite: int) -> list[str]:
    """Öffnet die Seite in dieser Breite, klappt ein Zeilenbild auf, gibt die
    Konsolenmeldungen zurück."""
    meldungen: list[str] = []
    ctx = chromium.new_context(viewport={"width": breite, "height": 900})
    try:
        ctx.route(
            "https://github.com/**",
            lambda r: r.fulfill(body=PNG, content_type="image/png"),
        )
        s = ctx.new_page()
        s.on("console", lambda m: meldungen.append(m.text))
        s.on("pageerror", lambda e: meldungen.append(str(e)))
        s.goto(adresse, wait_until="domcontentloaded")
        zeile = s.locator(f"{ZEILE} > summary").first
        assert zeile.is_visible(), breite
        assert "Zuordnung über die Messung" in zeile.inner_text()
        zeile.click()
        s.wait_for_function(f"document.querySelector('{OFFEN}').hasAttribute('src')")
        assert s.locator(OFFEN).is_visible(), breite
        s.wait_for_function(f"document.querySelector('{OFFEN}').complete")
        assert s.evaluate("document.documentElement.scrollWidth") <= breite
    finally:
        ctx.close()
    return meldungen


@pytest.mark.browser
def test_zeilenbild_im_echten_seitenfluss_sichtbar_und_aufklappbar(site, chromium):
    """Playwright auf der gebauten Seite (1440 und 390 px): der Zeilenbild-Aufklapper
    ist sichtbar, öffnet das Bild, kein Querscrollen, Konsole leer."""
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(site)
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        adresse = f"http://127.0.0.1:{httpd.server_address[1]}/geraete.html"
        for breite in (1440, 390):
            assert _pruefe_breite(chromium, adresse, breite) == [], breite
    finally:
        httpd.shutdown()


def _roh(beleg_id, rate, tag=HEUTE, **extra):
    satz = _satz("o2", "O2 Mobile Klein", "o2:klein", 24, rate, beleg_id, tag=tag)
    return {**satz, **extra}


def test_eindeutiger_spitzenreiter_ist_die_position():
    wahl = schluessel.position_des_bildes(
        [_roh("1" * 64, 30.0), _roh("2" * 64, 18.0)], HEUTE
    )
    assert wahl.satz is not None and wahl.satz["beleg_id"] == "2" * 64


@pytest.mark.parametrize(
    ("saetze", "grund"),
    [
        ([], schluessel.GRUND_KEIN_KLICKSATZ),
        ([_roh("", 18.0)], schluessel.GRUND_KEIN_KLICKSATZ),
        (
            [_roh("1" * 64, 18.0), _roh("2" * 64, 18.0)],
            schluessel.GRUND_GLEICHSTAND,
        ),
        (
            [_roh("1" * 64, 18.0), _roh("2" * 64, 30.0, tag="2026-09-12")],
            schluessel.GRUND_BESTAND_NEUER,
        ),
        ([_roh("1" * 64, 18.0, tag="2026-09-10")], schluessel.GRUND_KEIN_SATZ_VOM_TAG),
        ([_roh("1" * 64, 18.0, geraet_monatsrate=None)], schluessel.GRUND_KEINE_KOSTEN),
    ],
)
def test_ohne_beweis_keine_position(saetze, grund):
    wahl = schluessel.position_des_bildes(saetze, HEUTE)
    assert wahl.satz is None
    assert wahl.grund == grund


def _beleg() -> zeilen.Zeilenbeleg:
    return zeilen.Zeilenbeleg(
        geraet_id=MODELL,
        anbieter_id="o2",
        sku_id="apple-iphone-17-pro-256gb-ohne-farbe",
        tarif="O2 Mobile Klein",
        tarif_id="o2:klein",
        raten_laufzeit=24,
        beleg_id=ID_O2,
        datum=HEUTE,
        gross=False,
        url="https://example.de/bild.webp",
    )


def _karte(**abweichung) -> dict:
    karte = {
        "beleg_id": ID_O2,
        "modell_id": MODELL,
        "anbieter": "o2",
        "sku_id": "apple-iphone-17-pro-256gb-ohne-farbe",
        "tarif": "O2 Mobile Klein",
        "tarif_id": "o2:klein",
        "raten_laufzeit": 24,
    }
    return {**karte, **abweichung}


def test_passende_karte_wird_angenommen():
    assert zeilen.passt(_beleg(), _karte())


@pytest.mark.parametrize(
    "abweichung",
    [
        {"modell_id": "apple-iphone-17-pro-512"},
        {"anbieter": "Telekom"},
        {"sku_id": "apple-iphone-17-pro-256gb-orange"},
        {"tarif": "O2 Mobile Groß"},
        {"tarif_id": "o2:gross"},
        {"raten_laufzeit": 36},
        {"beleg_id": "e" * 64},
        {"beleg_id": ""},
    ],
)
def test_beleg_mit_abweichendem_geraet_oder_tarif_wird_abgelehnt(abweichung):
    """Das Bild einer anderen Variante oder eines anderen Tarifs ist nie ein Beleg."""
    assert not zeilen.passt(_beleg(), _karte(**abweichung))
    fuer = zeilen.zeilenbeleg_fuer({ID_O2: _beleg()})
    assert fuer(_karte(**abweichung)) is None
    assert fuer(_karte()) is not None


def test_bestand_ohne_datei_hat_keine_saetze_ein_kaputter_ist_ein_fehler(tmp_path):
    datei = tmp_path / "geraete_tco.json"
    assert schluessel.lies_buendel(datei) == []
    datei.write_text("{kaputt", encoding="utf-8")
    with pytest.raises(ValueError, match="geraete_tco.json"):
        schluessel.lies_buendel(datei)
