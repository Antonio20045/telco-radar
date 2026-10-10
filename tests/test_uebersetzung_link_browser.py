"""Sitzt der rote Link, wie er sitzen soll? Gemessen, nicht gelesen.

Das HTML war die ganze Zeit richtig. Der Fehler stand im Stylesheet, und er
war im Quelltext nicht zu sehen: die Kartenvorlagen wickeln ihre ganze Karte
in einen Link und formen ihn als Flexbox -

    .mlead a,.mzwei a{display:flex;flex-direction:column}
    .mz a{display:flex;gap:13px;padding:11px 0}
    .stueck a{display:flex;flex-direction:column}

Das sind Nachfahren-Selektoren, und der rote Link steht INNERHALB dieser
Karten. Er hat die Regeln also mitgeerbt: Text und Pfeil wurden zu zwei
Flex-Kindern und standen UNTEREINANDER. Gemessen am 15.08.2026 auf der
Aufmacher-Karte von meldungen.html: 38 px hoch statt 14, Breite 663 px statt
195 - der Pfeil, der laut Fussnote im Stylesheet "an das Wort" gehoert, stand
seit der Auslieferung des Feature auf einer eigenen Zeile.

Kein statischer Test haette das gemeldet. Deshalb dieser hier, und deshalb an
einem echten Browser.
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

from telco_radar.report import uebersetzung_view as uv
from telco_radar.report.html import render_site
from telco_radar.uebersetzung.store import Uebersetzung, UebersetzungsStore, text_hash

REPO = Path(__file__).resolve().parents[1]

HOECHSTHOEHE = 22


@contextlib.contextmanager
def _server(site: Path):
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
    """Die Ausgabe 2026-08-08 aus `BILDER_BESTAND` mit Bildern, und JEDE Meldung
    bekommt eine Uebersetzung.

    Alle Gewichtungen auf einmal: nur so ist zu messen, ob der Link an der
    Zeile anders sitzt als an der Aufmacher-Karte - und genau darin lag der
    Fehler.
    """
    bericht = BILDER_BESTAND / "reports" / "2026-08-08.json"
    daten = json.loads(bericht.read_text(encoding="utf-8"))
    urls = [
        h["url"]
        for region in (daten.get("regions") or {}).values()
        for h in (region.get("highlights") or [])
        if h.get("url")
    ]
    assert urls

    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True)
    for endung in (".json", ".md"):
        auch = bericht.with_suffix(endung)
        shutil.copy(auch, reports / auch.name)
    zustand = tmp_path / "data" / "state"
    zustand.mkdir(parents=True)
    store = UebersetzungsStore(zustand / "uebersetzungen.jsonl")
    for u in urls:
        store.add(
            Uebersetzung(
                item_id=uv.id_fuer_url(u),
                quell_hash=text_hash(u),
                titel_de="Deutsche Fassung",
                absaetze=["Ein Absatz."],
                sprache="pl",
                url=u,
                quelle="Quelle",
                erstellt_am="2026-08-15",
                herkunft="artikel",
            )
        )
    store.speichern()
    shutil.copytree(
        BILDER_BESTAND / "state" / "report_images", zustand / "report_images"
    )
    verlinke_neben_data(tmp_path)
    site = tmp_path / "site"
    render_site(site, reports, cfg=None)
    return site


@pytest.fixture(scope="module")
def _site(tmp_path_factory):
    return _baue(tmp_path_factory.mktemp("ueblink"))


@pytest.fixture(scope="module")
def _links(_site, chromium):
    """Ein Browserstart, zwei Seiten in zwei Breiten, alle Linkmasse.

    Die Telefonbreite steht seit dem Redesign vom 09.10.2026 mit drin: die
    170-px-Karten der dritten Reihe gibt es nicht mehr, die engste Stelle
    des Links ist jetzt die Spalte am Telefon. Auf meldungen.html steht der
    Link in der Leseansicht der Meldung, nicht auf der Kachel: gemessen
    wird nach dem Klick auf eine Meldung mit Uebersetzung."""
    site = _site

    messung: dict[str, list[dict]] = {}
    with _server(site) as wurzel:
        for seite_name, breite, hoehe in (
            ("index.html", 1440, 900),
            ("meldungen.html", 1440, 900),
            ("index.html", 390, 844),
            ("meldungen.html", 390, 844),
        ):
            schluessel = seite_name if breite > 400 else f"{seite_name}@{breite}"
            seite = chromium.new_page(viewport={"width": breite, "height": hoehe})
            try:
                seite.goto(f"{wurzel}/{seite_name}", wait_until="load")
                seite.evaluate(
                    "document.querySelectorAll('details').forEach(d=>d.open=true)"
                )
                if seite_name == "meldungen.html":
                    seite.locator(".meldung:has(.ueb-link) [data-panel]").first.click()
                seite.wait_for_timeout(400)
                messung[schluessel] = seite.evaluate("""(() => {
                    const raus = [];
                    document.querySelectorAll('.ueb-link').forEach(p => {
                        const a = p.querySelector('a');
                        if (!a || !p.getClientRects().length) return;
                        const r = a.getBoundingClientRect();
                        const s = getComputedStyle(a);
                        raus.push({
                            karte: (p.closest('article') || {}).className || '',
                            breite: Math.round(r.width),
                            hoehe: Math.round(r.height),
                            eltern_breite: Math.round(
                                p.getBoundingClientRect().width),
                            display: s.display,
                            farbe: s.color});
                    });
                    return raus;})()""")
            finally:
                seite.close()
    return messung


def test_der_link_steht_ueberhaupt_auf_beiden_seiten(_links):
    """Die Gegenprobe: ohne Treffer messen die Tests darunter nichts."""
    assert _links["meldungen.html"], "kein roter Link auf meldungen.html"
    assert _links["index.html"], "kein roter Link auf der Titelseite"


def test_der_link_bleibt_an_jeder_gewichtung_einzeilig(_links):
    """Der Fehler vom 15.08.2026: 38 px auf der Aufmacher-Karte."""
    zu_hoch = [
        lk for seite in _links.values() for lk in seite if lk["hoehe"] > HOECHSTHOEHE
    ]
    assert not zu_hoch, (
        f"{len(zu_hoch)} rote Links brechen um - der Pfeil steht auf einer "
        f"eigenen Zeile: {zu_hoch[:3]}"
    )


def test_der_link_ist_so_breit_wie_sein_text_nicht_wie_die_karte(_links):
    """Ein Flex-Kind streckt sich auf die Kartenbreite, und mit ihm die
    Unterstreichung - quer durch die ganze Karte statt unter dem Wort."""
    gestreckt = [
        lk
        for seite in _links.values()
        for lk in seite
        if lk["breite"] >= lk["eltern_breite"] and lk["eltern_breite"] > 260
    ]
    assert not gestreckt, (
        f"{len(gestreckt)} rote Links sind so breit wie ihre Karte: {gestreckt[:3]}"
    )


def test_der_link_passt_in_die_schmalste_karte(_links):
    """Die eigentliche Masszahl dieser Datei.

    Bis zum Redesign vom 09.10.2026 waren die vier kleinen Karten der
    dritten Reihe 170 px breit - die schmalste Stelle, an der der Link
    vorkam. "Vollständige Übersetzung lesen" brauchte 195 px und stand dort
    zweizeilig; deshalb heisst die Beschriftung "Übersetzung lesen". Heute
    ist die schmalste Stelle die Spalte am Telefon. Wer die Beschriftung
    verlaengert, sieht es hier.

    Verglichen wird gegen die KARTE und nicht gegen einen festen Wert: die
    echte Schrift laedt in der Sandbox nicht, ein Pixelmass waere eine Wette
    auf die Ruecklaufschrift (CLAUDE.md, Zeitungskopf).
    """
    alle = [lk for seite in _links.values() for lk in seite]
    schmalste = min(lk["eltern_breite"] for lk in alle)
    assert schmalste <= 400, (
        "die schmalste Karte ist breiter als erwartet - dieser Test misst "
        f"dann nicht mehr den engen Fall ({schmalste} px)"
    )
    zu_breit = [lk for lk in alle if lk["breite"] > lk["eltern_breite"]]
    assert not zu_breit, f"der Link laeuft aus seiner Karte: {zu_breit[:3]}"


def test_der_link_ist_rot_und_kein_flex_kind(_links):
    alle = [lk for seite in _links.values() for lk in seite]
    assert {lk["display"] for lk in alle} == {"inline"}
    assert {lk["farbe"] for lk in alle} == {"rgb(230, 0, 0)"}


def test_die_beschriftung_ist_an_beiden_orten_dieselbe(_site, chromium):
    """Der rote Link entsteht ZWEIMAL: als Jinja-Makro fuer die gerenderten
    Seiten und in `app.js` fuer den Explorer der Archivwochen, der seine
    Meldungen im Browser baut. Zwei Umsetzungen derselben Sache laufen
    auseinander - dann heisst der Link auf der Meldungsseite anders als im
    Archiv, und beide sind fuer sich gruen. Im Browser wird der Explorer
    bedient und sein Link gegen den serverseitig gerenderten gehalten.
    """
    from bs4 import BeautifulSoup

    vom_server = {
        a.get_text(strip=True)
        for name in ("index.html", "meldungen.html")
        for a in BeautifulSoup(
            (_site / name).read_text(encoding="utf-8"), "html.parser"
        ).select(".ueb-link a")
    }
    assert len(vom_server) == 1, vom_server
    archiv = sorted((_site / "reports").glob("2*.html"))
    assert archiv, "keine Archivwoche gerendert"

    with _server(_site) as wurzel:
        seite = chromium.new_page(viewport={"width": 1440, "height": 900})
        try:
            seite.goto(f"{wurzel}/reports/{archiv[-1].name}", wait_until="load")
            seite.evaluate(
                "document.querySelectorAll('details.evidence')"
                ".forEach(d => d.open = true)"
            )
            zeilen = seite.locator(".ex-row")
            assert zeilen.count() >= 2, "der Explorer zeigt keine Meldungen"
            vom_js = []
            for i in (0, zeilen.count() - 1):
                zeilen.nth(i).click()
                link = seite.locator("#ex-detail .ueb-link a")
                assert link.count() == 1, f"Meldung {i}: kein Link im Explorer"
                ziel = link.evaluate("e => e.href")
                status = seite.evaluate("async u => (await fetch(u)).status", ziel)
                assert status == 200, f"der JS-Link zeigt ins Leere: {ziel}"
                vom_js.append(link.inner_text().strip())
        finally:
            seite.close()
    assert set(vom_js) == vom_server, (
        f"app.js beschriftet den Link {vom_js!r}, die Vorlage {vom_server!r}"
    )
