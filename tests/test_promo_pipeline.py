"""Tests fuer die Promo-Pipeline-Verklebung (promo_pipeline.py) - nur die
reinen, ohne Netz/LLM testbaren Bausteine. Der volle run_promo_stage()-Ablauf
(Fetch + LLM + Screenshots) wird bewusst nicht hier getestet, exakt wie
schon vor diesem Feature - siehe die anderen test_promo_*.py-Dateien, die
jeweils nur ihre eigene Schicht isoliert pruefen.
"""
from telco_radar.analyze.promo_store import PromoDB
from telco_radar.pipeline import promo_stats
from telco_radar.promo_pipeline import (
    _angebote_bestaetigt,
    _angebote_neu,
    _resolve_item_url,
    _seiten_gelesen,
)


def test_resolve_item_url_prefers_the_llm_selected_deep_link():
    assert _resolve_item_url("https://example.test/geraet-a",
                             "https://example.test/deals/") == "https://example.test/geraet-a"


def test_resolve_item_url_falls_back_to_brand_url_when_missing():
    assert _resolve_item_url(None, "https://example.test/deals/") == "https://example.test/deals/"
    assert _resolve_item_url("", "https://example.test/deals/") == "https://example.test/deals/"


def test_resolve_item_url_falls_back_to_brand_url_when_blank():
    assert _resolve_item_url("   ", "https://example.test/deals/") == "https://example.test/deals/"


# --------------------------------------------------------------------------
# Die drei Zahlen fuers Laufprotokoll (27.08.2026, Strategie B6/E10b): der
# Promo-Ausfall seit dem 14.08.2026 stand bis dahin in KEINER Statistik, nur
# im Actions-Log. `run_promo_stage()` selbst bleibt bewusst ungetestet (siehe
# Modulkopf) - die AGGREGATION ist trotzdem reine Rechnung auf den
# Ruecklaufwerten und deshalb direkt pruefbar.
# --------------------------------------------------------------------------

def test_seiten_gelesen_zaehlt_abgerufene_seiten_nicht_die_extraktion():
    """"gelesen" ist der Seitenabruf, nicht die Extraktion danach - eine
    Seite mit gescheiterter Extraktion wurde trotzdem gelesen."""
    zaehler = {"ok": 3, "unveraendert": 5, "extraktion_fehlgeschlagen": 2,
              "fail": 4}
    assert _seiten_gelesen(zaehler, gesamt=14) == 10


def test_seiten_gelesen_ohne_fehlgeschlagene_abrufe():
    assert _seiten_gelesen({"ok": 5}, gesamt=5) == 5


def test_angebote_neu_summiert_ueber_alle_seiten():
    results = [{"status": "ok", "new_items": 3, "confirmed_items": 0},
              {"status": "ok", "new_items": 1, "confirmed_items": 9},
              {"status": "unveraendert"},                     # kein new_items-Feld
              {"status": "extraktion_fehlgeschlagen", "new_items": 0}]
    assert _angebote_neu(results) == 4
    assert _angebote_bestaetigt(results) == 9


def test_angebote_neu_ohne_treffer_ist_null():
    assert _angebote_neu([{"status": "fail"}]) == 0
    assert _angebote_bestaetigt([{"status": "fail"}]) == 0


def test_eine_ruhige_woche_ist_nicht_dasselbe_wie_ein_ausfall(tmp_path):
    """Der Befund: `_angebote_aktualisiert` zaehlte nur die NEUEN Angebote,
    das Etikett auf transparenz.html sagte "aktualisiert". Eine Woche, in der
    siebzig Aktionen bestaetigt und keine neu aufgenommen wurden, meldete
    damit "0 Angebote aktualisiert" - dasselbe Bild wie ein stiller
    Totalausfall der Extraktion. Gegen den alten Stand faellt dieser Test.

    Gemessen an einer ECHTEN PromoDB mit einem Bestands- und einem neuen
    Angebot, nicht an Handdaten gegen sich selbst: die Frage ist gerade, ob
    der Store die zwei Faelle ueberhaupt auseinanderhaelt.
    """
    db = PromoDB(tmp_path / "db.json")
    db.upsert([{"brand": "congstar", "headline": "10 GB Bonus"}], "2026-08-20")

    bilanz = db.upsert([{"brand": "congstar", "headline": "10 GB Bonus"},
                        {"brand": "congstar", "headline": "Wechselbonus 50 Euro"}],
                       "2026-08-27")

    assert bilanz.neu == 1
    assert bilanz.bestaetigt == 1
    assert len(bilanz.gesehene_ids) == 2
    # Und so, wie die Pipeline sie weiterreicht.
    rec = {"status": "ok", "new_items": bilanz.neu,
           "confirmed_items": bilanz.bestaetigt}
    assert _angebote_neu([rec]) == 1 and _angebote_bestaetigt([rec]) == 1


# --------------------------------------------------------------------------
# Was ins Laufprotokoll kommt - und was NICHT.
# --------------------------------------------------------------------------

def test_ohne_promo_lauf_stehen_keine_promo_zahlen_im_protokoll():
    """`promo_result` ist `{}`, wenn der Zweig abgeschaltet
    (`promo_enabled: false`) oder mit einer Ausnahme uebersprungen wurde. Ohne
    diese Regel stuende auf transparenz.html "0 Aktionsseiten gelesen, 0
    Angebote neu" - die Aussage eines Totalausfalls fuer eine Stufe, die es
    in diesem Lauf gar nicht gab. Gegen den alten Stand faellt dieser Test."""
    assert promo_stats({}) == {}


def test_ein_promo_lauf_ohne_funde_meldet_seine_nullen():
    """Gegenprobe, und sie ist der Punkt der ganzen Unterscheidung: eine
    Stufe, die LIEF und nichts fand, meldet ihre Nullen - genau das ist der
    Befund, der sonst unsichtbar bliebe."""
    stats = promo_stats({"seiten_gelesen": 0, "angebote_neu": 0,
                         "angebote_bestaetigt": 0,
                         "extraktion_fehlgeschlagen": 43})
    assert stats["promo_seiten_gelesen"] == 0
    assert stats["promo_extraktion_fehler"] == 43
