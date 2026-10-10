"""Zweite Lesung: Werte und Variante aus der Antwort über die Pfade der Klick-Karte.

``lies_antwort`` liest die Wertfelder an den Pfaden der Karte (``klickpfad``: Filter,
Auffächerung, Platzhalter) und die Variante an Pfaden oder in den Parametern der
Antwortadresse, mit ``segment`` auch aus deren Base64-Pfadsegment (o2). ``feldwert``
wandelt einen Wert in den Typ seines Felds: Betrag, Ganzzahl, Volumen in GB (``-1``
heißt unbegrenzt, o2) oder eine Phase ohne Ende, aus einer Liste von Posten die
Phasen wie im Text (o2 ``priceSummary.recurringChargesListEntries`` mit der Zeile „ab
dem 25. Monat: 29,99 €“); Bündelfelder (1&1, freenet) sind
Beträge in ``Antwortlesung.buendel``, Nachweise Wortlaute in
``Antwortlesung.nachweise``; ``einheit`` rechnet Cent in Euro
(1&1) und MB in GB (o2). Eine Laufzeit gilt nur als Monatsangabe („24 Monate“, „24 x“
oder reine Zahl), sonst ist sie ``None``; ``muster`` eines Pfads nimmt sie aus anderem
Text (o2 „24xhigh“). Markup in Varianten fällt weg (o2 „O<sub>2</sub>“). Fehlt ein
Wert, ist er ``None``, nie 0. Deutsche Zahlen liest ``tarif_model.zahl``. Dieses
Modul ruft kein Netz.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlsplit

from ...tarif_model import Preisphase, zahl
from .klickkarte import PHASENFELD, Antwortmuster, Phasenpfad, Wertpfad
from .klickkartentypen import BUENDELFELDER, EINHEIT_CENT, EINHEIT_MB, NACHWEISFELDER
from .klickoptionen import wert_nach_muster
from .klickpfad import am_pfad, ohne_markup, vergleichbar
from .klicktext import (
    Buendelwerte,
    Preiswerte,
    nennt_volumen,
    phase,
    phasen_aus_text,
    volumen_aus_zeile,
)

GANZZAHLFELDER = frozenset({"ratenzahl", "tarifbindung"})
VOLUMENFELD = "volumen_gb"
UNBEGRENZT_ZAHL = -1
MB_JE_GB = 1024
LAUFZEIT = "laufzeit"

_GANZZAHL = re.compile(r"\d+")
_MONATSANGABE = re.compile(r"(\d+)\s*(?:Monat|x\b|×)", re.I)
_NUR_ZAHL = re.compile(r"\s*(\d+)\s*")
_SUMME = re.compile(r"\s*(\d+)\s*\+\s*(\d+)\s*")


@dataclass(frozen=True)
class Antwortlesung:
    """Werte der Antwort und die Variante, die sie nennt (nur abgebildete Teile);
    ``nachweise`` hält je gelesenem Nachweisfeld seinen Wortlaut."""

    werte: Preiswerte
    variante: Mapping[str, str | int | None]
    buendel: Buendelwerte = Buendelwerte()
    nachweise: Mapping[str, str] = field(default_factory=dict)


def lies_antwort(
    nutzlast: object,
    muster: Antwortmuster,
    url: str | None = None,
    platz: Mapping[str, str | None] | None = None,
) -> Antwortlesung:
    """Liest dieselben Werte aus der JSON-Antwort über die Pfade der Klick-Karte.

    Die Variante steht an den Pfaden ``muster.variante`` oder in den Parametern
    ``muster.parameter`` der Adresse ``url`` (mit ``muster.segment`` auch in deren
    Pfadsegment); fehlt sie dort, ist sie ``None``. ``platz`` hält die Werte der
    Platzhalter in den Pfaden; ``muster.platzhalter`` fügt Werte dieser Antwort hinzu
    (fehlt einer oder ist er mehrdeutig, ist er ``None`` und jeder Pfad mit ihm auch).
    """
    platz = {} if platz is None else platz
    if muster.platzhalter:
        eigene = {
            name: _skalar(am_pfad(nutzlast, pfad, platz))
            for name, pfad in muster.platzhalter.items()
        }
        platz = {**platz, **eigene}
    gelesen: dict[str, Any] = {
        feld: _feldwert(feld, nutzlast, pfad, platz)
        for feld, pfad in muster.pfade.items()
    }
    nachweise = {f: gelesen.pop(f) for f in NACHWEISFELDER if f in gelesen}
    werte = {f: w for f, w in gelesen.items() if f not in BUENDELFELDER}
    buendel = {f: w for f, w in gelesen.items() if f in BUENDELFELDER}
    frage = adressparameter(url, muster.segment)
    variante = {
        d: _dimension(d, _gemustert(frage.get(_pfad(name)), name))
        for d, name in muster.parameter.items()
    }
    variante.update(
        {
            d: _dimension(d, _gemustert(am_pfad(nutzlast, _pfad(pfad), platz), pfad))
            for d, pfad in muster.variante.items()
        }
    )
    return Antwortlesung(
        Preiswerte(**werte),
        variante,
        Buendelwerte(**buendel),
        {f: w for f, w in nachweise.items() if w is not None},
    )


def adressparameter(url: str | None, segment: re.Pattern[str] | None) -> dict[str, str]:
    """Die Parameter einer Adresse, je Name der erste Wert.

    Mit ``segment`` dazu die Teile ``name=wert`` (durch ``;`` getrennt) aus der ersten
    Gruppe des Musters in der Adresse, Base64-kodiert wie bei o2 ``/configuration/…``.
    """
    if url is None:
        return {}
    frage = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
    treffer = None if segment is None else segment.search(url)
    if treffer is None:
        return frage
    roh = treffer[1] if treffer.re.groups else treffer[0]
    try:
        text = base64.urlsafe_b64decode(roh + "=" * (-len(roh) % 4)).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return frage
    for teil in text.split(";"):
        name, gleich, wert = teil.partition("=")
        if gleich and name.strip():
            frage.setdefault(name.strip(), wert.strip())
    return frage


def feldwert(feld: str, roh: object, einheit: str | None = None) -> object:
    """Ein Wert als Typ seines Felds: Betrag, Ganzzahl, Volumen in GB, Phase oder
    der Wortlaut eines Nachweises in einer Zeile (Liste oder Zuordnung als JSON)."""
    if feld in NACHWEISFELDER:
        return _nachweis(roh)
    if feld == PHASENFELD and isinstance(roh, list):
        return phasen_aus_text(_postenzeilen(roh))
    if feld == PHASENFELD:
        betrag = _umgerechnet(_betrag(roh), einheit)
        return None if betrag is None else (Preisphase(1, None, betrag),)
    if feld in GANZZAHLFELDER:
        return _ganzzahl(roh)
    if feld == VOLUMENFELD:
        return _umgerechnet(_volumen(roh), einheit)
    return _umgerechnet(_betrag(roh), einheit)


def _postenzeilen(posten: list) -> str:
    """Je Posten eine Zeile aus seinen Texten ohne Markup, ohne Schlüssel mit „@“."""
    zeilen = []
    for eintrag in posten:
        paare = eintrag.items() if isinstance(eintrag, Mapping) else [("", eintrag)]
        texte = [
            ohne_markup(w)
            for k, w in paare
            if isinstance(w, str) and not str(k).startswith("@")
        ]
        zeilen.append(" ".join(" ".join(texte).split()))
    return "\n".join(zeilen)


def _feldwert(
    feld: str,
    nutzlast: object,
    pfad: str | Wertpfad | Phasenpfad,
    platz: Mapping[str, str | None],
) -> object:
    if isinstance(pfad, Phasenpfad):
        return _phasen_aus_liste(am_pfad(nutzlast, pfad.liste, platz), pfad, platz)
    roh = _gemustert(am_pfad(nutzlast, _pfad(pfad), platz), pfad)
    return feldwert(feld, roh, pfad.einheit if isinstance(pfad, Wertpfad) else None)


def _pfad(pfad: str | Wertpfad) -> str:
    return pfad.pfad if isinstance(pfad, Wertpfad) else pfad


def _gemustert(roh: object, pfad: str | Wertpfad) -> object:
    if not isinstance(pfad, Wertpfad) or pfad.muster is None or roh is None:
        return roh
    text = roh if isinstance(roh, str) else vergleichbar(roh)
    return None if text is None else wert_nach_muster(text, pfad.muster)


def _umgerechnet(wert: float | None, einheit: str | None) -> float | None:
    if wert is None or math.isinf(wert):
        return wert
    if einheit == EINHEIT_CENT:
        return wert / 100
    if einheit == EINHEIT_MB:
        return wert / MB_JE_GB
    return wert


def _phasen_aus_liste(
    liste: object, pfad: Phasenpfad, platz: Mapping[str, str | None]
) -> tuple[Preisphase, ...] | None:
    if not isinstance(liste, list) or not liste:
        return None
    phasen = []
    for eintrag in liste:
        von = _ganzzahl(am_pfad(eintrag, pfad.von, platz))
        bis = _ganzzahl(am_pfad(eintrag, pfad.bis, platz))
        betrag = _betrag(am_pfad(eintrag, pfad.betrag, platz))
        teil = None if von is None else phase(von, bis, betrag)
        if teil is None:
            return None
        phasen.append(teil)
    return tuple(sorted(phasen, key=lambda p: p.von_monat))


def _betrag(roh: object) -> float | None:
    if isinstance(roh, bool):
        return None
    if isinstance(roh, int | float):
        return float(roh) if math.isfinite(roh) else None
    return zahl(roh) if isinstance(roh, str) else None


def _ganzzahl(roh: object) -> int | None:
    if isinstance(roh, bool):
        return None
    if isinstance(roh, int | float):
        return int(roh) if float(roh).is_integer() else None
    treffer = _GANZZAHL.search(roh) if isinstance(roh, str) else None
    return int(treffer[0]) if treffer else None


def monate(roh: object) -> int | None:
    """Eine Laufzeit als Monatszahl: „24 Monate“, „24 x“, reine Zahl oder Summe.

    Die Summe „24+12“ ist das 1&1-Modell: 24 Monate, dann 12 weitere, zusammen 36
    (Datenkonzept Geräteradar, Abschnitt 5.1).
    """
    if not isinstance(roh, str):
        return _ganzzahl(roh)
    summe = _SUMME.fullmatch(roh)
    if summe is not None:
        return int(summe[1]) + int(summe[2])
    treffer = _NUR_ZAHL.fullmatch(roh) or _MONATSANGABE.search(roh)
    return int(treffer[1]) if treffer else None


def _volumen(roh: object) -> float | None:
    if isinstance(roh, str) and nennt_volumen(roh):
        return volumen_aus_zeile(roh)
    menge = _betrag(roh)
    return math.inf if menge == UNBEGRENZT_ZAHL else menge


def _dimension(dimension: str, roh: object) -> str | int | None:
    if dimension == LAUFZEIT:
        return monate(roh)
    return als_text(ohne_markup(roh) if isinstance(roh, str) else roh)


def als_text(roh: object) -> str | None:
    """Ein Wert als Text ohne Ränder; leer oder ``None`` ist ``None``."""
    text = "" if roh is None or isinstance(roh, bool) else str(roh).strip()
    if not text:
        return None
    return text


def _nachweis(roh: object) -> str | None:
    """Ein Nachweis als Text in einer Zeile; eine Liste oder Zuordnung als JSON."""
    if isinstance(roh, list | dict):
        return json.dumps(roh, ensure_ascii=False, sort_keys=True)
    return als_text(" ".join(roh.split())) if isinstance(roh, str) else None


def _skalar(roh: object) -> str | None:
    """Ein Platzhalterwert: Text oder Zahl als Text, alles andere ``None``."""
    return als_text(roh) if isinstance(roh, str | int | float) else None
