"""Ziele und Bausteine der Klick-Erkundung ohne Browser: Konfiguration, Adressen, Arten.

Die ausgelieferte ``config/klick_erkundung.yaml`` muss sich gegen Quellen und Katalog
auflösen; jede kaputte Zeile wirft mit ihrer Stelle, statt still weniger zu erkunden.
Geprüft wird in einem Wegwerfordner mit Kopien der echten Quellen und des Katalogs.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from telco_radar.collect.geraete.klickablage import (
    GESCHWAERZT,
    RESERVE_INDEX,
    VERMERK_KOERPER,
    Ablage,
)
from telco_radar.collect.geraete.klickerkundung import gesamtstatus
from telco_radar.collect.geraete.klickinventar import art_der_gruppe
from telco_radar.collect.geraete.klickspur import ohne_geheimnisse
from telco_radar.collect.geraete.klickziele import (
    ErkundungszielFehler,
    lade_ziele,
    waehle,
)

WURZEL = Path(__file__).resolve().parents[1]
ANBIETER = ["o2", "vodafone", "1und1", "telekom", "congstar", "freenet"]


@pytest.fixture
def wurzel(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    for name in (
        "geraete_quellen.yaml",
        "geraete_katalog.yaml",
        "klick_erkundung.yaml",
    ):
        shutil.copy(WURZEL / "config" / name, tmp_path / "config" / name)
    return tmp_path


def _aendere(wurzel: Path, aendern) -> None:
    pfad = wurzel / "config" / "klick_erkundung.yaml"
    daten = yaml.safe_load(pfad.read_text(encoding="utf-8"))
    aendern(daten["anbieter"])
    pfad.write_text(yaml.safe_dump(daten, allow_unicode=True), encoding="utf-8")


def test_ausgelieferte_ziele_loesen_sich_gegen_quellen_und_katalog(wurzel):
    ziele = lade_ziele(wurzel)

    assert [z.schluessel for z in ziele] == ANBIETER
    assert all(z.seiten[0].geraet == "apple-iphone-17-pro" for z in ziele)
    assert all(z.seiten[0].speicher_gb == 256 for z in ziele)
    assert all(len(z.seiten) == 2 for z in ziele)
    assert all(s.adresse.startswith("https://") for z in ziele for s in z.seiten)
    kennungen = {z.schluessel: z.kennung for z in ziele}
    assert kennungen["o2"] is None
    assert kennungen["telekom"].startswith("TelcoRadar/1.0")
    assert {z.schluessel: z.rate_limit_sekunden for z in ziele}["telekom"] == 10.0


@pytest.mark.parametrize(
    ("aendern", "meldung"),
    [
        (lambda a: a[0]["seiten"][0].update(geraet="kein-geraet"), "fehlt im Katalog"),
        (lambda a: a[0]["seiten"][0].update(speicher_gb=3), "3 GB nicht beim Gerät"),
        (
            lambda a: a[0]["seiten"][0].update(url="https://www.fremd.de/x"),
            "Host fremd.de ist nicht o2online.de",
        ),
        (
            lambda a: a[0]["seiten"][0].update(url="http://www.o2online.de/x"),
            "Adresse ohne https",
        ),
        (lambda a: a[0].update(name="Unbekannt"), "fehlt in geraete_quellen.yaml"),
        (lambda a: a[0]["seiten"].append(a[0]["seiten"][0]), "höchstens 2"),
        (lambda a: a[1].update(schluessel="o2"), "Schlüssel doppelt"),
        (lambda a: a[0].update(seiten=[]), "keine Seiten"),
    ],
)
def test_kaputte_zeile_wirft_mit_stelle(wurzel, aendern, meldung):
    _aendere(wurzel, aendern)

    with pytest.raises(ErkundungszielFehler, match=meldung):
        lade_ziele(wurzel)


def test_auswahl_nennt_unbekannte_und_haelt_reihenfolge(wurzel):
    ziele = lade_ziele(wurzel)

    assert [z.schluessel for z in waehle(ziele, "alle")] == ANBIETER
    assert [z.schluessel for z in waehle(ziele, " telekom, o2,telekom")] == [
        "telekom",
        "o2",
    ]
    with pytest.raises(ErkundungszielFehler, match="unbekannter Anbieter xyz"):
        waehle(ziele, "o2,xyz")


@pytest.mark.parametrize(
    ("url", "erwartet"),
    [
        (
            "https://a.de/p?token=geheim&speicher=256",
            "https://a.de/p?token=ENTFERNT&speicher=256",
        ),
        ("https://nutzer:pw@a.de:8443/p?x=1#teil", "https://a.de:8443/p?x=1"),
        ("https://a.de/p?apiKey=1&sessionId=2&sig=3", None),
        ("data:text/plain,abc", "data:"),
    ],
)
def test_adresse_verliert_geheimnisse(url, erwartet):
    sauber = ohne_geheimnisse(url)

    if erwartet is None:
        assert (
            sauber == "https://a.de/p?apiKey=ENTFERNT&sessionId=ENTFERNT&sig=ENTFERNT"
        )
    else:
        assert sauber == erwartet


@pytest.mark.parametrize(
    ("texte", "name", "art"),
    [
        (["128 GB", "256 GB", "512 GB"], None, "speicher"),
        (["24 Monate", "36 Monate"], None, "laufzeit"),
        (["Mobil M", "Mobil L"], None, "tarif"),
        (["Schwarz", "Silber"], None, "farbe"),
        (["Hilfe", "Kontakt"], None, "unbekannt"),
        (["A", "B"], "Speicher wählen", "speicher"),
    ],
)
def test_art_der_gruppe(texte, name, art):
    assert art_der_gruppe([(t, t) for t in texte], name)[0] == art


def test_langer_kacheltext_ist_kein_speicher_aber_tarif():
    kacheln = [("", "Mobil M 256 GB 24 Monate 29,99 €"), ("", "Mobil L 39,99 €")]

    assert art_der_gruppe(kacheln, None)[0] == "tarif"


def test_gesamtstatus_nennt_die_erste_stoerung():
    gelesen = {"nummer": 1, "status": "gelesen", "grund": None}
    gesperrt = {"nummer": 2, "status": "gesperrt", "grund": "per robots.txt"}
    offen = {"nummer": 2, "status": "nicht_besucht", "grund": "Zeitgrenze"}

    assert gesamtstatus([gelesen, gelesen]) == ("gelesen", None)
    assert gesamtstatus([gesperrt, gesperrt]) == ("gesperrt", "per robots.txt")
    assert gesamtstatus([gelesen, offen]) == ("gestoert", "Seite 2: Zeitgrenze")


def test_ablage_schwaerzt_cookies_und_haelt_die_grenze(tmp_path):
    ablage = Ablage(tmp_path / "a", RESERVE_INDEX + 1000)
    ablage.merke_cookies(["KURZ", "LANGERWERT/123"])

    assert ablage.schreibe_json("x.json", {"t": "LANGERWERT/123 LANGERWERT%2F123"})
    assert ablage.schreibe("y.bin", b"0" * 2000) is None
    eintraege = [{"koerper": "z" * 900}, {"koerper": "kurz"}]
    ablage.passe_mitschnitt(eintraege, 200)
    ablage.schreibe_index({"status": "gelesen"})

    text = (tmp_path / "a" / "x.json").read_text(encoding="utf-8")
    assert text.count(GESCHWAERZT) == 2 and "LANGERWERT" not in text
    assert "KURZ" not in ablage.geheim
    assert eintraege == [
        {"koerper": None, "grund": VERMERK_KOERPER},
        {"koerper": "kurz"},
    ]
    assert ablage.vermerke[0].startswith("y.bin nicht gespeichert")
    belegt = sum(d.stat().st_size for d in (tmp_path / "a").iterdir())
    assert belegt == ablage.belegt <= RESERVE_INDEX + 1000
