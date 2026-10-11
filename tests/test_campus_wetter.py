"""Der Campus lebt (Antonio, 11.10.2026): hinter der Startseite laeuft eine
Schleife des Campus Duesseldorf, wie er gerade ist. Tageszeit und Wetter kommen
von Open-Meteo; der Test beantwortet die Anfrage selbst, damit kein Netz
gebraucht wird. Gegenprobe: antwortet der Dienst nicht, bleibt der Himmel
bewoelkt und es steht keine Wetterzeile da.
"""

from __future__ import annotations

import filecmp
import functools
import http.server
import json
import threading
import time
from pathlib import Path

import pytest

from telco_radar.report import statik
from telco_radar.report.html import schreibe_statische_dateien

TAGESZEITEN = ("morgen", "mittag", "abend", "nacht")
HIMMEL = ("sonne", "wolken", "regen", "schnee")

_SEITE = """<!doctype html><html class="ohne-js"><head><meta charset="utf-8"></head>
<body><section class="buehne"><div class="buehne-bild">
<img class="buehne-ebene" data-zeit-bild="tag" data-src="static/bilder/campus-tag.jpg">
<video class="buehne-film" data-basis="static/campus/" muted loop playsinline></video>
</div><div class="buehne-kopf"><h1>Datum</h1>
<p class="buehne-wetter" data-campus-wetter hidden></p></div>
</section><script src="app.js"></script></body></html>"""


class _LangsamesStartbild(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.endswith("/campus-tag.jpg"):
            time.sleep(1.5)
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


def _antwort(uhrzeit: str, code: int, grad: float) -> str:
    return json.dumps(
        {
            "current": {
                "time": f"2026-10-11T{uhrzeit}",
                "weather_code": code,
                "temperature_2m": grad,
            },
            "daily": {
                "sunrise": ["2026-10-11T07:52"],
                "sunset": ["2026-10-11T18:51"],
            },
        }
    )


def _oeffne(chromium, adresse, antwort):
    seite = chromium.new_page()
    seite.add_init_script(_ECHT)

    def beantworte(route):
        if antwort is None:
            route.abort()
        else:
            route.fulfill(status=200, content_type="application/json", body=antwort)

    seite.route("https://api.open-meteo.com/**", beantworte)
    seite.ablauf = []
    seite.on(
        "requestfinished",
        lambda a: a.url.endswith(".jpg") and seite.ablauf.append(a.url),
    )
    seite.on("request", lambda a: a.url.endswith(".mp4") and seite.ablauf.append(a.url))
    seite.goto(f"{adresse}/seite.html")
    seite.wait_for_selector(".buehne-film[data-szene]", state="attached")
    seite.wait_for_function("() => document.readyState === 'complete'")
    seite.wait_for_timeout(300)
    return seite


@pytest.mark.parametrize(
    ("uhrzeit", "code", "grad", "szene", "zeile"),
    [
        ("08:30", 61, 9.4, "morgen-regen", "Campus Düsseldorf · 9 °C, Regen"),
        ("13:05", 73, -1.2, "mittag-schnee", "Campus Düsseldorf · -1 °C, Schnee"),
        ("18:20", 3, 12.6, "abend-wolken", "Campus Düsseldorf · 13 °C, bewölkt"),
        ("23:10", 0, 7.0, "nacht-sonne", "Campus Düsseldorf · 7 °C, klar"),
    ],
)
def test_die_szene_folgt_uhrzeit_und_wetter_am_campus(
    chromium, site, uhrzeit, code, grad, szene, zeile
):
    _, adresse = site
    seite = _oeffne(chromium, adresse, _antwort(uhrzeit, code, grad))
    try:
        film = seite.locator(".buehne-film")
        assert film.get_attribute("data-szene") == szene
        assert film.evaluate("f => f.currentSrc || f.src").endswith(f"/{szene}.mp4")
        assert film.evaluate("f => f.poster").endswith(f"/{szene}.jpg")
        assert seite.inner_text("[data-campus-wetter]") == zeile
        assert seite.is_visible("[data-campus-wetter]")
    finally:
        seite.close()


def test_ohne_wetterdienst_bleibt_der_himmel_bewoelkt_und_die_zeile_leer(
    chromium, site
):
    _, adresse = site
    seite = _oeffne(chromium, adresse, None)
    try:
        szene = seite.get_attribute(".buehne-film", "data-szene")
        assert szene.endswith("-wolken")
        assert szene.split("-")[0] in TAGESZEITEN
        assert not seite.is_visible("[data-campus-wetter]")
    finally:
        seite.close()


def test_jede_szene_liegt_als_schleife_handyfassung_und_standbild_bereit(site):
    ordner, _ = site
    for zeit in TAGESZEITEN:
        for himmel in HIMMEL:
            for datei in (
                f"{zeit}-{himmel}.mp4",
                f"{zeit}-{himmel}-klein.mp4",
                f"{zeit}-{himmel}.jpg",
            ):
                pfad = ordner / "static" / "campus" / datei
                assert pfad.is_file() and pfad.stat().st_size > 10_000, datei


def test_die_schleifen_liegen_nicht_doppelt_auf_der_platte(site):
    ordner, _ = site
    vorlage = Path(statik.__file__).parent / "templates" / "static" / "campus"
    for datei in sorted(vorlage.iterdir()):
        kopie = ordner / "static" / "campus" / datei.name
        if datei.stat().st_dev == ordner.stat().st_dev:
            assert kopie.samefile(datei), datei.name
        else:
            assert filecmp.cmp(kopie, datei, shallow=False), datei.name


def test_nur_eine_schleife_und_erst_nach_dem_startbild(chromium, site):
    _, adresse = site
    seite = _oeffne(chromium, adresse, _antwort("13:05", 3, 12.6))
    try:
        filme = [u for u in seite.ablauf if u.endswith(".mp4")]
        assert len(filme) == 1, seite.ablauf
        startbild = [u for u in seite.ablauf if u.endswith("/campus-tag.jpg")]
        assert startbild, seite.ablauf
        assert seite.ablauf.index(startbild[0]) < seite.ablauf.index(filme[0])
    finally:
        seite.close()
