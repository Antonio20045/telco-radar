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

Der Stichtag der Zukunftssperre ist der Messstichtag des Bestands (``geraete_view``:
das spätere von Berichtsdatum und ``updated`` der Bündeldatei), NICHT das Datum des
jüngsten Tagesberichts: die Geräte werden nachts nach dem Bericht gemessen und laufen
ihm regelmäßig um einen Tag voraus (Prüfung PR 68, 08.11.2026).

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
ANTEIL = "{n} von {m} Preisen von diesem Tag"

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


def juengster_tag(daten: Iterable, heute: str = "") -> str:
    """Der jüngste lesbare Tag aus ``daten`` (ISO), nicht nach ``heute``; sonst "".

    Ein unlesbarer oder zukünftiger Wert zählt nicht: er darf den Vergleichstag der
    Einzelgerät-Zellen nicht nach oben ziehen (``max`` über Strings täte es)."""
    tage = [t for t in (_lesbar(d, heute) for d in daten or ()) if t is not None]
    return max(tage).isoformat() if tage else ""


def _zahl(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _lang(tag: _dt.date) -> str:
    return f"{tag.day:02d}.{tag.month:02d}.{tag.year}"


def je_anbieter(
    buendel: Iterable[dict], heute: str = "", erwartet: tuple[str, ...] = ERWARTET
) -> dict:
    """``{"zeilen": [...], "juengster": iso}`` - eine Zeile je Anbieter.

    Zeile: ``name``, ``datum`` (ISO oder ""), ``satz`` (der Text der Seite), ``alt``
    (nicht vom jüngsten Messtag), ``stand`` („Stand vom TT.MM.“ oder "") und ``anteil``
    („n von m Preisen von diesem Tag“, "" ohne Messdatum)."""
    letzte: dict[str, _dt.date] = {}
    zahl: dict[str, dict[_dt.date | None, int]] = {}
    namen = list(erwartet)
    for b in buendel or ():
        b = b if isinstance(b, dict) else vars(b)
        name = b.get("anbieter") or ""
        if not name:
            continue
        if name not in namen:
            namen.append(name)
        tag = _lesbar(b.get("abgerufen_am"), heute)
        je_tag = zahl.setdefault(name, {})
        je_tag[tag] = je_tag.get(tag, 0) + 1
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
                    "anteil": "",
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
                "anteil": ANTEIL.format(
                    n=_zahl(zahl[name][tag]), m=_zahl(sum(zahl[name].values()))
                ),
            }
        )
    return {"zeilen": zeilen, "juengster": juengster.isoformat() if juengster else ""}


def stand_vom(abgerufen_am, juengster: str = "") -> str:
    """Der Chip einer Zeile: „Stand vom TT.MM.“, wenn ihre Messung nicht vom jüngsten
    Messtag stammt; sonst "". „Messdatum unbekannt“, wenn das Datum fehlt, unlesbar ist
    oder nach ``juengster`` liegt (Zukunft) oder wenn es keinen Vergleichstag gibt
    (``juengster`` leer): nie geraten. Vorlagen-Helfer der Tafel „Einzelgerät“
    (Bündelzeilen: ``geraete_preisstand``). ``juengster``: siehe ``juengster_tag``."""
    tag = _lesbar(abgerufen_am, "")
    bis = _lesbar(juengster, "")
    if tag is None or bis is None or tag > bis:
        return LUECKE
    if tag == bis:
        return ""
    return STAND.format(kurz=f"{tag.day:02d}.{tag.month:02d}.")


def felder(
    bestand: list, tco: dict, heute: str, tco_updated: str, bestand_heute: str
) -> dict:
    """Die Felder des ``geraete``-Views für Abrufdaten und Messdatum.

    ``abgerufen_ab``/``abgerufen_bis``: erstes und letztes Abrufdatum der Einzelgeräte
    (roh, wie bisher). ``einzel_stichtag``: der Vergleichstag der Einzelgerät-Zellen,
    nur lesbar und nicht nach ``bestand_heute``. ``messdatum``: die Anbieter-Zeile; ihr
    Stichtag ist der Messstichtag der Bündel (das spätere von ``heute`` und
    ``tco_updated``), nicht das Berichtsdatum ``heute`` allein."""
    daten = sorted(e.get("abgerufen_am") for e in bestand if e.get("abgerufen_am"))
    stichtag = max((t for t in (heute, tco_updated) if _lesbar(t, "")), default="")
    return {
        "abgerufen_bis": daten[-1] if daten else "",
        "abgerufen_ab": daten[0] if daten else "",
        "einzel_stichtag": juengster_tag(daten, bestand_heute),
        "messdatum": je_anbieter(
            (tco.get("export") or {}).get("buendel") or [], stichtag
        ),
    }
