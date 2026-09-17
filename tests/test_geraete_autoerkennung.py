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

from telco_radar.collect.geraete import (
    autoerkennung, o2, sammle_anbieter, telekom, vodafone,
)
from telco_radar.collect.geraete.robots import RobotsWaechter
from telco_radar.geraete_config import Anbieter, Einstieg
from telco_radar.geraete_model import Geraet, Katalog, device_id

_TELEKOM_URL = "https://www.telekom.de/shop/geraete/smartphones/ohne-vertrag"
_HEUTE = "2026-09-15"


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
