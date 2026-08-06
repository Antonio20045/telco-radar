"""Tests fuer die Suche - seit dem Redesign Teil von meldungen.html.

Ausbau von claude/suche-ergebnisseite-konzept.md: statt eines Topbar-Dropdowns
mit 8er-Deckel gibt es eine eigenstaendige, bookmarkbare Ergebnisliste.

Seit dem Redesign (06.08.2026, PLAN_MARKTRECHERCHE_REDESIGN.md) lebt sie
nicht mehr auf einer eigenen suche.html, sondern oben auf meldungen.html -
zusammen mit dem Wochen-Explorer und dem Archiv. Der Grund: das waren drei
Orte fuer dasselbe Beduerfnis ("zeig mir die Einzelmeldung"). Die
Aggregationslogik ist unabhaengig davon in test_search_index.py abgesichert.
"""
from telco_radar.report.html import render_site

# Die vier Seiten der Marktrecherche nach dem Redesign.
SEITEN = ("index.html", "meldungen.html", "differenzierung.html",
          "transparenz.html")


def test_meldungen_traegt_die_suche_und_referenziert_den_index(tmp_path):
    reports_dir = tmp_path / "data" / "reports"
    reports_dir.mkdir(parents=True)
    site_dir = tmp_path / "site"

    render_site(site_dir, reports_dir, cfg=None)

    meldungen = (site_dir / "meldungen.html").read_text(encoding="utf-8")
    # Die Suche selbst: Eingabefeld, Filterchips, Trefferbehaelter.
    assert 'id="suche-input"' in meldungen
    assert 'id="suche-count"' in meldungen
    assert 'id="suche-results"' in meldungen
    assert 'data-kind="bericht"' in meldungen
    assert 'data-kind="differenzierung"' in meldungen

    # search_index.json entsteht daneben und ist das, was app.js laedt -
    # fuer das Topbar-Formular wie fuer die Ergebnisliste selbst.
    assert (site_dir / "search_index.json").exists()
    app_js = (site_dir / "app.js").read_text(encoding="utf-8")
    assert "search_index.json" in app_js
    assert "TelcoSearch" in app_js


def test_topbar_formular_zeigt_auf_meldungen(tmp_path):
    """Jede Seite traegt das native Formular (funktioniert ohne JS) und
    kein Live-Dropdown."""
    reports_dir = tmp_path / "data" / "reports"
    reports_dir.mkdir(parents=True)
    site_dir = tmp_path / "site"

    render_site(site_dir, reports_dir, cfg=None)

    for page in SEITEN:
        html = (site_dir / page).read_text(encoding="utf-8")
        assert 'action="meldungen.html"' in html
        assert "gsearch-results" not in html


def test_navigation_hat_vier_eintraege(tmp_path):
    """Sieben Unterseiten fuer eine Frage waren der Befund; vier sind das
    Ziel (PLAN_MARKTRECHERCHE_REDESIGN.md, Abschnitt 3)."""
    reports_dir = tmp_path / "data" / "reports"
    reports_dir.mkdir(parents=True)
    site_dir = tmp_path / "site"

    render_site(site_dir, reports_dir, cfg=None)

    html = (site_dir / "index.html").read_text(encoding="utf-8")
    nav = html.split('aria-label="Marktrecherche"')[1].split("</nav>")[0]
    for ziel in ("index.html", "meldungen.html", "differenzierung.html",
                 "transparenz.html"):
        assert f'href="{ziel}"' in nav
    # Die Rubrik heisst "Quellen" - "Transparenz" war Behoerdendeutsch.
    assert ">Quellen</a>" in nav
    assert ">Transparenz</a>" not in nav
    assert nav.count("<a ") == 4
    # Die aufgeloesten Seiten duerfen nicht mehr in der Navigation stehen.
    for weg in ("bericht.html", "archive.html", "sources.html",
                "protokoll.html", "wettbewerber.html", "suche.html"):
        assert f'href="{weg}"' not in nav


def test_alte_dateinamen_leiten_weiter(tmp_path):
    """Die alten URLs stehen in Lesezeichen und Mails - ein 404 waere die
    teuerste Art, eine Navigation aufzuraeumen."""
    reports_dir = tmp_path / "data" / "reports"
    reports_dir.mkdir(parents=True)
    site_dir = tmp_path / "site"

    render_site(site_dir, reports_dir, cfg=None)

    erwartet = {
        "bericht.html": "index.html",
        "suche.html": "meldungen.html",
        "archive.html": "meldungen.html#archiv",
        "protokoll.html": "transparenz.html",
        "sources.html": "transparenz.html#bestand",
        "wettbewerber.html": "index.html#deutschland-fokus",
    }
    for alt, ziel in erwartet.items():
        html = (site_dir / alt).read_text(encoding="utf-8")
        assert f'content="0; url={ziel}"' in html
        # Auch ohne Meta-Refresh muss man weiterkommen.
        assert f'href="{ziel}"' in html


def test_render_site_ohne_berichte_erzeugt_trotzdem_alle_seiten(tmp_path):
    """Bootstrap-Fall: die Site muss auch ohne einen einzigen Bericht
    vollstaendig und ohne tote Navigationslinks stehen."""
    reports_dir = tmp_path / "data" / "reports"
    reports_dir.mkdir(parents=True)
    site_dir = tmp_path / "site"

    render_site(site_dir, reports_dir, cfg=None)

    for seite in SEITEN:
        assert (site_dir / seite).exists(), seite
    assert (site_dir / "search_index.json").read_text(encoding="utf-8") == "[]"
