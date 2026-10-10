"""Bilder ohne Aufblitzen und das grosse Bild auf Meldungen (Antonio, 10.10.2026).

Beim Laden stand eine Sekunde lang die alte tuerkise Flaeche, bevor das Bild
kam; oben zog Safari einen dunklen Streifen ueber das Bild; unter "Die
wichtigsten Meldungen" fehlte ein Bild; Meldungen hatte als einzige Seite
kein grosses Bild.
"""

from __future__ import annotations

import base64
import functools
import http.server
import io
import re
import threading
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from PIL import Image

from telco_radar import bild_vorschau
from telco_radar.report import statik

_TEMPLATES = Path(statik.__file__).parent / "templates"

_DATA = re.compile(r"url\((data:image/jpeg;base64,[A-Za-z0-9+/=]+)\)")


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    from orakel.test_seiten_inhalt import PORTAL, render

    return render(tmp_path_factory.mktemp("vorschau"), highlights=PORTAL)


@pytest.fixture(scope="module")
def seiten(site):
    from orakel.test_seiten_inhalt import lies_seite

    return {
        name: BeautifulSoup(lies_seite(site, name), "html.parser")
        for name in ("meldungen.html", "geraete.html", "index.html")
    }


def _vorschau_von(knoten) -> Image.Image:
    treffer = _DATA.search(knoten.get("style", ""))
    assert treffer, f"keine Vorschau in {knoten.get('style')!r}"
    roh = base64.b64decode(treffer.group(1).split(",", 1)[1])
    return Image.open(io.BytesIO(roh))


def test_jedes_bild_hat_eine_kleine_vorschau(tmp_path):
    bilder = statik.kopiere(_TEMPLATES, tmp_path)
    dateien = {
        b.stem
        for b in (_TEMPLATES / "static" / "bilder").iterdir()
        if b.suffix == ".jpg"
    }
    assert set(bilder) == dateien
    for name, url in bilder.items():
        im = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))
        assert im.width == bild_vorschau.VORSCHAU_BREITE, name
        assert len(url) < 2000, name


def test_die_vorschau_zeigt_die_farben_des_bildes(tmp_path):
    bilder = statik.kopiere(_TEMPLATES, tmp_path)
    voll = Image.open(_TEMPLATES / "static" / "bilder" / "band-geraete.jpg").convert(
        "RGB"
    )
    klein = Image.open(
        io.BytesIO(base64.b64decode(bilder["band-geraete"].split(",", 1)[1]))
    )
    mittel_voll = voll.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
    mittel_klein = (
        klein.convert("RGB").resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
    )
    assert all(abs(a - b) <= 12 for a, b in zip(mittel_voll, mittel_klein, strict=True))


def test_das_grosse_bild_liegt_auf_seiner_vorschau(seiten):
    for name in ("meldungen.html", "geraete.html"):
        bild = seiten[name].select_one(".wa-bild img.wa-motiv")
        assert bild is not None, name
        assert bild.get("fetchpriority") == "high", name
        assert _vorschau_von(bild).width == bild_vorschau.VORSCHAU_BREITE, name


def test_die_buehne_der_woche_steht_sofort_auf_ihrer_vorschau(seiten):
    buehne = seiten["index.html"].select_one(".buehne-bild")
    assert buehne is not None
    assert _vorschau_von(buehne).width == bild_vorschau.VORSCHAU_BREITE


def test_die_wichtigsten_meldungen_haben_ein_bild(tmp_path):
    bilder = statik.kopiere(_TEMPLATES, tmp_path)
    assert "kapitel-meldungen" in bilder


def test_meldungen_haben_ein_grosses_bild_ohne_schlagworte(seiten):
    seite = seiten["meldungen.html"]
    auftakt = seite.select_one("section.wa-auftakt.mg-auftakt[data-buehne]")
    assert auftakt is not None
    assert "band-meldungen.jpg" in auftakt.select_one(".wa-bild img")["src"]
    assert auftakt.select_one(".mg-kopf .mg-titel")
    assert not auftakt.select(".mg-kicker, .meldung, .chip")
    assert "mit-buehne" in seite.body["class"]
    assert seite.select_one("section.mg-oben .meldung")


def test_oben_zieht_kein_gummiband_ueber_das_bild(site, chromium):
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(site)
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    seite = chromium.new_page(viewport={"width": 390, "height": 844})
    try:
        for name in ("meldungen.html", "geraete.html", "index.html"):
            seite.goto(f"http://127.0.0.1:{httpd.server_address[1]}/{name}")
            werte = seite.evaluate(
                """() => {
                  const h = getComputedStyle(document.documentElement);
                  const b = getComputedStyle(document.body);
                  return [h.overscrollBehaviorY, b.overscrollBehaviorY,
                          h.backgroundColor];
                }"""
            )
            assert werte[:2] == ["none", "none"], name
            assert werte[2] == seite.evaluate(
                "getComputedStyle(document.body).backgroundColor"
            ), name
            if name != "index.html":
                oben = seite.evaluate(
                    "document.querySelector('.wa-auftakt-buehne')"
                    ".getBoundingClientRect().top"
                )
                assert oben == 0, name
    finally:
        seite.close()
        httpd.shutdown()
