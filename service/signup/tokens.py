"""Signierte Token - der Kniff, mit dem dieser Dienst nichts speichern muss.

Zwischen Anmeldung und Bestaetigung wird **nichts** abgelegt. Alle Angaben
stecken signiert im Bestaetigungslink: Adresse, Filter, Fassung des
Einwilligungstextes, Zeitstempel und die gepfefferten Kennwerte von IP und
Browser. Wer nie bestaetigt, hinterlaesst im Dienst keine Daten - die Frage
nach der Loeschfrist fuer unbestaetigte Anmeldungen erledigt sich damit von
selbst, und Render Free hat ohnehin kein Dateisystem, das etwas ueberlebt.

**IP- und Browser-Kennwert MUESSEN mitreisen.** Zum Zeitpunkt der
Bestaetigung existiert die Anmeldeanfrage nicht mehr. Wer sie erst beim
Bestaetigen bildet, haelt die Werte des KLICKS fest statt die der
Einwilligung - und bei einem Klick vom Telefon aus dem Mobilfunknetz steht
im Einwilligungsprotokoll etwas, das mit der Einwilligung nichts zu tun hat.

Drei Eigenschaften, die alle drei noetig sind:

  * **HMAC-SHA256 ueber die Nutzlast**, nicht ueber eine Zusammenfassung.
    Wer den Dienst uebernimmt, kann keine bestehende Liste auslesen - aber
    er koennte gueltige Bestaetigungstoken faelschen. Deshalb zusaetzlich
    die Rechteeinschraenkung des GitHub-Tokens (siehe app.py).
  * **Ablauf im signierten Teil.** Ein Ablaufdatum neben der Signatur waere
    frei aenderbar.
  * **Vergleich in konstanter Zeit** (`hmac.compare_digest`). Ein
    zeichenweiser Vergleich verraet ueber die Laufzeit, wie viele Zeichen
    stimmen - das ist bei einem oeffentlich erreichbaren Endpunkt keine
    Theorie.

Kodiert wird base64url OHNE Polsterung: das Token steht in einem
PFADSEGMENT, und "=" waere dort zwar zulaessig, aber jeder zweite
Mailclient und jedes zweite Gateway macht daraus etwas anderes.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

# Getrennte Zwecke, getrennte Schluesselableitung. Ohne das
# Zweck-Praefix waere eine Nonce aus `/form-token` ein gueltiges
# Bestaetigungstoken - dieselbe Signatur, dieselbe Nutzlastform, und der
# Angreifer braeuchte den Schluessel gar nicht.
ZWECK_NONCE = "nonce"
ZWECK_BESTAETIGUNG = "confirm"
ZWECK_ABMELDUNG = "unsubscribe"

# 72 Stunden fuer den Bestaetigungslink. Kuerzer waere unhoeflich (jemand
# meldet sich Freitagabend an), laenger macht ein abgefangenes Token
# unnoetig lange brauchbar.
TTL_BESTAETIGUNG = 72 * 3600
# Die Nonce des Formulars: mindestens zwei Sekunden alt (schneller fuellt
# kein Mensch ein Formular aus) und hoechstens zwei Stunden.
NONCE_MIN = 2
NONCE_MAX = 2 * 3600


class TokenFehler(Exception):
    """Ungueltig, abgelaufen oder fuer einen anderen Zweck ausgestellt.

    EINE Fehlerklasse fuer alle drei Faelle, und die Meldung nach aussen ist
    immer dieselbe: ein Aufrufer, der erfaehrt, ob sein Token nur abgelaufen
    oder von vornherein falsch war, erfaehrt zu viel.
    """


def _b64(roh: bytes) -> str:
    return base64.urlsafe_b64encode(roh).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    fehlend = -len(text) % 4
    return base64.urlsafe_b64decode(text + "=" * fehlend)


def _signatur(key: str, zweck: str, koerper: bytes) -> str:
    # Der Zweck geht in die SIGNATUR ein, nicht nur in die Nutzlast: sonst
    # liesse sich ein gueltiges Token durch Umschreiben eines Feldes fuer
    # einen anderen Endpunkt verwenden.
    nachricht = zweck.encode("ascii") + b"." + koerper
    return _b64(hmac.new(key.encode("utf-8"), nachricht,
                         hashlib.sha256).digest())


def schreibe(key: str, zweck: str, daten: dict, *, jetzt: float | None = None) -> str:
    """`<nutzlast>.<signatur>` - beides base64url ohne Polsterung."""
    nutzlast = dict(daten, iat=int(jetzt if jetzt is not None else time.time()))
    koerper = json.dumps(nutzlast, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
    return f"{_b64(koerper)}.{_signatur(key, zweck, koerper)}"


def lies(key: str, zweck: str, token: str, *, max_alter: int,
         min_alter: int = 0, jetzt: float | None = None) -> dict:
    """Signatur und Alter pruefen, dann die Nutzlast zurueckgeben."""
    if not token or token.count(".") != 1:
        raise TokenFehler("Form")
    roh, signatur = token.split(".")
    try:
        koerper = _unb64(roh)
    except (ValueError, TypeError) as fehler:
        raise TokenFehler("Kodierung") from fehler
    if not hmac.compare_digest(signatur, _signatur(key, zweck, koerper)):
        raise TokenFehler("Signatur")
    try:
        daten = json.loads(koerper.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as fehler:
        raise TokenFehler("Nutzlast") from fehler
    if not isinstance(daten, dict):
        raise TokenFehler("Nutzlast")
    alter = (jetzt if jetzt is not None else time.time()) - float(daten.get("iat") or 0)
    if alter > max_alter:
        raise TokenFehler("abgelaufen")
    # Eine Nutzlast aus der Zukunft ist entweder eine verstellte Uhr oder ein
    # Versuch, den Ablauf auszuhebeln. Eine Minute Toleranz fuer den ersten
    # Fall, mehr nicht.
    if alter < -60:
        raise TokenFehler("Zukunft")
    if alter < min_alter:
        raise TokenFehler("zu frisch")
    return daten


def token_id(token: str) -> str:
    """Eine kurze Kennung des Tokens fuer das Einwilligungsprotokoll.

    Der Nachweis soll belegen, WELCHER Bestaetigungslink geklickt wurde,
    ohne den Link selbst aufzubewahren - mit ihm koennte man die Bestaetigung
    wiederholen."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
