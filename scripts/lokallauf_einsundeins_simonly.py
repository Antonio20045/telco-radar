"""Der 1&1-SIM-only-Lokallauf (S-5: Referenzen von der SIM-only-Seite).

WARUM ES DIESES SKRIPT GIBT
---------------------------
Dasselbe Muster wie `scripts/lokallauf_einsundeins.py` (B4): Die
1&1-SIM-only-Referenzen sollen noch HEUTE erhoben, committet und in der
Datenlage nachweisbar sein, nicht erst mit dem nächsten Nachtlauf - und
der Lauf soll einen Laufzeitbeleg haben, der jeden Abruf mit dem
tatsächlich gesendeten Absender nachweist (BRIEF S-5,
Abnahmekriterium 1). Derselbe Protokollhaken wie bei T2/B2/B3/B4
(`resp.request.headers`, `transport=http-get`, `browser=False`), eigene
Datei `beleg-einsundeins-simonly-<datum>.json`.

WAS ES TUT
----------
`collect.tarif_einsundeins_simonly.sammle()` mit dem echten Netz:
robots-Wächter über beide Domains, dann die Seite
`https://www.1und1.de/handytarife-ohne-handy` und je Tarif das im
`data-iframe` verlinkte Tarifdetails-Dokument (daher kommt der
Anschlusspreis). Absender ist der Absender des Briefs:
`TelcoRadar/1.0 (+https://telco-radar.onrender.com/ueber)`.

Die sieben Referenzen werden über `TcoDB.setze_referenzen` in
`data/state/geraete_tco.json` AUFGEFRISCHT - dieselben IDs wie die
bisherigen 1&1-Sätze (sie entstehen aus demselben `tarif_id`-Stamm),
also kein neuer Bestand, sondern die bessere Messung desselben
Massstabs. Buendel und Fremd-Referenzen bleiben unberuehrt; der
naechste Nachtlauf wiederholt die Messung ueber die Pipeline-Anbindung
(geraete_pipeline, S-5).

WAS ES NICHT TUT
-----------------
Es rendert die Seite nicht und committet nichts. Nach diesem Lauf
gehoert (derselbe Aufruf wie beim Telekom- und congstar-Lauf):

    PYTHONPATH=src python3 -c "
from pathlib import Path
from telco_radar.config import load_config
from telco_radar.report.html import render_site
cfg = load_config(Path('.'))
render_site(Path('site'), Path('data/reports'), cfg)
"

AUFRUF
------
    PYTHONPATH=src python3 scripts/lokallauf_einsundeins_simonly.py [--root .]
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
    """Umhüllt `collect.http.fetch` - derselbe Haken wie T2/B2/B3/B4 (siehe
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


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default=".")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("lokallauf_einsundeins_simonly")

    root = Path(args.root)
    from telco_radar.config import load_config
    from telco_radar import geraete_pipeline
    from telco_radar.analyze.tco_store import TcoDB
    from telco_radar.collect import http as _http_mod
    from telco_radar.collect.tarif_einsundeins_simonly import (
        sammle as sammle_simonly)

    cfg = load_config(root)
    http_cfg = cfg.settings.get("http", {})
    heute = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    beleg: list[dict] = []

    # Der Haken wird VOR dem Patchen gebaut: seine Closure hält dann den
    # ECHTEN fetch fest (dieselbe Zeile wie bei B2/B3/B4). Und er sitzt auf
    # dem Modul-Attribut, BEVOR `_hole_fabrik` seinen `from .collect.http
    # import fetch` ausfuehrt - sonst ginge der Abruf am Beleg vorbei.
    #
    # DIE VIERTE KOPIE DIESES HAKENS (Review B6): lokallauf_telekom,
    # lokallauf_congstar und lokallauf_einsundeins tragen dieselbe. Sie ist
    # bewusst kopiert und nicht ausgelagert - die drei Skripte teilen sich
    # keine Importbasis, und ein gemeinsames Modul waere ein Umbau der
    # Laufzeuge ueber drei fertige Auftraege hinweg. Wer den Haken aendert,
    # aendert ihn an allen vier Stellen; diese Zeile ist der Hinweis dafuer.
    _patch_fetch = _hole_mit_beleg(beleg)
    _echter_fetch = _http_mod.fetch
    _http_mod.fetch = _patch_fetch
    referenzen = []
    protokoll = {"seite": "(nicht gelaufen)"}
    try:
        hole = geraete_pipeline._hole_fabrik(http_cfg)
        referenzen, protokoll = sammle_simonly(hole, heute)
        if referenzen:
            tco = TcoDB(root / "data" / "state" / "geraete_tco.json")
            neu = tco.setze_referenzen(referenzen, heute)
            geschrieben = tco.save(heute)
            log.info("Geräte-TCO: %d 1&1-SIM-only-Referenzen aufgefrischt "
                     "(%d neu), Datei geschrieben: %s",
                     len(referenzen), neu, geschrieben)
        else:
            log.warning("Keine Referenzen erhoben - geraete_tco.json bleibt "
                        "unangetastet (%s)", protokoll)
    finally:
        _http_mod.fetch = _echter_fetch
        # Der Beleg wird AUCH bei einem Absturz geschrieben: die robots-
        # Abrufe stehen dann bereits in der Liste, und ein gescheiterter
        # Lauf ohne Laufzeitbeleg ist nicht mehr nachvollziehbar.
        unehrlich = [e for e in beleg
                     if not _ist_ehrliche_kennung(e.get("user_agent"))]
        beleg_datei = root / "outputs" / \
            f"beleg-einsundeins-simonly-{heute}.json"
        beleg_datei.parent.mkdir(parents=True, exist_ok=True)
        beleg_datei.write_text(json.dumps({
            "datum": heute,
            "anzahl_requests": len(beleg),
            "alle_ehrlich": not unehrlich,
            "requests": beleg,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        log.info("Laufzeitbeleg geschrieben: %s (%d Requests, "
                 "alle_ehrlich=%s)", beleg_datei, len(beleg), not unehrlich)
        log.info("Protokoll: %s", protokoll)
        if unehrlich:
            log.error("BEFUND: %d von %d 1&1-Requests wurden NICHT mit "
                      "TelcoRadar/1.0 gesendet. Details in %s. Das ist ein "
                      "Abnahme-Befund, kein Erfolg.",
                      len(unehrlich), len(beleg), beleg_datei)
        elif beleg:
            log.info("Alle %d 1&1-Requests bestätigt mit ehrlichem "
                     "TelcoRadar/1.0-Absender, reines HTTP-GET "
                     "(kein Browser).", len(beleg))

    log.info("Fertig. Jetzt rendern (report.html.render_site) und "
             "committen - dieses Skript tut beides bewusst nicht.")


if __name__ == "__main__":       # pragma: no cover
    main()
