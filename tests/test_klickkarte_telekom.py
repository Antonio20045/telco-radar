"""Klick-Karte Telekom gegen echte Daten der Klick-Erkundung vom 07.10.2026.

Ohne Browser: die Karte lädt, liest aus der mitgeschnittenen Antwort ``/v2/details``
(iPhone 17 Pro 512 GB, MagentaMobil M) je Laufzeit Rate, Anzahlung und Tarif, und
ihre Selektoren und Textmuster treffen das Inventar der Seite. Beide Fixtures sind
echte Daten (Herkunft in ``tests/fixtures/geraete/_herkunft.json``). ``RATEN_BEI_199``
nennt je Laufzeit die Rate des Plans mit 199 € Anzahlung (upfrontPrice RTK-…-<n>-1);
die Summen der Antwort (``totalPrices``) sind die Gegenprobe.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from bs4 import BeautifulSoup

from telco_radar.collect.geraete.klickantwort import feldwert, lies_antwort
from telco_radar.collect.geraete.klickkartenprobe import GELADEN, lade_karte
from telco_radar.collect.geraete.klickoptionen import wert_nach_muster
from telco_radar.geraete_model import device_id
from telco_radar.tarif_model import Preisphase

WURZEL = Path(__file__).resolve().parents[1]
FIXTURES = WURZEL / "tests" / "fixtures" / "geraete"
DETAILS = FIXTURES / "telekom_details_iphone17pro_512gb_20261007.json"
INVENTAR = FIXTURES / "telekom_bedienelemente_iphone17pro_20261007.json"
SEITE_512 = {"speicher": "512 GB", "tarif": "MagentaMobil M"}
RATEN_BEI_199 = {"36": 30.8, "24": 46.2, "12": 92.5}


@pytest.fixture(scope="module")
def karte():
    lage = lade_karte(WURZEL / "config" / "klickkarten", "telekom")
    assert lage.status == GELADEN, lage.grund
    return lage.karte


@pytest.fixture(scope="module")
def details():
    return json.loads(DETAILS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def inventar():
    return json.loads(INVENTAR.read_text(encoding="utf-8"))


def _lies(karte, details, laufzeit, anzahlung):
    platz = {**SEITE_512, "laufzeit": laufzeit, "anzahlung_gewaehlt": anzahlung}
    return lies_antwort(details, karte.lesequellen[0], None, platz)


@pytest.mark.parametrize("laufzeit", sorted(RATEN_BEI_199))
def test_antwort_liefert_rate_anzahlung_und_tarif_je_laufzeit(karte, details, laufzeit):
    lesung = _lies(karte, details, laufzeit, "199")
    werte = lesung.werte
    assert werte.rate == RATEN_BEI_199[laufzeit]
    assert werte.ratenzahl == int(laufzeit)
    assert werte.anzahlung == 199.0
    assert werte.tarifphasen == (Preisphase(1, None, 49.95),)
    assert werte.anschluss == 39.95
    assert werte.volumen_gb == 50.0
    assert lesung.variante == {"speicher": "512 GB", "tarif": "MagentaMobil M"}


@pytest.mark.parametrize("laufzeit", sorted(RATEN_BEI_199))
def test_gegenprobe_summen_der_antwort(karte, details, laufzeit):
    """Die Antwort nennt je Plan die Summen; sie bestätigen die gelesenen Teile."""
    plan = {"36": "RTK-13090-36-1", "24": "RTK-13090-24-2", "12": "RTK-13090-12-3"}
    summen = {
        p["priceType"]: p["actualValue"]
        for p in details["totalPrices"]
        if p.get("installmentId") == plan[laufzeit]
    }
    werte = _lies(karte, details, laufzeit, "199").werte
    assert summen["upfrontPrice"] == round(werte.anzahlung + werte.anschluss, 2)
    tarif = werte.tarifphasen[0].betrag
    assert summen["recurringFee"] == round(werte.rate + tarif, 2)


@pytest.mark.parametrize("anzahlung", [None, "99", "458,15"])
def test_ohne_eindeutigen_plan_keine_rate(karte, details, anzahlung):
    """99 € gibt es beim 512-GB-Gerät nicht, „458,15“ ist deutsch geschrieben (die
    Antwort nennt 458.15): kein Plan, also weder Rate noch Anzahlung, nie die eines
    anderen Plans."""
    werte = _lies(karte, details, "36", anzahlung).werte
    assert (werte.rate, werte.ratenzahl, werte.anzahlung) == (None, None, None)
    assert werte.tarifphasen == (Preisphase(1, None, 49.95),)


def test_drei_anzahlungsstufen_je_laufzeit_ohne_platzhalter_mehrdeutig(details):
    """Gegenprobe: ohne die Anzahlung der Seite trifft die Laufzeit drei Pläne."""
    plaene = [
        p["installmentId"]
        for p in details["variants"][0]["prices"]
        if p["name"] == "upfrontPrice" and p["numberOfInstallment"] == "36"
    ]
    assert len(plaene) == 3


def _seite(inventar) -> BeautifulSoup:
    """Ein Nachbau der Elemente unter ihrem Wurzelelement (Pfad oder Gruppe)."""
    suppe = BeautifulSoup("<html><body></body></html>", "html.parser")
    wurzeln = {}
    gruppe_von = {
        e: g["pfad"] for g in inventar["gruppen"].values() for e in g["elemente"]
    }
    for nummer, element in inventar["elemente"].items():
        pfad = element["pfad"]
        if element["id"] and pfad.startswith(f"#{element['id']}"):
            pfad = gruppe_von.get(int(nummer), "")
        wurzel = pfad.split(" ")[0].lstrip("#") if pfad.startswith("#") else "body"
        if wurzel not in wurzeln:
            wurzeln[wurzel] = suppe.new_tag("div", id=wurzel)
            suppe.body.append(wurzeln[wurzel])
        attribute = {**element["aria"], "class": " ".join(element["klassen"])}
        if element["rolle"] != element["tag"]:
            attribute["role"] = element["rolle"]
        if element["id"]:
            attribute["id"] = element["id"]
        tag = suppe.new_tag(element["tag"], attrs=attribute)
        tag["data-nummer"] = nummer
        tag.string = element["text"]
        wurzeln[wurzel].append(tag)
    return suppe


def _treffer(suppe, selektor):
    return [t["data-nummer"] for t in suppe.select(selektor)]


def test_knoepfe_treffen_nur_ihre_elemente(karte, inventar):
    suppe = _seite(inventar)
    speicher = karte.knoepfe["speicher"]
    laufzeit = karte.knoepfe["laufzeit"]
    assert _treffer(suppe, speicher.selektor) == ["36", "37", "38"]
    assert _treffer(suppe, laufzeit.selektor) == ["42", "43", "44"]
    assert _treffer(suppe, karte.knoepfe["tarif"].selektor) == ["63"]
    elemente = inventar["elemente"]
    werte = [elemente[n]["aria"][speicher.wert_attribut] for n in ("36", "37", "38")]
    assert werte == ["256 GB", "512 GB", "1 TB"]
    laufzeiten = [
        wert_nach_muster(elemente[n]["aria"][laufzeit.wert_attribut], laufzeit.muster)
        for n in ("42", "43", "44")
    ]
    assert laufzeiten == ["36", "24", "12"]


def test_marken_zeigen_genau_eine_gewaehlte_option(karte, inventar):
    elemente = inventar["elemente"]
    for dimension, nummern in (("speicher", "36 37 38"), ("laufzeit", "42 43 44")):
        marke = karte.knoepfe[dimension].marke
        liste = nummern.split()
        gewaehlt = [
            n for n in liste if elemente[n]["aria"][marke.attribut] == marke.wert
        ]
        assert gewaehlt == [liste[0]]


def test_seitenwert_vorbereitung_und_kanarie(karte, inventar):
    suppe = _seite(inventar)
    anzahlung = karte.seite["anzahlung_gewaehlt"]
    assert _treffer(suppe, anzahlung.selektor) == ["42"]
    label = inventar["elemente"]["42"]["aria"][anzahlung.attribut]
    assert wert_nach_muster(label, anzahlung.muster) == "99"
    vorbereitung = karte.vorbereitung[0]
    assert _treffer(suppe, vorbereitung.klick) == ["40"]
    assert _treffer(suppe, f"{vorbereitung.klick}{vorbereitung.bis}") == ["40"]
    katalog = yaml.safe_load((WURZEL / "config" / "geraete_katalog.yaml").read_text())
    modell = next(
        g["modell"]
        for g in katalog["geraete"]
        if device_id(g["hersteller"], g["modell"]) == "apple-iphone-17-pro"
    )
    kanarie = karte.kanarie
    assert _treffer(suppe, kanarie.selektor) == ["46"]
    wert = inventar["elemente"]["46"]["aria"][kanarie.attribut]
    assert kanarie.enthaelt.format(modell=modell) in wert


def test_textmuster_lesen_die_werte_der_seite(karte, inventar):
    suppe = _seite(inventar)
    muster = karte.textlesung.muster
    knopf = inventar["elemente"]["42"]["text"]
    for feld in ("rate", "ratenzahl", "anzahlung"):
        assert _treffer(suppe, muster[feld].selektor) == ["42"]
    gelesen = {
        feld: feldwert(feld, "".join(muster[feld].muster.search(text)[1].split()))
        for feld, text in (
            ("rate", knopf),
            ("ratenzahl", knopf),
            ("anzahlung", knopf),
            ("anschluss", inventar["gruppen"]["45"]["name"]),
            ("volumen_gb", inventar["gruppen"]["43"]["name"]),
            ("tarifphasen", inventar["preise"]["19"]["text"]),
        )
    }
    assert gelesen == {
        "rate": 26.9,
        "ratenzahl": 36,
        "anzahlung": 99.0,
        "anschluss": 39.95,
        "volumen_gb": 50.0,
        "tarifphasen": (Preisphase(1, None, 49.95),),
    }


def test_strukturselektoren_stehen_im_inventar(karte, inventar):
    preise, gruppen = inventar["preise"], inventar["gruppen"]
    erster, tarifblock = karte.textlesung.selektoren
    assert preise["22"]["pfad"].startswith(f"{erster} > ")
    assert gruppen["45"]["pfad"].startswith(f"{erster} > ")
    assert gruppen["42"]["pfad"].startswith(f"{tarifblock} > ")
    assert karte.textlesung.muster["tarifphasen"].selektor == preise["19"]["pfad"]
