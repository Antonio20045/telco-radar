"""Nur Tag (Antonio, 10.10.2026): Farben und Startbild sind zu jeder Uhrzeit die
Tagesansicht. Gemessen im echten Chromium mit einer Uhr am Abend und einem
Browser, der sich nicht als ferngesteuert meldet; die Gegenprobe ist der Gruss,
der weiter der Uhrzeit folgt.
"""

from __future__ import annotations

import functools
import http.server
import threading

import pytest

from telco_radar.report.html import schreibe_statische_dateien

_SEITE = """<!doctype html><html class="ohne-js"><head><meta charset="utf-8"></head>
<body><section class="buehne"><div class="buehne-bild">
<img class="buehne-ebene" data-zeit-bild="tag" data-src="data:,">
<img class="buehne-ebene" data-zeit-bild="abend" data-src="data:,">
</div><div class="buehne-kopf"><p class="buehne-gruss" data-gruss>Ausgabe</p></div>
</section><script src="app.js"></script></body></html>"""


def _uhr(stunde: int) -> str:
    return (
        "Object.defineProperty(navigator,'webdriver',{get:()=>false});"
        "const _D=Date;Date=class extends _D{constructor(...a){super(...(a.length?a:"
        f"[2026,9,10,{stunde},15,0]))}}"
        f"static now(){{return new _D(2026,9,10,{stunde},15).getTime()}}}};"
    )


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    ordner = tmp_path_factory.mktemp("tag")
    schreibe_statische_dateien(ordner)
    (ordner / "seite.html").write_text(_SEITE, encoding="utf-8")
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(ordner)
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()


@pytest.mark.parametrize(
    ("stunde", "gruss"), [(20, "Guten Abend"), (23, "Guten Abend"), (12, "Guten Tag")]
)
def test_jede_uhrzeit_zeigt_die_tagesansicht(chromium, site, stunde, gruss):
    seite = chromium.new_page()
    try:
        seite.add_init_script(_uhr(stunde))
        seite.goto(f"{site}/seite.html")
        assert seite.evaluate("navigator.webdriver") is False
        assert seite.evaluate("new Date().getHours()") == stunde
        assert seite.get_attribute("html", "data-zeit") == "tag"
        aktiv = seite.locator(".buehne-ebene.aktiv")
        assert aktiv.count() == 1
        assert aktiv.get_attribute("data-zeit-bild") == "tag"
        assert seite.inner_text("[data-gruss]") == gruss
    finally:
        seite.close()
