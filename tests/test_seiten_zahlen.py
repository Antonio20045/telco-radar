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

import gzip as _pf_gzip
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from orakel.test_geraete_bestand import (
    gw_cent,
    gw_vergleiche,
    pf_leitzahl_cent,
    pf_seitenzeilen,
)
from orakel.test_seiten_inhalt import (
    FADEN_BRIEFING,
    GELUNGEN,
    HIGHLIGHTS,
    NEU_GESAMMELT,
    PORTAL,
    faden_highlights,
    highlight,
    lies_seite,
    render,
)

from telco_radar.report.html import render_site


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

    site = render(tmp_path, highlights=PORTAL)
    soup = BeautifulSoup(lies_seite(site, "index.html"), "html.parser")
    assert not soup.select(".ressort-raster"), "Ressortraster noch auf der Titelseite"
    assert not soup.select(".ressort"), "Ressortbloecke noch auf der Titelseite"
    assert "Alle Signale dieser Woche" not in lies_seite(site, "index.html")

    # Die Gliederung selbst ist nicht verschwunden - sie steht dort, wo die
    # Frage nach der Einzelmeldung gestellt wird, und dort vollstaendig.
    bericht = json.loads(
        (tmp_path / "data" / "reports" / "2026-08-05.json").read_text(encoding="utf-8")
    )
    echt = _nach_ressort(_flatten(bericht))
    meldungen = BeautifulSoup(lies_seite(site, "meldungen.html"), "html.parser")
    assert len(meldungen.select(".mressort")) == len(echt)
    assert len(meldungen.select(".mressort .meldung")) == len(PORTAL)

    # Und keine tote Rechnung zurueckgelassen: was keine Vorlage mehr liest,
    # wird auch nicht mehr berechnet (dieselbe Regel wie bei der
    # Datumszeile - diese Codebasis hat schon einmal sechs solcher Werte
    # mitgeschleppt).
    assert "ressorts" not in _titelseite(_flatten(bericht))
    assert ".ressort-raster" not in lies_seite(site, "style.css")


def test_jede_meldung_bekommt_genau_ein_ressort():
    """Ohne diese Zusicherung faellt beim Gruppieren still etwas heraus."""
    from telco_radar.report.html import _flatten, _nach_ressort

    bericht = {
        "date": "2026-08-05",
        "stats": {},
        "regions": {"Europa": {"highlights": PORTAL}},
    }
    highlights = _flatten(bericht)
    verteilt = sum(r["n"] for r in _nach_ressort(highlights))
    assert verteilt == len(highlights)
    assert all(h.get("ressort") and h.get("ressort_label") for h in highlights)


def test_meldungsseite_zeigt_jedes_ressort_in_der_uebersicht(tmp_path):
    """Abnahmekriterium 3: erst die Ressorts, dann auf Klick die Tiefe.

    Die Seite war 12 249 px hoch; wer wissen wollte, was unter "Geld &
    Uebernahmen" steht, scrollte acht Bildschirmhoehen. Jetzt hat jedes
    Ressort eine Uebersichtskachel mit zwei bis drei Meldungen und EINEN
    Weg in die Tiefe. Die Pixelmessung dazu macht scripts/pruefe_portal.py
    im echten Browser; dieser Test haelt die Struktur fest, die sie
    voraussetzt."""
    from telco_radar.report.html import _flatten, _nach_ressort

    site = render(tmp_path, highlights=PORTAL)
    soup = BeautifulSoup(lies_seite(site, "meldungen.html"), "html.parser")
    bericht = json.loads(
        (tmp_path / "data" / "reports" / "2026-08-05.json").read_text(encoding="utf-8")
    )
    echt = _nach_ressort(_flatten(bericht))

    kacheln = soup.select(".rkachel")
    assert len(kacheln) == len(echt), "Nicht jedes Ressort hat eine Kachel"
    for kachel, r in zip(kacheln, echt):
        assert kachel.select_one(".rubrik h2").get_text(strip=True) == r["label"]
        # Zwei bis drei Meldungen je Kachel - ein Etikett allein waere ein
        # Inhaltsverzeichnis, keine Uebersicht.
        stuecke = kachel.select(".rk-stueck")
        assert 2 <= len(stuecke) <= 3 or len(stuecke) == r["n"], (
            f"{r['label']}: {len(stuecke)} Meldungen in der Kachel"
        )
        # ... und genau EINE Geste in die Tiefe.
        alle = kachel.select("a.rkachel-alle")
        assert len(alle) == 1
        assert alle[0]["href"] == f"#ressort-{r['key']}"
        assert soup.select_one(f"details#ressort-{r['key']}") is not None


# ------------------------------------------------- Modellwahl je Anbieter
@pytest.mark.parametrize(
    "anbieter,erwartet_analyst,erwartet_editor",
    [
        ("deepseek", "deepseek-v4-flash", "deepseek-v4-pro"),
        ("openai", "anbieter-a/flash", "anbieter-a/pro"),
        ("anthropic", "claude-analyst", "claude-editor"),
    ],
)
def test_modelle_kommen_vom_aktiven_anbieter(
    anbieter, erwartet_analyst, erwartet_editor
):
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

    settings = {
        "openai_analyst_model": "a/flash",
        "openai_editor_model": "a/pro",
        "deepseek_analyst_model": "b-flash",
        "deepseek_editor_model": "b-pro",
    }
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
    assert (
        _mechanik_modell(settings, "deepseek", "deepseek-v4-pro") == "deepseek-v4-flash"
    )
    assert (
        _mechanik_modell(settings, "anthropic", "claude-sonnet-5") == "claude-sonnet-5"
    )
    assert _mechanik_modell({}, "deepseek", "deepseek-v4-pro") == "deepseek-v4-pro"
    # Und die echte Konfiguration traegt den Eintrag wirklich - eine Zahl
    # in der Doku ist erst wahr, wenn ein Test sie gegen die Daten haelt.
    from pathlib import Path

    import yaml

    echte = yaml.safe_load(Path("config/settings.yaml").read_text(encoding="utf-8"))
    assert echte.get("deepseek_mechanik_model") == "deepseek-v4-flash"


def test_anker_ueberleben_umlaute_und_sonderzeichen(tmp_path):
    from telco_radar.report.html import _slug

    assert _slug("Afrika & Naher Osten") == "afrika-naher-osten"
    assert _slug("Türme, Glasfaser & Rechenzentren") == "tuerme-glasfaser-rechenzentren"
    assert (
        _slug("Technologie, Geräte & Regulierung") == "technologie-geraete-regulierung"
    )
    assert _slug("") == "abschnitt"


def test_gleichnamige_abschnitte_bekommen_verschiedene_anker():
    from telco_radar.report.html import _anchor_headings

    html, toc = _anchor_headings("<h2>Global</h2><p>a</p><h2>Global</h2><p>b</p>")
    assert [s["id"] for s in toc] == ["global", "global-2"]
    assert 'id="global"' in html and 'id="global-2"' in html


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

    text = (
        "MTN Nigeria meldet einen Nettogewinnsprung um 70,6 Prozent. "
        "Vodafone kann diese Entwicklung als Vorbild nutzen."
    )
    sauber = _strip_vodafone_advice(text)
    assert "70,6 Prozent" in sauber
    assert "Vodafone kann" not in sauber


def test_reiner_ratschlagsabsatz_faellt_ganz_weg():
    from telco_radar.report.html import _strip_vodafone_advice

    assert _strip_vodafone_advice("Für Vodafone heißt das: schneller werden.") == ""


def test_abkuerzungen_zerlegen_den_satz_nicht():
    """ "z. B." ist kein Satzende - sonst wuerde die halbe Aussage
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

    report = {
        "date": "2026-08-05",
        "stats": {"new": NEU_GESAMMELT},
        "regions": {"Europa": {"highlights": HIGHLIGHTS}},
        "competitors": GELUNGEN,
    }
    dash = _stats(report)
    assert set(dash) == {"tech_radar"}
    assert all(set(t) == {"theme", "n", "w"} for t in dash["tech_radar"])
    assert _flatten(report)  # Gegenprobe: die Fixture ist nicht leer


def test_schlagzeile_bricht_nicht_mitten_im_wort(tmp_path):
    from telco_radar.report.html import _schlagzeile

    lang = {
        "de_title": "Amazon Leo hat bei der US-Behörde FCC eine Genehmigung "
        "für ein Direct-to-Device-Satellitennetz mit bis zu 5.105 "
        "Satelliten beantragt und will 2028 starten"
    }
    kopf = _schlagzeile(lang)
    assert not kopf.rstrip("…").endswith("5.10"), kopf
    assert kopf.rstrip("…").split()[-1] in lang["de_title"].split()


def test_analystenschlagzeile_gewinnt_gegen_den_fliesstextsatz():
    from telco_radar.report.html import _schlagzeile

    h = {
        "headline": "Amazon beantragt Satellitennetz mit 5.105 Satelliten",
        "de_title": "Amazon Leo hat bei der US-Behörde FCC eine Genehmigung für ein …",
    }
    assert _schlagzeile(h) == "Amazon beantragt Satellitennetz mit 5.105 Satelliten"


def test_satztrenner_bricht_nicht_an_einer_datumszahl():
    """ "AST SpaceMobile hat am 5. August 2026 drei Satelliten gestartet"
    endete im Anriss der zweiten Reihe nach vier Woertern: "hat am 5."
    Ordnungszahlen sind im Deutschen keine Satzenden."""
    from telco_radar.report.html import _first_sentence

    text = (
        "AST SpaceMobile hat am 5. August 2026 drei Satelliten gestartet. "
        "Der naechste Start folgt."
    )
    assert _first_sentence(text, 150) == (
        "AST SpaceMobile hat am 5. August 2026 drei Satelliten gestartet."
    )
    # Gegenprobe: ein echtes Satzende wird weiterhin erkannt.
    assert _first_sentence("Erster Satz. Zweiter Satz.", 150) == "Erster Satz."


def test_platzhalter_im_betreiberfeld_erscheint_nicht_als_absender():
    """Der Analyst traegt bei branchenweiten Meldungen "kein spezifischer
    Betreiber" ein. Ueber einer Titelseiten-Schlagzeile gelesen ist das kein
    Absender - dann steht dort die Quelle."""
    from telco_radar.report.html import _flatten

    bericht = {
        "date": "2026-08-05",
        "stats": {},
        "regions": {
            "Global": {
                "highlights": [
                    dict(highlight(1, 5), operator="kein spezifischer Betreiber"),
                    dict(highlight(2, 5), operator="Branche"),
                    dict(highlight(3, 5), operator="Deutsche Telekom"),
                ]
            }
        },
    }
    ops = [h["operator"] for h in _flatten(bericht)]
    assert ops.count("") == 2
    assert "Deutsche Telekom" in ops


def test_originalueberschrift_schlaegt_den_gekuerzten_satz():
    """Vollstaendig und aussagekraeftig schlaegt deutsch und abgehackt."""
    from telco_radar.report.html import _schlagzeile

    h = {
        "title": "UK ISP Hey! Broadband Launch New Bundles with 6 Months Half Price",
        "de_title": "Der britische Glasfaser-Anbieter Hey! Broadband bringt drei neue…",
    }
    assert (
        _schlagzeile(h)
        == "UK ISP Hey! Broadband Launch New Bundles with 6 Months Half Price"
    )


def test_wettbewerber_bekommen_budget_fuer_ein_reasoning_modell():
    """3500 Token reichten unter flash, unter pro nicht: das Nachdenken
    zaehlt gegen max_tokens, und was uebrig bleibt, reicht nicht fuer das
    JSON. Abgerechnet werden erzeugte Token, ein hohes Limit kostet nichts."""
    from telco_radar.analyze.competitors import COMPETITOR_MAX_TOKENS

    assert COMPETITOR_MAX_TOKENS >= 8000


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
    from telco_radar.report.html import (
        _faden,
        _flatten,
        _fuehrende_saetze,
        _rangschluessel,
        _titelseite,
    )

    hs = _flatten(
        {
            "date": "2026-08-05",
            "stats": {},
            "regions": {"Europa": {"highlights": faden_highlights()}},
        }
    )
    # Die Voraussetzung des Falls, ausgeschrieben: gleicher Rang, damit der
    # Test nicht heimlich nur die Sortierung misst.
    rang = {h["operator"]: _rangschluessel(h) for h in hs}
    assert rang["Quasarnetz"] == rang["Blaulicht"] == rang["Tarifwerk"]

    front = _titelseite(hs, _faden(hs, _fuehrende_saetze(FADEN_BRIEFING)))

    assert "Quasarnetz" in front["aufmacher"]["schlagzeile"], (
        f"Aufmacher folgt dem Bericht nicht: {front['aufmacher']['schlagzeile']}"
    )
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
    from telco_radar.report.html import (
        _faden,
        _flatten,
        _fuehrende_saetze,
        _rangschluessel,
        _titelseite,
    )

    hs = _flatten(
        {
            "date": "2026-08-05",
            "stats": {},
            "regions": {"Europa": {"highlights": faden_highlights(quasar_relevance=3)}},
        }
    )
    rang = {h["operator"]: _rangschluessel(h) for h in hs}
    assert rang["Quasarnetz"] < rang["Blaulicht"], (
        "ohne Rangunterschied prueft dieser Test nichts"
    )

    front = _titelseite(hs, _faden(hs, _fuehrende_saetze(FADEN_BRIEFING)))

    aufmacher = front["aufmacher"]
    assert "Quasarnetz" not in aufmacher["schlagzeile"], (
        "der Faden hat eine schwaecher bewertete Meldung nach vorn gezogen: "
        f"{aufmacher['schlagzeile']}"
    )
    # Und positiv: der Aufmacher traegt den besten Rang, den eine Meldung
    # mit grossem Bild ueberhaupt hat.
    from telco_radar.report.bilder import MIND_BREITE_GROSS
    from telco_radar.report.html import _bildbreite

    bester = max(_rangschluessel(h) for h in hs if _bildbreite(h) >= MIND_BREITE_GROSS)
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
    from telco_radar.report.html import (
        _bildbreite,
        _flatten,
        _kennwoerter,
        _rangschluessel,
        _titelseite,
    )

    repo = Path(__file__).resolve().parents[1]
    geprueft = 0
    for datei in sorted((repo / "data" / "reports").glob("*.json")):
        hs = _flatten(json.loads(datei.read_text(encoding="utf-8")))
        if len(hs) < 14:
            continue  # zu klein fuer alle Stufen
        front = _titelseite(hs)
        oben = ([front["aufmacher"]] if front["aufmacher"] else []) + list(
            front["zwei"]
        )
        gross = [h for h in oben if _bildbreite(h) >= MIND_BREITE_GROSS]
        if not gross:
            continue
        schwaechste = min(_rangschluessel(h) for h in gross)
        # Wer den Absenderdeckel schon ausgeschoepft hat, darf hinten stehen.
        voll = set()
        for h in oben:
            kw = _kennwoerter(h.get("operator") or h.get("source_label") or "")
            if (
                sum(
                    1
                    for g in oben
                    if _kennwoerter(g.get("operator") or g.get("source_label") or "")
                    & kw
                )
                >= 2
            ):
                voll |= kw
        ueber = [
            h["schlagzeile"]
            for h in front["vier"]
            if _rangschluessel(h) > schwaechste
            and _bildbreite(h) >= MIND_BREITE_GROSS
            and not (
                _kennwoerter(h.get("operator") or h.get("source_label") or "") & voll
            )
        ]
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
    from telco_radar.report.html import (
        _bildbreite,
        _flatten,
        _rangschluessel,
        _titelseite,
    )

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
    namen = [
        "Quasarnetz",
        "Tarifwerk",
        "Blaulicht",
        "Nordfunk",
        "Sylttel",
        "Ostmobil",
        "Wattline",
        "Duenenfunk",
        "Kliffnetz",
        "Moorcom",
        "Heidefon",
        "Foehrmobil",
        "Bodencom",
        "Ryktel",
        "Aalfunk",
    ]
    roh = []
    for i, (ctm, rel) in enumerate([(2, 3)] * 3 + [(1, 3)] * 5 + [(1, 2)] * 7):
        h = highlight(700 + i, rel, "Tarif/Pricing", image_w=1200)
        h |= {"ctm_bezug": ctm, "operator": namen[i]}
        roh.append(h)
    hs = _flatten(
        {"date": "2026-08-15", "stats": {}, "regions": {"Europa": {"highlights": roh}}}
    )
    front = _titelseite(hs)
    assert front["vier"], "ohne dritte Reihe prueft dieser Test nichts"
    assert len(front["wichtig"]) == 7, front["wichtig"]

    schwaechste = min(_rangschluessel(h) for h in front["vier"])
    ueberholt = [
        h["schlagzeile"]
        for h in front["wichtig"]
        if _bildbreite(h) >= 1 and _rangschluessel(h) > schwaechste
    ]
    assert not ueberholt, (
        f"steht als Textzeile, obwohl schwaechere Meldungen eine Bildkachel "
        f"bekamen: {ueberholt}"
    )


def test_ohne_belegbaren_faden_bleibt_die_alte_reihenfolge(tmp_path):
    """Eine falsche Verbindung ist schlimmer als keine: teilt eine Meldung
    zu wenige seltene Woerter mit dem Fuehrungssatz, gilt er als nicht
    belegt und die Seite sortiert weiter nach Dringlichkeit."""
    from telco_radar.report.html import _faden, _flatten, _fuehrende_saetze, _titelseite

    hs = _flatten(
        {
            "date": "2026-08-05",
            "stats": {},
            "regions": {"Europa": {"highlights": faden_highlights()}},
        }
    )
    fremd = "## Auf einen Blick\n- Ein Thema, das in keiner Meldung vorkommt.\n"
    assert _faden(hs, _fuehrende_saetze(fremd)) == []
    front = _titelseite(hs, _faden(hs, _fuehrende_saetze(fremd)))
    assert front["faden_oben"] == 0
    assert front["aufmacher"] is not None


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
    from test_geraete_zeitreihe_ansicht import HEUTE as ZR_HEUTE
    from test_geraete_zeitreihe_ansicht import _baue

    from telco_radar.geraete_config import lade_katalog, lade_quellen
    from telco_radar.report import geraete_view, geraete_zeitreihe

    root, state = _baue(tmp_path)
    reports = root / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"{ZR_HEUTE}.json").write_text(
        json.dumps(
            {
                "date": ZR_HEUTE,
                "language": "de",
                "briefing_md": "## Auf einen Blick\n\n- Nichts.\n",
                "stats": {},
                "regions": [],
            }
        ),
        encoding="utf-8",
    )
    (reports / f"{ZR_HEUTE}.md").write_text("# B\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    g = geraete_view.aufbereiten(
        state, lade_quellen(root), lade_katalog(root), heute=ZR_HEUTE
    )
    aufbereitung = geraete_zeitreihe.aufbereiten(state, g["tco"])
    return site, aufbereitung


def test_die_kartenzahlen_stehen_wortlich_auf_der_seite(tmp_path):
    site, aufbereitung = _geraete_kartenzahl_site(tmp_path)
    soup = BeautifulSoup(
        (site / "geraete.html").read_text(encoding="utf-8"), "html.parser"
    )
    karten = soup.select("#gr-zr-kacheln button[data-modell]")
    assert karten, "die Modell-Karten fehlen auf der Geräteseite"
    assert len(karten) == len(aufbereitung["kacheln"]), (
        f"{len(karten)} Karten auf der Seite, "
        f"{len(aufbereitung['kacheln'])} in der Aufbereitung"
    )
    text_je_id = {k.get("data-modell"): k.get_text() for k in karten}
    assert len(text_je_id) == len(aufbereitung["kacheln"]), (
        "dieselbe Karte zweimal auf der Seite"
    )
    for k in aufbereitung["kacheln"]:
        text = text_je_id[k["id"]]
        assert k["kurz"] in text, f"Name fehlt auf der Karte {k['id']}"
        # P1-Fix (Sicht-B2): die Zahlen stehen JE BAND auf der Karte - jede
        # Bandlage muss wortlich da sein (get_text liest hidden mit).
        assert set(k["baender"]), f"Karte {k['id']} ohne Band-Werte"
        for band, s in k["baender"].items():
            if s["ab"]:
                assert s["ab"] in text, (
                    f"ab-Preis {s['ab']} ({band}) fehlt auf {k['id']}"
                )
                if s["ab_monat"]:
                    assert s["ab_monat"] in text, (
                        f"Ø/Monat {s['ab_monat']} ({band}) fehlt auf {k['id']}"
                    )
            # 28.09.2026: die Bewegung steht nur noch, wenn sich wirklich
            # etwas bewegt hat; „±0 € in N Tagen" bleibt von der Karte weg.
            if s["delta_text"] and s["delta_richtung"] != "gleich":
                assert s["delta_text"] in text, (
                    f"Bewegung {s['delta_text']} ({band}) fehlt auf {k['id']}"
                )
            elif s["delta_text"]:
                assert s["delta_text"] not in text, (
                    f"Stillstand {s['delta_text']} ({band}) steht auf {k['id']}"
                )


def test_keine_karte_zeigt_zahlen_die_die_aufbereitung_nicht_hat(tmp_path):
    """Gegenprobe: der Karten-Text der Seite besteht NUR aus Feldern der
    Aufbereitung - kein Zahlfragment, das dort nicht herkommt (waere die
    Vorlage auf eigene Rechnung gerechnet)."""
    import re

    site, aufbereitung = _geraete_kartenzahl_site(tmp_path)
    soup = BeautifulSoup(
        (site / "geraete.html").read_text(encoding="utf-8"), "html.parser"
    )
    erlaubt = set()
    for k in aufbereitung["kacheln"]:
        erlaubt |= {k["kurz"], "ab"}
        for s in k["baender"].values():
            erlaubt |= {s["ab"], s["ab_monat"], s["delta_text"], s["anbieter_text"]}
    erlaubt |= {t for k in aufbereitung["kacheln"] for t in k["kurz"].split()}
    erlaubt.discard(None)
    for karte in soup.select("#gr-zr-kacheln button[data-modell]"):
        for wort in re.findall(r"[\d.,]+ ?(?:€|€/Monat|Tag(?:en)?)", karte.get_text()):
            assert wort in erlaubt or any(wort in (f or "") for f in erlaubt if f), (
                f"Zahl {wort!r} steht auf der Karte, aber nicht in der Aufbereitung"
            )


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
    soup = BeautifulSoup(
        (site / "geraete.html").read_text(encoding="utf-8"), "html.parser"
    )
    zeilen = soup.select("#gr-katalogtabelle tr.gr-k-zeile")
    assert zeilen, "keine Katalog-Modellzeile - der Test prueft nichts"
    preise = [
        float(z["data-s-preis"])
        for z in zeilen
        if (z.get("data-s-preis") or "").strip()
    ]
    leit = soup.select_one("#tafel-katalog .gr-leit--katalog .gr-leit-zahl")
    assert preise, (
        "Fixture ohne einen einzigen ab-Preis - Gatterfall, "
        "der Test braeuchte die andere Lage"
    )
    assert leit is not None, (
        "Katalog ohne Leitzahl, obwohl Zeilen mit ab-Preis dastehen"
    )
    zahl = leit.get_text(" ", strip=True)
    match = re.match(r"^([\d.]+,\d\d) €$", zahl)
    assert match, f"Leitzahl ist kein Preis: {zahl!r}"
    assert float(match.group(1).replace(".", "").replace(",", ".")) == min(preise), (
        f"Leitzahl {zahl} != guenstigster Zeilenpreis {min(preise)}"
    )


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
    soup = BeautifulSoup(
        (site / "geraete.html").read_text(encoding="utf-8"), "html.parser"
    )
    first_paint = soup.select("#gr-zr-gruppe .gr-zr-rechnungen template[data-anb]")
    assert first_paint, "die Rechenweg-Vorlagen fehlen im First Paint"
    fragment = BeautifulSoup(
        (site / "data" / "geraete-zeitreihe.html").read_text("utf-8"), "html.parser"
    ).select("template[data-anb]")
    assert fragment, "das Zeitreihen-Fragment traegt keine Vorlagen"
    # Wächter (§6): der Lookup darf nicht teilweise treffen. Der First
    # Paint traegt NUR das Startpaar, das Fragment ALLE Paare - beide
    # Zahlen muessen gegen die Aufbereitung stimmen, sonst waere der
    # Zahl-Vergleich darunter grün, ohne etwas zu prüfen.
    start = aufbereitung["start_block"]
    assert start is not None, "die Aufbereitung nennt kein Startpaar"
    vorlagen_start = start["rechenweg_html"].count("<template")
    vorlagen_alle = sum(
        p["rechenweg_html"].count("<template") for p in aufbereitung["paare"]
    )
    assert len(first_paint) == vorlagen_start, (
        f"{len(first_paint)} Vorlagen im First Paint, {vorlagen_start} "
        f"beim Startpaar der Aufbereitung"
    )
    assert len(fragment) == vorlagen_alle, (
        f"{len(fragment)} Vorlagen im Fragment, {vorlagen_alle} in der Aufbereitung"
    )
    quelle = "\n".join(p["rechenweg_html"] for p in aufbereitung["paare"])
    assert quelle, "die Aufbereitung liefert keine Rechenweg-Zeichen"
    # Gegenprobe im selben Test (§6): eine Zusicherung, die nichts
    # ausschließt, prüft nichts - ein erfundener Betrag darf nie
    # durchgehen.
    assert "999999,99 €" not in quelle
    for t in list(first_paint) + list(fragment):
        for zahl in _re.findall(r"[0-9][0-9.,]*", t.get_text(" ", strip=True)):
            assert zahl in quelle, (
                f"Zahl {zahl!r} im Rechenweg-Panel kommt nicht aus der "
                f"Aufbereitung (Vorlage gerechnet statt gesetzt?)"
            )


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
    katalog = {
        "geraete": [
            {
                "hersteller": "Apple",
                "modell": "Apple X",
                "generation": 1,
                "speicher": [256],
                "segment": "flagship",
            },
            {
                "hersteller": "Samsung",
                "modell": "Galaxy S26 Ultra",
                "generation": 26,
                "speicher": [256],
                "segment": "flagship",
            },
            {
                "hersteller": "Google",
                "modell": "Pixel 11",
                "generation": 11,
                "speicher": [128],
                "segment": "flagship",
            },
        ]
    }
    quellen = {
        "anbieter": [
            {
                "name": "A-Laden",
                "typ": "handel",
                "rang": 1,
                "methode": "ldjson",
                "basis_url": "https://a.example",
                "einstiege": [{"url": "https://a.example/liste"}],
            },
            {
                "name": "B-Laden",
                "typ": "handel",
                "rang": 2,
                "methode": "ldjson",
                "basis_url": "https://b.example",
                "einstiege": [{"url": "https://b.example/liste"}],
            },
            {
                "name": "1&1",
                "typ": "netzbetreiber",
                "rang": 3,
                "methode": "ldjson",
                "basis_url": "https://1und1.example",
                "einstiege": [{"url": "https://1und1.example/liste"}],
            },
        ]
    }
    for name, daten in (
        ("geraete_katalog.yaml", katalog),
        ("farben.yaml", {"farben": {"schwarz": ["Schwarz"]}}),
        ("geraete_quellen.yaml", quellen),
    ):
        (root / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )

    def _listung(anbieter, device, speicher, preis, **kw):
        sku = f"{device}-{speicher}gb-{anbieter.lower().replace('&', '')}"
        e = {
            "id": f"{anbieter.lower()}--{sku}",
            "sku_id": sku,
            "device_id": device,
            "anbieter": anbieter,
            "anbieter_typ": "handel",
            "speicher_gb": speicher,
            "farbe_roh": "Schwarz",
            "farbe_normalisiert": "schwarz",
            "zustand": "neu",
            "first_seen": "2026-09-01",
            "last_verified": "2026-09-17",
            "status": "aktiv",
            "missed_checks": 0,
            "preis_ohne_vertrag": preis,
            "zuzahlung": None,
            "quelle_url": f"https://example.de/{sku}",
            "abgerufen_am": "2026-09-17",
            "verfuegbarkeit": "lieferbar",
        }
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
        _listung(
            "1&1",
            "samsung-galaxy-s26-ultra",
            256,
            None,
            anbieter_typ="netzbetreiber",
            tarif_referenz="1&1 All-Net-Flat S",
            preis_mit_vertrag_ab=32.99,
        ),
        _listung("A-Laden", "google-pixel-11", 128, 799.0),
    ]
    state = root / "data" / "state"
    state.mkdir(parents=True)
    (state / "geraete_db.json").write_text(
        json.dumps(
            {
                "updated": "2026-09-17",
                "anbieter": {n: {"laeufe": 4} for n in ("A-Laden", "B-Laden", "1&1")},
                "listungen": listungen,
            }
        ),
        encoding="utf-8",
    )
    (state / "geraete_preise.jsonl").write_text("", encoding="utf-8")

    def _buendel(anbieter, device, speicher, tarif, monat, komplett):
        sku = f"{device}-{speicher}gb-{anbieter.lower().replace('&', '')}"
        # `komplett`: ein Bündel MIT Aufteilung in Tarifpreis und Geräte-
        # rate (so rechnet die TCO-Ansicht Karten). Sonst nennt der Satz
        # nur den Bündel-Monatspreis - 1&1-Regel § 13.2: EIN Betrag, und
        # beides nebeneinander verwirft der TCO-Leser zu Recht.
        b = {
            "id": f"buendel--{anbieter.lower()}--{sku}",
            "sku_id": sku,
            "anbieter": anbieter,
            "tarif_name": tarif,
            "tarif_id": f"{anbieter.lower()}:m",
            "tarif_id_guete": "hoch",
            "buendel_monatlich": None,
            "tarif_monatlich": 20.0,
            "geraet_zuzahlung": 1.0,
            "geraet_monatsrate": 12.99,
            "laufzeit_monate": 24,
            "anschlusspreis": 0.0,
            "zustand": "neu",
            "rabatte": [],
            "quelle_url": f"https://example.de/{sku}/buendel",
            "abgerufen_am": "2026-09-17",
            "first_seen": "2026-09-17",
            "last_verified": "2026-09-17",
        }
        if komplett:
            return b
        b["tarif_monatlich"] = None
        b["geraet_monatsrate"] = None
        b["buendel_monatlich"] = monat
        return b

    (state / "geraete_tco.json").write_text(
        json.dumps(
            {
                "updated": "2026-09-17",
                "buendel": [
                    _buendel(
                        "1&1",
                        "samsung-galaxy-s26-ultra",
                        256,
                        "1&1 All-Net-Flat S",
                        32.99,
                        komplett=False,
                    ),
                    _buendel("A-Laden", "apple-x", 256, "A M", 41.0, komplett=True),
                ],
                "sim_only": [],
            }
        ),
        encoding="utf-8",
    )
    (state / "geraete_tco_historie.jsonl").write_text("", encoding="utf-8")
    tarife = [
        {
            "anbieter": b["anbieter"],
            "name": b["tarif_name"],
            "tarif_id": b["tarif_id"],
            "tarif_id_guete": "hoch",
            "grundgebuehr": b["tarif_monatlich"],
            "mindestlaufzeit_monate": 24,
            "rabattphasen": [],
            # P3-E1: ein Volumen plus Testleiter, damit die Band-Spalte
            # eine Stufe hat (10 GB -> XS der Testleiter).
            "datenvolumen_gb": 10,
            "quelle_url": b["quelle_url"],
            "abgerufen_am": "2026-09-17",
        }
        for b in (state / "geraete_tco.json").exists()
        and json.loads((state / "geraete_tco.json").read_text())["buendel"]
    ]
    from tarifleiter_testbestand import mit_leiter

    tarife = mit_leiter(tarife, "2026-09-17")
    (state / "tarife.jsonl").write_text(
        "\n".join(json.dumps(t) for t in tarife) + "\n", encoding="utf-8"
    )

    reports = root / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / "2026-09-17.json").write_text(
        json.dumps(
            {
                "date": "2026-09-17",
                "language": "de",
                "briefing_md": "## Auf einen Blick\n\n- Nichts.\n",
                "stats": {},
                "regions": [],
            }
        ),
        encoding="utf-8",
    )
    (reports / "2026-09-17.md").write_text("# B\n", encoding="utf-8")
    site = root / "site"
    # BEWUSST ohne cfg (S4-4 der P3-Code-Pruefung): geraete.html braucht
    # keines - aber NUR hier. render_site() OHNE cfg rendert sonst eine
    # still halbe Seite (CLAUDE.md §6: transparenz.html verliert seinen
    # Quellenbestand, wettbewerb.html den halben Inhalt). Wer diese Zeile
    # in eine Welt mit watchlist/news_sources KOPIERT, kopiert die Falle -
    # dort `load_config(root)` mitgeben.
    render_site(site, reports)
    g = geraete_view.aufbereiten(
        state, lade_quellen(root), lade_katalog(root), heute="2026-09-17"
    )
    return site, g


def _katalog_suppe(site):
    return BeautifulSoup(
        (site / "geraete.html").read_text(encoding="utf-8"), "html.parser"
    )


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
        'eine Zeile des Katalogs sagt "ohne Preis"'
    )
    # Gegenprobe im selben Test: die 1&1-Zeile ist DA und hat keinen
    # Barpreis - der Zustand, der das Wort frueher ausgeloest hat.
    ohne_barpreis = [m for m in g["katalog_modelle"] if m["ab_preis"] is None]
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
        f"der Bündel-Monatspreis {erwartet_monat} fehlt wortlich"
    )
    # Der Beleg der Modellzeile ist verlinkt (Belegzwang).
    modellzeile = next(
        z
        for z in suppe.select("#gr-katalogtabelle .gr-k-zeile")
        if "Galaxy S26 Ultra" in (z.get("data-s-geraet") or "")
    )
    links = [a.get("href") for a in modellzeile.select("a.gr-a-quelle")]
    assert modell["buendel_beleg"]["quelle_url"] in links, (
        f"der Bündel-Beleg fehlt unter den Links der Modellzeile: {links}"
    )
    # Und die AUFKLAPPERZEILE derselben 1&1-Listung traegt ihre Angabe
    # samt Tarifnamen - dieselbe Zahl, derselbe Beleg.
    auf = suppe.select_one(f"#{modellzeile['data-auf']}")
    zeilen = [
        r
        for r in auf.select("tr")
        if r.select_one("td") is not None and "1&1" in r.select_one("td").get_text()
    ]
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
                            "Kennwort 'nur im Bündel' in der Zelle"
                        )
                    assert ein_format.match(b[: -len("/Monat")]), (
                        f"{name}: Bündel-Betrag {b!r} folgt nicht dem einen Format"
                    )
                else:
                    assert ein_format.match(b), (
                        f"{name}: Betrag {b!r} folgt nicht dem einen "
                        "Format (deutsch, zwei Dezimalstellen)"
                    )

    # Ansicht Einzelgerätpreis: Modell-Preiszelle, Spannen-Zelle und die
    # Listungs-Preiszellen des Aufklappers - je EIN Format. Die Spanne
    # "X – Y" besteht aus zwei Beträgen, die JEDEM dem Muster folgen.
    _pruefe(
        [z.select("td.gr-sp--barpreis")[0] for z in zeilen],
        "der Einzelgerätepreis-Spalte",
    )
    _pruefe(
        [
            z.select("td.gr-sp--barpreis")[2]
            for z in zeilen
            if "€" in z.select("td.gr-sp--barpreis")[2].get_text()
        ],
        "der Spannen-Spalte",
    )
    _pruefe(
        [
            r.select("td")[2]
            for r in suppe.select("#gr-katalogtabelle .gr-k-listungen tr")
            if r.select_one("td") is not None and "€" in r.select("td")[2].get_text()
        ],
        "der Aufklapper-Preisspalte",
        kennwort_nötig=False,
    )
    # Ansicht Gesamtkosten: TCO-24-Zelle und Ø €/Monat-Zelle. Der
    # Monatsbetrag trägt seinen Zusatz "/Monat" - ein EINMALBETrag in der
    # Monats-Spalte waere die schlimmere Vermischung.
    _pruefe(
        [
            z.select("td.gr-sp--tco")[0]
            for z in zeilen
            if "€" in z.select("td.gr-sp--tco")[0].get_text()
        ],
        "der TCO-24-Spalte",
    )
    monat_zellen = [
        z.select("td.gr-sp--tco")[1]
        for z in zeilen
        if "€" in z.select("td.gr-sp--tco")[1].get_text()
    ]
    if monat_zellen:
        _pruefe(monat_zellen, "der Ø €/Monat-Spalte", kennwort_nötig=False)
        # EIN Format heisst auch: eine Einheiten-Schreibweise je Spalte.
        # Die Ø-Spalte trägt ihre Einheit im KOPF ("Ø €/Monat") und ihre
        # Beträge ohne Zusatz - gemischt waere der Fehlertyp.
        schreibweisen = {
            b.endswith("/Monat")
            for z in monat_zellen
            for b in betrag.findall(z.get_text())
        }
        assert len(schreibweisen) == 1, (
            f"die Ø €/Monat-Spalte mischt Beträge mit und ohne /Monat: {schreibweisen}"
        )


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
        f"Rubrik sagt {rubrik}, Aufbereitung kennt {len(modelle)} Modelle"
    )
    assert len(suppe.select("#gr-katalogtabelle .gr-k-zeile")) == len(modelle)
    assert len(supe := suppe.select("#gr-katalogtabelle .gr-a-auf")) == len(modelle), (
        "Aufklapperzahl != Modellzahl"
    )
    # Und die Listungen summieren zurück: jede Listung des Bestands steht
    # GENAU EINMAL in einem Aufklapper.
    aufklappzeilen = suppe.select("#gr-katalogtabelle .gr-k-listungen tr td")
    anzahl_listungszeilen = sum(
        1
        for r in suppe.select("#gr-katalogtabelle .gr-k-listungen tr")
        if r.select_one("td") is not None
    )
    erwartet = sum(m["listungen"] for m in modelle)
    assert anzahl_listungszeilen == erwartet, (
        f"{anzahl_listungszeilen} Aufklapperzeilen, die Aufbereitung "
        f"zählt {erwartet} Listungen"
    )
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
        '{"updated": "2026-09-17", "buendel": [KAPUTT', encoding="utf-8"
    )
    render_site(site, root / "data" / "reports")
    suppe = _katalog_suppe(site)
    tafel = suppe.select_one("#tafel-katalog")
    assert tafel, "Katalogtafel fehlt"
    assert "ohne Preis" not in tafel.get_text(), (
        'der unlesbare Store darf keine Zeile auf "ohne Preis" fallen lassen'
    )
    # Die Bündel-Angabe steht noch da - jetzt aus der LISTUNG gelesen:
    # derselbe Monatspreis (die 1&1-Listung traegt ihn selbst), der Beleg
    # ist der Quelllink DER LISTUNG statt des Stores.
    text = tafel.get_text()
    assert "nur im Bündel" in text
    erwartet = f"{mit_store['buendel_monat']:.2f}".replace(".", ",")
    assert f"ab {erwartet} €/Monat" in text, (
        f"der Bündel-Monatspreis {erwartet} fehlt ohne Store"
    )
    zeile = next(
        z
        for z in suppe.select("#gr-katalogtabelle .gr-k-zeile")
        if "Galaxy S26 Ultra" in (z.get("data-s-geraet") or "")
    )
    links = [a.get("href") for a in zeile.select("a.gr-a-quelle")]
    assert any("/samsung-galaxy-s26-ultra" in h for h in links), (
        f"der Beleg der Listung fehlt: {links}"
    )


def test_die_band_spalte_nennt_die_stufe_der_zeile(tmp_path):
    """Die Spalte "Band" der Katalogtabelle zeigt die Stufe des guenstigsten
    Buendels als Etikett der Tarifleiter ("XS"), eine Zeile ohne Buendel "–".
    Vorher bildete die Vorlage die alten Schluessel klein/mittel/gross von
    Hand ab - mit den Stufen-Schluesseln lief das ins Leere, und jede Zeile
    zeigte still "–". Gegenprobe: mindestens eine Zeile traegt eine Stufe."""
    site, g = _geraete_katalog_site(tmp_path)
    suppe = _katalog_suppe(site)
    je_modell = {
        z.get("data-s-geraet"): z
        for z in suppe.select("#gr-katalogtabelle .gr-k-zeile")
    }
    gezeigt = {}
    for m in g["katalog_modelle"]:
        zeile = je_modell.get(m["titel"])
        assert zeile is not None, f"keine Tabellenzeile fuer {m['titel']}"
        zelle = zeile.select("td.gr-sp--tco")[3].get_text().strip()
        soll = (m.get("tco_band") or "").upper() or "–"
        assert zelle == soll, f"{m['titel']}: Band {zelle!r} statt {soll!r}"
        gezeigt[m["titel"]] = zelle
    assert any(z != "–" for z in gezeigt.values()), (
        f"keine Zeile zeigt eine Stufe - der Test prueft so nichts: {gezeigt}"
    )
    assert gezeigt.get("Google Pixel 11 128 GB") == "–", gezeigt


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
        f"{delta_apple.get_text()!r}"
    )
    assert delta_apple.select_one("[title]"), "der Grund steht nicht im title der Zelle"
    # samsung: TCO aus dem 1&1-Monatspreis (32,99 × 24 + 1 Zuzahlung),
    # ebenfalls ohne Referenz - dasselbe Etikett.
    samsung = je_modell["Samsung Galaxy S26 Ultra 256 GB"]
    assert "keine Referenz" in samsung.select("td.gr-sp--tco")[2].get_text()
    # pixel: KEIN Bündel -> die TCO-Zelle nennt ihren eigenen Grund
    # ("kein Bündel gemessen"), die Delta-Zelle bleibt "–" - zwei
    # Stummen, aber nur eine braucht das Etikett.
    pixel = je_modell["Google Pixel 11 128 GB"]
    assert "kein Bündel gemessen" in pixel.select("td.gr-sp--tco")[0].get_text()
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
    je_modell = {
        z.get("data-s-geraet"): z
        for z in suppe.select("#gr-katalogtabelle .gr-k-zeile")
    }
    pixel = je_modell["Google Pixel 11 128 GB"]
    assert pixel.select("td.gr-sp--barpreis")[2].get_text().strip() == "ein Preis", (
        "ein Händler, aber keine Aussage in der Zelle"
    )
    # Gegenprobe: Apple hat ZWEI Händler mit wesentlichem Abstand (1000
    # gegen 1100) - dort steht die echte Spanne, nicht das Etikett.
    apple = je_modell["Apple X 256 GB"]
    spannen_text = apple.select("td.gr-sp--barpreis")[2].get_text()
    assert "1.000,00 € – 1.100,00 €" in spannen_text, (
        f"die Spanne fehlt: {spannen_text!r}"
    )
    assert "ein Preis" not in spannen_text


_PF_MECHANIK_HEUTE = "2026-09-20"
_PF_CS_FIXTURE = "congstar_tarifseite_allnet_flat_m.html.gz"
_PF_CS_URL = "https://www.congstar.de/handytarife/allnet-flat-tarife/allnet-flat-m/"
# Das Geraet des Abrufs, an dem beide Zahlweisen desselben Tarifs stehen.
_PF_CS_TITEL = "Apple iPhone 17 Pro 512 GB cosmic orange"
_PF_CS_TARIF = "Allnet Flat M"
_PF_CS_BLATT = "congstar:allnet-flat-m"
_PF_CS_SKU = "apple-iphone-17-pro-512gb-cosmic-orange"
_PF_CS_MODELL = "apple-iphone-17-pro-512"


def _pf_wegwerf_wurzel(tmp_path, buendel, blatt: dict, leiter: bool = True):
    """Ein Wegwerf-Repo (config/, data/state/, data/reports/) und der
    gerenderte Stand darin. Weder `site/` noch `data/` des Repos werden
    angefasst (harte Regel 1/3)."""
    import yaml

    from telco_radar.analyze.tco_store import TcoDB

    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    konfig = {
        "geraete_katalog.yaml": {
            "geraete": [
                {
                    "hersteller": "Apple",
                    "modell": "iPhone 17 Pro",
                    "generation": 17,
                    "marktstart": "2025-09-19",
                    "speicher": [512],
                    "segment": "premium",
                }
            ]
        },
        "farben.yaml": {"farben": {"cosmic orange": ["Cosmic Orange"]}},
        "geraete_quellen.yaml": {
            "anbieter": [
                {
                    "name": "congstar",
                    "typ": "discount",
                    "netz": "Telekom",
                    "rang": 3,
                    "methode": "congstar_next",
                    "basis_url": "https://www.congstar.de",
                    "einstiege": [{"url": _PF_CS_URL, "kind": "buendel"}],
                }
            ]
        },
    }
    for name, daten in konfig.items():
        (tmp_path / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )

    state = tmp_path / "data" / "state"
    state.mkdir(parents=True, exist_ok=True)
    # P3-E1: ohne Vodafone-Tarifleiter gibt es keine Stufe und damit
    # keinen Startblock (`vorgabe` leer) - die Mechanik braucht eine Leiter.
    # Die Testleiter (XS 5 / M 36 / L 85 GB) legt Allnet Flat M (125 GB)
    # in Stufe L; die Zahlen dieses Tests haengen an keiner Stufe.
    from tarifleiter_testbestand import mit_leiter

    (state / "tarife.jsonl").write_text(
        "".join(
            json.dumps(t, ensure_ascii=False) + "\n"
            for t in (mit_leiter([blatt], _PF_MECHANIK_HEUTE) if leiter else [blatt])
        ),
        encoding="utf-8",
    )
    (state / "geraete_preise.jsonl").write_text("", encoding="utf-8")
    (state / "geraete_db.json").write_text(
        json.dumps(
            {
                "updated": _PF_MECHANIK_HEUTE,
                "anbieter": {"congstar": {"laeufe": 4, "funde_gesamt": 1}},
                "listungen": [
                    {
                        "id": f"congstar--{_PF_CS_SKU}",
                        "sku_id": _PF_CS_SKU,
                        "device_id": "apple-iphone-17-pro",
                        "anbieter": "congstar",
                        "anbieter_typ": "discount",
                        "netz": "Telekom",
                        "speicher_gb": 512,
                        "farbe_roh": "Cosmic Orange",
                        "farbe_normalisiert": "cosmic orange",
                        "zustand": "neu",
                        "first_seen": _PF_MECHANIK_HEUTE,
                        "last_verified": _PF_MECHANIK_HEUTE,
                        "status": "aktiv",
                        "missed_checks": 0,
                        "preis_ohne_vertrag": None,
                        "quelle_url": _PF_CS_URL,
                        "abgerufen_am": _PF_MECHANIK_HEUTE,
                        "verfuegbarkeit": "lieferbar",
                        "confidence": "hoch",
                        "einstiege": [_PF_CS_URL],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    db = TcoDB(state / "geraete_tco.json")
    db.upsert_buendel(buendel, _PF_MECHANIK_HEUTE)
    assert db.save(_PF_MECHANIK_HEUTE), (
        "der Store hat nichts geschrieben - ohne Bestand rendert nichts"
    )

    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"{_PF_MECHANIK_HEUTE}.json").write_text(
        json.dumps(
            {
                "date": _PF_MECHANIK_HEUTE,
                "language": "de",
                "briefing_md": "## Auf einen Blick\n\n- Nichts Besonderes.\n",
                "stats": {},
                "regions": [],
            }
        ),
        encoding="utf-8",
    )
    (reports / f"{_PF_MECHANIK_HEUTE}.md").write_text("# Bericht\n", encoding="utf-8")

    site = tmp_path / "site"
    render_site(site, reports)
    return site


def test_pf_beide_ratenlaufzeiten_eines_congstar_abrufs_werden_zwei_zeilen(
    tmp_path, bestand
):
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
    rohsaetze = [
        s
        for s in lies_buendel(antwort, url=_PF_CS_URL)
        if s["titel"] == _PF_CS_TITEL and s["tarif_name"] == _PF_CS_TARIF
    ]
    # Gegenprobe am Adapter: ohne zwei Laufzeiten im ABRUF prueft der Rest
    # nichts (die Fixture waere getauscht worden).
    assert {s["laufzeit_monate"] for s in rohsaetze} == {24, 36}, (
        f"der gespeicherte Abruf {_PF_CS_FIXTURE} belegt nicht beide "
        f"Laufzeiten fuer {_PF_CS_TITEL}/{_PF_CS_TARIF}: "
        f"{sorted(s['laufzeit_monate'] for s in rohsaetze)}"
    )

    blatt = next(
        (
            json.loads(z)
            for z in (bestand / "state" / "tarife.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if z.strip() and json.loads(z).get("tarif_id") == _PF_CS_BLATT
        ),
        None,
    )
    assert blatt is not None, (
        f"Tarifblatt {_PF_CS_BLATT} fehlt im Bestand - ohne aufloesbaren "
        "Tarif legt der Store kein Buendel ab (benannte Luecke)"
    )

    bilanz = aus_rohsaetzen(
        [
            {**s, "anbieter": "congstar", "sku_id": _PF_CS_SKU, "quelle_url": s["url"]}
            for s in rohsaetze
        ],
        Tarifbestand([blatt]),
        _PF_MECHANIK_HEUTE,
    )
    assert len(bilanz.buendel) == 2, (
        f"{len(bilanz.buendel)} statt 2 Buendel aus zwei Rohsaetzen - "
        f"{bilanz.ohne_tarif} ohne aufloesbaren Tarif, "
        f"haeufigste: {bilanz.offene_tarife}"
    )

    site = _pf_wegwerf_wurzel(tmp_path, bilanz.buendel, blatt)
    seite = pf_seitenzeilen(
        (site / "data" / "geraete-buendel.html").read_text(encoding="utf-8"),
        (site / "geraete.html").read_text(encoding="utf-8"),
    )
    zeilen = [
        z
        for z in seite.get(_PF_CS_MODELL, [])
        if z["anbieter"] == "congstar"
        and z["tarif"] == _PF_CS_TARIF
        and z["zustand"] == "neu"
    ]
    assert len(zeilen) == 2, (
        f"{len(zeilen)} statt 2 Buendelzeilen fuer {_PF_CS_MODELL} - "
        "zwei Zahlweisen desselben Tarifs ueberschreiben sich wieder; "
        f"gezeigte Ratenlaufzeiten: "
        f"{[z['laufzeit_raten'] for z in zeilen]}"
    )

    je_laufzeit = {z["laufzeit_raten"]: z for z in zeilen}
    assert set(je_laufzeit) == {24, 36}, (
        f"die zwei Zeilen nennen nicht 24 und 36 Raten, sondern {sorted(je_laufzeit)}"
    )

    # Jede Zeile traegt IHRE Zahlen - Rate, Ratenzahl, Restschuld. Soll
    # aus der EINEN Definition dieses Abschnitts (`pf_leitzahl_cent`),
    # gerechnet auf dem ROHSATZ des Adapters, nicht auf der Seite.
    for satz in rohsaetze:
        laufzeit = satz["laufzeit_monate"]
        zeile = je_laufzeit[laufzeit]
        soll = pf_leitzahl_cent({**satz, "id": f"congstar/{laufzeit}m"})
        gw_vergleiche(
            Decimal(zeile["gesamt_cent"]) / 100,
            soll,
            f"congstar {_PF_CS_TARIF}, {laufzeit} Raten",
        )
        # Der Betrag in der Schreibweise der Seite - aus Cent, nicht aus
        # einer Fliesskomma-Formatierung (Geld rechnet dieser Abschnitt in
        # ganzen Cent, siehe `gw_cent`).
        rate_cent = gw_cent(satz["geraet_monatsrate"])
        rate = f"{rate_cent // 100},{rate_cent % 100:02d}"
        assert f"in {laufzeit} Raten à {rate} €" in zeile["bau"], (
            f"die {laufzeit}-Monats-Zeile nennt ihre Rate nicht: {zeile['bau']}"
        )
    assert je_laufzeit[24]["gesamt_cent"] == je_laufzeit[36]["gesamt_cent"], (
        "congstar finanziert zum Nulltarif - weichen die Leitzahlen ab, "
        "hat sich die Rechnung geaendert und dieser Test ist neu zu "
        f"verankern: {je_laufzeit[24]['gesamt_cent']} gegen "
        f"{je_laufzeit[36]['gesamt_cent']}"
    )

    # Die Restschuld trennt die zwei Zeilen: 12 Raten a 33,50 EUR bleiben
    # nach Monat 24 offen, bei 24 Raten nichts.
    inline = (site / "geraete.html").read_text(encoding="utf-8")
    offen = re.findall(r"danach noch offen: ([\d.,]+) € \((\d+) Geräteraten\)", inline)
    assert offen == [("402,00", "12")], (
        "genau die 36-Monats-Zeile muss ihre Restschuld nennen (402,00 € "
        f"aus 12 Geraeteraten), gefunden: {offen}"
    )


def test_pf_ohne_tarifleiter_nennt_die_seite_den_grund(tmp_path, bestand):
    """Fehlt die Vodafone-Leiter im Bestand, hat kein Geraet eine Stufe.
    Die Seite sagt dann genau das (`LEITER_FEHLT_TEXT`) und nicht, es gebe
    noch keine Messreihe - darunter stehen ja gemessene Buendel (Regel 9).

    Gegen den alten Stand rot: `band_leer` stand nur im JSON-Knoten, keine
    Vorlage las es; die Seite zeigte den Messreihen-Satz."""
    from telco_radar.analyze.tco_buendel import aus_rohsaetzen
    from telco_radar.collect.geraete.congstar import lies_buendel
    from telco_radar.report.geraete_tco_band import LEITER_FEHLT_TEXT
    from telco_radar.tarif_bezug import Tarifbestand

    pfad = Path(__file__).parent / "fixtures" / "geraete" / _PF_CS_FIXTURE
    antwort = _pf_gzip.open(pfad, "rb").read().decode("utf-8", "replace")
    rohsaetze = [
        s
        for s in lies_buendel(antwort, url=_PF_CS_URL)
        if s["titel"] == _PF_CS_TITEL and s["tarif_name"] == _PF_CS_TARIF
    ]
    blatt = next(
        json.loads(z)
        for z in (bestand / "state" / "tarife.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if z.strip() and json.loads(z).get("tarif_id") == _PF_CS_BLATT
    )
    bilanz = aus_rohsaetzen(
        [
            {**s, "anbieter": "congstar", "sku_id": _PF_CS_SKU, "quelle_url": s["url"]}
            for s in rohsaetze
        ],
        Tarifbestand([blatt]),
        _PF_MECHANIK_HEUTE,
    )
    # Gegenprobe: ohne Buendel waere der Messreihen-Satz sogar richtig.
    assert bilanz.buendel, "kein Buendel aus dem gespeicherten Abruf"

    site = _pf_wegwerf_wurzel(tmp_path, bilanz.buendel, blatt, leiter=False)
    seite = BeautifulSoup(
        (site / "geraete.html").read_text(encoding="utf-8"), "html.parser"
    )
    leer = seite.select_one("#gr-zr-gruppe .gr-zr-keine")
    assert leer is not None, "kein Leersatz im Graphbereich"
    text = " ".join(leer.get_text().split())
    assert text == LEITER_FEHLT_TEXT, text
    assert "Messreihe" not in text
