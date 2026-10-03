"""Zwischenspeicher der Wächter je Dateiinhalt, nur für die schnelle Leiter.

Ein Eintrag gilt für Art, Pfad und sha256 des Inhalts und nur, solange die Quelltexte
der Wächter unverändert sind. Ohne ``aktiv`` rechnet jede Prüfung neu; ``--voll``
nutzt den Speicher nie.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
from collections.abc import Callable, Iterator
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

_ORDNER = Path(__file__).resolve().parent
PARALLEL_STUECK = 16
_AKTIV: list[tuple[dict[str, list[str]], dict[str, list[str]]]] = []


def version() -> str:
    """Gibt den Hash über die Quellen der Wächter und der Testauswahl."""
    summe = hashlib.sha256()
    for datei in sorted([*_ORDNER.glob("waechter*.py"), _ORDNER / "leiter_schnell.py"]):
        summe.update(datei.name.encode() + b"\0" + datei.read_bytes())
    return summe.hexdigest()


@contextlib.contextmanager
def aktiv(datei: Path) -> Iterator[None]:
    """Liest den Speicher aus ``datei``, nutzt ihn im Block und schreibt zurück,
    was der Block gebraucht hat."""
    stand = version()
    try:
        gelesen = json.loads(datei.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        gelesen = {}
    if not isinstance(gelesen, dict) or gelesen.get("version") != stand:
        gelesen = {}
    alt = gelesen.get("eintraege", {})
    benutzt: dict[str, list[str]] = {}
    _AKTIV.append((alt, benutzt))
    try:
        yield
    finally:
        _AKTIV.pop()
    datei.parent.mkdir(parents=True, exist_ok=True)
    roh = json.dumps({"version": stand, "eintraege": benutzt})
    datei.write_text(roh, encoding="utf-8")


def schluessel(art: str, pfad: str, inhalt: str | bytes) -> str:
    """Gibt den Schlüssel aus Art, Pfad und sha256 des Inhalts."""
    roh = (
        inhalt.encode("utf-8", "surrogateescape") if isinstance(inhalt, str) else inhalt
    )
    return f"{art}\0{pfad}\0{hashlib.sha256(roh).hexdigest()}"


def hole(
    art: str, pfad: str, inhalt: str | bytes, rechne: Callable[[], list[str]]
) -> list[str]:
    """Gibt das gespeicherte Ergebnis oder rechnet es; ohne ``aktiv`` immer neu."""
    if not _AKTIV:
        return rechne()
    wert = bekannt(art, pfad, inhalt)
    if wert is None:
        wert = rechne()
        merke(art, pfad, inhalt, wert)
    return wert


def ist_aktiv() -> bool:
    """Wahr innerhalb von ``aktiv``."""
    return bool(_AKTIV)


def bekannt(art: str, pfad: str, inhalt: str | bytes) -> list[str] | None:
    """Gibt das gespeicherte Ergebnis oder ``None``; rechnet nie."""
    if not _AKTIV:
        return None
    alt, benutzt = _AKTIV[-1]
    kennung = schluessel(art, pfad, inhalt)
    wert = benutzt.get(kennung, alt.get(kennung))
    if wert is not None:
        benutzt[kennung] = wert
    return wert


def merke(art: str, pfad: str, inhalt: str | bytes, wert: list[str]) -> None:
    """Legt ein anderswo gerechnetes Ergebnis ab, wenn der Speicher aktiv ist."""
    if _AKTIV:
        _AKTIV[-1][1][schluessel(art, pfad, inhalt)] = wert


def je_datei(
    art: str,
    dateien: list[tuple[str, str]],
    rechne: Callable[[tuple[str, str]], list[str]],
    parallel_ab: int,
) -> list[list[str]]:
    """Gibt je ``(pfad, text)`` das Ergebnis; rechnet die unbekannten in einem Zug,
    ab ``parallel_ab`` Dateien in Prozessen."""
    bekannte = [bekannt(art, pfad, text) for pfad, text in dateien]
    offen = [d for d, wert in zip(dateien, bekannte, strict=True) if wert is None]
    if len(offen) < parallel_ab:
        neu = iter(list(map(rechne, offen)))
    else:
        with ProcessPoolExecutor() as pool:
            neu = iter(list(pool.map(rechne, offen, chunksize=PARALLEL_STUECK)))
    ergebnis = []
    for (pfad, text), wert in zip(dateien, bekannte, strict=True):
        if wert is None:
            wert = next(neu)
            merke(art, pfad, text, wert)
        ergebnis.append(wert)
    return ergebnis
