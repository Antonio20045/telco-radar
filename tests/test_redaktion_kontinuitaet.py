"""E3B: eine leere Bewertungsrunde darf die Titelseite nicht leerraeumen.

Drei Ebenen, von unten nach oben:
  1. Die reine Logik in analyze/redaktion_kontinuitaet.py.
  2. Das Rendern (report/html.py + woche.html.j2): zeigt die Titelseite bei
     einer uebernommenen Redaktion wirklich den alten Aufmacher UND den
     alten Wochenbericht, jeweils mit sichtbarem "Stand: ..."?
  3. pipeline.run() selbst, mit `quellen=[]` (leere Watchlist/Fachpresse/
     Themenfelder) als Simulation einer Runde ohne neue Meldungen - genau
     der im Brief verlangte Testfall. Das lauft OHNE jeden LLM-Aufruf, weil
     `new_items` dabei leer ist (pipeline.py: `if use_llm and new_items`).
"""
from __future__ import annotations

import json
import shutil
from datetime import date, timedelta
from pathlib import Path

import pytest

from telco_radar import pipeline
from telco_radar.analyze import redaktion_kontinuitaet as rk
from telco_radar.report.html import render_site

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _bericht(datum: str, *, editor_used: bool = True,
             highlights: list[dict] | None = None,
             redaktion_ausfall: dict | None = None) -> dict:
    d = {
        "date": datum,
        "generated_with_llm": True,
        "stats": {"new": 12, "collected": 12, "sources_ok": 1,
                  "sources_failed": 0},
        "briefing_md": (
            "## Auf einen Blick\n"
            "- Der Testbetreiber senkt den Preis für Unlimited-Tarife.\n\n"
            "## Das Wichtigste\n\nDer Testbetreiber hat den Preis gesenkt.\n"
        ),
        "regions": {
            "Europa": {
                "region_summary": "",
                "highlights": highlights if highlights is not None else [
                    {"title": "Testbetreiber senkt Preis für Unlimited-Tarife",
                     "headline": "Testbetreiber senkt Preis für Unlimited-Tarife",
                     "operator": "Testbetreiber", "url": "https://example.de/a",
                     "source": "Testpresse", "relevance": 4, "ctm_bezug": 2,
                     "category": "Tarif/Pricing", "date": datum},
                ],
            },
        },
        "competitors": [],
        "run": {
            "editor_used": editor_used, "duration_seconds": 1.0,
            "models": {"analyst": "m" if editor_used else None,
                      "editor": "m" if editor_used else None},
            "source_summary": {"total": 1, "ok": 1, "empty": 0, "failed": 0},
            "phases": [], "sources": [], "analysts": [],
        },
    }
    if redaktion_ausfall:
        d["redaktion_ausfall"] = redaktion_ausfall
    return d


# --------------------------------------------------------------------------- #
# 1. Die reine Logik
# --------------------------------------------------------------------------- #

def test_bewertete_meldungen_zaehlt_ueber_alle_regionen():
    bericht = _bericht("2026-08-01", highlights=[{"url": "a"}, {"url": "b"}])
    assert rk.bewertete_meldungen(bericht) == 2
    assert rk.bewertete_meldungen({"regions": {}}) == 0
    assert rk.bewertete_meldungen({}) == 0


def test_ist_gueltige_redaktion_braucht_editor_und_meldungen():
    assert rk.ist_gueltige_redaktion(_bericht("2026-08-01"))
    assert not rk.ist_gueltige_redaktion(
        _bericht("2026-08-01", editor_used=False))
    assert not rk.ist_gueltige_redaktion(
        _bericht("2026-08-01", highlights=[]))


def test_ist_gueltige_redaktion_verwirft_eine_uebernahme():
    """Eine Kette von Uebernahmen zeigt immer auf den echten Ursprung."""
    bericht = _bericht("2026-08-01",
                       redaktion_ausfall={"stand": "2026-07-20", "grund": "x"})
    assert not rk.ist_gueltige_redaktion(bericht)


def test_letzte_gueltige_redaktion_findet_den_juengsten_treffer(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    for datum, gueltig in (("2026-08-01", True), ("2026-08-05", False),
                          ("2026-08-10", True), ("2026-08-15", True)):
        (reports / f"{datum}.json").write_text(
            json.dumps(_bericht(datum, editor_used=gueltig)), encoding="utf-8")

    treffer = rk.letzte_gueltige_redaktion(reports, "2026-08-20")
    assert treffer is not None
    assert treffer["date"] == "2026-08-15"

    # Vor dem 08-10 gesucht: der 08-15er zaehlt nicht, der 08-05er ist
    # ungueltig, uebrig bleibt der 08-01er.
    treffer2 = rk.letzte_gueltige_redaktion(reports, "2026-08-10")
    assert treffer2["date"] == "2026-08-01"


def test_letzte_gueltige_redaktion_ohne_treffer_ist_none(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    assert rk.letzte_gueltige_redaktion(reports, "2026-08-01") is None
    # Auch wenn es Berichte gibt, aber keiner davon gueltig ist.
    (reports / "2026-07-01.json").write_text(
        json.dumps(_bericht("2026-07-01", editor_used=False)),
        encoding="utf-8")
    assert rk.letzte_gueltige_redaktion(reports, "2026-08-01") is None


def test_uebernehmen_greift_nur_bei_null_bewerteten_meldungen(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "2026-08-01.json").write_text(
        json.dumps(_bericht("2026-08-01")), encoding="utf-8")

    # Die aktuelle Runde hat selbst etwas geliefert - nichts wird ersetzt.
    eigene = [{"url": "https://example.de/heute", "title": "Heute"}]
    regional, body, comp, ausfall = rk.uebernehmen(
        {"Europa": {"highlights": eigene}}, "eigener Text", [], reports,
        "2026-08-10", "grund")
    assert ausfall is None
    assert regional == {"Europa": {"highlights": eigene}}
    assert body == "eigener Text"


def test_uebernehmen_holt_die_letzte_gueltige_redaktion(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "2026-08-01.json").write_text(
        json.dumps(_bericht("2026-08-01")), encoding="utf-8")

    regional, body, comp, ausfall = rk.uebernehmen(
        {}, "", [], reports, "2026-08-10", "keine neuen Meldungen")
    assert ausfall == {"stand": "2026-08-01", "grund": "keine neuen Meldungen"}
    assert rk.bewertete_meldungen({"regions": regional}) == 1
    assert "Auf einen Blick" in body


def test_uebernehmen_ohne_vorgeschichte_bleibt_unveraendert(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    regional, body, comp, ausfall = rk.uebernehmen(
        {}, "", [], reports, "2026-08-01", "grund")
    assert ausfall is None
    assert regional == {}
    assert body == ""


# --------------------------------------------------------------------------- #
# 2. Das Rendern: Kriterium 1 + 2 des Briefs
# --------------------------------------------------------------------------- #

def test_titelseite_zeigt_die_uebernommene_redaktion_mit_stand(tmp_path):
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / "2026-08-01.json").write_text(
        json.dumps(_bericht("2026-08-01")), encoding="utf-8")
    # Die leere Runde, schon so geschrieben wie pipeline.py es taete.
    ausfall = {"stand": "2026-08-01",
               "grund": "es gab in dieser Runde keine neuen Meldungen "
                        "zu bewerten"}
    leer = _bericht("2026-08-10", highlights=[], redaktion_ausfall=ausfall)
    leer["regions"] = json.loads(
        (reports / "2026-08-01.json").read_text())["regions"]
    leer["run"]["editor_used"] = False
    (reports / "2026-08-10.json").write_text(json.dumps(leer), encoding="utf-8")

    site = tmp_path / "site"
    render_site(site, reports)
    html = (site / "index.html").read_text(encoding="utf-8")

    # Kriterium 1: der alte Aufmacher UND der alte Wochenbericht stehen da.
    assert "Testbetreiber senkt Preis" in html
    assert "Der Testbetreiber hat den Preis gesenkt" in html
    # Kriterium 1 (Stand:) UND 2 (Ehrlichkeit): das Datum der echten
    # Redaktion steht sichtbar, zweimal (Aufmacher-Bereich + Wochenbericht).
    assert html.count("Stand: 1. August 2026") == 2
    assert "es gab in dieser Runde keine neuen Meldungen" in html
    # Und NICHT die alten, ehrlosen Leerzustaende.
    assert "Diese Woche keine priorisierte Meldung" not in html
    assert "Redaktions-Fallback" not in html
    assert "Roh-Digest" not in html


def test_transparenzseite_behauptet_keine_bewertung_die_nicht_stattfand(
        tmp_path):
    """E1: die eine Seite, die "kann ich dem Ding trauen" beantwortet, darf
    die uebernommenen Meldungen nicht als Ausbeute DIESER Runde zeigen."""
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / "2026-08-01.json").write_text(
        json.dumps(_bericht("2026-08-01")), encoding="utf-8")
    ausfall = {"stand": "2026-08-01", "grund": "keine neuen Meldungen"}
    leer = _bericht("2026-08-10", highlights=[], redaktion_ausfall=ausfall)
    leer["regions"] = json.loads(
        (reports / "2026-08-01.json").read_text())["regions"]
    leer["run"]["editor_used"] = False
    leer["stats"]["bewertete"] = 0  # was pipeline.py VOR der Uebernahme setzt
    (reports / "2026-08-10.json").write_text(json.dumps(leer), encoding="utf-8")

    site = tmp_path / "site"
    render_site(site, reports)

    transparenz = (site / "transparenz.html").read_text(encoding="utf-8")
    assert "<b>0</b><span>davon relevant</span>" in transparenz
    assert "<b>1</b><span>davon relevant</span>" not in transparenz

    index = (site / "index.html").read_text(encoding="utf-8")
    # "1 relevante Meldungen aus 12 neuen" waere zwei Zahlen aus zwei
    # verschiedenen Laeufen in einem Satz - die 12 sind von HEUTE (stats.new
    # der Fixture), die uebernommene Meldung ist von der Ausgabe vom 1.8.
    assert "relevante Meldungen</b>" in index
    assert "aus 12 neuen" not in index


def test_normale_woche_zeigt_keinen_ausfall_hinweis(tmp_path):
    """Der Hinweis darf nur bei einer echten Uebernahme erscheinen."""
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / "2026-08-10.json").write_text(
        json.dumps(_bericht("2026-08-10")), encoding="utf-8")
    site = tmp_path / "site"
    render_site(site, reports)
    html = (site / "index.html").read_text(encoding="utf-8")
    assert "ausfall-hinweis" not in html
    meldungen = (site / "meldungen.html").read_text(encoding="utf-8")
    assert "ausfall-hinweis" not in meldungen


def test_meldungenseite_zeigt_die_uebernommene_redaktion_mit_stand(tmp_path):
    """E3B-R2: meldungen.html zeigte dieselbe uebernommene Redaktion wie die
    Titelseite unter der Ueberschrift der HEUTIGEN Ausgabe - ohne jeden
    Alters- oder Ausfallhinweis (die Luecke aus Runde 1). Die Korrektur aus
    Runde 1 war nur auf woche.html.j2 angewendet."""
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / "2026-08-01.json").write_text(
        json.dumps(_bericht("2026-08-01")), encoding="utf-8")
    ausfall = {"stand": "2026-08-01",
               "grund": "es gab in dieser Runde keine neuen Meldungen "
                        "zu bewerten"}
    leer = _bericht("2026-08-10", highlights=[], redaktion_ausfall=ausfall)
    leer["regions"] = json.loads(
        (reports / "2026-08-01.json").read_text())["regions"]
    leer["run"]["editor_used"] = False
    (reports / "2026-08-10.json").write_text(json.dumps(leer), encoding="utf-8")

    site = tmp_path / "site"
    render_site(site, reports)
    meldungen = (site / "meldungen.html").read_text(encoding="utf-8")

    # Die Ueberschrift traegt weiterhin das Datum der HEUTIGEN (leeren) Runde -
    # sie ist keine Falschaussage, solange der Hinweis daneben steht.
    assert "Ausgabe vom 10. August 2026" in meldungen
    assert "Stand: 1. August 2026" in meldungen
    assert "es gab in dieser Runde keine neuen Meldungen" in meldungen
    assert "Testbetreiber senkt Preis" in meldungen


# --------------------------------------------------------------------------- #
# 3. pipeline.run() mit quellen=[] - die im Brief verlangte Simulation
# --------------------------------------------------------------------------- #

@pytest.fixture()
def leeres_projekt(tmp_path, monkeypatch):
    """Eine Projektwurzel ganz ohne Quellen - "quellen=[]"."""
    shutil.copytree(PROJECT_ROOT / "config", tmp_path / "config")
    settings = (tmp_path / "config" / "settings.yaml").read_text(encoding="utf-8")
    settings += (
        "\nfocus_competitors: []\npromo_enabled: false\n"
        "geraete_enabled: false\ncrawl_newsrooms: false\n"
    )
    (tmp_path / "config" / "settings.yaml").write_text(settings, encoding="utf-8")
    (tmp_path / "config" / "watchlist.yaml").write_text(
        "regions: {}\n", encoding="utf-8")
    (tmp_path / "config" / "news_sources.yaml").write_text(
        "news_sources: []\n", encoding="utf-8")
    (tmp_path / "config" / "tech_sources.yaml").write_text(
        "themen: {}\n", encoding="utf-8")
    # Kein API-Schluessel in der Umgebung - die Runde darf keinen echten
    # Netzaufruf machen, auch keinen versehentlichen.
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL",
               "AWS_BEDROCK_REGION"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def test_pipeline_behaelt_redaktion_bei_leerer_quellenliste(leeres_projekt):
    heute = date.today()
    stand = (heute - timedelta(days=5)).isoformat()
    reports_dir = leeres_projekt / "data" / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / f"{stand}.json").write_text(
        json.dumps(_bericht(stand)), encoding="utf-8")

    report_path = pipeline.run(leeres_projekt, use_llm=True, lookback_days=8)

    daten = json.loads(report_path.with_suffix(".json").read_text(
        encoding="utf-8"))
    # Kriterium 3: kein Datenverlust - die alte Ausgabe liegt unveraendert
    # weiter im Archiv.
    alte = json.loads((reports_dir / f"{stand}.json").read_text())
    assert rk.bewertete_meldungen(alte) == 1

    # Die HEUTIGE Runde hat 0 bewertete Meldungen (echte, ehrliche Zahlen)…
    assert daten["stats"]["new"] == 0
    assert daten["run"]["editor_used"] is False
    # … und trotzdem eine Titelseite mit Redaktion, uebernommen mit Hinweis.
    assert daten["redaktion_ausfall"]["stand"] == stand
    assert rk.bewertete_meldungen(daten) == 1

    render_site(leeres_projekt / "site", reports_dir)
    html = (leeres_projekt / "site" / "index.html").read_text(encoding="utf-8")
    assert "Testbetreiber senkt Preis" in html
    assert "Diese Woche keine priorisierte Meldung" not in html
    assert "Roh-Digest" not in html
