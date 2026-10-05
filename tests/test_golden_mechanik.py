"""Mechanik des goldenen Laufs ohne Aufnahme: Bänder, Nähte, Lücken, HTTP 402."""

from __future__ import annotations

import hashlib
import importlib
import json
import shutil
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
    sitzung = llm.LlmSitzung.aktive()
    assert (http.TRANSPORT, sitzung.transport, sitzung.client) == (None, None, None)


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


GOLDEN = Path(__file__).resolve().parent / "fixtures" / "golden"
AUFNAHME = max(p for p in GOLDEN.iterdir() if p.is_dir())
waechter_vertraege = importlib.import_module("waechter_vertraege")


def _kopie(tmp_path) -> Path:
    ziel = tmp_path / "wurzel" / "tests" / "fixtures" / "golden" / AUFNAHME.name
    shutil.copytree(AUFNAHME, ziel)
    return ziel


def _seiten_neu(monkeypatch, ordner: Path, seiten: dict[str, str]) -> list[str]:
    monkeypatch.setattr(golden_aufnehmen, "wiedergaben", lambda _: seiten)
    return golden_aufnehmen.seiten_neu(ordner)


def test_seiten_neu_schreibt_nur_erwartet_und_seinen_sha256(tmp_path, monkeypatch):
    ordner = _kopie(tmp_path)
    vorher = {p: p.read_bytes() for p in ordner.rglob("*") if p.is_file()}
    erwartet = json.loads((ordner / "erwartet.json").read_text(encoding="utf-8"))
    seiten = {**erwartet, "geraete.html": "neu"}
    del seiten["index.html"]

    geaendert = _seiten_neu(monkeypatch, ordner, seiten)

    assert geaendert == ["geraete.html", "index.html"]
    neu = json.loads((ordner / "erwartet.json").read_text(encoding="utf-8"))
    assert neu == seiten
    anders = sorted(p.name for p, roh in vorher.items() if p.read_bytes() != roh)
    assert anders == ["_herkunft.json", "erwartet.json"]
    alt_herkunft = json.loads(vorher[ordner / "_herkunft.json"])
    neu_herkunft = json.loads((ordner / "_herkunft.json").read_text(encoding="utf-8"))
    sha = hashlib.sha256((ordner / "erwartet.json").read_bytes()).hexdigest()
    for eintrag in alt_herkunft["eintraege"]:
        if eintrag["datei"] == "erwartet.json":
            eintrag["sha256_roh"] = sha
    assert neu_herkunft == alt_herkunft
    assert waechter_vertraege.fixture_herkunft(tmp_path / "wurzel") == []


def test_gleiche_seiten_lassen_die_aufnahme_unberuehrt(tmp_path, monkeypatch):
    ordner = _kopie(tmp_path)
    vorher = {p: p.read_bytes() for p in ordner.rglob("*") if p.is_file()}
    erwartet = json.loads((ordner / "erwartet.json").read_text(encoding="utf-8"))

    assert _seiten_neu(monkeypatch, ordner, erwartet) == []

    assert all(p.read_bytes() == roh for p, roh in vorher.items())


def test_von_hand_geaenderte_seite_ohne_sha256_ist_in_stufe_0_rot(tmp_path):
    ordner = _kopie(tmp_path)
    datei = ordner / "erwartet.json"
    zeilen = datei.read_text(encoding="utf-8").splitlines(keepends=True)
    zeilen[1] = zeilen[1].replace('": "', '": "0', 1)
    datei.write_text("".join(zeilen), encoding="utf-8")

    meldungen = waechter_vertraege.fixture_herkunft(tmp_path / "wurzel")

    assert meldungen == [
        f"tests/fixtures/golden/{AUFNAHME.name}/erwartet.json: sha256 weicht vom"
        " Eintrag in _herkunft.json ab"
    ]


def test_ableiten_behaelt_alte_luecken_die_noch_angefragt_werden():
    neu = golden.Band()
    neu.merke(("GET", QUELLE, "radar", "0"), {"fehler": "ConnectError"})
    alt = [
        f"HTTP-Antwort für GET {QUELLE} fehlt, {golden.HINWEIS}",
        f"HTTP-Antwort für GET https://weg.example/rss fehlt, {golden.HINWEIS}",
    ]
    fehlend = [f"HTTP-Antwort für GET https://neu.example/a,b fehlt, {golden.HINWEIS}"]

    luecken = golden_aufnehmen.luecken_vereinigen(alt, fehlend, neu)

    assert luecken == sorted([alt[0], fehlend[0]])
