"""o2 „Plus“: der Abstand zum gleichnamigen Tarif ohne Plus, am Plus-Bündel.

ENTSCHEIDUNG ANTONIO (21.11.2026)
---------------------------------
Im Gesamtkosten-Vergleich zählt bei o2 der Tarif ohne „Plus“ (Preis ohne Bedingung).
Ein Plus-Tarif zählt nicht (``ist_bedingter_tarif``); seine Zeile nennt „Plus: x €
günstiger mit Zweitprodukt“. Befund: die Produktseite bietet Plus und ohne Plus
nebeneinander an (iPhone 18 Pro Max, 21.11.2026: alle fünf Paare 5,00 € im Monat), und
die Fußnote sagt „Der o2 Plus Bundle Rabatt gilt solange zeitgleich ein zusätzliches
berechtigtes Zweitprodukt aktiv ist“.

DER BETRAG, AN EINER STELLE (Clean Code 1)
------------------------------------------
``plus_vorteil`` am Plus-Bündel: Monatsbetrag (Tarif plus Geräterate) des Gegenstücks
minus den des Plus-Bündels. Gegenstück ist das Bündel desselben Anbieters, derselben
SKU (Gerät, Speicher, Farbe), Ratenzahl, desselben Zustands und Messtags, dessen
Tarifname der Plus-Name ohne das Merkmalwort ist (``GERAETETARIF_MERKMAL``). Fehlt es,
ist es mehrdeutig oder der Abstand nicht positiv, bleibt das Feld ``None`` - die Seite
sagt dann „Rabatt nur mit Zweitprodukt“ ohne Betrag; der Lauf zählt die Gründe.
Gesetzt wird das Feld im Gerätelauf (``geraete_o2_anschluss.speichere``) an den
Bündeln des Tages; die Seite liest nur das Feld.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import replace

from .analyze.geraete_pruefstatus import GERAETETARIF_MERKMAL, ist_bedingter_tarif
from .geraete_model import normalisiere
from .tco_model import Buendel

log = logging.getLogger(__name__)

OHNE_GEGENSTUECK = "ohne_gegenstueck"
MEHRDEUTIG = "mehrdeutig"
NICHT_POSITIV = "nicht_positiv"
OHNE_BETRAG = "ohne_betrag"


def ohne_merkmal(anbieter: str, tarif_name: str) -> str:
    """Der Tarifname ohne das Plus-Wort (``GERAETETARIF_MERKMAL``) des Anbieters."""
    merkmal = GERAETETARIF_MERKMAL.get(normalisiere(anbieter))
    return " ".join(w for w in (tarif_name or "").split() if w != merkmal)


def _schluessel(b: Buendel, name: str) -> tuple:
    return (
        normalisiere(b.anbieter),
        b.sku_id,
        b.laufzeit_monate,
        b.zustand,
        b.abgerufen_am,
        " ".join(name.split()),
    )


def _monat(b: Buendel) -> float | None:
    if b.tarif_monatlich is None or b.geraet_monatsrate is None:
        return None
    return float(b.tarif_monatlich) + float(b.geraet_monatsrate)


def abstand(plus: Buendel, gegenstuecke: list[Buendel]) -> tuple[float | None, str]:
    """(Betrag, Grund): der Monatsvorteil des Plus-Bündels - oder None mit Grund."""
    if not gegenstuecke:
        return None, OHNE_GEGENSTUECK
    if len(gegenstuecke) > 1:
        return None, MEHRDEUTIG
    eigen, gegen = _monat(plus), _monat(gegenstuecke[0])
    if eigen is None or gegen is None:
        return None, OHNE_BETRAG
    betrag = round(gegen - eigen, 2)
    return (betrag, "") if betrag > 0 else (None, NICHT_POSITIV)


def vermerke(buendel: Iterable[Buendel], zaehler: Counter | None = None) -> list:
    """Jedes Plus-Bündel mit ``plus_vorteil`` (``abstand``); alle anderen unverändert.

    ``zaehler`` zählt je Grund, warum ein Plus-Bündel keinen Betrag trägt."""
    alle = list(buendel)
    z = zaehler if zaehler is not None else Counter()
    je_name: dict[tuple, list[Buendel]] = defaultdict(list)
    for b in alle:
        if not ist_bedingter_tarif(b.anbieter, b.tarif_name):
            je_name[_schluessel(b, b.tarif_name)].append(b)
    out = []
    for b in alle:
        if not ist_bedingter_tarif(b.anbieter, b.tarif_name):
            out.append(b)
            continue
        ziel = _schluessel(b, ohne_merkmal(b.anbieter, b.tarif_name))
        betrag, grund = abstand(b, je_name.get(ziel, []))
        z[grund or "mit_betrag"] += 1
        out.append(replace(b, plus_vorteil=betrag))
    if z:
        log.info("Plus-Abstand je Grund: %s", dict(sorted(z.items())))
    return out
