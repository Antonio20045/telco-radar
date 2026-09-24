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
   (`robots.py`), und sie gilt JE ABRUF - fuer jeden Abruf der Sammelphase
   UND fuer die Nachbearbeitungs-Haken der Adapter, die nach ihr noch
   einmal abrufen (`hole_mit_robots`, gerufen aus
   `geraete_pipeline.nachsammle_buendel`). Beide gehen durch dieselbe
   `Abrufschleuse`. Ein Lauf, der im Fenster startet, steht eine halbe
   Stunde spaeter davor - die Uhr laeuft mit (`_laufuhr`), und der
   Zeitanteil eines Anbieters mit Fenster endet spaetestens mit diesem
   (`_fensterfrist`). Wer draussen steht, wird uebersprungen - nicht
   gealtert, auch wenn die Tuer erst mitten im Lauf zugegangen ist.
3. **Eine Einstiegsseite gilt erst als GELESEN, wenn ihre Produktseiten
   abgerufen wurden** - und zwar alle bis auf die, die der Anbieter selbst
   als nicht mehr vorhanden beantwortet (HTTP 404/410), und auch die nur
   bis zu `_MINDESTANTEIL_GELESENER_PRODUKTSEITEN`. Nur eine gelesene Seite
   darf die Auslistungslogik ihre Geraete altern lassen. Ein Zeitbudget,
   ein Deckel oder ein Netzfehler mitten in der Seite macht aus einem halben
   Abruf sonst eine halbe Auslistung; eine veraltete Sitemap dagegen ist die
   erwartbare Lage und kein Ausfall (siehe den Abschnitt zu
   `_einstieg_gelesen`).
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
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ...geraete_model import Katalog, lies_listung
from . import autoerkennung
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
    derselben Quelle. Fuer einen Einstieg mit `kind: buendel` (o2: eine
    EIGENE Adresse, die nur Buendel traegt) wird sie ANSTELLE von `lies`
    aufgerufen. Fuer einen NORMALEN Einstieg ohne diesen `kind` wird sie
    ZUSAETZLICH zu `lies` auf JEDER Produktseite aufgerufen, die die
    generische Ernte-Schleife ohnehin schon holt (Vodafone, B1,
    05.09.2026: dieselbe Detailantwort traegt Geraetepreis UND
    Buendelpreise, ein zweiter Abruf waere redundant). Ihre Saetze werden
    KEINE Listungen: sie tragen Zuzahlung, Geraeterate, Tarifbetrag und
    Tarifbezug und gehoeren damit in `geraete_tco.json`, nicht in die
    Preisspalte der Geraeteseite.

    `loese_tarifnamen(hole, kopfzeilen, rohbuendel) -> int` ist OPTIONAL
    und laeuft NICHT waehrend des Sammelns, sondern danach, aus der
    Pipeline heraus (`geraete_pipeline.py`) - ein Adapter bleibt sonst ein
    reiner Text-zu-Daten-Uebersetzer ohne eigenes Netz. Sie darf
    zusaetzliche GETs machen, um einen Tarifnamen aufzuloesen, den die
    Sammelantwort selbst nicht nennt (Vodafone: nur ein `offerCoreHash`,
    keine Klarname - siehe `vodafone.py` Modulkopf, Abschnitt B1).

    `ergaenze_buendel(hole, kopfzeilen, rohbuendel) -> int` ist dieselbe
    Bauform fuer BETRAEGE statt Namen (S2-C, 09.09.2026): 1&1 nennt seine
    Bereitstellungsgebuehr erst im Tarifdetails-Iframe, einer eigenen
    Adresse, die die Geräteseite selbst verlinkt. Der Haken macht EIN GET
    je Tarif-Slug und setzt `anschlusspreis` auf den Saetzen - siehe
    `einsundeins.ergaenze_bereitstellungsgebuehr`.

    `buendel_auf_produktseite` (Voreinstellung True) sagt, ob die zweite
    Lesart auf den Produktseiten des ERNTE-Wegs ueberhaupt sinvoll ist.
    Vodafone traegt seine Buendel in derselben Detailantwort wie die
    Listungen (B1) - dort gehoert der Zusatzaufruf hin. congstar (B3)
    liest seine Buendel auf EIGENEN Tarifseiten-Einstiegen (`kind:
    buendel`, wie Telekom und o2); seine Produktseiten tragen KEIN
    prefetchedPlan, der Zusatzaufruf wuerde auf jeder der 55 Seiten
    werfen. Ein Adapter mit eigenen Buendel-Einstiegen setzt die Flagge
    auf False - die Einstiege selbst rufen `lies_buendel` natuerlich
    weiterhin.

    `lies_buendel(text, url, proben=None)` - der dritte Parameter ist die
    PROVIDER-PROBE (FM-2, P5-Auftrag 2): der Collector reicht die Bilanz-
    Zaehler des Anbieters hinein, und ein Adapter, der Feld-Proben kennt
    (o2: metric3+metric2 == monthlyPrice usw., Praezedenz Phase S),
    zaehlt hinein, wie viele der erwarteten Saetze ihre Feldebenen noch
    tragen. Adapter ohne Proben ignorieren ihn. Der Zaehler steht danach
    in `Anbieterbilanz.proben` und wird protokolliert - er loest nichts
    aus, er meldet.
    """
    name: str
    lies: Callable
    ernte: Optional[Callable] = None
    direkt: bool = False
    lies_buendel: Optional[Callable] = None
    buendel_auf_produktseite: bool = True
    loese_tarifnamen: Optional[Callable] = None
    ergaenze_buendel: Optional[Callable] = None
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
    fuehren kann und `mark_stale` ihre Geraete in Ruhe laesst.

    `status` ist der HTTP-Statuscode, WENN der Abruf bis zu einer Antwort
    kam - sonst `None`. Der Unterschied traegt die Unterscheidung zwischen
    einer TOTEN ADRESSE (der Anbieter antwortet "gibt es nicht") und einem
    ungelesenen Abruf (robots-Sperre, Besuchszeit, Netzfehler - keine
    Antwort, keine Aussage). `None` und nicht 0: 0 waere hier ein erfundener
    Statuscode, und geraten wird nichts (CLAUDE.md Clean Code 3). Der
    Aufrufer fragt das Feld ab, NICHT den Meldungstext - ein Zustand, den
    man an einem String erkennt, kippt bei der ersten Umformulierung.
    """

    def __init__(self, *args, status: Optional[int] = None):
        super().__init__(*args)
        self.status = status


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
    # Dieselben Faelle MIT Kontext (art titel|farbe, wert, quelle des
    # Feldes) - die Grundlage fuer data/state/geraete_unbekannt.jsonl.
    # Die String-Listen darueber bleiben unberuehrt: das Protokoll liest
    # sie, und der naechtliche Lauf gibt an niemanden zurueck.
    unbekannt: list = field(default_factory=list)
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
    # PROVIDER-PROBE (FM-2, P5-Auftrag 2): Existenz-Schwelle der Feld-
    # ebenen, gefuellt vom Adapter selbst (`lies_buendel(..., proben=...)`,
    # heute nur o2 mit den drei Proben aus Phase S). Zaehlungen:
    # `kandidaten`, `bestanden` und je gescheiterter Feldebene eine eigene
    # (z. B. `metric3+metric2`). Leer heisst "kein Adapter mit Proben" -
    # kein Lautwerden, denn es gibt keine Erwartung.
    proben: dict = field(default_factory=dict)
    # Produktadressen, die der Anbieter selbst nennt, die es aber nicht
    # mehr gibt (HTTP 404/410). Eine BENANNTE LUECKE und kein Ausfall:
    # freenets eigene Sitemap fuehrt veraltete Produktseiten, und neun
    # davon haben am 21.09.2026 einen Lauf mit 36 gelesenen Seiten und 133
    # Listungen auf `fehler` gekippt. Als Liste und nicht als blosse Zahl,
    # damit die naechste Sitzung sieht, WELCHE Adresse tot ist.
    tote_adressen: list = field(default_factory=list)
    # Wie viele Produktseiten ueberhaupt versucht wurden - der Nenner, gegen
    # den `_MINDESTANTEIL_GELESENER_PRODUKTSEITEN` rechnet. Ohne ihn ist
    # `produkte_abgerufen` eine Zahl ohne Bezugsgroesse: 36 gelesene Seiten
    # sind bei 45 versuchten ein guter Lauf und bei 450 ein Ausfall.
    produkte_versucht: int = 0
    # Hat die Besuchszeit aus der robots.txt diesen Abruf verhindert?
    # STRUKTURELL festgehalten und nicht am Grundtext erkannt: fuer den
    # Abdeckungswaechter (P1/C2) ist das der Unterschied zwischen "nicht
    # gelesen" (keine Aussage) und "gelesen, nichts gefunden" (Ausfall),
    # und ein Waechter, der diese zwei an einem String auseinanderhaelt,
    # kippt bei der ersten Umformulierung.
    ausserhalb_besuchszeit: bool = False

    @property
    def vollstaendig(self) -> bool:
        """Darf die Auslistungslogik fuer diesen Anbieter ueberhaupt laufen?

        Gefragt ist der EINSTIEG, nicht jede einzelne Produktadresse: was
        als gelesener Einstieg zaehlt, entscheidet `_einstieg_gelesen()`.
        """
        return self.status in ("ok", "leer") and bool(self.gelesene_einstiege)


# --------------------------------------------------------------------------
# WANN GILT EINE EINSTIEGSSEITE ALS GELESEN? (22.09.2026)
# --------------------------------------------------------------------------
# Bis hierher: nur dann, wenn JEDE ihrer Produktadressen durchkam. Gemessen
# an der Wirklichkeit war das zu streng, und der Preis war hoch.
# mobilcom-debitel stand seit dem 29.08.2026 mit NULL vollstaendigen Laeufen
# im Bestand (`letzter_lauf` fehlte ganz), obwohl es an 23 Tagen je 133
# Listungen lieferte: freenets eigene sitemap.xml fuehrt veraltete
# Produktadressen, neun davon antworteten am 21.09.2026 mit HTTP 404 - und
# neun tote Adressen kippten einen Lauf, der 36 von 45 Seiten gelesen hatte,
# auf `fehler`. Ein substanziell erfolgreicher Lauf wurde als Totalausfall
# verbucht; der Ausfall-Alarm hat ihn deshalb nie gemeldet, und sein Bestand
# alterte nie sauber.
#
# ZWEI DINGE, DIE NICHT VERWECHSELT WERDEN DUERFEN:
#   * TOTE ADRESSE: der Anbieter antwortet, und seine Antwort lautet "diese
#     Seite gibt es nicht" (404) bzw. "gibt es nicht mehr" (410). Das ist
#     eine AUSKUNFT ueber die Adresse, kein gescheiterter Leseversuch - eine
#     veraltete Sitemap ist die erwartbare Lage, nicht der Ausnahmefall. Sie
#     wird gezaehlt und als benannte Luecke gefuehrt (`tote_adressen`).
#   * NICHT GELESEN: robots-Sperre, Besuchszeit, Zeitbudget, Deckel,
#     Netzfehler, 5xx, unlesbare Nutzlast. Da steht etwas, das wir nicht
#     gesehen haben - "nicht gelesen ist nicht leer" (CLAUDE.md Clean Code
#     6). EIN solcher Fall macht die Seite weiterhin unvollstaendig.
_TOTE_STATUS = (404, 410)

# Wie viel einer Einstiegsseite gelesen sein muss, damit sie als gelesen
# zaehlt - und damit `mark_stale` ihre Geraete altern darf.
#
# DIE EINHEIT ZUERST, sonst begruendet man sich in die Irre. Diese Schwelle
# rechnet in ADRESSEN. Der Abdeckungswaechter rechnet in ZEILEN, also in
# Listungen plus Buendelsaetzen (`geraete_store.Messtag.zeilen`). Das sind
# zwei Groessen und nicht zwei Schreibweisen derselben: am 21.09.2026
# trugen 45 Adressen 133 Listungen, im Schnitt drei je Seite und ungleich
# verteilt. `geraete_store.ABDECKUNG_RUECKGANG` kann diese Schwelle
# deshalb WEDER nach unten begruenden NOCH nach oben decken - elf tote
# Adressen (24 %) koennen 50 Zeilen (37 %) kosten, und derselbe Tag ist
# dann zugleich "vollstaendig gelesen" und ein Rueckgangsbefund. Das ist
# kein Widerspruch, sondern die richtige Auskunft aus zwei Blickwinkeln:
# gealtert wird, was wirklich weg ist, gemeldet wird, DASS es weg ist.
#
# WAS DIE 0,75 TRAEGT - und mehr behauptet sie nicht:
#   * GEMESSEN: der Fall, um den es geht, liegt bei 36 von 45 = 0,80.
#     0,75 laesst ihn durch und haette Luft fuer zwei weitere tote
#     Adressen; eine Sitemap-Pflege, die hinterherhinkt, kippt den Lauf
#     damit nicht mehr.
#   * NACH OBEN begrenzt sie der Zweck: ein ECHTER Ausfall - Seite weg,
#     Adapter kaputt, Domain umgezogen, robots zu - trifft nicht jede
#     vierte Adresse, sondern praktisch alle. Zwischen 0,80 (Sitemap-Pflege
#     laeuft hinterher) und den 0,0-0,1 eines echten Ausfalls liegt diese
#     Schwelle mit Abstand nach beiden Seiten.
#   * NACH UNTEN haelt sie NICHT allein, und das ist keine Schwaeche der
#     Zahl, sondern ihre Bauart: eine Schwelle je Nacht sieht immer nur
#     diese eine Nacht. Ein Anbieter, der Nacht fuer Nacht knapp darunter
#     bleibt, broeselt unter ihr weg, ohne sie je zu reissen. Dagegen
#     steht der VERLAUF und nicht die Schwelle -
#     `geraete_store.ALARM_EROSION` vergleicht die GELESENEN ADRESSEN
#     (dieselbe Einheit, deshalb traegt der Vergleich) gegen den
#     aeltesten Messtag im Fenster und meldet, bevor der Anbieter leer
#     ist.
_MINDESTANTEIL_GELESENER_PRODUKTSEITEN = 0.75


def _einstieg_gelesen(versucht: int, tot: int) -> bool:
    """Reicht das Gelesene dieser Einstiegsseite fuer "gelesen"?

    `versucht` sind die Produktadressen, an denen dieser Lauf wirklich war,
    `tot` die davon, die der Anbieter selbst als nicht mehr vorhanden
    beantwortet hat. Eine Einstiegsseite ganz ohne Produktadressen ist
    gelesen - es gab nichts nachzuladen; das ist "gelesen, nichts
    gefunden" und damit eine Aussage, kein Ausfall.
    """
    if versucht <= 0:
        return True
    return (versucht - tot) >= _MINDESTANTEIL_GELESENER_PRODUKTSEITEN * versucht


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
                                        ernte=vodafone_modul.ernte,
                                        # B1 (05.09.2026): dieselbe
                                        # Detailantwort traegt unter
                                        # `atomics[].prices.composition`
                                        # auch die Buendelpreise - siehe
                                        # Adapter-Docstring oben.
                                        lies_buendel=vodafone_modul.lies_buendel,
                                        loese_tarifnamen=vodafone_modul.loese_tarifnamen))
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
    #
    # B3 (08.09.2026): derselbe Adapter liest auch die TARIFseiten als
    # Buendelkatalog (eigene Einstiege mit `kind: buendel` je Tarif) - die
    # Kombinatorik Geraet x Tarif steht dort serverseitig im selben
    # Flight-Payload, die Gerateseite traegt nur die Hardware-Preise. Der
    # Tarifname steht in derselben Antwort (`prefetchedPlan.variants[].title`),
    # deshalb braucht congstar anders als Vodafone keinen
    # `loese_tarifnamen`-Haken - derselbe Grund wie bei der Telekom.
    # `buendel_auf_produktseite=False`: Die Produktseiten tragen KEIN
    # prefetchedPlan - der Zusatzaufruf des Ernte-Wegs wuerde auf jeder der
    # bis zu 55 Seiten werfen (gemessen am ersten B3-Lauf), die Bündel
    # kommen ausschliesslich über die Tarifseiten-Einstiege.
    registriere("congstar_next", Adapter(name="congstar_next",
                                         lies=congstar_modul.lies,
                                         lies_buendel=congstar_modul.lies_buendel,
                                         buendel_auf_produktseite=False))
    # Die Kategorieseite IST die Nutzlast (`direkt`): sie traegt die
    # absoluten Betraege serverseitig, und die zehn Produktadressen stehen
    # als echte `<a href>` darin - der Adapter liest sie aus demselben
    # Text und braucht kein eigenes `ernte`.
    #
    # B2 (08.09.2026): derselbe Adapter liest auch die Buendel-Kategorieseite
    # (`?tariffId=MF_...`, eigene Einstiege mit `kind: buendel` je Tarif).
    # Der Tarifname steht in derselben Antwort (`productList.selectedPlan`),
    # deshalb braucht Telekom anders als Vodafone keinen
    # `loese_tarifnamen`-Haken.
    registriere("telekom_kategorie", Adapter(name="telekom_kategorie",
                                             lies=telekom_modul.lies,
                                             lies_buendel=telekom_modul.lies_buendel,
                                             direkt=True))
    # NICHT `direkt`: die Kategorieseite `/smartphones` traegt kein
    # Produktschema, nur die verlinkten Produktseiten. Die Linkernte ist
    # ANBIETEREIGEN, weil die Seite neben ihren 42 Katalogkacheln 125
    # weitere Adressen derselben Domain fuehrt - siehe
    # `einsundeins.ernte`.
    #
    # B4 (08.09.2026): derselbe Adapter liest auf JEDER Produktseite auch
    # deren Bündelpreiskarte (`hwdVariantsPrices`, Default-Tarif ueber alle
    # Farben und Speichergroessen) - dieselbe Antwort, die `lies()` fuer
    # die Listung ohnehin zerlegt, kein zusaetzlicher Abruf (Vodafone-B1-
    # Muster; `buendel_auf_produktseite` bleibt an). Der Satz traegt nur
    # den kombinierten Monatsbetrag (§ 13.2), siehe `einsundeins.lies_
    # buendel`.
    #
    # S2-C (09.09.2026): dieselbe Antwort traegt AUCH die Geräte-
    # Einmalzahlung je Variante (`hwdVariantsOneOffPaymentFees`) und den
    # Tarifdetails-Link. Die BEREITSTELLUNGSGEBUEHR steht erst hinter
    # jenem Link - dafuer der `ergaenze_buendel`-Haken: ein GET je
    # Tarif-Slug, nach dem Sammeln, aus der Pipeline.
    registriere("einsundeins_buendel",
                Adapter(name="einsundeins_buendel",
                        lies=einsundeins_modul.lies,
                        ernte=einsundeins_modul.ernte,
                        lies_buendel=einsundeins_modul.lies_buendel,
                        ergaenze_buendel=(
                            einsundeins_modul.ergaenze_bereitstellungsgebuehr)))
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


# --------------------------------------------------------------------------
# Die Uhr des Laufs
# --------------------------------------------------------------------------
# Bis zum 22.09.2026 reichte die Pipeline EINEN eingefrorenen Zeitstempel bis
# an jeden einzelnen Abruf durch (`waechter.darf(url, jetzt)`). Ein Lauf, der
# um 07:57 UTC startet, fragte damit um 08:20 immer noch mit 07:57 - und bekam
# "im Fenster", obwohl das Fenster von medimax.de und ep.de (Visit-time
# 0200-0800) laengst zu war. Der Crawl darf planmaessig bis zu `--frist`
# Sekunden dauern, und genau diese zwei Anbieter stehen weit hinten in der
# Reihenfolge; der Verstoss war also der Regelfall, nicht der Ausnahmefall.
#
# ZWEI UHREN, DIE NICHT VERWECHSELT WERDEN DUERFEN:
#   * `heute` (der Datumsstempel der Messung) bleibt eingefroren. Er steht an
#     jeder Listung, in `geraete_preise.jsonl` und in der Laufhistorie; ein
#     Lauf, der um 23:59 beginnt, muss seine Zeilen alle auf denselben Tag
#     schreiben, sonst zerfaellt eine Messung in zwei Messtermine.
#   * das Besuchsfenster laeuft mit. Es ist eine Aussage ueber DEN AUGENBLICK
#     DES ABRUFS, nicht ueber den Lauf.
# `jetzt` ist deshalb ab hier der BEGINN des Laufs und nichts weiter - die
# Zeit eines Abrufs kommt aus `uhr()`.


def _laufuhr(beginn: datetime) -> Callable[[], datetime]:
    """Die mitlaufende Uhr EINES Laufs: Beginn plus verstrichene Zeit.

    Nicht schlicht `datetime.now(timezone.utc)`, aus zwei Gruenden. Erstens
    muss der Aufrufer den Startpunkt einspeisen koennen - ein Test, der vom
    heutigen Datum abhinge, waere nach CLAUDE.md Regel 11 keiner. Zweitens
    kommt die verstrichene Zeit aus `time.monotonic()`: eine Systemuhr, die
    mitten im Lauf springt (NTP-Korrektur), verschoebe sonst das
    Besuchsfenster.
    """
    start = time.monotonic()
    return lambda: beginn + timedelta(seconds=time.monotonic() - start)


# Sicherheitsabstand zum Ende eines Besuchsfensters. Der Deckel greift so
# viele Sekunden VOR dem Fensterende, damit der letzte Abruf, der noch
# hineinpasst, auch drinnen fertig wird. Zehn Sekunden sind genau der
# Crawl-delay, den medimax.de und ep.de selbst verlangen - kuerzer kann der
# Abstand zum naechsten Abruf dort ohnehin nicht sein.
_FENSTER_PUFFER_SEKUNDEN = 10.0

# Was im Protokoll und in der Bilanz steht, wenn das ZEITBUDGET eines
# Anteils abgelaufen ist. Der zweite Grund - "Tuer zu" - braucht keine
# Konstante: sein Satz nennt das gemessene Fenster und entsteht deshalb erst
# an der Fundstelle (siehe unten, `frist_vom_fenster`). Unterschieden werden
# die beiden trotzdem nicht am Text, sondern am Flag `ausserhalb_besuchszeit`
# - der Abdeckungswaechter der Pipeline liest dieses Flag.
_FRIST_GRUND_BUDGET = "Zeitbudget des Geraetezweigs erschoepft"


def _fensterfrist(waechter: RobotsWaechter, url: str,
                  jetzt: datetime) -> Optional[float]:
    """Der monotone Zeitpunkt, zu dem das Besuchsfenster dieses Hosts zugeht.

    `None` heisst "dieser Host hat kein Fenster" - dann deckelt nichts. Ein
    bereits geschlossenes Fenster ergibt einen Zeitpunkt in der
    Vergangenheit; die Produktschleife bricht dann sofort ab, statt sich
    durch Dutzende Adressen zu arbeiten, die der Waechter ohnehin
    zurueckweist.
    """
    restzeit = waechter.restzeit_im_fenster(url, jetzt)
    if restzeit is None:
        return None
    return time.monotonic() + restzeit - _FENSTER_PUFFER_SEKUNDEN


class Abrufschleuse:
    """Das robots-Tor vor JEDEM Abruf gegen einen Anbieter.

    Eine Schleuse je Abruffolge. Sie haelt die zwei Dinge, die ein
    einzelner Aufruf nicht wissen kann: wann der letzte Abruf hinausging
    (fuer den Crawl-delay) und ob die Besuchszeit im Weg stand.

    ERST DIE WARTEZEIT RECHNEN, DANN DAS FENSTER PRUEFEN. Der Abruf geht
    nach dem Crawl-delay hinaus, nicht jetzt: bei zehn Sekunden Abstand
    ist der Unterschied klein, an der Kante eines Fensters entscheidet er
    darueber, ob wir die Tuer von innen oder von aussen sehen. Gewartet
    wird trotzdem erst NACH der Pruefung - eine abgelehnte Adresse soll
    keine Sekunde kosten.

    Der Abstand kommt je Adresse vom Waechter (`abstand()`, der groessere
    Wert aus Crawl-delay des Hosts und eigener Konfiguration). Je Adresse
    und nicht einmal je Anbieter, weil ein Anbieter Adressen auf mehreren
    Hosts hat (o2 und Vodafone lesen ihre Buendel ueber eine eigene
    Schnittstelle) - und die robots.txt des Zielhosts ist die, die gilt.
    Einen zusaetzlichen Abruf kostet das nicht: `darf()` holt die Regeln
    desselben Hosts ohnehin in denselben Cache.
    """

    def __init__(self, waechter: RobotsWaechter, uhr: Callable[[], datetime],
                 rate_limit_sekunden: float = 0.0):
        self._waechter = waechter
        self._uhr = uhr
        self._rate_limit = float(rate_limit_sekunden or 0.0)
        self._letzter_abruf = 0.0
        # Hat die BESUCHSZEIT einen Abruf verhindert (und nicht ein
        # Disallow oder eine unlesbare robots.txt)? Die Bilanz braucht
        # diesen Unterschied fuer den Abdeckungswaechter.
        self.ausserhalb_besuchszeit = False

    def passiere(self, url: str) -> None:
        """Laesst den Abruf durch - oder wirft `GeraeteAbrufFehler`.

        Kehrt erst zurueck, wenn der Crawl-delay abgewartet ist; der
        Aufrufer darf danach sofort abrufen.
        """
        abstand = self._waechter.abstand(url, self._rate_limit)
        noch_kein_abruf = self._letzter_abruf == 0.0
        warte = (0.0 if noch_kein_abruf else
                 max(0.0, abstand - (time.monotonic() - self._letzter_abruf)))
        zeitpunkt = self._uhr() + timedelta(seconds=warte)
        darf, grund = self._waechter.darf(url, zeitpunkt)
        if not darf:
            # Die Regeln liegen hier bereits im Cache des Waechters - der
            # Fenstertest kostet keinen zweiten Abruf.
            if not self._waechter.regeln(url).im_fenster(zeitpunkt):
                self.ausserhalb_besuchszeit = True
            raise GeraeteAbrufFehler(grund)
        if warte > 0:
            time.sleep(warte)
        self._letzter_abruf = time.monotonic()


def hole_mit_robots(hole: Callable, waechter: RobotsWaechter,
                    rate_limit_sekunden: float = 0.0,
                    uhr: Optional[Callable[[], datetime]] = None) -> Callable:
    """`hole` MIT robots-Pruefung - fuer Abrufe AUSSERHALB von `sammle()`.

    Die Nachbearbeitungs-Haken der Adapter (`loese_tarifnamen`,
    `ergaenze_buendel`) rufen nach der Sammelphase selbst ab. Bis zum
    22.09.2026 bekamen sie das rohe `hole` - ohne Disallow, ohne
    Crawl-delay, ohne Fensterpruefung, und das an der Stelle, an der der
    Lauf am weitesten fortgeschritten ist (die Zusage "JE ABRUF" oben im
    Modul und in `geraete.yml` galt damit fuer sie nicht). Sie gehen jetzt
    durch dieselbe `Abrufschleuse` wie die Sammelphase.

    Der Rueckgabewert hat den Vertrag von `hole` (`(status, text)`) und
    reicht jedes weitere Argument durch; eine verbotene Adresse wirft
    `GeraeteAbrufFehler` - die Haken fangen das je Adresse ab und lassen
    das Feld offen, statt zu raten.
    """
    schleuse = Abrufschleuse(waechter, uhr or (lambda: datetime.now(timezone.utc)),
                             rate_limit_sekunden)

    def gebremst(url: str, *args, **kwargs):
        schleuse.passiere(url)
        return hole(url, *args, **kwargs)

    return gebremst


def sammle_anbieter(anbieter, katalog: Katalog, farben: dict, hole: Callable,
                    heute: str, waechter: RobotsWaechter,
                    jetzt: Optional[datetime] = None,
                    frist_bis: Optional[float] = None,
                    uhr: Optional[Callable[[], datetime]] = None
                    ) -> Anbieterbilanz:
    """Einen Anbieter abarbeiten. Wirft nie - Fehler stehen in der Bilanz.

    `hole(url) -> (status, text)`. Der Status wird gebraucht und nicht
    weggeworfen: eine fehlende robots.txt (404) heisst "keine Regeln", eine
    verweigerte (403) heisst "nicht anfassen" - wer beides auf eine
    Ausnahme abbildet, verwechselt die zwei.

    `jetzt` ist der BEGINN des Laufs, nicht der Zeitpunkt eines Abrufs.
    `uhr()` liefert die Zeit des naechsten Abrufs; wer sie nicht mitgibt,
    bekommt `_laufuhr(jetzt)`. `sammle()` reicht EINE Uhr ueber alle
    Anbieter durch - eine je Anbieter neu gestellte Uhr faenge bei jedem
    wieder bei null an und waere derselbe eingefrorene Zeitstempel wie
    vorher, nur feiner verteilt.
    """
    bilanz = Anbieterbilanz(name=anbieter.name)
    if jetzt is None:
        jetzt = datetime.now(timezone.utc)
    if uhr is None:
        uhr = _laufuhr(jetzt)

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
    # Zusaetzliche Kopfzeilen werden NUR uebergeben, wenn der Anbieter welche
    # deklariert. Damit bleibt der Vertrag `hole(url)` fuer alle bestehenden
    # Aufrufer und jede vorhandene Testattrappe unveraendert gueltig - nur
    # die zwei Anbieter, die eine Schnittstelle mit Pflichtkopfzeile lesen
    # (o2s Medientyp, Vodafones oeffentlicher Browser-Schluessel), brauchen
    # eine Attrappe mit zweitem Parameter.
    kopfzeilen = dict(getattr(anbieter, "kopfzeilen", None) or {})
    # Derselbe Gedanke fuer den User-Agent (BRIEF_SATURN_ADAPTER_R2): NUR
    # wenn der Anbieter ihn ueberschreibt (Saturn), bekommt `hole()`
    # ueberhaupt ein drittes Argument - jede bestehende Testattrappe mit
    # `hole(url)` oder `hole(url, kopfzeilen=None)` bleibt gueltig.
    user_agent = (getattr(anbieter, "user_agent", "") or "").strip() or None

    # DER ROBOTS-ABRUF GEHOERT ZUM CRAWL DIESES ANBIETERS (B2,
    # 08.09.2026) - und tragt deshalb auch dessen Absender. Bis hier ging
    # er mit der globalen Kennung aus settings.yaml hinaus, obwohl der
    # Anbieter selbst unter seinem ehrlichen Namen anfragt; der T2-
    # Laufzeitbeleg hat genau das gemeldet (1 von 7 Requests mit Chrome-UA
    # auf robots.txt), und der Beleg existiert, um so etwas zu finden. Ein
    # Anbieter MIT Override bekommt deshalb eine eigene, provider-bezogene
    # Waechter-Sicht (einmalige robots.txt-Abfrage je Host, wie immer);
    # ohne Override bleibt es der geteilte Waechter mit der globalen
    # Kennung - die PM-Entscheidung zu settings.yaml steht weiter aus
    # (CLAUDE.md).
    if user_agent:
        waechter = RobotsWaechter(
            hole=lambda url: hole(url, user_agent=user_agent))

    leitadresse = anbieter.basis_url or anbieter.einstiege[0].url

    # DER ANTEIL EINES ANBIETERS ENDET SPAETESTENS MIT SEINEM FENSTER.
    # Ohne diesen Deckel bekaeme medimax.de um 07:55 noch die vollen
    # Minuten des Budgets zugeteilt und verbraechte sie ab 08:00 damit,
    # sich durch Adressen zu arbeiten, die der Waechter eine nach der
    # anderen zurueckweist - Zeit, die dem naechsten Anbieter fehlt.
    fensterfrist = _fensterfrist(waechter, leitadresse, uhr())
    frist_vom_fenster = (fensterfrist is not None
                         and (frist_bis is None or fensterfrist < frist_bis))
    if frist_vom_fenster:
        frist_bis = fensterfrist

    schleuse = Abrufschleuse(waechter, uhr, anbieter.rate_limit_sekunden)
    gruende: list[str] = []
    frist_erreicht = False

    def _hole(url: str) -> str:
        try:
            schleuse.passiere(url)
        except GeraeteAbrufFehler:
            # Die Schleuse weiss, WARUM sie zu war; die Bilanz traegt den
            # einen Unterschied weiter, auf den es dem Abdeckungswaechter
            # ankommt (Besuchszeit gegen alles andere).
            if schleuse.ausserhalb_besuchszeit:
                bilanz.ausserhalb_besuchszeit = True
            raise
        bilanz.besucht.append(url)
        kwargs = {}
        if kopfzeilen:
            kwargs["kopfzeilen"] = kopfzeilen
        if user_agent:
            kwargs["user_agent"] = user_agent
        status, text = hole(url, **kwargs) if kwargs else hole(url)
        if not (200 <= int(status) < 300):
            raise GeraeteAbrufFehler(f"HTTP {status}", status=int(status))
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
                roh = adapter.lies_buendel(inhalt, einstieg.url,
                                           proben=bilanz.proben) or []
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
        versucht_hier = 0
        tot_hier = 0
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
            versucht_hier += 1
            bilanz.produkte_versucht += 1
            try:
                seite = _hole(url)
            except GeraeteAbrufFehler as exc:
                if exc.status in _TOTE_STATUS:
                    # TOTE ADRESSE, kein Leseversuch: der Anbieter hat
                    # geantwortet, und seine Antwort ist "gibt es nicht".
                    # Gezaehlt und benannt, nicht als Ausfall gewertet -
                    # die Schwelle unten entscheidet, ob davon zu viele
                    # zusammenkommen.
                    tot_hier += 1
                    bilanz.tote_adressen.append(f"{url}: {exc}")
                    log.info("%s: %s tot (%s) - Adresse steht in der Quelle, "
                             "die Seite gibt es nicht mehr",
                             anbieter.name, url, exc)
                    continue
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
            if adapter.lies_buendel is not None \
                    and adapter.buendel_auf_produktseite:
                # ZWEITE LESART DERSELBEN SEITE (B1, Vodafone): dieselbe
                # Antwort, die `lies()` gerade in Listungen zerlegt hat,
                # traegt auch die Buendelpreise. Ein eigener `kind:
                # buendel`-Einstieg (wie bei o2) braucht nur, wer dafuer
                # eine EIGENE Adresse hat - hier ist es dieselbe. Adapter
                # MIT eigenen Buendel-Einstiegen schalten den Zusatzaufruf
                # ab (`buendel_auf_produktseite`, B3: congstar - seine
                # Produktseiten tragen keinen Plan, der Aufruf wuerde auf
                # jeder von ihnen werfen).
                try:
                    roh_buendel = adapter.lies_buendel(seite, url,
                                                       proben=bilanz.proben) or []
                except GeraeteAbrufFehler as exc:
                    log.info("%s: %s Buendel unlesbar (%s)",
                            anbieter.name, url, exc)
                else:
                    bilanz.buendel.extend(
                        _mit_sku(roh_buendel, anbieter, einstieg, katalog,
                                farben, heute, bilanz))
        if vollstaendig and not _einstieg_gelesen(versucht_hier, tot_hier):
            # Zu viele tote Adressen auf einmal. Das ist keine hinterher-
            # hinkende Sitemap mehr, sondern ein Umbau der Quelle - und der
            # darf nicht dazu fuehren, dass `mark_stale` ein halbes
            # Sortiment altert.
            vollstaendig = False
            gruende.append(
                f"{einstieg.url}: {tot_hier} von {versucht_hier} "
                f"Produktadressen tot, gelesen wurden weniger als "
                f"{round(_MINDESTANTEIL_GELESENER_PRODUKTSEITEN * 100)} %")
            log.warning("%s: %s - %d von %d Produktadressen tot, die Seite "
                        "gilt als unvollstaendig gelesen",
                        anbieter.name, einstieg.url, tot_hier, versucht_hier)
        if vollstaendig:
            bilanz.gelesene_einstiege.add(einstieg.url)

    if frist_erreicht:
        bilanz.status = "frist"
        if frist_vom_fenster:
            # NICHT "Budget alle": die Tuer ist zugegangen. Der Unterschied
            # ist keine Formulierung, sondern die Auskunft, die der
            # Abdeckungswaechter braucht - ein Anbieter ausserhalb seiner
            # Besuchszeit ist eine Luecke, kein Ausfall.
            bilanz.ausserhalb_besuchszeit = True
            fenster = waechter.regeln(leitadresse).fenster_text
            bilanz.grund = ("ausserhalb der Besuchszeit laut robots.txt "
                            f"({fenster})")
        else:
            bilanz.grund = _FRIST_GRUND_BUDGET
    elif bilanz.gelesene_einstiege:
        # BUENDEL ZAEHLEN MIT (B2, 08.09.2026): Bis hier sagte "leer" auch
        # einem Anbieter, der NUR Buendel geliefert hat - ein `kind:
        # buendel`-Einstieg erzeugt absichtlich keine Listungen, und seine
        # Saetze in `bilanz.buendel` waren fuer diesen Status unsichtbar.
        # "leer" heisst "nichts gefunden", und neun Buendel sind nicht
        # nichts. (`vollstaendig` gilt fuer "ok" und "leer" gleichermassen -
        # die Auslistungslogik ruehrt ein reiner Buendellieferant nicht an.)
        bilanz.status = ("ok" if (bilanz.listungen or bilanz.buendel)
                         else "leer")
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
    quellen: dict = {}
    for satz in rohsaetze:
        if satz.get("waehrung") and satz["waehrung"] not in ("EUR", ""):
            continue          # ein Preis in fremder Waehrung ist kein Vergleichswert
        listung = _als_listung_satz(satz, anbieter, einstieg, quelle_url,
                                    katalog, farben, heute, bilanz)
        if listung is not None:
            gelesen.append(listung)
            quellen[id(listung)] = satz.get("quelle") or ""
    for listung in _ohne_sammelknoten(gelesen):
        bilanz.listungen.append(listung)
        if listung.farbe_roh and listung.farbe_normalisiert is None:
            bilanz.unbekannte_farben.append(listung.farbe_roh)
            bilanz.unbekannt.append(
                {"art": "farbe", "wert": listung.farbe_roh,
                 "quelle": quellen.get(id(listung), "")})


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
        kwargs = dict(
            titel=satz.get("titel", ""), anbieter=anbieter.name,
            anbieter_typ=anbieter.typ, netz=anbieter.netz,
            quelle_url=urljoin(einstieg.url, satz.get("url") or "")
            or einstieg.url,
            abgerufen_am=heute, katalog=katalog, farben=farben,
            confidence=_belegstufe(satz.get("quelle")),
            farbe_roh=satz.get("farbe") or "",
            speicher_gb=satz.get("speicher_gb"),
            # Der ZUSTAND reist auch auf dem Buendelweg mit (B3, congstar:
            # `condition` als eigenes Feld). Vorher stand er nur im Titel
            # (o2, Telekom) oder in der Farbe - ein Anbieter, der ihn
            # strukturiert nennt, wurde darueber still als "neu" gelesen.
            # Rohsaetze ohne das Feld aendern nichts (`or ""`).
            zustand_hinweis=satz.get("zustand_hinweis") or "",
            einstieg_url=einstieg.url)
        listung = lies_listung(**kwargs)
        if listung is None and (satz.get("strukturierter_name") or "").strip():
            # E4-Auto-Erkennung, dieselbe Regel wie im Listungsweg: die
            # Buendel brauchen die sku_id desselben (neuen) Geraets - sonst
            # startete die Preishistorie auch hier erst beim zweiten Lauf.
            if autoerkennung.lege_an(satz["strukturierter_name"], katalog,
                                    heute,
                                    speicher_gb=satz.get("speicher_gb")) \
                    is not None:
                listung = lies_listung(**kwargs)
        if listung is None:
            titel = (satz.get("titel") or "").strip()
            if titel:
                bilanz.unbekannte_titel.append(titel)
                bilanz.unbekannt.append(
                    {"art": "titel", "wert": titel,
                     "quelle": satz.get("quelle") or ""})
            continue
        if listung.farbe_roh and listung.farbe_normalisiert is None:
            bilanz.unbekannte_farben.append(listung.farbe_roh)
            bilanz.unbekannt.append(
                {"art": "farbe", "wert": listung.farbe_roh,
                 "quelle": satz.get("quelle") or ""})
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
    kwargs = dict(
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
    listung = lies_listung(**kwargs)
    if listung is None and (satz.get("strukturierter_name") or "").strip():
        # E4-AUTO-ERKENNUNG: der Titel traf keinen Katalog-Eintrag, aber die
        # Quelle nennt ihren Namen strukturiert (Telekom `name`, o2
        # `description`, Vodafone `modelName`). ERST der Katalogabgleich,
        # DANN die Anlage - der Hand-Eintrag samt Alias schlaegt die Auto-
        # Anlage, und der Retry darunter trifft ihn. Ohne dieses Feld
        # passiert genau wie bisher nichts (Titel-Heuristik bleibt
        # verworfen).
        if autoerkennung.lege_an(satz["strukturierter_name"], katalog, heute,
                                speicher_gb=satz.get("speicher_gb")) is not None:
            listung = lies_listung(**kwargs)
    if listung is None:
        titel = (satz.get("titel") or "").strip()
        if titel:
            bilanz.unbekannte_titel.append(titel)
            bilanz.unbekannt.append(
                {"art": "titel", "wert": titel,
                 "quelle": satz.get("quelle") or ""})
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
           frist_sekunden: Optional[float] = None,
           uhr: Optional[Callable[[], datetime]] = None) -> dict:
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

    `jetzt` ist der Beginn des Laufs. Die daraus gestellte Uhr wird EINMAL
    gebaut und an jeden Anbieter durchgereicht: der vierte Anbieter soll
    sehen, dass seit dem Start eine halbe Stunde vergangen ist, und nicht
    wieder bei null anfangen.
    """
    if jetzt is None:
        jetzt = datetime.now(timezone.utc)
    if uhr is None:
        uhr = _laufuhr(jetzt)
    waechter = RobotsWaechter(hole=hole)
    frist_bis = (time.monotonic() + frist_sekunden) if frist_sekunden else None

    # `crawl_rang`, NICHT `rang` (P1/S2-4, 24.09.2026 - Befund Lauf 52/53):
    # `rang` ist die Anzeige-Reihenfolge auf der Seite und bleibt davon
    # unberuehrt. `crawl_rang` faellt ohne eigenen `sammelrang` auf `rang`
    # zurueck - fuer die meisten Anbieter aendert sich dadurch nichts.
    sortiert = sorted(quellen.anbieter, key=lambda a: (a.crawl_rang, a.name))
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
            eigene_frist, uhr=uhr))
    return {
        "anbieter": bilanzen,
        "listungen": [l for b in bilanzen for l in b.listungen],
        "abgefragt": sum(1 for b in bilanzen if b.status in ("ok", "leer", "frist")),
        "unbekannte_titel": sorted({t for b in bilanzen for t in b.unbekannte_titel}),
        # Unbekannte Titel und Farben MIT Anbieter und Feldquelle - die
        # Zeilen von data/state/geraete_unbekannt.jsonl (E4). Angelegt und
        # gezaehlt vom Lauf, nie von Hand gepflegt.
        "unbekannte": [{"anbieter": b.name, **e}
                       for b in bilanzen for e in b.unbekannt],
    }
