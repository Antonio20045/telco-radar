"""Lifecycle-Auswertung des Geraeteradars - deterministisch, ohne Modell.

Vier Fragen, alle aus der Historie gerechnet:

    Listungsdauer     Wie lange steht ein Geraet bei einem Anbieter im Regal?
    Preisverfall      Wie weit ist der Preis vom Einfuehrungspreis entfernt?
    Nachfolger-Effekt Was passiert mit dem Vorgaenger, wenn der Nachfolger
                      erscheint - nach 30, 60 und 90 Tagen?
    Portfolio-Tiefe   Wie viele Generationen fuehrt ein Anbieter gleichzeitig?

Die vierte ist der Kern von Antonios Beobachtung: Wettbewerber halten das
Vorgaengermodell als Preiseinstieg im Regal, waehrend bei Vodafone das alte
Geraet meist direkt ersetzt wird. Diese Zahl macht den Unterschied sichtbar.

KEIN LLM, und das ist keine Sparmassnahme. Jede Zahl hier laesst sich gegen
`data/state/geraete_preise.jsonl` nachrechnen; ein Modell dazwischen waere
eine Schicht, die niemand pruefen kann.

DIE EHRLICHKEIT UEBER DIE DATENBASIS
------------------------------------
In den ersten Wochen gibt es schlicht keine Historie. Aus zwei Messpunkten
laesst sich trotzdem eine Kurve zeichnen, und sie sieht gut aus - genau das
tut diese Seite nicht. Unterhalb von `MIND_PUNKTE` Messpunkten traegt jedes
Ergebnis `duenn: True` und einen Satz, der die Zahl nennt, auf der es beruht.
Ein Test haelt das fest.

DIE VERWEILDAUER NACH DEM MARKTSTART DES NACHFOLGERS
----------------------------------------------------
Die Anforderung der Fachabteilung lautet vollstaendig: "Preis des Vorgaengers
30/60/90 Tage nach Marktstart des Nachfolgers UND wie lange er danach noch im
Regal bleibt." Der zweite Halbsatz ist die eigentliche These - Wettbewerber
lassen das Vorjahresmodell als guenstigen Einstieg stehen, bei Vodafone wird
direkt ersetzt - und er haengt NICHT am Preis.

Vier Regeln tragen die Zahl:

1. Gerechnet wird je (Geraet, Anbieter), nicht je Listung. Ein Geraet steht
   bei einem Haendler in acht Farben und drei Speichergroessen; die Frage
   "wie lange bleibt es im Regal" beantwortet das REGAL, nicht die einzelne
   Farbvariante. Anfang und Ende der Gruppe sind deshalb das frueheste
   `first_seen` und das spaeteste `last_verified` ihrer Listungen.

2. Die Zahl sagt, ob sie eine UNTERGRENZE ist. Alle heutigen Kandidaten haben
   ihren Nachfolger-Marktstart 570 bis 710 Tage vor unserem ersten Messpunkt
   (10.08.2026): belastbar sagen laesst sich ueber sie nur "steht 709 Tage
   nach dem Marktstart seines Nachfolgers noch im Regal" - eine Untergrenze,
   kein Verlauf. Wer daraus eine gemessene Verweildauer macht, behauptet eine
   Beobachtung, die es nie gab. `verweildauer_untergrenze` traegt genau
   diesen Unterschied: True heisst "wir haben erst NACH dem Marktstart zu
   messen begonnen".

3. Eine Zeile OHNE Preisbasis erscheint trotzdem - mit Verweildauer und
   leeren Preisspalten. Das ist die Entscheidung dieser Datei, und sie ist
   begruendet: `basis` fehlt genau dann, wenn wir vor dem Marktstart des
   Nachfolgers noch nicht gemessen haben - heute bei ALLEN sechs
   (Geraet, Anbieter)-Paaren des Bestands. Wuerde die Zeile daran
   scheitern, verschwiege die Sektion eine echte Messung (die Verweildauer,
   sauber untergrenzt) wegen einer fehlenden (dem Preis von damals). Eine
   leere Preisspalte ist ehrlich; eine fehlende Zeile ist eine Auskunft,
   die wir haetten geben koennen. `nach` und `prozent` tragen dabei ihre
   vollen Schluessel mit None - die Darstellung soll nie zwischen zwei
   Formen unterscheiden muessen.

4. Die Tabelle steht hinter DERSELBEN Schwelle wie alles andere hier: vier
   Messtermine ueber mindestens 21 Tage. Bis zum 31.08.2026 lief sie durch
   kein Gatter und war damit die einzige Sektion, die aus zwei Messpunkten
   eine Aussage machte. Reicht es fuer kein Geraet, ist die Liste leer und
   die Seite sagt den Duenn-Satz.

Die Zeile traegt fuer das Darstellungspaket zusaetzlich zu den bisherigen
Schluesseln: `anbieter`, `verweildauer_tage`, `verweildauer_untergrenze`,
`noch_gelistet`, `beobachtet_seit` und `zuletzt_bestaetigt`.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from ..geraete_model import Katalog, serie_aus_modell
from .geraete_store import STATUS_AKTIV, STATUS_VERMUTLICH

log = logging.getLogger(__name__)

# Ab so vielen Messpunkten gilt die Datenbasis als tragfaehig. Zwoelf
# entspricht bei zwei Laeufen je Woche rund sechs Wochen - genug, um eine
# Preisstufe von einer Aktion zu unterscheiden.
MIND_PUNKTE = 12

# Und so viele Wochen Beobachtung nennt der Hinweis als Ziel. Bewusst eine
# runde, ehrliche Hausnummer: es ist die Zeit, in der ein Geraet ueblicherweise
# seine erste Preisstufe nimmt.
MIND_WOCHEN = 12

# --------------------------------------------------------------------------
# DIE SCHWELLE, ohne die diese Sektion luegt
# --------------------------------------------------------------------------
# Am 11.08.2026 zeigte die ausgelieferte Seite zwoelf Zeilen "0 Tage" und
# zwoelf Zeilen "+0.0 %". Der Grund stand eine Zeile hoeher: `duenn` rechnete
#
#     duenn = len(punkte) < MIND_PUNKTE
#
# und zaehlte damit PREISPUNKTE statt MESSTERMINE. 85 Listungen an EINEM Tag
# ergeben 85 Punkte, die Datenbasis galt als dick, der Nicht-duenn-Zweig lief,
# und die Klasse `gr-basis--duenn` - die im CSS seit dem ersten Tag angelegt
# ist - kam im HTML kein einziges Mal vor. Zwei Bildschirmseiten, die exakt
# nichts aussagen und dabei wie ein Ergebnis aussehen.
#
# Gezaehlt werden jetzt VERSCHIEDENE Messtage und die Spanne dazwischen, und
# zwar JE GERAET: ein Portfolio, in dem ein Geraet lange beobachtet wird und
# elf andere seit gestern, hat keine zwoelf belastbaren Zeilen.
#
# GENAU DAS TAT DER CODE BIS ZUM 31.08.2026 NICHT. `_oft_genug` las
# `termine_je_anbieter[eintrag["anbieter"]]` und zaehlte damit JE ANBIETER:
# ein einziges lange beobachtetes Geraet schaltete den ganzen Anbieter frei,
# also auch die elf von gestern. Docstring und Code widersprachen sich - die
# Fehlerklasse "eine Zusicherung in einer Docstring ist keine Zusicherung",
# an der dieses Projekt schon einmal 18 Tage lang vorbeigelaufen ist.
#
# Gezaehlt wird jetzt das FENSTER DER LISTUNG: ihre eigenen Preispunkte, ihr
# `erstpreis_am`, ihr `last_verified` - und die Prueftermine ihres Anbieters,
# SOWEIT SIE ZWISCHEN `first_seen` UND `last_verified` LIEGEN. Der letzte
# Teil ist kein Rueckfall in die Anbieterrechnung, sondern die Lehre aus G0
# (28.08.2026): `geraete_preise.jsonl` traegt nur AENDERUNGSpunkte, ein
# stabiler Preis schreibt keine Zeile. Wer nur die eigenen Punkte zaehlt,
# sperrt genau die Ware aus, die ein halbes Jahr unveraendert im Regal steht,
# und laesst die herein, deren Verfuegbarkeit flattert. Ein Prueftermin
# INNERHALB des Fensters ist dagegen eine echte Beobachtung dieser Listung:
# sie war davor da und danach noch da, und die Zwei-Stufen-Auslistung haette
# sie sonst gealtert.
#
# Die LAUFZAHL des Anbieters bleibt daneben ein Boden. Sie laesst sich
# keinem Fenster zuordnen, ist aber die einzige Auskunft, die einen Lauf
# ueberlebt, dessen Bestaetigung ein spaeterer ueberschrieben hat - und ohne
# sie faellt die Ware durch, die seit einem Jahr unveraendert im Regal steht.
# Das ist der bewusst verbliebene Rest Anbieterrechnung; er betrifft im
# Bestand vom 31.08.2026 zwei von 370 Listungen (ALDI TALK, vier Laeufe bei
# drei bekannten Terminen), und beide scheitern ohnehin an der Spanne.
MIND_TERMINE_JE_GERAET = 4
MIND_TAGE_JE_GERAET = 21

_FENSTER = (30, 60, 90)

_SICHTBAR = (STATUS_AKTIV, STATUS_VERMUTLICH)


def _datum(wert) -> Optional[date]:
    try:
        return datetime.strptime(str(wert or "").strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


# --------------------------------------------------------------------------
# Listungsdauer
# --------------------------------------------------------------------------

def listungsdauer(eintrag: dict) -> Optional[int]:
    """Tage von der ersten bis zur letzten BESTAETIGUNG.

    Bewusst `last_verified` und nicht `ended_since`: die zwei Fehltreffer, die
    die Auslistungslogik braucht, sind kein Portfoliozeitraum. Sonst haette
    jedes ausgelistete Geraet zwei Laufabstaende geschenkt bekommen.
    """
    von, bis = _datum(eintrag.get("first_seen")), _datum(eintrag.get("last_verified"))
    if von is None or bis is None or bis < von:
        return None
    return (bis - von).days


# --------------------------------------------------------------------------
# Preisverfall
# --------------------------------------------------------------------------

def _aktueller_preis(eintrag: dict, art: str) -> Optional[float]:
    feld = "preis_ohne_vertrag" if art == "ohne_vertrag" else "zuzahlung"
    wert = eintrag.get(feld)
    return float(wert) if wert is not None else None


def preisverfall(eintrag: dict) -> Optional[dict]:
    """Heutiger Preis gegen den Einfuehrungspreis, absolut und in Prozent.

    Gerechnet wird ausschliesslich innerhalb EINER Preisart. Ein
    Einfuehrungspreis von 1449 Euro ohne Vertrag gegen eine spaetere
    Zuzahlung von 49,95 Euro ergaebe 96,6 Prozent "Verfall" - die zwei
    Preisarten in einer Rechnung, genau was Teil C4 verbietet.
    """
    erst = eintrag.get("erstpreis")
    art = eintrag.get("erstpreis_art") or "ohne_vertrag"
    if erst in (None, 0):
        return None
    jetzt = _aktueller_preis(eintrag, art)
    if jetzt is None:
        return None
    erst = float(erst)
    return {
        "erstpreis": erst,
        "erstpreis_am": eintrag.get("erstpreis_am", ""),
        "aktuell": jetzt,
        "art": art,
        "absolut": round(jetzt - erst, 2),
        "prozent": round((jetzt - erst) / erst * 100.0, 1),
    }


# --------------------------------------------------------------------------
# Nachfolger-Effekt
# --------------------------------------------------------------------------

def _preis_am(punkte: list, stichtag: date, art: str = "preis_ohne_vertrag") -> Optional[float]:
    """Der zuletzt gemessene Preis AM oder VOR dem Stichtag.

    Eine Treppenfunktion, keine Interpolation: zwischen zwei
    Aenderungspunkten galt der aeltere Preis. Interpoliert waere eine Zahl,
    die nie ausgezeichnet war.
    """
    gueltig = None
    for p in sorted(punkte, key=lambda x: x.get("datum", "")):
        tag = _datum(p.get("datum"))
        if tag is None or tag > stichtag:
            continue
        if p.get(art) is not None:
            gueltig = float(p[art])
    return gueltig


def _eigene_punkte(punkte: list, device_id: str,
                   anbieter: Optional[str] = None) -> list:
    """Die Preispunkte, die zu diesem Geraet (und ggf. Anbieter) gehoeren.

    Der Rueckfall auf die ganze Liste gilt nur ohne Anbieterfilter und nur,
    wenn kein einziger Punkt ein `device_id` traegt - so rechnen aeltere
    Aufrufer und Tests, die eine reine Preisreihe uebergeben. MIT Anbieter
    darf er nicht greifen: dann waere die "Preisreihe dieses Haendlers" die
    aller Haendler, und der Nachfolger-Effekt verrechnete den Discounter
    gegen den Netzbetreiber.
    """
    treffer = [p for p in punkte
               if p.get("device_id") == device_id
               and (anbieter is None or p.get("anbieter") == anbieter)]
    if treffer:
        return treffer
    if anbieter is None:
        return punkte
    return [p for p in punkte if p.get("anbieter") == anbieter]


def nachfolger_effekt(device_id: str, katalog: Katalog, punkte: list,
                      heute: Optional[str] = None,
                      anbieter: Optional[str] = None) -> Optional[dict]:
    """Was der Marktstart des Nachfolgers mit dem PREIS des Vorgaengers macht.

    Gibt None, wenn es keinen Nachfolger im Katalog gibt, wenn dessen
    `marktstart` fehlt (ein geratenes Datum waere schlimmer als keines) oder
    wenn wir vor dem Start noch gar nicht gemessen haben.

    Die zweite Haelfte der Frage - wie lange der Vorgaenger danach noch im
    Regal steht - haengt am Preis NICHT und wohnt deshalb in
    `verweildauer_nach_nachfolger`. `auswertung` setzt beide zusammen; eine
    fehlende Preisbasis nimmt der Zeile ihre Preisspalten, nicht ihre
    Existenz (Modulkopf, Regel 3).
    """
    nachfolger = katalog.nachfolger_von(device_id)
    if nachfolger is None:
        return None
    start = _datum(nachfolger.marktstart)
    if start is None:
        return None
    eigene = _eigene_punkte(punkte, device_id, anbieter)
    basis = _preis_am(eigene, start)
    if basis is None or basis == 0:
        return None
    stand = _datum(heute) or date.today()

    nach: dict = {}
    prozent: dict = {}
    for tage in _FENSTER:
        stichtag = start.fromordinal(start.toordinal() + tage)
        if stichtag > stand:
            nach[tage] = None
            prozent[tage] = None
            continue
        wert = _preis_am(eigene, stichtag)
        nach[tage] = wert
        prozent[tage] = round((wert - basis) / basis * 100.0, 1) if wert else None
    return {
        "device_id": device_id,
        "nachfolger": nachfolger.device_id,
        "nachfolger_modell": nachfolger.modell,
        "marktstart": nachfolger.marktstart,
        "anbieter": anbieter or "",
        "basis": basis,
        "nach": nach,
        "prozent": prozent,
    }


# Die Preisspalten einer Zeile OHNE Basis. Dieselben Schluessel wie im
# Normalfall - eine Darstellung, die zwischen zwei Formen unterscheiden muss,
# unterscheidet irgendwann falsch.
def _leere_preisspalten() -> dict:
    return {"basis": None,
            "nach": {t: None for t in _FENSTER},
            "prozent": {t: None for t in _FENSTER}}


def verweildauer_nach_nachfolger(eintraege: list,
                                 katalog: Katalog) -> Optional[dict]:
    """Wie lange steht der Vorgaenger NACH dem Marktstart seines Nachfolgers?

    *eintraege* sind die Listungen EINER (Geraet, Anbieter)-Gruppe - acht
    Farben und drei Speichergroessen desselben Geraets sind ein Regalplatz,
    keine acht Antworten (Modulkopf, Regel 1). Gerechnet wird deshalb vom
    fruehesten `first_seen` bis zum spaetesten `last_verified` der Gruppe.

    Gibt None ohne Nachfolger, ohne dessen `marktstart` und ohne ein
    verwertbares `last_verified` - eine Verweildauer ohne rechte Kante waere
    geraten.

    `verweildauer_tage` ist die Zahl der Tage vom Marktstart des Nachfolgers
    bis zur letzten Bestaetigung, mindestens 0: verschwindet der Vorgaenger
    VOR dem Marktstart, ist die ehrliche Antwort "keinen Tag" und nicht eine
    negative Dauer.

    `verweildauer_untergrenze` ist True, wenn unsere Beobachtung erst NACH
    dem Marktstart begonnen hat. Dann ist die Zahl kein gemessener Verlauf,
    sondern eine Untergrenze: das Geraet stand mindestens so lange im Regal,
    wie wir zugesehen haben. Bei allen vier Kandidaten des Bestands vom
    31.08.2026 ist genau das der Fall (570 bis 710 Tage Vorlauf).

    `noch_gelistet` beantwortet "steht es heute noch da" aus dem Status des
    Stores - `heute` verschiebt den Status nicht, es taugt nur zum Vergleich
    und ist deshalb hier nur der Vollstaendigkeit halber entgegengenommen.
    """
    eintraege = [e for e in eintraege if e]
    if not eintraege:
        return None
    device_id = eintraege[0].get("device_id")
    nachfolger = katalog.nachfolger_von(device_id)
    if nachfolger is None:
        return None
    start = _datum(nachfolger.marktstart)
    if start is None:
        return None

    enden = [d for d in (_datum(e.get("last_verified")) for e in eintraege) if d]
    if not enden:
        return None
    ende = max(enden)

    # Der Beobachtungsbeginn der GRUPPE. `erstpreis_am` zaehlt mit: bei einer
    # Listung, die aus einem Altbestand uebernommen wurde, ist es der aeltere
    # der beiden Belege.
    anfaenge = [d for d in (_datum(e.get(feld))
                            for e in eintraege
                            for feld in ("first_seen", "erstpreis_am")) if d]
    beginn = min(anfaenge) if anfaenge else ende

    return {
        "device_id": device_id,
        "anbieter": eintraege[0].get("anbieter") or "",
        "nachfolger": nachfolger.device_id,
        "nachfolger_modell": nachfolger.modell,
        "marktstart": nachfolger.marktstart,
        "verweildauer_tage": max(0, (ende - start).days),
        "verweildauer_untergrenze": beginn > start,
        "noch_gelistet": any(e.get("status") == STATUS_AKTIV for e in eintraege),
        "beobachtet_seit": beginn.isoformat(),
        "zuletzt_bestaetigt": ende.isoformat(),
    }


# --------------------------------------------------------------------------
# Portfolio-Tiefe
# --------------------------------------------------------------------------

def portfolio_tiefe(eintraege: list, katalog: Katalog) -> list:
    """Wie viele GERAETE-Generationen fuehrt ein Anbieter gleichzeitig?

    Gezaehlt werden verschiedene (Hersteller, Baureihe, Jahrgang) - nicht
    device_ids und nicht SKUs. Acht Farben eines Modells sind ein Regalplatz,
    iPhone 17 / 17 Pro / 17 Pro Max sind EIN Jahrgang, und drei Jahrgaenge
    sind eine Strategie.

    Die Zahl der Modelle steht daneben als `modelle_anzahl`. Bis zum
    29.08.2026 stand sie unter der Ueberschrift "Generationen": die Seite
    meldete "o2 fuehrt 54 Generationen" bei 59 beobachteten Geraeten.
    """
    je_anbieter: dict[str, dict] = {}
    for e in eintraege:
        if e.get("status") not in _SICHTBAR:
            continue
        name = e.get("anbieter") or ""
        eintrag = je_anbieter.setdefault(name, {
            "anbieter": name, "anbieter_typ": e.get("anbieter_typ", ""),
            "geraete": set(), "skus": set(), "modelle": []})
        eintrag["geraete"].add(e.get("device_id"))
        eintrag["skus"].add(e.get("sku_id"))

    out = []
    for name, roh in je_anbieter.items():
        modelle = []
        for gid in sorted(roh["geraete"]):
            g = katalog.nach_id(gid)
            modelle.append({
                "device_id": gid,
                "modell": g.modell if g else gid,
                "hersteller": g.hersteller if g else "",
                "generation": g.generation if g else None,
            })
        # W3 (29.08.2026): bis dahin stand hier `len(roh["geraete"])` - also
        # die Zahl verschiedener MODELLE unter der Ueberschrift
        # "Generationen". Die Seite meldete damit "o2 fuehrt 54
        # Generationen" bei 59 beobachteten Geraeten insgesamt.
        #
        # Eine Generation ist der Jahrgang eines Herstellers: iPhone 17,
        # 17 Pro und 17 Pro Max sind EINE. Genau daran haengt die Aussage
        # dieser Kennzahl - wer das Vorjahresmodell im Regal laesst, hat
        # einen Preiseinstieg, ohne den Preis des neuen Geraets anzufassen.
        # Drei Varianten desselben Jahrgangs sind kein Preiseinstieg.
        #
        # Ein Katalogeintrag OHNE Jahrgang zaehlt nicht mit: sonst waeren
        # drei Geraete ohne Angabe drei Generationen, und die Kennzahl
        # wuchse mit der Luecke im Katalog statt mit dem Portfolio.
        # Je BAUREIHE, nicht je Hersteller: "Redmi 17", "Redmi Note 17" und
        # "Xiaomi 17T" sind drei Produktlinien mit derselben Nummer und
        # waeren als (Hersteller, Nummer) EINE Generation. Umgekehrt sind
        # Galaxy A57 und Galaxy S26 zwei Jahrgaenge zweier Reihen und keine
        # 31 Generationen Abstand.
        jahrgaenge = {(m["hersteller"], serie_aus_modell(m["modell"]),
                       m["generation"])
                      for m in modelle if m["generation"] is not None}
        out.append({
            "anbieter": name,
            "anbieter_typ": roh["anbieter_typ"],
            # Der eigene Anbieter steht in dieser Liste MIT, und rot. Das ist
            # der Punkt der Sektion: Wettbewerber lassen das Vorjahresmodell
            # als guenstigen Einstieg im Regal, bei uns wird das alte Geraet
            # meist direkt ersetzt. Eine Portfolio-Tiefe ohne uns beantwortet
            # die Frage nicht, wegen der sie dasteht.
            "eigen": (name or "").strip().lower() == "vodafone",
            "generationen": len(jahrgaenge),
            "modelle_anzahl": len(roh["geraete"]),
            "skus": len(roh["skus"]),
            "modelle": sorted(modelle, key=lambda m: (m["hersteller"],
                                                      -(m["generation"] or 0))),
        })
    return sorted(out, key=lambda t: (-t["generationen"],
                                      -t["modelle_anzahl"], t["anbieter"]))


# --------------------------------------------------------------------------
# Die Gesamtauswertung
# --------------------------------------------------------------------------

def auswertung(eintraege: list, punkte: list, katalog: Katalog,
               heute: Optional[str] = None,
               laeufe_je_anbieter: Optional[dict] = None,
               termine_je_anbieter: Optional[dict] = None) -> dict:
    """Alles zusammen, mitsamt der Aussage ueber die eigene Datenbasis.

    `termine_je_anbieter` ({anbieter: [ISO-Tage]}) ist die Quelle fuer die
    Messtermin-Zaehlung. Die Preishistorie taugt dafuer NICHT: sie traegt
    nur AENDERUNGSpunkte, und ein Bestand mit stabilen Preisen hat dort
    genau einen Tag - die Seite meldete deshalb am 28.08.2026 nach 17 Tagen
    und vier echten Pruefterminen "bisher 1 Messtermin". Ohne das Argument
    (aeltere Aufrufer, Tests) bleibt die alte Rechnung ueber die Historie.
    """
    daten = [d for d in (_datum(p.get("datum")) for p in punkte) if d]
    if termine_je_anbieter:
        for tage in termine_je_anbieter.values():
            daten.extend(d for d in (_datum(t) for t in (tage or [])) if d)
    termine = sorted({d for d in daten})
    # Der Bezugstag ist der SPAETERE von Berichtstag und juengster Messung -
    # dieselbe Rechnung wie in `geraete_view._auffaellig`. Der Geraetezweig
    # laeuft naechtlich, der Bericht zweimal die Woche; ohne die Korrektur
    # rechnete `(stand - min(daten)).days` negativ und `max(1, …)` machte
    # daraus "1 Woche", obwohl seit einem Tag gemessen wird.
    stand = _datum(heute) or date.today()
    if daten and max(daten) > stand:
        stand = max(daten)
    beobachtungstage = (stand - min(daten)).days if daten else 0
    wochen = max(1, beobachtungstage // 7) if beobachtungstage >= 7 else 0

    # JEDE KENNZAHL AN IHRER EIGENEN BEOBACHTUNGSDAUER, und keine an der
    # Preishistorie.
    #
    # Der erste Anlauf verlangte vier verschiedene Daten aus
    # `geraete_preise.jsonl`. Das ist die falsche Quelle: die Datei traegt nur
    # AENDERUNGSpunkte (geraete_store.py, Modulkopf) - ein unveraenderter
    # Preis schreibt keine Zeile. Ein Geraet, das ein halbes Jahr stabil im
    # Regal steht, haette damit einen einzigen Punkt und faellt fuer immer
    # durch; eines mit vier Verfuegbarkeits-Ausschlaegen in 22 Tagen kaeme
    # rein. Genau verkehrt herum: die Sektion zeigte bevorzugt das Rauschen.
    #
    # `first_seen` und `last_verified` wachsen dagegen bei JEDEM Lauf, auch
    # wenn sich nichts aendert - sie sind das ehrliche Mass dafuer, wie lange
    # beobachtet wurde. Der Preisverfall misst gegen `erstpreis_am`, also
    # gegen seinen eigenen Ausgangspunkt.
    def _spanne(von, bis) -> Optional[int]:
        a, b = _datum(von), _datum(bis)
        return None if a is None or b is None or b < a else (b - a).days

    # Ein MESSTERMIN ist ein Lauf, kein Preiswechsel. Wie oft eine Listung
    # angesehen wurde, weiss die Laufbilanz ihres Anbieters; die
    # Preishistorie weiss es nicht, sie schweigt bei unveraendertem Preis.
    # Ohne Bilanz (aeltere Bestaende, Tests) wird die Zahl nicht erfunden,
    # sondern die Termine-Bedingung entfaellt - die Spanne gilt weiter.
    #
    # GEZAEHLT WIRD JE LISTUNG, nicht je Anbieter (siehe den Block bei
    # MIND_TERMINE_JE_GERAET): ein Prueftermin des Anbieters zaehlt nur, wenn
    # er INNERHALB des Beobachtungsfensters dieser Listung liegt.
    laeufe_je_anbieter = laeufe_je_anbieter or {}
    termine_je_anbieter = termine_je_anbieter or {}

    punkte_je_listung: dict[str, set] = {}
    for p in punkte:
        lid, tag = p.get("listung_id"), _datum(p.get("datum"))
        if lid and tag is not None:
            punkte_je_listung.setdefault(lid, set()).add(tag)

    termine_daten = {
        name: sorted({d for d in (_datum(t) for t in (tage or [])) if d})
        for name, tage in termine_je_anbieter.items()}

    def _messtage(eintrag) -> int:
        """Verschiedene Tage, an denen DIESE Listung gemessen wurde."""
        tage = set(punkte_je_listung.get(eintrag.get("id") or "", ()))
        for feld in ("erstpreis_am", "last_verified"):
            tag = _datum(eintrag.get(feld))
            if tag is not None:
                tage.add(tag)
        # Das Fenster der Listung. Fehlt eine Kante, bleibt sie offen - eine
        # geratene Grenze waere schlimmer als eine fehlende.
        von = _datum(eintrag.get("first_seen")) or (min(tage) if tage else None)
        bis = _datum(eintrag.get("last_verified")) or (max(tage) if tage else None)
        for tag in termine_daten.get(eintrag.get("anbieter")) or ():
            if (von is None or tag >= von) and (bis is None or tag <= bis):
                tage.add(tag)
        return len(tage)

    def _oft_genug(eintrag) -> bool:
        if not termine_je_anbieter and not laeufe_je_anbieter:
            return True
        # Die TERMINE zaehlen je Listung und nur im eigenen Fenster - das ist
        # die Aenderung vom 31.08.2026. Die LAUFZAHL bleibt daneben ein
        # Boden, und das ist Absicht: sie ist die einzige Auskunft, die einen
        # Lauf ueberlebt, dessen Bestaetigung ein spaeterer ueberschrieben
        # hat (`last_verified` behaelt nur den juengsten). Ohne sie faellt
        # genau die Ware durch, die seit einem Jahr unveraendert im Regal
        # steht - der Fehler, den G0 am 28.08.2026 behoben hat.
        #
        # Der Unterschied zur alten Rechnung sitzt in der anderen Haelfte:
        # `len(termine_je_anbieter[name])` gab JEDER Listung des Anbieters
        # dieselbe Zahl. Im Bestand vom 31.08.2026 waren das fuer alle 140
        # mobilcom-debitel-Listungen fuenf Termine - auch fuer die, die es
        # erst seit dem vorletzten davon gibt.
        laeufe = int(laeufe_je_anbieter.get(eintrag.get("anbieter"), 0) or 0)
        return max(_messtage(eintrag), laeufe) >= MIND_TERMINE_JE_GERAET

    def _belastbar(eintrag) -> bool:
        """Vier Messtermine ueber mindestens 21 Tage - die eine Schwelle,
        die jede Lifecycle-Zeile nehmen muss. Auch die Nachfolger-Zeile:
        bis zum 31.08.2026 lief sie durch KEIN Gatter und war damit die
        einzige Sektion, die aus zwei Messpunkten eine Aussage machte."""
        tage = listungsdauer(eintrag)
        return (tage is not None and tage >= MIND_TAGE_JE_GERAET
                and _oft_genug(eintrag))

    dauern = []
    for e in eintraege:
        tage = listungsdauer(e)
        # Eine Zeile "0 Tage" ist kein Messergebnis, sondern der Beweis, dass
        # noch nicht lange genug gemessen wurde.
        if not _belastbar(e):
            continue
        g = katalog.nach_id(e.get("device_id"))
        dauern.append({
            "device_id": e.get("device_id"),
            "modell": g.modell if g else e.get("device_id"),
            "anbieter": e.get("anbieter"),
            "tage": tage,
            "status": e.get("status"),
        })

    verfaelle = []
    for e in eintraege:
        v = preisverfall(e)
        if v is None:
            continue
        beobachtet = _spanne(e.get("erstpreis_am"), e.get("last_verified"))
        if (beobachtet is None or beobachtet < MIND_TAGE_JE_GERAET
                or not _oft_genug(e)):
            # "+0.0 % seit gestern" ist keine Preisentwicklung.
            continue
        g = katalog.nach_id(e.get("device_id"))
        verfaelle.append({**v, "device_id": e.get("device_id"),
                          "modell": g.modell if g else e.get("device_id"),
                          "anbieter": e.get("anbieter")})
    verfaelle.sort(key=lambda v: v["prozent"])

    # Duenn ist die Basis, solange KEINE Kennzahl etwas hergibt.
    duenn = not dauern and not verfaelle

    # Der Nachfolger-Effekt, je (Geraet, Anbieter) und hinter derselben
    # Schwelle wie alles andere. Die Preisspalten koennen leer bleiben, die
    # Verweildauer nicht - sie ist die Zahl, wegen der die Sektion dasteht
    # (Modulkopf, Regel 3).
    gruppen: dict[tuple, list] = {}
    for e in eintraege:
        gid = e.get("device_id")
        if not gid:
            continue
        gruppen.setdefault((gid, e.get("anbieter") or ""), []).append(e)

    effekte = []
    for (gid, name), gruppe in sorted(gruppen.items()):
        if not any(_belastbar(e) for e in gruppe):
            continue
        verweil = verweildauer_nach_nachfolger(gruppe, katalog)
        if verweil is None:
            continue
        preis = nachfolger_effekt(gid, katalog, punkte, heute, anbieter=name)
        g = katalog.nach_id(gid)
        effekte.append({**(preis or _leere_preisspalten()), **verweil,
                        "modell": g.modell if g else gid})

    # Zahlwoerter beugen, Umlaute benutzen. Die alte Fassung schrieb an
    # prominenter Stelle "seit 1 Wochen" und "Messpunkte ueber 85 Listungen".
    def _n(zahl: int, eins: str, viele: str) -> str:
        return f"{zahl} {eins if zahl == 1 else viele}"

    seit = min(daten).strftime("%d.%m.%Y") if daten else ""
    if duenn:
        hinweis = (f"Datenbasis noch dünn: Preisverlauf wird seit dem {seit} "
                   f"erfasst" if seit
                   else "Datenbasis noch dünn: Preisverlauf wird noch nicht erfasst")
        # BEIDE Zahlen: wie lange schon, und wie lange noch. Ein Hinweis, der
        # nur "noch zu duenn" sagt, ist eine Ausrede statt einer Auskunft.
        # Bei einem einzigen Messtermin ist die Spanne null - und "0 Tage"
        # liest sich wie die Nullzeilen, die diese Schwelle gerade
        # abgeschafft hat.
        spanne = (f" – {_n(beobachtungstage, 'Tag', 'Tage')}"
                  if beobachtungstage else "")
        hinweis += (f"{spanne}, bisher "
                    f"{_n(len(termine), 'Messtermin', 'Messtermine')}. "
                    f"Belastbare Aussagen zu Verweildauer und Preisverfall gibt "
                    f"es ab etwa {MIND_WOCHEN} Wochen; bis dahin steht hier "
                    f"keine Zahl, die noch keine ist.")
    else:
        hinweis = (f"Preisverlauf seit {_n(wochen, 'Woche', 'Wochen')} "
                   f"beobachtet, {_n(len(termine), 'Messtermin', 'Messtermine')} "
                   f"über {_n(len(dauern), 'Listung', 'Listungen')}.")

    return {
        "duenn": duenn,
        "punkte": len(punkte),
        "termine": len(termine),
        "wochen": wochen,
        "hinweis": hinweis,
        "dauern": sorted(dauern, key=lambda d: -d["tage"]),
        "verfaelle": verfaelle,
        # Ein Trend wird nur ausgewiesen, wenn die Datenbasis ihn traegt.
        # Sonst steht die Messung da, aber nicht die Behauptung.
        "trends": [] if duenn else verfaelle[:12],
        "nachfolger": effekte,
        "portfolio": portfolio_tiefe(eintraege, katalog),
    }
