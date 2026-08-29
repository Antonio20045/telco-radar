"""Plausibilitaetspruefung des Geraetedatensatzes (W1.2, 29.08.2026).

Der Anlass steht in `claude/geraeteradar-evaluation-2026-08-29.md`: die
Vergleichstabelle meldete einen Wettbewerbsnachteil, wo in Wahrheit ein
Vorteil stand. Ein o2-Gebrauchtgeraet lief als Neugeraet mit, unterbot mit
seinem Gebrauchtpreis den Vodafone-Neupreis und stand als Sieger auf der
Seite.

Die URSACHE ist in `geraete_model._ZUSTAENDE` behoben. Dieses Modul ist das
NETZ darunter: es faengt denselben Fehlertyp beim naechsten Adapter, bei der
naechsten Schreibweise und bei der naechsten Quelle, ohne dass ihn wieder
jemand im Export von Hand finden muss.

Drei Pruefungen, alle gegen den fertigen Datensatz und alle vor dem Rendern:

    Doppelpreis        Dieselbe (Anbieter, Modell, Speicher, Zustand,
                       Preisart) mit zwei verschiedenen Preisen.
    Speicherinversion  Mehr Speicher kostet weniger als weniger Speicher.
    Ausreisser         Ein Preis weicht um mehr als AUSREISSER_ANTEIL vom
                       Median aller Preise fuer dasselbe (Modell, Speicher,
                       Zustand) ab.

Was ein Doppelpreis IST - und was nicht
---------------------------------------
Ein Farbaufschlag ist kein Widerspruch. Am 29.08.2026 ueber den echten
Bestand gemessen trennen sich die zwei Faelle sauber:

    112,3 %  o2  iPhone 14 Pro  128 GB   577 -> 1225   Gebrauchtgeraet
     53,0 %  o2  Galaxy S25     128 GB   577 ->  883   Gebrauchtgeraet
     21,6 %  o2  Galaxy S26 FE  128 GB   667 ->  811   "pistachio" / "pistachio bk"
      9,6 %  o2  Galaxy S26 U.  256 GB  1315 -> 1441   cobalt violet / schwarz
      5,7 %  o2  Galaxy S26     256 GB   955 -> 1009   cobalt violet / schwarz

Die beiden oberen sind Fehler, die drei unteren sind der Markt: Samsung
bepreist Aktionsfarben wirklich verschieden. Eine Regel, die alle fuenf
verwirft, loescht drei wahre Preise - und "mehr Daten sind nicht mehr Wert"
gilt in beide Richtungen. Deshalb wird JEDER Doppelpreis BERICHTET, aber nur
oberhalb von SPANNE_GRENZE auch AUSSORTIERT.

Fail closed in eine Richtung: eine aussortierte Zeile faellt aus Vergleich
UND Grafik, bleibt aber im CSV-Export und in der SKU-Ansicht. Was nicht
verglichen werden kann, verschwindet nicht - es wird nur nicht gegen etwas
gerechnet, das es nicht ist.
"""
from __future__ import annotations

from statistics import median

from ..geraete_model import VERGLEICHBARE_ZUSTAENDE, zustand_aus_titel

# Oberhalb dieser Spanne innerhalb einer Gruppe ist ein Doppelpreis kein
# Farbaufschlag mehr, sondern ein Hinweis auf zwei verschiedene Produkte.
# Gemessen am Bestand vom 29.08.2026 (siehe Modulkopf): die echten Fehler
# lagen bei 53 % und 112 %, die echten Farbpreise bei 5,7 bis 21,6 %.
SPANNE_GRENZE = 0.30

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


def _doppelpreise(eintraege: list, katalog) -> tuple[set, list]:
    gruppen: dict[tuple, list] = {}
    for e in eintraege:
        gruppen.setdefault(
            (e.get("anbieter"), e.get("device_id"), e.get("speicher_gb"),
             e.get("zustand") or "neu"), []).append(e)

    raus, befunde = set(), []
    for (anbieter, _gid, _sp, _zu), gruppe in gruppen.items():
        preise = {_preis(e) for e in gruppe}
        if len(preise) < 2:
            continue
        lo, hi = min(preise), max(preise)
        spanne = (hi - lo) / lo if lo else 0.0
        entfernt = spanne > SPANNE_GRENZE
        if entfernt:
            # Aussortiert wird die GANZE Gruppe, nicht nur der niedrigere
            # Preis: welcher der beiden stimmt, sagt der Datensatz nicht,
            # und den teureren stehen zu lassen waere dieselbe Raterei wie
            # den billigeren zu nehmen, nur mit umgekehrtem Vorzeichen.
            raus.update(_schluessel(e) for e in gruppe)
        befunde.append({
            "art": "doppelpreis",
            "anbieter": anbieter,
            "geraet": _label(gruppe[0], katalog),
            "spanne": round(spanne * 100, 1),
            "preise": sorted(preise),
            "farben": sorted({(e.get("farbe_normalisiert")
                               or e.get("farbe_roh") or "?") for e in gruppe}),
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

    Gibt `sauber` (die Eintraege, die in Vergleich und Grafik duerfen),
    `befunde` (jeder Treffer einzeln, fuer /geraete-quellen.html) und
    `zahlen` (die Kurzbilanz) zurueck. Der EINGABEDATENSATZ wird nicht
    veraendert - Export und SKU-Ansicht sehen weiterhin alles.
    """
    kandidaten = [e for e in eintraege if _vergleichbar(e)]

    raus: set = set()
    befunde: list = []
    for pruefung in (_zustand_veraltet, _doppelpreise,
                     _speicherinversionen, _ausreisser):
        weg, gefunden = pruefung(kandidaten, katalog)
        raus |= weg
        befunde.extend(gefunden)

    sauber = [e for e in eintraege if _schluessel(e) not in raus]
    entfernt = [b for b in befunde if b["entfernt"]]
    return {
        "sauber": sauber,
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
