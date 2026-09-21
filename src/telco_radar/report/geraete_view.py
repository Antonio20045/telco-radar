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
from itertools import zip_longest
from pathlib import Path
from typing import Optional

from ..geraete_model import ratenhinweis_aus_eintrag, serie_aus_modell
from . import (geraete_alarme, geraete_bereinigung, geraete_pruefung,
               geraete_tco_karten, geraete_tco_view, geraete_vergleich,
               geraete_verlauf, geraete_zeitreihe)
# MonatNamen der Katalog-Datumsformatierung - keine zweite Tabelle (driftet).
from .geraete_tco_band import _MONATE
from ..analyze import geraete_lifecycle
from ..analyze.tco_store import TcoDB
# Der Zeitraum der TCO-Spalte und DIE EINE Regel, ob zwei Leitzahlen
# gegeneinander gestellt werden duerfen (P0-B-h1) - der Katalog leitet
# beides nicht ab, er liest es.
from ..tco_model import TCO_HORIZONT, zeitraum_vergleichbar
from ..tarif_bezug import Tarifbestand
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

# Ab wann "neu im Regal" eine Marktbewegung meint und nicht die eigene
# Messdauer (30.08.2026).
#
# Die Karte meldete "59 Geraete neu im Regal" - bei 59 beobachteten Geraeten.
# Beides stimmte: die Preishistorie war 20 Tage alt, also war JEDES erfasste
# Geraet innerhalb des Fensters erstmals gesehen worden. Der Satz sagte
# damit nichts ueber den Markt, sondern ueber den Startzeitpunkt dieses
# Radars - und stand als Aussage ueber den Markt da.
#
# Unterhalb dieser Schwelle sagt die Karte deshalb EINEN Satz und zeigt
# keine Tabelle: die Zahl der erstmals erfassten Geraete gehoert in den
# Nebensatz, wo sie hingehoert, und die eine echte Preisaenderung steht
# ausgeschrieben daneben. Vier Wochen sind kein gerechneter Wert, sondern
# der Punkt, ab dem "seit der letzten Ausgabe" und "seit Messbeginn" nicht
# mehr dasselbe sind.
VORLAUF_TAGE = 28

# Wie viele Zeilen die zwei Lifecycle-Listen ohne Aufklappen zeigen
# (30.08.2026).
#
# GERECHNET, nicht gegriffen, und zwar an einer Fixture, die die Datenlage
# in etwa zwei Wochen vorwegnimmt: "Verweildauer im Regal" und
# "Preisverfall" stehen heute leer, weil die Historie zu duenn ist. Sobald
# sie sich einschalten, traegt jede Liste rund 51 px je Zeile - mit zwoelf
# bzw. ungedeckelt zusammen 1234 px, und der Portfolio-Reiter misst dann
# 3328 statt 2384 px. Die Grenze des Auftrags liegt bei 3000.
#
# Das ist dieselbe Fehlerklasse wie bei `KATALOG_SICHTBAR`: ein Deckel in
# ZEILEN ist immer nur ein Stellvertreter fuer eine Grenze in PIXELN, und
# eine Liste ohne Deckel haengt am Datenbestand. Sechs Zeilen kosten je
# Liste rund 310 px; der Rest steht zugeklappt darunter und ist nicht
# geloescht.
LIFECYCLE_SICHTBAR = 6

# Die Nachfolger-Tabelle bekommt ihren EIGENEN Deckel, nicht LIFECYCLE_SICHTBAR
# (B4/B4-Nachbesserung der Zurueckweisung vom 31.08.2026) - und er steht auf
# NULL. Das ist keine Verlegenheitsloesung, sondern das Ergebnis einer
# Messreihe, nicht einer Vermutung:
#
#   dauern+trends bei je 6 Zeilen (LIFECYCLE_SICHTBAR), Nachfolger LEER:
#                                                          2672-2759 px
#   + Nachfolger-Ueberschrift, Erklaersatz, Tabellenkopf (fester Aufschlag,
#     entsteht mit der ERSTEN Zeile ueberhaupt):                  ~188 px
#   + je Zeile (echtes Chromium, Playwright-Bounding-Box):          ~55 px
#
# Bei 328 px Rest bis zur 3000-px-Grenze reicht das fuer den Aufschlag
# allein - und schon EINE sichtbare Zeile reisst sie in der Kombination mit
# sechs vollen dauern/trends-Zeilen (gemessen: 2964-3050 px, abhaengig vom
# Gesamtbestand). `dauern` und `trends` sind eigene, laengst ausgelieferte
# Merkmale und werden hier NICHT enger gestellt, um dieser Tabelle Platz zu
# verschaffen - das waere eine Nebenwirkung auf ein fremdes Merkmal fuer
# einen Fall, der noch nicht eingetreten ist.
#
# Bei NULL sichtbaren Zeilen zeigt der Reiter deshalb GAR KEINE Tabelle
# oberhalb der Falz dieser Sektion - nur den Erklaersatz und darunter EINEN
# Aufklapper mit der vollstaendigen Tabelle (siehe Vorlage). Das ist
# dieselbe Regel wie bei jedem anderen Aufklapper dieser Seite: der Rest
# ist zugeklappt, nicht geloescht - hier ist der "Rest" nur ausnahmsweise
# alles.
NACHFOLGER_SICHTBAR = 0

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


def euro(betrag: float) -> str:
    """Ein Euro-Betrag in deutscher Schreibweise.

    Die Saetze der Wochenkarte schrieben ihre Preise bis zum 30.08.2026 mit
    `f"{wert:.2f} €"` - also "129.00 €" mit Dezimalpunkt, waehrend jede
    Tabelle derselben Seite "129,00 €" zeigt. Solange die Saetze neben einer
    Tabelle standen, ging das unter; seit die Karte unter kurzem Vorlauf NUR
    aus einem Satz besteht, ist es die erste Zahl, die jemand dort liest.

    Der Waechter `pruefe_zahlen` liest beide Schreibweisen ueber
    `lies_preis` - die Umstellung aendert nichts an dem, was er durchlaesst.
    """
    return f"{betrag:.2f}".replace(".", ",") + " €"


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


def _neu_seit(iso: str) -> str:
    """„17. September" - Tag und Monat fuer den Neu-Hinweis am Zeitreihen-
    Suchfeld (R3 der P5-Live-Pruefung). MonatNamen aus derselben Tabelle,
    die die Katalog-Zeile formatiert (`geraete_tco_band._MONATE` - eine
    zweite Kopie der zwolf Namen wuerde driften); ein unlesbares Datum
    steht roh im Satz statt geraten zu werden."""
    try:
        jahr, monat, tag = (int(x) for x in iso.split("-"))
        return f"{tag}. {_MONATE[monat - 1]}"
    except (AttributeError, ValueError, IndexError):
        return iso or ""


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


def _spaeterer_tag(erster: str, zweiter: str) -> str:
    """Der spaetere von zwei ISO-Tagen - oder "", wenn keiner lesbar ist.

    Ein unlesbarer Wert zaehlt nicht (Clean Code 4): er wird nie geraten
    und nie still durch den anderen ersetzt. Der lesbare gewinnt allein.
    """
    a, b = _tag(erster), _tag(zweiter)
    if a is None and b is None:
        return ""
    if a is None:
        return zweiter
    if b is None:
        return erster
    return zweiter if b > a else erster


# --------------------------------------------------------------------------
# Der Hinweis, wenn "Was der Nachfolger mit dem Preis macht" leer ist
# --------------------------------------------------------------------------
# P3 (31.08.2026, nach der Zurueckweisung Runde 1): die erste Fassung dieses
# Satzes behauptete zwei Dinge, die beide nicht stimmten - beide vom Lead
# selbst so in den Auftrag geschrieben, beide von einem adversarischen
# Pruefer nachgemessen widerlegt:
#
#   (1) "die Tabelle ist leer, weil kein Nachfolger ins Messfenster faellt".
#       Falsch: sie ist leer, weil `geraete_lifecycle._belastbar` VOR der
#       Nachfolger-Frage greift - 21 Tage Listungsdauer, und am 31.08.2026
#       erreicht KEINE der 370 Listungen mehr als 20. Ein einziger
#       Nachtlauf (last_verified +1) laesst 69 davon kippen; der Satz muss
#       also den echten Riegel nennen (die Beobachtungsdauer), nicht einen
#       erfundenen (die Terminlage der Nachfolger).
#   (2) "mehr Katalogpflege loest das nicht". Falsch: 13 der 59 beobachteten
#       Geraete haben einen Nachfolger im Katalog OHNE `marktstart`
#       (Pixel 10 -> Pixel 11 z.B.), waehrend nur 4 ein Datum tragen. Ein
#       fehlendes Datum ist ein Pflegeruecktand, kein Naturgesetz - die
#       Behauptung des Gegenteils war unbelegt und stand trotzdem als
#       Tatsachensatz auf der Seite (derselbe Fehler wie unten bei "waehrend
#       Vodafone ersetzt").
#
# Diese Fassung nennt deshalb ausschliesslich Groessen, die aus den Daten
# UND den oeffentlichen Konstanten von `geraete_lifecycle` kommen
# (`MIND_TAGE_JE_GERAET`, `listungsdauer()`) - nichts wird mehr geschaetzt
# oder behauptet. Auch die alte Zusatzzeile ("kam vor ueber eineinhalb
# Jahren auf den Markt") ist gestrichen: sie waehlte nur unter den VIER
# datierten Ketten und verschwieg damit die 13 undatierten, die dem Leser
# ein falsches Bild gaben ("der Katalog kennt nur alte Nachfolger" - er
# kennt vor allem gar keine Daten). `_zeitraum_grob()` faellt mit ihr weg;
# die Funktion rundete an vier von fuenf Stufengrenzen falsch auf (549 Tage
# waeren als "ueber zwei Jahren" gemeldet worden) und wurde von keinem Test
# aufgerufen - eine ungetestete Rundungsfunktion, die niemand mehr braucht.
#
# Und: KEINE Tatsachenbehauptung ueber das Verhalten von Vodafone oder dem
# Wettbewerb mehr. Vodafone fuehrt das iPhone 15 selbst 710 Tage nach dem
# Start des iPhone 16 - also laenger als jeder andere gemessene Fall. Die
# Sektion stellt die Frage, sie beantwortet sie nicht vorab.


def _nachfolger_leer_hinweis(eintraege: list, katalog,
                             nachfolger: list) -> str:
    """Warum "Was der Nachfolger mit dem Preis macht" heute leer ist - und
    wann sie es nicht mehr sein wird. Siehe Kommentar oben.

    Jede Zahl im Satz kommt aus einer oeffentlichen Konstante oder wird an
    Ort und Stelle aus *eintraege*/*katalog* gezaehlt - keine geschaetzte
    Staffelung, kein Kalenderdatum.
    """
    if nachfolger:
        return ""

    grenze = geraete_lifecycle.MIND_TAGE_JE_GERAET
    dauern_alle = [geraete_lifecycle.listungsdauer(e) for e in eintraege]
    dauern_alle = [d for d in dauern_alle if d is not None]
    laengste = max(dauern_alle) if dauern_alle else 0

    # B7 der Zurueckweisung: "seit dem 10.08.2026" stand hier UND im
    # "duenn"-Hinweis direkt darueber, wortgleich. `laengste` faellt heute
    # (20 Tage) zufaellig mit der dortigen Beobachtungsspanne zusammen - eine
    # zweite Formulierung derselben Zahl waere derselbe Fehler in neuer
    # Verkleidung. Berichtet wird deshalb der ABSTAND zur Schwelle, eine Zahl,
    # die an KEINER anderen Stelle der Seite steht.
    abstand = grenze - laengste
    if abstand > 0:
        dauer_satz = (f"Der Abstand zur nötigen Beobachtungsdauer beträgt "
                      f"heute noch {abstand} {'Tag' if abstand == 1 else 'Tage'}.")
    else:
        dauer_satz = ("Die nötige Beobachtungsdauer ist für mindestens eine "
                      "Listung bereits erreicht.")

    # Geraete mit einem Nachfolger im Katalog, dem das Marktstart-Datum
    # fehlt - der Beleg gegen "mehr Katalogpflege loest das nicht" (siehe
    # Kommentar oben). Gezaehlt wird je GERAET, nicht je Listung: ein
    # Katalogeintrag fehlt einmal, unabhaengig davon, bei wie vielen
    # Anbietern er beobachtet wird.
    geraete_ids = sorted({e.get("device_id") for e in eintraege
                          if e.get("device_id")})
    ohne_datum = 0
    for gid in geraete_ids:
        nf = katalog.nachfolger_von(gid)
        if nf is not None and not (nf.marktstart or "").strip():
            ohne_datum += 1

    zusatz = ""
    if ohne_datum:
        zusatz = (
            f" Bei {ohne_datum} {'Gerät fehlt' if ohne_datum == 1 else 'Geräten fehlt'} "
            f"dafür zusätzlich das Marktstart-Datum ihres Nachfolgers im "
            f"Katalog.")

    return (
        "Diese Tabelle soll zeigen, wie lange ein Vorjahresmodell nach dem "
        "Start seines Nachfolgers im Regal bleibt – bei uns wie beim "
        "Wettbewerb. Eine Zeile entsteht erst, wenn eine Listung "
        f"mindestens {grenze} Tage lang beobachtet wurde und ihr Nachfolger "
        f"im Katalog ein Marktstart-Datum trägt. {dauer_satz}"
        f"{zusatz} Sobald beides zusammenkommt, entsteht die erste Zeile."
    )


def _mit_beobachtungsbeleg(nachfolger: list) -> list:
    """Ergaenzt jede Nachfolger-Zeile um `beobachtet_tage`: wie viele Tage
    der gemeldeten Verweildauer WIRKLICH gemessen sind, statt aus dem
    Katalogdatum des Nachfolgers zurueckgerechnet (B2 der Zurueckweisung
    vom 31.08.2026).

    `verweildauer_tage` misst vom MARKTSTART DES NACHFOLGERS bis zur
    letzten Bestaetigung - bei allen heutigen Kandidaten faengt die eigene
    Beobachtung aber erst Jahre nach diesem Marktstart an
    (`verweildauer_untergrenze=True`). Ein Etikett "mind." beschreibt das
    als Untergrenze und suggeriert damit "die Wahrheit ist noch groesser" -
    das Gegenteil dessen, was zaehlt: der weitaus groesste Teil der Zahl ist
    gar nicht gemessen, sondern aus dem Katalogdatum angenommen. Die Seite
    zeigt deshalb zusaetzlich, wie viele Tage zwischen dem Beobachtungsbeginn
    (`beobachtet_seit`) und der letzten Bestaetigung (`zuletzt_bestaetigt`)
    wirklich liegen - beide Felder kommen aus demselben Parallelpaket und
    werden per `.get(...)` gelesen, eine fehlende Angabe ergibt `None` und
    die Vorlage zeigt dann nur die Gesamtzahl.
    """
    ergebnis = []
    for n in nachfolger:
        beginn = _tag(n.get("beobachtet_seit"))
        ende = _tag(n.get("zuletzt_bestaetigt"))
        beleg = ((ende - beginn).days
                 if beginn is not None and ende is not None and ende >= beginn
                 else None)
        ergebnis.append({**n, "beobachtet_tage": beleg})
    return ergebnis


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

    # WIE LANGE MESSEN WIR SCHON? Der Vorlauf entscheidet, ob "neu im Regal"
    # eine Marktbewegung meint oder nur den Startzeitpunkt dieses Radars.
    # Gerechnet gegen die aelteste Messung, nicht gegen `first_seen`: ein
    # Geraet, das erst gestern in den Katalog kam, verkuerzt den Vorlauf der
    # ganzen Sektion nicht.
    seit = juengste[0] if juengste else None
    bezug_tag = _tag(heute)
    vorlauf_tage = ((bezug_tag - seit).days
                    if seit and bezug_tag and bezug_tag >= seit else 0)
    kurzer_vorlauf = vorlauf_tage < VORLAUF_TAGE

    # DREI LAGEN, NICHT ZWEI - und die erste ist nicht die zweite.
    #
    #   `ohne_vorlauf`  : es gibt ueberhaupt keinen frueheren Stand (erster
    #                     oder zweiter Lauf). Dann ist "neu im Regal" nicht
    #                     nur schief, es ist unbelegbar, und die Karte sagt
    #                     genau das.
    #   `kurzer_vorlauf`: es gibt einen Vergleichsstand, aber er reicht nur
    #                     ueber wenige Tage. "59 Geraete neu im Regal" bei 59
    #                     beobachteten ist dann eine Aussage ueber die
    #                     Messdauer und keine ueber den Markt.
    #   sonst           : der Normalfall, mit Tabelle.
    #
    # Die erste Fassung dieser Aenderung hatte die zwei ersten Lagen
    # zusammengeworfen - und damit den Satz "es gibt noch keinen frueheren
    # Stand, gegen den sich vergleichen liesse" abgeschafft, den B7 Punkt 3
    # ausdruecklich verlangt. Ein bestehender Test hat das gemeldet.
    saetze = []
    if ohne_vorlauf:
        for b in bewegungen[:5]:
            richtung = "günstiger" if b["delta"] < 0 else "teurer"
            saetze.append(f"{b['modell']} bei {b['anbieter']}: "
                          f"{euro(abs(b['delta']))} {richtung} "
                          f"({euro(b['von'])} auf {euro(b['auf'])}).")
        if neu_geraete:
            saetze.append(f"{len(neu_geraete)} Gerät"
                          f"{'e' if len(neu_geraete) != 1 else ''} erstmals "
                          f"erfasst – es gibt noch keinen früheren Stand, gegen "
                          f"den sich vergleichen ließe.")
    elif kurzer_vorlauf and (neu_geraete or bewegungen or weg_geraete):
        # EIN SATZ STATT EINER TABELLE.
        #
        # Die Bedingung `neu_geraete or bewegungen` ist nicht kosmetisch:
        # ohne sie stuende in einer ruhigen Woche "Seit dem 10.08. wurden 0
        # Geraete erstmals erfasst; eine Preisaenderung ist dabei nicht
        # aufgefallen." - ein Satz, der nichts sagt, und die Rubrik "Was
        # diese Woche auffaellt" haette damit IMMER Inhalt. Vorher
        # verschwand sie in diesem Fall ganz (`hat_daten` blieb falsch), und
        # das ist die richtige Antwort: keine Zeile, die nichts sagt. Unter vier Wochen Vorlauf ist die
        # Zahl der erstmals erfassten Geraete eine Aussage ueber uns und
        # nicht ueber den Markt - sie steht deshalb im Nebensatz, und die
        # Preisaenderungen, die es wirklich gab, stehen ausgeschrieben
        # daneben statt als Tabelle mit Kopfzeile und einer Datenzeile.
        # Numerus: "wurden 1 Gerät erstmals erfasst" ist falsch, und der
        # Fall tritt in einer ruhigen Woche als erster ein.
        wieviel = len(neu_geraete)
        # "4.8.", nicht "4.08." - dieselbe Schreibweise wie `tagDE` in
        # app.js und wie die Chronik der Wettbewerbsseite ("7.8.").
        kopf = (f"Seit dem {seit.day}.{seit.month}. " if seit else "Bisher ")
        satz = (f"{kopf}{'wurde' if wieviel == 1 else 'wurden'} {wieviel} "
                f"Gerät{'' if wieviel == 1 else 'e'} erstmals erfasst; ")
        if not bewegungen:
            satz += "eine Preisänderung ist dabei nicht aufgefallen."
        else:
            teile = [f"{b['modell']} bei {b['anbieter']}, "
                     f"{euro(b['von'])} → {euro(b['auf'])}"
                     for b in bewegungen[:3]]
            wieviele = ("eine Preisänderung ist aufgefallen"
                        if len(bewegungen) == 1
                        else f"{len(bewegungen)} Preisänderungen sind "
                             f"aufgefallen")
            satz += wieviele + ": " + "; ".join(teile)
            if len(bewegungen) > 3:
                # DIE RESTZAHL MUSS ANGEMELDET SEIN. Sie ist gerechnet
                # (`len - 3`) und stand nicht in `erlaubt`; der Waechter
                # verwarf den Satz fail closed, und weil dieser Zweig KEINE
                # Tabelle mehr zeigt, blieb die Rubrik danach vollstaendig
                # leer - Ueberschrift ohne Inhalt. Ausgeloest ab der vierten
                # Preisbewegung einer Nacht, sobald kein Eigenname die Zahl
                # zufaellig deckt.
                erlaubt.add(len(bewegungen) - 3)
                satz += f" und {len(bewegungen) - 3} weitere"
            satz += "."
        saetze.append(satz)
        # EINE AUSLISTUNG IST DAS STAERKSTE SIGNAL DIESER SEITE und darf
        # nicht daran haengen, wie lange wir schon messen. Der erste Anlauf
        # dieses Zweiges kannte nur `neu_geraete` und `bewegungen`: zehn aus
        # dem Regal gefallene Geraete standen nirgends, waehrend der Satz
        # daneben "eine Preisaenderung ist dabei nicht aufgefallen" meldete.
        # Genau der Einbruch, den der Kommentar bei `ohne_vorlauf` als Grund
        # fuer die Laufbilanz nennt.
        if weg_geraete:
            saetze.append(
                f"{len(weg_geraete)} "
                f"Gerät{'' if len(weg_geraete) == 1 else 'e'} "
                f"{'ist' if len(weg_geraete) == 1 else 'sind'} aus dem "
                f"Portfolio gefallen.")
    else:
        for b in bewegungen[:5]:
            richtung = "günstiger" if b["delta"] < 0 else "teurer"
            saetze.append(f"{b['modell']} bei {b['anbieter']}: "
                          f"{euro(abs(b['delta']))} {richtung} "
                          f"({euro(b['von'])} auf {euro(b['auf'])}).")
        if neu_geraete:
            saetze.append(f"{len(neu_geraete)} Gerät{'e' if len(neu_geraete) != 1 else ''} "
                          f"neu im Regal.")
        if weg_geraete:
            saetze.append(f"{len(weg_geraete)} Gerät{'e' if len(weg_geraete) != 1 else ''} "
                          f"aus dem Portfolio gefallen.")

    # Das Datum im Kopfsatz ist so wenig eine Behauptung ueber den Markt wie
    # ein Eigenname - aber der Waechter prueft JEDE Zahl, und ohne diese
    # Anmeldung verwuerfe er den einen Satz, den die Karte dann noch hat.
    # Dieselbe Mechanik wie `zahlen_der_namen`, und aus demselben Grund
    # ausdruecklich statt stillschweigend.
    if kurzer_vorlauf and not ohne_vorlauf and seit:
        erlaubt |= zahlen_im_text(f"{seit.day}.{seit.month}.")

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
        # UNTER VIER WOCHEN VORLAUF KEINE TABELLE. Sie trug am 30.08.2026
        # eine Kopfzeile mit sieben Spalten und GENAU EINE Datenzeile - der
        # Satz darueber sagt dasselbe in einer Zeile und ohne, dass jemand
        # sieben Spaltenkoepfe liest, um eine Zahl zu finden. Die Bewegungen
        # sind nicht verloren: sie stehen ausgeschrieben im Satz.
        "bewegungen": [] if kurzer_vorlauf else bewegungen[:12],
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
        # AN DAS, WAS WIRKLICH AUF DIE SEITE KOMMT. `bewegungen` ist die
        # lokale, ungefilterte Liste; im kurzen Vorlauf wird sie oben auf
        # [] gesetzt, und `geprueft` kann der Zahlenwaechter leeren. Beides
        # zusammen ergab eine Rubrik, die rendert und nichts enthaelt.
        "hat_daten": bool(geprueft or (bewegungen and not kurzer_vorlauf)),
        "ohne_vorlauf": ohne_vorlauf,
        "kurzer_vorlauf": kurzer_vorlauf,
        "vorlauf_tage": vorlauf_tage,
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
# Seit P3 zaehlt der Deckel MODELLZEILEN - `BLOCK_SICHTBAR` (zwei Zeilen je
# Geraete-Block, P1 31.08.2026) ist mit der Listungs-Tabelle entfallen: ein
# Modell IST jetzt eine Zeile, seine Farb- und Anbieter-Varianten stehen im
# Zeilen-Aufklapper, und dort gibt es keinen sichtbaren Platz zu verteilen.
KATALOG_SICHTBAR = 12


def _katalog_betrag(z: dict):
    """Der GEZEIGTE Betrag einer Zeile, fuer Sortierung und Tiebreaks.

    Nicht `preis` allein: die Spalte zeigt bei einer Zeile ohne Barpreis die
    Zuzahlung. Mit `float("inf")` fuer fehlende Preise landete eine
    1-Euro-Zuzahlung hinter einem 1199-Euro-Barpreis - heute folgenlos (alle
    Zeilen tragen einen Barpreis), aber der naechste Buendelpreis-Adapter
    loest es aus.
    """
    for feld in ("preis", "zuzahlung"):
        if z[feld] is not None:
            return z[feld]
    return float("inf")


# Segmentrang fuer den Vergleich UEBER Baureihen hinweg (B1-Nachbesserung,
# 31.08.2026). `generation` ist NUR innerhalb einer Baureihe eine Zahl
# (Galaxy A57 traegt 57, Galaxy S26 traegt 26) - eine erste Fassung
# sortierte trotzdem flach nach `-generation` ueber den ganzen Hersteller,
# und reproduzierte damit exakt den Fehler vom 29.08.2026, den der Auftrag
# wortwoertlich als Warnung nennt: Samsungs erste Bildschirmseite fuehrte
# mit einer Galaxy A57, das Flaggschiff S26 stand auf Platz fuenf.
#
# `segment` ist das Feld, das der Katalog PFLEGT und das ueber Baureihen
# hinweg VERGLEICHBAR ist (flagship/premium/mid/entry) - anders als die
# Generation ist es keine Zahl, die an ihrer Baureihe haengt. Es fuehrt die
# Blockreihenfolge; die Generation zaehlt erst DANACH, und dann nur noch
# INNERHALB derselben Baureihe (siehe `_katalog_block_schluessel`).
_SEGMENT_RANG = {"flagship": 0, "premium": 1, "mid": 2, "entry": 3}


def _katalog_segment_rang(segment: str) -> int:
    return _SEGMENT_RANG.get((segment or "").strip().lower(), 4)


def _katalog_zeile_schluessel(z: dict):
    """Sortierschluessel INNERHALB eines Geraete-Blocks (B6/B8-Nachbesserung,
    31.08.2026): "neu" zuerst, dann der guenstigste Betrag, dann Anbieter
    und Farbe als volldeterministische Tiebreaks. Ohne Farbe blieb die
    Reihenfolge unterbestimmt - 18 von 30 Mischungen derselben Eingabe
    lieferten eine andere Zeilenfolge (B8), weil Pythons `sorted()` bei
    gleichem Schluessel die EINGABEreihenfolge beibehaelt und die haengt in
    Produktion an der Satzfolge in `geraete_db.json`.
    """
    return (0 if z["zustand"] == "neu" else 1, _katalog_betrag(z),
            z["anbieter"] or "", z["farbe"] or "")


def _katalog_block_schluessel(block: dict):
    """Sortierschluessel FUER die Geraete-Bloecke eines Herstellers.

    Segment zuerst (siehe Modulkopf oben), dann die Baureihe alphabetisch -
    NICHT die Generation, denn "Z Fold8" gegen "S26 Ultra" waere derselbe
    Kategorienfehler eine Ebene hoeher: zwei verschiedene Baureihen sind
    ueber ihre Generationszahl so wenig vergleichbar wie A- und S-Reihe.
    Erst INNERHALB derselben Baureihe zaehlt die Generation absteigend -
    dort ist sie eine echte Zahl (Galaxy S26 vor Galaxy S25).
    """
    gen = block["generation"]
    return (_katalog_segment_rang(block["segment"]), block["serie"] or "",
            0 if gen is not None else 1, -(gen or 0), block["modell"] or "",
            block["speicher"] or 0)


def _katalog_zeile(e: dict, katalog) -> dict:
    """EINE Listungs-Zeile des Katalogs - die Bauform, die Reiter 2 seit dem
    30.08.2026 zeigt, als eigene Funktion seit P3 (17.09.2026).

    Die Modell-Ebene (`katalog_modellzeilen`) braucht dieselben Zeilen fuer
    ihren Aufklapper, aber OHNE Interleave und Zeilendeckel - beides ist
    eine Entscheidung ueber die ANZEIGE der Liste und darf nicht an der
    Zeile haengen, die der Aufklapper eines Modells wieder neu ordnet. Zwei
    Kopien dieser Bauform waeren die Luecke, in der der Aufklapper eines
    Tages eine andere Zustands-Ableitung zeigt als die Zeile davor.
    """
    g = katalog.nach_id(e.get("device_id")) if katalog else None
    preis = e.get("preis_ohne_vertrag")
    # Der Zustand wird ABGELEITET, nicht aus dem Store uebernommen.
    # Sonst steht in dieser Tabelle "space schwarz erneuert - Zustand
    # neu", waehrend der Pruefbericht zwei Reiter weiter "refurbished"
    # sagt: die Seite widerspraeche sich selbst, und der Store ist die
    # schwaechere Quelle - er traegt seinen alten Wert bis zum naechsten
    # erfolgreichen Crawl.
    #
    # Gerufen wird die EINE Ableitung (`geraete_bereinigung`), nicht eine
    # eigene Fassung davon. Auf dem Bestand ist sie ohnehin schon
    # gelaufen und hat ihr Ergebnis in die Kopie geschrieben - das ist
    # der Grund, warum diese Zeile auch bei einer Farbe funktioniert,
    # aus der das Kennzeichen gerade entfernt wurde.
    zustand = geraete_bereinigung.zustand_der_zeile(e)
    return {
        "modell": g.modell if g else (e.get("device_id") or "?"),
        "hersteller": g.hersteller if g else "",
        # Nur fuer die Standardsortierung (Block/Baureihe/Segment) -
        # keine eigene Spalte.
        "generation": g.generation if g else None,
        "serie": serie_aus_modell(g.modell) if g else "",
        "segment": g.segment if g else "",
        "speicher": e.get("speicher_gb"),
        "farbe": e.get("farbe_normalisiert") or e.get("farbe_roh") or "",
        "anbieter": e.get("anbieter"),
        "anbieter_typ": e.get("anbieter_typ") or "",
        "netz": e.get("netz") or "",
        "zustand": zustand,
        "preis": preis,
        "ratenhinweis": ratenhinweis_aus_eintrag(e),
        "zuzahlung": e.get("zuzahlung"),
        "tarif": e.get("tarif_referenz") or "",
        "verfuegbarkeit": e.get("verfuegbarkeit") or "unbekannt",
        "url": e.get("quelle_url") or "",
        "abgerufen_am": e.get("abgerufen_am") or "",
        "sku_id": e.get("sku_id") or "",
    }


# --------------------------------------------------------------------------
# P3 (Strategie Geraete v3, 17.09.2026): der Katalog auf MODELL-Ebene.
#
# `katalogzeilen()` - die flache LISTUNGS-Tabelle mit Bloecken, Interleave
# je Anbieter im Block und `BLOCK_SICHTBAR` - ist mit P3/C3 (18.09.2026)
# ersatzlos entfallen: der Reiter rendert `katalog_modellzeilen()`, und die
# Listungs-Zeilen leben im Aufklapper JE MODELL (Bauform `_katalog_zeile`,
# dort nach `_katalog_zeile_schluessel` sortiert). Die Sortier-Regeln, die
# die alte Ebene trugen (B1/B5/B6/B9 der Zurueckweisung vom 31.08.2026),
# stehen seit C1 in den Docstrings von `katalog_modellzeilen()` und
# `_interleave_modelle_je_hersteller()` - eine Ebene hoeher, dort wo sie
# heute gerechnet werden. Zweite Rechnung fuer dieselbe Tabelle waere
# zwoelf Zeilen toter Kontext pro Rendern (E5-Regel).
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# P3 (Strategie Geraete v3, 17.09.2026): der Katalog auf MODELL-Ebene
# --------------------------------------------------------------------------

# Die beiden benannten Leerzustaende der TCO-Spalte. sichtbarer Text traegt
# Umlaute - nicht die ASCII-Umschrift der Kommentare (dieselbe Lehre wie
# bei der Uebersetzungsseite).
TCO_LEER_KEIN_BUNDEL = "kein Bündel gemessen"
TCO_LEER_KEIN_VERGLEICHBARES = "kein vergleichbares Bündel gemessen"
# A3 (STRATEGIE GERAETE V4, 20.09.2026): der dritte Zustand - Bündel gibt
# es, aber keines mit aktuellem Abruf. „kein Bündel gemessen“ waere hier
# gelogen (harte Regel 9), und der alte Preis darf nicht als heutiger
# stehen.
TCO_LEER_NUR_ALT = "kein aktueller Bündel-Stand"
# P0-B-h2: der vierte Zustand - Bündel gibt es, aktuell und vergleichbar,
# aber KEINES ueber den Zeitraum dieser Spalte. Gemessen am Bestand vom
# 21.09.2026: acht Modelle (z. B. Apple iPhone 15 256 GB, Nothing Phone
# (4a) Pro 128 GB) haben nur ein 1&1-Buendel, dessen Leitzahl 36 Monate
# traegt. Bis hierher stand deren 36-Monats-Summe unter dem Kopf "Kosten
# über 24 Monate" und sortierte gegen echte 24-Monats-Zahlen; sie ist
# richtig gerechnet, aber sie ist keine Zahl dieser Spalte.
TCO_LEER_ANDERE_LAUFZEIT = f"kein Bündel über {TCO_HORIZONT} Monate"

# Die benannten Leerzustaende der DELTA-Zelle (A2-Nachbesserung,
# Pruef-Befund 20.09.2026). Zwei verschiedene Stummen, zwei Etiketten:
# fehlt VODAFONE, fehlt die Referenz; fehlt nur der WETTBEWERBER neben
# einem eigenen Angebot, liegt die Luecke beim Wettbewerb - die Referenz
# ist dann das eigene Angebot selbst (derselbe Fehlertyp wie die beiden
# TCO-Leerzustaende: eine Ursache, ein Name).
TCO_DELTA_LEER_KEINE_REFERENZ = "keine Referenz"
TCO_DELTA_GRUND_KEINE_REFERENZ = (
    "Vodafone listet dieses Modell nicht - deshalb ist kein Abstand "
    "berechenbar (die Referenz fehlt)")
TCO_DELTA_LEER_KEIN_WETTBEWERBER = "kein Wettbewerber-Angebot"
TCO_DELTA_GRUND_KEIN_WETTBEWERBER = (
    "Vodafone listet dieses Modell, aber kein Wettbewerber-Angebot ist "
    "vergleichbar erhoben - deshalb ist kein Abstand berechenbar")
# P0-B-h2: der dritte Stumme dieser Zelle war der STRICH - und der heisst
# auf dieser Seite "kein Angebot" (A2). Ein Wettbewerber-Angebot, dessen
# Leitzahl einen anderen Zeitraum traegt als die Referenz, ist kein
# fehlendes Angebot: es ist gemessen und unvergleichbar. Die Buendelzeile
# sagt dazu seit P0-B-fix2 "andere Laufzeit" samt Satz
# (`geraete_tco_karten.delta_zustand`) - DIESE Zelle sagt jetzt dasselbe,
# aus derselben Definition (Clean Code 7), statt zu schweigen. Das WORT
# steht deshalb nicht hier, sondern in `DELTA_ANDERE_LAUFZEIT` dort.
# Gemessen am Bestand vom 21.09.2026: 25 stumme Zellen, davon 23 mit
# genau diesem Zustand (z. B. Apple iPhone 17 Pro Max 512 GB, dessen
# Zelle bis P0-B-fix2 "+341,74 € · +14,5 %" behauptete).
# Der Rueckfalltext unten gilt nur, wo die Karte ihren Satz nicht
# mitbringt - stumm bleibt die Zelle nie (harte Regel 9).
TCO_DELTA_GRUND_ANDERE_LAUFZEIT = (
    "Das günstigste Wettbewerber-Angebot trägt einen anderen Zeitraum als "
    "die Vodafone-Referenz - über zwei Laufzeiten gibt es keinen Abstand")
# Der vierte Stumme, beim Messen von P0-B-h2 gefunden: die Referenz
# EXISTIERT, ist aber nicht aktuell erhoben - `geraete_tco_karten.modelle`
# gibt sie dann keiner Karte als Massstab (S2-1), und keine Karte des
# Modells traegt ein Delta. Gemessen am 21.09.2026: Google Pixel 11 Pro
# Fold 256 GB (o2 2.380,75 EUR, Vodafone-Naeherung aus altem Barpreis).
# "kein Wettbewerber-Angebot" waere dort falsch (o2 und 1&1 stehen da),
# "keine Referenz" auch. Dieselbe Sprache wie `TCO_LEER_NUR_ALT`: die
# Luecke liegt beim STAND, nicht beim Bestand.
TCO_DELTA_LEER_ALTE_REFERENZ = "kein aktueller Referenz-Stand"
TCO_DELTA_GRUND_ALTE_REFERENZ = (
    "Die Vodafone-Referenz ist nicht aktuell erhoben - ein Abstand gegen "
    "sie wäre kein Abstand von heute")
# Die zweite Wand (S3c): ein Traeger MIT dem Zeitraum der Spalte, dem
# trotzdem kein Abstand anhaengt. Nach dem Filter unten kann das nicht
# mehr vorkommen - und WENN doch, steht der Zustand als Wort in der Zelle
# und nicht als Strich.
TCO_DELTA_LEER_UNBESTIMMT = "Abstand unbestimmt"
TCO_DELTA_GRUND_UNBESTIMMT = (
    "Zu diesem Wettbewerber-Angebot ist kein Abstand zur Vodafone-Referenz "
    "gerechnet")


def _buendel_je_anbieter_modell(buendel: list, eintraege: list, katalog
                                ) -> tuple[dict, dict]:
    """Zwei Lesarten derselben Bündel-Aufloesung.

    1. `(Anbieter, modell_schluessel) -> das guenstigste Bündel mit
       Monatspreis` - die Monatsangabe "nur im Bündel, ab X EUR/Monat"
       braucht einen Beleg aus `geraete_tco.json`, NICHT das
       `preis_mit_vertrag_ab` der Listung, denn der Bündelstore traegt dazu
       Quelle und Abrufdatum (Belegzwang).
    2. `modell_schluessel -> {device_id, speicher}` für JEDES Bündel, dessen
       SKU auf ein Geraet aufloest - unabhaengig vom Monatspreis (P5-Auftrag
       1, 18.09.2026: Sichtbarkeit folgt den Daten, nicht dem Weg - schon
       EIN Bündel ohne Listung stellt die Katalog-Zeile, auch wenn aus ihm
       noch keine Monatsangabe lesbar ist).

    Die Aufloesung einer Bündel-SKU auf das Modell laeuft ueber den WEG von
    `geraete_tco_karten.modelle()`: erst die Listung derselben SKU, dann der
    Katalog (`geraet_aus_sku`) - eine zweite, eigene Aufloesung wuesste
    bald etwas anderes als die TCO-Tafel ueber dasselbe Bündel.

    Der Monatsbetrag ist die Angabe des ANBIETERS, nie eine Rechnung dieses
    Projekts: `buendel_monatlich` (so verkauft 1&1, § 13.2) und nur wenn der
    fehlt, die Summe aus Tarif- und Geraeterate - zwei Felder, die der
    Anbieter selbst nebeneinander nennt.
    """
    modell_je_sku: dict[str, str] = {}
    geraet_je_sku: dict[str, tuple] = {}
    for e in eintraege:
        sku = e.get("sku_id") or ""
        if sku:
            modell_je_sku[sku] = geraete_tco_karten.modell_schluessel(
                e.get("device_id"), e.get("speicher_gb"))
            geraet_je_sku[sku] = (e.get("device_id") or "",
                                  e.get("speicher_gb"))
    beste: dict = {}
    geraet_je_mid: dict[str, dict] = {}
    for b in buendel or []:
        sku = b.get("sku_id") or ""
        mid = modell_je_sku.get(sku)
        if mid:
            geraet = geraet_je_sku.get(sku, ("", None))
        else:
            geraet = geraete_tco_karten.geraet_aus_sku(sku, katalog)
            if not geraet[0]:
                continue
            mid = geraete_tco_karten.modell_schluessel(*geraet)
        # JEDES aufloesbare Bündel traegt sein Geraet bei - auch eines, dessen
        # SKU eine Listung hat: `hat_buendel` der Katalog-Zeile haengt an
        # dieser Menge (iPhone 18 am 17.09.: 58 Listungen UND 105 Bündel
        # auf denselben SKUs, unter der Auto-Messtag-Schwelle der Wahl).
        geraet_je_mid.setdefault(mid, {"device_id": geraet[0],
                                       "speicher": geraet[1]})
        monat = b.get("buendel_monatlich")
        if monat is None:
            tarif, rate = b.get("tarif_monatlich"), b.get("geraet_monatsrate")
            if tarif is None or rate is None:
                continue
            monat = round(float(tarif) + float(rate), 2)
        monat = float(monat)
        schluessel = (geraete_tco_karten.normalisiere(b.get("anbieter", "")),
                      mid)
        bisher = beste.get(schluessel)
        if bisher is None or monat < bisher["monat"]:
            beste[schluessel] = {
                "monat": monat,
                "anbieter": b.get("anbieter", ""),
                "tarif": (b.get("tarif_name") or "").strip(),
                "quelle_url": b.get("quelle_url", ""),
                "abgerufen_am": b.get("abgerufen_am", ""),
            }
    return beste, geraet_je_mid


def _buendel_aus_listungen(eintraege: list) -> list[dict]:
    """Buendel-Saetze im Store-Format, gelesen aus den LISTUNGEN.

    Nur fuer den Fall, dass `geraete_tco.json` UNLESBAR ist (abgebrochener
    Schreibvorgang des Nachtlaufs): `TcoDB.buendel()` liefert dann still
    `[]`, und der Katalog fiele auf "ohne Preis" zurueck - DIE P3-REGEL
    gilt aber auch im Fehlerfall (S2-1 der P3-Code-Pruefung, 18.09.2026;
    Fehlerklasse B6: eine kaputte Datei sieht aus wie eine leere
    Datenlage). Die 1&1-Zeilen tragen ihren Buendel-Monatspreis selbst
    (`preis_mit_vertrag_ab`, so verkauft 1&1, § 13.2) samt Tarif und
    Beleg - genau die Felder, die der Store auch haette.

    Die Saetze sehen aus wie Store-Saetze, damit
    `_buendel_je_anbieter_modell` sie nicht unterscheiden muss. Gelesen
    wird nur, was der Anbieter selbst nennt - nichts gerechnet, keine
    Aufteilung erfunden.
    """
    saetze = []
    for e in eintraege:
        monat = e.get("preis_mit_vertrag_ab")
        if monat is None:
            continue
        saetze.append({
            "sku_id": e.get("sku_id") or "",
            "anbieter": e.get("anbieter") or "",
            "buendel_monatlich": monat,
            "tarif_name": (e.get("tarif_referenz") or "").strip(),
            "quelle_url": e.get("quelle_url") or "",
            "abgerufen_am": e.get("abgerufen_am") or "",
        })
    return saetze


def _tco_spalte(modell_tco: dict | None, heute: str = "") -> dict:
    """Die TCO-Felder EINER Modellzeile aus der TCO-Aufbereitung.

    `modell_tco` ist ein Eintrag aus `geraete_tco_view.aufbereiten()
    ["modelle"]` - dessen Karten tragen `delta_kurz` und `band` schon
    fertig (beide werden dort NACH `modelle()` gesetzt). Hier wird nichts
    gerechnet, nur das beste vergleichbare Angebot gewaehlt: DIE EINE REGEL
    von P3 - zwei Rechnungen fuer dieselbe Zahl sind zwei Zahlen. Das
    "beste" Angebot ist die guenstigste belastbare, vergleichbare Karte
    ohne Naeherung; `delta_kurz` existiert nur mit Vodafone-Referenz und
    wird unverändert durchgereicht.

    A2-Nachbesserung (Pruef-Befund 20.09.2026, schwer: hoch): die Leitzahl
    und der Abstand haben SEITDEM ZWEI TRAEGER. Gewann das EIGENE Buendel
    das Minimum (20 von 48 "keine Referenz"-Zeilen des Bestands, z. B.
    Galaxy A57 256: Vodafone 1.199,80 vor 1&1 1.207,54), lieferte `_delta`
    fuer die eigene Karte None (B4) - und die Delta-Zelle behauptete die
    fehlende Referenz, obwohl die TCO-Zelle derselben Zeile "bei Vodafone"
    sagte. Jetzt stellt das eigene Angebot weiterhin die Leitzahl; der
    Abstand gehoert dem guenstigsten FREMDEN Angebot (der Wert, den die
    Wr-Zeile desselben Modells schon zeigt). Ist kein fremdes Angebot
    vergleichbar, heisst die Luecke "kein Wettbewerber-Angebot" - nicht
    "keine Referenz", denn die Referenz ist das eigene Angebot selbst.

    P0-B-h2: DIE SPALTE HAT EINEN ZEITRAUM, und nur Zahlen dieses
    Zeitraums stehen darin (`TCO_HORIZONT`, derselbe Wert, den ihr Kopf
    nennt und den die Vodafone-Referenz traegt). Seit P0-B-fix2/h1 nennt
    jede Karte den Zeitraum, den ihre Leitzahl wirklich traegt
    (`leitzahl_monate`) - damit ist die Vorbedingung eingetreten, die im
    Kommentar unten stand ("Wird `laufzeit` je wieder variabel, MUSS an
    dieser Stelle auf 24 gefiltert werden"). Ohne den Filter stellten 16
    Modellzeilen eine 36-Monats-Summe unter den 24-Monats-Kopf, mit einem
    Ø/Monat und einem Sortierschluessel gegen echte 24-Monats-Zahlen; und
    schon die Wahl des Minimums verglich zwei Zeitraeume. Die anderen
    Zahlen verschwinden nicht, sie werden BENANNT: die Zeile sagt "kein
    Bündel über 24 Monate", die Δ-Zelle "andere Laufzeit" - dieselben
    Worte wie die Buendelzeile derselben Karte, und das ganze Buendel
    steht mit eigenem Etikett in der Vergleichsansicht.
    """
    leer_delta = {"tco_delta": None, "tco_delta_prozent": None,
                  "tco_delta_kurz": None, "tco_delta_anbieter": None,
                  "tco_delta_leer": None, "tco_delta_leer_grund": None}
    if not modell_tco:
        return {"tco_ab": None, "tco_anbieter": None, "tco_monat": None,
                "tco_band": None, "tco_beleg": None,
                "tco_leer": TCO_LEER_KEIN_BUNDEL, **leer_delta}
    # A3: NUR FRISCHE Karten stellen die Spalte (`frisch`, dieselbe
    # Definition wie die Tafel - Clean Code 7). Der Pool OHNE die
    # Frische entscheidet danach, ob die Lücke "kein vergleichbares
    # Bündel" oder "kein aktueller Stand" heißt. EINE Filterreihe, aus
    # der die andere ABGELEITET ist (S3e, Diff-Prüfung 21.09.2026): zwei
    # nebeneinander geschriebene Listen mit denselben Feldern driften
    # auseinander, sobald eine ein Feld mehr bekommt.
    pool = [k for k in modell_tco.get("karten") or []
            if k.get("vergleichbar") and k.get("belastbar")
            and not k.get("naeherung") and k.get("gesamt") is not None]
    kandidaten = [k for k in pool if k.get("frisch", True)]
    if not kandidaten:
        # Ein Bündel ohne vergleichbare Karte ist KEIN "kein Bündel": das
        # Modell hat eines, nur keine belastbare Neu-Geraete-Rechnung
        # (gemessener Fall: Galaxy S24 Ultra 512, einzige Karte erneuert).
        # Zwei Leerzustaende statt einem - dieselbe Lehre wie "keine
        # Angabe" gegen "nicht gemessen" bei den Tarifen. Und seit A3 ein
        # dritter: alles da, nur alt - dann heißt die Lücke beim Stand,
        # nicht beim Bestand.
        leer = (TCO_LEER_NUR_ALT if pool else TCO_LEER_KEIN_VERGLEICHBARES)
        return {"tco_ab": None, "tco_anbieter": None, "tco_monat": None,
                "tco_band": None, "tco_beleg": None,
                "tco_leer": leer, **leer_delta}
    # DER ZEITRAUM DER SPALTE (P0-B-h2). Hier stand der Kommentar "ein
    # Filter auf `karte['laufzeit'] == 24` ist bewusst NICHT gebaut ...
    # wird `laufzeit` je wieder variabel, MUSS an dieser Stelle auf 24
    # gefiltert werden". Genau das ist eingetreten - nur nicht an
    # `laufzeit` (der Tariflaufzeit der Rechnung, weiter konstant 24),
    # sondern am ZEITRAUM DER LEITZAHL: `leitzahl_monate` ist seit
    # P0-B-h1 die eine Zahl, die sagt, was `gesamt` traegt, und sie ist
    # bei einem zusammengelegten Buendelmonatspreis 36. Gefiltert wird
    # mit der EINEN Vergleichsregel des Projekts
    # (`tco_model.zeitraum_vergleichbar`): ein unbekannter Zeitraum ist
    # NIE gleich und faellt heraus, statt als 24 zu gelten.
    vergleichbare = [k for k in kandidaten
                     if zeitraum_vergleichbar(k.get("leitzahl_monate"),
                                              TCO_HORIZONT)]
    if not vergleichbare:
        # Gemessene, aktuelle Buendel - aber keines ueber den Zeitraum
        # dieser Spalte (8 Modelle am 21.09.2026, alle nur mit einem
        # 1&1-Buendel ueber 36 Monate). Die Zahl steht mit ihrem eigenen
        # Etikett in der Vergleichsansicht; HIER waere sie eine
        # 36-Monats-Summe unter einem 24-Monats-Kopf.
        return {"tco_ab": None, "tco_anbieter": None, "tco_monat": None,
                "tco_band": None, "tco_beleg": None,
                "tco_leer": TCO_LEER_ANDERE_LAUFZEIT, **leer_delta}
    bester = min(vergleichbare, key=lambda k: k["gesamt"])
    # Der TRAEGER des Abstands: das guenstigste FREMDE Angebot. Nur wo
    # der Wettbewerb selbst fuehrt, ist der Traeger zugleich das beste
    # Angebot - dann sind Leitzahl und Abstand eine Karte wie bisher.
    fremde = [k for k in vergleichbare if not k.get("eigen")]
    traeger = bester if not bester.get("eigen") else (
        min(fremde, key=lambda k: k["gesamt"]) if fremde else None)
    # Die fremden Angebote, die der Zeitraum der Spalte ausschliesst -
    # aus DERSELBEN Kandidatenmenge, nur die andere Seite des Filters
    # (Clean Code 7: eine Definition, zwei Lesarten). Sie sind der Grund,
    # aus dem die Δ-Zelle leer bleibt, und deshalb steht ihr Zustand
    # darin statt eines Strichs.
    im_zeitraum = {id(k) for k in vergleichbare}
    andere_laufzeit = [k for k in kandidaten
                       if not k.get("eigen") and id(k) not in im_zeitraum]
    referenz = modell_tco.get("referenz")
    if traeger is not None and traeger.get("delta_kurz"):
        delta_leer, delta_leer_grund = None, None
    elif referenz is None:
        # OHNE Referenz gibt es keinen Abstand, gleich wie viele
        # Wettbewerber-Angebote daneben stehen - das ist die Bedingung,
        # die `TCO_DELTA_GRUND_KEIN_WETTBEWERBER` unten voraussetzt
        # ("Vodafone listet dieses Modell, aber ..."). Deshalb steht die
        # Frage seit P0-B-h2 VOR den beiden Wettbewerber-Zustaenden.
        delta_leer = TCO_DELTA_LEER_KEINE_REFERENZ
        delta_leer_grund = TCO_DELTA_GRUND_KEINE_REFERENZ
    elif not geraete_tco_karten.referenz_ist_frisch(referenz, heute):
        # GELESEN, nicht nachgerechnet: dieselbe Funktion, mit der
        # `geraete_tco_karten.modelle` entscheidet, ob die Referenz
        # ueberhaupt Massstab eines Deltas sein darf (S2-1). Ist sie es
        # nicht, traegt KEINE Karte des Modells ein Delta - und der Grund
        # ist der Stand der Referenz, nicht der Wettbewerb.
        delta_leer = TCO_DELTA_LEER_ALTE_REFERENZ
        delta_leer_grund = TCO_DELTA_GRUND_ALTE_REFERENZ
    elif traeger is None and andere_laufzeit:
        # Ein Wettbewerber-Angebot GIBT es - nur nicht ueber den Zeitraum
        # der Referenz. Der Strich hiess hier "kein Angebot" (A2) und war
        # damit die falsche Aussage (P0-B-h2, Befund 2). Kurz und Satz
        # kommen aus der Karte selbst, also aus derselben Definition, die
        # die Buendelzeile beschriftet (`geraete_tco_karten.delta_zustand`)
        # - zwei Formulierungen fuer denselben Zustand waeren zwei
        # Zustaende.
        zustand = (min(andere_laufzeit, key=lambda k: k["gesamt"])
                   .get("delta_zustand") or {})
        delta_leer = (zustand.get("kurz")
                      or geraete_tco_karten.DELTA_ANDERE_LAUFZEIT)
        delta_leer_grund = (zustand.get("satz")
                            or TCO_DELTA_GRUND_ANDERE_LAUFZEIT)
    elif traeger is None:
        # Vodafone fuehrt, und KEIN Wettbewerber ist vergleichbar erhoben
        # (4 Zeilen des Bestands am 20.09.) - die Referenz existiert, die
        # Luecke liegt beim Wettbewerb.
        delta_leer = TCO_DELTA_LEER_KEIN_WETTBEWERBER
        delta_leer_grund = TCO_DELTA_GRUND_KEIN_WETTBEWERBER
    else:
        # Ein Traeger MIT dem Zeitraum der Spalte und ohne Abstand: seit
        # dem Filter oben tragen Traeger und Referenz denselben Zeitraum,
        # und damit rechnet `geraete_tco_karten._delta` einen Betrag (auch
        # eine Annaeherung ist einer). Bleibt die Zelle doch leer, steht
        # der Zustand der Karte darin - und wenn sie keinen nennt, dieser
        # Name. Ein Strich waere hier "kein Angebot" (A2) und damit
        # wieder die falsche Aussage.
        zustand = traeger.get("delta_zustand") or {}
        delta_leer = zustand.get("kurz") or TCO_DELTA_LEER_UNBESTIMMT
        delta_leer_grund = zustand.get("satz") or TCO_DELTA_GRUND_UNBESTIMMT
    delta = (traeger or {}).get("delta") or {}
    return {
        "tco_ab": bester["gesamt"],
        "tco_anbieter": bester.get("anbieter"),
        "tco_monat": bester.get("schnitt_monat"),
        "tco_delta": delta.get("betrag"),
        "tco_delta_prozent": delta.get("prozent"),
        "tco_delta_kurz": (traeger or {}).get("delta_kurz"),
        # Der Traeger des Abstands, wo er ein ANDERES Angebot ist als das
        # der Leitzahl - der title der Zelle nennt ihn.
        "tco_delta_anbieter": (traeger.get("anbieter")
                               if bester.get("eigen") and traeger is not None
                               else None),
        "tco_delta_leer": delta_leer,
        "tco_delta_leer_grund": delta_leer_grund,
        "tco_band": bester.get("band"),
        "tco_beleg": {"quelle_url": bester.get("quelle_url", ""),
                      "abgerufen_am": bester.get("abgerufen_am", "")},
        "tco_leer": None,
    }


def _interleave_modelle_je_hersteller(modelle: list) -> list:
    """Die Modellzeilen je Hersteller reihum - B5, eine Ebene hoeher.

    Dieselbe Regel wie `_interleave_je_hersteller` fuer Listungszeilen,
    aber auf der Modellebene von P3: innerhalb eines Herstellers zaehlt
    der BLOCK-Schluessel (Segment vor Baureihe vor Generation, B1), die
    Hersteller selbst laufen reihum, ein Hersteller ohne Namen ans Ende
    (B9). NICHT wiederverwendet werden kann der Listungs-Interleave: sein
    Zeilenschluessel liest `zustand` und `_katalog_betrag`, und eine
    Modellzeile hat beides nicht - sie hat einen ab-Preis und einen
    Aufklapper.
    """
    gruppen: dict[str, list] = {}
    for m in modelle:
        gruppen.setdefault(m["hersteller"] or "", []).append(m)
    geordnet = [sorted(gruppen[h], key=_katalog_block_schluessel)
                for h in sorted(gruppen, key=lambda h: (h == "", h))]
    ergebnis: list = []
    for runde in zip_longest(*geordnet):
        ergebnis.extend(m for m in runde if m is not None)
    return ergebnis


def katalog_leitzahl(katalog_modelle: list) -> float | None:
    """Der guenstigste AKTUELLE Einzelgeraetepreis des Regals.

    EINE Rechnung an EINER Stelle fuer die grosse Zahl ueber der Katalog-
    tafel - die Vorlage zeigt sie, sie aggregiert nicht (Clean Code 1).
    A3: ein "ab" ohne frischen Beleg (`ab_alt`, der letzte Stand mit
    Marke) zaehlt nicht hinein: die Leitzahl sagt "günstigster Stand von
    heute", und dafuer reicht kein Abruf, der aelter ist als jeder
    Leser-Rhythmus (`geraete_tco_karten.ALT_AB_TAGEN`).
    """
    return min((m["ab_preis"] for m in katalog_modelle
                if m.get("ab_preis") is not None
                and not m.get("ab_alt")), default=None)


def katalog_modellzeilen(eintraege: list, katalog, tco_modelle=None,
                         buendel=None, zr_erlaubt: dict | None = None,
                         heute: str = "") -> list[dict]:
    """Der Katalog auf MODELL-Ebene: eine Zeile je (Geraet, Speicher).

    P3 (Strategie Geraete v3, 17.09.2026), Antonios Forderung 5 und 6: der
    Katalog zeigte 566 Listungszeilen zu 111 Modellen, und 36 Zeilen
    sagten "ohne Preis" - dabei war der Preis da, nur nicht auf dieser
    Ebene gerechnet. Diese Funktion liefert die Datenquelle fuer EINE
    Tabelle mit Umschalter Einzelgeraepreis/TCO; beide Ansichten teilen
    `modell_schluessel` als Schluessel (geraete_tco_karten).

    DIE EINE REGEL: keine Modellzeile sagt "ohne Preis". Jede Zeile traegt
    einen Barpreis ("ab X EUR bei Y" = min ueber NEU-Listungen, Beleg mit
    Betrag, Link und Datum aus `barpreise()`) ODER den benannten
    Bündel-Zustand ("nur im Bündel, ab X EUR/Monat" aus geraete_tco.json)
    - nie eine Rate als Barpreis (Hausregel: zwei Preisarten nie mischen).

    Der ZUSTAND ist im Aggregations-Schluessel verankert, nicht erst im
    Text: `barpreise()` laeuft nur ueber NEU-Listungen
    (`VERGLEICHBARE_ZUSTAENDE`), ein refurbished Preis kann einen "ab"
    -Preis also nie stellen (Hausregel B1). Die erneuerten Zeilen bleiben
    im Aufklapper der Modellzeile stehen, mit Etikett.

    Die Listungs-Details werden NICHT geloescht: `zeilen` je Modellzeile
    traegt sie fuer den Zeilen-Aufklapper (die Vorlage baut ihn in P3/C2).
    Eine 1&1-Zeile ohne Barpreis traegt dort ihre Bündel-Angabe
    (`buendel_monat` samt Beleg) statt "ohne Preis".

    `tco_modelle` ist `geraete_tco_view.aufbereiten()["modelle"]` - wird
    nichts uebergeben, stehen die TCO-Felder auf ihrem benannten Leerzustand
    (dieselbe Fehlertoleranz wie ueberall auf dieser Seite: ein kaputter
    TCO-Store darf den Katalog nicht kosten).

    `zr_erlaubt` (P4 Schritt 2c, 18.09.2026) ist der `erlaubt`-Teil des
    Zeitreihen-Knotens (`geraete_zeitreihe.aufbereiten()["daten"]
    ["erlaubt"]`, gefiltert auf NICHT-LEERE Bänder-Listen) - dieselbe EINE
    Quelle, aus der app.js waehlt. Sie entscheidet das Feld `zr` je Zeile:
    True heisst "der Graph-Sprung der Zeitreihe trifft dieses Modell", und
    nur dann rendert die Vorlage den Link. Der Katalog rechnet die
    Erlaubnis NICHT selbst nach (zwei Rechnungen fuer dieselbe Menge
    warden zwei Mengen, CLAUDE.md §6); ohne Parameter bleibt `zr` False -
    fail-closed, ein fehlender Graph-Link ist ehrlicher als ein toter.

    A3-Nachbesserung (Pruefer 20.09.2026, "hoch"): `heute` stellt die Uhr
    fuer den ab-Preis. DIESELBE Frische-Definition wie an der Tafel
    (`geraete_tco_karten.ist_frisch`, Clean Code 7) entscheidet, welcher
    Beleg "ab" stellt und in die Spanne zaehlt - ein alter Barpreis ist
    kein "ab" von heute (gemessener Fall: "ab 1.299 EUR bei
    mobilcom-debitel" vom 14.08., 37 Tage; "ab 289 EUR bei Medimax" vom
    06.09. unterbot das frische ElectronicPartner-Angebot vom 19.09.).
    Ohne `heute` (leerer String) altert nichts - der Modus der alten
    Aufrufer und Tests.

    P5-AUFTRAG 1 (STRATEGIE_GERAETE_V3, 18.09.2026): SICHTBARKEIT FOLGT DEN
    DATEN, NICHT DEM WEG - Bündel ODER Listung genuegt. Neben den Gruppen
    aus dem Listungs-Bestand entsteht eine Zeile fuer jedes Modell, das
    NUR im Bündel-Store steht (`buendel`-Parameter); `hat_buendel` traegt
    jede Zeile, ob mit oder ohne Listung, und entscheidet in der Vorlage
    die Luecke "noch keine Zeitreihe" (Bündel vorhanden, aber noch nicht
    waehlbar - die Wahl der Zeitreihe greift erst ab 2 Bündel-Messtagen,
    `geraete_zeitreihe.AUTO_SICHTBAR_AB_MESTAGEN`).
    """
    belege = geraete_tco_karten.barpreise(eintraege)
    buendel_je, buendel_geraete = _buendel_je_anbieter_modell(
        buendel, eintraege, katalog)
    tco_je_id = {m.get("id"): m for m in (tco_modelle or [])}

    # Schritt 1: Listungszeilen (dieselbe Bauform wie Reiter 2) je Modell
    # gruppieren. Der Schluessel ist derselbe wie in der TCO-Ansicht -
    # EINE Modellmenge, nicht 111 gegen 97 mit zwei Schluesseln.
    gruppen: dict[str, dict] = {}
    for e in eintraege:
        zeile = _katalog_zeile(e, katalog)
        mid = geraete_tco_karten.modell_schluessel(e.get("device_id"),
                                                   e.get("speicher_gb"))
        g = gruppen.get(mid)
        if g is None:
            g = {"schluessel": mid, "device_id": e.get("device_id") or "",
                 "modell": zeile["modell"], "hersteller": zeile["hersteller"],
                 "generation": zeile["generation"], "serie": zeile["serie"],
                 "segment": zeile["segment"], "speicher": zeile["speicher"],
                 "eintraege": [], "zeilen": []}
            gruppen[mid] = g
        g["eintraege"].append(e)
        g["zeilen"].append(zeile)

    # P5-AUFTRAG 1 (STRATEGIE_GERAETE_V3, 18.09.2026): SICHTBARKEIT FOLGT DEN
    # DATEN, NICHT DEM WEG - Buendel ODER Listung genuegt. Ein Geraet, das
    # nur im Buendel verkauft wird (gemessener Fall: das iPhone 18 kam am
    # 17.09. mit 105 Buendeln an, die erste Listung stand noch nicht; die
    # iPad-Titel stehen heute noch in der Unbekannten-Liste), bekam KEINE
    # Katalog-Zeile - der Radar nannte es "nicht im Katalog", obwohl der
    # Bestand es laengst trug. Diese Modelle bekommen ihre Gruppe aus dem
    # Bündel-Store: Felder, die nur eine Listung fuellen kann (ab-Preis,
    # Farben, Listungs-Aufklapper), bleiben ehrlich leer, und die
    # Preiszelle traegt die Bündel-Angabe ("nur im Bündel", derselbe Zweig
    # wie die 1&1-Zeilen). Ein Modell OHNE Listung UND OHNE Bündel bleibt
    # draussen - ohne Daten keine Zeile, das ist dieselbe Regel in der
    # anderen Richtung.
    for mid, geraet in buendel_geraete.items():
        if mid in gruppen:
            continue
        g = katalog.nach_id(geraet["device_id"]) if katalog else None
        gruppen[mid] = {
            "schluessel": mid, "device_id": geraet["device_id"],
            "modell": g.modell if g else geraet["device_id"],
            "hersteller": g.hersteller if g else "",
            "generation": g.generation if g else None,
            "serie": serie_aus_modell(g.modell) if g else "",
            "segment": g.segment if g else "",
            "speicher": geraet["speicher"],
            "eintraege": [], "zeilen": []}

    ergebnis = []
    for mid, gruppe in gruppen.items():
        zeilen = sorted(gruppe["zeilen"], key=_katalog_zeile_schluessel)
        eintraege_modell = gruppe["eintraege"]

        # Schritt 2: der ab-Preis - min ueber die NEU-Barpreise je Anbieter.
        # Je Anbieter zuerst das Minimum (fuenf Farben eines Ladens sind
        # fuenfmal derselbe Preis, `_guenstigstes_je_laden`-Lehre), dann das
        # Gesamt-Minimum MIT Beleg: Betrag, Link, Abrufdatum.
        #
        # A3: FRISCHE Belege zuerst - `ist_frisch`, dieselbe Definition
        # wie die Tafel (Clean Code 7). Ein alter Beleg stellt kein "ab"
        # und keine Spanne von heute. Nur wenn GAR kein frischer Beleg
        # existiert, faellt die Zeile nicht auf "ohne Preis" zurueck,
        # sondern zeigt den letzten Stand MIT Marke (`ab_alt`, harte
        # Regel 9: es IST ein Preis da, nur kein aktueller) - die
        # Bündel-Angabe (Schritt 5) greift dann nicht, denn es gibt
        # Barpreis-Belege, nur keine frischen.
        je_anbieter: dict[str, dict] = {}
        je_anbieter_alt: dict[str, dict] = {}
        for e in eintraege_modell:
            sku = e.get("sku_id") or ""
            for anbieter, beleg in belege.get(sku, {}).items():
                ziel = (je_anbieter_alt
                        if not geraete_tco_karten.ist_frisch(
                            beleg.get("abgerufen_am", ""), heute)
                        else je_anbieter)
                bisher = ziel.get(anbieter)
                if bisher is None or beleg["betrag"] < bisher["betrag"]:
                    ziel[anbieter] = beleg
        auswahl = je_anbieter or je_anbieter_alt
        ab_beleg = (min(auswahl.values(), key=lambda b: b["betrag"])
                    if auswahl else None)
        # Der benannte Zustand "nichts aktuelles, aber ein letzter Stand":
        # die Vorlage graut den ab-Preis aus und haengt die Marke daran
        # (`geraete_tco_karten.alt_marke_fuer` - derselbe Satz wie an der
        # Bündelzeile, eine Stelle).
        ab_alt = bool(je_anbieter_alt) and not je_anbieter

        # Schritt 3: die Spanne - nur wenn WESSENTLICH verschieden. Dieselbe
        # Schwelle wie der Preisvergleich (ODER, nicht UND: bei 200 EUR sind
        # 15 EUR viel und 3 Prozent wenig, bei 2000 umgekehrt). Ein
        # Farbaufschlag von 5 EUR ist keine Spanne, die jemand lesen will.
        # A3: gerechnet ueber DIESELBE Auswahl wie der ab-Preis (`auswahl`)
        # - ein alter Anbieter stand sonst als Spannengrenze da, obwohl
        # sein "ab" schon herausgefallen ist.
        spanne: list = []
        if len(auswahl) >= 2 and ab_beleg is not None:
            betraege = [b["betrag"] for b in auswahl.values()]
            von, bis = min(betraege), max(betraege)
            abstand = bis - von
            if (abstand >= geraete_vergleich.WESENTLICH_EURO
                    or (von > 0
                        and abstand / von * 100 >=
                        geraete_vergleich.WESENTLICH_PROZENT)):
                spanne = [round(von, 2), round(bis, 2)]

        # Schritt 4: die Bündel-Angabe an den Zeilen OHNE Preis (die 37
        # 1&1-Zeilen). Der Monatspreis kommt aus dem Bündel-Store desselben
        # Anbieters, derselben Modellmenge - nie aus der Listung allein,
        # denn der Beleg (Quelle, Datum) haengt am Bündel.
        anbieter_mit_buendel = {}
        for z in zeilen:
            if z["preis"] is not None or z["zuzahlung"] is not None:
                continue
            treffer = buendel_je.get(
                (geraete_tco_karten.normalisiere(z["anbieter"] or ""), mid))
            if treffer is None:
                continue
            z["buendel_monat"] = treffer["monat"]
            z["buendel_tarif"] = treffer["tarif"]
            z["buendel_url"] = treffer["quelle_url"]
            z["buendel_abgerufen_am"] = treffer["abgerufen_am"]
            anbieter_mit_buendel[treffer["anbieter"]] = treffer

        # Schritt 5: der Bündel-Zustand der MODELLZEILE - nur wenn es
        # keinen Barpreis gibt (gemessener Fall: Nothing Phone 4a Pro, nur
        # 1&1). Ein Modell MIT Barpreis braucht ihn nicht: sein Preis steht
        # da, das Bündel steht in der TCO-Ansicht. P5-Auftrag 1: bei einem
        # Modell OHNE Listung gibt es keine zeilen ohne Preis, denen man
        # die Angabe anhaengen koennte - der Pool kommt dann direkt aus
        # dem Bündel-Store desselben Modells.
        buendel_angabe = None
        if ab_beleg is None:
            pool = (list(anbieter_mit_buendel.values())
                    if anbieter_mit_buendel
                    else [v for (_, m), v in buendel_je.items()
                          if m == mid])
            if pool:
                buendel_angabe = min(pool, key=lambda b: b["monat"])

        # Schritt 6: die TCO-Felder aus der TCO-Aufbereitung (nur Wahl des
        # besten Angebots, keine Rechnung - siehe `_tco_spalte`).
        name = gruppe["modell"]
        if gruppe["speicher"]:
            name = f"{name} {int(gruppe['speicher'])} GB"
        # `heute` ist die Uhr dieser Zeile (A3) - dieselbe, mit der oben
        # die Frische der Listungen und der Karten gemessen wird.
        tco_felder = _tco_spalte(tco_je_id.get(mid), heute)

        # Die Händler-Spalte zaehlt, WER das Geraet fuehrt. Ohne Listung
        # (P5-Auftrag 1) sind das die Bündel-Anbieter - "0 Händler" neben
        # "nur im Bündel bei congstar" widerspraeche der eigenen Zelle.
        listen_anbieter = sorted({z["anbieter"] for z in zeilen
                                  if z["anbieter"]})
        if not listen_anbieter:
            listen_anbieter = sorted({v["anbieter"]
                                      for (_, m), v in buendel_je.items()
                                      if m == mid})

        ergebnis.append({
            "schluessel": mid,
            # P4 Schritt 2c: trifft der Graph-Sprung der Zeitreihe dieses
            # Modell? (Siehe Docstring zu `zr_erlaubt` - gelesen, nie
            # nachgerechnet.) Das Feld ist Teil des EINEN Schluesselraums:
            # Katalog und Radar tragen denselben `modell_schluessel`, und
            # `zr` sagt, ob der zweite Reiter (Vergleichs-Zeitreihe) zum
            # selben Modell fuehrt.
            "zr": bool(zr_erlaubt and zr_erlaubt.get(mid)),
            # P5-Auftrag 1: hat dieses Modell ein Bündel (gleich welcher
            # SKU)? Die Vorlage entscheidet daran die Luecke "noch keine
            # Zeitreihe" - ein Modell MIT Bündel, das (noch) nicht waehlbar
            # ist, hat eine Zeitreihe, die MIT DEM NAECHSTEN Messtag
            # beginnt; eines ohne Bündel nennt die TCO-Spalte den Grund
            # ("kein Bündel gemessen"), dort waere der Satz die zweite
            # Aussage fuer dieselbe Tatsache.
            "hat_buendel": mid in buendel_geraete,
            "device_id": gruppe["device_id"],
            "modell": gruppe["modell"],
            "hersteller": gruppe["hersteller"],
            "titel": geraete_tco_karten.titel(gruppe["hersteller"], name),
            "generation": gruppe["generation"],
            "serie": gruppe["serie"],
            "segment": gruppe["segment"],
            "speicher": gruppe["speicher"],
            # ---- Ansicht Einzelgeraepreis ----
            "ab_preis": ab_beleg["betrag"] if ab_beleg else None,
            "ab_anbieter": ab_beleg["anbieter"] if ab_beleg else None,
            "ab_beleg": ab_beleg,
            # A3: der ab-Preis dieses Modells ist ein LETZTER STAND, kein
            # aktueller (kein frischer Beleg seit ALT_AB_TAGEN). Die
            # Zeile bleibt mit Preis, Anbieter und Datum - ausgegraut,
            # mit Marke - und zaehlt nicht in die Leitzahl des Katalogs.
            "ab_alt": ab_alt,
            "ab_alt_marke": (geraete_tco_karten.alt_marke_fuer(
                ab_beleg.get("abgerufen_am", ""))
                if ab_alt and ab_beleg else ""),
            "anbieterzahl": len(listen_anbieter),
            "anbieter": listen_anbieter,
            "farben": sorted({z["farbe"] for z in zeilen if z["farbe"]}),
            "spanne": spanne,
            # ---- Bündel-Zustand (statt "ohne Preis") ----
            "nur_buendel": buendel_angabe is not None,
            "buendel_monat": buendel_angabe["monat"] if buendel_angabe else None,
            "buendel_anbieter": (buendel_angabe["anbieter"]
                                 if buendel_angabe else None),
            "buendel_tarif": buendel_angabe["tarif"] if buendel_angabe else "",
            "buendel_beleg": ({"quelle_url": buendel_angabe["quelle_url"],
                               "abgerufen_am": buendel_angabe["abgerufen_am"]}
                              if buendel_angabe else None),
            # ---- Ansicht TCO ----
            **tco_felder,
            # ---- Aufklapper (Listungs-Ebene, nichts geloescht) ----
            "zeilen": zeilen,
            "listungen": len(zeilen),
        })

    # Schritt 7: Ordnung und Deckel - dieselben Regeln wie Reiter 2, nur
    # eine Ebene hoeher: Modellzeilen je Hersteller reihum
    # (`_interleave_modelle_je_hersteller`, B5), innerhalb des Herstellers
    # nach Segment/Baureihe/Generation (`_katalog_block_schluessel`, B1).
    # Der Zeilendeckel `KATALOG_SICHTBAR` zaehlt Modelle - eine Zeile je
    # Modell, ein Block-Deckel darueber gibt es seit P3 nicht mehr.
    ergebnis = _interleave_modelle_je_hersteller(ergebnis)
    sichtbar_zaehler = 0
    for z in ergebnis:
        z["zeilen_rest"] = sichtbar_zaehler >= KATALOG_SICHTBAR
        if not z["zeilen_rest"]:
            sichtbar_zaehler += 1
    return ergebnis


# `_matrix()` ist am 30.08.2026 geloescht worden, mit der Sektion, die es
# fuellte; die flache Listungs-Tabelle (`katalogzeilen`, 30.08.-18.09.2026)
# ist ihrerseits mit P3 der Modell-Tabelle gewichen. Eine Rechnung weiter
# laufen zu lassen und von keiner Vorlage lesen zu lassen waere derselbe
# Befund wie `UEBERSICHT_MAX_ZEILEN` beim Review davor: lebendig klingende
# Begruendung, keine Wirkung.

def _quellenlage(quellen, db: GeraeteDB, eintraege: list) -> dict:
    """Wer liefert, wer nicht - und warum nicht.

    Kein Anbieter verschwindet stillschweigend (Teil E). Das gilt auch fuer
    die Marken ohne Hardware-Vermarktung: sie stehen in einer eigenen Zeile,
    nicht als leere Karte im Raster.

    `eintraege` ist der BESTAND, nicht der Rohbestand: die Geraetezahl je
    Anbieter steht hier neben derselben Zahl auf `/geraete.html`, und aus
    zwei Mengen gerechnet waeren es zwei Zahlen (o2: 78 gegen 68). Der
    Zustand eines Anbieters kann daran nicht kippen - eine Zwillingsgruppe
    laesst immer einen Ueberlebenden, ein liefernder Anbieter bleibt also
    liefernd. Die GEPRUEFTE Menge waere hier dagegen falsch: ein Anbieter,
    dessen Preise sich alle widersprechen, liefert trotzdem.
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
        "fenster_tage": FENSTER_TAGE, "db_lesbar": not fehler,
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
        "tco": geraete_tco_view.leer(),
        "zeitreihe": geraete_zeitreihe.leer(),
        "katalog_modelle": [],
        # P4-Fix (Sicht-Pruefung 18.09.): die Katalog-Leitzahl auch im
        # Notzustand - der Schluesselmengen-Test haelt Normal- und Not-
        # zustand gegeneinander, und die Vorlage fragt das Feld bedingungs-
        # los ab (None laesst die Leitzahl weg, der Leer-Satz traegt).
        "katalog_ab_preis": None,
        "katalog_sichtbar": KATALOG_SICHTBAR,
        "lifecycle_sichtbar": LIFECYCLE_SICHTBAR,
        "nachfolger_sichtbar": NACHFOLGER_SICHTBAR,
        "auffaellig": {"hat_daten": False, "saetze": [], "bewegungen": [],
                       "neu": [], "weg": [], "kurzer_vorlauf": True,
                       "vorlauf_tage": 0},
        "bestand": [], "alle_punkte": [], "katalog_obj": None,
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
                      "nachfolger": [], "nachfolger_hinweis": "",
                      "portfolio": []},
        "quellenlage": {"zeilen": [], "ohne_hardware": [], "liefernd": 0,
                        "aufgefuehrt": 0, "konfiguriert": 0, "unbekannt": [],
                        "seiten": 0},
    }


def bestand_und_belastbar(sichtbar: list, katalog) -> tuple[dict, list, list]:
    """Die ZWEI Mengen dieser Seite. Gibt (Pruefung, Bestand, belastbar).

    Es sind zwei, nicht eine, und das ist die Regel dieses Projekts und
    nicht der Zuschnitt dieser Funktion: **die Plausibilitaetspruefung
    entscheidet, was GEGENEINANDER gerechnet werden darf - nicht, was es
    gibt.** Ein Ausreisser widerspricht dem Markt und wird gemeldet, nicht
    geloescht; ein Doppelpreis widerspricht sich selbst und darf deshalb in
    keiner Preisaussage stehen - aber er ist trotzdem eine Listung, die
    jemand im Regal findet.

        Bestand    = bereinige(sichtbar)          -> Geraetekatalog
                                                    (Reiter 2), Farbbericht,
                                                    CSV-Export, `bilanz`
        belastbar  = bereinige(pruefe(sichtbar))  -> Preisvergleich, Alarme,
                                                    Preisverlauf, Lifecycle

    Am Bestand vom 31.08.2026 gemessen: 370 sichtbar -> **360** Bestand ->
    **358** belastbar. Der Unterschied sind genau zwei Zeilen, das
    o2-Doppelpreispaar Galaxy S26 FE 128 GB ("pistachio" 811,00 und
    "pistachio bk" 667,00 unter zwei eigenen Adressen).

    WARUM DAS EINMAL FALSCH WAR. Bis zum 31.08.2026 gab diese Funktion die
    belastbare Menge an ALLES heraus, auch an den CSV-Export. Damit standen
    zwei Saetze auf der ausgelieferten Seite, die nicht mehr stimmten -
    Reiter 2: "was aus dem Preisvergleich faellt, verschwindet nicht", und
    `geraete-quellen.html`: "Alles bleibt in der CSV-Tabelle". Das
    S26-FE-Paar stand namentlich im Pruefbericht und fehlte in der Datei,
    auf die derselbe Absatz verwies: der Leser wird auf einen Befund
    gestossen, zur CSV geschickt und findet die Zeile dort nicht.

    Beide Mengen sind sauber im Sinne der Anzeige - keine Farbe mit
    Zustandswort, keine Zeile "Zustand = neu" auf Gebrauchtdaten, keine
    Dublette -, denn `bereinige()` laeuft in beiden.

    ZUR REIHENFOLGE INNERHALB VON `belastbar`. Sie bleibt: erst `pruefe()`,
    dann `bereinige()`. Der Grund ist ein anderer, als bis zum 31.08.2026
    hier stand - die alte Begruendung ("vertauscht stuenden die zwei
    o2-Gebrauchtpreise wieder als Neupreise in `geraete-aktuell.csv`")
    reproduziert NICHT: nachgemessen liefern beide Reihenfolgen denselben
    Bestand, Zeile fuer Zeile, weil die zwei Giftzeilen Zwillinge sind und
    so oder so fallen. Was sich messbar unterscheidet, ist der PRUEFBERICHT:
    `zustand_veraltet` steht in dieser Reihenfolge auf 2, vertauscht auf 0.
    `pruefe()` erkennt die falsch gespeicherte Zustandsangabe an genau dem
    Wort, das `bereinige()` aus der Farbe raeumt - laeuft die Bereinigung
    zuerst, findet die Pruefung nichts mehr zu melden. Ein Befund, den
    niemand mehr meldet, ist der Fehler, den beim naechsten Mal niemand
    findet.

    Und die Reihenfolge traegt ueber den heutigen Bestand hinaus: eine
    Giftzeile OHNE Zwilling faellt nur so heraus. Genau die bauen die zwei
    Tests in `tests/test_geraete_export.py` - ein Fall, den der echte
    Bestand heute nicht enthaelt.
    """
    pruefung = geraete_pruefung.pruefe(sichtbar, katalog)
    return (pruefung,
            geraete_bereinigung.bereinige(sichtbar),
            geraete_bereinigung.bereinige(pruefung["sauber"]))


def aufbereiten(state_dir: Path, quellen, katalog, heute: str = "") -> dict:
    """Alles fuer /geraete.html und /geraete-quellen.html."""
    state_dir = Path(state_dir)
    db = GeraeteDB(state_dir / "geraete_db.json")
    historie = Preishistorie(state_dir / "geraete_preise.jsonl")
    # Der Buendelbestand ist eine EIGENE Datei und heute nicht vorhanden -
    # `TcoDB` faengt das ab und startet leer (`analyze/tco_store`). Er wird
    # hier gelesen und nicht in `geraete_pipeline`, weil dieser Reiter beim
    # RENDERN entsteht: er hat keinen eigenen State und keine LLM-Stufe,
    # dieselbe Bauform wie `report/wettbewerb.py`.
    tco_db = TcoDB(state_dir / "geraete_tco.json")
    # DER TARIFBESTAND GEHOERT ZUR TCO-ANSICHT, nicht nur zum Tarifzweig:
    # er traegt die MINDESTLAUFZEIT des Tarifs, und ohne sie ist keine
    # Leitzahl rechenbar. o2 bindet den Tarif 24 Monate und finanziert das
    # Geraet ueber 36 - wer die zwei gleichsetzt, addiert zwoelf
    # Tarifmonate, die niemand schuldet (A5.5). Fehlt die Datei, bleibt
    # `je_id` leer und die Karten sagen ihre Luecke.
    tarifbestand = Tarifbestand.aus_datei(state_dir / "tarife.jsonl")
    alle = db.eintraege()
    sichtbar = [e for e in alle if e.get("status") in _SICHTBAR]

    # ZWEI MENGEN, und jede Zeile darunter sagt, welche sie meint (siehe
    # `bestand_und_belastbar`):
    #
    #   `bestand`   was es GIBT - bereinigt, aber ungeprueft. Regal,
    #               Farbbericht, CSV, Betriebszahlen.
    #   `belastbar` was gegeneinander gerechnet werden DARF. Vergleich,
    #               Alarme, Preisverlauf, Lifecycle.
    #
    # `sichtbar` bleibt der ROHBESTAND und hat genau noch einen Verbraucher:
    # die Veroeffentlichungsschwelle (siehe unten). Eine
    # Datenqualitaetsheuristik darf keine Navigation schalten.
    pruefung, bestand, belastbar = bestand_und_belastbar(sichtbar, katalog)

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
    # P3: der Satz, der die leere Nachfolger-Sektion erklaert, und der Beleg
    # dafuer, wie viel einer gefuellten Zeile wirklich gemessen ist. Beides
    # entsteht HIER und nicht in `geraete_lifecycle.auswertung` - dort
    # arbeitet parallel ein anderes Paket an der Rechnung selbst.
    lifecycle = {**lifecycle,
                "nachfolger": _mit_beobachtungsbeleg(lifecycle["nachfolger"]),
                "nachfolger_hinweis": _nachfolger_leer_hinweis(
                    alle, katalog, lifecycle["nachfolger"])}

    # Das ECHTE Abrufdatum. Faellt der naechtliche Lauf zwei Wochen aus,
    # behaelt die Datenbank ihre alten Werte - die Legende darf trotzdem
    # nicht den Berichtstag behaupten. Auf einer Seite, deren Verkaufsargument
    # der Belegzwang ist, ist das die teuerste Sorte falscher Zahl.
    # Auf dem BESTAND, nicht auf dem Rohbestand: der Kopf sagt "Preise vom
    # ...", und gemeint sind die Preise, die auf dieser Seite stehen. Eine
    # zusammengefasste Zwillingshaelfte darf das Datum nicht setzen.
    abrufdaten = sorted(e.get("abgerufen_am") for e in bestand
                        if e.get("abgerufen_am"))
    # Gezaehlt werden LAEDEN, nicht Marken. Die dritte Frage der Seite lautet
    # "was kostet dasselbe Geraet bei wem" - und zwei Marken desselben Shops
    # (mobilcom-debitel/freenet) beantworten sie nicht. Mit Marken gezaehlt
    # schaltete sich der Navigationseintrag mit "2 Anbietern" frei, waehrend
    # nur EIN Laden lieferte.
    def _laeden(menge):
        return {laden.get(e.get("anbieter"), e.get("anbieter")) for e in menge}

    def _hersteller(menge):
        return {g.hersteller
                for g in (katalog.nach_id(e.get("device_id")) for e in menge)
                if g and g.hersteller}

    # DIE VEROEFFENTLICHUNGSSCHWELLE RECHNET GEGEN DEN ROHBESTAND - als
    # einzige Zahl dieser Funktion. Bis zum 29.08.2026 nahm sie die
    # Spaltenzahl der Herstelleransicht, und die hing an der
    # Plausibilitaetspruefung. Damit haette ein Anbieter, der an einem Tag
    # seine Farbvarianten mit weiten Farbabstaenden bepreist, den
    # Navigationseintrag "Geraete" auf JEDER Seite verschwinden lassen -
    # ohne Fehler, ohne Warnung, und niemand faende die Seite mehr. Eine
    # Datenqualitaetsheuristik darf keine Navigation schalten (CLAUDE.md §6).
    # Das gilt fuer die Bereinigung genauso: sie kann heute keinen Anbieter
    # verlieren (ein Zwillingspaar laesst immer einen Ueberlebenden), aber
    # eine Schwelle, die sich auf diese Eigenschaft verlaesst, ist keine.
    erreicht = schwelle_erreicht(
        anbieter=len(_laeden(sichtbar)),
        skus=len({e.get("sku_id") for e in sichtbar}),
        hersteller=len(_hersteller(sichtbar)))

    # Die Betriebszahlen am Fuss der Seite stehen in EINEM Satz ("N Geraete
    # in M Varianten, zusammen L Listungen bei A Anbietern") - sie muessen
    # also aus EINER Menge kommen, und zwar aus der, die die Seite zeigt.
    laeden_mit_daten = _laeden(bestand)
    hersteller_mit_daten = _hersteller(bestand)

    # Reiter 1. Die Alarmtabelle liest den fertigen Vergleich - sie rechnet
    # keine Zahl zweimal (CLAUDE.md 6: zwei Rechnungen fuer dieselbe Zahl
    # sind zwei Zahlen). Die Ausreisser-Markierung kommt aus der Pruefung:
    # ein Ausreisser wird gemeldet statt geloescht, und gemeldet heisst DORT
    # sichtbar, wo jemand die Zahl liest.
    vergleich = geraete_vergleich.beide_preisarten(belastbar, katalog,
                                                   laeden=laden)
    alarme = geraete_alarme.zeilen(vergleich["ohne_vertrag"],
                                   pruefung.get("auffaellig"))

    # E2 (16.09.2026): die TCO-ZEITREIHE der Hauptansicht - eigene
    # Aufbereitung (Modell x Band x Anbieter x Messtag aus der rohen
    # Historie) aus DEMSELBEN tco-Dict wie die Bündel-Zeilen (keine zweite
    # Rechnung für dieselben Zahlen), eigener Fehlertopf: ein kaputter
    # Graph darf die GERAETESEITE nicht kosten, die übrigen Reiter bleiben
    # lesbar (dieselbe Auffanglogik wie beim Export weiter unten).
    #
    # A3-Nachbesserung (Pruefer 20.09.2026, "hoch"): Der Bezug der
    # Alterung ist der SPAETERE zweier Uhren, nicht der Berichtstag.
    # `heute` kommt aus `render_site` und ist das Datum des juengsten
    # RADAR-Berichts (Mi/Fr) - aber die Geräteseite rendert TAEGLICH
    # (`geraete.yml`, 03:10 UTC) und fasst die Berichte nicht an. Am
    # 20.09.2026 stand der juengste Bericht auf dem 16.09.: mit ihm als
    # `heute` waren alle sechs Telekom-Buendel vom 15.09. "einen Tag alt"
    # und fuehrten frisch Antwortzeile und Spanne - die 3-Tage-Regel war
    # regelmäßig (So-Mi) wirkungslos. Der Buendel-Store schreibt bei
    # JEDEM nächtlichen Lauf sein eigenes `updated`; derselbe Gedanke wie
    # in `_auffaellig` ("Als Bezug gilt deshalb der spaetere der beiden
    # Tage"). Ohne `heute` (lokaler Aufruf, alte Tests) altert weiter
    # nichts - der Berichtstag bleibt die einzige Uhr, die der Aufruf
    # stellt.
    tco_heute = _spaeterer_tag(heute, tco_db.updated) if heute else ""
    # A3-Nachbesserung (Pruefer 20.09.2026, "hoch"): dieselbe Uhrregel fuer
    # den KATALOG - sein "ab" liest LISTUNGEN, und deren Store
    # (geraete_db.json) schreibt sein eigenes `updated` bei jedem
    # naechtlichen Lauf. Der spaetere von Berichtstag und Bestands-Stand
    # stellt die Uhr fuer die Frische der ab-Auswahl.
    bestand_heute = _spaeterer_tag(heute, db.updated) if heute else ""
    tco = geraete_tco_view.aufbereiten(
        tco_db.buendel(), tco_db.referenzen(), belastbar, katalog,
        # B3 (21.09.2026): `je_id_aktuell`, nicht `je_id` - ein Buendel
        # loest immer auf den BARE `tarif_id` auf, und der bare Schluessel
        # gehoert oft dem Pflichtdokument (Bestandsschutz der Zeitreihe,
        # `tarif_bezug.Tarifbestand`). `je_id_aktuell` traegt dort die
        # Live-Shop-Lesart, wo es sie gibt - dieselbe Regel wie fuer die
        # SIM-only-Referenz nebenan.
        lesbar=tco_db.lesbar, tarife=tarifbestand.je_id_aktuell,
        # O4: der Anbietertyp fuer die Spalte des TCO-Exports (der
        # Store traegt ihn nicht) und die Lage der Buendel-Historie
        # fuer den ehrlichen Satz im Verlaufs-Reiter.
        anbieter_typen={a.name: a.typ for a in quellen.anbieter},
        tco_historie=tco_db.historie_lage(),
        # A3: der Bezugstag schaltet die Alterung ein - ohne ihn altert
        # nichts (`geraete_tco_karten.ist_frisch`).
        heute=tco_heute)
    try:
        # A1: derselbe Tarifbestand wie die Tafel - die Punkte der Historie
        # rechnet die Zeitreihe mit der HEUTIGEN Leitzahl, phasengewichtet
        # ueber dieselben Phasen (`phasen_fuer_buendel`, ohne Widerspruch
        # zur Messung).
        zeitreihe = geraete_zeitreihe.aufbereiten(
            state_dir, tco, tarife=tarifbestand.je_id_aktuell)
    except Exception as exc:                       # noqa: BLE001
        log.error("Zeitreihen-Aufbereitung gescheitert: %s: %s",
                  type(exc).__name__, exc)
        zeitreihe = geraete_zeitreihe.leer()

    # P4 Schritt 2c (18.09.2026): die WAHL-Menge der Zeitreihe (Modell ->
    # nicht-leere Bänder-Liste), gelesen aus DEMSELBEN Knoten, aus dem
    # app.js waehlt - der Katalog-Graph-Sprung darf nur stehen, wo der
    # Sprung auch trifft. Ein Modell ohne Bündel oder unter der Auto-
    # Messtag-Schwelle ist dort nicht waehlbar; sein Link waere ein toter.
    zr_erlaubt = {k: b for k, b in
                  ((zeitreihe.get("daten") or {}).get("erlaubt") or {}).items()
                  if b}

    # P4-Fix (Sicht-Pruefung 18.09., Falz 1): die Leitzahl des KATALOGS -
    # der guenstigste Einzelgeraetepreis des Regals, EINE Rechnung an
    # EINER Stelle (`katalog_leitzahl`, aus denselben Modellzeilen, die
    # die Tabelle rendert - die Vorlage zeigt, sie aggregiert nicht). Der
    # Katalog war der einzige Reiter ohne Falz-Antwort: die groesste
    # Schrift seiner Tafel war die h2.
    katalog_modelle = katalog_modellzeilen(
        bestand, katalog, (tco or {}).get("modelle"),
        tco_db.buendel() if tco_db.lesbar
        else _buendel_aus_listungen(bestand),
        zr_erlaubt=zr_erlaubt,
        # A3: die Uhr der ab-Auswahl - der spaetere von Berichtstag und
        # Bestands-Stand (siehe `bestand_heute` oben).
        heute=bestand_heute)
    katalog_ab_preis = katalog_leitzahl(katalog_modelle)

    # P5-LIVE-PRUEFUNG R3 (18.09.2026): Wer im Zeitreihen-Suchfeld nach
    # einem Modell sucht, das der Katalog kennt, die WAHL aber noch nicht
    # (Bündel mit erst einem Messtag - der iPhone-18-Fall des 17.09.),
    # bekam "kein Treffer" ohne ein Wort. Der Grund steht an der Katalog-
    # zeile, aber der Leser steht am Suchfeld. Der Wahl-Knoten traegt
    # deshalb dieselben "noch keine Zeitreihe"-Modelle (hat_buendel und
    # nicht zr - GELESEN aus denselben Zeilen, nicht nachgerechnet) mit
    # Titel und fruehestem Belegdatum; app.js zeigt daraus EINE Zeile,
    # nur bei 0 Treffern und Katalog-Treffer fuer denselben Begriff.
    katalog_neu = []
    for m in katalog_modelle:
        if not m.get("hat_buendel") or m.get("zr"):
            continue
        belege = sorted(
            b.get("abgerufen_am") for b in
            (m.get("ab_beleg"), m.get("buendel_beleg"))
            if b and b.get("abgerufen_am"))
        katalog_neu.append({
            "id": m["schluessel"], "titel": m["titel"],
            "datum": _neu_seit(belege[0]) if belege else "",
            "iso": belege[0] if belege else ""})
    if isinstance((zeitreihe or {}).get("daten"), dict):
        zeitreihe["daten"]["katalog_neu"] = katalog_neu

    return {
        "tco": tco,
        "zeitreihe": zeitreihe,
        # Der Verlauf rechnet auf `belastbar`, nicht auf `sichtbar`: ein
        # falsch gespeicherter Gebrauchtpreis in derselben Kurve ist ein
        # zweites Produkt in einer Linie, und der Sprung dazwischen saehe
        # aus wie ein Preissturz. Am Galaxy S25 128 GB gemessen macht das
        # den Unterschied zwischen "577-899 EUR" und "850-899 EUR".
        "verlauf": geraete_verlauf.aufbereiten(belastbar, historie, katalog),
        # P3: der Katalog auf MODELL-Ebene - die Datenquelle fuer EINE
        # Tabelle mit Umschalter Einzelgeraepreis/TCO. Er zeigt den
        # BESTAND und nicht `belastbar`: eine refurbished Zeile gehoert
        # nicht in den Vergleich, aber sehr wohl in den Aufklapper des
        # Katalogs - und ebenso die zwei Haelften eines Doppelpreises.
        # Er entsteht aus DEMSELBEN Bestand und DEMSELBEN TCO-Dict wie
        # alles andere auf dieser Seite - keine zweite Rechnung, keine
        # zweite Modellmenge. Ist der Bündel-Store UNLESBAR, liest die
        # Bündel-Angabe die Listung selbst (S2-1 der P3-Code-Pruefung):
        # `buendel()` wuerde still [] liefern, und die 1&1-Zeilen fielen
        # auf "ohne Preis" zurueck - DIE P3-REGEL gilt auch im Fehlerfall
        # (dieselbe Auffanglogik wie `lesbar=` zwei Aufrufe darueber).
        "katalog_modelle": katalog_modelle,
        "katalog_ab_preis": katalog_ab_preis,
        "katalog_sichtbar": KATALOG_SICHTBAR,
        "lifecycle_sichtbar": LIFECYCLE_SICHTBAR,
        "nachfolger_sichtbar": NACHFOLGER_SICHTBAR,
        "pruefung": pruefung["zahlen"],
        "pruefbefunde": pruefung["befunde"],
        # `bereinige()` leert eine nicht leere Menge nie (jede
        # Zwillingsgruppe behaelt einen Ueberlebenden), die zwei Ausdruecke
        # sind also gleichwertig - gefragt wird trotzdem die Menge, die die
        # Seite zeigt.
        "hat_daten": bool(bestand),
        "stand": heute,
        "abgerufen_bis": abrufdaten[-1] if abrufdaten else "",
        "abgerufen_ab": abrufdaten[0] if abrufdaten else "",
        "fenster_tage": FENSTER_TAGE,
        "db_lesbar": db.lesbar,
        "bilanz": {
            "geraete": len({e.get("device_id") for e in bestand}),
            "listungen": len(bestand),
            "skus": len({e.get("sku_id") for e in bestand}),
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
        # Fuer den CSV-Gesamtexport (report/geraete_export.py). Er entsteht
        # in `render_site`, weil er in `site/` schreibt und diese Funktion
        # bewusst KEINEN Schreibzugriff hat - aber er RECHNET seine Menge
        # nicht mehr selbst, er bekommt sie von hier.
        #
        # Der Schluessel hiess `alle_eintraege` (er trug den Rohbestand),
        # dann `export_bestand` (er trug die belastbare Menge). Beide Namen
        # sagten nicht, was drin ist, und der zweite hat die zwei
        # S26-FE-Zeilen aus der CSV entfernt, waehrend zwei Saetze der Seite
        # das Gegenteil versprachen. Jetzt heisst er wie die Menge:
        # `bestand`, gelesen von `geraete_export.schreibe_exporte`.
        "bestand": bestand,
        # Die Historie bleibt vollstaendig; `historie_csv` schneidet sie auf
        # die Listungen des Bestands zu. Der Zuschnitt gehoert dorthin, wo
        # die zwei Dateien nebeneinander entstehen.
        "alle_punkte": punkte_alle,
        "katalog_obj": katalog,
        # G2: der Preisvergleich gegen die eigene Listung. Er bekommt die
        # LADEN-Abbildung mit, sonst zaehlte mobilcom-debitel neben freenet
        # als zweiter guenstigerer Anbieter - derselbe Shop, zweimal.
        "vergleich": vergleich,
        "lifecycle": lifecycle,
        # Beide auf dem BESTAND. Die Quellenseite nennt je Anbieter eine
        # Geraetezahl, die neben derselben Zahl auf `geraete.html` steht -
        # aus zwei Mengen gerechnet waeren es zwei Zahlen.
        # Die Arbeitsliste fuer `config/farben.yaml` steht seit dem 03.09.2026
        # NICHT mehr auf dieser Seite: sie zaehlt der naechtliche Lauf ins
        # Protokoll (`Geraeteradar: unbekannte Farbschreibweisen ...`),
        # bereinigt um Zustandswoerter an der Quelle (geraete_model).
        "quellenlage": _quellenlage(quellen, db, bestand),
    }
