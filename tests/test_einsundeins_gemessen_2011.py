"""1&1: gemessene Bündel je Speicher und Laufzeit statt hergeleiteter Tarifstufen.

DER BEFUND (Geräte-Lauf 44728882384 und Lokallauf vom 20.11.2026)
------------------------------------------------------------------
Die Geräteseite trägt seit dem 20.11.2026 je Variante die Stufen "24 Monate Fix"
und "36 Monate Fix" (`hwdVariantsHardwarePrices`). Gelesen wurde nur "fix 24";
dazu kamen 432 Sätze anderer Tarife, hergeleitet aus dem Rasteraufschlag
(`tarifaufschlag_aus_tarifraster`) und auf JEDE Speichergröße übertragen. Die
Seite selbst widerlegt diese Übertragung: der Tarifnachlass hängt am Speicher
(iPhone 17 Pro Max, fix 24: All-Net-Flat S 9,99 bei 256 GB, 13,99 bei 512 GB).

Dazu verloren die gemessenen S-Sätze ihren Messtag an die gestrigen Klick-Sätze
desselben Schlüssels ("68 Adapterbündel weichen frischer Messung"), obwohl der
Klick-Lauf seit dem Markupwechsel gestört ist und die Beträge gleich waren.

FIXTURES: die gekürzten echten Geräteseiten vom 20.11.2026 (HTTP 200,
TelcoRadar/1.0, robots.txt erlaubt; Herkunft in
`test_geraete_tarifstufen_einsundeins_2011.py` bis 20.11.2026, jetzt hier), die
Geräteraster S/M und die Übersicht `/all-net-flat-vergleich` desselben Tages.
Die erwarteten Beträge sind Geräterate plus Tarifrate der "fix"-Stufe, von Hand
aus der Preiskarte abgelesen; die Geräteraten der Vorauswahl stehen sichtbar in
den Laufzeitschaltern ("24 Monate Fix 46,–").
"""

import gzip
from pathlib import Path

import pytest

from telco_radar import rechenweise
from telco_radar.analyze.buendel_abdeckung import pruefe
from telco_radar.analyze.klick_messtag import teile_nach_messtag
from telco_radar.collect.geraete import einsundeins as E
from telco_radar.tco_model import Buendel

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_TAG = "2026-11-20"

GEMESSEN = {
    "iphone_17": {
        (256, 24): 57.99,
        (256, 36): 42.99,
        (512, 24): 68.99,
        (512, 36): 49.99,
    },
    "iphone_17e": {(256, 24): 49.99, (256, 36): 37.99},
    "iphone_17_pro": {
        (256, 24): 59.99,
        (256, 36): 44.99,
        (512, 24): 70.99,
        (512, 36): 51.99,
    },
    "iphone_17_pro_max": {
        (256, 24): 67.99,
        (256, 36): 49.99,
        (512, 24): 81.99,
        (512, 36): 58.99,
        (1024, 24): 92.99,
        (1024, 36): 65.99,
        (2048, 24): 112.99,
        (2048, 36): 78.99,
    },
    "iphone_18_pro": {
        (256, 24): 72.99,
        (256, 36): 52.99,
        (512, 24): 83.99,
        (512, 36): 59.99,
        (1024, 24): 104.99,
        (1024, 36): 73.99,
        (2048, 24): 136.99,
        (2048, 36): 94.99,
    },
    "iphone_18_pro_max": {
        (256, 24): 74.99,
        (256, 36): 54.99,
        (512, 24): 85.99,
        (512, 36): 61.99,
        (1024, 24): 106.99,
        (1024, 36): 75.99,
        (2048, 24): 138.99,
        (2048, 36): 96.99,
    },
    "iphone_duo": {
        (256, 24): 109.99,
        (256, 36): 77.99,
        (512, 24): 120.99,
        (512, 36): 84.99,
        (1024, 24): 141.99,
        (1024, 36): 98.99,
        (2048, 24): 173.99,
        (2048, 36): 119.99,
    },
    "galaxy_s26": {
        (256, 24): 44.99,
        (256, 36): 34.99,
        (512, 24): 53.99,
        (512, 36): 40.99,
    },
}

SICHTBAR = {
    "iphone_17": {24: 46.0, 36: 30.0},
    "iphone_17e": {24: 36.0, 36: 24.0},
    "iphone_17_pro": {24: 50.0, 36: 33.0},
    "iphone_17_pro_max": {24: 58.0, 36: 38.0},
    "iphone_18_pro": {24: 60.0, 36: 40.0},
    "iphone_18_pro_max": {24: 66.0, 36: 44.0},
    "iphone_duo": {24: 100.0, 36: 66.0},
    "galaxy_s26": {24: 36.0, 36: 24.0},
}

MODELLE = sorted(GEMESSEN)

_NETZ = {
    "https://mobile.1und1.de/all-net-flat-vergleich": (
        f"einsundeins_tarifuebersicht_all_net_flat_{_TAG}.html.gz"
    ),
    "https://mobile.1und1.de/smartphones-all-net-flat-s": (
        f"einsundeins_tarifraster_all_net_flat_s_{_TAG}.html.gz"
    ),
    "https://mobile.1und1.de/smartphones-all-net-flat-m": (
        f"einsundeins_tarifraster_all_net_flat_m_{_TAG}.html.gz"
    ),
}


def _fixture(name: str) -> str:
    return gzip.open(_FIX / name, "rb").read().decode("utf-8", "replace")


def _seite(modell: str) -> str:
    return _fixture(f"einsundeins_produktseite_{modell}_{_TAG}.html.gz")


def _url(modell: str) -> str:
    return "https://mobile.1und1.de/" + modell.replace("_", "-")


@pytest.mark.parametrize("modell", MODELLE)
def test_jede_groesse_mal_beide_laufzeiten_gemessen(modell):
    """Je Speichergröße ein Satz für 24 und für 36 Monate, Betrag = Geräterate
    plus Tarifrate der "fix"-Stufe, Tarif der Seite, keine Herleitung."""
    saetze = E.lies_buendel(_seite(modell), url=_url(modell))
    gelesen = {
        (s["speicher_gb"], s["laufzeit_monate"]): s["buendel_monatlich"] for s in saetze
    }
    assert gelesen == GEMESSEN[modell]
    assert len(saetze) == len(GEMESSEN[modell])
    assert {s["tarif_name"] for s in saetze} == {"1&1 All-Net-Flat S"}
    assert not any(s.get("herleitung") for s in saetze)


@pytest.mark.parametrize("modell", MODELLE)
def test_die_sichtbaren_schalter_nennen_die_geraeterate_der_karte(modell):
    """Gegenprobe gegen den sichtbaren Seitentext: die Laufzeitschalter der
    Vorauswahl ("24 Monate Fix", "36 Monate Fix") nennen genau die Geräterate,
    die im Satz der vorausgewählten Variante steckt."""
    text = _seite(modell)
    assert E.sichtbare_geraeteraten(text) == SICHTBAR[modell]
    var = E.variante(text)
    eintrag = E._hardwarepreiskarte(text)[f"product-{var['color']}-{var['size']}"]
    for dauer, rate in SICHTBAR[modell].items():
        assert E._fixpreis(eintrag, dauer)[0] == rate


@pytest.mark.parametrize("modell", MODELLE)
def test_widerspricht_ein_schalter_der_karte_entfaellt_die_laufzeit(modell):
    """Zeigt die Seite für 24 Monate eine andere Rate als die Preiskarte, ist
    die Laufzeit auf dieser Seite unbelegt; 36 Monate bleiben."""
    rate = SICHTBAR[modell][24]
    alt = f'data-monthly-amount="{rate:.0f}"\n'
    text = _seite(modell)
    stelle = text.index('value="24-fix"')
    anfang = text.rindex(alt, 0, stelle)
    text = text[:anfang] + 'data-monthly-amount="1"\n' + text[anfang + len(alt) :]
    saetze = E.lies_buendel(text, url=_url(modell))
    assert {s["laufzeit_monate"] for s in saetze} == {36}
    erwartet = {k: v for k, v in GEMESSEN[modell].items() if k[1] == 36}
    assert {(s["speicher_gb"], 36): s["buendel_monatlich"] for s in saetze} == erwartet


class _Hole:
    """Die gespeicherten Antworten vom 20.11.2026; alles andere ist 404."""

    def __init__(self):
        self.abgerufen: list = []

    def __call__(self, url, kopfzeilen=None, **kw):
        self.abgerufen.append(url)
        if url not in _NETZ:
            return (404, "")
        return (200, _fixture(_NETZ[url]))


@pytest.mark.parametrize("modell", MODELLE)
def test_der_haken_leitet_keine_tarifstufe_mehr_her(modell):
    """Mit den echten Rastern S und M im Netz entstand bis 20.11.2026 je Gerät
    ein hergeleiteter M-Satz. Jetzt bleibt es bei den gemessenen Sätzen, und
    kein Raster wird abgerufen."""
    saetze = [
        {**s, "anbieter": "1&1", "sku_id": s["titel"]}
        for s in E.lies_buendel(_seite(modell), url=_url(modell))
    ]
    ohne_details = {"tarifdetails_url", "anschlusspreis"}
    vorher = [{k: v for k, v in s.items() if k not in ohne_details} for s in saetze]
    hole = _Hole()
    E.ergaenze_buendel(hole, {}, saetze)
    nachher = [{k: v for k, v in s.items() if k not in ohne_details} for s in saetze]
    assert nachher == vorher
    assert not [a for a in hole.abgerufen if "/smartphones-" in a]


@pytest.mark.parametrize("modell", MODELLE)
def test_der_tarifslug_kommt_aus_dem_datalayer(modell):
    """Seit K1 nennt die Seite den Slug nur noch im Datalayer (`tariff.name`);
    ohne ihn fand kein Satz seine Tarifdetails und damit keine
    Bereitstellungsgebühr."""
    saetze = E.lies_buendel(_seite(modell), url=_url(modell))
    assert {s["tarif_slug"] for s in saetze} == {"tariff-anf-s-mvl"}


def test_die_bereitstellungsgebuehr_kommt_ueber_die_uebersicht():
    """Ein Abruf der Übersicht findet den Iframe zum Slug, ein Abruf des
    Iframes die Gebühr "Tarif mit Smartphone" (39,90 €) - für alle Sätze."""
    saetze = [
        {**s, "anbieter": "1&1"}
        for m in MODELLE
        for s in E.lies_buendel(_seite(m), url=_url(m))
    ]
    details = (
        "https://mobile.1und1.de/details-all-net-flat-preisliste?chosenTariff="
        "tariff-anf-s-mvl&chosenNet=1u1&lightbox=true&bk=false"
    )
    netz = {
        E.TARIFUEBERSICHT: _fixture(_NETZ[E.TARIFUEBERSICHT]),
        details: _fixture("einsundeins_tarifdetails_anf_s.html.gz"),
    }
    abgerufen: list = []

    def hole(url, kopfzeilen=None, **kw):
        abgerufen.append(url)
        return (200, netz[url]) if url in netz else (404, "")

    assert E.ergaenze_buendel(hole, {}, saetze) == len(saetze)
    assert {s["anschlusspreis"] for s in saetze} == {39.9}
    assert abgerufen == [E.TARIFUEBERSICHT, details]


def test_der_tarifnachlass_haengt_am_speicher():
    """Warum keine Herleitung: dieselbe Seite nennt für All-Net-Flat S je
    Speicher eine andere Tarifrate - ein auf alle Größen übertragener Aufschlag
    wäre unbelegt."""
    karte = E._hardwarepreiskarte(_seite("iphone_17_pro_max"))
    tarif = {
        gb: karte[f"product-COSMIC_ORANGE-{gb}"]["24"]["fix"]["tariffPricePerMonth"]
        for gb in (256, 512)
    }
    assert tarif == {256: "9.99", 512: "13.99"}


def test_eine_ratensumme_zu_anderer_laufzeit_zaehlt_nicht():
    """Nennt die "fix 36"-Stufe eine Ratensumme, die nicht 36 Raten ergibt, ist
    der Betrag einer anderen Laufzeit und bleibt offen."""
    stufe = {
        "hardwarePricePerMonth": "30.00",
        "hardwareTotalPrice": "1440.00",
        "tariffPricePerMonth": "12.99",
        "tariffMonthlyPrices": [{"amount": 12.99, "begin": 1, "end": 36}],
    }
    assert E._fixpreis({"36": {"fix": stufe}}, 36) is None
    stufe["hardwareTotalPrice"] = "1080.00"
    assert E._fixpreis({"36": {"fix": stufe}}, 36) == (30.0, 12.99)


def _buendel(anbieter: str, betrag: float) -> Buendel:
    return Buendel(
        sku_id="apple-iphone-17-256gb-nebelblau",
        anbieter=anbieter,
        tarif_name="1&1 All-Net-Flat S",
        buendel_monatlich=betrag,
        laufzeit_monate=24,
        quelle_url="https://mobile.1und1.de/iphone-17",
        abgerufen_am="2026-11-20",
        zustand="neu",
    )


def _klickeintrag(betrag: float, tag: str) -> dict:
    return {"quelle_art": "klick", "abgerufen_am": tag, "buendel_monatlich": betrag}


@pytest.mark.parametrize(
    ("anbieter", "klickbetrag", "klicktag", "bleibt"),
    [
        ("1&1", 57.99, "2026-11-19", True),
        ("1&1", 62.99, "2026-11-19", True),
        ("1&1", 57.99, "2026-11-20", False),
        ("Telekom", 57.99, "2026-11-19", False),
    ],
    ids=["1und1-gestern-gleich", "1und1-gestern-anders", "1und1-heute", "telekom"],
)
def test_nur_eine_heutige_klickmessung_nimmt_1und1_den_messtag(
    anbieter, klickbetrag, klicktag, bleibt
):
    """Am 20.11.2026 wichen alle gemessenen S-Sätze den Klick-Sätzen vom Vortag
    (altes Angebot 24+12, Klick-Lauf seitdem gestört): gleiche Beträge kosteten
    den Messtag, gesenkte Preise (72,99 -> 68,99) ebenso. Bei 1&1 hat jetzt nur
    eine Klick-Messung von heute Vorrang; bei Telekom gilt die alte Regel."""
    satz = _buendel(anbieter, 57.99)
    eintrag = _klickeintrag(klickbetrag, klicktag)
    teile = teile_nach_messtag(
        [satz], lambda _id: eintrag, "2026-11-20", lambda _s: None
    )
    assert (satz in teile.bleiben) is bleibt
    assert (len(teile.gewichen) == 0) is bleibt


def test_die_neue_lesart_ist_ein_bruch_der_rechenweise_kein_preissprung():
    """Bis 19.11.2026 stand unter "36 Monate" das Angebot 24+12 mit
    Schlusszahlung (Pixel 11 256 GB: 37,99 €/Monat plus 280 €), seit 20.11.2026
    "36 Monate Fix" ohne Schlusszahlung (32,99 €). Das ist eine neue Lesart,
    keine Preisbewegung: der Abdeckungswächter meldete sonst acht Preissprünge
    über 25 %."""
    satz = _buendel("1&1", 32.99)
    assert rechenweise.felder(satz) == {rechenweise.FELD: 2}
    bid = "buendel--1-1--google-pixel-11-256gb-frost--1-1-all-net-flat-s--36m"
    historie = [
        {"id": bid, "datum": "2026-11-19", "gesamt": 1687.54, "zustand": "neu"},
        {
            "id": bid,
            "datum": "2026-11-20",
            "gesamt": 1227.54,
            "zustand": "neu",
            **rechenweise.felder(satz),
        },
    ]
    tco = {
        "updated": "2026-11-20",
        "buendel": [
            {
                "anbieter": "1&1",
                "sku_id": "google-pixel-11-256gb-frost",
                "tarif_name": "1&1 All-Net-Flat S",
                "laufzeit_monate": 36,
                "last_verified": "2026-11-20",
                "zustand": "neu",
            }
        ],
    }
    pflicht = {
        "anbieter": ["1&1"],
        "modelle": ["google-pixel-11"],
        "luecken": {},
        "speicher_pflicht_anbieter": [],
    }
    assert [b.art for b in pruefe(tco, historie, pflicht).befunde] == []
    historie[1].pop(rechenweise.FELD)
    assert [b.art for b in pruefe(tco, historie, pflicht).befunde] == ["preissprung"]
