"""Telekom: die Tarifkacheln der Shop-Uebersichtsseite `/shop/tarife/handyvertrag`.

WARUM ES DIESEN ADAPTER JETZT GIBT, UND WARUM NICHT FRUEHER
-------------------------------------------------------------
Der Kommentar am Fuss von `config/tarif_quellen.yaml` ("Warum der
TELEKOM-SHOP hier NICHT als Live-Quelle steht", Messung 04.09.2026) bleibt
fuer die dort geprueften Stellen richtig: `window.__INITIAL_STATE__.
tariffv2.plans` ist leer, `tariffHtmlSnippet.snippet.data` ist `[]`, und das
einzige ld+json der Seite traegt BreadcrumbList/Organization/FAQPage - keinen
Product-Knoten. Wer nur den Zustand abfragt, findet also weiterhin nichts.

Nachgemessen am 05.09.2026 (lokal, Absender `TelcoRadar/1.0`, HTTP 200,
2,26 MB): die Seite rendert ihre fuenf Tarifkacheln trotzdem SERVERSEITIG
als HTML - nur eben nicht als JSON-Zustand, sondern als React-CSS-Module-
Markup (`TariffTileModified_TariffTileModified__<hash>`). Genau das hatte
die fruehere Messung nicht gesehen, weil sie nur den Zustand las.

DIE ZAHL, DIE WIRKLICH ZAEHLT: DER DURCHGESTRICHENE PREIS, NICHT DAS "Ø"
--------------------------------------------------------------------------
Jede Kachel zeigt ZWEI Betraege: gross und mit "Ø" (Durchschnitt) praefixiert
einen kombinierten/rabattierten Preis (MagentaEINS-Kombivorteil o.ae.), und
darunter durchgestrichen einen zweiten, hoeheren Betrag.

    MagentaMobil S    Ø 34,95 € mtl.    durchgestrichen 39,95 €
    MagentaMobil M    Ø 39,95 € mtl.    durchgestrichen 49,95 €
    MagentaMobil L    Ø 49,95 € mtl.    durchgestrichen 59,95 €
    MagentaMobil XL   Ø 74,95 € mtl.    durchgestrichen 84,95 €
    MagentaMobil XS   Ø 24,95 € mtl.    durchgestrichen 29,95 €

Der DURCHGESTRICHENE Betrag ist die STANDALONE-Grundgebuehr, die
Ø-Zahl ist ein bedingter Kombipreis (setzt einen zweiten Vertrag oder einen
Festnetzanschluss voraus - dieselbe Grenze wie bei einer Vodafone-Kachel
"mit 5-Jahresversprechen": eine Tarifoption ist keine Gerätestufe). Das ist
keine Vermutung, sondern eine GEGENPROBE gegen die bestehende, aus den
Produktinformationsblaettern gelesene Datenbank: fuer S/M/L/XL steht dort
seit Jahren 39,95/49,95/59,95/84,95 EUR - exakt die vier durchgestrichenen
Betraege dieser Seite, nicht die vier Ø-Betraege. Nur MagentaMobil XS ist im
PIB-Bestand nicht vorhanden (dort steht stattdessen "MagentaMobil Basic" zu
24,95 EUR - ein anderer, mittlerweile wohl abgeloester Tarif) und bleibt
ohne Gegenprobe; dieselbe Extraktionslogik gilt fuer alle fuenf Kacheln
gleichermassen.

Deshalb: `grundgebuehr` kommt AUSSCHLIESSLICH aus dem durchgestrichenen
Preis. Fehlt er, wird die Kachel verworfen statt die Ø-Zahl zu uebernehmen -
sie waere ein Betrag, der eine zweite Bedingung voraussetzt, die dieser
Adapter nicht pruefen kann.

WAS DIE KACHEL SONST HERGIBT
-----------------------------
`datenvolumen_gb`  Aus der "hero"-Zahl (z. B. "50" fuer 50 GB) oder, wenn
                   die Kachel "Unlimited" zeigt, `float("inf")`.
`dokument_url`     Der Link "Tarif auswählen" (`?tariffId=MF_...`) - die
                   Tiefenadresse GENAU dieses Tarifs, nicht die
                   Uebersichtsseite fuer alle fuenf.
`laufzeit_monate`  Wird NICHT gesetzt: die Kachel selbst nennt keine
                   Mindestlaufzeit (die steht nur in einer Fussnote, die
                   diese Seite nicht mitliefert). Ein Wert ohne woertliche
                   Fundstelle waere geraten - `Tarif.setze()` verlangt genau
                   das nicht.
`anschlusspreis`   Ebenfalls nicht gesetzt - die Kachel zeigt keinen.

Was hier NICHT passiert: kein Feld wird aus dem Tarifnamen abgeleitet, keine
Mindestlaufzeit aus der bekannten Konvention ("Non-Flex-Tarife laufen 24
Monate") uebernommen. Was die Kachel nicht selbst zeigt, bleibt leer -
dieselbe Haltung wie in `tarif_kacheln.py` (o2) und `tarif_ldjson.py` (1&1).

WARUM DIE KACHELN NICHT DOPPELT GEZAEHLT WERDEN
--------------------------------------------------
Dieselben fuenf Kacheln stehen ein zweites Mal auf der Seite - aber nicht als
echtes HTML, sondern als JSON-ESCAPED Text-Kopie innerhalb eines
`<script>`-Blocks (fuer die Client-Hydration). `BeautifulSoup` parst diesen
Block als Text, nicht als Markup: die zweite Kopie erzeugt keine echten
Tag-Objekte mit der gesuchten Klasse und wird deshalb gar nicht erst
gefunden - kein zusaetzlicher Dublettenfilter noetig, anders als bei den
o2-Kacheln (`tarif_kacheln.py`), deren Dublette echtes HTML ist.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

from ..tarif_model import HOCH, PREISTYP_LIVE_SHOP, Tarif, zahl
from .tarif_pdf import dokument_hash

log = logging.getLogger(__name__)

# Der aeussere Kachel-Wrapper: genau EIN CSS-Modul-Hash-Suffix, keine
# weitere Teilbezeichnung. Die Unterknoten ("...__hero__27i7x",
# "...__strike-price__3Py6_") tragen zusaetzlich einen Teilnamen und werden
# von diesem Muster bewusst NICHT getroffen.
_TILE_RE = re.compile(r"^TariffTileModified_TariffTileModified__[A-Za-z0-9]+$")
_NAME_WRAPPER_RE = re.compile(r"TariffTile__name-wrapper")
_STRIKE_RE = re.compile(r"strike-price-value")
_HERO_VALUE_RE = re.compile(r"hero-value")
_HERO_UNLIMITED_RE = re.compile(r"hero-unlimited-top")


def _text(knoten) -> str:
    """Sichtbarer Text, auf einfache Leerzeichen normalisiert.

    Muss mit der Normalisierung in `rohtext` uebereinstimmen - sonst steht
    eine Fundstelle nicht woertlich im Rohtext und `pruefe_belege()` wirft,
    obwohl der Wert sauber gelesen wurde.
    """
    if knoten is None:
        return ""
    roh = knoten if isinstance(knoten, str) else knoten.get_text(" ")
    return " ".join(str(roh).replace("\xa0", " ").split())


def _auswahl_link(kachel) -> str:
    """Der Link "Tarif auswählen" dieser Kachel - die Tiefenadresse."""
    for anker in kachel.find_all("a", href=True):
        if "tariffid=" in anker["href"].lower():
            return anker["href"]
    return ""


def tarif_aus_kachel(kachel, *, anbieter: str, seiten_url: str,
                     abgerufen_am: str) -> Optional[tuple[Tarif, str]]:
    """Eine Tarifkachel wird ein Tarif - oder nichts.

    Nichts wird sie ohne Namen und ohne durchgestrichenen Preis. Die grosse
    "Ø"-Zahl wird bewusst NICHT als Rueckfall genommen (siehe Modul-
    Docstring): sie ist ein bedingter Kombipreis, kein Standalone-Betrag.
    """
    name = _text(kachel.find(class_=_NAME_WRAPPER_RE))
    if not name:
        return None

    strike_text = _text(kachel.find(class_=_STRIKE_RE))
    grundgebuehr = zahl(strike_text)
    if grundgebuehr is None:
        log.info("Telekom-Tarifkachel %r ohne durchgestrichenen Preis - "
                 "verworfen (nur der Ø-Kombipreis waere belegt)", name)
        return None

    href = _auswahl_link(kachel)
    tarif_url = href or seiten_url

    rohtext = _text(kachel)
    if href:
        rohtext = f"{rohtext} | Tarif auswählen: {href}"

    tarif = Tarif(anbieter=anbieter, abgerufen_am=abgerufen_am,
                  rohtext=rohtext, preistyp=PREISTYP_LIVE_SHOP,
                  dokument_url=tarif_url)
    tarif.setze("name", name, name, HOCH)
    tarif.setze("grundgebuehr", grundgebuehr, strike_text, HOCH)

    if kachel.find(class_=_HERO_UNLIMITED_RE) is not None:
        tarif.setze("datenvolumen_gb", float("inf"), "Unlimited", HOCH)
    else:
        hero = kachel.find(class_=_HERO_VALUE_RE)
        hero_text = _text(hero)
        volumen = zahl(hero_text)
        if volumen is not None:
            tarif.setze("datenvolumen_gb", volumen, hero_text, HOCH)

    hash_ = dokument_hash(rohtext)
    tarif.dokument_hash = hash_
    return tarif, hash_


def tarife_aus_html(html: str, *, anbieter: str, seiten_url: str,
                    abgerufen_am: str) -> list[tuple[Tarif, str]]:
    """Alle Tarife, die die Seite in ihren Tarifkacheln zeigt.

    Gleiche Signatur wie `tarif_ldjson.tarife_aus_html` und
    `tarif_kacheln.tarife_aus_html` - der Sammler unterscheidet die
    Lesarten an der `methode` der Quelle, nicht an ihrem Aufrufmuster.
    """
    suppe = BeautifulSoup(html or "", "html.parser")
    out: list[tuple[Tarif, str]] = []
    gesehen: set[str] = set()
    for kachel in suppe.find_all(class_=_TILE_RE):
        ergebnis = tarif_aus_kachel(kachel, anbieter=anbieter,
                                    seiten_url=seiten_url,
                                    abgerufen_am=abgerufen_am)
        if ergebnis is None:
            continue
        tarif, hash_ = ergebnis
        if hash_ in gesehen:
            continue
        gesehen.add(hash_)
        out.append((tarif, hash_))
    return out
