"""Liest, was pytest meldet, und hält es gegen die Rohaufzeichnung der Testfunktionen.

Die Rohaufzeichnung schreibt das Plugin ``leiter_plugin/leiter_roh.py``; ein als
bestanden gemeldeter Test, dessen Funktion scheiterte oder nie lief, ist umgeschrieben.
"""

from __future__ import annotations

import re
from pathlib import Path

PLUGIN_ORDNER = Path(__file__).resolve().parent / "leiter_plugin"
PLUGIN = "leiter_roh"
ROH_VARIABLE = "TELCO_LEITER_ROH"
_GESAMMELT = re.compile(
    r"^\d+ workers? \[(\d+) items?\]$"
    r"|^collected \d+ items?(?: / \d+ deselected)? / (\d+) selected"
    r"|^collected (\d+) items?$",
    re.MULTILINE,
)
_SCHLUSSZEILE = re.compile(r"^=+ (.+) in [\d.]+s(?: \([\d:]+\))? =+$", re.MULTILINE)
_NICHT_AUSGEFUEHRT = re.compile(r"(\d+) (?:skipped|xfailed)\b")


def pytest_ausgang(ausgabe: str) -> tuple[dict[str, str], set[str]]:
    """Gibt gescheiterte Tests mit ihrer Zeile und bestandene aus ``-rfEp`` zurück."""
    rot: dict[str, str] = {}
    gruen: set[str] = set()
    _, _, zusammenfassung = ausgabe.partition("short test summary info")
    for zeile in zusammenfassung.splitlines():
        art, _, rest = zeile.partition(" ")
        if art in ("FAILED", "ERROR"):
            rot[rest.split(" - ", 1)[0]] = zeile
        elif art == "PASSED":
            gruen.add(rest)
    return rot, gruen


def gesammelte_tests(ausgabe: str) -> int | None:
    """Liest, wie viele Tests pytest nach Auswahl ausführt; ``None`` heißt unlesbar."""
    treffer = _GESAMMELT.search(ausgabe)
    if treffer is None:
        return None
    return int(next(gruppe for gruppe in treffer.groups() if gruppe is not None))


def nicht_ausgefuehrte_tests(ausgabe: str) -> int | None:
    """Zählt übersprungene und ``xfail``-Tests der Schlusszeile; ``None``: unlesbar."""
    zeilen = _SCHLUSSZEILE.findall(ausgabe)
    if not zeilen:
        return None
    return sum(int(n) for n in _NICHT_AUSGEFUEHRT.findall(zeilen[-1]))


def lies_roh(ordner: Path) -> dict[str, str]:
    """Gibt je Test zurück, wie seine Funktion endete: ``ok`` oder ``fehler``."""
    roh: dict[str, str] = {}
    for datei in sorted(ordner.glob("*.txt")):
        for zeile in datei.read_text(encoding="utf-8").splitlines():
            art, _, nodeid = zeile.partition(" ")
            roh[nodeid] = "fehler" if roh.get(nodeid) == "fehler" else art
    return roh


def umgeschrieben(gruen: set[str], roh: dict[str, str]) -> list[str]:
    """Nennt jeden als bestanden gemeldeten Test, dessen Funktion nicht ok endete.

    Eine Meldung ``PASSED <test> - <text>`` trägt den Text eines umgeschriebenen
    Fehlers; ``-`` kann aber auch in der ID eines parametrisierten Tests stehen.
    """
    falsch = []
    for zeile in sorted(gruen):
        test = zeile if zeile in roh else zeile.split(" - ", 1)[0]
        if roh.get(test) != "ok":
            wie = "scheiterte" if roh.get(test) == "fehler" else "lief nie"
            falsch.append(f"{test}: als bestanden gemeldet, die Testfunktion {wie}")
    return falsch


def pruefe_ergebnisse(
    rot: dict[str, str], gruen: set[str], roh: dict[str, str], kanarie: str
) -> list[str]:
    """Hält Meldung und Rohaufzeichnung gegeneinander; nimmt den Kanarienvogel aus rot.

    Der Kanarienvogel muss rot gemeldet und roh gescheitert sein, sein Zwilling grün;
    jeder andere als bestanden gemeldete Test muss roh ``ok`` sein.
    """
    gescheitert = rot.pop(f"{kanarie}::test_muss_scheitern", None)
    if gescheitert is None or f"{kanarie}::test_muss_bestehen" not in gruen:
        return [f"{kanarie}: Ergebnisse werden umgeschrieben oder abgewählt"]
    if roh.get(f"{kanarie}::test_muss_scheitern") != "fehler":
        return [f"Rohaufzeichnung fehlt: Plugin {PLUGIN} lief nicht"]
    falsch = umgeschrieben(gruen, roh)
    return ["Ergebnisse umgeschrieben:", *falsch] if falsch else []
