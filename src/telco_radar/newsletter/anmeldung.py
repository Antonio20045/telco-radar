"""Anmelden, Bestaetigen, Abmelden direkt ueber Brevo (seit 11.10.2026).

Der Anmeldedienst auf Render ruft diese Funktionen; vorher lief jedes
Ereignis ueber zwei private Repos und einen Workflow. Die Regeln bleiben:

  * Ein Abo entsteht erst mit dem Klick auf den Bestaetigungslink, und erst
    dann liegt die Adresse bei Brevo.
  * Hoechstens eine Bestaetigungsmail je Adresse in `DOI_SPERRE_TAGE`. Die
    Sperre fragt Brevos Versandprotokoll (Schlagwort `DOI_SCHLAGWORT`) statt
    eines Zaehlers im Dienst: der ist nach jedem Einschlafen leer.
  * Abmelden loescht den Kontakt.
"""

from __future__ import annotations

import html
import logging
import urllib.parse
from datetime import UTC, datetime

from ..report.anbieter_farben import MAIL
from . import subscription as sub
from .brevo_kontakte import BrevoKontakte
from .config import NewsletterKatalog
from .filters import lies_filtersatz
from .transport import BrevoFehler, brevo_anfrage

log = logging.getLogger(__name__)

BREVO_MAIL = "https://api.brevo.com/v3/smtp/email"
BREVO_EREIGNISSE = "https://api.brevo.com/v3/smtp/statistics/events"
DOI_SCHLAGWORT = "telco-radar-doi"
DOI_SPERRE_TAGE = 1
BETREFF_DOI = "Bitte bestätigen: Telco Radar"


def bestaetigungsmail(bestaetigen: str, basis: str) -> tuple[str, str]:
    """HTML und Text der Bestaetigungsmail."""
    b = html.escape(bestaetigen, True)
    s = html.escape(basis, True)
    pa, flaeche, tinte = MAIL["papier"], MAIL["flaeche"], MAIL["tinte"]
    rot, grau = MAIL["rot"], MAIL["grau"]
    inhalt = f"""<!DOCTYPE html><html lang=de><body style="margin:0;background:{pa}">
<table role=presentation width="100%" cellpadding=0 cellspacing=0 border=0><tr>
<td align=center style="padding:28px 12px"><table role=presentation width=600
 cellpadding=0 cellspacing=0 border=0
 style="width:100%;max-width:600px;background:{flaeche};padding:26px 24px">
<tr><td style="font:700 24px/1.15 Georgia,serif;padding-bottom:14px;
border-bottom:3px solid {tinte}">Telco Radar</td></tr>
<tr><td style="font:400 15px/1.6 Georgia,serif;color:{tinte};padding-top:20px">
<p>Guten Tag,</p>
<p>bitte bestätigen Sie mit einem Klick, dass Sie den Telco Radar per E-Mail
bekommen möchten:</p>
<p><a href="{b}" style="color:{rot};font:700 15px Arial,sans-serif">Anmeldung
bestätigen &rsaquo;</a></p>
<p style="font-size:13px;color:{grau}">Der Link gilt 72 Stunden. <strong>Wenn
Sie das nicht waren, ignorieren Sie diese E-Mail — es passiert dann
nichts.</strong> Ohne Ihren Klick wird nichts gespeichert und es kommt keine
weitere Nachricht.</p>
<p style="font-size:13px;color:{grau}">Angefordert über das Anmeldeformular auf
{s}.</p>
</td></tr>
<tr><td style="padding-top:24px;border-top:3px solid {tinte};
font:400 11px/1.6 Arial,sans-serif;color:{grau}">
<a href="{s}/impressum.html" style="color:{grau}">Impressum</a> &middot;
<a href="{s}/datenschutz.html" style="color:{grau}">Datenschutzerklärung</a>
</td></tr></table></td></tr></table></body></html>"""
    text = (
        "TELCO RADAR\n===========\n\nGuten Tag,\n\n"
        "bitte bestätigen Sie mit einem Klick, dass Sie den Telco Radar per\n"
        f"E-Mail bekommen möchten:\n\n{bestaetigen}\n\nDer Link gilt 72 Stunden.\n\n"
        "Wenn Sie das nicht waren, ignorieren Sie diese E-Mail - es passiert\n"
        "dann nichts. Ohne Ihren Klick wird nichts gespeichert und es kommt\n"
        "keine weitere Nachricht.\n\n"
        f"Angefordert über das Anmeldeformular auf {basis}.\n\n"
        f"Impressum: {basis}/impressum.html\n"
        f"Datenschutzerklärung: {basis}/datenschutz.html\n"
    )
    return inhalt, text


def doi_kuerzlich(api_key: str, adresse: str, *, oeffner=None) -> bool:
    """Ging an diese Adresse in den letzten `DOI_SPERRE_TAGE` schon eine?"""
    abfrage = urllib.parse.urlencode(
        {
            "email": adresse,
            "tags": DOI_SCHLAGWORT,
            "event": "requests",
            "days": DOI_SPERRE_TAGE,
            "limit": 1,
        }
    )
    antwort = brevo_anfrage(
        api_key, "GET", f"{BREVO_EREIGNISSE}?{abfrage}", oeffner=oeffner
    )
    return bool(antwort.get("events"))


def doi_senden(
    api_key: str,
    *,
    adresse: str,
    absender: str,
    bestaetigen: str,
    basis: str,
    oeffner=None,
) -> None:
    """Die Bestaetigungsmail ueber Brevo. Wirft BrevoFehler."""
    inhalt, text = bestaetigungsmail(bestaetigen, basis)
    brevo_anfrage(
        api_key,
        "POST",
        BREVO_MAIL,
        {
            "sender": {"name": "Telco Radar", "email": absender},
            "to": [{"email": adresse}],
            "subject": BETREFF_DOI,
            "htmlContent": inhalt,
            "textContent": text,
            "tags": [DOI_SCHLAGWORT],
        },
        oeffner=oeffner,
    )


def abo_aus_bestaetigung(
    daten: dict,
    katalog: NewsletterKatalog,
    *,
    token_id: str,
    pepper: str,
    jetzt: datetime,
) -> sub.Abo:
    """Das aktive Abo aus dem gelesenen Bestaetigungstoken."""
    adresse = sub.normalisiere_adresse(str(daten.get("email") or ""))
    if not sub.ist_adresse(adresse):
        raise ValueError("Token ohne brauchbare Adresse")
    iat = daten.get("iat")
    angemeldet = (
        sub.zeitstempel(datetime.fromtimestamp(float(iat), UTC))
        if isinstance(iat, int | float)
        else ""
    )
    abo = sub.Abo(
        id=f"sub_{sub.adress_kennwert(pepper, adresse)[:20]}",
        email=adresse,
        email_hmac=sub.adress_kennwert(pepper, adresse),
        filter=lies_filtersatz(daten.get("filters") or {}, katalog),
        consent=sub.Einwilligungsnachweis(
            text_version=str(daten.get("consent_version") or ""),
            text_hash=str(daten.get("consent_hash") or ""),
            ip_hmac=str(daten.get("ip_hmac") or ""),
            user_agent_hmac=str(daten.get("ua_hmac") or ""),
            confirm_token_id=token_id,
        ),
        created_at=angemeldet,
        confirmed_at=sub.zeitstempel(jetzt),
        state="active",
    )
    if not abo.consent.vollstaendig:
        raise ValueError("Einwilligungsnachweis unvollstaendig")
    return abo


def abmelden(
    kontakte: BrevoKontakte, liste: int, abo_id: str, kennwert: str = ""
) -> bool:
    """Den Kontakt zu dieser Abo-ID (oder Kennwert) loeschen. False ohne Treffer."""
    adresse = kontakte.adresse_zu_id(liste, abo_id, kennwert)
    if not adresse:
        return False
    return kontakte.loeschen(adresse)


_LISTE: list[int] = []


def _kontakte(api_key: str) -> tuple[BrevoKontakte, int]:
    kontakte = BrevoKontakte(api_key)
    if not _LISTE:
        _LISTE.append(kontakte.einrichten())
    return kontakte, _LISTE[0]


def doi(api_key: str, adresse: str, *, absender: str, bestaetigen: str, basis: str):
    """Bestaetigungsmail, hoechstens eine je Adresse und Tag. False bei Ausfall."""
    try:
        if doi_kuerzlich(api_key, adresse):
            log.info("DOI gesperrt (eine je Tag)")
            return True
        doi_senden(
            api_key,
            adresse=adresse,
            absender=absender,
            bestaetigen=bestaetigen,
            basis=basis,
        )
    except BrevoFehler as fehler:
        log.error("DOI ueber Brevo gescheitert: HTTP %s", fehler.status)
        return False
    return True


def bestaetigen(api_key: str, daten: dict, katalog: NewsletterKatalog, **kw) -> bool:
    """Kontakt aus dem Bestaetigungstoken anlegen. False bei Ausfall."""
    try:
        abo = abo_aus_bestaetigung(daten, katalog, **kw)
        kontakte, liste = _kontakte(api_key)
        kontakte.speichern(abo, liste)
    except (ValueError, BrevoFehler) as fehler:
        log.error("Bestaetigung gescheitert: %s", type(fehler).__name__)
        return False
    return True


def abmelden_ueber_brevo(api_key: str, abo_id: str, kennwert: str) -> bool:
    """Kontakt loeschen; True auch, wenn es ihn nicht (mehr) gab. False bei Ausfall."""
    try:
        kontakte, liste = _kontakte(api_key)
        abmelden(kontakte, liste, abo_id, kennwert)
    except BrevoFehler as fehler:
        log.error("Abmeldung gescheitert: HTTP %s", fehler.status)
        return False
    return True


def sauberer_filter(roh: dict, katalog: NewsletterKatalog) -> dict:
    """Nur die bekannten Felder, nur die bekannten Formen.

    Ohne das reist alles mit, was jemand ins Formular-JSON schreibt - und
    landet signiert im Token und von dort im Store."""
    aus: dict = {}
    for feld in ("branches", "regions", "competitors", "categories"):
        aus[feld] = sorted(
            {str(w).strip() for w in (roh.get(feld) or []) if str(w).strip()}
        )[:50]
    stichwoerter = []
    for eintrag in (roh.get("keywords") or [])[: katalog.grenzen.max_stichwoerter]:
        if isinstance(eintrag, str):
            term, mode = eintrag, ""
        elif isinstance(eintrag, dict):
            term, mode = str(eintrag.get("term") or ""), str(eintrag.get("mode") or "")
        else:
            continue
        term = term.strip()[:60]
        if term:
            stichwoerter.append(
                {"term": term, "mode": mode if mode in ("word", "phrase") else ""}
            )
    aus["keywords"] = stichwoerter
    return aus


def antwortseite(titel: str, text: str, *, ziel: str = "") -> str:
    """Die Antwortseite des Dienstes im Look des Portals, ohne Stylesheet und
    ohne Skript: sie steht auch, wenn die Static Site nicht erreichbar ist."""
    m = MAIL
    weiter = (
        f'<p style="margin:32px 0 0"><a href="{html.escape(ziel, True)}" '
        f'style="color:{m["tinte"]};font-weight:500">Zum Portal &rsaquo;</a></p>'
        if ziel
        else ""
    )
    return (
        "<!DOCTYPE html><html lang=de><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(titel)}</title></head>"
        f"<body style='margin:0;background:{m['papier']};color:{m['text']};"
        "font:17px/1.6 system-ui,-apple-system,Segoe UI,Helvetica,Arial,sans-serif'>"
        "<main style='max-width:36em;margin:0 auto;padding:16vh 24px 12vh;"
        "text-align:center'>"
        f"<p style='margin:0;font-size:13px;font-weight:600;letter-spacing:.22em;"
        f"text-transform:uppercase;color:{m['rot']}'>Newsletter</p>"
        "<h1 style='margin:12px 0 0;padding:0 0 26px;"
        f"border-bottom:3px double {m['tinte']};"
        f"font:500 clamp(44px,9vw,84px)/1 Georgia,serif;"
        f"letter-spacing:-.02em;color:{m['tinte']}'>{html.escape(titel)}</h1>"
        "<p style='margin:24px 0 0;font:italic 22px/1.4 Georgia,serif'>"
        f"{html.escape(text)}</p>"
        f"{weiter}</main></body></html>"
    )
