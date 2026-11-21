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

DER GEGENBEFUND (21.11.2026)
----------------------------
Eine Geräteaktion kann den Betrag auch über die Fußnote heben: Xiaomi Redmi 17,
„O2 Mobile on Demand M“, Fußnote „0 €“, berechnet 39,99 €
(``tests/fixtures/geraete/o2_redmi17_tarifoptionen_20261121.json.gz``). Berechnet die
Antwort für ihren gewählten Tarif mehr als dessen Fußnote, taugen ihre Fußnoten nicht
als Beleg (``fussnoten_tragen``): jeder abgeleitete Anschlusspreis dieser Antwort ist
die Lücke. Gegenprobe am selben Tag gegen die Klick-Messung: 439 abgeleitete
Anschlusspreise gleich, 43 Lücke, 0 abweichend.
"""

from __future__ import annotations

import re

ZAEHLER_ANSCHLUSS_OFFEN = "anschluss_offen"
_CENT = 0.005
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


def fussnoten_tragen(gewaehlt: dict, berechnet: float | None) -> bool:
    """Die Fußnoten einer Antwort belegen 0 €, solange die Antwort für ihren gewählten
    Tarif nicht mehr berechnet als dessen Fußnote (``None``: keine Fußnote, trägt)."""
    liste = listen_anschluss(gewaehlt)
    return liste is None or berechnet is None or berechnet <= liste + _CENT


def abgeleiteter_anschluss(
    option: dict, zaehler: dict, fussnoten: bool = True
) -> float | None:
    """Der berechnete Anschlusspreis einer nicht gewählten Tarifoption: 0,00 € bei
    einem Listenpreis von 0 € und tragenden Fußnoten (``fussnoten_tragen``), sonst
    ``None`` (gezählt)."""
    if fussnoten and listen_anschluss(option) == 0:
        return 0.0
    zaehler[ZAEHLER_ANSCHLUSS_OFFEN] = int(zaehler.get(ZAEHLER_ANSCHLUSS_OFFEN, 0)) + 1
    return None


ADRESSE = "_anschluss_adresse"
"""Hilfsfeld eines abgeleiteten Satzes: die Antwort seines Tarifs (``selectCall``);
``nachmesse`` entfernt es aus jedem Satz."""
ZAEHLER_NACHGEMESSEN = "anschluss_nachgemessen"
ZAEHLER_NACHMESSUNG_WIDERSPRICHT = "anschluss_nachmessung_widerspricht"
ZAEHLER_NACHMESSUNG_FRIST = "anschluss_nachmessung_frist"
_GLEICH = (
    ("angebot", "angebot"),
    ("tarif_slug", "slug"),
    ("geraet_zuzahlung", "anzahlung"),
    ("geraet_monatsrate", "rate"),
    ("tarif_monatlich", "tarif_rate"),
)


def _bestaetigt(satz: dict, g: dict | None) -> bool:
    if g is None or g.get("anschluss") is None:
        return False
    for feld, mess in _GLEICH:
        a, b = satz.get(feld), g.get(mess)
        if isinstance(a, float) and isinstance(b, float):
            if abs(a - b) > _CENT:
                return False
        elif a != b:
            return False
    return True


def nachmesse(saetze: list, abruf, messe, weiter, zaehler: dict) -> list:
    """Je abgeleitetem Satz ohne Anschlusspreis die Antwort seines Tarifs, solange
    ``weiter()`` Zeit gibt (nach der Vertiefung, Befund im Kopf von
    ``tests/test_geraete_o2_anschluss_nachmessung.py``). Nennt sie dasselbe Angebot,
    denselben Tarif und dieselben Beträge, gilt ihr Anschlusspreis und der Satz ist
    gemessen; sonst bleibt die Lücke. ``abruf(url)`` liefert die gelesene Antwort oder
    ``None``, ``messe`` ist ``o2._gemessen``."""
    for satz in saetze:
        adresse = satz.pop(ADRESSE, None)
        if not adresse or satz.get("anschlusspreis") is not None:
            continue
        if not weiter():
            zaehler[ZAEHLER_NACHMESSUNG_FRIST] = (
                zaehler.get(ZAEHLER_NACHMESSUNG_FRIST, 0) + 1
            )
            continue
        antwort = abruf(adresse)
        g = messe(antwort) if antwort else None
        if g is None or not _bestaetigt(satz, g):
            name = ZAEHLER_NACHMESSUNG_WIDERSPRICHT
        else:
            satz["anschlusspreis"] = g["anschluss"]
            satz.pop("herleitung", None)
            name = ZAEHLER_NACHGEMESSEN
        zaehler[name] = zaehler.get(name, 0) + 1
    return saetze
