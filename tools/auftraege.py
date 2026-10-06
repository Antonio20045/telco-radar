"""Arbeitet einen Plan aus ``tools/plane.py`` ab, jeden Auftrag über ``auftrag.py``.

Ein Auftrag startet, wenn alle Aufträge aus ``abhaengigVon`` gemergt sind und sein
Bereich sich mit keinem laufenden überschneidet; höchstens ``PARALLEL`` laufen
gleichzeitig. Endet einer nicht mit ``gemergt``, startet kein weiterer mehr: Seine Notiz
macht den Arbeitsbaum unsauber, und jeder spätere Start scheiterte daran.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL / "scripts"))
git_ = importlib.import_module("auftrag_git")
prozess_ = importlib.import_module("auftrag_prozess")
plane_ = importlib.import_module("plane")

PARALLEL = 2
SKRIPT = WURZEL / "tools" / "auftrag.py"
ERGEBNIS = "ergebnis.md"
GEMERGT = 0
NICHT_GESTARTET = "nicht gestartet"


@dataclass
class Stand:
    """Was je Auftrag gelaufen ist; ``ergebnis`` hält den Exit-Code oder den Grund."""

    auftraege: dict[str, dict]
    reihenfolge: list[str]
    ergebnis: dict[str, int | str] = field(default_factory=dict)
    laufend: dict[Future[int], str] = field(default_factory=dict)

    @property
    def gescheitert(self) -> bool:
        """Wahr, sobald ein gestarteter Auftrag nicht gemergt endete."""
        return any(isinstance(e, int) and e != GEMERGT for e in self.ergebnis.values())

    def startbereit(self) -> str | None:
        """Der nächste Auftrag, der jetzt starten darf, sonst ``None``."""
        offen = [k for k in self.reihenfolge if k not in self.ergebnis]
        belegt = [self.auftraege[k]["bereich"] for k in self.laufend.values()]
        if self.gescheitert or len(self.laufend) >= PARALLEL:
            return None
        for kennung in offen:
            if kennung in self.laufend.values():
                continue
            auftrag = self.auftraege[kennung]
            fertig = all(
                self.ergebnis.get(d) == GEMERGT for d in auftrag["abhaengigVon"]
            )
            frei = not any(git_.ueberschneiden(auftrag["bereich"], b) for b in belegt)
            if fertig and frei:
                return kennung
        return None


def laden(ordner: Path) -> Stand:
    """Liest Reihenfolge und Aufträge eines Plans."""
    reihenfolge = json.loads((ordner / plane_.PLAN).read_text("utf-8"))
    auftraege = {
        k: json.loads((ordner / f"{k}.json").read_text("utf-8")) for k in reihenfolge
    }
    return Stand(auftraege, reihenfolge)


def _auftrag(befehl: list[str], ort: Path, log: Path) -> int:
    lauf = prozess_.starten(befehl, ort)
    log.write_text(lauf.stdout + lauf.stderr, "utf-8")
    return lauf.returncode


def abarbeiten(stand: Stand, ordner: Path, befehl: list[str], wurzel: Path) -> None:
    """Startet, was startbereit ist, und wartet, bis nichts mehr läuft."""
    with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
        while True:
            while kennung := stand.startbereit():
                datei, log = ordner / f"{kennung}.json", ordner / f"{kennung}.log"
                print(f"{kennung}: gestartet", flush=True)
                aufruf = [*befehl, str(datei), "--wurzel", str(wurzel)]
                stand.laufend[pool.submit(_auftrag, aufruf, wurzel, log)] = kennung
            if not stand.laufend:
                break
            fertig, _ = wait(stand.laufend, return_when=FIRST_COMPLETED)
            for zukunft in fertig:
                kennung = stand.laufend.pop(zukunft)
                stand.ergebnis[kennung] = zukunft.result()
                print(f"{kennung}: {_text(stand.ergebnis[kennung])}", flush=True)
    for kennung in stand.reihenfolge:
        stand.ergebnis.setdefault(kennung, NICHT_GESTARTET)


def _text(ergebnis: int | str) -> str:
    if ergebnis == GEMERGT:
        return "gemergt"
    return ergebnis if isinstance(ergebnis, str) else f"Exit {ergebnis}, siehe Log"


def bericht(stand: Stand, ordner: Path) -> str:
    """Eine Zeile je Auftrag mit Ergebnis und Log, dazu der nächste Schritt."""
    zeilen = [f"# Ergebnis {ordner.name}", ""]
    for kennung in stand.reihenfolge:
        ergebnis = _text(stand.ergebnis[kennung])
        zeilen.append(f"- {kennung}: {ergebnis} ({stand.auftraege[kennung]['ziel']})")
    if stand.gescheitert:
        zeilen += ["", "Notiz unter outputs/auftraege/, Log je Auftrag im Planordner."]
    elif all(e == GEMERGT for e in stand.ergebnis.values()):
        zeilen += [
            "",
            "Alles gemergt: git pull --rebase origin main, git push origin main",
        ]
    text = "\n".join(zeilen) + "\n"
    (ordner / ERGEBNIS).write_text(text, "utf-8")
    return text


def main(argv: list[str] | None = None) -> int:
    """Arbeitet den Plan im Ordner ab; Exit 0 nur, wenn alles gemergt ist."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("ordner", type=Path, help="Planordner aus tools/plane.py")
    parser.add_argument("--wurzel", type=Path, default=WURZEL)
    parser.add_argument("--agent", help="an tools/auftrag.py weitergereicht")
    parser.add_argument("--skript", type=Path, default=SKRIPT)
    argumente = parser.parse_args(argv)
    try:
        stand = laden(argumente.ordner)
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as fehler:
        print(f"Plan nicht lesbar: {type(fehler).__name__}: {fehler}")
        return 1
    befehl = [sys.executable, str(argumente.skript)]
    befehl += ["--agent", argumente.agent] if argumente.agent else []
    abarbeiten(stand, argumente.ordner, befehl, argumente.wurzel.resolve())
    print(bericht(stand, argumente.ordner), end="")
    return 0 if all(e == GEMERGT for e in stand.ergebnis.values()) else 2


if __name__ == "__main__":
    sys.exit(main())
