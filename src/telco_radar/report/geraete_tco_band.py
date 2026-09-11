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

import math
from typing import Optional

from . import geraete_tco_grafik
from .geraete_tco_karten import ANBIETER_REIHENFOLGE
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
    fuer die Tarifbindung liest (`Tarifbestand.je_id`) - keine zweite
    Datenquelle, nur eine zweite Lesart derselben Datei.
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
    # kein Angebot.
    echte = [k for k in (modell.get("karten") or [])
             if k.get("belastbar") and not k.get("naeherung")
             and k.get("gesamt") is not None]

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
        ergebnis.append({
            "key": key, "label": label, "bereich": bereich,
            "grafik": geraete_tco_grafik.zeitreihe(
                reihen, messgroesse="TCO-24", klasse="gr-tcoband"),
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
        })
    return ergebnis
