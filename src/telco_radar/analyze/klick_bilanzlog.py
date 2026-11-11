"""Protokollzeilen der Klick-Zusammenführung (aus ``klick_zusammenfuehrung``)."""

from __future__ import annotations

import logging


def protokolliere(bilanz: dict, log: logging.Logger) -> None:
    """Die Bilanz des Zusammenführens als Warnungen und eine Info-Zeile."""
    for datei in bilanz["dateien"]:
        if not datei["verwendet"]:
            log.warning(
                "Klick-Ergebnis %s ersetzt nichts: %s",
                datei["anbieter"],
                datei["warum_nicht"],
            )
        if datei["ueberfaellig"]:
            log.warning(
                "Klick-Ergebnis %s: %d Seiten überfällig",
                datei["anbieter"],
                len(datei["ueberfaellig"]),
            )
    if bilanz["geplant"] is None:
        log.warning("Klick-Tagesplan fehlt: geplante Anbieter unbekannt")
    for name in bilanz["fehlt"]:
        log.warning("Klick-Ergebnis %s fehlt: keine Datei im Ordner", name)
    for schluessel in bilanz["mehrdeutig"]:
        log.warning("Klick-Sätze mehrdeutig, keiner verwendet: %s", schluessel)
    unvollstaendig = bilanz["unvollstaendig"]
    if unvollstaendig["nicht_ersetzt"]:
        log.warning(
            "Klick-Sätze unvollständig, %d Adaptersätze nicht ersetzt: %s",
            unvollstaendig["nicht_ersetzt"],
            ", ".join(f"{f} {n}" for f, n in unvollstaendig["felder"].items()),
        )
    probe = bilanz["gegenprobe"]
    log.info(
        "Klick-Bündel: %d Sätze, %d Adaptersätze ersetzt (%d gleich, %d abweichend,"
        " %d ohne Vergleich), %d ohne Gegenstück",
        bilanz["klick_rohsaetze"],
        bilanz["ersetzt"],
        probe["gleich"],
        probe["abweichend"],
        probe["ohne_vergleich"],
        bilanz["ohne_gegenstueck"],
    )
    for beispiel in probe["beispiele"]:
        log.warning("Klick-Gegenprobe weicht ab: %s", beispiel)
