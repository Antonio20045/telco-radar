"""Soll/Ist Stufe 2: Vergleich auf Angebotsebene und die Seitenzeile „Angebote“.

Abnahmekriterium 1 (Antonio, 21.11.2026): je Anbieter „Telekom: 1 240 von 1 262
Angeboten erfasst · 22 Lücken“, Soll aus der Angebotszählung im Browser. Diese Tests
brauchen nur Module, die es vor Stufe 2 gab (``geraete_vollstaendigkeit``,
``report.geraete_vollstaendigkeit``), und sind gegen den Stand vor Stufe 2 fachlich
rot: dort verglich die Ist-Zählung Bündel-IDs wörtlich („… mit 150 GB (24 Mon.)“ und
„… mit 150 GB“ waren zwei Angebote), und die Seite kannte keine Angebotszeile.
"""

from __future__ import annotations

import copy

from telco_radar.geraete_vollstaendigkeit import (
    SichtbareAuswahl,
    Signale,
    baue,
    haenge_kombinationen_ein,
    ist_zaehlung,
)
from telco_radar.report import geraete_vollstaendigkeit as seite

TAG = "2026-11-21"


def _b(anbieter: str, sku: str, tarif_slug: str, laufzeit: int = 24) -> dict:
    return {
        "id": f"buendel--x--{sku}--{tarif_slug}--{laufzeit}m",
        "sku_id": sku,
        "anbieter": anbieter,
        "tarif_id": tarif_slug,
        "laufzeit_monate": laufzeit,
        "abgerufen_am": TAG,
    }


def test_ist_vergleicht_den_grundtarif_nicht_die_schreibweise_der_messung():
    """„O2 Mobile L Plus mit 150 GB+ (24 Mon.)“ und „… mit 150 GB+“ sind auf der
    Seite EIN Tarif; die Seite nennt ihn „O2 Mobile L Plus mit 150 GB+“."""
    sku = "apple-iphone-17-256gb-schwarz"
    buendel = [
        _b("o2", sku, "o2-mobile-l-plus-mit-150-gb-24-mon"),
        _b("o2", sku, "o2-mobile-l-plus-mit-150-gb"),
        _b("o2", sku, "o2-mobile-special-24-mon", 36),
    ]
    ist = ist_zaehlung(buendel, TAG)["o2"]
    assert ist.kombinationen == {
        "apple-iphone-17-256gb--o2-mobile-l-plus--24m",
        "apple-iphone-17-256gb--o2-mobile-special--36m",
    }
    assert ist.zahlen()["buendel"] == 3


def test_tarifwelt_varianten_gleichen_namens_werden_durchgezaehlt():
    """Fünfmal „Mobile Unlimited L Promo“ in der Tarifwelt sind fünf Angebote."""
    sku = "apple-iphone-17-256gb-schwarz"
    netz = "Saturn/MediaMarkt · o2-Netz"
    buendel = [
        _b(netz, sku, "mobile-unlimited-l-promo"),
        _b(netz, sku, "mobile-unlimited-l-promo-86c58f"),
        _b(netz, sku, "mobile-unlimited-l-promo-86c591"),
    ]
    assert ist_zaehlung(buendel, TAG)[netz].kombinationen == {
        "apple-iphone-17-256gb--mobile-unlimited-l-promo--24m",
        "apple-iphone-17-256gb--mobile-unlimited-l-promo~2--24m",
        "apple-iphone-17-256gb--mobile-unlimited-l-promo~3--24m",
    }
    weniger = ist_zaehlung(buendel[:2], TAG)[netz].kombinationen
    assert len(weniger) == 2


def _voll_mit_angeboten() -> dict:
    sku = "apple-iphone-17-256gb-schwarz"
    buendel = [
        _b("Telekom", sku, f"magentamobil-{t}", n) for t in ("m", "l") for n in (24, 36)
    ]
    voll = baue(TAG, f"{TAG}T04:00:00+00:00", buendel, {}, Signale())
    auswahl = SichtbareAuswahl(
        anbieter="Telekom",
        modell="apple-iphone-17",
        seite="https://www.telekom.de/shop/geraet/apple/apple-iphone-17/schwarz-256-gb",
        speicher=("256gb", "512gb"),
        tarife=("magentamobil-m", "magentamobil-l"),
        laufzeiten=(24, 36),
        gezaehlt_um=f"{TAG}T00:20:00+00:00",
    )
    haenge_kombinationen_ein(
        voll,
        "Telekom",
        [auswahl],
        buendel,
        Signale(),
        grund=lambda k: "Bei Telekom nur mit 256 GB gelesen (21.11.2026)",
        quelle={"art": "browser_auswahl", "gezaehlt_um": f"{TAG}T00:20:00+00:00"},
    )
    for z in voll["anbieter"]:
        z["angebot"] = {
            "status": "gelesen",
            "nicht_gezaehlt": [],
            "nicht_gezaehlt_zahl": 0,
        }
    return {"vollstaendigkeit": voll}


def test_die_zeile_nennt_angebote_als_wichtigste_zahl():
    lauf = _voll_mit_angeboten()
    telekom = seite.zeilen(lauf, TAG)["zeilen"][0]
    k = lauf["vollstaendigkeit"]["anbieter"][0]["ebenen"]["kombinationen"]
    assert (k["soll"], k["erfasst"], k["luecken_zahl"]) == (8, 4, 4)
    assert telekom["satz"] == "Telekom: 4 von 8 Angeboten erfasst"
    assert telekom["marke"] == "4 Lücken"
    assert telekom["ebene"] == "angebote"
    assert {lu["grund"] for lu in telekom["luecken"]} == {
        "Bei Telekom nur mit 256 GB gelesen (21.11.2026)"
    }
    assert seite.zeilen(lauf, TAG)["weitere"] == ""


def test_angebotszeile_gegenprobe_und_tausendertrenner():
    lauf = _voll_mit_angeboten()
    anders = copy.deepcopy(lauf)
    k = anders["vollstaendigkeit"]["anbieter"][0]["ebenen"]["kombinationen"]
    k.update(soll=1262, erfasst=1240, luecken_zahl=22)
    satz = seite.zeilen(anders, TAG)["zeilen"][0]
    assert satz["satz"] == "Telekom: 1 240 von 1 262 Angeboten erfasst"
    assert satz["marke"] == "22 Lücken"
    k.update(soll=1262, erfasst=1262, luecken_zahl=0)
    assert seite.zeilen(anders, TAG)["zeilen"][0]["marke"] == "vollständig"
    anders["vollstaendigkeit"]["anbieter"][0]["angebot"]["nicht_gezaehlt_zahl"] = 3
    assert seite.zeilen(anders, TAG)["zeilen"][0]["marke"] == "3 Geräte nicht gezählt"


def test_fehlt_die_zaehlung_heute_sagt_die_zeile_es_mit_grund():
    voll = baue(TAG, f"{TAG}T04:00:00+00:00", [], {}, Signale())
    grund = "Angebot heute nicht gezählt: keine Zählung für den 2026-11-21"
    voll["anbieter"][0]["ebenen"]["kombinationen"]["soll_grund"] = grund
    voll["anbieter"][0]["angebot"] = {"status": "fehlt", "grund": "keine Zählung"}
    telekom = seite.zeilen({"vollstaendigkeit": voll}, TAG)["zeilen"][0]
    assert telekom["marke"].endswith("Angebot heute nicht gezählt")
    assert telekom["grund"] == grund
    assert "vollständig" not in telekom["marke"]


def test_gerenderte_seite_zeigt_die_angebotszeile_aus_der_lauf_datei(tmp_path):
    """Die Zeile auf ``geraete.html`` gegen die Lauf-Datei, mit Gegenprobe über das
    Datenattribut und die hervorgehobene Zahl."""
    import shutil

    import test_geraete_buendel_kopf_zeitraum as basis
    from bs4 import BeautifulSoup
    from test_geraete_browser_fixture import HEUTE

    from telco_radar import geraete_lauf
    from telco_radar.report.html import render_site

    lauf = _voll_mit_angeboten()
    lauf["vollstaendigkeit"]["datum"] = HEUTE
    site = basis._baue(tmp_path)
    geraete_lauf.schreibe(site.parent / "data" / "state", HEUTE, lauf)
    shutil.rmtree(site)
    render_site(site, site.parent / "data" / "reports")
    html = (site / "geraete.html").read_text(encoding="utf-8")
    li = BeautifulSoup(html, "html.parser").select_one(
        '#vollstaendigkeit li.gr-vs-z[data-anbieter="Telekom"]'
    )
    k = lauf["vollstaendigkeit"]["anbieter"][0]["ebenen"]["kombinationen"]
    assert li["data-ebene"] == "angebote"
    assert (li["data-soll"], li["data-erfasst"]) == (str(k["soll"]), str(k["erfasst"]))
    assert li.select_one(".gr-vs-zahl").get_text() == f"{k['erfasst']} von {k['soll']}"
    assert li.summary.get_text(" ", strip=True) == (
        "Telekom: 4 von 8 Angeboten erfasst · 4 Lücken"
    )
    assert len(li.select(".gr-vs-luecken li")) == k["luecken_zahl"]
