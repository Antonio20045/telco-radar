"""Die Preisform der o2-Zahl: ein Ratengesamtbetrag sieht nicht mehr aus wie
ein Barpreis (03.09.2026).

DER BEFUND, DEN DIESE TESTS FESTHALTEN
--------------------------------------
o2s Preisspalte trug `totalPrice` - die Summe aus Anzahlung und 24
Monatsraten - und stand damit in derselben Optik wie freenets Barpreis. Am
03.09.2026 gemessen: iPhone 17 256 GB, 949,00 EUR bar bei freenet gegen
1027,00 EUR bei o2 (7 EUR Anzahlung plus 24 x 42,50). 78 EUR Unterschied, die
zum Teil eine Frage der Zahlweise sind und nicht des Preises.

Die Nutzlast, aus der die Zahlen dieses Moduls stammen, ist der Live-Abruf
des o2-Katalogs vom 03.09.2026, zitiert in `docs/STRATEGY_GERAETE_TCO.md`
(Abschnitt 1.3):

    {"oneTimePrice": 1, "monthlyPrice": 30.0, "totalPrice": 721.0,
     "activationFee": 0}

1 + 24 x 30 = 721. Die verlinkte Produktseite sagt dasselbe woertlich:
"Geraet Anzahlung: 1,00 EUR", "(Gesamtpreis Geraet: 721,00 EUR)".

KEIN NETZ. Die Saetze stehen als gekuerzte Nutzlast im Modul; die volle
Fixture (`o2_katalog.json`, echter Abruf vom 28.08.2026) traegt dieselbe
Struktur und wird fuer den Weg durch die Sammelschicht benutzt.
"""
import json
from pathlib import Path

import pytest

from telco_radar.analyze.geraete_store import GeraeteDB, Preishistorie
from telco_radar.collect.geraete import o2, sammle_anbieter
from telco_radar.collect.geraete.robots import RobotsWaechter
from telco_radar.geraete_config import (Anbieter, Einstieg, lade_farben,
                                        lade_katalog)
from telco_radar.geraete_model import (lies_listung, ratenhinweis,
                                       ratenhinweis_aus_eintrag)
from telco_radar.report import geraete_vergleich, geraete_view

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_WURZEL = Path(__file__).parent.parent

# Der gemessene Satz vom 03.09.2026, auf die Felder gekuerzt, die dieser
# Adapter liest. `description` und `offerName` stehen woertlich so im
# Katalog - der Angebotsname traegt die Ratenzahl als Suffix `-24xhigh`.
_IPHONE_14 = {
    "externalId": "4510 300000 00",
    "description": "Apple iPhone 14",
    "offerName": "privatkunden-apple-iphone-14-128gb-mitternacht-24xhigh",
    "price": {"oneTimePrice": 1, "monthlyPrice": 30.0, "totalPrice": 721.0,
              "activationFee": 0},
    "detailWwwAbsoluteCall": {"constantPayload": {"link": {
        "uri": "https://www.o2online.de/e-shop/apple/"
               "apple-iphone-14-128gb-mitternacht-details?ohne-tarif=ja"}}},
}


def _katalogantwort(*hardware) -> str:
    return json.dumps({"hardware": list(hardware)})


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(_WURZEL)


@pytest.fixture(scope="module")
def farben():
    return lade_farben(_WURZEL)


# --------------------------------------------------------------------------
# Der Adapter liest die Struktur, nicht nur die Summe
# --------------------------------------------------------------------------

def test_o2_liest_anzahlung_rate_und_laufzeit():
    """1 EUR + 24 x 30 EUR = 721 EUR - alle vier Zahlen, nicht nur die letzte."""
    satz = o2.lies(_katalogantwort(_IPHONE_14))[0]
    assert satz["preis"] == 721.0
    assert satz["anzahlung"] == 1.0
    assert satz["monatsrate"] == 30.0
    assert satz["laufzeit_monate"] == 24
    assert satz["anzahlung"] + 24 * satz["monatsrate"] == satz["preis"]


def test_o2_traegt_die_belegten_null_prozent():
    """o2 weist den Finanzierungshinweis auf der Produktseite aus ("Der
    Sollzins liegt bei 0 %, der effektive Jahreszins bei 0 %"). 0.0 heisst
    hier BELEGT null - nicht "unbekannt"."""
    satz = o2.lies(_katalogantwort(_IPHONE_14))[0]
    assert satz["zins_effektiv"] == 0.0


def test_o2_verwirft_die_laufzeit_wenn_die_rechenprobe_nicht_aufgeht():
    """Lieber kein Etikett als ein falsches.

    Der Modulkopf des Adapters nennt die Probe seit dem 28.08.2026 als
    Messbefund (92 von 93 Eintraegen gehen auf); hier ist sie die Bedingung.
    Geht sie nicht auf, steht die Zahl unetikettiert da statt mit einer
    Ratenzahl, die sie nicht belegt.
    """
    kaputt = dict(_IPHONE_14,
                  price=dict(_IPHONE_14["price"], totalPrice=999.0))
    satz = o2.lies(_katalogantwort(kaputt))[0]
    assert satz["preis"] == 999.0, "der Preis bleibt, was die Quelle sagt"
    assert satz["laufzeit_monate"] is None
    assert satz["anzahlung"] is None and satz["monatsrate"] is None
    assert satz["zins_effektiv"] is None


def test_o2_ohne_ratensuffix_im_angebotsnamen_kein_etikett():
    """Die Ratenzahl kommt aus der QUELLE (dem Angebotsnamen), nicht aus
    einer Rueckrechnung. Fehlt sie dort, wird nichts behauptet - auch dann
    nicht, wenn 721 = 1 + 24 x 30 zufaellig aufginge."""
    ohne = dict(_IPHONE_14,
                offerName="privatkunden-apple-iphone-14-128gb-mitternacht")
    satz = o2.lies(_katalogantwort(ohne))[0]
    assert satz["preis"] == 721.0
    assert satz["laufzeit_monate"] is None


def test_o2_ohne_monatsrate_kein_etikett():
    ohne = dict(_IPHONE_14, price={"oneTimePrice": 1, "totalPrice": 721.0})
    satz = o2.lies(_katalogantwort(ohne))[0]
    assert satz["preis"] == 721.0
    assert satz["laufzeit_monate"] is None


# --------------------------------------------------------------------------
# Die Formulierung steht an einer Stelle
# --------------------------------------------------------------------------

def test_der_hinweis_nennt_ratenzahl_und_belegten_zinssatz():
    assert ratenhinweis(24, 0.0) == "in 24 Raten (0 %)"


def test_ohne_belegten_zinssatz_steht_kein_prozentsatz_da():
    """`None` heisst unbekannt. Ein erfundenes "(0 %)" waere eine Aussage
    ueber einen Vertrag, die niemand gemessen hat."""
    assert ratenhinweis(24) == "in 24 Raten"


def test_ohne_laufzeit_kein_hinweis():
    assert ratenhinweis(None, 0.0) == ""
    assert ratenhinweis(None) == ""


def test_ein_bestandssatz_ohne_die_felder_bekommt_keinen_hinweis():
    """Bestandssaetze aus Laeufen vor dem 03.09.2026 tragen die Felder nicht.
    Sie werden nicht nachtraeglich umgedeutet."""
    assert ratenhinweis_aus_eintrag({"preis_ohne_vertrag": 949.0}) == ""


# --------------------------------------------------------------------------
# Der Weg durch Modell, Sammelschicht und Bestand
# --------------------------------------------------------------------------

def test_die_listung_traegt_die_preisform(katalog, farben):
    listung = lies_listung(
        titel="Apple iPhone 14 128 GB mitternacht", anbieter="o2",
        anbieter_typ="netzbetreiber", quelle_url="https://www.o2online.de/p",
        abgerufen_am="2026-09-03", katalog=katalog, farben=farben,
        preis_ohne_vertrag=721.0, anzahlung=1.0, monatsrate=30.0,
        laufzeit_monate=24, zins_effektiv=0.0)
    assert listung is not None
    assert listung.preisart == "ohne_vertrag", \
        "die vorhandene Preisart bleibt - die Preisform kommt daneben, nicht statt"
    assert listung.preis == 721.0
    assert listung.ratenhinweis == "in 24 Raten (0 %)"


def test_eine_negative_rate_laesst_sich_nicht_bauen(katalog, farben):
    with pytest.raises(ValueError):
        lies_listung(
            titel="Apple iPhone 14 128 GB mitternacht", anbieter="o2",
            anbieter_typ="netzbetreiber", quelle_url="https://www.o2online.de/p",
            abgerufen_am="2026-09-03", katalog=katalog, farben=farben,
            preis_ohne_vertrag=721.0, monatsrate=-30.0, laufzeit_monate=24)


def test_eine_laufzeit_von_null_laesst_sich_nicht_bauen(katalog, farben):
    with pytest.raises(ValueError):
        lies_listung(
            titel="Apple iPhone 14 128 GB mitternacht", anbieter="o2",
            anbieter_typ="netzbetreiber", quelle_url="https://www.o2online.de/p",
            abgerufen_am="2026-09-03", katalog=katalog, farben=farben,
            preis_ohne_vertrag=721.0, monatsrate=30.0, laufzeit_monate=0)


def test_die_sammelschicht_reicht_die_preisform_durch(katalog, farben):
    """Von der Nutzlast bis zur Listung, ohne Netz: `sammle_anbieter` mit
    einer Attrappe, die den gekuerzten Katalog zurueckgibt."""
    nutzlast = _katalogantwort(_IPHONE_14)

    def hole(url, kopfzeilen=None):
        if url.endswith("/robots.txt"):
            return (200, "User-agent: *\n")
        return (200, nutzlast)

    anbieter = Anbieter(
        name="o2", typ="netzbetreiber", methode="o2_katalog",
        basis_url="https://www.o2online.de", rate_limit_sekunden=0,
        kopfzeilen={"Accept": "x"},
        einstiege=[Einstieg(url="https://www.o2online.de/e-shop/rest/catalog/x",
                            kind="static")])
    bilanz = sammle_anbieter(anbieter, katalog, farben, hole, "2026-09-03",
                             RobotsWaechter(hole=hole))
    assert len(bilanz.listungen) == 1
    listung = bilanz.listungen[0]
    assert listung.preis_ohne_vertrag == 721.0
    assert listung.laufzeit_monate == 24
    assert listung.ratenhinweis == "in 24 Raten (0 %)"


def test_der_bestand_haelt_die_preisform_und_verliert_sie_nicht(tmp_path,
                                                                katalog, farben):
    """Ein Lauf, der die Felder nicht messen konnte, loescht sie nicht -
    dieselbe Regel, die fuer die Preisfelder seit jeher gilt."""
    def _listung(**kw):
        return lies_listung(
            titel="Apple iPhone 14 128 GB mitternacht", anbieter="o2",
            anbieter_typ="netzbetreiber", quelle_url="https://www.o2online.de/p",
            abgerufen_am="2026-09-03", katalog=katalog, farben=farben,
            preis_ohne_vertrag=721.0, **kw)

    db = GeraeteDB(tmp_path / "geraete_db.json")
    db.upsert([_listung(anzahlung=1.0, monatsrate=30.0, laufzeit_monate=24,
                        zins_effektiv=0.0)], "2026-09-03")
    eintrag = db.eintraege()[0]
    assert eintrag["laufzeit_monate"] == 24
    assert ratenhinweis_aus_eintrag(eintrag) == "in 24 Raten (0 %)"

    db.upsert([_listung()], "2026-09-04")
    assert db.eintraege()[0]["laufzeit_monate"] == 24, \
        "ein Ausfall der Extraktion ist keine Preisformaenderung"


def test_ein_ANDERER_preis_ohne_ratenfelder_verliert_die_alte_form(
        tmp_path, katalog, farben):
    """Die Form gehoert zu DER Zahl, mit der sie gemessen wurde.

    Steigt o2 bei einem Geraet auf Barkauf um, meldet der Adapter einen
    neuen Preis und KEINE Laufzeit (die Rechenprobe geht dann nicht mehr
    auf). Bliebe die alte Form stehen, traege der frische Barpreis das
    Etikett "in 24 Raten (0 %)" vom Vortag - schlimmer als gar keins.
    """
    def _listung(preis, **kw):
        return lies_listung(
            titel="Apple iPhone 14 128 GB mitternacht", anbieter="o2",
            anbieter_typ="netzbetreiber", quelle_url="https://www.o2online.de/p",
            abgerufen_am="2026-09-03", katalog=katalog, farben=farben,
            preis_ohne_vertrag=preis, **kw)

    db = GeraeteDB(tmp_path / "geraete_db.json")
    db.upsert([_listung(721.0, anzahlung=1.0, monatsrate=30.0,
                        laufzeit_monate=24, zins_effektiv=0.0)], "2026-09-03")
    assert ratenhinweis_aus_eintrag(db.eintraege()[0]) == "in 24 Raten (0 %)"

    db.upsert([_listung(949.0)], "2026-09-04")
    eintrag = db.eintraege()[0]
    assert eintrag["preis_ohne_vertrag"] == 949.0
    for feld in ("anzahlung", "monatsrate", "laufzeit_monate", "zins_effektiv"):
        assert feld not in eintrag, f"{feld} beschreibt einen alten Preis"
    assert ratenhinweis_aus_eintrag(eintrag) == ""


def test_ein_negativer_zinssatz_kommt_nicht_in_den_bestand(katalog, farben):
    """Ein Anbieter, der bei der Ratenzahlung draufzahlt, ist ein
    Vorzeichenfehler in der Quelle - dieselbe Sicherung wie bei jedem
    anderen Geldfeld der Listung."""
    with pytest.raises(ValueError, match="zins_effektiv"):
        lies_listung(
            titel="Apple iPhone 14 128 GB mitternacht", anbieter="o2",
            anbieter_typ="netzbetreiber", quelle_url="https://www.o2online.de/p",
            abgerufen_am="2026-09-03", katalog=katalog, farben=farben,
            preis_ohne_vertrag=721.0, anzahlung=1.0, monatsrate=30.0,
            laufzeit_monate=24, zins_effektiv=-0.5)


def test_die_preishistorie_wird_nicht_umgedeutet(tmp_path, katalog, farben):
    """Die Aenderungspunkte in `geraete_preise.jsonl` bleiben, was sie sind.

    Die Preisform beschreibt den AKTUELLEN Preis. Wuerde sie in die Historie
    wandern, bekaeme jede Listung im Lauf nach dieser Aenderung einen
    Aenderungspunkt, ohne dass sich ein Preis geaendert hat - eine Kurve, die
    einen Preiskampf zeigt, wo eine Softwareaenderung war.
    """
    listung = lies_listung(
        titel="Apple iPhone 14 128 GB mitternacht", anbieter="o2",
        anbieter_typ="netzbetreiber", quelle_url="https://www.o2online.de/p",
        abgerufen_am="2026-09-03", katalog=katalog, farben=farben,
        preis_ohne_vertrag=721.0, anzahlung=1.0, monatsrate=30.0,
        laufzeit_monate=24, zins_effektiv=0.0)

    historie = Preishistorie(tmp_path / "geraete_preise.jsonl")
    assert historie.schreibe(listung, "2026-09-03") is True
    punkt = historie.letzter(listung.listung_id)
    assert punkt["preis_ohne_vertrag"] == 721.0
    for feld in ("anzahlung", "monatsrate", "laufzeit_monate", "zins_effektiv"):
        assert feld not in punkt

    # Derselbe Preis mit derselben Form: kein zweiter Punkt.
    assert historie.schreibe(listung, "2026-09-04") is False


# --------------------------------------------------------------------------
# Die Ansichten zeigen es
# --------------------------------------------------------------------------

def _bestandssatz(**kw):
    e = {
        "id": "o2--apple-iphone-14-128gb-mitternacht",
        "sku_id": "apple-iphone-14-128gb-mitternacht",
        "device_id": "apple-iphone-14", "anbieter": "o2",
        "anbieter_typ": "netzbetreiber", "netz": "o2", "speicher_gb": 128,
        "farbe_roh": "Mitternacht", "farbe_normalisiert": "schwarz",
        "zustand": "neu", "status": "aktiv", "missed_checks": 0,
        "preis_ohne_vertrag": 721.0, "verfuegbarkeit": "unbekannt",
        "confidence": "hoch", "quelle_url": "https://www.o2online.de/p",
        "abgerufen_am": "2026-09-03",
        "anzahlung": 1.0, "monatsrate": 30.0, "laufzeit_monate": 24,
        "zins_effektiv": 0.0,
    }
    e.update(kw)
    return e


def test_die_katalogzeile_traegt_den_hinweis(katalog):
    zeilen = geraete_view.katalogzeilen([_bestandssatz()], katalog)
    assert zeilen[0]["preis"] == 721.0
    assert zeilen[0]["ratenhinweis"] == "in 24 Raten (0 %)"


def test_ein_barpreis_traegt_keinen_hinweis(katalog):
    bar = _bestandssatz(anbieter="mobilcom-debitel", anbieter_typ="handel",
                        preis_ohne_vertrag=949.0, anzahlung=None,
                        monatsrate=None, laufzeit_monate=None,
                        zins_effektiv=None)
    zeilen = geraete_view.katalogzeilen([bar], katalog)
    assert zeilen[0]["ratenhinweis"] == ""


def test_der_vergleich_stellt_die_zwei_formen_nebeneinander_gekennzeichnet(katalog):
    """Der Vergleich rechnet weiterhin beide gegeneinander - das aendert erst
    die Preisform als First-Class-Datum (Phase 3). Was er JETZT schon tut:
    er sagt an jeder Zahl, welche Form sie hat."""
    bar = _bestandssatz(
        id="freenet--apple-iphone-14-128gb-mitternacht", anbieter="freenet",
        anbieter_typ="handel", preis_ohne_vertrag=649.0, anzahlung=None,
        monatsrate=None, laufzeit_monate=None, zins_effektiv=None,
        quelle_url="https://www.freenet.de/p")
    eigen = _bestandssatz(
        id="vodafone--apple-iphone-14-128gb-mitternacht", anbieter="Vodafone",
        anbieter_typ="netzbetreiber", preis_ohne_vertrag=709.9, anzahlung=None,
        monatsrate=None, laufzeit_monate=None, zins_effektiv=None,
        quelle_url="https://www.vodafone.de/p")
    ergebnis = geraete_vergleich.vergleich([_bestandssatz(), bar, eigen],
                                           katalog)
    zeile = ergebnis["zeilen"][0]
    formen = {a["anbieter"]: a["ratenhinweis"]
              for a in zeile["guenstiger"] + zeile["teurer"]}
    assert formen["o2"] == "in 24 Raten (0 %)"
    assert formen["freenet"] == ""
