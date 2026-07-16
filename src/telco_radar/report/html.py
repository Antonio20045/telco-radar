"""Static report site generator - terminal-style intelligence dashboard."""
from __future__ import annotations

import html as html_lib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import markdown as md
from jinja2 import Environment, FileSystemLoader, select_autoescape

log = logging.getLogger(__name__)

_TEMPLATES = Path(__file__).parent / "templates"
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

RELEVANCE_LABELS = {
    5: "Sofort ansehen",
    4: "Wichtig",
    3: "Beobachten",
    2: "Randnotiz",
    1: "Randnotiz",
    0: "Unbewertet",
}

CATEGORY_COLORS = {
    "Produktlaunch": "#4c9aff",
    "Tarif/Pricing": "#36b37e",
    "Kampagne": "#a77bf3",
    "Partnerschaft": "#00b8d9",
    "Netz/Technologie": "#7a8cff",
    "Regulierung": "#ffab00",
    "M&A": "#ff5c5c",
    "Finanzen": "#8993a4",
    "Sonstiges": "#6b778c",
    "Unbewertet": "#6b778c",
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
    env = Environment(
        loader=FileSystemLoader(_TEMPLATES),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["domain"] = lambda u: urlsplit(u or "").netloc.removeprefix("www.")
    env.filters["date_de"] = _fmt_date_de
    return env


def _md_to_html(text: str) -> str:
    return md.markdown(text or "", extensions=["extra", "sane_lists"])


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
            reports[f.stem] = {
                "date": f.stem, "generated_with_llm": False, "stats": {},
                "briefing_md": f.read_text(encoding="utf-8"), "regions": {},
            }
    return [reports[k] for k in sorted(reports, reverse=True)]


def _flatten(report: dict) -> list[dict]:
    """All highlights across regions with ids, sorted: relevance desc, date desc."""
    out = []
    for region_name, region in (report.get("regions") or {}).items():
        for h in region.get("highlights") or []:
            h = dict(h)
            h["region"] = region_name
            h["relevance"] = h.get("relevance") or 0
            h["relevance_label"] = RELEVANCE_LABELS.get(h["relevance"], "")
            h["category"] = h.get("category") or "Sonstiges"
            h["source_domain"] = urlsplit(h.get("url") or "").netloc.removeprefix("www.")
            out.append(h)
    out.sort(key=lambda h: (h["relevance"], h.get("date") or ""), reverse=True)
    for i, h in enumerate(out):
        h["id"] = i
    return out


# --------------------------------------------------------------- SVG charts
def _bar_chart_svg(counts: list[tuple[str, int, str]], width: int = 460,
                   row_h: int = 34) -> str:
    """Horizontal bar chart. counts: [(label, value, color)]."""
    if not counts:
        return ""
    maxv = max(v for _, v, _ in counts) or 1
    label_w, value_w, pad = 150, 34, 6
    bar_max = width - label_w - value_w - pad * 2
    height = row_h * len(counts)
    parts = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
             f'role="img" class="chart">']
    for i, (label, value, color) in enumerate(counts):
        y = i * row_h
        bw = max(3, round(bar_max * value / maxv))
        lbl = html_lib.escape(label[:22])
        parts.append(
            f'<text x="{label_w - pad}" y="{y + row_h / 2 + 4}" text-anchor="end" '
            f'class="c-label">{lbl}</text>'
            f'<rect x="{label_w}" y="{y + 7}" width="{bar_max}" height="{row_h - 16}" '
            f'rx="5" class="c-track"/>'
            f'<rect x="{label_w}" y="{y + 7}" width="{bw}" height="{row_h - 16}" '
            f'rx="5" fill="{color}"/>'
            f'<text x="{label_w + bw + 8}" y="{y + row_h / 2 + 4}" class="c-value">'
            f'{value}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _charts(highlights: list[dict]) -> dict[str, str]:
    by_region: dict[str, int] = {}
    by_cat: dict[str, int] = {}
    by_rel: dict[int, int] = {5: 0, 4: 0, 3: 0, 2: 0}
    for h in highlights:
        by_region[h["region"]] = by_region.get(h["region"], 0) + 1
        by_cat[h["category"]] = by_cat.get(h["category"], 0) + 1
        r = max(2, min(5, h["relevance"] or 2))
        by_rel[r] += 1

    region_rows = sorted(by_region.items(), key=lambda kv: -kv[1])
    cat_rows = sorted(by_cat.items(), key=lambda kv: -kv[1])[:8]
    rel_colors = {5: "#ff4d4d", 4: "#ffab00", 3: "#4c9aff", 2: "#6b778c"}

    return {
        "regions": _bar_chart_svg(
            [(k, v, "#e60000") for k, v in region_rows]),
        "categories": _bar_chart_svg(
            [(k, v, CATEGORY_COLORS.get(k, "#6b778c")) for k, v in cat_rows]),
        "relevance": _bar_chart_svg(
            [(f"{r}/5 – {RELEVANCE_LABELS[r]}", by_rel[r], rel_colors[r])
             for r in (5, 4, 3, 2)]),
    }


# ------------------------------------------------------------------- render
def render_site(site_dir: Path, reports_dir: Path, cfg=None) -> None:
    env = _env()
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "reports").mkdir(exist_ok=True)
    (site_dir / ".nojekyll").write_text("")
    for asset in ("style.css", "app.js"):
        (site_dir / asset).write_text(
            (_TEMPLATES / asset).read_text(encoding="utf-8"), encoding="utf-8")

    reports = _load_reports(reports_dir)
    archive = [{"date": r["date"], "date_de": _fmt_date_de(r["date"]),
                "stats": r.get("stats", {}),
                "llm": r.get("generated_with_llm", False)} for r in reports]

    report_tpl = env.get_template("report.html.j2")
    for i, report in enumerate(reports):
        highlights = _flatten(report)
        top = [h for h in highlights if h["relevance"] >= 4][:6]
        ticker = [h for h in highlights if h["relevance"] >= 3][:14]
        ctx = {
            "report": report,
            "date_de": _fmt_date_de(report["date"]),
            "highlights": highlights,
            "explorer_json": json.dumps(highlights, ensure_ascii=False),
            "top_priorities": top,
            "ticker_items": ticker,
            "charts": _charts(highlights) if highlights else None,
            "briefing_html": _md_to_html(report.get("briefing_md", "")),
            "regions": sorted({h["region"] for h in highlights}),
            "categories": sorted({h["category"] for h in highlights}),
            "archive": archive,
            "is_latest": i == 0,
        }
        (site_dir / "reports" / f"{report['date']}.html").write_text(
            report_tpl.render(prefix="../", **ctx), encoding="utf-8")
        if i == 0:
            (site_dir / "index.html").write_text(
                report_tpl.render(prefix="", **ctx), encoding="utf-8")

    if not reports:
        (site_dir / "index.html").write_text(
            report_tpl.render(prefix="", report=None, date_de="", highlights=[],
                              explorer_json="[]", top_priorities=[],
                              ticker_items=[], charts=None, briefing_html="",
                              regions=[], categories=[], archive=[],
                              is_latest=True),
            encoding="utf-8")

    (site_dir / "archive.html").write_text(
        env.get_template("archive.html.j2").render(prefix="", archive=archive),
        encoding="utf-8")

    if cfg is not None:
        by_region: dict[str, list] = {}
        for op in cfg.operators:
            by_region.setdefault(op.region_name, []).append(op)
        (site_dir / "sources.html").write_text(
            env.get_template("sources.html.j2").render(
                prefix="", by_region=by_region, news_sources=cfg.news_sources),
            encoding="utf-8")

    log.info("Site rendered: %d report(s) -> %s", len(reports), site_dir)
