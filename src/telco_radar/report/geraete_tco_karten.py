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
from typing import Optional

from .effektivpreis import phasensumme
from .geraete_tco_grafik import anbieter_slug
from ..geraete_model import VERGLEICHBARE_ZUSTAENDE, normalisiere
from ..tarif_model import Preisphase
from ..tco_model import (LEITFRAGE_MONATE, POSTEN_ANSCHLUSS, Buendel,
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
                tarif_name=e["tarif_referenz"],
                buendel_monatlich=float(betrag),
                laufzeit_monate=int(e.get("laufzeit_monate") or 24),
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
           katalog, geraet_je_sku: dict) -> dict:
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
        "sku_id": b.sku_id,
        "modell_id": modell_schluessel(device_id, speicher),
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
        "leer_grund": "",
    }


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
            "anschlusspreis": None, "nach_bindung": None,
            "eff_ohne_geraet": None, "eff_basis": None, "bestandteile": [],
            "luecken": [], "boni": [], "boni_abzug": 0.0, "quelle_url": "",
            "abgerufen_am": "", "tarif_quelle_url": "", "naeherung": False,
            "leer_grund": grund or LEER_GRUND.get(anbieter, ""),
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
    summe = phasensumme(phasen, monate) if phasen else None
    # "Fortgeschrieben" heisst: das Blatt sagt zu diesen Monaten nichts, und
    # es gilt der zuletzt belegte Preis weiter. Das ist die vorsichtige
    # Annahme (dieselbe wie in `phasensumme`), aber sie ist eine Annahme -
    # deshalb steht sie auf der Karte und nicht nur im Code.
    abgedeckt = 0
    for phase in phasen:
        abgedeckt = max(abgedeckt,
                        monate if phase.bis_monat is None else phase.bis_monat)
    fortgeschrieben = abgedeckt < monate
    if summe is None:
        summe = round(referenz.tarif_sim_only_monatlich * monate, 2)
        fortgeschrieben = True
    gesamt = round(summe + geraet["betrag"], 2)
    return {
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
        "tarif": ref["tarif"], "label": f"TCO-{ref['monate']}",
        "laufzeit": ref["monate"], "tarif_bindung": ref["monate"],
        "belastbar": True, "naeherung": True,
        "gesamt": ref["gesamt"], "schnitt_monat": ref["schnitt_monat"],
        "monatlich": ref["monatlich"],
        # Auch die Referenz beantwortet Antonios Frage: nach 24 Monaten hat
        # man den Barpreis laengst gezahlt und den Tarif fuer 24 Monate.
        "gezahlt_nach_24": round(
            ref["geraet_betrag"]
            + ref["monatlich"] * min(LEITFRAGE_MONATE, ref["monate"]), 2),
        "bestandteile": [
            {"name": f"Gerät ohne Vertrag · Barpreis",
             "betrag": ref["geraet_betrag"], "kategorie": "einmalig"},
            {"name": f"Tarif · {ref['monate']} Monate {ref['tarif']}",
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
    gleiche_laufzeit = karte["laufzeit"] == referenz["monate"]
    betrag = (round(karte["gesamt"] - referenz["gesamt"], 2)
              if gleiche_laufzeit else None)
    monatlich = round(karte["schnitt_monat"] - referenz["schnitt_monat"], 2)
    bezug = betrag if betrag is not None else monatlich
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
    return (not karte["belastbar"], karte["naeherung"],
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
        modelle   [{id, name, hersteller, speicher, karten, referenz,
                    laufzeiten, spanne, anbieter_mit_zahl}]
        vorgabe   die ID des Modells, das ohne Klick sichtbar ist
    """
    geraet_je_sku: dict = {}
    for e in listungen:
        if e.get("sku_id"):
            geraet_je_sku.setdefault(e["sku_id"], (e.get("device_id") or "",
                                                   e.get("speicher_gb")))
    belege = barpreise(listungen)

    alle = list(buendel) + buendel_aus_listungen(listungen)
    gruppen: dict = {}
    for b in alle:
        if not isinstance(b, Buendel) or b.ohne_geraet:
            continue
        device_id, speicher = geraet_je_sku.get(b.sku_id, ("", None))
        mid = modell_schluessel(device_id, speicher)
        tarif = tarife.get(b.tarif_id) if b.tarif_id else None
        karte = _karte(b, tarif, _barpreis_fuer(belege.get(b.sku_id, {}),
                                                b.anbieter),
                       katalog, geraet_je_sku)
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
        je_angebot: dict = {}
        for k in karten:
            schluessel = (k["anbieter"], k["tarif"], k["laufzeit"])
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
        eigene = [k for k in karten if k["eigen"] and k["belastbar"]]
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

        betraege = [k["gesamt"] for k in karten
                    if k["belastbar"] and k["gesamt"] is not None]
        fertig.append({
            "id": mid,
            "name": _name(katalog, gruppe["device_id"], gruppe["speicher"],
                          rueckfall=mid),
            "hersteller": _hersteller(katalog, gruppe["device_id"]),
            "speicher": gruppe["speicher"],
            "karten": karten,
            "referenz": referenz,
            "laufzeiten": laufzeiten,
            "angebote": len([k for k in karten if k["belastbar"]]),
            "spanne": ([min(betraege), max(betraege)] if betraege else []),
            "anbieter_mit_zahl": sorted({k["anbieter"] for k in karten
                                         if k["belastbar"]}),
        })

    # Die Reihenfolge des Auswahlfeldes: die meisten Anbieter zuerst - dort
    # beantwortet die Seite ihre Frage am vollstaendigsten -, dann nach
    # Namen. NICHT nach Preis: eine nach Betrag sortierte Modellliste ist
    # eine Rangliste des Marktes, und der Marktueberblick steht im Katalog.
    fertig.sort(key=lambda m: (-len(m["anbieter_mit_zahl"]), m["name"]))
    return {"modelle": fertig, "vorgabe": _vorgabe(fertig),
            "gesamt": len(fertig)}


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
        punkte = []
        for satz in historie.reihe(lid):
            betrag = satz.get("preis_ohne_vertrag")
            if betrag is None or not satz.get("datum"):
                continue
            punkte.append({"datum": satz["datum"], "betrag": float(betrag)})
        if len(punkte) < 2:
            continue
        device_id, speicher = je_sku.get(e.get("sku_id", ""), ("", None))
        reihen.append({
            "name": _name(katalog, device_id, speicher,
                          rueckfall=e.get("sku_id", "")),
            "anbieter": e.get("anbieter", ""),
            "modell_id": modell_schluessel(device_id, speicher),
            "quelle_url": e.get("quelle_url", ""),
            "punkte": punkte})
    return reihen
