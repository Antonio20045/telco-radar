"""Wer ist guenstiger als Vodafone - und um wie viel?

DIE FRAGE, WEGEN DER DIESE SEKTION EXISTIERT
--------------------------------------------
Die interne Loesung der Fachkollegen zeigt, DASS ein Geraet irgendwo
guenstiger ist. Sie zeigt nicht, BEI WEM. Fuer eine Wettbewerbsanalyse ist
genau das die Auskunft: ein Preisabstand ohne Namen ist eine Zahl, mit Namen
ist er eine Handlungsoption. Deshalb nennt jede Zeile hier den guenstigsten
Wettbewerber beim Namen, und der Aufklapper nennt ALLE, die unter Vodafone
liegen - nicht nur den ersten.

VIER REGELN, DIE DIESE DATEI TRAGEN
-----------------------------------
1. **Kein Vergleich ohne beide Belege.** Eine Zeile entsteht nur, wenn BEIDE
   Seiten eine Quelladresse UND ein Abrufdatum tragen. Das ist keine
   Formalie: die ganze Seite verspricht, dass jede Zahl nachpruefbar ist,
   und ein Preisvergleich ist die Zahl, die am ehesten jemand bestreitet.
   `_belegt()` erzwingt es, ein Test stellt den Fall.

2. **Die zwei Preisarten werden nie gegeneinander gerechnet.** Eine
   Zuzahlung von 49,95 EUR im Tarifbuendel ist nicht "1300 EUR guenstiger"
   als ein Ladenpreis von 1349,90 EUR - sie ist eine andere Groesse. Die
   Preisart steht im Schluessel, nicht in einer Fussnote.

3. **Der ZUSTAND steht im Schluessel.** Dieselbe Lehre wie bei der
   Positionskarte (11.08.2026): ohne ihn schluckt ein refurbished-Preis den
   Neupreis desselben Geraets, und die Seite meldete einen Preisvorteil, den
   es nicht gibt.

4. **Verglichen werden LAEDEN, nicht Marken.** mobilcom-debitel und freenet
   sind derselbe Shop; als zwei Wettbewerber gezaehlt stuende dasselbe
   Angebot zweimal in der Liste "N Anbieter guenstiger als Vodafone".

Die Gegenrichtung ist selbst ein Befund: was Wettbewerber fuehren und
Vodafone nicht, steht in einer eigenen kurzen Zeile. Eine Luecke im eigenen
Regal ist eine Auskunft, kein fehlender Datensatz.
"""

from __future__ import annotations

from typing import Optional

from ..geraete_model import (
    STATUS_AKTIV,
    STATUS_VERMUTLICH,
    VERGLEICHBARE_ZUSTAENDE,
    ratenhinweis_aus_eintrag,
)

WESENTLICH_PROZENT = 3.0
WESENTLICH_EURO = 15.0

UEBERSICHT_MAX_ZEILEN = 14


def ist_wesentlich(zeile: dict) -> bool:
    """Traegt diese Zeile eine Aussage, oder ist sie Rauschen?"""
    if not zeile.get("bester"):
        return False
    return (zeile.get("prozent") or 0) >= WESENTLICH_PROZENT or (
        zeile.get("differenz") or 0
    ) >= WESENTLICH_EURO


EIGEN = ("vodafone",)

OHNE_VERTRAG = "ohne_vertrag"
MIT_VERTRAG = "mit_vertrag"

_SICHTBAR = (STATUS_AKTIV, STATUS_VERMUTLICH)


def _ist_eigen(anbieter: str) -> bool:
    return (anbieter or "").strip().lower() in EIGEN


def _laden(eintrag: dict, laeden: Optional[dict] = None) -> str:
    """Der LADEN hinter dem Anbieternamen.

    `laeden` bildet Anbietername -> Ladenname ab (aus `shop` in
    geraete_quellen.yaml). Ohne die Abbildung ist jeder Anbieter sein
    eigener Laden - dann verhaelt sich diese Datei wie vorher.
    """
    name = eintrag.get("anbieter") or ""
    return (laeden or {}).get(name, name)


def _preis(eintrag: dict) -> tuple[Optional[float], str]:
    """Den einen Preis dieser Listung samt seiner Art.

    Reihenfolge ist keine Vorliebe, sondern Definition: eine Listung mit
    Ladenpreis IST eine Listung ohne Vertrag, auch wenn derselbe Haendler
    daneben ein Buendel fuehrt.
    """
    ohne = eintrag.get("preis_ohne_vertrag")
    if ohne is not None:
        return float(ohne), OHNE_VERTRAG
    zuzahlung = eintrag.get("zuzahlung")
    if zuzahlung is not None and (eintrag.get("tarif_referenz") or "").strip():
        return float(zuzahlung), MIT_VERTRAG
    return None, ""


def _belegt(eintrag: dict) -> bool:
    """Traegt diese Listung Quelle UND Abrufdatum?"""
    return bool(
        (eintrag.get("quelle_url") or "").strip()
        and (eintrag.get("abgerufen_am") or "").strip()
    )


def _angebot(eintrag: dict, laeden: Optional[dict] = None) -> dict:
    preis, _ = _preis(eintrag)
    return {
        "anbieter": eintrag.get("anbieter") or "",
        "laden": _laden(eintrag, laeden),
        "typ": eintrag.get("anbieter_typ") or "",
        "preis": preis,
        "url": eintrag.get("quelle_url") or "",
        "abgerufen_am": eintrag.get("abgerufen_am") or "",
        "farbe": eintrag.get("farbe_normalisiert") or eintrag.get("farbe_roh") or "",
        "tarif": (eintrag.get("tarif_referenz") or "").strip(),
        "ratenhinweis": ratenhinweis_aus_eintrag(eintrag),
        "verfuegbarkeit": eintrag.get("verfuegbarkeit") or "unbekannt",
        "zustand": eintrag.get("zustand") or "neu",
        "listung_id": eintrag.get("id") or "",
    }


def _guenstigstes_je_laden(eintraege: list, laeden: Optional[dict]) -> list:
    """Je Laden das guenstigste belegte Angebot.

    Ein Haendler fuehrt dasselbe Geraet in fuenf Farben; fuer die Frage
    "wer ist guenstiger" zaehlt sein bester Preis, nicht fuenfmal derselbe
    Laden.
    """
    beste: dict[str, dict] = {}
    for e in eintraege:
        preis, _ = _preis(e)
        if preis is None or not _belegt(e):
            continue
        schluessel = _laden(e, laeden)
        vorher = beste.get(schluessel)
        if vorher is None or preis < vorher["preis"]:
            beste[schluessel] = _angebot(e, laeden)
    return sorted(beste.values(), key=lambda a: a["preis"])


def vergleich(
    eintraege: list,
    katalog,
    laeden: Optional[dict] = None,
    preisart: str = OHNE_VERTRAG,
) -> dict:
    """Je (Modell, Speicher, Zustand) eine Zeile - fuer alles, was Vodafone hat.

    Gibt zusaetzlich `ohne_vodafone`: was Wettbewerber fuehren und Vodafone
    nicht. Diese Liste ist absichtlich kurz gehalten und nach der Zahl der
    Wettbewerber sortiert - eine Luecke, die drei Haendler fuellen, ist eine
    andere Aussage als eine, die einer fuellt.
    """
    gruppen: dict[tuple, list] = {}
    for e in eintraege:
        if e.get("status") not in _SICHTBAR:
            continue
        preis, art = _preis(e)
        if preis is None or art != preisart:
            continue
        if (e.get("zustand") or "neu") not in VERGLEICHBARE_ZUSTAENDE:
            continue
        schluessel = (
            e.get("device_id"),
            e.get("speicher_gb"),
            e.get("zustand") or "neu",
        )
        gruppen.setdefault(schluessel, []).append(e)

    zeilen = []
    ohne_vodafone = []
    for (gid, speicher, zustand), gruppe in gruppen.items():
        geraet = katalog.nach_id(gid) if katalog else None
        modell = geraet.modell if geraet else gid
        hersteller = geraet.hersteller if geraet else ""

        eigene = [e for e in gruppe if _ist_eigen(e.get("anbieter", ""))]
        fremde = [e for e in gruppe if not _ist_eigen(e.get("anbieter", ""))]
        wettbewerb = _guenstigstes_je_laden(fremde, laeden)

        kopf = {
            "device_id": gid,
            "modell": modell,
            "hersteller": hersteller,
            "speicher": speicher,
            "zustand": zustand,
            "segment": geraet.segment if geraet else "",
        }

        vodafone = _guenstigstes_je_laden(eigene, laeden)
        if not vodafone:
            if wettbewerb and not eigene:
                ohne_vodafone.append(
                    {
                        **kopf,
                        "anbieter": wettbewerb,
                        "anzahl": len(wettbewerb),
                        "ab_preis": wettbewerb[0]["preis"],
                    }
                )
            continue

        eigen = vodafone[0]
        guenstiger = [a for a in wettbewerb if a["preis"] < eigen["preis"]]
        teurer = [a for a in wettbewerb if a["preis"] >= eigen["preis"]]

        zeile = {
            **kopf,
            "vodafone": eigen,
            "guenstiger": guenstiger,
            "teurer": teurer,
            "anzahl_guenstiger": len(guenstiger),
            "anzahl_verglichen": len(wettbewerb),
            "bester": guenstiger[0] if guenstiger else None,
            "differenz": None,
            "prozent": None,
        }
        if guenstiger:
            bester = guenstiger[0]
            zeile["differenz"] = round(eigen["preis"] - bester["preis"], 2)
            zeile["prozent"] = round(
                (eigen["preis"] - bester["preis"]) / eigen["preis"] * 100.0, 1
            )
        zeilen.append(zeile)

    zeilen.sort(key=lambda z: (-(z["differenz"] or 0), z["modell"], z["speicher"] or 0))
    ohne_vodafone.sort(key=lambda z: (-z["anzahl"], z["modell"]))

    mit_vorteil = [z for z in zeilen if z["anzahl_guenstiger"]]
    geraete = len({z["device_id"] for z in zeilen})
    alle_wesentlich = [z for z in zeilen if ist_wesentlich(z)]
    wesentlich = alle_wesentlich[:UEBERSICHT_MAX_ZEILEN]
    gezeigt = {id(z) for z in wesentlich}
    rest = [z for z in zeilen if id(z) not in gezeigt]
    return {
        "preisart": preisart,
        "zeilen": zeilen,
        "geraete": geraete,
        "wesentlich": wesentlich,
        "rest": rest,
        "mit_vorteil": len(mit_vorteil),
        "ohne_vorteil": len(zeilen) - len(mit_vorteil),
        "ohne_vodafone": ohne_vodafone[:15],
        "ohne_vodafone_gesamt": len(ohne_vodafone),
        "groesste_differenz": mit_vorteil[0]["differenz"] if mit_vorteil else None,
        "hat_daten": bool(zeilen or ohne_vodafone),
        "hat_vodafone": bool(zeilen),
    }


def beide_preisarten(eintraege: list, katalog, laeden: Optional[dict] = None) -> dict:
    """Beide Achsen getrennt gerechnet - nie in einer Tabelle gemischt."""
    ohne = vergleich(eintraege, katalog, laeden, OHNE_VERTRAG)
    mit = vergleich(eintraege, katalog, laeden, MIT_VERTRAG)
    return {
        "ohne_vertrag": ohne,
        "mit_vertrag": mit,
        "hat_daten": ohne["hat_daten"] or mit["hat_daten"],
        "standard": OHNE_VERTRAG if ohne["hat_daten"] else MIT_VERTRAG,
    }
