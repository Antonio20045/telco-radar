"""Der Glas-Umschalter (Antonio, 11.10.2026): Wettbewerb wechselt zwischen
Deutschland und Global so einfach wie die Geraeteseite zwischen "Mit Tarif"
und "Einzelgeraet" - ein Umschalter, der beim Scrollen ueber dem Inhalt
schwebt, nicht auf dem Startbild steht, und als "Liquid Glass" den Inhalt
durchscheinen laesst. Die Brechungskarte rechnet der Server (Rechenweg
shuding/liquid-glass, MIT).
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import json
import pathlib
import threading

import pytest
from bs4 import BeautifulSoup
from PIL import Image
from test_laufzeit_vergleich import baue

from telco_radar.report import glas
from telco_radar.report.html import render_site, schreibe_statische_dateien

OBEN = 84


def test_die_karte_laesst_die_mitte_ruhig_und_holt_die_raender_nach_innen():
    k = glas.karte()
    bild = Image.open(glas.PFAD).convert("RGB")
    assert bild.size == (k.breite, k.hoehe) == (glas.BREITE, glas.HOEHE)
    assert k.staerke > 0
    mitte = bild.getpixel((k.breite // 2, k.hoehe // 2))
    assert abs(mitte[0] - 127) <= 1 and abs(mitte[1] - 127) <= 1
    links = bild.getpixel((0, k.hoehe // 2))
    rechts = bild.getpixel((k.breite - 1, k.hoehe // 2))
    oben = bild.getpixel((k.breite // 2, 0))
    unten = bild.getpixel((k.breite // 2, k.hoehe - 1))
    assert links[0] > 135 and rechts[0] < 119
    assert oben[1] > 135 and unten[1] < 119
    assert abs((links[0] - 127) + (rechts[0] - 127)) <= 3


def test_die_eingecheckte_karte_ist_die_gerechnete():
    """Die Datei ist gerechnet, nicht gezeichnet: gleiche Pixel wie glas.bild()."""
    datei = Image.open(glas.PFAD).convert("RGB")
    assert list(datei.getdata()) == list(glas.bild().getdata())


def baue_site(ordner: pathlib.Path) -> pathlib.Path:
    root, _ = baue(ordner)
    reports = root / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    bericht = {
        "date": "2026-10-11",
        "language": "de",
        "briefing_md": "## Auf einen Blick\n\n- Nichts.\n",
        "stats": {},
        "regions": [],
    }
    (reports / "2026-10-11.json").write_text(json.dumps(bericht), encoding="utf-8")
    (reports / "2026-10-11.md").write_text("# B\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    return site


@contextlib.contextmanager
def server(site: pathlib.Path):
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(site)
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    return baue_site(tmp_path_factory.mktemp("glas"))


@pytest.mark.parametrize(
    ("datei", "aktiv"),
    [("wettbewerb.html", "Deutschland"), ("differenzierung.html", "Global")],
)
def test_wettbewerb_hat_einen_umschalter_ausserhalb_des_startbilds(site, datei, aktiv):
    soup = BeautifulSoup((site / datei).read_text(encoding="utf-8"), "html.parser")
    schalter = soup.select("nav.glas-schalter")
    assert len(schalter) == 1
    nav = schalter[0]
    assert nav.find_parent(class_="wa-auftakt") is None
    assert nav.get("id") == "ansicht"
    ziele = {a.get_text(strip=True): a["href"] for a in nav.select("a")}
    assert ziele == {
        "Deutschland": "wettbewerb.html#ansicht",
        "Global": "differenzierung.html#ansicht",
    }
    assert [a.get_text(strip=True) for a in nav.select("[aria-current=page]")] == [
        aktiv
    ]
    assert soup.select(".wa-auftakt .glas-schalter, .wa-auftakt .umschalter") == []
    assert soup.select(".weiter-blatt") == []
    bild = soup.select_one("#glas-linse feImage")
    assert bild is not None and bild["href"] == glas.DATEI
    assert (site / glas.DATEI).is_file()


def test_keine_seite_traegt_pngbytes_im_html(site):
    """Antonios Mac, 12.10.2026: die PNG-Bytes der Karte hingen von der
    zlib-Fassung ab und die Golden-Seiten wichen ab; Pixel sind ueberall gleich."""
    for seite in ("wettbewerb.html", "differenzierung.html", "geraete.html"):
        assert "data:image/png" not in (site / seite).read_text(encoding="utf-8")


def test_die_geraeteseite_traegt_dasselbe_glas(site):
    soup = BeautifulSoup(
        (site / "geraete.html").read_text(encoding="utf-8"), "html.parser"
    )
    nav = soup.select_one("nav.gx-modus")
    assert "glas-schalter" in nav["class"]
    assert nav.select_one(".glas-pille") is not None
    assert soup.select_one("#glas-linse") is not None


@pytest.fixture(scope="module")
def basis(site):
    with server(site) as adresse:
        yield adresse


def _seite(chromium, basis, datei, breite, hoehe):
    context = chromium.new_context(viewport={"width": breite, "height": hoehe})
    s = context.new_page()
    s.goto(f"{basis}/{datei}", wait_until="load")
    s.evaluate(
        "() => { const f = document.createElement('div');"
        " f.style.height = '4000px';"
        " document.querySelector('.glas-schalter').parentElement.append(f); }"
    )
    s.wait_for_timeout(200)
    return context, s


_LAGE = """() => {
  const s = document.querySelector('.glas-schalter');
  const p = s.querySelector('.glas-pille').getBoundingClientRect();
  const a = s.querySelector('[aria-current=page],[aria-selected=true]')
    .getBoundingClientRect();
  const r = s.getBoundingClientRect();
  return {oben: Math.round(r.top), unten: Math.round(r.bottom),
          pille: [Math.round(p.left), Math.round(p.width)],
          wahl: [Math.round(a.left), Math.round(a.width)],
          glas: getComputedStyle(s).webkitBackdropFilter
            || getComputedStyle(s).backdropFilter};
}"""


@pytest.mark.parametrize(
    ("breite", "hoehe", "oben"), [(1440, 900, OBEN), (390, 844, None)]
)
def test_der_umschalter_schwebt_beim_scrollen_und_ist_glas(
    chromium, basis, breite, hoehe, oben
):
    """Am Rechner schwebt er; am Telefon bleibt er an seinem Platz wie die
    Leiste der Geraeteseite (10.10.2026: nichts schwebt dort ueber Text)."""
    context, s = _seite(chromium, basis, "wettbewerb.html", breite, hoehe)
    try:
        start = s.evaluate(_LAGE)
        assert start["oben"] >= hoehe * 0.5, "der Umschalter steht im Startbild"
        s.evaluate("window.scrollTo(0, 3000)")
        s.wait_for_timeout(300)
        lage = s.evaluate(_LAGE)
        if oben is None:
            assert lage["unten"] < 0
        else:
            assert lage["oben"] == oben
        assert lage["pille"] == lage["wahl"]
        assert "blur" in lage["glas"]
    finally:
        context.close()


def test_global_landet_beim_umschalter_der_anderen_seite(chromium, basis):
    context, s = _seite(chromium, basis, "wettbewerb.html", 1440, 900)
    try:
        s.click(".glas-schalter a:has-text('Global')")
        s.wait_for_url("**/differenzierung.html#ansicht")
        s.wait_for_timeout(300)
        lage = s.evaluate(_LAGE)
        assert lage["pille"] == lage["wahl"]
        wahl = s.inner_text(".glas-schalter [aria-current=page]")
        assert wahl.strip() == "Global"
        box = s.evaluate(
            "(() => { const r = document.querySelector('.glas-schalter')"
            ".getBoundingClientRect(); return [r.top, r.bottom]; })()"
        )
        assert box[0] >= 0 and box[1] <= 900, box
    finally:
        context.close()


def test_die_pille_gleitet_unter_einzelgeraet(chromium, basis):
    context = chromium.new_context(viewport={"width": 1440, "height": 900})
    s = context.new_page()
    try:
        s.goto(f"{basis}/geraete.html", wait_until="load")
        s.wait_for_timeout(200)
        vorher = s.evaluate(_LAGE)
        s.click(".gx-modus button[data-tafel=tafel-verlauf]")
        s.wait_for_timeout(800)
        nachher = s.evaluate(_LAGE)
        assert nachher["pille"] == nachher["wahl"]
        assert nachher["pille"][0] > vorher["pille"][0]
    finally:
        context.close()


_HINTERGRUND = "() => getComputedStyle(document.querySelector('.glas-schalter'))"
_HINTERGRUND += ".backgroundColor"


def test_ueber_bildern_wird_das_glas_klarer(chromium, basis):
    context, s = _seite(chromium, basis, "wettbewerb.html", 1440, 900)
    try:
        s.evaluate("window.scrollTo(0, 3000)")
        s.wait_for_timeout(400)
        assert s.get_attribute(".glas-schalter", "data-unter") == "flaeche"
        matt = s.evaluate(_HINTERGRUND)
        s.evaluate(
            "() => { const b = document.createElement('img');"
            " b.id = 'unterlage'; b.alt = '';"
            " b.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;'"
            " + 'z-index:1';"
            " document.body.append(b); window.scrollBy(0, 5); }"
        )
        s.wait_for_timeout(400)
        assert s.get_attribute(".glas-schalter", "data-unter") == "bild"
        klar = s.evaluate(_HINTERGRUND)
        assert klar != matt
    finally:
        context.close()


_BUEHNE = """<!doctype html><html class="ohne-js"><head><meta charset="utf-8">
<link rel="stylesheet" href="style.css"></head><body><main>
<section data-buehne style="height:1400px"><div style="height:600px"></div></section>
<nav class="glas-schalter" data-glas style="margin-top:-700px">
<span class="glas-pille"></span><a href="#" aria-current="page">Mit Tarif</a>
<a href="#">Einzelgerät</a></nav><div style="height:3000px"></div>
</main><script src="app.js"></script></body></html>"""


@pytest.fixture(scope="module")
def buehne(tmp_path_factory):
    ordner = tmp_path_factory.mktemp("buehne")
    schreibe_statische_dateien(ordner)
    (ordner / "buehne.html").write_text(_BUEHNE, encoding="utf-8")
    with server(ordner) as adresse:
        yield adresse


def test_ueber_der_flaeche_bleibt_die_schrift_dunkel(chromium, buehne):
    """Live 11.10.2026: unter der Leiste der Geraeteseite lag der leere Teil
    des Startbild-Abschnitts; das Glas hielt ihn fuer ein Bild und schrieb
    "Einzelgeraet" weiss auf Weiss. Gegenprobe: ein echtes Bild darunter
    macht das Glas klar."""
    context = chromium.new_context(viewport={"width": 1440, "height": 900})
    s = context.new_page()
    try:
        s.goto(f"{buehne}/buehne.html", wait_until="load")
        s.evaluate("window.scrollTo(0, 5)")
        s.wait_for_timeout(300)
        assert s.get_attribute(".glas-schalter", "data-unter") == "flaeche"
        s.evaluate(
            "() => { const b = document.createElement('img'); b.alt = '';"
            " b.style.cssText = 'display:block;width:100%;height:1400px';"
            " document.querySelector('[data-buehne]').prepend(b);"
            " window.scrollTo(0, 10); }"
        )
        s.wait_for_timeout(300)
        assert s.get_attribute(".glas-schalter", "data-unter") == "bild"
    finally:
        context.close()


_KNOEPFE = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="style.css"></head><body><main>
<nav class="glas-schalter" data-glas><span class="glas-pille"></span>
<a href="#" aria-current="page">Mit Tarif</a><a href="#">Einzelgerät</a></nav>
<div style="height:1200px"></div>
<div id="baender" style="display:flex;justify-content:center;gap:8px">
<button>15 GB</button><button>30 GB</button><button>60 GB</button>
<button>120 GB</button></div><div style="height:3000px"></div>
</main><script src="app.js"></script></body></html>"""


@pytest.fixture(scope="module")
def knoepfe(tmp_path_factory):
    ordner = tmp_path_factory.mktemp("knoepfe")
    schreibe_statische_dateien(ordner)
    (ordner / "knoepfe.html").write_text(_KNOEPFE, encoding="utf-8")
    with server(ordner) as adresse:
        yield adresse


_UNTER_DEM_SCHALTER = """() => {
  const r = document.querySelector('.glas-schalter').getBoundingClientRect();
  const b = document.querySelector('#baender').getBoundingClientRect();
  window.scrollBy(0, b.top - r.top - 4);
}"""

_GREIFBAR = """() => {
  const b = document.querySelector('#baender button').getBoundingClientRect();
  return document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2)
    .textContent.trim();
}"""


def test_der_schwebende_umschalter_verdeckt_keine_knoepfe(chromium, knoepfe):
    """Crawler-Fund 11.10.2026: bei 1440 px lag "Mit Tarif / Einzelgeraet"
    ueber den Band-Knoepfen (15 GB bis 120 GB). Rollt ein Knopf unter den
    Umschalter, weicht er; Gegenprobe: ueber freier Flaeche bleibt er."""
    context = chromium.new_context(viewport={"width": 1440, "height": 900})
    s = context.new_page()
    try:
        s.goto(f"{knoepfe}/knoepfe.html", wait_until="load")
        s.evaluate("window.scrollTo(0, 400)")
        s.wait_for_timeout(300)
        assert (
            s.evaluate(
                "getComputedStyle(document.querySelector('.glas-schalter')).opacity"
            )
            == "1"
        )
        s.evaluate(_UNTER_DEM_SCHALTER)
        s.wait_for_timeout(500)
        assert "weicht" in s.get_attribute(".glas-schalter", "class")
        assert s.evaluate(_GREIFBAR) == "15 GB"
        s.evaluate("window.scrollBy(0, 800)")
        s.wait_for_timeout(500)
        assert "weicht" not in s.get_attribute(".glas-schalter", "class")
    finally:
        context.close()
