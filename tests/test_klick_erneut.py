"""Eigener Abruf eines Klick-Anbieters (``analyze.klick_erneut``) beim Nachholen.

Muster vom 21.11.2026: der Klick-Tageslauf endete bei 1&1 gestört (HTTP 502 auf der
Übersicht, alle Seiten ``nicht_besucht``), die Datei trägt das Datum von heute, und 14
Pflichtmodelle blieben ohne Bündel. Das Nachholen holte nur den Zweig und rief nichts
ab. Hier ohne Netz und ohne Browser: ``git`` ist ein Tar-Stand von ``origin``, der Abruf
schreibt die Dateien, die das Skript schreiben würde (Aufbau wie ``klickergebnisse``,
Lesung aus der gespeicherten 1&1-Produktseite). Die 14 Modelle sind Schlüssel aus der
echten Datei ``data/state/klick/1und1.json`` vom 21.11.2026.
"""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest
import yaml
from klickergebnisse import einsundeins_lesung, erfasst, ergebnisdatei, lauf

from telco_radar.analyze.klick_erneut import (
    MINDEST_S,
    PARALLEL_WORKFLOWS,
    PAUSE_S,
    SCHARD_PAUSE_S,
    VERSUCHE,
    Erneut,
    laufpruefung_aus_umgebung,
    schluessel_des_anbieters,
)
from telco_radar.analyze.klick_nachholen import (
    KEINER,
    LAEUFT,
    Nachholen,
    veraltet,
)
from telco_radar.collect.geraete.klickergebnis import (
    ORDNER,
    nicht_besucht,
    schreibe,
)
from telco_radar.collect.geraete.klicklauf import LAUF_GESTOERT
from telco_radar.collect.geraete.klickziele import Seitenziel
from telco_radar.klick_vertrag import ganz_gelesen

HEUTE = "2026-11-21"
VORTAG = "2026-11-20"
MODELLE = (
    "apple-iphone-17",
    "apple-iphone-17-pro",
    "apple-iphone-17-pro-max",
    "apple-iphone-17e",
    "apple-iphone-18-pro-max",
    "samsung-galaxy-s26-plus",
    "samsung-galaxy-s26-ultra",
    "samsung-galaxy-z-fold8",
    "samsung-galaxy-a17",
    "samsung-galaxy-a57",
    "google-pixel-11-pro",
    "google-pixel-11-pro-xl",
    "xiaomi-17",
    "xiaomi-17t",
)
SEITEN = [Seitenziel(m, 256, f"https://mobile.1und1.de/{m}", None, m) for m in MODELLE]
UEBERSICHT = (
    "https://mobile.1und1.de/details-all-net-flat-preisliste"
    "?chosenTariff=tariff-anf-s-mvl&chosenNet=1u1&lightbox=true&bk=false"
)
NACH_STOERUNG = "nach Störung keine weitere Anfrage (CLAUDE.md Regel 4)"
ABRUF = "Abruf gestört (HTTP {})"


def _gestoert(schluessel: str, status: int = 502, datum: str = HEUTE) -> dict:
    """Die Datei des 21.11.2026: Übersicht gestört, jede Seite ``nicht_besucht``."""
    grund = ABRUF.format(status)
    return {
        **ergebnisdatei("1&1", schluessel, [], datum, vertragsform="ein_vertrag"),
        "laufstatus": LAUF_GESTOERT,
        "grund": f"{UEBERSICHT}: {grund}",
        "seiten": [nicht_besucht(s, f"{NACH_STOERUNG}: {grund}") for s in SEITEN],
        "uebersichten": [
            {
                "adresse": UEBERSICHT,
                "http_status": status,
                "grund": grund,
                "seiten": [],
            },
        ],
    }


def _gelesen(schluessel: str, ziele: list[Seitenziel]) -> dict:
    lesung = einsundeins_lesung()
    seiten = [(z, lauf(z, [erfasst(lesung)])) for z in ziele]
    return ergebnisdatei("1&1", schluessel, seiten, HEUTE, vertragsform="ein_vertrag")


def _o2(datum: str = HEUTE) -> dict:
    ziel = Seitenziel("apple-iphone-17-pro", 256, "https://o2.example/x", None, "x")
    seiten = [(ziel, lauf(ziel, [erfasst(einsundeins_lesung())]))]
    return ergebnisdatei("o2", "o2", seiten, datum)


class Origin:
    """Der Stand von ``origin``: ``git`` liefert ihn als Tar, ``fetch`` tut nichts."""

    def __init__(self, ordner: Path) -> None:
        self.ordner = ordner
        self.aufrufe: list[list[str]] = []

    def __call__(self, argumente: list[str]) -> bytes:
        self.aufrufe.append(argumente)
        if argumente[0] != "archive":
            return b""
        puffer = io.BytesIO()
        with tarfile.open(fileobj=puffer, mode="w") as archiv:
            for datei in sorted(self.ordner.glob("*.json")):
                archiv.add(datei, arcname=f"{ORDNER.as_posix()}/{datei.name}")
        return puffer.getvalue()


class Uhr:
    def __init__(self) -> None:
        self.jetzt = 0.0
        self.pausen: list[float] = []

    def __call__(self) -> float:
        return self.jetzt

    def schlafe(self, sekunden: float) -> None:
        self.jetzt += sekunden
        self.pausen.append(sekunden)


class Aufbau:
    """Arbeitsbaum mit Konfiguration, ``origin`` mit 1&1 gestört und o2 von heute."""

    def __init__(self, tmp: Path, **dateien: dict) -> None:
        self.root = tmp / "repo"
        self.uhr = Uhr()
        karten = self.root / "config" / "klickkarten"
        karten.mkdir(parents=True)
        for karte in ("1und1", "o2"):
            (karten / f"{karte}.yaml").write_text("{}\n", encoding="utf-8")
        eintraege = [
            {"schluessel": "1und1", "name": "1&1"},
            {"schluessel": "1und1-2", "name": "1&1", "karte": "1und1"},
            {"schluessel": "o2", "name": "o2"},
        ]
        (self.root / "config" / "klick_tageslauf.yaml").write_text(
            yaml.safe_dump({"anbieter": eintraege}), encoding="utf-8"
        )
        self.origin_ordner = tmp / "origin"
        stand = {
            "1und1": _gestoert("1und1"),
            "1und1-2": _gestoert("1und1-2"),
            "o2": _o2(),
            **dateien,
        }
        for name, daten in stand.items():
            schreibe(self.origin_ordner / f"{name}.json", daten)
            schreibe(self.root / ORDNER / f"{name}.json", daten)
        self.git = Origin(self.origin_ordner)
        self.abrufe: list[str] = []

    def nachholen(self, erneut: Erneut | None, zustand: str = KEINER) -> Nachholen:
        return Nachholen(
            self.root,
            self.git,
            lambda heute: zustand,
            schlafe=self.uhr.schlafe,
            uhr=self.uhr,
            erneut=erneut,
        )

    def erneut(self, abruf, laeufe=lambda: None, **felder) -> Erneut:
        def mit_protokoll(schluessel: str, ausgabe: Path, frist_s: float):
            self.abrufe.append(schluessel)
            return abruf(schluessel, ausgabe, len(self.abrufe))

        return Erneut(
            self.root,
            mit_protokoll,
            laeufe,
            veraltet,
            schlafe=self.uhr.schlafe,
            uhr=self.uhr,
            **felder,
        )


def _schreibt(daten_je_nr):
    """Ein Abruf, der je laufender Nummer die Datei ``daten_je_nr(schluessel, nr)``
    schreibt, wie ``scripts/klick_tageslauf.py`` es täte."""

    def abruf(schluessel: str, ausgabe: Path, nr: int) -> None:
        schreibe(ausgabe / f"{schluessel}.json", daten_je_nr(schluessel, nr))

    return abruf


def _zweiter_gelingt(schluessel: str, nr: int) -> dict:
    """Erster Abruf scheitert mit 502, ab dem zweiten liest 1&1 alle 14 Modelle."""
    return _gestoert(schluessel) if nr == 1 else _gelesen(schluessel, SEITEN)


def test_gestoerter_anbieter_wird_selbst_abgerufen_14_modelle(tmp_path):
    """Der Zweig trägt 1&1 gestört (0 Seiten, Datum heute). Der erste eigene Abruf
    scheitert wieder mit 502, nach der Pause liest der zweite alle 14 Modelle: die Datei
    im Stand ersetzt die gestörte, der Anbieter gilt nicht mehr als veraltet."""
    aufbau = Aufbau(tmp_path)
    assert veraltet(aufbau.origin_ordner, HEUTE, ["1&1", "o2"]) == ["1&1"]
    nachholen = aufbau.nachholen(aufbau.erneut(_schreibt(_zweiter_gelingt)))

    with nachholen(HEUTE, 3000.0) as ordner:
        assert ordner is not None
        eins = json.loads((ordner / "1und1.json").read_text(encoding="utf-8"))
        zwei = json.loads((ordner / "1und1-2.json").read_text(encoding="utf-8"))
        assert [s["geraet"] for s in ganz_gelesen(eins["seiten"])] == list(MODELLE)
        assert len(MODELLE) == 14 and zwei["laufstatus"] == "gelesen"
        assert json.loads((ordner / "o2.json").read_text(encoding="utf-8"))["datum"]
        assert veraltet(ordner, HEUTE, ["1&1", "o2"]) == []

    assert nachholen.bilanz["erneut"] == {
        "1&1": {"versuche": 2, "gelesen": True, "grund": None},
    }
    assert nachholen.bilanz["veraltet_vorher"] == ["1&1"]
    assert nachholen.bilanz["veraltet"] == [] and nachholen.bilanz["grund"] is None
    assert aufbau.abrufe == ["1und1", "1und1", "1und1-2"]
    assert aufbau.uhr.pausen == [PAUSE_S, SCHARD_PAUSE_S]


def test_ohne_erneut_bleibt_der_anbieter_gestoert(tmp_path):
    """Gegenprobe zum alten Stand: ohne ``erneut`` ruft das Nachholen nur den Zweig,
    1&1 bleibt veraltet, kein Abruf, kein Schlüssel ``erneut`` in der Bilanz."""
    aufbau = Aufbau(tmp_path)
    nachholen = aufbau.nachholen(None)

    with nachholen(HEUTE, 3000.0) as ordner:
        assert ordner is not None
        assert veraltet(ordner, HEUTE, ["1&1", "o2"]) == ["1&1"]
    assert "erneut" not in nachholen.bilanz and aufbau.abrufe == []
    assert nachholen.bilanz["veraltet"] == ["1&1"]


def test_wiederholt_nur_dreimal_mit_pause_dann_benannter_grund(tmp_path):
    aufbau = Aufbau(tmp_path)
    nachholen = aufbau.nachholen(
        aufbau.erneut(_schreibt(lambda schluessel, nr: _gestoert(schluessel)))
    )

    with nachholen(HEUTE, 3000.0) as ordner:
        assert ordner is not None
        assert veraltet(ordner, HEUTE, ["1&1"]) == ["1&1"]

    eintrag = nachholen.bilanz["erneut"]["1&1"]
    assert eintrag["versuche"] == VERSUCHE == 3 and not eintrag["gelesen"]
    assert "HTTP 502" in eintrag["grund"]
    assert aufbau.abrufe == ["1und1"] * 3
    assert aufbau.uhr.pausen == [PAUSE_S, PAUSE_S]
    assert nachholen.bilanz["veraltet"] == ["1&1"]


def test_schutzantwort_bleibt_bei_einer_anfrage(tmp_path):
    """403 ist Bot-Schutz, kein Serverfehler: genau ein Abruf, keine Pause, nichts
    ersetzt (CLAUDE.md Regel 4)."""
    aufbau = Aufbau(tmp_path)
    nachholen = aufbau.nachholen(
        aufbau.erneut(_schreibt(lambda schluessel, nr: _gestoert(schluessel, 403)))
    )

    with nachholen(HEUTE, 3000.0) as ordner:
        assert ordner is not None
        eins = json.loads((ordner / "1und1.json").read_text(encoding="utf-8"))
        assert "HTTP 502" in eins["grund"]

    eintrag = nachholen.bilanz["erneut"]["1&1"]
    assert eintrag["versuche"] == 1 and "Schutzantwort" in eintrag["grund"]
    assert aufbau.abrufe == ["1und1"] and aufbau.uhr.pausen == []


def test_laeuft_ein_paralleler_lauf_kein_abruf(tmp_path):
    aufbau = Aufbau(tmp_path)
    grund = "Radarlauf läuft (radar.yml, in_progress)"
    nachholen = aufbau.nachholen(
        aufbau.erneut(_schreibt(_zweiter_gelingt), laeufe=lambda: grund)
    )

    with nachholen(HEUTE, 3000.0):
        pass

    assert aufbau.abrufe == []
    assert nachholen.bilanz["erneut"]["1&1"] == {
        "versuche": 0,
        "gelesen": False,
        "grund": grund,
    }


def test_laeuft_der_klick_tageslauf_ruft_das_nachholen_nichts_ab(tmp_path):
    """Der Klick-Tageslauf liest denselben Host: solange er läuft, wartet das
    Nachholen auf seinen Stand und ruft selbst nichts ab."""
    aufbau = Aufbau(tmp_path)
    nachholen = aufbau.nachholen(aufbau.erneut(_schreibt(_zweiter_gelingt)), LAEUFT)

    with nachholen(HEUTE, 150.0):
        pass

    assert aufbau.abrufe == [] and "erneut" not in nachholen.bilanz


def test_zu_wenig_restzeit_kein_abruf(tmp_path):
    aufbau = Aufbau(tmp_path)
    nachholen = aufbau.nachholen(aufbau.erneut(_schreibt(_zweiter_gelingt)))

    with nachholen(HEUTE, MINDEST_S - 1):
        pass

    assert aufbau.abrufe == []
    assert "Restzeit" in nachholen.bilanz["erneut"]["1&1"]["grund"]


def test_nur_der_betroffene_anbieter_wird_abgerufen(tmp_path):
    """o2 ist veraltet (Datei vom Vortag), steht aber nicht in ``ANBIETER``: kein
    Abruf. 1&1 ist heute gelesen und bleibt unberührt."""
    aufbau = Aufbau(
        tmp_path,
        **{
            "1und1": _gelesen("1und1", SEITEN),
            "1und1-2": _gelesen("1und1-2", SEITEN[:1]),
            "o2": _o2(VORTAG),
        },
    )
    nachholen = aufbau.nachholen(aufbau.erneut(_schreibt(_zweiter_gelingt)))

    with nachholen(HEUTE, 3000.0):
        pass

    assert nachholen.bilanz["veraltet_vorher"] == ["o2"]
    assert aufbau.abrufe == [] and "erneut" not in nachholen.bilanz


def test_schluessel_des_anbieters_nennt_beide_dateien_von_1und1(tmp_path):
    aufbau = Aufbau(tmp_path)
    assert schluessel_des_anbieters(aufbau.root, "1&1") == ["1und1", "1und1-2"]
    assert schluessel_des_anbieters(aufbau.root, "Telekom") == []
    assert schluessel_des_anbieters(tmp_path, "1&1") == []


def _auskunft(gesehen: list[tuple[str, dict]], gesamt: int = 0):
    def holer(url: str, kopf: dict[str, str]) -> tuple[int, str]:
        gesehen.append((url, kopf))
        return 200, json.dumps({"total_count": gesamt, "workflow_runs": []})

    return holer


@pytest.mark.parametrize("token", ["", "geheim"])
def test_laufpruefung_fragt_fremde_workflows_nie_den_eigenen(token):
    """Der Gerätelauf läuft selbst und darf sich nicht blockieren; ohne Token (die
    Datei ``geraete.yml`` reicht keines herein) geht keine Kopfzeile ``Authorization``
    mit."""
    gesehen: list[tuple[str, dict]] = []
    umgebung = {"GITHUB_REPOSITORY": "o/r", "GITHUB_TOKEN": token}

    pruefung = laufpruefung_aus_umgebung(umgebung, _auskunft(gesehen))

    assert pruefung() is None
    urls = " ".join(u for u, _ in gesehen)
    assert "klick.yml" in urls and "radar.yml" in urls and "geraete.yml" not in urls
    assert set(PARALLEL_WORKFLOWS) == {"klick.yml", "klick-erkundung.yml", "radar.yml"}
    assert all(("Authorization" in k) == bool(token) for _, k in gesehen)


def test_laufpruefung_meldet_laufenden_lauf_und_fehlendes_repo():
    gesehen: list[tuple[str, dict]] = []
    laufend = laufpruefung_aus_umgebung(
        {"GITHUB_REPOSITORY": "o/r"}, _auskunft(gesehen, gesamt=1)
    )
    assert "läuft" in (laufend() or "")
    ohne_repo = laufpruefung_aus_umgebung({}, _auskunft(gesehen))
    assert "GITHUB_REPOSITORY fehlt" in (ohne_repo() or "")
