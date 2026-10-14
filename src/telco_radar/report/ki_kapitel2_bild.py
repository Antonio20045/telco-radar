"""Die Linienzeichnung von Kapitel 2 der KI-Seite: „Was ist eigentlich KI?“.

Gleiche Machart wie Kapitel 1 (``ki_kapitel_bild``): eine 600 Einheiten
breite Zeichnung, durch die der rote Punkt fährt, dieselben Bausteine und
Klassen, also dieselbe Bewegung aus ``app.js``. Die Stationen: eine starre
Regel sortiert vier Mails und irrt zweimal, eine Ebene mit zwölf
Beispielen, deren Trennlinie sich nach 2, 6 und 12 Beispielen dreht, eine
neue Mail landet auf der richtigen Seite, ein Damebrett für Samuel 1959.
Die Punkte sind ein Lehrbeispiel (u = Werbung im Text, v = Absender
unbekannt, je 0 bis 1), keine Messung; ``seite_von()`` rechnet, auf welcher
Seite einer Linie ein Punkt liegt.
"""

from __future__ import annotations

from .ki_kapitel_bild import (
    MITTE,
    W,
    _e,
    _linie,
    _pille,
    _r,
    _t,
    _zahnrad,
    pillen_breite,
)

LINSE = 380
REGEL = "Enthält „klick“?"
MAILS = (
    ("Klick hier: Gewinn!", 190, 480, True),
    ("Rechnung Oktober", 410, 480, False),
    ("Gratis-Handy wartet", 120, 560, True),
    ("Klick-Zahlen Kampagne", 488, 560, False),
)
REGEL_Y = 760
FACH_Y = 910
FAECHER = (("Spam", 150), ("Posteingang", 450))
EBENE = (90, 510, 1690, 2190)
LINIEN = (
    ((0.55, 1.0), (0.45, 0.0), 2),
    ((0.25, 1.0), (0.85, 0.0), 6),
    ((0.1, 1.0), (1.0, 0.25), 12),
)
BEISPIELE = (
    (0.78, 0.78, True),
    (0.22, 0.25, False),
    (0.62, 0.22, False),
    (0.4, 0.9, True),
    (0.85, 0.55, True),
    (0.15, 0.6, False),
    (0.22, 0.95, True),
    (0.8, 0.3, False),
    (0.6, 0.7, True),
    (0.5, 0.45, False),
    (0.1, 0.7, False),
    (0.92, 0.85, True),
)
NEU = ("Gratis-Handy wartet", 0.7, 0.82)
NEU_Y = 2540
KLEIN = (180, 420, 2640, 2880)
BRETT = (180, 3180, 240)
ENDE = 4340
HOEHE = ENDE + 60


def seite_von(linie, u: float, v: float) -> bool:
    """True, wenn (u, v) auf der Spam-Seite der Linie liegt (rechts oben)."""
    (u0, v0), (u1, v1) = linie
    return (u1 - u0) * (v - v0) - (v1 - v0) * (u - u0) > 0


def _punkt(rahmen, u: float, v: float) -> tuple[float, float]:
    x0, x1, y0, y1 = rahmen
    return x0 + (x1 - x0) * u, y1 - (y1 - y0) * v


def _regel() -> tuple[list, list]:
    hinten = [
        _linie(f"M -600 {LINSE} L 1200 {LINSE}", LINSE - 1, LINSE + 1),
        _e("circle", klasse="ki-k1-flaeche", cx=MITTE, cy=LINSE, r=22),
    ]
    vorn = []
    for wort, x, y, _ in MAILS:
        oben = REGEL_Y - 35
        a = _r(x + (1 if x < MITTE else -1) * (pillen_breite(wort, 17) / 2 - 40))
        d = f"M {a} {y + 18} C {a} {y + 130} {MITTE} {oben - 95} {MITTE} {oben}"
        hinten.append(_linie(d, y + 18, REGEL_Y - 35, dicke=1))
        vorn.append(_pille(x, y, wort, 17))
    hinten += [
        _e(
            "rect",
            klasse="ki-k1-flaeche",
            x=160,
            y=REGEL_Y - 35,
            width=280,
            height=70,
            rx=6,
        ),
        _zahnrad(480, REGEL_Y, 16, 8, 1),
    ]
    vorn.append(_t(MITTE, REGEL_Y + 7, REGEL, "ki-k1-wort", 19, data_y=REGEL_Y))
    for (name, x), ja in zip(FAECHER, ("ja", "nein"), strict=True):
        r, f = REGEL_Y, FACH_Y
        d = f"M {MITTE} {r + 35} C {MITTE} {r + 90} {x} {f - 70} {x} {f - 6}"
        hinten.append(_linie(d, REGEL_Y + 35, FACH_Y))
        hinten.append(
            _linie(
                f"M {x - 100} {f} L {x - 88} {f + 55} "
                f"L {x + 88} {f + 55} L {x + 100} {f}",
                FACH_Y,
                FACH_Y + 55,
            )
        )
        vorn.append(_t(x, FACH_Y + 40, name, "ki-k1-wort", 17, data_y=FACH_Y))
        vorn.append(
            _t(x + (40 if x < MITTE else -40), REGEL_Y + 65, ja, "ki-k1-wort", 14)
        )
    fach = {True: [], False: []}
    for wort, _, _, spam in MAILS:
        fach["klick" in wort.lower()].append((wort, spam))
    for (_, x), sortiert in zip(FAECHER, (True, False), strict=True):
        for i, (wort, spam) in enumerate(fach[sortiert]):
            falsch = "ki-k1-zug--rot" if spam != sortiert else ""
            vorn.append(_pille(x, FACH_Y + 105 + i * 50, wort, 17, art=falsch))
    return hinten, vorn


def _ebene() -> tuple[list, list]:
    x0, x1, y0, y1 = EBENE
    hinten = [
        _linie(f"M {x0} {y0} L {x0} {y1} L {x1} {y1}", y0, y1),
        *(
            _linie(f"M {x0} {_r(y)} L {x1} {_r(y)}", y, y + 1, "ki-k1-grau", 1)
            for y in (y0 + 125, y0 + 250, y0 + 375)
        ),
    ]
    for i, (a, b, _) in enumerate(LINIEN):
        (ax, ay), (bx, by) = _punkt(EBENE, *a), _punkt(EBENE, *b)
        art, dicke = ("ki-k1-rot", 3) if i == len(LINIEN) - 1 else ("ki-k1-grau", 1.5)
        d = f"M {_r(ax)} {_r(ay)} L {_r(bx)} {_r(by)}"
        hinten.append(_linie(d, y0 + 60 + i * 200, y0 + 160 + i * 200, art, dicke))
    vorn = [
        _t(MITTE, y1 + 34, "mehr Werbung →", "ki-k1-wort", 15),
        _t(
            x0 - 18,
            (y0 + y1) / 2,
            "fremder Absender →",
            "ki-k1-wort",
            15,
            transform=f"rotate(-90 {x0 - 18} {(y0 + y1) / 2})",
        ),
    ]
    for x, spam, name in ((200, True, "Spam"), (390, False, "echte Mail")):
        art = "ki-k2-spam" if spam else "ki-k2-post"
        teile = [
            _e("circle", klasse=art, cx=x, cy=y0 - 40, r=7),
            _e("text", name, x=x + 14, y=y0 - 35, font_size=15, klasse="ki-k1-wort"),
        ]
        vorn.append(_e("g", kinder=teile, klasse="ki-k1-zug", data_y=y0 - 40))
    grenzen = [n for _, _, n in LINIEN]
    for i, (u, v, spam) in enumerate(BEISPIELE):
        stufe = next(k for k, n in enumerate(grenzen) if i < n)
        x, y = _punkt(EBENE, u, v)
        kreis = _e(
            "circle", klasse="ki-k2-spam" if spam else "ki-k2-post", cx=x, cy=y, r=7
        )
        vorn.append(
            _e("g", kinder=[kreis], klasse="ki-k1-zug", data_y=y0 + 40 + stufe * 200)
        )
    return hinten, vorn


def _neu() -> tuple[list, list]:
    wort, u, v = NEU
    x0, x1, y0, y1 = KLEIN
    a, b, _ = LINIEN[-1]
    (ax, ay), (bx, by) = _punkt(KLEIN, *a), _punkt(KLEIN, *b)
    px, py = _punkt(KLEIN, u, v)
    hinten = [
        _linie(f"M {MITTE} {NEU_Y + 20} L {MITTE} {y0}", NEU_Y + 20, y0),
        _linie(f"M {x0} {y0} L {x0} {y1} L {x1} {y1}", y0, y1),
        _linie(f"M {_r(ax)} {_r(ay)} L {_r(bx)} {_r(by)}", y0, y1, "ki-k1-rot", 3),
    ]
    neu = _e("circle", klasse="ki-k2-neu", cx=px, cy=py, r=9)
    vorn = [
        _pille(MITTE, NEU_Y, wort, 17),
        _e("g", kinder=[neu], klasse="ki-k1-zug", data_y=py),
        _pille(px + 20, py + 70, "Spam", 19, art="ki-k1-wahl", data_an=py),
    ]
    return hinten, vorn


def _brett() -> tuple[list, list]:
    x, y, s = BRETT
    f = s / 8
    hinten = [
        _linie(
            f"M {x} {_r(y + i * f)} L {x + s} {_r(y + i * f)}",
            y + i * f,
            y + i * f + 1,
            dicke=1,
        )
        for i in range(9)
    ]
    hinten += [
        _linie(f"M {_r(x + i * f)} {y} L {_r(x + i * f)} {y + s}", y, y + s, dicke=1)
        for i in range(9)
    ]
    vorn = []
    for i, (sp, ze) in enumerate(
        ((1, 0), (3, 0), (5, 0), (0, 1), (2, 1), (4, 5), (6, 5), (3, 6), (5, 6), (7, 6))
    ):
        art = "ki-k2-spam" if i < 5 else "ki-k2-post"
        k = _e(
            "circle",
            klasse=art,
            cx=x + (sp + 0.5) * f,
            cy=y + (ze + 0.5) * f,
            r=f * 0.36,
        )
        vorn.append(_e("g", kinder=[k], klasse="ki-k1-zug", data_y=y + ze * f))
    return hinten, vorn


def route() -> str:
    """Der Weg des roten Punkts: Regel, Spam-Fach, Trennlinie, neue Mail, Brett."""
    m, y1 = MITTE, EBENE[3]
    bx, by = _punkt(EBENE, *LINIEN[-1][1])
    _, sy = _punkt(EBENE, 0.5, 1 - (0.5 - 0.1) / 0.9 * 0.75)
    px, py = _punkt(KLEIN, *NEU[1:])
    fx = FAECHER[0][1]
    return " ".join(
        [
            f"M {m} {LINSE} L {m} {REGEL_Y}",
            f"C {m} {REGEL_Y + 90} {fx} {FACH_Y - 70} {fx} {FACH_Y + 30}",
            f"C {fx} {FACH_Y + 260} {m} {FACH_Y + 200} {m} {FACH_Y + 330}",
            f"L {m} {_r(sy)} L {_r(bx)} {_r(by)}",
            f"C {_r(bx)} {_r(by + 120)} {m} {y1 + 60} {m} {y1 + 160}",
            f"L {m} {KLEIN[2]} C {m} {_r(py - 40)} {_r(px)} {_r(py - 40)}",
            f"{_r(px)} {_r(py)}",
            f"C {_r(px)} {_r(py + 140)} {m} {KLEIN[3]} {m} {KLEIN[3] + 80}",
            f"L {m} {ENDE}",
        ]
    )


TEILE = {
    "Regel": (_regel,),
    "Beispiele": (_ebene,),
    "Neue Mail": (_neu,),
    "Gelernt": (_brett,),
}


def _ende() -> list:
    return [
        _linie(f"M -600 {ENDE} L 1200 {ENDE}", ENDE - 1, ENDE + 1),
        _e("circle", klasse="ki-k1-flaeche", cx=MITTE, cy=ENDE, r=22),
    ]


def zeichnung(stationen: tuple[str, ...]) -> dict:
    """Je Station die Elemente hinter und vor der Route, dazu Route und Punkt."""
    ringe = []
    for i, (x, y, r) in enumerate(
        ((60, 640, 150), (560, 1500, 220), (40, 2700, 180), (580, 3500, 160))
    ):
        kreise = [_e("circle", cx=x, cy=y, r=r), _e("circle", cx=x, cy=y, r=r * 0.55)]
        ringe.append(
            _e("g", kinder=kreise, klasse="ki-k1-ring", data_f=0.12 + (i % 2) * 0.08)
        )
    hinten, vorn = [], []
    for station in stationen:
        h, v = [], []
        for teil in TEILE[station]:
            th, tv = teil()
            h += th
            v += tv
        if station == stationen[-1]:
            h += _ende()
        hinten.append(_e("g", kinder=h, data_station=station))
        vorn.append(_e("g", kinder=v, klasse="ki-k1-station", data_station=station))
    return {
        "breite": W,
        "hoehe": HOEHE,
        "ringe": ringe,
        "hinten": hinten,
        "vorn": vorn,
        "route": route(),
        "punkt": (MITTE, ENDE),
    }
