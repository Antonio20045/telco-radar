"""Alles, was /geraete.html und /geraete-quellen.html brauchen.

Wie jede Dauerseite dieses Portals: ein `aufbereiten()`, das aus dem Zustand
ein fertiges Dict macht. Kein Netz, kein Modell, kein Schreibzugriff - die
Seite laesst sich damit ohne Lauf bauen und ohne Browser pruefen.

DIE POSITIONSKARTE
------------------
Vorbild ist die Canalys-Grafik "Flagship portfolios: price positioning": Y
ist der Preis in Euro, X sind kategoriale Spalten, jedes Geraet ein Punkt.
Zwei Dinge macht diese Umsetzung anders, und beide sind der eigentliche
Nutzen:

1. **Zwei Ansichten.** Spalten = HERSTELLER beantwortet "wie ist ein
   Portfolio ueber die Preisachse verteilt". Spalten = ANBIETER beantwortet
   "was kostet dasselbe Geraet bei wem" - und das ist die Frage, wegen der
   diese Seite existiert. Beide Ansichten werden hier fertig gerechnet; der
   Umschalter blendet nur um, er laedt nicht neu.
2. **Kollisionen werden entzerrt.** In der Vorlage ueberlappen die Labels.
   Punkte im selben Preisbereich bekommen hier einen senkrechten Versatz und
   eine Verbindungslinie zum echten Wert - der Punkt sitzt weiter auf seiner
   Preisachse, nur das Etikett rueckt.

Gerechnetes SVG, keine Bibliothek. Kein CDN-JS ist Hausregel, und die
Koordinaten stehen fertig im Datensatz - damit ist die Darstellung ohne
Browser testbar.

DIE ZWEI PREISARTEN
-------------------
In die Karte kommt ausschliesslich der Geraetepreis OHNE Vertrag. Eine
Zuzahlung im Tarifbuendel ist keine vergleichbare Zahl (Teil C4); sie steht
in der SKU-Matrix mit ihrem Tarif daneben, aber nie als Punkt neben einem
Ladenpreis.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from ..geraete_model import (VERGLEICHBARE_ZUSTAENDE, serie_aus_modell,
                             zustand_aus_feldern)
from . import geraete_alarme, geraete_pruefung, geraete_vergleich, geraete_verlauf
from ..analyze import geraete_lifecycle
from ..analyze.geraete_store import (
    GeraeteDB,
    Preishistorie,
    STATUS_AKTIV,
    STATUS_AUSGELISTET,
    STATUS_VERMUTLICH,
)

log = logging.getLogger(__name__)

# Die Positionskarte ist am 30.08.2026 GELOESCHT worden, nicht umgebaut.
# Sie zeigte 59 Geraete mal vier Anbietern in einem Bild - 114 senkrecht
# gedrehte Achsenbeschriftungen, 155 von 164 Punkten ohne Beschriftung - und
# drei Umschalter boten drei Ansichten derselben unlesbaren Grafik an. Ein
# Filter darauf haette den Fehler nicht behoben, sondern verkleinert.
#
# Was sie zeigen sollte, zeigt jetzt eine Tabelle (`geraete_alarme.py`).
# Ein Diagramm gibt es nur noch eines, es steht in "Preisverlauf", und es
# zeigt genau EIN Geraet.

_SICHTBAR = (STATUS_AKTIV, STATUS_VERMUTLICH)

# Wie weit "diese Woche" zurueckreicht. Bewusst weiter als sieben Tage: der
# Bericht erscheint zweimal woechentlich, und ein ausgefallener naechtlicher
# Lauf darf eine echte Bewegung nicht verschlucken.
FENSTER_TAGE = 14

EIGEN = ("vodafone",)

# --------------------------------------------------------------------------
# Die Veroeffentlichungsschwelle (CLAUDE.md §5)
# --------------------------------------------------------------------------
# Sie stand bis zum 11.08.2026 NUR im Test - und das war der Fehler daran:
# eine Schwelle, die nur ein Test kennt, kann die Navigation nicht schalten.
# Ein Mensch musste die Seite von Hand eintragen, und solange er das nicht
# tat, war sie fuer jeden Leser unsichtbar. Genau so ist es gekommen: die
# Seite stand live, war vollstaendig, und niemand konnte sie finden.
#
# Jetzt rechnet der Code sie, `base.html.j2` fragt sie ab, und der Test
# prueft BEIDE Zweige - unterhalb der Schwelle nicht verlinkt, oberhalb
# verlinkt.
#
# ZU DEN ZAHLEN. Anbieter steht auf DREI - dem Wert des Bauauftrags.
#
# Am 11.08.2026 stand er kurzzeitig auf zwei, mit der Begruendung, die Seite
# beantworte ihre erste und zweite Frage ("was fuehrt der Wettbewerb", "wo
# steht ein Geraet im Preis") auch mit zwei Laeden vollstaendig. Antonio hat
# das kassiert, nachdem er die Seite live gesehen hatte: sie soll nicht
# angezeigt werden, solange sie so aussieht.
#
# Er hat recht, und die Zahl macht es deutlicher als jede Erklaerung: von den
# zwei "Anbietern" traegt einer 84 von 85 Listungen. Die dritte Frage - "was
# kostet dasselbe Geraet bei wem" - ist die, wegen der diese Seite existiert,
# und mit einem echten Laden kann sie niemand beantworten. Eine Seite, die
# ihre Luecke beziffert, luegt zwar nicht; aber eine Marktuebersicht, die den
# Markt nicht zeigt, gehoert deshalb noch lange nicht in die Navigation.
#
# Die Seite wird weiter gebaut, getestet und ist ueber ihren direkten Link
# erreichbar - dieselbe Regel wie bei tarife.html und lieferzeit.html
# (CLAUDE.md §5). Sobald ein dritter Laden liefert, traegt sie sich selbst
# wieder ein; es braucht dafuer keine Handarbeit und keinen zweiten Ort.
SCHWELLE_ANBIETER = 3
SCHWELLE_HERSTELLER = 2
SCHWELLE_SKUS = 20


def schwelle_erreicht(anbieter: int, skus: int, hersteller: int) -> bool:
    """Darf die Seite in die Navigation? Eine Stelle, kein zweiter Ort."""
    return (anbieter >= SCHWELLE_ANBIETER and skus >= SCHWELLE_SKUS
            and hersteller >= SCHWELLE_HERSTELLER)

SEGMENT_LABEL = {"flagship": "Flaggschiff", "premium": "Premium",
                 "mid": "Mittelklasse", "entry": "Einstieg", "": "ohne Segment"}


def _ist_eigen(anbieter: str) -> bool:
    return (anbieter or "").strip().lower() in EIGEN


# --------------------------------------------------------------------------
# "Was diese Woche auffaellt"
# --------------------------------------------------------------------------

def zahlen_im_text(text: str) -> set:
    """JEDE Zahl eines Satzes, als Vergleichsform.

    Der erste Anlauf las nur Zahlen MIT Einheit (€, %) - und war damit fail
    OPEN: "Das iPhone kostet 999 Euro" kam vollstaendig erfunden durch, weil
    "Euro" ausgeschrieben war. Deshalb wird jetzt alles geprueft, und die
    Zahlen der Eigennamen ("iPhone 16 Pro Max", "1&1") kommen ueber
    `zahlen_der_namen()` in die erlaubte Menge. Ein Name ist keine
    Behauptung - aber er muss ANGEMELDET sein, nicht ungeprueft.

    Gelesen wird mit `strukturdaten.lies_preis`, derselben Funktion, die
    auch die Preise der Shops liest: zwei Zahlenleser waeren zwei Meinungen
    darueber, was "1.449" bedeutet, und der Waechter bliebe genau an dieser
    Differenz gruen, ohne etwas zu pruefen. Nur vor einem Prozentzeichen
    gilt das Komma als Dezimaltrenner ("27,8 %" ist 27,8 und nicht 278).
    """
    import re

    from ..collect.geraete.strukturdaten import lies_preis

    gefunden = set()
    for roh, prozent in re.findall(r"(\d[\d.,]*)\s*(%?)", text or ""):
        roh = roh.rstrip(".,")
        if not roh:
            continue
        if prozent:
            try:
                gefunden.add(round(float(roh.replace(",", ".")), 2))
            except ValueError:
                pass
            continue
        wert = lies_preis(roh)
        if wert is not None:
            gefunden.add(round(wert, 2))
        else:
            try:
                gefunden.add(round(float(roh.replace(".", "").replace(",", ".")), 2))
            except ValueError:
                pass
    return gefunden


def zahlen_der_namen(*namen) -> set:
    """Die Zahlen, die in Eigennamen stecken - "iPhone 16 Pro Max", "1&1",
    "Galaxy S25". Sie sind keine Behauptung ueber den Markt, muessen dem
    Waechter aber bekannt sein, sonst verwirft er wahre Saetze."""
    gefunden = set()
    for name in namen:
        gefunden |= zahlen_im_text(str(name or ""))
    return gefunden


def pruefe_zahlen(text: str, erlaubt: set) -> bool:
    """Steht jede Zahl dieses Satzes wirklich im Datensatz?

    Akzeptanzkriterium aus Teil E: "Ein Preis, der nicht im Rohdatensatz
    steht, kommt nicht in den Text der Karte." Die Saetze entstehen derzeit
    deterministisch aus den Daten - der Waechter ist trotzdem gebaut und
    getestet, denn genau an dieser Stelle wuerde ein Editor spaeter
    ansetzen, und dann muss die Sperre schon dastehen statt erst gebaut zu
    werden.

    Vorbild ist `analyze/faithfulness.py`: fail closed. Was sich nicht
    pruefen laesst, erscheint nicht.
    """
    return zahlen_im_text(text).issubset({round(float(z), 2) for z in erlaubt})


def _im_fenster(datum: str, heute: str, tage: int = FENSTER_TAGE) -> bool:
    """Liegt *datum* im Berichtsfenster?

    Ohne diese Pruefung stand eine Preisaenderung vom 9. Maerz in der
    Augustausgabe unter "Was diese Woche auffaellt" - und blieb dort in
    JEDER Ausgabe stehen, bis sich der Preis wieder aenderte. Die Rubrik
    heisst "diese Woche"; dann muss sie auch eine Woche meinen.

    Das Fenster ist mit vierzehn Tagen bewusst weiter als eine Woche: der
    Bericht erscheint zweimal woechentlich, und ein ausgefallener
    naechtlicher Lauf darf eine echte Bewegung nicht verschlucken.
    """
    if not datum or not heute:
        return False
    a, b = _tag(datum), _tag(heute)
    if a is None or b is None:
        return False
    return 0 <= (b - a).days <= tage


def _tag(wert):
    from datetime import datetime
    try:
        return datetime.strptime(str(wert).strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _auffaellig(eintraege: list, historie: Preishistorie, katalog,
                heute: str, laeufe: int = 0) -> dict:
    """Die groessten Bewegungen DIESES Zeitraums - aus den Deltas gerechnet.

    DER BEZUG IST DIE MESSUNG, NICHT DER BERICHTSTAG. Der Geraetezweig laeuft
    naechtlich und committet seinen Stand; der Bericht erscheint zweimal die
    Woche. Die Geraetedaten sind damit REGELMAESSIG neuer als `heute` - am
    11.08.2026 gemessen: Bestand vom 11., letzter Bericht vom 8. Weil das
    Fenster nur zurueckschaut, fiel jede Aenderung heraus, und die Sektion
    stand leer da, obwohl frische Daten vorlagen. Als Bezug gilt deshalb der
    spaetere der beiden Tage.
    """
    # Ueber `_tag()`, nicht ueber rohe Zeichenketten: ein kaputtes `datum`
    # ("unbekannt") sortiert lexikalisch hinter jedes ISO-Datum, wuerde
    # Bezugstag und liesse `_im_fenster` fuer ALLES falsch werden - die
    # ganze Sektion verschwaende lautlos.
    juengste = sorted(d for d in (_tag(p.get("datum"))
                                  for p in historie.alle_punkte()) if d)
    bezug = _tag(heute)
    if juengste and (bezug is None or juengste[-1] > bezug):
        heute = juengste[-1].isoformat()
    bewegungen = []
    for e in eintraege:
        reihe = historie.reihe(e["id"])
        if len(reihe) < 2:
            continue
        if not _im_fenster(reihe[-1].get("datum", ""), heute):
            continue
        alt = reihe[-2].get("preis_ohne_vertrag")
        neu = reihe[-1].get("preis_ohne_vertrag")
        if alt is None or neu is None or alt == 0 or alt == neu:
            continue
        g = katalog.nach_id(e.get("device_id"))
        bewegungen.append({
            "modell": g.modell if g else e.get("device_id"),
            "anbieter": e.get("anbieter"),
            "von": alt, "auf": neu,
            "delta": round(neu - alt, 2),
            "prozent": round((neu - alt) / alt * 100.0, 1),
            "datum": reihe[-1].get("datum", ""),
            "url": e.get("quelle_url", ""),
        })
    bewegungen.sort(key=lambda b: -abs(b["delta"]))

    # Ein Fenster, kein Stichtag. Der naechtliche Lauf schreibt an sechs von
    # sieben Tagen ein Datum, das nie ein Renderdatum ist - mit `== heute`
    # tauchte nur auf, was der Bericht selbst gefunden hat.
    neu_gelistet = [e for e in eintraege if _im_fenster(e.get("first_seen", ""), heute)]
    verschwunden = [e for e in eintraege
                    if e.get("status") == STATUS_AUSGELISTET
                    and _im_fenster(e.get("ended_since", ""), heute)]

    # W3 (29.08.2026): die Karte sagte "267 Geraete neu im Regal", waehrend
    # die Seite daneben 59 beobachtete Geraete auswies. Gezaehlt wurden
    # LISTUNGEN - dasselbe Geraet bei vier Anbietern in acht Farben sind 32
    # Listungen und EIN Geraet. Eine Kennzahl, die groesser ist als ihre
    # eigene Grundgesamtheit, macht jede andere Zahl der Seite unglaubwuerdig.
    #
    # Beide Zahlen bleiben stehen, sie heissen nur richtig: `*_geraete`
    # traegt den Satz, die Listungszahl bleibt fuer die Tabelle darunter.
    neu_geraete = {e.get("device_id") for e in neu_gelistet if e.get("device_id")}
    weg_geraete = {e.get("device_id") for e in verschwunden if e.get("device_id")}

    erlaubt = set()
    for b in bewegungen:
        erlaubt.update({abs(b["delta"]), b["von"], b["auf"], abs(b["prozent"])})
        erlaubt |= zahlen_der_namen(b["modell"], b["anbieter"])
    erlaubt.update({len(neu_gelistet), len(verschwunden), len(bewegungen),
                    len(neu_geraete), len(weg_geraete)})

    # Gibt es ueberhaupt einen Vorlauf zum Vergleichen? Dann zeigt die Karte,
    # was neu ERFASST wurde, und sagt das auch so - "keine Auffaelligkeiten"
    # ist etwas anderes als "noch nichts zu vergleichen".
    #
    # Gefragt wird die LAUFBILANZ, nicht die Preishistorie. Die erste Fassung
    # zaehlte Messtage in `geraete_preise.jsonl` - und die Datei traegt nur
    # Aenderungspunkte: ein Anbieter, der wegbricht, schreibt gar keine mehr,
    # waehrend `mark_stale` seine Listungen altert. Genau dann haette die
    # Kachel "ausgelistet" den Einbruch gezeigt und war ausgeblendet.
    ohne_vorlauf = laeufe < 2

    saetze = []
    for b in bewegungen[:5]:
        richtung = "günstiger" if b["delta"] < 0 else "teurer"
        saetze.append(f"{b['modell']} bei {b['anbieter']}: "
                      f"{abs(b['delta']):.2f} € {richtung} "
                      f"({b['von']:.2f} € auf {b['auf']:.2f} €).")
    if neu_geraete and ohne_vorlauf:
        saetze.append(f"{len(neu_geraete)} Gerät"
                      f"{'e' if len(neu_geraete) != 1 else ''} erstmals "
                      f"erfasst – es gibt noch keinen früheren Stand, gegen "
                      f"den sich vergleichen ließe.")
    elif neu_geraete:
        saetze.append(f"{len(neu_geraete)} Gerät{'e' if len(neu_geraete) != 1 else ''} "
                      f"neu im Regal.")
    if weg_geraete and not ohne_vorlauf:
        saetze.append(f"{len(weg_geraete)} Gerät{'e' if len(weg_geraete) != 1 else ''} "
                      f"aus dem Portfolio gefallen.")

    # Fail closed: ein Satz, dessen Zahlen nicht im Datensatz stehen,
    # erscheint nicht. Heute kann das nicht passieren - morgen, mit einem
    # Editor davor, schon.
    geprueft = [s for s in saetze if pruefe_zahlen(s, erlaubt)]
    if len(geprueft) != len(saetze):
        log.warning("Geraeteradar: %d Satz/Saetze mit ungedeckten Zahlen "
                    "verworfen", len(saetze) - len(geprueft))

    return {
        "saetze": geprueft,
        "neu_gelistet": len(neu_gelistet),
        "neu_gelistet_geraete": len(neu_geraete),
        "verschwunden": len(verschwunden),
        "verschwunden_geraete": len(weg_geraete),
        "bewegungen": bewegungen[:12],
        "neu": [{"modell": (katalog.nach_id(e.get("device_id")).modell
                            if katalog.nach_id(e.get("device_id"))
                            else e.get("device_id")),
                 "anbieter": e.get("anbieter"), "url": e.get("quelle_url", "")}
                for e in neu_gelistet[:12]],
        "weg": [{"modell": (katalog.nach_id(e.get("device_id")).modell
                            if katalog.nach_id(e.get("device_id"))
                            else e.get("device_id")),
                 "anbieter": e.get("anbieter"), "seit": e.get("ended_since", "")}
                for e in verschwunden[:12]],
        "hat_daten": bool(geprueft or bewegungen),
        "ohne_vorlauf": ohne_vorlauf,
    }


# --------------------------------------------------------------------------
# SKU-Matrix
# --------------------------------------------------------------------------

# Wie viele Katalogzeilen ohne Aufklappen stehen. GERECHNET wie
# `geraete_alarme.SICHTBAR_MAX`, am 30.08.2026 im echten Chromium gegen den
# ECHTEN Bestand: mit 25 Zeilen mass der Reiter 3353 px, mit 18 noch 3304,
# mit 12 dann 2- statt 3-tausender.
#
# Warum 18 nicht reichte, obwohl die Rechnung "68 px je Zeile" es hergab:
# eine Zeilenhoehe ist keine Konstante. Der naechtliche Lauf brachte 360
# statt 352 Listungen, und mit ihnen laengere Modellnamen - dieselbe
# Zeilenzahl wurde hoeher. Ein Deckel in ZEILEN ist immer nur ein Stellver-
# treter fuer eine Grenze in PIXELN; er braucht deshalb Reserve, nicht die
# knappste Zahl, die heute gerade passt. Dieselbe Fehlerklasse wie die
# Datums-Zeitbomben, nur ueber den Bestand statt ueber die Uhr.
#
# Die Zahl steht hier und nicht in der Vorlage, damit ein Test sie gegen die
# gemessene Hoehe halten kann.
KATALOG_SICHTBAR = 12


def katalogzeilen(eintraege: list, katalog) -> list[dict]:
    """Reiter 2 als FLACHE Tabelle: eine Zeile je (Geraet, Speicher, Farbe,
    Anbieter).

    Bis zum 30.08.2026 stand hier eine Matrix Modell x Anbieter plus 65
    Aufklapper - eine Zelle sagte "3 Varianten, 799-899 EUR", und wer wissen
    wollte, WELCHE, klappte zweimal auf. Der Auftrag verlangt stattdessen die
    flache Form: jede Zeile traegt alles, was sie behauptet, und die
    Filterleiste von Reiter 1 arbeitet darauf.

    Gezeigt wird ALLES, auch refurbished und Zuzahlungen - anders als in
    Vergleich und Diagramm. Dieser Reiter ist der Bestand, nicht die Aussage:
    was aus dem Vergleich faellt, verschwindet nicht, es wird nur nicht gegen
    etwas gerechnet, das es nicht ist.
    """
    zeilen = []
    for e in eintraege:
        g = katalog.nach_id(e.get("device_id")) if katalog else None
        preis = e.get("preis_ohne_vertrag")
        # Der Zustand wird NEU ABGELEITET, nicht aus dem Store uebernommen.
        # Sonst steht in dieser Tabelle "space schwarz erneuert - Zustand
        # neu", waehrend der Pruefbericht zwei Reiter weiter "refurbished"
        # sagt: die Seite widerspraeche sich selbst, und der Store ist die
        # schwaechere Quelle - er traegt seinen alten Wert bis zum naechsten
        # erfolgreichen Crawl.
        zustand = zustand_aus_feldern(
            e.get("titel_roh"), e.get("farbe_roh"), e.get("quelle_url"))
        if zustand in VERGLEICHBARE_ZUSTAENDE:
            zustand = e.get("zustand") or "neu"
        zeilen.append({
            "modell": g.modell if g else (e.get("device_id") or "?"),
            "hersteller": g.hersteller if g else "",
            "speicher": e.get("speicher_gb"),
            "farbe": e.get("farbe_normalisiert") or e.get("farbe_roh") or "",
            "anbieter": e.get("anbieter"),
            "anbieter_typ": e.get("anbieter_typ") or "",
            "netz": e.get("netz") or "",
            "zustand": zustand,
            "preis": preis,
            "zuzahlung": e.get("zuzahlung"),
            "tarif": e.get("tarif_referenz") or "",
            "verfuegbarkeit": e.get("verfuegbarkeit") or "unbekannt",
            "url": e.get("quelle_url") or "",
            "abgerufen_am": e.get("abgerufen_am") or "",
        })
    # Nach Modell, dann Speicher, dann dem GEZEIGTEN Betrag: wer ein Geraet
    # sucht, findet seine Zeilen beieinander, und innerhalb steht der
    # guenstigste oben.
    #
    # "Der gezeigte Betrag" und nicht `preis`: die Spalte zeigt bei einer
    # Zeile ohne Barpreis die Zuzahlung. Mit `float("inf")` fuer fehlende
    # Preise landete eine 1-Euro-Zuzahlung hinter einem 1199-Euro-Barpreis,
    # und der Kommentar darueber behauptete das Gegenteil. Heute folgenlos
    # (alle 352 Zeilen tragen einen Barpreis), aber der naechste
    # Buendelpreis-Adapter loest es aus.
    def betrag(z):
        for feld in ("preis", "zuzahlung"):
            if z[feld] is not None:
                return z[feld]
        return float("inf")

    return sorted(zeilen, key=lambda z: (
        z["hersteller"], z["modell"], z["speicher"] or 0,
        betrag(z), z["anbieter"] or ""))


# `_matrix()` ist am 30.08.2026 geloescht worden, mit der Sektion, die es
# fuellte. Es rechnete Modell x Anbieter mit Variantenzahl und Preisspanne je
# Zelle; Reiter 2 zeigt seitdem eine flache Tabelle, in der jede Zeile
# traegt, was sie behauptet (`katalogzeilen`). Die Rechnung weiter laufen zu
# lassen und von keiner Vorlage lesen zu lassen waere derselbe Befund wie
# `UEBERSICHT_MAX_ZEILEN` beim Review davor: lebendig klingende Begruendung,
# keine Wirkung.

def _quellenlage(quellen, db: GeraeteDB, eintraege: list) -> dict:
    """Wer liefert, wer nicht - und warum nicht.

    Kein Anbieter verschwindet stillschweigend (Teil E). Das gilt auch fuer
    die Marken ohne Hardware-Vermarktung: sie stehen in einer eigenen Zeile,
    nicht als leere Karte im Raster.
    """
    mit_daten = {e.get("anbieter") for e in eintraege}
    bekannt = {a.name for a in quellen.anbieter}
    zeilen, ohne_hardware = [], []
    for a in sorted(quellen.anbieter, key=lambda x: (x.rang, x.name)):
        vermarktung = db.hardware_vermarktung(a.name)
        if a.methode == "kein_hardware":
            vermarktung = "nein"
        satz = {
            "name": a.name, "typ": a.typ, "netz": a.netz, "gruppe": a.gruppe,
            "rang": a.rang, "methode": a.methode, "eigen": a.eigen,
            "aktiv": a.aktiv, "crawlbar": a.crawlbar, "grund": a.grund,
            "hinweis": a.hinweis,
            "einstiege": [{"url": e.url, "label": e.label, "kind": e.kind}
                          for e in a.crawled_einstiege],
            "geraete": sum(1 for e in eintraege if e.get("anbieter") == a.name),
            "liefert": a.name in mit_daten,
            "hardware_vermarktung": vermarktung,
            "bilanz": db.laufbilanz(a.name),
        }
        # GENAU DREI ZUSTAENDE, und keiner davon heisst "gemessen, aber ohne
        # Adapter". Diese vierte Kategorie ist am 30.08.2026 abgeschafft
        # worden, weil sie nichts aussagte: sie stand fuer "koennte man
        # bauen" und blieb stehen, ohne dass jemand entschied.
        #
        # Der mittlere Zustand heisst "ohne_daten" und nicht "gesperrt", und
        # das ist keine Wortklauberei: Medimax und ElectronicPartner sind
        # AKTIV, tragen einen Adapter und werden jede Nacht abgerufen - sie
        # finden nur seit sechzehn Naechten nichts. Als "gesperrt" gefuehrt
        # behauptete die Seite eine Sperre, die es nicht gibt, und der
        # eigentliche Befund (ein kaputter Extraktor) verschwand hinter dem
        # falschen Etikett. Der Auftrag nennt beide Faelle nebeneinander:
        # "technisch gesperrt, begruendet" und "ohne Fund, Ursache X".
        satz["zustand"] = ("liefert" if satz["liefert"]
                           else "ohne_hardware" if vermarktung == "nein"
                           else "ohne_daten")
        if vermarktung == "nein":
            ohne_hardware.append(satz)
        else:
            zeilen.append(satz)

    # Ein Anbieter, der in der Datenbank steht, aber nicht (mehr) in der
    # Konfiguration: umbenannt, entfernt, vertippt. Die Datenbank loescht per
    # Design nie, also bleibt er da - und faellt sonst genau unter dem Satz
    # durch, der verspricht, dass kein Anbieter stillschweigend fehlt.
    for name in sorted(n for n in mit_daten if n and n not in bekannt):
        zeilen.append({
            "name": name, "typ": "", "netz": "", "gruppe": "", "rang": 999,
            "methode": "nicht konfiguriert", "eigen": False, "aktiv": False,
            "crawlbar": False,
            "grund": "Steht mit Daten in der Datenbank, aber nicht in "
                     "config/geraete_quellen.yaml - umbenannt oder entfernt. "
                     "Die Bestandseinträge bleiben, werden aber nicht mehr "
                     "aufgefrischt.",
            "hinweis": "", "einstiege": [],
            "geraete": sum(1 for e in eintraege if e.get("anbieter") == name),
            "liefert": True, "hardware_vermarktung": "ja",
            "zustand": "liefert",
            "bilanz": db.laufbilanz(name),
        })

    return {
        "zeilen": zeilen,
        "ohne_hardware": ohne_hardware,
        "liefernd": sum(1 for z in zeilen if z["liefert"]),
        # Der Nenner der Zeile "N von M liefern Daten" muss zu den ZEILEN
        # passen, die darunter stehen - sonst steht ueber 21 Zeilen die Zahl
        # 23 (der Fehlertyp aus CLAUDE.md §6).
        "aufgefuehrt": len(zeilen),
        # Die drei Zustaende als Zahlen. Sie muessen sich auf `konfiguriert`
        # summieren - eine vierte Kategorie kann damit nicht unbemerkt
        # zurueckwachsen, und genau davon kam dieser Abschnitt.
        #
        # Gezaehlt wird nur, was KONFIGURIERT ist. `zeilen` traegt zusaetzlich
        # die Anbieter, die in der Datenbank stehen und nicht (mehr) in der
        # Konfiguration - umbenannt oder entfernt. Sie mitzuzaehlen liesse die
        # Summe ueber `konfiguriert` steigen, und die Seite meldete "5 von 4
        # konfigurierten Anbietern liefern". Der Zweig existiert genau fuer
        # diesen Fall; ihn in die Invariante zu ziehen hiesse, sie beim
        # ersten Umbenennen zu brechen.
        "liefernd_konfiguriert": sum(1 for z in zeilen
                                     if z["liefert"] and z["name"] in bekannt),
        "ohne_daten": sum(1 for z in zeilen if z["zustand"] == "ohne_daten"),
        "ohne_hardware_zahl": len(ohne_hardware),
        "nicht_konfiguriert": sum(1 for z in zeilen if z["name"] not in bekannt),
        "konfiguriert": len(quellen.anbieter),
        "unbekannt": [n for n in sorted(mit_daten) if n and n not in bekannt],
        "seiten": quellen.seiten_zahl,
    }


def _farbbericht(eintraege: list) -> list:
    """Unbekannte Farbschreibweisen mit der Zahl ihrer Listungen.

    Die Arbeitsliste fuer config/farben.yaml. Sie speist sich aus den
    FARBFELDERN der Quellen - eine Farbe, die nur im Titel stand und die
    Tabelle nicht kennt, taucht hier nicht auf, weil sie gar nicht erst
    uebernommen wird (das waere Raten).
    """
    gezaehlt: dict[str, int] = {}
    for e in eintraege:
        if e.get("farbe_roh") and not e.get("farbe_normalisiert"):
            gezaehlt[e["farbe_roh"]] = gezaehlt.get(e["farbe_roh"], 0) + 1
    return [{"schreibweise": k, "listungen": v}
            for k, v in sorted(gezaehlt.items(), key=lambda kv: (-kv[1], kv[0]))]


def _katalogluecken(katalog) -> dict:
    ohne_start = [g.modell for g in katalog.geraete if not g.marktstart]
    ohne_kette = [g.modell for g in katalog.geraete
                  if g.vorgaenger and katalog.nach_id(g.vorgaenger_device_id) is None]
    return {
        "modelle": len(katalog.geraete),
        "ohne_marktstart": sorted(ohne_start),
        "ohne_kette": sorted(ohne_kette),
    }


# --------------------------------------------------------------------------
# Der Einstieg
# --------------------------------------------------------------------------

def leer(fehler: str = "") -> dict:
    """Der Notzustand: die Seite entsteht trotzdem und sagt, was los ist.

    Ohne ihn liess ein einziger kaputter Eintrag beide Seiten ganz
    verschwinden - und weil `site/` committet wird, blieb live die Fassung
    der Vorwoche stehen. Ein Totalausfall, der wie ein gruener Lauf aussieht.
    """
    return {
        "hat_daten": False, "stand": "", "abgerufen_bis": "", "abgerufen_ab": "",
        "fenster_tage": FENSTER_TAGE, "ohne_katalog": [], "db_lesbar": not fehler,
        "fehler": fehler,
        "bilanz": {"geraete": 0, "listungen": 0, "skus": 0, "anbieter": 0,
                   "ausgelistet": 0, "preispunkte": 0, "hersteller": 0,
                   "schwelle_erreicht": False},
        # Der Notzustand muss JEDES Feld tragen, das die Vorlage liest -
        # genau dafuer gibt es ihn. Die Alarme kommen aus derselben Funktion
        # wie im Normalfall, damit die zwei Schluesselmengen nicht
        # auseinanderlaufen koennen (ein Test haelt sie gegeneinander).
        "alarme": geraete_alarme.leer(),
        "segmente": [], "segment_label": SEGMENT_LABEL, "speicherstufen": [],
        "verlauf": geraete_verlauf.leer(),
        "katalogtabelle": [],
        "katalog_sichtbar": KATALOG_SICHTBAR,
        "auffaellig": {"hat_daten": False, "saetze": [], "bewegungen": [],
                       "neu": [], "weg": []},
        "alle_eintraege": [], "alle_punkte": [], "katalog_obj": None,
        "export": {"stand": "", "aktuell": {"datei": "", "zeilen": 0, "bytes": 0},
                   "historie": {"datei": "", "zeilen": 0, "bytes": 0}},
        "vergleich": {"hat_daten": False, "standard": "ohne_vertrag",
                      "ohne_vertrag": {"zeilen": [], "ohne_vodafone": [],
                                       "hat_daten": False, "hat_vodafone": False,
                                       "mit_vorteil": 0, "ohne_vorteil": 0,
                                       "ohne_vodafone_gesamt": 0,
                                       "groesste_differenz": None,
                                       "preisart": "ohne_vertrag"},
                      "mit_vertrag": {"zeilen": [], "ohne_vodafone": [],
                                      "hat_daten": False, "hat_vodafone": False,
                                      "mit_vorteil": 0, "ohne_vorteil": 0,
                                      "ohne_vodafone_gesamt": 0,
                                      "groesste_differenz": None,
                                      "preisart": "mit_vertrag"}},
        "lifecycle": {"duenn": True, "punkte": 0, "wochen": 0, "hinweis": "",
                      "dauern": [], "verfaelle": [], "trends": [],
                      "nachfolger": [], "portfolio": []},
        "quellenlage": {"zeilen": [], "ohne_hardware": [], "liefernd": 0,
                        "aufgefuehrt": 0, "konfiguriert": 0, "unbekannt": [],
                        "seiten": 0},
        "farbbericht": [],
        "katalog": {"modelle": 0, "ohne_marktstart": [], "ohne_kette": []},
    }


def aufbereiten(state_dir: Path, quellen, katalog, heute: str = "") -> dict:
    """Alles fuer /geraete.html und /geraete-quellen.html."""
    state_dir = Path(state_dir)
    db = GeraeteDB(state_dir / "geraete_db.json")
    historie = Preishistorie(state_dir / "geraete_preise.jsonl")
    alle = db.eintraege()
    sichtbar = [e for e in alle if e.get("status") in _SICHTBAR]

    # W1.2 (29.08.2026): bevor irgendetwas gerendert wird, laeuft die
    # Plausibilitaetspruefung ueber den Datensatz. Was sie aussortiert, faellt
    # aus Vergleich UND Preisgrafik - beides sind Preisaussagen, und eine
    # Preisaussage aus zwei widerspruechlichen Zahlen ist keine. Der
    # CSV-Export und die SKU-Ansicht sehen weiterhin ALLES: eine Zeile, die
    # sich nicht vergleichen laesst, ist deshalb nicht verschwunden.
    pruefung = geraete_pruefung.pruefe(sichtbar, katalog)
    belastbar = pruefung["sauber"]

    # Laden und Anzeigename je Anbieter. Zwei Marken desselben Shops
    # (mobilcom-debitel/freenet) muessen EINE Spalte werden, sonst vergleicht
    # die Karte einen Laden mit sich selbst.
    laden = {a.name: (a.shop or a.name) for a in getattr(quellen, "anbieter", [])}
    anzeige = {a.name: (a.anzeige or a.name)
               for a in getattr(quellen, "anbieter", [])}
    # Der Anzeigename haengt am LADEN, nicht am Markennamen: die Spalte heisst
    # nach dem Shop, und der Shop traegt den Namen, unter dem seine Quelle
    # erreichbar ist.
    anzeige.update({(a.shop or a.name): (a.anzeige or a.name)
                    for a in getattr(quellen, "anbieter", [])})

    punkte_ohne_vertrag = []
    for e in belastbar:
        preis = e.get("preis_ohne_vertrag")
        if preis is None:
            continue
        g = katalog.nach_id(e.get("device_id"))
        speicher = e.get("speicher_gb")
        name = e.get("anbieter")
        punkte_ohne_vertrag.append({
            "shop": laden.get(name, name),
            "anbieter_anzeige": anzeige.get(name, name),
            "sku_id": e.get("sku_id"),
            "device_id": e.get("device_id"),
            "hersteller": g.hersteller if g else "ohne Katalogeintrag",
            "modell": g.modell if g else e.get("device_id"),
            "generation": g.generation if g else None,
            "segment": g.segment if g else "",
            "anbieter": e.get("anbieter"),
            "anbieter_typ": e.get("anbieter_typ", ""),
            "preis": float(preis),
            "speicher": speicher,
            "farbe": e.get("farbe_normalisiert") or e.get("farbe_roh") or "",
            # Ein refurbished Geraet ist nicht dasselbe Angebot wie ein neues
            # - es gehoert in den Aggregationsschluessel, sonst schluckt der
            # niedrigere Preis den hoeheren.
            "zustand": e.get("zustand") or "neu",
            "verfuegbarkeit": e.get("verfuegbarkeit", "unbekannt"),
            "url": e.get("quelle_url", ""),
            "abgerufen_am": e.get("abgerufen_am", ""),
            "eigen": _ist_eigen(e.get("anbieter", "")),
            "label": f"{g.modell if g else e.get('device_id')}"
                     + (f" · {speicher} GB" if speicher else ""),
        })

    # Die aktuelle Generation JE BAUREIHE, nicht je Hersteller. `generation`
    # ist die Nummer innerhalb einer Reihe: Samsungs Galaxy A57 traegt 57,
    # die Galaxy S26 traegt 26, das Galaxy Z Fold8 traegt 8. Je Hersteller
    # verglichen gewinnt die A-Reihe - die Standardansicht zeigte am
    # 29.08.2026 drei Galaxy A57 und keine einzige S26, also das aktuelle
    # Flaggschiff nicht. Der Filter blendet weiterhin, er rechnet nicht neu.
    for p in punkte_ohne_vertrag:
        p["serie"] = serie_aus_modell(p.get("modell") or "")
    hoechste: dict[tuple, int] = {}
    for p in punkte_ohne_vertrag:
        if p["generation"] is None:
            continue
        schluessel = (p["hersteller"], p["serie"])
        hoechste[schluessel] = max(hoechste.get(schluessel, 0), p["generation"])
    for p in punkte_ohne_vertrag:
        p["aktuelle_generation"] = (
            p["generation"] is not None
            and p["generation"] == hoechste.get((p["hersteller"], p["serie"])))

    # Wie oft ist der Geraetezweig ueberhaupt schon gelaufen? Das ist die
    # Frage hinter "gibt es einen frueheren Stand" - und sie wird an den
    # MESSTERMINEN beantwortet, nicht an der Preishistorie (die traegt nur
    # Aenderungspunkte und schweigt, wenn sich nichts aendert) und nicht an
    # `laeufe` (das zaehlt nur VOLLSTAENDIGE Laeufe - mobilcom-debitel wird
    # jede Nacht bestaetigt und war dort trotzdem nie verbucht, weil sein
    # Lauf am Zeitbudget nie fertig wurde).
    punkte_alle = historie.alle_punkte()
    termine_je_anbieter: dict[str, list] = {}
    laeufe_je_anbieter: dict[str, int] = {}
    for name in {e.get("anbieter") for e in alle if e.get("anbieter")}:
        termine = set(db.messtermine(name))
        termine.update(p.get("datum") for p in punkte_alle
                       if p.get("anbieter") == name and p.get("datum"))
        termine_je_anbieter[name] = sorted(termine)
        laeufe_je_anbieter[name] = int(db.laufbilanz(name).get("laeufe") or 0)
    laeufe = max((max(len(t), laeufe_je_anbieter.get(n, 0))
                  for n, t in termine_je_anbieter.items()), default=0)
    auffaellig = _auffaellig(alle, historie, katalog, heute, laeufe=laeufe)
    lifecycle = geraete_lifecycle.auswertung(
        alle, punkte_alle, katalog, heute,
        laeufe_je_anbieter=laeufe_je_anbieter,
        termine_je_anbieter=termine_je_anbieter)

    # Das ECHTE Abrufdatum. Faellt der naechtliche Lauf zwei Wochen aus,
    # behaelt die Datenbank ihre alten Werte - die Legende darf trotzdem
    # nicht den Berichtstag behaupten. Auf einer Seite, deren Verkaufsargument
    # der Belegzwang ist, ist das die teuerste Sorte falscher Zahl.
    abrufdaten = sorted(e.get("abgerufen_am") for e in sichtbar
                        if e.get("abgerufen_am"))
    ohne_katalog = sorted({e.get("device_id") for e in sichtbar
                           if katalog.nach_id(e.get("device_id")) is None})

    # Gezaehlt werden LAEDEN, nicht Marken. Die dritte Frage der Seite lautet
    # "was kostet dasselbe Geraet bei wem" - und zwei Marken desselben Shops
    # (mobilcom-debitel/freenet) beantworten sie nicht. Mit Marken gezaehlt
    # schaltete sich der Navigationseintrag mit "2 Anbietern" frei, waehrend
    # nur EIN Laden lieferte.
    laeden_mit_daten = {laden.get(e.get("anbieter"), e.get("anbieter"))
                        for e in sichtbar}
    # Die Veroeffentlichungsschwelle rechnet gegen den BESTAND, nicht gegen
    # die Karte. Bis zum 29.08.2026 nahm sie die Spaltenzahl der
    # Herstelleransicht - und die haengt seit W1.2 an der
    # Plausibilitaetspruefung. Damit haette ein Anbieter, der an einem Tag
    # seine Farbvarianten mit weiten Farbabstaenden bepreist, den
    # Navigationseintrag "Geraete" auf JEDER Seite verschwinden lassen -
    # ohne Fehler, ohne Warnung, und niemand faende die Seite mehr. Eine
    # Datenqualitaetsheuristik darf keine Navigation schalten.
    hersteller_mit_daten = {
        g.hersteller for g in (katalog.nach_id(e.get("device_id"))
                               for e in sichtbar)
        if g and g.hersteller}
    erreicht = schwelle_erreicht(
        anbieter=len(laeden_mit_daten),
        skus=len({e.get("sku_id") for e in sichtbar}),
        hersteller=len(hersteller_mit_daten))

    # Reiter 1. Die Alarmtabelle liest den fertigen Vergleich - sie rechnet
    # keine Zahl zweimal (CLAUDE.md 6: zwei Rechnungen fuer dieselbe Zahl
    # sind zwei Zahlen). Die Ausreisser-Markierung kommt aus der Pruefung:
    # ein Ausreisser wird gemeldet statt geloescht, und gemeldet heisst DORT
    # sichtbar, wo jemand die Zahl liest.
    vergleich = geraete_vergleich.beide_preisarten(belastbar, katalog,
                                                   laeden=laden)
    alarme = geraete_alarme.zeilen(vergleich["ohne_vertrag"],
                                   pruefung.get("auffaellig"))

    return {
        # Der Verlauf rechnet auf `belastbar`, nicht auf `sichtbar`: ein
        # falsch gespeicherter Gebrauchtpreis in derselben Kurve ist ein
        # zweites Produkt in einer Linie, und der Sprung dazwischen saehe aus
        # wie ein Preissturz. Am Galaxy S25 128 GB gemessen macht das den
        # Unterschied zwischen "577-899 EUR" und "850-899 EUR".
        "verlauf": geraete_verlauf.aufbereiten(belastbar, historie, katalog),
        # Reiter 2 zeigt den BESTAND, also `sichtbar` und nicht `belastbar`:
        # eine refurbished Zeile gehoert nicht in den Vergleich, aber sehr
        # wohl in den Katalog.
        "katalogtabelle": katalogzeilen(sichtbar, katalog),
        "katalog_sichtbar": KATALOG_SICHTBAR,
        "pruefung": pruefung["zahlen"],
        "pruefbefunde": pruefung["befunde"],
        "hat_daten": bool(sichtbar),
        "stand": heute,
        "abgerufen_bis": abrufdaten[-1] if abrufdaten else "",
        "abgerufen_ab": abrufdaten[0] if abrufdaten else "",
        "fenster_tage": FENSTER_TAGE,
        "ohne_katalog": ohne_katalog,
        "db_lesbar": db.lesbar,
        "bilanz": {
            "geraete": len({e.get("device_id") for e in sichtbar}),
            "listungen": len(sichtbar),
            "skus": len({e.get("sku_id") for e in sichtbar}),
            "anbieter": len(laeden_mit_daten),
            "ausgelistet": sum(1 for e in alle
                               if e.get("status") == STATUS_AUSGELISTET),
            # Ohne einen frueheren Stand ist "0 ausgelistet" keine Aussage,
            # sondern eine Selbstverstaendlichkeit - die Kachel bleibt weg,
            # bis es etwas zu vergleichen gibt. Steht dort eine Zahl groesser
            # null, ist sie IMMER eine Aussage und wird gezeigt.
            # Die Regel steht an EINER Stelle: `_auffaellig` rechnet sie,
            # hier wird sie gelesen. Zweimal gerechnet liefen Satz und Kachel
            # beim naechsten Umbau auseinander, ohne dass etwas rot wird.
            "ohne_vorlauf": auffaellig["ohne_vorlauf"],
            "preispunkte": historie.punkte_gesamt,
            "hersteller": len(hersteller_mit_daten),
            "schwelle_erreicht": erreicht,
        },
        "alarme": alarme,
        "segmente": sorted({p["segment"] for p in punkte_ohne_vertrag if p["segment"]}),
        "segment_label": SEGMENT_LABEL,
        "speicherstufen": sorted({p["speicher"] for p in punkte_ohne_vertrag
                                  if p["speicher"]}),
        "auffaellig": auffaellig,
        # Roh fuer den CSV-Gesamtexport (report/geraete_export.py). Er
        # entsteht in `render_site`, weil er in `site/` schreibt und diese
        # Funktion bewusst KEINEN Schreibzugriff hat.
        "alle_eintraege": sichtbar,
        "alle_punkte": punkte_alle,
        "katalog_obj": katalog,
        # G2: der Preisvergleich gegen die eigene Listung. Er bekommt die
        # LADEN-Abbildung mit, sonst zaehlte mobilcom-debitel neben freenet
        # als zweiter guenstigerer Anbieter - derselbe Shop, zweimal.
        "vergleich": vergleich,
        "lifecycle": lifecycle,
        "quellenlage": _quellenlage(quellen, db, sichtbar),
        "farbbericht": _farbbericht(sichtbar),
        "katalog": _katalogluecken(katalog),
    }
