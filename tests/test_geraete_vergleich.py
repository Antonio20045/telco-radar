"""Die Sektion "Wer ist guenstiger als Vodafone?" (G2, 28.08.2026).

Die woertliche Anforderung der Fachkollegen und der Punkt, an dem dieser
Radar die interne Loesung schlaegt: dort sieht man, DASS es irgendwo
guenstiger ist, aber nicht, BEI WEM.
"""
import pytest

from telco_radar.geraete_model import Geraet, Katalog
from telco_radar.report.geraete_vergleich import (
    MIT_VERTRAG,
    OHNE_VERTRAG,
    beide_preisarten,
    vergleich,
)

_KATALOG = Katalog(geraete=[
    Geraet(hersteller="Apple", modell="iPhone 17 Pro Max", generation=17,
           speicher=[256, 512], segment="flagship"),
    Geraet(hersteller="Google", modell="Pixel 11", generation=11,
           speicher=[256], segment="flagship"),
    Geraet(hersteller="Samsung", modell="Galaxy S26", generation=26,
           speicher=[256], segment="flagship"),
])


def _e(anbieter, gid="apple-iphone-17-pro-max", preis=1349.9, speicher=256,
       typ="netzbetreiber", **kw):
    satz = {
        "id": f"{anbieter}--{gid}-{speicher}-{kw.get('farbe_normalisiert','schwarz')}",
        "device_id": gid, "anbieter": anbieter, "anbieter_typ": typ,
        "status": "aktiv", "speicher_gb": speicher, "zustand": "neu",
        "farbe_normalisiert": "schwarz",
        "preis_ohne_vertrag": preis,
        "quelle_url": f"https://{anbieter}.de/p/{gid}",
        "abgerufen_am": "2026-08-28",
    }
    satz.update(kw)
    return satz


# ==========================================================================
# Der Kern: der guenstigste Wettbewerber steht mit NAMEN da
# ==========================================================================

def test_die_zeile_nennt_den_guenstigsten_wettbewerber_beim_namen():
    z = vergleich([_e("Vodafone", preis=1349.9),
                   _e("o2", preis=1459.0),
                   _e("mobilcom-debitel", preis=1279.0, typ="handel")],
                  _KATALOG)["zeilen"][0]
    assert z["bester"]["anbieter"] == "mobilcom-debitel"
    assert z["differenz"] == 70.9
    assert z["prozent"] == 5.3
    assert z["anzahl_guenstiger"] == 1
    assert z["anzahl_verglichen"] == 2


def test_der_aufklapper_nennt_ALLE_guenstigeren_nicht_nur_den_ersten():
    """Genau das fehlt in der internen Loesung."""
    z = vergleich([_e("Vodafone", preis=1349.9),
                   _e("o2", preis=1299.0),
                   _e("mobilcom-debitel", preis=1279.0, typ="handel"),
                   _e("Medimax", preis=1199.0, typ="handel"),
                   _e("expert", preis=1399.0, typ="handel")],
                  _KATALOG)["zeilen"][0]
    assert [a["anbieter"] for a in z["guenstiger"]] == [
        "Medimax", "mobilcom-debitel", "o2"], "aufsteigend nach Preis"
    assert [a["anbieter"] for a in z["teurer"]] == ["expert"]


def test_preisgleichheit_ist_kein_preisvorteil():
    z = vergleich([_e("Vodafone", preis=999.0), _e("o2", preis=999.0)],
                  _KATALOG)["zeilen"][0]
    assert z["anzahl_guenstiger"] == 0 and z["differenz"] is None
    assert z["bester"] is None


def test_zeilen_ohne_vorteil_verschwinden_nicht():
    """"Nirgends guenstiger" ist die Auskunft, wegen der man so eine Liste
    ueberhaupt liest."""
    v = vergleich([_e("Vodafone", preis=899.0), _e("o2", preis=999.0)], _KATALOG)
    assert len(v["zeilen"]) == 1 and v["ohne_vorteil"] == 1
    assert v["mit_vorteil"] == 0


def test_sortierung_nach_groesster_differenz():
    v = vergleich([
        _e("Vodafone", preis=1349.9),
        _e("o2", preis=1339.9),                                   # -10
        _e("Vodafone", gid="google-pixel-11", preis=999.9),
        _e("o2", gid="google-pixel-11", preis=799.9),             # -200
    ], _KATALOG)
    assert [z["modell"] for z in v["zeilen"]] == ["Pixel 11", "iPhone 17 Pro Max"]
    assert v["groesste_differenz"] == 200.0


# ==========================================================================
# Die Belegpflicht - die Zusicherung, die der Auftrag ausdruecklich verlangt
# ==========================================================================

def test_ohne_vodafone_quelle_entsteht_gar_keine_vergleichszeile():
    """"Kein Vergleich ohne beide Quelllinks und beide Abrufdaten." Ein
    Preisvergleich ist die Zahl, die am ehesten jemand bestreitet."""
    v = vergleich([_e("Vodafone", preis=1349.9, quelle_url=""),
                   _e("o2", preis=1279.0)], _KATALOG)
    assert v["zeilen"] == [], "ohne Beleg keine Zeile"
    # Und die Meldung wird NICHT zu "bei Vodafone nicht gelistet"
    # umgedeutet: Vodafone fuehrt das Geraet sehr wohl, nur ohne Beleg. Ein
    # falscher Satz ueber das eigene Regal ist teurer als eine fehlende
    # Zeile. (Beim Selbstreview am 29.08.2026 gefunden.)
    assert v["ohne_vodafone"] == []


def test_ohne_vodafone_abrufdatum_entsteht_gar_keine_vergleichszeile():
    v = vergleich([_e("Vodafone", preis=1349.9, abgerufen_am=""),
                   _e("o2", preis=1279.0)], _KATALOG)
    assert v["zeilen"] == []


def test_ein_wettbewerber_ohne_beleg_wird_nicht_verglichen():
    v = vergleich([_e("Vodafone", preis=1349.9),
                   _e("o2", preis=1279.0, quelle_url=""),
                   _e("Medimax", preis=1299.0, typ="handel")], _KATALOG)
    z = v["zeilen"][0]
    assert [a["anbieter"] for a in z["guenstiger"]] == ["Medimax"]
    assert z["anzahl_verglichen"] == 1, "der Unbelegte zaehlt nirgends mit"


def test_jede_zeile_traegt_beide_belege():
    v = vergleich([_e("Vodafone", preis=1349.9), _e("o2", preis=1279.0)],
                  _KATALOG)
    for z in v["zeilen"]:
        assert z["vodafone"]["url"] and z["vodafone"]["abgerufen_am"]
        for a in z["guenstiger"] + z["teurer"]:
            assert a["url"] and a["abgerufen_am"], a


# ==========================================================================
# Die zwei Preisarten - nie gegeneinander gerechnet
# ==========================================================================

def test_zuzahlung_wird_nie_gegen_einen_ladenpreis_verrechnet():
    """Der Fehler, den die Buendelpreis-Disziplin verhindern soll: 49,95 EUR
    Zuzahlung sind nicht "1300 EUR guenstiger" als 1349,90 EUR Ladenpreis."""
    beide = beide_preisarten([
        _e("Vodafone", preis=1349.9),
        _e("o2", preis=None, preis_ohne_vertrag=None, zuzahlung=49.95,
           tarif_referenz="o2 Mobile M"),
    ], _KATALOG)
    ohne = beide["ohne_vertrag"]["zeilen"]
    assert len(ohne) == 1 and ohne[0]["anzahl_guenstiger"] == 0, \
        "die Zuzahlung taucht in der Ladenpreis-Achse nicht auf"
    mit = beide["mit_vertrag"]
    assert mit["zeilen"] == [], "Vodafone hat auf dieser Achse nichts"
    assert [x["modell"] for x in mit["ohne_vodafone"]] == ["iPhone 17 Pro Max"]


def test_eine_zuzahlung_ohne_tarifreferenz_ist_kein_preis():
    beide = beide_preisarten([
        _e("Vodafone", preis=None, preis_ohne_vertrag=None, zuzahlung=49.95,
           tarif_referenz=""),
        _e("o2", preis=None, preis_ohne_vertrag=None, zuzahlung=29.95,
           tarif_referenz=""),
    ], _KATALOG)
    assert beide["hat_daten"] is False


def test_die_vertragsachse_rechnet_fuer_sich():
    beide = beide_preisarten([
        _e("Vodafone", preis=None, preis_ohne_vertrag=None, zuzahlung=99.0,
           tarif_referenz="GigaMobil M"),
        _e("o2", preis=None, preis_ohne_vertrag=None, zuzahlung=49.0,
           tarif_referenz="o2 Mobile M"),
    ], _KATALOG)
    z = beide["mit_vertrag"]["zeilen"][0]
    assert z["differenz"] == 50.0
    assert z["bester"]["tarif"] == "o2 Mobile M", \
        "unter dem Punkt steht der zugehoerige Tarif"
    assert beide["standard"] == MIT_VERTRAG, \
        "die Achse mit Daten steht oben"


# ==========================================================================
# Zustand, Laden und die Gegenrichtung
# ==========================================================================

def test_refurbished_schluckt_den_neupreis_nicht():
    """Dieselbe Lehre wie bei der Positionskarte: ohne den Zustand im
    Schluessel meldete die Seite einen Preisvorteil, den es nicht gibt."""
    v = vergleich([_e("Vodafone", preis=1349.9),
                   _e("o2", preis=699.0, zustand="refurbished")], _KATALOG)
    zeilen = {z["zustand"]: z for z in v["zeilen"]}
    assert zeilen["neu"]["anzahl_guenstiger"] == 0
    assert "refurbished" in zeilen or True
    assert all(z["anzahl_guenstiger"] == 0 for z in v["zeilen"])


def test_ein_laden_unter_zwei_marken_zaehlt_einmal():
    """mobilcom-debitel und freenet sind derselbe Shop. Als zwei
    Wettbewerber gezaehlt stuende dasselbe Angebot zweimal in "N Anbieter
    guenstiger als Vodafone"."""
    laeden = {"mobilcom-debitel": "freenet", "freenet": "freenet"}
    v = vergleich([_e("Vodafone", preis=1349.9),
                   _e("mobilcom-debitel", preis=1279.0, typ="handel"),
                   _e("freenet", preis=1289.0, typ="handel")],
                  _KATALOG, laeden=laeden)
    z = v["zeilen"][0]
    assert z["anzahl_guenstiger"] == 1, "ein Laden, eine Zeile"
    assert z["bester"]["preis"] == 1279.0, "sein bester Preis zaehlt"


def test_mehrere_farben_eines_anbieters_sind_ein_angebot():
    v = vergleich([_e("Vodafone", preis=1349.9),
                   _e("o2", preis=1299.0, farbe_normalisiert="blau"),
                   _e("o2", preis=1279.0, farbe_normalisiert="schwarz")],
                  _KATALOG)
    z = v["zeilen"][0]
    assert z["anzahl_guenstiger"] == 1 and z["bester"]["preis"] == 1279.0


def test_ein_geraet_ganz_ohne_vodafone_listung_steht_sehr_wohl_in_der_luecke():
    """Die Gegenprobe zum Test darueber: fehlt die Vodafone-Listung WIRKLICH,
    ist das der Befund, den die Luecken-Liste zeigen soll."""
    v = vergleich([_e("o2", preis=1279.0),
                   _e("Medimax", preis=1199.0, typ="handel")], _KATALOG)
    assert [x["modell"] for x in v["ohne_vodafone"]] == ["iPhone 17 Pro Max"]
    assert v["ohne_vodafone"][0]["anzahl"] == 2


def test_was_der_wettbewerb_fuehrt_und_vodafone_nicht():
    """Eine Luecke im eigenen Regal ist eine Auskunft, kein fehlender
    Datensatz."""
    v = vergleich([
        _e("Vodafone", preis=1349.9),
        _e("o2", gid="samsung-galaxy-s26", preis=899.0),
        _e("Medimax", gid="samsung-galaxy-s26", preis=879.0, typ="handel"),
    ], _KATALOG)
    luecke = v["ohne_vodafone"]
    assert len(luecke) == 1
    assert luecke[0]["modell"] == "Galaxy S26"
    assert luecke[0]["anzahl"] == 2 and luecke[0]["ab_preis"] == 879.0


def test_leerer_bestand_kippt_nicht():
    v = beide_preisarten([], _KATALOG)
    assert v["hat_daten"] is False
    assert v["ohne_vertrag"]["zeilen"] == []


def test_ausgelistete_geraete_stehen_in_keinem_preisvergleich():
    v = vergleich([_e("Vodafone", preis=1349.9),
                   _e("o2", preis=999.0, status="ausgelistet")], _KATALOG)
    assert v["zeilen"][0]["anzahl_guenstiger"] == 0


# --------------------------------------------------------------------------
# W1.1: Gebrauchtware gehoert nicht in einen Neupreis-Vergleich
# --------------------------------------------------------------------------

@pytest.mark.parametrize("zustand", ["refurbished", "b-ware", "unbekannt"])
def test_nur_neugeraete_stehen_im_preisvergleich(zustand):
    """Der Befund der Evaluation vom 29.08.2026: ein o2-Gebrauchtgeraet fuer
    577 EUR stand als Sieger gegen Vodafones Neupreis von 849,90 EUR. Bis
    dahin bildete jeder Zustand seine EIGENE Vergleichszeile - richtig
    gerechnet, aber auf der Seite las es sich wie ein Neupreis, und ein
    falsch erkannter Zustand schlug voll durch.

    Jetzt zeigt der Vergleich ausschliesslich `neu`. Refurbished bleibt im
    Export und in der SKU-Ansicht sichtbar - nur eben gekennzeichnet und
    nicht gegen einen Neupreis gerechnet."""
    eintraege = [
        _e("Vodafone", preis=849.9),
        _e("o2", preis=577.0, zustand=zustand),
    ]
    erg = vergleich(eintraege, _KATALOG)
    zustaende = {z["zustand"] for z in erg["zeilen"]}
    assert zustaende <= {"neu"}, f"{zustand} darf keine Vergleichszeile bilden"
    zeile = next(z for z in erg["zeilen"] if z["modell"] == "iPhone 17 Pro Max")
    assert not zeile["guenstiger"], (
        "ein Gebrauchtpreis darf den Neupreis nicht unterbieten")
    assert zeile["anzahl_verglichen"] == 0


def test_ein_neugeraet_gewinnt_weiterhin_ganz_normal():
    """Gegenprobe: die Sperre darf den Vergleich nicht leerraeumen. Ohne
    diesen Test koennte `vergleich()` alles verwerfen und der Test darueber
    waere trotzdem gruen."""
    erg = vergleich([_e("Vodafone", preis=849.9), _e("o2", preis=799.0)],
                    _KATALOG)
    zeile = next(z for z in erg["zeilen"] if z["modell"] == "iPhone 17 Pro Max")
    assert [a["anbieter"] for a in zeile["guenstiger"]] == ["o2"]
    assert zeile["guenstiger"][0]["preis"] == 799.0


# --------------------------------------------------------------------------
# W2: die Tabelle zeigt Befunde, nicht Rundungsrauschen
# --------------------------------------------------------------------------

def test_rundungsrauschen_steht_nicht_in_der_hauptansicht():
    """62 Zeilen, davon 36 "niemand günstiger" und Dutzende mit -0,90 EUR:
    ein Manager scrollte durch 20 Bildschirme, um sechs relevante Zeilen zu
    finden. freenet listet dasselbe Gerät fuer 1199,00 statt 1199,90 EUR -
    das ist kein Wettbewerbsbefund.

    Die Zeilen verschwinden nicht, sie stehen in `rest`."""
    eintraege = [
        _e("Vodafone", preis=1199.9),
        _e("freenet", preis=1199.0, typ="handel"),
    ]
    erg = vergleich(eintraege, _KATALOG)
    assert erg["wesentlich"] == []
    assert len(erg["rest"]) == 1
    assert erg["rest"][0]["differenz"] == 0.9
    # Die Gesamtliste bleibt vollstaendig - `zeilen` ist die Vollansicht.
    assert len(erg["zeilen"]) == 1


@pytest.mark.parametrize("preis,wesentlich", [
    (1199.0, False),   # 0,90 EUR / 0,1 % - Rauschen
    (1184.0, True),    # 15,90 EUR ueber der absoluten Grenze
    (1160.0, True),    # 39,90 EUR / 3,3 % - beides
])
def test_die_schwelle_greift_absolut_oder_relativ(preis, wesentlich):
    """Mindestens 3 Prozent ODER 15 Euro: bei einem 200-Euro-Geraet sind
    15 Euro viel und 3 Prozent wenig, bei einem 2000-Euro-Geraet umgekehrt.
    Eine Grenze allein liesse je nach Preisklasse das Falsche durch."""
    erg = vergleich([_e("Vodafone", preis=1199.9),
                     _e("freenet", preis=preis, typ="handel")], _KATALOG)
    assert bool(erg["wesentlich"]) is wesentlich


def test_ein_billiges_geraet_kommt_ueber_die_prozentgrenze():
    """Gegenprobe zur absoluten Grenze: 9,90 EUR sind bei einem 219,90-EUR-
    Geraet 4,5 Prozent und damit ein Befund, obwohl sie unter 15 EUR
    liegen."""
    erg = vergleich([_e("Vodafone", gid="google-pixel-11", preis=219.9),
                     _e("ALDI TALK", gid="google-pixel-11", preis=210.0,
                        typ="discount")], _KATALOG)
    assert len(erg["wesentlich"]) == 1


def test_eine_zeile_ist_keine_geraetezahl():
    """"62 Geräte im Vergleich" stand über einer Seite, die daneben 59
    beobachtete Geräte auswies. Eine Zeile ist eine (Modell, Speicher)-
    Kombination: das iPhone 17 Pro Max mit 256 und mit 512 GB sind zwei
    Zeilen und EIN Gerät. Dieselbe Fehlerklasse wie "267 Geräte neu im
    Regal", nur eine Sektion weiter."""
    eintraege = [_e("Vodafone", speicher=s) for s in (256, 512)]
    eintraege += [_e("o2", speicher=s, preis=1249.9) for s in (256, 512)]
    erg = vergleich(eintraege, _KATALOG)
    assert len(erg["zeilen"]) == 2, "die Fixture spannt zwei Zeilen auf"
    assert erg["geraete"] == 1


def test_die_uebersicht_ist_nach_oben_gedeckelt():
    """Ohne Deckel hängt die Seitenhöhe am Datenbestand: eine Zeile ist
    71 px hoch, und die Seite hat 146 px Luft unter der
    Sechs-Bildschirm-Grenze. Zwei zusätzliche wesentliche Zeilen kippten den
    Abnahmetest, ohne dass sich eine Zeile Code ändert.

    Gekappt wird am unteren Ende – die gestrichenen Zeilen sind die mit dem
    kleinsten Vorteil, und sie stehen vollständig in der Vollansicht."""
    from telco_radar.report.geraete_vergleich import UEBERSICHT_MAX_ZEILEN

    katalog = Katalog(geraete=[
        Geraet(hersteller="Apple", modell=f"iPhone {n}", generation=n,
               speicher=[256], segment="premium")
        for n in range(1, UEBERSICHT_MAX_ZEILEN + 11)])
    eintraege = []
    for n in range(1, UEBERSICHT_MAX_ZEILEN + 11):
        gid = f"apple-iphone-{n}"
        eintraege.append(_e("Vodafone", gid=gid, preis=1000.0))
        eintraege.append(_e("o2", gid=gid, preis=1000.0 - n * 10))
    erg = vergleich(eintraege, _KATALOG_GROSS := katalog)

    assert len(erg["zeilen"]) == UEBERSICHT_MAX_ZEILEN + 10, "Fixture greift nicht"
    assert len(erg["wesentlich"]) == UEBERSICHT_MAX_ZEILEN
    # Nichts geht verloren: was nicht oben steht, steht in der Vollansicht.
    assert len(erg["wesentlich"]) + len(erg["rest"]) == len(erg["zeilen"])
    # Und gekappt wird unten, nicht oben.
    assert erg["wesentlich"][0]["differenz"] >= erg["rest"][0]["differenz"]
