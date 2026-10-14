"""Die KI-Meldungen als Zeitung in Ressort-Kapiteln (Antonio, 13.10.2026).

Unter dem Kopf der KI-Seite steht je Ressort mit Meldung ein Kapitel: ein
eigenes Bild ``static/bilder/ki-<schluessel>.jpg`` mit dem Ressortnamen
darauf, darunter genau ein Aufmacher groß, daneben höchstens
``NEBEN_JE_KAPITEL`` kleinere; der Rest steht zugeklappt. Kein Bild kommt
von einer fremden Seite, kein Satz erklärt das Zeitungsprinzip, die
Videoreihe steht zwischen den Kapiteln. Im Chromium bei 390 und 1440 px:
kein seitlicher Überlauf, keine zwei Textblöcke eines Kapitels übereinander,
der Name liegt im Bild, sichtbar sind höchstens 1 + ``NEBEN_JE_KAPITEL``
Meldungen je Kapitel, die Schlagzeile des Aufmachers ist die größte ihres
Kapitels. Gegenprobe: aufgeklappt zeigt das Kapitel auch die weiteren.
``FOLGE`` nennt Ressort, Titel und Anzahl: der Kopf nimmt die acht
neuesten (Produkte), Chips und Start-ups bleiben leer, Modelle hat zwei
über dem Deckel.
Feste Tage, kein heute.
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import json
import threading
from datetime import date, timedelta
from pathlib import Path

import pytest
from bestand_pfad import verlinke_neben_data
from bs4 import BeautifulSoup

from telco_radar.analyze import ki_blatt
from telco_radar.config import load_config
from telco_radar.report import ki_seite
from telco_radar.report.html import render_site

ANFANG = date(2026, 8, 1)
OBEN = 1 + ki_seite.LINKS + ki_seite.RECHTS
SICHTBAR = 1 + ki_blatt.NEBEN_JE_KAPITEL
FOLGE = (
    ("Forschung", "Forscher zeigen neue Studie Nummer {i}", 1),
    ("Regeln & Recht", "EU verschärft Regeln Nummer {i}", 2),
    ("Modelle", "Neues Sprachmodell Nummer {i} vorgestellt", SICHTBAR + 2),
    ("KI im Mobilfunk", "Operators test AI in the RAN, round {i}", 3),
    ("Produkte", "Neue App fasst E-Mails zusammen, Folge {i}", OBEN),
)
ERWARTET = ["mobilfunk", "modelle", "regeln", "forschung"]


def _highlights() -> list[dict]:
    out = []
    i = 0
    for _, titel, anzahl in FOLGE:
        for _ in range(anzahl):
            out.append(
                {
                    "url": f"https://example.org/ki-anbieter/{i}",
                    "title": titel.format(i=i),
                    "summary": f"Kurztext zur Meldung {i} mit etwas mehr Inhalt.",
                    "source": "Beispielquelle",
                    "date": (ANFANG + timedelta(days=i)).isoformat(),
                    "relevance": 3,
                    "category": "Netz/Technologie",
                }
            )
            i += 1
    return out


def _baue(tmp: Path) -> Path:
    root = tmp / "repo"
    berichte = root / "data" / "reports"
    berichte.mkdir(parents=True)
    verlinke_neben_data(root)
    bericht = {
        "date": "2026-10-09",
        "regions": {"KI-Anbieter": {"highlights": _highlights()}},
    }
    (berichte / "2026-10-09.json").write_text(json.dumps(bericht), encoding="utf-8")
    site = tmp / "site"
    render_site(site, berichte, load_config(root))
    return site


def _render(tmp: Path) -> BeautifulSoup:
    html = (_baue(tmp) / "ki.html").read_text(encoding="utf-8")
    return BeautifulSoup(html, "html.parser")


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    return _baue(tmp_path_factory.mktemp("ki-kapitel"))


@pytest.fixture(scope="module")
def seite(site) -> BeautifulSoup:
    return BeautifulSoup((site / "ki.html").read_text(encoding="utf-8"), "html.parser")


def _kapitel(seite):
    return seite.select("#meldungen .ki-ressort")


def test_kapitel_in_fester_folge_leere_ressorts_entfallen(seite):
    assert [k["id"] for k in _kapitel(seite)] == [f"ressort-{s}" for s in ERWARTET]
    namen = [
        k.select_one("h2.ki-ressort-titel").get_text(strip=True)
        for k in _kapitel(seite)
    ]
    assert namen == ["KI im Mobilfunk", "Modelle", "Regeln & Recht", "Forschung"]


def test_je_kapitel_genau_ein_eigenes_bild_aus_dem_eigenen_ordner(site, seite):
    pfade = []
    for kapitel, schluessel in zip(_kapitel(seite), ERWARTET, strict=True):
        bilder = kapitel.select("img")
        assert len(bilder) == 1
        assert kapitel.select_one(".ki-ressort-bild img") is bilder[0]
        src = bilder[0]["src"]
        assert src == f"static/bilder/ki-{schluessel}.jpg"
        assert (site / src).is_file()
        assert bilder[0]["loading"] == "lazy"
        assert bilder[0]["width"] and bilder[0]["height"]
        pfade.append(src)
    assert len(set(pfade)) == len(pfade)


def test_kein_fremdes_bild_im_meldungsteil(seite):
    teil = seite.select_one("#meldungen")
    quellen = [i["src"] for i in teil.select("img")]
    quellen += [
        q.split()[0] for i in teil.select("img[srcset]") for q in i["srcset"].split(",")
    ]
    assert quellen
    assert all(q.startswith("static/bilder/") for q in quellen), quellen
    assert "og:image" not in str(teil) and "/images/" not in str(teil)


def test_je_kapitel_ein_aufmacher_hoechstens_drei_daneben_rest_zugeklappt(seite):
    for kapitel in _kapitel(seite):
        kopf = kapitel.select(".ki-meldung--kopf")
        assert len(kopf) == 1
        assert kopf[0].select_one(".ki-dek")
        neben = kapitel.select(".ki-ressort-neben .ki-meldung")
        assert len(neben) <= ki_blatt.NEBEN_JE_KAPITEL
        offen = [
            a
            for a in kapitel.select("article.ki-meldung")
            if not a.find_parent("details")
        ]
        assert len(offen) <= SICHTBAR
        for details in kapitel.select("details"):
            assert not details.has_attr("open")
    modelle = seite.select_one("#ressort-modelle")
    weitere = modelle.select("details.ki-ressort-weitere article.ki-meldung")
    assert len(weitere) == 2
    assert modelle.select_one("details summary").get_text(" ", strip=True) == (
        "Weitere 2 aus Modelle"
    )
    assert not seite.select_one("#ressort-forschung details")


def test_aufmacher_des_kapitels_ist_die_neueste_meldung_des_ressorts(seite):
    modelle = seite.select_one("#ressort-modelle")
    links = [a.select_one(".ki-schlag a")["href"] for a in modelle.select("article")]
    nummern = [int(h.rsplit("/", 1)[1]) for h in links]
    assert nummern == sorted(nummern, reverse=True)
    assert nummern[0] == 3 + SICHTBAR + 2 - 1


def test_kein_erklaersatz_und_videos_zwischen_den_kapiteln(seite):
    text = seite.select_one("#meldungen").get_text(" ")
    assert "wie in einer Zeitung" not in text
    assert "wandert ins Archiv" not in text
    assert not seite.select(".ki-mehr, .ki-liste")
    blatt = str(seite.select_one("#meldungen"))
    stellen = [blatt.index(f'id="ressort-{s}"') for s in ERWARTET]
    videos = blatt.index('id="ki-videos"')
    assert blatt.index('class="ki-oben"') < stellen[0]
    assert (
        stellen[ki_seite.VIDEOS_NACH_KAPITEL - 1]
        < videos
        < stellen[ki_seite.VIDEOS_NACH_KAPITEL]
    )


def test_rubrik_zaehlt_weiter_alle_meldungen_im_blatt(seite):
    zahl = seite.select_one('#ki-rubriken a[href="#meldungen"] b').get_text()
    assert int(zahl) == len(seite.select("#meldungen article.ki-meldung"))
    assert int(zahl) == sum(n for _, _, n in FOLGE)


class _Stumm(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@contextlib.contextmanager
def _browser_seite(chromium, wurzel: Path, breite: int):
    handler = functools.partial(_Stumm, directory=str(wurzel))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    kontext = chromium.new_context(viewport={"width": breite, "height": 844})
    try:
        page = kontext.new_page()
        page.goto(
            f"http://127.0.0.1:{httpd.server_address[1]}/ki.html", wait_until="load"
        )
        page.evaluate(
            "document.querySelectorAll('.ki-ressort-bild img')"
            ".forEach(i => i.loading = 'eager')"
        )
        page.wait_for_function(
            "[...document.querySelectorAll('.ki-ressort-bild img')]"
            ".every(i => i.complete)"
        )
        yield page
    finally:
        kontext.close()
        httpd.shutdown()


MESSUNG = """() => {
  const sichtbar = e => { const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0
      && e.checkVisibility({visibilityProperty: true}); };
  const box = e => { const r = e.getBoundingClientRect();
    return {l: r.left, r: r.right, o: r.top + scrollY, u: r.bottom + scrollY}; };
  return [...document.querySelectorAll('#meldungen .ki-ressort')].map(k => {
    const bild = k.querySelector('.ki-ressort-bild');
    const teile = '.ki-ressort-bild, .ki-schlag, .ki-dek, .ki-wer, summary';
    const texte = [...k.querySelectorAll(teile)]
      .filter(sichtbar).map(e => ({wer: e.className || e.tagName, ...box(e)}));
    const schrift = e => parseFloat(getComputedStyle(e).fontSize);
    return {
      id: k.id,
      bild: box(bild),
      titel: box(k.querySelector('.ki-ressort-titel')),
      geladen: k.querySelector('.ki-ressort-bild img').naturalWidth,
      sichtbar: [...k.querySelectorAll('article.ki-meldung')].filter(sichtbar).length,
      kopf: schrift(k.querySelector('.ki-meldung--kopf .ki-schlag')),
      kopf_box: box(k.querySelector('.ki-meldung--kopf')),
      andere: [...k.querySelectorAll('.ki-ressort-neben .ki-schlag')].map(schrift),
      texte,
    };
  });
}"""


def _ueberdeckt(a: dict, b: dict) -> bool:
    return min(a["r"], b["r"]) - max(a["l"], b["l"]) > 1 and (
        min(a["u"], b["u"]) - max(a["o"], b["o"]) > 1
    )


@pytest.mark.parametrize("breite", [390, 1440])
def test_kapitel_im_chromium_ohne_ueberlauf_und_ohne_ueberdeckung(
    chromium, site, breite
):
    with _browser_seite(chromium, site, breite) as page:
        ueberlauf = page.evaluate(
            "document.documentElement.scrollWidth"
            " - document.documentElement.clientWidth"
        )
        kapitel = page.evaluate(MESSUNG)
    assert ueberlauf <= 0
    assert [k["id"] for k in kapitel] == [f"ressort-{s}" for s in ERWARTET]
    for k in kapitel:
        assert k["geladen"] > 0, k["id"]
        assert 1 <= k["sichtbar"] <= SICHTBAR, k["id"]
        assert all(k["kopf"] > s for s in k["andere"]), k["id"]
        b, t = k["bild"], k["titel"]
        assert (
            b["l"] <= t["l"]
            and t["r"] <= b["r"]
            and b["o"] <= t["o"]
            and t["u"] <= b["u"]
        )
        if breite < 760:
            assert b["r"] - b["l"] >= breite * 0.75, k["id"]
            assert b["u"] - b["o"] <= 844 * 0.4, k["id"]
        else:
            assert b["r"] - b["l"] <= breite * 0.34, k["id"]
            assert abs(b["o"] - k["kopf_box"]["o"]) < 40, k["id"]
            assert k["kopf_box"]["l"] >= b["r"], k["id"]
        texte = k["texte"]
        for i, a in enumerate(texte):
            for c in texte[i + 1 :]:
                assert not _ueberdeckt(a, c), (k["id"], a, c)


def test_gegenprobe_aufgeklappt_zeigt_das_kapitel_die_weiteren(chromium, site):
    with _browser_seite(chromium, site, 1440) as page:
        page.click("#ressort-modelle details summary")
        kapitel = {k["id"]: k for k in page.evaluate(MESSUNG)}
    assert kapitel["ressort-modelle"]["sichtbar"] == SICHTBAR + 2
    assert kapitel["ressort-mobilfunk"]["sichtbar"] == 3


def test_gegenprobe_videos_folgen_der_konstante(tmp_path, monkeypatch):
    monkeypatch.setattr(ki_seite, "VIDEOS_NACH_KAPITEL", 3)
    blatt = str(_render(tmp_path).select_one("#meldungen"))
    stellen = [blatt.index(f'id="ressort-{s}"') for s in ERWARTET]
    assert stellen[2] < blatt.index('id="ki-videos"') < stellen[3]
