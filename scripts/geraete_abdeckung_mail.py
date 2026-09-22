#!/usr/bin/env python3
"""Der Versandschritt des Abdeckungswaechters (P1/C2).

Ein eigener Schritt und kein Anhaengsel des Laufs, aus zwei Gruenden:

  * Die SMTP-Zugangsdaten liegen als GitHub-Secrets vor und werden damit
    NUR diesem Schritt in die Umgebung gegeben. Die Sammelstufe, die gegen
    fremde Hosts spricht, sieht sie nie.
  * Ein Mailserver, der nicht antwortet, darf keinen Messtag kosten. Der
    Schritt steht deshalb hinter Bestand und Seite.

Er rechnet nichts nach: die Alarme kommen aus `GeraeteDB.ausfall_alarme()`,
derselben Funktion, die Lauf und Quellenseite lesen. Ohne Alarm geht keine
Mail hinaus - eine taegliche "alles in Ordnung"-Mail ist nach zwei Wochen
ein Postfachfilter.

    python scripts/geraete_abdeckung_mail.py --root .
    python scripts/geraete_abdeckung_mail.py --root . --trocken

RUECKGABECODES (der Workflow-Schritt haengt daran):

    0  gelaufen - entweder keine Alarme oder Mail zugestellt
    1  der Bestand kennt keinen Messtag (EXIT_KEIN_MESSTAG)
    2  Alarme da, Zustellung gescheitert (EXIT_NICHT_ZUGESTELLT)
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telco_radar.analyze.geraete_store import GeraeteDB          # noqa: E402
from telco_radar.geraete_config import lade_quellen              # noqa: E402
from telco_radar.geraete_pipeline import (                       # noqa: E402
    melde_ausfall,
    sende_alarm_mail,
)
from telco_radar.versand import VersandFehler                    # noqa: E402

log = logging.getLogger("geraete_abdeckung_mail")

# Die Rueckgabecodes dieses Schritts. Sie sind benannt, weil der Workflow
# an ihnen haengt und ein Test sie festnagelt - eine nackte 2 mitten im
# Code sagt nicht, wofuer sie steht.
EXIT_KEIN_MESSTAG = 1        # der Bestand kennt keinen einzigen Messtag
EXIT_NICHT_ZUGESTELLT = 2    # Alarme da, Zustellung gescheitert


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Abdeckungsalarme per Mail")
    p.add_argument("--root", default=".")
    p.add_argument("--trocken", action="store_true",
                   help="baut die Mail, verschickt sie aber nicht")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    root = Path(args.root)
    db = GeraeteDB(root / "data" / "state" / "geraete_db.json")
    quellen = lade_quellen(root)
    tag = db.letzter_messtag()
    if not tag:
        # KEIN MESSTAG IST EIN AUSFALL, KEINE ENTWARNUNG. Dieser Schritt
        # laeuft HINTER dem Lauf, der den Bestand schreibt; kennt der
        # Bestand danach keinen einzigen Messtag, dann hat entweder der
        # Lauf nichts geschrieben oder dieser Schritt liest den falschen
        # Pfad. Beides ist ein Befund, und beides bleibt unsichtbar, wenn
        # der Schritt gruen ausgeht - genau die Fehlerklasse, gegen die
        # dieser Waechter gebaut ist ("50 Laeufe gruen, sechs Tage ohne
        # Telekom-Zeile"). Der Schritt faellt deshalb rot aus.
        log.error("Geraeteradar-Abdeckung: der Bestand unter %s kennt "
                  "keinen Messtag - der Lauf hat nichts geschrieben oder "
                  "der Pfad stimmt nicht; nichts gemeldet, nichts "
                  "bestaetigt", db.path)
        return EXIT_KEIN_MESSTAG
    # `nur`: ein Anbieter, der aus der Konfiguration gefallen ist, wird
    # nicht mehr beobachtet und darf keine Ewigkeitsmail ausloesen.
    alarme = db.ausfall_alarme(nur={a.name for a in quellen.anbieter},
                               heute=tag)
    melde_ausfall(alarme)
    try:
        log.info("%s", sende_alarm_mail(alarme, tag, trocken=args.trocken))
    except VersandFehler as exc:
        # Weitergeben, nicht schlucken: ein Alarmkanal, der still nicht
        # zustellt, ist genau die Fehlerklasse, gegen die dieser Waechter
        # gebaut ist. Der Workflow-Schritt faellt damit rot aus.
        log.error("Geraeteradar-Abdeckung: %d Alarme NICHT zugestellt (%s)",
                  len(alarme), exc)
        return EXIT_NICHT_ZUGESTELLT
    return 0


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(main())
