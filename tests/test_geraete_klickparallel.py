"""Klick-Erkundung ohne Browser: Parallellauf-Prüfung, Frist vor robots.txt, Ablage.

``GithubLaeufe`` fragt mit einem Testdoppel statt der GitHub-API: ein anstehender oder
laufender Gerätelauf oder Radarlauf verschiebt den Anbieter, eine nicht lesbare API
ebenso. Steht die Prüfung schon vor der ersten Seite auf „belegt“ oder ist die Frist
um, geht keine Anfrage hinaus, auch nicht an robots.txt; der Index nennt dann keinen
Abstand aus robots.txt. ``lege_ab`` schreibt eine Seite allein aus dem
``Seitenergebnis``.
"""

from __future__ import annotations

import gzip
import json
import time
from datetime import UTC, datetime

import httpx
import pytest

from telco_radar.collect.geraete.klickablage import Ablage
from telco_radar.collect.geraete.klickerkundung import (
    VERSCHOBEN,
    erkunde_anbieter,
    lege_ab,
)
from telco_radar.collect.geraete.klickinventar import Inventar
from telco_radar.collect.geraete.klickparallel import (
    GRUND_API,
    GithubLaeufe,
    aus_umgebung,
)
from telco_radar.collect.geraete.klickseite import Seitenergebnis
from telco_radar.collect.geraete.klickziele import Erkundungsziel, Seitenziel

JETZT = datetime(2026, 10, 3, 5, 0, tzinfo=UTC)
TOKEN = "ghs_TESTTOKEN0815"
API = "https://api.example.test"


class Api:
    """Testdoppel der GitHub-API: Zahl der Läufe je Workflow und Zustand."""

    def __init__(self, laeufe: dict[tuple[str, str], int], status: int = 200):
        self.laeufe, self.status = laeufe, status
        self.fragen: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, kopf: dict[str, str]) -> tuple[int, str]:
        self.fragen.append((url, kopf))
        datei = url.split("/workflows/")[1].split("/")[0]
        zustand = url.split("status=")[1].split("&")[0]
        anzahl = self.laeufe.get((datei, zustand), 0)
        return self.status, json.dumps({"total_count": anzahl, "workflow_runs": []})


def _pruefung(api: Api) -> GithubLaeufe:
    return GithubLaeufe("Antonio20045/telco-radar", TOKEN, API, api)


def test_frei_wenn_kein_lauf_ansteht_und_jede_frage_traegt_das_token():
    api = Api({})

    assert _pruefung(api)() is None
    assert [u for u, _ in api.fragen] == [
        f"{API}/repos/Antonio20045/telco-radar/actions/workflows/{d}/runs"
        f"?status={z}&per_page=1"
        for d in ("geraete.yml", "klick.yml", "radar.yml")
        for z in ("queued", "in_progress")
    ]
    assert {k["Authorization"] for _, k in api.fragen} == {f"Bearer {TOKEN}"}


@pytest.mark.parametrize(
    ("laeufe", "grund"),
    [
        (
            {("geraete.yml", "in_progress"): 1},
            "Gerätelauf läuft (geraete.yml, in_progress)",
        ),
        ({("geraete.yml", "queued"): 2}, "Gerätelauf läuft (geraete.yml, queued)"),
        ({("radar.yml", "in_progress"): 1}, "Radarlauf läuft (radar.yml, in_progress)"),
        (
            {("klick.yml", "in_progress"): 1},
            "Klick-Tageslauf läuft (klick.yml, in_progress)",
        ),
    ],
)
def test_ein_anstehender_oder_laufender_lauf_ist_der_grund(laeufe, grund):
    assert _pruefung(Api(laeufe))() == grund


def test_unlesbare_api_ist_ebenfalls_ein_grund():
    def kaputt(url: str, kopf: dict[str, str]) -> tuple[int, str]:
        raise httpx.ConnectError("keine Verbindung")

    def ohne_zahl(url: str, kopf: dict[str, str]) -> tuple[int, str]:
        return 200, "{}"

    gruende = [
        _pruefung(Api({}, status=401))(),
        GithubLaeufe("a/b", TOKEN, API, kaputt)(),
        GithubLaeufe("a/b", TOKEN, API, ohne_zahl)(),
        aus_umgebung({"GITHUB_REPOSITORY": "a/b"})(),
        aus_umgebung({})(),
    ]

    assert gruende == [
        f"{GRUND_API} (geraete.yml: HTTP 401)",
        f"{GRUND_API} (geraete.yml: ConnectError)",
        f"{GRUND_API} (geraete.yml: Antwort ohne total_count)",
        f"{GRUND_API} (GITHUB_TOKEN fehlt)",
        f"{GRUND_API} (GITHUB_REPOSITORY, GITHUB_TOKEN fehlt)",
    ]
    assert TOKEN not in repr(GithubLaeufe("a/b", TOKEN))


def _ziel() -> Erkundungsziel:
    seiten = tuple(
        Seitenziel("beispielhandy-x", 256, f"https://www.example.de/handy/{p}")
        for p in ("x", "y")
    )
    return Erkundungsziel("beispiel", "Beispielanbieter", seiten, None, 2.0)


def test_belegter_lauf_verschiebt_den_anbieter_ohne_jede_anfrage(tmp_path):
    abgerufen: list[str] = []

    def hole(url: str) -> tuple[int, str]:
        abgerufen.append(url)
        return 200, "User-agent: *\nDisallow:\n"

    laeufe = _pruefung(Api({("geraete.yml", "in_progress"): 1}))
    index = erkunde_anbieter(
        None,
        _ziel(),
        lambda: JETZT,
        hole,
        tmp_path,
        time.monotonic() + 600,
        laeufe=laeufe,
    )

    assert abgerufen == []
    assert [s["status"] for s in index["seiten"]] == [VERSCHOBEN] * 2
    assert (index["status"], index["grund"]) == (
        VERSCHOBEN,
        "Seite 1: Gerätelauf läuft (geraete.yml, in_progress)",
    )
    assert index["parallelpruefung"] == "vor jeder Seite"


def test_nach_der_frist_geht_auch_robots_txt_nicht_hinaus(tmp_path):
    abgerufen: list[str] = []

    def hole(url: str) -> tuple[int, str]:
        abgerufen.append(url)
        return 200, "User-agent: *\nCrawl-delay: 5\n"

    index = erkunde_anbieter(
        None, _ziel(), lambda: JETZT, hole, tmp_path, time.monotonic() - 1
    )

    assert abgerufen == []
    assert [s["status"] for s in index["seiten"]] == ["nicht_besucht"] * 2
    assert index["robots_gelesen"] is False
    assert (index["abstand_sekunden"], index["besuchszeit"]) == (None, None)
    assert index["parallelpruefung"] == "aus"


def test_ablage_einer_seite_kommt_allein_aus_dem_seitenergebnis(tmp_path):
    inventar = Inventar(
        "https://www.example.de/handy/x",
        [{"text": "256 GB", "href": None}],
        [],
        1,
        [{"pfad": "#rate", "text": "35,00 €"}],
        1,
    )
    ergebnis = Seitenergebnis(
        inventar=inventar,
        http_status=200,
        anfragen=[{"nummer": 1, "url": "https://www.example.de/api/p"}],
        mitschnitt=[{"url": "https://www.example.de/api/p", "koerper": "{}"}],
        verworfen=[{"url": "https://www.example.de/privat", "grund": "robots"}] * 3,
        cookies={"KEKSWERT987654"},
        html="<p>KEKSWERT987654</p>",
    )
    ablage = Ablage(tmp_path / "a", 1_000_000)

    eintrag = lege_ab(
        ablage, 1, Seitenziel("x", 256, inventar.adresse), ergebnis, 500_000
    )

    assert eintrag["http_status"] == 200
    assert eintrag["zaehlung"]["anfragen"] == 1
    assert eintrag["zaehlung"]["verworfen"] == 3
    assert eintrag["zaehlung"]["preis_kandidaten"] == 1
    assert set(eintrag["dateien"]) == {
        "bedienelemente",
        "preise",
        "klicks",
        "mitschnitt",
        "html",
    }
    seite = gzip.decompress((tmp_path / "a" / "seite-1.html.gz").read_bytes())
    assert seite == b"<p>[Cookie entfernt]</p>"
