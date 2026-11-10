"""Falsche Lücken der Stichprobe vom 10.11.2026 (vier von zwölf am Original widerlegt).

(1) Telekom Google Pixel 11, 512 GB: „nur mit 256 GB im Angebot“. Der Klick-Lauf liest
die Seite in Frost (``.../frost-256-gb``); dort ist 512 GB gesperrt, in Obsidian ist er
bestellbar (+130 EUR, Warenkorb aktiv). Die Telekom-Karte erkennt „nur in anderer Farbe“
nicht (nur congstar trägt ``andere_farbe``), also ist „gesperrt“ dort kein Beleg.

(2) congstar Galaxy S26 256 GB, Xiaomi 17 Ultra 512 GB, Galaxy S26 Ultra 512 GB: „führt
nur ein erneuert Gerät“. Im Oktober standen in derselben Tabelle die Zeilen des
erneuerten Bündels (Quelle ``…-zustand-wie-neu``) mit diesem Grund neben den
vergleichbaren Zeilen des Neugeräts: „nur“ stimmte nie.

Regel: eine Zelle „nicht im Portfolio“ braucht frischen, eindeutigen Beleg, sonst ist
sie eine Messlücke. Widerspruchsregel und Höchstalter sind eine gemeinsame Logik.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from bestand_pfad import lese_wurzel

from telco_radar.analyze.buendel_abdeckung import lade_pflicht
from telco_radar.analyze.klick_erfassung import (
    BELEG_MAX_TAGE,
    SATZ_NICHT_IM_ANGEBOT,
    SATZ_SPEICHER,
    SATZ_SPEICHER_ANGEBOT,
    Neugeraete,
    beleg_gilt,
    fuer_modell,
)
from telco_radar.analyze.klick_zusammenfuehrung import fuehre_zusammen
from telco_radar.collect.geraete.klickziele import karten_mit_farbmarke
from telco_radar.geraete_config import lade_katalog
from telco_radar.report import geraete_radar as radar
from telco_radar.report.geraete_luecken_beleg import fuer_modell as belegte_luecken
from telco_radar.report.geraete_widerspruch import neugeraete, setze_luecken

HEUTE = "2026-11-09"
PIXEL = "google-pixel-11"
S26 = "samsung-galaxy-s26"
ADRESSE = "https://www.telekom.de/shop/geraet/google/google-pixel-11/frost-256-gb"
ROOT = Path(__file__).resolve().parent.parent


def _telekom_pixel_11() -> dict:
    """Die Telekom-Datei vom 09.11.2026 in klein: die Übersicht liest das Pixel 11 mit
    256 GB, die Produktseite (Frost) zeigt 512 GB gesperrt."""
    satz = {
        "titel": "Google Pixel 11 256 GB",
        "speicher_gb": 256,
        "tarif_name": "MagentaMobil L",
        "tarif_slug": "MF_17791",
        "tarif_monatlich": 49.95,
        "geraet_zuzahlung": 1.0,
        "geraet_monatsrate": 20.2,
        "anschlusspreis": 39.95,
        "laufzeit_monate": 24,
        "url": ADRESSE,
    }
    kombination = {
        "variante": {"speicher": "512 GB", "laufzeit": 24, "tarif": "MagentaMobil L"},
        "status": "nicht_angeboten",
    }
    return {
        "anbieter": "telekom",
        "name": "Telekom",
        "karte": "telekom.yaml",
        "datum": HEUTE,
        "format": 1,
        "laufstatus": "gelesen",
        "grund": None,
        "seiten": [
            {
                "adresse": ADRESSE,
                "geraet": PIXEL,
                "status": "gelesen",
                "kombinationen": [kombination],
            }
        ],
        "uebersichten": [
            {
                "adresse": "https://www.telekom.de/shop/geraete/smartphones",
                "status": "gelesen",
                "grund": None,
                "saetze": [satz],
                "vollstaendig": True,
                "unvollstaendig": None,
            }
        ],
    }


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


def _erfassung(katalog, **mehr) -> dict[str, str]:
    zug = fuehre_zusammen(
        [], [_telekom_pixel_11()], katalog, HEUTE, lambda sku: ("", None), **mehr
    )
    return zug.erfassung


def test_telekom_pixel_11_512_ist_keine_portfolio_luecke(katalog):
    """(1) Rot gegen origin/main: dort steht „nur mit 256 GB im Angebot“."""
    satz = fuer_modell(_erfassung(katalog), {"karten": [], "device_id": PIXEL})
    assert satz == {"Telekom": "Bei Telekom nur mit 256 GB gelesen (09.11.2026)"}
    assert "im Angebot" not in satz["Telekom"]


def test_gegenprobe_eine_karte_mit_farbmarke_belegt_die_sperre(katalog):
    """Wer „nur in anderer Farbe“ erkennt (congstar), darf „im Angebot“ sagen."""
    erfassung = _erfassung(katalog, farbmarke=frozenset({"telekom"}))
    assert erfassung[f"Telekom|{PIXEL}"] == (
        "Bei Telekom nur mit 256 GB im Angebot (09.11.2026)"
    )


def test_nur_congstar_markiert_die_andere_farbe():
    assert karten_mit_farbmarke(ROOT) == {"congstar"}


def _modelle_der_radarzeile(neu_da: list[str]) -> dict:
    """Ein Modell wie das Galaxy S26 256 GB: Vodafone im Band m, dazu das erneuerte
    Bündel von congstar (Quelle ``…-zustand-wie-neu``) und das Neugerät."""

    def karte(anbieter, gesamt, **mehr):
        return {
            "anbieter": anbieter,
            "gesamt": gesamt,
            "belastbar": True,
            "naeherung": False,
            "frisch": True,
            "tarif_id": "m",
            "tarif": "M",
            "raten_laufzeit": 24,
            "leitzahl_monate": 24,
            "vergleichbar": True,
            "zustand": "neu",
            **mehr,
        }

    karten = [
        karte("Vodafone", 1500.0),
        karte("congstar", 1060.0, vergleichbar=False, zustand="refurbished")
        | {"zustand_etikett": "erneuert"},
        karte("congstar", 1300.0),
    ]
    return {
        "id": "samsung-galaxy-s26-256",
        "titel": "Samsung Galaxy S26 256 GB",
        "hersteller": "Samsung",
        "speicher": 256,
        "karten": karten,
        "referenz": {"gesamt": 1500.0, "tarif_id": "m", "ansicht": 24, "monate": 24},
        "neu_da": neu_da,
    }


def _congstar_gruende(neu_da: list[str]) -> list[str]:
    (gruppe,) = radar.netzbetreiber_gruppen(
        [_modelle_der_radarzeile(neu_da)], {"m": "m"}
    )
    return [
        z["grund"]
        for z in gruppe["zeilen"]
        if z["anbieter"] == "congstar"
        and z["status"] == radar.STATUS_NICHT_VERGLEICHBAR
    ]


def test_erneuertes_angebot_neben_dem_neugeraet_sagt_nie_nur(katalog):
    """(2) Rot gegen origin/main: dort steht „führt … nur ein erneuert Gerät“."""
    saetze = _congstar_gruende(["congstar"])
    assert saetze
    assert not any("nur ein" in s for s in saetze)
    assert all("kein Vergleich gegen ein Neugerät" in s for s in saetze)


def test_gegenprobe_ohne_neugeraet_bleibt_der_satz():
    saetze = _congstar_gruende([])
    assert saetze == [
        "congstar führt für dieses Gerät nur ein erneuert Gerät – "
        "kein Vergleich gegen ein Neugerät."
    ]


def _listung(**mehr) -> dict:
    return {
        "anbieter": "congstar",
        "device_id": S26,
        "speicher_gb": 256,
        "zustand": "neu",
        "status": "aktiv",
        "verfuegbarkeit": "lieferbar",
        "last_verified": HEUTE,
    } | mehr


def test_neugeraet_zaehlt_nur_lieferbar_frisch_aktiv_und_neu():
    assert neugeraete([_listung()], HEUTE).speicher == {("congstar", S26, 256)}
    for abweichung in (
        {"verfuegbarkeit": "nicht_lieferbar"},
        {"verfuegbarkeit": "unbekannt"},
        {"zustand": "refurbished"},
        {"status": "ausgelistet"},
        {"last_verified": "2026-11-01"},
        {"last_verified": None},
        {"speicher_gb": None},
    ):
        assert neugeraete([_listung(**abweichung)], HEUTE) == Neugeraete(), abweichung
    assert neugeraete([_listung()], "") == Neugeraete()


NICHT_IM_ANGEBOT = SATZ_NICHT_IM_ANGEBOT.format(anbieter="congstar", datum="09.11.2026")
NUR_ANGEBOT = SATZ_SPEICHER_ANGEBOT.format(
    anbieter="congstar", speicher="256 GB", datum="09.11.2026"
)
NUR_GELESEN = SATZ_SPEICHER.format(
    anbieter="congstar", speicher="256 GB", datum="09.11.2026"
)
MODELL = {"device_id": S26, "speicher": 512, "karten": []}


def test_widerspruchsregel_gilt_fuer_alle_drei_lueckensaetze():
    """Der Radar führt congstar Galaxy S26 lieferbar: kein Satz bleibt stehen."""
    neu = neugeraete([_listung(speicher_gb=512)], HEUTE)
    for satz in (NICHT_IM_ANGEBOT, NUR_ANGEBOT, NUR_GELESEN):
        gruende = {f"congstar|{S26}": satz}
        assert fuer_modell(gruende, MODELL, HEUTE) == {"congstar": satz}
        assert fuer_modell(gruende, MODELL, HEUTE, neu) == {}, satz


def test_widerspruch_nur_bei_derselben_kombination():
    """Gegenprobe: ein anderer Speicher widerspricht „nur mit 256 GB“ nicht; „nicht im
    Angebot“ meint das Gerät und fällt bei jedem lieferbaren Speicher."""
    neu = neugeraete([_listung(speicher_gb=1024)], HEUTE)
    assert fuer_modell({f"congstar|{S26}": NUR_ANGEBOT}, MODELL, HEUTE, neu)
    assert not fuer_modell({f"congstar|{S26}": NICHT_IM_ANGEBOT}, MODELL, HEUTE, neu)
    anderer = neugeraete([_listung(anbieter="o2", speicher_gb=512)], HEUTE)
    assert fuer_modell({f"congstar|{S26}": NUR_ANGEBOT}, MODELL, HEUTE, anderer)


def test_stoerungssatz_ist_kein_lueckenbeleg():
    satz = "congstar nicht erfasst: Seite sperrt automatisches Lesen (HTTP 202)"
    neu = neugeraete([_listung(speicher_gb=512)], HEUTE)
    assert fuer_modell({"congstar": satz}, MODELL, HEUTE, neu) == {"congstar": satz}


def test_lueckenbeleg_hat_ein_hoechstalter():
    """Ein Satz ohne Datum, aus der Zukunft oder älter als ``BELEG_MAX_TAGE`` Tage ist
    kein Beleg mehr; ohne bekannten Stichtag auch nicht."""
    assert BELEG_MAX_TAGE == 3
    assert beleg_gilt(NUR_ANGEBOT, "2026-11-09")
    assert beleg_gilt(NUR_ANGEBOT, "2026-11-11")
    assert not beleg_gilt(NUR_ANGEBOT, "2026-11-12")
    assert not beleg_gilt(NUR_ANGEBOT, "2026-11-08")
    assert not beleg_gilt(NUR_ANGEBOT, "")
    assert not beleg_gilt(NICHT_IM_ANGEBOT.replace("09.11.2026", "31.02.2026"), HEUTE)
    gruende = {"congstar": "Bei congstar nur mit 256 GB im Angebot"}
    assert fuer_modell(gruende, MODELL, HEUTE) == gruende
    assert fuer_modell({"congstar": NUR_ANGEBOT}, MODELL, "2026-11-12") == {}


def test_alter_satz_wird_zur_messluecke_in_der_zeile():
    """Durch alle Schichten: derselbe Satz vom 09.11. ist am 09.11. ein Beleg, am
    12.11. „Noch nicht erfasst“."""
    from telco_radar.report.geraete_luecken import NOCH_NICHT_ERFASST, fehlen_im_paar

    def zeile(heute: str) -> str:
        modell = {**MODELL, "id": "x", "speicher": 256}
        setze_luecken([modell], {f"congstar|{S26}": NUR_GELESEN}, {}, [], heute)
        satz = {"zeilen": [], "fremd": [], "gesperrt": []}
        zeilen = fehlen_im_paar(modell, satz, "m", 24, {}, 24)
        return {z["anbieter"]: z["kurz"] for z in zeilen}["congstar"]

    assert zeile("2026-11-09") == "Nur mit 256 GB gelesen"
    assert zeile("2026-11-12") == NOCH_NICHT_ERFASST


def test_belegte_luecke_der_config_faellt_beim_widerspruch_weg():
    belege = lade_pflicht(ROOT / "config" / "geraete_abdeckung.yaml")["belege"]
    modell = {"device_id": "apple-iphone-17-pro-max", "speicher": 512, "karten": []}
    assert "congstar" in belegte_luecken(belege, modell, HEUTE)
    neu = neugeraete(
        [_listung(device_id="apple-iphone-17-pro-max", speicher_gb=512)], HEUTE
    )
    assert "congstar" not in belegte_luecken(belege, modell, HEUTE, neu)
