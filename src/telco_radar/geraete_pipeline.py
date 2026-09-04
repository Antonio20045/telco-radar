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
from .analyze.tarif_referenzen import aus_bestand
from .analyze.tco_store import TcoDB
from .tarif_bezug import Tarifbestand
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
    ("nicht anfassen") unterscheiden koennen. Ein Verbindungsfehler bleibt
    dagegen eine Ausnahme und wird oben als Fehler gewertet, nicht als
    Freibrief.

    DIESE FUNKTION HAT DAS BIS ZUM 28.08.2026 NICHT GEHALTEN, und ihre
    eigene Docstring behauptete das Gegenteil ("`fetch` wirft bei beidem
    nicht"). `collect.http.fetch` ruft `raise_for_status()` - es wirft bei
    JEDEM 4xx. Der Waechter bekam damit statt eines Status eine Ausnahme,
    und sein Ausnahmezweig sagt zu Recht "kein Ergebnis heisst nicht
    erlaubt": der Anbieter wurde als nicht abrufbar gefuehrt.

    Aufgefallen ist es nie, weil jeder bisher konfigurierte Host eine
    robots.txt mit HTTP 200 ausliefert. `api.vodafone.de` ist der erste
    ohne - dort antwortet 404, also "keine Regeln", und der ganze Anbieter
    fiel mit "404 Not Found" aus, obwohl die Schnittstelle einwandfrei
    antwortet. Ein Host ohne robots.txt ist der Normalfall im Web, nicht
    der Sonderfall.
    """
    import httpx

    from .collect.http import fetch

    def hole(url: str, kopfzeilen: Optional[dict] = None):
        try:
            antwort = fetch(url, http_cfg, extra_headers=kopfzeilen or None)
        except httpx.HTTPStatusError as exc:
            # Der Statuscode IST hier die Auskunft - 404 heisst etwas
            # anderes als 403, und beide etwas anderes als "kein Netz".
            return (exc.response.status_code, exc.response.text)
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
        # Die Buchfuehrung unterscheidet zwei Dinge, die vorher in einem
        # Handgriff steckten: `laeufe` (zaehlt nur VOLLSTAENDIGE Laeufe -
        # ein ausgefallener Abruf darf keine Marke zum SIM-only-Anbieter
        # erklaeren) und die MESSTERMINE (jeder Tag, an dem Listungen
        # wirklich gesehen wurden, auch in einem Teillauf). mobilcom-debitel
        # bestaetigte jede Nacht seine Listungen, wurde am Zeitbudget aber
        # nie fertig - und fehlte deshalb komplett in der Bilanz.
        if bilanz.vollstaendig or bilanz.listungen:
            db.protokolliere_lauf(bilanz.name, heute,
                                  funde=len(bilanz.listungen),
                                  vollstaendig=bilanz.vollstaendig)
        bilanzen.append({
            "anbieter": bilanz.name,
            "status": bilanz.status,
            "grund": bilanz.grund,
            "listungen": len(bilanz.listungen),
            "neu": neu,
            "seiten": bilanz.seiten_versucht,
            "gelesen": len(bilanz.gelesene_einstiege),
            "produkte_abgerufen": bilanz.produkte_abgerufen,
            "rohsaetze": bilanz.rohsaetze,
            "gedeckelt": bilanz.gedeckelt,
            "vollstaendig": bilanz.vollstaendig,
            "nicht_verlinkt": bilanz.nicht_verlinkt,
        })

    historie.save()
    db.save(heute)

    # --- Der Massstab aus dem Tarifbestand.
    #
    # `geraete_tco.json` gab es bis zum 04.09.2026 nicht: null Buendel, null
    # SIM-only-Referenzen, also keine einzige rechenbare TCO. Die Buendel
    # bleiben offen (sie brauchen einen Adapter, der Zuzahlung UND Tarif
    # ausweist, Phase 4) - die Referenzen aber nicht: was ein Tarif OHNE
    # Geraet kostet, steht seit Phase 6 belegt in `tarife.jsonl`.
    #
    # Das steht HIER und nicht im Renderer. Eine Zahl, die beim Rendern
    # entsteht, ist keine Messung, sondern eine Ableitung - und zwei
    # Ableitungen derselben Zahl an zwei Orten sind zwei Zahlen. Der
    # naechtliche Lauf ist der Ort, an dem der Geraetebestand entsteht;
    # die Referenzen gehoeren in dieselbe Datei und denselben Commit.
    referenzen: list = []
    tarife = 0
    try:
        bestand = Tarifbestand.aus_datei(zustand / "tarife.jsonl")
        tarife = len(bestand)
        referenzen = aus_bestand(bestand)
        tco = TcoDB(zustand / "geraete_tco.json")
        # ERSETZEN, nicht ergaenzen: die Referenzen sind abgeleitet und
        # entstehen bei jedem Lauf neu. Ergaenzt wuechse der Bestand bei
        # jeder Umbenennung eines Tarifs - siehe `ersetze_referenzen`.
        _, entfernt = tco.ersetze_referenzen(referenzen, heute)
        if entfernt:
            log.info("Tarif-Referenzen: %d nicht mehr im Tarifbestand - "
                     "entfernt", entfernt)
        tco.save(heute)
    except Exception as exc:  # noqa: BLE001
        # Ein Fehler hier darf den Geraetebestand nicht kosten - der ist
        # zu diesem Zeitpunkt schon gespeichert, und ein Messtag ist nicht
        # nachholbar (Lauf 31422689829).
        log.warning("SIM-only-Referenzen nicht geschrieben: %s", exc)
    log.info("Tarif-Referenzen: %d SIM-only-Referenzen aus %d Tarifen",
             len(referenzen), tarife)

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
        # Der Massstab aus dem Tarifbestand - in der Bilanz, damit ein
        # stiller Ausfall auffaellt. Steht hier 0, waehrend `tarife.jsonl`
        # gefuellt ist, hat der Schreibversuch geworfen.
        "sim_only_referenzen": len(referenzen),
        "tarife_im_bestand": tarife,
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
                     "(%d Preissaetze gelesen) (%s)",
                     satz["anbieter"], satz["status"], satz["listungen"],
                     satz["produkte_abgerufen"], satz["rohsaetze"],
                     satz["grund"][:160])
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
    # Zwei Katalog-Arbeitslisten: Modelle ohne belegtes Marktstartdatum
    # (ohne sie gibt es keine Nachfolger-Analyse) und Vorgaenger-Bezuege,
    # die auf kein Katalogmodell zeigen (Konfigurationsfehler). Beide
    # standen bis zum 03.09.2026 als Absaetze in der Sektion "Datenbasis
    # und Luecken" auf geraete.html - Antonio hat die Sektion kassiert,
    # und das Protokoll ist seit je der Kanal fuer Arbeitslisten des
    # naechtlichen Laufs. Der MARKTSTART ist der eine Punkt, den nur ein
    # Mensch schliessen kann; ohne diese Zeile waere die Liste still
    # verschwunden.
    ohne_start = [g.modell for g in katalog.geraete if not g.marktstart]
    if ohne_start:
        log.info("Geraeteradar: %d von %d Katalogmodellen ohne Marktstartdatum "
                 "(Arbeitsliste fuer config/geraete_katalog.yaml, keine "
                 "Nachfolger-Analyse): %s",
                 len(ohne_start), len(katalog.geraete),
                 " | ".join(ohne_start[:25]))
    ohn_kette = [g.modell for g in katalog.geraete
                 if g.vorgaenger and katalog.nach_id(g.vorgaenger_device_id) is None]
    if ohn_kette:
        log.warning("Geraeteradar: Vorgaenger-Bezug ohne Katalogziel in "
                    "config/geraete_katalog.yaml: %s",
                    " | ".join(ohn_kette[:25]))
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
