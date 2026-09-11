"""Die Hauptansicht der Geraeteseite: je Modell eine Karte pro Anbieter.

Die eine Frage, an der diese Tafel gebaut ist
--------------------------------------------
    "iPhone 17 Pro mit Tarif X bei Anbieter Y - was zahlt der Kunde
     ueber 24 Monate gesamt?"

Alles auf dieser Tafel beantwortet sie oder sagt, warum es sie nicht
beantworten kann. Der Barpreis ist dabei ein BAUSTEIN und keine
konkurrierende Hauptspalte (A4): er steht in der Aufschluesselung und in
der Effektivpreiszeile, nicht als zweite Leitzahl daneben.

Vier Anbieter, immer vier Zeilen
--------------------------------
Telekom, 1&1, o2 und Vodafone stehen JE MODELL da - mit einer Zahl oder
mit einem benannten Leerzustand (B.2.5). Ein Anbieter, der weggelassen
wird, weil zu ihm nichts erhoben ist, sieht auf der Seite aus wie ein
Anbieter, den es nicht gibt. Genau das ist E1: Vertrauen vor
Vollstaendigkeit.

Die Vodafone-Referenz ist GERECHNET und sagt es
-----------------------------------------------
Vodafone verkauft im erhobenen Bestand kein Buendel - 151 Listungen, alle
mit Barpreis, keine mit Tarifbezug. Ohne eine Vergleichszahl haette die
Tafel keine Referenzlinie, und das Euro-Delta aus B.2 waere unerfuellbar.
C.1 laesst dafuer ausdruecklich eine "gekennzeichnete Naeherung" zu, und
genau das ist die Referenz hier:

    Tarifgrundpreis aus dem Produktinformationsblatt (phasengewichtet)
  + Barpreis desselben Geraets bei Vodafone
  = was ein Kunde bei uns fuer dieselbe Laufzeit zahlt

**Beide Summanden sind gemessen; gerechnet ist nur ihre Summe, und die
Karte sagt das in ihrem eigenen Satz.** Sie traegt deshalb `naeherung:
True`, ein eigenes Etikett und niemals die Beschriftung eines Angebots.

Was hier NICHT passiert
-----------------------
Kein Barpreis wird aus einer Rate geschaetzt, kein Bundle-Monatspreis in
Tarif und Geraet zerlegt (§ 13.2: 1&1 nennt EINEN Betrag, seine Aufteilung
waere unsere Erfindung), und keine Zahl wird ueber Laufzeiten hinweg
verglichen ausser `Ø/Monat` (A5.3).
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from . import geraete_vergleich
from .effektivpreis import phasensumme
from .geraete_tco_grafik import anbieter_slug
from .geraete_verlauf import messtage
from ..geraete_model import VERGLEICHBARE_ZUSTAENDE, ZUSTAENDE, normalisiere
from ..tarif_model import Preisphase
from ..tco_model import (POSTEN_ANSCHLUSS, POSTEN_BUENDEL, POSTEN_RATE,
                         POSTEN_TARIF, POSTEN_ZUZAHLUNG, TCO_HORIZONT,
                         Buendel, tco_24)

# Ticket TCO24-1 (08.09.2026): die Leitzahl der Seite ist IMMER TCO-24
# (AUFTRAG_GERAETESEITE.md §3 - "Immer 24 Monate", verbindlich). Bis dahin
# fuehrte diese Tafel `tco_bindung()` - eine Kennzahl ueber die eigene
# Bindung des Buendels (24 ODER 36 Monate), sichtbar als "TCO-36". Das war
# der deklarierte Fehler: 324 sichtbare "TCO-36" auf der Live-Seite, gegen
# eine Norm, die genau das ausschliesst. Ersetzt durch `tco_24()` - dieselbe
# Bibliotheksfunktion, die `test_tco_model.py` seit E2 (03.09.2026) haelt.
# Raten jenseits 24 Monate stehen als `Tco.restbetrag` daneben, nie in der
# Leitzahl.

# Die Laufzeit, mit der JEDE Karte und die Referenz rechnen - keine
# Variable mehr, seit die Norm "Immer 24 Monate" sagt.
LAUFZEIT = TCO_HORIZONT
LABEL = f"TCO-{TCO_HORIZONT}"
# "ab Monat 25" - der erste Monat NACH dem festen Horizont. F5, Katalog D.
AB_MONAT = TCO_HORIZONT + 1

log = logging.getLogger(__name__)

# Die vier Anbieter der Vision (A2), in der Reihenfolge, in der sie auf
# jeder Karte stehen. congstar laeuft als Telekom-Netz-Zweitmarke mit,
# bekommt aber nur eine Karte, wenn es wirklich ein Buendel liefert - eine
# leere Zeile fuer jede denkbare Zweitmarke waere eine Wand aus Luecken.
ANBIETER_REIHENFOLGE = ("Telekom", "1&1", "o2", "Vodafone")

EIGEN = "vodafone"

# Das Geraet der Leitfrage aus dem Lastenheft (Abschnitt A). Es ist die
# Vorgabe des Auswahlfeldes, solange es mit zwei Anbietern rechenbar ist.
LEITFRAGE_MODELL = "apple-iphone-17-pro-256"

# Warum ein Anbieter heute keine Zahl hat. Der Satz steht auf der Karte,
# nicht in einem Protokoll - eine Luecke ohne Begruendung sieht aus wie ein
# Fehler der Seite.
#
# S-Q1 (Review vom 05.09.2026): der Telekom-Satz nannte woertlich "GitHub
# Actions", "202-Challenge" und "Phase T" - Begriffe aus der Werkstatt, die
# ein Manager ohne Technikhintergrund nicht liest. Die TECHNISCHE Ursache
# steht weiterhin in `config/geraete_quellen.yaml` (dort ist sie am Platz -
# wer Quellen pflegt, braucht sie), hier steht nur noch, was es fuer die
# Zahl bedeutet: sie fehlt heute und kommt mit der naechsten Messung.
LEER_GRUND = {
    "Telekom": ("Für dieses Modell ist bei Telekom noch kein Bündelpreis "
                "erhoben – die Vergleichszahl folgt mit der nächsten "
                "wöchentlichen Messung."),
    "1&1": ("Für dieses Modell ist bei 1&1 kein Bündel erhoben – die "
            "Kategorieseite führt es nicht als eigene Produktkachel."),
    "o2": "Für dieses Modell ist bei o2 kein Bündel erhoben.",
    "Vodafone": ("Kein Bündelpreis erhoben, und kein Barpreis dieses "
                 "Geräts – ohne beides gibt es keine Vergleichszahl."),
}

# Der Zustand, ueber den ueberhaupt verglichen wird. Ein refurbished Geraet
# ist ein anderes Produkt und kein guenstigeres Angebot - dieselbe Regel und
# dieselbe Konstante wie im Barpreisvergleich.
_ZUSTAND = VERGLEICHBARE_ZUSTAENDE

# Was auf der Karte steht, wenn das Geraet kein Neugeraet ist - oder wenn
# niemand belegt hat, was es ist. "erneuert" ist das Wort, das o2 selbst
# benutzt; "Zustand nicht belegt" ist ehrlicher als ein stilles "neu".
ZUSTAND_ETIKETT = {"neu": "", "refurbished": "erneuert", "b-ware": "B-Ware",
                   "unbekannt": "Zustand nicht belegt"}


def zustand_des_buendels(b: Buendel, zustand_je_listung: dict) -> str:
    """Der Geraetezustand eines Buendels - belegt oder `unbekannt`.

    Drei Quellen, in dieser Reihenfolge: das Feld am Buendel (seit dem
    04.09.2026 vom Sammler geschrieben), die Listung DERSELBEN SKU beim
    selben Anbieter (`geraete_db.json` traegt `zustand` an jeder Listung),
    und die Zustandsstrecke der SKU selbst (`sku_id(..., zustand)` haengt
    `-refurbished` an - dieselbe Erkennung, nur als Suffix). Was keine der
    drei belegt, ist `unbekannt`. NIE `neu`: ein fehlender Beleg ist kein
    Neugeraet, und genau diese Annahme hat zehn erneuerte o2-Geraete als
    Sieger gegen Neugeraete gefuehrt (QA-Befund B1, PM-Entscheidung H5).
    """
    zustand = (b.zustand or "").strip().lower()
    if zustand in ZUSTAENDE:
        return zustand
    zustand = zustand_je_listung.get((normalisiere(b.anbieter), b.sku_id), "")
    if zustand in ZUSTAENDE:
        return zustand
    for kandidat in ZUSTAENDE:
        if kandidat in _ZUSTAND:
            continue          # ein fehlendes Suffix belegt kein Neugeraet
        if b.sku_id.endswith("-" + normalisiere(kandidat)):
            return kandidat
    return "unbekannt"


def _zustand_je_listung(listungen: list) -> dict:
    """(Anbieter, sku_id) -> Zustand, aus dem Geraetebestand."""
    out: dict = {}
    for e in listungen:
        sku = e.get("sku_id") or ""
        zustand = (e.get("zustand") or "").strip().lower()
        if sku and zustand in ZUSTAENDE:
            out.setdefault((normalisiere(e.get("anbieter", "")), sku), zustand)
    return out


def _eigen(anbieter: str) -> bool:
    return normalisiere(anbieter) == EIGEN


def modell_schluessel(device_id: str, speicher) -> str:
    """`apple-iphone-17-pro-256` - Geraet UND Speicherstufe.

    Der Speicher gehoert in den Schluessel: 256 GB und 512 GB sind zwei
    Preise, und eine Karte, die beide unter einem Namen fuehrt, vergleicht
    zwei Geraete. Die Farbe gehoert NICHT hinein - sie ist keine
    Preisdimension (Befund vom 11.08.2026).
    """
    stufe = f"-{int(speicher)}" if speicher else ""
    return f"{device_id or 'ohne-geraet'}{stufe}"


# Das Speichersegment einer `sku_id` (`geraete_model.sku_id`): direkt hinter
# der Geraete-ID steht "<n>gb-" oder "ohne-speicher-", dann die Farbe.
_SPEICHER_SEGMENT = re.compile(r"^(?:(\d+)gb|ohne-speicher)-")


def geraet_aus_sku(sku_id: str, katalog) -> tuple:
    """(device_id, speicher) einer `sku_id` - ueber den KATALOG, nicht
    ueber den Text.

    Ein Buendel traegt nur seine `sku_id`; Name und Modellschluessel haengen
    an der `device_id`, und die stand bisher ausschliesslich an der LISTUNG
    derselben SKU. Fehlt die Listung (o2 fuehrt das iPhone 16 Pro Max
    256 GB im Buendelkatalog, aber nicht mehr im Barpreis-Katalog), stand
    das Buendel unter dem Rohschluessel "ohne-geraet" - im Auswahlfeld,
    als Ueberschrift und als `data-modell` (QA-Befund F-R2-3, 04.09.2026).

    Das ist KEIN Zerlegen der SKU am Bindestrich: `sku_id()` schreibt die
    Geraete-ID des Katalogs woertlich an den Anfang, dahinter das
    Speichersegment als harte Grenze. Gesucht wird die LAENGSTE Katalog-ID,
    auf die genau "<id>-<n>gb-" folgt - "apple-iphone-16-pro-max" schlaegt
    "apple-iphone-16-pro", und "apple-iphone-16" trifft "apple-iphone-16e-"
    nicht, weil hinter der ID kein Bindestrich steht. Eine Farbe mit
    Bindestrich ("space-grau") liegt HINTER dem Speichersegment und
    verschiebt nichts. Trifft keine Katalog-ID, ist die Antwort leer - und
    der Aufrufer benennt das Buendel als nicht zugeordnet, statt es unter
    einem Slug zu zeigen.
    """
    sku = (sku_id or "").strip()
    if not sku or katalog is None:
        return "", None
    treffer = None
    for g in getattr(katalog, "geraete", []) or []:
        gid = getattr(g, "device_id", "") or ""
        if not gid or not sku.startswith(gid + "-"):
            continue
        rest = _SPEICHER_SEGMENT.match(sku[len(gid) + 1:])
        if rest is None:
            continue
        if treffer is None or len(gid) > len(treffer[0]):
            treffer = (gid, int(rest.group(1)) if rest.group(1) else None)
    return treffer or ("", None)


GRUND_OHNE_ZUORDNUNG = ("im Gerätebestand steht keine Listung zu dieser SKU, "
                        "und der Katalog kennt das Gerät nicht")


def ergaenze_geraete_aus_katalog(geraet_je_sku: dict, buendel, katalog
                                 ) -> list:
    """Buendel-SKUs ohne Listung ueber den Katalog nachtragen.

    Traegt `geraet_je_sku` fuer jede aufloesbare SKU nach und gibt die
    NICHT aufloesbaren zurueck - je eine Zeile mit SKU, Anbieter und dem
    Grund, damit die Seite sie beim Namen nennt. Ein Slug als Geraetename
    ist weder Zuordnung noch Ausschluss.
    """
    offen = []
    for b in buendel:
        sku = getattr(b, "sku_id", "") or ""
        if not sku or sku in geraet_je_sku or getattr(b, "ohne_geraet", False):
            continue
        device_id, speicher = geraet_aus_sku(sku, katalog)
        if device_id:
            geraet_je_sku[sku] = (device_id, speicher)
        else:
            offen.append({"sku_id": sku,
                          "anbieter": getattr(b, "anbieter", ""),
                          "grund": GRUND_OHNE_ZUORDNUNG})
    for o in offen:
        log.warning("TCO: Buendel %s (%s) nicht zugeordnet - %s",
                    o["sku_id"], o["anbieter"], o["grund"])
    return offen


def _name(katalog, device_id: str, speicher, rueckfall: str = "") -> str:
    """Der Modellname aus dem KATALOG, nie aus der `sku_id` geschnitten.

    Dieselbe Regel und derselbe Weg wie in `geraete_tco_view._label`:
    Haendler benennen denselben Artikel staendig um, und ein aus der SKU
    zurechtgeschnittener Name liesse dasselbe Geraet unter zwei
    Ueberschriften in derselben Ansicht stehen.
    """
    g = katalog.nach_id(device_id) if (katalog and device_id) else None
    name = getattr(g, "modell", "") or device_id or rueckfall or "?"
    if speicher:
        name = f"{name} {int(speicher)} GB"
    return name


def _hersteller(katalog, device_id: str) -> str:
    g = katalog.nach_id(device_id) if (katalog and device_id) else None
    return getattr(g, "hersteller", "") or ""


def titel(hersteller: str, name: str) -> str:
    """Hersteller plus Modellname - ohne den Hersteller zu verdoppeln.

    Xiaomi, Nothing und Fairphone tragen ihren Namen IM Modellnamen
    ("Xiaomi 17", "Nothing Phone (3)", "Fairphone 6"); "Xiaomi Xiaomi 17
    512 GB" stand am 04.09.2026 in acht Ueberschriften und im Auswahlfeld
    (QA-Befund S12).
    """
    h = (hersteller or "").strip()
    n = (name or "").strip()
    if not h or normalisiere(n).startswith(normalisiere(h)):
        return n
    return f"{h} {n}"


# --------------------------------------------------------------------------
# Die Bausteine: Barpreise und Buendel aus den zwei Speichern
# --------------------------------------------------------------------------

def barpreise(listungen: list) -> dict:
    """sku_id -> {anbieter -> Beleg}, nur Neugeraete mit Kassenpreis.

    Diese Zahl ist der Nenner der Effektivpreiszeile ("was zahle ich fuer
    den TARIF, wenn ich das Geraet zum Marktpreis herausrechne"). Sie muss
    belegt sein - ein geschaetzter Geraetewert machte aus der Formel eine
    Meinung.
    """
    je_sku: dict = {}
    for e in listungen:
        if e.get("zustand") not in _ZUSTAND:
            continue
        preis = e.get("preis_ohne_vertrag")
        if preis is None:
            continue
        beleg = {"anbieter": e.get("anbieter", ""), "betrag": float(preis),
                 "quelle_url": e.get("quelle_url", ""),
                 "abgerufen_am": e.get("abgerufen_am", "")}
        # Eine Listung OHNE `sku_id` kommt vor (Fixtures, kaputte Saetze) -
        # sie darf keinen Schluesselfehler werfen und keinen Barpreis
        # stellen, dem niemand ein Geraet zuordnen kann.
        sku = e.get("sku_id") or ""
        if not sku:
            continue
        je_sku.setdefault(sku, {})
        bisher = je_sku[sku].get(beleg["anbieter"])
        # Der guenstigste Beleg je Anbieter: mehrere Farben desselben
        # Geraets stehen als eigene Listungen im Bestand.
        if bisher is None or beleg["betrag"] < bisher["betrag"]:
            je_sku[sku][beleg["anbieter"]] = beleg
    return je_sku


def _geraetepreis(barpreis: Optional[dict], zuzahlung: Optional[float],
                  raten_summe: Optional[float]) -> tuple[Optional[float],
                                                         Optional[str]]:
    """Der Geraetepreis der Karte - MIT SEINER ART (P1/TCO-1, 11.09.2026).

    Rueckgabe `(betrag, art)`, art ist "barpreis" oder "finanzierung"
    (beides `None`, wenn nichts belegt ist). Die Art entscheidet auf der
    Karte ueber das Etikett: Der EIGENE Barpreis ohne Vertrag heisst
    „Gerätepreis“ (A-R5, BRIEF_RAHMEN2 05.09.2026). Die Summe aus Zuzahlung
    und ALLEN Raten (das o2-Muster, bei congstar Galaxy S26 Ultra 1024
    am 11.09.2026 auf acht Karten unter „Gerätepreis“ gestanden) ist eine
    tariff-abhaengige FINANZIERUNGSSUMME - AUFTRAG_GERAETESEITE.md §3:
    „Zwei Zahlen, nie vermischt“. Sie heisst jetzt „Finanzierung gesamt“
    und wird aus der Gerätepreis-Antwort der Modelltafel ausgeschlossen.

    Dieselbe Regel wie im Zeitreihen-Graph (G0/G2, `historienreihen`):
    zuerst der EIGENE Barpreis ohne Vertrag - ein FREMDER (der guenstigste
    Marktpreis eines anderen Anbieters, `_barpreis_fuer`s Rueckfall) zaehlt
    hier nicht, er ist ein anderes Angebot. Fehlt der eigene Barpreis, aber
    die Rechnung traegt eine Ratenfinanzierung, ist DAS der Geraetepreis
    inkl. Finanzierung. Traegt keins von beiden etwas - 1&1 nennt nur EINEN
    Buendelmonatspreis fuer Tarif und Geraet zusammen, § 13.2 -, bleibt die
    Antwort `None` und die Karte fuehrt weiter mit ihrer TCO-Buendelzahl.
    Keine Erfindung.
    """
    if barpreis is not None and not barpreis.get("fremd"):
        return round(barpreis["betrag"], 2), "barpreis"
    if zuzahlung is not None and raten_summe is not None:
        return round(zuzahlung + raten_summe, 2), "finanzierung"
    return None, None


def _barpreis_fuer(belege: dict, anbieter: str) -> Optional[dict]:
    """Erst der EIGENE Barpreis des Anbieters, dann der guenstigste Markt.

    Die Reihenfolge ist nicht Geschmack: der Barpreis desselben Anbieters
    beantwortet "was kostet das Geraet HIER ohne Vertrag" und ist damit die
    saubere Gegenrechnung. Gibt es ihn nicht - 1&1 verkauft ueberhaupt kein
    Geraet ohne Vertrag -, tritt der guenstigste belegte Marktpreis an
    seine Stelle, und die Karte NENNT ihn samt Anbieter und Datum. Ein
    Marktpreis ohne diesen Hinweis waere eine fremde Zahl in einer eigenen
    Rechnung.
    """
    if not belege:
        return None
    eigener = belege.get(anbieter)
    if eigener is not None:
        return dict(eigener, fremd=False)
    guenstigster = min(belege.values(), key=lambda b: b["betrag"])
    return dict(guenstigster, fremd=True)


# Die drei vom PM benannten Haendler ohne Tarifbuendel (QUELLEN_MAP.md §6,
# Ersterkundung 05.09.2026): fuer sie gibt es keine TCO zu rechnen, nur den
# reinen Geraetepreis. EINE Liste fuer die Haendlerkarten (Vorlage) UND die
# Antwortzeile (`_haendler_geraetepreise` unten) - eine zweite Kopie in
# `geraete_tco_view.py` waere genau die Luecke gewesen, die den PM-Befund
# vom 05.09.2026 (Saturn 1.179,00 EUR unterbot die Antwortzeile-Vodafone-
# Zahl 1.199,90 EUR, ohne dass die Antwortzeile es je gesehen haette) erst
# moeglich gemacht hat.
HAENDLER_OHNE_BUENDEL = ("Amazon", "Expert", "Saturn")


def _haendler_geraetepreise(listungen: list) -> dict:
    """Je Haendler aus `HAENDLER_OHNE_BUENDEL`: der guenstigste NEU-Preis
    dieses Modells, falls schon erhoben - sonst `None`.

    Dieselbe Funktion traegt zwei Verwendungen: die Haendlerkarten der
    Vorlage (ueber `geraete_tco_view.aufbereiten`) UND die Antwortzeile
    (`modelle()` unten) - EINE Rechnung fuer eine Frage, sonst laufen beide
    auseinander wie am 05.09.2026 geschehen.
    """
    out: dict = {}
    for name in HAENDLER_OHNE_BUENDEL:
        kandidaten = [
            l for l in listungen
            if l.get("anbieter") == name
            and l.get("preis_ohne_vertrag") is not None
            and (l.get("zustand") or "neu") in VERGLEICHBARE_ZUSTAENDE
        ]
        if not kandidaten:
            out[name] = None
            continue
        bester = min(kandidaten, key=lambda l: l["preis_ohne_vertrag"])
        out[name] = {
            "preis": bester["preis_ohne_vertrag"],
            "quelle_url": bester.get("quelle_url", ""),
            "abgerufen_am": bester.get("abgerufen_am", ""),
        }
    return out


def buendel_aus_listungen(listungen: list) -> list[Buendel]:
    """Die Buendel, die als LISTUNG im Geraetebestand stehen - heute 1&1.

    1&1 verkauft Geraete ausschliesslich im Tarifbund; sein ld+json nennt
    EINEN Monatsbetrag fuer Tarif und Geraet (`preis_mit_vertrag_ab`) und
    die Laufzeit dazu. Genau so wird er gefuehrt: als
    `Buendel.buendel_monatlich`, ungeteilt.

    DIESE BRUECKE WEICHT VOR GEMESSENEN BUENDELN (S2-C, 09.09.2026):
    seit der Bündellesart (B4) liefert 1&1 dasselbe Angebot auch als
    Bündelsatz mit tarif_id, Einmalzahlung und Bereitstellungsgebühr - die
    Angebots-Dedupe in `modelle()` zieht die gemessene Karte vor
    (`_angebot_rang`). Eine Listung ohne Bündel-Adapter bleibt dagegen
    vollgueltig stehen; diese Funktion ist ihre einzige Karte.
    """
    fertig = []
    for e in listungen:
        betrag = e.get("preis_mit_vertrag_ab")
        if betrag is None or not (e.get("tarif_referenz") or "").strip():
            # Ein Monatsbetrag ohne seinen Tarif ist eine Zahl ohne
            # Bedeutung - dieselbe Regel wie bei `Listung.zuzahlung`.
            continue
        try:
            fertig.append(Buendel(
                sku_id=e.get("sku_id", ""), anbieter=e.get("anbieter", ""),
                # Der Tarifname ist der, den die Produktseite nennt - ein
                # Fremdschluessel auf `tarife.jsonl` entsteht daraus nicht,
                # weil 1&1s Tarife nicht im Tarifbestand stehen. Die Karte
                # traegt deshalb keinen Tarifbeleg und sagt das.
                tarif_name=e["tarif_referenz"],
                buendel_monatlich=float(betrag),
                laufzeit_monate=int(e.get("laufzeit_monate") or 24),
                zustand=e.get("zustand") or "",
                quelle_url=e.get("quelle_url", ""),
                abgerufen_am=e.get("abgerufen_am", "")))
        except (TypeError, ValueError) as exc:
            log.warning("Buendel aus Listung %s uebergangen: %s",
                        e.get("id", "?"), exc)
    return fertig


# --------------------------------------------------------------------------
# Eine Karte
# --------------------------------------------------------------------------

def _bestandteile_mit_kategorie(kennzahl) -> list:
    """`tco_24`s Posten (Name -> Betrag) mit ihrer Kostenart, fuer die
    Balkengrafik (`geraete_tco_grafik.balken`) - dieselbe Kategorienliste,
    die zuvor `tco_bindung` fuehrte. `tco_24` speichert die Posten als
    Woerterbuch (Name -> Betrag, dieselbe Reihenfolge wie gerechnet); die
    Grafik braucht dieselben Zeilen als Liste mit ihrer Kostenart, das ist
    Formatierung und keine zweite Rechnung.
    """
    posten = []
    for name, betrag in kennzahl.bestandteile.items():
        if name in (POSTEN_ZUZAHLUNG, POSTEN_ANSCHLUSS):
            kat = "einmalig"
        elif name.startswith(POSTEN_BUENDEL):
            kat = "buendel"
        elif name.startswith(POSTEN_RATE):
            kat = "raten"
        else:
            kat = "tarif"
        posten.append({"name": name, "betrag": betrag, "kategorie": kat})
    return posten


def _karte(b: Buendel, tarif: Optional[dict], barpreis: Optional[dict],
           katalog, geraet_je_sku: dict, zustand: str = "unbekannt") -> dict:
    """Aus einem Buendel wird eine Karte - gerechnet wird in `tco_model`.

    Diese Funktion addiert keinen Euro. Sie holt die Kennzahl, haengt die
    Belege daran und formt die Pflichtzeilen des Katalogs D.

    TICKET TCO24-1: die Leitzahl ist `tco_24()`, IMMER 24 Monate
    (AUFTRAG_GERAETESEITE.md §3). Bis dahin fuehrte diese Funktion
    `tco_bindung()`, eine Kennzahl ueber die eigene Bindung des Buendels -
    sichtbar als "TCO-36", der deklarierte Fehler dieses Tickets.
    """
    kennzahl = tco_24(b)
    device_id, speicher = geraet_je_sku.get(b.sku_id, ("", None))
    # "ab Monat 25: X EUR" - die Grundgebuehr nach dem festen 24-Monats-
    # Horizont, aus den PREISPHASEN des Pflichtdokuments. Sie ist die
    # Antwort auf die Kostenfallen-Kritik (Recherche § 2.3) und wird NICHT
    # geraten: gibt es keine Phase fuer den Monat danach, steht dort nichts.
    nach_bindung = _phase_ab(tarif, AB_MONAT) if tarif else None

    eff = None
    if barpreis is not None and kennzahl.belastbar:
        eff = round(kennzahl.monatlich - barpreis["betrag"] / TCO_HORIZONT, 2)
    # Katalog D: "X € in 36 Raten" - die volle Ratensumme (nicht auf 24
    # Monate gekappt), dieselbe Zahl traegt auch die Geraetepreis-Leitzahl
    # (A-R5), einmal gerechnet statt zweimal.
    raten_summe = (round(b.geraet_monatsrate * b.laufzeit_monate, 2)
                  if b.geraet_monatsrate is not None else None)
    geraetepreis, geraetepreis_art = _geraetepreis(
        barpreis, b.geraet_zuzahlung, raten_summe)
    return {
        # B.2.5 GILT AUCH HIER. Eine Karte ohne Zahl braucht ihren Grund -
        # `_leere_karte` fuellt ihn, diese Funktion tat es nicht, und die
        # Vorlage rendert dann einen leeren Absatz unter Anbieter und
        # Tarif.
        "leer_grund": "" if kennzahl.belastbar else _grund(kennzahl),
        "sku_id": b.sku_id,
        "modell_id": modell_schluessel(device_id, speicher),
        # DER ZUSTAND STEHT AN DER KARTE, und `vergleichbar` sagt, ob sie
        # im Vergleich des Modellblocks mitspielt: nur ein Neugeraet wird
        # gegen die Neugeraet-Referenz gestellt. Ein erneuertes Geraet
        # bekommt sein Etikett auf Karte, Balken und - wo eins entsteht -
        # im Delta-Satz (H5).
        "zustand": zustand,
        "zustand_etikett": ZUSTAND_ETIKETT.get(zustand, zustand),
        "vergleichbar": zustand in _ZUSTAND,
        # Dieselbe Klasse auf Karte, Balken und Legende - C.3 verlangt die
        # Anbieterfarbe konsistent ueber ALLE Grafiken und Tabellen.
        "slug": anbieter_slug(b.anbieter),
        "geraet": _name(katalog, device_id, speicher, rueckfall=b.sku_id),
        "anbieter": b.anbieter,
        "eigen": _eigen(b.anbieter),
        "tarif": b.tarif_name,
        "tarif_id": b.tarif_id,
        "tarif_id_guete": b.tarif_id_guete,
        # A-R5: DER GERAETEPREIS IST DIE LEITZAHL, das TCO-Etikett/-Label
        # steht daneben als Sekundaerzeile ("mit Tarif: ..."). `label` und
        # `gesamt` bleiben unveraendert die TCO-Zahl - nur die Vorlage
        # entscheidet, welche der beiden Zahlen zuerst und gross steht.
        # P1/TCO-1: die ART entscheidet ueber das Etikett - nur der eigene
        # Barpreis heisst „Gerätepreis“, die Finanzierungssumme heisst
        # „Finanzierung gesamt“ (§3, zwei Zahlen, nie vermischt).
        "geraetepreis": geraetepreis,
        "geraetepreis_art": geraetepreis_art,
        # TICKET TCO24-1: Laufzeit und Etikett sind Konstanten - "Immer 24
        # Monate" ist keine Ableitung aus dem Buendel mehr.
        "label": LABEL,
        "laufzeit": LAUFZEIT,
        "ab_monat": AB_MONAT,
        # Informativ: die eigene Mindestlaufzeit des TARIFS (kann von den
        # 24 Monaten der Leitzahl abweichen, z. B. bei einem Flextarif) und
        # die tatsaechliche Laufzeit der Geraeteraten. Beide bestimmen die
        # Leitzahl NICHT mehr - die tut es nie, seit sie fest ist.
        "tarif_bindung": b.tarif_bindung_monate,
        "raten_laufzeit": (b.laufzeit_monate
                           if (b.geraet_monatsrate is not None
                               or b.buendel_monatlich is not None) else None),
        "belastbar": kennzahl.belastbar,
        "gesamt": kennzahl.gesamt if kennzahl.belastbar else None,
        "schnitt_monat": kennzahl.monatlich if kennzahl.belastbar else None,
        # A5.2, Pflichtzeile, jetzt woertlich statt gerechnet: die Leitzahl
        # IST der 24-Monats-Betrag, "gezahlt nach 24 Monaten" ist deshalb
        # `gesamt` selbst. "Danach noch offen" ist der Restbetrag aus
        # `tco_model` - er veraendert weder TCO-24 noch deren Sortierung
        # (Abnahmekriterium 2).
        "gezahlt_nach_24": kennzahl.gesamt if kennzahl.belastbar else None,
        "offen_nach_24": (kennzahl.restbetrag
                          if kennzahl.belastbar and kennzahl.restbetrag
                          else None),
        "offene_raten": (max(0, (b.laufzeit_monate or 0) - TCO_HORIZONT)
                         if b.geraet_monatsrate is not None
                         or b.buendel_monatlich is not None else 0),
        # Die Bausteine, jeder mit dem Label aus Katalog D.
        "monatlich": b.tarif_monatlich,
        "buendel_monatlich": b.buendel_monatlich,
        "zuzahlung": b.geraet_zuzahlung,
        "rate": b.geraet_monatsrate,
        # Katalog D: "X € in 36 Raten" - die volle Ratensumme, siehe oben.
        "raten_summe": raten_summe,
        "anschlusspreis": b.anschlusspreis,
        "nach_bindung": nach_bindung,
        "eff_ohne_geraet": eff,
        "eff_basis": barpreis,
        "bestandteile": _bestandteile_mit_kategorie(kennzahl),
        "luecken": kennzahl.luecken,
        # Rabatte werden nie in die Leitzahl gerechnet (tco_model Regel 3,
        # AUFTRAG_GERAETESEITE §3: "Prämien, Cashback [...] bleiben
        # außerhalb der TCO-24"); `tco_24` fuehrt sie deshalb nicht mehr
        # einzeln ab, nur ihre Summe steht als Auskunft in `rabatte_offen`.
        "boni": [],
        "boni_abzug": kennzahl.rabatte_offen,
        "quelle_url": b.quelle_url,
        "abgerufen_am": b.abgerufen_am,
        "tarif_quelle_url": (tarif or {}).get("dokument_url", ""),
        "naeherung": False,
        # "ab": `preis_mit_vertrag_ab` heisst so, weil der Anbieter ihn fuer
        # den guenstigsten Tarif dieses Geraets nennt. Die Karte sagt es -
        # eine Leitzahl aus einem Ab-Preis ohne diesen Hinweis waere eine
        # exakte Zahl mit einem unausgesprochenen Vorbehalt.
        "ab_preis": b.buendel_monatlich is not None,
    }


# Was auf der Karte steht, wenn die Rechnung nicht traegt. `tco_24` kennt
# seit Ticket TCO24-1 nur noch EINE Luecke, die eine Karte unbelastbar
# macht: den fehlenden Tarifgrundpreis (`POSTEN_TARIF`). Die Flextarif-/
# Tarifbindungs-Sonderfaelle von `tco_bindung` entfallen - "Immer 24
# Monate" rechnet den Tarifgrundpreis unabhaengig von der Mindestlaufzeit.
_GRUND_JE_LUECKE = {
    POSTEN_TARIF: ("Der Tarifgrundpreis dieses Bündels ist nicht erhoben – "
                   "ohne ihn ist es kein Gesamtpreis, sondern ein "
                   "Gerätebetrag."),
}


def _grund(kennzahl) -> str:
    """Warum diese Karte keine Zahl traegt - in der Reihenfolge der Ursachen."""
    if POSTEN_TARIF in kennzahl.luecken:
        return _GRUND_JE_LUECKE[POSTEN_TARIF]
    if kennzahl.gesamt is None:
        return ("Zu diesem Bündel ist kein einziger Posten erhoben – es "
                "steht als Angebot da, nicht als Preis.")
    return ("Die Rechnung ist unvollständig: " +
            ", ".join(kennzahl.luecken) + " nicht gemessen.")


def _phase_ab(tarif: dict, monat: int) -> Optional[float]:
    """Der Betrag, der im gegebenen Monat laut Pflichtdokument gilt."""
    for phase in (tarif.get("preisphasen") or []):
        von = phase.get("von_monat") or 1
        bis = phase.get("bis_monat")
        if von <= monat and (bis is None or monat <= bis):
            betrag = phase.get("betrag")
            return round(float(betrag), 2) if betrag is not None else None
    return None


def _leere_karte(anbieter: str, grund: str = "") -> dict:
    """Ein Anbieter ohne Zahl - mit Namen und mit Begruendung (B.2.5)."""
    return {"anbieter": anbieter, "eigen": _eigen(anbieter), "tarif": "",
            "slug": anbieter_slug(anbieter),
            "geraetepreis": None, "geraetepreis_art": None,
            "label": "", "laufzeit": None, "ab_monat": None, "belastbar": False,
            "gesamt": None, "schnitt_monat": None, "gezahlt_nach_24": None,
            "offen_nach_24": None, "offene_raten": 0, "monatlich": None,
            "buendel_monatlich": None, "zuzahlung": None, "rate": None,
            "raten_summe": None,
            "anschlusspreis": None, "nach_bindung": None,
            "eff_ohne_geraet": None, "eff_basis": None, "bestandteile": [],
            "luecken": [], "boni": [], "boni_abzug": 0.0, "quelle_url": "",
            "abgerufen_am": "", "tarif_quelle_url": "", "naeherung": False,
            "leer_grund": grund or LEER_GRUND.get(anbieter, ""),
            "ab_preis": False,
            "zustand": "", "zustand_etikett": "", "vergleichbar": False,
            "sku_id": "", "modell_id": "", "geraet": "", "tarif_id": "",
            "tarif_id_guete": "", "tarif_bindung": None,
            "raten_laufzeit": None}


# --------------------------------------------------------------------------
# Die Vodafone-Referenz: gemessene Summanden, gerechnete Summe
# --------------------------------------------------------------------------

def _vodafone_referenz(referenzen: list, tarife: dict,
                       barpreise_der_sku: dict) -> Optional[dict]:
    """Tarif ohne Geraet + eigener Barpreis, ueber den festen 24-Monats-
    Horizont (TICKET TCO24-1: "Immer 24 Monate" - AUFTRAG_GERAETESEITE.md
    §3. Bis dahin rechnete diese Funktion ueber ein variables FENSTER,
    das die laengste Bindung der verglichenen Buendel uebernahm - der
    Grund, warum 30 Referenzkarten "TCO-36" trugen, obwohl Vodafone gar
    kein 36-Monats-Angebot hat).

    Genommen wird der GUENSTIGSTE belegte Vodafone-Mobilfunktarif. Die Wahl
    steht hier ausgeschrieben, weil sie das Ergebnis faerbt: der
    guenstigste Tarif ist die fuer uns UNguenstigste Referenz, also die
    konservative. Ein Delta "Wettbewerber ist teurer" haelt damit auch
    dann, wenn jemand einen anderen Vodafone-Tarif fuer den passenderen
    haelt.

    Der Tarifbetrag ist phasengewichtet (`effektivpreis.phasensumme`) -
    dieselbe Rechnung wie auf der Tarifseite und an EINER Stelle. Steht im
    Blatt eine Phase fuer Monat 25 und danach, wird sie gelesen; steht
    keine, gilt der Grundpreis fort, und die Karte sagt es.
    """
    vodafone = [r for r in referenzen
                if _eigen(getattr(r, "anbieter", ""))
                and getattr(r, "tarif_sim_only_monatlich", None) is not None]
    geraet = (barpreise_der_sku or {}).get("Vodafone")
    if not vodafone or geraet is None:
        return None
    referenz = min(vodafone, key=lambda r: r.tarif_sim_only_monatlich)
    tarif = tarife.get(referenz.tarif_id) or {}
    phasen = [Preisphase(von_monat=p.get("von_monat") or 1,
                         bis_monat=p.get("bis_monat"),
                         betrag=p.get("betrag"))
              for p in (tarif.get("preisphasen") or [])
              if p.get("betrag") is not None]

    summe = phasensumme(phasen, TCO_HORIZONT) if phasen else None
    # "Fortgeschrieben" heisst: das Blatt sagt zu einem Teil der 24 Monate
    # nichts, und es gilt der zuletzt belegte Preis weiter. Das ist die
    # vorsichtige Annahme (dieselbe wie in `phasensumme`), aber sie ist
    # eine Annahme - deshalb steht sie auf der Karte und nicht nur im Code.
    abgedeckt = 0
    for phase in phasen:
        abgedeckt = max(abgedeckt, TCO_HORIZONT if phase.bis_monat is None
                        else phase.bis_monat)
    fortgeschrieben = abgedeckt < TCO_HORIZONT
    if summe is None:
        summe = round(referenz.tarif_sim_only_monatlich * TCO_HORIZONT, 2)
        fortgeschrieben = fortgeschrieben or not phasen
    gesamt = round(summe + geraet["betrag"], 2)
    return {
        # F5 auch an der Referenz: das Blatt nennt "ab Monat 25" (Vodafone
        # Mobil XS: 29,95 EUR) - die Zeile steht auf jeder Karte mit Zahl.
        "nach_bindung": _phase_ab(tarif, AB_MONAT),
        "tarif": referenz.tarif_name,
        "tarif_id": referenz.tarif_id,
        "monatlich": referenz.tarif_sim_only_monatlich,
        "tarif_summe": summe,
        "tarif_quelle_url": referenz.quelle_url,
        "tarif_abgerufen_am": referenz.abgerufen_am,
        "geraet_betrag": geraet["betrag"],
        # Der Geraetebetrag der Naeherung ist der EIGENE Vodafone-Barpreis
        # (aus `barpreise_der_sku`) - also ein Barpreis, keine Finanzierung.
        "geraet_art": "barpreis",
        "geraet_quelle_url": geraet.get("quelle_url", ""),
        "geraet_abgerufen_am": geraet.get("abgerufen_am", ""),
        "monate": TCO_HORIZONT,
        "tarif_monate": TCO_HORIZONT,
        "gesamt": gesamt,
        "schnitt_monat": round(gesamt / TCO_HORIZONT, 2),
        "fortgeschrieben": fortgeschrieben,
    }


def _referenz_aus_buendel(karte: dict) -> dict:
    """Ein ECHTES eigenes Buendel schlaegt jede Naeherung.

    Wo Vodafone selbst ein Buendel zu diesem Geraet ausweist, ist das die
    Referenz - und die gerechnete Summe aus Tarif und Barpreis entfaellt.
    Beides nebeneinander stuende zweimal unter demselben Namen auf einer
    Karte, und der Leser muesste raten, welche der zwei Zahlen "unser
    Preis" ist. Dieselbe Regel wie ueberall auf dieser Seite: eine Zahl
    steht je Ort genau EINMAL.
    """
    return {
        "tarif": karte["tarif"], "tarif_id": karte.get("tarif_id", ""),
        "monatlich": karte.get("monatlich") or karte.get("buendel_monatlich"),
        "tarif_summe": None,
        "tarif_quelle_url": karte.get("tarif_quelle_url", ""),
        "tarif_abgerufen_am": karte.get("abgerufen_am", ""),
        # A-R5: traegt das Quellbuendel bereits einen Geraetepreis (eigener
        # Barpreis oder Zuzahlung+Ratensumme), fuehrt die Referenzkarte
        # damit - sonst faellt sie auf ihre TCO-Zahl zurueck, wie jede
        # andere Karte ohne belegten Geraetepreis auch. P1: die ART kommt
        # mit, damit die Referenzkarte dieselbe Trennung von Barpreis und
        # Finanzierungssumme traegt wie ihre Quelle.
        "geraet_betrag": karte.get("geraetepreis"),
        "geraet_art": karte.get("geraetepreis_art"),
        "geraet_quelle_url": karte.get("quelle_url", ""),
        "geraet_abgerufen_am": karte.get("abgerufen_am", ""),
        "monate": karte["laufzeit"], "gesamt": karte["gesamt"],
        "schnitt_monat": karte["schnitt_monat"], "fortgeschrieben": False,
        "aus_buendel": True,
    }


def _referenzkarte(ref: dict) -> dict:
    """Die Referenzrechnung als Karte - sichtbar als Naeherung markiert."""
    karte = _leere_karte("Vodafone")
    karte.update({
        # KEIN Leergrund: diese Karte traegt eine Zahl. Der Vorbehalt steht
        # in `naeherung` und auf der Seite in einem eigenen Satz - nicht in
        # dem Feld, das "hier gibt es nichts" bedeutet.
        "leer_grund": "",
        "tarif": ref["tarif"],
        # TICKET TCO24-1: die Leitzahl ist IMMER TCO-24 - `ref["monate"]`
        # und `ref["tarif_monate"]` sind seit `_vodafone_referenz` beide
        # der feste Horizont (`TCO_HORIZONT`), keine variable Fensterzahl
        # mehr. Vorher trugen alle 30 Referenzkarten "TCO-36" bei einer
        # Rechnung, die 24 Tarifmonate plus Barkauf war (QA-Befund F-R2-2).
        "label": LABEL, "ab_monat": AB_MONAT,
        "laufzeit": ref["tarif_monate"],
        "fenster": ref["monate"],
        "belastbar": True, "naeherung": True,
        # A-R5: der Barpreis des Geraets bei Vodafone ist der Geraetepreis
        # inkl. Finanzierung dieser Karte - er ist einer der zwei GEMESSENEN
        # Summanden, aus denen die Naeherung ihre TCO rechnet (siehe
        # Modulkopf). Kommt die Referenz aus einem echten Vodafone-Buendel,
        # steht hier stattdessen dessen eigener Geraetepreis (oder `None`,
        # wenn das Buendel selbst keinen belegt).
        "geraetepreis": ref["geraet_betrag"],
        # P1/TCO-1: auch die Referenzkarte nennt ihre Zahl beim Namen -
        # aus `_vodafone_referenz` ist es immer der eigene Barpreis, aus
        # `_referenz_aus_buendel` die Art des Quellbuendels.
        "geraetepreis_art": ref.get("geraet_art"),
        # `barpreise()` nimmt nur Neugeraete - die Referenz ist also eine
        # Neugeraet-Zahl und spielt im Vergleich mit.
        "zustand": "neu", "zustand_etikett": "", "vergleichbar": True,
        "gesamt": ref["gesamt"], "schnitt_monat": ref["schnitt_monat"],
        "monatlich": ref["monatlich"],
        # Auch die Referenz beantwortet Antonios Frage: nach 24 Monaten hat
        # man den Barpreis laengst gezahlt und den Tarif fuer 24 Monate.
        # Das Geraet ist am ersten Tag bezahlt, der Tarif laeuft seine
        # Mindestlaufzeit - nach 24 Monaten ist damit alles gezahlt, was
        # geschuldet ist. Vorher stand hier "davon noch offen: 359,40 €"
        # fuer ein bar gekauftes Geraet auf einem 24-Monats-Tarif.
        "gezahlt_nach_24": round(
            ref["geraet_betrag"]
            + ref["monatlich"] * min(TCO_HORIZONT, ref["tarif_monate"]), 2),
        "tarif_bindung": ref["tarif_monate"],
        "nach_bindung": ref.get("nach_bindung"),
        "bestandteile": [
            {"name": "Gerät ohne Vertrag · Barpreis",
             "betrag": ref["geraet_betrag"], "kategorie": "einmalig"},
            {"name": f"Tarif · {ref['tarif_monate']} Monate {ref['tarif']}",
             "betrag": ref["tarif_summe"], "kategorie": "tarif"}],
        # Der Anschlusspreis steht in KEINEM der fuenf Vodafone-Blaetter -
        # unbekannt ist nicht kostenlos.
        "luecken": [POSTEN_ANSCHLUSS],
        "quelle_url": ref["geraet_quelle_url"],
        "abgerufen_am": ref["geraet_abgerufen_am"],
        "tarif_quelle_url": ref["tarif_quelle_url"],
        "referenz": ref,
    })
    karte["offen_nach_24"] = round(karte["gesamt"] - karte["gezahlt_nach_24"], 2)
    return karte


# --------------------------------------------------------------------------
# Das Delta gegen die Referenz
# --------------------------------------------------------------------------

def _wesentlich(differenz: float, bezug: float) -> bool:
    """ODER, nicht UND - bei 200 EUR sind 15 EUR viel und 3 Prozent wenig."""
    abstand = abs(differenz)
    prozent = (abstand / bezug * 100) if bezug else 0.0
    return (prozent >= geraete_vergleich.WESENTLICH_PROZENT
            or abstand >= geraete_vergleich.WESENTLICH_EURO)


def _delta(karte: dict, referenz: Optional[dict]) -> Optional[dict]:
    """Euro primaer, Prozent sekundaer - und nur bei gleicher Laufzeit.

    Ueber Laufzeiten hinweg gibt es kein Euro-Delta (A5.4). Wo die Karte
    36 Monate bindet und die Referenz 24 rechnet, waere die Differenz die
    Laufzeit und nicht der Preis; dann steht nur der Abstand im
    Quervergleichsmass `Ø/Monat` (A5.3).
    """
    if referenz is None or not karte["belastbar"] or karte["naeherung"]:
        return None
    if karte["gesamt"] is None or not karte["laufzeit"]:
        return None
    if not karte.get("vergleichbar", True):
        # Ein erneuertes Geraet ist kein Konkurrent des Neugeraets (H5).
        # "775,35 EUR guenstiger als die Vodafone-Referenz" stand am
        # 04.09.2026 unter einem gebrauchten iPhone 15 gegen ein neues.
        return None
    if karte["eigen"]:
        # Ein eigenes Buendel IST die Referenz (oder ein zweites eigenes
        # Angebot). "0,00 € teurer als die Vodafone-Referenz" auf einer
        # Vodafone-Karte war der Befund B4 aus Phase 6a, hier neu
        # entstanden.
        return None
    gleiche_laufzeit = karte["laufzeit"] == referenz["monate"]
    betrag = (round(karte["gesamt"] - referenz["gesamt"], 2)
              if gleiche_laufzeit else None)
    monatlich = round(karte["schnitt_monat"] - referenz["schnitt_monat"], 2)
    bezug = betrag if betrag is not None else monatlich
    # WESENTLICHKEIT, dieselbe Schwelle und dieselbe Begruendung wie in
    # `geraete_vergleich` und `geraete_tco_view._delta`: unter drei Prozent
    # ODER fuenfzehn Euro ist der Abstand keine Meldung. Ohne sie schriebe
    # das lauteste Element der Karte bei zwei gleich teuren Angeboten
    # "0,00 € teurer als die Vodafone-Referenz".
    massstab = referenz["gesamt"] if betrag is not None \
        else referenz["schnitt_monat"]
    if not _wesentlich(bezug, massstab):
        return None
    return {
        "betrag": betrag,
        "prozent": (round(abs(betrag) / referenz["gesamt"] * 100, 1)
                    if betrag is not None and referenz["gesamt"] else None),
        "monatlich": monatlich,
        "guenstiger": bezug < 0,
        "abstand": abs(betrag) if betrag is not None else abs(monatlich),
        "gleiche_laufzeit": gleiche_laufzeit,
        "referenz_tarif": referenz["tarif"],
        "referenz_datum": referenz["tarif_abgerufen_am"],
        "referenz_gesamt": referenz["gesamt"],
    }


# --------------------------------------------------------------------------
# Der Einstieg
# --------------------------------------------------------------------------

def _rang(karte: dict) -> tuple:
    """Default-Sortierung: Ø/Monat aufsteigend (A5.3).

    Das ist das einzige Mass, das 24- und 36-Monats-Angebote in EINER
    Rangfolge fuehren darf. Karten ohne Zahl stehen hinten - sie sind kein
    guenstigstes Angebot, sondern eine Luecke.
    """
    return (not karte["belastbar"], not karte.get("vergleichbar", True),
            karte["naeherung"],
            karte["schnitt_monat"] if karte["schnitt_monat"] is not None
            else 9e9, karte["anbieter"])


def _angebot_rang(karte: dict) -> tuple:
    """Die Angebots-Dedupe in `modelle()`: QUELLE vor Preis (S2-C).

    Einem Anbieter mit Bündel-Adapter steht dasselbe Angebot ZWEIMAL im
    Bestand - als Listung (nur der Monatsbetrag) und als gemessenes Bündel
    (mit Einmalzahlung, Bereitstellungsgebühr und tarif_id). Die Listung
    kann die billigere Karte sein, weil ihr Posten FEHLEN; sie darf das
    gemessene Angebot deshalb nicht verdraengen. Erst wenn BEIDE Karten
    aus derselben Quelle kommen, entscheidet der Preis.
    """
    return (1 if karte.get("aus_listung") else 0,
            karte["schnitt_monat"] if karte["schnitt_monat"] is not None
            else 9e9)


def _vorgabe(modelle: list) -> str:
    """Welches Modell ohne Klick sichtbar ist.

    Das Lastenheft stellt seine Leitfrage woertlich an EINEM Geraet
    ("iPhone 17 Pro mit Tarif X bei Anbieter Y - was zahlt der Kunde ueber
    24 Monate gesamt?"), und die Abnahme (G3) prueft genau daran. Deshalb
    steht es vorn, sobald es mit mindestens zwei Anbietern rechenbar ist -
    und sonst faellt die Wahl auf das erste Modell der Liste. Eine
    Vorgabe, die an einem einzelnen Geraet haengt, waere ohne diesen
    Rueckfall ein Leerzustand, sobald Apple ein Modell umbenennt.

    F-5 (05.09.2026): `bundle_anbieter` zaehlt die Anbieter mit einem
    TCO-Buendel zu diesem Modell - eine ANDERE Menge als die
    "Anbieter"-Zahl, die die Seite jetzt zeigt (die Preispunkte-Reihen der
    Zeitreihe, `geraete_tco_grafik.zeitreihe().anbieterzahl`). Diese
    Schwelle bleibt bewusst bundle-bezogen: die Leitfrage handelt von einem
    RECHENBAREN Tarif-Vergleich ("mit Tarif X bei Anbieter Y"), nicht von
    Preispunkten in einem Chart.
    """
    for modell in modelle:
        if modell["id"] == LEITFRAGE_MODELL and len(
                modell["bundle_anbieter"]) >= 2:
            return modell["id"]
    return modelle[0]["id"] if modelle else ""


def modelle(buendel: list, listungen: list, referenzen: list, tarife: dict,
            katalog) -> dict:
    """Alle Modelle mit mindestens einem Buendel, je Modell vier Anbieter.

    Rueckgabe:
        modelle         [{id, name, hersteller, speicher, karten, referenz,
                          laufzeiten, spanne, bundle_anbieter}]
        vorgabe         die ID des Modells, das ohne Klick sichtbar ist
        ohne_zuordnung  Buendel, deren SKU weder eine Listung noch ein
                        Katalogeintrag aufloest - mit Grund, nie als Modell
    """
    geraet_je_sku: dict = {}
    for e in listungen:
        if e.get("sku_id"):
            geraet_je_sku.setdefault(e["sku_id"], (e.get("device_id") or "",
                                                   e.get("speicher_gb")))
    # Ein Buendel ohne Listung derselben SKU bekommt sein Geraet aus dem
    # Katalog (F-R2-3); was auch dort nicht steht, faellt BENANNT heraus.
    ohne_zuordnung = ergaenze_geraete_aus_katalog(geraet_je_sku, buendel,
                                                  katalog)
    belege = barpreise(listungen)
    zustaende = _zustand_je_listung(listungen)

    # Fuer die Antwortzeile (F-4a': "guenstigster Geraetepreis" gilt auch
    # ueber die Haendler ohne Tarifbuendel). Amazon, Expert und Saturn
    # bekommen NIE eine Karte in `gruppen` - sie liefern kein Buendel, also
    # auch keinen Eintrag in `alle` unten. Ohne diese eigene Gruppierung
    # nach MODELL (nicht nach SKU der Buendel) waere ihr Preis fuer die
    # Antwortzeile unsichtbar, obwohl er auf derselben Seite als
    # Haendlerkarte steht.
    listungen_je_modell: dict[str, list] = {}
    for e in listungen:
        mid_e = modell_schluessel(e.get("device_id"), e.get("speicher_gb"))
        listungen_je_modell.setdefault(mid_e, []).append(e)

    alle = list(buendel) + buendel_aus_listungen(listungen)
    # GEMESSENE BUENDEL SCHLAGEN LISTUNGS-BUENDEL DESSELBEN ANGEBOTS
    # (S2-C, 09.09.2026): fuer 1&1 stehen beide Lesarten nebeneinander - die
    # Listung nur mit dem Monatsbetrag, das Bündel im Store seit S2-C auch
    # mit Einmalzahlung und Bereitstellungsgebühr samt tarif_id. In der
    # Preisordnung des Monatsbetrags war die LISTUNG die guenstigere Karte,
    # weil ihr Felder fehlen: Sie verdraengte das gemessene Angebot und
    # riss ihm tarif_id und Band mit (im Wettbewerbs-Radar standen alle
    # 1&1-Zeilen als Band-Mismatch da, Beleg vom Vortag). Die Listung ist
    # die BRUECKE fuer Anbieter OHNE Bündel-Adapter - hat derselbe
    # Anbieter ein gemessenes Bündel, ist sie die schwaechere Quelle und
    # weicht, egal was sie kostet.
    listung_ids = {id(b) for b in alle[len(buendel):]}
    gruppen: dict = {}
    for b in alle:
        if not isinstance(b, Buendel) or b.ohne_geraet:
            continue
        if b.sku_id not in geraet_je_sku:
            continue          # steht in `ohne_zuordnung`, mit Grund
        device_id, speicher = geraet_je_sku[b.sku_id]
        mid = modell_schluessel(device_id, speicher)
        tarif = tarife.get(b.tarif_id) if b.tarif_id else None
        karte = _karte(b, tarif, _barpreis_fuer(belege.get(b.sku_id, {}),
                                                b.anbieter),
                       katalog, geraet_je_sku,
                       zustand=zustand_des_buendels(b, zustaende))
        if id(b) in listung_ids:
            karte["aus_listung"] = True
        gruppen.setdefault(mid, {"id": mid, "device_id": device_id,
                                 "speicher": speicher, "karten": [],
                                 "skus": set()})
        gruppen[mid]["karten"].append(karte)
        gruppen[mid]["skus"].add(b.sku_id)

    fertig = []
    for mid, gruppe in gruppen.items():
        karten = gruppe["karten"]
        # Nur EINE Karte je (Anbieter, Tarif): dasselbe Geraet in drei
        # Farben ist dreimal derselbe Preis, und drei gleiche Karten
        # nebeneinander sind der "Dedupe-Toggle"-Fall aus B.3, nur ohne
        # Schalter. Genommen wird die guenstigste - und zuerst die
        # GEMESSENE (`_angebot_rang`, S2-C: eine billigere Listungskarte
        # ist billig, weil ihr Felder fehlen).
        #
        # DER ZUSTAND GEHOERT IN DEN SCHLUESSEL. Ohne ihn nahm diese Stelle
        # je (Anbieter, Tarif) die guenstigste Karte - und die guenstigste
        # war bei zehn o2-Modellen das erneuerte Geraet. Der Store trug
        # beide (iPhone 15 128 GB: neu 20,00 EUR, erneuert 17,00 EUR im
        # Monat); die Tafel zeigte nur das erneuerte, ohne Etikett, als
        # Sieger gegen die Neugeraete von 1&1 und Vodafone (QA-Befund B1).
        je_angebot: dict = {}
        for k in karten:
            schluessel = (k["anbieter"], k["tarif"], k["laufzeit"],
                          k["zustand"])
            bisher = je_angebot.get(schluessel)
            if bisher is None or _angebot_rang(k) < _angebot_rang(bisher):
                je_angebot[schluessel] = k
        karten = sorted(je_angebot.values(), key=_rang)

        # Die Barpreisbelege aller Farben dieses Modells zusammen - die
        # Vodafone-Referenz haengt an einer beliebigen davon.
        belege_modell: dict = {}
        for sku in gruppe["skus"]:
            for anbieter, beleg in belege.get(sku, {}).items():
                bisher = belege_modell.get(anbieter)
                if bisher is None or beleg["betrag"] < bisher["betrag"]:
                    belege_modell[anbieter] = beleg

        laufzeiten = sorted({k["laufzeit"] for k in karten if k["laufzeit"]})
        # ERST DAS EIGENE BUENDEL, DANN DIE NAEHERUNG. Wo Vodafone selbst
        # ein Buendel zu diesem Geraet ausweist, ist es die Referenz; die
        # gerechnete Summe traete sonst als zweite Vodafone-Karte daneben.
        # ... und nur ein NEUGERAET: ein erneuertes eigenes Buendel als
        # Massstab fuer neue Wettbewerbergeraete waere derselbe Fehler mit
        # umgekehrtem Vorzeichen.
        eigene = [k for k in karten
                  if k["eigen"] and k["belastbar"] and k["vergleichbar"]]
        naeherung = None
        if eigene:
            referenz = _referenz_aus_buendel(
                min(eigene, key=lambda k: k["gesamt"]))
        else:
            # TICKET TCO24-1: die Naeherung rechnet ueber den festen
            # 24-Monats-Horizont - keine Laufzeit mehr, die sie sich von
            # den Karten dieses Modells leiht.
            referenz = _vodafone_referenz(referenzen, tarife, belege_modell)
            naeherung = referenz
        for k in karten:
            k["delta"] = _delta(k, referenz)

        vorhanden = {k["anbieter"] for k in karten}
        if naeherung is not None:
            karten.append(_referenzkarte(naeherung))
            vorhanden.add("Vodafone")
        for anbieter in ANBIETER_REIHENFOLGE:
            if anbieter not in vorhanden:
                karten.append(_leere_karte(anbieter))

        # DIE SPANNE UND DIE ZAEHLER MEINEN DEN VERGLEICH, also die
        # Neugeraete. Ein Angebot ist jede Karte mit Zahl, die KEINE
        # Referenzrechnung ist (die nennt sich selbst "kein Angebot" -
        # QA-Befund S3); die etikettierten stehen daneben, mit Zahl.
        angebote = [k for k in karten if k["belastbar"] and not k["naeherung"]]
        # DIE SPANNE IST DIE DER ANGEBOTE. Die Referenzrechnung stand bis zum
        # 04.09.2026 mit darin - und seit sie ihre eigene Bindung traegt
        # (F-R2-2), hiesse das "TCO-36 von 1.120,75 bis 1.428,70 EUR" mit
        # einer TCO-24-Zahl als Obergrenze. Dieselbe Fehlerklasse wie das
        # Etikett selbst, eine Zeile weiter oben auf der Seite.
        betraege = [k["gesamt"] for k in angebote
                    if k["vergleichbar"] and k["gesamt"] is not None]
        name = _name(katalog, gruppe["device_id"], gruppe["speicher"],
                     rueckfall=mid)
        hersteller = _hersteller(katalog, gruppe["device_id"])

        # DIE EINE ANTWORTZEILE (BRIEF_FADEN, 05.09.2026): "Was kostet
        # dieses Geraet?" - zwei Zahlen, je mit ihrem Anbieter, sonst ist
        # eine Zahl auf dieser Seite nicht nachpruefbar. Beide nur ueber
        # NEUGERAETE (`vergleichbar`) - ein erneuertes Geraet darf die
        # Antwort nicht unterbieten, das ist eine andere Preisdimension
        # (CLAUDE.md §6).
        #
        # DIE ZWEI ZAHLEN HABEN VERSCHIEDENE VERGLEICHSMENGEN, und das ist
        # kein Widerspruch: der GERAETEPREIS ist ein reiner Barpreis und
        # braucht kein eigenes Tarifbuendel, deshalb zaehlt auch die
        # Naeherungskarte mit (Vodafone fuehrt oft keinen Buendelpreis, wohl
        # aber einen eigenen Barpreis). Der TARIF-GESAMTPREIS ist dagegen
        # ein Angebot, das man wirklich kaufen kann - eine Naeherung ("kein
        # Angebot", QA-Befund S3) darf hier nicht gewinnen.
        vergleichbar_alle = [k for k in karten if k["vergleichbar"]]
        # P1/TCO-1 (11.09.2026): „Günstigster Gerätepreis“ ist ein Preis
        # OHNE Vertrag - eine Finanzierungssumme (Zuzahlung + alle Raten)
        # ist tarif-abhaengig und keine von beiden. Sie hatte bis P1 die
        # Antwortzeile geführt, wo kein einziger Barpreis gemessen war
        # (Galaxy S26 Ultra 1024: „1.285,00 € (congstar)“), und widersprach
        # damit ihrer eigenen Kartendefinition. Jetzt zaehlen nur noch
        # Barpreise; ist keiner gemessen, fehlt die Zahl ehrlich.
        geraetepreise = [k for k in vergleichbar_alle
                         if k["geraetepreis"] is not None
                         and k.get("geraetepreis_art") != "finanzierung"]
        # F-4a' (PM, 05.09.2026, 19:xx): das Minimum gilt auch ueber die
        # Haendler OHNE Tarifbuendel (Amazon/Expert/Saturn) - sie tragen
        # keine Karte in `karten` (kein Buendel, siehe oben), stehen aber
        # als eigene Haendlerkarte auf DERSELBEN Modelltafel. Gemessener
        # Fall: Saturn 1.179,00 EUR unterbot Vodafones 1.199,90 EUR, ohne
        # dass die Antwortzeile es je gesehen haette - E1-Verstoss, die
        # Leitzahl widersprach ihrer eigenen Nachbarkarte.
        for haendler, eintrag in _haendler_geraetepreise(
                listungen_je_modell.get(mid, [])).items():
            if eintrag is not None:
                geraetepreise.append({"anbieter": haendler,
                                      "geraetepreis": eintrag["preis"]})
        guenstigstes_geraet = (min(geraetepreise,
                                   key=lambda k: k["geraetepreis"])
                               if geraetepreise else None)
        tarifangebote = [k for k in angebote
                         if k["vergleichbar"] and k["gesamt"] is not None]
        guenstigster_tarif = (min(tarifangebote, key=lambda k: k["gesamt"])
                              if tarifangebote else None)
        antwort = {
            "geraetepreis": (guenstigstes_geraet["geraetepreis"]
                             if guenstigstes_geraet else None),
            "geraetepreis_anbieter": (guenstigstes_geraet["anbieter"]
                                      if guenstigstes_geraet else None),
            "tarif_gesamt": (guenstigster_tarif["gesamt"]
                             if guenstigster_tarif else None),
            "tarif_anbieter": (guenstigster_tarif["anbieter"]
                               if guenstigster_tarif else None),
        }

        fertig.append({
            "id": mid,
            "name": name,
            "hersteller": hersteller,
            "titel": titel(hersteller, name),
            "speicher": gruppe["speicher"],
            "karten": karten,
            "referenz": referenz,
            "laufzeiten": laufzeiten,
            "angebote": len(angebote),
            # Wie viele der Angebote NICHT im Vergleich stehen, je Grund -
            # das Band sagt "davon 1 erneuert", nicht "3 Angebote" allein.
            "erneuert": len([k for k in angebote
                             if k["zustand"] in ("refurbished", "b-ware")]),
            "zustand_offen": len([k for k in angebote
                                  if k["zustand"] == "unbekannt"]),
            "spanne": ([min(betraege), max(betraege)] if betraege else []),
            # F-5: NICHT die "Anbieter"-Zahl der Seite (siehe Docstring
            # oben) - nur der Sortier-/Vorgabe-Schluessel dieser Funktion.
            "bundle_anbieter": sorted({k["anbieter"] for k in angebote}),
            "antwort": antwort,
        })

    # Die Reihenfolge des Auswahlfeldes: die meisten Buendel-Anbieter zuerst
    # - dort beantwortet die Seite ihre Tarif-Frage am vollstaendigsten -,
    # dann nach Namen. NICHT nach Preis: eine nach Betrag sortierte
    # Modellliste ist eine Rangliste des Marktes, und der Marktueberblick
    # steht im Katalog.
    fertig.sort(key=lambda m: (-len(m["bundle_anbieter"]), m["name"]))
    return {"modelle": fertig, "vorgabe": _vorgabe(fertig),
            "gesamt": len(fertig), "ohne_zuordnung": ohne_zuordnung}


# --------------------------------------------------------------------------
# Die Reihen fuer G2 - der Preisverlauf je Modell x Anbieter
# --------------------------------------------------------------------------

def historienreihen(eintraege: list, historie, katalog) -> list:
    """Aus der Preishistorie werden Reihen fuer die Verlaufsgrafik.

    Gezeigt wird ausschliesslich der **Barpreis ohne Vertrag**. Einen
    Buendelmonatspreis in dieselbe Euro-Achse zu legen waere genau der
    Befund, mit dem dieses Vorhaben angefangen hat: zwei Groessen unter
    einer Ueberschrift (o2s 721 EUR Ratensumme neben freenets 949 EUR
    Kassenpreis).

    Einen TCO-VERLAUF gibt es hier noch nicht, und er wird auch nicht
    gerechnet: `geraete_tco.json` kennt je Buendel genau einen Stand
    (`first_seen == last_verified == 2026-09-04`). Eine Kurve daraus waere
    interpoliert, und C.2 verbietet die interpolierte Scheinkurve
    ausdruecklich.
    """
    je_sku: dict = {}
    for e in eintraege:
        if e.get("sku_id"):
            je_sku.setdefault(e["sku_id"], (e.get("device_id") or "",
                                            e.get("speicher_gb")))
    reihen = []
    for e in eintraege:
        if e.get("zustand") not in _ZUSTAND:
            continue
        lid = e.get("id") or ""
        # DIESELBE MESSTAG-REGEL WIE IN DER INTERAKTIVEN GRAFIK
        # (`geraete_verlauf.messtage`): ein Tag mit zwei Preisen derselben
        # Listung ist eine Messluecke. Er faellt aus der Kurve und steht in
        # `mehrdeutig`, damit die Grafik ihn BENENNT statt ihn als Pfeil zu
        # zeichnen (QA-Befund B2).
        eindeutig, mehrdeutig = messtage(historie.reihe(lid))
        punkte = [{"datum": t, "betrag": b} for t, b in sorted(eindeutig.items())]
        if len(punkte) < 2 and not mehrdeutig:
            continue
        device_id, speicher = je_sku.get(e.get("sku_id", ""), ("", None))
        reihen.append({
            "name": _name(katalog, device_id, speicher,
                          rueckfall=e.get("sku_id", "")),
            "anbieter": e.get("anbieter", ""),
            "modell_id": modell_schluessel(device_id, speicher),
            "quelle_url": e.get("quelle_url", ""),
            "punkte": punkte,
            "mehrdeutig": [{"datum": t, "betraege": mehrdeutig[t]}
                           for t in sorted(mehrdeutig)]})
    return reihen
