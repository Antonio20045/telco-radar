"""1&1-Rastersätze im Klick-Rohsatz: Speicher gemessen, Anschluss nach Tarifname.

Produktseiten-Sätze: zweite Lesung der Globalen ``hwdVariantsPrices`` gespeicherter
Produktseiten (iPhone 17 Pro 08.09., iPhone 18 Pro und Galaxy S26 Ultra 29.09.) mit
der Karte ``config/klickkarten/1und1.yaml``. Raster und Tarifdetail-Seite über die
Lesart der Übersicht. Wo ein Test einen Wert ändert, sagt es sein Name.
"""

from __future__ import annotations

import re
from dataclasses import replace

import pytest
from bestand_pfad import lese_wurzel
from klickergebnisse import (
    EINSUNDEINS_KARTE,
    EINSUNDEINS_SEITE,
    erfasst,
    ergebnisdatei,
    lauf,
)
from test_klick_anschluss_1und1 import DETAILS_M, DETAILS_S, HEUTE
from test_klick_raster_1und1 import DATEIEN, RASTER, text

from telco_radar.analyze.klick_zusammenfuehrung import zusammenfuehren
from telco_radar.collect.geraete.einsundeins import (
    ergaenze_bereitstellungsgebuehr,
    ergaenze_tarifstufen,
    lies_buendel,
)
from telco_radar.collect.geraete.klickantwort import lies_antwort
from telco_radar.collect.geraete.klickergebnis import schreibe
from telco_radar.collect.geraete.klicklauf import LAUF_GELESEN, LAUF_GESTOERT
from telco_radar.collect.geraete.klickraster import HERLEITUNG_SCHLUSSZAHLUNG
from telco_radar.collect.geraete.klickrohsatz import ausbeute
from telco_radar.collect.geraete.klickuebersicht import LESARTEN
from telco_radar.collect.geraete.klickziele import Seitenziel
from telco_radar.geraete_config import lade_katalog
from telco_radar.geraete_model import sku_id
from telco_radar.report.geraete_notbremse import HERLEITUNG_SATZ
from telco_radar.report.geraete_tco_karten import geraet_aus_sku

_PREISE = re.compile(r"hwdVariantsPrices\s*=\s*\{(.*?)\};", re.S)
_EINTRAG = re.compile(r"'product-([A-Z_]+)-(\d+)'\s*:\s*\[\s*(\d+)\s*,?\s*\]")
_LAUFZEIT = re.compile(r"window\.currentHardwareOfferDuration\s*=\s*'(\d+)'")
IPHONE_17 = ("einsundeins_produktseite_iphone_17_pro.html.gz", EINSUNDEINS_SEITE)
IPHONE_18 = (
    "einsundeins_produktseite_iphone_18_pro_2026-09-29.html.gz",
    Seitenziel("apple-iphone-18-pro", None, "https://mobile.1und1.de/iphone-18-pro"),
)
S26_ULTRA = (
    "einsundeins_produktseite_galaxy_s26_ultra_2026-09-29.html.gz",
    Seitenziel(
        "samsung-galaxy-s26-ultra",
        None,
        "https://mobile.1und1.de/samsung-galaxy-s26-ultra",
    ),
)
S_SLUG = "tariff-anf-s-mvl"


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


def produktseite(
    geraet: tuple[str, Seitenziel], einmal: float | None = None, **betrag: float
):
    datei, ziel = geraet
    html = text(datei)
    preise = _PREISE.search(html)
    laufzeit = _LAUFZEIT.search(html)
    assert preise is not None and laufzeit is not None
    eintraege = _EINTRAG.findall(preise[1])
    globale = {
        "hwdVariantsPrices": {
            f"product-{farbe}-{gb}": [int(cent)] for farbe, gb, cent in eintraege
        },
        "currentHardwareOfferDuration": laufzeit[1],
    }
    farbe = eintraege[0][0]
    kombinationen = []
    for gb in sorted({int(gb) for _, gb, _ in eintraege}):
        platz = {"speicher": str(gb), "tarif": S_SLUG, "laufzeit": "36", "farbe": farbe}
        lesung = lies_antwort(globale, EINSUNDEINS_KARTE.antwort, None, platz)
        if f"gb{gb}" in betrag:
            buendel = replace(lesung.buendel, buendelbetrag=betrag[f"gb{gb}"])
            lesung = replace(lesung, buendel=buendel)
        if einmal is not None:
            buendel = replace(lesung.buendel, einmalzahlung=einmal)
            lesung = replace(lesung, buendel=buendel)
        kombinationen.append(erfasst(lesung, str(gb), S_SLUG, 36))
    return ziel, lauf(ziel, kombinationen)


def uebersicht(adresse: str, inhalt: str, status: str = LAUF_GELESEN) -> dict:
    saetze = LESARTEN["1&1"].saetze(inhalt, adresse) if status == LAUF_GELESEN else []
    return {"adresse": adresse, "status": status, "saetze": saetze}


def raster(adresse: str, status: str = LAUF_GELESEN) -> dict:
    return uebersicht(adresse, text(DATEIEN[adresse]), status)


def details(adresse: str, tarif: str) -> dict:
    inhalt = text("einsundeins_tarifdetails_anf_s.html.gz")
    return uebersicht(adresse, inhalt.replace("1&1 All-Net-Flat S", tarif))


def klickdatei(seiten: list, *uebersichten: dict) -> dict:
    daten = ergebnisdatei("1&1", "1und1", seiten, HEUTE, vertragsform="ein_vertrag")
    return {**daten, "uebersichten": list(uebersichten)}


def rastersaetze(aus, geraet: str) -> list[dict]:
    return [
        s
        for s in aus.rohsaetze
        if s["device_id"] == geraet and s["quelle_url"].endswith("?tariffFirst=true")
    ]


def test_speicher_passt_genau_eine_groesse(katalog):
    daten = klickdatei([produktseite(IPHONE_18)], raster(RASTER[0]), raster(RASTER[1]))

    aus = ausbeute(daten, katalog)

    (satz,) = rastersaetze(aus, "apple-iphone-18-pro")
    assert satz["speicher_gb"] == 256
    assert satz["sku_id"] == sku_id("apple-iphone-18-pro", 256, None, "neu")
    assert satz["tarif_name"] == "1&1 All-Net-Flat M"
    assert satz["laufzeit_monate"] == 36
    assert satz["buendel_monatlich"] == 54.99
    assert (
        satz["quelle_url"] == "https://mobile.1und1.de/iphone-18-pro?tariffFirst=true"
    )
    assert satz["quelle_art"] == "klick" and satz["beleg_status"] == "offen"
    assert satz["abgerufen_am"] == HEUTE
    assert satz["anschlusspreis"] is None


def test_speicher_passt_keine_groesse_ist_luecke(katalog):
    daten = klickdatei([produktseite(S26_ULTRA)], raster(RASTER[0]), raster(RASTER[1]))

    aus = ausbeute(daten, katalog)

    assert rastersaetze(aus, "samsung-galaxy-s26-ultra") == []
    assert aus.luecken["buendel_mit_zubehoer"] == 25
    assert aus.luecken["speicher_unbekannt"] == 11


def test_speicher_mehrdeutig_ist_luecke(katalog):
    seite = produktseite(IPHONE_18, gb512=49.99)
    daten = klickdatei([seite], raster(RASTER[0]), raster(RASTER[1]))

    aus = ausbeute(daten, katalog)

    assert rastersaetze(aus, "apple-iphone-18-pro") == []


def test_ohne_produktseite_ist_speicher_luecke(katalog):
    daten = klickdatei([], raster(RASTER[0]), raster(RASTER[1]))

    aus = ausbeute(daten, katalog)

    assert aus.rohsaetze == []
    assert aus.luecken["speicher_unbekannt"] == 11
    assert aus.luecken["buendel_mit_zubehoer"] == 25
    assert aus.luecken["geraet_unbekannt"] == 7
    assert sum(aus.luecken.values()) == 43


def test_ohne_raster_s_ist_speicher_luecke(katalog):
    daten = klickdatei([produktseite(IPHONE_18)], raster(RASTER[1]))

    aus = ausbeute(daten, katalog)

    assert rastersaetze(aus, "apple-iphone-18-pro") == []


def test_gestoertes_raster_s_misst_nichts(katalog):
    daten = klickdatei(
        [produktseite(IPHONE_18)],
        raster(RASTER[0], LAUF_GESTOERT),
        raster(RASTER[1]),
    )

    aus = ausbeute(daten, katalog)

    assert rastersaetze(aus, "apple-iphone-18-pro") == []


def test_raster_s_wird_kein_rohsatz(katalog):
    daten = klickdatei([produktseite(IPHONE_18)], raster(RASTER[0]))

    aus = ausbeute(daten, katalog)

    assert rastersaetze(aus, "apple-iphone-18-pro") == []
    assert len(aus.rohsaetze) == 4
    assert {s["tarif_name"] for s in aus.rohsaetze} == {S_SLUG}
    assert dict(aus.luecken) == {}


def test_alle_sechs_tarife_fuer_ein_geraet(katalog):
    daten = klickdatei([produktseite(IPHONE_18)], *(raster(a) for a in RASTER))

    aus = ausbeute(daten, katalog)

    saetze = rastersaetze(aus, "apple-iphone-18-pro")
    assert sorted((s["tarif_name"], s["buendel_monatlich"]) for s in saetze) == [
        ("1&1 All-Net-Flat L", 59.99),
        ("1&1 All-Net-Flat M", 54.99),
        ("1&1 Unlimited XL", 74.99),
        ("1&1 Unlimited on demand L", 64.99),
        ("1&1 Unlimited on demand M", 59.99),
        ("1&1 Unlimited on demand S", 54.99),
    ]
    assert {s["speicher_gb"] for s in saetze} == {256}


def test_anschluss_nach_tarifname(katalog):
    daten = klickdatei(
        [produktseite(IPHONE_18)],
        details(DETAILS_S, "1&1 All-Net-Flat S"),
        details(DETAILS_M, "1&1 All-Net-Flat M"),
        raster(RASTER[0]),
        raster(RASTER[1]),
        raster(RASTER[2]),
    )

    aus = ausbeute(daten, katalog)

    preise = {
        s["tarif_name"]: s["anschlusspreis"]
        for s in rastersaetze(aus, "apple-iphone-18-pro")
    }
    assert preise == {"1&1 All-Net-Flat M": 39.9, "1&1 All-Net-Flat L": None}
    assert {
        s["anschlusspreis"] for s in aus.rohsaetze if s["tarif_name"] == S_SLUG
    } == {39.9}


def test_anschluss_einer_gestoerten_detailseite_gilt_nicht(katalog):
    gestoert = {**details(DETAILS_M, "1&1 All-Net-Flat M"), "status": LAUF_GESTOERT}
    daten = klickdatei(
        [produktseite(IPHONE_18)], gestoert, raster(RASTER[0]), raster(RASTER[1])
    )

    (satz,) = rastersaetze(ausbeute(daten, katalog), "apple-iphone-18-pro")

    assert satz["anschlusspreis"] is None


def _adapter(anschluss: str) -> list[dict]:
    html = text("einsundeins_produktseite_iphone_17_pro.html.gz")
    saetze = [
        {**r, "anbieter": "1&1", "zustand": "neu"}
        for r in lies_buendel(html, EINSUNDEINS_SEITE.adresse)
    ]
    netz = {
        "https://mobile.1und1.de/all-net-flat-vergleich": text(
            "einsundeins_tarifuebersicht_all_net_flat_2026-09-29.html.gz"
        ),
        "https://mobile.1und1.de/unbegrenztes-datenvolumen": text(
            "einsundeins_tarifuebersicht_unlimited_2026-09-29.html.gz"
        ),
        **{a: text(DATEIEN[a]) for a in RASTER[:2]},
    }

    def hole(url, kopfzeilen=None):
        if "details-" in url:
            return 200, anschluss
        return (200, netz[url]) if url in netz else (404, "")

    assert ergaenze_tarifstufen(hole, {}, saetze) > 0
    ergaenze_bereitstellungsgebuehr(hole, {}, saetze)
    return [
        {**s, "sku_id": sku_id("apple-iphone-17-pro", s["speicher_gb"], s["farbe"])}
        for s in saetze
        if s["tarif_name"] == "1&1 All-Net-Flat M" and s["speicher_gb"] == 256
    ]


@pytest.mark.parametrize(
    ("produktseite_da", "details_da", "ersetzt"),
    [(True, True, True), (True, False, False), (False, True, False)],
    ids=["gemessen-und-anschluss", "ohne-anschluss", "ohne-speicher"],
)
def test_rastersatz_ersetzt_adaptersatz_all_net_flat_m(
    katalog, tmp_path, produktseite_da, details_da, ersetzt
):
    anschluss = text("einsundeins_tarifdetails_anf_s.html.gz")
    (alt,) = _adapter(anschluss)
    assert alt["herleitung"] == "tarifaufschlag_aus_tarifraster"
    assert (alt["buendel_monatlich"], alt["laufzeit_monate"]) == (49.99, 36)
    seiten = [produktseite(IPHONE_17)] if produktseite_da else []
    uebersichten = [raster(RASTER[0]), raster(RASTER[1])]
    if details_da:
        uebersichten.insert(0, details(DETAILS_M, "1&1 All-Net-Flat M"))
    schreibe(tmp_path / "1und1.json", klickdatei(seiten, *uebersichten))

    zug = zusammenfuehren(
        [alt],
        tmp_path,
        lese_wurzel(),
        katalog,
        HEUTE,
        lambda sku: geraet_aus_sku(sku, katalog),
    )

    m = [s for s in zug.rohsaetze if s["tarif_name"] == "1&1 All-Net-Flat M"]
    neu = [s for s in m if s.get("quelle_art") == "klick"]
    assert zug.bilanz["mehrdeutig"] == []
    if not ersetzt:
        assert alt in zug.rohsaetze and zug.bilanz["ersetzt"] == 0
        return
    (satz,) = m
    assert satz in neu and satz["sku_id"] == alt["sku_id"]
    assert (satz["buendel_monatlich"], satz["anschlusspreis"]) == (49.99, 39.9)
    assert (
        satz["quelle_url"] == "https://mobile.1und1.de/iphone-17-pro?tariffFirst=true"
    )
    assert "herleitung" not in satz
    assert zug.bilanz["ersetzt"] == 1 and zug.bilanz["gegenprobe"]["gleich"] == 1


def _ganz(eintrag: dict, erkannt=None) -> dict:
    saetze = eintrag["saetze"] if erkannt is None else eintrag["saetze"][:erkannt]
    return {**eintrag, "saetze": saetze, "vollstaendig": True}


def test_rastergeraet_ist_angeboten(katalog):
    voll = _ganz(raster(RASTER[0]))
    bekannt = [s for s in voll["saetze"] if "iPhone 18 Pro" in s["titel"]]
    daten = klickdatei([], {**voll, "saetze": bekannt})

    aus = ausbeute(daten, katalog)

    assert "apple-iphone-18-pro" in aus.angeboten
    assert aus.nicht_im_angebot is not None
    assert "apple-iphone-18-pro" not in aus.nicht_im_angebot
    assert "apple-iphone-17-pro" in aus.nicht_im_angebot


def test_unbekanntes_rastergeraet_laesst_angebot_offen(katalog):
    daten = klickdatei([], _ganz(raster(RASTER[0])), _ganz(raster(RASTER[1])))

    aus = ausbeute(daten, katalog)

    assert "apple-iphone-18-pro" in aus.angeboten
    assert aus.nicht_im_angebot is None


def test_anschlussseite_zaehlt_nicht_als_geraet(katalog):
    voll = _ganz(raster(RASTER[0]))
    bekannt = [s for s in voll["saetze"] if "iPhone 18 Pro" in s["titel"]]
    detail = _ganz(details(DETAILS_S, "1&1 All-Net-Flat S"))
    daten = klickdatei([], detail, {**voll, "saetze": bekannt})

    aus = ausbeute(daten, katalog)

    assert aus.nicht_im_angebot is not None
    assert "apple-iphone-18-pro" not in aus.nicht_im_angebot


def test_schlusszahlung_kommt_vom_grundtarif(katalog):
    seite = produktseite(IPHONE_18, einmal=410.0)
    daten = klickdatei([seite], raster(RASTER[0]), raster(RASTER[1]))

    aus = ausbeute(daten, katalog)

    (satz,) = rastersaetze(aus, "apple-iphone-18-pro")
    assert satz["geraet_zuzahlung"] == 410.0
    assert satz["herleitung"] == HERLEITUNG_SCHLUSSZAHLUNG
    assert HERLEITUNG_SCHLUSSZAHLUNG in HERLEITUNG_SATZ
    grund = [s for s in aus.rohsaetze if s["tarif_name"] == S_SLUG]
    assert {s["geraet_zuzahlung"] for s in grund} == {410.0}
    assert all("herleitung" not in s for s in grund)


def test_ohne_schlusszahlung_am_grundtarif_bleibt_sie_offen(katalog):
    daten = klickdatei([produktseite(IPHONE_18)], raster(RASTER[0]), raster(RASTER[1]))

    (satz,) = rastersaetze(ausbeute(daten, katalog), "apple-iphone-18-pro")

    assert satz["geraet_zuzahlung"] is None
    assert "herleitung" not in satz


def test_schlusszahlung_nur_mit_gemessenem_speicher(katalog):
    seite = produktseite(S26_ULTRA, einmal=300.0)
    daten = klickdatei([seite], raster(RASTER[0]), raster(RASTER[1]))

    aus = ausbeute(daten, katalog)

    assert rastersaetze(aus, "samsung-galaxy-s26-ultra") == []
