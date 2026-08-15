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
import glob
import http.server
import json
import shutil
import socket
import threading
from pathlib import Path

import pytest

from telco_radar.report import uebersetzung_view as uv
from telco_radar.report.html import render_site
from telco_radar.uebersetzung.store import (
    UebersetzungsStore, Uebersetzung, text_hash)

REPO = Path(__file__).resolve().parents[1]

# Eine Zeile Text bei 11.5 px in der Grotesk. Zwei Zeilen waeren rund 28 px -
# die Grenze liegt bewusst dazwischen und nicht auf einem exakten Wert: die
# echte Schrift laedt in der Sandbox nicht, gemessen wird also die
# Ruecklaufschrift, und eine Kalibrierung auf eine Schrift ist eine Wette
# (siehe CLAUDE.md zum Zeitungskopf).
HOECHSTHOEHE = 22


def _chromium() -> str | None:
    """Beide Orte - Sandbox-Image und GitHub-Runner. Siehe
    tests/test_falz_browser.py: nur den ersten zu kennen heisst, dass der
    Test auf der Maschine schweigt, die Merges absichert."""
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


def _baue(tmp_path: Path) -> Path:
    """Die jüngste echte Ausgabe, und JEDE Meldung bekommt eine Uebersetzung.

    Alle Gewichtungen auf einmal: nur so ist zu messen, ob der Link an der
    Zeile anders sitzt als an der Aufmacher-Karte - und genau darin lag der
    Fehler.
    """
    berichte = sorted((REPO / "data" / "reports").glob("*.json"))
    if not berichte:
        pytest.skip("keine Berichte im Repo")
    daten = json.loads(berichte[-1].read_text(encoding="utf-8"))
    urls = [h["url"] for region in (daten.get("regions") or {}).values()
            for h in (region.get("highlights") or []) if h.get("url")]
    if not urls:
        pytest.skip("keine Meldung mit URL")

    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True)
    for endung in (".json", ".md"):
        auch = berichte[-1].with_suffix(endung)
        if auch.exists():
            shutil.copy(auch, reports / auch.name)
    zustand = tmp_path / "data" / "state"
    zustand.mkdir(parents=True)
    store = UebersetzungsStore(zustand / "uebersetzungen.jsonl")
    for u in urls:
        store.add(Uebersetzung(
            item_id=uv.id_fuer_url(u), quell_hash=text_hash(u),
            titel_de="Deutsche Fassung", absaetze=["Ein Absatz."],
            sprache="pl", url=u, quelle="Quelle", erstellt_am="2026-08-15",
            herkunft="artikel"))
    store.speichern()
    # Die Bilder der echten Ausgabe: ohne sie waeren die Karten anders hoch,
    # und die mittlere Gewichtung entstuende gar nicht.
    bilder = REPO / "site" / "images"
    if bilder.exists():
        (tmp_path / "site").mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            (tmp_path / "site" / "images").symlink_to(bilder)
    site = tmp_path / "site"
    render_site(site, reports, cfg=None)
    return site


@pytest.fixture(scope="module")
def _links(tmp_path_factory):
    """Ein Browserstart, zwei Seiten, alle Linkmasse."""
    sync_playwright = pytest.importorskip(
        "playwright.sync_api",
        reason="playwright fehlt - Browser-Messung entfaellt").sync_playwright
    pfad = _chromium()
    site = _baue(tmp_path_factory.mktemp("ueblink"))

    messung: dict[str, list[dict]] = {}
    with _server(site) as wurzel, sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                **({"executable_path": pfad} if pfad else {}))
        except Exception as exc:                       # noqa: BLE001
            pytest.skip(f"Chromium startet nicht ({str(exc)[:80]})")
        try:
            for seite_name in ("index.html", "meldungen.html"):
                seite = browser.new_page(
                    viewport={"width": 1440, "height": 900})
                seite.goto(f"{wurzel}/{seite_name}", wait_until="load")
                # Die Ressortbloecke sind <details> und liefern zugeklappt
                # keine Masse.
                seite.evaluate(
                    "document.querySelectorAll('details')"
                    ".forEach(d=>d.open=true)")
                seite.wait_for_timeout(400)
                messung[seite_name] = seite.evaluate("""(() => {
                    const raus = [];
                    document.querySelectorAll('.ueb-link').forEach(p => {
                        const a = p.querySelector('a');
                        if (!a) return;
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
                seite.close()
        finally:
            browser.close()
    return messung


def test_der_link_steht_ueberhaupt_auf_beiden_seiten(_links):
    """Die Gegenprobe: ohne Treffer messen die Tests darunter nichts."""
    assert _links["meldungen.html"], "kein roter Link auf meldungen.html"
    assert _links["index.html"], "kein roter Link auf der Titelseite"


def test_der_link_bleibt_an_jeder_gewichtung_einzeilig(_links):
    """Der Fehler vom 15.08.2026: 38 px auf der Aufmacher-Karte."""
    zu_hoch = [l for seite in _links.values() for l in seite
               if l["hoehe"] > HOECHSTHOEHE]
    assert not zu_hoch, (
        f"{len(zu_hoch)} rote Links brechen um - der Pfeil steht auf einer "
        f"eigenen Zeile: {zu_hoch[:3]}")


def test_der_link_ist_so_breit_wie_sein_text_nicht_wie_die_karte(_links):
    """Ein Flex-Kind streckt sich auf die Kartenbreite, und mit ihm die
    Unterstreichung - quer durch die ganze Karte statt unter dem Wort."""
    gestreckt = [l for seite in _links.values() for l in seite
                 if l["breite"] >= l["eltern_breite"]
                 and l["eltern_breite"] > 260]
    assert not gestreckt, (
        f"{len(gestreckt)} rote Links sind so breit wie ihre Karte: "
        f"{gestreckt[:3]}")


def test_der_link_passt_in_die_schmalste_karte(_links):
    """Die eigentliche Masszahl dieser Datei.

    Die vier kleinen Karten der dritten Reihe sind 170 px breit - die
    schmalste Stelle, an der der Link vorkommt. "Vollständige Übersetzung
    lesen" brauchte 195 px und stand dort zweizeilig; deshalb heisst die
    Beschriftung "Übersetzung lesen". Wer sie verlaengert, sieht es hier.

    Verglichen wird gegen die KARTE und nicht gegen einen festen Wert: die
    echte Schrift laedt in der Sandbox nicht, ein Pixelmass waere eine Wette
    auf die Ruecklaufschrift (CLAUDE.md, Zeitungskopf).
    """
    alle = [l for seite in _links.values() for l in seite]
    schmalste = min(l["eltern_breite"] for l in alle)
    assert schmalste < 260, (
        "die schmalste Karte ist breiter als erwartet - dieser Test misst "
        f"dann nicht mehr den engen Fall ({schmalste} px)")
    zu_breit = [l for l in alle if l["breite"] > l["eltern_breite"]]
    assert not zu_breit, f"der Link laeuft aus seiner Karte: {zu_breit[:3]}"


def test_der_link_ist_rot_und_kein_flex_kind(_links):
    alle = [l for seite in _links.values() for l in seite]
    assert {l["display"] for l in alle} == {"inline"}
    assert {l["farbe"] for l in alle} == {"rgb(230, 0, 0)"}


def test_die_beschriftung_ist_an_beiden_orten_dieselbe():
    """Der rote Link entsteht ZWEIMAL: als Jinja-Makro fuer die gerenderten
    Seiten und in `app.js` fuer den Explorer der Archivwochen, der seine
    Meldungen im Browser baut. Zwei Umsetzungen derselben Sache laufen
    auseinander - dann heisst der Link auf der Meldungsseite anders als im
    Archiv, und beide sind fuer sich gruen.
    """
    vorlagen = REPO / "src" / "telco_radar" / "report" / "templates"
    makro = (vorlagen / "_uebersetzung.html.j2").read_text(encoding="utf-8")
    js = (vorlagen / "app.js").read_text(encoding="utf-8")
    # Die Beschriftung aus dem Makro herausziehen, nicht hier wiederholen:
    # eine dritte Kopie im Test waere derselbe Fehler noch einmal.
    zeile = [z for z in makro.splitlines()
             if 'class="ueb-link"' in z and "{{" in z]
    assert len(zeile) == 1, "das Makro traegt nicht genau eine Linkzeile"
    text = zeile[0].split("</a>")[0].rsplit(">", 1)[1]
    assert text.strip(), "die Beschriftung liess sich nicht auslesen"
    assert f'>{text}</a>' in js, (
        f"app.js beschriftet den Link anders als das Makro ({text!r})")
