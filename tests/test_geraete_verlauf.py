"""Reiter 3: der Preisverlauf EINES Geraets (B4, 30.08.2026).

Geprueft wird hier die RECHNUNG. Dass ohne Klick das erste Geraet der
Liste vorausgewaehlt dasteht (P2, 17.09.2026 - die B4-Regel „ohne Auswahl
kein Diagramm" ist damit gekippt), dass die Achse hoechstens acht
waagerechte Marken traegt und dass keine Schrift unter 12 px faellt, misst
`tests/test_geraete_reiter_browser.py` im echten Chromium - im gerenderten
SVG, nicht im Quelltext. Ein statischer Test kann das nicht sehen, weil das
SVG erst im Browser entsteht.
"""
import pytest

from telco_radar.geraete_model import Geraet, Katalog
from telco_radar.report import anbieter_farben as farben
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
    eigen_farbe = farben.ANBIETER_FARBE["vodafone"].farbe
    farbe_je_anbieter = {r["anbieter"]: r["farbe"] for r in g["reihen"]}
    assert farbe_je_anbieter["Vodafone"] == eigen_farbe
    assert farbe_je_anbieter["o2"] != eigen_farbe
    assert [r["eigen"] for r in g["reihen"]] == [True, False]


def test_die_netzbetreiber_farben_sind_verschieden():
    """P2/D1: Vodafone, Telekom, o2, 1&1 und congstar tragen je eine
    EIGENE Markenfarbe aus der einen Quelle (`anbieter_farben.py`).
    Service-Provider und Haendler teilen bewusst eine Kategorie-Farbe
    (grau) - das ist keine Kollision, sondern der Auftrag: sie fuehren
    kein eigenes Netz und sollen keine eigene Marke im Bild vortaeuschen.
    """
    listungen = [_l("vf", "Vodafone", 800.0), _l("t", "Telekom", 801.0),
                 _l("o", "o2", 802.0), _l("e", "1&1", 803.0),
                 _l("c", "congstar", 804.0)]
    g = _eins(v.geraete_mit_verlauf(listungen, _Historie(), _KATALOG))
    farbwerte = [r["farbe"] for r in g["reihen"]]
    assert len(set(farbwerte)) == len(farbwerte), farbwerte


def test_unbekannte_anbieter_teilen_die_benannte_luecke():
    """Die HASH-PALETTE gab zwei unbekannten Namen so gut wie immer
    verschiedene Farben - eine geratene Unterscheidung, die es nicht
    gibt. `anbieter_farben.py` zeichnet einen unbekannten Anbieter als
    die eine benannte Luecke (Clean Code 3/4): dieselbe Farbe, derselbe
    Strich, derselbe Marker, `bekannt=False` - nie eine Erfindung."""
    listungen = [_l("a", "Erfundener Anbieter Eins", 800.0),
                 _l("b", "Erfundener Anbieter Zwei", 801.0)]
    g = _eins(v.geraete_mit_verlauf(listungen, _Historie(), _KATALOG))
    farbwerte = {r["farbe"] for r in g["reihen"]}
    assert farbwerte == {farben.LUECKE_FARBE}
    assert all(not r["bekannt"] for r in g["reihen"])


def test_die_telekom_farbe_ist_magenta_nicht_gruen():
    """DER gemessene Befund von P2/D1: die alte Hash-Palette
    (`md5('telekom') % 7`) traf auf `#217a3c` (Gruen) - die Telekom stand
    gruen im Preisverlauf, waehrend sie in der TCO-Zeitreihe
    (`geraete_zeitreihe.ANB_FARBE`) magenta war. Beide lesen jetzt aus
    derselben Quelle."""
    g = _eins(v.geraete_mit_verlauf(
        [_l("t", "Telekom", 900.0), _l("vf", "Vodafone", 899.0)],
        _Historie(), _KATALOG))
    telekom = next(r for r in g["reihen"] if r["anbieter"] == "Telekom")
    assert telekom["farbe"] == "#e20074"
    assert telekom["farbe"] != "#217a3c", "das ist die alte Hash-Gruen-Farbe"


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


def test_zwei_bekannte_anbieter_eines_diagramms_sehen_nie_gleich_aus():
    """P2/D1 loest diese Zusicherung anders ein als die alte Hash-Palette:
    nicht mehr JEDE Farbe einzeln verschieden (Service-Provider teilen
    bewusst ein Grau, Haendler ein anderes - das ist der Auftrag, keine
    Kollision), sondern die volle Kombination aus Farbe, Strichart und
    Markerform. Innerhalb einer Kategorie (hier: die drei Service-Provider
    ALDI TALK/freenet/mobilcom-debitel) traegt allein die MARKERFORM die
    Unterscheidung - farbe_fuer() allein reicht dort bewusst nicht."""
    namen = ["o2", "mobilcom-debitel", "ALDI TALK", "freenet", "Medimax",
             "congstar", "Vodafone"]
    g = _eins(v.geraete_mit_verlauf(
        [_l(f"l{i}", n, 800.0 + i) for i, n in enumerate(namen)],
        _Historie(), _KATALOG))
    stile = [(r["farbe"], r["strich"], r["marker"]) for r in g["reihen"]]
    assert len(set(stile)) == len(stile), list(zip(
        [r["anbieter"] for r in g["reihen"]], stile))
    # Gegenprobe: die drei Service-Provider TEILEN wirklich eine Farbe -
    # sonst prueft der Test oben nichts an der Stelle, an der es zaehlt.
    service_farben = {r["farbe"] for r in g["reihen"]
                      if r["anbieter"].lower() in
                      ("mobilcom-debitel", "aldi talk", "freenet")}
    assert service_farben == {farben.GRAU_SERVICE}


def test_ein_unbekannter_anbieter_im_diagramm_bekommt_keine_geratene_farbe():
    """Der frueher hier getestete Fall (Name 'expert', keine Markenfarbe
    hinterlegt) bekommt jetzt die benannte Luecke statt eine geratene
    Ausweichfarbe."""
    namen = ["Vodafone", "expert"]
    g = _eins(v.geraete_mit_verlauf(
        [_l(f"l{i}", n, 800.0 + i) for i, n in enumerate(namen)],
        _Historie(), _KATALOG))
    expert = next(r for r in g["reihen"] if r["anbieter"] == "expert")
    assert expert["farbe"] == farben.LUECKE_FARBE
    assert not expert["bekannt"]


def test_zwei_preise_an_einem_tag_sind_eine_messluecke_kein_punkt():
    """Bis zum 04.09.2026 stand hier "der bestaetigte Preis schlaegt den
    Historieneintrag": aus 129 und 155 EUR am selben Tag wurde der Preis der
    Datenbank. QA-Befund B2 dreht das um - zwei gleichzeitig gueltige Preise
    derselben Listung sind eine MESSLUECKE, keine Messung. Welcher der zwei
    in der Datenbank steht, haengt davon ab, welcher Artikel im Lauf zuerst
    kam; ihn zu zeichnen waere eine Wahl, keine Auskunft.

    Der Fall ist echt: ALDI TALKs "Galaxy A17 LTE + Starter Kit" (129 EUR)
    und "Galaxy A17 5G" (155/159 EUR) laufen unter derselben listung_id.
    """
    hist = _Historie({"a": [{"datum": "2026-08-29", "preis_ohne_vertrag": 129.0},
                            {"datum": "2026-08-29", "preis_ohne_vertrag": 155.0}]})
    listungen = [_l("a", "ALDI TALK", 155.0, last_verified="2026-08-29")]
    # Kein Punkt - auch nicht der bestaetigte aus der Datenbank.
    assert v._punkte(listungen, hist) == []
    assert v.geraete_mit_verlauf(listungen, hist, _KATALOG) == []
    # Aber die Luecke ist benannt, mit beiden Betraegen.
    assert v.mehrdeutige_tage(listungen, hist) == [
        {"anbieter": "ALDI TALK", "listung_id": "a", "tage": ["2026-08-29"],
         "betraege": {"2026-08-29": [129.0, 155.0]}}]
    # Und ein zweiter, eindeutiger Tag derselben Listung bleibt erhalten.
    hist2 = _Historie({"a": [{"datum": "2026-08-29", "preis_ohne_vertrag": 129.0},
                             {"datum": "2026-08-29", "preis_ohne_vertrag": 155.0},
                             {"datum": "2026-08-30", "preis_ohne_vertrag": 129.0}]})
    punkte = v._punkte([_l("a", "ALDI TALK", 129.0, last_verified="2026-08-31")],
                       hist2)
    assert [(p["datum"], p["preis"]) for p in punkte] == [
        ("2026-08-30", 129.0), ("2026-08-31", 129.0)]


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
