"""Tarifwelt im Tageslauf: Einhaengung, Band im Bericht, Wächter, Versand.

Alles gegen die gespeicherten Fixtures vom 08.11.2026
(`tests/fixtures/geraete/tarifwelt_mm_*`, Reste der Abrufe in `_herkunft.json`).
Kein Netz, kein Zugriff auf data/.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

import yaml
from bestand_pfad import lese_wurzel
from test_geraete_adapter_tarifwelt import LEITER, fixture_hole

from telco_radar import geraete_tarifwelt, tarifwelt_bestand
from telco_radar.analyze.tco_store import TcoDB
from telco_radar.collect.geraete import tarifwelt_lauf
from telco_radar.collect.geraete.basis import GeraeteAbrufFehler
from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import geraete_tco_band as bandmod
from telco_radar.report import geraete_tco_karten as karten
from telco_radar.tco_model import tco_24

WURZEL = pathlib.Path(__file__).resolve().parents[1]
KATALOG = lade_katalog(lese_wurzel())


def _vodafone_tarife() -> dict:
    """Die Vodafone-Leiter im Format des Tarifbestands (`je_id_aktuell`)."""
    return {
        f"vodafone:mobil-{k}": {
            "anbieter": "Vodafone",
            "name": f"Vodafone Mobil {k.upper()} mit Smartphone",
            "datenvolumen_gb": gb,
            "grundgebuehr": 20.0 + i * 10,
        }
        for i, (k, gb) in enumerate(LEITER)
    }


@dataclass
class _Quelle:
    methode: str
    aktiv: bool
    rate_limit_sekunden: float = 0.0


@dataclass
class _Quellen:
    anbieter: list


def _lauf_beide_geraete():
    hole, _ = fixture_hole()
    teile = [
        tarifwelt_lauf.lies_modell(m, LEITER, hole, "2026-11-08", warte=lambda s: None)
        for m in ("apple-iphone-17", "samsung-galaxy-s26")
    ]
    return teile


def test_lauf_traegt_die_stammdaten_jedes_tarifs_fuer_das_band():
    for teil in _lauf_beide_geraete():
        assert teil.buendel
        assert {b.tarif_id for b in teil.buendel} == set(teil.tarife)
        for tid, satz in teil.tarife.items():
            assert tid.startswith("mediamarkt_tarifwelt:")
            assert satz["anbieter"].startswith("Saturn/MediaMarkt · ")
            assert satz["name"]
            assert satz["datenvolumen_gb"] is not None


def test_tarifwelt_tarife_bekommen_im_bericht_dasselbe_band_wie_ein_netzbetreibertarif(
    tmp_path,
):
    """Mit dem Bestand bekommt jeder Tarifwelt-Tarif das Band, in das die
    Vodafone-Leiter sein Volumen legt; ohne ihn bleibt er ohne Band (Gegenprobe)."""
    vf = _vodafone_tarife()
    tarife = {}
    for teil in _lauf_beide_geraete():
        tarife.update(teil.tarife)
    ohne = bandmod.tarif_baender(vf)
    assert not any(t.startswith("mediamarkt_tarifwelt:") for t in ohne)

    pfad = tmp_path / "geraete_tco.json"
    abgelegt = TcoDB(pfad)
    abgelegt.haendler_tarife.update(tarife)
    abgelegt.upsert_buendel(
        [b for teil in _lauf_beide_geraete() for b in teil.buendel], "2026-11-08"
    )
    assert abgelegt.save("2026-11-08")
    gelesen = TcoDB(pfad).haendler_tarife
    assert set(gelesen) == set(tarife)

    gesamt = tarifwelt_bestand.mit_tarifwelt(vf, gelesen)
    assert set(vf) <= set(gesamt) and set(tarife) <= set(gesamt)
    baender = bandmod.tarif_baender(gesamt)
    leiter = bandmod.tarifleiter(gesamt)
    assert set(tarife) <= set(baender), "jeder Tarifwelt-Tarif hat ein Band"
    for tid, satz in tarife.items():
        assert baender[tid] == bandmod.band_von_gb(satz["datenvolumen_gb"], leiter)
    allnet = [t for t, s in tarife.items() if s["datenvolumen_gb"] == 50.0]
    assert allnet and all(baender[t] == "m" for t in allnet)
    vorher = bandmod.tarif_baender(vf)
    assert {t: baender[t] for t in vorher} == vorher


def test_bestand_ueberschreibt_keinen_netzbetreiber_tarif():
    zusatz = {
        "vodafone:mobil-m": {"datenvolumen_gb": 1},
        "mediamarkt_tarifwelt:x": {"datenvolumen_gb": 5},
    }
    vf = _vodafone_tarife()
    gesamt = tarifwelt_bestand.mit_tarifwelt(vf, zusatz)
    assert gesamt["vodafone:mobil-m"] == vf["vodafone:mobil-m"]
    assert gesamt["mediamarkt_tarifwelt:x"]["datenvolumen_gb"] == 5
    assert tarifwelt_bestand.mit_tarifwelt(vf, None) == vf


def test_buendel_der_tarifwelt_stehen_im_band_der_karten():
    """Karten (`geraete_tco_karten.modelle`) und Baender des Berichts: die
    Saturn-Zeile steht im Band ihres Tarifs, nicht unter "ohne Band"."""
    vf = _vodafone_tarife()
    tarife, buendel = {}, []
    for teil in _lauf_beide_geraete():
        tarife.update(teil.tarife)
        buendel.extend(teil.buendel)
    gesamt = {**tarife, **vf}
    modelle = karten.modelle(buendel, [], [], gesamt, KATALOG)["modelle"]
    iphone = next(m for m in modelle if m["id"].startswith("apple-iphone-17-256"))
    leiter = bandmod.tarifleiter(gesamt)
    band_je_tarif = bandmod.tarif_baender(gesamt, leiter)
    je_band = bandmod.alle_karten_je_band(iphone, band_je_tarif)
    saturn = {
        a
        for je_anbieter in je_band.values()
        for a in je_anbieter
        if a.startswith("Saturn/MediaMarkt")
    }
    assert saturn == {
        "Saturn/MediaMarkt · Telekom-Netz",
        "Saturn/MediaMarkt · o2-Netz",
    }
    for b in buendel:
        if b.sku_id.startswith("apple-iphone-17-256"):
            assert any(
                k["anbieter"] == b.anbieter
                and abs(k["gesamt"] - tco_24(b).gesamt) < 0.005
                for ks in (je_band[band_je_tarif[b.tarif_id]][b.anbieter],)
                for k in ks
            )


def test_stufe_ist_aus_solange_die_quelle_inaktiv_ist_die_echte_config_ist_aktiv():
    hole, aufrufe = fixture_hole()
    quellen = _Quellen([_Quelle("mediamarkt_tarifwelt", aktiv=False)])
    e = geraete_tarifwelt.lauf(quellen, _vodafone_tarife(), hole, "2026-11-08")
    assert (e.status, e.buendel, aufrufe) == ("aus", [], [])
    echt = lade_quellen(WURZEL)
    assert geraete_tarifwelt.quelle_aktiv(echt)
    assert any(a.methode == "mediamarkt_tarifwelt" for a in echt.anbieter)


def test_aktive_stufe_liest_nur_pflichtmodelle_und_sammelt_tarife(monkeypatch):
    hole, aufrufe = fixture_hole()
    quellen = _Quellen([_Quelle("mediamarkt_tarifwelt", aktiv=True)])
    monkeypatch.setattr(
        geraete_tarifwelt,
        "pflicht_modelle",
        lambda: frozenset({"apple-iphone-17", "samsung-galaxy-s26"}),
    )
    e = geraete_tarifwelt.lauf(
        quellen, _vodafone_tarife(), hole, "2026-11-08", warte=lambda s: None
    )
    assert e.status == "ok" and e.modelle == 2
    assert {b.sku_id.split("-256")[0] for b in e.buendel} >= {
        "apple-iphone-17",
        "samsung-galaxy-s26",
    }
    assert set(e.tarife) == {b.tarif_id for b in e.buendel}
    assert all("/pks" not in u and "checkout" not in u for u in aufrufe)


def test_ohne_vodafone_leiter_kein_abruf():
    hole, aufrufe = fixture_hole()
    quellen = _Quellen([_Quelle("mediamarkt_tarifwelt", aktiv=True)])
    e = geraete_tarifwelt.lauf(quellen, {}, hole, "2026-11-08")
    assert e.status == "keine_leiter" and aufrufe == [] and e.buendel == []


def test_schutzantwort_beendet_die_stufe_ohne_weiteren_abruf(monkeypatch):
    aufrufe = []

    def hole(url, **kw):
        aufrufe.append(url)
        return (403, "Forbidden")

    monkeypatch.setattr(
        geraete_tarifwelt,
        "pflicht_modelle",
        lambda: frozenset({"apple-iphone-17", "samsung-galaxy-s26"}),
    )
    quellen = _Quellen([_Quelle("mediamarkt_tarifwelt", aktiv=True)])
    e = geraete_tarifwelt.lauf(
        quellen, _vodafone_tarife(), hole, "2026-11-08", warte=lambda s: None
    )
    assert e.status == "abgebrochen" and len(aufrufe) == 1 and e.buendel == []
    assert "Schutzantwort" in e.grund
    assert issubclass(GeraeteAbrufFehler, Exception)


def test_waechter_config_nennt_die_drei_netzzeilen_erst_wirksam_bei_aktiv():
    daten = yaml.safe_load((WURZEL / "config" / "geraete_abdeckung.yaml").read_text())
    vorbereitet = daten["pflicht_anbieter_wenn_aktiv"]
    assert vorbereitet["MediaMarkt/Saturn Tarifwelt"] == [
        "Saturn/MediaMarkt · Telekom-Netz",
        "Saturn/MediaMarkt · Vodafone-Netz",
        "Saturn/MediaMarkt · o2-Netz",
    ]
    assert not set(sum(vorbereitet.values(), [])) & set(daten["pflicht_anbieter"])


def test_tageslauf_stufe_schreibt_buendel_und_tarifbestand(tmp_path, monkeypatch):
    """`geraete_tarifwelt.stufe`: Buendel UND Stammdaten im TCO-Store,
    nach `save` und neuem Lesen in `geraete_tco.json`; inaktiv schreibt nichts."""
    from datetime import UTC, datetime

    from telco_radar.tarif_bezug import Tarifbestand

    monkeypatch.setattr(
        geraete_tarifwelt,
        "pflicht_modelle",
        lambda: frozenset({"apple-iphone-17", "samsung-galaxy-s26"}),
    )
    monkeypatch.setattr(geraete_tarifwelt.time, "sleep", lambda s: None)
    bestand = Tarifbestand(
        [{"tarif_id": tid, **satz} for tid, satz in _vodafone_tarife().items()]
    )
    api, _ = fixture_hole()

    def hole(url, **kw):
        if url.endswith("/robots.txt"):
            return (404, "")
        return api(url, **kw)

    def uhr():
        return datetime(2026, 11, 8, 3, tzinfo=UTC)

    tco = TcoDB(tmp_path / "geraete_tco.json")
    aus = geraete_tarifwelt.stufe(
        _Quellen([_Quelle("mediamarkt_tarifwelt", False)]),
        bestand,
        hole,
        uhr,
        "2026-11-08",
        tmp_path,
        tco,
    )
    assert aus == {"status": "aus"}
    assert not tco.haendler_tarife

    an = geraete_tarifwelt.stufe(
        _Quellen([_Quelle("mediamarkt_tarifwelt", True)]),
        bestand,
        hole,
        uhr,
        "2026-11-08",
        tmp_path,
        tco,
    )
    assert an["status"] == "ok" and an["buendel"] == 4, an
    assert len(tco.buendel()) == 4
    assert {b["tarif_id"] for b in tco.buendel()} == set(tco.haendler_tarife)
    assert tco.save("2026-11-08")
    assert {b["tarif_id"] for b in tco.buendel()} == set(
        TcoDB(tmp_path / "geraete_tco.json").haendler_tarife
    )
