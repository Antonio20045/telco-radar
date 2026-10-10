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

from . import anbieter_farben as _anbieter_farben
from .ausfall import NEWSLETTER_TEIL, Ausfall, ohne_konfiguration
from . import bilder as report_bilder
from . import diff_bilder, differenzierung_bericht
from . import differenzierung_view, geraete_teurer, wettbewerb_puls
from . import geraete_tco_grafik as _geraete_tco_grafik
from . import fruehwarnung as fruehwarnung_mod, lieferzeit_view as lieferzeit_view_mod
from . import luecken as luecken_mod
from . import newsletter_protokoll, rechtstexte as rechtstexte_mod
from . import seit as seit_mod, verlauf as verlauf_mod
from . import meldungen_seite, startseite as startseite_mod, statik, suchindex
from .differentiation import DIFF_THEMES
from .promo import prepare_promo_view
from .thema import build_thema_view
from .wettbewerb import anker as _wb_anker, build_wettbewerb_view
from ..analyze import ctm, geraete_pruefkennzahlen
from ..analyze import themen_store
from ..analyze.diff_curator import DiffStore
from ..analyze.begriffe import (
    DIGEST_MARKER,
    MECHANICS as PROMO_MECHANICS,
    THEMES as SWEEP_THEMES,
)
from ..analyze.diff_db import DiffDB
from ..promo_config import load_promo_config
from ..textwerkzeug import (
    ABKUERZUNGEN as _ABK,
    gewicht as _gewicht,
    haeufigkeiten as _haeufigkeiten,
    saetze as _saetze,
    slug as _tw_slug,
    wortmenge as _wortmenge,
)
from .. import promo_bilder

_DIFF_COLOR = {t["key"]: t["color"] for t in DIFF_THEMES}

log = logging.getLogger(__name__)

_TEMPLATES = Path(__file__).parent / "templates"
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_SUPPRESSED_SOURCE_DOMAINS = {"inside-digital.de"}

RELEVANCE_LABELS = {
    5: "Sofort ansehen",
    4: "Wichtig",
    3: "Beobachten",
    2: "Randnotiz",
    1: "Randnotiz",
    0: "Unbewertet",
}
CATEGORY_COLORS = _anbieter_farben.KATEGORIE_FARBEN
MONTHS_DE = [
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]


def _fmt_date_de(iso: str) -> str:
    try:
        d = datetime.fromisoformat(iso)
        return f"{d.day}. {MONTHS_DE[d.month - 1]} {d.year}"
    except (ValueError, IndexError):
        return iso


def _fmt_monat_de(iso_monat: str) -> str:
    """ "2026-08" -> "August 2026" - die Ueberschrift einer Monatsgruppe in
    der Chronik der Wettbewerbsseite."""
    try:
        jahr, monat = (iso_monat or "").split("-")[:2]
        return f"{MONTHS_DE[int(monat) - 1]} {jahr}"
    except (ValueError, IndexError):
        return iso_monat


def _redaktion_ausfall_ctx(report: dict) -> dict | None:
    """Fuer eine Runde ohne bewertete Meldung (E3B): der Vorlage fertig
    formatierte Angaben mitgeben, statt Datumsrechnung in Jinja zu treiben.

    `pipeline.run()` traegt das Feld nur ein, wenn es selbst die letzte
    gueltige Redaktion uebernommen hat (siehe
    analyze/redaktion_kontinuitaet.py) - hier wird es nur noch angezeigt.
    """
    ausfall = report.get("redaktion_ausfall")
    if not ausfall:
        return None
    return {
        "stand_de": _fmt_date_de(ausfall.get("stand", "")),
        "grund": ausfall.get("grund", ""),
    }


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(_TEMPLATES),
        autoescape=select_autoescape(["html", "htm", "xml", "j2"]),
    )
    env.filters["domain"] = lambda u: urlsplit(u or "").netloc.removeprefix("www.")
    env.filters["date_de"] = _fmt_date_de
    env.filters["euro"] = _geraete_tco_grafik.euro
    env.filters["monat_de"] = _fmt_monat_de
    env.globals.update(startseite_mod.VORLAGEN_HELFER)
    return env


_MD_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "em",
    "h2",
    "h3",
    "h4",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "ul",
}
_MD_DANGEROUS_TAGS = {
    "base",
    "embed",
    "form",
    "iframe",
    "math",
    "object",
    "script",
    "style",
    "svg",
}


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
        if anker in vergeben:
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
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _redirect_html(ziel: str) -> str:
    """Weiterleitungsseite fuer einen alten Dateinamen.

    Render ist eine Static Site - es gibt keine Serverregel, in die man eine
    301 schreiben koennte. Meta-Refresh plus sichtbarer Link ist deshalb die
    ganze Mechanik; ein Skript waere unnoetig und wuerde ohne JS scheitern."""
    ziel_escaped = html_lib.escape(ziel, quote=True)
    return (
        '<!DOCTYPE html>\n<html lang="de">\n<head>\n<meta charset="utf-8">\n'
        f'<meta http-equiv="refresh" content="0; url={ziel_escaped}">\n'
        f'<link rel="canonical" href="{ziel_escaped}">\n'
        '<meta name="robots" content="noindex">\n'
        "<title>Weitergeleitet – Vodafone Product and Services Insights</title>\n</head>\n"
        '<body style="font-family:Inter,Arial,sans-serif;padding:40px">\n'
        f'<p>Diese Seite ist umgezogen. <a href="{ziel_escaped}">Weiter zu '
        f"{ziel_escaped}</a></p>\n</body>\n</html>\n"
    )


def _load_reports(reports_dir: Path) -> list[dict]:
    reports: dict[str, dict] = {}
    for f in sorted(reports_dir.glob("*.json")):
        if not _DATE_RE.fullmatch(f.stem):
            continue
        try:
            satz = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.warning("Skipping corrupt report json: %s", f)
            continue
        if not satz.get("date"):
            satz["date"] = f.stem
        reports[f.stem] = satz
    for f in sorted(reports_dir.glob("*.md")):
        if _DATE_RE.fullmatch(f.stem) and f.stem not in reports:
            reports[f.stem] = {
                "date": f.stem,
                "generated_with_llm": False,
                "stats": {},
                "briefing_md": f.read_text(encoding="utf-8"),
                "regions": {},
            }
    return [reports[k] for k in sorted(reports, reverse=True)]


def _load_latest_diff_report(reports_dir: Path) -> dict | None:
    """Load the newest generated prose report for the differentiation tab."""
    if not reports_dir.exists():
        return None
    candidates = [f for f in reports_dir.glob("*.md") if _DATE_RE.fullmatch(f.stem)]
    if not candidates:
        return None
    path = max(candidates, key=lambda f: f.stem)
    try:
        return {"date": path.stem, "briefing_md": path.read_text(encoding="utf-8")}
    except OSError:
        log.warning("Differenzierungsbericht nicht lesbar: %s", path)
        return None


_IST_PLATZHALTER = re.compile(
    r"(kein[^,]*betreiber|keine?r?|branche|diverse?|mehrere|unbekannt|"
    r"n/?a|-+|allgemein)",
    re.I,
)


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
            if _IST_PLATZHALTER.fullmatch((h.get("operator") or "").strip()):
                h["operator"] = ""
            h["de_title"] = (
                _first_sentence(h.get("summary") or "", 150) or h.get("title") or ""
            )
            h["schlagzeile"] = _schlagzeile(h)
            h["ressort"] = _ressort(h)
            h["ressort_label"] = _RESSORT_LABEL[h["ressort"]]
            try:
                h["ctm_bezug"] = int(h.get("ctm_bezug"))
            except (TypeError, ValueError):
                h["ctm_bezug"] = _CTM_BEZUG_ALTBERICHT
            h.setdefault("ctm_label", ctm.STUFEN_LABEL.get(h["ctm_bezug"], ""))
            out.append(h)
    out.sort(key=lambda h: (*_rangschluessel(h), h.get("date") or ""), reverse=True)
    for i, h in enumerate(out):
        h["id"] = i
    return out


def _is_suppressed_source(item: dict) -> bool:
    host = urlsplit(item.get("url") or "").netloc.removeprefix("www.").lower()
    source = (item.get("source") or "").strip().lower()
    return (
        source == "inside digital"
        or host in _SUPPRESSED_SOURCE_DOMAINS
        or any(host.endswith("." + domain) for domain in _SUPPRESSED_SOURCE_DOMAINS)
    )


def _strip_suppressed_source_content(text: str) -> str:
    """Remove stale source-linked paragraphs/lines from historical briefings."""
    blocks = re.split(r"\n\s*\n", text or "")
    kept = [
        block
        for block in blocks
        if not any(domain in block.lower() for domain in _SUPPRESSED_SOURCE_DOMAINS)
        and "inside digital" not in block.lower()
    ]
    cleaned = "\n\n".join(kept)
    return re.sub(
        r"(?im)^.*(?:inside-digital\.de|inside digital).*$\n?", "", cleaned
    ).strip()


TECH_THEMES = [
    ("5G Standalone", ["standalone", "5g sa", "5g-sa", "5g core", "sa network", "5g+"]),
    (
        "Satellit / NTN",
        [
            "satellite",
            "satellit",
            "ntn",
            "direct-to-cell",
            "direct to cell",
            "starlink",
            "spacemobile",
            "non-terrestrial",
            "d2c",
            "leo ",
        ],
    ),
    (
        "KI / AI",
        [
            " ai ",
            " ai-",
            "a.i.",
            "artificial intelligence",
            "genai",
            "gen ai",
            "agentic",
            "machine learning",
            " llm",
            "copilot",
            " ki ",
            "ki-",
        ],
    ),
    (
        "Glasfaser / FTTH",
        ["fiber", "fibre", "ftth", "glasfaser", "gigabit", "broadband"],
    ),
    (
        "Private Networks",
        ["private 5g", "private network", "campus network", "private-5g"],
    ),
    ("IoT / eSIM", ["iot", "esim", "e-sim", "m2m", "internet of things"]),
    (
        "Cloud / Edge",
        ["cloud", "edge computing", "hyperscaler", "edge-computing", " mec "],
    ),
    ("Open RAN", ["open ran", "openran", "o-ran", "oran", "vran", "v-ran"]),
    ("6G", ["6g"]),
    ("FWA", ["fwa", "fixed wireless", "fixed-wireless"]),
]


def _tag_tech(text):
    t = " " + (text or "").lower() + " "
    return [name for name, kws in TECH_THEMES if any(k in t for k in kws)]


RESSORTS: list[tuple[str, str, set[str]]] = [
    ("netz", "Netz & Technik", {"Netz/Technologie"}),
    ("tarife", "Tarife & Angebote", {"Tarif/Pricing", "Produktlaunch", "Kampagne"}),
    ("regulierung", "Regulierung & Politik", {"Regulierung"}),
    ("geld", "Geld & Übernahmen", {"Finanzen", "M&A"}),
    ("partner", "Partnerschaften", {"Partnerschaft"}),
    ("vermischt", "Vermischtes", {"Sonstiges"}),
]
_SATELLIT = ("satellit", "Satellit & Direct-to-Cell")
_RESSORT_REIHENFOLGE = [
    "netz",
    "tarife",
    _SATELLIT[0],
    "regulierung",
    "geld",
    "partner",
    "vermischt",
]
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


_GENERISCHE_NAMENSWOERTER = {
    "group",
    "telecom",
    "telecoms",
    "mobile",
    "communications",
    "holdings",
    "international",
    "limited",
    "global",
    "media",
    "news",
    "corp",
    "world",
    "corporation",
    "company",
    "networks",
    "network",
    "digital",
    "wireless",
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
    return frozenset(w for w in woerter if w not in _GENERISCHE_NAMENSWOERTER)


_MAX_JE_ABSENDER = 2
_CTM_BEZUG_ALTBERICHT = 1
_KUERZEN_MIND_ANTEIL = 0.6

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


_FADEN_MAX = 3
_FADEN_MIND_TREFFER = 2
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


def _faden(highlights: list[dict], saetze: list[str]) -> list[list[dict]]:
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
        _wortmenge(
            f"{h.get('schlagzeile') or ''} {h.get('operator') or ''} "
            f"{h.get('title') or ''} {h.get('summary') or ''}"
        )
        for h in highlights
    ]
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
            kandidaten.append(
                (-_gewicht(selten, haeufigkeit), -_bildbreite(h), rang, h)
            )
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
    return sorted(
        highlights,
        key=lambda h: (
            -int(h.get("ctm_bezug") or 0),
            -int(h.get("relevance") or 0),
            -int(h.get("quellenzahl") or 1),
        ),
    )


def _titelseite(
    highlights: list[dict],
    faden: list[list[dict]] | None = None,
    belegt: list[str] | None = None,
) -> dict:
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
    absender: list[set[str]] = []
    vergeben: list[int] = []

    def gruppe(h: dict) -> int | None:
        kw = _kennwoerter(h.get("operator") or h.get("source_label") or "")
        if not kw:
            return None
        for i, g in enumerate(absender):
            if g & kw:
                g |= kw
                return i
        absender.append(set(kw))
        vergeben.append(0)
        return len(absender) - 1

    def nimm(
        n: int,
        *,
        mind_breite: int = 0,
        aus: list[dict] | None = None,
        streng: bool = False,
    ) -> list[dict]:
        gewaehlt: list[dict] = []
        stufen = (
            [(mind_breite, True)]
            if streng
            else (
                ([(mind_breite, True)] if mind_breite else []) + [(0, True), (0, False)]
            )
        )
        for anspruch, deckel in stufen:
            for h in highlights if aus is None else aus:
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
        return max(
            (_rangschluessel(h) for h in highlights if frei(h, mind_breite)),
            default=None,
        )

    def gleichrangig(
        kandidaten: list[dict], latte: tuple[int, int] | None
    ) -> list[dict]:
        return [h for h in kandidaten if latte is None or _rangschluessel(h) >= latte]

    offen = [list(k) for k in (faden or []) if k]
    aufmacher_roh = None
    latte = spitze(MIND_BREITE_GROSS)
    for i, kandidaten in enumerate(offen):
        treffer = nimm(
            1,
            mind_breite=MIND_BREITE_GROSS,
            aus=gleichrangig(kandidaten, latte),
            streng=True,
        )
        if treffer:
            aufmacher_roh = treffer[0]
            offen.pop(i)
            break
    if aufmacher_roh is None:
        aufmacher_roh = (nimm(1, mind_breite=MIND_BREITE_GROSS) or [None])[0]
    aufmacher = None
    if aufmacher_roh is not None:
        aufmacher = dict(aufmacher_roh)
        aufmacher["vorspann"] = " ".join((aufmacher_roh.get("summary") or "").split())

    zwei: list[dict] = []
    while len(zwei) < 2:
        latte = spitze(MIND_BREITE_GROSS)
        treffer = nimm(
            1,
            mind_breite=MIND_BREITE_GROSS,
            aus=gleichrangig([k[0] for k in offen], latte),
            streng=True,
        ) or nimm(1, mind_breite=MIND_BREITE_GROSS)
        if not treffer:
            break
        zwei += treffer
    for h in zwei:
        h["anriss"] = _first_sentence(h.get("summary") or "", 150)
    wichtig = nimm(
        _WICHTIG_ZEILEN,
        aus=[
            h
            for h in _ctm_achse(highlights)
            if h.get("url") not in gesperrt
            and int(h.get("ctm_bezug") or 0) >= ctm.DIREKT
        ],
    )
    vier = nimm(4, mind_breite=1, streng=True)
    wichtig += nimm(
        _WICHTIG_ZEILEN - len(wichtig),
        aus=[h for h in _ctm_achse(highlights) if h.get("url") not in gesperrt],
    )
    vier += nimm(4 - len(vier), mind_breite=1)

    return {
        "aufmacher": aufmacher,
        "zwei": zwei,
        "vier": vier,
        "wichtig": wichtig,
        "faden_oben": sum(
            1
            for kandidaten in (faden or [])
            if any(h.get("url") in benutzt for h in kandidaten)
        ),
        "oben": 1 + len(zwei) + len(vier) + len(wichtig) if aufmacher else 0,
    }


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
        lead = next((h for h in eintraege[:5] if _bildbreite(h) >= 500), eintraege[0])
        rest = [h for h in eintraege if h is not lead]
        begleiter = (
            [h for h in rest if h.get("image")]
            + [h for h in rest if not h.get("image")]
        )[:2]
        out.append(
            {
                "key": key,
                "label": _RESSORT_LABEL[key],
                "lead": lead,
                "mittel": rest[:4],
                "zeilen": rest[4:],
                "n": len(eintraege),
                "kachel": [lead] + begleiter,
            }
        )
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


_SATZENDE = re.compile(
    r"(?:(?<=[a-z\u00e4\u00f6\u00fc\u00dfA-Z\u00c4\u00d6\u00dc\)\"'\u00bb])[.!?](?=\s+[A-Z\u00c4\u00d6\u00dc\u00ab\"\u201e])"
    r"|(?<=\s)[.!?](?=\s))"
)


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
        return t[: m.end()]
    if len(t) <= limit:
        return t
    schnitt = t[:limit].rstrip()
    leer = schnitt.rfind(" ")
    if leer > limit * _KUERZEN_MIND_ANTEIL:
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
    r"(?ms)^##\s+(?:Empfehlungen|Handlungsempfehlungen)[^\n]*\n.*?(?=^##\s|\Z)"
)
_ADVICE_LINE_RE = re.compile(r"(?mi)^\s*(?:Fuer|Für)\s+Vodafone\s*:.*(?:\n|$)")


_ADVICE_PHRASES = (
    "für vodafone",
    "fuer vodafone",
    "vodafone sollte",
    "vodafone könnte",
    "vodafone koennte",
    "vodafone muss",
    "vodafone kann",
)


def _ohne_ratschlagsaetze(block: str) -> str:
    """Entfernt aus einem Absatz die SAETZE mit Vodafone-Ratschlag.

    Der Satztrenner (mit Abkuerzungsschutz) steht in textwerkzeug - er wird
    von drei Stellen gebraucht, die dieselbe Redaktionsregel durchsetzen.
    """
    behalten = [
        s for s in _saetze(block) if not any(p in s.lower() for p in _ADVICE_PHRASES)
    ]
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
        return text[: m.end()]
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
    tech: dict[str, dict] = {}
    for h in _flatten(report):
        for name in _tag_tech(f"{h.get('title', '')} {h.get('summary', '')}"):
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
    for c in report.get("competitors") or []:
        c = dict(c)
        moves = []
        for m in c.get("moves") or []:
            m = dict(m)
            if _is_suppressed_source(m):
                continue
            m["domain"] = urlsplit(m.get("url") or "").netloc.removeprefix("www.")
            m["color"] = CATEGORY_COLORS.get(
                m.get("category"), _anbieter_farben.GRAU_MITTEL
            )
            moves.append(m)
        c["moves"] = moves
        c["anker"] = _wb_anker(c.get("name") or "")
        c["satz"] = _first_sentence(c.get("summary") or "", 190)
        out.append(c)
    return out


def schreibe_statische_dateien(site_dir: Path) -> set[str]:
    """Schreibt CSS, JS, Logo, Schrift und Bilder; nennt die vorhandenen Bilder."""
    for asset in ("style.css", "app.js"):
        inhalt = (_TEMPLATES / asset).read_text(encoding="utf-8")
        if asset == "style.css":
            inhalt = _anbieter_farben.in_stylesheet(inhalt)
        (site_dir / asset).write_text(inhalt, encoding="utf-8")
    return statik.kopiere(_TEMPLATES, site_dir)


def render_site(site_dir: Path, reports_dir: Path, cfg=None) -> list[Ausfall]:
    """Rendert die ganze Website und gibt die Teile zurück, die nicht neu gebaut wurden."""
    env = _env()
    _wurzel = getattr(cfg, "root", None) or reports_dir.parent.parent
    ausfaelle: list[Ausfall] = ohne_konfiguration(_wurzel)
    env.globals["ausfaelle"] = ausfaelle
    env.globals["hausfarbe"] = _anbieter_farben.TRANSPARENZ
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "reports").mkdir(exist_ok=True)
    folien_dir = site_dir / "folien"
    folien_dir.mkdir(exist_ok=True)
    (site_dir / ".nojekyll").write_text("")
    env.globals["bilder"] = schreibe_statische_dateien(site_dir)
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
    vorhandene_bilder = {
        b.name for quelle in bild_quellen for b in quelle.iterdir() if b.is_file()
    }
    for report in reports:
        for region in (report.get("regions") or {}).values():
            for h in region.get("highlights") or []:
                if h.get("image") and h["image"] not in vorhandene_bilder:
                    for feld in ("image", "image_w", "image_h"):
                        h.pop(feld, None)
    state_dir = reports_dir.parent / "state"
    themen = themen_store.lade_themen(state_dir)
    for thema in themen:
        for item in thema.get("items") or []:
            if item.get("image") and item["image"] not in vorhandene_bilder:
                for feld in ("image", "image_w", "image_h"):
                    item.pop(feld, None)
    themen_band = [
        {"slug": t.get("slug"), "titel": t.get("title"), "n": len(t.get("items") or [])}
        for t in themen
    ]

    from ..geraete_config import lade_katalog, lade_quellen as _lade_geraetequellen
    from . import geraete_view as geraete_view_mod

    try:
        geraete = geraete_view_mod.aufbereiten(
            state_dir,
            _lade_geraetequellen(_wurzel),
            lade_katalog(_wurzel),
            heute=reports[0].get("date", "") if reports else "",
        )
    except Exception as exc:  # noqa: BLE001
        log.error("Geraetedaten nicht aufbereitbar: %s: %s", type(exc).__name__, exc)
        geraete = geraete_view_mod.leer(f"{type(exc).__name__}: {exc}")
        ausfaelle.append(Ausfall.aus_ausnahme("Gerätedaten", exc))
    ausfaelle.extend(geraete["ausfaelle"])
    env.globals["geraete_verlinkt"] = bool(geraete["bilanz"].get("schwelle_erreicht"))

    from . import geraete_radar as _geraete_radar_mod

    try:
        _portfolio = {
            "lifecycle": geraete["lifecycle"],
            "auffaellig": geraete["auffaellig"],
            "lifecycle_sichtbar": geraete["lifecycle_sichtbar"],
            "nachfolger_sichtbar": geraete["nachfolger_sichtbar"],
            "fenster_tage": geraete["fenster_tage"],
        }
        radar_view = _geraete_radar_mod.radar(
            geraete["tco"],
            geraete["vergleich"]["ohne_vertrag"],
            geraete["quellenlage"],
            alarme=geraete["alarme"],
            portfolio=_portfolio,
        )
    except Exception as exc:  # noqa: BLE001
        log.error(
            "Wettbewerbs-Radar nicht aufbereitbar: %s: %s", type(exc).__name__, exc
        )
        radar_view = _geraete_radar_mod.leer()
        ausfaelle.append(Ausfall.aus_ausnahme("Wettbewerbs-Radar", exc))
    env.globals["radar_verlinkt"] = bool(radar_view["hat_vergleichbare_zeilen"])

    rechtstexte = rechtstexte_mod.alle(_wurzel)
    env.globals["rechtstexte_verlinkt"] = {t.schluessel for t in rechtstexte}
    env.globals["newsletter_verlinkt"] = rechtstexte_mod.vollstaendig(_wurzel)

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
                prefix="",
                active=text.schluessel,
                text={
                    "titel": text.titel,
                    "luecken": text.luecken,
                    "html": _md_to_html(text.markdown),
                },
            ),
            encoding="utf-8",
        )

    archive = [
        {
            "date": r["date"],
            "date_de": _fmt_date_de(r["date"]),
            "stats": r.get("stats", {}),
            "llm": r.get("generated_with_llm", False),
        }
        for r in reports
    ]

    woche_tpl = env.get_template("woche.html.j2")
    latest_ctx: dict | None = None
    wochen: list[dict] = []
    for i, report in enumerate(reports):
        highlights = _flatten(report)
        for h in highlights:
            pfad = uebersetzung_je_url.get(h.get("url") or "")
            if pfad:
                h["uebersetzung"] = pfad
        briefing_md = _strip_vodafone_advice(
            _strip_suppressed_source_content(report.get("briefing_md", ""))
        )
        briefing_html, toc = _anchor_headings(_md_to_html(briefing_md))
        kurzpfad = ctm.kurzpfad(highlights)
        front = _titelseite(
            highlights,
            _faden(highlights, _fuehrende_saetze(briefing_md)),
            belegt=[h.get("url") for h in kurzpfad],
        )
        competitors = _prep_competitors(report)
        wochen.append(
            {
                "date": report["date"],
                "highlights": highlights,
                "ausfall": bool(report.get("redaktion_ausfall")),
                "competitors": [] if report.get("redaktion_ausfall") else competitors,
            }
        )
        public_highlights = []
        for h in highlights:
            public_h = dict(h)
            public_h.pop("why_it_matters", None)
            public_highlights.append(public_h)
        ctx = {
            "report": report,
            "date_de": _fmt_date_de(report["date"]),
            "redaktion_ausfall": _redaktion_ausfall_ctx(report),
            "highlights": highlights,
            "explorer_json": _json_for_script(public_highlights),
            "front": front,
            "competitors": competitors,
            "dash": _stats(report) if (i == 0 and highlights) else None,
            "briefing_html": briefing_html,
            "kapitel": startseite_mod.kapitel(briefing_html),
            "toc": toc,
            "lesezeit": _lesezeit(briefing_md),
            "zwei_minuten": kurzpfad,
            "regions": sorted({h["region"] for h in highlights}),
            "categories": sorted({h["category"] for h in highlights}),
            "archive": archive,
            "is_latest": i == 0,
            "num_operators": num_operators or report.get("stats", {}).get("operators"),
            "n_competitors": len(competitors),
            "themen": themen_band,
            "fruehwarnung": None,
        }
        ctx_archiv = dict(ctx, is_latest=False)
        (site_dir / "reports" / f"{report['date']}.html").write_text(
            woche_tpl.render(prefix="../", show_explorer=True, **ctx_archiv),
            encoding="utf-8",
        )
        try:
            from . import folien as folien_mod

            folien_report = report
            if report.get("redaktion_ausfall"):
                folien_report = dict(
                    report,
                    date=report["redaktion_ausfall"].get("stand", report["date"]),
                )
            (folien_dir / f"{report['date']}.html").write_text(
                folien_mod.baue(folien_report), encoding="utf-8"
            )
        except Exception as exc:  # noqa: BLE001
            log.error("Foliensatz fuer %s nicht erzeugt: %s", report["date"], exc)
            ausfaelle.append(Ausfall.aus_ausnahme(f"Foliensatz {report['date']}", exc))
        if i == 0:
            latest_ctx = ctx

    latest = reports[0] if reports else None
    diff_report = _load_latest_diff_report(reports_dir / "differenzierung")

    db = DiffDB(state_dir / "differentiation_db.json")
    store = DiffStore(state_dir / "differentiation.jsonl")
    latest_date = latest["date"] if latest else ""
    theme_label_map = dict(SWEEP_THEMES)

    diff_teile = differenzierung_bericht.zerlegen(
        (diff_report or {}).get("briefing_md", ""), theme_label_map
    )

    diff = differenzierung_view.aufbereiten(
        list(db.entries.values()),
        store.entries(),
        SWEEP_THEMES,
        latest_date,
        _DIFF_COLOR,
        diff_teile["einordnung"],
        bilder=diff_bilder.lade_index(state_dir.parent.parent),
        vorhandene_bilder=vorhandene_bilder,
    )
    (site_dir / "differenzierung.html").write_text(
        env.get_template("differenzierung.html.j2").render(
            prefix="",
            diff=diff,
            seit=seit_mod.fuer_differenzierung(diff),
            verlauf=verlauf_mod.aufbereiten(diff["bestand"], theme_label_map),
            luecken=luecken_mod.bauen(
                diff["bestand"],
                theme_label_map,
                luecken_mod.lade_eigene_hebel(_wurzel),
            ),
            date_de=_fmt_date_de(latest["date"]) if latest else "",
            diff_lage_html=_md_to_html(diff_teile["lage"])
            if diff_teile["lage"]
            else "",
            diff_muster=[
                dict(m, text_html=_md_to_html(m["text"], inline=True))
                for m in diff_teile["muster"]
            ],
            diff_report_html=_md_to_html(diff_teile["alt_md"])
            if diff_teile["alt_md"]
            else "",
            diff_report_date=_fmt_date_de(diff_report["date"]) if diff_report else "",
        ),
        encoding="utf-8",
    )

    (site_dir / "meldungen.html").write_text(
        env.get_template("meldungen.html.j2").render(
            prefix="",
            archive=archive,
            num_operators=num_operators,
            date_de=(latest_ctx or {}).get("date_de", ""),
            redaktion_ausfall=(latest_ctx or {}).get("redaktion_ausfall"),
            highlights=(latest_ctx or {}).get("highlights", []),
            ausgabe=meldungen_seite.ausgabe(latest_ctx, cfg),
            explorer_json=(latest_ctx or {}).get("explorer_json", "[]"),
            regions=(latest_ctx or {}).get("regions", []),
            categories=(latest_ctx or {}).get("categories", []),
        ),
        encoding="utf-8",
    )

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
        promo_updated = promo_db_raw.get("updated") or (
            latest["date"] if latest else ""
        )

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
        if promo_dir_images.exists():
            for veraltet in promo_dir_images.iterdir():
                if veraltet.is_file() and veraltet.name not in ausgeliefert:
                    veraltet.unlink()

        promo_view = prepare_promo_view(promo_entries, promo_cfg.sources, promo_updated)
        startseite_mod.fristen_markieren(promo_view, promo_updated)

        promo_report_dir = reports_dir / "promo"
        promo_report = None
        if promo_report_dir.exists():
            cands = [
                f for f in promo_report_dir.glob("*.md") if _DATE_RE.fullmatch(f.stem)
            ]
            if cands:
                p = max(cands, key=lambda f: f.stem)
                promo_report = {
                    "date": p.stem,
                    "briefing_md": p.read_text(encoding="utf-8"),
                }

        promo_dir = site_dir / "promo"
        promo_dir.mkdir(exist_ok=True)
        (promo_dir / "index.html").write_text(
            env.get_template("promo_index.html.j2").render(
                prefix="../",
                date_de=_fmt_date_de(promo_updated),
                promo_view=promo_view,
                seit=seit_mod.fuer_promo(promo_view),
                promo_report_html=_md_to_html(promo_report["briefing_md"])
                if promo_report
                else "",
                promo_report_date=_fmt_date_de(promo_report["date"])
                if promo_report
                else "",
                promo_lead=_promo_lead(promo_report["briefing_md"])
                if promo_report
                else "",
            ),
            encoding="utf-8",
        )
        (promo_dir / "quellen.html").write_text(
            env.get_template("promo_quellen.html.j2").render(
                prefix="../", sources=promo_cfg.sources
            ),
            encoding="utf-8",
        )

    if latest_ctx is not None:
        latest_ctx["fruehwarnung"] = fruehwarnung_mod.aufbereiten(wochen, _wurzel)
        latest_ctx["fenster"] = startseite_mod.fenster(
            latest_ctx, geraete, cfg and promo_view, cfg and promo_updated
        )
        (site_dir / "index.html").write_text(
            woche_tpl.render(prefix="", show_explorer=False, **latest_ctx),
            encoding="utf-8",
        )

    thema_dir = site_dir / "thema"
    geschrieben: set[str] = set()
    if themen:
        thema_dir.mkdir(exist_ok=True)
        thema_tpl = env.get_template("thema.html.j2")
        for thema in themen:
            view = build_thema_view(thema, promo_entries)
            for schluessel in ("aufmacher", "zwei", "rest"):
                wert = view.get(schluessel)
                for h in [wert] if isinstance(wert, dict) else (wert or []):
                    pfad = uebersetzung_je_url.get(h.get("url") or "")
                    if pfad:
                        h["uebersetzung"] = pfad
            datei = f"{view['slug']}.html"
            (thema_dir / datei).write_text(
                thema_tpl.render(prefix="../", t=view), encoding="utf-8"
            )
            geschrieben.add(datei)
    if thema_dir.exists():
        for veraltet in thema_dir.iterdir():
            if veraltet.is_file() and veraltet.name not in geschrieben:
                veraltet.unlink()

    ueb_seiten = uebersetzung_view_mod.seiten(uebersetzungen)
    if ueb_seiten:
        ueb_dir = site_dir / uebersetzung_view_mod.ORDNER
        ueb_dir.mkdir(exist_ok=True)
        ueb_tpl = env.get_template("uebersetzung.html.j2")
        for seite in ueb_seiten:
            (ueb_dir / seite["dateiname"]).write_text(
                ueb_tpl.render(
                    prefix="../",
                    u=seite["u"],
                    sprachname=seite["sprachname"],
                    sprachname_dativ=seite["sprachname_dativ"],
                ),
                encoding="utf-8",
            )
        log.info("Uebersetzungsseiten gerendert: %d", len(ueb_seiten))

    search_index = suchindex.bauen(
        wochen,
        diff["bestand"],
        theme_label_map,
        promo_aktionen=promo_entries,
        mechanik_label=PROMO_MECHANICS,
    )
    (site_dir / "search_index.json").write_text(
        json.dumps(search_index, ensure_ascii=False), encoding="utf-8"
    )

    from ..newsletter.filters import baue_stichwort_index
    from ..newsletter.config import lade_katalog as _lade_nl_katalog

    try:
        _nl_tage = _lade_nl_katalog(_wurzel).grenzen.vorschau_tage
    except (FileNotFoundError, ValueError) as exc:
        log.warning(
            "newsletter.yaml nicht lesbar (%s) - Stichwort-Index mit 30 Tagen", exc
        )
        _nl_tage = 30
    (site_dir / "data").mkdir(exist_ok=True)
    (site_dir / "data" / "keyword-index.json").write_text(
        json.dumps(
            baue_stichwort_index(reports_dir, tage=_nl_tage), ensure_ascii=False
        ),
        encoding="utf-8",
    )

    from . import newsletter_seite as nl_seite

    try:
        nl_katalog = _lade_nl_katalog(_wurzel)
    except (FileNotFoundError, ValueError) as exc:
        log.error("newsletter.yaml nicht lesbar (%s) - keine Anmeldeseite", exc)
        ausfaelle.append(Ausfall.aus_ausnahme(NEWSLETTER_TEIL, exc))
        nl_katalog = None
    if nl_katalog is not None:
        fassung = rechtstexte_mod.aktuelle_einwilligung(_wurzel)
        nl_dienst_url = (
            cfg.settings.get("newsletter_dienst_url", "") if cfg is not None else ""
        )
        (site_dir / "newsletter.html").write_text(
            env.get_template("newsletter.html.j2").render(
                prefix="",
                active="newsletter",
                dimensionen=nl_seite.dimensionen(nl_katalog),
                grenzen=nl_katalog.grenzen,
                dienst_da=bool(nl_dienst_url),
                einwilligung_absaetze=nl_seite.einwilligung_absaetze(
                    fassung.text if fassung else ""
                ),
                einwilligung_version=fassung.version if fassung else "—",
                nl_config=nl_seite.konfiguration(
                    nl_katalog,
                    dienst_url=nl_dienst_url,
                    frei=env.globals["newsletter_verlinkt"],
                ),
            ),
            encoding="utf-8",
        )
        for name, (titel, text, weiter) in nl_seite.abschlussseiten().items():
            (site_dir / f"newsletter-{name}.html").write_text(
                env.get_template("newsletter_abschluss.html.j2").render(
                    prefix="",
                    active="newsletter",
                    titel=titel,
                    text=text,
                    weiter=weiter,
                ),
                encoding="utf-8",
            )
    (site_dir / "suche.html").write_text(
        env.get_template("suche.html.j2").render(
            prefix="", top_absender=suchindex.haeufigste_absender(search_index)
        ),
        encoding="utf-8",
    )

    wettbewerb_view = build_wettbewerb_view(
        wochen,
        getattr(cfg, "focus_competitors", None) or [],
        promo_entries,
        promo_sources,
        diff_bestand=diff["bestand"],
        theme_label=theme_label_map,
    )
    wettbewerb_view["puls"] = wettbewerb_puls.aus_ansicht(wettbewerb_view, wochen)
    (site_dir / "wettbewerb.html").write_text(
        env.get_template("wettbewerb.html.j2").render(
            prefix="",
            wettbewerb=wettbewerb_view,
            seit=seit_mod.fuer_wettbewerb(wettbewerb_view, wettbewerb_view["stand"]),
            date_de=_fmt_date_de(wettbewerb_view["stand"]),
        ),
        encoding="utf-8",
    )

    from ..collect.lieferzeit import lade_warenkorb

    lieferzeit_daten: dict = {}
    lieferzeit_pfad = state_dir / "lieferzeit.json"
    if lieferzeit_pfad.exists():
        try:
            lieferzeit_daten = json.loads(lieferzeit_pfad.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.warning("lieferzeit.json unlesbar - rendere leere Seite")
    lieferzeit_view = lieferzeit_view_mod.aufbereiten(
        lieferzeit_daten,
        lade_warenkorb(_wurzel),
        heute=latest["date"] if latest else "",
    )
    (site_dir / "lieferzeit.html").write_text(
        env.get_template("lieferzeit.html.j2").render(
            prefix="", lieferzeit=lieferzeit_view
        ),
        encoding="utf-8",
    )

    from . import tarife_view as tarife_view_mod

    try:
        from ..collect.tarif_crawler import lade_quellen as _lade_tarifquellen

        tarif_quellen = _lade_tarifquellen(_wurzel)
    except Exception as exc:  # noqa: BLE001
        tarif_quellen = []
        ausfaelle.append(Ausfall.aus_ausnahme("Tarifquellen", exc))
    tarife = tarife_view_mod.aufbereiten(
        state_dir / "tarife.jsonl",
        tarif_quellen,
        heute=latest["date"] if latest else "",
    )
    (site_dir / "tarife.html").write_text(
        env.get_template("tarife.html.j2").render(prefix="", tarife=tarife),
        encoding="utf-8",
    )

    try:
        from . import geraete_export as _geraete_export

        geraete["export"] = _geraete_export.schreibe_exporte(
            site_dir,
            geraete.get("bestand") or [],
            geraete.get("alle_punkte") or [],
            geraete.get("katalog_obj"),
            stand=geraete.get("stand", ""),
            tco=(geraete.get("tco") or {}).get("export"),
            radar=radar_view,
            modelle=geraete.get("katalog_modelle"),
        )
    except Exception as exc:  # noqa: BLE001
        log.error("Geraete-Export gescheitert: %s: %s", type(exc).__name__, exc)
        from . import geraete_export as _geraete_export

        geraete["export"] = _geraete_export.leer()
        radar_view["export"] = _geraete_export.leer()["radar"]
        ausfaelle.append(Ausfall.aus_ausnahme("Geräte-Export", exc))
    else:
        radar_view["export"] = geraete["export"]["radar"]

    (site_dir / "geraete.html").write_text(
        env.get_template("geraete.html.j2").render(
            prefix="",
            geraete=geraete,
            radar=radar_view,
            teurer=geraete_teurer.listen(geraete),
        ),
        encoding="utf-8",
    )
    _tco = geraete.get("tco") or {}
    if _tco.get("modelle"):
        (site_dir / "data").mkdir(exist_ok=True)
        _zr_start = (geraete.get("zeitreihe") or {}).get("start") or {}
        _start_modell = _zr_start.get("modell") or _tco["modell_vorgabe"]
        (site_dir / "data" / "geraete-buendel.html").write_text(
            env.get_template("geraete_buendel_fragment.html.j2").render(
                modelle=_tco["modelle"], vorgabe=_start_modell
            ),
            encoding="utf-8",
        )
        _zr = geraete.get("zeitreihe") or {}
        if _zr.get("paare"):
            (site_dir / "data" / "geraete-zeitreihe.html").write_text(
                env.get_template("geraete_zeitreihe_fragment.html.j2").render(
                    paare=_zr["paare"]
                ),
                encoding="utf-8",
            )
    (site_dir / "geraete-quellen.html").write_text(
        env.get_template("geraete_quellen.html.j2").render(prefix="", geraete=geraete),
        encoding="utf-8",
    )

    run = (latest or {}).get("run") if latest else None
    if run:
        run = dict(run)
        run["sources"] = [
            s for s in run.get("sources", []) if not _is_suppressed_source(s)
        ]
        summary = dict(run.get("source_summary") or {})
        summary["total"] = len(run["sources"])
        for schluessel, status in (
            ("ok", "ok"),
            ("empty", "empty"),
            ("failed", "fail"),
        ):
            summary[schluessel] = sum(
                1 for s in run["sources"] if s.get("status") == status
            )
        summary["quarantaene"] = sum(
            1 for s in run["sources"] if s.get("status") == "quarantaene"
        )
        summary["total"] -= summary["quarantaene"]
        run["source_summary"] = summary
    by_region: dict[str, list] = {}
    tech_themes: list[dict] = []
    news_sources: list = []
    if cfg is not None:
        for op in cfg.operators:
            by_region.setdefault(op.region_name, []).append(op)
        for key, label in cfg.themes:
            quellen = [s for s in cfg.tech_sources if s.theme == key]
            if quellen:
                tech_themes.append({"key": key, "label": label, "sources": quellen})
        news_sources = cfg.news_sources

    (site_dir / "transparenz.html").write_text(
        env.get_template("transparenz.html.j2").render(
            prefix="",
            run=run,
            report=latest,
            n_bewertet=(
                latest.get("stats", {}).get("bewertete")
                if latest and latest.get("stats", {}).get("bewertete") is not None
                else (len(_flatten(latest)) if latest else 0)
            ),
            date_de=_fmt_date_de(latest["date"]) if latest else "",
            ctm_stufen=[
                {
                    "stufe": s,
                    "label": ctm.STUFEN_LABEL[s],
                    "text": ctm.STUFEN_ERKLAERUNG[s],
                }
                for s in (3, 2, 1, 0)
            ],
            sicherheitsskala=ctm.lade_fokus(_wurzel).sicherheitsskala,
            newsletter=newsletter_protokoll.aufbereiten(
                state_dir / "newsletter_stats.jsonl"
            ),
            geraete_pruefung=geraete_pruefkennzahlen.aufbereiten(state_dir),
            by_region=by_region,
            news_sources=news_sources,
            tech_themes=tech_themes,
            n_tech_sources=sum(len(t["sources"]) for t in tech_themes),
            num_operators=num_operators,
        ),
        encoding="utf-8",
    )

    if not reports:
        (site_dir / "index.html").write_text(
            woche_tpl.render(
                prefix="",
                report=None,
                date_de="",
                highlights=[],
                explorer_json="[]",
                front=_titelseite([]),
                competitors=[],
                dash=None,
                toc=[],
                lesezeit=0,
                briefing_html="",
                regions=[],
                categories=[],
                archive=[],
                is_latest=True,
                show_explorer=False,
                themen=[],
                num_operators=num_operators,
                n_competitors=0,
            ),
            encoding="utf-8",
        )

    for alt, ziel in (
        ("bericht.html", "index.html"),
        ("archive.html", "meldungen.html#archiv"),
        ("protokoll.html", "transparenz.html"),
        ("sources.html", "transparenz.html#bestand"),
        ("wettbewerber.html", "wettbewerb.html"),
        ("wettbewerbsradar.html", "geraete.html#tafel-radar"),
    ):
        (site_dir / alt).write_text(_redirect_html(ziel), encoding="utf-8")

    log.info("Site rendered: %d report(s) -> %s", len(reports), site_dir)
    for ausfall in ausfaelle:
        log.error("Nicht neu gebaut: %s (%s)", ausfall.teil, ausfall.grund)
    return ausfaelle
