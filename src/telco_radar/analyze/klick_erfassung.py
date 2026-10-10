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
gestörter Lauf von heute gelesen hat (``speicher_gelesen``), den Satz „Bei Telekom nur
mit 256 GB gelesen (10.10.2026)“: ein Modell mit anderem Speicher fehlt dort, weil die
Übersicht je Gerät einen Speicher zeigt, nicht weil die Seite sperrt.
"""

from __future__ import annotations

import re
from datetime import date

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
TRENNER = "|"


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
    for eintrag in (bilanz or {}).get("dateien", []):
        if (satz := erfassungsgrund(eintrag)) is not None:
            gruende[str(eintrag.get("anbieter"))] = satz
        gruende.update(nicht_im_angebot(eintrag))
        gruende.update(speicher_gelesen(eintrag))
    return gruende


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
    """Je Gerät, das ein gestörter Lauf von heute gelesen hat, die gelesenen Speicher;
    ein Modell mit anderem Speicher zeigt sie statt des Anbietergrundes."""
    je_geraet = eintrag.get("speicher_gelesen")
    if erfassungsgrund(eintrag) is None or not isinstance(je_geraet, dict):
        return {}
    anbieter = str(eintrag.get("anbieter"))
    datum = date.fromisoformat(str(eintrag.get("datum"))).strftime("%d.%m.%Y")
    return {
        f"{anbieter}{TRENNER}{geraet}": SATZ_SPEICHER.format(
            anbieter=anbieter, speicher=_gb(speicher), datum=datum
        )
        for geraet, speicher in je_geraet.items()
    }


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


def fuer_modell(gruende: dict[str, str], modell: dict) -> dict[str, str]:
    """``ohne_karte`` für ein Modell der Geräteseite (Karten und Geräte-ID)."""
    return ohne_karte(gruende, modell.get("karten") or [], modell.get("device_id"))
