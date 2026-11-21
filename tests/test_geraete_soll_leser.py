"""Soll-Zählung, Stufe 1: die eigenen Leser der Anbieterlisten (Abnahmekriterium 1).

Jede Fixture ist eine am 21.11.2026 einmal abgerufene, unveränderte Antwort
(``tests/fixtures/geraete_soll/_herkunft.json``). Die Zahlen sind von Hand an den
Listen nachgezählt: congstar 64 Adressen, davon 39 Smartphones (Uhren, Kopfhörer,
Tablets, Kinderuhren fallen weg); 1&1 41 Kacheln; Vodafone 48 Geräte, 39 mit
``hardwareType`` Smartphone; o2 90 Katalogeinträge.

Unabhängigkeit vom Sammler: das Paket lädt kein Modul aus ``collect.geraete`` (Adapter,
Parser, Klick) und keins aus ``analyze``; aus ``collect`` nur den HTTP-Weg (geprüft in
einem frischen Interpreter, ohne Quelltext zu lesen).
"""

from __future__ import annotations

import gzip
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from telco_radar.geraete_model import Geraet, Katalog
from telco_radar.geraete_soll import (
    QUELLEN,
    SATURN_NETZE,
    Fund,
    leser,
    ordne_zu,
    zaehle,
    zaehle_alle,
)
from telco_radar.geraete_soll.leser import LeserFehler

FIXTURES = Path(__file__).parent / "fixtures" / "geraete_soll"
JETZT = "2026-11-21T03:00:00+00:00"


def _text(name: str) -> str:
    return gzip.decompress((FIXTURES / name).read_bytes()).decode("utf-8")


def _katalog() -> Katalog:
    return Katalog(
        geraete=[
            Geraet("Apple", "iPhone 17"),
            Geraet("Apple", "iPhone 17 Pro"),
            Geraet("Google", "Pixel 11"),
            Geraet("Samsung", "Galaxy S26"),
            Geraet("Samsung", "Galaxy S26 Plus", aliase=["Galaxy S26+"]),
        ]
    )


def test_congstar_sitemap_zaehlt_nur_smartphones():
    funde = leser.congstar_sitemap(_text("congstar_devices_20261121.xml.gz"))
    adressen = {f.url for f in funde}
    assert len(funde) == 39
    assert "https://www.congstar.de/geraete/apple/apple-iphone-17/" in adressen
    assert not any("watch" in a or "airpods" in a or "buds" in a for a in adressen)
    assert not any("ipad" in a or "anio" in a or "xplora" in a for a in adressen)


def test_congstar_gegenprobe_eine_adresse_weniger():
    text = _text("congstar_devices_20261121.xml.gz")
    weniger = text.replace(
        "<loc>https://www.congstar.de/geraete/apple/apple-iphone-17/</loc>", ""
    )
    assert len(leser.congstar_sitemap(weniger)) == 38


def test_telekom_sitemap_ein_fund_je_produkt_ohne_uhren_und_tablets():
    funde = leser.telekom_sitemap(_text("telekom_sitemap_20261121.xml.gz"))
    adressen = {f.url for f in funde}
    assert "https://www.telekom.de/shop/geraet/apple/apple-iphone-17" in adressen
    assert not any("/apple-iphone-17/" in a for a in adressen)
    assert not any("watch" in a or "ipad" in a or "-tv" in a for a in adressen)
    assert len(funde) == 49
    s26plus = next(f for f in funde if f.url.endswith("samsung-galaxy-s26plus"))
    assert s26plus.titel == "samsung galaxy s26 plus"


def test_tarifwelt_sitemap_fuehrt_aktionsseiten_auf_ein_modell():
    funde = leser.tarifwelt_sitemap(_text("tarifwelt_sitemap_20261121.xml.gz"))
    modelle = ordne_zu(funde, _katalog())
    seiten = [f.url.rsplit("/", 1)[1] for f in funde if "/apple/iphone-17" in f.url]
    iphone = [s for s in seiten if "pro" not in s and s != "iphone-17e"]
    assert iphone == [
        "iphone-17",
        "iphone-17-aktion",
        "iphone-17-apple-adapter",
        "iphone-17-online-bonus",
    ]
    assert "apple-iphone-17" in modelle
    assert not any("scooter" in f.url or "watch" in f.url for f in funde)


def test_einsundeins_kacheln():
    funde = leser.einsundeins_kacheln(_text("einsundeins_smartphones_20261121.html.gz"))
    assert len(funde) == 41
    titel = {f.titel: f.url for f in funde}
    assert titel["iPhone 17e"] == "https://mobile.1und1.de/iphone-17e"
    assert (
        titel["Samsung Galaxy S26+"]
        == "https://mobile.1und1.de/samsung-galaxy-s26-plus"
    )


def test_vodafone_liste_nur_smartphones():
    funde = leser.vodafone_liste(_text("vodafone_hardware_20261121.json.gz"))
    assert len(funde) == 39
    namen = {f.titel for f in funde}
    assert "iPhone 18 Pro" in namen
    assert not any("iPad" in n or "GigaCube" in n or "Watch" in n for n in namen)


def test_vodafone_liste_mit_falscher_geraetezahl_ist_ein_fehler():
    daten = json.loads(_text("vodafone_hardware_20261121.json.gz"))
    daten["data"]["devices"] = daten["data"]["devices"][:-1]
    with pytest.raises(LeserFehler):
        leser.vodafone_liste(json.dumps(daten))


def test_o2_katalog_pakete_mit_zubehoer():
    funde = leser.o2_katalog(_text("o2_katalog_20261121.json.gz"))
    assert len(funde) == 90
    modelle = ordne_zu(funde, _katalog())
    assert modelle["google-pixel-11"].nur_paket
    assert not modelle["samsung-galaxy-s26"].nur_paket
    assert not modelle["apple-iphone-17"].nur_paket


def test_o2_katalog_mit_folgeseite_ist_nicht_zaehlbar():
    daten = json.loads(_text("o2_katalog_20261121.json.gz"))
    daten["loadNextRestLink"] = {"uri": "https://www.o2online.de/e-shop/rest/naechste"}
    with pytest.raises(LeserFehler):
        leser.o2_katalog(json.dumps(daten))


@pytest.mark.parametrize(
    "lies",
    [
        leser.congstar_sitemap,
        leser.telekom_sitemap,
        leser.tarifwelt_sitemap,
        leser.einsundeins_kacheln,
        leser.vodafone_liste,
        leser.o2_katalog,
    ],
)
def test_leere_oder_fremde_antwort_ist_ein_fehler_kein_leeres_soll(lies):
    with pytest.raises(LeserFehler):
        lies("<html><body>Bitte warten</body></html>")


def test_ohne_katalogtreffer_ist_der_schluessel_die_normalisierte_adresse():
    funde = [Fund("HMD Fusion X1", "https://www.vodafone.de/privat/handys/hmd.html")]
    modell = ordne_zu(funde, _katalog())["https://vodafone.de/privat/handys/hmd.html"]
    assert not modell.im_katalog
    assert modell.name == "HMD Fusion X1"


def _quelle(name: str):
    return next(q for q in QUELLEN if name in q.zeilen)


class _Antwort(tuple):
    schutz = False


def _hole(status: int, text: str, schutz: bool = False):
    def hole(url, kopf=None, **_):
        antwort = _Antwort((status, text))
        antwort.schutz = schutz
        return antwort

    return hole


def test_zaehle_traegt_art_quelle_und_zeit():
    soll = zaehle(
        _quelle("congstar"),
        _hole(200, _text("congstar_devices_20261121.xml.gz")),
        {},
        JETZT,
        _katalog(),
    )
    daten = soll.als_dict()
    assert daten["art"] == "sitemap"
    assert daten["quelle"] == "https://www.congstar.de/sitemap/devices.xml"
    assert daten["gezaehlt_um"] == JETZT
    assert daten["gleiche_quelle_wie_sammler"] is True
    assert daten["grund"] is None
    assert daten["funde"] == 39
    assert {m["schluessel"] for m in daten["modelle"]} >= {"apple-iphone-17"}


@pytest.mark.parametrize(
    ("status", "schutz", "teil"),
    [
        (403, True, "Schutzantwort"),
        (502, False, "HTTP 502"),
        (200, False, "nicht lesbar"),
    ],
)
def test_scheitern_ist_kein_soll_null(status, schutz, teil):
    soll = zaehle(
        _quelle("Telekom"), _hole(status, "kaputt", schutz), {}, JETZT, _katalog()
    )
    assert soll.modelle is None
    assert soll.als_dict()["modelle"] is None
    assert teil in soll.grund


def test_ohne_restzeit_wird_nichts_abgerufen_und_der_grund_steht_da():
    abrufe = []

    def hole(url, *a, **k):
        abrufe.append(url)
        return _Antwort((200, ""))

    soll = zaehle_alle(None, hole, lambda: _Uhr(), _katalog(), lambda: 10.0, 45.0)
    assert abrufe == []
    assert set(soll) == {"Telekom", "Vodafone", "o2", "1&1", "congstar", *SATURN_NETZE}
    assert all(s.modelle is None and "Zeitbudget" in s.grund for s in soll.values())


class _Uhr:
    def isoformat(self, timespec="seconds"):
        return JETZT


def test_saturn_netze_teilen_eine_sitemap():
    quelle = _quelle(SATURN_NETZE[0])
    assert quelle.zeilen == SATURN_NETZE
    assert quelle.url == "https://tarife.mediamarkt.de/sitemap.xml"


def test_das_soll_paket_laedt_keinen_parser_des_sammlers():
    """Import-Prüfung in einem frischen Interpreter: wer ``telco_radar.geraete_soll``
    lädt, lädt kein Modul aus ``collect.geraete`` (Adapter, Parser, Klick). Der Abruf
    geht über ``geraete_abruf`` (robots.txt, Kennung), das die Schleuse erst beim
    Abruf lädt."""
    befehl = [
        sys.executable,
        "-c",
        "import sys, telco_radar.geraete_soll, telco_radar.geraete_soll.leser;"
        "print('\\n'.join(sorted(m for m in sys.modules if 'telco' in m)))",
    ]
    umgebung = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")}
    lauf = subprocess.run(
        befehl,
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).parent,
        env=umgebung,
    )
    geladen = set(lauf.stdout.split())
    assert "telco_radar.geraete_soll.leser" in geladen
    assert "telco_radar.collect.http" in geladen
    assert not [m for m in geladen if m.startswith("telco_radar.collect.geraete")]
    assert not [m for m in geladen if m.startswith("telco_radar.analyze")]
