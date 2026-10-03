"""Liest, was pytest meldet, und hält es gegen die Rohaufzeichnung der Testfunktionen.

Die Rohaufzeichnung schreibt das Plugin ``leiter_plugin/leiter_roh.py``; ein als
bestanden gemeldeter Test, dessen Funktion scheiterte oder nie lief, ist umgeschrieben,
und eine Testfunktion, die schon vor der Aufzeichnung umhüllt war, ist fremd. Die rohe
Sammlung ohne Projekteinstellungen und ohne conftest ist die Menge, die laufen muss.
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
_PARAMETER = re.compile(r"^(?P<basis>[^\[]+)(?:\[(?P<id>.*)\])?$")


def rohe_sammlung_ini(wurzel: Path, python_files: str) -> str:
    """Gibt eine eigene ini zurück, mit der die rohe Sammlung pyproject.toml umgeht.

    Sie setzt nur, was die Leiter selbst vorgibt: Testordner, Dateimuster und die
    Importpfade; ``addopts``, ``testpaths`` und die übrigen Muster bleiben Vorgabe.
    """
    return (
        "[pytest]\n"
        f"python_files = {python_files}\n"
        f"pythonpath = {wurzel / 'src'} {wurzel}\n"
    )


def rohe_sammlung_befehl(python: str, ini: Path, wurzel: Path) -> list[str]:
    """Sammelt ``tests/`` ohne conftest, ohne pyproject.toml und ohne ``addopts``."""
    return [
        python,
        "-m",
        "pytest",
        "--collect-only",
        "-q",
        "--noconftest",
        "-c",
        str(ini),
        "--rootdir",
        str(wurzel),
        "-p",
        "no:cacheprovider",
        str(wurzel / "tests"),
    ]


def gesammelte_ids(ausgabe: str) -> set[str]:
    """Liest die Node-IDs aus ``pytest --collect-only -q``: alles vor der Leerzeile."""
    ids, _, _ = ausgabe.partition("\n\n")
    return {zeile for zeile in ids.splitlines() if "::" in zeile}


def lies_gelaufen(ordner: Path) -> set[str]:
    """Gibt jeden Test zurück, dessen Ablaufbeginn das Plugin aufgezeichnet hat."""
    return {
        zeile.partition(" ")[2]
        for datei in sorted(ordner.glob("*.lief"))
        for zeile in datei.read_text(encoding="utf-8").splitlines()
        if zeile.startswith("lief ")
    }


def ohne_ergebnis(
    gestartet: set[str], roh: dict[str, str], rot: dict[str, str], nicht_gelaufen: int
) -> list[str]:
    """Nennt Tests, deren Ablauf begann, ohne dass ihre Funktion lief oder rot endete.

    Erlaubt sind so viele, wie pytest übersprungene und ``xfail``-Tests meldet; mehr
    heißt, dass ein Ablaufbeginn ohne Lauf gemeldet wurde, etwa von einer conftest.
    """
    ohne = sorted(gestartet - set(roh) - set(rot))
    if len(ohne) <= nicht_gelaufen:
        return []
    kopf = (
        f"{len(ohne)} Tests begannen ohne Lauf und ohne rotes Ergebnis, übersprungen"
        f" oder xfail sind nur {nicht_gelaufen}:"
    )
    return [kopf, *ohne]


def abgewaehlt(roh: set[str], gelaufen: set[str]) -> list[str]:
    """Nennt jeden Test der rohen Sammlung, dessen Ablauf im Lauf nie begann.

    Parameter aus einer conftest fehlen in der rohen Sammlung; ein roher Test gilt
    deshalb auch als gelaufen, wenn ein Lauf derselben Funktion seine Parameter-ID als
    ganzes Glied zwischen ``-`` enthält oder er selbst keine hat.
    """
    je_basis: dict[str, list[str]] = {}
    for test in gelaufen:
        teile = _PARAMETER.match(test)
        if teile:
            je_basis.setdefault(teile["basis"], []).append(teile["id"] or "")
    fehlend = []
    for test in sorted(roh - gelaufen):
        teile = _PARAMETER.match(test)
        ids = je_basis.get(teile["basis"], []) if teile else []
        eigene = (teile["id"] or "") if teile else ""
        if not any(not eigene or f"-{eigene}-" in f"-{i}-" for i in ids):
            fehlend.append(f"{test}: steht im Repo, lief aber nicht (abgewählt)")
    return fehlend


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


_VORRANG = {"fremd": 2, "fehler": 1}


def lies_roh(ordner: Path) -> dict[str, str]:
    """Gibt je Test zurück, wie seine Funktion endete: ``ok``, ``fehler``, ``fremd``.

    Endet ein Test in mehreren Läufen verschieden, gilt ``fremd`` vor ``fehler``
    vor ``ok``.
    """
    roh: dict[str, str] = {}
    for datei in sorted(ordner.glob("*.txt")):
        for zeile in datei.read_text(encoding="utf-8").splitlines():
            art, _, nodeid = zeile.partition(" ")
            if _VORRANG.get(art, 0) >= _VORRANG.get(roh.get(nodeid, ""), 0):
                roh[nodeid] = art
    return roh


def fremde(roh: dict[str, str]) -> list[str]:
    """Nennt jede Testfunktion, die schon vor der Aufzeichnung umhüllt war."""
    return [
        f"{test}: Testfunktion vor der Leiter umhüllt oder ersetzt"
        for test, art in sorted(roh.items())
        if art == "fremd"
    ]


def umgeschrieben(gruen: set[str], roh: dict[str, str]) -> list[str]:
    """Nennt jeden als bestanden gemeldeten Test, dessen Funktion nicht ok endete.

    Eine Meldung ``PASSED <test> - <text>`` trägt den Text eines umgeschriebenen
    Fehlers; ``-`` kann aber auch in der ID eines parametrisierten Tests stehen.
    """
    falsch = []
    for zeile in sorted(gruen):
        test = zeile if zeile in roh else zeile.split(" - ", 1)[0]
        if roh.get(test) not in ("ok", "fremd"):
            wie = "scheiterte" if roh.get(test) == "fehler" else "lief nie"
            falsch.append(f"{test}: als bestanden gemeldet, die Testfunktion {wie}")
    return falsch


def pruefe_ergebnisse(
    rot: dict[str, str], gruen: set[str], roh: dict[str, str], kanarie: str
) -> list[str]:
    """Hält Meldung und Rohaufzeichnung gegeneinander; nimmt den Kanarienvogel aus rot.

    Der Kanarienvogel muss rot gemeldet und roh gescheitert sein, sein Zwilling grün;
    jeder andere als bestanden gemeldete Test muss roh ``ok`` sein, und keine
    Testfunktion darf fremd sein, ob rot oder grün gemeldet.
    """
    gescheitert = rot.pop(f"{kanarie}::test_muss_scheitern", None)
    if gescheitert is None or f"{kanarie}::test_muss_bestehen" not in gruen:
        return [f"{kanarie}: Ergebnisse werden umgeschrieben oder abgewählt"]
    if roh.get(f"{kanarie}::test_muss_scheitern") not in ("fehler", "fremd"):
        return [f"Rohaufzeichnung fehlt: Plugin {PLUGIN} lief nicht"]
    falsch = umgeschrieben(gruen, roh)
    return (["Ergebnisse umgeschrieben:", *falsch] if falsch else []) + fremde(roh)
