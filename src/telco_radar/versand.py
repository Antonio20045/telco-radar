"""Push statt Pull: der Wochendigest per Mail und die Ausnahme per Teams.

Warum das die wichtigste fehlende Funktion war
----------------------------------------------
Alles an diesem Portal ist Pull. Wer nicht von selbst auf die Seite geht,
erfaehrt nichts - und das ist die mit Abstand haeufigste Todesursache
interner Intelligence-Programme. Ein Bericht, den niemand aufschlaegt, ist
kein Bericht.

Zwei Kanaele mit zwei verschiedenen Aufgaben
--------------------------------------------
**Mail, feste Kadenz, fester Wochentag.** Sie ist das Primaerformat: planbar,
weiterleitbar an Fuehrungskraefte, verschwindet nicht im Chatverlauf. Inhalt
ist der Zwei-Minuten-Pfad (analyze/ctm.py) und sonst nichts, plus der Link auf
die Ausgabe. Nicht der Wochenbericht - wer ihn lesen will, klickt.

**Teams nur fuer die Ausnahme.** Die Schwelle ist bewusst so hoch gesetzt,
dass hoechstens ein bis zwei Meldungen im Monat durchkommen: Stufe 3
(direkter Portfoliobezug) UND Prioritaet 5. Bei einem taeglichen Lauf mit
stark schwankenden Meldungszahlen (642 am 6.8., 124 am 4.8.) waere jeder
niedrigere Schwellenwert innerhalb von zwei Wochen stummgeschaltet - und ein
stummgeschalteter Kanal ist schlimmer als keiner, weil er den Eindruck von
Zustellung erweckt.

Was hier ausdruecklich NICHT passiert: jeden Lauf verschicken.

Zustellgedaechtnis
------------------
`data/state/versand.json` merkt sich, was schon hinaus ist. Ohne das schickt
ein zweiter Lauf am selben Tag dieselbe Mail noch einmal, und eine
Wiederholung ist bei Push teurer als bei Pull: sie kostet nicht einen Blick,
sondern das Vertrauen in den Kanal.
"""
from __future__ import annotations

import json
import logging
import os
import smtplib
import ssl
from datetime import date, datetime
from email.message import EmailMessage
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

SITE_URL = "https://telco-radar.onrender.com"

# Montag=0 ... Sonntag=6. Montagfrueh ist der Zeitpunkt, an dem jemand die
# Woche plant - eine Freitagsmail liest niemand mehr.
STANDARD_WOCHENTAG = 0

# Die Ausnahme-Schwelle fuer Teams. Beide Bedingungen, nicht eine.
TEAMS_CTM = 3
TEAMS_PRIORITAET = 5


class VersandFehler(RuntimeError):
    """Zustellung fehlgeschlagen. Bewusst eine eigene Klasse: der Aufrufer
    darf sie schlucken (ein Lauf ist nicht deshalb gescheitert, weil der
    Mailserver nicht antwortet), muss sie aber unterscheiden koennen."""


# --------------------------------------------------------------- Gedaechtnis

class Zustellbuch:
    """Was schon hinaus ist - je Kanal und je Ausgabe."""

    def __init__(self, pfad: Path):
        self.pfad = pfad
        self.daten: dict = {"mail": {}, "teams": {}}
        if pfad.exists():
            try:
                self.daten.update(json.loads(pfad.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                log.warning("versand.json unlesbar - beginne mit leerem "
                            "Zustellbuch")

    def schon_raus(self, kanal: str, schluessel: str) -> bool:
        return schluessel in (self.daten.get(kanal) or {})

    def merke(self, kanal: str, schluessel: str, notiz: str = "") -> None:
        self.daten.setdefault(kanal, {})[schluessel] = {
            "gesendet": datetime.now().isoformat(timespec="seconds"),
            "notiz": notiz}
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        self.pfad.write_text(
            json.dumps(self.daten, ensure_ascii=False, indent=1),
            encoding="utf-8")


# ------------------------------------------------------------------ Inhalte

def _highlights(report: dict) -> list[dict]:
    return [h for r in (report.get("regions") or {}).values()
            for h in (r.get("highlights") or [])]


def zwei_minuten_zeilen(report: dict, max_zeilen: int = 5) -> list[dict]:
    """Dieselbe Auswahl wie auf der Startseite - aus derselben Funktion.

    Bewusst kein zweiter Auswahlweg: eine Mail, die etwas anderes hervorhebt
    als die Seite, auf die sie verlinkt, ist schlimmer als keine Mail.
    """
    from .analyze.ctm import zwei_minuten
    return zwei_minuten(_highlights(report), max_zeilen=max_zeilen)


def ausnahmen(report: dict) -> list[dict]:
    """Was eine Sofortmeldung rechtfertigt - beide Bedingungen zusammen."""
    return [h for h in _highlights(report)
            if int(h.get("ctm_bezug") or 0) >= TEAMS_CTM
            and int(h.get("relevance") or 0) >= TEAMS_PRIORITAET]


def _datum_de(iso: str) -> str:
    monate = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
              "August", "September", "Oktober", "November", "Dezember"]
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{d.day}. {monate[d.month - 1]} {d.year}"


def baue_mail(report: dict, site_url: str = SITE_URL) -> tuple[str, str, str]:
    """(Betreff, Textfassung, HTML-Fassung).

    Die Textfassung ist keine Pflichtuebung: sie ist das, was in der Vorschau
    eines Mailprogramms und auf einer Uhr steht. Wer nur HTML schickt, schickt
    dort "Diese Nachricht kann nicht angezeigt werden".
    """
    datum = _datum_de(report.get("date") or "")
    zeilen = zwei_minuten_zeilen(report)
    stats = report.get("stats") or {}

    betreff = (f"Telco Radar, {datum}: "
               + (f"{len(zeilen)} Sache{'n' if len(zeilen) != 1 else ''} für "
                  "das Portfolio" if zeilen else "diese Woche nichts Direktes"))

    kopf = (f"Telco Radar – Ausgabe vom {datum}\n"
            f"{stats.get('events', stats.get('new', 0))} Ereignisse aus "
            f"{stats.get('sources_total', 0)} Quellen.\n\n")
    if zeilen:
        rumpf = "IN ZWEI MINUTEN\n\n" + "\n\n".join(
            f"{i}. {h.get('ctm_satz')}\n"
            f"   {h.get('operator') or h.get('source') or ''} – {h.get('url')}"
            for i, h in enumerate(zeilen, 1))
    else:
        # Ein Befund, keine Luecke - und er wird als Befund geschrieben.
        rumpf = ("Diese Woche gab es keine Meldung mit direktem Bezug zum "
                 "eigenen Portfolio. Die Ausgabe steht trotzdem online.")
    text = kopf + rumpf + f"\n\nGanze Ausgabe: {site_url}/\n"

    def esc(s: str) -> str:
        return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;"))

    if zeilen:
        punkte = "".join(
            f'<li style="margin:0 0 16px"><div style="font-size:16px;'
            f'line-height:1.45;color:#14120f">{esc(h.get("ctm_satz"))}</div>'
            f'<div style="font-size:12px;color:#8a8479;margin-top:4px">'
            f'{esc(h.get("operator") or h.get("source"))} · '
            f'<a href="{esc(h.get("url"))}" style="color:#5e594f">'
            f'{esc(h.get("headline") or h.get("title"))}</a></div></li>'
            for h in zeilen)
        inhalt = (f'<p style="font-size:11px;letter-spacing:.09em;'
                  f'text-transform:uppercase;color:#8a8479;margin:0 0 10px">'
                  f'In zwei Minuten</p><ol style="padding-left:18px;margin:0">'
                  f'{punkte}</ol>')
    else:
        inhalt = ('<p style="font-size:16px;color:#33302a;margin:0">Diese '
                  'Woche gab es keine Meldung mit direktem Bezug zum eigenen '
                  'Portfolio.</p>')

    html = (
        '<div style="font-family:Georgia,\'Source Serif 4\',serif;'
        'max-width:620px;margin:0 auto;padding:24px;background:#f6f4ee">'
        f'<div style="border-top:3px solid #14120f;padding-top:10px;'
        f'margin-bottom:22px"><div style="font-size:22px;font-weight:700">'
        f'Telco Radar</div><div style="font-size:11px;color:#8a8479;'
        f'letter-spacing:.06em">Ausgabe vom {esc(datum)}</div></div>'
        f'{inhalt}'
        f'<p style="margin:26px 0 0;border-top:1px solid #e6e2d8;'
        f'padding-top:12px;font-size:12px">'
        f'<a href="{esc(site_url)}/" style="color:#e60000">Ganze Ausgabe '
        f'öffnen</a></p></div>')
    return betreff, text, html


def baue_teams_karte(report: dict, treffer: list[dict],
                     site_url: str = SITE_URL) -> dict:
    """Die Nutzlast fuer einen eingehenden Teams-Webhook (MessageCard).

    Bewusst das alte, schlichte Format: es wird von jedem Connector
    angenommen und braucht kein Schema-Handshake.
    """
    zeilen = [{"name": (h.get("operator") or h.get("source") or "")[:60],
               "value": (h.get("ctm_satz") or h.get("headline")
                         or h.get("title") or "")[:300]}
              for h in treffer[:3]]
    return {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "themeColor": "E60000",
        "summary": "Telco Radar: direkt portfoliorelevante Meldung",
        "title": "Direkt für das Portfolio",
        "sections": [{"facts": zeilen, "markdown": False}],
        "potentialAction": [{
            "@type": "OpenUri", "name": "Ausgabe öffnen",
            "targets": [{"os": "default", "uri": f"{site_url}/"}]}],
    }


# ------------------------------------------------------------------ Zustellen

def sende_mail(betreff: str, text: str, html: str, *, trocken: bool = False
               ) -> str:
    """Verschickt ueber SMTP. Zugangsdaten kommen aus der Umgebung.

    Fehlt eine davon, wird NICHT verschickt und auch nicht so getan: der
    Aufrufer bekommt eine Meldung, die im Laufprotokoll steht. Ein stiller
    Nichtversand ist der Fehler, den man erst nach Wochen bemerkt.
    """
    host = os.environ.get("SMTP_HOST", "")
    absender = os.environ.get("MAIL_FROM", "")
    empfaenger = [e.strip() for e in
                  os.environ.get("MAIL_TO", "").split(",") if e.strip()]
    if not (host and absender and empfaenger):
        raise VersandFehler(
            "SMTP_HOST, MAIL_FROM oder MAIL_TO fehlen - keine Mail verschickt")

    nachricht = EmailMessage()
    nachricht["Subject"] = betreff
    nachricht["From"] = absender
    nachricht["To"] = ", ".join(empfaenger)
    nachricht.set_content(text)
    nachricht.add_alternative(html, subtype="html")

    if trocken:
        return f"trocken: an {len(empfaenger)} Empfänger"

    port = int(os.environ.get("SMTP_PORT", "587") or 587)
    benutzer = os.environ.get("SMTP_USER", "")
    passwort = os.environ.get("SMTP_PASSWORD", "")
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=30,
                                      context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(host, port, timeout=30)
        with server:
            if port != 465:
                server.starttls(context=ssl.create_default_context())
            if benutzer:
                server.login(benutzer, passwort)
            server.send_message(nachricht)
    except (OSError, smtplib.SMTPException) as exc:
        raise VersandFehler(f"SMTP: {exc}") from exc
    return f"an {len(empfaenger)} Empfänger"


def sende_teams(karte: dict, *, trocken: bool = False) -> str:
    webhook = os.environ.get("TEAMS_WEBHOOK", "")
    if not webhook:
        raise VersandFehler("TEAMS_WEBHOOK fehlt - keine Sofortmeldung")
    if trocken:
        return "trocken"
    try:
        antwort = httpx.post(webhook, json=karte, timeout=20)
        antwort.raise_for_status()
    except httpx.HTTPError as exc:
        raise VersandFehler(f"Teams: {exc}") from exc
    return "zugestellt"


# ------------------------------------------------------------------ Steuerung

def ist_versandtag(heute: date, wochentag: int) -> bool:
    return heute.weekday() == int(wochentag)


def versende(root: Path, report: dict, settings: dict, *,
             trocken: bool = False, erzwinge: bool = False) -> dict:
    """Der eine Einstiegspunkt. Liefert die Bilanz fuers Laufprotokoll.

    `erzwinge` uebergeht Wochentag und Zustellgedaechtnis - fuer den ersten
    Testversand, nicht fuer den Betrieb.
    """
    versand_cfg = dict(settings.get("versand") or {})
    bilanz: dict = {"mail": "aus", "teams": "aus"}
    buch = Zustellbuch(Path(root) / "data" / "state" / "versand.json")
    ausgabe = str(report.get("date") or date.today().isoformat())
    site_url = str(versand_cfg.get("site_url") or SITE_URL)

    # ---- Mail: feste Kadenz.
    if versand_cfg.get("mail_aktiv", True):
        wochentag = int(versand_cfg.get("wochentag", STANDARD_WOCHENTAG))
        try:
            heute = date.fromisoformat(ausgabe)
        except ValueError:
            heute = date.today()
        if not erzwinge and not ist_versandtag(heute, wochentag):
            bilanz["mail"] = f"kein Versandtag (Wochentag {wochentag})"
        elif not erzwinge and buch.schon_raus("mail", ausgabe):
            bilanz["mail"] = "schon verschickt"
        else:
            betreff, text, html = baue_mail(report, site_url)
            try:
                bilanz["mail"] = sende_mail(betreff, text, html, trocken=trocken)
                if not trocken:
                    buch.merke("mail", ausgabe, betreff)
            except VersandFehler as exc:
                bilanz["mail"] = f"FEHLER: {exc}"
                log.error("Mailversand: %s", exc)

    # ---- Teams: nur die Ausnahme, und jede Meldung genau einmal.
    if versand_cfg.get("teams_aktiv", True):
        treffer = [h for h in ausnahmen(report)
                   if erzwinge or not buch.schon_raus("teams", h.get("url", ""))]
        if not treffer:
            bilanz["teams"] = "keine Ausnahme"
        else:
            try:
                bilanz["teams"] = (
                    f"{sende_teams(baue_teams_karte(report, treffer, site_url), trocken=trocken)}"
                    f" ({len(treffer)} Meldung(en))")
                if not trocken:
                    for h in treffer:
                        buch.merke("teams", h.get("url", ""),
                                   h.get("headline") or h.get("title") or "")
            except VersandFehler as exc:
                bilanz["teams"] = f"FEHLER: {exc}"
                log.error("Teams-Sofortmeldung: %s", exc)

    log.info("Versand: Mail %s | Teams %s", bilanz["mail"], bilanz["teams"])
    return bilanz


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys
    from .config import load_config

    p = argparse.ArgumentParser(
        description="Wochendigest per Mail, Ausnahmen per Teams")
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--trocken", action="store_true",
                   help="baut alles, verschickt nichts")
    p.add_argument("--erzwinge", action="store_true",
                   help="ohne Ruecksicht auf Wochentag und Zustellbuch")
    p.add_argument("--zeige", action="store_true",
                   help="die Textfassung auf die Konsole")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    root = args.root.resolve()
    berichte = sorted((root / "data" / "reports").glob("*.json"))
    if not berichte:
        print("Kein Bericht gefunden.", file=sys.stderr)
        return 1
    report = json.loads(berichte[-1].read_text(encoding="utf-8"))
    if args.zeige:
        print(baue_mail(report)[1])
    bilanz = versende(root, report, load_config(root).settings,
                      trocken=args.trocken, erzwinge=args.erzwinge)
    print(json.dumps(bilanz, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
