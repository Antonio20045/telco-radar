"""Muster-Prompts der KI-Seite (Pitch 9, Schnitt 13).

Die Prompts stehen redaktionell in ``content/ki/muster-prompts.json`` (Liste von
[Thema, [[Titel, Text], …]]), geladen über ``analyze.ki_inhalte``. Kopfzeile,
Themenzeile und Rubrikleiste zählen dieselben Daten; alle Prompts stehen im
ausgelieferten HTML. Gegenproben: eine Datei mit 27 Prompts ergibt „27“, eine
fehlende oder kaputte Datei eine benannte Ausfallzeile statt eines leeren
Abschnitts. Im Chromium zeigt ein Klick auf ein Thema nur dessen Titel, und
„Kopieren“ legt den angezeigten Text in die Zwischenablage. Feste Tage.
"""

from __future__ import annotations

import contextlib
import functools
import html as html_mod
import http.server
import json
import re
import threading
from pathlib import Path

import pytest

from telco_radar.analyze import ki_inhalte
from telco_radar.config import load_config
from telco_radar.report.html import render_site

WURZEL = Path(__file__).resolve().parents[1]
DATEI = WURZEL / "content" / "ki" / "muster-prompts.json"
TAG = "2026-10-09"


def _echt() -> list:
    return json.loads(DATEI.read_text(encoding="utf-8"))


def _render(tmp_path: Path, prompts: str | None) -> str:
    root = tmp_path / "repo"
    berichte = root / "data" / "reports"
    berichte.mkdir(parents=True)
    (root / "config").symlink_to(WURZEL / "config", target_is_directory=True)
    (root / "content").mkdir()
    (root / "content" / "legal").symlink_to(WURZEL / "content" / "legal")
    (root / "content" / "consent_texts").symlink_to(
        WURZEL / "content" / "consent_texts"
    )
    if prompts is not None:
        (root / "content" / "ki").mkdir()
        (root / "content" / "ki" / "muster-prompts.json").write_text(
            prompts, encoding="utf-8"
        )
    meldung = {
        "url": "https://example.org/ki-anbieter/m1",
        "title": "Neues Sprachmodell vorgestellt",
        "summary": "Ein Anbieter zeigt ein neues Modell.",
        "source": "Beispielquelle",
        "date": TAG,
        "relevance": 3,
        "category": "Netz/Technologie",
    }
    bericht = {"date": TAG, "regions": {"KI-Anbieter": {"highlights": [meldung]}}}
    (berichte / f"{TAG}.json").write_text(json.dumps(bericht), encoding="utf-8")
    site = tmp_path / "site"
    render_site(site, berichte, load_config(root))
    return (site / "ki.html").read_text(encoding="utf-8")


def _abschnitt(html: str) -> str:
    return re.search(r'<section class="ki-prompts".*?</section>', html, re.S).group(0)


def _leiste(html: str) -> dict[str, str]:
    nav = re.search(r'<nav class="ki-rubriken".*?</nav>', html, re.S).group(0)
    return dict(
        (ziel, zahl)
        for ziel, _, zahl in re.findall(r'href="#([a-z]+)">([^<]+)<b>(\d+)</b>', nav)
    )


def _themenzeile(teil: str) -> list[str]:
    zeile = re.search(r'<nav class="ki-p-themen".*?</nav>', teil, re.S).group(0)
    return [html_mod.unescape(t) for t in re.findall(r"<a [^>]*>([^<]+)</a>", zeile)]


def test_loader_liest_28_prompts_in_sechs_themen():
    daten = ki_inhalte.lade_prompts(WURZEL)
    assert daten["error"] is None
    assert daten["anzahl"] == 28
    assert [t["name"] for t in daten["themen"]] == [t for t, _ in _echt()]
    assert [len(t["prompts"]) for t in daten["themen"]] == [1, 3, 9, 5, 8, 2]


def test_seite_zaehlt_kopf_themen_und_leiste_aus_derselben_datei(tmp_path):
    echt = _echt()
    html = _render(tmp_path, DATEI.read_text(encoding="utf-8"))
    teil = _abschnitt(html)
    assert re.search(r"<h2[^>]*>Muster-Prompts</h2>", teil)
    assert "28 zum Kopieren" in teil
    assert _themenzeile(teil) == [f"{t} ({len(p)})" for t, p in echt]
    assert _leiste(html)["prompts"] == "28"
    assert teil.count("<details") == 28
    paare = re.findall(
        r'<summary>([^<]*)</summary><pre class="ki-p-text">([^<]*)</pre>', teil
    )
    assert [(html_mod.unescape(t), html_mod.unescape(x)) for t, x in paare] == [
        (titel, text) for _, prompts in echt for titel, text in prompts
    ]


def test_prompts_stehen_nach_verstehen(tmp_path):
    html = _render(tmp_path, DATEI.read_text(encoding="utf-8"))
    ids = re.findall(r'<section [^>]*id="([a-z]+)"', html)
    assert ids.index("prompts") == ids.index("verstehen") + 1


def test_gegenprobe_27_prompts(tmp_path):
    echt = _echt()
    echt[2][1].pop()
    html = _render(tmp_path, json.dumps(echt, ensure_ascii=False))
    teil = _abschnitt(html)
    assert "27 zum Kopieren" in teil
    assert "28" not in "".join(_themenzeile(teil))
    assert _themenzeile(teil)[2] == "Präsentationen (8)"
    assert _leiste(html)["prompts"] == "27"
    assert teil.count("<details") == 27


@pytest.mark.parametrize("inhalt", [None, "{kaputt", '[["Thema", "kein Prompt"]]'])
def test_fehlende_oder_kaputte_datei_nennt_den_ausfall(tmp_path, inhalt):
    html = _render(tmp_path, inhalt)
    teil = _abschnitt(html)
    assert 'class="ki-p-ausfall"' in teil
    assert "Muster-Prompts nicht geladen" in teil
    assert "content/ki/muster-prompts.json" in teil
    assert "<details" not in teil
    assert "prompts" not in _leiste(html)
    daten = ki_inhalte.lade_prompts(tmp_path / "repo")
    assert daten["anzahl"] is None and daten["error"]


class _Stumm(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    tmp = tmp_path_factory.mktemp("ki-prompts")
    _render(tmp, DATEI.read_text(encoding="utf-8"))
    return tmp / "site"


@contextlib.contextmanager
def _seite(chromium, wurzel: Path, breite: int = 1440, **optionen):
    handler = functools.partial(_Stumm, directory=str(wurzel))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    kontext = chromium.new_context(
        viewport={"width": breite, "height": 800}, **optionen
    )
    try:
        page = kontext.new_page()
        url = f"http://127.0.0.1:{httpd.server_address[1]}"
        page.goto(f"{url}/ki.html", wait_until="load")
        page.wait_for_timeout(200)
        yield page, url
    finally:
        kontext.close()
        httpd.shutdown()


SICHTBARE_TITEL = (
    "[...document.querySelectorAll('#prompts .ki-p-titel')]"
    ".filter(b => b.getBoundingClientRect().height > 0).map(b => b.textContent)"
)


def test_klick_auf_thema_zeigt_nur_dessen_titel(chromium, site):
    echt = _echt()
    with _seite(chromium, site) as (page, _):
        start = page.evaluate(SICHTBARE_TITEL)
        page.click("#prompts .ki-p-themen a:nth-child(3)")
        page.wait_for_timeout(100)
        titel = page.evaluate(SICHTBARE_TITEL)
        an = page.evaluate(
            "[...document.querySelectorAll('#prompts .ki-p-themen a.an')]"
            ".map(a => a.textContent)"
        )
        offen = page.evaluate(
            "[...document.querySelectorAll('#prompts details')]"
            ".filter(d => d.getBoundingClientRect().height > 0).length"
        )
        name = page.evaluate(
            "document.querySelector('#prompts .ki-p-name').textContent"
        )
    assert start == [t for t, _ in echt[0][1]]
    assert titel == [t for t, _ in echt[2][1]]
    assert an == [f"{echt[2][0]} ({len(echt[2][1])})"]
    assert offen == 0
    assert name == echt[2][1][0][0]


def test_ohne_javascript_stehen_alle_themen_untereinander(chromium, site):
    with _seite(chromium, site, java_script_enabled=False) as (page, _):
        gruppen = page.evaluate(
            "[...document.querySelectorAll('#prompts .ki-p-gruppe')]"
            ".filter(g => g.getBoundingClientRect().height > 0).length"
        )
        summaries = page.evaluate(
            "[...document.querySelectorAll('#prompts summary')]"
            ".filter(s => s.getBoundingClientRect().height > 0).length"
        )
    assert gruppen == 6
    assert summaries == 28


def test_kopieren_legt_den_angezeigten_text_in_die_zwischenablage(chromium, site):
    echt = _echt()
    with _seite(chromium, site) as (page, url):
        page.context.grant_permissions(
            ["clipboard-read", "clipboard-write"], origin=url
        )
        page.click("#prompts .ki-p-themen a:nth-child(2)")
        page.click("#prompts .ki-p-titel >> nth=1")
        angezeigt = page.evaluate(
            "document.querySelector('#prompts .ki-p-text').textContent"
        )
        page.click("#prompts .ki-p-kopieren")
        page.wait_for_timeout(150)
        knopf = page.evaluate(
            "[document.querySelector('#prompts .ki-p-kopieren').textContent,"
            " getComputedStyle(document.querySelector('#prompts .ki-p-kopieren'))"
            ".backgroundColor]"
        )
        ablage = page.evaluate("navigator.clipboard.readText()")
    assert angezeigt == echt[1][1][1][1]
    assert ablage == angezeigt
    assert knopf == ["Kopiert", "rgb(230, 0, 0)"]


def test_am_handy_steht_das_panel_unter_dem_gewaehlten_titel(chromium, site):
    with _seite(chromium, site, breite=390) as (page, _):
        page.click("#prompts .ki-p-themen a:nth-child(3)")
        page.click("#prompts .ki-p-titel >> nth=2")
        lage = page.evaluate(
            "(() => { const b = document.querySelectorAll('#prompts .ki-p-titel')[2];"
            " const p = document.querySelector('#prompts .ki-p-panel');"
            " return [b.nextElementSibling === p,"
            " document.documentElement.scrollWidth <= innerWidth]; })()"
        )
    assert lage == [True, True]
