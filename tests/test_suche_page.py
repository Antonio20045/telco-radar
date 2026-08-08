"""Tests fuer die Suche - seit dem 08.08.2026 wieder eine eigene Seite.

Sie lebte von 06.08. bis 08.08.2026 am FUSS von meldungen.html, und genau das
war der Fehler: das Topbar-Formular fuehrte dorthin, und wer "Telekom" suchte,
sah zuerst sieben Ressortkacheln, sieben Ressortbloecke und das Archiv - die
Treffer standen nach rund 2400 px. Antonio: "Wenn ich was suche, werde ich auf
die Unterseite Meldungen weitergeleitet ... ich verstehe nicht, warum."

Die Begruendung von damals ("drei Orte fuer dasselbe Beduerfnis") war richtig
und wird hier nicht rueckgaengig gemacht: die Suche ist kein dritter Ort fuer
"zeig mir die Einzelmeldung", sondern beantwortet eine eigene Frage - "was
weiss dieses Portal ueber mein Thema, und wie hat es sich entwickelt". Deshalb
ist suche.html ein Dossier und keine Trefferliste.

Die Aggregationslogik ist unabhaengig davon in test_search_index.py
abgesichert.
"""
from telco_radar.report.html import render_site

# Die vier Seiten der Marktrecherche nach dem Redesign.
SEITEN = ("index.html", "meldungen.html", "differenzierung.html",
          "wettbewerb.html", "transparenz.html")


def test_die_suchseite_traegt_das_dossier_und_referenziert_den_index(tmp_path):
    reports_dir = tmp_path / "data" / "reports"
    reports_dir.mkdir(parents=True)
    site_dir = tmp_path / "site"

    render_site(site_dir, reports_dir, cfg=None)

    suche = (site_dir / "suche.html").read_text(encoding="utf-8")
    # Das Feld und die Behaelter, die app.js fuellt.
    assert 'id="dossier-input"' in suche
    assert 'id="dossier-bilanz"' in suche
    assert 'id="dossier-treffer"' in suche
    assert 'id="dossier-verlauf"' in suche      # die Entwicklung ueber Monate
    assert 'id="dossier-filter"' in suche

    # search_index.json entsteht daneben und ist das, was app.js laedt.
    assert (site_dir / "search_index.json").exists()
    app_js = (site_dir / "app.js").read_text(encoding="utf-8")
    assert "search_index.json" in app_js
    assert "TelcoSearch" in app_js


def test_die_suche_steht_nicht_mehr_am_fuss_der_meldungsseite(tmp_path):
    """Der Zustand, der Antonios Satz ausgeloest hat: das Topbar-Formular
    fuehrte auf meldungen.html, und die Treffer standen dort ganz unten."""
    reports_dir = tmp_path / "data" / "reports"
    reports_dir.mkdir(parents=True)
    site_dir = tmp_path / "site"

    render_site(site_dir, reports_dir, cfg=None)

    meldungen = (site_dir / "meldungen.html").read_text(encoding="utf-8")
    for tot in ('id="suche-input"', 'id="suche-count"', 'id="suche-results"',
                "Im Gesamtarchiv suchen"):
        assert tot not in meldungen, tot
    # Und kein toter CSS-Block zurueckgeblieben.
    assert "meldungen-suche" not in (site_dir / "style.css").read_text(encoding="utf-8")


def test_topbar_formular_zeigt_auf_die_suchseite(tmp_path):
    """Jede Seite traegt das native Formular (funktioniert ohne JS) und
    kein Live-Dropdown. Auf der Suchseite selbst faellt es weg - dort steht
    das grosse Feld im Seitenkopf, und zwei Suchfelder auf einer Seite sind
    zwei Bedienelemente fuer eine Handlung."""
    reports_dir = tmp_path / "data" / "reports"
    reports_dir.mkdir(parents=True)
    site_dir = tmp_path / "site"

    render_site(site_dir, reports_dir, cfg=None)

    for page in SEITEN:
        html = (site_dir / page).read_text(encoding="utf-8")
        assert 'action="suche.html"' in html
        assert "gsearch-results" not in html
    suche = (site_dir / "suche.html").read_text(encoding="utf-8")
    assert 'id="gsearch-input"' not in suche


def test_navigation_hat_fuenf_eintraege(tmp_path):
    """Sieben Unterseiten fuer eine Frage waren der Befund; vier waren das
    Ziel (PLAN_MARKTRECHERCHE_REDESIGN.md, Abschnitt 3). Seit dem 08.08.2026
    sind es fuenf: "Wettbewerb" beantwortet eine eigene Frage, die keine der
    vier beantwortet - was Telekom, O2 und 1&1 ueber die Wochen tun."""
    reports_dir = tmp_path / "data" / "reports"
    reports_dir.mkdir(parents=True)
    site_dir = tmp_path / "site"

    render_site(site_dir, reports_dir, cfg=None)

    html = (site_dir / "index.html").read_text(encoding="utf-8")
    nav = html.split('aria-label="Marktrecherche"')[1].split("</nav>")[0]
    for ziel in ("index.html", "meldungen.html", "differenzierung.html",
                 "wettbewerb.html", "transparenz.html"):
        assert f'href="{ziel}"' in nav
    # Die Rubrik heisst "Quellen" - "Transparenz" war Behoerdendeutsch.
    assert ">Quellen</a>" in nav
    assert ">Transparenz</a>" not in nav
    assert nav.count("<a ") == 5
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

    # `suche.html` steht NICHT mehr darunter: der Name ist seit dem
    # 08.08.2026 wieder eine echte Seite - ein Lesezeichen darauf landet also
    # dort, wo es immer hinwollte.
    erwartet = {
        "bericht.html": "index.html",
        "archive.html": "meldungen.html#archiv",
        "protokoll.html": "transparenz.html",
        "sources.html": "transparenz.html#bestand",
        # Seit dem 08.08.2026 gibt es die Seite wieder, die dieser Name
        # meint - die Weiterleitung zeigt wieder dorthin statt auf den
        # Kurzverweis der Titelseite.
        "wettbewerber.html": "wettbewerb.html",
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

    for seite in (*SEITEN, "suche.html"):
        assert (site_dir / seite).exists(), seite
    assert (site_dir / "search_index.json").read_text(encoding="utf-8") == "[]"
