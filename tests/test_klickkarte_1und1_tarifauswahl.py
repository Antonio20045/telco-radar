"""Klick-Karte 1&1 nach dem Shop-Umbau vom 20.11.2026: Tarifauswahl im Bestellweg.

Seit dem 20.11.2026 wählt die Produktseite Speicher und Laufzeit (Reiter „36 Monate“,
„24 Monate“, darunter „Fix“ und „+ 12 Monate Flex“), der Tarif steht erst auf der
Folgeseite /flow2/mobile/ssc-private/tariffselect nach „Weiter zur Tarifauswahl“. Je
Tarifkachel trägt das Radio ``data-tariff-price-hint`` (JSON); sichtbar sind der
Tarifpreis in der Kachel und die Geräterate in der Preisleiste. Fixtures (Herkunft in
``tests/fixtures/klickcrawler/_herkunft.json``): Produktseite iPhone 17 beim Laden
(36 Monate, Flex vorgewählt) und Tarifauswahl iPhone 17 512 GB „24 Monate Fix“ mit
sieben sichtbaren Kacheln und einer verborgenen Kopie der Tarifbox.

Erwartete Beträge sind die sichtbaren der Seite vom 20.11.2026, Geräterate 58,– € plus
Tarifpreis der Kachel: All-Net-Flat S 10,99, M 15,99, L 20,99, Unlimited on demand S
15,99, M 20,99, L 25,99, Unlimited XL 35,99.
"""

from __future__ import annotations

import html as html_modul
import json
import re
from pathlib import Path

import pytest
import soupsieve
import yaml
from bestand_pfad import lese_wurzel
from bs4 import BeautifulSoup

from telco_radar.collect.geraete.klickantwort import lies_antwort
from telco_radar.collect.geraete.klickbeleg import pfadtext
from telco_radar.collect.geraete.klickfarbe import sku_farbe
from telco_radar.collect.geraete.klickkarte import (
    KlickkartenFehler,
    klickkarte_aus_daten,
    lade_klickkarte,
)
from telco_radar.collect.geraete.klickoptionen import wert_nach_muster
from telco_radar.collect.geraete.klickquellen import Quellenleser
from telco_radar.collect.geraete.klickrohsatz import ausbeute
from telco_radar.collect.geraete.klicktextleser import Textleser
from telco_radar.geraete_config import lade_katalog
from telco_radar.tco_model import buendel_id

WURZEL = Path(__file__).resolve().parents[1]
KARTE = WURZEL / "config" / "klickkarten" / "1und1.yaml"
FIX = WURZEL / "tests" / "fixtures" / "klickcrawler"
PRODUKTSEITE = FIX / "einsundeins_produktseite_20261120.html"
TARIFAUSWAHL = FIX / "einsundeins_tarifauswahl_20261120.html"
TARIFE = (
    "tariff-anf-s-mvl",
    "tariff-anf-m-mvl",
    "tariff-anf-l-mvl",
    "tariff-anf-xxl-unlimited-s-mvl",
    "tariff-anf-xxl-unlimited-m-mvl",
    "tariff-anf-xxl-unlimited-l-mvl",
    "tariff-anf-xxl-unlimited-xl-mvl",
)
NAMEN = (
    "1&1 All-Net-Flat S",
    "1&1 All-Net-Flat M",
    "1&1 All-Net-Flat L",
    "1&1 Unlimited on demand S",
    "1&1 Unlimited on demand M",
    "1&1 Unlimited on demand L",
    "1&1 Unlimited XL",
)
BUENDEL_512_24 = (68.99, 73.99, 78.99, 73.99, 78.99, 83.99, 93.99)
PREISLEISTE = "#pso [data-pso-main-monthly-section]"


@pytest.fixture(scope="module")
def karte():
    return lade_klickkarte(KARTE)


@pytest.fixture(scope="module")
def produktseite() -> BeautifulSoup:
    return BeautifulSoup(PRODUKTSEITE.read_text(encoding="utf-8"), "html.parser")


@pytest.fixture(scope="module")
def tarifauswahl() -> BeautifulSoup:
    return BeautifulSoup(TARIFAUSWAHL.read_text(encoding="utf-8"), "html.parser")


def _werte(karte, dimension: str, dom: BeautifulSoup) -> list[str | None]:
    knopf = karte.knoepfe[dimension]
    werte = []
    for treffer in dom.select(knopf.selektor):
        traeger = treffer.select_one(knopf.wert_in) if knopf.wert_in else treffer
        roh = traeger.get(knopf.wert_attribut) if knopf.wert_attribut else None
        werte.append(wert_nach_muster(str(roh), knopf.muster))
    return werte


def _hinweise(karte, dom: BeautifulSoup) -> list[dict]:
    kacheln = dom.select(karte.knoepfe["tarif"].selektor)
    return [
        json.loads(k.select_one(karte.antwort.kachel)[karte.antwort.attribut])
        for k in kacheln
    ]


def test_karte_liest_tarife_als_kacheln_der_folgeseite(karte):
    assert karte.ein_vertrag
    assert karte.weiter.kacheln == "tarif"
    assert karte.weiter.text == "Weiter zur Tarifauswahl"
    assert (karte.antwort.kachel, karte.antwort.attribut) == (
        'input[name="tariff-plan"]',
        "data-tariff-price-hint",
    )
    assert pfadtext(karte.antwort.pfade["buendelbetrag"]) == (
        "hardwarePricePerMonth + tariffPricePerMonth"
    )


def test_produktseite_speicher_laufzeit_weiter_und_kanarie(karte, produktseite):
    assert _werte(karte, "speicher", produktseite) == ["256", "512"]
    assert _werte(karte, "laufzeit", produktseite) == ["36", "24"]
    (weiter,) = produktseite.select(karte.weiter.selektor)
    assert weiter.get_text(strip=True) == "Weiter zur Tarifauswahl"
    kanarie = produktseite.select_one(karte.kanarie.selektor)
    assert "iPhone 17" in kanarie[karte.kanarie.attribut]


def test_gegenprobe_sofort_ist_keine_laufzeit(karte, produktseite):
    reiter = produktseite.select("button.contract-toggle__contract")
    assert [r["data-target-model-id"] for r in reiter][-1] == "contract-tab-sofort"
    assert len(produktseite.select(karte.knoepfe["laufzeit"].selektor)) == 2


def test_seite_zeigt_speicher_und_nur_fix_als_laufzeit(karte, produktseite):
    speicher = produktseite.select_one(karte.seite["speicher"].selektor)
    assert speicher["value"] == "256"
    laufzeit = karte.seite["laufzeit"]
    gewaehlt = produktseite.select_one(laufzeit.selektor)
    assert gewaehlt["value"] == "36-flex"
    assert wert_nach_muster(gewaehlt["value"], laufzeit.muster) is None
    assert wert_nach_muster("24-fix", laufzeit.muster) == "24"


def test_vorbereitung_wartet_bis_der_weiter_knopf_fix_traegt(karte, produktseite):
    """Fix ist erst erreicht, wenn der Warenkorb des Weiter-Knopfs (``config``) dieselbe
    Laufzeit nennt (Lauf 20.11.: sonst lag „24-flex“ im Warenkorb)."""
    (schritt,) = karte.vorbereitung
    dom = BeautifulSoup(str(produktseite), "html.parser")
    knopf = dom.select_one("#price-summary-overlay-cta")
    fix = dom.select_one(schritt.pruefe)
    assert fix["value"] == "36-fix"
    assert not soupsieve.match(schritt.bis, fix)

    fix["checked"] = "checked"
    assert not soupsieve.match(schritt.bis, fix)
    knopf["config"] = knopf["config"].replace("36-flex", "36-fix")
    assert soupsieve.match(schritt.bis, fix)


def test_gegenprobe_veralteter_warenkorb_eines_anderen_reiters(karte, produktseite):
    (schritt,) = karte.vorbereitung
    dom = BeautifulSoup(str(produktseite), "html.parser")
    dom.select_one("#contract-tab-36")["class"].append("d-none")
    dom.select_one("#contract-tab-24")["class"].remove("d-none")
    knopf = dom.select_one("#price-summary-overlay-cta")
    knopf["config"] = knopf["config"].replace("36-flex", "36-fix")
    fix = dom.select_one(schritt.pruefe)
    fix["checked"] = "checked"
    assert fix["value"] == "24-fix"
    assert not soupsieve.match(schritt.bis, fix)

    knopf["config"] = knopf["config"].replace("36-fix", "24-fix")
    assert soupsieve.match(schritt.bis, fix)


def test_sieben_sichtbare_tarifkacheln_ohne_verborgene_kopien(karte, tarifauswahl):
    assert len(tarifauswahl.select('input[name="tariff-plan"]')) == 10
    assert _werte(karte, "tarif", tarifauswahl) == list(TARIFE)


def test_antwort_je_kachel_buendel_aus_geraeterate_und_tarifpreis(karte, tarifauswahl):
    lesungen = [lies_antwort(h, karte.antwort) for h in _hinweise(karte, tarifauswahl)]

    assert [x.buendel.buendelbetrag for x in lesungen] == list(BUENDEL_512_24)
    assert [x.nachweise["tarifname"] for x in lesungen] == list(NAMEN)
    assert {x.variante["laufzeit"] for x in lesungen} == {24}
    assert {x.buendel.einmalzahlung for x in lesungen} == {0.0}
    assert {x.nachweise["geraetegesamtpreis"] for x in lesungen} == {"1392.0"}


def test_gegenprobe_ohne_tarifpreis_kein_buendel(karte, tarifauswahl):
    hinweis = _hinweise(karte, tarifauswahl)[0]
    del hinweis["tariffPricePerMonth"]

    assert lies_antwort(hinweis, karte.antwort).buendel.buendelbetrag is None


def _karte(antwort: dict, weiter: bool = True) -> object:
    roh = yaml.safe_load(KARTE.read_text(encoding="utf-8"))
    roh["antwort"] = antwort
    if not weiter:
        roh.pop("weiter")
        roh["knoepfe"]["tarif"] = {"fest": "tariff-anf-s-mvl"}
    return klickkarte_aus_daten(roh, "test")


@pytest.mark.parametrize(
    "antwort",
    [
        pytest.param({"kachel": "input", "pfade": {"buendelbetrag": "a"}}, id="ohne"),
        pytest.param(
            {"global": ["x"], "attribut": "y", "pfade": {"buendelbetrag": "x.a"}},
            id="attribut-ohne-kachel",
        ),
        pytest.param(
            {
                "kachel": "input",
                "attribut": "data-x",
                "pfade": {"buendelbetrag": {"pfad": "a", "summe": ["b.{fremd}"]}},
                "variante": {"laufzeit": "t"},
            },
            id="summe-kein-pfad",
        ),
    ],
)
def test_gegenprobe_kachelquelle_unvollstaendig(antwort):
    with pytest.raises(KlickkartenFehler):
        _karte(antwort)


def test_gegenprobe_kachelquelle_ohne_kacheln():
    antwort = {
        "kachel": "input",
        "attribut": "data-x",
        "pfade": {"buendelbetrag": "a"},
        "variante": {"laufzeit": "t"},
    }
    with pytest.raises(KlickkartenFehler, match="weiter.kacheln"):
        _karte(antwort, weiter=False)


@pytest.fixture
def seite(chromium):
    seite = chromium.new_page(viewport={"width": 1440, "height": 1000})
    seite.set_content(TARIFAUSWAHL.read_text(encoding="utf-8"))
    yield seite
    seite.close()


def test_sichtbarer_text_kachel_plus_preisleiste_gleich_antwort(karte, seite):
    """Erste Lesung aus dem sichtbaren Text (Tarifpreis der Kachel, Geräterate der
    Preisleiste), zweite aus dem JSON der Kachel: dieselben sieben Bündel."""
    leser = Textleser(seite, karte, 2_000)
    kacheln = seite.locator(karte.textlesung.selektoren[0])
    assert kacheln.count() == 7
    im_text, fundorte = [], []
    for stelle in range(7):
        text = leser.zusammenfassung(kacheln.nth(stelle))
        _, buendel, orte = leser.textwerte(text)
        im_text.append(buendel.buendelbetrag)
        fundorte.append(orte["buendelbetrag"][1])

    assert im_text == list(BUENDEL_512_24)
    assert " ".join(fundorte[0].split()) == "10, 99 €/Monat + 58,– €/Mon"
    assert "Unlimitiert" not in leser.zusammenfassung(kacheln.nth(6))


def test_gegenprobe_ohne_preisleiste_kein_bündel_im_text(karte, seite):
    seite.evaluate(f"document.querySelector('{PREISLEISTE}').remove()")
    leser = Textleser(seite, karte, 500)
    kachel = seite.locator(karte.textlesung.selektoren[0]).first

    _, buendel, orte = leser.textwerte(leser.zusammenfassung(kachel))

    assert buendel.buendelbetrag is None
    assert "buendelbetrag" not in orte


def test_quellenleser_liest_die_kachel_und_ohne_kachel_nichts(karte, seite):
    leser = Quellenleser(seite, karte, None)
    kachel = seite.locator(karte.textlesung.selektoren[0]).nth(6)
    platz = {"speicher": "512", "tarif": TARIFE[6], "laufzeit": "24"}

    gelesen = leser.lies(0, False, platz, kachel=kachel)
    ohne = leser.lies(0, False, platz)

    assert gelesen.lesung.buendel.buendelbetrag == 93.99
    assert gelesen.lesung.nachweise == {
        "tarifname": "1&1 Unlimited XL",
        "geraetegesamtpreis": "1392.0",
    }
    assert gelesen.json_pfade == {
        "buendelbetrag": "hardwarePricePerMonth + tariffPricePerMonth",
        "einmalzahlung": (
            "hardwareTotalPrice − hardwareSelectedTermMonths × hardwarePricePerMonth"
        ),
    }
    (koerper,) = json.loads(gelesen.kopie.koerper).values()
    assert koerper["hardwarePricePerMonth"] == 58.0
    assert ohne.lesung is None


def _daten(tarif: str, name: str | None, anschluss_name: str | None) -> dict:
    kombination = {
        "status": "erfasst",
        "variante": {"speicher": "512", "tarif": tarif, "laufzeit": 24},
        "werte": {},
        "buendel": {"buendelbetrag": 93.99, "einmalzahlung": None},
        "nachweise": {} if name is None else {"tarifname": name},
    }
    anschluss = {
        "art": "anschluss",
        "anschlusspreis": 39.9,
        "tarif_slug": "tariff-anf-xxl-unlimited-xl-ovl",
        **({} if anschluss_name is None else {"tarif_name": anschluss_name}),
    }
    return {
        "name": "1&1",
        "datum": "2026-11-20",
        "vertragsform": "ein_vertrag",
        "seiten": [
            {
                "adresse": "https://mobile.1und1.de/iphone-17",
                "geraet": "apple-iphone-17",
                "status": "gelesen",
                "kombinationen": [kombination],
            }
        ],
        "uebersichten": [{"status": "gelesen", "saetze": [anschluss]}],
    }


def test_anschluss_ueber_den_tarifnamen_der_kachel():
    """Unlimited XL: die Kachel nennt ``…-xl-mvl``, die Tarifdetail-Seite ``…-xl-ovl``;
    beide nennen „1&1 Unlimited XL“."""
    katalog = lade_katalog(lese_wurzel())
    daten = _daten(TARIFE[6], NAMEN[6], NAMEN[6])

    (satz,) = ausbeute(daten, katalog).rohsaetze

    assert (satz["tarif_name"], satz["anschlusspreis"]) == (NAMEN[6], 39.9)
    assert (satz["laufzeit_monate"], satz["buendel_monatlich"]) == (24, 93.99)


def test_gegenprobe_ohne_namen_bleibt_der_anschluss_offen():
    katalog = lade_katalog(lese_wurzel())
    (satz,) = ausbeute(_daten(TARIFE[6], NAMEN[6], None), katalog).rohsaetze

    assert satz["anschlusspreis"] is None


def test_fixture_traegt_keine_kennung_des_warenkorbs():
    roh = TARIFAUSWAHL.read_text(encoding="utf-8")
    assert not re.search(r"traceId=|JSESSIONID|cart[-_]?id", roh, re.I)
    assert html_modul.unescape(roh).count('"hardwareSelectedTermMonths":24') == 10


GERAETEPREIS = {
    "einsundeins_tarifauswahl_pixel11_20261120.html": (34.0, 24, 816.0),
    "einsundeins_tarifauswahl_s26ultra_20261120.html": (33.0, 36, 1188.0),
}


@pytest.fixture(params=sorted(GERAETEPREIS))
def geraeteseite(request, chromium):
    seite = chromium.new_page(viewport={"width": 1440, "height": 1000})
    seite.set_content((FIX / request.param).read_text(encoding="utf-8"))
    yield request.param, seite
    seite.close()


def test_einmalzahlung_gesamtpreis_minus_raten_aus_text_und_antwort(
    karte, geraeteseite
):
    """Entscheidung 20.11.2026: Einmalzahlung = genannter „Gesamtpreis Hardware“ minus
    Raten × Geräterate. Pixel 11 (24 × 34,– = 816,– €) und Galaxy S26 Ultra (36 × 33,–
    = 1.188,– €): gemessen 0, im Text der Preisleiste wie im JSON jeder Kachel."""
    name, seite = geraeteseite
    rate, raten, gesamt = GERAETEPREIS[name]
    leser = Textleser(seite, karte, 2_000)
    kacheln = seite.locator(karte.textlesung.selektoren[0])
    _, buendel, orte = leser.textwerte(leser.zusammenfassung(kacheln.first))
    dom = BeautifulSoup((FIX / name).read_text(encoding="utf-8"), "html.parser")
    lesungen = [lies_antwort(h, karte.antwort) for h in _hinweise(karte, dom)]

    assert raten * rate == gesamt
    assert buendel.einmalzahlung == 0.0
    assert "Gesamtpreis Hardware:" in orte["einmalzahlung"][1]
    assert len(lesungen) == 7
    assert {x.buendel.einmalzahlung for x in lesungen} == {0.0}
    assert {x.nachweise["geraetegesamtpreis"] for x in lesungen} == {str(gesamt)}


@pytest.mark.parametrize(
    ("gesamt", "erwartet"),
    [
        pytest.param("900,–", 84.0, id="genannte-zuzahlung"),
        pytest.param("800,–", None, id="negativ-ist-luecke"),
    ],
)
def test_gegenprobe_zuzahlung_und_negative_differenz(karte, chromium, gesamt, erwartet):
    seite = chromium.new_page()
    try:
        roh = (FIX / sorted(GERAETEPREIS)[0]).read_text(encoding="utf-8")
        neu = roh.replace(
            "Gesamtpreis Hardware: 816,–", f"Gesamtpreis Hardware: {gesamt}"
        )
        assert neu != roh
        seite.set_content(neu)
        leser = Textleser(seite, karte, 500)
        kachel = seite.locator(karte.textlesung.selektoren[0]).first
        _, buendel, _ = leser.textwerte(leser.zusammenfassung(kachel))
    finally:
        seite.close()
    assert buendel.einmalzahlung == erwartet


def test_gegenprobe_ohne_gesamtpreis_keine_einmalzahlung(karte, tarifauswahl):
    hinweis = _hinweise(karte, tarifauswahl)[0]
    del hinweis["hardwareTotalPrice"]
    lesung = lies_antwort(hinweis, karte.antwort)

    assert lesung.buendel.einmalzahlung is None
    assert "geraetegesamtpreis" not in lesung.nachweise


def test_einmalzahlung_null_wird_zuzahlung_null():
    """Gemessen 0 ist die Zuzahlung 0,0 (nie ``None``), damit die Gesamtkosten (#175)
    rechnen; ohne Messung bleibt sie ``None``."""
    katalog = lade_katalog(lese_wurzel())
    daten = _daten(TARIFE[0], NAMEN[0], NAMEN[0])
    ohne = ausbeute(daten, katalog).rohsaetze[0]
    daten["seiten"][0]["kombinationen"][0]["buendel"]["einmalzahlung"] = 0.0
    (satz,) = ausbeute(daten, katalog).rohsaetze

    assert (satz["geraet_zuzahlung"], satz["einmalzahlung"]) == (0.0, 0.0)
    assert ohne["geraet_zuzahlung"] is None


FLEX = FIX / "einsundeins_tarifauswahl_flex_20261120.html"


def test_gegenprobe_flex_kachel_ist_befund_mit_grund(karte, chromium):
    """„24 + 12 Monate Flex“ trägt dieselbe Laufzeitzahl 24, aber ``flex: true``
    (12 weitere Raten): keine Fix-Zeile, sondern Befund mit Grund."""
    seite = chromium.new_page()
    try:
        seite.set_content(FLEX.read_text(encoding="utf-8"))
        kachel = seite.locator(karte.textlesung.selektoren[0]).first
        platz = {"speicher": "256", "tarif": TARIFE[0], "laufzeit": "24"}
        gelesen = Quellenleser(seite, karte, None).lies(0, False, platz, kachel=kachel)
    finally:
        seite.close()
    assert gelesen.lesung is None
    assert gelesen.befund is not None
    assert gelesen.befund.grund == "Kachel nennt flex = True, verlangt False"


def test_fix_kachel_traegt_flex_false(karte, seite):
    kachel = seite.locator(karte.textlesung.selektoren[0]).first
    platz = {"speicher": "512", "tarif": TARIFE[0], "laufzeit": "24"}
    gelesen = Quellenleser(seite, karte, None).lies(0, False, platz, kachel=kachel)

    assert gelesen.befund is None
    assert karte.antwort.gleich == {"flex": False}


def _bestandszeile(geraet: str, speicher: str, zustand: str | None = None) -> dict:
    daten = _daten(TARIFE[0], NAMEN[0], NAMEN[0])
    seite = daten["seiten"][0]
    seite["geraet"] = geraet
    seite["adresse"] = f"https://mobile.1und1.de/{geraet.removeprefix('apple-')}"
    if zustand is not None:
        seite["zustand"] = zustand
    kombination = seite["kombinationen"][0]
    kombination["variante"]["speicher"] = speicher
    return daten


def test_klickzeile_traegt_die_bundle_id_des_bestands():
    """Das Bündel iPhone 17 / 256 GB / All-Net-Flat S / 24 Monate steht im Bestand mit
    der Farbe des Adapters (NEBELBLAU, erste Variante der Preiskarte, nicht die
    vorgewählte LAVENDEL): ``buendel--1-1--apple-iphone-17-256gb-nebelblau--1-1-all-
    net-flat-s--24m`` (data/state/geraete_tco.json, main c1738cfe). Die Klick-Zeile
    schreibt dasselbe Bündel fort."""
    katalog = lade_katalog(lese_wurzel())
    (satz,) = ausbeute(_bestandszeile("apple-iphone-17", "256"), katalog).rohsaetze
    neu = buendel_id(
        satz["sku_id"], satz["anbieter"], satz["tarif_name"], satz["laufzeit_monate"]
    )

    assert satz["sku_id"] == "apple-iphone-17-256gb-nebelblau"
    assert (
        neu == "buendel--1-1--apple-iphone-17-256gb-nebelblau--1-1-all-net-flat-s--24m"
    )


def test_gegenprobe_ohne_bestandsfarbe_bleibt_ohne_farbe():
    katalog = lade_katalog(lese_wurzel())
    (satz,) = ausbeute(_bestandszeile("apple-iphone-17", "512"), katalog).rohsaetze
    assert satz["sku_id"] == "apple-iphone-17-512gb-nebelblau"
    assert sku_farbe("1&1", "apple-iphone-99", 256) is None
    assert sku_farbe("Telekom", "apple-iphone-17", 256) is None


def test_gegenprobe_erneuert_bekommt_keine_bestandsfarbe():
    katalog = lade_katalog(lese_wurzel())
    daten = _bestandszeile("apple-iphone-17", "256", "refurbished")
    (satz,) = ausbeute(daten, katalog).rohsaetze
    assert (
        satz["sku_id"].endswith("ohne-farbe-refurbished")
        or "nebelblau" not in (satz["sku_id"])
    )
