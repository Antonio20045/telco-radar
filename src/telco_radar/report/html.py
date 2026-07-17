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


def _charts(highlights) -> dict:
    by_op = {}
    for h in highlights:
        op = (h.get("operator") or "").strip()
        if op:
            by_op[op] = by_op.get(op, 0) + 1
    comp_rows = sorted(by_op.items(), key=lambda kv: -kv[1])[:8]
    competitors = _bar_chart_svg([(k, v, "#e60000") for k, v in comp_rows])

    by_cat = {}
    for h in highlights:
        by_cat[h["category"]] = by_cat.get(h["category"], 0) + 1
    cat_rows = sorted(by_cat.items(), key=lambda kv: -kv[1])[:8]
    categories = _bar_chart_svg(
        [(k, v, CATEGORY_COLORS.get(k, "#7e7e7e")) for k, v in cat_rows])

    return {"competitors": competitors, "categories": categories,
            "n_competitors": len(by_op),
            "top_category": cat_rows[0][0] if cat_rows else ""}


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
            "explorer_json": json.dumps(highlights, ensure_ascii=False),
            "top_priorities": top,
            "charts": _charts(highlights) if highlights else None,
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
