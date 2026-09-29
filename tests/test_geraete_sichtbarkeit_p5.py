"""P5-AUFTRAG 1 (STRATEGIE_GERAETE_V3, 18.09.2026): SICHTBARKEIT FOLGT DEN
DATEN, NICHT DEM WEG - Bündel ODER Listung genügt.

Antonios Forderung 8: „Wenn ein neues Modell rauskommt, ein neues iPhone,
muss es automatisch gecrawlt/erkannt werden, dass man das nicht manuell
programmieren muss. Ziel: dass man hier nie wieder was dran ändern muss."

Die gemessene Lücke (auto-doku.md, 17.09.): das iPhone 18 kam mit 105
Bündeln an, bevor die erste Listung stand - und der Katalog zählte nur
Listungen. Ein bündelloses Auto-Modell (damals Watch, Tab, AirPods; seit
29.09.2026 legt die Auto-Erkennung nur noch Smartphones an) erschien
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
diese Datei ist die Fixture-Seite derselben Regel. Seit dem Neuentwurf der
Geräteseite (29.09.2026, keine Zeitreihen-Wahl, kein Katalog-Reiter) prüft
sie die Regel an der Aufbereitung (`geraete_view.katalog_modelle`); die
Seitentests sind gefallen.
"""
from __future__ import annotations

import json
import pathlib

from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import geraete_view

from test_geraete_zeitreihe_ansicht import HEUTE, _baue, _sku

# Dasselbe Auto-Eintrag-Format wie in test_geraete_zeitreihe_ansicht: State,
# nicht Config - der Produktionsweg der E4-Auto-Erkennung.
#
# Beispielgeraet GEAENDERT 29.09.2026: bis dahin „iPad Pro 13". Seit der
# Regel „nur Smartphones" (Antonio will auf der Geraeteseite nur
# Smartphones; o2 fuehrte AirPods, Uhren und Tablets mit Tarif, die Seite
# zeigte „AirPods 5") faellt ein iPad in `lade_auto_zusaetze` und in
# `geraete_view.aufbereiten` heraus - die Sichtbarkeitsregel darunter liess
# sich an ihm nicht mehr pruefen. Das Galaxy XCover7 Pro ist ein Smartphone
# aus derselben Auto-Anlage vom 17.09. und traegt mit „xcover" ein Wort,
# das kein Hand-Modell der Fixture nennt (die Zeitreihen-Suche im
# Browser-Test braucht 0 Treffer in der Wahl).
_AUTO_EINTRAG = {"hersteller": "Samsung", "modell": "Galaxy XCover7 Pro",
                 "generation": None, "speicher": [256], "auto": "2026-09-15"}
_GID, _SPEICHER = "samsung-galaxy-xcover7-pro", 256
_MID = f"{_GID}-{_SPEICHER}"
_TARIF_ID, _TARIF = "o2:klein", "O2 Mobile Klein"


def _baue_buendel_modell(tmp_path: pathlib.Path, messtage: list[str],
                         mit_listung: bool = False):
    """Ein AUTO-Modell mit o2-Bündel im Band XS, N Bündel-Messtagen und
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
            "quelle_url": "https://example.de/o2/galaxy-xcover7-pro",
            "abgerufen_am": HEUTE, "verfuegbarkeit": "lieferbar",
            "confidence": "hoch", "einstiege": ["https://example.de/l"]})
        (state / "geraete_db.json").write_text(json.dumps(db),
                                               encoding="utf-8")

    tco = json.loads((state / "geraete_tco.json").read_text(encoding="utf-8"))
    buendel_id = f"buendel--o2--{_sku(_GID, _SPEICHER)}--{_TARIF_ID}"
    # Das Bündel im Store entsteht nur, wenn es Messungen gibt - die
    # bündellose Lage (ein Auto-Modell nur mit Listung) hat KEIN Bündel, nur die
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
            "rabatte": [], "quelle_url": "https://example.de/o2/galaxy-xcover7",
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
            "quelle_url": "https://example.de/o2/galaxy-xcover7", "abgerufen_am": tag,
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


# ==========================================================================
# (b) Die Zeitreihen-WAHL: erst ab 2 Bündel-Messtagen - und bündellose
#     Auto-Modelle bleiben draussen (der Fall vom 17.09. waren 12 Watches,
#     Tabs, AirPods; seit 29.09.2026 legt die Erkennung nur Smartphones an)
# ==========================================================================



# ==========================================================================
# (c) R3 der P5-Live-Pruefung: der Neu-Hinweis am Ort der Wahl
# ==========================================================================



