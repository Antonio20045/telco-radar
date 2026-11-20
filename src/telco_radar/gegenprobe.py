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

- ``bestaetigt``: jeder Pflichtposten des Anbieters ist auf der Seite gelesen und
  gleich dem gespeicherten Wert;
- ``abweichend``: mindestens ein gelesener Posten weicht ab, beide Werte stehen in
  ``abweichungen``;
- ``nicht_pruefbar``: die Seite war nicht lesbar oder ein Pflichtposten fehlt; ``grund``
  nennt es (Sperre, Zeitbudget, Tarif nicht wählbar, …).

Was der Anbieter auf diesem Weg nicht zeigt, steht in ``nicht_gelesen`` und ist keine
Bestätigung. Ein gespeicherter Wert ``None`` ist eine Lücke und wird nicht verglichen.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

BESTAETIGT = "bestaetigt"
ABWEICHEND = "abweichend"
NICHT_PRUEFBAR = "nicht_pruefbar"
STATUS = (BESTAETIGT, ABWEICHEND, NICHT_PRUEFBAR)

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

AENDERUNGSFELDER = (*FELDER, "gesamt")
"""Ändert sich einer dieser Werte zum Vortag, ist das Bündel eine Preisänderung."""

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
        if self.status == NICHT_PRUEFBAR and not self.grund:
            raise ValueError("nicht prüfbar ohne Grund")
        if self.status == ABWEICHEND and not self.abweichungen:
            raise ValueError("abweichend ohne abweichenden Posten")


class GegenprobeFehler(ValueError):
    """Eine Tagesdatei ist unlesbar (Zeile genannt)."""


def gleich(a: float | int, b: float | int) -> bool:
    """Gleich auf den Cent (``TOLERANZ_EUR``)."""
    return abs(float(a) - float(b)) < TOLERANZ_EUR


def vergleiche(
    gespeichert: Mapping, gelesen: Mapping, pflicht: Iterable[str]
) -> tuple[str, list[dict], list[str], str | None]:
    """(Status, Abweichungen, nicht gelesene Pflichtposten, Grund).

    Verglichen wird jeder Posten aus ``FELDER``, der gespeichert UND gelesen ist. Eine
    Abweichung entscheidet vor einer Lücke: ``abweichend`` auch dann, wenn ein
    anderer Pflichtposten nicht gelesen wurde. Ein gespeicherter Pflichtwert None ist
    keine Lücke der Seite und fehlt im Vergleich.
    """
    abweichungen = [
        {"feld": f, "gespeichert": gespeichert[f], "gelesen": gelesen[f]}
        for f in FELDER
        if gespeichert.get(f) is not None
        and gelesen.get(f) is not None
        and not gleich(gespeichert[f], gelesen[f])
    ]
    fehlt = [
        f for f in pflicht if gespeichert.get(f) is not None and gelesen.get(f) is None
    ]
    if abweichungen:
        return ABWEICHEND, abweichungen, fehlt, None
    if fehlt:
        namen = ", ".join(FELDNAMEN.get(f, f) for f in fehlt)
        return NICHT_PRUEFBAR, [], fehlt, f"Auf der Seite nicht ablesbar: {namen}"
    if not any(f in gelesen for f in pflicht):
        return NICHT_PRUEFBAR, [], [], "Kein Preis auf der Seite gelesen"
    return BESTAETIGT, [], [], None


def gespeicherte_werte(buendel: Mapping) -> dict:
    """Die vergleichbaren Posten eines Bestandssatzes (None bleibt stehen)."""
    return {f: buendel.get(f) for f in FELDER}


def geaendert(heute: Mapping, vortag: Mapping) -> bool:
    """Ob sich Gesamtkosten oder ein Posten zwischen zwei Messungen geändert haben."""
    for f in AENDERUNGSFELDER:
        a, b = heute.get(f), vortag.get(f)
        if (a is None) != (b is None):
            return True
        if a is not None and b is not None and not gleich(a, b):
            return True
    return False


def anbieter_aus_id(buendel_id: str) -> str:
    """Der Anbieter-Schlüssel im Bündel-Schlüssel (``buendel--<anbieter>--…``)."""
    teile = buendel_id.split("--")
    return teile[1] if len(teile) > 2 else ""


def auswahl(
    datum: str,
    heute: Iterable[Mapping],
    vortag: Iterable[Mapping],
    je_anbieter: int = STICHPROBE_JE_ANBIETER,
) -> list[tuple[str, str]]:
    """Die Bündel, die ``datum`` prüft: (Bündel-Schlüssel, Anlass), Änderungen zuerst.

    ``heute`` und ``vortag`` sind die Historienzeilen zweier Messtage. Gezählt wird nur
    eine Zeile, die an ihrem Tag gemessen ist (``abgerufen_am`` = ``datum`` der Zeile).
    Jede geänderte Zeile kommt dran, größte Änderung der Gesamtkosten zuerst; dazu
    je Anbieter ``je_anbieter`` unveränderte, zufällig, aber je Datum und Anbieter
    fest (``random.Random(f"{datum}|{anbieter}")``): derselbe Tag wählt dieselben.
    """
    gemessen = {
        z["id"]: z
        for z in heute
        if z.get("id") and z.get("abgerufen_am") == z.get("datum") == datum
    }
    alt = {z["id"]: z for z in vortag if z.get("id")}
    aenderungen: list[tuple[float, str]] = []
    ruhig: dict[str, list[str]] = defaultdict(list)
    for bid, zeile in gemessen.items():
        vorher = alt.get(bid)
        if vorher is not None and geaendert(zeile, vorher):
            neu, vor = zeile.get("gesamt"), vorher.get("gesamt")
            abstand = abs(neu - vor) if neu is not None and vor is not None else 0.0
            aenderungen.append((-abstand, bid))
        else:
            ruhig[anbieter_aus_id(bid)].append(bid)
    gewaehlt = [(bid, ANLASS_AENDERUNG) for _, bid in sorted(aenderungen)]
    for anbieter in sorted(ruhig):
        kandidaten = sorted(ruhig[anbieter])
        zufall = random.Random(f"{datum}|{anbieter}")
        stichprobe = zufall.sample(kandidaten, min(je_anbieter, len(kandidaten)))
        gewaehlt += [(bid, ANLASS_STICHPROBE) for bid in sorted(stichprobe)]
    return gewaehlt


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
