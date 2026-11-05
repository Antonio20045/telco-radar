"""Eine Zeile mit Plus-Tarif (Zweitprodukt-Bonus) zeigt keinen Preis.

Prüfung PR #38 (05.11.2026, M1): „o2 Mobile on Demand M Plus“ zeigte 20,00 € und die
Rechnung, nur mit dem Chip „nur mit Zweitprodukt“. Entscheidung des Managers: an die
Stelle des Preises tritt die benannte Lücke „nur mit Zweitprodukt – nicht vergleichbar“;
die Zeile geht auch nicht in Export, Durchschnitte oder Grafiken ein. Synthetisch,
fester Bezugstag.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import yaml

from telco_radar.report import geraete_preisstand, geraete_tco_karten, geraete_tco_view
from telco_radar.report import html as seiten
from telco_radar.report.geraete_export import SPALTE_UEBER_24, tco_csv
from telco_radar.tco_model import Buendel

HEUTE = "2026-11-05"
SKU = "pruefer-phone-256-schwarz"
PLUS = "O2 Mobile on Demand M Plus mit 50 GB+"
OHNE_PLUS = "O2 Mobile on Demand M mit 50 GB+"
GRUND = geraete_preisstand.SATZ_BEDINGT
WURZEL = Path(__file__).parent.parent


def _buendel(anbieter: str, tarif: float, name: str, sku: str = SKU) -> Buendel:
    return Buendel(
        sku_id=sku,
        anbieter=anbieter,
        tarif_name=name,
        tarif_monatlich=tarif,
        geraet_zuzahlung=1.0,
        geraet_monatsrate=30.0,
        laufzeit_monate=24,
        anschlusspreis=39.99,
        quelle_url=f"https://example.org/{anbieter}/buendel",
        abgerufen_am=HEUTE,
        zustand="neu",
    )


def _listung(anbieter: str) -> dict:
    return {
        "sku_id": SKU,
        "device_id": "pruefer-phone",
        "speicher_gb": 256,
        "anbieter": anbieter,
        "zustand": "neu",
        "farbe_normalisiert": "schwarz",
        "quelle_url": f"https://example.org/{anbieter}",
        "abgerufen_am": HEUTE,
    }


def _o2_karte(name: str) -> dict:
    buendel = [_buendel("Vodafone", 30.0, "Vodafone M"), _buendel("o2", 20.0, name)]
    listungen = [_listung("Vodafone"), _listung("o2")]
    erg = geraete_tco_karten.modelle(buendel, listungen, [], {}, None, heute=HEUTE)
    return next(k for k in erg["modelle"][0]["karten"] if k["anbieter"] == "o2")


def _zeile(karte: dict) -> str:
    modul = seiten._env().get_template("_geraete_buendel.html.j2").make_module()
    return str(modul.buendelzeile(karte))


def test_plus_zeile_zeigt_keinen_preis_keine_rechnung_nur_den_grund():
    karte = _o2_karte(PLUS)
    assert karte["bedingter_tarif"] and karte["gesamt"] is not None
    zeile = _zeile(karte)
    assert GRUND == "nur mit Zweitprodukt – nicht vergleichbar"
    assert GRUND in zeile
    for betrag in ("20,00", "39,99", "30,00", "1,00"):
        assert betrag not in zeile, betrag
    assert "gr-bnd-rechnung" not in zeile and "gr-bnd-summe" not in zeile
    assert 'data-gesamt=""' in zeile and 'data-schnitt=""' in zeile
    assert "gr-bnd--leer" in zeile


def test_gegenprobe_dasselbe_buendel_ohne_plus_zeigt_seinen_preis():
    zeile = _zeile(_o2_karte(OHNE_PLUS))
    assert "Zweitprodukt" not in zeile
    assert 'data-gesamt=""' not in zeile
    assert "gr-bnd-rechnung" in zeile and "20,00" in zeile
    assert "gr-bnd--leer" not in zeile


def test_anzeige_blankt_nur_die_kopie_und_nur_bei_plus():
    karte = _o2_karte(PLUS)
    gesamt = karte["gesamt"]
    kopie = geraete_preisstand.anzeige(karte)
    assert karte["gesamt"] == gesamt
    assert kopie["gesamt"] is None and kopie["delta"] is None
    assert kopie["belastbar"] is False and kopie["rechnung"] == []
    assert kopie["luecke_kurz"] == geraete_preisstand.KURZ_BEDINGT
    assert kopie["leer_grund"] == GRUND
    ohne = _o2_karte(OHNE_PLUS)
    assert geraete_preisstand.anzeige(ohne) is ohne


def test_die_plus_zeile_zaehlt_nicht_fuer_vergleich_und_durchschnitt():
    modell = geraete_tco_karten.modelle(
        [_buendel("Vodafone", 30.0, "Vodafone M"), _buendel("o2", 20.0, PLUS)],
        [_listung("Vodafone"), _listung("o2")],
        [],
        {},
        None,
        heute=HEUTE,
    )["modelle"][0]
    o2 = next(k for k in modell["karten"] if k["anbieter"] == "o2")
    assert o2["zaehlt"] is False and o2["notbremse"]["kurz"] == "nur mit Zweitprodukt"
    assert o2["delta"] is None


def _csv_zeilen(*buendel):
    zeilen = geraete_tco_view._export_zeilen(
        list(buendel), [], [], None, {}, None, HEUTE
    )
    text, _ = tco_csv(zeilen)
    kopf, *rest = csv.reader(io.StringIO(text), delimiter=";")
    return {r[kopf.index("SKU-ID")]: dict(zip(kopf, r, strict=True)) for r in rest}


def test_export_nennt_den_grund_statt_der_zahl():
    plus = _buendel("o2", 20.0, PLUS, sku="p")
    ohne = _buendel("o2", 20.0, OHNE_PLUS, sku="q")
    zeilen = _csv_zeilen(plus, ohne)
    assert zeilen["p"]["Tarif/Monat EUR"] == "" and zeilen["p"][SPALTE_UEBER_24] == ""
    assert zeilen["p"]["Lücke"] == GRUND
    assert zeilen["q"]["Tarif/Monat EUR"] == "20,00" and zeilen["q"][SPALTE_UEBER_24]
    assert zeilen["q"]["Lücke"] == ""


def test_plus_wort_bei_einem_anderen_anbieter_ist_kein_zweitprodukt_tarif():
    assert geraete_preisstand.buendel_luecke(_buendel("o2", 20.0, PLUS), HEUTE) == GRUND
    assert (
        geraete_preisstand.buendel_luecke(_buendel("Vodafone", 20.0, PLUS), HEUTE) == ""
    )
    assert (
        geraete_preisstand.buendel_luecke(_buendel("o2", 20.0, OHNE_PLUS), HEUTE) == ""
    )


def _o2_adressen() -> list[str]:
    """Alle Startadressen der o2-Einträge (``o2``, ``o2-tarife``, ``o2-tarife-2`` …)."""
    roh = yaml.safe_load(
        (WURZEL / "config" / "klick_tageslauf.yaml").read_text("utf-8")
    )
    return [
        s["url"]
        for a in roh["anbieter"]
        if a["schluessel"] == "o2" or a["schluessel"].startswith("o2-")
        for s in a["seiten"]
    ]


def _tarif(url: str) -> str:
    return dict(p.split("=", 1) for p in url.split("?", 1)[1].split("&")).get(
        "tarif", ""
    )


def test_jede_o2_startadresse_mit_tarif_m_hat_24_raten_und_kein_plus():
    adressen = _o2_adressen()
    m = [u for u in adressen if _tarif(u) == "o2-mobile-on-demand-m"]
    assert len(m) >= 67, "das Band M der Klick-Startadressen ist da"
    for url in m:
        assert "ratenzahlung=24" in url.split("?", 1)[1].split("&"), url
    assert not [u for u in adressen if "on-demand-m-plus" in u]
    assert [
        u for u in adressen if "ratenzahlung=24" not in u.split("?", 1)[1].split("&")
    ] == []
