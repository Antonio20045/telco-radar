"""Live-Abnahme 09.11.2026, Auflagen L1 und L2 - im echten Chromium.

L1: Nach einem Wechsel von Gerät (Speicher) steht der Beleg (Bild und Text) des vorigen
Geräts nicht mehr da, auch nicht 0,3 bis 0,5 s: er ist sofort leer oder ein Ladezustand.
Ein Fragment oder Bild, das verspätet eintrifft und nicht mehr zur Wahl passt, wird nie
angezeigt. Die Verzögerung ist künstlich (Playwright-Route), die Prüfung ist DOM-nah:
direkt im selben Task wie der Wechsel und in jedem Frame danach.
L2: Die Tabelle „Alle Geräte“ trägt an einer Zeile mit älterem Messtag
„Stand vom TT.MM.“ (dieselbe Logik wie die Messdatum-Zeile,
``geraete_messdatum.stand_vom``).
Feste Daten, nie das heutige Datum (CLAUDE.md Regel 7).
"""

from __future__ import annotations

import functools
import http.server
import json
import threading
from pathlib import Path

import pytest
import test_beleg_position as pos
import test_geraete_browser_fixture as fixture
import test_geraete_buendel_kopf_zeitraum as kopf
import test_geraete_messdatum as messdatum
from bs4 import BeautifulSoup

from telco_radar.beleg_manifest import MANIFEST_NAME, baue_manifest, schreibe
from telco_radar.report.html import render_site

MODELL_B = "samsung-galaxy-s26-256"
DEVICE_B = "samsung-galaxy-s26"
BILD_A = pos._bild("o2")
BILD_B = f"{MODELL_B}__o2__{pos.TAG.isoformat()}.webp"


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    """Zwei Geräte (iPhone 17 Pro 256 = Startgerät, Galaxy S26 256), jedes mit einem
    o2-Preis und einem eigenen Beleg-Bild."""
    site = kopf._baue(tmp_path_factory.mktemp("live_auflagen2"))
    wurzel = site.parent
    state = wurzel / "data" / "state"
    bestand = json.loads((state / "geraete_tco.json").read_text(encoding="utf-8"))
    vodafone = [b for b in bestand["buendel"] if b["anbieter"] == "Vodafone"]
    saetze = [
        pos._satz("o2", "O2 Mobile Klein", "o2:klein", 24, 18.0, pos.ID_O2),
        pos._satz(
            "o2",
            "O2 Mobile Klein",
            "o2:klein",
            24,
            19.0,
            "f" * 64,
            sku=fixture._sku(DEVICE_B, 256),
        ),
    ]
    (state / "geraete_tco.json").write_text(
        json.dumps({"updated": pos.HEUTE, "buendel": [*saetze, *vodafone]}),
        encoding="utf-8",
    )
    anhaenge = {f"belege-{pos.HEUTE}": [BILD_A, BILD_B]}
    schreibe(state / MANIFEST_NAME, baue_manifest(anhaenge, pos.TAG))
    render_site(site, wurzel / "data" / "reports")
    return site


@pytest.fixture(scope="module")
def adresse(site):
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(site)
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/geraete.html"
    httpd.shutdown()


def test_die_fixture_hat_zwei_geraete_mit_je_eigenem_beleg(site):
    """Gegenprobe: ohne zwei Belege prüfte der Browsertest nichts."""
    lager = BeautifulSoup(
        (site / "data" / "geraete-buendel.html").read_text(encoding="utf-8"),
        "html.parser",
    )
    bilder = {
        lg["data-modell"]: [i["data-src"] for i in lg.select(".gr-beleg-paare img")]
        for lg in lager.select(".gr-bnd-lager[data-modell]")
    }
    assert any(BILD_A in u for u in bilder.get(kopf.MODELL, [])), bilder
    assert any(BILD_B in u for u in bilder.get(MODELL_B, [])), bilder


_SPAEHER = """() => {
  window.__fremd = [];
  const lies = () => {
    const g = document.getElementById('gr-bnd-gruppe');
    const bilder = [...g.querySelectorAll('img')]
      .filter(i => i.getBoundingClientRect().height > 0 && i.complete
        && i.naturalWidth > 0)
      .map(i => i.getAttribute('src'));
    window.__fremd.push({t: performance.now(), bilder,
      text: g.textContent.replace(/\\s+/g, ' ').trim()});
    requestAnimationFrame(lies);
  };
  requestAnimationFrame(lies);
}"""

_WECHSEL = """(modell) => {
  const b = document.querySelector(
    '#gr-zr-vorschau button[data-modell="' + modell + '"]');
  window.__wechsel_t = performance.now();
  b.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true}));
  const g = document.getElementById('gr-bnd-gruppe');
  return {bilder: g.querySelectorAll('img').length,
          paare: g.querySelectorAll('.gr-beleg-paar').length,
          text: g.textContent.replace(/\\s+/g, ' ').trim()};
}"""

_GRUPPE = """() => [...document.querySelectorAll('#gr-bnd-gruppe img[data-src], '
  + '#gr-bnd-gruppe img[src]')]
  .map(i => i.getAttribute('data-src') || i.getAttribute('src'))"""

_GELADEN = """() => { const i = document.querySelector('#gr-bnd-gruppe img');
  return !!i && i.complete && i.naturalWidth > 0; }"""


class Netz:
    """Hält Anfragen an, bis der Test sie freigibt: künstlich verzögert, ohne die
    Playwright-Schleife zu blockieren (kein sleep im Handler)."""

    def __init__(self):
        self.halten = {"bnd": False, "bild": False}
        self.gehalten: list[tuple[str, object]] = []

    def bild(self, route):
        if self.halten["bild"]:
            self.gehalten.append(("bild", route))
        else:
            route.fulfill(body=pos.PNG, content_type="image/png")

    def fragment(self, route):
        if self.halten["bnd"]:
            self.gehalten.append(("bnd", route))
        else:
            route.continue_()

    def gebe_frei(self, art: str) -> None:
        self.halten[art] = False
        rest = []
        for k, route in self.gehalten:
            if k != art:
                rest.append((k, route))
            elif k == "bild":
                route.fulfill(body=pos.PNG, content_type="image/png")
            else:
                route.continue_()
        self.gehalten = rest


def _oeffne(chromium, adresse, breite=1440):
    ctx = chromium.new_context(viewport={"width": breite, "height": 900})
    netz = Netz()
    ctx.route("https://github.com/**", netz.bild)
    ctx.route("**/data/bnd/*.html", netz.fragment)
    s = ctx.new_page()
    meldungen: list[str] = []
    s.on("console", lambda m: meldungen.append(m.text))
    s.on("pageerror", lambda e: meldungen.append(str(e)))
    s.goto(adresse, wait_until="load")
    return ctx, s, netz, meldungen


def _nach_dem_wechsel(s):
    """Alle Frames ab dem Wechsel (der Späher läuft schon vorher)."""
    return s.evaluate("window.__fremd.filter(p => p.t >= window.__wechsel_t)")


def _zeige_vorschau(s, suchwort):
    s.fill("#gr-zr-suche", suchwort)
    s.wait_for_selector("#gr-zr-vorschau button")


def _kein_fremdes_bild(proben, fremd_bild: str):
    assert len(proben) > 10, "der Späher hat kaum Frames gesehen"
    fremd = [p for p in proben if any(fremd_bild in b for b in p["bilder"])]
    assert fremd == [], fremd[:2]


@pytest.mark.browser
def test_nach_dem_geraetewechsel_steht_sofort_kein_fremder_beleg(chromium, adresse):
    """Rot gegen main: das Fragment des neuen Geräts ist unterwegs, der Beleg des
    Startgeräts (Bild und Text) stand bis dahin weiter da. Jetzt ist er im selben Task
    weg, in keinem Frame steht ein Bild des alten Geräts, danach erscheint nur das
    neue."""
    ctx, s, netz, meldungen = _oeffne(chromium, adresse)
    try:
        s.locator("#gr-bnd-gruppe .gr-beleg-zeile summary").first.click()
        s.wait_for_function(_GELADEN)
        vorher = s.evaluate("document.getElementById('gr-bnd-gruppe').textContent")
        assert "O2 Mobile Klein" in vorher, "Gegenprobe: Beleg des Startgeräts steht"
        netz.halten["bnd"] = True
        s.evaluate(_SPAEHER)
        _zeige_vorschau(s, "galaxy s26")
        direkt = s.evaluate(_WECHSEL, MODELL_B)
        assert direkt["bilder"] == 0 and direkt["paare"] == 0, direkt
        assert "O2 Mobile Klein" not in direkt["text"], direkt
        s.wait_for_timeout(500)
        assert netz.gehalten, "Gegenprobe: das Fragment war wirklich unterwegs"
        assert s.locator("#gr-bnd-gruppe .gr-beleg-laedt").is_visible()
        netz.gebe_frei("bnd")
        s.wait_for_selector("#gr-bnd-gruppe .gr-beleg-paar:not([hidden])")
        s.locator("#gr-bnd-gruppe .gr-beleg-zeile summary").first.click()
        s.wait_for_function(_GELADEN)
        urls = s.evaluate(_GRUPPE)
        assert urls and all(BILD_B in u for u in urls), urls
        _kein_fremdes_bild(_nach_dem_wechsel(s), BILD_A)
        assert meldungen == []
    finally:
        ctx.close()


@pytest.mark.browser
def test_spaetes_fragment_eines_frueheren_geraets_ueberschreibt_nichts(
    chromium, adresse
):
    """Rot gegen main: Galaxy gewählt (Fragment unterwegs), sofort zurück aufs
    Startgerät. Das späte Galaxy-Fragment ersetzte den Beleg des Startgeräts, denn der
    Rückweg zählte die Folge nicht mit. Jetzt bleibt der Beleg des Startgeräts."""
    ctx, s, netz, meldungen = _oeffne(chromium, adresse)
    try:
        netz.halten["bnd"] = True
        _zeige_vorschau(s, "galaxy s26")
        s.evaluate(_WECHSEL, MODELL_B)
        _zeige_vorschau(s, "iphone 17 pro")
        s.evaluate(_WECHSEL, kopf.MODELL)
        s.wait_for_timeout(300)
        assert netz.gehalten, "Gegenprobe: das Galaxy-Fragment war unterwegs"
        netz.gebe_frei("bnd")
        s.wait_for_timeout(700)
        urls = s.evaluate(_GRUPPE)
        assert urls and all(BILD_A in u for u in urls), urls
        assert not any(BILD_B in u for u in urls), urls
        assert meldungen == []
    finally:
        ctx.close()


@pytest.mark.browser
@pytest.mark.parametrize("breite", [1440, 390])
def test_spaetes_bild_nach_schnellem_wechsel_wird_nie_gezeigt(
    chromium, adresse, breite
):
    """Das Bild des Startgeräts ist unterwegs, der Leser wechselt das Gerät, dessen
    Fragment auch noch fehlt. Trifft das Bild jetzt ein, passt es nicht mehr zur Wahl:
    es steht in keinem Frame sichtbar da (rot gegen main, dort blieb der alte Beleg
    samt Bild im Dokument)."""
    ctx, s, netz, meldungen = _oeffne(chromium, adresse, breite)
    try:
        netz.halten["bild"] = True
        s.evaluate(_SPAEHER)
        s.locator("#gr-bnd-gruppe .gr-beleg-zeile summary").first.click()
        s.wait_for_function("document.querySelector('#gr-bnd-gruppe img[src]')")
        s.wait_for_timeout(200)
        assert netz.gehalten, "Gegenprobe: das Bild war unterwegs"
        netz.halten["bnd"] = True
        _zeige_vorschau(s, "galaxy s26")
        s.evaluate(_WECHSEL, MODELL_B)
        netz.gebe_frei("bild")
        s.wait_for_timeout(500)
        _kein_fremdes_bild(_nach_dem_wechsel(s), BILD_A)
        netz.gebe_frei("bnd")
        s.wait_for_selector("#gr-bnd-gruppe .gr-beleg-paar:not([hidden])")
        s.wait_for_timeout(300)
        _kein_fremdes_bild(_nach_dem_wechsel(s), BILD_A)
        assert s.evaluate("document.documentElement.scrollWidth") <= breite
        assert meldungen == []
    finally:
        ctx.close()


def _ab_zellen(site) -> list[str]:
    """Die Zellen „Einzelgerätpreis“ der Tabelle „Alle Geräte“, die ein Datum tragen."""
    suppe = BeautifulSoup(
        (site / "geraete.html").read_text(encoding="utf-8"), "html.parser"
    )
    return [
        td.get_text(" ", strip=True)
        for td in suppe.select("#gr-katalogtabelle td.gr-sp--barpreis")
        if td.select_one(".gr-k-ab") is not None and td.select_one(".gr-a-datum")
    ]


def test_stand_vom_in_alle_geraete_bei_altem_messtag(tmp_path):
    """Rot gegen main: die Tabelle „Alle Geräte“ nannte nur das Datum. Die Zeile mit
    älterem Messtag (hier der günstigste Preis, 07.11. neben dem Stichtag 08.11.) trägt
    jetzt „Stand vom TT.MM.“; ohne älteren Messtag steht keine Marke da."""
    alt = _ab_zellen(
        messdatum._baue_wie_live(tmp_path / "alt", ["2026-11-08", "2026-11-07"])
    )
    assert alt, "keine Zelle mit Datum in Alle Geräte - der Test prüfte nichts"
    assert all(
        "7. November 2026" in z and z.endswith("Stand vom 07.11.") for z in alt
    ), alt
    gleich = _ab_zellen(
        messdatum._baue_wie_live(tmp_path / "gleich", ["2026-11-08", "2026-11-08"])
    )
    assert gleich and not any("Stand vom" in z for z in gleich), gleich
