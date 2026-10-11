"""Themenfeld ki: deutsche Fachpresse und Start-up-Quellen, keine gesperrten.

Die KI-Seite braucht neben den Herstellerfeeds deutschsprachige Fachpresse
(Lesende ohne Technik-Hintergrund) und eine Quelle fuer Start-ups und Geld.
The Decoder und YouTube-RSS sperren den Abruf per robots.txt und duerfen nie
hineinkommen.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from telco_radar.config import THEME_PREFIX, load_config

ROOT = Path(__file__).resolve().parents[1]
KI = THEME_PREFIX + "ki"
DEUTSCHE_FACHPRESSE = frozenset({"heise.de", "t3n.de", "golem.de"})
START_UP_PRESSE = frozenset({"techcrunch.com"})
SPERRLISTE = ("the-decoder.de", "youtube.com/feeds")
MIN_DEUTSCH = 2
MIN_START_UP = 1


def _host(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    teile = host.split(".")
    return ".".join(teile[-2:])


def _ki_urls() -> list[str]:
    cfg = load_config(ROOT)
    return [s.url for s in cfg.tech_sources if s.theme == KI]


def _treffer(urls: list[str], hosts: frozenset[str]) -> set[str]:
    return {_host(u) for u in urls} & hosts


def test_ki_hat_deutsche_fachpresse():
    assert len(_treffer(_ki_urls(), DEUTSCHE_FACHPRESSE)) >= MIN_DEUTSCH


def test_ki_hat_start_up_quelle():
    assert len(_treffer(_ki_urls(), START_UP_PRESSE)) >= MIN_START_UP


def test_ki_ohne_gesperrte_quellen():
    urls = _ki_urls()
    assert urls
    gesperrt = [u for u in urls if any(s in u.lower() for s in SPERRLISTE)]
    assert gesperrt == []


def test_gegenprobe_zaehlung_erkennt_fremde_und_gesperrte_quellen():
    fremd = [
        "https://openai.com/news/rss.xml",
        "https://www.heise.de/thema/Kuenstliche-Intelligenz.xml",
        "https://www.heise.de/rss/heise-atom.xml",
    ]
    assert _treffer(fremd, DEUTSCHE_FACHPRESSE) == {"heise.de"}
    assert _treffer(fremd, START_UP_PRESSE) == set()
    gesperrt = [
        "https://the-decoder.de/feed/",
        "https://www.youtube.com/feeds/videos.xml?channel_id=x",
    ]
    assert all(any(s in u for s in SPERRLISTE) for u in gesperrt)
