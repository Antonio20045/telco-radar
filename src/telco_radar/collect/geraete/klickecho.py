"""Echo nach dem Klick: ein Wert gilt nur, wenn Text, Antwort und Variante passen.

Nach jedem Klick liest der Klick-Crawler dieselben Werte zweimal (Datenkonzept
Geräteradar, Abschnitt 8): aus dem sichtbaren Text der Preiszusammenfassung
(``lies_zusammenfassung``) und aus der mitgeschnittenen Antwort über die Pfade der
Klick-Karte (``lies_antwort``). ``pruefe_echo`` übernimmt einen Wert nur, wenn beide ihn
gleich nennen und Seite wie Antwort die gewählte Variante zeigen; sonst entsteht ein
``Befund`` mit Grund. Fehlt ein Wert auf beiden Seiten, ist er ``None`` und eine
benannte Lücke, nie 0. Unbegrenztes Volumen ist ``math.inf`` wie im Tarifmodell.

Deutsche Zahlen haben Tausenderpunkt und Dezimalkomma („1.099,00 €“, „1.000 GB“); sie
liest ``tarif_model.zahl``, die eine Stelle dafür im Repo. Dieses Modul ruft kein Netz.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ...tarif_model import Preisphase, zahl
from .klickkarte import DIMENSIONEN, PHASENFELD, WERTFELDER, Antwortmuster, Phasenpfad

CENT_TOLERANZ = 0.005
GB_JE_EINHEIT = {"gb": 1.0, "mb": 0.001, "tb": 1000.0}
GANZZAHLFELDER = frozenset({"ratenzahl", "tarifbindung"})
VOLUMENFELD = "volumen_gb"
LAUFZEIT = "laufzeit"
GRUND_OHNE_ANTWORT = "keine Antwort mitgeschnitten"
GRUND_KEINE_WERTE = "weder Text noch Antwort nennen Preiswerte"
KEINE_AUSWAHL = "keine Auswahl"

_BETRAG = r"(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)\s*(?:€|EUR\b|Euro\b)"
_ZAHL = r"(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)"
_LUECKE = r"[^\d€\n]{0,40}?"
_BETRAG_RE = re.compile(_BETRAG, re.I)
_ANZAHLUNG = re.compile(r"\b(?:Anzahlung|Zuzahlung)" + _LUECKE + _BETRAG, re.I)
_RATE = re.compile(r"\b(?:Ger(?:ä|ae)te?)?rate\b" + _LUECKE + _BETRAG, re.I)
_MAL_RATE = re.compile(r"\b(\d{1,2})\s*[x×]\s*" + _BETRAG, re.I)
_RATENZAHL = re.compile(r"\b(\d{1,2})\s*(?:monatliche\s+)?Raten\b", re.I)
_TARIFZEILE = re.compile(r"\b(?:Tarif|Grundgeb(?:ü|ue)hr|Grundpreis)\b", re.I)
_SPANNE = r"\bMonate?n?\s+(\d{1,2})\s*(?:[-–]|bis)\s*(\d{1,2})\b"
_PHASE_SPANNE = re.compile(_BETRAG + _LUECKE + _SPANNE, re.I)
_AB = r"\bab\s+(?:dem\s+)?(?:Monat\s+(\d{1,2})|(\d{1,2})\.\s*Monat)\b"
_PHASE_AB = re.compile(_AB + _LUECKE + _BETRAG, re.I)
_PHASE_ERSTE = re.compile(
    r"\bersten\s+(\d{1,2})\s+Monate?n?\b" + _LUECKE + _BETRAG, re.I
)
_PHASE_DANACH = re.compile(r"\bdanach\b" + _LUECKE + _BETRAG, re.I)
_BINDUNG_WORT = r"\b(?:Mindest(?:vertrags)?laufzeit|Vertragslaufzeit|Tarifbindung)"
_BINDUNG = re.compile(_BINDUNG_WORT + r"\D{0,20}?(\d{1,2})\s*Monat", re.I)
_ANSCHLUSS_WORT = r"\b(?:Anschluss|Bereitstellung|Aktivierung)\w*"
_ANSCHLUSS = re.compile(_ANSCHLUSS_WORT + _LUECKE + _BETRAG, re.I)
_VOLUMENZEILE = re.compile(r"\b(?:Daten|Volumen|Highspeed)", re.I)
_VOLUMEN = re.compile(_ZAHL + r"\s*(GB|MB|TB)\b", re.I)
_UNBEGRENZT = re.compile(r"\b(?:unbegrenzt|unlimitiert|unlimited)", re.I)
_GANZZAHL = re.compile(r"\d+")


@dataclass(frozen=True)
class Variante:
    """Speicher, Tarif und Ratenlaufzeit in Monaten; ``None`` heißt nicht bestimmt."""

    speicher: str | None = None
    tarif: str | None = None
    laufzeit: int | None = None


@dataclass(frozen=True)
class Preiswerte:
    """Die Werte einer Preiszusammenfassung, Felder wie ``klickkarte.WERTFELDER``."""

    anzahlung: float | None = None
    rate: float | None = None
    ratenzahl: int | None = None
    tarifphasen: tuple[Preisphase, ...] | None = None
    tarifbindung: int | None = None
    anschluss: float | None = None
    volumen_gb: float | None = None


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
    return Variante(_als_text(speicher), _als_text(tarif), _ganzzahl(laufzeit))


def lies_zusammenfassung(text: str) -> Preiswerte:
    """Liest die Werte aus dem sichtbaren Text der Preiszusammenfassung."""
    rate, ratenzahl = _rate_aus_text(text)
    bindung = _BINDUNG.search(text)
    return Preiswerte(
        anzahlung=_betrag_nach(_ANZAHLUNG, text),
        rate=rate,
        ratenzahl=ratenzahl,
        tarifphasen=_phasen_aus_text(text),
        tarifbindung=int(bindung[1]) if bindung else None,
        anschluss=_betrag_nach(_ANSCHLUSS, text),
        volumen_gb=_volumen_aus_text(text),
    )


def lies_antwort(nutzlast: object, muster: Antwortmuster) -> Antwortlesung:
    """Liest dieselben Werte aus der JSON-Antwort über die Pfade der Klick-Karte."""
    werte: dict[str, Any] = {
        feld: _feldwert(feld, nutzlast, pfad) for feld, pfad in muster.pfade.items()
    }
    variante = {
        d: _dimension(d, _am_pfad(nutzlast, pfad))
        for d, pfad in muster.variante.items()
    }
    return Antwortlesung(werte=Preiswerte(**werte), variante=variante)


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
            continue
        ist = getattr(angezeigt, dimension)
        if ist != soll:
            grund = f"Seite zeigt {_option(ist)} statt {soll}"
            befunde.append(Befund(f"variante.{dimension}", grund))
        if dimension in genannt and genannt[dimension] != soll:
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


def _betrag_nach(muster: re.Pattern[str], text: str) -> float | None:
    treffer = muster.search(text)
    return zahl(treffer[1]) if treffer else None


def _rate_aus_text(text: str) -> tuple[float | None, int | None]:
    rate, mal = _RATE.search(text), _MAL_RATE.search(text)
    anzahl = _RATENZAHL.search(text)
    betrag = zahl(rate[1]) if rate else (zahl(mal[2]) if mal else None)
    raten = anzahl[1] if anzahl else (mal[1] if mal else None)
    return betrag, int(raten) if raten is not None else None


def _phasen_aus_text(text: str) -> tuple[Preisphase, ...] | None:
    for zeile in text.splitlines():
        if _TARIFZEILE.search(zeile) and _BETRAG_RE.search(zeile):
            return _phasen_aus_zeile(zeile)
    return None


def _phasen_aus_zeile(zeile: str) -> tuple[Preisphase, ...] | None:
    funde = _phasenfunde(zeile)
    belegt = [bereich for _, bereich in funde]
    phasen = [phase for phase, _ in funde if phase is not None]
    frei = [b for b in _BETRAG_RE.finditer(zeile) if not _in(b.start(), belegt)]
    if frei and (not belegt or frei[0].start() < min(a for a, _ in belegt)):
        beginn = min((p.von_monat for p in phasen), default=None)
        grundpreis = _phase(1, None if beginn is None else beginn - 1, frei[0][1])
        funde.append((grundpreis, frei[0].span()))
        phasen += [grundpreis] if grundpreis is not None else []
    if len(phasen) != len(funde):
        return None
    return tuple(sorted(phasen, key=lambda p: p.von_monat))


def _phasenfunde(zeile: str) -> list[tuple[Preisphase | None, tuple[int, int]]]:
    spannen, ab = _PHASE_SPANNE.finditer(zeile), _PHASE_AB.finditer(zeile)
    funde = [(_phase(t[2], t[3], t[1]), t.span()) for t in spannen]
    funde += [(_phase(t[1] or t[2], None, t[3]), t.span()) for t in ab]
    erste = _PHASE_ERSTE.search(zeile)
    if erste is None:
        return funde
    funde.append((_phase(1, erste[1], erste[2]), erste.span()))
    danach = _PHASE_DANACH.search(zeile, erste.end())
    if danach is not None:
        funde.append((_phase(int(erste[1]) + 1, None, danach[1]), danach.span()))
    return funde


def _phase(von: int | str, bis: int | str | None, betrag: str) -> Preisphase | None:
    wert = zahl(betrag)
    if wert is None:
        return None
    return Preisphase(int(von), None if bis is None else int(bis), wert)


def _in(stelle: int, bereiche: list[tuple[int, int]]) -> bool:
    return any(anfang <= stelle < ende for anfang, ende in bereiche)


def _volumen_aus_text(text: str) -> float | None:
    zeilen = (z for z in text.splitlines() if _VOLUMENZEILE.search(z))
    return next((w for w in map(_volumen_aus_zeile, zeilen) if w is not None), None)


def _volumen_aus_zeile(zeile: str) -> float | None:
    if _UNBEGRENZT.search(zeile):
        return math.inf
    treffer = _VOLUMEN.search(zeile)
    menge = zahl(treffer[1]) if treffer else None
    if treffer is None or menge is None:
        return None
    return menge * GB_JE_EINHEIT[treffer[2].lower()]


def _feldwert(feld: str, nutzlast: object, pfad: str | Phasenpfad) -> object:
    if isinstance(pfad, Phasenpfad):
        return _phasen_aus_liste(_am_pfad(nutzlast, pfad.liste), pfad)
    roh = _am_pfad(nutzlast, pfad)
    if feld == PHASENFELD:
        betrag = _betrag(roh)
        return None if betrag is None else (Preisphase(1, None, betrag),)
    if feld in GANZZAHLFELDER:
        return _ganzzahl(roh)
    if feld == VOLUMENFELD:
        return _volumen(roh)
    return _betrag(roh)


def _phasen_aus_liste(liste: object, pfad: Phasenpfad) -> tuple[Preisphase, ...] | None:
    if not isinstance(liste, list) or not liste:
        return None
    phasen = []
    for eintrag in liste:
        von = _ganzzahl(_am_pfad(eintrag, pfad.von))
        bis = _ganzzahl(_am_pfad(eintrag, pfad.bis))
        betrag = _betrag(_am_pfad(eintrag, pfad.betrag))
        if von is None or betrag is None:
            return None
        phasen.append(Preisphase(von, bis, betrag))
    return tuple(sorted(phasen, key=lambda p: p.von_monat))


def _am_pfad(nutzlast: object, pfad: str) -> object:
    knoten = nutzlast
    for teil in pfad.split("."):
        if isinstance(knoten, Mapping):
            knoten = knoten.get(teil)
        elif isinstance(knoten, list) and teil.isdigit() and int(teil) < len(knoten):
            knoten = knoten[int(teil)]
        else:
            return None
    return knoten


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


def _volumen(roh: object) -> float | None:
    if isinstance(roh, str) and (_VOLUMEN.search(roh) or _UNBEGRENZT.search(roh)):
        return _volumen_aus_zeile(roh)
    return _betrag(roh)


def _dimension(dimension: str, roh: object) -> str | int | None:
    return _ganzzahl(roh) if dimension == LAUFZEIT else _als_text(roh)


def _als_text(roh: object) -> str | None:
    text = "" if roh is None or isinstance(roh, bool) else str(roh).strip()
    return text or None
