"""Geometrie der TCO-Zeitreihe: runde Y-Achse, X-Marken, Stufenlinie, Marker.

Aus `geraete_zeitreihe` ausgelagert; dort steht die Aufbereitung der Daten und das
Zusammensetzen des SVG. Rein rechnerisch: nichts wird interpoliert.
"""

from __future__ import annotations

import math
from datetime import date

MIN_XTICK_ABSTAND = 34

LUECKE_TAGE_SCHWELLE = 10


def _nice_step(spanne: float) -> float:
    if spanne <= 0:
        return 1.0
    potenz = 10 ** math.floor(math.log10(spanne))
    n = spanne / potenz
    stufe = 1 if n <= 1 else 2 if n <= 2 else 2.5 if n <= 2.5 else 5 if n <= 5 else 10
    return stufe * potenz


_NICE_VIELFACH = (1, 2, 2.5, 5, 10)


def _y_schritt(y0: float, y1: float) -> float:
    """Der Y-Achsen-Schritt mit 4-5 RUNDEN Werten.

    `_nice_step((y1-y0)/4)` allein kann kollabieren: bei y0=752/y1=1248
    (Spanne 496) rundet Spanne/4=124 auf die naechste Stufe 200 - und von
    752 bis 1248 passen dann nur DREI Vielfache von 200 (800/1000/1200),
    nicht vier bis fuenf. Diese Funktion sucht stattdessen unter allen
    runden Schritten mehrerer Dekaden denjenigen, dessen TICKZAHL wirklich
    in [4, 5] faellt (bei Gleichstand der naechste an 5 dran) - nur wenn
    keiner der runden Schritte das trifft (seltene Randspannen), faellt
    sie auf die Zahl zurueck, die der Tickzahl 4,5 am naechsten kommt."""
    spanne = y1 - y0
    if spanne <= 0:
        return max(abs(y1), 1.0)
    basis = spanne / 4
    basis_potenz = 10 ** math.floor(math.log10(basis))
    kandidaten = sorted(
        {
            round(m * basis_potenz * (10**dek), 8)
            for dek in range(-3, 4)
            for m in _NICE_VIELFACH
            if m * basis_potenz * (10**dek) > 0
        }
    )
    beste_rang, bester_schritt = None, None
    for schritt in kandidaten:
        erster = math.ceil(y0 / schritt) * schritt
        n, wert = 0, erster
        while wert <= y1 + 0.01 and n < 60:
            n += 1
            wert += schritt
        if n < 2:
            continue
        rang = (0 if 4 <= n <= 5 else 1, abs(n - 4.5))
        if beste_rang is None or rang < beste_rang:
            beste_rang, bester_schritt = rang, schritt
    return bester_schritt if bester_schritt else _nice_step(spanne / 4)


def _xtick_x(
    iso: str, t0: date, t1: date, links: float, breite: float, tage: list[str]
) -> float:
    if t1 == t0:
        return links + breite / 2
    tag = date.fromisoformat(iso)
    return links + (tag - t0).days / max(1, (t1 - t0).days) * breite


def _x_marken(
    tage: list[str], x_v, mindestabstand: float = MIN_XTICK_ABSTAND
) -> set[str]:
    """Welche Messtage eine X-Achsen-BESCHRIFTUNG bekommen (`MIN_XTICK_ABSTAND`).

    Gierig von links: der erste Tag ist immer dabei, jeder weitere nur,
    wenn er `mindestabstand` Einheiten vom zuletzt beschrifteten Tag
    entfernt liegt; der letzte Tag ersetzt noetigenfalls den zuletzt
    gewaehlten, statt zusaetzlich zu kollidieren - eine Achse ohne
    Enddatum sagt nicht, bis wann sie reicht. Die RASTERLINIE bekommt
    trotzdem JEDER Messtag (siehe `_svg`) - nur die Textmarke wird
    ausgeduennt."""
    if len(tage) <= 1:
        return set(tage)
    behalten = [tage[0]]
    letzte_x = x_v(tage[0])
    for tag in tage[1:-1]:
        x = x_v(tag)
        if x - letzte_x >= mindestabstand:
            behalten.append(tag)
            letzte_x = x
    letzter = tage[-1]
    if x_v(letzter) - letzte_x < mindestabstand and len(behalten) > 1:
        behalten[-1] = letzter
    else:
        behalten.append(letzter)
    return set(behalten)


def _stufenpfad(punkte: list[tuple[float, float, float]]) -> str:
    """Der Pfad einer STUFENLINIE (»step-after«) durch die gegebenen
    (x, y, wert)-Punkte: waagerecht zum naechsten X, dann senkrecht zu
    seinem Y. Ein Preis gilt vom Messtag an - er GLEITET nicht zum
    naechsten, er SPRINGT dort, genau am naechsten Messtag."""
    if not punkte:
        return ""
    teile = [f"M{punkte[0][0]:.1f} {punkte[0][1]:.1f}"]
    for i in range(1, len(punkte)):
        y0 = punkte[i - 1][1]
        x1, y1, _wert = punkte[i]
        teile.append(f"L{x1:.1f} {y0:.1f}")
        if y1 != y0:
            teile.append(f"L{x1:.1f} {y1:.1f}")
    return " ".join(teile)


def _linien_laeufe(
    punkte: list[tuple[float, float, float]],
    tage: list[str],
    schwelle_tage: int = LUECKE_TAGE_SCHWELLE,
) -> list[tuple[list[tuple[float, float, float]], bool]]:
    """Zerlegt eine Punktreihe in (Teilstrecke, ist_luecke)-Laeufe.

    `tage` sind die ECHTEN Messtage (isoformat) parallel zu `punkte` -
    Grundlage der Tagesdifferenz. Ueberschreitet der Abstand zweier
    aufeinanderfolgender Punkte `schwelle_tage`, ist die Verbindung
    ZWISCHEN ihnen eine eigene, gepunktete Zweipunkt-Teilstrecke
    (`ist_luecke=True`); alle anderen aufeinanderfolgenden Punkte ohne
    grosse Luecke bilden EINE durchgezogene Teilstrecke. So bleibt jeder
    Lauf entweder ganz durchgezogen oder (bei genau zwei Punkten) ganz
    gepunktet - nie beides im selben `<path>`, dessen `stroke-dasharray`
    nur EIN Muster kennt."""
    if len(punkte) < 2:
        return [(punkte, False)] if punkte else []
    laeufe: list[tuple[list[tuple[float, float, float]], bool]] = []
    lauf: list[tuple[float, float, float]] = [punkte[0]]
    for i in range(1, len(punkte)):
        tag_davor = date.fromisoformat(tage[i - 1])
        tag = date.fromisoformat(tage[i])
        if (tag - tag_davor).days > schwelle_tage:
            if len(lauf) > 1:
                laeufe.append((lauf, False))
            laeufe.append(([punkte[i - 1], punkte[i]], True))
            lauf = [punkte[i]]
        else:
            lauf.append(punkte[i])
    if len(lauf) > 1:
        laeufe.append((lauf, False))
    return laeufe


def _form_pfad(marker: str, x: float, y: float, r: float) -> str | None:
    """Die Zusatzform eines Markers - ODER `None` fuer den Kreis (der
    Punkt TRAEGT die Form schon: `<circle class='gr-zr-punkt'>`) und fuer
    unbekannte Formen. Gezeichnet als OFFENER Umriss (fill='none') UM den
    bestehenden Kreis - keine Kreis-Selektoren aus Tests und `app.js`
    aendern sich damit (D1 hatte das deshalb offen gelassen); die Form
    ist eine reine Zusatzauskunft fuer Farbfehlsicht und Schwarzweiss."""
    if marker in ("kreis", "") or marker not in (
        "quadrat",
        "dreieck",
        "dreieck--runter",
        "raute",
        "sechseck",
        "ring",
        "kreuz",
    ):
        return None
    if marker == "quadrat":
        s = r * 0.86
        return (
            f"<rect x='{x - s:.1f}' y='{y - s:.1f}' width='{2 * s:.1f}' "
            f"height='{2 * s:.1f}'/>"
        )
    if marker == "raute":
        s = r * 1.15
        pkte = (
            f"{x:.1f},{y - s:.1f} {x + s:.1f},{y:.1f} "
            f"{x:.1f},{y + s:.1f} {x - s:.1f},{y:.1f}"
        )
        return f"<polygon points='{pkte}'/>"
    if marker in ("dreieck", "dreieck--runter"):
        s = r * 1.2
        if marker == "dreieck":
            pkte = (
                f"{x:.1f},{y - s:.1f} {x + s:.1f},{y + s * 0.85:.1f} "
                f"{x - s:.1f},{y + s * 0.85:.1f}"
            )
        else:
            pkte = (
                f"{x:.1f},{y + s:.1f} {x + s:.1f},{y - s * 0.85:.1f} "
                f"{x - s:.1f},{y - s * 0.85:.1f}"
            )
        return f"<polygon points='{pkte}'/>"
    if marker == "sechseck":
        pkte = " ".join(
            f"{x + r * 1.1 * math.cos(math.radians(60 * i - 30)):.1f},"
            f"{y + r * 1.1 * math.sin(math.radians(60 * i - 30)):.1f}"
            for i in range(6)
        )
        return f"<polygon points='{pkte}'/>"
    if marker == "ring":
        return f"<circle cx='{x:.1f}' cy='{y:.1f}' r='{r * 1.4:.1f}'/>"
    if marker == "kreuz":
        s = r * 1.15
        return (
            f"<path d='M{x - s:.1f} {y:.1f}L{x + s:.1f} {y:.1f} "
            f"M{x:.1f} {y - s:.1f}L{x:.1f} {y + s:.1f}'/>"
        )
    return None
