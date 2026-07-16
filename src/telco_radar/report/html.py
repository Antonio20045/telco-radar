"""Static report site generator (published via GitHub Pages)."""
from __future__ import annotations

import logging
import re
from pathlib import Path

import markdown as md
from jinja2 import Environment, FileSystemLoader, select_autoescape

log = logging.getLogger(__name__)

_TEMPLATES = Path(__file__).parent / "templates"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(_TEMPLATES),
        autoescape=select_autoescape(["html"]),
    )


def _md_to_html(text: str) -> str:
    return md.markdown(text, extensions=["extra", "sane_lists"])


def _archive_entries(reports_dir: Path) -> list[dict]:
    entries = []
    for f in sorted(reports_dir.glob("*.md"), reverse=True):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", f.stem):
            entries.append({"date": f.stem, "href": f"reports/{f.stem}.html"})
    return entries


def render_site(site_dir: Path, reports_dir: Path) -> None:
    """(Re)build the whole static site from data/reports/*.md."""
    env = _env()
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "reports").mkdir(exist_ok=True)
    (site_dir / ".nojekyll").write_text("")
    (site_dir / "style.css").write_text(
        (_TEMPLATES / "base.css").read_text(encoding="utf-8"), encoding="utf-8")

    archive = _archive_entries(reports_dir)
    report_tpl = env.get_template("report.html.j2")

    latest_html = ""
    for i, entry in enumerate(archive):
        source = reports_dir / f"{entry['date']}.md"
        body = _md_to_html(source.read_text(encoding="utf-8"))
        if i == 0:
            latest_html = body
        (site_dir / "reports" / f"{entry['date']}.html").write_text(
            report_tpl.render(date=entry["date"], body=body, archive=archive),
            encoding="utf-8",
        )

    index_tpl = env.get_template("index.html.j2")
    (site_dir / "index.html").write_text(
        index_tpl.render(
            latest=archive[0] if archive else None,
            body=latest_html,
            archive=archive,
        ),
        encoding="utf-8",
    )
    log.info("Site rendered: %d report(s), index -> %s",
             len(archive), site_dir / "index.html")
