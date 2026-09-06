"""BRIEF F-4a (05.09.2026, hoechste Prioritaet): "Die Antwortzeile ist die
Seite" - im echten Browser gemessen, weil "dominant" eine Aussage ueber
den AUSGERECHNETEN Stil ist (computed style), nicht ueber die Quelle. Ein
statischer Test sieht `font-size:32px` im Stylesheet, aber nicht, ob eine
spaetere Regel, eine Kaskade oder ein vererbter Wert das am Ende wieder
einkassiert - genau die Lehre aus der Positionskarte vom 10.08.2026
(CLAUDE.md §6).

Massstab ist Desktop 1440x900 (Antonio 18:52: Laptop-only, Mobil ist kein
Kriterium hier).

Dieselbe Bauform wie `tests/test_geraete_reiter_browser.py`: eigener Server
auf 127.0.0.1 (kein file://, kein Netz), Chromium an beiden bekannten Orten
gesucht, ein Browserstart je Testlauf.

Fixture: `_baue()` aus `test_geraete_tco_zustand.py` (ein Modell, o2 +
Vodafone, beide Antwort-Zahlen belastbar, Chart mit Daten) - dieselbe
Fixture, mit der die statischen Antwortzeilen-Tests in
`test_geraete_faden.py` schon laufen. Sie schreibt die gerenderte Seite
nach `tmp_path/"mit"/"site"`; dieser Test serviert genau dieses
Verzeichnis, statt es neu zu rendern.

Drei Abnahmekriterien des Auftrags, drei Tests:
  1. Schriftgroesse der Leitzahl >= Chart-Titel/Achsen; DOM-Reihenfolge
     Auswahl -> Antwortzeile -> Chart bleibt.
  2. Erklaerzeile vorhanden, <= 80 Zeichen, direkt an der Antwortzeile.
  3. (Antwortzeilen-Inhalt selbst: siehe test_geraete_faden.py /
     test_geraete_tco_hauptansicht.py - unveraendert, hier nicht erneut
     geprueft.)
"""
from __future__ import annotations

import contextlib
import functools
import glob
import http.server
import socket
import threading
from pathlib import Path

import pytest

from test_geraete_tco_zustand import _baue

REPO = Path(__file__).resolve().parents[1]


def _chromium():
    for muster in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",
                   str(Path.home() / ".cache/ms-playwright"
                       / "chromium*/chrome-linux*/chrome")):
        treffer = sorted(glob.glob(muster))
        if treffer:
            return treffer[-1]
    return None


@contextlib.contextmanager
def _server(site: Path):
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
def _seite(tmp_path_factory):
    """Ein Browser, eine Seite bei 1440x900 - der Massstab dieses Auftrags."""
    sync_playwright = pytest.importorskip(
        "playwright.sync_api", reason="playwright fehlt").sync_playwright

    tmp_path = tmp_path_factory.mktemp("antwortzeile")
    _baue(tmp_path)  # schreibt nach tmp_path/"mit"/"site"
    site = tmp_path / "mit" / "site"

    exe = _chromium()
    with _server(site) as basis, sync_playwright() as p:
        browser = (p.chromium.launch(executable_path=exe) if exe
                   else p.chromium.launch())
        seite = browser.new_page(viewport={"width": 1440, "height": 900})
        seite.goto(f"{basis}/geraete.html", wait_until="load")
        yield seite
        browser.close()


# --------------------------------------------------------------------------
# Kriterium 1: Schriftgroesse und DOM-Reihenfolge
# --------------------------------------------------------------------------

def test_leitzahl_ist_mindestens_so_gross_wie_chart_titel_und_achsen(_seite):
    """Die Zahl der Antwortzeile ist die groesste Schrift dieses
    Seitenabschnitts - konkret: nicht kleiner als die Chart-Chrome-Zeile
    (`.gr-g0-chrome`, der einzige Fliesstext am Graphen) und keine der
    Achsenbeschriftungen (`.gr-g0-achse`)."""
    leitzahl = _seite.eval_on_selector(
        "#tafel-tco .gr-tmodell:not([hidden]) .gr-antwort-zahl",
        "(e) => parseFloat(getComputedStyle(e).fontSize)")
    chart_titel = _seite.eval_on_selector(
        "#tafel-tco .gr-tmodell:not([hidden]) .gr-g0-chrome",
        "(e) => parseFloat(getComputedStyle(e).fontSize)")
    achsen = _seite.eval_on_selector_all(
        "#tafel-tco .gr-tmodell:not([hidden]) .gr-g0-achse",
        "(es) => es.map(e => parseFloat(getComputedStyle(e).fontSize))")

    assert achsen, "keine Achsenbeschriftung gefunden - Fixture ohne Chart?"
    assert leitzahl >= chart_titel, (leitzahl, chart_titel)
    assert all(leitzahl >= a for a in achsen), (leitzahl, achsen)
    # Gegenprobe: die Messung ist nicht zufaellig trivial (z. B. weil beide
    # winzig waeren) - die Leitzahl muss wirklich deutlich groesser sein
    # als die 12px-Chrome-/Achsenschrift, nicht nur auf dem Papier gleich.
    assert leitzahl >= chart_titel + 10, (leitzahl, chart_titel)


def test_dom_reihenfolge_auswahl_antwortzeile_chart_bleibt(_seite):
    """Auswahl -> Antwortzeile -> Chart, im LEBENDEN DOM gemessen (nicht
    nur im HTML-Quelltext wie in test_geraete_faden.py) - derselbe Baum,
    den der Leser wirklich sieht."""
    positionen = _seite.evaluate(
        "() => { const alle = [...document.querySelectorAll('#tafel-tco *')]; "
        "const msel = document.querySelector('#tafel-tco .gr-msel'); "
        "const block = document.querySelector("
        "  '#tafel-tco .gr-tmodell:not([hidden])'); "
        "const antwort = block.querySelector('.gr-antwort'); "
        "const chart = block.querySelector('figure.gr-grafik--zeitreihe'); "
        "return [alle.indexOf(msel), alle.indexOf(antwort), "
        "alle.indexOf(chart)]; }")
    msel_pos, antwort_pos, chart_pos = positionen
    assert -1 not in positionen, positionen
    assert msel_pos < antwort_pos < chart_pos, positionen


# --------------------------------------------------------------------------
# Kriterium 2: Erklaerzeile vorhanden, kurz, direkt benachbart
# --------------------------------------------------------------------------

def test_erklaerzeile_ist_vorhanden_kurz_und_direkt_benachbart(_seite):
    ergebnis = _seite.eval_on_selector(
        "#tafel-tco .gr-tmodell:not([hidden]) .gr-antwort",
        "(antwort) => { "
        "const erk = antwort.querySelector('.gr-antwort-erklaer'); "
        "if (!erk) return null; "
        "return {text: erk.textContent.trim(), "
        "istKindDerAntwortzeile: erk.parentElement === antwort, "
        "istLetztesKind: antwort.lastElementChild === erk}; }")
    assert ergebnis is not None, "die Erklaerzeile fehlt"
    assert ergebnis["text"], "die Erklaerzeile ist leer"
    assert len(ergebnis["text"]) <= 80, \
        f"{len(ergebnis['text'])} Zeichen: {ergebnis['text']!r}"
    assert ergebnis["istKindDerAntwortzeile"], \
        "die Erklaerzeile steht nicht in der Antwortzeile"
    assert ergebnis["istLetztesKind"], \
        "die Erklaerzeile ist nicht direkt benachbart"


def test_erklaerzeile_unterscheidet_geraetepreis_und_tarif(_seite):
    """Vision-Befund 8: "guenstig mit Tarif: 1.619,64 €" ist fuer Laien
    mehrdeutig (teurer? guenstiger?) - die Erklaerzeile muss die zwei
    Begriffe tatsaechlich benennen, nicht nur irgendeinen Satz zeigen."""
    text = _seite.eval_on_selector(
        "#tafel-tco .gr-tmodell:not([hidden]) .gr-antwort-erklaer",
        "(e) => e.textContent")
    assert "Gerätepreis" in text
    assert "Tarif" in text
