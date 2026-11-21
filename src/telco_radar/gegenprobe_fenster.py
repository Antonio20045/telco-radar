"""Fenster der Gegenprobe: jedes angezeigte Bündel binnen ``GEGENPROBE_FENSTER_TAGE``.

Abnahmekriterium 2 (Antonio, 21.11.2026): jedes Bündel der Geräteseite ist innerhalb
eines festen Fensters unabhängig gegengeprüft, jede Preisänderung am Tag ihres
Auftretens. Je Bündel gibt es zwei Größen, beide aus den Tagesdateien
(``gegenprobe.lies_alle``) und an EINER Stelle (``Gegenproben``), gelesen von Seite,
Fenster und Bilanz: ``letzte_gute`` ist der jüngste Besuch, der den Preis gelesen hat
(``gegenprobe.GEPRUEFT``), ``letzter_versuch`` der jüngste geöffnete Besuch, auch ein
belegt gescheiterter. Beide gehören zum aktuellen Preis (``zum_preis``: dasselbe
Bündel oder dasselbe Angebot in anderer Farbe mit gleichen Gesamtkosten; ohne
Gesamtkosten dasselbe Bündel mit denselben Einzelposten). „Im Fenster gegengeprüft“
heißt: ``letzte_gute`` ist jünger als ``GEGENPROBE_FENSTER_TAGE``. Ein gescheiterter
Versuch nimmt keiner guten Prüfung die Gültigkeit.

Reihenfolge (``kandidaten``) ist EINE Regel, früheste Frist zuerst (Earliest Deadline
First, Prüferbefund zu PR 200): Frist ist heute für eine Preisänderung des Tages,
sonst ``letzte_gute`` + Fenster, ohne gute Prüfung der Tag der ersten Anzeige
(``first_seen``, unbekannt: sofort fällig) + Fenster. Eine überfällige Frist zählt als
heute; bei gleicher Frist kommt die Preisänderung zuerst, dann die ältere Frist. Ein
gescheiterter Versuch ändert die Frist nicht. Fällig ist ein Bündel ab Frist −
``VORLAUF_TAGE``. Wiederholungsbremse: nach einem gescheiterten Versuch erst wieder,
wenn ``WIEDERHOLUNG_TAGE`` vergangen sind oder die Frist heute oder morgen endet (eine
schon verstrichene Frist zählt nicht dazu); so kosten Dauerfehler nicht jede Nacht
Zeit, und ein Zufallsfehler bekommt vor Fristende einen zweiten Versuch. Was heute zu
diesem Preis geöffnet wurde, kommt nicht noch einmal dran: ein zweiter Lauf am selben
Tag ergänzt. ``plane`` legt die Bündel nach Seitenbesuch zusammen: ein Besuch prüft
jedes noch nicht heute geöffnete Bündel seiner Seite mit (``ANLASS_GLEICHE_SEITE``);
die Besuche laufen reihum über die Anbieter. Ein fälliges Bündel, dessen letzter
Versuch scheiterte, ist verdächtig (``ANLASS_WIEDERHOLUNG``): der Lauf besucht je
Anbieter höchstens ``VERDAECHTIG_JE_NACHT`` Seiten, deren Bündel alle verdächtig sind,
und stellt weitere zurück; nie versuchte Seiten werden immer versucht (dritter
Prüferbefund zu PR 200: eine Serie von Fehlern sagt nichts über die nächste Seite).

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
from datetime import date, timedelta

from . import gegenprobe as gp
from .gegenprobe_reihe import reihum

GEGENPROBE_FENSTER_TAGE = 7
"""So viele Tage gilt eine Gegenprobe eines Preises (Tag der Prüfung eingeschlossen)."""
VORLAUF_TAGE = 2
"""So viele Tage vor Ablauf des Fensters ist ein Bündel wieder fällig."""
WIEDERHOLUNG_TAGE = 2
"""So viele Tage nach einem gescheiterten Versuch wird ein Bündel frühestens wieder
versucht, außer seine Frist ist höchstens einen Tag entfernt."""
VERDAECHTIG_JE_NACHT = 10
"""So viele Besuche verdächtiger Seiten (letzter Versuch gescheitert,
``ANLASS_WIEDERHOLUNG``) macht ein Lauf je Anbieter höchstens; weitere verdächtige
werden zurückgestellt, alle anderen laufen weiter."""

SAMMELJOBS: dict[str, tuple[str, ...]] = {
    "saturn-mediamarkt": tuple(
        f"saturn-mediamarkt-{netz}-netz" for netz in ("telekom", "vodafone", "o2")
    ),
}
"""Anbieter-Schlüssel, die einen Host teilen und darum einen Job bilden."""

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

    def letzte_gute(
        self, buendel_id: str, gesamt: float | None, posten: Mapping | None = None
    ) -> gp.Ergebnis | None:
        """Der jüngste Besuch, der diesen Preis gelesen hat (``gp.GEPRUEFT``)."""
        return self.zum_preis(buendel_id, gesamt, gp.GEPRUEFT, posten)

    def letzter_versuch(
        self, buendel_id: str, gesamt: float | None, posten: Mapping | None = None
    ) -> gp.Ergebnis | None:
        """Der jüngste geöffnete Besuch dieses Preises, auch ein gescheiterter."""
        return self.zum_preis(buendel_id, gesamt, gp.VERSUCHT, posten)

    def zuletzt_gescheitert(self, buendel_id: str) -> bool:
        """Ist der jüngste geöffnete Besuch dieses Bündels (gleich welcher Preis)
        gescheitert? Dann ist es verdächtig; nie versuchte und zuletzt gute nie."""
        versuche = [
            e for e in self._je_id.get(buendel_id, []) if e.status in gp.VERSUCHT
        ]
        return bool(versuche) and versuche[-1].status == gp.NICHT_PRUEFBAR

    def zum_preis(
        self,
        buendel_id: str,
        gesamt: float | None,
        nur: Sequence[str] = gp.VERSUCHT,
        posten: Mapping | None = None,
    ) -> gp.Ergebnis | None:
        """Die jüngste Gegenprobe dieses Preises mit einem Status aus ``nur``:
        dasselbe Bündel oder dasselbe Angebot in anderer Farbe, mit gleichen
        Gesamtkosten. Ohne Gesamtkosten ist der Preis seine Einzelposten
        (``posten``, ``gegenprobe.FELDER``): nur dasselbe Bündel mit denselben
        gespeicherten Posten; ohne ``posten`` gibt es dann keine."""
        if gesamt is None:
            if posten is None:
                return None
            for e in reversed(self._je_id.get(buendel_id, [])):
                if (
                    e.status in nur
                    and e.gesamt_gespeichert is None
                    and not gp.geaendert(e.gespeichert, posten)
                ):
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


def alter_tage(datum: str, letzte: str | None) -> int | None:
    """Tage zwischen der letzten Gegenprobe und ``datum``; None ohne Gegenprobe."""
    if letzte is None:
        return None
    return (date.fromisoformat(datum) - date.fromisoformat(letzte)).days


def im_fenster(datum: str, letzte: str | None) -> bool:
    """Gilt eine gute Gegenprobe vom Tag ``letzte`` an ``datum`` noch?"""
    alter = alter_tage(datum, letzte)
    return alter is not None and alter < GEGENPROBE_FENSTER_TAGE


def frist(datum: str, satz: Mapping, gute: gp.Ergebnis | None) -> str:
    """Bis wann das Bündel gegengeprüft sein muss: gute Prüfung + Fenster, ohne gute
    Prüfung erste Anzeige (``first_seen``) + Fenster. Ist die erste Anzeige unbekannt,
    ist die Frist ``datum`` (sofort fällig, ``ohne_erste_anzeige``), nie „heute neu“."""
    if gute is not None:
        anfang = gute.datum
    elif satz.get("first_seen"):
        anfang = str(satz["first_seen"])
    else:
        return datum
    return str(date.fromisoformat(anfang[:10]) + timedelta(GEGENPROBE_FENSTER_TAGE))


def ohne_erste_anzeige(satz: Mapping) -> bool:
    """Fehlt ``first_seen``? Dann ist das Bündel sofort fällig (benannt im Lauf)."""
    return not satz.get("first_seen")


def tage_bis(datum: str, bis: str) -> int:
    """Tage von ``datum`` bis ``bis`` (negativ: vorbei)."""
    return (date.fromisoformat(bis) - date.fromisoformat(datum)).days


def faellig(datum: str, bis: str) -> bool:
    """Fällig ab Frist − ``VORLAUF_TAGE``."""
    return tage_bis(datum, bis) <= VORLAUF_TAGE


def gebremst(datum: str, bis: str, versuch: gp.Ergebnis | None) -> bool:
    """Wiederholungsbremse: der letzte Versuch scheiterte vor weniger als
    ``WIEDERHOLUNG_TAGE``, und die Frist ist nicht heute oder morgen. Eine schon
    verstrichene Frist bremst mit: sonst käme ein Dauerfehler ohne je eine gute
    Prüfung (Frist längst vorbei) jede Nacht wieder."""
    if versuch is None or versuch.status != gp.NICHT_PRUEFBAR:
        return False
    seit = tage_bis(versuch.datum, datum)
    return seit < WIEDERHOLUNG_TAGE and not 0 <= tage_bis(datum, bis) <= 1


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


def _kandidat(
    datum: str, satz: Mapping, preis: float | None, proben: Gegenproben, stelle: int
) -> Kandidat:
    """Anlass und Rang nach der Fristregel (Modulkopf); ``stelle`` ist der Platz in
    der Folge der Preisänderungen, -1 ohne Preisänderung."""
    bid = str(satz["id"])
    aenderung = stelle >= 0
    gute = proben.letzte_gute(bid, preis, satz)
    bis = datum if aenderung else frist(datum, satz, gute)
    ist_faellig = aenderung or (
        faellig(datum, bis)
        and not gebremst(datum, bis, proben.letzter_versuch(bid, preis, satz))
    )
    if aenderung:
        anlass = gp.ANLASS_AENDERUNG
    elif not ist_faellig:
        anlass = gp.ANLASS_GLEICHE_SEITE
    elif proben.zuletzt_gescheitert(bid):
        anlass = gp.ANLASS_WIEDERHOLUNG
    else:
        anlass = gp.ANLASS_FENSTER
    rang = (max(bis, datum), not aenderung, bis, stelle, _streu(bid, datum))
    return Kandidat(bid, anlass, ist_faellig, rang)


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
        versuch = gegenproben.letzter_versuch(bid, preis, satz)
        if versuch is not None and versuch.datum == datum:
            continue
        out.append(_kandidat(datum, satz, preis, gegenproben, stelle.get(bid, -1)))
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
