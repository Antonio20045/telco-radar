"""Der Saturn-Lokallauf: den Geraeteradar NUR fuer Saturn abfragen.

WARUM ES DIESES SKRIPT GIBT
----------------------------
Nach demselben Muster wie `scripts/lokallauf_telekom.py`: der PM soll den
Saturn-Adapter (`config/geraete_quellen.yaml`, `methode: saturn_brand`)
wiederholen koennen, ohne den Adapter selbst zu verstehen oder aus Versehen
den kompletten `geraete_pipeline`-Lauf ueber alle ~20 konfigurierten
Anbieter anzustossen - das waere ein Vielfaches der Laufzeit und wuerde
Anbieter neu abfragen, die die naechtliche Automatik (`geraete.yml`) ohnehin
erreicht.

Anders als beim Telekom-Lokallauf gibt es hier keinen T1-Teil (Tarife):
Saturn ist ein Haendler (`typ: handel`), kein Netzbetreiber mit eigenem
Tarifbestand - nur die Geraetestufe ist einschlaegig.

WAS ES TUT
----------
`geraete_pipeline.run_geraete_stage()` NUR fuer den Anbieter "Saturn" - alle
17 konfigurierten Markenseiten (Apple-iPhone-Serien des Katalogs, Stand
05.09.2026). Schreibt in dieselben Bestandsdateien wie der normale Lauf
(`data/state/geraete_db.json`, `geraete_preise.jsonl`) - ein spaeterer
regulaerer Lauf ergaenzt sie, er ueberschreibt sie nicht.

WAS ES NICHT TUT
-----------------
Es rendert die Seite nicht und committet nichts. Nach diesem Lauf gehoert
(auf demselben Rechner, mit `/opt/homebrew/bin/python3` auf Antonios Mac):

    PYTHONPATH=src python3 -c "
from pathlib import Path
from telco_radar.config import load_config
from telco_radar.report.html import render_site
cfg = load_config(Path('.'))
render_site(Path('site'), Path('data/reports'), cfg)
"

und danach der uebliche Commit + Push.

AUFRUF
------
    PYTHONPATH=src python3 scripts/lokallauf_saturn.py [--root .] [--frist 600]

`--frist` ist das Zeitbudget der Geraetestufe in Sekunden. 17 Markenseiten
bei 10s Mindestabstand (Crawl-delay-Vorsicht gegenueber einem
Cloudflare-Host, siehe `config/geraete_quellen.yaml`) sind rund 170s reiner
Wartezeit plus Abrufzeit - 600s Voreinstellung lassen reichlich Luft.
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path


def _nur_saturn(original_lade_quellen):
    def _gefiltert(root):
        quellen = original_lade_quellen(root)
        quellen.anbieter = [a for a in quellen.anbieter if a.name == "Saturn"]
        return quellen
    return _gefiltert


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default=".")
    p.add_argument("--frist", type=float, default=600.0,
                   help="Zeitbudget der Geraetestufe in Sekunden")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("lokallauf_saturn")

    root = Path(args.root)
    from telco_radar.config import load_config
    from telco_radar import geraete_config, geraete_pipeline

    cfg = load_config(root)
    http_cfg = cfg.settings.get("http", {})
    heute = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    log.info("=== Saturn: Geraeteradar ueber alle konfigurierten Markenseiten ===")
    geraete_pipeline.lade_quellen = _nur_saturn(geraete_config.lade_quellen)
    bilanz = geraete_pipeline.run_geraete_stage(
        root, http_cfg, heute, frist_sekunden=args.frist)
    log.info("Saturn-Bilanz: %s", {k: v for k, v in bilanz.items()
                                   if k not in ("unbekannte_titel",
                                                "unbekannte_farben")})

    log.info("Fertig. Jetzt rendern (report.html.render_site) und committen -"
             " dieses Skript tut beides bewusst nicht.")


if __name__ == "__main__":       # pragma: no cover
    main()
