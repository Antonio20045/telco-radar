"""P3-E2: der Laufzeit-Filter der Bündeltabelle, Standard 24 Monate.

Python entscheidet, welche Zeile unter welcher Wahl steht
(`geraete_tco_karten.laufzeit_wahl`), app.js blendet nur. Die Wahl blendet
keinen Anbieter aus: wer die gewaehlte Laufzeit nicht anbietet, steht mit
seiner naechstgelegenen da (Telekom, o2 und 1&1 bieten heute nur 36 Raten).

Die Browser-Tests laufen im echten Chromium auf eigenem Server - dieselbe
Bauform wie `tests/test_geraete_o2_zeilen_browser.py`.
"""
from __future__ import annotations

import contextlib
import json

import pytest
import yaml

from telco_radar.report import geraete_tco_karten as karten
from telco_radar.report.html import render_site

from test_geraete_browser_fixture import (
    HEUTE, _chromium, _KATALOG, _FARBEN, _listung, _QUELLEN, _server, _sku)
from test_geraete_zeitreihe_browser import waehle_band


def _k(anbieter, tarif, lz, zustand="neu"):
    return {"anbieter": anbieter, "tarif": tarif, "raten_laufzeit": lz,
            "zustand": zustand}


# --------------------------------------------------------------------------
# Python: wer steht unter welcher Wahl
# --------------------------------------------------------------------------

def test_jede_wahl_zeigt_je_angebot_genau_eine_zeile():
    cs24, cs36 = _k("congstar", "XS", 24), _k("congstar", "XS", 36)
    o2 = _k("o2", "M", 36)
    vf12, vf24 = _k("Vodafone", "S", 12), _k("Vodafone", "S", 24)
    ref = _k("Vodafone", "Referenz", None)
    alle = [cs24, cs36, o2, vf12, vf24, ref]
    wahl = karten.laufzeit_wahl(alle)
    assert wahl == {"optionen": [12, 24, 36], "start": 24}
    assert cs24["laufzeit_sichtbar"] == "12 24"
    assert cs36["laufzeit_sichtbar"] == "36"
    assert o2["laufzeit_sichtbar"] == "12 24 36"
    assert vf12["laufzeit_sichtbar"] == "12"
    assert vf24["laufzeit_sichtbar"] == "24 36"
    assert ref["laufzeit_sichtbar"] == "", "ohne Raten gehoert sie zu keiner Wahl"
    # Gegenprobe: je Wahl und Angebot genau EINE Zeile.
    for lz in ("12", "24", "36"):
        je_angebot: dict = {}
        for k in alle[:-1]:
            if lz in k["laufzeit_sichtbar"].split():
                je_angebot.setdefault((k["anbieter"], k["tarif"]), []).append(k)
        assert all(len(v) == 1 for v in je_angebot.values()), (lz, je_angebot)
        assert len(je_angebot) == 3


def test_der_zustand_trennt_die_angebote():
    neu = _k("o2", "M", 24)
    erneuert = _k("o2", "M", 36, zustand="refurbished")
    karten.laufzeit_wahl([neu, erneuert])
    assert erneuert["laufzeit_sichtbar"] == "24 36"


def test_ohne_zwei_laufzeiten_gibt_es_nichts_zu_waehlen():
    k = _k("o2", "M", 36)
    assert karten.laufzeit_wahl([k, _k("Telekom", "L", 36)]) is None
    assert k["laufzeit_sichtbar"] == ""


def test_fehlt_die_standardlaufzeit_gilt_die_naechste_kuerzere():
    assert karten.laufzeit_wahl([_k("a", "t", 12), _k("b", "t", 36)])[
        "start"] == 12
    assert karten.laufzeit_wahl([_k("a", "t", 30), _k("b", "t", 36)])[
        "start"] == 30
    assert karten.LAUFZEIT_STANDARD == 24


# --------------------------------------------------------------------------
# Browser
# --------------------------------------------------------------------------

_GERAET = "apple-iphone-17-pro"
# (anbieter, tarif_id, tarif, laufzeit, rate, aktionen)
_BUENDEL = [
    ("congstar", "cs:xs", "Allnet Flat XS", 24, 41.25,
     [{"art": "trade_in", "bedingung": "nur mit Eintausch eines Altgeräts",
       "quelle_url": "https://www.congstar.de/handytarife/allnet-flat-tarife/"
                     "allnet-flat-xs/", "betrag": 324.0,
       "eingerechnet": False, "gueltig_bis": ""}]),
    ("congstar", "cs:xs", "Allnet Flat XS", 36, 27.5, []),
    ("o2", "o2:klein", "O2 Mobile Klein", 36, 30.0, []),
    ("Vodafone", "vf:klein", "Vodafone Mobil XS", 24, 45.0, []),
]


def _baue(tmp_path):
    root = tmp_path / "site_baum"
    (root / "config").mkdir(parents=True)
    for name, daten in (("geraete_katalog.yaml", _KATALOG),
                        ("farben.yaml", _FARBEN),
                        ("geraete_quellen.yaml", _QUELLEN)):
        (root / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
    state = root / "data" / "state"
    state.mkdir(parents=True)
    (state / "geraete_db.json").write_text(json.dumps({
        "updated": HEUTE, "anbieter": {
            n: {"laeufe": 4, "funde_gesamt": 1}
            for n in ("Vodafone", "o2", "congstar")},
        "listungen": [_listung("Vodafone", _GERAET, 256, 1199.90),
                      _listung("o2", _GERAET, 256, 1099.00),
                      _listung("congstar", _GERAET, 256, 1225.00)]}),
        encoding="utf-8")
    (state / "geraete_preise.jsonl").write_text("", encoding="utf-8")
    buendel = [{
        "id": f"buendel--{a.lower()}--{_sku(_GERAET, 256)}--{tid}--{lz}m",
        "sku_id": _sku(_GERAET, 256), "anbieter": a, "tarif_name": tarif,
        "tarif_id": tid, "tarif_id_guete": "hoch", "tarif_monatlich": 24.0,
        "geraet_zuzahlung": 1.0, "geraet_monatsrate": rate,
        "laufzeit_monate": lz, "anschlusspreis": 0.0, "zustand": "neu",
        "rabatte": [], "aktionen": aktionen,
        "quelle_url": f"https://example.de/{a.lower()}/{tid}",
        "abgerufen_am": HEUTE, "first_seen": HEUTE, "last_verified": HEUTE}
        for a, tid, tarif, lz, rate, aktionen in _BUENDEL]
    (state / "geraete_tco.json").write_text(json.dumps({
        "updated": HEUTE, "buendel": buendel, "sim_only": []}),
        encoding="utf-8")
    tarife = {tid: (a, tarif) for a, tid, tarif, *_ in _BUENDEL}
    (state / "tarife.jsonl").write_text("\n".join(json.dumps({
        "anbieter": a, "name": tarif, "tarif_id": tid, "art": "mobilfunk",
        "grundgebuehr": 24.0, "laufzeit_monate": 24, "datenvolumen_gb": 15,
        "preisphasen": [{"von_monat": 1, "bis_monat": None, "betrag": 24.0}],
        "dokument_url": f"https://example.de/pib/{tid}",
        "abgerufen_am": HEUTE, "confidence": {}, "fundstellen": {}})
        for tid, (a, tarif) in tarife.items()) + "\n", encoding="utf-8")
    reports = root / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / f"{HEUTE}.json").write_text(json.dumps({
        "date": HEUTE, "language": "de",
        "briefing_md": "## Auf einen Blick\n\n- Nichts Besonderes.\n",
        "stats": {}, "regions": []}), encoding="utf-8")
    (reports / f"{HEUTE}.md").write_text("# Bericht\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    return site


@contextlib.contextmanager
def _browser_ctx(tmp_path_factory):
    sync_playwright = pytest.importorskip(
        "playwright.sync_api", reason="playwright fehlt").sync_playwright
    site = _baue(tmp_path_factory.mktemp("laufzeitfilter"))
    exe = _chromium()
    with _server(site) as basis, sync_playwright() as p:
        browser = (p.chromium.launch(executable_path=exe) if exe
                   else p.chromium.launch())
        try:
            yield browser, basis
        finally:
            browser.close()


@pytest.fixture(scope="module")
def _browser_seite(tmp_path_factory):
    with _browser_ctx(tmp_path_factory) as paar:
        yield paar


@pytest.fixture(params=[(1440, 900), (390, 844)], ids=["breit", "telefon"])
def seite(_browser_seite, request):
    browser, basis = _browser_seite
    breite, hoehe = request.param
    s = browser.new_page(viewport={"width": breite, "height": hoehe})
    s.goto(f"{basis}/geraete.html", wait_until="load")
    s.click(".gr-reiter button[data-tafel='tafel-tco']")
    try:
        yield s
    finally:
        s.close()


# Sichtbarkeit wird im Browser GEMESSEN (Boxhoehe), nicht am Attribut -
# CLAUDE.md, Tests und Abnahme.
_SICHTBAR = """() => Array.from(document.querySelectorAll('#gr-bnd-gruppe .gr-bnd'))
  .filter(z => z.getBoundingClientRect().height > 0)
  .map(z => z.dataset.anbieter + ' ' + z.querySelector('.gr-bnd-raten')
                                       .textContent.trim().split(' ')[0])
  .sort()"""


def _waehle(seite, lz):
    seite.click(f".gr-bnd-lz button[data-lz='{lz}']")
    seite.wait_for_timeout(120)


def test_ohne_klick_stehen_24_monate(seite):
    gedrueckt = seite.eval_on_selector_all(
        ".gr-bnd-lz button[aria-pressed='true']", "e => e.map(k => k.textContent)")
    assert gedrueckt == ["24"]
    assert seite.evaluate(_SICHTBAR) == ["Vodafone 24", "congstar 24", "o2 36"]


def test_die_wahl_36_tauscht_nur_die_congstar_zeile(seite):
    _waehle(seite, "36")
    assert seite.evaluate(_SICHTBAR) == ["Vodafone 24", "congstar 36", "o2 36"]
    _waehle(seite, "alle")
    assert seite.evaluate(_SICHTBAR) == [
        "Vodafone 24", "congstar 24", "congstar 36", "o2 36"]


def test_die_laufzeitwahl_ueberlebt_den_bandwechsel(seite):
    _waehle(seite, "36")
    waehle_band(seite, "klein")
    assert seite.evaluate(_SICHTBAR) == ["Vodafone 24", "congstar 36", "o2 36"]


def test_der_filter_laeuft_nicht_aus_dem_bild(seite):
    ueber = seite.evaluate("""() => {
      const l = document.querySelector('.gr-bnd-lz').getBoundingClientRect();
      return Array.from(document.querySelectorAll('.gr-bnd-lz button'))
        .filter(k => k.getBoundingClientRect().right > l.right + 0.5
                  || k.getBoundingClientRect().right > window.innerWidth)
        .map(k => k.textContent)}""")
    assert ueber == []
    assert seite.evaluate(
        "() => document.documentElement.scrollWidth <= window.innerWidth")


def test_der_trade_in_steht_neben_der_leitzahl_und_im_rechenweg(seite):
    zeile = seite.query_selector(
        "#gr-bnd-gruppe .gr-bnd[data-anbieter='congstar']:not([hidden])")
    assert zeile.query_selector(".gr-bnd-aktion").inner_text() == \
        "bis −324,00 € mit Altgerät"
    # Die Leitzahl ist die ohne Eintausch: 1 + 24 x 41,25 + 24 x 24.
    assert "1.567,00 €" in zeile.query_selector(".gr-bnd-tco").inner_text()
    zeile.query_selector("summary").click()
    seite.wait_for_timeout(150)
    text = zeile.query_selector(".gr-kk-aktion").inner_text()
    assert "Trade-in −324,00 €" in text and "nicht eingerechnet" in text
    assert zeile.query_selector(".gr-kk-aktion a").get_attribute("href") \
        .startswith("https://www.congstar.de/")
    # Gegenprobe: die 36-Monats-Zeile ohne Aktion traegt keinen Ueberhang.
    _waehle(seite, "36")
    ohne = seite.query_selector(
        "#gr-bnd-gruppe .gr-bnd[data-anbieter='congstar']:not([hidden])")
    assert ohne.query_selector(".gr-bnd-aktion") is None
