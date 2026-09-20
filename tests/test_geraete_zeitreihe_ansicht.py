"""E2 (AUFTRAG_GERAETE_EINE_SEITE_V2 §1a, 16.09.2026): die TCO-ZEITREIHE
als Aufbereitung - `report/geraete_zeitreihe.py`.

Der genehmigte Prototyp (docs/entwuerfe/geraete-eine-seite-2026-09-16,
entwurf-v2.html, DOM-bewiesen) als SERVERSEITIGE Produktion:

  - Y-Achse TCO-24 in EUR mit Ticks, X-Achse das DATUM mit den ECHTEN
    Messtagen als Ticks und echten Datumsabstaenden (keine ordinale Achse).
  - Je Anbieter eine Linie mit einem Punkt je Messung; NICHTS interpoliert
    (unter 2 Punkten: kein Linienzug, nur der Punkt).
  - Wert-Labels am letzten (gross) und ersten (klein) Punkt; Vodafone rot
    mit Etikett "unser Angebot"; Beleg-Link je Anbieter am Linienende.
  - Startzustand = Modell x Band mit den meisten Anbietern, dann Punkten -
    AUS DEN DATEN gerechnet, nichts hardcodiert.
  - Antwort-Satz nennt die Leitzahl beim Namen („Kosten über 24 Monate");
    EIN Lueckensatz mit Namen und Alternativ-Baendern samt Betrag
    (Antonio 9b.7 / §4.5).

Alle Zahlen entstehen in Python; der Client setzt nur fertige Knoten.
"""
from __future__ import annotations

import json
import pathlib

import pytest
import yaml

from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import geraete_view, geraete_zeitreihe

HEUTE = "2026-09-16"

_KATALOG = {"geraete": [
    {"hersteller": "Apple", "modell": "iPhone 17 Pro", "generation": 17,
     "marktstart": "2025-09-19", "speicher": [256], "segment": "premium"},
    {"hersteller": "Samsung", "modell": "Galaxy S26", "generation": 26,
     "marktstart": "2026-01-30", "speicher": [256], "segment": "premium"},
    {"hersteller": "Google", "modell": "Pixel 11", "generation": 11,
     "marktstart": "2026-08-20", "speicher": [128], "segment": "premium"},
]}
_FARBEN = {"farben": {"schwarz": ["Schwarz"]}}
_QUELLEN = {"anbieter": [
    {"name": "Vodafone", "typ": "netzbetreiber", "rang": 1, "eigen": True,
     "methode": "ldjson", "basis_url": "https://www.vodafone.de",
     "einstiege": [{"url": "https://www.vodafone.de/handys"}]},
    {"name": "o2", "typ": "netzbetreiber", "rang": 2, "methode": "ldjson",
     "basis_url": "https://www.o2online.de",
     "einstiege": [{"url": "https://www.o2online.de/handys"}]},
]}

# (device_id, speicher, anbieter, tarif_id, tarif, gb, rate)
_BUENDEL = [
    # iPhone 17 Pro, Band klein: VIER Anbieter - das wird der Startzustand.
    ("apple-iphone-17-pro", 256, "o2", "o2:klein", "O2 Mobile Klein", 10, 18.0),
    ("apple-iphone-17-pro", 256, "congstar", "cs:klein", "Allnet Flat XS", 15, 22.0),
    ("apple-iphone-17-pro", 256, "Vodafone", "vf:klein", "Vodafone Mobil XS", 18, 26.0),
    ("apple-iphone-17-pro", 256, "1&1", "11:klein", "All-Net-Flat S", 8, 15.0),
    # iPhone 17 Pro, Band mittel: nur congstar - Telekom fehlt hier ganz
    # (hat KARTE in keinem Band -> "gar kein Bündel").
    ("apple-iphone-17-pro", 256, "congstar", "cs:mittel", "Allnet Flat S", 50, 20.0),
    # Galaxy S26, Band klein: nur 1&1.
    ("samsung-galaxy-s26", 256, "1&1", "11:klein", "All-Net-Flat S", 10, 15.0),
    # Galaxy S26, Band gross: Telekom - der Lueckenfall "kein Bündel in
    # diesem Band, aber klein 1&1" fuer das iPhone. (Telekom-Karte hier,
    # damit Telekom nicht "gar kein Bündel" fuer die S26 ist.)
    ("samsung-galaxy-s26", 256, "Telekom", "tk:klein", "MagentaMobil S", 10, 19.0),
]

# (buendel-index aus _BUENDEL, farb-suffix, tag, geräterate) - die Historie.
# o2 traegt an 2026-09-13 ZWEI Saetze (Farben) - das guenstigste gewinnt.
# Seit A1 rechnet die Zeitreihe jeden Punkt mit der HEUTIGEN Formel aus den
# Rohfeldern der Zeile neu; die Fixture schreibt deshalb JEDE Zeile mit
# ihrer eigenen Rate, und `gesamt` entsteht aus derselben Formel wie die
# Aufbereitung sie rechnet (1 EUR Zuzahlung + 24x20 EUR Tarif + 24x Rate).
# Wuerden alle Zeilen dieselbe Rate tragen, kollabierte jede Serie auf
# EINEN Betrag und Minimum, Front und Delta praegten nichts mehr.
_HISTORIE = [
    (0, "", "2026-09-12", 18.0),
    (0, "", "2026-09-13", 17.0),
    (0, "-blau", "2026-09-13", 19.0),   # zweite Farbe: verworfen (937,00)
    (0, "", "2026-09-14", 18.0),
    (1, "", "2026-09-12", 22.0),
    # congstar fehlt am 13. UND 14. nicht - aber der 13. fehlt: Luecke.
    (1, "", "2026-09-14", 22.0),
    (1, "", "2026-09-15", 22.0),
    (2, "", "2026-09-12", 26.0),
    (2, "", "2026-09-13", 25.5),
    (2, "", "2026-09-14", 25.75),
    # 1&1: nur EIN Messtag - ein Punkt, keine Linie.
    (3, "", "2026-09-12", 15.0),
    (4, "", "2026-09-12", 20.0),
    (4, "", "2026-09-13", 19.5),
    (5, "", "2026-09-12", 15.0),
]


def _sku(device_id, speicher):
    return f"{device_id}-{speicher}gb-schwarz"


def _baue(tmp_path: pathlib.Path):
    root = tmp_path / "zeitreihe"
    (root / "config").mkdir(parents=True)
    for name, daten in (("geraete_katalog.yaml", _KATALOG),
                        ("farben.yaml", _FARBEN),
                        ("geraete_quellen.yaml", _QUELLEN)):
        (root / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
    state = root / "data" / "state"
    state.mkdir(parents=True)

    def _listung(anbieter, device_id, speicher, preis):
        return {"id": f"{anbieter.lower()}--{_sku(device_id, speicher)}",
                "sku_id": _sku(device_id, speicher), "device_id": device_id,
                "anbieter": anbieter, "anbieter_typ": "netzbetreiber",
                "netz": anbieter, "speicher_gb": speicher,
                "farbe_roh": "Schwarz", "farbe_normalisiert": "schwarz",
                "zustand": "neu", "first_seen": "2026-09-01",
                "last_verified": HEUTE, "status": "aktiv", "missed_checks": 0,
                "preis_ohne_vertrag": preis, "erstpreis": preis,
                "erstpreis_art": "ohne_vertrag", "erstpreis_am": "2026-09-01",
                "quelle_url": f"https://example.de/{anbieter.lower()}/{device_id}",
                "abgerufen_am": HEUTE, "verfuegbarkeit": "lieferbar",
                "confidence": "hoch", "einstiege": ["https://example.de/l"]}

    (state / "geraete_db.json").write_text(json.dumps({
        "updated": HEUTE,
        "anbieter": {"Vodafone": {"laeufe": 4, "funde_gesamt": 1},
                     "o2": {"laeufe": 4, "funde_gesamt": 2}},
        "listungen": [_listung("Vodafone", "apple-iphone-17-pro", 256, 1199.90),
                      _listung("o2", "apple-iphone-17-pro", 256, 1099.00),
                      _listung("1&1", "samsung-galaxy-s26", 256, 1049.00),
                      _listung("Telekom", "samsung-galaxy-s26", 256, 1079.00),
                      _listung("o2", "google-pixel-11", 128, 799.00)]}),
        encoding="utf-8")
    (state / "geraete_preise.jsonl").write_text("", encoding="utf-8")

    buendel = []
    for i, (device_id, speicher, anbieter, tarif_id, tarif, gb, rate) \
            in enumerate(_BUENDEL):
        buendel.append({
            "id": f"buendel--{anbieter.lower()}--{_sku(device_id, speicher)}"
                  f"--{tarif_id}",
            "sku_id": _sku(device_id, speicher), "anbieter": anbieter,
            "tarif_name": tarif, "tarif_id": tarif_id,
            "tarif_id_guete": "hoch", "tarif_monatlich": 20.0,
            "geraet_zuzahlung": 1.0, "geraet_monatsrate": rate,
            "laufzeit_monate": 24, "anschlusspreis": 0.0,
            "zustand": "neu", "rabatte": [],
            "quelle_url": f"https://example.de/{anbieter.lower()}/{device_id}",
            "abgerufen_am": HEUTE, "first_seen": HEUTE,
            "last_verified": HEUTE})
    (state / "geraete_tco.json").write_text(json.dumps(
        {"updated": HEUTE, "buendel": buendel, "sim_only": []}),
        encoding="utf-8")

    zeilen = []
    for idx, suffix, tag, rate in _HISTORIE:
        b = buendel[idx]
        farbe = "schwarz" + suffix
        zeilen.append({"id": b["id"] + suffix, "datum": tag,
                       "tarif_id": b["tarif_id"],
                       "tarif_id_guete": "hoch", "tarif_monatlich": 20.0,
                       "geraet_zuzahlung": 1.0, "geraet_monatsrate": rate,
                       "laufzeit_monate": 24, "anschlusspreis": 0.0,
                       "quelle_url": b["quelle_url"], "abgerufen_am": tag,
                       "zustand": "neu",
                       "gesamt": round(1.0 + 24 * 20.0 + 24 * rate, 2),
                       "sku_id": b["sku_id"].replace("schwarz", farbe)})
    (state / "geraete_tco_historie.jsonl").write_text(
        "\n".join(json.dumps(z) for z in zeilen) + "\n", encoding="utf-8")

    tarife = []
    for device_id, speicher, anbieter, tarif_id, tarif, gb, rate in _BUENDEL:
        tarife.append({
            "anbieter": anbieter, "name": tarif, "tarif_id": tarif_id,
            "art": "mobilfunk", "grundgebuehr": 20.0,
            "laufzeit_monate": 24, "datenvolumen_gb": gb,
            "preisphasen": [{"von_monat": 1, "bis_monat": None,
                             "betrag": 20.0}],
            "dokument_url": f"https://example.de/pib/{tarif_id}",
            "abgerufen_am": HEUTE, "confidence": {}, "fundstellen": {}})
    (state / "tarife.jsonl").write_text(
        "\n".join(json.dumps(t) for t in tarife) + "\n", encoding="utf-8")
    return root, state


@pytest.fixture(scope="module")
def ansicht(tmp_path_factory):
    root, state = _baue(tmp_path_factory.mktemp("zr"))
    g = geraete_view.aufbereiten(state, lade_quellen(root), lade_katalog(root),
                                 heute=HEUTE)
    return geraete_zeitreihe.aufbereiten(state, g["tco"])


@pytest.fixture(scope="module")
def ansicht_state(tmp_path_factory):
    """Aufbereitung UND state-Pfad in EINEM Rendern - fuer Wahrheitstests,
    die gegen die rohen JSONL-Dateien gegenrechnen (P1/F3)."""
    root, state = _baue(tmp_path_factory.mktemp("zrstate"))
    g = geraete_view.aufbereiten(state, lade_quellen(root), lade_katalog(root),
                                 heute=HEUTE)
    return geraete_zeitreihe.aufbereiten(state, g["tco"]), state


def _paar(ansicht, modell_band):
    modell, band = modell_band
    for p in ansicht["paare"]:
        if p["modell"] == modell and p["band"] == band:
            return p
    return None


# --------------------------------------------------------------------------
# Der Startzustand - aus den Daten, nicht hardcodiert
# --------------------------------------------------------------------------

def test_der_startzustand_hat_die_meisten_anbieter_dann_punkte(ansicht):
    # iPhone 17 Pro x klein: 4 Anbieter, 9 Punkte - gegenueber S26 x klein
    # (1 Anbieter) und apple x mittel (1 Anbieter). Die alte Vorgabe aus
    # `geraete_tco_karten` (die meisten Bündel-Anbieter) trifft hier
    # dasselbe Geraet, aber die RECHNUNG ist eine andere: sie zaehlt
    # Historie-Anbieter und -Punkte.
    assert ansicht["start"] == {"modell": "apple-iphone-17-pro-256",
                                "band": "klein"}


def test_der_startzustand_ist_deterministisch(tmp_path):
    # Gleiche Ausbeute, zwei Kandidaten: der aufsteigende Schluessel bricht
    # den Gleichstand - kein Wuerfeln je Rendern.
    root, state = _baue(tmp_path)
    g = geraete_view.aufbereiten(state, lade_quellen(root),
                                 lade_katalog(root), heute=HEUTE)
    a = geraete_zeitreihe.aufbereiten(state, g["tco"])
    b = geraete_zeitreihe.aufbereiten(state, g["tco"])
    assert a["start"] == b["start"]


def test_der_startblock_ist_das_startpaar(ansicht):
    assert ansicht["start_block"]["modell"] == ansicht["start"]["modell"]
    assert ansicht["start_block"]["band"] == ansicht["start"]["band"]


# --------------------------------------------------------------------------
# Die Serien - guenstigstes Buendel je Tag, nichts interpoliert
# --------------------------------------------------------------------------

def test_zwei_buendel_desselben_tages_zaehlen_das_minimum(ansicht):
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "klein"))
    svg = paar["svg_breit"]
    suppe = __import__("bs4").BeautifulSoup(svg, "html.parser")
    # o2 am 13.9. in ZWEI Farbsaetzen: 17 EUR Rate (889,00 EUR) und 19 EUR
    # (937,00 EUR) - das guenstigste gewinnt. Der 13.9.-Punkt sitzt damit
    # WEITER UNTEN im Bild als der vom 12.9. (18 EUR = 913,00 EUR), hat
    # also die GROESSERE Y-Koordinate; haette der 937,00-er Satz gewonnen,
    # laege er darueber. Der verworfene Betrag steht nie als Label, der
    # des LETZTEN Punkts (913,00 am 14.9.) steht als Label.
    werte = {t.get_text(strip=True)
             for t in suppe.select("text.gr-zr-wert")}
    assert "913 €" in werte
    assert "937 €" not in werte
    o2 = sorted((float(c["cx"]), float(c["cy"]))
                for c in suppe.select("circle.gr-zr-punkt")
                if c.get("fill") == "#0019a5")
    assert len(o2) == 3, "o2 traegt drei Messtage - sonst prueft der Test nichts"
    assert o2[1][1] > o2[0][1], o2


def test_unter_zwei_punkten_gibt_es_keinen_linienzug(ansicht):
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "klein"))
    suppe = __import__("bs4").BeautifulSoup(paar["svg_breit"], "html.parser")
    # 1&1 hat genau einen Messtag (12.9.): ein Kreis, kein Pfad - Luecken
    # sind Informationen, nichts wird interpoliert.
    punkte_1u1 = [c for c in suppe.select("circle.gr-zr-punkt")
                  if c.get("fill") == "#00589e"]
    pfade = suppe.select("path.gr-zr-linie")
    assert len(punkte_1u1) == 1
    # 4 Anbieter, aber nur 3 mit >= 2 Punkten -> hoechstens 3 Linien.
    assert len(pfade) == 3


def test_der_fehlende_messtag_bleibt_punktlos(ansicht):
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "klein"))
    suppe = __import__("bs4").BeautifulSoup(paar["svg_breit"], "html.parser")
    # congstar fehlt am 13.9. - an der X-Position des 13.9. steht kein
    # congstar-Punkt (gelb #f5a800).
    xticks = {t.get_text(strip=True): float(t["x"])
              for t in suppe.select("text.gr-zr-xtick")}
    x13 = xticks["13.9."]
    congstar = [c for c in suppe.select("circle.gr-zr-punkt")
                if c.get("fill") == "#f5a800"]
    assert all(abs(float(c["cx"]) - x13) > 0.5 for c in congstar)


# --------------------------------------------------------------------------
# Die Achsen - echte Messtage, echte Datumsabstaende
# --------------------------------------------------------------------------

def test_die_x_achse_traegt_die_echten_messtage_als_ticks(ansicht):
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "klein"))
    suppe = __import__("bs4").BeautifulSoup(paar["svg_breit"], "html.parser")
    texte = [t.get_text(strip=True)
             for t in suppe.select("text.gr-zr-xtick")]
    # Union der Messtage DIESER Serien: 12., 13., 14., 15.9.
    assert texte == ["12.9.", "13.9.", "14.9.", "15.9."]


def test_die_x_abstaende_sind_datumsabstaende_keine_ordinalachse(ansicht):
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "klein"))
    suppe = __import__("bs4").BeautifulSoup(paar["svg_breit"], "html.parser")
    xticks = {t.get_text(strip=True): float(t["x"])
              for t in suppe.select("text.gr-zr-xtick")}
    eins = xticks["13.9."] - xticks["12.9."]
    zwei = xticks["15.9."] - xticks["13.9."]
    # Ein Tag Abstand gegen zwei Tage Abstand: der doppelte Weg.
    assert zwei == pytest.approx(2 * eins, abs=1.0)


def test_die_y_achse_traegt_betraege_als_ticks(ansicht):
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "klein"))
    suppe = __import__("bs4").BeautifulSoup(paar["svg_breit"], "html.parser")
    texte = [t.get_text(strip=True) for t in suppe.select("text.gr-zr-achse")]
    assert texte and all(t.endswith("€") for t in texte)


# --------------------------------------------------------------------------
# Antwort-Satz, Messtag-Zeile, Lueckensatz
# --------------------------------------------------------------------------

def test_der_antwort_satz_nennt_die_leitzahl_beim_namen(ansicht):
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "klein"))
    text = __import__("re").sub(r"<[^>]+>", "", paar["antwort_html"])
    # Seit A1 ist der Name der Leitzahl seine eigene Aufloesung: „Kosten
    # über 24 Monate" steht im Satz, das Kuerzel TCO-24 taucht nirgends
    # mehr auf der Seite auf.
    assert "Kosten über 24 Monate" in text, text
    assert "TCO-24" not in text, text


def test_der_antwort_satz_nennt_geraet_band_anbieter_zahl_und_schnitt(
        ansicht):
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "klein"))
    text = __import__("re").sub(r"<[^>]+>", "", paar["antwort_html"])
    text = text.replace("&amp;", "&").replace("&nbsp;", " ")
    assert "iPhone 17 Pro" in text and "Klein" in text
    assert "1&1" in text and "841,00 €" in text
    assert "€/Monat" in text


def test_der_antwort_satz_nennt_die_vodafone_referenz(ansicht):
    """P4/D4 (18.09.2026): das Delta zur Vodafone-Referenz steht nicht
    mehr IM Satz, sondern als EIGENE Leitzahl ueber ihm (DIE ANTWORT IST
    DIE GROESSTE ZAHL) - der Satz nennt Anbieter und TCO-24, die Leitzahl
    den Abstand samt Referenzbetrag. Beides zusammen ist die Antwort."""
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "klein"))
    text = __import__("re").sub(r"<[^>]+>", "", paar["antwort_html"])
    leit = __import__("re").sub(r"<[^>]+>", "", paar["leitzahl_html"] or "")
    assert "Vodafone" in leit and "1.105,00 €" in leit, (text, leit)


def test_der_antwort_satz_polt_den_abstand_zur_referenz_richtig(ansicht):
    """E3-Fix (QA 17.09.2026, B1): Der Anhang nannte den Abstand des
    GÜNSTIGSTEN Angebots immer 'über der Vodafone-Referenz' - die Zeilen
    stehen aufsteigend, die Differenz eigen − beste ist also IMMER positiv,
    und der Beste liegt UNTER der Referenz, sobald ein Wettbewerber führt.
    Dasselbe Δ-Vorzeichen wie die Bündel-Karte desselben Angebots (S4):
    unter heißt günstiger. 1&1 (841,00 €) liegt 264,00 € UNTER der
    Vodafone-Referenz (1.105,00 €) - die Karte darunter sagt genau das.
    P4/D4: der Abstand steht jetzt in der LEITZAHL ueber dem Satz -
    Polarität und Wortlaut unveraendert, nur der Ort ist neu."""
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "klein"))
    text = __import__("re").sub(r"<[^>]+>", "", paar["antwort_html"])
    leit = __import__("re").sub(r"<[^>]+>", "", paar["leitzahl_html"] or "")
    # Zahl und Richtung getrennt geprueft: Der Tag-Strip klebt das Ende
    # der <b>-Zahl an den Anfang des Labels ("€unter") - ein schwacher
    # Parser darf die Aussage nicht zerlegen (Lehre B6, 30.08.2026).
    assert "264,00 €" in leit, (text, leit)
    assert "unter der Vodafone-Referenz" in leit, (text, leit)
    assert "über der Vodafone-Referenz" not in leit, leit
    assert "über der Vodafone-Referenz" not in text, text


def test_der_antwort_satz_endet_auf_genau_einem_punkt(ansicht):
    # Der Startzustand laeuft durch den Referenz-Zweig (1&1 am
    # guenstigsten, Vodafone-Referenz als LEITZAHL ueber dem Satz) -
    # genau der Pfad, der live auf ").." endete: die Anhaengsel in
    # _antwort_html schliessen den Satz selbst, der Abschluss der
    # Funktion setzte einen ZWEITEN Punkt dahinter. Der Satzschluss-
    # punkt steht genau EINMAL, an keiner Stelle ein "..".
    saetze = {f"{p['modell']}/{p['band']}":
              __import__("re").sub(r"<[^>]+>", "", p["antwort_html"]).strip()
              for p in ansicht["paare"]}
    # Scharfheits-Beweis (P4/D4): die Fixture enthaelt wirklich einen
    # Fall mit Leitzahl (sonst pruefte der Test einen leeren Fall) - das
    # Delta ist der Pfad mit den Anhaengseln, die den ".."-Fehler trugen.
    assert any(p["leitzahl_html"] for p in ansicht["paare"]), (
        "kein Paar mit Leitzahl - die Fixture prueft den Delta-Fall nicht")
    for schluessel, text in saetze.items():
        assert text.endswith("."), schluessel
        assert not text.endswith(".."), schluessel
        assert ").." not in text, schluessel


# --- E5: der Antwort-Satz nennt den Hersteller aus dem Katalog ----------

_ZEILE = {"anbieter": "o2", "gesamt": 1000.0, "tarif": "O2 Mobile M",
          "schnitt_monat": 41.67, "band_gb_text": "30 GB"}


def _text(html):
    return __import__("re").sub(r"<[^>]+>", "", html)


def test_der_antwort_satz_nennt_den_hersteller_wenn_der_katalog_ihn_kennt():
    # Xiaomi 17: die Kachel-Logik (_kurz_name) schneidet den Hersteller ab
    # und laesst "17" - im Fliesstext liest sich "Beim 17 im Band Mittel"
    # als Zahl ohne Bezug. Der Satz praefigiert den Hersteller aus dem
    # Katalog-Eintrag des Modells.
    modell = {"id": "xiaomi-17", "titel": "Xiaomi 17",
              "hersteller": "Xiaomi", "speicher": None}
    html = geraete_zeitreihe._antwort_html(
        modell, "mittel", [dict(_ZEILE)], {"label": "Mittel"})
    assert "Beim Xiaomi 17 im Band Mittel" in _text(html), _text(html)


def test_ohne_katalog_hersteller_bleibt_der_kurzname_geraten_wird_nichts():
    # Fehlt der Hersteller im Eintrag, bleibt es beim Kurznamen - E5-Regel:
    # Quelle ist der Katalog-/Auto-Eintrag, keine Vermutung.
    modell = {"id": "17", "titel": "17", "hersteller": "", "speicher": None}
    html = geraete_zeitreihe._antwort_html(
        modell, "mittel", [dict(_ZEILE)], {"label": "Mittel"})
    assert "Beim 17 im Band Mittel" in _text(html), _text(html)
    assert "Beim  17" not in _text(html)


def test_der_antwort_satz_mit_hersteller_die_kachel_ohne(ansicht):
    # Die Trennung ist die Regel: der SATZ nennt "Apple iPhone 17 Pro",
    # die KACHEL-Vorschau bleibt kurz ("iPhone 17 Pro") - dieselbe
    # Aufbereitung, zwei Lesarten je Ort.
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "klein"))
    assert "Beim Apple iPhone 17 Pro im Band Klein" in _text(
        paar["antwort_html"]), _text(paar["antwort_html"])
    assert ansicht["daten"]["kurz"]["apple-iphone-17-pro-256"] == \
        "iPhone 17 Pro"


def test_die_messtagzeile_nennt_die_echte_spanne(ansicht):
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "klein"))
    assert paar["messtage_text"] == \
        "Messtage: 12.9. bis 15.9. (4 Messungen)"


def test_ein_lueckensatz_mit_alternativbaendern_statt_zeilen(ansicht):
    # Band MITTEL des iPhone: congstar allein; o2, 1&1 und Vodafone fehlen
    # hier, haben aber Klein-Buendel - der EINE Satz nennt sie mit Namen
    # und Alternativ-Band samt Betrag in Klammern. Telekom hat fuer das
    # iPhone gar kein Buendel (Antonio 9b.7: nichts heisst nicht einzeln).
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "mittel"))
    luecke = paar["luecke_text"]
    assert luecke
    assert "Telekom" in luecke and luecke.count("Telekom") == 1
    assert "o2 (klein 913,00 €)" in luecke
    assert "1&1 (klein 841,00 €)" in luecke
    assert "Vodafone (klein 1.105,00 €)" in luecke


def test_der_lueckensatz_nennt_nur_anbieter_ohne_zeile(ansicht):
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "klein"))
    # 1&1, congstar, Vodafone, o2 stehen als Zeile - sie stehen NICHT in
    # der Luecke.
    for name in ("1&1", "congstar"):
        assert name not in paar["luecke_text"]


# --------------------------------------------------------------------------
# Belege - echte URL je Anbieter am Linienende
# --------------------------------------------------------------------------

def test_jede_linie_endet_in_einem_beleglink_mit_datum(ansicht):
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "klein"))
    suppe = __import__("bs4").BeautifulSoup(paar["svg_breit"], "html.parser")
    links = suppe.select("a.gr-zr-link")
    assert len(links) == 4          # ein Link je Anbieter mit Serie
    for a in links:
        href = a.get("href") or ""
        assert href.startswith("https://")
        assert "↗" in a.get_text()


def test_vodafone_ist_rot_und_traegt_unser_angebot(ansicht):
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "klein"))
    suppe = __import__("bs4").BeautifulSoup(paar["svg_breit"], "html.parser")
    vf_punkte = [c for c in suppe.select("circle.gr-zr-punkt")
                 if c.get("fill") == "#e60000"]
    assert vf_punkte
    assert "unser Angebot" in paar["svg_breit"]


def test_kein_beleglink_ohne_echte_url(tmp_path):
    root, state = _baue(tmp_path)
    roh = json.loads((state / "geraete_tco.json").read_text())
    roh["buendel"][0]["quelle_url"] = None
    (state / "geraete_tco.json").write_text(json.dumps(roh), encoding="utf-8")
    g = geraete_view.aufbereiten(state, lade_quellen(root),
                                 lade_katalog(root), heute=HEUTE)
    a = geraete_zeitreihe.aufbereiten(state, g["tco"])
    paar = _paar(a, ("apple-iphone-17-pro-256", "klein"))
    suppe = __import__("bs4").BeautifulSoup(paar["svg_breit"], "html.parser")
    for a_tag in suppe.select("a.gr-zr-link"):
        assert (a_tag.get("href") or "").startswith("https://")


# --------------------------------------------------------------------------
# Suchvorschau und Kacheln - deterministisch, ohne Preise im Client
# --------------------------------------------------------------------------

def test_der_suchindex_ist_deterministisch_vorsortiert(ansicht):
    idx = ansicht["suchindex"]
    schluessel = [(-e["band_zahl"], -e["anbieter_zahl"], e["titel"])
                  for e in idx]
    assert schluessel == sorted(schluessel)
    assert len(idx) == 2               # zwei Modelle mit Karten/Zeilen


def _erweitere_um_modelle(root, n: int) -> None:
    """Haengt n zusaetzliche EIN-Band-Modelle an den Bestand (B1-Test).

    Jedes bekommt Katalogeintrag, Listung, Bündel und Tarif - es zaehlt
    damit als Modell mit erlaubtem Band und MUSS im Suchindex stehen, egal
    wie weit hinten es sortiert ist."""
    katalog = yaml.safe_load(
        (root / "config" / "geraete_katalog.yaml").read_text(encoding="utf-8"))
    db = json.loads(
        (root / "data" / "state" / "geraete_db.json").read_text(encoding="utf-8"))
    tco = json.loads(
        (root / "data" / "state" / "geraete_tco.json").read_text(encoding="utf-8"))
    tarife = [json.loads(z) for z in
              (root / "data" / "state" / "tarife.jsonl")
              .read_text(encoding="utf-8").splitlines() if z.strip()]
    for i in range(n):
        device_id = f"samsung-galaxy-x{i}"
        sku = f"{device_id}-256gb-schwarz"
        katalog["geraete"].append(
            {"hersteller": "Samsung", "modell": f"Galaxy X{i}",
             "generation": i, "marktstart": "2026-01-30", "speicher": [256],
             "segment": "budget"})
        db["listungen"].append({
            "id": f"o2--{sku}", "sku_id": sku, "device_id": device_id,
            "anbieter": "o2", "anbieter_typ": "netzbetreiber", "netz": "o2",
            "speicher_gb": 256, "farbe_roh": "Schwarz",
            "farbe_normalisiert": "schwarz", "zustand": "neu",
            "first_seen": "2026-09-01", "last_verified": HEUTE,
            "status": "aktiv", "missed_checks": 0, "preis_ohne_vertrag": 299.0,
            "erstpreis": 299.0, "erstpreis_art": "ohne_vertrag",
            "erstpreis_am": "2026-09-01",
            "quelle_url": f"https://example.de/o2/{device_id}",
            "abgerufen_am": HEUTE, "verfuegbarkeit": "lieferbar",
            "confidence": "hoch", "einstiege": ["https://example.de/l"]})
        tco["buendel"].append({
            "id": f"buendel--o2--{sku}--x{i}:klein", "sku_id": sku,
            "anbieter": "o2", "tarif_name": f"X{i} Klein",
            "tarif_id": f"x{i}:klein", "tarif_id_guete": "hoch",
            "tarif_monatlich": 20.0, "geraet_zuzahlung": 1.0,
            "geraet_monatsrate": 15.0, "laufzeit_monate": 24,
            "anschlusspreis": 0.0, "zustand": "neu", "rabatte": [],
            "quelle_url": f"https://example.de/o2/{device_id}",
            "abgerufen_am": HEUTE, "first_seen": HEUTE,
            "last_verified": HEUTE})
        tarife.append({
            "anbieter": "o2", "name": f"X{i} Klein", "tarif_id": f"x{i}:klein",
            "art": "mobilfunk", "grundgebuehr": 20.0, "laufzeit_monate": 24,
            "datenvolumen_gb": 10,
            "preisphasen": [{"von_monat": 1, "bis_monat": None,
                             "betrag": 20.0}],
            "dokument_url": f"https://example.de/pib/x{i}",
            "abgerufen_am": HEUTE, "confidence": {}, "fundstellen": {}})
    (root / "config" / "geraete_katalog.yaml").write_text(
        yaml.safe_dump(katalog, allow_unicode=True, sort_keys=False),
        encoding="utf-8")
    (root / "data" / "state" / "geraete_db.json").write_text(
        json.dumps(db), encoding="utf-8")
    (root / "data" / "state" / "geraete_tco.json").write_text(
        json.dumps(tco), encoding="utf-8")
    (root / "data" / "state" / "tarife.jsonl").write_text(
        "\n".join(json.dumps(t) for t in tarife) + "\n", encoding="utf-8")


def test_der_suchindex_traegt_jedes_modell_mit_band(tmp_path):
    """B1 (QA 17.09.2026): der Suchindex ist der VORRAT, nicht die Vorschau.

    Bis zum Fix kappte ihn `VORSCHAU_MAX * 4 = 32` Eintraege nach Band- und
    Anbieterzahl - am echten Bestand fehlten 56 von 88 Modellen hinter dem
    genehmigten Suchfeld (ganze Marken, die Galaxy-A-Reihe; 'motorola' ->
    'kein Treffer'). Die 8er-Kappung gilt der ANZEIGE (app.js), nie dem
    Vorrat - derselbe Fehler wie der Scan-Deckel der Uebersetzung (§6).
    2 Bestandsmodelle + 40 gestellte: alle 42 muessen im Knoten stehen,
    auch das alphabetisch letzte."""
    root, state = _baue(tmp_path)
    _erweitere_um_modelle(root, 40)
    g = geraete_view.aufbereiten(state, lade_quellen(root), lade_katalog(root),
                                 heute=HEUTE)
    a = geraete_zeitreihe.aufbereiten(state, g["tco"])
    idx = a["daten"]["suchindex"]
    ids = {e["id"] for e in idx}
    assert len(idx) == 42, \
        f"Suchindex haelt {len(idx)} von 42 Modellen mit Band bereit"
    assert "samsung-galaxy-x39-256" in ids, \
        "das hinterste Modell fehlt - ein Vorratsdeckel waehlt nach Listenposition"


def test_der_client_knoten_traegt_keine_preise(ansicht):
    daten = json.dumps(ansicht["daten"], ensure_ascii=False)
    assert "€" not in daten, "keine Beträge im Client-Knoten"
    assert '"gesamt"' not in daten and '"tco"' not in daten, \
        "keine Preisfelder im Client-Knoten"
    # Die Vorschau-Angaben je Modell: Titel + Zaehlungen, kein Betrag.
    for eintrag in ansicht["daten"]["suchindex"]:
        assert set(eintrag) <= {"id", "titel", "hersteller", "speicher",
                                "anbieter_zahl", "band_zahl"}


def test_die_kacheln_sind_die_haeufigsten_geraete_mit_kurznamen(ansicht):
    kacheln = ansicht["kacheln"]
    assert 1 <= len(kacheln) <= 6
    assert kacheln[0]["id"] == ansicht["start"]["modell"]
    assert kacheln[0]["kurz"] == "iPhone 17 Pro"


def test_die_karte_traegt_preis_und_anbieter_punkte(ansicht):
    """P1/F3 (A3) + P1-Fix (Sicht-B2/S3-4): aus dem Chip ist eine KARTE
    geworden, und ihre Werte stehen JE BAND - nicht mehr der ab-Preis über
    alle Bänder neben Bewegung und Punkten des Leit-Paares (zwei
    Maßstäbe). Der Band-Eintrag traegt den ab-Preis des besten ECHTEN
    Angebots DIESES Bandes (mit Ø/Monat und Anbieter) und die Anbieter
    der Zeitreihe DES BANDES als Punkte in ihren HAUSFARBEN."""
    k = ansicht["kacheln"][0]
    assert k["id"] == "apple-iphone-17-pro-256"
    assert set(k["baender"]) == {"klein", "mittel"}
    klein = k["baender"]["klein"]
    # 1&1-Buendel Band klein: 1 € Zuzahlung + 24×20 € Tarif + 24×15 € Rate
    assert klein["ab"] == "841,00 €"
    assert klein["ab_monat"] == "35,04 €/Monat"
    assert klein["anb"] == "1&1"
    assert klein["punkte_html"].count("<i") == 4
    assert "#e60000" in klein["punkte_html"], "Vodafone-Punkt in Hausfarbe"
    assert "#0019a5" in klein["punkte_html"], "o2-Punkt in Hausfarbe"
    # Reihenfolge der Punkte = ANBIETER_FOLGE (Netzbetreiber zuerst)
    assert klein["anbieter_text"] == "Vodafone, o2, 1&1, congstar"
    # Dasselbe Mass im ANDEREN Band: congstar ist dort der einzige echte
    # Anbieter - Kartenpreis und Punkte folgen dem Band, nicht dem Leit-Paar
    mittel = k["baender"]["mittel"]
    assert mittel["anb"] == "congstar"
    assert mittel["ab"] == "961,00 €"
    assert mittel["punkte_html"].count("<i") == 1
    assert mittel["anbieter_text"] == "congstar"
    assert mittel["delta_text"] == "↓ −12 € in 1 Tag"


def test_das_karten_delta_ist_die_bewegung_des_fuehrenden_anbieters(ansicht_state):
    """Gegenrechnung aus der ROHEN Historie (nicht aus der Aufbereitung),
    JE ANBIETER (A2, 20.09.2026): fuehrend am letzten Messtag des Bandes
    klein ist congstar - die EINZIGE Messung am 15.9. (1.009 EUR) -, und
    congstar stand auch am ersten Messtag (12.9.) bei 1.009 EUR. Die
    Bewegung der Karte ist congstars EIGENE (±0 in 3 Tagen). Die bis A2
    gerechnete Front haette 1&1s 841 EUR (12.9.) gegen congstars 1.009 EUR
    (15.9.) gestellt und "+168 in 3 Tagen" gemeldet - zwei VERSCHIEDENE
    Angebote gegeneinander, ohne dass ein Anbieter seinen Preis geaendert
    hat."""
    ansicht, state = ansicht_state
    k = ansicht["kacheln"][0]
    assert k["id"] == "apple-iphone-17-pro-256"
    tco = json.loads((pathlib.Path(state) / "geraete_tco.json")
                     .read_text(encoding="utf-8"))
    anbieter_je_id = {b["id"]: b["anbieter"] for b in tco["buendel"]}
    je_anbieter: dict[str, dict[str, float]] = {}
    pfad = pathlib.Path(state) / "geraete_tco_historie.jsonl"
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        satz = json.loads(zeile)
        if not satz["tarif_id"].endswith(":klein"):
            continue                       # die Karte zeigt Band klein
        if satz["id"] not in anbieter_je_id:
            continue                       # Farbdublette ohne Store-Satz
        je = je_anbieter.setdefault(anbieter_je_id[satz["id"]], {})
        if satz["datum"] not in je or satz["gesamt"] < je[satz["datum"]]:
            je[satz["datum"]] = satz["gesamt"]
    tage = sorted({d for je in je_anbieter.values() for d in je})
    assert (tage[0], tage[-1]) == ("2026-09-12", "2026-09-15")
    fuehrend = min((a for a in je_anbieter if tage[-1] in je_anbieter[a]),
                   key=lambda a: (je_anbieter[a][tage[-1]], a))
    assert fuehrend == "congstar"
    assert tage[0] in je_anbieter[fuehrend], \
        "ohne Messung am ersten Tag gaebe es keine Bewegung (A2)"
    delta = round(je_anbieter[fuehrend][tage[-1]]
                  - je_anbieter[fuehrend][tage[0]], 2)
    assert delta == 0.0
    assert k["baender"]["klein"]["delta_text"] == "±0 € in 3 Tagen"
    assert k["baender"]["klein"]["delta_richtung"] == "gleich"


def test_ohne_zwei_messtage_gibt_es_kein_delta(ansicht):
    """Galaxy S26 hat EINEN Messtag (12.9.) - eine Bewegung daraus waere
    geraten. Die Karte zeigt keins (Feld None, kein Pfeil)."""
    k = ansicht["kacheln"][1]
    assert k["id"] == "samsung-galaxy-s26-256"
    for band in k["baender"].values():
        assert band["delta_text"] is None
        assert band["delta_richtung"] is None


def test_bewegung_traegt_alle_richtungen():
    """Die Richtungs-Sprache der Karte: steigen rot, sinken gruen,
    unverändert grau - und gemessen wird die Reihe DES ANBIETERS, der am
    letzten Messtag fuehrt, nie der Wert des ersten Anbieters der
    Schleife."""
    steigt = geraete_zeitreihe._bewegung(
        {"a": [["2026-09-12", 100.0], ["2026-09-14", 120.0]]})
    assert steigt == {"text": "↑ +20 € in 2 Tagen", "richtung": "steigt"}
    sinkt = geraete_zeitreihe._bewegung(
        {"a": [["2026-09-12", 100.0], ["2026-09-13", 90.0]]})
    assert sinkt == {"text": "↓ −10 € in 1 Tag", "richtung": "sinkt"}
    gleich = geraete_zeitreihe._bewegung(
        {"a": [["2026-09-12", 100.0], ["2026-09-13", 100.0]]})
    assert gleich == {"text": "±0 € in 1 Tag", "richtung": "gleich"}
    # A2: fuehrt am letzten Tag ein Anbieter, der am ersten FEHLT (b: 90),
    # gibt es KEINE Bewegung. Die Front haette b (90) gegen a (100)
    # gestellt - zwei Angebote gegeneinander, keine Preisaenderung.
    front = geraete_zeitreihe._bewegung(
        {"a": [["2026-09-12", 100.0], ["2026-09-13", 110.0]],
         "b": [["2026-09-13", 90.0]]})
    assert front is None
    assert geraete_zeitreihe._bewegung(
        {"a": [["2026-09-12", 100.0]]}) is None


def test_wechselt_der_guenstigste_anbieter_ohne_preisaenderung_gibt_es_keine_bewegung():
    """A2 (20.09.2026), der Befund am iPhone 17 Pro, Band klein: congstar
    am 12.9., 1&1 am 18.9. - KEIN Anbieter hat seinen Preis geaendert, und
    die Karte meldete "+387 EUR in 6 Tagen". Bewegung ist anzeigepflichtig
    nur je ANBIETER: der Fuehrende am letzten Messtag (1&1) fehlt am
    ersten, also gibt es fuer ihn keine Bewegung - keinesfalls die
    Differenz der zwei Angebote."""
    # Der Produktionsfall in Zahlen: congstar 1.009 EUR (12.9.),
    # 1&1 1.396 EUR (18.9.) - 387 EUR Front-Differenz, null Preisaenderung.
    assert geraete_zeitreihe._bewegung(
        {"congstar": [["2026-09-12", 1009.0]],
         "1&1": [["2026-09-18", 1396.0]]}) is None
    # Dieselbe Fehlerklasse, andersherum: der bisher Fuehrende bleibt
    # weiter gemessen und unveraendert, ein NOCH guenstigerer Anbieter
    # kommt hinzu - die Front faellt, kein Preis hat sich bewegt.
    assert geraete_zeitreihe._bewegung(
        {"congstar": [["2026-09-12", 1009.0], ["2026-09-18", 1009.0]],
         "1&1": [["2026-09-18", 900.0]]}) is None


def test_die_bewegung_misst_den_fuehrenden_anbieter_an_beiden_endtagen():
    """Wer am letzten Messtag fuehrt, dessen EIGENE Reihe zwischen erstem
    und letztem Messtag ist die Bewegung - inklusive Gleichstand und
    Gleichstands-Tie-break ueber die Anbieterfolge (deterministisch, kein
    Wuerfeln je Rendern)."""
    # b fuehrt am letzten Tag (94 < 95) und stand am ersten bei 90: +4.
    steigt = geraete_zeitreihe._bewegung(
        {"a": [["2026-09-12", 100.0], ["2026-09-13", 95.0]],
         "b": [["2026-09-12", 90.0], ["2026-09-13", 94.0]]})
    assert steigt == {"text": "↑ +4 € in 1 Tag", "richtung": "steigt"}
    # o2 ist am letzten Tag die einzige (und damit fuehrende) Messung;
    # 1&1 war am ersten guenstiger, fehlt aber am letzten - o2s eigene
    # Reihe ist unveraendert: ±0, nicht 1&1s niedrigerer alter Preis.
    gleich = geraete_zeitreihe._bewegung(
        {"o2": [["2026-09-12", 100.0], ["2026-09-13", 100.0]],
         "1&1": [["2026-09-12", 80.0]]})
    assert gleich == {"text": "±0 € in 1 Tag", "richtung": "gleich"}
    # Gleichstand am letzten Tag (beide 100): die ANBIETER_FOLGE bricht
    # den Tie - o2 (Position 3) vor 1&1 (Position 4). Die Bewegung ist
    # o2s eigene (120 -> 100), nicht 1&1s (80 -> 100).
    tie = geraete_zeitreihe._bewegung(
        {"1&1": [["2026-09-12", 80.0], ["2026-09-13", 100.0]],
         "o2": [["2026-09-12", 120.0], ["2026-09-13", 100.0]]})
    assert tie == {"text": "↓ −20 € in 1 Tag", "richtung": "sinkt"}


def test_ohne_historie_gibt_es_den_ehrlichen_leersatz(tmp_path):
    root, state = _baue(tmp_path)
    (state / "geraete_tco_historie.jsonl").write_text("", encoding="utf-8")
    g = geraete_view.aufbereiten(state, lade_quellen(root),
                                 lade_katalog(root), heute=HEUTE)
    a = geraete_zeitreihe.aufbereiten(state, g["tco"])
    assert a["hat_daten"] is False
    paar = _paar(a, ("apple-iphone-17-pro-256", "klein"))
    assert paar["svg_breit"] == ""
    assert "iPhone 17 Pro" in paar["leer_text"]
    assert "Klein" in paar["leer_text"]


def test_die_schmalvariante_zeigt_dieselben_werte_weniger_labels(ansicht):
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "klein"))
    breit = __import__("bs4").BeautifulSoup(paar["svg_breit"], "html.parser")
    schmal = __import__("bs4").BeautifulSoup(paar["svg_schmal"], "html.parser")
    # Punkte und X-Ticks identisch (dieselben Messungen), Erst-Werte-Labels
    # nur auf dem breiten Bild.
    assert len(schmal.select("circle.gr-zr-punkt")) == \
        len(breit.select("circle.gr-zr-punkt"))
    assert len(schmal.select("text.gr-zr-xtick")) == \
        len(breit.select("text.gr-zr-xtick"))
    assert len(schmal.select(".gr-zr-wert--erst")) == 0


# ==========================================================================
# E4-Sichtbarkeit: Auto-Eintraege in der WAHL erst ab 2 Messtagen
# (Bau 2). Der Katalog-Reiter zeigt sie ab Tag 1, die Listung existiert
# ab Tag 1 - die Zeitreihe ist eine TCO-Aussage, und ein Messtag ist noch
# keine (PM-Vorgabe E4; Bestaetigung ueber zwei Naechte, bevor ein Gerät
# die Auswahl füllt).
# ==========================================================================

_AUTO_EINTRAG = {"hersteller": "Apple", "modell": "iPhone 18 Pro",
                 "generation": 18, "speicher": [256], "auto": "2026-09-15"}


def _baue_mit_auto(tmp_path: pathlib.Path, messtage: list[str]):
    """_baue plus einem AUTO angelegten iPhone 18 Pro (State, nicht Config -
    der Produktionsweg) mit o2-Buendel im Band klein und N Messtagen."""
    root, state = _baue(tmp_path)

    (state / "geraete_katalog_auto.json").write_text(
        json.dumps({"geraete": [_AUTO_EINTRAG]}, ensure_ascii=False),
        encoding="utf-8")

    db = json.loads((state / "geraete_db.json").read_text(encoding="utf-8"))
    gid, speicher = "apple-iphone-18-pro", 256
    db["listungen"].append({
        "id": f"o2--{_sku(gid, speicher)}", "sku_id": _sku(gid, speicher),
        "device_id": gid, "anbieter": "o2", "anbieter_typ": "netzbetreiber",
        "netz": "o2", "speicher_gb": speicher, "farbe_roh": "Schwarz",
        "farbe_normalisiert": "schwarz", "zustand": "neu",
        "first_seen": "2026-09-15", "last_verified": HEUTE, "status": "aktiv",
        "missed_checks": 0, "preis_ohne_vertrag": 1199.00,
        "erstpreis": 1199.00, "erstpreis_art": "ohne_vertrag",
        "erstpreis_am": "2026-09-15",
        "quelle_url": "https://example.de/o2/iphone-18-pro",
        "abgerufen_am": HEUTE, "verfuegbarkeit": "lieferbar",
        "confidence": "hoch", "einstiege": ["https://example.de/l"]})
    (state / "geraete_db.json").write_text(json.dumps(db), encoding="utf-8")

    tco = json.loads((state / "geraete_tco.json").read_text(encoding="utf-8"))
    buendel_id = f"buendel--o2--{_sku(gid, speicher)}--o2:klein"
    tco["buendel"].append({
        "id": buendel_id, "sku_id": _sku(gid, speicher), "anbieter": "o2",
        "tarif_name": "O2 Mobile Klein", "tarif_id": "o2:klein",
        "tarif_id_guete": "hoch", "tarif_monatlich": 20.0,
        "geraet_zuzahlung": 1.0, "geraet_monatsrate": 18.0,
        "laufzeit_monate": 24, "anschlusspreis": 0.0, "zustand": "neu",
        "rabatte": [], "quelle_url": "https://example.de/o2/18pro",
        "abgerufen_am": HEUTE, "first_seen": "2026-09-15",
        "last_verified": HEUTE})
    (state / "geraete_tco.json").write_text(json.dumps(tco), encoding="utf-8")

    zeilen = (state / "geraete_tco_historie.jsonl") \
        .read_text(encoding="utf-8").splitlines()
    for tag in messtage:
        zeilen.append(json.dumps({
            "id": buendel_id, "datum": tag, "tarif_id": "o2:klein",
            "tarif_id_guete": "hoch", "tarif_monatlich": 20.0,
            "geraet_zuzahlung": 1.0, "geraet_monatsrate": 18.0,
            "laufzeit_monate": 24, "anschlusspreis": 0.0,
            "quelle_url": "https://example.de/o2/18pro", "abgerufen_am": tag,
            "zustand": "neu", "gesamt": 1600.00,
            "sku_id": _sku(gid, speicher)}))
    (state / "geraete_tco_historie.jsonl").write_text(
        "\n".join(z for z in zeilen if z) + "\n", encoding="utf-8")
    return root, state


def test_auto_modell_mit_einem_mestag_steht_nicht_in_der_wahl(tmp_path):
    root, state = _baue_mit_auto(tmp_path, ["2026-09-15"])
    g = geraete_view.aufbereiten(state, lade_quellen(root),
                                 lade_katalog(root), heute=HEUTE)
    a = geraete_zeitreihe.aufbereiten(state, g["tco"])

    ids = {m["id"] for m in a["suchindex"]}
    assert "apple-iphone-18-pro-256" not in ids
    assert all(p["modell"] != "apple-iphone-18-pro-256" for p in a["paare"])
    assert all(k["id"] != "apple-iphone-18-pro-256" for k in a["kacheln"])
    assert a["start"]["modell"] != "apple-iphone-18-pro-256"

    # Der KATALOG-Reiter zeigt ihn ab Tag 1 (Listung existiert ab Tag 1):
    # eine Quelle der Wahrheit, zwei Sichtbarkeitsregeln. Seit P3 ist der
    # Katalog eine Zeile je Modell - der Listungs-Bestand lebt im
    # Aufklapper derselben Modellzeile.
    assert any(z["modell"] == "iPhone 18 Pro" and z["listungen"] >= 1
               for z in g["katalog_modelle"])

    # Gegenprobe: ein HAND-Eintrag mit EINEM Messtag bleibt waehlbar -
    # die Regel gilt nur fuer Auto-Eintraege (Galaxy S26 hat hier genau
    # einen Messtag, 2026-09-12, und steht heute in der Wahl).
    assert "samsung-galaxy-s26-256" in ids


def test_auto_modell_mit_zwei_mestagen_steht_in_der_wahl(tmp_path):
    root, state = _baue_mit_auto(tmp_path, ["2026-09-15", "2026-09-16"])
    g = geraete_view.aufbereiten(state, lade_quellen(root),
                                 lade_katalog(root), heute=HEUTE)
    a = geraete_zeitreihe.aufbereiten(state, g["tco"])
    ids = {m["id"] for m in a["suchindex"]}
    assert "apple-iphone-18-pro-256" in ids
    assert any(p["modell"] == "apple-iphone-18-pro-256" for p in a["paare"])
