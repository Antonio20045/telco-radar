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
import shutil
import socket
import threading
from pathlib import Path

import pytest

from telco_radar.config import load_config
from telco_radar.promo_config import PromoSource
from telco_radar.report.html import _env, render_site
from telco_radar.report.promo import prepare_promo_view

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


# --------------------------------------------------------------------------
# Leere Rasterzellen bei genau EINER bzw. genau DREI weiteren Karten
# (27.08.2026, live gemessen: PremiumSIM, simplytel je 1 leere Spalte,
# ALDI TALK 1 leere Zelle unten rechts). `report/promo.gewichte()` rechnet
# die Gewichte seitdem gegen die tatsaechliche Kartenzahl - dieser Test
# misst das Ergebnis am echten Raster, nicht nur an den beiden Booleans, mit
# denen Python rechnet.
#
# Kuenstliche Bloecke statt `data/state/promo_db.json`: der reale Bestand
# hat nicht garantiert Marken mit genau diesen Kartenzahlen, und der Test
# darf nicht vom Zufall des naechsten Laufs abhaengen.
# --------------------------------------------------------------------------

_MESSUNG_RASTER = """() => {
  const bloecke = [];
  document.querySelectorAll('.pmarke').forEach(m => {
    const raster = m.querySelector('.promo-karten');
    const r = raster.getBoundingClientRect();
    const karten = [...raster.querySelectorAll(':scope > .pkarte')].map(c => {
      const cr = c.getBoundingClientRect();
      return {gross: c.classList.contains('pkarte--gross'),
              hoch: c.classList.contains('pkarte--hoch'),
              x: Math.round(cr.x), y: Math.round(cr.y),
              w: Math.round(cr.width), h: Math.round(cr.height),
              right: Math.round(cr.right)};
    });
    bloecke.push({marke: m.querySelector('.pmarke-name').innerText.trim(),
                  rand: Math.round(r.right), karten});
  });
  return bloecke;
}"""


def _synth_entry(brand: str, n: int) -> dict:
    """Ein minimaler Angebots-Eintrag ohne Bild - eine Schriftkachel traegt
    dieselbe feste 16:9-Flaeche wie ein Bild (siehe motiv()-Makro), die
    Geometriemessung braucht also keine echte Bilddatei."""
    return {"id": f"{brand}:{n}", "brand": brand,
            "headline": f"{(n + 1) * 10} GB Angebot Nr {n}",
            "description": "", "valid_until": None,
            "url": "https://example.test/aktion", "status": "aktiv",
            "first_seen": "2026-07-01", "last_verified": "2026-08-20"}


@pytest.fixture(scope="module")
def _rasterluecken_bloecke(tmp_path_factory):
    """Zwei kuenstliche Markenbloecke: eine mit genau EINER, eine mit genau
    DREI weiteren Karten - die beiden live gemessenen Bugfaelle vom
    27.08.2026, unabhaengig vom aktuellen Datenbestand nachgebaut."""
    sync_playwright = pytest.importorskip(
        "playwright.sync_api",
        reason="playwright fehlt - Browser-Messung entfaellt").sync_playwright
    pfad = _chromium()

    sources = [PromoSource(name="ZweiKarten", url="https://example.test/",
                           tier=2, kind="static"),
              PromoSource(name="VierKarten", url="https://example.test/",
                         tier=2, kind="static")]
    entries = ([_synth_entry("ZweiKarten", i) for i in range(2)]
              + [_synth_entry("VierKarten", i) for i in range(4)])
    view = prepare_promo_view(entries, sources, "2026-08-20")

    site = tmp_path_factory.mktemp("promoraster_synth") / "site"
    site.mkdir(parents=True)
    templates_dir = REPO / "src" / "telco_radar" / "report" / "templates"
    shutil.copyfile(templates_dir / "style.css", site / "style.css")
    shutil.copyfile(templates_dir / "logo.png", site / "logo.png")
    html = _env().get_template("promo_index.html.j2").render(
        prefix="", date_de="20. August 2026", promo_view=view,
        seit={"zeilen": []}, promo_report_html="", promo_report_date="",
        promo_lead="")
    (site / "index.html").write_text(html, encoding="utf-8")

    with _server(site) as wurzel, sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                **({"executable_path": pfad} if pfad else {}))
        except Exception as exc:                       # noqa: BLE001
            pytest.skip(f"Chromium startet nicht ({str(exc)[:80]})")
        try:
            seite = browser.new_page(viewport={"width": 1440, "height": 900})
            seite.goto(f"{wurzel}/index.html", wait_until="networkidle")
            daten = seite.evaluate(_MESSUNG_RASTER)
        finally:
            browser.close()
    if not daten:
        pytest.skip("keine Markenbloecke gerendert")
    return {b["marke"]: b for b in daten}


def _luecke_neben_aufmacherkarte(block: dict) -> str | None:
    """None, wenn keine Rasterzelle neben/unter der Aufmacherkarte leer
    bleibt (oder der Block gar keine Aufmacherkarte hat) - sonst eine
    Fehlermeldung. Jede Zeile, die die Aufmacherkarte ueberdeckt, muss bis
    zum rechten Rasterrand reichen, sonst blieb genau dort eine Zelle frei."""
    lead = next((k for k in block["karten"] if k["gross"]), None)
    if lead is None:
        return None
    zeilen: dict[int, list[dict]] = {}
    for k in block["karten"]:
        if k is lead:
            continue
        if k["y"] < lead["y"] + lead["h"] - 2:
            zeilen.setdefault(k["y"], []).append(k)
    for y, karten_in_zeile in zeilen.items():
        rechts = max(k["right"] for k in karten_in_zeile)
        if rechts < block["rand"] - 4:
            return (f"Zeile bei y={y} erreicht den rechten Rasterrand nicht "
                    f"({rechts} von {block['rand']})")
    return None


def test_zwei_karten_je_block_haben_keine_luecke(_rasterluecken_bloecke):
    """PremiumSIM/simplytel, 27.08.2026: genau EINE weitere Karte neben der
    zweispaltigen Aufmacherkarte liess die vierte Spalte leer. Die
    Aufmacherkarte faellt bei genau einer weiteren Karte jetzt auf die
    normale Breite zurueck - zwei gleich grosse Karten in einer Reihe."""
    block = _rasterluecken_bloecke["ZweiKarten"]
    assert len(block["karten"]) == 2
    assert not any(k["gross"] for k in block["karten"]), (
        "die Aufmacherkarte darf bei genau einer weiteren Karte nicht mehr "
        "breit sein - sonst bleibt die vierte Spalte leer")
    assert _luecke_neben_aufmacherkarte(block) is None


def test_vier_karten_je_block_haben_keine_luecke(_rasterluecken_bloecke):
    """ALDI TALK, 27.08.2026: mit genau DREI weiteren Karten (4 Karten
    insgesamt) blieb die Zelle unten rechts der zweizeiligen Aufmacherkarte
    leer. `_HOCH_AB_WEITEREN` steht seitdem auf vier - die Aufmacherkarte
    bleibt hier einzeilig, und die Zeile wird vollstaendig gefuellt."""
    block = _rasterluecken_bloecke["VierKarten"]
    assert len(block["karten"]) == 4
    lead = next(k for k in block["karten"] if k["gross"])
    assert lead["hoch"] is False, (
        "drei weitere Karten fuellen die 2x2-Flaeche nicht vollstaendig")
    fehler = _luecke_neben_aufmacherkarte(block)
    assert fehler is None, fehler
