#!/usr/bin/env python3
"""Ein Testversand ueber die Brevo-HTTP-API. Gehoert zu mail_test.yml.

Bewusst ohne Projektimporte: dieses Skript wird zusammen mit dem Workflow
geloescht, sobald das Ergebnis in docs/mail-setup.md steht. Es darf deshalb
keine Abhaengigkeit sein, die jemand spaeter vermisst.

Es druckt keine Adresse - nur, an welches der beiden Postfaecher (Freemail
oder Firma) es gerade ging und was Brevo geantwortet hat.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.brevo.com/v3/smtp/email"
ABSENDER = {"name": "Telco Radar", "email": "antonio.fotiadis.francisco@gmail.com"}

TEXT = """Dies ist ein einmaliger Testversand fuer den Telco Radar.

Er enthaelt bewusst keinen Inhalt aus dem Wochenbericht. Geprueft wird nur
zweierlei: ob diese Nachricht ankommt, und wo sie landet.

Bitte einmal nachsehen:
  1. Posteingang oder Spam-Ordner?
  2. Kopfzeilen anzeigen und die Zeile "Authentication-Results" kopieren.

Danke.
"""


def senden(key: str, ziel: str, rolle: str) -> bool:
    nutzlast = {
        "sender": ABSENDER,
        "to": [{"email": ziel}],
        "subject": f"Telco Radar - Testversand ({rolle})",
        "textContent": TEXT,
        # Derselbe Header, den spaeter jede Ausgabe traegt: nur https, kein
        # mailto, kein List-Unsubscribe-Post. Wenn ein Gateway daran Anstoss
        # nimmt, soll es das JETZT tun und nicht bei der ersten echten
        # Ausgabe.
        "headers": {"List-Unsubscribe": "<https://telco-radar.onrender.com/newsletter.html>"},
    }
    anfrage = urllib.request.Request(
        API, data=json.dumps(nutzlast).encode("utf-8"),
        headers={"api-key": key, "content-type": "application/json",
                 "accept": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(anfrage, timeout=30) as antwort:
            koerper = json.loads(antwort.read().decode("utf-8") or "{}")
            print(f"  {rolle}: HTTP {antwort.status}, "
                  f"messageId={koerper.get('messageId', '?')}")
            return True
    except urllib.error.HTTPError as fehler:
        koerper = fehler.read().decode("utf-8", "replace")[:400]
        print(f"  {rolle}: HTTP {fehler.code} - {koerper}")
        # 401 ist der Fall, den man sonst stundenlang im Code sucht.
        if fehler.code == 401:
            print("  ::error::Key abgelehnt. Brevo-Keys verfallen nach 90 "
                  "Tagen ohne Nutzung (docs/mail-setup.md 3.2).")
        return False
    except OSError as fehler:
        print(f"  {rolle}: kein Kontakt zur API - {fehler}")
        return False


def main() -> int:
    key = os.environ.get("BREVO_API_KEY", "")
    ziele = [("Freemail", os.environ.get("FREEMAIL_TO", "")),
             ("Firma", os.environ.get("UNTERNEHMEN_TO", ""))]
    if not key or not all(z for _, z in ziele):
        print("::error::BREVO_API_KEY, FREEMAIL_TO und UNTERNEHMEN_TO noetig.")
        return 1
    print("Testversand ueber die Brevo-HTTP-API:")
    ergebnisse = [senden(key, ziel, rolle) for rolle, ziel in ziele]
    return 0 if all(ergebnisse) else 1


if __name__ == "__main__":
    sys.exit(main())
