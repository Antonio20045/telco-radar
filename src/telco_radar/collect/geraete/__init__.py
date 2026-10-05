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
   Stunde spaeter davor - die Uhr laeuft mit (`laufuhr`), und der
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
from datetime import datetime, timedelta
from typing import Callable, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ...geraete_model import Katalog, lies_listung
from . import autoerkennung, register
from .basis import (
    ADAPTER,
    Adapter,
    GeraeteAbrufFehler,
    registriere,
)
from .basis import umgesetzte_methoden as umgesetzte_methoden
from .robots import RobotsWaechter
from .strukturdaten import ist_lockpreis, produkte_aus_html

log = logging.getLogger(__name__)

_LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.IGNORECASE)


@dataclass
class Anbieterbilanz:
    """Was ein Anbieter in diesem Lauf ergeben hat - und warum nicht mehr."""

    name: str
    status: str = "ok"
    grund: str = ""
    listungen: list = field(default_factory=list)
    buendel: list = field(default_factory=list)
    gelesene_einstiege: set = field(default_factory=set)
    seiten_versucht: int = 0
    produkte_abgerufen: int = 0
    unbekannte_titel: list = field(default_factory=list)
    unbekannte_farben: list = field(default_factory=list)
    unbekannt: list = field(default_factory=list)
    gedeckelt: list = field(default_factory=list)
    besucht: list = field(default_factory=list)
    nicht_verlinkt: list = field(default_factory=list)
    rohsaetze: int = 0
    proben: dict = field(default_factory=dict)
    tote_adressen: list = field(default_factory=list)
    produkte_versucht: int = 0
    ausserhalb_besuchszeit: bool = False

    @property
    def vollstaendig(self) -> bool:
        """Darf die Auslistungslogik fuer diesen Anbieter ueberhaupt laufen?

        Gefragt ist der EINSTIEG, nicht jede einzelne Produktadresse: was
        als gelesener Einstieg zaehlt, entscheidet `_einstieg_gelesen()`.
        """
        return self.status in ("ok", "leer") and bool(self.gelesene_einstiege)


_TOTE_STATUS = (404, 410)

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


def ernte_links(
    inhalt: str, basis_url: str, pfadmuster="", kind: str = "static"
) -> list[str]:
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
    muster = (
        [pfadmuster]
        if isinstance(pfadmuster, str)
        else [str(m) for m in (pfadmuster or [])]
    )
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
            continue
        if muster and not all(m in url for m in muster):
            continue
        url = url.split("#", 1)[0]
        if url.rstrip("/") == (basis_url or "").rstrip("/"):
            continue
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
    for produkt in daten.get("products") or []:
        titel = str(produkt.get("title") or "").strip()
        handle = str(produkt.get("handle") or "").strip()
        for variante in produkt.get("variants") or []:
            preis = lies_preis(variante.get("price"))
            bezeichnung = str(variante.get("title") or "").strip()
            voller_titel = (
                titel
                if bezeichnung in ("", "Default Title")
                else f"{titel} {bezeichnung}"
            )
            out.append(
                {
                    "titel": voller_titel,
                    "preis": preis,
                    "waehrung": "EUR",
                    "verfuegbarkeit": "lieferbar"
                    if variante.get("available")
                    else "ausverkauft",
                    "sku": str(variante.get("sku") or "").strip(),
                    "ean": str(variante.get("barcode") or "").strip(),
                    "farbe": "",
                    "url": f"/products/{handle}" if handle else "",
                    "quelle": "shopify",
                }
            )
    return out


registriere(
    "ldjson", Adapter(name="ldjson", lies=lambda text, url="": produkte_aus_html(text))
)
registriere(
    "shopify",
    Adapter(
        name="shopify",
        lies=lambda text, url="": produkte_aus_shopify(text),
        direkt=True,
    ),
)


register.registriere_anbieter_adapter()


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
        return {
            "preis_ohne_vertrag": None,
            "zuzahlung": float(zuzahlung),
            "tarif_referenz": tarif,
            "preis_mit_vertrag_ab": monatspreis,
        }
    if monatspreis is not None and tarif:
        return {
            "preis_ohne_vertrag": None,
            "preis_mit_vertrag_ab": float(monatspreis),
            "tarif_referenz": tarif,
            "laufzeit_monate": satz.get("laufzeit_monate"),
        }
    if preis is None or ist_lockpreis(preis):
        return {"preis_ohne_vertrag": None}
    return {
        "preis_ohne_vertrag": preis,
        "anzahlung": satz.get("anzahlung"),
        "monatsrate": satz.get("monatsrate"),
        "laufzeit_monate": satz.get("laufzeit_monate"),
        "zins_effektiv": satz.get("zins_effektiv"),
    }


def laufuhr(beginn: datetime) -> Callable[[], datetime]:
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


_FENSTER_PUFFER_SEKUNDEN = 10.0

_FRIST_GRUND_BUDGET = "Zeitbudget des Geraetezweigs erschoepft"


def _fensterfrist(
    waechter: RobotsWaechter, url: str, jetzt: datetime
) -> Optional[float]:
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

    def __init__(
        self,
        waechter: RobotsWaechter,
        uhr: Callable[[], datetime],
        rate_limit_sekunden: float = 0.0,
    ):
        self._waechter = waechter
        self._uhr = uhr
        self._rate_limit = float(rate_limit_sekunden or 0.0)
        self._letzter_abruf = 0.0
        self.ausserhalb_besuchszeit = False

    def passiere(self, url: str) -> None:
        """Laesst den Abruf durch - oder wirft `GeraeteAbrufFehler`.

        Kehrt erst zurueck, wenn der Crawl-delay abgewartet ist; der
        Aufrufer darf danach sofort abrufen.
        """
        abstand = self._waechter.abstand(url, self._rate_limit)
        noch_kein_abruf = self._letzter_abruf == 0.0
        warte = (
            0.0
            if noch_kein_abruf
            else max(0.0, abstand - (time.monotonic() - self._letzter_abruf))
        )
        zeitpunkt = self._uhr() + timedelta(seconds=warte)
        darf, grund = self._waechter.darf(url, zeitpunkt)
        if not darf:
            if not self._waechter.regeln(url).im_fenster(zeitpunkt):
                self.ausserhalb_besuchszeit = True
            raise GeraeteAbrufFehler(grund)
        if warte > 0:
            time.sleep(warte)
        self._letzter_abruf = time.monotonic()


def hole_mit_robots(
    hole: Callable,
    waechter: RobotsWaechter,
    rate_limit_sekunden: float,
    uhr: Callable[[], datetime],
) -> Callable:
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
    schleuse = Abrufschleuse(waechter, uhr, rate_limit_sekunden)

    def gebremst(url: str, *args, **kwargs):
        schleuse.passiere(url)
        return hole(url, *args, **kwargs)

    return gebremst


def sammle_anbieter(
    anbieter,
    katalog: Katalog,
    farben: dict,
    hole: Callable,
    heute: str,
    waechter: RobotsWaechter,
    jetzt: datetime,
    frist_bis: Optional[float] = None,
    uhr: Optional[Callable[[], datetime]] = None,
) -> Anbieterbilanz:
    """Einen Anbieter abarbeiten. Wirft nie - Fehler stehen in der Bilanz.

    `hole(url) -> (status, text)`. Der Status wird gebraucht und nicht
    weggeworfen: eine fehlende robots.txt (404) heisst "keine Regeln", eine
    verweigerte (403) heisst "nicht anfassen" - wer beides auf eine
    Ausnahme abbildet, verwechselt die zwei.

    `jetzt` ist der BEGINN des Laufs, nicht der Zeitpunkt eines Abrufs.
    `uhr()` liefert die Zeit des naechsten Abrufs; wer sie nicht mitgibt,
    bekommt `laufuhr(jetzt)`. `sammle()` reicht EINE Uhr ueber alle
    Anbieter durch - eine je Anbieter neu gestellte Uhr faenge bei jedem
    wieder bei null an und waere derselbe eingefrorene Zeitstempel wie
    vorher, nur feiner verteilt.
    """
    bilanz = Anbieterbilanz(name=anbieter.name)
    if uhr is None:
        uhr = laufuhr(jetzt)

    if not anbieter.crawlbar:
        bilanz.status = "uebersprungen"
        bilanz.grund = anbieter.grund or "nicht crawlbar"
        return bilanz
    adapter = ADAPTER.get(anbieter.methode)
    if adapter is None:
        bilanz.status = "nicht_umgesetzt"
        bilanz.grund = anbieter.grund or (
            f"Beschaffungsmethode {anbieter.methode!r} ist gemessen, aber noch "
            f"nicht als Adapter gebaut"
        )
        return bilanz

    erlaubt: set[str] = set()
    kopfzeilen = dict(getattr(anbieter, "kopfzeilen", None) or {})
    user_agent = (getattr(anbieter, "user_agent", "") or "").strip() or None

    if user_agent:
        waechter = RobotsWaechter(hole=lambda url: hole(url, user_agent=user_agent))

    leitadresse = anbieter.basis_url or anbieter.einstiege[0].url

    fensterfrist = _fensterfrist(waechter, leitadresse, uhr())
    frist_vom_fenster = fensterfrist is not None and (
        frist_bis is None or fensterfrist < frist_bis
    )
    if frist_vom_fenster:
        frist_bis = fensterfrist

    schleuse = Abrufschleuse(waechter, uhr, anbieter.rate_limit_sekunden)
    gruende: list[str] = []
    frist_erreicht = False
    buendel_unlesbar = 0

    def _hole(url: str) -> str:
        try:
            schleuse.passiere(url)
        except GeraeteAbrufFehler:
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
        except Exception as exc:  # noqa: BLE001
            gruende.append(f"{einstieg.url}: {type(exc).__name__}: {str(exc)[:120]}")
            continue

        if einstieg.kind == "buendel":
            if adapter.lies_buendel is None:
                gruende.append(
                    f"{einstieg.url}: die Methode "
                    f"{anbieter.methode!r} kennt keine "
                    f"Buendellesart"
                )
                continue
            try:
                roh = (
                    adapter.lies_buendel(inhalt, einstieg.url, proben=bilanz.proben)
                    or []
                )
                gemappt = _mit_sku(
                    roh, anbieter, einstieg, katalog, farben, heute, bilanz
                )
                if adapter.vertiefe_buendel is not None and gemappt:
                    gemappt = _vertiefe(
                        adapter,
                        anbieter,
                        einstieg,
                        gemappt,
                        _hole,
                        frist_bis,
                        katalog,
                        farben,
                        heute,
                        bilanz,
                    )
                bilanz.buendel.extend(gemappt)
            except GeraeteAbrufFehler as exc:
                gruende.append(f"{einstieg.url}: {exc}")
                log.warning("%s: Buendelkatalog nicht lesbar (%s)", anbieter.name, exc)
                continue
            bilanz.gelesene_einstiege.add(einstieg.url)
            continue

        direkt = ADAPTER["shopify"] if einstieg.kind == "shopify" else adapter
        if direkt.direkt:
            try:
                roh = direkt.lies(inhalt, einstieg.url)
            except GeraeteAbrufFehler as exc:
                gruende.append(f"{einstieg.url}: {exc}")
                continue
            _uebernimm(
                roh, anbieter, einstieg, einstieg.url, katalog, farben, heute, bilanz
            )
            bilanz.gelesene_einstiege.add(einstieg.url)
            continue

        if adapter.ernte is not None:
            links = adapter.ernte(
                inhalt, einstieg.url, einstieg.pfadmuster, einstieg.kind
            )
        else:
            links = ernte_links(
                inhalt, einstieg.url, einstieg.pfadmuster, einstieg.kind
            )
        ohne = getattr(einstieg, "ohne_pfadmuster", ()) or ()
        if ohne:
            behalten = [a for a in links if not any(m in a for m in ohne)]
            if len(behalten) < len(links):
                log.info(
                    "%s: %d Adressen von %s ausgeschlossen (ohne_pfadmuster)",
                    anbieter.name,
                    len(links) - len(behalten),
                    einstieg.url,
                )
            links = behalten
        erlaubt.update(links)
        vollstaendig = True
        versucht_hier = 0
        tot_hier = 0
        if len(links) > anbieter.max_produkte:
            vollstaendig = False
            bilanz.gedeckelt.append(
                f"{einstieg.url}: {len(links)} Adressen, {anbieter.max_produkte} abgerufen"
            )
            log.warning(
                "%s: %s liefert %d Adressen, Deckel steht bei %d - "
                "die Seite gilt als unvollstaendig gelesen",
                anbieter.name,
                einstieg.url,
                len(links),
                anbieter.max_produkte,
            )
        for url in links[: anbieter.max_produkte]:
            if frist_bis is not None and time.monotonic() > frist_bis:
                frist_erreicht = True
                vollstaendig = False
                break
            versucht_hier += 1
            bilanz.produkte_versucht += 1
            try:
                seite = _hole(url)
            except GeraeteAbrufFehler as exc:
                if exc.status in _TOTE_STATUS:
                    tot_hier += 1
                    bilanz.tote_adressen.append(f"{url}: {exc}")
                    log.info(
                        "%s: %s tot (%s) - Adresse steht in der Quelle, "
                        "die Seite gibt es nicht mehr",
                        anbieter.name,
                        url,
                        exc,
                    )
                    continue
                log.info("%s: %s uebersprungen (%s)", anbieter.name, url, exc)
                vollstaendig = False
                continue
            except Exception as exc:  # noqa: BLE001
                log.warning("%s: %s nicht abrufbar (%s)", anbieter.name, url, exc)
                vollstaendig = False
                continue
            bilanz.produkte_abgerufen += 1
            try:
                roh = adapter.lies(seite, url)
            except GeraeteAbrufFehler as exc:
                log.info("%s: %s unlesbar (%s)", anbieter.name, url, exc)
                vollstaendig = False
                continue
            _uebernimm(roh, anbieter, einstieg, url, katalog, farben, heute, bilanz)
            if adapter.lies_buendel is not None and adapter.buendel_auf_produktseite:
                try:
                    roh_buendel = (
                        adapter.lies_buendel(seite, url, proben=bilanz.proben) or []
                    )
                except GeraeteAbrufFehler as exc:
                    log.warning("%s: %s Buendel unlesbar (%s)", anbieter.name, url, exc)
                    buendel_unlesbar += 1
                else:
                    bilanz.buendel.extend(
                        _mit_sku(
                            roh_buendel,
                            anbieter,
                            einstieg,
                            katalog,
                            farben,
                            heute,
                            bilanz,
                        )
                    )
        if vollstaendig and not _einstieg_gelesen(versucht_hier, tot_hier):
            vollstaendig = False
            gruende.append(
                f"{einstieg.url}: {tot_hier} von {versucht_hier} "
                f"Produktadressen tot, gelesen wurden weniger als "
                f"{round(_MINDESTANTEIL_GELESENER_PRODUKTSEITEN * 100)} %"
            )
            log.warning(
                "%s: %s - %d von %d Produktadressen tot, die Seite "
                "gilt als unvollstaendig gelesen",
                anbieter.name,
                einstieg.url,
                tot_hier,
                versucht_hier,
            )
        if vollstaendig:
            bilanz.gelesene_einstiege.add(einstieg.url)

    if buendel_unlesbar:
        bilanz.gedeckelt.append(
            f"{buendel_unlesbar} Produktseiten ohne lesbare Buendel"
        )

    if frist_erreicht:
        bilanz.status = "frist"
        if frist_vom_fenster:
            bilanz.ausserhalb_besuchszeit = True
            fenster = waechter.regeln(leitadresse).fenster_text
            bilanz.grund = f"ausserhalb der Besuchszeit laut robots.txt ({fenster})"
        else:
            bilanz.grund = _FRIST_GRUND_BUDGET
    elif bilanz.gelesene_einstiege:
        bilanz.status = "ok" if (bilanz.listungen or bilanz.buendel) else "leer"
        bilanz.grund = "; ".join(gruende)[:300]
    else:
        bilanz.status = "fehler"
        teile = gruende + bilanz.gedeckelt
        if not teile and (bilanz.produkte_abgerufen or bilanz.listungen):
            teile = [
                f"Einstieg gelesen, aber unvollstaendig ausgewertet: "
                f"{bilanz.produkte_abgerufen} Produktseiten abgerufen, "
                f"{len(bilanz.listungen)} Listungen"
            ]
        bilanz.grund = "; ".join(teile)[:300] or "kein Einstieg lesbar"
    bilanz.nicht_verlinkt = sorted(set(bilanz.besucht) - erlaubt)
    return bilanz


def _uebernimm(
    rohsaetze,
    anbieter,
    einstieg,
    quelle_url: str,
    katalog: Katalog,
    farben: dict,
    heute: str,
    bilanz: Anbieterbilanz,
) -> None:
    bilanz.rohsaetze += len(rohsaetze or [])
    gelesen = []
    quellen: dict = {}
    for satz in rohsaetze:
        if satz.get("waehrung") and satz["waehrung"] not in ("EUR", ""):
            continue
        listung = _als_listung_satz(
            satz, anbieter, einstieg, quelle_url, katalog, farben, heute, bilanz
        )
        if listung is not None:
            gelesen.append(listung)
            quellen[id(listung)] = satz.get("quelle") or ""
    for listung in _ohne_sammelknoten(gelesen):
        bilanz.listungen.append(listung)
        if listung.farbe_roh and listung.farbe_normalisiert is None:
            bilanz.unbekannte_farben.append(listung.farbe_roh)
            bilanz.unbekannt.append(
                {
                    "art": "farbe",
                    "wert": listung.farbe_roh,
                    "quelle": quellen.get(id(listung), ""),
                }
            )


def _vertiefe(
    adapter,
    anbieter,
    einstieg,
    gemappt: list,
    hole_text: Callable,
    frist_bis: Optional[float],
    katalog: Katalog,
    farben: dict,
    heute: str,
    bilanz: Anbieterbilanz,
) -> list:
    """Die Vertiefung eines Buendel-Einstiegs (siehe `Adapter`).

    Wirft nie: was die Vertiefung nicht schafft, fehlt als Zusatz, die
    Katalogsaetze bleiben. Ein Abbruch an der Frist steht in
    `bilanz.gedeckelt` und im Protokoll - er ist eine benannte Luecke, kein
    stiller Rest.
    """
    zaehler: dict = {}

    def weiter() -> bool:
        return frist_bis is None or time.monotonic() <= frist_bis

    try:
        tief = adapter.vertiefe_buendel(hole_text, gemappt, weiter, zaehler) or []
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "%s: Buendel-Vertiefung gescheitert (%s: %s)",
            anbieter.name,
            type(exc).__name__,
            str(exc)[:160],
        )
        bilanz.gedeckelt.append(
            f"{einstieg.url}: Buendel-Vertiefung gescheitert ({type(exc).__name__})"
        )
        return gemappt
    tief_gemappt = _mit_sku(tief, anbieter, einstieg, katalog, farben, heute, bilanz)
    zusammen = (
        adapter.fuehre_zusammen(gemappt, tief_gemappt)
        if adapter.fuehre_zusammen
        else gemappt + tief_gemappt
    )
    log.info(
        "%s: Buendel-Vertiefung %d Geraete, %d Abrufe, %d gemessen, "
        "%d abgeleitet, %d Rohsaetze (%d mit Geraet), zusammen %d "
        "(Zaehler %s)",
        anbieter.name,
        zaehler.get("geraete", 0),
        zaehler.get("abrufe", 0),
        zaehler.get("gemessen", 0),
        zaehler.get("abgeleitet", 0),
        len(tief),
        len(tief_gemappt),
        len(zusammen),
        dict(sorted(zaehler.items())),
    )
    if zaehler.get("frist"):
        bilanz.gedeckelt.append(
            f"{einstieg.url}: Buendel-Vertiefung an der Frist beendet "
            f"({zaehler.get('geraete', 0)} Geraete vertieft)"
        )
        log.warning(
            "%s: Buendel-Vertiefung an der Frist beendet - %d Geraete vertieft",
            anbieter.name,
            zaehler.get("geraete", 0),
        )
    return zusammen


def _mit_sku(
    rohsaetze,
    anbieter,
    einstieg,
    katalog: Katalog,
    farben: dict,
    heute: str,
    bilanz: Anbieterbilanz,
) -> list[dict]:
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
            titel=satz.get("titel", ""),
            anbieter=anbieter.name,
            anbieter_typ=anbieter.typ,
            netz=anbieter.netz,
            quelle_url=urljoin(einstieg.url, satz.get("url") or "") or einstieg.url,
            abgerufen_am=heute,
            katalog=katalog,
            farben=farben,
            confidence=_belegstufe(satz.get("quelle")),
            farbe_roh=satz.get("farbe") or "",
            speicher_gb=satz.get("speicher_gb"),
            zustand_hinweis=satz.get("zustand_hinweis") or "",
            einstieg_url=einstieg.url,
        )
        listung = lies_listung(**kwargs)
        if listung is None and (satz.get("strukturierter_name") or "").strip():
            if (
                autoerkennung.lege_an(
                    satz["strukturierter_name"],
                    katalog,
                    heute,
                    speicher_gb=satz.get("speicher_gb"),
                )
                is not None
            ):
                listung = lies_listung(**kwargs)
        if listung is None:
            titel = (satz.get("titel") or "").strip()
            if titel:
                bilanz.unbekannte_titel.append(titel)
                bilanz.unbekannt.append(
                    {"art": "titel", "wert": titel, "quelle": satz.get("quelle") or ""}
                )
            continue
        if listung.farbe_roh and listung.farbe_normalisiert is None:
            bilanz.unbekannte_farben.append(listung.farbe_roh)
            bilanz.unbekannt.append(
                {
                    "art": "farbe",
                    "wert": listung.farbe_roh,
                    "quelle": satz.get("quelle") or "",
                }
            )
        out.append(
            {
                **satz,
                "sku_id": listung.sku_id,
                "anbieter": anbieter.name,
                "zustand": listung.zustand,
                "quelle_url": listung.quelle_url,
            }
        )
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
    return [
        l
        for l in listungen
        if l.speicher_gb is not None or l.device_id not in mit_speicher
    ]


def _belegstufe(quelle: str) -> str:
    """Wie gut ein Satz belegt ist - nachgeschlagen, nicht aufgezaehlt."""
    for adapter in ADAPTER.values():
        if adapter.name == quelle:
            return adapter.confidence
    return "hoch" if quelle in ("ldjson", "shopify", "microdata") else "mittel"


def _als_listung_satz(
    satz, anbieter, einstieg, quelle_url, katalog, farben, heute, bilanz
):
    kwargs = dict(
        titel=satz.get("titel", ""),
        anbieter=anbieter.name,
        anbieter_typ=anbieter.typ,
        netz=anbieter.netz,
        quelle_url=urljoin(quelle_url, satz.get("url") or "") or quelle_url,
        abgerufen_am=heute,
        katalog=katalog,
        farben=farben,
        verfuegbarkeit=satz.get("verfuegbarkeit") or "unbekannt",
        confidence=_belegstufe(satz.get("quelle")),
        farbe_roh=satz.get("farbe") or "",
        ean=satz.get("ean") or "",
        zustand_hinweis=satz.get("zustand_hinweis") or "",
        speicher_gb=satz.get("speicher_gb"),
        einstieg_url=einstieg.url,
        **_preisfelder(anbieter, satz),
    )
    listung = lies_listung(**kwargs)
    if listung is None and (satz.get("strukturierter_name") or "").strip():
        if (
            autoerkennung.lege_an(
                satz["strukturierter_name"],
                katalog,
                heute,
                speicher_gb=satz.get("speicher_gb"),
            )
            is not None
        ):
            listung = lies_listung(**kwargs)
    if listung is None:
        titel = (satz.get("titel") or "").strip()
        if titel:
            bilanz.unbekannte_titel.append(titel)
            bilanz.unbekannt.append(
                {"art": "titel", "wert": titel, "quelle": satz.get("quelle") or ""}
            )
    return listung


_MINDEST_JE_ANBIETER = 120.0


def sammle(
    quellen,
    katalog: Katalog,
    farben: dict,
    hole: Callable,
    heute: str,
    jetzt: datetime,
    frist_sekunden: Optional[float] = None,
    uhr: Optional[Callable[[], datetime]] = None,
) -> dict:
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
    if uhr is None:
        uhr = laufuhr(jetzt)
    waechter = RobotsWaechter(hole=hole)
    frist_bis = (time.monotonic() + frist_sekunden) if frist_sekunden else None

    sortiert = sorted(quellen.anbieter, key=lambda a: (a.crawl_rang, a.name))
    crawlt = [
        a.name for a in sortiert if a.crawlbar and ADAPTER.get(a.methode) is not None
    ]

    bilanzen = []
    for anbieter in sortiert:
        eigene_frist = frist_bis
        if frist_bis is not None and anbieter.name in crawlt:
            nach_mir = len(crawlt) - crawlt.index(anbieter.name) - 1
            rest = frist_bis - time.monotonic()
            eigene_frist = min(
                frist_bis,
                time.monotonic()
                + max(_MINDEST_JE_ANBIETER, rest - nach_mir * _MINDEST_JE_ANBIETER),
            )
        bilanzen.append(
            sammle_anbieter(
                anbieter,
                katalog,
                farben,
                hole,
                heute,
                waechter,
                jetzt,
                eigene_frist,
                uhr=uhr,
            )
        )
    return {
        "anbieter": bilanzen,
        "listungen": [l for b in bilanzen for l in b.listungen],
        "abgefragt": sum(1 for b in bilanzen if b.status in ("ok", "leer", "frist")),
        "unbekannte_titel": sorted({t for b in bilanzen for t in b.unbekannte_titel}),
        "unbekannte": [
            {"anbieter": b.name, **e} for b in bilanzen for e in b.unbekannt
        ],
    }
