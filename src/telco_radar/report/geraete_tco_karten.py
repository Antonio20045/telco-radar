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
from ..tco_model import (LEITFRAGE_MONATE, POSTEN_ANSCHLUSS, POSTEN_TARIF,
                         POSTEN_TARIFBINDUNG, POSTEN_TARIF_FLEX, Buendel,
                         effektiv_ohne_geraet, tco_bindung)

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
LEER_GRUND = {
    "Telekom": ("Datenstand fehlt – Quelle in Vorbereitung. Der Abruf aus "
                "GitHub Actions beantwortet telekom.de mit einer "
                "202-Challenge; die Bündelpreise kommen mit dem lokalen "
                "Lauf (Phase T)."),
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


def buendel_aus_listungen(listungen: list) -> list[Buendel]:
    """Die Buendel, die als LISTUNG im Geraetebestand stehen - heute 1&1.

    1&1 verkauft Geraete ausschliesslich im Tarifbund; sein ld+json nennt
    EINEN Monatsbetrag fuer Tarif und Geraet (`preis_mit_vertrag_ab`) und
    die Laufzeit dazu. Genau so wird er gefuehrt: als
    `Buendel.buendel_monatlich`, ungeteilt.
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

def _karte(b: Buendel, tarif: Optional[dict], barpreis: Optional[dict],
           katalog, geraet_je_sku: dict, zustand: str = "unbekannt") -> dict:
    """Aus einem Buendel wird eine Karte - gerechnet wird in `tco_model`.

    Diese Funktion addiert keinen Euro. Sie holt die Kennzahl, haengt die
    Belege daran und formt die Pflichtzeilen des Katalogs D.
    """
    kennzahl = tco_bindung(b)
    device_id, speicher = geraet_je_sku.get(b.sku_id, ("", None))
    nach_bindung = None
    if tarif and kennzahl.tarif_bindung:
        # "ab Monat 25: X EUR" - die Grundgebuehr nach der Mindestlaufzeit,
        # aus den PREISPHASEN des Pflichtdokuments. Sie ist die Antwort auf
        # die Kostenfallen-Kritik (Recherche § 2.3) und wird NICHT geraten:
        # gibt es keine Phase fuer den Monat danach, steht dort nichts.
        nach_bindung = _phase_ab(tarif, kennzahl.tarif_bindung + 1)

    eff = effektiv_ohne_geraet(kennzahl,
                               barpreis["betrag"] if barpreis else None)
    return {
        # B.2.5 GILT AUCH HIER. Eine Karte ohne Zahl braucht ihren Grund -
        # `_leere_karte` fuellt ihn, diese Funktion tat es nicht, und die
        # Vorlage rendert dann einen leeren Absatz unter Anbieter und
        # Tarif. Der Fall entsteht mit dem ersten Buendel auf einem
        # Flextarif; im Bestand vom 04.09.2026 tragen acht von 44 Tarifen
        # `laufzeit_monate: 0`.
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
        # A5.1: die Laufzeit steht IM Namen der Leitzahl.
        "label": kennzahl.label,
        "laufzeit": kennzahl.bindung,
        "tarif_bindung": kennzahl.tarif_bindung,
        "raten_laufzeit": kennzahl.raten_laufzeit,
        "belastbar": kennzahl.belastbar,
        "gesamt": kennzahl.gesamt if kennzahl.belastbar else None,
        "schnitt_monat": kennzahl.schnitt_monat if kennzahl.belastbar else None,
        # A5.2, Pflichtzeile: Antonios Frage, woertlich beantwortet.
        "gezahlt_nach_24": kennzahl.gezahlt_nach_24,
        "offen_nach_24": kennzahl.offen_nach_24,
        "offene_raten": (max(0, (b.laufzeit_monate or 0) - LEITFRAGE_MONATE)
                         if b.geraet_monatsrate is not None
                         or b.buendel_monatlich is not None else 0),
        # Die Bausteine, jeder mit dem Label aus Katalog D.
        "monatlich": b.tarif_monatlich,
        "buendel_monatlich": b.buendel_monatlich,
        "zuzahlung": b.geraet_zuzahlung,
        "rate": b.geraet_monatsrate,
        # Katalog D: "X € in 36 Raten" - die Summe kommt aus dem Posten der
        # Kennzahl, nicht aus einer Multiplikation in der Vorlage.
        "raten_summe": next((p.get("betrag") for p in kennzahl.bestandteile
                             if p.get("kategorie") == "raten"), None),
        "anschlusspreis": b.anschlusspreis,
        "nach_bindung": nach_bindung,
        "eff_ohne_geraet": eff,
        "eff_basis": barpreis,
        "bestandteile": kennzahl.bestandteile,
        "luecken": kennzahl.luecken,
        "boni": kennzahl.boni,
        "boni_abzug": kennzahl.boni_abzug,
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


# Was auf der Karte steht, wenn die Rechnung nicht traegt. Jede Luecke
# bekommt einen Satz in der Sprache der Seite - "POSTEN_TARIFBINDUNG" ist
# ein Feldname und keine Auskunft.
_GRUND_JE_LUECKE = {
    POSTEN_TARIF: ("Der Tarifgrundpreis dieses Bündels ist nicht erhoben – "
                   "ohne ihn ist es kein Gesamtpreis, sondern ein "
                   "Gerätebetrag."),
    POSTEN_TARIFBINDUNG: ("Wie lange der Tarif bindet, ist nicht belegt – "
                          "und ohne die Bindung gibt es keine Laufzeit, "
                          "über die sich rechnen ließe."),
    POSTEN_TARIF_FLEX: ("Der Tarif ist monatlich kündbar. Über eine "
                        "Bindung, die es nicht gibt, ist kein Tarifbetrag "
                        "geschuldet – eine Gesamtsumme über die Laufzeit "
                        "wäre erfunden."),
}


def _grund(kennzahl) -> str:
    """Warum diese Karte keine Zahl traegt - in der Reihenfolge der Ursachen."""
    for posten in (POSTEN_TARIF, POSTEN_TARIF_FLEX, POSTEN_TARIFBINDUNG):
        if posten in kennzahl.luecken:
            return _GRUND_JE_LUECKE[posten]
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
            "label": "", "laufzeit": None, "belastbar": False,
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

def _vodafone_referenz(referenzen: list, tarife: dict, barpreise_der_sku: dict,
                       monate: int) -> Optional[dict]:
    """Tarif ohne Geraet + eigener Barpreis, ueber dieselbe Laufzeit.

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
    if not vodafone or geraet is None or not monate:
        return None
    referenz = min(vodafone, key=lambda r: r.tarif_sim_only_monatlich)
    tarif = tarife.get(referenz.tarif_id) or {}
    phasen = [Preisphase(von_monat=p.get("von_monat") or 1,
                         bis_monat=p.get("bis_monat"),
                         betrag=p.get("betrag"))
              for p in (tarif.get("preisphasen") or [])
              if p.get("betrag") is not None]

    # DER TARIF ZAEHLT SEINE EIGENE MINDESTLAUFZEIT, NICHT DAS FENSTER.
    #
    # Das ist dieselbe Regel, die `tco_bindung` fuer die Buendelkarte
    # anwendet (A5.5) - und sie hat auf BEIDEN Seiten zu gelten, sonst
    # vergleicht das Delta zwei verschieden zusammengesetzte Koerbe. Vorher
    # rechnete die Referenz 36 x 29,95 EUR, waehrend die o2-Karte daneben
    # 24 x 19,99 EUR trug: die Referenz war um 12 x 29,95 = 359,40 EUR zu
    # teuer, und ALLE 54 Delta-Zeilen der Seite sagten "guenstiger als
    # Vodafone", keine einzige "teurer". Eine Rechnung, die systematisch
    # zugunsten des Wettbewerbers ausfaellt, ist kein Wettbewerbsradar.
    #
    # Gemessen am Vorgabemodell (iPhone 17 Pro 256 GB): das Delta faellt
    # von -483,34 auf -123,94 EUR.
    tarif_monate = tarif.get("laufzeit_monate")
    if tarif_monate:
        tarif_monate = min(int(tarif_monate), monate)
    else:
        # Ohne belegte Mindestlaufzeit bleibt nur das Fenster - und die
        # Karte sagt, dass hier fortgeschrieben wurde.
        tarif_monate = monate
    summe = phasensumme(phasen, tarif_monate) if phasen else None
    # "Fortgeschrieben" heisst: das Blatt sagt zu diesen Monaten nichts, und
    # es gilt der zuletzt belegte Preis weiter. Das ist die vorsichtige
    # Annahme (dieselbe wie in `phasensumme`), aber sie ist eine Annahme -
    # deshalb steht sie auf der Karte und nicht nur im Code.
    abgedeckt = 0
    for phase in phasen:
        abgedeckt = max(abgedeckt, tarif_monate if phase.bis_monat is None
                        else phase.bis_monat)
    fortgeschrieben = abgedeckt < tarif_monate
    if summe is None:
        summe = round(referenz.tarif_sim_only_monatlich * tarif_monate, 2)
        fortgeschrieben = fortgeschrieben or not phasen
    if not tarif.get("laufzeit_monate"):
        # Der Tarifbetrag laeuft ueber das ganze Fenster, weil niemand eine
        # Mindestlaufzeit belegt hat. Auch das ist eine Fortschreibung.
        fortgeschrieben = True
    gesamt = round(summe + geraet["betrag"], 2)
    return {
        # F5 auch an der Referenz: das Blatt nennt "ab Monat 25" (Vodafone
        # Mobil XS: 29,95 EUR) - die Zeile steht auf jeder Karte mit Zahl.
        "nach_bindung": (_phase_ab(tarif, tarif_monate + 1)
                         if tarif.get("laufzeit_monate") else None),
        "tarif": referenz.tarif_name,
        "tarif_id": referenz.tarif_id,
        "monatlich": referenz.tarif_sim_only_monatlich,
        "tarif_summe": summe,
        "tarif_quelle_url": referenz.quelle_url,
        "tarif_abgerufen_am": referenz.abgerufen_am,
        "geraet_betrag": geraet["betrag"],
        "geraet_quelle_url": geraet.get("quelle_url", ""),
        "geraet_abgerufen_am": geraet.get("abgerufen_am", ""),
        "monate": monate,
        "tarif_monate": tarif_monate,
        "gesamt": gesamt,
        "schnitt_monat": round(gesamt / monate, 2),
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
        "geraet_betrag": None,
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
        # DIE LEITZAHL TRAEGT IHRE EIGENE BINDUNG (A5.1; QA-Befund F-R2-2,
        # 04.09.2026). `ref["monate"]` ist das FENSTER des verglichenen
        # Buendels (36 bei o2), `ref["tarif_monate"]` das, was die Referenz
        # wirklich rechnet: 24 Tarifmonate plus Barkauf, und in Monat 25-36
        # bindet Vodafone gar nicht. Alle 30 Referenzkarten des Bestands
        # trugen "TCO-36" und "Gerechnet ueber 36 Monate Bindung" - eine
        # richtige Zahl unter einer falschen Aussage. Das Fenster bleibt am
        # Referenz-Dict (`monate`): daran haengen das Euro-Delta (`_delta`,
        # `gleiche_laufzeit`) und die Referenzlinie in G1, und beides ist
        # E-2 - eine Entscheidung Antonios, nicht dieser Karte. Geaendert ist
        # die BESCHRIFTUNG, nicht die Rechnung: 52 Deltas vorher, 52 nachher,
        # auf den Cent gleich.
        "label": f"TCO-{ref['tarif_monate']}",
        "laufzeit": ref["tarif_monate"],
        "fenster": ref["monate"],
        "belastbar": True, "naeherung": True,
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
            + ref["monatlich"] * min(LEITFRAGE_MONATE, ref["tarif_monate"]), 2),
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


def _vorgabe(modelle: list) -> str:
    """Welches Modell ohne Klick sichtbar ist.

    Das Lastenheft stellt seine Leitfrage woertlich an EINEM Geraet
    ("iPhone 17 Pro mit Tarif X bei Anbieter Y - was zahlt der Kunde ueber
    24 Monate gesamt?"), und die Abnahme (G3) prueft genau daran. Deshalb
    steht es vorn, sobald es mit mindestens zwei Anbietern rechenbar ist -
    und sonst faellt die Wahl auf das erste Modell der Liste. Eine
    Vorgabe, die an einem einzelnen Geraet haengt, waere ohne diesen
    Rueckfall ein Leerzustand, sobald Apple ein Modell umbenennt.
    """
    for modell in modelle:
        if modell["id"] == LEITFRAGE_MODELL and len(
                modell["anbieter_mit_zahl"]) >= 2:
            return modell["id"]
    return modelle[0]["id"] if modelle else ""


def modelle(buendel: list, listungen: list, referenzen: list, tarife: dict,
            katalog) -> dict:
    """Alle Modelle mit mindestens einem Buendel, je Modell vier Anbieter.

    Rueckgabe:
        modelle         [{id, name, hersteller, speicher, karten, referenz,
                          laufzeiten, spanne, anbieter_mit_zahl}]
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

    alle = list(buendel) + buendel_aus_listungen(listungen)
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
        # Schalter. Genommen wird die guenstigste.
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
            if bisher is None or (k["schnitt_monat"] or 9e9) < \
                    (bisher["schnitt_monat"] or 9e9):
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
            # Die Naeherung rechnet ueber die Laufzeit, die die meisten
            # Karten dieses Modells binden - so entsteht das Euro-Delta
            # dort, wo es etwas aussagt.
            referenz = _vodafone_referenz(referenzen, tarife, belege_modell,
                                          laufzeiten[-1] if laufzeiten else 0)
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
            "anbieter_mit_zahl": sorted({k["anbieter"] for k in angebote}),
        })

    # Die Reihenfolge des Auswahlfeldes: die meisten Anbieter zuerst - dort
    # beantwortet die Seite ihre Frage am vollstaendigsten -, dann nach
    # Namen. NICHT nach Preis: eine nach Betrag sortierte Modellliste ist
    # eine Rangliste des Marktes, und der Marktueberblick steht im Katalog.
    fertig.sort(key=lambda m: (-len(m["anbieter_mit_zahl"]), m["name"]))
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
