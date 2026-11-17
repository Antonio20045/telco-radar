"""Die Punktgrafik der Herstellersicht: eine Zeile je Hersteller, ein Punkt je
Wettbewerber auf EINER gemeinsamen Achse.

Antonio, 17.11.2026: „der Graph Preisposition je Hersteller gefällt mir nicht,
wechsle die Art des Graphen, und zwar die, die wir bei Preisposition je Modell
hatten“. Das war die Punktgrafik aus `geraete_preisposition.py` (02.11.2026,
gelöscht am 13.11.2026 mit PR 102): Zeile, Punkt je Anbieter, dünne Linie vom
günstigsten zum teuersten Punkt, Beschriftung nur an den Enden. Dieselbe Form
trägt hier die Herstellersicht - die Modellgrafik bleibt gelöscht, es gibt
weiterhin nur EIN Preisbild auf der Seite.

GEZEICHNET WIRD KEINE NEUE ZAHL. Der Punkt eines Wettbewerbers sitzt auf dem
mittleren Abstand in Prozent, den `geraete_hersteller.zellen` rechnet - genau
der Wert, den die bisherige Tafel als Zahl zeigte. Null ist Vodafone (rote
Linie), links günstiger, rechts teurer. Ein Euro-Mittel je Hersteller wäre an
dieser Stelle unehrlich: die Wettbewerber führen verschieden viele Modelle
desselben Herstellers (o2 z. B. 1 von 3 Apple-Modellen), ein Mittelwert über
verschiedene Modellmengen ist nicht vergleichbar. Der Abstand ist je Modell
paarweise gerechnet und bleibt es.

Die Achse steht FEST: sie umfasst alle Werte, die ein wählbarer Zeitraum
annehmen kann (jeder Messtag, 7 und 30 Tage, der ganze Bereich, „aktuell“).
So verschiebt der Zeitraumwechsel nur die Punkte, nie das Raster.

Der Server zeichnet zwei Ausführungen (breit und schmal, das Stylesheet
schaltet um); `app.js` verschiebt beim Zeitraumwechsel nur noch die Punkte.
"""

from __future__ import annotations

import math
from html import escape

from . import geraete_zeitreihe_geometrie
from .anbieter_farben import slug_fuer, stil_fuer
from .geraete_hersteller_text import EIGEN, KLEIN, NBSP, prozent_text

MAX_TICKS = 9
TICK_SCHRITTE = (5, 10, 20, 25, 50, 100)
KEIN_PREIS = "kein Preis"

BREIT = {
    "w": 1000,
    "x0": 215,
    "x1": 952,
    "kopf": 28,
    "zeile": 62,
    "punkt_y": 30,
    "fehlt_y": 54,
    "name_y": 35,
    "r": 7.0,
}
SCHMAL = {
    "w": 358,
    "x0": 28,
    "x1": 330,
    "kopf": 30,
    "zeile": 68,
    "punkt_y": 40,
    "fehlt_y": 62,
    "name_y": 15,
    "r": 6.0,
}
MASSE = {"breit": BREIT, "schmal": SCHMAL}


def achse(werte: list[float]) -> dict | None:
    """Gemeinsame Prozentachse: Anfang, Ende, runde Teilstriche; Null liegt
    immer darin (sie ist Vodafone). `None`, wenn es keinen Wert gibt."""
    if not werte:
        return None
    tief, hoch = min([*werte, 0.0]), max([*werte, 0.0])
    schritt = TICK_SCHRITTE[-1]
    for kandidat in TICK_SCHRITTE:
        von = math.floor(tief / kandidat) * kandidat
        bis = math.ceil(hoch / kandidat) * kandidat
        if bis == von:
            bis = von + kandidat
        if (bis - von) / kandidat + 1 <= MAX_TICKS:
            schritt = kandidat
            break
    von = math.floor(tief / schritt) * schritt
    bis = math.ceil(hoch / schritt) * schritt
    if bis == von:
        bis = von + schritt
    ticks = [von + i * schritt for i in range(int((bis - von) // schritt) + 1)]
    return {"von": von, "bis": bis, "schritt": schritt, "ticks": ticks}


def x_fuer(wert: float, ach: dict, maß: dict) -> float:
    """Die Lage eines Prozentwertes auf der Achse (am Rand abgeschnitten, damit
    ein Ausreißer außerhalb der Achse nicht aus dem Bild läuft)."""
    anteil = (wert - ach["von"]) / (ach["bis"] - ach["von"])
    anteil = min(max(anteil, 0.0), 1.0)
    return maß["x0"] + anteil * (maß["x1"] - maß["x0"])


def tick_text(wert: float) -> str:
    """„+20 %“, „0“, „−20 %“ - dieselben Zeichen wie die Beschriftung."""
    return "0" if round(wert) == 0 else prozent_text(wert)


def _marke(anbieter: str, r: float) -> str:
    """Die Form des Punktes um (0,0): Kreis oder die Zusatzform des Anbieters."""
    form = geraete_zeitreihe_geometrie.form_pfad(stil_fuer(anbieter).marker, 0, 0, r)
    return form or f"<circle cx='0' cy='0' r='{r:.1f}'/>"


def titel(zelle: dict) -> str:
    """Der Tooltip eines Punktes: Anbieter, Zahl, Richtung, Modellzahl."""
    if zelle["leer"]:
        return f"{zelle['name']}: {KEIN_PREIS}"
    return f"{zelle['name']}: {zelle['text']} · {zelle['richtung']} · {zelle['n_text']}"


def _punkt(zelle: dict, x: float, y: float, r: float) -> str:
    klein = " gr-pp-duenn" if zelle.get("duenn") else ""
    sicht = "" if not zelle["leer"] else " hidden='hidden'"
    return (
        f"<g class='gr-pp-punkt gr-anb--{zelle['slug']}{klein}' "
        f"data-anbieter='{escape(zelle['name'])}' "
        f"transform='translate({x:.1f} {y:.1f})'{sicht}>"
        f"<title>{escape(titel(zelle))}</title>{_marke(zelle['name'], r)}</g>"
    )


def _zahl(klasse: str, text: str, x: float, y: float, anker: str) -> str:
    return (
        f"<text class='gr-pp-summe {klasse}' x='{x:.1f}' y='{y:.1f}' "
        f"text-anchor='{anker}'>{escape(text)}</text>"
    )


def fehlt_text(zellen: list[dict]) -> str:
    """„o2, congstar: kein Preis“ - die benannte Lücke unter der Zeile."""
    namen = [z["name"] for z in zellen if z["leer"]]
    return f"{', '.join(namen)}: {KEIN_PREIS}" if namen else ""


def _zeile(z: dict, ach: dict, maß: dict, oben: float) -> str:
    y = oben + maß["punkt_y"]
    mit = sorted(
        (c for c in z["zellen"] if not c["leer"]), key=lambda c: float(c["wert"])
    )
    alle = " gr-hm-zeile--alle" if z["gesamt"] else ""
    teile = [
        f"<g class='gr-hm-zeile{alle}' data-y='{y:.1f}' "
        f"data-hersteller='{escape(z['hersteller'])}'>",
        f"<text class='gr-pp-name' x='0' y='{oben + maß['name_y']:.1f}'>"
        f"{escape(z['name'])}</text>",
    ]
    xs = [x_fuer(float(c["wert"]), ach, maß) for c in mit]
    linie = (
        f"<line class='gr-pp-spanne' x1='{min(xs):.1f}' x2='{max(xs):.1f}' "
        f"y1='{y:.1f}' y2='{y:.1f}'/>"
        if len(xs) > 1
        else "<line class='gr-pp-spanne' x1='0' x2='0' y1='0' y2='0' hidden='hidden'/>"
    )
    teile.append(linie)
    tief = _zahl(
        "gr-hm-tief",
        mit[0]["text"] if len(mit) > 1 else "",
        (xs[0] - 14) if len(xs) > 1 else 0,
        y + 4,
        "end",
    )
    hoch = _zahl(
        "gr-hm-hoch",
        mit[-1]["text"] if mit else "",
        (xs[-1] + 14) if xs else 0,
        y + 4,
        "start",
    )
    teile += [tief, hoch]
    for c in z["zellen"]:
        x = x_fuer(float(c["wert"]), ach, maß) if not c["leer"] else maß["x0"]
        teile.append(_punkt(c, x, y, maß["r"]))
    teile.append(
        f"<text class='gr-pp-fehlt' x='{maß['x0']:.1f}' "
        f"y='{oben + maß['fehlt_y']:.1f}'>{escape(fehlt_text(z['zellen']))}</text>"
    )
    teile.append("</g>")
    return "".join(teile)


def svg(zeilen: list[dict], ach: dict, einheit: str, schmal: bool) -> str:
    """Das Bild in einer Ausführung; Werte und Achse kommen fertig herein."""
    maß = SCHMAL if schmal else BREIT
    hoehe = maß["kopf"] + maß["zeile"] * len(zeilen)
    teile = [
        f"<svg class='gr-pp-svg' viewBox='0 0 {maß['w']} {hoehe:.0f}' role='img' "
        f"aria-label='Preisposition je Hersteller: {escape(einheit)}' "
        "preserveAspectRatio='xMinYMin meet'>"
    ]
    for tick in ach["ticks"]:
        x = x_fuer(tick, ach, maß)
        null = round(tick) == 0
        teile.append(
            f"<line class='{'gr-pp-null' if null else 'gr-pp-raster'}' "
            f"x1='{x:.1f}' x2='{x:.1f}' y1='{maß['kopf'] - 8:.1f}' "
            f"y2='{hoehe:.0f}'/>"
            f"<text class='gr-pp-tick{' gr-pp-tick--null' if null else ''}' "
            f"x='{x:.1f}' y='{maß['kopf'] - 16:.1f}' text-anchor='middle'>"
            f"{escape(tick_text(tick))}</text>"
        )
    for i, z in enumerate(zeilen):
        teile.append(_zeile(z, ach, maß, maß["kopf"] + i * maß["zeile"]))
    teile.append("</svg>")
    return "".join(teile)


def richtungstext() -> tuple[str, str]:
    """Die zwei Hinweise links und rechts der Achse."""
    return ("← Vodafone günstiger", "Vodafone teurer →")


def legende(spalten: list[dict]) -> list[dict]:
    """Legende: erst Vodafone als Nulllinie, dann die Wettbewerber mit Form,
    zuletzt der Hinweis auf blasse Punkte (kleine Stichprobe)."""
    aus = [
        {
            "name": f"{EIGEN} ={NBSP}Nulllinie",
            "slug": slug_fuer(EIGEN),
            "null": True,
            "duenn": False,
            "marke": "",
        }
    ]
    aus += [
        {
            "name": w["legende"],
            "slug": w["slug"],
            "null": False,
            "duenn": False,
            "marke": _marke(w["name"], 5.5),
        }
        for w in spalten
    ]
    aus.append(
        {
            "name": f"weniger als {KLEIN} Modelle",
            "slug": "",
            "null": False,
            "duenn": True,
            "marke": "<circle cx='0' cy='0' r='5.5'/>",
        }
    )
    return aus


def zelle_werte(zeilen: list[dict]) -> list[float]:
    """Alle gezeichneten Werte - für die Achse."""
    return [float(c["wert"]) for z in zeilen for c in z["zellen"] if not c["leer"]]


def ergaenze(daten: dict, ach: dict | None) -> dict:
    """`daten` (aus `geraete_hersteller.aufbereiten`) um Achse, Legende und die
    zwei SVG erweitern. Die Achse kommt fertig herein, damit Bild und JSON
    dieselbe benutzen (Clean Code 1)."""
    if ach is None:
        return {**daten, "leer": True}
    links, rechts = richtungstext()
    return {
        **daten,
        "achse": ach,
        "legende": legende(daten["wettbewerber"]),
        "links": links,
        "rechts": rechts,
        "svg_breit": svg(daten["zeilen"], ach, daten["einheit"], False),
        "svg_schmal": svg(daten["zeilen"], ach, daten["einheit"], True),
    }


__all__ = [
    "achse",
    "ergaenze",
    "fehlt_text",
    "legende",
    "svg",
    "tick_text",
    "titel",
    "x_fuer",
]
