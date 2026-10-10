"""Die Meldungsseite als Magazin (Antonio, 10.10.2026).

Vorbild ist die Weltseite von The Atlantic: oben drei Spalten mit dem
Aufmacher in der Mitte, darunter eine Bildreihe, ein farbiger Schwerpunkt
je Thema, die uebrigen Meldungen als ruhige Liste und am Ende Deutschland.

Jede Meldung steht genau einmal im Lauf der Seite. Der Schwerpunkt
verweist nur auf Meldungen, die weiter oben oder unten vollstaendig
stehen; er zeigt keine eigene. Die Reihenfolge innerhalb jeder Position
ist die Dringlichkeit, die `_flatten()` gesetzt hat - hier wird nichts
neu bewertet, nur verteilt.
"""

from __future__ import annotations

from datetime import date

from .bilder import MIND_BREITE_GROSS

LINKS = 2
UNTER = 2
RECHTS = 5
REIHE = 4
SCHWERPUNKT_TIEFE = 5
SCHWERPUNKT_MIND = 3
STROM_SICHTBAR = 18
MIND_BREITE_SPALTE = 400
DEUTSCHLAND = "DE"


def _breite(h: dict) -> int:
    return int(h.get("image_w") or 0)


def deutsche_anbieter(cfg) -> set[str]:
    """Namen und Aliase der Anbieter mit `country: DE` aus der Watchlist."""
    if cfg is None:
        return set()
    namen: set[str] = set()
    for op in cfg.operators:
        if op.country == DEUTSCHLAND:
            namen.add(op.name)
            namen.update(op.aliases)
    return namen


def kalenderwoche(iso: str) -> int | None:
    """ISO-Kalenderwoche des Ausgabedatums; None, wenn es keins gibt."""
    try:
        return date.fromisoformat(str(iso)[:10]).isocalendar()[1]
    except ValueError:
        return None


def _schwerpunkte(meldungen: list[dict], aufmacher: dict | None) -> list[dict]:
    """Ein Schwerpunkt je Thema mit mindestens SCHWERPUNKT_MIND Meldungen.

    Zuerst steht das Thema mit den meisten Meldungen der Prioritaet 4 und 5,
    das nicht schon den Aufmacher stellt; die uebrigen folgen nach Zahl.
    """
    gruppen: dict[str, list[dict]] = {}
    for h in meldungen:
        gruppen.setdefault(h.get("ressort") or "vermischt", []).append(h)
    themen = [k for k, g in gruppen.items() if len(g) >= SCHWERPUNKT_MIND]

    def gewicht(k: str) -> tuple:
        wichtig = sum(1 for h in gruppen[k] if int(h.get("relevance") or 0) >= 4)
        eigen = aufmacher is not None and aufmacher.get("ressort") == k
        return (eigen, -wichtig, -len(gruppen[k]))

    erstes = sorted(themen, key=gewicht)[:1]
    rest = sorted(
        (k for k in themen if k not in erstes), key=lambda k: -len(gruppen[k])
    )
    out = []
    for k in erstes + rest:
        oben = gruppen[k][:SCHWERPUNKT_TIEFE]
        bild = next((h for h in oben if _breite(h) >= MIND_BREITE_GROSS), None)
        out.append(
            {
                "key": k,
                "label": oben[0].get("ressort_label") or k,
                "meldungen": oben,
                "bild": bild,
            }
        )
    return out


def ausgabe(kontext: dict | None, cfg) -> dict:
    """Verteilt die Meldungen der Ausgabe auf die Positionen der Seite."""
    kontext = kontext or {}
    alle = list(kontext.get("highlights") or [])
    de = deutsche_anbieter(cfg)
    deutschland = [h for h in alle if h.get("operator") in de]
    frei = [h for h in alle if h.get("operator") not in de]
    vergeben: set[int] = set()

    def nimm(n: int, passt=lambda h: True) -> list[dict]:
        out = [h for h in frei if id(h) not in vergeben and passt(h)][:n]
        vergeben.update(id(h) for h in out)
        return out

    oben = nimm(1, lambda h: _breite(h) >= MIND_BREITE_GROSS) or nimm(1)
    aufmacher = oben[0] if oben else None
    links = nimm(LINKS, lambda h: _breite(h) >= MIND_BREITE_SPALTE)
    unter = nimm(UNTER, lambda h: not h.get("image"))
    rechts = nimm(RECHTS)
    reihe = nimm(REIHE, lambda h: _breite(h) >= MIND_BREITE_SPALTE)
    strom = [h for h in frei if id(h) not in vergeben]
    return {
        "kw": kalenderwoche((kontext.get("report") or {}).get("date", "")),
        "aufmacher": aufmacher,
        "links": links,
        "unter": unter,
        "rechts": rechts,
        "reihe": reihe,
        "schwerpunkte": _schwerpunkte(frei, aufmacher),
        "strom": strom,
        "strom_sichtbar": STROM_SICHTBAR,
        "deutschland": deutschland,
    }
