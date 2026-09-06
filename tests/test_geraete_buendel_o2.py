"""Die zweite Lesart des o2-Katalogs: Geraet PLUS Tarif.

WAS HIER GEPRUEFT WIRD, UND WARUM ES EINE EIGENE DATEI IST
-----------------------------------------------------------
`geraete_db.json` sammelt Listungen, `geraete_tco.json` sammelt Buendel.
Das sind zwei Datensaetze mit zwei Namensmengen und zwei Regeln, und die
teuerste Verwechslung dieses Projekts war, einen Buendelbetrag in die
Spalte eines Kassenpreises zu schreiben. Die Buendelstrecke laeuft
deshalb an der Listungsstrecke VORBEI (`kind: buendel`), und diese Datei
haelt genau das fest.

DIE FIXTURE IST EIN GESPEICHERTER ECHTER ABRUF
----------------------------------------------
`tests/fixtures/geraete/o2_katalog_buendel.json.gz` ist die rohe,
ungekuerzte Antwort auf die Adresse, die `/e-shop/` in seiner eigenen
Nutzlast ausgibt - dieselbe wie die produktive, nur ohne `?hwOnly=true`
(04.09.2026, HTTP 200, 583.104 Bytes, Absender `TelcoRadar/1.0`,
`Accept: application/vnd.commerce.message+json`). Herkunft und sha256 des
entpackten Inhalts stehen in `tests/fixtures/geraete/_herkunft.json`.

DIE DREI RECHENPROBEN
---------------------
Die Aufteilung in Geraeterate und Tarifbetrag steht bei o2 nur im
Trackingblock der Antwort. Ein Trackingfeld ist kein Preisfeld, deshalb
wird ihm nichts geglaubt, was sich nicht gegen die typisierten Zahlen
DERSELBEN Antwort nachrechnen laesst - und die Proben sind Bedingung,
nicht Protokoll. Die Tests unten loesen jede einzeln aus.
"""
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from telco_radar.analyze.tco_buendel import aus_rohsaetzen
from telco_radar.collect.geraete import GeraeteAbrufFehler
from telco_radar.collect.geraete.o2 import lies_buendel
from telco_radar.tarif_bezug import Tarifbestand
from telco_radar.tarif_model import HOCH
from telco_radar.tco_model import TCO_HORIZONT, tco_24

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_DATEI = "o2_katalog_buendel.json.gz"
_URL = ("https://www.o2online.de/e-shop/rest/catalog/o2shop/privatkunden/"
        "ratenzahlung/default/__not-specified__/__not-specified__/"
        "__not-specified__")


def _katalog() -> str:
    with gzip.open(_FIX / _DATEI, "rt", encoding="utf-8") as fh:
        return fh.read()


def _saetze():
    return lies_buendel(_katalog(), _URL)


def _eintrag(beschreibung="Apple iPhone 15 Pro",
             angebot="privatkunden-apple-iphone-15-pro-128gb-titan-natur-36xhigh",
             einmalig=1.0, monatlich=48.99, gesamt=1764.64, anschluss=39.99,
             dauer="36 Monate", tarif="O<sub>2</sub> Mobile on Demand M Plus",
             geraet_mtl="34.0", tarif_mtl="14.99", anzahlung="1",
             anschluss_track="39.99", slug="o2-mobile-on-demand-m-plus"):
    """Ein Katalogeintrag in der Form, die o2 wirklich ausliefert."""
    return {
        "description": beschreibung, "offerName": angebot,
        "rateDurationValue": dauer,
        "price": {"oneTimePrice": einmalig, "monthlyPrice": monatlich,
                  "totalPrice": gesamt, "activationFee": anschluss},
        "bundle": {"tariffName": tarif,
                   "tariffOfferName": f"privatkunden-{slug}-online-hwv"},
        "ecommerceProductValue": {"attributes": {
            "metric3": geraet_mtl, "metric2": tarif_mtl, "metric5": anzahlung,
            "metric4": anschluss_track, "dimension59": slug}},
        "detailWwwAbsoluteCall": {"constantPayload": {"link": {
            "uri": "https://www.o2online.de/e-shop/apple/x-details?tarif=y"}}},
    }


def _antwort(*eintraege, zustand="BUNDLE"):
    return json.dumps({
        "hardware": list(eintraege),
        "hwCatalogSwitcherStateValue": {
            "hwOnlyOrBundleSwitcherValue": {
                "hwOnlyOrBundleState": {"name": zustand}}}})


# --------------------------------------------------------------------------
# Die gemessene Antwort
# --------------------------------------------------------------------------

def test_sechsundsechzig_buendel_aus_achtundachtzig_eintraegen():
    """22 der 88 sind Geraet PLUS Zubehoer und fallen heraus."""
    roh = json.loads(_katalog())
    assert len(roh["hardware"]) == 88
    assert len(_saetze()) == 66


def test_jedes_buendel_traegt_seine_vier_posten():
    for satz in _saetze():
        assert satz["geraet_zuzahlung"] is not None
        assert satz["geraet_monatsrate"] is not None
        assert satz["tarif_monatlich"] is not None
        assert satz["anschlusspreis"] is not None
        assert satz["laufzeit_monate"] == 36
        assert satz["tarif_name"] and satz["tarif_slug"]


def test_die_aufteilung_ergibt_wieder_den_monatsbetrag():
    """Die Probe, die dem Trackingblock ueberhaupt erst Glauben schenkt.

    Gerechnet gegen die TYPISIERTEN Zahlen derselben Antwort: die Summe
    aus Geraeterate und Tarifbetrag muss `price.monthlyPrice` sein.
    """
    je_sku = {h["externalId"]: h for h in json.loads(_katalog())["hardware"]}
    saetze = _saetze()
    # Die Zeile, ohne die dieser Test nichts prueft: trifft der Schluessel
    # nicht, ist die Schleife leer und `assert` in ihr nie ausgefuehrt.
    assert len(saetze) == 66
    for satz in saetze:
        h = je_sku[satz["sku"]]
        summe = satz["geraet_monatsrate"] + satz["tarif_monatlich"]
        assert abs(summe - h["price"]["monthlyPrice"]) < 0.005
        assert abs(satz["geraet_zuzahlung"]
                   - h["price"]["oneTimePrice"]) < 0.005
        assert abs(satz["anschlusspreis"]
                   - h["price"]["activationFee"]) < 0.005


def test_der_name_kommt_ohne_markup_an():
    """`O<sub>2</sub>` im Datenfeld waere sichtbares Markup auf der Seite."""
    namen = {s["tarif_name"] for s in _saetze()}
    assert namen == {
        "O2 Mobile L Plus mit 150 GB+ (24 Mon.)",
        "O2 Mobile on Demand M Plus mit 50 GB+ (24 Mon.)",
        "O2 Mobile on Demand M mit 50 GB+ (24 Mon.)"}
    assert not any("<" in n for n in namen)


def test_die_fixture_ist_der_unveraenderte_abruf():
    eintrag = [e for e in json.loads((_FIX / "_herkunft.json").read_text(
        encoding="utf-8"))["eintraege"] if e["datei"] == _DATEI]
    assert len(eintrag) == 1
    roh = gzip.open(_FIX / _DATEI, "rb").read()
    assert hashlib.sha256(roh).hexdigest() == eintrag[0]["sha256_roh"]
    assert len(roh) == eintrag[0]["bytes_roh"] == 583104
    assert eintrag[0]["http_status"] == 200
    # Die Adresse unterscheidet sich von der produktiven NUR im fehlenden
    # `?hwOnly=true` - beide gibt /e-shop/ selbst aus.
    assert eintrag[0]["url"] == _URL


# --------------------------------------------------------------------------
# Was NICHT hereinkommt
# --------------------------------------------------------------------------

def test_eine_hw_only_antwort_wirft_statt_leer_zu_liefern():
    """Ein leeres Ergebnis waere hier die falsche Meldung.

    Steht der Umschalter auf HW_ONLY, hat sich die Nutzlast geaendert -
    und ihre 95 Geraete als Buendel zu lesen ergaebe 95 Saetze ohne Tarif.
    Dieselbe Unterscheidung wie ueberall: ein gescheiterter Abruf ist
    nicht "nichts gefunden".
    """
    with pytest.raises(GeraeteAbrufFehler, match="HW_ONLY"):
        lies_buendel(_antwort(_eintrag(), zustand="HW_ONLY"))


def test_unlesbare_nutzlast_wirft():
    with pytest.raises(GeraeteAbrufFehler):
        lies_buendel("kein json")
    with pytest.raises(GeraeteAbrufFehler):
        lies_buendel(json.dumps({"foo": []}))


def test_zubehoerbuendel_faellt_heraus():
    mit = _eintrag(beschreibung="Apple iPhone 17 Pro Max mit AirPods Pro 3")
    assert lies_buendel(_antwort(mit)) == []


def test_ohne_tarifnamen_kein_buendel():
    """Eine Buendelzahl ohne ihren Vertrag ist bedeutungslos - dieselbe
    Regel wie in `Listung` und `Buendel`."""
    assert lies_buendel(_antwort(_eintrag(tarif=""))) == []


@pytest.mark.parametrize("feld,wert", [
    ("geraet_mtl", "30.0"),        # Summe trifft monthlyPrice nicht mehr
    ("tarif_mtl", "10.0"),
    ("anzahlung", "5"),            # widerspricht oneTimePrice
    ("anschluss_track", "0.0"),    # widerspricht activationFee
])
def test_ein_trackingblock_der_der_preisstruktur_widerspricht_faellt(feld, wert):
    """Jede der drei Proben einzeln ausgeloest.

    Ohne diese Zeilen glaubte der Adapter einem Feld, das die Seite fuer
    ihre Webanalyse fuellt - und schriebe eine Geraeterate in den Bestand,
    die mit dem Monatsbetrag daneben nicht zusammenpasst.
    """
    assert lies_buendel(_antwort(_eintrag(**{feld: wert}))) == []


def test_ohne_trackingblock_kein_buendel():
    """Kein Rueckfall auf `monthlyPrice` als Geraeterate.

    Der Monatsbetrag ist die SUMME. Ihn als Geraeterate zu speichern
    hiesse, den Tarif ein zweites Mal zu berechnen - und die TCO-Rechnung
    addiert ihn daneben noch einmal.
    """
    ohne = _eintrag()
    ohne["ecommerceProductValue"] = {}
    assert lies_buendel(_antwort(ohne)) == []


def test_eine_laufzeit_die_nicht_aufgeht_faellt():
    """`anzahlung + n x monatlich == totalPrice`, sonst kein Satz."""
    assert lies_buendel(_antwort(_eintrag(gesamt=1500.0))) == []
    assert lies_buendel(_antwort(_eintrag(dauer="ohne Angabe"))) == []


# --------------------------------------------------------------------------
# Vom Rohsatz zum Buendel
# --------------------------------------------------------------------------

def _bestand():
    """Der Tarifbestand, wie ihn die o2-Kacheln schreiben."""
    return Tarifbestand([
        {"tarif_id": "o2:o2-mobile-on-demand-m", "anbieter": "o2",
         "name": "O2 Mobile on Demand M", "grundgebuehr": 19.99,
         "buendel_slug": "o2-mobile-on-demand-m-plus"},
        {"tarif_id": "o2:o2-mobile-l", "anbieter": "o2",
         "name": "O2 Mobile L", "grundgebuehr": 24.99,
         "buendel_slug": "o2-mobile-l-plus"},
    ])


def _rohsatz(**kw):
    satz = {"sku_id": "apple-iphone-15-pro-128gb-titan-natur",
            "anbieter": "o2",
            "tarif_name": "O2 Mobile on Demand M Plus mit 50 GB+ (24 Mon.)",
            "tarif_slug": "o2-mobile-on-demand-m-plus",
            "tarif_monatlich": 14.99, "geraet_zuzahlung": 1.0,
            "geraet_monatsrate": 34.0, "anschlusspreis": 39.99,
            "laufzeit_monate": 36,
            "quelle_url": "https://www.o2online.de/e-shop/apple/x-details"}
    satz.update(kw)
    return satz


def test_der_slug_traegt_die_zuordnung():
    """Ueber den Namen loest hier NICHTS auf, und das ist richtig so."""
    bilanz = aus_rohsaetzen([_rohsatz()], _bestand(), "2026-09-04")
    assert len(bilanz.buendel) == 1
    buendel = bilanz.buendel[0]
    assert buendel.tarif_id == "o2:o2-mobile-on-demand-m"
    assert buendel.tarif_id_guete == HOCH
    # Der NAME bleibt der des Anbieters - laufen die zwei auseinander, ist
    # genau das die Auskunft.
    assert buendel.tarif_name.startswith("O2 Mobile on Demand M Plus")


def test_ohne_aufloesbaren_tarif_wird_verworfen_und_gezaehlt():
    """Verworfen, nicht gespeichert - und der Grund steht in der Bilanz.

    `TcoDB.upsert_buendel` wuerde bei einem Satz ohne `tarif_id` werfen und
    damit die ganze Uebergabe kosten. Hier faellt einer, die uebrigen
    bleiben.
    """
    bilanz = aus_rohsaetzen(
        [_rohsatz(), _rohsatz(tarif_slug="gibts-nicht",
                              tarif_name="O2 Irgendwas")],
        _bestand(), "2026-09-04")
    assert len(bilanz.buendel) == 1
    assert bilanz.ohne_tarif == 1
    assert bilanz.offene_tarife == {"O2 Irgendwas": 1}


def test_ohne_sku_wird_verworfen():
    """Ein Buendel ohne Geraet waere die SIM-only-Referenz eines Tarifs -
    und die entsteht aus dem Tarifbestand, nicht aus einer Geraetenutzlast."""
    bilanz = aus_rohsaetzen([_rohsatz(sku_id="")], _bestand(), "2026-09-04")
    assert bilanz.buendel == [] and bilanz.ohne_geraet == 1


def test_ein_unmoeglicher_posten_kostet_nicht_die_uebrigen():
    bilanz = aus_rohsaetzen(
        [_rohsatz(), _rohsatz(geraet_monatsrate=-1.0), "kein dict"],
        _bestand(), "2026-09-04")
    assert len(bilanz.buendel) == 1
    assert bilanz.ungueltig == 2


def test_die_rechenprobe_der_tco_am_echten_satz():
    """Die Zahl, die am Ende auf der Seite steht - von Hand nachgerechnet.

    1,00 EUR Zuzahlung + 24 x 34,00 EUR Geraeterate + 24 x 14,99 EUR Tarif
    + 39,99 EUR Anschlusspreis = 1216,75 EUR. Offen bleiben nach 24 Monaten
    zwoelf Geraeteraten = 408,00 EUR - sie fallen NICHT unter den Tisch.
    """
    buendel = aus_rohsaetzen([_rohsatz()], _bestand(), "2026-09-04").buendel[0]
    tco = tco_24(buendel)
    assert tco.belastbar
    assert tco.gesamt == pytest.approx(1.0 + TCO_HORIZONT * (34.0 + 14.99)
                                       + 39.99, abs=0.005)
    assert tco.gesamt == pytest.approx(1216.75, abs=0.005)
    assert tco.restbetrag == pytest.approx(408.0, abs=0.005)


def test_der_ganze_weg_an_der_echten_antwort():
    """Vom gespeicherten Abruf bis zur rechenbaren TCO, ohne Attrappe."""
    roh = [{**s, "anbieter": "o2", "sku_id": f"geraet-{i}",
            "quelle_url": s["url"]} for i, s in enumerate(_saetze())]
    bilanz = aus_rohsaetzen(roh, _bestand(), "2026-09-04")
    # 65 von 66: der Promo-Tarif "O2 Mobile on Demand M" (ohne "Plus")
    # steht in keiner SIM-only-Kachel und loest deshalb nicht auf.
    assert len(bilanz.buendel) == 65
    assert bilanz.ohne_tarif == 1
    assert all(tco_24(b).belastbar for b in bilanz.buendel)
    assert {b.laufzeit_monate for b in bilanz.buendel} == {36}
