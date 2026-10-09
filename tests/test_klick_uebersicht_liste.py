"""Telekom-Übersicht aus der Datenantwort ``productOfferings/listing`` (Pitch 4, 2b).

Klick-Tageslauf 09.10.2026 (Actions, Commit bd616939): die Übersicht MagentaMobil M kam
mit HTTP 200, trug aber kein Gerät mehr im Seitentext; der neue Shop lädt die Liste
per ``POST …/productOfferings/listing``. Die echte Antwort steht in
``tests/fixtures/geraete/telekom_listing_rueckgabedeal_20261009.json`` (Zweig
klick-erkundung, Commit b335c6ec) und zeigt die Preise MIT „Telekom Rückgabedeal“
(35 Raten plus Restzahlung ``buyBackPrice``): kein vergleichbarer Preis, je Gerät eine
benannte Lücke. Die Variante ohne Rückgabedeal ist eine ABLEITUNG im Test
(``_ohne_rueckgabedeal``), keine echte Antwort: buyBack-Felder entfernt, iPhone 17 auf
die Werte der Produktseite (Lauf 09.10.2026 06:25 UTC, Commit b57e7b5) gesetzt.

Im Browser liefert ein lokaler Server auf 127.0.0.1 eine Seite, die wie der Shop beim
Laden die Rückgabedeal-Antwort holt und nach dem Ausschalten des Schalters die Antwort
ohne Deal; „Weitere Geräte anzeigen“ lädt die zweite Seite. Fremde Hosts sperrt
robots.txt, es geht nichts ins Netz.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime

import pytest
from bestand_pfad import lese_wurzel
from klickergebnisse import WURZEL
from klickserver import Antwort, html, klickserver

from telco_radar.collect.geraete.klickergebnis import LAUF_LEER
from telco_radar.collect.geraete.klickkarte import lade_klickkarte
from telco_radar.collect.geraete.klicklauf import LAUF_GELESEN
from telco_radar.collect.geraete.klickliste import GRUND_OHNE_SCHALTER
from telco_radar.collect.geraete.klickrohsatz import ausbeute
from telco_radar.collect.geraete.klicktor import Hostschleuse
from telco_radar.collect.geraete.klickuebersicht import lies_uebersicht
from telco_radar.collect.geraete.robots import RobotsWaechter
from telco_radar.collect.geraete.telekom_liste import (
    LUECKE_RATENZAHL,
    LUECKE_RUECKGABEDEAL,
    lies_listing,
)
from telco_radar.geraete_config import lade_katalog

FIXTURE = WURZEL / "tests/fixtures/geraete/telekom_listing_rueckgabedeal_20261009.json"
PFAD = "/shop/geraete/smartphones?tariffId=MF_17791"
LISTING = "/shop/api/eshop/bff-de/productOfferings/listing"
IPHONE_17 = "/shop/geraet/apple/apple-iphone-17/lavendel-256-gb"
JETZT = datetime(2026, 10, 9, 11, 0, tzinfo=UTC)
OFFEN = "User-agent: *\nDisallow:\n"
ZU = "User-agent: *\nDisallow: /\n"


@pytest.fixture(scope="module")
def echt() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def karte():
    return lade_klickkarte(WURZEL / "config" / "klickkarten" / "telekom.yaml")


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


def _ohne_rueckgabedeal(echt: dict) -> dict:
    """ABLEITUNG, keine echte Antwort: ohne buyBack-Felder und Rückgabedeal-Plakette;
    iPhone 17 256 GB auf 99,00 + 36 × 23,80 = 955,80 (Produktseite 09.10.2026). Die
    übrigen Geräte behalten 35 Raten auf einen 36-Raten-Gesamtbetrag: keine Probe."""
    neu = copy.deepcopy(echt)
    for eintrag in neu["data"]:
        eintrag.pop("promotionTag", None)
        for plan in eintrag["price"]["installments"]:
            plan.pop("buyBackPrice", None)
            plan.pop("buyBackDiscount", None)
    iphone = next(e for e in neu["data"] if e["name"] == "Apple iPhone 17")
    iphone["price"]["upfrontPrice"] = 99.0
    (plan,) = iphone["price"]["installments"]
    plan.update(
        numberOfInstallments=37,
        recurringChargeOccurrence=36,
        recurringPrice=23.8,
        totalPrice=955.8,
    )
    return neu


def test_echte_antwort_mit_rueckgabedeal_gibt_keinen_preis(echt):
    lesung = lies_listing([echt], "", "https://www.telekom.de" + PFAD)
    assert lesung.saetze == []
    assert lesung.geraete == 14
    assert lesung.luecken == {LUECKE_RUECKGABEDEAL: 14}
    assert lesung.result_count == 56


def test_abgeleitete_antwort_ohne_deal_ergibt_iphone_17(echt):
    seite = f'<a href="{IPHONE_17}?tariffId=MF_17791">Apple iPhone 17</a>'
    lesung = lies_listing(
        [_ohne_rueckgabedeal(echt)], seite, "https://www.telekom.de" + PFAD
    )
    (satz,) = lesung.saetze
    assert satz["titel"] == "Apple iPhone 17 256 GB"
    assert satz["speicher_gb"] == 256
    assert satz["tarif_name"] == "MagentaMobil M"
    assert satz["tarif_slug"] == "MF_17791"
    assert satz["tarif_monatlich"] == 49.95
    assert satz["anschlusspreis"] == 39.95
    assert satz["laufzeit_monate"] == 36
    assert satz["geraet_zuzahlung"] == 99.0
    assert satz["geraet_monatsrate"] == 23.8
    assert satz["url"] == f"https://www.telekom.de{IPHONE_17}?tariffId=MF_17791"
    assert lesung.luecken == {LUECKE_RATENZAHL: 13}


def test_produktadresse_nur_wenn_sie_auf_der_seite_steht(echt):
    uebersicht = "https://www.telekom.de" + PFAD
    lesung = lies_listing([_ohne_rueckgabedeal(echt)], "<p>ohne Link</p>", uebersicht)
    assert lesung.saetze[0]["url"] == uebersicht


SEITE = """<html><body>
<span class="dt_switch forwardTradeInSwitch" role="switch" aria-checked="true"
 aria-label="Telekom Rückgabedeal, activated">Rückgabedeal</span>
<a href="IPHONE?tariffId=MF_17791">Apple iPhone 17</a>
<button id="weiter">Weitere Geräte anzeigen</button>
<script>
const schalter = document.querySelector('.forwardTradeInSwitch');
const weiter = document.getElementById('weiter');
let seite = 0;
function hole() {
  const deal = schalter ? schalter.getAttribute('aria-checked') : 'true';
  return fetch('LISTING?deal=' + deal + '&seite=' + seite,
    {method: 'POST', body: '{}'}).then(r => r.json());
}
hole();
if (schalter) schalter.addEventListener('click', () => {
  schalter.setAttribute('aria-checked', 'false');
  seite = 0;
  hole();
});
weiter.addEventListener('click', () => {
  seite += 1;
  hole().then(d => {
    if ((d.pageNumber + 1) * d.itemsPerPage >= d.resultCount) weiter.remove();
  });
});
</script></body></html>""".replace("IPHONE", IPHONE_17).replace("LISTING", LISTING)


def listenseiten(echt: dict) -> dict[str, dict]:
    """Rückgabedeal beim Laden; ohne Deal zwei Seiten zu je sieben Geräten (Ableitung,
    auf Seite 2 iPhone 17e 1,00 + 36 × 17,20 = 620,20)."""
    ohne = _ohne_rueckgabedeal(echt)
    erste = {**ohne, "itemsPerPage": 7, "resultCount": 14, "data": ohne["data"][:7]}
    zweite = {**erste, "pageNumber": 1, "data": copy.deepcopy(ohne["data"][7:])}
    e17 = next(e for e in zweite["data"] if e["name"] == "Apple iPhone 17e")
    e17["price"]["installments"][0]["recurringChargeOccurrence"] = 36
    return {
        "deal=true&seite=0": echt,
        "deal=false&seite=0": erste,
        "deal=false&seite=1": zweite,
    }


def antworte_liste(seite: str, listen: dict[str, dict]):
    def antworte(pfad: str) -> Antwort:
        if pfad == PFAD:
            return html(seite)
        if pfad.startswith(LISTING + "?"):
            nutzlast = listen.get(pfad.split("?", 1)[1])
            if nutzlast is not None:
                return Antwort(200, "application/json", json.dumps(nutzlast))
        return html("", 404)

    return antworte


def lies_testseite(chromium, karte, adresse: str) -> dict:
    def robots(url: str) -> tuple[int, str]:
        return 200, OFFEN if "127.0.0.1" in url else ZU

    waechter = RobotsWaechter(hole=robots)
    schleuse = Hostschleuse(waechter, lambda: JETZT)
    return lies_uebersicht(
        chromium, adresse, karte, waechter, lambda: JETZT, schleuse=schleuse
    )


def test_browser_liest_nur_antworten_nach_dem_ausschalten(
    chromium, karte, katalog, echt
):
    with klickserver(antworte_liste(SEITE, listenseiten(echt))) as server:
        ergebnis = lies_testseite(chromium, karte, server.adresse(PFAD))
        listings = server.mit(LISTING)
    assert ergebnis["status"] == LAUF_GELESEN, ergebnis["grund"]
    assert ergebnis["vollstaendig"] is True, ergebnis["unvollstaendig"]
    assert listings == [
        f"{LISTING}?deal=true&seite=0",
        f"{LISTING}?deal=false&seite=0",
        f"{LISTING}?deal=false&seite=1",
    ]
    titel = sorted(s["titel"] for s in ergebnis["saetze"])
    assert titel == ["Apple iPhone 17 256 GB", "Apple iPhone 17e 256 GB"]
    (seite,) = ergebnis["seiten"]
    assert seite["liste"] == {
        "result_count": 14,
        "antworten_beim_laden": 1,
        "einwilligung": None,
        "antworten": 2,
        "geraete": 14,
        "mit_rueckgabedeal": 0,
        "ohne_rueckgabedeal": 14,
        "luecken": {LUECKE_RATENZAHL: 12},
        "schalter_vorher": "true",
        "schalter_nachher": "false",
        "weiter_klicks": 1,
        "unvollstaendig": None,
    }
    daten = {"name": "Telekom", "datum": "2026-10-09", "seiten": []}
    aus = ausbeute({**daten, "uebersichten": [ergebnis]}, katalog)
    iphone = next(s for s in aus.rohsaetze if s["device_id"] == "apple-iphone-17")
    assert (iphone["geraet_zuzahlung"], iphone["geraet_monatsrate"]) == (99.0, 23.8)
    assert iphone["quelle_url"] == server.adresse(IPHONE_17 + "?tariffId=MF_17791")


def test_ohne_schalter_leer_mit_grund_und_ohne_rueckgabedeal_preise(
    chromium, karte, echt
):
    ohne = SEITE.split("<span", 1)[0] + SEITE.split("</span>", 1)[1]
    with klickserver(antworte_liste(ohne, listenseiten(echt))) as server:
        ergebnis = lies_testseite(chromium, karte, server.adresse(PFAD))
    assert ergebnis["status"] == LAUF_LEER
    assert ergebnis["grund"] == GRUND_OHNE_SCHALTER
    assert ergebnis["saetze"] == []
    assert ergebnis["vollstaendig"] is False
    assert ergebnis["seiten"][0]["liste"]["schalter_vorher"] is None
