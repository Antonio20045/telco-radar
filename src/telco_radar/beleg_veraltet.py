"""Welche Bilder gehören zu einer früheren Position desselben Paares und Tages?

Ein zweiter Klick-Lauf am selben Tag kann eine andere Position (Kennung im Namen,
``beleg_regeln.folge_dateiname``) wählen: Dann liegen für (Gerät, Anbieter, Tag) die
Einzelbilder zweier Kennungen im Release. Das Manifest (``beleg_manifest``) kann nicht
wissen, welche gilt, und verwirft das Paar. Die Entscheidung trifft die Uploadzeit der
Einzelbilder: die jüngste Kennung gilt, die früheren sind veraltet.

Gelöscht wird erst im Manifest-Schritt (``scripts/belege_manifest.py``), nachdem das
Manifest auf die neuen Bilder zeigt; der Klick-Job löscht nichts. So zeigt das letzte
eingecheckte Manifest bis zum Gerätelauf auf Dateien, die noch da sind.

Fail-closed: Nur bei mindestens zwei Kennungen mit eigenem Einzelbild wird etwas für
veraltet erklärt (Bilder einer Kennung ohne Einzelbild, etwa nach Teilausfall, gelten
nicht als Gegner). Fehlt die Zeit eines Einzelbilds oder liegen die beiden jüngsten
gleichauf, bleibt das Paar unentschieden: nichts wird gelöscht, das Manifest verwirft
es wie bisher, und das Paar steht in ``offen``. Stdlib, kein Netz.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from .beleg_bildfolge import PREIS
from .beleg_regeln import zerlege_folgename

Stelle = tuple[str, str]
"""(Release-Tag, Dateiname)."""
Paar = tuple[str, str, str]
Zeiten = Mapping[str, Mapping[str, str]]
"""Release-Tag -> Dateiname -> Uploadzeit (ISO 8601, als Text vergleichbar)."""


@dataclass(frozen=True)
class Veraltet:
    """Das Ergebnis: ``loeschen`` sind die Stellen früherer Positionen, ``offen`` die
    Paare (Text ``Gerät/Anbieter/Tag``), die ohne Zeit nicht entscheidbar sind."""

    loeschen: list[Stelle] = field(default_factory=list)
    offen: list[str] = field(default_factory=list)


def _positionen(
    anhaenge: Mapping[str, Sequence[str]],
) -> dict[Paar, dict[str, list[Stelle]]]:
    """Paar -> Kennung -> alle Stellen (Einzelbild und Schritte) dieser Kennung."""
    erg: dict[Paar, dict[str, list[Stelle]]] = defaultdict(lambda: defaultdict(list))
    for tag, dateien in anhaenge.items():
        for datei in dateien:
            folge = zerlege_folgename(datei)
            if folge is not None:
                erg[folge.paar][folge.kennung].append((tag, datei))
    return erg


def streitpaare(anhaenge: Mapping[str, Sequence[str]]) -> set[Paar]:
    """Paare mit Einzelbildern von mindestens zwei Kennungen."""
    return {
        paar
        for paar, kennungen in _positionen(anhaenge).items()
        if sum(1 for stellen in kennungen.values() if _einzel(stellen)) > 1
    }


def _einzel(stellen: Sequence[Stelle]) -> list[Stelle]:
    return [
        s
        for s in stellen
        if (f := zerlege_folgename(s[1])) is not None and f.schritt == PREIS
    ]


def finde_veraltete(anhaenge: Mapping[str, Sequence[str]], zeiten: Zeiten) -> Veraltet:
    """Die Stellen früherer Positionen (Modulkopf); ``zeiten`` nur für Streitpaare."""
    ergebnis = Veraltet()
    for paar, kennungen in sorted(_positionen(anhaenge).items()):
        mit_einzel = {k: _einzel(s) for k, s in kennungen.items() if _einzel(s)}
        if len(mit_einzel) < 2:
            continue
        stand: dict[str, str] = {}
        for kennung, einzel in mit_einzel.items():
            ts = [zeiten.get(tag, {}).get(datei) for tag, datei in einzel]
            if not all(ts):
                break
            stand[kennung] = max(str(t) for t in ts)
        else:
            rang = sorted(stand.values(), reverse=True)
            if rang[0] != rang[1]:
                neueste = max(stand, key=lambda k: stand[k])
                for kennung, stellen in kennungen.items():
                    if kennung != neueste:
                        ergebnis.loeschen.extend(stellen)
                continue
        ergebnis.offen.append("/".join(paar))
    return ergebnis


def ohne_stellen(
    anhaenge: Mapping[str, Sequence[str]], weg: Sequence[Stelle]
) -> dict[str, list[str]]:
    """Die Anhänge ohne die genannten Stellen."""
    gestrichen = set(weg)
    return {
        tag: [d for d in dateien if (tag, d) not in gestrichen]
        for tag, dateien in anhaenge.items()
    }
