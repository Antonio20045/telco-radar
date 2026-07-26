"""Tests fuer den Snapshot-Diff-Collector (collect/promo_snapshot.py) -
reine Text-Extraktion/Hashing, offline (kein echter HTTP-Abruf).

capture_hero_image() selbst startet einen echten Chromium-Prozess und wird -
wie das strukturell identische render_html() in newsroom_js.py - bewusst
NICHT gegen ein echtes Playwright gegen echte Websites getestet (kein Netz
in der Testumgebung, siehe TELCO_RADAR_HANDOVER.md Abschnitt 7). Getestet
wird stattdessen der Resilienz-Vertrag (nie werfen, Fehler -> None) und die
Cookie-Banner-Dismiss-Logik gegen ein leichtgewichtiges Fake-Page-Double."""
import re

from telco_radar.collect.promo_snapshot import (
    _CONSENT_SELECTORS, _CONSENT_TEXTS, _dismiss_cookie_banner,
    capture_hero_image, content_hash, extract_hero_image, extract_text,
)


def test_extract_text_strips_boilerplate_tags():
    html = """
    <html><body>
      <nav>Menu Link1 Link2</nav>
      <main><h1>10 GB Bonus</h1><p>Nur diese Woche: 10 GB extra.</p></main>
      <footer>Impressum Datenschutz</footer>
      <script>console.log('x')</script>
    </body></html>
    """
    text = extract_text(html)
    assert "10 GB Bonus" in text
    assert "Nur diese Woche" in text
    assert "Menu" not in text
    assert "Impressum" not in text
    assert "console.log" not in text


def test_extract_text_collapses_whitespace():
    html = "<body><p>Zeile   mit    vielen   Leerzeichen</p></body>"
    text = extract_text(html)
    assert "  " not in text


def test_extract_text_respects_max_chars():
    html = "<body><p>" + ("x" * 20000) + "</p></body>"
    text = extract_text(html, max_chars=100)
    assert len(text) <= 100


def test_content_hash_stable_and_sensitive():
    a = content_hash("Angebot A")
    b = content_hash("Angebot A")
    c = content_hash("Angebot B")
    assert a == b
    assert a != c


def test_extract_hero_image_prefers_og_image():
    html = """
    <html><head>
      <meta property="og:image" content="/images/aktion.jpg">
      <meta name="twitter:image" content="/images/other.jpg">
    </head><body></body></html>
    """
    url = extract_hero_image(html, "https://example.test/deals/")
    assert url == "https://example.test/images/aktion.jpg"


def test_extract_hero_image_falls_back_to_twitter_image():
    html = '<html><head><meta name="twitter:image" content="https://cdn.test/a.png"></head></html>'
    assert extract_hero_image(html, "https://example.test/") == "https://cdn.test/a.png"


def test_extract_hero_image_returns_none_without_meta_tags():
    html = "<html><head><title>Aktionen</title></head><body><p>Kein Bild.</p></body></html>"
    assert extract_hero_image(html, "https://example.test/") is None


class _FakeLocator:
    """Minimal stand-in for a Playwright Locator: only the surface
    _dismiss_cookie_banner() actually calls."""

    def __init__(self, count=0, visible=False, raise_on_click=False):
        self._count = count
        self._visible = visible
        self._raise_on_click = raise_on_click
        self.clicked = False

    @property
    def first(self):
        return self

    def count(self):
        return self._count

    def is_visible(self):
        return self._visible

    def click(self, timeout=None):
        if self._raise_on_click:
            raise TimeoutError("element not clickable in test double")
        self.clicked = True


class _FakePage:
    """selector_matches: {css_selector: _FakeLocator}
    text_matches: {button_text: _FakeLocator} (matched via get_by_role's
    regex `name` argument, same as the real _dismiss_cookie_banner call)."""

    def __init__(self, selector_matches=None, text_matches=None):
        self.selector_matches = selector_matches or {}
        self.text_matches = text_matches or {}
        self.wait_calls = []

    def locator(self, sel):
        return self.selector_matches.get(sel, _FakeLocator(count=0))

    def get_by_role(self, role, name=None):
        for text, loc in self.text_matches.items():
            if name is not None and name.search(text):
                return loc
        return _FakeLocator(count=0)

    def wait_for_timeout(self, ms):
        self.wait_calls.append(ms)


def test_dismiss_cookie_banner_clicks_known_selector():
    target_selector = _CONSENT_SELECTORS[1]  # Cookiebot - haeufig auf DE-Seiten
    hit = _FakeLocator(count=1, visible=True)
    page = _FakePage(selector_matches={target_selector: hit})
    _dismiss_cookie_banner(page)
    assert hit.clicked is True


def test_dismiss_cookie_banner_falls_back_to_text_match():
    hit = _FakeLocator(count=1, visible=True)
    page = _FakePage(text_matches={_CONSENT_TEXTS[0]: hit})  # "Alle akzeptieren"
    _dismiss_cookie_banner(page)
    assert hit.clicked is True


def test_dismiss_cookie_banner_is_noop_without_any_match():
    page = _FakePage()  # nichts matcht - darf nicht werfen
    _dismiss_cookie_banner(page)  # keine Assertion noetig: kein Raise ist der Test


def test_dismiss_cookie_banner_swallows_click_exceptions():
    """Ein Klick, der scheitert (Element inzwischen weg, Overlay, Timeout),
    darf die Screenshot-Aufnahme nie zum Absturz bringen - best effort."""
    broken = _FakeLocator(count=1, visible=True, raise_on_click=True)
    page = _FakePage(selector_matches={_CONSENT_SELECTORS[0]: broken})
    _dismiss_cookie_banner(page)  # darf nicht werfen


def test_capture_hero_image_returns_none_on_any_failure(monkeypatch):
    """Playwright/Browser-Fehler jeder Art (Absturz, Timeout, fehlende
    Installation) duerfen capture_hero_image() nie werfen lassen - der
    Aufrufer (promo_pipeline.py) behandelt None als normalen Fall (kein
    Screenshot diesen Lauf), nie als Fehler, der den Lauf gefaehrdet."""
    class _BoomPlaywrightCtx:
        def __enter__(self):
            raise RuntimeError("kein Browser in dieser Testumgebung verfuegbar")

        def __exit__(self, *exc_info):
            return False

    monkeypatch.setattr("playwright.sync_api.sync_playwright",
                        lambda: _BoomPlaywrightCtx())
    assert capture_hero_image("https://example.test/deals/", {}) is None
