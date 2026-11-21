"""Unabhängige Gegenprobe gespeicherter Bündelpreise: Auswahl, Vergleich, Ablage.

Der Sammler liest Preise aus Schnittstellenantworten (JSON). Die Gegenprobe liest sie
ein zweites Mal auf anderem Weg: ein echter Browser öffnet die Produktseite, wählt
wie ein Kunde und liest den SICHTBAREN Text des Preisbereichs
(``collect.geraete.gegenprobe_browser``, Leser je Anbieter in
``collect.geraete.gegenprobe_sicht``). Dieses Modul hält, was Skript, Workflow und
Seite teilen: welche Bündel ein Tag prüft (``auswahl``), wie gelesene und
gespeicherte Werte verglichen werden (``vergleiche``) und die Tagesdatei
``data/state/gegenprobe/<datum>.jsonl`` (``lies_tag``, ``schreibe_tag``).

Status einer Prüfung (``STATUS``):

- ``bestaetigt``: jeder Posten des Rechenwegs ist auf der Seite gelesen und gleich
  dem gespeicherten Wert;
- ``teilweise``: was die Seite zeigt, stimmt, aber ein Posten des Rechenwegs ist
  nicht gelesen (``grund`` nennt geprüfte und fehlende);
- ``abweichend``: mindestens ein gelesener Posten weicht ab oder fehlt im Bestand,
  beide Werte stehen in ``abweichungen``;
- ``nicht_pruefbar``: die Seite war nicht lesbar oder ein Pflichtposten fehlt; ``grund``
  nennt es (Sperre, Zeitbudget, Tarif nicht wählbar, …).

Was der Anbieter auf diesem Weg nicht zeigt, steht in ``nicht_gelesen`` und ist keine
Bestätigung. Ein gespeicherter Wert ``None``, den die Seite nennt, ist eine Abweichung.
Eine Preisänderung ist ein geänderter Posten gegenüber der letzten Messung davor
(``aenderungen``), dieselbe Definition für Auswahl und Seite.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .gegenprobe_reihe import reihum

log = logging.getLogger(__name__)

BESTAETIGT = "bestaetigt"
TEILWEISE = "teilweise"
ABWEICHEND = "abweichend"
NICHT_PRUEFBAR = "nicht_pruefbar"
STATUS = (BESTAETIGT, TEILWEISE, ABWEICHEND, NICHT_PRUEFBAR)

ANLASS_AENDERUNG = "preisaenderung"
ANLASS_STICHPROBE = "stichprobe"

STICHPROBE_JE_ANBIETER = 5
"""So viele unveränderte Bündel prüft ein Tag je Anbieter zu den Änderungen dazu."""

TOLERANZ_EUR = 0.005
"""Zwei Beträge gelten als gleich, wenn sie auf den Cent gleich sind."""

ORDNER = Path("data") / "state" / "gegenprobe"
RELEASE_PREFIX = "gegenprobe-"
REPO = "Antonio20045/telco-radar"
TEXT_HOECHSTENS = 4000
"""So viele Zeichen des gelesenen Seitentexts stehen im Ergebnis (Nachweis)."""

ABSTAND_STUNDEN = 6
"""Liegen Messung und Gegenprobe weiter auseinander, kann sich der Preis dazwischen
geändert haben; eine Abweichung sagt das dazu (sie bleibt eine Abweichung)."""

GRUND_ZEITBUDGET = "Zeitbudget des Laufs erschöpft, nicht geöffnet"
GRUND_KEIN_LESER = "Für diesen Anbieter gibt es noch keinen Kundenweg"
GRUND_GESPERRT = "Seite gesperrt (Bot-Schutz), nicht umgangen"
GRUND_ROBOTS = "robots.txt erlaubt den Abruf nicht"

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


FELDNAMEN = {
    "tarif_monatlich": "Tarif monatlich",
    "geraet_monatsrate": "Geräterate",
    "geraet_zuzahlung": "Gerät einmalig",
    "anschlusspreis": "Anschlusspreis",
    "buendel_monatlich": "Monatsbetrag Tarif und Gerät",
    "laufzeit_monate": "Zahl der Raten",
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


@dataclass
class Ergebnis:
    """Eine Gegenprobe eines Bündels an einem Tag (eine Zeile der Tagesdatei)."""

    datum: str
    buendel_id: str
    anbieter: str
    status: str
    anlass: str
    geprueft_um: str | None = None
    gemessen_um: str | None = None
    """Ende des Messlaufs, der den geprüften Preis las (``geraete_tco.json``), oder
    None, wenn der Lauf es nicht festhielt."""
    grund: str | None = None
    sku_id: str = ""
    tarif_name: str = ""
    laufzeit_monate: int | None = None
    seite: str = ""
    gelesen: dict = field(default_factory=dict)
    gespeichert: dict = field(default_factory=dict)
    abweichungen: list[dict] = field(default_factory=list)
    nicht_gelesen: list[str] = field(default_factory=list)
    gesamt_gespeichert: float | None = None
    gesamt_gelesen: float | None = None
    text: str = ""
    bild: str | None = None
    bild_fehlt: str | None = None

    def __post_init__(self) -> None:
        if self.status not in STATUS:
            raise ValueError(f"unbekannter Status {self.status!r}")
        if self.status in (NICHT_PRUEFBAR, TEILWEISE) and not self.grund:
            raise ValueError("nicht prüfbar ohne Grund")
        if self.status == ABWEICHEND and not self.abweichungen:
            raise ValueError("abweichend ohne abweichenden Posten")


class GegenprobeFehler(ValueError):
    """Eine Tagesdatei ist unlesbar (Zeile genannt)."""


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


def vergleiche(
    gespeichert: Mapping, gelesen: Mapping
) -> tuple[str, list[dict], list[str], str | None]:
    """(Status, Abweichungen, nicht gelesene Posten des Rechenwegs, Grund).

    Verglichen wird jeder Posten aus ``FELDER``, den die Seite zeigt. Weicht er ab
    oder fehlt er im Bestand (gespeichert None, Seite nennt ihn), ist das Bündel
    ``abweichend``. ``bestaetigt`` heißt: jeder Posten des Rechenwegs
    (``rechenweg_felder``) ist gelesen und gleich; fehlt einer, ist es ``teilweise``
    mit den geprüften und den nicht gelesenen Posten im Grund.
    """
    abweichungen = [
        {"feld": f, "gespeichert": gespeichert.get(f), "gelesen": gelesen[f]}
        for f in FELDER
        if gelesen.get(f) is not None
        and (gespeichert.get(f) is None or not gleich(gespeichert[f], gelesen[f]))
    ]
    noetig = rechenweg_felder(gespeichert)
    fehlt = [f for f in noetig if gelesen.get(f) is None]
    if abweichungen:
        return ABWEICHEND, abweichungen, fehlt, None
    geprueft = [f for f in FELDER if gelesen.get(f) is not None]
    if not geprueft:
        return NICHT_PRUEFBAR, [], fehlt, "Kein Preis auf der Seite gelesen"
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
    """Die vergleichbaren Posten eines Bestandssatzes (None bleibt stehen)."""
    return {f: buendel.get(f) for f in FELDER}


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


def tagesdatei(wurzel: Path, datum: str) -> Path:
    """``data/state/gegenprobe/<datum>.jsonl`` unter ``wurzel``."""
    return wurzel / ORDNER / f"{datum}.jsonl"


def als_zeile(ergebnis: Ergebnis) -> str:
    """Eine Zeile der Tagesdatei."""
    return json.dumps(asdict(ergebnis), ensure_ascii=False, sort_keys=True)


def schreibe_tag(pfad: Path, ergebnisse: Iterable[Ergebnis]) -> None:
    """Schreibt die Tagesdatei neu (ein Lauf je Tag ersetzt den vorigen)."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text("".join(als_zeile(e) + "\n" for e in ergebnisse), encoding="utf-8")


def lies_tag(pfad: Path) -> list[Ergebnis]:
    """Ergebnisse einer Tagesdatei; [] ohne Datei, ``GegenprobeFehler`` bei Unfug."""
    if not pfad.exists():
        return []
    out: list[Ergebnis] = []
    for nummer, zeile in enumerate(pfad.read_text(encoding="utf-8").splitlines(), 1):
        if not zeile.strip():
            continue
        try:
            out.append(Ergebnis(**json.loads(zeile)))
        except (TypeError, ValueError) as fehler:
            raise GegenprobeFehler(f"{pfad.name} Zeile {nummer}: {fehler}") from fehler
    return out


def lies_alle(ordner: Path) -> dict[tuple[str, str], Ergebnis]:
    """Alle Ergebnisse je (Bündel-Schlüssel, Datum); unlesbare Dateien werfen."""
    out: dict[tuple[str, str], Ergebnis] = {}
    if not ordner.is_dir():
        return out
    for pfad in sorted(ordner.glob("*.jsonl")):
        for e in lies_tag(pfad):
            out[(e.buendel_id, e.datum)] = e
    return out
