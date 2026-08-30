"""Plausibilitaetspruefung des Geraetedatensatzes (W1.2, 29.08.2026;
sequenziell verkettet und um die Farbe im Schluessel erweitert am 30.08.2026).

Der Anlass steht in `outputs/geraeteradar-wahrheit-2026-08-29.md`: die
Vergleichstabelle meldete einen Wettbewerbsnachteil, wo in Wahrheit ein
Vorteil stand. Ein o2-Gebrauchtgeraet lief als Neugeraet mit, unterbot mit
seinem Gebrauchtpreis den Vodafone-Neupreis und stand als Sieger auf der
Seite.

Die URSACHE ist in `geraete_model._ZUSTAENDE` behoben. Dieses Modul ist das
NETZ darunter: es faengt denselben Fehlertyp beim naechsten Adapter, bei der
naechsten Schreibweise und bei der naechsten Quelle, ohne dass ihn wieder
jemand im Export von Hand finden muss.

Wie weit dieses Netz traegt, ist begrenzt und soll es sein. Ein
Gebrauchtpreis, dessen Kennzeichen KEIN Eintrag der Wortliste trifft
("aufbereitet", "second life", "Zustand: gut"), faellt hier nur noch dann
heraus, wenn er in derselben Farbe wie ein Neupreis steht oder die Spanne
FARBSPANNE_UNMOEGLICH reisst. Sonst wird er berichtet und bleibt. Das ist die
Kehrseite der Farbe im Schluessel (siehe unten): sie beendet das Raten
darueber, was ein Farbaufschlag ist, und nimmt dafuer eine Faustregel
zurueck, die manchmal zufaellig richtig lag. Wer eine neue Schreibweise
sieht, traegt sie in `_ZUSTAENDE` ein - das ist der Ort dafuer.

Fuenf Pruefungen, alle gegen den fertigen Datensatz, alle vor dem Rendern
und alle NACHEINANDER (siehe `pruefe`):

    Zustand veraltet   Der gespeicherte Zustand widerspricht der heutigen
                       Regel. Der Store wird nicht angefasst.
    Doppelpreis        Dieselbe (Anbieter, Modell, Speicher, Zustand, FARBE)
                       mit zwei verschiedenen Preisen.
    Speicherinversion  Mehr Speicher kostet weniger als weniger Speicher.
    Farbspanne         Die Farben eines Geraets liegen weiter auseinander
                       als FARBSPANNE_GRENZE. Berichtet - und oberhalb von
                       FARBSPANNE_UNMOEGLICH auch entfernt.
    Ausreisser         Ein Preis weicht um mehr als AUSREISSER_ANTEIL vom
                       Median aller Preise fuer dasselbe (Modell, Speicher,
                       Zustand) ab. Nur berichtet, mit Markierung an der
                       Vergleichszeile.

Die Farbe gehoert in den Doppelpreis-Schluessel
-----------------------------------------------
Ein Farbaufschlag ist kein Widerspruch. Am 29.08.2026 ueber den echten
Bestand gemessen trennen sich die zwei Faelle sauber:

    112,3 %  o2  iPhone 14 Pro  128 GB   577 -> 1225   Gebrauchtgeraet
     53,0 %  o2  Galaxy S25     128 GB   577 ->  883   Gebrauchtgeraet
     21,6 %  o2  Galaxy S26 FE  128 GB   667 ->  811   "pistachio" / "pistachio bk"
      9,6 %  o2  Galaxy S26 U.  256 GB  1315 -> 1441   cobalt violet / schwarz
      5,7 %  o2  Galaxy S26     256 GB   955 -> 1009   cobalt violet / schwarz

Bis zum 30.08.2026 entschied darueber eine Spannengrenze von 30 %. Jede
solche Grenze verwirft an ihrer einen Seite wahre Preise und laesst an der
anderen falsche durch - sie schaetzt, was der Schluessel wissen kann. Mit
der Farbe im Schluessel ist die Frage entschieden statt geschaetzt:
verschiedene Farben sind nie ein Widerspruch, dieselbe Farbe ist immer
einer. Die drei unteren Faelle bleiben damit als Markt stehen; der
S26-FE-Fall ist keiner mehr, seit `farbschluessel()` "pistachio bk" und
"pistachio" als eine Farbe liest.

Fail closed in eine Richtung: eine aussortierte Zeile faellt aus Vergleich
UND Grafik, bleibt aber im CSV-Export und in der SKU-Ansicht. Was nicht
verglichen werden kann, verschwindet nicht - es wird nur nicht gegen etwas
gerechnet, das es nicht ist.
"""
from __future__ import annotations

from statistics import median

from ..geraete_model import (VERGLEICHBARE_ZUSTAENDE, farbschluessel,
                             zustand_aus_titel)

# Ab dieser Spanne ueber die FARBEN eines Geraets wird der Fall berichtet -
# nicht aussortiert. Kein Farbaufschlag ist ein Viertel des Geraetepreises;
# wenn doch, soll ihn jemand ansehen statt ihn zu verlieren. Gemessen am
# Bestand vom 29.08.2026 lagen die echten Farbpreise bei 5,7 bis 21,6 %.
FARBSPANNE_GRENZE = 0.25

# Und ab dieser Spanne ist es kein Farbaufschlag mehr, sondern ein falsch
# gelesenes Feld - die Gruppe wird entfernt.
#
# Diese zweite Grenze ist am 30.08.2026 nachgetragen worden, und ihr Fehlen
# war ein echter Rueckschritt: mit dem Wegfall der alten Spannengrenze hatte
# die `min`-Auswahl UEBER FARBEN HINWEG gar keinen Filter mehr, und CLAUDE.md
# sagt dazu einen Satz - "Der niedrigste Preis ist der wahrscheinlichste
# Fehler. Jede `min`-Auswahl braucht einen Filter davor." Nachgestellt: ein
# o2-Lockpreis von 1,00 EUR in anderer Farbe ueberlebte und gewann den
# Vergleich, waehrend die Quellenseite daneben "die Farben liegen 89800 %
# auseinander - gezeigt" schrieb.
#
# Sie steht bei 100 %, nicht bei 30 %: ein Geraet, das in einer Farbe doppelt
# so viel kostet wie in einer anderen, ist keine Farbvariante mehr. Alles
# darunter wird berichtet und BLEIBT - "kein Farbaufschlag ist ein Viertel
# des Geraetepreises; wenn doch, will ich es sehen, nicht geloescht
# bekommen". Gemessen lagen echte Farbpreise bei 5,7 bis 21,6 %.
FARBSPANNE_UNMOEGLICH = 1.00

# Abweichung vom Median, ab der ein Preis als Ausreisser gilt.
AUSREISSER_ANTEIL = 0.60

_SICHTBAR = ("aktiv", "beobachtet")


def _schluessel(e: dict):
    """Die Identitaet eines Eintrags.

    `id()` traegt nur, solange der Aufrufer dieselben Objekte durchreicht.
    Gaebe jemand `[dict(x) for x in bestand]` herein - was der eigene Test
    fuer die Unveraenderlichkeit genau so konstruiert -, waere `sauber`
    still identisch mit der Eingabe, die Pruefung faktisch abgeschaltet und
    jeder Test trotzdem gruen. Jede Listung traegt ihre `listung_id`; die
    ist der robuste Schluessel. `id()` bleibt der Rueckfall fuer rohe dicts
    ohne Kennung.
    """
    return e.get("id") or id(e)


def _preis(e: dict) -> float | None:
    wert = e.get("preis_ohne_vertrag")
    try:
        return float(wert) if wert is not None else None
    except (TypeError, ValueError):
        return None


def _vergleichbar(e: dict) -> bool:
    """Nur was in einer Preisaussage stehen darf, wird auch geprueft.

    Ein refurbished Geraet neben einem neuen ist KEIN Doppelpreis - es ist
    ein anderer Artikel. Die Trennung passiert schon im Schluessel; hier
    faellt zusaetzlich alles heraus, was ohnehin nicht in Vergleich und
    Grafik kommt, damit der Bericht keine Befunde ueber Zeilen meldet, die
    niemand sieht.
    """
    return (e.get("status") in _SICHTBAR
            and (e.get("zustand") or "neu") in VERGLEICHBARE_ZUSTAENDE
            and _preis(e) is not None)


def _label(e: dict, katalog) -> str:
    g = katalog.nach_id(e.get("device_id")) if katalog else None
    modell = g.modell if g else (e.get("device_id") or "?")
    sp = e.get("speicher_gb")
    return f"{modell} {sp} GB" if sp else modell


def _zustand_veraltet(eintraege: list, katalog) -> tuple[set, list]:
    """Eintraege, deren gespeicherter Zustand den heutigen Regeln widerspricht.

    Die Zustandserkennung ist am 29.08.2026 repariert worden, der STORE
    traegt seine alten Werte aber weiter - er wird erst beim naechsten
    erfolgreichen Crawl des Anbieters ueberschrieben. Bis dahin steht in
    `geraete_db.json` "neu", wo die heutige Regel "refurbished" sagt.

    Dass die zwei bekannten Faelle trotzdem nicht mehr als Sieger auf der
    Seite stehen, ist Zufall: das Doppelpreis-Netz hat sie nur erwischt,
    weil o2 dieselben Modelle zusaetzlich als Neugeraet fuehrt. Ein Modell,
    das ein Anbieter AUSSCHLIESSLICH gebraucht listet, faende kein Netz -
    es stuende mit seinem Gebrauchtpreis allein in der Neupreis-Tabelle.

    Deshalb wird der Zustand hier gegen den gespeicherten Rohtitel neu
    gerechnet. Das ist keine Datenwanderung: der Store wird nicht angefasst,
    die Zeile faellt nur aus den zwei Preisaussagen heraus, bis der naechste
    Lauf sie richtig schreibt.
    """
    raus, befunde = set(), []
    for e in eintraege:
        quelle = " ".join(str(e.get(feld) or "") for feld in
                          ("titel_roh", "farbe_roh", "quelle_url"))
        if not quelle.strip():
            continue
        jetzt = zustand_aus_titel(quelle)
        if jetzt in VERGLEICHBARE_ZUSTAENDE:
            continue
        raus.add(_schluessel(e))
        befunde.append({
            "art": "zustand_veraltet",
            "anbieter": e.get("anbieter"),
            "geraet": _label(e, katalog),
            "gespeichert": e.get("zustand") or "neu",
            "erkannt": jetzt,
            "entfernt": True,
        })
    return raus, befunde


def _farbe(e: dict) -> str:
    return farbschluessel(e.get("farbe_normalisiert"), e.get("farbe_roh") or "")


def _doppelpreise(eintraege: list, katalog) -> tuple[set, list]:
    """Zwei Preise fuer DIESELBE Farbe - das kann nicht sein.

    Die Farbe gehoert in den Schluessel, weil ein Farbaufschlag ein echter
    Preis ist: Samsung bepreist Aktionsfarben wirklich verschieden. Ohne
    Farbe im Schluessel entschied eine Spannengrenze darueber, ob ein
    Doppelpreis Fehler oder Markt war - und jede Grenze verwirft an ihrer
    einen Seite wahre Preise. Mit Farbe im Schluessel braucht es die Grenze
    nicht mehr: verschiedene Farben sind nie ein Widerspruch, gleiche Farbe
    ist immer einer.

    Aussortiert wird die GANZE Gruppe, nicht nur der niedrigere Preis:
    welcher der beiden stimmt, sagt der Datensatz nicht, und den teureren
    stehen zu lassen waere dieselbe Raterei mit umgekehrtem Vorzeichen.
    """
    gruppen: dict[tuple, list] = {}
    for e in eintraege:
        gruppen.setdefault(
            (e.get("anbieter"), e.get("device_id"), e.get("speicher_gb"),
             e.get("zustand") or "neu", _farbe(e)), []).append(e)

    raus, befunde = set(), []
    for (anbieter, _gid, _sp, _zu, farbe), gruppe in gruppen.items():
        preise = {_preis(e) for e in gruppe}
        if len(preise) < 2:
            continue
        lo, hi = min(preise), max(preise)
        raus.update(_schluessel(e) for e in gruppe)
        befunde.append({
            "art": "doppelpreis",
            "anbieter": anbieter,
            "geraet": _label(gruppe[0], katalog),
            "spanne": round((hi - lo) / lo * 100, 1) if lo else 0.0,
            "preise": sorted(preise),
            "farben": sorted({(e.get("farbe_roh") or farbe or "?")
                              for e in gruppe}),
            "entfernt": True,
        })
    return raus, befunde


def _farbspannen(eintraege: list, katalog) -> tuple[set, list]:
    """Der Abstand zwischen den Farben eines Geraets.

    Bis FARBSPANNE_UNMOEGLICH wird BERICHTET, nicht entfernt - anders als der
    Doppelpreis ist das kein Selbstwiderspruch, sondern eine
    Preisentscheidung des Anbieters. Darueber wird entfernt: eine Farbe, die
    das Geraet doppelt so teuer macht, ist keine Farbe mehr, sondern ein
    falsch gelesenes Feld (die 1-Euro-Anzahlung, der Buendelpreis, der
    Zubehoerartikel).
    """
    gruppen: dict[tuple, dict] = {}
    beispiele: dict[tuple, dict] = {}
    for e in eintraege:
        schluessel = (e.get("anbieter"), e.get("device_id"),
                      e.get("speicher_gb"), e.get("zustand") or "neu")
        # Der Beispieleintrag wird beim AUFBAU mitgefuehrt, nicht hinterher
        # gesucht. Die erste Fassung suchte ihn per `next()` ueber Anbieter
        # und Geraet - ohne Speicher und Zustand, also aus einer anderen
        # Gruppe: der Befund trug "Galaxy S26 128 GB" und die Preise der
        # 256-GB-Gruppe daneben.
        beispiele.setdefault(schluessel, e)
        farbe = _farbe(e)
        preise = gruppen.setdefault(schluessel, {})
        preise[farbe] = min(preise.get(farbe, float("inf")), _preis(e))

    raus, befunde = set(), []
    for schluessel, je_farbe in gruppen.items():
        if len(je_farbe) < 2:
            continue
        lo, hi = min(je_farbe.values()), max(je_farbe.values())
        spanne = (hi - lo) / lo if lo else 0.0
        if spanne <= FARBSPANNE_GRENZE:
            continue
        entfernt = spanne > FARBSPANNE_UNMOEGLICH
        if entfernt:
            raus.update(_schluessel(e) for e in eintraege
                        if (e.get("anbieter"), e.get("device_id"),
                            e.get("speicher_gb"),
                            e.get("zustand") or "neu") == schluessel)
        befunde.append({
            "art": "farbspanne",
            "anbieter": schluessel[0],
            "geraet": _label(beispiele[schluessel], katalog),
            "spanne": round(spanne * 100, 1),
            "preise": sorted(je_farbe.values()),
            "farben": sorted(je_farbe),
            "entfernt": entfernt,
        })
    return raus, befunde


def _speicherinversionen(eintraege: list, katalog) -> tuple[set, list]:
    je_reihe: dict[tuple, dict] = {}
    for e in eintraege:
        gb = e.get("speicher_gb")
        if not gb:
            continue
        schluessel = (e.get("anbieter"), e.get("device_id"),
                      e.get("zustand") or "neu")
        je_reihe.setdefault(schluessel, {}).setdefault(int(gb), []).append(e)

    raus, befunde = set(), []
    for (anbieter, _gid, _zu), stufen in je_reihe.items():
        sortiert = sorted(stufen)
        for kleiner, groesser in zip(sortiert, sortiert[1:]):
            billig = min(_preis(e) for e in stufen[groesser])
            teuer = min(_preis(e) for e in stufen[kleiner])
            if billig >= teuer:
                continue
            # Beide Stufen fliegen: die Inversion sagt, dass EINE von beiden
            # falsch gelesen ist, aber nicht welche.
            raus.update(_schluessel(e)
                        for e in stufen[kleiner] + stufen[groesser])
            befunde.append({
                "art": "speicherinversion",
                "anbieter": anbieter,
                "geraet": _label(stufen[kleiner][0], katalog),
                "klein_gb": kleiner, "klein_preis": teuer,
                "gross_gb": groesser, "gross_preis": billig,
                "entfernt": True,
            })
    return raus, befunde


def _ausreisser(eintraege: list, katalog) -> tuple[set, list]:
    gruppen: dict[tuple, list] = {}
    for e in eintraege:
        gruppen.setdefault(
            (e.get("device_id"), e.get("speicher_gb"),
             e.get("zustand") or "neu"), []).append(e)

    raus, befunde = set(), []
    for _gruppenschluessel, gruppe in gruppen.items():
        # Unter drei Angeboten ist der Median kein Median, sondern einer der
        # beiden Werte - und jede Abweichung waere per Definition gross.
        if len(gruppe) < 3:
            continue
        mitte = median([_preis(e) for e in gruppe])
        if not mitte:
            continue
        for e in gruppe:
            abweichung = abs(_preis(e) - mitte) / mitte
            if abweichung <= AUSREISSER_ANTEIL:
                continue
            # BERICHTET, nicht entfernt. Ein Doppelpreis und eine
            # Speicherinversion sind Selbstwidersprueche - der Datensatz
            # widerspricht sich selbst, und welche Zahl stimmt, sagt er
            # nicht. Ein Ausreisser ist etwas anderes: er widerspricht dem
            # MARKT, nicht sich selbst. Ein Discounter, der wirklich 60 %
            # unter dem Median liegt, ist genau das Signal, wegen dem diese
            # Seite existiert - ihn als Datenfehler zu loeschen hiesse, den
            # Befund gegen die Erwartung zu verwerfen.
            befunde.append({
                "art": "ausreisser",
                "listung_id": _schluessel(e),
                "anbieter": e.get("anbieter"),
                "geraet": _label(e, katalog),
                "preis": _preis(e),
                "median": mitte,
                "abweichung": round(abweichung * 100, 1),
                "entfernt": False,
            })
    return raus, befunde


def pruefe(eintraege: list, katalog=None) -> dict:
    """Prueft den Datensatz und sagt, was nicht verglichen werden darf.

    Die Pruefungen laufen NACHEINANDER, und jede sieht nur, was die vorige
    uebrig gelassen hat. Das ist keine Aufraeumarbeit, sondern der Kern:
    liefen sie unabhaengig und wuerden ihre Streichungen am Ende vereinigt,
    zieht eine schon verurteilte Zeile ihre gesunden Nachbarn mit.

    Am Bestand vom 30.08.2026 gemessen, mit unabhaengigen Pruefungen: o2
    fuehrt das Galaxy S25 128 GB als Neugeraet fuer 883 Euro und daneben
    eine falsch gespeicherte Gebrauchtzeile fuer 577 Euro. `_zustand_veraltet`
    erkennt die Gebrauchtzeile - `_doppelpreise` sah sie aber trotzdem, fand
    zwei Preise in einer Gruppe und warf BEIDE hinaus. Der echte o2-Neupreis
    verschwand aus dem Vergleich, und die Seite konnte die Aussage "o2 ist
    33 Euro teurer als wir" gar nicht mehr treffen. Dasselbe beim iPhone 14
    Pro (1225 Euro). Sequenziell geprueft bleibt in beiden Gruppen nach der
    Zustandspruefung genau ein Preis stehen, und es gibt keinen Doppelpreis
    mehr zu finden.

    Gibt `sauber` (die Eintraege, die in Vergleich und Grafik duerfen),
    `befunde` (jeder Treffer einzeln, fuer /geraete-quellen.html), `zahlen`
    (die Kurzbilanz) und `auffaellig` (die Kennungen der Zeilen, die zwar
    verglichen werden duerfen, aber einen Hinweis an der Vergleichszeile
    tragen) zurueck. Der EINGABEDATENSATZ wird nicht veraendert - Export und
    SKU-Ansicht sehen weiterhin alles.
    """
    kandidaten = [e for e in eintraege if _vergleichbar(e)]

    # Die ENTFERNENDEN Pruefungen laufen nacheinander; jede sieht nur, was
    # die vorige uebrig gelassen hat.
    raus: set = set()
    befunde: list = []
    uebrig = kandidaten
    for pruefung in (_zustand_veraltet, _doppelpreise, _speicherinversionen,
                     _farbspannen):
        weg, gefunden = pruefung(uebrig, katalog)
        raus |= weg
        befunde.extend(gefunden)
        if weg:
            uebrig = [e for e in uebrig if _schluessel(e) not in weg]

    # Die MELDENDE Pruefung sieht dagegen den ganzen Kandidatensatz, nicht den
    # Rest. Verkettet gemessen: bei "A 900 | B 200 | C 880 | C 850" nimmt der
    # Doppelpreis beide C-Zeilen heraus, die Gruppe faellt unter drei Angebote,
    # und der Median wird gar nicht mehr gerechnet - die 200-EUR-Zeile stuende
    # unmarkiert im Vergleich. Eine Pruefung, die nichts entfernt, darf ihr
    # Sichtfeld nicht von einer verlieren, die entfernt.
    _, ausreisser = _ausreisser(kandidaten, katalog)
    befunde.extend(b for b in ausreisser if b["listung_id"] not in raus)

    sauber = [e for e in eintraege if _schluessel(e) not in raus]
    entfernt = [b for b in befunde if b["entfernt"]]
    # Die Zeilen, die stehen bleiben und trotzdem einen Blick verdienen. Ein
    # Ausreisser ist der Befund, wegen dem diese Seite existiert - ein
    # Discounter 60 % unter dem Median ist das Signal, nicht der Fehler. Er
    # wird deshalb nicht geloescht, sondern an seiner Vergleichszeile
    # markiert, damit ein Mensch die Quelle aufruft und entscheidet.
    auffaellig = {b["listung_id"]: b for b in befunde
                  if b["art"] == "ausreisser" and b.get("listung_id")}
    return {
        "sauber": sauber,
        "auffaellig": auffaellig,
        "befunde": sorted(befunde, key=lambda b: (b["art"], b["anbieter"] or "",
                                                  b["geraet"])),
        "zahlen": {
            "geprueft": len(kandidaten),
            "aussortiert": len(raus),
            "zustand_veraltet": sum(1 for b in befunde
                                    if b["art"] == "zustand_veraltet"),
            "doppelpreise": sum(1 for b in befunde if b["art"] == "doppelpreis"),
            "speicherinversionen": sum(1 for b in befunde
                                       if b["art"] == "speicherinversion"),
            "farbspannen": sum(1 for b in befunde if b["art"] == "farbspanne"),
            "ausreisser": sum(1 for b in befunde if b["art"] == "ausreisser"),
            "befunde": len(befunde),
            # ZWEI verschiedene Zahlen, und sie duerfen nicht denselben Namen
            # bekommen: `aussortiert` sind die LISTUNGEN, die aus Vergleich
            # und Grafik fallen, `entfernt` die BEFUNDE, die das ausgeloest
            # haben. Ein Doppelpreis ist ein Befund und zwei Listungen - die
            # Seite meldete deshalb "2 aus dem Vergleich genommen", waehrend
            # die Listungszahl daneben um 4 fiel.
            "entfernt": len(entfernt),
        },
    }
