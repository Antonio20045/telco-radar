"""Belegte Lücken der Config stehen in der Modellansicht mit Grund und Prüfdatum.

Live-Abnahme 08.11.2026 (Punkte 3 und 4): o2 Air 512 GB und congstar iPhone 17 Pro
Max zeigten „Noch nicht erfasst“ bzw. veraltete Preise, obwohl die Lücke belegt war.
Regel für alle Anbieter: ein Preis, der nicht jünger ist als die Prüfung der Lücke,
ist veraltet und wird zur Lücke; ein jüngerer widerspricht ihr und bleibt stehen.
"""

from __future__ import annotations

import logging
from pathlib import Path

from telco_radar.analyze.buendel_abdeckung import lade_pflicht
from telco_radar.report.geraete_luecken import (
    NOCH_NICHT_ERFASST,
    fehlen_im_paar,
    ohne_tafelzeile,
)
from telco_radar.report.geraete_luecken_beleg import fuer_modell, ohne_widerlegte

CONFIG = Path(__file__).resolve().parents[1] / "config" / "geraete_abdeckung.yaml"
HEUTE = "2026-11-09"
PRO_MAX_512 = "apple-iphone-17-pro-max-512gb-deep-blue"


def _belege() -> dict:
    return lade_pflicht(CONFIG)["belege"]


def _karte(anbieter: str, zustand: str = "neu") -> dict:
    return {"anbieter": anbieter, "sku_id": "x", "zustand": zustand, "gesamt": 1.0}


def _modell(device_id: str, speicher: int, karten: list) -> dict:
    return {"device_id": device_id, "speicher": speicher, "karten": karten}


def _fehlzeilen(modell: dict, belege: dict) -> dict:
    modell["belegte_luecken"] = fuer_modell(belege, modell, HEUTE)
    satz = {"zeilen": [], "fremd": [], "gesperrt": []}
    return {f["anbieter"]: f for f in fehlen_im_paar(modell, satz, "m", 24, {}, 24)}


def _buendel(sku: str, abgerufen: str, anbieter: str = "congstar", **mehr) -> dict:
    return {"sku_id": sku, "anbieter": anbieter, "abgerufen_am": abgerufen, **mehr}


def test_o2_speicherluecke_nennt_grund_und_pruefdatum():
    zeilen = _fehlzeilen(_modell("apple-iphone-air", 512, []), _belege())
    assert zeilen["o2"]["kurz"] == "Nicht im Sortiment (geprüft 08.11.)"
    assert "Speicherstufe bei o2 nicht im Sortiment" in zeilen["o2"]["satz"]
    assert "Geprüft 08.11.2026, gültig bis 22.11.2026" in zeilen["o2"]["satz"]
    assert zeilen["Telekom"]["kurz"] == NOCH_NICHT_ERFASST


def test_gegenprobe_die_gefuehrte_stufe_ist_keine_luecke():
    zeilen = _fehlzeilen(_modell("apple-iphone-air", 256, []), _belege())
    assert zeilen["o2"]["kurz"] == NOCH_NICHT_ERFASST


def test_gegenprobe_eine_speicherluecke_ist_keine_modellluecke():
    belege = _belege()
    assert fuer_modell(belege, _modell("apple-iphone-air", 256, []), HEUTE) == {}
    assert "o2" in fuer_modell(belege, _modell("apple-iphone-air", 1024, []), HEUTE)


def test_congstar_pro_max_ist_in_jeder_stufe_nicht_im_sortiment():
    belege = _belege()
    for gb in (256, 512, 1024, 2048):
        zeilen = _fehlzeilen(_modell("apple-iphone-17-pro-max", gb, []), belege)
        assert zeilen["congstar"]["kurz"] == "Nicht im Sortiment (geprüft 08.11.)"
        assert "nicht mehr in der Geräteliste" in zeilen["congstar"]["satz"]


def test_congstar_duo_fehlt_nicht_still_in_der_modellansicht():
    zeilen = _fehlzeilen(_modell("apple-iphone-duo", 256, []), _belege())
    assert zeilen["congstar"]["kurz"] == "Nicht im Sortiment (geprüft 08.11.)"


def test_abgelaufener_beleg_ist_wieder_noch_nicht_erfasst():
    modell = _modell("apple-iphone-duo", 256, [])
    assert fuer_modell(_belege(), modell, "2026-11-23") == {}


def test_ein_neuer_preis_des_anbieters_verdraengt_die_luecke():
    modell = _modell("apple-iphone-17-pro-max", 512, [_karte("congstar")])
    assert "congstar" not in fuer_modell(_belege(), modell, HEUTE)


def test_eine_aufarbeitung_ersetzt_die_luecke_nicht():
    modell = _modell(
        "apple-iphone-17-pro-max", 512, [_karte("congstar", "refurbished")]
    )
    assert "congstar" in fuer_modell(_belege(), modell, HEUTE)
    fehlt = [{"anbieter": "congstar", "band": "m", "laufzeit": "24", "grund": "belegt"}]
    refurb = [{"anbieter": "congstar", "band": "m", "zustand": "refurbished"}]
    assert ohne_tafelzeile(fehlt, refurb) == fehlt
    neu = [{"anbieter": "congstar", "band": "m", "zustand": "neu"}]
    assert ohne_tafelzeile(fehlt, neu) == []


def test_preis_vor_der_pruefung_ist_veraltet_und_faellt_weg():
    """Pro Max 512 GB: Abruf 06.11., Lücke geprüft 08.11. - derselbe Tag zählt
    ebenso als veraltet (die Uhrzeit ist unbekannt, fail-closed)."""
    alt = _buendel(PRO_MAX_512, "2026-11-06")
    gleich = _buendel(PRO_MAX_512, "2026-11-08")
    unlesbar = _buendel(PRO_MAX_512, "")
    assert ohne_widerlegte([alt, gleich, unlesbar], _belege(), HEUTE) == []


def test_preis_nach_der_pruefung_bleibt_und_die_luecke_wird_gemeldet(caplog):
    neu = _buendel(PRO_MAX_512, "2026-11-09")
    with caplog.at_level(logging.WARNING):
        assert ohne_widerlegte([neu], _belege(), HEUTE) == [neu]
    assert "Belegte Lücke widerlegt: congstar" in caplog.text


def test_dieselbe_regel_gilt_fuer_jeden_anbieter_und_jede_stufe():
    o2_512 = _buendel("apple-iphone-air-512gb-weiss", "2026-11-07", "o2")
    o2_256 = _buendel("apple-iphone-air-256gb-weiss", "2026-11-07", "o2")
    telekom = _buendel(PRO_MAX_512, "2026-11-06", "Telekom")
    aufgearbeitet = _buendel(PRO_MAX_512, "2026-11-06", zustand="refurbished")
    rest = ohne_widerlegte([o2_512, o2_256, telekom, aufgearbeitet], _belege(), HEUTE)
    assert rest == [o2_256, telekom, aufgearbeitet]


def test_ohne_gueltigen_beleg_bleibt_jeder_preis():
    alt = _buendel(PRO_MAX_512, "2026-11-06")
    assert ohne_widerlegte([alt], _belege(), "2026-11-23") == [alt]
    assert ohne_widerlegte([alt], {}, HEUTE) == [alt]


def test_ein_stand_vor_der_pruefung_kennt_die_luecke_nicht():
    alt = _buendel(PRO_MAX_512, "2026-10-03")
    assert ohne_widerlegte([alt], _belege(), "2026-10-03") == [alt]
    modell = _modell("apple-iphone-duo", 256, [])
    assert fuer_modell(_belege(), modell, "2026-10-03") == {}
    assert "congstar" in fuer_modell(_belege(), modell, "2026-11-08")
