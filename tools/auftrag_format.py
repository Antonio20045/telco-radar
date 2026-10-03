"""Prüft das Auftragsformat, bevor ``tools/auftrag.py`` einen Auftrag startet."""

from __future__ import annotations

import csv
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
}

SPALTEN = ("datum", "auftrag", "rolle", "runde", "agent", "exit", "sekunden")
SPALTEN += ("kosten_usd", "token_ein", "token_aus", "ergebnis")


def gemergt(wurzel: Path) -> set[str]:
    """Gibt die Kennungen der Aufträge, die laut Kostendatei gemergt sind."""
    datei = wurzel / KOSTEN
    if not datei.is_file():
        return set()
    with datei.open(encoding="utf-8") as f:
        return {z["auftrag"] for z in csv.DictReader(f) if z["ergebnis"] == GEMERGT}


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
    im_bereich = bereich.startswith(BEREICH_WURZEL) and bereich.endswith("/")
    im_bereich &= bereich != BEREICH_WURZEL and (wurzel / bereich).is_dir()
    pruefungen = {
        "id nur aus Buchstaben, Ziffern, - und _": ID_MUSTER.fullmatch(auftrag["id"]),
        f"art ist weder {' noch '.join(ARTEN)}": art in ARTEN,
        f"bereich ist kein Unterordner von {BEREICH_WURZEL} mit /": im_bereich,
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
    """Hängt Zeilen an die Kostendatei unter ``ort`` an, mit Kopf bei neuer Datei."""
    datei = ort / KOSTEN
    datei.parent.mkdir(parents=True, exist_ok=True)
    neu = not datei.is_file()
    with datei.open("a", encoding="utf-8", newline="") as f:
        schreiber = csv.DictWriter(f, fieldnames=SPALTEN)
        if neu:
            schreiber.writeheader()
        schreiber.writerows(zeilen)
    return datei
