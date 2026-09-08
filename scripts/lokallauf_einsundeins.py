"""Der 1&1-Lokallauf (B4: Bündelerhebung auf den Geräteseiten).

WARUM ES DIESES SKRIPT GIBT
---------------------------
`scripts/lokallauf_telekom.py` läuft, weil telekom.de aus dem
GitHub-Actions-IP-Bereich mit HTTP 202 antwortet (T1/T2, CLAUDE.md § 6).
1&1 hat dieses Problem NICHT - der Nachtlauf erreicht ihn, und die 35
Bestandslistungen sind in Actions-Läufen entstanden. Dieses Skript
existiert aus dem anderen Grund des B-2/B-3-Musters: Die Bündelsätze
sollen noch HEUTE erhoben, committet und auf dem Radar sichtbar sein,
nicht erst mit dem nächsten Nachtlauf - und der Lauf soll einen
Laufzeitbeleg haben, der jeden Abruf mit dem tatsächlich gesendeten
Absender nachweist (BRIEF_B4, Abnahmekriterium 2). Derselbe
Protokollhaken wie bei T2/B2/B3 (`resp.request.headers`,
`transport=http-get`, `browser=False`), eigene Datei
`beleg-einsundeins-geraete-<datum>.json`.

WAS ES TUT
----------
`geraete_pipeline.run_geraete_stage()` NUR für den 1&1-Anbieter - die
Kategorieseite /smartphones samt der 42 Produktseiten (Ernte-Weg) und,
auf JEDER Produktseite in derselben Antwort, die Bündellesart
(`hwdVariantsPrices`, siehe `collect/geraete/einsundeins.py`). Kein
zweiter Abruf je Seite, keine eigenen Bündel-Einstiege.

Der Absender kommt aus dem Per-Anbieter-Override in
`config/geraete_quellen.yaml` (B2-Muster, siehe dortige Begründung):
`TelcoRadar/1.0`. Seit B2 trägt auch der robots.txt-Abruf den Absender des
Anbieters (provider-bezogene Wächter-Sicht in `sammle_anbieter`), und
genau das prüft der Beleg mit - ein Request mit der globalen
Chrome-Kennung aus `settings.yaml` würde als `alle_ehrlich: false`
gemeldet, nicht verschwiegen.

Es schreibt in dieselben Bestandsdateien wie der normale Lauf
(`geraete_db.json`, `geraete_preise.jsonl`, `geraete_tco.json`); ein
späterer regulärer Lauf ergänzt sie, er überschreibt sie nicht.

WAS ES NICHT TUT
-----------------
Es rendert die Seite nicht und committet nichts. Nach diesem Lauf gehört
(derselbe Aufruf wie beim Telekom- und congstar-Lauf):

    PYTHONPATH=src python3 -c "
from pathlib import Path
from telco_radar.config import load_config
from telco_radar.report.html import render_site
cfg = load_config(Path('.'))
render_site(Path('site'), Path('data/reports'), cfg)
"

AUFRUF
------
    PYTHONPATH=src python3 scripts/lokallauf_einsundeins.py [--root .] [--frist 600]

`--frist` ist das Zeitbudget der Geräte-Stufe in Sekunden. 1&1 crawlt
seine Kategorieseite plus bis zu 45 Produktseiten mit einem Abstand von
2 Sekunden aus der eigenen Konfiguration; 600 Sekunden reichen mit Reserve.
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


def _ist_ehrliche_kennung(user_agent: str | None) -> bool:
    """Dieselbe Prüfung wie beim Telekom- und congstar-Lauf: der
    Versions-/Kontaktzusatz ist erlaubt, eine Browser-Kennung nicht."""
    return bool(user_agent) and user_agent.startswith("TelcoRadar/1.0")


def _hole_mit_beleg(beleg: list):
    """Umhüllt `collect.http.fetch` - derselbe Haken wie T2/B2/B3 (siehe
    deren Docstrings): URL/Host, Status, der tatsächlich GESENDETE
    User-Agent aus `resp.request.headers` und explizit
    `transport="http-get", browser=False`. Keine Antwortkörper, keine
    Cookies, keine Zugangsdaten."""
    from telco_radar.collect.http import fetch as _echter_fetch

    def _protokolliert(url: str, http_cfg: dict, *args, **kwargs):
        eintrag = {
            "url": url,
            "host": urlsplit(url).netloc.lower(),
            "transport": "http-get",
            "browser": False,
        }
        try:
            antwort = _echter_fetch(url, http_cfg, *args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - protokollieren, dann weiterwerfen
            resp = getattr(exc, "response", None)
            eintrag["status"] = getattr(resp, "status_code", None)
            eintrag["user_agent"] = (
                resp.request.headers.get("User-Agent") if resp is not None else None)
            eintrag["fehler"] = type(exc).__name__
            beleg.append(eintrag)
            raise
        eintrag["status"] = antwort.status_code
        eintrag["user_agent"] = antwort.request.headers.get("User-Agent")
        beleg.append(eintrag)
        return antwort

    return _protokolliert


def _nur_einsundeins(original_lade_quellen):
    def _gefiltert(root):
        quellen = original_lade_quellen(root)
        quellen.anbieter = [a for a in quellen.anbieter if a.name == "1&1"]
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
    log = logging.getLogger("lokallauf_einsundeins")

    root = Path(args.root)
    from telco_radar.config import load_config
    from telco_radar import geraete_config, geraete_pipeline
    from telco_radar.collect import http as _http_mod

    cfg = load_config(root)
    http_cfg = cfg.settings.get("http", {})
    heute = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    beleg: list[dict] = []

    # Der Haken wird VOR dem Patchen gebaut: seine Closure hält dann den
    # ECHTEN fetch fest, und das Patchen des Modul-Attributs kann ihn nicht
    # auf sich selbst zeigen lassen (dieselbe Zeile wie bei B2/B3).
    _patch_fetch = _hole_mit_beleg(beleg)
    _echter_fetch = _http_mod.fetch
    _http_mod.fetch = _patch_fetch
    try:
        geraete_pipeline.lade_quellen = _nur_einsundeins(geraete_config.lade_quellen)
        bilanz = geraete_pipeline.run_geraete_stage(
            root, http_cfg, heute, frist_sekunden=args.frist)
    finally:
        _http_mod.fetch = _echter_fetch
    log.info("Bilanz: %s", {k: v for k, v in bilanz.items()
                            if k not in ("unbekannte_titel",
                                         "unbekannte_farben")})

    unehrlich = [e for e in beleg
                 if not _ist_ehrliche_kennung(e.get("user_agent"))]
    beleg_datei = root / "outputs" / f"beleg-einsundeins-geraete-{heute}.json"
    beleg_datei.parent.mkdir(parents=True, exist_ok=True)
    beleg_datei.write_text(json.dumps({
        "datum": heute,
        "anzahl_requests": len(beleg),
        "alle_ehrlich": not unehrlich,
        "requests": beleg,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log.info("Laufzeitbeleg geschrieben: %s (%d Requests, alle_ehrlich=%s)",
             beleg_datei, len(beleg), not unehrlich)
    if unehrlich:
        log.error("BEFUND: %d von %d 1&1-Requests wurden NICHT mit "
                  "TelcoRadar/1.0 gesendet. Details in %s. Das ist ein "
                  "Abnahme-Befund, kein Erfolg.",
                  len(unehrlich), len(beleg), beleg_datei)
    else:
        log.info("Alle %d 1&1-Requests bestätigt mit ehrlichem "
                 "TelcoRadar/1.0-Absender, reines HTTP-GET (kein Browser).",
                 len(beleg))

    log.info("Fertig. Jetzt rendern (report.html.render_site) und committen -"
             " dieses Skript tut beides bewusst nicht.")


if __name__ == "__main__":       # pragma: no cover
    main()
