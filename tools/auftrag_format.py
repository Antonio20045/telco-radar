"""Prüft das Auftragsformat, bevor ``tools/auftrag.py`` einen Auftrag startet."""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

ARTEN = ("umbau", "verhalten")
TEXTE = ("id", "art", "ziel", "bereich", "vorbild", "abnahme")
LISTEN = ("erwarteteDateien", "seite", "abhaengigVon")
OBJEKTE = ("datenquelle", "wasDarfNiePassieren")
PFLICHT = {**dict.fromkeys(TEXTE, str), **dict.fromkeys(LISTEN, list)}
PFLICHT |= dict.fromkeys(OBJEKTE, dict)
NIE_FAELLE = ("wiederholung", "gleichzeitig", "zeitueberschreitung", "abbruch")
ID_MUSTER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,40}")
ABNAHME_MUSTER = re.compile(r"tests/(\w+/)*test_\w+\.py")
BEREICH_WURZEL = "src/telco_radar/"
AUFTRAEGE = "outputs/auftraege"
KOSTEN = f"{AUFTRAEGE}/kosten.csv"
GEMERGT = "gemergt"
ECHTER_AGENT = "claude"

SOLL = {
    "verhalten": "scheitert fachlich, und die Fehlermeldung enthält „{}“",
    "umbau": "ist heute grün und hält fest, was der Umbau nicht ändern darf",
}
PROMPT = {
    "test": "Rolle Abnahmetest. Schreibe {abnahme} für den Auftrag in TELCO_AUFTRAG."
    " Er {soll}; ein Import- oder Tippfehler zählt nicht. Ändere nur tests/.",
    "bau": "Rolle Bau. Mach {abnahme} für den Auftrag in TELCO_AUFTRAG grün, ohne ihn"
    " zu ändern; Produktcode nur unter {bereich}, höchstens {grenze} Zeilen. Fehlt"
    " eine Änderung außerhalb des Bereichs, schreib einen Satz, was vorher umgebaut"
    " werden muss, in die Datei TELCO_VORAUSSETZUNG und hör auf. Die Commit-Nachricht"
    " kommt in die Datei TELCO_COMMIT_NACHRICHT.",
    "pruefer": "Rolle Prüfer. Prüfe den Auftrag in TELCO_AUFTRAG im Worktree: Diff mit"
    " git diff HEAD und neue Dateien, Abnahme {abnahme}, Bereich {bereich}."
    " Reproduktionen nur im Ordner TELCO_PRUEFER_ORDNER; antworte nur als JSON.",
}
ECHTE_ROLLEN = ("bau", "pruefer")

SPALTEN = ("datum", "auftrag", "rolle", "runde", "agent", "exit", "sekunden")
SPALTEN += ("kosten_usd", "token_ein", "token_aus", "modell", "ergebnis")


def gemergt(wurzel: Path) -> set[str]:
    """Gibt die Kennungen der Aufträge, die laut Kostendatei gemergt sind."""
    datei = wurzel / KOSTEN
    if not datei.is_file():
        return set()
    with datei.open(encoding="utf-8") as f:
        return {z["auftrag"] for z in csv.DictReader(f) if z["ergebnis"] == GEMERGT}


def echte_auftraege(wurzel: Path) -> set[str]:
    """Gemergte Aufträge, deren Bau und Prüfer ein Claude-Modell mit Kosten waren."""
    datei = wurzel / KOSTEN
    if not datei.is_file():
        return set()
    with datei.open(encoding="utf-8") as f:
        zeilen = list(csv.DictReader(f))
    echt = {
        (z["auftrag"], z["rolle"])
        for z in zeilen
        if z.get("agent") == ECHTER_AGENT
        and "claude-" in (z.get("modell") or "")
        and _positiv(z.get("kosten_usd"))
    }
    return {
        z["auftrag"]
        for z in zeilen
        if z.get("ergebnis") == GEMERGT
        and all((z["auftrag"], r) in echt for r in ECHTE_ROLLEN)
    }


def _positiv(text: str | None) -> bool:
    try:
        return float(text or "") > 0
    except ValueError:
        return False


def formatfehler(auftrag: object, wurzel: Path) -> list[str]:
    """Nennt jeden Verstoß gegen das Auftragsformat; leer heißt startbereit."""
    if not isinstance(auftrag, dict):
        return ["Auftrag ist kein JSON-Objekt"]
    fehler = [
        f"Feld {name} fehlt oder ist kein {typ.__name__}"
        for name, typ in PFLICHT.items()
        if not isinstance(auftrag.get(name), typ)
    ]
    if fehler:
        return fehler
    fehler += [
        f"wasDarfNiePassieren.{fall} fehlt oder ist leer"
        for fall in NIE_FAELLE
        if not isinstance(text := auftrag["wasDarfNiePassieren"].get(fall), str)
        or not text.strip()
    ]
    bereich, art = auftrag["bereich"], auftrag["art"]
    erwartet = auftrag.get("erwarteterFehler")
    ordner = bereich.endswith("/") and (wurzel / bereich).is_dir()
    modul = bereich.endswith(".py") and (wurzel / bereich).is_file()
    im_bereich = bereich.startswith(BEREICH_WURZEL) and bereich != BEREICH_WURZEL
    im_bereich &= ordner or modul
    im_bereich &= all(
        teil not in {"", ".", ".."} for teil in bereich.removesuffix("/").split("/")
    )
    pruefungen = {
        "id nur aus Buchstaben, Ziffern, - und _": ID_MUSTER.fullmatch(auftrag["id"]),
        f"art ist weder {' noch '.join(ARTEN)}": art in ARTEN,
        f"bereich ist kein Unterordner von {BEREICH_WURZEL} mit / und kein Modul"
        " .py darin": im_bereich,
        "abnahme ist keine Datei tests/…/test_*.py": ABNAHME_MUSTER.fullmatch(
            auftrag["abnahme"]
        ),
        "erwarteterFehler fehlt; ein Verhaltensauftrag beginnt rot": art != "verhalten"
        or (isinstance(erwartet, str) and bool(erwartet.strip())),
        "erwarteterFehler bei art umbau; der Abnahmetest bleibt grün": art != "umbau"
        or erwartet is None,
        "migration ist kein Text": isinstance(auftrag.get("migration"), str | None),
    }
    fehler += [text for text, gilt in pruefungen.items() if not gilt]
    offen = {str(k) for k in auftrag["abhaengigVon"]} - gemergt(wurzel)
    return fehler + [f"abhaengigVon {k} ist nicht gemergt" for k in sorted(offen)]


def zahl(quelle: object, schluessel: str) -> object:
    """Gibt eine Zahl aus dem Agentenbericht oder leer, nie 0 für eine Lücke."""
    wert = quelle.get(schluessel) if isinstance(quelle, dict) else None
    return wert if isinstance(wert, int | float) and not isinstance(wert, bool) else ""


def kosten_schreiben(zeilen: list[dict[str, object]], ort: Path) -> Path:
    """Hängt Zeilen an die Kostendatei an; mit altem Kopf wird sie umgeschrieben."""
    datei = ort / KOSTEN
    datei.parent.mkdir(parents=True, exist_ok=True)
    alte: list[dict[str, object]] = []
    neu = not datei.is_file()
    if not neu:
        with datei.open(encoding="utf-8", newline="") as f:
            leser = csv.DictReader(f)
            alte = [dict.fromkeys(SPALTEN, "") | z for z in leser]
            neu = tuple(leser.fieldnames or ()) != SPALTEN
    puffer = io.StringIO()
    schreiber = csv.DictWriter(puffer, fieldnames=SPALTEN)
    if neu:
        schreiber.writeheader()
    schreiber.writerows([*alte, *zeilen] if neu else zeilen)
    zwischen = datei.with_name(f"{datei.name}.neu")
    if neu:
        zwischen.write_text(puffer.getvalue(), "utf-8", newline="")
        zwischen.replace(datei)
    else:
        with datei.open("a", encoding="utf-8", newline="") as f:
            f.write(puffer.getvalue())
    return datei


def notiz(wurzel: Path, auftrag: dict, wt: Path, ende: str, befunde: list[str]) -> Path:
    """Schreibt die Notiz eines nicht gemergten Auftrags nach ``outputs/auftraege/``."""
    datei = wurzel / AUFTRAEGE / f"{auftrag['id']}-notiz.md"
    datei.parent.mkdir(parents=True, exist_ok=True)
    teile = [f"# Auftrag {auftrag['id']}: {ende}"]
    teile += [f"Ziel: {auftrag['ziel']}", f"Worktree: {wt}"]
    teile += [f"## Befund {n}\n\n```\n{b}\n```" for n, b in enumerate(befunde, 1)]
    datei.write_text("\n\n".join(teile) + "\n", "utf-8")
    return datei


def verbrauch(bericht: object) -> dict[str, object]:
    """Kosten, Token und Modelle aus dem Agentenbericht; Lücken bleiben leer."""
    nutzung = bericht.get("usage") if isinstance(bericht, dict) else None
    modelle = bericht.get("modelUsage") if isinstance(bericht, dict) else None
    return {
        "kosten_usd": zahl(bericht, "total_cost_usd"),
        "token_ein": zahl(nutzung, "input_tokens"),
        "token_aus": zahl(nutzung, "output_tokens"),
        "modell": " ".join(sorted(modelle)) if isinstance(modelle, dict) else "",
    }
