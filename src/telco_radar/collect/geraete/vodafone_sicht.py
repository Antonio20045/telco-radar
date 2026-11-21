"""Vodafone: nur Tarife, die die Produktseite auch zur Auswahl stellt.

BEFUND 21.11.2026 (Beleg `docs/belege/vodafone-tarife-ml-2111/`)
-----------------------------------------------------------------
Die Tarifschnittstelle `glados/v2/tariff/v2/hardware` nennt je Geraet Mobil XS,
S, M, L und XL. Die Produktseite zeigt nur XS, S und XL - bei zehn Geraeten aller
Preisklassen, mit „Unter 28“, mit Kombi-Vorteil und mit `?tariffId=269` in der
Adresse. Die Seite fragt dieselbe Schnittstelle selbst nur mit
`virtualItemId=267,268,271` ab. Die Liste baut ihr Skriptbuendel
(`/simplicity/device-details/device-details.bundle.js`, `getTariffWithHardware`)
aus `sailsPageOptions.householdPortfolio.subscriptions[kanal]` abzueglich
`additionalPageOptions.bntPromoHiddenSubscriptions[kanal]`; der zweite Block
steht im HTML jeder Produktseite und nennt fuer `consumer` 269 (Mobil M) und 270
(Mobil L). Dieselbe Ausblendung tragen die Tarifuebersicht
`alle-tarife-mit-vertrag.html` und die SIM-only-Seite.

Die Schnittstelle selbst traegt dafuer KEIN Merkmal: Mobil M und L haben dieselben
Felder wie XS, S und XL (`salesChannel` Online.Consumer, keine Gueltigkeit, kein
Status; `cheapest` ist bei XL ebenfalls false). Deshalb liest `loese_tarifnamen`
je Geraet die Produktseite und laesst Angebote eines dort ausgeblendeten Tarifs
weg - erkannt an der `virtualItemId`, nie am Namen. Ihre Bestandszeilen werden
nicht mehr aufgefrischt und altern in der Ansicht
(`report.geraete_tco_karten.ist_frisch`). Endet die Ausblendung (der Name
`bntPromo…` spricht fuer eine befristete Aktion), kommen sie im naechsten Lauf
zurueck.

EINE SEITE JE LAUF, NICHT JE GERAET
-----------------------------------
Die Ausblendung stand am 21.11.2026 auf allen elf geprueften Produktseiten, der
Tarifuebersicht `alle-tarife-mit-vertrag.html` (dort als `tariffIds`) und der
SIM-only-Seite gleich. Gelesen wird sie deshalb EINMAL je Lauf, von der
Tarifuebersicht (`UEBERSICHT`); scheitert die, von der ersten Produktseite. Jeder
Abruf kostet Zeit, die spaeter im Job der Tarifwelt fehlt.

NICHT GELESEN IST NICHT „NICHTS AUSGEBLENDET“
---------------------------------------------
Ist keine der beiden Seiten lesbar, ist unbekannt, was die Seiten zeigen. Dann
bleibt jeder Tarif der Schnittstelle, denn ein Ausfall von www.vodafone.de darf
nicht die ganze eigene Referenz kosten - aber nie still: Warnung „Sichtbarkeit
unbekannt“, und jeder so ersetzte Rohsatz traegt `UNGEPRUEFT`; das Laufergebnis
nennt die Anbieter unter `sichtbarkeit_nicht_geprueft` (`nicht_geprueft`), damit
die Seite „Sichtbarkeit nicht geprueft“ zeigen kann.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

from .basis import GeraeteAbrufFehler

log = logging.getLogger("telco_radar.collect.geraete.vodafone")

TARIF_ID = "tarif_virtual_item_id"

KANAL_DER_SEITE = "consumer"

UEBERSICHT_SCHLUESSEL = "tariffIds"

UEBERSICHT = (
    "https://www.vodafone.de/privat/handys-tablets-tarife/alle-tarife-mit-vertrag.html"
)

UNGEPRUEFT = "sichtbarkeit_nicht_geprueft"

SEITENOPTIONEN = "sailsPageOptions"

_AUSBLENDUNG_RE = re.compile(
    r"""["']?bntPromoHiddenSubscriptions["']?\s*:\s*\{(?P<koerper>[^{}]*)\}"""
)

_ID_RE = re.compile(r"""["'](\d+)["']""")


def ausgeblendete_tarife(html: str, kanal: str = KANAL_DER_SEITE) -> frozenset | None:
    """Tarif-IDs (`virtualItemId`), die die Produktseite fuer Neuvertraege NICHT
    zur Auswahl stellt - None, wenn die Seite nicht verstanden wurde.

    `kanal` ist der Schluessel der Produktseite zu `salesChannel=Online.Consumer`;
    die Tarifuebersicht hat nur einen Kanal und schreibt `tariffIds`. Eine Seite
    mit `sailsPageOptions`, aber ohne Ausblende-Block, blendet nichts aus (leere
    Menge); eine Seite ohne `sailsPageOptions` ist keine verstandene Seite.
    """
    if SEITENOPTIONEN not in (html or ""):
        return None
    for block in _AUSBLENDUNG_RE.finditer(html):
        for schluessel in (kanal, UEBERSICHT_SCHLUESSEL):
            liste = re.search(
                rf"(?:^|[\s,{{'\"]){re.escape(schluessel)}['\"]?\s*:\s*\[([^\]]*)\]",
                block.group("koerper"),
            )
            if liste:
                return frozenset(_ID_RE.findall(liste.group(1)))
    return frozenset()


def _lies_seite(hole: Callable, url: str) -> frozenset | None:
    """Die Produktseite abrufen und `ausgeblendete_tarife` lesen; bei jedem
    Scheitern None MIT Protokoll."""
    try:
        status, text = hole(url, kopfzeilen={"Accept": "text/html"})
    except (GeraeteAbrufFehler, OSError) as exc:
        log.warning("Vodafone-Produktseite %s: Abruf gescheitert (%s)", url, exc)
        return None
    if not (200 <= int(status) < 300):
        log.warning("Vodafone-Produktseite %s: HTTP %s", url, status)
        return None
    ausgeblendet = ausgeblendete_tarife(text)
    if ausgeblendet is None:
        log.warning(
            "Vodafone-Produktseite %s: ohne %s - Tarifauswahl nicht lesbar",
            url,
            SEITENOPTIONEN,
        )
    return ausgeblendet


def ausblendung_des_laufs(hole: Callable, geraeteseiten: list) -> frozenset | None:
    """Die ausgeblendeten Tarif-IDs dieses Laufs: Tarifuebersicht, sonst die erste
    Produktseite - hoechstens zwei Abrufe. None heisst „nicht geprueft“."""
    erste = next((a for a in geraeteseiten if a), None)
    for adresse in (UEBERSICHT, erste):
        ausgeblendet = _lies_seite(hole, adresse) if adresse else None
        if ausgeblendet is not None:
            return ausgeblendet
    log.warning(
        "Vodafone: weder Tarifuebersicht noch Produktseite lesbar - Sichtbarkeit "
        "unbekannt, alle Tarife der Schnittstelle bleiben"
    )
    return None


def vermerke(saetze: list, ausgeblendet: frozenset | None) -> list:
    """Die Rohsaetze, bei ungeprueftem Lauf mit `UNGEPRUEFT` gekennzeichnet."""
    if ausgeblendet is not None:
        return saetze
    return [{**s, UNGEPRUEFT: True} for s in saetze]


def nicht_geprueft(rohbuendel: list) -> list[str]:
    """Anbieter, deren Tarifauswahl in diesem Lauf nicht geprueft wurde."""
    return sorted(
        {str(b.get("anbieter") or "") for b in rohbuendel if b.get(UNGEPRUEFT)}
    )


def sichtbare_angebote(
    angebote: list, ausgeblendet: frozenset | None
) -> tuple[list, set[str]]:
    """(Tarifname, Komposition)-Paare ohne die ausgeblendeten Tarife, dazu die
    `offerCoreHash` der weggelassenen (fuer den Hash-Rueckfall der Vorschau)."""
    sichtbar: list = []
    verborgen: set[str] = set()
    for name, komposition in angebote:
        if komposition.get(TARIF_ID) in (ausgeblendet or ()):
            verborgen.add(str(komposition.get("offerCoreHash") or "").strip())
        else:
            sichtbar.append((name, komposition))
    verborgen.discard("")
    return sichtbar, verborgen
