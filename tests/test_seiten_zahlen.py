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
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from telco_radar.report.geraete_export import (
    SPALTE_UEBER_24, SPALTE_UEBER_LAUFZEIT, leitzahl_aus_zeile)
from telco_radar.report.html import render_site


def _highlight(i: int, relevance: int, category: str = "Netz/Technologie",
               image_w: int = 0) -> dict:
    h = {
        "title": f"Meldung {i}",
        "operator": f"Betreiber {i}",
        "url": f"https://example.com/{i}",
        "category": category,
        "relevance": relevance,
        "summary": f"Zusammenfassung der Meldung {i}.",
        "why_it_matters": "Interne Einordnung.",
        "date": "2026-08-05",
        "source": "Beispielquelle",
    }
    if image_w:
        h |= {"image": f"bild{i}.jpg", "image_w": image_w,
              "image_h": round(image_w * 9 / 16)}
    return h


# 12 relevante Meldungen, davon 8 mit relevance >= 4: mehr als der Deckel von
# sechs, den html.py auf die Signalliste legt - sonst wuerde der Test die
# Kappung gar nicht sehen.
HIGHLIGHTS = ([_highlight(i, 5) for i in range(4)]
              + [_highlight(i, 4) for i in range(4, 8)]
              + [_highlight(i, 3) for i in range(8, 12)])
NEU_GESAMMELT = 426

# Eine Ausgabe in der Groessenordnung einer echten (193 Meldungen am
# 06.08.2026): genug Meldungen fuer alle vier Gewichtsstufen der Titelseite
# UND fuer Ressortbloecke danach. Mit den zwoelf oben ist die Titelseite
# schon vor den Ressorts leergeraeumt - dann pruefte kein Test das Raster.
KATEGORIEN = ["Netz/Technologie", "Tarif/Pricing", "Regulierung", "M&A",
              "Partnerschaft", "Sonstiges", "Finanzen", "Produktlaunch"]
PORTAL = [
    _highlight(100 + i, 5 - (i % 3), KATEGORIEN[i % len(KATEGORIEN)],
               # jede zweite Meldung mit Bild, davon jede vierte zu klein
               # fuer eine grosse Position - genau die Mischung, in der sich
               # die Auswahl bewaehren muss
               image_w=(0 if i % 2 else (520 if i % 4 == 2 else 1200)))
    for i in range(48)
]


BRIEFING = "## Auf einen Blick\n\nText.\n\n## Europa\n\nMehr Text."


def _render(tmp_path, *, competitors=None, stats=None, highlights=None,
            bilder_anlegen=True, briefing=None, kosten=None):
    from telco_radar.report.bilder import bildordner

    # data/reports/ wie im echten Projekt: render_site() leitet den
    # Bildordner ueber `reports_dir.parent.parent` her. Lag der Bericht flach
    # unter tmp_path, zeigte das auf das GEMEINSAME pytest-Wurzelverzeichnis -
    # und ein Test sah die Bilddateien eines anderen.
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True)
    hs = HIGHLIGHTS if highlights is None else highlights
    run = {"duration_seconds": 1487.8, "models": {"analyst": "m", "editor": "m"},
           "phases": [],
           "analysts": [{"region": "Europa", "items_in": 15,
                         "highlights": 4, "model": "m"}],
           "sources": [],
           "source_summary": {"ok": 1, "empty": 0, "failed": 0}}
    if kosten is not None:
        run["kosten"] = kosten
    # Die Bilddateien muessen wirklich existieren: render_site() streicht
    # jeden `image`-Verweis, zu dem keine Datei mehr im Bildordner liegt
    # (sonst zeigen Archivwochen leere Kaesten, nachdem raeume_auf() ihre
    # Bilder geloescht hat). Ohne diese Dateien pruefte der Bildtest unten
    # eine Seite ganz ohne Bilder - also nichts.
    if bilder_anlegen:
        ordner = bildordner(reports.parent.parent)
        ordner.mkdir(parents=True, exist_ok=True)
        for h in hs:
            if h.get("image"):
                (ordner / h["image"]).write_bytes(b"nicht wirklich ein Bild")
    (reports / "2026-08-05.json").write_text(json.dumps({
        "date": "2026-08-05",
        "generated_with_llm": True,
        "stats": stats if stats is not None else {"new": NEU_GESAMMELT},
        "briefing_md": BRIEFING if briefing is None else briefing,
        "regions": {"Europa": {"region_summary": "", "highlights": hs}},
        "competitors": competitors if competitors is not None else [],
        "run": run,
    }, ensure_ascii=False), encoding="utf-8")
    site = tmp_path / "site"
    render_site(site, reports)
    return site


def _schlagzeilen(html: str, wurzel: str = "") -> list[str]:
    """Alle Schlagzeilen einer Seite, ueber die Klasse `szl`.

    Vorher listete jeder Test vier Regexe fuer vier Vorlagenklassen auf. Wer
    eine fuenfte Position ergaenzte, fiel damit still aus der Pruefung
    heraus - und genau so kam am 06.08.2026 eine doppelte Meldung auf die
    Titelseite. Jetzt traegt jede Schlagzeile in jeder Vorlage `szl`, und
    diese Funktion findet sie alle.
    """
    soup = BeautifulSoup(html, "html.parser")
    bereich = soup.select_one(wurzel) if wurzel else soup
    if bereich is None:
        return []
    return [e.get_text(" ", strip=True) for e in bereich.select(".szl")]


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
    assert "gekappt wird nichts" in html


def test_protokoll_erklaert_nichts_wenn_es_nichts_zu_erklaeren_gibt(tmp_path):
    """Gegenprobe: sind beide Zahlen gleich, faellt der Hinweis weg."""
    html = _seite(_render(tmp_path, stats={"new": len(HIGHLIGHTS)}), "transparenz.html")
    assert "gekappt wird nichts" not in html


# ------------------------------------------------------------------ Kosten
# Antonio zahlt die API privat. Bis zum 27.08.2026 stand nirgends, was ein
# Lauf verbraucht - der Lauf vom 27.08. kostete 1,95 $, und es war hinterher
# nicht zu sagen, an welcher Stufe.
KOSTEN = {
    "modelle": {
        "deepseek-v4-flash": {"aufrufe": 66, "prompt_tokens": 1_200_000,
                              "completion_tokens": 300_000, "usd": 0.252},
        "unbekanntes-modell": {"aufrufe": 3, "prompt_tokens": 900,
                               "completion_tokens": 400, "usd": None},
    },
    "summe_usd": 0.252,
    "ohne_preis": ["unbekanntes-modell"],
    "budget_usd": 1.5,
    "budget_ueberschritten": False,
}


def test_transparenz_nennt_kosten_und_token_je_modell(tmp_path):
    html = _seite(_render(tmp_path, kosten=KOSTEN), "transparenz.html")

    assert "deepseek-v4-flash" in html
    assert "66" in html
    assert "1.200.000" in html and "300.000" in html
    assert "0.25 $" in html
    assert "1.50 $" in html          # die Erwartung je Lauf


def test_transparenz_beziffert_ein_modell_ohne_preis_nicht(tmp_path):
    """Geraten wird nichts - die Luecke wird benannt."""
    html = _seite(_render(tmp_path, kosten=KOSTEN), "transparenz.html")
    assert "nicht beziffert" in html
    assert "unbekanntes-modell" in html


def test_transparenz_sagt_wenn_der_lauf_teurer_war_als_erwartet(tmp_path):
    """Und im selben Atemzug, dass deshalb nichts gekuerzt wurde - der
    Zaehler warnt, er greift nicht ein (Antonio, 27.08.2026)."""
    teuer = {**KOSTEN, "summe_usd": 1.93, "budget_ueberschritten": True}
    html = _seite(_render(tmp_path, kosten=teuer), "transparenz.html")
    assert "Dieser Lauf lag darüber" in html
    assert "Gekürzt wurde deswegen nichts" in html


def test_ein_lauf_im_rahmen_meldet_keine_ueberschreitung(tmp_path):
    """Gegenprobe zum Test darueber - sonst prueft er nur, dass irgendein
    Satz auf der Seite steht."""
    html = _seite(_render(tmp_path, kosten=KOSTEN), "transparenz.html")
    assert "Dieser Lauf lag darüber" not in html


def test_ohne_kostenblock_bleibt_die_seite_wie_vorher(tmp_path):
    """Archivberichte von vor dem 27.08.2026 tragen kein `run.kosten`."""
    html = _seite(_render(tmp_path), "transparenz.html")
    assert "Was dieser Lauf verbraucht hat" not in html


# ------------------------------------------------------------------- Promo
# E10b (27.08.2026, Strategie 2026-08-27 B6): der Promo-Ausfall seit dem
# 14.08.2026 (LLM-Extraktion scheiterte an leerem API-Guthaben) stand bis
# dahin in KEINER Statistik - `stats` kannte kein `promo_*`-Feld, nur das
# Actions-Log, das niemand liest.
PROMO_STATS = {"new": NEU_GESAMMELT, "promo_seiten_gelesen": 41,
              "promo_angebote_neu": 7, "promo_angebote_bestaetigt": 62,
              "promo_extraktion_fehler": 3}


def test_transparenz_nennt_die_promo_zahlen(tmp_path):
    html = _seite(_render(tmp_path, stats=PROMO_STATS), "transparenz.html")
    assert "41 Aktionsseiten gelesen" in html
    assert "7 Angebote neu aufgenommen" in html
    assert "62 bestätigt" in html
    assert "3 Seiten mit gescheiterter Extraktion" in html


def test_transparenz_trennt_neue_und_bestaetigte_angebote(tmp_path):
    """Der Befund vom 27.08.2026: gezaehlt wurden nur die NEUEN Angebote, das
    Etikett sagte "aktualisiert". Eine ruhige Woche (nichts neu, siebzig
    bestaetigt) las sich damit wie ein stiller Totalausfall der Extraktion.
    Gegen den alten Stand faellt dieser Test."""
    ruhig = {**PROMO_STATS, "promo_angebote_neu": 0,
             "promo_angebote_bestaetigt": 70, "promo_extraktion_fehler": 0}
    html = _seite(_render(tmp_path, stats=ruhig), "transparenz.html")
    assert "0 Angebote neu aufgenommen" in html
    assert "70 bestätigt" in html


def test_transparenz_verschweigt_null_extraktionsfehler(tmp_path):
    """Gegenprobe: ohne Fehler faellt der Halbsatz weg, statt eine "0" zu
    zeigen, die niemand einordnen kann."""
    ohne_fehler = {**PROMO_STATS, "promo_extraktion_fehler": 0}
    html = _seite(_render(tmp_path, stats=ohne_fehler), "transparenz.html")
    assert "gescheiterter Extraktion" not in html
    assert "41 Aktionsseiten gelesen" in html   # der Rest der Zeile bleibt


def test_ohne_promo_stats_bleibt_die_seite_wie_vorher(tmp_path):
    """Archivberichte von vor dem 27.08.2026 tragen kein `promo_*`-Feld -
    dieselbe Zusicherung wie beim Kostenblock direkt darueber."""
    html = _seite(_render(tmp_path), "transparenz.html")
    assert "Aktionsseiten gelesen" not in html


# ------------------------------------------------------------------ Bericht
def test_die_titelseite_traegt_die_ressortbloecke_nicht_mehr(tmp_path):
    """Antonio am 07.08.2026: "die haben genau das Gleiche, habe ich ja auf
    der naechsten Unterseite bei Meldungen. Das ist unnoetig, das ist doppelt
    gemoppelt."

    Bis dahin standen zwischen dem Ueberblick und dem Bericht sechs
    Ressortbloecke - dieselben Ressorts, dieselben Ueberschriften, dieselbe
    Quelle wie auf meldungen.html, nur als Teilmenge. Der Test haelt beides
    fest: die Bloecke sind weg UND keine Meldung ist dabei verloren
    gegangen, sie stehen weiterhin vollstaendig auf der Meldungsseite.
    """
    from telco_radar.report.html import _flatten, _nach_ressort, _titelseite

    site = _render(tmp_path, highlights=PORTAL)
    soup = BeautifulSoup(_seite(site, "index.html"), "html.parser")
    assert not soup.select(".ressort-raster"), "Ressortraster noch auf der Titelseite"
    assert not soup.select(".ressort"), "Ressortbloecke noch auf der Titelseite"
    assert "Alle Signale dieser Woche" not in _seite(site, "index.html")

    # Die Gliederung selbst ist nicht verschwunden - sie steht dort, wo die
    # Frage nach der Einzelmeldung gestellt wird, und dort vollstaendig.
    bericht = json.loads((tmp_path / "data" / "reports" / "2026-08-05.json")
                         .read_text(encoding="utf-8"))
    echt = _nach_ressort(_flatten(bericht))
    meldungen = BeautifulSoup(_seite(site, "meldungen.html"), "html.parser")
    assert len(meldungen.select(".mressort")) == len(echt)
    assert len(meldungen.select(".mressort .meldung")) == len(PORTAL)

    # Und keine tote Rechnung zurueckgelassen: was keine Vorlage mehr liest,
    # wird auch nicht mehr berechnet (dieselbe Regel wie bei der
    # Datumszeile - diese Codebasis hat schon einmal sechs solcher Werte
    # mitgeschleppt).
    assert "ressorts" not in _titelseite(_flatten(bericht))
    assert ".ressort-raster" not in _seite(site, "style.css")


def test_oberhalb_der_falz_stehen_mindestens_sechs_geschichten(tmp_path):
    """Abnahmekriterium 1 des Auftrags, als Test.

    Bis zum 06.08.2026 standen dort vier: ein Aufmacher und drei gleich
    grosse Anreisser. Das war der Kern von Antonios Befund - eine
    Titelseite mit vier Geschichten ist keine.
    """
    html = _seite(_render(tmp_path, highlights=PORTAL), "index.html")
    oben = _schlagzeilen(html, ".front-oben")
    assert len(oben) >= 6, f"Nur {len(oben)} Geschichten oberhalb der Falz"


def test_kein_kleines_bild_in_einer_grossen_position(tmp_path):
    """Abnahmekriterium 3: kein Bild im Aufmacher oder in der zweiten Reihe
    unter 800 px Breite.

    Am 06.08.2026 war der Aufmacher der Ausgabe ein 120x90-Vorschaubild aus
    einem Feed, auf rund 620 px hochskaliert. Die Ursache war die Auswahl
    ("Feed-Bild zuerst"), aber die Seite muss sich auch dann wehren, wenn
    die Beschaffung wieder etwas Kleines liefert.
    """
    from telco_radar.report.bilder import MIND_BREITE_GROSS

    site = _render(tmp_path, highlights=PORTAL)
    soup = BeautifulSoup(_seite(site, "index.html"), "html.parser")
    gross = soup.select(".aufmacher-bild img, .reihe-zwei .stueck-bild img")
    assert gross, "Weder Aufmacher noch zweite Reihe tragen ein Bild"
    for img in gross:
        breite = int(img.get("width") or 0)
        assert breite >= MIND_BREITE_GROSS, (
            f"Bild mit {breite} px in einer grossen Position "
            f"({img.get('src')})")


def test_geloeschtes_bild_hinterlaesst_keinen_leeren_kasten(tmp_path):
    """Eine Berichtsdatei behaelt ihre `image`-Verweise fuer immer, der
    Bildordner nicht: `raeume_auf()` loescht die Bilder aelterer Ausgaben.
    Jede Archivwoche jenseits der Aufbewahrungsfrist zeigte dadurch leere
    Bildkaesten - gefunden am 06.08.2026 an reports/2026-08-05.html."""
    site = _render(tmp_path, highlights=PORTAL, bilder_anlegen=False)
    for name in ("index.html", "meldungen.html", "reports/2026-08-05.html"):
        html = _seite(site, name)
        assert "images/bild" not in html, f"{name} verweist auf ein fehlendes Bild"
    # Gegenprobe: mit vorhandenen Dateien stehen die Bilder auch da.
    assert "images/bild" in _seite(_render(tmp_path / "mit", highlights=PORTAL),
                                   "index.html")


def test_site_images_sammelt_nicht(tmp_path):
    """site/images/ spiegelt den Bildordner, es sammelt nicht.

    Bis zum 06.08.2026 wurde dorthin nur kopiert und nie geloescht.
    `raeume_auf()` beschnitt den Zwischenspeicher, site/images/ behielt
    jedes je geladene Bild - bei rund 130 Bildern je Lauf und zwei Laeufen
    pro Woche waeren das mehrere Gigabyte im Jahr, fuer Bilder, auf die
    keine Seite mehr zeigt."""
    from telco_radar.report.bilder import bildordner

    site = _render(tmp_path, highlights=PORTAL)
    (site / "images" / "aus-einem-alten-lauf.jpg").write_bytes(b"alt")
    # Zweiter Renderlauf mit unveraendertem Bildordner.
    render_site(site, tmp_path / "data" / "reports")

    assert not (site / "images" / "aus-einem-alten-lauf.jpg").exists()
    assert {p.name for p in (site / "images").iterdir()} == \
        {p.name for p in bildordner(tmp_path).iterdir()}


def test_jede_meldung_bekommt_genau_ein_ressort():
    """Ohne diese Zusicherung faellt beim Gruppieren still etwas heraus."""
    from telco_radar.report.html import _flatten, _nach_ressort

    bericht = {"date": "2026-08-05", "stats": {},
               "regions": {"Europa": {"highlights": PORTAL}}}
    highlights = _flatten(bericht)
    verteilt = sum(r["n"] for r in _nach_ressort(highlights))
    assert verteilt == len(highlights)
    assert all(h.get("ressort") and h.get("ressort_label") for h in highlights)


def test_bericht_verlinkt_die_vollstaendige_liste(tmp_path):
    """Wer gekappt anzeigt, muss den Weg zur vollen Liste zeigen."""
    html = _seite(_render(tmp_path), "index.html")
    assert f"alle {len(HIGHLIGHTS)} Meldungen" in html
    assert "meldungen.html" in html


def test_kopfzeile_nennt_gelesen_und_relevant_getrennt(tmp_path):
    """Ein Halbsatz mit zwei Zahlen - beide muessen stimmen.

    Bis zum 08.08.2026 waren es drei Saetze mit vier Zahlen ("... Davon 13
    zum sofortigen Ansehen (5/5). Lesezeit etwa 16 Minuten."); die dritte
    Zahl stand an jeder betroffenen Meldung noch einmal als Prioritaet."""
    html = _seite(_render(tmp_path), "index.html")
    assert re.search(rf"<b>{len(HIGHLIGHTS)} relevante Meldungen</b>\s*"
                     rf"aus {NEU_GESAMMELT} neuen", html)


def test_meldungsseite_zeigt_wirklich_alle_meldungen(tmp_path):
    """Keine Meldung darf beim Umbau verschwinden.

    Seit dem 07.08.2026 stehen die Ressortbloecke in einem <details>: oben
    die Uebersicht, die Tiefe auf Klick. Zugeklappt heisst NICHT weg - die
    Belegebene ist Antonios ausdrueckliche Anforderung (CLAUDE.md §8), und
    alle Meldungen stehen vollstaendig im Quelltext, also auch im Suchlauf
    des Browsers.

    Gezaehlt wird ueber die Klasse `meldung`, die jede der drei
    Gewichtungen traegt (Ressortaufmacher, mittel, Zeile). Vorher lief die
    Zaehlung ueber `data-such` - ein Attribut, das es nur fuer den
    inzwischen entfernten Filter gab."""
    site = _render(tmp_path, highlights=PORTAL)
    soup = BeautifulSoup(_seite(site, "meldungen.html"), "html.parser")
    assert len(soup.select(".mressort .meldung")) == len(PORTAL)
    # Die Gesamtzahl steht seit dem 08.08.2026 nicht mehr als Satz im Kopf
    # ("138 Meldungen in 7 Ressorts ..."), sondern nur noch verteilt an den
    # Ressorts. Auch verteilt muss sie aufgehen.
    aus_ressorts = [int(re.search(r"\d+", z.get_text(" ", strip=True)).group())
                    for z in soup.select(".mressort > summary .rubrik-zahl")]
    assert sum(aus_ressorts) == len(PORTAL)


def test_meldungsseite_zeigt_jedes_ressort_in_der_uebersicht(tmp_path):
    """Abnahmekriterium 3: erst die Ressorts, dann auf Klick die Tiefe.

    Die Seite war 12 249 px hoch; wer wissen wollte, was unter "Geld &
    Uebernahmen" steht, scrollte acht Bildschirmhoehen. Jetzt hat jedes
    Ressort eine Uebersichtskachel mit zwei bis drei Meldungen und EINEN
    Weg in die Tiefe. Die Pixelmessung dazu macht scripts/pruefe_portal.py
    im echten Browser; dieser Test haelt die Struktur fest, die sie
    voraussetzt."""
    from telco_radar.report.html import _flatten, _nach_ressort

    site = _render(tmp_path, highlights=PORTAL)
    soup = BeautifulSoup(_seite(site, "meldungen.html"), "html.parser")
    bericht = json.loads((tmp_path / "data" / "reports" / "2026-08-05.json")
                         .read_text(encoding="utf-8"))
    echt = _nach_ressort(_flatten(bericht))

    kacheln = soup.select(".rkachel")
    assert len(kacheln) == len(echt), "Nicht jedes Ressort hat eine Kachel"
    for kachel, r in zip(kacheln, echt):
        assert kachel.select_one(".rubrik h2").get_text(strip=True) == r["label"]
        # Zwei bis drei Meldungen je Kachel - ein Etikett allein waere ein
        # Inhaltsverzeichnis, keine Uebersicht.
        stuecke = kachel.select(".rk-stueck")
        assert 2 <= len(stuecke) <= 3 or len(stuecke) == r["n"], (
            f"{r['label']}: {len(stuecke)} Meldungen in der Kachel")
        # ... und genau EINE Geste in die Tiefe.
        alle = kachel.select("a.rkachel-alle")
        assert len(alle) == 1
        assert alle[0]["href"] == f"#ressort-{r['key']}"
        assert soup.select_one(f"details#ressort-{r['key']}") is not None


def test_meldungsseite_traegt_den_entfernten_filter_nicht_mehr(tmp_path):
    """Abnahmekriterium 2: der Filter neben "Alle Meldungen" ist weg - samt
    allem, was nur ihm diente. Ein toter Filterrest ist genau die Sorte
    Ballast, die diese Codebasis schon einmal jahrelang mitgeschleppt hat."""
    site = _render(tmp_path, highlights=PORTAL)
    html = _seite(site, "meldungen.html")
    for rest in ("data-such", "meldung-filter", "meldung-leer", "meldung-zahl",
                 "ressort-nav"):
        assert rest not in html, f"Rest des Filters auf der Seite: {rest}"
    assert rest not in _seite(site, "app.js")
    # Die wochenuebergreifende Suche stand hier bis zum 08.08.2026 ganz
    # unten. Sie ist nicht geloescht, sondern eine eigene Seite geworden
    # (suche.html, als Dossier gebaut - siehe tests/test_suche_page.py):
    # das Topbar-Formular fuehrte auf diese Seite, und die Treffer standen
    # nach rund 2400 px. Antonio: "Ich verstehe nicht, warum ich da
    # weitergeleitet werde."
    assert "suche-input" not in html
    assert 'action="suche.html"' in html


def test_meldungsseite_gruppiert_und_gewichtet(tmp_path):
    """Abnahmekriterium 4: Ressorts statt einer flachen Liste, und innerhalb
    eines Ressorts drei Groessen statt einer.

    Vorher rendete die Seite 193-mal denselben Block. Antonio nannte das
    "extrem beschissenes Layout" - zu Recht, das war eine Datenbankausgabe.
    """
    soup = BeautifulSoup(
        _seite(_render(tmp_path, highlights=PORTAL), "meldungen.html"),
        "html.parser")

    ressorts = soup.select(".mressort")
    assert len(ressorts) >= 3, "Die Seite ist nicht nach Ressorts gegliedert"
    assert all(sec.name == "details" for sec in ressorts), (
        "Die Ressortbloecke sind nicht aufklappbar")
    # Jedes Ressort fuehrt mit genau einem Aufmacher ...
    for sec in ressorts:
        assert len(sec.select(".mlead")) == 1
    # ... und mindestens eines nutzt alle drei Gewichtungen.
    assert any(sec.select(".mlead") and sec.select(".mzwei") and sec.select(".mz")
               for sec in ressorts)
    # Die Ressortzahlen der Uebersicht summieren sich auf die Gesamtzahl.
    # (Bis zum 07.08.2026 stand diese Zahl in einer Sprungleiste; die war
    # die Kruecke einer zu langen Seite und ist mit ihr weggefallen. Seit
    # dem 08.08.2026 steht sie EINMAL je Kachel, im Link darunter - vorher
    # einmal als Chip neben der Rubrik und ein zweites Mal im Link.)
    links = soup.select(".rkachel .rkachel-alle")
    assert len(links) == len(soup.select(".rkachel"))
    aus_kacheln = [int(re.search(r"\d+", a.get_text(" ", strip=True)).group())
                   for a in links]
    assert sum(aus_kacheln) == len(PORTAL)
    assert not soup.select(".rkachel .rubrik-zahl"), (
        "Die Ressortzahl steht wieder zweimal in derselben Kachel")


def test_wochenseite_traegt_die_explorer_daten_nicht_mehr(tmp_path):
    """Der Explorer-JSON war 78,5 KB der 120 KB von bericht.html - fuer
    Daten, die nur sichtbar wurden, wenn jemand ein <details> aufklappte.
    Er gehoert auf meldungen.html, nicht auf die Landeseite."""
    site = _render(tmp_path)
    assert 'id="explorer-data"' not in _seite(site, "index.html")
    # Die Meldungsseite rendert die Meldungen serverseitig als Zeitungsseite,
    # der Explorer lebt nur noch auf den Archivwochen.
    assert 'id="explorer-data"' not in _seite(site, "meldungen.html")
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


def test_mechanik_stufen_haben_ein_eigenes_guenstiges_modell():
    """Kostensenkung vom 18.08.2026: v4-pro schreibt je Aufruf ~8-9k Token
    Denkspur - bei 150+ Aufrufen je Lauf der groesste Kostenposten. Die
    Mechanik-Stufen (Uebersetzung, Clustering-/Beleg-Pruefung, Promo-
    Extraktion, Sweep, CT-Radar, Diff-Kurator) laufen deshalb auf einem
    eigenen Modell; fehlt der Eintrag, verhaelt sich der Anbieter exakt wie
    vorher (Rueckfall auf das uebergebene Modell - der Anthropic-Pfad ist
    unveraendert)."""
    from telco_radar.pipeline import _mechanik_modell

    settings = {"deepseek_mechanik_model": "deepseek-v4-flash"}
    assert _mechanik_modell(settings, "deepseek", "deepseek-v4-pro") == "deepseek-v4-flash"
    assert _mechanik_modell(settings, "anthropic", "claude-sonnet-5") == "claude-sonnet-5"
    assert _mechanik_modell({}, "deepseek", "deepseek-v4-pro") == "deepseek-v4-pro"
    # Und die echte Konfiguration traegt den Eintrag wirklich - eine Zahl
    # in der Doku ist erst wahr, wenn ein Test sie gegen die Daten haelt.
    import yaml
    from pathlib import Path
    echte = yaml.safe_load(Path("config/settings.yaml").read_text(encoding="utf-8"))
    assert echte.get("deepseek_mechanik_model") == "deepseek-v4-flash"


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
    assert "Lesezeit ca." in html


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
    Rueckbau fest.

    Am 07.08.2026 ist die naechste Schicht gefallen: `kpis` (die Kachelreihe
    "Zahlen der Woche", deren Werte im selben Bildschirm ein zweites Mal
    standen) und `lead_signal` (seit Monaten berechnet, von keiner Vorlage
    je gelesen).

    Am 08.08.2026 der Rest: `sofort` (mit dem dritten Satz der Berichtszeile
    weggefallen) sowie `ops_top` und `ex` je Radareintrag - beide seit jeher
    berechnet, nie gerendert. Der Radar zeigt Name, Zahl und Balken."""
    from telco_radar.report.html import _flatten, _stats

    report = {"date": "2026-08-05", "stats": {"new": NEU_GESAMMELT},
              "regions": {"Europa": {"highlights": HIGHLIGHTS}},
              "competitors": GELUNGEN}
    dash = _stats(report)
    assert set(dash) == {"tech_radar"}
    assert all(set(t) == {"theme", "n", "w"} for t in dash["tech_radar"])
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
@pytest.mark.parametrize("hs", [HIGHLIGHTS, PORTAL], ids=["klein", "portal"])
def test_keine_meldung_steht_zweimal_auf_der_titelseite(tmp_path, hs):
    """Der Aufmacher wird fuer die Anzeige kopiert. Wurde er danach ueber
    Objektidentitaet aus den Anreissern gefiltert, stand dieselbe Meldung
    mit demselben Bild ein zweites Mal darunter - gefunden am 06.08.2026.

    Geprueft wird ueber die Klasse `szl`, also ueber ALLE Positionen der
    Seite: Aufmacher, zweite und dritte Reihe, "Was wichtig ist" und jeden
    Ressortblock. Die alte Fassung listete vier Regexe auf und haette einen
    fuenften Platz stillschweigend uebersehen.
    """
    alle = _schlagzeilen(_seite(_render(tmp_path, highlights=hs), "index.html"))
    doppelt = {t for t in alle if alle.count(t) > 1}
    assert not doppelt, f"Doppelte Meldung auf der Titelseite: {doppelt}"


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


def test_keine_ueberschrift_ist_abgeschnitten(tmp_path):
    """Der Kern der Kritik vom 06.08.2026: auf der Titelseite standen
    Ueberschriften, die mitten im Satz mit "…" aufhoerten - der Leser
    erfuhr nicht, worum es geht. Keine Ueberschrift darf so enden.

    Ueber `szl` gilt das jetzt fuer jede Position beider Seiten, nicht nur
    fuer die vier, die jemand einmal in ein Regex geschrieben hat."""
    site = _render(tmp_path, highlights=PORTAL)
    for seite in ("index.html", "meldungen.html"):
        gefunden = _schlagzeilen(_seite(site, seite))
        assert gefunden, f"{seite} traegt keine erkennbare Schlagzeile"
        for treffer in gefunden:
            assert not treffer.endswith("…"), (
                f"Abgeschnittene Ueberschrift auf {seite}: {treffer[:70]}")


def test_satztrenner_bricht_nicht_an_einer_datumszahl():
    """"AST SpaceMobile hat am 5. August 2026 drei Satelliten gestartet"
    endete im Anriss der zweiten Reihe nach vier Woertern: "hat am 5."
    Ordnungszahlen sind im Deutschen keine Satzenden."""
    from telco_radar.report.html import _first_sentence

    text = ("AST SpaceMobile hat am 5. August 2026 drei Satelliten gestartet. "
            "Der naechste Start folgt.")
    assert _first_sentence(text, 150) == (
        "AST SpaceMobile hat am 5. August 2026 drei Satelliten gestartet.")
    # Gegenprobe: ein echtes Satzende wird weiterhin erkannt.
    assert _first_sentence("Erster Satz. Zweiter Satz.", 150) == "Erster Satz."


def test_platzhalter_im_betreiberfeld_erscheint_nicht_als_absender():
    """Der Analyst traegt bei branchenweiten Meldungen "kein spezifischer
    Betreiber" ein. Ueber einer Titelseiten-Schlagzeile gelesen ist das kein
    Absender - dann steht dort die Quelle."""
    from telco_radar.report.html import _flatten

    bericht = {"date": "2026-08-05", "stats": {}, "regions": {"Global": {
        "highlights": [dict(_highlight(1, 5), operator="kein spezifischer Betreiber"),
                       dict(_highlight(2, 5), operator="Branche"),
                       dict(_highlight(3, 5), operator="Deutsche Telekom")]}}}
    ops = [h["operator"] for h in _flatten(bericht)]
    assert ops.count("") == 2
    assert "Deutsche Telekom" in ops


def test_originalueberschrift_schlaegt_den_gekuerzten_satz():
    """Vollstaendig und aussagekraeftig schlaegt deutsch und abgehackt."""
    from telco_radar.report.html import _schlagzeile
    h = {"title": "UK ISP Hey! Broadband Launch New Bundles with 6 Months Half Price",
         "de_title": "Der britische Glasfaser-Anbieter Hey! Broadband bringt drei neue…"}
    assert _schlagzeile(h) == "UK ISP Hey! Broadband Launch New Bundles with 6 Months Half Price"


def test_teilausfall_der_wettbewerber_wird_benannt(tmp_path):
    """Ein Profil da, zwei gescheitert darf nicht aussehen wie ein
    kleineres Wettbewerbsfeld - genau so sah es im Lauf vom 06.08.2026 aus,
    als zwei von drei Profilen am Token-Budget scheiterten."""
    gemischt = [
        dict(GELUNGEN[0]),
        {"name": "Telefónica / O2", "n_items": 12, "moves": [], "summary": "",
         "themes": [], "vodafone_implication": "", "error": "JSONDecodeError"},
        {"name": "1&1", "n_items": 8, "moves": [], "summary": "",
         "themes": [], "vodafone_implication": "", "error": "JSONDecodeError"},
    ]
    html = _seite(_render(tmp_path, competitors=gemischt), "index.html")
    assert "Profiltext." in html                      # das gelungene Profil
    assert "Telefónica / O2 und 1&amp;1" in html      # die gescheiterten
    assert "2 von 3 Profilen" in html


def test_wettbewerber_bekommen_budget_fuer_ein_reasoning_modell():
    """3500 Token reichten unter flash, unter pro nicht: das Nachdenken
    zaehlt gegen max_tokens, und was uebrig bleibt, reicht nicht fuer das
    JSON. Abgerechnet werden erzeugte Token, ein hohes Limit kostet nichts."""
    from telco_radar.analyze.competitors import COMPETITOR_MAX_TOKENS
    assert COMPETITOR_MAX_TOKENS >= 8000


# ------------------------------------------------------- Der rote Faden
# Antonio am 07.08.2026: "der rote Faden fehlt mir noch ueberall." Die
# Titelseite sortierte nach Dringlichkeit, der Bericht nach dem Urteil der
# Chefredaktion - beide fuehrten mit einer anderen Geschichte. Die Kopplung
# ist jetzt gebaut, also gehoert sie auch gehalten.
FADEN_BRIEFING = """## Auf einen Blick
- Quasarnetz kuendigt ein Kleinzellennetz an und greift damit die
  etablierten Mobilfunker an.
- Tarifwerk senkt den Einstiegspreis fuer unlimitierte Tarife deutlich.

## Das Wichtigste

Quasarnetz greift diese Woche das Kerngeschaeft der Mobilfunker an.

## Europa

Mehr Text.
"""


def _faden_highlights(quasar_relevance: int = 5) -> list[dict]:
    """Eine Ausgabe, in der die zwei Fuehrungssaetze belegbar sind - und in
    der eine gleich stark bewertete Meldung im Bericht NICHT vorkommt. Ohne
    diesen Gegensatz koennte der Test nicht unterscheiden, ob die Seite dem
    Faden folgt oder nur zufaellig dasselbe waehlt.

    `quasar_relevance` senkt die Bewertung der Meldung, die der Bericht
    meint. Damit misst derselbe Aufbau beide Seiten der Regel: bei
    Gleichstand ordnet der Faden, darunter schlaegt ihn der Rang."""
    hs = list(PORTAL)
    # Dieselbe Bewertung wie Quasarnetz, aber im Bericht kommt sie nicht
    # vor: die Meldung, die OHNE Faden den Aufmacher bekaeme (sie steht
    # vorn in der Liste, und `nimm` geht die Liste der Reihe nach durch).
    hs.insert(0, dict(_highlight(900, 5, "Netz/Technologie", image_w=1200),
                      title="Blaulicht Telekommunikation meldet Quartalszahlen",
                      operator="Blaulicht"))
    hs.append(dict(_highlight(901, quasar_relevance, "Netz/Technologie",
                              image_w=1200),
                   title="Quasarnetz kuendigt Kleinzellennetz gegen Mobilfunker an",
                   operator="Quasarnetz"))
    hs.append(dict(_highlight(902, quasar_relevance, "Tarif/Pricing",
                              image_w=1200),
                   title="Tarifwerk senkt Einstiegspreis fuer unlimitierte Tarife",
                   operator="Tarifwerk"))
    return hs


def test_die_titelseite_fuehrt_mit_dem_bericht(tmp_path):
    """Der Aufmacher kommt aus dem, worueber der Bericht fuehrt - unter den
    Meldungen, die den Platz nach ihrer Bewertung auch verdienen.

    Bis zum 15.08.2026 stand hier der Gegensatz "Faden schlaegt
    Dringlichkeit": die Fixture gab Blaulicht Prioritaet 5 und Quasarnetz
    die 3, und der Test verlangte trotzdem Quasarnetz als Aufmacher. Genau
    das hat die Titelseite kaputt gemacht - an der Ausgabe vom 14.08.2026
    fuehrte die Seite mit "T-Mobile wirbt mit Studienstart-Ratgeber"
    (Kontext, Prioritaet 2), waehrend "T-Mobile verschenkt Pixel 11 Pro XL"
    (Uebertragbar, Prioritaet 5) als Textzeile daneben stand.

    Die Regel ist jetzt: der Faden waehlt unter GLEICHRANGIGEN, welche
    Geschichte fuehrt. Hier haben Blaulicht und Quasarnetz denselben Rang -
    und dann muss der Bericht entscheiden."""
    from telco_radar.report.html import (_flatten, _titelseite, _faden,
                                         _fuehrende_saetze, _rangschluessel)

    hs = _flatten({"date": "2026-08-05", "stats": {},
                   "regions": {"Europa": {"highlights": _faden_highlights()}}})
    # Die Voraussetzung des Falls, ausgeschrieben: gleicher Rang, damit der
    # Test nicht heimlich nur die Sortierung misst.
    rang = {h["operator"]: _rangschluessel(h) for h in hs}
    assert rang["Quasarnetz"] == rang["Blaulicht"] == rang["Tarifwerk"]

    front = _titelseite(hs, _faden(hs, _fuehrende_saetze(FADEN_BRIEFING)))

    assert "Quasarnetz" in front["aufmacher"]["schlagzeile"], (
        f"Aufmacher folgt dem Bericht nicht: {front['aufmacher']['schlagzeile']}")
    # Beide Fuehrungssaetze stehen oberhalb der Falz.
    assert front["faden_oben"] == 2
    # Gegenprobe: OHNE Faden fuehrt die Seite mit der Dringlichkeit, und die
    # zeigt bei Gleichstand auf die erste Meldung der Liste.
    assert "Quasarnetz" not in _titelseite(hs)["aufmacher"]["schlagzeile"]


def test_der_faden_zieht_keine_schwaechere_meldung_nach_vorn(tmp_path):
    """Der Regressionstest zum Befund vom 15.08.2026. Antonio: "wie kann es
    sein dass artikel mit prioriät von 3 auf der titelseite landen ... die
    wichtigsten artikel sollen auch an erster reihe stehen."

    Derselbe Aufbau wie oben, nur ist die Meldung, die der Bericht meint,
    zwei Stufen schwaecher bewertet. Dann bekommt sie den Aufmacher NICHT -
    der Rang schlaegt den Faden. Gegen den Stand vom 14.08.2026 gemessen
    faellt dieser Test durch: dort stand Quasarnetz als Aufmacher."""
    from telco_radar.report.html import (_flatten, _titelseite, _faden,
                                         _fuehrende_saetze, _rangschluessel)

    hs = _flatten({"date": "2026-08-05", "stats": {},
                   "regions": {"Europa": {
                       "highlights": _faden_highlights(quasar_relevance=3)}}})
    rang = {h["operator"]: _rangschluessel(h) for h in hs}
    assert rang["Quasarnetz"] < rang["Blaulicht"], \
        "ohne Rangunterschied prueft dieser Test nichts"

    front = _titelseite(hs, _faden(hs, _fuehrende_saetze(FADEN_BRIEFING)))

    aufmacher = front["aufmacher"]
    assert "Quasarnetz" not in aufmacher["schlagzeile"], (
        "der Faden hat eine schwaecher bewertete Meldung nach vorn gezogen: "
        f"{aufmacher['schlagzeile']}")
    # Und positiv: der Aufmacher traegt den besten Rang, den eine Meldung
    # mit grossem Bild ueberhaupt hat.
    from telco_radar.report.bilder import MIND_BREITE_GROSS
    from telco_radar.report.html import _bildbreite
    bester = max(_rangschluessel(h) for h in hs
                 if _bildbreite(h) >= MIND_BREITE_GROSS)
    assert _rangschluessel(aufmacher) == bester


def test_die_bildstufen_stehen_in_der_rangfolge():
    """Aufmacher, zweite und dritte Reihe stehen untereinander in EINER
    Spalte - dann muessen sie auch in einer Rangfolge stehen.

    Gemessen wird an ALLEN archivierten Ausgaben, nicht an einer Fixture:
    die erste Fassung dieses Tests gab jeder Meldung `image_w=1200` und
    behauptete danach eine Zusicherung, die der Code gar nicht hat. Auf den
    echten Daten brach sie in 2 von 17 Ausgaben.

    Die Ausnahme, die dabei sichtbar wurde, ist keine Schlamperei sondern
    die Bildregel: Aufmacher und zweite Reihe verlangen 800 px, die dritte
    Reihe nur ueberhaupt ein Bild. Eine Meldung mit 776 px kann also in der
    dritten Reihe stehen und die zweite ueberragen (14.08.2026: "Free
    buendelt Disney+ Sportrechte", Uebertragbar/Prioritaet 4, 776 px). Sie
    ist deshalb ausgenommen - und nur sie. Wer die dritte Reihe fuer
    schwaechere Meldungen mit grossem Bild oeffnet, faellt hier durch.

    Ausgenommen ist ausserdem, was der Absenderdeckel verschoben hat: mehr
    als zwei Meldungen desselben Absenders duerfen oberhalb der Falz nicht
    stehen, und die dritte rutscht dadurch nach hinten."""
    from telco_radar.report.bilder import MIND_BREITE_GROSS
    from telco_radar.report.html import (_flatten, _titelseite, _bildbreite,
                                         _rangschluessel, _kennwoerter)

    repo = Path(__file__).resolve().parents[1]
    geprueft = 0
    for datei in sorted((repo / "data" / "reports").glob("*.json")):
        hs = _flatten(json.loads(datei.read_text(encoding="utf-8")))
        if len(hs) < 14:
            continue                      # zu klein fuer alle Stufen
        front = _titelseite(hs)
        oben = ([front["aufmacher"]] if front["aufmacher"] else []) \
            + list(front["zwei"])
        gross = [h for h in oben if _bildbreite(h) >= MIND_BREITE_GROSS]
        if not gross:
            continue
        schwaechste = min(_rangschluessel(h) for h in gross)
        # Wer den Absenderdeckel schon ausgeschoepft hat, darf hinten stehen.
        voll = set()
        for h in oben:
            kw = _kennwoerter(h.get("operator") or h.get("source_label") or "")
            if sum(1 for g in oben
                   if _kennwoerter(g.get("operator")
                                   or g.get("source_label") or "") & kw) >= 2:
                voll |= kw
        ueber = [h["schlagzeile"] for h in front["vier"]
                 if _rangschluessel(h) > schwaechste
                 and _bildbreite(h) >= MIND_BREITE_GROSS
                 and not (_kennwoerter(h.get("operator")
                                       or h.get("source_label") or "") & voll)]
        assert not ueber, f"{datei.name}: dritte Reihe ueberragt die zweite: {ueber}"
        geprueft += 1
    # Die Anti-Leerlauf-Zeile. Gemessen werden nur Ausgaben AB dem
    # 06.08.2026 - davor trugen die Berichte keine Bildbreiten (bilder.py
    # ist an dem Tag neu geschrieben worden), und ohne Bild gibt es keine
    # Bildstufe zu pruefen. Es sind aktuell fuenf, und die Zahl waechst mit
    # jeder Ausgabe; sie kann nicht schrumpfen, weil `_flatten` die Breite
    # aus dem BERICHT liest und nicht aus dem Bildordner, den ein
    # Aufraeumlauf beschneiden darf.
    assert geprueft >= 4, f"nur {geprueft} Ausgaben gemessen"


def test_die_spalte_nimmt_den_bildstufen_keine_bessere_meldung_weg(tmp_path):
    """Der Regressionstest zum zweiten Teil des Befunds vom 15.08.2026.

    Bis dahin zog die Digest-Spalte "Was wichtig ist" (sieben Textzeilen)
    VOR der dritten Reihe. Die Hauptspalte bekam dadurch systematisch die
    schwaecheren Meldungen: in der Ausgabe, die Antonio vorlag, standen in
    den vier Kacheln vier Meldungen mit Prioritaet 2, waehrend fuenf mit
    Prioritaet 3 als Textzeilen danebenlagen. Jede Karte traegt ihre
    Prioritaet als sichtbares Etikett - das war also kein Feinheitsproblem,
    sondern ein Widerspruch, den man auf der Seite lesen konnte.

    Geprueft wird nur, was die Regel wirklich zusichert: eine Meldung MIT
    Bild darf nicht in der Spalte stehen, waehrend eine schwaechere in der
    dritten Reihe steht. Meldungen OHNE Bild duerfen die Spalte sehr wohl
    anfuehren - sie passen in keine Bildstufe, und ein fehlendes Bild ist
    keine Abwertung."""
    from telco_radar.report.html import (_flatten, _titelseite, _bildbreite,
                                         _rangschluessel)

    # Der Zuschnitt der Ausgabe vom 15.08.2026, nachgebaut: drei Meldungen
    # fuer Aufmacher und zweite Reihe, danach fuenf mit Prioritaet 3 und
    # sieben mit Prioritaet 2 - alle mit grossem Bild. Die Spalte hat sieben
    # Plaetze; zieht sie zuerst, raeumt sie damit jede Prioritaet 3 ab, und
    # in die vier Kacheln fallen die Zweier. Jede Meldung braucht einen
    # eigenen Absender - und zwar einen, der kein gemeinsames Wort mit den
    # anderen teilt: "Anbieter 701" und "Anbieter 702" sind fuer
    # `_kennwoerter` DERSELBE Absender (die Ziffern sind zu kurz fuer das
    # Wortmuster), dann greift der Deckel statt der Rangfolge, und der Test
    # misst etwas anderes als er behauptet.
    namen = ["Quasarnetz", "Tarifwerk", "Blaulicht", "Nordfunk", "Sylttel",
             "Ostmobil", "Wattline", "Duenenfunk", "Kliffnetz", "Moorcom",
             "Heidefon", "Foehrmobil", "Bodencom", "Ryktel", "Aalfunk"]
    roh = []
    for i, (ctm, rel) in enumerate([(2, 3)] * 3 + [(1, 3)] * 5
                                   + [(1, 2)] * 7):
        h = _highlight(700 + i, rel, "Tarif/Pricing", image_w=1200)
        h |= {"ctm_bezug": ctm, "operator": namen[i]}
        roh.append(h)
    hs = _flatten({"date": "2026-08-15", "stats": {},
                   "regions": {"Europa": {"highlights": roh}}})
    front = _titelseite(hs)
    assert front["vier"], "ohne dritte Reihe prueft dieser Test nichts"
    assert len(front["wichtig"]) == 7, front["wichtig"]

    schwaechste = min(_rangschluessel(h) for h in front["vier"])
    ueberholt = [h["schlagzeile"] for h in front["wichtig"]
                 if _bildbreite(h) >= 1 and _rangschluessel(h) > schwaechste]
    assert not ueberholt, (
        f"steht als Textzeile, obwohl schwaechere Meldungen eine Bildkachel "
        f"bekamen: {ueberholt}")


def test_ohne_belegbaren_faden_bleibt_die_alte_reihenfolge(tmp_path):
    """Eine falsche Verbindung ist schlimmer als keine: teilt eine Meldung
    zu wenige seltene Woerter mit dem Fuehrungssatz, gilt er als nicht
    belegt und die Seite sortiert weiter nach Dringlichkeit."""
    from telco_radar.report.html import _flatten, _titelseite, _faden, _fuehrende_saetze

    hs = _flatten({"date": "2026-08-05", "stats": {},
                   "regions": {"Europa": {"highlights": _faden_highlights()}}})
    fremd = "## Auf einen Blick\n- Ein Thema, das in keiner Meldung vorkommt.\n"
    assert _faden(hs, _fuehrende_saetze(fremd)) == []
    front = _titelseite(hs, _faden(hs, _fuehrende_saetze(fremd)))
    assert front["faden_oben"] == 0
    assert front["aufmacher"] is not None


def test_der_vorspann_ueber_der_ausgabe_ist_weg(tmp_path):
    """Der Faden ordnet die Seite weiter, er wird nur nicht mehr abgeschrieben.

    Ueber der Ausgabe stand bis zum 07.08.2026 der erste Satz des Berichts
    als Vorspann samt Sprunglink. Antonio: "dieser kleine Ausschnitt von dem
    Bericht mit dem Link zum Bericht, das kann dann auch weg" - derselbe
    Text steht auf derselben Seite ohnehin vollstaendig.

    Was bleibt, ist die Wirkung: der Aufmacher ist weiterhin GENAU die
    Meldung, mit der der Bericht fuehrt (siehe
    test_die_titelseite_fuehrt_mit_dem_bericht). Und `briefing_lead` wird
    nicht mehr berechnet - eine Zahl, die keine Vorlage liest, ist genau der
    Zustand, aus dem dieser Wert einmal gekommen ist."""
    from telco_radar.report import html as html_mod

    site = _render(tmp_path, highlights=_faden_highlights(),
                   briefing=FADEN_BRIEFING)
    soup = BeautifulSoup(_seite(site, "index.html"), "html.parser")
    assert soup.select_one(".front-faden") is None, "Der Vorspann steht noch da"
    assert "Worum es diese Woche geht" not in _seite(site, "index.html")
    # Der Bericht steht direkt darunter und traegt seine Sprungmarke weiter.
    assert soup.select_one("#der-wochenbericht")
    assert "front-faden" not in _seite(site, "style.css")

    assert not hasattr(html_mod, "_briefing_lead")
    vorlagen = Path(html_mod.__file__).parent / "templates"
    for tpl in vorlagen.glob("*.j2"):
        text = re.sub(r"(?s)\{#.*?#\}", "", tpl.read_text(encoding="utf-8"))
        assert "briefing_lead" not in text, f"{tpl.name} liest briefing_lead"


# ------------------------------------------------- Was die Seite NICHT mehr traegt
def test_die_datumszeile_ist_auf_keiner_seite_mehr_da(tmp_path):
    """Abnahmekriterium 1. Antonio: "Loesch diese Zeile, das ist unnoetig."

    Geprueft wird auch, dass keine tote Variable zurueckgeblieben ist -
    diese Codebasis hat schon einmal sechs berechnete Werte mitgeschleppt,
    die keine Vorlage benutzte."""
    from telco_radar.report import html as html_mod

    site = _render(tmp_path, highlights=PORTAL)
    for name in ("index.html", "meldungen.html", "transparenz.html",
                 "differenzierung.html", "reports/2026-08-05.html"):
        seite = _seite(site, name)
        assert "dateline" not in seite, f"Datumszeile noch auf {name}"
        assert "Quellen beobachtet" not in seite
    assert "dateline" not in _seite(site, "style.css")
    # Und keine Vorlage fragt die Werte noch ab - sie werden nicht mehr
    # berechnet, ein Zugriff waere also still leer statt laut falsch.
    from pathlib import Path
    vorlagen = Path(html_mod.__file__).parent / "templates"
    for tpl in vorlagen.glob("*.j2"):
        # Ohne Jinja-Kommentare: dass in einem {# ... #} steht, WARUM die
        # Werte weg sind, ist Dokumentation und kein Zugriff.
        text = re.sub(r"(?s)\{#.*?#\}", "", tpl.read_text(encoding="utf-8"))
        for tot in ("ausgabe_datum", "ausgabe_quellen"):
            assert tot not in text, f"{tpl.name} liest die tote Variable {tot}"


def test_die_wochenseite_traegt_die_doppelten_formen_nicht_mehr(tmp_path):
    """Punkt 4 des Auftrags: "Wo dieselbe Information zweimal in zwei Formen
    steht, faellt eine weg."

    Die Kachelreihe "Zahlen der Woche" nannte gelesen/relevant ein zweites
    Mal (sie stehen als Satz ueber dem Bericht) und das Top-Technologiethema
    ein zweites Mal (es ist die erste Zeile des Themenradars). "Auswertung je
    Bereich" stand wortgleich auf transparenz.html."""
    site = _render(tmp_path, highlights=PORTAL)
    index = _seite(site, "index.html")
    assert "Zahlen der Woche" not in index
    assert "Auswertung je Bereich" not in index
    # ... aber die Frage, die sie beantworteten, hat weiterhin einen Ort.
    assert "Auswertung je Bereich" in _seite(site, "transparenz.html")
    # Die Zahl "davon N zum sofortigen Ansehen" ist am 08.08.2026 gefallen:
    # sie stand an jeder betroffenen Meldung ohnehin als Prioritaet 5/5.
    assert "zum sofortigen Ansehen" not in index


# ------------------------------------------------------ Die Wettbewerbsseite
# Sie zeigt zwei Zahlen: den Umfang der Chronik ("56 Meldungen seit 16. Juli
# 2026") und den Umfang je Monatsgruppe. Beide sind Aggregate ueber ALLE
# Wochen des Archivs - genau die Sorte Zahl, die still falsch wird, wenn
# jemand die Gruppierung anfasst.
def test_die_chronik_zaehlt_was_sie_zeigt(tmp_path):
    site = _render(tmp_path, competitors=GELUNGEN)
    soup = BeautifulSoup(_seite(site, "wettbewerb.html"), "html.parser")
    abschnitt = soup.select_one("section.wb")

    zeilen = abschnitt.select(".wb-zeile")
    kopf = " ".join(abschnitt.select_one(".rubrik-zahl").get_text().split())
    assert kopf.startswith(f"{len(zeilen)} Meldung"), kopf
    # Der Bericht ist der einzige im Archiv - also datiert die Chronik auf
    # seinen Tag, nicht auf den heutigen.
    assert kopf.endswith("seit 5. August 2026"), kopf

    # Die Monatszahlen summieren sich auf dieselbe Zahl (offener Monat plus
    # jeder zugeklappte).
    monate = [int(m.get_text(strip=True))
              for m in abschnitt.select(".wb-monat span")]
    assert sum(monate) == len(zeilen)


def test_der_kurzverweis_zeigt_jeden_wettbewerber_mit_profil(tmp_path):
    """Die Titelseite nennt je Wettbewerber eine Zeile - nicht mehr, nicht
    weniger. Ein stiller Verlust hier saehe aus wie ein kleineres
    Wettbewerbsfeld."""
    gemischt = [dict(GELUNGEN[0]),
                {"name": "1&1", "n_items": 8, "moves": [], "summary": "",
                 "themes": [], "vodafone_implication": "",
                 "error": "JSONDecodeError"}]
    soup = BeautifulSoup(_seite(_render(tmp_path, competitors=gemischt),
                                "index.html"), "html.parser")

    mit_profil = [c for c in gemischt if c["summary"]]
    assert len(soup.select(".wb-kurz-zeile")) == len(mit_profil)
    # ... und der Ausfall des anderen wird weiterhin benannt.
    assert "1 von 2 Profilen" in _seite(_render(tmp_path / "b",
                                                competitors=gemischt),
                                        "index.html")


# --------------------------------------------------- Die Themenseiten (temp.)
# Sie zeigen drei Zahlen: die Zahl der Meldungen des Themas (zweimal - im
# Seitenkopf und als Zaehler ueber der Zeilenliste), die Zahl der beteiligten
# Quellen und das Datum, seit dem das Thema laeuft. Alle drei sind Aggregate
# ueber den Themenspeicher, nicht ueber die Wochenausgabe - also genau die
# Sorte Zahl, die still falsch wird, sobald jemand die Zuordnung anfasst.
THEMA = {
    "slug": "starlink-plant-eigenes-mobilfunknetz",
    "title": "Starlink plant eigenes Mobilfunknetz",
    "description": "SpaceX will neben den Satelliten auch Funkmasten am Boden "
                   "betreiben und damit selbst Mobilfunk anbieten.",
    "keywords": ["Starlink", "SpaceX", "Mobilfunknetz"],
    "first_seen": "2026-08-04", "last_active": "2026-08-05",
    "runs_ohne_zuwachs": 0, "status": "aktiv",
    "items": [
        {"url": f"https://example.com/thema/{i}",
         "title": f"Starlink baut Netz {i}", "headline": f"Starlink baut Netz {i}",
         "summary": f"SpaceX kuendigt Schritt {i} an.", "operator": "SpaceX",
         "source": f"Quelle {i % 3}", "date": "2026-08-05", "week": "2026-08-05",
         "relevance": 5 - (i % 3)}
        for i in range(9)
    ],
}


def _themenspeicher(tmp_path, thema):
    state = tmp_path / "data" / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "highlight_topics.json").write_text(
        json.dumps({"updated": "2026-08-05", "topics": [thema]},
                   ensure_ascii=False), encoding="utf-8")


def _mit_thema(tmp_path, thema=None):
    site = _render(tmp_path)
    _themenspeicher(tmp_path, thema if thema is not None else THEMA)
    render_site(site, tmp_path / "data" / "reports")
    return site


def test_die_themenseite_zaehlt_was_sie_zeigt(tmp_path):
    site = _mit_thema(tmp_path)
    soup = BeautifulSoup(_seite(site, f"thema/{THEMA['slug']}.html"), "html.parser")

    lage = " ".join(soup.select_one(".tm-lage").get_text().split())
    quellen = {i["source"] for i in THEMA["items"]}
    assert lage == (f"Seit 4. August 2026 · {len(THEMA['items'])} Meldungen "
                    f"aus {len(quellen)} Quellen"), lage

    # Die Zahl im Kopf ist die einzige auf der Seite - und sie stimmt: jede
    # Meldung des Themas steht genau einmal darunter, verteilt auf Aufmacher,
    # zweite Reihe und Zeilenliste.
    schlagzeilen = [e.get_text(" ", strip=True) for e in soup.select(".szl")]
    assert len(schlagzeilen) == len(set(schlagzeilen)) == len(THEMA["items"])
    assert len(soup.select(".tm-zeile")) == len(THEMA["items"]) - 3


def test_das_fokusband_nennt_die_zahl_des_themas(tmp_path):
    site = _mit_thema(tmp_path)
    soup = BeautifulSoup(_seite(site, "index.html"), "html.parser")

    band = soup.select(".fokusband a")
    assert len(band) == 1
    assert band[0].select_one(".fokusband-titel").get_text(strip=True) == THEMA["title"]
    assert band[0].select_one(".fokusband-zahl").get_text(strip=True).startswith(
        f"{len(THEMA['items'])} Meldungen")
    assert band[0]["href"] == f"thema/{THEMA['slug']}.html"


def test_ohne_aktives_thema_steht_kein_band_und_keine_seite(tmp_path):
    """Gegenprobe: ein beendetes Thema verschwindet vollstaendig - Seite,
    Band und Ordnerinhalt."""
    site = _mit_thema(tmp_path)
    assert (site / "thema" / f"{THEMA['slug']}.html").exists()

    _themenspeicher(tmp_path, dict(THEMA, status="beendet"))
    render_site(site, tmp_path / "data" / "reports")
    assert not (site / "thema" / f"{THEMA['slug']}.html").exists()
    assert "fokusband" not in _seite(site, "index.html")


# ------------------------------------------------- Die Differenzierungs-Seite
# Sie zeigt seit dem 08.08.2026 nur noch EINE Zahl: je Hebel, wie viele
# Beispiele darunter stehen. Die alte Statuszeile ("51 Beispiele in der
# Bibliothek · 12 von 12 Hebeln aktiv · 5 neu") ist genau das Zahlenrauschen,
# das Antonio moniert hat - sie ist ersatzlos weg.
#
# Der zweite, wichtigere Punkt hier ist kein Layout-, sondern ein
# Inhaltsfehler: die Seite las bis dahin nur `differentiation_db.json` (den
# Web-Sweep). `differentiation.jsonl` (der Kurator ueber den woechentlichen
# Presse-Crawl) wurde jede Woche gefuellt und nie angezeigt.
DIFF_DB = [
    {"id": f"https://sweep{i}.example.com/x", "theme": t,
     "operator": f"Betreiber {i}", "region": "Europa",
     "what": f"Sweep-Beispiel {i} als Zusatzleistung.",
     "url": f"https://sweep{i}.example.com/x", "source": f"sweep{i}.example.com",
     "date": "2026", "why": "Bindet Kunden ohne Preisnachlass.",
     "first_seen": "2026-06-15", "last_verified": "2026-07-31",
     "status": "aktiv"}
    for i, t in enumerate(["ki", "ki", "ki", "cloud", "gaming"])
]
DIFF_STORE = [
    {"id": f"https://presse{i}.example.com/y", "first_seen": "2026-08-04",
     "theme": t, "title": f"Original headline {i} 20 Jul 2026",
     "summary": f"Presse-Beispiel {i} als Zusatzleistung. Nebensatz faellt weg.",
     "url": f"https://presse{i}.example.com/y", "operator": f"Presse-Betreiber {i}",
     "region": "Asien", "date": None, "category": "Partnerschaft", "relevance": 4,
     "why_it_matters": f"Begruendung {i}. Vodafone sollte pruefen, ob das traegt.",
     "source": f"Quelle {i}"}
    for i, t in enumerate(["ki", "security"])
]


def _diffspeicher(tmp_path, db=None, store=None):
    state = tmp_path / "data" / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "differentiation_db.json").write_text(
        json.dumps({"updated": "2026-08-05",
                    "entries": DIFF_DB if db is None else db},
                   ensure_ascii=False), encoding="utf-8")
    (state / "differentiation.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n"
                for e in (DIFF_STORE if store is None else store)),
        encoding="utf-8")


def _mit_differenzierung(tmp_path, db=None, store=None):
    site = _render(tmp_path)
    _diffspeicher(tmp_path, db, store)
    render_site(site, tmp_path / "data" / "reports")
    return site


def test_die_differenzierung_zeigt_BEIDE_speicher(tmp_path):
    """Der Kurator lief bis zum 08.08.2026 jede Woche umsonst."""
    soup = BeautifulSoup(_seite(_mit_differenzierung(tmp_path), "differenzierung.html"),
                         "html.parser")
    hauptzeilen = {e.get_text(" ", strip=True) for e in soup.select(".dzk-what")}
    assert "Sweep-Beispiel 0 als Zusatzleistung." in hauptzeilen
    assert "Presse-Beispiel 0 als Zusatzleistung." in hauptzeilen
    # Die Hauptzeile ist der deutsche Satz, nicht der mehrsprachige Rohtitel.
    assert not any("Original headline" in z for z in hauptzeilen)


def test_jeder_hebel_zaehlt_was_unter_ihm_steht(tmp_path):
    """Die einzige Zahl der Seite - gegen die Karten gehalten, die sie meint."""
    soup = BeautifulSoup(_seite(_mit_differenzierung(tmp_path), "differenzierung.html"),
                         "html.parser")
    erwartet = {"ki": 4, "security": 1, "cloud": 1, "gaming": 1}
    gesehen = {}
    for abschnitt in soup.select(".dz-hebel"):
        key = abschnitt["id"].removeprefix("dz-theme-")
        zahl = abschnitt.select_one(".rubrik-zahl").get_text(" ", strip=True)
        karten = abschnitt.select(".dzk")
        assert zahl == f"{len(karten)} Beispiel{'e' if len(karten) != 1 else ''}", key
        gesehen[key] = len(karten)
    assert gesehen == erwartet
    # Und jedes Beispiel steht in der Bibliothek genau EINMAL.
    quellen = [a["href"] for abschnitt in soup.select(".dz-hebel")
               for a in abschnitt.select(".dzk-what")]
    assert len(quellen) == len(set(quellen)) == len(DIFF_DB) + len(DIFF_STORE)


def test_hebel_ohne_beispiel_stehen_nicht_auf_der_seite(tmp_path):
    """Zwoelfmal "Noch keine bestaetigten Beispiele" war zwoelfmal derselbe
    leere Kasten - und die Sprungnavigation zeigt nur, was es gibt."""
    seite = _seite(_mit_differenzierung(tmp_path), "differenzierung.html")
    soup = BeautifulSoup(seite, "html.parser")
    assert "Noch keine bestätigten Beispiele" not in seite

    anker = {a["id"] for a in soup.select(".dz-hebel")}
    sprungziele = {a["href"].lstrip("#") for a in soup.select(".dz-nav a")}
    assert sprungziele == anker == {"dz-theme-ki", "dz-theme-security",
                                    "dz-theme-cloud", "dz-theme-gaming"}


def test_die_statuszeile_der_differenzierung_ist_weg(tmp_path):
    """Antonio: die Seite wirkt unruhig durch die vielen Kommentare. Geprueft
    wird auch, dass keine tote Vorlagen-Variable und kein toter CSS-Block
    zurueckgeblieben ist."""
    site = _mit_differenzierung(tmp_path)
    seite = _seite(site, "differenzierung.html")
    for tot in ("dz-status", "Beispiele in der Bibliothek", "Hebeln aktiv",
                "seit dem letzten Blick", "theme-grid", "theme-card"):
        assert tot not in seite, tot
    stil = _seite(site, "style.css")
    for tot in ("dz-status", "theme-grid", "theme-card", "dz-move", "dz-card"):
        assert tot not in stil, f"toter CSS-Block {tot}"

    from telco_radar.report import html as html_mod
    vorlage = (Path(html_mod.__file__).parent / "templates"
               / "differenzierung.html.j2").read_text(encoding="utf-8")
    vorlage = re.sub(r"(?s)\{#.*?#\}", "", vorlage)
    for tot in ("diff_stats", "diff_themes"):
        assert tot not in vorlage, f"Vorlage liest die tote Variable {tot}"


def test_neu_auf_dem_radar_zeigt_nur_junge_funde(tmp_path):
    site = _mit_differenzierung(tmp_path)
    soup = BeautifulSoup(_seite(site, "differenzierung.html"), "html.parser")
    radar = soup.select(".dz-radar .dzk")
    # Nur die zwei Presse-Eintraege sind juenger als zehn Tage (Ausgabe vom
    # 5.8., first_seen 4.8.); die Sweep-Eintraege stammen vom 15.6.
    assert len(radar) == len(DIFF_STORE)
    assert soup.select_one(".dz-radar .rubrik h2").get_text(strip=True) \
        == "Neu auf dem Radar"
    assert all(k.select_one(".dz-new") for k in radar)


def test_ohne_junge_funde_steht_oben_das_zuletzt_gepruefte(tmp_path):
    """Gegenprobe: eine ruhige Woche darf die Seite nicht enthaupten."""
    soup = BeautifulSoup(
        _seite(_mit_differenzierung(tmp_path, store=[]), "differenzierung.html"),
        "html.parser")
    assert soup.select_one(".dz-radar .rubrik h2").get_text(strip=True) \
        == "Zuletzt nachgeprüft"
    assert soup.select(".dz-radar .dzk")
    assert not soup.select(".dz-radar .dz-new")


def test_der_suchindex_kennt_auch_die_presse_eintraege(tmp_path):
    """Was auf der Seite steht, muss auffindbar sein - der Index speiste sich
    bis dahin allein aus der DiffDB."""
    site = _mit_differenzierung(tmp_path)
    index = json.loads(_seite(site, "search_index.json"))
    diff = [e for e in index if e["kind"] == "differenzierung"]
    assert len(diff) == len(DIFF_DB) + len(DIFF_STORE)
    presse = [e for e in diff if e["operator"] == "Presse-Betreiber 0"]
    assert len(presse) == 1
    assert presse[0]["deep_link"] == "differenzierung.html#dz-theme-ki"
    assert presse[0]["title"] == "Presse-Beispiel 0 als Zusatzleistung."


def test_der_differenzierungsbericht_bleibt_erhalten(tmp_path):
    """Der Essay wandert nach unten in einen Aufklapper - er verschwindet
    nicht. Loeschen von Funktionalitaet ist keine Vereinfachung."""
    site = _render(tmp_path)
    berichte = tmp_path / "data" / "reports" / "differenzierung"
    berichte.mkdir(parents=True, exist_ok=True)
    (berichte / "2026-08-05.md").write_text(
        "## Garantien\n\nEin Absatz des Essays.\n", encoding="utf-8")
    _diffspeicher(tmp_path)
    render_site(site, tmp_path / "data" / "reports")

    soup = BeautifulSoup(_seite(site, "differenzierung.html"), "html.parser")
    essay = soup.select_one("details.dz-essay")
    assert essay is not None and not essay.has_attr("open")
    assert "Ein Absatz des Essays." in essay.get_text(" ", strip=True)


# ---- Der Umbau vom 08.08.2026 (Antonio: "total unuebersichtlich, keine
# Bilder, es ist schwer zu verstehen ... viel besser sein analytisch").
def test_jede_karte_der_differenzierung_traegt_ein_motiv(tmp_path):
    """Bild ODER Schriftkachel - nie ein leerer Kasten. Dieselbe Regel wie
    auf der Promo Uebersicht (Abnahmekriterium 8c). Die Zeilen sind bewusst
    ausgenommen: sie sind die dritte Gewichtsstufe und tragen kein Motiv,
    genau wie die Zeilen der Meldungsseite."""
    soup = BeautifulSoup(_seite(_mit_differenzierung(tmp_path), "differenzierung.html"),
                         "html.parser")
    karten = [k for k in soup.select(".dzk")
              if "dzk--zeile" not in (k.get("class") or [])]
    assert karten
    for karte in karten:
        motiv = karte.select_one(".dzk-motiv")
        assert motiv is not None, karte.get_text(" ", strip=True)[:60]
        assert motiv.select_one("img") or motiv.get_text(strip=True), \
            "leerer Motivkasten"


def test_die_schriftkachel_wiederholt_den_absender_nicht(tmp_path):
    """Ohne Bild traegt die Kachel den Absender - dann steht er nicht noch
    einmal in der Metazeile darunter. Zweimal derselbe Name untereinander
    liest sich als Panne, nicht als Gestaltung."""
    soup = BeautifulSoup(_seite(_mit_differenzierung(tmp_path), "differenzierung.html"),
                         "html.parser")
    kacheln = soup.select(".dzk-kachel")
    assert kacheln, "ohne Bildindex muessten alle Karten eine Kachel tragen"
    for karte in soup.select(".dzk"):
        if karte.select_one(".dzk-kachel") and "dzk--zeile" not in (karte.get("class") or []):
            assert not karte.select_one(".dzk-op"), \
                karte.get_text(" ", strip=True)[:80]


def test_das_marktbild_zaehlt_was_die_bibliothek_zeigt(tmp_path):
    """Die Auswertung steht vor den Beispielen und muss dieselben Zahlen
    nennen wie die Rubriken darunter - sonst hat die Seite zwei Wahrheiten."""
    soup = BeautifulSoup(_seite(_mit_differenzierung(tmp_path), "differenzierung.html"),
                         "html.parser")
    marktbild = soup.select_one(".dz-marktbild")
    gesamt = marktbild.select_one(".rubrik-zahl").get_text(" ", strip=True)
    assert gesamt == f"{len(DIFF_DB) + len(DIFF_STORE)} Beispiele"

    # Der Hebel-Balken je Hebel gegen die Rubrikzahl desselben Hebels.
    balken = {li.select_one(".dz-balken-name").get_text(strip=True):
              int(li.select_one(".dz-balken-n").get_text(strip=True))
              for li in marktbild.select(".dz-mb-block")[0].select("li")}
    for abschnitt in soup.select(".dz-hebel"):
        label = abschnitt.select_one("h2").get_text(strip=True)
        n = len(abschnitt.select(".dzk"))
        assert balken[label] == n, label


def test_jeder_hebel_sagt_in_einem_satz_was_er_bedeutet(tmp_path):
    """Antonio: "damit nicht so viel kognitive Arbeit darin besteht, erstmal
    zu verstehen, was die Differenzierung ist." Wer "Super-App & Oekosystem"
    liest, soll nicht raten muessen."""
    soup = BeautifulSoup(_seite(_mit_differenzierung(tmp_path), "differenzierung.html"),
                         "html.parser")
    abschnitte = soup.select(".dz-hebel")
    assert abschnitte
    for abschnitt in abschnitte:
        satz = abschnitt.select_one(".dz-hebel-was")
        assert satz is not None and len(satz.get_text(strip=True)) > 30, \
            abschnitt.get("id")


def test_der_bericht_steht_verteilt_statt_als_block(tmp_path):
    """Die neue Gliederung landet im Seitenkopf, im Musterband und ueber den
    Hebeln - und dann gibt es KEINEN Aufklapper mehr am Seitenende. Das war
    der Block, den Antonio nicht "reingepastet" haben wollte."""
    site = _render(tmp_path)
    berichte = tmp_path / "data" / "reports" / "differenzierung"
    berichte.mkdir(parents=True, exist_ok=True)
    (berichte / "2026-08-05.md").write_text(
        "## Das Bild\n\nDie Lage in einem Satz.\n\n"
        "## Muster\n\n**Bündel** Zwei Anbieter tun dasselbe.\n\n"
        "## Einordnung\n\n### KI & Assistenten\n\nIndien treibt das Feld.\n",
        encoding="utf-8")
    _diffspeicher(tmp_path)
    render_site(site, tmp_path / "data" / "reports")

    soup = BeautifulSoup(_seite(site, "differenzierung.html"), "html.parser")
    assert "Die Lage in einem Satz." in soup.select_one(".dz-lage").get_text(" ", strip=True)
    assert "Zwei Anbieter tun dasselbe." in \
        soup.select_one(".dz-muster-band").get_text(" ", strip=True)
    ki = soup.select_one("#dz-theme-ki .dz-hebel-einordnung").get_text(" ", strip=True)
    assert ki == "Indien treibt das Feld."
    assert soup.select_one("details.dz-essay") is None


def test_keine_karte_der_differenzierung_raet_vodafone_etwas(tmp_path):
    """Die Seite berichtet, sie beraet nicht (CLAUDE.md §8).

    Geprueft wird ueber den GESAMTEN gerenderten Bestand, mit einem Muster,
    das eingeschobene Woerter zulaesst - "Vodafone prüfen könnte" stand nicht
    woertlich in den alten `_ADVICE_PHRASES` und rutschte deshalb durch.
    Der Gegenfall steht gleich mit drin: eine Beobachtung UEBER
    Vodafone-Gesellschaften ist kein Rat AN Vodafone und muss bleiben.
    """
    beobachtung = ("Vodafone-Afrika-Gesellschaften könnten Marktanteile an "
                   "Reisende verlieren, wenn MTN ein eSIM-Angebot platziert.")
    db = [dict(DIFF_DB[0], id="https://a.example.com/", url="https://a.example.com/",
               why="Ein Modell, das Vodafone prüfen könnte: KI-Bundles binden Kunden."),
          dict(DIFF_DB[1], id="https://b.example.com/", url="https://b.example.com/",
               why="Vodafone sollte prüfen, ob das trägt."),
          dict(DIFF_DB[2], id="https://c.example.com/", url="https://c.example.com/",
               why=beobachtung)]
    store = [dict(DIFF_STORE[0], id="https://d.example.com/",
                  url="https://d.example.com/",
                  why_it_matters="Zeigt die Zugkraft von Sportrechten. "
                                 "Wir sollten prüfen, ob wir nachziehen.")]
    site = _mit_differenzierung(tmp_path, db=db, store=store)
    soup = BeautifulSoup(_seite(site, "differenzierung.html"), "html.parser")

    modal = (r"(?:soll(?:te|ten)?|m(?:ü|u)ss(?:te|ten|en)?|"
             r"k(?:ö|oe)nn(?:te|ten|en)?|kann|pr(?:ü|ue)fen|bewerten)")
    adressat = r"vodafone|wir|uns(?:er\w*)?"
    rat = [re.compile(rf"(?<!\w)(?:{adressat})(?:\W+\w+){{0,4}}\W+{modal}(?!\w)", re.I),
           re.compile(rf"(?<!\w){modal}(?:\W+\w+){{0,4}}\W+(?:{adressat})(?!\w)", re.I)]

    karten = soup.select(".dzk")
    assert karten
    for karte in karten:
        text = " ".join(karte.get_text(" ", strip=True).split())
        if beobachtung[:40] in text:      # der Gegenfall - er DARF matchen
            continue
        for muster in rat:
            assert not muster.search(text), text

    # Der Gegenfall steht wirklich noch da, ungekuerzt.
    assert beobachtung in _seite(site, "differenzierung.html")
    # Und die reine Empfehlung hat ihre Karte nicht mitgenommen.
    zweitzeilen = len(soup.select(".dz-hebel .dzk-why"))
    assert len(soup.select(".dz-hebel .dzk")) == 4 and zweitzeilen == 3


# ------------------------------------------- Der Beruhigungs-Durchgang (A)
# Antonio am 08.08.2026: "Die Seite wirkt unruhig, weil ueberall so viele
# Kommentare sind - zum Beispiel '138 Meldungen in sieben Ressorts, jede
# Kachel zeigt ...'. Mehr roter Faden, einfacher zu lesen."
#
# Was daraufhin gestrichen wurde, hat je einen Test - sonst kommt es beim
# naechsten Umbau unbemerkt zurueck.
def test_keine_seite_erklaert_ihre_eigene_bedienung(tmp_path):
    """Saetze, die beschreiben, was ein Klick tut, statt etwas auszusagen."""
    site = _render(tmp_path, highlights=PORTAL, competitors=GELUNGEN)
    # "beim Anklicken" kam am 11.08.2026 auf der Geraeteseite dazu und ist
    # dieselbe Sorte Satz: er beschreibt eine Handlung, statt etwas
    # auszusagen. Die Seite fehlte in dieser Liste, also fing sie ihn nicht.
    verboten = ("Jede Kachel zeigt", "klappt das", "Suchbegriff eingeben",
                "beim Anklicken", "nennt ihn beim")
    for name in ("index.html", "meldungen.html", "transparenz.html",
                 "differenzierung.html", "wettbewerb.html", "geraete.html"):
        text = _seite(site, name)
        for satz in verboten:
            assert satz not in text, f"{name} erklaert seine Bedienung: {satz}"
    # Auch nicht aus dem Skript nachgereicht.
    assert "Suchbegriff eingeben" not in _seite(site, "app.js")


def test_meldungskopf_ist_kicker_und_ueberschrift(tmp_path):
    """Kein Erklaersatz unter der H1 - Antonios woertliches Beispiel."""
    soup = BeautifulSoup(
        _seite(_render(tmp_path, highlights=PORTAL), "meldungen.html"),
        "html.parser")
    kopf = soup.select_one(".meldungen-kopf")
    kinder = [k.name for k in kopf.find_all(recursive=False)]
    assert kinder == ["p", "h1"], kinder
    assert kopf.select_one("p")["class"] == ["page-kicker"]


def test_archivzeile_nennt_nur_die_neuen_meldungen(tmp_path):
    """"3447 gesammelt · 381 neu" waren zwei Zahlen je Zeile, von denen eine
    (die gesammelten) eine Transparenzfrage beantwortet und dort auch
    steht."""
    site = _render(tmp_path, highlights=PORTAL)
    soup = BeautifulSoup(_seite(site, "meldungen.html"), "html.parser")
    zeilen = soup.select("#archiv .list-row")
    assert zeilen
    for z in zeilen:
        felder = [s["class"][0] for s in z.select("span")]
        assert felder == ["list-row-date", "list-row-new"], felder
    assert "gesammelt" not in _seite(site, "meldungen.html")
    # Die verbliebene Zahl stimmt mit dem Bericht ueberein.
    assert f"{NEU_GESAMMELT} neue Meldungen" in zeilen[0].get_text(" ", strip=True)


def test_zaehlwerte_tragen_ueberall_dieselbe_klasse(tmp_path):
    """Ein Etikettensystem, nicht drei. `count-badge` (Chip) und der
    Inline-Style auf der Quellenseite sind in `rubrik-zahl` aufgegangen."""
    site = _render(tmp_path, highlights=PORTAL, competitors=GELUNGEN)
    for name in ("index.html", "meldungen.html", "transparenz.html",
                 "differenzierung.html", "wettbewerb.html"):
        assert "count-badge" not in _seite(site, name), name
    # Im Stylesheet ohne Kommentare - dass dort steht, WORAUS `rubrik-zahl`
    # hervorging, ist Dokumentation und keine Regel.
    css = re.sub(r"(?s)/\*.*?\*/", "", _seite(site, "style.css"))
    assert "count-badge" not in css
    # ... und die Klasse wird auch wirklich benutzt.
    soup = BeautifulSoup(_seite(site, "meldungen.html"), "html.parser")
    assert soup.select(".rubrik-zahl")


# =========================================================== CTM-Linse ====
# Die zweite Bewertungsachse (analyze/ctm.py) und der Zwei-Minuten-Pfad.
# Beides sind ZAHLEN und REIHENFOLGEN auf der Seite - also gehoert es hierhin
# und nicht in einen Modultest: dass `veredle()` richtig rechnet, sagt noch
# nicht, dass die Startseite das Ergebnis auch zeigt.

def _ctm_highlight(i, *, ctm_bezug, relevance=3, satz=None, operator=None):
    h = _highlight(i, relevance, "Tarif/Pricing", image_w=1200)
    h["ctm_bezug"] = ctm_bezug
    h["operator"] = operator or f"Betreiber {i}"
    if satz:
        h["ctm_satz"] = satz
    return h


def test_zwei_minuten_steht_in_der_spalte_ueber_was_wichtig_ist(tmp_path):
    """Bis zum 09.08.2026 stand der Kasten UEBER dem Aufmacher, und dieser
    Test hat genau das festgehalten ("wer zwei Minuten hat, soll nicht erst
    eine Zeitungsseite durchqueren").

    Die Rechnung ging nicht auf: fuenf Eintraege zu je einem Absatz plus
    Belegzeile haben die Schlagzeile des Aufmachers aus dem ersten
    Bildschirm gedraengt - der Kurzpfad hat nicht den Weg zur Titelseite
    abgekuerzt, sondern sie ersetzt. Er steht jetzt in der rechten Spalte
    ueber "Was wichtig ist": derselbe erste Bildschirm, aber neben der
    Nachricht statt vor ihr.

    Geprueft wird die Reihenfolge INNERHALB der Spalte mit - die beiden
    Module sortieren nach derselben Achse, und der kuerzere fuehrt."""
    hs = [_ctm_highlight(1, ctm_bezug=3, relevance=5,
                         satz="Drückt unsere Preisuntergrenze deutlich.",
                         operator="Deutsche Telekom")] + PORTAL
    html = _seite(_render(tmp_path, highlights=hs), "index.html")
    assert "In zwei Minuten" in html
    assert html.index("front-oben") < html.index("kurzpfad")
    soup = BeautifulSoup(html, "html.parser")
    spalte = soup.select_one(".front-wichtig")
    assert spalte.select_one(".kurzpfad") is not None
    # Der Kurzpfad zuerst, die Digest-Spalte darunter.
    rubriken = [h2.get_text(strip=True) for h2 in spalte.select("h2")]
    assert rubriken[:2] == ["In zwei Minuten", "Was wichtig ist"]


def test_zwei_minuten_zeigt_nur_saetze_mit_quelle(tmp_path):
    hs = [_ctm_highlight(1, ctm_bezug=3, relevance=5,
                         satz="Drückt unsere Preisuntergrenze deutlich.",
                         operator="Deutsche Telekom")] + PORTAL
    soup = BeautifulSoup(_seite(_render(tmp_path, highlights=hs),
                                "index.html"), "html.parser")
    zeilen = soup.select(".kurzpfad-zeile")
    assert zeilen
    for z in zeilen:
        assert z.select_one(".kurzpfad-satz").get_text(strip=True)
        assert z.select_one(".kurzpfad-beleg a")["href"].startswith("http")


def test_ohne_direkten_bezug_faellt_der_kasten_weg(tmp_path):
    """Eine Woche ohne Portfoliofrage ist ein Befund, kein Loch, das man mit
    Fuellzeilen schliesst."""
    html = _seite(_render(tmp_path, highlights=PORTAL), "index.html")
    assert "In zwei Minuten" not in html


def test_die_dringlichere_meldung_steht_vor_der_direkten(tmp_path):
    """Der Name stand bis zum 28.08.2026 andersherum und beschrieb damit die
    Regel VOR dem 27.08.2026 - das Verhalten war laengst umgekehrt, nur der
    Name log. Ein Testname ist die kuerzeste Fassung der Zusicherung; wer die
    Liste der Testnamen liest, liest sonst das Gegenteil dessen, was der Code
    tut.

    Antonio, 27.08.2026 (Strategie E6): "wie kann es sein dass artikel
    mit prioriät von 3 auf der titelseite landen ... die wichtigsten
    artikel sollen auch an erster reihe stehen." Bis dahin fuehrte der
    CTM-Bezug (Eingriff vom 07.08.2026: "OpenAI macht ChatGPT gratis
    unbegrenzt", Prioritaet 5, stand HINTER der Telekom-Flat fuer 34,95
    Euro, Prioritaet 3, weil deren CTM-Bezug hoeher war). Seit dem
    27.08.2026 fuehrt die Prioritaet, der CTM-Bezug bricht nur noch den
    Gleichstand (`html._rangschluessel`) - dieser Test ist deshalb
    UMGEKEHRT: die branchenweite Meldung mit der hoeheren Prioritaet
    steht jetzt VOR der Heimatmarkt-Meldung mit der niedrigeren, obwohl
    deren CTM-Bezug staerker ist."""
    welt = _ctm_highlight(90, ctm_bezug=1, relevance=5, operator="OpenAI")
    welt["title"] = "OpenAI macht ChatGPT für Gratisnutzer unlimitiert"
    heimat = _ctm_highlight(91, ctm_bezug=3, relevance=3,
                            operator="Deutsche Telekom")
    heimat["title"] = "Telekom-Flatrate mit Unlimited-Daten für 34,95 Euro"
    soup = BeautifulSoup(_seite(_render(tmp_path, highlights=[welt, heimat]),
                                "meldungen.html"), "html.parser")
    zeilen = [e.get_text(" ", strip=True) for e in soup.select(".szl")]
    assert any("34,95" in z for z in zeilen)
    erste_heimat = next(i for i, z in enumerate(zeilen) if "34,95" in z)
    erste_welt = next(i for i, z in enumerate(zeilen) if "ChatGPT" in z)
    assert erste_welt < erste_heimat


def test_alte_ausgaben_ohne_ctm_feld_behalten_ihre_reihenfolge(tmp_path):
    """Berichte von vor dem 08.08.2026 tragen das Feld nicht. Sie duerfen
    nicht alle auf Stufe 0 fallen - dann ordnete die Prioritaet nichts mehr,
    und eine Archivwoche kaeme in willkuerlicher Reihenfolge."""
    soup = BeautifulSoup(_seite(_render(tmp_path), "meldungen.html"),
                         "html.parser")
    zeilen = [e.get_text(" ", strip=True) for e in soup.select(".szl")]
    nummern = [int(re.search(r"Meldung (\d+)", z).group(1))
               for z in zeilen if re.search(r"Meldung (\d+)", z)]
    # HIGHLIGHTS: 0-3 tragen Prioritaet 5, 4-7 die 4, 8-11 die 3.
    stark = [n for n in nummern if n < 4]
    schwach = [n for n in nummern if n >= 8]
    assert stark and schwach
    assert nummern.index(stark[0]) < nummern.index(schwach[0])


def test_der_folgerungssatz_traegt_seine_marke(tmp_path):
    """Ohne die Marke liest er sich als zweite Zusammenfassung."""
    hs = [_ctm_highlight(1, ctm_bezug=3, relevance=5,
                         satz="Drückt unsere Preisuntergrenze deutlich.")] + PORTAL
    for seite in ("index.html", "meldungen.html"):
        soup = BeautifulSoup(_seite(_render(tmp_path / seite, highlights=hs),
                                    seite), "html.parser")
        satz = soup.select_one(".ctm-satz")
        assert satz is not None, seite
        assert satz.select_one(".ctm-marke").get_text(strip=True) == \
            "Was das für uns heißt"


def test_belege_eines_ereignisses_stehen_unter_der_meldung(tmp_path):
    """Die weiteren Quellen desselben Ereignisses (analyze/clustering.py) -
    einzeln anklickbar und NICHT als eigene Meldungszeile."""
    h = _highlight(1, 5, "Tarif/Pricing")
    h["weitere_quellen"] = [
        {"source": "Light Reading", "url": "https://lr.test/1", "title": "A"},
        {"source": "Telecoms.com", "url": "https://tc.test/2", "title": "B"}]
    h["quellenzahl"] = 3
    soup = BeautifulSoup(_seite(_render(tmp_path, highlights=[h] + PORTAL),
                                "meldungen.html"), "html.parser")
    belege = soup.select_one(".mz-belege")
    assert belege is not None
    assert len(belege.select("a")) == 2
    # Ein Link im Link waere ungueltiges HTML - die Belege muessen ausserhalb
    # des Meldungslinks stehen.
    assert belege.find_parent("a") is None


# ==========================================================================
# P1/F3 (A3, 17.09.2026): die Zahlen auf den MODELL-KARTEN des
# Vergleichs-Reiters. Die Karte ist der Schnelleingang der Tafel und
# traegt drei Zahlen (ab-Preis, Ø/Monat, Bewegungs-Delta) - jede wird
# gegen einen ZWEITEN Aufbereitungs-Lauf ueber denselben Bestand gehalten
# (Seite gegen Daten, nicht Vorlage gegen sich selbst). get_text OHNE
# Trenner: der Trenner machte aus "24" und "54 Modelle" einmal "2454"
# (30.08.2026) - derselbe Fehlertyp wie der Anlass dieser Datei.
# ==========================================================================

def _geraete_kartenzahl_site(tmp_path):
    from telco_radar.geraete_config import lade_katalog, lade_quellen
    from telco_radar.report import geraete_view, geraete_zeitreihe
    from test_geraete_zeitreihe_ansicht import HEUTE as ZR_HEUTE, _baue
    root, state = _baue(tmp_path)
    reports = root / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"{ZR_HEUTE}.json").write_text(json.dumps({
        "date": ZR_HEUTE, "language": "de",
        "briefing_md": "## Auf einen Blick\n\n- Nichts.\n",
        "stats": {}, "regions": []}), encoding="utf-8")
    (reports / f"{ZR_HEUTE}.md").write_text("# B\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    g = geraete_view.aufbereiten(state, lade_quellen(root),
                                 lade_katalog(root), heute=ZR_HEUTE)
    aufbereitung = geraete_zeitreihe.aufbereiten(state, g["tco"])
    return site, aufbereitung


def test_die_kartenzahlen_stehen_wortlich_auf_der_seite(tmp_path):
    site, aufbereitung = _geraete_kartenzahl_site(tmp_path)
    soup = BeautifulSoup((site / "geraete.html").read_text(encoding="utf-8"),
                         "html.parser")
    karten = soup.select("#gr-zr-kacheln button[data-modell]")
    assert karten, "die Modell-Karten fehlen auf der Geräteseite"
    assert len(karten) == len(aufbereitung["kacheln"]), \
        (f"{len(karten)} Karten auf der Seite, "
         f"{len(aufbereitung['kacheln'])} in der Aufbereitung")
    text_je_id = {k.get("data-modell"): k.get_text() for k in karten}
    assert len(text_je_id) == len(aufbereitung["kacheln"]), \
        "dieselbe Karte zweimal auf der Seite"
    for k in aufbereitung["kacheln"]:
        text = text_je_id[k["id"]]
        assert k["kurz"] in text, f"Name fehlt auf der Karte {k['id']}"
        # P1-Fix (Sicht-B2): die Zahlen stehen JE BAND auf der Karte - jede
        # Bandlage muss wortlich da sein (get_text liest hidden mit).
        assert set(k["baender"]), f"Karte {k['id']} ohne Band-Werte"
        for band, s in k["baender"].items():
            if s["ab"]:
                assert s["ab"] in text, \
                    f"ab-Preis {s['ab']} ({band}) fehlt auf {k['id']}"
                if s["ab_monat"]:
                    assert s["ab_monat"] in text, \
                        f"Ø/Monat {s['ab_monat']} ({band}) fehlt auf {k['id']}"
            if s["delta_text"]:
                assert s["delta_text"] in text, \
                    f"Bewegung {s['delta_text']} ({band}) fehlt auf {k['id']}"


def test_keine_karte_zeigt_zahlen_die_die_aufbereitung_nicht_hat(
        tmp_path):
    """Gegenprobe: der Karten-Text der Seite besteht NUR aus Feldern der
    Aufbereitung - kein Zahlfragment, das dort nicht herkommt (waere die
    Vorlage auf eigene Rechnung gerechnet)."""
    import re
    site, aufbereitung = _geraete_kartenzahl_site(tmp_path)
    soup = BeautifulSoup((site / "geraete.html").read_text(encoding="utf-8"),
                         "html.parser")
    erlaubt = set()
    for k in aufbereitung["kacheln"]:
        erlaubt |= {k["kurz"], "ab"}
        for s in k["baender"].values():
            erlaubt |= {s["ab"], s["ab_monat"], s["delta_text"],
                        s["anbieter_text"]}
    erlaubt |= {t for k in aufbereitung["kacheln"] for t in k["kurz"].split()}
    erlaubt.discard(None)
    for karte in soup.select("#gr-zr-kacheln button[data-modell]"):
        for wort in re.findall(r"[\d.,]+ ?(?:€|€/Monat|Tag(?:en)?)",
                               karte.get_text()):
            assert wort in erlaubt or any(
                wort in (f or "") for f in erlaubt if f), \
                f"Zahl {wort!r} steht auf der Karte, aber nicht in der " \
                f"Aufbereitung"


def test_die_katalog_leitzahl_ist_der_guenstigste_zeilenpreis(tmp_path):
    """P4-Fix (Sicht-Pruefung 18.09., Falz 1): die Katalog-Leitzahl ist der
    guenstigste Einzelgeraetepreis des Regals - gehalten gegen DIESELBEN
    Zahlen, die in den Zeilen stehen (data-s-preis, der Rohwert der
    ab-Preis-Spalte). Nicht gegen den View-Wert derselben Rechnung: das
    waere zirkulaer; hier steht Zelle gegen Zelle (CLAUDE.md §6: eine Zahl
    auf der Seite ist erst wahr, wenn ein Test sie gegen die Daten haelt).
    Ohne Barpreis im ganzen Regal gibt es keine Leitzahl (Gatter)."""
    import re
    site, _aufbereitung = _geraete_kartenzahl_site(tmp_path)
    soup = BeautifulSoup((site / "geraete.html").read_text(encoding="utf-8"),
                         "html.parser")
    zeilen = soup.select("#gr-katalogtabelle tr.gr-k-zeile")
    assert zeilen, "keine Katalog-Modellzeile - der Test prueft nichts"
    preise = [float(z["data-s-preis"]) for z in zeilen
              if (z.get("data-s-preis") or "").strip()]
    leit = soup.select_one("#tafel-katalog .gr-leit--katalog .gr-leit-zahl")
    assert preise, "Fixture ohne einen einzigen ab-Preis - Gatterfall, " \
                   "der Test braeuchte die andere Lage"
    assert leit is not None, \
        "Katalog ohne Leitzahl, obwohl Zeilen mit ab-Preis dastehen"
    zahl = leit.get_text(" ", strip=True)
    match = re.match(r"^([\d.]+,\d\d) €$", zahl)
    assert match, f"Leitzahl ist kein Preis: {zahl!r}"
    assert float(match.group(1).replace(".", "").replace(",", ".")) \
        == min(preise), \
        f"Leitzahl {zahl} != guenstigster Zeilenpreis {min(preise)}"


# ==========================================================================
# P1/F2 (A4, 17.09.2026): die Zahlen der RECHENWEG-VORLAGEN (Panel-Posten).
# Jeder Kurvenpunkt und die Preiszahl oeffnen auf Klick die Rechung genau
# dieser Messung; die Posten stehen serverseitig als <template> im First
# Paint. Auch diese Zahlen gelten erst, wenn ein Test sie gegen die Daten
# haelt: jede Zahl der Seite muss im ZWEITEN Aufbereitungs-Lauf ueber
# denselben Bestand stehen (die Vorlage darf nichts selbst rechnen oder
# formatieren). Dass die Posten die eingefrorene Leitzahl ergeben, hat
# A1 in test_geraete_zeitreihe_rechenweg.py nachgerechnet (2562/2562 am
# echten Bestand) - hier wird nur die SEITE gegen die Aufbereitung gehalten.
# ==========================================================================

def test_die_panel_posten_kommen_aus_der_aufbereitung(tmp_path):
    import re as _re
    site, aufbereitung = _geraete_kartenzahl_site(tmp_path)
    soup = BeautifulSoup((site / "geraete.html").read_text(encoding="utf-8"),
                         "html.parser")
    first_paint = soup.select(
        "#gr-zr-gruppe .gr-zr-rechnungen template[data-anb]")
    assert first_paint, "die Rechenweg-Vorlagen fehlen im First Paint"
    fragment = BeautifulSoup(
        (site / "data" / "geraete-zeitreihe.html").read_text("utf-8"),
        "html.parser").select("template[data-anb]")
    assert fragment, "das Zeitreihen-Fragment traegt keine Vorlagen"
    # Wächter (§6): der Lookup darf nicht teilweise treffen. Der First
    # Paint traegt NUR das Startpaar, das Fragment ALLE Paare - beide
    # Zahlen muessen gegen die Aufbereitung stimmen, sonst waere der
    # Zahl-Vergleich darunter grün, ohne etwas zu prüfen.
    start = aufbereitung["start_block"]
    assert start is not None, "die Aufbereitung nennt kein Startpaar"
    vorlagen_start = start["rechenweg_html"].count("<template")
    vorlagen_alle = sum(p["rechenweg_html"].count("<template")
                        for p in aufbereitung["paare"])
    assert len(first_paint) == vorlagen_start, \
        (f"{len(first_paint)} Vorlagen im First Paint, {vorlagen_start} "
         f"beim Startpaar der Aufbereitung")
    assert len(fragment) == vorlagen_alle, \
        (f"{len(fragment)} Vorlagen im Fragment, {vorlagen_alle} in der "
         f"Aufbereitung")
    quelle = "\n".join(p["rechenweg_html"] for p in aufbereitung["paare"])
    assert quelle, "die Aufbereitung liefert keine Rechenweg-Zeichen"
    # Gegenprobe im selben Test (§6): eine Zusicherung, die nichts
    # ausschließt, prüft nichts - ein erfundener Betrag darf nie
    # durchgehen.
    assert "999999,99 €" not in quelle
    for t in list(first_paint) + list(fragment):
        for zahl in _re.findall(r"[0-9][0-9.,]*", t.get_text(" ", strip=True)):
            assert zahl in quelle, \
                f"Zahl {zahl!r} im Rechenweg-Panel kommt nicht aus der " \
                f"Aufbereitung (Vorlage gerechnet statt gesetzt?)"


# ==========================================================================
# P3 (Strategie Geraete v3, 18.09.2026): die Zahlen des GERÄTEKATALOGS
# auf Modellebene. DIE EINE REGEL des Auftrags: keine Katalogzeile sagt
# "ohne Preis" - jede Modellzeile trägt einen Barpreis ("ab X € bei Y")
# oder den benannten Bündel-Zustand ("nur im Bündel, ab X €/Monat"), und
# die 1&1-Listungszeilen tragen ihre Bündel-Angabe im Aufklapper.
# Gemessen wird an der GERENDERTEN Seite gegen einen ZWEITEN Aufbereitungs-
# lauf über denselben Bestand - Zahlen OHNE get_text-Trenner gelesen
# (derselbe Fehlertyp wie "2454 Modelle", 30.08.2026).
# ==========================================================================

def _geraete_katalog_site(tmp_path):
    """Eine Katalog-Seite, die ALLE Preisdarstellungen des P3-Katalogs
    aufspannt: Barpreis mit Beleg, Spanne (wesentlich), Bündel-Modellzeile
    (nur 1&1, ohne jeden Barpreis) und die 1&1-AUFKLAPPERZEILE mit
    Bündel-Angabe - ohne den Bündelstore wuerde genau diese Zeile "ohne
    Preis" sagen, deshalb spannt die Fixture den Fall wirklich auf."""
    import yaml
    from telco_radar.geraete_config import lade_katalog, lade_quellen
    from telco_radar.report import geraete_view
    root = tmp_path / "katalog"
    (root / "config").mkdir(parents=True)
    katalog = {"geraete": [
        {"hersteller": "Apple", "modell": "Apple X", "generation": 1,
         "speicher": [256], "segment": "flagship"},
        {"hersteller": "Samsung", "modell": "Galaxy S26 Ultra",
         "generation": 26, "speicher": [256], "segment": "flagship"},
        {"hersteller": "Google", "modell": "Pixel 11", "generation": 11,
         "speicher": [128], "segment": "flagship"},
    ]}
    quellen = {"anbieter": [
        {"name": "A-Laden", "typ": "handel", "rang": 1, "methode": "ldjson",
         "basis_url": "https://a.example", "einstiege": [
             {"url": "https://a.example/liste"}]},
        {"name": "B-Laden", "typ": "handel", "rang": 2, "methode": "ldjson",
         "basis_url": "https://b.example", "einstiege": [
             {"url": "https://b.example/liste"}]},
        {"name": "1&1", "typ": "netzbetreiber", "rang": 3,
         "methode": "ldjson", "basis_url": "https://1und1.example",
         "einstiege": [{"url": "https://1und1.example/liste"}]},
    ]}
    for name, daten in (("geraete_katalog.yaml", katalog),
                        ("farben.yaml", {"farben": {"schwarz": ["Schwarz"]}}),
                        ("geraete_quellen.yaml", quellen)):
        (root / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False),
            encoding="utf-8")

    def _listung(anbieter, device, speicher, preis, **kw):
        sku = f"{device}-{speicher}gb-{anbieter.lower().replace('&', '')}"
        e = {"id": f"{anbieter.lower()}--{sku}", "sku_id": sku,
             "device_id": device, "anbieter": anbieter,
             "anbieter_typ": "handel", "speicher_gb": speicher,
             "farbe_roh": "Schwarz", "farbe_normalisiert": "schwarz",
             "zustand": "neu", "first_seen": "2026-09-01",
             "last_verified": "2026-09-17", "status": "aktiv",
             "missed_checks": 0, "preis_ohne_vertrag": preis,
             "zuzahlung": None, "quelle_url": f"https://example.de/{sku}",
             "abgerufen_am": "2026-09-17", "verfuegbarkeit": "lieferbar"}
        e.update(kw)
        return e

    # Galaxy S26 Ultra NUR bei 1&1 und OHNE Barpreis - die Modellzeile
    # muss "nur im Bündel" sagen, ihre Aufklapperzeile die Bündel-Angabe.
    # Die 1&1-Listung traegt ihren Bündel-Monatspreis WIE IM ECHTEN
    # BESTAND selbst (`preis_mit_vertrag_ab` + `tarif_referenz`, § 13.2):
    # genau daraus liest der S2-1-Fallback, wenn der Bündel-Store
    # unlesbar ist (siehe Test weiter unten).
    listungen = [
        _listung("A-Laden", "apple-x", 256, 1000.0),
        _listung("B-Laden", "apple-x", 256, 1100.0),
        _listung("1&1", "samsung-galaxy-s26-ultra", 256, None,
                 anbieter_typ="netzbetreiber",
                 tarif_referenz="1&1 All-Net-Flat S",
                 preis_mit_vertrag_ab=32.99),
        _listung("A-Laden", "google-pixel-11", 128, 799.0),
    ]
    state = root / "data" / "state"
    state.mkdir(parents=True)
    (state / "geraete_db.json").write_text(json.dumps(
        {"updated": "2026-09-17",
         "anbieter": {n: {"laeufe": 4} for n in
                      ("A-Laden", "B-Laden", "1&1")},
         "listungen": listungen}), encoding="utf-8")
    (state / "geraete_preise.jsonl").write_text("", encoding="utf-8")

    def _buendel(anbieter, device, speicher, tarif, monat, komplett):
        sku = f"{device}-{speicher}gb-{anbieter.lower().replace('&', '')}"
        # `komplett`: ein Bündel MIT Aufteilung in Tarifpreis und Geräte-
        # rate (so rechnet die TCO-Ansicht Karten). Sonst nennt der Satz
        # nur den Bündel-Monatspreis - 1&1-Regel § 13.2: EIN Betrag, und
        # beides nebeneinander verwirft der TCO-Leser zu Recht.
        b = {"id": f"buendel--{anbieter.lower()}--{sku}",
             "sku_id": sku, "anbieter": anbieter, "tarif_name": tarif,
             "tarif_id": f"{anbieter.lower()}:m", "tarif_id_guete": "hoch",
             "buendel_monatlich": None, "tarif_monatlich": 20.0,
             "geraet_zuzahlung": 1.0, "geraet_monatsrate": 12.99,
             "laufzeit_monate": 24, "anschlusspreis": 0.0,
             "zustand": "neu", "rabatte": [],
             "quelle_url": f"https://example.de/{sku}/buendel",
             "abgerufen_am": "2026-09-17",
             "first_seen": "2026-09-17", "last_verified": "2026-09-17"}
        if komplett:
            return b
        b["tarif_monatlich"] = None
        b["geraet_monatsrate"] = None
        b["buendel_monatlich"] = monat
        return b

    (state / "geraete_tco.json").write_text(json.dumps(
        {"updated": "2026-09-17",
         "buendel": [_buendel("1&1", "samsung-galaxy-s26-ultra", 256,
                              "1&1 All-Net-Flat S", 32.99, komplett=False),
                     _buendel("A-Laden", "apple-x", 256, "A M", 41.0,
                              komplett=True)],
         "sim_only": []}), encoding="utf-8")
    (state / "geraete_tco_historie.jsonl").write_text("", encoding="utf-8")
    tarife = [{"anbieter": b["anbieter"], "name": b["tarif_name"],
               "tarif_id": b["tarif_id"], "tarif_id_guete": "hoch",
               "grundgebuehr": b["tarif_monatlich"],
               "mindestlaufzeit_monate": 24, "rabattphasen": [],
               "quelle_url": b["quelle_url"],
               "abgerufen_am": "2026-09-17"}
              for b in (state / "geraete_tco.json").exists() and
              json.loads((state / "geraete_tco.json").read_text())["buendel"]]
    (state / "tarife.jsonl").write_text(
        "\n".join(json.dumps(t) for t in tarife) + "\n", encoding="utf-8")

    reports = root / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / "2026-09-17.json").write_text(json.dumps(
        {"date": "2026-09-17", "language": "de",
         "briefing_md": "## Auf einen Blick\n\n- Nichts.\n",
         "stats": {}, "regions": []}), encoding="utf-8")
    (reports / "2026-09-17.md").write_text("# B\n", encoding="utf-8")
    site = root / "site"
    # BEWUSST ohne cfg (S4-4 der P3-Code-Pruefung): geraete.html braucht
    # keines - aber NUR hier. render_site() OHNE cfg rendert sonst eine
    # still halbe Seite (CLAUDE.md §6: transparenz.html verliert seinen
    # Quellenbestand, wettbewerb.html den halben Inhalt). Wer diese Zeile
    # in eine Welt mit watchlist/news_sources KOPIERT, kopiert die Falle -
    # dort `load_config(root)` mitgeben.
    render_site(site, reports)
    g = geraete_view.aufbereiten(state, lade_quellen(root),
                                 lade_katalog(root), heute="2026-09-17")
    return site, g


def _katalog_suppe(site):
    return BeautifulSoup((site / "geraete.html").read_text(encoding="utf-8"),
                         "html.parser")


def test_keine_katalogzeile_sagt_ohne_preis(tmp_path):
    """DIE EINE REGEL des P3-Auftrags, an der gerenderten Seite: 36 Zeilen
    sagten "ohne Preis", obwohl der Preis da war (1&1: nur im Bündel).
    Die Fixture spannt genau den Fall auf - OHNE den Bündelstore wuerde die
    1&1-Zeile das Wort rendern, der Test prueft also die Regel, nicht nur
    den Glücksfall eines vollen Bestands."""
    site, g = _geraete_katalog_site(tmp_path)
    suppe = _katalog_suppe(site)
    tafel = suppe.select_one("#tafel-katalog")
    assert tafel, "Katalogtafel fehlt"
    assert "ohne Preis" not in tafel.get_text(), (
        'eine Zeile des Katalogs sagt "ohne Preis"')
    # Gegenprobe im selben Test: die 1&1-Zeile ist DA und hat keinen
    # Barpreis - der Zustand, der das Wort frueher ausgeloest hat.
    ohne_barpreis = [m for m in g["katalog_modelle"]
                     if m["ab_preis"] is None]
    assert ohne_barpreis, "die Fixture spannt den Fall nicht auf"
    nur_buendel = [m for m in ohne_barpreis if m["nur_buendel"]]
    assert nur_buendel, "kein Modell im Bündel-Zustand - Test prüft nichts"


def test_der_buendel_zustand_steht_wortlich_auf_der_seite(tmp_path):
    """Die 1&1-Bündel-Angabe muss WORTLICH da stehen: "nur im Bündel" nebst
    Monatspreis in der MODELLZEILE, "ab X €/Monat" mit Beleg-Link in der
    AUFKLAPPERZEILE der Listung - jede Zahl gegen die Aufbereitung, nicht
    gegen die Vorlage. Zahlen ohne get_text-Trenner gelesen."""
    site, g = _geraete_katalog_site(tmp_path)
    suppe = _katalog_suppe(site)
    modell = next(m for m in g["katalog_modelle"] if m["nur_buendel"])
    erwartet_monat = f"{modell['buendel_monat']:.2f}".replace(".", ",")
    text_seite = suppe.select_one("#tafel-katalog").get_text()
    assert "nur im Bündel" in text_seite
    assert f"ab {erwartet_monat} €/Monat" in text_seite, (
        f"der Bündel-Monatspreis {erwartet_monat} fehlt wortlich")
    # Der Beleg der Modellzeile ist verlinkt (Belegzwang).
    modellzeile = next(z for z in suppe.select("#gr-katalogtabelle .gr-k-zeile")
                       if "Galaxy S26 Ultra" in (z.get("data-s-geraet") or ""))
    links = [a.get("href") for a in modellzeile.select("a.gr-a-quelle")]
    assert modell["buendel_beleg"]["quelle_url"] in links, (
        f"der Bündel-Beleg fehlt unter den Links der Modellzeile: {links}")
    # Und die AUFKLAPPERZEILE derselben 1&1-Listung traegt ihre Angabe
    # samt Tarifnamen - dieselbe Zahl, derselbe Beleg.
    auf = suppe.select_one(f"#{modellzeile['data-auf']}")
    zeilen = [r for r in auf.select("tr") if r.select_one("td") is not None
              and "1&1" in r.select_one("td").get_text()]
    assert zeilen, "die 1&1-Listungszeile fehlt im Aufklapper"
    text_auf = zeilen[0].get_text()
    assert f"ab {erwartet_monat} €/Monat" in text_auf
    assert modell["buendel_tarif"] in text_auf


def test_jede_preisspalte_hat_genau_ein_format(tmp_path):
    """Der Befund vor P3: drei Preisformate in EINER Spalte. Seit P3 hat
    jede Spalte je Ansicht GENAU EIN Format - gemessen als EIN Regex, dem
    JEDE Betragsangabe der Spalte folgen muss (deutsch: Punkt als
    Tausender, Komma als Dezimal, zwei Stellen, Euro). Ein Betrag, der
    dem Muster nicht folgt, ist der Fehlertyp "1.099,00 € neben 1.099 €".
    """
    import re as _re
    site, _g = _geraete_katalog_site(tmp_path)
    suppe = _katalog_suppe(site)
    zeilen = suppe.select("#gr-katalogtabelle .gr-k-zeile")
    assert len(zeilen) >= 3, "zu wenige Modellzeilen für einen Formatvergleich"
    betrag = _re.compile(r"\d[\d.]*,\d\d €(?:/Monat)?")
    ein_format = _re.compile(r"^\d{1,3}(?:\.\d{3})*,\d\d €$")

    def _pruefe(zellen, name, kennwort_nötig=True):
        texte = [z.get_text() for z in zellen]
        preise = [b for t in texte for b in betrag.findall(t)]
        assert preise, f"keine Beträge in {name}"
        for z, t in zip(zellen, texte):
            for b in betrag.findall(t):
                if b.endswith("/Monat"):
                    # Der Monatsbetrag ist die benannte Bündel-Angabe. In
                    # der MODELL-Zelle braucht er sein Kennwort "nur im
                    # Bündel" (sonst waere er ein nackter Preis unter
                    # Einmalbeträgen); in der LISTUNGS-Zeile des Auf-
                    # klappers steht er mit "ab"-Vorspann und Tarifnamen
                    # - genau die 1&1-Regel des P3-Auftrags.
                    if kennwort_nötig:
                        assert "nur im Bündel" in t, (
                            f"{name}: Monatsbetrag {b!r} ohne das "
                            "Kennwort 'nur im Bündel' in der Zelle")
                    assert ein_format.match(b[:-len("/Monat")]), (
                        f"{name}: Bündel-Betrag {b!r} folgt nicht dem "
                        "einen Format")
                else:
                    assert ein_format.match(b), (
                        f"{name}: Betrag {b!r} folgt nicht dem einen "
                        "Format (deutsch, zwei Dezimalstellen)")

    # Ansicht Einzelgerätpreis: Modell-Preiszelle, Spannen-Zelle und die
    # Listungs-Preiszellen des Aufklappers - je EIN Format. Die Spanne
    # "X – Y" besteht aus zwei Beträgen, die JEDEM dem Muster folgen.
    _pruefe([z.select("td.gr-sp--barpreis")[0] for z in zeilen],
            "der Einzelgerätepreis-Spalte")
    _pruefe([z.select("td.gr-sp--barpreis")[2] for z in zeilen
             if "€" in z.select("td.gr-sp--barpreis")[2].get_text()],
            "der Spannen-Spalte")
    _pruefe([r.select("td")[2] for r in
             suppe.select("#gr-katalogtabelle .gr-k-listungen tr")
             if r.select_one("td") is not None
             and "€" in r.select("td")[2].get_text()],
            "der Aufklapper-Preisspalte", kennwort_nötig=False)
    # Ansicht Gesamtkosten: TCO-24-Zelle und Ø €/Monat-Zelle. Der
    # Monatsbetrag trägt seinen Zusatz "/Monat" - ein EINMALBETrag in der
    # Monats-Spalte waere die schlimmere Vermischung.
    _pruefe([z.select("td.gr-sp--tco")[0] for z in zeilen
             if "€" in z.select("td.gr-sp--tco")[0].get_text()],
            "der TCO-24-Spalte")
    monat_zellen = [z.select("td.gr-sp--tco")[1] for z in zeilen
                    if "€" in z.select("td.gr-sp--tco")[1].get_text()]
    if monat_zellen:
        _pruefe(monat_zellen, "der Ø €/Monat-Spalte", kennwort_nötig=False)
        # EIN Format heisst auch: eine Einheiten-Schreibweise je Spalte.
        # Die Ø-Spalte trägt ihre Einheit im KOPF ("Ø €/Monat") und ihre
        # Beträge ohne Zusatz - gemischt waere der Fehlertyp.
        schreibweisen = {b.endswith("/Monat")
                         for z in monat_zellen
                         for b in betrag.findall(z.get_text())}
        assert len(schreibweisen) == 1, (
            f"die Ø €/Monat-Spalte mischt Beträge mit und ohne /Monat: "
            f"{schreibweisen}")


def test_die_modellzahl_steht_an_allen_orten_derselben_zahl(tmp_path):
    """Die Modellzahl der Rubrik, der DOM-Zeilen und der Aufklapper muss
    der Aufbereitung entsprechen - gegen den ZWEITEN Lauf über denselben
    Bestand. OHNE get_text-Trenner gelesen: der Trenner machte aus "24"
    und "54 Modelle" einmal "2454"."""
    site, g = _geraete_katalog_site(tmp_path)
    suppe = _katalog_suppe(site)
    modelle = g["katalog_modelle"]
    assert len(modelle) >= 3, "zu wenige Modelle für einen Zahlenvergleich"
    rubrik = suppe.select_one(".gr-katalog h2 .rubrik-zahl").get_text()
    assert rubrik == str(len(modelle)), (
        f"Rubrik sagt {rubrik}, Aufbereitung kennt {len(modelle)} Modelle")
    assert len(suppe.select("#gr-katalogtabelle .gr-k-zeile")) == len(modelle)
    assert len(supe := suppe.select("#gr-katalogtabelle .gr-a-auf")) == len(
        modelle), "Aufklapperzahl != Modellzahl"
    # Und die Listungen summieren zurück: jede Listung des Bestands steht
    # GENAU EINMAL in einem Aufklapper.
    aufklappzeilen = suppe.select("#gr-katalogtabelle .gr-k-listungen tr td")
    anzahl_listungszeilen = sum(
        1 for r in suppe.select("#gr-katalogtabelle .gr-k-listungen tr")
        if r.select_one("td") is not None)
    erwartet = sum(m["listungen"] for m in modelle)
    assert anzahl_listungszeilen == erwartet, (
        f"{anzahl_listungszeilen} Aufklapperzeilen, die Aufbereitung "
        f"zählt {erwartet} Listungen")
    assert aufklappzeilen, "keine Zellen im Aufklapper"


def test_der_katalog_uebersteht_einen_unlesbaren_tco_store(tmp_path):
    """S2-1 der P3-Code-Pruefung: ist `geraete_tco.json` unlesbar (z. B. ein
    abgebrochener Schreibvorgang des Nachtlaufs), liefert `TcoDB.buendel()`
    still [] - und der Katalog fiel auf "ohne Preis" zurueck, obwohl die
    1&1-Listungen ihren Bündel-Monatspreis selbst tragen. DIE P3-REGEL gilt
    auch im Fehlerfall: der Katalog liest die Bündel-Angabe dann aus der
    Listung, mit deren Beleg. Fehlerklasse B6 - eine kaputte Datei sieht aus
    wie eine leere Datenlage."""
    site, g = _geraete_katalog_site(tmp_path)
    root = site.parent
    mit_store = next(m for m in g["katalog_modelle"] if m["nur_buendel"])
    (root / "data" / "state" / "geraete_tco.json").write_text(
        '{"updated": "2026-09-17", "buendel": [KAPUTT', encoding="utf-8")
    render_site(site, root / "data" / "reports")
    suppe = _katalog_suppe(site)
    tafel = suppe.select_one("#tafel-katalog")
    assert tafel, "Katalogtafel fehlt"
    assert "ohne Preis" not in tafel.get_text(), (
        'der unlesbare Store darf keine Zeile auf "ohne Preis" fallen lassen')
    # Die Bündel-Angabe steht noch da - jetzt aus der LISTUNG gelesen:
    # derselbe Monatspreis (die 1&1-Listung traegt ihn selbst), der Beleg
    # ist der Quelllink DER LISTUNG statt des Stores.
    text = tafel.get_text()
    assert "nur im Bündel" in text
    erwartet = f"{mit_store['buendel_monat']:.2f}".replace(".", ",")
    assert f"ab {erwartet} €/Monat" in text, (
        f"der Bündel-Monatspreis {erwartet} fehlt ohne Store")
    zeile = next(z for z in suppe.select("#gr-katalogtabelle .gr-k-zeile")
                 if "Galaxy S26 Ultra" in (z.get("data-s-geraet") or ""))
    links = [a.get("href") for a in zeile.select("a.gr-a-quelle")]
    assert any("/samsung-galaxy-s26-ultra" in h for h in links), (
        f"der Beleg der Listung fehlt: {links}")


def test_die_delta_spalte_benennt_ihren_leergrund(tmp_path):
    """Sicht-Pruefung Wesentliches 3: 38 von 111 Zeilen der Live-Seite
    zeigten ein stummes "–" in der Delta-Spalte - TCO da, aber keine
    Vodafone-Referenz (Vodafone listet das Modell nicht). Das "–" ist
    seit dem Fix BENANNT ("keine Referenz", Grund im title); ein Modell
    OHNE Bündel behält das "–", weil seine TCO-Zelle den Grund schon
    nennt ("kein Bündel gemessen") - zwei verschiedene Stummen, nur eine
    braucht das Etikett."""
    site, g = _geraete_katalog_site(tmp_path)
    suppe = _katalog_suppe(site)
    zeilen = suppe.select("#gr-katalogtabelle .gr-k-zeile")
    je_modell = {z.get("data-s-geraet"): z for z in zeilen}
    # apple-x: Bündel MIT Aufteilung -> TCO-Zahl, aber keine Referenz in
    # der Fixture (kein Vodafone-Anbieter) -> "keine Referenz".
    apple = je_modell["Apple X 256 GB"]
    delta_apple = apple.select("td.gr-sp--tco")[2]
    assert "keine Referenz" in delta_apple.get_text(), (
        f"apple-x hat TCO ohne Referenz, die Zelle sagt stumm: "
        f"{delta_apple.get_text()!r}")
    assert delta_apple.select_one("[title]"), (
        "der Grund steht nicht im title der Zelle")
    # samsung: TCO aus dem 1&1-Monatspreis (32,99 × 24 + 1 Zuzahlung),
    # ebenfalls ohne Referenz - dasselbe Etikett.
    samsung = je_modell["Samsung Galaxy S26 Ultra 256 GB"]
    assert "keine Referenz" in samsung.select(
        "td.gr-sp--tco")[2].get_text()
    # pixel: KEIN Bündel -> die TCO-Zelle nennt ihren eigenen Grund
    # ("kein Bündel gemessen"), die Delta-Zelle bleibt "–" - zwei
    # Stummen, aber nur eine braucht das Etikett.
    pixel = je_modell["Google Pixel 11 128 GB"]
    assert "kein Bündel gemessen" in pixel.select(
        "td.gr-sp--tco")[0].get_text()
    assert pixel.select("td.gr-sp--tco")[2].get_text().strip() == "–"
    # Gegenprobe an der Aufbereitung: die Unterscheidung ist Datenlage,
    # nicht Vorlage - apple traegt tco_ab ohne delta_kurz.
    a = next(m for m in g["katalog_modelle"] if "Apple X" in m["titel"])
    assert a["tco_ab"] is not None and a["tco_delta_kurz"] is None


def test_ein_haendler_heisst_in_der_spanne_ein_preis(tmp_path):
    """Sicht-Pruefung Kleineres 4: 62 von 111 Live-Modellen hatten kein
    "–" als Spanne, weil es nur EINEN Preis gibt - die Zelle sagt das
    jetzt selbst statt stumm zu bleiben. Ein Modell mit mehreren Händlern
    und unwesentlichem Abstand behält "–" (echte Spanne, nur klein)."""
    site, g = _geraete_katalog_site(tmp_path)
    suppe = _katalog_suppe(site)
    je_modell = {z.get("data-s-geraet"): z for z in
                 suppe.select("#gr-katalogtabelle .gr-k-zeile")}
    pixel = je_modell["Google Pixel 11 128 GB"]
    assert pixel.select("td.gr-sp--barpreis")[2].get_text(
    ).strip() == "ein Preis", "ein Händler, aber keine Aussage in der Zelle"
    # Gegenprobe: Apple hat ZWEI Händler mit wesentlichem Abstand (1000
    # gegen 1100) - dort steht die echte Spanne, nicht das Etikett.
    apple = je_modell["Apple X 256 GB"]
    spannen_text = apple.select("td.gr-sp--barpreis")[2].get_text()
    assert "1.000,00 € – 1.100,00 €" in spannen_text, (
        f"die Spanne fehlt: {spannen_text!r}")
    assert "ein Preis" not in spannen_text


# ==========================================================================
# v4-P0 (20.09.2026, seiten-pruefer): die LEITZAHL der Geraeteseite am
# GEFRORENEN Bestand. Die Abschnitte darueber (P1/F3, P1/F2, P3) halten
# die Seite gegen einen ZWEITEN Aufbereitungs-Lauf ueber Fixture-Bestaende;
# dieser Abschnitt haelt sie gegen den Bestand im Repo und gegen eine
# ZWEITE, UNABHAENGIGE RECHNUNG, die keinen Baustein des Bauern importiert
# (kein tco_model.tco_24, kein geraete_tco_karten, kein geraete_view):
# gerendert wird ueber render_site() in einen Wegwerfordner gegen
# data/reports des Repos (wie die Fixture in test_geraete_anbieterzaehlung.
# py:48), und jede gepruefte Zahl entsteht hier aus data/state/*.json und
# *.jsonl - nur lesend.
#
# Die Rechnung (Soll-Definition aus dem v4-Auftrag, Arithmetik in Cent mit
# decimal/ROUND_HALF_UP auf ganze Cent, Rundungsregeln offen benannt):
#
#   Leitzahl = Anzahlung
#            + Tarifsumme ueber 24 Monate - phasengewichtet, wenn das
#              Tarifblatt Preisphasen nennt, die zur MESSUNG am Buendel
#              passen; liegt die gemessene Monatsrate ausserhalb der
#              Phasenspanne (+/- 0,005 EUR), spricht das Blatt von einem
#              anderen Angebot und die MESSUNG gewinnt flach (dokumentierte
#              Regel geraete_tco_karten.phasen_fuer_buendel, QA-Fix vom
#              20.09.2026 - hier eigenstaendig nachgebaut, nicht importiert)
#            + alle Geraeteraten der eigenen Laufzeit, auch die nach
#              Monat 24 (Restschuld bleibt IN der Kennzahl)
#            + Anschlusspreis.
#   Buendelform (1&1, ein Monatsbetrag): Bündelbetrag x Laufzeit +
#   Zuzahlung + Anschlusspreis.
#   O/Monat = Leitzahl / 24, auf Cent gerundet (die Seite rundet flach
#   ueber Python round, also half-even; der Test akzeptiert half-even UND
#   half-up, da sie sich nur bei exakt einem halben Cent unterscheiden).
#
# Auswahl (A3, 20.09.2026): nur FRISCHE Bündel stellen Antwort-Satz und
# Referenz - "frisch" heisst hoechstens drei Tage zwischen `abgerufen_am`
# und dem Bezugstag, und der Bezugstag ist der SPAETERE von juengstem
# Bericht (reports/) und tco.updated (die Seite reicht den Berichtstag
# durch, render_site -> aufbereiten, und nimmt die spaetere Uhr; hier
# eigenstaendig nachgebaut in _gw_heute/_gw_frisch, nicht importiert).
# Gemessener Fall 20.09.: congstar Allnet Flat S vom 12.09. unterbot die
# frischen Vodafone-Bündel des iPhone 17 - ohne die Frische behauptete
# dieser Test einen Sieger, den die Seite zu Recht nicht mehr fuehrt.
#
# Mutationsnachweis (Pflicht des Auftrags, siehe
# test_mutation_eines_euros_am_pflichtfall_schlaegt_aus): einmal vor-
# gefuehrt am 20.09.2026 - Ergebnis im Kommentar dieses Tests.
#
# Kein heutiges Datum: der "aktuelle Stand" ist tco.updated aus den Daten,
# nie datetime.today(). Fehlt ein Geraet/Band im Bestand, skippt der Test
# mit benannter Luecke - geraten wird nichts.
# ==========================================================================
import csv as _gw_csv
from decimal import Decimal as _gw_Dez
from decimal import ROUND_HALF_EVEN as _gw_HEVEN
from decimal import ROUND_HALF_UP as _gw_HUP

_GW_WURZEL = Path(__file__).resolve().parents[1]
_GW_HORIZONT = 24
# Die Bandgrenzen der Vergleichsansicht (report/geraete_tco_band.py):
# kontinuierlich bis 20 GB klein, bis 60 GB mittel, darueber gross;
# FEHLEND und UNBEGRENZT sind kein Band (siehe _gw_band).
import math as _gw_math
import datetime as _gw_dt


def _gw_cent(wert) -> int:
    """Euro (float/str) -> ganze Cent, kaufmaennisch (HALF_UP)."""
    return int((_gw_Dez(str(wert)) * 100).quantize(_gw_Dez("1"),
                                                   rounding=_gw_HUP))


def _gw_dezimal(text: str) -> "_gw_Dez":
    """'1.459,00' -> Decimal('1459.00') (deutsches Zahlenformat der Seite)."""
    return _gw_Dez(text.replace(".", "").replace(",", "."))


def _gw_rohdaten() -> tuple[dict, dict, dict]:
    """(tco-store, tarifblaetter je id, geraete_db) - nur lesend."""
    tco = json.loads((_GW_WURZEL / "data" / "state" / "geraete_tco.json")
                     .read_text(encoding="utf-8"))
    # JE ID KOENNEN MEHRERE BLAETTER STEHEN (Lesarten und Staende) -
    # Phasen und Volumen nimmt der Test wie die Vorlage vom ersten Blatt,
    # das sie nennt.
    blaetter: dict[str, list] = {}
    for zeile in (_GW_WURZEL / "data" / "state" / "tarife.jsonl") \
            .read_text(encoding="utf-8").splitlines():
        if zeile.strip():
            blatt = json.loads(zeile)
            blaetter.setdefault(blatt["tarif_id"], []).append(blatt)
    db = json.loads((_GW_WURZEL / "data" / "state" / "geraete_db.json")
                    .read_text(encoding="utf-8"))
    return tco, blaetter, db


def _gw_phasen(buendel: dict, blaetter: dict) -> list[dict]:
    """Blatt-Phasen des Bündels - nur ohne Widerspruch zur Messung.

    Die Messung (tarif_monatlich) muss in der Preisspanne der Phasen
    liegen (einschliesslich, Toleranz ein halber Cent); sonst gewinnt die
    Messung flach und die Phasen gelten nicht. Ohne Messung gibt es keinen
    Widerspruch. Eigenbau nach der dokumentierten Regel, nicht importiert.
    """
    phasen = []
    for blatt in blaetter.get(buendel.get("tarif_id") or "", []):
        phasen = [p for p in (blatt.get("preisphasen") or [])
                  if p.get("betrag") is not None]
        if phasen:
            break
    messung = buendel.get("tarif_monatlich")
    if not phasen or messung is None:
        return phasen
    betraege = [_gw_Dez(str(p["betrag"])) for p in phasen]
    toleranz = _gw_Dez("0.005")
    if min(betraege) - toleranz <= _gw_Dez(str(messung)) <= max(betraege) \
            + toleranz:
        return phasen
    return []


def _gw_phasensumme(phasen: list[dict], horizont: int) -> int:
    """Monatsentgelte ueber den Horizont, phasengewichtet, in Cent.

    Phase ohne Ende laeuft bis zum Horizont, darueber hinausreichende
    werden gekappt, Monate nach der letzten Phase laufen zum letzten
    bekannten Preis weiter (der letzte Preis eines Tarifs ist der
    Normalpreis, nicht der Rabattpreis).
    """
    summe = abgedeckt = 0
    for phase in sorted(phasen, key=lambda p: p["von_monat"]):
        bis = horizont if phase.get("bis_monat") is None \
            else min(int(phase["bis_monat"]), horizont)
        monate = max(0, bis - int(phase["von_monat"]) + 1)
        if monate <= 0:
            continue
        summe += monate * _gw_cent(phase["betrag"])
        abgedeckt += monate
    if abgedeckt < horizont:
        letzter = max(phasen, key=lambda p: p["von_monat"])
        summe += (horizont - abgedeckt) * _gw_cent(letzter["betrag"])
    return summe


def _gw_leitzahl(buendel: dict, blaetter: dict) -> tuple:
    """(gesamt_cent, rest_cent) der Soll-Definition; None = Luecke."""
    laufzeit = int(buendel["laufzeit_monate"])
    offen = max(0, laufzeit - _GW_HORIZONT)
    if buendel.get("buendel_monatlich") is not None:
        monat = _gw_cent(buendel["buendel_monatlich"])
        teile = [monat * laufzeit, _gw_cent(buendel["geraet_zuzahlung"]),
                 _gw_cent(buendel["anschlusspreis"])]
        rest = monat * offen
    else:
        phasen = _gw_phasen(buendel, blaetter)
        tarif24 = _gw_phasensumme(phasen, _GW_HORIZONT) if phasen else None
        if tarif24 is None:
            if buendel.get("tarif_monatlich") is None:
                return None, None        # Tarifluecke: keine belastbare Zahl
            tarif24 = _gw_cent(buendel["tarif_monatlich"]) * _GW_HORIZONT
        rate = buendel.get("geraet_monatsrate")
        if rate is None:
            return None, None            # Ratenluecke
        rate_c = _gw_cent(rate)
        teile = [_gw_cent(buendel["geraet_zuzahlung"]), tarif24,
                 rate_c * laufzeit, _gw_cent(buendel["anschlusspreis"])]
        rest = rate_c * offen
    if any(t is None for t in teile):
        return None, None
    return sum(teile), rest


def _gw_band(buendel: dict, blaetter: dict) -> str | None:
    """Band aus dem Datenvolumen des Blatts - kontinuierlich, wie die Seite.

    bis 20 GB klein, bis 60 GB mittel, darueber gross. FEHLEND und
    UNBEGRENZT sind kein Band (`None`) - dieselbe Regel wie
    `geraete_tco_band.band_von_gb`: unbegrenzt ist eine Markierung am
    Tarif und keine Vergleichsstufe, und ein Tarif ohne Volumenangabe in
    "gross" waere eine erfundene Aussage. Kein 21/61-Raster: 20,5 GB
    liegt im Band mittel, nicht zwischen den Baendern.
    """
    gb = None
    for blatt in blaetter.get(buendel.get("tarif_id") or "", []):
        if blatt.get("datenvolumen_gb") is not None:
            gb = blatt["datenvolumen_gb"]
            break
    if gb is None:
        return None
    try:
        gb = float(gb)
    except (TypeError, ValueError):
        return None                     # 'unbegrenzt' o. a. ist kein Band
    if _gw_math.isnan(gb) or _gw_math.isinf(gb):
        return None
    if gb <= 20:
        return "klein"
    if gb <= 60:
        return "mittel"
    return "gross"


# Welche Stells ein Berichtsdatum sind - dieselbe Form, nach der
# `html._load_reports` filtert; hier eigenständig nachgebaut (der Orakel-
# Grundsatz dieses Abschnitts: nichts importieren, alles nachrechnen).
_GW_DATUM_STEM = re.compile(r"\d{4}-\d{2}-\d{2}")


def _gw_heute(tco: dict) -> str:
    """Der Bezugstag der Auswahl - EIGEN gerechnet, nicht importiert.

    Der SPAETERE von jüngstem Bericht (Stammname in reports/ - das
    Datum, das `render_site` als `heute` durchreicht) und dem `updated`
    des TCO-Stores. ISO-Tage vergleichen lexikographisch korrekt.

    S3a (Diff-Prüfung 21.09.2026): Die Uhr spiegelt die Seiten-Semantik.
    Gezaehlt werden nur Stems, die ein DATUM sind (ein Stray-JSON wie
    "entwurf.json" sortiert lexikalisch hinter jedem Datum und gewann
    vorher das max()), samt der .md-Faelle - deren Berichtsdatum ist der
    Stamm. Und ein unlesbares `updated` zaehlt nicht: Die Seite verwirft
    es ueber `_spaeterer_tag`, der Orakel tut dasselbe, sonst stellte er
    eine Uhr, die die Seite nie hat."""
    bericht = max((p.stem for p in
                   (_GW_WURZEL / "data" / "reports").glob("*")
                   if p.suffix in (".json", ".md")
                   and _GW_DATUM_STEM.fullmatch(p.stem)),
                  default="")
    aktualisiert = str(tco.get("updated") or "")
    if not _GW_DATUM_STEM.fullmatch(aktualisiert):
        aktualisiert = ""
    return max(bericht, aktualisiert)


def _gw_frisch(buendel: dict, heute: str) -> bool:
    """EIGENE Frische-Regel der Auswahl (A3): älter als drei Tage
    (dokumentiert in geraete_tco_karten.ALT_AB_TAGEN) führt kein Bündel
    mehr. Ein fehlendes oder unlesbares `abgerufen_am` ist „unbekannt“
    und zählt wie alt (Clean Code 4); ohne Bezugstag altert nichts."""
    if not heute:
        return True
    try:
        alter = (_gw_dt.date.fromisoformat(heute)
                 - _gw_dt.date.fromisoformat(
                     buendel.get("abgerufen_am") or "")).days
    except ValueError:
        return False
    return alter <= 3


def _gw_min_buendel(tco: dict, blaetter: dict, sku_präfix: str, band: str,
                    anbieter: str = ""):
    """Günstigstes neu-Bündel des Modells im Band nach EIGENER Rechnung.

    Auswahlmenge wie die Seite: Zustand neu (vergleichbar), eine
    belastbare Zahl (ohne Tarifgrundpreis zaehlt ein Bündel nicht) und -
    seit A3 - FRISCHE (`_gw_frisch`). Mit `anbieter` auf dessen Bündel
    beschraenkt - die Vodafone-Referenz ist das Minimum UNTER DEN
    EIGENEN frischen Bündeln, nicht der Sieger des Bandes.
    """
    heute = _gw_heute(tco)
    beste = None
    for b in tco["buendel"]:
        if b.get("zustand") != "neu":
            continue
        if anbieter and b["anbieter"] != anbieter:
            continue
        if not b["sku_id"].startswith(sku_präfix):
            continue
        if _gw_band(b, blaetter) != band:
            continue
        if not _gw_frisch(b, heute):
            continue
        gesamt, _rest = _gw_leitzahl(b, blaetter)
        if gesamt is None:
            continue
        if beste is None or gesamt < beste[0]:
            beste = (gesamt, b)
    return beste


def test_gw_heute_liest_nur_datums_stems_und_lesbare_uhren(tmp_path,
                                                           monkeypatch):
    """S3a (Diff-Prüfung 21.09.2026): die Orakel-Uhr spiegelt die
    Seiten-Semantik von `render_site` - nur Stems, die ein Datum sind
    (wie `html._load_reports` filtert, hier eigenständig nachgebaut),
    SAMT der .md-Fälle (deren Datum der Stamm ist), und ein unlesbares
    `updated` zählt nicht (die Seite verwirft es über `_spaeterer_tag`).
    Vor dem Fix gewann ein Stray-JSON ("entwurf.json") das max() über
    die Stems, und ein unlesbares `updated` ("kaputt") die Endsumme -
    die Uhr des Orakels stellte dann ein Datum, das die Seite nie hat."""
    import sys as _gw_sys
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / "entwurf.json").write_text("{}", encoding="utf-8")
    (reports / "2026-09-16.json").write_text("{}", encoding="utf-8")
    (reports / "2026-09-18.md").write_text("# B\n", encoding="utf-8")
    monkeypatch.setattr(_gw_sys.modules[__name__], "_GW_WURZEL", tmp_path)
    # Der jüngste DATUMS-Stem ist der .md- vom 18.09.; "kaputt" und
    # "entwurf" zählen nicht.
    assert _gw_heute({"updated": "kaputt"}) == "2026-09-18"
    # Ein lesbares `updated` JÜNGER als jeder Bericht gewinnt (der
    # tägliche Lauf schreibt seinen eigenen Stand).
    assert _gw_heute({"updated": "2026-09-20"}) == "2026-09-20"


# ---- Extraktion aus der gerenderten Seite (nur Lesen, nichts mutieren) ----
_GW_ANTWORT_MUSTER = re.compile(
    r"(?:ist (?P<anb1>[^:<]+?) am günstigsten|führt nur (?P<anb2>[^:<]+?))"
    r": <b class='gr-zr-zahl'>(?P<gesamt>[\d.,]+) €</b> "
    r"Kosten über 24 Monate, Ø "
    # greedy bis zur LETZTEN schliessenden Klammer: o2-Tarifnamen tragen
    # selbst Klammern ("... mit 50 GB+ (24 Mon.)").
    r"<b class='gr-zr-zahl'>(?P<o>[\d.,]+) €/Monat</b> \((?P<klammer>.*)\)")

_GW_LEIT_MUSTER = re.compile(
    r"<b class='gr-leit-zahl'>([\d.,]+) €</b>"
    r"<span class='gr-leit-label'>[^()]*\(([\d.,]+) €(?:, Näherung)?\)"
    r"</span>")


def _gw_paar_block(fragment: str, modell: str, band: str) -> str | None:
    """Der div.gr-zr-lager-Block eines (Modell, Band)-Paars."""
    assert fragment, "Fragment ist leer - der Render hat keine Zeitreihe"
    anfang = f'<div class="gr-zr-lager" data-modell="{modell}" ' \
             f'data-band="{band}"'
    i = fragment.find(anfang)
    if i < 0:
        return None
    j = fragment.find('<div class="gr-zr-lager"', i + 10)
    return fragment[i:j if j > 0 else len(fragment)]


def _gw_antwort(block: str) -> dict | None:
    assert block, "Paar-Block ist leer - Antwort-Satz nicht lesbar"
    m = _GW_ANTWORT_MUSTER.search(block)
    if not m:
        return None
    return {"anb": (m.group("anb1") or m.group("anb2")).strip(),
            "gesamt": _gw_dezimal(m.group("gesamt")),
            "o": _gw_dezimal(m.group("o")),
            "klammer": m.group("klammer")}


def _gw_neueste_vorlage(block: str, anbieter: str) -> tuple:
    """(messtag, inhalt) der neuesten Rechenweg-Vorlage eines Anbieters -
    der Block traegt JEDE Historien-Messung, und aeltere Raten duerfen
    andere sein (gemessen: congstar 29,70 vor dem 30,50 von heute)."""
    vorlagen = re.findall(
        r"<template data-anb='([^']+)' data-m='([^']+)'[^>]*>(.*?)</template>",
        block, re.S)
    assert block, "Paar-Block ist leer - kein Rechenweg lesbar"
    eigene = [(m, inhalt) for a, m, inhalt in vorlagen if a == anbieter]
    assert eigene, (f"kein {anbieter}-Rechenweg im Paar-Block - ohne ihn "
                    "prueft die Restschuld nichts")
    return max(eigene, key=lambda v: v[0])


def _gw_vergleiche(ist: "_gw_Dez", soll_cent: int, kontext: str) -> None:
    """Der eine Vergleich dieses Abschnitts - Seite gegen eigene Rechnung."""
    assert ist == _gw_Dez(soll_cent) / 100, (
        f"{kontext}: Seite zeigt {ist} €, die eigene Rechnung aus den "
        f"Rohdaten ergibt {_gw_Dez(soll_cent) / 100} €")


def _gw_o_monat(soll_cent: int) -> set:
    """O/Monat auf Cent gerundet - half-even (Python round der Seite) und
    half-up (kaufmaennisch) als akzeptierte Menge."""
    genau = _gw_Dez(soll_cent) / 2400
    return {genau.quantize(_gw_Dez("0.01"), rounding=_gw_HEVEN),
            genau.quantize(_gw_Dez("0.01"), rounding=_gw_HUP)}


@pytest.fixture(scope="module")
def gw_seite(tmp_path_factory) -> dict:
    """Ein Render gegen den gefrorenen Bestand des Repos, mit cfg.

    render_site() leitet den State ueber reports.parent.parent her - data/
    reports des Repos zeigt auf data/state des Repos. Wegwerfordner, nie
    site/ im Repo (harte Regel 1)."""
    from telco_radar.config import load_config

    site = tmp_path_factory.mktemp("v4-p0-leitzahl") / "site"
    render_site(site, _GW_WURZEL / "data" / "reports",
                load_config(_GW_WURZEL))
    return {
        "geraete": (site / "geraete.html").read_text(encoding="utf-8"),
        "fragment": (site / "data" / "geraete-zeitreihe.html")
        .read_text(encoding="utf-8"),
        # P0-B-Pruefung (21.09.2026): die Buendelliste JE MODELL liegt
        # nicht in geraete.html, sondern in diesem Nachladefragment - nur
        # das Startmodell steht inline. Wer nur geraete.html liest, prueft
        # 12 von 375 Buendeln und haelt das fuer die Seite. Die zwei
        # Dokumente bleiben GETRENNT: aneinandergehaengt fielen die
        # Inline-Buendel des Startmodells in den letzten Lager-Block.
        "buendel": (site / "data" / "geraete-buendel.html")
        .read_text(encoding="utf-8"),
        "csv": site / "exporte" / "geraete-tco.csv",
        "stand": json.loads((_GW_WURZEL / "data" / "state" / "geraete_tco.json")
                            .read_text(encoding="utf-8"))["updated"],
    }


# Der Pflichtfall des Auftrags: congstar Allnet Flat XS zum iPhone 17 Pro
# 256 GB - Finanzierung 1.098,00 EUR, Zuzahlung 1,00 EUR, Tarif 15,00 EUR,
# Anschlusspreis 0,00 EUR: 1 + 24 x 15,00 + 1.098,00 = 1.459,00 EUR.
#
# NACHGEZOGEN AM 22.09.2026 (Bot-Commit b78c0fa, Lauf 51 mit P0-B): der
# Pflichtfall traegt seither ZWEI Zahlweisen desselben Tarifs. Die
# Leitzahl aendert sich dadurch NICHT - congstar finanziert zum Nulltarif,
# 24 x 45,75 EUR und 36 x 30,50 EUR sind beide 1.098,00 EUR -, wohl aber
# die Restschuld: die 24er traegt nach Monat 24 nichts mehr offen, die
# 36er 12 x 30,50 = 366,00 EUR. Deshalb liefert dieser Helfer nicht mehr
# "irgendein Buendel" (`kandidaten[0]`, dessen Laufzeit von der Reihen-
# folge des Stores abhing), sondern die Buendel JE LAUFZEIT.
_GW_PFLICHT_SKU = "apple-iphone-17-pro-256gb"
_GW_PFLICHT_ANBIETER = "congstar"
_GW_PFLICHT_TARIF = "Allnet Flat XS"
# EXAKTE ANKER, keine Untergrenzen: Ratenzahl -> Monatsrate IN CENT
# (Geld rechnet dieser Abschnitt in ganzen Cent, siehe `_gw_cent`; ein
# Vergleich auf der float-Schreibweise haette 30.5 gegen "30.50"
# gestellt). Eigene Rechnung aus `data/state/geraete_tco_historie.jsonl`
# (Messung 2026-09-22): 24 x 45,75 = 1.098,00 und 36 x 30,50 = 1.098,00.
# Faellt eine der beiden weg, faellt dieser Anker - das ist die Meldung.
_GW_PFLICHT_RATEN = {24: 4575, 36: 3050}


def _gw_pflichtbuendel(tco: dict, blaetter: dict) -> tuple:
    """(soll_cent, {Laufzeit: Bündel}, {Abruftage}).

    Alle Farben UND alle Zahlweisen rechnen auf dieselbe Leitzahl; das
    wird hier geprüft, nicht vorausgesetzt."""
    kandidaten = [b for b in tco["buendel"]
                  if b["sku_id"].startswith(_GW_PFLICHT_SKU)
                  and b["anbieter"] == _GW_PFLICHT_ANBIETER
                  and b["tarif_name"] == _GW_PFLICHT_TARIF
                  and b.get("zustand") == "neu"]
    assert kandidaten, \
        ("Pflichtfall fehlt im Bestand (benannte Lücke, nicht raten): "
         f"kein neu-Bündel {_GW_PFLICHT_ANBIETER}/{_GW_PFLICHT_TARIF} "
         f"zu {_GW_PFLICHT_SKU}")
    werte = {_gw_leitzahl(b, blaetter)[0] for b in kandidaten}
    assert None not in werte and len(werte) == 1, (
        f"Farben des Pflichtfalls rechnen verschieden: {werte}")
    je_laufzeit: dict = {}
    for b in kandidaten:
        vorher = je_laufzeit.setdefault(b["laufzeit_monate"], b)
        assert _gw_cent(vorher["geraet_monatsrate"]) \
            == _gw_cent(b["geraet_monatsrate"]), (
            f"zwei Raten für dieselbe Laufzeit {b['laufzeit_monate']}: "
            f"{vorher['geraet_monatsrate']} gegen {b['geraet_monatsrate']}")
    ist_raten = {n: _gw_cent(b["geraet_monatsrate"])
                 for n, b in sorted(je_laufzeit.items())}
    assert ist_raten == _GW_PFLICHT_RATEN, (
        f"Zahlweisen des Pflichtfalls sind {ist_raten}, verankert ist "
        f"{_GW_PFLICHT_RATEN} (gemessen 22.09.2026). MEHR: die "
        "Erfassungslücke schliesst sich weiter - nachrechnen und den "
        "Anker samt Datum nachziehen. WENIGER: eine Zahlweise ist "
        "verlorengegangen, das ist ein Fehler und wird behoben.")
    tage = {b.get("abgerufen_am", "") for b in kandidaten}
    return werte.pop(), je_laufzeit, tage


def test_leitzahl_congstar_xs_iphone17pro256_am_bestand(gw_seite):
    """Der Pflichtfall, in allen Lagen, in denen die Seite ihn trägt:
    Antwort-Satz und Rechenweg im (Modell, Band)-Paar des Fragments -
    das Fragment gehört zum selben Render und trägt ALLE Paare - und,
    wenn der Server-First-Paint gerade mit diesem Paar startet, auch
    dessen Antwort-Satz und Bündelzeile.

    NACHGEZOGEN AM 22.09.2026: der Pflichtfall trägt seit Lauf 51 zwei
    Zahlweisen (24 x 45,75 EUR und 36 x 30,50 EUR). Die Leitzahl bleibt
    1.459,00 EUR - congstar finanziert zum Nulltarif, beide Wege summieren
    auf dieselben 1.098,00 EUR Finanzierung. Geändert hat sich NUR, welche
    Zahlweise der Rechenweg der jüngsten Messung nennt: die Zeitreihe führt
    je (Anbieter, Tag) ein Bündel, und bei zwei Zeiträumen am selben Tag
    gewinnt der des Horizonts (24). Vorher verglich dieser Test gegen
    `kandidaten[0]` - ein Bündel, dessen Laufzeit die Store-Reihenfolge
    bestimmte; das war eine Wette, kein Anker."""
    tco, blaetter, _db = _gw_rohdaten()
    soll_cent, je_laufzeit, _tage = _gw_pflichtbuendel(tco, blaetter)

    # 1) Der Anker: der Pflichtwert aus dem Auftrag. Bei einem Bot-Commit,
    #    der die congstar-Posten ändert, wird DIESER Assert bewusst rot -
    #    dann ist der neue Sollwert nachzurechnen und hier neu zu verankern
    #    (er verhindert, dass jemand Rechnung oder Seite still verbiegt,
    #    ohne dass der Pflichtfall es meldet).
    assert soll_cent == 145900, (
        f"Pflichtfall-Rechnung ergibt {soll_cent / 100} € - Verankerung "
        "1.459,00 € (1 + 24 × 15,00 + 36 × 30,50 + 0) stimmt nicht mehr")

    # 2) Das Paar im Fragment: Antwort-Satz mit Leitzahl und O/Monat.
    block = _gw_paar_block(gw_seite["fragment"],
                           "apple-iphone-17-pro-256", "klein")
    assert block, "Paar apple-iphone-17-pro-256/klein fehlt im Fragment"
    antwort = _gw_antwort(block)
    assert antwort, f"Paar ohne Antwort-Satz: {block[:200]!r}"
    assert antwort["anb"] == _GW_PFLICHT_ANBIETER, (
        f"Antwort nennt {antwort['anb']!r}, erwartet congstar")
    _gw_vergleiche(antwort["gesamt"], soll_cent,
                   "Pflichtfall, Antwort-Satz im Paar klein")
    assert _GW_PFLICHT_TARIF in antwort["klammer"], antwort["klammer"]
    assert antwort["o"] in _gw_o_monat(soll_cent), (
        f"Ø/Monat im Satz: {antwort['o']} €, erwartet "
        f"{_gw_o_monat(soll_cent)}")

    # 3) Der Rechenweg der neuesten congstar-Messung im selben Paar: die
    #    Posten des Panels gegen SICH SELBST (24 × Tarif, Laufzeit × Rate,
    #    Summe) UND gegen die eigene Store-Rechnung - zwei Rechnungen, die
    #    nichts voneinander wissen.
    messtag, inhalt = _gw_neueste_vorlage(block, _GW_PFLICHT_ANBIETER)
    posten = {}
    for m in re.finditer(
            r"<span class='gr-zr-pn'>([^<]+)</span>.*?"
            r"<span class='gr-zr-pr'>(.*?)</span></li>", inhalt, re.S):
        name = m.group(1)
        text = " ".join(re.sub(r"<[^>]+>", " ", m.group(2)).split())
        mal = re.search(r"(\d+) × ([\d.,]+) €\s*=\s*([\d.,]+) €", text)
        posten[name] = (_gw_dezimal(mal.group(3)),
                        int(mal.group(1)), _gw_dezimal(mal.group(2))) if mal \
            else (_gw_dezimal(re.search(r"([\d.,]+) €", text).group(1)),
                  None, None)
    summe = _gw_dezimal(re.search(
        r"gr-zr-rsumme'>= <b>([\d.,]+) €</b>", inhalt).group(1))
    teile = [_gw_dezimal("0")]
    for _name, (betrag, n, einzeln) in posten.items():
        teile.append(betrag)
        if n is not None:      # "N × einzeln = betrag" muss aufgehen
            assert einzeln * n == betrag, (
                f"Posten {_name}: {n} × {einzeln} != {betrag}")
    assert sum(teile) == summe, (
        f"Rechenweg-Summe {summe} != Summe der Posten {sum(teile)}")
    _gw_vergleiche(summe, soll_cent,
                   f"Pflichtfall, Rechenweg-Summe (Messung {messtag})")
    # Die Zahlweise, die der Rechenweg nennt, muss eine SEIN, die der
    # Bestand trägt - Ratenzahl UND Rate, nicht nur die Summe. Eine
    # erfundene Rate fällt hier auf, auch wenn sie sich zu 1.098,00 EUR
    # aufaddiert.
    n_raten = posten["Geräterate"][1]
    assert n_raten in je_laufzeit, (
        f"Rechenweg nennt {n_raten} Geräteraten - der Bestand kennt zum "
        f"Pflichtfall nur {sorted(je_laufzeit)}")
    buendel = je_laufzeit[n_raten]
    # Tarif-Posten: 24 Monate, zum gemessenen Tarifpreis
    assert posten["Tarif"][1] == 24 and \
        posten["Tarif"][2] == _gw_Dez(str(buendel["tarif_monatlich"]))
    assert posten["Geräterate"][2] \
        == _gw_Dez(str(buendel["geraet_monatsrate"])), (
        f"Rechenweg rechnet mit {posten['Geräterate'][2]} € je Rate, der "
        f"Bestand misst {buendel['geraet_monatsrate']} € für "
        f"{n_raten} Raten")
    # ANKER (22.09.2026): bei zwei Zahlweisen am selben Tag führt die
    # Zeitreihe die des Horizonts (`geraete_zeitreihe`: "Bei zwei
    # Zeitraeumen am selben Tag gewinnt der des Horizonts"). Der
    # Pflichtfall trägt seit Lauf 51 beide, also muss hier 24 stehen.
    # Fällt der Bestand auf eine Zahlweise zurück, fällt schon
    # `_GW_PFLICHT_RATEN` - dieser Assert bleibt dann stumm und fängt
    # nur den Fall ab, dass die Auswahl selbst kippt.
    assert n_raten == _GW_HORIZONT, (
        f"Rechenweg der jüngsten Messung nennt {n_raten} Raten; bei zwei "
        f"Zahlweisen führt die Zeitreihe die über {_GW_HORIZONT} Monate")

    # 3b) Die ZWEITE Zahlweise darf nicht still verschwinden: beide
    #     Ratenlaufzeiten des Pflichtfalls stehen als eigene Bündelzeile
    #     auf der Seite, jede mit IHRER Rate und derselben Leitzahl.
    #     (Das verlangt `test_pf_bestand_zaehlt_seine_ratenlaufzeiten_...`
    #     ausdrücklich, seit der Bestand zwei Laufzeiten trägt.)
    #     Die zwei Dokumente bleiben GETRENNT durchsucht (Warnung der
    #     Fixture): aneinandergehaengt verschoeben sich Blockgrenzen.
    gezeigt = {}
    for dok in (gw_seite["geraete"], gw_seite["buendel"]):
        for roh in re.findall(
                r'<details class="gr-bnd"[^>]*data-anbieter="congstar"'
                r'[^>]*data-band="klein"[^>]*>(.*?)</details>', dok, re.S):
            klar = " ".join(re.sub(r"<[^>]+>", " ", roh).split())
            if f"{_GW_PFLICHT_TARIF} ·" not in klar \
                    or "1.459,00 €" not in klar:
                continue
            for n, rate in re.findall(
                    r"in (\d+) Raten à ([\d.,]+) €", klar):
                gezeigt[int(n)] = _gw_dezimal(rate)
    assert gezeigt == {n: _gw_Dez(c) / 100
                       for n, c in _GW_PFLICHT_RATEN.items()}, (
        f"die Seite zeigt zum Pflichtfall die Zahlweisen {gezeigt}, der "
        f"Bestand trägt {_GW_PFLICHT_RATEN}. Eine Zahlweise, die der "
        "Bestand misst und die Seite verschweigt, ist ein Datenverlust")

    # 4) First Paint: der Server-Startblock - derselbe Pflichtfall wie im
    #    Fragment. Der Start fällt aus den Daten und darf wechseln; damit
    #    der Wechsel die Prüfungen nicht STILL überspringt, zählt der
    #    Zweig sich (fp_geprueft) und der Test meldet sich laut.
    titel = re.search(r'class="gr-bnd-titel"[^>]*>([^<]+)<',
                      gw_seite["geraete"])
    fp_geprueft = 0
    if titel and "Apple iPhone 17 Pro 256 GB" in titel.group(1):
        fp_geprueft += 1
        fp_antwort = _gw_antwort(gw_seite["geraete"])
        assert fp_antwort and fp_antwort["anb"] == _GW_PFLICHT_ANBIETER
        _gw_vergleiche(fp_antwort["gesamt"], soll_cent,
                       "Pflichtfall, Antwort-Satz im First Paint")
        zeile = re.search(
            r'<details class="gr-bnd"[^>]*data-anbieter="congstar"'
            r'[^>]*data-band="klein"[^>]*>(.*?)</details>',
            gw_seite["geraete"], re.S)
        assert zeile, "Bündelzeile congstar/klein fehlt im First Paint"
        kopf = re.search(r"<summary>(.*?)</summary>", zeile.group(1), re.S)
        assert kopf and _GW_PFLICHT_TARIF in kopf.group(1), \
            "Bündelzeile nennt nicht den Pflichttarif"
        attrs = re.search(r'<details class="gr-bnd"([^>]*)>', zeile.group(0))
        gesamt_attr = re.search(r'data-gesamt="([\d.]+)"', attrs.group(1))
        schnitt_attr = re.search(r'data-schnitt="([\d.]+)"', attrs.group(1))
        assert gesamt_attr and _gw_Dez(gesamt_attr.group(1)) \
            == _gw_Dez(soll_cent) / 100, gesamt_attr and gesamt_attr.group(1)
        assert schnitt_attr and \
            _gw_Dez(schnitt_attr.group(1)) in _gw_o_monat(soll_cent)
        text = " ".join(re.sub(r"<[^>]+>", " ", zeile.group(1)).split())
        assert "1.459,00 €" in text, "Leitzahl fehlt wortlich in der Zeile"
    assert fp_geprueft >= 1, (
        "Server-First-Paint startet nicht mit dem Pflichtpaar - Antwor- und "
        "Bündelzeilen-Prüfungen wären still übersprungen. Der Start folgt "
        "dem Bestand (meiste Anbieter); bei einem Wechsel diesen Zweig "
        "bewusst neu verankern oder auf ein anderes Fragment-Paar heben.")


def test_monatsschnitt_und_restschuld_des_pflichtfalls_am_bestand(gw_seite):
    """Die Zweitzahl (Ø/Monat) und die Restschuld-Ausweisungen: 'davon
    nach Monat 24 noch zu zahlen' im Rechenweg und 'danach noch offen' in
    der Bündelkarte - plus die gekappte Zahl 'nach 24 Monaten gezahlt',
    die seit A1 NUR noch unter diesem Label stehen darf (die alte,
    1.093,00 €-Leitzahl war genau um die Restschuld zu niedrig).

    NACHGEZOGEN AM 22.09.2026: der Pflichtfall trägt seit Lauf 51 zwei
    Zahlweisen, und die Restschuld ist die EINZIGE Zahl, die sie
    unterscheidet - 36 x 30,50 lassen nach Monat 24 noch 366,00 € offen,
    24 x 45,75 nichts. Die Leitzahl (1.459,00 €) und der Ø/Monat sind in
    beiden Fällen dieselben. Der Test verankert deshalb BEIDE Rechnungen
    und verlangt die Restschuld genau dort, wo es eine gibt: ein "davon
    nach Monat 24 noch zu zahlen" unter einer 24-Raten-Zahlweise wäre
    eine erfundene Schuld, sein Fehlen unter 36 Raten ein Datenverlust."""
    tco, blaetter, _db = _gw_rohdaten()
    soll_cent, je_laufzeit, _tage = _gw_pflichtbuendel(tco, blaetter)

    def _rest(n: int) -> int:
        return _gw_cent(je_laufzeit[n]["geraet_monatsrate"]) \
            * max(0, n - _GW_HORIZONT)

    # EXAKTE ANKER je Zahlweise: (Leitzahl, Restschuld, bis Monat 24
    # gezahlt) - eigene Rechnung aus den Rohdaten, nicht von der Seite.
    assert {n: (soll_cent, _rest(n), soll_cent - _rest(n))
            for n in sorted(je_laufzeit)} == {
        24: (145900, 0, 145900), 36: (145900, 36600, 109300)}

    block = _gw_paar_block(gw_seite["fragment"],
                           "apple-iphone-17-pro-256", "klein")
    _messtag, inhalt = _gw_neueste_vorlage(block, _GW_PFLICHT_ANBIETER)
    n_raten = int(re.search(
        r"<span class='gr-zr-pn'>Geräterate</span>.*?(\d+) × ",
        inhalt, re.S).group(1))
    assert n_raten in je_laufzeit, (
        f"Rechenweg nennt {n_raten} Geräteraten, der Bestand kennt "
        f"{sorted(je_laufzeit)}")
    buendel = je_laufzeit[n_raten]
    rest_c = _rest(n_raten)
    gezahlt_c = soll_cent - rest_c
    offen = re.search(
        r"davon nach Monat 24 noch zu zahlen: (\d+) × ([\d.,]+) € "
        r"= ([\d.,]+) €", inhalt)
    if rest_c:
        assert offen, (
            f"Rechenweg der {n_raten}-Raten-Zahlweise nennt die "
            f"Restschuld nicht - offen sind {rest_c / 100} €")
        assert int(offen.group(1)) == n_raten - _GW_HORIZONT
        assert _gw_dezimal(offen.group(2)) \
            == _gw_Dez(str(buendel["geraet_monatsrate"]))
        _gw_vergleiche(_gw_dezimal(offen.group(3)), rest_c,
                       "Restschuld im Rechenweg des Pflichtfalls")
    else:
        assert offen is None, (
            f"Rechenweg nennt eine Restschuld ({offen.group(3)} €), "
            f"obwohl {n_raten} Raten in {_GW_HORIZONT} Monaten bezahlt "
            "sind - eine erfundene Schuld")

    # Die ANDERE Zahlweise darf ihre Restschuld nicht verlieren: sie
    # steht im Rechenweg ihres letzten eigenen Messtags. Ohne diesen
    # Zweig prüfte der Test seit dem 22.09. keine Restschuld mehr.
    rest_geprueft = 0
    for n in sorted(je_laufzeit):
        if n == n_raten or not _rest(n):
            continue
        muster = (f"Geräterate</span>", f"{n} × ")
        for _anb, _m, roh in re.findall(
                r"<template data-anb='([^']+)' data-m='([^']+)'[^>]*>"
                r"(.*?)</template>", block, re.S):
            if _anb != _GW_PFLICHT_ANBIETER or not all(
                    t in roh for t in muster):
                continue
            treffer = re.search(
                r"davon nach Monat 24 noch zu zahlen: (\d+) × "
                r"([\d.,]+) € = ([\d.,]+) €", roh)
            assert treffer, (
                f"Rechenweg vom {_m} nennt {n} Raten, aber keine "
                f"Restschuld - {_rest(n) / 100} € fallen unter den Tisch")
            _gw_vergleiche(_gw_dezimal(treffer.group(3)), _rest(n),
                           f"Restschuld der {n}-Raten-Zahlweise ({_m})")
            rest_geprueft += 1
    assert rest_geprueft >= 1, (
        "keine Restschuld geprüft - trägt der Bestand nur noch die "
        f"{n_raten}-Raten-Zahlweise, fällt schon `_GW_PFLICHT_RATEN`; "
        "sonst hat das Fragment seine älteren Messungen verloren")

    # First Paint (Karte): der Startblock - mit Zaehler, damit ein
    # anderes Startpaar die Ausweisungs-Prüfung nicht still überspringt.
    # Fragment-Gegenstück: der offen-Satz im Rechenweg OBEN - der ist
    # paarungebunden geprüft und fällt nicht mit dem Startfall um.
    titel = re.search(r'class="gr-bnd-titel"[^>]*>([^<]+)<',
                      gw_seite["geraete"])
    # Seit dem 22.09. trägt der Startblock ZWEI congstar/klein-Zeilen je
    # Tarif (24 und 36 Raten). Geprüft wird JEDE Pflichttarif-Zeile
    # gegen die Rechnung IHRER Ratenzahl - `re.search` nahm die erste
    # und hätte die zweite still übersprungen.
    fp_geprueft = 0
    if titel and "Apple iPhone 17 Pro 256 GB" in titel.group(1):
        for roh in re.findall(
                r'<details class="gr-bnd"[^>]*data-anbieter="congstar"'
                r'[^>]*data-band="klein"[^>]*>(.*?)</details>',
                gw_seite["geraete"], re.S):
            text = " ".join(re.sub(r"<[^>]+>", " ", roh).split())
            raten = re.search(r"in (\d+) Raten à ([\d.,]+) €", text)
            if f"{_GW_PFLICHT_TARIF} ·" not in text or not raten:
                continue
            n = int(raten.group(1))
            if n not in je_laufzeit:
                continue
            fp_geprueft += 1
            assert _gw_dezimal(raten.group(2)) \
                == _gw_Dez(_GW_PFLICHT_RATEN[n]) / 100, (
                f"Bündelzeile nennt {raten.group(2)} € je Rate, verankert "
                f"sind {_GW_PFLICHT_RATEN[n]} Cent")
            m = re.search(r"nach 24 Monaten gezahlt: ([\d.,]+) € · "
                          r"danach noch offen: ([\d.,]+) € "
                          r"\((\d+) Geräteraten\)", text)
            if _rest(n):
                assert m, f"Bündelkarte ohne Ausweisung: {text[:160]!r}"
                _gw_vergleiche(_gw_dezimal(m.group(1)),
                               soll_cent - _rest(n),
                               f"'nach 24 Monaten gezahlt' ({n} Raten)")
                _gw_vergleiche(_gw_dezimal(m.group(2)), _rest(n),
                               f"'danach noch offen' ({n} Raten)")
                assert int(m.group(3)) == n - _GW_HORIZONT
            else:
                assert m is None, (
                    f"Bündelkarte weist {m.group(2)} € als offen aus, "
                    f"obwohl {n} Raten in {_GW_HORIZONT} Monaten bezahlt "
                    "sind")
                assert re.search(r"nach 24 Monaten gezahlt: ([\d.,]+) €",
                                 text), (
                    "auch die voll bezahlte Zahlweise nennt die gekappte "
                    f"Zahl unter ihrem Label: {text[:160]!r}")
            # Die gekappte Zahl darf nicht mehr als Leitzahl herhalten:
            # ihr Label muss das Kappen benennen (A1-Regel).
            assert "nach 24 Monaten gezahlt" in text
        assert fp_geprueft == len(je_laufzeit), (
            f"{fp_geprueft} von {len(je_laufzeit)} Zahlweisen im First "
            "Paint geprüft - eine Bündelzeile des Pflichttarifs fehlt")
    assert fp_geprueft >= 1, (
        "Server-First-Paint startet nicht mit dem Pflichtpaar - die "
        "Ausweisung 'nach 24 Monaten gezahlt / danach noch offen' wäre "
        "still übersprungen (Fragment-Gegenstück: der offen-Satz im "
        "Rechenweg oben).")


# Die vier Tor-Geräte des Auftrags, je zwei Bänder (Band-IDs der Paare).
_GW_TOR_FAELLE = [
    ("apple-iphone-17-pro-256", "klein"), ("apple-iphone-17-pro-256", "mittel"),
    ("apple-iphone-17-256", "klein"), ("apple-iphone-17-256", "mittel"),
    ("samsung-galaxy-s26-ultra-256", "klein"),
    ("samsung-galaxy-s26-ultra-256", "mittel"),
    ("google-pixel-10-pro-128", "klein"), ("google-pixel-10-pro-128", "mittel"),
]


@pytest.mark.parametrize("modell,band", _GW_TOR_FAELLE)
def test_tor_geraete_leitzahl_je_band_am_bestand(gw_seite, modell, band):
    """Je eine Leitzahl der vier Tor-Geräte, je zwei Bänder: die Zahl des
    Antwort-Satzes gegen die EIGENE Minimumsrechnung über alle neu-Bündel
    des Modells im Band - und die Guenstigkeitsbehauptung des Satzes
    ('ist X am guenstigsten' / 'fuehrt nur X') gegen dasselbe Minimum."""
    tco, blaetter, _db = _gw_rohdaten()
    block = _gw_paar_block(gw_seite["fragment"], modell, band)
    if block is None:
        pytest.skip(f"benannte Lücke: Paar {modell}/{band} fehlt im "
                    f"Fragment (Bestand vom {gw_seite['stand']})")
    antwort = _gw_antwort(block)
    if antwort is None:
        pytest.skip(f"benannte Lücke: Paar {modell}/{band} ohne Antwort-Satz")
    min_cent, min_buendel = _gw_min_buendel(tco, blaetter, f"{modell}gb",
                                            band)
    if min_buendel is None:
        pytest.skip(f"benannte Lücke: kein neu-Bündel von {modell} im Band "
                    f"{band} in der Auswahlmenge (Bestand {gw_seite['stand']})")
    _gw_vergleiche(antwort["gesamt"], min_cent,
                   f"{modell} Band {band}: Leitzahl des Antwort-Satzes")
    assert antwort["anb"] == min_buendel["anbieter"], (
        f"{modell} Band {band}: Satz nennt {antwort['anb']!r} am günstigsten, "
        f"die eigene Rechnung findet {min_buendel['anbieter']!r} "
        f"mit {_gw_Dez(min_cent) / 100} €")
    assert min_buendel["tarif_name"] in antwort["klammer"], (
        f"Satz nennt Tarif {antwort['klammer']!r}, die Rechnung rechnet "
        f"{min_buendel['tarif_name']!r}")
    assert antwort["o"] in _gw_o_monat(min_cent), (
        f"{modell} Band {band}: Ø/Monat {antwort['o']} € != "
        f"{_gw_o_monat(min_cent)}")


def test_vodafone_referenz_und_delta_des_pflichtfalls_am_bestand(gw_seite):
    """Die Leit-Zeile 'X € unter der Vodafone-Referenz (Y €)': die Referenz
    ist die guenstigste EIGENE Karte im selben Band (eine echte Vodafone-
    Bündel-Leitzahl, NICHT die SIM-only-Naeherung aus Blatt und Barpreis).
    Hier nur fuer den Pflichtfall geprueft, und nur wo Vodafone wirklich
    ein neu-Bündel im Band hat - sonst rechnet die Seite eine Naeherung,
    und das ist eine andere Rechnung als diese (benannte Grenze)."""
    tco, blaetter, _db = _gw_rohdaten()
    vf = _gw_min_buendel(tco, blaetter, _GW_PFLICHT_SKU, "klein",
                         anbieter="Vodafone")
    if vf is None:
        pytest.skip("benannte Lücke: Vodafone ohne neu-Bündel des "
                    "Pflichtfalls im Band klein - die Seite rechnet dann "
                    "eine Näherung, dieser Test prüft die Bündel-Referenz")
    beste_c, _b, _t = _gw_pflichtbuendel(tco, blaetter)
    soll_ref, soll_delta = vf[0], vf[0] - beste_c

    block = _gw_paar_block(gw_seite["fragment"],
                           "apple-iphone-17-pro-256", "klein")
    leit = _GW_LEIT_MUSTER.search(block or "")
    assert leit, "Leit-Zeile fehlt im Paar des Pflichtfalls"
    _gw_vergleiche(_gw_dezimal(leit.group(1)), soll_delta,
                   "Delta zur Vodafone-Referenz")
    _gw_vergleiche(_gw_dezimal(leit.group(2)), soll_ref,
                   "Vodafone-Referenz der Leit-Zeile")


def test_geraete_tco_csv_gegen_die_eigene_rechnung(gw_seite):
    """site/exporte/geraete-tco.csv desselben Renders: Jede Bündel-Zeile
    aus ihren eigenen Postenspalten nachgerechnet (Zuzahlung + 24 × Tarif
    + Rate × Laufzeit + Anschluss; Bündelform: Bündelbetrag × Laufzeit +
    Zuzahlung + Anschluss). SIM-only-Zeilen prüft der EIGENE Test mit dem
    fachlichen Soll inklusive Anschlusspreis (P0.8/A4) - hier stehen sie
    nicht, damit dieser Test nur die Bündel scharf hält. Und der heutige
    Stand zusaetzlich gegen den Store: jedes Bündel mit
    abgerufen_am == tco.updated muss als CSV-Zeile mit genau diesen
    Posten stehen und auf dieselbe Zahl rechnen."""
    tco, blaetter, _db = _gw_rohdaten()
    zeilen = list(_gw_csv.DictReader(
        gw_seite["csv"].open(encoding="utf-8-sig"), delimiter=";"))
    assert zeilen, "Export ohne Zeilen"

    def _n(s):
        return None if s in (None, "") else _gw_Dez(s.replace(",", "."))

    abweich, geprueft = [], 0
    for r in zeilen:
        zu, tarif = _n(r["Zuzahlung EUR"]), _n(r["Tarif/Monat EUR"])
        rate = _n(r["Geräterate EUR"])
        buendel = _n(r["Bündel/Monat EUR"])
        anschluss = _n(r["Anschlusspreis EUR"])
        lz = r["Laufzeit Monate"]
        if r["Art"] == "SIM-only":
            # P0.8/A4: SIM-only hat seinen EIGENEN Test mit dem fachlichen
            # Soll (24 × Tarif + Anschlusspreis, xfail strict) - hier steht
            # der Zweig nicht, damit dieser Test nur die Bündel scharf
            # hält und der offene Fehler genau EIN Gesicht hat.
            continue
        if buendel is not None:
            soll = buendel * int(lz) + (zu or 0) + (anschluss or 0)
        elif lz and tarif is not None and rate is not None:
            soll = (zu or 0) + tarif * 24 + rate * int(lz) + (anschluss or 0)
        else:
            soll = None                  # Luecke in der Zeile selbst
        ist = _n(leitzahl_aus_zeile(r))
        if soll is None or ist is None:
            continue
        geprueft += 1
        if soll != ist:
            abweich.append((r["Art"], r["Anbieter"], r["Modell"], r["Tarif"],
                            float(ist), float(soll)))
    assert geprueft >= 400, (
        f"nur {geprueft} von {len(zeilen)} Zeilen nachgerechnet - der Test "
        "greift nicht mehr")
    assert not abweich, f"{len(abweich)} CSV-Zeilen widersprechen ihren " \
                        f"eigenen Posten: {abweich[:5]}"

    # Der Pflichtfall als Zeile(n) seines Abruftags - der Export traegt
    # JEDE Historien-Messung, und der Abruftag des Bündels ist der
    # Schlüssel, nicht der Stand des Stores (Anbieter werden an
    # verschiedenen Tagen gemessen; am Stand vom 2026-09-20 war congstar
    # zuletzt am 2026-09-16 dran).
    _soll, _pflichtbuendel, tage = _gw_pflichtbuendel(tco, blaetter)
    pflicht = [r for r in zeilen if r["Anbieter"] == _GW_PFLICHT_ANBIETER
               and r["Tarif"] == _GW_PFLICHT_TARIF
               and r["Speicher GB"] == "256"
               and "iphone-17-pro" in r["Modell"].lower().replace(" ", "-")
               and r["Abgerufen am"] in tage]
    assert pflicht, "Pflichtfall fehlt im Export (Stand " \
                    f"{gw_seite['stand']})"
    for zeile in pflicht:
        _gw_vergleiche(_n(leitzahl_aus_zeile(zeile)),
                       _soll, "Pflichtfall im CSV-Export")

    # Store-Abgleich: jedes heute gemessene Bündel steht mit seinen Posten
    # im Export und rechnet dort auf dieselbe Zahl.
    stand_zeilen = {(r["Anbieter"], r["Tarif"], r["Modell"], r["Speicher GB"],
                     r["Laufzeit Monate"], r["Zustand"],
                     r["Zuzahlung EUR"], r["Tarif/Monat EUR"],
                     r["Geräterate EUR"], r["Bündel/Monat EUR"],
                     r["Anschlusspreis EUR"],
                     leitzahl_aus_zeile(r)): r for r in zeilen}
    treffer = 0
    for b in tco["buendel"]:
        if b.get("abgerufen_am") != gw_seite["stand"] \
                or not b["sku_id"] or b.get("zustand", "neu") != "neu":
            continue
        g, _rest = _gw_leitzahl(b, blaetter)
        if g is None:
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", b["sku_id"]).strip("-")
        # sku: hersteller-modell-speicher-farbe -> Modell + Speicher daraus
        # (das CSV nennt das Modell OHNE Hersteller: "iPhone 17 Pro")
        teile = slug.split("-")
        speicher = next((t for t in teile if t.endswith("gb")
                         and t[:-2].isdigit()), None)
        if speicher is None:
            continue                     # Speicherstufe nicht slug-faehig
        modell = "-".join(teile[1:teile.index(speicher)])
        # DIE POSTEN GEHOEREN IN DEN MATCH: Farben desselben Geraets tragen
        # verschiedene Raten (gemessen: iPhone 16 rosa 23,00 / blau 27,00),
        # und nur die Zeile MIT den Posten dieses Buendels rechnet seine Zahl.
        def _eur(wert):
            return "" if wert is None else f"{float(wert):.2f}".replace(".", ",")
        posten = (_eur(b.get("geraet_zuzahlung")), _eur(b.get("tarif_monatlich")),
                  _eur(b.get("geraet_monatsrate")), _eur(b.get("buendel_monatlich")),
                  _eur(b.get("anschlusspreis")))
        gefunden = [schluessel for schluessel in stand_zeilen
                    if schluessel[0] == b["anbieter"]
                    and schluessel[1] == b["tarif_name"]
                    and schluessel[2].lower().replace(" ", "-") == modell
                    and schluessel[3] == speicher[:-2]
                    and schluessel[4] == str(b["laufzeit_monate"])
                    and schluessel[6:11] == posten]
        if not gefunden:
            continue                     # Modellname im CSV nicht slug-faehig
        for schluessel in gefunden:
            ist = _n(schluessel[11])
            assert ist == _gw_Dez(g) / 100, (
                f"CSV-Zeile {schluessel[:4]}: {ist} €, Store-Rechnung "
                f"{_gw_Dez(g) / 100} € (Posten {schluessel[6:11]})")
            treffer += 1
    assert treffer >= 200, (
        f"nur {treffer} heute gemessene Bündel im CSV nachgerechnet - der "
        "Store-Abgleich greift nicht mehr")


def test_geraete_tco_csv_simonly_mit_anschlusspreis(gw_seite):
    """Der FACHLICHE Soll der SIM-only-Zeilen: 24 × Tarif PLUS
    Anschlusspreis, wo die Zeile ihn trägt (A4, 20.09.2026: die
    SIM-only-Leitzahl ist dieselbe Rechnung wie die der Bündel - Soll-
    Definition der Leitzahl und Konsistenz zu geraeteanteil(), das
    tco_24(als_buendel()) schon immer so rechnete; bis A4 rechnete der
    Export ohne ihn, und der Orakel-Soll war der Bug). Eine LEERE Zelle
    ist die Lücke des Modells (unbekannt ist nicht kostenlos), der
    Orakel-Soll rechnet dann ohne ihn - dieselbe Konvention wie beim
    Bündel-Zweig oben. Zuzahlung und Geräterate werden in SIM-only-Zeilen
    nicht erhoben und stehen leer.

    Auftrag P0.8: "Im SIM-only-Export fehlt der Anschlusspreis" - bis
    P0-A4 (2026-09-20) rechnete die Kennzahl ihn nicht ein; seither ist
    die SIM-only-Leitzahl dieselbe Rechnung wie die der Bündel.
    """
    zeilen = [r for r in _gw_csv.DictReader(
        gw_seite["csv"].open(encoding="utf-8-sig"), delimiter=";")
        if r["Art"] == "SIM-only"]
    assert zeilen, "Export ohne SIM-only-Zeilen"

    def _z(s):
        return None if s in (None, "") else _gw_Dez(s.replace(",", "."))

    abweich, geprueft, mit_anschluss = [], 0, 0
    for r in zeilen:
        tarif, ist = _z(r["Tarif/Monat EUR"]), _z(
            leitzahl_aus_zeile(r))
        anschluss = _z(r["Anschlusspreis EUR"])
        if tarif is None or ist is None:
            continue                     # Lücke in der Zeile selbst
        soll = tarif * 24 + (anschluss if anschluss is not None
                             else _gw_Dez(0))
        if anschluss is not None:
            mit_anschluss += 1
        geprueft += 1
        if ist != soll:
            abweich.append((r["Anbieter"], r["Tarif"], float(ist),
                            float(soll)))
    assert geprueft >= 40, (
        f"nur {geprueft} von {len(zeilen)} SIM-only-Zeilen nachgerechnet - "
        "der Test greift nicht mehr")
    assert mit_anschluss >= 5, (
        f"nur {mit_anschluss} SIM-only-Zeilen mit erhobenem Anschlusspreis "
        "- der Soll-Zweig prüfte ins Leere (am Bestand vom 2026-09-20: 16)")
    assert not abweich, (
        f"{len(abweich)} SIM-only-Zeilen ohne ihren Anschlusspreis "
        f"(P0.8/A4): {abweich[:5]}")


def test_mutation_eines_euros_am_pflichtfall_schlaegt_aus(gw_seite):
    """Schärfen-Nachweis des Auftrags: Wird die angezeigte Zahl um 1 €
    verdreht (an der EXTRAHIERTEN Zahl, nicht an den Daten), muss der
    Vergleich dieses Abschnitts rot werden. Ein Test, dessen Lookup ins
    Leere läuft, ist grün und prüft nichts - hier ist die Gegenprobe als
    eigener Test, sie läuft bei jedem Lauf mit.

    Was was belegt: Der AUTOMATISMUS unten (pytest.raises um
    _gw_vergleiche) weist nur nach, dass der VERGLEICH bei einer um 1 €
    verdrehten Zahl rot wird - nicht, dass die Extraktion sie findet.
    Die EXTRAKTIONSKETTE (Paar-Block-Wahl, Antwort-Regex, Wahl der
    neuesten Vorlage) belegt der manuelle Nachweis vom 20.09.2026: gegen
    den Render in /tmp wurde die Antwort-Zahl im gerenderten Text selbst
    auf 1.460,00 gesetzt und dieselbe Kette liefen lassen - rot mit
    'Mutation +1: Seite zeigt 1460.00 €, die eigene Rechnung aus den
    Rohdaten ergibt 1459 €' (und '1458.00 €' bei −1 €); unverändert lief
    derselbe Aufruf ohne Fehler."""
    tco, blaetter, _db = _gw_rohdaten()
    soll_cent, _b, _t = _gw_pflichtbuendel(tco, blaetter)
    block = _gw_paar_block(gw_seite["fragment"],
                           "apple-iphone-17-pro-256", "klein")
    antwort = _gw_antwort(block)
    assert antwort, "ohne Antwort-Satz prüft die Mutation nichts"
    for mutation in (antwort["gesamt"] + 1, antwort["gesamt"] - 1):
        with pytest.raises(AssertionError):
            _gw_vergleiche(_gw_Dez(mutation), soll_cent, "Mutation")
    # Gegenprobe: unverändert schlägt der Vergleich NICHT an.
    _gw_vergleiche(antwort["gesamt"], soll_cent, "Gegenprobe unverändert")


# ==========================================================================
# PRUEFER P0-B (21.09.2026): DIE ZWEITE RECHNUNG FUER DIE RATENLAUFZEIT
# ==========================================================================
# Geschrieben vom PRUEFER, nicht vom Bauer. Alles hier liest nur
# `data/state/geraete_tco_historie.jsonl`, `geraete_tco.json` und
# `tarife.jsonl` und rechnet selbst in Cent (decimal, HALF_UP) - kein
# `telco_radar.tco_model`, kein `geraete_tco_karten`, kein `geraete_view`.
#
# Soll-Definition (CLAUDE.md, Abschnitt "Geraeteseite: Leitzahl"):
#   Kosten ueber 24 Monate = Anzahlung
#                          + 24 Monate Tarif
#                          + ALLE Geraeteraten der eigenen Laufzeit,
#                            einschliesslich der Restschuld nach Monat 24
#                          + Anschlusspreis
#   Buendelform (ein Monatsbetrag fuer Tarif und Geraet zusammen, 1&1):
#   Anzahlung + Laufzeit x Buendelbetrag + Anschlusspreis.
#
# Warum gegen die HISTORIE und nicht gegen den Stand: die Seite zeichnet
# ihre Zeitreihe aus der Historie, und nur dort steht je Messtag, welche
# Ratenlaufzeit an dem Tag gemessen wurde. Das Feld `gesamt` der Historie
# wird hier ABSICHTLICH NICHT gelesen - es traegt am Bestand vom
# 20.09.2026 noch die alte, bei Monat 24 gekappte Rechnung (congstar
# Allnet Flat XS zum iPhone 17 Pro: 1093,00 gespeichert gegen 1459,00 als
# Leitzahl). Gelesen werden nur die POSTEN.
#
# Jeder Lookup ist scharf: findet er nichts, ist das ein AssertionError,
# kein stilles Weiterlaufen. `_PF_MINDESTFAELLE` haelt zusaetzlich fest,
# wie viele Faelle wirklich durchgerechnet wurden.

_PF_MODELL_RE = re.compile(r"^(?P<basis>.+)-(?P<gb>\d+)gb(?:-.*)?$")
_PF_LAGER_RE = re.compile(r'<div class="gr-bnd-lager" data-modell="')
_PF_DETAIL_RE = re.compile(r'<details class="gr-bnd"(.*?)</details>', re.S)
_PF_ATTR_RE = re.compile(r'data-([a-z]+)="([^"]*)"')
_PF_TARIF_RE = re.compile(r'gr-bnd-tarif">(.*?)</span>', re.S)
_PF_BAU_RE = re.compile(r'gr-kk-bau">(.*?)</p>', re.S)
_PF_RATEN_RE = re.compile(r"in (\d+) Raten")
_PF_BMONATE_RE = re.compile(r"zusammen · (\d+) Monate")

# Die vier Leitgeraete des Pruefauftrags, je Anbieter ein Buendel. Die
# Sollwerte stehen NICHT hier - sie werden unten aus den Rohdaten
# gerechnet; hier stehen nur die Zeilen, die auf der Seite gesucht werden.
_PF_FAELLE = (
    ("apple-iphone-17-pro-256", "congstar", "Allnet Flat XS"),
    ("apple-iphone-17-pro-256", "Vodafone", "Mobil XS"),
    ("apple-iphone-17-256", "Vodafone", "Mobil XS"),
    ("apple-iphone-17-256", "Vodafone", "Mobil M"),
    ("apple-iphone-17-256", "1&1", "1&1 All-Net-Flat S"),
    ("samsung-galaxy-s26-ultra-256", "congstar", "Allnet Flat S"),
    ("samsung-galaxy-s26-ultra-256", "Vodafone", "Mobil S"),
    ("samsung-galaxy-s26-ultra-256", "o2",
     "O2 Mobile Unlimited M Plus mit 100 MBit/s (24 Mon.)"),
    ("google-pixel-10-pro-128", "Vodafone", "Mobil XS"),
    ("google-pixel-10-pro-128", "o2",
     "O2 Mobile on Demand M Plus mit 50 GB+ (24 Mon.)"),
)
_PF_MINDESTFAELLE = len(_PF_FAELLE)


def _pf_modell(sku_id: str) -> str:
    """`apple-iphone-17-pro-256gb-silber` -> `apple-iphone-17-pro-256`.

    Dieselbe Form, die die Seite als `data-modell` traegt - eigenstaendig
    aus der SKU gebildet, nicht aus `geraete_model` importiert."""
    treffer = _PF_MODELL_RE.match(sku_id or "")
    if treffer is None:
        return ""
    return f"{treffer.group('basis')}-{treffer.group('gb')}"


def _pf_historie() -> list[dict]:
    """Alle Zeilen der TCO-Historie - nur lesend, keine Umschreibung."""
    pfad = _GW_WURZEL / "data" / "state" / "geraete_tco_historie.jsonl"
    zeilen = [json.loads(z) for z in
              pfad.read_text(encoding="utf-8").splitlines() if z.strip()]
    assert len(zeilen) >= 3000, (
        f"nur {len(zeilen)} Historienzeilen gelesen - der Bestand ist "
        "kleiner als am 21.09.2026 (3854), der Test greift nicht mehr")
    return zeilen


def _pf_anbieter_segment(satz_id: str) -> str:
    """Das Anbietersegment einer Buendel-ID (`buendel--o2--...`)."""
    teile = (satz_id or "").split("--")
    return teile[1] if len(teile) > 2 else ""


def _pf_letzte_messung(historie: list[dict], modell: str, anbieter_slug: str,
                       tarif_teil: str) -> dict:
    """Die JUENGSTE Historienzeile zu (Modell, Anbieter, Tarifsegment).

    Der Tarif steckt im letzten ID-Segment, nicht in einem eigenen Feld -
    verglichen wird deshalb auf dem ID-Segment. Mehrere Farben rechnen
    gleich; genommen wird die juengste Messung, bei Gleichstand die mit
    der lexikalisch kleinsten ID (stabil, nie zufaellig)."""
    treffer = []
    for satz in historie:
        satz_id = satz.get("id") or ""
        teile = satz_id.split("--")
        if len(teile) < 4:
            continue
        if _pf_anbieter_segment(satz_id) != anbieter_slug:
            continue
        if _pf_modell(teile[2]) != modell:
            continue
        if teile[3] != tarif_teil:
            continue
        treffer.append(satz)
    assert treffer, (
        "kein Messpunkt in der Historie fuer "
        f"{anbieter_slug}/{tarif_teil} zu {modell} - der Lookup greift ins "
        "Leere und dieser Test wuerde sonst gruen nichts pruefen")
    return sorted(treffer, key=lambda s: (s.get("datum", ""),
                                          s.get("id", "")))[-1]


def _pf_leitzahl_cent(satz: dict) -> int:
    """Die Soll-Leitzahl in Cent - EIGENE Rechnung aus den Posten.

    Rundung: jeder Posten wird einzeln auf ganze Cent gebracht (HALF_UP),
    dann summiert. Multiplikation nach der Rundung, weil die Quellen
    Monatsbetraege in Cent nennen - eine Rate von 30,50 EUR ist 3050
    Cent, nicht 30,4999.

    Eine Luecke ist eine Luecke: fehlt ein Posten, wirft diese Funktion.
    Keine 0, kein `or`-Vorgabewert (CLAUDE.md Clean Code 3)."""
    for feld in ("geraet_zuzahlung", "anschlusspreis", "laufzeit_monate"):
        assert satz.get(feld) is not None, (
            f"Posten {feld} fehlt in {satz.get('id')} - eine Leitzahl "
            "daraus waere geraten")
    laufzeit = int(satz["laufzeit_monate"])
    zuzahlung = _gw_cent(satz["geraet_zuzahlung"])
    anschluss = _gw_cent(satz["anschlusspreis"])
    buendelbetrag = satz.get("buendel_monatlich")
    rate = satz.get("geraet_monatsrate")
    tarif = satz.get("tarif_monatlich")
    if buendelbetrag is not None:
        assert tarif is None and rate is None, (
            f"{satz.get('id')} traegt Buendelbetrag UND getrennte Posten - "
            "welcher gilt, ist dann eine Meinung")
        return (zuzahlung + _gw_cent(buendelbetrag) * laufzeit + anschluss)
    assert tarif is not None and rate is not None, (
        f"{satz.get('id')} hat weder Buendelbetrag noch Tarif+Rate")
    return (zuzahlung + _gw_cent(tarif) * _GW_HORIZONT
            + _gw_cent(rate) * laufzeit + anschluss)


def _pf_seitenzeilen(fragment: str, geraete_html: str = "") -> dict:
    """{modell: [{anbieter, tarif, gesamt_cent, laufzeit_raten, ...}]}

    Gelesen wird das GERENDERTE HTML, nie ein Python-Objekt. Die
    Buendelliste steht je Modell in einem `gr-bnd-lager`-Block des
    Nachladefragments; das STARTMODELL bringt keinen Lager-Block mit -
    seine zwoelf Zeilen stehen inline in geraete.html, und seine Modell-ID
    steht dort als `vorgabe` im JSON-Block `gr-zeitreihe-daten`. Ohne
    diesen Zweig fehlt genau das Geraet, das die Seite zuerst zeigt."""
    zeilen: dict = {}
    for block in _PF_LAGER_RE.split(fragment)[1:]:
        modell = block[:block.index('"')]
        zeilen.setdefault(modell, []).extend(_pf_zeilen_aus_block(block))
    if not geraete_html:
        return zeilen
    daten = re.search(
        r'<script type="application/json" id="gr-zeitreihe-daten">(.*?)'
        r"</script>", geraete_html, re.S)
    assert daten is not None, (
        "geraete.html ohne JSON-Block gr-zeitreihe-daten - die Modell-ID "
        "der Startansicht ist damit nicht bestimmbar")
    start = json.loads(daten.group(1)).get("vorgabe") or ""
    assert start, "kein `vorgabe`-Modell im JSON-Block der Startansicht"
    inline = _pf_zeilen_aus_block(geraete_html)
    assert inline, (
        f"die Startansicht ({start}) rendert keine einzige Buendelzeile - "
        "der Lookup greift ins Leere")
    zeilen.setdefault(start, []).extend(inline)
    return zeilen


def _pf_zeilen_aus_block(block: str) -> list:
    out = []
    for roh in _PF_DETAIL_RE.findall(block):
        attr = dict(_PF_ATTR_RE.findall(roh))
        if "gesamt" not in attr or not attr["gesamt"]:
            continue
        tarif = _PF_TARIF_RE.search(roh)
        bau = _PF_BAU_RE.search(roh)
        text = " ".join(_gw_text(bau.group(1)).split()) if bau else ""
        raten = _PF_RATEN_RE.search(text) or _PF_BMONATE_RE.search(text)
        out.append({
            "anbieter": _gw_text(attr.get("anbieter", "")),
            "zustand": attr.get("zustand", ""),
            "tarif": " ".join(_gw_text(
                tarif.group(1)).split()).split(" · ")[0] if tarif else "",
            "gesamt_cent": _gw_cent(attr["gesamt"]),
            "laufzeit_raten": int(raten.group(1)) if raten else None,
            "bau": text,
        })
    return out


def _gw_text(roh: str) -> str:
    """HTML-Fragment -> Text (Tags weg, Entities aufgeloest)."""
    import html as _h
    return _h.unescape(re.sub(r"<[^>]+>", " ", roh))


def test_pf_leitzahl_von_zehn_buendeln_gegen_die_historie(gw_seite):
    """Die zweite Rechnung: zehn Leitzahlen der gerenderten Seite gegen
    eine EIGENE Cent-Rechnung aus `geraete_tco_historie.jsonl`.

    Vier Geraete (iPhone 17 Pro 256, iPhone 17 256, Galaxy S26 Ultra 256,
    Pixel 10 Pro 128) x je Anbieter ein Buendel. Gerechnet wird
    Anzahlung + 24 x Tarif + Laufzeit x Rate + Anschlusspreis, bei 1&1
    Anzahlung + Laufzeit x Buendelbetrag + Anschlusspreis.

    Greift ein Lookup ins Leere (Modell nicht gerendert, Tarif nicht in
    der Historie), ist das rot - nicht uebersprungen."""
    historie = _pf_historie()
    seite = _pf_seitenzeilen(gw_seite["buendel"], gw_seite["geraete"])
    assert seite, "kein einziger Buendelblock im gerenderten HTML"

    # Anbietername der Seite -> Anbietersegment der Buendel-ID.
    slug = {"congstar": "congstar", "Vodafone": "vodafone", "o2": "o2",
            "Telekom": "telekom", "1&1": "1-1"}
    geprueft = []
    for modell, anbieter, tarif in _PF_FAELLE:
        kandidaten = [z for z in seite.get(modell, [])
                      if z["anbieter"] == anbieter and z["tarif"] == tarif
                      and z["zustand"] == "neu"]
        assert kandidaten, (
            f"Die Seite fuehrt kein neu-Buendel {anbieter}/{tarif} zu "
            f"{modell} - Lookup ins Leere, der Test prueft sonst nichts")
        satz = _pf_letzte_messung(
            historie, modell, slug[anbieter],
            # Das Tarifsegment der ID ist der normalisierte Tarifname.
            re.sub(r"[^a-z0-9]+", "-", tarif.lower()).strip("-"))
        soll = _pf_leitzahl_cent(satz)
        ist = min(z["gesamt_cent"] for z in kandidaten)
        assert ist == soll, (
            f"{modell} / {anbieter} / {tarif}: Seite zeigt "
            f"{ist / 100:.2f} EUR, die eigene Rechnung aus "
            f"{satz['id']} (Messung {satz['datum']}, Laufzeit "
            f"{satz['laufzeit_monate']} Monate) ergibt {soll / 100:.2f} EUR")
        # Mutationsprobe: ein Euro daneben MUSS auffallen.
        assert ist + 100 != soll and ist - 100 != soll
        geprueft.append((modell, anbieter, tarif))

    assert len(geprueft) >= _PF_MINDESTFAELLE, (
        f"nur {len(geprueft)} von {_PF_MINDESTFAELLE} Faellen "
        "nachgerechnet - der Test greift nicht mehr")


def test_pf_die_gezeigte_ratenlaufzeit_ist_eine_gemessene(gw_seite):
    """Jede Laufzeit im Rechenweg der Seite muss im Bestand stehen.

    Die Seite schreibt "1.098,00 EUR in 36 Raten a 30,50 EUR". Diese 36
    muss die GEMESSENE `laufzeit_monate` eines Buendels desselben
    (Anbieter, Modell, Tarif, Zustand) sein - eine geratene
    Standardlaufzeit im Rechenweg waere eine erfundene Aussage
    (CLAUDE.md Clean Code 3/4).

    Gegenprobe gegen einen leeren Lauf: der Test zaehlt die gepruefte
    Menge und wird rot, wenn sie unter den Stand vom 21.09.2026 faellt."""
    # Geprueft wird gegen die HISTORIE, nicht gegen den Stand: Seite und
    # Stand lesen dieselbe Datei, ein Vergleich der zwei kann per
    # Konstruktion nicht auseinanderfallen. Die Historie ist die zweite,
    # unabhaengig geschriebene Quelle derselben Messung.
    historie = _pf_historie()
    slug_zu_name = {"congstar": "congstar", "vodafone": "Vodafone",
                    "o2": "o2", "telekom": "Telekom", "1-1": "1&1"}
    gemessen: dict = {}
    for satz in historie:
        teile = (satz.get("id") or "").split("--")
        if len(teile) < 4:
            continue
        anbieter = slug_zu_name.get(_pf_anbieter_segment(satz["id"]))
        if anbieter is None:
            continue
        schluessel = (anbieter, _pf_modell(teile[2]), teile[3],
                      satz.get("zustand") or "")
        gemessen.setdefault(schluessel, set()).add(
            satz.get("laufzeit_monate"))

    seite = _pf_seitenzeilen(gw_seite["buendel"], gw_seite["geraete"])
    geprueft, fehler, ohne_historie = 0, [], 0
    for modell, zeilen in seite.items():
        for z in zeilen:
            if z["laufzeit_raten"] is None:
                continue
            tarifteil = re.sub(r"[^a-z0-9]+", "-",
                               z["tarif"].lower()).strip("-")
            treffer = gemessen.get((z["anbieter"], modell, tarifteil,
                                    z["zustand"]))
            if not treffer:
                # Ein Buendel, das erst heute zum ersten Mal gesehen wurde,
                # hat noch keine Historienzeile - das ist keine Abweichung,
                # aber es wird gezaehlt, damit die Menge nicht still kippt.
                ohne_historie += 1
                continue
            geprueft += 1
            if z["laufzeit_raten"] not in treffer:
                fehler.append((modell, z["anbieter"], z["tarif"],
                               f"Seite {z['laufzeit_raten']}, in der "
                               f"Historie {sorted(treffer)}"))
    assert ohne_historie <= 20, (
        f"{ohne_historie} gerenderte Buendel ohne jede Historienzeile - "
        "die Zuordnung Seite/Historie greift nicht mehr")
    assert geprueft >= 300, (
        f"nur {geprueft} Rechenwege gegen die Historie gehalten - am "
        "21.09.2026 waren es 362; der Lookup greift ins Leere")
    assert not fehler, (
        f"{len(fehler)} Rechenwege mit nicht gemessener Laufzeit: "
        f"{fehler[:5]}")


# ==========================================================================
# Zwei Ratenlaufzeiten desselben Tarifs - zwei Tests, zwei Fragen
# --------------------------------------------------------------------------
# Bis zum 21.09.2026 stand hier EIN Test
# (`test_pf_beide_ratenlaufzeiten_eines_tarifs_stehen_auf_der_seite`), der
# beides in einem verlangte: dass der Bestand zwei Laufzeiten TRAEGT und
# dass die Seite sie ZEIGT. Er kann nicht gruen werden, denn er misst den
# committeten Produktionsbestand, und dort traegt keine einzige Gruppe
# zwei Laufzeiten. Ein Orakel, das dauerhaft rot bleibt, faerbt ci.yml rot
# und begraebt jeden WEITEREN Fehlschlag im bekannten Rot - genau die
# Fehlerklasse, die ein Tor unbrauchbar macht. Die Aussage ist deshalb
# aufgeteilt:
#   1. `test_pf_beide_ratenlaufzeiten_eines_congstar_abrufs_werden_zwei_zeilen`
#      prueft die MECHANIK am gespeicherten echten congstar-Abruf, in dem
#      24 und 36 Monate belegt sind - Adapter, Store, render_site.
#   2. `test_pf_bestand_zaehlt_seine_ratenlaufzeiten_und_haelt_die_luecke_fest`
#      prueft die BESTANDSLAGE und faellt nur bei einer Regression.
# ==========================================================================
import gzip as _pf_gzip

_PF_MECHANIK_HEUTE = "2026-09-20"
_PF_CS_FIXTURE = "congstar_tarifseite_allnet_flat_m.html.gz"
_PF_CS_URL = ("https://www.congstar.de/handytarife/allnet-flat-tarife/"
              "allnet-flat-m/")
# Das Geraet des Abrufs, an dem beide Zahlweisen desselben Tarifs stehen.
_PF_CS_TITEL = "Apple iPhone 17 Pro 512 GB cosmic orange"
_PF_CS_TARIF = "Allnet Flat M"
_PF_CS_BLATT = "congstar:allnet-flat-m"
_PF_CS_SKU = "apple-iphone-17-pro-512gb-cosmic-orange"
_PF_CS_MODELL = "apple-iphone-17-pro-512"


def _pf_wegwerf_wurzel(tmp_path, buendel, blatt: dict):
    """Ein Wegwerf-Repo (config/, data/state/, data/reports/) und der
    gerenderte Stand darin. Weder `site/` noch `data/` des Repos werden
    angefasst (harte Regel 1/3)."""
    import yaml

    from telco_radar.analyze.tco_store import TcoDB

    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    konfig = {
        "geraete_katalog.yaml": {"geraete": [
            {"hersteller": "Apple", "modell": "iPhone 17 Pro",
             "generation": 17, "marktstart": "2025-09-19",
             "speicher": [512], "segment": "premium"}]},
        "farben.yaml": {"farben": {"cosmic orange": ["Cosmic Orange"]}},
        "geraete_quellen.yaml": {"anbieter": [
            {"name": "congstar", "typ": "discount", "netz": "Telekom",
             "rang": 3, "methode": "congstar_next",
             "basis_url": "https://www.congstar.de",
             "einstiege": [{"url": _PF_CS_URL, "kind": "buendel"}]}]},
    }
    for name, daten in konfig.items():
        (tmp_path / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False),
            encoding="utf-8")

    state = tmp_path / "data" / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "tarife.jsonl").write_text(
        json.dumps(blatt, ensure_ascii=False) + "\n", encoding="utf-8")
    (state / "geraete_preise.jsonl").write_text("", encoding="utf-8")
    (state / "geraete_db.json").write_text(json.dumps({
        "updated": _PF_MECHANIK_HEUTE,
        "anbieter": {"congstar": {"laeufe": 4, "funde_gesamt": 1}},
        "listungen": [{
            "id": f"congstar--{_PF_CS_SKU}", "sku_id": _PF_CS_SKU,
            "device_id": "apple-iphone-17-pro", "anbieter": "congstar",
            "anbieter_typ": "discount", "netz": "Telekom",
            "speicher_gb": 512, "farbe_roh": "Cosmic Orange",
            "farbe_normalisiert": "cosmic orange", "zustand": "neu",
            "first_seen": _PF_MECHANIK_HEUTE,
            "last_verified": _PF_MECHANIK_HEUTE, "status": "aktiv",
            "missed_checks": 0, "preis_ohne_vertrag": None,
            "quelle_url": _PF_CS_URL, "abgerufen_am": _PF_MECHANIK_HEUTE,
            "verfuegbarkeit": "lieferbar", "confidence": "hoch",
            "einstiege": [_PF_CS_URL]}]}, ensure_ascii=False),
        encoding="utf-8")

    db = TcoDB(state / "geraete_tco.json")
    db.upsert_buendel(buendel, _PF_MECHANIK_HEUTE)
    assert db.save(_PF_MECHANIK_HEUTE), \
        "der Store hat nichts geschrieben - ohne Bestand rendert nichts"

    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"{_PF_MECHANIK_HEUTE}.json").write_text(json.dumps({
        "date": _PF_MECHANIK_HEUTE, "language": "de",
        "briefing_md": "## Auf einen Blick\n\n- Nichts Besonderes.\n",
        "stats": {}, "regions": []}), encoding="utf-8")
    (reports / f"{_PF_MECHANIK_HEUTE}.md").write_text(
        "# Bericht\n", encoding="utf-8")

    site = tmp_path / "site"
    render_site(site, reports)
    return site


def test_pf_beide_ratenlaufzeiten_eines_congstar_abrufs_werden_zwei_zeilen(
        tmp_path):
    """MECHANIK-GEGENPROBE: zwei Zahlweisen, zwei Zeilen, eigene Zahlen.

    GEMESSEN WIRD der ganze Weg an einem GESPEICHERTEN ECHTEN ABRUF -
    `tests/fixtures/geraete/congstar_tarifseite_allnet_flat_m.html.gz`
    (08.09.2026, HTTP 200). Nur dieser Abruf belegt beide Laufzeiten
    desselben Tarifs: Adapter (`congstar.lies_buendel`) -> Bestandsbezug
    (`tco_buendel.aus_rohsaetzen` am ECHTEN Tarifblatt
    `congstar:allnet-flat-m` aus `data/state/tarife.jsonl`, nur gelesen)
    -> Store (`TcoDB.upsert_buendel`/`save`) -> `render_site` in einen
    Wegwerfordner. Geprueft wird das gerenderte HTML.

    Der gemessene Fall (Apple iPhone 17 Pro 512 GB, Allnet Flat M):
      24 Raten a 50,25 EUR und 36 Raten a 33,50 EUR, je 97,00 EUR
      Zuzahlung, Tarif 24,00 EUR, Anschlusspreis 0,00 EUR.
    congstar finanziert zum Nulltarif - beide Zahlweisen ergeben dieselbe
    Leitzahl (1.879,00 EUR). Unterscheidbar sind sie an Rate, Ratenzahl
    und Restschuld: die 36er traegt nach Monat 24 noch 402,00 EUR offen
    (12 Geraeteraten), die 24er nichts. Genau das wird geprueft, damit
    der Test nicht auf zwei identischen Zeilen gruen wird.

    NICHT GEMESSEN wird die Bestandslage: ob der Produktionsbestand
    ueberhaupt Gruppen mit zwei Laufzeiten kennt, sagt
    `test_pf_bestand_zaehlt_seine_ratenlaufzeiten_und_haelt_die_luecke_fest`.
    Auch nicht gemessen: die Anbieterseiten selbst (aus dieser Umgebung
    nicht erreichbar) und die Optik der Zeilen.

    GEGEN DEN ALTEN STAND ROT - zweimal ausgefuehrt (21.09.2026, je ein
    Wegwerf-Worktree, dieselbe Testdatei hineinkopiert):
      - fde7f63 (vor P0-B): rot an der ersten Gegenprobe, der Adapter
        liest nur EINE Zahlweise -
        "belegt nicht beide Laufzeiten ...: [36]".
      - e6ab202 (P0-B-fix1, also NACH der Adaptererweiterung und VOR dem
        Kartenschluessel aus fix2): rot an der Seite -
        "1 statt 2 Buendelzeilen fuer apple-iphone-17-pro-512 ...
        gezeigte Ratenlaufzeiten: [24]". Dort entdoppelt
        `geraete_tco_karten.modelle` je (Anbieter, Tarif,
        `karte["laufzeit"]`, Zustand), und `karte["laufzeit"]` ist die
        KONSTANTE `LAUFZEIT` (= `TCO_HORIZONT` = 24); von beiden
        Zahlweisen bleibt eine Zeile uebrig.
    Der Test faellt also an JEDER der beiden Stellen, an denen die
    Mehrfacherfassung schon einmal kaputt war.
    """
    from telco_radar.analyze.tco_buendel import aus_rohsaetzen
    from telco_radar.collect.geraete.congstar import lies_buendel
    from telco_radar.tarif_bezug import Tarifbestand

    pfad = Path(__file__).parent / "fixtures" / "geraete" / _PF_CS_FIXTURE
    antwort = _pf_gzip.open(pfad, "rb").read().decode("utf-8", "replace")
    rohsaetze = [s for s in lies_buendel(antwort, url=_PF_CS_URL)
                 if s["titel"] == _PF_CS_TITEL
                 and s["tarif_name"] == _PF_CS_TARIF]
    # Gegenprobe am Adapter: ohne zwei Laufzeiten im ABRUF prueft der Rest
    # nichts (die Fixture waere getauscht worden).
    assert {s["laufzeit_monate"] for s in rohsaetze} == {24, 36}, (
        f"der gespeicherte Abruf {_PF_CS_FIXTURE} belegt nicht beide "
        f"Laufzeiten fuer {_PF_CS_TITEL}/{_PF_CS_TARIF}: "
        f"{sorted(s['laufzeit_monate'] for s in rohsaetze)}")

    blatt = next(
        (json.loads(z) for z in
         (_GW_WURZEL / "data" / "state" / "tarife.jsonl")
         .read_text(encoding="utf-8").splitlines()
         if z.strip() and json.loads(z).get("tarif_id") == _PF_CS_BLATT),
        None)
    assert blatt is not None, (
        f"Tarifblatt {_PF_CS_BLATT} fehlt im Bestand - ohne aufloesbaren "
        "Tarif legt der Store kein Buendel ab (benannte Luecke)")

    bilanz = aus_rohsaetzen(
        [{**s, "anbieter": "congstar", "sku_id": _PF_CS_SKU,
          "quelle_url": s["url"]} for s in rohsaetze],
        Tarifbestand([blatt]), _PF_MECHANIK_HEUTE)
    assert len(bilanz.buendel) == 2, (
        f"{len(bilanz.buendel)} statt 2 Buendel aus zwei Rohsaetzen - "
        f"{bilanz.ohne_tarif} ohne aufloesbaren Tarif, "
        f"haeufigste: {bilanz.offene_tarife}")

    site = _pf_wegwerf_wurzel(tmp_path, bilanz.buendel, blatt)
    seite = _pf_seitenzeilen(
        (site / "data" / "geraete-buendel.html").read_text(encoding="utf-8"),
        (site / "geraete.html").read_text(encoding="utf-8"))
    zeilen = [z for z in seite.get(_PF_CS_MODELL, [])
              if z["anbieter"] == "congstar" and z["tarif"] == _PF_CS_TARIF
              and z["zustand"] == "neu"]
    assert len(zeilen) == 2, (
        f"{len(zeilen)} statt 2 Buendelzeilen fuer {_PF_CS_MODELL} - "
        "zwei Zahlweisen desselben Tarifs ueberschreiben sich wieder; "
        f"gezeigte Ratenlaufzeiten: "
        f"{[z['laufzeit_raten'] for z in zeilen]}")

    je_laufzeit = {z["laufzeit_raten"]: z for z in zeilen}
    assert set(je_laufzeit) == {24, 36}, (
        "die zwei Zeilen nennen nicht 24 und 36 Raten, sondern "
        f"{sorted(je_laufzeit)}")

    # Jede Zeile traegt IHRE Zahlen - Rate, Ratenzahl, Restschuld. Soll
    # aus der EINEN Definition dieses Abschnitts (`_pf_leitzahl_cent`),
    # gerechnet auf dem ROHSATZ des Adapters, nicht auf der Seite.
    for satz in rohsaetze:
        laufzeit = satz["laufzeit_monate"]
        zeile = je_laufzeit[laufzeit]
        soll = _pf_leitzahl_cent(
            {**satz, "id": f"congstar/{laufzeit}m"})
        _gw_vergleiche(_gw_Dez(zeile["gesamt_cent"]) / 100, soll,
                       f"congstar {_PF_CS_TARIF}, {laufzeit} Raten")
        # Der Betrag in der Schreibweise der Seite - aus Cent, nicht aus
        # einer Fliesskomma-Formatierung (Geld rechnet dieser Abschnitt in
        # ganzen Cent, siehe `_gw_cent`).
        rate_cent = _gw_cent(satz["geraet_monatsrate"])
        rate = f"{rate_cent // 100},{rate_cent % 100:02d}"
        assert f"in {laufzeit} Raten à {rate} €" in zeile["bau"], (
            f"die {laufzeit}-Monats-Zeile nennt ihre Rate nicht: "
            f"{zeile['bau']}")
    assert je_laufzeit[24]["gesamt_cent"] == je_laufzeit[36]["gesamt_cent"], (
        "congstar finanziert zum Nulltarif - weichen die Leitzahlen ab, "
        "hat sich die Rechnung geaendert und dieser Test ist neu zu "
        f"verankern: {je_laufzeit[24]['gesamt_cent']} gegen "
        f"{je_laufzeit[36]['gesamt_cent']}")

    # Die Restschuld trennt die zwei Zeilen: 12 Raten a 33,50 EUR bleiben
    # nach Monat 24 offen, bei 24 Raten nichts.
    inline = (site / "geraete.html").read_text(encoding="utf-8")
    offen = re.findall(
        r"danach noch offen: ([\d.,]+) € \((\d+) Geräteraten\)", inline)
    assert offen == [("402,00", "12")], (
        "genau die 36-Monats-Zeile muss ihre Restschuld nennen (402,00 € "
        f"aus 12 Geraeteraten), gefunden: {offen}")


# Der Stand des Bestands am 22.09.2026 (`data/state/geraete_tco.json`,
# `updated` 2026-09-22), gemessen und nicht geschaetzt - Grundlage der
# Aussage unten.
#
# NACHGEZOGEN AM 22.09.2026 (vorher: Stand 2026-09-20, congstar [36],
# 0 Mehrlaufzeit-Gruppen). Grund: Lauf 51 vom 22.09. war der erste
# Produktionslauf MIT P0-B - der congstar-Adapter liest seither beide
# Zahlweisen desselben Tarifs, und der Buendelschluessel traegt die
# Laufzeit (`...--allnet-flat-xs--24m` / `--36m`). Nachgerechnet, nicht
# abgeschrieben: die 80 neuen 24-Monats-Buendel summieren auf DIESELBE
# Leitzahl wie ihre 36-Monats-Geschwister (congstar finanziert zum
# Nulltarif, Beispiel Pflichtfall 24 x 45,75 = 36 x 30,50 = 1.098,00 EUR),
# und die Zahl der congstar-SKUs ist mit 10 unveraendert - es ist eine
# zweite Zahlweise dazugekommen, kein Datensatz verlorengegangen.
#
# KEINE UNTERGRENZEN. Eine Untergrenze auf einer Zahl, die heute schon am
# Boden steht, ist keine Zusicherung: `len(mehrfach) >= 0` ist fuer jede
# Menge wahr und kann nie fallen (CLAUDE.md Regel 10 - ein Test, dessen
# Lookup ins Leere laeuft, ist gruen und prueft nichts). Die Zahlen unten
# sind deshalb EXAKTE ANKER: sie fallen in BEIDE Richtungen, und ein
# Fallen ist die Meldung dieses Tests, kein Fehler (siehe Docstring).
_PF_STAND_TAG = "2026-09-22"
_PF_STAND_MEHRLAUFZEIT = 80       # Gruppen mit ZWEI Ratenlaufzeiten
# Die Ratenlaufzeiten JE ANBIETER - der eigentliche Befund. Telekom, o2
# und 1&1 tragen weiterhin ausnahmslos 36 Monate; congstar traegt seit
# dem 22.09. 24 UND 36; Vodafone kennt drei, bindet sie aber je Tarifname
# an genau eine (Mobil S 12, Mobil M 24, Mobil XS 36) - darum traegt trotz
# dreier Laufzeiten keine VODAFONE-Gruppe zwei. Alle 80
# Mehrlaufzeit-Gruppen sind congstar-Gruppen.
_PF_STAND_LAUFZEITEN = {
    "1&1": [36], "Telekom": [36], "Vodafone": [12, 24, 36],
    "congstar": [24, 36], "o2": [36],
}
_PF_MINDEST_GRUPPEN = 200         # Anti-Leerlauf, nicht der Stand (509)


def test_pf_bestand_zaehlt_seine_ratenlaufzeiten_und_haelt_die_luecke_fest():
    """BESTANDSAUSSAGE: was der echte Bestand an Ratenlaufzeiten traegt.

    Stand am 22.09.2026 (`data/state/geraete_tco.json`, `updated`
    2026-09-22, 906 Buendel), jede Zahl gemessen (vorher 20.09.2026,
    792 Buendel, 0 Mehrlaufzeit-Gruppen - siehe "WAS SICH GEAENDERT HAT"):
      - 80 von 509 Gruppen (Anbieter, Modell, Tarif, Zustand) tragen ZWEI
        Ratenlaufzeiten; alle 80 sind congstar und alle 80 sind frisch
        (390 Gruppen sind frisch).
      - Je Anbieter: 1&1 nur 36 (74 Buendel), Telekom nur 36 (45),
        o2 nur 36 (73), congstar 36 (136) UND 24 (80), Vodafone 12 (169),
        24 (166) und 36 (163).
      - congstar traegt die zweite Zahlweise ueber alle acht Tarife
        gleichmaessig: Allnet Flat XS/S/M/L und ihre Flex-Varianten je
        17 Buendel ueber 36 Monate und 10 ueber 24.
      - Vodafone bindet die Laufzeit weiterhin an den TARIF: Mobil S
        immer 12 (169 von 169), Mobil M immer 24 (166 von 166), Mobil XS
        immer 36 (163 von 163). Das sind nicht drei Angebote, das ist
        EINE Laufzeit je Tarif - darum traegt bei Vodafone keine GRUPPE
        zwei Laufzeiten, obwohl der Anbieter drei kennt.
      - 0 Buendel ohne gemessene Laufzeit.
      - Die Historie sagt dasselbe ueber die Zeit: 4936 Zeilen, davon
        1-1 (726), o2 (634) und Telekom (35) AUSNAHMSLOS 36 Monate;
        congstar 560 Zeilen ueber 36 und 80 ueber 24 (alle 80 vom
        22.09.2026); Vodafone 2901 Zeilen, 12/24/36 je an ihren Tarif
        gebunden. 482 Historiengruppen, davon 80 mit zwei Laufzeiten -
        auch hier ausschliesslich congstar.

    WAS SICH GEAENDERT HAT (22.09.2026, Lauf 51 - der erste
    Produktionslauf mit P0-B): congstar liefert seither beide Zahlweisen
    desselben Tarifs, und der Buendelschluessel traegt die Laufzeit. Der
    Test faellt damit in seine GUTE Richtung; nachgerechnet wurde, bevor
    der Anker nachgezogen wurde:
      - Die Zahl der congstar-SKUs ist mit 10 unveraendert (17.09.: 11,
        20./21.09.: 10) - die 160 Historienzeilen vom 22.09. sind
        10 SKUs x 8 Tarife x 2 Zahlweisen. Es ist nichts verlorengegangen.
      - Die Leitzahl aendert sich NICHT: congstar finanziert zum
        Nulltarif, der Finanzierungsbetrag ist in beiden Zahlweisen
        derselbe (Pflichtfall iPhone 17 Pro 256 GB / Allnet Flat XS:
        24 x 45,75 = 36 x 30,50 = 1.098,00 EUR; mit 1,00 EUR Zuzahlung,
        24 x 15,00 EUR Tarif und 0,00 EUR Anschlusspreis in beiden
        Faellen 1.459,00 EUR).
      - Die Seite ZEIGT beide: der Server-First-Paint fuehrt zum
        Startpaar (Apple iPhone 17 Pro 256 GB, Band klein) zwei
        congstar-Buendelzeilen je Tarif, "1.098,00 EUR in 36 Raten a
        30,50 EUR" und "1.098,00 EUR in 24 Raten a 45,75 EUR", beide mit
        1.459,00 EUR Leitzahl. Geprueft wird das in
        `test_leitzahl_congstar_xs_iphone17pro256_am_bestand` (Schritt 3b)
        und `test_monatsschnitt_und_restschuld_des_pflichtfalls_am_bestand`
        (First Paint, beide Zahlweisen).

    WARUM DAS SO IST: die Erhebung ist defensiv gebaut (der Schluessel
    traegt die Laufzeit, der congstar-Weg ist mit
    `test_pf_beide_ratenlaufzeiten_eines_congstar_abrufs_werden_zwei_zeilen`
    belegt), aber in den GESPEICHERTEN ECHTEN ABRUFEN liefern drei von
    fuenf Anbietern nur eine Laufzeit: Telekom
    (`telekom_kategorie_buendel_magentamobil_s.html.gz`,
    `numberOfInstallments":36` 9x und nichts anderes), o2
    (`o2_katalog_buendel.json.gz`, `rateDurationValue" : "36 Monate"`
    88x) und 1&1 (`currentHardwareOfferDuration = '36'` in allen vier
    Produktseiten-Fixtures). Zwei Laufzeiten sind nur bei congstar
    belegt (`congstar_tarifseite_allnet_flat_m.html.gz`:
    INSTALLMENT_PLAN/UNSPECIFIED/24 58x und /36 58x, TRADE_IN/24 56x und
    /36 58x; Allnet Flat S identisch) und bei Vodafone
    (`financingDuration` 12/24/36, je 5x in `vodafone_tarif_hardware.json`
    und je 3x in `vodafone_virtualitem.json`).

    Ob die Anbieterseiten heute mehr anbieten, kann diese Umgebung NICHT
    nachpruefen: das Gateway antwortet auf CONNECT fuer telekom.de,
    congstar.de, 1und1.de, vodafone.de und o2online.de mit 403. CLAUDE.md
    Fallstrick 16 verlangt genau diese Gegenprobe an der Anbieterseite,
    und sie ist hier nicht zu leisten. Der Verdacht auf eine
    Erfassungsluecke bleibt damit OFFEN. Dieser Test tut NICHT so, als
    waere er ausgeraeumt - er haelt ihn als Zahl sichtbar fest.

    GEPRUEFT WIRD MIT EXAKTEN ANKERN, NICHT MIT UNTERGRENZEN:
      1. Der Scan sieht ueberhaupt Gruppen (Anti-Leerlauf; hier steht
         bewusst eine Untergrenze, denn sie kann fallen - der Stand liegt
         mit 507 weit darueber).
      2. Kein Buendel traegt eine fehlende Laufzeit (Clean Code 3/4).
      3. Die Ratenlaufzeiten JE ANBIETER sind genau
         `_PF_STAND_LAUFZEITEN`.
      4. Die Zahl der Gruppen mit zwei Laufzeiten ist genau
         `_PF_STAND_MEHRLAUFZEIT` (= 0).

    WAS ZU TUN IST, WENN DIESER TEST FAELLT - er faellt in BEIDE
    Richtungen, und beide Richtungen sind eine Meldung, kein Fehler:
      * BESSER (3. oder 4. nennt MEHR Laufzeiten, etwa Telekom 24 und 36,
        oder eine Gruppe traegt zwei): die Erfassungsluecke schliesst
        sich. Anker hochsetzen, mit Datum und der neuen Messung in diesem
        Docstring, und pruefen, ob die Seite die zweite Laufzeit auch
        ZEIGT - dafuer ist der Mechanik-Test daneben da.
      * SCHLECHTER (3. oder 4. nennt WENIGER, ein Anbieter fehlt ganz,
        oder 1./2. fallen): die Mehrfacherfassung oder der Scan ist
        kaputt. Das ist ein echter Fehler und wird behoben, nicht
        umgeschrieben.
      In keinem Fall wird der Anker auf eine Untergrenze aufgeweicht.
      Genau das war der Befund vom 22.09.2026: `>= _PF_STAND_MEHRLAUFZEIT`
      mit dem Anker 0 war eine gruene Zeile ohne Aussage.

    NICHT GEPRUEFT: ob die Seite zwei Laufzeiten ZEIGT (das ist der
    Mechanik-Test), und ob der Bestand vollstaendig ist - er ist es
    ausdruecklich nicht.
    """
    tco, _blaetter, _db = _gw_rohdaten()
    heute = _gw_heute(tco)
    gruppen: dict = {}
    frische_gruppen: dict = {}
    je_anbieter: dict = {}
    ohne_laufzeit = []
    for b in tco["buendel"]:
        laufzeit = b.get("laufzeit_monate")
        if laufzeit is None:
            ohne_laufzeit.append(b.get("id"))
            continue
        schluessel = (b["anbieter"], _pf_modell(b["sku_id"]),
                      b["tarif_name"], b.get("zustand") or "")
        gruppen.setdefault(schluessel, set()).add(laufzeit)
        je_anbieter.setdefault(b["anbieter"], set()).add(laufzeit)
        if _gw_frisch(b, heute):
            frische_gruppen.setdefault(schluessel, set()).add(laufzeit)

    assert len(gruppen) >= _PF_MINDEST_GRUPPEN, (
        f"nur {len(gruppen)} Gruppen im Bestand vom {heute} - am "
        f"{_PF_STAND_TAG} waren es 509 (390 frisch); der Scan greift ins "
        "Leere und dieser Test wuerde sonst gruen nichts pruefen")
    assert not ohne_laufzeit, (
        f"{len(ohne_laufzeit)} Buendel ohne gemessene Ratenlaufzeit "
        f"({ohne_laufzeit[:5]}) - am {_PF_STAND_TAG} war es keines. Eine "
        "fehlende Laufzeit ist eine Luecke, keine 24")

    # EXAKT, nicht ">=": ein `>=` auf einer Zahl, die schon am Boden
    # steht, kann nicht fallen. Dieser Assert faellt, wenn ein Anbieter
    # eine Laufzeit DAZUGEWINNT (gute Nachricht, Anker nachziehen) UND
    # wenn er eine verliert oder ganz ausfaellt (Fehler, beheben).
    ist_laufzeiten = {a: sorted(v) for a, v in je_anbieter.items()}
    assert ist_laufzeiten == _PF_STAND_LAUFZEITEN, (
        f"die Ratenlaufzeiten je Anbieter sind {ist_laufzeiten}, am "
        f"{_PF_STAND_TAG} waren es {_PF_STAND_LAUFZEITEN}. MEHR Laufzeiten "
        "oder ein neuer Anbieter: die Erfassungsluecke schliesst sich - "
        "Anker samt Datum im Docstring nachziehen und pruefen, ob die "
        "Seite die zweite Laufzeit zeigt. WENIGER Laufzeiten oder ein "
        "fehlender Anbieter: die Mehrfacherfassung ist ausgefallen - das "
        "ist ein Fehler und wird behoben, nicht umgeschrieben.")

    mehrfach = {k: sorted(v) for k, v in gruppen.items() if len(v) > 1}
    frisch_mehrfach = {k: sorted(v) for k, v in frische_gruppen.items()
                       if len(v) > 1}
    assert len(mehrfach) == _PF_STAND_MEHRLAUFZEIT, (
        f"{len(mehrfach)} von {len(gruppen)} Gruppen tragen zwei "
        f"Ratenlaufzeiten, am {_PF_STAND_TAG} waren es genau "
        f"{_PF_STAND_MEHRLAUFZEIT} (von 509, alle congstar). MEHR: die "
        "Erfassungsluecke "
        "schliesst sich - Anker mit Datum und Messung hochsetzen. "
        "WENIGER: eine Gruppe hat ihre zweite Laufzeit verloren, das ist "
        f"ein Fehler. Frisch: {len(frisch_mehrfach)} von "
        f"{len(frische_gruppen)}; Beispiele: "
        f"{sorted(mehrfach.items())[:4]}")

def test_pf_simonly_mit_erhobenem_volumen_traegt_sein_band(gw_seite):
    """B3-Gegenprobe: kein SIM-only-Tarif verliert sein Band.

    `tarif_bezug.Tarifbestand.je_id_aktuell` ist AUSSCHLIESSLICH auf den
    baren Schluessel (`tarif_model.zeitreihen_basis`) gefasst. Fuenf
    SIM-only-Referenzen des Bestands tragen aber die Lesart im eigenen
    `tarif_id` (`telekom:magentamobil-l#live_shop`, ebenso s/m/xl und
    `o2:o2-mobile-unlimited-m-flex#live_shop`); ihr Nachschlagen geht
    seit B3 ins Leere. Vorher (HEAD 9999658) stand im TCO-Export
    "MagentaMobil L; Gross", "MagentaMobil M; Mittel", "MagentaMobil S;
    Mittel" - jetzt steht dort nichts.

    Ein erhobener Wert, der zur Luecke wird, ist ein Datenverlust; die
    Zeile faellt zugleich aus jedem Bandraster der Vergleichsansicht."""
    _tco, blaetter, _db = _gw_rohdaten()

    def volumen(tarif_id: str):
        for blatt in blaetter.get(tarif_id, []):
            gb = blatt.get("datenvolumen_gb")
            if gb is None:
                continue
            try:
                wert = float(gb)
            except (TypeError, ValueError):
                continue
            if _gw_math.isnan(wert) or _gw_math.isinf(wert):
                continue
            return wert
        return None

    with gw_seite["csv"].open(encoding="utf-8-sig", newline="") as f:
        zeilen = [r for r in _gw_csv.DictReader(f, delimiter=";")
                  if r.get("Art") == "SIM-only"]
    assert zeilen, "Export ohne SIM-only-Zeilen"

    stand = json.loads((_GW_WURZEL / "data" / "state" / "geraete_tco.json")
                       .read_text(encoding="utf-8"))
    tarif_je_name = {(r["anbieter"], r["tarif_name"]): r.get("tarif_id") or ""
                     for r in stand["sim_only"]}

    ohne_band, geprueft = [], 0
    for r in zeilen:
        tarif_id = tarif_je_name.get((r["Anbieter"], r["Tarif"]))
        if not tarif_id:
            continue
        gb = volumen(tarif_id)
        if gb is None:
            continue                 # kein erhobenes Volumen: kein Band
        geprueft += 1
        if not (r.get("Band") or "").strip():
            ohne_band.append((r["Anbieter"], r["Tarif"], tarif_id, gb))
    assert geprueft >= 20, (
        f"nur {geprueft} SIM-only-Zeilen mit erhobenem Datenvolumen "
        "geprueft - der Lookup greift ins Leere")
    assert not ohne_band, (
        f"{len(ohne_band)} SIM-only-Zeilen mit erhobenem Datenvolumen ohne "
        f"Band: {ohne_band[:6]}")


# ==========================================================================
# ZWEITE RECHNUNG DES PRUEFERS - Behebungsrunde P0-B (21.09.2026)
# ==========================================================================
# Geschrieben vom PRUEFER, nicht vom Bauer. Gelesen wird das GERENDERTE
# HTML und die gerenderte CSV, gerechnet wird mit `decimal` aus
# `data/state/geraete_tco_historie.jsonl` - kein Import aus
# `telco_radar.tco_model`, `report.geraete_tco_karten` oder
# `report.geraete_radar`.
#
# Jeder Lookup ist scharf: wo nichts gefunden wird, wirft der Test statt
# gruen durchzulaufen (CLAUDE.md Regel 10).
#
# DREI DIESER TESTS SIND ABSICHTLICH ROT - sie halten die Befunde der
# Pruefung fest. Wer sie gruen macht, hat den Befund behoben; wer sie
# loescht, hat ihn versteckt.

import html as _pr_html

_PR_DETAIL_RE = re.compile(r'<details class="gr-bnd"(.*?)</details>', re.S)
_PR_ATTR_RE = re.compile(r'data-([a-z]+)="([^"]*)"')
_PR_LABEL_RE = re.compile(r'gr-bnd-label">([^<]*)<')
_PR_RWZ_RE = re.compile(r'gr-bnd-rw-z">(.*?)</p>', re.S)
_PR_NAME_RE = re.compile(r'gr-bnd-name">([^<]*)<')
_PR_TARIF_RE = re.compile(r'gr-bnd-tarif">(.*?)</span>', re.S)
_PR_MONATE_RE = re.compile(r"Kosten über (\d+) Monate")
_PR_SCHNITT_RE = re.compile(r"Ø ([\d.]+,\d\d) €/Monat")
_PR_ALARM_RE = re.compile(r'<tr class="gr-a-zeile.*?</tr>', re.S)
_PR_KATALOG_RE = re.compile(r'<tr[^>]*data-modell="([^"]+)"(.*?)</tr>', re.S)


def _pr_betrag_cent(text: str) -> int:
    """„1.835,54 €" -> 183554. Eigene Zerlegung, keine Formatierhilfe."""
    roh = (text or "").replace("−", "-").replace("\xa0", " ")
    treffer = re.search(r"-?[\d.]+,\d\d", roh)
    assert treffer, f"kein Betrag in {text!r}"
    zahl = treffer.group(0).replace(".", "").replace(",", ".")
    return int((_gw_Dez(zahl) * 100).to_integral_value(rounding=_gw_HUP))


def _pr_abschnitte(gw_seite: dict) -> list[tuple]:
    """[(modell, quelle, html)] - je Modell der Block mit seinen Zeilen.

    Das Startgeraet steht inline in `geraete.html` (seine ID steht dort im
    JSON-Block als `vorgabe`), alle anderen Modelle in je einem
    `gr-bnd-lager`-Block des Nachladefragments. Der Block wird MIT seinem
    Modell gefuehrt und nicht hinterher ueber den Betrag gesucht: zwei
    Modelle koennen denselben Betrag tragen, und eine Suche nach dem
    ersten Treffer haengt die Zeile dann an das falsche Geraet (eigener
    Fehler, gemessen am 21.09.2026: congstar/Allnet Flat S landete mit
    1.615,00 EUR am Galaxy S26 Ultra)."""
    vorgabe = re.search(r'"vorgabe":\s*"([^"]+)"', gw_seite["geraete"])
    assert vorgabe, "kein `vorgabe`-Modell in geraete.html gefunden"
    stelle = gw_seite["geraete"].find('id="gr-bndliste"')
    assert stelle > 0, "keine Inline-Buendelliste in geraete.html"
    abschnitte = [(vorgabe.group(1), "geraete.html",
                   gw_seite["geraete"][stelle:])]
    for block in re.split(r'<div class="gr-bnd-lager" data-modell="',
                          gw_seite["buendel"])[1:]:
        abschnitte.append((block[:block.index('"')],
                           "data/geraete-buendel.html", block))
    assert len(abschnitte) >= 90, (
        f"nur {len(abschnitte)} Modellbloecke gelesen - der Parser greift "
        "ins Leere")
    return abschnitte


def _pr_buendelzeilen(gw_seite: dict) -> list[dict]:
    """Alle Buendelzeilen BEIDER Dokumente, je mit ihrem Modell."""
    zeilen = []
    for modell, quelle, text in _pr_abschnitte(gw_seite):
        for treffer in _PR_DETAIL_RE.finditer(text):
            block = treffer.group(1)
            attribute = dict(_PR_ATTR_RE.findall(block))
            etikett = _PR_LABEL_RE.search(block)
            rechenweg = _PR_RWZ_RE.search(block)
            name = _PR_NAME_RE.search(block)
            tarif = _PR_TARIF_RE.search(block)
            zeilen.append({
                "quelle": quelle,
                "modell": modell,
                "attribute": attribute,
                "etikett": (etikett.group(1) if etikett else ""),
                "rechenweg": re.sub(
                    r"\s+", " ",
                    re.sub("<[^>]+>", "", rechenweg.group(1))
                ).strip() if rechenweg else "",
                "anbieter": (name.group(1) if name else ""),
                "tarif": re.sub(r"\s+", " ",
                                re.sub("<[^>]+>", " ", tarif.group(1))
                                ).strip() if tarif else "",
            })
    assert len(zeilen) >= 300, (
        f"nur {len(zeilen)} Buendelzeilen gelesen - am 21.09.2026 waren es "
        "375; der Parser greift ins Leere")
    return zeilen


def test_pr_fuenf_leitzahlen_gegen_die_historie_nachgerechnet(gw_seite):
    """Fuenf Zahlen der Seite, EIGENE Rechnung aus der Historie.

    Definition (Auftrag): Anzahlung + 24 Monate Tarif + ALLE Geraeteraten
    einschliesslich der Restschuld nach Monat 24 + Anschlusspreis. Bei
    einem zusammengelegten Buendelmonatspreis (1&1) tritt dieser Betrag
    ueber seine eigene Laufzeit an die Stelle von Tarif UND Rate.

    Rundung offen benannt: jeder Monatsbetrag wird als ganze Cent gelesen
    und danach multipliziert (eine Rate von 30,50 EUR ist 3050 Cent), die
    Summe bleibt exakt - keine Gleitkommatoleranz.

    Nachgerechnet am 21.09.2026 (Pruefer), Seite == Soll:
      congstar / iPhone 17 Pro 256 / Allnet Flat XS   1.459,00 EUR
      o2       / iPhone 17 Pro 256 / Unlimited M Plus 1.794,76 EUR
      Vodafone / iPhone 17 Pro 256 / Mobil XS         1.955,80 EUR
      1&1      / iPhone 17 Pro 256 / All-Net-Flat S   2.019,54 EUR
      congstar / Galaxy S26 Ultra 256 / Allnet Flat S 1.399,00 EUR
    """
    historie = _pf_historie()
    faelle = (
        ("apple-iphone-17-pro-256", "congstar", "allnet-flat-xs", 145900),
        ("apple-iphone-17-pro-256", "o2",
         "o2-mobile-unlimited-m-plus-mit-100-mbit-s-24-mon", 179476),
        ("apple-iphone-17-pro-256", "vodafone", "mobil-xs", 195580),
        ("apple-iphone-17-pro-256", "1-1", "1-1-all-net-flat-s", 201954),
        ("samsung-galaxy-s26-ultra-256", "congstar", "allnet-flat-s", 139900),
    )
    zeilen = _pr_buendelzeilen(gw_seite)
    geprueft, fehler = 0, []
    for modell, slug, tarifteil, verankert in faelle:
        satz = _pf_letzte_messung(historie, modell, slug, tarifteil)
        soll = _pf_leitzahl_cent(satz)
        # Der Anker aus der Pruefung vom 21.09.2026: aendert ein Bot-Commit
        # die Posten, wird DIESER Assert rot - dann ist der neue Sollwert
        # nachzurechnen, nicht der Test zu loeschen.
        assert soll == verankert, (
            f"{slug}/{tarifteil} zu {modell}: eigene Rechnung "
            f"{soll / 100} EUR gegen verankerte {verankert / 100} EUR")
        treffer = [z for z in zeilen
                   if _pr_anbieter_slug(z["anbieter"]) == slug
                   and _pr_tarifteil(z["tarif"]) == tarifteil
                   and z["attribute"].get("zustand") == "neu"
                   and z["attribute"].get("gesamt")
                   and z["modell"] == modell]
        assert treffer, (
            f"keine Buendelzeile {slug}/{tarifteil} zu {modell} auf der "
            "Seite - der Lookup greift ins Leere und dieser Test wuerde "
            "sonst gruen nichts pruefen")
        for zeile in treffer:
            geprueft += 1
            ist = int((_gw_Dez(zeile["attribute"]["gesamt"]) * 100)
                      .to_integral_value(rounding=_gw_HUP))
            if ist != soll:
                fehler.append((modell, slug, tarifteil, ist, soll))
    assert geprueft >= len(faelle), (
        f"nur {geprueft} Zeilen geprueft - erwartet mindestens "
        f"{len(faelle)}")
    assert not fehler, f"Seite gegen eigene Rechnung: {fehler}"


def _pr_anbieter_slug(anbieter: str) -> str:
    """„1&1" -> `1-1`, „Vodafone" -> `vodafone` - wie das ID-Segment.

    Die Entities werden ZUERST aufgeloest: `1&amp;1` ergibt sonst
    `1-amp-1`, und der Vergleich zweier Tabellen faellt still ins Leere -
    genau der gruene Test, der nichts prueft."""
    roh = _pr_html.unescape(anbieter or "")
    return re.sub(r"[^a-z0-9]+", "-", roh.lower()).strip("-")


def _pr_tarifteil(tarif: str) -> str:
    """Der Tarifname der Zeile als ID-Segment (ohne „ · 15 GB")."""
    name = _pr_html.unescape(tarif or "").split("·")[0]
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def test_pr_kein_monatsschnitt_teilt_eine_36_monats_summe_durch_24(gw_seite):
    """BEFUND (hoch): Ø/Monat rechnet 36-Monats-Summe / 24 Monate.

    Seit P0-B-fix2 nennt das Etikett den Zeitraum der Zahl
    ("Kosten über 36 Monate"). Der Ø/Monat DERSELBEN Zeile teilt
    weiterhin durch 24 (`tco_model.Tco.monatlich`). Gerendert am
    21.09.2026, 1&1 / iPhone 17 Pro 256 GB:

        "Kosten über 36 Monate 2.019,54 € · Ø 84,15 €/Monat"

    84,15 x 36 = 3.029,40 EUR - die Zeile widerspricht sich selbst. Der
    Monatsbetrag des Angebots ist 44,99 EUR, die Summe ueber ihren
    eigenen Zeitraum ergibt 56,10 EUR je Monat. Betroffen sind 70 Zeilen
    (Seite plus Fragment).

    Geprueft wird die Identitaet, die auf JEDER Zeile gelten muss:
    gezeigter Ø x gezeigte Monate == gezeigte Leitzahl (eine Cent-
    Rundungsspanne je Monat erlaubt)."""
    zeilen = _pr_buendelzeilen(gw_seite)
    geprueft, fehler = 0, []
    for zeile in zeilen:
        monate = _PR_MONATE_RE.search(zeile["etikett"])
        schnitt = _PR_SCHNITT_RE.search(zeile["rechenweg"])
        if monate is None or schnitt is None:
            continue
        geprueft += 1
        n = int(monate.group(1))
        gezeigt = _pr_betrag_cent(schnitt.group(1))
        summe = _pr_betrag_cent(zeile["rechenweg"])
        if abs(gezeigt * n - summe) > n:
            fehler.append((zeile["anbieter"], zeile["tarif"], n,
                           summe / 100, gezeigt / 100,
                           round(summe / n / 100, 2)))
    assert geprueft >= 300, (
        f"nur {geprueft} Zeilen mit Etikett UND Ø gelesen - der Parser "
        "greift ins Leere")
    assert not fehler, (
        f"{len(fehler)} Zeilen, deren Ø/Monat nicht zu ihrem eigenen "
        f"Zeitraum passt (Anbieter, Tarif, Monate, Summe, Ø gezeigt, "
        f"Ø soll): {fehler[:4]}")


def test_pr_kein_vorzeichen_gegen_vodafone_ueber_zwei_zeitraeume(gw_seite):
    """BEFUND (kritisch): das Delta ist nur in der Buendelzeile entschaerft.

    P0-B-fix2 nimmt der Buendelzeile eines 1&1-Angebots das Euro- und
    Prozent-Delta ("andere Laufzeit", "Kein Abstand zur
    Vodafone-Referenz: diese Zahl trägt 36 Monate, die Referenz 24
    Monate"). Die Alarm-/Radarzeilen desselben Angebots auf derselben
    Seite tragen ihr Vorzeichen weiter (`report/geraete_radar.py:251`
    und `:282` rechnen `prozent` ohne Horizont-Tor), ebenso
    `exporte/wettbewerbsradar.csv` (Status `vergleichbar`, Preisart
    "Kosten über 24 Monate") - gemessen am 21.09.2026: 26 Alarmzeilen mit
    1&1-Prozentzahl, darunter iPhone 17 Pro 256 GB mit +3,3 % gegen eine
    Referenz von 1.955,80 EUR.

    Die 1&1-Zahlen tragen 36 Monate Tarif UND Geraet in EINEM Betrag;
    allein die zwoelf Tarifmonate jenseits des Horizonts (12 x 14,99 EUR
    nach `tarife.jsonl` = 179,88 EUR) sind groesser als jedes hier
    ausgewiesene Delta. Geprueft wird: kein Vorzeichen fuer ein Angebot,
    dessen Buendelzeile den Zeitraum 36 nennt."""
    zeilen = _pr_buendelzeilen(gw_seite)
    andere_laufzeit = {
        (_pr_anbieter_slug(z["anbieter"]), z["attribute"].get("gesamt"))
        for z in zeilen
        if (_PR_MONATE_RE.search(z["etikett"]) or [None, "24"])[1] != "24"}
    assert andere_laufzeit, (
        "keine Zeile mit abweichendem Zeitraum auf der Seite - der Test "
        "wuerde sonst gruen nichts pruefen")

    mit_vorzeichen = []
    for treffer in _PR_ALARM_RE.finditer(gw_seite["geraete"]):
        block = treffer.group(0)
        attribute = dict(re.findall(r'data-s-([a-z]+)="([^"]*)"', block))
        anbieter = _pr_anbieter_slug(
            (attribute.get("anbieter") or "").replace("&amp;", "&"))
        gesamt = attribute.get("gesamt")
        if not attribute.get("prozent"):
            continue
        if (anbieter, gesamt) in andere_laufzeit:
            mit_vorzeichen.append((attribute.get("geraet"), anbieter, gesamt,
                                   attribute.get("prozent")))
    assert not mit_vorzeichen, (
        f"{len(mit_vorzeichen)} Alarm-/Radarzeilen tragen ein Delta-"
        "Vorzeichen fuer eine Zahl, deren eigene Buendelzeile einen "
        f"anderen Zeitraum nennt: {mit_vorzeichen[:4]}")


def test_pr_eine_verschwundene_abweichung_traegt_ihren_grund(gw_seite):
    """BEFUND (hoch): 22 Abweichungen sind zum Strich geworden, ohne Grund.

    `report/geraete_view.py:1084` laesst die Luecke der Delta-Spalte
    ausdruecklich leer ("Strich wie die Buendelzeile - die Referenz
    existiert"). Seit P0-B-fix2 trifft das nicht mehr zu: die
    Buendelzeile zeigt dort "andere Laufzeit", die Katalogzeile den
    Strich, und der Strich heisst auf dieser Seite "kein Angebot" (A2).

    Gemessen am 21.09.2026 (gleicher Bestand, zwei Codestaende):
    `exporte/geraete-modell-tco.csv` verlor 22 von 57 Abweichungen
    (2aa7dbd -> ac80e83), und KEINE der 22 Zeilen traegt einen Grund in
    der Statusspalte - z. B. Apple iPhone 17 Pro Max 512 GB (Vodafone
    2.351,80 EUR): vorher "+341,74 € · +14,5 %", jetzt "–".

    Geprueft wird die Zusicherung des Exports selbst
    (`geraete_export.modell_tco_csv`): "Eine Zeile ohne Zahl ODER OHNE
    ABSTAND traegt den benannten Grund in der Statusspalte."""
    pfad = Path(gw_seite["csv"]).parent / "geraete-modell-tco.csv"
    assert pfad.exists(), f"{pfad} fehlt - der Export wurde nicht gerendert"
    zeilen = list(_gw_csv.DictReader(
        pfad.read_text(encoding="utf-8-sig").splitlines(), delimiter=";"))
    assert len(zeilen) >= 100, (
        f"nur {len(zeilen)} Modellzeilen im Export - der Lookup greift ins "
        "Leere")
    stumm = [(z["Hersteller"], z["Modell"], z["Speicher GB"],
              z["Bester Anbieter"], z["TCO ab EUR"])
             for z in zeilen
             if z["TCO ab EUR"].strip() and not z["Abweichung %"].strip()
             and not (z["Status"] or "").strip()]
    assert not stumm, (
        f"{len(stumm)} Modellzeilen mit Leitzahl, aber ohne Abweichung UND "
        f"ohne Grund in der Statusspalte: {stumm[:6]}")


# ==========================================================================
# PRUEFER P0-B (21.09.2026) - die zweite, unabhaengige Rechnung
# --------------------------------------------------------------------------
# Diese drei Tests stammen vom Pruefer, nicht vom Bauer. Sie importieren
# `telco_radar.tco_model` NICHT: die Leitzahl wird hier aus den Rohfeldern
# von `data/state/geraete_tco.json` mit `decimal` neu gerechnet, nach der
# Definition aus CLAUDE.md ("Kosten über 24 Monate = Anzahlung + 24 Monate
# Tarif + alle Geraeteraten inklusive Restschuld nach Monat 24 +
# Anschlusspreis"; bei einem zusammengelegten Monatsbetrag ueber die ganze
# eigene Laufzeit). Rundung: HALF_UP auf zwei Stellen, einmal am Ende -
# dieselbe Regel, die die Seite fuer Euro-Betraege verwendet.
# ==========================================================================

_PZ_TOLERANZ = _gw_Dez("0.01")     # ein Cent je Monat auf dem O/Monat

# Die Spalte, deren Kopf P0-B-z3 WISSENTLICH stehen gelassen hat: sie ist
# ein Fremdschluessel fuer `test_geraete_tco_csv_gegen_die_eigene_rechnung`
# und traegt ihre Summe fuer JEDE Zeile, auch fuer die, deren eigener
# Zeitraum 36 ist. Der Widerspruch ist damit sichtbar gemacht, nicht
# behoben - und wird hier als Zahl festgehalten, statt uebersehen zu
# werden (Befund vom 22.09.2026, siehe Docstring unten).
_PZ_CSV_ZEITRAUM = "Leitzahl-Zeitraum Monate"


def _pz_soll(b: dict) -> tuple:
    """(Leitzahl, Zeitraum) aus den ROHFELDERN - oder (None, None).

    Zwei Formen, genau wie die Anbieter sie ausweisen:
      * zusammengelegter Monatsbetrag (`buendel_monatlich`, 1&1): Tarif und
        Geraet in EINER Rate, der Zeitraum ist die eigene Laufzeit.
      * getrennt (`tarif_monatlich` + `geraet_monatsrate`): 24 Tarifmonate,
        dazu ALLE Geraeteraten der eigenen Laufzeit - der Zeitraum dieser
        Zahl ist 24.
    Ohne gemessene Laufzeit gibt es keine Summe und keinen Zeitraum (None,
    nie 0, nie geraten).
    """
    def dez(wert):
        return None if wert is None else _gw_Dez(str(wert))

    zu = dez(b.get("geraet_zuzahlung")) or _gw_Dez("0")
    anschluss = dez(b.get("anschlusspreis")) or _gw_Dez("0")
    laufzeit = b.get("laufzeit_monate")
    zusammen = dez(b.get("buendel_monatlich"))
    tarif = dez(b.get("tarif_monatlich"))
    rate = dez(b.get("geraet_monatsrate"))
    if zusammen is not None:
        if laufzeit is None:
            return None, None
        summe = zu + zusammen * laufzeit + anschluss
        return summe.quantize(_gw_Dez("0.01"), rounding=_gw_HUP), laufzeit
    if tarif is None:
        return None, None
    summe = zu + tarif * _GW_HORIZONT + anschluss
    if rate is not None:
        if laufzeit is None:
            return None, None
        summe = summe + rate * laufzeit
    return summe.quantize(_gw_Dez("0.01"), rounding=_gw_HUP), _GW_HORIZONT


def _pz_zeilen(html: str) -> list[dict]:
    """Die Buendelzeilen eines Dokuments - Attribute und Etikett je Zeile."""
    zeilen = []
    for block in html.split('<details class="gr-bnd')[1:]:
        kopf = block[:block.find("</summary>")]

        def feld(muster, quelle=kopf):
            treffer = re.search(muster, quelle, re.S)
            return treffer.group(1) if treffer else None

        zeilen.append({
            "anbieter": (feld(r'gr-bnd-name">([^<]*)<') or "")
            .replace("&amp;", "&").strip(),
            "gesamt": feld(r'data-gesamt="([^"]*)"'),
            "schnitt": feld(r'data-schnitt="([^"]*)"'),
            "laufzeit_attr": feld(r'data-laufzeit="([^"]*)"'),
            "etikett": feld(r"Kosten über (\d+) Monate"),
        })
    return zeilen


def test_pruefer_jede_leitzahl_der_seite_gegen_eine_eigene_rechnung(gw_seite):
    """Leitzahl, Zeitraum und O/Monat JEDER Buendelzeile, neu gerechnet.

    Gegenprobe gegen einen Test, dessen Lookup ins Leere laeuft: jede
    gerenderte Zeile MUSS im unabhaengig gerechneten Bestand einen
    Betragspartner finden (`ohne_partner` ist ein Fehlschlag, kein
    Ueberspringen), es muessen mehr als 400 Zeilen geprueft werden, und
    beide Zeitraeume des Bestands (24 UND 36) muessen vorkommen - sonst
    prueft der Test die interessante Haelfte nicht.
    """
    stand = json.loads((_GW_WURZEL / "data" / "state" / "geraete_tco.json")
                       .read_text(encoding="utf-8"))
    # (Anbieter, Leitzahl) -> die Zeitraeume, die diese Summe tragen kann.
    soll: dict[tuple, set] = {}
    for b in stand["buendel"]:
        betrag, monate = _pz_soll(b)
        if betrag is None:
            continue
        soll.setdefault((b["anbieter"], betrag), set()).add(monate)
    assert len(soll) > 200, \
        f"nur {len(soll)} eigene Leitzahlen gerechnet - Rohdaten leer?"

    zeilen = (_pz_zeilen(gw_seite["buendel"])
              + _pz_zeilen(gw_seite["geraete"]))
    geprueft = 0
    zeitraeume: set = set()
    ohne_partner, falsches_etikett, falscher_schnitt = [], [], []
    for z in zeilen:
        if not z["gesamt"] or not z["etikett"]:
            continue
        betrag = _gw_Dez(z["gesamt"]).quantize(_gw_Dez("0.01"))
        moeglich = soll.get((z["anbieter"], betrag))
        if not moeglich:
            ohne_partner.append((z["anbieter"], z["gesamt"]))
            continue
        geprueft += 1
        monate = int(z["etikett"])
        zeitraeume.add(monate)
        if monate not in moeglich:
            falsches_etikett.append((z["anbieter"], str(betrag), monate,
                                     sorted(moeglich)))
        schnitt = _gw_Dez(z["schnitt"] or "0")
        if abs(schnitt * monate - betrag) > _PZ_TOLERANZ * monate:
            falscher_schnitt.append((z["anbieter"], str(betrag), monate,
                                     z["schnitt"]))
    assert not ohne_partner, (
        f"{len(ohne_partner)} Buendelzeilen mit einer Summe, die die eigene "
        f"Rechnung nicht kennt: {ohne_partner[:6]}")
    assert geprueft > 400, \
        f"nur {geprueft} Zeilen geprueft - der Lookup greift nicht"
    assert {24, 36} <= zeitraeume, \
        f"nur die Zeitraeume {sorted(zeitraeume)} geprueft, nicht 24 UND 36"
    assert not falsches_etikett, (
        "Etikett nennt einen Zeitraum, den die Summe nicht tragen kann: "
        f"{falsches_etikett[:6]}")
    assert not falscher_schnitt, (
        "O/Monat x Etikett-Zeitraum != Leitzahl: "
        f"{falscher_schnitt[:6]}")


def test_pruefer_kein_spaltenkopf_behauptet_24_ueber_einer_36_monats_zahl(
        gw_seite):
    """Der Spaltenkopf IST eine Aussage ueber jede Zahl unter ihm.

    Geprueft wird die Buendeltafel des Startmodells: nennt der Kopf der
    TCO-Spalte eine Monatszahl, dann muss JEDE Zeile unter ihm genau
    diesen Zeitraum tragen. Der Sortierknopf dieses Kopfes
    (`data-bsort="tco"`, app.js liest `data-gesamt`) stellt alle Summen
    der Spalte in EINEN Rang - ein Kopf, der einen Zeitraum behauptet,
    behauptet ihn damit fuer den ganzen Rang.

    GEMESSEN am 22.09.2026 (echter Render gegen den Bestand vom
    20.09.2026): 19 Buendelzeilen inline, alle 19 mit `data-gesamt` UND
    eigenem Etikett, 18 ueber 24 Monate und 1 ueber 36 (die 1&1-Zeile mit
    `buendel_monatlich`). Der Kopf lautet "nach den Kosten mit Tarif
    sortieren, getrennt nach Zeitraum" und nennt KEINE Monatszahl - das
    ist der Stand nach P0-B-z2 und der gewollte Zustand: der Kopf nennt
    die Spalte, die Zeile ihren Zeitraum.

    WARUM DIE PRUEFUNG SO GEBAUT IST (Befund vom 22.09.2026): vorher
    stand hier `assert not (fremde and behauptet == [_GW_HORIZONT])`.
    Nach z2 ist `behauptet` leer, also ist `behauptet == [24]` fuer immer
    falsch und der Assert konnte nicht mehr fallen - egal was in der
    Spalte steht. Er war ausserdem nur auf die eine Richtung gefasst:
    ein Kopf, der "36 Monate" ueber 24-Monats-Zeilen behauptet, kam
    durch. Geprueft wird jetzt die Aussage selbst, in beide Richtungen,
    mit zwei Gegenproben, die verhindern, dass sie gruen ins Leere
    laeuft: die Spalte muss Zeilen MIT Etikett haben, und sie muss
    MEHRERE Zeitraeume tragen (sonst koennte eine Monatszahl im Kopf
    ueberhaupt nicht widersprechen und der Test prueft nichts).
    """
    seite = gw_seite["geraete"]
    koepfe = re.findall(r'data-bsort="tco"[^>]*aria-label=\s*"([^"]*)"',
                        seite)
    assert koepfe, "Sortierkopf der TCO-Spalte nicht gefunden - Lookup leer"

    spaltenzeilen = [z for z in _pz_zeilen(seite) if z["gesamt"]]
    assert spaltenzeilen, (
        "keine Buendelzeile mit data-gesamt in der Startansicht - der "
        "Lookup greift ins Leere und dieser Test wuerde sonst gruen "
        "nichts pruefen")
    # Die Haelfte von z2, die traegt: JEDE Zahl nennt ihren eigenen
    # Zeitraum. Ohne Etikett waere der Kopf die einzige Angabe, und der
    # Widerspruch unten waere gar nicht messbar.
    ohne_etikett = [(z["anbieter"], z["gesamt"]) for z in spaltenzeilen
                    if not z["etikett"]]
    assert not ohne_etikett, (
        f"{len(ohne_etikett)} von {len(spaltenzeilen)} Zeilen tragen eine "
        f"Summe ohne eigenen Zeitraum: {ohne_etikett[:6]} - am 22.09.2026 "
        "trugen alle 19 ihr Etikett. Ohne Etikett gilt wieder der Kopf "
        "fuer alle")

    etiketten = {int(z["etikett"]) for z in spaltenzeilen}
    # Gegenprobe: bei nur EINEM Zeitraum in der Spalte koennte kein Kopf
    # widersprechen - der Assert unten waere dann gruen ohne Aussage.
    assert len(etiketten) > 1, (
        f"die Spalte traegt nur den Zeitraum {sorted(etiketten)}; am "
        "22.09.2026 standen dort 24 UND 36 Monate (18 zu 1). Mit einem "
        "einzigen Zeitraum kann ein Spaltenkopf nicht widersprechen und "
        "dieser Test prueft nichts - die Startansicht ist neu zu waehlen "
        "oder der Anker neu zu setzen, nicht der Assert aufzuweichen")

    behauptet = {int(m) for kopf in koepfe
                 for m in re.findall(r"(\d+) Monate", kopf)}
    # Ein Kopf ohne Monatszahl behauptet nichts und kann nicht
    # widersprechen (Stand nach z2). Nennt er eine, muss sie der Zeitraum
    # JEDER Zeile darunter sein.
    widerspruch = sorted(etiketten - behauptet) if behauptet else []
    assert not widerspruch, (
        f"Spaltenkopf {koepfe[0]!r} behauptet {sorted(behauptet)} Monate, "
        f"in derselben Spalte stehen Zeilen mit {widerspruch} Monaten - "
        "und derselbe Knopf sortiert sie gemeinsam nach data-gesamt. Der "
        "Zeitraum gehoert an die Zeile, nicht an den Kopf")


def test_pruefer_der_csv_kopf_widerspricht_nicht_seiner_zeitraum_spalte(
        gw_seite):
    """`geraete-tco.csv`: Kopf und Zeitraum-Spalte derselben Zeile.

    P0-B-h4 hat die Spalte "Leitzahl-Zeitraum Monate" ergaenzt, den Kopf
    der Wertspalte aber stehen gelassen. Eine Zeile, deren Zeitraum 36
    sagt, traegt ihre Summe damit unter "Kosten über 24 Monate EUR" -
    zwei Zahlen zum selben Zeitraum in derselben Zeile.

    GEPRUEFT WERDEN ALLE "Kosten über"-Spalten, nicht eine.

    Befund vom 22.09.2026: vorher nahm dieser Test
    `next(k for k in zeilen[0] if k.startswith("Kosten über"))` - also die
    ERSTE solche Spalte in Spaltenreihenfolge. Seit z3 gibt es ZWEI:
      * "Kosten über 24 Monate EUR (eigener Zeitraum)" - gefuellt nur
        dort, wo der eigene Zeitraum wirklich 24 ist (763 von 837),
        sonst eine benannte Luecke (74). Diese Spalte ist stimmig.
      * "Kosten über 24 Monate EUR" - fuer JEDE der 837 Zeilen gefuellt,
        auch fuer die 74 mit eigenem Zeitraum 36. z3 hat sie wortgleich
        stehen gelassen, weil `test_geraete_tco_csv_gegen_die_eigene_
        rechnung` sie als Fremdschluessel liest.
    Weil die neue Spalte in der Reihenfolge davor stand, pruefte `next()`
    ab z3 nur noch die stimmige und meldete 0 Widersprueche - waehrend
    dieselbe Datei 74 trug. Ein Lookup, der an der Spaltenreihenfolge
    haengt und am Fehler vorbeigreift, ist kein Nachweis; deshalb pruefen
    wir jetzt JEDE solche Spalte.

    SEIT DEM 22.09.2026 (Lead) gibt es die widersprechende Spalte nicht
    mehr. Der Export legt jede Summe in den Kopf, der fuer sie WAHR ist:
    "Kosten über 24 Monate EUR" nur bei Zeitraum 24 (763 von 837),
    "Kosten über die Bündellaufzeit EUR" bei jedem anderen (74), daneben
    "Leitzahl-Zeitraum Monate". Der Sonderzweig, der den bekannten
    Widerspruch als exakte Gleichheit festhielt, ist damit entfallen -
    genau so, wie er es selbst vorgesehen hatte.

    ZWEI RICHTUNGEN, weil eine allein billig zu erfuellen waere:
      * Kein Kopf, der eine Monatszahl nennt, traegt eine Zahl mit
        anderem Zeitraum.
      * Keine Zeile verliert dabei ihren Wert, und keine traegt ihn unter
        zwei Koepfen. Ohne das waere der erste Punkt auch mit einem
        Export gruen, der die 74 Zahlen einfach weglaesst.

    WAS ZU TUN IST, WENN DIESER TEST FAELLT: Es ist ein Fehler im Export,
    kein Anker, der nachgezogen werden muss. Die Meldung nennt Anbieter
    und Zeitraum der betroffenen Zeilen.
    """
    zeilen = list(_gw_csv.DictReader(
        gw_seite["csv"].read_text(encoding="utf-8-sig").splitlines(),
        delimiter=";"))
    assert zeilen, "geraete-tco.csv ist leer - Lookup greift nicht"
    spalten = [k for k in zeilen[0] if k.startswith("Kosten über")]
    assert spalten, (
        f"keine 'Kosten über'-Spalte in {sorted(zeilen[0])} - der Lookup "
        "greift ins Leere und dieser Test wuerde sonst gruen nichts "
        "pruefen")
    assert _PZ_CSV_ZEITRAUM in zeilen[0], (
        f"Spalte {_PZ_CSV_ZEITRAUM!r} fehlt - ohne den Zeitraum JE ZEILE "
        "ist kein Widerspruch zum Kopf messbar")

    # Gegenprobe: ohne Zeile mit fremdem Zeitraum kann kein Kopf
    # widersprechen, und alles darunter waere gruen ohne Aussage.
    fremde_zeilen = [z for z in zeilen
                     if (z[_PZ_CSV_ZEITRAUM] or "").strip()
                     and int(z[_PZ_CSV_ZEITRAUM]) != _GW_HORIZONT]
    assert fremde_zeilen, (
        f"keine der {len(zeilen)} Zeilen traegt einen Zeitraum ungleich "
        f"{_GW_HORIZONT}; am 22.09.2026 waren es 74 von 837 (1&1, "
        "Buendelbetrag ueber 36 Monate). Ohne sie prueft dieser Test "
        "nichts - Anker mit Begruendung neu setzen, nicht aufweichen")

    # Ein Kopf, der eine MONATSZAHL nennt, behauptet einen Zeitraum und
    # kann ihm widersprechen. Ein Kopf, der keine nennt ("Kosten über die
    # Bündellaufzeit EUR"), behauptet keinen festen Zeitraum - bei ihm
    # steht der Zeitraum in der Zeile, und es gibt nichts zu widerlegen.
    # Diese Unterscheidung ist die Loesung des Befunds, nicht seine
    # Umgehung: dass jede Zeile IHREN Wert behaelt, prueft die
    # Gegenrichtung unten.
    mit_zahl_im_kopf = [k for k in spalten if re.search(r"\d", k)]
    assert mit_zahl_im_kopf, (
        f"keine 'Kosten über'-Spalte nennt eine Monatszahl ({spalten}) - "
        "dann prueft die Schleife nichts; Anker mit Begruendung neu setzen")
    for kopf in mit_zahl_im_kopf:
        kopf_monate = int(re.search(r"(\d+)", kopf).group(1))
        fremd = [(z["Anbieter"], z[_PZ_CSV_ZEITRAUM], z[kopf])
                 for z in zeilen
                 if (z[_PZ_CSV_ZEITRAUM] or "").strip()
                 and int(z[_PZ_CSV_ZEITRAUM]) != kopf_monate
                 and (z[kopf] or "").strip()]
        assert not fremd, (
            f"{len(fremd)} Zeilen tragen ihre Summe unter dem Kopf "
            f"{kopf!r}, obwohl ihre eigene Zeitraum-Spalte einen anderen "
            f"Wert nennt: {fremd[:4]}")

    # Die andere Haelfte: kein Kopf luegen zu lassen ist billig, wenn man
    # die Zahl einfach weglaesst. Jede Zeile mit einem gemessenen Zeitraum
    # traegt ihre Summe in GENAU EINER der Spalten - nie in keiner.
    stumm = [(z["Anbieter"], z[_PZ_CSV_ZEITRAUM]) for z in zeilen
             if (z[_PZ_CSV_ZEITRAUM] or "").strip()
             and not any((z[k] or "").strip() for k in spalten)]
    assert not stumm, (
        f"{len(stumm)} Zeilen tragen einen Zeitraum, aber in keiner "
        f"'Kosten über'-Spalte eine Zahl: {stumm[:4]}")
    doppelt = [(z["Anbieter"], z[_PZ_CSV_ZEITRAUM]) for z in zeilen
               if sum(1 for k in spalten if (z[k] or "").strip()) > 1]
    assert not doppelt, (
        f"{len(doppelt)} Zeilen tragen dieselbe Summe unter zwei Koepfen "
        f"mit verschiedenem Zeitraum: {doppelt[:4]}")


def test_der_name_der_grafik_nennt_die_zeitraeume_die_darin_liegen(gw_seite):
    """Der zugaengliche Name der Grafik-Sektion gegen ihre Kurven.

    P0-B (22.09.2026): `_geraete_zeitreihe.html.j2` trug den Namen FEST -
    "Kosten über 24 Monate je Messtag und Anbieter" -, auch wenn im Bild
    eine 36-Monats-Kurve lag. Paket z1 hatte das aria-label IM SVG
    dynamisch gemacht und die Sektion darueber nicht gesehen: wer die
    Seite sieht, las am Kurvenende "36 Mon.", wer sie hoert, bekam "Kosten
    über 24 Monate" - dieselbe Grafik, zwei Aussagen (Clean Code 7).

    Geprueft wird die Uebereinstimmung, nicht eine Zahl: welche Zeitraeume
    das Bild traegt, sagen seine Kurvenetiketten (`gr-zr-mon`); der Name
    der Sektion muss genau diese nennen. Der Test driftet damit nicht mit
    dem Bestand - er faellt, wenn Name und Bild auseinanderlaufen.

    Gegenprobe eingebaut: das Bild MUSS mindestens zwei verschiedene
    Zeitraeume tragen, sonst prueft der Test nur den einfachen Fall. Am
    22.09.2026 traegt die Startansicht (Apple iPhone 17 Pro 256 GB, Band
    Klein) vier Kurven - congstar, Telekom, Vodafone mit 24 Monaten und
    1&1 mit 36.
    """
    seite = gw_seite["geraete"]
    name = re.search(r'gr-zr-graph"\s+aria-label="([^"]*)"', seite, re.S)
    assert name, "keine Grafik-Sektion mit zugaenglichem Namen gefunden"
    genannt = {int(z) for z in re.findall(r"\d+", name.group(1))}

    im_bild = {int(z) for z in re.findall(r">(\d+) Mon\.?<", seite)}
    assert len(im_bild) >= 2, (
        f"die Startansicht traegt nur die Zeitraeume {im_bild} - dann "
        "prueft dieser Test nur den einfachen Fall. Am 22.09.2026 waren "
        "es 24 und 36 (1&1 mit Buendelbetrag ueber 36 Monate). Anker mit "
        "Begruendung neu setzen, nicht aufweichen")

    assert genannt == im_bild, (
        f"der Name der Grafik nennt {sorted(genannt)} Monate, die Kurven "
        f"darin tragen {sorted(im_bild)}: "
        f"{' '.join(name.group(1).split())!r}")
