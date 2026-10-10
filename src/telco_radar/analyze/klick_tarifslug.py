"""Der Tarif-Slug eines Klick-Satzes, aus dem, was die Seite selbst nennt.

Ohne alten Leser (Pitch 3) hat ein Klick-Satz kein Gegenstück, das ihm Slug und
Tarifnamen leiht (``klick_zusammenfuehrung.UEBERNOMMEN``). Über den gelesenen
Namen allein löst ``Tarifbestand.loese`` o2 und congstar nicht auf: o2 nennt
„O2 Mobile Unlimited L Plus mit 300 MBit/s“, das Blatt „O2 Mobile Unlimited L“;
congstar nennt „Allnet Flat XS“, das Blatt „Allnet Flat XS mit GB+“. Klick-Lauf
vom 10.10.2026: 492 von 688 o2- und congstar-Sätzen ohne Tarif, bei o2 alle.

Die Brücke ist dieselbe, die der alte Leser nutzt, nur von der Seite gelesen:

* o2: der Name ohne Leistungszusatz („ mit 300 MBit/s“) ist der Angebots-Slug,
  den die Seite selbst bestellt (``tariff=o2shop::privatkunden-<slug>-online-…``
  in der Antwortadresse; 568 von 568 Kombinationen am 10.10.2026). „Plus“ bleibt
  im Slug; welchen Tarif er meint, entscheidet ``ueber_slug`` über die Kachel.
* congstar: ``planId`` der Seitenadresse ist die Nummer des Pflichtblatts
  (``ergaenze_pib_slug``), genau wie beim alten Leser.

Ein Satz, der schon einen Slug trägt, behält ihn; andere Anbieter bekommen keinen.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

from ..collect.geraete.klickrohsatz import QUELLE
from ..collect.tarif_crawler import tarif_id

SLUG_AUS_NAMEN = "o2"
SLUG_AUS_PLAN = "congstar"
PLAN_PARAMETER = "planId"
_LEISTUNGSZUSATZ = re.compile(r"\s+mit\s+.*$", re.IGNORECASE)
_KLAMMER = re.compile(r"\s*\([^)]*\)\s*$")
_NUMMER = re.compile(r"^\d+$")


def klick_slug(satz: dict) -> str:
    """Der Slug eines Klick-Satzes nach dem Modulkopf; sonst leer."""
    if satz.get("quelle_art") != QUELLE:
        return ""
    anbieter = str(satz.get("anbieter") or "")
    if anbieter == SLUG_AUS_NAMEN:
        return o2_slug(str(satz.get("tarif_name") or ""))
    if anbieter == SLUG_AUS_PLAN:
        return plan_nummer(str(satz.get("quelle_url") or ""))
    return ""


def o2_slug(name: str) -> str:
    """„O2 Mobile Unlimited L Plus mit 300 MBit/s“ → ``o2-mobile-unlimited-l-plus``."""
    kern = _LEISTUNGSZUSATZ.sub("", _KLAMMER.sub("", name.strip()))
    if not kern:
        return ""
    return tarif_id(SLUG_AUS_NAMEN, kern).split(":", 1)[1]


def plan_nummer(adresse: str) -> str:
    """Die ``planId`` einer congstar-Seitenadresse, nur wenn sie eine Zahl ist."""
    werte = parse_qs(urlsplit(adresse).query).get(PLAN_PARAMETER) or []
    return werte[0] if len(werte) == 1 and _NUMMER.match(werte[0]) else ""
