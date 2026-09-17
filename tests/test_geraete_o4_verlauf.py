"""O4 (STRATEGIE_GERAETE_OPTIK §3, 15.09.2026) → E3-Fix (QA 17.09.2026):
der Verlaufs-Reiter OHNE den G0-Block.

O4 hatte die je-Modell-Barpreis-Zeitreihe G0 (serverseitig für das
Vorgabemodell, per Fragment für jedes andere) im Verlaufs-Reiter
angebunden. Der QA-Lauf vom 17.09. fand darin die Doppel-Darstellung, die
§4.6/§4.8 verbieten: der Reiter trug ZWEI Barpreis-Grafiken desselben
Geräts über dieselbe Zeitachse - den G0-Block oben, gesteuert von der
Modellwahl des VERGLEICHS-Reiters, und die eigene Geräteauswahl unten.
Wählte der Leser im Verlaufs-Reiter ein Gerät, zeigte der obere Block
weiterhin das Gerät des ANDEREN Reiters (gemessen: G0-Titel unverändert
APPLE IPHONE 17 PRO 256 GB, während der große Graph Galaxy S26 zeigte) -
zwei Bilder, dieselbe Frage, widersprüchlicher Zustand.

G0 ist deshalb GEFALLEN. Die Barpreis-Frage des Reiters (E3/S1: „Wie hat
sich der BARPREIS eines Geräts entwickelt?") antwortet die eigene Auswahl
unten - ebenso der mit P2 (17.09.2026, Antonio F4) gefallene feste
Markt-Graph G2, der ihr vorher zur Seite stand. Der
Rechenweg-`modell["zeitreihe"]` im View ist mitgefallen (tote Rechnung
je Modell).

Gemessen wird am ECHTEN Bestand (render_site), dieselbe Bauform wie
`tests/test_geraete_o3_rollen.py`. Die Interaktion (die Auswahl steuert
das EINZIGE Barpreis-Bild) misst `tests/test_geraete_o4_verlauf_browser.py`.
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


# --------------------------------------------------------------------------
# E3-Fix: der Reiter trägt GENAU EIN Barpreis-Bild-System (die eigene
# Auswahl) - kein G0-Block mehr
# --------------------------------------------------------------------------

def test_der_verlaufs_reiter_traegt_keine_zweite_barpreis_grafik(geraete):
    """G0 und die eigene Auswahl unten zeichneten beide den Barpreis
    desselben Geräts über dieselbe Zeitachse (§4.6/§4.8 - keine Doppel-
    Darstellung, keine zweite Graph-Form). Weder der Montagepunkt noch
    ein G0-SVG darf zurückkehren."""
    verlauf = geraete.select_one("#tafel-verlauf")
    assert verlauf is not None
    assert verlauf.select_one("#gr-g0-lager") is None, (
        "der G0-Block steht noch im Verlaufs-Reiter (Doppel-Darstellung "
        "zur eigenen Geräteauswahl desselben Reiters)")
    assert verlauf.select_one("svg.gr-g0") is None


def test_das_fragment_traegt_keine_g0_bloecke_mehr(site):
    """Das lazy Fragment versorgte den Modellwechsel mit G0-Blöcken je
    Modell (ZWEI Lager-Knoten je Modell). Ohne den Block auf der Seite
    wären Fragment-Blöcke toter Ballast, der die Datei aufbläht - sie
    trägt nur die Bündel-Zeilen."""
    fragment = site / "data" / "geraete-buendel.html"
    assert fragment.exists(), "Bündel-Fragment fehlt"
    suppe = BeautifulSoup(fragment.read_text(encoding="utf-8"),
                          "html.parser")
    assert not suppe.select(".gr-g0-lager"), (
        "das Fragment trägt noch G0-Blöcke - niemand setzt sie ein")
    assert suppe.select(".gr-bnd-lager"), (
        "die Bündel-Zeilen fehlen im Fragment (O3-Anbindung gerissen)")


def test_nur_die_zeitreihe_ist_svg_in_der_vergleichsansicht(geraete):
    """E2 dreht die alte Regel um: die Vergleichsansicht TRÄGT ein SVG -
    die TCO-Zeitreihe (Antonios Graph-Entscheidung). Die Zeitreihe ist der
    EINZIGE SVG-Block der Tafel."""
    tco = geraete.select_one("#tafel-tco")
    assert tco is not None
    svgs = tco.select("svg")
    assert svgs, "die Zeitreihe (svg.gr-zr) fehlt"
    for svg in svgs:
        assert "gr-zr" in (svg.get("class") or []), (
            "SVG ausser der Zeitreihe in der Vergleichsansicht")


# --------------------------------------------------------------------------
# Ehrliche Hinweise nach dem Entwurf
# --------------------------------------------------------------------------

def test_der_beginn_der_tco_historie_ist_der_echte(geraete):
    """E3 (S1) hat den TCO-Historie-Absatz dieses Reiters FALLEN lassen:
    Seit E2 ist die TCO-Zeitreihe die Hauptansicht des Vergleichs-Reiters,
    und ihre Messtag-Zeile nennt den echten Beginn selbst - dieselbe
    Ankündigung hier noch einmal wäre die Doppel-Darstellung aus §4.6.
    Der Test hält jetzt die REGEL statt des Wortlauts: Der Verlaufs-Reiter
    stellt die BARPREIS-Frage (Titel) und trägt keinen TCO-Absatz; der
    Beginn der Historie steht in der Zeitreihe, aus derselben Datei."""
    verlauf = geraete.select_one("#tafel-verlauf")
    text = " ".join(verlauf.get_text(" ", strip=True).split())
    tage = set()
    pfad = WURZEL / "data" / "state" / "geraete_tco_historie.jsonl"
    if pfad.exists():
        for zeile in pfad.read_text(encoding="utf-8").splitlines():
            if zeile.strip():
                tage.add(json.loads(zeile).get("datum"))
    # Der Reiter fragt nach dem Barpreis - im Titel (S1) und ohne jeden
    # TCO-Historie-Absatz mehr.
    titel = verlauf.select_one("h2.rubrik")
    assert titel is not None
    assert "Barpreis" in titel.get_text(" ", strip=True), (
        "der Verlaufs-Reiter benennt nicht die Barpreis-Frage (E3/S1)")
    assert "TCO-24-Historie" not in text, (
        "der TCO-Historie-Absatz ist zurückgekehrt (E3/S1: Doppel-"
        "Darstellung zur Zeitreihe des Vergleichs-Reiters)")
    if not tage:
        pytest.skip("keine TCO-Historie im Bestand")
    seit = min(tage)
    # Dasselbe KURZ-Format wie die Messtag-Zeile der Zeitreihe
    # („12.9." - `geraete_zeitreihe._tag_monat`): Der Beginn der Historie
    # steht seit dem Wegfall des Absatzes DORT, nicht mehr hier.
    _y, m, d = seit.split("-")
    erwartet = f"{int(d)}.{int(m)}."
    vergleich = geraete.select_one("#tafel-tco")
    assert vergleich is not None
    assert erwartet in " ".join(
        vergleich.get_text(" ", strip=True).split()), (
        f"Der Vergleichs-Reiter nennt nicht den echten Beginn {seit} "
        f"der TCO-Historie ({erwartet!r} fehlt in der Messtag-Zeile)")


def test_der_alte_falsche_satz_ist_weg(geraete):
    """Bis O4 behauptete der Reiter, der Bündelbestand kenne je Bündel
    'genau einen Stand' - seit dem 12.09.2026 ist das falsch, die Historie
    wächst. Der Satz muss weg sein, sonst widerlegt die Datei die Seite."""
    verlauf = geraete.select_one("#tafel-verlauf")
    text = " ".join(verlauf.get_text(" ", strip=True).split())
    assert "genau einen Stand" not in text
