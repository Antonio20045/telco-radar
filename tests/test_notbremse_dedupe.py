"""Notbremse in der Angebots-Dedupe: eine Schätzung drängt kein gemessenes Angebot
aus der Seite. Zwei Farben desselben Geräts beim selben Anbieter, gleicher Tarif,
gleiche Ratenlaufzeit: die eine gemessen, die andere abgeleitet und billiger.
Die gemessene muss als Karte bleiben und die Spanne/den günstigsten Tarif
stellen (Datenkonzept Regel 1: nur gemessene Werte zählen - und die gemessenen
zählen). Am Schnappschuss: Galaxy S26 256 GB, o2 „O2 Mobile L Plus“, gemessen
1.488,76 € wird von der Schätzung 1.434,76 € verdrängt.

Synthetisch über den öffentlichen Eingang ``geraete_tco_karten.modelle``; fester
Bezugstag.
"""

from __future__ import annotations

import pytest

from telco_radar.report import geraete_tco_karten
from telco_radar.tco_model import Aktion, Buendel

HEUTE = "2026-10-03"
TARIF = "O2 Mobile L Plus mit 150 GB+ (24 Mon.)"


def _listung(sku: str, farbe: str) -> dict:
    return {
        "sku_id": sku,
        "device_id": "pruefer-phone",
        "speicher_gb": 256,
        "anbieter": "o2",
        "zustand": "neu",
        "farbe_normalisiert": farbe,
        "quelle_url": "https://example.org/o2",
        "abgerufen_am": HEUTE,
    }


ABGELAUFEN = Aktion(
    art="anschluss_erlassen",
    bedingung="Online-Aktion",
    quelle_url="https://example.org/o2/aktion",
    eingerechnet=True,
    gueltig_bis="2026-09-29",
)


def _buendel(
    sku: str, tarif: float, herleitung: str = "", aktionen: tuple = ()
) -> Buendel:
    return Buendel(
        sku_id=sku,
        anbieter="o2",
        tarif_name=TARIF,
        tarif_monatlich=tarif,
        geraet_zuzahlung=1.0,
        geraet_monatsrate=30.0,
        laufzeit_monate=24,
        anschlusspreis=39.99,
        quelle_url=f"https://example.org/o2/{sku}",
        abgerufen_am=HEUTE,
        herleitung=herleitung,
        aktionen=list(aktionen),
        zustand="neu",
    )


def _modell(buendel: list) -> dict:
    listungen = [_listung("p-schwarz", "schwarz"), _listung("p-blau", "blau")]
    erg = geraete_tco_karten.modelle(buendel, listungen, [], {}, None, heute=HEUTE)
    assert len(erg["modelle"]) == 1, erg["modelle"]
    return erg["modelle"][0]


@pytest.mark.parametrize(
    "gesperrt",
    [
        {"herleitung": "tarifsumme_minus_geraeterate"},
        {"aktionen": (ABGELAUFEN,)},
    ],
    ids=["schaetzung", "aktion-abgelaufen"],
)
def test_gemessenes_angebot_bleibt_neben_billigerer_schaetzung(gesperrt):
    gemessen = _buendel("p-schwarz", 30.0)
    schaetzung = _buendel("p-blau", 25.0, **gesperrt)
    modell = _modell([gemessen, schaetzung])
    betrag_gemessen = _modell([gemessen])["spanne"]
    assert betrag_gemessen, "Gegenprobe: das gemessene Bündel allein hat eine Spanne"
    gesamt = betrag_gemessen[0]
    karten = [k["gesamt"] for k in modell["karten"] if k.get("anbieter") == "o2"]
    assert gesamt in karten, (
        f"gemessenes o2-Angebot ({gesamt} €) fehlt in den Karten {karten}: "
        f"die billigere Schätzung hat es in der Angebots-Dedupe verdrängt"
    )
    assert modell["spanne"] == [gesamt, gesamt], (
        f"Spanne {modell['spanne']} - erwartet das gemessene Angebot {gesamt} €"
    )
    assert modell["antwort"]["tarif_gesamt"] == gesamt, modell["antwort"]
