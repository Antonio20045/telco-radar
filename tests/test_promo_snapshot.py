"""Tests fuer den Snapshot-Diff-Collector (collect/promo_snapshot.py) -
Text-Extraktion, Hashing, Link- und Bildkandidaten, offline (kein echter
HTTP-Abruf).

Hier standen bis zum 07.08.2026 zusaetzlich acht Tests fuer
capture_hero_image()/_dismiss_cookie_banner() gegen ein Fake-Page-Double.
Beide Funktionen sind weg, und mit ihnen ihre Tests: die Seite bebildert
sich jetzt aus den Kampagnenmotiven der Aktionsseiten
(extract_image_candidates unten + promo_bilder.py), nicht aus Screenshots.
Zwei der 14 Screenshots zeigten das Cookie-Banner - die Dismiss-Logik war
also durchaus getestet und trotzdem unzureichend, weil ein Test gegen ein
Double nur belegt, dass der KNOWN Selektor geklickt wird."""
import re

from telco_radar.collect.promo_snapshot import (
    _normalize_link_for_hash, content_hash, extract_hero_image,
    extract_image_candidates, extract_link_candidates, extract_text,
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


def test_content_hash_without_links_matches_pre_deep_links_behaviour():
    """Callers that never pass links (older tests, or a fetch with no
    candidates) still get the historical text-only hash."""
    assert content_hash("Angebot A") == content_hash("Angebot A", links=[])
    assert content_hash("Angebot A") == content_hash("Angebot A", links=None)


def test_content_hash_changes_when_link_target_changes_but_text_does_not():
    """The actual bug this closes: a brand swaps a button's link target
    while the visible text stays identical - the old text-only hash would
    never notice, so the stale deep link would never be re-extracted."""
    same_text = "Jetzt sichern"
    links_a = [{"href": "https://example.test/geraet-a", "text": "Jetzt sichern"}]
    links_b = [{"href": "https://example.test/geraet-b", "text": "Jetzt sichern"}]
    assert content_hash(same_text, links_a) != content_hash(same_text, links_b)


def test_content_hash_ignores_tracking_param_differences():
    """A pure tracking/campaign-id churn (utm_*, FF_*) must not look like a
    content change every single run."""
    links_a = [{"href": "https://example.test/p?FF_CAMPAIGN=123&id=42"}]
    links_b = [{"href": "https://example.test/p?FF_CAMPAIGN=999&id=42"}]
    assert content_hash("text", links_a) == content_hash("text", links_b)


def test_normalize_link_for_hash_strips_tracking_but_keeps_functional_params():
    normalized = _normalize_link_for_hash(
        "https://www.o2online.de/e-shop/details?tarif=x&ratenzahlung=36&utm_source=news")
    assert "utm_source" not in normalized
    assert "tarif=x" in normalized
    assert "ratenzahlung=36" in normalized


def test_extract_link_candidates_same_origin_only():
    html = """
    <html><body>
      <main>
        <article><h2>Galaxy A57</h2><a href="/e-shop/galaxy-a57">Nur 27,49 EUR</a></article>
        <article><h2>Affiliate-Angebot</h2>
          <a href="https://affiliate.example/redirect?to=galaxy">Mehr erfahren</a>
        </article>
      </main>
    </body></html>
    """
    candidates = extract_link_candidates(html, "https://www.o2online.de/deals/")
    hrefs = [c["href"] for c in candidates]
    assert "https://www.o2online.de/e-shop/galaxy-a57" in hrefs
    assert not any("affiliate.example" in h for h in hrefs)


def test_extract_link_candidates_uses_heading_as_context_for_price_only_anchor_text():
    """Reproduces the o2online.de case from the concept doc: the anchor
    text alone is only the price CTA, the product name sits in a heading
    just before it in the same card."""
    html = """
    <main><article>
      <h2>Samsung Galaxy A57 128GB Awesome Navy</h2>
      <a href="/e-shop/samsung/galaxy-a57-details?tarif=m-plus">Nur 27,49 EUR monatlich</a>
    </article></main>
    """
    candidates = extract_link_candidates(html, "https://example.test/deals/")
    assert len(candidates) == 1
    assert "Samsung Galaxy A57" in candidates[0]["text"]
    assert "27,49" in candidates[0]["text"]


def test_extract_link_candidates_ignores_nav_footer_and_non_http_hrefs():
    html = """
    <html><body>
      <nav><a href="/menu-punkt">Menu</a></nav>
      <footer><a href="/impressum">Impressum</a></footer>
      <main>
        <a href="#top">Nach oben</a>
        <a href="javascript:void(0)">Klick mich</a>
        <a href="mailto:info@example.test">Kontakt</a>
        <a href="tel:+490000000">Anruf</a>
        <article><h2>Echtes Angebot</h2><a href="/echtes-angebot">Ansehen</a></article>
      </main>
    </body></html>
    """
    candidates = extract_link_candidates(html, "https://example.test/")
    hrefs = [c["href"] for c in candidates]
    assert hrefs == ["https://example.test/echtes-angebot"]


def test_extract_link_candidates_dedupes_same_resolved_url():
    html = """
    <main>
      <article><h2>Angebot X</h2><a href="/x">Details</a></article>
      <article><a href="/x">Nochmal Details</a></article>
    </main>
    """
    candidates = extract_link_candidates(html, "https://example.test/")
    assert len(candidates) == 1
    assert candidates[0]["href"] == "https://example.test/x"


def test_extract_link_candidates_respects_max_candidates():
    links_html = "".join(
        f'<article><h2>Angebot {i}</h2><a href="/a{i}">Details</a></article>'
        for i in range(80))
    html = f"<main>{links_html}</main>"
    candidates = extract_link_candidates(html, "https://example.test/", max_candidates=10)
    assert len(candidates) == 10


def test_extract_link_candidates_returns_empty_list_on_missing_html():
    assert extract_link_candidates(None, "https://example.test/") == []
    assert extract_link_candidates("", "https://example.test/") == []


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


# --------------------------------------------------------- Bildkandidaten
# Die Grundlage der Bebilderung: was hier nicht als Kandidat herauskommt,
# kann promo_bilder.py keinem Angebot zuordnen.

def test_extract_image_candidates_findet_bild_mit_anker_und_kontext():
    html = """
    <body><main>
      <div class="kachel">
        <h3>Allnet Flat M mit 125 GB</h3>
        <a href="/tarife/allnet-m/">
          <img src="/media/allnet-m-kampagne.jpg" alt="Frau mit Smartphone">
        </a>
      </div>
    </main></body>"""
    kand = extract_image_candidates(html, "https://marke.test/angebote/")
    assert len(kand) == 1
    assert kand[0]["src"] == "https://marke.test/media/allnet-m-kampagne.jpg"
    assert kand[0]["anchor"] == "https://marke.test/tarife/allnet-m/"
    # Der Kontext traegt BEIDES: alt-Text und die naechste Ueberschrift. Der
    # alt-Text allein reicht oft nicht ("Frau mit Smartphone" sagt nichts
    # ueber das Angebot), die Ueberschrift allein fehlt bei vielen Kacheln.
    assert "Frau mit Smartphone" in kand[0]["context"]
    assert "125 GB" in kand[0]["context"]


def test_extract_image_candidates_nimmt_die_breiteste_srcset_variante():
    """Ein srcset nennt dieselbe Aufnahme in mehreren Groessen. Fuer eine
    Kachel ist die groesste die richtige - genau der Fehler, den
    report/bilder.py am 06.08.2026 behoben hat (Feed-Thumbnails statt
    Artikelbilder, 18 von 31 Bildern zu schmal)."""
    html = """<body><img src="/klein.jpg"
      srcset="/klein.jpg 320w, /mittel.jpg 768w, /gross.jpg 1920w"
      alt="Kampagne"></body>"""
    kand = extract_image_candidates(html, "https://marke.test/")
    assert kand[0]["src"] == "https://marke.test/gross.jpg"
    assert kand[0]["hint_w"] == 1920


def test_extract_image_candidates_liest_picture_source():
    """Bei <picture> steht die Desktop-Fassung oft nur im <source srcset>,
    waehrend das <img> das Handybild traegt."""
    html = """<body><picture>
      <source srcset="/desktop.jpg 1600w" media="(min-width:900px)">
      <img src="/handy.jpg" alt="Aktion">
    </picture></body>"""
    kand = extract_image_candidates(html, "https://marke.test/")
    assert kand[0]["src"] == "https://marke.test/desktop.jpg"


def test_extract_image_candidates_behaelt_header_verwirft_nav_und_footer():
    """Anders als bei Text und Links bleibt <header> stehen: das
    Kampagnenmotiv einer Aktionsseite steht sehr oft genau dort."""
    html = """<body>
      <header><img src="/buehne.jpg" alt="Sommeraktion"></header>
      <nav><img src="/menue.jpg" alt="Menue"></nav>
      <footer><img src="/fuss.jpg" alt="Fuss"></footer>
    </body>"""
    quellen = [k["src"] for k in extract_image_candidates(html, "https://marke.test/")]
    assert quellen == ["https://marke.test/buehne.jpg"]


def test_extract_image_candidates_verwirft_datenurls_und_vektoren():
    html = """<body>
      <img src="data:image/png;base64,AAAA" alt="inline">
      <img src="/icon.svg" alt="Vektor">
      <img src="/echt.jpg" alt="Motiv">
    </body>"""
    quellen = [k["src"] for k in extract_image_candidates(html, "https://marke.test/")]
    assert quellen == ["https://marke.test/echt.jpg"]


def test_extract_image_candidates_entdoppelt_und_deckelt():
    html = "<body>" + "".join(
        f'<img src="/b{i}.jpg" alt="Motiv {i}">' for i in range(10)
    ) + '<img src="/b3.jpg" alt="nochmal"></body>'
    kand = extract_image_candidates(html, "https://marke.test/", max_candidates=4)
    assert len(kand) == 4
    assert len({k["src"] for k in kand}) == 4


def test_extract_image_candidates_gibt_leere_liste_ohne_html():
    assert extract_image_candidates("", "https://marke.test/") == []
    assert extract_image_candidates(None, "https://marke.test/") == []
