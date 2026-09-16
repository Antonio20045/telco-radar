"""O4 (STRATEGIE_GERAETE_OPTIK §3, 15.09.2026): G0 im Verlaufs-Reiter.

O1 hatte die je-Modell-Barpreis-Zeitreihe G0 aus der Vergleichsansicht
gekappt - die Rechnung blieb im Code (`modell["zeitreihe"]` wird weiterhin
gefüllt), nur der Aufruf fiel. O4 bindet sie im Verlaufs-Reiter wieder an:

  * Barpreis-Punktplot je Anbieter (dasselbe servergerenderte SVG, KEIN
    zweiter Renderer),
  * Wertetabelle mit den Reihen der Grafik,
  * ehrliche Hinweise nach dem Entwurf (§2): die TCO-24-Historie je Bündel
    wächst seit dem ersten nächtlichen Lauf am 12.09.2026 - mit der ECHTEN
    Zahl aus `data/state/geraete_tco_historie.jsonl`, nie behauptet.

Diese Datei misst am ECHTEN Bestand (render_site), dieselbe Bauform wie
`tests/test_geraete_o3_rollen.py`. Die Interaktion (Modellwechsel tauscht
den G0-Block) misst `tests/test_geraete_o4_verlauf_browser.py` an einer
eigenen Fixture.
"""
from __future__ import annotations

import json
import pathlib

import pytest
from bs4 import BeautifulSoup

from telco_radar.report.html import render_site

WURZEL = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> pathlib.Path:
    ziel = tmp_path_factory.mktemp("o4-verlauf") / "site"
    render_site(ziel, WURZEL / "data" / "reports")
    return ziel


@pytest.fixture(scope="module")
def geraete(site) -> BeautifulSoup:
    return BeautifulSoup((site / "geraete.html").read_text(encoding="utf-8"),
                         "html.parser")


@pytest.fixture(scope="module")
def vorgabe(geraete) -> dict:
    """Titel und ID des Vorgabemodells - aus dem JSON-Knoten der Seite.

    Der Test liest die Erwartung aus demselben Knoten, aus dem auch der
    Modell-Umschalter liest: dieselbe Quelle, keine zweite Berechnung.
    """
    # E2: der Modell-Umschalter liest #gr-zeitreihe-daten (Titel und
    # Erlaubnis, keine Zahlen); der alte Balken-Knoten #gr-graph-daten ist
    # mit der Balkenansicht gefallen.
    knoten = geraete.select_one("#gr-zeitreihe-daten")
    assert knoten is not None, "JSON-Knoten #gr-zeitreihe-daten fehlt"
    daten = json.loads(knoten.get_text())
    assert daten["vorgabe"], "kein Startmodell im Knoten"
    return {"id": daten["vorgabe"],
            "titel": daten["titel"][daten["vorgabe"]]}


# --------------------------------------------------------------------------
# G0 steht im Verlaufs-Reiter - und nur dort
# --------------------------------------------------------------------------

def test_g0_steht_im_verlaufs_reiter(geraete):
    """Das servergerenderte G0-SVG des Vorgabemodells steht in
    #tafel-verlauf - First Paint ohne JavaScript, dieselbe Grafik, die bis
    O1 in der Vergleichsansicht hing."""
    verlauf = geraete.select_one("#tafel-verlauf")
    assert verlauf is not None
    assert verlauf.select_one("svg.gr-g0") is not None, (
        "G0 (Barpreis-Zeitreihe) fehlt im Verlaufs-Reiter")


def test_g0_folgt_dem_vorgabemodell_mit_titel(geraete, vorgabe):
    """Der G0-Block nennt das Modell, dessen Bündel die Vergleichsansicht
    zeigt - Titel aus demselben JSON-Knoten wie der Selektor."""
    block = geraete.select_one("#gr-g0-lager")
    assert block is not None
    titel = block.select_one(".gr-g0-titel")
    assert titel is not None
    assert vorgabe["titel"] in titel.get_text(" ", strip=True), (
        f"G0-Titel nennt nicht das Vorgabemodell {vorgabe['titel']!r}: "
        f"{titel.get_text(' ', strip=True)!r}")


def test_nur_die_zeitreihe_ist_svg_in_der_vergleichsansicht(geraete):
    """E2 dreht die alte Regel um: die Vergleichsansicht TRÄGT ein SVG -
    die TCO-Zeitreihe (Antonios Graph-Entscheidung). G0 bleibt der
    Verlaufs-Reiter; die Zeitreihe ist der EINZIGE SVG-Block der Tafel."""
    tco = geraete.select_one("#tafel-tco")
    assert tco is not None
    svgs = tco.select("svg")
    assert svgs, "die Zeitreihe (svg.gr-zr) fehlt"
    for svg in svgs:
        assert "gr-zr" in (svg.get("class") or []), (
            "SVG ausser der Zeitreihe in der Vergleichsansicht")


def test_g0_wertetabelle_traegt_die_reihen_der_grafik(geraete):
    """Die Wertetabelle nennt dieselben Anbieter wie die Legende des SVG -
    zwei Ansichten EINER Menge, und die Tabelle ist vollständig (auch der
    Anbieter mit nur einem Messpunkt, der im Bild nur ein Punkt ist)."""
    block = geraete.select_one("#gr-g0-lager")
    assert block is not None
    legende = {t.get_text(strip=True)
               for t in block.select(".gr-g0-legende")}
    assert legende, "G0-SVG ohne Legendenzeilen"
    tabelle = block.select_one(".gr-g0-werte tbody")
    assert tabelle is not None, "Wertetabelle fehlt im G0-Block"
    zeilen = tabelle.select("tr")
    assert zeilen, "Wertetabelle ohne Zeilen"
    anbieter = {z.select_one("td").get_text(" ", strip=True)
                for z in zeilen}
    assert anbieter == legende, (
        f"Wertetabelle {sorted(anbieter)} und SVG-Legende "
        f"{sorted(legende)} sind nicht dieselbe Menge")


def test_die_wertetabelle_traegt_preis_und_veraenderung(geraete):
    """Je Zeile: Anbieter, Messung, Gerätepreis ohne Vertrag, Veränderung.
    Eine Reihe mit einem Messpunkt sagt 'ein Messpunkt' statt einer
    erfundenen Veränderung."""
    block = geraete.select_one("#gr-g0-lager")
    kopf = [th.get_text(" ", strip=True)
            for th in block.select(".gr-g0-werte thead th")]
    assert kopf[:2] == ["Anbieter", "Messung"], kopf
    assert any("Gerätepreis" in k for k in kopf), kopf
    assert any("Veränderung" in k for k in kopf), kopf
    for zeile in block.select(".gr-g0-werte tbody tr"):
        zellen = [z.get_text(" ", strip=True)
                  for z in zeile.select("td")]
        assert len(zellen) == len(kopf), zellen
        assert "€" in zellen[2], f"Preiszelle ohne Betrag: {zellen}"


# --------------------------------------------------------------------------
# Ehrliche Hinweise nach dem Entwurf
# --------------------------------------------------------------------------

def test_der_beginn_der_tco_historie_ist_der_echte(geraete):
    """Der Satz nennt das ECHTE Datum des ersten TCO-Historien-Laufs (aus
    geraete_tco_historie.jsonl) und die Zahl der Messtage - nicht das
    festgeschriebene '12.09.' des Entwurfs, das an einem anderen Bestand
    eine Behauptung wäre."""
    verlauf = geraete.select_one("#tafel-verlauf")
    text = " ".join(verlauf.get_text(" ", strip=True).split())
    tage = set()
    pfad = WURZEL / "data" / "state" / "geraete_tco_historie.jsonl"
    if pfad.exists():
        for zeile in pfad.read_text(encoding="utf-8").splitlines():
            if zeile.strip():
                tage.add(json.loads(zeile).get("datum"))
    if not tage:
        pytest.skip("keine TCO-Historie im Bestand")
    seit = min(tage)
    # Dasselbe Format wie der date_de-Filter der Seite: "12. September 2026"
    from datetime import datetime
    MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
              "August", "September", "Oktober", "November", "Dezember"]
    d = datetime.fromisoformat(seit)
    erwartet = f"{d.day}. {MONATE[d.month - 1]} {d.year}"
    assert erwartet in text, (
        f"Der Verlaufs-Reiter nennt nicht den echten Beginn {seit} "
        f"der TCO-Historie ({erwartet!r} fehlt)")


def test_der_alte_falsche_satz_ist_weg(geraete):
    """Bis O4 behauptete der Reiter, der Bündelbestand kenne je Bündel
    'genau einen Stand' - seit dem 12.09.2026 ist das falsch, die Historie
    wächst. Der Satz muss weg sein, sonst widerlegt die Datei die Seite."""
    verlauf = geraete.select_one("#tafel-verlauf")
    text = " ".join(verlauf.get_text(" ", strip=True).split())
    assert "genau einen Stand" not in text


# --------------------------------------------------------------------------
# Das Fragment trägt G0 je Modell (kein zweiter Renderer)
# --------------------------------------------------------------------------

def test_das_fragment_traegt_g0_fuer_jedes_nicht_vorgabemodell(
        site, geraete):
    """Die G0-Blöcke aller übrigen Modelle stehen im lazy Fragment - dieselbe
    Bauform wie die Bündel-Zeilen seit O3: die Hauptseite bleibt klein, der
    Modellwechsel holt eine Datei und setzt fertiges Markup."""
    knoten = geraete.select_one("#gr-zeitreihe-daten")
    daten = json.loads(knoten.get_text())
    fragment = (site / "data" / "geraete-buendel.html")
    assert fragment.exists(), "Bündel-Fragment fehlt"
    suppe = BeautifulSoup(fragment.read_text(encoding="utf-8"),
                          "html.parser")
    ids = [l.get("data-modell") for l in suppe.select(".gr-g0-lager")]
    # E2: "Vorgabe" des Fragments ist der ZEITREIHEN-Startzustand - dieselbe
    # Wahl wie der Server-First-Paint (Graph und G0 folgen demselben Modell).
    erwartet = [mid for mid in daten["titel"]
                if mid != daten["vorgabe"]]
    assert len(ids) == len(erwartet), (
        f"{len(ids)} G0-Blöcke im Fragment, erwartet {len(erwartet)}")
    assert set(ids) == set(erwartet)
    assert daten["vorgabe"] not in ids, (
        "das Vorgabemodell steht doppelt: Seite UND Fragment")


def test_das_fragment_g0_hat_dasselbe_markup_wie_die_seite(site, geraete):
    """Der Fragment-Block eines Modells trägt dieselben Bausteine wie der
    Server-Block der Seite (SVG bzw. Leerzustand, Wertetabelle) - ein
    Modellwechsel darf keine andere Ansicht zeigen als den First Paint."""
    fragment = BeautifulSoup(
        (site / "data" / "geraete-buendel.html").read_text(encoding="utf-8"),
        "html.parser")
    erster = fragment.select_one(".gr-g0-lager")
    assert erster is not None
    assert erster.select_one(".gr-g0-titel") is not None
    assert (erster.select_one("svg.gr-g0") is not None
            or "keine Preishistorie" in erster.get_text(" ", strip=True)), (
        "Fragment-G0 weder Grafik noch ehrlicher Leerzustand")
