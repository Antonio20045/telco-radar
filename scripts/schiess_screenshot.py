#!/usr/bin/env python3
"""Screenshots einer gerenderten Seite - und die Gegenprobe an den Daten.

WARUM ES DAS GIBT. Die Geraeteseite ist am 10.08.2026 mit einer Grafik
ausgeliefert worden, deren Etiketten bis zu 235 px von ihrem Punkt entfernt
standen - "iPhone 17 · 512 GB" auf Hoehe der 175-EUR-Linie bei einem echten
Preis von 1199 EUR. Die Sitzung hatte Tests geschrieben, Daten geprueft und
Quellen diagnostiziert; sie hatte das Ergebnis nur nie mit den Augen
kontrolliert. Ein einziger Screenshot haette gereicht.

Im ganzen Repo gab es bis dahin keinen Abnahme-Screenshot: `pruefe_portal.py`
misst im Browser, aber es fotografiert nicht. Dieses Skript schliesst die
Luecke und macht aus "ansehen" einen Befehl.

EINE AUSGABE: PNGs je Format (1440x900 und 390x844), einmal die ganze Seite
und einmal der genannte Ausschnitt. Die sieht ein MENSCH an - dafuer gibt es
dieses Skript, und CLAUDE.md nennt den Grund: "Eine Grafik ist erst fertig,
wenn sie jemand ANGESEHEN hat."

Bis zum 30.08.2026 gab es hier zweitens `--pruefe-etiketten`, die
Gegenprobe zur Positionskarte: aus der gerenderten Etikettenhoehe wurde der
Preis zurueckgerechnet und gegen `data-preis` gehalten. Die Karte ist
geloescht, also auch die Messung. Was an ihre Stelle tritt, steht in
`tests/test_geraete_reiter_browser.py`.

Ohne `--site` wird frisch nach einem temporaeren Ordner gerendert; `site/` im
Repo wird nie angefasst.

    python scripts/schiess_screenshot.py --seite geraete.html \\
        --ausschnitt '#tafel-alarme'
"""
from __future__ import annotations

import argparse
import functools
import glob
import http.server
import json
import socket
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

# Dieselben zwei Formate wie in tests/test_falz_browser.py und im Auftrag.
FORMATE = [("schreibtisch", 1440, 900), ("telefon", 390, 844)]


def _chromium() -> str | None:
    """Wo der Browser liegt - oder None, wenn Playwright ihn selbst findet.

    Zwei Orte, weil es zwei Maschinen gibt: das Sandbox-Image legt Chromium
    unter /opt/pw-browsers ab, `playwright install` auf einem GitHub-Runner
    unter ~/.cache/ms-playwright. Wortgleich zu tests/test_falz_browser.py -
    wer nur den ersten kennt, bekommt auf der anderen Maschine ein Schweigen,
    das wie ein Erfolg aussieht.
    """
    for muster in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",
                   str(Path.home() / ".cache/ms-playwright"
                       / "chromium*/chrome-linux*/chrome")):
        treffer = sorted(glob.glob(muster))
        if treffer:
            return treffer[-1]
    return None


@contextmanager
def _server(site: Path):
    """Ein lokaler Server statt file://.

    Dieselbe Lehre wie in `pruefe_portal.py`: unter file:// sperrt die
    Same-Origin-Regel `fetch()`. Bindet auf 127.0.0.1, braucht kein Netz -
    was hier zaehlt, weil Chromium in der Sandbox nicht ins Netz kommt.
    """
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


def _rendern(ziel: Path) -> Path:
    """Frisch rendern - MIT cfg.

    `render_site()` ohne den dritten Parameter rendert stillschweigend eine
    halbe Seite (CLAUDE.md §6). Hier wird deshalb geladen, was `pipeline.py`
    auch laedt.
    """
    from telco_radar.config import load_config
    from telco_radar.report.html import render_site
    render_site(ziel, REPO / "data" / "reports", load_config(REPO))
    return ziel


# Gemessen wird je FLAECHE, und die Geometrie kommt aus ihren
# data-Attributen. Der erste Anlauf las sie aus dem Modul nach - und zwar aus
# den CHIP-Flaechen, waehrend er die Punkte BEIDER Formen einsammelte. Weil
# die Bandform einen anderen unteren Rand hat (148 statt 70), haette das
# ~20 % Abweichung gemeldet, die es nicht gibt, sobald ein Bandpunkt ein
# Etikett traegt. Dieselbe Lehre wie bei `pruefe_portal.py`: die Zahl gehoert
# dorthin, wo sie entsteht.
# Die Etikettengegenprobe ist am 30.08.2026 entfallen, mit der Grafik, die
# sie vermass: sie rechnete aus jeder Etikettenhoehe den Preis zurueck und
# hielt ihn gegen `data-preis`. Die Positionskarte ist geloescht - es gibt
# keine `.gr-punkt` mehr, aus deren Geometrie sich etwas zurueckrechnen
# liesse, und der Import von `geraete_karte` warf hier zuletzt einen
# ImportError, den nur niemand sah, weil die Messung vorher leer zurueckkam.
#
# Was an ihre Stelle tritt, misst dieselbe Sorte Fehler an der neuen Seite:
# `tests/test_geraete_reiter_browser.py` prueft im echten Chromium, dass kein
# gedrehter Text, keine Schrift unter 12 px und keine mit "..." gekuerzte
# Beschriftung dasteht. Dieses Skript bleibt, wofuer es sonst da ist -
# fotografieren, damit ein Mensch hinsieht.


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", type=Path,
                    help="fertiges site/-Verzeichnis; ohne das wird gerendert")
    ap.add_argument("--seite", default="geraete.html")
    ap.add_argument("--ausschnitt", default="",
                    help="CSS-Auswahl, die zusaetzlich einzeln fotografiert wird")
    ap.add_argument("--ziel", type=Path,
                    default=Path("/tmp/telco-screenshots"))
    ap.add_argument("--marke", default="",
                    help="Namenszusatz, um zwei Staende zu vergleichen")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright fehlt: pip install -r requirements.txt")
        return 2

    site = args.site
    tmp = None
    if site is None:
        import tempfile
        tmp = tempfile.TemporaryDirectory()
        site = _rendern(Path(tmp.name) / "site")
    if not (site / args.seite).exists():
        print(f"{site / args.seite} gibt es nicht")
        return 2

    args.ziel.mkdir(parents=True, exist_ok=True)
    zusatz = f"-{args.marke}" if args.marke else ""
    stamm = args.seite.replace(".html", "")
    pfad = _chromium()
    fehler: list[str] = []
    geschrieben: list[Path] = []

    with _server(site) as wurzel, sync_playwright() as p:
        browser = p.chromium.launch(
            **({"executable_path": pfad} if pfad else {}),
            args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            for name, breite, hoehe in FORMATE:
                seite = browser.new_page(
                    viewport={"width": breite, "height": hoehe})
                seite.goto(f"{wurzel}/{args.seite}", wait_until="networkidle")
                # Ohne das Durchscrollen bleiben lazy geladene Bilder leer -
                # dieselbe Vorsichtsmassnahme wie in pruefe_portal.py.
                seite.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                seite.wait_for_timeout(400)
                seite.evaluate("window.scrollTo(0, 0)")
                seite.wait_for_timeout(200)

                ganz = args.ziel / f"{stamm}{zusatz}-{name}.png"
                seite.screenshot(path=str(ganz), full_page=True)
                geschrieben.append(ganz)

                if args.ausschnitt:
                    el = seite.query_selector(args.ausschnitt)
                    if el:
                        aus = args.ziel / f"{stamm}{zusatz}-{name}-ausschnitt.png"
                        el.screenshot(path=str(aus))
                        geschrieben.append(aus)
                    else:
                        fehler.append(f"{name}: '{args.ausschnitt}' gibt es nicht")

                seite.close()
        finally:
            browser.close()

    for f in geschrieben:
        print(f"  {f}")
    if tmp is not None:
        tmp.cleanup()
    if fehler:
        print(f"\n{len(fehler)} Beanstandungen")
        return 1
    print("\nkeine Beanstandungen")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
