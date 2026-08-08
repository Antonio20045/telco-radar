"""Tests for RSS + newsroom parsing (fixtures, no network)."""
from datetime import datetime, timezone
from pathlib import Path

from telco_radar.collect.newsroom import parse_newsroom_html
from telco_radar.collect.rss import parse_feed_bytes
from telco_radar.config import Source

FIXTURES = Path(__file__).parent / "fixtures"


def test_rss_parsing():
    raw = (FIXTURES / "sample_feed.xml").read_bytes()
    src = Source(type="rss", url="https://example-telconews.com/feed",
                 name="Sample Telco News")
    items = parse_feed_bytes(raw, src, "global", None, "industry_news")
    assert len(items) == 3
    first = items[0]
    assert "eSIM roaming" in first.title
    assert first.published == datetime(2026, 7, 14, 9, 0, tzinfo=timezone.utc)
    assert first.origin == "industry_news"
    assert first.summary.startswith("Vodafone introduced")


def test_rss_tracking_params_do_not_change_id():
    raw = (FIXTURES / "sample_feed.xml").read_bytes()
    src = Source(type="rss", url="https://example-telconews.com/feed", name="S")
    items = parse_feed_bytes(raw, src, "global", None, "industry_news")
    from telco_radar.models import Item
    clean = Item(title=items[0].title,
                 url="https://example-telconews.com/2026/07/vodafone-esim-roaming-pass",
                 source_name="S")
    assert items[0].id == clean.id  # utm_source stripped before hashing


def test_newsroom_parsing():
    html = (FIXTURES / "sample_newsroom.html").read_text()
    src = Source(type="newsroom", url="https://www.example-telco.com/news",
                 name="Example Telco")
    items = parse_newsroom_html(html, src, "europe", "Example Telco", "operator")
    titles = [i.title for i in items]

    assert len(items) == 2  # external domain, short link, footer links skipped
    assert any("Unlimited 5G+" in t for t in titles)
    assert any("StreamCo" in t for t in titles)
    # date extracted from URL path /2026/07/
    assert all(i.published is not None and i.published.year == 2026 for i in items)
    # relative link resolved against source URL
    assert items[0].url.startswith("https://www.example-telco.com/")


def test_newsroom_respects_item_selector():
    html = (FIXTURES / "sample_newsroom.html").read_text()
    src = Source(type="newsroom", url="https://www.example-telco.com/news",
                 name="Example Telco", item_selector="footer")
    items = parse_newsroom_html(html, src, "europe", "Example Telco", "operator")
    assert items == []  # footer links are all skip-hinted or too short


def test_newsroom_item_selector_bypasses_url_keyword_heuristic():
    # Some CMS card layouts (e.g. Presspage) use opaque slugs with no
    # news/press/media keyword in the path - only a configured item_selector
    # can tell these apart from navigation, since the URL heuristic can't.
    html = (FIXTURES / "sample_card_newsroom.html").read_text()
    src = Source(type="newsroom_js", url="https://www.example-telco.com/press-browser/",
                 name="Example Telco", item_selector="a.card")
    items = parse_newsroom_html(html, src, "europe", "Example Telco", "operator")
    assert len(items) == 2
    assert all("/content/" in i.url for i in items)


def test_newsroom_item_selector_still_applies_skip_hints():
    html = (FIXTURES / "sample_card_newsroom.html").read_text()
    src = Source(type="newsroom_js", url="https://www.example-telco.com/press-browser/",
                 name="Example Telco", item_selector="nav a")
    items = parse_newsroom_html(html, src, "europe", "Example Telco", "operator")
    assert items == []  # mailto: link is still skip-hinted even with a selector


def test_newsroom_parses_ordinal_day_month_year_dates():
    # UK-style press dates ("28th May 2026") appear as plain surrounding text,
    # not in the URL - seen on threemediacentre.co.uk press-release cards.
    html = """
    <article><a href="/news/example-telco-launches-a-thing">Example Telco launches a thing</a>
      <span>Press release 28th May 2026</span></article>
    """
    src = Source(type="newsroom", url="https://example.com/news", name="S")
    items = parse_newsroom_html(html, src, "europe", "Example", "operator")
    assert len(items) == 1
    assert items[0].published.date().isoformat() == "2026-05-28"


def test_newsroom_skips_navigation_and_parses_common_date_formats():
    html = """
    <a href="/media-relations">Media contacts for journalists</a>
    <a href="/support/articledetail?artid=123">How to reset your router</a>
    <article><a href="/press-release/07-2026/new-service">New customer service launch</a>
      <time>July 9, 2026</time></article>
    """
    src = Source(type="newsroom", url="https://example.com/news", name="S")
    items = parse_newsroom_html(html, src, "europe", "Example", "operator")
    assert len(items) == 1
    assert items[0].published.date().isoformat() == "2026-07-09"


def test_rss_falls_back_to_human_readable_date():
    """Fierce Network prints "Jul 31, 2026 12:57pm" instead of RFC822, so
    feedparser leaves published_parsed empty. Undated items sort below the
    analyst's per-region cap, so the busiest trade-press feed would never be
    read - the collector must parse the raw string instead."""
    raw = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel><title>Fierce-style</title>
      <item>
        <title>NTIA tees up 4.4 GHz band</title>
        <link>https://example.com/ntia-4-4-ghz</link>
        <description>Spectrum news.</description>
        <pubDate>Jul 31, 2026 12:57pm</pubDate>
      </item>
    </channel></rss>"""
    src = Source(type="rss", url="https://example.com/rss/xml", name="Fierce-style")
    items = parse_feed_bytes(raw, src, "global", None, "industry_news")
    assert len(items) == 1
    assert items[0].published == datetime(2026, 7, 31, tzinfo=timezone.utc)


def test_url_date_ignores_numeric_id_after_a_year_in_the_slug():
    """Deutsche Telekom's ".../fifa-wm-2030-1116606" parsed as 16 Nov 2030,
    so the release was discarded as "published in the future" instead of
    using the date printed on the card."""
    from telco_radar.collect.newsroom import _date_from_url

    assert _date_from_url("https://x.test/detail/fifa-wm-2030-1116606") == (None, False)
    # real date paths keep working
    assert _date_from_url("https://x.test/news/2026/07/31/foo") == (
        datetime(2026, 7, 31, tzinfo=timezone.utc), True)


def test_newsroom_reads_aem_datamodel_article_list():
    """Optus ships its media releases as HTML-escaped JSON in a
    datamodel="..." attribute; Akamai blocks the headless browser, so the
    static HTML is the only way in - and it already holds everything."""
    html = (
        '<div class="articlelist" datamodel="'
        '{&quot;articles&quot;:[{&quot;title&quot;:&quot;Optus completes world-first trial&quot;,'
        '&quot;link&quot;:&quot;/about/media-centre/media-releases/2026/07/world-first&quot;,'
        '&quot;description&quot;:&quot;&lt;p&gt;A trial.&lt;/p&gt;&quot;,'
        '&quot;curatorAsDate&quot;:1783585800000,'
        '&quot;curator&quot;:&quot;7 July 2026, 08:30 AM&quot;}],'
        '&quot;totalPages&quot;:3,&quot;view&quot;:&quot;list&quot;}"></div>'
    )
    src = Source(type="newsroom", name="Optus",
                 url="https://www.optus.com.au/about/media-centre/media-releases")
    items = parse_newsroom_html(html, src, "oceania", "Optus", "operator")
    assert len(items) == 1
    assert items[0].title == "Optus completes world-first trial"
    assert items[0].url == ("https://www.optus.com.au/about/media-centre/"
                            "media-releases/2026/07/world-first")
    assert items[0].published is not None
    # the printed label wins over curatorAsDate (which is a day earlier in UTC)
    assert items[0].published.date().isoformat() == "2026-07-07"
    assert items[0].summary == "A trial."


def test_dates_in_local_languages_are_parsed():
    """A newsroom that prints its date in the local language yielded undated
    items, and undated items sort below the analyst's per-region cap - Turk
    Telekom delivered 10 releases a run and was never read."""
    from telco_radar.collect.newsroom import _date_from_text

    cases = {
        "24 Temmuz 2026": (2026, 7, 24),        # tr
        "30 de julho de 2026": (2026, 7, 30),   # pt
        "5 Agustus 2026": (2026, 8, 5),         # id
        "1. Oktober 2026": (2026, 10, 1),       # de
        "3 avril 2026": (2026, 4, 3),           # fr
        "20 Jul 2026": (2026, 7, 20),           # en, unveraendert
    }
    for text, (y, m, d) in cases.items():
        assert _date_from_text(text) == datetime(y, m, d, tzinfo=timezone.utc), text
    # a word that is not a month must stay unparsed
    assert _date_from_text("15 Werke 2026") is None


def test_exclude_url_pattern_drops_language_mirrors():
    """Verizon mirrors 7 of every 25 releases in Spanish under /about/news/es/.
    Different URL, so the seen-store counts it as a separate story and the
    same news would enter the report twice."""
    import re as _re
    from telco_radar.collect import _collect_source

    src = Source(type="rss", url="https://example.com/feed", name="X",
                 exclude_url_pattern="/about/news/es/")
    raw = b"""<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>Verizon kicks off NFL season</title>
        <link>https://example.com/about/news/nfl-season</link>
        <pubDate>Thu, 30 Jul 2026 10:00:00 GMT</pubDate></item>
      <item><title>Verizon inicia la temporada de la NFL</title>
        <link>https://example.com/about/news/es/nfl-temporada</link>
        <pubDate>Thu, 30 Jul 2026 10:00:00 GMT</pubDate></item>
    </channel></rss>"""

    import telco_radar.collect as collect_mod
    original = collect_mod.collect_rss
    collect_mod.collect_rss = lambda s, r, o, g, h: parse_feed_bytes(raw, s, r, o, g)
    try:
        items = _collect_source(src, "north_america", "Verizon", "operator", {})
    finally:
        collect_mod.collect_rss = original
    assert [i.title for i in items] == ["Verizon kicks off NFL season"]
    assert _re.search("/about/news/es/", items[0].url) is None


def test_leading_date_label_is_stripped_from_title():
    """Wire newsrooms print the timestamp inside the headline element
    ("Jul 31, 2026, 16:15 ET Rebecca McKillican joins ..."). The date is
    already parsed into published, so in the title it is only noise the
    report would print verbatim."""
    from telco_radar.collect.newsroom import _strip_leading_date_label

    when = datetime(2026, 7, 31, tzinfo=timezone.utc)
    assert _strip_leading_date_label(
        "Jul 31, 2026, 16:15 ET Rebecca McKillican joins the Board of BCE Inc.",
        when) == "Rebecca McKillican joins the Board of BCE Inc."
    assert _strip_leading_date_label(
        "16/07/2026 - Students from Kiambu National Polytechnic gain skills",
        when) == "Students from Kiambu National Polytechnic gain skills"
    # a year inside a real headline must not be treated as a label
    headline = "Vodafone launches 5G in 2026 across ten more cities right now"
    assert _strip_leading_date_label(headline, when) == headline
    # undated items keep their title - the label is the only date they have
    assert _strip_leading_date_label("Jul 31, 2026 Something happened here ok",
                                     None) == "Jul 31, 2026 Something happened here ok"


def test_datamodel_extractor_handles_alternate_field_names():
    """Optus and Singtel ship the same AEM datamodel shape under different
    field names (title/link vs articleHeading/pagePath)."""
    html = (
        '<div datamodel="'
        '{&quot;articles&quot;:[{&quot;articleHeading&quot;:&quot;Singtel Group celebrates National Day&quot;,'
        '&quot;pagePath&quot;:&quot;/about-us/media-centre/news-releases/national-day&quot;,'
        '&quot;articleDesc&quot;:&quot;A tribute film.&quot;,'
        '&quot;publishDate&quot;:&quot;24 Jul 2026&quot;}],'
        '&quot;totalPages&quot;:2}"></div>'
    )
    src = Source(type="newsroom", name="Singtel",
                 url="https://www.singtel.com/about-us/media-centre")
    items = parse_newsroom_html(html, src, "asien", "Singtel", "operator")
    assert len(items) == 1
    assert items[0].title == "Singtel Group celebrates National Day"
    assert items[0].published == datetime(2026, 7, 24, tzinfo=timezone.utc)
    assert items[0].summary == "A tribute film."


def test_rss_refetches_when_the_body_is_not_a_feed():
    """Telecoms Tech News answers with a WAF captcha page instead of RSS in
    roughly 4 of 10 runs; the HTTP layer sees a success, so only a re-fetch
    after the parse failure helps."""
    from telco_radar.collect import rss as rss_mod

    captcha = b"<html><head><meta http-equiv=refresh content=0></head></html>"
    good = b"""<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>FCC opens C-band proceeding</title>
        <link>https://example.com/c-band</link>
        <pubDate>Thu, 30 Jul 2026 10:00:00 GMT</pubDate></item>
    </channel></rss>"""
    bodies = [captcha, good]

    class _Resp:
        def __init__(self, content):
            self.content = content

    calls = []

    def fake_fetch(url, http_cfg, timeout=None, headers=None):
        calls.append(url)
        return _Resp(bodies[min(len(calls) - 1, len(bodies) - 1)])

    import telco_radar.collect.http as http_mod
    original_fetch, original_wait = http_mod.fetch, rss_mod._PARSE_RETRY_WAIT
    http_mod.fetch, rss_mod._PARSE_RETRY_WAIT = fake_fetch, 0
    try:
        src = Source(type="rss", url="https://example.com/feed", name="TTN")
        items = rss_mod.collect_rss(src, "global", None, "industry_news", {})
    finally:
        http_mod.fetch, rss_mod._PARSE_RETRY_WAIT = original_fetch, original_wait

    assert len(calls) == 2  # first body was not a feed
    assert [i.title for i in items] == ["FCC opens C-band proceeding"]


def test_sibling_subdomain_and_table_layout_like_att():
    """AT&T's newsroom is Akamai-blocked, but its IR release list is not - and
    that list keeps the headline in a sibling cell, repeats the column header
    as a screen-reader label, and links every story to a sibling subdomain."""
    html = """<table><tbody>
      <tr class="yr-2026">
        <th class="pr-date-field"><span class="pr-mobi-headers">Date</span>July 28, 2026</th>
        <td class="pr-title-field"><span class="pr-mobi-headers">Title</span>AT&amp;T Closes Acquisition of Spectrum Licenses</td>
        <td class="pr-document-field"><a class="icon-lnk"
           href="https://about.att.com/story/2026/echostar-spectrum.html"><span></span></a></td>
      </tr>
    </tbody></table>"""
    src = Source(type="newsroom", name="AT&T",
                 url="https://investors.att.com/news-and-events/news-releases",
                 item_selector="tr[class*=yr-]")
    items = parse_newsroom_html(html, src, "north_america", "AT&T", "operator")
    assert len(items) == 1
    assert items[0].title == "AT&T Closes Acquisition of Spectrum Licenses"
    assert items[0].published == datetime(2026, 7, 28, tzinfo=timezone.utc)
    assert items[0].url.startswith("https://about.att.com/")


def test_parent_site_never_widens_to_a_public_suffix():
    """Dropping a label off tim.com.br must not leave com.br, which would
    match every Brazilian site."""
    from telco_radar.collect.newsroom import _parent_site

    assert _parent_site("investors.att.com") == "att.com"
    assert _parent_site("www.tim.com.br") == "tim.com.br"
    assert _parent_site("tim.com.br") == ""      # would be com.br
    assert _parent_site("att.com") == ""


# ---------------------------------------------------- Datum aus dem Link
# Ein Feed ohne pubDate ist kein Sonderfall: der RSS-Feed der
# Bundesnetzagentur - der Regulierer des Marktes, in dem die Kollegin
# arbeitet - traegt weder pubDate noch dc:date. Alle 50 Meldungen galten
# damit als undatiert, und undatiert heisst faktisch unsichtbar: sie
# sortieren ans Ende und der Abnahme-Check lehnt die Quelle zu Recht ab.

def test_datum_kommt_notfalls_aus_dem_link():
    from telco_radar.collect.rss import _datum_aus_url
    assert _datum_aus_url(
        "https://www.bundesnetzagentur.de/SharedDocs/Pressemitteilungen/DE/"
        "2026/20260806_Agnes.html").date().isoformat() == "2026-08-06"
    assert _datum_aus_url(
        "https://example.com/2026/08/06/artikel").date().isoformat() == "2026-08-06"
    assert _datum_aus_url(
        "https://example.com/news/2026-08-06-artikel").date().isoformat() == "2026-08-06"


def test_artikelnummer_ist_kein_datum():
    """Sechsstellig gesucht faende das jede Artikelnummer - deshalb nur
    vierstellige Jahre, und der Tag darf keine weitere Ziffer nach sich
    ziehen."""
    from telco_radar.collect.rss import _datum_aus_url
    assert _datum_aus_url("https://example.com/artikel/260806") is None
    assert _datum_aus_url("https://example.com/id/20260899.html") is None
    assert _datum_aus_url("https://example.com/nr/202608061234") is None
    assert _datum_aus_url("https://example.com/ohne-datum") is None


def test_echtes_pubdate_schlaegt_den_link():
    """Der Link ist der LETZTE Ausweg. Ein Feed mit Datum darf nicht
    ploetzlich das Datum seiner URL-Struktur tragen."""
    from telco_radar.collect.rss import parse_feed_bytes
    from telco_radar.config import Source
    feed = b"""<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>Mit Datum</title>
        <link>https://example.com/2020/01/01/alt</link>
        <pubDate>Thu, 06 Aug 2026 09:00:00 +0000</pubDate></item>
      <item><title>Ohne Datum</title>
        <link>https://example.com/2026/08/06/neu</link></item>
    </channel></rss>"""
    items = parse_feed_bytes(feed, Source(type="rss", url="https://example.com/feed"),
                             "global", None, "industry_news")
    assert items[0].published.date().isoformat() == "2026-08-06"
    assert items[1].published.date().isoformat() == "2026-08-06"


def test_deckel_je_feed_ist_einstellbar():
    """Am 07.08.2026 lieferten die zehn ergiebigsten Quellen exakt 40
    Meldungen - also den damaligen Deckel und nicht ihren Bestand."""
    from telco_radar.collect.rss import parse_feed_bytes, MAX_ENTRIES_PER_FEED
    from telco_radar.config import Source
    eintraege = "".join(
        f"<item><title>Meldung {i}</title>"
        f"<link>https://example.com/{i}</link></item>" for i in range(80))
    feed = ('<?xml version="1.0"?><rss version="2.0"><channel>'
            + eintraege + "</channel></rss>").encode()
    src = Source(type="rss", url="https://example.com/feed")
    assert len(parse_feed_bytes(feed, src, "global", None, "industry_news")) \
        == MAX_ENTRIES_PER_FEED
    assert len(parse_feed_bytes(feed, src, "global", None, "industry_news",
                                max_entries=10)) == 10
