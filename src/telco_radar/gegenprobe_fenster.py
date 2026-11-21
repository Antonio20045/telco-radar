"""Fenster der Gegenprobe: jedes angezeigte Bündel binnen ``GEGENPROBE_FENSTER_TAGE``.

Abnahmekriterium 2 (Antonio, 21.11.2026): jedes Bündel der Geräteseite ist innerhalb
eines festen Fensters unabhängig gegengeprüft, jede Preisänderung am Tag ihres
Auftretens. „Zuletzt gegengeprüft“ steht nicht am Bündel, sondern folgt aus den
Tagesdateien (``gegenprobe.lies_alle``) über ``Gegenproben.zum_preis``: dieselbe
Stelle, an der die Seite die Gegenprobe eines Preises findet (dasselbe Bündel oder
dasselbe Angebot in anderer Farbe mit gleichen Gesamtkosten; ein Bündel ohne
Gesamtkosten nur seine eigene Prüfung ohne Gesamtkosten). Nur eine gelesene Seite
zählt (``gegenprobe.GEPRUEFT``); ein geänderter Preis ist wieder ungeprüft.

Reihenfolge eines Laufs (``kandidaten``): (a) die Preisänderungen des Tages in der
Folge von ``gegenprobe.auswahl``, (b) die fälligen Bündel, nie geprüfte zuerst, dann
die älteste Prüfung, bei Gleichstand der ältere Fehlversuch. Fällig ist ein Bündel
``VORLAUF_TAGE`` vor Ablauf seines Fensters. Was heute zu diesem Preis schon geöffnet
wurde, kommt nicht noch einmal dran: ein zweiter Lauf am selben Tag ergänzt.
``plane`` legt die Bündel nach Seitenbesuch zusammen: ein Besuch prüft jedes noch
nicht heute geprüfte Bündel seiner Seite mit, auch die noch nicht fälligen
(``ANLASS_GLEICHE_SEITE``), und die Besuche laufen reihum über die Anbieter.

Anbieter-Schnitt (``job_von``): ein Job je Host, damit robots.txt und Abstand je Host
gelten; die drei Netze von Saturn/MediaMarkt teilen ``tarife.mediamarkt.de`` und
bilden EINEN Job ``saturn-mediamarkt``. Jeder Anbieter-Schlüssel gehört zu genau einem
Job.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from . import gegenprobe as gp
from .gegenprobe_reihe import reihum

GEGENPROBE_FENSTER_TAGE = 7
"""So viele Tage gilt eine Gegenprobe eines Preises (Tag der Prüfung eingeschlossen)."""
VORLAUF_TAGE = 2
"""So viele Tage vor Ablauf des Fensters ist ein Bündel wieder fällig."""

SAMMELJOBS: dict[str, tuple[str, ...]] = {
    "saturn-mediamarkt": tuple(
        f"saturn-mediamarkt-{netz}-netz" for netz in ("telekom", "vodafone", "o2")
    ),
}
"""Anbieter-Schlüssel, die einen Host teilen und darum einen Job bilden."""

GEZEIGT = tuple(s for s in gp.STATUS if s != gp.NICHT_GEGENGEPRUEFT)
"""Was die Seite als Gegenprobe eines Preises zeigt: nie eine nicht geöffnete Seite."""

SPEICHER_MUSTER = re.compile(r"^(.*?-\d+(?:gb|tb))(?:-.*)?$")
_ZUSTAND = re.compile(r"-(refurbished|gebraucht|erneuert|b-ware)$")


def angebot(buendel_id: str) -> str:
    """Der Bündel-Schlüssel ohne Farbe: Anbieter, Gerät mit Speicher und Zustand,
    Tarif, Raten. Farben eines Geräts sind dasselbe Angebot, wenn der Preis gleich
    ist; der Zustand (erneuert, gebraucht) bleibt ein anderes."""
    teile = buendel_id.split("--")
    if len(teile) != 5:
        return buendel_id
    sku = teile[2]
    treffer = SPEICHER_MUSTER.match(sku)
    zustand = _ZUSTAND.search(sku)
    if treffer:
        teile[2] = treffer.group(1) + (zustand.group(0) if zustand else "")
    return "--".join(teile)


class Gegenproben:
    """Alle Gegenproben je Bündel und je Angebot (ohne Farbe), jüngste zuletzt."""

    def __init__(self, ergebnisse: Iterable[gp.Ergebnis] = ()) -> None:
        self._je_id: dict[str, list[gp.Ergebnis]] = defaultdict(list)
        self._je_angebot: dict[str, list[gp.Ergebnis]] = defaultdict(list)
        for e in sorted(ergebnisse, key=lambda e: (e.datum, e.geprueft_um or "")):
            self._je_id[e.buendel_id].append(e)
            self._je_angebot[angebot(e.buendel_id)].append(e)

    def zum_preis(
        self, buendel_id: str, gesamt: float | None, nur: Sequence[str] = GEZEIGT
    ) -> gp.Ergebnis | None:
        """Die jüngste Gegenprobe dieses Preises mit einem Status aus ``nur``:
        dasselbe Bündel oder dasselbe Angebot in anderer Farbe, mit gleichen
        Gesamtkosten; ohne Gesamtkosten nur dasselbe Bündel, ebenfalls ohne."""
        if gesamt is None:
            for e in reversed(self._je_id.get(buendel_id, [])):
                if e.status in nur and e.gesamt_gespeichert is None:
                    return e
            return None
        for liste in (
            self._je_id.get(buendel_id, []),
            self._je_angebot.get(angebot(buendel_id), []),
        ):
            for e in reversed(liste):
                if (
                    e.status in nur
                    and e.gesamt_gespeichert is not None
                    and gp.gleich(e.gesamt_gespeichert, gesamt)
                ):
                    return e
        return None

    def am(self, buendel_id: str, datum: str) -> gp.Ergebnis | None:
        """Die Gegenprobe dieses Bündels an diesem Tag."""
        for e in reversed(self._je_id.get(buendel_id, [])):
            if e.datum == datum:
                return e
        return None

    def letzter_versuch(self, buendel_id: str) -> str | None:
        """Der Tag des letzten geöffneten Besuchs dieses Bündels (auch gescheitert)."""
        tage = [
            e.datum for e in self._je_id.get(buendel_id, []) if e.status in gp.VERSUCHT
        ]
        return max(tage, default=None)


def alter_tage(datum: str, letzte: str | None) -> int | None:
    """Tage zwischen der letzten Gegenprobe und ``datum``; None ohne Gegenprobe."""
    if letzte is None:
        return None
    return (date.fromisoformat(datum) - date.fromisoformat(letzte)).days


def im_fenster(datum: str, letzte: str | None) -> bool:
    """Gilt eine Gegenprobe vom Tag ``letzte`` an ``datum`` noch?"""
    alter = alter_tage(datum, letzte)
    return alter is not None and alter < GEGENPROBE_FENSTER_TAGE


def faellig(datum: str, letzte: str | None) -> bool:
    """Nie geprüft oder höchstens ``VORLAUF_TAGE`` vor Ablauf des Fensters."""
    alter = alter_tage(datum, letzte)
    return alter is None or alter >= GEGENPROBE_FENSTER_TAGE - VORLAUF_TAGE


def job_von(schluessel: str) -> str:
    """Der Job des Anbieter-Schlüssels (``SAMMELJOBS``, sonst der Schlüssel selbst)."""
    for job, schluessel_des_jobs in SAMMELJOBS.items():
        if schluessel in schluessel_des_jobs:
            return job
    return schluessel


def schluessel_der_jobs(namen: Iterable[str]) -> frozenset[str] | None:
    """Die Anbieter-Schlüssel zu ``--anbieter`` (Job oder Schlüssel); None = alle."""
    out: set[str] = set()
    for name in namen:
        out.update(SAMMELJOBS.get(name, (name,)))
    return frozenset(out) if out else None


@dataclass(frozen=True)
class Kandidat:
    """Ein Bündel, das ein Lauf öffnen kann, mit Anlass und Rang (kleiner zuerst)."""

    buendel_id: str
    anlass: str
    faellig: bool
    rang: tuple


def _streu(buendel_id: str, datum: str) -> str:
    """Fester, je Tag anderer Gleichstandsbrecher (keine Seite immer zuerst)."""
    return hashlib.sha256(f"{datum}|{buendel_id}".encode()).hexdigest()[:12]


def kandidaten(
    datum: str,
    angezeigt: Iterable[Mapping],
    gesamt: Callable[[Mapping], float | None],
    gegenproben: Gegenproben,
    aenderungen: Sequence[str],
    nur: frozenset[str] | None = None,
) -> list[Kandidat]:
    """Jedes angezeigte Bündel, dessen Preis heute noch nicht geöffnet wurde, in
    Prüfreihenfolge (Modulkopf); ``nur`` beschränkt auf diese Anbieter-Schlüssel."""
    stelle = {bid: i for i, bid in enumerate(aenderungen)}
    out: list[Kandidat] = []
    for satz in angezeigt:
        bid = str(satz["id"])
        if nur is not None and gp.anbieter_aus_id(bid) not in nur:
            continue
        preis = gesamt(satz)
        versucht = gegenproben.zum_preis(bid, preis, gp.VERSUCHT)
        if versucht is not None and versucht.datum == datum:
            continue
        if bid in stelle:
            out.append(Kandidat(bid, gp.ANLASS_AENDERUNG, True, (0, stelle[bid])))
            continue
        probe = gegenproben.zum_preis(bid, preis, gp.GEPRUEFT)
        letzte = probe.datum if probe is not None else None
        ist_faellig = faellig(datum, letzte)
        anlass = gp.ANLASS_FENSTER if ist_faellig else gp.ANLASS_GLEICHE_SEITE
        rang = (
            1 if ist_faellig else 2,
            0,
            letzte or "",
            gegenproben.letzter_versuch(bid) or "",
            _streu(bid, datum),
        )
        out.append(Kandidat(bid, anlass, ist_faellig, rang))
    return sorted(out, key=lambda k: k.rang)


def plane(
    kandidaten: Iterable[Kandidat], seite: Callable[[str], str]
) -> list[list[tuple[str, str]]]:
    """Die Seitenbesuche: je Seite mit mindestens einem fälligen Bündel ein Besuch mit
    allen Kandidaten dieser Seite, Besuche reihum über die Anbieter, je Anbieter in
    der Reihenfolge ihres ersten Bündels."""
    je_seite: dict[str, list[Kandidat]] = {}
    for k in kandidaten:
        je_seite.setdefault(seite(k.buendel_id), []).append(k)
    je_anbieter: dict[str, list[list[tuple[str, str]]]] = defaultdict(list)
    for gruppe in je_seite.values():
        if any(k.faellig for k in gruppe):
            schluessel = gp.anbieter_aus_id(gruppe[0].buendel_id)
            je_anbieter[schluessel].append([(k.buendel_id, k.anlass) for k in gruppe])
    return reihum(je_anbieter)


def jobs(kandidaten: Iterable[Kandidat]) -> list[str]:
    """Die Jobs, für die etwas fällig ist (leer: nichts zu tun, der Lauf steigt aus)."""
    return sorted(
        {job_von(gp.anbieter_aus_id(k.buendel_id)) for k in kandidaten if k.faellig}
    )
