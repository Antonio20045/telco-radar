"""Die Rubrikleiste der KI-Seite (Pitch 9, Schnitt 8).

Die Leiste nennt je Abschnitt seine Zahl aus demselben Feld wie der Abschnitt:
„Meldungen“ zählt die Meldungen im Blatt, „Modelle“ die Länge der Top-Liste.
Gegenproben: elf statt neun Meldungen ergeben „11“, ohne Store fehlt „Modelle“.
Feste Tage, kein heute.
"""

from __future__ import annotations

import json
import re

from bestand_pfad import verlinke_neben_data

from telco_radar.analyze import ki_modelle
from telco_radar.config import load_config
from telco_radar.report.html import render_site

TAG = "2026-10-09"


def _meldung(i: int) -> dict:
    return {
        "url": f"https://example.org/ki-anbieter/meldung-{i}",
        "title": f"Neues Sprachmodell Nummer {i} vorgestellt",
        "summary": "Ein Anbieter zeigt ein neues Modell.",
        "source": "Beispielquelle",
        "date": TAG,
        "relevance": 3,
        "category": "Netz/Technologie",
    }


def _store(n: int) -> dict:
    return {
        "stand": TAG,
        "top": [
            {
                "platz": i,
                "name": f"Modell {i}",
                "kurz": f"Modell {i}",
                "farbe": "--ki-openai",
            }
            for i in range(1, n + 1)
        ],
        "quellen": {},
    }


def _ki(tmp_path, meldungen: int, store: dict | None) -> str:
    root = tmp_path / "repo"
    berichte = root / "data" / "reports"
    berichte.mkdir(parents=True)
    verlinke_neben_data(root)
    bericht = {
        "date": TAG,
        "regions": {
            "KI-Anbieter": {"highlights": [_meldung(i) for i in range(meldungen)]}
        },
    }
    (berichte / f"{TAG}.json").write_text(json.dumps(bericht), encoding="utf-8")
    if store is not None:
        pfad = root / "data" / "state" / ki_modelle.STORE_NAME
        pfad.parent.mkdir(parents=True)
        pfad.write_text(json.dumps(store), encoding="utf-8")
    site = tmp_path / "site"
    render_site(site, berichte, load_config(root))
    return (site / "ki.html").read_text(encoding="utf-8")


def _leiste(html: str) -> dict[str, str]:
    nav = re.search(r'<nav class="ki-rubriken".*?</nav>', html, re.S).group(0)
    return dict(
        (ziel, zahl)
        for ziel, _, zahl in re.findall(r'href="#([a-z]+)">([^<]+)<b>(\d+)</b>', nav)
    )


def _im_blatt(html: str) -> int:
    blatt = re.search(r'<section class="ki-blatt".*?</section>', html, re.S).group(0)
    return blatt.count('<article class="ki-meldung ')


def test_leiste_zaehlt_meldungen_im_blatt_und_modelle_der_top_liste(tmp_path):
    html = _ki(tmp_path, 9, _store(10))
    assert _leiste(html) == {
        "meldungen": "9",
        "modelle": "10",
        "verstehen": "12",
        "prompts": "28",
    }
    assert _im_blatt(html) == 9
    assert html.count('class="ki-rang-eintrag"') == 10
    assert 'id="meldungen"' in html and 'id="modelle"' in html


def test_gegenprobe_elf_meldungen_und_ohne_store_keine_modelle(tmp_path):
    html = _ki(tmp_path, 11, None)
    assert _leiste(html) == {"meldungen": "11", "verstehen": "12", "prompts": "28"}
    assert _im_blatt(html) == 11


def test_gegenprobe_kuerzere_top_liste(tmp_path):
    html = _ki(tmp_path, 9, _store(7))
    assert _leiste(html)["modelle"] == "7"
