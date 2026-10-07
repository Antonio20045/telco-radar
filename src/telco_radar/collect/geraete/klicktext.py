"""Lesung der sichtbaren Preiszusammenfassung nach einem Klick.

Die erste der zwei Lesungen des Klick-Crawlers (Datenkonzept Geräteradar, Abschnitt 8);
die zweite, die Antwort, liest ``klickecho``. Ein genannter Betrag geht vor, aber nur am
Posten selbst: ein Posten endet an Komma, Gedankenstrich, Semikolon, „·“ und Zeilenende,
und die Lücke bis zum Betrag überspringt weder „entfällt“, „keine“, „kostenlos“ noch
„sonst“, „statt“, „danach“; ein verneinter Posten („ohne Anzahlung“) nimmt keinen
Betrag. Ohne Betrag ist ein Posten 0, wenn das Nullwort unmittelbar am Posten steht
(„Anzahlung: entfällt“) oder davor („ohne Anzahlung“); ein Nullwort eines anderen
Satzteils („keine Zinsen“) ist keine 0. Ein Datenvolumen mit GB-Zahl ist begrenzt, auch
wenn die Zeile „unbegrenzt“ nennt; unbegrenzt ist es nur ohne Zahl (``math.inf``).
Tarifphasen mit einem Ende vor dem Anfang sind ein Widerspruch: die Zeile ergibt dann
keine Phasen. Zur Tarifzeile gehören die direkt folgenden Zeilen, die mit „ab (dem)
N. Monat“ beginnen (o2: eigene Zeile „ab dem 25. Monat: 29,99 €“ unter „Tarif mtl.“).
Leerraum vor einem Dezimalkomma ist Satz, kein Text: ``zahlen_ohne_leerraum`` macht
aus „44\n,\n99\n€/Monat“ (1&1 setzt Euro, Komma und Cent in eigene Elemente) „44,99“,
bevor ein Muster liest; ein Komma ohne Leerraum davor („12, 24 Monate“) und ein
Zeilenumbruch zwischen zwei Zahlen („36,50 €\nTarif“) bleiben. Fehlt ein Wert, ist er
``None``, nie 0. Deutsche Zahlen liest ``tarif_model.zahl``. ``fundstellen`` nennt je
Feld den Ausschnitt, aus dem der Wert stammt; der Beleg (``klickbeleg``) hält ihn fest.
"""

from __future__ import annotations

import itertools
import math
import re
from dataclasses import dataclass

from ...tarif_model import Preisphase, zahl

GB_JE_EINHEIT = {"gb": 1.0, "mb": 0.001, "tb": 1000.0}

_BETRAG = r"(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)\s*(?:€|EUR\b|Euro\b)"
_ZAHL = r"(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)"
_NULLWORT = r"\b(?:entf(?:ä|ae)ll\w*|keine?|kostenlos|gratis)\b"
_HALT = _NULLWORT + r"|\b(?:sonst|statt|danach)\b|[·•|;]"
_AM_POSTEN = r"\w*\s*[:–—-]?\s*"
_POSTEN_HALT = _HALT + r"|[,–—]|\s-\s"
_POSTEN_LUECKE = r"(?:(?!" + _POSTEN_HALT + r")[^\d€\n]){0,40}?"
_VERNEINT = re.compile(r"\b(?:ohne|keine?)\s+$", re.I)
_LUECKE = r"(?:(?!" + _HALT + r")[^\d€\n]){0,40}?"
_BETRAG_RE = re.compile(_BETRAG, re.I)
_RATE = re.compile(r"\b(?:Ger(?:ä|ae)te?)?rate\b" + _LUECKE + _BETRAG, re.I)
_MAL_RATE = re.compile(r"\b(\d{1,2})\s*[x×]\s*" + _BETRAG, re.I)
_RATENZAHL = re.compile(r"\b(\d{1,2})\s*(?:monatliche\s+)?Raten\b", re.I)
_TARIFZEILE = re.compile(r"\b(?:Tarif|Grundgeb(?:ü|ue)hr|Grundpreis)\b", re.I)
_SPANNE = r"\bMonate?n?\s+(\d{1,2})\s*(?:[-–]|bis)\s*(\d{1,2})\b"
_PHASE_SPANNE = re.compile(_BETRAG + _LUECKE + _SPANNE, re.I)
_AB = r"\bab\s+(?:dem\s+)?(?:Monat\s+(\d{1,2})|(\d{1,2})\.\s*Monat)\b"
_PHASE_AB = re.compile(_AB + _LUECKE + _BETRAG, re.I)
_FOLGEPHASE = re.compile(r"\s*" + _AB, re.I)
_ERSTE = r"\bersten\s+(\d{1,2})\s+Monate?n?\b"
_PHASE_ERSTE = re.compile(_ERSTE + _LUECKE + _BETRAG, re.I)
_PHASE_ERSTE_VORN = re.compile(_BETRAG + _LUECKE + _ERSTE, re.I)
_PHASE_DANACH = re.compile(r"\bdanach\b" + _LUECKE + _BETRAG, re.I)
_BINDUNG_WORT = r"\b(?:Mindest(?:vertrags)?laufzeit|Vertragslaufzeit|Tarifbindung)"
_BINDUNG = re.compile(_BINDUNG_WORT + r"\D{0,20}?(\d{1,2})\s*Monat", re.I)
_VOLUMENZEILE = re.compile(r"\b(?:Daten|Volumen|Highspeed)", re.I)
_VOLUMEN = re.compile(_ZAHL + r"\s*(GB|MB|TB)\b", re.I)
_UNBEGRENZT = re.compile(
    r"\b(?:unbegrenzt|unlimitiert|unlimited)(?![a-z]*[\s-]+on[\s-]+demand)", re.I
)
"""„unbegrenzt“ als Volumen; „Unlimited on demand“ ist bei 1&1 ein Produktname mit
festem Grundvolumen (S 10, M 50, L 150 GB laut 1&1, tarife.jsonl), kein Volumen."""
_GEGENWERT = re.compile(r"\b(?:statt|sonst)\b", re.I)
_LEERRAUM_IN_ZAHL = re.compile(r"(?<=\d)\s+,\s*(?=\d{1,2}(?!\d))")


def _posten(wort: str) -> tuple[re.Pattern[str], ...]:
    betrag = re.compile(wort + _AM_POSTEN + _POSTEN_LUECKE + _BETRAG, re.I)
    null_danach = re.compile(wort + _AM_POSTEN + _NULLWORT, re.I)
    null_davor = re.compile(r"\b(?:keine?|ohne)\s+" + wort, re.I)
    return betrag, null_danach, null_davor


_ANZAHLUNG = _posten(r"\b(?:Anzahlung|Zuzahlung)")
_ANSCHLUSS = _posten(r"\b(?:Anschluss|Bereitstellung|Aktivierung)\w*")


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
class Buendelwerte:
    """Werte eines Vertrags aus Gerät und Tarif (``klickkarte.BUENDELFELDER``)."""

    buendelbetrag: float | None = None
    einmalzahlung: float | None = None


def zahlen_ohne_leerraum(text: str) -> str:
    """``text`` ohne Leerraum um ein Komma mit Leerraum davor („44 , 99“ → „44,99“)."""
    return _LEERRAUM_IN_ZAHL.sub(",", text)


def nennt_betrag(text: str) -> bool:
    """Wahr, wenn ``text`` einen Betrag mit €, EUR oder Euro nennt."""
    return _BETRAG_RE.search(zahlen_ohne_leerraum(text)) is not None


def lies_zusammenfassung(text: str) -> Preiswerte:
    """Liest die Werte aus dem sichtbaren Text der Preiszusammenfassung."""
    text = zahlen_ohne_leerraum(text)
    rate, ratenzahl = _rate_aus_text(text)
    bindung = _BINDUNG.search(text)
    return Preiswerte(
        anzahlung=_postenwert(_ANZAHLUNG, text),
        rate=rate,
        ratenzahl=ratenzahl,
        tarifphasen=phasen_aus_text(text),
        tarifbindung=int(bindung[1]) if bindung else None,
        anschluss=_postenwert(_ANSCHLUSS, text),
        volumen_gb=_volumen_aus_text(text),
    )


def fundstellen(text: str) -> dict[str, str]:
    """Je Wertfeld der Ausschnitt, aus dem ``lies_zusammenfassung`` den Wert liest.

    Allein gelesen nennt ein Ausschnitt sein Feld wie der ganze Text: so findet eine
    Prüfung einen archivierten Wert an seiner Fundstelle wieder.
    """
    text = zahlen_ohne_leerraum(text)
    zeilen = text.splitlines()
    rate, mal = _RATE.search(text), _MAL_RATE.search(text)
    funde = {
        "anzahlung": _postenstelle(_ANZAHLUNG, text),
        "rate": _ausschnitt(rate or mal),
        "ratenzahl": _ausschnitt(_RATENZAHL.search(text) or mal),
        "tarifphasen": _tarifstelle(zeilen),
        "tarifbindung": _ausschnitt(_BINDUNG.search(text)),
        "anschluss": _postenstelle(_ANSCHLUSS, text),
        "volumen_gb": next((z for z in zeilen if _volumenzeile(z)), None),
    }
    return {feld: stelle for feld, stelle in funde.items() if stelle is not None}


def volumen_aus_zeile(zeile: str) -> float | None:
    """GB aus einer Zeile; ``math.inf`` nur für „unbegrenzt“ ohne GB-Zahl.

    „1&1 Unlimited on demand S“ nennt kein Volumen (None); „… S 10 GB“ nennt 10 GB.
    """
    vorn = _GEGENWERT.split(zeile, maxsplit=1)[0]
    treffer = _VOLUMEN.search(vorn)
    if treffer is None:
        return math.inf if _UNBEGRENZT.search(vorn) else None
    menge = zahl(treffer[1])
    if menge is None:
        return None
    return menge * GB_JE_EINHEIT[treffer[2].lower()]


def nennt_volumen(text: str) -> bool:
    """Wahr, wenn ``text`` eine GB-Zahl oder „unbegrenzt“ nennt."""
    return bool(_VOLUMEN.search(text) or _UNBEGRENZT.search(text))


def phase(
    von: int | str, bis: int | str | None, betrag: float | None
) -> Preisphase | None:
    """Eine Preisphase; ``None`` ohne Betrag oder mit einem Ende vor dem Anfang."""
    if betrag is None:
        return None
    anfang, ende = int(von), None if bis is None else int(bis)
    if ende is not None and ende < anfang:
        return None
    return Preisphase(anfang, ende, betrag)


def _postenwert(muster: tuple[re.Pattern[str], ...], text: str) -> float | None:
    betrag, *null = muster
    for treffer in betrag.finditer(text):
        if not _VERNEINT.search(text[: treffer.start()]):
            return zahl(treffer[1])
    return 0.0 if any(m.search(text) for m in null) else None


def _postenstelle(muster: tuple[re.Pattern[str], ...], text: str) -> str | None:
    betrag, *null = muster
    for treffer in betrag.finditer(text):
        if not _VERNEINT.search(text[: treffer.start()]):
            return treffer[0]
    return next((t[0] for m in null if (t := m.search(text)) is not None), None)


def _ausschnitt(treffer: re.Match[str] | None) -> str | None:
    return None if treffer is None else treffer[0]


def _volumenzeile(zeile: str) -> bool:
    return bool(_VOLUMENZEILE.search(zeile)) and volumen_aus_zeile(zeile) is not None


def _rate_aus_text(text: str) -> tuple[float | None, int | None]:
    rate, mal = _RATE.search(text), _MAL_RATE.search(text)
    anzahl = _RATENZAHL.search(text)
    betrag = zahl(rate[1]) if rate else (zahl(mal[2]) if mal else None)
    raten = anzahl[1] if anzahl else (mal[1] if mal else None)
    return betrag, int(raten) if raten is not None else None


def phasen_aus_text(text: str) -> tuple[Preisphase, ...] | None:
    """Die Tarifphasen der ersten Tarifzeile mit Betrag samt ihren Folgezeilen."""
    stelle = _tarifstelle(text.splitlines())
    return None if stelle is None else _phasen_aus_zeile(" ".join(stelle.splitlines()))


def phasen_der_stelle(stelle: str) -> tuple[Preisphase, ...] | None:
    """Die Tarifphasen einer Stelle ohne Tarifwort, Zeilenumbrüche als Leerzeichen:
    die erste Gruppe eines Textmusters (o2 „19,99 €\nab dem 25. Monat: 29,99 €“)."""
    return _phasen_aus_zeile(" ".join(zahlen_ohne_leerraum(stelle).split()))


def _tarifstelle(zeilen: list[str]) -> str | None:
    """Die erste Tarifzeile mit Betrag und die direkt folgenden Zeilen „ab … Monat“."""
    for nummer, zeile in enumerate(zeilen):
        if _TARIFZEILE.search(zeile) and _BETRAG_RE.search(zeile):
            folge = itertools.takewhile(_FOLGEPHASE.match, zeilen[nummer + 1 :])
            return "\n".join([zeile, *folge])
    return None


def _phasen_aus_zeile(zeile: str) -> tuple[Preisphase, ...] | None:
    funde = _phasenfunde(zeile)
    belegt = [bereich for _, bereich in funde]
    phasen = [p for p, _ in funde if p is not None]
    frei = [b for b in _BETRAG_RE.finditer(zeile) if not _in(b.start(), belegt)]
    if frei and (not belegt or frei[0].start() < min(a for a, _ in belegt)):
        beginn = min((p.von_monat for p in phasen), default=None)
        bis = None if beginn is None else beginn - 1
        grundpreis = phase(1, bis, zahl(frei[0][1]))
        funde.append((grundpreis, frei[0].span()))
        phasen += [grundpreis] if grundpreis is not None else []
    if len(phasen) != len(funde):
        return None
    return tuple(sorted(phasen, key=lambda p: p.von_monat))


def _phasenfunde(zeile: str) -> list[tuple[Preisphase | None, tuple[int, int]]]:
    spannen, ab = _PHASE_SPANNE.finditer(zeile), _PHASE_AB.finditer(zeile)
    funde = [(phase(t[2], t[3], zahl(t[1])), t.span()) for t in spannen]
    funde += [(phase(t[1] or t[2], None, zahl(t[3])), t.span()) for t in ab]
    hinten = _PHASE_ERSTE.search(zeile)
    vorn = None if hinten else _PHASE_ERSTE_VORN.search(zeile)
    erste = hinten or vorn
    if erste is None:
        return funde
    monate, betrag = (erste[1], erste[2]) if hinten else (erste[2], erste[1])
    funde.append((phase(1, monate, zahl(betrag)), erste.span()))
    danach = _PHASE_DANACH.search(zeile, erste.end())
    if danach is not None:
        folge = phase(int(monate) + 1, None, zahl(danach[1]))
        funde.append((folge, danach.span()))
    return funde


def _in(stelle: int, bereiche: list[tuple[int, int]]) -> bool:
    return any(anfang <= stelle < ende for anfang, ende in bereiche)


def _volumen_aus_text(text: str) -> float | None:
    zeilen = (z for z in text.splitlines() if _VOLUMENZEILE.search(z))
    return next((w for w in map(volumen_aus_zeile, zeilen) if w is not None), None)
