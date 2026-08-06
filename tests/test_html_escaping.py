"""Ueberschriften fremder Quellen duerfen kein HTML in die Seite tragen.

Am 04.08.2026 gefunden: `select_autoescape(["html"])` sieht nur die LETZTE
Dateiendung an, und jede Vorlage heisst "*.html.j2". Das Escaping war damit
auf JEDER Seite aus - aufgefallen ist es an einem Themenlabel ("Chips &
Modems"), das als rohes "&" im HTML landete.

Die ernste Seite: in den Bericht fliessen die Ueberschriften und URLs fremder
Newsrooms und Fachpresse-Feeds. Was dort im Titel steht, bestimmt nicht
dieses Projekt. Mit dem Quellen-Ausbau sind es rund 130 Absender.

Die vier Stellen mit absichtlich fertigem HTML tragen "| safe" - dieser Test
haelt beides zusammen fest: Fremdtext wird escaped, die Redaktionsprosa nicht.
"""
from __future__ import annotations

import json
import re

from telco_radar.report.html import _env, render_site

BOESER_TITEL = '<img src=x onerror="alert(1)">Betreiber senkt Preise deutlich'


def test_vorlagen_escapen_wirklich():
    """Der eigentliche Fehler: die Endung heisst j2, nicht html."""
    env = _env()
    assert env.autoescape("sources.html.j2") is True
    assert env.autoescape("report.html.j2") is True
    assert env.from_string("{{ x }}").render(x="<b>&</b>") in (
        "&lt;b&gt;&amp;&lt;/b&gt;", "&lt;b&gt;&amp;&lt;/b&gt;")


def _bericht(tmp_path, briefing_md: str = "## Auf einen Blick\n\nText.") -> str:
    reports = tmp_path / "reports"
    reports.mkdir(parents=True)
    (reports / "2026-08-04.json").write_text(json.dumps({
        "date": "2026-08-04",
        "generated_with_llm": True,
        "stats": {"new": 1},
        "briefing_md": briefing_md,
        "regions": {"Europa": {"region_summary": "", "highlights": [{
            "title": BOESER_TITEL,
            "operator": "Beispiel",
            "url": "https://example.com/a",
            "category": "Tarif/Pricing",
            "relevance": 5,
            "summary": BOESER_TITEL,
            "why_it_matters": "Preisdruck.",
            "date": "2026-08-04",
            "source": "Beispiel",
        }]}},
    }, ensure_ascii=False), encoding="utf-8")
    render_site(tmp_path / "site", reports)
    return (tmp_path / "site" / "index.html").read_text(encoding="utf-8")


def test_fremde_ueberschrift_landet_escaped_in_der_seite(tmp_path):
    html = _bericht(tmp_path)
    # Entscheidend ist nicht, dass die Zeichenfolge "onerror" verschwindet -
    # als Text ist sie harmlos -, sondern dass kein Tag daraus wird. Auf "<img"
    # allein darf man dabei nicht pruefen: das Seitenlogo ist selbst ein
    # img-Tag.
    assert "<img src=x" not in html
    assert "&lt;img src=x" in html
    # Auch das Attribut darf nicht als Attribut dastehen: die
    # Anfuehrungszeichen sind escaped, damit es Text bleibt.
    assert 'onerror="alert(1)"' not in html
    assert "onerror=&#34;alert(1)&#34;" in html


def test_redaktionsprosa_bleibt_gerendertes_markdown(tmp_path):
    """Gegenprobe: der Wochenbericht selbst muss weiter echtes HTML sein,
    sonst haette der Fix die Seite zerlegt."""
    html = _bericht(tmp_path, "## Auf einen Blick\n\nEin **fetter** Satz.")
    assert "<strong>fetter</strong>" in html
    assert "&lt;strong&gt;" not in html


def test_explorer_json_bleibt_lesbar(tmp_path):
    """Die eingebetteten Explorer-Daten stehen in einem script-Tag und
    duerfen vom Escaping nicht zerstoert werden.

    Seit dem Redesign (06.08.2026) stehen sie auf meldungen.html statt auf
    der Berichtsseite - die Landeseite trug 78,5 KB JSON fuer einen
    zugeklappten Aufklapper."""
    _bericht(tmp_path)
    html = (tmp_path / "site" / "meldungen.html").read_text(encoding="utf-8")
    m = re.search(r'id="explorer-data">(.*?)</script>', html, re.S)
    assert m, "Explorer-Daten fehlen"
    daten = json.loads(m.group(1))
    assert daten and daten[0]["title"] == BOESER_TITEL
