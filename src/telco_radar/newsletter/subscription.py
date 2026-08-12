"""Ein Abonnement: was drinsteht, was gueltig ist, und wie gehasht wird.

**Alle Kennwerte sind HMAC-SHA256 mit geheimem Pepper, nie blankes SHA-256.**
Das ist keine Feinheit. Ein SHA-256 ueber eine E-Mail-Adresse ist per Brute
Force in Minuten umkehrbar - der Raum realer Adressen ist winzig gegenueber
dem Hashraum, und Wortlisten gibt es fertig. Dasselbe gilt fuer eine IPv4:
vier Milliarden Kandidaten sind auf einem Notebook eine Sache von Sekunden.
Ein blanker Hash waere hier also keine Pseudonymisierung, sondern eine
Formalitaet, die im Datenschutz-Kapitel gut aussieht und nichts schuetzt.

Der Pepper liegt als Secret, NICHT neben den Daten. Wer den verschluesselten
Store bekommt, aber nicht den Pepper, kann die Kennwerte nicht aufloesen.

Der zweite Punkt, der leicht falsch gebaut wird: **die Anmeldewerte reisen im
signierten Token mit.** Zum Zeitpunkt der Bestaetigung existiert die
urspruengliche Anfrage nicht mehr - der Signup-Dienst speichert ja nichts.
Wer IP- und Browser-Kennwert erst beim Bestaetigen bilden wollte, wuerde die
Werte des Klicks festhalten statt die der Anmeldung, und bei einem Klick vom
Telefon aus dem Mobilfunknetz stuende im Einwilligungsprotokoll etwas, das
mit der Einwilligung nichts zu tun hat.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from .config import FELD_JE_DIMENSION, NewsletterKatalog
from .filters import Filtersatz, Stichwort, lies_filtersatz, stichwort_fehler

# Bewusst grosszuegig und bewusst kein RFC-5322-Ungetuem: die einzige Pruefung,
# die wirklich zaehlt, ist die Bestaetigungsmail. Eine Adresse, die hier
# durchrutscht und nicht existiert, bekommt keine Mail und wird nie ein Abo.
# Eine gueltige Adresse, die ein zu strenges Muster abweist, ist dagegen ein
# verlorener Abonnent, der nicht weiss warum.
_ADRESSE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[A-Za-z]{2,}$")

ZUSTAENDE = ("pending", "active", "unsubscribed", "bounced")


def ist_adresse(wert: str) -> bool:
    wert = (wert or "").strip()
    return bool(wert) and len(wert) <= 254 and bool(_ADRESSE.match(wert))


def normalisiere_adresse(wert: str) -> str:
    """Kleingeschrieben und ohne Rand.

    NUR das - kein Entfernen von Punkten, kein Abschneiden hinter "+". Beides
    ist eine Gmail-Eigenheit und bei anderen Anbietern schlicht falsch: dort
    sind `a.b@` und `ab@` zwei verschiedene Postfaecher. Wer normalisiert, um
    Doppelanmeldungen zu erkennen, wuerde damit fremde Post zusammenlegen.
    """
    return (wert or "").strip().lower()


def kennwert(pepper: str, wert: str) -> str:
    """HMAC-SHA256 mit Pepper. Der einzige Weg, in diesem Paket zu hashen."""
    return hmac.new((pepper or "").encode("utf-8"),
                    (wert or "").encode("utf-8"), hashlib.sha256).hexdigest()


def adress_kennwert(pepper: str, adresse: str) -> str:
    """Der Kennwert, der eine Abmeldung ueberlebt.

    Nach dem Widerruf wird die Adresse geloescht, dieser Wert bleibt. Er
    beantwortet zwei Fragen, fuer die man sonst die Adresse braeuchte: "hat
    diese Adresse in den letzten 24 Stunden schon eine Bestaetigungsmail
    bekommen" (Mailbomben-Schutz) und "hat sich diese Adresse schon einmal
    abgemeldet" (dann nicht erneut anschreiben).
    """
    return kennwert(pepper, normalisiere_adresse(adresse))


def jetzt() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


@dataclass
class Einwilligungsnachweis:
    text_version: str = ""
    text_hash: str = ""
    ip_hmac: str = ""
    user_agent_hmac: str = ""
    confirm_token_id: str = ""

    def as_dict(self) -> dict:
        return {"text_version": self.text_version, "text_hash": self.text_hash,
                "ip_hmac": self.ip_hmac, "user_agent_hmac": self.user_agent_hmac,
                "confirm_token_id": self.confirm_token_id}

    @property
    def vollstaendig(self) -> bool:
        """Ohne Fassung und Hash ist der Nachweis wertlos.

        IP- und Browser-Kennwert duerfen fehlen (ein Klient ohne
        User-Agent-Kopfzeile ist kein Grund, eine Anmeldung zu verweigern) -
        der WORTLAUT darf es nicht. Er ist das, wonach eine Behoerde fragt.
        """
        return bool(self.text_version and self.text_hash)


@dataclass
class Abo:
    id: str
    email: str
    filter: Filtersatz = field(default_factory=Filtersatz)
    consent: Einwilligungsnachweis = field(default_factory=Einwilligungsnachweis)
    created_at: str = ""
    confirmed_at: str = ""
    state: str = "pending"
    cadence: str = "jeder_lauf"
    format: str = "kurz"
    email_hmac: str = ""
    bounce_hard: int = 0
    bounce_soft: int = 0
    bounce_last: str = ""

    @property
    def aktiv(self) -> bool:
        return self.state == "active" and bool(self.email)

    def abgemeldet(self, *, zeitpunkt: str = "") -> "Abo":
        """Widerruf: Zustand setzen und die ADRESSE LOESCHEN.

        Der Kennwert bleibt - ohne ihn wuerde dieselbe Adresse beim naechsten
        Anmeldeversuch wieder angeschrieben, und ein Widerruf, der nach vier
        Wochen von selbst verfaellt, ist keiner.
        """
        return replace(self, state="unsubscribed", email="",
                       confirmed_at=self.confirmed_at,
                       bounce_last=zeitpunkt or jetzt())


# ==================================================  lesen und schreiben  ==

def als_dict(abo: Abo) -> dict:
    """Die Form, die in `subscribers.jsonl` steht."""
    filters = {FELD_JE_DIMENSION[d]: list(abo.filter.werte(d))
               for d in FELD_JE_DIMENSION}
    filters["keywords"] = [{"term": s.term, "mode": s.mode}
                           for s in abo.filter.stichwoerter]
    return {
        "id": abo.id,
        "email": abo.email,
        "email_hmac": abo.email_hmac,
        "created_at": abo.created_at,
        "confirmed_at": abo.confirmed_at,
        "consent": abo.consent.as_dict(),
        "filters": filters,
        "cadence": abo.cadence,
        "format": abo.format,
        "state": abo.state,
        "bounce": {"hard": abo.bounce_hard, "soft": abo.bounce_soft,
                   "last": abo.bounce_last or None},
    }


def aus_dict(roh: dict, katalog: NewsletterKatalog) -> Abo:
    bounce = roh.get("bounce") or {}
    consent = roh.get("consent") or {}
    return Abo(
        id=str(roh.get("id") or ""),
        email=normalisiere_adresse(roh.get("email") or ""),
        email_hmac=str(roh.get("email_hmac") or ""),
        filter=lies_filtersatz(roh.get("filters") or {}, katalog),
        consent=Einwilligungsnachweis(
            text_version=str(consent.get("text_version") or ""),
            text_hash=str(consent.get("text_hash") or ""),
            ip_hmac=str(consent.get("ip_hmac") or ""),
            user_agent_hmac=str(consent.get("user_agent_hmac") or ""),
            confirm_token_id=str(consent.get("confirm_token_id") or "")),
        created_at=str(roh.get("created_at") or ""),
        confirmed_at=str(roh.get("confirmed_at") or ""),
        state=str(roh.get("state") or "pending"),
        cadence=str(roh.get("cadence") or "jeder_lauf"),
        format=str(roh.get("format") or "kurz"),
        bounce_hard=int(bounce.get("hard") or 0),
        bounce_soft=int(bounce.get("soft") or 0),
        bounce_last=str(bounce.get("last") or ""),
    )


def neue_id() -> str:
    return f"sub_{uuid.uuid4().hex[:20]}"


# =========================================================  Zulaessigkeit  ==

def pruefe_anmeldung(adresse: str, filter_roh: dict,
                     katalog: NewsletterKatalog) -> list[str]:
    """Alles, was an einer Anmeldung nicht stimmt - als lesbare Saetze.

    Gibt eine LISTE zurueck und nicht den ersten Fehler: wer drei Stichwoerter
    falsch eingetragen hat, soll das in einem Durchgang erfahren und nicht in
    dreien.
    """
    fehler: list[str] = []
    if not ist_adresse(adresse):
        fehler.append("Das ist keine gültige E-Mail-Adresse.")

    satz = lies_filtersatz(filter_roh or {}, katalog)
    for dimension in FELD_JE_DIMENSION:
        erlaubt = katalog.schluessel(dimension)
        unbekannt = [w for w in satz.werte(dimension) if w not in erlaubt]
        if unbekannt:
            fehler.append(f"Unbekannte Auswahl bei {dimension}: "
                          f"{', '.join(sorted(unbekannt))}.")

    roh_stichwoerter = (filter_roh or {}).get("keywords") or []
    if len(roh_stichwoerter) > katalog.grenzen.max_stichwoerter:
        fehler.append(f"Höchstens {katalog.grenzen.max_stichwoerter} "
                      f"Stichwörter, angegeben sind {len(roh_stichwoerter)}.")
    for stichwort in satz.stichwoerter:
        grund = stichwort_fehler(stichwort.term, katalog)
        if grund:
            fehler.append(f"Stichwort „{stichwort.term}“: {grund}")
    return fehler


def erlaubt_nach_domainliste(adresse: str, erlaubte_domains) -> bool:
    """Die Domain-Allowlist. Steht auf LEER und ist trotzdem gebaut.

    Festlegung 3 des Konzepts: Die Anmeldung ist offen fuer alle. Dass sich
    Telekom, O2 und 1&1 eintragen koennen, ist keine Panne, sondern die
    bewusst gewaehlte Funktion - die Seite ist ohnehin oeffentlich und die
    Mail nur Anreisser plus Link.

    Gebaut wird sie trotzdem, damit das Umschalten spaeter eine
    Konfigurationszeile ist und kein Umbau. **Leer heisst hier "alle
    erlaubt"** - dieselbe Regel wie bei den Filtern, damit niemand zwei
    gegensaetzliche Bedeutungen von "leer" im Kopf behalten muss.
    """
    domains = [d.strip().lower().lstrip("@") for d in (erlaubte_domains or [])
               if str(d).strip()]
    if not domains:
        return True
    domain = normalisiere_adresse(adresse).rpartition("@")[2]
    # Subdomains zaehlen mit: wer "vodafone.de" erlaubt, meint auch
    # "mail.vodafone.de" - aber NICHT "vodafone.de.beispiel.com".
    return any(domain == d or domain.endswith("." + d) for d in domains)
