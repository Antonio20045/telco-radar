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

ZWEI AUSGABEN, und die zweite ist die wichtigere:

1. PNGs je Format (1440x900 und 390x844), einmal die ganze Seite und einmal
   der genannte Ausschnitt. Die sieht ein Mensch an.
2. `--pruefe-etiketten`: die Gegenprobe, die kein Mensch zuverlaessig macht.
   Aus der gerenderten Etikettenhoehe wird der Preis ZURUECKGERECHNET und
   gegen `data-preis` gehalten. Das ist genau die Messung, an der die alte
   Grafik gescheitert waere - und sie kostet keine Sekunde Aufmerksamkeit.

Ohne `--site` wird frisch nach einem temporaeren Ordner gerendert; `site/` im
Repo wird nie angefasst.

    python scripts/schiess_screenshot.py --seite geraete.html \\
        --ausschnitt '#positionskarte' --pruefe-etiketten
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

# Toleranz der Rueckrechnung. Der Auftrag nennt drei Prozent; mehr ist keine
# Rundung mehr, sondern eine andere Aussage.
TOLERANZ_PROZENT = 3.0


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
_MESSUNG_JS = """
() => {
  const raus = [];
  for (const f of document.querySelectorAll('.gr-flaeche')) {
    const geo = {
      achse: parseFloat(f.dataset.achse),
      plot_h: parseFloat(f.dataset.plotH),
      y_max: parseFloat(f.dataset.ymax),
      form: f.dataset.form || '',
      ansicht: (f.closest('.gr-ansicht') || {dataset: {}}).dataset.ansicht || '',
    };
    for (const g of f.querySelectorAll('.gr-punkt')) {
      const text = g.querySelector('.gr-etikett');
      raus.push({
        ...geo,
        modell: g.dataset.modell || '',
        preis: parseFloat(g.dataset.preis || 'NaN'),
        label_y: text ? parseFloat(text.getAttribute('y')) : null,
        label: text ? text.textContent.trim() : '',
      });
    }
  }
  return raus;
}
"""


def _pruefe_etiketten(punkte: list) -> list[str]:
    """Aus der Etikettenhoehe den Preis zurueckrechnen.

    Gerechnet wird mit `geraete_karte.preis_aus_hoehe` und
    `geraete_karte.toleranz` - denselben Funktionen, die auch
    `scripts/pruefe_portal.py` und die Tests benutzen. Eine eigene Fassung
    hier waere eine zweite Meinung darueber, wo die Nulllinie liegt, und
    beide waeren fuer sich gruen.

    Ein Punkt OHNE Etikett wird uebersprungen - das ist der erlaubte Ausweg
    der Regel (passt es nicht in 12 px, wird es weggelassen), und ihn als
    Fehler zu zaehlen hiesse, genau die Loesung zu bestrafen.
    """
    from telco_radar.report import geraete_karte

    fehler = []
    for p in punkte:
        if p.get("label_y") is None or not p.get("preis"):
            continue
        if not p.get("plot_h") or not p.get("y_max"):
            continue
        gelesen = geraete_karte.preis_aus_hoehe(
            p["label_y"], p["y_max"], p["achse"], p["plot_h"])
        echt = p["preis"]
        if abs(gelesen - echt) > geraete_karte.toleranz(
                echt, p["y_max"], p["plot_h"]):
            fehler.append(
                f"{p['ansicht']}/{p['form']}: {p['label'] or p['modell']} steht "
                f"auf Hoehe {gelesen:.0f} EUR, kostet aber {echt:.2f} EUR")
    return fehler


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
    ap.add_argument("--pruefe-etiketten", action="store_true",
                    help="Preis aus der Etikettenhoehe zurueckrechnen")
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

                if args.pruefe_etiketten and name == "schreibtisch":
                    punkte = seite.evaluate(_MESSUNG_JS)
                    if not punkte:
                        print("  keine Punkte gefunden - Grafik leer?")
                    else:
                        mit = [p for p in punkte if p.get("label_y") is not None]
                        schlecht = _pruefe_etiketten(punkte)
                        formen = sorted({p["form"] for p in punkte})
                        print(f"  Etikettenprobe: {len(punkte)} Punkte in "
                              f"{len(formen)} Formen ({', '.join(formen)}), "
                              f"{len(mit)} mit Etikett, "
                              f"{len(schlecht)} weiter als "
                              f"{TOLERANZ_PROZENT:.0f} % daneben")
                        for zeile in schlecht[:8]:
                            print(f"    ! {zeile}")
                        fehler.extend(schlecht)
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
