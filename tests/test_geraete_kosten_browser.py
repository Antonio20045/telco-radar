"""Kostenvergleich im echten Chromium: JS-Auswahl == Python-Auswahl.

`app.js` (`grKosten`) wiederholt `geraete_kosten.rangliste()` im Browser
(Clean Code 1: zwei Rechnungen brauchen einen Browser-Test, der sie
zusammenhält). Der Test klickt wie ein Leser durch Marke, Gerät, Speicher,
Tarif und Raten und vergleicht nach jedem Klick Reihenfolge, Summen und
Abstände der Zeilen mit der Python-Rangliste zur Auswahl aus der Adresse.
"""
from __future__ import annotations

import contextlib
import functools
import glob
import http.server
import json
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from telco_radar.config import load_config
from telco_radar.report import geraete_kosten as gk
from telco_radar.report.geraete_tco_grafik import euro
from telco_radar.report.html import render_site

REPO = Path(__file__).resolve().parents[1]
ZUSTAND = REPO / "data" / "state"
BESTAND_DA = all((ZUSTAND / n).exists() for n in
                 ("geraete_tco.json", "geraete_db.json", "tarife.jsonl"))

pw = pytest.importorskip("playwright.sync_api")


def _chromium():
    for muster in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",
                   str(Path.home() / ".cache/ms-playwright/chromium-*/chrome-linux*/chrome")):
        treffer = sorted(glob.glob(muster))
        if treffer:
            return treffer[-1]
    return None


class _Still(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@contextlib.contextmanager
def _server(verzeichnis: Path):
    handler = functools.partial(_Still, directory=str(verzeichnis))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()


@pytest.fixture(scope="module")
def seite(tmp_path_factory):
    if not BESTAND_DA:
        pytest.skip("kein ausgelieferter Bestand")
    ziel = tmp_path_factory.mktemp("site")
    render_site(ziel, REPO / "data" / "reports", load_config(REPO))
    html = (ziel / "geraete.html").read_text(encoding="utf-8")
    start = html.index('id="kv-daten">') + len('id="kv-daten">')
    daten = json.loads(html[start:html.index("</script>", start)])
    with _server(ziel) as basis, pw.sync_playwright() as p:
        try:
            browser = p.chromium.launch(executable_path=_chromium())
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"kein Chromium: {exc}")
        yield browser, basis, daten
        browser.close()

def _wahl(url: str, daten: dict) -> dict:
    q = parse_qs(urlparse(url).query)
    if not q:
        return {k: daten["start"][k] for k in ("modell", "stufe", "raten")}
    raten = q["raten"][0]
    return {"modell": q["modell"][0], "stufe": q["band"][0],
            "raten": raten if raten == "alle" else int(raten)}


def _erwartet(daten, wahl):
    r = gk.rangliste(daten, wahl["modell"], wahl["stufe"], wahl["raten"])
    zeilen = []
    for g in r["gruppen"]:
        zeilen.append(("kopf", f"Kosten über {g['monate']} Monate", ""))
        zeilen += [(z["anbieter"], euro(z["angebot"]["gesamt"]),
                    "günstigste" if z["sieger"] else
                    ("+" + euro(z["abstand"])) if z["abstand"] is not None
                    else "") for z in g["zeilen"]]
    if not r["gruppen"]:
        zeilen.append(("kopf", f"Kosten über {gk.HORIZONT} Monate", ""))
    if r["anders"]:
        zeilen.append(("anders", " | ".join(
            f"{x['anbieter']} · {n} Raten →" for x in r["anders"]
            for n in x["raten"]), ""))
    if r["ohne"]:
        zeilen.append(("ohne", " · ".join(r["ohne"]), "—"))
    return zeilen


_LESEN = """els => els.map(el => {
    const text = sel => el.querySelector(sel).textContent.replace(/\\u00a0/g, ' ').trim();
    if (el.classList.contains('kv-kopfzeile')) return ['kopf', el.textContent.trim(), ''];
    if (el.classList.contains('kv-anders')) return ['anders', [...el.querySelectorAll('button')]
        .map(b => b.textContent.replace(/\u00a0/g, ' ').trim()).join(' | '), ''];
    if (el.classList.contains('kv-ohne')) return ['ohne', text('.kv-ohne-namen'), text('.kv-summe')];
    return [el.dataset.anbieter, text('.kv-summe'), text('.kv-abstand')];
})"""


def _gelesen(page):
    return [tuple(z) for z in page.eval_on_selector_all(
        "#kv-ergebnis .kv-kopfzeile, #kv-ergebnis .kv-zeile, "
        "#kv-ergebnis .kv-anders, #kv-ergebnis .kv-ohne",
        _LESEN)]


def _pruefe(page, daten):
    wahl = _wahl(page.url, daten)
    assert _gelesen(page) == _erwartet(daten, wahl), wahl
    return wahl


def _klick(page, reihe, wert):
    page.click(f'.kv-reihe[data-wahl="{reihe}"] [data-wert="{wert}"]')


def _werte(page, reihe):
    return page.eval_on_selector_all(
        f'.kv-reihe[data-wahl="{reihe}"] .kv-chip:not([disabled])',
        "els => els.map(e => e.dataset.wert)")


def test_jeder_klick_zeigt_die_python_rangliste(seite):
    browser, basis, daten = seite
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(f"{basis}/geraete.html")
    geprueft = {json.dumps(_pruefe(page, daten))}
    for marke in daten["hersteller"][:3]:
        _klick(page, "hersteller", marke)
        geprueft.add(json.dumps(_pruefe(page, daten)))
        for reihe in ("stufe", "raten", "stufe"):
            for wert in _werte(page, reihe):
                _klick(page, reihe, wert)
                geprueft.add(json.dumps(_pruefe(page, daten)))
    # Gegenprobe: die Klicks haben die Auswahl wirklich gewechselt.
    assert len(geprueft) >= 10
    page.close()


def test_telefon_waehlt_das_geraet_aus_der_liste(seite):
    browser, basis, daten = seite
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(f"{basis}/geraete.html")
    assert not page.is_visible('.kv-reihe[data-wahl="familie"]')
    ziel = next(f for f in daten["geraete"] if f["hersteller"] == "Samsung")
    page.select_option("#kv-geraet", ziel["id"])
    wahl = _pruefe(page, daten)
    assert wahl["modell"] in {s["modell"] for s in ziel["speicher"]}
    assert ziel["name"] in page.text_content("#kv-titel")
    assert page.evaluate("document.documentElement.scrollWidth") <= 390
    page.close()


def test_ratenfilter_haengt_beim_geraetewechsel_nicht_fest(seite):
    browser, basis, daten = seite
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(f"{basis}/geraete.html")
    for fam in daten["geraete"]:
        for sp in fam["speicher"]:
            stufe = daten["start"]["stufe"]
            raten = {a["raten"] for a in daten["angebote"][sp["modell"]]
                     if a["stufe"] == stufe}
            if raten and 24 not in raten:
                page.goto(f"{basis}/geraete.html?modell={daten['start']['modell']}"
                          f"&band={stufe}&raten=24")
                if not page.is_enabled('.kv-reihe[data-wahl="raten"] [data-wert="24"]'):
                    continue
                page.evaluate("m => grKosten.waehle('modell', m)", sp["modell"])
                assert _wahl(page.url, daten)["raten"] == "alle"
                _pruefe(page, daten)
                page.close()
                return
    page.close()
    pytest.skip("kein Gerät ohne 24 Raten im Bestand")


def test_adresse_stellt_die_auswahl_wieder_her(seite):
    browser, basis, daten = seite
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(f"{basis}/geraete.html")
    _klick(page, "hersteller", "Samsung")
    _klick(page, "stufe", _werte(page, "stufe")[-1])
    adresse, vorher = page.url, _gelesen(page)
    titel = page.text_content("#kv-titel")
    page.goto(adresse)
    assert _gelesen(page) == vorher
    assert page.text_content("#kv-titel") == titel
    assert "Galaxy" in titel
    page.close()


def test_rechenweg_klappt_auf_und_nennt_summe_und_quelle(seite):
    browser, basis, daten = seite
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(f"{basis}/geraete.html")
    erste = page.locator(".kv-zeile").first
    weg = erste.locator(".kv-weg")
    assert not weg.is_visible()
    erste.locator("summary").click()
    assert weg.is_visible()
    summe = weg.locator(".kv-weg-summe td:last-child").text_content()
    assert summe.replace(" ", " ") == \
        erste.locator(".kv-summe").text_content().replace(" ", " ")
    assert erste.locator(".kv-quelle").get_attribute("href").startswith("http")
    page.close()


@pytest.mark.parametrize("breite,hoehe", [(1440, 900), (390, 844)])
def test_der_guenstigste_steht_ohne_scrollen_da(seite, breite, hoehe):
    browser, basis, _ = seite
    page = browser.new_page(viewport={"width": breite, "height": hoehe})
    page.goto(f"{basis}/geraete.html")
    unten = page.evaluate("""() => document.querySelector(
        '.kv-zeile .kv-summe').getBoundingClientRect().bottom""")
    assert unten <= hoehe
    assert page.evaluate("document.documentElement.scrollWidth") <= breite
    page.close()


def test_ausgefilterte_anbieter_schalten_die_raten_um(seite):
    browser, basis, daten = seite
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    for modell, liste in daten["angebote"].items():
        for a in liste:
            andere = {b["raten"] for b in liste if b["anbieter"] == a["anbieter"]
                      and b["stufe"] == a["stufe"]}
            if a["raten"] in andere and len(andere) == 1:
                fremd = next((b for b in liste if b["stufe"] == a["stufe"]
                              and b["anbieter"] != a["anbieter"]
                              and b["raten"] != a["raten"]), None)
                if fremd is None:
                    continue
                page.goto(f"{basis}/geraete.html?modell={modell}"
                          f"&band={a['stufe']}&raten={fremd['raten']}")
                _pruefe(page, daten)
                knopf = page.locator(
                    f'.kv-umschalten[data-raten="{a["raten"]}"]',
                    has_text=a["anbieter"])
                assert knopf.count() == 1
                assert a["anbieter"] not in page.text_content(".kv-ohne") \
                    if page.locator(".kv-ohne").count() else True
                knopf.click()
                assert _wahl(page.url, daten)["raten"] == a["raten"]
                assert page.locator(
                    f'.kv-zeile[data-anbieter="{a["anbieter"]}"]').count() == 1
                _pruefe(page, daten)
                page.close()
                return
    page.close()
    pytest.skip("kein Anbieter mit nur einer Ratenzahl neben einem anderen")


def test_die_erste_zahl_ist_immer_die_groesste(seite):
    browser, basis, daten = seite
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(f"{basis}/geraete.html")
    groessen = page.eval_on_selector_all(
        "#kv-ergebnis .kv-summe",
        "els => els.map(e => parseFloat(getComputedStyle(e).fontSize))")
    assert groessen and groessen[0] == max(groessen)
    assert all(g < groessen[0] for g in groessen[1:])
    page.close()


def test_anderer_zeitraum_steht_zugeklappt_ohne_betrag_im_blick(seite):
    browser, basis, daten = seite
    for modell, liste in daten["angebote"].items():
        for a in liste:
            if a["monate"] != gk.HORIZONT and any(
                    b["monate"] == gk.HORIZONT and b["stufe"] == a["stufe"]
                    for b in liste):
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                page.goto(f"{basis}/geraete.html?modell={modell}"
                          f"&band={a['stufe']}&raten=alle")
                _pruefe(page, daten)
                neben = page.locator(".kv-gruppe--neben")
                assert neben.count() == 1
                betrag = neben.locator(".kv-summe").first
                assert not betrag.is_visible()
                assert a["anbieter"] in neben.locator(".kv-neben-namen").text_content()
                neben.locator("summary.kv-neben-kopf").click()
                # Gegenprobe: aufgeklappt ist der Betrag da.
                assert betrag.is_visible()
                page.close()
                return
    pytest.skip("kein zweiter Zeitraum neben 24 Monaten im Bestand")


def test_neues_geraet_oeffnet_mit_dem_kleinsten_speicher(seite):
    browser, basis, daten = seite
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(f"{basis}/geraete.html")
    ziel = next(f for f in daten["geraete"]
                if f["hersteller"] == "Apple" and len(f["speicher"]) > 1
                and f["id"] != daten["start"]["familie"])
    page.evaluate("f => grKosten.waehle('familie', f)", ziel["id"])
    assert _wahl(page.url, daten)["modell"] == ziel["speicher"][0]["modell"]
    _pruefe(page, daten)
    page.close()
