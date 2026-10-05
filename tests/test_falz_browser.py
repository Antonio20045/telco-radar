"""Steht die Nachricht im ersten Bildschirm? Gemessen, nicht geschaetzt.

Der Befund vom 8. August war kein Geschmacksurteil, sondern eine Hoehe: der
Zwei-Minuten-Kasten stand mit fuenf mehrzeiligen Eintraegen ueber dem
Aufmacher, und die Schlagzeile der Ausgabe begann darunter. Am Telefon war
sie zwei Wischer entfernt.

Genau das laesst sich im HTML nicht sehen. Ob eine Schlagzeile ohne Scrollen
sichtbar ist, entscheiden Schriftgroessen, Zeilenumbrueche, Bildhoehen und
die Umbruchpunkte des Rasters - also der Browser. Dieser Test misst deshalb
an einem echten Chromium auf zwei Formaten:

    1440 x 900   der Schreibtisch, dasselbe Mass wie scripts/pruefe_portal.py
     390 x 844   das Telefon, auf dem der Bericht montags gelesen wird

Er ist die Gegenprobe zu jeder kuenftigen Ergaenzung oberhalb der Falz. Wer
dort etwas einfuegt, sieht hier, was es kostet - `pruefe_portal.py`
Kriterium 1 zaehlt Geschichten, dieses hier misst Pixel.
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import json
import shutil
import socket
import threading
from pathlib import Path

import pytest
from bestand_pfad import BILDER_BESTAND, ZUSTAND, verlinke_neben_data

from telco_radar.report.html import render_site

BERICHT_DIR = BILDER_BESTAND / "reports"
AUSGABE = "2026-08-08"

FORMATE = [("Schreibtisch", 1440, 900), ("Telefon", 390, 844)]


@contextlib.contextmanager
def _server(site: Path):
    """Ein lokaler Server statt file://.

    Dieselbe Lehre wie in `pruefe_portal.py`: unter file:// sperrt die
    Same-Origin-Regel `fetch()`, und die Messung faende einen Fehler, den es
    nicht gibt. Bindet auf 127.0.0.1, braucht kein Netz.
    """
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(site)
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()


def _baue(tmp_path: Path) -> Path:
    """Die Ausgabe 2026-08-08 mit ihren Bildern aus `BILDER_BESTAND` - siehe
    `tests/test_startseite_kurzpfad.py`, wo dieselbe Rechnung steht. Ohne
    Bilder waere jede Meldung gleich hoch und der Aufmacher zu kurz, um die
    Frage ueberhaupt zu stellen. Das Thema aus `highlight_topics.json` des
    Schnappschusses 2026-10-03 (dort `beendet`) laeuft hier als `aktiv`, damit
    das Fokusband entsteht, dessen Hoehe gemessen wird."""
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True)
    for endung in (".json", ".md"):
        shutil.copy(BERICHT_DIR / f"{AUSGABE}{endung}", reports / f"{AUSGABE}{endung}")
    shutil.copytree(
        BILDER_BESTAND / "state" / "report_images",
        tmp_path / "data" / "state" / "report_images",
    )
    themen = json.loads((ZUSTAND / "highlight_topics.json").read_text("utf-8"))
    for thema in themen["topics"]:
        thema["status"] = "aktiv"
    (tmp_path / "data" / "state" / "highlight_topics.json").write_text(
        json.dumps(themen, ensure_ascii=False), encoding="utf-8"
    )
    verlinke_neben_data(tmp_path)
    site = tmp_path / "site"
    render_site(site, reports, cfg=None)
    return site


@pytest.fixture(scope="module")
def _gemessen(tmp_path_factory, chromium):
    """Ein Browserstart je Testlauf, nicht je Format: Chromium hochzufahren
    kostet mehr als die Messung selbst."""
    site = _baue(tmp_path_factory.mktemp("falz"))

    werte: dict[str, dict] = {}
    with _server(site) as wurzel:
        for name, breite, hoehe in FORMATE:
            seite = chromium.new_page(viewport={"width": breite, "height": hoehe})
            try:
                seite.goto(f"{wurzel}/index.html", wait_until="load")
                seite.wait_for_timeout(400)
                szl = seite.locator(".aufmacher .szl").first
                werte[name] = {
                    "hoehe": hoehe,
                    "kasten": szl.bounding_box(),
                    "text": " ".join(szl.inner_text().split())[:80],
                    "kurzpfad": (
                        seite.locator(".kurzpfad").first.bounding_box()
                        if seite.locator(".kurzpfad").count()
                        else None
                    ),
                    "fokusband": (
                        seite.locator(".fokusband").first.bounding_box()
                        if seite.locator(".fokusband").count()
                        else None
                    ),
                }
            finally:
                seite.close()
    return werte


@pytest.mark.parametrize("format_name", [f[0] for f in FORMATE])
def test_die_aufmacher_schlagzeile_steht_ohne_scrollen_da(_gemessen, format_name):
    """Die eine Zahl, um die es beim Rueckbau des Kurzpfads ging.

    Verlangt wird die VOLLSTAENDIGE Schlagzeile im ersten Bildschirm, nicht
    ihre erste Zeile: eine halb angeschnittene Ueberschrift ist der Zustand,
    den man sofort wegscrollen will."""
    messung = _gemessen[format_name]
    kasten = messung["kasten"]
    assert kasten is not None, "die Titelseite hat keinen Aufmacher"
    unterkante = kasten["y"] + kasten["height"]
    assert unterkante <= messung["hoehe"], (
        f"{format_name}: die Schlagzeile {messung['text']!r} endet bei "
        f"{unterkante:.0f} px und damit unterhalb der Falz "
        f"({messung['hoehe']} px)"
    )


@pytest.mark.parametrize("format_name", [f[0] for f in FORMATE])
def test_der_kurzpfad_steht_nicht_ueber_der_schlagzeile(_gemessen, format_name):
    """Der Rueckbau selbst, in Pixeln statt in Reihenfolge im Quelltext.

    Auf dem Schreibtisch steht der Kasten NEBEN der Schlagzeile: er beginnt
    sogar ein paar Pixel hoeher, weil die Schlagzeile links noch eine
    Rubrikzeile ueber sich hat. Das ist kein Verstoss - die beiden teilen
    sich dasselbe Baender, nur in verschiedenen Spalten. Auf dem Telefon
    faellt die Spalte unter den Aufmacher.

    Verboten ist deshalb nicht "hoeher", sondern "davor": ein Kasten, der
    ENDET, bevor die Schlagzeile anfaengt, steht in derselben Spalte ueber
    ihr und schiebt sie nach unten. Genau das war der Zustand vom
    8. August."""
    messung = _gemessen[format_name]
    kurzpfad = messung["kurzpfad"]
    assert kurzpfad is not None, "diese Ausgabe hat keinen Kurzpfad"
    unterkante = kurzpfad["y"] + kurzpfad["height"]
    assert unterkante > messung["kasten"]["y"], (
        f"{format_name}: der Kurzpfad endet bei {unterkante:.0f} px, bevor "
        f"die Schlagzeile bei {messung['kasten']['y']:.0f} px beginnt - er "
        f"steht ueber ihr statt neben ihr"
    )


@pytest.mark.parametrize("format_name", [f[0] for f in FORMATE])
def test_das_fokusband_steht_ohne_scrollen_da(_gemessen, format_name):
    """Die Themenseite ist nur ueber dieses Band auffindbar - also muss es
    im ersten Bildschirm stehen.

    Am 29.08.2026 gemessen, an der live ausgelieferten Ausgabe vom 28.08.:
    das Band stand am ENDE der linken Spalte, hinter Aufmacher, zweiter und
    dritter Reihe - auf dem Schreibtisch bei y=1316 px (Falz 900), auf dem
    Telefon bei y=3031 px (Falz 844). Antonio: "es ist keine highlightseite
    zu sehen live im browser wenn ich die domain aufrufe." Er hatte recht,
    und es war im HTML nicht zu sehen: der Link war da, nur nie im Bild.

    Die rechte Spalte waere der billigere Platz gewesen (sie beginnt auf
    dem Schreibtisch bei y=132 px und kostet die Hauptspalte nichts) - aber
    auf dem Telefon faellt sie unter das ganze Raster, und dort waere das
    Band wieder drei Bildschirme tief. Deshalb steht es ueber dem
    Aufmacher, als EINE Zeile: der Zwei-Minuten-Kasten hat an derselben
    Stelle die Titelseite gekostet (09.08.2026), aber das war ein Block aus
    fuenf Absaetzen, kein Strich. Was es wirklich kostet, misst
    `pruefe_portal.py` Kriterium 1."""
    messung = _gemessen[format_name]
    kasten = messung["fokusband"]
    assert kasten is not None, "diese Ausgabe hat kein laufendes Thema"
    unterkante = kasten["y"] + kasten["height"]
    assert unterkante <= messung["hoehe"], (
        f"{format_name}: das Fokusband endet bei {unterkante:.0f} px und "
        f"damit unterhalb der Falz ({messung['hoehe']} px) - die "
        f"Themenseite ist beim Aufruf der Domain unsichtbar"
    )


@pytest.mark.parametrize("format_name", [f[0] for f in FORMATE])
def test_das_fokusband_verdraengt_die_schlagzeile_nicht(_gemessen, format_name):
    """Die Gegenprobe zum Test darueber - sonst waere er mit einem Band
    erfuellbar, das die Ausgabe aus dem Bild schiebt. Genau der Tausch war
    der Fehler vom 09.08.2026."""
    messung = _gemessen[format_name]
    assert messung["fokusband"] is not None, "kein laufendes Thema"
    kasten = messung["kasten"]
    assert kasten is not None, "die Titelseite hat keinen Aufmacher"
    unterkante = kasten["y"] + kasten["height"]
    assert unterkante <= messung["hoehe"], (
        f"{format_name}: mit dem Fokusband endet die Schlagzeile erst bei "
        f"{unterkante:.0f} px, Falz {messung['hoehe']} px"
    )
