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
`.github/workflows/geraete.yml` holt sie um 02:17 UTC nach.

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
from html import escape
from pathlib import Path
from typing import Callable, Optional

from . import versand
from .analyze.geraete_store import (
    GELESEN,
    GeraeteDB,
    LESEFEHLER,
    NICHT_GELESEN,
    Preishistorie,
    TEILGELESEN,
    tag_de,
)
from .analyze.tarif_referenzen import aus_bestand
from .analyze.tco_buendel import aus_rohsaetzen
from .analyze.tco_store import TcoDB
from .tarif_bezug import Tarifbestand
from .collect.geraete import ADAPTER, hole_mit_robots, laufuhr, sammle
from .collect.geraete.robots import RobotsWaechter
from .collect.geraete import autoerkennung
from .collect.geraete.congstar import ergaenze_pib_slug
from .collect.tarif_einsundeins_simonly import ANBIETER as SIMONLY_ANBIETER
from .collect.tarif_einsundeins_simonly import sammle as sammle_simonly

from . import geraete_fragment
from .geraete_config import lade_farben, lade_katalog, lade_quellen

log = logging.getLogger(__name__)

FRIST_STANDARD = 900.0
FRIST_TAGESLAUF = 1500.0
UNBEKANNTE_TITEL_MAX = 40


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
    from .collect.http import StatusFehler, fetch

    def hole(
        url: str, kopfzeilen: Optional[dict] = None, user_agent: Optional[str] = None
    ):
        cfg = http_cfg if not user_agent else {**http_cfg, "user_agent": user_agent}
        try:
            antwort = fetch(url, cfg, extra_headers=kopfzeilen or None)
        except StatusFehler as exc:
            return (exc.response.status_code, exc.response.text)
        return (antwort.status_code, antwort.text)

    return hole


def _abdeckungszustand(bilanz) -> str:
    """Wie ist dieser Anbieter heute gelesen worden? EINE Definition.

    Sie steht hier und nicht im Store, weil nur diese Schicht beide Seiten
    kennt: den Sammelstatus des Collectors und den Bestand, der ihn
    aufnimmt. Vier Faelle, und die zwei mittleren sind die teuren:

      * `uebersprungen` / `nicht_umgesetzt`: der Lauf hat den Anbieter gar
        nicht angefasst (nicht crawlbar, kein Adapter).
      * AUSSERHALB DER BESUCHSZEIT, OHNE EINE EINZIGE GELESENE SEITE:
        robots.txt erlaubt den Abruf zu dieser Stunde nicht, und zwar von
        Anfang an. Das ist KEIN Ausfall, sondern eine Luecke: der Fall,
        den medimax.de und ep.de an jedem Tag erzeugen, an dem der Lauf
        ganz hinter 08:00 UTC liegt. Der PREIS dieser Regel steht hier,
        damit ihn niemand suchen muss: ueber einen Anbieter, der gar
        nicht erreichbar war, kann der Waechter nichts sagen. Das ist die
        ehrliche Luecke; die falsche Alternative waere ein taeglicher
        Alarm, den nach einer Woche niemand mehr liest.
      * AUSSERHALB DER BESUCHSZEIT, ABER MIT GELESENEM: die Tuer ging
        MITTEN im Lauf zu. Bis zum 22.09.2026 galt dieser Anbieter
        ebenfalls als "nicht angefasst" - auch mit vier gelesenen
        Produktseiten und drei Listungen (S2-1). Weil genau medimax.de und
        ep.de jede Nacht an ihrem Fenster haengen, war der Waechter fuer
        sie im REGELFALL blind. Was gelesen wurde, ist gesehen worden: der
        Teiltag bleibt im Vergleich, taugt aber nicht als Vergleichsbasis
        (`Messtag.vergleichsbasis`).
      * sonst `vollstaendig`: gelesen. Und alles andere - Zeitbudget,
        HTTP-Fehler, tote Einstiegsseite, abgeschalteter Collector - ist
        ein Leseversuch, der nicht durchkam. Der zaehlt als Ausfall, denn
        genau dafuer gibt es diesen Waechter.

    WARUM TOTE PRODUKTADRESSEN HIER NICHT VORKOMMEN (22.09.2026). Eine
    Quelle, deren Sitemap veraltete Adressen fuehrt, liefert einen Lauf
    mit Luecken - und trotzdem GELESEN, nicht TEILGELESEN. Das ist kein
    zweiter Teilzustand neben dem des Waechters, sondern ausdruecklich ein
    anderer Fall, und der Unterschied ist der Grund fuer beide Zustaende:
    TEILGELESEN heisst "der Lauf wurde ABGEBROCHEN, was durchkam ist nicht
    das Sortiment" - deshalb taugt so ein Tag nicht als Vergleichsbasis
    (`Messtag.vergleichsbasis`). Bei einer toten Adresse ist nichts
    abgebrochen: jede Adresse, die der Anbieter nennt, wurde versucht, und
    die fehlenden hat er selbst als nicht mehr vorhanden beantwortet. Da
    ist nichts mehr zu lesen - das IST das Sortiment, und der Tag ist eine
    taugliche Basis. Waere er TEILGELESEN, haette mobilcom-debitel nie
    wieder einen vollstaendigen Vergleichstag und liefe nach
    `_OHNE_BASIS_TAGE` dauerhaft in `ALARM_OHNE_BASIS` - genau die
    Blindheit, gegen die S2-1 gebaut wurde. Wie viele tote Adressen ein
    Lauf vertraegt, entscheidet allein
    `collect.geraete._MINDESTANTEIL_GELESENER_PRODUKTSEITEN`; reisst er
    die Schwelle, ist `vollstaendig` False und der Tag hier LESEFEHLER.
    Dass diese Schwelle je Nacht rechnet und eine langsame Erosion
    darunter durchginge, faengt nicht dieser Zustand ab, sondern der
    Verlauf: `geraete_store.ALARM_EROSION`, gespeist aus `_adressbilanz`.

    Erkannt wird die Besuchszeit am Flag der Bilanz
    (`ausserhalb_besuchszeit`), nicht am Grundtext - ein Waechter, der
    zwei Zustaende an einem String auseinanderhaelt, kippt bei der ersten
    Umformulierung.
    """
    if bilanz.status in ("uebersprungen", "nicht_umgesetzt"):
        return NICHT_GELESEN
    if getattr(bilanz, "ausserhalb_besuchszeit", False):
        gelesen = bilanz.gelesene_einstiege or bilanz.listungen or bilanz.buendel
        return TEILGELESEN if gelesen else NICHT_GELESEN
    return GELESEN if bilanz.vollstaendig else LESEFEHLER


def _adressbilanz(bilanz) -> tuple:
    """Die zwei ADRESSZAHLEN eines Laufs - oder zweimal `None`.

    `(produkte_versucht, tote_adressen)`. "Keine Produktadresse versucht"
    ist KEINE Null: ein uebersprungener Anbieter, ein toter Einstieg und
    ein Adapter ohne Produktseiten haben nichts gemessen, und eine 0
    daneben waere die Entwarnung "versucht, keine war tot" - genau die,
    die `test_ein_lauf_ohne_produktseiten_bucht_keine_null` fuer den
    Bestand verbietet und die bis zum 22.09.2026 trotzdem im
    Protokoll-JSON stand (CLAUDE.md Clean Code 3).

    EINE Rechnung fuer beide Kanaele - Bestand und Protokoll -, damit die
    Seite nicht etwas anderes zaehlt als das Log (Clean Code 7). Aus dem
    Bestand wird daraus die Reihe, an der `geraete_store.ALARM_EROSION`
    eine ueber Tage wegbroeselnde Quelle erkennt.
    """
    if bilanz.produkte_versucht <= 0:
        return (None, None)
    return (bilanz.produkte_versucht, len(bilanz.tote_adressen))


def melde_ausfall(alarme: list) -> None:
    """Je eingebrochenem Anbieter EINE Zeile, mit fester Wortform.

    Der Wortlaut ist Testvertrag (`tests/test_geraete_abdeckung.py`) - die
    Zeile ist der Alarm, und ein Alarm, dessen Wortlaut driftet, ist im
    Actions-Log nicht mehr grepbar. Der Satz selbst kommt aus dem
    Alarmobjekt: Protokoll, Mail und Quellenseite sagen damit wortgleich
    dasselbe (Clean Code 7).
    """
    for alarm in alarme:
        log.warning(
            "Geraeteradar-Abdeckung: %s (Quelle pruefen: geraete-quellen.html)",
            alarm.satz,
        )


def baue_alarm_mail(alarme: list, tag: str) -> tuple:
    """(Betreff, Text, HTML) fuer die Abdeckungsmail. Ohne Netz, ohne
    Zustellung - damit der Inhalt pruefbar ist, ohne einen Mailserver zu
    brauchen.

    Der Inhalt ist EIN Satz je Anbieter, derselbe wie im Protokoll und auf
    der Quellenseite. Keine Zusammenfassung, keine Empfehlung: die Mail
    sagt, was fehlt, und verlinkt die Seite, auf der es nachzusehen ist.
    """
    datum = tag_de(tag)
    seite = f"{versand.SITE_URL}/geraete-quellen.html"
    betreff = (
        f"Geräteradar {datum}: {len(alarme)} Anbieter heute nicht vollständig erfasst"
    )
    zeilen = [a.satz for a in alarme]
    text = "\n".join(
        [f"Stand {datum}", ""]
        + [f"- {z}" for z in zeilen]
        + ["", f"Quellenseite: {seite}"]
    )
    inhalt = (
        f"<html><body><p>Stand {escape(datum)}</p><ul>"
        + "".join(f"<li>{escape(z)}</li>" for z in zeilen)
        + f'</ul><p><a href="{seite}">Quellenseite</a></p></body></html>'
    )
    return betreff, text, inhalt


def sende_alarm_mail(alarme: list, tag: str, *, trocken: bool = False) -> str:
    """Verschickt die Abdeckungsmail und gibt die Bilanzzeile zurueck.

    Ohne Alarme wird NICHTS verschickt - eine taegliche "alles in Ordnung"-
    Mail ist nach zwei Wochen ein Filter im Postfach, und ein
    stummgeschalteter Kanal ist schlimmer als keiner (`versand.py`).

    Ein Zustellfehler wird NICHT geschluckt: `VersandFehler` geht an den
    Aufrufer weiter (der Workflow-Schritt faellt damit rot aus). Ein
    Alarmkanal, der still nicht zustellt, ist genau die Fehlerklasse, gegen
    die dieser Waechter gebaut ist.
    """
    if not alarme:
        return "keine Abdeckungsalarme - keine Mail"
    betreff, text, html = baue_alarm_mail(alarme, tag)
    ergebnis = versand.sende_mail(betreff, text, html, trocken=trocken)
    log.warning(
        "Geraeteradar-Abdeckung: %d Alarme per Mail (%s)", len(alarme), ergebnis
    )
    return ergebnis


def melde_proben(bilanzen: list) -> None:
    """Je Anbieter MIT Feld-Proben eine Zeile - die Existenz-Schwelle.

    100 % sind eine Info-Zeile, darunter eine Warnung mit den gescheiterten
    Feldebenen: genau der Fall, in dem die Nutzlast einer Schnittstelle
    sich geaendert hat, ohne dass ein Abruf fehlschlaegt (FM 2). Der
    TOTALTOD des Referenzfeldes zaehlt als gescheiterte Probe (Ebene
    "monthlyPrice"), nicht als Stille - sonst wuerde der Fall an der
    Buendelzeile ("0 von 0", Info) und am Ausfallalarm (o2 liefert seine
    LISTUNGEN weiter, Funde bleiben > 0) vorbeigehen (S2-1 der
    P5-Codepruefung). Ohne Kandidaten (Probe lief nicht - kein Bündel-
    zweig, nur Zubehör- und tariflose Sätze) steht keine Zeile: dafuer
    sind die Buendel- und Ausfallzeile da.
    """
    for satz in bilanzen:
        proben = satz.get("proben") or {}
        erwartete = int(proben.get("kandidaten", 0))
        if not erwartete:
            continue
        bestanden = int(proben.get("bestanden", 0))
        prozent = int(100.0 * bestanden / erwartete)
        ebenen = ", ".join(
            f"{wert}x {name}"
            for name, wert in sorted(proben.items())
            if name not in ("kandidaten", "bestanden") and int(wert) > 0
        )
        if prozent >= 100:
            log.info(
                "Geraeteradar-Probe: %s liefert %d von %d erwarteten "
                "Saetzen noch ihre Felder (%d %%)",
                satz["anbieter"],
                bestanden,
                erwartete,
                prozent,
            )
        else:
            log.warning(
                "Geraeteradar-Probe: %s liefert %d von %d erwarteten "
                "Saetzen noch ihre Felder (%d %%) - gescheitert an: %s",
                satz["anbieter"],
                bestanden,
                erwartete,
                prozent,
                ebenen or "unbekannt",
            )


def nachsammle_buendel(
    bilanzen: list,
    quellen,
    hole: Callable,
    uhr: Callable[[], datetime],
) -> None:
    """Die Nachbearbeitungs-Haken der Adapter ueber die Buendel laufen
    lassen. Wirft nie - ein Fehler hier darf den Bestand nicht kosten,
    er ist an dieser Stelle laengst gespeichert.

    ROBOTS GILT AUCH HIER (S2-3, 22.09.2026). Die Haken rufen selbst ab
    (`vodafone.loese_tarifnamen`, `einsundeins.ergaenze_buendel`) und
    bekamen bis hierher das ROHE `hole`: ohne Disallow, ohne Crawl-delay,
    ohne Fensterpruefung - und das ausgerechnet nach der Sammelphase, also
    an der spaetesten Stelle des Laufs, an der ein Besuchsfenster am
    ehesten zu ist. Die Zusage "die Fensterpruefung gilt JE ABRUF"
    (Collector-Modulkopf, `geraete.yml`) hielt fuer sie nicht. Jeder Haken
    bekommt deshalb ein `hole`, das durch dieselbe `Abrufschleuse` geht
    wie die Sammelphase - je Anbieter eine eigene, wie dort.

    `uhr()` ist die Zeit des NAECHSTEN Abrufs: die Stufe laeuft in Echtzeit,
    ein eingefrorener Zeitstempel waere der Fehler, den die Fensterprobe sucht.
    """
    for bilanz in bilanzen:
        if not bilanz.buendel:
            continue
        anbieter = quellen.nach_name(bilanz.name)
        adapter = ADAPTER.get(anbieter.methode) if anbieter else None
        if adapter is None:
            continue
        user_agent = (getattr(anbieter, "user_agent", "") or "").strip()
        waechter = RobotsWaechter(
            hole=(lambda url, ua=user_agent: hole(url, user_agent=ua))
            if user_agent
            else hole
        )
        hole_anbieter = (
            (
                lambda url, *args, ua=user_agent, **kwargs: hole(
                    url, *args, user_agent=ua, **kwargs
                )
            )
            if user_agent
            else hole
        )
        gebremst = hole_mit_robots(
            hole_anbieter,
            waechter,
            getattr(anbieter, "rate_limit_sekunden", 0.0) or 0.0,
            uhr,
        )
        for haken, meldung in (
            (
                adapter.loese_tarifnamen,
                "%s: %d von %d Buendel-Tarifnamen ueber die "
                "Tarifschnittstelle aufgeloest",
            ),
            (
                adapter.ergaenze_buendel,
                "%s: %d Buendel-Saetze um die Bereitstellungsgebuehr "
                "ergaenzt (%d Rohsaetze)",
            ),
        ):
            if haken is None:
                continue
            try:
                gesetzt = haken(
                    gebremst,
                    dict(getattr(anbieter, "kopfzeilen", None) or {}),
                    bilanz.buendel,
                )
                if gesetzt:
                    log.info(meldung, bilanz.name, gesetzt, len(bilanz.buendel))
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "%s: Buendel-Nachsammeln gescheitert (%s)", bilanz.name, exc
                )


def run_geraete_stage(
    root: Path,
    http_cfg: dict,
    heute: Optional[str],
    jetzt: Optional[datetime] = None,
    frist_sekunden: Optional[float] = FRIST_STANDARD,
    hole: Optional[Callable] = None,
    referenz_anbieter: Optional[set] = None,
) -> dict:
    """Sammeln, aufnehmen, altern, speichern. Gibt die Bilanz zurueck.

    `referenz_anbieter` grenzt die SIM-only-Referenzstufe ein (Menge von
    Anbieternamen wie im Tarifbestand). Der naechtliche Gesamtlauf ruft
    OHNE den Parameter und erneuert den Massstab fuer alle Anbieter wie
    bisher. Ein Lokallauf EINES Anbieters (scripts/lokallauf_*.py) uebergibt
    seinen Namen - dann wird auch die 1&1-SIM-only-Messung (S-5) nur
    ausgefuehrt, wenn 1&1 selbst im Scope liegt, und der Store traegt
    heutige Daten NUR an die Referenzen dieses Anbieters ein. Der Lauf
    vom 15.09.2026 hat ohne diesen Scope 35 Fremd-Referenzen neu datiert
    und 1&1 abgerufen (Befund Runde 2, outputs/telekom-taeglich-2026-09-15.md).
    """
    beginn = time.monotonic()
    if jetzt is None:
        jetzt = datetime.now(timezone.utc)
    if heute is None:
        heute = jetzt.strftime("%Y-%m-%d")
    uhr = laufuhr(jetzt)
    root = Path(root)

    katalog = lade_katalog(root)
    auto_vorher = len([g for g in katalog.geraete if g.auto])
    farben = lade_farben(root)
    quellen = lade_quellen(root)
    if not quellen.anbieter or not katalog.geraete:
        return {
            "status": "keine Konfiguration",
            "anbieter": [],
            "listungen": 0,
            "neu": 0,
            "gealtert": 0,
        }

    hole = hole or _hole_fabrik(http_cfg)
    ergebnis = sammle(quellen, katalog, farben, hole, heute, jetzt, frist_sekunden, uhr)

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
        uebergangen = {id(x) for x in getattr(db, "uebergangen", [])}
        for listung in bilanz.listungen:
            if id(listung) in uebergangen:
                continue
            if historie.schreibe(listung, heute):
                punkte += 1
        kollisionen.extend(getattr(db, "kollisionen", []))
        if bilanz.vollstaendig:
            leitseite = (
                anbieter.crawled_einstiege[0].url
                if anbieter and anbieter.crawled_einstiege
                else ""
            )
            gealtert_gesamt += db.mark_stale(
                bilanz.name,
                gesehen,
                heute,
                gelesene_einstiege=bilanz.gelesene_einstiege,
                leitseite=leitseite,
            )
        versucht, tote = _adressbilanz(bilanz)
        db.protokolliere_lauf(
            bilanz.name,
            heute,
            funde=len(bilanz.listungen),
            vollstaendig=bilanz.vollstaendig,
            zustand=_abdeckungszustand(bilanz),
            buendel=len(bilanz.buendel),
            tote_adressen=tote,
            produkte_versucht=versucht,
        )
        bilanzen.append(
            {
                "anbieter": bilanz.name,
                "status": bilanz.status,
                "grund": bilanz.grund,
                "listungen": len(bilanz.listungen),
                "neu": neu,
                "seiten": bilanz.seiten_versucht,
                "gelesen": len(bilanz.gelesene_einstiege),
                "produkte_abgerufen": bilanz.produkte_abgerufen,
                "rohsaetze": bilanz.rohsaetze,
                "proben": dict(bilanz.proben),
                "gedeckelt": bilanz.gedeckelt,
                "vollstaendig": bilanz.vollstaendig,
                "nicht_verlinkt": bilanz.nicht_verlinkt,
                "produkte_versucht": versucht,
                "tote_adressen": tote,
            }
        )

    historie.save()
    db.save(heute)

    nachsammle_buendel(ergebnis["anbieter"], quellen, hole, uhr)

    rohbuendel = [
        b for bilanz in ergebnis["anbieter"] for b in getattr(bilanz, "buendel", [])
    ]
    referenzen: list = []
    tarife = 0
    neue_buendel = 0
    buendelbilanz = None
    geschrieben = False
    try:
        bestand = Tarifbestand.aus_datei(zustand / "tarife.jsonl")
        ergaenze_pib_slug(bestand)
        tarife = len(bestand)
        referenzen = aus_bestand(bestand)
        if not referenzen:
            log.warning(
                "Tarif-Referenzen: der Tarifbestand liefert keine "
                "einzige Referenz (%d Saetze gelesen) - der "
                "bisherige Massstab bleibt unangetastet",
                tarife,
            )
        else:
            try:
                if (
                    referenz_anbieter is not None
                    and SIMONLY_ANBIETER not in referenz_anbieter
                ):
                    simonly_refs = []
                    simonly_protokoll = {}
                else:
                    simonly_refs, simonly_protokoll = sammle_simonly(hole, heute, uhr)
            except Exception as exc:  # noqa: BLE001
                simonly_refs = []
                log.warning(
                    "1&1 SIM-only-Messung gescheitert (%s) - die "
                    "Bestandsableitung bleibt stehen",
                    exc,
                )
            if simonly_refs:
                gemessen = {r.tarif_name for r in simonly_refs}
                zurueckgefallen = sum(
                    1
                    for r in referenzen
                    if r.anbieter == SIMONLY_ANBIETER and r.tarif_name not in gemessen
                )
                referenzen = [
                    r
                    for r in referenzen
                    if r.anbieter != SIMONLY_ANBIETER or r.tarif_name not in gemessen
                ] + simonly_refs
                log.info(
                    "1&1 SIM-only: %d Referenzen von der SIM-only-Seite "
                    "(%s, %d Tarifdetails gelesen%s)",
                    len(simonly_refs),
                    simonly_protokoll.get("seite", ""),
                    simonly_protokoll.get("details", 0),
                    f", {zurueckgefallen} nur im Bestand" if zurueckgefallen else "",
                )
            tco = TcoDB(zustand / "geraete_tco.json")
            _, entfernt = tco.ersetze_referenzen(
                referenzen, heute, anbieter=referenz_anbieter
            )
            if entfernt:
                log.info(
                    "Tarif-Referenzen: %d nicht mehr im Tarifbestand - entfernt",
                    entfernt,
                )
            if rohbuendel:
                buendelbilanz = aus_rohsaetzen(rohbuendel, bestand, heute)
                if buendelbilanz.buendel:
                    neue_buendel, _ = tco.upsert_buendel(buendelbilanz.buendel, heute)
            tco.save(heute)
            geschrieben = True
    except Exception as exc:  # noqa: BLE001
        log.warning("SIM-only-Referenzen nicht geschrieben: %s", exc)
    log.info(
        "Tarif-Referenzen: %d SIM-only-Referenzen aus %d Tarifen%s",
        len(referenzen),
        tarife,
        "" if geschrieben else " - NICHT GESCHRIEBEN",
    )
    log.info(
        "Buendel: %d von %d Rohsaetzen uebernommen (%d neu)%s%s",
        len(buendelbilanz.buendel) if buendelbilanz else 0,
        len(rohbuendel),
        neue_buendel,
        f", {buendelbilanz.verworfen} verworfen"
        if buendelbilanz and buendelbilanz.verworfen
        else "",
        "" if geschrieben else " - NICHT GESCHRIEBEN",
    )

    if kollisionen:
        log.warning(
            "Geraeteradar: %d Kollisionen - zwei Artikel desselben "
            "Laufs auf einer Listungs-ID, der zweite ist weder "
            "eingetragen noch in der Historie: %s",
            len(kollisionen),
            "; ".join(f"{lid} <- {titel!r}" for lid, titel in kollisionen[:12]),
        )

    auto_eintraege = [g for g in katalog.geraete if g.auto]
    auto_neu = max(0, len(auto_eintraege) - auto_vorher)
    if auto_eintraege:
        autoerkennung.speichere_auto_zusaetze(root, katalog)
    if auto_neu:
        log.info(
            "Geraeteradar: Auto-Erkennung hat %d neue Katalog-"
            "Eintraege angelegt (Auto-Bestand %d, Stand via data/state/"
            "geraete_katalog_auto.json): %s",
            auto_neu,
            len(auto_eintraege),
            " | ".join(
                f"{g.hersteller} {g.modell} (auto:{g.auto})"
                for g in auto_eintraege[-auto_neu:]
            ),
        )
    unbekannte = ergebnis.get("unbekannte") or []
    if unbekannte:
        zeilen = autoerkennung.persistiere_unbekannte(root, unbekannte, heute)
        log.info(
            "Geraeteradar: %d unbekannte Titel/Farben in data/state/"
            "geraete_unbekannt.jsonl gezaehlt (%d Zeilen Bestand)",
            len(unbekannte),
            zeilen,
        )
    bilanz = {
        "status": "ok",
        "anbieter": bilanzen,
        "abgefragt": ergebnis["abgefragt"],
        "listungen": len(ergebnis["listungen"]),
        "neu": neu_gesamt,
        "gealtert": gealtert_gesamt,
        "preispunkte": punkte,
        "bestand": len(db.eintraege()),
        "unbekannte_titel": ergebnis["unbekannte_titel"][:UNBEKANNTE_TITEL_MAX],
        "unbekannte_titel_gesamt": len(ergebnis["unbekannte_titel"]),
        "unbekannte_farben": sorted(
            {f for b in ergebnis["anbieter"] for f in b.unbekannte_farben}
        )[:40],
        "rohbuendel": len(rohbuendel),
        "buendel": len(buendelbilanz.buendel) if buendelbilanz else 0,
        "buendel_neu": neue_buendel,
        "buendel_ohne_tarif": buendelbilanz.ohne_tarif if buendelbilanz else 0,
        "kollisionen": len(kollisionen),
        "auto_neu": auto_neu,
        "auto_eintraege": len(auto_eintraege),
        "sim_only_referenzen": len(referenzen) if geschrieben else 0,
        "tarife_im_bestand": tarife,
        "sekunden": round(time.monotonic() - beginn, 1),
    }
    log.info(
        "Geraeteradar: %d Anbieter abgefragt, %d Listungen (%d neu), "
        "%d Preispunkte, %d gealtert, Bestand %d, %.1fs",
        bilanz["abgefragt"],
        bilanz["listungen"],
        bilanz["neu"],
        punkte,
        gealtert_gesamt,
        bilanz["bestand"],
        bilanz["sekunden"],
    )
    for satz in bilanzen:
        if satz["status"] != "ok":
            log.info(
                "Geraeteradar: %s -> %s, %d Listungen aus %d Produktseiten "
                "(%d Preissaetze gelesen) (%s)",
                satz["anbieter"],
                satz["status"],
                satz["listungen"],
                satz["produkte_abgerufen"],
                satz["rohsaetze"],
                satz["grund"][:160],
            )
        if satz["tote_adressen"]:
            log.info(
                "Geraeteradar: %s -> %d von %d Produktadressen tot "
                "(HTTP 404/410, von der Quelle selbst verlinkt), %d "
                "Produktseiten gelesen, Lauf %s",
                satz["anbieter"],
                satz["tote_adressen"],
                satz["produkte_versucht"],
                satz["produkte_abgerufen"],
                "vollständig" if satz["vollstaendig"] else "unvollständig",
            )
    alarme = db.ausfall_alarme(nur={satz["anbieter"] for satz in bilanzen}, heute=heute)
    melde_ausfall(alarme)
    bilanz["abdeckung_alarme"] = [a.als_dict() for a in alarme]
    melde_proben(bilanzen)
    if bilanz["unbekannte_titel"]:
        log.info(
            "Geraeteradar: %d Titel ohne Katalogtreffer (Arbeitsliste "
            "fuer config/geraete_katalog.yaml): %s",
            bilanz["unbekannte_titel_gesamt"],
            " | ".join(bilanz["unbekannte_titel"][:25]),
        )
    if bilanz["unbekannte_farben"]:
        log.info(
            "Geraeteradar: unbekannte Farbschreibweisen (Arbeitsliste "
            "fuer config/farben.yaml): %s",
            ", ".join(bilanz["unbekannte_farben"]),
        )
    ohne_start = [g.modell for g in katalog.geraete if not g.marktstart]
    if ohne_start:
        log.info(
            "Geraeteradar: %d von %d Katalogmodellen ohne Marktstartdatum "
            "(Arbeitsliste fuer config/geraete_katalog.yaml, keine "
            "Nachfolger-Analyse): %s",
            len(ohne_start),
            len(katalog.geraete),
            " | ".join(ohne_start[:25]),
        )
    ohn_kette = [
        g.modell
        for g in katalog.geraete
        if g.vorgaenger and katalog.nach_id(g.vorgaenger_device_id) is None
    ]
    if ohn_kette:
        log.warning(
            "Geraeteradar: Vorgaenger-Bezug ohne Katalogziel in "
            "config/geraete_katalog.yaml: %s",
            " | ".join(ohn_kette[:25]),
        )
    zeile = geraete_fragment.protokoll_zeile(root)
    if zeile:
        log.info("%s", zeile)
    return bilanz


def main() -> None:
    """Eigener Einstieg fuer den naechtlichen Lauf."""
    import argparse

    from .config import load_config

    p = argparse.ArgumentParser(description="Geraete- und Preisradar")
    p.add_argument("--root", default=".")
    p.add_argument("--frist", type=float, default=FRIST_STANDARD)
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    root = Path(args.root)
    cfg = load_config(root)
    run_geraete_stage(
        root, cfg.settings.get("http", {}), None, frist_sekunden=args.frist
    )


if __name__ == "__main__":
    main()
