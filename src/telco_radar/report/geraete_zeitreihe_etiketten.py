"""Namensetiketten am rechten Rand der Zeitreihe: Name, Zeitraum, Abrufdatum.

Aus `geraete_zeitreihe` ausgelagert (Issue 125). Ein langer Name mit Netz
(„Saturn/MediaMarkt · Telekom-Netz“) steht zweizeilig und kleiner, schmal mit
breiterem Rand. Etiketten rücken nie näher als ihre eigene Höhe zusammen; reicht
das Bild dafür nicht, wird es höher (`mindesthoehe`). Etiketten rücken nach unten
wie bisher (`_gestapelt`); erst wenn dabei eines unter die Linie des nächsten
Anbieters oder aus dem Bild geriete, stehen sie zentriert (`_platziere`).
"""

from __future__ import annotations

from .anbieter_farben import stil_fuer
from .geraete_rechenweg import _datum_kurz, _esc
from .geraete_zeitreihe_legende import NAMEN_TRENNER, _mon_kurz, zweizeilig

ENDLABEL_RAND = 6
RAND_RECHTS = {True: 158, False: 96}
RAND_RECHTS_ZWEIZEILIG = {True: 158, False: 120}
"""Rechter Rand (breit/schmal); schmal trägt der Händlername 11 px erst ab 120."""
ABSTAND = {True: 46, False: 44}
ZEITRAUM_ZEILE = 13
ZWEITE_ZEILE = {True: 14, False: 12}
SCHRIFT_ZWEIZEILIG = {True: 13, False: 11}
"""Schrift (px) und Zeilenabstand eines zweizeiligen Namens; die übrigen 15 px."""
ETIKETT_OBEN = 8
ETIKETT_UNTEN = 21
"""Ein Etikett reicht von ty - 8 (Oberkante Name) bis ty + 21 (Datum mit Unterlänge)."""


def rand_rechts(anbieter: list[str], breit: bool) -> int:
    """Der rechte Rand des Bildes; breiter nur, wenn ein langer Name darin steht."""
    if any(zweizeilig(a) for a in anbieter):
        return RAND_RECHTS_ZWEIZEILIG[breit]
    return RAND_RECHTS[breit]


def _zweite(name: str, breit: bool) -> int:
    return ZWEITE_ZEILE[breit] if zweizeilig(name) else 0


def _mon(a: str, mon_je: dict, mehrere: bool) -> str:
    return _mon_kurz(mon_je.get(a) or []) if mehrere else ""


def _abstaende(folge: list[str], breit: bool, mon_je: dict, mehrere: bool) -> list:
    """Mindestabstand jedes Etiketts zum vorigen (von oben nach unten).

    Die Zeitraumzeile zählt, wenn eines der beiden sie trägt, die zweite
    Namenszeile, wenn das vorige sie trägt - dessen Zeilen liegen dazwischen."""
    abstaende, davor = [], None
    for a in folge:
        mon = _mon(a, mon_je, mehrere) or (
            davor is not None and _mon(davor, mon_je, mehrere)
        )
        zweite = _zweite(davor, breit) if davor is not None else 0
        abstaende.append(ABSTAND[breit] + (ZEITRAUM_ZEILE if mon else 0) + zweite)
        davor = a
    return abstaende


def _unten(a: str, breit: bool, mon_je: dict, mehrere: bool) -> int:
    mon = ZEITRAUM_ZEILE if _mon(a, mon_je, mehrere) else 0
    return ETIKETT_UNTEN + _zweite(a, breit) + mon


def mindesthoehe(
    serien: dict, anbieter: list[str], breit: bool, mon_je: dict, mehrere: bool
) -> int:
    """Die Bildhöhe, in die alle Etiketten untereinander passen.

    Die Folge von oben nach unten ist die der Endwerte, absteigend - dieselbe,
    die `_svg` über die Y-Koordinate sortiert, aber ohne die Höhe zu kennen."""
    if not anbieter:
        return 0
    folge = sorted(anbieter, key=lambda a: -serien[a][-1][1])
    stapel = sum(_abstaende(folge, breit, mon_je, mehrere)[1:])
    return ETIKETT_OBEN + stapel + _unten(folge[-1], breit, mon_je, mehrere)


def _gestapelt(ideal: list, abstaende: list) -> list:
    """Jedes Etikett an seiner Kurve oder, wenn das vorige im Weg ist, darunter."""
    tys, letzte = [], -99.0
    for y, abstand in zip(ideal, abstaende, strict=True):
        letzte = max(y, letzte + abstand)
        tys.append(letzte)
    return tys


def _irrefuehrend(tys: list, ideal: list, unten: float) -> bool:
    """Steht ein Etikett tiefer als die Linie des nächsten Anbieters oder unten
    aus dem Bild? Dann liest man es (gleiches Händlergrau!) als fremde Linie."""
    if tys and tys[-1] > unten:
        return True
    return any(ty > y for ty, y in zip(tys, ideal[1:], strict=False))


def _platziere(ideal: list, abstaende: list, oben: float, unten: float) -> list:
    """Höhe je Etikett: so nah an seiner Kurve wie möglich, nie enger als `abstaende`.

    Ein Etikett ohne Nachbarn im Weg steht genau an seiner Kurve. Stoßen zwei
    zusammen, bilden sie eine Gruppe, die um die Kurven ihrer Glieder zentriert
    steht (mittlere Verschiebung null) statt nur nach unten zu rücken - sonst
    stünde ein graues Händleretikett neben der Linie eines anderen Händlers.
    Die Gruppe bleibt zwischen `oben` und `unten` (`mindesthoehe` sorgt für Platz)."""
    versatz = [0.0]
    for abstand in abstaende[1:]:
        versatz.append(versatz[-1] + abstand)
    gruppen: list[list[int]] = []
    kopf: list[float] = []

    def lage(glieder: list[int]) -> float:
        mitte = sum(ideal[i] - versatz[i] for i in glieder) / len(glieder)
        grenze = unten - (versatz[glieder[-1]] - versatz[glieder[0]])
        return max(oben, min(mitte + versatz[glieder[0]], grenze))

    for i in range(len(ideal)):
        gruppen.append([i])
        kopf.append(lage([i]))
        while len(gruppen) > 1:
            vorn = gruppen[-2]
            ende_vorn = kopf[-2] + versatz[vorn[-1]] - versatz[vorn[0]]
            if kopf[-1] - ende_vorn >= abstaende[gruppen[-1][0]]:
                break
            gruppen[-2:] = [vorn + gruppen[-1]]
            kopf[-2:] = [lage(gruppen[-1])]
    return [
        k + versatz[i] - versatz[g[0]]
        for g, k in zip(gruppen, kopf, strict=True)
        for i in g
    ]


def _name_html(a: str, lx: float, breit: bool, mit_pfeil: bool) -> str:
    """Der Name; ein langer bricht vor dem Trenner um (tspan mit Nullbreite)."""
    if zweizeilig(a):
        vorn, hinten = a.split(NAMEN_TRENNER, 1)
        text = (
            f"{_esc(vorn)}<tspan class='gr-zr-umbruch' x='{lx:.1f}' "
            f"dy='{ZWEITE_ZEILE[breit]}'>&#x200b;</tspan>"
            f"{_esc(NAMEN_TRENNER + hinten)}"
        )
    else:
        text = _esc(a)
    return text + ("<tspan class='gr-zr-pfeil'> ↗</tspan>" if mit_pfeil else "")


def namensetiketten(
    enden: list,
    breit: bool,
    w: int,
    h: int,
    beleg_je: dict,
    mon_je: dict,
    mehrere: bool,
) -> list[str]:
    """Je Kurvenende (x, y, Anbieter), von oben nach unten sortiert, ein Etikett."""
    folge = [a for _x, _y, a in enden]
    abstaende = _abstaende(folge, breit, mon_je, mehrere)
    ideal = [y for _x, y, _a in enden]
    unten = h - _unten(folge[-1], breit, mon_je, mehrere) if folge else h
    tys = _gestapelt(ideal, abstaende)
    if any(zweizeilig(a) for a in folge) and _irrefuehrend(tys, ideal, unten):
        tys = _platziere(ideal, abstaende, ETIKETT_OBEN, unten)
    teile: list[str] = []
    lx = w - ENDLABEL_RAND
    for a, ty in zip(folge, tys, strict=True):
        farbe = stil_fuer(a).farbe
        mon_text = _mon(a, mon_je, mehrere)
        url, datum = beleg_je.get(a, ("", ""))
        zeilen = (
            f" data-zeilen='2' style='font-size:{SCHRIFT_ZWEIZEILIG[breit]}px'"
            if zweizeilig(a)
            else ""
        )
        kopf = (
            f"<text class='gr-zr-name' x='{lx:.1f}' y='{ty + 4:.1f}' "
            f"text-anchor='end' fill='{farbe}'{zeilen}>"
        )
        if url:
            teile.append(
                f"<a class='gr-zr-link' href='{_esc(url)}' "
                f"target='_blank' rel='noopener' aria-label='Beleg bei "
                f"{_esc(a)} öffnen'>{kopf}{_name_html(a, lx, breit, True)}</text></a>"
            )
        else:
            teile.append(f"{kopf}{_name_html(a, lx, breit, False)}</text>")
        unter = ty + _zweite(a, breit)
        mon = ZEITRAUM_ZEILE if mon_text else 0
        if mon_text:
            teile.append(
                f"<text class='gr-zr-datum gr-zr-mon' "
                f"x='{lx:.1f}' y='{unter + 17:.1f}' "
                f"text-anchor='end'>{_esc(mon_text)}</text>"
            )
        if datum:
            teile.append(
                f"<text class='gr-zr-datum' x='{lx:.1f}' "
                f"y='{unter + 17 + mon:.1f}' "
                f"text-anchor='end'>{_datum_kurz(datum)}</text>"
            )
    return teile
