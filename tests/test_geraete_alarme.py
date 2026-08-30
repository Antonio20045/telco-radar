"""Reiter 1 der Geraeteseite - die Rechnung, nicht die Darstellung.

Diese Datei ist am 30.08.2026 nachgetragen worden, nachdem der Review
festgestellt hat, dass `report/geraete_alarme.py` keinen einzigen direkten
Test hatte: 219 Zeilen neue Logik, geprueft ausschliesslich indirekt ueber
gerendertes HTML mit einer Fixture aus zwei Geraeten. Damit lagen die
Grenzen der vier Stufen, der Deckel `SICHTBAR_MAX`, der Fall "kein
Wettbewerber" und `leer()` ungeprueft da.
"""
import pytest

from telco_radar.report import geraete_alarme as al


def _angebot(anbieter, preis, **kw):
    satz = {"anbieter": anbieter, "laden": anbieter, "typ": "handel",
            "preis": preis, "url": f"https://{anbieter}.de/p",
            "abgerufen_am": "2026-08-30", "farbe": "navy", "tarif": "",
            "verfuegbarkeit": "lieferbar", "zustand": "neu",
            "listung_id": f"{anbieter}-{preis}"}
    satz.update(kw)
    return satz


def _zeile(*, unser=1000.0, fremd=None, modell="Galaxy S26", gb=256,
           hersteller="Samsung"):
    """Eine Vergleichszeile, wie `geraete_vergleich.vergleich` sie liefert.

    `fremd=None` heisst: kein Wettbewerber fuehrt diese Kombination. Das ist
    NICHT dasselbe wie "wir sind am guenstigsten", und genau diese
    Unterscheidung war der erste Fehler dieser Datei.
    """
    guenstiger = [_angebot("o2", fremd)] if fremd and fremd < unser else []
    teurer = [_angebot("o2", fremd)] if fremd and fremd >= unser else []
    verglichen = len(guenstiger) + len(teurer)
    return {
        "device_id": modell.lower().replace(" ", "-"), "modell": modell,
        "hersteller": hersteller, "speicher": gb, "zustand": "neu",
        "segment": "premium",
        "vodafone": _angebot("Vodafone", unser),
        "guenstiger": guenstiger, "teurer": teurer,
        "anzahl_guenstiger": len(guenstiger), "anzahl_verglichen": verglichen,
        "bester": guenstiger[0] if guenstiger else None,
        "prozent": round((unser - fremd) / unser * 100, 1) if guenstiger else None,
        "differenz": round(unser - fremd, 2) if guenstiger else None,
    }


# --------------------------------------------------------------------------
# Die vier Stufen
# --------------------------------------------------------------------------

@pytest.mark.parametrize("prozent,erwartet", [
    (41.3, "kritisch"),
    (10.0, "kritisch"),          # die Grenze gehoert der schaerferen Stufe
    (9.99, "mittel"),
    (3.0, "mittel"),
    (2.99, "gering"),
    (0.1, "gering"),
    (0.0, "bestpreis"),
    (-5.0, "bestpreis"),
    (None, "bestpreis"),
])
def test_die_stufen_treffen_an_ihren_grenzen(prozent, erwartet):
    """Die Grenzen sind der ganze Inhalt dieser Funktion. Ein Test auf
    "41 Prozent ist kritisch" prueft sie nicht - er prueft die Mitte."""
    assert al.einstufung(prozent) == erwartet


def test_die_kacheln_summieren_sich_auf_die_verglichenen():
    """Eine Kachel, die anders zaehlt als der Satz darunter, ist der
    Fehlertyp aus CLAUDE.md 6."""
    zeilen = [_zeile(unser=1000.0, fremd=800.0),      # kritisch
              _zeile(unser=1000.0, fremd=950.0),      # mittel
              _zeile(unser=1000.0, fremd=990.0),      # gering
              _zeile(unser=1000.0, fremd=1100.0)]     # bestpreis
    erg = al.zeilen({"zeilen": zeilen})
    gezaehlt = {k["schluessel"]: k["zahl"] for k in erg["kacheln"]}
    assert gezaehlt == {"kritisch": 1, "mittel": 1, "gering": 1, "bestpreis": 1}
    assert sum(gezaehlt.values()) == erg["verglichen"] == 4


def test_ein_geraet_ohne_wettbewerber_ist_kein_bestpreis():
    """Nicht verglichen ist nicht dasselbe wie guenstiger. Beides gleich zu
    zaehlen behauptete einen gewonnenen Vergleich, den niemand gefuehrt hat -
    auf einer Seite, deren Verkaufsargument der Belegzwang ist, die teuerste
    Sorte falscher Zahl. Am Bestand vom 30.08.2026 waren das 16 von 62
    Zeilen."""
    erg = al.zeilen({"zeilen": [_zeile(fremd=None), _zeile(fremd=1100.0)]})
    gezaehlt = {k["schluessel"]: k["zahl"] for k in erg["kacheln"]}
    assert gezaehlt["bestpreis"] == 1, "nur die verglichene Zeile zaehlt"
    assert erg["verglichen"] == 1
    assert erg["ohne_wettbewerber"] == 1


# --------------------------------------------------------------------------
# Die Tabelle
# --------------------------------------------------------------------------

def test_zeilen_ohne_rueckstand_stehen_nicht_in_der_tabelle():
    """"niemand guenstiger" stand 36-mal in der alten Tabelle. Das ist keine
    Aussage - die Kachel "Bestpreis" sagt dasselbe einmal."""
    erg = al.zeilen({"zeilen": [_zeile(unser=1000.0, fremd=900.0),
                                _zeile(unser=1000.0, fremd=1100.0)]})
    assert erg["gesamt"] == 1
    assert [z["stufe"] for z in erg["sichtbar"]] == ["kritisch"]


def test_sortiert_wird_nach_prozent_nicht_nach_euro():
    """15 Euro sind bei einem 200-Euro-Geraet viel und bei einem
    2000-Euro-Geraet nichts. Ein 300-Euro-Abstand auf ein 3000-Euro-Geraet
    ist ein kleinerer Rueckstand als 100 Euro auf 400."""
    gross_in_euro = _zeile(unser=3000.0, fremd=2700.0, modell="A")   # 10 %
    gross_in_prozent = _zeile(unser=400.0, fremd=300.0, modell="B")  # 25 %
    erg = al.zeilen({"zeilen": [gross_in_euro, gross_in_prozent]})
    assert [z["modell"] for z in erg["sichtbar"]] == ["B", "A"]
    assert erg["sichtbar"][0]["euro"] < erg["sichtbar"][1]["euro"], (
        "die Fixture trennt die zwei Sortierungen nicht - der Test misst nichts")


def test_der_deckel_schneidet_die_tabelle_und_verliert_nichts():
    """`SICHTBAR_MAX` deckelt die Seitenhoehe STRUKTURELL. Ohne den Deckel
    haengt sie am Datenbestand, und zwei zusaetzliche Zeilen kippen den
    Abnahmetest, ohne dass sich eine Zeile Code aendert."""
    viele = [_zeile(unser=1000.0, fremd=1000.0 - i, modell=f"M{i}")
             for i in range(1, al.SICHTBAR_MAX + 6)]
    erg = al.zeilen({"zeilen": viele})
    assert len(erg["sichtbar"]) == al.SICHTBAR_MAX
    assert len(erg["rest"]) == 5
    assert len(erg["sichtbar"]) + len(erg["rest"]) == erg["gesamt"] == len(viele)


def test_der_aufklapper_traegt_unseren_eigenen_preis_mit():
    """Der Klick zeigt die ganze Lage, nicht nur den Sieger."""
    erg = al.zeilen({"zeilen": [_zeile(unser=1000.0, fremd=900.0)]})
    alle = erg["sichtbar"][0]["alle"]
    assert [a["anbieter"] for a in alle] == ["o2", "Vodafone"], "nach Preis"
    assert any(a.get("eigen") for a in alle), "unser Preis ist nicht markiert"


def test_ein_angebot_ohne_preis_reisst_die_sortierung_nicht():
    """Ein Tupelvergleich auf None wirft, sobald das erste Element gleich
    ist. Hier ist es das - beide sind `True`."""
    zeile = _zeile(unser=1000.0, fremd=900.0)
    zeile["teurer"] = [_angebot("freenet", None), _angebot("expert", None)]
    erg = al.zeilen({"zeilen": [zeile]})
    assert len(erg["sichtbar"][0]["alle"]) == 4


# --------------------------------------------------------------------------
# Ausreisser und Notzustand
# --------------------------------------------------------------------------

def test_ein_ausreisser_wird_an_seiner_zeile_markiert():
    """Ein Ausreisser wird gemeldet statt geloescht - und gemeldet heisst
    DORT sichtbar, wo jemand die Zahl liest."""
    zeile = _zeile(unser=1000.0, fremd=300.0)
    kennung = zeile["bester"]["listung_id"]
    erg = al.zeilen({"zeilen": [zeile]}, {kennung: {"art": "ausreisser"}})
    assert erg["sichtbar"][0]["auffaellig"] is True
    ohne = al.zeilen({"zeilen": [zeile]})
    assert ohne["sichtbar"][0]["auffaellig"] is False


def test_der_notzustand_traegt_dieselben_schluessel_wie_der_normalfall():
    """Ein fehlender Schluessel ist in Jinja kein Fehler, sondern eine stumm
    leere Seite. `leer()` und `zeilen()` duerfen nicht auseinanderlaufen -
    und bis zum 30.08.2026 behauptete der Modulkopf einen Test dafuer, den
    es nicht gab."""
    assert set(al.leer()) == set(al.zeilen({"zeilen": []}))
    assert al.leer()["hat_daten"] is False
    assert [k["schluessel"] for k in al.leer()["kacheln"]] == [
        s for s, _, _ in al.STUFEN]


def test_die_filterlisten_kommen_aus_den_gezeigten_zeilen():
    """Ein Auswahlfeld, das eine Marke anbietet, zu der die Tabelle keine
    Zeile hat, fuehrt zu einer leeren Tabelle und sieht wie ein Fehler aus."""
    erg = al.zeilen({"zeilen": [
        _zeile(unser=1000.0, fremd=900.0, hersteller="Samsung", gb=256),
        _zeile(unser=1000.0, fremd=1100.0, hersteller="Apple", gb=512),
    ]})
    assert erg["marken"] == ["Samsung"], "Apple steht nur in der Bestpreis-Kachel"
    assert erg["speicher"] == [256]
