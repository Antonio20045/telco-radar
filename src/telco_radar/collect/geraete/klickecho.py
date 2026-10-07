"""Echo nach dem Klick: ein Wert gilt nur, wenn Text, Antwort und Variante passen.

Nach jedem Klick liest der Klick-Crawler dieselben Werte zweimal (Datenkonzept
Geräteradar, Abschnitt 8): aus dem sichtbaren Text der Preiszusammenfassung
(``lies_zusammenfassung`` in ``klicktext``) und aus der mitgeschnittenen Antwort über
die Pfade der Klick-Karte (``lies_antwort``). Die Antwort nennt ihre Variante über Pfade
in der JSON-Antwort oder Parameter ihrer Adresse. ``pruefe_echo`` übernimmt einen Wert
nur, wenn beide ihn gleich nennen und Seite wie Antwort die gewählte Variante zeigen;
eine gewählte Option, die sich nicht lesen lässt, bestätigt nichts. Sonst entsteht ein
``Befund`` mit Grund. Fehlt ein Wert auf beiden Seiten, ist er ``None`` und eine
benannte Lücke, nie 0. Unbegrenztes Volumen ist ``math.inf`` wie im Tarifmodell, in
der Antwort auch -1 (o2). Eine Laufzeit gilt nur als Monatsangabe („24 Monate“, „24 x“
oder reine Zahl), sonst ist sie ``None``; ``muster`` eines Pfads nimmt sie aus anderem
Text (o2 „24xhigh“). Pfade mit Filtern und Platzhaltern liest ``klickpfad``; Optionen
vergleicht das Echo ohne Markup, Leerraum sowie Groß- und Kleinschreibung. Deutsche
Zahlen liest ``tarif_model.zahl``. Dieses Modul ruft kein Netz.
"""

from __future__ import annotations

import base64
import binascii
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlsplit

from ...tarif_model import Preisphase, zahl
from .klickkarte import (
    DIMENSIONEN,
    PHASENFELD,
    WERTFELDER,
    Antwortmuster,
    Phasenpfad,
    Wertpfad,
)
from .klickkartentypen import EINHEIT_CENT, EINHEIT_MB
from .klickoptionen import wert_nach_muster
from .klickpfad import am_pfad, ohne_markup, vergleichbar
from .klicktext import Preiswerte, nennt_volumen, phase, volumen_aus_zeile
from .klicktext import lies_zusammenfassung as lies_zusammenfassung

CENT_TOLERANZ = 0.005
GANZZAHLFELDER = frozenset({"ratenzahl", "tarifbindung"})
VOLUMENFELD = "volumen_gb"
UNBEGRENZT_ZAHL = -1
MB_JE_GB = 1024
LAUFZEIT = "laufzeit"
GRUND_OHNE_ANTWORT = "keine Antwort mitgeschnitten"
GRUND_KEINE_WERTE = "weder Text noch Antwort nennen Preiswerte"
KEINE_AUSWAHL = "keine Auswahl"
GRUND_UNLESBAR = "gewählte Option nicht lesbar"

_GANZZAHL = re.compile(r"\d+")
_MONATSANGABE = re.compile(r"(\d+)\s*(?:Monat|x\b|×)", re.I)
_NUR_ZAHL = re.compile(r"\s*(\d+)\s*")


@dataclass(frozen=True)
class Variante:
    """Speicher, Tarif und Ratenlaufzeit in Monaten; ``None`` heißt nicht bestimmt."""

    speicher: str | None = None
    tarif: str | None = None
    laufzeit: int | None = None


@dataclass(frozen=True)
class Antwortlesung:
    """Werte der Antwort und die Variante, die sie nennt (nur abgebildete Teile)."""

    werte: Preiswerte
    variante: Mapping[str, str | int | None]


@dataclass(frozen=True)
class Befund:
    """Ein Wert, der nicht übernommen wurde, und warum."""

    feld: str
    grund: str


@dataclass(frozen=True)
class Echo:
    """Übernommene Werte, Befunde und Lücken einer Kombination."""

    werte: Preiswerte
    befunde: tuple[Befund, ...]
    luecken: tuple[str, ...]

    @property
    def stimmt(self) -> bool:
        """Wahr, wenn es keinen Befund gibt."""
        return not self.befunde


def variante_aus(speicher: object, tarif: object, laufzeit: object) -> Variante:
    """Liest eine Variante einheitlich: Text ohne Ränder, Laufzeit als Monatszahl."""
    return Variante(_als_text(speicher), _als_text(tarif), _monate(laufzeit))


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
    Platzhalter in den Pfaden.
    """
    platz = {} if platz is None else platz
    werte: dict[str, Any] = {
        feld: _feldwert(feld, nutzlast, pfad, platz)
        for feld, pfad in muster.pfade.items()
    }
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
    return Antwortlesung(werte=Preiswerte(**werte), variante=variante)


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
    """Ein Wert als Typ seines Felds: Betrag, Ganzzahl, Volumen in GB oder Phase."""
    if feld == PHASENFELD:
        betrag = _umgerechnet(_betrag(roh), einheit)
        return None if betrag is None else (Preisphase(1, None, betrag),)
    if feld in GANZZAHLFELDER:
        return _ganzzahl(roh)
    if feld == VOLUMENFELD:
        return _umgerechnet(_volumen(roh), einheit)
    return _umgerechnet(_betrag(roh), einheit)


def gleiche_option(a: object, b: object) -> bool:
    """Wahr, wenn zwei Optionswerte ohne Markup, Leerraum und Groß-/Kleinschreibung
    gleich sind; ``None`` ist nur ``None`` gleich."""
    if a is None or b is None:
        return a is None and b is None
    return vergleichbar(a) == vergleichbar(b)


def pruefe_echo(
    gewaehlt: Variante,
    angezeigt: Variante,
    text: Preiswerte,
    antwort: Antwortlesung | None,
) -> Echo:
    """Übernimmt jeden Wert, den Text und Antwort zur Variante gleich nennen."""
    befunde = _variantenbefunde(gewaehlt, angezeigt, antwort)
    if antwort is None:
        befunde.append(Befund("antwort", GRUND_OHNE_ANTWORT))
    if befunde or antwort is None:
        return Echo(Preiswerte(), tuple(befunde), ())
    bestaetigt: dict[str, Any] = {}
    luecken = []
    for feld in WERTFELDER:
        im_text, in_antwort = getattr(text, feld), getattr(antwort.werte, feld)
        befund = _vergleiche(feld, im_text, in_antwort)
        if befund is not None:
            befunde.append(befund)
        elif im_text is None:
            luecken.append(feld)
        else:
            bestaetigt[feld] = im_text
    raten = _ratenbefund(gewaehlt, bestaetigt.get("ratenzahl"))
    if raten is not None:
        del bestaetigt["ratenzahl"]
        befunde.append(raten)
    if not bestaetigt and not befunde:
        befunde.append(Befund("werte", GRUND_KEINE_WERTE))
    return Echo(Preiswerte(**bestaetigt), tuple(befunde), tuple(luecken))


def _ratenbefund(gewaehlt: Variante, raten: int | None) -> Befund | None:
    if raten is None or gewaehlt.laufzeit is None or raten == gewaehlt.laufzeit:
        return None
    grund = f"Seite nennt {raten} Raten, gewählt {gewaehlt.laufzeit} Monate"
    return Befund("ratenzahl", grund)


def _variantenbefunde(
    gewaehlt: Variante, angezeigt: Variante, antwort: Antwortlesung | None
) -> list[Befund]:
    befunde = []
    genannt = antwort.variante if antwort is not None else {}
    for dimension in DIMENSIONEN:
        soll = getattr(gewaehlt, dimension)
        if soll is None:
            befunde.append(Befund(f"variante.{dimension}", GRUND_UNLESBAR))
            continue
        ist = getattr(angezeigt, dimension)
        if not gleiche_option(ist, soll):
            grund = f"Seite zeigt {_option(ist)} statt {soll}"
            befunde.append(Befund(f"variante.{dimension}", grund))
        if dimension in genannt and not gleiche_option(genannt[dimension], soll):
            grund = f"Antwort nennt {_option(genannt[dimension])} statt {soll}"
            befunde.append(Befund(f"antwort.{dimension}", grund))
    return befunde


def _vergleiche(feld: str, im_text: object, in_antwort: object) -> Befund | None:
    if im_text is None and in_antwort is None:
        return None
    if im_text is None:
        return Befund(feld, f"fehlt im Text, Antwort {_zeige(in_antwort)}")
    if in_antwort is None:
        return Befund(feld, f"fehlt in der Antwort, Text {_zeige(im_text)}")
    if not _gleich(im_text, in_antwort):
        return Befund(feld, f"Text {_zeige(im_text)}, Antwort {_zeige(in_antwort)}")
    return None


def _gleich(a: object, b: object) -> bool:
    if isinstance(a, tuple) and isinstance(b, tuple):
        return len(a) == len(b) and all(map(_gleiche_phase, a, b))
    if isinstance(a, float) and isinstance(b, float):
        return a == b or abs(a - b) < CENT_TOLERANZ
    return a == b


def _gleiche_phase(a: Preisphase, b: Preisphase) -> bool:
    gleiche_monate = (a.von_monat, a.bis_monat) == (b.von_monat, b.bis_monat)
    return gleiche_monate and _gleich(a.betrag, b.betrag)


def _zeige(wert: object) -> str:
    if isinstance(wert, tuple):
        return "; ".join(map(_zeige_phase, wert))
    if isinstance(wert, float):
        return "unbegrenzt" if math.isinf(wert) else _deutsch(wert)
    return str(wert)


def _zeige_phase(p: Preisphase) -> str:
    bis = f"–{p.bis_monat}" if p.bis_monat is not None else " und danach"
    return f"Monat {p.von_monat}{bis}: {_deutsch(p.betrag)}"


def _deutsch(betrag: float) -> str:
    englisch = f"{betrag:,.2f}"
    return englisch.replace(",", " ").replace(".", ",").replace(" ", ".")


def _option(wert: object) -> str:
    return KEINE_AUSWAHL if wert is None else str(wert)


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


def _monate(roh: object) -> int | None:
    if not isinstance(roh, str):
        return _ganzzahl(roh)
    treffer = _NUR_ZAHL.fullmatch(roh) or _MONATSANGABE.search(roh)
    return int(treffer[1]) if treffer else None


def _volumen(roh: object) -> float | None:
    if isinstance(roh, str) and nennt_volumen(roh):
        return volumen_aus_zeile(roh)
    menge = _betrag(roh)
    return math.inf if menge == UNBEGRENZT_ZAHL else menge


def _dimension(dimension: str, roh: object) -> str | int | None:
    if dimension == LAUFZEIT:
        return _monate(roh)
    return _als_text(ohne_markup(roh) if isinstance(roh, str) else roh)


def _als_text(roh: object) -> str | None:
    text = "" if roh is None or isinstance(roh, bool) else str(roh).strip()
    if not text:
        return None
    return text
