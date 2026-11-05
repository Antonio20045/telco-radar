"""Ein Preis in Quarantäne steht nicht auf der Seite: „Preis in Prüfung“ statt Zahl.

Prüferprotokoll 05.11.2026 (o2 Galaxy S26 256, Band M, Regel 5): die Karte hielt
Δ, Sieger und Spanne zurück, zeigte aber weiter Gesamtpreis, Rate und Rechnung.
Maßstab: lieber kein Preis als ein falscher. Die Zeile nutzt denselben Weg wie
ein veralteter Preis (``geraete_preisstand``); Export und Seite teilen die
Entscheidung. Synthetisch, fester Bezugstag.
"""

from __future__ import annotations

import csv
import io

import pytest

from telco_radar.report import geraete_preisstand, geraete_tco_karten, geraete_tco_view
from telco_radar.report import html as seiten
from telco_radar.report.geraete_export import SPALTE_UEBER_24, tco_csv
from telco_radar.tco_model import Buendel

HEUTE = "2026-11-05"
SKU = "pruefer-phone-256-schwarz"


def _buendel(anbieter: str, tarif: float, pruefung: str | None = None) -> Buendel:
    return Buendel(
        sku_id=SKU,
        anbieter=anbieter,
        tarif_name=f"{anbieter} M",
        tarif_monatlich=tarif,
        geraet_zuzahlung=1.0,
        geraet_monatsrate=30.0,
        laufzeit_monate=24,
        anschlusspreis=39.99,
        quelle_url=f"https://example.org/{anbieter}/buendel",
        abgerufen_am=HEUTE,
        zustand="neu",
        pruefung=pruefung,
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


def _o2_karte(pruefung: str | None) -> dict:
    buendel = [_buendel("Vodafone", 30.0), _buendel("o2", 20.0, pruefung)]
    listungen = [_listung("Vodafone"), _listung("o2")]
    erg = geraete_tco_karten.modelle(buendel, listungen, [], {}, None, heute=HEUTE)
    return next(k for k in erg["modelle"][0]["karten"] if k["anbieter"] == "o2")


def _zeile(karte: dict) -> str:
    modul = seiten._env().get_template("_geraete_buendel.html.j2").make_module()
    return str(modul.buendelzeile(karte))


def test_quarantaene_zeigt_keinen_preis_nur_den_hinweis():
    karte = _o2_karte("quarantaene 5")
    zeile = _zeile(karte)
    assert karte["quarantaene"] and karte["gesamt"] is not None
    assert "Preis in Prüfung" in zeile
    assert 'data-gesamt=""' in zeile and 'data-schnitt=""' in zeile
    assert "gr-bnd--leer" in zeile
    assert "gr-bnd-rechnung" not in zeile and "gr-bnd-summe" not in zeile
    assert "gr-kk-marke--notbremse" not in zeile
    for betrag in ("20,00", "30,00", "39,99", "1,00"):
        assert betrag not in zeile, betrag


def test_gegenprobe_gueltiges_buendel_zeigt_seinen_preis():
    karte = _o2_karte(None)
    zeile = _zeile(karte)
    assert "Preis in Prüfung" not in zeile
    assert 'data-gesamt=""' not in zeile
    assert "gr-bnd-rechnung" in zeile
    assert "gr-bnd--leer" not in zeile
    assert "Euro" in zeile or "€" in zeile


@pytest.mark.parametrize("pruefung", [None, "gueltig", "unbekannt RuntimeError: x"])
def test_gegenprobe_nur_quarantaene_wird_zur_luecke(pruefung):
    karte = _o2_karte(pruefung)
    assert geraete_preisstand.anzeige(karte) is karte


def test_anzeige_laesst_die_karte_unveraendert_und_blankt_die_kopie():
    karte = _o2_karte("quarantaene 5")
    gesamt = karte["gesamt"]
    kopie = geraete_preisstand.anzeige(karte)
    assert karte["gesamt"] == gesamt
    assert kopie["gesamt"] is None and kopie["delta"] is None
    assert kopie["belastbar"] is False
    assert kopie["luecke_kurz"] == geraete_preisstand.KURZ_PRUEFUNG
    assert kopie["leer_grund"] == "Preis in Prüfung."


def _csv_zeilen(*buendel):
    zeilen = geraete_tco_view._export_zeilen(
        list(buendel), [], [], None, {}, None, HEUTE
    )
    text, _ = tco_csv(zeilen)
    kopf, *rest = csv.reader(io.StringIO(text), delimiter=";")
    return {r[kopf.index("SKU-ID")]: dict(zip(kopf, r, strict=True)) for r in rest}


def test_export_nennt_den_hinweis_statt_der_zahl():
    import dataclasses

    gesperrt = dataclasses.replace(_buendel("o2", 20.0, "quarantaene 5"), sku_id="g")
    gut = dataclasses.replace(_buendel("o2", 20.0), sku_id="h")
    zeilen = _csv_zeilen(gesperrt, gut)
    assert zeilen["g"]["Tarif/Monat EUR"] == "" and zeilen["g"][SPALTE_UEBER_24] == ""
    assert zeilen["g"]["Lücke"] == "Preis in Prüfung."
    assert zeilen["h"]["Tarif/Monat EUR"] == "20,00" and zeilen["h"][SPALTE_UEBER_24]
    assert zeilen["h"]["Lücke"] == ""
