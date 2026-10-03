"""Mechanik des goldenen Laufs ohne Aufnahme: Bänder, Nähte, Lücken, HTTP 402."""

from __future__ import annotations

import importlib
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from telco_radar import golden
from telco_radar.analyze import llm
from telco_radar.collect import http
from telco_radar.naehte import PRODUKTION, Naehte

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
golden_aufnehmen = importlib.import_module("golden_aufnehmen")

QUELLE = "https://quelle.example/rss"


@pytest.fixture(autouse=True)
def _naehte_zurueck():
    yield
    PRODUKTION.setzen()


def _quelle(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/kaputt":
        raise httpx.ConnectTimeout("zu langsam", request=request)
    return httpx.Response(200, headers={"content-type": "text/xml"}, text="<rss/>")


def _aufgenommen(tmp_path) -> golden.Band:
    band = golden.Band()
    Naehte(transport=http.Aufnahme(band, httpx.MockTransport(_quelle))).setzen()
    assert http.fetch(QUELLE, {}).text == "<rss/>"
    with pytest.raises(httpx.ConnectTimeout):
        http.fetch("https://quelle.example/kaputt", {}, schnell=True)
    golden.schreibe_band(tmp_path / golden.HTTP_DATEI, band)
    return golden.lies_band(tmp_path / golden.HTTP_DATEI)


def test_wiedergabe_liefert_antwort_und_fehler_der_aufnahme(tmp_path):
    band = _aufgenommen(tmp_path)
    Naehte(transport=http.Wiedergabe(band)).setzen()

    antwort = http.fetch(QUELLE, {})

    assert (antwort.status_code, antwort.text) == (200, "<rss/>")
    assert antwort.headers["content-type"] == "text/xml"
    with pytest.raises(httpx.ConnectTimeout):
        http.fetch("https://quelle.example/kaputt", {}, schnell=True)
    assert band.fehlend == []


def test_unbekannte_adresse_ist_eine_benannte_luecke(tmp_path):
    band = _aufgenommen(tmp_path)
    Naehte(transport=http.Wiedergabe(band)).setzen()

    with pytest.raises(httpx.ConnectError):
        http.fetch("https://quelle.example/neu", {}, schnell=True)

    assert band.fehlend == [
        "HTTP-Antwort für GET https://quelle.example/neu fehlt, "
        "neu aufnehmen mit make golden-aufnehmen"
    ]


def test_llm_antwort_nach_stufe_modell_und_prompt(tmp_path):
    band = golden.Band()
    aufnahme = golden.LlmBand(band, "2026-10-03", lambda s, u, m, x, v: f"{m}:{u}")
    Naehte(llm_client=aufnahme).setzen()
    assert llm.complete("sys", "frage", "modell-a") == "modell-a:frage"
    golden.schreibe_band(tmp_path / golden.LLM_DATEI, band)

    wiedergabe = golden.LlmBand(
        golden.lies_band(tmp_path / golden.LLM_DATEI), "2026-10-03"
    )
    Naehte(llm_client=wiedergabe).setzen()

    assert llm.complete("sys", "frage", "modell-a") == "modell-a:frage"
    with pytest.raises(llm.LLMFatalError):
        llm.complete("sys geändert", "frage", "modell-a")
    assert wiedergabe.band.fehlend == [
        "LLM-Antwort für Stufe test_golden_mechanik fehlt, "
        "neu aufnehmen mit make golden-aufnehmen"
    ]


def test_anderer_aufnahmetag_ist_ein_anderer_schluessel():
    band = golden.Band()
    golden.LlmBand(band, "2026-10-03", lambda *a: "ja")("s", "u", "m", 1, 1)

    wiedergabe = golden.LlmBand(band, "2026-10-04")

    with pytest.raises(golden.AufnahmeFehlt):
        wiedergabe("s", "u", "m", 1, 1)


def test_leeres_guthaben_trifft_den_llm_endpunkt_mit_402(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "golden-wiedergabe")
    monkeypatch.setenv("LLM_API_BASE", "https://llm.example/v1")
    monkeypatch.setattr(llm, "_DEAD_MODELS", set())
    Naehte(transport=http.Wiedergabe(golden.Band(), guthaben_leer=True)).setzen()

    with pytest.raises(llm.LLMModelUnavailable, match="402"):
        llm.complete("sys", "frage", "modell-a")

    assert "modell-a" in llm.dead_models()


def test_produktion_setzt_jede_naht_zurueck():
    Naehte(
        transport=http.KEIN_BILD,
        bilder=http.KEIN_BILD,
        llm_client=lambda *a: "",
        uhr=lambda: datetime(2026, 10, 3, tzinfo=UTC),
    ).setzen()

    assert PRODUKTION.setzen() is None
    assert (http.TRANSPORT, llm.TRANSPORT, llm.CLIENT) == (None, None, None)


def test_umleitung_wird_aufgenommen_und_wiedergegeben(tmp_path):
    def umleiten(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/alt":
            return httpx.Response(301, headers={"location": QUELLE})
        return _quelle(request)

    band = golden.Band()
    Naehte(transport=http.Aufnahme(band, httpx.MockTransport(umleiten))).setzen()
    assert http.fetch("https://quelle.example/alt", {}, schnell=True).text == "<rss/>"
    Naehte(transport=http.Wiedergabe(band)).setzen()

    assert http.fetch("https://quelle.example/alt", {}, schnell=True).text == "<rss/>"
    assert band.fehlend == []


def _antworten(*eintraege: dict) -> golden.Band:
    band = golden.Band()
    for nr, eintrag in enumerate(eintraege):
        band.merke(("editor", "modell-a", str(nr)), eintrag)
    return band


def test_ausfall_wird_nur_mit_dem_schalter_aufgenommen():
    abgelehnt = _antworten({"fehler": "LLMFatalError"})

    with pytest.raises(SystemExit, match="--llm-ausfall"):
        golden_aufnehmen.llm_pruefen(abgelehnt, llm_ausfall=False)
    golden_aufnehmen.llm_pruefen(abgelehnt, llm_ausfall=True)


def test_schalter_ausfall_verweigert_einen_lauf_mit_antwort():
    beantwortet = _antworten({"fehler": "LLMFatalError"}, {"antwort": "ja"})

    with pytest.raises(SystemExit, match="hat geantwortet"):
        golden_aufnehmen.llm_pruefen(beantwortet, llm_ausfall=True)
    golden_aufnehmen.llm_pruefen(beantwortet, llm_ausfall=False)
