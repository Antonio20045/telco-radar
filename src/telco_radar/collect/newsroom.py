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
from html import unescape
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from ..config import Source
from ..models import Item

log = logging.getLogger(__name__)

_ARTICLE_HINTS = re.compile(
    r"(news|press|media|release|announce|story|article|aktuell|presse)", re.I
)
_SKIP_HINTS = re.compile(
    r"(login|signin|cookie|privacy|legal|terms|contact|careers|jobs|search|"
    r"subscribe|newsletter|archive\?|/tag/|/category/|/author/|#|mailto:|tel:|"
    r"/mediathek(?:/|$)|/media[-_]?(?:relations|library|contacts)(?:/|$)|"
    r"/investor[-_]?relations(?:/|$)|/voting[-_]?rights(?:/|$)|"
    r"/news[-_]?service[-_]?registration(?:/|$)|/shareholders?(?:/|$)|"
    r"/stockholders?(?:/|$)|/capex(?:[-_/]|$)|/support(?:[-_/]|$)|"
    r"/articledetail(?:/|\?|$)|/official[-_]?(?:channels|website)(?:/|$)|"
    r"/ansprechpartner(?:/|$)|/frequently[-_]asked[-_]questions(?:/|$)|"
    r"/social[-_]?media(?:/|$)|/press[-_]?conference[-_]?materials(?:/|$))",
    re.I,
)
_SKIP_FILE_EXT = re.compile(r"\.(pdf|jpg|jpeg|png|gif|svg|mp4|zip)$", re.I)
_TRUSTED_EXTERNAL_HOSTS = {"listedcompany.com"}
_PUBLIC_SUFFIXES = {
    "com.br",
    "com.au",
    "co.uk",
    "com.tr",
    "co.za",
    "com.mx",
    "co.nz",
    "com.ar",
    "com.sa",
    "co.ke",
    "com.my",
    "com.ph",
    "com.sg",
    "co.th",
    "com.cn",
    "co.jp",
    "co.kr",
    "com.tw",
    "com.hk",
    "com.eg",
    "com.pk",
    "co.id",
    "com.vn",
    "com.co",
    "com.pe",
    "com.ng",
    "com.kw",
    "com.qa",
}


def _parent_site(host: str) -> str:
    """Drop the leading label so sibling subdomains can be recognised.

    AT&T lists its releases on investors.att.com but links every story to
    about.att.com - the same company, a different host. Only applied when a
    real parent domain is left over (never down to a public suffix).
    """
    labels = host.split(".")
    if len(labels) < 3:
        return ""
    parent = ".".join(labels[1:])
    if parent in _PUBLIC_SUFFIXES or len(parent.split(".")) < 2:
        return ""
    return parent


_URL_DATE = re.compile(
    r"(?:/|[-_])(20\d{2})[/\-_]?(0[1-9]|1[0-2])(?:[/\-_]?(0[1-9]|[12]\d|3[01]))?"
    r"(?![0-9])"
)
_TEXT_DATE = re.compile(
    r"\b(0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?[./\s]+(?:de\s+)?"
    r"(0?[1-9]|1[0-2]|[^\W\d_]{3,12})[./\s,]+(?:de\s+)?(20\d{2})\b",
    re.I,
)
_TEXT_DATE_MDY = re.compile(
    r"\b(Jan\w*|Feb\w*|Mar\w*|Apr\w*|May|Jun\w*|Jul\w*|Aug\w*|"
    r"Sep\w*|Oct\w*|Nov\w*|Dec\w*)\s+(0?[1-9]|[12]\d|3[01])"
    r"(?:st|nd|rd|th)?[./\s,]+(20\d{2})\b",
    re.I,
)
_TEXT_DATE_ISO = re.compile(
    r"\b(20\d{2})[-/.](0[1-9]|1[0-2])[-/.](0[1-9]|[12]\d|3[01])\b"
)
_JUNK_EXACT = {
    "frequently asked questions",
    "faq",
    "faqs",
    "perspectives",
    "newsroom",
    "media center",
    "media centre",
    "media center landing",
    "press releases",
    "press release",
    "our reports, studies, and publications",
    "sitemap",
    "social media",
    "social media listing of all swisscom social media channels",
    "press conference materials top",
    "emergency resource center",
    "read more",
    "learn more",
    "see all",
    "view all",
    "all news",
    "back to top",
    "top",
    "cookie policy",
    "privacy policy",
    "contact us",
    "media contacts",
    "regulatory news service (regulatory)",
}
_JUNK_BEGRIFF = re.compile(
    r"(?:perspectives|faqs?|frequently asked(?: questions)?|social media"
    r"|press conference materials|our reports|emergency resources?"
    r"|media (?:center|centre)|sitemap)"
    r"(?:\s+of\s+(?:the\s+)?(?:\S+\s+){0,3}(?:newsroom|website|site))?\W*",
    re.I,
)


_LABEL_WORDS = {
    "press",
    "release",
    "releases",
    "regulatory",
    "media",
    "news",
    "notice",
    "announcement",
    "announcements",
    "update",
    "updates",
    "corporate",
    "company",
    "group",
    "story",
    "article",
    "pressemitteilung",
    "presse",
    "communique",
    "comunicado",
    "noticia",
    "bulteni",
    "bulten",
}


def _strip_leading_date_label(
    title: str, published, operator: str | None = None
) -> str:
    """Drop a date/time label the card prints in front of the headline.

    Wire newsrooms and several CMS card layouts put the timestamp inside the
    same element as the headline ("Jul 31, 2026, 16:15 ET Rebecca McKillican
    joins ...", "16/07/2026 - Students from ...", "Press release * 8 juli,
    2026 Telenor acquires ..."). The date is already parsed into `published`,
    so in the title it is only noise that the report would print verbatim.
    Only applied to items that HAVE a date, and only when a real headline is
    left over.
    """
    if published is None:
        return title
    allowed = set(_LABEL_WORDS)
    if operator:
        allowed.update(w.lower() for w in re.findall(r"[^\W\d_]+", operator))
    for pattern in (_TEXT_DATE, _TEXT_DATE_MDY, _TEXT_DATE_ISO):
        m = pattern.search(title[:70])
        if not m:
            continue
        prefix_words = re.findall(r"[^\W\d_]+", title[: m.start()])
        if any(w.lower() not in allowed for w in prefix_words):
            continue
        rest = title[m.end() :]
        rest = re.sub(
            r"^,?\s*\d{1,2}[:.]\d{2}\s*(?:[APap]\.?[Mm]\.?)?"
            r"\s*(?:[A-Z]{2,4})?",
            "",
            rest,
        )
        rest = rest.lstrip(" \t-–—|:•·,")
        if len(rest) >= 25 and not _is_junk_title(rest):
            return rest
    return title


def _is_junk_title(title: str) -> bool:
    norm = " ".join(title.strip().lower().split())
    if norm in _JUNK_EXACT:
        return True
    if len(title) < 45 and _JUNK_BEGRIFF.fullmatch(norm):
        return True
    words = norm.split()
    if len(words) >= 2 and len(set(words)) == 1:
        return True
    return False


_MONTHS = {
    m: i + 1
    for i, m in enumerate(
        [
            "jan",
            "feb",
            "mar",
            "apr",
            "may",
            "jun",
            "jul",
            "aug",
            "sep",
            "oct",
            "nov",
            "dec",
        ]
    )
}
_MONTHS.update(
    {
        "ene": 1,
        "abr": 4,
        "ago": 8,
        "set": 9,
        "dic": 12,
        "fev": 2,
        "mai": 5,
        "out": 10,
        "dez": 12,
        "mär": 3,
        "okt": 10,
        "mei": 5,
        "agu": 8,
        "des": 12,
        "oca": 1,
        "şub": 2,
        "sub": 2,
        "nis": 4,
        "haz": 6,
        "tem": 7,
        "ağu": 8,
        "eyl": 9,
        "eki": 10,
        "kas": 11,
        "ara": 12,
        "fév": 2,
        "avr": 4,
        "aoû": 8,
        "aou": 8,
        "déc": 12,
    }
)

_EMBEDDED_CARD_ATTR_RE = re.compile(r"\beds-card\s*=\s*'(\[.*?\])'", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
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


def _extract_embedded_cards(
    html: str,
    source: Source,
    region: str,
    operator: str | None,
    origin: str,
    max_links: int,
) -> list[Item]:
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
            url = (
                href
                if href.startswith("http")
                else urljoin(site_root + "/", href.lstrip("/"))
            )
            host = urlsplit(url).netloc.removeprefix("www.")
            if host != base_host and not host.endswith("." + base_host):
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)
            badge = rec.get("badge") or {}
            items.append(
                Item(
                    title=title,
                    url=url,
                    source_name=source.name or base_host,
                    region=region,
                    operator=operator,
                    published=_parse_badge_date(str(badge.get("text") or "")),
                    origin=origin,
                )
            )
            if len(items) >= max_links:
                return items
    return items


_DATAMODEL_ATTR_RE = re.compile(r'\bdatamodel\s*=\s*"([^"]{200,})"')
_DM_TITLE_KEYS = ("title", "articleHeading", "heading")
_DM_LINK_KEYS = ("link", "pagePath", "url")
_DM_DESC_KEYS = ("description", "articleDesc", "summary")
_DM_DATE_KEYS = ("curator", "publishDate", "date", "publishedDate")


def _dm_first(rec: dict, keys) -> str:
    for k in keys:
        v = rec.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _epoch_ms_to_date(value) -> datetime | None:
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _extract_datamodel_articles(
    html: str,
    source: Source,
    region: str,
    operator: str | None,
    origin: str,
    max_links: int,
) -> list[Item]:
    site_root = f"{urlsplit(source.url).scheme}://{urlsplit(source.url).netloc}"
    base_host = urlsplit(source.url).netloc.removeprefix("www.")
    items: list[Item] = []
    seen_urls: set[str] = set()
    for block in _DATAMODEL_ATTR_RE.findall(html):
        try:
            model = json.loads(unescape(block))
        except json.JSONDecodeError:
            continue
        if not isinstance(model, dict):
            continue
        records = model.get("articles")
        if not isinstance(records, list):
            continue
        for rec in records:
            if not isinstance(rec, dict):
                continue
            title = " ".join(_dm_first(rec, _DM_TITLE_KEYS).split())
            href = _dm_first(rec, _DM_LINK_KEYS)
            if not title or not href:
                continue
            url = (
                href
                if href.startswith("http")
                else urljoin(site_root + "/", href.lstrip("/"))
            )
            host = urlsplit(url).netloc.removeprefix("www.")
            if host != base_host and not host.endswith("." + base_host):
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)
            published = _date_from_text(_dm_first(rec, _DM_DATE_KEYS)[:60])
            if published is None:
                published = _epoch_ms_to_date(rec.get("curatorAsDate"))
            items.append(
                Item(
                    title=title,
                    url=url,
                    source_name=source.name or base_host,
                    region=region,
                    operator=operator,
                    published=published,
                    summary=" ".join(
                        _TAG_RE.sub(" ", _dm_first(rec, _DM_DESC_KEYS)).split()
                    )[:600],
                    origin=origin,
                )
            )
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
    boundary = getattr(item_root, "div", item_root)
    node = a
    while node.parent is not None and node.parent is not boundary:
        node = node.parent
    if not hasattr(node, "find_all"):
        return ""
    headings = node.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    if not headings:
        headings = [
            p
            for p in node.find_all("p")
            if any("title" in c.lower() for c in (p.get("class") or []))
        ]
    if not headings:
        return ""
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
        reverse = re.search(
            r"(?:/|[-_])(0[1-9]|1[0-2])[-_](20\d{2})"
            r"(?:[-_/](0[1-9]|[12]\d|3[01]))?",
            url,
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
            return datetime(
                int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc
            )
        except ValueError:
            pass
    return None


def parse_newsroom_html(
    html: str,
    source: Source,
    region: str,
    operator: str | None,
    origin: str,
    max_links: int = 30,
) -> list[Item]:
    """Extract article-like links from a newsroom page (testable, no I/O)."""
    if "eds-card=" in html:
        embedded = _extract_embedded_cards(
            html, source, region, operator, origin, max_links
        )
        if embedded:
            return embedded
    if "datamodel=" in html:
        embedded = _extract_datamodel_articles(
            html, source, region, operator, origin, max_links
        )
        if embedded:
            return embedded

    soup = BeautifulSoup(html, "html.parser")
    for hidden in soup.select(
        "[class*=sr-only], [class*=visually-hidden], [class*=screen-reader],"
        " [class*=mobi-header], [class*=visuallyhidden]"
    ):
        hidden.decompose()
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
        if _SKIP_FILE_EXT.search(url) and not selector_matched:
            continue
        if parts.scheme not in ("http", "https"):
            continue
        host = parts.netloc.removeprefix("www.")
        on_domain = host == base_host or host.endswith("." + base_host)
        if not on_domain:
            parent = _parent_site(base_host)
            on_domain = bool(parent) and (host == parent or host.endswith("." + parent))
        on_trusted_vendor = selector_matched and any(
            host == d or host.endswith("." + d) for d in _TRUSTED_EXTERNAL_HOSTS
        )
        if not on_domain and not on_trusted_vendor:
            continue
        if not selector_matched and not _ARTICLE_HINTS.search(parts.path):
            continue
        if parts.path.rstrip("/") == urlsplit(source.url).path.rstrip("/"):
            continue

        title = " ".join(a.get_text(" ", strip=True).split())
        if selector_matched and len(title) > 300:
            title_el = a.select_one(".title")
            if title_el:
                narrowed = " ".join(title_el.get_text(" ", strip=True).split())
                if (
                    narrowed
                    and 25 <= len(narrowed) <= 300
                    and not _is_junk_title(narrowed)
                ):
                    title = narrowed
        if selector_matched and hasattr(a, "select_one"):
            heading_el = a.select_one("[class*=heading], [class*=title]")
            if heading_el:
                narrowed = " ".join(heading_el.get_text(" ", strip=True).split())
                if 25 <= len(narrowed) < len(title) and not _is_junk_title(narrowed):
                    title = narrowed
        if selector_matched and (
            len(title) < 25 or len(title) > 300 or _is_junk_title(title)
        ):
            container = a.find_parent("tr") or a.parent
            if container is not None and hasattr(container, "select_one"):
                cell = container.select_one("[class*=title]")
                if cell is not None:
                    labelled = " ".join(cell.get_text(" ", strip=True).split())
                    if 25 <= len(labelled) <= 300 and not _is_junk_title(labelled):
                        title = labelled
        if selector_matched and (
            len(title) < 25 or len(title) > 300 or _is_junk_title(title)
        ):
            heading_title = _heading_title_for(a, scope)
            if (
                heading_title
                and 25 <= len(heading_title) <= 300
                and not _is_junk_title(heading_title)
            ):
                title = heading_title
        if selector_matched and (
            len(title) < 25 or len(title) > 300 or _is_junk_title(title)
        ):
            attr_title = (a.get("title") or a.get("aria-label") or "").strip()
            attr_title = re.sub(r"^[\w][\w \-]{2,30}:\s*", "", attr_title)
            if (
                attr_title
                and 25 <= len(attr_title) <= 300
                and not _is_junk_title(attr_title)
            ):
                title = attr_title
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
            date_el = a.select_one("[class*=date]")
            if date_el:
                published = _date_from_text(date_el.get_text(" ", strip=True)[:100])
        if published is None and selector_matched and hasattr(a, "get_text"):
            published = _date_from_text(a.get_text(" ", strip=True)[:400])
        if published is None:
            context = a.find_parent("tr") or a.find_parent(["article", "li", "div"])
            if context is not None:
                published = _date_from_text(context.get_text(" ", strip=True)[:400])
        if published is None and selector_matched:
            boundary = getattr(scope, "div", scope)
            node = a
            while node.parent is not None and node.parent is not boundary:
                node = node.parent
            if hasattr(node, "get_text"):
                published = _date_from_text(node.get_text(" ", strip=True)[:600])
        if published is None:
            published = url_date

        title = _strip_leading_date_label(title, published, operator)

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


def collect_newsroom(
    source: Source, region: str, operator: str | None, origin: str, http_cfg: dict
) -> list[Item]:
    from .http import fetch

    resp = fetch(source.url, http_cfg, source.timeout_seconds, source.headers)
    max_links = int(http_cfg.get("max_links_per_newsroom", 30))
    return parse_newsroom_html(resp.text, source, region, operator, origin, max_links)
