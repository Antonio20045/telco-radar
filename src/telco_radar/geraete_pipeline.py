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
from .analyze.tco_buendel import aus_rohsaetzen
from .analyze.tco_store import TcoDB
from .tarif_bezug import Tarifbestand
from .collect.geraete import ADAPTER, sammle
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

    def hole(url: str, kopfzeilen: Optional[dict] = None,
             user_agent: Optional[str] = None):
        # `user_agent` ist der PER-ANBIETER-UEBERSCHREIBER (Anbieter.
        # user_agent, siehe geraete_config.py) - er baut ein EIGENES
        # http_cfg nur fuer diesen Aufruf, das globale `http_cfg` (aus
        # config/settings.yaml, Entscheidung E-1) bleibt fuer jeden anderen
        # Anbieter unangetastet. `fetch()` sieht davon nichts Neues: es
        # bekommt schlicht ein `http_cfg`, dessen `user_agent` schon den
        # honoreichen Wert traegt, und leitet daraus PRIMARY/Fallback wie
        # immer ab.
        cfg = http_cfg if not user_agent else {**http_cfg, "user_agent": user_agent}
        try:
            antwort = fetch(url, cfg, extra_headers=kopfzeilen or None)
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
    kollisionen: list = []
    for bilanz in ergebnis["anbieter"]:
        anbieter = quellen.nach_name(bilanz.name)
        neu, gesehen = db.upsert(bilanz.listungen, heute)
        neu_gesamt += neu
        # NUR WAS DIE DATENBANK GENOMMEN HAT, BEKOMMT EINEN HISTORIENPUNKT.
        # `upsert` verwirft den zweiten Satz derselben ID (zwei Artikel,
        # die die Zuordnung nicht unterscheiden konnte) - und diese Schleife
        # schrieb ihn bis zum 04.09.2026 trotzdem in die Historie. Ergebnis:
        # ALDI TALKs "Galaxy A17 LTE + Starter Kit" (129 EUR) und "Galaxy
        # A17 5G" (159 EUR) treffen beide den Katalogeintrag "Galaxy A17",
        # teilen sich eine Listungs-ID, und `geraete_preise.jsonl` trug je
        # Tag zwei Zeilen: 13 von 15 Pfeilen in G2 zeigten eine
        # Preisaenderung, die nie stattgefunden hat (QA-Befund B2).
        uebergangen = {id(x) for x in getattr(db, "uebergangen", [])}
        for listung in bilanz.listungen:
            if id(listung) in uebergangen:
                continue
            if historie.schreibe(listung, heute):
                punkte += 1
        # Ueber ALLE Anbieter sammeln: `db.kollisionen` gilt je Aufruf, und
        # am Ende der Schleife stand nur die Liste des letzten Anbieters.
        kollisionen.extend(getattr(db, "kollisionen", []))
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

    # --- Der Massstab aus dem Tarifbestand - und die Buendel dazu.
    #
    # `geraete_tco.json` gab es bis zum 04.09.2026 nicht: null Buendel, null
    # SIM-only-Referenzen, also keine einzige rechenbare TCO. Seit dem
    # 04.09.2026 stehen BEIDE Seiten: die Referenzen aus `tarife.jsonl`
    # (was ein Tarif OHNE Geraet kostet) und die Buendel aus den
    # Buendel-Einstiegen der Anbieter (`kind: buendel`).
    #
    # Sie stehen in DIESER Reihenfolge, und das ist keine Kosmetik: ein
    # Buendel ohne aufloesbaren Tarif wird verworfen, und aufloesen kann
    # nur, wer den Tarifbestand gelesen hat. Beides braucht denselben
    # `Tarifbestand`, er wird deshalb einmal geladen.
    #
    # Das steht HIER und nicht im Renderer. Eine Zahl, die beim Rendern
    # entsteht, ist keine Messung, sondern eine Ableitung - und zwei
    # Ableitungen derselben Zahl an zwei Orten sind zwei Zahlen. Der
    # naechtliche Lauf ist der Ort, an dem der Geraetebestand entsteht;
    # die Referenzen gehoeren in dieselbe Datei und denselben Commit.
    #
    # TARIFNAMEN AUFLOESEN, BEVOR DER TARIFBESTAND BEFRAGT WIRD (B1,
    # 05.09.2026): manche Anbieter (Vodafone) nennen in ihrer Buendelantwort
    # keinen Klarnamen, nur einen Hash - ein zweiter, GEZIELTER Abruf je
    # Geraet (nicht je Rohsatz) kann ihn nachliefern (siehe
    # `vodafone.loese_tarifnamen`). Das gehoert hierher und nicht in den
    # Adapter: ein `lies_buendel()` bleibt ein reiner Text-zu-Daten-
    # Uebersetzer ohne eigenes Netz, diese Stufe darf zusaetzliche GETs
    # machen. Ein Fehler hier darf den Geraetebestand nicht kosten - er
    # ist zu diesem Zeitpunkt schon gespeichert.
    for bilanz in ergebnis["anbieter"]:
        if not bilanz.buendel:
            continue
        anbieter = quellen.nach_name(bilanz.name)
        adapter = ADAPTER.get(anbieter.methode) if anbieter else None
        if adapter is None or adapter.loese_tarifnamen is None:
            continue
        try:
            aufgeloest = adapter.loese_tarifnamen(
                hole, dict(getattr(anbieter, "kopfzeilen", None) or {}),
                bilanz.buendel)
            if aufgeloest:
                log.info("%s: %d von %d Buendel-Tarifnamen ueber die "
                         "Tarifschnittstelle aufgeloest",
                         bilanz.name, aufgeloest, len(bilanz.buendel))
        except Exception as exc:                          # noqa: BLE001
            log.warning("%s: Tarifnamen-Aufloesung gescheitert (%s)",
                        bilanz.name, exc)

    rohbuendel = [b for bilanz in ergebnis["anbieter"]
                  for b in getattr(bilanz, "buendel", [])]
    referenzen: list = []
    tarife = 0
    neue_buendel = 0
    buendelbilanz = None
    geschrieben = False
    try:
        bestand = Tarifbestand.aus_datei(zustand / "tarife.jsonl")
        tarife = len(bestand)
        referenzen = aus_bestand(bestand)
        if not referenzen:
            # "NICHT GELESEN" IST NICHT "LEER". `Tarifbestand.aus_datei`
            # wirft bei fehlender Datei nicht, sondern liefert einen leeren
            # Bestand - ein Baseline-Reset, ein Merge-Konflikt oder ein
            # Wettlauf mit `radar.yml` saehe damit aus wie "es gibt keine
            # Tarife mehr", und `ersetze_referenzen` loeschte den ganzen
            # Massstab. Dieselbe Fehlerklasse wie bei
            # `promo_store.mark_stale` ohne `gepruefte_seiten` und beim
            # `PromoExtractionError`, beide in CLAUDE.md § 6 als teuer
            # dokumentiert.
            log.warning("Tarif-Referenzen: der Tarifbestand liefert keine "
                        "einzige Referenz (%d Saetze gelesen) - der "
                        "bisherige Massstab bleibt unangetastet", tarife)
        else:
            tco = TcoDB(zustand / "geraete_tco.json")
            # ERSETZEN, nicht ergaenzen: die Referenzen sind abgeleitet und
            # entstehen bei jedem Lauf neu. Ergaenzt wuechse der Bestand bei
            # jeder Umbenennung eines Tarifs - siehe `ersetze_referenzen`.
            _, entfernt = tco.ersetze_referenzen(referenzen, heute)
            if entfernt:
                log.info("Tarif-Referenzen: %d nicht mehr im Tarifbestand - "
                         "entfernt", entfernt)
            if rohbuendel:
                # AUFFRISCHEN, nicht ersetzen - anders als die Referenzen.
                # Ein Buendel ist eine MESSUNG an einer Anbieterseite, keine
                # Ableitung aus dem Tarifbestand; faellt der Abruf einer
                # Nacht aus, darf sein Verschwinden nicht als "gibt es nicht
                # mehr" gelten. Dieselbe Haltung wie bei `GeraeteDB`, die
                # nichts loescht.
                buendelbilanz = aus_rohsaetzen(rohbuendel, bestand, heute)
                if buendelbilanz.buendel:
                    neue_buendel, _ = tco.upsert_buendel(
                        buendelbilanz.buendel, heute)
            tco.save(heute)
            # ERST HIER. `save()` kann werfen (Platte, Rechte, Pfad), und
            # der Auffangboden unten faengt das ab - eine Bilanz, die schon
            # vorher "25 Referenzen" meldet, ist genau im einzigen Fall
            # blind, fuer den sie gebaut ist.
            geschrieben = True
    except Exception as exc:  # noqa: BLE001
        # Ein Fehler hier darf den Geraetebestand nicht kosten - der ist
        # zu diesem Zeitpunkt schon gespeichert, und ein Messtag ist nicht
        # nachholbar (Lauf 31422689829).
        log.warning("SIM-only-Referenzen nicht geschrieben: %s", exc)
    log.info("Tarif-Referenzen: %d SIM-only-Referenzen aus %d Tarifen%s",
             len(referenzen), tarife,
             "" if geschrieben else " - NICHT GESCHRIEBEN")
    # Die Buendelzeile steht AUCH da, wenn nichts ankam: "0 von 0" heisst
    # "kein Anbieter liefert Buendel", "0 von 63" heisst "der Tarifbestand
    # traegt ihre Tarife nicht" - zwei ganz verschiedene Arbeitslisten, und
    # ohne beide Zahlen sind sie nicht zu unterscheiden.
    log.info("Buendel: %d von %d Rohsaetzen uebernommen (%d neu)%s%s",
             len(buendelbilanz.buendel) if buendelbilanz else 0,
             len(rohbuendel), neue_buendel,
             f", {buendelbilanz.verworfen} verworfen" if buendelbilanz
             and buendelbilanz.verworfen else "",
             "" if geschrieben else " - NICHT GESCHRIEBEN")

    if kollisionen:
        # Die Arbeitsliste fuer den Katalog: zwei Artikel auf einer ID sind
        # zwei Produkte, die der Katalog nicht auseinanderhaelt.
        log.warning("Geraeteradar: %d Kollisionen - zwei Artikel desselben "
                    "Laufs auf einer Listungs-ID, der zweite ist weder "
                    "eingetragen noch in der Historie: %s",
                    len(kollisionen),
                    "; ".join(f"{lid} <- {titel!r}"
                              for lid, titel in kollisionen[:12]))
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
        # Zwei Zahlen, nicht eine: `rohbuendel` sagt, was die Anbieter
        # geliefert haben, `buendel` was davon einen Tarif im Bestand hat.
        "rohbuendel": len(rohbuendel),
        "buendel": len(buendelbilanz.buendel) if buendelbilanz else 0,
        "buendel_neu": neue_buendel,
        "buendel_ohne_tarif": buendelbilanz.ohne_tarif if buendelbilanz else 0,
        "kollisionen": len(kollisionen),
        # Der Massstab aus dem Tarifbestand - in der Bilanz, damit ein
        # stiller Ausfall auffaellt. Steht hier 0, waehrend `tarife.jsonl`
        # gefuellt ist, hat der Schreibversuch geworfen.
        "sim_only_referenzen": len(referenzen) if geschrieben else 0,
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
