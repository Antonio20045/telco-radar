"""Die Linienzeichnung von Kapitel 1 der KI-Seite (Pitch 9, Schnitte 10–12).

Rechnet jede Koordinate der Fahrt in einer 600 Einheiten breiten Zeichnung:
Frage, Schneidwerk mit Tokens und Nummern, schräge Karte der Bedeutungen,
Kreis der Aufmerksamkeit, Trichter mit den Kandidaten und die Antwort, dazu
die Route des roten Punkts. Jedes Element ist ein Dict ``tag``, ``attrs``,
``text``, ``kinder``; die Vorlage schreibt es, ``app.js`` animiert es über
``data-y`` (erscheint), ``data-an`` (Punkt erreicht) und ``data-h``.
Farben stehen nur als Klassen in ``style.css``. Pillenbreiten schätzt
``breite()`` aus der Schriftgröße von Instrument Sans.
"""

from __future__ import annotations

import math

W = 600
MITTE = 300
FRAGE = "Kann ich meinen Vertrag kündigen?"
TOKENS = (
    ("Kann", 42173),
    ("ich", 1873),
    ("meinen", 30515),
    ("Vertrag", 61102),
    ("künd", 9420),
    ("igen", 2211),
    ("?", 30),
)
FOKUS = 4
BEZUG = 3
ORTE: tuple[tuple[float, float], ...] = (
    (0.13, 0.12),
    (0.3, 0.42),
    (0.45, 0.1),
    (0.62, 0.5),
    (0.86, 0.28),
)
ORTE += ((0.9, 0.62), (0.08, 0.86))
NACHBARN = (
    ("Tarif", 0.5, 0.72, 3),
    ("Laufzeit", 0.78, 0.78, 3),
    ("beenden", 0.95, 0.08, 4),
    ("wechseln", 0.7, 0.16, 4),
    ("du", 0.18, 0.58, 1),
    ("wir", 0.4, 0.62, 1),
    ("dein", 0.6, 0.02, 2),
)
WINKEL = (200, 235, 270, 320, 90, 40, 145)
GEWICHTE = (0.05, 0.08, 0.22, 0.62, 0.0, 0.38, 0.03)
ANTEIL_AB = 0.2
KANDIDATEN: tuple[tuple[str, float, int], ...] = (
    ("Ja", 0.62, 100),
    ("Das", 0.17, 240),
    ("Grundsätzlich", 0.11, 385),
)
KANDIDATEN += (("Nein", 0.06, 525),)
ANTWORT = (("Ja,", "das", "geht", "zum"), ("Ende", "der", "Laufzeit."))
RINGE = ((60, 700, 150), (560, 1500, 220), (40, 2560, 180), (580, 3460, 160))
LINSE = 380
FRAGE_Y = 480
SCHNITT = 597
REIHEN = (700, 760)
ZAEHLER_Y = 850
KARTE = (1160, 1690)
KREIS = (2500, 185)
TRICHTER = 3020
WAHL_Y = TRICHTER + 380
ANTWORT_Y = TRICHTER + 680
ENDE = ANTWORT_Y + 760
HOEHE = ENDE + 60
_SCHMAL = frozenset("iljtfr.,:;!?'|I ")
_BREIT = frozenset("mwMW")


def breite(text: str, schrift: float) -> float:
    """Geschätzte Breite eines Texts in Instrument Sans bei ``schrift``."""
    em = 0.0
    for z in text:
        if z in _SCHMAL:
            em += 0.3
        elif z in _BREIT:
            em += 0.82
        else:
            em += 0.66 if z.isupper() else 0.55
    return em * schrift


def _r(v):
    return round(v, 1) if isinstance(v, float) else v


def _e(tag: str, text: str | None = None, kinder: list | None = None, **a) -> dict:
    """Ein SVG-Element; ``klasse`` wird ``class``, ``_`` im Namen wird ``-``."""
    attrs = [
        ("class" if k == "klasse" else k.replace("_", "-"), _r(v)) for k, v in a.items()
    ]
    return {"tag": tag, "attrs": attrs, "text": text, "kinder": kinder or []}


def _t(x, y, text, klasse: str, f: float = 15, **a) -> dict:
    return _e(
        "text", text, x=x, y=y, font_size=f, text_anchor="middle", klasse=klasse, **a
    )


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def ort(u: float, v: float) -> tuple[float, float]:
    """Punkt auf der schrägen Karte der Bedeutungen (u quer, v in die Tiefe)."""
    vv = v**1.25
    links, rechts = _lerp(140, 20, vv), _lerp(460, 580, vv)
    return _lerp(links, rechts, u), _lerp(KARTE[0], KARTE[1], vv)


def pillen_breite(wort: str, f: float) -> float:
    """Breite einer Pille: Text plus Rand links und rechts."""
    return breite(wort, f) + f * 1.3


def _pille(x, y, wort, f=21, dreh=0, art="", zeige=None, **a) -> dict:
    w, h = pillen_breite(wort, f), f * 2
    rand = _e("rect", x=-w / 2, y=-h / 2, width=w, height=h, rx=h / 2)
    schrift = _e("text", wort, y=f * 0.35, font_size=f, text_anchor="middle")
    lage = f"translate({_r(float(x))},{_r(float(y))}) rotate({dreh})"
    innen = _e("g", kinder=[rand, schrift], transform=lage)
    klasse = f"ki-k1-zug {art}".strip()
    return _e(
        "g", kinder=[innen], klasse=klasse, data_y=y if zeige is None else zeige, **a
    )


def _linie(d: str, y0: float, y1: float, art: str = "", dicke: float = 1.3) -> dict:
    klasse = f"ki-k1-zieh {art}".strip()
    return _e(
        "path",
        klasse=klasse,
        d=d,
        stroke_width=dicke,
        data_y=y0,
        data_h=max(y1 - y0, 1),
    )


def _zahnrad(cx: float, cy: float, r: float, zaehne: int, richtung: int) -> dict:
    aussen = r + 7

    def p(rad, a):
        return f"{_r(cx + math.cos(a) * rad)} {_r(cy + math.sin(a) * rad)}"

    d = []
    for i in range(zaehne):
        a0, a1, a2 = (2 * math.pi * k / zaehne for k in (i, i + 0.5, i + 1))
        d.append(
            f"M {p(r, a0)} L {p(aussen, a0)} A {aussen} {aussen} 0 0 1 {p(aussen, a1)} "
            f"L {p(r, a1)} A {r} {r} 0 0 1 {p(r, a2)}"
        )
    teile = [
        _e("path", klasse="ki-k1-flaeche", d=" ".join(d)),
        _e("circle", klasse="ki-k1-flaeche", cx=cx, cy=cy, r=r * 0.35),
        _e("circle", klasse="ki-k1-nabe", cx=cx, cy=cy, r=3),
    ]
    return _e(
        "g", kinder=teile, klasse="ki-k1-rad", data_cx=cx, data_cy=cy, data_f=richtung
    )


def _frage() -> tuple[list, list]:
    hinten = [_linie(f"M -600 {LINSE} L 1200 {LINSE}", LINSE - 1, LINSE + 1)]
    linse = _e("circle", klasse="ki-k1-flaeche", cx=MITTE, cy=LINSE, r=22)
    return [*hinten, linse], [_pille(MITTE, FRAGE_Y, FRAGE, 20)]


def token_x(i: int) -> int:
    """Waagerechte Lage des i-ten Tokens unter dem Schneidwerk."""
    return 60 + i * 80


def _zaehler(x: int, nummer: int) -> dict:
    y = ZAEHLER_Y
    teile = [
        _e("rect", x=x - 34, y=y, width=68, height=34, rx=3),
        _e("line", x1=x - 34, x2=x + 34, y1=y + 8, y2=y + 8),
        _t(x, y + 25, f"{nummer:05d}", "ki-k1-zahl", 13, data_y=y),
    ]
    return _e("g", kinder=teile, klasse="ki-k1-zaehler")


def _woerter() -> tuple[list, list]:
    s = SCHNITT
    hinten = [
        _linie(f"M 40 {s - 7} L 560 {s - 7}", s - 8, s - 6),
        _linie(f"M 40 {s + 7} L 560 {s + 7}", s + 6, s + 8),
        _zahnrad(40, s, 18, 9, 1),
        _zahnrad(560, s, 18, 9, -1),
    ]
    vorn = []
    for i, (wort, nummer) in enumerate(TOKENS):
        x, y = token_x(i), REIHEN[i % 2]
        for xx in (x - 6, x + 6):
            hinten.append(
                _linie(f"M {xx} {s + 15} L {xx} {y - 24}", s + 15, y - 24, dicke=1)
            )
        hinten.append(
            _e("path", klasse="ki-k1-flaeche", d=f"M {x - 6} {s + 7} l 6 -10 l 6 10")
        )
        hinten.append(
            _linie(f"M {x} {y + 22} L {x} {ZAEHLER_Y}", y + 22, ZAEHLER_Y, dicke=1)
        )
        vorn += [_pille(x, y, wort, 19, -5 if i % 2 else 5), _zaehler(x, nummer)]
    return hinten, vorn


def _bedeutung() -> tuple[list, list]:
    t0, t1 = KARTE
    hinten = []
    for i in range(len(TOKENS)):
        x, z = token_x(i), _r(MITTE + (token_x(i) - MITTE) * 0.12)
        if i != BEZUG:
            d = f"M {x} {ZAEHLER_Y + 34} C {x} 1040 {z} 1060 {z} 1140"
            hinten.append(_linie(d, ZAEHLER_Y + 34, 1140, dicke=1))
    netz = [(ort(k / 8, 0), ort(k / 8, 1)) for k in range(9)]
    netz += [(ort(0, k / 6), ort(1, k / 6)) for k in range(7)]
    for (ax, ay), (bx, by) in netz:
        d = f"M {_r(ax)} {_r(ay)} L {_r(bx)} {_r(by)}"
        hinten.append(_linie(d, min(ay, by), max(by, ay + 1), "ki-k1-grau", 1))
    orte = [ort(u, v) for u, v in ORTE]
    vorn = []
    for wort, u, v, zu in NACHBARN:
        (qx, qy), (zx, zy) = ort(u, v), orte[zu]
        hinten.append(_e("line", klasse="ki-k1-strich", x1=zx, y1=zy, x2=qx, y2=qy))
        teile = [_e("circle", cx=qx, cy=qy, r=3.5), _t(qx, qy - 9, wort, "ki-k1-wort")]
        vorn.append(_e("g", kinder=teile, klasse="ki-k1-zug ki-k1-nachbar", data_y=qy))
    vorn += [_pille(x, y, w, 17) for (w, _), (x, y) in zip(TOKENS, orte, strict=True)]
    return hinten, vorn


def kreis_orte() -> list[tuple[float, float]]:
    """Lage der Tokens auf dem Kreis der Aufmerksamkeit."""
    cy, r = KREIS
    return [
        (MITTE + r * math.cos(math.radians(w)), cy + r * math.sin(math.radians(w)))
        for w in WINKEL
    ]


def _aufmerksamkeit() -> tuple[list, list]:
    cy, r = KREIS
    bogen = f"A {r} {r} 0 1 1"
    rund = f"M {MITTE + r} {cy} {bogen} {MITTE - r} {cy} {bogen} {MITTE + r} {cy}"
    hinten, vorn = [_linie(rund, cy - r, cy + r, "ki-k1-grau", 1)], []
    punkte = kreis_orte()
    kx, ky = punkte[FOKUS]
    for i, (qx, qy) in enumerate(punkte):
        if i == FOKUS:
            continue
        mx = (qx + kx) / 2 + (MITTE - (qx + kx) / 2) * 0.35
        my = (qy + ky) / 2 + (cy - (qy + ky) / 2) * 0.35
        rot = " ki-k1-rot" if i == BEZUG else ""
        d = f"M {_r(kx)} {_r(ky)} Q {_r(mx)} {_r(my)} {_r(qx)} {_r(qy)}"
        hinten.append(
            _e(
                "path",
                klasse="ki-k1-sehne" + rot,
                d=d,
                stroke_width=1 + GEWICHTE[i] * 10,
                data_an=cy - 40,
                style=f"--n:{i}",
            )
        )
        if GEWICHTE[i] >= ANTEIL_AB:
            anteil = f"{round(GEWICHTE[i] * 100)} %"
            vorn.append(_t(mx, my - 8, anteil, "ki-k1-anteil" + rot, data_an=cy - 40))
    for i, ((wort, _), (x, y)) in enumerate(zip(TOKENS, punkte, strict=True)):
        if i == FOKUS:
            vorn.append(_pille(x, y, wort, 19, art="ki-k1-fokus", data_an=cy + r - 30))
        else:
            vorn.append(_pille(x, y, wort, 19))
    return hinten, vorn


def _kandidaten() -> tuple[list, list]:
    t, ky = TRICHTER, WAHL_Y
    hinten = [
        _e("ellipse", klasse="ki-k1-form", cx=MITTE, cy=t, rx=200, ry=18),
        _linie(
            f"M 100 {t} C 110 {t + 90} 280 {t + 120} 288 {t + 170} L 288 {t + 210}",
            t,
            t + 210,
        ),
        _linie(
            f"M 500 {t} C 490 {t + 90} 320 {t + 120} 312 {t + 170} L 312 {t + 210}",
            t,
            t + 210,
        ),
        _zahnrad(520, t + 160, 16, 8, 1),
    ]
    vorn = []
    for i, (wort, p, x) in enumerate(KANDIDATEN):
        rot = "" if i else "ki-k1-rot"
        d = f"M {MITTE} {t + 210} C {MITTE} {t + 290} {x} {t + 280} {x} {ky - 22}"
        hinten.append(_linie(d, t + 210, ky - 22, rot, 1 + p * 10))
        if i:
            vorn.append(_pille(x, ky, wort, 19))
        else:
            vorn.append(_pille(x, ky, wort, 19, art="ki-k1-wahl", data_an=ky - 10))
        vorn.append(_t(x, ky + 40, f"{round(p * 100)} %", f"ki-k1-wert {rot}".strip()))
    return hinten, vorn


def _antwort() -> tuple[list, list]:
    vorn = []
    for ri, reihe in enumerate(ANTWORT):
        y = ANTWORT_Y + ri * 56
        breiten = [pillen_breite(w, 19) for w in reihe]
        x = MITTE - (sum(breiten) + 10 * (len(reihe) - 1)) / 2
        for i, (wort, b) in enumerate(zip(reihe, breiten, strict=True)):
            art = "ki-k1-zug--rot" if ri == 0 and i == 0 else ""
            zeige = y - 60 + i * 14 + ri * 40
            vorn.append(_pille(x + b / 2, y, wort, 19, art=art, zeige=zeige))
            x += b + 10
    hinten = [
        _linie(f"M -600 {ENDE} L 1200 {ENDE}", ENDE - 1, ENDE + 1),
        _e("circle", klasse="ki-k1-flaeche", cx=MITTE, cy=ENDE, r=22),
    ]
    return hinten, vorn


def route() -> str:
    """Der Weg des roten Punkts durch alle Stationen, von der Frage bis zum Ende."""
    vx, vy = (_r(k) for k in ort(*ORTE[BEZUG]))
    tx, ty = (_r(k) for k in ort(0.5, 0.72))
    cy, r = KREIS
    t, ky, ay, m, x = TRICHTER, WAHL_Y, ANTWORT_Y, MITTE, KANDIDATEN[0][2]
    return " ".join(
        [
            f"M {m} {LINSE} L {m} {FRAGE_Y} L {m} {SCHNITT} L {m} {REIHEN[1]}",
            f"L {m} {ZAEHLER_Y + 17} L {m} 1100 C {m} 1150 {m} 1160 {m} 1170",
            f"C {m} 1260 {vx} {_r(vy - 90)} {vx} {vy}",
            f"C {vx} {_r(vy + 40)} {tx} {_r(ty - 40)} {tx} {ty}",
            f"C {tx} {_r(ty + 60)} {m} {KARTE[1] + 10} {m} {KARTE[1] + 70}",
            f"L {m} {cy - r} L {m} {cy} L {m} {cy + r} L {m} {t} L {m} {t + 210}",
            f"C {m} {t + 290} {x} {t + 280} {x} {ky - 22} L {x} {ky}",
            f"C {x} {ky + 120} {m} {ky + 110} {m} {ay - 60}",
            f"L {m} {ay + 56} L {m} {ENDE}",
        ]
    )


TEILE = (_frage, _woerter, _bedeutung, _aufmerksamkeit, _kandidaten, _antwort)


def zeichnung(stationen: tuple[str, ...]) -> dict:
    """Je Station die Elemente hinter und vor der Route, dazu Route und Punkt.

    Kandidaten und Antwort bilden zusammen die letzte Station.
    """
    ringe = []
    for i, (x, y, r) in enumerate(RINGE):
        kreise = [_e("circle", cx=x, cy=y, r=r), _e("circle", cx=x, cy=y, r=r * 0.55)]
        ringe.append(
            _e("g", kinder=kreise, klasse="ki-k1-ring", data_f=0.12 + (i % 2) * 0.08)
        )
    hinten, vorn = [], []
    for station, teile in zip(
        stationen,
        (TEILE[:1], TEILE[1:2], TEILE[2:3], TEILE[3:4], TEILE[4:]),
        strict=True,
    ):
        h, v = [], []
        for teil in teile:
            th, tv = teil()
            h += th
            v += tv
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
