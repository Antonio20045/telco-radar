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
  3. hashes that text (plus a normalised link signature, see content_hash())
     and compares it against the hash stored for this brand in
     data/state/promo_snapshots.json (analyze/promo_store.SnapshotStore),
  4. the caller (promo_pipeline.run_promo_stage) only sends the text to the
     LLM extractor when the hash changed since the previous run.

A failing/unreachable source never aborts the run - same resilience
contract as rss.py/newsroom.py/newsroom_js.py: the caller catches and logs.

Deep links (claude/promo-tiefenlinks-konzept.md): a promo card used to link
to the brand's one configured overview URL for every single offer, because
extract_text() below throws away all <a href> attributes before the page
text ever reaches the LLM - there was no href left to give it. This module
now ALSO returns extract_link_candidates(): same-origin anchors (never an
affiliate/tracking redirect, see the konzept doc Premortem d) with a short
heading-aware context string, so analyze/promo_analyst.py can let the model
pick ONE of these by index (never invent a free-form URL) for the specific
offer it is describing. A brand with no usable candidates (or where nothing
was picked) falls back to the brand's overview URL exactly as before - this
is a strictly additive signal, never a new failure mode.

Separately, capture_hero_image() below takes an actual screenshot of the
brand's promo page for use as the card image on the site (see
promo_images.py + report/promo.py). It is deliberately a SECOND, independent
page load rather than reusing the text-extraction fetch above: the text path
blocks images/fonts/stylesheets for speed (see newsroom_js.render_html),
which is exactly what a screenshot needs loaded to look like anything. The
og:image/twitter:image meta-tag extraction (extract_hero_image) stays as a
lightweight fallback signal - most promo pages simply have no such meta tag,
or one pointing at a generic brand logo, which is the whole reason the
screenshot capture exists.
"""
from __future__ import annotations

import hashlib
import logging
import re
from urllib.parse import (
    parse_qsl, urlencode, urljoin, urlsplit, urlunsplit,
)

from bs4 import BeautifulSoup

from .http import fetch, BROWSER_UA
from .newsroom_js import render_html

log = logging.getLogger(__name__)

# Best-effort cookie-consent dismissal before a screenshot: no CMP is known
# in advance for a given brand site, so we try the selectors of the CMPs
# most common on German/EU sites first (cheap, exact), then fall back to
# text-matching common accept-button wording. A miss here is normal, not an
# error - the screenshot is still useful with a consent banner covering the
# top few hundred pixels of a large clip, just not ideal.
_CONSENT_SELECTORS = (
    "#onetrust-accept-btn-handler",           # OneTrust
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",  # Cookiebot
    '[data-testid="uc-accept-all-button"]',   # Usercentrics
    "._brlbs-btn-accept-all",                 # Borlabs Cookie (viel auf DE-WordPress)
    ".cmpboxbtnyes",                          # consentmanager.net
    ".cm-btn-success",                        # Klaro
)
_CONSENT_TEXTS = (
    "Alle akzeptieren", "Alle Cookies akzeptieren", "Akzeptieren",
    "Zustimmen", "Einverstanden", "Accept all", "I agree",
)
_IMG_VIEWPORT = {"width": 1280, "height": 900}
_IMG_CLIP = {"x": 0, "y": 60, "width": 1280, "height": 720}

_STRIP_TAGS = ("script", "style", "noscript", "svg", "nav", "footer", "header",
               "form", "iframe")
_WS_RE = re.compile(r"[ \t]+")
_BLANK_RE = re.compile(r"\n{3,}")

# Meta tags that commonly carry a page's representative campaign visual, in
# priority order. Deliberately page-level only (one "hero" image per brand
# snapshot) - matching individual offers to individual images on a page we
# do not control would need per-brand selector tuning or vision extraction,
# far more fragile than this one well-supported convention. A missing/failed
# image is never an error: the template falls back to a colour tile.
_IMG_META = (
    ("property", "og:image:secure_url"),
    ("property", "og:image"),
    ("name", "twitter:image"),
    ("name", "twitter:image:src"),
)

# Upper bound on link candidates handed to the LLM per brand: a page can have
# hundreds of anchors, and every candidate costs prompt tokens. 30 is
# generous for the handful of genuinely distinct offers a promo page shows
# (see promo_analyst._MAX_ENTRIES_PER_BRAND=8) while keeping the prompt
# bounded even on a link-heavy page.
_MAX_LINK_CANDIDATES = 30
# Containers whose own text is a reasonable last-resort context for a link
# that has neither useful anchor text nor a nearby heading.
_LINK_CONTAINER_TAGS = ("article", "li", "div", "section")
_SKIP_HREF_PREFIXES = ("#", "javascript:", "mailto:", "tel:")
# Tracking/campaign query params seen on real deep links during the
# promo-tiefenlinks-konzept.md research (ALDI TALK's FF_* funnel tracker,
# generic utm_*). Stripped ONLY for the internal content_hash() signature
# below - the displayed/stored URL keeps these untouched, because they can
# be functional (see the konzept doc Premortem c: O2's own ratenzahlung/
# zielgruppe params are not tracking, they select the actual tariff variant).
_HASH_TRACKING_PARAM_RE = re.compile(r"^(utm_|ff_)", re.I)


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


def extract_hero_image(html: str, base_url: str) -> str | None:
    """Best-effort representative image for the page (og:image/twitter:image
    meta tag), resolved to an absolute URL. Returns None if the page has
    none - that is the normal case for many of these sources, not a bug,
    and callers must treat it as optional."""
    soup = BeautifulSoup(html or "", "html.parser")
    for attr, key in _IMG_META:
        tag = soup.find("meta", attrs={attr: key})
        content = (tag.get("content") or "").strip() if tag else ""
        if content:
            return urljoin(base_url, content)
    return None


def _link_context(a_tag) -> str:
    """Short context string for an anchor: nearest heading in the same
    block, else the anchor's own text, else a slice of its container's text.

    Needed because the anchor text ALONE is often not enough to know which
    offer a link belongs to - e.g. on o2online.de/deals the product name
    ("Samsung Galaxy A57...") sits in a heading BEFORE the link, and the
    anchor text itself is only the price CTA ("Nur 27,49 EUR monatlich").
    See claude/promo-tiefenlinks-konzept.md section 3 for the research."""
    anchor_text = a_tag.get_text(" ", strip=True)
    texts = [anchor_text] if anchor_text else []
    node = a_tag
    for _ in range(4):
        node = getattr(node, "parent", None)
        if node is None or getattr(node, "name", None) is None:
            break
        heading = node.find(["h1", "h2", "h3", "h4"])
        if heading is not None:
            h_text = heading.get_text(" ", strip=True)
            if h_text and h_text not in texts:
                texts.insert(0, h_text)
            break
        if node.name in _LINK_CONTAINER_TAGS:
            block_text = node.get_text(" ", strip=True)
            if block_text and block_text != anchor_text:
                texts.append(block_text[:160])
            break
    context = " - ".join(t for t in texts if t)
    return _WS_RE.sub(" ", context).strip()[:200]


def extract_link_candidates(html: str, base_url: str,
                            max_candidates: int = _MAX_LINK_CANDIDATES) -> list[dict]:
    """Same-origin link candidates an individual offer might deep-link to:
    [{"href": <absolute url>, "text": <short context>}, ...].

    Runs over the same boilerplate-stripped soup as extract_text() (nav/
    footer/header/form already removed), so navigation chrome never becomes
    a candidate. Same-origin only - never let an affiliate/tracking
    redirect masquerade as a brand's own deep link (see
    claude/promo-tiefenlinks-konzept.md Premortem d). Deduplicated by
    resolved URL, keeping the first (topmost) context found for it. Returns
    [] on any parse problem - this is a purely additive signal for
    analyze/promo_analyst.py, never required for a page to be processed."""
    try:
        soup = BeautifulSoup(html or "", "html.parser")
        for tag in soup.find_all(_STRIP_TAGS):
            tag.decompose()
        base_host = urlsplit(base_url).netloc.lower()
        seen: dict[str, str] = {}
        for a in soup.find_all("a", href=True):
            href = (a.get("href") or "").strip()
            if not href or href.lower().startswith(_SKIP_HREF_PREFIXES):
                continue
            absolute = urljoin(base_url, href)
            parts = urlsplit(absolute)
            if parts.scheme not in ("http", "https"):
                continue
            if parts.netloc.lower() != base_host:
                continue
            if absolute in seen:
                continue
            context = _link_context(a)
            if not context:
                continue
            seen[absolute] = context
            if len(seen) >= max_candidates:
                break
        return [{"href": href, "text": text} for href, text in seen.items()]
    except Exception:  # noqa: BLE001 - additive signal, must never break the fetch
        log.info("Link-Kandidaten-Extraktion fehlgeschlagen fuer %s", base_url)
        return []


def _normalize_link_for_hash(href: str) -> str:
    """Strip known tracking/campaign params before folding *href* into
    content_hash()'s link signature, so a page swapping only a campaign
    tracker (not the actual link target) does not look like a content
    change every run. Never used for the displayed/stored URL itself."""
    try:
        parts = urlsplit(href)
    except ValueError:
        return href
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not _HASH_TRACKING_PARAM_RE.match(k)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), ""))


def fetch_snapshot(url: str, kind: str, http_cfg: dict) -> dict:
    """Fetch *url* and return {"text": <visible text>, "image_url": <hero
    image or None>, "links": <link candidates, see extract_link_candidates>}.
    Raises on failure - the caller is responsible for catching and recording
    it as a source failure, exactly like the other collectors."""
    if kind == "js":
        timeout_s = float(http_cfg.get("render_timeout_seconds",
                                        http_cfg.get("timeout_seconds", 25)))
        ua = http_cfg.get("user_agent", BROWSER_UA)
        html = render_html(url, timeout_s, ua)
    else:
        resp = fetch(url, http_cfg)
        html = resp.text
    return {
        "text": extract_text(html),
        "image_url": extract_hero_image(html, url),
        "links": extract_link_candidates(html, url),
    }


def _dismiss_cookie_banner(page) -> None:
    """Best-effort only: never let a missing/unrecognised banner raise. A
    successful click gets a short settle so the reflow finishes before the
    screenshot (accepted banners often collapse with a brief transition)."""
    try:
        for sel in _CONSENT_SELECTORS:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                loc.click(timeout=800)
                page.wait_for_timeout(600)
                return
        for text in _CONSENT_TEXTS:
            loc = page.get_by_role("button", name=re.compile(re.escape(text), re.I)).first
            if loc.count() and loc.is_visible():
                loc.click(timeout=800)
                page.wait_for_timeout(600)
                return
    except Exception:  # noqa: BLE001 - purely cosmetic, must never fail capture
        pass


def capture_hero_image(url: str, http_cfg: dict) -> bytes | None:
    """Best-effort JPEG screenshot of *url* for use as a promo card's hero
    image. Returns None on any failure - callers must treat a missing image
    as the normal case (falls back to the colour+initials card), not an
    error, exactly like extract_hero_image() above.

    A deliberately separate Chromium launch from fetch_snapshot()/
    render_html(): those block images/fonts/stylesheets for fast text
    extraction, which would make a screenshot pointless. locale is de-DE
    (rather than render_html's en-US) so German cookie-consent banners show
    their normal German button text, which _dismiss_cookie_banner() matches
    against."""
    timeout_s = float(http_cfg.get(
        "image_timeout_seconds", http_cfg.get("render_timeout_seconds", 17)))
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage",
                      "--disable-gpu", "--disable-blink-features=AutomationControlled"],
            )
            try:
                page = browser.new_page(
                    viewport=_IMG_VIEWPORT, device_scale_factor=1, locale="de-DE",
                    user_agent=http_cfg.get("user_agent", BROWSER_UA),
                )
                page.goto(url, wait_until="load", timeout=int(timeout_s * 1000))
                page.wait_for_timeout(1500)
                _dismiss_cookie_banner(page)
                # Nudge past a sticky top nav / any residual banner chrome so
                # the clip below lands on actual page content, not furniture.
                page.evaluate("window.scrollTo(0, 200)")
                page.wait_for_timeout(400)
                return page.screenshot(type="jpeg", quality=68, clip=_IMG_CLIP)
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001
        log.info("Promo-Hero-Screenshot fehlgeschlagen (%s): %s",
                 url, f"{type(exc).__name__}: {str(exc)[:140]}")
        return None


def content_hash(text: str, links: list[dict] | None = None) -> str:
    """Change-detection hash for promo_pipeline.py's snapshot diff.

    With *links* given (the pipeline always passes the current fetch's link
    candidates), the hash also folds in a normalised, sorted signature of
    their hrefs - so a page that swaps a button's link target while keeping
    the visible text identical still counts as "changed" and triggers a
    re-extract (see claude/promo-tiefenlinks-konzept.md Premortem f/g: the
    text-only hash could otherwise never notice a pure link change).
    Tracking/campaign params are stripped before hashing (see
    _normalize_link_for_hash) so an unrelated tracker swap alone does not.

    Backward compatible for callers/tests that only care about text
    (links omitted or empty -> identical to the pre-deep-links behaviour).
    Note this DOES change the stored hash for every brand the first time the
    pipeline starts passing links (a deliberate, one-off full re-extraction
    - see the konzept doc's "Nächste Schritte", not a bug)."""
    basis = text
    if links:
        signature = "\n".join(sorted(
            _normalize_link_for_hash(link.get("href") or "") for link in links))
        basis = f"{text}\n\x00LINKS\x00\n{signature}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()
