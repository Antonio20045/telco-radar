"""1&1: der Monatspreis des BUENDELS, und nichts anderes.

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

NUR "fix" IST OHNE "24+12" BELEGBAR: Der Analytics-Datalayer derselben
Antwort (`const products = [...]`, GA4-Schema) nennt die echte Mindest-
bindung `tariff.contractduration` und schluesselt ihre Perioden als
"mandatory" gegen "optional-24+12"/"optional-36+12" - eine FREIWILLIGE
Verlaengerung zum gleichen Preis ueber die Mindestbindung hinaus. Genau
das ist "flex": ihre `tariffMonthlyPrices` laufen bis Laufzeit+12
(24->36, 36->48). "fix" ist dagegen fuer GENAU `contractduration` flach
und springt danach auf den Listenpreis - gegengeprueft ueber dem ersten
Eintrag von `tariffMonthlyPrices` (deckt Monat 1 bis mindestens
`contractduration` zum Betrag aus `tariffPricePerMonth`). Gelesen wird
deshalb nur "fix"; eine Abweichung bleibt unbelegt und wird verworfen
(lieber keine Zahl als eine 24+12-Zahl).

Tarifname/Marke/Modell kommen aus demselben Datalayer (`tariff.external
name`, `hardware.brand`/`name`) - der `tariff-description`-Span und das
`application/ld+json`-Product dafuer stehen auf keiner gemessenen Seite
mehr, bleiben aber als Rueckfallstufe im Code. `hwdVariantsOneOffPayment
Fees` (Einmalzahlung) und der `data-iframe`-Link zur Bereitstellungs-
gebuehr fehlen ebenfalls; beide degradieren ohne ihren Textmarker auf
`None`/`""` (E1) statt eine falsche Zahl anzunehmen.

MARKUP-STAND 20.11.2026 (K2): die Geraeteraster nennen mit
`data-hardware-months` die Zahl der GERAETERATEN (seit diesem Tag 48),
nicht die Mindestbindung - Gegenprobe und Begruendung stehen in
`einsundeins_raten.py`.

Keine zusaetzlichen Abrufe: `lies_buendel` liest dieselbe Antwort, die
der Ernte-Weg fuer die Listung ohnehin holt.
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
from .basis import GeraeteAbrufFehler
from .einsundeins_raten import flache_tarifrate, gegenwert, geraeteraten_preise

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


def _vertragslaufzeit(text: str) -> int | None:
    """Mindestbindung aus `tariff.contractduration`, NICHT `current
    HardwareOfferDuration` (Modulkopf, "24+12"); nur fuer die neue
    Preiskarte, die alte bleibt bei `laufzeit_monate`."""
    tarifposten = _datalayer(text).get("tariff") or {}
    dauer = (tarifposten.get("tariff") or {}).get("contractduration")
    return dauer if isinstance(dauer, int) and dauer > 0 else None


def _fixpreis(karteneintrag: dict, dauer: int) -> tuple[float, float] | None:
    """(Hardware-, Tarifrate/Monat) der "fix"-Stufe zu `dauer`, nur bei
    belegter Flachheit (Modulkopf, "24+12"); sonst `None`."""
    stufe = (karteneintrag or {}).get(str(dauer), {})
    stufe = stufe.get("fix") if isinstance(stufe, dict) else None
    if not isinstance(stufe, dict):
        return None
    hardwarerate = zahl(str(stufe.get("hardwarePricePerMonth")))
    tarifrate = flache_tarifrate(stufe, dauer)
    if hardwarerate is None or tarifrate is None:
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
    """Aus einer Geräteseite je SPEICHERGROESSE einen Bündel-Rohsatz.

    Die Karte preist den Default-Tarif der Seite ueber alle Farben - die
    erste Farbe vertritt ihre Groesse. Der Satz traegt NUR den kombi-
    nierten Monatsbetrag (`buendel_monatlich`, § 13.2), nie eine
    Aufspaltung ohne Beleg.

    Wirft, wenn die Seite gar keine Preiskarte trägt (altes wie neues
    Markup, Modulkopf) - ein leeres Ergebnis waere dafuer die falsche
    Meldung (dasselbe Muster wie bei o2, Telekom und congstar). Ohne
    lesbaren Tarifnamen oder ohne bestimmbare Mindestbindung liefert sie
    nur ihre leere Ausbeute mit einer Protokollzeile (Name/Laufzeit
    stehen einmal je Seite, trifft also die ganze Seite - gelogt, nicht
    geworfen).
    """
    karte = _hardwarepreiskarte(text)
    dauer = _vertragslaufzeit(text) if karte else None
    if not karte:
        karte = _alte_preiskarte(text)
        dauer = laufzeit_monate(text)
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
    if dauer is None:
        log.info(
            "1&1: %s nennt keine Mindestbindung (Datalayer-contractduration/"
            "currentHardwareOfferDuration) - Bündelsätze verworfen",
            url,
        )
        return []
    slug_treffer = _SLUG_RE.search(text or "")
    tarif_slug = slug_treffer.group(1) if slug_treffer else ""

    marke, name = _marke_name(text)
    einmalzahlungen = _einmalzahlungen(text)
    tarifdetails = _tarifdetails_url(text, url)
    hw_id = _hw_id(text)
    vorauswahl = variante(text).get("size") or ""
    angezeigt_html = _angezeigter_preis(text, hw_id)
    out: list[dict] = []
    gesehen: dict[int, tuple[str, float]] = {}
    for schluessel, eintrag in karte.items():
        treffer = _VARIANTSCHLUESSEL_RE.match(schluessel)
        if not treffer:
            continue
        gb = int(treffer.group("gb"))
        farbe_roh = treffer.group("farbe")
        farbe = farbe_roh.replace("_", " ").strip().lower()
        preis = _preis_je_schluessel(eintrag, dauer)
        if preis is None:
            log.info(
                "1&1: %s/%s ohne belegten Flachpreis zur Mindestbindung "
                "(%d Monate) - Variante verworfen",
                url,
                schluessel,
                dauer,
            )
            continue
        betrag = round(sum(preis), 2)
        vorher = gesehen.get(gb)
        if vorher is not None:
            if vorher[1] != betrag:
                log.warning(
                    "1&1: %s trägt zwei Preise für %d GB (%.2f und "
                    "%.2f) - der erste bleibt",
                    url,
                    gb,
                    vorher[1],
                    betrag,
                )
            continue
        gesehen[gb] = (farbe, betrag)
        if not name:
            continue
        einmalzahlung = einmalzahlungen.get((farbe_roh, gb))
        if einmalzahlungen and einmalzahlung is None:
            log.info(
                "1&1: %s nennt keine Einmalzahlung für %s/%d GB - Feld bleibt offen",
                url,
                farbe_roh,
                gb,
            )
        vorausgewaehlt = str(gb) == vorauswahl
        angezeigt = angezeigt_html if angezeigt_html is not None else betrag
        raten_preise = geraeteraten_preise(eintrag)
        raten_preise.setdefault(dauer, betrag)
        out.append(
            {
                "hw_id": hw_id,
                "vorausgewaehlt": vorausgewaehlt,
                "angezeigt_monatlich": angezeigt if vorausgewaehlt else None,
                "raten_preise": raten_preise if vorausgewaehlt else None,
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


TARIFUEBERSICHTEN = (
    "https://mobile.1und1.de/all-net-flat-vergleich",
    "https://mobile.1und1.de/unbegrenztes-datenvolumen",
)

_RASTER_LINK_RE = re.compile(
    r'targetpage="(?P<ziel>(?://mobile\.1und1\.de)?/smartphones-[a-z0-9-]+)'
)

_TAG_RE = re.compile(r"<(?:a|span)\b[^>]*>", re.S)
_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')

_RASTER_FORM_RE = re.compile(r'<form class="hardware-box\b.*?</form>', re.S)
_RASTER_GERAET_RE = re.compile(r'data-hardware-select="([^"]+)"')
_RASTER_MONATE_RE = re.compile(r'data-hardware-months="(\d+)"')
_RASTER_EURO_RE = re.compile(r'-price--euro"[^>]*>\s*(\d+)\s*<')
_RASTER_CENT_RE = re.compile(r'-price--cent"[^>]*>\s*([0-9–-]+)\s*<')
_RASTER_TARIF_RE = re.compile(r"Inkl\.\s*([^<]+)")

_KLAMMERZUSATZ_RE = re.compile(r"\s*\([^()]*\)\s*$")

_MINDEST_GERAETE_EINHEITLICH = 5
HERLEITUNG_TARIFAUFSCHLAG = "tarifaufschlag_aus_tarifraster"

_NUR_DEFAULTSATZ = ("angezeigt_monatlich", "anschlusspreis", "raten_preise")


def tarifname_bereinigt(name: str) -> str:
    """ "1&1 All-Net-Flat M (50 GB)" -> "1&1 All-Net-Flat M".

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


def _angezeigter_preis(text: str, hw_id: str) -> float | None:
    """Der Monatspreis, den die Geraeteseite im `hwd-monthly-price`-Block
    serverseitig anzeigt (VOR K1, mit `id="<hw_id>--price__digits"` im
    Markup). `None`, wenn der Block fehlt (K1-Markup ab 20.11.2026 traegt
    ihn nicht mehr) - der Aufrufer faellt dann auf die Preiskarte zurueck,
    statt eine falsche Zahl anzunehmen."""
    if not hw_id:
        return None
    kopf = re.escape(hw_id)
    euro = re.search(rf'id="{kopf}--price__digits">\s*(\d+)\s*<', text or "")
    cent = re.search(
        rf'id="{kopf}--price__decimals"[^>]*>\s*([0-9–-]+)\s*<', text or ""
    )
    if not (euro and cent):
        return None
    return _cent(euro.group(1), cent.group(1)) / 100.0


def tarifraster_adressen(text: str, basis_url: str) -> list[str]:
    """Die Geraeteraster, die eine Tarifuebersicht verlinkt."""
    out: list[str] = []
    for treffer in _RASTER_LINK_RE.finditer(text or ""):
        ziel = urljoin(basis_url or "https://mobile.1und1.de", treffer.group("ziel"))
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
        name = tarifname_bereinigt(titel[len("Tarifdetails ") :])
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
            int(monate.group(1)) if monate else None,
        )
    if not preise:
        raise GeraeteAbrufFehler(
            f"1&1-Geräteraster ohne hardware-box-Kachel "
            f"({len(text or '')} Bytes) - Markup geändert?"
        )
    if len(namen) != 1:
        log.warning(
            "1&1: Geräteraster nennt %d Tarifnamen (%s) - verworfen",
            len(namen),
            ", ".join(sorted(namen)),
        )
    return {
        "tarif_name": next(iter(namen)) if len(namen) == 1 else "",
        "preise": preise,
    }


def _hole_text(hole: Callable, kopfzeilen: dict, adresse: str) -> str | None:
    """Ein Abruf; None bei Fehler - protokolliert, nie still."""
    try:
        status, text = hole(adresse, kopfzeilen=kopfzeilen)
    except Exception as exc:  # noqa: BLE001
        log.warning("1&1: %s nicht abrufbar (%s)", adresse, exc)
        return None
    if not (200 <= int(status) < 300):
        log.warning("1&1: %s mit HTTP %s", adresse, status)
        return None
    return text


def ergaenze_tarifstufen(hole: Callable, kopfzeilen: dict, rohbuendel: list) -> int:
    """Aus den Default-Tarif-Saetzen die Saetze der uebrigen Tarifstufen.

    Rechnung, Gegenprobe und Grenzen stehen im Kopf dieses Abschnitts.
    Abrufe: die zwei Tarifuebersichten plus ein Raster je verlinktem
    Tarif (am 29.09.2026: 2 + 7). Haengt die neuen Saetze an `rohbuendel` an,
    gibt ihre Zahl zurueck. Ohne Default-Raster keine Gegenprobe, also
    nichts. Die Ablöse hängt nur an der Gerätevariante (`klickraster`).

    GEGENPROBE (K2, Modulkopf): ein Gerät zählt nur, wenn beide Raster
    dieselbe Ratenzahl nennen und das Raster des Default-Tarifs denselben
    Preis nennt wie die Geräteseite (`_gegenwert`). Die Mindestbindung des
    hergeleiteten Satzes ist die des Default-Satzes, nicht die Ratenzahl
    des Rasters.
    """
    basis = [
        s
        for s in (rohbuendel or [])
        if s.get("quelle") == "einsundeins_buendel"
        and not s.get("herleitung")
        and s.get("hw_id")
    ]
    if not basis:
        return 0
    basistarife = {s.get("tarif_name") for s in basis}
    if len(basistarife) != 1:
        log.warning(
            "1&1: Geräteseiten nennen %d Default-Tarife (%s) - "
            "keine Tarifstufen hergeleitet",
            len(basistarife),
            ", ".join(sorted(map(str, basistarife))),
        )
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
        log.warning(
            "1&1: kein Geräteraster für den Default-Tarif %s - "
            "keine Tarifstufen hergeleitet (%d Raster gelesen)",
            basistarif,
            len(raster),
        )
        return 0
    _, basisraster = raster[basistarif]

    vorhanden = {
        (s.get("sku_id"), s.get("tarif_name"), s.get("laufzeit_monate"))
        for s in rohbuendel
    }
    neu: list[dict] = []
    for tarif, (adresse, gelesen) in sorted(raster.items()):
        if tarif == basistarif:
            continue
        aufschlaege = {
            hw: preis[0] - basisraster["preise"][hw][0]
            for hw, preis in gelesen["preise"].items()
            if hw in basisraster["preise"]
        }
        einheitlich = (
            len(aufschlaege) >= _MINDEST_GERAETE_EINHEITLICH
            and len(set(aufschlaege.values())) == 1
        )
        detail_url, slug = details.get(tarif, ("", ""))
        unstimmig = 0
        for hw, saetze in sorted(je_geraet.items()):
            if hw not in aufschlaege:
                continue
            vorher = next((s for s in saetze if s.get("vorausgewaehlt")), None)
            basis_cent, basis_monate = basisraster["preise"][hw]
            monate = gelesen["preise"][hw][1]
            gegen = gegenwert(vorher, basis_monate)
            if (
                gegen is None
                or monate is None
                or monate != basis_monate
                or round(gegen * 100) != basis_cent
            ):
                unstimmig += 1
                continue
            ziele = saetze if einheitlich else [vorher]
            for satz in ziele:
                schluessel = (satz.get("sku_id"), tarif, satz.get("laufzeit_monate"))
                if schluessel in vorhanden:
                    continue
                vorhanden.add(schluessel)
                cent = round(satz["buendel_monatlich"] * 100) + aufschlaege[hw]
                kopie = {k: v for k, v in satz.items() if k not in _NUR_DEFAULTSATZ}
                kopie.update(
                    {
                        "tarif_name": tarif,
                        "tarif_slug": slug,
                        "tarifdetails_url": detail_url,
                        "buendel_monatlich": round(cent / 100.0, 2),
                        "herleitung": HERLEITUNG_TARIFAUFSCHLAG,
                        "url": adresse,
                        "quelle_url": adresse,
                    }
                )
                neu.append(kopie)
        log.info(
            "1&1: %s - Aufschlag %s, %s%s",
            tarif,
            "einheitlich" if einheitlich else "geräteabhängig",
            "alle Speichergrößen" if einheitlich else "nur die vorausgewählte Größe",
            f", {unstimmig} Geräte ohne passende Gegenprobe" if unstimmig else "",
        )
    rohbuendel.extend(neu)
    return len(neu)


def ergaenze_buendel(hole: Callable, kopfzeilen: dict, rohbuendel: list) -> int:
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
