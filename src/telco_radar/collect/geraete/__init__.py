"""Der Geraete-Collector: von der Einstiegsseite zum belegten Preis.

Ablauf je Anbieter:

    robots pruefen  ->  Einstiegsseite lesen  ->  Produktlinks ERNTEN
                    ->  je Link die Produktseite  ->  strukturierte Daten
                    ->  Katalogabgleich  ->  Listung

VIER REGELN, DIE HIER ERZWUNGEN WERDEN
--------------------------------------
1. **Nur verlinkte Adressen.** Abgerufen wird ausschliesslich, was auf einer
   konfigurierten Einstiegsseite oder in einer vom Anbieter selbst
   ausgewiesenen Sitemap stand. Keine hochgezaehlte ID - dieselbe Regel und
   derselbe Grund wie beim Tarif-Sammler (§ 87b UrhG). `bilanz["nicht_verlinkt"]`
   fuehrt darueber Buch, ein Test stellt eine erreichbare, aber unverlinkte
   Falle auf.
2. **robots.txt gilt**, und zwar mit Crawl-delay und Besuchszeit
   (`robots.py`). Wer draussen steht, wird uebersprungen - nicht gealtert.
3. **Eine Einstiegsseite gilt erst als GELESEN, wenn alle ihre Produkte
   abgerufen wurden.** Nur dann darf die Auslistungslogik ihre Geraete
   altern. Ein Zeitbudget, das mitten in der Seite zuschlaegt, macht aus
   einem halben Abruf sonst eine halbe Auslistung.
4. **Ein gescheiterter Abruf ist nicht "nichts gefunden".** Er wirft bzw.
   setzt `status: fehler`, und der Anbieter kommt nicht in die Menge der
   gelesenen. Dieselbe Unterscheidung wie `PromoExtractionError` im
   Promo-Zweig, aus demselben Grund.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ...geraete_model import Katalog, lies_listung
from .robots import RobotsWaechter
from .strukturdaten import ist_lockpreis, produkte_aus_html

log = logging.getLogger(__name__)

_LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.IGNORECASE)

# --------------------------------------------------------------------------
# Die Adapter-Registry
# --------------------------------------------------------------------------
# Bis zum 11.08.2026 war das ein Tupel von zwei Methodennamen plus ein
# hartcodiertes `if einstieg.kind == "shopify" or anbieter.methode ==
# "shopify"` mitten in `sammle_anbieter`. Damit war der Ausbau von zwei auf
# acht Anbieter kein Adapterproblem, sondern ein Umbau derselben Funktion -
# und `json_endpunkt` war ein SAMMELBEGRIFF fuer fuenf voellig verschiedene
# Nutzlasten (Nuxt-Referenzarray, __PRELOADED_STATE__, productDetailsData,
# ng-state, INITIAL_STATE). Wer ihn implementiert haette, haette alle fuenf
# gleichzeitig scharf geschaltet.
#
# ZWEI TEILE JE ADAPTER, und der zweite wird gern vergessen: Telekom und o2
# fuehren ihre Produktadressen NICHT als `<a href>`, sondern in derselben
# JSON-Nutzlast wie die Preise. Ein Adapter, der nur `lies` mitbringt, findet
# dort null Seiten. Die Regel "nur verlinkte Adressen, nie hochgezaehlte IDs"
# gilt dabei unveraendert: was in der Nutzlast der Einstiegsseite steht, hat
# der Anbieter selbst genannt.


@dataclass
class Adapter:
    """Wie eine Quelle gelesen wird.

    `lies(text, url) -> list[rohsatz]` mit den neun Schluesseln
    (titel, preis, waehrung, verfuegbarkeit, sku, ean, farbe, url, quelle)
    und wahlweise `zuzahlung` + `tarif` fuer Buendelpreise.

    `ernte(text, basis_url, pfadmuster, kind) -> list[str]` nur, wenn die
    Adressen nicht als `<a href>` oder `<loc>` dastehen.

    `direkt=True` heisst: die Einstiegsseite IST die Nutzlast, es werden
    keine Produktseiten nachgeladen (so arbeitet Shopify).

    `lies_buendel(text, url) -> list[rohsatz]` ist die ZWEITE Lesart
    derselben Quelle und wird nur fuer Einstiege mit `kind: buendel`
    aufgerufen. Ihre Saetze werden KEINE Listungen: sie tragen Zuzahlung,
    Geraeterate, Tarifbetrag und Tarifbezug und gehoeren damit in
    `geraete_tco.json`, nicht in die Preisspalte der Geraeteseite. o2
    liefert beide Lesarten unter derselben Adresse - einmal mit
    `?hwOnly=true` (Geraete ohne Tarif), einmal ohne (Buendel).
    """
    name: str
    lies: Callable
    ernte: Optional[Callable] = None
    direkt: bool = False
    lies_buendel: Optional[Callable] = None
    # Ein Satz aus strukturierten Daten ist belegt, einer aus Fliesstext
    # geraten. Wer das hier vergisst, bekommt eine Listung, die sich selbst
    # als "mittel" ausweist, obwohl sie aus ld+json stammt.
    confidence: str = "hoch"


ADAPTER: dict = {}


def registriere(methode: str, adapter: Adapter) -> None:
    ADAPTER[methode] = adapter


def umgesetzte_methoden() -> tuple:
    return tuple(sorted(ADAPTER))



class GeraeteAbrufFehler(RuntimeError):
    """Der Abruf ist gescheitert - das ist NICHT dasselbe wie "keine Geraete
    auf der Seite". Eigene Klasse, damit der Aufrufer die Seite als ungelesen
    fuehren kann und `mark_stale` ihre Geraete in Ruhe laesst."""


@dataclass
class Anbieterbilanz:
    """Was ein Anbieter in diesem Lauf ergeben hat - und warum nicht mehr."""
    name: str
    status: str = "ok"        # ok | leer | fehler | uebersprungen | frist | nicht_umgesetzt
    grund: str = ""
    listungen: list = field(default_factory=list)
    # Rohsaetze aus Buendel-Einstiegen. Sie sind KEINE Listungen und werden
    # nicht in `geraete_db.json` aufgenommen - die Pipeline macht daraus
    # `tco_model.Buendel`, sobald sie ihren Tarif aufloesen kann. Sie stehen
    # hier und nicht in `listungen`, weil ein Buendelmonatspreis in der
    # Preisspalte der Geraeteseite eine Zahl ohne gemeinsame Einheit waere -
    # derselbe Befund, mit dem dieses Vorhaben angefangen hat.
    buendel: list = field(default_factory=list)
    gelesene_einstiege: set = field(default_factory=set)
    seiten_versucht: int = 0
    produkte_abgerufen: int = 0
    unbekannte_titel: list = field(default_factory=list)
    unbekannte_farben: list = field(default_factory=list)
    gedeckelt: list = field(default_factory=list)
    besucht: list = field(default_factory=list)
    nicht_verlinkt: list = field(default_factory=list)
    # Wie viele PREISSAETZE der Extraktor auf den gelesenen Seiten ueberhaupt
    # gefunden hat - vor dem Katalogabgleich. Ohne diese Zahl sind zwei ganz
    # verschiedene Ausfaelle im Protokoll nicht zu unterscheiden: "die Seite
    # gibt nichts her" (rohsaetze 0) und "die Seite gibt etwas her, aber
    # nichts davon steht im Katalog" (rohsaetze > 0, listungen 0). Genau
    # diese Frage stand am 28.08.2026 fuer Medimax und ElectronicPartner
    # offen - 20 abgerufene Produktseiten, 0 Listungen, und das Protokoll
    # sagte nicht, an welcher der beiden Stufen es lag.
    rohsaetze: int = 0

    @property
    def vollstaendig(self) -> bool:
        """Darf die Auslistungslogik fuer diesen Anbieter ueberhaupt laufen?"""
        return self.status in ("ok", "leer") and bool(self.gelesene_einstiege)


# --------------------------------------------------------------------------
# Linkernte
# --------------------------------------------------------------------------

def ernte_links(inhalt: str, basis_url: str, pfadmuster="",
                kind: str = "static") -> list[str]:
    """Produktadressen aus einer Einstiegsseite.

    `static` liest echte `<a href>`, `sitemap` die `<loc>`-Eintraege. Beides
    sind Adressen, die der Anbieter SELBST nennt; geraten wird nichts.
    Reihenfolge = Seitenreihenfolge, entdoppelt.

    `pfadmuster` ist ein Teilstring ODER eine Liste von Teilstrings, die ALLE
    enthalten sein muessen. Die Liste braucht es, weil ein einzelner
    Teilstring kein UND ausdruecken kann: freenets Sitemap traegt unter
    `-ohne-vertrag/p/P-M-` auch Tablets - und jede dieser Seiten kostet bei
    Crawl-delay einen zweistelligen Sekundenbetrag des Zeitbudgets, ohne je
    den Katalog treffen zu koennen.
    """
    muster = ([pfadmuster] if isinstance(pfadmuster, str) else
              [str(m) for m in (pfadmuster or [])])
    muster = [m for m in muster if m]
    roh: list[str] = []
    if kind == "sitemap":
        roh = [t.strip() for t in _LOC_RE.findall(inhalt or "")]
    else:
        suppe = BeautifulSoup(inhalt or "", "html.parser")
        for anker in suppe.find_all("a"):
            href = (anker.get("href") or "").strip()
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue
            roh.append(href)

    basis_host = urlparse(basis_url).netloc.lower()
    gesehen: set[str] = set()
    out: list[str] = []
    for href in roh:
        url = urljoin(basis_url, href)
        teile = urlparse(url)
        if teile.scheme not in ("http", "https"):
            continue
        if basis_host and teile.netloc.lower() != basis_host:
            continue          # Fremde Domain: nicht unser Beobachtungsraum
        if muster and not all(m in url for m in muster):
            continue
        url = url.split("#", 1)[0]
        if url.rstrip("/") == (basis_url or "").rstrip("/"):
            continue          # die Einstiegsseite selbst
        if url in gesehen:
            continue
        gesehen.add(url)
        out.append(url)
    return out


def produkte_aus_shopify(nutzlast: str) -> list[dict]:
    """Shopify legt seinen Katalog unter /products.json offen - ein
    dokumentierter, oeffentlicher Endpunkt, kein aufgemachter Innenweg.
    Je Variante ein Satz mit Titel, Preis und Verfuegbarkeit."""
    import json
    try:
        daten = json.loads(nutzlast or "")
    except (json.JSONDecodeError, ValueError) as exc:
        raise GeraeteAbrufFehler(f"products.json unlesbar: {exc}") from exc
    from .strukturdaten import lies_preis
    out = []
    for produkt in (daten.get("products") or []):
        titel = str(produkt.get("title") or "").strip()
        handle = str(produkt.get("handle") or "").strip()
        for variante in (produkt.get("variants") or []):
            preis = lies_preis(variante.get("price"))
            bezeichnung = str(variante.get("title") or "").strip()
            voller_titel = titel if bezeichnung in ("", "Default Title") \
                else f"{titel} {bezeichnung}"
            out.append({
                "titel": voller_titel,
                "preis": preis,
                "waehrung": "EUR",
                "verfuegbarkeit": "lieferbar" if variante.get("available") else "ausverkauft",
                "sku": str(variante.get("sku") or "").strip(),
                "ean": str(variante.get("barcode") or "").strip(),
                "farbe": "",
                "url": f"/products/{handle}" if handle else "",
                "quelle": "shopify",
            })
    return out


# --------------------------------------------------------------------------
# Die zwei Adapter, mit denen der Zweig gestartet ist
# --------------------------------------------------------------------------
# `ldjson` ist in Wahrheit eine KASKADE (ld+json, dann Microdata) - so haengt
# ALDI TALK daran, das gar kein ld+json ausliefert. Der Methodenname ist
# deshalb bewusst nicht "der Extraktor", sondern "die uebliche Lesart einer
# gewoehnlichen Produktseite".
registriere("ldjson", Adapter(name="ldjson",
                              lies=lambda text, url="": produkte_aus_html(text)))
registriere("shopify", Adapter(name="shopify",
                               lies=lambda text, url="": produkte_aus_shopify(text),
                               direkt=True))


def _registriere_anbieter_adapter() -> None:
    """Die anbietereigenen Adapter, jeder mit EIGENEM Methodennamen.

    Der Import steht in einer Funktion, weil die Module aus diesem Paket
    `GeraeteAbrufFehler` importieren - auf Modulebene waere das ein Zirkel.
    """
    from . import congstar as congstar_modul
    from . import einsundeins as einsundeins_modul
    from . import o2 as o2_modul
    from . import saturn as saturn_modul
    from . import telekom as telekom_modul
    from . import vodafone as vodafone_modul

    registriere("vodafone_api", Adapter(name="vodafone_api",
                                        lies=vodafone_modul.lies,
                                        ernte=vodafone_modul.ernte))
    # Zwei Lesarten derselben Adresse: `lies` fuer den Katalog ohne Tarif
    # (`?hwOnly=true`), `lies_buendel` fuer den mit. o2 gibt beide Adressen
    # in der Nutzlast von /e-shop/ selbst aus.
    registriere("o2_katalog", Adapter(name="o2_katalog",
                                      lies=o2_modul.lies,
                                      lies_buendel=o2_modul.lies_buendel,
                                      direkt=True))
    # Kein `ernte` noetig: die Sitemap traegt echte `<loc>`-Adressen, die
    # generische `ernte_links(kind="sitemap")` findet sie ohne Zutun. Nicht
    # `direkt`: die Einstiegsseite (Sitemap) ist nur ein Verzeichnis, die
    # Preise stehen erst auf den einzelnen Produktseiten.
    registriere("congstar_next", Adapter(name="congstar_next",
                                         lies=congstar_modul.lies))
    # Die Kategorieseite IST die Nutzlast (`direkt`): sie traegt die
    # absoluten Betraege serverseitig, und die zehn Produktadressen stehen
    # als echte `<a href>` darin - der Adapter liest sie aus demselben
    # Text und braucht kein eigenes `ernte`.
    registriere("telekom_kategorie", Adapter(name="telekom_kategorie",
                                             lies=telekom_modul.lies,
                                             direkt=True))
    # NICHT `direkt`: die Kategorieseite `/smartphones` traegt kein
    # Produktschema, nur die verlinkten Produktseiten. Die Linkernte ist
    # ANBIETEREIGEN, weil die Seite neben ihren 42 Katalogkacheln 125
    # weitere Adressen derselben Domain fuehrt - siehe
    # `einsundeins.ernte`.
    registriere("einsundeins_buendel",
                Adapter(name="einsundeins_buendel",
                        lies=einsundeins_modul.lies,
                        ernte=einsundeins_modul.ernte))
    # Die Markenseite IST die Nutzlast (direkt): ld+json UND Apollo-Cache
    # stehen bereits in dieser einen Antwort, keine Produktseite wird
    # nachgeladen. Kein `ernte` noetig - die Beleglinks je Variante liest
    # der Adapter selbst aus dem Apollo-Cache (saturn.py).
    registriere("saturn_brand", Adapter(name="saturn_brand",
                                        lies=saturn_modul.lies,
                                        direkt=True))


_registriere_anbieter_adapter()


# --------------------------------------------------------------------------
# Ein Anbieter
# --------------------------------------------------------------------------

def _preisfelder(anbieter, satz: dict) -> dict:
    """Welche der zwei Preisarten traegt diese Zahl? (Teil C4)

    DIE DISZIPLIN BLEIBT, SIE WIRD NUR PRAEZISER. Bis zum 11.08.2026 kannte
    diese Funktion ausschliesslich `preis_ohne_vertrag`, und der
    Lockpreis-Waechter warf jede Zahl unter 30 EUR weg. Das war richtig - es
    hat 1-Euro-iPhones aus der Preiskarte gehalten - und hatte einen Preis:
    KEIN einziger Netzbetreiber erschien, also fehlte die Haelfte des
    Marktes. Gemessen an Blau steht der Geraetepreis dort als `"price":
    "1.00"` in einem escapten ld+json-Block; ohne Tarifbezug ist diese Zahl
    tatsaechlich bedeutungslos, MIT ihm ist sie die eigentliche Auskunft.

    Neue Regel:
    - Ein Buendelpreis wird gespeichert, wenn seine Tarifreferenz mitgelesen
      werden konnte. Ohne sie wird er weiterhin verworfen.
    - Er landet in EIGENEN Feldern und nie in `preis_ohne_vertrag`. Die
      Positionskarte mischt die zwei Achsen nicht.
    - Der Lockpreis-Waechter greift unveraendert fuer Zahlen, die als
      Ladenpreis ausgegeben werden.

    `Listung.__post_init__` ist die dritte Sicherung: eine Zuzahlung ohne
    `tarif_referenz` wirft dort.

    SEIT DEM 03.09.2026 REICHT SIE DIE PREISFORM MIT DURCH. Ein Ladenpreis
    ist nicht automatisch ein Barpreis: o2s Zahl ist der Gesamtbetrag einer
    24-Monats-Ratenzahlung. Wo ein Adapter Anzahlung, Rate und Laufzeit
    gelesen hat, wandern sie an die Listung und von dort auf die Seite. Wo er
    sie nicht gelesen hat, bleibt alles wie bisher - diese Funktion erfindet
    keine Preisform und leitet keine aus dem Anbieternamen ab.
    """
    preis = satz.get("preis")
    zuzahlung = satz.get("zuzahlung")
    monatspreis = satz.get("monatspreis")
    tarif = (satz.get("tarif") or "").strip()

    if zuzahlung is not None and tarif:
        return {"preis_ohne_vertrag": None, "zuzahlung": float(zuzahlung),
                "tarif_referenz": tarif,
                "preis_mit_vertrag_ab": monatspreis}
    if monatspreis is not None and tarif:
        # DER BUENDELPREIS OHNE ZUZAHLUNG (seit dem 04.09.2026, 1&1).
        # Bis dahin brauchte ein Buendel eine Zuzahlung, um ueberhaupt
        # gespeichert zu werden - der Monatspreis war nur ihr Beiwerk.
        # 1&1 kennt keine Zuzahlung: das Geraet steckt vollstaendig im
        # Monatspreis (44,99 EUR = iPhone 17 Pro + All-Net-Flat S ueber 36
        # Monate), und `preis_ohne_vertrag` gibt es dort ueberhaupt nicht.
        #
        # Ein Buendel ohne Barpreis ist trotzdem ein Buendel, und unter
        # TCO-first ist sein Monatspreis die Leitgroesse. Er landet
        # deshalb in `preis_mit_vertrag_ab` - nie in `preis_ohne_vertrag`,
        # denn dort stuende er neben Kassenpreisen und waere plausibel
        # falsch. Der Lockpreis-Waechter unten sieht ihn gar nicht erst;
        # er ist die Sicherung fuer Zahlen, die als Ladenpreis ausgegeben
        # werden, und das behauptet hier niemand.
        #
        # Die Laufzeit wandert mit: eine Monatszahl ohne die Zahl der
        # Monate ist keine Aussage ueber die Bindung.
        return {"preis_ohne_vertrag": None,
                "preis_mit_vertrag_ab": float(monatspreis),
                "tarif_referenz": tarif,
                "laufzeit_monate": satz.get("laufzeit_monate")}
    if preis is None or ist_lockpreis(preis):
        return {"preis_ohne_vertrag": None}
    return {"preis_ohne_vertrag": preis,
            "anzahlung": satz.get("anzahlung"),
            "monatsrate": satz.get("monatsrate"),
            "laufzeit_monate": satz.get("laufzeit_monate"),
            "zins_effektiv": satz.get("zins_effektiv")}


def sammle_anbieter(anbieter, katalog: Katalog, farben: dict, hole: Callable,
                    heute: str, waechter: RobotsWaechter,
                    jetzt: Optional[datetime] = None,
                    frist_bis: Optional[float] = None) -> Anbieterbilanz:
    """Einen Anbieter abarbeiten. Wirft nie - Fehler stehen in der Bilanz.

    `hole(url) -> (status, text)`. Der Status wird gebraucht und nicht
    weggeworfen: eine fehlende robots.txt (404) heisst "keine Regeln", eine
    verweigerte (403) heisst "nicht anfassen" - wer beides auf eine
    Ausnahme abbildet, verwechselt die zwei.
    """
    bilanz = Anbieterbilanz(name=anbieter.name)
    jetzt = jetzt or datetime.now(timezone.utc)

    if not anbieter.crawlbar:
        bilanz.status = "uebersprungen"
        bilanz.grund = anbieter.grund or "nicht crawlbar"
        return bilanz
    adapter = ADAPTER.get(anbieter.methode)
    if adapter is None:
        bilanz.status = "nicht_umgesetzt"
        bilanz.grund = anbieter.grund or (
            f"Beschaffungsmethode {anbieter.methode!r} ist gemessen, aber noch "
            f"nicht als Adapter gebaut")
        return bilanz

    erlaubt: set[str] = set()
    abstand = waechter.abstand(anbieter.basis_url or anbieter.einstiege[0].url,
                               anbieter.rate_limit_sekunden)
    letzter_abruf = [0.0]
    gruende: list[str] = []
    frist_erreicht = False

    # Zusaetzliche Kopfzeilen werden NUR uebergeben, wenn der Anbieter welche
    # deklariert. Damit bleibt der Vertrag `hole(url)` fuer alle bestehenden
    # Aufrufer und jede vorhandene Testattrappe unveraendert gueltig - nur
    # die zwei Anbieter, die eine Schnittstelle mit Pflichtkopfzeile lesen
    # (o2s Medientyp, Vodafones oeffentlicher Browser-Schluessel), brauchen
    # eine Attrappe mit zweitem Parameter.
    kopfzeilen = dict(getattr(anbieter, "kopfzeilen", None) or {})

    def _hole(url: str) -> str:
        darf, grund = waechter.darf(url, jetzt)
        if not darf:
            raise GeraeteAbrufFehler(grund)
        warte = abstand - (time.monotonic() - letzter_abruf[0])
        if letzter_abruf[0] and warte > 0:
            time.sleep(warte)
        letzter_abruf[0] = time.monotonic()
        bilanz.besucht.append(url)
        status, text = hole(url, kopfzeilen) if kopfzeilen else hole(url)
        if not (200 <= int(status) < 300):
            raise GeraeteAbrufFehler(f"HTTP {status}")
        return text

    for einstieg in anbieter.crawled_einstiege:
        if frist_erreicht:
            break
        bilanz.seiten_versucht += 1
        erlaubt.add(einstieg.url)
        try:
            inhalt = _hole(einstieg.url)
        except GeraeteAbrufFehler as exc:
            gruende.append(f"{einstieg.url}: {exc}")
            continue
        except Exception as exc:                       # noqa: BLE001
            gruende.append(f"{einstieg.url}: {type(exc).__name__}: {str(exc)[:120]}")
            continue

        # `kind: buendel` heisst: dieselbe Nutzlastform, andere Lesart.
        # Der Einstieg wird gelesen und NICHT geerntet; seine Saetze gehen
        # an der Listungsstrecke vorbei in `bilanz.buendel`.
        if einstieg.kind == "buendel":
            if adapter.lies_buendel is None:
                gruende.append(f"{einstieg.url}: die Methode "
                               f"{anbieter.methode!r} kennt keine "
                               f"Buendellesart")
                continue
            try:
                roh = adapter.lies_buendel(inhalt, einstieg.url) or []
                bilanz.buendel.extend(
                    _mit_sku(roh, anbieter, einstieg, katalog, farben,
                             heute, bilanz))
            except GeraeteAbrufFehler as exc:
                # Laut, nicht still: eine Buendelantwort, die keine ist,
                # heisst "das Nutzlastformat hat sich geaendert" - und ein
                # leeres Ergebnis waere dafuer die falsche Meldung.
                gruende.append(f"{einstieg.url}: {exc}")
                log.warning("%s: Buendelkatalog nicht lesbar (%s)",
                            anbieter.name, exc)
                continue
            bilanz.gelesene_einstiege.add(einstieg.url)
            continue

        # `direkt` heisst: die Einstiegsseite IST die Nutzlast. Der
        # Einstiegstyp gewinnt ueber die Methode - eine Marke kann eine
        # Shopify-Liste UND eine gewoehnliche Kategorieseite fuehren.
        direkt = ADAPTER["shopify"] if einstieg.kind == "shopify" else adapter
        if direkt.direkt:
            try:
                roh = direkt.lies(inhalt, einstieg.url)
            except GeraeteAbrufFehler as exc:
                gruende.append(f"{einstieg.url}: {exc}")
                continue
            _uebernimm(roh, anbieter, einstieg, einstieg.url, katalog, farben,
                       heute, bilanz)
            bilanz.gelesene_einstiege.add(einstieg.url)
            continue

        # Die Linkernte gehoert zum Adapter. Telekom und o2 fuehren ihre
        # Produktadressen in derselben JSON-Nutzlast wie die Preise, nicht als
        # `<a href>` - der beste Extraktor faende dort sonst null Seiten.
        if adapter.ernte is not None:
            links = adapter.ernte(inhalt, einstieg.url, einstieg.pfadmuster,
                                  einstieg.kind)
        else:
            links = ernte_links(inhalt, einstieg.url, einstieg.pfadmuster,
                                einstieg.kind)
        erlaubt.update(links)
        vollstaendig = True
        if len(links) > anbieter.max_produkte:
            # Eine abgeschnittene Seite ist KEINE gelesene Seite. Ohne diese
            # Zeile gilt sie als vollstaendig, und `mark_stale` altert alles
            # jenseits des Deckels: bei 83 Adressen und einem Deckel von 60
            # waeren das 23 Geraete je Lauf, nach zwei Laeufen "ausgelistet" -
            # und das Protokoll saehe normal aus.
            vollstaendig = False
            bilanz.gedeckelt.append(
                f"{einstieg.url}: {len(links)} Adressen, {anbieter.max_produkte} abgerufen")
            log.warning("%s: %s liefert %d Adressen, Deckel steht bei %d - "
                        "die Seite gilt als unvollstaendig gelesen",
                        anbieter.name, einstieg.url, len(links), anbieter.max_produkte)
        for url in links[:anbieter.max_produkte]:
            if frist_bis is not None and time.monotonic() > frist_bis:
                # Sauber abbrechen und das Teilergebnis behalten - aber die
                # Seite gilt NICHT als gelesen, sonst altert ihr Rest.
                frist_erreicht = True
                vollstaendig = False
                break
            try:
                seite = _hole(url)
            except GeraeteAbrufFehler as exc:
                log.info("%s: %s uebersprungen (%s)", anbieter.name, url, exc)
                vollstaendig = False
                continue
            except Exception as exc:                   # noqa: BLE001
                log.warning("%s: %s nicht abrufbar (%s)", anbieter.name, url, exc)
                vollstaendig = False
                continue
            bilanz.produkte_abgerufen += 1
            try:
                roh = adapter.lies(seite, url)
            except GeraeteAbrufFehler as exc:
                # Eine unlesbare Nutzlast ist NICHT "keine Geraete auf der
                # Seite" - dieselbe Lehre wie bei `PromoExtractionError`.
                log.info("%s: %s unlesbar (%s)", anbieter.name, url, exc)
                vollstaendig = False
                continue
            _uebernimm(roh, anbieter, einstieg, url, katalog, farben, heute,
                       bilanz)
        if vollstaendig:
            bilanz.gelesene_einstiege.add(einstieg.url)

    if frist_erreicht:
        bilanz.status = "frist"
        bilanz.grund = "Zeitbudget des Geraetezweigs erschoepft"
    elif bilanz.gelesene_einstiege:
        bilanz.status = "ok" if bilanz.listungen else "leer"
        bilanz.grund = "; ".join(gruende)[:300]
    else:
        # Keine einzige Einstiegsseite vollstaendig gelesen. Der Anbieter
        # gilt als ungelesen - `vollstaendig` ist False, also altert nichts.
        #
        # "Nicht vollstaendig gelesen" ist aber NICHT dasselbe wie "nicht
        # lesbar", und der erste echte Lauf hat genau daran gezeigt, wie
        # irrefuehrend die alte Meldung war: mobilcom-debitel stand mit
        # "kein Einstieg lesbar" im Protokoll und hatte dabei 84 Listungen
        # geliefert - die Einstiegsseite war lesbar, nur ihr Deckel war
        # erreicht. Wer das Protokoll liest, muss den Unterschied sehen.
        bilanz.status = "fehler"
        teile = gruende + bilanz.gedeckelt
        if not teile and (bilanz.produkte_abgerufen or bilanz.listungen):
            teile = [f"Einstieg gelesen, aber unvollstaendig ausgewertet: "
                     f"{bilanz.produkte_abgerufen} Produktseiten abgerufen, "
                     f"{len(bilanz.listungen)} Listungen"]
        bilanz.grund = "; ".join(teile)[:300] or "kein Einstieg lesbar"
    bilanz.nicht_verlinkt = sorted(set(bilanz.besucht) - erlaubt)
    return bilanz


def _uebernimm(rohsaetze, anbieter, einstieg, quelle_url: str, katalog: Katalog,
               farben: dict, heute: str, bilanz: Anbieterbilanz) -> None:
    bilanz.rohsaetze += len(rohsaetze or [])
    gelesen = []
    for satz in rohsaetze:
        if satz.get("waehrung") and satz["waehrung"] not in ("EUR", ""):
            continue          # ein Preis in fremder Waehrung ist kein Vergleichswert
        listung = _als_listung_satz(satz, anbieter, einstieg, quelle_url,
                                    katalog, farben, heute, bilanz)
        if listung is not None:
            gelesen.append(listung)
    for listung in _ohne_sammelknoten(gelesen):
        bilanz.listungen.append(listung)
        if listung.farbe_roh and listung.farbe_normalisiert is None:
            bilanz.unbekannte_farben.append(listung.farbe_roh)


def _mit_sku(rohsaetze, anbieter, einstieg, katalog: Katalog, farben: dict,
             heute: str, bilanz: Anbieterbilanz) -> list[dict]:
    """Jedem Buendel-Rohsatz seine `sku_id` geben - oder ihn verwerfen.

    Ein Buendel zeigt auf ein GERAET, und der Schluessel dafuer ist
    dieselbe `sku_id`, die eine Listung traegt (`tco_model.Buendel.sku_id`).
    Sie wird deshalb auf demselben Weg gebildet wie dort - ueber
    `lies_listung` und damit ueber den KATALOG, nie ueber ein Zerlegen des
    Titels. Wer sie hier anders rechnete, baute eine zweite Namensmenge:
    die TCO-Tafel schlaegt den Geraetenamen ueber die Listung derselben SKU
    nach und faende nichts.

    Der Satz bekommt an dieser Stelle bewusst KEINEN Preis mit. Eine
    Listung, die aus einem Buendel entstuende, truege einen Monatsbetrag in
    einer Spalte voller Kassenpreise - genau der Befund, mit dem dieses
    Vorhaben angefangen hat. Gebraucht wird hier nur der Schluessel.

    Ein Titel ohne Katalogtreffer landet in derselben Arbeitsliste wie im
    Listungsweg (`unbekannte_titel`): dass ein Geraet dem Katalog fehlt,
    ist eine Auskunft und keine Eigenheit dieser Lesart.
    """
    out: list[dict] = []
    for satz in rohsaetze:
        listung = lies_listung(
            titel=satz.get("titel", ""), anbieter=anbieter.name,
            anbieter_typ=anbieter.typ, netz=anbieter.netz,
            quelle_url=urljoin(einstieg.url, satz.get("url") or "")
            or einstieg.url,
            abgerufen_am=heute, katalog=katalog, farben=farben,
            confidence=_belegstufe(satz.get("quelle")),
            farbe_roh=satz.get("farbe") or "",
            speicher_gb=satz.get("speicher_gb"),
            einstieg_url=einstieg.url)
        if listung is None:
            titel = (satz.get("titel") or "").strip()
            if titel:
                bilanz.unbekannte_titel.append(titel)
            continue
        if listung.farbe_roh and listung.farbe_normalisiert is None:
            bilanz.unbekannte_farben.append(listung.farbe_roh)
        # Der ZUSTAND reist mit - er ist dieselbe Erkennung wie die, aus
        # der die `-refurbished`-Strecke der SKU entsteht, und die
        # TCO-Tafel braucht ihn als Feld, nicht als Suffix (QA-Befund B1).
        out.append({**satz, "sku_id": listung.sku_id,
                    "anbieter": anbieter.name,
                    "zustand": listung.zustand,
                    "quelle_url": listung.quelle_url})
    return out


def _ohne_sammelknoten(listungen: list) -> list:
    """Den Container-Knoten einer Produktseite verwerfen.

    freenet traegt je Seite einen Product-Knoten fuer das Geraet UND je einen
    fuer seine Varianten. Der erste hat keinen Speicher und keine Farbe - er
    ist eine Zusammenfassung, kein Artikel. Als eigene Listung geschrieben
    kollidierte er mit jeder anderen Variante, deren Speicher nicht gelesen
    werden konnte, und die Preishistorie sprang zwischen zwei Werten.

    Verworfen wird nur, was FUER DASSELBE GERAET auf DERSELBEN Seite eine
    genauere Entsprechung hat - eine Seite, die ausschliesslich einen
    Sammelknoten traegt, behaelt ihn.
    """
    mit_speicher = {l.device_id for l in listungen if l.speicher_gb is not None}
    return [l for l in listungen
            if l.speicher_gb is not None or l.device_id not in mit_speicher]


def _belegstufe(quelle: str) -> str:
    """Wie gut ein Satz belegt ist - nachgeschlagen, nicht aufgezaehlt."""
    for adapter in ADAPTER.values():
        if adapter.name == quelle:
            return adapter.confidence
    # "microdata" ist keine eigene Methode, sondern die zweite Stufe der
    # Kaskade in `produkte_aus_html` - so haengt ALDI TALK am ldjson-Adapter.
    return "hoch" if quelle in ("ldjson", "shopify", "microdata") else "mittel"


def _als_listung_satz(satz, anbieter, einstieg, quelle_url, katalog, farben,
                      heute, bilanz):
    listung = lies_listung(
        titel=satz.get("titel", ""), anbieter=anbieter.name,
        anbieter_typ=anbieter.typ, netz=anbieter.netz,
        quelle_url=urljoin(quelle_url, satz.get("url") or "") or quelle_url,
        abgerufen_am=heute, katalog=katalog, farben=farben,
        verfuegbarkeit=satz.get("verfuegbarkeit") or "unbekannt",
        # Die Belegstufe kommt aus der REGISTRY, nicht aus einer Liste von
        # Namen an dieser Stelle: eine Liste hier haette jeder neue Adapter
        # stillschweigend verfehlt, und seine Listungen stuenden als
        # "mittel" da, obwohl sie aus strukturierten Daten stammen.
        confidence=_belegstufe(satz.get("quelle")),
        farbe_roh=satz.get("farbe") or "", ean=satz.get("ean") or "",
        zustand_hinweis=satz.get("zustand_hinweis") or "",
        # Strukturierte Daten schlagen Textextraktion - die Rangfolge aus
        # Teil C1. Vodafone und o2 nennen den Speicher als eigenes Feld
        # (`capacity.displayLabel`, der Angebotsslug); ohne diese Zeile
        # haette `lies_listung` ihn erneut aus dem Titel geraten, den dieser
        # Adapter selbst zusammengesetzt hat.
        speicher_gb=satz.get("speicher_gb"),
        einstieg_url=einstieg.url,
        **_preisfelder(anbieter, satz))
    if listung is None:
        titel = (satz.get("titel") or "").strip()
        if titel:
            bilanz.unbekannte_titel.append(titel)
    return listung


# --------------------------------------------------------------------------
# Alle Anbieter
# --------------------------------------------------------------------------

# Was jedem noch ausstehenden Anbieter vom Zeitbudget mindestens bleiben
# muss, bevor ein grosser Anbieter weiterlaufen darf. Ohne diese Reserve
# frass freenet (Crawl-delay mal ueber 70 Produktseiten) das gesamte Budget,
# und ALDI TALK stand ab dem 15.08.2026 jede Nacht mit "frist, 0 Listungen
# aus 5 Produktseiten" da - seine letzte Bestaetigung blieb der 14.08.
_MINDEST_JE_ANBIETER = 120.0


def sammle(quellen, katalog: Katalog, farben: dict, hole: Callable, heute: str,
           jetzt: Optional[datetime] = None,
           frist_sekunden: Optional[float] = None) -> dict:
    """Den ganzen Beobachtungsraum abarbeiten.

    Sequenziell, nicht nebenlaeufig: die Bremse ist ohnehin der Abstand je
    Domain (bei Medimax und ep.de zehn Sekunden aus ihrer eigenen
    robots.txt), und zwei parallele Collector gegen denselben Betreiber
    waeren effektiv der halbe Abstand - also ein Bruch der Vorgabe.

    Das Zeitbudget ist keine gemeinsame Weide: jeder Anbieter darf hoechstens
    so viel verbrauchen, dass jedem NACH ihm noch `_MINDEST_JE_ANBIETER`
    Sekunden bleiben. Gezaehlt werden dabei nur Anbieter, die wirklich
    crawlen werden (aktiv, crawlbar, Adapter vorhanden) - ein uebersprungener
    kostet nichts und reserviert nichts.
    """
    jetzt = jetzt or datetime.now(timezone.utc)
    waechter = RobotsWaechter(hole=hole)
    frist_bis = (time.monotonic() + frist_sekunden) if frist_sekunden else None

    sortiert = sorted(quellen.anbieter, key=lambda a: (a.rang, a.name))
    crawlt = [a.name for a in sortiert
              if a.crawlbar and ADAPTER.get(a.methode) is not None]

    bilanzen = []
    for anbieter in sortiert:
        eigene_frist = frist_bis
        if frist_bis is not None and anbieter.name in crawlt:
            nach_mir = len(crawlt) - crawlt.index(anbieter.name) - 1
            rest = frist_bis - time.monotonic()
            # Die Untergrenze ist `_MINDEST_JE_ANBIETER`, nicht null - und
            # das ist der ganze Unterschied. Mit `max(0, …)` bekaeme bei
            # KNAPPEM Budget jeder ausser dem letzten null Sekunden: die
            # Reserve fuer die Nachfolgenden frisst dann den eigenen Anteil
            # vollstaendig auf. Das waere dasselbe Verhungern, das diese
            # Rechnung verhindern soll, nur am anderen Ende der Liste.
            # Rechenbeispiel: 240 s Budget, 6 crawlende Anbieter -> der
            # erste haette 240 - 5*120 = -360, also 0.
            #
            # `frist_bis` bleibt die harte Grenze: die Summe der Anteile
            # darf sie ueberschreiten, der einzelne Abruf nicht.
            eigene_frist = min(frist_bis,
                               time.monotonic()
                               + max(_MINDEST_JE_ANBIETER,
                                     rest - nach_mir * _MINDEST_JE_ANBIETER))
        bilanzen.append(sammle_anbieter(
            anbieter, katalog, farben, hole, heute, waechter, jetzt,
            eigene_frist))
    return {
        "anbieter": bilanzen,
        "listungen": [l for b in bilanzen for l in b.listungen],
        "abgefragt": sum(1 for b in bilanzen if b.status in ("ok", "leer", "frist")),
        "unbekannte_titel": sorted({t for b in bilanzen for t in b.unbekannte_titel}),
    }
