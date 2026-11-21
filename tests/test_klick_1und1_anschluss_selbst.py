"""1&1: jeder Eintrag liest die Tarifdetail-Seiten selbst (Anschlusspreis, 21.11.2026).

Nachtlauf 21.11.2026: alle 308 1&1-Bündel des Tages standen ohne Anschlusspreis und
damit ohne Gesamtkosten (am 19.11.: 39,90 €). Die 308 Sätze kamen aus dem Eintrag
``1und1-2`` (15 Produktseiten gelesen). Den Anschlusspreis nennt nur die
Tarifdetail-Seite je Tarif. Die Tarifauswahl, die ``1und1-2`` liest, zeigt ihn nicht:
die Kachel nennt keine Einmalzahlung, die Preisübersicht braucht einen POST. Die
Produktseite nennt nur „erstatten wir Ihnen den Bereitstellungspreis“ ohne Betrag
(Abruf 21.11.2026). Die Tarifdetail-Seiten las aber nur ``1und1``, und der bekam HTTP
502. Mit PR 184 teilen sich die Einträge den Anschluss eines Tags; fällt der eine aus,
fehlt er trotzdem allen. Erwartet:

- jeder 1&1-Eintrag liest alle Tarifdetail-Seiten selbst;
- eine Datei, die nur Tarifdetail-Seiten als Übersicht trägt, sagt nichts über das
  Geräteangebot (``nicht_im_angebot`` bleibt ``None``, nicht „alle Geräte“);
- mit den echten Dateien der Nacht (``1und1`` mit 502) und den Tarifdetail-Seiten im
  Eintrag ``1und1-2`` trägt jeder Satz 39,90 €.

Gegenprobe: ohne gelesene Tarifdetail-Seite bleibt der Anschlusspreis ``None``
(``test_klick_1und1_anschluss_je_lauf``).
"""

from __future__ import annotations

import json
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import pytest
from bestand_pfad import lese_wurzel
from klickergebnisse import WURZEL

from telco_radar.analyze.klick_erfassung import erfassungsgruende
from telco_radar.analyze.klick_zusammenfuehrung import fuehre_zusammen
from telco_radar.collect.geraete.klickanschluss import (
    TAGESANSCHLUESSE,
    tagesanschluesse,
)
from telco_radar.collect.geraete.klickkarte import lade_klickkarte
from telco_radar.collect.geraete.klicklauf import (
    LAUF_GESTOERT,
    STOERUNG_SERVER,
    Klicklauf,
)
from telco_radar.collect.geraete.klickrohsatz import ausbeute
from telco_radar.collect.geraete.klicktageslauf import fahre
from telco_radar.collect.geraete.klickwiederholung import Wiederholung
from telco_radar.collect.geraete.klickziele import (
    TAGESDATEI,
    Seitenziel,
    lade_ziele,
)
from telco_radar.geraete_config import lade_katalog
from telco_radar.report.geraete_tco_karten import geraet_aus_sku

HEUTE = "2026-11-21"
ORDNER = WURZEL / "tests" / "fixtures" / "klickcrawler"
TARIFDETAIL = "einsundeins_1und1_tarifdetail_20261121.json"
NACHT = "einsundeins_1und1_nacht_20261121.json"
ZWEITER = "einsundeins_1und1-2_nacht_20261121.json"


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(lese_wurzel())


def _lade(name: str) -> dict:
    return json.loads((ORDNER / name).read_text(encoding="utf-8"))


def _tarife(adressen) -> set[str]:
    return {
        parse_qs(urlsplit(a).query)["chosenTariff"][0]
        for a in adressen
        if "chosenTariff=" in a
    }


def test_jeder_1und1_eintrag_liest_alle_tarifdetail_seiten():
    ziele = [
        z
        for z in lade_ziele(lese_wurzel(), TAGESDATEI, hoechste=None)
        if z.name == "1&1" and z.schluessel in ("1und1", "1und1-2")
    ]
    gelesen = {u["adresse"] for u in _lade(TARIFDETAIL)["uebersichten"]}

    assert [z.schluessel for z in ziele] == ["1und1", "1und1-2"]
    assert len(_tarife(gelesen)) == 7
    assert {z.schluessel: _tarife(z.uebersichten) for z in ziele} == {
        "1und1": _tarife(gelesen),
        "1und1-2": _tarife(gelesen),
    }


def test_tarifdetail_seiten_sind_keine_geraeteliste(katalog):
    """Die echte Datei mit nur den sieben Tarifdetail-Seiten (alle gelesen und
    vollständig) nannte bisher jedes Katalog-Gerät „nicht im Angebot“."""
    daten = _lade(TARIFDETAIL)
    assert {(u["status"], u["vollstaendig"]) for u in daten["uebersichten"]} == {
        ("gelesen", True)
    }

    assert ausbeute(daten, katalog).nicht_im_angebot is None


def _zweiter_mit_tarifdetail() -> dict:
    zweiter = _lade(ZWEITER)
    return {**zweiter, "uebersichten": _lade(TARIFDETAIL)["uebersichten"]}


def test_nacht_mit_502_der_zweite_eintrag_bringt_den_anschluss_selbst(katalog):
    nacht = _lade(NACHT)
    assert (nacht["laufstatus"], nacht["datum"]) == ("gestoert", HEUTE)

    zug = fuehre_zusammen(
        [],
        [nacht, _zweiter_mit_tarifdetail()],
        katalog,
        HEUTE,
        lambda s: geraet_aus_sku(s, katalog),
    )
    saetze = [s for s in zug.rohsaetze if s["anbieter"] == "1&1"]

    assert len(saetze) == 28
    assert {s["anschlusspreis"] for s in saetze} == {39.9}


def test_kein_geraet_heisst_nicht_im_angebot(katalog):
    zug = fuehre_zusammen(
        [],
        [_lade(NACHT), _zweiter_mit_tarifdetail()],
        katalog,
        HEUTE,
        lambda s: geraet_aus_sku(s, katalog),
    )
    gruende = erfassungsgruende(zug.bilanz)

    assert not [s for s in gruende.values() if "nicht im Angebot" in s]


class _Uhr:
    def __init__(self) -> None:
        self.jetzt = 0.0

    def __call__(self) -> float:
        return self.jetzt


def _fahre_mit_502_am_detail_endpunkt(schluessel: str) -> dict:
    """Wie am 21.11.: jede Tarifdetail-Seite 502, jede Produktseite erreichbar."""
    ziel = {z.schluessel: z for z in lade_ziele(lese_wurzel(), TAGESDATEI, None)}[
        schluessel
    ]
    seiten = tuple(
        Seitenziel(g, None, f"https://mobile.1und1.de/{g}")
        for g in ("apple-iphone-17", "google-pixel-10a", "samsung-galaxy-s26")
    )
    ziel = replace(ziel, seiten=seiten)
    karte = lade_klickkarte(lese_wurzel() / "config" / "klickkarten" / "1und1.yaml")
    uhr = _Uhr()

    def schlafe(sekunden: float) -> None:
        uhr.jetzt += sekunden

    def crawle(seite, _ende):
        uhr.jetzt += 60
        return Klicklauf("1&1", seite.adresse)

    def lies(adresse, _ende):
        uhr.jetzt += 3
        teil = {
            "adresse": adresse,
            "status": LAUF_GESTOERT,
            "grund": "Abruf gestört (HTTP 502)",
            "stoerung": STOERUNG_SERVER,
        }
        return {**teil, "seiten": [teil], "saetze": [], "vollstaendig": False}

    crawler, leser = Wiederholung(uhr, schlafe).um(crawle, lies)
    return fahre(
        ziel,
        karte,
        "1und1.yaml",
        crawler,
        HEUTE,
        10**6,
        gelesen={},
        uhr=uhr,
        schlafe=schlafe,
        lies_uebersicht=leser,
    )


@pytest.mark.parametrize("schluessel", ["1und1", "1und1-2"])
def test_detail_endpunkt_mit_502_kostet_keine_geraeteseite(schluessel):
    """Prüfer zu PR 199: liest ein Eintrag die Tarifdetail-Seiten zuerst, beenden drei
    502 in Folge (``HOECHSTE_SERVERFEHLER_IN_FOLGE``) den Eintrag vor jeder
    Produktseite. Der Ausfall des Detail-Endpunkts kostet nur den Anschlusspreis."""
    daten = _fahre_mit_502_am_detail_endpunkt(schluessel)

    assert [s["status"] for s in daten["seiten"]] == ["gelesen"] * 3
    tarifdetail = [u for u in daten["uebersichten"] if "chosenTariff=" in u["adresse"]]
    assert len(tarifdetail) == 7
    assert {u["status"] for u in tarifdetail} <= {"gestoert", "nicht_besucht"}


def _anschluss_datei(preise: dict[str, float], datum: str = HEUTE) -> dict:
    """Die echten Tarifdetail-Sätze der Nacht mit den Preisen ``preise`` je Slug."""
    daten = _lade(TARIFDETAIL)
    uebersichten = [
        {
            **u,
            "saetze": [
                {**s, "anschlusspreis": preise[s["tarif_slug"]]} for s in u["saetze"]
            ],
        }
        for u in daten["uebersichten"]
    ]
    return {**daten, "datum": datum, "uebersichten": uebersichten}


def _slugs() -> list[str]:
    return [
        s["tarif_slug"] for u in _lade(TARIFDETAIL)["uebersichten"] for s in u["saetze"]
    ]


def test_verschiedene_preise_je_tarif_landen_beim_richtigen_tarif(katalog):
    """Die Fixture hat für alle sieben Tarife 39,90 €; eine Vertauschung fiele dort
    nicht auf. Hier trägt jeder Tarif seinen eigenen Betrag."""
    preise = {slug: 10.0 * (i + 1) for i, slug in enumerate(_slugs())}
    namen = {
        s["tarif_name"]: preise[s["tarif_slug"]]
        for u in _lade(TARIFDETAIL)["uebersichten"]
        for s in u["saetze"]
    }
    zug = fuehre_zusammen(
        [],
        [_lade(NACHT), {**_lade(ZWEITER), **_teil(_anschluss_datei(preise))}],
        katalog,
        HEUTE,
        lambda s: geraet_aus_sku(s, katalog),
    )
    saetze = [s for s in zug.rohsaetze if s["anbieter"] == "1&1"]

    assert len(saetze) == 28 and len(set(namen.values())) == 7
    assert {(s["tarif_name"], s["anschlusspreis"]) for s in saetze} == set(
        namen.items()
    )


def _teil(daten: dict) -> dict:
    return {"uebersichten": daten["uebersichten"]}


@pytest.mark.parametrize("umgekehrt", [False, True])
def test_zwei_lesungen_eines_tags_widersprechen_sich_benannte_luecke(umgekehrt, caplog):
    """Prüfer zu PR 199: 39,90 € in ``1und1``, 49,90 € in ``1und1-2`` am selben Tag gab
    bisher still den Wert der zuletzt gelesenen Datei."""
    eins = _anschluss_datei(dict.fromkeys(_slugs(), 39.9))
    zwei = {**_anschluss_datei(dict.fromkeys(_slugs(), 39.9)), "anbieter": "1und1-2"}
    zwei["uebersichten"][0]["saetze"][0]["anschlusspreis"] = 49.9
    s_slug = zwei["uebersichten"][0]["saetze"][0]["tarif_slug"]
    s_name = zwei["uebersichten"][0]["saetze"][0]["tarif_name"]
    reihe = [zwei, eins] if umgekehrt else [eins, zwei]

    ergebnis = tagesanschluesse(eins, reihe)

    assert ergebnis[s_slug] is None and ergebnis[s_name] is None
    assert {k: v for k, v in ergebnis.items() if v is not None} == {
        k: 39.9 for k in ergebnis if k not in (s_slug, s_name)
    }
    assert "zwei Lesungen widersprechen sich: 39.90/49.90" in caplog.text


def test_widerspruch_ist_eine_benannte_luecke_der_ausbeute(katalog):
    from telco_radar.collect.geraete.klickrohsatz import LUECKE_ANSCHLUSS_WIDERSPRUCH

    eins = _anschluss_datei(dict.fromkeys(_slugs(), 39.9))
    zwei = {**_lade(ZWEITER), **_teil(_anschluss_datei(dict.fromkeys(_slugs(), 49.9)))}

    zug = fuehre_zusammen(
        [], [eins, zwei], katalog, HEUTE, lambda s: geraet_aus_sku(s, katalog)
    )
    saetze = [s for s in zug.rohsaetze if s["anbieter"] == "1&1"]

    assert len(saetze) == 28 and {s["anschlusspreis"] for s in saetze} == {None}
    assert (
        ausbeute(
            {**zwei, TAGESANSCHLUESSE: tagesanschluesse(zwei, [eins, zwei])}, katalog
        ).luecken[LUECKE_ANSCHLUSS_WIDERSPRUCH]
        == 28
    )


def test_gleiche_lesungen_zweier_eintraege_sind_ein_wert():
    eins = _anschluss_datei(dict.fromkeys(_slugs(), 39.9))
    zwei = {**eins, "anbieter": "1und1-2"}

    assert set(tagesanschluesse(eins, [eins, zwei]).values()) == {39.9}
