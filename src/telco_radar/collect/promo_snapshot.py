"""Snapshot-diff collector for consumer promo/Aktionen pages.

Unlike press RSS/newsroom sources - where every article is a discrete, dated
signal that a seen-store can dedupe - a promo page such as o2online.de/deals
is a live, UNDATED snapshot of whatever campaign happens to be running right
now. There is no article list to diff against data/state/seen.jsonl.

Instead this collector:
  1. fetches the page (plain HTTP via collect/http.py, or a headless Chromium
     render via collect/newsroom_js.py for JS-rendered brands - reusing the
     exact same fetch/render primitives as the press collectors, not a
     bespoke fetcher per brand),
  2. extracts the visible text of the page (script/style/nav/footer/forms
     stripped) so boilerplate does not dominate the diff or the LLM prompt,
  3. hashes that text and compares it against the hash stored for this brand
     in data/state/promo_snapshots.json (analyze/promo_store.SnapshotStore),
  4. the caller (promo_pipeline.run_promo_stage) only sends the text to the
     LLM extractor when the hash changed since the previous run.

A failing/unreachable source never aborts the run - same resilience
contract as rss.py/newsroom.py/newsroom_js.py: the caller catches and logs.
"""
from __future__ import annotations

import hashlib
import logging
import re

from bs4 import BeautifulSoup

from .http import fetch, BROWSER_UA
from .newsroom_js import render_html

log = logging.getLogger(__name__)

_STRIP_TAGS = ("script", "style", "noscript", "svg", "nav", "footer", "header",
               "form", "iframe")
_WS_RE = re.compile(r"[ \t]+")
_BLANK_RE = re.compile(r"\n{3,}")


def extract_text(html: str, max_chars: int = 12000) -> str:
    """Visible main-content text: strip boilerplate tags, collapse whitespace.

    Deliberately simple (no readability/main-content heuristics beyond tag
    stripping): promo pages vary too much in structure to hand-tune a
    selector per brand, and the LLM extraction step is instructed to ignore
    leftover navigation text rather than relying on perfect extraction here.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()
    text = soup.get_text("\n")
    lines = [_WS_RE.sub(" ", ln).strip() for ln in text.splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    text = _BLANK_RE.sub("\n\n", text)
    return text[:max_chars]


def fetch_snapshot(url: str, kind: str, http_cfg: dict) -> str:
    """Fetch *url* and return its extracted visible text. Raises on failure -
    the caller is responsible for catching and recording it as a source
    failure, exactly like the other collectors."""
    if kind == "js":
        timeout_s = float(http_cfg.get("render_timeout_seconds",
                                        http_cfg.get("timeout_seconds", 25)))
        ua = http_cfg.get("user_agent", BROWSER_UA)
        html = render_html(url, timeout_s, ua)
    else:
        resp = fetch(url, http_cfg)
        html = resp.text
    return extract_text(html)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
