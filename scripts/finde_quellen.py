#!/usr/bin/env python3
"""Breitensuche nach zusaetzlichen Quellen - mechanisch, ohne Modell.

Der teuerste Teil eines Quellen-Ausbaus ist nicht das Finden, sondern das
Raten: ein Modell schlaegt eine plausible Feed-URL vor, sie ist 404, und die
Pruefung kostet trotzdem einen Abruf. Dieses Skript dreht die Reihenfolge um -
es probiert erst die Wege, auf denen sich Feeds tatsaechlich finden lassen,
und liefert nur ausgelieferte URLs als Kandidaten:

  1. <link rel="alternate" type="application/rss+xml"> auf den angegebenen
     Seiten (Startseite, Newsroom, Investor Relations, ...)
  2. Kandidatenpfade, die in dieser Branche immer wieder funktionieren
     (/feed, /rss, /news/feed, ?format=feed, /wp-json/wp/v2/posts, ...)
  3. WordPress-REST-Endpunkt, wenn die Seite nach WordPress aussieht

Ausgabe ist eine Kandidatendatei fuer scripts/pruefe_quellenvorschlag.py.
Hier wird NICHTS abgenommen - dieses Skript sammelt nur Adressen, die
ueberhaupt etwas ausliefern. Die Abnahme macht allein der Abnahme-Check.

Massenbetrieb
-------------
Fuer den Ausbau auf 1000 Quellen ist das Skript auf Hunderte Ziele ausgelegt:

  * `--aus-watchlist` baut die Ziele selbst aus config/watchlist.yaml und
    config/tech_sources.yaml. Das ist der billigste Zugewinn ueberhaupt -
    kein einziges Unternehmen muss recherchiert werden, die Firmen stehen
    schon da, und erst 10 von 85 Betreibern haben mehr als einen Kanal.
  * `--firmen firmen.yaml` nimmt eine Liste aus Name + Domain (+ optional
    Region/Land/Thema) und probiert dieselben Wege auf neuen Unternehmen.
  * `--cache` merkt sich gepruefte Adressen; ein Abbruch nach 600 Zielen
    kostet dann nicht den ganzen Durchgang.
  * Bereits konfigurierte URLs werden gar nicht erst vorgeschlagen.

Die Host-Drosselung aus collect/http.py ist dabei eingeschaltet: eine Firma
hat schnell zwanzig Kandidatenpfade, und die alle gleichzeitig gegen denselben
Server zu werfen provoziert genau die 429/403, die den Kandidaten dann faelsch-
licherweise als tot ausweisen wuerden.

Aufruf:
    python scripts/finde_quellen.py ziele.yaml --out kandidaten.yaml
    python scripts/finde_quellen.py --aus-watchlist --out kandidaten.yaml
    python scripts/finde_quellen.py --firmen firmen.yaml --out kandidaten.yaml \
        --cache /tmp/gefunden.json

ziele.yaml:
    ziele:
      - operator: "Orange"            # oder thema/name fuer Themenquellen
        seiten:
          - "https://www.orange.com/en/newsroom"
          - "https://www.orange.com/en/investors"

firmen.yaml:
    firmen:
      - name: "Telenor Norge"
        domain: "telenor.no"
        region: europe                # nur beschreibend, fuer den Eintrag
        country: "NO"
"""
from __future__ import annotations

import argparse
import re
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import yaml
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

# Der Sucher wirft absichtlich einen HTML-Parser auf Adressen, von denen er
# noch nicht weiss, was sie ausliefern - eine XML-Warnung je Feed ist Rauschen.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telco_radar.collect.http import configure_throttle, fetch  # noqa: E402
from telco_radar.collect.newsroom import parse_newsroom_html  # noqa: E402
from telco_radar.config import Source, load_config  # noqa: E402
from telco_radar.models import normalize_url  # noqa: E402

# Kurze Zeitgrenze mit Absicht: in einer Breitensuche sind die meisten
# geprobten Adressen 404, und ein Server, der 8 s fuer eine Feed-Datei
# braucht, wird auch im Lauf zum Problem. Ein Timeout kostet hier das
# Sechsfache eines Treffers (zwei User-Agents x drei Versuche).
HTTP_CFG = {"timeout_seconds": 8}

# Pfade, die in dieser Branche ueberdurchschnittlich oft ein Feed sind.
# Reihenfolge = Trefferwahrscheinlichkeit; die Liste bleibt bewusst kurz,
# jeder Eintrag kostet einen Abruf je Ziel.
KANDIDATENPFADE = (
    "/feed", "/rss", "/feed/", "/rss.xml", "/feed.xml", "/atom.xml",
    "/index.xml", "/news/feed", "/news/rss", "/blog/feed", "/blog/rss.xml",
    "/?format=feed&type=rss", "/rss/news", "/en/feed", "/de/feed",
    "/wp-json/wp/v2/posts?per_page=25&_embed=1",
    # Weitere Muster, die im Bestand nachweislich vorkommen bzw. bei
    # Telco-Newsrooms ueberdurchschnittlich oft treffen. Jeder Eintrag kostet
    # einen Abruf je Ziel - die Liste bleibt deshalb kurz und begruendet.
    "/news/feed/", "/press/feed", "/presse/feed", "/media/feed",
    "/newsroom/feed", "/newsroom/rss", "/news.xml", "/press-releases/feed",
    "/en/rss.xml", "/rss/pressreleases.xml", "/feeds/news.xml",
    "/sitemap-news.xml", "/api/news", "/blog/index.xml",
)

# Unterpfade, die AN DIE GENANNTE SEITE gehaengt werden (nicht an die Domain).
_SEITEN_SUFFIXE = ("/feed", "/rss", "/feed/", "/rss.xml",
                   "?format=feed&type=rss")

# Newsroom-Pfade, die auf einer blossen Domain ueberhaupt erst gesucht werden
# muessen: bei --firmen ist nur "telenor.no" bekannt, nicht wo dort die
# Pressemeldungen liegen. Die rel=alternate-Suche braucht aber eine Seite.
NEWSROOM_PFADE = (
    "", "/news", "/en/news", "/newsroom", "/press", "/media",
)

_FEED_TYPES = ("application/rss+xml", "application/atom+xml",
               "application/feed+json", "application/json")
_FEED_ANKER = re.compile(r"(rss|feed|atom)", re.I)


def _ist_feed_inhalt(text: str, content_type: str) -> str:
    """Liefert den Quellentyp ('rss'/'json_api') oder '' wenn es keiner ist."""
    kopf = text[:2000].lstrip()
    ct = (content_type or "").lower()
    if kopf.startswith("<?xml") or "<rss" in kopf[:400].lower() \
            or "<feed" in kopf[:400].lower():
        return "rss"
    if "xml" in ct and ("<item" in text[:6000] or "<entry" in text[:6000]):
        return "rss"
    if kopf.startswith(("[", "{")) and ("json" in ct or True):
        # Nur als json_api melden, wenn ueberhaupt mehrere Datensaetze
        # drinstehen - eine Fehlerseite in JSON ist kein Feed.
        if text.count('"title"') >= 3 or text.count('"headline"') >= 3 \
                or text.count('"link"') >= 3:
            return "json_api"
    return ""


def _pruefe_url(url: str) -> tuple[str, str] | None:
    try:
        resp = fetch(url, HTTP_CFG, schnell=True)
    except Exception:  # noqa: BLE001
        return None
    typ = _ist_feed_inhalt(resp.text, resp.headers.get("content-type", ""))
    return (str(resp.url), typ) if typ else None


def _hole_seite(seite: str) -> tuple[str, str] | None:
    """Eine Seite EINMAL holen und (Endadresse, HTML) zurueckgeben.

    Frueher holte die Feed-Suche jede Seite und warf das HTML sofort weg. Die
    Newsroom-Erkennung braucht genau dieses HTML noch einmal - und ein zweiter
    Abruf derselben Seite ist bei mehreren hundert Firmen der teuerste Fehler,
    den man machen kann. Deshalb wird einmal geholt und beides daraus bedient.
    """
    try:
        resp = fetch(seite, HTTP_CFG, schnell=True)
    except Exception:  # noqa: BLE001
        return None
    text = resp.text or ""
    if len(text) < 400:          # Fehlerseite oder leerer Rumpf
        return None
    return str(resp.url), text


def _feeds_aus_html(html: str, basis: str) -> list[str]:
    """Feed-URLs, die die Seite selbst angibt (rel=alternate) oder verlinkt."""
    soup = BeautifulSoup(html, "html.parser")
    gefunden: list[str] = []
    for link in soup.find_all("link", rel=True):
        rels = [r.lower() for r in (link.get("rel") or [])]
        typ = (link.get("type") or "").lower()
        if "alternate" in rels and typ in _FEED_TYPES and link.get("href"):
            gefunden.append(urljoin(basis, link["href"]))
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if _FEED_ANKER.search(href) and not href.startswith(("mailto:", "#")):
            if href.lower().endswith((".xml", "/feed", "/feed/", "/rss")) \
                    or "format=feed" in href.lower():
                gefunden.append(urljoin(basis, href))
    # Reihenfolge erhalten, Dubletten raus
    return list(dict.fromkeys(gefunden))


# --------------------------------------------------------------------------- #
# Newsroom-Erkennung
#
# Der groesste einzelne Hebel im Ausbau (AUFTRAG_1000_QUELLEN_WELLE3.md
# Abschnitt 4.1). Vorher akzeptierte dieses Skript nur RSS und JSON-APIs als
# Kandidaten - moderne Konzernseiten deklarieren aber meist keinen Feed mehr.
# Von 604 mechanisch gesuchten Firmen der Vorsession brachten 418 (69 %) null
# Kandidaten, obwohl Telenor Norwegen, Vodafone Italien, Orange Spanien und
# Fastweb alle mit HTTP 200 antworten und funktionierende Presseseiten haben.
# Die Pipeline liest solche Seiten laengst (52 der 205 Quellen sind
# `type: newsroom`); nur der SUCHER konnte sie nicht vorschlagen.
#
# Hier wird NICHTS abgenommen. Der Sucher muss nur grosszuegig genug sein, einen
# plausiblen Vorschlag samt item_selector zu formulieren - ob der Selektor
# taugt, entscheidet allein scripts/pruefe_quellenvorschlag.py, und der laeuft
# ohnehin durch collect_source, also den echten Pfad der Pipeline.
# --------------------------------------------------------------------------- #

# Ab hier lohnt es sich, einen Newsroom ueberhaupt vorzuschlagen. Bewusst nur
# die Meldungszahl und die Adressform, NICHT der Datumsanteil: der Abnahme-Check
# verlangt 80 % datiert, aber ob eine Seite datiert gelesen wird, haengt am
# Datums-Parser - und den zu messen ist gerade der Punkt. Ein Vorschlag, der an
# Kriterium 3 scheitert, ist eine Parser-Luecke und soll sichtbar sein, nicht
# schon hier weggefiltert werden.
NEWSROOM_MIN_ITEMS = 5
# Anteil der Treffer, deren ADRESSE nach einer Meldung aussieht - siehe
# _artikelanteil(). Trennt die Artikelliste vom Navigationsmenue.
MIN_ARTIKELANTEIL = 0.5
# Mehr als zwei Newsroom-Seiten je Firma sind fast immer dieselbe Liste unter
# anderem Pfad (/news und /en/news). Der Dublettencheck faengt das ab, aber
# jeder Kandidat kostet dort einen Abruf.
NEWSROOM_MAX_JE_ZIEL = 2

# Woerter, hinter denen eine Presseseite liegt - in den Sprachen, in denen die
# Seiten wirklich geschrieben sind. Eine blosse Domain sagt nichts darueber, WO
# die Meldungen liegen: "/news" gibt es auf telenor.no nicht, "/presse" schon.
# Ein Blick in die Startseite ist billiger als zwanzig geratene Pfade.
#
# Geprueft wird SEGMENTWEISE und am Wortanfang, nicht irgendwo in der URL. Der
# erste Anlauf suchte im ganzen Pfad und schlug deshalb
# "/freebox/gestion-suppression-compte-free" als Presseseite vor.
_PRESSE_WORT = (
    r"newsroom|news|press|presse|pressroom|pressemitteilung|pressemeldung|"
    r"medieninformation|media|medien|mediacenter|aktuelles|meldungen|"
    r"nyheter|nyheder|nyhetsrom|uutiset|uutishuone|tiedotteet|"
    r"noticias|noticies|not[ií]cias|novedades|prensa|imprensa|"
    r"actualit[eé]s|actualite|communiques|communiqu[eé]s|comunicati|"
    r"comunicados|stampa|sala-stampa|sala-de-imprensa|sala-de-prensa|"
    r"basin|haberler|medya|wiadomosci|aktualnosci|prasa|biuro-prasowe|"
    r"h[ií]rek|sajt[oó]szoba|zpravy|tiskove|persberichten|nieuws|perscentrum|"
    r"berita|siaran-pers|tin-tuc|press-releases|press-release|press-room|"
    r"press-centre|press-center|media-centre|media-center|media-releases|"
    r"media-room|news-and-media|news-events|newsandevents|corporate"
)
# Endungstolerant: norwegisch "pressemeldinger", schwedisch "pressmeddelanden",
# tuerkisch "basin-bultenleri" sind alle dasselbe Wort mit Flexionsendung. Ohne
# die Toleranz findet der Sucher Telenors Meldungsliste nicht, obwohl sie von
# der Presseseite direkt verlinkt ist.
_PRESSE_SEGMENT = re.compile(rf"^({_PRESSE_WORT})[\w-]{{0,14}}$", re.I)
_PRESSE_TEXT = re.compile(rf"(^|\W)({_PRESSE_WORT})\w{{0,14}}(\W|$)", re.I)
# Segmente, die ganz sicher eine Presseseite sind - im Gegensatz zu "corporate",
# das nur ein Zwischenschritt dorthin ist. Entscheidet, ob ein Kandidat als
# echte Presseseite gilt oder als Beifang.
_PRESSE_KERN = re.compile(
    r"^(newsroom|news|press|presse|pressroom|pressemitteilung\w*|"
    r"medieninformation\w*|aktuelles|meldungen|nyheter|nyheder|nyhetsrom|"
    r"uutiset|uutishuone|tiedotteet|noticias|noticies|not[ií]cias|novedades|"
    r"prensa|imprensa|actualit[eé]s|actualite|communiques|communiqu[eé]s|"
    r"comunicati|comunicados|stampa|sala-stampa|sala-de-imprensa|"
    r"sala-de-prensa|basin\w*|haberler|medya|wiadomosci|aktualnosci|prasa|"
    r"biuro-prasowe|h[ií]rek|sajt[oó]szoba|zpravy|tiskove\w*|persberichten|"
    r"nieuws|perscentrum|berita|siaran-pers|tin-tuc|press-\w+|media-\w+|"
    r"news-\w+)[\w-]{0,14}$", re.I)
# Pfade, die zwar wie Presse aussehen, aber Sackgassen sind.
_PRESSE_SACKGASSE = re.compile(
    r"(/kontakt|/contact|/abonn|/subscribe|/newsletter|/rss|/feed|\.xml$"
    r"|/mediathek|/media[-_]?(kit|library|assets|contacts)|/logo|/bilder"
    r"|/images?/|/download|/archiv/\d{4}|/tag/|/category/|/author/"
    r"|/suche|/search|/login|/sitemap)", re.I)

# Klassennamen, hinter denen in dieser Branche Artikelkacheln stecken. Aus den
# bestehenden newsroom-Quellen abgelesen - dort wiederholen sich .card-item,
# .news__item, .mediaItem, a.card, article.press-post, .tile-box-tile,
# div.artigo-sem-imagem, a.relases-card immer wieder.
_KACHEL_KLASSE = re.compile(
    r"(card|item|tile|teaser|article|post|news|press|release|entry|listing"
    r"|result|story|artigo|noticia|meldung|beitrag|bulten|kachel)", re.I)
# Klassen, die zwar "item" enthalten, aber ein Menue sind. DNAs Newsroom lieferte
# ueber `li.ds-main-nav__item--level-2` 28 saubere "Meldungen" - die zweite Ebene
# der Hauptnavigation. Ohne diesen Ausschluss schlaegt der Sucher Menueleisten
# als Quelle vor, und der Abnahme-Check muss sie erst abrufen, um das zu merken.
_MENUE_KLASSE = re.compile(
    r"(nav|menu|breadcrumb|footer|header|topbar|sidebar|drawer|dropdown|"
    r"submenu|pagination|tab-|-tab|cookie|banner|social|share|lang)", re.I)
# CSS-sichere Klassennamen. Utility-Frameworks (Tailwind) erzeugen Klassen wie
# "md:flex" oder "w-1/2", die als Selektor einen Syntaxfehler ausloesen.
_KLASSE_OK = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{1,38}$")
# Strukturelle Selektoren ohne Klassennamen. Im Bestand tragen Airtel Africa und
# Spark genau diesen (`tbody tr`), Anthropic `article`.
_STRUKTUR_SELEKTOREN = ("article", "tbody tr", "li", ".card", ".item")
# Eine Artikeladresse sieht anders aus als ein Menuepunkt: sie traegt einen Slug
# mit mehreren Bindestrichen, eine Jahreszahl oder eine Meldungs-ID.
# /uutishuone/tiedotteet ist ein Menuepunkt,
# /uutishuone/dna-avaa-5g-verkon-oulussa-2026 ist eine Meldung.
_ARTIKEL_ID = re.compile(r"(/20\d{2}[/\-_]|[-_]\d{4,}(?:[./]|$)|\d{6,})")


def _presseseiten_aus_html(html: str, basis: str) -> list[str]:
    """Presseseiten, die die Seite selbst verlinkt.

    Genauer und billiger als Pfade zu raten: die Seite kennt ihren eigenen
    Newsroom, und sie kennt ihn in der richtigen Sprache.
    """
    soup = BeautifulSoup(html, "html.parser")
    basis_host = urlsplit(basis).netloc.removeprefix("www.")
    treffer: list[str] = []
    for a in soup.find_all("a", href=True):
        href = (a["href"] or "").strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        url = urljoin(basis, href)
        teile = urlsplit(url)
        if teile.scheme not in ("http", "https"):
            continue
        host = teile.netloc.removeprefix("www.")
        if host != basis_host and not host.endswith("." + basis_host):
            continue
        if _PRESSE_SACKGASSE.search(url):
            continue
        pfad = teile.path.rstrip("/")
        if not pfad or pfad.count("/") > 4:
            continue
        segmente = [s for s in pfad.split("/") if s]
        text = " ".join(a.get_text(" ", strip=True).split())[:60]
        if not (any(_PRESSE_SEGMENT.match(s) for s in segmente)
                or _PRESSE_TEXT.search(text)):
            continue
        treffer.append(f"{teile.scheme}://{teile.netloc}{pfad}")
    # Kurze Pfade zuerst: /presse schlaegt /presse/archiv/2019
    return sorted(dict.fromkeys(treffer), key=lambda u: (len(u), u))[:4]


def _ist_pressepfad(url: str) -> bool:
    """Sagt die URL selbst, dass hier Meldungen liegen?

    Trennt die echte Presseseite vom Beifang. Eine Startseite kann formal wie
    eine Artikelliste aussehen (Produktkacheln mit langen Ankertexten), ist aber
    keine - und ein Vorschlag, der auf die Startseite zeigt, waere im Bericht
    Werbung statt Nachricht.
    """
    segmente = [s for s in urlsplit(url).path.split("/") if s]
    return any(_PRESSE_KERN.match(s) for s in segmente)


def _selektor_kandidaten(soup: BeautifulSoup, grenze: int = 8) -> list[str]:
    """CSS-Selektoren fuer Artikelkacheln aus dem DOM ableiten.

    Kein Ratespiel ueber eine feste Liste, sondern eine Auswertung dessen, was
    auf der Seite tatsaechlich wiederholt vorkommt: ein Klassenname, der 5- bis
    80-mal auftritt und dessen Knoten je einen Link mit langem Text tragen, IST
    die Artikelkachel dieser Seite.
    """
    kandidaten: dict[str, int] = {}
    for el in soup.find_all(True):
        for klasse in (el.get("class") or []):
            if not _KLASSE_OK.match(klasse or "") \
                    or not _KACHEL_KLASSE.search(klasse) \
                    or _MENUE_KLASSE.search(klasse):
                continue
            for sel in (f"{el.name}.{klasse}", f".{klasse}"):
                kandidaten[sel] = kandidaten.get(sel, 0) + 1

    bewertet: list[tuple[int, int, str]] = []
    for sel, roh in kandidaten.items():
        if not (NEWSROOM_MIN_ITEMS <= roh <= 80):
            continue
        try:
            knoten = soup.select(sel)
        except Exception:  # noqa: BLE001 - kaputter Selektor, naechster
            continue
        mit_link = 0
        for k in knoten:
            link = k if k.name == "a" and k.get("href") else k.find("a", href=True)
            if link is None:
                continue
            if len(" ".join(k.get_text(" ", strip=True).split())) >= 25:
                mit_link += 1
        if mit_link < NEWSROOM_MIN_ITEMS:
            continue
        # Je spezifischer (tag.klasse) und je mehr echte Kacheln, desto besser.
        bewertet.append((mit_link, 1 if "." in sel[1:] else 0, sel))
    bewertet.sort(reverse=True)
    return [sel for _, _, sel in bewertet[:grenze]]


def _artikelanteil(items: list) -> float:
    """Wie viele der gefundenen Adressen sehen ueberhaupt nach Meldung aus?

    Der Datumsanteil taugt dafuer nicht: ob eine echte Meldungsliste datiert
    gelesen wird, haengt am Datums-Parser, und genau der wird gerade gemessen.
    Die Adressform haengt an nichts davon.
    """
    if not items:
        return 0.0
    treffer = 0
    for i in items:
        pfad = urlsplit(i.url or "").path.rstrip("/")
        letztes = pfad.rsplit("/", 1)[-1]
        if letztes.count("-") >= 3 or len(letztes) >= 30 \
                or _ARTIKEL_ID.search(pfad):
            treffer += 1
    return treffer / len(items)


def _bewerte_newsroom(html: str, url: str, name: str,
                      selektor: str | None) -> tuple[int, int, float, list]:
    """Eine Seite mit genau dem Parser lesen, den auch die Pipeline nimmt."""
    quelle = Source(type="newsroom", url=url, name=name, kind="newsroom",
                    item_selector=selektor)
    try:
        items = parse_newsroom_html(html, quelle, "europe", None, "operator")
    except Exception:  # noqa: BLE001
        return 0, 0, 0.0, []
    titel = {" ".join((i.title or "").lower().split()) for i in items}
    if len(titel) < NEWSROOM_MIN_ITEMS:
        # Zehnmal dieselbe Zeile ist keine Artikelliste - der Abnahme-Check
        # wuerde das an Kriterium 5b fangen, aber dann hat er schon abgerufen.
        return 0, 0, 0.0, []
    return (len(items), sum(1 for i in items if i.published),
            _artikelanteil(items), items)


def _bester_newsroom(html: str, url: str, name: str) -> dict | None:
    """Die beste Lesart einer Seite: ohne Selektor oder mit dem passendsten."""
    soup = BeautifulSoup(html, "html.parser")
    versuche: list[str | None] = [None]
    for sel in [*_selektor_kandidaten(soup), *_STRUKTUR_SELEKTOREN]:
        if sel not in versuche:
            versuche.append(sel)

    bestes: dict | None = None
    marke_best: tuple = ()
    for selektor in versuche:
        n, datiert, artikel, _ = _bewerte_newsroom(html, url, name, selektor)
        if n < NEWSROOM_MIN_ITEMS or artikel < MIN_ARTIKELANTEIL:
            continue
        anteil = datiert / n
        # Datumsanteil vor Meldungszahl: eine undatierte Meldung sortiert im
        # Lauf ans Ende und wird faktisch nie bewertet. 30 undatierte Treffer
        # sind weniger wert als 8 datierte. Bei Gleichstand gewinnt KEIN
        # Selektor - eine Zeile weniger Konfiguration, die kaputtgehen kann,
        # wenn die Seite ihr CSS umbenennt.
        marke = (round(anteil, 2), round(artikel, 2), min(n, 30),
                 1 if selektor is None else 0)
        if not marke_best or marke > marke_best:
            marke_best = marke
            bestes = {"url": url, "type": "newsroom",
                      "item_selector": selektor, "n_items": n,
                      "n_datiert": datiert, "anteil": round(anteil, 2),
                      "artikelanteil": round(artikel, 2)}
    return bestes


def _newsroom_kandidaten(ziel: dict, geholt: dict[str, tuple[str, str]],
                         bekannt: set[str]) -> list[dict]:
    """Presseseiten ohne Feed als `type: newsroom` vorschlagen.

    Arbeitet zuerst auf dem HTML, das die Feed-Suche ohnehin schon geholt hat,
    und holt nur die Presseseiten nach, die die Seiten selbst verlinken.
    """
    name = ziel.get("operator") or ziel.get("name") or ziel.get("thema") or ""

    def _bewerten(quellen: dict[str, tuple[str, str]],
                  gesehen: set[str]) -> list[dict]:
        raus: list[dict] = []
        for endadresse, html in quellen.values():
            schluessel = _schluessel(endadresse)
            if schluessel in gesehen or schluessel in bekannt:
                continue
            gesehen.add(schluessel)
            treffer = _bester_newsroom(html, endadresse, name)
            if treffer:
                treffer["pressepfad"] = _ist_pressepfad(endadresse)
                raus.append(treffer)
        return raus

    gesehen: set[str] = set()
    bewertet = _bewerten(geholt, gesehen)

    # Zwei Runden, weil die verlinkte Presseseite oft nur eine Drehscheibe ist:
    # telenor.no/om/presse-og-media traegt Kontaktadressen und einen Link "Les
    # flere nyheter" - die Meldungsliste selbst liegt eine Ebene tiefer unter
    # /pressemeldinger/. Die zweite Runde laeuft nur, wenn die erste nichts
    # Lesbares ergeben hat.
    quelle_der_links = dict(geholt)
    for _runde in (1, 2):
        if bewertet and any(t["pressepfad"] for t in bewertet):
            break
        verlinkt: list[str] = []
        for endadresse, html in quelle_der_links.values():
            verlinkt.extend(_presseseiten_aus_html(html, endadresse))
        offen = [u for u in dict.fromkeys(verlinkt)
                 if u not in geholt and _schluessel(u) not in bekannt][:4]
        if not offen:
            break
        neu: dict[str, tuple[str, str]] = {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            for u, ergebnis in zip(offen, pool.map(_hole_seite, offen)):
                if ergebnis:
                    geholt[u] = neu[u] = ergebnis
        bewertet.extend(_bewerten(neu, gesehen))
        quelle_der_links = neu

    # Echte Presseseiten zuerst, dann datierte, dann die ergiebigeren.
    bewertet.sort(key=lambda t: (t["pressepfad"], t["anteil"], t["n_items"]),
                  reverse=True)
    # Wenn es eine echte Presseseite gibt, ist alles andere auf dieser Domain
    # Beifang - die Startseite einer Telco ist ein Produktregal, keine
    # Meldungsliste, und sie besteht den Abnahme-Check nur zufaellig.
    echte = [t for t in bewertet if t["pressepfad"]]
    if echte:
        bewertet = echte
    return bewertet[:NEWSROOM_MAX_JE_ZIEL]


def _ziel_bearbeiten(ziel: dict, bekannt: set[str] | None = None,
                     newsroom: bool = True,
                     newsroom_immer: bool = False) -> list[dict]:
    """Ein Ziel in Stufen abarbeiten, mit Frueh-Abbruch.

    Warum Stufen: die erste Fassung probierte alle Seiten UND alle
    Kandidatenpfade UND alle Suffixe - rund 107 Abrufe je Firma. Da die
    Host-Drosselung (zu Recht) nur zwei gleichzeitige Verbindungen je Server
    zulaesst, brauchte ein einziges Ziel damit ueber eine Minute, acht Ziele
    ueber neun. Bei 112 Zielen ist das keine Breitensuche mehr.

    Die Abkuerzung kostet fast nichts: wenn eine Seite ihren Feed per
    <link rel="alternate"> selbst angibt, sind die Kandidatenpfade ueberfluessig
    - sie wuerden dieselbe Adresse noch einmal finden.

      Stufe 1  rel=alternate auf den genannten Seiten (billig, hohe Trefferrate)
      Stufe 2  nur wenn Stufe 1 leer blieb: die Kandidatenpfade auf der Domain
      Stufe 3  nur wenn beides leer blieb: /feed & Co. an den Seitenpfaden
      Stufe 4  nur wenn alles leer blieb: die Seite selbst als HTML-Newsroom

    Stufe 4 ist der Hebel aus Welle 3. Sie laeuft auf dem HTML, das Stufe 1
    ohnehin schon geholt hat, und kostet deshalb fast nichts extra.
    """
    seiten = ziel.get("seiten") or []
    if not seiten:
        return []
    bekannt = bekannt or set()
    basen = {f"{urlsplit(s).scheme}://{urlsplit(s).netloc}" for s in seiten}

    def _pruefe_viele(urls: list[str]) -> list[tuple[str, str]]:
        urls = [u for u in dict.fromkeys(urls) if _schluessel(u) not in bekannt]
        if not urls:
            return []
        with ThreadPoolExecutor(max_workers=8) as pool:
            return [r for r in pool.map(_pruefe_url, urls) if r]

    # --- Stufe 1: was die Seiten selbst angeben. Das HTML wird aufgehoben -
    # Stufe 4 liest es noch einmal, ohne einen zweiten Abruf.
    geholt: dict[str, tuple[str, str]] = {}
    angegeben: list[str] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for seite, ergebnis in zip(seiten, pool.map(_hole_seite, seiten)):
            if not ergebnis:
                continue
            geholt[seite] = ergebnis
            angegeben.extend(_feeds_aus_html(ergebnis[1], ergebnis[0]))
    gefunden = _pruefe_viele(angegeben)

    # --- Stufe 2: die ueblichen Pfade auf der Domain
    if not gefunden:
        gefunden = _pruefe_viele([b + p for b in sorted(basen)
                                  for p in KANDIDATENPFADE])

    # --- Stufe 3: /feed & Co. an den genannten Seitenpfaden
    if not gefunden:
        gefunden = _pruefe_viele([s.rstrip("/") + suffix for s in seiten
                                  for suffix in _SEITEN_SUFFIXE])

    # --- Stufe 4: kein Feed, aber vielleicht eine lesbare Artikelliste
    newsrooms: list[dict] = []
    if newsroom and (newsroom_immer or not gefunden):
        newsrooms = _newsroom_kandidaten(ziel, geholt, bekannt)

    treffer: list[dict] = []
    gesehen: set[str] = set()

    def _eintragen(url: str, typ: str, extra: dict | None = None) -> None:
        schluessel = _schluessel(url)
        if schluessel in gesehen or schluessel in bekannt:
            return
        gesehen.add(schluessel)
        eintrag = {"url": url, "type": typ}
        for feld in ("operator", "thema", "name", "website", "country",
                     "region"):
            if ziel.get(feld):
                eintrag[feld] = ziel[feld]
        eintrag.update(extra or {})
        eintrag.setdefault("begruendung",
                           "mechanisch gefunden - noch nicht abgenommen")
        eintrag["herkunft"] = ziel.get("herkunft", "mechanische Breitensuche")
        treffer.append(eintrag)

    for url, typ in gefunden:
        _eintragen(url, typ)
    for n in newsrooms:
        _eintragen(n["url"], "newsroom", {
            "item_selector": n["item_selector"],
            "begruendung": (
                "HTML-Newsroom ohne Feed"
                + ("" if n["pressepfad"]
                   else " (kein Pressepfad in der URL - Beifang)")
                + f" - im Suchlauf {n['n_items']} Meldungen, davon "
                + f"{n['n_datiert']} datiert ({n['anteil']:.0%}), "
                + f"{n['artikelanteil']:.0%} artikelhafte Adressen; "
                + "noch nicht abgenommen"),
        })
    return treffer


def _schluessel(url: str) -> str:
    return normalize_url(url).lower()


# --------------------------------------------------------------------------- #
# Rubrik-Feeds
#
# Eine Fachpresse-Site ist selten EINE Quelle. Sie hat Rubriken - /category/5g/,
# /tag/regulation/, /topics/iot/ - und fast jedes CMS liefert zu jeder Rubrik
# einen eigenen Feed. Der Hauptfeed zeigt dagegen immer nur die letzten 10 bis
# 30 Meldungen. Das ist reine Mechanik und kostet keine Recherche
# (AUFTRAG_1000_QUELLEN_WELLE3.md Abschnitt 4.3). Der Dublettencheck des
# Abnahme-Skripts faengt ab, was sich zu stark mit dem Hauptfeed ueberschneidet.
# --------------------------------------------------------------------------- #

# Rubriken, die in dieser Branche Inhalt tragen. Ohne diese Liste schlaegt eine
# WordPress-Site mit 300 Kategorien 300 Feeds vor, von denen 280 leer sind.
_RUBRIK_INTERESSANT = re.compile(
    r"(5g|6g|4g|lte|mobile|mobil|wireless|funk|network|netz|fiber|fibre|"
    r"glasfaser|broadband|breitband|regulat|policy|spectrum|frequenz|"
    r"satellit|satellite|ntn|iot|m2m|edge|cloud|ai|ki|artificial|security|"
    r"cyber|data ?cent|rechenzentr|operator|carrier|telco|telecom|roaming|"
    r"esim|mvno|open ?ran|oran|core|transport|enterprise|b2b|wholesale|"
    r"infrastructure|infrastruktur|technolog|innovat|private ?5g|"
    r"submarine|subsea|tower|antenn)", re.I)
# Rubriken, die es in dieser Branche zwar gibt, die aber nie eine Quelle sind.
_RUBRIK_UNINTERESSANT = re.compile(
    r"(uncategor|allgemein|sonstige|advertorial|sponsor|partner ?content|"
    r"press ?release ?service|webinar|event|award|jobs?|karriere|people|"
    r"opinion|kommentar|kolumne|podcast|video|gewinnspiel|deal|angebot|"
    r"schnaeppchen|test|review|ratgeber|tipps|how ?to|anleitung)", re.I)
# Pfadmuster, hinter denen eine Rubrik steckt.
_RUBRIK_PFAD = re.compile(
    r"/(category|categoria|categorie|kategorie|tag|tags|topic|topics|thema|"
    r"themen|rubrik|rubrique|section|sezione|seccion|canal|channel)/"
    r"([A-Za-z0-9][A-Za-z0-9_-]{1,40})/?$", re.I)
# Wie viele Rubrikfeeds je Site hoechstens vorgeschlagen werden. Die Kappung
# steht hier und wird im Lauf protokolliert - eine stille Kappung liest sich
# spaeter wie "da war nicht mehr".
RUBRIK_MAX_JE_SITE = 8


def _wp_rubriken(basis: str) -> list[tuple[str, str]]:
    """Rubriken ueber die WordPress-REST-Schnittstelle - exakt statt geraten.

    Liefert (Name, Feed-URL). Die REST-Antwort nennt die echte Rubrik-URL, es
    muss also nichts ueber die Pfadstruktur angenommen werden.
    """
    try:
        resp = fetch(f"{basis}/wp-json/wp/v2/categories?per_page=100",
                     HTTP_CFG, schnell=True)
        eintraege = resp.json()
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(eintraege, list):
        return []
    raus: list[tuple[str, str]] = []
    for e in eintraege:
        if not isinstance(e, dict):
            continue
        link = str(e.get("link") or "").strip()
        name = str(e.get("name") or e.get("slug") or "").strip()
        # Unter zehn Beitraegen ist eine Rubrik kein Kanal, sondern ein Etikett.
        if not link or not name or int(e.get("count") or 0) < 10:
            continue
        raus.append((name, link.rstrip("/") + "/feed/"))
    return raus


def _rubriken_aus_html(html: str, basis: str) -> list[tuple[str, str]]:
    """Rubriken, die die Seite selbst verlinkt - fuer alles, was kein WP ist."""
    soup = BeautifulSoup(html, "html.parser")
    basis_host = urlsplit(basis).netloc.removeprefix("www.")
    raus: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        url = urljoin(basis, (a["href"] or "").strip())
        teile = urlsplit(url)
        if teile.scheme not in ("http", "https"):
            continue
        host = teile.netloc.removeprefix("www.")
        if host != basis_host and not host.endswith("." + basis_host):
            continue
        treffer = _RUBRIK_PFAD.search(teile.path)
        if not treffer:
            continue
        name = " ".join(a.get_text(" ", strip=True).split()) or treffer.group(2)
        pfad = teile.path.rstrip("/")
        raus.append((name, f"{teile.scheme}://{teile.netloc}{pfad}/feed"))
    return list(dict.fromkeys(raus))


def _rubrik_ziel(site: dict, bekannt: set[str]) -> list[dict]:
    """Alle Rubrikfeeds einer Site einsammeln und auf Auslieferung pruefen."""
    basis = site["basis"]
    rubriken = _wp_rubriken(basis)
    if not rubriken:
        # Die konfigurierte Quellen-URL ist meist der FEED selbst - dort steht
        # keine Rubriknavigation drin. Die Rubriken stehen im Menue der Site,
        # also auf der Wurzel; die konfigurierte Seite ist nur der Rueckfall
        # fuer Sites, deren Wurzel eine Weiterleitung ist.
        for seite_url in (basis, site.get("seite")):
            if not seite_url:
                continue
            seite = _hole_seite(seite_url)
            if seite:
                rubriken = _rubriken_aus_html(seite[1], seite[0])
            if rubriken:
                break

    passend = [(name, url) for name, url in rubriken
               if _RUBRIK_INTERESSANT.search(name)
               and not _RUBRIK_UNINTERESSANT.search(name)
               and _schluessel(url) not in bekannt]
    # Nach Name eindeutig, damit /category/5g/feed und /tag/5g/feed nicht beide
    # durchlaufen.
    einmalig: dict[str, tuple[str, str]] = {}
    for name, url in passend:
        einmalig.setdefault(name.lower(), (name, url))
    auswahl = list(einmalig.values())
    gekappt = max(0, len(auswahl) - RUBRIK_MAX_JE_SITE)
    auswahl = auswahl[:RUBRIK_MAX_JE_SITE]
    if gekappt:
        print(f"    (gekappt: {gekappt} weitere Rubriken auf "
              f"{urlsplit(basis).netloc} nicht geprueft)")
    if not auswahl:
        return []

    with ThreadPoolExecutor(max_workers=6) as pool:
        ergebnisse = list(pool.map(_pruefe_url, [u for _, u in auswahl]))

    treffer: list[dict] = []
    for (name, _), ergebnis in zip(auswahl, ergebnisse):
        if not ergebnis:
            continue
        url, typ = ergebnis
        if _schluessel(url) in bekannt:
            continue
        eintrag = {"url": url, "type": typ,
                   "begruendung": f'Rubrikfeed "{name}" von '
                                  f"{urlsplit(basis).netloc} - noch nicht "
                                  f"abgenommen",
                   "herkunft": "Rubriksuche"}
        for feld in ("operator", "thema", "name", "website", "country",
                     "region"):
            if site.get(feld):
                eintrag[feld] = site[feld]
        eintrag["label"] = name
        treffer.append(eintrag)
    return treffer


def sites_aus_konfiguration(root: Path) -> list[dict]:
    """Jede Site, die heute schon eine Quelle stellt - einmal je Domain."""
    cfg = load_config(root)
    sites: dict[str, dict] = {}

    def _merken(url: str, felder: dict) -> None:
        teile = urlsplit(url)
        if teile.scheme not in ("http", "https"):
            return
        basis = f"{teile.scheme}://{teile.netloc}"
        if basis in sites:
            return
        sites[basis] = {"basis": basis, "seite": url, **felder}

    for op in cfg.operators:
        for src in op.sources:
            if src.crawlable:
                _merken(src.url, {"operator": op.name, "website": op.website,
                                  "country": op.country,
                                  "region": op.region_key})
    for src in cfg.news_sources:
        _merken(src.url, {"name": src.name})
    for src in cfg.tech_sources:
        if src.crawlable:
            _merken(src.url, {"thema": src.theme.removeprefix("thema:"),
                              "name": src.name})
    return list(sites.values())


def ziele_aus_watchlist(root: Path) -> list[dict]:
    """Zweitkanaele: jede Firma, die schon in der Konfiguration steht.

    Der billigste Zugewinn im ganzen Ausbau (Auftrag Abschnitt 4): kein
    Unternehmen muss recherchiert werden, und erst 10 von 85 Betreibern haben
    ueberhaupt mehr als einen Kanal. Als Suchseiten dienen die bereits
    eingetragenen Quellen-URLs, die Unternehmenswebsite und die ueblichen
    Newsroom-Pfade darauf.
    """
    cfg = load_config(root)
    ziele: list[dict] = []
    for op in cfg.operators:
        seiten: list[str] = []
        for src in op.sources:
            seiten.append(src.url)
        if op.website:
            # Nur die Wurzel, NICHT die geratenen Newsroom-Pfade: die
            # bestehende Quellen-URL zeigt bereits auf den Newsroom, und
            # rel=alternate steht bei fast jedem CMS im <head> jeder Seite.
            # Dreizehn Ratepfade je Firma waren der Grund, warum ein
            # Durchgang ueber 112 Betreiber nicht fertig wurde.
            basis = op.website if op.website.startswith("http") \
                else f"https://www.{op.website}"
            seiten.append(basis.rstrip("/"))
        if seiten:
            ziele.append({"operator": op.name, "website": op.website,
                          "country": op.country, "region": op.region_key,
                          "seiten": list(dict.fromkeys(seiten)),
                          "herkunft": "Zweitkanal (aus Watchlist)"})
    for src in cfg.tech_sources:
        ziele.append({"thema": src.theme.removeprefix("thema:"),
                      "name": src.name, "seiten": [src.url],
                      "herkunft": "Zweitkanal (aus tech_sources)"})
    return ziele


def ziele_aus_firmen(pfad: Path) -> list[dict]:
    """Neue Unternehmen: Name + Domain reichen, die Newsroom-Pfade raten wir."""
    roh = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    firmen = roh.get("firmen") if isinstance(roh, dict) else roh
    ziele: list[dict] = []
    for f in firmen or []:
        domain = str(f.get("domain") or "").strip().rstrip("/")
        if not domain:
            continue
        basis = domain if domain.startswith("http") else f"https://www.{domain}"
        ziel = {"seiten": [basis.rstrip("/") + p for p in NEWSROOM_PFADE],
                "website": domain,
                "herkunft": f.get("herkunft", "Firmenliste")}
        for feld in ("operator", "thema", "name", "country", "region"):
            if f.get(feld):
                ziel[feld] = f[feld]
        if not ziel.get("operator") and not ziel.get("thema") and f.get("name"):
            ziel["operator"] = f["name"]
        ziele.append(ziel)
    return ziele


def bekannte_urls(root: Path) -> set[str]:
    """Alles, was schon konfiguriert ist - das schlaegt niemand noch mal vor."""
    try:
        cfg = load_config(root)
    except Exception:  # noqa: BLE001
        return set()
    urls = {_schluessel(s.url) for op in cfg.operators for s in op.sources}
    urls |= {_schluessel(s.url) for s in cfg.news_sources}
    urls |= {_schluessel(s.url) for s in cfg.tech_sources}
    return urls


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("ziele", type=Path, nargs="?")
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--aus-watchlist", action="store_true",
                   help="Ziele aus der bestehenden Konfiguration bauen "
                        "(Zweitkanaele) - keine Recherche noetig")
    p.add_argument("--firmen", type=Path,
                   help="YAML mit name+domain je Firma (neue Unternehmen)")
    p.add_argument("--cache", type=Path,
                   help="bereits bearbeitete Ziele ueberspringen "
                        "(Wiederaufnahme nach Abbruch)")
    p.add_argument("--limit", type=int, help="nur die ersten N Ziele")
    p.add_argument("--rubriken", action="store_true",
                   help="Rubrikfeeds (/category/<x>/feed, /tag/<x>/feed, "
                        "WordPress-Kategorien) jeder bereits konfigurierten "
                        "Site suchen - statt der Zielsuche")
    p.add_argument("--kein-newsroom", action="store_true",
                   help="Stufe 4 (HTML-Newsrooms ohne Feed) ueberspringen")
    p.add_argument("--newsroom-immer", action="store_true",
                   help="Newsroom-Erkennung auch dann laufen lassen, wenn die "
                        "Firma schon einen Feed hergibt (Zweitkanal)")
    # Der Deckel der Breitensuche ist NICHT die Zahl der Ziele, sondern die
    # Host-Drosselung: eine Firma ist ein Server, und alle 40+ Adressen eines
    # Ziels laufen gegen genau diesen einen. Mit 4 gleichzeitigen Verbindungen
    # brauchte ein Durchgang ueber 338 Firmen hochgerechnet zwei Stunden, von
    # denen fast alles Wartezeit auf 404er war. Die Suche ist nicht der Lauf -
    # sie darf hier mehr riskieren, solange die Drosselung ueberhaupt greift.
    p.add_argument("--host-parallel", type=int, default=8,
                   help="gleichzeitige Verbindungen je Server (Standard 8)")
    p.add_argument("--host-pause", type=float, default=0.05,
                   help="Mindestabstand zwischen zwei Abrufen je Server")
    args = p.parse_args(argv)

    root = args.root.resolve()
    # Ohne Drosselung schlagen bei 16 gleichzeitigen Zielen mal eben 200
    # Verbindungen gleichzeitig los - und mehrere davon auf denselben Server.
    configure_throttle(args.host_parallel, args.host_pause)

    ziele: list[dict] = []
    if args.ziele:
        roh = yaml.safe_load(args.ziele.read_text(encoding="utf-8")) or {}
        ziele.extend(roh.get("ziele") if isinstance(roh, dict) else roh)
    if args.aus_watchlist:
        ziele.extend(ziele_aus_watchlist(root))
    if args.firmen:
        ziele.extend(ziele_aus_firmen(args.firmen))
    if args.rubriken:
        ziele.extend(sites_aus_konfiguration(root))
    if not ziele:
        p.error("Keine Ziele: Datei angeben, --aus-watchlist, --firmen "
                "oder --rubriken")

    bekannt = bekannte_urls(root)
    erledigt: set[str] = set()
    alle: list[dict] = []
    if args.cache and args.cache.exists():
        gespeichert = yaml.safe_load(args.cache.read_text(encoding="utf-8")) or {}
        alle = gespeichert.get("kandidaten") or []
        erledigt = set(gespeichert.get("erledigte_ziele") or [])
        print(f"Cache: {len(erledigt)} Ziele erledigt, "
              f"{len(alle)} Kandidaten bereits gefunden")

    def _kennung(z: dict) -> str:
        if z.get("basis"):
            return z["basis"]
        return z.get("operator") or z.get("name") or z.get("thema") or \
            (z.get("seiten") or ["?"])[0]

    def _bearbeiten(z: dict) -> list[dict]:
        if z.get("basis"):
            return _rubrik_ziel(z, bekannt)
        return _ziel_bearbeiten(z, bekannt, not args.kein_newsroom,
                                args.newsroom_immer)

    offen = [z for z in ziele if _kennung(z) not in erledigt]
    if args.limit:
        offen = offen[:args.limit]
    print(f"{len(offen)} Ziele werden bearbeitet "
          f"({len(bekannt)} URLs sind bereits konfiguriert und werden "
          f"uebersprungen)")

    fertig = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futs = {pool.submit(_bearbeiten, z): z for z in offen}
        for fut in as_completed(futs):
            ziel = futs[fut]
            fertig += 1
            try:
                gefunden = fut.result()
            except Exception as exc:  # noqa: BLE001
                print(f"  ! {_kennung(ziel)}: {exc}")
                continue
            erledigt.add(_kennung(ziel))
            if gefunden:
                print(f"{len(gefunden):>3} Kandidat(en)  {_kennung(ziel)}")
                for g in gefunden:
                    print(f"       {g['type']:9} {g['url']}")
            alle.extend(gefunden)
            # Nach jedem Ziel sichern: bei 800 Zielen ist ein Abbruch die
            # Regel, nicht die Ausnahme.
            if args.cache and fertig % 10 == 0:
                args.cache.write_text(yaml.safe_dump(
                    {"kandidaten": alle, "erledigte_ziele": sorted(erledigt)},
                    allow_unicode=True, sort_keys=False), encoding="utf-8")

    # Dubletten unter den Funden selbst (mehrere Ziele finden denselben Feed)
    einmalig: dict[str, dict] = {}
    for k in alle:
        einmalig.setdefault(_schluessel(k["url"]), k)
    alle = list(einmalig.values())

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        yaml.safe_dump({"kandidaten": alle}, allow_unicode=True, sort_keys=False),
        encoding="utf-8")
    if args.cache:
        args.cache.write_text(yaml.safe_dump(
            {"kandidaten": alle, "erledigte_ziele": sorted(erledigt)},
            allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"\n{len(alle)} Kandidaten -> {args.out}")
    print("Naechster Schritt: python scripts/pruefe_quellenvorschlag.py "
          f"{args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
