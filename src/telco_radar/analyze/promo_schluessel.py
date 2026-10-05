"""Schlüssel und ID eines Promo-Angebots, Migration alter promo_db.json-Einträge.

Die ID kommt aus Marke, Zielseite, Konditionen (alle Zahlen der Beschreibung)
und einer Laufnummer, nie aus der Überschrift: eine Umformulierung ändert den
Titel, nicht das Angebot.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

from ..models import normalize_url

ID_FELD = "idSchluessel"
ID_SCHLUESSEL = "marke-zielseite-konditionen"
"""Kennzeichen einer promo_db.json, deren IDs schon aus dem Schlüssel stammen."""

_TAUSENDERPUNKT = re.compile(r"(?<=\d)\.(?=\d{3}(?!\d))")
_DEZIMALKOMMA = re.compile(r"(?<=\d),(?=\d)")
_ZAHL = re.compile(r"\d+(?:\.\d+)?")

Schluessel = tuple[str, str, tuple[str, ...]]


def entry_id(brand: str, headline: str) -> str:
    """Alte ID aus Marke und Überschrift, nur für Bestand ohne ``id``."""
    basis = (
        f"{(brand or '').strip().lower()}|{' '.join((headline or '').lower().split())}"
    )
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def _text(wert: object) -> str:
    """Ein Feld als Text; fehlend ist leer."""
    return "" if wert is None else str(wert)


def _ohne_nullen(zahl: str) -> str:
    """149.00 wird 149, 9.50 wird 9.5, 05 wird 5."""
    ganz, _, rest = zahl.partition(".")
    ganz = ganz.lstrip("0") or "0"
    rest = rest.rstrip("0")
    return f"{ganz}.{rest}" if rest else ganz


def konditionen(beschreibung: str | None) -> tuple[str, ...]:
    """Die Menge aller Zahlen einer Beschreibung, sortiert."""
    text = unicodedata.normalize("NFKC", _text(beschreibung))
    text = _DEZIMALKOMMA.sub(".", _TAUSENDERPUNKT.sub("", text))
    return tuple(sorted({_ohne_nullen(z) for z in _ZAHL.findall(text)}))


def zielseite(url: str | None, source_url: str | None) -> str:
    """Normalisierte Zielseite; ohne eigenen Link die gelesene Seite."""
    roh = _text(url).strip() or _text(source_url).strip()
    return normalize_url(roh) if roh else ""


def schluessel(
    brand: str | None,
    url: str | None,
    source_url: str | None,
    beschreibung: str | None,
) -> Schluessel:
    """Marke, Zielseite und Konditionen eines Angebots."""
    return (
        _text(brand).strip().lower(),
        zielseite(url, source_url),
        konditionen(beschreibung),
    )


def schluessel_eintrag(e: dict) -> Schluessel:
    """Schlüssel eines gespeicherten Eintrags nach seinen jetzigen Feldern."""
    return schluessel(
        e.get("brand"), e.get("url"), e.get("source_url"), e.get("description")
    )


def id_aus_schluessel(stamm: Schluessel, laufnummer: int) -> str:
    """sha1 aus Marke, Zielseite, Konditionen und Laufnummer, 16 Hexzeichen."""
    marke, seite, zahlen = stamm
    basis = f"{marke}|{seite}|{','.join(zahlen)}|{laufnummer}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def rang(e: dict) -> tuple[bool, str]:
    """Aktiv vor nicht aktiv, dann der zuletzt bestätigte."""
    return e.get("status") == "aktiv", _text(e.get("last_verified"))


def migriere(roh: list[dict]) -> dict[str, dict]:
    """Legt Einträge mit gleichem Schlüssel zusammen, ohne etwas zu schreiben.

    Gleichzeitig gelesen (gleicher Schlüssel, first_seen und source_url) bleibt
    getrennt über die Laufnummer, vergeben nach alter ID. Es gewinnt der jüngere
    last_verified, dann der jüngere first_seen, dann die kleinere alte ID; die
    übrigen stehen in seinem Feld verlauf, alle alten IDs in alteIds.
    """
    alt: list[tuple[str, dict]] = []
    for e in roh:
        eid = e.get("id") or entry_id(e.get("brand", ""), e.get("headline", ""))
        if eid:
            alt.append((eid, e))
    alt.sort(key=lambda p: p[0])
    laeufe: dict[tuple[Schluessel, str, str], int] = {}
    gruppen: dict[str, list[tuple[str, dict]]] = {}
    for eid, e in alt:
        stamm = schluessel_eintrag(e)
        lauf = (stamm, _text(e.get("first_seen")), _text(e.get("source_url")))
        laeufe[lauf] = laeufe.get(lauf, 0) + 1
        gruppen.setdefault(id_aus_schluessel(stamm, laeufe[lauf]), []).append((eid, e))
    eintraege: dict[str, dict] = {}
    for neue_id, mitglieder in gruppen.items():
        _, gewinner = max(
            mitglieder,
            key=lambda p: (
                _text(p[1].get("last_verified")),
                _text(p[1].get("first_seen")),
            ),
        )
        eintrag = dict(gewinner)
        eintrag["id"] = neue_id
        eintrag["alteIds"] = [eid for eid, _ in mitglieder]
        eintrag["verlauf"] = [
            *(gewinner.get("verlauf") or []),
            *(e for _, e in mitglieder if e is not gewinner),
        ]
        eintraege[neue_id] = eintrag
    return eintraege
