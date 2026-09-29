"""Phase P2, Paket D3: der Zerlegungsbalken der Bündelzeile.

Die Bündelzeile der alten Geräteseite ist mit dem Neuentwurf (29.09.2026,
eine Kosten-Rangliste) gefallen, mit ihr die Seitentests dieser Datei
(zugeklappte Unterscheidbarkeit, Δ-Spalte, Anbieterfarbe, Segmente im
gerenderten Rechenweg). Geblieben sind die Einheitstests von
`geraete_tco_karten.zerlegung_balken`: die Segmentsumme ist die Leitzahl,
und eine Restschuld erzeugt nie ein Phantom- oder Nullsegment.
"""
from __future__ import annotations

import pytest


def test_mutationsprobe_punkt4_erkennt_falsche_segmentsumme():
    """`zerlegung_balken()` MUSS eine Summe liefern, die von `gesamt`
    abweicht, wenn ein Segmentbetrag verfälscht wird - sonst könnte die
    Anzeige unbemerkt von der Leitzahl abweichen."""
    from telco_radar.report.geraete_tco_karten import zerlegung_balken

    bestandteile = [
        {"name": "Tarif über 24 Monate", "betrag": 360.0, "kategorie": "tarif"},
        {"name": "Gerätezuzahlung", "betrag": 1.0, "kategorie": "einmalig"},
        {"name": "Geräteraten über 36 Monate", "betrag": 1098.0,
         "kategorie": "raten"},
        {"name": "Anschlusspreis", "betrag": 0.0, "kategorie": "einmalig"},
    ]
    seg = zerlegung_balken(bestandteile, restbetrag=366.0, gesamt=1459.0)
    assert round(sum(s["betrag"] for s in seg), 2) == pytest.approx(1459.0)
    # MUTATION: ein Segmentbetrag wird verfaelscht - die Summenprobe muss
    # das erkennen.
    kaputt = [dict(s) for s in seg]
    kaputt[0]["betrag"] += 10.0
    assert round(sum(s["betrag"] for s in kaputt), 2) != pytest.approx(1459.0)


def test_review_fix_s3_1_restbetrag_none_erzeugt_keinen_phantom_split():
    """`restbetrag=None` heisst "nicht bestimmbar" (Clean Code 3) - KEIN
    Split, keine erfundene Restschuld von 0,00 €. Gegenprobe: eine ECHTE,
    gemessene Restschuld > 0 splittet weiterhin, und 0,00 € (gemessen,
    "nichts offen") verhaelt sich wie `None` (kein Split), aber aus einem
    ANDEREN, ebenfalls gemessenen Grund."""
    from telco_radar.report.geraete_tco_karten import zerlegung_balken

    bestandteile = [
        {"name": "Tarif über 24 Monate", "betrag": 360.0, "kategorie": "tarif"},
        {"name": "Geräteraten über 30 Monate", "betrag": 1000.0,
         "kategorie": "raten"},
    ]
    seg_none = zerlegung_balken(bestandteile, restbetrag=None, gesamt=1360.0)
    assert not any(s["offen"] for s in seg_none), (
        f"restbetrag=None erzeugt trotzdem ein offenes Segment: {seg_none}")
    assert all(s["kategorie"] != "restschuld" for s in seg_none), (
        f"restbetrag=None erfindet eine Restschuld: {seg_none}")
    assert round(sum(s["betrag"] for s in seg_none), 2) \
        == pytest.approx(1360.0)

    seg_null = zerlegung_balken(bestandteile, restbetrag=0.0, gesamt=1360.0)
    assert not any(s["offen"] for s in seg_null)

    # Gegenprobe: eine echte, gemessene Restschuld > 0 splittet weiterhin.
    seg_echt = zerlegung_balken(bestandteile, restbetrag=200.0, gesamt=1360.0)
    offen = [s for s in seg_echt if s["offen"]]
    assert len(offen) == 1 and offen[0]["betrag"] == pytest.approx(200.0), (
        f"eine echte Restschuld splittet nicht mehr: {seg_echt}")


def test_review_fix_s3_2_nullbetrag_posten_ohne_balkenteil():
    """Ein Posten mit Betrag exakt 0,00 € (eine gemessene "keine
    Zuzahlung"/"kein Anschlusspreis") bekommt keinen eigenen
    Balken-Segment - sonst zeigt `min-width:2px` (D3-CSS-Block) einen
    Phantomstreifen ohne Aussage. Ein echter Betrag bleibt stehen."""
    from telco_radar.report.geraete_tco_karten import zerlegung_balken

    bestandteile = [
        {"name": "Tarif über 24 Monate", "betrag": 360.0, "kategorie": "tarif"},
        {"name": "Gerätezuzahlung", "betrag": 0.0, "kategorie": "einmalig"},
        {"name": "Anschlusspreis", "betrag": 0.0, "kategorie": "einmalig"},
        {"name": "Geräteraten über 24 Monate", "betrag": 1000.0,
         "kategorie": "raten"},
    ]
    seg = zerlegung_balken(bestandteile, restbetrag=0.0, gesamt=1360.0)
    namen = {s["name"] for s in seg}
    assert "Gerätezuzahlung" not in namen and "Anschlusspreis" not in namen, (
        f"ein 0,00-€-Posten hat trotzdem ein Segment: {seg}")
    assert "Tarif über 24 Monate" in namen and \
        "Geräteraten über 24 Monate" in namen, (
        f"ein echter Posten fehlt: {seg}")
    assert round(sum(s["betrag"] for s in seg), 2) == pytest.approx(1360.0)


def test_ausfall_restbetrag_groesser_als_posten_zeichnet_keinen_balken(
        caplog):
    """S3-Nachtrag (gemessen): eine Restschuld, die groesser ist als der
    Posten, aus dem sie stammt (ein widerspruechlicher Bestand), darf
    NIE ein negatives Balkensegment erzeugen (Clean Code 5) - der alte
    Stand rechnete `betrag - rest` ungeprueft und haengte das Ergebnis
    ungeprueft an; das war hier -100.0. Der Ausfall ist benannt: ein
    Protokolleintrag (`logging.warning`) und eine leere Liste als
    Kennzeichen "kein Balken", dieselbe Bedeutung wie ein fehlendes
    `gesamt` oben in der Funktion - die Vorlage laesst den Balken bei
    einer leeren `k.zerlegung` ohnehin schon weg (`{% if k.zerlegung %}`
    in `_geraete_buendel.html.j2`)."""
    from telco_radar.report.geraete_tco_karten import zerlegung_balken

    bestandteile = [
        {"name": "Geräteraten über 36 Monate", "betrag": 400.0,
         "kategorie": "raten"},
    ]
    with caplog.at_level("WARNING"):
        seg = zerlegung_balken(bestandteile, restbetrag=500.0, gesamt=400.0)
    assert seg == [], (
        f"eine Restschuld ueber dem Posten erzeugt trotzdem einen "
        f"Balken: {seg}")
    assert any("restbetrag" in r.message and "500" in r.message
              for r in caplog.records), (
        "kein Protokolleintrag zum Ausfall - Regel 5 verlangt ein "
        "Protokoll, kein stilles leeres Ergebnis ohne Spur")


def test_review_fix_s3_2_voll_offene_raten_ohne_faelliges_nullsegment():
    """Ist die gesamte Rate erst nach Monat 24 faellig (Restschuld ==
    Ratensumme), waere der "fällige" Teil vor dem Split exakt 0,00 € -
    auch DIESES Segment bleibt weg, nur das offene (schraffierte)
    Segment steht."""
    from telco_radar.report.geraete_tco_karten import zerlegung_balken

    seg = zerlegung_balken(
        [{"name": "Geräteraten über 36 Monate", "betrag": 500.0,
          "kategorie": "raten"}],
        restbetrag=500.0, gesamt=500.0)
    faellig = [s for s in seg if not s["offen"]]
    assert not faellig, f"ein 0,00-€ 'fälliger' Teil steht im Balken: {seg}"
    offen = [s for s in seg if s["offen"]]
    assert len(offen) == 1 and offen[0]["betrag"] == pytest.approx(500.0)
