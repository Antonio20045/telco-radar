"""Gesperrte Quellen (Auftrag fetch-ehrlich-0511, Nachbesserung M1/M2/S2).

Eine Quelle, die mit `SchutzAntwort` endet, steht im Lauf-Ergebnis mit Status
und Datum; die Quellenseite listet sie daraus auf. Nichts davon ist hart
kodiert. `scripts/rescue_sources.py` wechselt nach einer Sperre nicht mehr die
Kennung.
"""

from __future__ import annotations

import importlib.util
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from bs4 import BeautifulSoup

import telco_radar.collect as collect_mod
from telco_radar.collect import collect_all, http
from telco_radar.config import Source
from telco_radar.models import Item
from telco_radar.report.html import render_site

JETZT = datetime(2026, 11, 5, 12, tzinfo=UTC)
URL_GESPERRT = "https://gesperrt.example/feed"
URL_OFFEN = "https://offen.example/feed"


class _Cfg:
    def __init__(self):
        self.settings = {"collect_max_workers": 2}
        self.operators = []
        self.news_sources = [
            Source(type="rss", url=URL_GESPERRT, name="Gesperrt", kind="trade_press"),
            Source(type="rss", url=URL_OFFEN, name="Offen", kind="trade_press"),
        ]
        self.tech_sources = []


@pytest.fixture(autouse=True)
def _gate_zuruecksetzen():
    vorher = http.active_gate()
    yield
    http._gate = vorher


def _schutz(status: int) -> http.SchutzAntwort:
    anfrage = httpx.Request("GET", URL_GESPERRT)
    antwort = httpx.Response(status, request=anfrage)
    return http.schutz(antwort, f"Schutzantwort {status}, kein zweiter Versuch")


def _sammeln(monkeypatch, fehler: Exception, register=None):
    def rss(source, *a, **k):
        if source.url == URL_GESPERRT:
            raise fehler
        return [Item(title="Meldung", url="https://offen.example/1", source_name="O")]

    monkeypatch.setattr(collect_mod, "collect_rss", rss)
    _, ergebnisse = collect_all(_Cfg(), register=register, jetzt=JETZT)
    return {r["url"]: r for r in ergebnisse}


def test_schutzantwort_stoppt_die_anderen_quellen_nicht(monkeypatch):
    erg = _sammeln(monkeypatch, _schutz(403))
    assert erg[URL_OFFEN]["status"] == "ok"
    assert erg[URL_OFFEN]["count"] == 1
    assert erg[URL_GESPERRT]["status"] == "fail"
    assert erg[URL_GESPERRT]["error"].startswith("SchutzAntwort:")


def test_gesperrte_quelle_traegt_status_und_datum_im_lauf_ergebnis(monkeypatch):
    erg = _sammeln(monkeypatch, _schutz(406))
    gesperrt = erg[URL_GESPERRT]
    assert gesperrt["schutz"] is True
    assert gesperrt["schutz_status"] == 406
    assert gesperrt["schutz_datum"] == "2026-11-05"
    assert "schutz" not in erg[URL_OFFEN]


def test_anderer_fehler_ist_keine_sperre(monkeypatch):
    erg = _sammeln(monkeypatch, ValueError("unparseable feed"))
    assert erg[URL_GESPERRT]["status"] == "fail"
    assert "schutz" not in erg[URL_GESPERRT]


def test_gewoehnlicher_statusfehler_ist_keine_sperre(monkeypatch):
    anfrage = httpx.Request("GET", URL_GESPERRT)
    fehler = httpx.HTTPStatusError(
        "status 404", request=anfrage, response=httpx.Response(404, request=anfrage)
    )
    assert "schutz" not in _sammeln(monkeypatch, fehler)[URL_GESPERRT]


def test_stillgelegte_gesperrte_quelle_bleibt_in_der_liste(monkeypatch):
    """Nach der Stilllegung wird nicht mehr abgerufen; die Sperre bleibt sichtbar."""

    class Eintrag:
        quarantaene_grund = (
            "3 Laeufe ohne Meldung (zuletzt fail: SchutzAntwort: "
            "Schutzantwort 403, kein zweiter Versuch)"
        )
        letzter_lauf = "2026-11-03"

    class Register:
        def wird_abgerufen(self, url):
            return url != URL_GESPERRT

        def eintrag(self, url):
            return Eintrag()

    erg = _sammeln(monkeypatch, _schutz(403), register=Register())
    still = erg[URL_GESPERRT]
    assert still["status"] == "quarantaene"
    assert (still["schutz"], still["schutz_status"], still["schutz_datum"]) == (
        True,
        403,
        "2026-11-03",
    )


def _seite(tmp_path, quellen: list[dict]) -> BeautifulSoup:
    reports = tmp_path / "reports"
    reports.mkdir(parents=True)
    (reports / "2026-11-05.json").write_text(
        json.dumps(
            {
                "date": "2026-11-05",
                "generated_with_llm": True,
                "stats": {"new": 0},
                "briefing_md": "## Auf einen Blick\n\nText.",
                "regions": {},
                "competitors": [],
                "run": {
                    "duration_seconds": 60,
                    "models": {"analyst": "m", "editor": "m"},
                    "phases": [],
                    "analysts": [],
                    "sources": quellen,
                    "source_summary": {},
                },
            }
        ),
        encoding="utf-8",
    )
    site = tmp_path / "site"
    render_site(site, reports)
    html = (site / "transparenz.html").read_text(encoding="utf-8")
    return BeautifulSoup(html, "html.parser")


def _quelle(name: str, **extra) -> dict:
    return {
        "name": name,
        "url": f"https://{name.lower()}.example/feed",
        "kind": "rss",
        "region": "global",
        "status": "fail",
        "count": 0,
        "error": "SchutzAntwort: Schutzantwort 403, kein zweiter Versuch",
    } | extra


def test_seite_listet_gesperrte_quellen_aus_den_daten(tmp_path):
    quellen = [
        _quelle("Broadcom", schutz=True, schutz_status=403, schutz_datum="2026-11-05"),
        _quelle("Safaricom", schutz=True, schutz_status=406, schutz_datum="2026-11-04"),
        _quelle("Kaputt", error="ValueError: unparseable feed"),
    ]
    karte = _seite(tmp_path, quellen).select_one("#gesperrt")
    assert karte is not None
    text = karte.get_text(" ", strip=True)
    assert "wir umgehen Sperren nicht, deshalb fehlen ihre Daten" in text
    zeilen = [z.get_text(" ", strip=True) for z in karte.select(".rowtable-row")]
    assert zeilen == [
        "Broadcom Status 403 5. November 2026",
        "Safaricom Status 406 4. November 2026",
    ]
    assert "Kaputt" not in text
    assert "keine Quelle den Abruf gesperrt" not in text


def test_seite_sagt_ohne_sperren_dass_keine_gesperrt_hat(tmp_path):
    karte = _seite(tmp_path, [_quelle("Kaputt", error="ValueError: x")]).select_one(
        "#gesperrt"
    )
    assert karte is not None
    text = karte.get_text(" ", strip=True)
    assert "Beim letzten Lauf hat keine Quelle den Abruf gesperrt." in text
    assert not karte.select(".rowtable-row")
    assert "umgehen Sperren nicht" not in text


def _rescue():
    pfad = Path(__file__).resolve().parents[1] / "scripts" / "rescue_sources.py"
    spec = importlib.util.spec_from_file_location("rescue_sources_test", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.fixture
def naht(monkeypatch):
    gesehen: list[httpx.Request] = []

    def setze(antwort: httpx.Response) -> list[httpx.Request]:
        def antworte(anfrage: httpx.Request) -> httpx.Response:
            gesehen.append(anfrage)
            return antwort

        monkeypatch.setattr(http, "TRANSPORT", httpx.MockTransport(antworte))
        monkeypatch.setattr(http, "_gate", http.HostGate(max_parallel=1_000_000))
        return gesehen

    return setze


@pytest.mark.parametrize("status", [403, 406, 429])
def test_rescue_wechselt_nach_sperre_weder_kennung_noch_header(naht, status, caplog):
    gesehen = naht(httpx.Response(status, text="gesperrt"))
    with caplog.at_level(logging.WARNING):
        assert _rescue()._get("https://beispiel.example/feed") is None
    assert len(gesehen) == 1
    assert gesehen[0].headers["user-agent"] == http.BOT_UA
    assert any("SchutzAntwort" in m for m in caplog.messages)


def test_rescue_holt_eine_freie_seite_mit_ehrlicher_kennung(naht):
    gesehen = naht(httpx.Response(200, text="<html></html>"))
    antwort = _rescue()._get("https://beispiel.example/")
    assert antwort is not None and antwort.status_code == 200
    assert [a.headers["user-agent"] for a in gesehen] == [http.BOT_UA]


def test_rescue_404_ist_keine_sperre_und_gibt_none(naht, caplog):
    naht(httpx.Response(404, text="weg"))
    with caplog.at_level(logging.WARNING):
        assert _rescue()._get("https://beispiel.example/x") is None
    assert not any("SchutzAntwort" in m for m in caplog.messages)


@pytest.mark.parametrize("status", [401, 451])
def test_cf_mitigated_unter_500_ist_schutzantwort_ohne_wiederholung(
    monkeypatch, status
):
    gesehen: list[httpx.Request] = []

    def antworte(anfrage: httpx.Request) -> httpx.Response:
        gesehen.append(anfrage)
        return httpx.Response(status, headers={"cf-mitigated": "challenge"})

    monkeypatch.setattr(http, "TRANSPORT", httpx.MockTransport(antworte))
    monkeypatch.setattr(http, "_gate", http.HostGate(max_parallel=1_000_000))
    with pytest.raises(http.SchutzAntwort):
        http.fetch(URL_GESPERRT, {"user_agent": http.BOT_UA})
    assert len(gesehen) == 1
