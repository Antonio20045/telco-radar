"""Static report site generator (deployed to Render as a static site)."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from urllib.parse import urlsplit

import markdown as md
from jinja2 import Environment, FileSystemLoader, select_autoescape

log = logging.getLogger(__name__)

_TEMPLATES = Path(__file__).parent / "templates"
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

CATEGORY_CLASS = {
    "Produktlaunch": "cat-launch",
    "Tarif/Pricing": "cat-pricing",
    "Kampagne": "cat-campaign",
    "Partnerschaft": "cat-partner",
    "Netz/Technologie": "cat-tech",
    "Regulierung": "cat-regulation",
    "M&A": "cat-ma",
    "Finanzen": "cat-finance",
    "Sonstiges": "cat-other",
    "Unbewertet": "cat-unrated",
}


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(_TEMPLATES),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["domain"] = lambda u: urlsplit(u or "").netloc.removeprefix("www.")
    env.filters["catclass"] = lambda c: CATEGORY_CLASS.get(c or "", "cat-other")
    return env


def _md_to_html(text: str) -> str:
    return md.markdown(text or "", extensions=["extra", "sane_lists"])


def _load_reports(reports_dir: Path) -> list[dict]:
    """Load all reports, newest first. JSON preferred, bare MD as fallback."""
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
                "date": f.stem,
                "generated_with_llm": False,
                "stats": {},
                "briefing_md": f.read_text(encoding="utf-8"),
                "regions": {},
            }
    return [reports[k] for k in sorted(reports, reverse=True)]


def _flatten_highlights(report: dict) -> list[dict]:
    """All highlights across regions, sorted by relevance desc, date desc."""
    out = []
    for region_name, region in (report.get("regions") or {}).items():
        for h in region.get("highlights") or []:
            h = dict(h)
            h["region"] = region_name
            out.append(h)
    out.sort(key=lambda h: (-(h.get("relevance") or 0), h.get("date") or ""),
             reverse=False)
    out.sort(key=lambda h: ((h.get("relevance") or 0), h.get("date") or ""),
             reverse=True)
    return out


def render_site(site_dir: Path, reports_dir: Path, cfg=None) -> None:
    """(Re)build the whole static site from data/reports/."""
    env = _env()
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "reports").mkdir(exist_ok=True)
    (site_dir / ".nojekyll").write_text("")
    for asset in ("style.css", "app.js"):
        (site_dir / asset).write_text(
            (_TEMPLATES / asset).read_text(encoding="utf-8"), encoding="utf-8")

    reports = _load_reports(reports_dir)
    archive = [{"date": r["date"], "stats": r.get("stats", {}),
                "llm": r.get("generated_with_llm", False)} for r in reports]

    report_tpl = env.get_template("report.html.j2")
    for i, report in enumerate(reports):
        ctx = {
            "report": report,
            "highlights": _flatten_highlights(report),
            "briefing_html": _md_to_html(report.get("briefing_md", "")),
            "regions": sorted((report.get("regions") or {}).keys()),
            "categories": sorted({h.get("category") or "Sonstiges"
                                  for h in _flatten_highlights(report)}),
            "archive": archive,
            "is_latest": i == 0,
        }
        (site_dir / "reports" / f"{report['date']}.html").write_text(
            report_tpl.render(prefix="../", **ctx), encoding="utf-8")
        if i == 0:
            (site_dir / "index.html").write_text(
                report_tpl.render(prefix="", **ctx), encoding="utf-8")

    if not reports:
        empty_tpl = env.get_template("report.html.j2")
        (site_dir / "index.html").write_text(
            empty_tpl.render(prefix="", report=None, highlights=[],
                             briefing_html="", regions=[], categories=[],
                             archive=[], is_latest=True),
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
