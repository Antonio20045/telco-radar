"""Telekom-Geräte mit 6 Raten (Abgleich 10.10.2026).

Der Tarif bindet 24 Monate, also trägt ein Angebot mit 6 Raten eine Zahl über 24
Monate und steht in der 24er-Ansicht; eine Auswahl für 6 Monate gibt es nicht.
In der 36er-Ansicht heißt ein Band, das nur mit 6 Raten erfasst ist, „Mit 36
Raten nicht erfasst (6 Raten erfasst)“, nicht „Nur in anderen Bändern“.
"""

from __future__ import annotations

from telco_radar.report.geraete_laufzeit import ansicht, setze_ansicht
from telco_radar.report.geraete_luecken import fehlen_im_paar


def _karte(band: str, raten: int, gesamt: float) -> dict:
    return {
        "anbieter": "Telekom",
        "sku_id": "samsung-galaxy-a17-128",
        "band": band,
        "raten_laufzeit": raten,
        "leitzahl_monate": max(raten, 24),
        "gesamt": gesamt,
        "frisch": True,
        "vergleichbar": True,
        "belastbar": True,
        "eigen": False,
    }


def test_sechs_raten_stehen_in_der_24er_ansicht():
    karten = [_karte("l", 6, 1200.0), _karte("s", 36, 900.0), _karte("m", 12, 950.0)]
    assert [ansicht(k) for k in karten] == [24, 36, 12]
    setze_ansicht(karten)
    assert [k["laufzeit_sichtbar"] for k in karten] == ["24", "36", "12"]
    assert ansicht({"raten_laufzeit": 48}) is None


def _fehlzeile(karten: list, band: str, laufzeit: int) -> dict:
    satz = {"zeilen": []}
    fehlen = fehlen_im_paar({"karten": karten}, satz, band, laufzeit, {}, 36)
    (telekom,) = [z for z in fehlen if z["anbieter"] == "Telekom"]
    return telekom


def test_ein_band_nur_mit_sechs_raten_ist_kein_anderes_band():
    karten = [_karte("s", 36, 900.0), _karte("xs", 36, 800.0), _karte("l", 6, 1200.0)]
    zeile = _fehlzeile(karten, "l", 36)
    assert zeile["grund"] == "nicht-erfasst"
    assert zeile["kurz"] == "Mit 36 Raten nicht erfasst (6 Raten erfasst)"


def test_gegenprobe_ohne_das_band_bleibt_es_ein_anderes_band():
    karten = [_karte("s", 36, 900.0), _karte("xs", 36, 800.0)]
    zeile = _fehlzeile(karten, "l", 36)
    assert zeile["grund"] == "anderes-band"
    assert zeile["kurz"].startswith("Nur in anderen Bändern: ")
