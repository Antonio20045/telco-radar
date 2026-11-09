"""Kein Querscrollen auf der Startseite: scrollWidth höchstens Fensterbreite.

Befund (Prüfung PR 68, 09.11.2026): index.html lief bei 390 px um 25 px über
(scrollWidth 415), schon vor dem PR. Ursache war kein Layoutfehler der Seite,
sondern Inhalt: der Redaktions-Agent schrieb in zwei Absätze des Wochenberichts
einen Quellenverweis mit falsch geschlossener Klammer, `[Quelle](https://…]`. Der
Markdown-Umsetzer erkennt ihn nicht als Link, die Adresse steht als Fließtext im
Absatz, und eine Adresse hat keine Umbruchstelle: `.szene-text` und `.prose` ließen
sie über den Rand hinausstehen. Dieselben zwei Berichte liegen als Archivseiten
(`reports/<Tag>.html`) noch heute so aus.

Der Test baut die Startseite aus dem Schnappschuss 2026-08-08 und hängt an jeden
langen Absatz des Berichtstextes genau diese Form. Er geht den echten Pfad
(`render_site`, echtes `style.css`, Chromium); ohne die Umbruchregel in
`style.css` steht scrollWidth bei 433 statt 390.
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
from bestand_pfad import BILDER_BESTAND, verlinke_neben_data

from telco_radar.report.html import render_site

AUSGABE = "2026-08-08"
KAPUTTER_LINK = (
    " [Quelle](https://www.telepolis.pl/tech/bezpieczenstwo/"
    "tik-tok-for-you-unia-europejska-komisja-europejska-dsa]"
)
FORMATE = [("Telefon", 390, 844), ("Schreibtisch", 1440, 900)]
SEITEN = ["index.html", f"reports/{AUSGABE}.html"]


@contextlib.contextmanager
def _server(site: Path):
    """Lokaler Server auf 127.0.0.1 statt file:// (kein Netz)."""
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
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True)
    quelle = BILDER_BESTAND / "reports"
    bericht = json.loads((quelle / f"{AUSGABE}.json").read_text("utf-8"))
    zeilen = bericht["briefing_md"].split("\n")
    angehaengt = 0
    for i, zeile in enumerate(zeilen):
        if len(zeile) > 200 and not zeile.startswith(("-", "*", "[")):
            zeilen[i] = zeile + KAPUTTER_LINK
            angehaengt += 1
    assert angehaengt >= 2, (
        "die Fixture trägt keine Absätze mehr, an die sich hängen ließe"
    )
    bericht["briefing_md"] = "\n".join(zeilen)
    (reports / f"{AUSGABE}.json").write_text(
        json.dumps(bericht, ensure_ascii=False), encoding="utf-8"
    )
    shutil.copy(quelle / f"{AUSGABE}.md", reports / f"{AUSGABE}.md")
    shutil.copytree(
        BILDER_BESTAND / "state" / "report_images",
        tmp_path / "data" / "state" / "report_images",
    )
    verlinke_neben_data(tmp_path)
    site = tmp_path / "site"
    render_site(site, reports, cfg=None)
    return site


@pytest.fixture(scope="module")
def _breiten(tmp_path_factory, chromium):
    site = _baue(tmp_path_factory.mktemp("querlauf"))
    werte: dict[tuple[str, int], dict] = {}
    with _server(site) as wurzel:
        for seite_name in SEITEN:
            for _name, breite, hoehe in FORMATE:
                seite = chromium.new_page(viewport={"width": breite, "height": hoehe})
                try:
                    seite.goto(f"{wurzel}/{seite_name}", wait_until="load")
                    seite.wait_for_timeout(300)
                    werte[(seite_name, breite)] = seite.evaluate(
                        """() => ({
                            breit: document.documentElement.scrollWidth,
                            fenster: document.documentElement.clientWidth,
                            koerper: document.body.scrollWidth,
                            kaputt: document.body.innerText.includes('](https://'),
                        })"""
                    )
                finally:
                    seite.close()
    return werte


@pytest.mark.parametrize("seite_name", SEITEN)
@pytest.mark.parametrize("breite", [390, 1440])
def test_die_seite_laeuft_nicht_ueber_den_rand(_breiten, seite_name, breite):
    w = _breiten[(seite_name, breite)]
    assert w["fenster"] == breite
    assert max(w["breit"], w["koerper"]) <= w["fenster"], (
        f"{seite_name} bei {breite} px: scrollWidth {w['breit']} / Körper "
        f"{w['koerper']} über Fensterbreite {w['fenster']}"
    )


def test_die_fixture_traegt_die_adresse_wirklich_als_fliesstext(_breiten):
    """Gegenprobe: ohne die Adresse im Text wäre der Test oben nie rot geworden."""
    assert _breiten[("index.html", 390)]["kaputt"]
