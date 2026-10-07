"""Abdeckungsalarme des Gerätelaufs: Protokollzeile und Mail.

Ausgelagert aus ``geraete_pipeline`` (dort weiter importierbar); Protokoll, Mail und
Quellenseite sagen wortgleich dasselbe (Clean Code 7).
"""

from __future__ import annotations

import logging
from html import escape

from . import versand
from .analyze.geraete_store import tag_de

log = logging.getLogger("telco_radar.geraete_pipeline")


def melde_ausfall(alarme: list) -> None:
    """Je eingebrochenem Anbieter EINE Zeile, mit fester Wortform.

    Der Wortlaut ist Testvertrag (`tests/test_geraete_abdeckung.py`) - die
    Zeile ist der Alarm, und ein Alarm, dessen Wortlaut driftet, ist im
    Actions-Log nicht mehr grepbar. Der Satz selbst kommt aus dem
    Alarmobjekt: Protokoll, Mail und Quellenseite sagen damit wortgleich
    dasselbe (Clean Code 7).
    """
    for alarm in alarme:
        log.warning(
            "Geraeteradar-Abdeckung: %s (Quelle pruefen: geraete-quellen.html)",
            alarm.satz,
        )


def baue_alarm_mail(alarme: list, tag: str) -> tuple:
    """(Betreff, Text, HTML) fuer die Abdeckungsmail. Ohne Netz, ohne
    Zustellung - damit der Inhalt pruefbar ist, ohne einen Mailserver zu
    brauchen.

    Der Inhalt ist EIN Satz je Anbieter, derselbe wie im Protokoll und auf
    der Quellenseite. Keine Zusammenfassung, keine Empfehlung: die Mail
    sagt, was fehlt, und verlinkt die Seite, auf der es nachzusehen ist.
    """
    datum = tag_de(tag)
    seite = f"{versand.SITE_URL}/geraete-quellen.html"
    betreff = (
        f"Geräteradar {datum}: {len(alarme)} Anbieter heute nicht vollständig erfasst"
    )
    zeilen = [a.satz for a in alarme]
    text = "\n".join(
        [f"Stand {datum}", ""]
        + [f"- {z}" for z in zeilen]
        + ["", f"Quellenseite: {seite}"]
    )
    inhalt = (
        f"<html><body><p>Stand {escape(datum)}</p><ul>"
        + "".join(f"<li>{escape(z)}</li>" for z in zeilen)
        + f'</ul><p><a href="{seite}">Quellenseite</a></p></body></html>'
    )
    return betreff, text, inhalt


def sende_alarm_mail(alarme: list, tag: str, *, trocken: bool = False) -> str:
    """Verschickt die Abdeckungsmail und gibt die Bilanzzeile zurueck.

    Ohne Alarme wird NICHTS verschickt - eine taegliche "alles in Ordnung"-
    Mail ist nach zwei Wochen ein Filter im Postfach, und ein
    stummgeschalteter Kanal ist schlimmer als keiner (`versand.py`).

    Ein Zustellfehler wird NICHT geschluckt: `VersandFehler` geht an den
    Aufrufer weiter (der Workflow-Schritt faellt damit rot aus). Ein
    Alarmkanal, der still nicht zustellt, ist genau die Fehlerklasse, gegen
    die dieser Waechter gebaut ist.
    """
    if not alarme:
        return "keine Abdeckungsalarme - keine Mail"
    betreff, text, html = baue_alarm_mail(alarme, tag)
    ergebnis = versand.sende_mail(betreff, text, html, trocken=trocken)
    log.warning(
        "Geraeteradar-Abdeckung: %d Alarme per Mail (%s)", len(alarme), ergebnis
    )
    return ergebnis
