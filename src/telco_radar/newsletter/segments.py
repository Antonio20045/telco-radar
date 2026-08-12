"""Segmente: einmal rendern, N-mal zustellen.

Zwei Personen mit denselben Filtern bekommen dieselbe Mail. Aus 200
Abonnenten mit 12 Filterkombinationen werden 12 Renderings und 200
Zustellungen - personalisiert bleiben nur die Anrede und die Abmelde-URL.

Der `segment_hash` ist der Schluessel dieser Buendelung UND die Haelfte des
Idempotenzschluessels beim Versand (`report_date` + `segment_hash` +
`subscriber_id`). Daraus folgt seine wichtigste Eigenschaft: **er muss
stabil sein.** Zwei Abos mit derselben Auswahl in anderer Reihenfolge oder
anderer Gross-/Kleinschreibung sind EIN Segment - sonst rendert der Lauf
zweimal dasselbe, und schlimmer: ein Wiederanlauf nach einer
Reihenfolgeaenderung haelt seinen eigenen Sendeplan fuer einen fremden und
verschickt alles noch einmal.

Deshalb wird der Hash ueber eine normalisierte, sortierte Form gerechnet und
nicht ueber das Abo-JSON. Ein Feld, das dem Abo spaeter dazukommt (ein
Anzeigename, ein Zaehler), darf die Buendelung nicht veraendern.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from .config import DIMENSIONEN, NewsletterKatalog
from .filters import Filtersatz, Treffer, waehle


def normalform(satz: Filtersatz) -> dict:
    """Die Form, ueber die gehasht wird. Sortiert und kleingeschrieben."""
    aus = {d: sorted({w.strip().lower() for w in satz.werte(d) if w.strip()})
           for d in DIMENSIONEN}
    # Stichwoerter tragen ihre Betriebsart mit: "5G Netz" als Phrase und
    # dieselben zwei Woerter als zwei Stichwoerter sind verschiedene Abos,
    # und sie bekommen verschiedene Mails.
    aus["keywords"] = sorted(
        {f"{s.mode}:{s.term.strip().lower()}" for s in satz.stichwoerter
         if s.term.strip()})
    return aus


def segment_hash(satz: Filtersatz) -> str:
    roh = json.dumps(normalform(satz), sort_keys=True, ensure_ascii=False,
                     separators=(",", ":"))
    return hashlib.sha256(roh.encode("utf-8")).hexdigest()[:16]


@dataclass
class Segment:
    hash: str
    filter: Filtersatz
    abo_ids: list[str] = field(default_factory=list)
    treffer: list[Treffer] = field(default_factory=list)

    @property
    def leer(self) -> bool:
        """Ein Segment ohne Treffer wird NICHT verschickt.

        Zweimal pro Woche eine Mail, in der nichts steht, erzieht zum
        Ignorieren - und zwar nicht nur fuer die leeren Ausgaben."""
        return not self.treffer


def bilde_segmente(abos, eintraege, katalog: NewsletterKatalog) -> list[Segment]:
    """Aus Abos und Eintraegen die Segmente dieser Ausgabe.

    Erwartet je Abo ein Objekt mit `.id` und `.filter` (ein `Abo` aus
    `subscription.py`). Gerechnet wird die Auswahl EINMAL je Segment, nicht
    je Abo - das ist der ganze Sinn der Uebung.
    """
    nach_hash: dict[str, Segment] = {}
    for abo in abos:
        h = segment_hash(abo.filter)
        segment = nach_hash.get(h)
        if segment is None:
            segment = Segment(hash=h, filter=abo.filter)
            segment.treffer = waehle(eintraege, abo.filter, katalog)
            nach_hash[h] = segment
        segment.abo_ids.append(abo.id)
    # Stabile Reihenfolge: der Sendeplan wird gepusht und spaeter mit sich
    # selbst verglichen. Eine wechselnde Reihenfolge sieht in jedem Diff wie
    # eine Aenderung aus.
    return sorted(nach_hash.values(), key=lambda s: s.hash)
