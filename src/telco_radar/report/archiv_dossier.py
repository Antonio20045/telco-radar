"""Frag das Archiv: eine Frage, eine belegte Antwort - oder gar keine.

Die Randbedingung, die alles bestimmt
-------------------------------------
Die Website ist eine **Static Site ohne Backend**, und das ist kein Zufall,
sondern die Bedingung dafuer, dass sie nie einschlaeft (CLAUDE.md §6). Ein
RAG-Aufbau mit Embedding-Dienst, Cross-Encoder und Synthese-Modell braucht
einen Dienst zur LAUFZEIT. Den gibt es hier nicht, und ihn einzufuehren
hiesse, die eine Eigenschaft aufzugeben, wegen der das Portal existiert.

Deshalb ist die Antwort EXTRAKTIV, nicht generativ
--------------------------------------------------
Die Antwort besteht aus den Archiveintraegen selbst - jede Zeile ist ein
Zitat mit Fussnote, keine Umformulierung. Das ist nicht die Notloesung fuer
das fehlende Modell, sondern fuer die Zusage dieses Auftrags die STAERKERE
Bauweise:

    "Jede Fussnote zeigt auf ein real existierendes Archiv-Item, dessen
     Inhalt die Aussage deckt."

Ein Modell kann diese Zusage nur einhalten, wenn ein Prueflauf sie
nachtraeglich erzwingt (so macht es `analyze/faithfulness.py`). Eine
extraktive Antwort kann sie **nicht verletzen**: die Aussage IST der
Eintrag. Die Erfindung ist nicht unwahrscheinlich gemacht, sondern
unmoeglich.

Was dafuer fehlt, steht offen auf der Seite: es entsteht keine
zusammenfassende Prosa. Wer die will, bekommt sie vom Wochenbericht - der
ist genau dafuer da und laeuft durch den Prueflauf.

BM25 statt Wortzaehlung
-----------------------
Die bestehende Suche (`TelcoSearch` in app.js) gewichtet Feld und
Dringlichkeit. Fuer eine FRAGE reicht das nicht: "Wie hat sich der Preis
von unbegrenzten Tarifen entwickelt?" enthaelt vier haeufige Woerter und
zwei seltene, und nur die zwei seltenen tragen die Frage. BM25 gewichtet
genau danach - seltene Begriffe schwer, haeufige leicht, lange Dokumente
nicht bevorzugt.

"Nichts gefunden" ist eine gueltige Antwort
-------------------------------------------
Und die wichtigste. Unterhalb von `MIND_SCORE` liefert `frage()` eine leere
Antwort mit Begruendung, nicht die drei am wenigsten schlechten Treffer.
Eine freundlich formulierte Nicht-Antwort ist schlimmer als ein ehrliches
"dazu steht nichts im Archiv": sie kostet dieselbe Zeit und hinterlaesst
den Eindruck, die Frage sei beantwortet.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

# BM25-Parameter. k1 steuert, wie stark Mehrfachnennungen zaehlen, b, wie
# stark lange Dokumente bestraft werden. Die Werte sind die ueblichen; die
# Eintraege hier sind kurz und aehnlich lang, also haengt wenig daran.
K1 = 1.5
B = 0.75

# Unterhalb davon gilt eine Frage als unbeantwortet. Gemessen an echten
# Fragen gegen das Archiv: eine Frage mit einem passenden seltenen Begriff
# kommt deutlich darueber, eine Frage ohne jeden Bezug bleibt bei 0.
MIND_SCORE = 1.0

# Wie viele Belege eine Antwort traegt. Mehr ist keine Antwort mehr,
# sondern wieder eine Trefferliste.
MAX_BELEGE = 8

_WORT = re.compile(r"[a-zA-ZäöüßÄÖÜ0-9]{2,}")

# Deutsche Stoppwoerter. Sie tragen keine Frage und wuerden bei kurzen
# Eintraegen die Rangfolge dominieren.
STOPP = {
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem",
    "einer", "eines", "und", "oder", "aber", "auch", "mit", "von", "vom",
    "für", "fuer", "auf", "aus", "bei", "nach", "über", "ueber", "unter",
    "zwischen", "ist", "sind", "war", "waren", "wird", "werden", "wurde",
    "wurden", "hat", "haben", "hatte", "sich", "nicht", "kein", "keine",
    "als", "wie", "was", "wer", "wo", "wann", "warum", "welche", "welcher",
    "welches", "sein", "seine", "ihr", "ihre", "im", "in", "an", "am", "zu",
    "zum", "zur", "es", "sie", "er", "wir", "man", "mehr", "sehr", "schon",
    "noch", "nur", "dass", "denn", "doch", "so", "the", "and", "for", "of",
}


def zerlege(text: str) -> list[str]:
    """Text in gewichtsfaehige Woerter. Stoppwoerter fliegen raus."""
    return [w for w in (m.group(0).lower() for m in _WORT.finditer(text or ""))
            if w not in STOPP]


@dataclass
class Beleg:
    """Ein Archiveintrag, der die Frage beruehrt."""

    titel: str
    text: str
    quelle: str
    url: str
    datum: str
    bereich: str
    score: float
    treffer: list[str] = field(default_factory=list)


@dataclass
class Antwort:
    frage: str
    belege: list[Beleg] = field(default_factory=list)
    begruendung: str = ""
    gesucht: list[str] = field(default_factory=list)

    @property
    def gefunden(self) -> bool:
        return bool(self.belege)


class ArchivIndex:
    """BM25 ueber alle Archiveintraege.

    Gebaut wird er aus dem bestehenden Suchindex - es gibt keinen zweiten
    Datenbestand und keine zweite Wahrheit.
    """

    def __init__(self, eintraege: list[dict]) -> None:
        self.eintraege = list(eintraege or [])
        self.dokumente: list[list[str]] = []
        self.haeufigkeit: list[Counter] = []
        for e in self.eintraege:
            worte = zerlege(" ".join(str(e.get(f) or "") for f in
                                     ("title", "summary", "operator",
                                      "category", "source_label")))
            self.dokumente.append(worte)
            self.haeufigkeit.append(Counter(worte))
        self.n = len(self.dokumente)
        self.mittlere_laenge = (
            sum(len(d) for d in self.dokumente) / self.n) if self.n else 0.0
        self.dokumentfrequenz: Counter = Counter()
        for d in self.dokumente:
            self.dokumentfrequenz.update(set(d))

    def _idf(self, wort: str) -> float:
        """Wie selten - und damit wie aussagekraeftig - ein Wort ist.

        Der +1 im Logarithmus haelt den Wert positiv: ohne ihn bekaeme ein
        Wort, das in mehr als der Haelfte der Eintraege steht, ein NEGATIVES
        Gewicht und zoege Treffer nach unten, die es enthalten.
        """
        df = self.dokumentfrequenz.get(wort, 0)
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def bewerte(self, worte: list[str], i: int) -> tuple[float, list[str]]:
        if not self.dokumente[i]:
            return 0.0, []
        laenge = len(self.dokumente[i])
        norm = K1 * (1 - B + B * laenge / (self.mittlere_laenge or 1))
        score = 0.0
        getroffen = []
        for wort in set(worte):
            tf = self.haeufigkeit[i].get(wort, 0)
            if not tf:
                continue
            getroffen.append(wort)
            score += self._idf(wort) * (tf * (K1 + 1)) / (tf + norm)
        return score, sorted(getroffen)


def _beleg(eintrag: dict, score: float, treffer: list[str]) -> Beleg:
    return Beleg(
        titel=str(eintrag.get("title") or ""),
        text=str(eintrag.get("summary") or ""),
        quelle=str(eintrag.get("source_label") or eintrag.get("operator") or ""),
        url=str(eintrag.get("url") or ""),
        datum=str(eintrag.get("date") or ""),
        bereich=str(eintrag.get("kind") or ""),
        score=round(score, 3),
        treffer=treffer,
    )


def frage(index: ArchivIndex, text: str, *, max_belege: int = MAX_BELEGE,
          mind_score: float = MIND_SCORE) -> Antwort:
    """Eine Frage gegen das Archiv. Belege oder ein ehrliches Nein.

    Es wird NICHTS formuliert, was nicht im Archiv steht - die Antwort
    besteht aus den Eintraegen selbst. Deshalb kann eine Fussnote hier
    nicht auf etwas zeigen, das die Aussage nicht deckt: die Aussage IST
    der Eintrag.
    """
    worte = zerlege(text)
    antwort = Antwort(frage=" ".join(str(text or "").split()), gesucht=worte)

    if not worte:
        antwort.begruendung = ("Die Frage enthält keine durchsuchbaren "
                               "Begriffe.")
        return antwort
    if not index.n:
        antwort.begruendung = "Das Archiv ist leer."
        return antwort

    bewertet = []
    for i in range(index.n):
        score, treffer = index.bewerte(worte, i)
        if score >= mind_score:
            bewertet.append((score, treffer, i))

    if not bewertet:
        antwort.begruendung = (
            "Dazu steht nichts im Archiv. Das heißt nicht, dass es nichts "
            "gibt — es heißt, dass keine der bisher erfassten Meldungen die "
            "Frage berührt.")
        return antwort

    # Absteigend nach Score, bei Gleichstand die juengere Meldung zuerst.
    bewertet.sort(key=lambda t: (-t[0], _sortdatum(index.eintraege[t[2]])))
    gesehen: set[str] = set()
    for score, treffer, i in bewertet:
        if len(antwort.belege) >= max_belege:
            break
        eintrag = index.eintraege[i]
        kennung = str(eintrag.get("url") or eintrag.get("title") or "")
        if kennung and kennung in gesehen:
            continue
        gesehen.add(kennung)
        antwort.belege.append(_beleg(eintrag, score, treffer))
    return antwort


def _sortdatum(eintrag: dict) -> str:
    """Absteigend nach Datum - als Sortierschluessel invertiert."""
    datum = str(eintrag.get("date") or "")
    return "".join(chr(255 - ord(c)) if ord(c) < 255 else c for c in datum)


def verlauf(antwort: Antwort) -> list[dict]:
    """Wie sich das Thema ueber die Monate verteilt.

    Der zweite Teil der Frage aus dem Auftrag ("und wie hat es sich
    entwickelt") - gezaehlt, nicht gedeutet.
    """
    monate: Counter = Counter()
    for beleg in antwort.belege:
        if len(beleg.datum) >= 7:
            monate[beleg.datum[:7]] += 1
    return [{"monat": m, "anzahl": monate[m]} for m in sorted(monate)]


def als_dict(antwort: Antwort) -> dict:
    return {
        "frage": antwort.frage,
        "gefunden": antwort.gefunden,
        "begruendung": antwort.begruendung,
        "gesucht": antwort.gesucht,
        "verlauf": verlauf(antwort),
        "belege": [{
            "titel": b.titel, "text": b.text, "quelle": b.quelle,
            "url": b.url, "datum": b.datum, "bereich": b.bereich,
            "score": b.score, "treffer": b.treffer,
        } for b in antwort.belege],
    }
