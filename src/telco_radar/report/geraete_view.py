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

from ..geraete_model import serie_aus_modell
from . import (geraete_alarme, geraete_bereinigung, geraete_pruefung,
               geraete_vergleich, geraete_verlauf)
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
KATALOG_SICHTBAR = 12

# Wie viele Zeilen EIN Geraete-Block in der Standardansicht zeigt (P1,
# dritte Nachbesserung 31.08.2026 - Coordinator-Entscheidung nach dem
# zweiten Ruecklauf). Der Auftrag: "was haben die anderen im Regal" ist
# mit sieben Farbvarianten DESSELBEN iPhones nicht beantwortet, mit drei
# Herstellern schon. Gemessen an den echten Daten (`geraete_db.json`,
# 31.08.2026): ein einzelner Block (iPhone 17 Pro, sieben Zeilen: drei
# Vodafone-, drei mobilcom-debitel-, eine o2-Farbvariante) fuellte davor
# mehr als die Haelfte der zwoelf sichtbaren Zeilen - zusammen mit dem
# naechsten Block (Fairphone 6, fuenf Zeilen) blieben nur ZWEI Hersteller
# sichtbar, obwohl mindestens drei gefordert sind. Der Block bleibt dabei
# GANZ erhalten (B6) - dieser Deckel schneidet nur, was OHNE Klick auf
# "alle anzeigen" sichtbar ist, nicht den Block selbst.
BLOCK_SICHTBAR = 2


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


def _interleave_je_anbieter_im_block(zeilen: list) -> list:
    """Reihum je Anbieter INNERHALB eines Geraete-Blocks (P1, dritte
    Nachbesserung 31.08.2026) - dieselbe Technik wie
    `_interleave_je_hersteller`, eine Ebene tiefer.

    Ohne sie fuellte der GUENSTIGSTE Anbieter mit seinen eigenen
    Farbvarianten die beiden sichtbaren Zeilen dieses Blocks
    (`BLOCK_SICHTBAR`) - gemessen am iPhone 17 Pro: drei Vodafone-Farben
    waeren vor der ersten mobilcom-debitel-Zeile gestanden. Die Deckelung
    braeuchte dann zwei Farben DESSELBEN Ladens statt zweier verschiedener
    Laeden, und die Preisspalte vergliche nichts - "je Anbieter die
    guenstigste" ist deshalb der fuehrende Schluessel: die Anbietergruppen
    selbst sind nach ihrer je EIGENEN guenstigsten Zeile geordnet, und erst
    dann wird reihum eine Zeile je Anbieter genommen.
    """
    gruppen: dict[str, list] = {}
    for z in sorted(zeilen, key=_katalog_zeile_schluessel):
        gruppen.setdefault(z["anbieter"] or "", []).append(z)
    geordnet = [gruppen[a] for a in
                sorted(gruppen, key=lambda a: (_katalog_betrag(gruppen[a][0]), a))]
    ergebnis: list = []
    for runde in zip_longest(*geordnet):
        ergebnis.extend(z for z in runde if z is not None)
    return ergebnis


def _katalog_bloecke(zeilen: list) -> list:
    """Fasst Zeilen zu Geraete-Bloecken zusammen: (Hersteller, Modell,
    Speicher). Ein Block bleibt beim Mischen IMMER zusammen (B6, 31.08.2026
    - siehe `_interleave_je_hersteller`) - "wer ein Geraet sucht, findet
    seine Zeilen beieinander", der Zweck, den der Vorgaenger dieser Zeile
    schon einmal trug und den die reine Herstellermischung ersatzlos
    gestrichen hatte: 69 von 90 Geraeten standen in bis zu zwoelf Bloecken
    ueber die ganze Tabelle verteilt.

    JEDE Zeile traegt danach `block_rest`: True, wenn sie die
    `BLOCK_SICHTBAR`-Grenze ihres eigenen Blocks ueberschreitet (P1, dritte
    Nachbesserung, 31.08.2026). Das ist eine reine ANZEIGE-Markierung -
    die Zeile bleibt im Block, an ihrer Stelle, sie wird nur in der
    Standardansicht nicht gezeigt (siehe `app.js`, `anwenden()`). Ein Block
    mit sieben Farbvarianten desselben Geraets fuellte sonst allein einen
    Grossteil der zwoelf sichtbaren Zeilen der ganzen Tabelle - gemessen am
    iPhone 17 Pro (sieben Zeilen) plus Fairphone 6 (fuenf): zusammen zwoelf
    Zeilen, aber nur ZWEI Hersteller, obwohl mindestens drei gefordert
    sind.
    """
    bloecke: dict[tuple, dict] = {}
    for z in zeilen:
        schluessel = (z["hersteller"], z["modell"], z["speicher"])
        b = bloecke.get(schluessel)
        if b is None:
            b = {"hersteller": z["hersteller"], "modell": z["modell"],
                 "speicher": z["speicher"], "generation": z.get("generation"),
                 "serie": z.get("serie") or "", "segment": z.get("segment") or "",
                 "zeilen": []}
            bloecke[schluessel] = b
        b["zeilen"].append(z)
    for b in bloecke.values():
        b["zeilen"] = _interleave_je_anbieter_im_block(b["zeilen"])
        for i, z in enumerate(b["zeilen"]):
            z["block_rest"] = i >= BLOCK_SICHTBAR
    return sorted(bloecke.values(), key=_katalog_block_schluessel)


def _interleave_je_hersteller(zeilen: list) -> list:
    """Reihum je Hersteller statt Hersteller fuer Hersteller - auf
    BLOCK-Ebene, nicht auf Zeilenebene (B6-Nachbesserung, 31.08.2026).

    Dieselbe Technik wie `pipeline._interleave_by_source` fuer die
    Analysten-Stapel: eine reine Gruppierung laesst den alphabetisch ersten
    Hersteller den ganzen sichtbaren Bereich vor dem Deckel verbrauchen
    (B5, 31.08.2026, an der Ausgabe vom 30.08. gemessen: zwoelf
    o2-iPhone-14-Varianten vorn, Samsung/Google/Xiaomi erst nach Scrollen).
    Gemischt wird aber je BLOCK: ein Geraet (Hersteller+Modell+Speicher)
    ist die kleinste Einheit, die reihum weitergereicht wird, und alle
    seine Zeilen wandern gemeinsam - sonst zerreisst dieselbe Mischung, die
    B5 loest, genau das, was Reiter 2 seit seinem Bau verspricht (B6).

    Die Herstellerreihenfolge selbst ist alphabetisch (deterministisch,
    testbar) - mit EINER Ausnahme: ein Hersteller ohne Namen (kein
    Katalogtreffer, `hersteller == ""`) faellt ans ENDE (B9, 31.08.2026).
    `sorted()` stellt einen leeren String sonst an den Anfang, und genau
    diese Gruppe eroeffnete dann das Reihum - die Docstring behauptete das
    Gegenteil, ohne dass eine Zeile Code es einloeste.
    """
    bloecke = _katalog_bloecke(zeilen)
    gruppen: dict[str, list] = {}
    for b in bloecke:
        gruppen.setdefault(b["hersteller"] or "", []).append(b)
    geordnet = [gruppen[h] for h in sorted(gruppen, key=lambda h: (h == "", h))]
    ergebnis: list = []
    for runde in zip_longest(*geordnet):
        for block in runde:
            if block is not None:
                ergebnis.extend(block["zeilen"])
    return ergebnis


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

    DIE STANDARDANSICHT (B5, zurueckgewiesen und nachgebessert am
    31.08.2026). Die Seite oeffnete auf zwoelf Apple-Zeilen bei o2 - die
    Sortierung war rein alphabetisch (Hersteller, Modell), und "iPhone 14"
    steht alphabetisch ganz vorn.

    Die ERSTE Nachbesserung hatte einen globalen Schnitt "neu komplett vor
    dem Rest" plus eine flache Herstellermischung - und geriet damit in
    einen Zielkonflikt, den der zweite Pruefdurchgang aufgedeckt hat (B6):
    dieselbe Mischung, die Herstellervielfalt herstellt, zerreisst die
    Zeilen EINES Geraets ueber die ganze Tabelle (69 von 90 Geraeten in bis
    zu zwoelf Bloecken). Und die flache Generation als Sortierschluessel
    reproduzierte den Fehler vom 29.08.2026 eine Ebene hoeher (B1): eine
    Galaxy A57 (Generation 57) schlug jede S- oder Z-Reihe, weil
    `generation` nur innerhalb ihrer eigenen Baureihe eine Zahl ist.

    Diese Fassung loest beides zugleich, indem sie auf BLOCK-Ebene mischt
    (`_katalog_bloecke`, `_interleave_je_hersteller`) statt auf Zeilenebene:

      1. Ein GERAET (Hersteller, Modell, Speicher) ist ein Block. Seine
         Zeilen bleiben IMMER zusammen, sortiert "neu" vor Rest und danach
         nach Betrag (`_katalog_zeile_schluessel`) - wer ein Geraet sucht,
         findet seine Zeilen beieinander, der guenstigste Preis oben (B6).
      2. Die Bloecke EINES Herstellers sind nach SEGMENT geordnet
         (flagship vor premium vor mid vor entry), nicht nach roher
         Generation - das ist das Feld, das ueber Baureihen hinweg
         vergleichbar ist. Erst innerhalb derselben Baureihe zaehlt die
         Generation absteigend (`_katalog_block_schluessel`, B1).
      3. Die Bloecke MEHRERER Hersteller laufen reihum
         (`_interleave_je_hersteller`) statt Hersteller fuer Hersteller -
         sonst verbraucht der alphabetisch erste Hersteller den ganzen
         sichtbaren Bereich vor dem Deckel (B5).

    Ob "neu" wirklich vorn STEHT (nicht nur innerhalb seines eigenen
    Blocks, sondern sichtbar ohne Scrollen), regelt seit der Nachbesserung
    NICHT mehr diese Sortierung, sondern der Zustandsfilter zusammen mit
    dem filterbewussten Deckel (`app.js`, `anwenden()`, B2/B3): eine
    Umsortierung allein kann das nicht mehr leisten, sobald ein Geraet
    sowohl neue als auch gebrauchte Zeilen hat - genau der Fall, den B6
    zeigt. Diese Funktion filtert weiterhin NICHTS heraus: die Zeilenzahl
    bleibt exakt der Bestand, Ueberschrift, Deckel und "alle anzeigen"
    lesen dieselbe, vollstaendige Liste.
    """
    zeilen = []
    for e in eintraege:
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
        zeilen.append({
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
            "zuzahlung": e.get("zuzahlung"),
            "tarif": e.get("tarif_referenz") or "",
            "verfuegbarkeit": e.get("verfuegbarkeit") or "unbekannt",
            "url": e.get("quelle_url") or "",
            "abgerufen_am": e.get("abgerufen_am") or "",
        })

    ergebnis = _interleave_je_hersteller(zeilen)

    # `zeilen_rest` ist die EINE Zusicherung, die sowohl das SSR-Markup
    # (kein JavaScript) als auch `app.js` beim ersten Laden lesen: eine
    # Zeile bleibt in der Standardansicht verborgen, wenn sie ENTWEDER
    # `block_rest` ist (ueber `BLOCK_SICHTBAR` ihres eigenen Blocks
    # hinaus, P1) ODER die zwoelf sichtbaren Plaetze unter den nicht schon
    # block-gedeckelten Zeilen bereits vergeben sind (`KATALOG_SICHTBAR`).
    # Ohne diese Verrechnung saehe ein Leser OHNE JavaScript weiterhin
    # sieben Farbvarianten desselben Geraets vor den ersten zwoelf
    # Positionen - block_rest existiert serverseitig, wurde bis hierhin nur
    # noch nicht mit dem Zeilendeckel verrechnet.
    sichtbar_zaehler = 0
    for z in ergebnis:
        if z["block_rest"]:
            z["zeilen_rest"] = True
            continue
        z["zeilen_rest"] = sichtbar_zaehler >= KATALOG_SICHTBAR
        if not z["zeilen_rest"]:
            sichtbar_zaehler += 1
    return ergebnis


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
        "katalogtabelle": [],
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

    return {
        # Der Verlauf rechnet auf `belastbar`, nicht auf `sichtbar`: ein
        # falsch gespeicherter Gebrauchtpreis in derselben Kurve ist ein
        # zweites Produkt in einer Linie, und der Sprung dazwischen saehe aus
        # wie ein Preissturz. Am Galaxy S25 128 GB gemessen macht das den
        # Unterschied zwischen "577-899 EUR" und "850-899 EUR".
        "verlauf": geraete_verlauf.aufbereiten(belastbar, historie, katalog),
        # Reiter 2 zeigt den BESTAND und nicht `belastbar`: eine refurbished
        # Zeile gehoert nicht in den Vergleich, aber sehr wohl in den
        # Katalog - und ebenso die zwei Haelften eines Doppelpreises. Genau
        # das verspricht der Satz ueber der Tabelle.
        "katalogtabelle": katalogzeilen(bestand, katalog),
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
