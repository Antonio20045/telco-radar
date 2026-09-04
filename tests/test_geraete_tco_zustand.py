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

SKU_NEU = "apple-iphone-15-128gb-schwarz"
SKU_ERNEUERT = "apple-iphone-15-128gb-schwarz-refurbished"
HEUTE = "2026-09-04"


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
    return [{"anbieter": "o2", "name": "O2 Mobile on Demand M",
             "tarif_id": "o2:on-demand-m", "art": "mobilfunk",
             "grundgebuehr": 19.99, "laufzeit_monate": 24,
             "preisphasen": [{"von_monat": 1, "bis_monat": None,
                              "betrag": 19.99}],
             "dokument_url": "https://example.de/pib/o2-m",
             "abgerufen_am": HEUTE, "confidence": {}, "fundstellen": {}},
            {"anbieter": "Vodafone", "name": "Vodafone Mobil XS",
             "tarif_id": "vf:xs", "art": "mobilfunk",
             "grundgebuehr": 29.95, "laufzeit_monate": 24,
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
            "geraet_zuzahlung": b.geraet_zuzahlung,
            "geraet_monatsrate": b.geraet_monatsrate,
            "laufzeit_monate": b.laufzeit_monate,
            "anschlusspreis": b.anschlusspreis, "rabatte": [],
            "zustand": b.zustand, "quelle_url": b.quelle_url,
            "abgerufen_am": b.abgerufen_am, "first_seen": HEUTE,
            "last_verified": HEUTE}


def _baue(tmp_path: pathlib.Path, erneuert: bool = True,
          punkte: list | None = None) -> BeautifulSoup:
    """`punkte` ersetzt die Preishistorie - `test_geraete_preis_mehrdeutig`
    stellt darueber Tage mit zwei Preisen derselben Listung."""
    root = tmp_path / ("mit" if erneuert else "ohne")
    (root / "config").mkdir(parents=True)
    for name, daten in (("geraete_katalog.yaml", _KATALOG),
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
    (state / "tarife.jsonl").write_text(
        "\n".join(json.dumps(t) for t in _tarife()) + "\n", encoding="utf-8")
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


def test_die_gerenderte_seite_traegt_das_etikett_auf_karte_balken_und_tabelle(tmp_path):
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    karten_o2 = tafel.select('.gr-kkarte[data-anbieter="o2"]')
    assert len(karten_o2) == 2

    erneuert = tafel.select_one('.gr-kkarte[data-zustand="refurbished"]')
    assert erneuert is not None
    assert erneuert.select_one(".gr-kk-marke--zustand").get_text(strip=True) == "erneuert"
    assert erneuert.select_one(".gr-kk-delta") is None, \
        "das erneuerte Geraet ist kein Konkurrent des Neugeraets"
    neu = tafel.select_one('.gr-kkarte[data-anbieter="o2"][data-zustand="neu"]')
    assert neu.select_one(".gr-kk-marke--zustand") is None
    assert neu.select_one(".gr-kk-delta") is not None

    balken = tafel.select("svg.gr-g1 .gr-g1-zustand")
    assert [b.get_text(strip=True) for b in balken] == ["erneuert"]

    zeile = tafel.select_one('#gr-tco-tabelle tr[data-zustand="refurbished"]')
    assert zeile is not None
    assert zeile.select_one(".gr-t-zustand").get_text(strip=True) == "erneuert"

    band = " ".join(tafel.select_one(".gr-mband").get_text(" ", strip=True).split())
    assert "2 Angebote · davon 1 erneuert" in band
    # Die leere Vodafone-Karte gibt es hier nicht, die gefuellte ist die
    # Referenzrechnung - und die heisst nicht "unser Angebot" (S3).
    marken = [m.get_text(strip=True) for m in tafel.select(".gr-kk-marke")]
    assert "unser Angebot" not in marken


def test_ohne_erneuertes_buendel_kein_etikett(tmp_path):
    """Die Gegenprobe: dieselbe Seite ohne das zweite Buendel."""
    s = _baue(tmp_path, erneuert=False)
    tafel = s.select_one("#tafel-tco")
    assert len(tafel.select('.gr-kkarte[data-anbieter="o2"]')) == 1
    assert not tafel.select(".gr-kk-marke--zustand")
    assert not tafel.select(".gr-g1-zustand")
    assert not tafel.select(".gr-t-zustand")
    assert "erneuert" not in tafel.get_text(" ")
