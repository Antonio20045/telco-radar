"""P2/D2: die Zeichenregeln der TCO-Zeitreihen-Kurve (`geraete_zeitreihe.
_svg`) - Stufenlinie, gepunktete Messluecke, Y-Achse mit 4-5 Werten samt
Achsenbruch, Markerform. Getestet wird direkt gegen `_svg()` mit
synthetischen Serien (schnell, ohne die volle Katalog-/Buendel-Fixture) -
dieselbe Bauform wie der Repro fuer den X-Label-Ueberlapp
(`test_geraete_zeitreihe_xtick_browser.py`)."""
from __future__ import annotations

import re
from datetime import date, timedelta

from telco_radar.report import geraete_zeitreihe as gz

_BELEG = {"Vodafone": ("https://example.de/vodafone", "2026-09-20"),
          "Telekom": ("https://example.de/telekom", "2026-09-20")}


def _tage(start_iso: str, n: int, schritt_tage: int = 1) -> list[str]:
    start = date.fromisoformat(start_iso)
    return [(start + timedelta(days=i * schritt_tage)).isoformat()
            for i in range(n)]


# --------------------------------------------------------------------------
# Stufenlinie - der Pfad springt, statt zu gleiten
# --------------------------------------------------------------------------

def test_stufenpfad_springt_statt_zu_gleiten():
    punkte = [(0.0, 100.0, 900.0), (50.0, 60.0, 950.0), (100.0, 60.0, 950.0)]
    pfad = gz._stufenpfad(punkte)
    # eine direkte Gerade waere "M0.0 100.0 L50.0 60.0 L100.0 60.0" - die
    # Stufe fuegt VOR jedem Sprung einen waagerechten Zwischenschritt auf
    # der ALTEN Hoehe ein.
    assert pfad == "M0.0 100.0 L50.0 100.0 L50.0 60.0 L100.0 60.0"


def test_die_linie_im_svg_ist_eine_stufe_kein_direkter_sprung():
    tage = _tage("2026-09-12", 3)
    serien = {"Vodafone": [(tage[0], 900.0), (tage[1], 950.0),
                           (tage[2], 950.0)]}
    svg = gz._svg(serien, True, _BELEG, None)
    pfad = re.search(r"<path class='gr-zr-linie' d='([^']+)'", svg).group(1)
    # eine Stufe hat MEHR "L"-Befehle als Punkte-1 (direkte Linie); bei
    # drei Punkten mit EINEM echten Sprung sind das 3 "L" (waagerecht,
    # senkrecht, waagerecht) statt 2 bei einer Geraden.
    assert pfad.count("L") == 3, pfad


# --------------------------------------------------------------------------
# Messluecke: gepunktet, kein schraeger Durchzug
# --------------------------------------------------------------------------

def test_grosse_luecke_wird_gepunktet_nicht_schraeg_verbunden():
    """Vodafone: 12.9. -> 25.9. (13 Tage, > LUECKE_TAGE_SCHWELLE=10) ->
    eigener gepunkteter Zweipunkt-Lauf; 12.9./13.9./25.9./26.9. insgesamt:
    ein durchgezogener Lauf (12./13.), die Luecke, ein durchgezogener Lauf
    (25./26.)."""
    tage = ["2026-09-12", "2026-09-13", "2026-09-25", "2026-09-26"]
    serien = {"Vodafone": [(t, 900.0 + i * 5) for i, t in enumerate(tage)]}
    svg = gz._svg(serien, True, _BELEG, None)
    pfade = re.findall(r"<path class='([^']+)'", svg)
    linien = [p for p in pfade if p.startswith("gr-zr-linie")]
    assert linien.count("gr-zr-linie") == 2, linien
    assert linien.count("gr-zr-linie gr-zr-linie--luecke") == 1, linien
    luecken_pfad = re.search(
        r"<path class='gr-zr-linie gr-zr-linie--luecke' d='[^']+' "
        r"stroke='[^']+' stroke-dasharray='([^']+)'", svg)
    assert luecken_pfad is not None
    assert luecken_pfad.group(1) == gz.STRICHMUSTER["gepunktet"]


def test_grenzfall_genau_schwelle_tage_bleibt_durchgezogen():
    """E (QA-Fix 24.09.2026): eine Luecke von GENAU
    `LUECKE_TAGE_SCHWELLE` (10) Tagen ist NICHT groesser als die
    Schwelle (`>`, nicht `>=`, siehe `_linien_laeufe`) - der Zug bleibt
    EIN durchgezogener Lauf, keine gepunktete Teilstrecke."""
    assert gz.LUECKE_TAGE_SCHWELLE == 10, (
        "dieser Grenzfalltest nimmt 10 an - die Konstante hat sich "
        f"geaendert ({gz.LUECKE_TAGE_SCHWELLE})")
    tage = ["2026-09-12", "2026-09-22"]  # exakt 10 Tage Abstand
    serien = {"Vodafone": [(t, 900.0 + i * 5) for i, t in enumerate(tage)]}
    svg = gz._svg(serien, True, _BELEG, None)
    pfade = re.findall(r"<path class='([^']+)'", svg)
    linien = [p for p in pfade if p.startswith("gr-zr-linie")]
    assert linien == ["gr-zr-linie"], (
        f"eine 10-Tage-Luecke (== Schwelle) wurde gepunktet: {linien}")


def test_grenzfall_ein_tag_ueber_der_schwelle_wird_gepunktet():
    """E (QA-Fix 24.09.2026): Gegenprobe - EIN Tag mehr (11) ueberschreitet
    die Schwelle und wird zur eigenen, gepunkteten Teilstrecke."""
    tage = ["2026-09-12", "2026-09-23"]  # exakt 11 Tage Abstand
    serien = {"Vodafone": [(t, 900.0 + i * 5) for i, t in enumerate(tage)]}
    svg = gz._svg(serien, True, _BELEG, None)
    pfade = re.findall(r"<path class='([^']+)'", svg)
    linien = [p for p in pfade if p.startswith("gr-zr-linie")]
    assert linien == ["gr-zr-linie gr-zr-linie--luecke"], (
        f"eine 11-Tage-Luecke (> Schwelle) blieb durchgezogen: {linien}")


def test_kleine_luecke_bleibt_durchgezogen():
    """congstar fehlt an EINEM Tag (13.9.) - zwei Tage Abstand (12.->14.)
    liegt WEIT unter der Schwelle und bleibt EIN durchgezogener Lauf."""
    tage = ["2026-09-12", "2026-09-14", "2026-09-15"]
    serien = {"congstar": [(t, 900.0 + i * 3) for i, t in enumerate(tage)]}
    svg = gz._svg(serien, True, _BELEG, None)
    pfade = re.findall(r"<path class='([^']+)'", svg)
    linien = [p for p in pfade if p.startswith("gr-zr-linie")]
    assert linien == ["gr-zr-linie"]


# --------------------------------------------------------------------------
# Y-Achse: 4-5 runde Werte, Achsenbruch bei kleiner Spanne
# --------------------------------------------------------------------------

def test_y_achse_zeigt_vier_bis_fuenf_werte():
    """Vorher (_nice_step((y1-y0)/4) direkt): bei dieser Spanne (752-1248)
    kamen nur DREI Ticks heraus (800/1000/1200, Schritt 200 statt 100)."""
    tage = _tage("2026-09-12", 2)
    serien = {"Vodafone": [(tage[0], 800.0), (tage[1], 1200.0)]}
    svg = gz._svg(serien, True, _BELEG, None)
    werte = re.findall(r"<text class='gr-zr-achse'[^>]*>([^<]*)</text>",
                       svg)
    assert 4 <= len(werte) <= 5, werte


def test_kein_achsenbruch_bei_normaler_spanne():
    tage = _tage("2026-09-12", 2)
    serien = {"Vodafone": [(tage[0], 800.0), (tage[1], 1200.0)]}
    svg = gz._svg(serien, True, _BELEG, None)
    assert "gr-zr-achsenbruch" not in svg


def test_achsenbruch_bei_kleiner_spanne():
    """Spanne 5 EUR auf einem Niveau von 900 EUR: (905-900)/905 < 10%."""
    tage = _tage("2026-09-12", 2)
    serien = {"Vodafone": [(tage[0], 900.0), (tage[1], 905.0)]}
    svg = gz._svg(serien, True, _BELEG, None)
    assert "gr-zr-achsenbruch" in svg


# --------------------------------------------------------------------------
# Markerform: gezeichnet, additiv zum bestehenden Kreis
# --------------------------------------------------------------------------

def test_markerform_wird_fuer_telekom_gezeichnet_kreis_bleibt():
    """Telekom traegt die Form 'quadrat' (anbieter_farben.ANBIETER_FARBE)
    - vorher stand `Anbieterstil.marker` nirgends im gezeichneten SVG."""
    tage = _tage("2026-09-12", 2)
    serien = {"Telekom": [(tage[0], 800.0), (tage[1], 820.0)]}
    svg = gz._svg(serien, True, _BELEG, None)
    assert "gr-zr-form gr-zr-form--quadrat" in svg
    assert "<rect " in svg
    # der Kreis bleibt UNVERAENDERT bestehen (Kreis-Selektoren aus Tests
    # und app.js).
    assert re.search(r"<circle class='gr-zr-punkt", svg)


def test_vodafone_kreis_bekommt_keine_zusatzform():
    """Vodafones Marker IST 'kreis' - der Punkt traegt die Form schon,
    eine zweite waere dieselbe Aussage zweimal (Beruhigungsregel)."""
    tage = _tage("2026-09-12", 2)
    serien = {"Vodafone": [(tage[0], 800.0), (tage[1], 820.0)]}
    svg = gz._svg(serien, True, _BELEG, None)
    assert "gr-zr-form" not in svg
