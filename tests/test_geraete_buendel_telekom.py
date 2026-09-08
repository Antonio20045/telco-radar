"""Die Bündellesart der Telekom-Kategorieseite: Gerät×Tarif je tariffId (B2).

WAS HIER GEPRÜFT WIRD, UND WARUM ES EINE EIGENE DATEI IST
--------------------------------------------------------
Bis zum 08.09.2026 gab es Gerät×Tarif-Bündel für o2 (63) und Vodafone (253);
die Telekom stand bei 0 — ihre Produktseiten tragen je Speicherstufe nur
einen `deltaPrice` (T2-Befund), und Produktinformationsblätter liefern keine
Bündelkombinatorik. Die Bündelseiten der Telekom sind DIESELBE
Kategorieseite mit `?tariffId=MF_<id>` — je MagentaMobil-Tarif eine
Antwort, mit dem Tarifnamen in `productList.selectedPlan` derselben
Antwort (kein zweiter Endpunkt nötig, der Unterschied zu Vodafones
`offerCoreHash`).

DIE FIXTURES SIND GESPEICHERTE ECHTE ABRUFE
--------------------------------------------
`telekom_kategorie_buendel_magentamobil_s.html.gz` ist die Antwort auf
`/shop/geraete/smartphones?tariffId=MF_17785` (08.09.2026, HTTP 200,
509 KB, Absender `TelcoRadar/1.0`, reiner HTTP-GET). Sie trägt 10
Einträge, davon 9 Geräte und eine Werbekachel ohne `name`.
`telekom_kategorie_smartphones_ohne_vertrag.html.gz` ist die schon
vorhandene Fixture des Preis-ohne-Vertrag-Adapters (04.09.2026) — ihr
`selectedPlan` ist `null`, deshalb ist sie hier der FALL FÜR DEN
FEHLERPFAD: eine Antwort ohne gewählten Tarif ist keine Bündelantwort.

ZWEI NACHRECHNUNGEN SIND BEDINGUNG, NICHT PROTOKOLL
----------------------------------------------------
1. `upfrontPrice + numberOfInstallments × recurringPrice == totalPrice`
   (dieselbe Probe wie beim Preis-ohne-Vertrag-Adapter, `_preisform`).
2. Der je-Gerät-Tarifpreis (`formattedPrices.recurringTariffPrice`) muss
   zum `selectedPlan` gehören (Preis-ID beginnt mit der Plan-ID) und ihm
   entsprechen (Betrag) — sonst hätte die Antwort zwei Tarife, und der
   Satz wäre falsch etikettiert.
"""
import gzip
import json
import re
from pathlib import Path

import pytest

from telco_radar.analyze.tco_buendel import aus_rohsaetzen
from telco_radar.collect.geraete import (
    ADAPTER,
    GeraeteAbrufFehler,
    sammle_anbieter,
)
from telco_radar.collect.geraete.robots import RobotsWaechter
from telco_radar.collect.geraete.telekom import lies_buendel
from telco_radar.geraete_config import Anbieter, Einstieg, lade_farben, lade_katalog
from telco_radar.tarif_bezug import Tarifbestand
from telco_radar.tarif_model import HOCH

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_WURZEL = Path(__file__).parent.parent

# Die echten Werte der Fixture (MagentaMobil S, MF_17785, 08.09.2026).
_PLAN_ID = "MF_17785"
_PLAN_NAME = "MagentaMobil S"
_TARIF_MONATLICH = 39.95
_ANSCHLUSS = 39.95


def _fixture(name: str) -> str:
    """HTML lesen; `.gz`-Fixtures sind gespeicherte echte Abrufe."""
    pfad = _FIX / name
    if pfad.suffix == ".gz":
        return gzip.open(pfad, "rb").read().decode("utf-8", "replace")
    return pfad.read_text(encoding="utf-8")


def _saetze():
    return lies_buendel(_fixture("telekom_kategorie_buendel_magentamobil_s.html.gz"))


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(_WURZEL)


@pytest.fixture(scope="module")
def farben():
    return lade_farben(_WURZEL)


def _zustand(html: str) -> dict:
    treffer = re.search(r"window\.__INITIAL_STATE__\s*=\s*", html)
    daten, _ = json.JSONDecoder().raw_decode(html, treffer.end())
    return daten


# ==========================================================================
# lies_buendel()
# ==========================================================================

def test_neun_saetze_aus_neun_geraeten_und_einer_werbekachel():
    """10 Einträge, davon eine Kachel ohne `name` (tileType/höhererTariff-
    Discount) — sie wird übergangen, nicht geraten."""
    saetze = _saetze()
    assert len(saetze) == 9
    assert len({s["titel"] for s in saetze}) == 9      # keine Dublette


def test_jeder_satz_traegt_den_tarifnamen_aus_der_antwort():
    """Der Name steht in `productList.selectedPlan.name` — derselben
    Antwort, aus der die Preise kommen. Nicht geraten, nicht hardcoded."""
    for s in _saetze():
        assert s["tarif_name"] == _PLAN_NAME
        assert s["tarif_slug"] == _PLAN_ID


def test_jeder_satz_traegt_anschlusspreis_und_tarif_monatlich():
    """Anschlusspreis (oneTimeTariffFee) und Tarif-Monatsgebühr
    (monthlyTariffFee) kommen aus den typisierten Preisen des selectedPlan."""
    for s in _saetze():
        assert s["anschlusspreis"] == _ANSCHLUSS
        assert s["tarif_monatlich"] == _TARIF_MONATLICH
        assert s["laufzeit_monate"] == 36
        assert s["geraet_zuzahlung"] is not None
        assert s["geraet_monatsrate"] is not None


def test_der_pixel_satz_nach_rechnung():
    """Vollständige Nachrechnung an einem konkreten Satz: Pixel 11 Pro
    256 GB olive, 99 € + 36 × 28,30 € = 1117,80 € Ratengesamtbetrag,
    dazu 39,95 €/Monat Tarif und 39,95 € Anschlusspreis."""
    s = next(x for x in _saetze() if "Pixel 11 Pro 256 GB" in x["titel"])
    assert s["geraet_zuzahlung"] == 99.0
    assert s["geraet_monatsrate"] == 28.3
    assert s["geraet_zuzahlung"] + 36 * s["geraet_monatsrate"] == \
        pytest.approx(1117.8, abs=0.005)
    assert s["farbe"] == "olive"
    assert s["speicher_gb"] == 256


def test_jede_ratenform_geht_gegen_die_rohantwort_auf():
    """Die Probe ist Bedingung: je Satz muss upfront + n × rate == dem
    totalPrice desselben Eintrags in der ROHANTWORT entsprechen — hier
    nachgelesen, nicht nur dem schon gefilterten Satz geglaubt."""
    html = _fixture("telekom_kategorie_buendel_magentamobil_s.html.gz")
    roh_je_id = {}
    for eintrag in _zustand(html)["productList"]["data"]:
        if isinstance(eintrag, dict) and eintrag.get("id"):
            roh_je_id[str(eintrag["id"])] = eintrag
    # 9 Einträge MIT id — die Werbekachel trägt keine.
    assert len(roh_je_id) == 9

    saetze = _saetze()
    assert len(saetze) == 9                 # die Lookup-Zeile (kein blinder Test)
    for s in saetze:
        eintrag = roh_je_id[s["sku"]]
        erste = (eintrag.get("price") or {}).get("installments")[0]
        assert s["geraet_zuzahlung"] + \
            s["laufzeit_monate"] * s["geraet_monatsrate"] == \
            pytest.approx(float(erste["totalPrice"]), abs=0.005)
        assert s["geraet_monatsrate"] == float(erste["recurringPrice"])
        # Zweite Probe: der je-Gerät-Tarifpreis gehört zum selectedPlan.
        geraet_tarif = (eintrag.get("formattedPrices") or {}) \
            .get("recurringTariffPrice", {}).get("price", {})
        assert geraet_tarif["id"].startswith(f"{_PLAN_ID}-")
        assert s["tarif_monatlich"] == float(geraet_tarif["actualValue"])


def test_kaputte_nutzlast_wirft():
    with pytest.raises(GeraeteAbrufFehler):
        lies_buendel("gar kein html")


def test_die_ohne_vertrag_antwort_ist_keine_buendelantwort():
    """`selectedPlan: null` auf der ohne-vertrag-Seite — dieselbe Stelle,
    die der Preis-Adapter liest, ist für Bündel die falsche Antwort. Ein
    leeres Ergebnis wäre die falsche Meldung: das Nutzlastformat hat den
    Tarif nicht, der Aufrufer hat ihn nicht mitgegeben."""
    with pytest.raises(GeraeteAbrufFehler, match="selectedPlan"):
        lies_buendel(_fixture(
            "telekom_kategorie_smartphones_ohne_vertrag.html.gz"))


def _erster_geraeteeintrag(html: str) -> str:
    """Die Antwort auf den ersten GERÄTEEintrag kappen, damit ein
    manipuliertes Beispiel nicht zwischen echten Sätzen verschwindet."""
    daten = _zustand(html)
    geraete = [e for e in daten["productList"]["data"]
               if isinstance(e, dict) and e.get("name")]
    daten["productList"]["data"] = geraete[:1]
    return f'<script>window.__INITIAL_STATE__ = {json.dumps(daten)};</script>'


def test_eine_ratenform_die_nicht_aufgeht_faellt():
    html = _fixture("telekom_kategorie_buendel_magentamobil_s.html.gz")
    daten = _zustand(html)
    geraete = [e for e in daten["productList"]["data"]
               if isinstance(e, dict) and e.get("name")]
    geraete[0]["price"]["installments"][0]["totalPrice"] = 9999.0
    daten["productList"]["data"] = geraete[:1]
    geaendert = f'<script>window.__INITIAL_STATE__ = {json.dumps(daten)};</script>'
    assert lies_buendel(geaendert) == []


def test_ein_geraetepreis_eines_fremden_tarifs_faellt():
    """Die Preis-ID `MF_99999-MRC-Price` gehört nicht zum selectedPlan
    MF_17785 — der Satz wäre falsch etikettiert, also verworfen."""
    html = _fixture("telekom_kategorie_buendel_magentamobil_s.html.gz")
    daten = _zustand(html)
    geraete = [e for e in daten["productList"]["data"]
               if isinstance(e, dict) and e.get("name")]
    geraete[0]["formattedPrices"]["recurringTariffPrice"]["price"]["id"] = \
        "MF_99999-MRC-Price"
    daten["productList"]["data"] = geraete[:1]
    geaendert = f'<script>window.__INITIAL_STATE__ = {json.dumps(daten)};</script>'
    assert lies_buendel(geaendert) == []


def test_ein_geraetepreis_der_dem_plan_widerspricht_faellt():
    """Richtige ID, falscher Betrag: die Antwort widerspricht sich selbst
    — kein Satz, sondern ein Befund."""
    html = _fixture("telekom_kategorie_buendel_magentamobil_s.html.gz")
    daten = _zustand(html)
    geraete = [e for e in daten["productList"]["data"]
               if isinstance(e, dict) and e.get("name")]
    geraete[0]["formattedPrices"]["recurringTariffPrice"]["price"] \
        ["actualValue"] = 19.99
    daten["productList"]["data"] = geraete[:1]
    geaendert = f'<script>window.__INITIAL_STATE__ = {json.dumps(daten)};</script>'
    assert lies_buendel(geaendert) == []


# ==========================================================================
# Vom Rohsatz zum echten Buendel - der Name loest im Bestand auf
# ==========================================================================

def _bestand_mit_magentamobil_s():
    """Der Tarifbestand, wie ihn der Tarif-Sammler aus dem Telekom-PIB
    schreibt — der Name steht wortgleich in `selectedPlan.name`."""
    return Tarifbestand([
        {"tarif_id": "telekom:magentamobil-s", "anbieter": "Telekom",
         "name": "MagentaMobil S", "grundgebuehr": 39.95},
    ])


def test_der_ganze_weg_bis_zum_buendel():
    """Ende zu Ende: selectedPlan.name -> tarif_id über den Bestand
    (Güte HOCH, über den Namen), mit Zuzahlung, Rate, Anschlusspreis."""
    roh = next(s for s in _saetze()
               if "Pixel 11 Pro 256 GB" in s["titel"])
    satz = {**roh, "anbieter": "Telekom",
            "sku_id": "google-pixel-11-pro-256gb-ohne-farbe",
            "quelle_url": roh["url"]}
    bilanz = aus_rohsaetzen([satz], _bestand_mit_magentamobil_s(),
                            "2026-09-08")
    assert len(bilanz.buendel) == 1
    b = bilanz.buendel[0]
    assert b.tarif_id == "telekom:magentamobil-s"
    assert b.tarif_id_guete == HOCH
    assert b.geraet_zuzahlung == 99.0
    assert b.geraet_monatsrate == 28.3
    assert b.anschlusspreis == 39.95
    assert b.tarif_monatlich == 39.95
    assert b.laufzeit_monate == 36


def test_der_beleglink_traegt_die_tariffid():
    """Der Tiefenlink auf der Bündelseite führt die tariffId mit — er
    belegt nicht nur das Gerät, sondern das Gerät IN DIESEM Tarif."""
    for s in _saetze():
        assert "tariffId=MF_17785" in s["url"], s["url"]


# ==========================================================================
# Die Verdrahtung: sammle_anbieter() am kind:buendel-Einstieg
# ==========================================================================

_ROBOTS_FREI = (200, "User-agent: *\nDisallow: /is-bin/\n")


def _telekom_anbieter():
    return Anbieter(
        name="Telekom", typ="netzbetreiber", methode="telekom_kategorie",
        basis_url="https://www.telekom.de", rate_limit_sekunden=0,
        einstiege=[Einstieg(
            url="https://www.telekom.de/shop/geraete/smartphones"
                "?tariffId=MF_17785",
            label="Bündel MagentaMobil S", kind="buendel")])


def test_sammle_anbieter_liefert_buendel_und_keine_listungen(katalog, farben):
    """`kind: buendel` heißt: die Sätze gehen an der Listungsstrecke
    vorbei in `bilanz.buendel` — ein Bündelmonatspreis gehört nicht in die
    Preisspalte der Geräteseite."""
    def hole(url, **kwargs):
        if url.endswith("/robots.txt"):
            return _ROBOTS_FREI
        return 200, _fixture(
            "telekom_kategorie_buendel_magentamobil_s.html.gz")

    waechter = RobotsWaechter(hole=hole)
    bilanz = sammle_anbieter(_telekom_anbieter(), katalog, farben, hole,
                             "2026-09-08", waechter)
    assert bilanz.status == "ok"
    assert bilanz.listungen == []
    assert len(bilanz.buendel) == 9
    b = bilanz.buendel[0]
    assert b["anbieter"] == "Telekom"
    assert b["sku_id"]                     # über den Katalog gebildet
    assert b["tarif_name"] == "MagentaMobil S"
    assert b["geraet_zuzahlung"] is not None


def test_adapter_registry_traegt_telekoms_buendelhaken():
    adapter = ADAPTER["telekom_kategorie"]
    assert adapter.lies_buendel is not None
    # Der Tarifname steht in derselben Antwort — Telekom braucht anders
    # als Vodafone keinen Haken für die Namensauflösung nach dem Sammeln.
    assert adapter.loese_tarifnamen is None


def test_der_robots_abruf_traegt_den_absender_des_anbieters(katalog, farben):
    """B2-Befund vom 08.09.2026, erster Lauf: alle sechs Seitenrequests
    gingen mit TelcoRadar/1.0 hinaus, der robots.txt-Abruf davor aber mit
    der globalen Chrome-Kennung aus settings.yaml (Laufzeitbeleg
    `beleg-telekom-geraete-2026-09-08.json`, 1 von 7 Requests unehrlich).
    Der robots-Abruf gehört zum Crawl DIESES Anbieters und trägt deshalb
    denselben Absender — ein Anbieter ohne Override bleibt beim geteilten
    Wächter (PM-Entscheidung zu settings.yaml steht aus)."""
    gesehen: dict[str, str | None] = {}

    def hole(url, kopfzeilen=None, user_agent=None):
        gesehen[url] = user_agent
        if url.endswith("/robots.txt"):
            return (200, "User-agent: *\nDisallow: /is-bin/\n")
        return 200, _fixture(
            "telekom_kategorie_buendel_magentamobil_s.html.gz")

    anbieter = Anbieter(
        name="Telekom", typ="netzbetreiber", methode="telekom_kategorie",
        basis_url="https://www.telekom.de", rate_limit_sekunden=0,
        user_agent="TelcoRadar/1.0 (+https://telco-radar.onrender.com/ueber)",
        einstiege=[Einstieg(
            url="https://www.telekom.de/shop/geraete/smartphones"
                "?tariffId=MF_17785",
            label="Bündel MagentaMobil S", kind="buendel")])

    bilanz = sammle_anbieter(anbieter, katalog, farben, hole, "2026-09-08",
                             RobotsWaechter(hole=hole))
    assert bilanz.status == "ok" and bilanz.buendel
    robots = [u for u in gesehen if u.endswith("/robots.txt")]
    assert robots, "kein robots.txt-Abruf erfolgt — der Test prüft nichts"
    # Die Lookup-Zeile: JEDER Abruf dieses Anbieters — robots.txt wie
    # Bündelseite — mit demselben ehrlichen Absender.
    assert gesehen and all(
        ua == "TelcoRadar/1.0 (+https://telco-radar.onrender.com/ueber)"
        for ua in gesehen.values()), gesehen
