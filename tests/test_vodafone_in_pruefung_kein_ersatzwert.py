"""Hält die Prüfstelle den Vodafone-Preis zurück, steht kein Ersatzwert im Vergleich.

Prüfung 11.11.2026 (Galaxy S26 256 GB): alle Vodafone-Bündel standen in Quarantäne
(Regel 11), die Seite verglich 1&1 (1.231,66 €) trotzdem mit „Vodafone 1.518,70 €“ -
der Näherung aus Tarif ohne Gerät plus Barpreis - und nannte „18,9 % günstiger“.
Jetzt hat das Modell keine Vodafone-Referenz, der Radar nennt „Vodafone-Preis wird
geprüft“. Gegenproben: ohne eigenes Bündel bleibt die Näherung, ein gültiges eigenes
Bündel bleibt die Referenz. Synthetisch, fester Bezugstag.
"""

from __future__ import annotations

from telco_radar.report import (
    geraete_eigen_pruefung,
    geraete_radar,
    geraete_tco_karten,
    geraete_view,
)
from telco_radar.report import html as seiten
from telco_radar.report.geraete_preisposition_preise import preise_je_anbieter
from telco_radar.tco_model import Buendel, SimOnlyReferenz

HEUTE = "2026-11-11"
SKU = "pruefer-phone-256-schwarz"
BAENDER = {"vodafone:xs": "xs", "vodafone:m": "m", "11:s": "xs", "11:m": "m"}
BARPREIS = 799.90
NAEHERUNG = round(24 * 29.95 + BARPREIS, 2)


def _buendel(anbieter: str, tarif_id: str, tarif: float, pruefung=None) -> Buendel:
    return Buendel(
        sku_id=SKU,
        anbieter=anbieter,
        tarif_name=f"{anbieter} {tarif_id.split(':')[1].upper()}",
        tarif_id=tarif_id,
        tarif_monatlich=tarif,
        geraet_zuzahlung=1.0,
        geraet_monatsrate=29.25,
        laufzeit_monate=24,
        anschlusspreis=39.99,
        quelle_url=f"https://example.org/{anbieter}/{tarif_id}",
        abgerufen_am=HEUTE,
        zustand="neu",
        pruefung=pruefung,
    )


def _listung(anbieter: str, preis: float | None = None) -> dict:
    return {
        "sku_id": SKU,
        "device_id": "pruefer-phone",
        "speicher_gb": 256,
        "anbieter": anbieter,
        "zustand": "neu",
        "farbe_normalisiert": "schwarz",
        "preis_ohne_vertrag": preis,
        "quelle_url": f"https://example.org/{anbieter}",
        "abgerufen_am": HEUTE,
    }


def _sim_only() -> SimOnlyReferenz:
    return SimOnlyReferenz(
        anbieter="Vodafone",
        tarif_name="Vodafone Mobil XS",
        tarif_id="vodafone:xs",
        tarif_sim_only_monatlich=29.95,
        quelle_url="https://example.org/vodafone/tarife",
        abgerufen_am=HEUTE,
    )


def _modell(vodafone: list[Buendel]) -> dict:
    buendel = [
        *vodafone,
        _buendel("1&1", "11:s", 20.0),
        _buendel("1&1", "11:m", 25.0),
    ]
    listungen = [_listung("Vodafone", BARPREIS), _listung("1&1")]
    erg = geraete_tco_karten.modelle(
        buendel, listungen, [_sim_only()], {}, None, heute=HEUTE, band_je_tarif=BAENDER
    )
    return erg["modelle"][0]


def _in_pruefung() -> dict:
    return _modell(
        [
            _buendel("Vodafone", "vodafone:xs", 31.95, "quarantaene 11"),
            _buendel("Vodafone", "vodafone:m", 33.45, "quarantaene 11"),
        ]
    )


def _radarzeile(modell: dict) -> dict:
    gruppen = geraete_radar.netzbetreiber_gruppen([modell], BAENDER)
    return geraete_radar.modellliste(gruppen)["zeilen"][0]


def test_preis_in_pruefung_bekommt_keine_naeherung_als_referenz():
    modell = _in_pruefung()
    assert modell["referenz"] is None
    assert not any(k["naeherung"] for k in modell["karten"])
    assert geraete_eigen_pruefung.zurueckgehalten(modell["karten"])
    fremde = [k for k in modell["karten"] if k["anbieter"] == "1&1"]
    assert fremde and all(k["delta"] is None for k in fremde)


def test_radar_nennt_die_pruefung_statt_einer_vodafone_zahl():
    zeile = _radarzeile(_in_pruefung())
    assert zeile["vf_gesamt"] is None and zeile["prozent"] is None
    assert zeile["luecke"] == "Vodafone-Preis wird geprüft"
    assert zeile["vodafone"] is None
    assert "wird geprüft" in zeile["vodafone_grund"]
    assert all(z.get("vf_gesamt") is None for z in zeile["gruppe_zeilen"])
    modul = seiten._env().get_template("_geraete_radar.html.j2").make_module()
    text = str(modul.modellzeile(zeile, 1))
    assert "Vodafone-Preis wird geprüft" in text
    assert 'data-s-vf=""' in text and 'data-s-prozent=""' in text
    assert "1.518,70" not in text and "· VF" not in text


def test_kennzahl_ueber_10_prozent_teurer_zaehlt_das_modell_nicht():
    modell = _in_pruefung()
    assert "Vodafone" not in preise_je_anbieter(modell)
    spalte = geraete_view._tco_spalte(modell, HEUTE)
    assert spalte["tco_delta"] is None
    assert spalte["tco_delta_leer"] == geraete_eigen_pruefung.KURZ


def test_gegenprobe_ohne_eigenes_buendel_bleibt_die_naeherung():
    modell = _modell([])
    assert modell["referenz"]["gesamt"] == NAEHERUNG == 1518.70
    assert not modell["referenz"].get("aus_buendel")
    zeile = _radarzeile(modell)
    assert zeile["vf_gesamt"] == NAEHERUNG and zeile["prozent"] is not None
    assert zeile["luecke"] == ""


def test_gegenprobe_gueltiges_eigenes_buendel_bleibt_die_referenz():
    modell = _modell(
        [
            _buendel("Vodafone", "vodafone:xs", 31.95, "gueltig"),
            _buendel("Vodafone", "vodafone:m", 33.45, "quarantaene 11"),
        ]
    )
    assert modell["referenz"]["aus_buendel"]
    zeile = _radarzeile(modell)
    assert zeile["vf_gesamt"] == modell["referenz"]["gesamt"]
    assert zeile["prozent"] is not None and zeile["luecke"] == ""


def test_gegenprobe_veraltetes_eigenes_buendel_ist_kein_preis_in_pruefung():
    alt = _buendel("Vodafone", "vodafone:xs", 31.95, "quarantaene 11")
    alt.abgerufen_am = "2026-10-01"
    modell = _modell([alt])
    assert not geraete_eigen_pruefung.zurueckgehalten(modell["karten"])
    assert modell["referenz"]["gesamt"] == NAEHERUNG
