"""Die Zeile „Vollständigkeit“ je Anbieter auf der Geräteseite (Abnahmekriterium 1).

Liest nur die fertigen Felder der Lauf-Datei (``geraete_lauf``; gerechnet in
``geraete_vollstaendigkeit``): „Telekom: 48 von 50 Modellen erfasst“, die Lücken mit
Grund zum Aufklappen, die Quelle des Solls. Rechnet nichts (Vertrag report-rechnet-nur).

Ein nicht zählbares Soll steht als „Angebot nicht zählbar“ mit seinem Grund da, nie als
100 %. Ohne Lauf-Datei (alter Stand) entsteht die Seite trotzdem und sagt, dass für den
Messtag keine Zählung vorliegt; eine unlesbare Datei ist zusätzlich ein Ausfall.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import geraete_lauf
from .ausfall import Ausfall

TEIL = "Vollständigkeit"
FEHLT = "Für den Messtag liegt keine Zählung der Vollständigkeit vor."
UNLESBAR = "Die Zählung der Vollständigkeit ist nicht lesbar."
GESCHEITERT = "Die Zählung der Vollständigkeit ist gescheitert."
SATZ = "{name}: {erfasst} von {soll} Modellen erfasst"
OHNE_SOLL = "{name}: Angebot nicht zählbar"
KEINE_ZEILE = "{name}: keine Zählung"
LUECKEN = {0: "vollständig", 1: "1 Lücke"}
LUECKEN_VIELE = "{n} Lücken"
STAND = "Stand vom {kurz}"
ART = {
    "sitemap": "Sitemap des Anbieters",
    "uebersichtsseite": "Übersichtsseite des Anbieters",
    "uebersicht_api": "Geräteliste des Shops",
}
GLEICHE_QUELLE = "dieselbe Liste liest auch die Messung"
NICHT_IM_SOLL = "{n} erfasste Modelle stehen nicht in dieser Liste"
WEITERE = "Speicher und Tarife werden noch nicht gegengezählt."


def _kurz(iso: str) -> str:
    teile = (iso or "")[:10].split("-")
    return f"{teile[2]}.{teile[1]}." if len(teile) == 3 else ""


def _marke(ebene: dict) -> str:
    n = ebene.get("luecken_zahl")
    if n is None:
        return ""
    return LUECKEN.get(n, LUECKEN_VIELE.format(n=n))


def zeile(z: dict) -> dict:
    """Die Anzeige einer Anbieterzeile aus der Lauf-Datei."""
    m = (z.get("ebenen") or {}).get("modelle") or {}
    quelle = z.get("soll_quelle") or {}
    ohne_soll = m.get("soll") is None
    satz = (
        OHNE_SOLL.format(name=z["name"])
        if ohne_soll
        else SATZ.format(name=z["name"], erfasst=m.get("erfasst"), soll=m.get("soll"))
    )
    luecken = list(m.get("luecken") or ())
    extra = m.get("nicht_im_soll_zahl")
    return {
        "name": z["name"],
        "satz": satz,
        "ohne_soll": ohne_soll,
        "soll": m.get("soll"),
        "erfasst": m.get("erfasst"),
        "grund": m.get("soll_grund") if ohne_soll else "",
        "marke": "" if ohne_soll else _marke(m),
        "offen": any(not lu.get("benannt") for lu in luecken),
        "luecken": luecken,
        "nicht_im_soll": NICHT_IM_SOLL.format(n=extra) if extra else "",
        "quelle_text": ART.get(str(quelle.get("art")), ""),
        "quelle_url": quelle.get("quelle") or "",
        "gleiche_quelle": GLEICHE_QUELLE
        if quelle.get("gleiche_quelle_wie_sammler")
        else "",
        "gezaehlt": _kurz(str(quelle.get("gezaehlt_um") or "")),
    }


def zeilen(lauf: dict | None, stichtag: str, unlesbar: bool = False) -> dict:
    """``{"fehlt", "stand", "zeilen", "weitere"}`` für die Vorlage."""
    if unlesbar:
        return {"fehlt": UNLESBAR, "stand": "", "zeilen": [], "weitere": ""}
    voll = (lauf or {}).get("vollstaendigkeit")
    if not isinstance(voll, dict):
        return {"fehlt": FEHLT, "stand": "", "zeilen": [], "weitere": ""}
    if voll.get("fehler"):
        return {"fehlt": GESCHEITERT, "stand": "", "zeilen": [], "weitere": ""}
    datum = str(voll.get("datum") or "")
    return {
        "fehlt": "",
        "stand": STAND.format(kurz=_kurz(datum)) if datum != stichtag else "",
        "zeilen": [zeile(z) for z in voll.get("anbieter") or ()],
        "weitere": WEITERE,
    }


def installiere(env: Any, state_dir: Path) -> list[Ausfall]:
    """Hängt ``vollstaendigkeit(stichtag)`` an die Jinja-Umgebung; gelesen wird die
    jüngste Lauf-Datei. Eine unlesbare Datei ist der Ausfall „Vollständigkeit“."""
    ausfaelle: list[Ausfall] = []
    lauf, unlesbar = None, False
    tag = geraete_lauf.juengster_tag(state_dir)
    if tag is not None:
        try:
            lauf = geraete_lauf.lies(state_dir, tag)
        except geraete_lauf.LaufDateiFehler as fehler:
            unlesbar = True
            ausfaelle.append(Ausfall(teil=TEIL, grund=str(fehler), satz=UNLESBAR))
    env.globals["vollstaendigkeit"] = lambda stichtag: zeilen(
        lauf, str(stichtag or ""), unlesbar
    )
    return ausfaelle
