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

from ..geraete_model import VERGLEICHBARE_ZUSTAENDE

# Ab wann ein Preisunterschied ein BEFUND ist und kein Rundungsrauschen.
# Am 29.08.2026 standen 62 Zeilen auf der Seite, davon 36 "niemand
# guenstiger" und Dutzende mit -0,90 EUR (freenet fuehrt dasselbe Geraet fuer
# 1199,00 statt 1199,90). Wer wissen will, wo wir teurer sind, scrollte durch
# zwanzig Bildschirme, um sechs Zeilen zu finden.
#
# ODER, nicht UND: bei einem 200-Euro-Geraet sind 15 Euro viel und 3 Prozent
# wenig, bei einem 2000-Euro-Geraet umgekehrt. Eine Grenze allein liesse je
# nach Preisklasse das Falsche durch.
#
# Nichts wird geloescht - `zeilen` bleibt die Vollansicht, `rest` steht auf
# der Seite hinter einem Aufklapper.
WESENTLICH_PROZENT = 3.0
WESENTLICH_EURO = 15.0

# Wie viele Zeilen die alte Vergleichsuebersicht ohne Aufklappen zeigte.
#
# ACHTUNG, wer die Seitenhoehe deckeln will: das ist seit dem 30.08.2026
# NICHT mehr diese Zahl. Die Vergleichssektion ist durch die Alarmtabelle
# ersetzt, und deren Deckel heisst `report/geraete_alarme.SICHTBAR_MAX`.
# Hier standen bis dahin siebzehn Zeilen Begruendung, dass diese Konstante
# die Seite kurz haelt, samt Verweis auf einen Test, den es nicht mehr gibt -
# eine lebendig klingende Erklaerung an einer Schraube, die nichts mehr
# bewegt. `vergleich()` rechnet `wesentlich`/`rest` weiter aus (und Tests
# halten die Rechnung fest), aber KEINE Vorlage liest sie.
UEBERSICHT_MAX_ZEILEN = 14


def ist_wesentlich(zeile: dict) -> bool:
    """Traegt diese Zeile eine Aussage, oder ist sie Rauschen?"""
    if not zeile.get("bester"):
        return False
    return ((zeile.get("prozent") or 0) >= WESENTLICH_PROZENT
            or (zeile.get("differenz") or 0) >= WESENTLICH_EURO)

# Wie in `geraete_view`: Vodafone ist die eigene Referenz, kein Wettbewerber.
EIGEN = ("vodafone",)

# Ohne Vertrag und mit Vertrag - die zwei Achsen, die nie zusammenfliessen.
OHNE_VERTRAG = "ohne_vertrag"
MIT_VERTRAG = "mit_vertrag"

# Ein sichtbarer Bestand ist einer, der noch im Regal steht. Ein
# ausgelistetes Geraet gehoert nicht in einen Preisvergleich von heute.
_SICHTBAR = ("aktiv", "vermutlich ausgelistet")


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
    # Eine Zuzahlung OHNE Tarifreferenz ist nach der Disziplin dieses
    # Projekts kein Preis. `Listung.__post_init__` faengt das schon ab -
    # hier steht es noch einmal, weil diese Funktion auch rohe dicts aus
    # der Zustandsdatei sieht.
    if zuzahlung is not None and (eintrag.get("tarif_referenz") or "").strip():
        return float(zuzahlung), MIT_VERTRAG
    return None, ""


def _belegt(eintrag: dict) -> bool:
    """Traegt diese Listung Quelle UND Abrufdatum?"""
    return bool((eintrag.get("quelle_url") or "").strip()
                and (eintrag.get("abgerufen_am") or "").strip())


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
        # Ein Kampfpreis auf ein nicht lieferbares Geraet ist ein anderer
        # Sachverhalt als einer auf ein lieferbares. Die Alarmtabelle zeigt
        # das als eigene Spalte, statt beides gleich aussehen zu lassen.
        "verfuegbarkeit": eintrag.get("verfuegbarkeit") or "unbekannt",
        "zustand": eintrag.get("zustand") or "neu",
        # Traegt die Markierung des Pruefberichts an die Zeile: ein Ausreisser
        # wird gemeldet statt geloescht, und gemeldet heisst DORT sichtbar,
        # wo jemand die Zahl liest.
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


def vergleich(eintraege: list, katalog, laeden: Optional[dict] = None,
              preisart: str = OHNE_VERTRAG) -> dict:
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
        # W1.1, Evaluation vom 29.08.2026: der Vergleich zeigt NUR
        # Neugeraete. Bis dahin bildete jeder Zustand seine eigene Zeile -
        # arithmetisch richtig, auf der Seite aber nicht zu unterscheiden,
        # und ein falsch erkannter Zustand schlug voll durch: ein o2-Geraet
        # fuer 577 EUR ("grau erneuert") stand als Sieger gegen Vodafones
        # Neupreis von 849,90 EUR. "unbekannt" faellt aus demselben Grund
        # heraus - ein nicht bestimmter Zustand wird nicht als neu
        # angenommen. Beides bleibt im CSV-Export und in der SKU-Ansicht.
        if (e.get("zustand") or "neu") not in VERGLEICHBARE_ZUSTAENDE:
            continue
        schluessel = (e.get("device_id"), e.get("speicher_gb"),
                      e.get("zustand") or "neu")
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
            "device_id": gid, "modell": modell, "hersteller": hersteller,
            "speicher": speicher, "zustand": zustand,
            "segment": geraet.segment if geraet else "",
        }

        vodafone = _guenstigstes_je_laden(eigene, laeden)
        if not vodafone:
            # ZWEI verschiedene Faelle, und sie duerfen nicht denselben Satz
            # bekommen:
            #
            #   `eigene` leer          Vodafone fuehrt das Geraet nicht. Das
            #                          ist selbst ein Befund und gehoert in
            #                          die Luecken-Liste.
            #   `eigene` da, unbelegt  Vodafone fuehrt es sehr wohl, nur ohne
            #                          Quelle oder Abrufdatum. "Bei Vodafone
            #                          nicht gelistet" waere dann eine
            #                          FALSCHE Aussage ueber das eigene
            #                          Portfolio - die Zeile entfaellt
            #                          stillschweigend, der Vergleich auch.
            #
            # Der zweite Fall kann aus der Pipeline nicht entstehen
            # (`Listung.__post_init__` erzwingt Quelle und Abrufdatum zu
            # jedem Preis). Er steht hier trotzdem, weil diese Funktion auch
            # rohe dicts aus der Zustandsdatei sieht - und weil ein falscher
            # Satz ueber das eigene Regal teurer ist als eine fehlende Zeile.
            if wettbewerb and not eigene:
                ohne_vodafone.append({**kopf, "anbieter": wettbewerb,
                                      "anzahl": len(wettbewerb),
                                      "ab_preis": wettbewerb[0]["preis"]})
            continue

        eigen = vodafone[0]
        # STRIKT guenstiger: Preisgleichheit ist kein Preisvorteil.
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
                (eigen["preis"] - bester["preis"]) / eigen["preis"] * 100.0, 1)
        zeilen.append(zeile)

    # Groesster Abstand zuerst; Zeilen ohne guenstigeren Wettbewerber danach,
    # nach Modell sortiert. Sie verschwinden NICHT - "nirgends guenstiger"
    # ist die Auskunft, wegen der man eine Vergleichsliste liest.
    zeilen.sort(key=lambda z: (-(z["differenz"] or 0), z["modell"],
                               z["speicher"] or 0))
    ohne_vodafone.sort(key=lambda z: (-z["anzahl"], z["modell"]))

    mit_vorteil = [z for z in zeilen if z["anzahl_guenstiger"]]
    # Eine Zeile ist eine (Modell, Speicher)-Kombination, KEIN Geraet: das
    # iPhone 17 mit 256 und mit 512 GB sind zwei Zeilen und ein Geraet. Als
    # "62 Geraete im Vergleich" stand darueber eine Zahl, die groesser war
    # als die 59 beobachteten Geraete daneben - dieselbe Fehlerklasse wie
    # "267 Geraete neu im Regal" (W3), nur eine Sektion weiter.
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
        # Die Seite blendet die Sektion aus, solange es nichts zu vergleichen
        # gibt. Ein leerer Kasten mit Ueberschrift sagt "kaputt", nicht
        # "noch keine Daten".
        "hat_daten": bool(zeilen or ohne_vodafone),
        "hat_vodafone": bool(zeilen),
    }


def beide_preisarten(eintraege: list, katalog,
                     laeden: Optional[dict] = None) -> dict:
    """Beide Achsen getrennt gerechnet - nie in einer Tabelle gemischt."""
    ohne = vergleich(eintraege, katalog, laeden, OHNE_VERTRAG)
    mit = vergleich(eintraege, katalog, laeden, MIT_VERTRAG)
    return {
        "ohne_vertrag": ohne,
        "mit_vertrag": mit,
        "hat_daten": ohne["hat_daten"] or mit["hat_daten"],
        # Welche Achse die Seite zuerst zeigt: die mit Daten. Ohne diese
        # Zeile stuende bei einem reinen Buendel-Bestand die leere Achse
        # oben und die volle im zugeklappten Umschalter.
        "standard": OHNE_VERTRAG if ohne["hat_daten"] else MIT_VERTRAG,
    }
