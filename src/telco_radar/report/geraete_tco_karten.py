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

from . import anbieter_farben, geraete_vergleich
from .geraete_tco_grafik import anbieter_slug
from ..geraete_model import VERGLEICHBARE_ZUSTAENDE, ZUSTAENDE, normalisiere
from ..tarif_model import Preisphase
from ..tco_model import (POSTEN_ANSCHLUSS, POSTEN_BUENDEL, POSTEN_LAUFZEIT,
                         POSTEN_RATE, POSTEN_TARIF, POSTEN_ZUZAHLUNG,
                         TCO_HORIZONT, Buendel, monatsschnitt, phasensumme,
                         tco_24, zeitraum_vergleichbar)

# Ticket TCO24-1 (08.09.2026) stellte die Tafel auf `tco_24()` und den
# festen 24-Monats-Horizont; A1 (20.09.2026) hat dieselbe Funktion auf die
# vollstaendige Rechnung umgestellt - ALLE Geräteraten (auch die Restschuld
# nach Monat 24, in der Zahl UND daneben ausgewiesen) und den Tarif
# PHASENGEWICHTET, wo der Tarifbestand Preisphasen nennt.

# Die TARIFLAUFZEIT der Rechnung - keine Variable mehr, seit die Norm
# "Immer 24 Monate" sagt. Sie ist NICHT der Zeitraum, den die Leitzahl
# traegt, und seit P0-B-h1 auch nicht mehr der Teiler des Ø/Monat: bei
# einem zusammengelegten Buendelmonatspreis (1&1) laeuft dieser EINE
# Betrag ueber seine eigene Laufzeit und traegt Tarif und Geraet
# zusammen. Diesen Zeitraum bestimmt `tco_model.tco_24` an der Stelle,
# die die Monate zaehlt, und liefert ihn als `Tco.leitzahl_monate` - die
# Kartenschicht LIEST ihn und rechnet ihn nie nach.
LAUFZEIT = TCO_HORIZONT
# A1 (20.09.2026): das Etikett der Leitzahl ist der deutsche Satz statt
# der Kurzform - "Kosten über 24 Monate" sagt einem Manager ohne
# Technik-Hintergrund, was die Zahl bedeutet; "TCO-24" sagt es nur denen,
# die die Abkürzung bereits kennen.
#
# P0-B-fix2: die KONSTANTE `LABEL = "Kosten über 24 Monate"` ist gefallen.
# Das Etikett haengt am Zeitraum der jeweiligen Zahl und wird deshalb
# gebaut (`label_der_leitzahl`) - eine Konstante daneben waere die zweite
# Beschriftungsregel, die genau den Widerspruch aus Befund 3 erzeugt hat.
#
# "ab Monat 25" - der erste Monat NACH dem festen Horizont. F5, Katalog D.
AB_MONAT = TCO_HORIZONT + 1
# Das Etikett einer Zahl, deren Zeitraum nicht gemessen ist. Sie erscheint
# nicht: ohne Ratenlaufzeit ist die Kennzahl unbelastbar (`tco_24` fuehrt
# `POSTEN_LAUFZEIT`), und die Zeile zeigt ihre benannte Luecke. Das
# Etikett steht hier, damit KEIN Weg eine Zahl mit "über 24 Monate"
# beschriftet, deren Laufzeit niemand gemessen hat (P0-B-fix2).
LABEL_OHNE_LAUFZEIT = "Kosten – Laufzeit nicht gemessen"

# Der BENANNTE Δ-Zustand einer Zeile, deren Leitzahl einen anderen
# Zeitraum traegt als die Vodafone-Referenz (P0-B-fix2). Der Strich der
# Δ-Spalte heisst "kein Angebot" (A2) und eine Zahl waere hier eine
# Behauptung: 1&1s 1.927,54 EUR enthalten 36 Monate Tarif UND Geraet, die
# Referenz 24 Monate Tarif plus Barpreis - allein die 12 Tarifmonate
# jenseits des Horizonts (mindestens 12 × 14,99 = 179,88 EUR nach dem
# Tarifstamm) sind groesser als der ausgewiesene Abstand von 79,74 EUR.
# Das VORZEICHEN des Vergleichs ist damit nicht belegt, und was nicht
# belegt ist, wird nicht angezeigt (CLAUDE.md, Clean Code 4: ein nicht
# bestimmbarer Zustand heisst `unbekannt` und faellt aus Vergleichen).
DELTA_ANDERE_LAUFZEIT = "andere Laufzeit"

log = logging.getLogger(__name__)

# Die vier Anbieter der Vision (A2), in der Reihenfolge, in der sie auf
# jeder Karte stehen. congstar laeuft als Telekom-Netz-Zweitmarke mit,
# bekommt aber nur eine Karte, wenn es wirklich ein Buendel liefert - eine
# leere Zeile fuer jede denkbare Zweitmarke waere eine Wand aus Luecken.
ANBIETER_REIHENFOLGE = ("Telekom", "1&1", "o2", "Vodafone")

EIGEN = "vodafone"

# A3 (STRATEGIE GERAETE V4, 20.09.2026): Wann ein Bündel als ALT gilt.
# Ein Angebot, dessen `abgerufen_am` älter als diese Zahl Tage ist, fällt
# aus „ab“-Preis, Delta und Ranking - die Zeile bleibt, ausgegraut, mit
# Abrufdatum sichtbar (harte Regel 9). Der Deckel ist eine benannte
# Konstante hier im Modul (Clean Code 8) und wird nie als Zahl in eine
# Vorlage geschrieben.
#
# AUFTRAG (Antonio, 20.09.2026): 3 Tage - „älter als 3 Tage fällt aus
# ab-Preis, Delta und Ranking; Tag-3-Grenzfall bleibt drin“. Die
# Gegenargumente aus der Datenlage stehen hier, weil sie weiter gelten
# (data/state/geraete_db.json, `anbieter.*.termine`, Stand 20.09.2026):
# der Telekom-Leser misst im 4-6-Tage-Rhythmus (05./06./08./09./15.09.),
# ElectronicPartner und Medimax im Wochenrhythmus (06. -> 12. -> 19.09.)
# - ihre Bündel gelten mit 3 Tagen regelmäßig als alt. Das ist keine
# Fehlmessung der Grenze, sondern der ANTRIEB für P1: Telekom soll
# täglich gelesen werden. Bis dahin ist der ausgegraute Stand mit Datum
# die ehrliche Aussage (Regel 9), kein falscher Tagespreis.
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
        return (_dt.date.fromisoformat(heute)
                - _dt.date.fromisoformat(abgerufen_am)).days
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
                # DIE GEMESSENE LAUFZEIT, ungeraten (P0-B-fix2, dieselbe
                # Regel und dieselbe Stelle wie P0-B-fix1 im Rechenkern):
                # bis hierher stand `int(... or 24)`. Eine Listung ohne
                # `laufzeit_monate` - 1&1 liefert sie, wenn die
                # Produktseite keine Dauer nennt - bekam damit eine
                # geratene 24 in Schluessel, Rechnung und Etikett. Jetzt
                # geht der Wert durch: `None` wird zur benannten Luecke
                # (`tco_model.POSTEN_LAUFZEIT`), die Zeile bleibt stehen
                # und nennt sie (Regel 9), eine unmoegliche Zahl wirft in
                # `Buendel.__post_init__` und landet im `except` darunter.
                laufzeit_monate=e.get("laufzeit_monate"),
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


# D3 (Phase P2, Zerlegungsbalken der Bündelzeile): die Segmente kommen
# AUSSCHLIESSLICH aus `_bestandteile_mit_kategorie()` und `Tco.restbetrag`
# (Clean Code 1 - keine zweite Rechnung). `restbetrag` ist in `tco_24()`
# kein eigener Posten, sondern der Anteil EINES vorhandenen Postens
# (Geräteraten oder Bündelbetrag), der erst nach Monat 24 fällig wird -
# der Balken teilt genau dieses eine Segment in einen fälligen und einen
# offenen (schraffierten) Teil. Jedes andere Segment bleibt ganz. Die
# Summe der Segmentbeträge ist dadurch immer exakt `kennzahl.gesamt`:
# `faellig + offen == betrag` per Konstruktion, und kein Segment wird neu
# addiert.
_ZERLEGUNG_RATENKATEGORIEN = ("raten", "buendel")
LABEL_RESTSCHULD = "Restschuld nach Monat 24"


def zerlegung_balken(bestandteile: list, restbetrag: Optional[float],
                     gesamt: Optional[float]) -> list:
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
    # `None` heisst "Restschuld nicht bestimmbar" (kein Split - dieselbe
    # Zeile bliebe dann unbelastbar und käme hier ohnehin nicht an,
    # `tco_model.tco_24`), 0,00 EUR heisst "nichts offen" (ebenfalls kein
    # Split, aber eine GEMESSENE Aussage). Truthiness (`if restbetrag`)
    # behandelte beide gleich, aber aus Zufall: eine echte, ungemessene
    # Restschuld naeher an 0 als 0,005 EUR waere sonst als "kein Split"
    # verschwunden, ohne dass "nicht bestimmbar" das je gesagt hat.
    rest = round(restbetrag, 2) if restbetrag is not None else 0.0
    segmente = []
    gesplittet = False
    for posten in bestandteile:
        name, betrag = posten["name"], posten["betrag"]
        kategorie = posten["kategorie"]
        if rest and not gesplittet and kategorie in _ZERLEGUNG_RATENKATEGORIEN:
            faellig = round(betrag - rest, 2)
            # Ausfall (Clean Code 5), kein stilles negatives Segment: eine
            # Restschuld, die groesser ist als der Posten, aus dem sie
            # kommt, ist ein widerspruechlicher Bestand (z. B. eine falsch
            # zugeordnete Restschuld aus einer anderen Laufzeit) - der
            # Balken bleibt UNGEZEICHNET (leere Liste, dieselbe
            # Bedeutung wie "kein `gesamt`" oben), nie ein Balken mit
            # einer erfundenen Breite unter 0 %.
            if faellig < 0:
                log.warning(
                    "zerlegung_balken: restbetrag %.2f EUR groesser als "
                    "der Posten %r (%.2f EUR) - Balken bleibt "
                    "ungezeichnet", rest, name, betrag)
                return []
            if faellig:
                segmente.append({"name": name, "betrag": faellig,
                                 "kategorie": kategorie, "offen": False})
            segmente.append({"name": LABEL_RESTSCHULD, "betrag": rest,
                             "kategorie": "restschuld", "offen": True})
            gesplittet = True
        elif betrag:
            segmente.append({"name": name, "betrag": betrag,
                             "kategorie": kategorie, "offen": False})
    for seg in segmente:
        seg["pct"] = round(seg["betrag"] / gesamt * 100, 3) if gesamt else 0.0
    return segmente


# P0-B-h1: HIER STAND `leitzahl_monate(b: Buendel)` und leitete den
# Zeitraum der Leitzahl ein ZWEITES Mal aus dem Buendel ab ("kein
# Buendelmonatspreis -> 24, sonst die Laufzeit") - dieselbe Regel, die
# `tco_model.tco_24` beim Zaehlen der Monate schon anwendet. Genau diese
# zwei Stellen sind auseinandergelaufen: das Etikett nannte 36 Monate,
# waehrend derselbe Datensatz seinen Ø/Monat durch 24 teilte. Der
# Zeitraum kommt seither aus `Tco.leitzahl_monate`, also aus der
# Rechnung selbst, und jeder Leser hier liest dieses Feld.


def label_der_leitzahl(monate: Optional[int]) -> str:
    """"Kosten über 36 Monate" - das Etikett NENNT den Zeitraum der Zahl.

    Ein Etikett, das 24 sagt, wo die Zahl 36 Monate traegt, ist keine
    Formulierungsfrage: es macht aus einer richtigen Summe eine falsche
    Aussage. Der Zeitraum kommt aus `Tco.leitzahl_monate` - dieselbe
    Zahl, die den Ø/Monat teilt und ueber den Δ-Vergleich entscheidet
    (Clean Code 7).
    """
    if monate is None:
        return LABEL_OHNE_LAUFZEIT
    return f"Kosten über {monate} Monate"


def _karte(b: Buendel, tarif: Optional[dict], barpreis: Optional[dict],
           katalog, geraet_je_sku: dict, zustand: str = "unbekannt",
           heute: str = "") -> dict:
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
    # Der Zeitraum, den die Leitzahl dieser Zeile traegt - GELESEN, nicht
    # abgeleitet: er kommt aus der Rechnung, die die Monate gezaehlt hat
    # (`tco_model.Tco.leitzahl_monate`, P0-B-h1). Etikett, Ø/Monat und
    # Δ-Vergleich lesen dieselbe Zahl.
    monate = kennzahl.leitzahl_monate
    device_id, speicher = geraet_je_sku.get(b.sku_id, ("", None))
    # "ab Monat 25: X EUR" - die Grundgebuehr nach dem festen 24-Monats-
    # Horizont, aus den PREISPHASEN des Pflichtdokuments. Sie ist die
    # Antwort auf die Kostenfallen-Kritik (Recherche § 2.3) und wird NICHT
    # geraten: gibt es keine Phase fuer den Monat danach, steht dort nichts.
    nach_bindung = _phase_ab(tarif, AB_MONAT) if tarif else None

    eff = None
    if barpreis is not None and kennzahl.belastbar and monate:
        # BEIDE Seiten dieser Differenz laufen ueber DENSELBEN Zeitraum
        # (P0-B-h1). Bis hierher stand hier `/ TCO_HORIZONT`: bei einem
        # 36-Monats-Buendel zog das einen auf 24 Monate verteilten
        # Barpreis von einem Ø/Monat ab, der 36 Monate traegt - die
        # Differenz war dann weder ein Tarifpreis noch sonst etwas.
        eff = round(kennzahl.monatlich - barpreis["betrag"] / monate, 2)
    # Katalog D: "X € in 36 Raten" - die volle Ratensumme (nicht auf 24
    # Monate gekappt), dieselbe Zahl traegt auch die Geraetepreis-Leitzahl
    # (A-R5), einmal gerechnet statt zweimal.
    #
    # P0-B-fix2: OHNE gemessene Laufzeit gibt es keine Ratensumme. Bis
    # hierher stand nur `if b.geraet_monatsrate is not None` - seit
    # P0-B-fix1 ist `laufzeit_monate` `Optional[int]`, und diese Zeile
    # rechnete dann `float * None` (TypeError, die ganze Seite aus).
    # Ein geratener Faktor waere die andere Haelfte desselben Fehlers:
    # "1.098,00 € in 36 Raten" ohne gemessene 36 ist eine Erfindung.
    raten_summe = (round(b.geraet_monatsrate * b.laufzeit_monate, 2)
                   if (b.geraet_monatsrate is not None
                       and b.laufzeit_monate is not None) else None)
    # Wie viele Raten nach Monat 24 noch laufen.
    #
    # P0-B-fix2: `(b.laufzeit_monate or 0)` ist weg. Ein Angebot OHNE
    # Raten hat null offene - das ist eine Aussage. Ein Ratengeschaeft
    # ohne gemessene Laufzeit hat dagegen eine unbekannte Zahl offener
    # Raten, und die heisst `None` und nicht 0 (Clean Code 3: 0 nur, wo 0
    # eine Aussage ist).
    if b.geraet_monatsrate is None and b.buendel_monatlich is None:
        offene_raten: Optional[int] = 0
    elif b.laufzeit_monate is None:
        offene_raten = None
    else:
        offene_raten = max(0, b.laufzeit_monate - TCO_HORIZONT)
    geraetepreis, geraetepreis_art = _geraetepreis(
        barpreis, b.geraet_zuzahlung, raten_summe)
    # D3: EINMAL berechnet, zweimal gelesen (Clean Code 1) - die
    # textliche Postenliste (`bestandteile`) und der Zerlegungsbalken
    # (`zerlegung`) lesen dieselbe Liste, keine zweite Ableitung aus
    # `kennzahl`.
    bestandteile = _bestandteile_mit_kategorie(kennzahl)
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
        # A3: die Frische DIESER Karte - eine boolesche Aussage über die
        # Messung, keine über die Rechnung. `alt_marke` ist der fertige
        # Chip-Text (das Datum ist Teil der Marke, nicht der Vorlage -
        # dort stünde sonst eine zweite Formatierung derselben Zahl).
        "frisch": frisch,
        "alt_marke": ("" if frisch else alt_marke_fuer(b.abgerufen_am)),
        # Dieselbe Klasse auf Karte, Balken und Legende - C.3 verlangt die
        # Anbieterfarbe konsistent ueber ALLE Grafiken und Tabellen.
        "slug": anbieter_slug(b.anbieter),
        # D3: DIE EINE Quelle der Anbieterfarbe ist `anbieter_farben.py`
        # (CLAUDE.md, DATEIGRENZE) - `slug` oben ist ein anderer, aelterer
        # Schluessel (`geraete_tco_grafik.anbieter_slug`, fuer SVG und
        # Filter) und faellt fuer unbekannte Anbieter NICHT auf die
        # benannte Luecke zurueck. Die Bündelzeile traegt die Farbe als
        # Custom-Property-WERT (`style="--anb:…"` in der Vorlage), nicht
        # als `gr-anb--<slug>`-Klasse: der Wahrheits-Orakeltest
        # (`tests/test_seiten_zahlen.py`) sucht an dieser Zeile woertlich
        # `class="gr-bnd"` ohne Zusatz.
        "anb_farbe": anbieter_farben.farbe_fuer(b.anbieter),
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
        # TICKET TCO24-1: die TARIFLAUFZEIT der Rechnung ist eine
        # Konstante - "Immer 24 Monate" ist keine Ableitung aus dem
        # Buendel mehr. Sie ist auch der Teiler des Ø/Monat.
        #
        # P0-B-fix2: DAS ETIKETT ist es NICHT. Es nennt den Zeitraum, den
        # die Zahl wirklich traegt (`leitzahl_monate`) - bei einem
        # zusammengelegten Buendelmonatspreis ueber 36 Monate steht dort
        # "Kosten über 36 Monate", nicht "über 24 Monate".
        "label": label_der_leitzahl(monate),
        "laufzeit": LAUFZEIT,
        "leitzahl_monate": monate,
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
        # A5.2, Pflichtzeile: seit A1 ist "gezahlt nach 24 Monaten" die
        # Leitzahl MINUS die Restschuld - die Leitzahl rechnet alle Raten,
        # und der Teil, der nach Monat 24 noch laeuft, steht als
        # `offen_nach_24` daneben (IN der Zahl UND ausgewiesen).
        # `is not None` und nicht Truthiness: eine gemessene 0.0 ist die
        # Aussage "nichts offen", kein fehlender Wert (CLAUDE.md Clean
        # Code 3).
        "gezahlt_nach_24": (round(kennzahl.gesamt - (kennzahl.restbetrag
                                or 0.0), 2)
                            if kennzahl.belastbar else None),
        "offen_nach_24": (kennzahl.restbetrag
                          if kennzahl.belastbar
                          and kennzahl.restbetrag is not None else None),
        "offene_raten": offene_raten,
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
        "bestandteile": bestandteile,
        # D3: der Zerlegungsbalken der Leitzahl - liest `bestandteile` und
        # `restbetrag` dieser Kennzahl, rechnet keinen Euro neu.
        "zerlegung": zerlegung_balken(bestandteile, kennzahl.restbetrag,
                                      kennzahl.gesamt if kennzahl.belastbar
                                      else None),
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
# ZWEI Luecken, die eine Karte unbelastbar machen: den fehlenden
# Tarifgrundpreis (`POSTEN_TARIF`) und - seit P0-B-fix1 - die fehlende
# Ratenlaufzeit (`POSTEN_LAUFZEIT`). Die Flextarif-/Tarifbindungs-
# Sonderfaelle von `tco_bindung` entfallen - "Immer 24 Monate" rechnet den
# Tarifgrundpreis unabhaengig von der Mindestlaufzeit.
_GRUND_JE_LUECKE = {
    POSTEN_TARIF: ("Der Tarifgrundpreis dieses Bündels ist nicht erhoben – "
                   "ohne ihn ist es kein Gesamtpreis, sondern ein "
                   "Gerätebetrag."),
    POSTEN_LAUFZEIT: ("Die Ratenlaufzeit dieses Bündels ist nicht erhoben – "
                      "ohne die Zahl der Monate ergibt der Monatsbetrag "
                      "keine Gesamtsumme."),
}


def _grund(kennzahl) -> str:
    """Warum diese Karte keine Zahl traegt - in der Reihenfolge der Ursachen."""
    if POSTEN_TARIF in kennzahl.luecken:
        return _GRUND_JE_LUECKE[POSTEN_TARIF]
    if POSTEN_LAUFZEIT in kennzahl.luecken:
        # P0-B-fix2: VOR dem Satz "kein einziger Posten erhoben". Ein
        # Buendelmonatspreis ohne seine Laufzeit hat sehr wohl einen
        # gemessenen Posten - es fehlt seine LAENGE, und die Karte sagt
        # genau das (Regel 9), statt das Angebot fuer unerhoben zu
        # erklaeren.
        return _GRUND_JE_LUECKE[POSTEN_LAUFZEIT]
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
            "anb_farbe": anbieter_farben.farbe_fuer(anbieter),
            "geraetepreis": None, "geraetepreis_art": None,
            "label": "", "laufzeit": None, "leitzahl_monate": None,
            "ab_monat": None, "belastbar": False,
            "gesamt": None, "schnitt_monat": None, "gezahlt_nach_24": None,
            "offen_nach_24": None, "offene_raten": 0, "monatlich": None,
            "buendel_monatlich": None, "zuzahlung": None, "rate": None,
            "raten_summe": None,
            "anschlusspreis": None, "nach_bindung": None,
            "eff_ohne_geraet": None, "eff_basis": None, "bestandteile": [],
            "zerlegung": [],
            "luecken": [], "boni": [], "boni_abzug": 0.0, "quelle_url": "",
            "abgerufen_am": "", "tarif_quelle_url": "", "naeherung": False,
            "leer_grund": grund or LEER_GRUND.get(anbieter, ""),
            "ab_preis": False,
            # A3: eine Leerkarte ist keine Bündel-Messung - sie altert
            # nicht. Die NÄHERUNGSKARTE, die auf dieser Bauform aufsetzt,
            # überschreibt beide Felder mit dem Stand ihrer Belege
            # (`_referenzkarte`, S2-1) - dieser Default gilt nur für
            # Karten ohne jede Messung.
            "frisch": True, "alt_marke": "",
            "zustand": "", "zustand_etikett": "", "vergleichbar": False,
            "sku_id": "", "modell_id": "", "geraet": "", "tarif_id": "",
            "tarif_id_guete": "", "tarif_bindung": None,
            "raten_laufzeit": None}


# --------------------------------------------------------------------------
# Die Vodafone-Referenz: gemessene Summanden, gerechnete Summe
# --------------------------------------------------------------------------

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
    return [Preisphase(von_monat=p.get("von_monat") or 1,
                       bis_monat=p.get("bis_monat"),
                       betrag=p.get("betrag"))
            for p in ((tarif or {}).get("preisphasen") or [])
            if p.get("betrag") is not None]


# Die Spanne, innerhalb derer eine gemessene Monatsrate als "im Blatt
# befindlich" gilt - zwei auf Cent gerundete Werte duerfen um ein Rundungs-
# rest voneinander abweichen, ohne schon ein anderes Preisniveau zu sein.
_PREIS_TOLERANZ = 0.005


def phasen_fuer_buendel(tarif: Optional[dict],
                        tarif_monatlich: Optional[float]) -> list:
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
    if (min(betraege) - _PREIS_TOLERANZ <= tarif_monatlich
            <= max(betraege) + _PREIS_TOLERANZ):
        return phasen
    return []


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

    Der Tarifbetrag ist phasengewichtet (`tco_model.phasensumme`, seit A1
    Teil des Moduls der Leitzahl) - dieselbe Rechnung wie auf der
    Tarifseite und an EINER Stelle. Steht im Blatt eine Phase fuer Monat 25
    und danach, wird sie gelesen; steht keine, gilt der Grundpreis fort,
    und die Karte sagt es.
    """
    vodafone = [r for r in referenzen
                if _eigen(getattr(r, "anbieter", ""))
                and getattr(r, "tarif_sim_only_monatlich", None) is not None]
    geraet = (barpreise_der_sku or {}).get("Vodafone")
    if not vodafone or geraet is None:
        return None
    referenz = min(vodafone, key=lambda r: r.tarif_sim_only_monatlich)
    tarif = tarife.get(referenz.tarif_id) or {}
    # QA-Fix 20.09.2026: dieselbe Rangfolge wie am Bündel - widerspricht
    # die gemessene SIM-only-Rate den Phasen des Blatts, gewinnt die
    # Messung (flach). Am Bestand stimmen beide ueberein (29,95 EUR); die
    # Regel steht hier, damit sie an KEINER Stelle des Blatts fehlt.
    phasen = phasen_fuer_buendel(tarif, referenz.tarif_sim_only_monatlich)

    # Der Zeitraum, ueber den diese Naeherung rechnet - EIN Wert, aus dem
    # unten Summe, Ø/Monat, Etikett und Δ-Tor lesen (P0-B-h1).
    monate = TCO_HORIZONT
    summe = phasensumme(phasen, monate) if phasen else None
    # "Fortgeschrieben" heisst: das Blatt sagt zu einem Teil der 24 Monate
    # nichts, und es gilt der zuletzt belegte Preis weiter. Das ist die
    # vorsichtige Annahme (dieselbe wie in `phasensumme`), aber sie ist
    # eine Annahme - deshalb steht sie auf der Karte und nicht nur im Code.
    abgedeckt = 0
    for phase in phasen:
        abgedeckt = max(abgedeckt, monate if phase.bis_monat is None
                        else phase.bis_monat)
    fortgeschrieben = abgedeckt < monate
    if summe is None:
        summe = round(referenz.tarif_sim_only_monatlich * monate, 2)
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
        # Der Zeitraum dieser Zahl, an EINER Stelle: die Naeherung ist
        # `monate` Tarifmonate plus Barpreis, also traegt sie genau
        # diesen Zeitraum. `tarif_monate` ist derselbe Wert unter dem
        # Namen, den `geraete_tco_grafik` und die Referenzkarte lesen -
        # und er wird hier nicht ein zweites Mal hingeschrieben.
        "monate": monate,
        "tarif_monate": monate,
        "gesamt": gesamt,
        # Dieselbe Division wie auf jeder Buendelzeile, aus derselben
        # Funktion (`tco_model.monatsschnitt`, P0-B-h1).
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
        # P0-B-fix2: der Zeitraum, den die Zahl dieser Karte traegt
        # (`leitzahl_monate`), nicht die Tariflaufzeit der Rechnung - sonst
        # meldete ein eigenes 36-Monats-Buendel als Referenz "24 Monate"
        # und jede fremde Zeile bekaeme ein Delta gegen einen anderen
        # Zeitraum.
        "monate": karte["leitzahl_monate"], "gesamt": karte["gesamt"],
        "schnitt_monat": karte["schnitt_monat"], "fortgeschrieben": False,
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
    return (ist_frisch(ref.get("tarif_abgerufen_am") or "", heute)
            and ist_frisch(ref.get("geraet_abgerufen_am") or "", heute))


def _referenz_stand(ref: dict) -> str:
    """Das Datum der Marke einer alten Näherung - ISO oder „“.

    Der späteste Tag, an dem noch BEIDE Summanden gestimmt haben, ist
    der ÄLTERE der zwei Abrufdaten. Ist eines unlesbar, ist der Stand
    unbekannt („seit <Datum>“ hieße, der andere Summand hätte noch
    gestimmt - geraten wird nichts, Clean Code 4).
    """
    daten = [ref.get("tarif_abgerufen_am") or "",
             ref.get("geraet_abgerufen_am") or ""]
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
    karte.update({
        # KEIN Leergrund: diese Karte traegt eine Zahl. Der Vorbehalt steht
        # in `naeherung` und auf der Seite in einem eigenen Satz - nicht in
        # dem Feld, das "hier gibt es nichts" bedeutet.
        "leer_grund": "",
        "tarif": ref["tarif"],
        # P1/UX-1, nachgetragen mit O2: DIE TARIF-ID MIT - ohne sie bekam
        # die Referenzkarte KEIN Band (band_je_tarif schluesselt auf die
        # tarif_id) und stand in der Gruppe "Ohne Tarifband", obwohl ihr
        # Tarif eines hat. Am echten Bestand fiel es nicht auf (Vodafone
        # hat dort ueberall echte Buendel); die Zustands-Fixture traegt
        # eine Naeherung, und an ihr hielt der neue Zeilen-Test es fest.
        "tarif_id": ref.get("tarif_id", ""),
        # TICKET TCO24-1: die Leitzahl ist IMMER TCO-24 - `ref["monate"]`
        # und `ref["tarif_monate"]` sind seit `_vodafone_referenz` beide
        # der feste Horizont (`TCO_HORIZONT`), keine variable Fensterzahl
        # mehr. Vorher trugen alle 30 Referenzkarten "TCO-36" bei einer
        # Rechnung, die 24 Tarifmonate plus Barkauf war (QA-Befund F-R2-2).
        # P0-B-fix2: Etikett und Zeitraum kommen aus DEMSELBEN Feld wie an
        # jeder anderen Zeile - die Naeherung rechnet `tarif_monate`
        # Tarifmonate plus den Barpreis, ihre Zahl traegt also genau
        # diesen Zeitraum - gebaut aus `label_der_leitzahl`, damit hier
        # keine zweite Beschriftungsregel entsteht.
        "label": label_der_leitzahl(ref["tarif_monate"]),
        "ab_monat": AB_MONAT,
        "laufzeit": ref["tarif_monate"],
        "leitzahl_monate": ref["tarif_monate"],
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
        # geschuldet ist.
        #
        # A1 (20.09.2026): `gezahlt_nach_24` ist SEITHER die `gesamt` der
        # Referenz selbst. Die fruehere Formel (Barpreis + flacher
        # Tarifgrundpreis × 24) rechnete eine ZWEITE Summe - und gegen die
        # phasengewichtete `gesamt` ein NEGATIVES `offen_nach_24`, sobald
        # das Blatt Rabattphaen nennt. Die Referenz schuldet nach Monat 24
        # nichts: 0.0 ist die Aussage, nicht ein fehlender Wert.
        "gezahlt_nach_24": ref["gesamt"],
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
    karte["offen_nach_24"] = 0.0
    # D3: die Näherung schuldet nach Monat 24 nichts (siehe oben) - ihr
    # Balken hat deshalb nie ein schraffiertes Segment, aber denselben
    # Aufbau wie jede andere Zeile (aus ihren EIGENEN `bestandteile`).
    karte["zerlegung"] = zerlegung_balken(karte["bestandteile"], 0.0,
                                          karte["gesamt"])
    # S2-1: die Frische ÜBERSCHREIBT den Default der Leerkarte - die
    # Näherung ist eine gerechnete Summe aus zwei gemessenen Belegen,
    # und ihr Stand ist der der Belege (siehe `_referenz_stand`).
    frisch = referenz_ist_frisch(ref, heute)
    karte["frisch"] = frisch
    karte["alt_marke"] = ("" if frisch
                          else alt_marke_fuer(_referenz_stand(ref)))
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
        # A3: ein altes Angebot ist kein Abstand zur Gegenwart. Sein Delta
        # gegen die heutige Referenz waere eine Zahl, die an keinem Tag
        # beide Seiten gleichzeitig gegolten hat - dieselbe Fehlerklasse
        # wie die Mischung zweier Messungen in einer Summe (tco_store).
        return False
    if not karte.get("vergleichbar", True):
        # Ein erneuertes Geraet ist kein Konkurrent des Neugeraets (H5).
        # "775,35 EUR guenstiger als die Vodafone-Referenz" stand am
        # 04.09.2026 unter einem gebrauchten iPhone 15 gegen ein neues.
        return False
    if karte["eigen"]:
        # Ein eigenes Buendel IST die Referenz (oder ein zweites eigenes
        # Angebot). "0,00 € teurer als die Vodafone-Referenz" auf einer
        # Vodafone-Karte war der Befund B4 aus Phase 6a, hier neu
        # entstanden.
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
    return zeitraum_vergleichbar(karte.get("leitzahl_monate"),
                                 referenz.get("monate"))


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
    if not _delta_faellig(karte, referenz) or gleicher_horizont(karte,
                                                                referenz):
        return None
    monate = karte.get("leitzahl_monate")
    dieses = (f"{monate} Monate" if monate is not None
              else "eine nicht gemessene Laufzeit")
    return {
        "kurz": DELTA_ANDERE_LAUFZEIT,
        "satz": (f"Kein Abstand zur Vodafone-Referenz: diese Zahl trägt "
                 f"{dieses}, die Referenz {referenz['monate']} Monate."),
    }


def _delta(karte: dict, referenz: Optional[dict]) -> Optional[dict]:
    """Euro primaer, Prozent sekundaer - und nur bei gleichem Zeitraum.

    Ueber Laufzeiten hinweg gibt es kein Euro-Delta (A5.4). Wo die Zahl
    der Karte 36 Monate traegt und die Referenz 24, waere die Differenz
    die Laufzeit und nicht der Preis.

    P0-B-fix2: dann gibt es auch KEIN monatliches Delta mehr. Bis hierher
    stand in diesem Fall der Ø/Monat-Abstand da (A5.3) - aber der Ø/Monat
    teilt beide Summen durch dieselben 24 Monate
    (`tco_model.Tco.monatlich`), und eine 36-Monats-Summe durch 24 ist
    kein Monatspreis. Gemessen an 1&1s iPhone 17 256 GB: ausgewiesen waren
    "+79,74 EUR / +4,3 % über der Vodafone-Referenz", waehrend allein die
    12 Tarifmonate jenseits des Horizonts mit mindestens 179,88 EUR in der
    Zahl stecken - das Vorzeichen war nicht belegt. Die Zeile bekommt
    stattdessen den benannten Zustand aus `delta_zustand` (Regel 9: der
    Ausfall steht auf der Seite).

    Ein Abstand unter der Wesentlichkeits-Schwelle ist eine ANNAEHERUNG
    (`ungefaehr`, A2 20.09.2026), kein fehlendes Delta: der Strich der
    Δ-Spalte heisst "kein Angebot", und ein gemessenes, das nur knapp
    daneben liegt, ist sehr wohl eines.
    """
    if not _delta_faellig(karte, referenz):
        return None
    if not gleicher_horizont(karte, referenz):
        # Kein Euro-Delta UND kein Monatsdelta - `delta_zustand` benennt
        # die Zeile stattdessen.
        return None
    betrag = round(karte["gesamt"] - referenz["gesamt"], 2)
    monatlich = round(karte["schnitt_monat"] - referenz["schnitt_monat"], 2)
    # WESENTLICHKEIT, dieselbe Schwelle und dieselbe Begruendung wie in
    # `geraete_vergleich` und `geraete_tco_view._delta`: unter drei Prozent
    # ODER fuenfzehn Euro ist der Abstand keine Meldung. Ohne sie schriebe
    # das lauteste Element der Karte bei zwei gleich teuren Angeboten
    # "0,00 € teurer als die Vodafone-Referenz".
    #
    # P0-B-fix2: Bezug und Massstab sind IMMER der Euro-Betrag - seit dem
    # Horizont-Tor kommt diese Stelle nur noch mit gleichem Zeitraum
    # zustande, und die frueheren Monats-Zweige (`betrag is not None`)
    # waren danach unerreichbar.
    ungefaehr = not _wesentlich(betrag, referenz["gesamt"])
    return {
        "ungefaehr": ungefaehr,
        "betrag": betrag,
        "prozent": (None if ungefaehr or not referenz["gesamt"] else
                    round(abs(betrag) / referenz["gesamt"] * 100, 1)),
        "monatlich": monatlich,
        "guenstiger": betrag < 0,
        "abstand": abs(betrag),
        # Dieses Feld ist seit dem Horizont-Tor immer `True` - es bleibt,
        # weil `geraete_export` und die Vorlagen es lesen.
        "gleiche_laufzeit": True,
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
    guenstigstes Angebot, sondern eine Luecke. Dasselbe gilt seit A3 für
    ALTE Angebote: die Zeile bleibt, aber hinter jeder frischen.
    """
    return (not karte["belastbar"], not karte.get("vergleichbar", True),
            karte["naeherung"], not karte.get("frisch", True),
            karte["schnitt_monat"] if karte["schnitt_monat"] is not None
            else 9e9, karte["anbieter"])


def _neuigkeit(karte: dict) -> int:
    """`abgerufen_am` als ordnungsfeste Zahl, absteigend verglichen.

    Ein unlesbares oder leeres Datum zaehlt als aelteste Messung (0): eine
    Karte ohne Datum gewinnt den Slot nie, sie verliert ihn nur - ein
    fehlender Wert ist keine Aussage ueber die Aktualitaet (Clean Code 3).
    """
    try:
        return _datum.fromisoformat(
            (karte.get("abgerufen_am") or "").strip()).toordinal()
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
    desselben Angebots, statt weiter als aktuelle Karte zu stehen. A2
    bleibt der Tiebreaker INNERHALB der Frische - und ihr einziger
    Anker im Kompatibilitätsmodus `heute=""`, in dem nichts altert und
    alle Karten gleich frisch sind: dort entscheidet weiter das
    aktuellste Datum vor dem Preis.
    """
    return (not karte.get("frisch", True),
            1 if karte.get("aus_listung") else 0,
            -_neuigkeit(karte),
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
            katalog, heute: str = "") -> dict:
    """Alle Modelle mit mindestens einem Buendel, je Modell vier Anbieter.

    Rueckgabe:
        modelle         [{id, name, hersteller, speicher, karten, referenz,
                          laufzeiten, spanne, bundle_anbieter}]
        vorgabe         die ID des Modells, das ohne Klick sichtbar ist
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
                       zustand=zustand_des_buendels(b, zustaende),
                       heute=heute)
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
        #
        # DIE LAUFZEIT IM SCHLUESSEL IST DIE GEMESSENE RATENLAUFZEIT
        # (P0-B-fix2). Bis hierher stand `k["laufzeit"]` darin - das ist
        # die KONSTANTE `LAUFZEIT` (= `TCO_HORIZONT` = 24), also fuer jede
        # Karte dieselbe Zahl. B1 legte die Ratenlaufzeit in den
        # Buendelschluessel des Bestands, damit zwei Zahlweisen desselben
        # Tarifs zwei Buendel sind; hier ueberschrieben sie sich weiter,
        # nur eine Ebene hoeher, und welche ueberlebt, entschied
        # `_angebot_rang` (Datum, dann Preis). Nachgemessen am Bestand vom
        # 21.09.2026: ein zweites congstar-Buendel (Allnet Flat S zum
        # Galaxy S26 Ultra 256 GB, 24 Raten neben den gemessenen 36) liess
        # die 36-Monats-Variante samt ihrer Restschuld-Zeile verschwinden.
        # `raten_laufzeit` ist `None`, wo es ueberhaupt keine Rate gibt -
        # solche Zeilen gruppieren sich weiter korrekt miteinander.
        je_angebot: dict = {}
        for k in karten:
            schluessel = (k["anbieter"], k["tarif"], k["raten_laufzeit"],
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

        # Die GEMESSENEN Ratenlaufzeiten dieses Modells (P0-B-fix2).
        # Vorher stand hier `k["laufzeit"]`, also die Konstante 24 - eine
        # Liste, die per Konstruktion `[24]` war und damit nichts sagte.
        # Dieselbe Zahl, die auch den Entdoppelungs-Schluessel traegt.
        laufzeiten = sorted({k["raten_laufzeit"] for k in karten
                             if k["raten_laufzeit"]})
        # ERST DAS EIGENE BUENDEL, DANN DIE NAEHERUNG. Wo Vodafone selbst
        # ein Buendel zu diesem Geraet ausweist, ist es die Referenz; die
        # gerechnete Summe traete sonst als zweite Vodafone-Karte daneben.
        # ... und nur ein NEUGERAET: ein erneuertes eigenes Buendel als
        # Massstab fuer neue Wettbewerbergeraete waere derselbe Fehler mit
        # umgekehrtem Vorzeichen.
        # A3: ... und nur ein FRISCHES. Ein altes eigenes Buendel ist kein
        # Massstab von heute; die Referenz faellt dann auf die gerechnete
        # Naeherung zurueck (deren Karte aber NICHT mit dazu - Vodafone
        # steht je Modell genau einmal, siehe unten).
        eigene = [k for k in karten
                  if k["eigen"] and k["belastbar"] and k["vergleichbar"]
                  and k["frisch"]]
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
        # S2-1 (Diff-Prüfung 21.09.2026): eine ALTERTE Referenz ist kein
        # Maßstab von heute. Deltas gegen sie wären Zahlen, die an keinem
        # Tag beide Seiten gleichzeitig gegolten haben - dieselbe
        # Fehlerklasse wie ein altes Angebot selbst (siehe `_delta`).
        # Die Referenz bleibt am Modell (Regel 9: die Karte zeigt den
        # letzten Stand), aber der Delta-Bezug bekommt sie nicht.
        referenz_aktuell = referenz_ist_frisch(referenz, heute)
        for k in karten:
            massstab = referenz if referenz_aktuell else None
            k["delta"] = _delta(k, massstab)
            # P0-B-fix2: wo es keine Zahl geben DARF, weil die zwei Zahlen
            # verschiedene Zeitraeume tragen, steht der benannte Zustand -
            # nicht der Strich, der "kein Angebot" heisst (Regel 9).
            k["delta_zustand"] = delta_zustand(k, massstab)

        vorhanden = {k["anbieter"] for k in karten}
        # A3: die Naeherungs-Karte nur, wo Vodafone nicht schon (etwa als
        # altes eigenes Buendel) eine Zeile hat - sonst stuenden zwei
        # Vodafone-Zeilen nebeneinander, und der Leser muesste raten,
        # welche "unser Preis" ist (derselbe Einwand wie in
        # `test_ein_eigenes_buendel_verdraengt_die_naeherung`).
        if naeherung is not None and not any(k["eigen"] for k in karten):
            karten.append(_referenzkarte(naeherung, heute))
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
                    if k["vergleichbar"] and k["frisch"]
                    and k["gesamt"] is not None]
        name = _name(katalog, gruppe["device_id"], gruppe["speicher"],
                     rueckfall=mid)
        hersteller = _hersteller(katalog, gruppe["device_id"])
        # E4: der Auto-Marker des Katalog-Eintrags - die Sichtbarkeitsregel
        # der Zeitreihen-Wahl haengt daran (geraete_zeitreihe: Auto-Modelle
        # erst ab 2 Messtagen waehlbar). Leer = Hand-Eintrag aus der Config
        # (oder kein Katalog uebergeben, wie in den Karten-Tests).
        katalog_eintrag = (katalog.nach_id(gruppe["device_id"])
                           if katalog else None)

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
                         and k.get("geraetepreis_art") != "finanzierung"
                         and k.get("frisch", True)]
        # F-4a' (PM, 05.09.2026, 19:xx): das Minimum gilt auch ueber die
        # Haendler OHNE Tarifbuendel (Amazon/Expert/Saturn) - sie tragen
        # keine Karte in `karten` (kein Buendel, siehe oben), stehen aber
        # als eigene Haendlerkarte auf DERSELBEN Modelltafel. Gemessener
        # Fall: Saturn 1.179,00 EUR unterbot Vodafones 1.199,90 EUR, ohne
        # dass die Antwortzeile es je gesehen haette - E1-Verstoss, die
        # Leitzahl widersprach ihrer eigenen Nachbarkarte.
        for haendler, eintrag in _haendler_geraetepreise(
                listungen_je_modell.get(mid, [])).items():
            # A3-Nachbesserung (Prüfer 20.09.2026, "hoch"): DIESELBE
            # Frische-Definition wie an jeder anderen Stelle der Antwort-
            # zeile (`ist_frisch`, Clean Code 7) - ein alter Händlerpreis
            # ist kein „günstigster Gerätepreis“ von heute (im Bestand
            # stehen Saturn-Preise mit 11-15 Tagen). Die HändlerKARTE
            # zeigt den Preis weiter, mit Datum - nur die Auswahl der
            # Antwortzeile liest frisch.
            if eintrag is not None and ist_frisch(
                    eintrag.get("abgerufen_am", ""), heute):
                geraetepreise.append({"anbieter": haendler,
                                      "geraetepreis": eintrag["preis"]})
        guenstigstes_geraet = (min(geraetepreise,
                                   key=lambda k: k["geraetepreis"])
                               if geraetepreise else None)
        tarifangebote = [k for k in angebote
                         if k["vergleichbar"] and k["frisch"]
                         and k["gesamt"] is not None]
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

        # A3: „alles alt“ am ganzen Modell. Ein Modell, dessen letzte
        # Bündel-Messung älter als ALT_AB_TAGEN ist, zeigt das ÜBER den
        # Zeilen (harte Regel 9: kein „nichts gefunden“ vortäuschen) -
        # `alt_seit` ist der SPÄTESTE Abruf der alten Bündel (ISO), das
        # Datum des letzten Standes. Ein unbekanntes Datum stellt keinen
        # Stand; die Naeherung ist keine Bündel-Messung und zaehlt nicht
        # mit.
        alte = [k for k in karten if k.get("sku_id") and not k["frisch"]]
        alt_seit = max(
            (k.get("abgerufen_am") or "" for k in alte
             if kurz_datum(k.get("abgerufen_am") or "")), default="")
        alles_alt = bool(alte) and not any(
            k["frisch"] for k in karten if k.get("sku_id"))
        if alles_alt and alt_seit:
            alt_hinweis = (f"Kein aktueller Bündel-Stand seit dem "
                           f"{kurz_datum(alt_seit)} – alle Zeilen dieses "
                           f"Modells sind älter als {ALT_AB_TAGEN} Tage.")
        elif alles_alt:
            alt_hinweis = ("Kein aktueller Bündel-Stand – das Abrufdatum "
                           "dieser Bündel ist unbekannt, ihre Werte zählen "
                           "nicht in den Vergleich.")
        else:
            alt_hinweis = ""

        fertig.append({
            "id": mid,
            "name": name,
            "hersteller": hersteller,
            "titel": titel(hersteller, name),
            "auto": (katalog_eintrag.auto if katalog_eintrag else ""),
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
            # A3: nur FRISCHE Angebote - ein alter Anbieter ist keines,
            # das die Seite heute beantworten kann.
            "bundle_anbieter": sorted({k["anbieter"] for k in angebote
                                       if k["frisch"]}),
            # A3: der benannte Zustand des ganzen Modells, wenn kein
            # frisches Bündel mehr steht (siehe Block oben).
            "alles_alt": alles_alt,
            "alt_seit": alt_seit,
            "alt_hinweis": alt_hinweis,
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


# P2 (Antonio F4, 17.09.2026): der Abschnitt "Die Reihen fuer G2"
# (`historienreihen`, 49 Zeilen) ist GEFALLEN - der feste Markt-Graph des
# Verlaufs-Reiters wurde geloescht (siehe geraete.html.j2, Kommentar
# "G2 IST GEFALLEN"); danach hatte die Funktion keinen Aufrufer mehr.
# Der WAEHLER desselben Reiters rechnet seinen eigenen Weg:
# `geraete_verlauf.reihen_fuer_listungen` + `messtage`.
