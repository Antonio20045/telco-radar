"""Die Geraetestufe des Wochenlaufs - und ihr eigener naechtlicher Lauf.

Sie haengt wie der Promo-Zweig NACH dem Kernlauf, mit eigenem try/except.
Zwei Dinge macht sie besser als er, beide aus Teil F des Auftrags:

  * **Ein echtes Zeitbudget.** Der Promo-Zweig hat keines; seine einzige
    Grenze ist das 50-Minuten-Job-Timeout, und ein Timeout ist in GitHub ein
    "cancelled", kein "failed". Diese Stufe bekommt eine Frist, bricht bei
    Ablauf sauber ab, speichert das Teilergebnis und vermerkt es.
  * **Sie ist auf der Website sichtbar.** `promo_result` wird zugewiesen und
    nie wieder gelesen - der ganze Promo-Zweig existiert nur im Actions-Log.
    Diese Stufe gibt eine Bilanz zurueck, die in `stats` gehoert.

WARUM ES AUSSERDEM EINEN EIGENEN NAECHTLICHEN LAUF GIBT
------------------------------------------------------
medimax.de und ep.de erlauben Abrufe laut eigener robots.txt nur zwischen
02:00 und 08:00 UTC. Der Wochenlauf startet um 08:30. Im Tageslauf werden sie
deshalb uebersprungen - und, das ist der wichtigere Teil, NICHT gealtert.
`.github/workflows/geraete.yml` holt sie um 03:10 UTC nach.

DIE REGEL, DIE DIESE DATEI TRAEGT
---------------------------------
`mark_stale` laeuft NUR fuer Anbieter, deren Bilanz `vollstaendig` ist. Ein
Teilausfall, ein Fristablauf, eine gesperrte oder ausserhalb ihrer Besuchszeit
liegende Quelle - alles das heisst "nicht gelesen", und was nicht gelesen
wurde, altert nicht.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .analyze.geraete_store import GeraeteDB, Preishistorie
from .collect.geraete import sammle
from .geraete_config import lade_farben, lade_katalog, lade_quellen

log = logging.getLogger(__name__)

# Voreinstellung des Zeitbudgets. Bewusst grosszuegig fuer den naechtlichen
# Lauf und knapp fuer den Tageslauf (der Aufrufer setzt es): bei zehn
# Sekunden Abstand je Abruf sind 20 Produktseiten allein drei Minuten.
FRIST_STANDARD = 900.0


def _hole_fabrik(http_cfg: dict) -> Callable:
    """`(status, text)` statt Response oder Ausnahme.

    Der Waechter muss 404 ("keine robots.txt, also keine Regeln") von 403
    ("nicht anfassen") unterscheiden koennen. `collect.http.fetch` wirft bei
    beidem nicht, aber ein Verbindungsfehler schon - der bleibt eine
    Ausnahme und wird oben als Fehler gewertet, nicht als Freibrief.
    """
    from .collect.http import fetch

    def hole(url: str):
        antwort = fetch(url, http_cfg)
        return (antwort.status_code, antwort.text)

    return hole


def run_geraete_stage(root: Path, http_cfg: dict, heute: str,
                      jetzt: Optional[datetime] = None,
                      frist_sekunden: Optional[float] = FRIST_STANDARD,
                      hole: Optional[Callable] = None) -> dict:
    """Sammeln, aufnehmen, altern, speichern. Gibt die Bilanz zurueck."""
    beginn = time.monotonic()
    jetzt = jetzt or datetime.now(timezone.utc)
    root = Path(root)

    katalog = lade_katalog(root)
    farben = lade_farben(root)
    quellen = lade_quellen(root)
    if not quellen.anbieter or not katalog.geraete:
        return {"status": "keine Konfiguration", "anbieter": [],
                "listungen": 0, "neu": 0, "gealtert": 0}

    hole = hole or _hole_fabrik(http_cfg)
    ergebnis = sammle(quellen, katalog, farben, hole, heute, jetzt,
                      frist_sekunden=frist_sekunden)

    zustand = root / "data" / "state"
    db = GeraeteDB(zustand / "geraete_db.json")
    historie = Preishistorie(zustand / "geraete_preise.jsonl")

    neu_gesamt = gealtert_gesamt = punkte = 0
    bilanzen = []
    for bilanz in ergebnis["anbieter"]:
        anbieter = quellen.nach_name(bilanz.name)
        neu, gesehen = db.upsert(bilanz.listungen, heute)
        neu_gesamt += neu
        for listung in bilanz.listungen:
            if historie.schreibe(listung, heute):
                punkte += 1
        if bilanz.vollstaendig:
            leitseite = (anbieter.crawled_einstiege[0].url
                         if anbieter and anbieter.crawled_einstiege else "")
            gealtert_gesamt += db.mark_stale(
                bilanz.name, gesehen, heute,
                gelesene_einstiege=bilanz.gelesene_einstiege,
                leitseite=leitseite)
            # Nur ein wirklich gelesener Anbieter geht in die Buchfuehrung
            # ueber die Hardware-Vermarktung ein. Ein ausgefallener Abruf
            # darf keine Marke zum SIM-only-Anbieter erklaeren.
            db.protokolliere_lauf(bilanz.name, heute, funde=len(bilanz.listungen))
        bilanzen.append({
            "anbieter": bilanz.name,
            "status": bilanz.status,
            "grund": bilanz.grund,
            "listungen": len(bilanz.listungen),
            "neu": neu,
            "seiten": bilanz.seiten_versucht,
            "gelesen": len(bilanz.gelesene_einstiege),
            "produkte_abgerufen": bilanz.produkte_abgerufen,
            "gedeckelt": bilanz.gedeckelt,
            "vollstaendig": bilanz.vollstaendig,
            "nicht_verlinkt": bilanz.nicht_verlinkt,
        })

    historie.save()
    db.save(heute)

    kollisionen = list(getattr(db, "kollisionen", []))
    bilanz = {
        "status": "ok",
        "anbieter": bilanzen,
        "abgefragt": ergebnis["abgefragt"],
        "listungen": len(ergebnis["listungen"]),
        "neu": neu_gesamt,
        "gealtert": gealtert_gesamt,
        "preispunkte": punkte,
        "bestand": len(db.eintraege()),
        # Die Liste ist gedeckelt, die ZAHL ist es nicht - sonst meldet ein
        # Lauf mit 300 unerkannten Titeln genau 40 davon und sieht harmlos aus.
        "unbekannte_titel": ergebnis["unbekannte_titel"][:40],
        "unbekannte_titel_gesamt": len(ergebnis["unbekannte_titel"]),
        "unbekannte_farben": sorted({f for b in ergebnis["anbieter"]
                                     for f in b.unbekannte_farben})[:40],
        "kollisionen": len(kollisionen),
        "sekunden": round(time.monotonic() - beginn, 1),
    }
    log.info("Geraeteradar: %d Anbieter abgefragt, %d Listungen (%d neu), "
             "%d Preispunkte, %d gealtert, Bestand %d, %.1fs",
             bilanz["abgefragt"], bilanz["listungen"], bilanz["neu"],
             punkte, gealtert_gesamt, bilanz["bestand"], bilanz["sekunden"])
    for satz in bilanzen:
        if satz["status"] != "ok":
            # Die Zahlen gehoeren in DIESE Zeile. Ein Anbieter, der 84
            # Listungen liefert und trotzdem "fehler" heisst, ist erklaerbar
            # (der Einstieg galt als unvollstaendig gelesen) - aber nur, wenn
            # das Protokoll die 84 auch nennt.
            log.info("Geraeteradar: %s -> %s, %d Listungen aus %d Produktseiten "
                     "(%s)", satz["anbieter"], satz["status"], satz["listungen"],
                     satz["produkte_abgerufen"], satz["grund"][:160])
    if bilanz["unbekannte_titel"]:
        # Die Arbeitsliste fuer config/geraete_katalog.yaml. Sie stand bisher
        # nur in der Rueckgabe - und der naechtliche Lauf gibt an niemanden
        # zurueck, sein einziger Kanal ist dieses Protokoll.
        log.info("Geraeteradar: %d Titel ohne Katalogtreffer (Arbeitsliste "
                 "fuer config/geraete_katalog.yaml): %s",
                 bilanz["unbekannte_titel_gesamt"],
                 " | ".join(bilanz["unbekannte_titel"][:25]))
    if bilanz["unbekannte_farben"]:
        log.info("Geraeteradar: unbekannte Farbschreibweisen (Arbeitsliste "
                 "fuer config/farben.yaml): %s",
                 ", ".join(bilanz["unbekannte_farben"]))
    return bilanz


def main() -> None:
    """Eigener Einstieg fuer den naechtlichen Lauf."""
    import argparse

    from .config import load_config

    p = argparse.ArgumentParser(description="Geraete- und Preisradar")
    p.add_argument("--root", default=".")
    p.add_argument("--frist", type=float, default=FRIST_STANDARD)
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = Path(args.root)
    cfg = load_config(root)
    heute = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run_geraete_stage(root, cfg.settings.get("http", {}), heute,
                      frist_sekunden=args.frist)


if __name__ == "__main__":       # pragma: no cover
    main()
