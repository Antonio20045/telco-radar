"""`fetch` umgeht keinen Bot-Schutz (CLAUDE.md Regel 4, Auftrag fetch-ehrlich-0511).

Bis zum 05.11.2026 wechselte `fetch` nach 403/406 auf eine andere Kennung
(Chrome mit Client-Hints oder umgekehrt) und wiederholte 429 mit Backoff. Jetzt:
Schutzantwort heisst genau eine Anfrage, dieselben Kopfzeilen, kein Wechsel.
"""

from __future__ import annotations

import httpx
import pytest

from telco_radar.collect import http

_URL = "https://www.example.de/feed"
_BOT = {"user_agent": http.BOT_UA}
_CHROME = {"user_agent": http.BROWSER_UA}


@pytest.fixture
def pausen() -> list[float]:
    return []


@pytest.fixture
def naht(monkeypatch, pausen):
    """Mock-Transport mit festen Antworten; schreibt Anfragen und Pausen mit."""
    gesehen: list[httpx.Request] = []

    def setze(*antworten: httpx.Response) -> list[httpx.Request]:
        folge = list(antworten)

        def antworte(anfrage: httpx.Request) -> httpx.Response:
            gesehen.append(anfrage)
            return folge.pop(0) if len(folge) > 1 else folge[0]

        monkeypatch.setattr(http, "TRANSPORT", httpx.MockTransport(antworte))
        monkeypatch.setattr(http, "_BACKOFF_WAITS", (0.0, 0.0))
        monkeypatch.setattr(http.time, "sleep", pausen.append)
        monkeypatch.setattr(http, "_gate", http.HostGate(max_parallel=1_000_000))
        return gesehen

    return setze


@pytest.mark.parametrize("status", [403, 406])
@pytest.mark.parametrize("cfg", [_BOT, _CHROME, {}], ids=["ehrlich", "chrome", "leer"])
def test_schutzantwort_kostet_genau_eine_anfrage(naht, status, cfg, pausen):
    gesehen = naht(httpx.Response(status, text="gesperrt"))
    with pytest.raises(httpx.HTTPStatusError) as fehler:
        http.fetch(_URL, cfg)
    assert isinstance(fehler.value, http.SchutzAntwort)
    assert fehler.value.response.status_code == status
    assert len(gesehen) == 1
    assert pausen == []


@pytest.mark.parametrize("status", [403, 406])
def test_nach_schutzantwort_wechselt_kein_header(naht, status):
    """Die einzige Anfrage traegt genau die konfigurierte Kennung; ein zweiter
    Satz Kopfzeilen (Client-Hints, andere Kennung) wird nie gesendet."""
    gesehen = naht(httpx.Response(status), httpx.Response(200, text="offen"))
    with pytest.raises(http.SchutzAntwort):
        http.fetch(_URL, _BOT)
    assert [a.headers["user-agent"] for a in gesehen] == [http.BOT_UA]
    assert "sec-ch-ua" not in gesehen[0].headers
    assert "sec-fetch-mode" not in gesehen[0].headers


def test_standardkennung_ist_ehrlich_ohne_client_hints(naht):
    gesehen = naht(httpx.Response(200, text="ok"))
    http.fetch(_URL, {})
    assert gesehen[0].headers["user-agent"] == http.BOT_UA
    assert "sec-ch-ua" not in gesehen[0].headers


def test_429_ohne_retry_after_wird_nicht_wiederholt(naht, pausen):
    gesehen = naht(httpx.Response(429), httpx.Response(200, text="offen"))
    with pytest.raises(http.SchutzAntwort) as fehler:
        http.fetch(_URL, _BOT)
    assert fehler.value.response.status_code == 429
    assert len(gesehen) == 1
    assert pausen == []


def test_429_mit_zu_langem_retry_after_bricht_ab(naht, pausen):
    gesehen = naht(
        httpx.Response(429, headers={"Retry-After": "61"}),
        httpx.Response(200, text="offen"),
    )
    with pytest.raises(http.SchutzAntwort):
        http.fetch(_URL, _BOT)
    assert len(gesehen) == 1
    assert pausen == []


def test_429_mit_retry_after_im_rahmen_wartet_einmal_und_ruft_einmal_wieder_ab(
    naht, pausen
):
    gesehen = naht(
        httpx.Response(429, headers={"Retry-After": "60"}),
        httpx.Response(200, text="offen"),
    )
    antwort = http.fetch(_URL, _BOT)
    assert antwort.text == "offen"
    assert len(gesehen) == 2
    assert pausen == [60.0]
    assert gesehen[0].headers == gesehen[1].headers


def test_zweites_429_trotz_retry_after_wird_nicht_noch_einmal_wiederholt(naht, pausen):
    gesehen = naht(httpx.Response(429, headers={"Retry-After": "5"}))
    with pytest.raises(http.SchutzAntwort):
        http.fetch(_URL, _BOT)
    assert len(gesehen) == 2
    assert pausen == [5.0]


def test_retry_after_als_datum_wird_nicht_geraten(naht):
    gesehen = naht(
        httpx.Response(429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})
    )
    with pytest.raises(http.SchutzAntwort):
        http.fetch(_URL, _BOT)
    assert len(gesehen) == 1


def test_schnell_wartet_auch_bei_kurzem_retry_after_nicht(naht, pausen):
    gesehen = naht(httpx.Response(429, headers={"Retry-After": "1"}))
    with pytest.raises(http.SchutzAntwort):
        http.fetch(_URL, _BOT, schnell=True)
    assert len(gesehen) == 1
    assert pausen == []


def test_retry_after_ueber_die_restfrist_hinaus_bricht_ab(naht):
    gesehen = naht(httpx.Response(429, headers={"Retry-After": "30"}))
    with http.deadline(5), pytest.raises(http.SchutzAntwort):
        http.fetch(_URL, _BOT)
    assert len(gesehen) == 1


@pytest.mark.parametrize(
    "antwort",
    [
        httpx.Response(503, headers={"cf-mitigated": "challenge"}, text="x"),
        httpx.Response(503, text="<title>Just a moment...</title>"),
        httpx.Response(
            503, text='<script src="/cdn-cgi/challenge-platform/h"></script>'
        ),
    ],
    ids=["kopf", "moment", "plattform"],
)
def test_503_mit_challenge_ist_schutzantwort_ohne_wiederholung(naht, antwort):
    gesehen = naht(antwort, httpx.Response(200, text="offen"))
    with pytest.raises(http.SchutzAntwort) as fehler:
        http.fetch(_URL, _BOT)
    assert fehler.value.response.status_code == 503
    assert len(gesehen) == 1


@pytest.mark.parametrize("status", [500, 502, 503])
def test_gegenprobe_serverfehler_ohne_challenge_wird_mit_derselben_kennung_wiederholt(
    naht, status
):
    gesehen = naht(httpx.Response(status, text="Wartungsarbeiten"))
    with pytest.raises(httpx.HTTPStatusError) as fehler:
        http.fetch(_URL, _BOT)
    assert not isinstance(fehler.value, http.SchutzAntwort)
    assert len(gesehen) == 3
    assert {a.headers["user-agent"] for a in gesehen} == {http.BOT_UA}


def test_gegenprobe_serverfehler_dann_erfolg(naht):
    gesehen = naht(httpx.Response(503, text="kurz weg"), httpx.Response(200, text="da"))
    assert http.fetch(_URL, _BOT).text == "da"
    assert len(gesehen) == 2
