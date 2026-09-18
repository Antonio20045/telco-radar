"""P5-AUFTRAG 1 (STRATEGIE_GERAETE_V3, 18.09.2026): SICHTBARKEIT FOLGT DEN
DATEN, NICHT DEM WEG - Bündel ODER Listung genügt.

Antonios Forderung 8: „Wenn ein neues Modell rauskommt, ein neues iPhone,
muss es automatisch gecrawlt/erkannt werden, dass man das nicht manuell
programmieren muss. Ziel: dass man hier nie wieder was dran ändern muss."

Die gemessene Lücke (auto-doku.md, 17.09.): das iPhone 18 kam mit 105
Bündeln an, bevor die erste Listung stand - und der Katalog zählte nur
Listungen. Ein bündelloses Auto-Modell (Watch, Tab, AirPods) erschien
NIRGENDS: der Katalog wollte eine Listung, die Zeitreihen-Wahl zwei
Bündel-Messtage. Diese Datei nagelt die Regel an ihrem gemessenen Fall fest:

    KATALOG         ab der ERSTEN Listung (Tag 1) ODER ab dem ersten Bündel
    ZEITREIHEN-WAHL erst ab 2 Bündel-Messtagen (keine unsichtbaren
                    Wahl-Einträge, FM 6.4) - am Modell MIT Bündel heisst
                    die Lücke dort „noch keine Zeitreihe", am Modell OHNE
                    Bündel nennt die TCO-Spalte den Grund und die Lücke
                    schweigt (eine Aussage je Ort genau EINMAL).

Der Live-Fall iPhone 18 am echten Bestand steht in der Notiz
`outputs/strategie-geraete-v3-2026-09-17/p5/notiz-e1-sichtbarkeit.md`;
diese Datei ist die Fixture-Seite derselben Regel.
"""
from __future__ import annotations

import json
import pathlib

from bs4 import BeautifulSoup

from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import geraete_view, geraete_zeitreihe
from telco_radar.report.html import render_site

from test_geraete_zeitreihe_ansicht import HEUTE, _baue, _sku

# Dasselbe Auto-Eintrag-Format wie in test_geraete_zeitreihe_ansicht: State,
# nicht Config - der Produktionsweg der E4-Auto-Erkennung.
_AUTO_EINTRAG = {"hersteller": "Apple", "modell": "iPad Pro 13",
                 "generation": None, "speicher": [256], "auto": "2026-09-15"}
_GID, _SPEICHER = "apple-ipad-pro-13", 256
_MID = f"{_GID}-{_SPEICHER}"
_TARIF_ID, _TARIF = "o2:klein", "O2 Mobile Klein"


def _baue_buendel_modell(tmp_path: pathlib.Path, messtage: list[str],
                         mit_listung: bool = False):
    """Ein AUTO-Modell mit o2-Bündel im Band klein, N Bündel-Messtagen und
    (wahlweise) OHNE jede Listung - der gemessene iPhone-18-Weg vom 17.09.:
    die Bündel kamen an, die Listung stand noch nicht."""
    root, state = _baue(tmp_path)
    (state / "geraete_katalog_auto.json").write_text(
        json.dumps({"geraete": [_AUTO_EINTRAG]}, ensure_ascii=False),
        encoding="utf-8")

    if mit_listung:
        db = json.loads((state / "geraete_db.json").read_text(encoding="utf-8"))
        db["listungen"].append({
            "id": f"o2--{_sku(_GID, _SPEICHER)}",
            "sku_id": _sku(_GID, _SPEICHER), "device_id": _GID,
            "anbieter": "o2", "anbieter_typ": "netzbetreiber", "netz": "o2",
            "speicher_gb": _SPEICHER, "farbe_roh": "Silber",
            "farbe_normalisiert": "silber", "zustand": "neu",
            "first_seen": "2026-09-15", "last_verified": HEUTE,
            "status": "aktiv", "missed_checks": 0,
            "preis_ohne_vertrag": 1199.00, "erstpreis": 1199.00,
            "erstpreis_art": "ohne_vertrag", "erstpreis_am": "2026-09-15",
            "quelle_url": "https://example.de/o2/ipad-pro-13",
            "abgerufen_am": HEUTE, "verfuegbarkeit": "lieferbar",
            "confidence": "hoch", "einstiege": ["https://example.de/l"]})
        (state / "geraete_db.json").write_text(json.dumps(db),
                                               encoding="utf-8")

    tco = json.loads((state / "geraete_tco.json").read_text(encoding="utf-8"))
    buendel_id = f"buendel--o2--{_sku(_GID, _SPEICHER)}--{_TARIF_ID}"
    # Das Bündel im Store entsteht nur, wenn es Messungen gibt - die
    # bündellose Lage (Watches/Tabs/AirPods) hat KEIN Bündel, nur die
    # Listung. (Ein Bündel OHNE Messtag wäre eine dritte, eigene Lage -
    # nach der Heimregel "Tag 1 ist gespeichert" kommt sie im Bestand
    # nicht vor.)
    if messtage:
        tco["buendel"].append({
            "id": buendel_id, "sku_id": _sku(_GID, _SPEICHER),
            "anbieter": "o2", "tarif_name": _TARIF, "tarif_id": _TARIF_ID,
            "tarif_id_guete": "hoch", "tarif_monatlich": 20.0,
            "geraet_zuzahlung": 1.0, "geraet_monatsrate": 25.0,
            "laufzeit_monate": 24, "anschlusspreis": 0.0, "zustand": "neu",
            "rabatte": [], "quelle_url": "https://example.de/o2/ipad",
            "abgerufen_am": HEUTE, "first_seen": "2026-09-15",
            "last_verified": HEUTE})
        (state / "geraete_tco.json").write_text(json.dumps(tco),
                                                encoding="utf-8")

    zeilen = (state / "geraete_tco_historie.jsonl") \
        .read_text(encoding="utf-8").splitlines()
    for tag in messtage:
        zeilen.append(json.dumps({
            "id": buendel_id, "datum": tag, "tarif_id": _TARIF_ID,
            "tarif_id_guete": "hoch", "tarif_monatlich": 20.0,
            "geraet_zuzahlung": 1.0, "geraet_monatsrate": 25.0,
            "laufzeit_monate": 24, "anschlusspreis": 0.0,
            "quelle_url": "https://example.de/o2/ipad", "abgerufen_am": tag,
            "zustand": "neu", "gesamt": 1400.00,
            "sku_id": _sku(_GID, _SPEICHER)}))
    (state / "geraete_tco_historie.jsonl").write_text(
        "\n".join(z for z in zeilen if z) + "\n", encoding="utf-8")

    tarife = (state / "tarife.jsonl").read_text(encoding="utf-8").splitlines()
    tarife.append(json.dumps({
        "anbieter": "o2", "name": _TARIF, "tarif_id": _TARIF_ID,
        "art": "mobilfunk", "grundgebuehr": 20.0, "laufzeit_monate": 24,
        "datenvolumen_gb": 10,
        "preisphasen": [{"von_monat": 1, "bis_monat": None, "betrag": 20.0}],
        "dokument_url": "https://example.de/pib/klein",
        "abgerufen_am": HEUTE, "confidence": {}, "fundstellen": {}}))
    (state / "tarife.jsonl").write_text(
        "\n".join(z for z in tarife if z) + "\n", encoding="utf-8")
    return root, state


def _rendern(root: pathlib.Path) -> tuple[BeautifulSoup, dict]:
    """Site rendern und (geraete.html als Suppe, Zeitreihen-Wahl-Knoten)."""
    reports = root / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"{HEUTE}.json").write_text(json.dumps({
        "date": HEUTE, "language": "de",
        "briefing_md": "## Auf einen Blick\n\n- Nichts.\n",
        "stats": {}, "regions": []}), encoding="utf-8")
    (reports / f"{HEUTE}.md").write_text("# B\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    suppe = BeautifulSoup((site / "geraete.html").read_text(encoding="utf-8"),
                          "html.parser")
    knoten = suppe.select_one("#gr-zeitreihe-daten")
    assert knoten is not None, "Zeitreihen-Knoten fehlt - Test prueft nichts"
    return suppe, json.loads(knoten.get_text())


def _text(el) -> str:
    return " ".join(el.get_text(" ", strip=True).split())


def _katalog_zeile(suppe, mid: str):
    return next((z for z in suppe.select("#gr-katalogtabelle tr.gr-k-zeile")
                 if z.get("data-modell") == mid), None)


# ==========================================================================
# (a) Der KATALOG: Bündel ODER Listung genügt
# ==========================================================================

def test_buendel_ohne_listung_mit_einem_mestag_steht_im_katalog(tmp_path):
    """DER gemessene Fall des 17.09. (iPhone 18: 105 Bündel, keine Listung)
    als Fixture: ein Auto-Modell mit EINEM Bündel-Messtag und ohne jede
    Listung steht IM KATALOG - mit der Bündel-Angabe in der Preiszelle
    statt eines Barpreises (die P3-Regel „keine Modellzeile sagt ohne
    Preis" gilt seit P5 auch für den Bündel-weg) und OHNE toten
    Graph-Sprung: es ist nicht waehlbar, die Luecke heisst beim Namen."""
    root, state = _baue_buendel_modell(tmp_path, ["2026-09-15"])
    g = geraete_view.aufbereiten(state, lade_quellen(root),
                                 lade_katalog(root), heute=HEUTE)

    zeile = next((z for z in g["katalog_modelle"]
                  if z["schluessel"] == _MID), None)
    assert zeile is not None, \
        "Bündel ohne Listung ohne Katalog-Zeile - die P5-Regel greift nicht"
    assert zeile["nur_buendel"] is True
    assert zeile["buendel_monat"] == 45.0, zeile["buendel_monat"]
    assert zeile["buendel_anbieter"] == "o2"
    assert zeile["hat_buendel"] is True
    assert zeile["zr"] is False, "ein Messtag ist keine waehlbare Reihe"
    assert zeile["listungen"] == 0 and zeile["zeilen"] == []
    # Die Händler-Spalte nennt die Bündel-Anbieter, nicht "0 Händler" -
    # das widerspraeche der eigenen Preiszelle ("nur im Bündel bei o2").
    assert zeile["anbieter"] == ["o2"]
    assert zeile["anbieterzahl"] == 1


def test_buendel_ohne_listung_gerendert_luecke_statt_totem_link(tmp_path):
    """Dieselbe Lage nach regelkonformem RENDERN: die Katalog-Zeile steht
    mit „nur im Bündel" und der benannten Lücke „noch keine Zeitreihe" am
    Modellnamen - kein toter Deep-Link, kein Stummsein. Und sie hat KEINE
    Detailzeile: es gibt keine Listungs-Details, die Bündel-Angebote
    stehen im Vergleichs-Reiter und im Radar (keine Doppel-Darstellung)."""
    root, _ = _baue_buendel_modell(tmp_path, ["2026-09-15"])
    suppe, daten = _rendern(root)

    zeile = _katalog_zeile(suppe, _MID)
    assert zeile is not None, "Katalog-Zeile fehlt im gerenderten HTML"
    text = _text(zeile)
    assert "nur im Bündel" in text and "€/Monat" in text
    assert zeile.select_one("a.gr-sprung") is None, \
        "toter Graph-Sprung auf ein nicht waehlbares Modell"
    assert "noch keine Zeitreihe" in text
    # keine Detailzeile: data-auf trifft ins Leere (app.js bewacht das mit
    # `if (p.auf)`), und die Zeile zeigt keinen Aufklapp-Zeiger.
    assert suppe.select_one(f"#{zeile.get('data-auf')}") is None
    assert "gr-k--ohne-details" in (zeile.get("class") or [])
    # Gegenprobe der Regel: das Modell steht in KEINEM Wahl-Eingang.
    erlaubt = {k for k, v in daten["erlaubt"].items() if v}
    assert _MID not in erlaubt
    assert _MID not in {m["id"] for m in daten["suchindex"]}


def test_ab_dem_zweiten_mestag_ist_das_modell_waehlbar_und_verlinkt(tmp_path):
    """DIESELBE Fixture mit dem zweiten Bündel-Messtag: das Modell steht in
    der WAHL (Suchindex, erlaubt) - zwei Nächte bestätigen, dass der
    strukturierte Name kein Einmal-Fund war - und die Katalog-Zeile trägt
    den lebenden Graph-Sprung statt der Lücke. Bündel-Modelle erscheinen
    also mit dem zweiten Nachtlauf VON SELBST in der Zeitreihe: genau die
    Automatik von Antonios Forderung 8."""
    root, state = _baue_buendel_modell(tmp_path, ["2026-09-15", "2026-09-16"])
    g = geraete_view.aufbereiten(state, lade_quellen(root),
                                 lade_katalog(root), heute=HEUTE)
    suppe, daten = _rendern(root)

    erlaubt = {k for k, v in daten["erlaubt"].items() if v}
    assert _MID in erlaubt, "zwei Messtage, aber nicht waehlbar"
    assert _MID in {m["id"] for m in daten["suchindex"]}
    zeile = _katalog_zeile(suppe, _MID)
    assert zeile is not None
    sprung = zeile.select_one("a.gr-sprung")
    assert sprung is not None and sprung.get("data-modell") == _MID
    assert "noch keine Zeitreihe" not in _text(zeile)
    assert next(z for z in g["katalog_modelle"]
                if z["schluessel"] == _MID)["zr"] is True


# ==========================================================================
# (b) Die Zeitreihen-WAHL: erst ab 2 Bündel-Messtagen - und die 12
#     bündellosen Auto-Modelle (Watches, Tabs, AirPods) bleiben draussen
# ==========================================================================

def test_buendelloses_auto_modell_mit_listung_steht_nur_im_katalog(tmp_path):
    """Der FM-6.4-Fall: ein Auto-Modell MIT Listung (Tag 1) und OHNE jedes
    Bündel - die 12 Watches/Tabs/AirPods des Stand-Commits vom 17.09. Es
    steht im KATALOG (erste Listung genügt) und in KEINEM Wahl-Eingang der
    Zeitreihe: ein Wahl-Eintrag ohne zwei Messungen wäre ein unsichtbarer.
    Die Lücke „noch keine Zeitreihe" SCHWEIGT hier bewusst - ohne Bündel
    beginnt keine Reihe, die TCO-Spalte nennt den Grund („kein Bündel
    gemessen"), und derselbe Satz am Modellnamen wäre die zweite Aussage
    für dieselbe Tatsache (Beruhigungsregel: eine Aussage je Ort EINMAL)."""
    root, state = _baue_buendel_modell(tmp_path, [], mit_listung=True)
    g = geraete_view.aufbereiten(state, lade_quellen(root),
                                 lade_katalog(root), heute=HEUTE)
    suppe, daten = _rendern(root)

    zeile = next((z for z in g["katalog_modelle"]
                  if z["schluessel"] == _MID), None)
    assert zeile is not None, "erste Listung genügt für den Katalog"
    assert zeile["listungen"] == 1
    assert zeile["hat_buendel"] is False
    assert zeile["zr"] is False

    erlaubt = {k for k, v in daten["erlaubt"].items() if v}
    assert _MID not in erlaubt
    assert _MID not in {m["id"] for m in daten["suchindex"]}
    assert all(p["modell"] != _MID for p in
               geraete_zeitreihe.aufbereiten(state, g["tco"])["paare"])

    gerendert = _katalog_zeile(suppe, _MID)
    assert gerendert is not None
    assert "noch keine Zeitreihe" not in _text(gerendert), \
        "die Lücke verspricht eine Reihe, die ohne Bündel nicht beginnt"
    assert gerendert.select_one("a.gr-sprung") is None


# ==========================================================================
# (c) R3 der P5-Live-Pruefung: der Neu-Hinweis am Ort der Wahl
# ==========================================================================

def test_wahl_knoten_traegt_die_neuen_modelle_mit_datum(tmp_path):
    """Der Wahl-Knoten (#gr-zeitreihe-daten) traegt die "noch keine
    Zeitreihe"-Modelle - hat_buendel und nicht zr, GELESEN aus denselben
    Katalog-Zeilen - mit Titel und fruehestem Belegdatum (dasselbe Datum
    wie die Katalog-Zeile, keine zweite Rechnung). Der JS-Teil zeigt daraus
    den Hinweis am Suchfeld, wenn die Wahl selbst keinen Treffer hat."""
    root, _ = _baue_buendel_modell(tmp_path, ["2026-09-15"])
    _, daten = _rendern(root)

    neu = daten.get("katalog_neu") or []
    treffer = [n for n in neu if n["id"] == _MID]
    assert len(treffer) == 1, \
        "das hat_buendel-und-nicht-zr-Modell fehlt im Wahl-Knoten"
    n = treffer[0]
    assert "iPad Pro 13" in n["titel"]
    assert n["iso"] == HEUTE, n
    assert n["datum"] == "16. September", n
    # Gegenproben: WAHLBARE Modelle stehen nicht im Neu-Hinweis, und das
    # buendellose Pixel (Listung ohne Bündel) ebenso wenig.
    erlaubt = {k for k, v in daten["erlaubt"].items() if v}
    assert not (erlaubt & {x["id"] for x in neu})
    assert all("google-pixel-11" not in x["id"] for x in neu)


def test_ab_dem_zweiten_mestag_verschwindet_der_hinweis(tmp_path):
    """Derselbe Fall nach dem zweiten Messtag: das Modell ist waehlbar,
    der Neu-Hinweis duerfte nicht mehr stehen - sonst verspraeche er eine
    Zeitreihe, die bereits waehlbar ist."""
    root, _ = _baue_buendel_modell(tmp_path, ["2026-09-15", "2026-09-16"])
    _, daten = _rendern(root)
    neu = daten.get("katalog_neu") or []
    assert _MID not in {x["id"] for x in neu}
    assert _MID in {k for k, v in daten["erlaubt"].items() if v}


def test_buendelloses_modell_bekomt_keinen_neu_hinweis(tmp_path):
    """Ohne Bündel beginnt keine Reihe - der Hinweis "Neu seit ... -
    im Katalog ansehen" wuerde eine kommende Zeitreihe versprechen, die
    nicht kommt. Die TCO-Spalte nennt den Grund, der Hinweis schweigt
    (dieselbe Aussage-je-Ort-Regel wie die Luecke in (b))."""
    root, _ = _baue_buendel_modell(tmp_path, [], mit_listung=True)
    _, daten = _rendern(root)
    assert _MID not in {x["id"] for x in (daten.get("katalog_neu") or [])}
