#!/usr/bin/env python3
"""Der Versand nach jedem Radar-Lauf: Abonnenten aus der Brevo-Liste.

Seit 11.10.2026 (Antonio: ein Repo, Mail bei jedem Lauf) laeuft der Versand
als eigener Job in radar.yml nach dem Deploy. Scharf ist er nur, wenn die
Repo-Variable NEWSLETTER_AN genau `ja` ist; sonst rechnet er alles und
schickt nichts (`SCHALTER`). Bis Antonios Go bleibt die Variable leer.

    PYTHONPATH=src:. versand_brevo.py --bericht data/reports/<datum>.json
    PYTHONPATH=src:. versand_brevo.py --bericht ... --nur-test

`--nur-test` schickt eine Ausgabe ohne Filter an die erste Adresse aus
MAIL_TO (Antonios Berichtsadresse) und fasst die Liste nicht an.

Doppelversand: jeder zugestellte Kontakt bekommt das Ausgabedatum in
`ATTR_LETZTE`; wer es schon traegt, wird uebersprungen. Ausgegeben werden
nur Zahlen; `--zahlen` schreibt sie fuer data/state/newsletter_stats.jsonl.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, date, datetime
from pathlib import Path

from service.signup import tokens
from telco_radar.newsletter import render
from telco_radar.newsletter import versand as v
from telco_radar.newsletter.brevo_kontakte import BrevoKontakte
from telco_radar.newsletter.config import lade_katalog
from telco_radar.newsletter.filters import Filtersatz, waehle
from telco_radar.newsletter.quelle import aus_bericht, aus_promo
from telco_radar.newsletter.segments import bilde_segmente
from telco_radar.newsletter.transport import BrevoTransport, Trockenlauf
from telco_radar.report import geraete_bewegung
from telco_radar.report.html import MONTHS_DE

WURZEL = Path(__file__).resolve().parents[2]
SCHALTER = "NEWSLETTER_AN"
ABSENDER_VORGABE = "antonio.fotiadis.francisco@gmail.com"


def _fmt_date_de(iso: str) -> str:
    try:
        d = date.fromisoformat(iso[:10])
    except ValueError:
        return iso
    return f"{d.day}. {MONTHS_DE[d.month - 1]} {d.year}"


def vorige_ausgabe(datum: str, berichte: Path = WURZEL / "data" / "reports") -> str:
    """Das Datum des Berichts vor `datum` (Grenze fuer neue Aktionen), sonst ''."""
    tage = [p.stem for p in berichte.glob("*.json") if p.stem < datum]
    return max((t for t in tage if len(t) == 10 and t[4] == "-"), default="")


def _zahl(name: str, wert) -> None:
    print(f"{name}: {wert}", flush=True)


def scharf(umgebung: dict) -> bool:
    """Nur `ja` schaltet den Versand an Abonnenten ein."""
    return str(umgebung.get(SCHALTER) or "").strip() == "ja"


def _transport(trocken: bool):
    if trocken:
        return Trockenlauf()
    return BrevoTransport(
        api_key=os.environ.get("BREVO_API_KEY", ""),
        absender_name=render.lade_chrome().get("absender_name", "Telco Radar"),
        absender_adresse=os.environ.get("MAIL_FROM") or ABSENDER_VORGABE,
    )


def _ausgabe(treffer, bewegung, datum: str, basis: str, *, seit: str, filt):
    return render.baue(
        treffer,
        datum_de=_fmt_date_de(datum),
        bericht_url=f"{basis}/index.html",
        abmelde_url=f"{basis}/newsletter-abgemeldet.html",
        seit_datum=_fmt_date_de(seit[:10] or datum),
        basis_url=basis,
        mit_filter=filt,
        bewegung=bewegung,
    )


def _abmeldelink(abo, dienst: str) -> str:
    token = tokens.schreibe(
        os.environ.get("SIGNUP_TOKEN_KEY", ""),
        tokens.ZWECK_ABMELDUNG,
        {"sub_id": abo.id, "addr_hmac": abo.email_hmac},
    )
    return f"{dienst}/unsubscribe/{token}"


def _persoenlich(nachricht, platzhalter: str, link: str):
    return render.Nachricht(
        betreff=nachricht.betreff,
        html=nachricht.html.replace(platzhalter, link),
        text=nachricht.text.replace(platzhalter, link),
        headers=dict(nachricht.headers, **{"List-Unsubscribe": f"<{link}>"}),
    )


def testausgabe(bericht, datum, eintraege, katalog, basis, *, trocken) -> int:
    """Eine Ausgabe ohne Filter an Antonios Berichtsadresse."""
    adresse = (os.environ.get("MAIL_TO") or "").split(",")[0].strip()
    if not adresse and not trocken:
        print("::error::MAIL_TO fehlt - kein Testversand.", flush=True)
        return 2
    if adresse:
        print(f"::add-mask::{adresse}", flush=True)
    block = bericht.get("geraete_bewegung")
    if block is None:
        block = geraete_bewegung.fuer_bericht(
            WURZEL, date.fromisoformat(datum), WURZEL / "data" / "reports"
        )
    nachricht = _ausgabe(
        waehle(eintraege, Filtersatz(), katalog),
        dict(block, im_newsletter=True),
        datum,
        basis,
        seit=datum,
        filt=False,
    )
    nachricht.betreff = f"[Test] {nachricht.betreff}"
    ergebnis = _transport(trocken).send(nachricht, adresse or "trocken@example.invalid")
    _zahl(
        "Testversand",
        "zugestellt"
        if ergebnis.ok and not trocken
        else ("nur gerendert" if ergebnis.ok else f"gescheitert ({ergebnis.status})"),
    )
    return 0 if ergebnis.ok else 1


def main(argv=None, umgebung=None) -> int:
    teil = argparse.ArgumentParser(description=__doc__)
    teil.add_argument("--bericht", required=True)
    teil.add_argument("--promo", default="data/state/promo_db.json")
    teil.add_argument("--nur-test", action="store_true")
    teil.add_argument("--zahlen", default="", help="Datei fuer die Laufzahlen")
    args = teil.parse_args(argv)
    umgebung = os.environ if umgebung is None else umgebung

    bericht = json.loads(Path(args.bericht).read_text(encoding="utf-8"))
    datum = str(bericht.get("date") or "")
    basis = umgebung.get("SITE_BASE_URL") or "https://telco-radar.onrender.com"
    basis = basis.rstrip("/")
    katalog = lade_katalog(WURZEL)
    eintraege = aus_bericht(bericht, bericht_url=f"{basis}/reports/{datum}.html")
    if Path(args.promo).exists():
        promo = json.loads(Path(args.promo).read_text(encoding="utf-8"))
        eintraege += aus_promo(
            promo.get("entries") or [], neu_nach=vorige_ausgabe(datum)
        )
    _zahl("Eintraege zur Auswahl", len(eintraege))

    if args.nur_test:
        return testausgabe(
            bericht,
            datum,
            eintraege,
            katalog,
            basis,
            trocken=not umgebung.get("BREVO_API_KEY"),
        )

    trocken = not scharf(umgebung)
    _zahl("Versand an Abonnenten", "AN" if not trocken else "aus (nur gerechnet)")
    fehlt = [n for n in ("BREVO_API_KEY", "SIGNUP_TOKEN_KEY") if not umgebung.get(n)]
    if fehlt:
        print(f"::warning::{', '.join(fehlt)} fehlt - kein Versand.", flush=True)
        return 0 if trocken else 1
    brevo = BrevoKontakte(umgebung.get("BREVO_API_KEY", ""))
    liste = brevo.liste_id()
    if liste is None:
        _zahl("Abos aktiv", "0 (Liste noch nicht eingerichtet)")
        return 0
    kontakte = [k for k in brevo.alle(liste, katalog) if k.abo.aktiv]
    for k in kontakte:
        print(f"::add-mask::{k.abo.email}", flush=True)
    gesperrt = [k for k in kontakte if k.gesperrt]
    erledigt = [k for k in kontakte if k.letzte_ausgabe == datum]
    offen = [k for k in kontakte if not k.gesperrt and k.letzte_ausgabe != datum]
    _zahl("Abos aktiv", len(kontakte))
    _zahl("Von Brevo gesperrt", len(gesperrt))
    _zahl("Diese Ausgabe schon erhalten", len(erledigt))

    abos = [k.abo for k in offen]
    segmente = bilde_segmente(abos, eintraege, katalog, bericht.get("geraete_bewegung"))
    plan = v.baue_sendeplan(datum, segmente)
    je_id = {a.id: a for a in abos}
    platzhalter = f"{basis}/newsletter-abgemeldet.html"
    dienst = (
        umgebung.get("DIENST_BASE_URL") or "https://telco-radar-signup.onrender.com"
    ).rstrip("/")
    vorlagen = {
        s.hash: _ausgabe(
            s.treffer,
            s.geraete,
            datum,
            basis,
            seit=je_id[s.abo_ids[0]].confirmed_at,
            filt=not s.filter.ist_leer,
        )
        for s in segmente
        if not s.leer
    }
    nachrichten = {
        str(p.schluessel): _persoenlich(
            vorlagen[p.schluessel.segment],
            platzhalter,
            _abmeldelink(je_id[p.schluessel.abo], dienst),
        )
        for p in plan
    }
    _zahl("Empfaenger mit neuen Meldungen", len(plan))

    def vermerken(posten):
        if posten.status == "gesendet" and not trocken:
            brevo.ausgabe_vermerken(je_id[posten.schluessel.abo].email, datum)

    lauf = v.versende(
        plan,
        nachrichten,
        {a.id: a.email for a in abos},
        _transport(trocken),
        log_pfad=Path("newsletter_send_log.jsonl"),
        datum=datum,
        protokollieren=vermerken,
        uhr=lambda: datetime.now(UTC),
    )
    _zahl(
        "Zugestellt" if not trocken else "Gerechnet, nicht verschickt", lauf.zugestellt
    )
    _zahl("Fehler", lauf.fehler)
    if args.zahlen and not trocken:
        Path(args.zahlen).write_text(json.dumps(lauf.as_dict()), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
