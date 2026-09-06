"""Eine leere Bewertungsrunde darf die Titelseite nicht ihrer Redaktion
entziehen (Ticket E3B, 05.09.2026).

Der Ausloeser vom 04.09.2026: DeepSeek war "not usable on this account", der
Anthropic-Anker wurde von der Anthropic-API mit einem Guthaben-Fehler
abgewiesen (HTTP 400, "credit balance too low") - beide Konten leer, kein
Codefehler. Das Ergebnis waren 0 bewertete Meldungen, und die Pipeline hat
trotzdem veroeffentlicht: die Titelseite zeigte "Diese Woche keine
priorisierte Meldung", der Bericht einen unverdichteten Roh-Digest. Fuer den
Leser sah eine leere Bewertung wie Stillstand aus, nicht wie ein
voruebergehender Ausfall - und CI fiel an der Foliendatei, die ohne Meldungen
keine Quellenfolie bauen kann.

Die Regel jetzt: liefert eine Runde 0 bewertete Meldungen (egal warum -
kein neuer Stoff oder ein ausgefallener Analyse-Dienst), bleibt die
Titelseite bei der letzten Ausgabe stehen, deren Redaktion tatsaechlich
gelaufen ist (`run.editor_used == True` UND mindestens eine bewertete
Meldung). Uebernommen werden NUR die Meldungen und der Fliesstext - die
Zahlen, die ueber die aktuelle Runde berichten (`stats`, `run`), bleiben die
der aktuellen Runde. Sonst wuerde eine leere Runde vorgaukeln, sie haette
etwas geliefert.

Ein Bericht, der SELBST schon eine Uebernahme ist (`redaktion_ausfall`
gesetzt), zaehlt nicht als gueltig - eine Kette von Uebernahmen soll immer
auf den echten Ursprung zeigen, nicht auf die zuletzt uebernommene Ausgabe.
Das haelt den sichtbaren "Stand:"-Hinweis stabil, auch wenn mehrere Runden
in Folge ausfallen.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def bewertete_meldungen(report: dict) -> int:
    """Summe aller Highlights ueber alle Regionen und Themenfelder."""
    return sum(len(r.get("highlights") or [])
               for r in (report.get("regions") or {}).values())


def ist_gueltige_redaktion(report: dict) -> bool:
    """True, wenn DIESER Bericht aus einer echten Redaktion stammt.

    Zwei Bedingungen, beide muessen gelten: der Editor ist wirklich
    gelaufen (`run.editor_used`), und es gab ueberhaupt etwas zu redigieren.
    Der zweite Punkt faengt den Sonderfall ab, in dem der Editor auf einer
    komplett leeren Eingabe erfolgreich einen "nichts Neues"-Text schreibt -
    das ist ehrlich fuer SEINE eigene Ausgabe, aber kein Stand, den eine
    spaetere leere Runde sinnvoll uebernehmen koennte.
    """
    if report.get("redaktion_ausfall"):
        return False
    if not (report.get("run") or {}).get("editor_used"):
        return False
    return bewertete_meldungen(report) > 0


def letzte_gueltige_redaktion(reports_dir: Path, vor_datum: str) -> dict | None:
    """Der juengste Bericht VOR `vor_datum` mit einer echten Redaktion.

    None, wenn es keinen gibt - beim allerersten Lauf zum Beispiel, oder
    wenn das Archiv noch nie eine erfolgreiche Redaktion gesehen hat. Dann
    bleibt es beim bisherigen Verhalten: es gibt nichts zu bewahren, und
    eine leere Titelseite ist in diesem einen Fall die ehrliche Auskunft.
    """
    if not reports_dir.exists():
        return None
    kandidaten = sorted(
        (f for f in reports_dir.glob("*.json")
         if _DATE_RE.fullmatch(f.stem) and f.stem < vor_datum),
        reverse=True)
    for pfad in kandidaten:
        try:
            report = json.loads(pfad.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Ueberspringe unlesbaren Bericht %s: %s", pfad, exc)
            continue
        if ist_gueltige_redaktion(report):
            return report
    return None


def uebernehmen(regional: dict, body: str, competitor_profiles: list,
                reports_dir: Path, heutiges_datum: str,
                grund: str) -> tuple[dict, str, list, dict | None]:
    """Bei 0 bewerteten Meldungen die letzte gueltige Redaktion uebernehmen.

    Gibt IMMER ein 4-Tupel zurueck (regions, briefing_md, competitors,
    redaktion_ausfall). Das vierte Feld ist None, solange die aktuelle Runde
    selbst etwas geliefert hat ODER es keine gueltige Vorgaenger-Redaktion
    gibt - in beiden Faellen bleiben die ersten drei Werte unveraendert.
    """
    if bewertete_meldungen({"regions": regional}) > 0:
        return regional, body, competitor_profiles, None
    vorheriger = letzte_gueltige_redaktion(reports_dir, heutiges_datum)
    if vorheriger is None:
        return regional, body, competitor_profiles, None
    stand = vorheriger.get("date", "")
    log.warning(
        "Redaktion ausgefallen (0 bewertete Meldungen am %s) - Titelseite "
        "zeigt weiter den Stand vom %s", heutiges_datum, stand)
    return (
        dict(vorheriger.get("regions") or {}),
        vorheriger.get("briefing_md") or "",
        list(vorheriger.get("competitors") or []),
        {"stand": stand, "grund": grund},
    )
