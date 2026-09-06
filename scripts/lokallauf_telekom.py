"""Der woechentliche Telekom-Lokallauf (T1: Tarife, T2: Geraete).

WARUM ES DIESES SKRIPT GIBT
---------------------------
Aus dem IP-Bereich von GitHub Actions antwortet telekom.de httpx mit einer
202-Challenge statt mit der Seite (CLAUDE.md § 6). Von einem gewoehnlichen
Rechner - auch von diesem hier - kommt derselbe Abruf durch (gemessen
04./05.09.2026, siehe QUELLEN_MAP.md und `outputs/phase-t1-2026-09-05.md`).
Entscheidung H1: die Telekom-Tarif- und -Geraetequellen laufen deshalb
woechentlich VON HAND, nicht im automatischen GitHub-Actions-Lauf.

Dieses Skript ist genau dieser Lauf, auf Telekom eingeschraenkt - kein
kompletter `geraete_pipeline`- oder `tarif_crawler`-Durchlauf ueber alle
konfigurierten Anbieter. Ein Lokallauf soll die Telekom-Luecke schliessen,
nicht nebenbei freenet, Vodafone & Co. neu abrufen, die die Automatik ohnehin
erreicht.

WAS ES TUT
----------
1. `tarif_crawler.sammle()` NUR fuer die Telekom-Tarifquellen (T1: das
   Pflichtdokument-Verzeichnis UND die Shop-Tarifkacheln,
   `methode: telekom_kacheln`).
2. `geraete_pipeline.run_geraete_stage()` NUR fuer den Telekom-Anbieter
   (T2: die Geraetekategorie `methode: telekom_kategorie`).

Beide schreiben in dieselben Bestandsdateien wie der normale Lauf
(`data/state/tarife.jsonl`, `geraete_db.json`, `geraete_preise.jsonl`,
`geraete_tco.json`) - ein spaeterer regulaerer Lauf ergaenzt sie, er
ueberschreibt sie nicht.

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
    PYTHONPATH=src python3 scripts/lokallauf_telekom.py [--root .] [--frist 180]

`--frist` ist das Zeitbudget der GERAETE-Stufe in Sekunden (T1 braucht keins -
es sind zwei kurze, direkte Abrufe). 180 Sekunden reichen: die Kategorieseite
ist EIN Abruf (`direkt=True`), kein Linknetz.
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


def _hole_mit_beleg(beleg: list):
    """Umhuellt `collect.http.fetch` und haengt VOR jedem echten Abruf einen
    Datensatz an `beleg` an: URL/Host, HTTP-Status, der tatsaechlich
    GESENDETE `User-Agent` (aus `resp.request.headers`, nicht die
    Konfiguration - der ist die Auskunft, nicht was `http_cfg` vorschreibt)
    und explizit `transport="http-get", browser=False` (echtes `httpx.get`,
    kein Playwright/Selenium). Keine Antwortkoerper, Cookies oder
    Zugangsdaten - nur die Kopfzeile, die den Absender verraet.

    Aktiv NUR fuer die Dauer dieses Skripts: `fetch()` selbst bleibt
    unveraendert, jeder andere Aufrufer im Projekt sieht davon nichts.
    """
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
        except Exception as exc:  # noqa: BLE001 - wir protokollieren, dann werfen wir weiter
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


def _geraete_hole_mit_beleg(http_cfg: dict, beleg: list):
    """Dasselbe Protokoll wie `geraete_pipeline._hole_fabrik`
    (`hole(url) -> (status, text)`, gebraucht fuer Robots-Wächter UND
    Seitenabruf) - nur mit dem protokollierenden `fetch` von oben darunter
    statt dem rohen. Bewusst eine eigene Kopie statt eines Eingriffs in
    `geraete_pipeline.py`: dieser Auftrag ergaenzt Belege, er aendert kein
    Produktionsverhalten.
    """
    import httpx

    hole_roh = _hole_mit_beleg(beleg)

    def hole(url: str, kopfzeilen=None, user_agent=None):
        cfg = http_cfg if not user_agent else {**http_cfg, "user_agent": user_agent}
        try:
            antwort = hole_roh(url, cfg, extra_headers=kopfzeilen or None)
        except httpx.HTTPStatusError as exc:
            return (exc.response.status_code, exc.response.text)
        return (antwort.status_code, antwort.text)

    return hole


def _nur_telekom_tarife(original_lade_quellen):
    def _gefiltert(root):
        quellen = original_lade_quellen(root)
        return [q for q in quellen if q.anbieter == "Telekom"]
    return _gefiltert


def _nur_telekom_geraete(original_lade_quellen):
    def _gefiltert(root):
        quellen = original_lade_quellen(root)
        quellen.anbieter = [a for a in quellen.anbieter if a.name == "Telekom"]
        return quellen
    return _gefiltert


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default=".")
    p.add_argument("--frist", type=float, default=180.0,
                   help="Zeitbudget der Geraetestufe in Sekunden")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("lokallauf_telekom")

    root = Path(args.root)
    from telco_radar.collect.http import _ist_ehrliche_kennung
    from telco_radar.config import load_config
    from telco_radar.collect import tarif_crawler
    from telco_radar import geraete_config, geraete_pipeline

    cfg = load_config(root)
    http_cfg = cfg.settings.get("http", {})
    heute = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    beleg: list[dict] = []

    # --- T1: Tarife -------------------------------------------------------
    log.info("=== T1: Telekom-Tarife (Pflichtdokumente + Shop-Kacheln) ===")
    tarif_crawler.lade_quellen = _nur_telekom_tarife(tarif_crawler.lade_quellen)
    _items, bilanz_tarife = tarif_crawler.sammle(
        root, http_cfg, hole=_hole_mit_beleg(beleg))
    log.info("T1-Bilanz: %s", bilanz_tarife)

    # --- T2: Geraete --------------------------------------------------------
    log.info("=== T2: Telekom-Geraetekategorie ===")
    geraete_pipeline.lade_quellen = _nur_telekom_geraete(
        geraete_config.lade_quellen)
    bilanz_geraete = geraete_pipeline.run_geraete_stage(
        root, http_cfg, heute, frist_sekunden=args.frist,
        hole=_geraete_hole_mit_beleg(http_cfg, beleg))
    log.info("T2-Bilanz: %s", {k: v for k, v in bilanz_geraete.items()
                               if k not in ("unbekannte_titel",
                                            "unbekannte_farben")})

    # --- Laufzeitbeleg -------------------------------------------------------
    # Kriterium 1/2 des Auftrags: nicht Code-Plausibilitaet ("fetch() sollte
    # TelcoRadar/1.0 senden"), sondern die tatsaechlich beim echten Abruf
    # gesendete Kennung, gemessen an `resp.request.headers`. Ehrlich heisst
    # hier: startet mit "TelcoRadar/1.0" (`_ist_ehrliche_kennung`, dieselbe
    # Pruefung wie in `fetch()` selbst) - alles andere ist eine Browser- oder
    # sonstige Fremdkennung und wird als Befund ausgewiesen, nicht verschwiegen.
    unehrlich = [e for e in beleg
                 if not _ist_ehrliche_kennung(e.get("user_agent") or "")]
    beleg_datei = root / "outputs" / f"beleg-telekom-lokallauf-{heute}.json"
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
        log.error("BEFUND: %d von %d Telekom-Requests wurden NICHT mit "
                   "TelcoRadar/1.0 gesendet (Browser-Imitation oder UA-"
                   "Wechsel). Details in %s. Das ist ein Abnahme-Befund, "
                   "kein Erfolg.", len(unehrlich), len(beleg), beleg_datei)
    else:
        log.info("Alle %d Telekom-Requests bestaetigt mit ehrlichem "
                 "TelcoRadar/1.0-Absender, reines HTTP-GET (kein Browser).",
                 len(beleg))

    log.info("Fertig. Jetzt rendern (report.html.render_site) und committen -"
             " dieses Skript tut beides bewusst nicht.")


if __name__ == "__main__":       # pragma: no cover
    main()
