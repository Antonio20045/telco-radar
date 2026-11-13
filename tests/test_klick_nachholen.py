"""Klick-Stand nachholen (``analyze.klick_nachholen``) im Gerätelauf.

Muster vom 10.11.2026: der Gerätelauf checkt ``main`` aus, die Klick-Dateien im
Arbeitsbaum sind vom Vortag, 76 Sekunden später legt der Klick-Tageslauf den Stand von
heute ab. Hier mit echtem ``git`` (ein Bare-Repo als origin, ein Klon als Arbeitsbaum,
ein zweiter Klon als Klick-Bot) und dem o2-Mitschnitt vom 29.09.2026.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import test_klick_zusammenfuehrung as vorlage
from klickergebnisse import erfasst, o2_lesung

from telco_radar.analyze.klick_nachholen import (
    ABSTAND_S,
    FERTIG,
    KEINER,
    LAEUFT,
    UNBEKANNT,
    WARTEN_HOECHSTENS_S,
    Nachholen,
    git_im_repo,
    klicklauf_aus_umgebung,
    restzeit,
    veraltet,
)
from telco_radar.collect.geraete.klickergebnis import ORDNER, schreibe
from telco_radar.geraete_pipeline import run_geraete_stage

HEUTE = vorlage.HEUTE
M_PLUS = vorlage.M_PLUS
VORTAG = "2026-09-28"
UMGEBUNG = "TELCO_KLICK_ERGEBNISSE"


def _git(ort: Path, *argumente: str) -> str:
    kennung = [
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t",
        "-c",
        "commit.gpgsign=false",
    ]
    ergebnis = subprocess.run(
        ["git", *kennung, *argumente],
        cwd=ort,
        check=True,
        capture_output=True,
        text=True,
    )
    return ergebnis.stdout


def _klick_datei(datum: str) -> dict:
    return vorlage._o2(erfasst(o2_lesung("256 GB", M_PLUS, 36)), datum=datum)


class Aufbau:
    """Arbeitsbaum mit Klick-Datei vom Vortag; ``bot`` legt später den Stand ab."""

    def __init__(self, tmp: Path, datum: str = VORTAG) -> None:
        self.root = vorlage._repo(tmp)
        self.origin = tmp / "origin.git"
        self.bot = tmp / "bot"
        schreibe(self.root / ORDNER / "o2.json", _klick_datei(datum))
        _git(tmp, "init", "--bare", "-b", "main", str(self.origin))
        _git(self.root, "init", "-b", "main")
        _git(self.root, "remote", "add", "origin", str(self.origin))
        _git(self.root, "add", "config", "data/state/klick")
        _git(self.root, "commit", "-m", "Stand")
        _git(self.root, "push", "origin", "main")
        _git(tmp, "clone", "-b", "main", str(self.origin), str(self.bot))

    def bot_legt_ab(self, datum: str = HEUTE) -> None:
        """Der Klick-Tageslauf: neuer Stand auf origin/main (``klick: Stand …``)."""
        schreibe(self.bot / ORDNER / "o2.json", _klick_datei(datum))
        _git(self.bot, "add", "data/state/klick")
        _git(self.bot, "commit", "-m", f"klick: Stand {datum}")
        _git(self.bot, "pull", "--rebase", "origin", "main")
        _git(self.bot, "push", "origin", "main")


class Uhr:
    """Eine Uhr, die nur ``schlafe`` vorstellt; ``bei`` läuft nach dem n-ten Schlaf."""

    def __init__(self, bei: dict[int, callable] | None = None) -> None:
        self.jetzt = 0.0
        self.schlaefe = 0
        self.bei = bei or {}

    def __call__(self) -> float:
        return self.jetzt

    def schlafe(self, sekunden: float) -> None:
        self.jetzt += sekunden
        self.schlaefe += 1
        if self.schlaefe in self.bei:
            self.bei[self.schlaefe]()


def _nachholen(aufbau: Aufbau, uhr: Uhr, zustand: str = LAEUFT, **felder) -> Nachholen:
    return Nachholen(
        aufbau.root,
        git_im_repo(aufbau.root),
        lambda heute: zustand,
        schlafe=uhr.schlafe,
        uhr=uhr,
        **felder,
    )


def _lauf(aufbau: Aufbau, nachholen: Nachholen | None, heute: str = HEUTE) -> dict:
    return run_geraete_stage(
        aufbau.root,
        {},
        heute,
        jetzt=vorlage._JETZT,
        hole=vorlage._hole(),
        klick_nachholen=nachholen,
    )


def _klick_buendel(root: Path) -> list[dict]:
    store = json.loads((root / "data/state/geraete_tco.json").read_text("utf-8"))
    return [b for b in store["buendel"] if b.get("quelle_art") == "klick"]


@pytest.fixture(autouse=True)
def _ohne_umgebung(monkeypatch):
    monkeypatch.delenv(UMGEBUNG, raising=False)


@pytest.mark.parametrize("nachholen", [False, True], ids=["ohne", "mit"])
def test_muster_1011_klick_stand_kommt_nach_dem_checkout(tmp_path, nachholen):
    """Der Stand von heute liegt erst nach dem Checkout auf origin. Ohne Nachholen
    ersetzt kein Klick-Satz etwas (0 Bündel, wie am 10.11.); mit Nachholen kommt das
    Klick-Bündel von heute in den Bestand. Der Arbeitsbaum bleibt dabei sauber, und der
    ``git pull --rebase`` am Ende von ``geraete.yml`` läuft ohne Konflikt."""
    aufbau = Aufbau(tmp_path)
    aufbau.bot_legt_ab()
    uhr = Uhr()

    bilanz = _lauf(aufbau, _nachholen(aufbau, uhr) if nachholen else None)

    assert bilanz["klick"]["ersetzt"] == (1 if nachholen else 0)
    assert [b["abgerufen_am"] for b in _klick_buendel(aufbau.root)] == (
        [HEUTE] if nachholen else []
    )
    assert _git(aufbau.root, "status", "--porcelain", "--", "data/state/klick") == ""
    assert uhr.schlaefe == 0
    if nachholen:
        assert bilanz["klick"]["nachholen"]["veraltet_vorher"] == ["o2"]
        assert bilanz["klick"]["nachholen"]["veraltet"] == []
    _git(aufbau.root, "add", "data/state/geraete_tco.json")
    _git(aufbau.root, "commit", "-m", "geraeteradar: Stand")
    _git(aufbau.root, "pull", "--rebase", "origin", "main")
    _git(aufbau.root, "push", "origin", "HEAD:main")
    datei = json.loads((aufbau.root / ORDNER / "o2.json").read_text("utf-8"))
    assert datei["datum"] == HEUTE


def test_stand_kommt_waehrend_des_wartens(tmp_path):
    """Der Klick-Lauf läuft noch: nach zwei Wartezeiten liegt sein Stand auf origin."""
    aufbau = Aufbau(tmp_path)
    uhr = Uhr({2: aufbau.bot_legt_ab})

    bilanz = _lauf(aufbau, _nachholen(aufbau, uhr))

    nachholen = bilanz["klick"]["nachholen"]
    assert (nachholen["abrufe"], uhr.schlaefe) == (3, 2)
    assert nachholen["gewartet_s"] == 2 * ABSTAND_S
    assert nachholen["veraltet"] == [] and nachholen["klicklauf"] == LAEUFT
    assert bilanz["klick"]["ersetzt"] == 1


def test_stand_bleibt_alt_dann_gilt_kein_klickpreis_als_heute(tmp_path):
    """Der Klick-Lauf liefert nichts mehr: das Warten endet nach der Frist, Klick-Datei
    und Bestand bleiben beim Vortag. Kein Klick-Bündel trägt das heutige Datum, der
    Befund nennt o2 unter ``veraltet``."""
    aufbau = Aufbau(tmp_path)
    _lauf(aufbau, None, heute=VORTAG)
    assert [b["abgerufen_am"] for b in _klick_buendel(aufbau.root)] == [VORTAG]
    uhr = Uhr()

    bilanz = _lauf(aufbau, _nachholen(aufbau, uhr))

    nachholen = bilanz["klick"]["nachholen"]
    assert nachholen["veraltet"] == ["o2"]
    assert (
        WARTEN_HOECHSTENS_S - ABSTAND_S < nachholen["gewartet_s"] <= WARTEN_HOECHSTENS_S
    )
    assert nachholen["abrufe"] == uhr.schlaefe + 1
    assert bilanz["klick"]["ersetzt"] == 0
    (eintrag,) = bilanz["klick"]["dateien"]
    assert not eintrag["verwendet"] and eintrag["datum"] == VORTAG
    assert [b["abgerufen_am"] for b in _klick_buendel(aufbau.root)] == [VORTAG]
    assert not [b for b in _klick_buendel(aufbau.root) if b["abgerufen_am"] == HEUTE]


@pytest.mark.parametrize("zustand", [KEINER, FERTIG])
def test_ohne_laufenden_klicklauf_bleibt_es_bei_einem_abruf(tmp_path, zustand):
    aufbau = Aufbau(tmp_path)
    uhr = Uhr()

    bilanz = _lauf(aufbau, _nachholen(aufbau, uhr, zustand))

    assert uhr.schlaefe == 0
    assert bilanz["klick"]["nachholen"]["abrufe"] == 1
    assert bilanz["klick"]["nachholen"]["veraltet"] == ["o2"]


def test_restzeit_deckelt_das_warten(tmp_path):
    """Regel 8: ist vom Job nichts übrig, bleibt es bei einem Abruf ohne Schlaf."""
    aufbau = Aufbau(tmp_path)
    uhr = Uhr()
    nachholen = _nachholen(aufbau, uhr)

    with nachholen(HEUTE, restzeit(2400.0)) as ordner:
        assert ordner is not None
    assert (uhr.schlaefe, nachholen.bilanz["abrufe"]) == (0, 1)
    assert restzeit(0.0) < WARTEN_HOECHSTENS_S * 2
    with nachholen(HEUTE, 150.0):
        pass
    assert uhr.schlaefe == 2


def test_origin_nicht_erreichbar_bleibt_beim_arbeitsbaum(tmp_path):
    aufbau = Aufbau(tmp_path)
    _git(aufbau.root, "remote", "set-url", "origin", str(tmp_path / "gibt-es-nicht"))
    uhr = Uhr()

    bilanz = _lauf(aufbau, _nachholen(aufbau, uhr))

    nachholen = bilanz["klick"]["nachholen"]
    assert "gescheitert" in nachholen["grund"] and nachholen["abrufe"] == 0
    assert nachholen["veraltet"] == ["o2"] and uhr.schlaefe == 0
    assert bilanz["klick"]["ersetzt"] == 0


def test_aktueller_stand_aendert_nichts(tmp_path):
    """Im Normalfall (Klick-Dateien von heute) ruft das Nachholen weder git noch
    GitHub, und der Bestand ist Byte für Byte der ohne Nachholen."""
    ohne = Aufbau(tmp_path / "ohne", HEUTE)
    mit = Aufbau(tmp_path / "mit", HEUTE)

    def nie(_argumente):
        raise AssertionError("kein git bei aktuellem Stand")

    nachholen = Nachholen(mit.root, nie, lambda heute: pytest.fail("keine Auskunft"))
    bilanz_ohne = _lauf(ohne, None)
    bilanz_mit = _lauf(mit, nachholen)

    assert "nachholen" not in bilanz_mit["klick"]
    assert bilanz_ohne["klick"] == bilanz_mit["klick"]
    store = Path("data/state/geraete_tco.json")
    assert (ohne.root / store).read_bytes() == (mit.root / store).read_bytes()


def test_genannter_ordner_wird_nicht_nachgeholt(tmp_path, monkeypatch):
    aufbau = Aufbau(tmp_path)
    aufbau.bot_legt_ab()
    nachholen = _nachholen(aufbau, Uhr())

    bilanz = run_geraete_stage(
        aufbau.root,
        {},
        HEUTE,
        jetzt=vorlage._JETZT,
        hole=vorlage._hole(),
        klick=aufbau.root / ORDNER,
        klick_nachholen=nachholen,
    )
    assert "nachholen" not in bilanz["klick"] and bilanz["klick"]["ersetzt"] == 0
    monkeypatch.setenv(UMGEBUNG, str(aufbau.root / ORDNER))
    bilanz = _lauf(aufbau, nachholen)
    assert "nachholen" not in bilanz["klick"] and bilanz["klick"]["ersetzt"] == 0


def test_veraltet_kennt_fehlende_alte_und_zukuenftige_dateien(tmp_path):
    schreibe(tmp_path / "o2.json", _klick_datei(VORTAG))
    schreibe(tmp_path / "x.json", {**_klick_datei("2026-10-01"), "name": "Zukunft"})
    assert veraltet(tmp_path, HEUTE, ["o2", "Telekom"]) == ["o2", "Telekom"]
    assert veraltet(tmp_path, HEUTE, None) == ["o2"]
    assert veraltet(tmp_path, "2026-09-28", ["o2"]) == []
    schreibe(tmp_path / "o2-2.json", _klick_datei(HEUTE))
    assert veraltet(tmp_path, HEUTE, ["o2"]) == ["o2"]


def _antwort(laeufe: list[dict], status: int = 200):
    return lambda url, kopf: (status, json.dumps({"workflow_runs": laeufe}))


@pytest.mark.parametrize(
    ("laeufe", "status", "erwartet"),
    [
        (
            [{"status": "in_progress", "created_at": "2026-09-29T07:02:00Z"}],
            200,
            LAEUFT,
        ),
        ([{"status": "queued", "created_at": "2026-09-29T07:02:00Z"}], 200, LAEUFT),
        ([{"status": "completed", "created_at": "2026-09-29T07:02:00Z"}], 200, FERTIG),
        ([{"status": "completed", "created_at": "2026-09-28T07:02:00Z"}], 200, KEINER),
        ([], 200, KEINER),
        ([], 403, UNBEKANNT),
    ],
)
def test_klicklauf_des_tages_aus_der_github_auskunft(laeufe, status, erwartet):
    umgebung = {"GITHUB_REPOSITORY": "Antonio20045/telco-radar"}
    frage = klicklauf_aus_umgebung(umgebung, _antwort(laeufe, status))
    assert frage(HEUTE) == erwartet


def test_klicklauf_ohne_repo_oder_bei_netzfehler_ist_unbekannt():
    def kaputt(url, kopf):
        raise OSError("kein Netz")

    assert klicklauf_aus_umgebung({}, _antwort([]))(HEUTE) == UNBEKANNT
    umgebung = {"GITHUB_REPOSITORY": "a/b"}
    assert klicklauf_aus_umgebung(umgebung, kaputt)(HEUTE) == UNBEKANNT
