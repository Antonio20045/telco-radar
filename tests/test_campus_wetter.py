"""Der Campus lebt, programmiert (Antonio, 11.10.2026): hinter der Startseite
steht EIN Foto des Turms; Himmel, Tageszeit, Wetter und Jahreszeit rechnet ein
WebGL-Canvas darueber, so wie es gerade am Campus ist. Tageszeit und Wetter
kommen von Open-Meteo; der Test beantwortet die Anfrage selbst, damit kein Netz
gebraucht wird. Gegenprobe: antwortet der Dienst nicht, bleibt der Himmel
bewoelkt und es steht keine Wetterzeile da.
"""

from __future__ import annotations

import functools
import http.server
import io
import json
import threading
import time
from pathlib import Path

import pytest
from PIL import Image, ImageStat

from telco_radar.report import statik
from telco_radar.report.html import schreibe_statische_dateien

TAGESZEITEN = ("morgen", "mittag", "abend", "nacht")
_VORLAGEN = Path(statik.__file__).parent / "templates" / "static"

_SEITE = """<!doctype html><html class="ohne-js"><head><meta charset="utf-8">
<style>.buehne{position:relative;width:960px;height:540px}.buehne-bild{position:absolute;inset:0}
.buehne-himmel{position:absolute;inset:0;width:100%;height:100%}</style></head>
<body><section class="buehne"><div class="buehne-bild">
<img class="buehne-ebene" data-zeit-bild="tag" data-src="static/bilder/campus-turm.jpg">
<canvas class="buehne-himmel" data-bild="static/bilder/campus-turm.jpg"
 data-bild-klein="static/bilder/campus-turm.jpg"
 data-maske="static/campus/campus-maske.png"
 data-maske-klein="static/campus/campus-maske-1200.png"></canvas>
</div><div class="buehne-kopf"><h1>Datum</h1>
<p class="buehne-wetter" data-campus-wetter hidden></p></div>
</section><script src="app.js"></script></body></html>"""


class _LangsamesStartbild(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.endswith("/campus-turm.jpg"):
            time.sleep(1.0)
        super().do_GET()

    def log_message(self, *_):
        pass


_ECHT = "Object.defineProperty(navigator,'webdriver',{get:()=>false});"


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    ordner = tmp_path_factory.mktemp("campus")
    schreibe_statische_dateien(ordner)
    (ordner / "seite.html").write_text(_SEITE, encoding="utf-8")
    handler = functools.partial(_LangsamesStartbild, directory=str(ordner))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield ordner, f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()


def _antwort(uhrzeit: str, code: int, grad: float, datum: str = "2026-10-11") -> str:
    return json.dumps(
        {
            "current": {
                "time": f"{datum}T{uhrzeit}",
                "weather_code": code,
                "temperature_2m": grad,
                "cloud_cover": 40,
                "wind_speed_10m": 12.0,
            },
            "daily": {
                "sunrise": [f"{datum}T07:52"],
                "sunset": [f"{datum}T18:51"],
            },
        }
    )


def _oeffne(chromium, adresse, antwort, ruhig=False):
    kontext = chromium.new_context(
        viewport={"width": 960, "height": 540},
        reduced_motion="reduce" if ruhig else "no-preference",
    )
    seite = kontext.new_page()
    seite.add_init_script(_ECHT)

    def beantworte(route):
        if antwort is None:
            route.abort()
        else:
            route.fulfill(status=200, content_type="application/json", body=antwort)

    seite.route("https://api.open-meteo.com/**", beantworte)
    seite.ablauf = []
    seite.on("requestfinished", lambda a: seite.ablauf.append(a.url))
    seite.goto(f"{adresse}/seite.html")
    seite.wait_for_selector(".buehne-himmel[data-szene]", state="attached")
    seite.wait_for_function("() => document.readyState === 'complete'")
    return seite


@pytest.mark.parametrize(
    ("uhrzeit", "code", "grad", "szene", "zeile", "tag"),
    [
        ("08:30", 61, 9.4, "morgen-regen", "Campus Düsseldorf · 9 °C, Regen", True),
        ("13:05", 73, -1.2, "mittag-schnee", "Campus Düsseldorf · -1 °C, Schnee", True),
        ("18:20", 3, 12.6, "abend-wolken", "Campus Düsseldorf · 13 °C, bewölkt", True),
        ("23:10", 0, 7.0, "nacht-sonne", "Campus Düsseldorf · 7 °C, klar", False),
        ("07:10", 45, 4.0, "nacht-nebel", "Campus Düsseldorf · 4 °C, Nebel", False),
        (
            "16:00",
            95,
            18.0,
            "mittag-gewitter",
            "Campus Düsseldorf · 18 °C, Gewitter",
            True,
        ),
    ],
)
def test_die_szene_folgt_uhrzeit_und_wetter_am_campus(
    chromium, site, uhrzeit, code, grad, szene, zeile, tag
):
    _, adresse = site
    seite = _oeffne(chromium, adresse, _antwort(uhrzeit, code, grad))
    try:
        himmel = seite.locator(".buehne-himmel")
        assert himmel.get_attribute("data-szene") == szene
        assert himmel.get_attribute("data-jahreszeit") == "herbst"
        assert (int(himmel.get_attribute("data-sonne")) > 0) is tag
        assert seite.inner_text("[data-campus-wetter]") == zeile
        assert seite.is_visible("[data-campus-wetter]")
    finally:
        seite.context.close()


def test_die_sonne_steht_mittags_im_sommer_hoeher_als_im_winter(chromium, site):
    """Düsseldorf liegt auf 51,2 Grad Nord: mittags rund 62 Grad zur Sommer- und
    15 Grad zur Wintersonnenwende."""
    _, adresse = site
    hoehen = {}
    for datum in ("2026-06-21", "2026-12-21"):
        seite = _oeffne(chromium, adresse, _antwort("13:21", 0, 10.0, datum))
        try:
            himmel = seite.locator(".buehne-himmel")
            hoehen[datum] = int(himmel.get_attribute("data-sonne"))
            erwartet = "sommer" if datum.startswith("2026-06") else "winter"
            assert himmel.get_attribute("data-jahreszeit") == erwartet
        finally:
            seite.context.close()
    assert 58 <= hoehen["2026-06-21"] <= 66
    assert 11 <= hoehen["2026-12-21"] <= 19


def test_ohne_wetterdienst_bleibt_der_himmel_bewoelkt_und_die_zeile_leer(
    chromium, site
):
    _, adresse = site
    seite = _oeffne(chromium, adresse, None)
    try:
        szene = seite.get_attribute(".buehne-himmel", "data-szene")
        assert szene.endswith("-wolken")
        assert szene.split("-")[0] in TAGESZEITEN
        assert not seite.is_visible("[data-campus-wetter]")
    finally:
        seite.context.close()


def _helligkeit(seite) -> float:
    seite.wait_for_selector(".buehne-himmel.laeuft", timeout=20_000)
    bild = Image.open(io.BytesIO(seite.locator(".buehne-himmel").screenshot()))
    return ImageStat.Stat(bild.convert("L")).mean[0]


def test_der_canvas_malt_tag_hell_und_nacht_dunkel(chromium, site):
    """Die Rechnung laeuft im Browser, also misst der Test die gemalten Pixel."""
    _, adresse = site
    werte = {}
    for name, uhrzeit in (("tag", "13:05"), ("nacht", "23:10")):
        seite = _oeffne(chromium, adresse, _antwort(uhrzeit, 0, 10.0), ruhig=True)
        try:
            werte[name] = _helligkeit(seite)
        finally:
            seite.context.close()
    assert werte["tag"] > werte["nacht"] + 40, werte


def test_ein_foto_und_eine_maske_kein_film_und_die_maske_erst_nach_dem_startbild(
    chromium, site
):
    _, adresse = site
    seite = _oeffne(chromium, adresse, _antwort("13:05", 3, 12.6))
    try:
        seite.wait_for_selector(".buehne-himmel.laeuft", timeout=20_000)
        filme = [u for u in seite.ablauf if u.endswith((".mp4", ".webm"))]
        assert not filme, seite.ablauf
        masken = [u for u in seite.ablauf if u.endswith("/campus-maske.png")]
        startbild = [u for u in seite.ablauf if u.endswith("/campus-turm.jpg")]
        assert len(masken) == 1 and startbild, seite.ablauf
        assert seite.ablauf.index(startbild[0]) < seite.ablauf.index(masken[0])
    finally:
        seite.context.close()


def test_foto_und_masken_passen_zusammen():
    with Image.open(_VORLAGEN / "bilder" / "campus-turm.jpg") as foto:
        groesse = foto.size
    with Image.open(_VORLAGEN / "campus" / "campus-maske.png") as maske:
        assert maske.size == groesse and maske.mode == "RGB"
        himmel = ImageStat.Stat(maske.getchannel("R")).mean[0] / 255
    with Image.open(_VORLAGEN / "campus" / "campus-maske-1200.png") as klein:
        assert klein.size == (1200, round(groesse[1] / 2))
    assert 0.25 < himmel < 0.55, himmel
    assert not list((_VORLAGEN / "campus").glob("*.mp4"))
