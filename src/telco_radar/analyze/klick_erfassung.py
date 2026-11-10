"""Der Erfassungsgrund eines gestörten Klick-Laufs für die Geräteseite.

Grundlage ist der Bilanzeintrag einer Klick-Ergebnisdatei (``klick_zusammenfuehrung``,
``bilanz["dateien"]``). Ein Lauf mit Status ``gestoert``, jünger als
``FRISCHEGRENZE_TAGE``, ergibt je Anbieter einen Satz wie „Telekom nicht erfasst:
Seite sperrt automatisches Lesen (HTTP 202, 08.10.2026)“; Anbieter, HTTP-Status und
Datum stammen aus der Datei. HTTP 202, 4xx oder eine Challenge heißen Sperre, alles
andere Störung. Ein gelesener, veralteter oder datumloser Lauf hat keinen Grund.

Trägt der Eintrag einer Datei von heute ``nicht_im_angebot`` (``klickrohsatz``: alle
Übersichten ganz gelesen, das Gerät in keiner), bekommt jedes dieser Geräte den Satz
„Bei Telekom nicht im Angebot (Übersicht vom 09.10.2026 ganz gelesen)“ unter dem
Schlüssel ``Anbieter|device_id`` (``TRENNER``); ``fuer_modell`` gibt ihn dem Modell
mit dieser Geräte-ID statt eines Anbietergrundes. Ebenso bekommt jedes Gerät, das ein
Lauf von heute gelesen hat (``speicher_gelesen``), gestört oder nicht, den Satz „Bei
Telekom nur mit 256 GB gelesen (10.10.2026)“: ein Modell mit anderem Speicher fehlt
dort, weil die Übersicht je Gerät einen Speicher zeigt, nicht weil die Seite sperrt.

Diese drei Sätze sind Lückenbelege und gelten nur mit Datum, höchstens
``BELEG_MAX_TAGE`` alt (``beleg_gilt``), und nur ohne Widerspruch des Radars
(``Neugeraete``: lieferbares Neugerät derselben Kombination). „Nur mit … im Angebot“
braucht zusätzlich eine Seite, die eine gesperrte Option von einer Option in anderer
Farbe unterscheidet (``sperre_eindeutig``): Telekom las das Pixel 11 in Frost, dort ist
512 GB gesperrt, in Obsidian bestellbar (Stichprobe 10.11.2026). Was daran fehlt, ist
eine Messlücke („nur … gelesen“, „Noch nicht erfasst“), keine Portfolio-Lücke.
"""

from __future__ import annotations

import re
from datetime import date
from typing import NamedTuple

from ..klick_vertrag import (
    CHALLENGE_STATUS,
    FEHLER_AB_STATUS,
    FRISCHEGRENZE_TAGE,
    LAUF_GESTOERT,
)

SATZ = "{anbieter} nicht erfasst: {art} ({angaben})"
ART_SPERRE = "Seite sperrt automatisches Lesen"
ART_STOERUNG = "Lesen gestört"
SERVERFEHLER_AB = 500
CHALLENGE = "Challenge"
_HTTP = re.compile(r"HTTP (\d{3})")
SATZ_NICHT_IM_ANGEBOT = (
    "Bei {anbieter} nicht im Angebot (Übersicht vom {datum} ganz gelesen)"
)
SATZ_SPEICHER = "Bei {anbieter} nur mit {speicher} gelesen ({datum})"
SATZ_SPEICHER_ANGEBOT = "Bei {anbieter} nur mit {speicher} im Angebot ({datum})"
TRENNER = "|"
BELEG_MAX_TAGE = FRISCHEGRENZE_TAGE
"""Höchstalter eines Lückenbelegs in Tagen (ausschließlich): so lange gilt auch die
Klick-Datei, aus der er stammt; ein älterer Satz stand ohne neue Lesung im Bestand."""
GESPERRT = "gesperrt"
OFFEN = "offen"
"""Schlüssel von ``speicher_seite`` (``klick_teillauf``): gesperrt gezeigte Speicher
und solche, die eine gelesene Seite weder gesperrt zeigte noch erfasste."""
Angebot = dict[str, dict[str, set[int]]]
"""Je Anbieter und Gerät die angebotenen Speicher (``angebotene_speicher``)."""


def erfassungsgrund(eintrag: dict) -> str | None:
    """Der Satz zu einem Bilanzeintrag, ``None`` ohne frische Störung."""
    alter = eintrag.get("alter_tage")
    if eintrag.get("laufstatus") != LAUF_GESTOERT or alter is None:
        return None
    if not 0 <= alter < FRISCHEGRENZE_TAGE:
        return None
    grund = str(eintrag.get("grund") or "")
    treffer = _HTTP.search(grund)
    status = int(treffer[1]) if treffer else None
    gesperrt = status == CHALLENGE_STATUS or (
        status is not None and FEHLER_AB_STATUS <= status < SERVERFEHLER_AB
    )
    datum = date.fromisoformat(str(eintrag.get("datum"))).strftime("%d.%m.%Y")
    angaben = datum if status is None else f"HTTP {status}, {datum}"
    return SATZ.format(
        anbieter=eintrag.get("anbieter"),
        art=ART_SPERRE if gesperrt or CHALLENGE in grund else ART_STOERUNG,
        angaben=angaben,
    )


def erfassungsgruende(bilanz: dict | None) -> dict[str, str]:
    """Je Anbieter mit frisch gestörtem Klick-Lauf sein Erfassungsgrund."""
    gruende = {}
    dateien = (bilanz or {}).get("dateien", [])
    for eintrag in dateien:
        if (satz := erfassungsgrund(eintrag)) is not None:
            gruende[str(eintrag.get("anbieter"))] = satz
        gruende.update(nicht_im_angebot(eintrag))
    for eintrag in je_anbieter_vereint(dateien):
        gruende.update(speicher_gelesen(eintrag))
    return gruende


def angebotene_speicher(
    listungen: list[dict], gelesen: set[str], heute: str
) -> Angebot:
    """Je Anbieter, dessen Geräteliste heute ganz gelesen wurde (``gelesen``), und
    Gerät die Speicher seiner heute gesehenen, aktiven Neugeräte."""
    angebot: Angebot = {}
    for x in listungen:
        anbieter, speicher = str(x.get("anbieter")), x.get("speicher_gb")
        if (
            anbieter not in gelesen
            or x.get("status") != "aktiv"
            or x.get("zustand", "neu") != "neu"
            or x.get("last_verified") != heute
            or not isinstance(speicher, int)
        ):
            continue
        geraete = angebot.setdefault(anbieter, {})
        geraete.setdefault(str(x.get("device_id")), set()).add(speicher)
    return angebot


def je_anbieter_vereint(dateien: list[dict]) -> list[dict]:
    """Heutige Dateien eines Anbieters (ein Anbieter auf mehrere Jobs verteilt) mit
    vereinten ``speicher_gelesen``; ältere Dateien unverändert."""
    vereint: dict[str, dict] = {}
    rest = []
    for eintrag in dateien:
        je_geraet = eintrag.get("speicher_gelesen")
        if eintrag.get("alter_tage") != 0 or not isinstance(je_geraet, dict):
            rest.append(eintrag)
            continue
        ziel = vereint.setdefault(
            str(eintrag.get("anbieter")),
            {**eintrag, "speicher_gelesen": {}, "speicher_seite": {}},
        )
        ziel["sperre_eindeutig"] = bool(
            ziel.get("sperre_eindeutig") and eintrag.get("sperre_eindeutig")
        )
        for geraet, speicher in je_geraet.items():
            bisher = ziel["speicher_gelesen"].get(geraet, [])
            ziel["speicher_gelesen"][geraet] = sorted({*bisher, *speicher})
        for geraet, arten in (eintrag.get("speicher_seite") or {}).items():
            bisher = ziel["speicher_seite"].setdefault(geraet, {})
            for art, speicher in arten.items():
                bisher[art] = sorted({*bisher.get(art, []), *speicher})
    return [*rest, *vereint.values()]


def nicht_im_angebot(eintrag: dict) -> dict[str, str]:
    """Je Gerät außerhalb ganz gelesener Übersichten von heute sein Satz."""
    geraete = eintrag.get("nicht_im_angebot")
    if eintrag.get("alter_tage") != 0 or not isinstance(geraete, list):
        return {}
    anbieter = str(eintrag.get("anbieter"))
    datum = date.fromisoformat(str(eintrag.get("datum"))).strftime("%d.%m.%Y")
    satz = SATZ_NICHT_IM_ANGEBOT.format(anbieter=anbieter, datum=datum)
    return {f"{anbieter}{TRENNER}{g}": satz for g in geraete}


def speicher_gelesen(eintrag: dict) -> dict[str, str]:
    """Je Gerät, das ein Lauf von heute gelesen hat, die gelesenen Speicher; ein
    Modell mit anderem Speicher zeigt sie statt des Anbietergrundes oder der Lücke.
    Nur wenn die Seite selbst jeden übrigen Speicher gesperrt zeigt (``seite_belegt``),
    heißt es „nur mit … im Angebot“. Die Geräteliste belegt das nicht: o2 führte das
    iPhone 17 Pro am 12.10.2026 nur mit 256 GB, die Klick-Seite las 512 GB."""
    je_geraet = eintrag.get("speicher_gelesen")
    if eintrag.get("alter_tage") != 0 or not isinstance(je_geraet, dict):
        return {}
    anbieter = str(eintrag.get("anbieter"))
    datum = date.fromisoformat(str(eintrag.get("datum"))).strftime("%d.%m.%Y")
    saetze = {}
    for geraet, speicher in je_geraet.items():
        belegt = seite_belegt(eintrag, geraet, speicher)
        satz = SATZ_SPEICHER_ANGEBOT if belegt else SATZ_SPEICHER
        saetze[f"{anbieter}{TRENNER}{geraet}"] = satz.format(
            anbieter=anbieter, speicher=_gb(speicher), datum=datum
        )
    return saetze


def seite_belegt(eintrag: dict, geraet: str, gelesen: list[int]) -> bool:
    """Die Seiten von heute zeigen mindestens einen Speicher gesperrt und jeden nicht
    gelesenen entweder gesperrt oder gar nicht (``klick_teillauf.speicher_seite``).
    Nur wenn die Karte der Seite „gesperrt“ von „nur in anderer Farbe“ unterscheidet
    (``sperre_eindeutig``, ``klick_zusammenfuehrung``); sonst gesperrt in der gelesenen
    Farbe, und die Seite kann den Speicher in einer anderen führen."""
    if not eintrag.get("sperre_eindeutig"):
        return False
    arten = (eintrag.get("speicher_seite") or {}).get(geraet) or {}
    offen = set(arten.get(OFFEN) or []) - set(gelesen)
    return bool(arten.get(GESPERRT)) and not offen


def _gb(speicher: list[int]) -> str:
    texte = [f"{gb // 1024} TB" if gb >= 1024 else f"{gb} GB" for gb in speicher]
    return " und ".join([", ".join(texte[:-1]), texte[-1]] if len(texte) > 1 else texte)


def ohne_karte(
    gruende: dict[str, str], karten: list[dict], device_id: str | None = None
) -> dict[str, str]:
    """Die Gründe der Anbieter ohne Karte mit Betrag im Modell: wer die Seite gelesen
    hat, zeigt seine Zeile statt des Grundes; ein Platzhalter zählt nicht. Ein Satz
    zum Gerät ``device_id`` geht dem Grund seines Anbieters vor."""
    mit_karte = {k.get("anbieter") for k in karten if k.get("gesamt") is not None}
    eigene = {a: s for a, s in gruende.items() if TRENNER not in a}
    for schluessel, satz in gruende.items():
        anbieter, _, geraet = schluessel.partition(TRENNER)
        if geraet and geraet == device_id:
            eigene[anbieter] = satz
    return {a: satz for a, satz in eigene.items() if a not in mit_karte}


class Neugeraete(NamedTuple):
    """Lieferbare, frische Neugeräte des Radars: (Anbieter, Gerät) und
    (Anbieter, Gerät, Speicher in GB)."""

    geraet: frozenset[tuple[str, str]] = frozenset()
    speicher: frozenset[tuple[str, str, int]] = frozenset()


KEINE_NEUGERAETE = Neugeraete()
_LUECKEN_ART = {
    SATZ_NICHT_IM_ANGEBOT: "geraet",
    SATZ_SPEICHER_ANGEBOT: "speicher",
    SATZ_SPEICHER: "speicher",
}
_FELD = {
    "{anbieter}": ".+",
    "{speicher}": ".+",
    "{datum}": r"(?P<datum>\d{2}\.\d{2}\.\d{4})",
}


def _muster(vorlage: str) -> re.Pattern[str]:
    text = re.escape(vorlage)
    for feld, regel in _FELD.items():
        text = text.replace(re.escape(feld), regel)
    return re.compile(text)


_LUECKEN_MUSTER = [(_muster(v), art) for v, art in _LUECKEN_ART.items()]


def lueckenbeleg(satz: str) -> tuple[str, date | None] | None:
    """Art (``geraet``: Gerät nicht im Angebot, ``speicher``: Speicher) und Datum eines
    Satzes, der eine Lücke behauptet; ``None`` für jeden anderen Satz (Störung). Das
    Datum ist ``None``, wenn es kein Tag ist."""
    for muster, art in _LUECKEN_MUSTER:
        if treffer := muster.fullmatch(satz):
            tag, monat, jahr = (int(t) for t in treffer["datum"].split("."))
            try:
                return art, date(jahr, monat, tag)
            except ValueError:
                return art, None
    return None


def beleg_gilt(satz: str, heute: str | None) -> bool:
    """Ein Lückenbeleg gilt mit Datum von heute bis höchstens ``BELEG_MAX_TAGE`` vorher
    (ausschließlich); ohne Datum, aus der Zukunft oder ohne bekannten Stichtag nicht.
    ``heute=None``: Aufrufer ohne Uhr, nur Tests. Andere Sätze gelten immer."""
    beleg = lueckenbeleg(satz)
    if beleg is None or heute is None:
        return True
    try:
        stichtag = date.fromisoformat(heute)
    except ValueError:
        return False
    return beleg[1] is not None and 0 <= (stichtag - beleg[1]).days < BELEG_MAX_TAGE


def widerspricht(
    satz: str, anbieter: str, geraet: str | None, speicher: int | None, neu: Neugeraete
) -> bool:
    """Der Radar führt für dieselbe Kombination selbst ein lieferbares Neugerät: der
    Lückensatz ist dann kein Beleg (Messlücke). „Nicht im Angebot“ meint das Gerät,
    jeder Speichersatz den Speicher dieses Modells."""
    beleg = lueckenbeleg(satz)
    if beleg is None or geraet is None:
        return False
    if beleg[0] == "geraet":
        return (anbieter, geraet) in neu.geraet
    return (anbieter, geraet, speicher) in neu.speicher


def fuer_modell(
    gruende: dict[str, str],
    modell: dict,
    heute: str | None = None,
    neu: Neugeraete = KEINE_NEUGERAETE,
) -> dict[str, str]:
    """``ohne_karte`` für ein Modell der Geräteseite (Karten und Geräte-ID), ohne
    Lückenbelege, die nicht mehr gelten (``beleg_gilt``) oder denen der Radar
    widerspricht (``widerspricht``)."""
    geraet, speicher = modell.get("device_id"), modell.get("speicher")
    eigene = ohne_karte(gruende, modell.get("karten") or [], geraet)
    return {
        a: satz
        for a, satz in eigene.items()
        if beleg_gilt(satz, heute) and not widerspricht(satz, a, geraet, speicher, neu)
    }
