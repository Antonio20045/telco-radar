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

# Methoden, fuer die es in diesem Abschnitt einen Adapter gibt. Alles andere
# ist gemessen und dokumentiert (config/geraete_quellen.yaml), wartet aber auf
# eigenen Code - drei stabile Adapter sind mehr wert als zwanzig halbe.
UMGESETZTE_METHODEN = ("ldjson", "shopify")


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
    gelesene_einstiege: set = field(default_factory=set)
    seiten_versucht: int = 0
    produkte_abgerufen: int = 0
    unbekannte_titel: list = field(default_factory=list)
    unbekannte_farben: list = field(default_factory=list)
    gedeckelt: list = field(default_factory=list)
    besucht: list = field(default_factory=list)
    nicht_verlinkt: list = field(default_factory=list)

    @property
    def vollstaendig(self) -> bool:
        """Darf die Auslistungslogik fuer diesen Anbieter ueberhaupt laufen?"""
        return self.status in ("ok", "leer") and bool(self.gelesene_einstiege)


# --------------------------------------------------------------------------
# Linkernte
# --------------------------------------------------------------------------

def ernte_links(inhalt: str, basis_url: str, pfadmuster: str = "",
                kind: str = "static") -> list[str]:
    """Produktadressen aus einer Einstiegsseite.

    `static` liest echte `<a href>`, `sitemap` die `<loc>`-Eintraege. Beides
    sind Adressen, die der Anbieter SELBST nennt; geraten wird nichts.
    Reihenfolge = Seitenreihenfolge, entdoppelt.
    """
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
        if pfadmuster and pfadmuster not in url:
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
# Ein Anbieter
# --------------------------------------------------------------------------

def _preisfelder(anbieter, preis: Optional[float]) -> dict:
    """Welche der zwei Preisarten traegt diese Zahl? (Teil C4)

    Die umgesetzten Adapter bedienen ausschliesslich Geraetepreise OHNE
    Vertrag - jede Quelle, deren strukturierter Preis in Wahrheit eine
    Zuzahlung ist, steht in der Konfiguration mit `aktiv: false` und dem
    Grund dabei. Der Lockpreis-Waechter ist die zweite Sicherung: taucht
    trotzdem eine Buendelzahl auf, wird sie NICHT als Ladenpreis gefuehrt.
    """
    if preis is None or ist_lockpreis(preis):
        return {"preis_ohne_vertrag": None}
    return {"preis_ohne_vertrag": preis}


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
    if anbieter.methode not in UMGESETZTE_METHODEN:
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

    def _hole(url: str) -> str:
        darf, grund = waechter.darf(url, jetzt)
        if not darf:
            raise GeraeteAbrufFehler(grund)
        warte = abstand - (time.monotonic() - letzter_abruf[0])
        if letzter_abruf[0] and warte > 0:
            time.sleep(warte)
        letzter_abruf[0] = time.monotonic()
        bilanz.besucht.append(url)
        status, text = hole(url)
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

        if einstieg.kind == "shopify" or anbieter.methode == "shopify":
            try:
                roh = produkte_aus_shopify(inhalt)
            except GeraeteAbrufFehler as exc:
                gruende.append(f"{einstieg.url}: {exc}")
                continue
            _uebernimm(roh, anbieter, einstieg, einstieg.url, katalog, farben,
                       heute, bilanz)
            bilanz.gelesene_einstiege.add(einstieg.url)
            continue

        links = ernte_links(inhalt, einstieg.url, einstieg.pfadmuster, einstieg.kind)
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
            _uebernimm(produkte_aus_html(seite), anbieter, einstieg, url,
                       katalog, farben, heute, bilanz)
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
        bilanz.status = "fehler"
        bilanz.grund = "; ".join(gruende)[:300] or "kein Einstieg lesbar"
    bilanz.nicht_verlinkt = sorted(set(bilanz.besucht) - erlaubt)
    return bilanz


def _uebernimm(rohsaetze, anbieter, einstieg, quelle_url: str, katalog: Katalog,
               farben: dict, heute: str, bilanz: Anbieterbilanz) -> None:
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


def _als_listung_satz(satz, anbieter, einstieg, quelle_url, katalog, farben,
                      heute, bilanz):
    listung = lies_listung(
        titel=satz.get("titel", ""), anbieter=anbieter.name,
        anbieter_typ=anbieter.typ, netz=anbieter.netz,
        quelle_url=urljoin(quelle_url, satz.get("url") or "") or quelle_url,
        abgerufen_am=heute, katalog=katalog, farben=farben,
        verfuegbarkeit=satz.get("verfuegbarkeit") or "unbekannt",
        confidence="hoch" if satz.get("quelle") in ("ldjson", "shopify") else "mittel",
        farbe_roh=satz.get("farbe") or "", ean=satz.get("ean") or "",
        einstieg_url=einstieg.url,
        **_preisfelder(anbieter, satz.get("preis")))
    if listung is None:
        titel = (satz.get("titel") or "").strip()
        if titel:
            bilanz.unbekannte_titel.append(titel)
    return listung


# --------------------------------------------------------------------------
# Alle Anbieter
# --------------------------------------------------------------------------

def sammle(quellen, katalog: Katalog, farben: dict, hole: Callable, heute: str,
           jetzt: Optional[datetime] = None,
           frist_sekunden: Optional[float] = None) -> dict:
    """Den ganzen Beobachtungsraum abarbeiten.

    Sequenziell, nicht nebenlaeufig: die Bremse ist ohnehin der Abstand je
    Domain (bei Medimax und ep.de zehn Sekunden aus ihrer eigenen
    robots.txt), und zwei parallele Collector gegen denselben Betreiber
    waeren effektiv der halbe Abstand - also ein Bruch der Vorgabe.
    """
    jetzt = jetzt or datetime.now(timezone.utc)
    waechter = RobotsWaechter(hole=hole)
    frist_bis = (time.monotonic() + frist_sekunden) if frist_sekunden else None

    bilanzen = []
    for anbieter in sorted(quellen.anbieter, key=lambda a: (a.rang, a.name)):
        bilanzen.append(sammle_anbieter(
            anbieter, katalog, farben, hole, heute, waechter, jetzt, frist_bis))
    return {
        "anbieter": bilanzen,
        "listungen": [l for b in bilanzen for l in b.listungen],
        "abgefragt": sum(1 for b in bilanzen if b.status in ("ok", "leer", "frist")),
        "unbekannte_titel": sorted({t for b in bilanzen for t in b.unbekannte_titel}),
    }
