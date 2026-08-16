"""Steht das Raster der Promo Uebersicht buendig? Gemessen, nicht gelesen.

Am 16.08.2026 sah Antonio die Seite an: "die ganzen Artikel bei der
Promo-Uebersicht, die sind kreuz und quer. Das sieht total bescheuert aus.
Es ist nicht geordnet und kein konsistent einheitliches Layout."

Im HTML war nichts davon zu sehen - jede Karte trug dieselben Felder in
derselben Reihenfolge. Der Fehler lag in der HOEHE des Motivs, und die
entstand erst im Browser:

    Bild im 16:9-Rahmen   156 px
    Werbebanner (>2,2:1)   46 px   (bekam absichtlich keinen Rahmen)
    Schriftkachel      95-179 px   (so hoch wie ihr Text)

In einem Raster, dessen Karten oben buendig beginnen, faengt damit jede
Schlagzeile einer Reihe auf einer anderen Hoehe an. Gemessen an der Ausgabe
vom 15.08.2026 standen die Motivhoehen EINES Markenblocks zwischen 46 und
156 px auseinander.

Deshalb dieser Test, und deshalb an einem echten Browser. Er misst drei
Dinge, die alle drei nur die fertige Seite beantworten kann:

  1. Jedes Motiv einer Karte ist so hoch wie jedes andere seiner Reihe.
  2. Die Schlagzeilen einer Reihe beginnen auf einer Hoehe.
  3. Kein Motiv wird ueber seine Dateibreite hinaus gezeigt (dieselbe
     Zusicherung wie Kriterium 6 von scripts/pruefe_portal.py, hier fuer
     die Promo Uebersicht, deren Karten seit dem 16.08.2026 eine feste
     Bildflaeche haben - und eine feste Flaeche kann skalieren).
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

from telco_radar.config import load_config
from telco_radar.report.html import render_site

REPO = Path(__file__).resolve().parents[1]

# Zwei Karten derselben Reihe duerfen sich um diesen Betrag unterscheiden.
# Nicht null: die Rueckfallschrift der Sandbox und die echte Source Serif 4
# runden Zeilenhoehen verschieden, und eine Kalibrierung auf eine Schrift
# waere eine Wette (CLAUDE.md zum Zeitungskopf). Der Fehler, um den es geht,
# war 110 px gross.
TOLERANZ = 4


def _chromium() -> str | None:
    """Beide Orte - Sandbox-Image und GitHub-Runner. Siehe
    tests/test_falz_browser.py."""
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


_MESSUNG = """() => {
  const bloecke = [];
  document.querySelectorAll('.pmarke').forEach(m => {
    const karten = [...m.querySelectorAll('.pkarte')].map(c => {
      const motiv = c.querySelector('.pk-bild');
      const titel = c.querySelector('.pk-titel');
      const img = c.querySelector('.pk-bild img');
      const r = c.getBoundingClientRect();
      const mr = motiv ? motiv.getBoundingClientRect() : null;
      return {
        gross: c.classList.contains('pkarte--gross'),
        x: Math.round(r.x), y: Math.round(r.y),
        motiv_hoehe: mr ? Math.round(mr.height) : null,
        titel_oben: titel ? Math.round(titel.getBoundingClientRect().y) : null,
        bild: img ? {nat: img.naturalWidth,
                     disp: Math.round(img.getBoundingClientRect().width),
                     src: img.getAttribute('src')} : null,
      };
    });
    bloecke.push({marke: m.querySelector('.pmarke-name').innerText.trim(),
                  karten});
  });
  return bloecke;
}"""


@pytest.fixture(scope="module")
def _bloecke(tmp_path_factory):
    """Ein Browserstart, die echte Promo Uebersicht, alle Kartenmasse."""
    sync_playwright = pytest.importorskip(
        "playwright.sync_api",
        reason="playwright fehlt - Browser-Messung entfaellt").sync_playwright
    if not (REPO / "data" / "state" / "promo_db.json").exists():
        pytest.skip("kein Promo-Bestand im Repo")
    pfad = _chromium()
    site = tmp_path_factory.mktemp("promoraster") / "site"
    # Gegen die WIRKLICHEN Daten und mit `cfg` - ohne den dritten Parameter
    # rendert render_site() eine stillschweigend halbe Seite (CLAUDE.md §6).
    render_site(site, REPO / "data" / "reports", load_config(REPO))
    if not (site / "promo" / "index.html").exists():
        pytest.skip("keine Promo Uebersicht gerendert")

    with _server(site) as wurzel, sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                **({"executable_path": pfad} if pfad else {}))
        except Exception as exc:                       # noqa: BLE001
            pytest.skip(f"Chromium startet nicht ({str(exc)[:80]})")
        try:
            seite = browser.new_page(viewport={"width": 1440, "height": 900})
            seite.goto(f"{wurzel}/promo/index.html", wait_until="networkidle")
            # Ohne Durchscrollen bleiben die `loading="lazy"`-Bilder
            # ungeladen, und `naturalWidth` ist dann 0.
            seite.evaluate(
                "async()=>{for(let y=0;y<document.body.scrollHeight;y+=600)"
                "{window.scrollTo(0,y);await new Promise(r=>setTimeout(r,50));}"
                "window.scrollTo(0,0);}")
            seite.wait_for_timeout(1200)
            daten = seite.evaluate(_MESSUNG)
        finally:
            browser.close()
    if not daten:
        pytest.skip("keine Markenbloecke auf der Seite")
    return daten


def _reihen(karten: list[dict]) -> list[list[dict]]:
    """Karten nach Rasterreihe, an ihrer Oberkante gruppiert. Die grosse
    Aufmacherkarte kann zwei Reihen hoch sein und steht deshalb nur in der
    ersten - sie wird hier nicht mitgemessen, ihr Motiv ist bewusst
    groesser."""
    reihen: dict[int, list[dict]] = {}
    for k in karten:
        if k["gross"]:
            continue
        reihen.setdefault(k["y"], []).append(k)
    return [r for r in reihen.values() if len(r) > 1]


def test_die_motive_einer_reihe_sind_gleich_hoch(_bloecke):
    """Der eigentliche Befund vom 16.08.2026. Gegen den Stand von vorher
    faellt dieser Test an jedem Block, der ein Banner oder eine Schriftkachel
    neben einem Bild zeigt - das waren 12 der 15."""
    schief = []
    for block in _bloecke:
        for reihe in _reihen(block["karten"]):
            hoehen = [k["motiv_hoehe"] for k in reihe
                      if k["motiv_hoehe"] is not None]
            if hoehen and max(hoehen) - min(hoehen) > TOLERANZ:
                schief.append((block["marke"], hoehen))
    assert not schief, f"Motivhoehen einer Reihe laufen auseinander: {schief}"


def test_die_schlagzeilen_einer_reihe_beginnen_auf_einer_hoehe(_bloecke):
    """Die Folge daraus, und das, was man sieht: steht das Motiv der einen
    Karte hoeher als das der anderen, faengt auch ihre Schlagzeile
    woanders an."""
    schief = []
    for block in _bloecke:
        for reihe in _reihen(block["karten"]):
            oben = [k["titel_oben"] for k in reihe if k["titel_oben"] is not None]
            if oben and max(oben) - min(oben) > TOLERANZ:
                schief.append((block["marke"], oben))
    assert not schief, f"Schlagzeilen stehen versetzt: {schief}"


def test_kein_motiv_wird_hochskaliert(_bloecke):
    """Seit die Bildflaeche fest ist, KANN ein Motiv skaliert werden - vorher
    verhinderte das ein `max-width` auf dem Bild. An seine Stelle tritt die
    Regel, dass nur in eine Flaeche darf, wer sie fuellen kann
    (promo.LEAD_MIND_BREITE fuer die grosse, die Mindestbreite des
    Bildholers fuer die kleine). Dieser Test haelt sie."""
    zu_gross = [(b["marke"], k["bild"])
                for b in _bloecke for k in b["karten"]
                if k["bild"] and k["bild"]["nat"]
                and k["bild"]["disp"] > k["bild"]["nat"] + 1]
    assert not zu_gross, f"hochskalierte Motive: {zu_gross}"


def test_jede_karte_traegt_ein_motiv(_bloecke):
    """Bild oder Schriftkachel - die Kachel ist nicht der Notnagel fuer ein
    fehlendes Bild, sondern die zweite gueltige Form einer Karte (08.08.2026,
    Kriterium 8c von scripts/pruefe_portal.py). Ohne diese Zusicherung
    reisst eine Karte ohne Motiv wieder ein Loch in ihre Rasterreihe."""
    ohne = [b["marke"] for b in _bloecke for k in b["karten"]
            if not k["motiv_hoehe"]]
    assert not ohne, f"Karten ohne Motiv: {sorted(set(ohne))}"
