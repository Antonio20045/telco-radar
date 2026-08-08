"""Foliensatz-Export: feste Vorlage, harte Grenzen, Quellenfolie ist Pflicht."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from telco_radar.report import folien
from telco_radar.report.folien import (
    MAX_KONSEQUENZEN, MAX_LEDE, MAX_PUNKT, MAX_PUNKTE, MAX_QUELLEN,
    MAX_QUELLE_TEXT, MAX_TITEL, baue, inhalt, kuerze,
)


def _bericht(**kw) -> dict:
    d = {
        "date": "2026-08-08",
        "regions": {
            "Europa": {"highlights": [
                {"headline": "Telekom bündelt Google One in Mobilfunktarife",
                 "title": "Mehr Speicher und KI", "operator": "Deutsche Telekom",
                 "url": "https://example.de/a", "source": "teltarif",
                 "relevance": "3", "ctm_bezug": 3,
                 "ctm_satz": "Bündelangebote binden Kunden länger, das trifft "
                             "unsere Wechselquote."},
                {"headline": "o2 senkt den Preis für Unlimited",
                 "url": "https://example.de/b", "source": "o2",
                 "relevance": "2", "ctm_bezug": 2,
                 "why_it_matters": "Preisdruck im unbegrenzten Segment."},
            ]},
            "Asien": {"highlights": [
                {"headline": "Jio startet neues Prepaid",
                 "url": "https://example.de/c", "source": "presse",
                 "relevance": "1", "ctm_bezug": 0},
            ]},
        },
    }
    d.update(kw)
    return d


# --------------------------------------------------------------------------- #
# Kuerzen: Modelltext, der ueberlaeuft, wird nicht durchgereicht
# --------------------------------------------------------------------------- #

def test_kuerze_bleibt_unter_der_grenze():
    lang = "Wort " * 100
    assert len(kuerze(lang, 40)) <= 40


def test_kuerze_schneidet_an_der_wortgrenze():
    assert kuerze("Telekom senkt den Preis erheblich", 20) == "Telekom senkt den…"


def test_kurzer_text_bleibt_unveraendert():
    assert kuerze("Kurz", 40) == "Kurz"


def test_kuerze_zieht_leerraum_zusammen():
    assert kuerze("a    b\n c", 40) == "a b c"


def test_kuerze_vertraegt_none():
    assert kuerze(None, 10) == ""


# --------------------------------------------------------------------------- #
# Die Budgets werden eingehalten - das ist die Zusage dieses Moduls
# --------------------------------------------------------------------------- #

def test_kein_platzhalter_reisst_sein_budget():
    """Eine Folie ist 1080 px hoch und scrollt nicht. Ein Satz, der unten
    herausragt, faellt erst im Termin auf."""
    assert inhalt(_bericht()).ueberlaeufe() == []


def test_ueberlanger_modelltext_wird_gekuerzt_nicht_durchgereicht():
    bericht = _bericht(regions={"Europa": {"highlights": [
        {"headline": "H " * 200, "url": "https://x.de/1", "source": "s",
         "ctm_satz": "K " * 400, "relevance": "3"},
    ]}})
    satz = inhalt(bericht)
    assert satz.ueberlaeufe() == []
    assert len(satz.was_passiert[0]) <= MAX_PUNKT
    assert len(satz.was_heisst_das[0]) <= MAX_LEDE


def test_hoechstens_drei_punkte():
    viele = [{"headline": f"Meldung {i}", "url": f"https://x.de/{i}",
              "source": "s", "relevance": "3"} for i in range(30)]
    satz = inhalt(_bericht(regions={"E": {"highlights": viele}}))
    assert len(satz.was_passiert) == MAX_PUNKTE
    assert len(satz.was_heisst_das) <= MAX_KONSEQUENZEN


def test_quellenliste_ist_gedeckelt():
    viele = [{"headline": f"M {i}", "url": f"https://x.de/{i}", "source": "s"}
             for i in range(40)]
    satz = inhalt(_bericht(regions={"E": {"highlights": viele}}))
    assert len(satz.quellen) == MAX_QUELLEN
    assert all(len(q.text) <= MAX_QUELLE_TEXT for q in satz.quellen)


def test_ueberlauf_bricht_hart_ab(monkeypatch):
    """Vertrauen ist keine Zusicherung: lieber abbrechen als eine Folie
    ausliefern, die im Termin unten herauslaeuft."""
    monkeypatch.setattr(folien, "kuerze", lambda t, g: " ".join(str(t).split()))
    with pytest.raises(ValueError, match="Budget"):
        baue(_bericht(regions={"E": {"highlights": [
            {"headline": "H " * 200, "url": "https://x.de/1", "source": "s"}]}}))


# --------------------------------------------------------------------------- #
# Sortierung und Herkunft der Texte
# --------------------------------------------------------------------------- #

def test_ctm_bezug_bestimmt_die_reihenfolge():
    satz = inhalt(_bericht())
    assert satz.was_passiert[0].startswith("Telekom bündelt")


def test_geprueter_ctm_satz_schlaegt_why_it_matters():
    """Der CTM-Satz ist bereits gegen den Originaltext geprueft."""
    satz = inhalt(_bericht())
    assert satz.was_heisst_das[0].startswith("Bündelangebote binden")


def test_ohne_einordnung_wird_nichts_erfunden():
    bericht = _bericht(regions={"E": {"highlights": [
        {"headline": "Etwas ist passiert", "url": "https://x.de/1",
         "source": "s"}]}})
    satz = inhalt(bericht)
    assert satz.was_heisst_das == []
    assert "keine geprüfte Einordnung" in baue(bericht)


def test_doppelte_quellen_erscheinen_einmal():
    doppelt = [{"headline": "A", "url": "https://x.de/1", "source": "s"},
               {"headline": "B", "url": "https://x.de/1", "source": "s"}]
    assert len(inhalt(_bericht(regions={"E": {"highlights": doppelt}})).quellen) == 1


def test_regions_als_liste_funktioniert_auch():
    bericht = {"date": "2026-08-08", "regions": [
        {"highlights": [{"headline": "X", "url": "https://x.de/1",
                         "source": "s"}]}]}
    assert inhalt(bericht).was_passiert == ["X"]


def test_kaputte_relevanz_kippt_die_sortierung_nicht():
    bericht = _bericht(regions={"E": {"highlights": [
        {"headline": "A", "url": "https://x.de/1", "relevance": "hoch"},
        {"headline": "B", "url": "https://x.de/2", "relevance": "3"}]}})
    assert inhalt(bericht).was_passiert[0] == "B"


# --------------------------------------------------------------------------- #
# Die Quellenfolie ist Pflicht
# --------------------------------------------------------------------------- #

def test_quellenfolie_ist_immer_da():
    """baue() hat keinen Schalter dafuer, und das ist Absicht: das ganze
    Projekt haengt an der Nachpruefbarkeit jeder Aussage."""
    deck = baue(_bericht())
    # Nicht auf den Klartext der Headline pruefen: _akzent() setzt ein Wort
    # in ein <span>, und dann steht die Zeile nicht mehr am Stueck da.
    assert '<ul class="quellen">' in deck
    assert "steht in einer der oben verlinkten Quellen" in deck
    assert 'href="https://example.de/a"' in deck


def test_baue_kennt_keinen_schalter_fuer_die_quellenfolie():
    import inspect
    parameter = set(inspect.signature(baue).parameters)
    assert parameter == {"report", "titel"}


def test_jede_meldung_der_folien_hat_ihre_quelle():
    deck = baue(_bericht())
    for url in ("https://example.de/a", "https://example.de/b"):
        assert url in deck


# --------------------------------------------------------------------------- #
# Das Deck als Datei
# --------------------------------------------------------------------------- #

def test_deck_ist_eine_datei_ohne_fremde_abhaengigkeiten():
    deck = baue(_bericht())
    assert deck.startswith("<!DOCTYPE html>")
    # Inter per Google Fonts ist in der Design-Spezifikation ausdruecklich
    # vorgesehen; sonst nichts Fremdes.
    fremde = [z for z in deck.splitlines()
              if "http" in z and "fonts.g" not in z and "example.de" not in z]
    assert fremde == []


def test_vier_folien_mit_lueckenloser_nummer():
    deck = baue(_bericht())
    assert deck.count('class="slide"') == 4
    for n in range(1, 5):
        assert f"{n:02d} / 04" in deck


def test_genau_ein_akzentwort_je_headline():
    deck = baue(_bericht())
    for zeile in deck.splitlines():
        if 'class="headline"' in zeile or 'class="cover-title"' in zeile:
            assert zeile.count('class="accent"') <= 1


def test_html_wird_maskiert():
    """Ein Anbietername mit spitzen Klammern darf das Deck nicht zerlegen."""
    bericht = _bericht(regions={"E": {"highlights": [
        {"headline": "<script>alert(1)</script>", "url": "https://x.de/1",
         "source": "s"}]}})
    deck = baue(bericht)
    assert "<script>alert(1)</script>" not in deck
    assert "&lt;script&gt;" in deck


def test_leerer_bericht_ergibt_trotzdem_ein_deck():
    deck = baue({"date": "2026-08-08", "regions": {}})
    assert deck.count('class="slide"') == 4
    assert '<ul class="quellen">' in deck


def test_eigener_titel_wird_uebernommen():
    deck = baue(_bericht(), titel="Wochenlage Mobilfunk")
    assert "Wochenlage Mobilfunk" in deck


def test_zu_langer_titel_wird_gekuerzt():
    satz = inhalt(_bericht(), titel="T" * 300)
    assert len(satz.titel) <= MAX_TITEL


def test_deck_laeuft_gegen_einen_echten_bericht():
    """Gegen die zuletzt ausgelieferte Ausgabe, nicht gegen ein Konstrukt."""
    pfad = Path(__file__).resolve().parents[1] / "data" / "reports"
    echte = sorted(pfad.glob("2*.json")) if pfad.exists() else []
    if not echte:
        pytest.skip("kein Bericht im Archiv")
    bericht = json.loads(echte[-1].read_text(encoding="utf-8"))
    satz = inhalt(bericht)
    assert satz.ueberlaeufe() == []
    deck = baue(bericht)
    assert deck.count('class="slide"') == 4
    assert satz.quellen
