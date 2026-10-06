"""Macht aus einem Wunsch eine Spezifikation und zerlegt sie in Aufträge.

Der Planer ist ein Agent in der Rolle ``suchen``: Er liest Code und Doku und ändert
nichts. Seine Antwort ist ein JSON mit Spezifikation und Unteraufgaben; das Skript
vergibt die Kennungen ``<kennung>-<nr>``, prüft jede Unteraufgabe mit derselben
Formatprüfung wie ``tools/auftrag.py`` und schreibt alles in einen Ordner außerhalb
des Repos. ``tools/auftraege.py`` arbeitet den Ordner danach ab.
"""

from __future__ import annotations

import argparse
import importlib
import json
import shlex
import sys
from enum import IntEnum
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL / "scripts"))
format_ = importlib.import_module("auftrag_format")
prozess_ = importlib.import_module("auftrag_prozess")
rolle_ = importlib.import_module("claude_rolle")

ROLLE = "suchen"
VERSUCHE = 2
HOECHSTENS = 5
PLAN = "plan.json"
SPEZIFIKATION = "spezifikation.md"
ROH = "planer-roh.txt"
STANDARD_AGENT = f"{format_.ECHTER_AGENT} -p --output-format json"
PROMPT = """Rolle Planer. Du änderst nichts, du planst.

Wunsch von Antonio: {wunsch}

Lies CLAUDE.md, docs/seitenauftrag.md, die CLAUDE.md im betroffenen Ordner unter
src/telco_radar/ und den Code, den der Wunsch berührt. Schreib dann eine kurze
Spezifikation auf Deutsch (was sich auf welcher Seite sichtbar ändert, was gleich
bleibt) und zerlege sie in 1 bis {hoechstens} Unteraufgaben. Jede Unteraufgabe ist
ein Auftrag nach docs/seitenauftrag.md: eine kleine Änderung mit eigenem Abnahmetest,
der die Seite rendert, und einem Bereich so eng wie möglich (ein Modul .py vor einem
Ordner), damit unabhängige Aufträge parallel laufen. Prüf mit grep unter tests/, dass
kein bestehender Test einen Text festhält, den eine Unteraufgabe ändern soll; sonst
nenne das in der Spezifikation unter "Grenzen" und lass die Unteraufgabe weg.

Antworte am Ende nur mit einem JSON-Objekt, ohne Text davor oder danach:
{{"spezifikation": "Markdown", "auftraege": [{{"nr": 1, "art": "verhalten",
"ziel": "…", "bereich": "src/telco_radar/…", "erwarteteDateien": ["…"],
"vorbild": "…", "seite": ["geraete.html"], "datenquelle": {{}},
"abnahme": "tests/test_…py", "erwarteterFehler": "…", "abhaengigVon": [],
"migration": null, "wasDarfNiePassieren": {{"wiederholung": "…",
"gleichzeitig": "…", "zeitueberschreitung": "…", "abbruch": "…"}}}}]}}
abhaengigVon nennt die nr früherer Unteraufgaben derselben Antwort."""


class Ende(IntEnum):
    """Exit-Code des Planers."""

    GEPLANT = 0
    NICHT_GESTARTET = 1
    PLAN_UNGUELTIG = 2


class PlanFehler(ValueError):
    """Die Antwort des Planers ist kein gültiger Plan."""


def _json_aus(text: str) -> dict:
    anfang, ende = text.find("{"), text.rfind("}")
    if anfang < 0 or ende < anfang:
        raise PlanFehler("keine JSON-Antwort")
    try:
        plan = json.loads(text[anfang : ende + 1])
    except json.JSONDecodeError as fehler:
        raise PlanFehler(f"JSON nicht lesbar: {fehler}") from fehler
    if not isinstance(plan, dict):
        raise PlanFehler("die Antwort ist kein JSON-Objekt")
    return plan


def auftraege(antwort: str, kennung: str, wurzel: Path) -> tuple[str, list[dict]]:
    """Spezifikation und geprüfte Aufträge aus der Antwort des Planers."""
    plan = _json_aus(antwort)
    spezifikation, liste = plan.get("spezifikation"), plan.get("auftraege")
    if not isinstance(spezifikation, str) or not spezifikation.strip():
        raise PlanFehler("spezifikation fehlt")
    if not isinstance(liste, list) or not 1 <= len(liste) <= HOECHSTENS:
        raise PlanFehler(f"auftraege ist keine Liste mit 1 bis {HOECHSTENS} Einträgen")
    fehler: list[str] = []
    nummern: list[object] = []
    fertig: list[dict] = []
    for teil in liste:
        if not isinstance(teil, dict):
            raise PlanFehler("ein Auftrag ist kein JSON-Objekt")
        nr = teil.get("nr")
        vorher, abhaengig = list(nummern), teil.get("abhaengigVon")
        if not isinstance(abhaengig, list):
            fehler.append(f"Auftrag {nr}: abhaengigVon ist keine Liste")
            abhaengig = []
        if offen := [n for n in abhaengig if n not in vorher]:
            fehler.append(f"Auftrag {nr}: abhaengigVon {offen} ist keine frühere nr")
        nummern.append(nr)
        auftrag = {k: v for k, v in teil.items() if k != "nr"}
        auftrag |= {"id": f"{kennung}-{nr}", "abhaengigVon": []}
        fehler += [f"Auftrag {nr}: {f}" for f in format_.formatfehler(auftrag, wurzel)]
        if (wurzel / str(auftrag.get("abnahme"))).exists():
            fehler.append(f"Auftrag {nr}: abnahme {auftrag['abnahme']} gibt es schon")
        auftrag["abhaengigVon"] = [f"{kennung}-{n}" for n in abhaengig]
        fertig.append(auftrag)
    if len(set(map(str, nummern))) != len(nummern):
        fehler.append("nr ist nicht eindeutig")
    abnahmen = [a.get("abnahme") for a in fertig]
    if len(set(map(str, abnahmen))) != len(abnahmen):
        fehler.append("zwei Aufträge teilen eine abnahme")
    if fehler:
        raise PlanFehler("\n".join(fehler))
    return spezifikation.strip(), fertig


def _fragen(agent: list[str], wurzel: Path, prompt: str) -> str:
    einstellungen = json.dumps(rolle_.einstellungen(ROLLE))
    befehl = [*agent, "--settings", einstellungen]
    umgebung = prozess_.ohne_git({"TELCO_ROLLE": ROLLE})
    lauf = prozess_.starten(befehl, wurzel, prompt, umgebung)
    if lauf.returncode:
        raise PlanFehler(f"Planer Exit {lauf.returncode}\n{lauf.stderr[-2000:]}")
    zeilen = lauf.stdout.strip().splitlines() or ["{}"]
    try:
        bericht = json.loads(zeilen[-1])
    except json.JSONDecodeError:
        return lauf.stdout
    ergebnis = bericht.get("result") if isinstance(bericht, dict) else None
    return ergebnis if isinstance(ergebnis, str) else lauf.stdout


def schreiben(ordner: Path, spezifikation: str, liste: list[dict]) -> None:
    """Legt Spezifikation, Aufträge und Reihenfolge im Ordner ab."""
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / SPEZIFIKATION).write_text(spezifikation + "\n", "utf-8")
    for auftrag in liste:
        text = json.dumps(auftrag, ensure_ascii=False, indent=1) + "\n"
        (ordner / f"{auftrag['id']}.json").write_text(text, "utf-8")
    ids = [a["id"] for a in liste]
    (ordner / PLAN).write_text(json.dumps(ids, ensure_ascii=False) + "\n", "utf-8")


def planen(
    wunsch: str, kennung: str, ordner: Path, wurzel: Path, agent: list[str]
) -> Ende:
    """Fragt den Planer höchstens ``VERSUCHE``-mal und schreibt den gültigen Plan."""
    prompt, befund, antwort = (
        PROMPT.format(wunsch=wunsch, hoechstens=HOECHSTENS),
        "",
        "",
    )
    for _ in range(VERSUCHE):
        frage = prompt + (
            f"\n\nDein letzter Plan war ungültig:\n{befund}" * bool(befund)
        )
        try:
            antwort = _fragen(agent, wurzel, frage)
            spezifikation, liste = auftraege(antwort, kennung, wurzel)
        except PlanFehler as fehler:
            befund = str(fehler)
            continue
        schreiben(ordner, spezifikation, liste)
        print(f"Spezifikation: {ordner / SPEZIFIKATION}")
        for auftrag in liste:
            nach = ", ".join(auftrag["abhaengigVon"]) or "sofort"
            print(f"- {auftrag['id']} ({nach}): {auftrag['ziel']}")
        print(f"Starten: .venv/bin/python tools/auftraege.py {ordner}")
        return Ende.GEPLANT
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / ROH).write_text(f"{befund}\n\n{antwort}\n", "utf-8")
    print(f"Plan ungültig nach {VERSUCHE} Versuchen:\n{befund}\nRoh: {ordner / ROH}")
    return Ende.PLAN_UNGUELTIG


def main(argv: list[str] | None = None) -> int:
    """Liest Kennung und Wunsch und legt den Plan unter ``--ordner`` ab."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("kennung", help="Kennung des Wunsches, etwa S2")
    parser.add_argument("wunsch", help="ein Satz, was auf der Seite anders sein soll")
    parser.add_argument("--ordner", type=Path, help="Standard ~/auftraege/<kennung>")
    parser.add_argument("--wurzel", type=Path, default=WURZEL)
    parser.add_argument("--agent", default=STANDARD_AGENT, help="Prompt auf stdin")
    argumente = parser.parse_args(argv)
    kennung, wurzel = argumente.kennung, argumente.wurzel.resolve()
    ordner = argumente.ordner or Path.home() / "auftraege" / kennung
    gruende = []
    if not format_.ID_MUSTER.fullmatch(f"{kennung}-1"):
        gruende.append("kennung nur aus Buchstaben, Ziffern, - und _")
    if ordner.exists() and any(ordner.iterdir()):
        gruende.append(f"{ordner} ist nicht leer; andere kennung oder Ordner leeren")
    if ordner.resolve().is_relative_to(wurzel):
        gruende.append("der Ordner liegt im Repo; er gehört außerhalb")
    if not argumente.wunsch.strip():
        gruende.append("wunsch ist leer")
    if gruende:
        print("Planer startet nicht:\n- " + "\n- ".join(gruende))
        return Ende.NICHT_GESTARTET
    agent = shlex.split(argumente.agent)
    return planen(argumente.wunsch, kennung, ordner, wurzel, agent)


if __name__ == "__main__":
    sys.exit(main())
