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

import datetime as _dt
import logging
import re
from datetime import date as _datum
from typing import Optional

from ..geraete_model import VERGLEICHBARE_ZUSTAENDE, ZUSTAENDE, normalisiere
from ..tarif_model import Preisphase
from ..tco_model import (
    AKTION_ANSCHLUSS_ERLASSEN,
    AKTION_GERAETERABATT,
    AKTION_ONLINE_VORTEIL,
    AKTION_TARIFRABATT,
    AKTION_TRADE_IN,
    AKTION_WECHSELBONUS,
    POSTEN_ANSCHLUSS,
    POSTEN_BUENDEL,
    POSTEN_LAUFZEIT,
    POSTEN_RABATTE,
    POSTEN_RATE,
    POSTEN_TARIF,
    POSTEN_ZUZAHLUNG,
    TCO_HORIZONT,
    Buendel,
    monatsschnitt,
    phasensumme,
    tco_24,
    zeitraum_vergleichbar,
)
from . import anbieter_farben, geraete_vergleich
from . import geraete_notbremse as notbremse
from .geraete_tco_grafik import anbieter_slug

LAUFZEIT = TCO_HORIZONT
AB_MONAT = TCO_HORIZONT + 1
LABEL_OHNE_LAUFZEIT = "Kosten – Laufzeit nicht gemessen"

DELTA_ANDERE_LAUFZEIT = "andere Laufzeit"

log = logging.getLogger(__name__)

ANBIETER_REIHENFOLGE = ("Telekom", "1&1", "o2", "Vodafone")

EIGEN = "vodafone"

ALT_AB_TAGEN = 3


def alter_in_tagen(abgerufen_am: str, heute: str) -> Optional[int]:
    """Tage zwischen Abruf und heute - oder None, wenn eins der beiden
    Daten fehlt oder unlesbar ist.

    Vergleichsbasis ist `abgerufen_am` JE BÜNDEL. Das Datum wird nie
    geraten (Clean Code 4): fehlt es, ist das Alter „unbekannt“ und
    fällt aus jedem Vergleich heraus - `ist_frisch` behandelt unbekannt
    wie alt, niemals wie frisch.
    """
    if not abgerufen_am or not heute:
        return None
    try:
        return (
            _dt.date.fromisoformat(heute) - _dt.date.fromisoformat(abgerufen_am)
        ).days
    except ValueError:
        return None


def ist_frisch(abgerufen_am: str, heute: str) -> bool:
    """DIE EINE Definition von „frisch“ (Clean Code 7).

    Anzeige (Marke, Ausgrauung), Auswahl (Antwortzeile, Spanne, Bänder,
    Zeitreihe, Katalog) und Sortierung lesen alle diese Funktion - eine
    zweite Frische-Liste wäre zwei Listen, die auseinanderlaufen.
    Ohne `heute` (leerer String) altert nichts: das ist der Modus der
    Tests ohne Datum und jeder Aufruf, der bewusst nicht altert.
    """
    if not heute:
        return True
    alter = alter_in_tagen(abgerufen_am, heute)
    return alter is not None and alter <= ALT_AB_TAGEN


def kurz_datum(iso: str) -> str:
    """„2026-09-16“ -> „16.09.2026“; „“, wenn kein lesbares Datum steht.

    Das kurze Format (kein Monatsname) ist bewusst: `strftime('%B')`
    hinge an der Locale des Rechners und würde in Actions englische
    Monate schreiben. `html._fmt_date_de` umgeht das mit einer Tabelle -
    für die Marken und Hinweise der Alterung reicht die Ziffernform.

    S3b (Diff-Prüfung 21.09.2026): `None` (JSON-null aus einem halben
    Schreibvorgang des Stores) ist KEIN Crash, sondern „unlesbar“ - ein
    fehlender Wert wird nie geraten und wirft die Seite nicht in den
    Notzustand.
    """
    try:
        d = _dt.date.fromisoformat(str(iso or ""))
    except (ValueError, TypeError):
        return ""
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def alt_marke_fuer(abgerufen_am: str) -> str:
    """Der Chip an der alten Zeile: „kein aktueller Stand seit …“.

    Ohne lesbares Datum heißt es „unbekannt“ - nie heute, nie geraten.
    Öffentlich, weil dieselbe Marke seit der A3-Nachbesserung auch der
    Katalog an seinen ab-Preis hängt (Clean Code 1: ein Satz, eine
    Stelle) - der Bündelzeile und der Katalogzeile steht derselbe Text.
    """
    kurz = kurz_datum(abgerufen_am)
    if kurz:
        return f"kein aktueller Stand seit {kurz}"
    return "kein aktueller Stand – Abrufdatum unbekannt"


LEITFRAGE_MODELL = "apple-iphone-17-pro-256"

LEER_GRUND = {
    "Telekom": (
        "Für dieses Modell ist bei Telekom noch kein Bündelpreis "
        "erhoben – die Vergleichszahl folgt mit der nächsten "
        "wöchentlichen Messung."
    ),
    "1&1": (
        "Für dieses Modell ist bei 1&1 kein Bündel erhoben – die "
        "Kategorieseite führt es nicht als eigene Produktkachel."
    ),
    "o2": "Für dieses Modell ist bei o2 kein Bündel erhoben.",
    "Vodafone": (
        "Kein Bündelpreis erhoben, und kein Barpreis dieses "
        "Geräts – ohne beides gibt es keine Vergleichszahl."
    ),
}

_ZUSTAND = VERGLEICHBARE_ZUSTAENDE

ZUSTAND_ETIKETT = {
    "neu": "",
    "refurbished": "erneuert",
    "b-ware": "B-Ware",
    "unbekannt": "Zustand nicht belegt",
}


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
            continue
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
        rest = _SPEICHER_SEGMENT.match(sku[len(gid) + 1 :])
        if rest is None:
            continue
        if treffer is None or len(gid) > len(treffer[0]):
            treffer = (gid, int(rest.group(1)) if rest.group(1) else None)
    return treffer or ("", None)


GRUND_OHNE_ZUORDNUNG = (
    "im Gerätebestand steht keine Listung zu dieser SKU, "
    "und der Katalog kennt das Gerät nicht"
)


def ergaenze_geraete_aus_katalog(geraet_je_sku: dict, buendel, katalog) -> list:
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
            offen.append(
                {
                    "sku_id": sku,
                    "anbieter": getattr(b, "anbieter", ""),
                    "grund": GRUND_OHNE_ZUORDNUNG,
                }
            )
    for o in offen:
        log.warning(
            "TCO: Buendel %s (%s) nicht zugeordnet - %s",
            o["sku_id"],
            o["anbieter"],
            o["grund"],
        )
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
        beleg = {
            "anbieter": e.get("anbieter", ""),
            "betrag": float(preis),
            "quelle_url": e.get("quelle_url", ""),
            "abgerufen_am": e.get("abgerufen_am", ""),
        }
        sku = e.get("sku_id") or ""
        if not sku:
            continue
        je_sku.setdefault(sku, {})
        bisher = je_sku[sku].get(beleg["anbieter"])
        if bisher is None or beleg["betrag"] < bisher["betrag"]:
            je_sku[sku][beleg["anbieter"]] = beleg
    return je_sku


def _geraetepreis(
    barpreis: Optional[dict], zuzahlung: Optional[float], raten_summe: Optional[float]
) -> tuple[Optional[float], Optional[str]]:
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

    Dieselbe Regel wie im Zeitreihen-Graph (G0, bis P2 auch G2):
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
            l
            for l in listungen
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
            continue
        try:
            fertig.append(
                Buendel(
                    sku_id=e.get("sku_id", ""),
                    anbieter=e.get("anbieter", ""),
                    tarif_name=e["tarif_referenz"],
                    buendel_monatlich=float(betrag),
                    laufzeit_monate=e.get("laufzeit_monate"),
                    zustand=e.get("zustand") or "",
                    quelle_url=e.get("quelle_url", ""),
                    abgerufen_am=e.get("abgerufen_am", ""),
                )
            )
        except (TypeError, ValueError) as exc:
            log.warning("Buendel aus Listung %s uebergangen: %s", e.get("id", "?"), exc)
    return fertig


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


_ZERLEGUNG_RATENKATEGORIEN = ("raten", "buendel")
LABEL_RESTSCHULD = "Restschuld nach Monat 24"


def zerlegung_balken(
    bestandteile: list, restbetrag: Optional[float], gesamt: Optional[float]
) -> list:
    """Die Segmente des Zerlegungsbalkens, mit ihrem Breitenanteil `pct`.

    Ohne `gesamt` (die Kennzahl ist nicht belastbar) oder ohne einen
    einzigen Posten gibt es keinen Balken - eine leere Liste, kein Balken
    aus Teilbeträgen ohne Summe (Regel 9: eine Lücke bleibt eine Lücke).

    Review-Fix S3 (mitgenommen): ein Segment mit Betrag exakt 0,00 EUR
    (eine gemessene "keine Zuzahlung"/"kein Anschlusspreis", Clean Code 3
    - 0 ist hier eine Aussage, kein fehlender Wert) bekommt keinen
    eigenen Balkenteil. Der Posten steht textlich ohnehin schon im
    Rechenweg darunter; ein Nullbreiten-Segment wuerde nur durch die
    optische Mindestbreite (D3-CSS-Block) als Phantomstreifen sichtbar.
    """
    if gesamt is None or not bestandteile:
        return []
    rest = round(restbetrag, 2) if restbetrag is not None else 0.0
    segmente = []
    gesplittet = False
    for posten in bestandteile:
        name, betrag = posten["name"], posten["betrag"]
        kategorie = posten["kategorie"]
        if rest and not gesplittet and kategorie in _ZERLEGUNG_RATENKATEGORIEN:
            faellig = round(betrag - rest, 2)
            if faellig < 0:
                log.warning(
                    "zerlegung_balken: restbetrag %.2f EUR groesser als "
                    "der Posten %r (%.2f EUR) - Balken bleibt "
                    "ungezeichnet",
                    rest,
                    name,
                    betrag,
                )
                return []
            if faellig:
                segmente.append(
                    {
                        "name": name,
                        "betrag": faellig,
                        "kategorie": kategorie,
                        "offen": False,
                    }
                )
            segmente.append(
                {
                    "name": LABEL_RESTSCHULD,
                    "betrag": rest,
                    "kategorie": "restschuld",
                    "offen": True,
                }
            )
            gesplittet = True
        elif betrag:
            segmente.append(
                {"name": name, "betrag": betrag, "kategorie": kategorie, "offen": False}
            )
    for seg in segmente:
        seg["pct"] = round(seg["betrag"] / gesamt * 100, 3) if gesamt else 0.0
    return segmente


def label_der_leitzahl(monate: Optional[int]) -> str:
    """ "Kosten über 36 Monate" - das Etikett NENNT den Zeitraum der Zahl.

    Ein Etikett, das 24 sagt, wo die Zahl 36 Monate traegt, ist keine
    Formulierungsfrage: es macht aus einer richtigen Summe eine falsche
    Aussage. Der Zeitraum kommt aus `Tco.leitzahl_monate` - dieselbe
    Zahl, die den Ø/Monat teilt und ueber den Δ-Vergleich entscheidet
    (Clean Code 7).
    """
    if monate is None:
        return LABEL_OHNE_LAUFZEIT
    return f"Kosten über {monate} Monate"


AKTION_NAME = {
    AKTION_TRADE_IN: "Trade-in",
    AKTION_GERAETERABATT: "Geräterabatt im Tarif",
    AKTION_TARIFRABATT: "Grundpreisnachlass",
    AKTION_ANSCHLUSS_ERLASSEN: "Anschlusspreis erlassen",
    AKTION_WECHSELBONUS: "Wechselbonus",
    AKTION_ONLINE_VORTEIL: "Online-Vorteil",
}
AKTION_KURZ = {
    AKTION_TRADE_IN: "mit Altgerät",
    AKTION_WECHSELBONUS: "mit Rufnummernmitnahme",
    AKTION_ONLINE_VORTEIL: "bei Online-Bestellung",
}


def aktionen_der_karte(b: Buendel, heute: str = "") -> tuple[list, Optional[dict]]:
    """Die laufenden Aktionen eines Buendels fuer die Seite - und der eine
    Ueberhang, der an der Zeile steht.

    Abgelaufene Aktionen (`Aktion.gilt_am`) fallen weg: ein Nachlass "bis
    zum 29.09." ist am 30.09. keine Auskunft mehr, sondern eine falsche.
    Der Ueberhang ist die groesste NICHT eingerechnete Aktion mit Betrag -
    die Zahl, um die das Angebot unter einer Bedingung noch sinkt. Eine
    eingerechnete Aktion hat keinen Ueberhang: sie steckt schon in der
    Leitzahl."""
    liste = []
    for a in b.aktionen:
        if not a.gilt_am(heute):
            continue
        liste.append(
            {
                "art": a.art,
                "name": AKTION_NAME.get(a.art, a.art),
                "betrag": a.betrag,
                "betrag_monatlich": a.betrag_monatlich,
                "bedingung": a.bedingung,
                "eingerechnet": a.eingerechnet,
                "gueltig_bis": a.gueltig_bis,
                "quelle_url": a.quelle_url,
            }
        )
    offen = [a for a in liste if not a["eingerechnet"] and a["betrag"]]
    ueberhang = None
    if offen:
        groesste = max(offen, key=lambda a: a["betrag"])
        ueberhang = {
            "betrag": groesste["betrag"],
            "kurz": AKTION_KURZ.get(groesste["art"], groesste["name"]),
        }
    return liste, ueberhang


def _karte(
    b: Buendel,
    tarif: Optional[dict],
    barpreis: Optional[dict],
    katalog,
    geraet_je_sku: dict,
    zustand: str = "unbekannt",
    heute: str = "",
) -> dict:
    """Aus einem Buendel wird eine Karte - gerechnet wird in `tco_model`.

    Diese Funktion addiert keinen Euro. Sie holt die Kennzahl, haengt die
    Belege daran und formt die Pflichtzeilen des Katalogs D.

    TICKET TCO24-1: die Leitzahl ist `tco_24()`, IMMER 24 Monate
    (AUFTRAG_GERAETESEITE.md §3). Bis dahin fuehrte diese Funktion
    `tco_bindung()`, eine Kennzahl ueber die eigene Bindung des Buendels -
    sichtbar als "TCO-36", der deklarierte Fehler dieses Tickets.

    A3: `heute` entscheidet über die Frische der Karte (`ist_frisch`,
    dieselbe Definition wie jede Auswahl). Ohne das Datum altert nichts.
    """
    frisch = ist_frisch(b.abgerufen_am, heute)
    kennzahl = tco_24(b)
    aktionen, aktion_ueberhang = aktionen_der_karte(b, heute)
    monate = kennzahl.leitzahl_monate
    device_id, speicher = geraet_je_sku.get(b.sku_id, ("", None))
    nach_bindung = _phase_ab(tarif, AB_MONAT) if tarif else None

    eff = None
    if barpreis is not None and kennzahl.belastbar and monate:
        eff = round(kennzahl.monatlich - barpreis["betrag"] / monate, 2)
    raten_summe = (
        round(b.geraet_monatsrate * b.laufzeit_monate, 2)
        if (b.geraet_monatsrate is not None and b.laufzeit_monate is not None)
        else None
    )
    if b.geraet_monatsrate is None and b.buendel_monatlich is None:
        offene_raten: Optional[int] = 0
    elif b.laufzeit_monate is None:
        offene_raten = None
    else:
        offene_raten = max(0, b.laufzeit_monate - TCO_HORIZONT)
    geraetepreis, geraetepreis_art = _geraetepreis(
        barpreis, b.geraet_zuzahlung, raten_summe
    )
    bestandteile = _bestandteile_mit_kategorie(kennzahl)
    return {
        "leer_grund": "" if kennzahl.belastbar else _grund(kennzahl),
        "sku_id": b.sku_id,
        "modell_id": modell_schluessel(device_id, speicher),
        "zustand": zustand,
        "zustand_etikett": ZUSTAND_ETIKETT.get(zustand, zustand),
        "vergleichbar": zustand in _ZUSTAND,
        "frisch": frisch,
        "alt_marke": ("" if frisch else alt_marke_fuer(b.abgerufen_am)),
        "slug": anbieter_slug(b.anbieter),
        "anb_farbe": anbieter_farben.farbe_fuer(b.anbieter),
        "geraet": _name(katalog, device_id, speicher, rueckfall=b.sku_id),
        "anbieter": b.anbieter,
        "eigen": _eigen(b.anbieter),
        "tarif": b.tarif_name,
        "tarif_id": b.tarif_id,
        "tarif_id_guete": b.tarif_id_guete,
        "geraetepreis": geraetepreis,
        "geraetepreis_art": geraetepreis_art,
        "label": label_der_leitzahl(monate),
        "laufzeit": LAUFZEIT,
        "leitzahl_monate": monate,
        "ab_monat": AB_MONAT,
        "tarif_bindung": b.tarif_bindung_monate,
        "raten_laufzeit": (
            b.laufzeit_monate
            if (b.geraet_monatsrate is not None or b.buendel_monatlich is not None)
            else None
        ),
        "belastbar": kennzahl.belastbar,
        "gesamt": kennzahl.gesamt if kennzahl.belastbar else None,
        "schnitt_monat": kennzahl.monatlich if kennzahl.belastbar else None,
        "gezahlt_nach_24": (
            round(kennzahl.gesamt - (kennzahl.restbetrag or 0.0), 2)
            if kennzahl.belastbar
            else None
        ),
        "offen_nach_24": (
            kennzahl.restbetrag
            if kennzahl.belastbar and kennzahl.restbetrag is not None
            else None
        ),
        "offene_raten": offene_raten,
        "monatlich": b.tarif_monatlich,
        "buendel_monatlich": b.buendel_monatlich,
        "zuzahlung": b.geraet_zuzahlung,
        "rate": b.geraet_monatsrate,
        "raten_summe": raten_summe,
        "anschlusspreis": b.anschlusspreis,
        "nach_bindung": nach_bindung,
        "eff_ohne_geraet": eff,
        "eff_basis": barpreis,
        "bestandteile": bestandteile,
        "zerlegung": zerlegung_balken(
            bestandteile,
            kennzahl.restbetrag,
            kennzahl.gesamt if kennzahl.belastbar else None,
        ),
        "luecken": [
            l for l in kennzahl.luecken if not (l == POSTEN_RABATTE and aktionen)
        ],
        "boni": [],
        "boni_abzug": kennzahl.rabatte_offen,
        "aktionen": aktionen,
        "aktion_ueberhang": aktion_ueberhang,
        "quelle_url": b.quelle_url,
        "abgerufen_am": b.abgerufen_am,
        "tarif_quelle_url": (tarif or {}).get("dokument_url", ""),
        "naeherung": False,
        **notbremse.felder(b, heute),
        "ab_preis": b.buendel_monatlich is not None,
    }


_GRUND_JE_LUECKE = {
    POSTEN_TARIF: (
        "Der Tarifgrundpreis dieses Bündels ist nicht erhoben – "
        "ohne ihn ist es kein Gesamtpreis, sondern ein "
        "Gerätebetrag."
    ),
    POSTEN_LAUFZEIT: (
        "Die Ratenlaufzeit dieses Bündels ist nicht erhoben – "
        "ohne die Zahl der Monate ergibt der Monatsbetrag "
        "keine Gesamtsumme."
    ),
}


def _grund(kennzahl) -> str:
    """Warum diese Karte keine Zahl traegt - in der Reihenfolge der Ursachen."""
    if POSTEN_TARIF in kennzahl.luecken:
        return _GRUND_JE_LUECKE[POSTEN_TARIF]
    if POSTEN_LAUFZEIT in kennzahl.luecken:
        return _GRUND_JE_LUECKE[POSTEN_LAUFZEIT]
    if kennzahl.gesamt is None:
        return (
            "Zu diesem Bündel ist kein einziger Posten erhoben – es "
            "steht als Angebot da, nicht als Preis."
        )
    return (
        "Die Rechnung ist unvollständig: "
        + ", ".join(kennzahl.luecken)
        + " nicht gemessen."
    )


def _phase_ab(tarif: dict, monat: int) -> Optional[float]:
    """Der Betrag, der im gegebenen Monat laut Pflichtdokument gilt."""
    for phase in tarif.get("preisphasen") or []:
        von = phase.get("von_monat") or 1
        bis = phase.get("bis_monat")
        if von <= monat and (bis is None or monat <= bis):
            betrag = phase.get("betrag")
            return round(float(betrag), 2) if betrag is not None else None
    return None


def _leere_karte(anbieter: str, grund: str = "") -> dict:
    """Ein Anbieter ohne Zahl - mit Namen und mit Begruendung (B.2.5)."""
    return {
        "anbieter": anbieter,
        "eigen": _eigen(anbieter),
        "tarif": "",
        "slug": anbieter_slug(anbieter),
        "anb_farbe": anbieter_farben.farbe_fuer(anbieter),
        "geraetepreis": None,
        "geraetepreis_art": None,
        "label": "",
        "laufzeit": None,
        "leitzahl_monate": None,
        "ab_monat": None,
        "belastbar": False,
        "gesamt": None,
        "schnitt_monat": None,
        "gezahlt_nach_24": None,
        "offen_nach_24": None,
        "offene_raten": 0,
        "monatlich": None,
        "buendel_monatlich": None,
        "zuzahlung": None,
        "rate": None,
        "raten_summe": None,
        "anschlusspreis": None,
        "nach_bindung": None,
        "eff_ohne_geraet": None,
        "eff_basis": None,
        "bestandteile": [],
        "zerlegung": [],
        "luecken": [],
        "boni": [],
        "boni_abzug": 0.0,
        "quelle_url": "",
        "abgerufen_am": "",
        "tarif_quelle_url": "",
        "naeherung": False,
        "leer_grund": grund or LEER_GRUND.get(anbieter, ""),
        "ab_preis": False,
        "frisch": True,
        "alt_marke": "",
        "zustand": "",
        "zustand_etikett": "",
        "vergleichbar": False,
        "sku_id": "",
        "modell_id": "",
        "geraet": "",
        "tarif_id": "",
        "tarif_id_guete": "",
        "tarif_bindung": None,
        "raten_laufzeit": None,
    }


def phasen_aus_tarifsatz(tarif: Optional[dict]) -> list:
    """Die Preisphasen aus einem Tarifsatz des Bestands (`tarife.jsonl`).

    A1 (20.09.2026): die EINE Stelle, an der ein Tarif-Dict zu Preisphasen
    wird. `_vodafone_referenz`, die Bündel-Anreicherung
    (`geraete_tco_view.aufbereiten`) und die Zeitreihe lesen dieselben
    Phasen - sonst rechneten drei Stellen denselben Tarif-Stamm verschieden.
    Ein Betrag ohne Wert ist keine Phase (None heisst hier "nicht im
    Blatt", nicht "0 EUR"); ohne Phasen bleibt eine leere Liste, und die
    Rechnung faellt auf den flachen Grundpreis zurueck.
    """
    return [
        Preisphase(
            von_monat=p.get("von_monat") or 1,
            bis_monat=p.get("bis_monat"),
            betrag=p.get("betrag"),
        )
        for p in ((tarif or {}).get("preisphasen") or [])
        if p.get("betrag") is not None
    ]


_PREIS_TOLERANZ = 0.005


def phasen_fuer_buendel(
    tarif: Optional[dict], tarif_monatlich: Optional[float]
) -> list:
    """Phasen des Blatts - nur, wenn sie zur MESSUNG am Bündel passen.

    QA-Fix (20.09.2026, Prüfer-Befund "hoch"): das Blatt beschreibt den
    Tarif OHNE den geräteabhängigen Zuschlag - Vodafone Mobil XS steht mit
    29,95 EUR im Blatt, das Bündel mit Premium-Smartphone misst 31,95 EUR
    (alle drei Mobil-Tarife, 473 Bündel). Die Anreicherung hob die Messung
    still auf: die Karte sagte "monatlich 31,95 EUR", die Postenliste
    rechnete 24 x 29,95 EUR, und die Leitzahl war mit der eigenen Karte
    nicht mehr nachrechenbar.

    Die Regel: Die Phasen beschreiben das Bündel nur, wenn die gemessene
    Monatsrate in ihrer Preisspanne liegt (einschließlich - der Shop nennt
    bei "12 Monate 10 EUR, danach 20 EUR" den Rabatt- oder den Normalpreis,
    je nach Seite). Liegt die Messung darüber oder darunter, spricht das
    Blatt von einem anderen Angebot, und die MESSUNG gewinnt flach - nie
    umgekehrt. Ohne Messung (None) gibt es keinen Widerspruch, dann gelten
    die Phasen; ohne Phasen bleibt es bei der leeren Liste.
    """
    phasen = phasen_aus_tarifsatz(tarif)
    if not phasen or tarif_monatlich is None:
        return phasen
    betraege = [p.betrag for p in phasen]
    if (
        min(betraege) - _PREIS_TOLERANZ
        <= tarif_monatlich
        <= max(betraege) + _PREIS_TOLERANZ
    ):
        return phasen
    return []


def _vodafone_referenz(
    referenzen: list, tarife: dict, barpreise_der_sku: dict
) -> Optional[dict]:
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

    Der Tarifbetrag ist phasengewichtet (`tco_model.phasensumme`, seit A1
    Teil des Moduls der Leitzahl) - dieselbe Rechnung wie auf der
    Tarifseite und an EINER Stelle. Steht im Blatt eine Phase fuer Monat 25
    und danach, wird sie gelesen; steht keine, gilt der Grundpreis fort,
    und die Karte sagt es.
    """
    vodafone = [
        r
        for r in referenzen
        if _eigen(getattr(r, "anbieter", ""))
        and getattr(r, "tarif_sim_only_monatlich", None) is not None
    ]
    geraet = (barpreise_der_sku or {}).get("Vodafone")
    if not vodafone or geraet is None:
        return None
    referenz = min(vodafone, key=lambda r: r.tarif_sim_only_monatlich)
    tarif = tarife.get(referenz.tarif_id) or {}
    phasen = phasen_fuer_buendel(tarif, referenz.tarif_sim_only_monatlich)

    monate = TCO_HORIZONT
    summe = phasensumme(phasen, monate) if phasen else None
    abgedeckt = 0
    for phase in phasen:
        abgedeckt = max(
            abgedeckt, monate if phase.bis_monat is None else phase.bis_monat
        )
    fortgeschrieben = abgedeckt < monate
    if summe is None:
        summe = round(referenz.tarif_sim_only_monatlich * monate, 2)
        fortgeschrieben = fortgeschrieben or not phasen
    gesamt = round(summe + geraet["betrag"], 2)
    return {
        "nach_bindung": _phase_ab(tarif, AB_MONAT),
        "tarif": referenz.tarif_name,
        "tarif_id": referenz.tarif_id,
        "monatlich": referenz.tarif_sim_only_monatlich,
        "tarif_summe": summe,
        "tarif_quelle_url": referenz.quelle_url,
        "tarif_abgerufen_am": referenz.abgerufen_am,
        "geraet_betrag": geraet["betrag"],
        "geraet_art": "barpreis",
        "geraet_quelle_url": geraet.get("quelle_url", ""),
        "geraet_abgerufen_am": geraet.get("abgerufen_am", ""),
        "monate": monate,
        "tarif_monate": monate,
        "gesamt": gesamt,
        "schnitt_monat": monatsschnitt(gesamt, monate),
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
        "tarif": karte["tarif"],
        "tarif_id": karte.get("tarif_id", ""),
        "monatlich": karte.get("monatlich") or karte.get("buendel_monatlich"),
        "tarif_summe": None,
        "tarif_quelle_url": karte.get("tarif_quelle_url", ""),
        "tarif_abgerufen_am": karte.get("abgerufen_am", ""),
        "geraet_betrag": karte.get("geraetepreis"),
        "geraet_art": karte.get("geraetepreis_art"),
        "geraet_quelle_url": karte.get("quelle_url", ""),
        "geraet_abgerufen_am": karte.get("abgerufen_am", ""),
        "monate": karte["leitzahl_monate"],
        "gesamt": karte["gesamt"],
        "schnitt_monat": karte["schnitt_monat"],
        "fortgeschrieben": False,
        "aus_buendel": True,
    }


def referenz_ist_frisch(ref: Optional[dict], heute: str) -> bool:
    """Die Frische der REFERENZ - aus ihren Belegen, nicht aus der Uhr.

    S2-1 (Diff-Prüfung 21.09.2026): Eine Referenz aus einem echten
    eigenen Bündel ist so frisch wie ihre Quelle - `modelle()` wählt sie
    nur aus frischen eigenen Karten (A3). Die NÄHERUNG hat zwei
    GEMESSENE Summanden mit eigenen Abrufdaten, Tarifblatt und Barpreis;
    sie gilt nur als frisch, wenn BEIDE frisch sind. Eine Näherung aus
    einem Blatt von heute und einem Barpreis vom 08.09. ist keine Zahl
    von heute (der Prüfer-Repro: 999,00 € Barpreis, 12 Tage alt, ohne
    Altkennzeichnung in der Antwortzeile). Ohne `heute` altert nichts -
    der Kompatibilitätsmodus wie überall.
    """
    if not ref:
        return False
    if ref.get("aus_buendel"):
        return True
    return ist_frisch(ref.get("tarif_abgerufen_am") or "", heute) and ist_frisch(
        ref.get("geraet_abgerufen_am") or "", heute
    )


def _referenz_stand(ref: dict) -> str:
    """Das Datum der Marke einer alten Näherung - ISO oder „“.

    Der späteste Tag, an dem noch BEIDE Summanden gestimmt haben, ist
    der ÄLTERE der zwei Abrufdaten. Ist eines unlesbar, ist der Stand
    unbekannt („seit <Datum>“ hieße, der andere Summand hätte noch
    gestimmt - geraten wird nichts, Clean Code 4).
    """
    daten = [ref.get("tarif_abgerufen_am") or "", ref.get("geraet_abgerufen_am") or ""]
    try:
        return str(min(_dt.date.fromisoformat(d) for d in daten))
    except ValueError:
        return ""


def _referenzkarte(ref: dict, heute: str = "") -> dict:
    """Die Referenzrechnung als Karte - sichtbar als Naeherung markiert.

    S2-1 (Diff-Prüfung 21.09.2026): die Frische der Karte kommt aus den
    BEIDEN Belegen der Näherung (`referenz_ist_frisch`), nicht mehr aus
    dem pauschalen Default der Leerkarte. Eine alte Näherung bleibt
    stehen (Regel 9) - ausgegraut, mit Marke - und fällt aus Antwort-
    zeile und jedem Delta-Bezug (dort filtert `frisch` sie heraus).
    """
    karte = _leere_karte("Vodafone")
    karte.update(
        {
            "leer_grund": "",
            "tarif": ref["tarif"],
            "tarif_id": ref.get("tarif_id", ""),
            "label": label_der_leitzahl(ref["tarif_monate"]),
            "ab_monat": AB_MONAT,
            "laufzeit": ref["tarif_monate"],
            "leitzahl_monate": ref["tarif_monate"],
            "fenster": ref["monate"],
            "belastbar": True,
            "naeherung": True,
            "geraetepreis": ref["geraet_betrag"],
            "geraetepreis_art": ref.get("geraet_art"),
            "zustand": "neu",
            "zustand_etikett": "",
            "vergleichbar": True,
            "gesamt": ref["gesamt"],
            "schnitt_monat": ref["schnitt_monat"],
            "monatlich": ref["monatlich"],
            "gezahlt_nach_24": ref["gesamt"],
            "tarif_bindung": ref["tarif_monate"],
            "nach_bindung": ref.get("nach_bindung"),
            "bestandteile": [
                {
                    "name": "Gerät ohne Vertrag · Barpreis",
                    "betrag": ref["geraet_betrag"],
                    "kategorie": "einmalig",
                },
                {
                    "name": f"Tarif · {ref['tarif_monate']} Monate {ref['tarif']}",
                    "betrag": ref["tarif_summe"],
                    "kategorie": "tarif",
                },
            ],
            "luecken": [POSTEN_ANSCHLUSS],
            "quelle_url": ref["geraet_quelle_url"],
            "abgerufen_am": ref["geraet_abgerufen_am"],
            "tarif_quelle_url": ref["tarif_quelle_url"],
            "referenz": ref,
        }
    )
    karte["offen_nach_24"] = 0.0
    karte["zerlegung"] = zerlegung_balken(karte["bestandteile"], 0.0, karte["gesamt"])
    frisch = referenz_ist_frisch(ref, heute)
    karte["frisch"] = frisch
    karte["alt_marke"] = "" if frisch else alt_marke_fuer(_referenz_stand(ref))
    return karte


def _wesentlich(differenz: float, bezug: float) -> bool:
    """ODER, nicht UND - bei 200 EUR sind 15 EUR viel und 3 Prozent wenig."""
    abstand = abs(differenz)
    prozent = (abstand / bezug * 100) if bezug else 0.0
    return (
        prozent >= geraete_vergleich.WESENTLICH_PROZENT
        or abstand >= geraete_vergleich.WESENTLICH_EURO
    )


def _delta_faellig(karte: dict, referenz: Optional[dict]) -> bool:
    """Steht dieser Zeile ueberhaupt ein Abstand zur Referenz zu?

    DIE EINE Menge (Clean Code 7): `_delta` (die Zahl) und `delta_zustand`
    (der benannte Zustand, wo es keine geben darf) lesen dieselbe
    Vorauswahl. Zwei eigene Bedingungslisten waeren zwei Definitionen von
    "vergleichbare Zeile", und eine Leerkarte oder die Referenz selbst
    bekaeme irgendwann ein "andere Laufzeit" an die Δ-Spalte.
    """
    if referenz is None or not karte["belastbar"] or karte["naeherung"]:
        return False
    if karte["gesamt"] is None or not karte["laufzeit"]:
        return False
    if not karte.get("frisch", True):
        return False
    if not karte.get("vergleichbar", True):
        return False
    if karte["eigen"]:
        return False
    return True


def gleicher_horizont(karte: dict, referenz: Optional[dict]) -> bool:
    """Tragen Zeile und Referenz denselben Zeitraum? DAS EINE TOR.

    Der ganze Weg zu einem Delta laeuft hier durch - Euro-Delta
    (`_delta`), benannter Ersatzzustand (`delta_zustand`) und jeder
    Leser, der eine Kartenzeile gegen die Referenz stellt (Radar, Alarm,
    Export): wer ein Vorzeichen zeigen will, fragt DIESE Funktion. Sie
    liest die zwei Felder und wendet die Regel nicht selbst an - die
    steht in `tco_model.zeitraum_vergleichbar`, neben der Rechnung, die
    die Zeitraeume bestimmt (P0-B-h1).

    Verglichen werden die Zeitraeume, die die zwei ZAHLEN tragen
    (`leitzahl_monate` gegen `referenz["monate"]`) - nicht die
    Tariflaufzeit der Rechnung, die auf jeder Karte 24 ist. Genau diese
    Verwechslung hat 1&1s 36-Monats-Buendel ein Euro-Delta gegen eine
    24-Monats-Referenz gegeben (P0-B-fix2, Befund 3).
    """
    if referenz is None:
        return False
    return zeitraum_vergleichbar(karte.get("leitzahl_monate"), referenz.get("monate"))


def delta_zustand(karte: dict, referenz: Optional[dict]) -> Optional[dict]:
    """Der BENANNTE Zustand einer Zeile, die kein Delta tragen DARF.

    `{"kurz": <Δ-Spalte>, "satz": <ein Satz im Rechenweg>}` - oder `None`,
    wo der Strich der Δ-Spalte weiter richtig ist (keine Referenz, kein
    Angebot, eigenes Angebot, altes oder erneuertes Geraet: alles Faelle,
    die `_delta_faellig` schon aussortiert).

    Der Strich heisst "kein Angebot" (A2). Eine Zeile MIT Angebot, deren
    Zahl aber einen anderen Zeitraum traegt als die Referenz, ist kein
    fehlendes Angebot und auch kein Abstand von null - sie ist
    unvergleichbar, und das steht als Wort da (Clean Code 4). Sie traegt
    damit auch keinen numerischen Δ-Sortierschluessel und faellt aus der
    Rangfolge nach Δ heraus (`data-delta` bleibt leer).
    """
    if not _delta_faellig(karte, referenz):
        return None
    if gesperrt := notbremse.zustand(karte):
        return gesperrt
    if gleicher_horizont(karte, referenz):
        return None
    monate = karte.get("leitzahl_monate")
    dieses = (
        f"{monate} Monate" if monate is not None else "eine nicht gemessene Laufzeit"
    )
    return {
        "kurz": DELTA_ANDERE_LAUFZEIT,
        "satz": (
            f"Kein Abstand zur Vodafone-Referenz: diese Zahl trägt "
            f"{dieses}, die Referenz {referenz['monate']} Monate."
        ),
    }


def _delta(karte: dict, referenz: Optional[dict]) -> Optional[dict]:
    """Euro primaer, Prozent sekundaer - und nur bei gleichem Zeitraum.

    Ueber Laufzeiten hinweg gibt es kein Euro-Delta (A5.4). Wo die Zahl
    der Karte 36 Monate traegt und die Referenz 24, waere die Differenz
    die Laufzeit und nicht der Preis.

    P0-B-fix2: dann auch kein monatliches Delta (36-Monats-Summe durch 24
    ist kein Monatspreis), sondern der Zustand aus `delta_zustand`. Unter
    der Wesentlichkeits-Schwelle ist es `ungefaehr` (A2), nicht fehlend.
    """
    if not _delta_faellig(karte, referenz) or not notbremse.zaehlt(karte):
        return None
    if not gleicher_horizont(karte, referenz):
        return None
    betrag = round(karte["gesamt"] - referenz["gesamt"], 2)
    monatlich = round(karte["schnitt_monat"] - referenz["schnitt_monat"], 2)
    ungefaehr = not _wesentlich(betrag, referenz["gesamt"])
    return {
        "ungefaehr": ungefaehr,
        "betrag": betrag,
        "prozent": (
            None
            if ungefaehr or not referenz["gesamt"]
            else round(abs(betrag) / referenz["gesamt"] * 100, 1)
        ),
        "monatlich": monatlich,
        "guenstiger": betrag < 0,
        "abstand": abs(betrag),
        "gleiche_laufzeit": True,
        "referenz_tarif": referenz["tarif"],
        "referenz_datum": referenz["tarif_abgerufen_am"],
        "referenz_gesamt": referenz["gesamt"],
    }


def _rang(karte: dict) -> tuple:
    """Default-Sortierung: Ø/Monat aufsteigend (A5.3).

    Das ist das einzige Mass, das 24- und 36-Monats-Angebote in EINER
    Rangfolge fuehren darf. Karten ohne Zahl stehen hinten - sie sind kein
    guenstigstes Angebot, sondern eine Luecke. Dasselbe gilt seit A3 für
    ALTE Angebote: die Zeile bleibt, aber hinter jeder frischen.
    """
    return (
        not karte["belastbar"],
        not karte.get("vergleichbar", True),
        karte["naeherung"],
        not karte.get("frisch", True),
        karte["schnitt_monat"] if karte["schnitt_monat"] is not None else 9e9,
        karte["anbieter"],
    )


def _neuigkeit(karte: dict) -> int:
    """`abgerufen_am` als ordnungsfeste Zahl, absteigend verglichen.

    Ein unlesbares oder leeres Datum zaehlt als aelteste Messung (0): eine
    Karte ohne Datum gewinnt den Slot nie, sie verliert ihn nur - ein
    fehlender Wert ist keine Aussage ueber die Aktualitaet (Clean Code 3).
    """
    try:
        return _datum.fromisoformat(
            (karte.get("abgerufen_am") or "").strip()
        ).toordinal()
    except ValueError:
        return 0


def _angebot_rang(karte: dict) -> tuple:
    """Die Angebots-Dedupe in `modelle()`: QUELLE vor DATUM vor Preis.

    Einem Anbieter mit Bündel-Adapter steht dasselbe Angebot ZWEIMAL im
    Bestand - als Listung (nur der Monatsbetrag) und als gemessenes Bündel
    (mit Einmalzahlung, Bereitstellungsgebühr und tarif_id). Die Listung
    kann die billigere Karte sein, weil ihr Posten FEHLEN; sie darf das
    gemessene Angebot deshalb nicht verdraengen.

    A2 (20.09.2026), die Stufe dahinter: das AKTUELLSTE Datum vor dem
    Preis. Der Store überschreibt Bündel und löscht keins - eine Messung,
    die seit vierzehn Läufen nie wieder bestätigt wurde, kann im selben
    Slot billiger sein als die täglich gemessenen Farben (iPhone 17
    256 GB: 0,99/26,00 vom 06.09. gegen 1,00/30,00 vom 20.09.) und dann
    als billigste eigene Karte die Referenz stellen. Erst bei gleichem
    Datum - oder gleich unbekanntem - entscheidet wieder der Preis.

    A3 darüber (20.09.2026): FRISCHE vor Quelle und Datum - ein Angebot
    jenseits von ALT_AB_TAGEN verliert die Dedupe an eine frische Listung
    desselben Angebots; A2 bleibt Tiebreaker INNERHALB der Frische und
    einziger Anker im Modus `heute=""` (nichts altert, das aktuellste Datum
    entscheidet vor dem Preis). Gleich nach der Frische die Notbremse: eine
    billigere Schätzung verdrängt kein gemessenes Angebot.
    """
    return (
        not karte.get("frisch", True),
        not notbremse.zaehlt(karte),
        1 if karte.get("aus_listung") else 0,
        -_neuigkeit(karte),
        karte["schnitt_monat"] if karte["schnitt_monat"] is not None else 9e9,
    )


LAUFZEIT_STANDARD = 24


def laufzeit_wahl(karten: list) -> Optional[dict]:
    """Der Laufzeit-Filter eines Modells (P3-E2) - und je Karte, unter
    welcher Wahl sie sichtbar ist (`k["laufzeit_sichtbar"]`).

    Die Wahl blendet nicht stumpf alles aus, was nicht passt: dann
    verschwaenden bei "24 Monate" Telekom, o2 und 1&1, die heute nur
    36 Raten anbieten (Fallstrick 16: gemessen, keine Erfassungsluecke -
    und selbst wenn, waere Ausblenden die falsche Antwort). Stattdessen
    gilt je Angebot (Anbieter, Tarif, Zustand): die gewaehlte Laufzeit,
    wenn es sie gibt, sonst die naechstgelegene (bei Gleichstand die
    kuerzere). Jede Zeile nennt ihre Ratenzahl selbst.

    Karten ohne Ratenlaufzeit (Referenzrechnung, Barpreis-Angebote,
    Platzhalter) gehoeren zu keiner Wahl und bleiben immer sichtbar
    (`laufzeit_sichtbar` leer). Rueckgabe `None`, wenn das Modell keine
    zwei Laufzeiten fuehrt - dann gibt es nichts zu waehlen.
    """
    optionen = sorted({k["raten_laufzeit"] for k in karten if k.get("raten_laufzeit")})
    for k in karten:
        k["laufzeit_sichtbar"] = ""
    if len(optionen) < 2:
        return None
    gruppen: dict = {}
    for k in karten:
        if k.get("raten_laufzeit"):
            schluessel = (k["anbieter"], k.get("tarif"), k.get("zustand"))
            gruppen.setdefault(schluessel, []).append(k)
    for gruppe in gruppen.values():
        vorhanden = sorted({k["raten_laufzeit"] for k in gruppe})
        sichtbar: dict = {lz: [] for lz in vorhanden}
        for wahl in optionen:
            passend = min(vorhanden, key=lambda lz: (abs(lz - wahl), lz))
            sichtbar[passend].append(str(wahl))
        for k in gruppe:
            k["laufzeit_sichtbar"] = " ".join(sichtbar[k["raten_laufzeit"]])
    start = (
        LAUFZEIT_STANDARD
        if LAUFZEIT_STANDARD in optionen
        else min(optionen, key=lambda lz: (abs(lz - LAUFZEIT_STANDARD), lz))
    )
    return {"optionen": optionen, "start": start}


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
        if modell["id"] == LEITFRAGE_MODELL and len(modell["bundle_anbieter"]) >= 2:
            return modell["id"]
    return modelle[0]["id"] if modelle else ""


def modelle(
    buendel: list,
    listungen: list,
    referenzen: list,
    tarife: dict,
    katalog,
    heute: str = "",
) -> dict:
    """Alle Modelle mit mindestens einem Buendel, je Modell vier Anbieter.

    Rueckgabe:
        modelle         [{id, name, hersteller, speicher, karten, referenz,
                          laufzeiten, spanne, bundle_anbieter}]; `spanne` und
                          der günstigste Tarif aus derselben Menge (zaehlt)
        vorgabe        die ID des Modells, das ohne Klick sichtbar ist
        ohne_zuordnung  Buendel, deren SKU weder eine Listung noch ein
                        Katalogeintrag aufloest - mit Grund, nie als Modell

    A3: `heute` (Datum der Ausgabe, "YYYY-MM-DD") schaltet die Alterung
    ein - `ist_frisch` entscheidet dann je Bündel über „ab“-Preis, Delta
    und Ranking. Ohne das Datum (leerer String) altert nichts; die Seite
    rendert in Production immer mit dem Datum des Berichts.
    """
    geraet_je_sku: dict = {}
    for e in listungen:
        if e.get("sku_id"):
            geraet_je_sku.setdefault(
                e["sku_id"], (e.get("device_id") or "", e.get("speicher_gb"))
            )
    ohne_zuordnung = ergaenze_geraete_aus_katalog(geraet_je_sku, buendel, katalog)
    belege = barpreise(listungen)
    zustaende = _zustand_je_listung(listungen)

    listungen_je_modell: dict[str, list] = {}
    for e in listungen:
        mid_e = modell_schluessel(e.get("device_id"), e.get("speicher_gb"))
        listungen_je_modell.setdefault(mid_e, []).append(e)

    alle = list(buendel) + buendel_aus_listungen(listungen)
    listung_ids = {id(b) for b in alle[len(buendel) :]}
    gruppen: dict = {}
    for b in alle:
        if not isinstance(b, Buendel) or b.ohne_geraet:
            continue
        if b.sku_id not in geraet_je_sku:
            continue
        device_id, speicher = geraet_je_sku[b.sku_id]
        mid = modell_schluessel(device_id, speicher)
        tarif = tarife.get(b.tarif_id) if b.tarif_id else None
        karte = _karte(
            b,
            tarif,
            _barpreis_fuer(belege.get(b.sku_id, {}), b.anbieter),
            katalog,
            geraet_je_sku,
            zustand=zustand_des_buendels(b, zustaende),
            heute=heute,
        )
        if id(b) in listung_ids:
            karte["aus_listung"] = True
        gruppen.setdefault(
            mid,
            {
                "id": mid,
                "device_id": device_id,
                "speicher": speicher,
                "karten": [],
                "skus": set(),
            },
        )
        gruppen[mid]["karten"].append(karte)
        gruppen[mid]["skus"].add(b.sku_id)

    fertig = []
    for mid, gruppe in gruppen.items():
        karten = gruppe["karten"]
        je_angebot: dict = {}
        for k in karten:
            schluessel = (k["anbieter"], k["tarif"], k["raten_laufzeit"], k["zustand"])
            bisher = je_angebot.get(schluessel)
            if bisher is None or _angebot_rang(k) < _angebot_rang(bisher):
                je_angebot[schluessel] = k
        karten = sorted(je_angebot.values(), key=_rang)

        belege_modell: dict = {}
        for sku in gruppe["skus"]:
            for anbieter, beleg in belege.get(sku, {}).items():
                bisher = belege_modell.get(anbieter)
                if bisher is None or beleg["betrag"] < bisher["betrag"]:
                    belege_modell[anbieter] = beleg

        laufzeiten = sorted(
            {k["raten_laufzeit"] for k in karten if k["raten_laufzeit"]}
        )
        eigene = [
            k
            for k in filter(notbremse.zaehlt, karten)
            if k["eigen"] and k["belastbar"] and k["vergleichbar"] and k["frisch"]
        ]
        naeherung = None
        if eigene:
            referenz = _referenz_aus_buendel(min(eigene, key=lambda k: k["gesamt"]))
        else:
            referenz = _vodafone_referenz(referenzen, tarife, belege_modell)
            naeherung = referenz
        referenz_aktuell = referenz_ist_frisch(referenz, heute)
        for k in karten:
            massstab = referenz if referenz_aktuell else None
            k["delta"] = _delta(k, massstab)
            k["delta_zustand"] = delta_zustand(k, massstab)

        vorhanden = {k["anbieter"] for k in karten}
        if naeherung is not None and not any(k["eigen"] for k in karten):
            karten.append(_referenzkarte(naeherung, heute))
            vorhanden.add("Vodafone")
        for anbieter in ANBIETER_REIHENFOLGE:
            if anbieter not in vorhanden:
                karten.append(_leere_karte(anbieter))

        angebote = [k for k in karten if k["belastbar"] and not k["naeherung"]]
        tarifangebote = [
            k
            for k in filter(notbremse.zaehlt, angebote)
            if k["vergleichbar"] and k["frisch"] and k["gesamt"] is not None
        ]
        betraege = [k["gesamt"] for k in tarifangebote]
        name = _name(katalog, gruppe["device_id"], gruppe["speicher"], rueckfall=mid)
        hersteller = _hersteller(katalog, gruppe["device_id"])
        katalog_eintrag = katalog.nach_id(gruppe["device_id"]) if katalog else None

        vergleichbar_alle = [k for k in karten if k["vergleichbar"]]
        geraetepreise = [
            k
            for k in vergleichbar_alle
            if k["geraetepreis"] is not None
            and k.get("geraetepreis_art") != "finanzierung"
            and k.get("frisch", True)
        ]
        for haendler, eintrag in _haendler_geraetepreise(
            listungen_je_modell.get(mid, [])
        ).items():
            if eintrag is not None and ist_frisch(
                eintrag.get("abgerufen_am", ""), heute
            ):
                geraetepreise.append(
                    {"anbieter": haendler, "geraetepreis": eintrag["preis"]}
                )
        guenstigstes_geraet = (
            min(geraetepreise, key=lambda k: k["geraetepreis"])
            if geraetepreise
            else None
        )
        guenstigster_tarif = (
            min(tarifangebote, key=lambda k: k["gesamt"]) if tarifangebote else None
        )
        antwort = {
            "geraetepreis": (
                guenstigstes_geraet["geraetepreis"] if guenstigstes_geraet else None
            ),
            "geraetepreis_anbieter": (
                guenstigstes_geraet["anbieter"] if guenstigstes_geraet else None
            ),
            "tarif_gesamt": (
                guenstigster_tarif["gesamt"] if guenstigster_tarif else None
            ),
            "tarif_anbieter": (
                guenstigster_tarif["anbieter"] if guenstigster_tarif else None
            ),
        }

        alte = [k for k in karten if k.get("sku_id") and not k["frisch"]]
        alt_seit = max(
            (
                k.get("abgerufen_am") or ""
                for k in alte
                if kurz_datum(k.get("abgerufen_am") or "")
            ),
            default="",
        )
        alles_alt = bool(alte) and not any(
            k["frisch"] for k in karten if k.get("sku_id")
        )
        if alles_alt and alt_seit:
            alt_hinweis = (
                f"Kein aktueller Bündel-Stand seit dem "
                f"{kurz_datum(alt_seit)} – alle Zeilen dieses "
                f"Modells sind älter als {ALT_AB_TAGEN} Tage."
            )
        elif alles_alt:
            alt_hinweis = (
                "Kein aktueller Bündel-Stand – das Abrufdatum "
                "dieser Bündel ist unbekannt, ihre Werte zählen "
                "nicht in den Vergleich."
            )
        else:
            alt_hinweis = ""

        fertig.append(
            {
                "id": mid,
                "name": name,
                "hersteller": hersteller,
                "titel": titel(hersteller, name),
                "auto": (katalog_eintrag.auto if katalog_eintrag else ""),
                "speicher": gruppe["speicher"],
                "karten": karten,
                "referenz": referenz,
                "laufzeiten": laufzeiten,
                "laufzeit_wahl": laufzeit_wahl(karten),
                "angebote": len(angebote),
                "erneuert": len(
                    [k for k in angebote if k["zustand"] in ("refurbished", "b-ware")]
                ),
                "zustand_offen": len(
                    [k for k in angebote if k["zustand"] == "unbekannt"]
                ),
                "spanne": ([min(betraege), max(betraege)] if betraege else []),
                "bundle_anbieter": sorted(
                    {k["anbieter"] for k in angebote if k["frisch"]}
                ),
                "alles_alt": alles_alt,
                "alt_seit": alt_seit,
                "alt_hinweis": alt_hinweis,
                "antwort": antwort,
            }
        )

    fertig.sort(key=lambda m: (-len(m["bundle_anbieter"]), m["name"]))
    return {
        "modelle": fertig,
        "vorgabe": _vorgabe(fertig),
        "gesamt": len(fertig),
        "ohne_zuordnung": ohne_zuordnung,
    }
