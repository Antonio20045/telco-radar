"""1&1: der Monatspreis des BUENDELS, und nichts anderes.

DER BEFUND, DER DIESEN ANBIETER EIN JAHR LANG DRAUSSEN HIELT
------------------------------------------------------------
Die Produktseite traegt ein sauberes `application/ld+json` vom Typ
`Product` - und sein `offers.price` ist NICHT der Geraetepreis, sondern der
Monatspreis des Buendels aus Geraet und Tarif. Gemessen am 04.09.2026 an
`https://mobile.1und1.de/iphone-17-pro` (HTTP 200, 325 KB):

    "name": "iPhone 17 Pro",
    "description": "iPhone 17 Pro mit 1&1 All-Net-Flat S",
    "offers": {"priceCurrency": "EUR", "price": "44.99"}

44,99 EUR ist kein Preis fuer ein Telefon. Als Barpreis gespeichert waere
die Zahl **plausibel falsch** - genau die Sorte Fehler, gegen die der
Lockpreis-Waechter gebaut ist, nur oberhalb seiner Grenze von 30 EUR. Der
`grund` in `geraete_quellen.yaml` sagte das seit 08/2026 richtig; falsch war
nur die Folgerung, dass man deshalb warten muesse.

UNTER TCO-FIRST IST GENAU DIESE ZAHL DIE LEITGROESSE
----------------------------------------------------
1&1 verkauft Geraete NUR im Tarifbund. Es gibt dort keinen Barpreis, den
dieser Adapter verschweigen wuerde - es gibt ihn nicht. Was es gibt, ist
eine vollstaendige Buendelaussage, und die Seite nennt alle drei Teile
selbst:

    Monatspreis     `offers.price`                     44,99 EUR
    Tarif           aus `description` ("... mit X")    1&1 All-Net-Flat S
    Laufzeit        `window.currentHardwareOfferDuration`   36

`preis_ohne_vertrag` bleibt deshalb LEER. Nicht, weil die Zahl fehlt,
sondern weil es sie nicht gibt; sie aus 44,99 x 36 minus Tarif zu rechnen
waere eine Rechnung dieses Projekts und keine Angabe des Anbieters
(dieselbe Grenze wie beim Vierwochenpreis im Tarif-Sammler).

WARUM DER TARIFNAME AUS DER BESCHREIBUNG KOMMT
----------------------------------------------
`Listung.__post_init__` verwirft jede Buendelzahl ohne `tarif_referenz` -
"iPhone fuer 1 Euro" ist ohne den Vertrag daneben bedeutungslos. 1&1
schreibt den Tarif in dieselbe Zeile wie das Geraet ("iPhone 17 Pro mit
1&1 All-Net-Flat S"), also steht er in der Quelle und muss nicht geraten
werden. Findet sich dort kein Tarif, wird der Satz verworfen - lieber keine
Listung als eine Zahl ohne ihren Vertrag.

Der so gelesene Name trifft den Tarifbestand: `/handytarife` fuehrt densel-
ben Tarif als ld+json-Knoten "1&1 All-Net-Flat S", und `tarif_bezug` loest
beide auf dieselbe ID auf (`11:1-1-all-net-flat-s`). Das ist kein Zufall,
sondern derselbe Anbietertext an zwei Stellen seiner eigenen Seite.

WELCHE VARIANTE DER PREIS MEINT
-------------------------------
Die Seite zeigt eine Variante VORAUSGEWAEHLT und nennt sie:

    window.currentProductVariants[window.productId] = {
        'color': 'COSMIC_ORANGE', 'size': '256', 'depositValue': '' };

Der Preis im ld+json gehoert zu dieser Variante. Die uebrigen Kombinationen
(drei Farben x drei Speicherstufen in `window.availabilities`) tragen andere
Preise, die die Seite erst im Browser nachlaedt - sie werden hier NICHT
angefasst. Eine Preistabelle ueber Tarif x Speicher braucht einen eigenen
Spike; sie hier aus einer einzigen Zahl zu vervielfaeltigen hiesse, drei
Viertel der Saetze zu erfinden.

`depositValue` ist die Anzahlung. Im gemessenen Fall ist sie leer - dann
gibt es keine, und das Feld bleibt leer statt 0.00: "nicht genannt" und
"null Euro" sind zwei verschiedene Aussagen.

ROBOTS.TXT (04.09.2026 gelesen)
-------------------------------
`mobile.1und1.de/robots.txt` sperrt fuer `User-agent: *` die Verzeichnisse
`/xml/`, `/static/`, `/modules/`, dazu einzelne Aktions- und
Bestellstrecken. Die Produktseiten und `/smartphones` sind frei; der
Parameter `?chosenTariff=` ist sogar ausdruecklich erlaubt. Unser Absender
ist `TelcoRadar/1.0` und faellt unter `*`.
"""
from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ...tarif_model import zahl
from ..tarif_ldjson import ld_json_bloecke

log = logging.getLogger(__name__)

# "iPhone 17 Pro mit 1&1 All-Net-Flat S" -> "1&1 All-Net-Flat S".
# Bewusst gierig bis zum Zeilenende: der Tarifname traegt selbst Leerzeichen
# und Bindestriche, und ein sparsames Muster schnitte ihn nach dem ersten
# Wort ab. `&amp;` kommt vor, weil dieselbe Beschreibung auch in HTML-Text
# steht.
_TARIF_RE = re.compile(r"\bmit\s+(?P<tarif>\S.*?)\s*$", re.I)

# window.currentProductVariants[window.productId] = { 'color': 'X', ... }
_VARIANTE_RE = re.compile(
    r"window\.currentProductVariants\s*\[[^\]]+\]\s*=\s*\{(?P<rumpf>[^}]*)\}",
    re.S)
_FELD_RE = re.compile(r"['\"](?P<feld>\w+)['\"]\s*:\s*['\"](?P<wert>[^'\"]*)['\"]")

_LAUFZEIT_RE = re.compile(
    r"window\.currentHardwareOfferDuration\s*=\s*['\"](?P<monate>\d+)['\"]")

# schema.org/InStock -> lieferbar. Nur die Zustaende, die 1&1 wirklich
# ausliefert, werden uebersetzt; alles andere ist `unbekannt` und behauptet
# nichts.
_LAGER = {
    "instock": "lieferbar",
    "preorder": "vorbestellbar",
    "outofstock": "ausverkauft",
    "soldout": "ausverkauft",
    "backorder": "nicht_lieferbar",
}


def _verfuegbarkeit(roh) -> str:
    schluessel = str(roh or "").rsplit("/", 1)[-1].strip().lower()
    return _LAGER.get(schluessel, "unbekannt")


def _tarif_aus_beschreibung(text: str) -> str:
    treffer = _TARIF_RE.search((text or "").replace("&amp;", "&").strip())
    return treffer.group("tarif").strip() if treffer else ""


def variante(html: str) -> dict:
    """Farbe, Speicher und Anzahlung der VORAUSGEWAEHLTEN Variante."""
    treffer = _VARIANTE_RE.search(html or "")
    if not treffer:
        return {}
    return {m.group("feld"): m.group("wert")
            for m in _FELD_RE.finditer(treffer.group("rumpf"))}


def laufzeit_monate(html: str) -> Optional[int]:
    """Die Bindungsdauer des Hardware-Angebots, wie die Seite sie nennt."""
    treffer = _LAUFZEIT_RE.search(html or "")
    if not treffer:
        return None
    monate = int(treffer.group("monate"))
    return monate if monate > 0 else None


# Die Kachelueberschrift eines Geraets im Katalograster. Genau diese Klasse
# traegt die 42 Produktadressen der Kategorieseite - und NUR sie.
_KACHEL_KLASSE = "hardware-box__heading"


def ernte(text: str, basis_url: str, pfadmuster="", kind: str = "") -> list[str]:
    """Aus der Kategorieseite die Produktadressen - eine je Geraet.

    WARUM DIE ALLGEMEINE LINKERNTE HIER NICHT REICHT
    ------------------------------------------------
    `mobile.1und1.de/smartphones` traegt am 04.09.2026 **167** Adressen auf
    der eigenen Domain, davon nur 42 Produktseiten. Der Rest sind
    Hauptnavigation, Themenseiten (`/unbegrenztes-datenvolumen`,
    `/handyvertrag-ohne-laufzeit`), Zubehoer-Auflagen
    (`/DetailsAirPods4?lightbox=true`) und 39 Bilder unter
    `/_catalog/images/`. Ein Pfadmuster hilft nicht: die Produktseiten
    heissen `/iphone-17-pro` und `/fairphone-6` und haben keinen
    gemeinsamen Pfadteil, den die Themenseiten nicht auch haetten.

    Mit `ernte_links` liefe der Sammler deshalb in seinen Deckel
    (`max_produkte`), meldete die Seite als unvollstaendig gelesen - und
    haette dafuer ueber hundert Abrufe verbraucht, die kein Geraet tragen
    koennen.

    Gelesen wird stattdessen das, was die Seite selbst als Katalogkachel
    auszeichnet: `<a class="hardware-box__heading">`. Das ist keine
    Konstruktion, sondern die Auswahl, die 1&1 auf seiner eigenen Seite
    trifft; die Adressen stehen woertlich als `href` darin.

    `pfadmuster` wirkt zusaetzlich, wenn eines konfiguriert ist - dieselbe
    Bedeutung wie in `ernte_links`, damit eine Konfiguration den Umfang
    weiter einengen kann, ohne den Adapter anzufassen.
    """
    muster = ([m for m in pfadmuster if m] if isinstance(pfadmuster, (list, tuple))
              else ([pfadmuster] if pfadmuster else []))
    suppe = BeautifulSoup(text or "", "html.parser")
    out: list[str] = []
    gesehen: set[str] = set()
    for anker in suppe.find_all("a", href=True):
        if _KACHEL_KLASSE not in (anker.get("class") or []):
            continue
        ziel = urljoin(basis_url or "https://mobile.1und1.de",
                       anker["href"]).split("#", 1)[0]
        if muster and not all(m in ziel for m in muster):
            continue
        if ziel in gesehen:
            continue
        gesehen.add(ziel)
        out.append(ziel)
    if not out:
        # Kein Wurf: eine leere Ernte ist im Sammler ein eigener,
        # sichtbarer Zustand ("0 Listungen aus 1 Seite"). Eine Ausnahme
        # machte daraus einen Abruffehler und verwechselte "Seite gelesen,
        # Raster leer" mit "Seite nicht gelesen".
        log.warning("1&1: %s traegt keine %s-Kachel (%d Bytes) - "
                    "Raster leer oder Markup geaendert",
                    basis_url, _KACHEL_KLASSE, len(text or ""))
    return out


def lies(text: str, url: str = "") -> list[dict]:
    """Eine Produktseite in hoechstens einen Rohsatz zerlegen.

    Hoechstens einen, weil die Seite genau EINE Variante bepreist. Ein
    zweiter Satz koennte nur aus einer Vervielfaeltigung entstehen, und
    eine vervielfaeltigte Zahl ist keine gemessene.
    """
    laufzeit = laufzeit_monate(text)
    var = variante(text)
    out: list[dict] = []
    for block in ld_json_bloecke(text):
        knoten = block if isinstance(block, dict) else {}
        typ = knoten.get("@type")
        if typ != "Product" and not (isinstance(typ, list) and "Product" in typ):
            continue
        angebot = knoten.get("offers")
        if isinstance(angebot, list):
            angebot = angebot[0] if angebot else None
        if not isinstance(angebot, dict):
            continue
        monatspreis = zahl(angebot.get("price"))
        if monatspreis is None:
            continue

        tarif = _tarif_aus_beschreibung(knoten.get("description"))
        if not tarif:
            # Eine Buendelzahl ohne ihren Tarif ist bedeutungslos, und
            # `Listung.__post_init__` wuerde sie ohnehin zurueckweisen.
            # Hier faellt sie mit einer Zeile im Protokoll, statt weiter
            # unten mit einer Ausnahme.
            log.info("1&1: %s nennt keinen Tarif in der Beschreibung (%r) - "
                     "Buendelpreis verworfen", url,
                     str(knoten.get("description"))[:80])
            continue

        marke = knoten.get("brand")
        marke_name = (marke.get("name") if isinstance(marke, dict)
                      else marke) or ""
        name = str(knoten.get("name") or "").strip()
        if not name:
            continue
        speicher = var.get("size")
        farbe = (var.get("color") or "").replace("_", " ").strip().lower()
        out.append({
            "titel": " ".join(x for x in (str(marke_name).strip(), name,
                                          f"{speicher} GB" if speicher else "",
                                          farbe) if x),
            # KEIN Barpreis. 1&1 verkauft Geraete nur im Tarifbund; die
            # Spalte bleibt leer, statt eine Zahl zu bekommen, die es
            # nicht gibt.
            "preis": None,
            "monatspreis": monatspreis,
            "tarif": tarif,
            "laufzeit_monate": laufzeit,
            "waehrung": str(angebot.get("priceCurrency") or "EUR").upper(),
            "verfuegbarkeit": _verfuegbarkeit(angebot.get("availability")),
            # Die Kennung, die die Seite selbst fuehrt.
            "sku": str(knoten.get("sku") or "").strip(),
            "ean": str(knoten.get("gtin13") or knoten.get("gtin") or "").strip(),
            "farbe": farbe,
            "speicher_gb": int(speicher) if str(speicher).isdigit() else None,
            "url": str(knoten.get("url") or "").strip() or url,
            "quelle": "einsundeins_buendel",
        })
    return out
