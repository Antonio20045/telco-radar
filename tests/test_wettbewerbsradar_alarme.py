"""O2 (STRATEGIE_GERAETE_OPTIK §3, 11.09.2026): die Alarmtabelle wandert
von der Vergleichsansicht der Geräteseite auf den Wettbewerbs-Radar.

E3 (AUFTRAG_GERAETE_EINE_SEITE_V2 §1d, 17.09.2026) korrigiert den Ort des
Sortiments-Aufklappers "Bei Wettbewerbern gelistet, bei Vodafone nicht":
Er steht jetzt IM GERÄTEKATALOG-REITER der Geräteseite - im Vier-Reiter-
Gerüst der EINEN Seite ist der Katalog der Sortiments-Reiter, und "nur bei
Wettbewerbern im Regal" ist die Komplementäraussage zu dessen Tabelle
(S1/S3), keine Radar-Frage. Auf der Schwesterseite bleibt er weg: umgezogen,
nicht kopiert (§4.6). Die Alarmtabelle bleibt Radar-Inhalt (E3 Schritt 2
montiert sie in den Radar-Reiter derselben Seite).

Die gerenderten Seitentests fielen mit dem Neuentwurf der Geräteseite
(29.09.2026, eine Kosten-Rangliste ohne Radar-Reiter). Geblieben ist die
Aufbereitung: der Radar trägt am echten Bestand alle Alarmzeilen und die
Sortimentslücke der View.
"""
from __future__ import annotations

import pathlib

import pytest

from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import geraete_view, geraete_radar as wr

WURZEL = pathlib.Path(__file__).resolve().parents[1]

# --------------------------------------------------------------------------
# Am echten Bestand: Vollständigkeit des Umzugs (keine Tageszählung - die
# Zeilenzahl der Seite wird gegen die Aufbereitung gehalten, nicht auf eine
# Zahl festgenagelt, die jede Nacht wächst). View-Ebene wie der `echt`-
# Fixture der Nachbardatei.
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def echt():
    state = WURZEL / "data" / "state"
    if not (state / "geraete_db.json").exists():
        pytest.skip("kein Gerätebestand im Checkout")
    view = geraete_view.aufbereiten(state, lade_quellen(WURZEL),
                                    lade_katalog(WURZEL), heute="")
    radar = wr.radar(view["tco"], view["vergleich"]["ohne_vertrag"],
                     view["quellenlage"], alarme=view["alarme"])
    return {"view": view, "radar": radar}


def test_am_echten_bestand_traegt_der_radar_alle_alarmzeilen(echt):
    """Der Deckel (`SICHTBAR_MAX`) kappt nur die ANSICHT - die View führt
    die volle Liste. Ein Umzug, der nur die sichtbaren Zeilen nimmt,
    verlöre den Rest still."""
    alarme = echt["view"]["alarme"]
    if not alarme["gesamt"]:
        pytest.skip("Bestand ohne Alarmzeile")
    ueber = echt["radar"]["alarme"]
    assert ueber["gesamt"] == alarme["gesamt"]
    assert len(ueber["sichtbar"]) + len(ueber["rest"]) == alarme["gesamt"]


def test_am_echten_bestand_traegt_der_radar_die_sortimentsluecke(echt):
    ohne = echt["view"]["vergleich"]["ohne_vertrag"]
    if not ohne["ohne_vodafone_gesamt"]:
        pytest.skip("Bestand ohne Sortimentslücke")
    assert echt["radar"]["ohne_vodafone_gesamt"] == \
        ohne["ohne_vodafone_gesamt"]
    assert len(echt["radar"]["ohne_vodafone"]) == \
        len(ohne["ohne_vodafone"])
