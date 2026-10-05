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

    0  gelaufen - keine Alarme, Mail zugestellt, ODER der Mailkanal ist
       nicht eingerichtet (EXIT_OK). Der letzte Fall ist eine WARNUNG
       (GitHub-Annotation plus Protokollzeile), kein Fehler: solange die
       SMTP-Secrets in diesem Repo fehlen, waere jeder Lauf sonst rot -
       ein Signal, das immer an ist, unterscheidet einen echten
       Zustellfehler nicht mehr von einem nicht eingerichteten Kanal
       (dieselbe Fehlerklasse wie "50 Laeufe gruen ohne Daten", nur
       umgekehrt). Der Alarm selbst steht trotzdem im Protokoll und auf
       der Quellenseite - nichts wird verschwiegen.
    1  der Bestand kennt keinen Messtag (EXIT_KEIN_MESSTAG)
    2  der Kanal IST eingerichtet, die Zustellung ist trotzdem gescheitert
       (EXIT_NICHT_ZUGESTELLT) - z. B. ein SMTP-Fehler.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telco_radar.analyze.geraete_store import GeraeteDB  # noqa: E402
from telco_radar.geraete_config import lade_quellen  # noqa: E402
from telco_radar.geraete_pipeline import (  # noqa: E402
    melde_ausfall,
    sende_alarm_mail,
)
from telco_radar.versand import VersandFehler, VersandNichtEingerichtet  # noqa: E402

log = logging.getLogger("geraete_abdeckung_mail")

EXIT_OK = 0
EXIT_KEIN_MESSTAG = 1
EXIT_NICHT_ZUGESTELLT = 2

_GITHUB_WARNUNG_PRAEFIX = "::warning::"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Abdeckungsalarme per Mail")
    p.add_argument("--root", default=".")
    p.add_argument(
        "--trocken",
        action="store_true",
        help="baut die Mail, verschickt sie aber nicht",
    )
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    root = Path(args.root)
    db = GeraeteDB(root / "data" / "state" / "geraete_db.json")
    quellen = lade_quellen(root)
    tag = db.letzter_messtag()
    if not tag:
        log.error(
            "Geraeteradar-Abdeckung: der Bestand unter %s kennt "
            "keinen Messtag - der Lauf hat nichts geschrieben oder "
            "der Pfad stimmt nicht; nichts gemeldet, nichts "
            "bestaetigt",
            db.path,
        )
        return EXIT_KEIN_MESSTAG
    alarme = db.ausfall_alarme(nur={a.name for a in quellen.anbieter}, heute=tag)
    melde_ausfall(alarme)
    try:
        log.info("%s", sende_alarm_mail(alarme, tag, trocken=args.trocken))
    except VersandNichtEingerichtet as exc:
        meldung = (
            f"Geraeteradar-Abdeckung: {len(alarme)} Alarme NICHT "
            f"zugestellt ({exc}) - der Mailkanal ist in diesem "
            "Repo nicht eingerichtet, kein Zustellfehler"
        )
        print(f"{_GITHUB_WARNUNG_PRAEFIX} {meldung}")
        log.warning(meldung)
        return EXIT_OK
    except VersandFehler as exc:
        log.error(
            "Geraeteradar-Abdeckung: %d Alarme NICHT zugestellt (%s)", len(alarme), exc
        )
        return EXIT_NICHT_ZUGESTELLT
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
