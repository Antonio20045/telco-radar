"""Die Zeile „Vollständigkeit“ je Anbieter auf der Geräteseite (Abnahmekriterium 1).

Liest nur die fertigen Felder der Lauf-Datei (``geraete_lauf``; gerechnet in
``geraete_vollstaendigkeit``), die Lücken mit Grund zum Aufklappen, die Quelle des
Solls. Rechnet nichts (Vertrag report-rechnet-nur). Die Zeile sagt nie mehr, als die
Zahl trägt (Prüfung PR 201):

* Soll aus einer Liste, die auch die Messung liest: „o2: 63 von 63 Modellen der
  Anbieterliste erfasst · Liste nicht unabhängig“, nie „vollständig“.
* Kein Soll: „Telekom: 53 Modelle erfasst · Angebot noch nicht gezählt“, Grund im
  aufgeklappten Teil; nie als 100 %.
* „vollständig“ nur bei unabhängigem Soll ohne Lücke und ohne Ausfallvermerk.
* Ein Ausfallvermerk des Laufs (``ausfall``) steht sichtbar unter der Zeile.

Ohne Lauf-Datei (alter Stand) entsteht die Seite trotzdem und sagt, dass für den
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
SATZ_LISTE = "{name}: {erfasst} von {soll} Modellen der Anbieterliste erfasst"
OHNE_SOLL = "{name}: {ist} Modelle erfasst"
NICHT_GEZAEHLT = "Angebot noch nicht gezählt"
NICHT_UNABHAENGIG = "Liste nicht unabhängig"
VOLLSTAENDIG = "vollständig"
LUECKEN = {1: "1 Lücke"}
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


def _luecken(n: int | None) -> str:
    if not n:
        return ""
    return LUECKEN.get(n, LUECKEN_VIELE.format(n=n))


def _marken(m: dict, gleich: bool, ausfall: str) -> list[str]:
    if m.get("soll") is None:
        return [NICHT_GEZAEHLT]
    luecken = _luecken(m.get("luecken_zahl"))
    if gleich:
        return [x for x in (luecken, NICHT_UNABHAENGIG) if x]
    if luecken:
        return [luecken]
    return [] if ausfall else [VOLLSTAENDIG]


def _satz(name: str, m: dict, gleich: bool) -> str:
    if m.get("soll") is None:
        return OHNE_SOLL.format(name=name, ist=m.get("ist"))
    muster = SATZ_LISTE if gleich else SATZ
    return muster.format(name=name, erfasst=m.get("erfasst"), soll=m.get("soll"))


def zeile(z: dict) -> dict:
    """Die Anzeige einer Anbieterzeile aus der Lauf-Datei."""
    m = (z.get("ebenen") or {}).get("modelle") or {}
    quelle = z.get("soll_quelle") or {}
    gleich = quelle.get("gleiche_quelle_wie_sammler") is not False
    ausfall = str(z.get("ausfall") or "")
    ohne_soll = m.get("soll") is None
    luecken = list(m.get("luecken") or ())
    extra = m.get("nicht_im_soll_zahl")
    return {
        "name": z["name"],
        "satz": _satz(z["name"], m, gleich),
        "ohne_soll": ohne_soll,
        "soll": m.get("soll"),
        "erfasst": m.get("erfasst"),
        "ist": m.get("ist"),
        "grund": m.get("soll_grund") if ohne_soll else "",
        "marke": " · ".join(_marken(m, gleich, ausfall)),
        "ausfall": ausfall,
        "offen": any(not lu.get("benannt") for lu in luecken),
        "luecken": luecken,
        "nicht_im_soll": NICHT_IM_SOLL.format(n=extra) if extra else "",
        "quelle_text": ART.get(str(quelle.get("art")), ""),
        "quelle_url": quelle.get("quelle") or "",
        "gleiche_quelle": GLEICHE_QUELLE if quelle and gleich else "",
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
