"""Eine Zeile der Gegenprobe und die Tagesdatei ``data/state/gegenprobe/<datum>.jsonl``.

Die Statuswerte stehen in ``gegenprobe`` (Modulkopf) beschrieben; dieses Modul hält
sie, die Zeile (``Ergebnis``) und das Lesen und Schreiben der Tagesdatei.
``gegenprobe`` gibt jeden Namen weiter, Leser schreiben weiter ``gp.Ergebnis``.

Ein zweiter Lauf am selben Tag ergänzt die Datei (``ergaenze_tag``), statt sie zu
ersetzen: eine geöffnete Seite ersetzt jede Zeile desselben Bündels, eine Zeile
„nicht gegengeprüft“ füllt nur, was noch fehlt. Eine Zeile in der Form vor den
geschärften Statuswerten (bis 21.11.2026) ordnet ``Ergebnis`` selbst nach derselben
Definition ein (``teile_auf``): eine Lücke ist keine Abweichung, das Zeitbudget kein
„nicht prüfbar“. So sieht jeder Leser dieselben Status, gleich woher die Zeile kommt.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path

BESTAETIGT = "bestaetigt"
TEILWEISE = "teilweise"
ABWEICHEND = "abweichend"
ERFASSUNGSLUECKE = "erfassungsluecke"
NICHT_PRUEFBAR = "nicht_pruefbar"
NICHT_GEGENGEPRUEFT = "nicht_gegengeprueft"
STATUS = (
    BESTAETIGT,
    TEILWEISE,
    ABWEICHEND,
    ERFASSUNGSLUECKE,
    NICHT_PRUEFBAR,
    NICHT_GEGENGEPRUEFT,
)
GEPRUEFT = (BESTAETIGT, TEILWEISE, ABWEICHEND, ERFASSUNGSLUECKE)
"""Status einer gelesenen Seite: nur sie zählen als Gegenprobe eines Preises."""
VERSUCHT = (*GEPRUEFT, NICHT_PRUEFBAR)
"""Status eines geöffneten Besuchs (gelesen oder mit belegtem Grund gescheitert)."""

ANLASS_AENDERUNG = "preisaenderung"
ANLASS_STICHPROBE = "stichprobe"
ANLASS_FENSTER = "fenster"
"""Das Bündel ist im Fenster fällig (nie oder vor langem gegengeprüft)."""
ANLASS_GLEICHE_SEITE = "gleiche_seite"
"""Nicht fällig, aber auf einer Seite, die der Lauf ohnehin öffnet."""
ANLASS_WIEDERHOLUNG = "wiederholung"
"""Fällig, aber der letzte Versuch scheiterte: verdächtig, je Nacht begrenzt
(``gegenprobe_fenster.VERDAECHTIG_JE_NACHT``)."""

ORDNER = Path("data") / "state" / "gegenprobe"

GRUND_ZEITBUDGET = "Zeitbudget des Laufs erschöpft, nicht geöffnet"
GRUND_KEIN_LESER = "Für diesen Anbieter gibt es noch keinen Kundenweg"
GRUND_GESPERRT = "Seite gesperrt (Bot-Schutz), nicht umgangen"
GRUND_ROBOTS = "robots.txt erlaubt den Abruf nicht"


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
    luecken: list[dict] = field(default_factory=list)
    """Posten, die der Bestand als Lücke führt und die Seite nennt."""
    nicht_gelesen: list[str] = field(default_factory=list)
    gesamt_gespeichert: float | None = None
    gesamt_gelesen: float | None = None
    text: str = ""
    bild: str | None = None
    bild_fehlt: str | None = None

    def __post_init__(self) -> None:
        self._einordnen()
        if self.status not in STATUS:
            raise ValueError(f"unbekannter Status {self.status!r}")
        if self.status in (NICHT_PRUEFBAR, NICHT_GEGENGEPRUEFT, TEILWEISE) and (
            not self.grund
        ):
            raise ValueError(f"{self.status} ohne Grund")
        if self.status == ABWEICHEND and not self.abweichungen:
            raise ValueError("abweichend ohne abweichenden Posten")
        if self.status == ERFASSUNGSLUECKE and not self.luecken:
            raise ValueError("Erfassungslücke ohne gelesenen Posten (Lücke)")

    def _einordnen(self) -> None:
        """Lücken aus ``abweichungen`` nach ``luecken``; ohne echten Widerspruch ist
        „abweichend“ eine Erfassungslücke, das Zeitbudget ``nicht_gegengeprueft``."""
        if self.status == NICHT_PRUEFBAR and self.grund == GRUND_ZEITBUDGET:
            self.status = NICHT_GEGENGEPRUEFT
        abweichungen, luecken = teile_auf(self.abweichungen)
        if luecken:
            self.abweichungen = abweichungen
            self.luecken = [*self.luecken, *luecken]
        if self.status == ABWEICHEND and self.luecken and not self.abweichungen:
            self.status = ERFASSUNGSLUECKE


class GegenprobeFehler(ValueError):
    """Eine Tagesdatei ist unlesbar (Zeile genannt)."""


def teile_auf(eintraege: Iterable[Mapping]) -> tuple[list[dict], list[dict]]:
    """(echte Abweichungen, Lücken): ein Eintrag mit gespeichert None ist eine Lücke
    des Bestands, kein Widerspruch. DIE Trennung für Vergleich und alte Zeilen."""
    liste = [dict(e) for e in eintraege]
    abweichungen = [e for e in liste if e.get("gespeichert") is not None]
    return abweichungen, [e for e in liste if e.get("gespeichert") is None]


def tagesdatei(wurzel: Path, datum: str) -> Path:
    """``data/state/gegenprobe/<datum>.jsonl`` unter ``wurzel``."""
    return wurzel / ORDNER / f"{datum}.jsonl"


def als_zeile(ergebnis: Ergebnis) -> str:
    """Eine Zeile der Tagesdatei."""
    return json.dumps(asdict(ergebnis), ensure_ascii=False, sort_keys=True)


def schreibe_tag(pfad: Path, ergebnisse: Iterable[Ergebnis]) -> None:
    """Schreibt die Datei neu (Teildatei eines Jobs; Tagesdatei: ``ergaenze_tag``)."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text("".join(als_zeile(e) + "\n" for e in ergebnisse), encoding="utf-8")


def ersetzt(alt: Ergebnis | None, neu: Ergebnis) -> bool:
    """Ob ``neu`` die Zeile ``alt`` desselben Bündels und Tages ersetzt: eine geöffnete
    Seite immer, „nicht gegengeprüft“ nur eine fehlende oder ebensolche Zeile."""
    return alt is None or neu.status != NICHT_GEGENGEPRUEFT or alt.status == neu.status


def ergaenze_tag(pfad: Path, neue: Iterable[Ergebnis]) -> list[Ergebnis]:
    """Ergänzt die Tagesdatei um ``neue`` (``ersetzt``) und gibt den Stand zurück."""
    stand = {e.buendel_id: e for e in lies_tag(pfad)}
    for e in neue:
        if ersetzt(stand.get(e.buendel_id), e):
            stand[e.buendel_id] = e
    schreibe_tag(pfad, stand.values())
    return list(stand.values())


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
