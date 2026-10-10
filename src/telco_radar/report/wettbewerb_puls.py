"""Puls der Wettbewerbsseite: Meldungen je Kalenderwoche und Wettbewerber.

Antonio am 10.10.2026: die Seite soll zeigen, wer wie oft in den Meldungen
steht, Woche für Woche. Eine Woche, in der jeder Lauf ohne Bewertung blieb
(Redaktionsausfall), ist eine Lücke und keine Null; ebenso eine Woche ohne
Lauf. Gezählt werden die Chronik-Einträge der Wettbewerbsseite, also dieselben
Meldungen, die das Porträt darunter auflistet.
"""

from __future__ import annotations

from datetime import date, timedelta

from markupsafe import Markup, escape

WOCHEN = 13

KLASSE = {"deutsche-telekom": "telekom", "telefonica-o2": "o2", "1-1": "1-1"}
KURZNAME = {"deutsche-telekom": "Telekom", "telefonica-o2": "O2", "1-1": "1&1"}

GELESEN = "gelesen"
AUSFALL = "ausfall"
OHNE_LAUF = "ohne_lauf"

_BREITE, _HOEHE = 1100, 340
_LINKS, _RECHTS, _OBEN, _UNTEN = 44, 120, 24, 40
_ABSTAND_NAMEN = 22


def _montag(tag: date) -> date:
    return tag - timedelta(days=tag.weekday())


def _tag_de(iso: str) -> str:
    return f"{int(iso[8:10])}.{int(iso[5:7])}."


def puls(daten_je_anker: dict[str, list[str]], wochen: list[dict], stand: str) -> dict:
    """Zählt je Wettbewerber die Chronik-Einträge der letzten `WOCHEN` Wochen.

    `daten_je_anker` hält je Wettbewerber-Anker die ISO-Daten seiner
    Chronik-Einträge, `wochen` die Läufe mit `date` und `ausfall`.
    """
    if not stand:
        return {"wochen": [], "reihen": [], "ausfall": None}
    ende = _montag(date.fromisoformat(stand))
    montage = [ende - timedelta(weeks=WOCHEN - 1 - i) for i in range(WOCHEN)]
    laeufe: dict[date, list[bool]] = {}
    for w in wochen:
        if w.get("date"):
            laeufe.setdefault(_montag(date.fromisoformat(w["date"])), []).append(
                bool(w.get("ausfall"))
            )
    spalten = []
    for m in montage:
        lauf = laeufe.get(m)
        zustand = OHNE_LAUF if not lauf else (AUSFALL if all(lauf) else GELESEN)
        spalten.append(
            {"montag": m.isoformat(), "kw": m.isocalendar()[1], "zustand": zustand}
        )
    reihen = []
    for anker, daten in daten_je_anker.items():
        zaehler: dict[date, int] = {}
        for d in daten:
            m = _montag(date.fromisoformat(d))
            zaehler[m] = zaehler.get(m, 0) + 1
        werte = [
            zaehler.get(m, 0) if s["zustand"] == GELESEN else None
            for m, s in zip(montage, spalten, strict=True)
        ]
        reihen.append(
            {
                "anker": anker,
                "name": KURZNAME.get(anker, anker),
                "klasse": KLASSE.get(anker, "ohne-farbe"),
                "werte": werte,
                "diese_woche": werte[-1],
            }
        )
    erster, letzter = montage[0].isoformat(), (ende + timedelta(days=6)).isoformat()
    ausfall_tage = sorted(
        w["date"] for w in wochen if w.get("ausfall") and erster <= w["date"] <= letzter
    )
    ausfall = (
        {"von": _tag_de(ausfall_tage[0]), "bis": _tag_de(ausfall_tage[-1])}
        if ausfall_tage
        else None
    )
    return {"wochen": spalten, "reihen": reihen, "ausfall": ausfall}


def aus_ansicht(ansicht: dict, wochen: list[dict]) -> dict:
    """Der Puls zur fertigen Wettbewerbsansicht: Daten aus ihrer Chronik."""
    daten = {
        w["anker"]: [e["datum"] for m in w["monate"] for e in m["eintraege"]]
        for w in ansicht["wettbewerber"]
    }
    return puls(daten, wochen, ansicht["stand"])


def _stuecke(spalten: list[dict]) -> list[list[int]]:
    stuecke, aktuell = [], []
    for i, s in enumerate(spalten):
        if s["zustand"] == GELESEN:
            aktuell.append(i)
        elif aktuell:
            stuecke.append(aktuell)
            aktuell = []
    if aktuell:
        stuecke.append(aktuell)
    return stuecke


def _el(tag: str, inhalt: str = "", **attr) -> str:
    werte = " ".join(
        f'{k.rstrip("_").replace("_", "-")}="{v}"' for k, v in attr.items()
    )
    return f"<{tag} {werte}>{inhalt}</{tag}>" if inhalt else f"<{tag} {werte}/>"


class _Achsen:
    def __init__(self, n: int, ymax: int) -> None:
        self.n, self.ymax = n, ymax

    def x(self, i: int) -> float:
        return round(_LINKS + i * (_BREITE - _LINKS - _RECHTS) / max(1, self.n - 1), 1)

    def y(self, v: float) -> float:
        return round(_OBEN + (_HOEHE - _OBEN - _UNTEN) * (1 - v / self.ymax), 1)


def _raster(spalten: list[dict], a: _Achsen) -> list[str]:
    teile = []
    for v in range(0, a.ymax + 1, 10):
        y = a.y(v)
        teile.append(
            _el(
                "line",
                class_="puls-gitter",
                x1=_LINKS,
                x2=_BREITE - _RECHTS,
                y1=y,
                y2=y,
            )
        )
        teile.append(
            _el(
                "text",
                str(v),
                class_="puls-achse",
                x=_LINKS - 10,
                y=y + 4,
                text_anchor="end",
            )
        )
    for i, s in enumerate(spalten):
        if i % 2 == 0 or i == a.n - 1:
            teile.append(
                _el(
                    "text",
                    f"KW {s['kw']}",
                    class_="puls-achse",
                    x=a.x(i),
                    y=_HOEHE - 12,
                    text_anchor="middle",
                )
            )
    return teile


def _luecke(daten: dict, a: _Achsen) -> list[str]:
    luecke = [i for i, s in enumerate(daten["wochen"]) if s["zustand"] != GELESEN]
    if not luecke:
        return []
    x0, x1 = a.x(luecke[0]) - 14, a.x(luecke[-1]) + 14
    mitte = round((x0 + x1) / 2, 1)
    ausfall = daten["ausfall"]
    titel = "Bewertung ausgefallen" if ausfall else "Kein Lauf"
    zeile = (
        f"{ausfall['von']} bis {ausfall['bis']}, keine Meldung bewertet"
        if ausfall
        else "keine Meldung gelesen"
    )
    return [
        _el(
            "rect",
            class_="puls-luecke",
            x=round(x0, 1),
            y=_OBEN,
            width=round(x1 - x0, 1),
            height=round(a.y(0) - _OBEN, 1),
            rx=10,
        ),
        _el(
            "text",
            titel,
            class_="puls-luecke-text",
            x=mitte,
            y=_OBEN + 26,
            text_anchor="middle",
        ),
        _el(
            "text",
            zeile,
            class_="puls-luecke-text",
            x=mitte,
            y=_OBEN + 46,
            text_anchor="middle",
        ),
    ]


def _linien(daten: dict, a: _Achsen) -> list[str]:
    teile = []
    stuecke = [st for st in _stuecke(daten["wochen"]) if len(st) > 1]
    for j, r in enumerate(daten["reihen"]):
        for st in stuecke:
            pfad = "M" + " L".join(f"{a.x(i)},{a.y(r['werte'][i])}" for i in st)
            flaeche = f"{pfad} L{a.x(st[-1])},{a.y(0)} L{a.x(st[0])},{a.y(0)} Z"
            inhalt = _el("path", class_="puls-flaeche", d=flaeche) + _el(
                "path",
                class_="puls-linie",
                pathLength=1,
                d=pfad,
                style=f"--v:{j * 0.25}s",
            )
            teile.append(_el("g", inhalt, class_=f"gr-anb--{r['klasse']}"))
    return teile


def _enden(daten: dict, a: _Achsen) -> list[str]:
    enden = sorted(
        (a.y(r["werte"][-1]), r) for r in daten["reihen"] if r["werte"][-1] is not None
    )
    teile, vorher = [], -99.0
    for y, r in enden:
        ly = max(y, vorher + _ABSTAND_NAMEN)
        vorher = ly
        x = a.x(a.n - 1)
        name = f"{escape(r['name'])} {r['werte'][-1]}"
        inhalt = _el("circle", class_="puls-punkt", cx=x, cy=y, r=5) + _el(
            "text", name, class_="puls-name", x=x + 14, y=ly + 5
        )
        teile.append(_el("g", inhalt, class_=f"gr-anb--{r['klasse']}"))
    return teile


def svg(daten: dict) -> Markup:
    """Die Pulskurve als Inline-SVG; Lücken sind beschriftete Flächen."""
    if not daten["wochen"] or not daten["reihen"]:
        return Markup("")
    hoechster = max(
        (v for r in daten["reihen"] for v in r["werte"] if v is not None), default=0
    )
    a = _Achsen(len(daten["wochen"]), (hoechster // 10 + 1) * 10)
    kopf = (
        f'<svg class="puls-svg" viewBox="0 0 {_BREITE} {_HOEHE}" role="img" '
        'aria-label="Meldungen je Kalenderwoche">'
    )
    teile = _raster(daten["wochen"], a) + _luecke(daten, a) + _linien(daten, a)
    return Markup(kopf + "".join(teile + _enden(daten, a)) + "</svg>")
