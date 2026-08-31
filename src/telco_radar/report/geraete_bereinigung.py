"""Der Geraetebestand, wie er ANGEZEIGT und EXPORTIERT wird (31.08.2026).

Zwei Fehler stehen heute auf `/geraete.html` und in `site/exporte/`, und
beide haben dieselbe Wurzel: der Store loescht nie etwas, und er korrigiert
nie etwas. Er ist die Chronik der Messungen, nicht das Bild des Marktes.

    1. Die Farbe traegt das Zustandswort mit. o2 fuehrt seine
       Gebrauchtstrecke als "space schwarz erneuert", "titanium black
       gebraucht", "grau erneuert". In der Katalogtabelle steht dann "space
       schwarz erneuert" in der Spalte FARBE, waehrend die Spalte ZUSTAND
       daneben "refurbished" sagt - dieselbe Aussage zweimal, einmal an der
       falschen Stelle. Gemessen am Bestand vom 30.08.2026: zehn Listungen,
       neun verschiedene Schreibweisen, alle o2.

    2. Dieselbe Listung steht zweimal. Aendert die Quelle ihre
       Farbschreibweise, aendert sich die `sku_id`, der Store legt eine neue
       Listung an und altert die alte auf "vermutlich ausgelistet" - beide
       sind sichtbar, beide zeigen denselben Preis unter derselben Adresse.
       Gemessen: zehn Paare, alle o2, alle aus dem Wegfall des
       Zustandsworts in der Farbe ("mitternacht erneuert" -> "mitternacht",
       "titanium black gebraucht" -> "titanium black", und so fort).

Was der Zustand in der Farbe NICHT ist: die einzige Fundstelle. Ueber alle
370 sichtbaren Listungen gemessen traegt keine einzige ihr Kennzeichen nur
dort - alle zehn nennen es zusaetzlich im Titel ("Apple iPhone 14
(gebraucht) 128 GB mitternacht erneuert") und in der Adresse
(`...-mitternacht-erneuert-details`). Der Zustand ist also nicht in Gefahr;
was hier behoben wird, ist eine Farbspalte, die eine Zustandsangabe zeigt.

Bereinigt wird beim LESEN, nicht im Store
-----------------------------------------
`bereinige()` gibt Kopien zurueck und fasst `data/state/geraete_db.json`
nicht an. Das ist keine Vorsicht, sondern die einzige richtige Reihenfolge:
die bereinigte Farbe ginge in die `sku_id` ein, der gesamte Altbestand
haette damit eine neue Kennung, gaelte als ausgelistet und entstuende neu -
Listungsdauer und Preisverlauf begaennen bei null. Der Fehler steht in der
ANZEIGE, also wird er in der Anzeige behoben.

Die Kopie ist FLACH (`copy`, nicht `deepcopy`). Die geschachtelten Werte -
`einstiege` ist der einzige - liegen also weiterhin am Store-Objekt. Wer in
so eine Liste schreibt, schreibt in den Store; gelesen wird sie ueberall,
geschrieben nirgends. Eine tiefe Kopie waere hier 370-mal je Rendern
Arbeit fuer einen Fall, den es nicht gibt - aber wer einen Verbraucher
baut, der `einstiege` veraendert, aendert diese Zeile mit.

Die Falle: eine echte Farbvariante ist kein Zwilling
----------------------------------------------------
Vodafone fuehrt dasselbe iPhone 17 256 GB in fuenf Farben zu identischen
949,90 EUR. Die Fachseite hat die Farbvarianten ausdruecklich bestellt -
wer sie zusammenfasst, loescht wahre Zeilen, um zehn falsche zu entfernen.

Die naheliegende Unterscheidung traegt NICHT: es ist nicht wahr, dass echte
Varianten verschiedene `quelle_url` haetten. Nachgemessen zeigen alle fuenf
Vodafone-Farben auf `.../privat/handys/iphone-17.html` - eine Produktseite,
fuenf Varianten; ueber den ganzen Bestand verteilen sich 370 Listungen auf
251 Adressen. Der Schluessel dieses Moduls OHNE die Farbe faltet den
sichtbaren Bestand deshalb von 370 auf **272** Zeilen zusammen: 88 echte
Varianten weg, um 10 Zwillinge zu treffen.

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
stehen (360 gegen 362 Zeilen), und zwar die zwei, bei denen die falsche
Haelfte als NEUgeraet in den Preisvergleich ginge. `zustand_der_zeile()`
leitet ihn
deshalb aus Titel, Farbe und Adresse ab - dieselbe Rechnung wie in
`geraete_view.katalogzeilen()`, aus demselben Grund: der Store ist die
schwaechere Quelle.

In der Auslieferung faengt `geraete_pruefung.pruefe()` diese zwei Zeilen
schon vorher ab (sie sind der Befund `zustand_veraltet`). Das macht die
Regel nicht entbehrlich: `bereinige()` ist eine eigene Funktion mit einer
eigenen Zusicherung, und eine Zusicherung, die an einer anderen Stufe
haengt, ist keine.

Die Zahlen der Auslieferung
---------------------------
`bereinige()` steht in ZWEI Rechnungen, und sie liefern verschiedene Zahlen
(Bestand vom 31.08.2026, nachgemessen):

    Bestand    = bereinige(sichtbar)          370 -> **360**
    belastbar  = bereinige(pruefe(sichtbar))  370 -> 366 -> **358**

Der Unterschied sind genau zwei Zeilen: o2 fuehrt das Galaxy S26 FE 128 GB
unter zwei Adressen als "pistachio" (811,00) und "pistachio bk" (667,00) -
ein Doppelpreis, also keine Preisaussage, aber sehr wohl zwei Listungen, die
es gibt. Sie stehen im Gerätekatalog und in der CSV und fehlen in Vergleich,
Alarmen und Preisverlauf. Welche Menge wo hingehoert, entscheidet
`geraete_view.bestand_und_belastbar()`; wer eine dieser Zahlen zitiert, sagt
dazu, welche gemeint ist - sie sind nicht dieselbe.

`pruefe()` nimmt vier Zeilen (zwei falsch gespeicherte Zustaende, ein
Doppelpreis), darunter zwei Haelften von Zwillingspaaren; `bereinige()`
fasst danach die verbleibenden **acht** Paare zusammen, auf dem sichtbaren
Bestand allein sind es **zehn**.

Was der Zwilling an Historie mitnimmt
-------------------------------------
Die weggefallene Zeile hat eigene Preispunkte in `geraete_preise.jsonl`, und
`geraete_export.historie_csv()` schneidet die Historie auf die Kennungen des
Bestands zu. Acht der 369 Punkte der Kette fallen damit aus
`geraete-historie.csv`.

Das ist nachgemessen und vertretbar: jeder dieser acht Punkte traegt
GENAU DEN PREIS, den der Ueberlebende am Folgetag ebenfalls traegt (445,00
gegen 445,00; 577,00 gegen 577,00; und so weiter durch alle acht). Die
Preiskurve ist danach dieselbe Kurve - verloren geht nicht ein Preis,
sondern ein Tag, an dem er schon galt.

Was daran wirklich weh taete, gibt der Ueberlebende deshalb nicht her: er
erbt das FRUEHERE `first_seen` seines Zwillings (siehe `_verschmolzen`).
Sonst waere jede umbenannte Listung nach dem Merge einen Tag alt, und die
Verweildauer im Portfolio-Reiter zaehlte die Umbenennung als Neuzugang -
genau der Schaden, den das Bereinigen beim Lesen vermeiden soll.

Die Kennungen der zusammengefassten Zwillinge stehen als `zwilling_ids` am
Ueberlebenden. Heute liest sie niemand; wer die acht Punkte auch im Export
haben will, nimmt sie dort in die Kennungsmenge auf - die Angabe dafuer
muss aus dieser Funktion kommen, denn nur sie weiss, welche Zeile welche
abgeloest hat.
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
    Preisverlauf auf null). Die Kopie ist flach.

    Die Reihenfolge der ueberlebenden Eintraege bleibt die der Eingabe. Wer
    sortiert, sortiert selbst - `katalogzeilen()` und `aktuell_csv()` tun es
    jeweils anders, und eine Sortierung hier waere eine dritte, die niemand
    sieht.
    """
    sauber = [_mit_sauberer_farbe(e) for e in eintraege]
    return _ohne_zwillinge(sauber)


def _mit_sauberer_farbe(eintrag: dict) -> dict:
    """Eine Kopie des Eintrags: Zustand festgeschrieben, Farbe ohne dessen Wort.

    DIE REIHENFOLGE INNERHALB DIESER FUNKTION IST DIE GANZE POINTE. Der
    Zustand wird aus den ROHEN Feldern abgeleitet und in die Kopie
    geschrieben, BEVOR das Kennzeichen aus der Farbe faellt - sonst loescht
    Schritt 1 das Beweisstueck, aus dem Schritt 2 und jeder spaetere Leser
    ihn ableiten.

    Ohne diese Zeile stuende eine Listung, deren Kennzeichen NUR in der Farbe
    steht, im Geraetekatalog als "mitternacht - Zustand neu" da: der
    Store-Wert ist falsch, und das einzige Gegenzeugnis ist gerade
    weggeraeumt worden. Im Bestand vom 31.08.2026 gibt es diesen Fall nicht -
    alle zehn betroffenen Zeilen nennen ihr Kennzeichen zusaetzlich im Titel
    und in der Adresse (siehe Modulkopf) -, und genau deshalb steht die Zeile
    hier: eine Zusicherung, die nur fuer die heutige Datenlage gilt, ist
    keine, und o2 hat sein Kennzeichen schon einmal in genau ein Feld
    geschrieben (`geraete_model.zustand_aus_feldern`).
    `tests/test_geraete_seite.py::test_die_katalogzeile_nennt_den_
    ABGELEITETEN_zustand` baut den Fall.

    Der Store wird dabei NICHT angefasst; korrigiert wird die Kopie, aus der
    die Seite liest.

    Kopiert wird IMMER, auch wenn nichts zu streichen war: ein Aufrufer, der
    das Ergebnis veraendert, darf nicht je nach Datenlage mal den Store
    treffen und mal nicht.

    `ohne_zustandswort` gibt eine Farbe ohne Kennzeichen unveraendert
    zurueck, Zeichen fuer Zeichen. Darauf ruht dieser Schritt: er laeuft
    ueber ALLE Listungen, nicht nur ueber die zehn betroffenen, und was er
    bei den uebrigen 360 tut, muss nichts sein. Bis zum 31.08.2026 tat er
    dort etwas - `.strip(" -,;/()[]")` lief unbedingt und machte aus "Silver
    Shadow (Enterprise Edition)" ein "Silver Shadow (Enterprise Edition".
    """
    kopie = copy(eintrag)
    kopie["zustand"] = zustand_der_zeile(eintrag)
    for feld in FARBFELDER:
        wert = kopie.get(feld)
        if wert:
            kopie[feld] = ohne_zustandswort(wert)
    return kopie


def _ohne_zwillinge(eintraege: list[dict]) -> list[dict]:
    """Je Zwillingsschluessel bleibt genau ein Eintrag stehen."""
    gruppen: dict[tuple, list[dict]] = {}
    for eintrag in eintraege:
        gruppen.setdefault(_zwillingsschluessel(eintrag), []).append(eintrag)
    # `dict` haelt die Einfuegereihenfolge, also die der Eingabe - auch wenn
    # ein spaeterer Zwilling den frueheren verdraengt hat. Der Platz gehoert
    # dem Paar, nicht dem Gewinner.
    return [_verschmolzen(gruppe) for gruppe in gruppen.values()]


def _verschmolzen(gruppe: list[dict]) -> dict:
    """Aus einer Zwillingsgruppe wird eine Zeile.

    Der aktive Eintrag traegt sie - er ist der, den die Quelle zuletzt
    bestaetigt hat, und sein Preis ist der frischere. Aus der aufgeloesten
    Zeile uebernimmt er zwei Dinge, und beide sind Angaben ueber DIESELBE
    Listung, nicht ueber eine fremde:

        `first_seen`    das fruehere Datum. Eine umbenannte Listung ist
                        nicht neu; ohne diese Zeile zaehlte die Verweildauer
                        im Portfolio-Reiter jede Umbenennung als Zugang.
        `zwilling_ids`  die Kennungen der aufgeloesten Zeilen, damit ein
                        Verbraucher ihre Preispunkte wiederfindet (siehe
                        Modulkopf).

    Alles andere bleibt beim Sieger. Insbesondere wird KEIN Preis
    uebernommen: zwei verschiedene Preise waeren kein Zwilling, sondern ein
    Doppelpreis - der steht im Schluessel und faellt hier gar nicht an.
    """
    sieger = gruppe[0]
    for kandidat in gruppe[1:]:
        if _gewinnt(kandidat, sieger):
            sieger = kandidat
    if len(gruppe) == 1:
        return sieger
    # Die Gruppenmitglieder sind bereits unsere eigenen Kopien (Schritt 1),
    # geschrieben wird also nie in den Store.
    daten = [e.get("first_seen") for e in gruppe if e.get("first_seen")]
    if daten:
        sieger["first_seen"] = min(daten)
    sieger["zwilling_ids"] = sorted(
        e.get("id") for e in gruppe if e is not sieger and e.get("id"))
    return sieger


def _zwillingsschluessel(eintrag: dict) -> tuple:
    """Woran zwei Zeilen als DIESELBE Listung erkannt werden.

    `quelle_url` MUSS drin sein: zwei Angebote unter verschiedenen Adressen
    sind zwei Angebote, auch wenn sie sich in allem anderen gleichen. Die
    bereinigte Farbe MUSS drin sein: sonst faellt jede echte Farbvariante
    weg (siehe Modulkopf, 370 -> 272 Zeilen).

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
        # Auf den Kopien von Schritt 1 ist das der festgeschriebene Wert;
        # die Funktion ist auf ihnen idempotent. Sie steht hier trotzdem und
        # nicht als `eintrag["zustand"]`, damit der Schluessel auch dann
        # stimmt, wenn ihn jemand auf rohe Store-Eintraege anwendet.
        zustand_der_zeile(eintrag),
        eintrag.get("preis_ohne_vertrag"),
        eintrag.get("zuzahlung"),
        eintrag.get("tarif_referenz"),
        eintrag.get("quelle_url"),
        farbschluessel(eintrag.get("farbe_normalisiert"),
                       eintrag.get("farbe_roh") or ""),
    )


def zustand_der_zeile(eintrag: dict) -> str:
    """Der Zustand, wie ihn die heutige Regel liest. DIE EINE Ableitung.

    Sie stand am 31.08.2026 in DREI Fassungen: hier, in
    `geraete_view.katalogzeilen()` und - als schweigendes Vertrauen auf den
    Store - im CSV-Export. Drei Fassungen einer Regel sind drei Regeln, und
    die dritte war die falsche: `geraete_export.aktuell_csv()` schrieb
    `eintrag["zustand"]` roh in die Spalte. Solange der Export die
    GEPRUEFTE Menge bekam, deckte `geraete_pruefung._zustand_veraltet()`
    das zu; seit er den BESTAND bekommt (siehe
    `geraete_view.bestand_und_belastbar`), tut es das nicht mehr. Eine
    Zusicherung, die an einer anderen Stufe haengt, ist keine.

    Deshalb oeffentlich und deshalb hier: dieses Modul ist der Ort, an dem
    der ANGEZEIGTE Bestand entsteht, und Reiter 2 wie CSV zeigen dieselbe
    Zeile - sie duerfen nicht zwei Antworten auf dieselbe Zelle geben.

    Die Einschraenkung: die Ableitung kann ein GEBRAUCHTgeraet beweisen (ein
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
