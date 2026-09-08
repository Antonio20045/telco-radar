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


def baender_fuer_modell(modell: dict, band_je_tarif: dict) -> list[dict]:
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
    """
    # Nur ECHTE Buendel (Regel 2 des Modulkopfs) - die Naeherungskarte ist
    # kein Angebot.
    echte = [k for k in (modell.get("karten") or [])
             if k.get("belastbar") and not k.get("naeherung")
             and k.get("gesamt") is not None]
    anbieter_mit_irgendeinem_buendel = {k["anbieter"] for k in echte}

    je_band: dict[str, dict] = {}
    for k in echte:
        band = band_je_tarif.get(k.get("tarif_id") or "")
        if not band:
            continue          # kein Datenvolumen erhoben oder unbegrenzt
        bisher = je_band.setdefault(band, {})
        vorhandene = bisher.get(k["anbieter"])
        # Die GUENSTIGSTE Karte dieses Anbieters in diesem Band traegt die
        # Linie - dieselbe Wahl wie ueberall auf dieser Seite (ein
        # Anbieter, eine Zahl je Ort).
        if vorhandene is None or k["gesamt"] < vorhandene["gesamt"]:
            bisher[k["anbieter"]] = k

    ergebnis = []
    for key, label, bereich in BAENDER:
        karten_je_anbieter = je_band.get(key)
        if not karten_je_anbieter:
            continue           # kein einziges Buendel in diesem Band
        reihen = [_reihe(anbieter, karte)
                  for anbieter, karte in sorted(karten_je_anbieter.items(),
                                                key=lambda kv: (not _eigen(kv[0]),
                                                               kv[0]))]
        vorhanden = set(karten_je_anbieter)
        fehlend = [{"anbieter": a,
                    "grund": _grund(a, a in anbieter_mit_irgendeinem_buendel)}
                   for a in ERWARTETE_ANBIETER if a not in vorhanden]
        ergebnis.append({
            "key": key, "label": label, "bereich": bereich,
            "grafik": geraete_tco_grafik.zeitreihe(
                reihen, messgroesse="TCO-24", klasse="gr-tcoband"),
            "fehlend": fehlend,
        })
    return ergebnis
