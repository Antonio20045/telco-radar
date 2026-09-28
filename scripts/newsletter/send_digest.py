#!/usr/bin/env python3
"""Der Versandlauf: Bericht laden, segmentieren, rendern, zustellen.

Aufgerufen von `newsletter.yml` im privaten Repo, ausgeloest per
`repository_dispatch` NACH erfolgreichem Deploy. Bewusst ein eigener
Workflow in einem eigenen Repo:

  * Der Radar-Lauf lag am 6. August bei 27,4 von 35 Minuten - dort gehoert
    nichts mehr hinein, und ein gedrosselter Versand an 200 Empfaenger
    dauert allein rund sieben Minuten.
  * Ein fehlgeschlagener Versand darf den Radar-Lauf nie rot faerben. Der
    Bericht ist das Produkt; die Mail ist ein Ausspielkanal.
  * Abonnenten gehoeren nicht in ein oeffentliches Repository.

Die dreistufige Idempotenz und der Limit-Waechter stehen in
`newsletter/versand.py`; hier wird sie nur verdrahtet. Was hier NICHT
passiert: ein Modellaufruf. Die Mail besteht ausschliesslich aus Bausteinen,
die im Bericht-JSON stehen.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WURZEL / "src"))

from telco_radar.newsletter import render, versand as v          # noqa: E402
from telco_radar.newsletter import store as st                   # noqa: E402
from telco_radar.newsletter.config import lade_katalog           # noqa: E402
from telco_radar.newsletter.quelle import aus_bericht, aus_promo  # noqa: E402
from telco_radar.newsletter.segments import bilde_segmente       # noqa: E402
from telco_radar.newsletter.transport import BrevoTransport, Trockenlauf  # noqa: E402
from telco_radar.report.html import _fmt_date_de                 # noqa: E402


def _zahl(name: str, wert) -> None:
    print(f"{name}: {wert}", flush=True)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bericht", required=True,
                   help="Pfad zum Bericht-JSON aus dem oeffentlichen Repo")
    p.add_argument("--promo", default="", help="Pfad zu promo_db.json")
    p.add_argument("--store", default="store/subscribers.jsonl")
    p.add_argument("--send-log", default="store/send_log.jsonl")
    p.add_argument("--plan", default="store/sendeplan.json")
    p.add_argument("--dry-run", action="store_true",
                   help="alles rendern, nichts verschicken")
    p.add_argument("--stufe", choices=("plan", "versand"), default="versand",
                   help="'plan' schreibt nur den Sendeplan (Stufe 1 der "
                        "Idempotenz, wird VOR dem Versand gepusht)")
    p.add_argument("--nur-test", action="store_true",
                   help="eine Ausgabe (alle Themen) NUR an die Adresse aus "
                        "$TEST_EMPFAENGER - Store, Plan und Sendeprotokoll "
                        "bleiben unberuehrt")
    p.add_argument("--ausgabe", default="",
                   help="Verzeichnis: die Test-Ausgabe zusaetzlich als "
                        "test.html/test.txt ablegen (Sichtpruefung)")
    args = p.parse_args(argv)

    bericht = json.loads(Path(args.bericht).read_text(encoding="utf-8"))
    datum = str(bericht.get("date") or "")
    if not datum:
        raise SystemExit("::error::Bericht ohne Datum.")

    basis = os.environ.get("SITE_BASE_URL",
                           "https://telco-radar.onrender.com").rstrip("/")
    katalog = lade_katalog(WURZEL)

    eintraege = aus_bericht(bericht, bericht_url=f"{basis}/reports/{datum}.html")
    if args.promo and Path(args.promo).exists():
        daten = json.loads(Path(args.promo).read_text(encoding="utf-8"))
        eintraege += aus_promo(daten.get("entries") or [])
    _zahl("Eintraege zur Auswahl", len(eintraege))

    if args.nur_test:
        return _testausgabe(args, bericht, datum, eintraege, katalog, basis)

    store = st.AboStore(Path(args.store), katalog)
    abos = store.aktive()
    _zahl("Abos aktiv", len(abos))
    if not abos:
        _zahl("Versand", "kein Empfaenger - nichts zu tun")
        return 0

    segmente = bilde_segmente(abos, eintraege, katalog)
    voll = [s for s in segmente if not s.leer]
    _zahl("Segmente", f"{len(voll)} mit Inhalt, {len(segmente) - len(voll)} leer")

    plan = v.baue_sendeplan(datum, segmente)
    if args.stufe == "plan":
        # Stufe 1: den Plan schreiben und pushen, BEVOR die erste Mail
        # rausgeht. Ohne ihn weiss ein Wiederanlauf nach einem
        # Runner-Absturz nicht, was er eigentlich vorhatte.
        Path(args.plan).parent.mkdir(parents=True, exist_ok=True)
        Path(args.plan).write_text(json.dumps(
            {"date": datum, "posten": [p.as_dict() for p in plan]},
            ensure_ascii=False, indent=1), encoding="utf-8")
        _zahl("Sendeplan", f"{len(plan)} Posten geschrieben")
        # Der Waechter laeuft schon HIER mit: ein Lauf, der das Limit
        # reissen wuerde, soll abbrechen, bevor irgendetwas gepusht ist.
        try:
            rest = v.pruefe_limit(len(plan), Path(args.send_log))
            _zahl("Abstand zum Tageslimit", rest)
        except v.LimitGerissen as fehler:
            print(f"::error::{fehler}", flush=True)
            return 2
        return 0

    # Stufe 2: rendern und zustellen.
    nachrichten = {}
    for segment in voll:
        erstes_abo = store.finde(segment.abo_ids[0])
        nachrichten[segment.hash] = render.baue(
            segment.treffer,
            datum_de=_fmt_date_de(datum),
            bericht_url=f"{basis}/index.html",
            abmelde_url=f"{basis}/newsletter-abgemeldet.html",
            seit_datum=_fmt_date_de((erstes_abo.confirmed_at or datum)[:10])
            if erstes_abo else _fmt_date_de(datum),
            basis_url=basis,
            mit_filter=not segment.filter.ist_leer,
            bewegung=bericht.get("geraete_bewegung"))

    # Die Abmelde-URL traegt ein signiertes Token je Abo, ist also je
    # Empfaenger verschieden. GERENDERT wurde trotzdem nur einmal je Segment
    # - personalisiert wird durch Ersetzen der Platzhalter-URL, und das
    # kostet nichts. `versende()` sucht die Nachricht zuerst unter dem vollen
    # Sendeschluessel und faellt sonst auf den Segmentschluessel zurueck.
    adressen = {a.id: a.email for a in abos}
    je_posten = _personalisiert(nachrichten, plan,
                                _abmeldelinks(abos, basis), basis)

    transport = Trockenlauf() if args.dry_run else BrevoTransport(
        api_key=os.environ.get("BREVO_API_KEY", ""),
        absender_name=render.lade_chrome().get("absender_name", "Telco Radar"),
        absender_adresse=os.environ.get(
            "MAIL_FROM", "antonio.fotiadis.francisco@gmail.com"))

    protokoll = st.lies_jsonl(Path(args.send_log))

    def anhaengen(posten):
        # Stufe 2 der Idempotenz. Im echten Workflow ersetzt der Aufrufer
        # das durch einen Contents-API-Aufruf mit `sha`-Vorbedingung: bei
        # paralleler Aenderung schlaegt der FEHL statt zu ueberschreiben.
        protokoll.append(posten.as_dict())
        st.schreibe_jsonl(Path(args.send_log), protokoll)

    try:
        lauf = v.versende(plan, je_posten, adressen, transport,
                          log_pfad=Path(args.send_log), datum=datum,
                          protokollieren=anhaengen)
    except v.LimitGerissen as fehler:
        print(f"::error::{fehler}", flush=True)
        return 2

    _zahl("Zugestellt", lauf.zugestellt)
    _zahl("Uebersprungen (schon erledigt)", lauf.uebersprungen)
    _zahl("Fehler", lauf.fehler)
    _zahl("Dauerhaft gescheitert", len(lauf.dauerhaft_fehl))
    _zahl("Zustellquote", v.zustellquote(lauf))
    _zahl("Abstand zum Tageslimit", lauf.abstand_zum_limit)

    Path("newsletter_lauf.json").write_text(
        json.dumps(lauf.as_dict(), ensure_ascii=False), encoding="utf-8")
    return 0


def _testausgabe(args, bericht: dict, datum: str, eintraege, katalog,
                 basis: str) -> int:
    """P4: EINE Ausgabe an EINE Adresse, bevor echte Abonnenten eine sehen.

    Die Adresse kommt nur aus der Umgebung (`TEST_EMPFAENGER`, ein Secret im
    privaten Repo) und steht in keiner Logzeile. Die Auswahl ist die eines
    Abos ohne Filter (alle Themen). Store, Sendeplan und Sendeprotokoll
    werden nicht angefasst: ein Testversand zaehlt nicht als Zustellung.
    """
    from datetime import date

    from telco_radar.newsletter.filters import Filtersatz, waehle
    from telco_radar.report import geraete_bewegung
    block = bericht.get("geraete_bewegung")
    if block is None:
        # Ein Bericht von vor P4 traegt den Block nicht. Der Test soll ihn
        # trotzdem zeigen: gerechnet aus dem Geraetestand DIESES Checkouts,
        # genau wie der naechste Radar-Lauf es tut.
        block = geraete_bewegung.fuer_bericht(
            WURZEL, date.fromisoformat(datum), WURZEL / "data" / "reports")
    # Der Test zeigt den Block immer, auch an einem Freitag.
    block = dict(block, im_newsletter=True)
    adresse = os.environ.get("TEST_EMPFAENGER", "").strip()
    if not adresse and not args.dry_run:
        print("::error::TEST_EMPFAENGER fehlt - kein Testversand.", flush=True)
        return 2
    if adresse and os.environ.get("GITHUB_ACTIONS"):
        print(f"::add-mask::{adresse}", flush=True)
    nachricht = render.baue(
        waehle(eintraege, Filtersatz(), katalog),
        datum_de=_fmt_date_de(datum), bericht_url=f"{basis}/index.html",
        abmelde_url=f"{basis}/newsletter-abgemeldet.html",
        seit_datum=_fmt_date_de(datum), basis_url=basis, mit_filter=False,
        bewegung=block)
    nachricht.betreff = f"[Test] {nachricht.betreff}"
    if args.ausgabe:
        ziel = Path(args.ausgabe)
        ziel.mkdir(parents=True, exist_ok=True)
        (ziel / "test.html").write_text(nachricht.html, encoding="utf-8")
        (ziel / "test.txt").write_text(nachricht.text, encoding="utf-8")
    transport = Trockenlauf() if args.dry_run else BrevoTransport(
        api_key=os.environ.get("BREVO_API_KEY", ""),
        absender_name=render.lade_chrome().get("absender_name", "Telco Radar"),
        absender_adresse=os.environ.get(
            "MAIL_FROM", "antonio.fotiadis.francisco@gmail.com"))
    ergebnis = transport.send(nachricht, adresse or "trocken@example.invalid")
    _zahl("Testversand", "zugestellt" if ergebnis.ok else
          f"gescheitert ({ergebnis.status})")
    return 0 if ergebnis.ok else 1


def _abmeldelinks(abos, basis: str) -> dict:
    """Je Abo ein signierter Abmeldelink. Er laeuft NIE ab.

    Ein abgelaufener Abmeldelink waere das Gegenteil eines Widerrufs - die
    Mail von vor zwei Jahren muss ihn noch tragen.
    """
    sys.path.insert(0, str(WURZEL))
    from service.signup import tokens
    key = os.environ.get("SIGNUP_TOKEN_KEY", "")
    aus = {}
    for abo in abos:
        token = tokens.schreibe(key, tokens.ZWECK_ABMELDUNG,
                                {"sub_id": abo.id, "addr_hmac": abo.email_hmac})
        # Nicht `basis`: das ist die Website. `/unsubscribe/...` ist eine
        # Route des Signup-Dienstes. Derselbe Fehler wie beim
        # Bestaetigungslink, nur faellt er spaeter auf - erst wenn sich
        # jemand abmelden will und ein 404 bekommt.
        dienst = os.environ.get(
            "DIENST_BASE_URL", "https://telco-radar-signup.onrender.com"
        ).rstrip("/")
        aus[abo.id] = f"{dienst}/unsubscribe/{token}"
    return aus


def _personalisiert(nachrichten: dict, plan, abmeldelinks: dict,
                    basis: str) -> dict:
    """`str(Sendeschluessel) -> Nachricht` mit der Abmelde-URL des Empfaengers.

    Gerendert wird NICHT neu - ersetzt wird die Platzhalter-URL in HTML, Text
    und `List-Unsubscribe`. Alles andere an der Nachricht ist je Segment
    gleich, und genau dafuer gibt es Segmente.
    """
    from telco_radar.newsletter.render import Nachricht
    platzhalter = f"{basis}/newsletter-abgemeldet.html"
    aus: dict[str, Nachricht] = {}
    for posten in plan:
        vorlage = nachrichten.get(posten.schluessel.segment)
        if vorlage is None:
            continue
        link = abmeldelinks.get(posten.schluessel.abo, "")
        if not link:
            aus[str(posten.schluessel)] = vorlage
            continue
        aus[str(posten.schluessel)] = Nachricht(
            betreff=vorlage.betreff,
            html=vorlage.html.replace(platzhalter, link),
            text=vorlage.text.replace(platzhalter, link),
            headers=dict(vorlage.headers, **{"List-Unsubscribe": f"<{link}>"}))
    return aus


if __name__ == "__main__":
    raise SystemExit(main())
