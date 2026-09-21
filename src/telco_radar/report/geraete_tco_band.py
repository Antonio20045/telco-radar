"""GRAPH-1: Gerät × Tarifniveau im Graphen (BRIEF_GRAPH1, 08.09.2026).

Die eine Frage, an der dieser Baustein gebaut ist
--------------------------------------------------
    "Iphone 17 Pro, Tarifband Mittel - was kostet dasselbe Gerät bei
     welchem Anbieter, wenn ich nach Datenvolumen vergleiche statt nach
     Tarifnamen?"

AUFTRAG_GERAETESEITE.md §2a verlangt die Kopplung Geraet x Tarifniveau,
eine Linie je Anbieter. §7 legt die drei Baender fest (Klein/Mittel/Gross),
abgeleitet aus den ERHOBENEN Datenvolumina von `tarife.jsonl` - nicht
erfunden, nicht gerundet.

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
import math
from typing import Optional

from . import geraete_tco_grafik
from .geraete_tco_karten import (ANBIETER_REIHENFOLGE,
                                 HAENDLER_OHNE_BUENDEL)
from .geraete_verlauf import farbe_fuer

# Die drei Baender aus AUFTRAG_GERAETESEITE.md §7 - entschieden am
# 05.09.2026 aus 56 erhobenen Tarifsaetzen (o2 15, Telekom 14, Vodafone 10,
# congstar 10, 1&1 7), je mindestens 12 Saetze und alle fuenf erhobenen
# Anbieter je Band. NICHT erfunden, NICHT gerundet auf "runde" GB-Zahlen.
BAENDER = (
    ("klein", "Klein", "bis 20 GB"),
    ("mittel", "Mittel", "21 bis 60 GB"),
    ("gross", "Groß", "über 60 GB"),
)
_BAND_LABEL = {k: (l, b) for k, l, b in BAENDER}

# Dieselben Anbieter wie die vier festen Karten der Hauptansicht
# (`geraete_tco_karten.ANBIETER_REIHENFOLGE`), UM CONGSTAR ERWEITERT: die
# Hauptansicht laesst congstar bewusst weg ("eine leere Zeile fuer jede
# denkbare Zweitmarke waere eine Wand aus Luecken"), aber BRIEF_GRAPH1
# nennt es ausdruecklich als eigene benannte Luecke neben Telekom und 1&1 -
# der Datenlage-Absatz zaehlt fuenf Anbieter, nicht vier. Ein weggelassener
# Anbieter sieht auf dieser Seite aus wie einen, den es nicht gibt
# (CLAUDE.md, dieselbe Regel wie B.2.5 im Lastenheft).
ERWARTETE_ANBIETER = ANBIETER_REIHENFOLGE + ("congstar",)


def band_von_gb(gb) -> Optional[str]:
    """Klein/Mittel/Gross - oder `None`: kein Band (fehlend ODER unbegrenzt).

    §7 zieht beide Faelle aus dem Raster: "13 der 56 Tarifsaetze tragen
    KEIN Datenvolumen ... fallen aus jedem Raster heraus" (fehlend, `gb`
    ist `None`) und "Unbegrenzt bleibt ausserhalb der Baender ... wird als
    Markierung am Tarif gefuehrt, nicht als Vergleichsstufe" (unbegrenzt,
    `tarife.jsonl` schreibt dafuer `Infinity`). Beide sind ehrlich `None`
    statt in ein Band gepresst zu werden - ein Tarif ohne Volumenangabe im
    Band "Gross" waere eine erfundene Aussage.
    """
    if gb is None:
        return None
    try:
        gb = float(gb)
    except (TypeError, ValueError):
        return None
    if math.isnan(gb) or math.isinf(gb):
        return None
    if gb <= 20:
        return "klein"
    if gb <= 60:
        return "mittel"
    return "gross"


def tarif_baender(tarife: dict) -> dict:
    """tarif_id -> Band, aus dem ERHOBENEN Datenvolumen von `tarife.jsonl`.

    `tarife` ist derselbe Bestand, den `geraete_tco_view.aufbereiten` schon
    fuer die Tarifbindung liest (`Tarifbestand.je_id_aktuell`, B3
    21.09.2026 - nicht `je_id`, sonst traegt die Bandkarte bei Telekom das
    Datenvolumen des Pflichtdokuments statt der aktuellen Lesart) - keine
    zweite Datenquelle, nur eine zweite Lesart derselben Datei.
    """
    out: dict = {}
    for tarif_id, tarif in (tarife or {}).items():
        band = band_von_gb((tarif or {}).get("datenvolumen_gb"))
        if band:
            out[tarif_id] = band
    return out


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
BAND_LEER_TEXT = ("Für dieses Gerät liegt in keinem Tarifband ein Bündel "
                  "vor – die Tarifband-Auswahl entsteht, sobald ein Anbieter "
                  "einen Tarif mit erhobenem Datenvolumen ausweist.")


def _chip(key: str) -> str:
    label, bereich = _BAND_LABEL[key]
    return f"Band {label} · {bereich}"


def band_label(band) -> str:
    """Das Band als lesbares Wort ('Klein'), leer wenn keins ist.

    O4: der TCO-Export traegt dieselbe Bezeichnung, die der Chip der
    Vergleichsansicht zeigt - ein 'klein' in der Spalte waere eine zweite
    Sprache fuer dieselbe Sache. Ein UNBEKANNTES Band wird mit seinem
    Schluessel benannt statt erraten (dieselbe Regel wie eine unbekannte
    Farbe in farben.yaml).
    """
    if not band:
        return ""
    if band in _BAND_LABEL:
        return _BAND_LABEL[band][0]
    return str(band)


def baender_fuer_modell(modell: dict, band_je_tarif: dict,
                        gb_je_tarif: dict | None = None) -> list[dict]:
    """Je Modell die Baender, fuer die es ECHTE Buendel gibt (§7/Aufgabe 1).

    Rueckgabe: eine Liste, EIN Eintrag je Band MIT mindestens einem echten
    Buendel - kein leeres Band wird als Auswahloption angeboten (Aufgabe 1:
    "pro Modell nur Bänder anbieten, für die Bündel existieren"). Je Eintrag:
        key, label, bereich   - siehe `BAENDER`
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
    for key, label, bereich in BAENDER:
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
            "chip": _chip(key),
        })
    return ergebnis
