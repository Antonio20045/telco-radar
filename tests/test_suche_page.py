"""Tests for the standalone search results page (suche.html).

Ausbau von claude/suche-ergebnisseite-konzept.md: statt eines Topbar-Dropdowns
mit 8er-Deckel gibt es jetzt eine eigenstaendige, bookmarkbare Ergebnisseite.
Dieser Test prueft den im Konzept geforderten Mindest-Rendering-Nachweis:
render_site() erzeugt suche.html, und die Seite (bzw. die von ihr genutzte
app.js) referenziert den siteweiten search_index.json. Die eigentliche
Aggregationslogik ist unabhaengig davon in test_search_index.py abgesichert.
"""
from telco_radar.report.html import render_site


def test_render_site_creates_suche_page_that_references_the_search_index(tmp_path):
    reports_dir = tmp_path / "data" / "reports"
    reports_dir.mkdir(parents=True)
    site_dir = tmp_path / "site"

    render_site(site_dir, reports_dir, cfg=None)

    suche_html = (site_dir / "suche.html").read_text(encoding="utf-8")
    # The results page itself: search input, filter chips, results container.
    assert 'id="suche-input"' in suche_html
    assert 'id="suche-count"' in suche_html
    assert 'id="suche-results"' in suche_html
    assert 'data-kind="bericht"' in suche_html
    assert 'data-kind="differenzierung"' in suche_html

    # search_index.json is written alongside and is what app.js fetches for
    # both the topbar form target and suche.html itself - the "referenced"
    # half of the acceptance test from the concept doc.
    assert (site_dir / "search_index.json").exists()
    app_js = (site_dir / "app.js").read_text(encoding="utf-8")
    assert "search_index.json" in app_js
    assert "TelcoSearch" in app_js

    # Decision (siehe Konzept Abschnitt 6): kein eigener Navigationslink -
    # suche.html ist nur ueber die Suche selbst erreichbar. Jede Seite traegt
    # aber die Topbar mit dem nativen Formular, das ohne JS zu suche.html
    # navigiert, und zeigt kein Live-Dropdown mehr.
    for page in ("archive.html", "differenzierung.html", "wettbewerber.html", "suche.html"):
        html = (site_dir / page).read_text(encoding="utf-8")
        assert 'action="suche.html"' in html
        assert 'href="suche.html"' not in html
        assert "gsearch-results" not in html


def test_render_site_without_any_reports_still_renders_suche_page(tmp_path):
    """suche.html must exist even on a fresh/empty site (bootstrap case)."""
    reports_dir = tmp_path / "data" / "reports"
    reports_dir.mkdir(parents=True)
    site_dir = tmp_path / "site"

    render_site(site_dir, reports_dir, cfg=None)

    assert (site_dir / "suche.html").exists()
    assert (site_dir / "search_index.json").read_text(encoding="utf-8") == "[]"
