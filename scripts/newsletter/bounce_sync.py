#!/usr/bin/env python3
"""Bounces und Beschwerden aus der Brevo-Events-API in den Store schreiben.

Laeuft TAEGLICH per Cron im privaten Repo. Nicht als Teil des Versandlaufs:
Ereignisse brauchen Zeit, und die Frage "ist diese Adresse noch erreichbar"
ist nicht an einen Versandtag gebunden.

**Kein IMAP, kein Postfach.** Die API ist die Quelle - das ist einer der
Gruende, aus denen der Versand ueber HTTP und nicht ueber SMTP laeuft.

Warum das ueberhaupt sein muss: Transaktionsanbieter reagieren auf schlechte
Bounce- und Beschwerdequoten empfindlich und **deaktivieren Free-Konten
schnell und ohne Vorwarnung**. Der Vorteil gegenueber einem privaten
Postfach als Absender ist, dass es dann nur den Newsletter trifft und nicht
die eigene Post - aber es trifft ihn eben.

Zugeordnet wird ueber die **Message-ID** aus `send_log.jsonl`, nicht ueber
die Adresse: die steht in den Ereignissen zwar drin, muesste dann aber durch
dieses Skript und ins Log - und im Log darf keine stehen.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WURZEL / "src"))

from telco_radar.newsletter import store as st                   # noqa: E402
from telco_radar.newsletter import versand as v                  # noqa: E402
from telco_radar.newsletter.config import lade_katalog           # noqa: E402
from telco_radar.newsletter.transport import hole_ereignisse     # noqa: E402


def _zahl(name: str, wert) -> None:
    print(f"{name}: {wert}", flush=True)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--store", default="store/subscribers.jsonl")
    p.add_argument("--send-log", default="store/send_log.jsonl")
    p.add_argument("--stand", default="store/bounce_stand.json",
                   help="zuletzt verarbeiteter Zeitpunkt")
    p.add_argument("--trocken", action="store_true")
    args = p.parse_args(argv)

    stand_pfad = Path(args.stand)
    stand = {}
    if stand_pfad.exists():
        try:
            stand = json.loads(stand_pfad.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            stand = {}
    seit = str(stand.get("bis") or "")[:10]

    ereignisse = hole_ereignisse(os.environ.get("BREVO_API_KEY", ""), seit=seit)
    _zahl("Ereignisse", len(ereignisse))
    if not ereignisse:
        return 0

    # message_id -> abo_id, aus dem Sendeprotokoll.
    zuordnung = {str(e.get("message_id")): str(e.get("sub"))
                 for e in st.lies_jsonl(Path(args.send_log))
                 if e.get("message_id") and e.get("sub")}

    katalog = lade_katalog(WURZEL)
    store = st.AboStore(Path(args.store), katalog)
    bounce_stand = {a.id: {"hard": a.bounce_hard, "soft": a.bounce_soft}
                    for a in store.alle()}

    ergebnis = v.werte_ereignisse_aus(ereignisse, zuordnung, bounce_stand)
    _zahl("Nicht zuzuordnen", ergebnis.unbekannt)
    _zahl("Weiche Rueckläufer", len(ergebnis.weich))
    _zahl("Abzuschalten", len(ergebnis.abgeschaltet))

    if args.trocken:
        _zahl("Trockenlauf", "nichts geschrieben")
        return 0

    for abo_id in ergebnis.weich:
        abo = store.finde(abo_id)
        if abo and abo.state == "active":
            abo.bounce_soft += 1
            abo.bounce_last = ergebnis.letzter_zeitpunkt
            store.setze(abo)
    for abo_id in ergebnis.abgeschaltet:
        abo = store.finde(abo_id)
        if abo is None or abo.state != "active":
            continue
        abo.bounce_hard += 1
        abo.bounce_last = ergebnis.letzter_zeitpunkt
        abo.state = "bounced"
        # Die Adresse faellt hier NICHT weg. Ein Hard Bounce ist kein
        # Widerruf - der Betroffene hat nichts erklaert, sein Postfach war
        # nur nicht erreichbar. Wer sie loescht, kann eine
        # Fehlklassifizierung nie mehr zuruecknehmen.
        store.setze(abo)
    store.speichern()

    # Der zuletzt verarbeitete Zeitpunkt - sonst laufen Ereignisse doppelt,
    # und ein zweimal gezaehlter Soft Bounce schaltet eine lebende Adresse ab.
    if ergebnis.letzter_zeitpunkt:
        stand_pfad.parent.mkdir(parents=True, exist_ok=True)
        stand_pfad.write_text(json.dumps({"bis": ergebnis.letzter_zeitpunkt}),
                              encoding="utf-8")
    _zahl("Abos aktiv", len(store.aktive()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
