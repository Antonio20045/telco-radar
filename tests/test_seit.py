"""„Neu seit der letzten Ausgabe" - die Spalte neben dem Seitenkopf.

Sie schliesst eine gemessene Luecke des Aufmasses vom 08.08.2026: auf
`wettbewerb`, `differenzierung` und `promo` stand im Desktop in einem sonst
leeren Drittel nur "Stand 7. August 2026".

Der teuerste Fehler dieses Bausteins waere ein Sprungziel, das es nicht gibt -
eine Zahl, die anklickbar aussieht und nirgends hinfuehrt. Genau dagegen
steht der letzte Test hier.
"""
from __future__ import annotations

from telco_radar.report import seit


def test_leer_heisst_leer():
    """Eine Zeile "0 neue Beispiele", die jede Woche gleich aussieht, ist
    Rauschen. Dann zeigt die Vorlage wieder nur den Stand."""
    assert seit.fuer_differenzierung({"bestand": []})["zeilen"] == []
    assert seit.fuer_promo({"karten": []})["zeilen"] == []
    assert seit.fuer_wettbewerb({"wettbewerber": []}, "2026-08-08")["zeilen"] == []


def test_differenzierung_zaehlt_neue_beispiele_und_hebel():
    diff = {"bestand": [
        {"neu": True, "theme": "ki"}, {"neu": True, "theme": "ki"},
        {"neu": True, "theme": "gaming"}, {"neu": False, "theme": "loyalty"}]}
    zeilen = seit.fuer_differenzierung(diff)["zeilen"]
    assert zeilen[0]["n"] == 3 and "Beispiele" in zeilen[0]["text"]
    assert zeilen[1]["n"] == 2


def test_einzahl_und_mehrzahl():
    zeilen = seit.fuer_differenzierung(
        {"bestand": [{"neu": True, "theme": "ki"}]})["zeilen"]
    assert zeilen[0]["text"] == "neues Beispiel"


def test_promo_zaehlt_auf_den_angeboten_nicht_auf_den_karten():
    """`neu` und der Status stehen am Angebot; die Karte traegt nur, was sie
    anzeigt. Auf der Karte gezaehlt kam immer 0 heraus."""
    view = {"karten": [
        {"offer": {"neu": True, "status": "aktiv"}},
        {"offer": {"neu": False, "status": "ausgelaufen"}},
        {"offer": {"neu": False, "status": "evtl. ausgelaufen"}},
        {"offer": {"neu": False, "status": "aktiv"}}]}
    zeilen = seit.fuer_promo(view)["zeilen"]
    assert zeilen[0]["n"] == 1
    assert zeilen[1]["n"] == 2


def test_wettbewerb_zaehlt_das_datum_nicht_die_position():
    """Die Chronik reicht ueber das ganze Archiv; ein Eintrag rutscht darin
    nach unten, ohne alt zu werden."""
    view = {"wettbewerber": [
        {"name": "Deutsche Telekom", "monate": [
            {"eintraege": [{"datum": "2026-08-08"}, {"datum": "2026-07-01"}]}]},
        {"name": "O2", "monate": [{"eintraege": [{"datum": "2026-08-08"}]}]},
        {"name": "1&1", "monate": [{"eintraege": [{"datum": "2026-06-02"}]}]}]}
    zeilen = seit.fuer_wettbewerb(view, "2026-08-08")["zeilen"]
    assert zeilen[0]["n"] == 2
    assert zeilen[1]["n"] == 2      # zwei der drei Wettbewerber betroffen


def test_hoechstens_drei_zeilen():
    """Die Spalte steht neben einer Ueberschrift und darf nicht an ihr
    herunterlaufen."""
    viele = [{"n": i, "text": "x", "anker": "#a"} for i in range(9)]
    assert len(seit._zusammen(*viele)["zeilen"]) <= seit.MAX_ZEILEN


def test_jedes_sprungziel_gibt_es_auch(tmp_path):
    """Der teuerste Fehler waere eine Zahl, die anklickbar aussieht und
    nirgends hinfuehrt."""
    import json
    import re
    from bs4 import BeautifulSoup
    from telco_radar.config import load_config
    from telco_radar.report.html import render_site
    from pathlib import Path
    import shutil

    wurzel = Path(__file__).resolve().parents[1]
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / "2026-08-05.json").write_text(json.dumps({
        "date": "2026-08-05", "generated_with_llm": True,
        "stats": {"new": 3}, "briefing_md": "## Auf einen Blick\n\nText.",
        "regions": {"Europa": {"region_summary": "", "highlights": [
            {"title": "Meldung", "url": "https://example.com/1",
             "operator": "Deutsche Telekom", "category": "Tarif/Pricing",
             "relevance": 5, "summary": "Text.", "date": "2026-08-05",
             "source": "Quelle"}]}},
        "competitors": [],
        "run": {"duration_seconds": 60.0, "phases": [], "sources": [],
                "models": {}, "analysts": [],
                "source_summary": {"ok": 1, "empty": 0, "failed": 0}},
    }, ensure_ascii=False), encoding="utf-8")
    shutil.copytree(wurzel / "config", tmp_path / "config")
    site = tmp_path / "site"
    render_site(site, reports, load_config(tmp_path))

    for datei in ("differenzierung.html", "wettbewerb.html",
                  "promo/index.html"):
        pfad = site / datei
        if not pfad.exists():
            continue
        soup = BeautifulSoup(pfad.read_text(encoding="utf-8"), "html.parser")
        ids = {e.get("id") for e in soup.select("[id]")}
        for a in soup.select(".seit-liste a"):
            ziel = (a.get("href") or "").lstrip("#")
            assert ziel in ids, f"{datei}: #{ziel} gibt es nicht"
