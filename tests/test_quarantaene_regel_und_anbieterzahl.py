"""Zwei Befunde vom 17.11.2026, Auftrag A-4JR34A.

1. Die Lücke einer Quarantäne-Zeile nannte nur „Preis in Prüfung.“, nie die
verletzte Regel - ein Sprung von 0 auf 29 Telekom-Quarantänezeilen war aus dem
Export allein nicht beurteilbar (``arbeit/ursache-rueckgang-1717.md``, Abschnitt 3).
Jetzt steht die Regel mit Nummer dabei, wie an der kurzen Marke der Notbremse
(``geraete_notbremse.zustand``).

2. Der Export nennt je Anbieter zwei Zahlen - Zeilen und davon mit Gesamtpreis
(``geraete_export_anbieter.je_anbieter``) -, DIE EINE Stelle, an der diese Zahl entsteht
(Clean Code 1): sonst zählt jede Abnahme sie von Hand aus der CSV neu und hält
dabei leicht zwei verschiedene Regeln (Tagesdatei, Exportansicht) für vergleichbar.
"""

from __future__ import annotations

import csv
import io

from telco_radar.report import geraete_preisstand, geraete_tco_karten, geraete_tco_view
from telco_radar.report.geraete_export import SPALTE_UEBER_24, tco_csv
from telco_radar.report.geraete_export_anbieter import je_anbieter
from telco_radar.tco_model import Buendel

HEUTE = "2026-11-17"
SKU = "pruefer-phone-256-schwarz"


def _buendel(anbieter: str, sku: str = SKU, pruefung: str | None = None) -> Buendel:
    return Buendel(
        sku_id=sku,
        anbieter=anbieter,
        tarif_name=f"{anbieter} M",
        tarif_monatlich=30.0,
        geraet_zuzahlung=1.0,
        geraet_monatsrate=20.0,
        laufzeit_monate=24,
        anschlusspreis=39.99,
        quelle_url=f"https://example.org/{anbieter}/{sku}",
        abgerufen_am=HEUTE,
        zustand="neu",
        pruefung=pruefung,
    )


def _listung(anbieter: str, sku: str = SKU) -> dict:
    return {
        "sku_id": sku,
        "device_id": "pruefer-phone",
        "speicher_gb": 256,
        "anbieter": anbieter,
        "zustand": "neu",
        "farbe_normalisiert": "schwarz",
        "quelle_url": f"https://example.org/{anbieter}",
        "abgerufen_am": HEUTE,
    }


def _karte(anbieter: str, pruefung: str | None, sku: str = SKU) -> dict:
    buendel = [_buendel("Vodafone", sku), _buendel(anbieter, sku, pruefung)]
    listungen = [_listung("Vodafone", sku), _listung(anbieter, sku)]
    erg = geraete_tco_karten.modelle(buendel, listungen, [], {}, None, heute=HEUTE)
    return next(k for k in erg["modelle"][0]["karten"] if k["anbieter"] == anbieter)


def test_die_luecke_nennt_die_verletzte_regel_mit_nummer():
    karte = _karte("Telekom", "quarantaene 11")
    kopie = geraete_preisstand.anzeige(karte)
    assert kopie["luecke_kurz"] == geraete_preisstand.KURZ_PRUEFUNG
    assert kopie["leer_grund"] == "Preis in Prüfung. Regel 11: Sprung zum Vortag."


def test_mehrere_regeln_stehen_beide_in_der_luecke():
    karte = _karte("Telekom", "quarantaene 5 11")
    kopie = geraete_preisstand.anzeige(karte)
    assert kopie["leer_grund"] == (
        "Preis in Prüfung. Regel 5: Preis je Speicher. Regel 11: Sprung zum Vortag."
    )


def test_gegenprobe_ohne_regelnummer_bleibt_der_grundsatz():
    karte = _karte("Telekom", "quarantaene")
    kopie = geraete_preisstand.anzeige(karte)
    assert kopie["leer_grund"] == "Preis in Prüfung."


def _csv_zeilen(*buendel):
    zeilen = geraete_tco_view._export_zeilen(
        list(buendel), [], [], None, {}, None, HEUTE
    )
    text, _ = tco_csv(zeilen)
    kopf, *rest = csv.reader(io.StringIO(text), delimiter=";")
    gefunden = {r[kopf.index("SKU-ID")]: dict(zip(kopf, r, strict=True)) for r in rest}
    return zeilen, gefunden


def test_export_zaehlt_zeilen_und_zeilen_mit_gesamtpreis_je_anbieter():
    import dataclasses

    gesperrt = dataclasses.replace(
        _buendel("Telekom", pruefung="quarantaene 11"), sku_id="g"
    )
    gut_1 = dataclasses.replace(_buendel("Telekom"), sku_id="h1")
    gut_2 = dataclasses.replace(_buendel("o2"), sku_id="h2")
    zeilen, csv_zeilen = _csv_zeilen(gesperrt, gut_1, gut_2)

    assert csv_zeilen["g"][SPALTE_UEBER_24] == ""
    assert csv_zeilen["h1"][SPALTE_UEBER_24] and csv_zeilen["h2"][SPALTE_UEBER_24]

    je_ab = {e["anbieter"]: e for e in je_anbieter(zeilen)}
    assert je_ab["Telekom"] == {
        "anbieter": "Telekom",
        "zeilen": 2,
        "mit_gesamtpreis": 1,
    }
    assert je_ab["o2"] == {"anbieter": "o2", "zeilen": 1, "mit_gesamtpreis": 1}


def test_je_anbieter_ohne_zeilen_bleibt_leer():
    assert je_anbieter({}) == []
    assert je_anbieter({"buendel": []}) == []
