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

Stufe 2 (Angebotszählung im Browser, ``geraete_angebot``): trägt die Ebene
``kombinationen`` ein Soll der Art „browser_auswahl“, ist sie die Zeile: „Telekom:
1 240 von 1 262 Angeboten erfasst · 22 Lücken“; Modelle und Speicher stehen im
aufgeklappten Teil. „vollständig“ nur, wenn alle Angebote erfasst sind, keine Seite
ungezählt blieb und kein Ausfall vermerkt ist. Fehlt die Zählung des Tages, sagt die
Marke „Angebot heute nicht gezählt“, der Grund steht darunter.
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
ART_AUSWAHL = "browser_auswahl"
SATZ_ANGEBOTE = "{name}: {erfasst} von {soll} Angeboten erfasst"
HEUTE_NICHT = "Angebot heute nicht gezählt"
EBENE_SATZ = "{titel}: {erfasst} von {soll} erfasst"
EXTRA_ANGEBOTE = "Preise, die der Anbieter so nicht anbietet ({n}):"
OHNE_ANGEBOT = "{n} Preise, die der Anbieter so nicht anbietet"
GERAETE = " Angeboten erfasst ({gezaehlt} von {soll} Geräten gezählt)"
NICHT_VERGLICHEN = "{n} Preise nicht verglichen ({grund})"
KONKURRENZ_OFFEN = "Überschneidung mit anderen Läufen nicht prüfbar"
UEBERSICHT_OFFEN = "Übersicht nicht ganz gelesen"
AUSWAHL_OFFEN = "Auswahl nicht ganz gelesen"
LUECKEN_ZEIGEN = 40
"""Höchstzahl gezeigter Lücken je Anbieter; die Zahl steht immer vollständig."""
EXTRAS_ZEIGEN = 12
"""Beispiele erfasster Preise, die der Anbieter so nicht anbietet."""


def zahl(n: int | None) -> str:
    """„1 262“ mit schmalem geschütztem Leerzeichen als Tausendertrenner."""
    return "" if n is None else f"{n:,}".replace(",", "\u202f")


def _ist_angebot(z: dict) -> bool:
    k = (z.get("ebenen") or {}).get("kombinationen") or {}
    return (
        k.get("soll") is not None and (k.get("quelle") or {}).get("art") == ART_AUSWAHL
    )


def _ebene_satz(titel: str, e: dict) -> str:
    if e.get("soll") is None:
        return ""
    satz = EBENE_SATZ.format(
        titel=titel, erfasst=zahl(e.get("erfasst")), soll=zahl(e.get("soll"))
    )
    luecken = _luecken(e.get("luecken_zahl"))
    return f"{satz} · {luecken}" if luecken else satz


OHNE_GRUND = "ohne benannten Grund"


def _lesbare_luecke(luecke: dict) -> dict:
    if luecke.get("benannt"):
        return luecke
    return {**luecke, "grund": OHNE_GRUND}


KAUFWEGE = (
    "Tarifübersicht: {n} Tarife mit „Handy hinzufügen“ (anderer Kaufweg, nicht gezählt)"
)


def _kaufwege(herkunft: dict | None) -> str:
    tarife = ((herkunft or {}).get("tarifuebersicht") or {}).get("tarife")
    return KAUFWEGE.format(n=len(tarife)) if tarife else ""


def _hinweise(angebot: dict, k: dict) -> list[str]:
    uebersicht = angebot.get("uebersicht") or {}
    gruende: dict[str, int] = {}
    for e in k.get("nicht_verglichen") or ():
        gruende[str(e.get("grund"))] = gruende.get(str(e.get("grund")), 0) + 1
    konkurrenz = str(angebot.get("konkurrenz") or "")
    return [
        x
        for x in (
            ""
            if uebersicht.get("vollstaendig")
            else str(uebersicht.get("beleg") or UEBERSICHT_OFFEN),
            *list(angebot.get("unvollstaendig") or ())[:LUECKEN_ZEIGEN],
            *(NICHT_VERGLICHEN.format(n=zahl(n), grund=g) for g, n in gruende.items()),
            KONKURRENZ_OFFEN if konkurrenz.startswith("Prüfung auf parallele") else "",
        )
        if x
    ]


def _angebot_marken(z: dict, k: dict) -> list[str]:
    angebot = z.get("angebot") or {}
    extra = k.get("nicht_im_soll_zahl")
    marken = [
        x
        for x in (
            _luecken(k.get("luecken_zahl")),
            OHNE_ANGEBOT.format(n=zahl(extra)) if extra else "",
            ""
            if (angebot.get("uebersicht") or {}).get("vollstaendig")
            else UEBERSICHT_OFFEN,
            AUSWAHL_OFFEN if angebot.get("unvollstaendig") else "",
        )
        if x
    ]
    return marken if geraete_lauf.vorbehalte(z) else [VOLLSTAENDIG]


def angebot_zeile(z: dict) -> dict:
    """Die Anzeige einer Anbieterzeile mit Angebotszählung (Stufe 2): wichtigste
    Zahl sind die Angebote im gezählten Teil, immer mit dem Anteil gezählter Geräte
    („Telekom: 20 von 20 Angeboten erfasst (1 von 45 Geräten gezählt)“); „vollständig“
    nur ohne jeden Vorbehalt (``geraete_lauf.vorbehalte``)."""
    ebenen = z.get("ebenen") or {}
    k = ebenen["kombinationen"]
    angebot = z.get("angebot") or {}
    ausfall = str(z.get("ausfall") or "")
    extra = k.get("nicht_im_soll_zahl")
    geraete = angebot.get("geraete") or {}
    marken = _angebot_marken(z, k)
    luecken = list(k.get("luecken") or ())
    quelle = z.get("soll_quelle") or {}
    zahlen = f"{zahl(k.get('erfasst'))} von {zahl(k.get('soll'))}"
    hinten = GERAETE.format(
        gezaehlt=zahl(geraete.get("gezaehlt")), soll=zahl(geraete.get("soll"))
    )
    return {
        "name": z["name"],
        "vorne": f"{z['name']}: ",
        "zahl": zahlen,
        "hinten": hinten,
        "satz": f"{z['name']}: {zahlen}{hinten}",
        "ohne_soll": False,
        "soll": k.get("soll"),
        "erfasst": k.get("erfasst"),
        "ist": k.get("ist"),
        "grund": "",
        "marke": " · ".join(marken),
        "ausfall": ausfall,
        "offen": any(not lu.get("benannt") for lu in luecken),
        "luecken": [_lesbare_luecke(lu) for lu in luecken[:LUECKEN_ZEIGEN]],
        "ebenen_saetze": [
            s
            for s in (
                _ebene_satz("Modelle", ebenen.get("modelle") or {}),
                _ebene_satz("Speicher", ebenen.get("modell_speicher") or {}),
                _kaufwege(angebot.get("herkunft")),
            )
            if s
        ],
        "ungezaehlt": list(angebot.get("nicht_gezaehlt") or ())[:LUECKEN_ZEIGEN],
        "nicht_im_soll": EXTRA_ANGEBOTE.format(n=zahl(extra)) if extra else "",
        "extras": [_lesbare_luecke(e) for e in (k.get("nicht_im_soll") or ())][
            :EXTRAS_ZEIGEN
        ],
        "hinweise": _hinweise(angebot, k),
        "quelle_text": "Übersicht und Auswahl im Browser",
        "quelle_url": quelle.get("quelle") or "",
        "gleiche_quelle": "",
        "gezaehlt": _kurz(str((k.get("quelle") or {}).get("gezaehlt_um") or "")),
        "ebene": "angebote",
    }


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
    if _ist_angebot(z):
        return angebot_zeile(z)
    m = (z.get("ebenen") or {}).get("modelle") or {}
    quelle = z.get("soll_quelle") or {}
    gleich = quelle.get("gleiche_quelle_wie_sammler") is not False
    ausfall = str(z.get("ausfall") or "")
    ohne_soll = m.get("soll") is None
    luecken = list(m.get("luecken") or ())
    extra = m.get("nicht_im_soll_zahl")
    fehlt = (z.get("angebot") or {}).get("status") == "fehlt"
    marken = _marken(m, gleich, ausfall)
    if fehlt:
        marken = [x for x in marken if x != NICHT_GEZAEHLT] + [HEUTE_NICHT]
    marke = " · ".join(marken)
    k_grund = ((z.get("ebenen") or {}).get("kombinationen") or {}).get("soll_grund")
    return {
        "name": z["name"],
        "satz": _satz(z["name"], m, gleich),
        "ohne_soll": ohne_soll,
        "soll": m.get("soll"),
        "erfasst": m.get("erfasst"),
        "ist": m.get("ist"),
        "grund": k_grund if fehlt else (m.get("soll_grund") if ohne_soll else ""),
        "marke": marke,
        "ausfall": ausfall,
        "offen": any(not lu.get("benannt") for lu in luecken),
        "luecken": luecken,
        "nicht_im_soll": NICHT_IM_SOLL.format(n=extra) if extra else "",
        "quelle_text": ART.get(str(quelle.get("art")), ""),
        "quelle_url": quelle.get("quelle") or "",
        "gleiche_quelle": GLEICHE_QUELLE if quelle and gleich else "",
        "gezaehlt": _kurz(str(quelle.get("gezaehlt_um") or "")),
        "ebenen_saetze": [],
        "ungezaehlt": [],
        "extras": [],
        "hinweise": [],
        "ebene": "modelle",
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
    alle = list(voll.get("anbieter") or ())
    return {
        "fehlt": "",
        "stand": STAND.format(kurz=_kurz(datum)) if datum != stichtag else "",
        "zeilen": [zeile(z) for z in alle],
        "weitere": "" if any(_ist_angebot(z) for z in alle) else WEITERE,
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
