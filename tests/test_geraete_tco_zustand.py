"""B1 (QA-Befund vom 04.09.2026): der Geraetezustand steht auf der Karte,
am G1-Balken und in der Tabelle - und ein erneuertes Geraet ist kein
Konkurrent des Neugeraets.

Der Fehler, gegen den diese Tests gebaut sind: der Store trug zu iPhone 15
128 GB bei o2 BEIDE Buendel (neu 20,00 EUR, erneuert 17,00 EUR im Monat),
die Kartenauswahl nahm je (Anbieter, Tarif, Laufzeit) die guenstigste -
also die erneuerte -, und die stand ohne ein Wort "erneuert" mit "775,35 EUR
guenstiger als die Vodafone-Referenz" gegen Neugeraete.

Bestandsdateien, die die gerenderte Ansicht laedt (hier alle als Fixture
in `tmp_path` geschrieben, keine davon aus dem Repo):
  data/state/geraete_db.json      Listungen MIT `zustand`
  data/state/geraete_tco.json     die Buendel (neu UND erneuert) + SIM-only
  data/state/tarife.jsonl         die Tarifbindung - ohne sie ist keine
                                  Karte belastbar, und die ganze Tafel waere
                                  ein Leerzustand (Lektion aus Phase R)
  data/state/geraete_preise.jsonl die Preishistorie
  config/geraete_katalog.yaml, config/farben.yaml, config/geraete_quellen.yaml

Die Gegenprobe (`test_ohne_erneuertes_buendel_kein_etikett`) baut dieselbe
Seite OHNE das erneuerte Buendel: kein Etikett, keine zweite o2-Karte. Der
Test misst also die Daten, nicht die Vorlage.
"""
from __future__ import annotations

import json
import pathlib

import yaml
from bs4 import BeautifulSoup

from telco_radar.analyze.tco_buendel import aus_rohsaetzen
from telco_radar.analyze.tco_store import TcoDB
from telco_radar.geraete_config import lade_katalog
from telco_radar.report import geraete_tco_grafik as grafik
from telco_radar.report import geraete_tco_karten as karten
from telco_radar.report import geraete_tco_view as view
from telco_radar.report.html import render_site
from telco_radar.tarif_bezug import Tarifbestand
from telco_radar.tco_model import Buendel, SimOnlyReferenz

WURZEL = pathlib.Path(__file__).resolve().parents[1]


def vorlage_text(el) -> str:
    """Text eines Elements, AUCH wenn es in einem <template> liegt.

    BeautifulSoup (ab 4.13) behandelt <template>-Inhalt als versteckt:
    get_text() liefert ihn nicht - auch nicht nach Re-Parse oder
    Entpacken (get_text behaelt die Hidden-Markierung am String bei).
    Der Rechenweg der Bündel-Zeilen liegt seit dem P4-Fix (template-Pool,
    Montage per Klick) dort. find_all(string=True) sammelt die Textknoten
    ohne Hidden-Filter; Join und split()-Normalisierung halten Interpunkt-
    ion zusammen (ein strip-je-Knoten machte aus "TCO-24)" ein "TCO-24 )")
    - am gerenderten HTML wird nichts veraendert."""
    return " ".join("".join(el.find_all(string=True)).split())


SKU_NEU = "apple-iphone-15-128gb-schwarz"
SKU_ERNEUERT = "apple-iphone-15-128gb-schwarz-refurbished"
HEUTE = "2026-09-04"

# BRIEF_RAHMEN2_R3 (05.09.2026): ein zweites Modell OHNE Listung in
# `geraete_db.json` und OHNE Preishistorie - ueber den Katalog nachgetragen
# (F-R2-3), belastbare Karte, aber `zeitreihe.hat_daten == False`. Derselbe
# Slug wie einer der drei echten graphlosen Bloecke im Bestand.
SKU_GRAPHLOS = "apple-iphone-16-pro-max-256gb-schwarz"


# --------------------------------------------------------------------------
# Bausteine
# --------------------------------------------------------------------------

def _listung(anbieter, sku, preis, zustand="neu"):
    return {"id": f"{anbieter.lower()}--{sku}", "sku_id": sku,
            "device_id": "apple-iphone-15", "anbieter": anbieter,
            "anbieter_typ": "netzbetreiber", "netz": anbieter,
            "speicher_gb": 128, "farbe_roh": "Schwarz",
            "farbe_normalisiert": "schwarz", "zustand": zustand,
            "first_seen": "2026-08-20", "last_verified": HEUTE,
            "status": "aktiv", "missed_checks": 0,
            "preis_ohne_vertrag": preis, "erstpreis": preis,
            "erstpreis_art": "ohne_vertrag", "erstpreis_am": "2026-08-20",
            "quelle_url": f"https://example.de/{anbieter.lower()}/{sku}",
            "abgerufen_am": HEUTE, "verfuegbarkeit": "lieferbar",
            "confidence": "hoch", "einstiege": ["https://example.de/liste"]}


def _listungen():
    return [_listung("o2", SKU_NEU, 709.0),
            _listung("o2", SKU_ERNEUERT, 445.0, zustand="refurbished"),
            _listung("Vodafone", SKU_NEU, 709.90)]


def _buendel(sku, rate, zustand=""):
    return Buendel(sku_id=sku, anbieter="o2",
                   tarif_name="O2 Mobile on Demand M Plus mit 50 GB+ (24 Mon.)",
                   tarif_id="o2:on-demand-m", tarif_id_guete="hoch",
                   tarif_monatlich=14.99, tarif_bindung_monate=24,
                   geraet_zuzahlung=1.0, geraet_monatsrate=rate,
                   laufzeit_monate=36, anschlusspreis=39.99,
                   zustand=zustand,
                   quelle_url=f"https://example.de/o2/{sku}",
                   abgerufen_am=HEUTE)


def _referenzen():
    return [SimOnlyReferenz(anbieter="Vodafone", tarif_name="Vodafone Mobil XS",
                            tarif_id="vf:xs", tarif_sim_only_monatlich=29.95,
                            quelle_url="https://example.de/pib/vf-xs",
                            abgerufen_am=HEUTE),
            SimOnlyReferenz(anbieter="o2", tarif_name="O2 Mobile on Demand M",
                            tarif_id="o2:on-demand-m",
                            tarif_sim_only_monatlich=19.99,
                            quelle_url="https://example.de/pib/o2-m",
                            abgerufen_am=HEUTE)]


def _tarife():
    # o2 mit `preisphasen: []` wie die echte Kachel-Lesart (preistyp
    # live_shop): die Quelle schweigt ueber die Zeit nach der
    # Mindestlaufzeit - die Karte muss die Luecke BENENNEN (F5).
    return [{"anbieter": "o2", "name": "O2 Mobile on Demand M",
             "tarif_id": "o2:on-demand-m", "art": "mobilfunk",
             "grundgebuehr": 19.99, "laufzeit_monate": 24,
             # O1 (11.09.2026): ein Datenvolumen je Tarif, damit die
             # Fixture Bänder hat und der Graph Zeilen rendert.
             "datenvolumen_gb": 50,
             "preisphasen": [],
             "dokument_url": "https://example.de/pib/o2-m",
             "abgerufen_am": HEUTE, "confidence": {}, "fundstellen": {}},
            {"anbieter": "Vodafone", "name": "Vodafone Mobil XS",
             "tarif_id": "vf:xs", "art": "mobilfunk",
             "grundgebuehr": 29.95, "laufzeit_monate": 24,
             "datenvolumen_gb": 18,
             "preisphasen": [{"von_monat": 1, "bis_monat": 24, "betrag": 29.95},
                             {"von_monat": 25, "bis_monat": None,
                              "betrag": 29.95}],
             "dokument_url": "https://example.de/pib/vf-xs",
             "abgerufen_am": HEUTE, "confidence": {}, "fundstellen": {}}]


def _modell(erneuert=True):
    tarife = {t["tarif_id"]: t for t in _tarife()}
    buendel = [_buendel(SKU_NEU, 20.0)]
    if erneuert:
        buendel.append(_buendel(SKU_ERNEUERT, 17.0))
    ergebnis = karten.modelle(buendel, _listungen(), _referenzen(), tarife,
                              lade_katalog(WURZEL))
    assert len(ergebnis["modelle"]) == 1
    return ergebnis["modelle"][0]


# --------------------------------------------------------------------------
# Die Karten
# --------------------------------------------------------------------------

def test_neu_und_erneuert_sind_zwei_karten_und_nur_das_neue_konkurriert():
    modell = _modell()
    o2 = [k for k in modell["karten"] if k["anbieter"] == "o2"]
    assert len(o2) == 2, "der Dedupe-Schluessel muss den Zustand kennen"
    neu = next(k for k in o2 if k["sku_id"] == SKU_NEU)
    erneuert = next(k for k in o2 if k["sku_id"] == SKU_ERNEUERT)

    assert neu["zustand"] == "neu" and neu["zustand_etikett"] == ""
    assert neu["vergleichbar"] is True
    assert erneuert["zustand"] == "refurbished"
    assert erneuert["zustand_etikett"] == "erneuert"
    assert erneuert["vergleichbar"] is False

    # Beide tragen eine Zahl - das erneuerte ist ein Angebot, nur kein
    # Konkurrent: das Neugeraet bekommt das Delta, das erneuerte nicht.
    assert neu["belastbar"] and erneuert["belastbar"]
    assert erneuert["gesamt"] < neu["gesamt"]
    assert neu["delta"] is not None
    assert erneuert["delta"] is None

    # Das Band zaehlt beide als Angebot und nennt das erneuerte; die
    # Spanne gehoert dem Vergleich, also den Neugeraeten.
    assert modell["angebote"] == 2
    assert modell["erneuert"] == 1
    assert erneuert["gesamt"] not in modell["spanne"]
    # Das erneuerte steht HINTER dem Vergleich, nicht davor.
    reihenfolge = [k["sku_id"] for k in modell["karten"] if k["sku_id"]]
    assert reihenfolge.index(SKU_NEU) < reihenfolge.index(SKU_ERNEUERT)


def test_das_etikett_steht_am_g1_balken():
    svg = grafik.balken(_modell())
    assert 'class="gr-g1-zustand">erneuert</tspan>' in svg
    assert "o2 (erneuert): " in svg, "auch der Balkentitel nennt den Zustand"
    # Und genau einmal - der neue o2-Balken traegt kein Etikett.
    assert svg.count('gr-g1-zustand') == 1


def test_ohne_beleg_gilt_der_zustand_als_unbekannt_nicht_als_neu():
    """Ein Buendel ohne Listung, ohne Feld und ohne Zustandsstrecke."""
    tarife = {t["tarif_id"]: t for t in _tarife()}
    fremd = _buendel("apple-iphone-15-256gb-blau", 22.0)
    ergebnis = karten.modelle([fremd], _listungen(), _referenzen(), tarife,
                              lade_katalog(WURZEL))
    karte = next(k for m in ergebnis["modelle"] for k in m["karten"]
                 if k["sku_id"] == fremd.sku_id)
    assert karte["zustand"] == "unbekannt"
    assert karte["zustand_etikett"] == "Zustand nicht belegt"
    assert karte["vergleichbar"] is False
    assert karte["delta"] is None


def test_die_zustandsstrecke_der_sku_belegt_erneuert_aber_nie_neu():
    ohne_listung: dict = {}
    assert karten.zustand_des_buendels(
        _buendel("x-refurbished", 1.0), ohne_listung) == "refurbished"
    assert karten.zustand_des_buendels(
        _buendel("x-b-ware", 1.0), ohne_listung) == "b-ware"
    assert karten.zustand_des_buendels(_buendel("x", 1.0), ohne_listung) == "unbekannt"
    # Das Feld am Buendel schlaegt alles; die Listung schlaegt das Suffix.
    assert karten.zustand_des_buendels(
        _buendel("x", 1.0, zustand="refurbished"), ohne_listung) == "refurbished"
    assert karten.zustand_des_buendels(
        _buendel("x", 1.0), {("o2", "x"): "b-ware"}) == "b-ware"


def test_ein_erneuertes_eigenes_buendel_wird_nicht_zur_referenz():
    """Ein erneuertes Vodafone-Buendel ist kein Massstab fuer Neugeraete."""
    tarife = {t["tarif_id"]: t for t in _tarife()}
    eigen = Buendel(sku_id=SKU_ERNEUERT, anbieter="Vodafone",
                    tarif_name="Vodafone Mobil XS", tarif_id="vf:xs",
                    tarif_monatlich=29.95, tarif_bindung_monate=24,
                    geraet_zuzahlung=1.0, geraet_monatsrate=10.0,
                    laufzeit_monate=24, zustand="refurbished",
                    quelle_url="https://example.de/vf/x", abgerufen_am=HEUTE)
    listungen = _listungen() + [_listung("Vodafone", SKU_ERNEUERT, 400.0,
                                         zustand="refurbished")]
    ergebnis = karten.modelle([_buendel(SKU_NEU, 20.0), eigen], listungen,
                              _referenzen(), tarife, lade_katalog(WURZEL))
    modell = ergebnis["modelle"][0]
    assert not modell["referenz"].get("aus_buendel"), \
        "die Referenz bleibt die Neugeraet-Naeherung"
    vodafone = [k for k in modell["karten"] if k["anbieter"] == "Vodafone"]
    # Das erneuerte eigene Buendel steht als etikettierte Karte daneben.
    assert any(k["zustand_etikett"] == "erneuert" for k in vodafone)


# --------------------------------------------------------------------------
# Speicher und Leser
# --------------------------------------------------------------------------

def test_der_zustand_ueberlebt_speicher_und_leser(tmp_path):
    db = TcoDB(tmp_path / "geraete_tco.json")
    db.upsert_buendel([_buendel(SKU_ERNEUERT, 17.0, zustand="refurbished")],
                      HEUTE)
    assert db.save(HEUTE)
    neu_geladen = TcoDB(tmp_path / "geraete_tco.json")
    gespeichert = neu_geladen.buendel()[0]
    assert gespeichert["zustand"] == "refurbished"
    # ... und der Leser der Tafel nimmt das Feld mit.
    (satz,) = view._aus_speicher([gespeichert], Buendel, view._BUENDEL_FELDER)
    assert satz.zustand == "refurbished"


def test_der_buendelleser_reicht_den_zustand_durch():
    bestand = Tarifbestand([
        {"tarif_id": "o2:on-demand-m", "anbieter": "o2",
         "name": "O2 Mobile on Demand M", "grundgebuehr": 19.99,
         "buendel_slug": "o2-mobile-on-demand-m-plus"}])
    roh = {"sku_id": SKU_ERNEUERT, "anbieter": "o2",
           "tarif_name": "O2 Mobile on Demand M Plus mit 50 GB+ (24 Mon.)",
           "tarif_slug": "o2-mobile-on-demand-m-plus",
           "tarif_monatlich": 14.99, "geraet_zuzahlung": 1.0,
           "geraet_monatsrate": 17.0, "anschlusspreis": 39.99,
           "laufzeit_monate": 36, "zustand": "refurbished",
           "quelle_url": "https://example.de/o2/x"}
    bilanz = aus_rohsaetzen([roh], bestand, HEUTE)
    assert bilanz.buendel[0].zustand == "refurbished"


# --------------------------------------------------------------------------
# Die gerenderte Seite
# --------------------------------------------------------------------------

_KATALOG = {"geraete": [
    {"hersteller": "Apple", "modell": "iPhone 15", "generation": 15,
     "marktstart": "2023-09-22", "speicher": [128, 256], "segment": "premium"},
]}
_FARBEN = {"farben": {"schwarz": ["Schwarz", "Black"]}}
_QUELLEN = {"anbieter": [
    {"name": "o2", "typ": "netzbetreiber", "rang": 1, "methode": "json_endpunkt",
     "basis_url": "https://www.o2online.de",
     "einstiege": [{"url": "https://www.o2online.de/e-shop/",
                    "label": "Katalog", "kind": "static"}]},
    {"name": "Vodafone", "typ": "netzbetreiber", "rang": 2, "eigen": True,
     "methode": "json_endpunkt", "basis_url": "https://www.vodafone.de",
     "einstiege": [{"url": "https://api.vodafone.de/glados/v2/hardware",
                    "label": "Liste", "kind": "static"}]},
]}


def _speicherform(b: Buendel) -> dict:
    return {"id": b.id, "sku_id": b.sku_id, "anbieter": b.anbieter,
            "tarif_name": b.tarif_name, "tarif_id": b.tarif_id,
            "tarif_id_guete": b.tarif_id_guete,
            "tarif_monatlich": b.tarif_monatlich,
            "buendel_monatlich": b.buendel_monatlich,
            "geraet_zuzahlung": b.geraet_zuzahlung,
            "geraet_monatsrate": b.geraet_monatsrate,
            "laufzeit_monate": b.laufzeit_monate,
            "anschlusspreis": b.anschlusspreis, "rabatte": [],
            "zustand": b.zustand, "quelle_url": b.quelle_url,
            "abgerufen_am": b.abgerufen_am, "first_seen": HEUTE,
            "last_verified": HEUTE}


def _baue(tmp_path: pathlib.Path, erneuert: bool = True,
          punkte: list | None = None,
          graphloses_modell: bool = False,
          eins_und_eins: bool = False,
          einmalzahlung: float | None = None,
          anschlusspreis: float | None = None,
          ungefaehr_delta: bool = False) -> BeautifulSoup:
    """`punkte` ersetzt die Preishistorie - `test_geraete_preis_mehrdeutig`
    stellt darueber Tage mit zwei Preisen derselben Listung.

    `graphloses_modell` (BRIEF_RAHMEN2_R3, 05.09.2026) haengt ein zweites
    Buendel (SKU_GRAPHLOS) an, dem keine Listung und keine Preishistorie
    gegenuebersteht - derselbe Fall wie bei den drei echten Bloecken ohne
    Zeitreihen-Graph. Default False: kein bestehender Aufrufer von `_baue`
    aendert sein Ergebnis.

    `eins_und_eins` (S-Q4, 09.09.2026) haengt eine 1&1-Karte an DASSELBE
    Modell: ein Buendel mit `buendel_monatlich` und OHNE Aufteilung (§ 13.2,
    Bauweise wie test_geraete_buendel_einsundeins), tarif_id leer wie im
    echten Bestand - die Karte muss ihre "ab Monat 25"-Luecke selbst
    benennen. Dient dem Terminologie-Test der BAU-Zeile und der
    Monatsraten/Geräteraten-Unterscheidung.

    `einmalzahlung`/`anschlusspreis` (S2-C, 09.09.2026) setzen die zwei
    neuen 1&1-Felder auf genau dieser Karte - beide None (Default) lassen
    jeden bestehenden Aufrufer unveraendert. Die Werte sind die echten
    der iPhone-Fixture (360,00/39,90), siehe test_geraete_buendel_
    einsundeins.

    `ungefaehr_delta` (A2, 20.09.2026) haengt eine Vodafone-Mobil-XS-
    Referenz aus einem ECHTEN Buendel (1.799,80) und ein o2-Angebot
    knapp darueber (1.810,80 = +11,00) an - der Fall der ≈-Spalte am
    gerenderten Blatt (Fix 2)."""
    root = tmp_path / ("mit" if erneuert else "ohne")
    (root / "config").mkdir(parents=True)
    katalog = _KATALOG
    if graphloses_modell:
        katalog = {"geraete": _KATALOG["geraete"] + [
            {"hersteller": "Apple", "modell": "iPhone 16 Pro Max",
             "generation": 16, "marktstart": "2024-09-20", "speicher": [256],
             "segment": "premium"}]}
    for name, daten in (("geraete_katalog.yaml", katalog),
                        ("farben.yaml", _FARBEN),
                        ("geraete_quellen.yaml", _QUELLEN)):
        (root / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
    state = root / "data" / "state"
    state.mkdir(parents=True)
    listungen = _listungen()
    (state / "geraete_db.json").write_text(json.dumps({
        "updated": HEUTE, "anbieter": {
            "o2": {"laeufe": 4, "funde_gesamt": 2},
            "Vodafone": {"laeufe": 4, "funde_gesamt": 1}},
        "listungen": listungen}), encoding="utf-8")
    if punkte is None:
        punkte = [{"listung_id": e["id"], "device_id": e["device_id"],
                   "anbieter": e["anbieter"], "datum": "2026-08-20",
                   "preis_ohne_vertrag": e["preis_ohne_vertrag"],
                   "quelle_url": e["quelle_url"]} for e in listungen]
    (state / "geraete_preise.jsonl").write_text(
        "\n".join(json.dumps(z) for z in punkte) + "\n", encoding="utf-8")
    buendel = [_buendel(SKU_NEU, 20.0, zustand="neu")]
    if erneuert:
        buendel.append(_buendel(SKU_ERNEUERT, 17.0, zustand="refurbished"))
    if graphloses_modell:
        # Bewusst KEINE Listung in `geraete_db.json` und KEIN Punkt in
        # `geraete_preise.jsonl` fuer dieses Geraet - `geraet_aus_sku()`
        # loest es trotzdem ueber den Katalog auf (F-R2-3), die Karte
        # rechnet, aber `listungen_je_modell` bleibt fuer diese ID leer.
        # O1 (11.09.2026): der Tarif dieses Buendels traegt KEIN
        # Datenvolumen - damit bleibt das Modell auch nach O1 „ohne Graph“,
        # weil der Graph an Baendern haengt (nicht mehr an der Zeitreihe).
        graphlos = _buendel(SKU_GRAPHLOS, 20.0, zustand="neu")
        graphlos = Buendel(
            **{**graphlos.__dict__, "tarif_id": "o2:ohne-volumen",
               "tarif_name": "O2 Mobile on Demand M Flex"})
        buendel.append(graphlos)
    if eins_und_eins:
        # § 13.2: NUR der kombinierte Monatsbetrag, keine Aufteilung - die
        # Bauweise der echten 1&1-Saetze (44,99 €/36 Monate, siehe
        # test_geraete_buendel_einsundeins). tarif_id bleibt leer, weil
        # 1&1-Tarife nicht im Tarifbestand stehen (F5-Kommentar im
        # Template).
        buendel.append(Buendel(
            sku_id=SKU_NEU, anbieter="1&1",
            tarif_name="1&1 All-Net-Flat S",
            buendel_monatlich=44.99, laufzeit_monate=36, zustand="neu",
            geraet_zuzahlung=einmalzahlung, anschlusspreis=anschlusspreis,
            quelle_url="https://example.de/einsundeins/" + SKU_NEU,
            abgerufen_am=HEUTE))
    if ungefaehr_delta:
        buendel.append(_xs_buendel(SKU_NEU, 30.0, HEUTE,
                                   tarif_monatlich=29.95))
        buendel.append(_knapp_o2(30.25, 2.0))
    (state / "geraete_tco.json").write_text(json.dumps({
        "updated": HEUTE, "buendel": [_speicherform(b) for b in buendel],
        "sim_only": [{"id": r.id, "anbieter": r.anbieter,
                      "tarif_name": r.tarif_name, "tarif_id": r.tarif_id,
                      "tarif_id_guete": "hoch",
                      "tarif_sim_only_monatlich": r.tarif_sim_only_monatlich,
                      "anschlusspreis": None, "rabatte": [],
                      "quelle_url": r.quelle_url, "abgerufen_am": HEUTE,
                      "first_seen": HEUTE, "last_verified": HEUTE}
                     for r in _referenzen()]}), encoding="utf-8")
    tarife = list(_tarife())
    if graphloses_modell:
        ohne = {"anbieter": "o2", "name": "O2 Mobile on Demand M Flex",
                "tarif_id": "o2:ohne-volumen", "art": "mobilfunk",
                "grundgebuehr": 14.99, "laufzeit_monate": 24,
                "preisphasen": [],
                "dokument_url": "https://example.de/pib/o2-flex",
                "abgerufen_am": HEUTE, "confidence": {}, "fundstellen": {}}
        tarife.append(ohne)
    (state / "tarife.jsonl").write_text(
        "\n".join(json.dumps(t) for t in tarife) + "\n", encoding="utf-8")
    # E2 (16.09.2026): die TCO-HISTORIE - ohne sie haette die Hauptansicht
    # der Fixture keine Zeitreihe (nur den Leer-Satz), und jeder Test, der
    # den Graphen prueft, prueft einen Leerzustand. Drei Messtage fuer das
    # NEUE o2-Buendel (Band mittel, 50 GB); das erneuerte und das 1&1-
    # Bündel haben absichtlich keinen Punkt - genau die Luecke, die der
    # Graph fuehren soll.
    neu_b = _buendel(SKU_NEU, 20.0, zustand="neu")
    historie = []
    for tag, gesamt in (("2026-09-02", 961.76), ("2026-09-03", 961.76),
                        ("2026-09-04", 951.76)):
        historie.append({**_speicherform(neu_b), "id": neu_b.id,
                         "datum": tag, "gesamt": gesamt})
    (state / "geraete_tco_historie.jsonl").write_text(
        "\n".join(json.dumps(z) for z in historie) + "\n", encoding="utf-8")
    reports = root / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / f"{HEUTE}.json").write_text(json.dumps({
        "date": HEUTE, "language": "de",
        "briefing_md": "## Auf einen Blick\n\n- Nichts Besonderes.\n",
        "stats": {}, "regions": []}), encoding="utf-8")
    (reports / f"{HEUTE}.md").write_text("# Bericht\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    return BeautifulSoup((site / "geraete.html").read_text(encoding="utf-8"),
                         "html.parser")


def test_die_gerenderte_seite_traegt_das_etikett_auf_zeile_und_rechenweg(tmp_path):
    """BRIEF_FADEN (05.09.2026): G1 (der Balken) ist aus DIESER Ansicht
    entfernt - seit O2 (11.09.2026) sind die Karten Tabellenzeilen, und
    der Test prueft das Etikett an den ZEILEN. Dass `geraete_tco_grafik.
    balken()` das Etikett weiterhin rechnet (Code bleibt, nur der Aufruf
    im Template ist geloescht), haelt die Gegenprobe unten UND
    `test_das_etikett_steht_am_g1_balken` oben."""
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    zeilen_o2 = tafel.select('.gr-bnd[data-anbieter="o2"]')
    assert len(zeilen_o2) == 2

    erneuert = tafel.select_one('.gr-bnd[data-zustand="refurbished"]')
    assert erneuert is not None
    assert erneuert.select_one(".gr-kk-marke--zustand").get_text(strip=True) == "erneuert"
    assert erneuert.select_one(".gr-kk-delta") is None, \
        "das erneuerte Geraet ist kein Konkurrent des Neugeraets"
    neu = tafel.select_one('.gr-bnd[data-anbieter="o2"][data-zustand="neu"]')
    assert neu.select_one(".gr-kk-marke--zustand") is None
    assert neu.select_one(".gr-kk-delta") is not None

    # G1 wird nicht mehr gerendert - G0 (die Zeitreihe) ist die einzige
    # Grafik je Modellblock (BRIEF_FADEN, Kriterium 1).
    assert tafel.select_one("svg.gr-g1") is None
    # Die Rechnung bleibt trotzdem korrekt, nur nicht mehr aufgerufen -
    # dieselbe Zusicherung wie `test_das_etikett_steht_am_g1_balken`.
    svg = grafik.balken(_modell())
    assert 'class="gr-g1-zustand">erneuert</tspan>' in svg

    # Die alte "Alle Bündel als Tabelle" (mit ihrer eigenen Zustandsspalte
    # `.gr-t-zustand`) ist mit O2 in die Zeilen-Tabelle aufgegangen - das
    # Etikett steht jetzt an der Zeile selbst.
    assert tafel.select_one("#gr-tco-tabelle") is None
    assert not tafel.select(".gr-t-zustand")
    assert "erneuert" in " ".join(erneuert.get_text(" ", strip=True).split())

    # Die gr-mband-Angebotszeile ("2 Angebote · davon 1 erneuert") ist mit
    # O1 entfallen - die fuenf Zaehlsysteme der Vergleichsansicht sind auf
    # DIE EINE Fussnote unter dem Graphen gesammelt, und die nennt Geraete,
    # keine Angebote. Das Etikett selbst steht weiterhin auf der Zeile
    # (oben geprueft) - der Zweck der Zeile bleibt erfuellt.
    assert tafel.select_one(".gr-mband") is None
    # Die leere Vodafone-Zeile gibt es hier nicht, die gefuellte ist die
    # Referenzrechnung - und die heisst nicht "unser Angebot" (S3).
    marken = [m.get_text(strip=True) for m in tafel.select(".gr-kk-marke")]
    assert "unser Angebot" not in marken


def test_ohne_erneuertes_buendel_kein_etikett(tmp_path):
    """Die Gegenprobe: dieselbe Seite ohne das zweite Buendel."""
    s = _baue(tmp_path, erneuert=False)
    tafel = s.select_one("#tafel-tco")
    assert len(tafel.select('.gr-bnd[data-anbieter="o2"]')) == 1
    assert not tafel.select(".gr-kk-marke--zustand")
    assert not tafel.select(".gr-g1-zustand")
    assert "erneuert" not in tafel.get_text(" ")


# --------------------------------------------------------------------------
# F1 (Stufe 1) und F5 an der gerenderten Seite
# --------------------------------------------------------------------------

def test_jede_karte_mit_zahl_nennt_den_preis_nach_der_laufzeit_oder_die_luecke(tmp_path):
    """F5: "ab Monat 25" steht auf JEDER Zeile mit Zahl - als Betrag, wo das
    Pflichtdokument eine Preisphase nennt (Vodafone Mobil XS: 29,95 EUR),
    sonst als benannte Luecke (o2: `preisphasen: []`). Eine stumme
    Auslassung liest sich als "es aendert sich nichts"."""
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    mit_zahl = [k for k in tafel.select(".gr-bnd")
                if k.get("data-gesamt")]
    assert len(mit_zahl) == 3            # o2 neu, o2 erneuert, Referenz
    for k in mit_zahl:
        assert k.select_one(".gr-kk-nach") is not None, k["data-anbieter"]

    referenz = tafel.select_one('.gr-bnd[data-anbieter="Vodafone"]')
    assert "ab Monat 25: 29,95 € Tarifgrundpreis" in vorlage_text(
        referenz.select_one(".gr-kk-nach"))
    o2 = tafel.select_one('.gr-bnd[data-anbieter="o2"][data-zustand="neu"]')
    luecke = o2.select_one(".gr-kk-nach--luecke")
    assert luecke is not None
    assert "ab Monat 25: nicht belegt" in vorlage_text(luecke)

    # F1, Stufe 1: die Referenz spricht dem Anbieter nichts ab, das er
    # ausweist - sie nennt sich Naeherung und den Buendelpreis "nicht erhoben".
    hinweis = vorlage_text(referenz.select_one(".gr-kk-hinweis"))
    assert "noch nicht erhoben" in hinweis
    # Gegen seitenlangen Blindtest: seit dem P4-Fix (template-Pool) sieht
    # get_text() den Rechenweg NICHT mehr - der "not in"-Check laeuft
    # gegen den VORLAGEN-Text, sonst pruefte er einen leer gerenderten
    # Baum (CLAUDE.md §6: ein Test, dessen Lookup ins Leere geht, ist
    # gruen und prueft nichts).
    assert "weist zu diesem Gerät keinen Bündelpreis aus" \
        not in vorlage_text(tafel)


# --------------------------------------------------------------------------
# A2 (20.09.2026): die Geist-Messung in der Angebots-Dedupe, das kleine
# Delta mit ≈ statt Strich
# --------------------------------------------------------------------------

def _xs_buendel(sku, rate, tag, zuzahlung=1.0, anschluss=0.0,
                tarif_monatlich=31.95):
    """Vodafone Mobil XS zum iPhone 15 128 GB - die Bauform des echten
    Bestands: 36 Raten, gemessene Buendel-Rate ueber dem Blatt-Preis
    (29,95 im Pflichtdokument, mit Smartphone-Zuschlag 31,95 am Bündel)."""
    return Buendel(sku_id=sku, anbieter="Vodafone",
                   tarif_name="Vodafone Mobil XS", tarif_id="vf:xs",
                   tarif_id_guete="hoch", tarif_monatlich=tarif_monatlich,
                   tarif_bindung_monate=24, geraet_zuzahlung=zuzahlung,
                   geraet_monatsrate=rate, laufzeit_monate=36,
                   anschlusspreis=anschluss, zustand="neu",
                   quelle_url=f"https://example.de/vodafone/{sku}",
                   abgerufen_am=tag)


def test_eine_veraltete_messung_verdraengt_kein_aktuelles_angebot():
    """A2 (20.09.2026), der Befund am iPhone 17 256 GB: ein Bündel, das
    seit 14 nächtlichen Läufen nie wieder bestätigt wurde, unterbietet im
    selben Angebots-Slot die täglich gemessenen Farben und stellte als
    billigste eigene Karte die Vodafone-Referenz. Der Store überschreibt
    Bündel (AUFFRISCHEN, nie löschen) - die Auswahl muss deshalb die
    AKTUELLSTE Messung des Slots nehmen, nicht die billigste Geist-Zahl.

    Frisch (schwarz, 20.09.): 1,00 + 24×31,95 + 36×30,00 + 0,00
                             = 1.847,80 EUR
    Geist (weiss, 06.09.):   0,99 + 24×31,95 + 36×26,00
                             = 1.703,79 EUR - billiger, aber alt."""
    tarife = {t["tarif_id"]: t for t in _tarife()}
    frisch = _xs_buendel(SKU_NEU, 30.0, "2026-09-20")
    geist = _xs_buendel("apple-iphone-15-128gb-weiss", 26.0, "2026-09-06",
                        zuzahlung=0.99)
    modell = karten.modelle([frisch, geist], _listungen(), _referenzen(),
                            tarife, lade_katalog(WURZEL))["modelle"][0]
    xs = [k for k in modell["karten"] if k["anbieter"] == "Vodafone"]
    assert len(xs) == 1, "mehrere Farben, ein Slot: eine Karte"
    assert xs[0]["abgerufen_am"] == "2026-09-20"
    assert xs[0]["gesamt"] == 1847.8
    assert all(k.get("abgerufen_am") != "2026-09-06"
               for k in modell["karten"]), \
        "die Geist-Messung vom 06.09. steht noch auf einer Karte"
    ref = modell["referenz"]
    assert ref["aus_buendel"] is True
    assert ref["tarif"] == "Vodafone Mobil XS"
    assert ref["gesamt"] == 1847.8
    assert ref["tarif_abgerufen_am"] == "2026-09-20"

    # Gegenprobe 1: die Geist-Messung ALLEIN bleibt eine Karte mit ihrer
    # eigenen Zahl - die Neuigkeits-Stufe stellt keine Weiche, sie bricht
    # nur den Gleichstand verschiedener Messungen desselben Slots.
    allein = karten.modelle([geist], _listungen(), _referenzen(), tarife,
                            lade_katalog(WURZEL))["modelle"][0]
    geist_karte = [k for k in allein["karten"]
                   if k["anbieter"] == "Vodafone"][0]
    assert geist_karte["abgerufen_am"] == "2026-09-06"
    assert geist_karte["gesamt"] == 1703.79

    # Gegenprobe 2: gleich alt, verschieden teuer - dann entscheidet
    # wieder der Preis (blau 28 statt gruen 30: 1.775,80 EUR).
    gleich_alt = karten.modelle(
        [_xs_buendel("apple-iphone-15-128gb-blau", 28.0, "2026-09-20"),
         _xs_buendel("apple-iphone-15-128gb-gruen", 30.0, "2026-09-20")],
        _listungen(), _referenzen(), tarife, lade_katalog(WURZEL)
    )["modelle"][0]
    assert [k for k in gleich_alt["karten"]
            if k["anbieter"] == "Vodafone"][0]["gesamt"] == 1775.8


def _knapp_o2(rate, anschluss):
    """Ein o2-Bündel mit DEMSELBEN gemessenen Tarifpreis wie die Referenz
    (29,95) - der Abstand zur Referenz steckt allein in Rate und
    Anschlusspreis, damit die Schwelle (15 EUR / 3 %) gezielt unter-
    und überschritten wird. Der Tarifname unterscheidet sich vom
    Standard-o2-Bündel der Fixture, damit die Angebots-Dedupe die zwei
    Karten nicht in einen Slot legt."""
    return Buendel(sku_id=SKU_NEU, anbieter="o2",
                   tarif_name="O2 Mobile on Demand M",
                   tarif_id="o2:on-demand-m", tarif_id_guete="hoch",
                   tarif_monatlich=29.95, tarif_bindung_monate=24,
                   geraet_zuzahlung=1.0, geraet_monatsrate=rate,
                   laufzeit_monate=36, anschlusspreis=anschluss,
                   zustand="neu",
                   quelle_url=f"https://example.de/o2/knapp",
                   abgerufen_am=HEUTE)


def test_ein_kleiner_abstand_erscheint_als_ungefaehr_statt_strich():
    """Fix 2 (A2): der Strich in der Δ-Spalte bedeutet "kein Angebot" -
    bis A2 bedeutete er auch "Abstand unter 15 EUR / 3 %", und ein
    gemessenes Angebot stand da wie ein fehlendes. Referenz (Vodafone
    Mobil XS, 29,95 gemessen): 1,00 + 24×29,95 + 36×30,00 + 0,00
    = 1.799,80 EUR. Knapp daneben (Rate 30,25, Anschluss 2,00):
    1.810,80 EUR - exakt +11,00 EUR, 0,6 %."""
    tarife = {t["tarif_id"]: t for t in _tarife()}
    referenz = _xs_buendel(SKU_NEU, 30.0, HEUTE, tarif_monatlich=29.95)
    modell = karten.modelle([referenz, _knapp_o2(30.25, 2.0)],
                            _listungen(), _referenzen(), tarife,
                            lade_katalog(WURZEL))["modelle"][0]
    o2 = [k for k in modell["karten"] if k["anbieter"] == "o2"][0]
    assert o2["gesamt"] == 1810.8
    d = o2["delta"]
    assert d["ungefaehr"] is True
    assert d["betrag"] == 11.0 and d["abstand"] == 11.0
    assert d["guenstiger"] is False
    assert d["prozent"] is None, \
        "an einer Annäherung gibt es kein Prozentmaß (Scheingenaugkeit)"

    # Auf gleicher Hoehe: 1.799,80 EUR - "≈ ±0,00 €", keine Richtung.
    gleich = karten.modelle([referenz, _knapp_o2(30.0, 0.0)],
                            _listungen(), _referenzen(), tarife,
                            lade_katalog(WURZEL))["modelle"][0]
    d0 = [k for k in gleich["karten"] if k["anbieter"] == "o2"][0]["delta"]
    assert d0["ungefaehr"] is True
    assert d0["betrag"] == 0.0 and d0["abstand"] == 0.0
    assert d0["guenstiger"] is False

    # Gegenprobe: ein echter Abstand (Anschluss 40,00 -> +40,00 EUR) ist
    # keine Annäherung - die Schwelle sortiert, sie streicht nicht.
    deutlich = karten.modelle([referenz, _knapp_o2(30.0, 40.0)],
                              _listungen(), _referenzen(), tarife,
                              lade_katalog(WURZEL))["modelle"][0]
    dw = [k for k in deutlich["karten"] if k["anbieter"] == "o2"][0]["delta"]
    assert dw["ungefaehr"] is False
    assert dw["betrag"] == 40.0 and dw["prozent"] == 2.2

    # Gegenprobe Strich: ohne Vodafone-Bündel und ohne eigenen Barpreis
    # gibt es keine Referenz - KEIN Delta (None), und der Strich der
    # Zeile meint "kein Angebot zum Vergleich", nicht "Abstand zu klein".
    ohne_vodafone = [l for l in _listungen() if l["anbieter"] != "Vodafone"]
    ohne = karten.modelle([_knapp_o2(30.25, 2.0)], ohne_vodafone,
                          _referenzen(), tarife,
                          lade_katalog(WURZEL))["modelle"][0]
    assert [k for k in ohne["karten"]
            if k["anbieter"] == "o2"][0]["delta"] is None


def test_delta_kurz_und_der_graph_traegen_das_ungefaehr():
    """Fix 2 (A2), die Anzeige: Zeile (delta_kurz) und Balken (G1-tspan)
    tragen "≈ +11,00 €" - dasselbe Format an beiden Orten, ohne Prozent
    (eine Annäherung mit auf die Zehntel gerundetem Prozent waere
    Scheingenaugkeit). Die delta_text-Einheit selbst haelt beide Welten:
    ungefaehr OHNE Prozentanteil, wesentlich MIT - unverändert."""
    tarife = {t["tarif_id"]: t for t in _tarife()}
    referenz = _xs_buendel(SKU_NEU, 30.0, HEUTE, tarif_monatlich=29.95)
    ergebnis = view.aufbereiten([_speicherform(referenz),
                                 _speicherform(_knapp_o2(30.25, 2.0))],
                                [], _listungen(), lade_katalog(WURZEL),
                                tarife=tarife)
    o2 = next(k for m in ergebnis["modelle"] for k in m["karten"]
              if k["anbieter"] == "o2")
    assert o2["delta_kurz"] == "≈ +11,00 €"
    assert "≈ +11,00 €" in grafik.balken(ergebnis["modelle"][0])

    from telco_radar.report import geraete_tco_band as tco_band
    assert tco_band.delta_text(11.0, 0.6, ungefaehr=True) == "≈ +11,00 €"
    assert tco_band.delta_text(-11.0, 0.6, ungefaehr=True) == "≈ −11,00 €"
    assert tco_band.delta_text(0.0, 0.0, ungefaehr=True) == "≈ ±0,00 €"
    assert tco_band.delta_text(None, None, ungefaehr=True) is None
    # Unveraendert: das wesentliche Delta mit Prozent (Band-Graph und
    # Antwort-Satz rechnen weiter darueber). Das Prozent kommt als
    # ABSOLUTER Wert - das Vorzeichen liefert der Euro-Betrag.
    assert tco_band.delta_text(-100.0, 9.1) == "−100,00 € · −9,1 %"


def test_die_gerenderte_zeile_zeigt_kleine_abstaende_mit_ungefaehr(tmp_path):
    """Fix 2 (A2) am gerenderten Blatt: die Δ-Spalte zeigt "≈ +11,00 €"
    und OHNE die Δ-Präfix-Klasse (mobil wuerde sonst "Δ ≈" stehen), der
    Delta-Satz im Rechenweg "≈ 11,00 € über der Vodafone-Referenz" ohne
    Prozent. Gegenproben am selben Blatt: das wesentliche o2-Delta
    (−679,05 € · −37,7 %) behält Prozent UND Präfix-Klasse, und das
    erneuerte Geraet zeigt weiterhin den Strich - "kein Angebot"."""
    s = _baue(tmp_path, ungefaehr_delta=True)
    tafel = s.select_one("#tafel-tco")
    o2_zeilen = tafel.select('.gr-bnd[data-anbieter="o2"]')
    assert len(o2_zeilen) == 3, "o2 neu, o2 knapp daneben, o2 erneuert"

    knapp = next(z for z in o2_zeilen
                 if "≈" in (z.select_one(".gr-bnd-delta").get_text() or ""))
    zelle = knapp.select_one(".gr-bnd-delta")
    assert zelle.get_text(strip=True) == "≈ +11,00 €"
    assert "gr-bnd-delta--wert" not in (zelle.get("class") or [])
    satz = vorlage_text(knapp.select_one(".gr-kk-delta"))
    assert "≈ 11,00 € über der Vodafone-Referenz" in satz, satz
    assert "%" not in satz and "unter" not in satz, satz

    deutlich = next(z for z in o2_zeilen
                    if z.get("data-zustand") == "neu" and z is not knapp)
    dzelle = deutlich.select_one(".gr-bnd-delta")
    assert dzelle.get_text(strip=True) == "−679,05 € · −37,7 %"
    assert "gr-bnd-delta--wert" in (dzelle.get("class") or [])
    dsatz = vorlage_text(deutlich.select_one(".gr-kk-delta"))
    assert "679,05 € (37,7 %) unter der Vodafone-Referenz" in dsatz, dsatz

    erneuert_zeile = tafel.select_one(
        '.gr-bnd[data-anbieter="o2"][data-zustand="refurbished"]')
    assert erneuert_zeile.select_one(".gr-bnd-delta").get_text(
        strip=True) == "–"


def test_ueber_zwei_zeitraeume_steht_kein_betrag_sondern_der_zustand():
    """P0-B-fix2 (Befund 3b): ueber zwei Zeitraeume gibt es KEINE Zahl.

    Bis hierher hiess dieser Test `test_annaeherung_nur_bei_gleicher_
    laufzeit_der_satz_sagt_je_monat` und hielt fest, dass bei
    verschiedener Laufzeit der Ø/Monat-Abstand danebensteht ("0,04 € je
    Monat über der Vodafone-Referenz", ohne "≈" - S1 der Diff-Pruefung
    vom 20.09.2026).

    Dieser Abstand ist selbst nicht belegt: `tco_model.Tco.monatlich`
    teilt JEDE Summe durch dieselben 24 Monate, eine 36-Monats-Summe
    durch 24 ist also kein Monatspreis, und das Vorzeichen des
    Vergleichs haengt an Tarifmonaten, die in der einen Zahl stecken und
    in der anderen nicht (1&1, Befund 3: 12 × 42,99 EUR jenseits des
    Horizonts gegen ein ausgewiesenes Delta von 79,74 EUR). Die Zeile
    traegt deshalb den BENANNTEN Zustand statt einer Zahl - und keinen
    numerischen Δ-Sortierschluessel (`data-delta` bleibt leer, die Zeile
    faellt aus der Rangfolge nach Δ).

    Der S1-Befund selbst bleibt geprueft: es steht KEIN "≈" und kein
    Euro-Betrag mehr da, wo der Bezug fehlt.

    Referenz (Vodafone Mobil XS, als 36-Monats-Zahl simuliert):
    1.799,80 EUR. o2 mit 24 Monaten: 1,00 + 24×29,95 + 24×45,04 =
    1.800,76 EUR - vier Cent im Monat darueber, aber nicht ueber
    denselben Zeitraum."""
    tarife = {t["tarif_id"]: t for t in _tarife()}
    referenz = _xs_buendel(SKU_NEU, 30.0, HEUTE, tarif_monatlich=29.95)
    o2_24 = Buendel(sku_id=SKU_NEU, anbieter="o2",
                    tarif_name="O2 Mobile on Demand M (24 Mon.)",
                    tarif_id="o2:on-demand-m", tarif_monatlich=29.95,
                    tarif_bindung_monate=24, geraet_zuzahlung=1.0,
                    geraet_monatsrate=45.04, laufzeit_monate=24,
                    anschlusspreis=0.0, zustand="neu",
                    quelle_url="https://example.de/o2/l24",
                    abgerufen_am=HEUTE)
    modell = karten.modelle([referenz, o2_24], _listungen(), _referenzen(),
                            tarife, lade_katalog(WURZEL))["modelle"][0]
    karte = next(k for k in modell["karten"] if k["anbieter"] == "o2")
    # Eine Referenz, deren Zahl 36 Monate traegt (1&1s Bauform) - hier
    # per `monate` simuliert, weil Vodafone im Bestand kein
    # zusammengelegtes Buendel verkauft.
    ref36 = {**modell["referenz"], "monate": 36}
    assert karten._delta(karte, ref36) is None, \
        "ueber zwei Zeitraeume gibt es keinen Betrag - auch keinen je Monat"
    zustand = karten.delta_zustand(karte, ref36)
    assert zustand["kurz"] == "andere Laufzeit"
    assert zustand["satz"] == ("Kein Abstand zur Vodafone-Referenz: diese "
                               "Zahl trägt 24 Monate, die Referenz 36 "
                               "Monate.")

    # Gegenprobe: GLEICHER Zeitraum, kleiner Abstand - die Annaeherung
    # bleibt, Fix 2 (A2) unveraendert fuer den Fall, fuer den er gebaut
    # war, und KEIN benannter Zustand daneben.
    d24 = karten._delta(karte, modell["referenz"])
    assert d24["gleiche_laufzeit"] is True and d24["betrag"] == 0.96
    assert d24["ungefaehr"] is True
    assert karten.delta_zustand(karte, modell["referenz"]) is None

    # Am ECHTEN Makro: der Zustand steht in der Δ-Spalte und als Satz im
    # Rechenweg, `data-delta` ist leer - kein "≈", kein Euro-Betrag.
    from telco_radar.report import html as html_mod
    karte["delta"] = None
    karte["delta_kurz"] = None
    karte["delta_zustand"] = zustand
    zeile = BeautifulSoup(html_mod._env().from_string(
        '{% from "_geraete_buendel.html.j2" import buendelzeile %}'
        "{{ buendelzeile(k) }}").render(k=karte), "html.parser")
    zelle = zeile.select_one(".gr-bnd-delta")
    assert zelle.get_text(strip=True) == "andere Laufzeit"
    assert "gr-bnd-delta--wert" not in (zelle.get("class") or [])
    assert zeile.select_one(".gr-bnd")["data-delta"] == ""
    assert zeile.select_one(".gr-kk-delta") is None, \
        "der laute Delta-Satz in Alarmfarbe steht hier nicht"
    satz = vorlage_text(zeile.select_one(".gr-kk-luecke"))
    assert satz == zustand["satz"], satz
    assert "≈" not in satz and "€" not in satz, satz
