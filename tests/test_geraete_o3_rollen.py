"""O3 (STRATEGIE_GERAETE_OPTIK §3, 15.09.2026): Rollen und Navigation.

Die Reiter, Querlinks und Bündel-Fragmente dieser Datei sind mit dem
Neuentwurf der Geräteseite (29.09.2026, eine Kosten-Rangliste ohne Reiter)
gefallen, mit ihnen die Seitentests. Geblieben ist der Rückbau leserloser
Felder in `geraete_tco_view` (S4).
"""
from __future__ import annotations


def test_die_tco_view_liefert_keine_leserlosen_felder_mehr():
    """S4: `tabelle`, `hat_tco` und `zeilen_gesamt` hatten nach O2 keinen
    Leser mehr in Vorlage, JS oder Tests — Rückbau statt Ruhelager.

    `zeilen` und `delta` BLEIBEN bewusst: Kein Template liest sie, aber
    die Rechen-Testreihe (tests/test_geraete_tco_view.py) hält an ihnen
    die Zusicherungen von `tco_24()` fest, und `_offene_posten` rechnet
    aus `zeilen` — der Auftragswortlaut sagt „entfernen ODER verbrauchen",
    und das ist das Verbrauchen."""
    from telco_radar.report import geraete_tco_view
    for feld in ("tabelle", "zeilen_gesamt", "hat_tco"):
        assert feld not in geraete_tco_view.leer(), feld
        assert feld not in geraete_tco_view.aufbereiten(
            [], [], [], katalog=None), feld
