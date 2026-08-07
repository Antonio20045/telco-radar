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

Bilder: extract_image_candidates() liefert die Bilder, die die Aktionsseite
SELBST zeigt - mit dem umgebenden <a href> und einem kurzen Kontext, damit
promo_bilder.py sie den einzelnen Angeboten zuordnen kann (Anker zuerst,
Textnaehe als Notnagel). Bis zum 07.08.2026 stand hier stattdessen
capture_hero_image(): ein Playwright-Screenshot der ganzen Seite je Marke,
1280x720 aus dem Viewport geschnitten. Zwei der 14 zeigten das Cookie-
Banner, einer war weiss, und als Kachel war keiner davon lesbar. Der
Kommentarblock weiter unten (vor content_hash) haelt fest, warum.
extract_hero_image() (og:image/twitter:image) bleibt als letzte Absicherung
je Marke - meist ein generisches Markenlogo, deshalb nur die letzte.
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

# Bildkandidaten (siehe extract_image_candidates). Eine Aktionsseite traegt
# deutlich mehr Bilder als brauchbare Links - Geraetefotos, Testimonials,
# Netzkarten -, und die Zuordnung unten waehlt daraus. 60 ist grosszuegig
# genug fuer die groesste gemessene Seite (winSIM: 66 <img>, davon 25 ueber
# 400 px) und deckelt trotzdem eine Seite mit tausend Produktkacheln.
_MAX_IMAGE_CANDIDATES = 60
# Tags, die fuer die BILDsuche stehen bleiben duerfen. Anders als bei Text
# und Links bleibt <header> hier drin: das Kampagnenmotiv einer Aktionsseite
# steht sehr oft genau dort (o2online.de, otelo.de, congstar.de - alle drei
# fuehren mit einem Buehnenbild im Kopfbereich). Wer header mitentfernt,
# wirft zuerst das beste Bild der Seite weg.
_IMG_STRIP_TAGS = ("script", "style", "noscript", "svg", "iframe", "form",
                   "nav", "footer")
_IMG_SRC_ATTRS = ("src", "data-src", "data-lazy-src", "data-original",
                  "data-image-src")
_IMG_SRCSET_ATTRS = ("srcset", "data-srcset")
# Dateiendungen, die als Bild taugen. Ein Pfad ohne Endung (CDN mit
# Query-Parametern) faellt NICHT durch - der Download misst ohnehin nach.
_IMG_BAD_SUFFIX = (".svg", ".gif")
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


def _bestes_aus_srcset(wert: str) -> tuple[str, int]:
    """Die breiteste Variante aus einem srcset: ("url", breite).

    Ein srcset nennt dieselbe Aufnahme in mehreren Groessen
    ("...-768.jpg 768w, ...-1920.jpg 1920w"). Fuer eine Kachel auf einer
    Zeitungsseite ist die groesste die richtige - genau der Fehler, den
    report/bilder.py am 06.08.2026 behoben hat (Feed-Thumbnails statt
    Artikelbilder). Ohne Breitenangabe ("2x"-Deskriptoren, nackte Liste)
    gewinnt der letzte Eintrag; das ist die Konvention aufsteigender
    srcset-Listen."""
    bestes, breite = "", 0
    for teil in (wert or "").split(","):
        stuecke = teil.split()
        if not stuecke:
            continue
        url = stuecke[0].strip()
        if not url:
            continue
        w = 0
        if len(stuecke) > 1 and stuecke[1].endswith("w"):
            try:
                w = int(stuecke[1][:-1])
            except ValueError:
                w = 0
        if w >= breite:
            bestes, breite = url, w
    return bestes, breite


def _bild_quelle(img) -> tuple[str, int]:
    """Beste Quell-URL eines <img> samt angekuendigter Breite (0 = unbekannt).

    Beruecksichtigt das umgebende <picture> mit: dort steht die grosse
    Desktop-Fassung oft nur in einem <source srcset>, waehrend das <img>
    selbst das Handybild traegt."""
    kandidaten: list[tuple[str, int]] = []
    for attr in _IMG_SRCSET_ATTRS:
        if img.get(attr):
            kandidaten.append(_bestes_aus_srcset(img.get(attr)))
    eltern = getattr(img, "parent", None)
    if eltern is not None and getattr(eltern, "name", "") == "picture":
        for quelle in eltern.find_all("source"):
            for attr in _IMG_SRCSET_ATTRS:
                if quelle.get(attr):
                    kandidaten.append(_bestes_aus_srcset(quelle.get(attr)))
    for attr in _IMG_SRC_ATTRS:
        wert = (img.get(attr) or "").strip()
        if wert:
            kandidaten.append((wert, 0))
            break
    kandidaten = [(u, w) for u, w in kandidaten if u]
    if not kandidaten:
        return "", 0
    # Eine angekuendigte Breite schlaegt eine unbekannte; unter mehreren
    # gewinnt die groesste. Gemessen wird spaeter trotzdem mit Pillow -
    # das hier ist nur die Vorauswahl.
    breiteste = max(kandidaten, key=lambda k: k[1])
    if breiteste[1]:
        return breiteste
    return kandidaten[0]


def _naechster_anker(img) -> str:
    """href des <a>, in dem das Bild steht - "" wenn es in keinem steht.

    Das ist das staerkste Zuordnungssignal, das eine Aktionsseite hergibt:
    ein Angebot kennt seinen Tiefenlink (der Analyst hat ihn aus genau
    diesen Ankern gewaehlt, siehe extract_link_candidates), und das Bild im
    selben Anker gehoert zu genau diesem Angebot. Keine Heuristik, sondern
    die Struktur der Seite."""
    node = img
    for _ in range(6):
        node = getattr(node, "parent", None)
        if node is None or getattr(node, "name", None) is None:
            break
        if node.name == "a" and node.get("href"):
            return (node.get("href") or "").strip()
    return ""


def extract_image_candidates(html: str, base_url: str,
                             max_candidates: int = _MAX_IMAGE_CANDIDATES) -> list[dict]:
    """Bildkandidaten der Seite:
    [{"src": <absolut>, "context": <alt + naechste Ueberschrift>,
      "anchor": <absoluter href des umgebenden <a> oder "">,
      "hint_w": <angekuendigte Breite, 0 = unbekannt>}, ...]

    In Dokumentreihenfolge, nach URL entdoppelt. Das Gegenstueck zu
    extract_link_candidates(): dort waehlt ein Modell den Link, hier ordnet
    promo_bilder.py die Bilder den Angeboten mechanisch zu (Anker zuerst,
    Textnaehe als Notnagel).

    Warum ueberhaupt: bis zum 07.08.2026 bekam jede Marke EIN Bild, und das
    war ein Playwright-Screenshot ihrer Aktionsseite - 1280x720 aus dem
    Viewport geschnitten. Zwei der 14 zeigten das Cookie-Banner, einer war
    weiss, und alle waren als Kachel unlesbar (eine ganze Webseite auf
    Kachelbreite verkleinert). Die Aktionsseiten tragen ihr Kampagnenmotiv
    aber selbst - dieselbe Beobachtung, die die Marktrecherche bebildert
    (report/bilder.py). Fremde Bilder werden nicht mitgeholt, nur die der
    beobachteten Seite selbst.

    Gibt [] bei jedem Parse-Problem zurueck - ein rein additives Signal,
    nie ein neuer Fehlerfall."""
    try:
        soup = BeautifulSoup(html or "", "html.parser")
        for tag in soup.find_all(_IMG_STRIP_TAGS):
            tag.decompose()
        gesehen: dict[str, dict] = {}
        for img in soup.find_all("img"):
            roh, hint_w = _bild_quelle(img)
            if not roh or roh.lower().startswith("data:"):
                continue
            absolut = urljoin(base_url, roh)
            teile = urlsplit(absolut)
            if teile.scheme not in ("http", "https"):
                continue
            if teile.path.lower().endswith(_IMG_BAD_SUFFIX):
                continue
            if absolut in gesehen:
                continue
            alt = _WS_RE.sub(" ", (img.get("alt") or "").strip())
            kontext = " - ".join(t for t in (alt, _link_context(img)) if t)
            anker = _naechster_anker(img)
            gesehen[absolut] = {
                "src": absolut,
                "context": kontext[:200],
                "anchor": urljoin(base_url, anker) if anker else "",
                "hint_w": hint_w,
            }
            if len(gesehen) >= max_candidates:
                break
        return list(gesehen.values())
    except Exception:  # noqa: BLE001 - additives Signal, darf den Abruf nie kippen
        log.info("Bild-Kandidaten-Extraktion fehlgeschlagen fuer %s", base_url)
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
    image or None>, "links": <link candidates, see extract_link_candidates>,
    "images": <image candidates, see extract_image_candidates>}.
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
        "images": extract_image_candidates(html, url),
    }


# Hier standen bis zum 07.08.2026 `_dismiss_cookie_banner()` und
# `capture_hero_image()`: je Marke ein eigener Chromium-Start, der die
# Aktionsseite mit echten Bildern und Schriften laed, ein Cookie-Banner
# wegzuklicken versucht und dann 1280x720 aus dem Viewport schneidet.
#
# Das Ergebnis war messbar schlecht. Von den 15 aufgenommenen Screenshots
# zeigten zwei das Cookie-Banner statt der Aktion (1&1, congstar - der
# Klickversuch trifft laengst nicht jede Zustimmungsschicht), einer war
# eine weisse Flaeche, und ALLE hatten dasselbe Grundproblem: eine ganze
# Webseite, auf Kachelbreite verkleinert, zeigt keine Aktion, sondern ein
# Muster. Antonio: "Bei vielen sieht man nur die Cookies. Und so ein
# Screenshot hilft ueberhaupt nicht."
#
# Ersetzt durch extract_image_candidates() oben plus promo_bilder.py: das
# Kampagnenmotiv, das die Aktionsseite selbst zeigt - dieselbe Loesung, mit
# der die Marktrecherche seit dem 06.08.2026 bebildert wird. Nebenbei faellt
# damit ein Chromium-Start je Marke weg.


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
