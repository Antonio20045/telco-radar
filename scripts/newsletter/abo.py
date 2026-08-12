#!/usr/bin/env python3
"""Anmeldung, Bestaetigung, Abmeldung - die drei Ereignisse des Abo-Stores.

Aufgerufen von den Workflows im PRIVATEN Repo `telco-radar-mail`, die dieses
Repo dafuer auschecken. Warum die Logik hier und nicht dort liegt, steht im
Kopf von `src/telco_radar/newsletter/store.py`: eine Kopie der Filter-Engine
im privaten Repo wuerde driften, und nach drei Monaten schickte die Mail
etwas anderes, als die Website zeigt.

**In diesem Repo liegt keine einzige Adresse.** Die Skripte bekommen den Pfad
zum entschluesselten Store als Argument; der liegt zur Laufzeit im Runner und
nirgends sonst.

Drei Unterbefehle:

    abo.py doi         --token-datei ... --store ... --doi-log ...
    abo.py confirm     --token-datei ... --store ...
    abo.py unsubscribe --token-datei ... --store ...

Das Token kommt ueber eine DATEI, nicht ueber ein Argument: eine
Kommandozeile steht in der Prozessliste und im Actions-Log, und im Token
steckt die Adresse.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WURZEL / "src"))
sys.path.insert(0, str(WURZEL))

from service.signup import tokens                                # noqa: E402
from telco_radar.newsletter import store as st                   # noqa: E402
from telco_radar.newsletter import subscription as sub           # noqa: E402
from telco_radar.newsletter.config import lade_katalog           # noqa: E402
from telco_radar.newsletter.filters import lies_filtersatz       # noqa: E402
from telco_radar.report import rechtstexte                       # noqa: E402


def maskiere(wert: str) -> None:
    """Actions anweisen, diesen Wert in JEDER Logzeile zu schwaerzen.

    Vor dem ersten Gebrauch aufrufen - danach ist es zu spaet, die Zeile
    steht schon da. Ein Actions-Log ist oeffentlich, sobald das Repo es ist.
    """
    if wert:
        print(f"::add-mask::{wert}", flush=True)


def _token(pfad: str, zweck: str, max_alter: int) -> dict:
    key = os.environ.get("SIGNUP_TOKEN_KEY", "")
    if not key:
        raise SystemExit("::error::SIGNUP_TOKEN_KEY fehlt.")
    roh = Path(pfad).read_text(encoding="utf-8").strip()
    try:
        daten = tokens.lies(key, zweck, roh, max_alter=max_alter)
    except tokens.TokenFehler as fehler:
        # Kein Detail nach aussen: ob ein Token abgelaufen oder gefaelscht
        # war, geht niemanden etwas an, der das Log lesen kann.
        raise SystemExit(f"::error::Token abgelehnt ({fehler}).") from fehler
    maskiere(str(daten.get("email") or ""))
    return daten


def _zahl(name: str, wert) -> None:
    """Eine Zeile fuers Actions-Log. ZAHLEN, keine Adressen."""
    print(f"{name}: {wert}", flush=True)


# ----------------------------------------------------------------- doi -----

def befehl_doi(args) -> int:
    """Bestaetigungsmail versenden - oder stillschweigend nicht.

    HIER liegt die 24-Stunden-Sperre je Adresse, und nicht im Signup-Dienst.
    Dessen Zaehler ist nach jedem Spin-down und jedem Deploy leer; wer die
    Sperre dort einbaut, baut sie an der einzigen Stelle ein, an der sie
    sicher nicht wirkt. Ohne sie ist das offene Formular ein Versandwerkzeug
    fuer Dritte: jemand traegt eine fremde Adresse ein, so oft er mag, und
    das schlaegt direkt auf die Absenderreputation durch.
    """
    daten = _token(args.token_datei, tokens.ZWECK_BESTAETIGUNG,
                   tokens.TTL_BESTAETIGUNG)
    kennwert = str(daten.get("addr_hmac") or "")
    doi_log = Path(args.doi_log)

    if st.doi_gesperrt(doi_log, kennwert):
        # STILLSCHWEIGEND. Eine Rueckmeldung waere ein Weg, herauszufinden,
        # ob eine Adresse gerade angeschrieben wurde.
        _zahl("DOI", "gesperrt (24-Stunden-Regel)")
        return 0

    adresse = str(daten.get("email") or "")
    if not sub.ist_adresse(adresse):
        _zahl("DOI", "abgelehnt (Adressform)")
        return 0

    from telco_radar.newsletter.render import lade_chrome
    from telco_radar.newsletter.transport import BrevoTransport, Trockenlauf
    from telco_radar.newsletter.render import Nachricht

    chrome = lade_chrome()
    basis = os.environ.get("SITE_BASE_URL",
                           "https://telco-radar.onrender.com").rstrip("/")
    bestaetigen = args.confirm_url or f"{basis}/confirm/unbekannt"
    nachricht = Nachricht(
        betreff="Bitte bestätigen: Telco Radar",
        html=_doi_html(bestaetigen, basis),
        text=_doi_text(bestaetigen, basis),
        # KEIN List-Unsubscribe: es gibt noch kein Abo, von dem man sich
        # abmelden koennte. Ein Header, der auf eine leere Handlung zeigt,
        # ist schlimmer als keiner.
        headers={})

    if args.trocken:
        transport = Trockenlauf()
    else:
        transport = BrevoTransport(
            api_key=os.environ.get("BREVO_API_KEY", ""),
            absender_name=chrome.get("absender_name", "Telco Radar"),
            absender_adresse=os.environ.get(
                "MAIL_FROM", "antonio.fotiadis.francisco@gmail.com"))
    ergebnis = transport.send(nachricht, adresse)
    _zahl("DOI", "versendet" if ergebnis.ok else f"gescheitert ({ergebnis.status})")
    if ergebnis.ok:
        # Vermerkt wird NUR bei Erfolg: eine gescheiterte Mail darf die
        # Adresse nicht 24 Stunden sperren, sonst kommt der Nutzer beim
        # zweiten Versuch nicht durch und weiss nicht warum.
        st.doi_vermerken(doi_log, kennwert, token_id=args.token_id)
    st.doi_aufraeumen(doi_log)
    return 0 if ergebnis.ok else 1


def _doi_html(bestaetigen: str, basis: str) -> str:
    import html as h
    return f"""<!DOCTYPE html><html lang=de><body style="margin:0;background:#f6f4ee">
<table role=presentation width="100%" cellpadding=0 cellspacing=0 border=0><tr>
<td align=center style="padding:28px 12px"><table role=presentation width=600
 cellpadding=0 cellspacing=0 border=0 style="width:100%;max-width:600px;background:#fffdf8;padding:26px 24px">
<tr><td style="font:700 24px/1.15 Georgia,serif;padding-bottom:14px;border-bottom:3px solid #141414">Telco Radar</td></tr>
<tr><td style="font:400 15px/1.6 Georgia,serif;color:#141414;padding-top:20px">
<p>Guten Tag,</p>
<p>bitte bestätigen Sie mit einem Klick, dass Sie den Telco Radar per E-Mail bekommen möchten:</p>
<p><a href="{h.escape(bestaetigen, True)}" style="color:#e60000;font:700 15px Arial,sans-serif">Anmeldung bestätigen &rsaquo;</a></p>
<p style="font-size:13px;color:#6b6b6b">Der Link gilt 72 Stunden. <strong>Wenn Sie das nicht waren, ignorieren Sie diese E-Mail — es passiert dann nichts.</strong> Ohne Ihren Klick wird nichts gespeichert und es kommt keine weitere Nachricht.</p>
<p style="font-size:13px;color:#6b6b6b">Angefordert über das Anmeldeformular auf {h.escape(basis, True)}.</p>
</td></tr>
<tr><td style="padding-top:24px;border-top:3px solid #141414;font:400 11px/1.6 Arial,sans-serif;color:#6b6b6b">
<a href="{h.escape(basis, True)}/impressum.html" style="color:#6b6b6b">Impressum</a> &middot;
<a href="{h.escape(basis, True)}/datenschutz.html" style="color:#6b6b6b">Datenschutzerklärung</a>
</td></tr></table></td></tr></table></body></html>"""


def _doi_text(bestaetigen: str, basis: str) -> str:
    return (
        "TELCO RADAR\n"
        "===========\n\n"
        "Guten Tag,\n\n"
        "bitte bestätigen Sie mit einem Klick, dass Sie den Telco Radar per\n"
        "E-Mail bekommen möchten:\n\n"
        f"{bestaetigen}\n\n"
        "Der Link gilt 72 Stunden.\n\n"
        "Wenn Sie das nicht waren, ignorieren Sie diese E-Mail - es passiert\n"
        "dann nichts. Ohne Ihren Klick wird nichts gespeichert und es kommt\n"
        "keine weitere Nachricht.\n\n"
        f"Angefordert über das Anmeldeformular auf {basis}.\n\n"
        f"Impressum: {basis}/impressum.html\n"
        f"Datenschutzerklärung: {basis}/datenschutz.html\n")


# ------------------------------------------------------------- confirm -----

def befehl_confirm(args) -> int:
    """Erst hier entsteht ein Abonnement - und das vollstaendige Protokoll."""
    daten = _token(args.token_datei, tokens.ZWECK_BESTAETIGUNG,
                   tokens.TTL_BESTAETIGUNG)
    pepper = os.environ.get("SIGNUP_PEPPER", "")
    if not pepper:
        raise SystemExit("::error::SIGNUP_PEPPER fehlt.")

    katalog = lade_katalog(WURZEL)
    adresse = sub.normalisiere_adresse(str(daten.get("email") or ""))
    if not sub.ist_adresse(adresse):
        raise SystemExit("::error::Token ohne brauchbare Adresse.")

    # Die Domain-Allowlist wird HIER ausgewertet, nicht nur im Dienst: der
    # Dienst kann ausgetauscht werden, der Store nicht.
    erlaubte = [d for d in os.environ.get("ERLAUBTE_DOMAINS", "").split(",")
                if d.strip()]
    if not sub.erlaubt_nach_domainliste(adresse, erlaubte):
        _zahl("Bestaetigung", "abgewiesen (Domainliste)")
        return 0

    kennwert = sub.adress_kennwert(pepper, adresse)
    store = st.AboStore(Path(args.store), katalog)

    vorhanden = store.finde_ueber_kennwert(kennwert)
    if vorhanden and vorhanden.state == "active":
        # Zweimal geklickt. Kein Fehler und kein zweites Abo - der Nutzer
        # sieht auf beiden Seiten "Angemeldet", und das stimmt.
        _zahl("Bestaetigung", "bereits aktiv")
        return 0

    # Der Wortlaut, dem zugestimmt wurde. Er kommt aus dem TOKEN, nicht aus
    # der heutigen Datei: eine Behoerde fragt nach dem Text von damals.
    version = str(daten.get("consent_version") or "")
    fassung = rechtstexte.einwilligung(WURZEL, version)
    hash_im_token = str(daten.get("consent_hash") or "")
    if fassung is not None and fassung.hash != hash_im_token:
        # Der Text hat sich seit der Anmeldung geaendert. Der Nachweis
        # bleibt trotzdem gueltig - er belegt den Hash von DAMALS. Es
        # gehoert nur ins Protokoll, damit es niemanden ueberrascht.
        _zahl("Einwilligung", f"Fassung {version} hat sich seither geändert")

    abo = vorhanden or sub.Abo(id=sub.neue_id(), email=adresse)
    abo.email = adresse
    abo.email_hmac = kennwert
    abo.filter = lies_filtersatz(daten.get("filters") or {}, katalog)
    abo.consent = sub.Einwilligungsnachweis(
        text_version=version, text_hash=hash_im_token,
        ip_hmac=str(daten.get("ip_hmac") or ""),
        user_agent_hmac=str(daten.get("ua_hmac") or ""),
        confirm_token_id=args.token_id)
    abo.created_at = abo.created_at or _iso(daten.get("iat"))
    abo.confirmed_at = sub.jetzt()
    abo.state = "active"
    if not abo.consent.vollstaendig:
        raise SystemExit("::error::Einwilligungsnachweis unvollständig - "
                         "kein Abo angelegt.")
    store.setze(abo)
    store.speichern()
    _zahl("Bestaetigung", "aktiv")
    _zahl("Abos aktiv", len(store.aktive()))
    return 0


def _iso(iat) -> str:
    from datetime import datetime, timezone
    try:
        return datetime.fromtimestamp(float(iat), timezone.utc).replace(
            microsecond=0).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError):
        return sub.jetzt()


# --------------------------------------------------------- unsubscribe -----

def befehl_unsubscribe(args) -> int:
    """Widerruf: Zustand setzen, ADRESSE LOESCHEN, Kennwert behalten.

    Der Kennwert bleibt, weil sonst dieselbe Adresse beim naechsten
    Anmeldeversuch wieder angeschrieben wuerde - ein Widerruf, der nach vier
    Wochen von selbst verfaellt, ist keiner.
    """
    daten = _token(args.token_datei, tokens.ZWECK_ABMELDUNG,
                   10 * 365 * 24 * 3600)
    katalog = lade_katalog(WURZEL)
    store = st.AboStore(Path(args.store), katalog)

    abo = (store.finde(str(daten.get("sub_id") or ""))
           or store.finde_ueber_kennwert(str(daten.get("addr_hmac") or "")))
    if abo is None:
        # Schon abgemeldet oder nie da gewesen. Kein Fehler: der Nutzer hat
        # auf der Seite bereits "Abgemeldet" gelesen, und das stimmt.
        _zahl("Abmeldung", "kein Abo gefunden")
        return 0
    store.setze(abo.abgemeldet())
    store.speichern()
    _zahl("Abmeldung", "erledigt")
    _zahl("Abos aktiv", len(store.aktive()))
    return 0


# ---------------------------------------------------------------- main -----

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    unter = p.add_subparsers(dest="befehl", required=True)

    for name in ("doi", "confirm", "unsubscribe"):
        u = unter.add_parser(name)
        # Ueber eine DATEI, nicht ueber ein Argument: eine Kommandozeile
        # steht in der Prozessliste und im Actions-Log, und im Token steckt
        # die Adresse.
        u.add_argument("--token-datei", required=True)
        u.add_argument("--token-id", default="")
        u.add_argument("--store", default="store/subscribers.jsonl")
        if name == "doi":
            u.add_argument("--doi-log", default="store/doi_log.jsonl")
            u.add_argument("--confirm-url", default="")
            u.add_argument("--trocken", action="store_true")

    args = p.parse_args(argv)
    return {"doi": befehl_doi, "confirm": befehl_confirm,
            "unsubscribe": befehl_unsubscribe}[args.befehl](args)


if __name__ == "__main__":
    raise SystemExit(main())
