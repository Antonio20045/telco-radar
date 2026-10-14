"""Die Linienzeichnung von Kapitel 4 der KI-Seite: „Warum sie würfelt“.

Gleiche Machart wie Kapitel 1 (``ki_kapitel_bild``) und dieselbe Frage mit
denselben vier Kandidaten (``KANDIDATEN``, Rest ``REST``). ``verteilung()``
rechnet die Anteile bei einer Temperatur T: p(T) ∝ p^(1/T) (Hinton u. a.
2015); Balken, Prozente und Sätze lesen nur diese Funktion. ``ziehungen()``
zieht fünfmal mit festen Zufallszahlen (``WUERFE``) aus der Verteilung bei
T = 1, damit die Seite bei jedem Bau gleich aussieht.
"""

from __future__ import annotations

from .ki_kapitel_bild import FRAGE, KANDIDATEN, MITTE, W, _e, _linie, _pille, _t

REST = round(1 - sum(p for _, p, _ in KANDIDATEN), 4)
TEMPERATUREN = ((2.0, "heiß"), (1.0, "normal"), (0.5, "kalt"))
WUERFE = (0.12, 0.55, 0.71, 0.33, 0.86)
LINSE = 380
FRAGE_Y = 480
WUERFEL_Y = 640
BALKEN_Y = 830
BALKEN_X, BALKEN_L = 280, 260
ROHR = (30, 1600, 2500)
GRUPPEN_Y = (1640, 1940, 2240)
ZUG_Y = 2900
ENDE = 3870
HOEHE = ENDE + 60


def verteilung(t: float) -> list[tuple[str, float]]:
    """Anteile der vier Kandidaten bei Temperatur ``t`` (Rest zählt mit)."""
    roh = [(w, p ** (1 / t)) for w, p, _ in KANDIDATEN]
    summe = sum(g for _, g in roh) + REST ** (1 / t)
    return [(w, g / summe) for w, g in roh]


def ziehungen() -> list[str]:
    """Das gezogene erste Wort je Wurf bei Temperatur 1; der Rest heißt „…“."""
    out = []
    for u in WUERFE:
        summe = 0.0
        wahl = "…"
        for w, p in verteilung(1.0):
            summe += p
            if u < summe:
                wahl = w
                break
        out.append(wahl)
    return out


def zahl(t: float) -> str:
    """Eine Temperatur in deutscher Schreibweise."""
    return f"{t:g}".replace(".", ",")


def prozent(p: float) -> str:
    """Ein Anteil als ganze Prozent, wie er auf der Seite steht."""
    return f"{round(p * 100)} %"


def _rechts(x, y, text, klasse, anker, zeige=None) -> dict:
    t = _e("text", text, x=x, y=y, font_size=15, text_anchor=anker, klasse=klasse)
    return t if zeige is None else _e("g", kinder=[t], data_y=zeige)


def _balken(y0: float, t: float) -> tuple[list, list]:
    hinten, vorn = [], []
    for i, (wort, p) in enumerate(verteilung(t)):
        y = y0 + i * 46
        lang = max(p * BALKEN_L, 2)
        rot = "ki-k1-rot" if i == 0 else ""
        d = f"M {BALKEN_X} {y} L {round(BALKEN_X + lang, 1)} {y}"
        hinten.append(_linie(d, y - 10, y + 10, rot, 18))
        vorn.append(_rechts(BALKEN_X - 14, y + 5, wort, "ki-k1-wort", "end", y))
        wert = f"ki-k1-wert {rot}".strip()
        vorn.append(_rechts(BALKEN_X + lang + 12, y + 5, prozent(p), wert, "start"))
    return hinten, vorn


def _wuerfel() -> dict:
    x, y, s = MITTE, WUERFEL_Y, 110
    teile = [
        _e(
            "rect",
            klasse="ki-k1-flaeche",
            x=x - s / 2,
            y=y - s / 2,
            width=s,
            height=s,
            rx=16,
        )
    ]
    for dx, dy in ((-1, -1), (1, -1), (0, 0), (-1, 1), (1, 1)):
        teile.append(
            _e("circle", klasse="ki-k1-nabe", cx=x + dx * 28, cy=y + dy * 28, r=8)
        )
    return _e("g", kinder=teile, klasse="ki-k1-rad", data_cx=x, data_cy=y, data_f=1)


def _wuerfeln() -> tuple[list, list]:
    hinten = [
        _linie(f"M -600 {LINSE} L 1200 {LINSE}", LINSE - 1, LINSE + 1),
        _e("circle", klasse="ki-k1-flaeche", cx=MITTE, cy=LINSE, r=22),
        _wuerfel(),
    ]
    h, vorn = _balken(BALKEN_Y, 1.0)
    return hinten + h, [_pille(MITTE, FRAGE_Y, FRAGE, 20), *vorn]


def _temperatur() -> tuple[list, list]:
    x, oben, unten = ROHR
    hinten = [
        _linie(f"M {x - 12} {oben} L {x - 12} {unten}", oben, unten),
        _linie(f"M {x + 12} {oben} L {x + 12} {unten}", oben, unten),
        _e("circle", klasse="ki-k2-neu", cx=x, cy=unten + 26, r=26),
    ]
    vorn = []
    for (t, name), y in zip(TEMPERATUREN, GRUPPEN_Y, strict=True):
        hinten.append(_linie(f"M {x + 12} {y} L {x + 50} {y}", y, y + 1))
        vorn.append(_pille(x + 140, y, f"{name} · {zahl(t)}", 16))
        h, v = _balken(y + 60, t)
        hinten += h
        vorn += v
    return hinten, vorn


def _ziehen() -> tuple[list, list]:
    vorn = []
    for i, wort in enumerate(ziehungen()):
        y = ZUG_Y + i * 60
        vorn.append(_t(150, y + 6, f"Versuch {i + 1}", "ki-k1-wort", 15, data_y=y))
        art = "ki-k1-zug--rot" if wort == KANDIDATEN[0][0] else ""
        vorn.append(_pille(MITTE + 60, y, f"{wort} …", 18, art=art))
    hinten = [
        _linie(f"M -600 {ENDE} L 1200 {ENDE}", ENDE - 1, ENDE + 1),
        _e("circle", klasse="ki-k1-flaeche", cx=MITTE, cy=ENDE, r=22),
    ]
    return hinten, vorn


def route() -> str:
    """Der Weg des roten Punkts: durch Frage und Würfel, das Thermometer hinab."""
    m, (x, oben, unten) = MITTE, ROHR
    return " ".join(
        [
            f"M {m} {LINSE} L {m} {BALKEN_Y - 40} L {m} 1500",
            f"C {m} 1560 {x} 1540 {x} {oben} L {x} {unten + 26}",
            f"C {x} {unten + 200} {m} {unten + 120} {m} {unten + 300} L {m} {ENDE}",
        ]
    )


TEILE = {"Würfel": _wuerfeln, "Temperatur": _temperatur, "Ziehen": _ziehen}


def zeichnung(stationen: tuple[str, ...]) -> dict:
    """Je Station die Elemente hinter und vor der Route, dazu Route und Punkt."""
    ringe = []
    lagen = ((540, 700, 150), (560, 1500, 220), (520, 2700, 180), (40, 3400, 160))
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
