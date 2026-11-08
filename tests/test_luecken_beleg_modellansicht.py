"""Belegte Lücken der Config stehen in der Modellansicht mit Grund und Prüfdatum.

Live-Abnahme 08.11.2026 (Punkte 3 und 4): o2 Air 512 GB und congstar iPhone 17 Pro
Max zeigten „Noch nicht erfasst“ bzw. veraltete Preise, obwohl die Lücke belegt war.
Regel für alle Anbieter: ein Preis, der nicht jünger ist als die Prüfung der Lücke,
ist veraltet und wird zur Lücke (ein Mechanismus: `geraete_sortiment.markiere_mit`);
ein jüngerer widerspricht ihr, bleibt stehen und wird gemeldet.
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
from telco_radar.report.geraete_luecken_beleg import fuer_modell
from telco_radar.report.geraete_sortiment import VERMERK, markiere_mit
from telco_radar.report.geraete_zeitreihe_legende import (
    legende_html,
    ohne_alte,
    ueberholt_html,
)

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


def test_der_grund_steht_als_sichtbarer_kurztext_in_der_zeile():
    """Auf dem Telefon gibt es kein Tooltip: `detail` ist der Grund als Text, bei
    o2 ohne die Wiederholung „nicht im Sortiment (geprüft …)“."""
    o2 = _fehlzeilen(_modell("apple-iphone-air", 512, []), _belege())["o2"]
    assert o2["detail"] == "der Speicher-Wähler der Produktseite zeigt nur 256 GB"
    cs = _fehlzeilen(_modell("apple-iphone-17-pro-max", 512, []), _belege())
    assert cs["congstar"]["detail"].startswith(
        "Gerät ist nicht mehr in der Geräteliste"
    )
    assert "Geprüft" not in cs["congstar"]["detail"]


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


def _veraltet(saetze: list, belege: dict, heute: str = HEUTE) -> list[bool]:
    return [s.get("pruefung") == VERMERK for s in markiere_mit(saetze, belege, heute)]


def test_preis_vor_der_pruefung_ist_veraltet(caplog):
    """Pro Max 512 GB: Abruf 06.11., Lücke geprüft 08.11. Unlesbar ist fail-closed."""
    alt = _buendel(PRO_MAX_512, "2026-11-06")
    unlesbar = _buendel(PRO_MAX_512, "")
    with caplog.at_level(logging.WARNING):
        assert _veraltet([alt, unlesbar], _belege()) == [True, True]
    assert caplog.text == ""


def test_gleichstand_ist_veraltet_und_warnt(caplog):
    """Abruf == Prüfdatum: Uhrzeit unbekannt, also veraltet - aber nicht still."""
    gleich = _buendel(PRO_MAX_512, "2026-11-08")
    with caplog.at_level(logging.WARNING):
        assert _veraltet([gleich], _belege()) == [True]
    assert "Belegte Lücke überholt einen Preis vom Prüftag: congstar" in caplog.text


def test_preis_nach_der_pruefung_bleibt_und_die_luecke_wird_gemeldet(caplog):
    neu = _buendel(PRO_MAX_512, "2026-11-09")
    with caplog.at_level(logging.WARNING):
        assert markiere_mit([neu], _belege(), HEUTE) == [neu]
    assert "Belegte Lücke widerlegt: congstar" in caplog.text


def test_dieselbe_regel_gilt_fuer_jeden_anbieter_und_jede_stufe():
    o2_512 = _buendel("apple-iphone-air-512gb-weiss", "2026-11-07", "o2")
    o2_256 = _buendel("apple-iphone-air-256gb-weiss", "2026-11-07", "o2")
    telekom = _buendel(PRO_MAX_512, "2026-11-06", "Telekom")
    aufgearbeitet = _buendel(PRO_MAX_512, "2026-11-06", zustand="refurbished")
    saetze = [o2_512, o2_256, telekom, aufgearbeitet]
    assert _veraltet(saetze, _belege()) == [True, False, False, False]


def test_ohne_gueltigen_beleg_bleibt_jeder_preis():
    alt = _buendel(PRO_MAX_512, "2026-11-06")
    assert _veraltet([alt], _belege(), "2026-11-23") == [False]
    assert _veraltet([alt], {}) == [False]


def test_ein_stand_vor_der_pruefung_kennt_die_luecke_nicht():
    alt = _buendel(PRO_MAX_512, "2026-10-03")
    assert _veraltet([alt], _belege(), "2026-10-03") == [False]
    modell = _modell("apple-iphone-duo", 256, [])
    assert fuer_modell(_belege(), modell, "2026-10-03") == {}
    assert "congstar" in fuer_modell(_belege(), modell, "2026-11-08")


def test_legende_nennt_den_von_der_luecke_ueberholten_preis_ohne_zahl():
    """Zeitreihe: der überholte congstar-Preis (06.11.) zählt nicht mehr, die Reihe
    fehlt - die Legende sagt warum, statt „zuletzt 2.001 €“ oder Schweigen."""
    modell = {
        "belegte_luecken": {"congstar": {"kurz": "Nicht im Sortiment (geprüft 08.11.)"}}
    }
    mess = {"congstar": {"2026-11-06": {"wert": None}}}
    html = ueberholt_html(modell, mess, serien={})
    assert "Nicht im Sortiment (geprüft 08.11.)" in html
    assert "frühere Preise überholt" in html and "zuletzt" not in html
    assert ueberholt_html(modell, {}, serien={}) == ""
    assert (
        ueberholt_html(modell, mess, serien={"congstar": [("2026-11-09", 1.0)]}) == ""
    )
    legende = legende_html({}, None, html)
    assert legende.startswith("<div class='gr-zr-legende'>") and "congstar" in legende


def test_ein_ueberholter_preis_ersetzt_die_fehlzeile_nicht():
    """Pro Max 512 bei congstar: das Bündel vom 06.11. ist überholt
    (`nicht_im_sortiment`) - die Fehlzeile mit Grund und Prüfdatum bleibt."""
    fehlt = [{"anbieter": "congstar", "band": "m", "laufzeit": "24", "grund": "belegt"}]
    ueberholt = [
        {
            "anbieter": "congstar",
            "band": "m",
            "zustand": "neu",
            "nicht_im_sortiment": True,
        }
    ]
    assert ohne_tafelzeile(fehlt, ueberholt) == fehlt


def test_rechenweg_vorlagen_ueberholter_anbieter_fallen_weg():
    """Ohne Reihe sind die verdeckten Vorlagen nicht erreichbar, trügen aber die
    alte Zahl im HTML; wer eine Reihe hat oder keine Lücke, behält sie."""
    modell = {"belegte_luecken": {"congstar": {"kurz": "x"}}}
    mess = {"congstar": {"2026-11-06": {}}, "o2": {"2026-11-06": {}}}
    assert list(ohne_alte(modell, mess, serien={})) == ["o2"]
    assert list(ohne_alte(modell, mess, serien={"congstar": [1]})) == ["congstar", "o2"]
    assert list(ohne_alte({}, mess, serien={})) == ["congstar", "o2"]
