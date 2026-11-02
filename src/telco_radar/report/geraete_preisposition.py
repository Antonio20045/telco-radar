"""Preispositionierung: wo die Anbieter beim Preis stehen - ein Bild, ganz oben.

Eine Zeile je Modell (aktuelle iPhone-Generation, Galaxy-S-Reihe, Pixel-
Reihe, kleinster Speicher), ein Punkt je Anbieter auf EINER Preisachse, eine
dünne Linie vom günstigsten zum teuersten Punkt. Die Achse ist die Leitzahl
der Seite: TCO über 24 Monate im Band M (`LAUFZEIT_STANDARD`, `BAND`).

Nichts wird hier gerechnet, was die Seite schon rechnet (Clean Code 1): der
Wert eines Punktes ist `gesamt` der Karte, die `geraete_zeitreihe.
_band_zeilen` als Zeile des Bandes führt - dieselbe Auswahl wie Antwort-
Satz und Zeitreihe (vergleichbar, belastbar, frisch, Notbremse). Was die
Seite als alt oder ungeprüft behandelt, bekommt hier keinen Punkt. Die
Vodafone-Näherung ist kein Angebot und ebenfalls keiner. Ein Anbieter ohne
geprüften Preis ist eine benannte Lücke in der Zeile, nie ein Punkt bei 0.

Der Server zeichnet das SVG (zwei Ausführungen, breit und schmal, die das
Stylesheet umschaltet); es gibt kein JavaScript und keine Bibliothek.
Fällt die Aufbereitung aus, nennt die Seite den Ausfall (`fehler`).
"""

from __future__ import annotations

import logging
import math
from html import escape

from ..geraete_model import serie_aus_modell
from . import geraete_notbremse as notbremse
from . import geraete_rechenweg, geraete_zeitreihe, geraete_zeitreihe_geometrie
from .anbieter_farben import legendenname, slug_fuer, stil_fuer
from .geraete_laufzeit import LAUFZEIT_STANDARD

log = logging.getLogger(__name__)

BAND = "m"
LAUFZEIT = LAUFZEIT_STANDARD
EIGEN = "Vodafone"
ANBIETER_FOLGE = tuple(geraete_rechenweg.ANBIETER_FOLGE)

REIHEN = (("Apple", "iPhone"), ("Samsung", "Galaxy S"), ("Google", "Pixel"))
VARIANTEN = ("", "Plus", "Pro", "Pro Max", "Ultra", "Pro XL")
GENERATIONEN_ZURUECK = 1

MAX_TICKS = 7
TICK_SCHRITTE = (50, 100, 200, 250, 500, 1000, 2500, 5000)
FEHLT_TEXT = "kein aktueller Preis"
TICK_Y = 12

BREIT = {
    "w": 1000,
    "x0": 245,
    "x1": 925,
    "kopf": 26,
    "zeile": 48,
    "punkt_y": 17,
    "fehlt_y": 40,
}
SCHMAL = {
    "w": 358,
    "x0": 22,
    "x1": 334,
    "kopf": 30,
    "zeile": 62,
    "punkt_y": 36,
    "fehlt_y": 54,
}
R_PUNKT = 6.5
R_EIGEN = 8.5


def _de(wert: float) -> str:
    """1.234 - ganze Euro mit Punkt als Tausendertrenner."""
    return f"{wert:,.0f}".replace(",", ".")


def _eur(wert: float) -> str:
    """Betrag mit Euro-Zeichen, ganze Euro."""
    return f"{_de(wert)} €"


def modelle_waehlen(katalog) -> list[dict]:
    """Die Zeilen des Bildes aus dem Katalog: je Reihe und Ausführung die
    neueste Generation (höchstens `GENERATIONEN_ZURUECK` hinter der Reihe),
    mit dem kleinsten Speicher. Jede Zeile: id, name, speicher."""
    gewaehlt: list[dict] = []
    for hersteller, serie in REIHEN:
        kandidaten = []
        for geraet in getattr(katalog, "geraete", None) or []:
            if geraet.hersteller != hersteller or geraet.generation is None:
                continue
            if serie_aus_modell(geraet.modell) != serie or not geraet.speicher:
                continue
            rest = geraet.modell[len(serie) :].split()
            if not rest or rest[0] != str(geraet.generation):
                continue
            variante = " ".join(rest[1:])
            if variante in VARIANTEN:
                kandidaten.append((variante, geraet))
        if not kandidaten:
            continue
        neueste = max(g.generation for _, g in kandidaten)
        for variante in VARIANTEN:
            gens = [
                g
                for v, g in kandidaten
                if v == variante and g.generation >= neueste - GENERATIONEN_ZURUECK
            ]
            if not gens:
                continue
            geraet = max(gens, key=lambda g: g.generation)
            speicher = min(geraet.speicher)
            gewaehlt.append(
                {
                    "id": f"{geraet.device_id}-{speicher}",
                    "name": geraet.modell,
                    "speicher": speicher,
                }
            )
    return gewaehlt


def preise_je_anbieter(modell: dict | None) -> dict[str, dict]:
    """Anbieter -> Karte (Zeile des Bandes M bei 24 Raten) mit geprüftem Preis.

    Die Zeilen kommen aus `_band_zeilen`; hier fällt nur heraus, was kein
    Angebot mit Preis ist (Näherung) oder nicht zählt. Ohne Modell: leer."""
    if not modell:
        return {}
    satz = geraete_zeitreihe._band_zeilen(modell, LAUFZEIT).get(BAND) or {}
    karten: dict[str, dict] = {}
    for karte in satz.get("zeilen") or []:
        wert = karte.get("gesamt")
        if karte.get("naeherung") or wert is None:
            continue
        if not karte.get("frisch", True) or not notbremse.zaehlt(karte):
            continue
        karten.setdefault(karte["anbieter"], karte)
    return karten


def achse(werte: list[float]) -> dict | None:
    """Gemeinsame Achse: Anfang, Ende und runde Teilstriche; `None` ohne Werte."""
    if not werte:
        return None
    tief, hoch = min(werte), max(werte)
    for schritt in TICK_SCHRITTE:
        von = math.floor(tief / schritt) * schritt
        bis = math.ceil(hoch / schritt) * schritt
        if bis == von:
            bis = von + schritt
        if (bis - von) / schritt + 1 <= MAX_TICKS:
            break
    ticks = [von + i * schritt for i in range(int((bis - von) // schritt) + 1)]
    return {"von": von, "bis": bis, "schritt": schritt, "ticks": ticks}


def _anteil(wert: float, ach: dict) -> float:
    """Lage des Wertes auf der Achse, 0 (links) bis 1 (rechts)."""
    return (wert - ach["von"]) / (ach["bis"] - ach["von"])


def _marke(anbieter: str, x: float, y: float, r: float) -> str:
    """Die Form des Punktes: Kreis, sonst die Zusatzform des Anbieters."""
    form = geraete_zeitreihe_geometrie._form_pfad(stil_fuer(anbieter).marker, x, y, r)
    return form or f"<circle cx='{x:.1f}' cy='{y:.1f}' r='{r:.1f}'/>"


def _punkt(zeile: dict, p: dict, y: float) -> str:
    eigen = p["anbieter"] == EIGEN
    tip = f"{p['anbieter']}: {geraete_rechenweg._euro(p['wert'])}"
    return (
        f"<g class='gr-pp-punkt gr-anb--{p['slug']}{' gr-pp-eigen' if eigen else ''}' "
        f"data-modell='{escape(zeile['id'])}' data-anbieter='{escape(p['anbieter'])}' "
        f"data-wert='{p['wert']}' data-x='{p['x']:.1f}'>"
        f"<title>{escape(tip)}</title>"
        f"{_marke(p['anbieter'], p['x'], y, R_EIGEN if eigen else R_PUNKT)}</g>"
    )


def _klasse(p: dict) -> str:
    eigen = " gr-pp-summe--eigen" if p["anbieter"] == EIGEN else ""
    return f"gr-pp-summe{eigen}"


def _zahl(p: dict, x: float, y: float, anker: str = "start") -> str:
    """Ein Betrag am Bild; Vodafones Zahl ist die größte der Zeile."""
    return (
        f"<text class='{_klasse(p)}' x='{x:.1f}' y='{y:.1f}' "
        f"text-anchor='{anker}'>{_eur(p['wert'])}</text>"
    )


def _beschriftung(pts: list[dict], y: float, oben: float, schmal: bool) -> list[str]:
    """Die Beträge einer Zeile: günstigster und teuerster Punkt, Vodafone
    dazu, wo er mittendrin liegt. Schmal steht alles in der Namenszeile."""
    tief, hoch = pts[0], pts[-1]
    if schmal:
        zahlen = [tief] if tief is hoch else [tief, hoch]
        teile = [
            f"<tspan class='{_klasse(p)}' dx='{8 if i else 0}'>"
            f"{_eur(p['wert'])}</tspan>"
            for i, p in enumerate(zahlen)
        ]
        return [
            f"<text x='{SCHMAL['w']}' y='{oben + 14}' text-anchor='end'>"
            f"{''.join(teile)}</text>"
        ]
    aus = []
    if tief is not hoch:
        aus.append(_zahl(tief, tief["x"] - 14, y + 4, "end"))
    aus.append(_zahl(hoch, hoch["x"] + 14, y + 4))
    mitte = next((p for p in pts[1:-1] if p["anbieter"] == EIGEN), None)
    if mitte is not None:
        aus.append(_zahl(mitte, mitte["x"], y - 14, "middle"))
    return aus


def _svg(daten: dict, schmal: bool) -> str:
    """Das Bild in einer Ausführung. Zeilen und Achse kommen fertig in `daten`."""
    m = SCHMAL if schmal else BREIT
    ach = daten["achse"]
    zeilen = daten["zeilen"]
    hoehe = m["kopf"] + m["zeile"] * len(zeilen)
    x0, x1 = m["x0"], m["x1"]
    teile = [
        f"<svg class='gr-pp-svg' viewBox='0 0 {m['w']} {hoehe}' role='img' "
        f"aria-label='Preispositionierung: {escape(daten['achsentitel'])}' "
        "preserveAspectRatio='xMinYMin meet'>"
    ]
    tick_y = TICK_Y
    for tick in ach["ticks"]:
        x = x0 + _anteil(tick, ach) * (x1 - x0)
        teile.append(
            f"<line class='gr-pp-raster' x1='{x:.1f}' x2='{x:.1f}' "
            f"y1='{tick_y + 8}' y2='{hoehe}'/>"
            f"<text class='gr-pp-tick' x='{x:.1f}' y='{tick_y}' "
            f"text-anchor='middle'>{_de(tick)}</text>"
        )
    for i, zeile in enumerate(zeilen):
        oben = m["kopf"] + i * m["zeile"]
        y = oben + m["punkt_y"]
        name = escape(zeile["name"])
        gb = f"{zeile['speicher']} GB"
        if schmal:
            teile.append(
                f"<text class='gr-pp-name' x='0' y='{oben + 14}'>{name}"
                f"<tspan class='gr-pp-gb' dx='6'>{gb}</tspan></text>"
            )
        else:
            teile.append(
                f"<text class='gr-pp-name' x='0' y='{oben + 17}'>{name}</text>"
                f"<text class='gr-pp-gb' x='0' y='{oben + 34}'>{gb}</text>"
            )
        pts = zeile["punkte"]
        if pts:
            xs = [p["x"] for p in pts]
            teile.append(
                f"<line class='gr-pp-spanne' x1='{min(xs):.1f}' x2='{max(xs):.1f}' "
                f"y1='{y}' y2='{y}'/>"
            )
            teile += _beschriftung(pts, y, oben, schmal)
            for p in sorted(pts, key=lambda q: q["anbieter"] == EIGEN):
                teile.append(_punkt(zeile, p, y))
        if zeile["luecken"]:
            teile.append(
                f"<text class='gr-pp-fehlt' x='{x0 if not schmal else 0}' "
                f"y='{oben + m['fehlt_y']}'>{escape(', '.join(zeile['luecken']))}"
                f": {FEHLT_TEXT}</text>"
            )
    teile.append("</svg>")
    return "".join(teile)


def _legende(anbieter: list[str], ohne: set[str]) -> list[dict]:
    """Die Legende; ein Anbieter ohne Punkt in jeder Zeile nennt das hier einmal."""
    return [
        {
            "name": legendenname(a),
            "slug": slug_fuer(a),
            "fehlt": FEHLT_TEXT if a in ohne else "",
            "marke": _marke(a, 0, 0, 5.5 if a != EIGEN else 6.5),
        }
        for a in anbieter
    ]


def _bandname(tco: dict) -> str:
    for eintrag in tco.get("baender_katalog") or []:
        if isinstance(eintrag, dict) and eintrag.get("key") == BAND:
            return str(eintrag.get("label") or BAND.upper())
    return BAND.upper()


def aufbereiten(geraete: dict) -> dict:
    """Die Daten des Bildes aus dem Geräte-Kontext der Seite.

    `fehler` ist leer oder der Grund, warum das Bild fehlt; `leer` heißt: es
    gibt keinen einzigen geprüften Preis in den gewählten Modellen."""
    tco = geraete.get("tco") or {}
    katalog = geraete.get("katalog_obj")
    modelle = {m["id"]: m for m in tco.get("modelle") or []}
    rohe = []
    for wahl in modelle_waehlen(katalog):
        karten = preise_je_anbieter(modelle.get(wahl["id"]))
        rohe.append((wahl, karten))
    werte = [k["gesamt"] for _, karten in rohe for k in karten.values()]
    ach = achse(werte)
    titel = f"Kosten über {LAUFZEIT} Monate · Tarif {_bandname(tco)} · in €"
    if ach is None:
        return {
            "fehler": "",
            "leer": True,
            "zeilen": [],
            "anbieter": [],
            "legende": [],
            "achse": None,
            "achsentitel": titel,
        }
    fremde = sorted({a for _, karten in rohe for a in karten} - set(ANBIETER_FOLGE))
    anbieter = [*ANBIETER_FOLGE, *fremde]
    x0, x1 = BREIT["x0"], BREIT["x1"]
    ohne = {a for a in anbieter if all(a not in karten for _, karten in rohe)}
    zeilen = []
    for wahl, karten in rohe:
        punkte = [
            {
                "anbieter": a,
                "slug": slug_fuer(a),
                "wert": k["gesamt"],
                "anteil": _anteil(k["gesamt"], ach),
                "x": x0 + _anteil(k["gesamt"], ach) * (x1 - x0),
                "beleg": k.get("quelle_url") or "",
            }
            for a, k in karten.items()
        ]
        punkte.sort(key=lambda p: (p["wert"], p["anbieter"]))
        zeilen.append(
            {
                **wahl,
                "punkte": punkte,
                "luecken": [a for a in anbieter if a not in karten and a not in ohne],
            }
        )
    daten = {
        "fehler": "",
        "leer": False,
        "zeilen": zeilen,
        "anbieter": anbieter,
        "legende": _legende(anbieter, ohne),
        "achse": ach,
        "achsentitel": titel,
    }
    daten["svg_breit"] = _svg(daten, False)
    schmal = {
        **daten,
        "zeilen": [
            {
                **z,
                "punkte": [
                    {
                        **p,
                        "x": SCHMAL["x0"] + p["anteil"] * (SCHMAL["x1"] - SCHMAL["x0"]),
                    }
                    for p in z["punkte"]
                ],
            }
            for z in zeilen
        ],
    }
    daten["svg_schmal"] = _svg(schmal, True)
    return daten


def ergaenze(geraete: dict) -> dict:
    """Der Geräte-Kontext mit `preisposition`; ein Ausfall steht im Bild.

    Schlägt die Aufbereitung fehl, nennt `fehler` den Grund - die Seite
    zeigt ihn statt eines leeren Bildes, das „nichts gefunden“ vortäuschte."""
    try:
        daten = aufbereiten(geraete)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        log.exception("Preispositionierung nicht aufbereitbar")
        daten = {"fehler": f"{type(exc).__name__}: {exc}", "leer": False}
    return {**geraete, "preisposition": daten}
