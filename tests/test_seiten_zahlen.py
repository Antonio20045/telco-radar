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
    html = _seite(_render(tmp_path), "transparenz.html")

    assert f"<b>{NEU_GESAMMELT}</b><span>neue Meldungen gelesen</span>" in html
    assert f"<b>{len(HIGHLIGHTS)}</b><span>davon relevant</span>" in html
    # Der alte, falsche Text darf nicht zurueckkommen.
    assert f"<b>{NEU_GESAMMELT}</b><span>neue Meldungen bewertet</span>" not in html


def test_protokoll_erklaert_den_abstand_zwischen_den_zahlen(tmp_path):
    html = _seite(_render(tmp_path), "transparenz.html")
    assert "Warum die zweite Zahl kleiner ist" in html


def test_protokoll_erklaert_nichts_wenn_es_nichts_zu_erklaeren_gibt(tmp_path):
    """Gegenprobe: sind beide Zahlen gleich, faellt der Hinweis weg."""
    html = _seite(_render(tmp_path, stats={"new": len(HIGHLIGHTS)}), "transparenz.html")
    assert "Warum die zweite Zahl kleiner ist" not in html


# ------------------------------------------------------------------ Bericht
def test_signalliste_verspricht_nicht_mehr_als_sie_zeigt(tmp_path):
    """Die Ueberschrift muss der Zahl der gerenderten Zeilen entsprechen."""
    html = _seite(_render(tmp_path), "index.html")

    gezeigt = html.count('class="signal-row"')
    m = re.search(r"<h2>Die (\d+) [a-zä]+ Signale</h2>", html)
    assert m, "Ueberschrift der Signalliste fehlt"
    assert int(m.group(1)) == gezeigt, (
        f"Ueberschrift sagt {m.group(1)}, gerendert sind {gezeigt}")

    # Das eigentliche Verbot: keine Ueberschrift, die "alle" behauptet,
    # solange gekappt wird.
    assert gezeigt < len(HIGHLIGHTS)
    assert "Alle Signale dieser Woche" not in html


def test_bericht_verlinkt_die_vollstaendige_liste(tmp_path):
    """Wer gekappt anzeigt, muss den Weg zur vollen Liste zeigen."""
    html = _seite(_render(tmp_path), "index.html")
    assert f"alle {len(HIGHLIGHTS)} Meldungen" in html
    assert "meldungen.html" in html


def test_kopfzeile_nennt_gelesen_und_relevant_getrennt(tmp_path):
    html = _seite(_render(tmp_path), "index.html")
    assert re.search(rf"{NEU_GESAMMELT} neue Meldungen gelesen,\s*"
                     rf"<b>{len(HIGHLIGHTS)} davon relevant</b>", html)


def test_explorer_enthaelt_wirklich_alle_meldungen(tmp_path):
    """Die Zahl in der Ueberschrift muss zu den eingebetteten Daten passen."""
    html = _seite(_render(tmp_path), "meldungen.html")
    daten = json.loads(re.search(r'id="explorer-data">(.*?)</script>', html, re.S).group(1))
    assert len(daten) == len(HIGHLIGHTS)
    assert f"Diese Woche: {len(HIGHLIGHTS)} Meldungen" in html


def test_wochenseite_traegt_die_explorer_daten_nicht_mehr(tmp_path):
    """Der Explorer-JSON war 78,5 KB der 120 KB von bericht.html - fuer
    Daten, die nur sichtbar wurden, wenn jemand ein <details> aufklappte.
    Er gehoert auf meldungen.html, nicht auf die Landeseite."""
    site = _render(tmp_path)
    assert 'id="explorer-data"' not in _seite(site, "index.html")
    assert 'id="explorer-data"' in _seite(site, "meldungen.html")
    # Die Archivwoche hat keine meldungen.html, auf die sie verweisen
    # koennte - sie traegt ihre Meldungen weiter selbst.
    assert 'id="explorer-data"' in _seite(site, "reports/2026-08-05.html")


def test_interne_einordnung_verlaesst_die_seite_nicht(tmp_path):
    """`why_it_matters` ist intern und darf in keiner Seite auftauchen."""
    site = _render(tmp_path)
    for name in ("index.html", "meldungen.html", "search_index.json"):
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
    html = _seite(_render(tmp_path, competitors=GESCHEITERT), "index.html")
    assert "ist gescheitert" in html
    assert "entsteht beim nächsten Lauf" not in html
    # Und die Seite gibt zu, dass die Zuordnung funktioniert hat.
    assert "16 Treffer" in html


def test_vorhandene_profile_zeigen_keinen_leertext(tmp_path):
    """Der Fall, der am 04.08. still verloren ging."""
    html = _seite(_render(tmp_path, competitors=GELUNGEN), "index.html")
    assert "Profiltext." in html
    assert "ist gescheitert" not in html
    assert "liegt noch keine Wettbewerber-Detailanalyse vor" not in html


def test_ohne_profile_kein_leerer_block(tmp_path):
    """Ein Lauf ohne KI hat wirklich nichts - dann faellt der Block weg,
    statt eine leere Ueberschrift zu zeigen."""
    html = _seite(_render(tmp_path, competitors=[]), "index.html")
    assert "Deutschland-Fokus</h2>" not in html
    assert "ist gescheitert" not in html


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


# ------------------------------------------------- Sprungnavigation (Etappe 2)
def test_bericht_bekommt_ein_inhaltsverzeichnis_mit_ankern(tmp_path):
    """2863 Woerter in elf Abschnitten standen als ein Block ohne Einstieg
    da. Jede Ueberschrift braucht einen Anker, damit man aus einer Mail in
    einen Abschnitt verlinken kann."""
    html = _seite(_render(tmp_path), "index.html")

    assert '<nav class="toc"' in html
    # Beide Abschnitte der Fixture ("Auf einen Blick", "Europa") tauchen als
    # Anker UND als Sprungziel auf.
    for titel, anker in (("Auf einen Blick", "auf-einen-blick"), ("Europa", "europa")):
        assert f'href="#{anker}"' in html
        assert f'<h2 id="{anker}">{titel}</h2>' in html


def test_anker_ueberleben_umlaute_und_sonderzeichen(tmp_path):
    from telco_radar.report.html import _slug
    assert _slug("Afrika & Naher Osten") == "afrika-naher-osten"
    assert _slug("Türme, Glasfaser & Rechenzentren") == "tuerme-glasfaser-rechenzentren"
    assert _slug("Technologie, Geräte & Regulierung") == "technologie-geraete-regulierung"
    assert _slug("") == "abschnitt"


def test_gleichnamige_abschnitte_bekommen_verschiedene_anker():
    from telco_radar.report.html import _anchor_headings
    html, toc = _anchor_headings("<h2>Global</h2><p>a</p><h2>Global</h2><p>b</p>")
    assert [s["id"] for s in toc] == ["global", "global-2"]
    assert 'id="global"' in html and 'id="global-2"' in html


def test_lesezeit_wird_genannt(tmp_path):
    html = _seite(_render(tmp_path), "index.html")
    assert "Lesezeit etwa" in html


# ------------------------------------------- Quellenbilanz des Laufprotokolls
QUELLEN = [
    {"name": "A", "url": "https://a.example/f", "kind": "rss", "region": "global",
     "status": "ok", "count": 5, "error": ""},
    {"name": "B", "url": "https://b.example/f", "kind": "rss", "region": "global",
     "status": "empty", "count": 0, "error": ""},
    {"name": "C", "url": "https://c.example/f", "kind": "rss", "region": "global",
     "status": "fail", "count": 0, "error": "HTTPStatusError: 403"},
    {"name": "D", "url": "https://d.example/f", "kind": "rss", "region": "global",
     "status": "fail", "count": 0, "error": "ValueError: unparseable feed"},
    {"name": "E", "url": "https://e.example/f", "kind": "rss", "region": "global",
     "status": "quarantaene", "count": 0, "error": ""},
]


def test_gescheiterte_quellen_werden_gezaehlt(tmp_path):
    """Der fuenfte falsche Wert, gefunden beim Nachrendern am 06.08.2026.

    Das Laufprotokoll schreibt `status: "fail"`, die Zusammenfassung der
    Seite heisst `failed`. Die Neuberechnung im Renderer zaehlte nach
    "failed" und fand nie einen: der Lauf vom 05.08. hatte 6 gescheiterte
    Quellen, die Seite meldete 0 - also ausgerechnet die Zahl, die den
    Bestand gesund aussehen laesst.
    """
    reports = tmp_path / "reports"
    reports.mkdir(parents=True)
    (reports / "2026-08-05.json").write_text(json.dumps({
        "date": "2026-08-05", "generated_with_llm": True,
        "stats": {"new": NEU_GESAMMELT},
        "briefing_md": "## Auf einen Blick\n\nText.",
        "regions": {"Europa": {"region_summary": "", "highlights": HIGHLIGHTS}},
        "competitors": [],
        "run": {"duration_seconds": 60, "models": {"analyst": "m", "editor": "m"},
                "phases": [], "analysts": [], "sources": QUELLEN,
                "source_summary": {}},
    }, ensure_ascii=False), encoding="utf-8")
    site = tmp_path / "site"
    render_site(site, reports)
    html = (site / "transparenz.html").read_text(encoding="utf-8")

    # 1 ok / 1 leer / 2 gescheitert - die Quarantaene zaehlt nicht als
    # abgefragt, sonst sieht die Bilanz besser aus, je mehr Quellen
    # aufgegeben wurden.
    assert "<b>1 / 1 / 2</b><span>ok / leer / fehlgeschlagen</span>" in html
    assert "<b>4</b><span>Quellen abgefragt</span>" in html
    assert "nicht erreichbar (2)" in html


# ------------------------------- Vodafone-Filter: Rat weg, Befund bleibt
def test_ratschlag_faellt_der_befund_im_selben_absatz_bleibt():
    """Der sechste falsche Wert - diesmal ein fehlender.

    Die Regel "die Website berichtet, sie beraet nicht" galt je ABSATZ. Ein
    Absatz enthaelt aber in aller Regel zuerst den Befund und erst am Ende
    die Folgerung. Am Bericht vom 05.08.2026 gemessen verschwanden dadurch
    drei Absaetze mit 77 Woertern, darunter das Gewinnwachstum von MTN
    Nigeria - berichtete Fakten, geloescht wegen des Nachsatzes.
    """
    from telco_radar.report.html import _strip_vodafone_advice

    text = ("MTN Nigeria meldet einen Nettogewinnsprung um 70,6 Prozent. "
            "Vodafone kann diese Entwicklung als Vorbild nutzen.")
    sauber = _strip_vodafone_advice(text)
    assert "70,6 Prozent" in sauber
    assert "Vodafone kann" not in sauber


def test_reiner_ratschlagsabsatz_faellt_ganz_weg():
    from telco_radar.report.html import _strip_vodafone_advice
    assert _strip_vodafone_advice("Für Vodafone heißt das: schneller werden.") == ""


def test_abkuerzungen_zerlegen_den_satz_nicht():
    """"z. B." ist kein Satzende - sonst wuerde die halbe Aussage
    mitgeloescht."""
    from telco_radar.report.html import _strip_vodafone_advice
    text = "Mehrere Betreiber, z. B. Orange, senken Preise. Vodafone sollte reagieren."
    sauber = _strip_vodafone_advice(text)
    assert sauber == "Mehrere Betreiber, z. B. Orange, senken Preise."


def test_absatz_ohne_vodafone_bleibt_unveraendert():
    from telco_radar.report.html import _strip_vodafone_advice
    text = "Orange senkt die Preise.\n\nTelefónica zieht nach."
    assert _strip_vodafone_advice(text) == text


# ------------------------------------------------ Waechter gegen toten Code
def test_dash_liefert_nur_was_die_vorlage_auch_benutzt(tmp_path):
    """Bis zum Redesign berechnete _stats() sechs Werte, die in KEINER
    Vorlage vorkamen (sov, pricing, deals, risks, chances, n_competitors) -
    bei jedem Rendern, fuer jede Archivwoche. Dieser Test haelt den
    Rueckbau fest."""
    from telco_radar.report.html import _flatten, _stats

    report = {"date": "2026-08-05", "stats": {"new": NEU_GESAMMELT},
              "regions": {"Europa": {"highlights": HIGHLIGHTS}},
              "competitors": GELUNGEN}
    dash = _stats(report)
    assert set(dash) == {"kpis", "lead_signal", "tech_radar"}
    assert _flatten(report)  # Gegenprobe: die Fixture ist nicht leer


def test_archivkopie_gibt_sich_als_archiv_zu_erkennen(tmp_path):
    """reports/<datum>.html ist immer eine Archiv-URL - auch fuer die
    neueste Woche. Sonst stehen zwei Seiten mit derselben Ueberschrift
    unter zwei Adressen und die datierte verschweigt, dass sie datiert ist."""
    site = _render(tmp_path)
    archiv = _seite(site, "reports/2026-08-05.html")
    start = _seite(site, "index.html")

    assert "Archivierter Bericht vom 5. August 2026" in archiv
    assert "zur aktuellen Ausgabe" in archiv
    assert "Archivierter Bericht" not in start


# ---------------------------------------------- Titelseite: keine Dubletten
def test_aufmacher_steht_nicht_zweimal_auf_der_titelseite(tmp_path):
    """Der Aufmacher wird fuer die Anzeige kopiert. Wurde er danach ueber
    Objektidentitaet aus den Anreissern gefiltert, stand dieselbe Meldung
    mit demselben Bild ein zweites Mal darunter - gefunden am 06.08.2026."""
    html = _seite(_render(tmp_path), "index.html")

    titel = re.findall(r'<h1>(.*?)</h1>', html, re.S)
    anreisser = re.findall(r'class="anreisser-titel">(.*?)</span>', html, re.S)
    weitere = re.findall(r'class="signal-title">(.*?)</span>', html, re.S)
    alle = [t.strip() for t in titel + anreisser + weitere]
    assert len(alle) == len(set(alle)), f"Doppelte Meldung auf der Titelseite: {alle}"


def test_schlagzeile_bricht_nicht_mitten_im_wort(tmp_path):
    from telco_radar.report.html import _schlagzeile
    lang = {"de_title": "Amazon Leo hat bei der US-Behörde FCC eine Genehmigung "
                        "für ein Direct-to-Device-Satellitennetz mit bis zu 5.105 "
                        "Satelliten beantragt und will 2028 starten"}
    kopf = _schlagzeile(lang)
    assert not kopf.rstrip("…").endswith("5.10"), kopf
    assert kopf.rstrip("…").split()[-1] in lang["de_title"].split()


def test_analystenschlagzeile_gewinnt_gegen_den_fliesstextsatz():
    from telco_radar.report.html import _schlagzeile
    h = {"headline": "Amazon beantragt Satellitennetz mit 5.105 Satelliten",
         "de_title": "Amazon Leo hat bei der US-Behörde FCC eine Genehmigung für ein …"}
    assert _schlagzeile(h) == "Amazon beantragt Satellitennetz mit 5.105 Satelliten"


def test_bilder_alter_wochen_werden_aufgeraeumt(tmp_path):
    """Rund 9 Bilder je Lauf mal zwei Laeufe pro Woche waeren ueber ein Jahr
    etwa 200 MB im Repo. Was kein junger Bericht mehr referenziert, faellt."""
    from telco_radar.report import bilder

    reports = tmp_path / "reports"; reports.mkdir(parents=True)
    (reports / "2026-08-05.json").write_text(json.dumps({
        "date": "2026-08-05", "stats": {}, "briefing_md": "",
        "regions": {"Europa": {"highlights": [dict(_highlight(1, 5), image="behalten.jpg")]}},
    }), encoding="utf-8")
    ordner = bilder.bildordner(tmp_path)
    ordner.mkdir(parents=True)
    (ordner / "behalten.jpg").write_bytes(b"x" * 10)
    (ordner / "verwaist.jpg").write_bytes(b"x" * 10)

    assert bilder.raeume_auf(tmp_path, reports) == 1
    assert (ordner / "behalten.jpg").exists()
    assert not (ordner / "verwaist.jpg").exists()
