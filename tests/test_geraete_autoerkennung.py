# -*- coding: utf-8 -*-
"""E4 Auto-Erkennung: neue Katalog-Eintraege aus strukturierten Live-Namen.

Beleg ist der Telekom-Tageslauf vom 15.09.2026: die Kategorieseite lieferte
die Geraete „iPhone 18 Pro" (variantSlug polar-256-gb, zusammengesetzter
Titel „iPhone 18 Pro 256 GB polar") und „iPhone 18 Pro Max" strukturiert;
beide wurden als „Titel ohne Katalogtreffer" protokolliert und verworfen.
Antonios Wortlaut dazu in AUFTRAG_GERAETE_EINE_SEITE_V2.md §9a: „Das muss
automatisch gehen."

Die Nutzlast unten folgt Feld fuer Feld der gespeicherten echten Abrufs
tests/fixtures/geraete/telekom_kategorie_smartphones_ohne_vertrag.html.gz
(04.09.2026, Herkunft in _herkunft.json); Namen und variantSlugs sind die
protokollierten des 15.09.-Laufs, die Ratenformen sind so gewaehlt, dass
die probe_geht_auf aufgeht. Titel-Heuristik fuer HTML-Seiten (Option a)
bleibt verworfen: Ausloeser ist allein das strukturierte Namensfeld
(`strukturierter_name`), das nur Telekom `name`, o2 `description` und
Vodafone `modelName` setzen.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from telco_radar.collect.geraete import (
    autoerkennung, o2, sammle_anbieter, telekom, vodafone,
)
from telco_radar.collect.geraete.robots import RobotsWaechter
from telco_radar.geraete_config import Anbieter, Einstieg
from telco_radar.geraete_model import (
    Geraet, Katalog, device_id, erkenne_geraet,
)

_TELEKOM_URL = "https://www.telekom.de/shop/geraete/smartphones/ohne-vertrag"
_HEUTE = "2026-09-15"
_FIX = Path(__file__).parent / "fixtures" / "geraete"


def _eintrags(name, slug, rate, gesamt, gid):
    return {"id": gid, "name": name, "variantSlug": slug,
            "availabilityStatus": "IN_STOCK",
            "price": {"upfrontPrice": 0,
                      "installments": [{"numberOfInstallments": 36,
                                        "recurringPrice": rate,
                                        "totalPrice": gesamt}]}}


def _telekom_html(*eintraege):
    daten = {"productList": {"data": list(eintraege)}}
    return ('<script>window.__INITIAL_STATE__ = '
            + json.dumps(daten) + ';</script>')


# Der 15.09.-Beleg: das iPhone-Duo, das der Katalog noch nicht kannte.
_BELEG_HTML = _telekom_html(
    _eintrags("iPhone 18 Pro", "polar-256-gb", 40.0, 1440.0, "hw-18-pro"),
    _eintrags("iPhone 18 Pro Max", "schwarz-512-gb", 45.0, 1620.0,
              "hw-18-pro-max"),
)


def _mini_katalog() -> Katalog:
    """Hand-Katalog OHNE das iPhone 18 - der Zustand vom 15.09.2026.

    Die Serie „iPhone" ist bei Apple bekannt: genau daran haengt der
    Serien-Anker, der einen Namen OHNE Hersteller-Praefix (Telekom nennt
    kein „Apple" im name-Feld der 15.09.-Antwort) trotzdem eindeutig
    Apple zuordnet.
    """
    return Katalog(geraete=[
        Geraet(hersteller="Apple", modell="iPhone 17",
               marktstart="2025-09-19", generation=17, speicher=[128, 256]),
        Geraet(hersteller="Apple", modell="iPhone 16", generation=16),
        # Ein Xiaomi-Modell, damit „Xiaomi" als Hersteller-Praefix bekannt
        # ist (die Schaellung kennt nur Katalog-Hersteller - nichts geraten).
        Geraet(hersteller="Xiaomi", modell="Redmi Note 17", generation=17),
    ])


def _anbieter() -> Anbieter:
    return Anbieter(name="Telekom", typ="netzbetreiber",
                    methode="telekom_kategorie",
                    basis_url="https://www.telekom.de",
                    einstiege=[Einstieg(url=_TELEKOM_URL, label="ohne Vertrag")],
                    rate_limit_sekunden=0)


def _hole(html):
    def hole(url, kopfzeilen=None, user_agent=None):
        if url.endswith("/robots.txt"):
            return (200, "User-agent: *\n")
        return (200, html)
    return hole


def _sammle(html, katalog):
    return sammle_anbieter(_anbieter(), katalog, {}, _hole(html), _HEUTE,
                           RobotsWaechter(hole=_hole(html)),
                           datetime(2026, 9, 15, 3, tzinfo=timezone.utc))


# ==========================================================================
# Der Beleg-Fall, Ende zu Ende (rot vor gruen bewiesen)
# ==========================================================================

def test_beleg_iphone_18_duo_wird_automatisch_angelegt():
    """Der 15.09.-Lauf, nachgebaut: statt Verwurf + Protokollzeile
    entstehen Katalog-Eintraege, und die Listungen sind SOFORT dabei -
    die Launch-Preishistorie beginnt mit Tag 1."""
    katalog = _mini_katalog()
    bilanz = _sammle(_BELEG_HTML, katalog)

    assert bilanz.status == "ok"
    # ZWEI Eintraege: „Pro Max" ist ein eigenes Geraet, kein Modellzusatz
    # des schon angelegten „Pro" (die _MODELLZUSATZ-Sperre haette beide
    # unter „iPhone 18 Pro" verschmolzen - dieselbe Falle wie „Pixel 10
    # Pro Fold" gegen „Pixel 10 Pro").
    ids = sorted(l.device_id for l in bilanz.listungen)
    erwartung = sorted([device_id("Apple", "iPhone 18 Pro"),
                        device_id("Apple", "iPhone 18 Pro Max")])
    assert ids == erwartung

    eintrag = katalog.nach_id(device_id("Apple", "iPhone 18 Pro"))
    assert eintrag is not None
    # Der Marker: ISO-Datum des anlegenden Laufs.
    assert eintrag.auto == _HEUTE
    # NICHTS wird geraten: marktstart und vorgaenger bleiben leer (ein
    # leeres marktstart schaltet die Nachfolger-Analyse ab - ein geratenes
    # Datum waere schlimmer, CLAUDE.md-Katalogregel).
    assert eintrag.marktstart == ""
    assert eintrag.vorgaenger == ""
    # generation NUR bei eindeutiger Serie: „iPhone" ist als Apple-Serie im
    # Katalog bekannt, die Zahl innerhalb der Serie ist 18.
    assert eintrag.generation == 18
    assert katalog.nach_id(device_id("Apple", "iPhone 18 Pro Max")).auto \
        == _HEUTE


def test_beleg_titel_steht_nicht_mehr_in_der_arbeitsliste():
    """Der Verwurf war der Befund: dieselbe Nutzlast darf die Titel nicht
    mehr als ‚ohne Katalogtreffer' melden, wenn ein Eintrag entstand."""
    katalog = _mini_katalog()
    bilanz = _sammle(_BELEG_HTML, katalog)
    assert "iPhone 18 Pro 256 GB polar" not in bilanz.unbekannte_titel
    assert "iPhone 18 Pro Max 512 GB schwarz" not in bilanz.unbekannte_titel
    assert bilanz.listungen


def test_beleg_listung_traegt_speicher_und_farbe():
    """Speicher und Farbe kommen aus den strukturierten Feldern der
    Nutzlast (variantSlug), nicht aus einer Titel-Schaetzung - und die
    unbekannte Farbe bleibt Rohschreibweise (Arbeitsliste farben.yaml)."""
    katalog = _mini_katalog()
    bilanz = _sammle(_BELEG_HTML, katalog)
    pro = [l for l in bilanz.listungen if l.speicher_gb == 256]
    assert len(pro) == 1 and pro[0].farbe_roh == "polar"
    # Der Auto-Eintrag kennt die gemessene Stufe: sie ist der Filter, gegen
    # den ein spaeterer Titel ohne strukturiertes Speicherfeld gelesen wird.
    assert katalog.nach_id(device_id("Apple", "iPhone 18 Pro")).speicher \
        == [256]


# ==========================================================================
# Die Regeln der Anlage
# ==========================================================================

def test_hand_eintrag_schlaegt_auto():
    """Steht das Geraet als Hand-Eintrag im Katalog, wird KEIN zweiter
    angelegt - die Listung trifft den Hand-Eintrag, und der Katalog bleibt
    Hand-befaehrt (derselbe Lauf legt nur an, was niemand gepflegt hat)."""
    katalog = _mini_katalog()
    hand = Geraet(hersteller="Apple", modell="iPhone 18 Pro",
                  marktstart="2026-09-19", generation=18)
    katalog.ergaenze(hand)
    # Nur das Pro-Geraet: der Pro Max steht weiterhin NICHT im Katalog und
    # wuerde die Aussage verwaessernn (er wird zu Recht auto-angelegt).
    html = _telekom_html(
        _eintrags("iPhone 18 Pro", "polar-256-gb", 40.0, 1440.0, "hw-18-pro"))
    bilanz = _sammle(html, katalog)

    assert [g for g in katalog.geraete if g.auto] == []
    pro = [l for l in bilanz.listungen
           if l.device_id == device_id("Apple", "iPhone 18 Pro")]
    assert len(pro) == 1
    assert hand.marktstart == "2026-09-19" and hand.auto == ""


def test_zubehoer_wird_nicht_angelegt():
    """Ein Zubehoername bleibt Zubehoer: kein Katalog-Eintrag, der Titel
    als Arbeitsliste (derselbe Schutz wie erkenne_geraet)."""
    katalog = _mini_katalog()
    html = _telekom_html(
        _eintrags("Ladekabel fuer iPhone 18 Pro", "weiss-0-gb", 1.0, 36.0,
                  "hw-kabel"))
    bilanz = _sammle(html, katalog)
    assert bilanz.listungen == []
    assert any("Ladekabel" in t for t in bilanz.unbekannte_titel)
    assert [g for g in katalog.geraete if g.auto] == []


def test_unbekannter_hersteller_ohne_anker_wird_nicht_geraten():
    """Ein Name, dessen Hersteller weder als Praefex noch als Serie im
    Katalog bekannt ist, wird NICHT angelegt - geraten wird nichts."""
    katalog = _mini_katalog()
    html = _telekom_html(
        _eintrags("FooPhone X200", "grau-128-gb", 1.0, 36.0, "hw-foo"))
    bilanz = _sammle(html, katalog)
    assert bilanz.listungen == []
    assert [g for g in katalog.geraete if g.auto] == []


def test_hersteller_pruefix_wird_geschaelt():
    """„Apple iPhone 18 Pro" (Schreibweise der 04.09.-Antwort) -> Hersteller
    Apple, Modell ohne das Praefix - konsistent zur Schreibweise der
    Hand-Eintraege („iPhone 17", nicht „Apple iPhone 17")."""
    katalog = _mini_katalog()
    html = _telekom_html(
        _eintrags("Apple iPhone 18 Air", "weiss-256-gb", 30.0, 1080.0,
                  "hw-air"))
    bilanz = _sammle(html, katalog)
    eintrag = katalog.nach_id(device_id("Apple", "iPhone 18 Air"))
    assert eintrag is not None and eintrag.auto == _HEUTE
    # „Air" traegt keine Zahl innerhalb einer NEUEN Serie? Doch: die Serie
    # ist „iPhone" und bekannt - die Zahl ist 18. Aber der NAME dieser
    # Variante endet auf „Air" - generation bleibt die der Serie.
    assert eintrag.generation == 18


def test_neue_serie_ohne_zahl_bekommt_keine_generation():
    """Ein Hersteller-Pruefix allein reicht fuer die Anlage - aber ohne
    bekannte Serie gibt es KEINE generation (nichts geraten)."""
    katalog = _mini_katalog()
    html = _telekom_html(
        _eintrags("Xiaomi NeueReihe X1", "blau-128-gb", 10.0, 360.0,
                  "hw-x1"))
    _sammle(html, katalog)
    eintrag = katalog.nach_id(device_id("Xiaomi", "NeueReihe X1"))
    assert eintrag is not None
    assert eintrag.generation is None
    assert eintrag.marktstart == "" and eintrag.vorgaenger == ""


def test_wortmarken_kollision_verhindert_die_anlage():
    """Zwei Auto-Kandidaten, deren normalisierte Schreibweisen nicht
    unterscheidbar sind, legen NICHT an (derselbe Schutz, der den Hand-
    Katalog wirft) - der Titel geht in die Arbeitsliste."""
    katalog = _mini_katalog()
    assert autoerkennung.lege_an("iPhone 18 Pro", katalog, _HEUTE, speicher_gb=256) is not None
    # „iPhone 18 Pro" noch einmal: keine zweite Anlage, derselbe Eintrag.
    zweite = autoerkennung.lege_an("iPhone 18 Pro", katalog, _HEUTE, speicher_gb=512)
    assert zweite.device_id == device_id("Apple", "iPhone 18 Pro")
    assert len([g for g in katalog.geraete if g.auto]) == 1
    # Die zweite Stufe erweitert die speicher-Liste DES Auto-Eintrags.
    assert sorted(katalog.nach_id(device_id("Apple", "iPhone 18 Pro")).speicher) \
        == [256, 512]


# ==========================================================================
# Persistenz
# ==========================================================================

def test_unbekannte_titel_und_farben_werden_gezaehlt(tmp_path):
    """data/state/geraete_unbekannt.jsonl: eine Zeile je Titel bzw. Farbe,
    mit Anbieter, Quelle des Feldes und Haeufigkeit - angelegt und erweitert
    vom Lauf, nicht von Hand."""
    eintraege = [{"art": "titel", "wert": "FooPhone X200",
                  "anbieter": "Telekom", "quelle": "telekom_kategorie"},
                 {"art": "farbe", "wert": "polar",
                  "anbieter": "Telekom", "quelle": "telekom_kategorie"}]
    autoerkennung.persistiere_unbekannte(tmp_path, eintraege, _HEUTE)
    autoerkennung.persistiere_unbekannte(tmp_path, eintraege[:1], _HEUTE)

    datei = tmp_path / "data" / "state" / "geraete_unbekannt.jsonl"
    zeilen = [json.loads(z) for z in datei.read_text().splitlines() if z]
    assert len(zeilen) == 2
    titel = [z for z in zeilen if z["art"] == "titel"][0]
    farbe = [z for z in zeilen if z["art"] == "farbe"][0]
    assert titel["haeufigkeit"] == 2 and titel["datum"] == _HEUTE
    assert titel["anbieter"] == "Telekom"
    assert titel["quelle"] == "telekom_kategorie"
    assert farbe["haeufigkeit"] == 1


def test_unbekannte_datei_fehlt_ist_kein_fehler(tmp_path):
    autoerkennung.persistiere_unbekannte(tmp_path, [], _HEUTE)
    assert not (tmp_path / "data" / "state" / "geraete_unbekannt.jsonl").exists()


def test_auto_zusaetze_ueberleben_den_neustart(tmp_path):
    """Der Auto-Katalog ist ein STATE: beim naechsten Lauf wird er mit
    geladen - ein Geraet wird nicht jeden Lauf neu angelegt (die
    device_id waere zwar stabil, der Marker und die Speicherliste aber
    nicht)."""
    katalog = _mini_katalog()
    autoerkennung.lege_an("iPhone 18 Pro", katalog, _HEUTE, speicher_gb=256)
    autoerkennung.speichere_auto_zusaetze(tmp_path, katalog)

    frisch = _mini_katalog()
    autoerkennung.lade_auto_zusaetze(tmp_path, frisch)
    eintrag = frisch.nach_id(device_id("Apple", "iPhone 18 Pro"))
    assert eintrag is not None and eintrag.auto == _HEUTE
    assert eintrag.speicher == [256]


def test_hand_schlaegt_auto_beim_laden(tmp_path):
    """Hat ein Mensch den Eintrag zwischenzeitlich in die Config
    uebernommen, gewinnt der Hand-Eintrag - der State-Eintrag wird
    verworfen, nicht doppelt angelegt."""
    katalog = _mini_katalog()
    autoerkennung.lege_an("iPhone 18 Pro", katalog, _HEUTE, speicher_gb=256)
    autoerkennung.speichere_auto_zusaetze(tmp_path, katalog)

    # Der Mensch pflegt dasselbe Geraet von Hand in die Config.
    hand_besitzend = _mini_katalog()
    hand_besitzend.ergaenze(Geraet(hersteller="Apple", modell="iPhone 18 Pro",
                                   marktstart="2026-09-19", generation=18))
    autoerkennung.lade_auto_zusaetze(tmp_path, hand_besitzend)
    treffer = hand_besitzend.nach_id(device_id("Apple", "iPhone 18 Pro"))
    assert treffer.marktstart == "2026-09-19" and treffer.auto == ""
    assert len([g for g in hand_besitzend.geraete if g.auto]) == 0


# ==========================================================================
# Nur strukturierte Felder loesen die Anlage aus
# ==========================================================================

def test_ohne_strukturiertes_namensfeld_gibt_es_keine_anlage():
    """Ein Titel allein (Option a) loest nichts aus: nur die drei Adapter
    mit strukturiertem Namensfeld setzen ‚strukturierter_name'."""
    katalog = _mini_katalog()
    satz = {"titel": "iPhone 18 Pro 256 GB polar", "farbe": "polar",
            "speicher_gb": 256, "quelle": "ldjson"}
    ergebnis = autoerkennung.lege_an(satz.get("strukturierter_name", ""),
                                     katalog, _HEUTE)
    assert ergebnis is None
    assert [g for g in katalog.geraete if g.auto] == []


def test_die_drei_adapter_nennen_ihr_namensfeld():
    """Telekom ‚name', o2 ‚description', Vodafone ‚modelName' - der
    strukturierte Name reist als eigenes Feld, getrennt vom
    zusammengesetzten Titel."""
    saetze = telekom.lies(_BELEG_HTML, _TELEKOM_URL)
    assert [s["strukturierter_name"] for s in saetze] \
        == ["iPhone 18 Pro", "iPhone 18 Pro Max"]

    # o2: der Name steht in `description`, der Titel wird daraus MIT
    # Speicher und Farbe aus dem Angebots-Slug zusammengesetzt.
    o2_json = json.dumps({"hardware": [{
        "description": "Apple iPhone 18 Pro",
        "offerName": "privatkunden-apple-iphone-18-pro-256gb-polar-24xhigh",
        "externalId": "o2-18-pro",
        "price": {"totalPrice": 1000.0},
    }]})
    o2_saetze = o2.lies(o2_json, "https://www.o2online.de/e-shop/")
    assert o2_saetze[0]["strukturierter_name"] == "Apple iPhone 18 Pro"
    assert o2_saetze[0]["titel"] == "Apple iPhone 18 Pro 256 GB polar"

    # Vodafone: der Name steht in `modelName` der Detailnutzlast.
    vf_json = json.dumps({"modelName": "APPLE IPHONE 18 PRO",
                          "hubpage": {"href": "/privat/handys/x.html"},
                          "atomics": [{
                              "hardwareId": "vf-18-pro",
                              "capacity": {"displayLabel": "256 GB"},
                              "color": {"displayLabel": "Polar"},
                              "prices": {"hardware": {"priceByType": {
                                  "rate": {"onetime": {
                                      "withoutDiscounts": {
                                          "gross": 1199.0}}}}}},
                          }]})
    vf_saetze = vodafone.lies(vf_json, "https://api.vodafone.de/x")
    assert vf_saetze[0]["strukturierter_name"] == "APPLE IPHONE 18 PRO"


# ==========================================================================
# Kollisionswaechter: die Modellzusatz-Falle (E4-Regeln, Bau 2)
# ==========================================================================

def _katalog_mit_pixel() -> Katalog:
    """_mini_katalog plus Google-Anker: die Serie „Pixel" ist damit als
    Google-Serie bekannt, und die Schaellung eines Namens ohne
    Hersteller-Praefix trifft sie."""
    katalog = _mini_katalog()
    katalog.ergaenze(Geraet(hersteller="Google", modell="Pixel 9",
                            generation=9, speicher=[128]))
    return katalog


def test_stamm_eines_hand_eintrags_wird_nicht_angelegt(caplog):
    """CLAUDE.md-Falle: „Pixel 10 Pro Fold" vs „Pixel 10 Pro". Ein
    Live-Katalog, der den STAMM eines gepflegten Hand-Eintrags nennt,
    verkuerzt den Namen moeglicherweise nur - genau dann waere die
    Auto-Anlage ein Phantom neben dem echten Geraet. Verworfen und
    protokolliert (der Verwurf ist die Katalog-Pflege-Aufgabe, nicht ein
    stiller Fall in die Arbeitsliste)."""
    import logging
    katalog = _katalog_mit_pixel()
    katalog.ergaenze(Geraet(hersteller="Google", modell="Pixel 10 Pro Fold",
                            marktstart="2026-05-15", generation=10))
    vorher = len(katalog.geraete)

    with caplog.at_level(logging.WARNING):
        ergebnis = autoerkennung.lege_an("Pixel 10 Pro", katalog, _HEUTE,
                                         speicher_gb=256)

    assert ergebnis is None
    assert len(katalog.geraete) == vorher
    assert "Pixel 10 Pro Fold" in caplog.text
    assert "nicht angelegt" in caplog.text


def test_zusatz_ueber_lebendem_hand_stamm_wird_angelegt():
    """Die Gegenrichtung ist der Belegfall des Auftrags (15.09.:
    „iPhone 18 Pro" UND „iPhone 18 Pro Max"): ein Live-Name, der einen
    MODELLZUSATZ ueber einem bestehenden Eintrag traegt, ist ein eigenes
    Geraet - ein Live-Katalog erweitert Namen nicht, er kuerzt allenfalls.
    Die Sperre duerfte NUR in der Stamm-Richtung greifen."""
    katalog = _mini_katalog()
    katalog.ergaenze(Geraet(hersteller="Apple", modell="iPhone 18 Pro",
                            generation=18, marktstart="2026-09-19"))
    ergebnis = autoerkennung.lege_an("iPhone 18 Pro Max", katalog, _HEUTE,
                                     speicher_gb=512)
    assert ergebnis is not None and ergebnis.auto == _HEUTE
    assert katalog.nach_id(device_id("Apple", "iPhone 18 Pro Max")) \
        is not None


def test_fuzzy_kollision_nur_gegen_hand_eintraege():
    """Pro und Pro Max erscheinen im SELBEN Lauf, und die Reihenfolge der
    Nutzlast ist nicht garantiert: laege die Sperre auch ueber
    Auto-Eintraegen, hinge der 15.09.-Beleg an der Satzreihenfolge - der
    Max zuerst genannt wuerde den Pro-Stamm sperren. Der Waechter prueft
    deshalb gegen den HAND-Katalog (der Auftrag: ein Hand-Eintrag schlaegt
    IMMER die Auto-Anlage), nicht gegen frisch Angelegte."""
    katalog = _mini_katalog()
    assert autoerkennung.lege_an("iPhone 18 Pro Max", katalog, _HEUTE,
                                 speicher_gb=512) is not None
    assert autoerkennung.lege_an("iPhone 18 Pro", katalog, _HEUTE,
                                 speicher_gb=256) is not None
    assert len([g for g in katalog.geraete if g.auto]) == 2


def test_hand_schlaegt_auto_auch_fuzzy_beim_laden(tmp_path, caplog):
    """Der Waechter gilt auch im MERGE: ein State-Auto-Eintrag, dessen Stamm
    zwischenzeitlich als Hand-Eintrag MIT ZUSATZ gepflegt wurde, wird beim
    Laden verworfen und protokolliert - der Mensch hat entschieden, dass
    es dieses Stamms als eigenes Geraet (noch) nicht gibt."""
    import logging
    katalog = _katalog_mit_pixel()
    assert autoerkennung.lege_an("Pixel 10", katalog, "2026-09-10",
                                 speicher_gb=128) is not None
    autoerkennung.speichere_auto_zusaetze(tmp_path, katalog)

    hand = _katalog_mit_pixel()
    hand.ergaenze(Geraet(hersteller="Google", modell="Pixel 10 Pro",
                         generation=10))
    with caplog.at_level(logging.INFO):
        autoerkennung.lade_auto_zusaetze(tmp_path, hand)

    assert [g for g in hand.geraete if g.auto] == []
    assert hand.nach_id(device_id("Google", "Pixel 10 Pro")).marktstart == ""
    assert "Pixel 10 Pro" in caplog.text


def test_verwurf_gleicher_device_id_beim_laden_protokolliert(tmp_path, caplog):
    """Auch der einfache Konflikt (gleiche device_id, Hand hat
    uebernommen) steht im Protokoll - ein stiller Verwurf waere beim
    Nachvollzug des Auto-Bestands unsichtbar."""
    import logging
    katalog = _mini_katalog()
    autoerkennung.lege_an("iPhone 18 Pro", katalog, _HEUTE, speicher_gb=256)
    autoerkennung.speichere_auto_zusaetze(tmp_path, katalog)

    hand = _mini_katalog()
    hand.ergaenze(Geraet(hersteller="Apple", modell="iPhone 18 Pro",
                         marktstart="2026-09-19", generation=18))
    with caplog.at_level(logging.INFO):
        uebernommen = autoerkennung.lade_auto_zusaetze(tmp_path, hand)

    assert uebernommen == 0
    assert "iPhone 18 Pro" in caplog.text
    assert len([g for g in hand.geraete if g.auto]) == 0


# ==========================================================================
# EINE Quelle der Wahrheit: lade_katalog merged die Auto-Eintraege
# ==========================================================================

def test_lade_katalog_liefert_den_gemergten_katalog(tmp_path):
    """Der Render-Pfad (report/html.py) laedt den Katalog ueber
    geraete_config.lade_katalog - ohne den Merge wuerde der Lauf Listungen
    zu einem Geraet schreiben, das die Seite nie rendert (derselbe Fehler
    wie der Navigationseintrag am 11.08.: gebaut, geprueft, unsichtbar).
    Pipeline UND Seite sehen denselben Bestand."""
    import yaml
    root = tmp_path / "mitte"
    (root / "config").mkdir(parents=True)
    (root / "config" / "geraete_katalog.yaml").write_text(
        yaml.safe_dump({"geraete": [
            {"hersteller": "Apple", "modell": "iPhone 17",
             "generation": 17, "speicher": [128]},
            {"hersteller": "Xiaomi", "modell": "Redmi Note 17"},
        ]}, allow_unicode=True), encoding="utf-8")

    vorlage = Katalog(geraete=[
        Geraet(hersteller="Apple", modell="iPhone 17", generation=17),
        Geraet(hersteller="Xiaomi", modell="Redmi Note 17"),
    ])
    autoerkennung.lege_an("iPhone 18 Pro", vorlage, _HEUTE, speicher_gb=256)
    autoerkennung.speichere_auto_zusaetze(root, vorlage)

    from telco_radar.geraete_config import lade_katalog
    geladen = lade_katalog(root)
    eintrag = geladen.nach_id(device_id("Apple", "iPhone 18 Pro"))
    assert eintrag is not None and eintrag.auto == _HEUTE
    assert geladen.nach_id(device_id("Apple", "iPhone 17")).auto == ""


# ==========================================================================
# E4-P1: Funk-Anhaengsel - dieselbe Nennung mit und ohne „5G"
# ==========================================================================
# o2 schreibt die Funkfaehigkeit in das description-Feld („Xiaomi Redmi
# Note 17 Pro Max 5G", tests/fixtures/geraete/o2_katalog.json); Telekom
# `name` und Vodafone `modelName` nennen dasselbe Geraet ohne Zusatz
# („Apple iPhone 17 Pro Max", „Google Pixel 11"). Im SELBEN Lauf schuetzt
# heute die Config-Reihenfolge - der Bruch kam ueber NAECHEST Naechte: legt
# o2 zuerst/allein an (der Telekom-202-Ausfall in Actions ist dokumentierte
# Realitaet) und nennt ein spaeterer strukturierter Anbieter das Geraet
# ohne Zusatz, entsteht der zweite Eintrag STILL, ohne Signal an die
# Arbeitsliste. Zwei device_ids fuer ein Geraet sind die Saegezahn-Klasse,
# gegen die die ganze ID-Regel gebaut ist.

def test_funk_anhang_wird_aus_dem_modellnamen_geschaelt():
    """Der Zusatz ist keine Identitaet: 5G/4G/LTE werden wie das
    Speichersegment aus dem Modellnamen geschaelt - aus beiden Nennungen
    wird dieselbe device_id, egal welcher Anbieter sie wie schreibt."""
    katalog = _mini_katalog()
    assert autoerkennung.schale("Xiaomi Redmi Note 18 Pro Max 5G", katalog) \
        == ("Xiaomi", "Redmi Note 18 Pro Max")
    assert autoerkennung.schale("Xiaomi Redmi Note 18 4G", katalog) \
        == ("Xiaomi", "Redmi Note 18")
    assert autoerkennung.schale("Xiaomi Redmi Note 18 LTE", katalog) \
        == ("Xiaomi", "Redmi Note 18")
    # Nennung OHNE Zusatz bleibt unberuehrt (Telekom `name`-Schreibweise).
    assert autoerkennung.schale("Redmi Note 18 Pro Max", katalog) \
        == ("Xiaomi", "Redmi Note 18 Pro Max")


def test_funk_variante_legt_kein_zweites_geraet_an():
    """Beide Richtungen der Naechte: legt o2 zuerst an und nennt ein
    spaeterer Anbieter das Geraet ohne Zusatz - oder umgekehrt -, entsteht
    EIN Eintrag, und die zweite Nacht erweitert die Speicherstufen
    desselben (statt ein Duplikat mit eigener Preishistorie)."""
    fuenf_g = "Xiaomi Redmi Note 18 Pro Max 5G"
    stamm = "Redmi Note 18 Pro Max"
    for erste, zweite in ((fuenf_g, stamm), (stamm, fuenf_g)):
        katalog = _mini_katalog()
        a = autoerkennung.lege_an(erste, katalog, "2026-09-17",
                                  speicher_gb=256)
        b = autoerkennung.lege_an(zweite, katalog, "2026-09-18",
                                  speicher_gb=512)
        assert a is not None and b is not None
        assert a.device_id == b.device_id \
            == device_id("Xiaomi", "Redmi Note 18 Pro Max")
        assert len([g for g in katalog.geraete if g.auto]) == 1
        assert sorted(a.speicher) == [256, 512]


def test_titel_ohne_funkzusatz_trifft_den_aus_funknennung_entstandenen_eintrag():
    """Solange nur der 5G-Eintrag existierte, matchte KEIN Haendlertitel
    ohne „5G" die laengere Nadel - das Geraet waere nur bei o2 beobachtbar
    gewesen, „Wer ist guenstiger" und Preisverlauf haetten gespalten."""
    katalog = _mini_katalog()
    autoerkennung.lege_an("Xiaomi Redmi Note 18 Pro Max 5G", katalog, _HEUTE,
                          speicher_gb=256)
    ohne = erkenne_geraet("Redmi Note 18 Pro Max 256 GB obsidian", katalog)
    mit = erkenne_geraet("Xiaomi Redmi Note 18 Pro Max 5G 256 GB obsidian",
                         katalog)
    assert ohne is not None and mit is not None
    assert ohne.device_id == mit.device_id \
        == device_id("Xiaomi", "Redmi Note 18 Pro Max")


_O2_URL = "https://www.o2online.de/e-shop/handy/"
_NACHT1, _NACHT2 = "2026-09-17", "2026-09-18"


def _o2_payload(description, slug, slug_gb, farbe, gid, preis):
    """Nutzlast im Format der gespeicherten o2-Antwort: der strukturierte
    Name steht in `description`, Speicher und Farbe im Angebotsslug (Muster
    „privatkunden-google-pixel-11-pro-xl-256gb-canyon-24xhigh")."""
    return json.dumps({"hardware": [{
        "description": description,
        "offerName": f"privatkunden-{slug}-{slug_gb}gb-{farbe}-24xhigh",
        "externalId": gid,
        "price": {"totalPrice": preis},
    }]})





def _sammle_anbieter_nacht(anbieter, payload, katalog, heute):
    return sammle_anbieter(
        anbieter, katalog, {}, _hole(payload), heute,
        RobotsWaechter(hole=_hole(payload)),
        datetime(2026, 9, 17, 3, tzinfo=timezone.utc))


def test_o2_nacht_mit_5g_und_telekom_nacht_ohne_bleiben_ein_geraet():
    """Der Beleg E2E (E4-P1, mit den echten Adaptern o2_katalog und
    telekom_kategorie): Nacht 1 legt o2 aus `description` („… 5G") an,
    Nacht 2 nennt die Telekom `name` ohne Zusatz. Beide Listungen laufen
    auf dieselbe device_id - vorher entstand der zweite Eintrag still, und
    unbekannte_titel blieb leer (kein Signal an die Arbeitsliste)."""
    katalog = _mini_katalog()
    o2_anbieter = Anbieter(
        name="o2", typ="netzbetreiber", methode="o2_katalog",
        basis_url="https://www.o2online.de",
        einstiege=[Einstieg(url=_O2_URL)], rate_limit_sekunden=0)

    nacht1 = _sammle_anbieter_nacht(
        o2_anbieter,
        _o2_payload("Xiaomi Redmi Note 18 Pro Max 5G",
                    "xiaomi-redmi-note-18-pro-max", 256, "obsidian",
                    "o2-note18pm", 899.0),
        katalog, _NACHT1)
    assert nacht1.status == "ok"
    assert [l.device_id for l in nacht1.listungen] \
        == [device_id("Xiaomi", "Redmi Note 18 Pro Max")]

    html = _telekom_html(
        _eintrags("Redmi Note 18 Pro Max", "obsidian-256-gb", 25.0, 900.0,
                  "hw-note18pm"))
    nacht2 = _sammle_anbieter_nacht(_anbieter(), html, katalog, _NACHT2)
    assert nacht2.status == "ok"
    assert [l.device_id for l in nacht2.listungen] \
        == [device_id("Xiaomi", "Redmi Note 18 Pro Max")]
    assert nacht2.unbekannte_titel == []

    autos = [g for g in katalog.geraete if g.auto]
    assert len(autos) == 1
    assert autos[0].modell == "Redmi Note 18 Pro Max"
    assert sorted(autos[0].speicher) == [256]


def test_stamm_eines_hand_eintrags_mit_funkzusatz_wird_nicht_angelegt(caplog):
    """Hand schlaegt Auto auch in der Funk-Variante: ist der Hand-Eintrag
    MIT Zusatz gepflegt („Galaxy A13 5G" ist real ein eigenes Geraet),
    legt eine Nennung ohne Zusatz kein Phantom daneben an - der Verwurf
    steht im Protokoll, und die Katalog-Pflege entscheidet (dieselbe
    Stamm-Richtung wie die Modellzusatz-Falle)."""
    import logging
    katalog = _mini_katalog()
    katalog.ergaenze(Geraet(hersteller="Xiaomi", modell="Redmi Note 18 5G",
                            generation=18))
    vorher = len(katalog.geraete)

    with caplog.at_level(logging.WARNING):
        ergebnis = autoerkennung.lege_an("Xiaomi Redmi Note 18", katalog,
                                         _HEUTE, speicher_gb=128)

    assert ergebnis is None
    assert len(katalog.geraete) == vorher
    assert "Redmi Note 18 5G" in caplog.text
    assert "nicht angelegt" in caplog.text


# ==========================================================================
# P5/E3: Tarif-Rauschen aus der Arbeitsliste (FM 1 - Fruehindikator)
# ==========================================================================
# ALDI TALK liefert je Lauf drei Tarifpakete als „Geraet" in den strukturierten
# Daten mit („Tarif S", „Tarif M", „Tarif L", quelle microdata). Am 17.09.2026
# standen sie als 3 Zeilen mit Haeufigkeitssumme 87 von 284 in
# data/state/geraete_unbekannt.jsonl (je 29 Zaehlungen - der Auftrag nennt
# „87 von 284 Zeilen" und meint diese Vorkommen). Die Liste ist der
# Fruehindikator fuer Anker-Luecken (FM 1); Rauschen macht sie taub. Alle
# Titel dieser Sektion sind die gespeicherten ECHTEN der Datei vom 17.09. -
# einzeln hierher kopiert und als Ganzes als Fixture
# tests/fixtures/geraete/unbekannte_titel_2026-09-17.jsonl (145 Titel-Zeilen,
# Herkunft in _herkunft.json). NICHTS ist erfunden.

def test_tarif_titel_erkennen():
    """Die Regel selbst, an den echten Werten: Wort ‚Tarif' UND keine Ziffer.
    Der einzige ziffernlose Geraetetitel des Bestands (Oakley, ld+json von
    mobilcom-debitel) traegt das Wort ‚Tarif' nicht - die UND-Verknuepfung
    haelt ihn drin."""
    assert autoerkennung.ist_tarif_titel("Tarif S")
    assert autoerkennung.ist_tarif_titel("Tarif M")
    assert autoerkennung.ist_tarif_titel("Tarif L")
    # Echte Geraetetitel der selben Liste bleiben stehen - auch die von
    # ALDI TALK selbst (derselbe Anbieter wie das Rauschen).
    assert not autoerkennung.ist_tarif_titel(
        "MOTOROLA moto g86 5G, 256 GB, Spellbound (XT2527-2)")
    assert not autoerkennung.ist_tarif_titel(
        "Oakley Meta - HSTN Prizm Polarized (AI Glasses)")
    assert not autoerkennung.ist_tarif_titel("Samsung Galaxy A36 5G")
    assert not autoerkennung.ist_tarif_titel("")
    assert not autoerkennung.ist_tarif_titel(None)


def test_tarif_titel_werden_nicht_gespeichert(tmp_path):
    """Neue Tarif-Titel kommen nicht in die Arbeitsliste - Geraetetitel und
    Farben desselben Laufs sehr wohl (echte Werte des ALDI-TALK-Kontingents
    vom 17.09.)."""
    eintraege = [
        {"art": "titel", "wert": "Tarif S", "anbieter": "ALDI TALK",
         "quelle": "microdata"},
        {"art": "titel", "wert": "Tarif M", "anbieter": "ALDI TALK",
         "quelle": "microdata"},
        {"art": "titel", "wert": "Tarif L", "anbieter": "ALDI TALK",
         "quelle": "microdata"},
        {"art": "titel",
         "wert": "MOTOROLA moto g86 5G, 256 GB, Spellbound (XT2527-2)",
         "anbieter": "ALDI TALK", "quelle": "microdata"},
        {"art": "titel", "wert": "SONIM XP400, 128 GB, Schwarz",
         "anbieter": "ALDI TALK", "quelle": "microdata"},
        {"art": "farbe", "wert": "Glacier Blue", "anbieter": "ALDI TALK",
         "quelle": "microdata"},
    ]
    zeilen_gesamt = autoerkennung.persistiere_unbekannte(
        tmp_path, eintraege, "2026-09-18")

    datei = tmp_path / "data" / "state" / "geraete_unbekannt.jsonl"
    zeilen = [json.loads(z) for z in datei.read_text().splitlines() if z]
    assert zeilen_gesamt == 3 == len(zeilen)
    assert {z["wert"] for z in zeilen} == {
        "MOTOROLA moto g86 5G, 256 GB, Spellbound (XT2527-2)",
        "SONIM XP400, 128 GB, Schwarz", "Glacier Blue"}
    # Kein Tarifname steht irgendwo in der Liste.
    assert all("Tarif" not in z["wert"] for z in zeilen)


def test_bestaende_werden_beim_naechsten_schreiben_bereinigt(tmp_path):
    """Die Regel wirkt im CODE, die Bereinigung macht der NAECHSTE Lauf:
    data/state wird nie von Hand angefasst (Hausregel). Der Bestand vom
    17.09. - 3 Tarif-Zeilen mit Haeufigkeit 29 je, echte Geraetetitel und
    eine echte Farbe daneben - wird beim naechsten Schreiben einer EINZEN
    neuen Farbe um genau die 3 Rausch-Zeilen kleiner."""
    bestand = [
        {"art": "titel", "wert": "Tarif S", "anbieter": "ALDI TALK",
         "quelle": "microdata", "datum": "2026-09-17", "haeufigkeit": 29},
        {"art": "titel", "wert": "Tarif M", "anbieter": "ALDI TALK",
         "quelle": "microdata", "datum": "2026-09-17", "haeufigkeit": 29},
        {"art": "titel", "wert": "Tarif L", "anbieter": "ALDI TALK",
         "quelle": "microdata", "datum": "2026-09-17", "haeufigkeit": 29},
        {"art": "titel", "wert": "iPad Pro 11 (2025)", "anbieter": "Vodafone",
         "quelle": "vodafone_buendel", "datum": "2026-09-17",
         "haeufigkeit": 2},
        {"art": "farbe", "wert": "Burgunder", "anbieter": "Vodafone",
         "quelle": "vodafone_api", "datum": "2026-09-17", "haeufigkeit": 40},
    ]
    pfad = tmp_path / "data" / "state" / "geraete_unbekannt.jsonl"
    pfad.parent.mkdir(parents=True)
    pfad.write_text("".join(json.dumps(z, ensure_ascii=False) + "\n"
                            for z in bestand), encoding="utf-8")

    # Der naechste Lauf meldet EINE neue echte Farbe (Polar, iPhone 18).
    autoerkennung.persistiere_unbekannte(
        tmp_path,
        [{"art": "farbe", "wert": "Polar", "anbieter": "Vodafone",
          "quelle": "vodafone_api"}],
        "2026-09-18")

    zeilen = [json.loads(z) for z in pfad.read_text().splitlines() if z]
    assert len(zeilen) == 3
    assert {z["wert"] for z in zeilen} \
        == {"iPad Pro 11 (2025)", "Burgunder", "Polar"}
    # Die gezaehlte Haeufigkeit der Rausch-Zeilen (29 je, Summe 87) verhindert
    # nicht ihr Verschwinden - sie war eine Zaehlung, keine Buchfuehrung.
    assert all("Tarif" not in z["wert"] for z in zeilen)


def test_ueber_den_ganzen_echten_bestand_vom_17_09():
    """Die Wahrheitsprobe gegen ALLE 145 echten Titel-Zeilen des 17.09.
    (Fixture, s. _herkunft.json): die Regel trifft GENAU die drei ALDI-Tarife
    und keinen einzigen Geraetetitel - auch nicht die ziffernlosen."""
    zeilen = [json.loads(z) for z in
              (_FIX / "unbekannte_titel_2026-09-17.jsonl")
              .read_text(encoding="utf-8").splitlines() if z.strip()]
    assert len(zeilen) == 145          # die Fixture ist der ganze Bestand

    rauschen = [z for z in zeilen if autoerkennung.ist_tarif_titel(z["wert"])]
    assert sorted(z["wert"] for z in rauschen) == ["Tarif L", "Tarif M",
                                                   "Tarif S"]
    assert {z["anbieter"] for z in rauschen} == {"ALDI TALK"}
    assert sum(z.get("haeufigkeit", 0) for z in rauschen) == 87

    # Jeder andere Titel bleibt stehen - 142 von 145.
    assert len(zeilen) - len(rauschen) == 142
    # Die ziffernlosen Geraetetitel des Bestands tragen kein ‚Tarif' und
    # fallen nicht durch die UND-Regel:
    for titel in ("Oakley Meta - HSTN Prizm Polarized (AI Glasses)",
                  "motorola edge 70"):
        assert any(z["wert"] == titel for z in zeilen)
        assert not autoerkennung.ist_tarif_titel(titel)


# ==========================================================================
# P5/E3: Feste Familien-Anker - iPad, Watch, AirPods ohne Praefix
# ==========================================================================
# Vodafone nennt seine iPads im strukturierten Namen OHNE Hersteller-Praefix
# (`modelName`: „iPad Pro 11 (2025)", „iPad (2025)", „iPad Pro 11 2024" -
# data/state/geraete_unbekannt.jsonl vom 17.09.). Die Serie „iPad" stand in
# keinem Katalog-Eintrag, also griff der Serien-Anker nie: die Anker-Luecke
# aus auto-doku.md. iPad, Watch und AirPods sind Apple-Serien - der feste
# Familien-Anker ist Markennamen-Fakt, keine Raterei, und greift NUR, wo der
# Katalog die Reihe nicht kennt (Hand schlaegt Auto bleibt).

def test_ipad_ohne_hersteller_praefix_wird_ueber_familien_anker_angelegt():
    """Die echten Vodafone-modelNames vom 17.09. werden von _mini_katalog
    (der Katalog kennt KEIN iPad) aus Apple geschält - kuenftige iPads
    („iPad Air", „iPad mini", „iPad Pro 14") ebenso, ohne Katalog-Pflege."""
    for name in ("iPad Pro 11 (2025)", "iPad (2025)", "iPad Pro 11 2024"):
        assert autoerkennung.schale(name, _mini_katalog()) == ("Apple", name)

    eintrag = autoerkennung.lege_an("iPad Pro 11 (2025)", _mini_katalog(),
                                    "2026-09-18", speicher_gb=256)
    assert eintrag is not None
    assert eintrag.hersteller == "Apple"
    assert eintrag.modell == "iPad Pro 11 (2025)"
    assert eintrag.device_id == device_id("Apple", "iPad Pro 11 (2025)")
    assert eintrag.auto == "2026-09-18"
    # Auto-Regeln unveraendert: marktstart und vorgaenger bleiben leer.
    assert eintrag.marktstart == "" and eintrag.vorgaenger == ""


def test_vodafone_ipad_titel_trifft_den_auto_eintrag():
    """Die Launch-Kette bis zur Listung: nach der Anlage aus dem strukturierten
    Namen trifft der ZUSAMMENGESETZTE Vodafone-Titel (echt aus der Liste vom
    17.09., mit Speicher und Farbe) den Eintrag - derselbe Retry, den der
    Listungsweg macht."""
    katalog = _mini_katalog()
    autoerkennung.lege_an("iPad Pro 11 (2025)", katalog, "2026-09-18",
                          speicher_gb=256)
    treffer = erkenne_geraet("iPad Pro 11 (2025) 256 GB Silber", katalog)
    assert treffer is not None
    assert treffer.device_id == device_id("Apple", "iPad Pro 11 (2025)")


def test_watch_und_airpods_ohne_praefix_werden_angelegt():
    """Dieselben Familien in den Benennformen des Bestands: Watch-Modellnamen
    (so stehen sie seit dem 17.09. im Auto-Katalog) und die AirPods-Titel
    congstars. Mit Praefix liefen sie ueber den Praefix-Pfad - der Anker
    traegt die Nennung OHNE nach."""
    katalog = _mini_katalog()
    for name in ("Watch Ultra 4", "Watch Series 12 46 Aluminium",
                 "AirPods 5", "AirPods Max 2", "AirPods Pro (3. Gen.)"):
        assert autoerkennung.schale(name, katalog) == ("Apple", name)


def test_familien_anker_schlaegt_nicht_den_katalog():
    """Hand schlaegt Auto, in beide Richtungen: kennt der Katalog die Reihe
    EINDEUTIG - auch von einem ANDEREN Hersteller -, entscheidet er; kennt er
    sie WIDERSPRUECHLICH, bleibt es beim Verwurf (nichts geraten). Der feste
    Apple-Anker darf beides nicht ueberschreiben."""
    eindeutig_samsung = Katalog(geraete=[
        Geraet(hersteller="Samsung", modell="Watch 7", generation=7)])
    assert autoerkennung.schale("Watch 8", eindeutig_samsung) \
        == ("Samsung", "Watch 8")

    zweideutig = Katalog(geraete=[
        Geraet(hersteller="Samsung", modell="Watch 7", generation=7),
        Geraet(hersteller="Apple", modell="Watch 9", generation=9)])
    assert autoerkennung.schale("Watch 8", zweideutig) is None
    assert autoerkennung.lege_an("Watch 8", zweideutig, _HEUTE) is None


def test_hmd_und_router_bleiben_anker_luecken():
    """Der Fruehindikator bleibt ehrlich: „HMD Fusion X1" (echter Vodafone-
    Titel, Hersteller ohne jeden Katalogbezug) und „Vodafone GigaCube 5G"
    (Router - der Hand-Katalog verfolgt sie bewusst nicht) werden NICHT
    angelegt. Nicht jede unbekannte Benennform wird ein Eintrag; diese
    bleiben Arbeitsliste."""
    katalog = _mini_katalog()
    for name in ("HMD Fusion X1", "GigaCube 5G", "Vodafone GigaCube 5G"):
        assert autoerkennung.schale(name, katalog) is None
    assert autoerkennung.lege_an("HMD Fusion X1", katalog, _HEUTE) is None
    assert [g for g in katalog.geraete if g.auto] == []
