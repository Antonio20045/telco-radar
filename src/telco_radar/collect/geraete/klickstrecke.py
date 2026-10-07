"""Bestellstrecke: welcher Weiter-Knopf erlaubt ist und wo die Strecke endet.

Die Folgeseite der Erkundung (``klickfolgeseite``) und der Weiter-Schritt der
Klick-Karte (``klickweiter``) klicken genau einen Knopf in die Bestellstrecke. Erlaubt
ist er nur als ``a`` oder ``button`` (oder mit dieser Rolle), ohne neues Fenster und
ohne Kauf-, Kassen- oder Anmeldewort (``KAUFWORT``); ``kein_weiter`` nennt den Mangel.
``streckenende`` erkennt Anmeldung, Checkout oder Zahlung an Host oder Pfad der Adresse
oder an sichtbaren Feldern der Seite (``FELDER_JS``: Passwort-, Karten- oder IBAN-Feld,
Knopf „zahlungspflichtig bestellen“). Dieses Modul ruft kein Netz.
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urldefrag, urlsplit

KNOPF_TAGS = frozenset({"a", "button"})
KNOPF_ROLLEN = frozenset({"button", "link"})
NEUES_FENSTER = "_blank"
WEBSCHEMATA = frozenset({"http", "https"})
KAUFWORT = re.compile(
    r"kaufen|bestell|kasse|bezahl|anmeld|einlogg|login|registrier|checkout", re.I
)
_RAND = r"(?<![a-z0-9])(?:{})(?![a-z0-9])"
STRECKENENDE = {
    "Anmeldung": re.compile(
        _RAND.format(
            "login|log-in|signin|sign-in|anmelden|anmeldung|einloggen"
            "|authentifizierung|auth"
        ),
        re.I,
    ),
    "Checkout": re.compile(
        _RAND.format(
            "checkout|check-out|kasse|bestellabschluss|bestelluebersicht"
            "|bestellübersicht"
        ),
        re.I,
    ),
    "Zahlung": re.compile(
        _RAND.format("payment|zahlung|zahlungsart|zahlungsdaten|bezahlen|bezahlung"),
        re.I,
    ),
}
FELDER_JS = """() => {
  const sichtbar = (e) => !!(e.offsetWidth || e.offsetHeight
    || e.getClientRects().length);
  const zeigt = (wahl) => [...document.querySelectorAll(wahl)].some(sichtbar);
  if (zeigt('input[type="password"]')) return ["Anmeldung", "Passwortfeld"];
  if (zeigt('input[autocomplete^="cc-"], input[name*="iban" i], input[id*="iban" i]'))
    return ["Zahlung", "Karten- oder IBAN-Feld"];
  const kasse = /(?:zahlungs|kosten)pflichtig\\s+bestellen/i;
  const knoepfe = document.querySelectorAll(
    'button, input[type="submit"], [role="button"]');
  for (const k of knoepfe) {
    if (sichtbar(k) && kasse.test(k.innerText || k.value || ""))
      return ["Checkout", "Knopf „" + (k.innerText || k.value).trim() + "“"];
  }
  return null;
}"""
KNOPF_JS = """(e) => ({tag: e.tagName.toLowerCase(), rolle: e.getAttribute("role"),
  text: (e.innerText || e.textContent || "").replace(/\\s+/g, " ").trim(),
  ziel: e.getAttribute("target")})"""


def streckenende(adresse: str, felder: list[str] | None) -> str | None:
    """Was die Folgeseite als Anmeldung, Checkout oder Zahlung zeigt, mit Beleg."""
    teile = urlsplit(adresse)
    ort = unquote(f"{teile.hostname or ''}{teile.path}")
    for art, muster in STRECKENENDE.items():
        treffer = muster.search(ort)
        if treffer is not None:
            return f"{art} (Adresse: {treffer[0]})"
    return None if felder is None else f"{felder[0]} ({felder[1]})"


def kein_weiter(daten: dict) -> str | None:
    """Warum ein Knopf (Daten aus ``KNOPF_JS``) kein erlaubter Weiter ist."""
    if daten["tag"] not in KNOPF_TAGS and daten["rolle"] not in KNOPF_ROLLEN:
        return f"ist kein Knopf und kein Link ({daten['tag']})"
    if daten["ziel"] == NEUES_FENSTER:
        return "öffnet ein neues Fenster"
    if KAUFWORT.search(daten["text"]):
        return "sieht nach Kauf, Kasse oder Anmeldung aus"
    return None


def knapp(text: str) -> str:
    """Text ohne doppelten Leerraum und ohne Groß-/Kleinschreibung."""
    return " ".join(text.split()).casefold()


def ohne_anker(adresse: str) -> str:
    """Die Adresse ohne Anker."""
    return urldefrag(adresse)[0]
