"""Die Tarif-Seite: Effektivpreise und die Positionskarte.

Was diese Seite beantwortet
---------------------------
"Was kostet was wirklich, und wer liegt ueber dem, was am Markt ueblich
ist?" Das ist die erste Frage dieses Portals, die sich nicht aus Meldungen
beantworten laesst, sondern nur aus Daten.

Warum das Diagramm im Python gerechnet wird und nicht im Browser
----------------------------------------------------------------
Die Punktkoordinaten stehen fertig im Datensatz, das Template setzt nur noch
`<circle>`. Drei Gruende: es braucht keine Bibliothek (die Seite laedt kein
CDN-JS, das ist Hausregel), es ist ohne Browser testbar - eine Zahl auf
einer Seite ist erst wahr, wenn ein Test sie gegen die Daten haelt -, und
es funktioniert, wenn JavaScript nicht laeuft.

Unbegrenzte Tarife stehen NICHT in der Wolke
--------------------------------------------
Ein Tarif mit unbegrenztem Volumen hat auf einer Volumenachse keinen Ort.
Ihn ans rechte Ende zu setzen waere eine erfundene Zahl, und sie zoege die
Ausgleichsgerade mit. Solche Tarife stehen als eigene Liste darunter - mit
ihrem Effektivpreis, denn der ist bekannt und vergleichbar.

Die Live-Shop-Lesart fuehrt die Zeile, das Pflichtdokument bleibt Referenz
------------------------------------------------------------------------
Traegt ein Tarif zwei Staende - einen aus dem Pflichtdokument (`dokument`)
und einen aus der Shop-Seite von heute (`live_shop`), beide mit derselben
Titelzeile -, zeigt die Seite nur noch EINE Zeile: die der Live-Lesart, mit
ihrem eigenen Beleglink. Das Pflichtdokument verschwindet nicht aus dem
Bestand (`data/state/tarife.jsonl` behaelt beide Zeitreihen), es tritt hier
nur zurueck - als zweiter, kleinerer Link "Produktinformationsblatt
(Referenz)" an derselben Zeile, wenn seine Adresse eine andere ist.

Der Anlass: sechs der neun Telekom-Blaetter stammen aus dem Jahr 2021
(`…-20211121`, `…-20211005`) und werden bei jedem Lauf nur neu ABGERUFEN,
nie neu AUSGESTELLT - `abgerufen_am` wandert weiter, waehrend die Seite
"Stand [heutiges Datum]" ueber einem fuenf Jahre alten Dokument zeigt. Die
Shop-Kachel (`collect/tarif_telekom_kacheln.py`) traegt denselben Betrag,
aber mit dem Stand von heute und einem Link auf die Verkaufsseite.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from ..tarif_model import PREISTYP_LIVE_SHOP, Preisphase, Tarif
from .effektivpreis import VERGLEICHSMONATE, Effektivpreis, rechne, regression

log = logging.getLogger(__name__)

# Zeichenflaeche der Positionskarte.
BREITE, HOEHE = 760, 420
RAND_L, RAND_R, RAND_O, RAND_U = 58, 18, 18, 44

# Der eigene Konzern wird hervorgehoben - die Karte beantwortet "wo stehen
# WIR", nicht "wie sieht der Markt aus".
EIGEN = {"vodafone", "otelo"}


def _aus_satz(satz: dict) -> Tarif:
    """Einen gespeicherten Stand zurueck in ein Tarif-Objekt.

    `als_dict()` laesst den Rohtext weg; die Belegpruefung laeuft deshalb
    hier nicht mehr - sie ist beim Einlesen gelaufen, und das ist der
    richtige Ort dafuer.
    """
    t = Tarif()
    for feld, wert in satz.items():
        if feld in ("preisphasen", "geraetepreisstaffel", "tarif_id"):
            continue
        if hasattr(t, feld):
            setattr(t, feld, wert)
    t.preisphasen = [
        Preisphase(von_monat=int(p.get("von_monat", 1)),
                   bis_monat=p.get("bis_monat"),
                   betrag=float(p.get("betrag", 0)))
        for p in (satz.get("preisphasen") or [])
        if isinstance(p, dict)
    ]
    return t


def lade_staende(pfad: Path) -> list[dict]:
    """Der JUENGSTE Stand je Tarif aus data/state/tarife.jsonl."""
    if not Path(pfad).exists():
        return []
    neueste: dict[str, dict] = {}
    for zeile in Path(pfad).read_text(encoding="utf-8").splitlines():
        zeile = zeile.strip()
        if not zeile:
            continue
        try:
            satz = json.loads(zeile)
        except json.JSONDecodeError:
            continue
        if isinstance(satz, dict) and satz.get("tarif_id"):
            neueste[satz["tarif_id"]] = satz
    return list(neueste.values())


def _zeile(satz: dict) -> dict:
    tarif = _aus_satz(satz)
    preis: Effektivpreis = rechne(tarif)
    unbegrenzt = tarif.datenvolumen_gb == float("inf")
    return {
        "tarif_id": satz.get("tarif_id", ""),
        "anbieter": tarif.anbieter or "",
        "name": tarif.name or satz.get("tarif_id", ""),
        "art": tarif.art or "",
        "grundgebuehr": tarif.grundgebuehr,
        "volumen": None if unbegrenzt else tarif.datenvolumen_gb,
        "unbegrenzt": unbegrenzt,
        "laufzeit": tarif.laufzeit_monate,
        "effektiv": preis.monatlich,
        "belastbar": preis.belastbar,
        "je_gb": preis.preis_je_gb,
        "luecken": preis.luecken,
        "bestandteile": preis.bestandteile,
        "flags": [{"text": f.text, "gut": f.gut} for f in preis.flags],
        "url": tarif.dokument_url,
        "stand": tarif.versionsstand or tarif.abgerufen_am or "",
        "eigen": (tarif.anbieter or "").strip().lower() in EIGEN,
        # Nur gesetzt, wenn _bevorzuge_live_shop() ein Pflichtdokument
        # mit derselben Titelzeile zurueckgestuft hat.
        "referenz_url": satz.get("_referenz_url") or "",
        "referenz_stand": satz.get("_referenz_stand") or "",
    }


def _bevorzuge_live_shop(staende: list[dict]) -> list[dict]:
    """Von zwei Staenden mit derselben Titelzeile gewinnt die Live-Lesart.

    Nur wenn BEIDE preistypen fuer (Anbieter, Name) vorkommen: der
    `dokument`-Satz faellt aus der Liste, seine Adresse und sein Stand
    wandern als Referenz auf den ueberlebenden `live_shop`-Satz. Alles
    andere (zwei Tarife mit verschiedenem Namen, zwei Faelle derselben
    Lesart) bleibt unberuehrt.
    """
    gruppen: dict[tuple[str, str], list[dict]] = {}
    for satz in staende:
        schluessel = ((satz.get("anbieter") or "").strip().lower(),
                      (satz.get("name") or "").strip().lower())
        gruppen.setdefault(schluessel, []).append(satz)

    ergebnis: list[dict] = []
    for staende_der_gruppe in gruppen.values():
        live = [s for s in staende_der_gruppe
                if s.get("preistyp") == PREISTYP_LIVE_SHOP]
        dokument = [s for s in staende_der_gruppe
                   if s.get("preistyp") != PREISTYP_LIVE_SHOP]
        if not live or not dokument:
            ergebnis.extend(staende_der_gruppe)
            continue
        # Beide Lesarten vorhanden: die Live-Saetze bleiben, jeder
        # Dokument-Satz wird zu einer Referenz auf dem ERSTEN Live-Satz -
        # zwei Flex-Fassungen desselben Namens gibt es hier nicht, aber
        # zwei Dokument-Versionen (alt/neu) waeren sonst zwei Referenzen
        # auf derselben Zeile.
        primaer = live[0]
        for d in dokument:
            url = str(d.get("dokument_url") or "")
            if url and url != primaer.get("dokument_url"):
                primaer.setdefault("_referenz_url", url)
                primaer.setdefault("_referenz_stand",
                                   d.get("abgerufen_am") or "")
        ergebnis.extend(live)
    return ergebnis


def _karte(zeilen: list[dict]) -> dict:
    """Die Positionskarte: Punkte, Achsen und die Fair-Value-Linie."""
    punkte = [z for z in zeilen
              if z["volumen"] and z["effektiv"] is not None and z["belastbar"]]
    if not punkte:
        return {"punkte": [], "hat_daten": False, "gerade": None,
                "breite": BREITE, "hoehe": HOEHE, "x_ticks": [], "y_ticks": []}

    xs = [z["volumen"] for z in punkte]
    ys = [z["effektiv"] for z in punkte]
    # Die Achsen beginnen bei null: eine abgeschnittene Preisachse laesst
    # kleine Unterschiede riesig aussehen. Bei einem Preisvergleich ist das
    # keine Gestaltungsfrage.
    x_max = max(xs) * 1.08 or 1
    y_max = max(ys) * 1.15 or 1

    def px(x: float) -> float:
        return RAND_L + (x / x_max) * (BREITE - RAND_L - RAND_R)

    def py(y: float) -> float:
        return HOEHE - RAND_U - (y / y_max) * (HOEHE - RAND_O - RAND_U)

    gerade = regression([(z["volumen"], z["effektiv"]) for z in punkte])
    linie = None
    if gerade:
        a, b = gerade
        y0, y1 = a, a + b * x_max
        # Nur zeichnen, wenn die Gerade im Bild bleibt - eine Linie, die
        # oben aus dem Rahmen laeuft, behauptet mehr als die Daten hergeben.
        if 0 <= y0 <= y_max and 0 <= y1 <= y_max:
            linie = {"x1": round(px(0), 1), "y1": round(py(y0), 1),
                     "x2": round(px(x_max), 1), "y2": round(py(y1), 1),
                     "a": a, "b": b}

    gezeichnet = []
    for z in punkte:
        ueber = None
        if gerade:
            erwartet = gerade[0] + gerade[1] * z["volumen"]
            ueber = round(z["effektiv"] - erwartet, 2)
        gezeichnet.append({
            **z,
            "cx": round(px(z["volumen"]), 1),
            "cy": round(py(z["effektiv"]), 1),
            "ueber_linie": ueber,
        })

    schritt_x = max(1, int(x_max / 5))
    schritt_y = max(1, int(y_max / 5))
    return {
        "punkte": gezeichnet,
        "hat_daten": True,
        "gerade": linie,
        "breite": BREITE, "hoehe": HOEHE,
        "rand_l": RAND_L, "rand_u": RAND_U, "rand_o": RAND_O,
        "x_ticks": [{"wert": w, "x": round(px(w), 1)}
                    for w in range(0, int(x_max) + 1, schritt_x)],
        "y_ticks": [{"wert": w, "y": round(py(w), 1)}
                    for w in range(0, int(y_max) + 1, schritt_y)],
    }


def aufbereiten(state_pfad: Path, quellen=None, heute: str = "") -> dict:
    """Alles, was die Tarif-Seite braucht.

    `quellen` sind die konfigurierten Tarifquellen - sie sagen, wer beobachtet
    WIRD. Der Unterschied zu dem, was in den Daten steht, ist die
    Vollstaendigkeitsangabe, und die gehoert auf die Seite: eine
    Positionskarte mit zwei von sechs Anbietern ist keine Marktuebersicht,
    und sie darf nicht so aussehen.
    """
    staende = _bevorzuge_live_shop(lade_staende(Path(state_pfad)))
    zeilen = [_zeile(s) for s in staende]
    zeilen.sort(key=lambda z: (z["effektiv"] is None, z["effektiv"] or 0))

    vorhanden = sorted({z["anbieter"] for z in zeilen if z["anbieter"]})
    konfiguriert = sorted({q.anbieter for q in (quellen or [])})
    fehlend = [a for a in konfiguriert if a not in vorhanden]

    # DAS KOPFDATUM IST DAS DATUM DES NEUESTEN TARIFSATZES, nicht das des
    # letzten Wochenberichts (QA-Befund F3, Abnahmekriterium G7): `html.py`
    # reicht `heute=latest["date"]` durch, und am 04.09.2026 stand damit
    # "Stand 2026-09-02" ueber 44 Saetzen, die alle `abgerufen_am:
    # 2026-09-04` trugen. `heute` bleibt der Rueckfall fuer einen Bestand
    # ohne Abrufdatum.
    abgerufen = [str(s.get("abgerufen_am") or "") for s in staende]
    stand = max((a for a in abgerufen if a), default=heute)

    return {
        "zeilen": zeilen,
        "unbegrenzt": [z for z in zeilen if z["unbegrenzt"]],
        "karte": _karte(zeilen),
        "horizont": VERGLEICHSMONATE,
        "hat_daten": bool(zeilen),
        "stand": stand,
        "bilanz": {
            "tarife": len(zeilen),
            "anbieter": len(vorhanden),
            "belastbar": sum(1 for z in zeilen if z["belastbar"]),
            "mit_luecken": sum(1 for z in zeilen if z["luecken"]),
            "in_der_karte": len(_karte(zeilen)["punkte"]),
        },
        "vorhanden": vorhanden,
        "konfiguriert": konfiguriert,
        "fehlend": fehlend,
    }
