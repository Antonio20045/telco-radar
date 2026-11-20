"""1&1: der Monatspreis des BUENDELS (seit 20.11.2026 nur noch Leser der Tests).

Preise misst nur der Klick-Lauf (config/klickkarten/1und1.yaml, alle Tarife der
Tarifauswahl); `register.py` verdrahtet `lies_buendel` nicht mehr (Testleser).

1&1 verkauft Geraete nur im Tarifbund - es gibt keinen Barpreis zu
verschweigen. Jeder Satz traegt deshalb NUR `buendel_monatlich`
(Geraet+Tarif kombiniert) und `tarif_name`, nie eine Aufspaltung in
`geraet_monatsrate`/`tarif_monatlich` (§ 13.2): die Seite nennt oft eine
Aufteilung, die sich widerspricht (45,00+14,99=59,99 bei einem Buendel
von 44,99 - der Rabatt gilt nur im Verbund). Ohne lesbaren Tarifnamen
wird der Satz verworfen (`Listung.__post_init__` ohnehin).

MARKUP-STAND 20.11.2026 (K1, Befund A-72ZCSS): die Preiskarte heisst
jetzt `window.hwdVariantsHardwarePrices`, JSON mit Schluesseln
`product-FARBE-GB`, aber je Schluessel VERSCHACHTELT nach Finanzierungs-
dauer ("24", "36", "1") und darunter nach "fix"/"flex" (Zubehoer-Bundles
tragen andere, hw_id-basierte Schluessel in `hwdBundleOfferPrices` und
tauchen hier nie auf). Die alte flache Preiskarte (`_alte_preiskarte`,
Cent-Array) bleibt als Rueckfallstufe fuer Seiten von VOR K1.

NUR "fix" IST OHNE "24+12" BELEGBAR: "flex" verlaengert die Geraeteraten
freiwillig um 12 Monate ("24 + 12 Monate Flex", "36 + 12 Monate Flex"),
ihre `tariffMonthlyPrices` laufen bis Laufzeit+12. "fix" ist fuer GENAU
seine Laufzeit flach und springt danach auf den Listenpreis -
gegengeprueft ueber dem ersten Eintrag von `tariffMonthlyPrices` (deckt
Monat 1 bis mindestens zur Laufzeit zum Betrag aus `tariffPricePerMonth`)
und, wo die Karte ihn nennt, ueber `hardwareTotalPrice` = Laufzeit mal
Rate. Gelesen werden deshalb nur "fix 24" und "fix 36", die zwei
Laufzeiten, die die Seite als "24 Monate Fix"/"36 Monate Fix" zeigt; eine
Abweichung bleibt unbelegt und wird verworfen.

NUR DER TARIF DER SEITE IST GEMESSEN (Stand 20.11.2026): die Geraeteseite
traegt einen einzigen Tarif (`hwdTariffName`, All-Net-Flat S); der Tarif
wird erst im Bestellweg nach "Weiter zur Tarifauswahl" gewaehlt (Warenkorb).
Der Tarifnachlass haengt dabei an Geraet, Speicher UND Laufzeit (iPhone 17
Pro Max fix 24: 9,99 bei 256 GB, 13,99 bei 512 GB) - eine Uebertragung
eines Aufschlags auf andere Speicher oder Tarife ist deshalb nicht belegt
und entfaellt. Andere Tarife sind eine benannte Luecke, keine Rechnung.

SICHTPROBE: die Seite rendert die Geraeteraten der vorausgewaehlten
Variante serverseitig in den Laufzeitschaltern (`data-term`,
`data-monthly-amount`, `value="24-fix"`). Nennt ein Schalter eine andere
Rate als die Preiskarte, gilt die Laufzeit auf dieser Seite als unbelegt
(`sichtbare_geraeteraten`).

Tarifname/Marke/Modell kommen aus demselben Datalayer (`tariff.external
name`, `hardware.brand`/`name`) - der `tariff-description`-Span und das
`application/ld+json`-Product dafuer stehen auf keiner gemessenen Seite
mehr, bleiben aber als Rueckfallstufe im Code. `hwdVariantsOneOffPayment
Fees` (Einmalzahlung) und der `data-iframe`-Link zur Bereitstellungs-
gebuehr fehlen ebenfalls; beide degradieren ohne ihren Textmarker auf
`None`/`""` (E1) statt eine falsche Zahl anzunehmen.
"""

from __future__ import annotations

import html as html_modul
import json
import logging
import re
import time
from collections.abc import Callable
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ...tarif_model import zahl
from ..tarif_ldjson import ld_json_bloecke
from . import einsundeins_raten as ER
from .basis import GeraeteAbrufFehler

log = logging.getLogger(__name__)

_TARIF_RE = re.compile(r"\bmit\s+(?P<tarif>\S.*?)\s*$", re.I)

_VARIANTE_RE = re.compile(
    r"window\.currentProductVariants\s*\[[^\]]+\]\s*=\s*\{(?P<rumpf>[^}]*)\}", re.S
)
_FELD_RE = re.compile(r"['\"](?P<feld>\w+)['\"]\s*:\s*['\"](?P<wert>[^'\"]*)['\"]")

_LAUFZEIT_RE = re.compile(
    r"window\.currentHardwareOfferDuration\s*=\s*['\"](?P<monate>\d+)['\"]"
)

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
    return {
        m.group("feld"): m.group("wert")
        for m in _FELD_RE.finditer(treffer.group("rumpf"))
    }


def laufzeit_monate(html: str) -> int | None:
    """Die Bindungsdauer des Hardware-Angebots, wie die Seite sie nennt."""
    treffer = _LAUFZEIT_RE.search(html or "")
    if not treffer:
        return None
    monate = int(treffer.group("monate"))
    return monate if monate > 0 else None


_KACHEL_KLASSE = "hardware-box__heading"


def ernte(text: str, basis_url: str, pfadmuster="", kind: str = "") -> list[str]:
    """Aus der Kategorieseite die Produktadressen - eine je Geraet.

    `mobile.1und1.de/smartphones` traegt neben Produktseiten auch Haupt-
    navigation, Themenseiten und Zubehoer-Auflagen ohne gemeinsamen
    Pfadteil - ein Pfadmuster allein hilft nicht. Gelesen wird deshalb
    das, was die Seite selbst als Katalogkachel auszeichnet:
    `<a class="hardware-box__heading">`, keine eigene Konstruktion.

    `pfadmuster` wirkt zusaetzlich, wenn eines konfiguriert ist - dieselbe
    Bedeutung wie in `ernte_links`.
    """
    muster = (
        [m for m in pfadmuster if m]
        if isinstance(pfadmuster, (list, tuple))
        else ([pfadmuster] if pfadmuster else [])
    )
    suppe = BeautifulSoup(text or "", "html.parser")
    out: list[str] = []
    gesehen: set[str] = set()
    for anker in suppe.find_all("a", href=True):
        if _KACHEL_KLASSE not in (anker.get("class") or []):
            continue
        ziel = urljoin(basis_url or "https://mobile.1und1.de", anker["href"]).split(
            "#", 1
        )[0]
        if muster and not all(m in ziel for m in muster):
            continue
        if ziel in gesehen:
            continue
        gesehen.add(ziel)
        out.append(ziel)
    if not out:
        log.warning(
            "1&1: %s traegt keine %s-Kachel (%d Bytes) - "
            "Raster leer oder Markup geaendert",
            basis_url,
            _KACHEL_KLASSE,
            len(text or ""),
        )
    return out


_HARDWAREPREISKARTE_ANFANG = "window.hwdVariantsHardwarePrices = "

_VARIANTSCHLUESSEL_RE = re.compile(r"^product-(?P<farbe>[A-Z0-9_]+)-(?P<gb>\d+)$")

_PRODUKTE_ANFANG = "const products = ["

_TARIF_SPAN_RE = re.compile(r'<span id="tariff-description">([^<]*)</span>')

_SLUG_RE = re.compile(r"[?&]chosenTariff=([A-Za-z0-9_.-]+)")

_TARIFDETAILS_RE = re.compile(r'data-iframe="(/details-[^"]+)"')


def _json_rumpf(text: str, anfang_marke: str, klammer_auf: str, klammer_zu: str) -> str:
    """Rumpf eines `window.x = {...};`-Literals bis zum ersten `klammer_zu;`."""
    roh = text or ""
    anfang = roh.find(anfang_marke)
    if anfang < 0:
        return ""
    start = anfang + len(anfang_marke) - 1
    ende = roh.find(klammer_zu + ";", start)
    if ende < 0:
        return ""
    return roh[start : ende + 1]


def _hardwarepreiskarte(text: str) -> dict:
    """{'product-FARBE-GB': {Laufzeit: {'fix': {...}}}}; `{}` ohne den
    Marker oder bei kaputtem JSON."""
    rumpf = _json_rumpf(text, _HARDWAREPREISKARTE_ANFANG, "{", "}")
    if not rumpf:
        return {}
    try:
        geladen = json.loads(rumpf)
    except ValueError:
        return {}
    return geladen if isinstance(geladen, dict) else {}


_ALT_PREISKARTE_ANFANG = "hwdVariantsPrices = {"

_ALT_PREISKARTE_SCHLUESSEL = re.compile(
    r"'product-(?P<farbe>[A-Z0-9_]+)-(?P<gb>\d+)':\s*\[\s*(?P<cents>\d+)"
)


def _alte_preiskarte(text: str) -> dict:
    """Rueckfallstufe fuer Seiten von VOR K1: liefert dieselbe Schluessel-
    form wie `_hardwarepreiskarte`, mit Platzhalter fuer `_preis_je_
    schluessel`; `{}` ohne den alten Marker."""
    anfang = (text or "").find(_ALT_PREISKARTE_ANFANG)
    if anfang < 0:
        return {}
    ende = text.find("};", anfang)
    if ende < 0:
        return {}
    out: dict = {}
    for treffer in _ALT_PREISKARTE_SCHLUESSEL.finditer(text[anfang:ende]):
        schluessel = f"product-{treffer.group('farbe')}-{treffer.group('gb')}"
        out.setdefault(schluessel, {"_alt_cent": int(treffer.group("cents"))})
    return out


def _preis_je_schluessel(eintrag: dict, dauer: int) -> tuple[float, float] | None:
    """(Hardware-, Tarifrate) ueber `_fixpreis`, ausser bei einem Eintrag
    aus `_alte_preiskarte` (ein Cent-Betrag ohne Aufteilung)."""
    if "_alt_cent" in eintrag:
        return round(eintrag["_alt_cent"] / 100.0, 2), 0.0
    return _fixpreis(eintrag, dauer)


def _datalayer(text: str) -> dict:
    """{'hardware': Posten, 'tariff': Posten} aus `const products = [...]`
    (GA4-Schema, Modulkopf); nennt auch `contractduration`."""
    rumpf = _json_rumpf(text, _PRODUKTE_ANFANG, "[", "]")
    if not rumpf:
        return {}
    try:
        eintraege = json.loads(rumpf)
    except ValueError:
        return {}
    if not isinstance(eintraege, list):
        return {}
    out: dict = {}
    for eintrag in eintraege:
        produkt = (eintrag or {}).get("product") if isinstance(eintrag, dict) else None
        if not isinstance(produkt, dict):
            continue
        typ = produkt.get("type")
        if typ in ("hardware", "tariff") and typ not in out:
            out[typ] = produkt
    return out


LAUFZEITEN_FIX = (24, 36)
"""Die Laufzeiten, die die Geraeteseite als "24 Monate Fix"/"36 Monate Fix"
zeigt; "flex" (+12) wird nie gelesen (Modulkopf)."""

_SCHALTER_RE = re.compile(r"<input\b[^>]*\bdata-term=[^>]*>", re.S)
_SCHALTER_ATTR_RE = re.compile(r'(data-term|data-monthly-amount|value)="([^"]*)"')


def sichtbare_geraeteraten(text: str) -> dict[int, float]:
    """{Laufzeit: Geraeterate} der "fix"-Schalter, wie die Seite sie fuer die
    vorausgewaehlte Variante serverseitig zeigt (Modulkopf, SICHTPROBE)."""
    out: dict[int, float] = {}
    for tag in _SCHALTER_RE.findall(text or ""):
        attrs = dict(_SCHALTER_ATTR_RE.findall(tag))
        term = attrs.get("data-term", "")
        if attrs.get("value") != f"{term}-fix" or not term.isdigit():
            continue
        rate = zahl(attrs.get("data-monthly-amount", ""))
        if rate is not None:
            out.setdefault(int(term), rate)
    return out


def _fixpreis(karteneintrag: dict, dauer: int) -> tuple[float, float] | None:
    """(Hardware-, Tarifrate/Monat) der "fix"-Stufe zu `dauer`, nur bei
    belegter Flachheit und, wo genannt, `hardwareTotalPrice` = `dauer`
    Raten (Modulkopf); sonst `None`."""
    stufe = (karteneintrag or {}).get(str(dauer), {})
    stufe = stufe.get("fix") if isinstance(stufe, dict) else None
    if not isinstance(stufe, dict):
        return None
    hardwarerate = zahl(str(stufe.get("hardwarePricePerMonth")))
    tarifrate = ER.flache_tarifrate(stufe, dauer)
    if hardwarerate is None or tarifrate is None:
        return None
    gesamt_genannt = stufe.get("hardwareTotalPrice") is not None
    if gesamt_genannt and ER.raten(stufe, hardwarerate) != dauer:
        return None
    return hardwarerate, tarifrate


_EINMALZAHLUNG_ANFANG = "hwdVariantsOneOffPaymentFees = {"

_EINMALZAHLUNG_SCHLUESSEL = re.compile(
    r"[\"']product-(?P<farbe>[A-Z0-9_]+)-(?P<gb>\d+)[\"']\s*:\s*"
    r"[\"'](?P<wert>[^\"']*)[\"']"
)


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


_DATALAYER_SLUG_RE = re.compile(r"^tariff-[a-z0-9-]+$")


def _datalayer_slug(text: str) -> str:
    """Der Tarif-Slug aus `tariff.name` des Datalayers ("tariff-anf-s-mvl"),
    seit K1 der einzige Ort, an dem die Seite ihn nennt; sonst ""."""
    name = str((_datalayer(text).get("tariff") or {}).get("name") or "").strip()
    return name if _DATALAYER_SLUG_RE.match(name) else ""


def _tarifname(text: str) -> str:
    """Tarifname aus `tariff.externalname` (Modulkopf), sonst Span/ld+json."""
    tarifposten = _datalayer(text).get("tariff") or {}
    name = (tarifposten.get("tariff") or {}).get("externalname")
    if name:
        name = str(name).strip()
        if name:
            return name
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


def lies_buendel(text: str, url: str = "", proben: dict | None = None) -> list[dict]:
    """Aus einer Geräteseite je SPEICHERGROESSE und Laufzeit einen Bündel-Rohsatz.

    Die Karte preist den Tarif der Seite ueber alle Farben - die erste Farbe
    vertritt ihre Groesse. Je Groesse entsteht ein Satz fuer jede Laufzeit aus
    `LAUFZEITEN_FIX` mit belegtem "fix"-Preis (Modulkopf); die alte Karte vor
    K1 kennt nur ihre eine Laufzeit. Der Satz traegt NUR den kombinierten
    Monatsbetrag (`buendel_monatlich`, § 13.2).

    Wirft, wenn die Seite gar keine Preiskarte trägt (altes wie neues
    Markup, Modulkopf) - ein leeres Ergebnis waere dafuer die falsche
    Meldung (dasselbe Muster wie bei o2, Telekom und congstar). Ohne
    lesbaren Tarifnamen oder (alte Karte) ohne Laufzeit liefert sie nur ihre
    leere Ausbeute mit einer Protokollzeile.
    """
    karte = _hardwarepreiskarte(text)
    laufzeiten: tuple = LAUFZEITEN_FIX if karte else ()
    if not karte:
        karte = _alte_preiskarte(text)
        dauer = laufzeit_monate(text)
        laufzeiten = (dauer,) if dauer is not None else ()
    if not karte:
        raise GeraeteAbrufFehler(
            f"1&1-Geräteseite ohne hwdVariantsHardwarePrices ({len(text or '')} Bytes)"
            " - kein Bündelkatalog (Markup geändert?)"
        )

    tarif = tarifname_bereinigt(_tarifname(text))
    if not tarif:
        log.info(
            "1&1: %s nennt keinen Tarifnamen (Datalayer/tariff-description/"
            "Beschreibung) - Bündelsätze verworfen",
            url,
        )
        return []
    if not laufzeiten:
        log.info(
            "1&1: %s nennt keine Laufzeit (currentHardwareOfferDuration) - "
            "Bündelsätze verworfen",
            url,
        )
        return []
    laufzeiten = _sichtprobe(text, karte, laufzeiten, url)
    slug_treffer = _SLUG_RE.search(text or "")
    tarif_slug = slug_treffer.group(1) if slug_treffer else _datalayer_slug(text)

    marke, name = _marke_name(text)
    einmalzahlungen = _einmalzahlungen(text)
    tarifdetails = _tarifdetails_url(text, url)
    out: list[dict] = []
    gesehen: dict[tuple[int, int], float] = {}
    for schluessel, eintrag in karte.items():
        treffer = _VARIANTSCHLUESSEL_RE.match(schluessel)
        if not treffer:
            continue
        gb = int(treffer.group("gb"))
        farbe_roh = treffer.group("farbe")
        farbe = farbe_roh.replace("_", " ").strip().lower()
        for dauer in laufzeiten:
            preis = _preis_je_schluessel(eintrag, dauer)
            if preis is None:
                log.info(
                    "1&1: %s/%s ohne belegten Flachpreis zu %d Monaten - "
                    "Laufzeit offen",
                    url,
                    schluessel,
                    dauer,
                )
                continue
            betrag = round(sum(preis), 2)
            vorher = gesehen.get((gb, dauer))
            if vorher is not None:
                if vorher != betrag:
                    log.warning(
                        "1&1: %s trägt zwei Preise für %d GB/%d Monate (%.2f "
                        "und %.2f) - der erste bleibt",
                        url,
                        gb,
                        dauer,
                        vorher,
                        betrag,
                    )
                continue
            gesehen[(gb, dauer)] = betrag
            if not name:
                continue
            einmalzahlung = _einmalzahlung(einmalzahlungen, farbe_roh, gb, url)
            out.append(
                {
                    "titel": " ".join(x for x in (marke, name, f"{gb} GB", farbe) if x),
                    "farbe": farbe,
                    "speicher_gb": gb,
                    "tarif_name": tarif,
                    "tarif_slug": tarif_slug,
                    "buendel_monatlich": betrag,
                    "geraet_zuzahlung": einmalzahlung,
                    "laufzeit_monate": dauer,
                    "tarifdetails_url": tarifdetails,
                    "url": url,
                    "quelle": "einsundeins_buendel",
                }
            )
    return out


def _einmalzahlung(einmalzahlungen: dict, farbe_roh: str, gb: int, url: str):
    """Die Einmalzahlung der Variante; fehlt sie in einem vorhandenen Block,
    bleibt das Feld offen und meldet sich."""
    einmalzahlung = einmalzahlungen.get((farbe_roh, gb))
    if einmalzahlungen and einmalzahlung is None:
        log.info(
            "1&1: %s nennt keine Einmalzahlung für %s/%d GB - Feld bleibt offen",
            url,
            farbe_roh,
            gb,
        )
    return einmalzahlung


def _sichtprobe(text: str, karte: dict, laufzeiten: tuple, url: str) -> tuple:
    """Die Laufzeiten, deren sichtbare Geraeterate der Preiskarte nicht
    widerspricht (Modulkopf, SICHTPROBE). Ohne Schalter (alte Karte) bleibt
    alles; ohne vorausgewaehlte Variante in der Karte gibt es nichts zu
    vergleichen."""
    sichtbar = sichtbare_geraeteraten(text)
    var = variante(text)
    eintrag = karte.get(f"product-{var.get('color', '')}-{var.get('size', '')}")
    if not sichtbar or not isinstance(eintrag, dict):
        return laufzeiten
    bleiben = []
    for dauer in laufzeiten:
        preis = _preis_je_schluessel(eintrag, dauer)
        gezeigt = sichtbar.get(dauer)
        if preis is not None and gezeigt is not None and round(preis[0], 2) != gezeigt:
            log.warning(
                "1&1: %s zeigt %d Monate Fix zu %.2f, die Preiskarte nennt %.2f "
                "- Laufzeit auf dieser Seite unbelegt",
                url,
                dauer,
                gezeigt,
                preis[0],
            )
            continue
        bleiben.append(dauer)
    return tuple(bleiben)


def _marke_name(text: str) -> tuple[str, str]:
    """Marke/Modell aus dem `hardware`-Posten (Modulkopf), sonst ld+json."""
    hardwareposten = _datalayer(text).get("hardware") or {}
    marke_name = str((hardwareposten.get("hardware") or {}).get("brand") or "").strip()
    name = str(hardwareposten.get("name") or "").strip()
    if name:
        if marke_name and name.lower().startswith(marke_name.lower() + " "):
            name = name[len(marke_name) :].strip()
        return marke_name, name
    for block in ld_json_bloecke(text or ""):
        knoten = block if isinstance(block, dict) else {}
        typ = knoten.get("@type")
        if typ != "Product" and not (isinstance(typ, list) and "Product" in typ):
            continue
        marke = knoten.get("brand")
        marke_name = (marke.get("name") if isinstance(marke, dict) else marke) or ""
        name = str(knoten.get("name") or "").strip()
        if name:
            return str(marke_name).strip(), name
    return "", ""


_GEBUEHR_ABSTAND = 2.0

_GEBUEHR_FENSTER = 2000
_BEREITSTELLUNGS_RE = re.compile(r"Einmalige Bereitstellungsgebühr")
_MIT_SMARTPHONE_RE = re.compile(r"Tarif mit Smartphone:?\s*</strong>\s*([^<]{1,40})")


def _tarifdetails_url(text: str, basis_url: str) -> str:
    """Die Adresse des Tarifdetails-Iframes, wie der Anbieter sie setzt."""
    treffer = _TARIFDETAILS_RE.search(text or "")
    if not treffer:
        return ""
    return urljoin(
        basis_url or "https://mobile.1und1.de", html_modul.unescape(treffer.group(1))
    )


def bereitstellungsgebuehr(text: str) -> float | None:
    """Die einmalige Bereitstellungsgebühr des Tarifs MIT Smartphone.

    None, wenn die Antwort sie nicht nennt - der Iframe ist auch ohne
    diese Zeile eine gueltige Tarifseite, und ein fehlender Betrag wird
    nie angenommen (E1).
    """
    roh = text or ""
    anfang = _BEREITSTELLUNGS_RE.search(roh)
    if not anfang:
        return None
    treffer = _MIT_SMARTPHONE_RE.search(
        roh, anfang.end(), anfang.end() + _GEBUEHR_FENSTER
    )
    if not treffer:
        return None
    return zahl(html_modul.unescape(treffer.group(1)))


def ergaenze_bereitstellungsgebuehr(
    hole: Callable, kopfzeilen: dict, rohbuendel: list
) -> int:
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
    vertreter: dict[str, str] = {}
    for satz in rohbuendel or []:
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
        except Exception:  # noqa: BLE001
            log.info(
                "1&1: Tarifdetails zu %s nicht abrufbar - "
                "Bereitstellungsgebühr bleibt offen",
                slug,
            )
            continue
        if not (200 <= int(status) < 300):
            log.info(
                "1&1: Tarifdetails zu %s mit HTTP %s - "
                "Bereitstellungsgebühr bleibt offen",
                slug,
                status,
            )
            continue
        gebuehr = bereitstellungsgebuehr(text)
        if gebuehr is None:
            log.info(
                "1&1: Tarifdetails zu %s nennen keine "
                "Bereitstellungsgebühr - Feld bleibt offen",
                slug,
            )
            continue
        gebuehren[slug] = gebuehr

    gesetzt = 0
    for satz in rohbuendel or []:
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


_RASTER_LINK_RE = re.compile(
    r'targetpage="(?P<ziel>(?://mobile\.1und1\.de)?/smartphones-[a-z0-9-]+)'
)

_KLAMMERZUSATZ_RE = re.compile(r"\s*\([^()]*\)\s*$")


def tarifname_bereinigt(name: str) -> str:
    """ "1&1 All-Net-Flat M (50 GB)" -> "1&1 All-Net-Flat M".

    Das Raster haengt das Volumen in Klammern an; der Tarifbestand fuehrt
    den Namen ohne (`/handytarife`), und `tarif_bezug` loest nur den auf.
    """
    text = " ".join(html_modul.unescape(name or "").split())
    return _KLAMMERZUSATZ_RE.sub("", text).strip()


def tarifraster_adressen(text: str, basis_url: str) -> list[str]:
    """Die Geraeteraster, die eine Tarifuebersicht verlinkt (Klick-Tagesdatei)."""
    out: list[str] = []
    for treffer in _RASTER_LINK_RE.finditer(text or ""):
        ziel = urljoin(basis_url or "https://mobile.1und1.de", treffer.group("ziel"))
        if ziel not in out:
            out.append(ziel)
    return out


TARIFUEBERSICHT = "https://mobile.1und1.de/all-net-flat-vergleich"
"""Die Tarifuebersicht, die je Tarif-Slug den Tarifdetails-Iframe verlinkt."""

_DETAILS_IFRAME_RE = re.compile(r'data-iframe="([^"]*/details-[^"]*)"')


def tarifdetails_je_slug(text: str, basis_url: str) -> dict[str, str]:
    """{Tarif-Slug: Tarifdetails-Adresse}, wie die Uebersicht sie verlinkt."""
    out: dict[str, str] = {}
    for roh in _DETAILS_IFRAME_RE.findall(text or ""):
        ziel = html_modul.unescape(roh)
        slug = _SLUG_RE.search(ziel)
        if slug:
            out.setdefault(slug.group(1), urljoin(basis_url, ziel))
    return out


def ergaenze_tarifdetails(hole: Callable, kopfzeilen: dict, rohbuendel: list) -> int:
    """`tarifdetails_url` fuer 1&1-Saetze mit Slug, aber ohne Adresse (seit K1
    traegt die Geraeteseite keinen Iframe-Link mehr): EIN Abruf der
    Tarifuebersicht, nur wenn ein solcher Satz da ist. Ein gescheiterter Abruf
    laesst das Feld leer und meldet sich. Zurueck kommt die Zahl gesetzter Saetze."""
    offen = [
        s
        for s in rohbuendel or []
        if s.get("quelle") == "einsundeins_buendel"
        and s.get("tarif_slug")
        and not s.get("tarifdetails_url")
    ]
    if not offen:
        return 0
    try:
        status, text = hole(TARIFUEBERSICHT, kopfzeilen=kopfzeilen)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "1&1: %s nicht abrufbar (%s) - Tarifdetails offen", TARIFUEBERSICHT, exc
        )
        return 0
    if not (200 <= int(status) < 300):
        log.warning("1&1: %s mit HTTP %s - Tarifdetails offen", TARIFUEBERSICHT, status)
        return 0
    adressen = tarifdetails_je_slug(text, TARIFUEBERSICHT)
    gesetzt = 0
    for satz in offen:
        adresse = adressen.get(satz["tarif_slug"])
        if adresse:
            satz["tarifdetails_url"] = adresse
            gesetzt += 1
    if gesetzt < len(offen):
        log.info(
            "1&1: %d Sätze ohne Tarifdetails in der Übersicht", len(offen) - gesetzt
        )
    return gesetzt


def ergaenze_buendel(hole: Callable, kopfzeilen: dict, rohbuendel: list) -> int:
    """Der Nachbearbeitungs-Haken: die Bereitstellungsgebühr fuer alle Saetze.

    Tarifstufen werden hier NICHT mehr hergeleitet (bis 20.11.2026:
    Rasteraufschlag auf alle Speicher, `tarifaufschlag_aus_tarifraster`): der
    Tarifnachlass haengt an Speicher und Laufzeit (Modulkopf), ein
    uebertragener Aufschlag waere unbelegt. Zurueck kommt die Zahl der Saetze
    mit gesetzter Gebühr."""
    ergaenze_tarifdetails(hole, kopfzeilen, rohbuendel)
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
            log.info(
                "1&1: %s nennt keinen Tarif in der Beschreibung (%r) - "
                "Buendelpreis verworfen",
                url,
                str(knoten.get("description"))[:80],
            )
            continue

        marke = knoten.get("brand")
        marke_name = (marke.get("name") if isinstance(marke, dict) else marke) or ""
        name = str(knoten.get("name") or "").strip()
        if not name:
            continue
        speicher = var.get("size")
        farbe = (var.get("color") or "").replace("_", " ").strip().lower()
        out.append(
            {
                "titel": " ".join(
                    x
                    for x in (
                        str(marke_name).strip(),
                        name,
                        f"{speicher} GB" if speicher else "",
                        farbe,
                    )
                    if x
                ),
                "preis": None,
                "monatspreis": monatspreis,
                "tarif": tarif,
                "laufzeit_monate": laufzeit,
                "waehrung": str(angebot.get("priceCurrency") or "EUR").upper(),
                "verfuegbarkeit": _verfuegbarkeit(angebot.get("availability")),
                "sku": str(knoten.get("sku") or "").strip(),
                "ean": str(knoten.get("gtin13") or knoten.get("gtin") or "").strip(),
                "farbe": farbe,
                "speicher_gb": int(speicher) if str(speicher).isdigit() else None,
                "url": str(knoten.get("url") or "").strip() or url,
                "quelle": "einsundeins_buendel",
            }
        )
    return out
