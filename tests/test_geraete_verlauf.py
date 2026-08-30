"""Reiter 3: der Preisverlauf EINES Geraets (B4, 30.08.2026).

Geprueft wird hier die RECHNUNG. Dass ohne Auswahl kein Diagramm dasteht,
dass die Achse hoechstens acht waagerechte Marken traegt und dass keine
Schrift unter 12 px faellt, misst `tests/test_geraete_reiter_browser.py` im
echten Chromium - im gerenderten SVG, nicht im Quelltext. Ein statischer
Test kann das nicht sehen, weil das SVG erst im Browser entsteht.
"""
import pytest

from telco_radar.geraete_model import Geraet, Katalog
from telco_radar.report import geraete_verlauf as v

_KATALOG = Katalog(geraete=[
    Geraet(hersteller="Samsung", modell="Galaxy S25", generation=25,
           speicher=[128, 256], segment="premium"),
])
_GID = "samsung-galaxy-s25"


class _Historie:
    """Nur die eine Methode, die `_punkte` benutzt."""

    def __init__(self, reihen=None):
        self._reihen = reihen or {}

    def reihe(self, listung_id):
        return sorted(self._reihen.get(listung_id, []),
                      key=lambda s: s.get("datum", ""))


def _l(kennung, anbieter, preis, *, last_verified="2026-08-29", speicher=128,
       zustand="neu"):
    return {"id": kennung, "anbieter": anbieter, "device_id": _GID,
            "speicher_gb": speicher, "zustand": zustand,
            "preis_ohne_vertrag": preis, "last_verified": last_verified,
            "farbe_normalisiert": "navy"}


def _eins(geraete):
    assert len(geraete) == 1, [g["label"] for g in geraete]
    return geraete[0]


# --------------------------------------------------------------------------
# Die Messpunkte
# --------------------------------------------------------------------------

def test_der_bestaetigungstag_verlaengert_die_kurve():
    """Die Historie traegt nur AENDERUNGSpunkte. Ohne `last_verified` endet
    jede Linie am Tag ihrer letzten Aenderung und behauptet damit, das Geraet
    sei seitdem nicht mehr gesehen worden.

    Genau daran haengt auch die Zahl der Messtermine: wer nur die
    Aenderungsdatei zaehlt, kommt auf zwei statt vier.
    """
    hist = _Historie({"a": [{"datum": "2026-08-10", "preis_ohne_vertrag": 899.0}]})
    g = _eins(v.geraete_mit_verlauf(
        [_l("a", "o2", 880.0, last_verified="2026-08-29")], hist, _KATALOG))
    assert g["tage"] == ["2026-08-10", "2026-08-29"]
    assert g["messpunkte"] == 2


def test_ein_bestaetigungstag_verdraengt_keinen_echten_messpunkt():
    """Faellt der Bestaetigungstag auf denselben Tag wie eine Aenderung,
    stehen zwei Punkte fuer denselben (Anbieter, Tag) zur Wahl. Sie tragen
    denselben Preis, weil `last_verified` den AKTUELLEN Preis bestaetigt -
    ein Widerspruch waere ein Datenfehler und keine Preisbewegung."""
    hist = _Historie({"a": [{"datum": "2026-08-29", "preis_ohne_vertrag": 880.0}]})
    g = _eins(v.geraete_mit_verlauf(
        [_l("a", "o2", 880.0, last_verified="2026-08-29")], hist, _KATALOG))
    assert g["messpunkte"] == 1
    assert g["reihen"][0]["punkte"] == [{"datum": "2026-08-29", "preis": 880.0}]


def test_zwei_farben_desselben_geraets_sind_ein_punkt_je_tag():
    """Zwei Farben sind zwei Listungen, aber EIN Preis auf der Kurve. Sonst
    zeichnete die Linie an einem Tag fuenf Punkte uebereinander, und die
    Zahl "Messpunkte" zaehlte Farben statt Messungen."""
    g = _eins(v.geraete_mit_verlauf(
        [_l("a", "o2", 899.0), _l("b", "o2", 880.0)], _Historie(), _KATALOG))
    assert g["messpunkte"] == 1
    assert g["reihen"][0]["punkte"][0]["preis"] == 880.0, "der niedrigere gilt"


def test_eine_listung_ohne_preis_erzeugt_keinen_punkt():
    assert v.geraete_mit_verlauf([_l("a", "o2", None)], _Historie(),
                                 _KATALOG) == []


def test_gebrauchtgeraete_stehen_nicht_in_derselben_kurve():
    """Ein Gebrauchtpreis und ein Neupreis in einer Linie sind zwei Produkte,
    und der Sprung dazwischen saehe aus wie ein Preissturz."""
    geraete = v.geraete_mit_verlauf(
        [_l("a", "o2", 899.0), _l("b", "o2", 577.0, zustand="refurbished")],
        _Historie(), _KATALOG)
    g = _eins(geraete)
    assert g["min"] == 899.0 and g["max"] == 899.0


# --------------------------------------------------------------------------
# Die Linien
# --------------------------------------------------------------------------

def test_hoechstens_acht_linien():
    """Mehr Anbieter kann ein Mensch in einem Liniendiagramm nicht
    auseinanderhalten, und die Legende waere laenger als das Bild."""
    listungen = [_l(f"a{i}", f"Anbieter {i}", 800.0 + i) for i in range(12)]
    g = _eins(v.geraete_mit_verlauf(listungen, _Historie(), _KATALOG))
    assert len(g["reihen"]) == v.MAX_LINIEN
    assert g["anbieter"] == v.MAX_LINIEN


def test_der_eigene_anbieter_faellt_nie_aus_der_kappung():
    """Eine Preisgrafik ohne uns beantwortet die Frage nicht, wegen der sie
    dasteht. Vodafone hat hier den WENIGSTEN Stoff - nach Punktzahl allein
    sortiert fiele es als Erstes heraus."""
    hist = _Historie({f"a{i}": [{"datum": "2026-08-10",
                                 "preis_ohne_vertrag": 800.0 + i}]
                      for i in range(12)})
    listungen = [_l(f"a{i}", f"Anbieter {i}", 800.0 + i) for i in range(12)]
    listungen.append(_l("vf", "Vodafone", 849.9))
    g = _eins(v.geraete_mit_verlauf(listungen, hist, _KATALOG))
    namen = [r["anbieter"] for r in g["reihen"]]
    assert "Vodafone" in namen, namen
    assert namen[0] == "Vodafone", "der eigene Anbieter steht zuerst"
    # Gegenprobe: ohne die Ausnahme haette er wirklich weichen muessen.
    ohne = v.geraete_mit_verlauf(listungen[:-1], hist, _KATALOG)[0]
    assert len(ohne["reihen"]) == v.MAX_LINIEN


def test_der_eigene_anbieter_ist_rot_und_die_uebrigen_nicht():
    g = _eins(v.geraete_mit_verlauf(
        [_l("vf", "Vodafone", 849.9), _l("o", "o2", 883.0)],
        _Historie(), _KATALOG))
    farben = {r["anbieter"]: r["farbe"] for r in g["reihen"]}
    assert farben["Vodafone"] == v.EIGEN_FARBE
    assert farben["o2"] != v.EIGEN_FARBE
    assert [r["eigen"] for r in g["reihen"]] == [True, False]


def test_die_farben_der_wettbewerber_sind_verschieden():
    listungen = [_l(f"a{i}", f"Anbieter {i}", 800.0 + i)
                 for i in range(len(v.FARBEN))]
    g = _eins(v.geraete_mit_verlauf(listungen, _Historie(), _KATALOG))
    farben = [r["farbe"] for r in g["reihen"]]
    assert len(set(farben)) == len(farben), farben


# --------------------------------------------------------------------------
# Die Tabelle unter dem Diagramm
# --------------------------------------------------------------------------

def test_ohne_zweiten_messpunkt_gibt_es_keine_veraenderung():
    """"-0,00 EUR" und "0 Tage" sind keine Auskunft. Der Auftrag verbietet
    Zeilen, die nichts sagen - hier steht dann ein Strich."""
    g = _eins(v.geraete_mit_verlauf([_l("a", "o2", 899.0)], _Historie(),
                                    _KATALOG))
    assert g["aktuell"][0]["veraenderung"] is None


def test_ein_unveraenderter_preis_ist_auch_keine_veraenderung():
    hist = _Historie({"a": [{"datum": "2026-08-10", "preis_ohne_vertrag": 899.0}]})
    g = _eins(v.geraete_mit_verlauf(
        [_l("a", "o2", 899.0, last_verified="2026-08-29")], hist, _KATALOG))
    assert g["aktuell"][0]["messpunkte"] == 2, "die Fixture hat zwei Punkte"
    assert g["aktuell"][0]["veraenderung"] is None


def test_eine_echte_bewegung_wird_beziffert():
    hist = _Historie({"a": [{"datum": "2026-08-10", "preis_ohne_vertrag": 949.0}]})
    g = _eins(v.geraete_mit_verlauf(
        [_l("a", "o2", 899.0, last_verified="2026-08-29")], hist, _KATALOG))
    assert g["aktuell"][0]["veraenderung"] == -50.0
    assert g["aktuell"][0]["preis"] == 899.0, "der JUENGSTE Preis, nicht der erste"


def test_die_tabelle_sortiert_nach_preis():
    g = _eins(v.geraete_mit_verlauf(
        [_l("a", "o2", 883.0), _l("b", "freenet", 899.0),
         _l("vf", "Vodafone", 849.9)], _Historie(), _KATALOG))
    assert [z["anbieter"] for z in g["aktuell"]] == ["Vodafone", "o2", "freenet"]


# --------------------------------------------------------------------------
# Die Bilanz
# --------------------------------------------------------------------------

def test_die_messtermine_werden_gerechnet_und_nicht_behauptet():
    """Der Auftrag nennt vier Messtermine. Die Zahl steht nirgends im Code -
    sie entsteht aus den Daten, und wenn naechste Woche fuenf da sind, sagt
    die Seite fuenf."""
    hist = _Historie({"a": [{"datum": "2026-08-10", "preis_ohne_vertrag": 949.0},
                            {"datum": "2026-08-21", "preis_ohne_vertrag": 920.0}]})
    erg = v.aufbereiten([_l("a", "o2", 899.0, last_verified="2026-08-29")],
                        hist, _KATALOG)
    assert erg["messtermine"] == 3
    assert erg["seit"] == "2026-08-10" and erg["bis"] == "2026-08-29"
    assert erg["hat_daten"] is True


def test_der_leerzustand_traegt_dieselben_schluessel():
    """Ein fehlender Schluessel ist in Jinja kein Fehler, sondern eine stumm
    leere Seite."""
    voll = v.aufbereiten([_l("a", "o2", 899.0)], _Historie(), _KATALOG)
    assert set(v.leer()) == set(voll)
    assert v.leer()["hat_daten"] is False
    assert v.aufbereiten([], _Historie(), _KATALOG)["hat_daten"] is False


@pytest.mark.parametrize("begriff", ["galaxy", "samsung", "128", "navy"])
def test_der_suchtext_findet_das_geraet(begriff):
    """Ohne Treffer im Suchfeld ist das Geraet unerreichbar - und damit sein
    Diagramm."""
    g = _eins(v.geraete_mit_verlauf([_l("a", "o2", 899.0)], _Historie(),
                                    _KATALOG))
    assert begriff in g["suchtext"], g["suchtext"]


def test_ein_anbieter_behaelt_seine_farbe_ueber_geraete_hinweg():
    """Die erste Fassung vergab die Farbe nach der SORTIERPOSITION innerhalb
    eines Geraets. Ueber die 89 waehlbaren Geraete gemessen hatte o2 damit
    drei Farben, und `#2b5bd7` hiess beim einen Geraet "o2" und beim
    naechsten "mobilcom-debitel"."""
    hist = _Historie()
    # Geraet A: o2 hat mehr Punkte, steht also zuerst.
    a = v.geraete_mit_verlauf(
        [_l("x", "o2", 800.0), _l("y", "freenet", 810.0)], hist, _KATALOG)[0]
    # Geraet B: die Reihenfolge dreht sich um.
    b = v.geraete_mit_verlauf(
        [_l("x", "freenet", 700.0), _l("y", "o2", 710.0),
         _l("z", "ALDI TALK", 690.0)], hist, _KATALOG)[0]
    von = lambda g, n: next(r["farbe"] for r in g["reihen"] if r["anbieter"] == n)
    assert von(a, "o2") == von(b, "o2")
    assert von(a, "freenet") == von(b, "freenet")


def test_zwei_anbieter_eines_diagramms_teilen_nie_eine_farbe():
    """Der Hash kann kollidieren - im selben Bild darf er es nicht. Genau
    dieser Fall trat mit der Zeichenquersumme bei o2 und mobilcom-debitel
    ein, und die zwei stehen bei fast jedem Geraet nebeneinander."""
    namen = ["o2", "mobilcom-debitel", "ALDI TALK", "freenet", "Medimax",
             "expert", "congstar", "Vodafone"]
    g = _eins(v.geraete_mit_verlauf(
        [_l(f"l{i}", n, 800.0 + i) for i, n in enumerate(namen)],
        _Historie(), _KATALOG))
    farben = [r["farbe"] for r in g["reihen"]]
    assert len(set(farben)) == len(farben), list(zip(
        [r["anbieter"] for r in g["reihen"]], farben))


def test_der_bestaetigte_preis_schlaegt_den_historieneintrag():
    """"Der niedrigste Preis ist der wahrscheinlichste Fehler; jede
    min-Auswahl braucht einen Filter davor." Hier stand ein nacktes Minimum.

    Der Fall ist echt: eine ALDI-TALK-Listung traegt am 29.08.2026 zwei
    Historienzeilen (129 und 155 EUR), weil zwei Produkte unter derselben
    listung_id laufen. Die Pruefung meldet das, filtert aber EINTRAEGE - die
    Historie zu einem ueberlebenden Eintrag wird roh gelesen.
    """
    hist = _Historie({"a": [{"datum": "2026-08-29", "preis_ohne_vertrag": 129.0},
                            {"datum": "2026-08-29", "preis_ohne_vertrag": 155.0}]})
    g = _eins(v.geraete_mit_verlauf(
        [_l("a", "ALDI TALK", 155.0, last_verified="2026-08-29")], hist,
        _KATALOG))
    assert g["reihen"][0]["punkte"] == [{"datum": "2026-08-29", "preis": 155.0}], (
        "die Kurve zeigt einen Preis, den die Datenbank fuer dieses Geraet "
        "nicht kennt")


# --------------------------------------------------------------------------
# NACHBESSERUNG 30.08.2026: Messtermine je Geraet
# --------------------------------------------------------------------------

def test_jedes_geraet_nennt_seine_eigenen_messtermine():
    """Die Kachel ueber dem Diagramm zeigte `messpunkte` (Preispunkte ueber
    alle Anbieter) unter der Ueberschrift "Messpunkte", waehrend der Satz
    zwei Zeilen darunter die globalen `messtermine` nannte: "4 Messpunkte"
    ueber "5 Messtermine". Beide Zahlen stimmten und zaehlten Verschiedenes -
    fuer den Leser sind das zwei Zahlen fuer dieselbe Sache.

    Ein Messtermin ist ein TAG, an dem gemessen wurde. Bei drei Anbietern an
    zwei Tagen sind das sechs Preispunkte und zwei Termine."""
    hist = _Historie({
        "a": [{"datum": "2026-08-10", "preis_ohne_vertrag": 900.0}],
        "b": [{"datum": "2026-08-10", "preis_ohne_vertrag": 880.0}],
        "c": [{"datum": "2026-08-10", "preis_ohne_vertrag": 870.0}],
    })
    g = _eins(v.geraete_mit_verlauf(
        [_l("a", "o2", 900.0), _l("b", "Vodafone", 880.0),
         _l("c", "mobilcom-debitel", 870.0)], hist, _KATALOG))
    assert g["messtermine"] == 2, g["tage"]
    assert g["messpunkte"] == 6
    assert g["messtermine"] == len(g["tage"])


def test_die_schwelle_fuers_diagramm_steht_im_modul():
    """Sie entscheidet, ob ueberhaupt ein Diagramm entsteht, und `app.js`
    liest sie als data-Attribut aus der Vorlage. Zwei Zahlen fuer dieselbe
    Regel waeren zwei Regeln - dieselbe Lehre wie bei der
    Stichwort-Vorschau (CLAUDE.md §6)."""
    assert v.DIAGRAMM_AB_TERMINEN >= 3, (
        "unter drei Punkten ist jede Linie eine Gerade durch zwei Punkte")
    assert v.aufbereiten([], _Historie(), _KATALOG)["diagramm_ab_terminen"] \
        == v.DIAGRAMM_AB_TERMINEN
    assert v.leer()["diagramm_ab_terminen"] == v.DIAGRAMM_AB_TERMINEN
    # Der Leerzustand muss DIESELBEN Schluessel tragen wie der Normalfall -
    # ein fehlender ist in Jinja kein Fehler, sondern eine stumm leere Seite.
    assert set(v.leer()) == set(v.aufbereiten([], _Historie(), _KATALOG))
