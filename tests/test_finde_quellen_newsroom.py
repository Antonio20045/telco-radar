"""Die Newsroom- und Rubrikerkennung des Suchers - die Hebel aus Welle 3.

Bis dahin akzeptierte scripts/finde_quellen.py nur RSS und JSON-APIs als
Kandidaten. Von 604 mechanisch gesuchten Firmen brachten deshalb 418 (69 %)
null Kandidaten, obwohl sie funktionierende Presseseiten haben - sie
deklarieren nur keinen Feed. Die Pipeline liest solche Seiten laengst.

Getestet wird das, was schiefgehen kann und beim Bauen auch schiefgegangen
ist: eine Hauptnavigation als "Artikelliste" vorschlagen, die Startseite statt
der Presseseite nehmen, an einer flektierten Pfadbezeichnung scheitern, einen
Treffer mitten im Wort finden.

Kein Netz noetig - gearbeitet wird auf HTML-Schnipseln.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from bs4 import BeautifulSoup

_PFAD = Path(__file__).resolve().parents[1] / "scripts" / "finde_quellen.py"
_spec = importlib.util.spec_from_file_location("finde_quellen", _PFAD)
fq = importlib.util.module_from_spec(_spec)
sys.modules["finde_quellen"] = fq
_spec.loader.exec_module(fq)


def _kachelseite(n: int = 8, klasse: str = "news-card") -> str:
    """Eine gewoehnliche Kachel-Artikelliste, wie sie jedes CMS ausliefert."""
    karten = "".join(
        f'<div class="{klasse}">'
        f'<span class="date">1{i} July 2026</span>'
        f'<a href="/news/vodafone-startet-projekt-nummer-{i}-im-netz">'
        f"Vodafone startet Projekt Nummer {i} im landesweiten Netz</a>"
        f"</div>"
        for i in range(n)
    )
    return f"<html><body><main>{karten}</main></body></html>"


# --------------------------------------------------------------------------- #
# Presseseiten finden
# --------------------------------------------------------------------------- #

def test_presseseite_wird_aus_der_startseite_gelesen():
    """Der Pfad steht in der Landessprache - raten hilft nicht."""
    html = """<html><body>
      <a href="/privat/">Privat</a>
      <a href="/om/presse-og-media/">Nyheter</a>
      <a href="/om/jobbitelenor/">Karriere</a>
    </body></html>"""
    treffer = fq._presseseiten_aus_html(html, "https://www.telenor.no/")
    assert "https://www.telenor.no/om/presse-og-media" in treffer


def test_flektierte_pfadbezeichnung_zaehlt_auch():
    """"pressemeldinger" ist "presse" mit norwegischer Endung.

    Ohne Endungstoleranz findet der Sucher Telenors Meldungsliste nicht,
    obwohl sie von der Presseseite direkt verlinkt ist.
    """
    html = '<a href="/om/presse-og-media/pressemeldinger/">Les flere nyheter</a>'
    treffer = fq._presseseiten_aus_html(html, "https://www.telenor.no/")
    assert any(t.endswith("/pressemeldinger") for t in treffer)


def test_kein_pressetreffer_mitten_im_wort():
    """Der erste Anlauf suchte im ganzen Pfad und schlug
    "/freebox/gestion-suppression-compte-free" als Presseseite vor."""
    html = ('<a href="/freebox/gestion-suppression-compte-free">Mon compte</a>'
            '<a href="/assistance/supervision">Supervision</a>')
    assert fq._presseseiten_aus_html(html, "https://www.free.fr/") == []


def test_sackgassen_werden_uebersprungen():
    html = ('<a href="/presse/newsletter">Newsletter</a>'
            '<a href="/presse/mediathek">Mediathek</a>'
            '<a href="/presse/kontakt">Pressekontakt</a>')
    assert fq._presseseiten_aus_html(html, "https://www.telekom.de/") == []


def test_fremde_domain_ist_keine_presseseite():
    html = '<a href="https://fremd.example/presse">Presse</a>'
    assert fq._presseseiten_aus_html(html, "https://www.telekom.de/") == []


def test_pressepfad_trennt_presseseite_von_startseite():
    assert fq._ist_pressepfad("https://x.de/presse/meldungen")
    assert fq._ist_pressepfad("https://corporate.dna.fi/uutishuone")
    assert not fq._ist_pressepfad("https://www.windtre.it")
    assert not fq._ist_pressepfad("https://www.fastweb.it/corporate/")


# --------------------------------------------------------------------------- #
# Selektoren ableiten
# --------------------------------------------------------------------------- #

def test_selektor_wird_aus_dem_dom_abgeleitet():
    soup = BeautifulSoup(_kachelseite(klasse="press-item"), "html.parser")
    selektoren = fq._selektor_kandidaten(soup)
    assert "div.press-item" in selektoren or ".press-item" in selektoren


def test_navigationsklassen_werden_nicht_vorgeschlagen():
    """DNAs Newsroom lieferte ueber `li.ds-main-nav__item--level-2` 28 saubere
    "Meldungen" - die zweite Ebene der Hauptnavigation."""
    html = "".join(
        f'<li class="ds-main-nav-item-level-2">'
        f'<a href="/uutishuone/tiedotteet-{i}">Tiedotteet ja uutiset {i}</a></li>'
        for i in range(9)
    )
    soup = BeautifulSoup(f"<ul>{html}</ul>", "html.parser")
    assert not any("nav" in s for s in fq._selektor_kandidaten(soup))


def test_css_unsichere_klassennamen_werden_uebersprungen():
    """Tailwind-Klassen wie "md:flex" sind als Selektor ein Syntaxfehler."""
    html = "".join(
        f'<div class="md:news-card"><a href="/news/eine-lange-meldung-nr-{i}">'
        f"Eine ausreichend lange Ueberschrift Nummer {i}</a></div>"
        for i in range(8)
    )
    soup = BeautifulSoup(html, "html.parser")
    assert all(":" not in s for s in fq._selektor_kandidaten(soup))


# --------------------------------------------------------------------------- #
# Adressform: Artikelliste oder Menue?
# --------------------------------------------------------------------------- #

class _FakeItem:
    def __init__(self, url: str):
        self.url = url


def test_artikelanteil_erkennt_meldungsadressen():
    items = [_FakeItem(f"https://x.de/news/dna-avaa-5g-verkon-oulussa-{i}")
             for i in range(5)]
    assert fq._artikelanteil(items) == 1.0


def test_artikelanteil_erkennt_menuepunkte():
    items = [_FakeItem(u) for u in (
        "https://x.de/uutishuone/tiedotteet",
        "https://x.de/yritys/sijoittajat",
        "https://x.de/medialle",
        "https://x.de/kauppa",
        "https://x.de/tuki",
    )]
    assert fq._artikelanteil(items) < fq.MIN_ARTIKELANTEIL


# --------------------------------------------------------------------------- #
# Die beste Lesart einer Seite
# --------------------------------------------------------------------------- #

def test_newsroom_wird_vorgeschlagen():
    treffer = fq._bester_newsroom(_kachelseite(10), "https://x.de/presse", "X")
    assert treffer is not None
    assert treffer["type"] == "newsroom"
    assert treffer["n_items"] >= fq.NEWSROOM_MIN_ITEMS
    # Die Karten tragen ein Datum - der Sucher muss die Lesart waehlen, die es
    # auch findet. Undatierte Meldungen sortieren im Lauf ans Ende.
    assert treffer["n_datiert"] == treffer["n_items"]


def test_zu_wenige_meldungen_sind_kein_newsroom():
    assert fq._bester_newsroom(_kachelseite(3), "https://x.de/presse",
                               "X") is None


def test_menue_ist_kein_newsroom():
    """Kurze Menuepfade, keine Artikelslugs - der Adressform-Filter greift."""
    html = "".join(
        f'<div class="news-item"><a href="/uutishuone/menue{i}">'
        f"Tiedotteet ja uutiset Nummer {i} lang genug</a></div>"
        for i in range(9)
    )
    assert fq._bester_newsroom(html, "https://x.fi/uutishuone", "X") is None


def test_hoechstens_zwei_newsrooms_je_ziel():
    seiten = {f"s{i}": (f"https://x.de/presse{i}", _kachelseite(10))
              for i in range(5)}
    treffer = fq._newsroom_kandidaten({"operator": "X"}, seiten, set())
    assert len(treffer) <= fq.NEWSROOM_MAX_JE_ZIEL


def test_bekannte_urls_werden_nicht_vorgeschlagen():
    seiten = {"a": ("https://x.de/presse", _kachelseite(10))}
    bekannt = {fq._schluessel("https://x.de/presse")}
    assert fq._newsroom_kandidaten({"operator": "X"}, seiten, bekannt) == []


# --------------------------------------------------------------------------- #
# Rubrikfeeds
# --------------------------------------------------------------------------- #

def test_rubriken_aus_html():
    html = ('<a href="/category/5g/">5G</a>'
            '<a href="/category/regulation/">Regulation</a>'
            '<a href="/2026/07/eine-meldung/">Eine Meldung</a>')
    rubriken = fq._rubriken_aus_html(html, "https://telecoms.example/")
    urls = {u for _, u in rubriken}
    assert "https://telecoms.example/category/5g/feed" in urls
    assert "https://telecoms.example/category/regulation/feed" in urls
    assert len(rubriken) == 2


def test_uninteressante_rubriken_fallen_durch():
    assert fq._RUBRIK_INTERESSANT.search("5G & Mobilfunk")
    assert fq._RUBRIK_UNINTERESSANT.search("Gewinnspiel")
    assert fq._RUBRIK_UNINTERESSANT.search("Podcast")
