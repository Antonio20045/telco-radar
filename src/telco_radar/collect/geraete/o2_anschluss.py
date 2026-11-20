"""o2: der Anschlusspreis eines abgeleiteten Tarifs, nur aus der eigenen Antwort.

DER BEFUND (Gegenprobe 20.11.2026)
----------------------------------
Abgeleitete Sätze (``o2.HERLEITUNG_TARIFSUMME``) nahmen den Anschlusspreis aus der
Referenz, also vom ersten Gerät des Laufs. iPhone 14 erneuert, „O2 Mobile Unlimited
S Special Plus“: gespeichert 39,99 €, die Seite berechnet 0,00 € (39,99 €
durchgestrichen). Am 20.11.2026 trugen 234 abgeleitete o2-Sätze 39,99 € aus der
Referenz; bei 24 davon nannte ein gemessener Satz desselben Modells und Tarifs 0,00 €.

WAS DIE ANTWORT HERGIBT
-----------------------
Die Preiszusammenfassung (``priceSummary``) nennt den berechneten Anschlusspreis nur
für den gewählten Tarif. Für jede andere Tarifoption steht in ihrer Fußnote
(``blauFootnotes``) der Listenpreis: „Einmaliger Anschlusspreis 39,99 €“ bzw. „0 €“;
die Zweitkarte „O2 Mobile Special“ nennt keinen. Eine Geräteaktion kann den Betrag
nur senken (iPhone 14 erneuert: Fußnote 39,99 €, berechnet 0,00 €). Darum:

- Listenpreis 0 € → 0,00 € (weniger geht nicht).
- Listenpreis über 0 € oder keiner → ``None``: die Gesamtkosten nennen die Lücke
  „Anschlusspreis“ (``tco_kosten``), gezählt unter ``ZAEHLER_ANSCHLUSS_OFFEN``.
"""

from __future__ import annotations

import re

ZAEHLER_ANSCHLUSS_OFFEN = "anschluss_offen"
"""Abgeleitete Sätze ohne berechneten Anschlusspreis in der Antwort."""

_TAG_RE = re.compile(r"<[^>]+>")
_LISTENPREIS_RE = re.compile(
    r"Einmaliger Anschlusspreis\s+(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*€"
)


def listen_anschluss(option: dict) -> float | None:
    """Der Listenpreis „Einmaliger Anschlusspreis“ aus der Fußnote einer Tarifoption;
    ``None``, wenn die Fußnote keinen oder mehr als einen nennt."""
    text = " ".join(_TAG_RE.sub(" ", str(option.get("blauFootnotes") or "")).split())
    treffer = set(_LISTENPREIS_RE.findall(text))
    if len(treffer) != 1:
        return None
    betrag = treffer.pop().replace(".", "").replace(",", ".")
    return float(betrag)


def abgeleiteter_anschluss(option: dict, zaehler: dict) -> float | None:
    """Der berechnete Anschlusspreis einer nicht gewählten Tarifoption: 0,00 € bei
    einem Listenpreis von 0 €, sonst ``None`` (gezählt)."""
    if listen_anschluss(option) == 0:
        return 0.0
    zaehler[ZAEHLER_ANSCHLUSS_OFFEN] = int(zaehler.get(ZAEHLER_ANSCHLUSS_OFFEN, 0)) + 1
    return None
