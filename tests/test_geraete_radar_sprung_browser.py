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
    """Wie ein Klick auf den Reiter-Knopf - robust gegen Layout-Fragen.

    P4/D1 (STRATEGIE_GERAETE_V3, 18.09.2026): die Modell-Liste steht
    seit dem Design-Durchlauf IM AUFKLAPPER unter der Balkengrafik -
    Sprung- und Zeilenklick-Tests oeffnen ihn hier, sonst wartet der
    Klick auf eine unsichtbare Zeile."""
    seite.click('.gr-reiter button[data-tafel="tafel-radar"]')
    seite.wait_for_timeout(80)
    auf = seite.query_selector("#wr-abweichung details.gr-auf:not([open])")
    if auf:
        auf.query_selector("summary").click()
        seite.wait_for_timeout(60)


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


# ==========================================================================
# P4 SCHRITT 2c (STRATEGIE_GERAETE_V3, 18.09.2026): die ZWEITE Kante des
# roten Fadens - Radar -> KATALOG -> Zeitreihe am EINEN Schluessel, und
# der Ansichts-Deep-Link ?ansicht= (P3-Rest). Statische Haelfte:
# tests/test_geraete_faden_schluessel.py.
# ==========================================================================

def test_der_katalog_sprung_legt_filter_und_zeile_frei(paar):
    """Klick auf „im Katalog“ einer Radar-Modellzeile: der Katalog-Reiter
    ist aktiv, die Zielzeile (derselbe `modell_schluessel` wie data-modell
    des Links) ist SICHTBAR und markiert (.gr-k-ziel) - selbst unter
    einem AKTIVEN Markenfilter, der sie sonst versteckt hätte. Der Sprung
    legt Filter und Deckel frei, statt an einer unsichtbaren Zeile zu
    enden."""
    paar.goto(paar.url.split("#")[0].split("?")[0], wait_until="load")
    # Filter am KATALOG setzen (Samsung), der Sprung zielt auf ein Apple-
    # Modell - ohne Freilegen waere die Zeile versteckt.
    paar.click('.gr-reiter button[data-tafel="tafel-katalog"]')
    paar.select_option('#tafel-katalog select[data-filter="marke"]',
                       label="Samsung")
    _radar_zeigen(paar)
    link = next(a for a in paar.query_selector_all(
        "#wr-abweichung a.gr-ksprung[data-modell]")
        if "apple" in a.get_attribute("data-modell"))
    ziel = link.get_attribute("data-modell")
    link.click()
    paar.wait_for_timeout(250)
    assert paar.eval_on_selector(
        '.gr-reiter button[data-tafel="tafel-katalog"]',
        "e => e.getAttribute('aria-selected')") == "true", \
        "der Katalog-Reiter ist nach dem Sprung nicht aktiv"
    sichtbar = paar.eval_on_selector(
        f'#gr-katalogtabelle tr.gr-k-zeile[data-modell="{ziel}"]',
        "e => !e.hidden && e.checkVisibility()")
    assert sichtbar is True, \
        f"Zielzeile {ziel} bleibt unter dem Filter unsichtbar"
    markiert = paar.eval_on_selector(
        f'#gr-katalogtabelle tr.gr-k-zeile[data-modell="{ziel}"]',
        "e => e.classList.contains('gr-k-ziel')")
    assert markiert is True, "die Zielzeile ist nicht markiert"
    # Der Filter ist zurueckgesetzt - der Leser sieht, was die Tabelle
    # gerade zeigt (dieselbe Regel wie der Filterleisten-Etikett-Satz).
    wert = paar.eval_on_selector(
        '#tafel-katalog select[data-filter="marke"]', "e => e.value")
    assert wert == "", f"Markenfilter bleibt auf {wert!r} stehen"


def test_der_katalog_graph_sprung_waehlt_das_modell(paar):
    """Klick auf „im Graph ansehen“ an der KATALOG-Modellzeile: der
    Vergleichs-Reiter ist aktiv und die URL traegt das GEWAEHLTE Modell -
    der dritte Reiter der Kette am selben Schluessel."""
    paar.goto(paar.url.split("#")[0].split("?")[0], wait_until="load")
    paar.click('.gr-reiter button[data-tafel="tafel-katalog"]')
    link = paar.query_selector(
        "#gr-katalogtabelle tr.gr-k-zeile a.gr-sprung[data-modell]")
    assert link is not None, \
        "kein Graph-Sprung im Katalog der Fixture - der Test prueft nichts"
    ziel = link.get_attribute("data-modell")
    link.click()
    paar.wait_for_timeout(400)
    assert paar.eval_on_selector(
        '.gr-reiter button[data-tafel="tafel-tco"]',
        "e => e.getAttribute('aria-selected')") == "true", \
        "der Vergleichs-Reiter ist nach dem Sprung nicht aktiv"
    assert f"modell={ziel}" in paar.url, paar.url
    # Das Suchfeld nennt das gewaehlte Modell (Kacheln sind nur
    # Schnelleingang - das Ziel kann ausserhalb der 6 liegen).
    feld = paar.eval_on_selector("#gr-zr-suche", "e => e.value")
    assert feld and feld.strip(), "das Suchfeld nennt kein gewaehltes Modell"


def test_ansicht_deep_link_schaltet_und_ueberlebt(paar):
    """P3-Rest, P4 gebaut: ?ansicht=tco stellt die TCO-Ansicht beim Laden
    her; der RUECKKnopf loescht den Parameter (barpreis ist die Grundfrage
    und bleibt die kurze URL); ein Modellwechsel der Zeitreihe haelt ihn
    stehen (bis P4 baute waehle() die URL neu auf und loeschte ihn)."""
    basis = paar.url.split("/geraete.html")[0] + "/geraete.html"
    paar.goto(basis + "?ansicht=tco", wait_until="load")
    assert paar.eval_on_selector(
        "#gr-katalogtabelle",
        "e => e.classList.contains('gr-katalog--tco')") is True, \
        "?ansicht=tco schaltet die TCO-Ansicht beim Laden nicht um"
    assert paar.eval_on_selector(
        '.gr-kansicht button[data-ansicht="tco"]',
        "e => e.getAttribute('aria-pressed')") == "true"
    paar.click('.gr-reiter button[data-tafel="tafel-katalog"]')
    paar.click('.gr-kansicht button[data-ansicht="barpreis"]')
    paar.wait_for_timeout(120)
    assert "ansicht=" not in paar.url, \
        f"ansicht-Parameter bleibt nach barpreis-Klick stehen: {paar.url}"
    # Modellwechsel der Zeitreihe: modell/band kommen dazu, ansicht bleibt
    paar.click('.gr-kansicht button[data-ansicht="tco"]')
    paar.wait_for_timeout(80)
    paar.click('.gr-reiter button[data-tafel="tafel-tco"]')
    paar.wait_for_timeout(80)
    paar.click("#gr-zr-baender button[data-band]:not([disabled])")
    paar.wait_for_timeout(200)
    assert "ansicht=tco" in paar.url, \
        f"ansicht-Parameter geht beim Band-/Modellwechsel verloren: {paar.url}"
    # Aufraeumen: URL ohne Parameter, damit nachfolgende Tests ein
    # sauberes Startgeraett sehen (die Fixture hat Modulgueltigkeit).
    paar.goto(basis, wait_until="load")
