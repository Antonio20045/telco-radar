"""Der Geraetebestand, wie er ANGEZEIGT und EXPORTIERT wird (31.08.2026).

Zwei Fehler stehen heute auf `/geraete.html` und in `site/exporte/`, und
beide haben dieselbe Wurzel: der Store loescht nie etwas, und er korrigiert
nie etwas. Er ist die Chronik der Messungen, nicht das Bild des Marktes.

    1. Die Farbe traegt das Zustandswort mit. o2 schreibt sein Kennzeichen
       ausschliesslich in das Farbfeld ("space schwarz erneuert", "titanium
       black gebraucht", "grau erneuert"). In der Katalogtabelle steht dann
       "space schwarz erneuert" in der Spalte FARBE, waehrend die Spalte
       ZUSTAND daneben "refurbished" sagt - dieselbe Aussage zweimal, einmal
       an der falschen Stelle. Gemessen am Bestand vom 30.08.2026: zehn
       Listungen.

    2. Dieselbe Listung steht zweimal. Aendert die Quelle ihre
       Farbschreibweise, aendert sich die `sku_id`, der Store legt eine neue
       Listung an und altert die alte auf "vermutlich ausgelistet" - beide
       sind sichtbar, beide zeigen denselben Preis unter derselben Adresse.
       Gemessen: zehn Paare, alle o2, alle vom Umstieg "mitternacht
       erneuert" -> "mitternacht".

Bereinigt wird beim LESEN, nicht im Store
-----------------------------------------
`bereinige()` gibt Kopien zurueck und fasst `data/state/geraete_db.json`
nicht an. Das ist keine Vorsicht, sondern die einzige richtige Reihenfolge:
die bereinigte Farbe ginge in die `sku_id` ein, der gesamte Altbestand
haette damit eine neue Kennung, gaelte als ausgelistet und entstuende neu -
Listungsdauer und Preisverlauf begaennen bei null. Der Fehler steht in der
ANZEIGE, also wird er in der Anzeige behoben.

Die Falle: eine echte Farbvariante ist kein Zwilling
----------------------------------------------------
Vodafone fuehrt dasselbe iPhone 17 256 GB in fuenf Farben zu identischen
949,90 EUR. Ueber den Bestand vom 30.08.2026 gezaehlt gibt es **90** Gruppen
mit gleichem (Anbieter, Geraet, Speicher, Preis); nur **10** davon sind
Zwillinge. Die Fachseite hat die Farbvarianten ausdruecklich bestellt - wer
sie zusammenfasst, loescht 96 wahre Zeilen, um 10 falsche zu entfernen.

Die naheliegende Unterscheidung traegt NICHT: es ist nicht wahr, dass echte
Varianten verschiedene `quelle_url` haetten. Nachgemessen zeigen alle fuenf
Vodafone-Farben auf `.../privat/handys/iphone-16.html` - eine
Produktseite, fuenf Varianten. Auf die URL allein geschluesselt blieben von
370 Listungen 274 uebrig.

Was die zwei Faelle wirklich trennt, ist die Farbe SELBST - aber erst,
nachdem Schritt 1 gelaufen ist: "mitternacht erneuert" und "mitternacht"
sind nach dem Streichen des Zustandsworts dieselbe Farbe, "Salbei" und
"Nebelblau" sind es nie. Deshalb steht die bereinigte Farbe im Schluessel,
und deshalb ist die Reihenfolge der beiden Schritte nicht beliebig.

Verglichen wird ueber `farbschluessel()` - die Frage "ist das buchstaeblich
dieselbe Variante?" ist dort schon beantwortet, samt "pistachio bk" =
"pistachio". Auf die kanonische Farbe geschluesselt waeren "Obsidian" und
"Mitternacht" desselben Geraets ein Zwilling, und das sind zwei Varianten.

Der Zustand kommt aus der Ableitung, nicht aus dem Store
--------------------------------------------------------
Zwei der zehn Paare tragen im Store verschiedene Zustaende: die gealterte
Zeile sagt "neu", die aktive "refurbished" - derselbe Artikel, dieselbe
Adresse (`...-space-schwarz-erneuert-details`), nur hat der Store seinen
alten, falschen Wert bis zum naechsten Crawl behalten. Auf den
gespeicherten Zustand geschluesselt blieben genau diese zwei Zwillinge
stehen, und zwar die zwei, bei denen die falsche Haelfte als NEUgeraet in
den Preisvergleich ginge. `_zustand()` leitet ihn deshalb aus Titel, Farbe
und Adresse ab - dieselbe Rechnung wie in `geraete_view.katalogzeilen()`,
aus demselben Grund: der Store ist die schwaechere Quelle.
"""
from __future__ import annotations

from copy import copy
from typing import Optional

from ..analyze.geraete_store import STATUS_AKTIV
from ..geraete_model import (VERGLEICHBARE_ZUSTAENDE, farbschluessel,
                             ohne_zustandswort, zustand_aus_feldern)

# Die zwei Felder, aus denen Anzeige und Export ihre Farbe bauen - beide mit
# demselben Ausdruck `farbe_normalisiert or farbe_roh`
# (`geraete_view.katalogzeilen()`, `geraete_export.aktuell_csv()`). Beide
# werden bereinigt, obwohl heute nur `farbe_roh` ein Zustandswort traegt:
# fuellt der naechste Adapter das kanonische Feld mit "grau erneuert", stuende
# das Wort ueber den Vorrang der ersten Haelfte sofort wieder auf der Seite,
# und die Bereinigung saehe von aussen aus, als haette sie ausgesetzt.
FARBFELDER = ("farbe_normalisiert", "farbe_roh")


def bereinige(eintraege: list[dict]) -> list[dict]:
    """Der Bestand, wie er ANGEZEIGT und EXPORTIERT wird.

    Zwei Schritte in dieser Reihenfolge: erst faellt das Zustandswort aus
    der Farbe, dann werden Zwillinge zusammengefasst. Die Reihenfolge
    traegt die zweite Haelfte - vor Schritt 1 sind "mitternacht erneuert"
    und "mitternacht" zwei Farben und damit zwei Listungen.

    Gibt KOPIEN zurueck; die uebergebenen dicts werden nicht veraendert
    (siehe Modulkopf: eine geaenderte Farbe im Store setzt Listungsdauer und
    Preisverlauf auf null).

    Die Reihenfolge der ueberlebenden Eintraege bleibt die der Eingabe. Wer
    sortiert, sortiert selbst - `katalogzeilen()` und `aktuell_csv()` tun es
    jeweils anders, und eine Sortierung hier waere eine dritte, die niemand
    sieht.
    """
    sauber = [_mit_sauberer_farbe(e) for e in eintraege]
    return _ohne_zwillinge(sauber)


def _mit_sauberer_farbe(eintrag: dict) -> dict:
    """Eine Kopie des Eintrags, deren Farbfelder kein Zustandswort tragen.

    Kopiert wird IMMER, auch wenn nichts zu streichen war: ein Aufrufer, der
    das Ergebnis veraendert, darf nicht je nach Datenlage mal den Store
    treffen und mal nicht. Flach kopiert - `einstiege` und die uebrigen
    Listen werden hier nur gelesen.
    """
    kopie = copy(eintrag)
    for feld in FARBFELDER:
        wert = kopie.get(feld)
        if wert:
            # `ohne_zustandswort` gibt die Farbe unveraendert zurueck, wenn
            # nach dem Streichen nichts uebrig bleibt - eine geleerte Farbe
            # verloere die Dimension. Das Feld kann hier also nie leer werden.
            kopie[feld] = ohne_zustandswort(wert)
    return kopie


def _ohne_zwillinge(eintraege: list[dict]) -> list[dict]:
    """Je Zwillingsschluessel bleibt genau ein Eintrag stehen."""
    beste: dict[tuple, dict] = {}
    for eintrag in eintraege:
        schluessel = _zwillingsschluessel(eintrag)
        vorhanden = beste.get(schluessel)
        if vorhanden is None or _gewinnt(eintrag, vorhanden):
            beste[schluessel] = eintrag
    # `dict` haelt die Einfuegereihenfolge, also die der Eingabe - auch wenn
    # ein spaeterer Zwilling den frueheren verdraengt hat. Der Platz gehoert
    # dem Paar, nicht dem Gewinner.
    return list(beste.values())


def _zwillingsschluessel(eintrag: dict) -> tuple:
    """Woran zwei Zeilen als DIESELBE Listung erkannt werden.

    `quelle_url` MUSS drin sein: zwei Angebote unter verschiedenen Adressen
    sind zwei Angebote, auch wenn sie sich in allem anderen gleichen. Die
    bereinigte Farbe MUSS drin sein: sonst faellt jede echte Farbvariante
    weg (siehe Modulkopf, 90 Gruppen gegen 10 Zwillinge).

    Der Preis steht mit BEIDEN Betraegen im Schluessel. Ein Barpreis und
    eine Zuzahlung sind nicht dieselbe Aussage; `tarif_referenz` gehoert
    dazu, weil dieselbe Zuzahlung zu zwei Tarifen zwei Angebote sind. Heute
    folgenlos - alle Listungen tragen einen Barpreis -, aber der naechste
    Buendelpreis-Adapter loest es aus.
    """
    return (
        eintrag.get("anbieter"),
        eintrag.get("device_id"),
        eintrag.get("speicher_gb"),
        _zustand(eintrag),
        eintrag.get("preis_ohne_vertrag"),
        eintrag.get("zuzahlung"),
        eintrag.get("tarif_referenz"),
        eintrag.get("quelle_url"),
        farbschluessel(eintrag.get("farbe_normalisiert"),
                       eintrag.get("farbe_roh") or ""),
    )


def _zustand(eintrag: dict) -> str:
    """Der Zustand, wie ihn die heutige Regel liest.

    Dieselbe Ableitung wie in `geraete_view.katalogzeilen()`, und dieselbe
    Einschraenkung: die Ableitung kann ein GEBRAUCHTgeraet beweisen (ein
    Kennzeichen in Titel, Farbe oder Adresse), sie kann kein Neugeraet
    beweisen - "neu" ist dort nur die Abwesenheit eines Kennzeichens. Faellt
    sie auf "neu" zurueck, gilt deshalb der gespeicherte Wert: den hat der
    Adapter aus dem strukturierten Feld der Quelle gelesen, und das weiss
    mehr als ein Titel.
    """
    abgeleitet = zustand_aus_feldern(eintrag.get("titel_roh"),
                                     eintrag.get("farbe_roh"),
                                     eintrag.get("quelle_url"))
    if abgeleitet in VERGLEICHBARE_ZUSTAENDE:
        return eintrag.get("zustand") or "neu"
    return abgeleitet


def _gewinnt(neu: dict, alt: dict) -> bool:
    """Verdraengt `neu` den bisher gemerkten Zwilling `alt`?

    Der aktive Eintrag gewinnt gegen jeden nicht aktiven - er ist der, den
    die Quelle zuletzt bestaetigt hat. Stehen beide gleich, entscheidet das
    juengere `abgerufen_am`; auch dann bleibt einer stehen, und zwar der mit
    dem frischeren Preis.
    """
    if _aktiv(neu) != _aktiv(alt):
        return _aktiv(neu)
    return _datum(neu) > _datum(alt)


def _aktiv(eintrag: dict) -> bool:
    return eintrag.get("status") == STATUS_AKTIV


def _datum(eintrag: dict) -> str:
    """`abgerufen_am` als vergleichbare Zeichenkette.

    ISO-Datum, also lexikografisch gleich sortiert wie chronologisch. Ein
    fehlendes Datum wird zum leeren String und verliert damit gegen jedes
    vorhandene - das ist die richtige Seite: ein Eintrag ohne Abrufdatum ist
    der schlechter belegte.
    """
    wert: Optional[str] = eintrag.get("abgerufen_am")
    return wert or ""
