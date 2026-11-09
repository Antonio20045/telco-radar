"""Rest der Legende (Nachprüfung PR #75, 09.11.2026): jede Legendenzahl hat eine
zählende Tafelzeile oder einen wahren Satz darunter.

Vorher fehlte der Satz, wo die Tafel für den Anbieter gar keine Karte im Band führt
(Telekom iPhone 17 Pro 512 in S/L/XL; o2 Pixel 10 Pro 128 in M: dort nur Karten „ohne
Tarifband“), er sagte bei „Preis veraltet“ etwas Unschärferes („Schätzung oder nur mit
Zweitprodukt“), und neben einer zählenden Zeile blieb eine billigere Schätzzeile ohne
Hinweis (Fairphone 6 256, o2 XL). Die Sätze lesen die Wörter der Tafel
(`geraete_preisstand.zeilen_grund`); jeder Test unten ist gegen den Stand von #75 rot.
"""

from __future__ import annotations

import html
import re

import pytest
from bestand_pfad import abbild, lese_wurzel

from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import (
    geraete_preisstand,
    geraete_view,
    geraete_zeitreihe,
    geraete_zeitreihe_legende,
)

HEUTE_BESTAND = "2026-10-03"


def _karte(anbieter="o2", gesamt=1285.75, **felder) -> dict:
    """Eine Karte in der Form, die `band_zeilen` aus der Tafel liest."""
    return {
        "anbieter": anbieter,
        "band": "xl",
        "raten_laufzeit": 24,
        "leitzahl_monate": 24,
        "sku_id": "sku",
        "zustand": "neu",
        "vergleichbar": True,
        "belastbar": True,
        "frisch": True,
        "zaehlt": True,
        "gesamt": gesamt,
        "abgerufen_am": "2026-11-07",
        **felder,
    }


def _satz(*karten) -> dict:
    return geraete_zeitreihe.band_zeilen({"karten": list(karten)}, 24).get(
        "xl", {"zeilen": [], "karten": [], "gesperrt": []}
    )


def _legende(satz, anbieter="o2", wert=1285.75) -> str:
    mess = {anbieter: {"2026-11-07": {"zaehlt": True}}}
    serien = {anbieter: [("2026-11-07", wert)]}
    return html.unescape(geraete_zeitreihe_legende.schaetzung_html(satz, mess, serien))


def test_ohne_karte_im_band_sagt_die_legende_dass_die_tafel_keinen_preis_fuehrt():
    """Telekom iPhone 17 Pro 512 S: die Tafel führt nur XS und M."""
    ohne_telekom = _satz(_karte("Vodafone", gesamt=2300.0))
    assert not [k for k in ohne_telekom["karten"] if k["anbieter"] == "Telekom"]
    text = _legende(ohne_telekom, "Telekom", 2407)
    assert "Telekom · Die Tafel führt hier keinen Preis" in text, text
    assert "letzte zählende Messung (2.407 €)" in text, text


def test_karten_ohne_tarifband_sind_keine_karten_des_bandes():
    """o2 Pixel 10 Pro 128 M: nur Karten „ohne Tarifband“ - im Band steht keine."""
    satz = _satz(_karte("o2", band=None, gesamt=1339.75))
    assert "xl" not in geraete_zeitreihe.band_zeilen(
        {"karten": [_karte(band=None)]}, 24
    )
    assert "keinen Preis" in _legende(satz, "o2", 1500)


def test_gegenprobe_mit_zaehlender_zeile_steht_kein_satz():
    satz = _satz(_karte("o2", 1285.75))
    assert _legende(satz) == ""


def test_preis_veraltet_heisst_in_der_legende_preis_veraltet():
    """Die Tafel sagt „Preis veraltet / kein aktueller Stand“, ohne Preis."""
    alt = _karte(frisch=False, zaehlt=False, schaetzung=True, alt_marke="seit 20.10.")
    assert geraete_preisstand.zeilen_grund(alt) == "Preis veraltet"
    text = _legende(_satz(alt), wert=1506)
    assert "nicht zählen (Preis veraltet)" in text, text
    assert "Schätzung" not in text and "Zweitprodukt" not in text, text


def test_zweitprodukt_und_schaetzung_stehen_mit_den_woertern_der_tafel():
    plus = _karte(zaehlt=False, bedingter_tarif=True, gesamt=1339.75)
    geschaetzt = _karte(zaehlt=False, schaetzung=True, gesamt=1165.75, tarif_id="x")
    assert geraete_preisstand.zeilen_grund(plus) == "nur mit Zweitprodukt"
    assert geraete_preisstand.zeilen_grund(geschaetzt) == "nicht direkt genannt"
    assert geraete_preisstand.zeilen_grund(_karte()) == ""
    text = _legende(_satz(plus, geschaetzt), wert=1374)
    assert "(nur mit Zweitprodukt, nicht direkt genannt)" in text, text


def test_billigere_schaetzzeile_neben_der_zaehlenden_zeile_wird_genannt():
    """Fairphone 6 256 o2 XL: zählend 1.285,75 €, daneben Schätzung 1.165,75 €."""
    zaehlend = _karte(gesamt=1285.75, tarif_id="a")
    geschaetzt = _karte(gesamt=1165.75, zaehlt=False, schaetzung=True, tarif_id="b")
    satz = _satz(zaehlend, geschaetzt)
    assert [z["gesamt"] for z in satz["zeilen"]] == [1285.75]
    text = _legende(satz)
    assert "billigeren Preis, der nicht zählt (nicht direkt genannt: 1.166 €)" in text
    assert "zählende Zeile (1.286 €)" in text, text


@pytest.mark.parametrize(
    "dazu",
    [
        _karte(gesamt=1400.0, zaehlt=False, schaetzung=True, tarif_id="b"),
        _karte(gesamt=1285.75, zaehlt=False, schaetzung=True, tarif_id="b"),
        _karte(gesamt=1000.0, zaehlt=False, schaetzung=True, zustand="refurbished"),
        _karte(gesamt=1000.0, zaehlt=False, bedingter_tarif=True, tarif_id="b"),
    ],
    ids=["teurer", "gleich", "b-ware", "ohne-zahl-in-der-tafel"],
)
def test_gegenprobe_kein_hinweis_ohne_billigere_sichtbare_schaetzung(dazu):
    satz = _satz(_karte(tarif_id="a"), dazu)
    assert _legende(satz) == ""


def _legendennamen(legende_html: str) -> set[str]:
    return {
        html.unescape(n)
        for n in re.findall(
            r"<i style='background:[^']*'></i>([^<]*?) <span class='gr-zr-leg-wert'>",
            legende_html,
        )
    }


def _satznamen(legende_html: str) -> set[str]:
    return {
        html.unescape(n).strip()
        for n in re.findall(
            r"<span class='gr-zr-leg-ueberholt'><i [^>]*></i>([^<]*?) · ", legende_html
        )
    }


@pytest.fixture(scope="module")
def seite(tmp_path_factory):
    wurzel = tmp_path_factory.mktemp("rest")
    abbild(wurzel)
    zustand = wurzel / "data" / "state"
    w = lese_wurzel()
    return geraete_view.aufbereiten(
        zustand, lade_quellen(w), lade_katalog(w), heute=HEUTE_BESTAND
    )


def test_jeder_legendeneintrag_hat_eine_zaehlende_zeile_oder_einen_satz(seite):
    modelle = {m["id"]: m for m in seite["tco"]["modelle"]}
    geprueft, ohne = 0, []
    for p in seite["zeitreihe"]["paare"]:
        zeilen = geraete_zeitreihe.band_zeilen(modelle[p["modell"]], p["laufzeit"])
        mit_zeile = {z["anbieter"] for z in zeilen.get(p["band"], {}).get("zeilen", [])}
        saetze = _satznamen(p["legende_html"])
        for anbieter in _legendennamen(p["legende_html"]):
            geprueft += 1
            if anbieter not in mit_zeile and anbieter not in saetze:
                ohne.append((p["modell"], p["band"], p["laufzeit"], anbieter))
    assert geprueft > 50, geprueft
    assert not ohne, f"{len(ohne)} von {geprueft}: {ohne[:3]}"
