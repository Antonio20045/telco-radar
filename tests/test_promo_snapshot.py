"""Tests fuer den Snapshot-Diff-Collector (collect/promo_snapshot.py) -
reine Text-Extraktion/Hashing, offline (kein echter HTTP-Abruf)."""
from telco_radar.collect.promo_snapshot import content_hash, extract_text


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
