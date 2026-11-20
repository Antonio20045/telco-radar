"""1&1 ab 20.11.2026: "24/36 Monate Fix" ist eine neue Lesart, keine Preisbewegung.

Bis 19.11.2026 las der (inzwischen entfernte) 1&1-Adapter unter "36 Monate" das
Angebot 24+12 mit Schlusszahlung; seit 20.11.2026 misst der Klick-Lauf "36 Monate
Fix". `rechenweise` trennt den Bruch (1&1 Stufe 2), sonst meldete der
Abdeckungswächter Preissprünge über 25 %.
"""

from telco_radar import rechenweise
from telco_radar.analyze.buendel_abdeckung import pruefe
from telco_radar.tco_model import Buendel


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
