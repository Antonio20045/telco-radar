"""Nicht gelesen ist nicht „nicht lieferbar“: fehlt der Filter der Uebersicht oder
eine Angabe darin, markiert der Tarifwelt-Lauf nichts (Prueferbefund zu #123).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import telco_radar
from telco_radar import geraete_tarifwelt, tarifwelt_bestand
from telco_radar.analyze.tco_store import TcoDB
from telco_radar.geraete_model import device_id, sku_id
from telco_radar.report import geraete_notbremse, geraete_sortiment
from telco_radar.tarif_bezug import Tarifbestand
from telco_radar.tco_model import Buendel

REPO = Path(telco_radar.__file__).resolve().parents[2]
FIXTURE = (
    REPO
    / "tests/fixtures/geraete"
    / "tarifwelt_mm_productdetail_galaxys26_standard_20261108.json"
)
GESTERN = "2026-11-12"
HEUTE = "2026-11-13"
TELEKOM = "Saturn/MediaMarkt · Telekom-Netz"
S26 = "samsung-galaxy-s26"
LEITER = (("xs", 15.0), ("s", 30.0), ("m", 60.0), ("l", 120.0), ("xl", None))


@dataclass
class _Quelle:
    methode: str
    aktiv: bool
    rate_limit_sekunden: float = 0.0


@dataclass
class _Quellen:
    anbieter: list


def _tarifbestand() -> Tarifbestand:
    return Tarifbestand(
        [
            {
                "tarif_id": f"vodafone:mobil-{k}",
                "anbieter": "Vodafone",
                "name": f"Vodafone Mobil {k.upper()} mit Smartphone",
                "datenvolumen_gb": gb if gb is not None else float("inf"),
                "grundgebuehr": 20.0 + i * 10,
            }
            for i, (k, gb) in enumerate(LEITER)
        ]
    )


def _buendel(hersteller, name, slug, gb, abgerufen_am) -> Buendel:
    return Buendel(
        sku_id=sku_id(device_id(hersteller, name), gb, None),
        anbieter=TELEKOM,
        tarif_name="Allnet Flat 50GB",
        tarif_id=f"{tarifwelt_bestand.PRAEFIX}allnet50",
        tarif_id_guete="niedrig",
        tarif_monatlich=44.99,
        geraet_zuzahlung=129.0,
        geraet_monatsrate=0.0,
        laufzeit_monate=24,
        anschlusspreis=0.0,
        quelle_url=f"https://tarife.mediamarkt.de/smartphones/samsung/{slug}/?speicher={gb}",
        abgerufen_am=abgerufen_am,
        herleitung="tarifwelt_productdetail",
        zustand="neu",
    )


def _bestand(tmp_path, b: Buendel, tag: str) -> TcoDB:
    pfad = tmp_path / "state" / "geraete_tco.json"
    tco = TcoDB(pfad)
    tco.upsert_buendel([b], tag)
    assert tco.save(tag)
    return TcoDB(pfad)


def _hole(uebersichten: dict[str, str]):
    def hole(url, **kw):
        if url.endswith("/robots.txt"):
            return (404, "")
        rest = url.split("/v1/productdetail/", 1)[1]
        if "/tariff?" in rest:
            return (200, "[]")
        if "?" in rest:
            return (404, "")
        return (200, uebersichten[rest])

    return hole


def _stufe(monkeypatch, tco, hole, modelle):
    monkeypatch.setattr(
        geraete_tarifwelt, "pflicht_modelle", lambda: frozenset(modelle)
    )
    monkeypatch.setattr(geraete_tarifwelt.time, "sleep", lambda s: None)
    return geraete_tarifwelt.stufe(
        _Quellen([_Quelle(tarifwelt_bestand.METHODE, True)]),
        _tarifbestand(),
        hole,
        lambda: datetime(2026, 11, 13, 2, 17, tzinfo=UTC),
        HEUTE,
        tco.path.parent,
        tco,
    )


def _zaehlt_auf_der_seite(tco: TcoDB, tmp_path) -> bool:
    (gelesen,) = geraete_sortiment.lies(tco.buendel(), tmp_path / "state", HEUTE)
    return geraete_notbremse.zaehlt(geraete_notbremse.felder_aus_satz(gelesen, HEUTE))


def test_fehlender_variantfilter_ist_nicht_gelesen_nicht_nicht_lieferbar(
    tmp_path, monkeypatch
):
    """Echte Uebersicht (Fixture 08.11.), nur das Feld `variantFilter` fehlt
    (Schemaaenderung, nichts ueber Lieferbarkeit gelesen). Die Seite darf dann
    nicht behaupten, die Stufe sei „nicht lieferbar“ (Auftrag: Nicht gelesen ist
    nicht „nicht lieferbar“)."""
    alt = _buendel("Samsung", "Galaxy S26", "galaxy-s26", 256, GESTERN)
    tco = _bestand(tmp_path, alt, GESTERN)
    daten = json.loads(FIXTURE.read_text(encoding="utf-8"))
    daten["hardware"].pop("variantFilter")
    _stufe(monkeypatch, tco, _hole({"galaxy-s26": json.dumps(daten)}), {S26})

    satz = tco.nach_id(alt.id)
    (gelesen,) = geraete_sortiment.lies(tco.buendel(), tmp_path / "state", HEUTE)
    flags = geraete_notbremse.felder_aus_satz(gelesen, HEUTE)
    assert not flags.get("nicht_lieferbar"), (
        "Lieferbarkeit nicht gelesen (variantFilter fehlt), Seite nennt trotzdem "
        f"'nicht lieferbar': nicht_lieferbar_am={satz.get('nicht_lieferbar_am')!r}, "
        f"Zustand={geraete_notbremse.zustand(flags)!r}"
    )


def test_unlesbarer_variantfilter_eintrag_ist_nicht_nicht_lieferbar(
    tmp_path, monkeypatch
):
    """Echte Uebersicht; die variantFilter-Eintraege der Stufe 256 haben kein `hwi`
    (unlesbar, `available` war True). Auch das ist „nicht gelesen“."""
    alt = _buendel("Samsung", "Galaxy S26", "galaxy-s26", 256, GESTERN)
    tco = _bestand(tmp_path, alt, GESTERN)
    daten = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for v in daten["hardware"]["variantFilter"]:
        if v["storage"] == 256:
            v.pop("hwi")
    _stufe(monkeypatch, tco, _hole({"galaxy-s26": json.dumps(daten)}), {S26})

    satz = tco.nach_id(alt.id)
    assert "nicht_lieferbar_am" not in satz, (
        "unlesbarer variantFilter-Eintrag (available=True, ohne hwi) als "
        f"'nicht lieferbar' markiert: {satz.get('nicht_lieferbar_am')!r}"
    )
