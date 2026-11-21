"""Unabhängige Gegenprobe gespeicherter Bündelpreise: Vergleich und Tagesdatei.

Der Sammler liest Preise aus Schnittstellenantworten (JSON). Die Gegenprobe liest sie
ein zweites Mal im echten Browser: Produktseite öffnen, wählen wie ein Kunde, den
SICHTBAREN Text des Preisbereichs lesen (``collect.geraete.gegenprobe_wege``, Leser in
``collect.geraete.gegenprobe_sicht``). Dieses Modul hält, was Skript, Workflow und
Seite teilen: den Vergleich (``vergleiche``), die Preisänderung (``aenderungen``) und
die Tagesdatei ``data/state/gegenprobe/<datum>.jsonl``. Welche Bündel ein Lauf prüft,
steht in ``gegenprobe_fenster``, die Bilanz je Anbieter in ``gegenprobe_bilanz``.

Status einer Prüfung (``STATUS``):

- ``bestaetigt``: jeder Posten des Rechenwegs ist gelesen und gleich dem Bestand;
- ``teilweise``: das Gelesene stimmt, ein Posten des Rechenwegs ist nicht gelesen
  (``grund`` nennt geprüfte und fehlende);
- ``abweichend``: ein gelesener Posten widerspricht einem gespeicherten WERT; beide
  stehen in ``abweichungen``;
- ``erfassungsluecke``: kein Widerspruch, aber der Bestand führt einen Posten als
  Lücke (None), den die Seite nennt (``luecken``); keine Preisabweichung;
- ``nicht_pruefbar``: die Seite war geöffnet, aber nicht lesbar; ``grund`` belegt es
  (Sperre, Auswahl nicht gefunden, anderer Tarif, …), ``seite`` und ``bild`` zeigen,
  was der Browser sah;
- ``nicht_gegengeprueft``: die Seite wurde in diesem Lauf nicht geöffnet (Zeitbudget,
  Ausfall des Anbieters); ``grund`` nennt es. Das ist kein Befund über den Preis.

Was der Anbieter auf diesem Weg nicht zeigt, steht in ``nicht_gelesen`` und ist keine
Bestätigung. Eine Preisänderung ist ein geänderter Posten gegenüber der letzten
Messung davor (``aenderungen``), dieselbe Definition für Auswahl und Seite.
"""

from __future__ import annotations

import hashlib
import logging
import random
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime

from .gegenprobe_reihe import reihum
from .gegenprobe_zeile import ABWEICHEND as ABWEICHEND
from .gegenprobe_zeile import ANLASS_AENDERUNG as ANLASS_AENDERUNG
from .gegenprobe_zeile import ANLASS_FENSTER as ANLASS_FENSTER
from .gegenprobe_zeile import ANLASS_GLEICHE_SEITE as ANLASS_GLEICHE_SEITE
from .gegenprobe_zeile import ANLASS_STICHPROBE as ANLASS_STICHPROBE
from .gegenprobe_zeile import BESTAETIGT as BESTAETIGT
from .gegenprobe_zeile import ERFASSUNGSLUECKE as ERFASSUNGSLUECKE
from .gegenprobe_zeile import GEPRUEFT as GEPRUEFT
from .gegenprobe_zeile import GRUND_GESPERRT as GRUND_GESPERRT
from .gegenprobe_zeile import GRUND_KEIN_LESER as GRUND_KEIN_LESER
from .gegenprobe_zeile import GRUND_ROBOTS as GRUND_ROBOTS
from .gegenprobe_zeile import GRUND_ZEITBUDGET as GRUND_ZEITBUDGET
from .gegenprobe_zeile import NICHT_GEGENGEPRUEFT as NICHT_GEGENGEPRUEFT
from .gegenprobe_zeile import NICHT_PRUEFBAR as NICHT_PRUEFBAR
from .gegenprobe_zeile import ORDNER as ORDNER
from .gegenprobe_zeile import STATUS as STATUS
from .gegenprobe_zeile import TEILWEISE as TEILWEISE
from .gegenprobe_zeile import VERSUCHT as VERSUCHT
from .gegenprobe_zeile import Ergebnis as Ergebnis
from .gegenprobe_zeile import GegenprobeFehler as GegenprobeFehler
from .gegenprobe_zeile import als_zeile as als_zeile
from .gegenprobe_zeile import ergaenze_tag as ergaenze_tag
from .gegenprobe_zeile import lies_alle as lies_alle
from .gegenprobe_zeile import lies_tag as lies_tag
from .gegenprobe_zeile import schreibe_tag as schreibe_tag
from .gegenprobe_zeile import tagesdatei as tagesdatei
from .gegenprobe_zeile import teile_auf as teile_auf
from .versandkosten import versand_fuer

log = logging.getLogger(__name__)

STICHPROBE_JE_ANBIETER = 5
"""So viele unveränderte Bündel prüft ein Tag je Anbieter zu den Änderungen dazu."""

TOLERANZ_EUR = 0.005
"""Zwei Beträge gelten als gleich, wenn sie auf den Cent gleich sind."""

RELEASE_PREFIX = "gegenprobe-"
REPO = "Antonio20045/telco-radar"
TEXT_HOECHSTENS = 4000
"""So viele Zeichen des gelesenen Seitentexts stehen im Ergebnis (Nachweis)."""

ABSTAND_STUNDEN = 6
"""Liegen Messung und Gegenprobe weiter auseinander, kann sich der Preis dazwischen
geändert haben; eine Abweichung sagt das dazu (sie bleibt eine Abweichung)."""

BETRAGSFELDER = (
    "tarif_monatlich",
    "geraet_monatsrate",
    "geraet_zuzahlung",
    "anschlusspreis",
    "buendel_monatlich",
)
GANZZAHLFELDER = ("laufzeit_monate",)
FELDER = BETRAGSFELDER + GANZZAHLFELDER
"""Die Posten eines Bündels, die eine Gegenprobe lesen kann (Namen wie im Bestand)."""
VERSAND = "versand"
VERGLEICHSFELDER = (*FELDER, VERSAND)
"""Was ``vergleiche`` gegenüberstellt: die Posten und der Versand, den die Seite in die
Gesamtkosten rechnet (gespeichert: ``config/versandkosten.yaml``)."""


FELDNAMEN = {
    "tarif_monatlich": "Tarif monatlich",
    "geraet_monatsrate": "Geräterate",
    "geraet_zuzahlung": "Gerät einmalig",
    "anschlusspreis": "Anschlusspreis",
    "buendel_monatlich": "Monatsbetrag Tarif und Gerät",
    "laufzeit_monate": "Zahl der Raten",
    VERSAND: "Versand",
}
"""Die Namen der Posten auf der Seite (laienverständlich)."""


@dataclass
class Sichtwerte:
    """Was ein Leser im sichtbaren Preisbereich gefunden hat; None = nicht gelesen.

    ``roh`` nennt die gelesenen Beträge mit der Beschriftung der Seite (Nachweis),
    ``versand`` den sichtbaren Versand (nur Anzeige, nicht verglichen)."""

    tarif_monatlich: float | None = None
    geraet_monatsrate: float | None = None
    laufzeit_monate: int | None = None
    geraet_zuzahlung: float | None = None
    anschlusspreis: float | None = None
    buendel_monatlich: float | None = None
    versand: float | None = None
    tarif_name: str | None = None
    roh: dict[str, str] = field(default_factory=dict)

    def werte(self) -> dict[str, float | int]:
        """Die gelesenen Posten (ohne None) unter den Namen des Bestands."""
        return {f: getattr(self, f) for f in FELDER if getattr(self, f) is not None}


def gleich(a: float | int, b: float | int) -> bool:
    """Gleich auf den Cent (``TOLERANZ_EUR``)."""
    return abs(float(a) - float(b)) < TOLERANZ_EUR


def rechenweg_felder(gespeichert: Mapping) -> list[str]:
    """Die Posten, die der Rechenweg dieses Bündels nutzt (Betrag nicht 0 oder None);
    die Ratenzahl, wenn eine Rate oder ein Monatsbetrag für Tarif und Gerät zählt."""
    out: list[str] = []
    if gespeichert.get("buendel_monatlich") is not None:
        out += ["buendel_monatlich", "laufzeit_monate"]
    else:
        if gespeichert.get("tarif_monatlich"):
            out.append("tarif_monatlich")
        if gespeichert.get("geraet_monatsrate"):
            out += ["geraet_monatsrate", "laufzeit_monate"]
    return out + [
        f for f in ("geraet_zuzahlung", "anschlusspreis") if gespeichert.get(f)
    ]


def _namen(felder: Iterable[str]) -> str:
    return ", ".join(FELDNAMEN.get(f, f) for f in felder)


def _gegenueber(gespeichert: Mapping, gelesen: Mapping) -> list[dict]:
    return [
        {"feld": f, "gespeichert": gespeichert.get(f), "gelesen": gelesen[f]}
        for f in VERGLEICHSFELDER
        if gelesen.get(f) is not None
        and (gespeichert.get(f) is None or not gleich(gespeichert[f], gelesen[f]))
    ]


def luecken_von(gespeichert: Mapping, gelesen: Mapping) -> list[dict]:
    """Die Posten, die der Bestand als Lücke führt und die Seite nennt."""
    return teile_auf(_gegenueber(gespeichert, gelesen))[1]


def vergleiche(
    gespeichert: Mapping, gelesen: Mapping
) -> tuple[str, list[dict], list[str], str | None]:
    """(Status, Abweichungen, nicht gelesene Posten des Rechenwegs, Grund).

    Verglichen wird jeder Posten aus ``VERGLEICHSFELDER``, den die Seite zeigt.
    Widerspricht er einem gespeicherten Wert, ist das Bündel ``abweichend``. Führt der
    Bestand ihn als Lücke, ist das eine ``erfassungsluecke`` (``luecken_von``), keine
    Abweichung. ``bestaetigt`` heißt: jeder Posten des Rechenwegs
    (``rechenweg_felder``) ist gelesen und gleich; fehlt einer, ist es ``teilweise``
    mit den geprüften und den nicht gelesenen Posten im Grund.
    """
    abweichungen, luecken = teile_auf(_gegenueber(gespeichert, gelesen))
    noetig = rechenweg_felder(gespeichert)
    fehlt = [f for f in noetig if gelesen.get(f) is None]
    if abweichungen:
        return ABWEICHEND, abweichungen, fehlt, None
    geprueft = [f for f in FELDER if gelesen.get(f) is not None]
    if not geprueft:
        return NICHT_PRUEFBAR, [], fehlt, "Kein Preis auf der Seite gelesen"
    if luecken:
        return ERFASSUNGSLUECKE, [], fehlt, None
    if fehlt:
        grund = f"Bestätigt: {_namen(geprueft)}; nicht gelesen: {_namen(fehlt)}"
        return TEILWEISE, [], fehlt, grund
    return BESTAETIGT, [], [], None


def messzeit(gemessen_um: str | None, satz: Mapping) -> str | None:
    """Die Zeit des Messlaufs, wenn der Satz in diesem Lauf gelesen ist (sein
    ``abgerufen_am`` ist der Tag des Laufs); sonst None."""
    if not gemessen_um or satz.get("abgerufen_am") != gemessen_um[:10]:
        return None
    return gemessen_um


def abstand_stunden(gemessen_um: str | None, geprueft_um: str | None) -> float | None:
    """Stunden zwischen Messung und Gegenprobe; None, wenn eine Zeit fehlt."""
    try:
        a = datetime.fromisoformat(gemessen_um or "")
        b = datetime.fromisoformat(geprueft_um or "")
    except ValueError:
        return None
    if a.tzinfo is None or b.tzinfo is None:
        return None
    return abs((b - a).total_seconds()) / 3600


def gespeicherte_werte(buendel: Mapping) -> dict:
    """Die vergleichbaren Posten eines Bestandssatzes (None bleibt stehen) und der
    Versand, den die Gesamtkosten für diesen Anbieter rechnen (unbelegt: None)."""
    werte = {f: buendel.get(f) for f in FELDER}
    werte[VERSAND] = versand_fuer(str(buendel.get("anbieter") or "")).betrag
    return werte


def geaendert(heute: Mapping, vorher: Mapping) -> bool:
    """Ob sich ein Posten zwischen zwei Messungen geändert hat (eine Lücke, die zum
    Wert wird oder umgekehrt, zählt). Das eingefrorene ``gesamt`` der Historie zählt
    nie: bis 19.11.2026 rechnete es eine andere Formel."""
    for f in FELDER:
        a, b = heute.get(f), vorher.get(f)
        if (a is None) != (b is None):
            return True
        if a is not None and b is not None and not gleich(a, b):
            return True
    return False


def gemessen(saetze: Iterable[Mapping], datum: str) -> dict[str, Mapping]:
    """Die Zeilen, die an ``datum`` gemessen sind (``abgerufen_am`` = ``datum``)."""
    return {
        z["id"]: z
        for z in saetze
        if z.get("id") and z.get("abgerufen_am") == z.get("datum") == datum
    }


def letzte_messungen(tage: Iterable[tuple[str, list]]) -> dict[str, Mapping]:
    """Je Bündel die letzte Messung aus (Datum, Zeilen) in Datumsfolge."""
    zuletzt: dict[str, Mapping] = {}
    for datum, saetze in tage:
        zuletzt.update(gemessen(saetze, datum))
    return zuletzt


def aenderungen(
    heute: Mapping[str, Mapping], vorher: Mapping[str, Mapping]
) -> list[tuple[Mapping, Mapping]]:
    """(heute, letzte Messung davor) je Bündel, dessen Posten sich geändert haben.

    DIE Definition einer Preisänderung, für die Seite „Preisänderungen“ und die
    Auswahl der Gegenprobe gleich: ``heute`` sind die gemessenen Zeilen eines Tages,
    ``vorher`` die letzte Messung jedes Bündels vor diesem Tag (``letzte_messungen``).
    """
    out = []
    for bid, zeile in heute.items():
        alt = vorher.get(bid)
        if alt is not None and geaendert(zeile, alt):
            out.append((zeile, alt))
    return out


def gewicht(heute: Mapping, vorher: Mapping) -> float:
    """Wie groß eine Änderung ist (Betrag je Posten, Monatsbeträge über ihre Monate);
    nur für die Reihenfolge, nie für die Frage, ob sich etwas geändert hat."""
    monate = heute.get("laufzeit_monate") or 24
    summe = 0.0
    for f in BETRAGSFELDER:
        a, b = heute.get(f), vorher.get(f)
        if a is not None and b is not None:
            faktor = (
                monate
                if f in ("tarif_monatlich", "geraet_monatsrate", "buendel_monatlich")
                else 1
            )
            summe += abs(a - b) * faktor
    return summe


def anbieter_aus_id(buendel_id: str) -> str:
    """Der Anbieter-Schlüssel im Bündel-Schlüssel (``buendel--<anbieter>--…``)."""
    teile = buendel_id.split("--")
    return teile[1] if len(teile) > 2 else ""


def auswahl(
    datum: str,
    heute: Iterable[Mapping],
    vorher: Iterable[Mapping],
    je_anbieter: int = STICHPROBE_JE_ANBIETER,
) -> list[tuple[str, str]]:
    """Die Bündel, die ``datum`` prüft: (Bündel-Schlüssel, Anlass) in Prüfreihenfolge.

    ``heute`` sind die Historienzeilen des Tages, ``vorher`` je Bündel die letzte
    Messung davor (``letzte_messungen``). Jede Änderung nach ``aenderungen`` kommt dran;
    dazu je Anbieter ``je_anbieter`` unveränderte, zufällig, aber je Datum und Anbieter
    fest (Zufall aus „Datum|Anbieter“). Fair, weil das Zeitbudget nicht immer reicht
    (``gegenprobe_reihe``): zuerst jede Stichprobe reihum, dann die Änderungen reihum
    über die Anbieter, je Anbieter die größte zuerst (``gewicht``).
    """
    tag = gemessen(heute, datum)
    alt = {z["id"]: z for z in vorher if z.get("id")}
    geaenderte = sorted(aenderungen(tag, alt), key=lambda p: (-gewicht(*p), p[0]["id"]))
    aenderung: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for zeile, _ in geaenderte:
        aenderung[anbieter_aus_id(zeile["id"])].append((zeile["id"], ANLASS_AENDERUNG))
    schon = {zeile["id"] for zeile, _ in geaenderte}
    ruhig: dict[str, list[str]] = defaultdict(list)
    for bid in tag:
        if bid not in schon:
            ruhig[anbieter_aus_id(bid)].append(bid)
    stichprobe: dict[str, list[tuple[str, str]]] = {}
    for anbieter, kandidaten in ruhig.items():
        zufall = random.Random(f"{datum}|{anbieter}")
        gezogen = zufall.sample(sorted(kandidaten), min(je_anbieter, len(kandidaten)))
        stichprobe[anbieter] = [(bid, ANLASS_STICHPROBE) for bid in sorted(gezogen)]
    return reihum(stichprobe) + reihum(aenderung)


def kennung(buendel_id: str, datum: str) -> str:
    """Stabiler Bildname aus Bündel-Schlüssel und Tag, nie aus Titeltext."""
    return hashlib.sha256(f"{buendel_id}|{datum}".encode()).hexdigest()[:16]


def release_tag(datum: str) -> str:
    """Das Release, in dem die Bilder eines Tages liegen."""
    return f"{RELEASE_PREFIX}{datum}"


def bild_url(datum: str, datei: str) -> str:
    """Die öffentliche Adresse eines hochgeladenen Bilds."""
    return f"https://github.com/{REPO}/releases/download/{release_tag(datum)}/{datei}"
