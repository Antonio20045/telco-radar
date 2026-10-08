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
from datetime import UTC, datetime, timedelta

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
    WARTET_HOECHSTENS,
    GithubLaeufe,
    aus_umgebung,
)
from telco_radar.collect.geraete.klickseite import Seitenergebnis
from telco_radar.collect.geraete.klickziele import Erkundungsziel, Seitenziel

JETZT = datetime(2026, 10, 3, 5, 0, tzinfo=UTC)
TOKEN = "ghs_TESTTOKEN0815"
API = "https://api.example.test"


class Api:
    """Testdoppel der GitHub-API: Zahl der Läufe je Workflow und Zustand, dazu die
    aufgelisteten Läufe (``workflow_runs``), wo ein Test sie braucht."""

    def __init__(
        self,
        laeufe: dict[tuple[str, str], int],
        status: int = 200,
        listen: dict[tuple[str, str], list[dict]] | None = None,
    ):
        self.laeufe, self.status, self.listen = laeufe, status, listen or {}
        self.fragen: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, kopf: dict[str, str]) -> tuple[int, str]:
        self.fragen.append((url, kopf))
        datei = url.split("/workflows/")[1].split("/")[0]
        zustand = url.split("status=")[1].split("&")[0]
        anzahl = self.laeufe.get((datei, zustand), 0)
        laeufe = self.listen.get((datei, zustand), [])
        return self.status, json.dumps({"total_count": anzahl, "workflow_runs": laeufe})


def _pruefung(api: Api) -> GithubLaeufe:
    return GithubLaeufe("Antonio20045/telco-radar", TOKEN, API, api)


def test_frei_wenn_kein_lauf_ansteht_und_jede_frage_traegt_das_token():
    api = Api({})

    assert _pruefung(api)() is None
    assert [u for u, _ in api.fragen] == [
        f"{API}/repos/Antonio20045/telco-radar/actions/workflows/{d}/runs"
        f"?status={z}&per_page={n}"
        for d in ("geraete.yml", "klick.yml", "radar.yml")
        for z, n in (("queued", 100), ("in_progress", 1))
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


HAENGT = {"id": 37655532485, "status": "queued", "created_at": "2026-10-07T16:57:03Z"}
TAGESLAUF = datetime(2026, 10, 8, 6, 17, 3, tzinfo=UTC)


def _wartend(laeufe: list[dict], gesamt: int | None = None) -> Api:
    schluessel = ("geraete.yml", "queued")
    anzahl = len(laeufe) if gesamt is None else gesamt
    return Api({schluessel: anzahl}, listen={schluessel: laeufe})


def _um(api: Api, jetzt: datetime) -> str | None:
    return GithubLaeufe(
        "Antonio20045/telco-radar", TOKEN, API, api, uhr=lambda: jetzt
    )()


def test_ein_seit_stunden_haengender_lauf_sperrt_nicht_und_steht_im_protokoll(caplog):
    """Gerätelauf #89: geplant, erstellt 07.10.2026 16:57:03 UTC, nie gestartet; der
    erste Klick-Tageslauf fragte am 08.10.2026 um 06:17 UTC und verschob alle
    Anbieter."""
    with caplog.at_level("WARNING"):
        assert _um(_wartend([HAENGT]), TAGESLAUF) is None
    assert (
        "geraete.yml: Lauf 37655532485 wartet seit 2026-10-07T16:57:03Z" in caplog.text
    )


def test_gegenprobe_ein_frisch_wartender_lauf_sperrt_weiter():
    """Derselbe Lauf eine Stunde nach seiner Erstellung: er wartet zu Recht."""
    eine_stunde = datetime(2026, 10, 7, 17, 57, 3, tzinfo=UTC)
    assert _um(_wartend([HAENGT]), eine_stunde) == (
        "Gerätelauf läuft (geraete.yml, queued)"
    )


@pytest.mark.parametrize(
    ("alter", "grund"),
    [
        (timedelta(hours=3, minutes=59), "Gerätelauf läuft (geraete.yml, queued)"),
        (timedelta(hours=4), "Gerätelauf läuft (geraete.yml, queued)"),
        (timedelta(hours=4, seconds=1), None),
    ],
)
def test_die_grenze_ist_wartet_hoechstens(alter, grund):
    erstellt = datetime(2026, 10, 7, 16, 57, 3, tzinfo=UTC)
    assert timedelta(hours=4) == WARTET_HOECHSTENS
    assert _um(_wartend([HAENGT]), erstellt + alter) == grund


@pytest.mark.parametrize(
    ("laeufe", "gesamt"),
    [
        ([HAENGT], 2),
        ([HAENGT, {**HAENGT, "id": 2, "created_at": "2026-10-08T06:00:00Z"}], None),
        ([{**HAENGT, "created_at": "gestern"}], None),
        ([{**HAENGT, "created_at": "2026-10-07T16:57:03"}], None),
        ([{key: v for key, v in HAENGT.items() if key != "created_at"}], None),
    ],
    ids=[
        "nicht-aufgelistet",
        "zweiter-frisch",
        "datum-unlesbar",
        "ohne-zone",
        "ohne-datum",
    ],
)
def test_was_nicht_als_haengend_belegt_ist_sperrt_weiter(laeufe, gesamt):
    assert _um(_wartend(laeufe, gesamt), TAGESLAUF) == (
        "Gerätelauf läuft (geraete.yml, queued)"
    )


def test_ohne_uhr_sperrt_jeder_wartende_lauf():
    api = _wartend([HAENGT])
    assert GithubLaeufe("Antonio20045/telco-radar", TOKEN, API, api)() == (
        "Gerätelauf läuft (geraete.yml, queued)"
    )


def test_aus_umgebung_reicht_die_uhr_durch():
    umgebung = {
        "GITHUB_REPOSITORY": "a/b",
        "GITHUB_TOKEN": TOKEN,
        "GITHUB_API_URL": API,
    }
    pruefung = aus_umgebung(umgebung, uhr=lambda: TAGESLAUF)
    assert isinstance(pruefung, GithubLaeufe)
    assert pruefung.uhr is not None and pruefung.uhr() == TAGESLAUF
    assert aus_umgebung(umgebung).uhr is None


def test_ein_laufender_lauf_sperrt_unabhaengig_vom_alter():
    alt = {**HAENGT, "status": "in_progress"}
    api = Api(
        {("geraete.yml", "in_progress"): 1},
        listen={("geraete.yml", "in_progress"): [alt]},
    )
    assert _um(api, TAGESLAUF) == "Gerätelauf läuft (geraete.yml, in_progress)"


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
