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
from .differentiation import DIFF_THEMES
from .promo import prepare_promo_view
from ..analyze.diff_curator import DiffStore
from ..analyze.category_sweep import DiffDB, THEMES as SWEEP_THEMES
from ..promo_config import load_promo_config
from ..promo_images import image_path as promo_image_path

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
    return env


_MD_TAGS = {"a", "blockquote", "br", "code", "em", "h2", "h3", "h4",
            "li", "ol", "p", "pre", "strong", "ul"}
_MD_DANGEROUS_TAGS = {"base", "embed", "form", "iframe", "math", "object",
                      "script", "style", "svg"}


def _md_to_html(text: str) -> str:
    """Render the editor's Markdown while stripping raw HTML and unsafe URLs."""
    rendered = md.markdown(text or "", extensions=["extra", "sane_lists"])
    soup = BeautifulSoup(rendered, "html.parser")
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


_SLUG_MAP = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
                           "Ä": "ae", "Ö": "oe", "Ü": "ue"})


def _slug(text: str) -> str:
    """Stabiler Anker aus einer Ueberschrift ("Afrika & Naher Osten" ->
    "afrika-naher-osten"). Muss ueber Laeufe hinweg gleich bleiben - die
    Anker landen in Mails."""
    s = (text or "").strip().lower().translate(_SLUG_MAP)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "abschnitt"


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
        "<title>Weitergeleitet – Vodafone Insights</title>\n</head>\n"
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
            h["de_title"] = _first_sentence(h.get("summary") or "", 150) or h.get("title") or ""
            out.append(h)
    out.sort(key=lambda h: (h["relevance"], h.get("date") or ""), reverse=True)
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


def _schlagzeile(h: dict, max_zeichen: int = 110) -> str:
    """Die Schlagzeile einer Meldung.

    Erste Wahl ist `headline` - eine echte, vom Analysten geschriebene
    Schlagzeile (max. neun Woerter, Aktiv). Die gibt es erst fuer Berichte ab
    dem 06.08.2026; aeltere Berichte haben sie nicht.

    Fallback ist der volle Zusammenfassungssatz. **Nicht mechanisch gekuerzt**:
    ein erster Versuch, an Komma oder Semikolon zu trennen, machte aus
    "SpaceX-Praesidentin Gwynne Shotwell sagt, Starlink Mobile werde direkt
    mit AT&T konkurrieren" die Schlagzeile "SpaceX-Praesidentin Gwynne
    Shotwell sagt" - grammatisch sauber und inhaltsleer. Eine Schlagzeile
    laesst sich nicht aus einem Fliesstextsatz schneiden; wer es doch tut,
    produziert Zeilen, die nichts mehr sagen. Lieber drei Zeilen, die stimmen.
    """
    kopf = " ".join((h.get("headline") or "").split()).strip(" .")
    if kopf:
        return kopf
    satz = " ".join((h.get("de_title") or "").split())
    if len(satz) <= max_zeichen:
        return satz.rstrip(" .")
    schnitt = satz[:max_zeichen].rstrip()
    leer = schnitt.rfind(" ")
    if leer > max_zeichen * 0.5:
        schnitt = schnitt[:leer]
    return schnitt.rstrip(" ,;:–-") + "…"


def _text_aus_html(html: str) -> str:
    """Reintext aus gerendertem HTML - inklusive Aufloesung der Entitaeten.

    Wichtig: die Vorspaenne (_briefing_lead/_promo_lead) ziehen Text aus
    bereits gerendertem HTML. Wer dort nur die Tags per Regex entfernt,
    behaelt "&amp;" als Zeichenfolge - und Jinja escaped die beim Einsetzen
    ein zweites Mal. Auf der Titelseite stand deshalb "mit AT&amp;T".
    """
    return " ".join(BeautifulSoup(html or "", "html.parser").get_text(" ").split())


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
    for sep in (". ", "! ", "? "):
        k = t.find(sep)
        if 0 < k < limit:
            return t[:k + 1]
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
# Abkuerzungen, deren Punkt kein Satzende ist. Ohne diesen Schutz zerlegt der
# Satztrenner "z. B. Vodafone kann ..." in zwei Teile und wirft den halben
# Satz weg.
_ABK = ("z. B.", "d. h.", "u. a.", "u. Ä.", "bzw.", "ca.", "ggf.", "inkl.",
        "Mio.", "Mrd.", "Nr.", "Abb.", "evtl.", "sog.", "Prof.", "Dr.")
_SATZ_GRENZE = re.compile(r"(?<=[.!?])\s+(?=[«\"„*\[(A-ZÄÖÜ])")


def _ohne_ratschlagsaetze(block: str) -> str:
    """Entfernt aus einem Absatz die SAETZE mit Vodafone-Ratschlag."""
    geschuetzt = block
    for i, abk in enumerate(_ABK):
        geschuetzt = geschuetzt.replace(abk, f"\x00{i}\x00")
    saetze = _SATZ_GRENZE.split(geschuetzt)
    behalten = [s for s in saetze
                if not any(p in s.lower() for p in _ADVICE_PHRASES)]
    text = " ".join(behalten)
    for i, abk in enumerate(_ABK):
        text = text.replace(f"\x00{i}\x00", abk)
    return text.strip()


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


def _briefing_lead(md_text: str) -> str:
    """Kurzer, plakativer Vorspann fuer die Uebersicht (Klartext, gekuerzt)."""
    secs = _briefing_sections(md_text)
    pick = None
    for sec in secs:
        if "wichtig" in (sec.get("title") or "").lower():
            pick = sec
            break
    if pick is None:
        pick = secs[1] if len(secs) > 1 else (secs[0] if secs else None)
    if not pick:
        return ""
    return _first_sentence(_text_aus_html(pick["html"]), 360)


def _promo_lead(md_text: str) -> str:
    """Kurzer Vorspann aus dem Promo-Wochenbericht fuer die rote Stat-Karte
    ("Was diese Woche auffaellt") auf der Promo-Uebersicht. Der Bericht
    beginnt bereits mit einem gleichnamigen Abschnitt, es wird also nur
    dessen erster Teil fuer die Karte gekuerzt - keine separate Zusammen-
    fassung wird erfunden."""
    secs = _briefing_sections(md_text)
    if not secs:
        return ""
    return _first_sentence(_text_aus_html(secs[0]["html"]), 280)


def _stats(report):
    """Kennzahlen der aktuellen Woche fuer den Kopf der Wochenseite.

    Beim Redesign am 06.08.2026 auf das reduziert, was wirklich gerendert
    wird. Entfernt, weil seit Monaten berechnet und in KEINER Vorlage
    referenziert: sov (Share of Voice), pricing, deals, risks/chances und
    n_competitors. Ebenso die Parameter prev_report/trend_reports - sie
    dienten nur der Delta-Rechnung von sov.
    """
    highlights = _flatten(report)

    # --- Themenradar (Schlagwortthemen ueber Titel und Zusammenfassung) ---
    tech: dict[str, dict] = {}
    for h in highlights:
        for name in _tag_tech(f"{h.get('title','')} {h.get('summary','')}"):
            t = tech.setdefault(name, {"theme": name, "n": 0, "ops": {}, "ex": None})
            t["n"] += 1
            op = (h.get("operator") or "").strip()
            if op:
                t["ops"][op] = t["ops"].get(op, 0) + 1
            if t["ex"] is None or (h.get("relevance") or 0) >= 4:
                t["ex"] = {"title": h.get("title"), "url": h.get("url")}
    tech_radar = sorted(tech.values(), key=lambda x: -x["n"])
    tmax = max((t["n"] for t in tech_radar), default=1) or 1
    for t in tech_radar:
        t["w"] = round(100 * t["n"] / tmax)
        t["ops_top"] = ", ".join(k for k, _ in sorted(t["ops"].items(),
                                                      key=lambda kv: -kv[1])[:2])

    profile = [{"name": c.get("name"), "n": int(c.get("n_items") or 0)}
               for c in (report.get("competitors") or [])]
    top_comp = max(profile, key=lambda c: c["n"], default=None)

    lead = next((h for h in highlights if (h.get("relevance") or 0) >= 4), None)
    if lead:
        lead = {
            "title": lead.get("title"), "url": lead.get("url"),
            "de_title": _first_sentence(lead.get("summary") or "", 150) or lead.get("title"),
            "op": lead.get("operator") or lead.get("source_label"),
            "region": lead.get("region"), "category": lead.get("category"),
            "rel": lead.get("relevance") or 0,
        }
    kpis = [
        {"num": (report.get("stats") or {}).get("new", len(highlights)),
         "label": "neue Meldungen gelesen"},
        {"num": len(highlights), "label": "davon relevant", "tint": True},
        {"num": sum(1 for h in highlights if h.get("relevance") == 5),
         "label": "sofort ansehen (5/5)", "accent": True},
        {"num": (tech_radar[0]["theme"] if tech_radar else "-"),
         "label": "Top-Technologiethema", "text": True},
    ]
    if top_comp and top_comp["n"]:
        kpis.insert(3, {"num": top_comp["name"], "label": "aktivster Wettbewerber",
                        "text": True})
    return {"kpis": kpis, "lead_signal": lead, "tech_radar": tech_radar}


def _prep_competitors(report: dict) -> list[dict]:
    """Enrich competitor profiles for rendering (domains, category colours)."""
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
        out.append(c)
    return out


# ------------------------------------------------------------- search index
def _search_entry_bericht(h: dict, report_date: str) -> dict:
    """Ein Bericht-Highlight fuer den siteweiten Suchindex (search_index.json)."""
    return {
        "kind": "bericht",
        "title": h.get("de_title") or h.get("title") or "",
        "summary": h.get("summary") or "",
        "operator": h.get("operator") or h.get("source_label") or "",
        "region": h.get("region") or "",
        "category": h.get("category") or "",
        "date": report_date,
        "source_label": h.get("source_label") or h.get("source") or "",
        "url": h.get("url") or "",
        "deep_link": f"reports/{report_date}.html",
    }


def _search_entry_diff(e: dict, theme_label: str) -> dict:
    """Ein Differenzierungs-Eintrag (data/state/differentiation_db.json) fuer
    den siteweiten Suchindex."""
    theme_key = e.get("theme") or ""
    return {
        "kind": "differenzierung",
        "title": e.get("what") or "",
        "summary": e.get("why") or "",
        "operator": e.get("operator") or "",
        "region": e.get("region") or "",
        "category": theme_label or theme_key,
        "date": e.get("first_seen") or e.get("last_verified") or "",
        "source_label": e.get("source") or "",
        "url": e.get("url") or "",
        "deep_link": f"differenzierung.html#dz-theme-{theme_key}",
    }


def _build_search_index(reports: list[dict], diff_entries: list[dict],
                         theme_label_map: dict[str, str]) -> list[dict]:
    """Aggregiert Bericht-Highlights ALLER Wochen (nicht nur der aktuellen) plus
    die persistente Differenzierungs-Bibliothek zu einem einzigen, siteweiten
    Suchindex.

    v1 macht bewusst nur Substring-Matching (in app.js) auf diesen Feldern -
    keine Tokenisierung/kein Scoring hier. Beide Quellen muessen zusammen rein:
    ein Themenbegriff wie "Perplexity" taucht fast ausschliesslich in der
    Differenzierungs-Bibliothek auf, nicht in den woechentlichen
    Bericht-Highlights derselben Woche - eine Suche, die nur den aktuellen
    Bericht abdeckt, wuerde beim ersten Ernstfall leer laufen (siehe
    claude/suche-marktrecherche-konzept.md, Pre-Mortem Punkt 2)."""
    out: list[dict] = []
    for report in reports:
        for h in _flatten(report):
            public_h = dict(h)
            public_h.pop("why_it_matters", None)
            out.append(_search_entry_bericht(public_h, report["date"]))
    for e in diff_entries:
        theme_key = e.get("theme") or ""
        out.append(_search_entry_diff(e, theme_label_map.get(theme_key, theme_key)))
    return out


# ------------------------------------------------------------------- render
def render_site(site_dir: Path, reports_dir: Path, cfg=None) -> None:
    env = _env()
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "reports").mkdir(exist_ok=True)
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
    bild_quelle = report_bilder.bildordner(reports_dir.parent.parent)
    if bild_quelle.exists():
        bild_ziel = site_dir / "images"
        bild_ziel.mkdir(exist_ok=True)
        for bild in bild_quelle.iterdir():
            if bild.is_file():
                shutil.copyfile(bild, bild_ziel / bild.name)

    num_operators = len(cfg.operators) if cfg is not None else None
    reports = _load_reports(reports_dir)
    # Die Datumszeile des Zeitungskopfs steht auf JEDER Seite und haengt an
    # der Ausgabe, nicht an der einzelnen Vorlage - deshalb als Global statt
    # als Kontextvariable, die man an sechs Aufrufstellen vergessen kann.
    env.globals["ausgabe_datum"] = _fmt_date_de(reports[0]["date"]) if reports else ""
    env.globals["ausgabe_quellen"] = (
        (reports[0].get("stats") or {}).get("sources_total") if reports else None)
    archive = [{"date": r["date"], "date_de": _fmt_date_de(r["date"]),
                "stats": r.get("stats", {}),
                "llm": r.get("generated_with_llm", False)} for r in reports]

    # Eine Vorlage fuer die aktuelle Woche UND jede Archivwoche. Bis zum
    # 06.08.2026 waren es zwei (uebersicht.html.j2 + report.html.j2), die
    # dieselbe Berichtsdatei aus zwei Blickwinkeln zeigten und sich
    # gegenseitig verlinkten - zwei Ladevorgaenge fuer eine Frage.
    woche_tpl = env.get_template("woche.html.j2")
    latest_ctx: dict | None = None
    for i, report in enumerate(reports):
        highlights = _flatten(report)
        spitze = [h for h in highlights if h["relevance"] >= 4]
        # Der Aufmacher ist die dringendste Meldung MIT Bild - so fuehrt in
        # jeder Zeitung die Bildgeschichte. Am 05.08.2026 haben die beiden
        # dringendsten kein Bild (Mobile World Live und Telecoms.com weisen
        # den Abruf mit 403 ab), die dritte schon.
        aufmacher_roh = next((h for h in spitze if h.get("image")),
                             spitze[0] if spitze else None)
        # Ueber die URL ausschliessen, nicht ueber Objektidentitaet: der
        # Aufmacher wird unten kopiert, und nach dem Kopieren traf `is not`
        # nicht mehr zu - die Aufmachermeldung stand dadurch ein zweites Mal
        # als erster Anreisser darunter, mit demselben Bild.
        aufmacher_url = (aufmacher_roh or {}).get("url")
        rest = [h for h in spitze if h.get("url") != aufmacher_url]
        aufmacher = None
        if aufmacher_roh is not None:
            aufmacher = dict(aufmacher_roh)
            aufmacher["schlagzeile"] = _schlagzeile(aufmacher_roh)
            # Der Vorspann ist die Zusammenfassung DIESER Meldung, nicht die
            # der Woche: briefing_lead ist derselbe Text, mit dem der Bericht
            # darunter woertlich beginnt - das las sich wie ein Fehler.
            aufmacher["vorspann"] = _first_sentence(
                aufmacher_roh.get("summary") or "", 260)
        # Zweite Reihe: drei Anreisser, bevorzugt bebildert.
        zweite_reihe = [dict(h, schlagzeile=_schlagzeile(h, 96))
                        for h in ([h for h in rest if h.get("image")]
                                  + [h for h in rest if not h.get("image")])[:3]]
        top = spitze[:6]
        competitors = _prep_competitors(report)
        public_highlights = []
        for h in highlights:
            public_h = dict(h)
            public_h.pop("why_it_matters", None)
            public_highlights.append(public_h)
        briefing_md = _strip_vodafone_advice(
            _strip_suppressed_source_content(report.get("briefing_md", "")))
        briefing_html, toc = _anchor_headings(_md_to_html(briefing_md))
        ctx = {
            "report": report, "date_de": _fmt_date_de(report["date"]),
            "highlights": highlights,
            "explorer_json": _json_for_script(public_highlights),
            "top_priorities": top,
            "aufmacher": aufmacher,
            "zweite_reihe": zweite_reihe,
            # Was nach Aufmacher und zweiter Reihe uebrig bleibt - sonst
            # stuende dieselbe Meldung dreimal auf der Titelseite.
            "weitere_signale": [h for h in rest if h.get("url") not in
                                {z.get("url") for z in zweite_reihe}][:6],
            "competitors": competitors,
            # _stats() ist teuer und wird nur von der aktuellen Woche
            # gebraucht. Bis zum 06.08.2026 lief es fuer JEDE Archivwoche mit
            # und das Ergebnis wurde verworfen.
            "dash": _stats(report) if (i == 0 and highlights) else None,
            "briefing_html": briefing_html,
            "toc": toc,
            "lesezeit": _lesezeit(briefing_md),
            "briefing_lead": _briefing_lead(briefing_md),
            "regions": sorted({h["region"] for h in highlights}),
            "categories": sorted({h["category"] for h in highlights}),
            "archive": archive, "is_latest": i == 0,
            "num_operators": num_operators or report.get("stats", {}).get("operators"),
            "n_competitors": len(competitors),
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
        if i == 0:
            latest_ctx = ctx
            (site_dir / "index.html").write_text(
                woche_tpl.render(prefix="", show_explorer=False, **ctx),
                encoding="utf-8")

    latest = reports[0] if reports else None
    diff_report = _load_latest_diff_report(reports_dir / "differenzierung")

    # ---- Differenzierung (persistente, kuratierte Bibliothek)
    # Primaerquelle: der git-versionierte Kurator-Speicher (data/state/
    # differentiation.jsonl) - so bleiben relevante Moves ueber Wochen erhalten,
    # unabhaengig davon, wie lange die Wochen-Report-JSONs aufgehoben werden.
    # Fallback (Bootstrap / erste Runde): Aggregation aller Report-Highlights.
    # ---- Differenzierung: aus der dynamischen, quellenbelegten DB
    # (data/state/differentiation_db.json), gepflegt vom Kategorie-Sweep.
    state_dir = reports_dir.parent / "state"
    from datetime import date, datetime, timedelta
    db = DiffDB(state_dir / "differentiation_db.json")
    by_theme = db.by_theme()
    latest_date = latest["date"] if latest else date.today().isoformat()
    try:
        cutoff = (datetime.fromisoformat(latest_date) - timedelta(days=10)).date().isoformat()
    except ValueError:
        cutoff = ""
    diff_themes = []
    for key, label in SWEEP_THEMES:
        entries = by_theme.get(key, [])
        for e in entries:
            e["neu"] = bool((e.get("first_seen") or "") > cutoff)
            e["verified_de"] = _fmt_date_de(e.get("last_verified") or "")
        diff_themes.append({"key": key, "label": label,
                            "color": _DIFF_COLOR.get(key, "#e60000"),
                            "entries": entries, "n": len(entries)})
    diff_stats = {
        "total": len(db), "updated_de": _fmt_date_de(db.updated or latest_date),
        "themes_active": sum(1 for t in diff_themes if t["n"]),
        "themes_total": len(diff_themes),
        "new": sum(1 for t in diff_themes for e in t["entries"] if e["neu"]),
    }
    (site_dir / "differenzierung.html").write_text(
        env.get_template("differenzierung.html.j2").render(
            prefix="", diff_themes=diff_themes, diff_stats=diff_stats,
            date_de=_fmt_date_de(latest["date"]) if latest else "",
            diff_report=diff_report,
            diff_report_html=_md_to_html(diff_report["briefing_md"])
            if diff_report else "",
            diff_report_date=_fmt_date_de(diff_report["date"])
            if diff_report else "",
            num_operators=num_operators),
        encoding="utf-8")

    # ---- Suchindex (siteweit): Bericht-Highlights aller Wochen + persistente
    # Differenzierungs-Bibliothek in einem Index, den app.js im Browser
    # durchsucht (reines Filtern eines JSON-Arrays, kein Suchserver noetig -
    # siehe claude/suche-marktrecherche-konzept.md).
    theme_label_map = dict(SWEEP_THEMES)
    search_index = _build_search_index(reports, list(db.entries.values()), theme_label_map)
    (site_dir / "search_index.json").write_text(
        json.dumps(search_index, ensure_ascii=False), encoding="utf-8")

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
            explorer_json=(latest_ctx or {}).get("explorer_json", "[]"),
            regions=(latest_ctx or {}).get("regions", []),
            categories=(latest_ctx or {}).get("categories", [])),
        encoding="utf-8")

    # ---- Promo Uebersicht: eigener zweiter Anwendungsfall neben Marktrecherche
    # (siehe promo_pipeline.py). Eigene Quellen (config/promo_sources.yaml),
    # eigener State (data/state/promo_db.json) - komplett getrennt vom
    # Presse-Collect oben. Fehlt der State (z. B. render_site() ohne
    # vorherigen Promo-Lauf), wird einfach eine leere Uebersicht gerendert.
    if cfg is not None:
        promo_cfg = load_promo_config(cfg.root)
        promo_db_raw: dict = {}
        promo_db_path = state_dir / "promo_db.json"
        if promo_db_path.exists():
            try:
                promo_db_raw = json.loads(promo_db_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                log.warning("promo_db.json unlesbar - rendere leere Promo-Uebersicht")
        promo_entries = promo_db_raw.get("entries") or []
        promo_updated = promo_db_raw.get("updated") or (latest["date"] if latest else "")

        # Hero screenshots (data/state/promo_images/<slug>.jpg, written by
        # promo_pipeline.py) are pipeline STATE, not site output, so they are
        # copied into site/promo/images/ on every render, same as any other
        # generated site asset - never edit/add files under site/ by hand.
        promo_dir_images = site_dir / "promo" / "images"
        promo_image_map: dict[str, str] = {}
        for src in promo_cfg.sources:
            cached = promo_image_path(cfg.root, src.name)
            if not cached.exists():
                continue
            promo_dir_images.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(cached, promo_dir_images / cached.name)
            promo_image_map[src.name] = f"images/{cached.name}"

        promo_view = prepare_promo_view(promo_entries, promo_cfg.sources,
                                        promo_updated, images=promo_image_map)

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
            by_region=by_region, news_sources=news_sources,
            tech_themes=tech_themes,
            n_tech_sources=sum(len(t["sources"]) for t in tech_themes),
            num_operators=num_operators),
        encoding="utf-8")

    if not reports:
        (site_dir / "index.html").write_text(
            woche_tpl.render(prefix="", report=None, date_de="", highlights=[],
                             explorer_json="[]", top_priorities=[],
                             competitors=[], dash=None, toc=[], lesezeit=0,
                             briefing_lead="", briefing_html="", regions=[],
                             categories=[], archive=[], is_latest=True,
                             show_explorer=False,
                             num_operators=num_operators, n_competitors=0),
            encoding="utf-8")

    # ---- Weiterleitungen von den alten Dateinamen. Sie stehen in Lesezeichen
    # und in Mails an die Fachabteilung; ein 404 waere die teuerste Art, eine
    # Navigation aufzuraeumen.
    for alt, ziel in (("bericht.html", "index.html"),
                      ("suche.html", "meldungen.html"),
                      ("archive.html", "meldungen.html#archiv"),
                      ("protokoll.html", "transparenz.html"),
                      ("sources.html", "transparenz.html#bestand"),
                      ("wettbewerber.html", "index.html#deutschland-fokus")):
        (site_dir / alt).write_text(_redirect_html(ziel), encoding="utf-8")

    log.info("Site rendered: %d report(s) -> %s", len(reports), site_dir)
