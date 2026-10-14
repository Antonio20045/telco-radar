"""Die Linienzeichnung von Kapitel 3 der KI-Seite: „Wie eine KI lernt“.

Gleiche Machart wie Kapitel 1 (``ki_kapitel_bild``): Raten des nächsten
Zeichens mit Stellschrauben, vier Textproben eines kleinen Modells nach
``PROBEN`` Runden (Karpathy 2015, wörtlich gekürzt), ein Raster aus Chips
für die Rechenzeit, zum Schluss feste Stellschrauben beim Benutzen.
"""

from __future__ import annotations

from .ki_kapitel_bild import MITTE, W, _e, _linie, _pille, _t, _zahnrad

LINSE = 380
WORT = "Vertra"
KACHEL_Y = 520
TIPP = (("Tipp: k", 330), ("richtig: g", 500))
TIPP_Y = 700
SCHRAUBEN_Y = 880
PROBEN = (
    (100, "tyntd-iafhatawiaoihrdemot lytdws"),
    (300, "Keushey. Thom here sheulke,"),
    (700, "Aftair fall unsuch that the hall"),
    (2000, "“Why do what that day,” replied Natasha"),
)
KARTE_Y = (1560, 1790, 2020, 2250)
CHIPS = (120, 2620, 10, 5, 36)
FRAGE_Y = 3200
FEST_Y = 3360
ANTWORT = "Ja, zum Ende der Laufzeit."
ANTWORT_Y = 3520
ENDE = 4270
HOEHE = ENDE + 60


def kachel_x(i: int) -> float:
    """Lage der i-ten Zeichenkachel; die letzte ist das gesuchte Zeichen."""
    return MITTE + (i - len(WORT) / 2) * 56


def _kachel(x: float, zeichen: str, art: str = "") -> dict:
    rand = _e("rect", x=-23, y=-28, width=46, height=56, rx=6)
    schrift = _e("text", zeichen, y=8, font_size=22, text_anchor="middle")
    innen = _e("g", kinder=[rand, schrift], transform=f"translate({x},{KACHEL_Y})")
    return _e("g", kinder=[innen], klasse=f"ki-k1-zug {art}".strip(), data_y=KACHEL_Y)


def _schrauben(y: int, fest: bool = False) -> list:
    raeder = [
        _zahnrad(x, y, 18, 9, 1 if i % 2 else -1)
        for i, x in enumerate(range(100, 501, 100))
    ]
    if fest:
        for r in raeder:
            r["attrs"] = [("class", "ki-k3-fest")]
    return raeder


def _raten() -> tuple[list, list]:
    hinten = [
        _linie(f"M -600 {LINSE} L 1200 {LINSE}", LINSE - 1, LINSE + 1),
        _e("circle", klasse="ki-k1-flaeche", cx=MITTE, cy=LINSE, r=22),
    ]
    vorn = [_kachel(kachel_x(i), z) for i, z in enumerate(WORT)]
    frage_x = kachel_x(len(WORT))
    vorn.append(_kachel(frage_x, "?", "ki-k1-zug--rot"))
    for i, (wort, x) in enumerate(TIPP):
        d = f"M {frage_x} {KACHEL_Y + 30} C {frage_x} 620 {x} 620 {x} {TIPP_Y - 20}"
        hinten.append(_linie(d, KACHEL_Y + 30, TIPP_Y - 20, dicke=1))
        d = f"M {x} {TIPP_Y + 20} C {x} 800 {MITTE} 780 {MITTE} {SCHRAUBEN_Y - 25}"
        hinten.append(_linie(d, TIPP_Y + 20, SCHRAUBEN_Y - 25, dicke=1))
        if i:
            vorn.append(_pille(x, TIPP_Y, wort, 17, art="ki-k1-wahl", data_an=TIPP_Y))
        else:
            vorn.append(_pille(x, TIPP_Y, wort, 17))
    hinten.append(
        _linie(f"M 60 {SCHRAUBEN_Y} L 540 {SCHRAUBEN_Y}", SCHRAUBEN_Y, SCHRAUBEN_Y + 1)
    )
    return hinten + _schrauben(SCHRAUBEN_Y), vorn


def _runden() -> tuple[list, list]:
    hinten, vorn = [], []
    for (runde, probe), y in zip(PROBEN, KARTE_Y, strict=True):
        hinten.append(
            _e(
                "rect",
                klasse="ki-k1-flaeche",
                x=40,
                y=y - 35,
                width=520,
                height=70,
                rx=6,
            )
        )
        vorn.append(_pille(118, y - 35, f"Runde {runde}", 15))
        vorn.append(
            _e(
                "g",
                kinder=[_t(MITTE, y + 12, probe, "ki-k3-probe", 19)],
                klasse="ki-k1-zug",
                data_y=y,
            )
        )
    return hinten, vorn


def _chips() -> tuple[list, list]:
    x0, y0, spalten, reihen, s = CHIPS
    vorn = []
    for r in range(reihen):
        zeile = [
            _e("rect", x=x0 + c * s, y=y0 + r * s, width=s - 8, height=s - 8, rx=3)
            for c in range(spalten)
        ]
        vorn.append(
            _e("g", kinder=zeile, klasse="ki-k1-zug ki-k3-chips", data_y=y0 + r * s)
        )
    return [], vorn


def _benutzen() -> tuple[list, list]:
    hinten = [
        *_schrauben(FEST_Y, fest=True),
        _linie(f"M 60 {FEST_Y} L 540 {FEST_Y}", FEST_Y, FEST_Y + 1, "ki-k1-rot", 3),
        _linie(f"M -600 {ENDE} L 1200 {ENDE}", ENDE - 1, ENDE + 1),
        _e("circle", klasse="ki-k1-flaeche", cx=MITTE, cy=ENDE, r=22),
    ]
    vorn = [
        _pille(MITTE, FRAGE_Y, "Kann ich kündigen?", 19),
        _pille(MITTE, ANTWORT_Y, ANTWORT, 19, art="ki-k1-wahl", data_an=ANTWORT_Y),
    ]
    return hinten, vorn


def route() -> str:
    """Der Weg des roten Punkts: zum gesuchten Zeichen, zur Lösung, dann mittig."""
    m, fx, rx = MITTE, kachel_x(len(WORT)), TIPP[1][1]
    return " ".join(
        [
            f"M {m} {LINSE} L {m} 470 C {m} 500 {fx} 470 {fx} {KACHEL_Y}",
            f"L {fx} 560 C {fx} 620 {rx} 640 {rx} {TIPP_Y}",
            f"C {rx} 800 {m} 780 {m} {SCHRAUBEN_Y} L {m} {ENDE}",
        ]
    )


TEILE = {
    "Raten": _raten,
    "Runden": _runden,
    "Rechenzeit": _chips,
    "Benutzen": _benutzen,
}


def zeichnung(stationen: tuple[str, ...]) -> dict:
    """Je Station die Elemente hinter und vor der Route, dazu Route und Punkt."""
    ringe = []
    lagen = ((60, 640, 150), (560, 1500, 220), (40, 2700, 180), (580, 3600, 160))
    for i, (x, y, r) in enumerate(lagen):
        kreise = [_e("circle", cx=x, cy=y, r=r), _e("circle", cx=x, cy=y, r=r * 0.55)]
        ringe.append(
            _e("g", kinder=kreise, klasse="ki-k1-ring", data_f=0.12 + (i % 2) * 0.08)
        )
    hinten, vorn = [], []
    for station in stationen:
        h, v = TEILE[station]()
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
