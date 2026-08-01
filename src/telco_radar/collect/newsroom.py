"""Generic HTML newsroom collector.

Press/newsroom landing pages differ wildly between operators. This collector
uses conservative heuristics: it extracts links that look like individual
press releases / news articles, optionally narrowed by a per-source CSS
selector from the watchlist. Dates are parsed from the URL or nearby text
when possible; undated items rely on the seen-store for novelty.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from ..config import Source
from ..models import Item

log = logging.getLogger(__name__)

# URL path fragments that indicate an article-like page
_ARTICLE_HINTS = re.compile(
    r"(news|press|media|release|announce|story|article|aktuell|presse)", re.I
)
# Path fragments that indicate navigation/utility pages -> skip
_SKIP_HINTS = re.compile(
    r"(login|signin|cookie|privacy|legal|terms|contact|careers|jobs|search|"
    r"subscribe|newsletter|archive\?|/tag/|/category/|/author/|#|mailto:|tel:|"
    r"/mediathek(?:/|$)|/media[-_]?(?:relations|library|contacts)(?:/|$)|"
    r"/investor[-_]?relations(?:/|$)|/voting[-_]?rights(?:/|$)|"
    r"/news[-_]?service[-_]?registration(?:/|$)|/shareholders?(?:/|$)|"
    r"/stockholders?(?:/|$)|/capex(?:[-_/]|$)|/support(?:[-_/]|$)|"
    r"/articledetail(?:/|\?|$)|/official[-_]?(?:channels|website)(?:/|$)|"
    r"/ansprechpartner(?:/|$)|/frequently[-_]asked[-_]questions(?:/|$)|"
    r"/social[-_]?media(?:/|$)|/press[-_]?conference[-_]?materials(?:/|$))", re.I
)
# Binary/document file extensions. Normally skipped (they're rarely articles),
# but some operators (e.g. TPG Telecom) publish releases as a heading + a PDF
# download with no separate HTML article page - there the PDF *is* the
# article, so a configured item_selector (which already narrows the DOM to
# verified article cards) is allowed to keep them.
_SKIP_FILE_EXT = re.compile(
    r"\.(pdf|jpg|jpeg|png|gif|svg|mp4|zip)$", re.I
)
# Third-party stock-exchange filing/IR vendors some operators route their
# regulatory announcements through instead of hosting them on their own
# domain (see the same-domain check below).
_TRUSTED_EXTERNAL_HOSTS = {"listedcompany.com"}
# Date patterns inside URLs, e.g. /2026/07/ or /2026-07-14- or 20260714
# The trailing (?![0-9]) matters: without it the numeric id in a slug like
# ".../fifa-wm-2030-1116606" parses as 16 Nov 2030, and the item is then
# thrown away by the freshness filter as "published in the future" instead of
# falling back to the correct date printed on the card.
_URL_DATE = re.compile(
    r"(?:/|[-_])(20\d{2})[/\-_]?(0[1-9]|1[0-2])(?:[/\-_]?(0[1-9]|[12]\d|3[01]))?"
    r"(?![0-9])"
)
_TEXT_DATE = re.compile(
    r"\b(0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?[./\s]+"
    r"(0?[1-9]|1[0-2]|Jan\w*|Feb\w*|Mar\w*|Apr\w*|May|Jun\w*|Jul\w*|Aug\w*|"
    r"Sep\w*|Oct\w*|Nov\w*|Dec\w*)[./\s,]+(20\d{2})\b", re.I
)
_TEXT_DATE_MDY = re.compile(
    r"\b(Jan\w*|Feb\w*|Mar\w*|Apr\w*|May|Jun\w*|Jul\w*|Aug\w*|"
    r"Sep\w*|Oct\w*|Nov\w*|Dec\w*)\s+(0?[1-9]|[12]\d|3[01])"
    r"(?:st|nd|rd|th)?[./\s,]+(20\d{2})\b", re.I
)
_TEXT_DATE_ISO = re.compile(
    r"\b(20\d{2})[-/.](0[1-9]|1[0-2])[-/.](0[1-9]|[12]\d|3[01])\b"
)
# Navigation / section labels that are not articles (exact-match, lowercased).
_JUNK_EXACT = {
    "frequently asked questions", "faq", "faqs", "perspectives", "newsroom",
    "media center", "media centre", "media center landing", "press releases",
    "press release", "our reports, studies, and publications", "sitemap",
    "social media", "social media listing of all swisscom social media channels",
    "press conference materials top", "emergency resource center", "read more",
    "learn more", "see all", "view all", "all news", "back to top", "top",
    "cookie policy", "privacy policy", "contact us", "media contacts",
    "regulatory news service (regulatory)",
}
# Phrases that mark a non-article link when the title is short.
_JUNK_CONTAINS = re.compile(
    r"^(perspectives|faq|frequently asked|social media|press conference "
    r"materials|our reports|emergency resource|media (center|centre)|sitemap)",
    re.I,
)


def _is_junk_title(title: str) -> bool:
    norm = " ".join(title.strip().lower().split())
    if norm in _JUNK_EXACT:
        return True
    if len(title) < 45 and _JUNK_CONTAINS.search(norm):
        return True
    words = norm.split()
    if len(words) >= 2 and len(set(words)) == 1:  # "Perspectives Perspectives"
        return True
    return False


_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"])}
# Spanish month abbreviations that don't already coincide with the English
# ones above (mar/may/jun/jul/feb/sep/oct/nov overlap and need no alias).
_MONTHS.update({"ene": 1, "abr": 4, "ago": 8, "set": 9, "dic": 12})

# Web-component "card" widgets (seen on Modyo/Andino-based CMSs, e.g. Entel)
# embed the whole item list as a JSON array inside a custom element attribute
# instead of rendering plain <a> links - the markup looks like
# <andino-card-general eds-card='[{"text": "...", "href": "...", "badge":
# {"text": "25 Jul, 2026"}}]'></andino-card-general>. This is already present
# in the *static* HTML (no JS needed), so a dedicated extractor - tried before
# the generic <a>-based heuristic below - picks it up directly.
_EMBEDDED_CARD_ATTR_RE = re.compile(r"\beds-card\s*=\s*'(\[.*?\])'", re.S)
_ES_DATE_RE = re.compile(r"(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\.?,?\s+(\d{4})")


def _parse_badge_date(raw: str) -> datetime | None:
    m = _ES_DATE_RE.match(raw.strip())
    if not m:
        return None
    day, mon_raw, year = m.groups()
    month = _MONTHS.get(mon_raw.lower()[:3])
    if not month:
        return None
    try:
        return datetime(int(year), month, int(day), tzinfo=timezone.utc)
    except ValueError:
        return None


def _extract_embedded_cards(html: str, source: Source, region: str,
                            operator: str | None, origin: str,
                            max_links: int) -> list[Item]:
    site_root = f"{urlsplit(source.url).scheme}://{urlsplit(source.url).netloc}"
    base_host = urlsplit(source.url).netloc.removeprefix("www.")
    items: list[Item] = []
    seen_urls: set[str] = set()
    for block in _EMBEDDED_CARD_ATTR_RE.findall(html):
        try:
            records = json.loads(block)
        except json.JSONDecodeError:
            continue
        if not isinstance(records, list):
            continue
        for rec in records:
            if not isinstance(rec, dict):
                continue
            title = " ".join(str(rec.get("text") or "").split())
            href = str(rec.get("href") or "").strip()
            if not title or not href:
                continue
            url = href if href.startswith("http") else urljoin(site_root + "/", href.lstrip("/"))
            host = urlsplit(url).netloc.removeprefix("www.")
            if host != base_host and not host.endswith("." + base_host):
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)
            badge = rec.get("badge") or {}
            items.append(Item(
                title=title,
                url=url,
                source_name=source.name or base_host,
                region=region,
                operator=operator,
                published=_parse_badge_date(str(badge.get("text") or "")),
                origin=origin,
            ))
            if len(items) >= max_links:
                return items
    return items


def _heading_title_for(a, item_root) -> str:
    """Nearest heading text within the item's own container.

    Some CMS card layouts (e.g. TPG Telecom, e&) put the headline in an
    <h1>-<h6> tag next to the link instead of inside it (the link itself is
    just a "View PDF"/"Read more"/"Load More" button) - a configured
    item_selector already narrows the DOM to one container per item, so
    it's safe to fall back to the heading text for the title in that scope.
    """
    # `item_root` is the synthetic wrapper soup built around the selected
    # item nodes (one direct child of `item_root.div` per matched item) -
    # stop climbing once we reach that direct child, not the shared wrapper
    # itself, or every item would resolve to the very first heading in
    # document order.
    boundary = getattr(item_root, "div", item_root)
    node = a
    while node.parent is not None and node.parent is not boundary:
        node = node.parent
    if not hasattr(node, "find_all"):
        return ""
    headings = node.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    if not headings:
        # Some card layouts (e.g. Telecom Argentina) style the headline as a
        # <p class="...title..."> instead of a semantic heading tag - only
        # trust a <p> whose class name says "title" to avoid grabbing an
        # unrelated body paragraph.
        headings = [p for p in node.find_all("p")
                   if any("title" in c.lower() for c in (p.get("class") or []))]
    if not headings:
        return ""
    # A card can carry more than one heading level - e.g. e& tiles have a
    # short <h5> category badge ("Strategy & Operations") *before* the real
    # <h2> headline in document order. Picking the first match would grab
    # the badge, so take the longest heading text instead - the real
    # headline is reliably the longest string among short badges/labels.
    best = max(headings, key=lambda h: len(h.get_text(strip=True)))
    return " ".join(best.get_text(" ", strip=True).split())


def _date_from_url(url: str) -> tuple[datetime | None, bool]:
    """Returns (date, has_day_precision)."""
    m = _URL_DATE.search(url)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        has_day = m.group(3) is not None
        day = int(m.group(3)) if has_day else 1
    else:
        # Some official press pages use /07-2026/ instead of /2026/07/.
        reverse = re.search(
            r"(?:/|[-_])(0[1-9]|1[0-2])[-_](20\d{2})"
            r"(?:[-_/](0[1-9]|[12]\d|3[01]))?", url
        )
        if not reverse:
            return None, False
        month, year = int(reverse.group(1)), int(reverse.group(2))
        has_day = reverse.group(3) is not None
        day = int(reverse.group(3)) if has_day else 1
    try:
        parsed = datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None, False
    # A year in the headline ("Strategie 2030") can still slip through as a
    # date. Treat anything from the future as no date at all, so the card's
    # own date text gets a chance instead.
    if parsed > datetime.now(timezone.utc) + timedelta(days=1):
        return None, False
    return parsed, has_day


def _date_from_text(text: str) -> datetime | None:
    m = _TEXT_DATE.search(text)
    if m:
        day, mon_raw, year = m.group(1), m.group(2).lower(), int(m.group(3))
        month = _MONTHS.get(mon_raw[:3]) if not mon_raw.isdigit() else int(mon_raw)
        if month:
            try:
                return datetime(year, month, int(day), tzinfo=timezone.utc)
            except ValueError:
                pass
    m = _TEXT_DATE_MDY.search(text)
    if m:
        mon_raw, day, year = m.group(1).lower(), m.group(2), int(m.group(3))
        month = _MONTHS.get(mon_raw[:3])
        if month:
            try:
                return datetime(year, month, int(day), tzinfo=timezone.utc)
            except ValueError:
                pass
    m = _TEXT_DATE_ISO.search(text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def parse_newsroom_html(html: str, source: Source, region: str,
                        operator: str | None, origin: str,
                        max_links: int = 30) -> list[Item]:
    """Extract article-like links from a newsroom page (testable, no I/O)."""
    if "eds-card=" in html:
        embedded = _extract_embedded_cards(html, source, region, operator, origin, max_links)
        if embedded:
            return embedded

    soup = BeautifulSoup(html, "html.parser")
    scope = soup
    selector_matched = False
    if source.item_selector:
        selected = soup.select(source.item_selector)
        if selected:
            wrapper = BeautifulSoup("<div></div>", "html.parser")
            for node in selected:
                wrapper.div.append(node)
            scope = wrapper
            selector_matched = True

    base_host = urlsplit(source.url).netloc.removeprefix("www.")
    items: list[Item] = []
    seen_urls: set[str] = set()

    for a in scope.find_all("a", href=True):
        href = a["href"].strip()
        if not href:
            continue
        url = urljoin(source.url, href)
        parts = urlsplit(url)
        if _SKIP_HINTS.search(url):
            continue
        # Binary file links (PDF/etc.) are normally not articles, but some
        # operators (e.g. TPG Telecom) publish releases as heading + PDF
        # download with no separate HTML page - there the PDF *is* the
        # article, so trust an explicit item_selector over this heuristic.
        if _SKIP_FILE_EXT.search(url) and not selector_matched:
            continue
        if parts.scheme not in ("http", "https"):
            continue
        # stay on the operator's domain (subdomains allowed) - with a narrow
        # exception for known third-party stock-exchange filing vendors,
        # which several APAC-listed telcos (e.g. True Corporation) use to
        # host their regulatory/SET announcements instead of their own
        # domain. Only trusted once an explicit item_selector already
        # verified the surrounding container is a real announcement card.
        host = parts.netloc.removeprefix("www.")
        on_domain = host == base_host or host.endswith("." + base_host)
        on_trusted_vendor = selector_matched and any(
            host == d or host.endswith("." + d) for d in _TRUSTED_EXTERNAL_HOSTS)
        if not on_domain and not on_trusted_vendor:
            continue
        # A configured item_selector already narrows the DOM to verified
        # article containers (e.g. CMS card layouts whose URLs are opaque
        # slugs with no news/press keyword) - trust it over the URL heuristic.
        if not selector_matched and not _ARTICLE_HINTS.search(parts.path):
            continue
        # article pages have a real path, not just the section root
        if parts.path.rstrip("/") == urlsplit(source.url).path.rstrip("/"):
            continue

        title = " ".join(a.get_text(" ", strip=True).split())
        # Some card layouts (e.g. SK Telecom) wrap the whole card - headline
        # AND a long summary paragraph - inside one <a>, so a.get_text()
        # returns thousands of characters and fails the length filter below.
        # A descendant literally classed "title" is a common enough
        # convention to check first, before falling back to the length
        # heuristics that assume the anchor text IS the headline.
        if selector_matched and len(title) > 300:
            title_el = a.select_one(".title")
            if title_el:
                narrowed = " ".join(title_el.get_text(" ", strip=True).split())
                if narrowed and 25 <= len(narrowed) <= 300 and not _is_junk_title(narrowed):
                    title = narrowed
        # Some card layouts (e.g. e& newsroom) put the headline in a sibling
        # <h1>-<h6> inside the card and reserve the anchor text for a generic
        # "Read more"/"Load More" label - only worth searching once the
        # selector already narrowed us to a real article container.
        if selector_matched and (len(title) < 25 or len(title) > 300
                                  or _is_junk_title(title)):
            heading_title = _heading_title_for(a, scope)
            if heading_title and 25 <= len(heading_title) <= 300 \
                    and not _is_junk_title(heading_title):
                title = heading_title
        if selector_matched and (len(title) < 25 or len(title) > 300
                                  or _is_junk_title(title)):
            # Some icon-only links (e.g. Deutsche Telekom's media-link
            # anchors) carry the real headline only in a title/aria-label
            # attribute, often prefixed with a generic category label
            # ("Media information: <headline>") - strip that prefix.
            attr_title = (a.get("title") or a.get("aria-label") or "").strip()
            attr_title = re.sub(r"^[\w][\w \-]{2,30}:\s*", "", attr_title)
            if attr_title and 25 <= len(attr_title) <= 300 \
                    and not _is_junk_title(attr_title):
                title = attr_title
        # nav links are short; but some real content is legitimately terse
        # (e.g. RNS/regulatory-announcement titles like "Q1 Results") - a
        # source explicitly opts in via allow_short_titles rather than this
        # being a blanket relaxation for any item_selector, since most
        # item_selector-scoped nav-link false positives (e.g. "About Us")
        # are exactly as short.
        min_title_len = 6 if source.allow_short_titles else 25
        if len(title) < min_title_len or len(title) > 300:
            continue
        if _is_junk_title(title):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)

        url_date, url_has_day = _date_from_url(url)
        published = url_date if url_has_day else None
        if published is None and hasattr(a, "select_one"):
            # A descendant classed "date" (e.g. SK Telecom's "reg-date") is a
            # precise, common convention - worth trying before the truncated
            # whole-card text search below, which can miss a date sitting
            # after a long summary paragraph within the same [:400] cutoff.
            date_el = a.select_one("[class*=date]")
            if date_el:
                published = _date_from_text(date_el.get_text(" ", strip=True)[:100])
        if published is None:
            # A <tr> (e.g. RNS/regulatory-announcement tables like
            # Investegate's) must be tried before the broader div/li/article
            # fallback: several <a> siblings can share one outer div/table,
            # so climbing straight past the row would give every item in
            # that table the same (wrong) date.
            context = a.find_parent("tr") or a.find_parent(["article", "li", "div"])
            if context is not None:
                published = _date_from_text(context.get_text(" ", strip=True)[:400])
        if published is None and selector_matched:
            # Nearest small div (above) may sit inside the card without the
            # date, which is often a sibling elsewhere in the same item -
            # widen the search to the whole item container as a last resort.
            boundary = getattr(scope, "div", scope)
            node = a
            while node.parent is not None and node.parent is not boundary:
                node = node.parent
            if hasattr(node, "get_text"):
                published = _date_from_text(node.get_text(" ", strip=True)[:600])
        if published is None:
            published = url_date  # month precision is better than nothing

        items.append(
            Item(
                title=title,
                url=url,
                source_name=source.name or base_host,
                region=region,
                operator=operator,
                published=published,
                origin=origin,
            )
        )
        if len(items) >= max_links:
            break
    return items


def collect_newsroom(source: Source, region: str, operator: str | None,
                     origin: str, http_cfg: dict) -> list[Item]:
    from .http import fetch
    resp = fetch(source.url, http_cfg, source.timeout_seconds)
    max_links = int(http_cfg.get("max_links_per_newsroom", 30))
    return parse_newsroom_html(resp.text, source, region, operator,
                               origin, max_links)
