"""Überholte Klick-Bündel je Ratenzahl: Telekom-Produktseite und Übersicht, 10.10.2026.

Die Produktseite des iPhone 17 Pro 256 GB lieferte am 10.10. MagentaMobil M mit 12, 24
und 36 Raten; die Übersichten lesen nur 36 Raten. Liest der Lauf am 11.10. nur die
Übersicht, bleiben die Bündel mit 12 und 24 Raten stehen. Gegenprobe: ein jüngeres
Bündel mit 24 Raten überholt das ältere mit 24 Raten.
"""

from telco_radar.report.klick_ueberholt import ueberholt

SKU = "apple-iphone-17-pro-256gb-tiefblau"
TARIF = "MagentaMobil M"


def _b(raten: int, datum: str) -> dict:
    return {
        "id": f"{raten}|{datum}",
        "anbieter": "Telekom",
        "sku_id": SKU,
        "tarif_name": TARIF,
        "laufzeit_monate": raten,
        "abgerufen_am": datum,
        "quelle_art": "klick",
    }


def test_uebersicht_mit_36_raten_ueberholt_12_und_24_nicht():
    bestand = [_b(12, "2026-10-10"), _b(24, "2026-10-10"), _b(36, "2026-10-11")]
    assert ueberholt(bestand) == set()


def test_gegenprobe_juengere_24_raten_ueberholen_aeltere():
    bestand = [_b(24, "2026-10-10"), _b(24, "2026-10-11"), _b(36, "2026-10-11")]
    assert ueberholt(bestand) == {"24|2026-10-10"}
