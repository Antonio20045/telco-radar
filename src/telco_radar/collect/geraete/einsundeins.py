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

DER BUENDELKATALOG: DIE PREISKARTE AUF DER GERAETESEITE (B4, 08.09.2026)
-------------------------------------------------------------------------
Die Geraet-x-Tarif-Kombinatorik ueber ALLE Tarife traegt die Seite NICHT
serverseitig - der Konfigurator laedt seine Tariftabelle erst im Browser
nach. Gemessen 08.09.2026: `?chosenTariff=tariff-anf-m-mvl` liefert eine
BYTE-IDENTISCHE Antwort wie die Seite ohne Parameter (326 604 Bytes), das
ld+json bleibt bei "All-Net-Flat S", 44,99. Echte Tarifwaehler gibt es an
dieser Quelle nur im Browser - das ist eine Messgrenze, keine Luecke.

DIE EINMALZAHLUNG DES GERAETS (S2-C, 09.09.2026)
-------------------------------------------------
DIE GERAETE-EINMALZAHLUNG steht in derselben Antwort wie die Preiskarte:
`hwdVariantsOneOffPaymentFees = {"product-COSMIC_ORANGE-256":"360,–", …}`
- dieselben Schluessel wie `hwdVariantsPrices`, Werte als deutsche
Betraege, mit Gedankenstrich statt der Centstelle ("360,-" heisst
360,00 EUR). Die Zuweisung steht hinter der Bedingung
`window.currentHardwareOfferDuration === '36'`: die Einmalzahlung gibt es
NUR bei der 36-Monats-Finanzierung. Fehlt der Block, fehlt die Zahl - und
"nicht genannt" bleibt leer statt 0.00 (dieselbe Regel wie beim
`depositValue` oben).

DER TARIFDETAILS-IFRAME UND DIE BEREITSTELLUNGSGEBUEHR (S2-C, 09.09.2026)
-------------------------------------------------------------------------
Bis zum 08.09.2026 stand hier, der von der Seite verlinkte Tarifdetails-
Iframe sei "eine 48-KB-JavaScript-Huelle ohne einen Preis". Das war falsch
gemessen: Er traegt keinen BUNDELpreis (sein Smartphoneangebot sagt
woertlich "Preis abhängig vom gewählten Smartphone"), sehr aber die
EINMALIGE BEREITSTELLUNGSGEBUEHR des Tarifs - nachgemessen 09.09.2026 an
`/details-all-net-flat-preisliste?chosenTariff=tariff-anf-s-mvl&…`
(HTTP 200, 48 112 B, Absender TelcoRadar/1.0):

    <td><strong>Einmalige Bereitstellungsgebühr</strong></td>
    <td><div><strong>Tarif ohne Smartphone:</strong> 19,90&nbsp;€<br>
        <strong>Tarif mit Smartphone:</strong> 39,90&nbsp;€</div></td>

Die Gebuehr ist TARIFF- und GERATEUNABHAENGIG - gegenprobe mit anderem
Geraet (hw-samsung-galaxy-a57) und anderem Tarif (tariff-anf-m-mvl):
jeweils 19,90/39,90. Erhoben wird sie als `anschlusspreis` auf dem
BUNDEL-Satz (unser Bündel hat immer ein Smartphone, also 39,90) durch
`ergaenze_bereitstellungsgebuehr()` - EIN GET je Tarif-Slug, nicht je
Geraet, die Adresse nimmt der Adapter unverandert aus dem `data-iframe`-
Attribut der Geräteseite (nur verlinkte Adressen). robots.txt (gelesen
09.09.2026): der Pfad ist fuer `User-agent: *` frei - gesperrt sind
/xml/, /static/, /modules/ und Bestellstrecken, nicht /details-all-net-
flat-preisliste.

Was serverseitig da ist, ist die Preiskarte des DEFAULT-Tarifs ueber ALLE
Farben und Speichergroessen - und damit mehr als das ld+json, das nur die
VORAUSGEWAEHLTE Variante bepreist:

    function setHwdPrices() { hwdVariantsPrices = {
        'product-COSMIC_ORANGE-256': [4499,],
        'product-COSMIC_ORANGE-256-bundle-hw-…-WEISS-0': [5399,],
        …

Die Schluessel OHNE `-bundle-`-Segment sind das Tarifbuendel (Wert in
CENT); die mit sind ZUBEHOER-Bundles (AirPods, `data-iframe="/Details
AirPods4"`), kein Tarif - ihr Preis steht HOEHER als der Tarifbund und
wird ueber den Schluessel verworfen, nicht ueber den Betrag. Der Tarifname
desselben Bündels steht in derselben Antwort (`<span id="tariff-
description">1&1 All-Net-Flat S</span>`), seine Slug im eigenen
Tarifdetails-Link (`?chosenTariff=tariff-anf-s-mvl`), seine Laufzeit in
`window.currentHardwareOfferDuration`. Gemessen an zehn Geräteseiten
(08.09.2026): der Default-Tarif ist ueberall die 1&1 All-Net-Flat S, die
Dauer ueberall 36, und der Preis ist bei jeder Farbe derselben
Speichergroesse identisch - je Speichergroesse EIN Satz, die erste Farbe
vertritt ihn (dieselbe Dedupe-Regel wie congstar B3).

DER EINE MONATSBETRAG WIRD NICHT AUFGETEILT (§ 13.2)
----------------------------------------------------
Der Datalayer der Seite nennt eine Aufteilung - und widerlegt sich selbst:
Hardware-Rate 45,00 plus Tarif 14,99 waere 59,99, das Buendel kostet aber
44,99 (ld+json und Preiskarte, beide 256 GB). Die Differenz von 15,00 ist
ein unbenannter Nachlass, der nur im Verbund gilt; bei 512 GB sind es 18,00.
Diese Zahlen in `geraet_monatsrate` und `tarif_monatlich` zu schreiben
waere eine Aufspaltung OHNE Beleg - genau der Fall, fuer den
`tco_model.Buendel.buendel_monatlich` existiert. Der Satz traegt deshalb
NUR den kombinierten Monatsbetrag, dazu die Laufzeit der Hardware-Angebots.

KEINE ZUSAETZLICHEN ABRUFE: `lies_buendel` liest SELBE Antwort, die der
Ernte-Weg fuer die Listung ohnehin holt (`buendel_auf_produktseite` bleibt
an, dasselbe Muster wie Vodafone B1). Der Parameter `?size=` (robots:
erlaubt) wuerde dieselbe Karte je Speichergroesse einzeln liefern - die
Karte steht schon in EINER Antwort, also wird er nicht benutzt.
"""
from __future__ import annotations

import html as html_modul
import logging
import re
import time
from typing import Callable, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from . import GeraeteAbrufFehler
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


# --------------------------------------------------------------------------
# DER BUENDELKATALOG - die Preiskarte der Geräteseite (B4, siehe Modulkopf)
# --------------------------------------------------------------------------

# Der Anfang der serverseitig gerenderten Preiskarte. Ihr Objekt enthaelt
# keine verschachtelten Klammern - der Schnitt am ersten `};` nach dem
# Anfang ist deshalb sicher (und der JS-Quelltext der Seite nutzt dieselbe
# Form an jedem Gerät).
_PREISKARTE_ANFANG = "hwdVariantsPrices = {"

# Ein SCHLUESSEL der Preiskarte ohne Zubehoer-Segment:
# `'product-COSMIC_ORANGE-256': [ 4499, ]`. Das `-bundle-…`-Segment steht
# ZWISCHEN Speicher und schliessendem Anfuehrungszeichen - das Muster
# fordert das Anfuehrungszeichen direkt hinter der Speicherzahl und
# verwirft die Zubehoer-Schluessel deshalb ueber ihre FORM, nicht ueber
# ihren (hoeheren) Betrag.
_PREISKARTE_SCHLUESSEL = re.compile(
    r"'product-(?P<farbe>[A-Z0-9_]+)-(?P<gb>\d+)':\s*\[\s*(?P<cents>\d+)")

# Der Tarifname des Bündels, wie die Seite ihn neben dem Preis setzt.
_TARIF_SPAN_RE = re.compile(
    r'<span id="tariff-description">([^<]*)</span>')

# Die Slug des Tarifs aus dem Tarifdetails-Link, den die Seite selbst
# setzt (`data-iframe="…?chosenTariff=tariff-anf-s-mvl&…"`).
_SLUG_RE = re.compile(r"[?&]chosenTariff=([A-Za-z0-9_.-]+)")

# Der Tarifdetails-Link der Seite (S2-C). Das Attribut nennt die Adresse,
# die der Anbieter selbst fuer die Tarifdetails setzt - relativ, deshalb
# wird sie gegen die Geräteseite aufgeloest. Erstes Vorkommen: die Seite
# setzt denselben Link mehrfach (Konfigurator und Fußnote), und sie sind
# identisch.
_TARIFDETAILS_RE = re.compile(r'data-iframe="(/details-[^"]+)"')


def _preiskarte(text: str) -> str:
    """Der Rumpf der Preiskarte - oder `""`, wenn die Seite keine trägt.

    Wirft nicht: Eine Geräteseite ohne `hwdVariantsPrices` ist ein
    GERAETESEITE-ohne-Preiskarte, und darueber entscheidet `lies_buendel`
    mit einer eigenen, lautenden Ausnahme - hier wird nur geschnitten.
    """
    anfang = (text or "").find(_PREISKARTE_ANFANG)
    if anfang < 0:
        return ""
    ende = text.find("};", anfang)
    if ende < 0:
        return ""
    return text[anfang:ende]


# --------------------------------------------------------------------------
# DIE EINMALZAHLUNG - `hwdVariantsOneOffPaymentFees` (S2-C, Modulkopf)
# --------------------------------------------------------------------------

# Anfang und Schluss derselben Form wie bei der Preiskarte: das Objekt
# enthaelt keine verschachtelten Klammern, der Schnitt am ersten `};` ist
# sicher. Der Block steht hinter `currentHardwareOfferDuration === '36'`
# - fehlt er, gibt es die Einmalzahlung bei diesem Angebot nicht, und
# KEIN Feld wird gefuellt.
_EINMALZAHLUNG_ANFANG = "hwdVariantsOneOffPaymentFees = {"

# `'product-COSMIC_ORANGE-256': "360,–"` - dieselbe SCHLUESSELFORM wie die
# Preiskarte (Zubehoer-Schluessel fallen damit ueber ihre Form, das
# Anfuehrungszeichen direkt hinter der Speicherzahl), der Wert ist ein
# deutscher Betrag ALS ZEICHENKETTE. `zahl()` nimmt ihm En-Gedankenstrich
# und Waehrungszeichen ab.
_EINMALZAHLUNG_SCHLUESSEL = re.compile(
    r"[\"']product-(?P<farbe>[A-Z0-9_]+)-(?P<gb>\d+)[\"']\s*:\s*"
    r"[\"'](?P<wert>[^\"']*)[\"']")


def _einmalzahlungen(text: str) -> dict:
    """Die Geräte-Einmalzahlung je (Farbe in ROHSCHREIBWEISE, GB).

    Leer, wenn die Seite den Block nicht traegt - das ist ein eigener,
    gueltiger Zustand (die Zuweisung steht hinter der Bedingung
    `=== '36'`, Modulkopf) und KEIN Fehler; darueber entscheidet der
    Aufrufer.
    """
    roh = text or ""
    anfang = roh.find(_EINMALZAHLUNG_ANFANG)
    if anfang < 0:
        return {}
    ende = roh.find("};", anfang)
    if ende < 0:
        return {}
    out: dict = {}
    for treffer in _EINMALZAHLUNG_SCHLUESSEL.finditer(roh[anfang:ende]):
        betrag = zahl(treffer.group("wert"))
        if betrag is None:
            continue
        out[(treffer.group("farbe"), int(treffer.group("gb")))] = betrag
    return out


def _tarifname(text: str) -> str:
    """Der Tarif des Bündels aus dem `tariff-description`-Span, alternativ
    aus der ld+json-Beschreibung (derselbe Anbietertext an zwei Stellen)."""
    treffer = _TARIF_SPAN_RE.search(text or "")
    if treffer:
        name = html_modul.unescape(treffer.group(1)).strip()
        if name:
            return name
    for block in ld_json_bloecke(text or ""):
        knoten = block if isinstance(block, dict) else {}
        if knoten.get("@type") != "Product":
            continue
        name = _tarif_aus_beschreibung(knoten.get("description"))
        if name:
            return name
    return ""


# `proben` ist die Schnittstelle der Provider-Probe (FM-2, P5 - siehe
# Adapter-Docstring in collect/geraete/__init__.py); dieser Adapter
# traegt keine Feld-Proben hinein.
def lies_buendel(text: str, url: str = "",
                 proben: Optional[dict] = None) -> list[dict]:
    """Aus einer Geräteseite je SPEICHERGROESSE einen Bündel-Rohsatz.

    Die Karte preist den Default-Tarif der Seite (gemessen an zehn Seiten:
    ueberall die 1&1 All-Net-Flat S) über alle Farben - die erste Farbe
    vertritt ihre Groesse. Der Satz traegt NUR den kombinierten Monatsbetrag
    (`buendel_monatlich`, § 13.2): die Aufteilung der Seite widerspricht
    sich selbst (Modulkopf), und ein Betrag ohne Beleg wird nicht
    aufgespalten.

    Wirft, wenn die Seite gar keine Preiskarte trägt - eine Geräteseite
    ohne `hwdVariantsPrices` ist ein geaendertes Markup, und ein leeres
    Ergebnis waere dafuer die falsche Meldung (dasselbe Muster wie bei
    o2, Telekom und congstar). Eine Karte ohne lesbaren Tarifnamen liefert
    nur ihre leere Ausbeute mit einer Protokollzeile - ein Satz ohne
    benannten Tarif ist bedeutungslos, die Karte darunter kann aber noch
    eine andere Groesse hergeben (der Name steht einmal je Seite, also
    trifft das heute die ganze Seite - gelogt, nicht geworfen).
    """
    karte = _preiskarte(text)
    if not karte:
        raise GeraeteAbrufFehler(
            f"1&1-Geräteseite ohne hwdVariantsPrices ({len(text or '')} Bytes)"
            " - kein Bündelkatalog (Markup geändert?)")

    tarif = tarifname_bereinigt(_tarifname(text))
    if not tarif:
        log.info("1&1: %s nennt keinen Tarifnamen (tariff-description/"
                 "Beschreibung) - Bündelsätze verworfen", url)
        return []
    slug_treffer = _SLUG_RE.search(text or "")
    tarif_slug = slug_treffer.group(1) if slug_treffer else ""
    dauer = laufzeit_monate(text)

    marke, name = _marke_name(text)
    # Die Einmalzahlung desselben Angebots (S2-C, Modulkopf): leer ist
    # ein gueltiger Zustand - der Block steht hinter `=== '36'`.
    einmalzahlungen = _einmalzahlungen(text)
    tarifdetails = _tarifdetails_url(text, url)
    # Fuer die Tarifstufen (29.09.2026, `ergaenze_tarifstufen`): die
    # Geraete-ID der Seite verbindet sie mit den Tarifrastern, und die
    # vorausgewaehlte Groesse samt dem Preis, den die Seite beim Laden
    # ZEIGT, ist die Gegenprobe gegen das Raster des Default-Tarifs.
    hw_id = _hw_id(text)
    vorauswahl = variante(text).get("size") or ""
    angezeigt = _angezeigter_preis(text, hw_id)
    out: list[dict] = []
    gesehen: dict[int, tuple[str, float]] = {}
    for treffer in _PREISKARTE_SCHLUESSEL.finditer(karte):
        gb = int(treffer.group("gb"))
        farbe_roh = treffer.group("farbe")
        farbe = farbe_roh.replace("_", " ").strip().lower()
        betrag = round(int(treffer.group("cents")) / 100.0, 2)
        vorher = gesehen.get(gb)
        if vorher is not None:
            if vorher[1] != betrag:
                # Gemessen kommt das nicht vor (zehn Seiten, je Farbe
                # derselbe Preis) - sollte eine Seite es doch tun, steht
                # es im Protokoll und der ERSTE Eintrag bleibt, statt
                # still die billigste Farbe zu nehmen.
                log.warning("1&1: %s trägt zwei Preise für %d GB (%.2f und "
                            "%.2f) - der erste bleibt", url, gb, vorher[1],
                            betrag)
            continue
        gesehen[gb] = (farbe, betrag)
        if not name:
            continue          # ohne Gerätname kein Titel, also kein Satz
        # DIE EINMALZAHLUNG DES GERAETS, geschluesselt ueber dieselbe
        # Rohschreibweise wie die Preiskarte. Fehlt der Schlussel, bleibt
        # das Feld leer - der Betrag einer ANDEREN Farbe derselben Groesse
        # waere eine Annahme, keine Messung.
        einmalzahlung = einmalzahlungen.get((farbe_roh, gb))
        if einmalzahlungen and einmalzahlung is None:
            log.info("1&1: %s nennt keine Einmalzahlung für %s/%d GB - "
                     "Feld bleibt offen", url, farbe_roh, gb)
        vorausgewaehlt = str(gb) == vorauswahl
        out.append({
            "hw_id": hw_id,
            "vorausgewaehlt": vorausgewaehlt,
            # Nur am vorausgewaehlten Satz: der Preis, den die Seite beim
            # Laden zeigt - MIT einem vorab angehakten Zubehoer-Bundle
            # (`data-auto-add="true"`, gemessen am Galaxy S26 Ultra: 44,99
            # gezeigt, 42,99 in der Preiskarte). Er ist KEIN Buendelpreis
            # und geht in keinen Betrag ein - nur in die Gegenprobe.
            "angezeigt_monatlich": angezeigt if vorausgewaehlt else None,
            "titel": " ".join(x for x in (marke, name, f"{gb} GB", farbe)
                              if x),
            "farbe": farbe,
            "speicher_gb": gb,
            "tarif_name": tarif,
            # Die Ordnung des Anbieters aus dem Tarifdetails-Link (Modulkopf)
            "tarif_slug": tarif_slug,
            # § 13.2: EIN Betrag für Tarif und Gerät - keine Aufspaltung
            # ohne Beleg (der Datalayer widerspricht sich selbst, Modulkopf).
            "buendel_monatlich": betrag,
            # S2-C: die Geräte-Einmalzahlung dieser Variante bei der
            # 36-Monats-Finanzierung - None heisst "nicht genannt", nicht
            # "kostet nichts".
            "geraet_zuzahlung": einmalzahlung,
            "laufzeit_monate": dauer,
            # Der Tarifdetails-Link des ANBIETERS, fuer die
            # Bereitstellungsgebühr (siehe ergaenze_bereitstellungsgebuehr).
            "tarifdetails_url": tarifdetails,
            "url": url,
            "quelle": "einsundeins_buendel",
        })
    return out


def _marke_name(text: str) -> tuple[str, str]:
    """Marke und Modellname aus dem Product-Knoten der Seite.

    Derselbe Knoten, aus dem auch `lies()` baut - zwei Lesarten desselben
    Textes sollen nicht zwei Namen fuer dasselbe Gerät gebären.
    """
    for block in ld_json_bloecke(text or ""):
        knoten = block if isinstance(block, dict) else {}
        typ = knoten.get("@type")
        if typ != "Product" and not (isinstance(typ, list) and "Product" in typ):
            continue
        marke = knoten.get("brand")
        marke_name = (marke.get("name") if isinstance(marke, dict)
                      else marke) or ""
        name = str(knoten.get("name") or "").strip()
        if name:
            return str(marke_name).strip(), name
    return "", ""


# --------------------------------------------------------------------------
# DIE BEREITSTELLUNGSGEBUEHR aus dem Tarifdetails-Iframe (S2-C, Modulkopf)
# --------------------------------------------------------------------------

# Mindestabstand zweier Abrufe derselben Domain - dieselbe Zahl wie der
# `rate_limit_sekunden` des Anbieters in geraete_quellen.yaml und wie
# Vodafones Tarif-Haken (`_TARIF_RATE_LIMIT`).
_GEBUEHR_ABSTAND = 2.0

# Die Gebühr steht in der Tariftabelle des Iframes, wortgleich beim
# Anbieter (Modulkopf). Gesucht wird der Betrag hinter "Tarif MIT
# Smartphone" - das Bündel hat immer ein Gerät; der ohne-Smartphone-Preis
# gehoert zum SIM-only-Tarif und steht im Tarifbestand, nicht hier.
# Das Fenster begrenzt den Satz auf die Zeilen NACH der Überschrift,
# damit nicht ein "Tarif mit Smartphone" aus einem anderen Abschnitt
# Treffer wird.
_GEBUEHR_FENSTER = 2000
_BEREITSTELLUNGS_RE = re.compile(r"Einmalige Bereitstellungsgebühr")
_MIT_SMARTPHONE_RE = re.compile(
    r"Tarif mit Smartphone:?\s*</strong>\s*([^<]{1,40})")


def _tarifdetails_url(text: str, basis_url: str) -> str:
    """Die Adresse des Tarifdetails-Iframes, wie der Anbieter sie setzt."""
    treffer = _TARIFDETAILS_RE.search(text or "")
    if not treffer:
        return ""
    return urljoin(basis_url or "https://mobile.1und1.de",
                   html_modul.unescape(treffer.group(1)))


def bereitstellungsgebuehr(text: str) -> Optional[float]:
    """Die einmalige Bereitstellungsgebühr des Tarifs MIT Smartphone.

    None, wenn die Antwort sie nicht nennt - der Iframe ist auch ohne
    diese Zeile eine gueltige Tarifseite, und ein fehlender Betrag wird
    nie angenommen (E1).
    """
    roh = text or ""
    anfang = _BEREITSTELLUNGS_RE.search(roh)
    if not anfang:
        return None
    treffer = _MIT_SMARTPHONE_RE.search(roh, anfang.end(),
                                        anfang.end() + _GEBUEHR_FENSTER)
    if not treffer:
        return None
    return zahl(html_modul.unescape(treffer.group(1)))


def ergaenze_bereitstellungsgebuehr(hole: Callable, kopfzeilen: dict,
                                    rohbuendel: list) -> int:
    """`anschlusspreis` auf bereits gesammelte 1&1-Bündelsätze setzen.

    EIN GET JE TARIF-SLUG, nicht je Gerät: Die Gebühr ist tarif- und
    geräteunabhängig (gemessen, Modulkopf), und alle heute bekannten
    1&1-Bündel laufen auf demselben Default-Tarif - der Lauf macht also
    EINEN zusaetzlichen Abruf. Die Adresse steht im `tarifdetails_url`-
    Feld der Saetze, unverändert aus dem `data-iframe`-Attribut der
    Geräteseite uebernommen (nur verlinkte Adressen).

    Nicht von `lies_buendel()` selbst aufgerufen: ein Adapter bleibt ein
    reiner Text-zu-Daten-Uebersetzer ohne eigenes Netz (dieselbe Regel
    wie bei `vodafone.loese_tarifnamen`); diese Funktion laeuft ueber
    `Adapter.ergaenze_buendel` aus der Pipeline, NACHDEM alle Anbieter
    gesammelt sind, und mutiert die Saetze in place.

    Ein gescheiterter Abruf laesst die Saetze UNVERAENDERT - keine
    Annahme, kein Default (E1), und ein einziger toter Iframe darf die
    Bündel des Laufs nicht kosten. Zurueck kommt die Zahl der Saetze mit
    neu gesetzter Gebühr.
    """
    # Ein Vertreter je Slug: die erste `tarifdetails_url` dieses Slugs.
    vertreter: dict[str, str] = {}
    for satz in (rohbuendel or []):
        if satz.get("quelle") != "einsundeins_buendel":
            continue
        if satz.get("anschlusspreis") is not None:
            continue
        slug = str(satz.get("tarif_slug") or "").strip()
        adresse = str(satz.get("tarifdetails_url") or "").strip()
        if not slug or not adresse:
            continue
        vertreter.setdefault(slug, adresse)

    gebuehren: dict[str, float] = {}
    letzter = 0.0
    for slug, adresse in sorted(vertreter.items()):
        warte = _GEBUEHR_ABSTAND - (time.monotonic() - letzter)
        if letzter and warte > 0:
            time.sleep(warte)
        letzter = time.monotonic()
        try:
            status, text = hole(adresse, kopfzeilen=kopfzeilen)
        except Exception:                                 # noqa: BLE001
            log.info("1&1: Tarifdetails zu %s nicht abrufbar - "
                     "Bereitstellungsgebühr bleibt offen", slug)
            continue
        if not (200 <= int(status) < 300):
            log.info("1&1: Tarifdetails zu %s mit HTTP %s - "
                     "Bereitstellungsgebühr bleibt offen", slug, status)
            continue
        gebuehr = bereitstellungsgebuehr(text)
        if gebuehr is None:
            log.info("1&1: Tarifdetails zu %s nennen keine "
                     "Bereitstellungsgebühr - Feld bleibt offen", slug)
            continue
        gebuehren[slug] = gebuehr

    gesetzt = 0
    for satz in (rohbuendel or []):
        if satz.get("quelle") != "einsundeins_buendel":
            continue
        if satz.get("anschlusspreis") is not None:
            continue
        slug = str(satz.get("tarif_slug") or "").strip()
        gebuehr = gebuehren.get(slug)
        if gebuehr is None:
            continue
        satz["anschlusspreis"] = gebuehr
        gesetzt += 1
    return gesetzt


# --------------------------------------------------------------------------
# DIE TARIFSTUFEN (29.09.2026): Tarifuebersicht -> Geraeteraster je Tarif
# --------------------------------------------------------------------------
#
# WAS GEMESSEN IST (29.09.2026, HTTP-GET, Absender TelcoRadar/1.0)
# ----------------------------------------------------------------
# Die Geraeteseite preist NUR den Default-Tarif (All-Net-Flat S), mit und
# ohne `?chosenTariff=` byte-gleich im Preis (Modulkopf). Der Tarifwechsel
# der Seite ("Weiter zur Tarifauswahl") ist ein Warenkorb-Schritt
# (`add-to-cart-button`, `startPageFlowId=f2-ssc-hw-private`) - eine
# Bestellstrecke, die hier nicht betreten wird. Serverseitig da ist etwas
# anderes: die Tarifuebersichten `/all-net-flat-vergleich` und
# `/unbegrenztes-datenvolumen` verlinken je Tarif "Mit Handy weiter" auf
# ein GERAETERASTER dieses Tarifs (`targetpage="//mobile.1und1.de/
# smartphones-all-net-flat-m?..."`, dazu `-s`, `-l`, `smartphones-
# unlimited-s/-m/-l` und `/smartphones-unlimited-xl`). Jedes Raster traegt
# fuer alle 43 Geraete EINEN Monatspreis (die vorausgewaehlte Variante),
# den Tarifnamen ("Inkl. 1&1 All-Net-Flat M (50 GB)") und die Laufzeit
# (`data-hardware-months="36"`). robots.txt: keiner dieser Pfade ist
# gesperrt.
#
# DIE RECHNUNG, UND WARUM SIE KEINE ANNAHME IST
# ---------------------------------------------
# Rasterpreis(Tarif T) minus Rasterpreis(All-Net-Flat S) ist am 29.09.2026
# fuer ALLE 43 Geraete derselbe Betrag: M +5,00, L +10,00, Unlimited S
# +5,00, M +10,00, L +15,00 - bei Geraeten von 19,99 bis 69,99 EUR. Der
# Tarifaufschlag haengt also nicht am Geraet, und damit auch nicht an
# seiner Speichergroesse. Nur dann (`einheitlich`) wird er auf JEDE
# Speichergroesse der Geraeteseite uebertragen:
#
#     Buendel(Groesse, T) = Preiskarte(Groesse, S) + Aufschlag(T, Geraet)
#
# Der Aufschlag ist je Geraet GEMESSEN (zwei Rasterpreise desselben
# Geraets), nicht der Mittelwert. Das Raster selbst wird NICHT als
# Buendelpreis uebernommen: es zeigt den Preis MIT einem vorab angehakten
# Zubehoer-Bundle (Galaxy S26 Ultra: Raster S 44,99, Preiskarte 42,99 -
# `data-auto-add="true"`), und Buendel aus Geraet plus Zubehoer werden
# verworfen (CLAUDE.md, Geraeteradar). Die Differenz zweier Raster traegt
# dasselbe Zubehoer auf beiden Seiten und hebt es auf.
#
# Unlimited XL ist NICHT einheitlich (Apple +25,00, alle anderen +30,00):
# dort haengt der Aufschlag am Geraet, und ob er an der Speichergroesse
# haengt, sagt keine serverseitige Zahl. Ein solcher Tarif bekommt nur
# den Satz der VORAUSGEWAEHLTEN Groesse (fuer die der Aufschlag genau
# gemessen ist), und seine Geraete-Einmalzahlung bleibt offen - die
# Einmalzahlungs-Karte der Seite gehoert zum Default-Tarif.
#
# DIE GEGENPROBE je Geraet: der Rasterpreis im Default-Tarif muss dem
# Preis gleichen, den die Geraeteseite beim Laden zeigt, und die Raster-
# laufzeit der der Seite. Sonst sind Raster und Seite nicht dasselbe
# Angebot, und das Geraet bekommt keinen weiteren Tarif.
#
# DIE LAUFZEIT: Alle Raster und alle Geraeteseiten nennen 36 Monate
# ("24 + 12", `/handyvertrag`). Die 24-Monats-Finanzierung waehlt man erst
# im Warenkorb (`hwDurationsAvailable`) - serverseitig steht sie nirgends.
# Sie bleibt eine benannte Luecke, statt geraten zu werden.

# Die zwei Tarifuebersichten, von denen die Raster verlinkt sind. Jede
# Geraeteseite verlinkt sie in ihrer Hauptnavigation ("1&1 Unlimited
# Tarife", "1&1 All-Net-Flat mit 10, 50 oder 150 GB").
TARIFUEBERSICHTEN = (
    "https://mobile.1und1.de/all-net-flat-vergleich",
    "https://mobile.1und1.de/unbegrenztes-datenvolumen",
)

# "Mit Handy weiter": `targetpage="//mobile.1und1.de/smartphones-…?…"`
# oder relativ `targetpage="/smartphones-unlimited-xl?"`. Die Anfrage-
# parameter (`tariffChangeUrl`, `optionalPrecedingDocuments`) fuehren nur
# den Warenkorb zurueck und werden nicht mitgeschickt.
_RASTER_LINK_RE = re.compile(
    r'targetpage="(?P<ziel>(?://mobile\.1und1\.de)?/smartphones-[a-z0-9-]+)')

# Der Tarifdetails-Link je Tarifkachel der Uebersicht: `data-iframe` mit
# `chosenTariff=` und `title="Tarifdetails <Tarifname>"` im selben Tag.
_TAG_RE = re.compile(r"<(?:a|span)\b[^>]*>", re.S)
_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')

_RASTER_FORM_RE = re.compile(r'<form class="hardware-box\b.*?</form>', re.S)
_RASTER_GERAET_RE = re.compile(r'data-hardware-select="([^"]+)"')
_RASTER_MONATE_RE = re.compile(r'data-hardware-months="(\d+)"')
_RASTER_EURO_RE = re.compile(r'-price--euro"[^>]*>\s*(\d+)\s*<')
_RASTER_CENT_RE = re.compile(r'-price--cent"[^>]*>\s*([0-9–-]+)\s*<')
_RASTER_TARIF_RE = re.compile(r"Inkl\.\s*([^<]+)")

_KLAMMERZUSATZ_RE = re.compile(r"\s*\([^()]*\)\s*$")

# So viele Geraete muessen Default- und Tarifraster gemeinsam fuehren, bevor
# ein gleicher Aufschlag als "einheitlich" gilt und auf alle Speichergroessen
# uebertragen wird. Gemessen am 29.09.2026: 43 gemeinsame Geraete je Raster.
_MINDEST_GERAETE_EINHEITLICH = 5
HERLEITUNG_TARIFAUFSCHLAG = "tarifaufschlag_aus_tarifraster"


def tarifname_bereinigt(name: str) -> str:
    """"1&1 All-Net-Flat M (50 GB)" -> "1&1 All-Net-Flat M".

    Das Raster haengt das Volumen in Klammern an; der Tarifbestand fuehrt
    den Namen ohne (`/handytarife`), und `tarif_bezug` loest nur den auf.
    """
    text = " ".join(html_modul.unescape(name or "").split())
    return _KLAMMERZUSATZ_RE.sub("", text).strip()


def _hw_id(text: str) -> str:
    treffer = re.search(r"window\.productId\s*=\s*'([^']+)'", text or "")
    return treffer.group(1) if treffer else ""


def _cent(euro: str, cent: str) -> int:
    rest = cent.strip()
    return int(euro) * 100 + (0 if rest in ("–", "-") else int(rest))


def _angezeigter_preis(text: str, hw_id: str) -> Optional[float]:
    """Der Monatspreis, den die Geraeteseite serverseitig anzeigt."""
    if not hw_id:
        return None
    kopf = re.escape(hw_id)
    euro = re.search(rf'id="{kopf}--price__digits">\s*(\d+)\s*<', text or "")
    cent = re.search(rf'id="{kopf}--price__decimals"[^>]*>\s*([0-9–-]+)\s*<',
                     text or "")
    if not (euro and cent):
        return None
    return _cent(euro.group(1), cent.group(1)) / 100.0


def tarifraster_adressen(text: str, basis_url: str) -> list[str]:
    """Die Geraeteraster, die eine Tarifuebersicht verlinkt."""
    out: list[str] = []
    for treffer in _RASTER_LINK_RE.finditer(text or ""):
        ziel = urljoin(basis_url or "https://mobile.1und1.de",
                       treffer.group("ziel"))
        if ziel not in out:
            out.append(ziel)
    return out


def tarifdetails_je_tarif(text: str, basis_url: str) -> dict:
    """{Tarifname: (Tarifdetails-Adresse, Slug)} aus einer Tarifuebersicht."""
    out: dict = {}
    for tag in _TAG_RE.findall(text or ""):
        attrs = dict(_ATTR_RE.findall(tag))
        ziel = html_modul.unescape(attrs.get("data-iframe", ""))
        titel = html_modul.unescape(attrs.get("title", ""))
        if "/details-" not in ziel or not titel.startswith("Tarifdetails "):
            continue
        slug = _SLUG_RE.search(ziel)
        if not slug:
            continue
        name = tarifname_bereinigt(titel[len("Tarifdetails "):])
        out.setdefault(name, (urljoin(basis_url, ziel), slug.group(1)))
    return out


def lies_tarifraster(text: str) -> dict:
    """Ein Geraeteraster: Tarifname und je Geraete-ID (Cent, Monate).

    Wirft, wenn die Seite keine Geraetekachel traegt - ein leeres Raster
    ist ein geaendertes Markup und nicht "dieser Tarif hat keine Geraete".
    Nennen die Kacheln verschiedene Tarife, ist der Name leer.
    """
    namen: set = set()
    preise: dict = {}
    for form in _RASTER_FORM_RE.findall(text or ""):
        geraet = _RASTER_GERAET_RE.search(form)
        euro = _RASTER_EURO_RE.search(form)
        cent = _RASTER_CENT_RE.search(form)
        if not (geraet and euro and cent):
            continue
        monate = _RASTER_MONATE_RE.search(form)
        tarif = _RASTER_TARIF_RE.search(form)
        if tarif:
            namen.add(tarifname_bereinigt(tarif.group(1)))
        preise[geraet.group(1)] = (
            _cent(euro.group(1), cent.group(1)),
            int(monate.group(1)) if monate else None)
    if not preise:
        raise GeraeteAbrufFehler(
            f"1&1-Geräteraster ohne hardware-box-Kachel "
            f"({len(text or '')} Bytes) - Markup geändert?")
    if len(namen) != 1:
        log.warning("1&1: Geräteraster nennt %d Tarifnamen (%s) - verworfen",
                    len(namen), ", ".join(sorted(namen)))
    return {"tarif_name": next(iter(namen)) if len(namen) == 1 else "",
            "preise": preise}


def _hole_text(hole: Callable, kopfzeilen: dict, adresse: str
               ) -> Optional[str]:
    """Ein Abruf; None bei Fehler - protokolliert, nie still."""
    try:
        status, text = hole(adresse, kopfzeilen=kopfzeilen)
    except Exception as exc:                              # noqa: BLE001
        log.warning("1&1: %s nicht abrufbar (%s)", adresse, exc)
        return None
    if not (200 <= int(status) < 300):
        log.warning("1&1: %s mit HTTP %s", adresse, status)
        return None
    return text


def ergaenze_tarifstufen(hole: Callable, kopfzeilen: dict,
                         rohbuendel: list) -> int:
    """Aus den Default-Tarif-Saetzen die Saetze der uebrigen Tarifstufen.

    Rechnung, Gegenprobe und Grenzen stehen im Kopf dieses Abschnitts.
    Abrufe: die zwei Tarifuebersichten plus ein Raster je verlinktem
    Tarif (am 29.09.2026: 2 + 7). Haengt die neuen Saetze an `rohbuendel`
    an und gibt ihre Zahl zurueck. Ein fehlendes Default-Raster heisst:
    nichts herleiten - ohne die Gegenprobe ist ein Aufschlag keiner.
    """
    basis = [s for s in (rohbuendel or [])
             if s.get("quelle") == "einsundeins_buendel"
             and not s.get("herleitung") and s.get("hw_id")]
    if not basis:
        return 0
    basistarife = {s.get("tarif_name") for s in basis}
    if len(basistarife) != 1:
        log.warning("1&1: Geräteseiten nennen %d Default-Tarife (%s) - "
                    "keine Tarifstufen hergeleitet", len(basistarife),
                    ", ".join(sorted(map(str, basistarife))))
        return 0
    basistarif = basistarife.pop()
    je_geraet: dict = {}
    for satz in basis:
        je_geraet.setdefault(satz["hw_id"], []).append(satz)

    raster_adressen: list[str] = []
    details: dict = {}
    for uebersicht in TARIFUEBERSICHTEN:
        text = _hole_text(hole, kopfzeilen, uebersicht)
        if text is None:
            continue
        for adresse in tarifraster_adressen(text, uebersicht):
            if adresse not in raster_adressen:
                raster_adressen.append(adresse)
        for name, wert in tarifdetails_je_tarif(text, uebersicht).items():
            details.setdefault(name, wert)

    raster: dict = {}
    for adresse in raster_adressen:
        text = _hole_text(hole, kopfzeilen, adresse)
        if text is None:
            continue
        try:
            gelesen = lies_tarifraster(text)
        except GeraeteAbrufFehler as exc:
            log.warning("1&1: %s: %s", adresse, exc)
            continue
        if gelesen["tarif_name"]:
            raster.setdefault(gelesen["tarif_name"], (adresse, gelesen))

    if basistarif not in raster:
        log.warning("1&1: kein Geräteraster für den Default-Tarif %s - "
                    "keine Tarifstufen hergeleitet (%d Raster gelesen)",
                    basistarif, len(raster))
        return 0
    _, basisraster = raster[basistarif]

    vorhanden = {(s.get("sku_id"), s.get("tarif_name"),
                  s.get("laufzeit_monate")) for s in rohbuendel}
    neu: list[dict] = []
    for tarif, (adresse, gelesen) in sorted(raster.items()):
        if tarif == basistarif:
            continue
        aufschlaege = {
            hw: preis[0] - basisraster["preise"][hw][0]
            for hw, preis in gelesen["preise"].items()
            if hw in basisraster["preise"]}
        # Einheitlich heisst: an genug Geraeten gemessen gleich. Ein
        # einziges gemeinsames Geraet waere trivial "einheitlich".
        einheitlich = (len(aufschlaege) >= _MINDEST_GERAETE_EINHEITLICH
                       and len(set(aufschlaege.values())) == 1)
        detail_url, slug = details.get(tarif, ("", ""))
        unstimmig = 0
        for hw, saetze in sorted(je_geraet.items()):
            if hw not in aufschlaege:
                continue
            vorher = next((s for s in saetze if s.get("vorausgewaehlt")),
                          None)
            basis_cent, basis_monate = basisraster["preise"][hw]
            monate = gelesen["preise"][hw][1]
            angezeigt = vorher.get("angezeigt_monatlich") if vorher else None
            if (angezeigt is None or round(angezeigt * 100) != basis_cent
                    or monate is None or monate != basis_monate
                    or monate != vorher.get("laufzeit_monate")):
                unstimmig += 1
                continue
            ziele = saetze if einheitlich else [vorher]
            for satz in ziele:
                schluessel = (satz.get("sku_id"), tarif, monate)
                if schluessel in vorhanden:
                    continue
                vorhanden.add(schluessel)
                cent = round(satz["buendel_monatlich"] * 100) + aufschlaege[hw]
                kopie = {k: v for k, v in satz.items()
                         if k not in ("angezeigt_monatlich", "anschlusspreis")}
                kopie.update({
                    "tarif_name": tarif,
                    "tarif_slug": slug,
                    "tarifdetails_url": detail_url,
                    "buendel_monatlich": round(cent / 100.0, 2),
                    "laufzeit_monate": monate,
                    # Die Einmalzahlungs-Karte der Geraeteseite gehoert zum
                    # Default-Tarif, und das Raster nennt keine. Ein
                    # einheitlicher MONATSaufschlag sagt nichts ueber die
                    # Einmalzahlung eines anderen Tarifs - sie bleibt eine
                    # benannte Luecke (Clean Code 3), nicht uebertragen.
                    "geraet_zuzahlung": None,
                    "herleitung": HERLEITUNG_TARIFAUFSCHLAG,
                    "url": adresse,
                    "quelle_url": adresse,
                })
                neu.append(kopie)
        log.info("1&1: %s - Aufschlag %s, %s%s", tarif,
                 "einheitlich" if einheitlich else "geräteabhängig",
                 "alle Speichergrößen" if einheitlich
                 else "nur die vorausgewählte Größe",
                 f", {unstimmig} Geräte ohne passende Gegenprobe"
                 if unstimmig else "")
    rohbuendel.extend(neu)
    return len(neu)


def ergaenze_buendel(hole: Callable, kopfzeilen: dict,
                     rohbuendel: list) -> int:
    """Der Nachbearbeitungs-Haken: erst die Tarifstufen, dann die
    Bereitstellungsgebühr fuer ALLE Saetze (auch die neuen Tarife).
    Zurueck kommt die Zahl der Saetze mit gesetzter Gebühr."""
    neu = ergaenze_tarifstufen(hole, kopfzeilen, rohbuendel)
    if neu:
        log.info("1&1: %d Bündel-Sätze weiterer Tarifstufen hergeleitet", neu)
    return ergaenze_bereitstellungsgebuehr(hole, kopfzeilen, rohbuendel)


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
