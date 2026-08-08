"""Frühwarn-Board: die Fragen, die dauerhaft offen sind.

Der Wochenbericht beantwortet "was ist passiert?". Er kann nicht beantworten
"wie steht es um die Fragen, die uns seit Monaten beschaeftigen?" - dafuer
muesste jemand jede Woche dieselben fuenf Dinge nachschlagen und sich merken,
was beim letzten Mal dastand.

Das ist die Methode "Indicators & Warnings": nicht alle Neuigkeiten quer
lesen, sondern VORHER festlegen, worauf man wartet, und dann nur noch
pruefen, ob es eingetreten ist. Der Wert steckt im "vorher" - ein Indikator,
der nach dem Ereignis formuliert wird, ist keine Warnung, sondern eine
Erklaerung. Deshalb stehen die Indikatoren in einer Konfigurationsdatei und
werden nicht aus den Meldungen abgeleitet.

Warum das hier kein Modell braucht
----------------------------------
Ein Indikator muss falsifizierbar sein, also aus Woertern bestehen, die in
einer Meldung stehen oder nicht stehen. Wer das ein Modell entscheiden
laesst, bekommt jede Woche eine andere Auslegung derselben Frage - und damit
genau das Gegenteil eines Frühwarnsystems.

"Ruhend" ist ein Ergebnis
-------------------------
Eine Frage, zu der seit sechs Wochen nichts kommt, ist beantwortet: es
passiert gerade nichts. Diese Zeile wegzulassen waere der Fehler - dann
sieht das Board jede Woche gleich voll aus, und niemand merkt, dass eine
Frage zur Ruhe gekommen ist.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

AKTIV, BEOBACHTET, RUHEND = "aktiv", "beobachtet", "ruhend"

# Wie viele Belege je Indikator gezeigt werden. Mehr als zwei macht aus dem
# Board eine zweite Meldungsliste.
MAX_BELEGE = 2


@dataclass
class Indikator:
    name: str
    stichworte: list[str] = field(default_factory=list)
    marken: list[str] = field(default_factory=list)
    _wort: list[re.Pattern] = field(default_factory=list)
    _marke: list[re.Pattern] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._wort = [_muster(s) for s in self.stichworte if s]
        self._marke = [_muster(m) for m in self.marken if m]

    def trifft(self, h: dict) -> bool:
        text = " ".join(str(h.get(f) or "") for f in
                        ("headline", "title", "summary", "schlagzeile")).lower()
        if not any(p.search(text) for p in self._wort):
            return False
        if not self._marke:
            return True
        # Die Marke darf im Absenderfeld ODER im Text stehen: eine
        # Fachpressemeldung ueber die Telekom traegt sie oft nur im Titel.
        absender = str(h.get("operator") or h.get("source") or "").lower()
        return any(p.search(absender) or p.search(text) for p in self._marke)


def _muster(begriff: str) -> re.Pattern:
    """Wortgrenzen - ohne sie faende "d2d" jedes "ad2do" und "O2" jedes
    "CO2". Dieselbe Regel wie in analyze/competitors.py."""
    return re.compile(r"(?<!\w)" + re.escape(begriff.strip().lower()) + r"(?!\w)")


@dataclass
class Frage:
    frage: str
    warum: str = ""
    indikatoren: list[Indikator] = field(default_factory=list)


def lade_fragen(root: Path) -> tuple[list[Frage], int]:
    pfad = Path(root) / "config" / "fruehwarnung.yaml"
    if not pfad.exists():
        return [], 4
    daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    fragen = []
    for f in (daten.get("fragen") or []):
        fragen.append(Frage(
            frage=str(f.get("frage") or ""),
            warum=" ".join(str(f.get("warum") or "").split()),
            indikatoren=[Indikator(name=str(i.get("name") or ""),
                                   stichworte=list(i.get("stichworte") or []),
                                   marken=list(i.get("marken") or []))
                         for i in (f.get("indikatoren") or [])]))
    return fragen, int(daten.get("fenster_ausgaben", 4) or 4)


def _beleg(h: dict, datum: str) -> dict:
    return {"titel": (h.get("schlagzeile") or h.get("headline")
                      or h.get("title") or "")[:120],
            "url": h.get("url") or "",
            "absender": h.get("operator") or h.get("source") or "",
            "datum": datum}


def aufbereiten(wochen: list[dict], root: Path) -> dict:
    """`wochen` ist je Ausgabe {"date", "highlights"} - dieselbe Liste, aus
    der die Wettbewerbsseite ihre Chronik baut."""
    fragen, fenster = lade_fragen(root)
    if not fragen:
        return {"aktiv": False, "fragen": []}

    sortiert = sorted((w for w in wochen if w.get("date")),
                      key=lambda w: w["date"], reverse=True)
    if not sortiert:
        return {"aktiv": False, "fragen": []}
    aktuelle = sortiert[0]
    frueher = sortiert[1:fenster]

    ausgabe = []
    for frage in fragen:
        zeilen = []
        for ind in frage.indikatoren:
            jetzt = [_beleg(h, aktuelle["date"])
                     for h in (aktuelle.get("highlights") or []) if ind.trifft(h)]
            davor = [_beleg(h, w["date"]) for w in frueher
                     for h in (w.get("highlights") or []) if ind.trifft(h)]
            zustand = AKTIV if jetzt else (BEOBACHTET if davor else RUHEND)
            zeilen.append({
                "name": ind.name,
                "zustand": zustand,
                "n_jetzt": len(jetzt),
                "n_fenster": len(jetzt) + len(davor),
                "belege": (jetzt or davor)[:MAX_BELEGE],
            })
        ausgabe.append({
            "frage": frage.frage,
            "warum": frage.warum,
            "indikatoren": zeilen,
            # Der Zustand der FRAGE ist der staerkste ihrer Indikatoren.
            "zustand": (AKTIV if any(z["zustand"] == AKTIV for z in zeilen)
                        else BEOBACHTET
                        if any(z["zustand"] == BEOBACHTET for z in zeilen)
                        else RUHEND),
        })

    # Aktive Fragen zuerst, ruhende zuletzt - aber ALLE bleiben stehen. Eine
    # Frage, zu der seit Wochen nichts kommt, ist beantwortet, und genau das
    # soll man sehen koennen.
    rang = {AKTIV: 0, BEOBACHTET: 1, RUHEND: 2}
    ausgabe.sort(key=lambda f: rang[f["zustand"]])
    return {
        "aktiv": True,
        "fragen": ausgabe,
        "fenster": fenster,
        "n_aktiv": sum(1 for f in ausgabe if f["zustand"] == AKTIV),
    }
