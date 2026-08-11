"""Der Versandweg - hinter einer Schnittstelle, damit er austauschbar bleibt.

Zwei Umsetzungen: **Brevo ueber die HTTP-API** und ein **Trockenlauf**, der
alles rechnet und nichts verschickt. **Kein SMTP**, auch nicht als Rueckfall.

Warum HTTP und nicht SMTP: Render Free sperrt ausgehend die Ports 25, 465 und
587, es braeuchte ein App-Passwort mit allem, was daran haengt, und der
Versandcode waere Verbindungsverwaltung statt eines `post`. Bounces holt man
sich ueber die Events-API, statt ein Postfach per IMAP zu durchsuchen. Der
Signup-Dienst *koennte* ueber HTTPS technisch senden - er tut es trotzdem
nicht: der API-Key soll nicht auf einer oeffentlich erreichbaren Instanz
liegen.

DIE ZWEI DINGE, DIE HIER RICHTIG SEIN MUESSEN:

1. **Die Message-ID kommt zurueck.** `bounce_sync` ordnet ihre Ereignisse
   darueber zu. Ohne sie ist die Bounce-Erkennung blind, und das faellt erst
   auf, wenn die Absenderreputation schon gelitten hat.
2. **4xx und 429/5xx sind NICHT dasselbe.** Ein 400 ("invalid recipient")
   wird beim vierten Versuch nicht gueltiger - der Empfaenger gehoert
   markiert. Ein 429 oder 503 ist voruebergehend und gehoert wiederholt. Wer
   beides gleich behandelt, verbrennt entweder Tageskontingent an tote
   Adressen oder wirft lebende weg.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .render import Nachricht

log = logging.getLogger(__name__)

BREVO_API = "https://api.brevo.com/v3/smtp/email"
BREVO_EVENTS = "https://api.brevo.com/v3/smtp/statistics/events"


@dataclass
class Ergebnis:
    """Was aus einem Zustellversuch geworden ist."""
    ok: bool
    message_id: str = ""
    status: int = 0
    fehler: str = ""
    dauerhaft: bool = False        # True = nicht wiederholen, Empfaenger markieren

    @property
    def wiederholbar(self) -> bool:
        return not self.ok and not self.dauerhaft


class Transport:
    """Die Schnittstelle. `send(nachricht, an) -> Ergebnis`."""

    def send(self, nachricht: Nachricht, an: str) -> Ergebnis:  # pragma: no cover
        raise NotImplementedError


@dataclass
class Trockenlauf(Transport):
    """Rechnet alles, verschickt nichts. Fuer Tests und `dry_run`.

    Merkt sich, WAS gegangen waere - der Trockenlauf ist die Fassung, die man
    sich vor dem ersten echten Versand ansieht, und dafuer muss man
    hineinsehen koennen.
    """
    versendet: list[tuple[str, Nachricht]] = field(default_factory=list)

    def send(self, nachricht: Nachricht, an: str) -> Ergebnis:
        self.versendet.append((an, nachricht))
        # Eine Kennung, die wie eine echte aussieht, aber erkennbar keine
        # ist: ein Trockenlauf darf im Sendeprotokoll nie mit einem echten
        # Versand verwechselt werden.
        return Ergebnis(ok=True, message_id=f"trocken-{len(self.versendet)}")


@dataclass
class BrevoTransport(Transport):
    """Der echte Weg. Ein `POST` je Empfaenger.

    Bewusst EIN Empfaenger je Aufruf und keine Sammelzustellung: bei einer
    Sammelzustellung stehen alle Adressen in einer Nachricht, die
    Abmelde-URL kann nicht personalisiert werden, und ein Fehler betrifft
    die ganze Gruppe statt einer Adresse.
    """
    api_key: str
    absender_name: str = "Telco Radar"
    absender_adresse: str = ""
    timeout: int = 30
    versuche: int = 3

    def _nutzlast(self, nachricht: Nachricht, an: str) -> dict:
        return {
            "sender": {"name": self.absender_name,
                       "email": self.absender_adresse},
            "to": [{"email": an}],
            "subject": nachricht.betreff,
            "htmlContent": nachricht.html,
            "textContent": nachricht.text,
            "headers": dict(nachricht.headers),
        }

    def send(self, nachricht: Nachricht, an: str) -> Ergebnis:
        letzte = Ergebnis(ok=False, fehler="kein Versuch")
        for versuch in range(1, self.versuche + 1):
            letzte = self._einmal(nachricht, an)
            if letzte.ok or letzte.dauerhaft:
                return letzte
            if versuch < self.versuche:
                # Rueckwaerts wachsende Wartezeit. Bei 429 ist die Gegenseite
                # ueberlastet oder das Kontingent erschoepft - schnelles
                # Nachfassen macht beides schlimmer.
                time.sleep(min(2 ** versuch, 16))
        return letzte

    def _einmal(self, nachricht: Nachricht, an: str) -> Ergebnis:
        anfrage = urllib.request.Request(
            BREVO_API,
            data=json.dumps(self._nutzlast(nachricht, an)).encode("utf-8"),
            headers={"api-key": self.api_key,
                     "content-type": "application/json",
                     "accept": "application/json"},
            method="POST")
        try:
            with urllib.request.urlopen(anfrage, timeout=self.timeout) as antwort:
                koerper = json.loads(antwort.read().decode("utf-8") or "{}")
                return Ergebnis(ok=True, status=antwort.status,
                                message_id=str(koerper.get("messageId") or ""))
        except urllib.error.HTTPError as fehler:
            text = fehler.read().decode("utf-8", "replace")[:300]
            # 429 ist die Ratengrenze und voruebergehend, 5xx ebenso. Alles
            # andere im 4xx-Bereich ist eine Aussage ueber DIESE Anfrage und
            # wird beim vierten Versuch nicht wahrer.
            dauerhaft = 400 <= fehler.code < 500 and fehler.code != 429
            if fehler.code == 401:
                text += (" | Erste Ursache: Brevo-Keys verfallen nach 90 "
                         "Tagen ohne Nutzung (docs/mail-setup.md 3.2).")
            # Im Log steht der Code und der Text der API - NIE die Adresse.
            log.warning("Brevo antwortet HTTP %s (%s)", fehler.code,
                        "dauerhaft" if dauerhaft else "wiederholbar")
            return Ergebnis(ok=False, status=fehler.code, fehler=text,
                            dauerhaft=dauerhaft)
        except (OSError, json.JSONDecodeError) as fehler:
            log.warning("Brevo nicht erreichbar: %s", type(fehler).__name__)
            return Ergebnis(ok=False, fehler=f"{type(fehler).__name__}: {fehler}")


def hole_ereignisse(api_key: str, *, seit: str = "", limit: int = 500,
                    oeffner=None) -> list[dict]:
    """Die Bounce- und Beschwerde-Ereignisse. Grundlage von `bounce_sync`.

    `seit` ist ein ISO-Datum; Brevo will `startDate=YYYY-MM-DD`. Der zuletzt
    verarbeitete Zeitpunkt wird vom Aufrufer festgehalten, damit Ereignisse
    nicht doppelt laufen - ein zweimal gezaehlter Soft Bounce schaltet eine
    lebende Adresse ab.
    """
    ziel = f"{BREVO_EVENTS}?limit={int(limit)}"
    if seit:
        ziel += f"&startDate={seit}"
    anfrage = urllib.request.Request(
        ziel, headers={"api-key": api_key, "accept": "application/json"})
    oeffnen = oeffner or urllib.request.urlopen
    try:
        with oeffnen(anfrage, timeout=30) as antwort:
            daten = json.loads(antwort.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as fehler:
        log.error("Events-API antwortet HTTP %s", fehler.code)
        return []
    except (OSError, json.JSONDecodeError) as fehler:
        log.error("Events-API nicht erreichbar: %s", type(fehler).__name__)
        return []
    return list(daten.get("events") or [])
