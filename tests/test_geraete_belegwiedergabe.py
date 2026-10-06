"""Belege des Klick-Crawlers als Regressionstest (Datenkonzept Geräteradar, Abs. 10).

Quelle ist die BEISPIEL-Produktseite unter ``tests/fixtures/klickcrawler/`` auf einem
lokalen Server (127.0.0.1). Der erste Lauf liest und belegt jede Kombination, das
Archiv legt Screenshot und HAR in einen Ordner und schreibt das Manifest. Dann liefert
der Server falsche Preise, und ein zweiter Lauf spielt die gespeicherten HAR-Belege
mit ``route_from_har`` ab: er liest dieselben Werte, ohne den Preis-Endpunkt zu fragen.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from klickserver import JETZT, Antwort, html, klickserver, laufe

from telco_radar.collect.geraete.belegablage import LokaleAblage
from telco_radar.collect.geraete.belegarchiv import ARCHIVIERT, archiviere
from telco_radar.collect.geraete.belegmanifest import (
    ablageschluessel,
    lies_manifest,
    pruefe_manifest,
)
from telco_radar.collect.geraete.klickbeleg import WEBP, werte_aus_json
from telco_radar.collect.geraete.klickecho import lies_antwort
from telco_radar.collect.geraete.klickhar import har_eintrag
from telco_radar.collect.geraete.klickkarte import lade_klickkarte
from telco_radar.collect.geraete.klicklauf import BELEGT, OHNE_WERT
from telco_radar.collect.geraete.klicktext import lies_zusammenfassung

FIXTURES = Path(__file__).parent / "fixtures" / "klickcrawler"
PRODUKTPFAD = "/handy/beispielhandy-x"
ROBOTS = "User-agent: *\nDisallow: /privat/json/\n"
FRIST_MS = 5000
FALSCH = 100.0


def _antworte(zustand: dict):
    preise = json.loads((FIXTURES / "beispiel_preise.json").read_text("utf-8"))
    seite = (FIXTURES / "beispiel_produktseite.html").read_text("utf-8")

    def antworte(pfad: str) -> Antwort:
        teile = urlsplit(pfad)
        if teile.path == PRODUKTPFAD:
            return html(seite)
        if teile.path != "/api/preis":
            return Antwort(404)
        frage = parse_qs(teile.query)
        teil = ("speicher", "tarif", "laufzeit")
        schluessel = "|".join(frage.get(t, [""])[0] for t in teil)
        antwort = json.loads(json.dumps(preise[schluessel]))
        if zustand["falsch"]:
            antwort["preis"]["rate"] += FALSCH
            antwort["preis"]["anzahlung"] += FALSCH
        return Antwort(200, "application/json", json.dumps(antwort))

    return antworte


def _je_variante(lauf) -> dict:
    return {
        (e.variante.speicher, e.variante.tarif, e.variante.laufzeit): e
        for e in lauf.ergebnisse
    }


@pytest.fixture(scope="module")
def laeufe(chromium, tmp_path_factory):
    """Erster Lauf, Archiv, Wiedergabe und Lauf ohne Wiedergabe, einmal je Modul."""
    ordner = tmp_path_factory.mktemp("belege")
    karte = lade_klickkarte(FIXTURES / "beispiel_karte.yaml")
    zustand = {"falsch": False}
    ablage = LokaleAblage(ordner / "ablage")
    with klickserver(_antworte(zustand)) as server:
        adresse = server.adresse(PRODUKTPFAD)
        erster = laufe(chromium, adresse, karte, ROBOTS, frist_ms=FRIST_MS)
        bericht = archiviere(
            erster, ablage, ordner / "manifest", JETZT, stempler=lambda d: ()
        )
        manifest = bericht.manifeste[0]
        belege = lies_manifest(manifest).belege
        har = tuple(ablage.ordner / ablageschluessel(b, b.mitschnitt) for b in belege)
        zustand["falsch"] = True
        vorher = len(server.mit("/api/preis"))
        wieder = laufe(
            chromium, adresse, karte, ROBOTS, frist_ms=FRIST_MS, wiedergabe=har
        )
        aus_wiedergabe = server.mit("/api/preis")[vorher:]
        ohne = laufe(chromium, adresse, karte, ROBOTS, frist_ms=FRIST_MS)
    return {
        "karte": karte,
        "erster": erster,
        "bericht": bericht,
        "ablage": ablage,
        "manifest": manifest,
        "belege": belege,
        "wieder": wieder,
        "aus_wiedergabe": aus_wiedergabe,
        "ohne": ohne,
    }


def test_jede_gelesene_kombination_traegt_ihren_beleg(laeufe):
    erster = _je_variante(laeufe["erster"])

    gelesen = [e for e in erster.values() if e.status in ("erfasst", "befund")]
    assert len(gelesen) == 6
    assert all(e.beleg_status == BELEGT for e in gelesen)
    assert all(e.beleg is not None for e in gelesen)
    assert all(e.beleg.bild[:4] == b"RIFF" for e in gelesen)
    assert all(e.beleg.beleg.bild.typ == WEBP for e in gelesen)
    assert [e.gueltig for e in gelesen].count(True) == 5
    assert not erster[("256", "M", 36)].gueltig
    for variante in (("128", "S", 36), ("256", "S", 36)):
        assert erster[variante].beleg is None
        assert erster[variante].beleg_status == OHNE_WERT


def test_archiv_ist_vollstaendig_und_jeder_hash_passt(laeufe):
    bericht = laeufe["bericht"]

    assert bericht.zustand == ARCHIVIERT
    assert bericht.belege == 6
    assert pruefe_manifest(laeufe["manifest"], laeufe["ablage"].lies) == []
    ids = [b.beleg_id for b in laeufe["belege"]]
    assert len(set(ids)) == 6
    gross = next(b for b in laeufe["belege"] if b.variante["speicher"] == "256")
    assert gross.zeitpunkt == "2026-10-03T05:00:00Z"
    assert gross.http_status == 200
    assert gross.adresse.endswith(PRODUKTPFAD)


def test_jeder_wert_steht_woertlich_an_seinen_fundstellen(laeufe):
    karte, ablage = laeufe["karte"], laeufe["ablage"]

    for beleg in laeufe["belege"]:
        werte = werte_aus_json(beleg.werte)
        roh = ablage.lies(ablageschluessel(beleg, beleg.mitschnitt))
        url, status, koerper = har_eintrag(roh)
        antwort = lies_antwort(json.loads(koerper), karte.antwort, url).werte
        assert (url, status) == (beleg.antwort_url, 200)
        assert beleg.fundstellen
        for stelle in beleg.fundstellen:
            wert = getattr(werte, stelle.feld)
            assert wert is not None
            assert getattr(lies_zusammenfassung(stelle.ausschnitt), stelle.feld) == wert
            assert getattr(antwort, stelle.feld) == wert


def test_wiedergabe_liest_dieselben_werte_ohne_den_preis_endpunkt(laeufe):
    erster = _je_variante(laeufe["erster"])
    wieder = _je_variante(laeufe["wieder"])

    assert laeufe["wieder"].status == "gelesen"
    assert laeufe["aus_wiedergabe"] == []
    assert {v: e.status for v, e in wieder.items()} == {
        v: e.status for v, e in erster.items()
    }
    assert {v: e.werte for v, e in wieder.items()} == {
        v: e.werte for v, e in erster.items()
    }
    assert wieder[("256", "S", 24)].werte.rate == 25.0


def test_ohne_wiedergabe_liest_der_lauf_die_falschen_preise_gegenprobe(laeufe):
    erster = _je_variante(laeufe["erster"])
    ohne = _je_variante(laeufe["ohne"])

    assert ohne[("256", "S", 24)].werte.rate == 25.0 + FALSCH
    assert ohne[("256", "S", 24)].werte != erster[("256", "S", 24)].werte
