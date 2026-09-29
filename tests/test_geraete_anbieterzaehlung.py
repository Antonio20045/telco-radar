"""BRIEF_F5_ANBIETERZAEHLUNG (05.09.2026): eine Zahl, ein Wort.

Der Befund: auf derselben Modelltafel bedeutete "Anbieter" zwei
verschiedene Dinge - die Geraeteauswahl zaehlte die Anbieter mit einem
TCO-Buendel ("Apple iPhone 17 Pro 256 GB - 2 Anbieter"), der Zeitreihen-
Chart darunter (aria-label und chrome-Zeile) zaehlte die Preispunkte-
Reihen der Zeitreihe ("5 Anbieter"). Zwei Zaehlweisen, dasselbe Wort.

O1 (STRATEGIE_GERAETE_OPTIK, 11.09.2026) hat das Problem AN DER WURZEL
geloest, nicht umgangen: Das "- N Anbieter"-Suffix existiert nicht mehr.
Die Geraeteauswahl nennt nur den Geraetenamen, und die fuenf Zehlsysteme
der Vergleichsansicht sind auf EINE Fussnote unter dem Graphen gesammelt
("N Geraete mit mindestens einem erhebbaren Buendel"). Der Zeitreihen-
Chart ist mit O1 aus der Vergleichsansicht entfernt (O4 bindet ihn im
Verlaufs-Reiter wieder an).

Diese Datei sichert seither die EINE Rechnung: `zeitreihe()` liefert
seine Reihenzahl als Feld. (Die Seiten-Tests der alten Geräteauswahl
fielen mit dem Neuentwurf der Geräteseite am 29.09.2026.)
"""
from __future__ import annotations

from telco_radar.report import geraete_tco_grafik as grafik


# --------------------------------------------------------------------------
# Die eine Rechnung: `zeitreihe()` liefert ihre Reihenzahl als Feld
# --------------------------------------------------------------------------

def _reihe(anbieter, punkte):
    return {"anbieter": anbieter, "farbe": "#123456", "eigen": False,
            "punkte": [{"datum": d, "preis": p} for d, p in punkte]}


def test_zeitreihe_liefert_ihre_eigene_reihenzahl_als_feld():
    """Das Feld, das die Vorlage fuer das Dropdown-Label liest, muss
    dieselbe Zahl tragen wie das aria-label - beide entstehen aus
    `len(reihen)`, nicht aus zwei getrennten Zaehlungen."""
    reihen = [
        _reihe("Vodafone", [("2026-08-20", 1000.0), ("2026-09-01", 1000.0)]),
        _reihe("congstar", [("2026-08-20", 990.0)]),
        _reihe("o2", [("2026-08-20", 980.0), ("2026-09-01", 970.0)]),
    ]
    ergebnis = grafik.zeitreihe(reihen)
    assert ergebnis["anbieterzahl"] == 3 == len(reihen)
    assert f"{ergebnis['anbieterzahl']} Anbieter" in ergebnis["svg"]


def test_zeitreihe_ohne_jeden_messpunkt_traegt_die_zahl_null():
    ergebnis = grafik.zeitreihe([])
    assert ergebnis["hat_daten"] is False
    assert ergebnis["anbieterzahl"] == 0
