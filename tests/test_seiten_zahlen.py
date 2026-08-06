"""Wahrheitstests: keine Zahl auf einer Seite darf den Daten widersprechen.

Der Anlass, gefunden am 06.08.2026 beim Aufmass fuer den Redesign
(PLAN_MARKTRECHERCHE_REDESIGN.md, Abschnitt 1):

* `protokoll.html` trug die Kachel "426 neue Meldungen bewertet". 426 waren
  die neu GESAMMELTEN, bewertet (als relevant behalten) wurden 92.
* `bericht.html` ueberschrieb "Alle Signale dieser Woche" eine Liste, die
  html.py auf `relevance >= 4` und dann auf sechs Eintraege kappt - am
  05.08.2026 also 6 von 92.
* `wettbewerber.html` war seit dem 04.08. leer und sagte dem Leser, die
  Analyse "entstehe beim naechsten Lauf" - obwohl der Lauf stattgefunden
  hatte und in 0,6 s an einer falschen Modell-ID gescheitert war.

Alle drei sind an `pytest -q` vorbeigekommen, weil von den damals 37
Testdateien nur zwei ueberhaupt `render_site()` aufriefen und beide nur die
FORM pruefen (Escaping, Existenz von Elementen). Diese Datei prueft den
INHALT: was auf der Seite steht, gegen das, was in der Berichtsdatei steht.
"""
from __future__ import annotations

import json
import re

import pytest

from telco_radar.report.html import render_site


def _highlight(i: int, relevance: int) -> dict:
    return {
        "title": f"Meldung {i}",
        "operator": f"Betreiber {i}",
        "url": f"https://example.com/{i}",
        "category": "Netz/Technologie",
        "relevance": relevance,
        "summary": f"Zusammenfassung der Meldung {i}.",
        "why_it_matters": "Interne Einordnung.",
        "date": "2026-08-05",
        "source": "Beispielquelle",
    }


# 12 relevante Meldungen, davon 8 mit relevance >= 4: mehr als der Deckel von
# sechs, den html.py auf die Signalliste legt - sonst wuerde der Test die
# Kappung gar nicht sehen.
HIGHLIGHTS = ([_highlight(i, 5) for i in range(4)]
              + [_highlight(i, 4) for i in range(4, 8)]
              + [_highlight(i, 3) for i in range(8, 12)])
NEU_GESAMMELT = 426


def _render(tmp_path, *, competitors=None, stats=None):
    reports = tmp_path / "reports"
    reports.mkdir(parents=True)
    (reports / "2026-08-05.json").write_text(json.dumps({
        "date": "2026-08-05",
        "generated_with_llm": True,
        "stats": stats if stats is not None else {"new": NEU_GESAMMELT},
        "briefing_md": "## Auf einen Blick\n\nText.\n\n## Europa\n\nMehr Text.",
        "regions": {"Europa": {"region_summary": "", "highlights": HIGHLIGHTS}},
        "competitors": competitors if competitors is not None else [],
        "run": {"duration_seconds": 1487.8, "models": {"analyst": "m", "editor": "m"},
                "phases": [], "analysts": [], "sources": [],
                "source_summary": {"ok": 1, "empty": 0, "failed": 0}},
    }, ensure_ascii=False), encoding="utf-8")
    site = tmp_path / "site"
    render_site(site, reports)
    return site


def _seite(site, name: str) -> str:
    return (site / name).read_text(encoding="utf-8")


# --------------------------------------------------------------- Protokoll
def test_protokoll_trennt_gesammelt_von_bewertet(tmp_path):
    """Die beiden Zahlen duerfen nicht unter EIN Label fallen."""
    html = _seite(_render(tmp_path), "protokoll.html")

    assert f"<b>{NEU_GESAMMELT}</b><span>neue Meldungen gelesen</span>" in html
    assert f"<b>{len(HIGHLIGHTS)}</b><span>davon relevant</span>" in html
    # Der alte, falsche Text darf nicht zurueckkommen.
    assert f"<b>{NEU_GESAMMELT}</b><span>neue Meldungen bewertet</span>" not in html


def test_protokoll_erklaert_den_abstand_zwischen_den_zahlen(tmp_path):
    html = _seite(_render(tmp_path), "protokoll.html")
    assert "Warum die zweite Zahl kleiner ist" in html


def test_protokoll_erklaert_nichts_wenn_es_nichts_zu_erklaeren_gibt(tmp_path):
    """Gegenprobe: sind beide Zahlen gleich, faellt der Hinweis weg."""
    html = _seite(_render(tmp_path, stats={"new": len(HIGHLIGHTS)}), "protokoll.html")
    assert "Warum die zweite Zahl kleiner ist" not in html


# ------------------------------------------------------------------ Bericht
def test_signalliste_verspricht_nicht_mehr_als_sie_zeigt(tmp_path):
    """Die Ueberschrift muss der Zahl der gerenderten Zeilen entsprechen."""
    html = _seite(_render(tmp_path), "bericht.html")

    gezeigt = html.count('class="signal-row"')
    m = re.search(r"<h2>Die (\d+) dringendsten Signale</h2>", html)
    assert m, "Ueberschrift der Signalliste fehlt"
    assert int(m.group(1)) == gezeigt

    # Das eigentliche Verbot: keine Ueberschrift, die "alle" behauptet,
    # solange gekappt wird.
    assert gezeigt < len(HIGHLIGHTS)
    assert "Alle Signale dieser Woche" not in html


def test_bericht_verlinkt_die_vollstaendige_liste(tmp_path):
    """Wer gekappt anzeigt, muss den Weg zur vollen Liste zeigen."""
    html = _seite(_render(tmp_path), "bericht.html")
    assert f"alle {len(HIGHLIGHTS)} Meldungen" in html
    assert 'id="alle-meldungen"' in html


def test_kopfzeile_nennt_gelesen_und_relevant_getrennt(tmp_path):
    html = _seite(_render(tmp_path), "bericht.html")
    assert f"{NEU_GESAMMELT} neue Meldungen gelesen, {len(HIGHLIGHTS)} relevant" in html


def test_explorer_enthaelt_wirklich_alle_meldungen(tmp_path):
    """Die Zahl im Aufklapper muss zu den eingebetteten Daten passen."""
    html = _seite(_render(tmp_path), "bericht.html")
    daten = json.loads(re.search(r'id="explorer-data">(.*?)</script>', html, re.S).group(1))
    assert len(daten) == len(HIGHLIGHTS)
    assert f"Alle {len(HIGHLIGHTS)} Meldungen durchsuchen" in html


def test_interne_einordnung_verlaesst_die_seite_nicht(tmp_path):
    """`why_it_matters` ist intern und darf in keiner Seite auftauchen."""
    site = _render(tmp_path)
    for name in ("bericht.html", "index.html", "search_index.json"):
        assert "Interne Einordnung." not in _seite(site, name)


# ------------------------------------------------------------- Wettbewerber
GESCHEITERT = [{"name": "Deutsche Telekom", "n_items": 16, "moves": [],
                "summary": "", "themes": [], "vodafone_implication": "",
                "error": "RuntimeError: unknown model"}]
GELUNGEN = [{"name": "Deutsche Telekom", "n_items": 16,
             "moves": [{"title": "Ein Zug", "url": "https://example.com/z",
                        "category": "Netz/Technologie", "note": "Notiz."}],
             "summary": "Profiltext.", "themes": ["5G"],
             "vodafone_implication": "Folge.", "error": ""}]


def test_gescheiterte_analyse_sagt_dass_sie_gescheitert_ist(tmp_path):
    """Kein "kommt beim naechsten Lauf", wenn der Lauf schon war."""
    html = _seite(_render(tmp_path, competitors=GESCHEITERT), "wettbewerber.html")
    assert "ist gescheitert" in html
    assert "entsteht beim nächsten Lauf" not in html
    # Und die Seite gibt zu, dass die Zuordnung funktioniert hat.
    assert "16 Treffer" in html


def test_vorhandene_profile_zeigen_keinen_leertext(tmp_path):
    """Der Fall, der am 04.08. still verloren ging."""
    html = _seite(_render(tmp_path, competitors=GELUNGEN), "wettbewerber.html")
    assert "Profiltext." in html
    assert "ist gescheitert" not in html
    assert "liegt noch keine Wettbewerber-Detailanalyse vor" not in html


def test_ohne_profile_bleibt_der_alte_hinweis(tmp_path):
    """Ein Lauf ohne KI hat wirklich nichts - das darf so dastehen."""
    html = _seite(_render(tmp_path, competitors=[]), "wettbewerber.html")
    assert "liegt noch keine Wettbewerber-Detailanalyse vor" in html


# ------------------------------------------------- Modellwahl je Anbieter
@pytest.mark.parametrize("anbieter,erwartet_analyst,erwartet_editor", [
    ("deepseek", "deepseek-v4-flash", "deepseek-v4-pro"),
    ("openai", "anbieter-a/flash", "anbieter-a/pro"),
    ("anthropic", "claude-analyst", "claude-editor"),
])
def test_modelle_kommen_vom_aktiven_anbieter(anbieter, erwartet_analyst,
                                             erwartet_editor):
    """Die Ursache des Wettbewerber-Ausfalls, als Regressionstest.

    Bis zum 06.08.2026 holte der Wettbewerber-Zweig sein Modell fest aus
    `openai_analyst_model` - auch wenn DeepSeek der aktive Anbieter war. Der
    DeepSeek-Endpunkt kennt "deepseek-ai/deepseek-v4-flash" nicht und lehnte
    sofort ab.
    """
    from telco_radar.pipeline import _modelle_fuer_anbieter

    settings = {
        "openai_analyst_model": "anbieter-a/flash",
        "openai_editor_model": "anbieter-a/pro",
        "deepseek_analyst_model": "deepseek-v4-flash",
        "deepseek_editor_model": "deepseek-v4-pro",
        "analyst_model": "claude-analyst",
        "editor_model": "claude-editor",
    }
    analyst, editor = _modelle_fuer_anbieter(settings, anbieter, "fallback")
    assert (analyst, editor) == (erwartet_analyst, erwartet_editor)


def test_kein_anbieter_erbt_die_modell_id_eines_anderen():
    """Der allgemeine Fall: die Modell-IDs zweier OpenAI-kompatibler
    Anbieter duerfen sich nie mischen."""
    from telco_radar.pipeline import OPENAI_KOMPATIBEL, _modelle_fuer_anbieter

    settings = {"openai_analyst_model": "a/flash", "openai_editor_model": "a/pro",
                "deepseek_analyst_model": "b-flash", "deepseek_editor_model": "b-pro"}
    for anbieter, (_, analyst_key, editor_key) in OPENAI_KOMPATIBEL.items():
        analyst, editor = _modelle_fuer_anbieter(settings, anbieter, "fallback")
        assert analyst == settings[analyst_key]
        assert editor == settings[editor_key]
