"""Belegbilder zu gemessenen Preisen: Dateiname, Release-Tags, Schwelle, Aufbewahrung.

Der Klick-Tageslauf macht zu jedem gemessenen Preis ein Bild der Anbieterseite. Die
Bilder liegen als Anhänge von GitHub-Releases, nie im Repo (öffentlich, die Historie
wüchse für immer): je Tag ein Release ``belege-JJJJ-MM-TT``, nach ``AUFBEWAHRUNG_TAGE``
Tagen gelöscht; die Bilder großer Preisänderungen liegen zusätzlich im Release
``belege-gross-JJJJ-MM`` und bleiben ``AUFBEWAHRUNG_GROSS_TAGE`` Tage.

Der Dateiname trägt die stabilen Schlüssel:
``<geraet_id>__<anbieter_id>__<JJJJ-MM-TT>.webp``.
``geraet_id`` ist Gerät und Speicher des Katalogs
(``geraete_tco_karten.modell_schluessel``),
``anbieter_id`` der ASCII-Schlüssel des Anbieternamens (``anbieter_schluessel``),
nie ein Titeltext. Wer ein Bild von Hand hochlädt, benennt es genauso; die Seite
liest die Anhänge der Releases (``beleg_manifest``) und kennt keinen zweiten Weg.

Große Änderung: die Gesamtkosten über 24 Monate weichen von der letzten Messung
derselben Konfiguration um mindestens ``GROSS_PROZENT`` Prozent ODER ``GROSS_EURO`` Euro
ab. Ohne frühere Messung oder bei einer Lücke (``None``) ist die Änderung nie groß: was
nicht vergleichbar ist, fällt aus dem Vergleich (CLAUDE.md Clean Code 3, 4).

Reines Stdlib-Modul ohne Netz: Workflow-Skripte und Seite lesen dieselben Zahlen
(CLAUDE.md Clean Code 1, 7).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

REPO = "Antonio20045/telco-radar"
AUFBEWAHRUNG_TAGE = 7
AUFBEWAHRUNG_GROSS_TAGE = 90
ANZEIGE_TAGE = AUFBEWAHRUNG_TAGE
"""Die Seite zeigt alle Belege dieser letzten Tage (wie ``ist_abgelaufen``)."""
ANZEIGE_GROSS_ANZAHL = 3
"""Dazu höchstens so viele ältere große Änderungen (die jüngsten der 90 Tage)."""
GROSS_PROZENT = 5
GROSS_EURO = 50
MAX_ANHAENGE_JE_RELEASE = 900
"""GitHub erlaubt höchstens 1000 Anhänge je Release; der Rest ist Reserve."""

ENDUNG = ".webp"
TRENNER = "__"
TAG_TAG = "belege-"
TAG_GROSS = "belege-gross-"
_ID = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_NAME = re.compile(
    rf"^({_ID}){TRENNER}({_ID}){TRENNER}(\d{{4}}-\d{{2}}-\d{{2}}){ENDUNG}$"
)
_TAG = re.compile(r"^belege-(\d{4}-\d{2}-\d{2})(?:-(\d+))?$")
_TAG_GROSS = re.compile(r"^belege-gross-(\d{4})-(\d{2})(?:-(\d+))?$")
_ID_PRUEFUNG = re.compile(rf"^{_ID}$")


@dataclass(frozen=True)
class Dateiname:
    """Der zerlegte Dateiname eines Belegs."""

    geraet_id: str
    anbieter_id: str
    datum: date

    @property
    def schluessel(self) -> str:
        """Gerät und Anbieter ohne Datum."""
        return f"{self.geraet_id}{TRENNER}{self.anbieter_id}"


def anbieter_schluessel(anbieter: str) -> str:
    """Stabiler ASCII-Schlüssel eines Anbieternamens, immer im Schema von ``dateiname``.

    ``1&1`` wird ``1-1``, ``ALDI TALK`` wird ``aldi-talk``, ``Telefónica`` wird
    ``telefonica``. Bleibt nach dem Falten nichts übrig (nur Zeichen außerhalb von
    ASCII), ist der Schlüssel ``anbieter-<8 Zeichen Prüfsumme des Namens>``: stabil, nie
    leer, nie ein Fehler, der das Hochladen aller anderen Bilder stoppt. Seite und
    Hochladen rufen dieselbe Funktion (CLAUDE.md Clean Code 1).
    """
    gefaltet = unicodedata.normalize("NFKD", anbieter or "").encode("ascii", "ignore")
    schluessel = re.sub(r"[^a-z0-9]+", "-", gefaltet.decode("ascii").lower()).strip("-")
    if schluessel:
        return schluessel
    pruefsumme = hashlib.sha1((anbieter or "").encode("utf-8")).hexdigest()[:8]
    return f"anbieter-{pruefsumme}"


def dateiname(geraet_id: str, anbieter_id: str, datum: date) -> str:
    """``<geraet_id>__<anbieter_id>__<JJJJ-MM-TT>.webp``; wirft bei unbrauchbarer ID."""
    for name, wert in (("geraet_id", geraet_id), ("anbieter_id", anbieter_id)):
        if not _ID_PRUEFUNG.match(wert or ""):
            raise ValueError(f"{name} unbrauchbar: {wert!r}")
    return f"{geraet_id}{TRENNER}{anbieter_id}{TRENNER}{datum.isoformat()}{ENDUNG}"


def zerlege_dateiname(name: str) -> Dateiname | None:
    """Die Schlüssel eines Dateinamens; ``None``, wenn er nicht im Schema liegt."""
    treffer = _NAME.match(name or "")
    if not treffer:
        return None
    try:
        datum = date.fromisoformat(treffer.group(3))
    except ValueError:
        return None
    return Dateiname(treffer.group(1), treffer.group(2), datum)


def tages_tag(tag: date, teil: int = 1) -> str:
    """``belege-JJJJ-MM-TT``; ab dem zweiten Teil mit Zähler (``…-2``)."""
    basis = f"{TAG_TAG}{tag.isoformat()}"
    return basis if teil <= 1 else f"{basis}-{teil}"


def gross_tag(tag: date, teil: int = 1) -> str:
    """``belege-gross-JJJJ-MM``; ab dem zweiten Teil mit Zähler."""
    basis = f"{TAG_GROSS}{tag:%Y-%m}"
    return basis if teil <= 1 else f"{basis}-{teil}"


def ist_gross_tag(tag: str) -> bool:
    """Ist es ein Monats-Release für große Änderungen?"""
    return bool(_TAG_GROSS.match(tag))


def ist_beleg_tag(tag: str) -> bool:
    """Gehört der Tag ins Schema? Fremde Releases fasst nichts an."""
    return bool(_TAG.match(tag) or _TAG_GROSS.match(tag))


def _cent(euro: float) -> int:
    return round(euro * 100)


def ist_grosse_aenderung(vorher: float | None, jetzt: float | None) -> bool:
    """Wahr bei mindestens ``GROSS_PROZENT`` % oder ``GROSS_EURO`` € Abweichung.

    Gerechnet in Cent, damit der Rand exakt trifft (50,00 € sind groß, 49,99 € nicht).
    """
    if vorher is None or jetzt is None:
        return False
    unterschied = abs(_cent(jetzt) - _cent(vorher))
    if unterschied == 0:
        return False
    if unterschied >= GROSS_EURO * 100:
        return True
    return unterschied * 100 >= GROSS_PROZENT * abs(_cent(vorher))


def ist_anzeige_neu(datum: date, heute: date) -> bool:
    """Gehört der Beleg zu den letzten ``ANZEIGE_TAGE`` Tagen? (Alter 7 ja, 8 nein.)"""
    return (heute - datum).days <= ANZEIGE_TAGE


def release_ende(tag: str) -> date | None:
    """Der letzte Tag, den ein Release im Schema abdeckt; sonst ``None``.

    Tages-Release: sein Tag. Monats-Release: der letzte Tag des Monats.
    """
    treffer = _TAG.match(tag)
    if treffer:
        try:
            return date.fromisoformat(treffer.group(1))
        except ValueError:
            return None
    treffer = _TAG_GROSS.match(tag)
    if treffer:
        jahr, monat = int(treffer.group(1)), int(treffer.group(2))
        if not 1 <= monat <= 12:
            return None
        return date(jahr + (monat == 12), monat % 12 + 1, 1) - timedelta(days=1)
    return None


def aufbewahrung_tage(gross: bool) -> int:
    """Aufbewahrung in Tagen."""
    return AUFBEWAHRUNG_GROSS_TAGE if gross else AUFBEWAHRUNG_TAGE


def ist_abgelaufen(datum: date, heute: date, gross: bool) -> bool:
    """Alter 7 bleibt, Alter 8 geht (große Änderung: 90 bleibt, 91 geht)."""
    return (heute - datum).days > aufbewahrung_tage(gross)


def release_abgelaufen(tag: str, heute: date) -> bool:
    """Gehört das Release gelöscht? Nur Tags im Schema; fremde Tags: nie."""
    ende = release_ende(tag)
    return ende is not None and ist_abgelaufen(ende, heute, ist_gross_tag(tag))


def ist_sichtbar(tag: str, datei: str, heute: date) -> bool:
    """Zeigt die Seite dieses Bild? Löschen und Anzeigen fragen dasselbe (Clean Code 7).

    Maßgeblich ist das Datum im Dateinamen, nicht das des Releases: ein Bild von Hand im
    Tages-Release von morgen trägt sein eigenes Datum. Dateien außerhalb des Schemas und
    Releases außerhalb des Schemas sind nie sichtbar und werden nie gelöscht.
    """
    name = zerlege_dateiname(datei)
    if name is None or not ist_beleg_tag(tag):
        return False
    return not ist_abgelaufen(name.datum, heute, ist_gross_tag(tag))
