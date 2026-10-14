"""Videos zwischen den KI-Meldungen (Pitch 9, Schnitte 14 und 15).

Die Videos kommen aus dem Store ``ki_videos.json`` (``analyze.ki_videos``).
Videos unter ``KURZ_UNTER_SEKUNDEN`` (Shorts) und ohne Dauer fallen weg. Das
erste lange Video steht groß oben in der linken Spalte, das zweite klein unter
der ersten Meldung von „Auch wichtig“, die nächsten sechs in der Reihe
``#ki-videos`` zwischen den Ressort-Kapiteln; jedes genau einmal. Ohne Store oder mit
``error`` nennt die Reihe Grund und Stand, ohne Videos bleiben die Spalten reine
Meldungsspalten. Im HTML steht kein iframe und keine Adresse von YouTube außer
dem Link „auf YouTube öffnen“; erst ein Klick im Chromium setzt das iframe
von youtube-nocookie.com, alle fremden Anfragen werden abgefangen. Feste Tage.
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import json
import re
import threading
from datetime import date
from pathlib import Path

import pytest
from bestand_pfad import verlinke_neben_data
from bs4 import BeautifulSoup

from telco_radar.analyze import ki_videos
from telco_radar.collect import youtube_api
from telco_radar.config import load_config
from telco_radar.report.html import render_site

WURZEL = Path(__file__).resolve().parents[1]
FIXTURES = WURZEL / "tests" / "fixtures" / "ki"
HEUTE = date(2026, 10, 11)
GESTERN = date(2026, 10, 10)
KURZ = {"VID00000091", "VID00000092", "VID00000093"}
KATALOG = [
    {"name": "c't 3003", "stufe": "Einstieg", "sprache": "de"},
    {"name": "Everlast AI", "stufe": "Fortgeschritten", "sprache": "de"},
]


def _video(nr: int, sekunden: int | None, tag: int) -> dict:
    return {
        "id": f"VID{nr:08d}",
        "titel": f"Video Nummer {nr}",
        "datum": f"2026-10-{tag:02d}",
        "dauer_sekunden": sekunden,
    }


def _lange_und_kurze() -> list[dict]:
    lange = [_video(nr, 600 + nr, 11 - nr % 10) for nr in range(1, 11)]
    kurz = [_video(91, 45, 10), _video(92, 119, 10), _video(93, None, 10)]
    return lange + kurz


def _store(state: Path, abrufe: list[tuple[dict, date]]) -> dict:
    store: dict = {}
    for abruf, tag in abrufe:
        store = ki_videos.aktualisiere(state, KATALOG, abruf, tag)
    return store


def _abruf(videos: list[dict], kanal: str = "c't 3003") -> dict:
    return {"kanaele": {kanal: {"videos": videos}}}


def _render(
    tmp_path: Path,
    abrufe: list[tuple[dict, date]] | None,
    bilder: dict[str, bool] | None = None,
) -> BeautifulSoup:
    root = tmp_path / "repo"
    berichte = root / "data" / "reports"
    berichte.mkdir(parents=True)
    verlinke_neben_data(root)
    meldungen = [
        {
            "url": f"https://example.org/ki-anbieter/m{nr}",
            "title": f"Sprachmodell Nummer {nr} vorgestellt",
            "summary": "Ein Anbieter zeigt ein neues Modell.",
            "source": "Beispielquelle",
            "date": f"2026-10-{10 - nr % 9:02d}",
            "relevance": 3,
            "category": "Netz/Technologie",
        }
        for nr in range(1, 11)
    ]
    bericht = {
        "date": "2026-10-10",
        "regions": {"KI-Anbieter": {"highlights": meldungen}},
    }
    (berichte / "2026-10-10.json").write_text(json.dumps(bericht), encoding="utf-8")
    if abrufe is not None:
        _store(root / "data" / "state", abrufe)
    site = tmp_path / "site"
    if bilder is not None:
        _lege_bilder_ab(root / "data" / "state", bilder, site)
    render_site(site, berichte, load_config(root))
    return BeautifulSoup((site / "ki.html").read_text(encoding="utf-8"), "html.parser")


def _ids(teil) -> list[str]:
    return [b["data-ki-video"] for b in teil.select("[data-ki-video]")]


def _text(teil) -> str:
    return " ".join(teil.get_text(" ").split())


def test_verteilung_eins_links_eins_rechts_sechs_in_der_reihe(tmp_path):
    seite = _render(tmp_path, [(_abruf(_lange_und_kurze()), HEUTE)])
    lange = [
        v["id"] for v in ki_videos.lade(tmp_path / "repo" / "data" / "state")["videos"]
    ]
    lange = [i for i in lange if i not in KURZ]
    assert _ids(seite.select_one(".ki-links")) == lange[:1]
    assert _ids(seite.select_one(".ki-rechts")) == lange[1:2]
    reihe = seite.select_one("#ki-videos")
    assert _ids(reihe) == lange[2:8]
    alle = _ids(seite)
    assert sorted(alle) == sorted(lange[:8])
    assert len(alle) == len(set(alle)) == 8
    rechts = seite.select_one(".ki-rechts").find_all("article", recursive=False)
    assert "ki-meldung" in rechts[0]["class"] and "ki-video--mini" in rechts[1]["class"]
    links = seite.select_one(".ki-links").find_all("article", recursive=False)
    assert "ki-video--gross" in links[0]["class"]
    assert len(links) == 3


def test_reihe_steht_nach_dem_ressort_kapitel_unter_dem_kopf(tmp_path):
    seite = _render(tmp_path, [(_abruf(_lange_und_kurze()), HEUTE)])
    blatt = str(seite.select_one("#meldungen"))
    assert blatt.index('class="ki-oben"') < blatt.index('id="ressort-modelle"')
    assert blatt.index('id="ressort-modelle"') < blatt.index('id="ki-videos"')
    assert len(seite.select("#meldungen .ki-ressort")) == 1
    titel = seite.select_one("#ki-videos h2")
    assert _text(titel) == "Videos · was man mit KI bauen kann"


def test_kicker_quelle_und_dauer_aus_dem_store(tmp_path):
    videos = [_video(1, 847, 9), _video(2, 3725, 8)]
    seite = _render(tmp_path, [(_abruf(videos), HEUTE)])
    gross = seite.select_one(".ki-links .ki-video")
    assert _text(gross.select_one(".ki-zeit")) == "14:07"
    assert _text(gross.select_one(".ki-kicker")) == "Video · Einstieg"
    assert _text(gross.select_one(".ki-video-titel")) == "Video Nummer 1"
    assert _text(gross.select_one(".ki-wer")).startswith("c't 3003 · 14 Minuten")
    mini = seite.select_one(".ki-rechts .ki-video")
    assert _text(mini.select_one(".ki-zeit")) == "62:05"
    assert "62 Minuten" in _text(mini)
    assert "Video · Einstieg" in _text(mini)


def test_kurze_videos_fallen_weg():
    store = {"videos": _lange_und_kurze()}
    ids = [v["id"] for v in ki_videos.lange(store)]
    assert "VID00000091" not in ids and "VID00000092" not in ids
    assert "VID00000093" not in ids
    assert len(ids) == 10
    grenze = {"videos": [_video(5, ki_videos.KURZ_UNTER_SEKUNDEN, 9)]}
    assert [v["id"] for v in ki_videos.lange(grenze)] == ["VID00000005"]
    assert ki_videos.KURZ_UNTER_SEKUNDEN == 120


def test_ohne_store_reine_meldungsspalten_und_ausfallzeile(tmp_path):
    seite = _render(tmp_path, None)
    assert _ids(seite) == []
    assert seite.select(".ki-links .ki-video, .ki-rechts .ki-video") == []
    assert len(seite.select_one(".ki-links").find_all("article")) == 2
    zeile = seite.select_one("#ki-videos .ki-video-ausfall")
    assert _text(zeile) == "Videos nicht abgerufen: noch kein Abruf"


def test_fehlender_schluessel_steht_mit_grund_in_der_reihe(tmp_path):
    abruf = {"error": youtube_api.OHNE_SCHLUESSEL}
    seite = _render(tmp_path, [(abruf, HEUTE)])
    assert _ids(seite) == []
    assert seite.select(".ki-oben .ki-video") == []
    zeile = _text(seite.select_one("#ki-videos .ki-video-ausfall"))
    assert zeile == "Videos nicht abgerufen: YouTube-Schlüssel fehlt"


def test_ausfall_nach_erfolg_nennt_den_stand_und_laesst_die_alten_videos(tmp_path):
    videos = [_video(1, 847, 9), _video(2, 900, 8), _video(3, 950, 7)]
    abrufe = [(_abruf(videos), GESTERN), ({"error": "HTTP 403 quotaExceeded"}, HEUTE)]
    seite = _render(tmp_path, abrufe)
    zeile = _text(seite.select_one("#ki-videos .ki-video-ausfall"))
    assert zeile == "Videos nicht abgerufen: HTTP 403 quotaExceeded · Stand 10.10.2026"
    assert _ids(seite) == ["VID00000001", "VID00000002", "VID00000003"]


def test_ohne_ausfall_keine_ausfallzeile(tmp_path):
    seite = _render(tmp_path, [(_abruf(_lange_und_kurze()), HEUTE)])
    assert seite.select(".ki-video-ausfall") == []


def test_store_ueber_den_parser_aus_den_fixtures(tmp_path):
    liste = youtube_api.uploads(
        json.loads(
            (FIXTURES / "youtube-playlistitems.json").read_text(encoding="utf-8")
        )
    )
    dauer = youtube_api.dauern(
        json.loads((FIXTURES / "youtube-videos.json").read_text(encoding="utf-8"))
    )
    videos = [dict(v, dauer_sekunden=dauer[v["id"]]) for v in liste if v["id"] in dauer]
    seite = _render(tmp_path, [(_abruf(videos), HEUTE)])
    assert _ids(seite.select_one(".ki-links")) == ["TEST0000001"]
    assert _ids(seite.select_one(".ki-rechts")) == ["TEST0000002"]
    assert "TEST0000004" not in _ids(seite)
    assert _text(seite.select_one(".ki-links .ki-video-titel")) == (
        "Eigenen KI-Agenten bauen – so geht's"
    )


def test_kein_iframe_und_keine_youtube_adresse_ausser_dem_link(tmp_path):
    seite = _render(tmp_path, [(_abruf(_lange_und_kurze()), HEUTE)])
    roh = str(seite)
    assert "<iframe" not in roh
    assert "ytimg" not in roh and "youtube-nocookie" not in roh
    adressen = re.findall(r"https?://[^\"'\s<>]*youtu[^\"'\s<>]*", roh)
    links = seite.select('a[href*="youtu"]')
    assert len(adressen) == len(links) == 8
    for a in links:
        vid = a.find_parent("article").select_one("[data-ki-video]")["data-ki-video"]
        assert a["href"] == f"https://www.youtube.com/watch?v={vid}"
        assert _text(a) == "auf YouTube öffnen"


class _Stumm(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    tmp = tmp_path_factory.mktemp("ki-videos")
    _render(tmp, [(_abruf(_lange_und_kurze()), HEUTE)])
    return tmp / "site"


@contextlib.contextmanager
def _seite(chromium, wurzel: Path, breite: int = 1440):
    handler = functools.partial(_Stumm, directory=str(wurzel))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    kontext = chromium.new_context(viewport={"width": breite, "height": 900})
    fremd: list[str] = []

    def abfangen(route):
        if route.request.url.startswith("http://127.0.0.1:"):
            route.continue_()
        else:
            fremd.append(route.request.url)
            route.abort()

    try:
        kontext.route("**/*", abfangen)
        page = kontext.new_page()
        page.goto(
            f"http://127.0.0.1:{httpd.server_address[1]}/ki.html", wait_until="load"
        )
        page.wait_for_timeout(150)
        yield page, fremd
    finally:
        kontext.close()
        httpd.shutdown()


RAHMEN = (
    "[...document.querySelectorAll('iframe')].map(f => [f.getAttribute('src'),"
    " f.getAttribute('allow'), f.hasAttribute('allowfullscreen'),"
    " Math.round(f.getBoundingClientRect().width)])"
)


def test_klick_auf_den_player_setzt_das_iframe_von_youtube_nocookie(chromium, site):
    with _seite(chromium, site) as (page, fremd):
        vorher = page.evaluate(RAHMEN)
        fremd_vorher = list(fremd)
        vid = page.get_attribute(".ki-links [data-ki-video]", "data-ki-video")
        page.click(".ki-links [data-ki-video]")
        page.wait_for_timeout(100)
        nachher = page.evaluate(RAHMEN)
        knopf = page.evaluate(
            "document.querySelectorAll('.ki-links [data-ki-video]').length"
        )
    assert vorher == [] and fremd_vorher == []
    assert len(nachher) == 1
    src, allow, voll, breite = nachher[0]
    assert src == f"https://www.youtube-nocookie.com/embed/{vid}?autoplay=1&rel=0"
    assert allow == "autoplay; encrypted-media; picture-in-picture"
    assert voll is True and breite > 200
    assert knopf == 0
    assert all("youtube-nocookie.com" in u for u in fremd)


def test_mini_video_spielt_in_voller_spaltenbreite(chromium, site):
    with _seite(chromium, site) as (page, _):
        mini = page.evaluate(
            "Math.round(document.querySelector('.ki-rechts [data-ki-video]')"
            ".getBoundingClientRect().width)"
        )
        page.click(".ki-rechts [data-ki-video]")
        page.wait_for_timeout(100)
        breite = page.evaluate(
            "Math.round(document.querySelector('.ki-rechts iframe')"
            ".getBoundingClientRect().width)"
        )
    assert mini == 96
    assert breite > 200


def test_am_handy_kein_ueberlauf_und_die_reihe_zum_wischen(chromium, site):
    with _seite(chromium, site, breite=390) as (page, _):
        lage = page.evaluate(
            "(() => { const r = document.querySelector('#ki-videos .ki-videos');"
            " const v = [...r.querySelectorAll('.ki-video')];"
            " return [document.documentElement.scrollWidth <= innerWidth,"
            " new Set(v.map(e => Math.round(e.getBoundingClientRect().top))).size,"
            " v.length, r.scrollWidth > r.clientWidth,"
            " v.every(e => e.getBoundingClientRect().width >= 250)]; })()"
        )
    assert lage == [True, 1, 6, True, True]


def _lege_bilder_ab(state: Path, mit_datei: dict[str, bool], site: Path) -> None:
    """``bild`` je Video im Store; die Datei nur, wo ``True``; dazu eine Altlast."""
    from PIL import Image

    ordner = ki_videos.bildordner(state)
    ordner.mkdir(parents=True, exist_ok=True)
    for vid, datei in mit_datei.items():
        if datei:
            Image.new("RGB", (960, 540), (30, 90, 160)).save(ordner / f"{vid}.jpg")
    ki_videos.setze_bilder(state, {vid: f"{vid}.jpg" for vid in mit_datei})
    altlast = site / "images" / "ki-videos" / "WEG00000001.jpg"
    altlast.parent.mkdir(parents=True)
    altlast.write_bytes(b"alt")


def test_vorschaubild_kommt_aus_der_eigenen_site_nie_von_youtube(tmp_path):
    bilder = {"VID00000001": True, "VID00000002": True, "VID00000003": False}
    seite = _render(tmp_path, [(_abruf(_lange_und_kurze()), HEUTE)], bilder)
    site = tmp_path / "site"
    standbilder = {
        b["data-ki-video"]: b.select_one("img.ki-standbild")
        for b in seite.select(".ki-player[data-ki-video]")
    }
    mit_bild = {vid for vid, img in standbilder.items() if img is not None}
    assert mit_bild == {"VID00000001", "VID00000002"}
    for vid in mit_bild:
        img = standbilder[vid]
        assert img["src"] == f"images/ki-videos/{vid}.jpg"
        assert img["alt"] == "" and img["loading"] == "lazy"
        assert (site / img["src"]).is_file()
        knopf = img.find_parent("button")
        assert knopf.select_one(".ki-knopf") and knopf.select_one(".ki-zeit")
        assert knopf.select("svg") == []
    for img in seite.select("img"):
        assert "ytimg" not in img["src"] and "youtu" not in img["src"]
    assert "ytimg" not in str(seite)
    ohne = standbilder.keys() - mit_bild
    assert "VID00000003" in ohne
    for vid in ohne:
        assert seite.select_one(f'[data-ki-video="{vid}"] svg') is not None
    ausgeliefert = sorted(p.name for p in (site / "images" / "ki-videos").iterdir())
    assert ausgeliefert == ["VID00000001.jpg", "VID00000002.jpg"]


def test_ohne_bilder_bleibt_das_gezeichnete_standbild(tmp_path):
    seite = _render(tmp_path, [(_abruf(_lange_und_kurze()), HEUTE)], {})
    assert seite.select(".ki-player img") == []
    knoepfe = seite.select(".ki-player[data-ki-video]")
    assert len(knoepfe) == 8 and all(b.select_one("svg") for b in knoepfe)
    assert list((tmp_path / "site" / "images" / "ki-videos").iterdir()) == []


BILDLAGE = (
    "(() => { const i = document.querySelector('.ki-links img.ki-standbild');"
    " const b = i.closest('button').getBoundingClientRect();"
    " const r = i.getBoundingClientRect();"
    " const k = document.querySelector('.ki-links .ki-knopf');"
    " k.scrollIntoView({block: 'center'}); const m = k.getBoundingClientRect();"
    " const oben = document.elementFromPoint(m.x + m.width / 2, m.y + m.height / 2);"
    " return [i.naturalWidth, Math.round(r.width) === Math.round(b.width),"
    " Math.round(r.height) === Math.round(b.height), k === oben]; })()"
)


def test_vorschaubild_laedt_im_chromium_ohne_fremde_anfrage(chromium, tmp_path):
    abrufe = [(_abruf(_lange_und_kurze()), HEUTE)]
    _render(tmp_path, abrufe, {"VID00000010": True})
    with _seite(chromium, tmp_path / "site") as (page, fremd):
        page.wait_for_function(
            "document.querySelector('.ki-links img.ki-standbild').complete"
        )
        lage = page.evaluate(BILDLAGE)
    assert fremd == []
    assert lage == [960, True, True, True]
