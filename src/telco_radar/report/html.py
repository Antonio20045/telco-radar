"""Static report site generator - Vodafone light design."""
from __future__ import annotations

import html as html_lib
import json
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import markdown as md
from jinja2 import Environment, FileSystemLoader, select_autoescape
from bs4 import BeautifulSoup

from . import bilder as report_bilder
from . import diff_bilder
from . import differenzierung_bericht
from . import differenzierung_view
from . import fruehwarnung as fruehwarnung_mod
from . import lieferzeit_view as lieferzeit_view_mod
from . import luecken as luecken_mod
from . import newsletter_protokoll
from . import rechtstexte as rechtstexte_mod
from . import seit as seit_mod
from . import verlauf as verlauf_mod
from . import suchindex
from .differentiation import DIFF_THEMES
from .promo import prepare_promo_view
from .thema import build_thema_view
from .wettbewerb import anker as _wb_anker, build_wettbewerb_view
from ..analyze import ctm
from ..analyze import highlight_topics
from ..analyze.diff_curator import DiffStore
from ..analyze.category_sweep import DiffDB, THEMES as SWEEP_THEMES
from ..analyze.promo_ranker import MECHANICS as PROMO_MECHANICS
from ..promo_config import load_promo_config
from ..textwerkzeug import (ABKUERZUNGEN as _ABK, gewicht as _gewicht,
                            haeufigkeiten as _haeufigkeiten, saetze as _saetze,
                            slug as _tw_slug, wortmenge as _wortmenge)
from .. import promo_bilder

_DIFF_COLOR = {t["key"]: t["color"] for t in DIFF_THEMES}

log = logging.getLogger(__name__)

_TEMPLATES = Path(__file__).parent / "templates"
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
# Sources removed from the configuration must not keep polluting historical
# public pages. The raw reports remain available for auditability, but their
# stale highlights and source-linked prose are suppressed at render time.
_SUPPRESSED_SOURCE_DOMAINS = {"inside-digital.de"}

RELEVANCE_LABELS = {
    5: "Sofort ansehen", 4: "Wichtig", 3: "Beobachten",
    2: "Randnotiz", 1: "Randnotiz", 0: "Unbewertet",
}
CATEGORY_COLORS = {
    "Produktlaunch": "#e60000", "Tarif/Pricing": "#ac1811", "Kampagne": "#c2185b",
    "Partnerschaft": "#3860be", "Netz/Technologie": "#5a6b9e",
    "Regulierung": "#8a7a2f", "M&A": "#25282b", "Finanzen": "#7e7e7e",
    "Sonstiges": "#a8a8a8", "Unbewertet": "#c4c4c4",
}
MONTHS_DE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
             "August", "September", "Oktober", "November", "Dezember"]


def _fmt_date_de(iso: str) -> str:
    try:
        d = datetime.fromisoformat(iso)
        return f"{d.day}. {MONTHS_DE[d.month - 1]} {d.year}"
    except (ValueError, IndexError):
        return iso


def _fmt_monat_de(iso_monat: str) -> str:
    """"2026-08" -> "August 2026" - die Ueberschrift einer Monatsgruppe in
    der Chronik der Wettbewerbsseite."""
    try:
        jahr, monat = (iso_monat or "").split("-")[:2]
        return f"{MONTHS_DE[int(monat) - 1]} {jahr}"
    except (ValueError, IndexError):
        return iso_monat


def _env() -> Environment:
    # "j2" MUSS in der Liste stehen. select_autoescape() sieht nur die LETZTE
    # Dateiendung an, und jede Vorlage hier heisst "*.html.j2" - mit
    # ["html"] allein war das Escaping also auf JEDER Seite aus. Aufgefallen
    # am 04.08.2026: Themenlabels wie "Chips & Modems" landeten als rohes "&"
    # im HTML. Das ist die harmlose Seite davon. Die ernste: in den Bericht
    # fliessen Ueberschriften FREMDER Newsrooms und Fachpresse-Feeds
    # (h.de_title, h.url) - ohne Escaping steht dort, was ein beliebiger
    # beobachteter Anbieter in seinen Titel schreibt. Mit dem Quellen-Ausbau
    # sind das rund 130 Absender.
    # Die vier Stellen, an denen absichtlich fertiges HTML eingesetzt wird
    # (briefing_html, diff_report_html, promo_report_html, explorer_json),
    # tragen bereits "| safe" - die Vorlagen waren also immer fuer aktives
    # Escaping geschrieben, es war nur nie eingeschaltet.
    env = Environment(loader=FileSystemLoader(_TEMPLATES),
                      autoescape=select_autoescape(["html", "htm", "xml", "j2"]))
    env.filters["domain"] = lambda u: urlsplit(u or "").netloc.removeprefix("www.")
    env.filters["date_de"] = _fmt_date_de
    env.filters["monat_de"] = _fmt_monat_de
    return env


_MD_TAGS = {"a", "blockquote", "br", "code", "em", "h2", "h3", "h4",
            "li", "ol", "p", "pre", "strong", "ul"}
_MD_DANGEROUS_TAGS = {"base", "embed", "form", "iframe", "math", "object",
                      "script", "style", "svg"}


def _md_to_html(text: str, inline: bool = False) -> str:
    """Render the editor's Markdown while stripping raw HTML and unsafe URLs.

    `inline=True` liefert den Text OHNE das umschliessende <p> - fuer Stellen,
    an denen das Ergebnis in ein vorhandenes Element gesetzt wird (ein
    Listenpunkt der Muster-Liste zum Beispiel). Ein <p> in einem <li> reisst
    dort den Zeilenfluss auf, in dem der fette Musterbegriff steht.
    """
    rendered = md.markdown(text or "", extensions=["extra", "sane_lists"])
    soup = BeautifulSoup(rendered, "html.parser")
    if inline:
        for absatz in soup.find_all("p"):
            absatz.unwrap()
    for tag in soup.find_all(True):
        if tag.name in _MD_DANGEROUS_TAGS:
            tag.decompose()
            continue
        if tag.name not in _MD_TAGS:
            tag.unwrap()
            continue
        for attr in list(tag.attrs):
            if tag.name == "a" and attr == "href":
                scheme = urlsplit(str(tag.attrs[attr]).strip()).scheme.lower()
                if scheme in {"", "http", "https"}:
                    continue
            del tag.attrs[attr]
    return str(soup)


# Der Anker der Berichtsabschnitte und der Dateiname einer Themenseite
# muessen aus demselben Titel dasselbe ergeben - deshalb steht die Rechnung
# in textwerkzeug.py und nicht hier (siehe dortiger Modulkopf).
_slug = _tw_slug


def _anchor_headings(html: str) -> tuple[str, list[dict]]:
    """Gibt jeder h2-Ueberschrift des Berichts einen Anker und liefert die
    Gliederung zurueck.

    Muss NACH _md_to_html() laufen: die Sanitisierung dort loescht jedes
    Attribut, ein vorher gesetztes id waere also wieder weg.

    Der Bericht vom 05.08.2026 hat 2863 Woerter in elf Abschnitten und stand
    als ein einziger Prosablock auf der Seite - ohne Inhaltsverzeichnis, ohne
    Sprungmarken, fuer eine Zielgruppe ohne Technikhintergrund.
    """
    if not html:
        return html, []
    soup = BeautifulSoup(html, "html.parser")
    toc: list[dict] = []
    vergeben: set[str] = set()
    for h in soup.find_all("h2"):
        titel = h.get_text(" ", strip=True)
        if not titel:
            continue
        anker = _slug(titel)
        if anker in vergeben:          # zwei gleichnamige Abschnitte
            n = 2
            while f"{anker}-{n}" in vergeben:
                n += 1
            anker = f"{anker}-{n}"
        vergeben.add(anker)
        h["id"] = anker
        toc.append({"id": anker, "title": titel})
    return str(soup), toc


def _lesezeit(md_text: str) -> int:
    """Lesezeit in Minuten, konservativ mit 200 Woertern/Minute gerechnet."""
    woerter = len((md_text or "").split())
    return max(1, round(woerter / 200)) if woerter else 0


def _json_for_script(value: object) -> str:
    """Serialize public source text safely inside an application/json script."""
    return (json.dumps(value, ensure_ascii=False)
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026")
            .replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029"))


def _redirect_html(ziel: str) -> str:
    """Weiterleitungsseite fuer einen alten Dateinamen.

    Render ist eine Static Site - es gibt keine Serverregel, in die man eine
    301 schreiben koennte. Meta-Refresh plus sichtbarer Link ist deshalb die
    ganze Mechanik; ein Skript waere unnoetig und wuerde ohne JS scheitern.
    """
    ziel_escaped = html_lib.escape(ziel, quote=True)
    return (
        "<!DOCTYPE html>\n<html lang=\"de\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<meta http-equiv=\"refresh\" content=\"0; url={ziel_escaped}\">\n"
        f"<link rel=\"canonical\" href=\"{ziel_escaped}\">\n"
        "<meta name=\"robots\" content=\"noindex\">\n"
        "<title>Weitergeleitet – Vodafone Product and Services Insights</title>\n</head>\n"
        "<body style=\"font-family:Inter,Arial,sans-serif;padding:40px\">\n"
        f"<p>Diese Seite ist umgezogen. <a href=\"{ziel_escaped}\">Weiter zu "
        f"{ziel_escaped}</a></p>\n</body>\n</html>\n")


def _load_reports(reports_dir: Path) -> list[dict]:
    reports: dict[str, dict] = {}
    for f in sorted(reports_dir.glob("*.json")):
        if not _DATE_RE.fullmatch(f.stem):
            continue
        try:
            reports[f.stem] = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.warning("Skipping corrupt report json: %s", f)
    for f in sorted(reports_dir.glob("*.md")):
        if _DATE_RE.fullmatch(f.stem) and f.stem not in reports:
            reports[f.stem] = {"date": f.stem, "generated_with_llm": False,
                               "stats": {}, "briefing_md": f.read_text(encoding="utf-8"),
                               "regions": {}}
    return [reports[k] for k in sorted(reports, reverse=True)]


def _load_latest_diff_report(reports_dir: Path) -> dict | None:
    """Load the newest generated prose report for the differentiation tab."""
    if not reports_dir.exists():
        return None
    candidates = [f for f in reports_dir.glob("*.md")
                  if _DATE_RE.fullmatch(f.stem)]
    if not candidates:
        return None
    path = max(candidates, key=lambda f: f.stem)
    try:
        return {"date": path.stem,
                "briefing_md": path.read_text(encoding="utf-8")}
    except OSError:
        log.warning("Differenzierungsbericht nicht lesbar: %s", path)
        return None


_IST_PLATZHALTER = re.compile(
    r"(kein[^,]*betreiber|keine?r?|branche|diverse?|mehrere|unbekannt|"
    r"n/?a|-+|allgemein)", re.I)


def _flatten(report: dict) -> list[dict]:
    out = []
    for region_name, region in (report.get("regions") or {}).items():
        for h in region.get("highlights") or []:
            h = dict(h)
            if _is_suppressed_source(h):
                continue
            h["region"] = region_name
            h["relevance"] = h.get("relevance") or 0
            h["relevance_label"] = RELEVANCE_LABELS.get(h["relevance"], "")
            h["category"] = h.get("category") or "Sonstiges"
            dom = urlsplit(h.get("url") or "").netloc.removeprefix("www.")
            h["source_domain"] = dom
            h["source_label"] = h.get("source") or dom
            # Der Analyst traegt bei branchenweiten Meldungen Platzhalter in
            # das Betreiberfeld ("kein spezifischer Betreiber", "Branche").
            # Als Rubrikzeile ueber einer Titelseiten-Schlagzeile gelesen ist
            # das kein Absender, sondern eine Ausrede - dann steht dort die
            # Quelle, die die Meldung wirklich verantwortet.
            if _IST_PLATZHALTER.fullmatch((h.get("operator") or "").strip()):
                h["operator"] = ""
            h["de_title"] = _first_sentence(h.get("summary") or "", 150) or h.get("title") or ""
            # Jede Meldung traegt ihre vollstaendige Ueberschrift - die
            # Meldungsseite zeigt alle, nicht nur die der Titelseite.
            h["schlagzeile"] = _schlagzeile(h)
            # ... und ihr Ressort. Titelseite und Meldungsseite gruppieren
            # beide danach; die Zuordnung darf nur an EINER Stelle stehen.
            h["ressort"] = _ressort(h)
            h["ressort_label"] = _RESSORT_LABEL[h["ressort"]]
            # Die CTM-Linse. Berichte von vor dem 08.08.2026 tragen das Feld
            # nicht; fuer sie gilt 1 ("Kontext"), damit eine Archivwoche ihre
            # Reihenfolge behaelt, statt komplett auf 0 zu fallen.
            try:
                h["ctm_bezug"] = int(h.get("ctm_bezug"))
            except (TypeError, ValueError):
                h["ctm_bezug"] = 1
            h.setdefault("ctm_label", ctm.STUFEN_LABEL.get(h["ctm_bezug"], ""))
            out.append(h)
    # Sortiert wird mit demselben Schluessel wie die Titelseite
    # (`_rangschluessel`, Strategie E6, 27.08.2026): die Prioritaet fuehrt,
    # der CTM-Bezug bricht nur noch den Gleichstand. Bis zum 27.08.2026 fuehrte
    # der CTM-Bezug - das war der Eingriff vom 08.08.2026, der "OpenAI macht
    # ChatGPT gratis unbegrenzt" ueber die Telekom-Flat fuer 34,95 Euro stellen
    # sollte. Am 27.08.2026 hat sich das gegen den Leser gewendet, siehe
    # `_rangschluessel` fuer die Begruendung.
    out.sort(key=lambda h: (*_rangschluessel(h), h.get("date") or ""),
             reverse=True)
    for i, h in enumerate(out):
        h["id"] = i
    return out


def _is_suppressed_source(item: dict) -> bool:
    host = urlsplit(item.get("url") or "").netloc.removeprefix("www.").lower()
    source = (item.get("source") or "").strip().lower()
    return source == "inside digital" or host in _SUPPRESSED_SOURCE_DOMAINS \
        or any(host.endswith("." + domain) for domain in _SUPPRESSED_SOURCE_DOMAINS)


def _strip_suppressed_source_content(text: str) -> str:
    """Remove stale source-linked paragraphs/lines from historical briefings."""
    blocks = re.split(r"\n\s*\n", text or "")
    kept = [block for block in blocks if not any(
        domain in block.lower() for domain in _SUPPRESSED_SOURCE_DOMAINS
    ) and "inside digital" not in block.lower()]
    cleaned = "\n\n".join(kept)
    return re.sub(r"(?im)^.*(?:inside-digital\.de|inside digital).*$\n?", "", cleaned).strip()


TECH_THEMES = [
    ("5G Standalone", ["standalone", "5g sa", "5g-sa", "5g core", "sa network", "5g+"]),
    ("Satellit / NTN", ["satellite", "satellit", "ntn", "direct-to-cell", "direct to cell",
                          "starlink", "spacemobile", "non-terrestrial", "d2c", "leo "]),
    ("KI / AI", [" ai ", " ai-", "a.i.", "artificial intelligence", "genai", "gen ai",
                  "agentic", "machine learning", " llm", "copilot", " ki ", "ki-"]),
    ("Glasfaser / FTTH", ["fiber", "fibre", "ftth", "glasfaser", "gigabit", "broadband"]),
    ("Private Networks", ["private 5g", "private network", "campus network", "private-5g"]),
    ("IoT / eSIM", ["iot", "esim", "e-sim", "m2m", "internet of things"]),
    ("Cloud / Edge", ["cloud", "edge computing", "hyperscaler", "edge-computing", " mec "]),
    ("Open RAN", ["open ran", "openran", "o-ran", "oran", "vran", "v-ran"]),
    ("6G", ["6g"]),
    ("FWA", ["fwa", "fixed wireless", "fixed-wireless"]),
]
def _tag_tech(text):
    t = " " + (text or "").lower() + " "
    return [name for name, kws in TECH_THEMES if any(k in t for k in kws)]


# ------------------------------------------------------------------ Ressorts
# Eine Zeitung hat Ressorts, und zwar VOR der Nachrichtenlage: der Leser
# weiss, wo Netzthemen stehen, bevor er die Ausgabe aufschlaegt. Die
# Zuordnung kommt aus der `category`, die der Analyst ohnehin je Meldung
# vergibt - keine zweite Klassifizierung, kein zusaetzlicher LLM-Aufruf.
#
# Zwei Kategorien pro Ressort zusammenzufassen ist Absicht: "Produktlaunch"
# und "Tarif/Pricing" sind fuer den Leser dasselbe Ressort ("was kann ich
# kaufen und was kostet es"), und ein Ressort mit fuenf Meldungen ist keins.
RESSORTS: list[tuple[str, str, set[str]]] = [
    ("netz", "Netz & Technik", {"Netz/Technologie"}),
    ("tarife", "Tarife & Angebote",
     {"Tarif/Pricing", "Produktlaunch", "Kampagne"}),
    ("regulierung", "Regulierung & Politik", {"Regulierung"}),
    ("geld", "Geld & Übernahmen", {"Finanzen", "M&A"}),
    ("partner", "Partnerschaften", {"Partnerschaft"}),
    ("vermischt", "Vermischtes", {"Sonstiges"}),
]
# Die eine Ausnahme von "Ressort = Kategorie": Satellit/NTN. Sonst lieferte
# "Netz/Technologie" ein Viertel der ganzen Ausgabe (46 von 193 am
# 06.08.2026, plus 28 Satellitenmeldungen darin), und das ist kein Ressort,
# das ist ein Sammelbecken. Der Themen-Tagger steht ohnehin schon da.
_SATELLIT = ("satellit", "Satellit & Direct-to-Cell")
_RESSORT_REIHENFOLGE = ["netz", "tarife", _SATELLIT[0], "regulierung",
                        "geld", "partner", "vermischt"]
_RESSORT_LABEL = dict([(k, l) for k, l, _ in RESSORTS] + [_SATELLIT])


def _ressort(h: dict) -> str:
    """Der Ressortschluessel einer Meldung. Jede bekommt genau einen."""
    if "Satellit / NTN" in _tag_tech(f"{h.get('title', '')} {h.get('summary', '')}"):
        return _SATELLIT[0]
    kategorie = h.get("category") or "Sonstiges"
    for key, _label, kategorien in RESSORTS:
        if kategorie in kategorien:
            return key
    return "vermischt"


def _bildbreite(h: dict) -> int:
    """Breite des abgelegten Bildes in Pixeln, 0 wenn es keins gibt.

    `image_w` schreibt report/bilder.py beim Ablegen. Berichte von vor dem
    06.08.2026 haben das Feld nicht - fuer die gilt 0, sie landen also nie
    in einer Position, die ein grosses Bild verlangt. Genau richtig: ihre
    Bilder waren die 120x90-Vorschaubilder, um die es hier geht.
    """
    return int(h.get("image_w") or 0) if h.get("image") else 0


# Woerter, die keinen Absender unterscheiden. Ohne diese Liste faende
# "T-Mobile US" und "Mobile World Live" denselben Namen.
_GENERISCHE_NAMENSWOERTER = {
    "group", "telecom", "telecoms", "mobile", "communications", "holdings",
    "international", "limited", "global", "media", "news", "corp", "world",
    "corporation", "company", "networks", "network", "digital", "wireless",
}


def _kennwoerter(name: str) -> frozenset[str]:
    """Die unterscheidenden Woerter eines Absendernamens.

    Dient nur einem Zweck: erkennen, dass "Starlink (SpaceX)",
    "SpaceX / Starlink" und "SpaceX" derselbe Absender sind. Am 06.08.2026
    standen dadurch fuenf von sieben Zeilen der Spalte "Was wichtig ist"
    unter demselben Namen - eine Zeitung bringt nicht fuenfmal dieselbe
    Firma auf der Titelseite, auch wenn die Nachrichtenlage es hergibt.
    """
    woerter = re.findall(r"[a-zäöüß0-9]{4,}", (name or "").lower())
    return frozenset(w for w in woerter
                     if w not in _GENERISCHE_NAMENSWOERTER)


# Wie oft ein Absender oberhalb der Falz vorkommen darf.
_MAX_JE_ABSENDER = 2

# Zeilen der Digest-Spalte "Was wichtig ist". Steht als Konstante da, weil
# die Spalte in ZWEI Schritten gefuellt wird (erst die Meldungen der Stufe
# "Direkt fuer uns", dann der Rest) - zwei Literale 7 laufen auseinander,
# und das Ergebnis waere eine Spalte mit acht oder sechs Zeilen.
_WICHTIG_ZEILEN = 7


def _rangschluessel(h: dict) -> tuple[int, int]:
    """Der Rang einer Meldung: Prioritaet vor CTM-Bezug.

    Antonio, 27.08.2026 (Strategie E6): "wie kann es sein dass artikel mit
    prioriät von 3 auf der titelseite landen ... die wichtigsten artikel
    sollen auch an erster reihe stehen." Bis dahin fuehrte der CTM-Bezug -
    das war der Eingriff vom 08.08.2026, der "OpenAI macht ChatGPT gratis
    unbegrenzt" (branchenweit) ueber die Telekom-Flat fuer 34,95 Euro
    (Heimatmarkt, aber schwaecher bewertet) stellen sollte. Am 27.08.2026 hat
    sich das gegen den Leser gewendet: acht relevance=5-Meldungen ohne jeden
    CTM-Bezug saettigten alle Bildplaetze, waehrend eine hoch bewertete
    Heimatmarkt-Meldung dahinter verschwand. Die Prioritaet fuehrt jetzt, der
    CTM-Bezug bricht nur noch den Gleichstand - er bleibt also weiterhin der
    Grund, warum zwei gleich dringliche Meldungen unterschiedlich stehen,
    kann aber keine schwaecher bewertete mehr nach vorne ziehen.

    Dieselben zwei Schluessel, nach denen `_flatten` sortiert - hier als
    eigene Funktion, weil die Titelseite sie nicht nur zum Sortieren braucht,
    sondern zum VERGLEICHEN: der rote Faden darf nur unter Gleichrangigen
    waehlen (siehe `_titelseite`). `_ctm_achse` (Kurzpfad) rechnet bewusst
    weiter in der ALTEN Reihenfolge - das ist eine andere Frage ("was betrifft
    unser Portfolio unmittelbar?"), keine Kopie dieser Funktion.
    """
    return (int(h.get("relevance") or 0), int(h.get("ctm_bezug") or 0))


# ------------------------------------------------------------- roter Faden
# Antonio am 07.08.2026: "der rote Faden fehlt mir noch ueberall". Gemessen
# war das keine Geschmacksfrage - die Titelseite fuehrte mit einer anderen
# Geschichte als der Wochenbericht, weil beide unabhaengig voneinander
# sortierten: die Seite nach Dringlichkeit und Bildbreite, der Bericht nach
# dem Urteil der Chefredaktion.
#
# Der Bericht beginnt mit einer Aufzaehlung "Auf einen Blick" - drei Saetze,
# die sagen, worum es in dieser Woche geht. Die uebernimmt jetzt die
# Titelseite als Fuehrung: Aufmacher und zweite Reihe belegen diese drei
# Saetze, in ihrer Reihenfolge. Das ist der Faden, und er ist nachpruefbar -
# nicht "die Seite wirkt geordneter".
_FADEN_MAX = 3
_FADEN_MIND_TREFFER = 2
# Wie viele Meldungen je Fuehrungssatz vorgemerkt werden. Mehr als eine,
# weil der Aufmacher ein Bild von mindestens 800 px verlangt: hat die
# bestbelegte Meldung eines Satzes keins, soll die Seite bei DIESEM Satz
# weitersuchen, statt zum naechsten zu springen. Genau das war am 07.08.2026
# der Fall - der Bericht fuehrte mit SpaceX, die beste SpaceX-Meldung hatte
# 720 px, und die Titelseite fuehrte deshalb mit der Telekom.
_FADEN_KANDIDATEN = 4


def _fuehrende_saetze(md_text: str) -> list[str]:
    """Die Punkte aus "Auf einen Blick" - womit der Bericht fuehrt."""
    for sec in _briefing_sections(md_text):
        if "blick" not in (sec.get("title") or "").lower():
            continue
        soup = BeautifulSoup(sec.get("html") or "", "html.parser")
        punkte = [li.get_text(" ", strip=True) for li in soup.find_all("li")]
        if punkte:
            return punkte[:_FADEN_MAX]
    return []


def _faden(highlights: list[dict],
           saetze: list[str]) -> list[list[dict]]:
    """Zu jedem Fuehrungssatz die Meldungen, die ihn belegen - beste zuerst.

    Zugeordnet wird ueber SELTENE gemeinsame Woerter. Ein Abgleich ueber
    alle Woerter faende "Netz", "Kunden" und "Milliarden" in jeder zweiten
    Meldung und damit ueberall eine Uebereinstimmung; gezaehlt werden
    deshalb nur Woerter, die in hoechstens einem Achtel der Meldungen
    vorkommen ("Starlink", "IHS", "Freenet").

    Gezaehlt reicht nicht, GEWICHTET muss es sein. Am 07.08.2026 gemessen:
    fuer den Satz "MTN erlangt vollstaendige Kontrolle ueber den
    Turminfrastrukturbetreiber IHS Towers ... in Afrika" fanden sich zwei
    Meldungen mit je drei gemeinsamen seltenen Woertern - die richtige
    (MTN/IHS Towers) und "KI treibt Cyberkriminalitaet in Afrika massiv
    voran", die ueber "Afrika" und "treibt" mitkam. Ein Wort, das genau
    zweimal vorkommt, beweist mehr als eines, das siebzehnmal vorkommt;
    jeder Treffer zaehlt deshalb mit 1/Haeufigkeit.

    Bei gleichem Gewicht gewinnt das breitere Bild. Nicht aus Kosmetik:
    unter gleich gut belegten Meldungen ist die brauchbar, die den
    Aufmacher auch tragen kann - der verlangt 800 px (Abnahmekriterium 3
    des Vorgaengerauftrags).

    Wer weniger als `_FADEN_MIND_TREFFER` seltene Woerter teilt, gilt als
    nicht belegt - dann fuehrt die Seite nach Dringlichkeit weiter, statt
    eine falsche Verbindung zu behaupten.
    """
    if not highlights or not saetze:
        return []
    worte_je_meldung = [
        _wortmenge(f"{h.get('schlagzeile') or ''} {h.get('operator') or ''} "
                   f"{h.get('title') or ''} {h.get('summary') or ''}")
        for h in highlights]
    haeufigkeit = _haeufigkeiten(worte_je_meldung)
    deckel = max(2, len(highlights) // 8)

    gewaehlt: list[list[dict]] = []
    vergeben: set[str] = set()
    for satz in saetze:
        sw = _wortmenge(satz)
        kandidaten: list[tuple[float, int, int, dict]] = []
        for rang, (h, worte) in enumerate(zip(highlights, worte_je_meldung)):
            if h.get("url") in vergeben:
                continue
            selten = [t for t in sw & worte if haeufigkeit[t] <= deckel]
            if len(selten) < _FADEN_MIND_TREFFER:
                continue
            kandidaten.append((-_gewicht(selten, haeufigkeit),
                               -_bildbreite(h), rang, h))
        if not kandidaten:
            continue
        kandidaten.sort(key=lambda k: k[:3])
        belegt = [k[3] for k in kandidaten[:_FADEN_KANDIDATEN]]
        vergeben.update(h.get("url") for h in belegt)
        gewaehlt.append(belegt)
    return gewaehlt


def _ctm_achse(highlights: list[dict]) -> list[dict]:
    """Genau die Reihenfolge, nach der auch der Kurzpfad auswaehlt.

    Die ersten zwei Schluessel teilt sie mit `_flatten`, der dritte nicht:
    dort entscheidet bei Gleichstand das Datum, hier die Zahl der Quellen -
    weil `ctm.zwei_minuten()` es so haelt, und weil "dieselbe Achse wie der
    Kurzpfad" der ganze Zweck dieser Funktion ist. Dass mehrere unabhaengige
    Redaktionen dieselbe Sache melden, ist in der Regel der bessere
    Wichtigkeitsbeleg als das juengere Datum.

    Der Aufruf ist deshalb auch keine Verdopplung von `_flatten`:
    `_titelseite` bekommt seine Liste nicht nur von dort, und eine
    Zusicherung, die an der Sortierung einer anderen Funktion haengt, faellt
    still aus, sobald jemand die andere Funktion anfasst.

    `sorted` ist stabil - bei gleichem Bezug bleibt die Dringlichkeitsfolge,
    in der die Meldungen ankommen, unangetastet.
    """
    return sorted(highlights,
                  key=lambda h: (-int(h.get("ctm_bezug") or 0),
                                 -int(h.get("relevance") or 0),
                                 -int(h.get("quellenzahl") or 1)))


def _titelseite(highlights: list[dict],
                faden: list[list[dict]] | None = None,
                belegt: list[str] | None = None) -> dict:
    """Verteilt die Meldungen auf die Gewichtsstufen der Titelseite.

    Bis zum 06.08.2026 kannte die Titelseite ZWEI Stufen: einen Aufmacher
    und drei gleich grosse Anreisser, dahinter eine flache Liste. Eine
    Zeitungstitelseite braucht vier, und sie muss oberhalb der Falz mehr als
    vier Geschichten zeigen.

        aufmacher     1  gross, Bild >= 800 px
        zwei          2  mittel, Bild >= 800 px  (die zweite Reihe)
        vier          4  klein, Bild beliebig
        wichtig       7  nur Text, nummeriert - die Spalte "Was wichtig ist"

    Die Reihenfolge der Vergabe ist der Punkt: die Bildpositionen greifen
    zuerst zu, damit die grossen Bilder nicht in einer Textzeile verpuffen.
    Eine Meldung wird ueber ihre URL genau einmal vergeben - ueber
    Objektidentitaet ging das schon einmal schief (der Aufmacher stand
    zweimal auf der Seite, weil er fuer die Anzeige kopiert wird).

    Vergeben wird in EINER Rangfolge (Prioritaet vor CTM-Bezug, seit
    27.08.2026, Strategie E6 - siehe `_rangschluessel`), von oben nach
    unten. Zwei Regeln halten sie:

    * **Der Rang schlaegt den Faden.** Der rote Faden waehlt nur unter
      gleichrangigen Meldungen, welche die Geschichte erzaehlt; er kann
      keine schwaechere hochziehen.
    * **Ein fehlendes Bild ist keine Abwertung.** Wer die Bildstufe nicht
      erfuellt, faellt in die Spalte "Was wichtig ist" - und steht dort
      ganz oben, statt hinter den bebilderten Kacheln zu verschwinden.

    `belegt` sind die Meldungen, die der Kurzpfad schon zeigt. Sie werden
    NUR aus "Was wichtig ist" herausgehalten, nicht von der ganzen Seite -
    und das ist der Unterschied, auf den es ankommt:

    * Kurzpfad-Zeile und Digest-Zeile stehen in DERSELBEN Spalte
      untereinander und zeigen beide Text. Dieselbe Meldung dort zweimal
      ist genau das "doppelt gemoppelt", das am 07.08.2026 die
      Ressortbloecke gekostet hat.
    * Aufmacher und Kurzpfad sind zweierlei: der eine zeigt Schlagzeile und
      Bild, der andere den Folgerungssatz - und der Aufmacher zeigt ihn
      absichtlich mit ("Was das fuer uns heisst", `.ctm-satz`). Sperrte man
      belegte Meldungen auch dort, koennte die Meldung mit dem besten
      Folgerungssatz nie mehr Aufmacher werden, und die Marke verschwaende
      von der Seite.
    """
    gesperrt: set[str] = {u for u in (belegt or []) if u}
    benutzt: set[str] = set()
    absender: list[set[str]] = []      # Kennwoerter je Absendergruppe
    vergeben: list[int] = []           # wie viele Plaetze die Gruppe schon hat

    def gruppe(h: dict) -> int | None:
        kw = _kennwoerter(h.get("operator") or h.get("source_label") or "")
        if not kw:
            return None
        for i, g in enumerate(absender):
            if g & kw:
                g |= kw                # Namensvarianten wachsen zusammen
                return i
        absender.append(set(kw))
        vergeben.append(0)
        return len(absender) - 1

    def nimm(n: int, *, mind_breite: int = 0, aus: list[dict] | None = None,
             streng: bool = False) -> list[dict]:
        gewaehlt: list[dict] = []
        # Drei Durchgaenge, in dieser Reihenfolge:
        #   1. Bildanspruch UND Absenderdeckel
        #   2. nur Absenderdeckel   - Vielfalt schlaegt Bebilderung
        #   3. ohne beides          - eine Position bleibt nie leer
        # `streng` laesst nur den ersten zu: wer aus einer Kandidatenliste
        # des Fadens waehlt, will lieber leer ausgehen als den Bildanspruch
        # aufgeben - die naechste Stufe darueber faengt das ab.
        stufen = [(mind_breite, True)] if streng else (
            ([(mind_breite, True)] if mind_breite else [])
            + [(0, True), (0, False)])
        for anspruch, deckel in stufen:
            for h in (highlights if aus is None else aus):
                if len(gewaehlt) >= n:
                    break
                if h.get("url") in benutzt or _bildbreite(h) < anspruch:
                    continue
                i = gruppe(h)
                if deckel and i is not None and vergeben[i] >= _MAX_JE_ABSENDER:
                    continue
                if i is not None:
                    vergeben[i] += 1
                benutzt.add(h.get("url"))
                gewaehlt.append(h)
            if len(gewaehlt) >= n:
                break
        return gewaehlt

    from .bilder import MIND_BREITE_GROSS

    def frei(h: dict, mind_breite: int) -> bool:
        """Kann diese Meldung den naechsten Platz dieser Bildstufe bekommen?

        Der Absenderdeckel gehoert in diese Frage hinein, sonst misst die
        Latte an der Vergabe vorbei: eine deckelblockierte Meldung KANN den
        Platz nicht bekommen, also darf sie ihn auch nicht fuer alle
        anderen sperren. Ohne diese Zeile wirft `gleichrangig()` die
        Faden-Kandidaten gegen einen Rang weg, den niemand mehr erreichen
        darf, und der Platz faellt an den Rueckfall - der rote Faden waere
        stumm abgeschaltet. Konstruiert reproduzierbar (drei Meldungen
        desselben Absenders ueber den Faden-Kandidaten); ueber die 17
        archivierten Ausgaben gerechnet aendert die Zeile keine einzige
        Belegung, sie haelt nur den Fall auf, wenn er eintritt.

        `gruppe()` NICHT aufrufen - die Funktion legt Absendergruppen an
        und veraendert damit den Zustand, den sie hier nur lesen darf.
        """
        if h.get("url") in benutzt or _bildbreite(h) < mind_breite:
            return False
        kw = _kennwoerter(h.get("operator") or h.get("source_label") or "")
        for i, g in enumerate(absender):
            if g & kw:
                return vergeben[i] < _MAX_JE_ABSENDER
        return True

    def spitze(mind_breite: int) -> tuple[int, int] | None:
        """Der beste Rang, den eine noch vergebbare Meldung dieser Bildstufe
        hat.

        Die Messlatte fuer den roten Faden: was darunter liegt, darf den
        Platz nicht bekommen, egal wie gut es den Fuehrungssatz belegt.
        """
        return max((_rangschluessel(h) for h in highlights
                    if frei(h, mind_breite)), default=None)

    def gleichrangig(kandidaten: list[dict],
                     latte: tuple[int, int] | None) -> list[dict]:
        return [h for h in kandidaten
                if latte is None or _rangschluessel(h) >= latte]

    # Der Faden zuerst: die Meldungen, die die Fuehrungssaetze des Berichts
    # belegen, bekommen Aufmacher und zweite Reihe - in der Reihenfolge des
    # Berichts. Der Aufmacher nimmt den ERSTEN Satz, fuer den sich eine
    # Meldung mit grossem Bild findet; innerhalb eines Satzes wird dafuer
    # bis zum vierten Kandidaten gesucht, bevor der naechste Satz drankommt.
    # Bleibt der Faden leer (kein Bericht, keine belegbare Zuordnung),
    # laeuft alles wie vorher nach Dringlichkeit.
    #
    # Seit dem 15.08.2026 schlaegt der RANG den Faden: gewaehlt wird nur
    # unter Meldungen, die den besten noch freien Rangschluessel dieser
    # Bildstufe erreichen. Der Faden entscheidet also, WELCHE der
    # gleichrangigen Geschichten fuehrt - er kann keine schwaechere
    # hochziehen. Bis dahin ordnete er die zwei obersten Stufen allein nach
    # Wortueberschneidung, und das war an der Ausgabe vom 14.08.2026
    # messbar falsch: Aufmacher war "T-Mobile wirbt mit Studienstart-
    # Ratgeber" (Kontext, Prioritaet 2), waehrend "T-Mobile verschenkt
    # Pixel 11 Pro XL" (Uebertragbar, Prioritaet 5) als Textzeile in der
    # Spalte stand. Antonio: "die wichtigsten artikel sollen auch an erster
    # reihe stehen."
    offen = [list(k) for k in (faden or []) if k]
    aufmacher_roh = None
    latte = spitze(MIND_BREITE_GROSS)
    for i, kandidaten in enumerate(offen):
        treffer = nimm(1, mind_breite=MIND_BREITE_GROSS,
                       aus=gleichrangig(kandidaten, latte), streng=True)
        if treffer:
            aufmacher_roh = treffer[0]
            offen.pop(i)          # dieser Satz ist erzaehlt
            break
    if aufmacher_roh is None:
        aufmacher_roh = (nimm(1, mind_breite=MIND_BREITE_GROSS) or [None])[0]
    aufmacher = None
    if aufmacher_roh is not None:
        aufmacher = dict(aufmacher_roh)
        # Die volle Zusammenfassung des Analysten - sie ist bereits auf ein
        # bis zwei Saetze angelegt. Ein Schnitt daran machte einen Halbsatz.
        aufmacher["vorspann"] = " ".join((aufmacher_roh.get("summary") or "").split())

    # Die zweite Reihe erzaehlt die uebrigen Fuehrungssaetze, je einen -
    # und misst die Latte VOR JEDEM Platz neu. Einmal vorab gerechnet waere
    # sie nach dem ersten Zugriff veraltet: dann duerfte der zweite Platz
    # nur noch von einem Rang genommen werden, den es gar nicht mehr gibt,
    # und die Reihe bliebe halb leer.
    zwei: list[dict] = []
    while len(zwei) < 2:
        latte = spitze(MIND_BREITE_GROSS)
        treffer = nimm(1, mind_breite=MIND_BREITE_GROSS,
                       aus=gleichrangig([k[0] for k in offen], latte),
                       streng=True) \
            or nimm(1, mind_breite=MIND_BREITE_GROSS)
        if not treffer:
            break
        zwei += treffer
    for h in zwei:
        h["anriss"] = _first_sentence(h.get("summary") or "", 150)
    # Die dritte Reihe zieht seit dem 15.08.2026 wieder VOR der
    # Digest-Spalte - aber erst, nachdem sich die Spalte genommen hat, was
    # ihr K2 (09.08.2026) zugesagt hat. Drei Stufen, in dieser Reihenfolge:
    #
    #   1. `wichtig` nimmt die Meldungen der Stufe "Direkt fuer uns"
    #   2. `vier` fuellt seine Bildkacheln aus der Rangfolge
    #   3. `wichtig` fuellt auf, `vier` notfalls ohne Bild
    #
    # Warum ueberhaupt zurueckgedreht: die Spalte zuerst hiess, dass die
    # HAUPTSPALTE systematisch die schwaecheren Meldungen bekam. An der
    # Ausgabe vom 15.08.2026 standen in den vier Kacheln vier Meldungen mit
    # Prioritaet 2, waehrend fuenf mit Prioritaet 3 als Textzeilen daneben
    # lagen. Aufmacher, zweite und dritte Reihe stehen untereinander in
    # derselben Spalte und werden in dieser Folge gelesen - was
    # untereinander steht, muss in einer Rangfolge stehen.
    #
    # Warum trotzdem die Reservierung: der Befund vom 08.08.2026 war, dass
    # die Bildkacheln JEDE Meldung mit direktem Portfoliobezug abraeumten
    # und "Was wichtig ist" deshalb mit zwei BREKO-Stellungnahmen (Stufe 2)
    # fuehrte. Es waere verlockend, das dem Kurzpfad zu ueberlassen - "In
    # zwei Minuten" steht ueber derselben Spalte, und `gesperrt` haelt
    # seine Meldungen aus dem Digest heraus. Diese Begruendung traegt aber
    # nicht: der Kurzpfad nimmt nur Meldungen mit einem GEPRUEFTEN
    # Folgerungssatz, und der faellt regelmaessig aus (am 14.08.2026
    # verwarf der Prueflauf gegen den Originaltext alle neun Saetze). Ueber
    # die 17 archivierten Ausgaben gemessen ist der Kurzpfad in 16 leer.
    # Eine Zusicherung, die an einer anderen Stufe haengt, ist keine.
    #
    # Die Reservierung greift NICHT vor Aufmacher und zweiter Reihe: dort
    # steht eine Stufe-3-Meldung besser als in einer Textzeile, und die
    # zwei Stufen sind ohnehin streng nach Rang vergeben.
    wichtig = nimm(_WICHTIG_ZEILEN,
                   aus=[h for h in _ctm_achse(highlights)
                        if h.get("url") not in gesperrt
                        and int(h.get("ctm_bezug") or 0) >= ctm.DIREKT])
    # `streng` ist hier die halbe Regel: die dritte Reihe ist eine
    # BILDposition. Ohne sie greift ihr Rueckfall auf Meldungen OHNE Bild
    # zu - und weil sie vor der Spalte zieht, holte sie sich die hoch
    # bewerteten bildlosen Meldungen in eine Kachel, die dann leer bleibt,
    # und naehme sie damit der Spalte weg. Eine bildlose Meldung ist in
    # einer Textzeile besser aufgehoben als in einer Bildkachel ohne Bild.
    vier = nimm(4, mind_breite=1, streng=True)
    wichtig += nimm(_WICHTIG_ZEILEN - len(wichtig),
                    aus=[h for h in _ctm_achse(highlights)
                         if h.get("url") not in gesperrt])
    vier += nimm(4 - len(vier), mind_breite=1)

    # Hier wurden bis zum 07.08.2026 zusaetzlich sechs Ressortbloecke
    # bestueckt (je ein Aufmacher und vier Zeilen). Sie sind weg: dieselbe
    # Gliederung nach denselben Ressorts steht vollstaendig auf der
    # Meldungsseite (_nach_ressort), die Titelseite zeigte davon nur eine
    # Teilmehge - dieselbe Ueberschrift, dieselbe Quelle, ein Klick weiter.
    # Die Meldungen, die dort standen, sind nicht verschwunden; sie stehen
    # auf meldungen.html, wo sie ohnehin schon standen.

    return {"aufmacher": aufmacher, "zwei": zwei, "vier": vier,
            "wichtig": wichtig,
            # Wie viele der Fuehrungssaetze des Berichts oberhalb der Falz
            # wirklich mit ihrer Meldung stehen. Die Zahl ist die Messgroesse
            # fuer den roten Faden - tests/test_seiten_zahlen.py haelt sie
            # dagegen, damit die Kopplung nicht still verloren geht.
            "faden_oben": sum(1 for kandidaten in (faden or [])
                              if any(h.get("url") in benutzt
                                     for h in kandidaten)),
            # Was oberhalb der Falz mit eigener Schlagzeile steht. Der Test
            # in tests/test_seiten_zahlen.py haelt diese Zahl gegen die
            # gerenderten Elemente.
            "oben": 1 + len(zwei) + len(vier) + len(wichtig) if aufmacher else 0}


def _nach_ressort(highlights: list[dict]) -> list[dict]:
    """Alle Meldungen nach Ressort gruppiert, in fester Reihenfolge.

    Fuer die Meldungsseite: dort steht jede Meldung, nicht nur eine Auswahl.
    Innerhalb eines Ressorts bleibt die Sortierung nach Dringlichkeit, die
    `_flatten()` gesetzt hat - der erste Eintrag ist also der Aufmacher des
    Ressorts.

    `kachel` ist die Auswahl fuer die Ressortuebersicht am Seitenkopf: drei
    Meldungen, moeglichst bebildert, den Ressortaufmacher immer voran. Sie
    ist eine Teilmenge von `lead`/`mittel`/`zeilen`, keine zusaetzliche
    Meldung - die Uebersicht zeigt an, was darunter vollstaendig steht.
    """
    gruppen: dict[str, list[dict]] = {}
    for h in highlights:
        gruppen.setdefault(h.get("ressort") or "vermischt", []).append(h)
    out = []
    for key in _RESSORT_REIHENFOLGE:
        eintraege = gruppen.get(key) or []
        if not eintraege:
            continue
        # Der Ressortaufmacher steht mit grossem Bild - also muss er eins
        # haben. Sonst gaehnt links eine Textwueste, waehrend die zwei
        # kleineren daneben bebildert sind. Unter den ersten fuenf, damit
        # die Dringlichkeit nicht der Bebilderung geopfert wird.
        lead = next((h for h in eintraege[:5] if _bildbreite(h) >= 500),
                    eintraege[0])
        rest = [h for h in eintraege if h is not lead]
        # Zwei Begleiter zum Aufmacher: bebilderte zuerst, sonst waere die
        # Kachel ein Inhaltsverzeichnis. Innerhalb beider Gruppen bleibt die
        # Reihenfolge nach Dringlichkeit erhalten.
        begleiter = ([h for h in rest if h.get("image")]
                     + [h for h in rest if not h.get("image")])[:2]
        out.append({"key": key, "label": _RESSORT_LABEL[key],
                    "lead": lead, "mittel": rest[:4],
                    "zeilen": rest[4:], "n": len(eintraege),
                    "kachel": [lead] + begleiter})
    return out


def _schlagzeile(h: dict, max_zeichen: int = 0) -> str:
    """Die Ueberschrift einer Meldung. **Nie abgeschnitten.**

    Reihenfolge, und sie ist der ganze Punkt:

    1. `headline` - eine echte, vom Analysten geschriebene Schlagzeile
       (max. neun Woerter, Aktiv). Gibt es fuer Berichte ab dem 06.08.2026.
    2. `title` - die Originalueberschrift der Quelle. Vollstaendig, und sie
       IST eine Ueberschrift, weil eine Redaktion sie als solche geschrieben
       hat. Oft englisch - aber vollstaendig und aussagekraeftig schlaegt
       deutsch und abgehackt.
    3. `de_title` - der Zusammenfassungssatz, nur als letzter Ausweg.

    Was hier ausdruecklich NICHT passiert: kuerzen. Bis zum 06.08.2026 stand
    auf der Titelseite "Amazon Leo hat bei der US-Behoerde FCC eine
    Genehmigung fuer ein Direct-to-Device-Satellitennetz mit bis zu…" - der
    Leser erfuhr nicht, worum es geht. Eine Ueberschrift, die mitten im Satz
    aufhoert, ist keine. Lieber vier Zeilen, die vollstaendig sind; der Grad
    richtet sich im CSS nach der Laenge.
    """
    for feld in ("headline", "title", "de_title"):
        wert = " ".join((h.get(feld) or "").split()).strip()
        # Ein bereits gekuerzter Wert (endet auf …) taugt nicht als
        # Ueberschrift - dann lieber das naechste Feld.
        if wert and not wert.endswith("…"):
            return wert.rstrip(" .")
    return " ".join((h.get("de_title") or "").split()).rstrip("… ")


def _text_aus_html(html: str) -> str:
    """Reintext aus gerendertem HTML - inklusive Aufloesung der Entitaeten.

    Wichtig: der Vorspann der Promo-Uebersicht (_promo_lead) zieht Text aus
    bereits gerendertem HTML. Wer dort nur die Tags per Regex entfernt,
    behaelt "&amp;" als Zeichenfolge - und Jinja escaped die beim Einsetzen
    ein zweites Mal. Auf der Titelseite stand deshalb "mit AT&amp;T".
    """
    return " ".join(BeautifulSoup(html or "", "html.parser").get_text(" ").split())


# Ein Punkt ist nur dann ein Satzende, wenn ein Buchstabe oder eine
# schliessende Klammer davor steht und ein Grossbuchstabe dahinter. Ohne die
# erste Bedingung ist "AST SpaceMobile hat am 5. August drei Satelliten
# gestartet" nach vier Woertern zu Ende - genau so stand es am 06.08.2026 im
# Anriss der zweiten Reihe ("AST SpaceMobile hat am 5."). Ordnungszahlen,
# Datumsangaben und Geldbetraege sind im Deutschen voller solcher Punkte.
#
# Zwei Faelle, und der zweite ist nicht kosmetisch: ein freistehender Punkt
# (" . ") ist immer ein Satzende und nie eine Ordnungszahl. Ohne diese
# zweite Alternative verlor die Promo-Uebersicht ihren Schnitt - deren
# Wochentext besteht aus aneinandergereihten Angebotstiteln, und der naechste
# beginnt mit einer Ziffer ("1&1 Mobilfunk"), nicht mit einem Grossbuchstaben.
_SATZENDE = re.compile(
    r"(?:(?<=[a-z\u00e4\u00f6\u00fc\u00dfA-Z\u00c4\u00d6\u00dc\)\"'\u00bb])[.!?](?=\s+[A-Z\u00c4\u00d6\u00dc\u00ab\"\u201e])"
    r"|(?<=\s)[.!?](?=\s))")


def _first_sentence(text, limit=170):
    """Erster Satz, sonst gekuerzt - aber NIE mitten im Wort.

    Bis zum 06.08.2026 schnitt die letzte Zeile hart bei `limit`. In der
    Aufmacher-Schlagzeile stand deshalb "... die drei US-Betreiber erzielen
    z\u2026" - in 33px Serife ueber drei Zeilen. Jetzt bis zur letzten
    Wortgrenze davor.
    """
    t = " ".join((text or "").split())
    if not t:
        return ""
    geschuetzt = t
    for i, abk in enumerate(_ABK):
        geschuetzt = geschuetzt.replace(abk, "\x00" * len(abk))
    m = _SATZENDE.search(geschuetzt)
    if m and 0 < m.end() < limit:
        return t[:m.end()]
    if len(t) <= limit:
        return t
    schnitt = t[:limit].rstrip()
    leer = schnitt.rfind(" ")
    if leer > limit * 0.6:          # sonst waere die Zeile unbrauchbar kurz
        schnitt = schnitt[:leer]
    return schnitt.rstrip(" ,;:\u2013-") + "\u2026"


def _briefing_sections(md_text):
    if not md_text:
        return []
    parts = re.split(r"(?m)^##\s+(.+?)\s*$", md_text)
    sections = []
    pre = (parts[0] or "").strip()
    if pre:
        sections.append({"title": "\u00dcberblick", "html": _md_to_html(pre)})
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        body = (parts[i + 1] if i + 1 < len(parts) else "").strip()
        if title or body:
            sections.append({"title": title, "html": _md_to_html(body)})
    return sections


_ADVICE_SECTION_RE = re.compile(
    r"(?ms)^##\s+(?:Empfehlungen|Handlungsempfehlungen)[^\n]*\n.*?(?=^##\s|\Z)")
_ADVICE_LINE_RE = re.compile(r"(?mi)^\s*(?:Fuer|Für)\s+Vodafone\s*:.*(?:\n|$)")


_ADVICE_PHRASES = (
    "für vodafone", "fuer vodafone", "vodafone sollte", "vodafone könnte",
    "vodafone koennte", "vodafone muss", "vodafone kann",
)
def _ohne_ratschlagsaetze(block: str) -> str:
    """Entfernt aus einem Absatz die SAETZE mit Vodafone-Ratschlag.

    Der Satztrenner (mit Abkuerzungsschutz) steht in textwerkzeug - er wird
    von drei Stellen gebraucht, die dieselbe Redaktionsregel durchsetzen.
    """
    behalten = [s for s in _saetze(block)
                if not any(p in s.lower() for p in _ADVICE_PHRASES)]
    return " ".join(behalten).strip()


def _strip_vodafone_advice(md_text: str) -> str:
    """Haelt die oeffentliche Seite beobachtend statt empfehlend.

    Die Regel selbst ist eine Redaktionsentscheidung und bleibt: die Website
    berichtet, sie berät nicht. Sie galt bis zum 06.08.2026 aber je ABSATZ -
    und ein Absatz enthaelt in aller Regel zuerst den Befund und erst am Ende
    die Folgerung. Gemessen am Bericht vom 05.08.2026 verschwanden dadurch
    drei Absaetze mit 77 Woertern, darunter das Gewinnwachstum von MTN
    Nigeria (70,6 %) - also berichtete Fakten, nur weil im selben Absatz
    "Vodafone kann" stand.

    Jetzt satzgenau: die Folgerung faellt, der Befund bleibt. Bleibt von
    einem Absatz nichts uebrig, faellt er wie bisher ganz weg.
    """
    cleaned = _ADVICE_SECTION_RE.sub("", md_text or "")
    cleaned = _ADVICE_LINE_RE.sub("", cleaned)
    blocks = []
    for block in re.split(r"\n{2,}", cleaned):
        if not any(p in block.lower() for p in _ADVICE_PHRASES):
            blocks.append(block)
            continue
        rest = _ohne_ratschlagsaetze(block)
        if rest:
            blocks.append(rest)
    return "\n\n".join(blocks).strip()


# `_briefing_lead()` stand hier bis zum 07.08.2026: der erste Satz des
# Abschnitts "Was wichtig ist", gekuerzt auf 360 Zeichen, als Vorspann ueber
# der Ausgabe. Er ist mit seiner Anzeige zusammen entfernt worden (siehe
# woche.html.j2) - eine Funktion, deren Ergebnis keine Vorlage mehr liest,
# ist genau der Zustand, in dem `briefing_lead` schon einmal ein halbes Jahr
# lang unbemerkt berechnet wurde.


# Ein Satzende, dem eine KLEIN geschriebene Marke folgt. `_SATZENDE` verlangt
# dahinter einen Grossbuchstaben - im Nachrichtentext die richtige Vorsicht
# gegen Abkuerzungen, in der Promo-Welt die falsche: winSIM, congstar, otelo,
# simplytel und mobilcom-debitel schreiben sich alle klein. Gemessen am
# Promo-Bericht vom 07.08.2026 uebersah die Regel deshalb das erste Satzende
# ("... Eskalationsstufe erreicht. winSIM senkt ...") und lieferte statt eines
# Leitsatzes 280 Zeichen mit "…" am Ende - als einzigen Vorspann der Seite.
_PROMO_SATZENDE = re.compile(r"(?<=[a-zäöüßA-ZÄÖÜ\)\"'»])[.!?](?=\s+\S)")


def _promo_lead(md_text: str) -> str:
    """Kurzer Vorspann aus dem Promo-Wochenbericht fuer die Karte "Was diese
    Woche auffaellt". Der Bericht beginnt mit einem gleichnamigen Abschnitt,
    es wird also nur dessen erster Satz gekuerzt - keine separate
    Zusammenfassung wird erfunden.

    Nur, wenn es ueberhaupt Saetze sind. Scheitert der Promo-Editor, faellt
    die Pipeline auf `build_digest()` zurueck, und der schreibt unter
    derselben Ueberschrift eine Liste von Angebotstiteln. Am 06.08.2026 stand
    daraus auf der Seite "ALDI TALK imoo Kinder-Smartwatch kaufen + 2
    MovieChoice-Kinogutscheine ALDI TALK - imoo Kinder-Smartwatch kaufen + 2
    MovieChoice-Kinogutscheine ." Der Digest sagt jetzt selbst, dass er
    keiner ist (`DIGEST_MARKER`); hier wird darauf gehoert und lieber nichts
    zurueckgegeben, als eine Aufzaehlung als Analyse auszugeben. Die Karte
    zeigt in dem Fall die Datenlage statt eines Textes (siehe Vorlage).
    """
    from ..analyze.promo_editor import DIGEST_MARKER

    secs = _briefing_sections(md_text)
    if not secs:
        return ""
    text = _text_aus_html(secs[0]["html"])
    if text.startswith(DIGEST_MARKER):
        return ""
    geschuetzt = text
    for abk in _ABK:
        geschuetzt = geschuetzt.replace(abk, "\x00" * len(abk))
    m = _PROMO_SATZENDE.search(geschuetzt)
    if m and m.end() <= 280:
        return text[:m.end()]
    return _first_sentence(text, 280)


def _stats(report):
    """Der Themenradar der aktuellen Woche - mehr braucht die Wochenseite nicht.

    Beim Redesign am 06.08.2026 auf das reduziert, was wirklich gerendert
    wird. Entfernt, weil seit Monaten berechnet und in KEINER Vorlage
    referenziert: sov (Share of Voice), pricing, deals, risks/chances und
    n_competitors. Ebenso die Parameter prev_report/trend_reports - sie
    dienten nur der Delta-Rechnung von sov.

    Am 07.08.2026 ist die naechste Schicht gefallen. `kpis` fuetterte die
    Kachelreihe "Zahlen der Woche"; von ihren fuenf Werten standen zwei
    (gelesen/relevant) im selben Bildschirm noch einmal als Satz ueber dem
    Bericht und ein dritter (Top-Technologiethema) als erste Zeile des
    Themenradars daneben. Dieselbe Information in zwei Formen ist genau die
    Unruhe, die Antonio benannt hat - die Kachelreihe ist weg, die
    verbliebenen Zahlen stehen im Berichtskopf. `lead_signal` war noch
    aelter: berechnet seit Monaten, von keiner Vorlage je gelesen.

    Am 08.08.2026 ist der Rest gefallen. `sofort` ("davon 13 zum sofortigen
    Ansehen") war der dritte Satz einer Zeile, die jetzt ein Halbsatz ist -
    und die Zahl steht ohnehin an jeder betroffenen Meldung als Prioritaet
    5/5. Mit ihr die letzten zwei Radarfelder, die nie eine Vorlage gelesen
    hat: `ops_top` (die zwei haeufigsten Betreiber je Thema) und `ex` (ein
    Beispielartikel je Thema). Der Themenradar zeigt Name, Zahl und Balken.
    """
    # --- Themenradar (Schlagwortthemen ueber Titel und Zusammenfassung) ---
    tech: dict[str, dict] = {}
    for h in _flatten(report):
        for name in _tag_tech(f"{h.get('title','')} {h.get('summary','')}"):
            t = tech.setdefault(name, {"theme": name, "n": 0})
            t["n"] += 1
    tech_radar = sorted(tech.values(), key=lambda x: -x["n"])
    tmax = max((t["n"] for t in tech_radar), default=1) or 1
    for t in tech_radar:
        t["w"] = round(100 * t["n"] / tmax)

    return {"tech_radar": tech_radar}


def _prep_competitors(report: dict) -> list[dict]:
    """Enrich competitor profiles for rendering (domains, category colours).

    Liefert ausserdem, was die Titelseite fuer ihren Kurzverweis braucht:
    `anker` (Sprungziel auf wettbewerb.html) und `satz` (der erste Satz des
    Profils). Die Detailkarten sind am 08.08.2026 auf die Wettbewerbsseite
    umgezogen - die Titelseite nennt nur noch Name und Lage in einer Zeile.
    """
    out = []
    for c in (report.get("competitors") or []):
        c = dict(c)
        moves = []
        for m in (c.get("moves") or []):
            m = dict(m)
            if _is_suppressed_source(m):
                continue
            m["domain"] = urlsplit(m.get("url") or "").netloc.removeprefix("www.")
            m["color"] = CATEGORY_COLORS.get(m.get("category"), "#7e7e7e")
            moves.append(m)
        c["moves"] = moves
        c["anker"] = _wb_anker(c.get("name") or "")
        c["satz"] = _first_sentence(c.get("summary") or "", 190)
        out.append(c)
    return out


# ------------------------------------------------------------- search index
# Der Index selbst wird in report/suchindex.py gebaut - er speist seit dem
# 08.08.2026 nicht mehr nur die Bericht-Highlights und die Differenzierung,
# sondern auch die Promo-Aktionen, und jeder Eintrag traegt sein Bild. Die
# Aufbereitung dorthin auszulagern hat einen zweiten Grund: der Index ist die
# einzige Datei, die eine SEITE nicht ist - sie wird vom Browser gelesen, und
# eine 1400-Zeilen-Datei ist der falsche Ort fuer ein Datenformat.


# ------------------------------------------------------------------- render
def render_site(site_dir: Path, reports_dir: Path, cfg=None) -> None:
    env = _env()
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "reports").mkdir(exist_ok=True)
    # Ein Foliensatz je Ausgabe, neben dem Bericht. Nicht in der Navigation:
    # er ist kein Ort zum Lesen, sondern eine Datei zum Mitnehmen.
    folien_dir = site_dir / "folien"
    folien_dir.mkdir(exist_ok=True)
    (site_dir / ".nojekyll").write_text("")
    for asset in ("style.css", "app.js"):
        (site_dir / asset).write_text(
            (_TEMPLATES / asset).read_text(encoding="utf-8"), encoding="utf-8")
    for binasset in ("logo.png",):
        src = _TEMPLATES / binasset
        if src.exists():
            shutil.copy(src, site_dir / binasset)
    # Meldungsbilder sind Pipeline-State (data/state/report_images/), nicht
    # Site-Quelltext - sie werden bei jedem Rendern kopiert, genau wie die
    # Promo-Screenshots. Nie von Hand unter site/ ablegen.
    #
    # site/images/ SPIEGELT den Ordner - es sammelt nicht. Bis zum
    # 06.08.2026 wurde hier nur kopiert und nie geloescht: `raeume_auf()`
    # beschnitt den Zwischenspeicher, site/images/ behielt jedes jemals
    # geladene Bild. Solange es 9 Bilder je Lauf waren, fiel das nicht auf;
    # seit es rund 130 sind, waere das Repo in einem Jahr um mehrere
    # Gigabyte gewachsen - fuer Bilder, auf die keine Seite mehr zeigt.
    #
    # Gespiegelt werden ZWEI Ordner: die Bilder der Wochenberichte und die der
    # Differenzierungs-Bibliothek (data/state/diff_images, seit 08.08.2026).
    # Sie brauchen getrennte Speicher, weil `report_bilder.raeume_auf()` nur
    # behaelt, was die letzten vier Ausgaben referenzieren - ein
    # Differenzierungs-Beispiel lebt aber Monate. Ausgeliefert werden sie im
    # selben Ordner: die Dateinamen sind Hashes ihrer Bild-URL, eine Kollision
    # waere dieselbe Datei, und eine Seite muss nicht wissen, aus welchem
    # Speicher ihr Bild stammt.
    bild_quelle = report_bilder.bildordner(reports_dir.parent.parent)
    diff_bild_quelle = diff_bilder.bildordner(reports_dir.parent.parent)
    bild_quellen = [q for q in (bild_quelle, diff_bild_quelle) if q.exists()]
    if bild_quellen:
        bild_ziel = site_dir / "images"
        bild_ziel.mkdir(exist_ok=True)
        vorhanden = set()
        for quelle in bild_quellen:
            for bild in quelle.iterdir():
                if bild.is_file():
                    shutil.copyfile(bild, bild_ziel / bild.name)
                    vorhanden.add(bild.name)
        for veraltet in bild_ziel.iterdir():
            if veraltet.is_file() and veraltet.name not in vorhanden:
                veraltet.unlink()

    num_operators = len(cfg.operators) if cfg is not None else None
    reports = _load_reports(reports_dir)
    # Eine Berichtsdatei behaelt ihre `image`-Verweise fuer immer, der
    # Bildordner nicht: `raeume_auf()` loescht die Bilder aelterer Ausgaben,
    # damit das Repo nicht unbegrenzt waechst. Ohne diesen Abgleich zeigt
    # jede Archivwoche jenseits der Aufbewahrungsfrist leere Bildkaesten -
    # und der Satz kommt ohne Bild aus, das ist von Anfang an so gebaut.
    # Beide Speicher, weil beide nach site/images/ gespiegelt werden - ein
    # Differenzierungs-Beispiel kann sein Bild aus dem Bericht geerbt haben
    # oder ein eigenes og:image tragen.
    vorhandene_bilder = {b.name for quelle in bild_quellen
                         for b in quelle.iterdir() if b.is_file()}
    for report in reports:
        for region in (report.get("regions") or {}).values():
            for h in region.get("highlights") or []:
                if h.get("image") and h["image"] not in vorhandene_bilder:
                    for feld in ("image", "image_w", "image_h"):
                        h.pop(feld, None)
    # Die temporaeren Themen (data/state/highlight_topics.json). Sie werden
    # hier geladen, weil die Titelseite unter ihrer dritten Reihe darauf
    # verweist - gerendert werden ihre Seiten weiter unten, nach den Promos:
    # ein Thema darf die dazu passenden Aktionen zeigen.
    state_dir = reports_dir.parent / "state"
    themen = highlight_topics.lade_themen(state_dir)
    for thema in themen:
        for item in thema.get("items") or []:
            if item.get("image") and item["image"] not in vorhandene_bilder:
                for feld in ("image", "image_w", "image_h"):
                    item.pop(feld, None)
    themen_band = [{"slug": t.get("slug"), "titel": t.get("title"),
                    "n": len(t.get("items") or [])} for t in themen]

    # Hier standen bis zum 07.08.2026 die Globals `ausgabe_datum` und
    # `ausgabe_quellen` fuer die Datumszeile des Zeitungskopfs. Die Zeile ist
    # weg (Antonio: "das ist unnoetig"), also sind es die Werte auch - diese
    # Codebasis hat schon einmal sechs berechnete Groessen mitgeschleppt, die
    # keine Vorlage benutzte.
    # ---- Geraetedaten: HIER, nicht erst bei ihrer eigenen Seite.
    # Sie entscheiden ueber einen Navigationseintrag, und die Navigation
    # steht in `base.html.j2` - also auf JEDER Seite, auch auf denen, die
    # weiter unten schon gerendert sind. Wer das Aufbereiten unten laesst,
    # bekommt eine Startseite ohne den Eintrag und eine Geraeteseite mit ihm.
    #
    # Die Aufbereitung faellt aus, wenn ein Eintrag kaputt ist; dann steht
    # die Seite in ihrem Notzustand und der Eintrag bleibt weg. Der try/except
    # deckt ausdruecklich NUR das Aufbereiten ab, nie das Rendern.
    from ..geraete_config import lade_katalog, lade_quellen as _lade_geraetequellen
    from . import geraete_view as geraete_view_mod
    _wurzel = getattr(cfg, "root", None) or reports_dir.parent.parent
    try:
        geraete = geraete_view_mod.aufbereiten(
            state_dir, _lade_geraetequellen(_wurzel), lade_katalog(_wurzel),
            heute=reports[0]["date"] if reports else "")
    except Exception as exc:  # noqa: BLE001
        log.error("Geraetedaten nicht aufbereitbar: %s: %s",
                  type(exc).__name__, exc)
        geraete = geraete_view_mod.leer(f"{type(exc).__name__}: {exc}")
    env.globals["geraete_verlinkt"] = bool(
        geraete["bilanz"].get("schwelle_erreicht"))

    # ---- Rechtstexte: aus demselben Grund HIER und nicht bei ihrer Seite.
    # Die Fusszeile steht in `base.html.j2`, also auf JEDER Seite - und die
    # Schwelle "Impressum vollstaendig" entscheidet zusaetzlich darueber, ob
    # das Anmeldeformular ueberhaupt verlinkt wird. Beides muss feststehen,
    # bevor die erste Seite gerendert wird; sonst hat die Startseite eine
    # andere Fusszeile als die Quellenseite.
    rechtstexte = rechtstexte_mod.alle(_wurzel)
    env.globals["rechtstexte_verlinkt"] = {t.schluessel for t in rechtstexte}
    # Der Newsletter braucht BEIDE Pflichtseiten vollstaendig. Ohne sie wird
    # das Formular gebaut, aber nicht verlinkt - dieselbe
    # Veroeffentlichungsschwelle wie bei der Geraeteseite, und aus demselben
    # Grund im Code statt in einem Test.
    env.globals["newsletter_verlinkt"] = rechtstexte_mod.vollstaendig(_wurzel)

    # ---- Uebersetzungen: die Zuordnung muss stehen, BEVOR die erste Woche
    # gerendert wird. Der rote Link haengt an der einzelnen Meldung, und
    # dieselbe Meldung steht auf der Titelseite, auf der Meldungsseite und in
    # jeder Archivwoche - alle drei lesen `h["uebersetzung"]`.
    #
    # Es wird NICHT gefiltert, welche Ausgabe eine Uebersetzung bekommt: der
    # Speicher wird nie beschnitten, also traegt auch eine Archivwoche von
    # vor drei Monaten ihren Link weiter. Das ist die Gegenmassnahme zu den
    # toten Archivlinks (Premortem 6).
    from . import uebersetzung_view as uebersetzung_view_mod
    uebersetzungen = uebersetzung_view_mod.lade(state_dir)
    uebersetzung_je_url = uebersetzung_view_mod.zuordnung(uebersetzungen)
    if not env.globals["newsletter_verlinkt"]:
        for seite, was in rechtstexte_mod.offene_stellen(_wurzel):
            log.warning("Rechtstext unvollstaendig: %s -> %s", seite, was)
    rechtstext_tpl = env.get_template("rechtstext.html.j2")
    for text in rechtstexte:
        (site_dir / f"{text.schluessel}.html").write_text(
            rechtstext_tpl.render(
                prefix="", active=text.schluessel,
                text={"titel": text.titel, "luecken": text.luecken,
                      "html": _md_to_html(text.markdown)}),
            encoding="utf-8")

    archive = [{"date": r["date"], "date_de": _fmt_date_de(r["date"]),
                "stats": r.get("stats", {}),
                "llm": r.get("generated_with_llm", False)} for r in reports]

    # Eine Vorlage fuer die aktuelle Woche UND jede Archivwoche. Bis zum
    # 06.08.2026 waren es zwei (uebersicht.html.j2 + report.html.j2), die
    # dieselbe Berichtsdatei aus zwei Blickwinkeln zeigten und sich
    # gegenseitig verlinkten - zwei Ladevorgaenge fuer eine Frage.
    woche_tpl = env.get_template("woche.html.j2")
    latest_ctx: dict | None = None
    # Je Woche das, woraus die Wettbewerbsseite ihre Chronik und der Suchindex
    # seine Meldungen bauen. Es faellt in dieser Schleife ohnehin an - alles
    # ein zweites Mal zu rechnen waere der teuerste Teil des Rendervorgangs
    # (14 Wochen x _flatten()).
    wochen: list[dict] = []
    for i, report in enumerate(reports):
        highlights = _flatten(report)
        # Der rote Link. Er entsteht beim Rendern und steht nicht in der
        # Berichtsdatei: eine Uebersetzung kann nach der Ausgabe entstehen
        # (die Stufe hat eine Frist und arbeitet ihre Kandidaten der Reihe
        # nach ab), und ein Bericht wird nicht rueckwirkend umgeschrieben.
        for h in highlights:
            pfad = uebersetzung_je_url.get(h.get("url") or "")
            if pfad:
                h["uebersetzung"] = pfad
        briefing_md = _strip_vodafone_advice(
            _strip_suppressed_source_content(report.get("briefing_md", "")))
        briefing_html, toc = _anchor_headings(_md_to_html(briefing_md))
        # Vier Gewichtsstufen plus Ressortbloecke statt "Aufmacher, drei
        # gleich grosse Anreisser, flache Liste" - siehe _titelseite(). Der
        # Faden aus dem Bericht bestimmt, WOMIT die Seite fuehrt; die
        # Gewichtung bleibt davon unberuehrt. Gelesen wird der BEREINIGTE
        # Bericht - die Seite darf nicht einem Satz folgen, den sie selbst
        # nicht zeigt.
        # Der Kurzpfad wird VOR der Titelseite gewaehlt, damit sie ihn
        # aussparen kann. Seit dem 09.08.2026 stehen beide in derselben
        # Spalte und ziehen aus derselben Sortierung - ohne diese Reihenfolge
        # steht dieselbe Meldung als Kurzpfad-Zeile 1 und als erste Zeile von
        # "Was wichtig ist" direkt untereinander. Genau das "doppelt
        # gemoppelt" hat Antonio am 07.08.2026 an den Ressortbloecken
        # kassiert; die Regel "eine Meldung genau einmal" galt auf dieser
        # Seite bisher nur innerhalb von `_titelseite`.
        kurzpfad = ctm.kurzpfad(highlights)
        front = _titelseite(highlights,
                            _faden(highlights, _fuehrende_saetze(briefing_md)),
                            belegt=[h.get("url") for h in kurzpfad])
        competitors = _prep_competitors(report)
        wochen.append({"date": report["date"], "highlights": highlights,
                       "competitors": competitors})
        public_highlights = []
        for h in highlights:
            public_h = dict(h)
            public_h.pop("why_it_matters", None)
            public_highlights.append(public_h)
        ctx = {
            "report": report, "date_de": _fmt_date_de(report["date"]),
            "highlights": highlights,
            "explorer_json": _json_for_script(public_highlights),
            "front": front,
            "competitors": competitors,
            # _stats() ist teuer und wird nur von der aktuellen Woche
            # gebraucht. Bis zum 06.08.2026 lief es fuer JEDE Archivwoche mit
            # und das Ergebnis wurde verworfen.
            "dash": _stats(report) if (i == 0 and highlights) else None,
            "briefing_html": briefing_html,
            "toc": toc,
            "lesezeit": _lesezeit(briefing_md),
            # Der Zwei-Minuten-Pfad. "Lesezeit ca. 16 Minuten" ist ehrlich und
            # trotzdem das Ende der Nutzung - 16 Minuten liest kein
            # Bereichsleiter. Jede Zeile mit Konsequenz und Quellenlink,
            # ausschliesslich aus geprueften Folgerungssaetzen.
            # Bleibt die Liste leer, steht der Kasten nicht da: eine Woche
            # ohne direkte Portfoliofrage ist ein Befund, keine Luecke, die
            # man mit Fuellzeilen schliesst.
            "zwei_minuten": kurzpfad,
            "regions": sorted({h["region"] for h in highlights}),
            "categories": sorted({h["category"] for h in highlights}),
            "archive": archive, "is_latest": i == 0,
            "num_operators": num_operators or report.get("stats", {}).get("operators"),
            "n_competitors": len(competitors),
            # Die laufenden Themenseiten. Nur die aktuelle Ausgabe verweist
            # darauf - eine Archivwoche zeigt den Stand ihres Tages, und die
            # Themen von heute gehoeren nicht dazu (die Vorlage prueft
            # `is_latest`).
            "themen": themen_band,
            # Das Fruehwarn-Board braucht das ARCHIV, nicht nur diese Woche -
            # "beobachtet" heisst "in einer der letzten Ausgaben belegt".
            # Deshalb wird es unten nach der Schleife nachgereicht und die
            # Startseite ein zweites Mal geschrieben; nur sie zeigt es
            # ohnehin (`is_latest`).
            "fruehwarnung": None,
        }
        # Die Archivwoche traegt ihre Meldungen selbst - sie hat keine
        # meldungen.html, auf die sie verweisen koennte, und die globale
        # Suche verlinkt mit ?q= genau hierher.
        # is_latest=False auch fuer die neueste Woche: reports/<datum>.html
        # ist immer die Archiv-URL. Ohne das truege die Archivkopie der
        # aktuellen Woche dieselbe Ueberschrift wie die Startseite und
        # verschwiege, dass man eine datierte Fassung ansieht.
        ctx_archiv = dict(ctx, is_latest=False)
        (site_dir / "reports" / f"{report['date']}.html").write_text(
            woche_tpl.render(prefix="../", show_explorer=True, **ctx_archiv),
            encoding="utf-8")
        # Der Foliensatz je Ausgabe. Feste Vorlage, feste Platzhalter, harte
        # Zeichengrenzen - der Nutzer braucht selten einen Text, er braucht
        # drei Folien fuer den Montagstermin. Ein Ueberlauf wirft, statt eine
        # Folie auszuliefern, die unten herauslaeuft; das darf keine Ausgabe
        # kosten, deshalb wird der Fehler protokolliert und nicht geworfen.
        try:
            from . import folien as folien_mod
            (folien_dir / f"{report['date']}.html").write_text(
                folien_mod.baue(report), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            log.error("Foliensatz fuer %s nicht erzeugt: %s",
                      report["date"], exc)
        if i == 0:
            latest_ctx = ctx
            (site_dir / "index.html").write_text(
                woche_tpl.render(prefix="", show_explorer=False, **ctx),
                encoding="utf-8")

    # Das Fruehwarn-Board steht auf der Startseite, braucht aber alle
    # Ausgaben - erst nach der Schleife oben liegen sie vor. Die Startseite
    # wird deshalb mit dem fertigen Board noch einmal geschrieben. Ein zweiter
    # Rendervorgang derselben Vorlage kostet Millisekunden; die Alternative
    # waere, `wochen` vor der Schleife ein zweites Mal zu berechnen (14 x
    # _flatten(), der teuerste Teil des Rendervorgangs).
    if latest_ctx is not None:
        latest_ctx["fruehwarnung"] = fruehwarnung_mod.aufbereiten(
            wochen, reports_dir.parent.parent)
        (site_dir / "index.html").write_text(
            woche_tpl.render(prefix="", show_explorer=False, **latest_ctx),
            encoding="utf-8")

    latest = reports[0] if reports else None
    diff_report = _load_latest_diff_report(reports_dir / "differenzierung")

    # ---- Differenzierung: BEIDE Speicher, zu einem Bestand gemischt.
    #   differentiation_db.json  - der rotierende Web-Sweep (Kategorie-Sweep).
    #   differentiation.jsonl    - der Kurator ueber den Presse-Crawl.
    # Bis zum 08.08.2026 rendere die Seite nur den ersten; der Kurator lief
    # jede Woche und landete nirgends. Die Zusammenfuehrung (und warum ein
    # Presse-Eintrag seine Hauptzeile aus `summary` bezieht) steht in
    # report/differenzierung_view.py.
    from datetime import date
    db = DiffDB(state_dir / "differentiation_db.json")
    store = DiffStore(state_dir / "differentiation.jsonl")
    latest_date = latest["date"] if latest else date.today().isoformat()
    theme_label_map = dict(SWEEP_THEMES)

    # Der Bericht wird ZERLEGT statt angehaengt: die Lage in den Seitenkopf,
    # die Muster neben das Marktbild, die Einordnung je Hebel ueber dessen
    # Beispiele. Nur ein Bericht in der alten Gliederung (bis 08.08.2026:
    # "Konkrete Entwicklungen" + "Quellenbasis") landet noch als Block am
    # Seitenende - siehe report/differenzierung_bericht.py.
    diff_teile = differenzierung_bericht.zerlegen(
        (diff_report or {}).get("briefing_md", ""), theme_label_map)

    # Die Bilder kommen aus dem Index, den die Pipeline gefuellt hat
    # (report/diff_bilder.py). `render_site()` fasst nie das Netz an - sonst
    # koennte weder `scripts/pruefe_portal.py` noch ein Test die Seite bauen.
    # Sie gehen IN `aufbereiten` hinein, nicht nachtraeglich darueber: die
    # Gewichtung eines Hebels entscheidet anhand des Bildes, wer ihn anfuehrt.
    diff = differenzierung_view.aufbereiten(
        list(db.entries.values()), store.entries(), SWEEP_THEMES,
        latest_date, _DIFF_COLOR, diff_teile["einordnung"],
        bilder=diff_bilder.lade_index(state_dir.parent.parent),
        vorhandene_bilder=vorhandene_bilder)
    (site_dir / "differenzierung.html").write_text(
        env.get_template("differenzierung.html.j2").render(
            prefix="", diff=diff,
            # Neben der Ueberschrift stand bis zum 08.08.2026 in einem sonst
            # leeren Drittel nur "Stand 7. August 2026" - der beste Platz der
            # Seite mit einer Datumszeile belegt (report/seit.py).
            seit=seit_mod.fuer_differenzierung(diff),
            # Was waechst, was kippt - die Zeitachse aus `first_seen`. Kein
            # neuer Speicher, kein Modellaufruf: das Rohmaterial liegt seit
            # Juli vor, es hat es nur nie jemand gerechnet.
            verlauf=verlauf_mod.aufbereiten(diff["bestand"], theme_label_map),
            # Die Gegenfrage: wer hat einen Hebel, den wir nicht haben?
            # Gerechnet gegen eine GEPFLEGTE Liste - nie gegen eine
            # Modellvermutung (report/luecken.py).
            luecken=luecken_mod.bauen(
                diff["bestand"], theme_label_map,
                luecken_mod.lade_eigene_hebel(reports_dir.parent.parent)),
            date_de=_fmt_date_de(latest["date"]) if latest else "",
            diff_lage_html=_md_to_html(diff_teile["lage"])
            if diff_teile["lage"] else "",
            diff_muster=[dict(m, text_html=_md_to_html(m["text"], inline=True))
                         for m in diff_teile["muster"]],
            # Nur noch der Rueckfall fuer die alte Gliederung.
            diff_report_html=_md_to_html(diff_teile["alt_md"])
            if diff_teile["alt_md"] else "",
            diff_report_date=_fmt_date_de(diff_report["date"])
            if diff_report else ""),
        encoding="utf-8")

    # ---- Meldungen: die Belegebene an EINEM Ort. Loest den zugeklappten
    # Explorer der Berichtsseite, suche.html und archive.html ab - drei Orte
    # fuer dasselbe Beduerfnis ("zeig mir die Einzelmeldung"). Die Suche
    # selbst bleibt rein clientseitig: app.js laedt search_index.json per
    # fetch() und filtert im Browser, kein Suchserver noetig.
    (site_dir / "meldungen.html").write_text(
        env.get_template("meldungen.html.j2").render(
            prefix="", archive=archive, num_operators=num_operators,
            date_de=(latest_ctx or {}).get("date_de", ""),
            highlights=(latest_ctx or {}).get("highlights", []),
            # Nach Ressort gruppiert und innerhalb gewichtet - vorher waren
            # es 193 identisch gebaute Zeilen untereinander.
            ressorts=_nach_ressort((latest_ctx or {}).get("highlights", [])),
            explorer_json=(latest_ctx or {}).get("explorer_json", "[]"),
            regions=(latest_ctx or {}).get("regions", []),
            categories=(latest_ctx or {}).get("categories", [])),
        encoding="utf-8")

    # ---- Promo Uebersicht: eigener zweiter Anwendungsfall neben Marktrecherche
    # (siehe promo_pipeline.py). Eigene Quellen (config/promo_sources.yaml),
    # eigener State (data/state/promo_db.json) - komplett getrennt vom
    # Presse-Collect oben. Fehlt der State (z. B. render_site() ohne
    # vorherigen Promo-Lauf), wird einfach eine leere Uebersicht gerendert.
    promo_entries: list[dict] = []
    promo_sources: list = []
    if cfg is not None:
        promo_cfg = load_promo_config(cfg.root)
        promo_sources = promo_cfg.sources
        promo_db_raw: dict = {}
        promo_db_path = state_dir / "promo_db.json"
        if promo_db_path.exists():
            try:
                promo_db_raw = json.loads(promo_db_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                log.warning("promo_db.json unlesbar - rendere leere Promo-Uebersicht")
        promo_entries = promo_db_raw.get("entries") or []
        promo_updated = promo_db_raw.get("updated") or (latest["date"] if latest else "")

        # Kampagnenbilder (data/state/promo_images/<hash>-1280.jpg, von
        # promo_bilder.py je ANGEBOT abgelegt) sind Pipeline-State, keine
        # Site-Ausgabe - sie werden bei jedem Rendern nach site/promo/images/
        # kopiert, wie site/images/ auch. Nie von Hand etwas unter site/
        # ablegen.
        #
        # Bis zum 07.08.2026 lag hier je MARKE ein Screenshot, und die
        # Pruefung `ist_leer` fing die weisse Aufnahme ab, die dabei
        # entstand. Beides ist weg: promo_bilder.py prueft schon beim Ablegen
        # (Mindestbreite UND `ist_leer`), ein leeres Bild kommt gar nicht
        # mehr bis hierher. Was bleibt, ist die andere Richtung - ein
        # Eintrag, dessen Bilddatei nicht mehr da ist, verliert seinen
        # Verweis, sonst zeigt die Seite einen leeren Kasten.
        promo_dir_images = site_dir / "promo" / "images"
        promo_bild_ordner = promo_bilder.bildordner(cfg.root)
        ausgeliefert: set[str] = set()
        for e in promo_entries:
            name = e.get("image")
            if not name:
                continue
            quelle = promo_bild_ordner / name
            if not quelle.exists():
                for feld in ("image", "image_w", "image_h"):
                    e.pop(feld, None)
                continue
            if name not in ausgeliefert:
                promo_dir_images.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(quelle, promo_dir_images / name)
                ausgeliefert.add(name)
        # Der Ordner SPIEGELT, er sammelt nicht - sonst behielte eine
        # ausgelaufene Aktion ihr Bild fuer immer.
        if promo_dir_images.exists():
            for veraltet in promo_dir_images.iterdir():
                if veraltet.is_file() and veraltet.name not in ausgeliefert:
                    veraltet.unlink()

        promo_view = prepare_promo_view(promo_entries, promo_cfg.sources,
                                        promo_updated)

        promo_report_dir = reports_dir / "promo"
        promo_report = None
        if promo_report_dir.exists():
            cands = [f for f in promo_report_dir.glob("*.md") if _DATE_RE.fullmatch(f.stem)]
            if cands:
                p = max(cands, key=lambda f: f.stem)
                promo_report = {"date": p.stem, "briefing_md": p.read_text(encoding="utf-8")}

        promo_dir = site_dir / "promo"
        promo_dir.mkdir(exist_ok=True)
        (promo_dir / "index.html").write_text(
            env.get_template("promo_index.html.j2").render(
                prefix="../", date_de=_fmt_date_de(promo_updated),
                promo_view=promo_view,
                seit=seit_mod.fuer_promo(promo_view),
                promo_report_html=_md_to_html(promo_report["briefing_md"])
                if promo_report else "",
                promo_report_date=_fmt_date_de(promo_report["date"])
                if promo_report else "",
                promo_lead=_promo_lead(promo_report["briefing_md"])
                if promo_report else ""),
            encoding="utf-8")
        (promo_dir / "quellen.html").write_text(
            env.get_template("promo_quellen.html.j2").render(
                prefix="../", sources=promo_cfg.sources),
            encoding="utf-8")

    # ---- Themenseiten: eine Seite je laufendem Ereignis, temporaer.
    # Der Ordner SPIEGELT den Themenspeicher, er sammelt nicht - genau wie
    # site/images/. Ein beendetes Thema verliert damit seine Seite von
    # selbst, ohne dass irgendwo eine Loeschliste gefuehrt werden muss.
    # Die Promos stehen hier schon bereit: ein Thema zeigt die Aktionen, die
    # sich ueber seine Suchwoerter belegen lassen.
    thema_dir = site_dir / "thema"
    geschrieben: set[str] = set()
    if themen:
        thema_dir.mkdir(exist_ok=True)
        thema_tpl = env.get_template("thema.html.j2")
        for thema in themen:
            view = build_thema_view(thema, promo_entries)
            # Der rote Link auch hier. Eine Themenseite zeigt dieselben
            # Meldungen wie die Titelseite, nur auf ein Ereignis verengt -
            # und die Historie eines Ereignisses ist genau der Ort, an dem
            # jemand nach dem vollen Text sucht. Sie baut ihre Karten aber
            # aus dem Themenspeicher und nicht aus `_flatten()`, bekommt die
            # Zuordnung oben also nicht mit; dieselbe Positivlisten-Falle
            # wie in `_items_payload`.
            for schluessel in ("aufmacher", "zwei", "rest"):
                wert = view.get(schluessel)
                for h in ([wert] if isinstance(wert, dict) else (wert or [])):
                    pfad = uebersetzung_je_url.get(h.get("url") or "")
                    if pfad:
                        h["uebersetzung"] = pfad
            datei = f"{view['slug']}.html"
            (thema_dir / datei).write_text(
                thema_tpl.render(prefix="../", t=view), encoding="utf-8")
            geschrieben.add(datei)
    if thema_dir.exists():
        for veraltet in thema_dir.iterdir():
            if veraltet.is_file() and veraltet.name not in geschrieben:
                veraltet.unlink()

    # ---- Uebersetzungsseiten, eine je Eintrag im Speicher.
    #
    # Anders als `thema/` wird hier NICHT gespiegelt: kein Aufraeumen, kein
    # Loeschen veralteter Dateien. Eine Uebersetzung gehoert zu einer
    # Meldung, und die steht noch in Jahren im Archiv - eine Seite, die
    # verschwindet, sobald ihre Ausgabe aus dem Frischefenster rotiert,
    # waere ein toter Link im eigenen Bestand.
    #
    # Die HTML-Dateien entstehen bei JEDEM Rendern neu aus dem JSONL. Das
    # ist der Grund, warum der Speicher das JSONL ist und nicht der Ordner:
    # eine Aenderung an der Vorlage schreibt sonst dreitausend
    # Einzeldateien in die git-Historie (Premortem 7).
    ueb_seiten = uebersetzung_view_mod.seiten(uebersetzungen)
    if ueb_seiten:
        ueb_dir = site_dir / uebersetzung_view_mod.ORDNER
        ueb_dir.mkdir(exist_ok=True)
        ueb_tpl = env.get_template("uebersetzung.html.j2")
        for seite in ueb_seiten:
            (ueb_dir / seite["dateiname"]).write_text(
                ueb_tpl.render(prefix="../", u=seite["u"],
                               sprachname=seite["sprachname"],
                               sprachname_dativ=seite["sprachname_dativ"]),
                encoding="utf-8")
        log.info("Uebersetzungsseiten gerendert: %d", len(ueb_seiten))

    # ---- Suchindex und Dossier-Seite.
    #
    # Sie stehen hier unten und nicht weiter oben, weil der Index ALLE drei
    # Bereiche traegt - und die Promo-Aktionen entstehen erst im Block
    # darueber. Wer "Telekom" sucht, will die Meldungen, die Beispiele UND
    # die laufenden Aktionen der Marke sehen; bis zum 08.08.2026 fehlte der
    # dritte Bereich ganz, und die Suche fuehrte auf eine Seite, die vor den
    # Treffern erst ihre eigenen Ressorts zeigte (Antonio: "Ich verstehe
    # nicht, warum ich da weitergeleitet werde").
    #
    # Gesucht wird rein clientseitig: app.js laedt search_index.json per
    # fetch() und filtert im Browser, kein Suchserver noetig.
    search_index = suchindex.bauen(
        wochen, diff["bestand"], theme_label_map,
        promo_aktionen=promo_entries, mechanik_label=PROMO_MECHANICS)
    (site_dir / "search_index.json").write_text(
        json.dumps(search_index, ensure_ascii=False), encoding="utf-8")

    # ---- Der Stichwort-Index der Newsletter-Anmeldung.
    # Die Trefferzahl-Vorschau ("Ihr Stichwort hätte in den letzten 30 Tagen
    # 47 Meldungen getroffen") ist die wirksamste Einzelmassnahme gegen
    # Abo-Muedigkeit - sie loest das Problem, bevor es Mails erzeugt. Aber
    # die Anmeldeseite ist statisch und kann kein Python aufrufen, und der
    # Signup-Dienst hat die Berichtsarchive nicht. Also zaehlt der Browser
    # gegen diese Datei, und die Pipeline schreibt sie bei jedem Lauf mit.
    #
    # `newsletter/filters.baue_stichwort_index()` ist ihr Erzeuger UND die
    # Testgrundlage: ein Test haelt jedes Wort des Index gegen `vorschau()`.
    # Ohne den wuerde die Seite eine Zahl voraussagen, die der Versand nie
    # einloest, und beide waeren fuer sich gruen.
    from ..newsletter.filters import baue_stichwort_index
    from ..newsletter.config import lade_katalog as _lade_nl_katalog
    try:
        _nl_tage = _lade_nl_katalog(_wurzel).grenzen.vorschau_tage
    except (FileNotFoundError, ValueError) as exc:
        log.warning("newsletter.yaml nicht lesbar (%s) - Stichwort-Index mit "
                    "30 Tagen", exc)
        _nl_tage = 30
    (site_dir / "data").mkdir(exist_ok=True)
    (site_dir / "data" / "keyword-index.json").write_text(
        json.dumps(baue_stichwort_index(reports_dir, tage=_nl_tage),
                   ensure_ascii=False), encoding="utf-8")

    # ---- Die Anmeldeseite und ihre zwei Abschlussseiten.
    # Die beiden kleinen sind die wichtigeren: sie sind STATISCH und kommen
    # ohne den Signup-Dienst aus. Wer auf den Abmeldelink klickt, waehrend
    # Render die Instanz schlafen laesst, wartet sonst eine Minute vor einem
    # Spinner - und der Abmeldelink ist der einzige Abmeldeweg.
    from . import newsletter_seite as nl_seite
    try:
        nl_katalog = _lade_nl_katalog(_wurzel)
    except (FileNotFoundError, ValueError) as exc:
        log.error("newsletter.yaml nicht lesbar (%s) - keine Anmeldeseite", exc)
        nl_katalog = None
    if nl_katalog is not None:
        fassung = rechtstexte_mod.aktuelle_einwilligung(_wurzel)
        # Zwei UNABHAENGIGE Bedingungen sperren diese Seite, und der Leser
        # muss beide OBEN erfahren. Der Hinweis auf den fehlenden Dienst kam
        # bis zum 12.08.2026 nur aus app.js - und landete damit unter dem
        # Absendeknopf, am Fuss einer 2145 px hohen Seite. Wer der Navigation
        # folgte, waehlte vier Filter, tippte seine Adresse ein und hakte die
        # Einwilligung ab, bevor er las, dass nichts davon ankommt. Solange
        # die Rechtstexte unvollstaendig waren, fiel das niemandem auf: ohne
        # Navigationseintrag fand die Seite ohnehin niemand.
        nl_dienst_url = (cfg.settings.get("newsletter_dienst_url", "")
                         if cfg is not None else "")
        (site_dir / "newsletter.html").write_text(
            env.get_template("newsletter.html.j2").render(
                prefix="", active="newsletter",
                dimensionen=nl_seite.dimensionen(nl_katalog),
                grenzen=nl_katalog.grenzen,
                dienst_da=bool(nl_dienst_url),
                einwilligung_absaetze=nl_seite.einwilligung_absaetze(
                    fassung.text if fassung else ""),
                einwilligung_version=fassung.version if fassung else "—",
                nl_config=nl_seite.konfiguration(
                    nl_katalog,
                    dienst_url=nl_dienst_url,
                    frei=env.globals["newsletter_verlinkt"])),
            encoding="utf-8")
        for name, (titel, text, weiter) in nl_seite.abschlussseiten().items():
            (site_dir / f"newsletter-{name}.html").write_text(
                env.get_template("newsletter_abschluss.html.j2").render(
                    prefix="", active="newsletter", titel=titel, text=text,
                    weiter=weiter),
                encoding="utf-8")
    (site_dir / "suche.html").write_text(
        env.get_template("suche.html.j2").render(
            prefix="",
            top_absender=suchindex.haeufigste_absender(search_index)),
        encoding="utf-8")

    # ---- Wettbewerb: die Dauerseite zu Telekom, O2 und 1&1.
    # Antonio am 08.08.2026: "nicht nur die Meldung dieser Woche, sondern
    # ueber die Wochen und Monate - wie passt die Meldung dieser Woche zu
    # dem, was davor kam?" Sie entsteht komplett hier beim Rendern aus dem
    # Berichtsarchiv: kein eigener State, kein zusaetzlicher LLM-Aufruf.
    # Deshalb waechst sie mit jedem Lauf, ohne dass die Pipeline etwas davon
    # wissen muss.
    wettbewerb_view = build_wettbewerb_view(
        wochen, getattr(cfg, "focus_competitors", None) or [],
        promo_entries, promo_sources,
        # Die Differenzierungs-Hebel je Wettbewerber. Sie lagen bis zum
        # 08.08.2026 eine Seite weiter und dort nach THEMA sortiert - also
        # genau nicht nach der Frage "was macht dieser eine Anbieter".
        diff_bestand=diff["bestand"], theme_label=theme_label_map)
    (site_dir / "wettbewerb.html").write_text(
        env.get_template("wettbewerb.html.j2").render(
            prefix="", wettbewerb=wettbewerb_view,
            seit=seit_mod.fuer_wettbewerb(wettbewerb_view,
                                          wettbewerb_view["stand"]),
            date_de=_fmt_date_de(wettbewerb_view["stand"])),
        encoding="utf-8")

    # ---- Lieferzeiten: die einzige Frage dieses Portals, zu der es sonst
    # NIRGENDS eine Antwort gibt - es existiert keine oeffentliche Studie, die
    # Lieferzeiten der deutschen Anbieter systematisch vergleicht. Die Seite
    # entsteht wie die Wettbewerbsseite beim Rendern, aus dem Speicher, den
    # die Sammelstufe gefuellt hat (collect/lieferzeit.py).
    from ..collect.lieferzeit import lade_warenkorb
    lieferzeit_daten: dict = {}
    lieferzeit_pfad = state_dir / "lieferzeit.json"
    if lieferzeit_pfad.exists():
        try:
            lieferzeit_daten = json.loads(
                lieferzeit_pfad.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.warning("lieferzeit.json unlesbar - rendere leere Seite")
    lieferzeit_view = lieferzeit_view_mod.aufbereiten(
        lieferzeit_daten, lade_warenkorb(reports_dir.parent.parent),
        heute=latest["date"] if latest else "")
    (site_dir / "lieferzeit.html").write_text(
        env.get_template("lieferzeit.html.j2").render(
            prefix="", lieferzeit=lieferzeit_view),
        encoding="utf-8")

    # ---- Tarife: Effektivpreis und Positionskarte.
    # Die erste Seite, die nicht aus Meldungen entsteht, sondern aus den
    # Pflichtdokumenten nach § 1 TK-TransparenzV. Die Punktkoordinaten des
    # Streudiagramms werden hier gerechnet, nicht im Browser - kein CDN-JS
    # ist Hausregel, und so ist die Darstellung ohne Browser testbar.
    from . import tarife_view as tarife_view_mod
    try:
        from ..collect.tarif_crawler import lade_quellen as _lade_tarifquellen
        tarif_quellen = _lade_tarifquellen(reports_dir.parent.parent)
    except Exception:  # noqa: BLE001 - eine fehlende Config kippt keine Seite
        tarif_quellen = []
    tarife = tarife_view_mod.aufbereiten(
        state_dir / "tarife.jsonl", tarif_quellen,
        heute=latest["date"] if latest else "")
    (site_dir / "tarife.html").write_text(
        env.get_template("tarife.html.j2").render(prefix="", tarife=tarife),
        encoding="utf-8")

    # ---- Geraete- und Preisradar: Positionskarte, SKU-Matrix, Lifecycle.
    # Zwei Seiten aus einem Datensatz, wie Promo-Uebersicht und Promo-Quellen.
    # Beide entstehen ohne Netz und ohne Modell - der Zustand liegt fertig in
    # data/state/geraete_db.json und geraete_preise.jsonl.
    #
    # Die Seite steht bewusst NICHT in der Navigation: die
    # Veroeffentlichungsschwelle (CLAUDE.md §5) verlangt, dass eine Seite ihre
    # Frage beantworten kann, bevor sie verlinkt wird. Erreichbar ist sie
    # ueber ihren direkten Link; die Schwelle steht beziffert im Test
    # (tests/test_geraete_seite.py).
    #
    # Das try/except umschliesst NUR die Datenaufbereitung, nicht das
    # Rendern. Beides zusammen abzufangen hiess: ein einziger kaputter
    # Eintrag laesst beide Seiten verschwinden, `site/` behaelt beim naechsten
    # Commit die alte Fassung, und die Seite friert still auf dem Stand der
    # Vorwoche ein - waehrend `pruefe_portal.py` "nicht gerendert" meldet und
    # trotzdem mit 0 endet. CLAUDE.md §6: "Eine gescheiterte Stufe muss sich
    # bis auf die Seite melden. log.error reicht nicht."
    #
    # Deshalb: gescheiterte Aufbereitung -> die Seite entsteht trotzdem und
    # SAGT, dass sie nichts zeigen kann. Aufbereitet wird `geraete` weiter
    # OBEN, vor der ersten gerenderten Seite - es entscheidet ueber einen
    # Navigationseintrag, und die Navigation steht auf jeder Seite.
    # Der Gesamtexport entsteht VOR der Seite: sie nennt Zeilenzahl und
    # Groesse neben dem Link, und diese Zahlen kommen aus den wirklich
    # geschriebenen Dateien. Ein Link mit gerechneter statt gemessener Zahl
    # waere genau die Sorte Angabe, die dieses Portal nicht macht.
    #
    # Was er schreibt, waehlt er NICHT selbst aus (31.08.2026): `aufbereiten`
    # hat den Bestand einmal geprueft und bereinigt und reicht ihn als
    # `export_bestand` heraus. Vorher filterte der Export nach `status` und
    # die Seite nach der Plausibilitaetspruefung - zwei Rechnungen fuer
    # dieselbe Menge, und sie liefen auseinander: zwei Gebrauchtpreise
    # standen in `geraete-aktuell.csv` mit `Zustand = neu`.
    try:
        from . import geraete_export as _geraete_export
        geraete["export"] = _geraete_export.schreibe_exporte(
            site_dir, geraete.get("export_bestand") or [],
            geraete.get("alle_punkte") or [], geraete.get("katalog_obj"),
            stand=geraete.get("stand", ""))
    except Exception as exc:                      # noqa: BLE001
        # Wie beim Rest dieser Stufe: ein gescheiterter Export darf die
        # Seite nicht kosten - aber er verschwindet auch nicht still.
        log.error("Geraete-Export gescheitert: %s: %s", type(exc).__name__, exc)
        from . import geraete_export as _geraete_export
        geraete["export"] = _geraete_export.leer()

    (site_dir / "geraete.html").write_text(
        env.get_template("geraete.html.j2").render(prefix="", geraete=geraete),
        encoding="utf-8")
    (site_dir / "geraete-quellen.html").write_text(
        env.get_template("geraete_quellen.html.j2").render(
            prefix="", geraete=geraete),
        encoding="utf-8")

    # ---- Transparenz: Laufprotokoll UND Quellenbestand auf einer Seite.
    # Beide beantworten dieselbe Frage ("kann ich dem Ding trauen?") und
    # wurden ohnehin nacheinander gelesen.
    run = (latest or {}).get("run") if latest else None
    if run:
        run = dict(run)
        run["sources"] = [s for s in run.get("sources", [])
                           if not _is_suppressed_source(s)]
        summary = dict(run.get("source_summary") or {})
        summary["total"] = len(run["sources"])
        # Die Statuswerte des Laufprotokolls heissen "ok", "empty", "fail" und
        # "quarantaene" (pipeline.py:249ff). Die Zusammenfassung der Seite
        # nennt den dritten "failed" - bis zum 06.08.2026 zaehlte diese
        # Schleife deshalb nach "failed" und fand nie einen: der Lauf vom
        # 05.08. hatte 6 gescheiterte Quellen, die Seite meldete 0. Der
        # Schluessel der Zusammenfassung und der Wert im Protokoll sind zwei
        # verschiedene Namen fuer dieselbe Sache - hier die Zuordnung.
        for schluessel, status in (("ok", "ok"), ("empty", "empty"),
                                   ("failed", "fail")):
            summary[schluessel] = sum(1 for s in run["sources"]
                                      if s.get("status") == status)
        # Stillgelegte Quellen zaehlen nicht als "abgefragt" - sonst sieht die
        # Bilanz besser aus, je mehr Quellen aufgegeben wurden.
        summary["quarantaene"] = sum(1 for s in run["sources"]
                                     if s.get("status") == "quarantaene")
        summary["total"] -= summary["quarantaene"]
        run["source_summary"] = summary
    by_region: dict[str, list] = {}
    tech_themes: list[dict] = []
    news_sources: list = []
    if cfg is not None:
        for op in cfg.operators:
            by_region.setdefault(op.region_name, []).append(op)
        # Themenfelder (config/tech_sources.yaml) bekommen einen eigenen Block
        # auf der Quellenseite - sie sind weder Betreiber noch Fachpresse,
        # und die Seite verspricht Nachpruefbarkeit ueber ALLE Quellen.
        for key, label in cfg.themes:
            quellen = [s for s in cfg.tech_sources if s.theme == key]
            if quellen:
                tech_themes.append({"key": key, "label": label,
                                    "sources": quellen})
        news_sources = cfg.news_sources

    (site_dir / "transparenz.html").write_text(
        env.get_template("transparenz.html.j2").render(
            prefix="", run=run, report=latest,
            # Die Zahl, die die Seite wirklich zeigen kann: bewertete
            # Meldungen nach dem Ausfiltern stillgelegter Quellen. NICHT
            # stats.new - das sind die neu GESAMMELTEN.
            n_bewertet=len(_flatten(latest)) if latest else 0,
            date_de=_fmt_date_de(latest["date"]) if latest else "",
            # Die CTM-Linse erklaert sich hier und nur hier: die Startseite
            # zeigt die Etiketten, die Transparenzseite sagt, was sie
            # bedeuten. Die Sicherheitsskala kommt aus derselben Datei, aus
            # der auch der Prompt sie bezieht - zwei Fassungen davon waeren
            # zwei Bedeutungen desselben Wortes.
            ctm_stufen=[{"stufe": s, "label": ctm.STUFEN_LABEL[s],
                         "text": ctm.STUFEN_ERKLAERUNG[s]}
                        for s in (3, 2, 1, 0)],
            sicherheitsskala=ctm.lade_fokus(
                reports_dir.parent.parent).sicherheitsskala,
            # Der Newsletter-Abschnitt: NUR Zahlen, nie Adressen. Ein
            # CI-Test prueft die Statistikdatei gegen ein Adressmuster.
            newsletter=newsletter_protokoll.aufbereiten(
                state_dir / "newsletter_stats.jsonl"),
            by_region=by_region, news_sources=news_sources,
            tech_themes=tech_themes,
            n_tech_sources=sum(len(t["sources"]) for t in tech_themes),
            num_operators=num_operators),
        encoding="utf-8")

    if not reports:
        (site_dir / "index.html").write_text(
            woche_tpl.render(prefix="", report=None, date_de="", highlights=[],
                             explorer_json="[]", front=_titelseite([]),
                             competitors=[], dash=None, toc=[], lesezeit=0,
                             briefing_html="", regions=[],
                             categories=[], archive=[], is_latest=True,
                             show_explorer=False, themen=[],
                             num_operators=num_operators, n_competitors=0),
            encoding="utf-8")

    # ---- Weiterleitungen von den alten Dateinamen. Sie stehen in Lesezeichen
    # und in Mails an die Fachabteilung; ein 404 waere die teuerste Art, eine
    # Navigation aufzuraeumen.
    # `suche.html` steht nicht mehr darunter: der Name ist seit dem 08.08.2026
    # wieder eine echte Seite - die Dossier-Suche. Ein Lesezeichen darauf
    # landet also dort, wo es immer hinwollte.
    for alt, ziel in (("bericht.html", "index.html"),
                      ("archive.html", "meldungen.html#archiv"),
                      ("protokoll.html", "transparenz.html"),
                      ("sources.html", "transparenz.html#bestand"),
                      ("wettbewerber.html", "wettbewerb.html")):
        (site_dir / alt).write_text(_redirect_html(ziel), encoding="utf-8")

    log.info("Site rendered: %d report(s) -> %s", len(reports), site_dir)
