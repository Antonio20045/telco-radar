"""Preisposition je Hersteller als Liniendiagramm: eine Linie je Hersteller.

Antonio, 12.12.2026: aus den beiden oberen Preisbildern der Geräteseite wird
EIN Bild. Die Tafel „Hersteller x Wettbewerber" (eine Zahl je Zelle) und die
Punktwolke je Modell sind gefallen; was bleibt, ist die Frage, die beide
beantworten sollten: *wie steht Vodafone im Preis, und bewegt sich das?*

WAS DIE Y-ACHSE SAGT
  Der Abstand der Vodafone-Gesamtkosten zum Wettbewerb in Prozent
  (`geraete_hersteller.abstand`, unverändert). Je Messtag und Hersteller
  zuerst je Wettbewerber das Mittel über die Modelle des Herstellers, dann
  das Mittel über die Wettbewerber - so wiegt ein Wettbewerber mit vielen
  gemessenen Modellen die Linie nicht schwerer als einer mit wenigen.
  0 % ist die Nulllinie: Vodafone gleichauf.

VERGLEICHSTAGE - WARUM NICHT JEDER MESSTAG GEZEICHNET WIRD
  Am 08., 10. und 12.11.2026 lagen für Telekom und o2 keine gezählten
  24-Monats-Preise vor, für congstar und 1&1 schon. Ein Mittel über diesen
  Rest springt um 12 Prozentpunkte nach oben - nicht weil Vodafone teurer
  wurde, sondern weil die billigeren Vergleichspartner fehlten. Ein Tag
  zählt deshalb nur, wenn JEDER gezeigte Wettbewerber an ihm mindestens
  `KLEIN` gemessene Modelle hat. Die anderen Tage sind eine Lücke, kein
  Punkt: lieber Lücke als falscher Preis (Antonio).

Der Server zeichnet; `app.js` schaltet nur den Zeitraum um und zeichnet aus
demselben JSON nach derselben Regel (`vergleichstage`, `tageswert`).
"""

from __future__ import annotations

import html
import math
from datetime import date

from .anbieter_farben import hersteller_stil
from .geraete_hersteller_text import KLEIN, MINUS, NBSP, prozent_text
from .geraete_zeitreihe_geometrie import _x_marken, _xtick_x, _y_schritt, form_pfad

GESAMT_NAME = "Alle Hersteller"

BREIT_W, BREIT_H = 1136, 430
SCHMAL_W, SCHMAL_H = 358, 320
FREIRAUM_ANTEIL = 0.14
PUNKT_R = 3.5


def _tag_monat(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(d)}.{int(m)}."


MINDEST_MODELLE = KLEIN
"""Wie viele gemessene Modelle ein Wettbewerber an einem Tag mindestens tragen
muss, damit der Tag ein Vergleichstag ist - dieselbe Schwelle, ab der eine
Stichprobe nicht mehr „klein" heisst."""


def vergleichstage(
    rechnung: dict, spalten: list[int], mindest: int | None = None
) -> list[str]:
    """Die Messtage, an denen JEDER gezeigte Wettbewerber `mindest` Modelle trägt.

    `spalten` sind die Indizes der gezeigten Wettbewerber in
    `geraete_hersteller.WETTBEWERBER`. Ohne Spalten gibt es keinen
    Vergleichstag - eine leere Liste, nie eine stillschweigende Lockerung."""
    mindest = MINDEST_MODELLE if mindest is None else mindest
    if not spalten:
        return []
    tage = []
    for tag in rechnung["tage"]:
        zeilen = rechnung["pct"][tag]
        if all(sum(1 for z in zeilen if z[j] is not None) >= mindest for j in spalten):
            tage.append(tag)
    return tage


def tageswert(
    rechnung: dict, tag: str, hersteller: str | None, spalten: list[int]
) -> tuple[float | None, int]:
    """(Prozentwert, Zahl der eingegangenen Modellwerte) für einen Messtag.

    `hersteller=None` ist „Alle Hersteller". Zwei Stufen: je Wettbewerber das
    Mittel über die Modelle, dann das Mittel über die Wettbewerber mit Wert.
    Ohne jeden Wert bleibt es `None` - nie 0 (Clean Code 3)."""
    zeilen = rechnung["pct"][tag]
    namen = [m["hersteller"] for m in rechnung["modelle"]]
    je_spalte: list[float] = []
    n = 0
    for j in spalten:
        werte = [
            zeilen[i][j]
            for i in range(len(namen))
            if zeilen[i][j] is not None
            and (hersteller is None or namen[i] == hersteller)
        ]
        if werte:
            je_spalte.append(sum(werte) / len(werte))
            n += len(werte)
    if not je_spalte:
        return None, 0
    return sum(je_spalte) / len(je_spalte), n


def reihen(
    rechnung: dict, spalten: list[int], tage: list[str], ordnung: list[str]
) -> list[dict]:
    """Je Hersteller (`ordnung`, die Reihenfolge der Seite) und zuletzt „Alle
    Hersteller" eine Reihe mit Stil und Punkten; ein Hersteller ohne einen
    einzigen Punkt fällt weg, statt als leere Legendenzeile zu stehen."""
    aus: list[dict] = []
    for i, name in enumerate([*ordnung, None]):
        gesamt = name is None
        punkte: list[dict] = []
        letzter = 0.0
        for tag in tage:
            wert, n = tageswert(rechnung, tag, name, spalten)
            if wert is not None:
                letzter = round(wert, 2)
                punkte.append({"tag": tag, "wert": letzter, "n": n})
        if not punkte:
            continue
        stil = hersteller_stil(None if gesamt else i)
        aus.append(
            {
                "hersteller": name or "",
                "name": GESAMT_NAME if gesamt else name,
                "gesamt": gesamt,
                "farbe": stil.farbe,
                "muster": stil.muster,
                "breite": stil.breite,
                "marker": stil.marker,
                "punkte": punkte,
                "letzter": prozent_text(letzter),
            }
        )
    return aus


def _spanne(reihen_: list[dict]) -> tuple[float, float]:
    """Y-Grenzen mit Luft, 0 % immer im Bild (die Nulllinie ist die Aussage)."""
    werte = [p["wert"] for r in reihen_ for p in r["punkte"]] or [0.0]
    ymin, ymax = min(min(werte), 0.0), max(max(werte), 0.0)
    luft = (ymax - ymin) * FREIRAUM_ANTEIL or 1.0
    return ymin - luft, ymax + luft


def _marke(marker: str, x: float, y: float) -> str:
    pfad = form_pfad(marker, x, y, PUNKT_R)
    if pfad:
        return pfad
    return f"<circle cx='{x:.1f}' cy='{y:.1f}' r='{PUNKT_R:.1f}'/>"


def svg(
    reihen_: list[dict], tage: list[str], breit: bool = True, titel: str = ""
) -> str:
    """Das Bild - fertiges SVG, ohne JavaScript lesbar.

    X ist das echte Datum (gleiche Distanzregel wie die TCO-Zeitreihe), Y der
    Prozentabstand. Keine Beschriftung dreht sich, keine Schrift unter 12 px;
    am Ende jeder Linie steht ihr letzter Wert. `titel` ist die
    Achsenbeschriftung - sie steht IM Bild, damit um das Bild herum kein Text
    steht (Antonio, 12.12.2026)."""
    if not reihen_ or not tage:
        return ""
    g = geometrie()
    w, h = g["breit"] if breit else g["schmal"]
    links, oben, unten = g["links"], g["oben"], g["unten"]
    rechts = g["rechts_breit"] if breit else g["rechts_schmal"]
    pw, ph = w - links - rechts, h - oben - unten
    t0, t1 = date.fromisoformat(tage[0]), date.fromisoformat(tage[-1])

    def x_v(iso: str) -> float:
        return _xtick_x(iso, t0, t1, links, pw, tage)

    y0, y1 = _spanne(reihen_)

    def y_v(wert: float) -> float:
        return oben + (1 - (wert - y0) / (y1 - y0)) * ph

    teile = [
        f"<svg class='gr-hl gr-hl--{'breit' if breit else 'schmal'}' "
        f"viewBox='0 0 {w} {h}' role='img' aria-label='Abstand der "
        f"Vodafone-Gesamtkosten zum Wettbewerb in Prozent je Messtag und "
        f"Hersteller: {html.escape(', '.join(r['name'] for r in reihen_))}'>"
    ]
    if titel:
        teile.append(
            f"<text class='gr-hl-titel' x='{links - 8}' y='16'>"
            f"{html.escape(titel)}</text>"
        )
    schritt = _y_schritt(y0, y1)
    wert = math.ceil(y0 / schritt) * schritt
    while wert <= y1 + 0.01:
        y = y_v(wert)
        null = abs(wert) < 0.001
        teile.append(
            f"<line class='gr-hl-raster{' gr-hl-null' if null else ''}' "
            f"x1='{links}' y1='{y:.1f}' x2='{w - rechts}' y2='{y:.1f}'/>"
            f"<text class='gr-hl-achse' x='{links - 8}' y='{y + 4:.1f}' "
            f"text-anchor='end'>{_achsentext(wert)}</text>"
        )
        wert += schritt
    beschriftet = _x_marken(tage, x_v, breit)
    for tag in tage:
        x = x_v(tag)
        if tag in beschriftet:
            teile.append(
                f"<text class='gr-hl-xtick' x='{x:.1f}' y='{h - unten + 22}' "
                f"text-anchor='middle'>{_tag_monat(tag)}</text>"
            )
    for r in reihen_:
        punkte = [(x_v(p["tag"]), y_v(p["wert"]), p["wert"]) for p in r["punkte"]]
        klasse = "gr-hl-linie" + (" gr-hl-linie--gesamt" if r["gesamt"] else "")
        stil = (
            f"stroke:{r['farbe']};stroke-width:{r['breite']};"
            f"stroke-dasharray:{r['muster']}"
        )
        if len(punkte) > 1:
            pfad = " ".join(
                ("M" if i == 0 else "L") + f"{x:.1f} {y:.1f}"
                for i, (x, y, _w) in enumerate(punkte)
            )
            teile.append(f"<path class='{klasse}' style='{stil}' d='{pfad}'/>")
        marken = "".join(_marke(r["marker"], x, y) for x, y, _w in punkte)
        teile.append(
            f"<g class='gr-hl-punkte' style='fill:{r['farbe']};"
            f"stroke:{r['farbe']}'>{marken}</g>"
        )
        if breit:
            x, y, _w = punkte[-1]
            teile.append(
                f"<text class='gr-hl-ende' x='{x + 10:.1f}' y='{y + 5:.1f}' "
                f"style='fill:{r['farbe']}'>{html.escape(r['letzter'])}</text>"
            )
    teile.append("</svg>")
    return "".join(teile)


def stile(ordnung: list[str]) -> list[dict]:
    """Stil und Name jeder möglichen Reihe - auch der gerade punktlosen.

    `app.js` zeichnet damit jeden Zeitraum, ohne die Palette ein zweites Mal
    zu führen: die Farben kommen auch im Browser aus `anbieter_farben`."""
    aus = []
    for i, name in enumerate([*ordnung, None]):
        stil = hersteller_stil(None if name is None else i)
        aus.append(
            {
                "hersteller": name or "",
                "name": GESAMT_NAME if name is None else name,
                "gesamt": name is None,
                "farbe": stil.farbe,
                "muster": stil.muster,
                "breite": stil.breite,
                "marker": stil.marker,
            }
        )
    return aus


def geometrie() -> dict:
    """Die Maße des Bildes - EINE Quelle für Server und `app.js`."""
    return {
        "breit": [BREIT_W, BREIT_H],
        "schmal": [SCHMAL_W, SCHMAL_H],
        "links": 54,
        "rechts_breit": 96,
        "rechts_schmal": 54,
        "oben": 34,
        "unten": 44,
        "r": PUNKT_R,
        "luft": FREIRAUM_ANTEIL,
    }


def _achsentext(wert: float) -> str:
    r = int(round(wert))
    vor = "+" if r > 0 else MINUS if r < 0 else ""
    return f"{vor}{abs(r)}{NBSP}%"


def vergleichstag_satz() -> str:
    """Die Methodik-Zeile auf `geraete-quellen.html#methodik`: warum nicht jeder
    Messtag im Bild steht. Auf der Geräteseite selbst steht sie nicht."""
    return (
        "Eine Linie je Hersteller: der Abstand der Vodafone-Gesamtkosten zum "
        "Wettbewerb in Prozent, je Messtag erst je Wettbewerber über dessen "
        "Modelle gemittelt, dann über die Wettbewerber. Gezeichnet werden nur "
        f"Vergleichstage - Tage, an denen jeder gezeigte Wettbewerber "
        f"mindestens {MINDEST_MODELLE} gemessene Modelle hat; sonst wäre die "
        "Bewegung der Linie nur ein Wechsel der Vergleichspartner."
    )


def achsentitel(laufzeit: int, kurz: bool = False) -> str:
    """Die EINE Zeile im Bild: was die Y-Achse misst. Keine Erklärung, eine
    Achsenbeschriftung - ohne sie wäre die Skala unbenannt.

    `kurz` ist die Fassung für das schmale Bild: auf 358 px lief die lange
    rechts aus dem Bild heraus („… · Gesamtkost"), und eine abgeschnittene
    Beschriftung ist schlimmer als eine knappe."""
    if kurz:
        return f"Vodafone zum Wettbewerb · {laufzeit}{NBSP}Mon. · in{NBSP}%"
    return (
        f"Vodafone gegenüber dem Wettbewerb · Gesamtkosten {laufzeit}{NBSP}Monate"
        f" · in{NBSP}%"
    )
