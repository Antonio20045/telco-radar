"""UI-1717 Aufgabe 6: die gepunktete Linie im Chart "Verlauf mit Tarif"
(`#gr-zr-bild`, Pfadklasse `gr-zr-linie--luecke`) ist eine ECHTE Messlücke,
keine Fehldarstellung - sie braucht einen Erklärsatz, der NUR steht, wenn
die konkrete Serie wirklich eine Unterbrechung über der Schwelle zeigt, und
mit dem Datum aus den echten Messtagen (nie hart codiert).

Rot gegen den alten Stand: `_fenster_html()` lieferte vor diesem Auftrag nie
einen solchen Satz, auch nicht bei einer echten Lücke.
"""

from __future__ import annotations

from telco_radar.report import geraete_zeitreihe as zr


def test_ohne_luecke_kein_satz():
    """Zwei dicht aufeinanderfolgende Messtage (unter der Schwelle) - kein
    Hinweis, weil die Linie durchgezogen bleibt."""
    serien = {
        "Telekom": [("2026-10-01", 100.0), ("2026-10-05", 100.0)],
        "Vodafone": [("2026-10-01", 90.0), ("2026-10-05", 90.0)],
    }
    assert zr._luecken_satz(serien) == ""


def test_echte_luecke_nennt_anbieter_und_echtes_datum():
    """Telekom hat vom 21.10. bis zum 02.11. keine Messung (12 Tage, über
    der Schwelle `LUECKE_TAGE_SCHWELLE` von 10) - der Satz nennt genau
    diese beiden Daten, nicht irgendein festes Datum."""
    serien = {
        "Telekom": [
            ("2026-10-21", 100.0),
            ("2026-11-02", 100.0),
        ],
    }
    satz = zr._luecken_satz(serien)
    assert satz != ""
    assert "Telekom" in satz
    assert "21.10." in satz
    assert "2.11." in satz
    assert "gr-zr-luecken-hinweis" in satz


def test_satz_steht_nur_fuer_die_serie_mit_wirklicher_luecke():
    """Vodafone bleibt dicht gemessen - der Satz nennt nur Telekom, nicht
    beide Anbieter pauschal."""
    serien = {
        "Telekom": [("2026-10-21", 100.0), ("2026-11-02", 100.0)],
        "Vodafone": [("2026-10-21", 90.0), ("2026-10-25", 90.0), ("2026-11-02", 90.0)],
    }
    satz = zr._luecken_satz(serien)
    assert "Telekom" in satz
    assert "Vodafone" not in satz


def test_satz_steht_im_gr_zr_bild_block():
    """`_fenster_html()` haengt den Satz NACH dem `#gr-zr-bild`-Block an,
    nicht irgendwo im Legenden-Teil davor."""
    serien = {
        "Telekom": [("2026-10-21", 100.0), ("2026-11-02", 100.0)],
    }
    html = zr._fenster_html(serien, {}, {}, 24)
    pos_bild = html.index('id="gr-zr-bild"')
    pos_satz = html.index("gr-zr-luecken-hinweis")
    assert pos_satz > pos_bild
