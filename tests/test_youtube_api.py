"""Videos für ki.html über die YouTube Data API v3 (Pitch 9, Schnitt 14).

Die Antworten unter ``tests/fixtures/ki/youtube-*.json`` sind nach der
API-Dokumentation gebaut, nicht live abgerufen (``_herkunft.json``). Geprüft:
Titel, Datum, Dauer und ID aus ``playlistItems.list`` und ``videos.list``; der
Schlüssel geht nur im Kopf mit, nie in Adresse, Protokoll oder Fehlertext; ohne
Schlüssel, bei erschöpftem Kontingent und ungültigem Schlüssel steht ein
benannter Ausfall im Store, und der alte Stand bleibt. Der Store hält höchstens
30 Videos der letzten 60 Tage. Feste Tage, nie heute.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest
from bestand_pfad import verlinke_neben_data

from telco_radar import zusatzstufen
from telco_radar.analyze import ki_videos
from telco_radar.analyze.takt import Takt
from telco_radar.collect import http, youtube_api
from telco_radar.config import load_config

WURZEL = Path(__file__).resolve().parents[1]
FIXTURES = WURZEL / "tests" / "fixtures" / "ki"
HEUTE = date(2026, 10, 11)
GESTERN = date(2026, 10, 10)
SCHLUESSEL = "test-schluessel-nicht-echt-0815"
CT = {
    "name": "c't 3003",
    "kanal_id": "UC1t9VFj-O6YUDPQxaVg-NkQ",
    "uploads": "UU1t9VFj-O6YUDPQxaVg-NkQ",
    "sprache": "de",
    "stufe": "Einstieg",
}


def _json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _api(gefragt: list[httpx.Request], fehler: str | None = None, status=403):
    def antworte(anfrage: httpx.Request) -> httpx.Response:
        gefragt.append(anfrage)
        if anfrage.url.host == "i.ytimg.com":
            return httpx.Response(404)
        if fehler is not None:
            return httpx.Response(status, json=_json(fehler))
        if anfrage.url.path.endswith("/playlistItems"):
            if anfrage.url.params["playlistId"] != CT["uploads"]:
                return httpx.Response(404, json={"error": {"code": 404}})
            return httpx.Response(200, json=_json("youtube-playlistitems.json"))
        assert anfrage.url.path.endswith("/videos")
        return httpx.Response(200, json=_json("youtube-videos.json"))

    return httpx.MockTransport(antworte)


def test_parser_lesen_id_titel_datum_aus_playlistitems():
    videos = youtube_api.uploads(_json("youtube-playlistitems.json"))
    assert videos == [
        {
            "id": "TEST0000001",
            "titel": "🔥 Eigenen KI-Agenten bauen – so geht's 🤖",
            "datum": "2026-10-09",
            "vorschau": "https://i.ytimg.com/vi/TEST0000001/hqdefault.jpg",
        },
        {
            "id": "TEST0000002",
            "titel": "Copilot im Büro: Was wirklich hilft",
            "datum": "2026-10-02",
            "vorschau": None,
        },
        {
            "id": "TEST0000004",
            "titel": "Alte Folge vom Juli",
            "datum": "2026-07-01",
            "vorschau": None,
        },
    ]


def test_parser_liest_die_dauer_aus_videos():
    dauer = youtube_api.dauern(_json("youtube-videos.json"))
    assert dauer == {"TEST0000001": 847, "TEST0000002": 3720, "TEST0000004": 45}


@pytest.mark.parametrize(
    ("iso", "sekunden"),
    [
        ("PT14M7S", 847),
        ("PT1H2M", 3720),
        ("PT45S", 45),
        ("P1DT1S", 86401),
        ("P0D", None),
        ("kaputt", None),
    ],
)
def test_iso_dauer_in_sekunden(iso, sekunden):
    assert youtube_api.dauer_sekunden(iso) == sekunden


def test_abruf_traegt_den_schluessel_nur_im_kopf(monkeypatch, caplog):
    gefragt: list[httpx.Request] = []
    monkeypatch.setattr(http, "TRANSPORT", _api(gefragt))
    caplog.set_level(logging.DEBUG)
    abruf = youtube_api.abrufen([CT], {"timeout_seconds": 5}, SCHLUESSEL)
    assert [a.url.path for a in gefragt] == [
        "/youtube/v3/playlistItems",
        "/youtube/v3/videos",
    ]
    assert gefragt[0].url.params["part"] == "snippet,contentDetails"
    assert int(gefragt[0].url.params["maxResults"]) <= 10
    assert gefragt[1].url.params["id"] == "TEST0000001,TEST0000002,TEST0000004"
    assert all(a.headers["x-goog-api-key"] == SCHLUESSEL for a in gefragt)
    assert not any(SCHLUESSEL in str(a.url) for a in gefragt)
    assert SCHLUESSEL not in caplog.text
    videos = abruf["kanaele"]["c't 3003"]["videos"]
    assert videos[0] == {
        "id": "TEST0000001",
        "titel": "🔥 Eigenen KI-Agenten bauen – so geht's 🤖",
        "datum": "2026-10-09",
        "vorschau": "https://i.ytimg.com/vi/TEST0000001/hqdefault.jpg",
        "dauer_sekunden": 847,
    }


def test_ohne_schluessel_benannter_ausfall_und_kein_abruf(monkeypatch):
    gefragt: list[httpx.Request] = []
    monkeypatch.setattr(http, "TRANSPORT", _api(gefragt))
    abruf = youtube_api.abrufen([CT], {}, None)
    assert abruf == {"error": "YouTube-Schlüssel fehlt"}
    assert youtube_api.abrufen([CT], {}, "") == abruf
    assert gefragt == []


@pytest.mark.parametrize(
    ("datei", "status", "erwartet"),
    [
        ("youtube-fehler-kontingent.json", 403, "403 quotaExceeded"),
        ("youtube-fehler-schluessel.json", 400, "400 keyInvalid"),
    ],
)
def test_kontingent_und_schluessel_sind_benannte_fehler(
    monkeypatch, caplog, datei, status, erwartet
):
    gefragt: list[httpx.Request] = []
    monkeypatch.setattr(http, "TRANSPORT", _api(gefragt, datei, status))
    zweiter = dict(CT, name="Zweiter", uploads="UUzweiter")
    abruf = youtube_api.abrufen([CT, zweiter], {}, SCHLUESSEL)
    assert erwartet in abruf["error"]
    assert "kanaele" not in abruf
    assert len(gefragt) == 1
    assert SCHLUESSEL not in abruf["error"] + caplog.text


def test_fehlende_playlist_trifft_nur_ihren_kanal(monkeypatch):
    gefragt: list[httpx.Request] = []
    monkeypatch.setattr(http, "TRANSPORT", _api(gefragt))
    weg = dict(CT, name="Weg", uploads="UUweg")
    abruf = youtube_api.abrufen([weg, CT], {}, SCHLUESSEL)
    assert abruf["kanaele"]["Weg"]["error"].startswith("HTTP 404")
    assert len(abruf["kanaele"]["c't 3003"]["videos"]) == 3


def _abruf_mit(videos: list[dict]) -> dict:
    return {"kanaele": {"c't 3003": {"videos": videos}}}


def _video(nr: int, tag: date) -> dict:
    return {
        "id": f"V{nr:010d}",
        "titel": f"Video {nr}",
        "datum": tag.isoformat(),
        "dauer_sekunden": 600,
    }


def test_store_haelt_hoechstens_30_videos_der_letzten_60_tage(tmp_path):
    kanaele = [CT]
    videos = [_video(i, HEUTE - timedelta(days=i)) for i in range(70)]
    store = ki_videos.aktualisiere(tmp_path, kanaele, _abruf_mit(videos), HEUTE)
    assert len(store["videos"]) == ki_videos.HOECHSTENS == 30
    assert store["videos"][0]["id"] == "V0000000000"
    assert store["videos"][-1]["id"] == "V0000000029"
    wenige = [_video(i, HEUTE - timedelta(days=i * 10)) for i in range(10)]
    store = ki_videos.aktualisiere(tmp_path / "b", kanaele, _abruf_mit(wenige), HEUTE)
    assert [v["datum"] for v in store["videos"]][-1] == "2026-08-12"
    assert len(store["videos"]) == 7
    assert store["videos"][0] == {
        "id": "V0000000000",
        "titel": "Video 0",
        "kanal": "c't 3003",
        "datum": "2026-10-11",
        "dauer_sekunden": 600,
        "stufe": "Einstieg",
        "sprache": "de",
        "bild": None,
    }


def test_store_aus_den_fixtures_saeubert_titel_und_laesst_alte_weg(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(http, "TRANSPORT", _api([]))
    abruf = youtube_api.abrufen([CT], {}, SCHLUESSEL)
    store = ki_videos.aktualisiere(tmp_path, [CT], abruf, HEUTE)
    assert [v["titel"] for v in store["videos"]] == [
        "Eigenen KI-Agenten bauen – so geht's",
        "Copilot im Büro: Was wirklich hilft",
    ]
    assert store["stand"] == HEUTE.isoformat()
    assert store["error"] is None
    assert store["kanaele"]["c't 3003"]["error"] is None
    assert "ytimg" not in json.dumps(store)
    assert ki_videos.lade(tmp_path) == store


def test_ausfall_behaelt_den_alten_stand_und_nennt_ihn(tmp_path):
    alt = [_video(1, GESTERN)]
    ki_videos.aktualisiere(tmp_path, [CT], _abruf_mit(alt), GESTERN)
    store = ki_videos.aktualisiere(
        tmp_path, [CT], {"error": "YouTube-Schlüssel fehlt"}, HEUTE
    )
    assert store["error"] == "YouTube-Schlüssel fehlt"
    assert store["stand"] == GESTERN.isoformat()
    assert [v["id"] for v in store["videos"]] == ["V0000000001"]
    kanal = {"c't 3003": {"error": "HTTP 503 backendError"}}
    store = ki_videos.aktualisiere(tmp_path, [CT], {"kanaele": kanal}, HEUTE)
    assert store["kanaele"]["c't 3003"]["error"] == "HTTP 503 backendError"
    assert store["kanaele"]["c't 3003"]["abgerufen"] == GESTERN.isoformat()
    assert [v["id"] for v in store["videos"]] == ["V0000000001"]


def test_lade_ohne_store_ist_nicht_abgerufen(tmp_path):
    assert ki_videos.lade(tmp_path) == {
        "stand": None,
        "videos": [],
        "kanaele": {},
        "error": None,
    }


def test_kanalliste_ist_belegt_und_deutsch_zuerst():
    kanaele = ki_videos.kanaele(WURZEL)
    assert len(kanaele) == 17
    assert kanaele[0]["name"] == "c't 3003"
    sprachen = [k["sprache"] for k in kanaele]
    assert sprachen == sorted(sprachen, key=lambda s: s != "de")
    for k in kanaele:
        assert k["kanal_id"].startswith("UC") and len(k["kanal_id"]) == 24
        assert k["uploads"] == "UU" + k["kanal_id"][2:]
        assert k["stufe"] in ("Einstieg", "Fortgeschritten")


def test_zusatzstufe_ruft_nur_mit_schalter_ab(tmp_path, monkeypatch):
    gefragt: list[httpx.Request] = []
    monkeypatch.setattr(http, "TRANSPORT", _api(gefragt))
    monkeypatch.setenv(youtube_api.UMGEBUNG, SCHLUESSEL)
    verlinke_neben_data(tmp_path)
    takt = Takt(lambda: 0.0, lambda *_: None, lambda f, ausfall: f())
    cfg = load_config(tmp_path)
    cfg.settings["ki_videos_aktiv"] = False
    zusatzstufen._ki_videos(cfg, tmp_path, HEUTE, takt)
    assert gefragt == []
    assert not (tmp_path / "data" / "state" / ki_videos.STORE_NAME).exists()
    cfg.settings["ki_videos_aktiv"] = True
    zusatzstufen._ki_videos(cfg, tmp_path, HEUTE, takt)
    store = ki_videos.lade(tmp_path / "data" / "state")
    assert store["stand"] == HEUTE.isoformat()
    assert len(store["videos"]) == 2
    assert [v["bild"] for v in store["videos"]] == [None, None]
    assert "ytimg" not in json.dumps(store)
    monkeypatch.delenv(youtube_api.UMGEBUNG)
    zusatzstufen._ki_videos(cfg, tmp_path, HEUTE, takt)
    store = ki_videos.lade(tmp_path / "data" / "state")
    assert store["error"] == "YouTube-Schlüssel fehlt"
    assert len(store["videos"]) == 2
