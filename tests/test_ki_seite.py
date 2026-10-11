"""Die KI-Seite (Pitch 9, Schnitt 1): Tab „KI“ und die KI-Meldungen aller Berichte.

KI-Meldung ist, was in der Region „KI-Anbieter“ steht oder beim Titel und
Kurztext das Technikthema „KI / AI“ trägt. Jede URL steht einmal, die neueste
Meldung zuerst, und der Meldungsteil zeigt kein fremdes Foto. Gegenprobe: die
Netzmeldung ohne KI steht nicht auf der Seite. Feste Tage, kein heute.
"""

from __future__ import annotations

import json
import re

from bestand_pfad import verlinke_neben_data

from telco_radar.config import load_config
from telco_radar.report.html import render_site

ALT = "2026-10-02"
NEU = "2026-10-09"
MODELL = "https://example.org/ki-anbieter/neues-modell"
TELEKOM_KI = "https://example.org/europa/telekom-ki-sparen"
NETZ = "https://example.org/europa/glasfaser-ausbau"
AGENTEN = "https://example.org/ki-anbieter/agenten-alt"


def _meldung(url: str, titel: str, datum: str, relevanz: int) -> dict:
    return {
        "url": url,
        "title": titel,
        "summary": titel,
        "source": "Beispielquelle",
        "date": datum,
        "relevance": relevanz,
        "category": "Netz/Technologie",
        "image": "fremd.jpg",
        "image_w": 1600,
        "image_h": 900,
    }


def _bericht(datum: str, regionen: dict[str, list[dict]]) -> dict:
    return {
        "date": datum,
        "regions": {name: {"highlights": hs} for name, hs in regionen.items()},
    }


def _seiten(tmp_path) -> tuple[str, str]:
    root = tmp_path / "repo"
    berichte = root / "data" / "reports"
    berichte.mkdir(parents=True)
    verlinke_neben_data(root)
    alt = _bericht(
        ALT,
        {
            "KI-Anbieter": [
                _meldung(MODELL, "Neues Sprachmodell vorgestellt", ALT, 3),
                _meldung(AGENTEN, "Firma zeigt Werkzeug für Kundenservice", ALT, 4),
            ]
        },
    )
    neu = _bericht(
        NEU,
        {
            "KI-Anbieter": [
                _meldung(MODELL, "Neues Sprachmodell vorgestellt", NEU, 2),
            ],
            "Europa": [
                _meldung(TELEKOM_KI, "Telekom will mit KI Kosten sparen", NEU, 4),
                _meldung(NETZ, "Telekom baut Glasfaser in Bonn aus", NEU, 5),
            ],
        },
    )
    for bericht in (alt, neu):
        datei = berichte / f"{bericht['date']}.json"
        datei.write_text(json.dumps(bericht, ensure_ascii=False), encoding="utf-8")
    site = tmp_path / "site"
    render_site(site, berichte, load_config(root))
    ki = (site / "ki.html").read_text(encoding="utf-8")
    meldungen = (site / "meldungen.html").read_text(encoding="utf-8")
    return ki, meldungen


def _leiste(html: str) -> str:
    return re.search(r'<nav class="subbar[^"]*".*?</nav>', html, re.S).group(0)


def _blatt(html: str) -> str:
    return re.search(r'<section class="ki-blatt".*?</section>', html, re.S).group(0)


def test_leiste_fuehrt_ki_zwischen_promo_und_quellen(tmp_path):
    ki, meldungen = _seiten(tmp_path)
    for html in (ki, meldungen):
        leiste = _leiste(html)
        promo = leiste.index("promo/index.html")
        quellen = leiste.index("transparenz.html")
        assert promo < leiste.index('href="ki.html"') < quellen
    assert 'href="ki.html" class="on" aria-current="page"' in _leiste(ki)


def test_ki_seite_zeigt_nur_ki_meldungen_einmal_und_neueste_zuerst(tmp_path):
    ki, _ = _seiten(tmp_path)
    assert "Kalenderwoche 41" in ki
    assert "Ausgabe vom 9. Oktober 2026" in ki
    blatt = _blatt(ki)
    urls = re.findall(r'class="ki-quelle" href="([^"]+)"', blatt)
    assert urls == [TELEKOM_KI, MODELL, AGENTEN]
    assert NETZ not in blatt
    assert "Glasfaser" not in blatt
    assert "<img" not in blatt
