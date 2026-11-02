"""Manifest der Belegbilder: aus der Liste der Release-Anhänge, ohne Netz.

Feste Daten, nie das heutige Datum (CLAUDE.md Regel 7).
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from telco_radar.beleg_manifest import (
    DOWNLOAD_BASIS,
    MANIFEST_NAME,
    BelegManifestFehler,
    baue_manifest,
    bild_url,
    lies,
    schreibe,
)
from telco_radar.beleg_regeln import dateiname

HEUTE = date(2026, 11, 10)


def name(geraet: str, anbieter: str, tag: date) -> str:
    return dateiname(geraet, anbieter, tag)


def test_manifest_aus_gemockter_releaseliste():
    a = name("iphone-17-256", "vodafone", date(2026, 11, 10))
    b = name("iphone-17-256", "o2", date(2026, 11, 9))
    anhaenge = {"belege-2026-11-10": [a], "belege-2026-11-09": [b]}
    manifest = baue_manifest(anhaenge, HEUTE)
    assert manifest["fremd"] == 0
    assert manifest["belege"] == [
        {
            "geraet_id": "iphone-17-256",
            "anbieter_id": "vodafone",
            "datum": "2026-11-10",
            "gross": False,
            "url": f"{DOWNLOAD_BASIS}/belege-2026-11-10/{a}",
        },
        {
            "geraet_id": "iphone-17-256",
            "anbieter_id": "o2",
            "datum": "2026-11-09",
            "gross": False,
            "url": f"{DOWNLOAD_BASIS}/belege-2026-11-09/{b}",
        },
    ]


def test_bild_url_aus_tag_und_dateiname():
    assert bild_url("belege-2026-11-10", "x.webp") == (
        "https://github.com/Antonio20045/telco-radar/releases/download/"
        "belege-2026-11-10/x.webp"
    )


def test_tag_und_monat_fuehren_zu_einem_eintrag_mit_gross():
    datei = name("g", "o2", date(2026, 11, 10))
    anhaenge = {"belege-gross-2026-11": [datei], "belege-2026-11-10": [datei]}
    belege = baue_manifest(anhaenge, HEUTE)["belege"]
    assert len(belege) == 1
    assert belege[0]["gross"] is True
    assert "/belege-gross-2026-11/" in belege[0]["url"]


def test_nur_im_monatsrelease_ist_ebenfalls_gross():
    datei = name("g", "o2", date(2026, 9, 1))
    belege = baue_manifest({"belege-gross-2026-09": [datei]}, HEUTE)["belege"]
    assert [b["gross"] for b in belege] == [True]


def test_abgelaufenes_faellt_heraus_grosses_bleibt():
    alt = name("g", "o2", date(2026, 11, 2))
    knapp = name("g", "vodafone", date(2026, 11, 3))
    anhaenge = {
        "belege-2026-11-02": [alt],
        "belege-2026-11-03": [knapp],
        "belege-gross-2026-11": [alt],
    }
    belege = baue_manifest(anhaenge, HEUTE)["belege"]
    assert {(b["anbieter_id"], b["datum"]) for b in belege} == {
        ("vodafone", "2026-11-03"),
        ("o2", "2026-11-02"),
    }
    gross = {b["anbieter_id"]: b["gross"] for b in belege}
    assert gross == {"vodafone": False, "o2": True}


def test_gross_nach_einundneunzig_tagen_weg():
    datei = name("g", "o2", date(2026, 8, 10))
    assert baue_manifest({"belege-gross-2026-08": [datei]}, HEUTE)["belege"] == []


def test_fremde_dateien_zaehlen_und_erscheinen_nicht():
    gut = name("g", "o2", HEUTE)
    anhaenge = {"belege-2026-11-10": [gut, "foto.webp", "notiz.txt", "A__b__x.webp"]}
    manifest = baue_manifest(anhaenge, HEUTE)
    assert manifest["fremd"] == 3
    assert len(manifest["belege"]) == 1


def test_leere_releaseliste_gibt_leeres_manifest():
    manifest = baue_manifest({}, HEUTE)
    assert manifest["belege"] == []
    assert manifest["erstellt"] == "2026-11-10"


def test_neueste_zuerst_dann_nach_schluessel():
    anhaenge = {
        "belege-2026-11-09": [name("b", "o2", date(2026, 11, 9))],
        "belege-2026-11-10": [
            name("b", "o2", HEUTE),
            name("a", "vodafone", HEUTE),
        ],
    }
    belege = baue_manifest(anhaenge, HEUTE)["belege"]
    assert [(b["datum"], b["geraet_id"]) for b in belege] == [
        ("2026-11-10", "a"),
        ("2026-11-10", "b"),
        ("2026-11-09", "b"),
    ]


def test_schreiben_und_lesen_rundreise(tmp_path):
    datei = name("g", "o2", HEUTE)
    manifest = baue_manifest({"belege-2026-11-10": [datei]}, HEUTE)
    pfad = tmp_path / "data" / "state" / MANIFEST_NAME
    schreibe(pfad, manifest)
    belege = lies(pfad)
    assert [(b.geraet_id, b.anbieter_id, b.datum, b.gross) for b in belege] == [
        ("g", "o2", HEUTE, False)
    ]
    assert belege[0].url == bild_url("belege-2026-11-10", datei)


def test_fehlende_datei_ist_leer_nicht_fehler(tmp_path):
    assert lies(tmp_path / MANIFEST_NAME) == []


@pytest.mark.parametrize(
    "inhalt",
    ["{kaputt", json.dumps({"format": 99, "belege": []}), json.dumps({"format": 1})],
)
def test_kaputtes_manifest_ist_nie_leer(tmp_path, inhalt):
    pfad = tmp_path / MANIFEST_NAME
    pfad.write_text(inhalt, encoding="utf-8")
    with pytest.raises(BelegManifestFehler):
        lies(pfad)


def test_sichtbar_nutzt_dieselbe_regel_wie_das_loeschen(tmp_path):
    datei = name("g", "o2", date(2026, 11, 3))
    manifest = baue_manifest({"belege-2026-11-03": [datei]}, HEUTE)
    pfad = tmp_path / MANIFEST_NAME
    schreibe(pfad, manifest)
    beleg = lies(pfad)[0]
    assert beleg.sichtbar(date(2026, 11, 10))
    assert not beleg.sichtbar(date(2026, 11, 11))
