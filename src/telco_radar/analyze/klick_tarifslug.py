"""Der Tarif-Slug eines Klick-Satzes, aus dem, was die Seite selbst nennt.

Ohne alten Leser (Pitch 3) hat ein Klick-Satz kein Gegenstück, das ihm Slug und
Tarifnamen leiht (``klick_zusammenfuehrung.UEBERNOMMEN``). Über den gelesenen
Namen allein löst ``Tarifbestand.loese`` o2 und congstar nicht auf: o2 nennt
„O2 Mobile Unlimited L Plus mit 300 MBit/s“, das Blatt „O2 Mobile Unlimited L“;
congstar nennt „Allnet Flat XS“, das Blatt „Allnet Flat XS mit GB+“. Klick-Lauf
vom 10.10.2026: 492 von 688 o2- und congstar-Sätzen ohne Tarif, bei o2 alle.

Die Brücke ist dieselbe, die der alte Leser nutzt, nur von der Seite gelesen. Welche
gilt, steht in der Klick-Karte des Anbieters (Feld ``tarifslug``, ``klickregeln``),
nicht im Code; ohne das Feld hat ein Satz keinen Slug (der Bündelbau zählt ihn als
Tarif ohne Auflösung):

* ``art: name`` (o2): der Name ohne Leistungszusatz („ mit 300 MBit/s“) ist der
  Angebots-Slug, den die Seite selbst bestellt
  (``tariff=o2shop::privatkunden-<slug>-online-…`` in der Antwortadresse; 568 von 568
  Kombinationen am 10.10.2026). „Plus“ bleibt im Slug; welchen Tarif er meint,
  entscheidet ``ueber_slug`` über die Kachel.
* ``art: seitenparameter`` (congstar): ``planId`` der Seitenadresse ist die Nummer des
  Pflichtblatts (``ergaenze_pib_slug``), genau wie beim alten Leser.

Ein Satz, der schon einen Slug trägt, behält ihn; Anbieter ohne Regel bekommen keinen.

Dieselbe Brücke gibt dem Beleglink die Konfiguration der Zeile (``klick_beleglink``,
Kartenfeld ``tarifslug.beleglink: konfiguration``):
der Klick wählt Tarif und Ratenzahl im Browser, die Adresse der Seite bleibt die der
Konfiguration (Preisprüfung 02.11.2026: Link ``ratenzahlung=36`` und
``tarif=o2-mobile-unlimited-m`` zu Zeilen mit 24 Raten und ``O2 Mobile L``).
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit

from ..collect.geraete.klickkartenteile import (
    BELEGLINK_KONFIGURATION,
    TARIFSLUG_NAME,
    TARIFSLUG_SEITENPARAMETER,
)
from ..collect.geraete.klickregeln import regeln
from ..collect.geraete.klickrohsatz import QUELLE
from ..collect.geraete.o2_referenz import belegadresse
from ..collect.tarif_crawler import tarif_id

PLAN_PARAMETER = "planId"
RATEN_PARAMETER = "ratenzahlung"
TARIF_PARAMETER = "tarif"
_LEISTUNGSZUSATZ = re.compile(r"\s+mit\s+.*$", re.IGNORECASE)
_KLAMMER = re.compile(r"\s*\([^)]*\)\s*$")
_NUMMER = re.compile(r"^\d+$")


def klick_slug(satz: dict, karten: Path | None = None) -> str:
    """Der Slug eines Klick-Satzes nach der Regel seiner Karte; sonst leer."""
    if satz.get("quelle_art") != QUELLE:
        return ""
    regel = regeln(satz.get("anbieter"), karten).tarifslug
    if regel is None:
        return ""
    if regel.art == TARIFSLUG_NAME:
        return o2_slug(str(satz.get("tarif_name") or ""))
    if regel.art == TARIFSLUG_SEITENPARAMETER and regel.parameter:
        return plan_nummer(str(satz.get("quelle_url") or ""), regel.parameter)
    return ""


def klick_beleglink(satz: dict, karten: Path | None = None) -> str:
    """Die Quelladresse des Satzes; bei o2-Klick-Sätzen mit Tarif und Ratenzahl der
    Zeile (``o2_referenz.belegadresse``, wie beim Adapter). Die Adresse der Seite
    trägt Tarif und Ratenzahl ihrer Startkonfiguration (36 Raten, ein anderer Tarif):
    kennt der Satz einen Wert nicht, entfällt dessen Angabe, statt den der Seite für
    eine andere Zeile stehen zu lassen (Preisprüfung 03.11.2026: Link
    ``ratenzahlung=36`` zu 24 Raten, ``tarif=o2-mobile-unlimited-m`` zu „On Demand
    M“)."""
    adresse = str(satz.get("quelle_url") or "")
    if satz.get("quelle_art") != QUELLE:
        return adresse
    regel = regeln(satz.get("anbieter"), karten).tarifslug
    if regel is None or regel.beleglink != BELEGLINK_KONFIGURATION:
        return adresse
    raten = satz.get("laufzeit_monate")
    raten = raten if isinstance(raten, int) and not isinstance(raten, bool) else None
    slug = klick_slug(satz, karten)
    link = belegadresse(adresse, slug, raten)
    streichen = {RATEN_PARAMETER} if raten is None else set()
    if not slug:
        streichen.add(TARIF_PARAMETER)
    if not streichen:
        return link
    teile = urlsplit(link)
    frage = [
        (k, v)
        for k, v in parse_qsl(teile.query, keep_blank_values=True)
        if k not in streichen
    ]
    return urlunsplit(teile._replace(query=urlencode(frage)))


def o2_slug(name: str) -> str:
    """„O2 Mobile Unlimited L Plus mit 300 MBit/s“ → ``o2-mobile-unlimited-l-plus``."""
    kern = _LEISTUNGSZUSATZ.sub("", _KLAMMER.sub("", name.strip()))
    if not kern:
        return ""
    return tarif_id("", kern).partition(":")[2]


def plan_nummer(adresse: str, parameter: str = PLAN_PARAMETER) -> str:
    """Der Wert von ``parameter`` (congstar ``planId``) in der Seitenadresse, nur wenn
    er eine Zahl ist."""
    werte = parse_qs(urlsplit(adresse).query).get(parameter) or []
    return werte[0] if len(werte) == 1 and _NUMMER.match(werte[0]) else ""
