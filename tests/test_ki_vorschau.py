"""Vorschaubilder der KI-Videos selbst ausliefern (Pitch 9, Schnitt 14).

Der Tageslauf holt je Video im Store das größte Vorschaubild aus
``snippet.thumbnails`` (maxres > standard > high > medium) mit ehrlicher
Kennung und nach robots.txt, schneidet 4:3-Balken auf 16:9, verkleinert auf
960 px und legt ``<id>.jpg`` unter ``data/state/ki_videos/`` ab. Scheitert ein
Bild, heißt ``bild`` ``None``. Die Bilder entstehen hier mit Pillow, der Abruf
läuft über die Naht ``http.TRANSPORT``; kein Netz, feste Tage. ``ROBOTS`` ist
der Wortlaut von https://i.ytimg.com/robots.txt am 13.10.2026.
"""

from __future__ import annotations

import io
import json
import logging
from datetime import date
from pathlib import Path

import httpx
import pytest
from bestand_pfad import verlinke_neben_data
from PIL import Image

from telco_radar import zusatzstufen
from telco_radar.analyze import ki_videos
from telco_radar.analyze.takt import Takt
from telco_radar.collect import http, youtube_api, youtube_vorschau

WURZEL = Path(__file__).resolve().parents[1]
FIXTURES = WURZEL / "tests" / "fixtures" / "ki"
HEUTE = date(2026, 10, 11)
ROBOTS = (
    "# robots.txt file for ytimg.com\n\nUser-agent: Mediapartners-Google*\n"
    "Disallow:\n\nUser-agent: *\nDisallow: /sb/\n"
)
CT = {
    "name": "c't 3003",
    "kanal_id": "UC1t9VFj-O6YUDPQxaVg-NkQ",
    "uploads": "UU1t9VFj-O6YUDPQxaVg-NkQ",
    "sprache": "de",
    "stufe": "Einstieg",
}


def _jpeg(breite: int, hoehe: int, balken: int = 0) -> bytes:
    bild = Image.new("RGB", (breite, hoehe), (200, 40, 40))
    if balken:
        schwarz = Image.new("RGB", (breite, balken), (0, 0, 0))
        bild.paste(schwarz, (0, 0))
        bild.paste(schwarz, (0, hoehe - balken))
    aus = io.BytesIO()
    bild.save(aus, "JPEG", quality=90)
    return aus.getvalue()


def _netz(bilder: dict[str, httpx.Response], gefragt: list, robots: str = ROBOTS):
    def antworte(anfrage: httpx.Request) -> httpx.Response:
        gefragt.append(anfrage)
        if anfrage.url.path == "/robots.txt":
            return httpx.Response(200, text=robots)
        return bilder.get(str(anfrage.url), httpx.Response(404))

    return httpx.MockTransport(antworte)


def _url(vid: str, groesse: str = "maxresdefault") -> str:
    return f"https://i.ytimg.com/vi/{vid}/{groesse}.jpg"


def test_bestes_vorschaubild_in_der_reihenfolge_maxres_standard_high_medium():
    alle = {
        g: {"url": f"https://i.ytimg.com/vi/X/{g}.jpg"}
        for g in ("default", "medium", "high", "standard", "maxres")
    }
    assert youtube_api.vorschau({"thumbnails": alle}).endswith("/maxres.jpg")
    del alle["maxres"]
    assert youtube_api.vorschau({"thumbnails": alle}).endswith("/standard.jpg")
    del alle["standard"]
    assert youtube_api.vorschau({"thumbnails": alle}).endswith("/high.jpg")
    del alle["high"]
    assert youtube_api.vorschau({"thumbnails": alle}).endswith("/medium.jpg")
    del alle["medium"]
    assert youtube_api.vorschau({"thumbnails": alle}) is None
    assert youtube_api.vorschau({}) is None


def test_bild_wird_mit_ehrlicher_kennung_geholt_und_auf_960_verkleinert(
    tmp_path, monkeypatch
):
    gefragt: list[httpx.Request] = []
    url = _url("VID00000001")
    netz = _netz({url: httpx.Response(200, content=_jpeg(1280, 720))}, gefragt)
    monkeypatch.setattr(http, "TRANSPORT", netz)
    bilder = youtube_vorschau.hole(
        [{"id": "VID00000001"}], {"VID00000001": url}, tmp_path, {}
    )
    assert bilder == {"VID00000001": "VID00000001.jpg"}
    with Image.open(tmp_path / "VID00000001.jpg") as bild:
        assert bild.format == "JPEG"
        assert bild.size == (youtube_vorschau.BREITE, 540) == (960, 540)
    assert [a.url.path for a in gefragt] == [
        "/robots.txt",
        "/vi/VID00000001/maxresdefault.jpg",
    ]
    assert all(a.headers["user-agent"] == http.BOT_UA for a in gefragt)


def test_vier_zu_drei_mit_balken_wird_auf_sechzehn_zu_neun_beschnitten(
    tmp_path, monkeypatch
):
    url = _url("VID00000002", "hqdefault")
    roh = _jpeg(480, 360, balken=45)
    netz = _netz({url: httpx.Response(200, content=roh)}, [])
    monkeypatch.setattr(http, "TRANSPORT", netz)
    youtube_vorschau.hole([{"id": "VID00000002"}], {"VID00000002": url}, tmp_path, {})
    with Image.open(tmp_path / "VID00000002.jpg") as bild:
        assert bild.size == (480, 270)
        oben = bild.convert("RGB").getpixel((240, 2))
    assert oben[0] > 150, "der schwarze Balken ist abgeschnitten"


@pytest.mark.parametrize(
    ("antwort", "robots"),
    [
        (httpx.Response(404), ROBOTS),
        (httpx.Response(200, content=b"<html>keine Grafik</html>"), ROBOTS),
        (
            httpx.Response(200, content=_jpeg(1280, 720)),
            "User-agent: *\nDisallow: /vi/\n",
        ),
    ],
    ids=["404", "kein-bild", "robots-sperrt"],
)
def test_scheitern_heisst_bild_none_und_wird_protokolliert(
    tmp_path, monkeypatch, caplog, antwort, robots
):
    url = _url("VID00000003")
    gefragt: list[httpx.Request] = []
    monkeypatch.setattr(http, "TRANSPORT", _netz({url: antwort}, gefragt, robots))
    caplog.set_level(logging.WARNING)
    bilder = youtube_vorschau.hole(
        [{"id": "VID00000003"}, {"id": "VID00000004"}],
        {"VID00000003": url, "VID00000004": None},
        tmp_path,
        {},
    )
    assert bilder == {"VID00000003": None, "VID00000004": None}
    assert list(tmp_path.iterdir()) == []
    assert "Vorschaubild VID00000003 nicht geladen" in caplog.text
    if "Disallow: /vi/" in robots:
        assert [a.url.path for a in gefragt] == ["/robots.txt"]


def test_vorhandenes_bild_wird_nicht_neu_geholt_und_fremde_id_nie(
    tmp_path, monkeypatch
):
    gefragt: list[httpx.Request] = []
    monkeypatch.setattr(http, "TRANSPORT", _netz({}, gefragt))
    (tmp_path / "VID00000005.jpg").write_bytes(_jpeg(960, 540))
    bilder = youtube_vorschau.hole(
        [{"id": "VID00000005"}, {"id": "../boese"}],
        {"VID00000005": _url("VID00000005"), "../boese": _url("x")},
        tmp_path,
        {},
    )
    assert bilder == {"VID00000005": "VID00000005.jpg", "../boese": None}
    assert gefragt == []


def test_aufraeumen_trifft_nur_jpegs_ohne_video_im_ordner(tmp_path):
    ordner = tmp_path / "ki_videos"
    ordner.mkdir()
    for name in ("A0000000001.jpg", "A0000000002.jpg", "notiz.txt"):
        (ordner / name).write_bytes(b"x")
    (tmp_path / "nachbar.jpg").write_bytes(b"x")
    assert youtube_vorschau.raeume_auf(ordner, {"A0000000001.jpg"}) == 1
    assert sorted(p.name for p in ordner.iterdir()) == ["A0000000001.jpg", "notiz.txt"]
    assert (tmp_path / "nachbar.jpg").exists()
    assert youtube_vorschau.raeume_auf(tmp_path / "fehlt", set()) == 0


def test_zusatzstufe_legt_bilder_ab_nennt_sie_im_store_und_raeumt_auf(
    tmp_path, monkeypatch
):
    def antworte(anfrage: httpx.Request) -> httpx.Response:
        if anfrage.url.host == "i.ytimg.com":
            if anfrage.url.path == "/robots.txt":
                return httpx.Response(200, text=ROBOTS)
            if anfrage.url.path == "/vi/TEST0000001/hqdefault.jpg":
                return httpx.Response(200, content=_jpeg(480, 360, balken=45))
            return httpx.Response(404)
        datei = "youtube-playlistitems.json"
        if anfrage.url.path.endswith("/videos"):
            datei = "youtube-videos.json"
        inhalt = (FIXTURES / datei).read_text(encoding="utf-8")
        return httpx.Response(200, json=json.loads(inhalt))

    monkeypatch.setattr(http, "TRANSPORT", httpx.MockTransport(antworte))
    monkeypatch.setenv(youtube_api.UMGEBUNG, "test-schluessel-nicht-echt")
    verlinke_neben_data(tmp_path)
    state = tmp_path / "data" / "state"
    ordner = ki_videos.bildordner(state)
    ordner.mkdir(parents=True)
    (ordner / "WEG00000001.jpg").write_bytes(b"alt")
    from telco_radar.config import load_config

    cfg = load_config(tmp_path)
    cfg.settings["ki_videos_aktiv"] = True
    takt = Takt(lambda: 0.0, lambda *_: None, lambda f, ausfall: f())
    zusatzstufen._ki_videos(cfg, tmp_path, HEUTE, takt)
    store = ki_videos.lade(state)
    assert {v["id"]: v["bild"] for v in store["videos"]} == {
        "TEST0000001": "TEST0000001.jpg",
        "TEST0000002": None,
    }
    assert sorted(p.name for p in ordner.iterdir()) == ["TEST0000001.jpg"]
    assert "ytimg" not in json.dumps(store)
    with Image.open(ordner / "TEST0000001.jpg") as bild:
        assert bild.size == (480, 270)
    monkeypatch.delenv(youtube_api.UMGEBUNG)
    zusatzstufen._ki_videos(cfg, tmp_path, HEUTE, takt)
    store = ki_videos.lade(state)
    assert store["error"] == youtube_api.OHNE_SCHLUESSEL
    assert store["videos"][0]["bild"] == "TEST0000001.jpg"
    assert (ordner / "TEST0000001.jpg").exists()
