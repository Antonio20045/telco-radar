"""Ein veralteter Preis steht auf keiner Bündelzeile als aktueller Preis.

Befund 02.11.2026 (Preisprüfung gegen die Originale): 1&1 und Telekom zeigten auf der
Detailzeile einen Preis aus alten Daten mit voller Rechnung, nur mit einer Marke
daneben. Tabelle, Graph und „Alle Geräte" nehmen solche Karten schon heraus; die
Zeile selbst nennt jetzt statt der Zahl die benannte Lücke („kein aktueller Stand
seit TT.MM.JJJJ" bzw. „veraltet"). Fester Bezugstag, kein heutiges Datum.
"""

from __future__ import annotations

import pytest

from telco_radar.report import geraete_tco_karten
from telco_radar.report import html as seitenbau
from telco_radar.report.geraete_tco_grafik import euro
from telco_radar.tco_model import Buendel

HEUTE = "2026-11-02"
ALT = "2026-10-20"
SKU = "preis-phone-256-schwarz"
EINDEUTIG = 23.17


def _buendel(anbieter, tarif, abgerufen_am=HEUTE, pruefung=None):
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
        abgerufen_am=abgerufen_am,
        zustand="neu",
        pruefung=pruefung,
    )


def _listung(anbieter):
    return {
        "sku_id": SKU,
        "device_id": "preis-phone",
        "speicher_gb": 256,
        "anbieter": anbieter,
        "zustand": "neu",
        "farbe_normalisiert": "schwarz",
        "quelle_url": f"https://example.org/{anbieter}",
        "abgerufen_am": HEUTE,
    }


def _zeilen(stand_o2):
    """Vodafone frisch, o2 mit dem übergebenen Stand; je Anbieter die Karte."""
    buendel = [_buendel("Vodafone", 30.0), _buendel("o2", EINDEUTIG, **stand_o2)]
    listungen = [_listung("Vodafone"), _listung("o2")]
    erg = geraete_tco_karten.modelle(buendel, listungen, [], {}, None, heute=HEUTE)
    modell = erg["modelle"][0]
    return {k["anbieter"]: k for k in modell["karten"] if k.get("sku_id")}


def _html(karte):
    modul = seitenbau._env().get_template("_geraete_buendel.html.j2").make_module()
    return str(modul.buendelzeile(karte))


STAENDE = {
    "zu_alt": {"abgerufen_am": ALT},
    "pruefung_veraltet": {"pruefung": "veraltet 16"},
}


@pytest.mark.parametrize("stand", sorted(STAENDE))
def test_veralteter_preis_steht_als_luecke_nicht_als_zahl(stand):
    karten = _zeilen(STAENDE[stand])
    o2 = karten["o2"]
    assert o2["gesamt"] is not None, "die Karte rechnet; die Zeile zeigt nur nichts"
    html = _html(o2)
    zahl = euro(o2["gesamt"])
    assert zahl not in html, f"veralteter Preis {zahl} steht auf der Zeile"
    assert euro(EINDEUTIG) not in html, "auch der Einzelposten fehlt"
    assert 'data-gesamt=""' in html
    assert 'data-schnitt=""' in html
    assert "gr-bnd-rechnung" not in html and "gr-bnd-zerl" not in html
    assert "keine belastbare Zahl" not in html, "die Lücke hat einen Namen"
    assert "veraltet" in html or "kein aktueller Stand" in html


def test_alte_zeile_nennt_das_abrufdatum_in_der_luecke():
    html = _html(_zeilen(STAENDE["zu_alt"])["o2"])
    assert "kein aktueller Stand seit 20.10.2026" in html


@pytest.mark.parametrize("stand", [{}, {"pruefung": "gueltig"}], ids=["nie", "gueltig"])
def test_gegenprobe_frischer_geprueft_gueltiger_preis_bleibt_sichtbar(stand):
    karten = _zeilen(stand)
    o2 = karten["o2"]
    html = _html(o2)
    assert euro(o2["gesamt"]) in html
    assert f'data-gesamt="{o2["gesamt"]}"' in html
    assert "gr-bnd-rechnung" in html
    assert "kein aktueller Stand" not in html


def test_gegenprobe_die_frische_zeile_daneben_bleibt_unberuehrt():
    karten = _zeilen(STAENDE["zu_alt"])
    vodafone = karten["Vodafone"]
    assert euro(vodafone["gesamt"]) in _html(vodafone)
