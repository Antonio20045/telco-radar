"""Der Fremdschluessel vom Geraet zum Tarif - und die Grenze der Betragssuche.

Gemessen am echten Bestand (`data/state/tarife.jsonl`, Stand 04.09.2026:
32 Tarife von vier Anbietern) UND an gestellten Faellen. Der echte Bestand
beweist, dass die Namen dieses Marktes wirklich treffen; die gestellten
Faelle beweisen die Regeln, die heute zufaellig nicht eintreten.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from telco_radar.analyze.tarif_referenzen import aus_bestand
from telco_radar.collect.tarif_crawler import tarif_id
from telco_radar.tarif_bezug import Bezug, Tarifbestand
from telco_radar.tarif_model import HOCH, MITTEL
from telco_radar.tco_model import SimOnlyReferenz

_WURZEL = Path(__file__).parent.parent
# Die MESSUNG vom 04.09.2026, als Fixture. Sie liegt hier und nicht in
# `data/state/`, weil ein Baseline-Reset (CLAUDE.md § 6: die vier
# State-Dateien per `git rm` entfernen) sonst diese Testdatei mitnaehme -
# und ein Test, der an einem Betriebszustand haengt, meldet den naechsten
# Reset statt den naechsten Fehler.
_FIXTURE = _WURZEL / "tests" / "fixtures" / "tarife" / "bestand_2026-09-04.jsonl"
# Der AUSGELIEFERTE Bestand. Genau EIN Test sieht ihn an, und der prueft
# das Abnahmekriterium der Phase 6, nicht das Verhalten des Codes.
_BESTAND = _WURZEL / "data" / "state" / "tarife.jsonl"


def _satz(anbieter: str, name: str, grundgebuehr=None, **kw) -> dict:
    """Ein Bestandssatz mit der KANONISCHEN Tarif-ID.

    Sie wird gerechnet und nicht hingeschrieben: eine gestellte ID, die
    `tarif_id()` nie erzeugen wuerde, macht jeden Namenstest gruen oder rot
    aus dem falschen Grund - genau das ist beim ersten Anlauf passiert.
    """
    tid = tarif_id(anbieter, name)
    satz = {"tarif_id": tid, "anbieter": anbieter, "name": name,
            "grundgebuehr": grundgebuehr, "art": "mobilfunk",
            "dokument_url": f"https://x.de/{tid}.pdf",
            "abgerufen_am": "2026-09-04", "preisphasen": []}
    satz.update(kw)
    return satz


@pytest.fixture(scope="module")
def echt() -> Tarifbestand:
    return Tarifbestand.aus_datei(_FIXTURE)


# --------------------------------------------------------------------------
# Der Weg ueber den Namen
# --------------------------------------------------------------------------

def test_der_echte_bestand_traegt_vier_anbieter(echt):
    """Das Abnahmekriterium der Phase 6, gegen die Datei gemessen.

    Nicht gegen die Konfiguration: eine konfigurierte Quelle, die nichts
    liefert, ist kein Anbieter im Bestand. Genau so wurde die Telekom zwei
    Monate lang als erfasst gefuehrt.
    """
    anbieter = {s["anbieter"] for s in echt.saetze()}
    assert len(anbieter) >= 3, anbieter
    assert {"Telekom", "Vodafone", "congstar", "o2"} <= anbieter


@pytest.mark.parametrize("anbieter,referenz,erwartet", [
    ("Telekom", "MagentaMobil L", "telekom:magentamobil-l"),
    # Der Klammerzusatz ist eine Einordnung des Blattes, kein Produktname.
    ("Telekom", "MagentaMobil L (Mobilfunk)", "telekom:magentamobil-l"),
    ("Vodafone", "Vodafone Mobil M", "vodafone:vodafone-mobil-m"),
    # Auf der Produktseite steht der Anbietername nicht noch einmal.
    ("Vodafone", "Mobil M", "vodafone:vodafone-mobil-m"),
    # congstar schreibt "(Postpaid Mobilfunk)" ins Blatt.
    ("congstar", "Allnet Flat L", "congstar:allnet-flat-l"),
])
def test_echte_tarifnamen_treffen(echt, anbieter, referenz, erwartet):
    bezug = echt.ueber_namen(anbieter, referenz)
    assert bezug is not None, f"{anbieter} / {referenz}"
    assert bezug.tarif_id == erwartet
    assert bezug.guete == HOCH and bezug.belastbar


def test_ein_tarif_den_es_nicht_gibt_loest_nicht_auf(echt):
    """"GigaMobil M" ist Vodafones ALTE Portfolio-Bezeichnung.

    Eine Zuordnung auf den naechstbesten Tarif waere hier das Schlimmste,
    was passieren kann: die TCO truege dann einen fremden Grundpreis, und
    niemand saehe es der Zahl an.
    """
    assert echt.ueber_namen("Vodafone", "GigaMobil M") is None


def test_ein_leerer_name_ist_keine_referenz(echt):
    assert echt.ueber_namen("Telekom", "") is None
    assert echt.ueber_namen("Telekom", "   ") is None


# --------------------------------------------------------------------------
# Der Weg ueber den Betrag - Guete `mittel`, nie `hoch`
# --------------------------------------------------------------------------

def test_ein_eindeutiger_betrag_gibt_guete_mittel():
    """Das Abnahmekriterium: Betragszuordnung ist `mittel`, nie `hoch`.

    Der Betrag ist nur innerhalb DIESES Bestands eindeutig. Der Anbieter
    fuehrt mehr Tarife, als das Projekt liest; ein zweiter mit demselben
    Preis machte die Zuordnung falsch, ohne dass sich hier etwas aendert.
    Genau dieser Unterschied ist `mittel`.
    """
    bestand = Tarifbestand([
        _satz("Vodafone", "Tarif A", 41.95),
        _satz("Vodafone", "Tarif B", 29.95),
    ])
    bezug = bestand.ueber_betrag("Vodafone", 41.95)
    assert bezug == Bezug(tarif_id=tarif_id("Vodafone", "Tarif A"),
                          tarif_name="Tarif A", guete=MITTEL,
                          grund=bezug.grund)
    assert bezug.guete == MITTEL
    assert not bezug.belastbar
    # Und die Gegenprobe im selben Test: ueber den NAMEN waere es `hoch`.
    # Ohne sie bewiese der Test nur, dass irgendetwas `mittel` ist.
    assert bestand.ueber_namen("Vodafone", "Tarif A").guete == HOCH


def test_zwei_tarife_mit_demselben_preis_ergeben_keine_zuordnung():
    """Zwei Treffer sind keine schwache Zuordnung, sondern gar keine.

    Das ist am 04.09.2026 der reale Fall: Vodafone veroeffentlicht jeden
    Tarif zweimal - einmal ohne und einmal mit Geraetestaffel -, beide mit
    demselben Grundpreis. Ein Betrag trifft dort also regelmaessig zwei
    Datensaetze.
    """
    bestand = Tarifbestand([
        _satz("Vodafone", "Vodafone Mobil M", 49.95),
        _satz("Vodafone", "Vodafone Mobil M mit Smartphone", 49.95),
    ])
    assert bestand.ueber_betrag("Vodafone", 49.95) is None


def test_ein_betrag_der_nicht_vorkommt_wird_nicht_gerundet():
    """31,45 EUR gegen 31,95 EUR im Bestand - "fast" ist keine Zuordnung.

    Der gemessene Fall: Vodafones Geraetenutzlast nennt 41,95 und 31,45
    EUR, und 31,45 steht in keinem der gelesenen Blaetter.
    """
    bestand = Tarifbestand([_satz("Vodafone", "XS", 31.95)])
    assert bestand.ueber_betrag("Vodafone", 31.45) is None
    assert bestand.ueber_betrag("Vodafone", 31.95) is not None


def test_der_betrag_eines_anderen_anbieters_zaehlt_nicht():
    """Sonst truege ein o2-Geraet den Grundpreis eines Telekom-Tarifs."""
    bestand = Tarifbestand([_satz("Telekom", "MagentaMobil L",
                                  59.95)])
    assert bestand.ueber_betrag("o2", 59.95) is None


def test_der_name_schlaegt_den_betrag():
    """Eine Messung wird nicht durch eine Wahrscheinlichkeit ersetzt."""
    bestand = Tarifbestand([
        _satz("Telekom", "MagentaMobil L", 59.95),
        _satz("Telekom", "Ein anderer", 12.34),
    ])
    bezug = bestand.loese("Telekom", "MagentaMobil L", betrag=12.34)
    assert bezug.tarif_id == "telekom:magentamobil-l" and bezug.guete == HOCH


def test_ohne_namen_bleibt_der_betrag():
    bestand = Tarifbestand([_satz("Telekom", "Ein anderer",
                                  12.34)])
    bezug = bestand.loese("Telekom", "", betrag=12.34)
    assert bezug.tarif_id == tarif_id("Telekom", "Ein anderer")
    assert bezug.guete == MITTEL


# --------------------------------------------------------------------------
# Der Bestand als Zeitreihe
# --------------------------------------------------------------------------

def test_von_zwei_staenden_desselben_tarifs_gilt_der_letzte():
    """`tarife.jsonl` ist eine Zeitreihe, keine Tabelle.

    Ein Tarif steht mehrfach darin, einmal je Fassung - die aeltere Fassung
    ist kein zweiter Tarif. Ohne diese Regel meldete die Betragssuche bei
    jedem geaenderten Preis "nicht eindeutig".
    """
    bestand = Tarifbestand([
        _satz("Telekom", "MagentaMobil L", 54.95),
        _satz("Telekom", "MagentaMobil L", 59.95),
    ])
    assert len(bestand) == 1
    assert bestand.ueber_betrag("Telekom", 59.95) is not None
    assert bestand.ueber_betrag("Telekom", 54.95) is None


def test_eine_kaputte_zeile_kostet_nicht_den_bestand(tmp_path):
    p = tmp_path / "tarife.jsonl"
    p.write_text('{"tarif_id":"a","anbieter":"o2","name":"A"}\nkaputt\n\n',
                 encoding="utf-8")
    assert len(Tarifbestand.aus_datei(p)) == 1


def test_eine_fehlende_datei_ist_ein_leerer_bestand(tmp_path):
    assert len(Tarifbestand.aus_datei(tmp_path / "gibtsnicht.jsonl")) == 0


# --------------------------------------------------------------------------
# Die SIM-only-Referenzen aus dem Bestand
# --------------------------------------------------------------------------

def test_der_echte_bestand_ergibt_referenzen_mit_belegtem_preis(echt):
    """Der Massstab, den Phase 6 liefert.

    Jede Referenz traegt ihren Dokumentlink - das ist der Beleg, und ohne
    ihn waere die Zahl eine Behauptung.
    """
    referenzen = aus_bestand(echt)
    assert len(referenzen) >= 20
    assert all(isinstance(r, SimOnlyReferenz) for r in referenzen)
    assert all(r.tarif_sim_only_monatlich is not None for r in referenzen)
    assert all(r.quelle_url.startswith("http") for r in referenzen)
    assert all(r.tarif_id for r in referenzen)


def test_ein_festnetztarif_ist_kein_massstab_fuer_ein_smartphone():
    bestand = Tarifbestand([
        _satz("o2", "O2 Home L", 44.99, art="festnetz"),
        _satz("o2", "O2 Mobile M", 39.99, art="mobilfunk"),
    ])
    ids = {r.tarif_id for r in aus_bestand(bestand)}
    assert ids == {tarif_id("o2", "O2 Mobile M")}


def test_ein_tarif_ohne_preis_hat_keine_referenz():
    bestand = Tarifbestand([_satz("X", "Ohne Preis", None)])
    assert aus_bestand(bestand) == []


def test_die_erste_preisphase_gilt_und_nicht_ihr_durchschnitt():
    """Bei einer Rabattphase ist der Einstiegspreis der Preis.

    Vodafones Blatt zeichnet die Phasen selbst aus ("Monat 1-24" / "ab
    Monat 25"). Steht dort einmal eine echte Staffelung, ist der Mittelwert
    beider Phasen eine Zahl, die auf keinem Dokument steht.
    """
    bestand = Tarifbestand([_satz(
        "Vodafone", "Mobil M", 19.95,
        preisphasen=[{"von_monat": 1, "bis_monat": 6, "betrag": 19.95},
                     {"von_monat": 7, "bis_monat": None, "betrag": 49.95}])])
    assert aus_bestand(bestand)[0].tarif_sim_only_monatlich == 19.95


def test_ein_fehlender_anschlusspreis_bleibt_none_und_wird_nicht_null():
    """"Kein Anschlusspreis bekannt" heisst nicht "kostenlos"."""
    bestand = Tarifbestand([_satz("X", "A", 10.0)])
    assert aus_bestand(bestand)[0].anschlusspreis is None


def test_der_ausgelieferte_bestand_erfuellt_das_abnahmekriterium():
    """Phase 6: "`tarife.jsonl` enthaelt Tarife von mindestens drei Anbietern."

    Der EINZIGE Test, der die Betriebsdatei ansieht - und er prueft
    absichtlich nicht den Code, sondern den Bestand. Wird er rot, ist nicht
    eine Funktion kaputt, sondern das Kriterium nicht mehr erfuellt (etwa
    nach einem Baseline-Reset). Alles Verhalten haengt an der Fixture
    daneben.
    """
    zeilen = [json.loads(z) for z in
              _BESTAND.read_text(encoding="utf-8").splitlines() if z.strip()]
    assert all(z.get("tarif_id") for z in zeilen)
    assert len({z["anbieter"] for z in zeilen}) >= 3


def test_fixture_und_betriebsdatei_sind_dasselbe_format():
    """Sonst prueft die halbe Datei ein Format, das es nicht gibt.

    Die Fixture ist eine Kopie vom 04.09.2026 und darf im Aufbau nicht von
    der Datei abweichen, die der Sammler wirklich schreibt - dieselbe
    Ueberlegung wie beim Test, der PDF und Textfixture gegeneinander haelt.
    """
    def felder(pfad):
        zeilen = [json.loads(z) for z in
                  pfad.read_text(encoding="utf-8").splitlines() if z.strip()]
        return set().union(*(set(z) for z in zeilen)) if zeilen else set()
    assert felder(_FIXTURE) == felder(_BESTAND)


def test_das_geraeteblatt_eines_tarifs_ist_keine_zweite_referenz():
    """Vodafone veroeffentlicht jeden Tarif zweimal.

    "Vodafone Mobil M" und "Vodafone Mobil M mit Smartphone" nennen
    denselben Preis ohne Geraet - es ist derselbe Tarif, zweimal
    beschrieben. Als zwei Referenzen stuende derselbe Massstab zweimal
    untereinander mit demselben Betrag; das ist eine Dublette und keine
    Auskunft.
    """
    bestand = Tarifbestand([
        _satz("Vodafone", "Vodafone Mobil M", 49.95),
        _satz("Vodafone", "Vodafone Mobil M mit Smartphone", 49.95),
    ])
    namen = [r.tarif_name for r in aus_bestand(bestand)]
    assert namen == ["Vodafone Mobil M"]


def test_zwei_tarife_mit_demselben_preis_bleiben_zwei_referenzen():
    """Die Gegenprobe, und sie ist der Grund fuer die enge Fassung.

    "MagentaMobil S" und "MagentaMobil S Flex" kosten beide 39,95 EUR und
    sind trotzdem zwei Tarife - der eine mit Mindestlaufzeit, der andere
    ohne. Eine Regel ueber Namenspraefixe haette den zweiten geloescht.
    """
    bestand = Tarifbestand([
        _satz("Telekom", "MagentaMobil S", 39.95),
        _satz("Telekom", "MagentaMobil S Flex", 39.95),
    ])
    assert len(aus_bestand(bestand)) == 2


def test_das_geraeteblatt_bleibt_wenn_sein_preis_abweicht():
    """Gleicher Name plus Zusatz, aber anderer Betrag: zwei Aussagen."""
    bestand = Tarifbestand([
        _satz("Vodafone", "Vodafone Mobil M", 49.95),
        _satz("Vodafone", "Vodafone Mobil M mit Smartphone", 59.95),
    ])
    assert len(aus_bestand(bestand)) == 2


def test_der_echte_bestand_traegt_jeden_massstab_genau_einmal():
    """Gegen die Datei im Repo gemessen - keine Dublette im Massstab."""
    referenzen = aus_bestand(Tarifbestand.aus_datei(_FIXTURE))
    ids = [r.id for r in referenzen]
    assert len(ids) == len(set(ids))
    # Und die Vodafone-Geraeteblaetter sind wirklich draussen; ohne diese
    # Zeile bewiese der Test nur, dass IDs eindeutig sind.
    assert not [r for r in referenzen if "mit Smartphone" in r.tarif_name]


# --------------------------------------------------------------------------
# Nachtrag aus dem Review vom 04.09.2026
# --------------------------------------------------------------------------

@pytest.mark.parametrize("anbieter,referenz", [
    # Die Marke steht im Blatt, nicht auf der Produktseite (Vodafone).
    ("Vodafone", "Mobil M"),
    ("Vodafone", "Vodafone Mobil M"),
])
def test_die_marke_darf_auf_der_einen_seite_fehlen(echt, anbieter, referenz):
    assert echt.ueber_namen(anbieter, referenz) is not None


@pytest.mark.parametrize("anbieter,referenz,erwartet", [
    # ... und andersherum: im Blatt steht sie NICHT, auf der Produktseite
    # schon. Das ist bei Telekom und congstar der Regelfall - und genau die
    # Richtung, die die erste Fassung nicht aufloeste. Weil
    # `TcoDB.upsert_buendel` ohne `tarif_id` wirft, haette Phase 4 fuer
    # beide Anbieter keinen einzigen Buendelpreis speichern koennen.
    ("Telekom", "Telekom MagentaMobil L", "telekom:magentamobil-l"),
    ("congstar", "congstar Allnet Flat L", "congstar:allnet-flat-l"),
])
def test_die_marke_darf_auch_auf_der_anderen_seite_stehen(echt, anbieter,
                                                          referenz, erwartet):
    bezug = echt.ueber_namen(anbieter, referenz)
    assert bezug is not None, f"{anbieter} / {referenz}"
    assert bezug.tarif_id == erwartet


def test_die_marke_verbindet_keine_verschiedenen_tarife(echt):
    """Die Gegenprobe zur Praefix-Regel.

    Sie darf Schreibweisen zusammenfuehren, nicht Tarife. Ohne diese Zeile
    bewiese der Test darueber nur, dass die Regel etwas findet.
    """
    assert echt.ueber_namen("Telekom", "Telekom MagentaMobil XL") \
        .tarif_id == "telekom:magentamobil-xl"
    assert echt.ueber_namen("Telekom", "Telekom MagentaMobil Gibtsnicht") is None


def test_zwei_tarife_mit_derselben_titelzeile_ergeben_einen_massstab():
    """Live gemessen fuehrt o2 zwei PDFs mit derselben Ueberschrift.

    `SimOnlyReferenz.id` ist (Anbieter, Tarifname) und kann sie nicht
    trennen. Ohne die Sperre uebernaehme der Speicher den ZWEITEN Satz und
    behielte den Schluessel des ersten - die Zeile truege dann einen Betrag
    aus dem einen und einen `tarif_id` aus dem anderen Dokument.
    """
    ersterer = _satz("o2", "O2 Mobile L 175/250/300 Flex", 44.99)
    ersterer["dokument_url"] = "https://x.de/erstes.pdf"
    zweiter = _satz("o2", "O2 Mobile L 175/250/300 Flex", 54.99)
    zweiter["tarif_id"] += "#abcd1234"      # so trennt sie der Tarifspeicher
    zweiter["dokument_url"] = "https://x.de/zweites.pdf"
    referenzen = aus_bestand(Tarifbestand([ersterer, zweiter]))
    assert len(referenzen) == 1
    # Der ueberlebende Satz ist in sich stimmig: sein Betrag und sein
    # Beleg gehoeren zusammen.
    assert referenzen[0].tarif_sim_only_monatlich == 44.99
    assert referenzen[0].quelle_url == "https://x.de/erstes.pdf"


# --------------------------------------------------------------------------
# Der dritte Weg: der Slug, den der Anbieter selbst setzt
# --------------------------------------------------------------------------
# Er ist am 04.09.2026 dazugekommen, weil o2 seinen Buendeltarif anders
# nennt als seinen SIM-only-Tarif und weder Name noch Betrag die zwei
# verbinden. Verbunden werden sie von o2: die SIM-only-Kachel verlinkt
# unter "Handy hinzufügen" genau den Slug, den der Geraetekatalog am
# Buendel fuehrt.

_O2_KACHEL = dict(buendel_slug="o2-mobile-on-demand-m-plus")


def test_der_slug_loest_auf_wo_der_name_es_nicht_kann():
    bestand = Tarifbestand([
        _satz("o2", "O2 Mobile on Demand M", 19.99, **_O2_KACHEL)])
    katalogname = "O2 Mobile on Demand M Plus mit 50 GB+ (24 Mon.)"
    # Der Name trifft NICHT - und das ist richtig so: "M" und "M Plus"
    # sind verschiedene Zeichenketten, und eine Heuristik, die "Plus"
    # wegwirft, wuerfe beim naechsten Tarif etwas Bedeutungstragendes weg.
    assert bestand.ueber_namen("o2", katalogname) is None
    bezug = bestand.loese("o2", katalogname,
                          slug="o2-mobile-on-demand-m-plus")
    assert bezug is not None
    assert bezug.tarif_id == "o2:o2-mobile-on-demand-m"
    assert bezug.guete == HOCH and bezug.belastbar
    assert "Handy" not in bezug.grund      # der Grund nennt die Sache, nicht den Knopf
    assert "o2-mobile-on-demand-m-plus" in bezug.grund


def test_der_name_gewinnt_ueber_den_slug():
    """Das Blatt schlaegt die Produktordnung des Shops.

    Beides ist belegt; das Pflichtdokument ist die staerkere Quelle.
    """
    bestand = Tarifbestand([
        _satz("o2", "O2 Mobile L", 24.99, buendel_slug="o2-mobile-l-plus"),
        _satz("o2", "O2 Mobile L Plus", 29.99,
              buendel_slug="o2-mobile-l-plus-2")])
    bezug = bestand.loese("o2", "O2 Mobile L Plus", slug="o2-mobile-l-plus")
    assert bezug.tarif_id == "o2:o2-mobile-l-plus"
    assert "Produktinformationsblatt" in bezug.grund


def test_zwei_tarife_mit_demselben_slug_loesen_nicht_auf():
    """Zwei Treffer sind keine schwache Zuordnung, sondern gar keine -
    dieselbe Regel wie beim Betrag."""
    bestand = Tarifbestand([
        _satz("o2", "O2 Mobile L", 24.99, buendel_slug="o2-mobile-l-plus"),
        _satz("o2", "O2 Mobile L Zweitfassung", 24.99,
              buendel_slug="o2-mobile-l-plus")])
    assert bestand.ueber_slug("o2", "o2-mobile-l-plus") is None


def test_der_slug_gilt_nur_innerhalb_des_anbieters():
    bestand = Tarifbestand([
        _satz("o2", "O2 Mobile L", 24.99, buendel_slug="o2-mobile-l-plus")])
    assert bestand.ueber_slug("Vodafone", "o2-mobile-l-plus") is None


def test_ein_leerer_slug_loest_nichts_auf():
    """Sonst traefe jeder Bestandssatz ohne Slug jede Anfrage ohne Slug."""
    bestand = Tarifbestand([_satz("o2", "O2 Mobile L", 24.99)])
    assert bestand.ueber_slug("o2", "") is None
    assert bestand.ueber_slug("o2", "   ") is None
    assert bestand.loese("o2", "Gibtsnicht", slug="") is None


def test_der_slug_kommt_vor_dem_betrag():
    """Ein Betrag ist ein schwacher Schluessel - der Slug ist eine Angabe."""
    bestand = Tarifbestand([
        _satz("o2", "O2 Mobile on Demand M", 19.99, **_O2_KACHEL),
        _satz("o2", "O2 Mobile S", 14.99)])
    bezug = bestand.loese("o2", "Gibtsnicht", betrag=14.99,
                          slug="o2-mobile-on-demand-m-plus")
    assert bezug.tarif_id == "o2:o2-mobile-on-demand-m"
    assert bezug.guete == HOCH
