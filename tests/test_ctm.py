"""Die CTM-Linse: nicht "ist das wichtig?", sondern "ist das fuer UNS wichtig?".

Die Beispiele sind die aus dem Auftragsdokument vom 08.08.2026 - also die
Meldungen, an denen der falsche Massstab aufgefallen ist.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from telco_radar.analyze import ctm

WURZEL = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def fokus():
    return ctm.lade_fokus(WURZEL)


def _h(**kw):
    basis = {"title": "", "summary": "", "operator": "", "category": "Sonstiges",
             "region": "Global", "relevance": 3}
    basis.update(kw)
    return basis


# ------------------------------------------------------- Stufe 3 im Code

def test_telekom_flat_ist_direkt(fokus):
    """Der Fall aus dem Dokument: preisrelevant, deutscher Markt - und stand
    trotzdem klein in der dritten Reihe."""
    h = _h(title="Telekom-Flatrate mit Unlimited-Daten für 34,95 Euro bei Freenet",
           operator="Deutsche Telekom", category="Tarif/Pricing")
    assert ctm.deterministische_stufe(h, fokus) == ctm.DIREKT


def test_heimatmarkt_ohne_endkundenthema_ist_nicht_direkt(fokus):
    """"Deutsche Telekom baut Rechenzentrum" ist Heimatmarkt und trotzdem
    keine Portfoliofrage. Beides zusammen, nie eins allein."""
    h = _h(title="Deutsche Telekom, AIT Advance European Quantum Communication",
           operator="Deutsche Telekom", category="Netz/Technologie")
    assert ctm.deterministische_stufe(h, fokus) is None


def test_preisfrage_ausserhalb_des_heimatmarkts_ist_nicht_direkt(fokus):
    h = _h(title="Reliance Jio Rs 200 OTT Pass is Also Bundling Unlimited 5G",
           operator="Reliance Jio", category="Tarif/Pricing")
    assert ctm.deterministische_stufe(h, fokus) is None


def test_stichwort_ersetzt_die_kategorie(fokus):
    """Eine Lieferzeitmeldung ist eine Portfoliofrage, auch wenn der Analyst
    sie unter "Sonstiges" abgelegt hat."""
    h = _h(title="o2 nennt neue Lieferzeit für das iPhone", operator="O2",
           category="Sonstiges", summary="Die Lieferzeit steigt auf drei Wochen.")
    assert ctm.deterministische_stufe(h, fokus) == ctm.DIREKT


def test_markenname_trifft_nicht_mitten_im_wort(fokus):
    """Ohne Wortgrenze fand "O2" jedes "CO2" - dieselbe Lehre wie im
    Promo-Zweig, wo "EUR" aus "1 Euro einmalig" die Kachel "1 Eur" schnitt."""
    h = _h(title="Neue CO2-Bilanz der Branche veröffentlicht",
           category="Tarif/Pricing")
    assert ctm.deterministische_stufe(h, fokus) is None


# ------------------------------------------------- Zusammenspiel mit dem Modell

def test_das_modell_kann_stufe_3_nicht_wegnehmen(fokus):
    h = _h(title="Telekom senkt Preis für Allnet-Flat", operator="Telekom",
           category="Tarif/Pricing", ctm_bezug=0)
    ctm.veredle([h], fokus)
    assert h["ctm_bezug"] == ctm.DIREKT
    assert h["ctm_quelle"] == "regel"


def test_das_modell_kann_sich_keine_stufe_3_geben(fokus):
    """Sonst waere die Achse wieder das, was sie ersetzen soll: eine
    Einschaetzung, die jeder Lauf neu auslegt."""
    h = _h(title="Jio bundles OTT with unlimited 5G", operator="Reliance Jio",
           category="Tarif/Pricing", ctm_bezug=3)
    ctm.veredle([h], fokus)
    assert h["ctm_bezug"] == ctm.UEBERTRAGBAR
    assert h["ctm_quelle"] == "modell"


def test_ohne_modellwert_gibt_es_eine_begruendbare_stufe(fokus):
    """Bei einem Lauf ohne Modell stuenden sonst alle Meldungen auf 0 und die
    Sortierung waere leer - schlimmer als vorher."""
    h = _h(title="MTN übernimmt IHS Towers", operator="MTN Group",
           category="M&A")
    ctm.veredle([h], fokus)
    assert h["ctm_bezug"] == ctm.HINTERGRUND
    assert h["ctm_quelle"] == "rückfall"


def test_bilanz_zaehlt_die_stufen(fokus):
    hs = [_h(title="Telekom senkt Preise", operator="Telekom",
             category="Tarif/Pricing"),
          _h(title="MTN übernimmt IHS Towers", operator="MTN", category="M&A")]
    bilanz = ctm.veredle(hs, fokus)
    assert bilanz["direkt"] == 1 and bilanz["hintergrund"] == 1


# ------------------------------------------------------------- der Satz

@pytest.mark.parametrize("satz,gut", [
    ("Erste 5G-Flat unter 35 Euro in einem Nachbarmarkt – drückt die "
     "Preisuntergrenze für unsere Unlimited-Stufe.", True),
    ("Das zeigt den Trend zu Bundles.", False),
    ("Unterstreicht die Bedeutung von Konvergenz im Markt.", False),
    ("Wahrscheinlich müssen wir die Option nachziehen, sonst wandern "
     "Bestandskunden ab.", True),
    ("Kurz.", False),
])
def test_satz_muss_eine_konsequenz_tragen(satz, gut):
    assert ctm.satz_taugt(satz)[0] is gut


def test_zu_langer_satz_wird_verworfen_nicht_gekuerzt():
    """Ein Halbsatz mit "…" ist in dieser Codebasis schon zweimal als Fehler
    benannt worden. Lieber keine Zeile als eine abgehackte."""
    lang = ("Wir müssen unsere Preisuntergrenze " + "sehr " * 30 + "prüfen.")
    ok, grund = ctm.satz_taugt(lang)
    assert not ok and "lang" in grund


def test_satz_unter_stufe_2_wird_entfernt(fokus):
    """Ein Konsequenzsatz zu einer Meldung ohne Konsequenz ist erfunden."""
    h = _h(title="MTN übernimmt IHS Towers", category="M&A", ctm_bezug=0,
           ctm_satz="Drückt unsere Marge im Turmgeschäft.")
    ctm.veredle([h], fokus)
    assert "ctm_satz" not in h


def test_verworfene_saetze_stehen_mit_grund_in_der_bilanz(fokus):
    h = _h(title="Jio bundles OTT", category="Tarif/Pricing", ctm_bezug=2,
           ctm_satz="Das zeigt den Trend zu Bundles.")
    bilanz = ctm.veredle([h], fokus)
    assert bilanz["saetze_verworfen"] == 1
    assert "ctm_satz" not in h
    assert bilanz["gruende"]


# ------------------------------------------------------- Zwei-Minuten-Pfad

def test_zwei_minuten_nimmt_nur_geprueftes():
    hs = [
        _h(title="A", ctm_bezug=3, relevance=5,
           ctm_satz="Drückt unsere Preisuntergrenze deutlich nach unten."),
        _h(title="B", ctm_bezug=3, relevance=5),          # ohne Satz
        _h(title="C", ctm_bezug=1, relevance=5, ctm_satz="Egal welcher Satz."),
    ]
    pfad = ctm.zwei_minuten(hs)
    assert [h["title"] for h in pfad] == ["A"]


def test_zwei_minuten_bringt_einen_absender_nur_einmal():
    hs = [_h(title=f"T{i}", operator="Deutsche Telekom", ctm_bezug=3,
             relevance=5, ctm_satz="Drückt unsere Preisuntergrenze.")
          for i in range(4)]
    hs.append(_h(title="O2", operator="O2", ctm_bezug=3, relevance=4,
                 ctm_satz="Zwingt uns zu einer Antwort beim Anschlusspreis."))
    pfad = ctm.zwei_minuten(hs)
    assert len(pfad) == 2
    assert {h["operator"] for h in pfad} == {"Deutsche Telekom", "O2"}


def test_zwei_minuten_ist_leer_wenn_es_nichts_gibt():
    """Eine Woche ohne direkte Portfoliofrage ist ein Befund, kein Loch."""
    assert ctm.zwei_minuten([_h(title="A", ctm_bezug=1)]) == []


def test_zwei_minuten_hoert_bei_fuenf_zeilen_auf():
    hs = [_h(title=f"T{i}", operator=f"Anbieter {i}", ctm_bezug=3, relevance=5,
             ctm_satz="Drückt unsere Preisuntergrenze deutlich.")
          for i in range(12)]
    assert len(ctm.zwei_minuten(hs)) == 5


# ------------------------------------------------------------ Konfiguration

def test_fehlende_konfiguration_legt_nichts_lahm(tmp_path):
    leer = ctm.lade_fokus(tmp_path)
    h = _h(title="Telekom senkt Preise", operator="Telekom",
           category="Tarif/Pricing")
    assert ctm.deterministische_stufe(h, leer) is None
    ctm.veredle([h], leer)          # darf nicht werfen
    assert h["ctm_bezug"] in (0, 1, 2, 3)


def test_die_ausgelieferte_konfiguration_kennt_die_deutschen_marken(fokus):
    assert fokus.trifft_heimatmarkt("Angebot von congstar")
    assert fokus.trifft_heimatmarkt("1&1 startet Aktion")
    assert not fokus.trifft_heimatmarkt("Verizon startet Aktion")
    assert fokus.sicherheitsskala, "die Skala speist die Transparenzseite"
