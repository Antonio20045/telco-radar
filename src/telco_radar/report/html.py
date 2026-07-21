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

from .differentiation import build_differentiation

log = logging.getLogger(__name__)

_TEMPLATES = Path(__file__).parent / "templates"
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

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
    env = Environment(loader=FileSystemLoader(_TEMPLATES),
                      autoescape=select_autoescape(["html"]))
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


def _json_for_script(value: object) -> str:
    """Serialize public source text safely inside an application/json script."""
    return (json.dumps(value, ensure_ascii=False)
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026")
            .replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029"))


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


def _flatten(report: dict) -> list[dict]:
    out = []
    for region_name, region in (report.get("regions") or {}).items():
        for h in region.get("highlights") or []:
            h = dict(h)
            h["region"] = region_name
            h["relevance"] = h.get("relevance") or 0
            h["relevance_label"] = RELEVANCE_LABELS.get(h["relevance"], "")
            h["category"] = h.get("category") or "Sonstiges"
            dom = urlsplit(h.get("url") or "").netloc.removeprefix("www.")
            h["source_domain"] = dom
            h["source_label"] = h.get("source") or dom
            out.append(h)
    out.sort(key=lambda h: (h["relevance"], h.get("date") or ""), reverse=True)
    for i, h in enumerate(out):
        h["id"] = i
    return out


# --------------------------------------------------------------- SVG charts
def _bar_chart_svg(rows, width=520, row_h=40, label_w=180) -> str:
    if not rows:
        return ""
    maxv = max(v for _, v, _ in rows) or 1
    value_w, pad = 40, 8
    bar_max = width - label_w - value_w - pad * 2
    height = row_h * len(rows)
    parts = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
             f'role="img" class="chart" preserveAspectRatio="xMinYMin meet">']
    for i, (label, value, color) in enumerate(rows):
        y = i * row_h
        bw = max(4, round(bar_max * value / maxv))
        lbl = html_lib.escape(label[:28])
        parts.append(
            f'<text x="{label_w - pad}" y="{y + row_h / 2 + 4}" text-anchor="end" '
            f'class="c-label">{lbl}</text>'
            f'<rect x="{label_w}" y="{y + 8}" width="{bar_max}" height="{row_h - 18}" '
            f'rx="4" class="c-track"/>'
            f'<rect x="{label_w}" y="{y + 8}" width="{bw}" height="{row_h - 18}" '
            f'rx="4" fill="{color}"/>'
            f'<text x="{label_w + bw + 8}" y="{y + row_h / 2 + 4}" class="c-value">'
            f'{value}</text>')
    parts.append("</svg>")
    return "".join(parts)


REL_COLORS = {5: "#e60000", 4: "#e07a00", 3: "#3860be", 2: "#9aa0aa"}


def _delta(cur, prev):
    d = int(cur or 0) - int(prev or 0)
    return {"diff": d, "abs": abs(d),
            "dir": "up" if d > 0 else ("down" if d < 0 else "flat")}


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
_PRICE_RE = re.compile(
    r"(\d+\s?(gb|tb)\b)|([\u20ac$\u00a3]\s?\d)|(\d+[.,]?\d*\s?(euro|eur|dollar))"
    r"|\b(unlimited|allnet|flatrate|flat\b|prepaid|tarif|tariff|pricing|price cut"
    r"|preissenkung|g\u00fcnstig|per month|/month|im monat)\b", re.I)
_DEAL_RE = re.compile(
    r"\b(partners? with|teams up|collaborat|acquir|acquisition|merger|merge[sd]?"
    r"|joint venture|\bjv\b|stake|kooperation|\u00fcbernahme|to buy|invest|alliance"
    r"|allianz|partnership)\b", re.I)
_RISK_KW = ["druck", "risiko", "kontern", "verteidig", "angriff", "bedroh", "nachteil",
            "verlieren", "abwander", "aufholen", "hinterher", "nachziehen", "reagieren",
            "gefahr", "verdr\u00e4ng", "marktanteil verlier", "unter zugzwang"]
_CHANCE_KW = ["chance", "potenzial", "potential", "nutzen", "adaptier", "adoptier",
              "lernen", "vorbild", "m\u00f6glichkeit", "opportun", "vorreiter",
              "vorsprung", "differenzier", "erschlie\u00df", "wachstum"]


def _tag_tech(text):
    t = " " + (text or "").lower() + " "
    return [name for name, kws in TECH_THEMES if any(k in t for k in kws)]


def _classify_angle(why):
    w = (why or "").lower()
    r = sum(w.count(k) for k in _RISK_KW)
    c = sum(w.count(k) for k in _CHANCE_KW)
    if r == 0 and c == 0:
        return "neutral"
    return "risk" if r >= c else "chance"


def _first_sentence(text, limit=170):
    t = " ".join((text or "").split())
    if not t:
        return ""
    for sep in (". ", "! ", "? "):
        k = t.find(sep)
        if 0 < k < limit:
            return t[:k + 1]
    return (t[:limit].rstrip() + "\u2026") if len(t) > limit else t


def _op_counts(report):
    c = {}
    for h in _flatten(report):
        op = (h.get("operator") or "").strip()
        if op:
            c[op] = c.get(op, 0) + 1
    return c


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


def _stats(report, prev_report, trend_reports):
    highlights = _flatten(report)
    total = len(highlights) or 1
    cur_ops = _op_counts(report)
    prev_ops = _op_counts(prev_report) if prev_report else {}

    sov = [{"op": k, "n": v, "pct": round(100 * v / total),
            "delta": _delta(v, prev_ops.get(k, 0))}
           for k, v in sorted(cur_ops.items(), key=lambda kv: -kv[1])[:6]]
    sov_max = max((s["n"] for s in sov), default=1) or 1
    for s in sov:
        s["w"] = round(100 * s["n"] / sov_max)

    # --- Tech radar (keyword themes over the news text) ---
    tech = {}
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
        t["ops_top"] = ", ".join(k for k, _ in sorted(t["ops"].items(), key=lambda kv: -kv[1])[:2])

    # --- Pricing radar ---
    pricing = [{"op": h.get("operator") or h.get("source_label"), "title": h.get("title"),
                "url": h.get("url"), "region": h.get("region")}
               for h in highlights
               if h.get("category") == "Tarif/Pricing"
               or _PRICE_RE.search(f"{h.get('title','')} {h.get('summary','')}")][:6]

    # --- Deals & partnerships ---
    deals = [{"op": h.get("operator") or h.get("source_label"), "title": h.get("title"),
              "url": h.get("url"), "region": h.get("region"), "cat": h.get("category")}
             for h in highlights
             if h.get("category") in ("Partnerschaft", "M&A")
             or _DEAL_RE.search(h.get("title", ""))][:6]

    # --- Chances vs risks for Vodafone ---
    risks, chances = [], []
    for h in highlights:
        if (h.get("relevance") or 0) < 3 or not h.get("why_it_matters"):
            continue
        rec = {"title": h.get("title"), "op": h.get("operator") or h.get("source_label"),
               "url": h.get("url"), "why": h.get("why_it_matters"),
               "cat": h.get("category"), "region": h.get("region"),
               "rel": h.get("relevance") or 0}
        angle = _classify_angle(h.get("why_it_matters"))
        if angle == "risk":
            risks.append(rec)
        elif angle == "chance":
            chances.append(rec)
    risks.sort(key=lambda r: -r["rel"])
    chances.sort(key=lambda r: -r["rel"])
    risks, chances = risks[:5], chances[:5]

    # --- Competitor move-type matrix ---
    move_matrix = []
    for c in (report.get("competitors") or []):
        cats = {}
        for m in (c.get("moves") or []):
            cat = m.get("category") or "Sonstiges"
            cats[cat] = cats.get(cat, 0) + 1
        move_matrix.append({
            "name": c.get("name"), "n": int(c.get("n_items") or 0),
            "impl": _first_sentence(c.get("vodafone_implication")),
            "cats": sorted(cats.items(), key=lambda kv: -kv[1])[:4]})

    top_comp = max(move_matrix, key=lambda c: c["n"], default=None)
    lead = next((h for h in highlights if (h.get("relevance") or 0) >= 4), None)
    if lead:
        lead = {
            "title": lead.get("title"), "url": lead.get("url"),
            "why": _first_sentence(lead.get("why_it_matters"), limit=250),
            "op": lead.get("operator") or lead.get("source_label"),
            "region": lead.get("region"), "category": lead.get("category"),
            "rel": lead.get("relevance") or 0,
        }
    kpis = [
        {"num": (report.get("stats") or {}).get("new", len(highlights)),
         "label": "neue Meldungen"},
        {"num": sum(1 for h in highlights if h.get("relevance") == 5),
         "label": "sofort relevant (5/5)", "accent": True},
        {"num": (top_comp["name"] if top_comp and top_comp["n"] else "-"),
         "label": "aktivster Wettbewerber", "text": True},
        {"num": (tech_radar[0]["theme"] if tech_radar else "-"),
         "label": "Top-Technologiethema", "text": True},
    ]
    return {"kpis": kpis, "lead_signal": lead, "sov": sov, "tech_radar": tech_radar, "pricing": pricing,
            "deals": deals, "risks": risks, "chances": chances,
            "move_matrix": move_matrix, "n_competitors": len(cur_ops),
            "diff": build_differentiation(highlights)}


def _prep_competitors(report: dict) -> list[dict]:
    """Enrich competitor profiles for rendering (domains, category colours)."""
    out = []
    for c in (report.get("competitors") or []):
        c = dict(c)
        moves = []
        for m in (c.get("moves") or []):
            m = dict(m)
            m["domain"] = urlsplit(m.get("url") or "").netloc.removeprefix("www.")
            m["color"] = CATEGORY_COLORS.get(m.get("category"), "#7e7e7e")
            moves.append(m)
        c["moves"] = moves
        out.append(c)
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

    num_operators = len(cfg.operators) if cfg is not None else None
    reports = _load_reports(reports_dir)
    archive = [{"date": r["date"], "date_de": _fmt_date_de(r["date"]),
                "stats": r.get("stats", {}),
                "llm": r.get("generated_with_llm", False)} for r in reports]

    report_tpl = env.get_template("report.html.j2")
    for i, report in enumerate(reports):
        highlights = _flatten(report)
        top = [h for h in highlights if h["relevance"] >= 4][:6]
        competitors = _prep_competitors(report)
        ctx = {
            "report": report, "date_de": _fmt_date_de(report["date"]),
            "highlights": highlights,
            "explorer_json": _json_for_script(highlights),
            "top_priorities": top,
            "dash": _stats(report, reports[i + 1] if i + 1 < len(reports) else None,
                           reports[i:i + 8]) if highlights else None,
            "briefing_sections": _briefing_sections(report.get("briefing_md", "")),
            "briefing_html": _md_to_html(report.get("briefing_md", "")),
            "regions": sorted({h["region"] for h in highlights}),
            "categories": sorted({h["category"] for h in highlights}),
            "archive": archive, "is_latest": i == 0,
            "num_operators": num_operators or report.get("stats", {}).get("operators"),
            "n_competitors": len(competitors),
        }
        (site_dir / "reports" / f"{report['date']}.html").write_text(
            report_tpl.render(prefix="../", **ctx), encoding="utf-8")
        if i == 0:
            (site_dir / "index.html").write_text(
                report_tpl.render(prefix="", **ctx), encoding="utf-8")

    latest = reports[0] if reports else None

    # ---- Wettbewerber (competitor deep-dive) for the latest run
    (site_dir / "wettbewerber.html").write_text(
        env.get_template("wettbewerber.html.j2").render(
            prefix="", competitors=_prep_competitors(latest or {}),
            date_de=_fmt_date_de(latest["date"]) if latest else "",
            num_operators=num_operators),
        encoding="utf-8")

    # ---- Differenzierung (rolling multi-week differentiation lens)
    _diff_all = [h for rep in reports for h in _flatten(rep)]
    (site_dir / "differenzierung.html").write_text(
        env.get_template("differenzierung.html.j2").render(
            prefix="", diff=build_differentiation(_diff_all),
            date_de=_fmt_date_de(latest["date"]) if latest else "",
            num_operators=num_operators),
        encoding="utf-8")

    # ---- Protokoll
    run = (latest or {}).get("run") if latest else None
    (site_dir / "protokoll.html").write_text(
        env.get_template("protokoll.html.j2").render(
            prefix="", run=run, report=latest,
            date_de=_fmt_date_de(latest["date"]) if latest else "",
            num_operators=num_operators),
        encoding="utf-8")

    if not reports:
        (site_dir / "index.html").write_text(
            report_tpl.render(prefix="", report=None, date_de="", highlights=[],
                              explorer_json="[]", top_priorities=[], charts=None,
                              briefing_html="", regions=[], categories=[],
                              archive=[], is_latest=True,
                              num_operators=num_operators, n_competitors=0),
            encoding="utf-8")

    (site_dir / "archive.html").write_text(
        env.get_template("archive.html.j2").render(
            prefix="", archive=archive, num_operators=num_operators),
        encoding="utf-8")

    if cfg is not None:
        by_region: dict[str, list] = {}
        for op in cfg.operators:
            by_region.setdefault(op.region_name, []).append(op)
        (site_dir / "sources.html").write_text(
            env.get_template("sources.html.j2").render(
                prefix="", by_region=by_region, news_sources=cfg.news_sources,
                num_operators=num_operators),
            encoding="utf-8")

    log.info("Site rendered: %d report(s) -> %s", len(reports), site_dir)
