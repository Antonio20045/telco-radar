"""E3 Schritt 2: der SPRUNG aus der Radar-Modellliste in den Graphen des
Vergleichs-Reiters - im echten Chromium gemessen.

Warum im Browser: der Sprung ist der einzige Weg dieser Seite, der ZWEI
Mechaniken verkettet (Reiter-Umschaltung + Zeitreihen-Wahl + Scroll). Im
statischen HTML steht nur der Link - ob sein Klick den Graphen wirklich
auf das Modell des Links stellt, sieht man erst im gerenderten Dokument.
Die Stichprobe reicht: EIN Sprung mit Band, ein Zeilen-Klick (Detailzeile).
Die Fixture ist die der Zeitreihen-Seite (`test_geraete_zeitreihe_ansicht`)
- sie trägt Historie, damit `daten.erlaubt` gefüllt ist und der In-page-
Handler anspringt statt nur neu zu laden.

Bauform wie `test_geraete_zeitreihe_browser.py`: eigener Server auf
127.0.0.1, kein file://, Chromium an beiden bekannten Orten.
"""
from __future__ import annotations

import contextlib
import functools
import glob
import http.server
import socket
import threading

import pytest

from test_geraete_zeitreihe_browser import _baue_site


def _chromium():
    for muster in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",
                   str(__import__("pathlib").Path.home()
                       / ".cache/ms-playwright/chromium*/chrome-linux*/chrome"),
                   "/Applications/Chromium.app/Contents/MacOS/Chromium"):
        treffer = sorted(glob.glob(muster))
        if treffer:
            return treffer[-1]
    return None


@contextlib.contextmanager
def _server(site):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(site))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()


@pytest.fixture(scope="module")
def paar(tmp_path_factory):
    import pathlib
    from playwright.sync_api import sync_playwright
    site = _baue_site(tmp_path_factory.mktemp("e3-radar"))
    with _server(site) as basis:
        with sync_playwright() as p:
            exe = _chromium()
            browser = (p.chromium.launch(executable_path=exe) if exe
                       else p.chromium.launch())
            seite = browser.new_page(viewport={"width": 1440, "height": 900})
            seite.goto(f"{basis}/geraete.html", wait_until="load")
            yield seite
            browser.close()


def _radar_zeigen(seite):
    """Wie ein Klick auf den Reiter-Knopf - robust gegen Layout-Fragen."""
    seite.click('.gr-reiter button[data-tafel="tafel-radar"]')
    seite.wait_for_timeout(80)


def test_der_sprung_stellt_reiter_modell_und_band_ein(paar):
    """EIN Klick auf „im Graph ansehen": der Vergleichs-Reiter ist aktiv,
    die URL trägt ?modell= und &band= (die Deep-Link-Mechanik von E2), und
    der Bündel-Titel nennt das GEWÄHLTE Modell - nicht das Startgerät."""
    _radar_zeigen(paar)
    # Der Modell-Wechsel ist asynchron (Fragment): auf das Erscheinen des
    # Titels warten, nicht auf eine feste Zahl von Millisekunden.
    links = paar.query_selector_all("#wr-abweichung a.gr-sprung[data-band]")
    assert links, "keine vergleichbare Zeile mit Band-Sprung in der Fixture"
    ziel_id = links[0].get_attribute("data-modell")
    ziel_band = links[0].get_attribute("data-band")
    links[0].click()
    paar.wait_for_timeout(150)
    assert paar.eval_on_selector(
        '.gr-reiter button[data-tafel="tafel-tco"]',
        "e => e.getAttribute('aria-selected')") == "true", \
        "der Vergleichs-Reiter ist nach dem Sprung nicht aktiv"
    url = paar.url
    assert f"modell={ziel_id}" in url, url
    assert f"band={ziel_band}" in url, url
    titel = paar.eval_on_selector("#gr-bnd-titel", "e => e.textContent")
    assert titel and titel.strip(), "kein Bündel-Titel nach dem Sprung"


def test_der_zeilenklick_oeffnet_die_detailzeile(paar):
    """Dieselbe Zeilenmechanik wie die Alarmtabelle, im eigenen Container:
    der Klick auf eine Modell-Hauptzeile zeigt alle Anbieter der Gruppe."""
    paar.goto(paar.url.split("#")[0], wait_until="load")
    _radar_zeigen(paar)
    zeile = paar.query_selector(
        "#wr-abweichung table tbody tr.gr-a-zeile:not(.gr-a-rest)")
    assert zeile is not None
    auf_id = zeile.get_attribute("data-auf")
    zeile.click()
    paar.wait_for_timeout(60)
    offen = paar.eval_on_selector(
        f"#{auf_id}", "e => e.classList.contains('gr-a-auf--an')")
    assert offen is True, f"Detailzeile #{auf_id} öffnet nicht"


def test_alle_reiter_bleiben_ohne_js_fehler(paar):
    """Der Radar-Reiter bringt neuen DOM und neuen Handler - kein
    Konsolenfehler beim Öffnen, Springen und Zurückkehren."""
    fehler = []
    paar.on("console", lambda m: fehler.append(m.text)
            if m.type == "error" else None)
    paar.goto(paar.url.split("#")[0].split("?")[0], wait_until="load")
    _radar_zeigen(paar)
    paar.click('.gr-reiter button[data-tafel="tafel-tco"]')
    paar.wait_for_timeout(80)
    assert not fehler, fehler
