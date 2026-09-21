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
# 256 GB - 1 + 24 x 15,00 + 36 x 30,50 + 0 = 1.459,00 EUR.
_GW_PFLICHT_SKU = "apple-iphone-17-pro-256gb"
_GW_PFLICHT_ANBIETER = "congstar"
_GW_PFLICHT_TARIF = "Allnet Flat XS"


def _gw_pflichtbuendel(tco: dict, blaetter: dict) -> tuple:
    """(soll_cent, ein Bündel, {Abruftage}) - alle Farben rechnen gleich."""
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
    tage = {b.get("abgerufen_am", "") for b in kandidaten}
    return werte.pop(), kandidaten[0], tage


def test_leitzahl_congstar_xs_iphone17pro256_am_bestand(gw_seite):
    """Der Pflichtfall, in allen Lagen, in denen die Seite ihn trägt:
    Antwort-Satz und Rechenweg im (Modell, Band)-Paar des Fragments -
    das Fragment gehört zum selben Render und trägt ALLE Paare - und,
    wenn der Server-First-Paint gerade mit diesem Paar startet, auch
    dessen Antwort-Satz und Bündelzeile."""
    tco, blaetter, _db = _gw_rohdaten()
    soll_cent, buendel, _tage = _gw_pflichtbuendel(tco, blaetter)

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
    # Tarif-Posten: 24 Monate, zum gemessenen Tarifpreis
    assert posten["Tarif"][1] == 24 and \
        posten["Tarif"][2] == _gw_Dez(str(buendel["tarif_monatlich"]))
    assert posten["Geräterate"][1] == buendel["laufzeit_monate"] and \
        posten["Geräterate"][2] == _gw_Dez(str(buendel["geraet_monatsrate"]))

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
    1.093,00 €-Leitzahl war genau um die Restschuld zu niedrig)."""
    tco, blaetter, _db = _gw_rohdaten()
    soll_cent, buendel, _tage = _gw_pflichtbuendel(tco, blaetter)
    rest_c = _gw_cent(buendel["geraet_monatsrate"]) * max(
        0, buendel["laufzeit_monate"] - _GW_HORIZONT)
    gezahlt_c = soll_cent - rest_c
    assert (soll_cent, rest_c, gezahlt_c) == (145900, 36600, 109300)

    block = _gw_paar_block(gw_seite["fragment"],
                           "apple-iphone-17-pro-256", "klein")
    _messtag, inhalt = _gw_neueste_vorlage(block, _GW_PFLICHT_ANBIETER)
    offen = re.search(
        r"davon nach Monat 24 noch zu zahlen: (\d+) × ([\d.,]+) € "
        r"= ([\d.,]+) €", inhalt)
    assert offen, "Rechenweg nennt die Restschuld nicht"
    assert int(offen.group(1)) == buendel["laufzeit_monate"] - 24
    assert _gw_dezimal(offen.group(2)) \
        == _gw_Dez(str(buendel["geraet_monatsrate"]))
    _gw_vergleiche(_gw_dezimal(offen.group(3)), rest_c,
                   "Restschuld im Rechenweg des Pflichtfalls")

    # First Paint (Karte): der Startblock - mit Zaehler, damit ein
    # anderes Startpaar die Ausweisungs-Prüfung nicht still überspringt.
    # Fragment-Gegenstück: der offen-Satz im Rechenweg OBEN - der ist
    # paarungebunden geprüft und fällt nicht mit dem Startfall um.
    titel = re.search(r'class="gr-bnd-titel"[^>]*>([^<]+)<',
                      gw_seite["geraete"])
    fp_geprueft = 0
    if titel and "Apple iPhone 17 Pro 256 GB" in titel.group(1):
        fp_geprueft += 1
        zeile = re.search(
            r'<details class="gr-bnd"[^>]*data-anbieter="congstar"'
            r'[^>]*data-band="klein"[^>]*>(.*?)</details>',
            gw_seite["geraete"], re.S)
        text = " ".join(re.sub(r"<[^>]+>", " ", zeile.group(1)).split())
        m = re.search(r"nach 24 Monaten gezahlt: ([\d.,]+) € · "
                      r"danach noch offen: ([\d.,]+) € \((\d+) Geräteraten\)",
                      text)
        assert m, f"Bündelkarte ohne Ausweisung: {text[:160]!r}"
        _gw_vergleiche(_gw_dezimal(m.group(1)), gezahlt_c,
                       "'nach 24 Monaten gezahlt'")
        _gw_vergleiche(_gw_dezimal(m.group(2)), rest_c,
                       "'danach noch offen'")
        assert int(m.group(3)) == buendel["laufzeit_monate"] - 24
        # Die gekappte Zahl darf nicht mehr als Leitzahl herhalten: ihr
        # Label muss das Kappen benennen (A1-Regel).
        assert "nach 24 Monaten gezahlt" in text
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
        ist = _n(r["Kosten über 24 Monate EUR"])
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
        _gw_vergleiche(_n(zeile["Kosten über 24 Monate EUR"]),
                       _soll, "Pflichtfall im CSV-Export")

    # Store-Abgleich: jedes heute gemessene Bündel steht mit seinen Posten
    # im Export und rechnet dort auf dieselbe Zahl.
    stand_zeilen = {(r["Anbieter"], r["Tarif"], r["Modell"], r["Speicher GB"],
                     r["Laufzeit Monate"], r["Zustand"],
                     r["Zuzahlung EUR"], r["Tarif/Monat EUR"],
                     r["Geräterate EUR"], r["Bündel/Monat EUR"],
                     r["Anschlusspreis EUR"],
                     r["Kosten über 24 Monate EUR"]): r for r in zeilen}
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
            r["Kosten über 24 Monate EUR"])
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


def test_pf_beide_ratenlaufzeiten_eines_tarifs_stehen_auf_der_seite(gw_seite):
    """P0-B, die eigentliche Frage: ueberschreiben sich Laufzeitvarianten?

    B1 verspricht "die Zahlweisen eines Tarifs sind jetzt zwei Buendel und
    ueberschreiben sich nicht mehr gegenseitig", B2a verspricht
    "Telekom/congstar/Vodafone erfassen ALLE angebotenen Ratenlaufzeiten"
    (Telekom 6/12/24/36, o2 24/36, congstar 24/36, Vodafone 12/24/36).

    Geprueft wird beides am ECHTEN Bestand:
      1. Traegt irgendein (Anbieter, Modell, Tarif, Zustand) zwei
         Ratenlaufzeiten? Traegt keiner eine, ist die Erfassung tot und
         nur der Schluessel neu - das ist der Befund, nicht der Beweis.
      2. Wo es zwei gibt, muessen BEIDE auf der Seite stehen.

    Gegenprobe (Pruefer, 21.09.2026): mit einem zusaetzlich in eine
    Wegwerf-Kopie des Bestands gelegten congstar-Buendel (Allnet Flat S
    zum Galaxy S26 Ultra 256 GB, 918,00 EUR in 24 Raten a 38,25 EUR neben
    den gemessenen 36 Raten a 25,50 EUR) rendert die Seite WEITERHIN 13
    Buendelzeilen fuer dieses Modell - die 36-Monats-Variante samt ihrer
    Zeile "danach noch offen: 306,00 EUR" verschwindet vollstaendig.
    Ursache: report/geraete_tco_karten.py:1327 entdoppelt je
    (Anbieter, Tarif, karte["laufzeit"], Zustand), und
    `karte["laufzeit"]` ist die KONSTANTE LAUFZEIT = TCO_HORIZONT = 24
    (geraete_tco_karten.py:646/68), nicht die gemessene Ratenlaufzeit."""
    tco, _blaetter, _db = _gw_rohdaten()
    heute = _gw_heute(tco)
    gruppen: dict = {}
    for b in tco["buendel"]:
        if not _gw_frisch(b, heute):
            continue
        schluessel = (b["anbieter"], _pf_modell(b["sku_id"]),
                      b["tarif_name"], b.get("zustand") or "")
        gruppen.setdefault(schluessel, set()).add(b.get("laufzeit_monate"))
    mehrfach = {k: v for k, v in gruppen.items() if len(v) > 1}

    assert mehrfach, (
        "KEIN einziger frischer (Anbieter, Modell, Tarif, Zustand) traegt "
        "zwei Ratenlaufzeiten - bei "
        f"{len(gruppen)} Gruppen im Bestand vom {heute}. Das Ziel nennt "
        "Telekom 6/12/24/36, o2 24/36, congstar 24/36, Vodafone 12/24/36; "
        "der Bestand kennt je Anbieter genau eine Laufzeit (CLAUDE.md "
        "Fallstrick 16: ein bei allen gleicher Wert ist zuerst der "
        "Verdacht auf eine Erfassungsluecke). Der Buendelschluessel traegt "
        "die Laufzeit seit B1 - erhoben wird sie nicht.")

    seite = _pf_seitenzeilen(gw_seite["buendel"], gw_seite["geraete"])
    fehlend = []
    for (anbieter, modell, tarif, zustand), laufzeiten in mehrfach.items():
        gezeigt = {z["laufzeit_raten"] for z in seite.get(modell, [])
                   if z["anbieter"] == anbieter and z["tarif"] == tarif
                   and z["zustand"] == zustand}
        if not laufzeiten <= gezeigt:
            fehlend.append((anbieter, modell, tarif, sorted(laufzeiten),
                            sorted(x for x in gezeigt if x is not None)))
    assert not fehlend, (
        f"{len(fehlend)} Tarife zeigen nicht alle gemessenen "
        f"Ratenlaufzeiten: {fehlend[:5]}")


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
