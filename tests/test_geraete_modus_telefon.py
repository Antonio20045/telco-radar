"""Die Leiste "Mit Tarif | Einzelgerät" verdeckt am Telefon keinen Text.

Am 10.10.2026 schwebte sie auf 390 px beim Scrollen mitten über der
Modellliste und dem Antwortsatz. Am Telefon bleibt sie an ihrem Platz unter
dem Bild; am Rechner darf sie weiter mitlaufen.
"""

from __future__ import annotations

import functools
import http.server
import threading

import pytest
import test_geraete_seite


@pytest.fixture(scope="module")
def basis(tmp_path_factory):
    site = test_geraete_seite._baue(tmp_path_factory.mktemp("modus"))
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(site)
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()


def _lage(chromium, basis, breite, hoehe):
    seite = chromium.new_page(viewport={"width": breite, "height": hoehe})
    try:
        seite.goto(f"{basis}/geraete.html")
        leiste = seite.locator(".gr-reiter.gx-modus")
        assert leiste.count() == 1
        art = leiste.evaluate("e => getComputedStyle(e).position")
        seite.evaluate(
            "window.scrollTo(0, document.getElementById('tafel-tco')"
            ".getBoundingClientRect().top + scrollY + 400)"
        )
        seite.wait_for_timeout(200)
        unten = leiste.evaluate("e => e.getBoundingClientRect().bottom")
        return art, unten
    finally:
        seite.close()


def test_am_telefon_schwebt_die_leiste_nicht_ueber_dem_text(basis, chromium):
    art, unten = _lage(chromium, basis, 390, 844)
    assert art != "sticky"
    assert unten < 0


def test_am_rechner_laeuft_die_leiste_mit(basis, chromium):
    art, unten = _lage(chromium, basis, 1440, 900)
    assert art == "sticky"
    assert unten > 0
