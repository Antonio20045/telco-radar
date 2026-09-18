"""PM-6: Das Wachstum der Geraete-Fragmente - gemessen, nicht geschaetzt.

WARUM ES DAS GIBT (Premortem FM 3, 17.09.2026): die Zeitreihen-Hauptansicht
(E2) laedt ihren Graph-Zustand aus `site/data/geraete-zeitreihe.html`. Dieses
Fragment wächst mit JEDEM Messtag der Bündel-Historie - und zwar_linear_,
weil jeder (Anbieter x Messtag)-Punkt Markup mitträgt (P1: klickbarer
Rechenweg je Messung; P4: Punkt plus Halo im SVG). Das Bündel-Fragment
`geraete-buendel.html` wächst dagegen mit der Zahl der MODELLE, nicht der
Messtage. Stand 18.09.2026: Zeitreihe 3.56 MB bei 6 Messtagen und 2562
Messpaaren, rund 1,4 KB je Messpaar - der Premortem-Schätzwert "~7 KB je
Paar" war also um Faktor fünf zu hoch, die Richtung stimmte aber.

Dieses Modul SETZT KEINEN DECKEL. Es macht das Wachstum messbar, damit die
PM-6-Entscheidung (01.10.2026, siehe `scripts/geraete_fragment_wachstum.py`)
auf einer echten Rate beruht statt auf einem einzigen Schätzwert - dieselbe
Lehre wie bei der Seitenhöhen-Bombe (`UEBERSICHT_MAX_ZEILEN`, 30.08.2026):
die Grenze kommt VOR dem Umkippen, nicht danach.

DIE DREI ZAHLEN der Protokollzeile `Fragmentgroesse:` (ein Ziel, eine
Quelle - Skript und Pipeline-Lauf lesen sie hier, nicht je neu):

  1. Messtage   distinct `datum` in geraete_tco_historie.jsonl
  2. Messpaare  Zeilen (buendel_id, datum) - idempotent, ein zweiter Lauf
                am selben Tag ersetzt seine Zeile und zählt nicht doppelt
  3. Fragment-KB  Bytes beider site/data-Fragmente zusammen

DIE EINE ANNAHME der Prognose: Bytes wachsen LINEAR durch den Nullpunkt
(bytes_je_paar * paare). Das fixede Markup je (Modell x Band)-Block
(derzeit 170 Bloecke) geht damit in die Rate ein - bei 15 Messpaaren je
Block ist der Fehler klein, und die Rate wird ohnehin bei jedem Lauf neu
gemessen. Vorlagewechsel (P1: +2,4 MB ueber Nacht ohne neuen Messtag)
sind SPRUENGE, die die Prognose nicht kennt - sie steht deshalb IMMER
mit ihrem Messdatum daneben.
"""
from __future__ import annotations

import gzip
import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

# Die PM-6-Entscheidungsgrenze: 5 MB ROHBYTES je Fragment (nicht gzip -
# das SVG-Markup ist so repetitiv, dass gzip es auf ~4,5 % staucht; die
# 5 MB sind eine Grenze fuer Repository und Browser-Parsing, nicht fuer
# die Leitung). Eine Grenze der SUMME beider Fragmente waere heute schon
# ueberschritten (5,1 MB) und wuerde die Entscheidung unmoeglich machen.
GRENZE_BYTES = 5_000_000

# Wie weit die Prognosetabelle reicht, wenn die Grenze vorher nicht fällt.
HORIZONT_TAGE = 60

# Fixe Tagesabstaende der Prognosetabelle (plus der Tag der Grenze selbst,
# falls er innerhalb des Horizonts liegt).
PROGNOSE_SCHRITTE = (1, 2, 3, 7, 14, 30, 60)

ZEITREIHE_NAME = "geraete-zeitreihe.html"
BUNDEL_NAME = "geraete-buendel.html"


@dataclass(frozen=True)
class Bestand:
    """Was in der Historie steht - die Messgrundlage, keine Ableitung.

    `tage` traegt je Messtag das Datum und die Zahl der Messpaare NEU an
    diesem Tag, aufsteigend. `paare` ist die Summe - nach dem Ursprung der
    Datei identisch mit der Zahl der (buendel_id, datum)-Zeilen.
    """

    tage: tuple[tuple[date, int], ...]
    paare: int

    @property
    def messtage(self) -> int:
        return len(self.tage)

    @property
    def anker(self) -> date | None:
        """Letzter Messtag - das Datum, ab dem die Prognose rechnet.

        Bewusst der letzte MESSTAG und nicht "heute": zwischen dem letzten
        Messtag und heute ist nichts gewachsen, und ein Feiertag ohne Lauf
        wuerde die Prognose sonst altern lassen. `heute` dient nur der
        Anzeige.
        """
        return self.tage[-1][0] if self.tage else None

    def rate_je_messtag(self) -> float | None:
        """Messpaare je Messtag (Mittel) - bei einem Messtag unbestimmt.

        Ein einziger Messtag hat keine Rate (die Division durch 1 wuerde
        den ersten Tag zur Prognose erheben). Die PM-6-Regel will ohnehin
        14 Tage Daten, bevor die Zahl entscheidet.
        """
        if self.messtage < 2:
            return None
        return self.paare / self.messtage


def lies_historie(pfad: Path) -> Bestand:
    """Liest geraete_tco_historie.jsonl: ein (datum, paare) je Messtag.

    Fehlt die Datei, ist das eine leere Messung (Bestand mit 0 Messtagen)
    und kein Fehler - der erste Lauf ohne Buendel legt sie noch nicht an.
    Eine unlesbare Zeile wird uebersprungen und gemeldet, eine unlesbare
    DATEI liefert ebenfalls einen leeren Bestand: die Messung soll nie
    den Lauf kosten, sie ist Protokoll, nicht Guete.
    """
    pfad = Path(pfad)
    if not pfad.exists():
        return Bestand(tage=(), paare=0)
    je_tag: dict[date, dict[str, None]] = {}
    paare: set[tuple[str, str]] = set()
    try:
        zeilen = pfad.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        log.warning("%s unlesbar (%s) - Fragmentmessung ohne Historie",
                    pfad.name, exc)
        return Bestand(tage=(), paare=0)
    for zeile in zeilen:
        if not zeile.strip():
            continue
        try:
            satz = json.loads(zeile)
        except json.JSONDecodeError:
            continue
        bid, datum = satz.get("id"), satz.get("datum")
        if not bid or not datum:
            continue
        try:
            tag = date.fromisoformat(str(datum))
        except ValueError:
            continue
        # Idempotenz der Historie nachbilden: derselbe (id, datum)-Schluessel
        # ersetzt seine Zeile in der Datei - hier zaehlt er genau einmal.
        if (str(bid), str(datum)) in paare:
            continue
        paare.add((str(bid), str(datum)))
        je_tag.setdefault(tag, {})[str(bid)] = None
    tage = tuple((tag, len(ids)) for tag, ids in sorted(je_tag.items()))
    return Bestand(tage=tage, paare=len(paare))


@dataclass(frozen=True)
class Fragment:
    """Eine Fragment-Datei mit rohen und gezippten Bytes."""

    name: str
    bytes: int
    gzip_bytes: int

    @property
    def kb(self) -> int:
        return self.bytes // 1024

    @property
    def ratio(self) -> float:
        return self.gzip_bytes / self.bytes if self.bytes else 0.0


def fragment_groessen(site_dir: Path) -> list[Fragment]:
    """Beide Ladegueter unter site/data/ mit Bytes und gzip-Groesse.

    Fehlt eine Datei, fehlt sie in der Liste - "nicht da" ist keine 0.
    `gzip.compress(..., mtime=0)` haelt die Messung deterministisch (der
    Zeitstempel ginge sonst in die Zahl ein, ohne dass sich das Fragment
    geaendert hat).
    """
    out: list[Fragment] = []
    for name in (ZEITREIHE_NAME, BUNDEL_NAME):
        pfad = Path(site_dir) / "data" / name
        if not pfad.exists():
            continue
        roh = pfad.read_bytes()
        out.append(Fragment(name=name, bytes=len(roh),
                            gzip_bytes=len(gzip.compress(roh, mtime=0))))
    return out


def prognose(bytes_je_paar: float, paare: int, rate: float,
             grenze: int, anker: date) -> tuple[date, int, bool]:
    """Erster Tag, an dem das Zeitreihen-Fragment die Grenze ERREICHT.

    Linear durch den Nullpunkt: bytes(d) = bytes_je_paar * (paare +
    rate * d) mit d in Messtagen ab dem Anker (Annahme: 1 Messtag/Tag,
    der naechtliche Lauf haelt sie, ein Ausfall verdoppelt hoechstens
    den Schritt des Folgetags). Zurueck kommen (Datum, Messtage bis zur
    Grenze, ob die Grenze am Anker schon ueberschritten war) - die
    ceil-Rechnung rundet AUF, ein Tag "genau auf der Grenze" zaehlt als
    gehalten.
    """
    if bytes_je_paar <= 0 or rate <= 0:
        raise ValueError("Prognose braucht bytes_je_paar > 0 und rate > 0")
    paare_grenze = grenze / bytes_je_paar
    if paare_grenze <= paare:
        return anker, 0, True
    tage = -(-(paare_grenze - paare) // rate)   # ceil ohne float-Rundung
    return anker + timedelta(days=int(tage)), int(tage), False


def protokoll_zeile(root: Path) -> str | None:
    """Die EINE Zeile 'Fragmentgroesse:' - drei Zahlen, eine Quelle.

    None heisst "nichts zu sagen" (keine Historie) - dann bleibt die
    Zeile weg, statt 0/0/0 zu melden und einen Messpunkt vorzutaeuschen.
    Fehlen die Fragmente (erster Lauf vor dem ersten Render), stehen die
    beiden Messzahlen trotzdem: die Historie ist frisch, der Render laeuft
    hinterher, und die Reihe reißt nicht.
    """
    root = Path(root)
    bestand = lies_historie(root / "data" / "state" / "geraete_tco_historie.jsonl")
    if not bestand.tage:
        return None
    fragmente = fragment_groessen(root / "site")
    if fragmente:
        groesse = f"{sum(f.kb for f in fragmente)} KB Fragmente"
    else:
        groesse = "kein Fragment auf Platt (Render laeuft nach diesem Schritt)"
    return (f"Fragmentgroesse: {bestand.messtage} Messtage, "
            f"{bestand.paare} Messpaare, {groesse}")
