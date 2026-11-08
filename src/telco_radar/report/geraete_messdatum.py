"""Das letzte Messdatum je Anbieter - die Zeile oben auf der Geräteseite.

Brief messdatum-0811 (Antonio, 08.11.2026 13:20): „Bei einigen Anbietern fehlen die
Werte von heute.“ Die Seite sagte nur „Stand 08.11.2026“ (der Tag der Berechnung) und
trug das Abrufdatum erst an der einzelnen Bündelzeile („Preis vom 07.11.2026“,
``geraete_preisstand.marke``). Hier steht es je Anbieter oben: „Telekom: zuletzt
gemessen am 07.11.2026“.

Das Messdatum eines Anbieters ist der jüngste lesbare ``abgerufen_am`` seiner Bündel.
Es wird nie geraten (Clean Code 4): ein fehlendes, unlesbares oder in der Zukunft
liegendes Datum heißt „Messdatum unbekannt“, nie das heutige. Ein Anbieter, dessen Datum
nicht dem jüngsten Messtag der Seite entspricht, trägt „Stand vom TT.MM.“.

``ERWARTET`` sind die Anbieter der Bündelseite in ihrer Reihenfolge; ein erwarteter
Anbieter ohne jedes Bündel steht als „Messdatum unbekannt“ da, statt zu fehlen.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Iterable

LUECKE = "Messdatum unbekannt"
SATZ = "{anbieter}: zuletzt gemessen am {datum}"
SATZ_LUECKE = "{anbieter}: " + LUECKE
STAND = "Stand vom {kurz}"

ERWARTET = ("Vodafone", "Telekom", "o2", "1&1", "congstar")


def _lesbar(iso, heute: str) -> _dt.date | None:
    """Das Datum, wenn es ein ISO-Tag ist und nicht nach ``heute`` liegt, sonst None."""
    try:
        tag = _dt.date.fromisoformat(str(iso or ""))
        grenze = _dt.date.fromisoformat(heute) if heute else None
    except (ValueError, TypeError):
        return None
    if grenze is not None and tag > grenze:
        return None
    return tag


def _lang(tag: _dt.date) -> str:
    return f"{tag.day:02d}.{tag.month:02d}.{tag.year}"


def je_anbieter(
    buendel: Iterable[dict], heute: str = "", erwartet: tuple[str, ...] = ERWARTET
) -> dict:
    """``{"zeilen": [...], "juengster": iso}`` - eine Zeile je Anbieter.

    Zeile: ``name``, ``datum`` (ISO oder ""), ``satz`` (der Text der Seite), ``alt``
    (nicht vom jüngsten Messtag) und ``stand`` („Stand vom TT.MM.“ oder "")."""
    letzte: dict[str, _dt.date] = {}
    namen = list(erwartet)
    for b in buendel or ():
        b = b if isinstance(b, dict) else vars(b)
        name = b.get("anbieter") or ""
        if not name:
            continue
        if name not in namen:
            namen.append(name)
        tag = _lesbar(b.get("abgerufen_am"), heute)
        if tag is not None and (name not in letzte or tag > letzte[name]):
            letzte[name] = tag
    juengster = max(letzte.values()) if letzte else None
    zeilen = []
    for name in namen:
        tag = letzte.get(name)
        if tag is None:
            zeilen.append(
                {
                    "name": name,
                    "datum": "",
                    "satz": SATZ_LUECKE.format(anbieter=name),
                    "alt": True,
                    "stand": "",
                }
            )
            continue
        alt = tag != juengster
        zeilen.append(
            {
                "name": name,
                "datum": tag.isoformat(),
                "satz": SATZ.format(anbieter=name, datum=_lang(tag)),
                "alt": alt,
                "stand": STAND.format(kurz=f"{tag.day:02d}.{tag.month:02d}.")
                if alt
                else "",
            }
        )
    return {"zeilen": zeilen, "juengster": juengster.isoformat() if juengster else ""}


def stand_vom(abgerufen_am, juengster: str = "") -> str:
    """Der Chip einer Zeile: „Stand vom TT.MM.“, wenn ihre Messung nicht vom jüngsten
    Messtag stammt; „Messdatum unbekannt“ ohne lesbares Datum; sonst "". Vorlagen-Helfer
    ``stand_vom`` der Tafel „Einzelgerät“ (Bündelzeilen: ``geraete_preisstand``)."""
    tag = _lesbar(abgerufen_am, "")
    if tag is None:
        return LUECKE
    bis = _lesbar(juengster, "")
    if bis is None or tag >= bis:
        return ""
    return STAND.format(kurz=f"{tag.day:02d}.{tag.month:02d}.")
