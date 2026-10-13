"""Der Campus lebt (Antonio, 13.10.2026): hinter der Startseite stehen sieben
echte Fotoplatten des Turms; ein WebGL-2-Canvas blendet zwischen ihnen nach
der Sonnenhoehe am Campus und legt das Wetter darueber. Es zaehlt die echte
Zeit in Duesseldorf: der Test stellt die Uhr des Browsers fest, statt vom
heutigen Datum abzuhaengen, und beantwortet die Wetteranfrage selbst, damit
kein Netz gebraucht wird. Gegenprobe: antwortet der Dienst nicht, bleibt der
Himmel bewoelkt und es steht keine Wetterzeile da.
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

_VORLAGEN = Path(statik.__file__).parent / "templates" / "static"
_PLATTEN = ("tag", "gold", "blau", "nacht", "spaet", "regen", "schnee")

_SEITE = """<!doctype html><html class="ohne-js"><head><meta charset="utf-8">
<style>.buehne{position:relative;width:960px;height:540px}.buehne-bild{position:absolute;inset:0}
.buehne-himmel{position:absolute;inset:0;width:100%;height:100%}</style></head>
<body><section class="buehne"><div class="buehne-bild">
<img class="buehne-ebene" data-zeit-bild="tag" data-src="static/bilder/campus-turm.jpg">
<canvas class="buehne-himmel" data-basis="static/campus/"
 data-blau="static/bilder/campus-turm.jpg"></canvas>
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
_UHR = (
    "(()=>{const D=Date,off=D.parse(%r)-D.now();"
    "class F extends D{constructor(...a){"
    "if(a.length)super(...a);else super(D.now()+off)}"
    "static now(){return D.now()+off}};window.Date=F})()"
)


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


def _antwort(code: int, grad: float, wolken: int = 40) -> str:
    return json.dumps(
        {
            "current": {
                "time": "2026-10-13T12:00",
                "weather_code": code,
                "temperature_2m": grad,
                "cloud_cover": wolken,
                "wind_speed_10m": 12.0,
            }
        }
    )


def _oeffne(chromium, adresse, zeitpunkt, antwort, ruhig=False):
    kontext = chromium.new_context(
        viewport={"width": 960, "height": 540},
        reduced_motion="reduce" if ruhig else "no-preference",
    )
    seite = kontext.new_page()
    seite.add_init_script(_ECHT)
    seite.add_init_script(_UHR % zeitpunkt)

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
    ("zeitpunkt", "code", "grad", "szene", "zeile", "hell"),
    [
        ("2026-10-13T10:30:00Z", 61, 9.4, "tag-regen", "9 °C, Regen", False),
        ("2026-10-13T11:05:00Z", 0, 16.2, "tag-klar", "16 °C, klar", True),
        ("2026-10-13T16:35:00Z", 1, 13.0, "gold-klar", "13 °C, klar", False),
        ("2026-10-13T17:25:00Z", 2, 12.6, "blau-klar", "13 °C, klar", False),
        ("2026-10-13T21:10:00Z", 45, 7.0, "nacht-nebel", "7 °C, Nebel", False),
        ("2026-10-13T14:00:00Z", 95, 18.0, "tag-gewitter", "18 °C, Gewitter", False),
        ("2027-01-15T12:00:00Z", 73, -1.2, "tag-schnee", "-1 °C, Schnee", False),
    ],
)
def test_die_szene_folgt_uhrzeit_und_wetter_am_campus(
    chromium, site, zeitpunkt, code, grad, szene, zeile, hell
):
    _, adresse = site
    seite = _oeffne(chromium, adresse, zeitpunkt, _antwort(code, grad))
    try:
        himmel = seite.locator(".buehne-himmel")
        assert himmel.get_attribute("data-szene") == szene
        assert (
            seite.inner_text("[data-campus-wetter]") == "Campus Düsseldorf · " + zeile
        )
        assert seite.is_visible("[data-campus-wetter]")
        dunkel = "film-dunkel" in seite.get_attribute(".buehne", "class")
        assert dunkel is not hell
    finally:
        seite.context.close()


def test_es_zaehlt_die_zeit_in_duesseldorf_nicht_die_des_lesers(chromium, site):
    """Derselbe Augenblick in Tokio: am Campus ist es Mittag, nicht Abend."""
    _, adresse = site
    kontext = chromium.new_context(timezone_id="Asia/Tokyo")
    seite = kontext.new_page()
    seite.add_init_script(_ECHT)
    seite.add_init_script(_UHR % "2026-10-13T11:05:00Z")
    seite.route("https://api.open-meteo.com/**", lambda r: r.abort())
    try:
        seite.goto(f"{adresse}/seite.html")
        seite.wait_for_selector(".buehne-himmel[data-szene]", state="attached")
        assert seite.get_attribute(".buehne-himmel", "data-szene") == "tag-unbekannt"
        assert int(seite.get_attribute(".buehne-himmel", "data-buero")) == 95
    finally:
        kontext.close()


def test_die_sonne_steht_mittags_im_sommer_hoeher_als_im_winter(chromium, site):
    """Düsseldorf liegt auf 51,2 Grad Nord: mittags rund 62 Grad zur Sommer- und
    15 Grad zur Wintersonnenwende."""
    _, adresse = site
    hoehen = {}
    for zeitpunkt, jahreszeit in (
        ("2026-06-21T11:35:00Z", "sommer"),
        ("2026-12-21T11:35:00Z", "winter"),
    ):
        seite = _oeffne(chromium, adresse, zeitpunkt, _antwort(0, 10.0))
        try:
            himmel = seite.locator(".buehne-himmel")
            hoehen[jahreszeit] = int(himmel.get_attribute("data-sonne"))
            assert himmel.get_attribute("data-jahreszeit") == jahreszeit
        finally:
            seite.context.close()
    assert 58 <= hoehen["sommer"] <= 66
    assert 11 <= hoehen["winter"] <= 19


@pytest.mark.parametrize(
    ("zeitpunkt", "licht"),
    [
        ("2026-10-13T18:00:00Z", 30),
        ("2026-10-13T22:00:00Z", 4),
        ("2026-10-18T18:00:00Z", 7),
    ],
)
def test_die_bueros_leeren_sich_am_abend_und_am_wochenende(
    chromium, site, zeitpunkt, licht
):
    """Dienstag 20 Uhr brennt in knapp einem Drittel der Bueros Licht, um
    Mitternacht kaum noch; am Sonntag ist der Turm auch um 20 Uhr fast dunkel."""
    _, adresse = site
    seite = _oeffne(chromium, adresse, zeitpunkt, _antwort(0, 10.0))
    try:
        assert int(seite.get_attribute(".buehne-himmel", "data-buero")) == licht
    finally:
        seite.context.close()


def test_ohne_wetterdienst_bleibt_der_himmel_bewoelkt_und_die_zeile_leer(
    chromium, site
):
    _, adresse = site
    seite = _oeffne(chromium, adresse, "2026-10-13T11:05:00Z", None)
    try:
        assert seite.get_attribute(".buehne-himmel", "data-szene") == "tag-unbekannt"
        assert not seite.is_visible("[data-campus-wetter]")
    finally:
        seite.context.close()


def _helligkeit(seite) -> float:
    seite.wait_for_selector(".buehne-himmel.laeuft", timeout=30_000)
    bild = Image.open(io.BytesIO(seite.locator(".buehne-himmel").screenshot()))
    return ImageStat.Stat(bild.convert("L")).mean[0]


def test_der_canvas_malt_tag_hell_und_nacht_dunkel(chromium, site):
    """Die Rechnung laeuft im Browser, also misst der Test die gemalten Pixel."""
    _, adresse = site
    werte = {}
    for name, zeitpunkt in (
        ("tag", "2026-10-13T11:05:00Z"),
        ("nacht", "2026-10-13T21:30:00Z"),
    ):
        seite = _oeffne(chromium, adresse, zeitpunkt, _antwort(0, 10.0), ruhig=True)
        try:
            werte[name] = _helligkeit(seite)
        finally:
            seite.context.close()
    assert werte["tag"] > werte["nacht"] + 40, werte


def _geladen(seite, endung: str) -> list[str]:
    return [u for u in seite.ablauf if u.endswith(endung)]


def test_am_klaren_tag_laden_nur_die_noetigen_platten_und_erst_nach_dem_startbild(
    chromium, site
):
    _, adresse = site
    seite = _oeffne(chromium, adresse, "2026-10-13T11:05:00Z", _antwort(0, 16.0, 10))
    try:
        seite.wait_for_selector(".buehne-himmel.laeuft", timeout=30_000)
        assert not _geladen(seite, ".mp4"), seite.ablauf
        startbild = _geladen(seite, "/campus-turm.jpg")
        tag = _geladen(seite, "/2k/platte-tag.jpg")
        assert startbild and tag and _geladen(seite, "/2k/maske-a.png"), seite.ablauf
        assert seite.ablauf.index(startbild[0]) < seite.ablauf.index(tag[0])
        for unnoetig in ("nacht", "spaet", "regen", "schnee", "gold"):
            assert not _geladen(seite, f"/platte-{unnoetig}.jpg"), unnoetig
        assert not _geladen(seite, "/maske-b.png")
    finally:
        seite.context.close()


def test_nachts_kommen_abend_und_nachtplatte_mit_der_fenstermaske(chromium, site):
    _, adresse = site
    seite = _oeffne(chromium, adresse, "2026-10-13T21:30:00Z", _antwort(0, 8.0, 10))
    try:
        seite.wait_for_selector(".buehne-himmel.laeuft", timeout=30_000)
        for noetig in ("/2k/platte-nacht.jpg", "/2k/platte-spaet.jpg", "/maske-b.png"):
            assert _geladen(seite, noetig), noetig
        assert not _geladen(seite, "/platte-tag.jpg")
    finally:
        seite.context.close()


def test_platten_und_masken_passen_zusammen():
    """Alle Platten eines Satzes sind gleich gross; die blaue 2K-Platte ist das
    Startfoto. Atlas und Leuchthof haben die Kacheln, die der Shader liest."""
    campus = _VORLAGEN / "campus"
    groessen = {"4k": (3840, 2124), "2k": (2560, 1416)}
    for satz, groesse in groessen.items():
        for platte in _PLATTEN:
            datei = campus / satz / f"platte-{platte}.jpg"
            if satz == "2k" and platte == "blau":
                datei = _VORLAGEN / "bilder" / "campus-turm.jpg"
            with Image.open(datei) as bild:
                assert bild.size == groesse, datei
        with Image.open(campus / satz / "maske-a.png") as maske:
            assert maske.mode == "RGB"
            assert maske.size[0] / maske.size[1] == pytest.approx(3840 / 2124, rel=0.01)
            himmel = ImageStat.Stat(maske.getchannel("R")).mean[0] / 255
            assert 0.2 < himmel < 0.6, himmel
    with Image.open(campus / "maske-b.png") as maske:
        assert maske.size == (1920, 1062)
    with Image.open(campus / "himmel-atlas.png") as atlas:
        assert atlas.size == (480, 266 * 7)
    with Image.open(campus / "glanz.png") as glanz:
        assert glanz.size == (960, 531 * 3)
    assert not list(campus.rglob("*.mp4"))
