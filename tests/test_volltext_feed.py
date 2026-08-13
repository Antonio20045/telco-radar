"""Der billige Weg: Volltext aus dem Feed, ohne zusaetzlichen Abruf.

Gemessen am 13.08.2026 ueber 1329 Eintraege aus 140 RSS-Quellen:
`content:encoded` ist bei 45,2 % vorhanden und traegt bei 33,2 % Volltext -
und wurde bis dahin von keiner Zeile dieses Projekts gelesen. Die Kappung
`[:600]` aufzuheben haette dagegen nur 14,1 % gebracht.

Dazu die Zusicherung, die diese Aenderung ueberhaupt erst erlaubt:
**`summary` bleibt gekappt.** Was der Analyst sieht, ist eine eigene
Entscheidung - kein Nebeneffekt einer Uebersetzungsfunktion.
"""
from __future__ import annotations

from telco_radar.collect.rss import parse_feed_bytes, VOLLTEXT_MINDESTLAENGE
from telco_radar.config import Source
from telco_radar.models import Item

LANG = ("Este es un parrafo largo del articulo original que el sistema de "
        "gestion de contenidos entrega dentro del feed. ")


def _feed(beschreibung: str = "", content: str = "") -> bytes:
    inhalt = (f"<content:encoded><![CDATA[{content}]]></content:encoded>"
              if content else "")
    return f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel><title>Testfeed</title>
    <item>
      <title>Un titulo de prueba</title>
      <link>https://beispiel.test/a/1</link>
      <pubDate>Wed, 13 Aug 2026 09:00:00 +0000</pubDate>
      <description><![CDATA[{beschreibung}]]></description>
      {inhalt}
    </item>
  </channel>
</rss>""".encode("utf-8")


def _eins(roh: bytes) -> Item:
    src = Source(type="rss", url="https://beispiel.test/feed", name="Testfeed")
    items = parse_feed_bytes(roh, src, "global", None, "industry_news")
    assert len(items) == 1
    return items[0]


def test_content_encoded_wird_gelesen():
    """Das Feld, das bis zum 13.08.2026 niemand gelesen hat."""
    item = _eins(_feed(beschreibung="Anreisser.", content=LANG * 30))
    assert len(item.volltext) >= VOLLTEXT_MINDESTLAENGE
    assert "parrafo largo" in item.volltext


def test_summary_bleibt_bei_600_zeichen_gekappt():
    """Leitplanke A: der Analyst sieht NICHT mehr als vorher."""
    item = _eins(_feed(beschreibung=LANG * 30, content=LANG * 30))
    assert len(item.summary) == 600


def test_html_wird_aus_dem_volltext_entfernt():
    item = _eins(_feed(content="<p>" + LANG * 30 + "</p><script>x</script>"))
    assert "<p>" not in item.volltext
    assert "parrafo" in item.volltext


def test_langer_teaser_zaehlt_als_volltext():
    """9,7 % der Eintraege tragen den ganzen Artikel in `description`.

    TeleSemana lieferte in der Messung 15 289 Zeichen dort - ohne diese
    Regel waere der teuerste Weg fuer den billigsten Fall gelaufen.
    """
    item = _eins(_feed(beschreibung=LANG * 30))
    assert len(item.volltext) >= VOLLTEXT_MINDESTLAENGE
    assert len(item.summary) == 600


def test_kurzer_teaser_ist_kein_volltext():
    item = _eins(_feed(beschreibung="Nur ein kurzer Anreisser."))
    assert item.volltext == ""


def test_feed_ohne_content_encoded_bleibt_ohne_volltext():
    item = _eins(_feed(beschreibung="Kurz."))
    assert item.volltext == ""


def test_das_laengste_content_element_gewinnt():
    """Manche Feeds fuehren dort zusaetzlich eine Kurzfassung."""
    roh = f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel><title>T</title><item>
    <title>Titulo</title><link>https://beispiel.test/a/2</link>
    <content:encoded><![CDATA[kurz]]></content:encoded>
    <content:encoded><![CDATA[{LANG * 30}]]></content:encoded>
  </item></channel></rss>""".encode("utf-8")
    assert len(_eins(roh).volltext) >= VOLLTEXT_MINDESTLAENGE


# ------------------------------------------------------------------- Modell
def test_item_dict_runde_haelt_die_neuen_felder():
    item = Item(title="t", url="https://beispiel.test/x", source_name="q",
                volltext="lang", sprache="es", image_url="https://bild.test/1")
    zurueck = Item.from_dict(item.to_dict())
    assert zurueck.volltext == "lang"
    assert zurueck.sprache == "es"


def test_from_dict_verliert_das_bild_nicht():
    """Nebenbefund vom 13.08.2026: `image_url` fehlte in `from_dict`.

    `to_dict` schrieb es korrekt, `from_dict` liess es fallen - ein aus
    einem Dict wiederhergestelltes Item verlor sein Feed-Bild lautlos.
    """
    item = Item(title="t", url="https://beispiel.test/y", source_name="q",
                image_url="https://bild.test/2.jpg")
    assert Item.from_dict(item.to_dict()).image_url == "https://bild.test/2.jpg"
