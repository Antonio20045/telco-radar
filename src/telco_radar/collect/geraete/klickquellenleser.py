"""Lader der zweiten Lesung: Quellen, Seitenwerte und Textmuster der Klick-Karte.

Ergänzt ``klickkartenleser`` um die Teile von Format 2, die ``klickkarte`` beschreibt:
``antwort`` als eine Quelle oder Liste von Quellen, ``seite`` mit benannten
Seitenwerten und ``zusammenfassung.muster`` je Wertfeld; ``pfade`` nennen dazu Nachweise
(``NACHWEISFELDER``), die nur die Antwort trägt. Jeder Pfad wird auf Form
(``klickpfad.pfadfehler``) und Platzhalter geprüft; ein Fehler wirft
``KlickkartenFehler`` mit Punktpfad. ``platzhalter`` einer Quelle sind benannte Pfade,
die nur die Platzhalter der Kombination tragen und keinen anderen Namen verdecken;
ihre Namen gelten in ``pfade`` und ``variante`` derselben Quelle. Die Pfade einer
``seitenwerte``-Quelle sind Namen aus ``seite``. Dieses Modul ruft kein Netz.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING

from .klickkartentypen import (
    BUENDELFELDER,
    DIMENSIONEN,
    EINHEITEN,
    ENTFALLEN_IM_BUENDEL,
    GRUND_EINE_QUELLE,
    GRUND_EINHEIT,
    GRUND_ENTFAELLT,
    GRUND_FEHLT,
    GRUND_KEINE_ZUORDNUNG,
    GRUND_NAME,
    GRUND_NUR_BUENDEL,
    GRUND_NUR_URL,
    GRUND_OHNE_VARIANTE,
    GRUND_PLATZHALTER,
    GRUND_SEITENWERT,
    GRUND_WAHRHEITSWERT,
    NACHWEISFELDER,
    PHASENFELD,
    PHASENTEILE,
    PLATZHALTER_MODELL,
    WERTFELDER,
    Antwortmuster,
    Phasenpfad,
    Seitenwert,
    Textmuster,
    Wertpfad,
)
from .klickpfad import pfadfehler, platzhalter

if TYPE_CHECKING:
    from .klickkartenleser import Kartenleser

QUELLENARTEN = ("url_muster", "skript", "global", "seitenwerte")
QUELLENTEILE = (
    *QUELLENARTEN,
    "laden",
    "start",
    "erkennung",
    "segment",
    "pfade",
    "variante",
    "parameter",
    "platzhalter",
)
WERTPFADTEILE = ("pfad", "muster", "einheit")
PARAMETERTEILE = ("name", "muster")
SEITENTEILE = ("selektor", "attribut", "parameter", "muster")
MUSTERTEILE = ("muster", "selektor")
GRUND_PFAD = "kein gültiger Pfad"
GRUND_GLOBAL = "kein Bezeichner einer globalen Variable"
GRUND_KEIN_SEITENWERT = "kein Seitenwert dieses Namens"
FELDER = (*WERTFELDER, *BUENDELFELDER)
ANTWORTFELDER = (*FELDER, *NACHWEISFELDER)
_NAME = re.compile(r"[a-z_][a-z0-9_]*")
_GLOBAL = re.compile(r"[A-Za-z_$][\w$]*")


def lies_quellen(
    leser: Kartenleser, roh: object, seite: Mapping[str, Seitenwert]
) -> tuple[Antwortmuster, ...]:
    """Die Quellen der zweiten Lesung; mindestens eine Dimension braucht ein Echo."""
    namen = {*DIMENSIONEN, PLATZHALTER_MODELL, *seite}
    if isinstance(roh, list):
        orte = [f"antwort.{n}" for n in range(len(leser.liste(roh, "antwort")))]
        quellen = tuple(
            _quelle(leser, e, o, namen) for e, o in zip(roh, orte, strict=True)
        )
    else:
        orte = ["antwort"]
        quellen = (_quelle(leser, roh, "antwort", namen),)
    for quelle, ort in zip(quellen, orte, strict=True):
        _pruefe_seitenquelle(leser, quelle, ort, seite)
    echo = any(q.variante or q.parameter for q in quellen)
    if not echo and not any(n in DIMENSIONEN for n in seite):
        raise leser.fehler(f"{orte[0]}.variante", GRUND_OHNE_VARIANTE)
    return quellen


def lies_seite(leser: Kartenleser, roh: object) -> dict[str, Seitenwert]:
    """Benannte Seitenwerte; ohne Feld keine."""
    if roh is None:
        return {}
    if not isinstance(roh, Mapping):
        raise leser.fehler("seite", GRUND_KEINE_ZUORDNUNG)
    werte = {}
    for name, eintrag in roh.items():
        feld = f"seite.{name}"
        if not _NAME.fullmatch(str(name)) or name == PLATZHALTER_MODELL:
            raise leser.fehler(feld, GRUND_NAME)
        daten = leser.zuordnung(eintrag, feld, SEITENTEILE)
        selektor = leser.wahlweise_text(daten, "selektor", feld)
        parameter = leser.wahlweise_text(daten, "parameter", feld)
        if selektor is None and parameter is None:
            raise leser.fehler(f"{feld}.selektor", GRUND_SEITENWERT)
        attribut = leser.wahlweise_text(daten, "attribut", feld)
        if attribut is not None and selektor is None:
            raise leser.fehler(f"{feld}.attribut", "nur mit selektor")
        muster = leser.wahlweise_muster(daten, "muster", feld)
        werte[str(name)] = Seitenwert(selektor, attribut, parameter, muster)
    return werte


def pruefe_felder(
    leser: Kartenleser, felder: Mapping[str, object], ort: str, ein_vertrag: bool
) -> None:
    """Bündelfelder nur bei ``ein_vertrag``; dort entfallen Rate und Ratenzahl."""
    for feld in felder:
        if feld in BUENDELFELDER and not ein_vertrag:
            raise leser.fehler(f"{ort}.{feld}", GRUND_NUR_BUENDEL)
        if feld in ENTFALLEN_IM_BUENDEL and ein_vertrag:
            raise leser.fehler(f"{ort}.{feld}", GRUND_ENTFAELLT)


def lies_textmuster(leser: Kartenleser, roh: object) -> dict[str, Textmuster]:
    """Fundort je Wertfeld im Text; ohne Feld keiner."""
    if roh is None:
        return {}
    ort = "zusammenfassung.muster"
    daten = leser.zuordnung(roh, ort, FELDER)
    muster = {}
    for feld in daten:
        if not isinstance(daten[feld], Mapping):
            muster[feld] = Textmuster(leser.muster(daten, feld, ort))
            continue
        teile = leser.zuordnung(daten[feld], f"{ort}.{feld}", MUSTERTEILE)
        muster[feld] = Textmuster(
            leser.muster(teile, "muster", f"{ort}.{feld}"),
            leser.wahlweise_text(teile, "selektor", f"{ort}.{feld}"),
        )
    return muster


def texte(
    leser: Kartenleser, daten: Mapping, schluessel: str, feld: str
) -> tuple[str, ...]:
    """Ein Text oder eine Liste von Texten an ``schluessel`` als Tupel."""
    wert = daten.get(schluessel)
    if not isinstance(wert, list):
        return (leser.text(daten, schluessel, feld),)
    ort = f"{feld}.{schluessel}"
    liste = leser.liste(wert, ort)
    return tuple(leser.text({str(n): e}, str(n), ort) for n, e in enumerate(liste))


def _quelle(
    leser: Kartenleser, roh: object, feld: str, namen: set[str]
) -> Antwortmuster:
    daten = leser.zuordnung(roh, feld, QUELLENTEILE)
    arten = [a for a in QUELLENARTEN if daten.get(a) is not None]
    if not arten:
        raise leser.fehler(f"{feld}.url_muster", GRUND_FEHLT)
    if len(arten) > 1:
        raise leser.fehler(f"{feld}.{arten[1]}", GRUND_EINE_QUELLE)
    url = leser.wahlweise_muster(daten, "url_muster", feld)
    for nur in ("laden", "segment"):
        if url is None and daten.get(nur) is not None:
            raise leser.fehler(f"{feld}.{nur}", GRUND_NUR_URL)
    pfade = leser.zuordnung(daten.get("pfade"), f"{feld}.pfade", ANTWORTFELDER)
    if not pfade:
        raise leser.fehler(f"{feld}.pfade", GRUND_FEHLT)
    erkennung = leser.wahlweise_text(daten, "erkennung", feld)
    if erkennung is not None:
        _pruefe_pfad(leser, erkennung, f"{feld}.erkennung", namen)
    platzhalter = _platzhalter(leser, daten, feld, namen)
    eigene = {*namen, *platzhalter}
    return Antwortmuster(
        url_muster=url,
        pfade={f: _feldpfad(leser, pfade, f, f"{feld}.pfade", eigene) for f in pfade},
        variante=_dimensionen(leser, daten, "variante", feld, eigene),
        parameter=_dimensionen(leser, daten, "parameter", feld, namen),
        skript=leser.wahlweise_text(daten, "skript", feld),
        globale=_globale(leser, daten, feld),
        seitenwerte=_wahrheitswert(leser, daten, "seitenwerte", feld),
        laden=_wahrheitswert(leser, daten, "laden", feld),
        start=_wahrheitswert(leser, daten, "start", feld),
        erkennung=erkennung,
        segment=leser.wahlweise_muster(daten, "segment", feld),
        platzhalter=platzhalter,
    )


def _pruefe_seitenquelle(
    leser: Kartenleser, quelle: Antwortmuster, ort: str, seite: Mapping[str, Seitenwert]
) -> None:
    """Jeder Pfad einer ``seitenwerte``-Quelle ist der Name eines Seitenwerts."""
    if not quelle.seitenwerte:
        return
    for feld, pfad in quelle.pfade.items():
        name = pfad if isinstance(pfad, str) else getattr(pfad, "pfad", None)
        if name not in seite:
            raise leser.fehler(f"{ort}.pfade.{feld}", GRUND_KEIN_SEITENWERT)


def _platzhalter(
    leser: Kartenleser, daten: Mapping, feld: str, namen: set[str]
) -> dict[str, str]:
    """Benannte Pfade der Quelle; ein Name verdeckt keinen anderen Platzhalter."""
    roh = daten.get("platzhalter")
    if roh is None:
        return {}
    ort = f"{feld}.platzhalter"
    if not isinstance(roh, Mapping) or not roh:
        raise leser.fehler(ort, GRUND_KEINE_ZUORDNUNG)
    pfade = {}
    for name in roh:
        stelle = f"{ort}.{name}"
        if not _NAME.fullmatch(str(name)) or name in namen:
            raise leser.fehler(stelle, GRUND_NAME)
        pfad = leser.text(roh, name, ort)
        _pruefe_pfad(leser, pfad, stelle, namen)
        pfade[str(name)] = pfad
    return pfade


def _globale(leser: Kartenleser, daten: Mapping, feld: str) -> tuple[str, ...]:
    if daten.get("global") is None:
        return ()
    namen = texte(leser, daten, "global", feld)
    for name in namen:
        if not _GLOBAL.fullmatch(name):
            raise leser.fehler(f"{feld}.global", f"{GRUND_GLOBAL}: {name}")
    return namen


def _wahrheitswert(
    leser: Kartenleser, daten: Mapping, schluessel: str, feld: str
) -> bool:
    wert = daten.get(schluessel)
    if wert is None:
        return False
    if not isinstance(wert, bool):
        raise leser.fehler(f"{feld}.{schluessel}", GRUND_WAHRHEITSWERT)
    return wert


def _dimensionen(
    leser: Kartenleser, daten: Mapping, schluessel: str, feld: str, namen: set[str]
) -> dict[str, str | Wertpfad]:
    if daten.get(schluessel) is None:
        return {}
    ort = f"{feld}.{schluessel}"
    zuordnung = leser.zuordnung(daten[schluessel], ort, DIMENSIONEN)
    teile = WERTPFADTEILE[:2] if schluessel == "variante" else PARAMETERTEILE
    return {d: _wertpfad(leser, zuordnung, d, ort, namen, teile) for d in zuordnung}


def _feldpfad(
    leser: Kartenleser, pfade: Mapping, feld: str, ort: str, namen: set[str]
) -> str | Wertpfad | Phasenpfad:
    roh = pfade.get(feld)
    if feld == PHASENFELD and isinstance(roh, Mapping) and "pfad" not in roh:
        stelle = f"{ort}.{feld}"
        teile = leser.zuordnung(roh, stelle, PHASENTEILE)
        liste, von, bis, betrag = (leser.text(teile, t, stelle) for t in PHASENTEILE)
        for teil, pfad in zip(PHASENTEILE, (liste, von, bis, betrag), strict=True):
            _pruefe_pfad(leser, pfad, f"{stelle}.{teil}", namen)
        return Phasenpfad(liste=liste, von=von, bis=bis, betrag=betrag)
    return _wertpfad(leser, pfade, feld, ort, namen, WERTPFADTEILE)


def _wertpfad(
    leser: Kartenleser,
    daten: Mapping,
    schluessel: str,
    ort: str,
    namen: set[str],
    teile: tuple[str, ...],
) -> str | Wertpfad:
    stelle = f"{ort}.{schluessel}"
    if not isinstance(daten.get(schluessel), Mapping):
        pfad = leser.text(daten, schluessel, ort)
        if teile != PARAMETERTEILE:
            _pruefe_pfad(leser, pfad, stelle, namen)
        return pfad
    eintrag = leser.zuordnung(daten[schluessel], stelle, teile)
    pfad = leser.text(eintrag, teile[0], stelle)
    if teile != PARAMETERTEILE:
        _pruefe_pfad(leser, pfad, f"{stelle}.{teile[0]}", namen)
    einheit = leser.wahlweise_text(eintrag, "einheit", stelle)
    if einheit is not None and einheit not in EINHEITEN:
        raise leser.fehler(f"{stelle}.einheit", f"{GRUND_EINHEIT} {einheit}")
    muster = leser.wahlweise_muster(eintrag, "muster", stelle)
    return Wertpfad(pfad=pfad, muster=muster, einheit=einheit)


def _pruefe_pfad(leser: Kartenleser, pfad: str, ort: str, namen: set[str]) -> None:
    grund = pfadfehler(pfad)
    if grund is not None:
        raise leser.fehler(ort, f"{GRUND_PFAD} ({grund})")
    for name in platzhalter(pfad):
        if name not in namen:
            raise leser.fehler(ort, f"{GRUND_PLATZHALTER} {{{name}}}")
