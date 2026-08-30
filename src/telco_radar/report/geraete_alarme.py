"""Reiter 1 der Geraeteseite: die Preis-Alarme (B2, 30.08.2026).

Die Startansicht der Geraeteseite ist eine TABELLE. Sie beantwortet eine
Frage - *bei welchem Geraet liegen wir am weitesten zurueck* - und sie
beantwortet sie in fuenf Sekunden oder gar nicht.

Was diese Datei ersetzt
-----------------------
Bis zum 30.08.2026 stand oben eine Positionskarte mit 59 Geraeten mal vier
Anbietern in einem Bild: 114 senkrecht gedrehte Achsenbeschriftungen, 155
von 164 Punkten ohne Beschriftung. Daneben fuenf Kennzahlkacheln
("59 Geraete beobachtet", "250 Varianten", "353 Preispunkte") - Betriebsdaten,
keine Aussagen. Sie stehen jetzt als Fliesstext am Seitenende, und ihren
Platz nehmen vier Kacheln ein, die eine Handlung nahelegen.

Die vier Stufen
---------------
Sie sind eine Einteilung des ABSTANDS, nicht der Wichtigkeit, und sie
stehen hier statt in der Vorlage, damit Kachel und Tabellenzeile dieselbe
Rechnung benutzen. Eine Kachel, die anders zaehlt als die Tabelle unter ihr,
ist der Fehlertyp aus CLAUDE.md 6: ein Etikett und ein Feld, die nicht
dasselbe meinen.

Warum die Prozentzahl gross steht und der Euro-Betrag klein
-----------------------------------------------------------
Vorgabe des Auftrags, und sie ist richtig: 15 Euro sind bei einem
200-Euro-Geraet viel und bei einem 2000-Euro-Geraet nichts. Der Prozentsatz
ist die vergleichbare Zahl, der Euro-Betrag ihr Beleg.

Keine Zeile, die nichts sagt
----------------------------
"niemand guenstiger" stand 36-mal in der alten Tabelle. Das ist keine
Aussage, das ist eine leere Zeile mit Text darin - die Kachel "Bestpreis"
sagt dasselbe einmal, und nur solche Zeilen fallen aus der Tabelle.

Zeilen mit KLEINEM Rueckstand bleiben dagegen stehen. Der Auftrag wollte sie
zuerst auch heraushaben ("Rundungsrauschen"), aber der Unterschied ist
keiner der Aussage, sondern des Grades: "1,6 % guenstiger" ist eine wahre
Auskunft, "niemand guenstiger" ist keine. Die Kachel "Gering" zaehlt sie,
die Tabelle zeigt sie, und die Sortierung stellt sie ans Ende - dort kostet
ihre Anwesenheit nichts.
"""
from __future__ import annotations

from typing import Optional

# Die Grenzen der vier Stufen, in Prozent Abstand zu unserem Preis.
KRITISCH_AB = 10.0
MITTEL_AB = 3.0

# Wie viele Zeilen ohne Aufklappen sichtbar sind. Die Zahl deckelt die
# Seitenhoehe STRUKTURELL: ohne Deckel haengt sie am Datenbestand, und zwei
# zusaetzliche Zeilen kippten den Abnahmetest, ohne dass sich eine Zeile Code
# aendert.
#
# Die 12 sind GERECHNET, nicht gegriffen, und zwar am 30.08.2026 im echten
# Chromium: eine Zeile misst 68 px, der Reiter ohne Tabelle 2102 px, das
# Budget des Auftrags liegt bei 3000 px auf 1440 px Breite. Damit bleiben
# 898 px fuer die Tabelle, also 13 Zeilen - eine weniger als Reserve, weil
# ein laengerer Modellname eine Zeile zweizeilig macht.
#
# Der Auftrag nennt "hoechstens 15 Zeilen sichtbar". Mit 15 mass der Reiter
# 3154 px und riss damit die andere Vorgabe desselben Auftrags. Von zwei
# Zahlen desselben Absatzes gewinnt die, die der Leser merkt: drei
# Bildschirme.
SICHTBAR_MAX = 12

# Reihenfolge, Beschriftung und Farbe der vier Stufen. Die Farben stehen als
# CSS-Variablen im Stylesheet; hier steht nur ihr Name, damit Kachel und
# Pille dieselbe Quelle haben.
STUFEN = (
    ("kritisch", "Kritisch", "10 % oder mehr günstiger als wir"),
    ("mittel", "Mittel", "3 bis 10 % günstiger"),
    ("gering", "Gering", "unter 3 % günstiger"),
    ("bestpreis", "Bestpreis", "Vodafone ist am günstigsten"),
)


def einstufung(prozent: Optional[float]) -> str:
    """Die Stufe eines Abstands. `prozent` ist positiv, wenn ein Wettbewerber
    guenstiger ist - dieselbe Vorzeichenkonvention wie in `geraete_vergleich`.

    `None` heisst hier "kein Wettbewerber ist guenstiger", also Bestpreis.
    Es heisst NICHT "niemand wurde verglichen" - diesen Fall haelt
    `_verglichen` vorher heraus, und er darf nie in dieser Funktion landen.
    """
    if prozent is None or prozent <= 0:
        return "bestpreis"
    if prozent >= KRITISCH_AB:
        return "kritisch"
    if prozent >= MITTEL_AB:
        return "mittel"
    return "gering"


def _verglichen(zeile: dict) -> bool:
    """Steht diesem Geraet ueberhaupt ein Wettbewerber gegenueber?

    Ein Geraet, das nur wir fuehren, ist NICHT unser Bestpreis - es ist gar
    nicht verglichen. Beides gleich zu zaehlen waere die teuerste Sorte
    falscher Zahl auf einer Seite, deren Verkaufsargument der Belegzwang ist:
    sie behauptete einen gewonnenen Vergleich, den niemand gefuehrt hat.
    Am Bestand vom 30.08.2026 sind das 15 von 62 Zeilen.
    """
    return bool(zeile.get("anzahl_verglichen"))


def _prozent(zeile: dict) -> Optional[float]:
    """Der Abstand zum guenstigsten Wettbewerber, in Prozent unseres Preises.

    `geraete_vergleich` rechnet ihn bereits - hier wird er nur gelesen und
    NICHT neu gerechnet. Zwei Rechnungen fuer dieselbe Zahl sind zwei Zahlen
    (CLAUDE.md 6, der Fall der Stichwort-Vorschau).
    """
    wert = zeile.get("prozent")
    return float(wert) if wert is not None else None


def _euro(zeile: dict) -> Optional[float]:
    wert = zeile.get("differenz")
    return abs(float(wert)) if wert is not None else None


def kacheln(zeilen: list) -> list:
    """Die vier Kennzahlen ueber der Tabelle.

    Gezaehlt werden ALLE verglichenen Zeilen, nicht nur die sichtbaren -
    sonst zaehlte die Kachel "Gering" genau die Zeilen, die unter ihr fehlen,
    und haette damit keinen Nenner mehr. Zeilen ohne Wettbewerber zaehlen in
    keiner der vier Kacheln mit (siehe `_verglichen`).
    """
    gezaehlt = {schluessel: 0 for schluessel, _, _ in STUFEN}
    for z in zeilen:
        if not _verglichen(z):
            continue
        gezaehlt[einstufung(_prozent(z))] += 1
    return [{"schluessel": schluessel, "name": name, "schwelle": schwelle,
             "zahl": gezaehlt[schluessel]}
            for schluessel, name, schwelle in STUFEN]


def _bester(zeile: dict) -> Optional[dict]:
    """Der guenstigste Wettbewerber, oder None wenn keiner unterbietet."""
    guenstiger = zeile.get("guenstiger") or []
    return guenstiger[0] if guenstiger else None


def _alle_anbieter(zeile: dict) -> list:
    """Alle Anbieter dieses Geraets, unser eigener eingeschlossen, nach Preis.

    Das ist der Inhalt des Aufklappers: der Klick auf eine Zeile soll die
    ganze Lage zeigen, nicht nur den einen Sieger.
    """
    alle = list(zeile.get("guenstiger") or []) + list(zeile.get("teurer") or [])
    eigen = zeile.get("vodafone")
    if eigen:
        alle = alle + [dict(eigen, eigen=True)]
    return sorted(alle, key=lambda a: (a.get("preis") is None, a.get("preis")))


def zeilen(vergleich: dict, auffaellig: Optional[dict] = None) -> dict:
    """Die Alarmtabelle: sichtbare Zeilen, Rest, und die vier Kacheln.

    `auffaellig` ist die Ausreisser-Markierung aus `geraete_pruefung.pruefe`.
    Ein Ausreisser wird gemeldet statt geloescht - gemeldet heisst, dass er
    an DER Zeile steht, an der jemand die Zahl liest, mit dem Quelllink
    daneben, damit ein Mensch entscheidet.
    """
    auffaellig = auffaellig or {}
    roh = [z for z in (vergleich.get("zeilen") or []) if _verglichen(z)]
    ohne_wettbewerber = sum(1 for z in (vergleich.get("zeilen") or [])
                            if not _verglichen(z))

    gebaut = []
    for z in roh:
        prozent = _prozent(z)
        stufe = einstufung(prozent)
        bester = _bester(z)
        alle = _alle_anbieter(z)
        gebaut.append({
            "device_id": z.get("device_id"),
            "modell": z.get("modell"),
            "hersteller": z.get("hersteller"),
            "speicher": z.get("speicher"),
            "zustand": z.get("zustand"),
            "segment": z.get("segment"),
            "unser": z.get("vodafone"),
            "bester": bester,
            "prozent": prozent,
            "euro": _euro(z),
            "stufe": stufe,
            "stufe_name": dict((s, n) for s, n, _ in STUFEN)[stufe],
            "alle": alle,
            "anzahl_alle": len(alle),
            # Die Markierung haengt am guenstigsten Wettbewerber: er traegt
            # die Zahl, die in der Zeile steht.
            "auffaellig": bool(bester
                               and auffaellig.get(bester.get("listung_id"))),
        })

    # Nach dem PROZENTABSTAND, absteigend. Zeilen ohne Rueckstand stehen
    # nicht in der Tabelle - sie sind die Kachel "Bestpreis".
    mit_rueckstand = [z for z in gebaut if z["stufe"] != "bestpreis"]
    mit_rueckstand.sort(key=lambda z: -(z["prozent"] or 0))

    # Die Filterlisten kommen aus den ANGEZEIGTEN Zeilen, nicht aus dem
    # Gesamtbestand: ein Auswahlfeld, das eine Marke anbietet, zu der die
    # Tabelle keine Zeile hat, fuehrt zu einer leeren Tabelle und sieht wie
    # ein Fehler aus.
    return {
        "kacheln": kacheln(roh),
        "marken": sorted({z["hersteller"] for z in mit_rueckstand
                          if z["hersteller"]}),
        "modelle": sorted({z["modell"] for z in mit_rueckstand if z["modell"]}),
        "speicher": sorted({z["speicher"] for z in mit_rueckstand
                            if z["speicher"]}),
        "sichtbar": mit_rueckstand[:SICHTBAR_MAX],
        "rest": mit_rueckstand[SICHTBAR_MAX:],
        "gesamt": len(mit_rueckstand),
        "verglichen": len(roh),
        "ohne_wettbewerber": ohne_wettbewerber,
        "hat_daten": bool(roh),
    }


def leer() -> dict:
    """Der Notzustand - dieselben Felder, alle leer.

    Die Vorlage darf nicht wissen muessen, ob es Daten gibt: ein fehlender
    Schluessel in Jinja ist kein Fehler, sondern eine stumm leere Seite.
    """
    return {"kacheln": [{"schluessel": s, "name": n, "schwelle": w, "zahl": 0}
                        for s, n, w in STUFEN],
            "marken": [], "modelle": [], "speicher": [],
            "sichtbar": [], "rest": [], "gesamt": 0, "verglichen": 0,
            "ohne_wettbewerber": 0, "hat_daten": False}
