"""Live-Abnahme 09.11.2026, Nachbesserung zu L1: die Wahl ändert sich WÄHREND das
Fragment des neuen Geräts lädt.

Grundregel: Nach dem Laden zeigt der Beleg die aktuell gewählte Kombination (Gerät,
Speicher, Tarifstufe, Anbieter), nie Zeile oder Bild einer anderen, auch nicht kurz.
Lücke im Stand 6100f4c2: ``setzeBuendel`` gab dem Einsetzen das Band des
Geräteklicks, nicht ``zustand.band``. Wer die Stufe wechselte, während das Fragment
lud, behielt den Beleg der alten Stufe unter der neuen.

Die Seite hat keinen Anbieter-Schalter; die Anbieter-Achse sind die Beleg-Paare je
Anbieter (hier o2 und congstar), die je Stufe zu- oder abgeschaltet werden.
Fragment (``data/bnd/*.html``) künstlich angehalten und freigegeben, ein Späher prüft
jedes Frame. Feste Daten, nie das heutige Datum (CLAUDE.md Regel 7).

Fixture: iPhone 17 Pro 256 (Startgerät, Stufe XS), Galaxy S26 256 und 512, je mit
einem o2-Beleg in XS und einem congstar-Beleg in M.
"""

from __future__ import annotations

import copy
import functools
import http.server
import json
import threading
from pathlib import Path

import pytest
import test_beleg_position as pos
import test_geraete_browser_fixture as fixture
import test_geraete_buendel_kopf_zeitraum as kopf
import test_live_auflagen2_0911 as basis
import yaml
from bs4 import BeautifulSoup

from telco_radar.beleg_manifest import MANIFEST_NAME, baue_manifest, schreibe
from telco_radar.beleg_regeln import dateiname
from telco_radar.report.html import render_site

G256 = "samsung-galaxy-s26-256"
G512 = "samsung-galaxy-s26-512"
SKU_256 = fixture._sku("samsung-galaxy-s26", 256)
SKU_512 = fixture._sku("samsung-galaxy-s26", 512)
O2 = "O2 Mobile Klein"
CS = "Allnet Flat M"


def _bild(modell: str, anbieter_id: str) -> str:
    return dateiname(modell, anbieter_id, pos.TAG)


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    site = kopf._baue(tmp_path_factory.mktemp("wahl_waehrend_laden"))
    wurzel = site.parent
    katalog = copy.deepcopy(kopf._KATALOG)
    for g in katalog["geraete"]:
        if g["modell"] == "Galaxy S26":
            g["speicher"] = [256, 512]
    (wurzel / "config" / "geraete_katalog.yaml").write_text(
        yaml.safe_dump(katalog, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    state = wurzel / "data" / "state"
    bestand = json.loads((state / "geraete_tco.json").read_text(encoding="utf-8"))
    vodafone = [b for b in bestand["buendel"] if b["anbieter"] == "Vodafone"]
    saetze = [
        pos._satz("o2", O2, "o2:klein", 24, 18.0, pos.ID_O2),
        pos._satz("o2", O2, "o2:klein", 24, 19.0, "f" * 64, sku=SKU_256),
        pos._satz("congstar", CS, "cs:mittel", 24, 20.0, "e" * 64, sku=SKU_256),
        pos._satz("o2", O2, "o2:klein", 24, 21.0, "1" * 64, sku=SKU_512),
        pos._satz("congstar", CS, "cs:mittel", 24, 22.0, "2" * 64, sku=SKU_512),
    ]
    (state / "geraete_tco.json").write_text(
        json.dumps({"updated": pos.HEUTE, "buendel": [*saetze, *vodafone]}),
        encoding="utf-8",
    )
    tarife = [
        json.loads(z)
        for z in (state / "tarife.jsonl").read_text(encoding="utf-8").splitlines()
        if z.strip()
    ]
    mittel = copy.deepcopy(next(t for t in tarife if t["tarif_id"] == "cs:klein"))
    mittel.update(tarif_id="cs:mittel", name=CS, datenvolumen_gb=50)
    (state / "tarife.jsonl").write_text(
        "\n".join(json.dumps(t) for t in [*tarife, mittel]) + "\n", encoding="utf-8"
    )
    namen = [
        _bild(kopf.MODELL, "o2"),
        _bild(G256, "o2"),
        _bild(G256, "congstar"),
        _bild(G512, "o2"),
        _bild(G512, "congstar"),
    ]
    schreibe(
        state / MANIFEST_NAME, baue_manifest({f"belege-{pos.HEUTE}": namen}, pos.TAG)
    )
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


def test_die_fixture_hat_je_geraet_zwei_anbieter_in_zwei_stufen(site):
    """Gegenprobe: ohne o2 (XS) und congstar (M) je Gerät prüfte nichts die Stufe."""
    lager = BeautifulSoup(
        (site / "data" / "geraete-buendel.html").read_text(encoding="utf-8"),
        "html.parser",
    )
    kombis = {
        lg["data-modell"]: sorted(
            (
                z.find_parent("li")
                .select_one(".gr-beleg-anbieter")
                .get_text(strip=True),
                z["data-kombi"],
            )
            for z in lg.select(".gr-beleg-zeile")
        )
        for lg in lager.select(".gr-bnd-lager[data-modell]")
    }
    for modell in (G256, G512):
        assert kombis.get(modell) == [("congstar", "m:24"), ("o2", "xs:24")], kombis


_SPAEHER = """() => {
  window.__proben = [];
  const lies = () => {
    const g = document.getElementById('gr-bnd-gruppe');
    const sicht = e => e.getBoundingClientRect().height > 0;
    const zeilen = [...g.querySelectorAll('.gr-beleg-zeile')].filter(sicht)
      .map(z => z.getAttribute('data-kombi'));
    const bilder = [...g.querySelectorAll('img')].filter(sicht)
      .map(i => i.getAttribute('src') || i.getAttribute('data-src'));
    window.__proben.push({t: performance.now(), zeilen, bilder});
    requestAnimationFrame(lies);
  };
  requestAnimationFrame(lies);
}"""

_MARKE = "() => { window.__marke = performance.now(); }"

_ZEILEN = """() => [...document.querySelectorAll('#gr-bnd-gruppe .gr-beleg-paar')]
  .filter(li => li.getBoundingClientRect().height > 0)
  .map(li => li.querySelector('.gr-beleg-anbieter').textContent.trim() + '|'
    + [...li.querySelectorAll('.gr-beleg-zeile')]
      .filter(z => z.getBoundingClientRect().height > 0)
      .map(z => z.getAttribute('data-kombi')).join(','))"""


def _waehle(s, suchwort, modell):
    basis._zeige_vorschau(s, suchwort)
    s.evaluate(basis._WECHSEL, modell)


def _stufe(s, band):
    s.click(f'#gr-zr-baender button[data-band="{band}"]')


def _nach_marke(s):
    return s.evaluate("window.__proben.filter(p => p.t >= window.__marke)")


def _pruefe_endzustand(s, erwartet_bild, anbieter, kombi, fremd_bilder):
    """Nach dem Laden: genau ein Anbieter-Paar mit genau der Zeile der Wahl; nach dem
    Aufklappen steht genau deren Bild da."""
    s.wait_for_selector("#gr-bnd-gruppe .gr-beleg-paar:not([hidden])")
    s.wait_for_timeout(200)
    assert s.evaluate(_ZEILEN) == [f"{anbieter}|{kombi}"]
    s.locator("#gr-bnd-gruppe .gr-beleg-zeile:not([hidden]) summary").first.click()
    s.wait_for_function(
        "() => [...document.querySelectorAll('#gr-bnd-gruppe img')].some("
        "i => i.getBoundingClientRect().height > 0 && i.complete && i.naturalWidth > 0)"
    )
    sichtbar = s.evaluate(
        "() => [...document.querySelectorAll('#gr-bnd-gruppe img')]"
        ".filter(i => i.getBoundingClientRect().height > 0)"
        ".map(i => i.getAttribute('src'))"
    )
    assert sichtbar and all(erwartet_bild in u for u in sichtbar), sichtbar
    assert not any(f in u for u in sichtbar for f in fremd_bilder), sichtbar


def _kein_fremdes_im_frame(proben, erlaubte_kombis):
    assert len(proben) > 10, "der Späher hat kaum Frames gesehen"
    schlecht = [p for p in proben if set(p["zeilen"]) - set(erlaubte_kombis)]
    assert schlecht == [], schlecht[:2]
    bilder = [p for p in proben if p["bilder"] and not p["zeilen"]]
    assert bilder == [], bilder[:2]


@pytest.mark.browser
@pytest.mark.parametrize("breite", [1440, 390])
def test_stufenwechsel_waehrend_das_fragment_laedt(chromium, adresse, breite):
    """Rot gegen 6100f4c2: Galaxy S26 256 gewählt (Fragment unterwegs), dann Stufe
    XS -> M. Das Fragment setzte die Zeilen der XS-Stufe des Geräteklicks ein; unter
    "M" stand der o2-Beleg (XS) samt Bild. Jetzt steht dort nur der congstar-Beleg."""
    ctx, s, netz, meldungen = basis._oeffne(chromium, adresse, breite)
    try:
        netz.halten["bnd"] = True
        s.evaluate(_SPAEHER)
        _waehle(s, "galaxy s26", G256)
        s.wait_for_timeout(100)
        _stufe(s, "m")
        s.evaluate(_MARKE)
        s.wait_for_timeout(300)
        assert netz.gehalten, "Gegenprobe: das Fragment war wirklich unterwegs"
        assert (
            s.evaluate(
                "document.querySelector('#gr-zr-baender "
                "[aria-pressed=true]').dataset.band"
            )
            == "m"
        )
        netz.gebe_frei("bnd")
        _pruefe_endzustand(
            s, _bild(G256, "congstar"), "congstar", "m:24", [_bild(G256, "o2")]
        )
        _kein_fremdes_im_frame(_nach_marke(s), ["m:24"])
        assert s.evaluate("document.documentElement.scrollWidth") <= breite
        assert meldungen == []
    finally:
        ctx.close()


@pytest.mark.browser
def test_speicherwechsel_und_stufe_waehrend_das_fragment_laedt(chromium, adresse):
    """Rot gegen 6100f4c2: Galaxy 256 gewählt, gleich auf 512 gewechselt, dann Stufe
    M. Beide Fragmente sind unterwegs; das späte 256-Fragment trifft nach dem 512er
    ein. Jetzt zeigt der Beleg nur 512 in M (nie 256, nie XS)."""
    ctx, s, netz, meldungen = basis._oeffne(chromium, adresse)
    try:
        netz.halten["bnd"] = True
        s.evaluate(_SPAEHER)
        _waehle(s, "galaxy s26", G256)
        s.wait_for_timeout(50)
        _waehle(s, "galaxy s26", G512)
        s.wait_for_timeout(50)
        _stufe(s, "m")
        s.evaluate(_MARKE)
        s.wait_for_timeout(300)
        assert len(netz.gehalten) >= 2, "Gegenprobe: beide Fragmente unterwegs"
        for art, route in list(netz.gehalten):
            if "512" in route.request.url:
                route.continue_()
                netz.gehalten.remove((art, route))
        s.wait_for_timeout(300)
        netz.gebe_frei("bnd")
        s.wait_for_timeout(300)
        _pruefe_endzustand(
            s,
            _bild(G512, "congstar"),
            "congstar",
            "m:24",
            [_bild(G512, "o2"), _bild(G256, "o2"), _bild(G256, "congstar")],
        )
        _kein_fremdes_im_frame(_nach_marke(s), ["m:24"])
        assert meldungen == []
    finally:
        ctx.close()


@pytest.mark.browser
def test_anbieterbeleg_folgt_der_stufe_die_beim_laden_zurueckgewechselt_wird(
    chromium, adresse
):
    """Rot gegen 6100f4c2: Galaxy 256 steht in M (nur der congstar-Beleg). Wechsel auf
    512 (Fragment unterwegs), dabei Stufe XS gewählt. Das Fragment setzte die Zeilen
    der M-Stufe des Geräteklicks ein; unter "XS" stand der congstar-Beleg (M). Jetzt
    steht dort nur der o2-Beleg."""
    ctx, s, netz, meldungen = basis._oeffne(chromium, adresse)
    try:
        _waehle(s, "galaxy s26", G256)
        s.wait_for_selector("#gr-bnd-gruppe .gr-beleg-paar:not([hidden])")
        _stufe(s, "m")
        s.wait_for_timeout(200)
        assert s.evaluate(_ZEILEN) == ["congstar|m:24"], "Gegenprobe: M zeigt congstar"
        netz.halten["bnd"] = True
        s.evaluate(_SPAEHER)
        _waehle(s, "galaxy s26", G512)
        s.wait_for_timeout(100)
        _stufe(s, "xs")
        s.evaluate(_MARKE)
        s.wait_for_timeout(300)
        assert netz.gehalten, "Gegenprobe: das Fragment war unterwegs"
        netz.gebe_frei("bnd")
        _pruefe_endzustand(
            s, _bild(G512, "o2"), "o2", "xs:24", [_bild(G512, "congstar")]
        )
        _kein_fremdes_im_frame(_nach_marke(s), ["xs:24"])
        assert meldungen == []
    finally:
        ctx.close()
