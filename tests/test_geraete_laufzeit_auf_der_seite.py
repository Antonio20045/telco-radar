"""P0-B-fix2: die Ratenlaufzeit auf der SEITE - Schluessel, Etikett, Delta.

Vier Befunde des Pruefers vom 21.09.2026, vier Testgruppen. Alle vier
betreffen die Lesepfade der Geraeteseite, nicht den Rechenkern (der steht
seit P0-B-fix1) - und alle vier machten aus einer gemessenen Laufzeit
wieder eine geratene 24 oder eine Aussage, die niemand gemessen hat.

  1. `geraete_tco_karten.modelle` entdoppelte je (Anbieter, Tarif,
     `karte["laufzeit"]`, Zustand) - und `karte["laufzeit"]` ist die
     KONSTANTE `LAUFZEIT` (= `TCO_HORIZONT` = 24), also fuer jede Karte
     dieselbe Zahl. Zwei Zahlweisen desselben Tarifs ueberschrieben sich
     damit weiter, obwohl B1 die Laufzeit in den Bestandsschluessel gelegt
     hat.
  2. `geraete_zeitreihe._messungen` verwarf jede ID, deren Form es nicht
     kannte - Stand UND Historie -, und die Zeitreihe verschwand
     ersatzlos.
  3. Das Etikett "Kosten über 24 Monate" stand auch an einer Zahl, die 36
     Monate Tarif UND Geraet traegt (1&1s Buendelmonatspreis), und das
     Delta gegen die 24-Monats-Referenz trug ein Vorzeichen, das die
     Zahlen nicht belegen.
  4. Zwei Lesepfade (`buendel_aus_listungen`, `_buendel_aus_messung`)
     rieten `int(... or 24)`, wo die Quelle keine Dauer nennt.

Die Gegenproben stehen JE Test: ein Test, der nur zeigt, dass etwas fehlt,
waere auch mit einer Seite gruen, die ueberhaupt nichts mehr zeigt.
"""
from __future__ import annotations

import json
import pathlib

import yaml
from bs4 import BeautifulSoup

from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import geraete_tco_karten as karten
from telco_radar.report import geraete_view, geraete_zeitreihe
from telco_radar.report.html import _env
from telco_radar.tco_model import Buendel, SimOnlyReferenz

WURZEL = pathlib.Path(__file__).resolve().parents[1]
HEUTE = "2026-09-20"
SKU = "apple-iphone-17-pro-256gb-schwarz"
DEVICE = "apple-iphone-17-pro"
MODELL = "apple-iphone-17-pro-256"


def vorlage_text(el) -> str:
    """Text eines Elements, AUCH aus einem <template> (siehe
    `tests/test_geraete_tco_zustand.vorlage_text` - dieselbe Lage, die
    der Rechenweg-Pool seit dem P4-Fix erzeugt)."""
    return " ".join("".join(el.find_all(string=True)).split())


def zeile_html(karte: dict) -> BeautifulSoup:
    """EINE Buendelzeile am ECHTEN Makro - keine Textkopie."""
    return BeautifulSoup(_env().from_string(
        '{% from "_geraete_buendel.html.j2" import buendelzeile %}'
        "{{ buendelzeile(k) }}").render(k=karte), "html.parser")


# --------------------------------------------------------------------------
# Bausteine fuer die Kartenansicht
# --------------------------------------------------------------------------

def _listung(anbieter, preis, sku=SKU):
    return {"id": f"{anbieter.lower()}--{sku}", "sku_id": sku,
            "device_id": DEVICE, "anbieter": anbieter,
            "anbieter_typ": "netzbetreiber", "netz": anbieter,
            "speicher_gb": 256, "farbe_roh": "Schwarz",
            "farbe_normalisiert": "schwarz", "zustand": "neu",
            "first_seen": "2026-09-01", "last_verified": HEUTE,
            "status": "aktiv", "missed_checks": 0,
            "preis_ohne_vertrag": preis, "erstpreis": preis,
            "erstpreis_art": "ohne_vertrag", "erstpreis_am": "2026-09-01",
            "quelle_url": f"https://example.de/{anbieter.lower()}/{sku}",
            "abgerufen_am": HEUTE, "verfuegbarkeit": "lieferbar",
            "confidence": "hoch", "einstiege": ["https://example.de/l"]}


def _congstar(laufzeit: int, rate: float) -> Buendel:
    """Dieselbe Zahlweise, ANDERE Ratenlaufzeit - congstar bietet 24 und
    36 Raten zum selben Tarif an (`config/geraete_quellen.yaml`,
    `tests/test_geraete_buendel_congstar.py`)."""
    return Buendel(sku_id=SKU, anbieter="congstar",
                   tarif_name="Allnet Flat S", tarif_id="cs:s",
                   tarif_id_guete="hoch", tarif_monatlich=15.0,
                   tarif_bindung_monate=24, geraet_zuzahlung=1.0,
                   geraet_monatsrate=rate, laufzeit_monate=laufzeit,
                   anschlusspreis=0.0, zustand="neu",
                   quelle_url="https://example.de/congstar/s",
                   abgerufen_am=HEUTE)


def _einsundeins(laufzeit=36) -> Buendel:
    """1&1: EIN Monatsbetrag fuer Tarif UND Geraet (§ 13.2) ueber 36
    Monate - die Werte der echten Fixture (340,00 Zuzahlung, 42,99 im
    Monat, 39,90 Anschlusspreis, siehe Befund 3)."""
    return Buendel(sku_id=SKU, anbieter="1&1",
                   tarif_name="All-Net-Flat S",
                   buendel_monatlich=42.99, geraet_zuzahlung=340.0,
                   laufzeit_monate=laufzeit, anschlusspreis=39.9,
                   zustand="neu", quelle_url="https://example.de/1und1/s",
                   abgerufen_am=HEUTE)


def _vodafone() -> Buendel:
    """Ein eigenes Buendel mit getrenntem Tarif und Rate - seine Zahl
    traegt 24 Tarifmonate und ist damit die Referenz."""
    return Buendel(sku_id=SKU, anbieter="Vodafone",
                   tarif_name="Vodafone Mobil XS", tarif_id="vf:xs",
                   tarif_id_guete="hoch", tarif_monatlich=29.95,
                   tarif_bindung_monate=24, geraet_zuzahlung=1.0,
                   geraet_monatsrate=45.0, laufzeit_monate=24,
                   anschlusspreis=0.0, zustand="neu",
                   quelle_url="https://example.de/vf/xs",
                   abgerufen_am=HEUTE)


def _tarife():
    return {t["tarif_id"]: t for t in (
        {"anbieter": "congstar", "name": "Allnet Flat S", "tarif_id": "cs:s",
         "art": "mobilfunk", "grundgebuehr": 15.0, "laufzeit_monate": 24,
         "datenvolumen_gb": 50,
         "preisphasen": [{"von_monat": 1, "bis_monat": None, "betrag": 15.0}],
         "dokument_url": "https://example.de/pib/cs-s",
         "abgerufen_am": HEUTE, "confidence": {}, "fundstellen": {}},
        {"anbieter": "Vodafone", "name": "Vodafone Mobil XS",
         "tarif_id": "vf:xs", "art": "mobilfunk", "grundgebuehr": 29.95,
         "laufzeit_monate": 24, "datenvolumen_gb": 18,
         "preisphasen": [{"von_monat": 1, "bis_monat": None,
                          "betrag": 29.95}],
         "dokument_url": "https://example.de/pib/vf-xs",
         "abgerufen_am": HEUTE, "confidence": {}, "fundstellen": {}})}


def _referenzen():
    return [SimOnlyReferenz(anbieter="Vodafone", tarif_name="Vodafone Mobil XS",
                            tarif_id="vf:xs", tarif_sim_only_monatlich=29.95,
                            quelle_url="https://example.de/pib/vf-xs",
                            abgerufen_am=HEUTE)]


def _modell(buendel, listungen=None):
    ergebnis = karten.modelle(buendel, listungen or [_listung("Vodafone",
                                                              1199.9)],
                              _referenzen(), _tarife(),
                              lade_katalog(WURZEL), heute=HEUTE)
    treffer = [m for m in ergebnis["modelle"] if m["id"] == MODELL]
    assert treffer, f"kein Modellblock {MODELL}: {ergebnis['modelle']}"
    return treffer[0]


# --------------------------------------------------------------------------
# 1. Der Kartenschluessel traegt die GEMESSENE Ratenlaufzeit (Befund 1)
# --------------------------------------------------------------------------

def test_zwei_ratenlaufzeiten_desselben_tarifs_sind_zwei_zeilen():
    """Befund 1: 918,00 EUR in 24 Raten und in 36 Raten sind ZWEI
    Angebote - kein Angebot verdraengt das andere.

    Gegen den alten Stand rot: der Schluessel trug `karte["laufzeit"]`,
    also die Konstante 24 fuer beide, und `_angebot_rang` liess genau eine
    Zeile uebrig.
    """
    modell = _modell([_congstar(36, 25.5), _congstar(24, 38.25),
                      _vodafone()])
    cs = [k for k in modell["karten"] if k["anbieter"] == "congstar"]
    assert len(cs) == 2, \
        "zwei Ratenlaufzeiten desselben Tarifs sind zwei Zeilen"
    assert sorted(k["raten_laufzeit"] for k in cs) == [24, 36]
    # Dieselbe Zahl, die den Schluessel traegt, steht auch am Modell -
    # eine zweite Definition waere eine zweite Wahrheit.
    assert modell["laufzeiten"] == [24, 36]
    # Beide Zeilen stehen wirklich da, jede mit ihrer Ratenzahl.
    texte = [vorlage_text(zeile_html(k).select_one(".gr-kk-bau")) for k in cs]
    assert any("36 Raten à 25,50 €" in t for t in texte), texte
    assert any("24 Raten à 38,25 €" in t for t in texte), texte

    # GEGENPROBE: EIN congstar-Buendel ergibt EINE Zeile - der Test zaehlt
    # nicht einfach alles mit, was im Bestand steht.
    einzeln = _modell([_congstar(36, 25.5), _vodafone()])
    nur_eins = [k for k in einzeln["karten"] if k["anbieter"] == "congstar"]
    assert len(nur_eins) == 1
    assert nur_eins[0]["raten_laufzeit"] == 36
    # Die 24 in dieser Liste ist die des Vodafone-Buendels, nicht eine
    # zweite congstar-Variante.
    assert einzeln["laufzeiten"] == [24, 36]


def test_zwei_farben_derselben_laufzeit_bleiben_eine_zeile():
    """Die Entdoppelung selbst bleibt scharf: dasselbe Geraet in zwei
    Farben ist zweimal derselbe Preis (B.3) - nur die LAUFZEIT ist neu im
    Schluessel, nicht die Farbe."""
    blau = _congstar(36, 25.5)
    blau.sku_id = SKU.replace("schwarz", "blau")
    modell = _modell([_congstar(36, 25.5), blau, _vodafone()],
                     listungen=[_listung("Vodafone", 1199.9),
                                _listung("congstar", 1249.0),
                                _listung("congstar", 1249.0,
                                         sku=SKU.replace("schwarz", "blau"))])
    cs = [k for k in modell["karten"] if k["anbieter"] == "congstar"]
    assert len(cs) == 1, "zwei Farben sind EIN Angebot"


# --------------------------------------------------------------------------
# 3. Etikett und Delta sagen die Wahrheit (Befund 3)
# --------------------------------------------------------------------------

def test_ein_buendelmonatspreis_ueber_36_monate_nennt_seinen_zeitraum():
    """Befund 3a: 340,00 + 36 × 42,99 + 39,90 = 1.927,54 EUR sind KEINE
    "Kosten über 24 Monate" - in dieser Summe stecken 36 Monate Tarif und
    Geraet zusammen.

    Gegen den alten Stand rot: `label` war die Konstante "Kosten über 24
    Monate" fuer jede Karte.
    """
    modell = _modell([_einsundeins(), _vodafone()])
    eins = next(k for k in modell["karten"] if k["anbieter"] == "1&1")
    assert eins["belastbar"] and eins["gesamt"] == 1927.54
    assert eins["leitzahl_monate"] == 36
    assert eins["label"] == "Kosten über 36 Monate"
    text = vorlage_text(zeile_html(eins))
    assert "1.927,54 € Kosten über 36 Monate" in text, text
    assert "Kosten über 24 Monate" not in text, text
    assert "Gerechnet über 36 Monate" in text, text

    # GEGENPROBE: die aufgeteilte Form (Tarif und Rate getrennt) traegt
    # weiter 24 - dort sind es wirklich 24 Tarifmonate, und die Raten
    # jenseits stehen als Restschuld daneben.
    vf = next(k for k in modell["karten"]
              if k["anbieter"] == "Vodafone" and k["sku_id"])
    assert vf["leitzahl_monate"] == 24
    assert vf["label"] == "Kosten über 24 Monate"


def test_ueber_zwei_zeitraeume_steht_der_zustand_statt_eines_vorzeichens():
    """Befund 3b: das Delta gegen die 24-Monats-Referenz wird fuer so ein
    Buendel NICHT als Zahl gefuehrt.

    Die Unvergleichbarkeit ist GROESSER als der Abstand: 12 × 42,99 =
    515,88 EUR liegen jenseits des Horizonts, davon nach dem Tarifstamm
    mindestens 12 × 14,99 = 179,88 EUR reiner Tarif - gegen ein
    ausgewiesenes Delta von 79,74 EUR. Ein Vorzeichen, das nicht belegt
    ist, wird nicht angezeigt (Clean Code 4).

    Gegen den alten Stand rot: dort stand ein Δ mit Vorzeichen (bis B1 ein
    Euro-Betrag, danach der Ø/Monat-Abstand - beide aus zwei Summen
    verschiedener Zeitraeume).
    """
    modell = _modell([_einsundeins(), _vodafone()])
    eins = next(k for k in modell["karten"] if k["anbieter"] == "1&1")
    assert eins["delta"] is None, "kein Betrag ueber zwei Zeitraeume"
    assert eins["delta_zustand"]["kurz"] == "andere Laufzeit"
    assert "36 Monate, die Referenz 24 Monate" in eins["delta_zustand"]["satz"]

    zeile = zeile_html(eins)
    zelle = zeile.select_one(".gr-bnd-delta")
    assert zelle.get_text(strip=True) == "andere Laufzeit"
    # Kein Zahlenwert: kein Δ-Praefix und KEIN Sortierschluessel - die
    # Zeile faellt aus der Rangfolge nach Δ heraus.
    assert "gr-bnd-delta--wert" not in (zelle.get("class") or [])
    assert zeile.select_one(".gr-bnd")["data-delta"] == ""
    assert "über der Vodafone-Referenz" not in vorlage_text(zeile)
    assert "unter der Vodafone-Referenz" not in vorlage_text(zeile)
    # Der Satz steht als benannte Luecke im Rechenweg - zurueckgenommen,
    # nicht als lauter Delta-Satz in Alarmfarbe (`gr-kk-delta`).
    assert zeile.select_one(".gr-kk-delta") is None
    assert vorlage_text(zeile.select_one(".gr-kk-luecke")) == \
        eins["delta_zustand"]["satz"]

    # GEGENPROBE: die 24-Monats-Zeile desselben Modells bekommt ihr Delta
    # wie bisher - mit Betrag, Prozent und Vorzeichen.
    modell2 = _modell([_congstar(36, 25.5), _vodafone()])
    cs = next(k for k in modell2["karten"] if k["anbieter"] == "congstar")
    assert cs["leitzahl_monate"] == 24
    assert cs["delta_zustand"] is None
    assert cs["delta"]["betrag"] is not None
    assert cs["delta"]["gleiche_laufzeit"] is True
    zeile2 = zeile_html(cs)
    assert zeile2.select_one(".gr-bnd")["data-delta"] == str(
        cs["delta"]["betrag"])


# --------------------------------------------------------------------------
# 4. Kein Lesepfad raet mehr eine 24 (Befund 4)
# --------------------------------------------------------------------------

def test_eine_listung_ohne_laufzeit_bekommt_keine_geratene_24():
    """`buendel_aus_listungen` las `int(... or 24)`.

    Gegen den alten Stand rot: dort trug das Buendel 24 Monate, rechnete
    24 × 44,99 EUR und stand mit einer belastbaren Zahl da, die niemand
    gemessen hat.
    """
    listung = dict(_listung("1&1", None), preis_mit_vertrag_ab=44.99,
                   tarif_referenz="All-Net-Flat S")
    listung.pop("laufzeit_monate", None)
    b = karten.buendel_aus_listungen([listung])
    assert len(b) == 1
    assert b[0].laufzeit_monate is None, "keine Dauer in der Quelle"

    karte = karten._karte(b[0], None, None, lade_katalog(WURZEL),
                          {SKU: (DEVICE, 256)}, zustand="neu", heute=HEUTE)
    assert karte["belastbar"] is False
    assert "Ratenlaufzeit" in karte["luecken"]
    assert karte["gesamt"] is None
    assert karte["label"] == "Kosten – Laufzeit nicht gemessen"
    # Regel 9: die Zeile zeigt den Ausfall, statt "nichts gefunden"
    # vorzutaeuschen.
    text = vorlage_text(zeile_html(karte))
    assert "keine belastbare Zahl" in text
    assert karte["leer_grund"] == (
        "Die Ratenlaufzeit dieses Bündels ist nicht erhoben – ohne die "
        "Zahl der Monate ergibt der Monatsbetrag keine Gesamtsumme."), \
        karte["leer_grund"]
    assert karte["leer_grund"] in text, "der Grund steht auf der Zeile"

    # GEGENPROBE: MIT gemessener Laufzeit rechnet derselbe Weg wie immer.
    mit = karten.buendel_aus_listungen(
        [dict(listung, laufzeit_monate=24)])[0]
    assert mit.laufzeit_monate == 24
    karte_mit = karten._karte(mit, None, None, lade_katalog(WURZEL),
                              {SKU: (DEVICE, 256)}, zustand="neu",
                              heute=HEUTE)
    assert karte_mit["leitzahl_monate"] == 24


def test_eine_rate_ohne_laufzeit_wirft_keinen_typeerror():
    """Die Ratensumme ist `float * laufzeit` - seit P0-B-fix1 kann die
    Laufzeit `None` sein.

    Gegen den alten Stand rot mit `TypeError: unsupported operand
    type(s) for *: 'float' and 'NoneType'` - die ganze Seite waere
    ausgefallen.
    """
    b = Buendel(sku_id=SKU, anbieter="o2", tarif_name="O2 Mobile M",
                tarif_id="o2:m", tarif_monatlich=19.99,
                tarif_bindung_monate=24, geraet_zuzahlung=1.0,
                geraet_monatsrate=30.5, laufzeit_monate=None,
                anschlusspreis=0.0, zustand="neu",
                quelle_url="https://example.de/o2/m", abgerufen_am=HEUTE)
    karte = karten._karte(b, None, None, lade_katalog(WURZEL),
                          {SKU: (DEVICE, 256)}, zustand="neu", heute=HEUTE)
    assert karte["raten_summe"] is None, "keine Ratensumme ohne ihre Monate"
    assert karte["offene_raten"] is None, \
        "unbekannt viele offene Raten sind nicht null offene Raten"
    assert karte["belastbar"] is False
    assert "Ratenlaufzeit" in karte["luecken"]
    # Und die Zeile rendert (kein halbes Dokument).
    assert "keine belastbare Zahl" in vorlage_text(zeile_html(karte))

    # GEGENPROBE: mit Laufzeit steht die Ratensumme da wie immer.
    b.laufzeit_monate = 36
    karte36 = karten._karte(b, None, None, lade_katalog(WURZEL),
                            {SKU: (DEVICE, 256)}, zustand="neu", heute=HEUTE)
    assert karte36["raten_summe"] == 1098.0
    assert karte36["offene_raten"] == 12


# --------------------------------------------------------------------------
# 2. + 4. Die Zeitreihe: unbekannte ID-Form und ungeratene Laufzeit
# --------------------------------------------------------------------------

_KATALOG = {"geraete": [
    {"hersteller": "Apple", "modell": "iPhone 17 Pro", "generation": 17,
     "marktstart": "2025-09-19", "speicher": [256], "segment": "premium"}]}
_FARBEN = {"farben": {"schwarz": ["Schwarz"]}}
_QUELLEN = {"anbieter": [
    {"name": "Vodafone", "typ": "netzbetreiber", "rang": 1, "eigen": True,
     "methode": "ldjson", "basis_url": "https://www.vodafone.de",
     "einstiege": [{"url": "https://www.vodafone.de/handys"}]},
    {"name": "o2", "typ": "netzbetreiber", "rang": 2, "methode": "ldjson",
     "basis_url": "https://www.o2online.de",
     "einstiege": [{"url": "https://www.o2online.de/handys"}]}]}


def _zeitreihe_wurzel(tmp_path: pathlib.Path, buendel_id: str,
                      laufzeit=24) -> tuple:
    """Ein Bestand mit EINEM o2-Buendel und drei Messtagen.

    `buendel_id` ist der Schluessel, unter dem Stand und Historie
    einander finden muessen - der Test setzt dort auch eine ID, deren Form
    dieses Projekt nicht kennt.
    """
    root = tmp_path / "zr"
    (root / "config").mkdir(parents=True)
    for name, daten in (("geraete_katalog.yaml", _KATALOG),
                        ("farben.yaml", _FARBEN),
                        ("geraete_quellen.yaml", _QUELLEN)):
        (root / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
    state = root / "data" / "state"
    state.mkdir(parents=True)
    (state / "geraete_db.json").write_text(json.dumps({
        "updated": HEUTE, "anbieter": {"o2": {"laeufe": 3, "funde_gesamt": 1}},
        "listungen": [_listung("o2", 1099.0)]}), encoding="utf-8")
    (state / "geraete_preise.jsonl").write_text("", encoding="utf-8")
    satz = {"id": buendel_id, "sku_id": SKU, "anbieter": "o2",
            "tarif_name": "O2 Mobile M", "tarif_id": "o2:m",
            "tarif_id_guete": "hoch", "tarif_monatlich": 20.0,
            "geraet_zuzahlung": 1.0, "geraet_monatsrate": 25.0,
            "laufzeit_monate": laufzeit, "anschlusspreis": 0.0,
            "zustand": "neu", "rabatte": [],
            "quelle_url": "https://example.de/o2/m", "abgerufen_am": HEUTE,
            "first_seen": "2026-09-18", "last_verified": HEUTE}
    (state / "geraete_tco.json").write_text(json.dumps(
        {"updated": HEUTE, "buendel": [satz], "sim_only": []}),
        encoding="utf-8")
    zeilen = []
    for tag, rate in (("2026-09-18", 25.0), ("2026-09-19", 24.0),
                      (HEUTE, 25.0)):
        z = dict(satz, datum=tag, geraet_monatsrate=rate,
                 gesamt=round(1.0 + 24 * 20.0 + (laufzeit or 24) * rate, 2))
        if laufzeit is None:
            z.pop("laufzeit_monate")
        zeilen.append(z)
    if laufzeit is None:
        roh = json.loads((state / "geraete_tco.json").read_text("utf-8"))
        roh["buendel"][0].pop("laufzeit_monate")
        (state / "geraete_tco.json").write_text(json.dumps(roh),
                                                encoding="utf-8")
    (state / "geraete_tco_historie.jsonl").write_text(
        "\n".join(json.dumps(z) for z in zeilen) + "\n", encoding="utf-8")
    (state / "tarife.jsonl").write_text(json.dumps(
        {"anbieter": "o2", "name": "O2 Mobile M", "tarif_id": "o2:m",
         "art": "mobilfunk", "grundgebuehr": 20.0, "laufzeit_monate": 24,
         "datenvolumen_gb": 50,
         "preisphasen": [{"von_monat": 1, "bis_monat": None,
                          "betrag": 20.0}],
         "dokument_url": "https://example.de/pib/o2-m",
         "abgerufen_am": HEUTE, "confidence": {}, "fundstellen": {}}) + "\n",
        encoding="utf-8")
    return root, state


def _punkte(root: pathlib.Path, state: pathlib.Path) -> dict:
    """Wie viele Messungen die Zeitreihe aus dem Bestand liest - und wie
    viele Punkte davon im fertigen SVG stehen."""
    g = geraete_view.aufbereiten(state, lade_quellen(root),
                                 lade_katalog(root), heute=HEUTE)
    tco = g["tco"]
    mess = geraete_zeitreihe._messungen(state, tco)
    paare = geraete_zeitreihe.aufbereiten(state, tco).get("paare") or []
    return {"reihen": sum(len(anbieter) for anbieter in mess.values()),
            "punkte": sum(len(tage) for anbieter in mess.values()
                          for tage in anbieter.values()),
            "kreise": sum(p.get("svg_breit", "").count("<circle")
                          for p in paare)}


def test_eine_unbekannte_id_form_behaelt_ihre_messungen(tmp_path):
    """Befund 2: `buendel--o2-1` hat weder vier noch fuenf Segmente.

    Gegen den alten Stand rot: `id_aus_satz` gab `None`, Stand UND
    Historie verwarfen den Satz per `continue`, und die Zeitreihe des
    Modells verschwand ersatzlos (genau der Fehlschlag von
    `tests/test_geraete_reiter_browser.py::test_die_startansicht_traegt_
    genau_die_pflichtgrafik`). Eine ID ist ein OPAKER Schluessel: wer ihre
    Form nicht kennt, verwendet sie unveraendert weiter.
    """
    root, state = _zeitreihe_wurzel(tmp_path, "buendel--o2-1")
    gemessen = _punkte(root, state)
    assert gemessen["reihen"] >= 1, \
        "die unbekannte ID-Form kostet die ganze Zeitreihe"
    assert gemessen["punkte"] == 3, "drei Messtage, drei Punkte"
    assert gemessen["kreise"] >= 3, "die Punkte stehen auch im Bild"

    # GEGENPROBE: dieselbe Lage mit einer ID der HEUTIGEN Form ergibt
    # genau dasselbe Bild - der Test misst die Zuordnung, nicht die
    # Fixture.
    root2, state2 = _zeitreihe_wurzel(
        tmp_path / "bekannt", "buendel--o2--" + SKU + "--o2-mobile-m--24m")
    bekannt = _punkte(root2, state2)
    assert (bekannt["reihen"], bekannt["punkte"]) == \
        (gemessen["reihen"], gemessen["punkte"])


def test_der_schluessel_verwirft_nur_einen_satz_ohne_jede_id():
    """Die EINE Stelle der Zuordnung - und ihre Grenze.

    Eine ID von vor B1 (vier Segmente) wird migriert, eine heutige bleibt,
    eine unbekannte Form geht unveraendert durch, und nur ein Satz OHNE
    jede ID hat keinen Schluessel.
    """
    schluessel = geraete_zeitreihe.buendel_schluessel
    assert schluessel({"id": "buendel--o2--sku--tarif",
                       "laufzeit_monate": 36}) == \
        "buendel--o2--sku--tarif--36m"
    assert schluessel({"id": "buendel--o2--sku--tarif--24m"}) == \
        "buendel--o2--sku--tarif--24m"
    assert schluessel({"id": "buendel--o2-1"}) == "buendel--o2-1"
    assert schluessel({"id": ""}) is None
    assert schluessel({}) is None


def test_eine_historienzeile_ohne_laufzeit_wird_nicht_auf_24_geraten(tmp_path):
    """Befund 4: `int(satz.get("laufzeit_monate") or 24)`.

    Gegen den alten Stand rot: die Messung bekam eine geratene 24, und
    der Punkt stand auf einer Hoehe (1.081,00 EUR bei 25,00 EUR Rate), die
    aus keiner Messung folgt. Jetzt gibt es keinen Punkt - eine erfundene
    Hoehe ist schlechter als eine Luecke (Modulkopf-Regel 2).
    """
    root, state = _zeitreihe_wurzel(tmp_path, "buendel--o2--sku--o2-m",
                                    laufzeit=None)
    ohne = _punkte(root, state)
    assert ohne["punkte"] == 0, "kein Punkt aus einer geratenen Laufzeit"

    satz = json.loads((state / "geraete_tco_historie.jsonl")
                      .read_text("utf-8").splitlines()[0])
    stand = json.loads((state / "geraete_tco.json").read_text("utf-8"))
    b = geraete_zeitreihe._buendel_aus_messung(
        {"satz": satz, "stand": stand["buendel"][0]})
    assert b is not None and b.laufzeit_monate is None
    assert geraete_zeitreihe._wert_aus_messung(
        {"satz": satz, "stand": stand["buendel"][0]}) is None

    # GEGENPROBE: MIT gemessener Laufzeit rechnet dieselbe Stelle ihre
    # drei Punkte wie immer.
    root2, state2 = _zeitreihe_wurzel(tmp_path / "mit",
                                      "buendel--o2--sku--o2-m", laufzeit=24)
    assert _punkte(root2, state2)["punkte"] == 3
