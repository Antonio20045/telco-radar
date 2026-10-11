#!/usr/bin/env python3
"""Einmaliger Umzug: alter age-Store -> Brevo-Liste (Antonio, 11.10.2026).

Laeuft im Workflow `umzug.yml` des privaten Repos telco-radar-mail, das den
Store entschluesselt und dieses Repo mit PYTHONPATH=src auscheckt. Gibt NUR Zahlen aus.

    umzug_brevo.py --store store/subscribers.jsonl --nur-zaehlen
    umzug_brevo.py --store store/subscribers.jsonl

Ohne --nur-zaehlen legt es jedes aktive Abo als Kontakt an und liest die
Liste danach zurueck. Fehlt danach ein Abo oder weicht ein Datensatz ab,
endet es rot: der alte Store bleibt dann die Wahrheit.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path

from telco_radar.newsletter import brevo_kontakte as bk
from telco_radar.newsletter import store as st
from telco_radar.newsletter.config import lade_katalog
from telco_radar.newsletter.subscription import als_dict

WURZEL = Path(__file__).resolve().parents[2]


def _zahl(name: str, wert) -> None:
    print(f"{name}: {wert}", flush=True)


def main(argv=None) -> int:
    teil = argparse.ArgumentParser()
    teil.add_argument("--store", required=True)
    teil.add_argument("--nur-zaehlen", action="store_true")
    args = teil.parse_args(argv)

    katalog = lade_katalog(WURZEL)
    abos = st.AboStore(Path(args.store), katalog).alle()
    for abo in abos:
        if abo.email:
            print(f"::add-mask::{abo.email}", flush=True)
    for zustand, anzahl in sorted(Counter(a.state for a in abos).items()):
        _zahl(f"Abos {zustand}", anzahl)
    aktive = [a for a in abos if a.aktiv]
    _zahl("Abos aktiv mit Adresse", len(aktive))
    laengen = [len(json.dumps(als_dict(a), ensure_ascii=False)) for a in aktive]
    laengste = max(laengen, default=0)
    _zahl("Laengster Datensatz (Zeichen)", laengste)
    if args.nur_zaehlen:
        return 0

    brevo = bk.BrevoKontakte(os.environ.get("BREVO_API_KEY", ""))
    liste = brevo.einrichten()
    for abo in aktive:
        brevo.speichern(abo, liste)
    _zahl("Nach Brevo uebertragen", len(aktive))

    zurueck = {k.abo.id: k.abo for k in brevo.alle(liste, katalog)}
    fehlend = [a for a in aktive if a.id not in zurueck]
    abweichend = [
        a for a in aktive if a.id in zurueck and als_dict(zurueck[a.id]) != als_dict(a)
    ]
    _zahl("In der Brevo-Liste", len(zurueck))
    _zahl("Fehlend", len(fehlend))
    _zahl("Abweichend", len(abweichend))
    if fehlend or abweichend:
        print("::error::Umzug unvollstaendig - alter Store bleibt die Wahrheit.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
