"""o2: Bündel nur für Tarife, die ein Kunde bei o2 selbst wählen und kaufen kann.

ENTSCHEIDUNG ANTONIO (21.11.2026)
---------------------------------
Die Geräteseite zeigt nur Gesamtkosten, die ein Kunde bei o2 selbst wählen und
kaufen kann. Ein Tarif, der nur in der Schnittstelle steht, wird kein Bündel
(wie Mobil M/L bei Vodafone, `vodafone_sicht`).

DER BEFUND (21.11.2026)
-----------------------
`<script id="pageValue">` der Produktseite nennt zum Galaxy S26 256 GB zwölf
Tarifoptionen, alle `disabled: false`, ohne ein Feld für Sichtbarkeit oder Kanal. Die
Seite selbst (Browser, Reiter Neukunden) zeigt fünf Kacheln: die fünf „Plus“-Tarife.
Die Kacheln zeichnet erst ein Skript im Browser (`/codehub-de/packages-loader.js`);
das HTML vom Server trägt sie nicht (Abruf 21.11.2026 15:50 MEZ ohne Browser: kein
`pdp-tariff-plans`). Was die fünf erzeugt, ist ohne Browser nicht bestimmbar.

DIE WEGE, DIE ALS KAUFBAR GELTEN (`grund`)
------------------------------------------
1. `PRODUKTSEITE`: Kachel der Produktseite. ANNAHME, belegt am 21.11.2026: eine
   Kachel hat genau der Tarif, dessen Slug (`dimension59`, `tarif=` im Link) auf
   `PLUS_ENDUNG` endet. Belege: die fünf Kacheln des S26 sind die fünf Optionen mit
   „Plus“ im Namen (Browser), und „Plus“ im Namen hat genau der Slug mit `-plus`
   (zwölf Paare aus echten Antworten). Die Tests in `test_o2_kaufbare_tarife.py`
   brechen, wenn eins davon nicht mehr gilt; sieht ein Lauf gar keinen Slug mit der
   Endung, nennt das Protokoll das Muster als verloren (`MUSTER_FEHLT`).
2. `VORGEWAEHLT`: der Tarif, mit dem die Produktseite geöffnet wurde. Der
   Gerätekatalog („Handys mit Vertrag“) verlinkt jedes Gerät mit einem Tarif; die
   Seite zeigt ihn als Kachel (Redmi 17 mit sieben Tarifen ohne „Plus“: eine Kachel,
   der gewählte; S26 mit `tarif=o2-mobile-on-demand-m`: sechste Kachel, PR 195). Das
   ist der gemessene Satz jeder Antwort, also jeder Satz ohne `herleitung`.
3. `UEBERSICHT`: Tarife, die die Tarifübersicht `UEBERSICHT` mit „Handy hinzufügen“
   verlinkt (`/e-shop?tarif=<slug>`). Die Seite ist serverseitig gezeichnet, ein
   Abruf je Lauf. Am 21.11.2026 zehn Slugs, darunter `o2-mobile-unlimited-l` (ohne
   „Plus“; über diesen Weg mit Gerät buchbar, Preis traf das Bündel Wert für Wert).

Jeder andere abgeleitete Satz wird kein Bündel; das Protokoll zählt die Tarife
(„o2: n Tarife nur in der Schnittstelle, nicht kaufbar: …“). Am 21.11.2026: Mobile
L, Mobile S, Mobile Special, Unlimited M, Unlimited S Special, on Demand M (ohne
„Plus“). Ihre Bestandszeilen werden nicht mehr aufgefrischt und fallen nach
`ALT_AB_TAGEN` aus der Ansicht (`report.geraete_tco_karten.ist_frisch`).

AUSFALL DER ÜBERSICHT
---------------------
Nicht gelesen ist nicht leer und nicht „alles kaufbar“: dann gelten nur die Wege 1
und 2, und das Protokoll nennt den Ausfall (`AUSFALL`).
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from ..http import HttpFehler
from .basis import GeraeteAbrufFehler
from .o2 import HERLEITUNG_TARIFSUMME

log = logging.getLogger(__name__)

UEBERSICHT = "https://www.o2online.de/tarife/"
HANDY_HINZUFUEGEN = "Handy hinzufügen"
SHOP_PFADE = frozenset({"/e-shop", "/e-shop/"})
PLUS_ENDUNG = "-plus"

PRODUKTSEITE = "produktseite"
VORGEWAEHLT = "vorgewaehlt"
UEBERSICHT_GRUND = "uebersicht"

AUSFALL = (
    "o2: Tarifübersicht nicht gelesen - nur die Auswahl der Produktseite gilt als "
    "kaufbar"
)
MUSTER_FEHLT = (
    "o2: kein Tarif mit Slug-Endung '-plus' - Kacheln der Produktseite unbekannt, "
    "nur vorgewählte und verlinkte Tarife gelten als kaufbar"
)


def _text(knoten) -> str:
    return " ".join(knoten.get_text(" ").split())


def slugs_der_uebersicht(html: str) -> frozenset | None:
    """Die Tarif-Slugs, die die Tarifübersicht mit „Handy hinzufügen“ verlinkt.

    Gezählt wird ein Link nur, wenn sein Text „Handy hinzufügen“ ist und er auf den
    Shop (`/e-shop?tarif=<slug>`) zeigt. None, wenn die Seite keinen solchen Link
    trägt: dann ist sie nicht verstanden, und das ist ein Ausfall, kein leeres
    Ergebnis.
    """
    suppe = BeautifulSoup(html or "", "html.parser")
    slugs: set[str] = set()
    for anker in suppe.find_all("a"):
        if _text(anker) != HANDY_HINZUFUEGEN:
            continue
        teile = urlsplit(str(anker.get("href") or ""))
        if teile.path not in SHOP_PFADE:
            continue
        for slug in parse_qs(teile.query).get("tarif") or []:
            if slug.strip():
                slugs.add(slug.strip())
    return frozenset(slugs) if slugs else None


def lies_uebersicht(hole: Callable) -> frozenset | None:
    """Ein Abruf der Tarifübersicht über das robots-treue `hole` des Laufs.

    Jedes Scheitern (Sperre der Schleuse, HTTP-Fehler, Schutzantwort, unverstandene
    Seite) ist None MIT Protokoll, nie eine leere Menge.
    """
    try:
        antwort = hole(UEBERSICHT, kopfzeilen={"Accept": "text/html"}, einmalig=True)
        status, text = antwort
    except (GeraeteAbrufFehler, HttpFehler, OSError, RuntimeError) as exc:
        log.warning("o2-Tarifübersicht %s: Abruf gescheitert (%s)", UEBERSICHT, exc)
        return None
    if getattr(antwort, "schutz", False) or not 200 <= int(status) < 300:
        log.warning("o2-Tarifübersicht %s: HTTP %s", UEBERSICHT, status)
        return None
    slugs = slugs_der_uebersicht(text)
    if slugs is None:
        log.warning(
            "o2-Tarifübersicht %s: kein Link '%s' - Seite nicht verstanden",
            UEBERSICHT,
            HANDY_HINZUFUEGEN,
        )
    return slugs


def ist_vorgewaehlt(satz: dict) -> bool:
    """Der gemessene Satz einer Antwort: ihr gewählter Tarif (ohne `herleitung`)."""
    return satz.get("herleitung") != HERLEITUNG_TARIFSUMME


def ist_kachel(slug: str) -> bool:
    """Hat dieser Tarif eine Kachel der Produktseite? (Annahme 1 im Modulkopf)."""
    return slug.endswith(PLUS_ENDUNG)


def grund(satz: dict, uebersicht: frozenset | None) -> str | None:
    """Über welchen sichtbaren Weg ist dieser Satz kaufbar - oder None.

    Dieselbe Definition gilt für jede Zählung angebotener o2-Tarife.
    """
    slug = str(satz.get("tarif_slug") or "").strip()
    if ist_vorgewaehlt(satz):
        return VORGEWAEHLT
    if ist_kachel(slug):
        return PRODUKTSEITE
    if uebersicht is not None and slug in uebersicht:
        return UEBERSICHT_GRUND
    return None


@dataclass
class Befund:
    """Ergebnis eines Laufs: behaltene Sätze und die verworfenen Tarife."""

    behalten: list = field(default_factory=list)
    verworfen: Counter = field(default_factory=Counter)
    wege: Counter = field(default_factory=Counter)
    uebersicht_gelesen: bool = False
    muster_gesehen: bool = False

    @property
    def zeile(self) -> str:
        """Die Protokollzeile: wie viele Tarife nur in der Schnittstelle stehen."""
        teile = ", ".join(
            f"{name} ({anzahl} Bündel)"
            for name, anzahl in sorted(self.verworfen.items())
        )
        return (
            f"o2: {len(self.verworfen)} Tarife nur in der Schnittstelle, nicht "
            f"kaufbar: {teile or '-'}; {sum(self.verworfen.values())} Bündel verworfen"
        )


def _tarif(satz: dict) -> str:
    name = str(satz.get("tarif_name") or "").strip()
    return name.split(" (", 1)[0] if name else str(satz.get("tarif_slug") or "")


def pruefe(rohbuendel: list, uebersicht: frozenset | None) -> Befund:
    """Teilt die o2-Rohsätze in kaufbare und verworfene (`grund`). Ohne Netz."""
    befund = Befund(uebersicht_gelesen=uebersicht is not None)
    for satz in rohbuendel:
        weg = grund(satz, uebersicht)
        befund.muster_gesehen |= ist_kachel(str(satz.get("tarif_slug") or ""))
        if weg is None:
            befund.verworfen[_tarif(satz)] += 1
            continue
        befund.wege[weg] += 1
        befund.behalten.append(satz)
    return befund


def protokolliere(befund: Befund) -> None:
    """Schreibt Zählung, Ausfall und verlorenes Muster ins Erfassungsprotokoll."""
    log.info(
        "%s (behalten je Weg: %s)", befund.zeile, dict(sorted(befund.wege.items()))
    )
    if not befund.uebersicht_gelesen:
        log.warning(AUSFALL)
    if not befund.muster_gesehen:
        log.warning(MUSTER_FEHLT)


def nur_kaufbare(hole: Callable, kopfzeilen: dict, rohbuendel: list) -> int:
    """Nachbearbeitungs-Haken (`Adapter.loese_tarifnamen`) für o2.

    Liest die Tarifübersicht einmal (`lies_uebersicht`), behält nur kaufbare Sätze
    (`pruefe`) und ändert `rohbuendel` an Ort und Stelle. `kopfzeilen` (der
    Medientyp der Shop-Schnittstelle) gilt für die HTML-Seite nicht. Gibt 0 zurück:
    hier wird kein Tarifname aufgelöst.
    """
    del kopfzeilen
    if not any(not ist_vorgewaehlt(s) for s in rohbuendel):
        return 0
    befund = pruefe(rohbuendel, lies_uebersicht(hole))
    rohbuendel[:] = befund.behalten
    protokolliere(befund)
    return 0
