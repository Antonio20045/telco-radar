"""Das Liniendiagramm „Preisposition je Hersteller" (Antonio, 12.12.2026).

Eine Linie je Hersteller über die Zeit, plus die Leitlinie „Alle Hersteller".
Geprüft wird die Rechnung (Vergleichstage, Zweistufen-Mittel, Lücke statt
Null), die Stilvergabe und das fertige SVG. Nichts hängt am heutigen Datum.
"""

from __future__ import annotations

import pytest

from telco_radar.report import anbieter_farben as af
from telco_radar.report import geraete_hersteller_grafik as gr

TAGE = ("2026-10-30", "2026-10-31", "2026-11-01")


def _rechnung(pct: dict, hersteller: list[str]) -> dict:
    """Eine Rechnung in der Form, die `geraete_hersteller.berechne` liefert."""
    return {
        "stand": TAGE[-1],
        "modelle": [{"id": f"m{i}", "hersteller": h} for i, h in enumerate(hersteller)],
        "ohne": [],
        "tage": list(pct),
        "pct": pct,
    }


def _voll(wert: float, n: int = 3) -> list:
    """`n` Modelle, zwei Wettbewerber, überall derselbe Abstand."""
    return [[wert, wert] for _ in range(n)]


def test_ein_tag_ohne_vollen_wettbewerb_ist_kein_vergleichstag():
    """Der Fehler vom 08./10./12.11.2026: fehlt ein Wettbewerber, springt das
    Mittel - der Tag wird nicht gezeichnet, statt eine Bewegung zu behaupten."""
    pct = {
        TAGE[0]: [[5.0, 5.0], [5.0, 5.0], [5.0, 5.0]],
        TAGE[1]: [[5.0, None], [5.0, None], [5.0, None]],
        TAGE[2]: [[5.0, 5.0], [5.0, 5.0], [None, None]],
    }
    r = _rechnung(pct, ["Apple"] * 3)
    assert gr.vergleichstage(r, [0, 1]) == [TAGE[0]]
    assert gr.vergleichstage(r, [0]) == [TAGE[0], TAGE[1]]
    assert gr.vergleichstage(r, [0, 1], mindest=2) == [TAGE[0], TAGE[2]]


def test_ohne_gezeigten_wettbewerber_gibt_es_keinen_vergleichstag():
    r = _rechnung({TAGE[0]: _voll(5.0)}, ["Apple"] * 3)
    assert gr.vergleichstage(r, []) == []


def test_mindestschwelle_ist_die_benannte_konstante():
    from telco_radar.report.geraete_hersteller_text import KLEIN

    assert gr.MINDEST_MODELLE == KLEIN


def test_tageswert_mittelt_erst_je_wettbewerber_dann_ueber_die_wettbewerber():
    """Ein Wettbewerber mit vielen gemessenen Modellen darf die Linie nicht
    schwerer wiegen als einer mit wenigen."""
    pct = {TAGE[0]: [[10.0, 30.0], [20.0, None], [30.0, None]]}
    r = _rechnung(pct, ["Apple"] * 3)
    wert, n = gr.tageswert(r, TAGE[0], None, [0, 1])
    spalte_0 = (10.0 + 20.0 + 30.0) / 3
    spalte_1 = 30.0
    assert wert == pytest.approx((spalte_0 + spalte_1) / 2)
    assert n == 4


def test_tageswert_je_hersteller_zaehlt_nur_dessen_modelle():
    pct = {TAGE[0]: [[10.0, 10.0], [40.0, 40.0]]}
    r = _rechnung(pct, ["Apple", "Samsung"])
    assert gr.tageswert(r, TAGE[0], "Apple", [0, 1])[0] == pytest.approx(10.0)
    assert gr.tageswert(r, TAGE[0], "Samsung", [0, 1])[0] == pytest.approx(40.0)
    assert gr.tageswert(r, TAGE[0], None, [0, 1])[0] == pytest.approx(25.0)


def test_ohne_jeden_wert_bleibt_es_none_und_wird_nie_null():
    pct = {TAGE[0]: [[None, None]]}
    r = _rechnung(pct, ["Apple"])
    assert gr.tageswert(r, TAGE[0], None, [0, 1]) == (None, 0)


def test_reihe_ueberspringt_tage_ohne_wert_statt_eine_null_zu_zeichnen():
    pct = {
        TAGE[0]: [[10.0, 10.0]],
        TAGE[1]: [[None, None]],
        TAGE[2]: [[20.0, 20.0]],
    }
    r = _rechnung(pct, ["Apple"])
    reihen = gr.reihen(r, [0, 1], list(TAGE), ["Apple"])
    apple = next(x for x in reihen if x["hersteller"] == "Apple")
    assert [p["tag"] for p in apple["punkte"]] == [TAGE[0], TAGE[2]]
    assert [p["wert"] for p in apple["punkte"]] == [10.0, 20.0]


def test_hersteller_ohne_einen_einzigen_punkt_steht_nicht_in_der_legende():
    pct = {TAGE[0]: [[10.0, 10.0], [None, None]]}
    r = _rechnung(pct, ["Apple", "Samsung"])
    namen = [x["name"] for x in gr.reihen(r, [0, 1], [TAGE[0]], ["Apple", "Samsung"])]
    assert namen == ["Apple", gr.GESAMT_NAME]


def test_die_leitlinie_heisst_alle_hersteller_und_traegt_vodafone_rot():
    pct = {TAGE[0]: [[10.0, 10.0]]}
    r = _rechnung(pct, ["Apple"])
    gesamt = gr.reihen(r, [0, 1], [TAGE[0]], ["Apple"])[-1]
    assert gesamt["gesamt"] and gesamt["name"] == gr.GESAMT_NAME
    assert gesamt["farbe"] == af.VODAFONE_ROT
    assert gesamt["breite"] == af.BREITE_EIGEN


def test_stil_haengt_am_platz_und_wird_nie_geraten(caplog):
    """Mehr Hersteller als Stile: benannte Luecke und ein Protokolleintrag -
    keine Farbe aus einem Hash (CLAUDE.md Clean Code 3)."""
    erste = [af.hersteller_stil(i) for i in range(len(af.HERSTELLER_STILE))]
    assert len({s.farbe for s in erste}) == len(erste)
    assert len({s.marker for s in erste}) == len(erste)
    with caplog.at_level("WARNING"):
        zuviel = af.hersteller_stil(len(af.HERSTELLER_STILE))
    assert zuviel is af.LUECKE
    assert "ohne hinterlegten Stil" in caplog.text


def test_stile_nennt_jede_moegliche_reihe_fuer_den_browser():
    stile = gr.stile(["Apple", "Samsung"])
    assert [s["name"] for s in stile] == ["Apple", "Samsung", gr.GESAMT_NAME]
    assert [s["hersteller"] for s in stile] == ["Apple", "Samsung", ""]
    assert stile[-1]["gesamt"] and not stile[0]["gesamt"]


def _svg(wert: float = 12.0, tage: tuple[str, ...] = TAGE) -> str:
    pct = {t: [[wert, wert]] for t in tage}
    r = _rechnung(pct, ["Apple"])
    reihen = gr.reihen(r, [0, 1], list(tage), ["Apple"])
    return gr.svg(reihen, list(tage), True, gr.achsentitel(24))


def test_svg_zeichnet_nulllinie_titel_und_endwert():
    bild = _svg()
    assert "gr-hl-null" in bild
    assert "Gesamtkosten 24" in bild and "gr-hl-titel" in bild
    assert "gr-hl-ende" in bild and ">+12" in bild
    assert "rotate" not in bild


def test_svg_zeigt_die_null_auch_wenn_alle_werte_darueber_liegen():
    """Ohne die Null im Bild sieht ein Abstand von +30 % aus wie jeder andere."""
    y0, y1 = gr._spanne([{"punkte": [{"wert": 30.0}, {"wert": 32.0}]}])
    assert y0 < 0 < y1


def test_ohne_reihen_oder_tage_entsteht_kein_leeres_bild():
    assert gr.svg([], TAGE) == ""
    assert gr.svg([{"punkte": [], "gesamt": False}], []) == ""


def test_schmaler_titel_ist_kuerzer_als_der_breite():
    """Auf 358 px lief die lange Beschriftung rechts aus dem Bild."""
    assert len(gr.achsentitel(24, kurz=True)) < len(gr.achsentitel(24))
    assert "24" in gr.achsentitel(24, kurz=True)


def test_geometrie_ist_die_eine_quelle_der_masse():
    g = gr.geometrie()
    assert g["breit"] == [gr.BREIT_W, gr.BREIT_H]
    assert g["schmal"] == [gr.SCHMAL_W, gr.SCHMAL_H]
    assert g["r"] == gr.PUNKT_R
