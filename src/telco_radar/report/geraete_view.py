"""Alles, was /geraete.html und /geraete-quellen.html brauchen.

Wie jede Dauerseite dieses Portals: ein `aufbereiten()`, das aus dem Zustand
ein fertiges Dict macht. Kein Netz, kein Modell, kein Schreibzugriff - die
Seite laesst sich damit ohne Lauf bauen und ohne Browser pruefen.

DIE POSITIONSKARTE
------------------
Vorbild ist die Canalys-Grafik "Flagship portfolios: price positioning": Y
ist der Preis in Euro, X sind kategoriale Spalten, jedes Geraet ein Punkt.
Zwei Dinge macht diese Umsetzung anders, und beide sind der eigentliche
Nutzen:

1. **Zwei Ansichten.** Spalten = HERSTELLER beantwortet "wie ist ein
   Portfolio ueber die Preisachse verteilt". Spalten = ANBIETER beantwortet
   "was kostet dasselbe Geraet bei wem" - und das ist die Frage, wegen der
   diese Seite existiert. Beide Ansichten werden hier fertig gerechnet; der
   Umschalter blendet nur um, er laedt nicht neu.
2. **Kollisionen werden entzerrt.** In der Vorlage ueberlappen die Labels.
   Punkte im selben Preisbereich bekommen hier einen senkrechten Versatz und
   eine Verbindungslinie zum echten Wert - der Punkt sitzt weiter auf seiner
   Preisachse, nur das Etikett rueckt.

Gerechnetes SVG, keine Bibliothek. Kein CDN-JS ist Hausregel, und die
Koordinaten stehen fertig im Datensatz - damit ist die Darstellung ohne
Browser testbar.

DIE ZWEI PREISARTEN
-------------------
In die Karte kommt ausschliesslich der Geraetepreis OHNE Vertrag. Eine
Zuzahlung im Tarifbuendel ist keine vergleichbare Zahl (Teil C4); sie steht
in der SKU-Matrix mit ihrem Tarif daneben, aber nie als Punkt neben einem
Ladenpreis.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from ..analyze import geraete_lifecycle
from ..analyze.geraete_store import (
    GeraeteDB,
    Preishistorie,
    STATUS_AKTIV,
    STATUS_AUSGELISTET,
    STATUS_VERMUTLICH,
)

log = logging.getLogger(__name__)

BREITE, HOEHE = 980, 540
RAND_L, RAND_R, RAND_O, RAND_U = 66, 18, 20, 70

# Preisachse: feste Schrittweite wie in der Vorlage. Sie beginnt bei NULL -
# eine abgeschnittene Preisachse laesst kleine Unterschiede riesig aussehen,
# und bei einem Preisvergleich ist das keine Gestaltungsfrage.
Y_SCHRITT = 200
# Untergrenze der Achse. Die Kehrseite der Nullpunkt-Regel: ein Portfolio aus
# reinen Einstiegsgeraeten (alles unter 300 EUR) draengt sich sonst im
# untersten Zehntel. 800 ist der Kompromiss - hoch genug, dass die Achse eine
# Aussage behaelt, niedrig genug, dass ein Guenstig-Sortiment noch Luft hat.
Y_MINDEST = 800

# Mindestabstand zweier Etiketten in einer Spalte. Darunter wird entzerrt.
_ENTZERR_ABSTAND = 14

# Abstand des Etiketts vom Punkt (muss zum `x`-Versatz in der Vorlage passen).
_ETIKETT_ABSTAND = 10

# Ungefaehre Zeichenbreite bei 10px - reicht, um ein Etikett auf die
# Spaltenbreite zu kuerzen, statt es in die Nachbarspalte laufen zu lassen.
_ZEICHENBREITE = 5.1

_SICHTBAR = (STATUS_AKTIV, STATUS_VERMUTLICH)

# Wie weit "diese Woche" zurueckreicht. Bewusst weiter als sieben Tage: der
# Bericht erscheint zweimal woechentlich, und ein ausgefallener naechtlicher
# Lauf darf eine echte Bewegung nicht verschlucken.
FENSTER_TAGE = 14

EIGEN = ("vodafone",)

SEGMENT_LABEL = {"flagship": "Flaggschiff", "premium": "Premium",
                 "mid": "Mittelklasse", "entry": "Einstieg", "": "ohne Segment"}


def _ist_eigen(anbieter: str) -> bool:
    return (anbieter or "").strip().lower() in EIGEN


def _kurz(text: str, breite_px: float) -> str:
    grenze = max(6, int(breite_px / _ZEICHENBREITE))
    text = text or ""
    return text if len(text) <= grenze else text[:grenze - 1].rstrip() + "…"


# --------------------------------------------------------------------------
# Die Positionskarte
# --------------------------------------------------------------------------

def _karte(punkte: list, spaltenfeld: str, achsname: str) -> dict:
    """Eine Ansicht der Positionskarte.

    `punkte` sind Dicts mit mindestens `preis`, `label`, `eigen` und dem
    Spaltenfeld. Gibt Koordinaten, Achsen und Spalten fertig zurueck.
    """
    brauchbar = [p for p in punkte if p.get("preis") is not None]
    if not brauchbar:
        return {"hat_daten": False, "punkte": [], "spalten": [], "y_ticks": [],
                "breite": BREITE, "hoehe": HOEHE, "rand_l": RAND_L,
                "rand_u": RAND_U, "rand_o": RAND_O, "achsname": achsname}

    hoechster = max(p["preis"] for p in brauchbar)
    y_max = max(Y_MINDEST, int((hoechster // Y_SCHRITT + 1) * Y_SCHRITT))
    spaltennamen = sorted({p[spaltenfeld] for p in brauchbar})
    innen = BREITE - RAND_L - RAND_R
    breite_spalte = innen / max(1, len(spaltennamen))

    def py(preis: float) -> float:
        return HOEHE - RAND_U - (preis / y_max) * (HOEHE - RAND_O - RAND_U)

    spalten = []
    for i, name in enumerate(spaltennamen):
        spalten.append({
            "name": name,
            "x": round(RAND_L + (i + 0.5) * breite_spalte, 1),
            "x0": round(RAND_L + i * breite_spalte, 1),
            "breite": round(breite_spalte, 1),
            "label": _kurz(name, breite_spalte - 6),
        })
    index = {s["name"]: s for s in spalten}

    # Der Text beginnt RECHTS vom Punkt, und der Punkt sitzt in der
    # Spaltenmitte - dem Etikett steht also nur die halbe Spalte zur
    # Verfuegung. Die Formel des Spaltenkopfes (ganze Breite) gilt hier
    # nicht: der traegt text-anchor="middle", das Etikett nicht.
    etikettbreite = breite_spalte / 2 - _ETIKETT_ABSTAND - 4
    unterkante = HOEHE - RAND_U

    gezeichnet = []
    verborgen = 0
    for name in spaltennamen:
        in_spalte = sorted([p for p in brauchbar if p[spaltenfeld] == name],
                           key=lambda p: -p["preis"])
        spalte = index[name]
        letzte = None
        for p in in_spalte:
            cy = py(p["preis"])
            # Entzerren: das Etikett rueckt nach unten, der PUNKT bleibt auf
            # seinem Preis. Die Verbindungslinie macht den Versatz sichtbar -
            # sonst waere es eine stille Verschiebung der Aussage.
            ly = cy if letzte is None else max(cy, letzte + _ENTZERR_ABSTAND)
            # ... aber nur bis zur Nulllinie. Ohne diesen Deckel waendern die
            # Etiketten einer vollen Spalte unter die Achse und aus dem Bild:
            # bei 450 px Zeichenhoehe und 14 px Mindestabstand passen 32
            # Etiketten, mehr nicht. Was nicht mehr passt, bekommt KEIN
            # Etikett - der Punkt bleibt, sein Titel bleibt, und die Legende
            # sagt, wie viele es waren. Eine stille Kappung waere schlimmer
            # als eine sichtbare Luecke.
            beschriftet = ly <= unterkante
            if beschriftet:
                letzte = ly
            else:
                verborgen += 1
            gezeichnet.append({
                **p,
                "cx": spalte["x"],
                "cy": round(cy, 1),
                "ly": round(min(ly, unterkante), 1),
                "verschoben": beschriftet and abs(ly - cy) > 0.5,
                "beschriftet": beschriftet,
                "label_kurz": _kurz(p["label"], etikettbreite) if beschriftet else "",
                "spalte": name,
            })

    return {
        "hat_daten": True,
        "punkte": gezeichnet,
        "spalten": spalten,
        "y_max": y_max,
        "y_ticks": [{"wert": w, "y": round(py(w), 1)}
                    for w in range(0, y_max + 1, Y_SCHRITT)],
        "breite": BREITE, "hoehe": HOEHE, "rand_l": RAND_L,
        "rand_r": RAND_R, "rand_u": RAND_U, "rand_o": RAND_O,
        "achsname": achsname,
        "anzahl": len(gezeichnet),
        "spaltenzahl": len(spalten),
        "etiketten_verborgen": verborgen,
    }


# --------------------------------------------------------------------------
# "Was diese Woche auffaellt"
# --------------------------------------------------------------------------

def zahlen_im_text(text: str) -> set:
    """JEDE Zahl eines Satzes, als Vergleichsform.

    Der erste Anlauf las nur Zahlen MIT Einheit (€, %) - und war damit fail
    OPEN: "Das iPhone kostet 999 Euro" kam vollstaendig erfunden durch, weil
    "Euro" ausgeschrieben war. Deshalb wird jetzt alles geprueft, und die
    Zahlen der Eigennamen ("iPhone 16 Pro Max", "1&1") kommen ueber
    `zahlen_der_namen()` in die erlaubte Menge. Ein Name ist keine
    Behauptung - aber er muss ANGEMELDET sein, nicht ungeprueft.

    Gelesen wird mit `strukturdaten.lies_preis`, derselben Funktion, die
    auch die Preise der Shops liest: zwei Zahlenleser waeren zwei Meinungen
    darueber, was "1.449" bedeutet, und der Waechter bliebe genau an dieser
    Differenz gruen, ohne etwas zu pruefen. Nur vor einem Prozentzeichen
    gilt das Komma als Dezimaltrenner ("27,8 %" ist 27,8 und nicht 278).
    """
    import re

    from ..collect.geraete.strukturdaten import lies_preis

    gefunden = set()
    for roh, prozent in re.findall(r"(\d[\d.,]*)\s*(%?)", text or ""):
        roh = roh.rstrip(".,")
        if not roh:
            continue
        if prozent:
            try:
                gefunden.add(round(float(roh.replace(",", ".")), 2))
            except ValueError:
                pass
            continue
        wert = lies_preis(roh)
        if wert is not None:
            gefunden.add(round(wert, 2))
        else:
            try:
                gefunden.add(round(float(roh.replace(".", "").replace(",", ".")), 2))
            except ValueError:
                pass
    return gefunden


def zahlen_der_namen(*namen) -> set:
    """Die Zahlen, die in Eigennamen stecken - "iPhone 16 Pro Max", "1&1",
    "Galaxy S25". Sie sind keine Behauptung ueber den Markt, muessen dem
    Waechter aber bekannt sein, sonst verwirft er wahre Saetze."""
    gefunden = set()
    for name in namen:
        gefunden |= zahlen_im_text(str(name or ""))
    return gefunden


def pruefe_zahlen(text: str, erlaubt: set) -> bool:
    """Steht jede Zahl dieses Satzes wirklich im Datensatz?

    Akzeptanzkriterium aus Teil E: "Ein Preis, der nicht im Rohdatensatz
    steht, kommt nicht in den Text der Karte." Die Saetze entstehen derzeit
    deterministisch aus den Daten - der Waechter ist trotzdem gebaut und
    getestet, denn genau an dieser Stelle wuerde ein Editor spaeter
    ansetzen, und dann muss die Sperre schon dastehen statt erst gebaut zu
    werden.

    Vorbild ist `analyze/faithfulness.py`: fail closed. Was sich nicht
    pruefen laesst, erscheint nicht.
    """
    return zahlen_im_text(text).issubset({round(float(z), 2) for z in erlaubt})


def _im_fenster(datum: str, heute: str, tage: int = FENSTER_TAGE) -> bool:
    """Liegt *datum* im Berichtsfenster?

    Ohne diese Pruefung stand eine Preisaenderung vom 9. Maerz in der
    Augustausgabe unter "Was diese Woche auffaellt" - und blieb dort in
    JEDER Ausgabe stehen, bis sich der Preis wieder aenderte. Die Rubrik
    heisst "diese Woche"; dann muss sie auch eine Woche meinen.

    Das Fenster ist mit vierzehn Tagen bewusst weiter als eine Woche: der
    Bericht erscheint zweimal woechentlich, und ein ausgefallener
    naechtlicher Lauf darf eine echte Bewegung nicht verschlucken.
    """
    if not datum or not heute:
        return False
    a, b = _tag(datum), _tag(heute)
    if a is None or b is None:
        return False
    return 0 <= (b - a).days <= tage


def _tag(wert):
    from datetime import datetime
    try:
        return datetime.strptime(str(wert).strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _auffaellig(eintraege: list, historie: Preishistorie, katalog,
                heute: str) -> dict:
    """Die groessten Bewegungen DIESES Zeitraums - aus den Deltas gerechnet."""
    bewegungen = []
    for e in eintraege:
        reihe = historie.reihe(e["id"])
        if len(reihe) < 2:
            continue
        if not _im_fenster(reihe[-1].get("datum", ""), heute):
            continue
        alt = reihe[-2].get("preis_ohne_vertrag")
        neu = reihe[-1].get("preis_ohne_vertrag")
        if alt is None or neu is None or alt == 0 or alt == neu:
            continue
        g = katalog.nach_id(e.get("device_id"))
        bewegungen.append({
            "modell": g.modell if g else e.get("device_id"),
            "anbieter": e.get("anbieter"),
            "von": alt, "auf": neu,
            "delta": round(neu - alt, 2),
            "prozent": round((neu - alt) / alt * 100.0, 1),
            "datum": reihe[-1].get("datum", ""),
            "url": e.get("quelle_url", ""),
        })
    bewegungen.sort(key=lambda b: -abs(b["delta"]))

    # Ein Fenster, kein Stichtag. Der naechtliche Lauf schreibt an sechs von
    # sieben Tagen ein Datum, das nie ein Renderdatum ist - mit `== heute`
    # tauchte nur auf, was der Bericht selbst gefunden hat.
    neu_gelistet = [e for e in eintraege if _im_fenster(e.get("first_seen", ""), heute)]
    verschwunden = [e for e in eintraege
                    if e.get("status") == STATUS_AUSGELISTET
                    and _im_fenster(e.get("ended_since", ""), heute)]

    erlaubt = set()
    for b in bewegungen:
        erlaubt.update({abs(b["delta"]), b["von"], b["auf"], abs(b["prozent"])})
        erlaubt |= zahlen_der_namen(b["modell"], b["anbieter"])
    erlaubt.update({len(neu_gelistet), len(verschwunden), len(bewegungen)})

    saetze = []
    for b in bewegungen[:5]:
        richtung = "günstiger" if b["delta"] < 0 else "teurer"
        saetze.append(f"{b['modell']} bei {b['anbieter']}: "
                      f"{abs(b['delta']):.2f} € {richtung} "
                      f"({b['von']:.2f} € auf {b['auf']:.2f} €).")
    if neu_gelistet:
        saetze.append(f"{len(neu_gelistet)} Gerät{'e' if len(neu_gelistet) != 1 else ''} "
                      f"neu im Regal.")
    if verschwunden:
        saetze.append(f"{len(verschwunden)} Gerät{'e' if len(verschwunden) != 1 else ''} "
                      f"aus dem Portfolio gefallen.")

    # Fail closed: ein Satz, dessen Zahlen nicht im Datensatz stehen,
    # erscheint nicht. Heute kann das nicht passieren - morgen, mit einem
    # Editor davor, schon.
    geprueft = [s for s in saetze if pruefe_zahlen(s, erlaubt)]
    if len(geprueft) != len(saetze):
        log.warning("Geraeteradar: %d Satz/Saetze mit ungedeckten Zahlen "
                    "verworfen", len(saetze) - len(geprueft))

    return {
        "saetze": geprueft,
        "bewegungen": bewegungen[:12],
        "neu": [{"modell": (katalog.nach_id(e.get("device_id")).modell
                            if katalog.nach_id(e.get("device_id"))
                            else e.get("device_id")),
                 "anbieter": e.get("anbieter"), "url": e.get("quelle_url", "")}
                for e in neu_gelistet[:12]],
        "weg": [{"modell": (katalog.nach_id(e.get("device_id")).modell
                            if katalog.nach_id(e.get("device_id"))
                            else e.get("device_id")),
                 "anbieter": e.get("anbieter"), "seit": e.get("ended_since", "")}
                for e in verschwunden[:12]],
        "hat_daten": bool(geprueft or bewegungen),
    }


# --------------------------------------------------------------------------
# SKU-Matrix
# --------------------------------------------------------------------------

def _matrix(eintraege: list, katalog) -> dict:
    """Modell x Anbieter. Zelle: Zahl der Varianten und Preisspanne."""
    anbieter = sorted({e.get("anbieter") for e in eintraege if e.get("anbieter")})
    zeilen: dict[str, dict] = {}
    for e in eintraege:
        gid = e.get("device_id")
        g = katalog.nach_id(gid)
        zeile = zeilen.setdefault(gid, {
            "device_id": gid,
            "modell": g.modell if g else gid,
            "hersteller": g.hersteller if g else "ohne Katalogeintrag",
            "generation": g.generation if g else None,
            "segment": g.segment if g else "",
            "zellen": {},
        })
        zelle = zeile["zellen"].setdefault(e.get("anbieter"), {
            "varianten": [], "preise": [], "buendel": []})
        zelle["varianten"].append({
            "sku_id": e.get("sku_id"),
            "speicher": e.get("speicher_gb"),
            "farbe": e.get("farbe_normalisiert") or e.get("farbe_roh") or "",
            "farbe_roh": e.get("farbe_roh", ""),
            "preis": e.get("preis_ohne_vertrag"),
            "zuzahlung": e.get("zuzahlung"),
            "tarif": e.get("tarif_referenz", ""),
            "verfuegbarkeit": e.get("verfuegbarkeit", "unbekannt"),
            "status": e.get("status"),
            "zustand": e.get("zustand", "neu"),
            "url": e.get("quelle_url", ""),
            "abgerufen_am": e.get("abgerufen_am", ""),
        })
        if e.get("preis_ohne_vertrag") is not None:
            zelle["preise"].append(e["preis_ohne_vertrag"])
        if e.get("zuzahlung") is not None:
            zelle["buendel"].append(e["zuzahlung"])

    out = []
    for zeile in zeilen.values():
        zellen = []
        for name in anbieter:
            z = zeile["zellen"].get(name)
            if not z:
                zellen.append({"anbieter": name, "leer": True})
                continue
            preise = sorted(z["preise"])
            zellen.append({
                "anbieter": name,
                "leer": False,
                "varianten": sorted(z["varianten"],
                                    key=lambda v: (v["speicher"] or 0, v["farbe"])),
                "anzahl": len(z["varianten"]),
                "speicher": sorted({v["speicher"] for v in z["varianten"]
                                    if v["speicher"]}),
                "farben": sorted({v["farbe"] for v in z["varianten"] if v["farbe"]}),
                "min": preise[0] if preise else None,
                "max": preise[-1] if preise else None,
                "nur_buendel": not preise and bool(z["buendel"]),
            })
        zeile["zellen"] = zellen
        zeile["anbieter_mit_geraet"] = sum(1 for z in zellen if not z["leer"])
        out.append(zeile)

    out.sort(key=lambda z: (z["hersteller"], -(z["generation"] or 0), z["modell"]))
    return {"anbieter": anbieter, "zeilen": out}


# --------------------------------------------------------------------------
# Datenbasis und Luecken
# --------------------------------------------------------------------------

def _quellenlage(quellen, db: GeraeteDB, eintraege: list) -> dict:
    """Wer liefert, wer nicht - und warum nicht.

    Kein Anbieter verschwindet stillschweigend (Teil E). Das gilt auch fuer
    die Marken ohne Hardware-Vermarktung: sie stehen in einer eigenen Zeile,
    nicht als leere Karte im Raster.
    """
    mit_daten = {e.get("anbieter") for e in eintraege}
    bekannt = {a.name for a in quellen.anbieter}
    zeilen, ohne_hardware = [], []
    for a in sorted(quellen.anbieter, key=lambda x: (x.rang, x.name)):
        vermarktung = db.hardware_vermarktung(a.name)
        if a.methode == "kein_hardware":
            vermarktung = "nein"
        satz = {
            "name": a.name, "typ": a.typ, "netz": a.netz, "gruppe": a.gruppe,
            "rang": a.rang, "methode": a.methode, "eigen": a.eigen,
            "aktiv": a.aktiv, "crawlbar": a.crawlbar, "grund": a.grund,
            "hinweis": a.hinweis,
            "einstiege": [{"url": e.url, "label": e.label, "kind": e.kind}
                          for e in a.crawled_einstiege],
            "geraete": sum(1 for e in eintraege if e.get("anbieter") == a.name),
            "liefert": a.name in mit_daten,
            "hardware_vermarktung": vermarktung,
            "bilanz": db.laufbilanz(a.name),
        }
        if vermarktung == "nein":
            ohne_hardware.append(satz)
        else:
            zeilen.append(satz)

    # Ein Anbieter, der in der Datenbank steht, aber nicht (mehr) in der
    # Konfiguration: umbenannt, entfernt, vertippt. Die Datenbank loescht per
    # Design nie, also bleibt er da - und faellt sonst genau unter dem Satz
    # durch, der verspricht, dass kein Anbieter stillschweigend fehlt.
    for name in sorted(n for n in mit_daten if n and n not in bekannt):
        zeilen.append({
            "name": name, "typ": "", "netz": "", "gruppe": "", "rang": 999,
            "methode": "nicht konfiguriert", "eigen": False, "aktiv": False,
            "crawlbar": False,
            "grund": "Steht mit Daten in der Datenbank, aber nicht in "
                     "config/geraete_quellen.yaml - umbenannt oder entfernt. "
                     "Die Bestandseinträge bleiben, werden aber nicht mehr "
                     "aufgefrischt.",
            "hinweis": "", "einstiege": [],
            "geraete": sum(1 for e in eintraege if e.get("anbieter") == name),
            "liefert": True, "hardware_vermarktung": "ja",
            "bilanz": db.laufbilanz(name),
        })

    return {
        "zeilen": zeilen,
        "ohne_hardware": ohne_hardware,
        "liefernd": sum(1 for z in zeilen if z["liefert"]),
        # Der Nenner der Zeile "N von M liefern Daten" muss zu den ZEILEN
        # passen, die darunter stehen - sonst steht ueber 21 Zeilen die Zahl
        # 23 (der Fehlertyp aus CLAUDE.md §6).
        "aufgefuehrt": len(zeilen),
        "konfiguriert": len(quellen.anbieter),
        "unbekannt": [n for n in sorted(mit_daten) if n and n not in bekannt],
        "seiten": quellen.seiten_zahl,
    }


def _farbbericht(eintraege: list) -> list:
    """Unbekannte Farbschreibweisen mit der Zahl ihrer Listungen.

    Die Arbeitsliste fuer config/farben.yaml. Sie speist sich aus den
    FARBFELDERN der Quellen - eine Farbe, die nur im Titel stand und die
    Tabelle nicht kennt, taucht hier nicht auf, weil sie gar nicht erst
    uebernommen wird (das waere Raten).
    """
    gezaehlt: dict[str, int] = {}
    for e in eintraege:
        if e.get("farbe_roh") and not e.get("farbe_normalisiert"):
            gezaehlt[e["farbe_roh"]] = gezaehlt.get(e["farbe_roh"], 0) + 1
    return [{"schreibweise": k, "listungen": v}
            for k, v in sorted(gezaehlt.items(), key=lambda kv: (-kv[1], kv[0]))]


def _katalogluecken(katalog) -> dict:
    ohne_start = [g.modell for g in katalog.geraete if not g.marktstart]
    ohne_kette = [g.modell for g in katalog.geraete
                  if g.vorgaenger and katalog.nach_id(g.vorgaenger_device_id) is None]
    return {
        "modelle": len(katalog.geraete),
        "ohne_marktstart": sorted(ohne_start),
        "ohne_kette": sorted(ohne_kette),
    }


# --------------------------------------------------------------------------
# Der Einstieg
# --------------------------------------------------------------------------

def leer(fehler: str = "") -> dict:
    """Der Notzustand: die Seite entsteht trotzdem und sagt, was los ist.

    Ohne ihn liess ein einziger kaputter Eintrag beide Seiten ganz
    verschwinden - und weil `site/` committet wird, blieb live die Fassung
    der Vorwoche stehen. Ein Totalausfall, der wie ein gruener Lauf aussieht.
    """
    return {
        "hat_daten": False, "stand": "", "abgerufen_bis": "", "abgerufen_ab": "",
        "fenster_tage": FENSTER_TAGE, "ohne_katalog": [], "db_lesbar": not fehler,
        "fehler": fehler,
        "bilanz": {"geraete": 0, "listungen": 0, "skus": 0, "anbieter": 0,
                   "ausgelistet": 0, "preispunkte": 0, "in_der_karte": 0},
        "karte_hersteller": {"hat_daten": False, "punkte": [], "spalten": [],
                             "etiketten_verborgen": 0, "spaltenzahl": 0},
        "karte_anbieter": {"hat_daten": False, "punkte": [], "spalten": [],
                           "etiketten_verborgen": 0, "spaltenzahl": 0},
        "segmente": [], "segment_label": SEGMENT_LABEL, "speicherstufen": [],
        "auffaellig": {"hat_daten": False, "saetze": [], "bewegungen": [],
                       "neu": [], "weg": []},
        "matrix": {"anbieter": [], "zeilen": []},
        "lifecycle": {"duenn": True, "punkte": 0, "wochen": 0, "hinweis": "",
                      "dauern": [], "verfaelle": [], "trends": [],
                      "nachfolger": [], "portfolio": []},
        "quellenlage": {"zeilen": [], "ohne_hardware": [], "liefernd": 0,
                        "aufgefuehrt": 0, "konfiguriert": 0, "unbekannt": [],
                        "seiten": 0},
        "farbbericht": [],
        "katalog": {"modelle": 0, "ohne_marktstart": [], "ohne_kette": []},
    }


def aufbereiten(state_dir: Path, quellen, katalog, heute: str = "") -> dict:
    """Alles fuer /geraete.html und /geraete-quellen.html."""
    state_dir = Path(state_dir)
    db = GeraeteDB(state_dir / "geraete_db.json")
    historie = Preishistorie(state_dir / "geraete_preise.jsonl")
    alle = db.eintraege()
    sichtbar = [e for e in alle if e.get("status") in _SICHTBAR]

    punkte_ohne_vertrag = []
    for e in sichtbar:
        preis = e.get("preis_ohne_vertrag")
        if preis is None:
            continue
        g = katalog.nach_id(e.get("device_id"))
        speicher = e.get("speicher_gb")
        punkte_ohne_vertrag.append({
            "sku_id": e.get("sku_id"),
            "device_id": e.get("device_id"),
            "hersteller": g.hersteller if g else "ohne Katalogeintrag",
            "modell": g.modell if g else e.get("device_id"),
            "generation": g.generation if g else None,
            "segment": g.segment if g else "",
            "anbieter": e.get("anbieter"),
            "anbieter_typ": e.get("anbieter_typ", ""),
            "preis": float(preis),
            "speicher": speicher,
            "farbe": e.get("farbe_normalisiert") or e.get("farbe_roh") or "",
            "verfuegbarkeit": e.get("verfuegbarkeit", "unbekannt"),
            "url": e.get("quelle_url", ""),
            "abgerufen_am": e.get("abgerufen_am", ""),
            "eigen": _ist_eigen(e.get("anbieter", "")),
            "label": f"{g.modell if g else e.get('device_id')}"
                     + (f" · {speicher} GB" if speicher else ""),
        })

    # Nur die aktuelle Generation je Hersteller-Familie kennzeichnen - der
    # Filter blendet, er rechnet nicht neu.
    hoechste: dict[str, int] = {}
    for p in punkte_ohne_vertrag:
        if p["generation"] is None:
            continue
        hoechste[p["hersteller"]] = max(hoechste.get(p["hersteller"], 0),
                                        p["generation"])
    for p in punkte_ohne_vertrag:
        p["aktuelle_generation"] = (p["generation"] is not None
                                    and p["generation"] == hoechste.get(p["hersteller"]))

    lifecycle = geraete_lifecycle.auswertung(
        alle, historie.alle_punkte(), katalog, heute)

    # Das ECHTE Abrufdatum. Faellt der naechtliche Lauf zwei Wochen aus,
    # behaelt die Datenbank ihre alten Werte - die Legende darf trotzdem
    # nicht den Berichtstag behaupten. Auf einer Seite, deren Verkaufsargument
    # der Belegzwang ist, ist das die teuerste Sorte falscher Zahl.
    abrufdaten = sorted(e.get("abgerufen_am") for e in sichtbar
                        if e.get("abgerufen_am"))
    ohne_katalog = sorted({e.get("device_id") for e in sichtbar
                           if katalog.nach_id(e.get("device_id")) is None})

    return {
        "hat_daten": bool(sichtbar),
        "stand": heute,
        "abgerufen_bis": abrufdaten[-1] if abrufdaten else "",
        "abgerufen_ab": abrufdaten[0] if abrufdaten else "",
        "fenster_tage": FENSTER_TAGE,
        "ohne_katalog": ohne_katalog,
        "db_lesbar": db.lesbar,
        "bilanz": {
            "geraete": len({e.get("device_id") for e in sichtbar}),
            "listungen": len(sichtbar),
            "skus": len({e.get("sku_id") for e in sichtbar}),
            "anbieter": len({e.get("anbieter") for e in sichtbar}),
            "ausgelistet": sum(1 for e in alle
                               if e.get("status") == STATUS_AUSGELISTET),
            "preispunkte": historie.punkte_gesamt,
            "in_der_karte": len(punkte_ohne_vertrag),
        },
        "karte_hersteller": _karte(punkte_ohne_vertrag, "hersteller", "Hersteller"),
        "karte_anbieter": _karte(punkte_ohne_vertrag, "anbieter", "Anbieter"),
        "segmente": sorted({p["segment"] for p in punkte_ohne_vertrag if p["segment"]}),
        "segment_label": SEGMENT_LABEL,
        "speicherstufen": sorted({p["speicher"] for p in punkte_ohne_vertrag
                                  if p["speicher"]}),
        "auffaellig": _auffaellig(alle, historie, katalog, heute),
        "matrix": _matrix(sichtbar, katalog),
        "lifecycle": lifecycle,
        "quellenlage": _quellenlage(quellen, db, sichtbar),
        "farbbericht": _farbbericht(sichtbar),
        "katalog": _katalogluecken(katalog),
    }
