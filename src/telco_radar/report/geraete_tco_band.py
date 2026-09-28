"""GRAPH-1: Gerät × Tarifniveau im Graphen (BRIEF_GRAPH1, 08.09.2026).

Die eine Frage, an der dieser Baustein gebaut ist
--------------------------------------------------
    "iPhone 17 Pro, Vodafone Mobil M - was kostet dasselbe Gerät bei
     welchem Anbieter, wenn ich nach Datenvolumen vergleiche statt nach
     Tarifnamen?"

AUFTRAG_GERAETESEITE.md §2a verlangt die Kopplung Geraet x Tarifniveau,
eine Linie je Anbieter. Die Stufen sind seit P3-E1 (28.09.2026) die
Vodafone-Tarifleiter (`tarifleiter`), abgeleitet aus den ERHOBENEN Saetzen
von `tarife.jsonl` - nicht erfunden, nicht gerundet. Die frueheren festen
Baender Klein/Mittel/Gross (bis 20 / 21-60 / ueber 60 GB) sind entfallen.

Warum hier keine echte Zeitreihe entsteht
------------------------------------------
`analyze/tco_store.TcoDB` fuehrt bewusst KEINE Preishistorie (siehe
Modulkopf dort: "Was hier bewusst NICHT steht ... keine Preishistorie -
beides braucht erst einen Lauf, der Buendel wirklich sammelt"). Jeder
Buendeldatensatz zeigt EINE Messung, `abgerufen_am`. Eine Linie "je
Anbieter ueber die Monate" ist deshalb heute genau das, was G0 fuer einen
einzelnen Messpunkt schon kennt: ein einzelner, ehrlich beschrifteter
Punkt ("Serie startet"). Sobald ein zweiter Lauf Buendel liefert, TRAEGT
`geraete_tco_grafik.zeitreihe()` automatisch eine echte Linie - dieselbe
Funktion wie fuer G0, hier nur unter der TCO-24-Beschriftung
(`messgroesse="TCO-24"`). Keine zweite Geometrie, keine erfundene
Zwischenstufe.

Die drei Regeln, die dieses Modul traegt
-----------------------------------------
1. **Gerechnet wird ausschliesslich in `tco_model`.** Dieses Modul liest
   die schon fertigen Karten aus `geraete_tco_karten.modelle()` (`gesamt`
   ist bereits `tco_24().gesamt`) und gruppiert sie nach Band - es addiert
   keinen Euro.
2. **Nur ECHTE Buendel, keine Naeherung.** Die Vodafone-Referenzkarte
   (`karte["naeherung"]`) ist kein Angebot, sondern ein Massstab - sie
   wuerde in einer Anbieter-Linie wie ein echtes Vodafone-Buendel aussehen.
3. **Ein Anbieter ohne Buendel in diesem Band wird BEIM NAMEN genannt**,
   nicht weggelassen - dasselbe Muster wie die Haendler-Luecken am
   Zeitreihen-Block (`gr-g0-haendler`).
"""
from __future__ import annotations

import datetime as _dt
import logging
import math
import re
from dataclasses import dataclass
from typing import Optional

from . import geraete_tco_grafik
from .anbieter_farben import farbe_fuer
from .geraete_tco_karten import (ANBIETER_REIHENFOLGE,
                                 HAENDLER_OHNE_BUENDEL)

log = logging.getLogger(__name__)

# P3-E1 (28.09.2026): die Tarifleiter. Bis hierher standen drei feste
# Baender (bis 20 GB, 21 bis 60 GB, ueber 60 GB) - eine Einteilung, die kein
# Anbieter verkauft. Jetzt ist die Leiter das Sortiment, gegen das die
# Seite vergleicht: die Vodafone-Tarife "mit Smartphone" aus
# `tarife.jsonl`, je Lauf neu abgeleitet (Stand 25.09.2026: XS 15 GB,
# S 30 GB, M 60 GB, L 120 GB, XL ohne erhobenes Volumen). Ein Wettbewerber
# faellt in die Stufe des naechstgelegenen Vodafone-Volumens.
#
# Die Stufe traegt den Namen, den Vodafone ihr gibt ("XS"), der Schluessel
# ist derselbe Name klein geschrieben ("xs") - `band_label` kehrt das um,
# ohne dass ein Leser die Leiter kennen muss.
_VODAFONE_MIT_SMARTPHONE = re.compile(
    r"^Vodafone Mobil (?P<stufe>[A-Z]{1,4}) mit Smartphone$")
# Vodafones eigene Tarife werden ueber den NAMEN zugeordnet, nicht ueber
# das Volumen: "Vodafone Mobil XS" (ohne Geraet, 18 GB) ist die Stufe XS,
# auch wenn ihr Volumen naeher an einer anderen laege. Und "Vodafone Mobil
# XL" traegt heute kein erhobenes Volumen, gehoert aber trotzdem zu XL.
_VODAFONE_STUFE = re.compile(
    r"^Vodafone Mobil (?P<stufe>[A-Z]{1,4})(?: mit Smartphone)?$")


@dataclass(frozen=True)
class Stufe:
    """Eine Sprosse der Tarifleiter: ein Vodafone-Tarif "mit Smartphone"."""
    key: str                  # "xs"
    label: str                # "XS"
    gb: Optional[float]       # erhobenes Volumen, inf = unbegrenzt, None = fehlt
    tarif_id: str
    name: str                 # "Vodafone Mobil XS mit Smartphone"
    grundgebuehr: Optional[float]

    @property
    def bereich(self) -> str:
        """Das Volumen der Stufe als Text ("15 GB"), leer wenn es fehlt."""
        return gb_text(self.gb)

# Dieselben Anbieter wie die vier festen Karten der Hauptansicht
# (`geraete_tco_karten.ANBIETER_REIHENFOLGE`), UM CONGSTAR ERWEITERT: die
# Hauptansicht laesst congstar bewusst weg ("eine leere Zeile fuer jede
# denkbare Zweitmarke waere eine Wand aus Luecken"), aber BRIEF_GRAPH1
# nennt es ausdruecklich als eigene benannte Luecke neben Telekom und 1&1 -
# der Datenlage-Absatz zaehlt fuenf Anbieter, nicht vier. Ein weggelassener
# Anbieter sieht auf dieser Seite aus wie einen, den es nicht gibt
# (CLAUDE.md, dieselbe Regel wie B.2.5 im Lastenheft).
ERWARTETE_ANBIETER = ANBIETER_REIHENFOLGE + ("congstar",)


def _zahl(wert) -> Optional[float]:
    """Ein Datenvolumen als Zahl - `None`, wenn es fehlt oder unlesbar ist.
    `inf` (unbegrenzt) bleibt `inf`: das ist eine Aussage, kein Loch."""
    if wert is None:
        return None
    try:
        zahl = float(wert)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(zahl) else zahl


def tarifleiter(tarife: dict) -> tuple[Stufe, ...]:
    """Die Vodafone-Tarife "mit Smartphone" als Leiter, guenstigste zuerst.

    Geordnet wird nach der Grundgebuehr, nicht nach dem Volumen: XL traegt
    heute kein erhobenes Volumen und stuende sonst an einer geratenen
    Stelle. Die Grundgebuehr steht in jedem Satz, und bei Vodafone steigt
    sie mit der Stufe. Eine Stufe erscheint einmal, auch wenn der Bestand
    sie unter zwei Lesarten fuehrt (`#live_shop`).

    Eine leere Leiter (kein Vodafone-Satz im Bestand) ist ein Ausfall der
    Erhebung, kein Ergebnis - `band_leer_text` sagt das auf der Seite
    (Leersatz des Graphen in `geraete.html.j2`).
    """
    je_key: dict[str, Stufe] = {}
    for tarif_id, satz in sorted((tarife or {}).items()):
        satz = satz or {}
        if (satz.get("anbieter") or "").strip().lower() != "vodafone":
            continue
        treffer = _VODAFONE_MIT_SMARTPHONE.match((satz.get("name") or "").strip())
        if not treffer:
            continue
        label = treffer.group("stufe")
        key = label.lower()
        if key in je_key:
            continue
        je_key[key] = Stufe(
            key=key, label=label, gb=_zahl(satz.get("datenvolumen_gb")),
            tarif_id=tarif_id, name=satz["name"].strip(),
            grundgebuehr=_zahl(satz.get("grundgebuehr")))
    if not je_key:
        log.warning("Tarifleiter: kein Vodafone-Tarif 'mit Smartphone' im "
                    "Tarifbestand - keine Tarifbaender.")
    return tuple(sorted(
        je_key.values(),
        key=lambda s: (s.grundgebuehr is None, s.grundgebuehr or 0.0,
                       s.gb is None, s.gb or 0.0, s.key)))


def band_von_gb(gb, leiter: tuple[Stufe, ...]) -> Optional[str]:
    """Die Stufe des naechstgelegenen Vodafone-Volumens - oder `None`.

    `None` heisst: nicht zuordenbar, und die Karte steht unter "Ohne
    Tarifband" statt in einer erfundenen Stufe. Das gilt fuer ein fehlendes
    Volumen und fuer "unbegrenzt", solange keine Vodafone-Stufe selbst als
    unbegrenzt erhoben ist; ist sie es, faellt unbegrenzt genau dorthin.
    Liegt ein Volumen genau zwischen zwei Stufen, zaehlt die groessere:
    wer 45 GB bietet, deckt die 30-GB-Stufe ganz ab.
    """
    zahl = _zahl(gb)
    if zahl is None:
        return None
    if math.isinf(zahl):
        for stufe in leiter:
            if stufe.gb is not None and math.isinf(stufe.gb):
                return stufe.key
        return None
    endlich = [s for s in leiter if s.gb is not None and not math.isinf(s.gb)]
    if not endlich:
        return None
    return min(endlich, key=lambda s: (abs(s.gb - zahl), -s.gb)).key


def _eigene_stufe(satz: dict, leiter: tuple[Stufe, ...]) -> Optional[str]:
    """Die Stufe eines Vodafone-Tarifs ueber seinen Namen (siehe
    `_VODAFONE_STUFE`) - `None` fuer jeden anderen Anbieter oder einen
    Vodafone-Tarif, dessen Stufe nicht auf der Leiter steht."""
    if (satz.get("anbieter") or "").strip().lower() != "vodafone":
        return None
    treffer = _VODAFONE_STUFE.match((satz.get("name") or "").strip())
    if not treffer:
        return None
    key = treffer.group("stufe").lower()
    return key if any(s.key == key for s in leiter) else None


def tarif_baender(tarife: dict,
                  leiter: Optional[tuple[Stufe, ...]] = None) -> dict:
    """tarif_id -> Stufe der Tarifleiter, aus demselben Tarifbestand.

    `tarife` ist derselbe Bestand, den `geraete_tco_view.aufbereiten` schon
    fuer die Tarifbindung liest (`Tarifbestand.je_id_aktuell`, B3
    21.09.2026 - nicht `je_id`, sonst traegt die Bandkarte bei Telekom das
    Datenvolumen des Pflichtdokuments statt der aktuellen Lesart) - keine
    zweite Datenquelle, nur eine zweite Lesart derselben Datei. Die Leiter
    kommt aus demselben Bestand, wenn sie nicht mitgegeben wird.
    """
    if leiter is None:
        leiter = tarifleiter(tarife)
    out: dict = {}
    for tarif_id, tarif in (tarife or {}).items():
        tarif = tarif or {}
        band = (_eigene_stufe(tarif, leiter)
                or band_von_gb(tarif.get("datenvolumen_gb"), leiter))
        if band:
            out[tarif_id] = band
    return out


def baender_katalog(leiter: tuple[Stufe, ...]) -> list[dict]:
    """Die Leiter als Auswahlkatalog: key, label, bereich - in Leiterfolge.

    EINMAL hier gebaut, damit Vorlage, Zeitreihe und Radar dieselben
    Stufen in derselben Reihenfolge nennen.
    """
    return [{"key": s.key, "label": s.label, "bereich": s.bereich}
            for s in leiter]


def gb_text(gb) -> str:
    """Das Datenvolumen als lesbarer Text - "18 GB", "unbegrenzt" oder ""

    P1 (11.09.2026): jede Bandkarte und jeder Eintrag der Band-Werteliste
    nennt sein Datenvolumen - ohne GB-Angabe ist eine Bandauswahl nicht
    nachpruefbar (UX-1). Unbegrenzt bleibt dabei „unbegrenzt“ und kein GB-
    Wert: §7 fuehrt es als Markierung ausserhalb der Bänder, nicht als
    Vergleichsstufe. Dasselbe gilt fuer `float('inf')`, das der echte
    Tarifbestand dafuer schreibt.
    """
    if gb is None:
        return ""
    try:
        wert = float(gb)
    except (TypeError, ValueError):
        return ""
    if math.isnan(wert):
        return ""
    if math.isinf(wert):
        return "unbegrenzt"
    # :g laesst 18.0 zu "18" werden und haelt 7.5 als "7.5" - die Seite
    # schreibt Nachkommastellen nur, wenn das Erhobene sie hat.
    return f"{wert:g} GB"


def _eigen(anbieter: str) -> bool:
    return (anbieter or "").strip().lower() == "vodafone"


def _reihe(anbieter: str, karte: dict) -> dict:
    """Eine Ein-Punkt-Reihe aus der guenstigsten Karte dieses Anbieters -
    dasselbe Reihenformat, das `geraete_verlauf._reihen` fuer G0 baut
    (`anbieter`/`farbe`/`eigen`/`punkte`), damit `geraete_tco_grafik.
    zeitreihe()` ohne Sonderfall zeichnet."""
    return {
        "anbieter": anbieter, "farbe": farbe_fuer(anbieter),
        "eigen": _eigen(anbieter),
        "punkte": [{"datum": karte.get("abgerufen_am") or "",
                    "preis": karte["gesamt"]}],
        "tarif": karte.get("tarif", ""),
        "quelle_url": karte.get("quelle_url", ""),
    }


def _grund(anbieter: str, hat_irgendein_buendel: bool) -> str:
    """Warum dieser Anbieter in diesem Band keine Linie traegt.

    Zwei Faelle, unterschieden: der Anbieter liefert fuer dieses Geraet
    UEBERHAUPT kein Buendel (die Formulierung, die BRIEF_GRAPH1 fuer
    Telekom woertlich vorgibt), oder er liefert welche, nur keins in DIESEM
    Band (ein anderes Datenvolumen).
    """
    if not hat_irgendein_buendel:
        return f"Bündel seitens {anbieter} noch nicht erhoben."
    return f"{anbieter} führt für dieses Gerät kein Bündel in diesem Band."


def alle_karten_je_band(modell: dict,
                        band_je_tarif: dict) -> dict[str, dict[str, list]]:
    """Je Band ALLE echten Karten jedes Anbieters, nach Gesamt sortiert.

    Rueckgabe: `{band_key: {anbieter: [karte, ...]}}` - nur Baender mit
    mindestens einem echten Buendel stehen darin, und je Anbieter steht
    die GUENSTIGSTE Karte zuerst (ks[0] ist dieselbe Karte, die
    `karten_je_band` liefert). Diese Funktion ist der EINE Ort, an dem
    "Geraet x Tarifband" gruppiert wird; der Graph (`karten_je_band` via
    `baender_fuer_modell`) liest die guenstigste Karte je Anbieter, der
    Wettbewerbs-Radar (RAD-1b) liest ALLE - ein Anbieter, der dasselbe
    Geraet in ZWEI Tarifen desselben Bandes fuehrt (Telekom XS/S/M alle
    im Band Klein), hat auch ZWEI Vergleichspaare, nicht eines.
    """
    # Nur ECHTE Buendel (Regel 2 des Modulkopfs) - die Naeherungskarte ist
    # kein Angebot. Und seit A3 nur FRISCHE: Balken-JSON und Radar lesen
    # hier ihre guenstigste Karte je Anbieter, und ein altes Angebot ist
    # keine Zahl von heute (`geraete_tco_karten.ist_frisch`, Clean Code 7).
    echte = [k for k in (modell.get("karten") or [])
             if k.get("belastbar") and not k.get("naeherung")
             and k.get("gesamt") is not None and k.get("frisch", True)]

    je_band: dict[str, dict[str, list]] = {}
    for k in echte:
        band = band_je_tarif.get(k.get("tarif_id") or "")
        if not band:
            continue          # kein Datenvolumen erhoben oder unbegrenzt
        je_band.setdefault(band, {}).setdefault(k["anbieter"], []).append(k)
    for je_anbieter in je_band.values():
        for karten in je_anbieter.values():
            karten.sort(key=lambda k: k["gesamt"])
    return je_band


def karten_je_band(modell: dict, band_je_tarif: dict) -> dict[str, dict]:
    """Je Band die guenstigste ECHTE Karte jedes Anbieters (Regel 1-3 oben).

    Rueckgabe: `{band_key: {anbieter: karte}}` - nur Baender mit mindestens
    einem echten Buendel stehen darin. Diese Funktion ist der EINE Ort, an
    dem "Geraet x Tarifband" gruppiert wird; `baender_fuer_modell` (der
    Graph) und `wettbewerbs_radar` (die %-Abweichung, RAD-1) lesen beide
    von hier - keine zweite Gruppierung fuer dieselbe Frage.
    """
    alle = alle_karten_je_band(modell, band_je_tarif)
    # Die GUENSTIGSTE Karte dieses Anbieters in diesem Band traegt die
    # Linie - dieselbe Wahl wie ueberall auf dieser Seite (ein
    # Anbieter, eine Zahl je Ort). `alle_karten_je_band` sortiert nach
    # Gesamt, also ist ks[0] genau diese Karte.
    return {band: {anbieter: ks[0] for anbieter, ks in je_anbieter.items()}
            for band, je_anbieter in alle.items()}


def anbieter_mit_irgendeinem_buendel(modell: dict) -> set:
    """Wer fuer dieses Geraet UEBERHAUPT ein echtes Buendel fuehrt - in
    IRGENDEINEM Band. Getrennt von `karten_je_band`, weil `_grund` beide
    Mengen braucht (siehe dort)."""
    return {k["anbieter"] for k in (modell.get("karten") or [])
            if k.get("belastbar") and not k.get("naeherung")
            and k.get("gesamt") is not None}


# --------------------------------------------------------------------------
# O1 (STRATEGIE_GERAETE_OPTIK, 11.09.2026): der EINE Balkengraph
# --------------------------------------------------------------------------

def _minus(zahl: float) -> str:
    """Das echte Minus (U+2212), nicht der Bindestrich der Tastatur.

    Der Entwurf schreibt "−466,80 € · −29,9 %" - das Vorzeichen ist Teil
    der Zahl und wird nicht durch einen Trennstrich ersetzt. Dieselbe
    Konvention wie im Rest des Portals (SVG-Marker, G2-Pfeile).
    """
    return f"{abs(zahl):,.2f}".replace(",", "#").replace(".", ",") \
        .replace("#", ".")


# Der Beginn der Beschaffung bei Händlern ohne Tarifbündel - dieselbe
# Konstante, die bis O1 als `haendler_seit` in der Vorlage stand. Sie ist
# hierher gezogen, weil die Legendenzeile des Graphen sie jetzt im
# Python-Satz trägt (F-6: "Beschaffung läuft" allein wirkte unfertig statt
# geplant - der Beginn der Beschaffung ist belegt, ein Lieferdatum wäre
# erfunden).
HAENDLER_SEIT = "2026-09-05"

_MONATE = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
           "August", "September", "Oktober", "November", "Dezember")


def _datum_de(iso: str) -> str:
    """Dasselbe Format wie `html._fmt_date_de` - als Mini-Abbildung hier,
    weil ein Import quer durch die Renderkette zirkulär wäre (html.py
    lädt geraete_view, das geraete_tco_view lädt, das dieses Modul lädt)."""
    try:
        d = _dt.date.fromisoformat(iso)
        return f"{d.day}. {_MONATE[d.month - 1]} {d.year}"
    except ValueError:
        return iso


def delta_text(euro: Optional[float], prozent: Optional[float],
               ungefaehr: bool = False) -> Optional[str]:
    """"−466,80 € · −29,9 %" - EINE Stelle für dieses Format.

    Diese Zeichenkette entsteht hier in Python und wird von Vorlage UND
    `app.js` nur noch gesetzt - eine zweite Formatierung im Browser waere
    eine zweite Beschriftung fuer dieselbe Zahl (CLAUDE.md §6).

    Seit O2 (11.09.2026) liest sie auch die Buendel-ZEILE der Vergleichs-
    ansicht (`geraete_tco_view` haengt sie als `delta_kurz` an die Karte):
    Graph und Zeile tragen dieselbe Zeichenkette, nicht zwei Formate fuer
    dieselbe Differenz. Deshalb ist sie kein `_`-Privatweg mehr.

    A2 (20.09.2026): `ungefaehr` fuer einen Abstand UNTER der Wesentlich-
    keits-Schwelle - "≈ ±X €" mit dem echten Betrag statt des Strichs,
    der "kein Angebot" heisst. Ohne Prozentanteil: Zehntel-Prozent an
    einer Annäherung waeren Scheingenaugkeit. Exakt null heisst "±".
    """
    if euro is None:
        return None
    if ungefaehr:
        zeichen = "±" if not euro else ("−" if euro < 0 else "+")
        return f"≈ {zeichen}{_minus(euro)} €"
    zeichen = "−" if euro < 0 else "+"
    text = f"{zeichen}{_minus(euro)} €"
    if prozent is not None:
        text += f" · {zeichen}{prozent:,.1f}".replace(".", ",") + " %"
    return text


def _balken(je_anbieter: dict[str, list], gb_je_tarif: dict,
            haendler_preise: dict | None) -> dict:
    """Zeilen, Referenz und Lücken des EINEN Graphen - ein Band.

    O1 (STRATEGIE_GERAETE_OPTIK §2): sortierte horizontale Balken
    "TCO-24 je Anbieter", der Wert GEDRUCKT, Δ zur Vodafone-Referenz
    DESSELBEN Bandes, Vodafone als Emphasis. Gerechnet wird nichts: jede
    Zeile liest `gesamt` aus der Karte, die `tco_24()` schon gerechnet
    hat (Regel 1 des Modulkopfs); Δ ist Differenzbildung wie in
    `geraete_tco_karten._delta`.

    Drei Zusicherungen, die der Graph von seinen Zeilen verlangt:
      * NUR ECHTE Bündel (Regel 2 des Modulkopfs): die Näherungskarte ist
        kein Angebot und wäre als Vodafone-Zeile nicht von einem zu
        unterscheiden.
      * NUR NEUE Geräte: ein erneuertes ist eine andere Preisdimension
        (QA-Befund B1) und darf die Anbieter-Zeile nicht unterbieten. Ein
        Anbieter mit ausschließlich erneuerten Bündeln im Band steht als
        Name in der EINEN Legendenzeile, nicht als Zeile.
      * EIN Δ-Bezug: die günstigste eigene Karte IM SELBEN BAND. Gibt es
        keine, gibt es kein Δ (der Entwurf sagt es im Band Groß wörtlich:
        "Vodafone fehlt in diesem Band - keine Δ-Angabe") - die Näherung
        der Karten ist ein Maßstab und wird nicht heimlich zur Referenz
        des Graphen.
    """
    # Zeilen: die guenstigste vergleichbare (NEUE) Karte je Anbieter.
    zeilen_je_anbieter: dict[str, dict] = {}
    erneuert: set[str] = set()
    for anbieter, karten in je_anbieter.items():
        neu = [k for k in karten if k.get("vergleichbar")]
        if neu:
            zeilen_je_anbieter[anbieter] = neu[0]   # sortiert nach gesamt
        else:
            erneuert.add(anbieter)

    eigene = [k for k in zeilen_je_anbieter.values() if _eigen(k["anbieter"])]
    referenz = min(eigene, key=lambda k: k["gesamt"]) if eigene else None

    zeilen = []
    for anbieter, karte in zeilen_je_anbieter.items():
        ist_ref = referenz is not None and karte is referenz
        delta_euro = (None if referenz is None or ist_ref else
                      round(karte["gesamt"] - referenz["gesamt"], 2))
        delta_prozent = (None if delta_euro is None else
                         round(abs(delta_euro) / referenz["gesamt"] * 100, 1))
        zeilen.append({
            "anbieter": anbieter,
            "slug": geraete_tco_grafik.anbieter_slug(anbieter),
            "eigen": _eigen(anbieter),
            "tarif": karte.get("tarif", ""),
            "gb": gb_text((gb_je_tarif or {}).get(karte.get("tarif_id") or "")),
            # DSELBE Zahl wie Karte und Tabelle - `gesamt` ist schon
            # `tco_24().gesamt` (Regel 1 des Modulkopfs).
            "gesamt": karte["gesamt"],
            "gesamt_text": geraete_tco_grafik.euro(karte["gesamt"]),
            # Balkenbreite proportional zum Wert; der laengste ist 100 %
            # (gesetzt, sobald alle Zeilen stehen - siehe unten).
            "breite": 0.0,
            "delta_euro": delta_euro,
            "delta_prozent": delta_prozent,
            "delta_text": delta_text(delta_euro, delta_prozent),
            "referenz": ist_ref,
            "zustand_etikett": karte.get("zustand_etikett") or "",
        })
    zeilen.sort(key=lambda z: z["gesamt"])
    maximum = max((z["gesamt"] for z in zeilen), default=0.0)
    for z in zeilen:
        z["breite"] = round(z["gesamt"] / maximum * 100, 1) if maximum else 0.0

    # Die EINE Legendenzeile: Namen, gruppiert nach Grund - kein Satz je
    # Anbieter mehr (die 145 "fuehrt kein Buendel in diesem Band"-
    # Einzelizeilen der alten Band-Panels entfallen mit dem Graphen).
    ohne = sorted(a for a in ERWARTETE_ANBIETER
                  if a not in zeilen_je_anbieter and a not in erneuert)
    haendler = sorted(h for h in HAENDLER_OHNE_BUENDEL
                      if not (haendler_preise or {}).get(h))
    # Der fertige Satz der EINEN Legendenzeile - in Python gebaut, weil
    # Vorlage UND app.js ihn nur setzen (keine zweite Satzbaustelle im
    # Browser). Keine Lücke, keine Zeile - dann steht auch kein leeres
    # "Kein Bündel:" mit Doppelpunkt ohne Namen da.
    teile = []
    if ohne:
        teile.append("Kein Bündel in diesem Band: " + ", ".join(ohne))
    if erneuert:
        teile.append("Nur erneuerte Geräte im Band: " + ", ".join(sorted(erneuert)))
    if haendler:
        teile.append("Beschaffung läuft seit "
                     + _datum_de(HAENDLER_SEIT) + ": " + ", ".join(haendler))
    return {
        "zeilen": zeilen,
        "referenz_da": referenz is not None,
        "luecke": {"kein_buendel": ohne, "nur_erneuert": sorted(erneuert),
                   "haendler": haendler},
        "luecke_text": " · ".join(teile) or None,
    }


def _unterzeile(balken: dict) -> str:
    """Die EINE Chart-Chrome-Zeile unter dem Graph-Titel.

    O3 (15.09.2026): „Vodafone FEHLT in diesem Band" nach dem Wortlaut des
    freigegebenen Entwurfs (docs/entwuerfe/geraete-optik-2026-09-11/
    entwurf.html, `unterzeile` im Datenblock) statt „FÜHRT kein Bündel in
    diesem Band" - ein Band ohne eigene Referenz ist eine Lücke der
    Erhebung, keine Feststellung über das Sortiment.
    """
    if balken["referenz_da"]:
        return ("Günstigstes Bündel je Anbieter im gewählten Band · "
                "Δ = Abstand zur Vodafone-Referenz")
    return ("Günstigstes Bündel je Anbieter im gewählten Band · Vodafone "
            "fehlt in diesem Band – keine Δ-Angabe")


# Der Leerlauf des Graphen für ein Modell ohne ein einziges Band - der
# Satz steht hier EINMAL und wird von Vorlage und `app.js` nur gesetzt
# (derselben Regel wie die Übersetzungs-Linkbeschriftung: steht ein Text
# zweimal im Code, hält ihn ein Test zusammen - hier hält ihn der Test an
# genau dieser Konstanten).
# Die Leiter selbst fehlt: dann gibt es fuer KEIN Geraet eine Stufe, und
# der Grund ist die Erhebung, nicht das Sortiment (Regel 9 aus CLAUDE.md).
LEITER_FEHLT_TEXT = ("Vodafone-Tarifleiter nicht erhoben – ohne sie gibt es "
                     "keine Tarifstufen zum Vergleich.")


def band_leer_text(leiter: tuple[Stufe, ...]) -> str:
    """Der Leersatz des Graphen: fehlende Leiter oder kein Bündel."""
    return BAND_LEER_TEXT if leiter else LEITER_FEHLT_TEXT


BAND_LEER_TEXT = ("Für dieses Gerät liegt in keinem Tarifband ein Bündel "
                  "vor – die Tarifband-Auswahl entsteht, sobald ein Anbieter "
                  "einen Tarif mit erhobenem Datenvolumen ausweist.")


def _chip(stufe: Stufe) -> str:
    """"Band XS · 15 GB" - ohne erhobenes Volumen nur "Band XL"."""
    return f"Band {stufe.label}" + (f" · {stufe.bereich}" if stufe.bereich
                                    else "")


def band_label(band) -> str:
    """Die Stufe als lesbarer Name ('XS'), leer wenn keine ist.

    O4: der TCO-Export traegt dieselbe Bezeichnung, die der Chip der
    Vergleichsansicht zeigt. Der Schluessel ist Vodafones Stufenname klein
    geschrieben (`tarifleiter`), der Name ist er gross geschrieben - dafuer
    braucht kein Leser die Leiter.
    """
    return str(band).upper() if band else ""


def baender_fuer_modell(modell: dict, band_je_tarif: dict,
                        gb_je_tarif: dict | None = None,
                        leiter: tuple[Stufe, ...] = ()) -> list[dict]:
    """Je Modell die Baender, fuer die es ECHTE Buendel gibt (§7/Aufgabe 1).

    Rueckgabe: eine Liste, EIN Eintrag je Band MIT mindestens einem echten
    Buendel - kein leeres Band wird als Auswahloption angeboten (Aufgabe 1:
    "pro Modell nur Bänder anbieten, für die Bündel existieren"). Je Eintrag:
        key, label, bereich   - die Stufe der `leiter`
        grafik                 - `geraete_tco_grafik.zeitreihe(...)`,
                                  Y-Achse TCO-24 (Aufgabe 3)
        fehlend                 - [{"anbieter","grund"}] fuer jeden
                                  erwarteten Anbieter ohne Linie in diesem
                                  Band (Aufgabe 4)
        werte (P1, 11.09.2026) - [{"anbieter","slug","eigen","tarif","gb",
                                  "gesamt"}] je Anbieter MIT Linie: die
                                  exakten TCO-24 als SICHTBARER TEXT unter
                                  dem Chart, nicht nur im Hover-Tooltip, den
                                  es am Telefon nicht gibt (UX-5). `gb`
                                  braucht `gb_je_tarif` (tarif_id ->
                                  Datenvolumen, dieselbe Datei wie
                                  `band_je_tarif`); ohne es steht "" da.
    """
    gb_je_tarif = gb_je_tarif or {}
    je_band = karten_je_band(modell, band_je_tarif)
    alle_je_band = alle_karten_je_band(modell, band_je_tarif)
    mit_irgendeinem_buendel = anbieter_mit_irgendeinem_buendel(modell)

    ergebnis = []
    for stufe in leiter:
        key, label, bereich = stufe.key, stufe.label, stufe.bereich
        karten_je_anbieter = je_band.get(key)
        if not karten_je_anbieter:
            continue           # kein einziges Buendel in diesem Band
        # DSELBE Ordnung wie die Reihen der Grafik: der eigene Anbieter
        # zuerst, dann nach Name - Werteliste und Chart nennen dieselben
        # Anbieter in derselben Reihenfolge, sonst sucht der Leser eine
        # Zahl an der falschen Stelle.
        geordnet = sorted(karten_je_anbieter.items(),
                          key=lambda kv: (not _eigen(kv[0]), kv[0]))
        reihen = [_reihe(anbieter, karte) for anbieter, karte in geordnet]
        vorhanden = set(karten_je_anbieter)
        fehlend = [{"anbieter": a,
                    "grund": _grund(a, a in mit_irgendeinem_buendel)}
                   for a in ERWARTETE_ANBIETER if a not in vorhanden]
        # O1: der EINE Balkengraph dieses Bandes. Die Händlerpreise stehen
        # am Modell (`geraete_tco_view` setzt sie VOR den Bändern) - ein
        # Händler mit Preis gehört nicht in die Legende, er steht als
        # Händlerkarte in der Kartenklappe.
        balken = _balken(alle_je_band.get(key) or {}, gb_je_tarif,
                         modell.get("haendler_ohne_buendel"))
        ergebnis.append({
            "key": key, "label": label, "bereich": bereich,
            "grafik": geraete_tco_grafik.zeitreihe(
                reihen, messgroesse="Kosten über 24 Monate",
                klasse="gr-tcoband"),
            "fehlend": fehlend,
            "werte": [{
                "anbieter": anbieter,
                "slug": geraete_tco_grafik.anbieter_slug(anbieter),
                "eigen": _eigen(anbieter),
                "tarif": karte.get("tarif", ""),
                "gb": gb_text((gb_je_tarif or {}).get(
                    karte.get("tarif_id") or "")),
                # DSELBE Zahl wie Graph, Karte und Tabelle - `gesamt` ist
                # schon `tco_24().gesamt` (Regel 1 des Modulkopfs).
                "gesamt": karte["gesamt"],
                "abgerufen_am": karte.get("abgerufen_am", ""),
            } for anbieter, karte in geordnet],
            # ---- O1 (11.09.2026): der EINE Balkengraph ----------------
            # `grafik`/`werte`/`fehlend` bleiben gefuellt: Deren Renderer
            # ist in der Vorlage gekappt (O1), die Felder bleiben fuer
            # O4 erreichbar - dieselbe Kappe wie bei G1 (BRIEF_FADEN).
            "balken": balken,
            "unterzeile": _unterzeile(balken),
            "chip": _chip(stufe),
        })
    return ergebnis
