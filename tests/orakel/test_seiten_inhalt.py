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


def highlight(
    i: int, relevance: int, category: str = "Netz/Technologie", image_w: int = 0
) -> dict:
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
        h |= {
            "image": f"bild{i}.jpg",
            "image_w": image_w,
            "image_h": round(image_w * 9 / 16),
        }
    return h


# 12 relevante Meldungen, davon 8 mit relevance >= 4: mehr als der Deckel von
# sechs, den html.py auf die Signalliste legt - sonst wuerde der Test die
# Kappung gar nicht sehen.
HIGHLIGHTS = (
    [highlight(i, 5) for i in range(4)]
    + [highlight(i, 4) for i in range(4, 8)]
    + [highlight(i, 3) for i in range(8, 12)]
)
NEU_GESAMMELT = 426

# Eine Ausgabe in der Groessenordnung einer echten (193 Meldungen am
# 06.08.2026): genug Meldungen fuer alle vier Gewichtsstufen der Titelseite
# UND fuer Ressortbloecke danach. Mit den zwoelf oben ist die Titelseite
# schon vor den Ressorts leergeraeumt - dann pruefte kein Test das Raster.
KATEGORIEN = [
    "Netz/Technologie",
    "Tarif/Pricing",
    "Regulierung",
    "M&A",
    "Partnerschaft",
    "Sonstiges",
    "Finanzen",
    "Produktlaunch",
]
PORTAL = [
    highlight(
        100 + i,
        5 - (i % 3),
        KATEGORIEN[i % len(KATEGORIEN)],
        # jede zweite Meldung mit Bild, davon jede vierte zu klein
        # fuer eine grosse Position - genau die Mischung, in der sich
        # die Auswahl bewaehren muss
        image_w=(0 if i % 2 else (520 if i % 4 == 2 else 1200)),
    )
    for i in range(48)
]


BRIEFING = "## Auf einen Blick\n\nText.\n\n## Europa\n\nMehr Text."


def render(
    tmp_path,
    *,
    competitors=None,
    stats=None,
    highlights=None,
    bilder_anlegen=True,
    briefing=None,
    kosten=None,
):
    from telco_radar.report.bilder import bildordner

    # data/reports/ wie im echten Projekt: render_site() leitet den
    # Bildordner ueber `reports_dir.parent.parent` her. Lag der Bericht flach
    # unter tmp_path, zeigte das auf das GEMEINSAME pytest-Wurzelverzeichnis -
    # und ein Test sah die Bilddateien eines anderen.
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True)
    hs = HIGHLIGHTS if highlights is None else highlights
    run = {
        "duration_seconds": 1487.8,
        "models": {"analyst": "m", "editor": "m"},
        "phases": [],
        "analysts": [
            {"region": "Europa", "items_in": 15, "highlights": 4, "model": "m"}
        ],
        "sources": [],
        "source_summary": {"ok": 1, "empty": 0, "failed": 0},
    }
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
    (reports / "2026-08-05.json").write_text(
        json.dumps(
            {
                "date": "2026-08-05",
                "generated_with_llm": True,
                "stats": stats if stats is not None else {"new": NEU_GESAMMELT},
                "briefing_md": BRIEFING if briefing is None else briefing,
                "regions": {"Europa": {"region_summary": "", "highlights": hs}},
                "competitors": competitors if competitors is not None else [],
                "run": run,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
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


def lies_seite(site, name: str) -> str:
    return (site / name).read_text(encoding="utf-8")


# --------------------------------------------------------------- Protokoll
def test_protokoll_trennt_gesammelt_von_bewertet(tmp_path):
    """Die beiden Zahlen duerfen nicht unter EIN Label fallen."""
    html = lies_seite(render(tmp_path), "transparenz.html")

    assert f"<b>{NEU_GESAMMELT}</b><span>neue Meldungen gelesen</span>" in html
    assert f"<b>{len(HIGHLIGHTS)}</b><span>davon relevant</span>" in html
    # Der alte, falsche Text darf nicht zurueckkommen.
    assert f"<b>{NEU_GESAMMELT}</b><span>neue Meldungen bewertet</span>" not in html


def test_protokoll_erklaert_den_abstand_zwischen_den_zahlen(tmp_path):
    html = lies_seite(render(tmp_path), "transparenz.html")
    assert "gekappt wird nichts" in html


def test_protokoll_erklaert_nichts_wenn_es_nichts_zu_erklaeren_gibt(tmp_path):
    """Gegenprobe: sind beide Zahlen gleich, faellt der Hinweis weg."""
    html = lies_seite(
        render(tmp_path, stats={"new": len(HIGHLIGHTS)}), "transparenz.html"
    )
    assert "gekappt wird nichts" not in html


# ------------------------------------------------------------------ Kosten
# Antonio zahlt die API privat. Bis zum 27.08.2026 stand nirgends, was ein
# Lauf verbraucht - der Lauf vom 27.08. kostete 1,95 $, und es war hinterher
# nicht zu sagen, an welcher Stufe.
KOSTEN = {
    "modelle": {
        "deepseek-v4-flash": {
            "aufrufe": 66,
            "prompt_tokens": 1_200_000,
            "completion_tokens": 300_000,
            "usd": 0.252,
        },
        "unbekanntes-modell": {
            "aufrufe": 3,
            "prompt_tokens": 900,
            "completion_tokens": 400,
            "usd": None,
        },
    },
    "summe_usd": 0.252,
    "ohne_preis": ["unbekanntes-modell"],
    "budget_usd": 1.5,
    "budget_ueberschritten": False,
}


def test_transparenz_nennt_kosten_und_token_je_modell(tmp_path):
    html = lies_seite(render(tmp_path, kosten=KOSTEN), "transparenz.html")

    assert "deepseek-v4-flash" in html
    assert "66" in html
    assert "1.200.000" in html and "300.000" in html
    assert "0.25 $" in html
    assert "1.50 $" in html  # die Erwartung je Lauf


def test_transparenz_beziffert_ein_modell_ohne_preis_nicht(tmp_path):
    """Geraten wird nichts - die Luecke wird benannt."""
    html = lies_seite(render(tmp_path, kosten=KOSTEN), "transparenz.html")
    assert "nicht beziffert" in html
    assert "unbekanntes-modell" in html


def test_transparenz_sagt_wenn_der_lauf_teurer_war_als_erwartet(tmp_path):
    """Und im selben Atemzug, dass deshalb nichts gekuerzt wurde - der
    Zaehler warnt, er greift nicht ein (Antonio, 27.08.2026)."""
    teuer = {**KOSTEN, "summe_usd": 1.93, "budget_ueberschritten": True}
    html = lies_seite(render(tmp_path, kosten=teuer), "transparenz.html")
    assert "Dieser Lauf lag darüber" in html
    assert "Gekürzt wurde deswegen nichts" in html


def test_ein_lauf_im_rahmen_meldet_keine_ueberschreitung(tmp_path):
    """Gegenprobe zum Test darueber - sonst prueft er nur, dass irgendein
    Satz auf der Seite steht."""
    html = lies_seite(render(tmp_path, kosten=KOSTEN), "transparenz.html")
    assert "Dieser Lauf lag darüber" not in html


def test_ohne_kostenblock_bleibt_die_seite_wie_vorher(tmp_path):
    """Archivberichte von vor dem 27.08.2026 tragen kein `run.kosten`."""
    html = lies_seite(render(tmp_path), "transparenz.html")
    assert "Was dieser Lauf verbraucht hat" not in html


# ------------------------------------------------------------------- Promo
# E10b (27.08.2026, Strategie 2026-08-27 B6): der Promo-Ausfall seit dem
# 14.08.2026 (LLM-Extraktion scheiterte an leerem API-Guthaben) stand bis
# dahin in KEINER Statistik - `stats` kannte kein `promo_*`-Feld, nur das
# Actions-Log, das niemand liest.
PROMO_STATS = {
    "new": NEU_GESAMMELT,
    "promo_seiten_gelesen": 41,
    "promo_angebote_neu": 7,
    "promo_angebote_bestaetigt": 62,
    "promo_extraktion_fehler": 3,
}


def test_transparenz_nennt_die_promo_zahlen(tmp_path):
    html = lies_seite(render(tmp_path, stats=PROMO_STATS), "transparenz.html")
    assert "41 Aktionsseiten gelesen" in html
    assert "7 Angebote neu aufgenommen" in html
    assert "62 bestätigt" in html
    assert "3 Seiten mit gescheiterter Extraktion" in html


def test_transparenz_trennt_neue_und_bestaetigte_angebote(tmp_path):
    """Der Befund vom 27.08.2026: gezaehlt wurden nur die NEUEN Angebote, das
    Etikett sagte "aktualisiert". Eine ruhige Woche (nichts neu, siebzig
    bestaetigt) las sich damit wie ein stiller Totalausfall der Extraktion.
    Gegen den alten Stand faellt dieser Test."""
    ruhig = {
        **PROMO_STATS,
        "promo_angebote_neu": 0,
        "promo_angebote_bestaetigt": 70,
        "promo_extraktion_fehler": 0,
    }
    html = lies_seite(render(tmp_path, stats=ruhig), "transparenz.html")
    assert "0 Angebote neu aufgenommen" in html
    assert "70 bestätigt" in html


def test_transparenz_verschweigt_null_extraktionsfehler(tmp_path):
    """Gegenprobe: ohne Fehler faellt der Halbsatz weg, statt eine "0" zu
    zeigen, die niemand einordnen kann."""
    ohne_fehler = {**PROMO_STATS, "promo_extraktion_fehler": 0}
    html = lies_seite(render(tmp_path, stats=ohne_fehler), "transparenz.html")
    assert "gescheiterter Extraktion" not in html
    assert "41 Aktionsseiten gelesen" in html  # der Rest der Zeile bleibt


def test_ohne_promo_stats_bleibt_die_seite_wie_vorher(tmp_path):
    """Archivberichte von vor dem 27.08.2026 tragen kein `promo_*`-Feld -
    dieselbe Zusicherung wie beim Kostenblock direkt darueber."""
    html = lies_seite(render(tmp_path), "transparenz.html")
    assert "Aktionsseiten gelesen" not in html


def test_oberhalb_der_falz_stehen_mindestens_sechs_geschichten(tmp_path):
    """Abnahmekriterium 1 des Auftrags, als Test.

    Bis zum 06.08.2026 standen dort vier: ein Aufmacher und drei gleich
    grosse Anreisser. Das war der Kern von Antonios Befund - eine
    Titelseite mit vier Geschichten ist keine.
    """
    html = lies_seite(render(tmp_path, highlights=PORTAL), "index.html")
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

    site = render(tmp_path, highlights=PORTAL)
    soup = BeautifulSoup(lies_seite(site, "index.html"), "html.parser")
    gross = soup.select(".aufmacher-bild img, .reihe-zwei .stueck-bild img")
    assert gross, "Weder Aufmacher noch zweite Reihe tragen ein Bild"
    for img in gross:
        breite = int(img.get("width") or 0)
        assert breite >= MIND_BREITE_GROSS, (
            f"Bild mit {breite} px in einer grossen Position ({img.get('src')})"
        )


def test_geloeschtes_bild_hinterlaesst_keinen_leeren_kasten(tmp_path):
    """Eine Berichtsdatei behaelt ihre `image`-Verweise fuer immer, der
    Bildordner nicht: `raeume_auf()` loescht die Bilder aelterer Ausgaben.
    Jede Archivwoche jenseits der Aufbewahrungsfrist zeigte dadurch leere
    Bildkaesten - gefunden am 06.08.2026 an reports/2026-08-05.html."""
    site = render(tmp_path, highlights=PORTAL, bilder_anlegen=False)
    for name in ("index.html", "meldungen.html", "reports/2026-08-05.html"):
        html = lies_seite(site, name)
        assert "images/bild" not in html, f"{name} verweist auf ein fehlendes Bild"
    # Gegenprobe: mit vorhandenen Dateien stehen die Bilder auch da.
    assert "images/bild" in lies_seite(
        render(tmp_path / "mit", highlights=PORTAL), "index.html"
    )


def test_site_images_sammelt_nicht(tmp_path):
    """site/images/ spiegelt den Bildordner, es sammelt nicht.

    Bis zum 06.08.2026 wurde dorthin nur kopiert und nie geloescht.
    `raeume_auf()` beschnitt den Zwischenspeicher, site/images/ behielt
    jedes je geladene Bild - bei rund 130 Bildern je Lauf und zwei Laeufen
    pro Woche waeren das mehrere Gigabyte im Jahr, fuer Bilder, auf die
    keine Seite mehr zeigt."""
    from telco_radar.report.bilder import bildordner

    site = render(tmp_path, highlights=PORTAL)
    (site / "images" / "aus-einem-alten-lauf.jpg").write_bytes(b"alt")
    # Zweiter Renderlauf mit unveraendertem Bildordner.
    render_site(site, tmp_path / "data" / "reports")

    assert not (site / "images" / "aus-einem-alten-lauf.jpg").exists()
    assert {p.name for p in (site / "images").iterdir()} == {
        p.name for p in bildordner(tmp_path).iterdir()
    }


def test_bericht_verlinkt_die_vollstaendige_liste(tmp_path):
    """Wer gekappt anzeigt, muss den Weg zur vollen Liste zeigen."""
    html = lies_seite(render(tmp_path), "index.html")
    assert f"alle {len(HIGHLIGHTS)} Meldungen" in html
    assert "meldungen.html" in html


def test_kopfzeile_nennt_gelesen_und_relevant_getrennt(tmp_path):
    """Ein Halbsatz mit zwei Zahlen - beide muessen stimmen.

    Bis zum 08.08.2026 waren es drei Saetze mit vier Zahlen ("... Davon 13
    zum sofortigen Ansehen (5/5). Lesezeit etwa 16 Minuten."); die dritte
    Zahl stand an jeder betroffenen Meldung noch einmal als Prioritaet."""
    html = lies_seite(render(tmp_path), "index.html")
    assert re.search(
        rf"<b>{len(HIGHLIGHTS)} relevante Meldungen</b>\s*"
        rf"aus {NEU_GESAMMELT} neuen",
        html,
    )


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
    site = render(tmp_path, highlights=PORTAL)
    soup = BeautifulSoup(lies_seite(site, "meldungen.html"), "html.parser")
    assert len(soup.select(".mressort .meldung")) == len(PORTAL)
    # Die Gesamtzahl steht seit dem 08.08.2026 nicht mehr als Satz im Kopf
    # ("138 Meldungen in 7 Ressorts ..."), sondern nur noch verteilt an den
    # Ressorts. Auch verteilt muss sie aufgehen.
    aus_ressorts = [
        int(re.search(r"\d+", z.get_text(" ", strip=True)).group())
        for z in soup.select(".mressort > summary .rubrik-zahl")
    ]
    assert sum(aus_ressorts) == len(PORTAL)


def test_meldungsseite_traegt_den_entfernten_filter_nicht_mehr(tmp_path):
    """Abnahmekriterium 2: der Filter neben "Alle Meldungen" ist weg - samt
    allem, was nur ihm diente. Ein toter Filterrest ist genau die Sorte
    Ballast, die diese Codebasis schon einmal jahrelang mitgeschleppt hat."""
    site = render(tmp_path, highlights=PORTAL)
    html = lies_seite(site, "meldungen.html")
    for rest in (
        "data-such",
        "meldung-filter",
        "meldung-leer",
        "meldung-zahl",
        "ressort-nav",
    ):
        assert rest not in html, f"Rest des Filters auf der Seite: {rest}"
    assert rest not in lies_seite(site, "app.js")
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
        lies_seite(render(tmp_path, highlights=PORTAL), "meldungen.html"), "html.parser"
    )

    ressorts = soup.select(".mressort")
    assert len(ressorts) >= 3, "Die Seite ist nicht nach Ressorts gegliedert"
    assert all(sec.name == "details" for sec in ressorts), (
        "Die Ressortbloecke sind nicht aufklappbar"
    )
    # Jedes Ressort fuehrt mit genau einem Aufmacher ...
    for sec in ressorts:
        assert len(sec.select(".mlead")) == 1
    # ... und mindestens eines nutzt alle drei Gewichtungen.
    assert any(
        sec.select(".mlead") and sec.select(".mzwei") and sec.select(".mz")
        for sec in ressorts
    )
    # Die Ressortzahlen der Uebersicht summieren sich auf die Gesamtzahl.
    # (Bis zum 07.08.2026 stand diese Zahl in einer Sprungleiste; die war
    # die Kruecke einer zu langen Seite und ist mit ihr weggefallen. Seit
    # dem 08.08.2026 steht sie EINMAL je Kachel, im Link darunter - vorher
    # einmal als Chip neben der Rubrik und ein zweites Mal im Link.)
    links = soup.select(".rkachel .rkachel-alle")
    assert len(links) == len(soup.select(".rkachel"))
    aus_kacheln = [
        int(re.search(r"\d+", a.get_text(" ", strip=True)).group()) for a in links
    ]
    assert sum(aus_kacheln) == len(PORTAL)
    assert not soup.select(".rkachel .rubrik-zahl"), (
        "Die Ressortzahl steht wieder zweimal in derselben Kachel"
    )


def test_wochenseite_traegt_die_explorer_daten_nicht_mehr(tmp_path):
    """Der Explorer-JSON war 78,5 KB der 120 KB von bericht.html - fuer
    Daten, die nur sichtbar wurden, wenn jemand ein <details> aufklappte.
    Er gehoert auf meldungen.html, nicht auf die Landeseite."""
    site = render(tmp_path)
    assert 'id="explorer-data"' not in lies_seite(site, "index.html")
    # Die Meldungsseite rendert die Meldungen serverseitig als Zeitungsseite,
    # der Explorer lebt nur noch auf den Archivwochen.
    assert 'id="explorer-data"' not in lies_seite(site, "meldungen.html")
    assert 'id="explorer-data"' in lies_seite(site, "reports/2026-08-05.html")


def test_interne_einordnung_verlaesst_die_seite_nicht(tmp_path):
    """`why_it_matters` ist intern und darf in keiner Seite auftauchen."""
    site = render(tmp_path)
    for name in ("index.html", "meldungen.html", "search_index.json"):
        assert "Interne Einordnung." not in lies_seite(site, name)


# ------------------------------------------------------------- Wettbewerber
GESCHEITERT = [
    {
        "name": "Deutsche Telekom",
        "n_items": 16,
        "moves": [],
        "summary": "",
        "themes": [],
        "vodafone_implication": "",
        "error": "RuntimeError: unknown model",
    }
]
GELUNGEN = [
    {
        "name": "Deutsche Telekom",
        "n_items": 16,
        "moves": [
            {
                "title": "Ein Zug",
                "url": "https://example.com/z",
                "category": "Netz/Technologie",
                "note": "Notiz.",
            }
        ],
        "summary": "Profiltext.",
        "themes": ["5G"],
        "vodafone_implication": "Folge.",
        "error": "",
    }
]


def test_gescheiterte_analyse_sagt_dass_sie_gescheitert_ist(tmp_path):
    """Kein "kommt beim naechsten Lauf", wenn der Lauf schon war."""
    html = lies_seite(render(tmp_path, competitors=GESCHEITERT), "index.html")
    assert "ist gescheitert" in html
    assert "entsteht beim nächsten Lauf" not in html
    # Und die Seite gibt zu, dass die Zuordnung funktioniert hat.
    assert "16 Treffer" in html


def test_vorhandene_profile_zeigen_keinen_leertext(tmp_path):
    """Der Fall, der am 04.08. still verloren ging."""
    html = lies_seite(render(tmp_path, competitors=GELUNGEN), "index.html")
    assert "Profiltext." in html
    assert "ist gescheitert" not in html
    assert "liegt noch keine Wettbewerber-Detailanalyse vor" not in html


def test_ohne_profile_kein_leerer_block(tmp_path):
    """Ein Lauf ohne KI hat wirklich nichts - dann faellt der Block weg,
    statt eine leere Ueberschrift zu zeigen."""
    html = lies_seite(render(tmp_path, competitors=[]), "index.html")
    assert "Deutschland-Fokus</h2>" not in html
    assert "ist gescheitert" not in html


# ------------------------------------------------- Sprungnavigation (Etappe 2)
def test_bericht_bekommt_ein_inhaltsverzeichnis_mit_ankern(tmp_path):
    """2863 Woerter in elf Abschnitten standen als ein Block ohne Einstieg
    da. Jede Ueberschrift braucht einen Anker, damit man aus einer Mail in
    einen Abschnitt verlinken kann."""
    html = lies_seite(render(tmp_path), "index.html")

    assert '<nav class="toc"' in html
    # Beide Abschnitte der Fixture ("Auf einen Blick", "Europa") tauchen als
    # Anker UND als Sprungziel auf.
    for titel, anker in (("Auf einen Blick", "auf-einen-blick"), ("Europa", "europa")):
        assert f'href="#{anker}"' in html
        assert f'<h2 id="{anker}">{titel}</h2>' in html


def test_lesezeit_wird_genannt(tmp_path):
    html = lies_seite(render(tmp_path), "index.html")
    assert "Lesezeit ca." in html


# ------------------------------------------- Quellenbilanz des Laufprotokolls
QUELLEN = [
    {
        "name": "A",
        "url": "https://a.example/f",
        "kind": "rss",
        "region": "global",
        "status": "ok",
        "count": 5,
        "error": "",
    },
    {
        "name": "B",
        "url": "https://b.example/f",
        "kind": "rss",
        "region": "global",
        "status": "empty",
        "count": 0,
        "error": "",
    },
    {
        "name": "C",
        "url": "https://c.example/f",
        "kind": "rss",
        "region": "global",
        "status": "fail",
        "count": 0,
        "error": "HTTPStatusError: 403",
    },
    {
        "name": "D",
        "url": "https://d.example/f",
        "kind": "rss",
        "region": "global",
        "status": "fail",
        "count": 0,
        "error": "ValueError: unparseable feed",
    },
    {
        "name": "E",
        "url": "https://e.example/f",
        "kind": "rss",
        "region": "global",
        "status": "quarantaene",
        "count": 0,
        "error": "",
    },
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
    (reports / "2026-08-05.json").write_text(
        json.dumps(
            {
                "date": "2026-08-05",
                "generated_with_llm": True,
                "stats": {"new": NEU_GESAMMELT},
                "briefing_md": "## Auf einen Blick\n\nText.",
                "regions": {"Europa": {"region_summary": "", "highlights": HIGHLIGHTS}},
                "competitors": [],
                "run": {
                    "duration_seconds": 60,
                    "models": {"analyst": "m", "editor": "m"},
                    "phases": [],
                    "analysts": [],
                    "sources": QUELLEN,
                    "source_summary": {},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    site = tmp_path / "site"
    render_site(site, reports)
    html = (site / "transparenz.html").read_text(encoding="utf-8")

    # 1 ok / 1 leer / 2 gescheitert - die Quarantaene zaehlt nicht als
    # abgefragt, sonst sieht die Bilanz besser aus, je mehr Quellen
    # aufgegeben wurden.
    assert "<b>1 / 1 / 2</b><span>ok / leer / fehlgeschlagen</span>" in html
    assert "<b>4</b><span>Quellen abgefragt</span>" in html
    assert "nicht erreichbar (2)" in html


def test_archivkopie_gibt_sich_als_archiv_zu_erkennen(tmp_path):
    """reports/<datum>.html ist immer eine Archiv-URL - auch fuer die
    neueste Woche. Sonst stehen zwei Seiten mit derselben Ueberschrift
    unter zwei Adressen und die datierte verschweigt, dass sie datiert ist."""
    site = render(tmp_path)
    archiv = lies_seite(site, "reports/2026-08-05.html")
    start = lies_seite(site, "index.html")

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
    alle = _schlagzeilen(lies_seite(render(tmp_path, highlights=hs), "index.html"))
    doppelt = {t for t in alle if alle.count(t) > 1}
    assert not doppelt, f"Doppelte Meldung auf der Titelseite: {doppelt}"


def test_bilder_alter_wochen_werden_aufgeraeumt(tmp_path):
    """Rund 9 Bilder je Lauf mal zwei Laeufe pro Woche waeren ueber ein Jahr
    etwa 200 MB im Repo. Was kein junger Bericht mehr referenziert, faellt."""
    from telco_radar.report import bilder

    reports = tmp_path / "reports"
    reports.mkdir(parents=True)
    (reports / "2026-08-05.json").write_text(
        json.dumps(
            {
                "date": "2026-08-05",
                "stats": {},
                "briefing_md": "",
                "regions": {
                    "Europa": {
                        "highlights": [dict(highlight(1, 5), image="behalten.jpg")]
                    }
                },
            }
        ),
        encoding="utf-8",
    )
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
    site = render(tmp_path, highlights=PORTAL)
    for seite in ("index.html", "meldungen.html"):
        gefunden = _schlagzeilen(lies_seite(site, seite))
        assert gefunden, f"{seite} traegt keine erkennbare Schlagzeile"
        for treffer in gefunden:
            assert not treffer.endswith("…"), (
                f"Abgeschnittene Ueberschrift auf {seite}: {treffer[:70]}"
            )


def test_teilausfall_der_wettbewerber_wird_benannt(tmp_path):
    """Ein Profil da, zwei gescheitert darf nicht aussehen wie ein
    kleineres Wettbewerbsfeld - genau so sah es im Lauf vom 06.08.2026 aus,
    als zwei von drei Profilen am Token-Budget scheiterten."""
    gemischt = [
        dict(GELUNGEN[0]),
        {
            "name": "Telefónica / O2",
            "n_items": 12,
            "moves": [],
            "summary": "",
            "themes": [],
            "vodafone_implication": "",
            "error": "JSONDecodeError",
        },
        {
            "name": "1&1",
            "n_items": 8,
            "moves": [],
            "summary": "",
            "themes": [],
            "vodafone_implication": "",
            "error": "JSONDecodeError",
        },
    ]
    html = lies_seite(render(tmp_path, competitors=gemischt), "index.html")
    assert "Profiltext." in html  # das gelungene Profil
    assert "Telefónica / O2 und 1&amp;1" in html  # die gescheiterten
    assert "2 von 3 Profilen" in html


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


def faden_highlights(quasar_relevance: int = 5) -> list[dict]:
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
    hs.insert(
        0,
        dict(
            highlight(900, 5, "Netz/Technologie", image_w=1200),
            title="Blaulicht Telekommunikation meldet Quartalszahlen",
            operator="Blaulicht",
        ),
    )
    hs.append(
        dict(
            highlight(901, quasar_relevance, "Netz/Technologie", image_w=1200),
            title="Quasarnetz kuendigt Kleinzellennetz gegen Mobilfunker an",
            operator="Quasarnetz",
        )
    )
    hs.append(
        dict(
            highlight(902, quasar_relevance, "Tarif/Pricing", image_w=1200),
            title="Tarifwerk senkt Einstiegspreis fuer unlimitierte Tarife",
            operator="Tarifwerk",
        )
    )
    return hs


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

    site = render(tmp_path, highlights=faden_highlights(), briefing=FADEN_BRIEFING)
    soup = BeautifulSoup(lies_seite(site, "index.html"), "html.parser")
    assert soup.select_one(".front-faden") is None, "Der Vorspann steht noch da"
    assert "Worum es diese Woche geht" not in lies_seite(site, "index.html")
    # Der Bericht steht direkt darunter und traegt seine Sprungmarke weiter.
    assert soup.select_one("#der-wochenbericht")
    assert "front-faden" not in lies_seite(site, "style.css")

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

    site = render(tmp_path, highlights=PORTAL)
    for name in (
        "index.html",
        "meldungen.html",
        "transparenz.html",
        "differenzierung.html",
        "reports/2026-08-05.html",
    ):
        seite = lies_seite(site, name)
        assert "dateline" not in seite, f"Datumszeile noch auf {name}"
        assert "Quellen beobachtet" not in seite
    assert "dateline" not in lies_seite(site, "style.css")
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
    site = render(tmp_path, highlights=PORTAL)
    index = lies_seite(site, "index.html")
    assert "Zahlen der Woche" not in index
    assert "Auswertung je Bereich" not in index
    # ... aber die Frage, die sie beantworteten, hat weiterhin einen Ort.
    assert "Auswertung je Bereich" in lies_seite(site, "transparenz.html")
    # Die Zahl "davon N zum sofortigen Ansehen" ist am 08.08.2026 gefallen:
    # sie stand an jeder betroffenen Meldung ohnehin als Prioritaet 5/5.
    assert "zum sofortigen Ansehen" not in index


# ------------------------------------------------------ Die Wettbewerbsseite
# Sie zeigt zwei Zahlen: den Umfang der Chronik ("56 Meldungen seit 16. Juli
# 2026") und den Umfang je Monatsgruppe. Beide sind Aggregate ueber ALLE
# Wochen des Archivs - genau die Sorte Zahl, die still falsch wird, wenn
# jemand die Gruppierung anfasst.
def test_die_chronik_zaehlt_was_sie_zeigt(tmp_path):
    site = render(tmp_path, competitors=GELUNGEN)
    soup = BeautifulSoup(lies_seite(site, "wettbewerb.html"), "html.parser")
    abschnitt = soup.select_one("section.wb")

    zeilen = abschnitt.select(".wb-zeile")
    kopf = " ".join(abschnitt.select_one(".rubrik-zahl").get_text().split())
    assert kopf.startswith(f"{len(zeilen)} Meldung"), kopf
    # Der Bericht ist der einzige im Archiv - also datiert die Chronik auf
    # seinen Tag, nicht auf den heutigen.
    assert kopf.endswith("seit 5. August 2026"), kopf

    # Die Monatszahlen summieren sich auf dieselbe Zahl (offener Monat plus
    # jeder zugeklappte).
    monate = [int(m.get_text(strip=True)) for m in abschnitt.select(".wb-monat span")]
    assert sum(monate) == len(zeilen)


def test_der_kurzverweis_zeigt_jeden_wettbewerber_mit_profil(tmp_path):
    """Die Titelseite nennt je Wettbewerber eine Zeile - nicht mehr, nicht
    weniger. Ein stiller Verlust hier saehe aus wie ein kleineres
    Wettbewerbsfeld."""
    gemischt = [
        dict(GELUNGEN[0]),
        {
            "name": "1&1",
            "n_items": 8,
            "moves": [],
            "summary": "",
            "themes": [],
            "vodafone_implication": "",
            "error": "JSONDecodeError",
        },
    ]
    soup = BeautifulSoup(
        lies_seite(render(tmp_path, competitors=gemischt), "index.html"), "html.parser"
    )

    mit_profil = [c for c in gemischt if c["summary"]]
    assert len(soup.select(".wb-kurz-zeile")) == len(mit_profil)
    # ... und der Ausfall des anderen wird weiterhin benannt.
    assert "1 von 2 Profilen" in lies_seite(
        render(tmp_path / "b", competitors=gemischt), "index.html"
    )


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
    "first_seen": "2026-08-04",
    "last_active": "2026-08-05",
    "runs_ohne_zuwachs": 0,
    "status": "aktiv",
    "items": [
        {
            "url": f"https://example.com/thema/{i}",
            "title": f"Starlink baut Netz {i}",
            "headline": f"Starlink baut Netz {i}",
            "summary": f"SpaceX kuendigt Schritt {i} an.",
            "operator": "SpaceX",
            "source": f"Quelle {i % 3}",
            "date": "2026-08-05",
            "week": "2026-08-05",
            "relevance": 5 - (i % 3),
        }
        for i in range(9)
    ],
}


def _themenspeicher(tmp_path, thema):
    state = tmp_path / "data" / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "highlight_topics.json").write_text(
        json.dumps({"updated": "2026-08-05", "topics": [thema]}, ensure_ascii=False),
        encoding="utf-8",
    )


def _mit_thema(tmp_path, thema=None):
    site = render(tmp_path)
    _themenspeicher(tmp_path, thema if thema is not None else THEMA)
    render_site(site, tmp_path / "data" / "reports")
    return site


def test_die_themenseite_zaehlt_was_sie_zeigt(tmp_path):
    site = _mit_thema(tmp_path)
    soup = BeautifulSoup(lies_seite(site, f"thema/{THEMA['slug']}.html"), "html.parser")

    lage = " ".join(soup.select_one(".tm-lage").get_text().split())
    quellen = {i["source"] for i in THEMA["items"]}
    assert lage == (
        f"Seit 4. August 2026 · {len(THEMA['items'])} Meldungen "
        f"aus {len(quellen)} Quellen"
    ), lage

    # Die Zahl im Kopf ist die einzige auf der Seite - und sie stimmt: jede
    # Meldung des Themas steht genau einmal darunter, verteilt auf Aufmacher,
    # zweite Reihe und Zeilenliste.
    schlagzeilen = [e.get_text(" ", strip=True) for e in soup.select(".szl")]
    assert len(schlagzeilen) == len(set(schlagzeilen)) == len(THEMA["items"])
    assert len(soup.select(".tm-zeile")) == len(THEMA["items"]) - 3


def test_das_fokusband_nennt_die_zahl_des_themas(tmp_path):
    site = _mit_thema(tmp_path)
    soup = BeautifulSoup(lies_seite(site, "index.html"), "html.parser")

    band = soup.select(".fokusband a")
    assert len(band) == 1
    assert band[0].select_one(".fokusband-titel").get_text(strip=True) == THEMA["title"]
    assert (
        band[0]
        .select_one(".fokusband-zahl")
        .get_text(strip=True)
        .startswith(f"{len(THEMA['items'])} Meldungen")
    )
    assert band[0]["href"] == f"thema/{THEMA['slug']}.html"


def test_ohne_aktives_thema_steht_kein_band_und_keine_seite(tmp_path):
    """Gegenprobe: ein beendetes Thema verschwindet vollstaendig - Seite,
    Band und Ordnerinhalt."""
    site = _mit_thema(tmp_path)
    assert (site / "thema" / f"{THEMA['slug']}.html").exists()

    _themenspeicher(tmp_path, dict(THEMA, status="beendet"))
    render_site(site, tmp_path / "data" / "reports")
    assert not (site / "thema" / f"{THEMA['slug']}.html").exists()
    assert "fokusband" not in lies_seite(site, "index.html")


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
    {
        "id": f"https://sweep{i}.example.com/x",
        "theme": t,
        "operator": f"Betreiber {i}",
        "region": "Europa",
        "what": f"Sweep-Beispiel {i} als Zusatzleistung.",
        "url": f"https://sweep{i}.example.com/x",
        "source": f"sweep{i}.example.com",
        "date": "2026",
        "why": "Bindet Kunden ohne Preisnachlass.",
        "first_seen": "2026-06-15",
        "last_verified": "2026-07-31",
        "status": "aktiv",
    }
    for i, t in enumerate(["ki", "ki", "ki", "cloud", "gaming"])
]
DIFF_STORE = [
    {
        "id": f"https://presse{i}.example.com/y",
        "first_seen": "2026-08-04",
        "theme": t,
        "title": f"Original headline {i} 20 Jul 2026",
        "summary": f"Presse-Beispiel {i} als Zusatzleistung. Nebensatz faellt weg.",
        "url": f"https://presse{i}.example.com/y",
        "operator": f"Presse-Betreiber {i}",
        "region": "Asien",
        "date": None,
        "category": "Partnerschaft",
        "relevance": 4,
        "why_it_matters": f"Begruendung {i}. Vodafone sollte pruefen, ob das traegt.",
        "source": f"Quelle {i}",
    }
    for i, t in enumerate(["ki", "security"])
]


def _diffspeicher(tmp_path, db=None, store=None):
    state = tmp_path / "data" / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "differentiation_db.json").write_text(
        json.dumps(
            {"updated": "2026-08-05", "entries": DIFF_DB if db is None else db},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (state / "differentiation.jsonl").write_text(
        "".join(
            json.dumps(e, ensure_ascii=False) + "\n"
            for e in (DIFF_STORE if store is None else store)
        ),
        encoding="utf-8",
    )


def _mit_differenzierung(tmp_path, db=None, store=None):
    site = render(tmp_path)
    _diffspeicher(tmp_path, db, store)
    render_site(site, tmp_path / "data" / "reports")
    return site


def test_die_differenzierung_zeigt_BEIDE_speicher(tmp_path):
    """Der Kurator lief bis zum 08.08.2026 jede Woche umsonst."""
    soup = BeautifulSoup(
        lies_seite(_mit_differenzierung(tmp_path), "differenzierung.html"),
        "html.parser",
    )
    hauptzeilen = {e.get_text(" ", strip=True) for e in soup.select(".dzk-what")}
    assert "Sweep-Beispiel 0 als Zusatzleistung." in hauptzeilen
    assert "Presse-Beispiel 0 als Zusatzleistung." in hauptzeilen
    # Die Hauptzeile ist der deutsche Satz, nicht der mehrsprachige Rohtitel.
    assert not any("Original headline" in z for z in hauptzeilen)


def test_jeder_hebel_zaehlt_was_unter_ihm_steht(tmp_path):
    """Die einzige Zahl der Seite - gegen die Karten gehalten, die sie meint."""
    soup = BeautifulSoup(
        lies_seite(_mit_differenzierung(tmp_path), "differenzierung.html"),
        "html.parser",
    )
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
    quellen = [
        a["href"]
        for abschnitt in soup.select(".dz-hebel")
        for a in abschnitt.select(".dzk-what")
    ]
    assert len(quellen) == len(set(quellen)) == len(DIFF_DB) + len(DIFF_STORE)


def test_hebel_ohne_beispiel_stehen_nicht_auf_der_seite(tmp_path):
    """Zwoelfmal "Noch keine bestaetigten Beispiele" war zwoelfmal derselbe
    leere Kasten - und die Sprungnavigation zeigt nur, was es gibt."""
    seite = lies_seite(_mit_differenzierung(tmp_path), "differenzierung.html")
    soup = BeautifulSoup(seite, "html.parser")
    assert "Noch keine bestätigten Beispiele" not in seite

    anker = {a["id"] for a in soup.select(".dz-hebel")}
    sprungziele = {a["href"].lstrip("#") for a in soup.select(".dz-nav a")}
    assert (
        sprungziele
        == anker
        == {"dz-theme-ki", "dz-theme-security", "dz-theme-cloud", "dz-theme-gaming"}
    )


def test_die_statuszeile_der_differenzierung_ist_weg(tmp_path):
    """Antonio: die Seite wirkt unruhig durch die vielen Kommentare. Geprueft
    wird auch, dass keine tote Vorlagen-Variable und kein toter CSS-Block
    zurueckgeblieben ist."""
    site = _mit_differenzierung(tmp_path)
    seite = lies_seite(site, "differenzierung.html")
    for tot in (
        "dz-status",
        "Beispiele in der Bibliothek",
        "Hebeln aktiv",
        "seit dem letzten Blick",
        "theme-grid",
        "theme-card",
    ):
        assert tot not in seite, tot
    stil = lies_seite(site, "style.css")
    for tot in ("dz-status", "theme-grid", "theme-card", "dz-move", "dz-card"):
        assert tot not in stil, f"toter CSS-Block {tot}"

    from telco_radar.report import html as html_mod

    vorlage = (
        Path(html_mod.__file__).parent / "templates" / "differenzierung.html.j2"
    ).read_text(encoding="utf-8")
    vorlage = re.sub(r"(?s)\{#.*?#\}", "", vorlage)
    for tot in ("diff_stats", "diff_themes"):
        assert tot not in vorlage, f"Vorlage liest die tote Variable {tot}"


def test_neu_auf_dem_radar_zeigt_nur_junge_funde(tmp_path):
    site = _mit_differenzierung(tmp_path)
    soup = BeautifulSoup(lies_seite(site, "differenzierung.html"), "html.parser")
    radar = soup.select(".dz-radar .dzk")
    # Nur die zwei Presse-Eintraege sind juenger als zehn Tage (Ausgabe vom
    # 5.8., first_seen 4.8.); die Sweep-Eintraege stammen vom 15.6.
    assert len(radar) == len(DIFF_STORE)
    assert (
        soup.select_one(".dz-radar .rubrik h2").get_text(strip=True)
        == "Neu auf dem Radar"
    )
    assert all(k.select_one(".dz-new") for k in radar)


def test_ohne_junge_funde_steht_oben_das_zuletzt_gepruefte(tmp_path):
    """Gegenprobe: eine ruhige Woche darf die Seite nicht enthaupten."""
    soup = BeautifulSoup(
        lies_seite(_mit_differenzierung(tmp_path, store=[]), "differenzierung.html"),
        "html.parser",
    )
    assert (
        soup.select_one(".dz-radar .rubrik h2").get_text(strip=True)
        == "Zuletzt nachgeprüft"
    )
    assert soup.select(".dz-radar .dzk")
    assert not soup.select(".dz-radar .dz-new")


def test_der_suchindex_kennt_auch_die_presse_eintraege(tmp_path):
    """Was auf der Seite steht, muss auffindbar sein - der Index speiste sich
    bis dahin allein aus der DiffDB."""
    site = _mit_differenzierung(tmp_path)
    index = json.loads(lies_seite(site, "search_index.json"))
    diff = [e for e in index if e["kind"] == "differenzierung"]
    assert len(diff) == len(DIFF_DB) + len(DIFF_STORE)
    presse = [e for e in diff if e["operator"] == "Presse-Betreiber 0"]
    assert len(presse) == 1
    assert presse[0]["deep_link"] == "differenzierung.html#dz-theme-ki"
    assert presse[0]["title"] == "Presse-Beispiel 0 als Zusatzleistung."


def test_der_differenzierungsbericht_bleibt_erhalten(tmp_path):
    """Der Essay wandert nach unten in einen Aufklapper - er verschwindet
    nicht. Loeschen von Funktionalitaet ist keine Vereinfachung."""
    site = render(tmp_path)
    berichte = tmp_path / "data" / "reports" / "differenzierung"
    berichte.mkdir(parents=True, exist_ok=True)
    (berichte / "2026-08-05.md").write_text(
        "## Garantien\n\nEin Absatz des Essays.\n", encoding="utf-8"
    )
    _diffspeicher(tmp_path)
    render_site(site, tmp_path / "data" / "reports")

    soup = BeautifulSoup(lies_seite(site, "differenzierung.html"), "html.parser")
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
    soup = BeautifulSoup(
        lies_seite(_mit_differenzierung(tmp_path), "differenzierung.html"),
        "html.parser",
    )
    karten = [
        k for k in soup.select(".dzk") if "dzk--zeile" not in (k.get("class") or [])
    ]
    assert karten
    for karte in karten:
        motiv = karte.select_one(".dzk-motiv")
        assert motiv is not None, karte.get_text(" ", strip=True)[:60]
        assert motiv.select_one("img") or motiv.get_text(strip=True), (
            "leerer Motivkasten"
        )


def test_die_schriftkachel_wiederholt_den_absender_nicht(tmp_path):
    """Ohne Bild traegt die Kachel den Absender - dann steht er nicht noch
    einmal in der Metazeile darunter. Zweimal derselbe Name untereinander
    liest sich als Panne, nicht als Gestaltung."""
    soup = BeautifulSoup(
        lies_seite(_mit_differenzierung(tmp_path), "differenzierung.html"),
        "html.parser",
    )
    kacheln = soup.select(".dzk-kachel")
    assert kacheln, "ohne Bildindex muessten alle Karten eine Kachel tragen"
    for karte in soup.select(".dzk"):
        if karte.select_one(".dzk-kachel") and "dzk--zeile" not in (
            karte.get("class") or []
        ):
            assert not karte.select_one(".dzk-op"), karte.get_text(" ", strip=True)[:80]


def test_das_marktbild_zaehlt_was_die_bibliothek_zeigt(tmp_path):
    """Die Auswertung steht vor den Beispielen und muss dieselben Zahlen
    nennen wie die Rubriken darunter - sonst hat die Seite zwei Wahrheiten."""
    soup = BeautifulSoup(
        lies_seite(_mit_differenzierung(tmp_path), "differenzierung.html"),
        "html.parser",
    )
    marktbild = soup.select_one(".dz-marktbild")
    gesamt = marktbild.select_one(".rubrik-zahl").get_text(" ", strip=True)
    assert gesamt == f"{len(DIFF_DB) + len(DIFF_STORE)} Beispiele"

    # Der Hebel-Balken je Hebel gegen die Rubrikzahl desselben Hebels.
    balken = {
        li.select_one(".dz-balken-name").get_text(strip=True): int(
            li.select_one(".dz-balken-n").get_text(strip=True)
        )
        for li in marktbild.select(".dz-mb-block")[0].select("li")
    }
    for abschnitt in soup.select(".dz-hebel"):
        label = abschnitt.select_one("h2").get_text(strip=True)
        n = len(abschnitt.select(".dzk"))
        assert balken[label] == n, label


def test_jeder_hebel_sagt_in_einem_satz_was_er_bedeutet(tmp_path):
    """Antonio: "damit nicht so viel kognitive Arbeit darin besteht, erstmal
    zu verstehen, was die Differenzierung ist." Wer "Super-App & Oekosystem"
    liest, soll nicht raten muessen."""
    soup = BeautifulSoup(
        lies_seite(_mit_differenzierung(tmp_path), "differenzierung.html"),
        "html.parser",
    )
    abschnitte = soup.select(".dz-hebel")
    assert abschnitte
    for abschnitt in abschnitte:
        satz = abschnitt.select_one(".dz-hebel-was")
        assert satz is not None and len(satz.get_text(strip=True)) > 30, abschnitt.get(
            "id"
        )


def test_der_bericht_steht_verteilt_statt_als_block(tmp_path):
    """Die neue Gliederung landet im Seitenkopf, im Musterband und ueber den
    Hebeln - und dann gibt es KEINEN Aufklapper mehr am Seitenende. Das war
    der Block, den Antonio nicht "reingepastet" haben wollte."""
    site = render(tmp_path)
    berichte = tmp_path / "data" / "reports" / "differenzierung"
    berichte.mkdir(parents=True, exist_ok=True)
    (berichte / "2026-08-05.md").write_text(
        "## Das Bild\n\nDie Lage in einem Satz.\n\n"
        "## Muster\n\n**Bündel** Zwei Anbieter tun dasselbe.\n\n"
        "## Einordnung\n\n### KI & Assistenten\n\nIndien treibt das Feld.\n",
        encoding="utf-8",
    )
    _diffspeicher(tmp_path)
    render_site(site, tmp_path / "data" / "reports")

    soup = BeautifulSoup(lies_seite(site, "differenzierung.html"), "html.parser")
    assert "Die Lage in einem Satz." in soup.select_one(".dz-lage").get_text(
        " ", strip=True
    )
    assert "Zwei Anbieter tun dasselbe." in soup.select_one(".dz-muster-band").get_text(
        " ", strip=True
    )
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
    beobachtung = (
        "Vodafone-Afrika-Gesellschaften könnten Marktanteile an "
        "Reisende verlieren, wenn MTN ein eSIM-Angebot platziert."
    )
    db = [
        dict(
            DIFF_DB[0],
            id="https://a.example.com/",
            url="https://a.example.com/",
            why="Ein Modell, das Vodafone prüfen könnte: KI-Bundles binden Kunden.",
        ),
        dict(
            DIFF_DB[1],
            id="https://b.example.com/",
            url="https://b.example.com/",
            why="Vodafone sollte prüfen, ob das trägt.",
        ),
        dict(
            DIFF_DB[2],
            id="https://c.example.com/",
            url="https://c.example.com/",
            why=beobachtung,
        ),
    ]
    store = [
        dict(
            DIFF_STORE[0],
            id="https://d.example.com/",
            url="https://d.example.com/",
            why_it_matters="Zeigt die Zugkraft von Sportrechten. "
            "Wir sollten prüfen, ob wir nachziehen.",
        )
    ]
    site = _mit_differenzierung(tmp_path, db=db, store=store)
    soup = BeautifulSoup(lies_seite(site, "differenzierung.html"), "html.parser")

    modal = (
        r"(?:soll(?:te|ten)?|m(?:ü|u)ss(?:te|ten|en)?|"
        r"k(?:ö|oe)nn(?:te|ten|en)?|kann|pr(?:ü|ue)fen|bewerten)"
    )
    adressat = r"vodafone|wir|uns(?:er\w*)?"
    rat = [
        re.compile(rf"(?<!\w)(?:{adressat})(?:\W+\w+){{0,4}}\W+{modal}(?!\w)", re.I),
        re.compile(rf"(?<!\w){modal}(?:\W+\w+){{0,4}}\W+(?:{adressat})(?!\w)", re.I),
    ]

    karten = soup.select(".dzk")
    assert karten
    for karte in karten:
        text = " ".join(karte.get_text(" ", strip=True).split())
        if beobachtung[:40] in text:  # der Gegenfall - er DARF matchen
            continue
        for muster in rat:
            assert not muster.search(text), text

    # Der Gegenfall steht wirklich noch da, ungekuerzt.
    assert beobachtung in lies_seite(site, "differenzierung.html")
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
    site = render(tmp_path, highlights=PORTAL, competitors=GELUNGEN)
    # "beim Anklicken" kam am 11.08.2026 auf der Geraeteseite dazu und ist
    # dieselbe Sorte Satz: er beschreibt eine Handlung, statt etwas
    # auszusagen. Die Seite fehlte in dieser Liste, also fing sie ihn nicht.
    verboten = (
        "Jede Kachel zeigt",
        "klappt das",
        "Suchbegriff eingeben",
        "beim Anklicken",
        "nennt ihn beim",
    )
    for name in (
        "index.html",
        "meldungen.html",
        "transparenz.html",
        "differenzierung.html",
        "wettbewerb.html",
        "geraete.html",
    ):
        text = lies_seite(site, name)
        for satz in verboten:
            assert satz not in text, f"{name} erklaert seine Bedienung: {satz}"
    # Auch nicht aus dem Skript nachgereicht.
    assert "Suchbegriff eingeben" not in lies_seite(site, "app.js")


def test_meldungskopf_ist_kicker_und_ueberschrift(tmp_path):
    """Kein Erklaersatz unter der H1 - Antonios woertliches Beispiel."""
    soup = BeautifulSoup(
        lies_seite(render(tmp_path, highlights=PORTAL), "meldungen.html"), "html.parser"
    )
    kopf = soup.select_one(".meldungen-kopf")
    kinder = [k.name for k in kopf.find_all(recursive=False)]
    assert kinder == ["p", "h1"], kinder
    assert kopf.select_one("p")["class"] == ["page-kicker"]


def test_archivzeile_nennt_nur_die_neuen_meldungen(tmp_path):
    """ "3447 gesammelt · 381 neu" waren zwei Zahlen je Zeile, von denen eine
    (die gesammelten) eine Transparenzfrage beantwortet und dort auch
    steht."""
    site = render(tmp_path, highlights=PORTAL)
    soup = BeautifulSoup(lies_seite(site, "meldungen.html"), "html.parser")
    zeilen = soup.select("#archiv .list-row")
    assert zeilen
    for z in zeilen:
        felder = [s["class"][0] for s in z.select("span")]
        assert felder == ["list-row-date", "list-row-new"], felder
    assert "gesammelt" not in lies_seite(site, "meldungen.html")
    # Die verbliebene Zahl stimmt mit dem Bericht ueberein.
    assert f"{NEU_GESAMMELT} neue Meldungen" in zeilen[0].get_text(" ", strip=True)


def test_zaehlwerte_tragen_ueberall_dieselbe_klasse(tmp_path):
    """Ein Etikettensystem, nicht drei. `count-badge` (Chip) und der
    Inline-Style auf der Quellenseite sind in `rubrik-zahl` aufgegangen."""
    site = render(tmp_path, highlights=PORTAL, competitors=GELUNGEN)
    for name in (
        "index.html",
        "meldungen.html",
        "transparenz.html",
        "differenzierung.html",
        "wettbewerb.html",
    ):
        assert "count-badge" not in lies_seite(site, name), name
    # Im Stylesheet ohne Kommentare - dass dort steht, WORAUS `rubrik-zahl`
    # hervorging, ist Dokumentation und keine Regel.
    css = re.sub(r"(?s)/\*.*?\*/", "", lies_seite(site, "style.css"))
    assert "count-badge" not in css
    # ... und die Klasse wird auch wirklich benutzt.
    soup = BeautifulSoup(lies_seite(site, "meldungen.html"), "html.parser")
    assert soup.select(".rubrik-zahl")


# =========================================================== CTM-Linse ====
# Die zweite Bewertungsachse (analyze/ctm.py) und der Zwei-Minuten-Pfad.
# Beides sind ZAHLEN und REIHENFOLGEN auf der Seite - also gehoert es hierhin
# und nicht in einen Modultest: dass `veredle()` richtig rechnet, sagt noch
# nicht, dass die Startseite das Ergebnis auch zeigt.


def _ctm_highlight(i, *, ctm_bezug, relevance=3, satz=None, operator=None):
    h = highlight(i, relevance, "Tarif/Pricing", image_w=1200)
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
    hs = [
        _ctm_highlight(
            1,
            ctm_bezug=3,
            relevance=5,
            satz="Drückt unsere Preisuntergrenze deutlich.",
            operator="Deutsche Telekom",
        )
    ] + PORTAL
    html = lies_seite(render(tmp_path, highlights=hs), "index.html")
    assert "In zwei Minuten" in html
    assert html.index("front-oben") < html.index("kurzpfad")
    soup = BeautifulSoup(html, "html.parser")
    spalte = soup.select_one(".front-wichtig")
    assert spalte.select_one(".kurzpfad") is not None
    # Der Kurzpfad zuerst, die Digest-Spalte darunter.
    rubriken = [h2.get_text(strip=True) for h2 in spalte.select("h2")]
    assert rubriken[:2] == ["In zwei Minuten", "Was wichtig ist"]


def test_zwei_minuten_zeigt_nur_saetze_mit_quelle(tmp_path):
    hs = [
        _ctm_highlight(
            1,
            ctm_bezug=3,
            relevance=5,
            satz="Drückt unsere Preisuntergrenze deutlich.",
            operator="Deutsche Telekom",
        )
    ] + PORTAL
    soup = BeautifulSoup(
        lies_seite(render(tmp_path, highlights=hs), "index.html"), "html.parser"
    )
    zeilen = soup.select(".kurzpfad-zeile")
    assert zeilen
    for z in zeilen:
        assert z.select_one(".kurzpfad-satz").get_text(strip=True)
        assert z.select_one(".kurzpfad-beleg a")["href"].startswith("http")


def test_ohne_direkten_bezug_faellt_der_kasten_weg(tmp_path):
    """Eine Woche ohne Portfoliofrage ist ein Befund, kein Loch, das man mit
    Fuellzeilen schliesst."""
    html = lies_seite(render(tmp_path, highlights=PORTAL), "index.html")
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
    heimat = _ctm_highlight(91, ctm_bezug=3, relevance=3, operator="Deutsche Telekom")
    heimat["title"] = "Telekom-Flatrate mit Unlimited-Daten für 34,95 Euro"
    soup = BeautifulSoup(
        lies_seite(render(tmp_path, highlights=[welt, heimat]), "meldungen.html"),
        "html.parser",
    )
    zeilen = [e.get_text(" ", strip=True) for e in soup.select(".szl")]
    assert any("34,95" in z for z in zeilen)
    erste_heimat = next(i for i, z in enumerate(zeilen) if "34,95" in z)
    erste_welt = next(i for i, z in enumerate(zeilen) if "ChatGPT" in z)
    assert erste_welt < erste_heimat


def test_alte_ausgaben_ohne_ctm_feld_behalten_ihre_reihenfolge(tmp_path):
    """Berichte von vor dem 08.08.2026 tragen das Feld nicht. Sie duerfen
    nicht alle auf Stufe 0 fallen - dann ordnete die Prioritaet nichts mehr,
    und eine Archivwoche kaeme in willkuerlicher Reihenfolge."""
    soup = BeautifulSoup(lies_seite(render(tmp_path), "meldungen.html"), "html.parser")
    zeilen = [e.get_text(" ", strip=True) for e in soup.select(".szl")]
    nummern = [
        int(re.search(r"Meldung (\d+)", z).group(1))
        for z in zeilen
        if re.search(r"Meldung (\d+)", z)
    ]
    # HIGHLIGHTS: 0-3 tragen Prioritaet 5, 4-7 die 4, 8-11 die 3.
    stark = [n for n in nummern if n < 4]
    schwach = [n for n in nummern if n >= 8]
    assert stark and schwach
    assert nummern.index(stark[0]) < nummern.index(schwach[0])


def test_der_folgerungssatz_traegt_seine_marke(tmp_path):
    """Ohne die Marke liest er sich als zweite Zusammenfassung."""
    hs = [
        _ctm_highlight(
            1, ctm_bezug=3, relevance=5, satz="Drückt unsere Preisuntergrenze deutlich."
        )
    ] + PORTAL
    for seite in ("index.html", "meldungen.html"):
        soup = BeautifulSoup(
            lies_seite(render(tmp_path / seite, highlights=hs), seite), "html.parser"
        )
        satz = soup.select_one(".ctm-satz")
        assert satz is not None, seite
        assert (
            satz.select_one(".ctm-marke").get_text(strip=True)
            == "Was das für uns heißt"
        )


def test_belege_eines_ereignisses_stehen_unter_der_meldung(tmp_path):
    """Die weiteren Quellen desselben Ereignisses (analyze/clustering.py) -
    einzeln anklickbar und NICHT als eigene Meldungszeile."""
    h = highlight(1, 5, "Tarif/Pricing")
    h["weitere_quellen"] = [
        {"source": "Light Reading", "url": "https://lr.test/1", "title": "A"},
        {"source": "Telecoms.com", "url": "https://tc.test/2", "title": "B"},
    ]
    h["quellenzahl"] = 3
    soup = BeautifulSoup(
        lies_seite(render(tmp_path, highlights=[h] + PORTAL), "meldungen.html"),
        "html.parser",
    )
    belege = soup.select_one(".mz-belege")
    assert belege is not None
    assert len(belege.select("a")) == 2
    # Ein Link im Link waere ungueltiges HTML - die Belege muessen ausserhalb
    # des Meldungslinks stehen.
    assert belege.find_parent("a") is None
