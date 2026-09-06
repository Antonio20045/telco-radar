"""Der taegliche Telekom-Lokallauf (T1: Tarife) - mit Laufzeitbeleg.

WARUM ES DIESES SKRIPT GIBT
---------------------------
`config/tarif_quellen.yaml` traegt seit BRIEF_TELEKOM_TAEGLICH_R3_E4 einen
Per-Anbieter-Override: NUR Telekom bekommt den ehrlichen
`TelcoRadar/1.0`-Absender, `config/settings.yaml -> http.user_agent`
(die globale Chrome-Kennung fuer alle anderen 195 Quellen) bleibt
unangetastet. Dieses Skript ist der taegliche Telekom-Tarif-Lauf, auf genau
diesen einen Anbieter eingeschraenkt - kein kompletter
`tarif_crawler.sammle()`-Durchlauf ueber o2 und jede andere konfigurierte
Quelle, die die Automatik ohnehin erreicht.

Von den zwei in `CLAUDE.md` beschriebenen Telekom-Signalebenen ist auf dem
Hauptzweig NUR die Tarif-Ebene aktiv: der Geraeteradar fuehrt Telekom in
`config/geraete_quellen.yaml` mit `aktiv: false` (AWS-WAF, kein Adapter
liefert einen Preis ohne Vertrag - siehe der `grund:`-Eintrag dort). Dieses
Skript ruft deshalb ausschliesslich `tarif_crawler.sammle()` auf.

WAS ES TUT
----------
`tarif_crawler.sammle()` NUR fuer die Telekom-Tarifquelle (das
Pflichtdokument-Verzeichnis `produktinformationsblatt`), mit einer
Huellfunktion um `collect.http.fetch`, die JEDEN echten Abruf protokolliert:
URL, Host, HTTP-Status, der tatsaechlich GESENDETE `User-Agent` (aus
`resp.request.headers` - dem Objekt, das httpx nach dem echten Request
zurueckgibt, nicht die Konfiguration, die ihn vorschreiben soll), sowie
explizit `transport="http-get", browser=False` (reines `httpx.get`, kein
Playwright/Selenium/Headless-Browser). Keine Antwortkoerper, keine Cookies,
keine Zugangsdaten - nur die Kopfzeile, die den Absender verraet.

Der Lauf schreibt den Beleg nach
`outputs/beleg-telekom-lokallauf-<datum>.json` (versioniert im Repo, nicht
unter `data/state/` - das wird nie committet) und prueft am Ende SELBST, ob
ALLE Eintraege mit der ehrlichen Kennung gesendet wurden
(`_ist_ehrliche_kennung`: beginnt der gesendete `User-Agent` mit
`TelcoRadar/1.0`?). Es gibt keinen Codepfad, der eine unehrliche Kennung
stillschweigend als Erfolg meldet - ein Befund wird als `ERROR` protokolliert,
nicht verschwiegen.

`fetch()` selbst bleibt unveraendert; die Instrumentierung ist ausschliesslich
in diesem Skript aktiv und betrifft keinen anderen Aufrufer im Projekt.

Es schreibt in dieselbe Bestandsdatei wie der normale Lauf
(`data/state/tarife.jsonl`) - ein spaeterer regulaerer Lauf ergaenzt sie, er
ueberschreibt sie nicht.

WAS ES NICHT TUT
-----------------
Es rendert die Seite nicht und committet nichts. Nach diesem Lauf gehoert:

    PYTHONPATH=src python3 -c "
from pathlib import Path
from telco_radar.config import load_config
from telco_radar.report.html import render_site
cfg = load_config(Path('.'))
render_site(Path('site'), Path('data/reports'), cfg)
"

und danach der uebliche Commit.

AUFRUF
------
    PYTHONPATH=src python3 scripts/lokallauf_telekom.py [--root .]
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


def _ist_ehrliche_kennung(user_agent: str | None) -> bool:
    """Dieselbe Pruefung, die den Absender auf `TelcoRadar/1.0` festnagelt -
    der Versions-/Kontaktzusatz ist erlaubt, ein Browser-UA nicht.
    """
    return bool(user_agent) and user_agent.startswith("TelcoRadar/1.0")


def _hole_mit_beleg(beleg: list):
    """Umhuellt `collect.http.fetch` und haengt VOR jedem echten Abruf einen
    Datensatz an `beleg` an: URL/Host, HTTP-Status, der tatsaechlich
    GESENDETE `User-Agent` (aus `resp.request.headers`, nicht die
    Konfiguration - die ist die Vorschrift, nicht die Auskunft) und explizit
    `transport="http-get", browser=False` (echtes `httpx.get`, kein
    Playwright/Selenium). Keine Antwortkoerper, Cookies oder Zugangsdaten -
    nur die Kopfzeile, die den Absender verraet.

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


def _nur_telekom(original_lade_quellen):
    def _gefiltert(root):
        quellen = original_lade_quellen(root)
        return [q for q in quellen if q.anbieter == "Telekom"]
    return _gefiltert


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default=".")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("lokallauf_telekom")

    root = Path(args.root)
    from telco_radar.config import load_config
    from telco_radar.collect import tarif_crawler

    cfg = load_config(root)
    http_cfg = cfg.settings.get("http", {})
    heute = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    beleg: list[dict] = []

    log.info("=== T1: Telekom-Tarife (Pflichtdokument-Verzeichnis) ===")
    tarif_crawler.lade_quellen = _nur_telekom(tarif_crawler.lade_quellen)
    items, bilanz = tarif_crawler.sammle(
        root, http_cfg, hole=_hole_mit_beleg(beleg))
    log.info("T1-Bilanz: %s", bilanz)
    log.info("Meldungen: %d", len(items))

    # --- Laufzeitbeleg --------------------------------------------------- #
    # Kriterium 2/3 des Auftrags: nicht Code-Plausibilitaet, sondern die
    # tatsaechlich beim echten Abruf gesendete Kennung, gemessen an
    # `resp.request.headers`. Ehrlich heisst hier: beginnt mit
    # "TelcoRadar/1.0" - alles andere ist eine Browser- oder sonstige
    # Fremdkennung und wird als Befund ausgewiesen, nicht verschwiegen.
    unehrlich = [e for e in beleg
                 if not _ist_ehrliche_kennung(e.get("user_agent"))]
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
