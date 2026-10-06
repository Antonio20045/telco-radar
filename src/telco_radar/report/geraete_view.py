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

from ..geraete_model import (
    STATUS_AKTIV,
    STATUS_AUSGELISTET,
    STATUS_VERMUTLICH,
    ratenhinweis_aus_eintrag,
    serie_aus_modell,
)
from . import (
    geraete_alarme,
    geraete_bereinigung,
    geraete_pruefung,
    geraete_tco_karten,
    geraete_tco_view,
    geraete_vergleich,
    geraete_verlauf,
    geraete_zeitreihe,
)
from . import geraete_notbremse as notbremse

from .geraete_laufzeit import LAUFZEIT_STANDARD, ansicht
from .geraete_tco_band import _MONATE, band_label
from ..analyze import geraete_lifecycle
from ..analyze.tco_store import TcoDB

from ..tco_model import TCO_HORIZONT, zeitraum_vergleichbar
from ..tarif_bezug import Tarifbestand
from .ausfall import Ausfall
from ..analyze.geraete_store import (
    GELESEN,
    GeraeteDB,
    Preishistorie,
    TEILGELESEN,
    tag_de,
)

log = logging.getLogger(__name__)


_SICHTBAR = (STATUS_AKTIV, STATUS_VERMUTLICH)

FENSTER_TAGE = 14
ZEITREIHE_TEIL = "Zeitreihe der Geräteseite"

VORLAUF_TAGE = 28

LIFECYCLE_SICHTBAR = 6

NACHFOLGER_SICHTBAR = 0

EIGEN = ("vodafone",)

SCHWELLE_ANBIETER = 3
SCHWELLE_HERSTELLER = 2
SCHWELLE_SKUS = 20


def schwelle_erreicht(anbieter: int, skus: int, hersteller: int) -> bool:
    """Darf die Seite in die Navigation? Eine Stelle, kein zweiter Ort."""
    return (
        anbieter >= SCHWELLE_ANBIETER
        and skus >= SCHWELLE_SKUS
        and hersteller >= SCHWELLE_HERSTELLER
    )


SEGMENT_LABEL = {
    "flagship": "Flaggschiff",
    "premium": "Premium",
    "mid": "Mittelklasse",
    "entry": "Einstieg",
    "": "ohne Segment",
}


def _ist_eigen(anbieter: str) -> bool:
    return (anbieter or "").strip().lower() in EIGEN


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


def _nachfolger_leer_hinweis(eintraege: list, katalog, nachfolger: list) -> str:
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

    abstand = grenze - laengste
    if abstand > 0:
        dauer_satz = (
            f"Der Abstand zur nötigen Beobachtungsdauer beträgt "
            f"heute noch {abstand} {'Tag' if abstand == 1 else 'Tage'}."
        )
    else:
        dauer_satz = (
            "Die nötige Beobachtungsdauer ist für mindestens eine "
            "Listung bereits erreicht."
        )

    geraete_ids = sorted({e.get("device_id") for e in eintraege if e.get("device_id")})
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
            f"Katalog."
        )

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
        beleg = (
            (ende - beginn).days
            if beginn is not None and ende is not None and ende >= beginn
            else None
        )
        ergebnis.append({**n, "beobachtet_tage": beleg})
    return ergebnis


def _auffaellig(
    eintraege: list, historie: Preishistorie, katalog, heute: str, laeufe: int = 0
) -> dict:
    """Die groessten Bewegungen DIESES Zeitraums - aus den Deltas gerechnet.

    DER BEZUG IST DIE MESSUNG, NICHT DER BERICHTSTAG. Der Geraetezweig laeuft
    naechtlich und committet seinen Stand; der Bericht erscheint zweimal die
    Woche. Die Geraetedaten sind damit REGELMAESSIG neuer als `heute` - am
    11.08.2026 gemessen: Bestand vom 11., letzter Bericht vom 8. Weil das
    Fenster nur zurueckschaut, fiel jede Aenderung heraus, und die Sektion
    stand leer da, obwohl frische Daten vorlagen. Als Bezug gilt deshalb der
    spaetere der beiden Tage.
    """
    juengste = sorted(
        d for d in (_tag(p.get("datum")) for p in historie.alle_punkte()) if d
    )
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
        bewegungen.append(
            {
                "modell": g.modell if g else e.get("device_id"),
                "anbieter": e.get("anbieter"),
                "von": alt,
                "auf": neu,
                "delta": round(neu - alt, 2),
                "prozent": round((neu - alt) / alt * 100.0, 1),
                "datum": reihe[-1].get("datum", ""),
                "url": e.get("quelle_url", ""),
            }
        )
    bewegungen.sort(key=lambda b: -abs(b["delta"]))

    neu_gelistet = [e for e in eintraege if _im_fenster(e.get("first_seen", ""), heute)]
    verschwunden = [
        e
        for e in eintraege
        if e.get("status") == STATUS_AUSGELISTET
        and _im_fenster(e.get("ended_since", ""), heute)
    ]

    neu_geraete = {e.get("device_id") for e in neu_gelistet if e.get("device_id")}
    weg_geraete = {e.get("device_id") for e in verschwunden if e.get("device_id")}

    erlaubt = set()
    for b in bewegungen:
        erlaubt.update({abs(b["delta"]), b["von"], b["auf"], abs(b["prozent"])})
        erlaubt |= zahlen_der_namen(b["modell"], b["anbieter"])
    erlaubt.update(
        {
            len(neu_gelistet),
            len(verschwunden),
            len(bewegungen),
            len(neu_geraete),
            len(weg_geraete),
        }
    )

    ohne_vorlauf = laeufe < 2

    seit = juengste[0] if juengste else None
    bezug_tag = _tag(heute)
    vorlauf_tage = (
        (bezug_tag - seit).days if seit and bezug_tag and bezug_tag >= seit else 0
    )
    kurzer_vorlauf = vorlauf_tage < VORLAUF_TAGE

    saetze = []
    if ohne_vorlauf:
        for b in bewegungen[:5]:
            richtung = "günstiger" if b["delta"] < 0 else "teurer"
            saetze.append(
                f"{b['modell']} bei {b['anbieter']}: "
                f"{euro(abs(b['delta']))} {richtung} "
                f"({euro(b['von'])} auf {euro(b['auf'])})."
            )
        if neu_geraete:
            saetze.append(
                f"{len(neu_geraete)} Gerät"
                f"{'e' if len(neu_geraete) != 1 else ''} erstmals "
                f"erfasst – es gibt noch keinen früheren Stand, gegen "
                f"den sich vergleichen ließe."
            )
    elif kurzer_vorlauf and (neu_geraete or bewegungen or weg_geraete):
        wieviel = len(neu_geraete)
        kopf = f"Seit dem {seit.day}.{seit.month}. " if seit else "Bisher "
        satz = (
            f"{kopf}{'wurde' if wieviel == 1 else 'wurden'} {wieviel} "
            f"Gerät{'' if wieviel == 1 else 'e'} erstmals erfasst; "
        )
        if not bewegungen:
            satz += "eine Preisänderung ist dabei nicht aufgefallen."
        else:
            teile = [
                f"{b['modell']} bei {b['anbieter']}, "
                f"{euro(b['von'])} → {euro(b['auf'])}"
                for b in bewegungen[:3]
            ]
            wieviele = (
                "eine Preisänderung ist aufgefallen"
                if len(bewegungen) == 1
                else f"{len(bewegungen)} Preisänderungen sind aufgefallen"
            )
            satz += wieviele + ": " + "; ".join(teile)
            if len(bewegungen) > 3:
                erlaubt.add(len(bewegungen) - 3)
                satz += f" und {len(bewegungen) - 3} weitere"
            satz += "."
        saetze.append(satz)
        if weg_geraete:
            saetze.append(
                f"{len(weg_geraete)} "
                f"Gerät{'' if len(weg_geraete) == 1 else 'e'} "
                f"{'ist' if len(weg_geraete) == 1 else 'sind'} aus dem "
                f"Portfolio gefallen."
            )
    else:
        for b in bewegungen[:5]:
            richtung = "günstiger" if b["delta"] < 0 else "teurer"
            saetze.append(
                f"{b['modell']} bei {b['anbieter']}: "
                f"{euro(abs(b['delta']))} {richtung} "
                f"({euro(b['von'])} auf {euro(b['auf'])})."
            )
        if neu_geraete:
            saetze.append(
                f"{len(neu_geraete)} Gerät{'e' if len(neu_geraete) != 1 else ''} "
                f"neu im Regal."
            )
        if weg_geraete:
            saetze.append(
                f"{len(weg_geraete)} Gerät{'e' if len(weg_geraete) != 1 else ''} "
                f"aus dem Portfolio gefallen."
            )

    if kurzer_vorlauf and not ohne_vorlauf and seit:
        erlaubt |= zahlen_im_text(f"{seit.day}.{seit.month}.")

    geprueft = [s for s in saetze if pruefe_zahlen(s, erlaubt)]
    if len(geprueft) != len(saetze):
        log.warning(
            "Geraeteradar: %d Satz/Saetze mit ungedeckten Zahlen verworfen",
            len(saetze) - len(geprueft),
        )

    return {
        "saetze": geprueft,
        "neu_gelistet": len(neu_gelistet),
        "neu_gelistet_geraete": len(neu_geraete),
        "verschwunden": len(verschwunden),
        "verschwunden_geraete": len(weg_geraete),
        "bewegungen": [] if kurzer_vorlauf else bewegungen[:12],
        "neu": [
            {
                "modell": (
                    katalog.nach_id(e.get("device_id")).modell
                    if katalog.nach_id(e.get("device_id"))
                    else e.get("device_id")
                ),
                "anbieter": e.get("anbieter"),
                "url": e.get("quelle_url", ""),
            }
            for e in neu_gelistet[:12]
        ],
        "weg": [
            {
                "modell": (
                    katalog.nach_id(e.get("device_id")).modell
                    if katalog.nach_id(e.get("device_id"))
                    else e.get("device_id")
                ),
                "anbieter": e.get("anbieter"),
                "seit": e.get("ended_since", ""),
            }
            for e in verschwunden[:12]
        ],
        "hat_daten": bool(geprueft or (bewegungen and not kurzer_vorlauf)),
        "ohne_vorlauf": ohne_vorlauf,
        "kurzer_vorlauf": kurzer_vorlauf,
        "vorlauf_tage": vorlauf_tage,
    }


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
    return (
        0 if z["zustand"] == "neu" else 1,
        _katalog_betrag(z),
        z["anbieter"] or "",
        z["farbe"] or "",
    )


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
    return (
        _katalog_segment_rang(block["segment"]),
        block["serie"] or "",
        0 if gen is not None else 1,
        -(gen or 0),
        block["modell"] or "",
        block["speicher"] or 0,
    )


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
    zustand = geraete_bereinigung.zustand_der_zeile(e)
    return {
        "modell": g.modell if g else (e.get("device_id") or "?"),
        "hersteller": g.hersteller if g else "",
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


TCO_LEER_KEIN_BUNDEL = "kein Bündel gemessen"
TCO_LEER_KEIN_VERGLEICHBARES = "kein vergleichbares Bündel gemessen"
TCO_LEER_NUR_ALT = "kein aktueller Bündel-Stand"
TCO_LEER_ANDERE_LAUFZEIT = f"kein Bündel mit {LAUFZEIT_STANDARD} Raten"

TCO_DELTA_LEER_KEINE_REFERENZ = "keine Referenz"
TCO_DELTA_GRUND_KEINE_REFERENZ = (
    "Vodafone listet dieses Modell nicht - deshalb ist kein Abstand "
    "berechenbar (die Referenz fehlt)"
)
TCO_DELTA_LEER_KEIN_WETTBEWERBER = "kein Wettbewerber-Angebot"
TCO_DELTA_GRUND_KEIN_WETTBEWERBER = (
    "Vodafone listet dieses Modell, aber kein Wettbewerber-Angebot ist "
    "vergleichbar erhoben - deshalb ist kein Abstand berechenbar"
)
TCO_DELTA_GRUND_ANDERE_LAUFZEIT = (
    "Das günstigste Wettbewerber-Angebot trägt einen anderen Zeitraum als "
    "die Vodafone-Referenz - über zwei Laufzeiten gibt es keinen Abstand"
)
TCO_DELTA_LEER_ALTE_REFERENZ = "kein aktueller Referenz-Stand"
TCO_DELTA_GRUND_ALTE_REFERENZ = (
    "Die Vodafone-Referenz ist nicht aktuell erhoben - ein Abstand gegen "
    "sie wäre kein Abstand von heute"
)
TCO_DELTA_LEER_UNBESTIMMT = "Abstand unbestimmt"
TCO_DELTA_GRUND_UNBESTIMMT = (
    "Zu diesem Wettbewerber-Angebot ist kein Abstand zur Vodafone-Referenz gerechnet"
)


def _buendel_je_anbieter_modell(
    buendel: list, eintraege: list, katalog, heute: str = ""
) -> tuple[dict, dict]:
    """Zwei Lesarten derselben Bündel-Aufloesung.

    1. `(Anbieter, modell_schluessel) -> das guenstigste Bündel mit
       Monatspreis`, das zählt (`geraete_notbremse`) - die Monatsangabe "nur
       im Bündel, ab X EUR/Monat" braucht einen Beleg aus `geraete_tco.json`,
       NICHT das `preis_mit_vertrag_ab` der Listung (Belegzwang).
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
                e.get("device_id"), e.get("speicher_gb")
            )
            geraet_je_sku[sku] = (e.get("device_id") or "", e.get("speicher_gb"))
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
        geraet_je_mid.setdefault(mid, {"device_id": geraet[0], "speicher": geraet[1]})
        if not notbremse.felder_aus_satz(b, heute)["zaehlt"]:
            continue
        monat = b.get("buendel_monatlich")
        if monat is None:
            tarif, rate = b.get("tarif_monatlich"), b.get("geraet_monatsrate")
            if tarif is None or rate is None:
                continue
            monat = round(float(tarif) + float(rate), 2)
        monat = float(monat)
        schluessel = (geraete_tco_karten.normalisiere(b.get("anbieter", "")), mid)
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
        saetze.append(
            {
                "sku_id": e.get("sku_id") or "",
                "anbieter": e.get("anbieter") or "",
                "buendel_monatlich": monat,
                "tarif_name": (e.get("tarif_referenz") or "").strip(),
                "quelle_url": e.get("quelle_url") or "",
                "abgerufen_am": e.get("abgerufen_am") or "",
            }
        )
    return saetze


def _tco_leer(grund: str) -> dict:
    """Die TCO-Felder einer Modellzeile ohne bestes Bündel, mit benanntem Grund."""
    return {
        "tco_ab": None,
        "tco_anbieter": None,
        "tco_monat": None,
        "tco_band": None,
        "tco_band_label": "",
        "tco_beleg": None,
        "tco_leer": grund,
        "tco_delta": None,
        "tco_delta_prozent": None,
        "tco_delta_kurz": None,
        "tco_delta_anbieter": None,
        "tco_delta_leer": None,
        "tco_delta_leer_grund": None,
    }


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

    P0-B-h2 und Datenkonzept Geräte Schritt 2: DIE SPALTE IST DIE
    STANDARDANSICHT (24 Raten über `TCO_HORIZONT`, wie ihr Kopf und die
    Vodafone-Referenz). Andere Zahlen werden BENANNT: die Zeile sagt "kein
    Bündel mit 24 Raten", die Δ-Zelle "andere Laufzeit".

    Notbremse (Datenkonzept Geräteradar, Schritt 1): Bester und Traeger
    des Abstands sind nur Karten mit `zaehlt`. Zaehlt keine, nennt die
    Zeile den Zustand der Karte ("Schätzung", "Aktion abgelaufen"), die
    Δ-Zelle ebenso, wenn nur ein nicht zaehlendes fremdes Angebot bleibt.
    """
    if not modell_tco:
        return _tco_leer(TCO_LEER_KEIN_BUNDEL)
    pool = [
        k
        for k in modell_tco.get("karten") or []
        if k.get("vergleichbar")
        and k.get("belastbar")
        and not k.get("naeherung")
        and k.get("gesamt") is not None
    ]
    kandidaten = [k for k in pool if k.get("frisch", True)]
    if not kandidaten:
        return _tco_leer(TCO_LEER_NUR_ALT if pool else TCO_LEER_KEIN_VERGLEICHBARES)
    vergleichbare = [
        k
        for k in kandidaten
        if ansicht(k) == LAUFZEIT_STANDARD
        and zeitraum_vergleichbar(k.get("leitzahl_monate"), TCO_HORIZONT)
    ]
    if not vergleichbare:
        return _tco_leer(TCO_LEER_ANDERE_LAUFZEIT)
    zaehlende = list(filter(notbremse.zaehlt, vergleichbare))
    if not zaehlende:
        gesperrt = min(vergleichbare, key=lambda k: k["gesamt"])
        return _tco_leer(notbremse.gruende([gesperrt]))
    bester = min(zaehlende, key=lambda k: k["gesamt"])
    fremde = [k for k in zaehlende if not k.get("eigen")]
    traeger = (
        bester
        if not bester.get("eigen")
        else (min(fremde, key=lambda k: k["gesamt"]) if fremde else None)
    )
    im_zeitraum = {id(k) for k in zaehlende}
    ohne_abstand = [
        k for k in kandidaten if not k.get("eigen") and id(k) not in im_zeitraum
    ]
    referenz = modell_tco.get("referenz")
    if traeger is not None and traeger.get("delta_kurz"):
        delta_leer, delta_leer_grund = None, None
    elif referenz is None:
        delta_leer = TCO_DELTA_LEER_KEINE_REFERENZ
        delta_leer_grund = TCO_DELTA_GRUND_KEINE_REFERENZ
    elif not geraete_tco_karten.referenz_ist_frisch(referenz, heute):
        delta_leer = TCO_DELTA_LEER_ALTE_REFERENZ
        delta_leer_grund = TCO_DELTA_GRUND_ALTE_REFERENZ
    elif traeger is None and ohne_abstand:
        zustand = (
            min(ohne_abstand, key=lambda k: k["gesamt"]).get("delta_zustand") or {}
        )
        delta_leer = zustand.get("kurz") or geraete_tco_karten.DELTA_ANDERE_LAUFZEIT
        delta_leer_grund = zustand.get("satz") or TCO_DELTA_GRUND_ANDERE_LAUFZEIT
    elif traeger is None:
        delta_leer = TCO_DELTA_LEER_KEIN_WETTBEWERBER
        delta_leer_grund = TCO_DELTA_GRUND_KEIN_WETTBEWERBER
    else:
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
        "tco_delta_anbieter": (
            traeger.get("anbieter")
            if bester.get("eigen") and traeger is not None
            else None
        ),
        "tco_delta_leer": delta_leer,
        "tco_delta_leer_grund": delta_leer_grund,
        "tco_band": bester.get("band"),
        "tco_band_label": band_label(bester.get("band")),
        "tco_beleg": {
            "quelle_url": bester.get("quelle_url", ""),
            "abgerufen_am": bester.get("abgerufen_am", ""),
        },
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
    geordnet = [
        sorted(gruppen[h], key=_katalog_block_schluessel)
        for h in sorted(gruppen, key=lambda h: (h == "", h))
    ]
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
    return min(
        (
            m["ab_preis"]
            for m in katalog_modelle
            if m.get("ab_preis") is not None and not m.get("ab_alt")
        ),
        default=None,
    )


def katalog_modellzeilen(
    eintraege: list,
    katalog,
    tco_modelle=None,
    buendel=None,
    zr_erlaubt: dict | None = None,
    heute: str = "",
) -> list[dict]:
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
    fuer den ab-Preis und die Notbremse der Bündel-Angabe. DIESELBE
    Frische-Definition wie an der Tafel (`geraete_tco_karten.ist_frisch`,
    Clean Code 7) entscheidet, welcher Beleg "ab" stellt und in die Spanne
    zaehlt - ein alter Barpreis ist kein "ab" von heute (gemessen: "ab
    1.299 EUR bei mobilcom-debitel" vom 14.08., 37 Tage; "ab 289 EUR bei
    Medimax" vom 06.09. unterbot ElectronicPartner vom 19.09.). Ohne
    `heute` altert nichts - der Modus der alten Aufrufer und Tests.

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
        buendel, eintraege, katalog, heute
    )
    tco_je_id = {m.get("id"): m for m in (tco_modelle or [])}

    gruppen: dict[str, dict] = {}
    for e in eintraege:
        zeile = _katalog_zeile(e, katalog)
        mid = geraete_tco_karten.modell_schluessel(
            e.get("device_id"), e.get("speicher_gb")
        )
        g = gruppen.get(mid)
        if g is None:
            g = {
                "schluessel": mid,
                "device_id": e.get("device_id") or "",
                "modell": zeile["modell"],
                "hersteller": zeile["hersteller"],
                "generation": zeile["generation"],
                "serie": zeile["serie"],
                "segment": zeile["segment"],
                "speicher": zeile["speicher"],
                "eintraege": [],
                "zeilen": [],
            }
            gruppen[mid] = g
        g["eintraege"].append(e)
        g["zeilen"].append(zeile)

    for mid, geraet in buendel_geraete.items():
        if mid in gruppen:
            continue
        g = katalog.nach_id(geraet["device_id"]) if katalog else None
        gruppen[mid] = {
            "schluessel": mid,
            "device_id": geraet["device_id"],
            "modell": g.modell if g else geraet["device_id"],
            "hersteller": g.hersteller if g else "",
            "generation": g.generation if g else None,
            "serie": serie_aus_modell(g.modell) if g else "",
            "segment": g.segment if g else "",
            "speicher": geraet["speicher"],
            "eintraege": [],
            "zeilen": [],
        }

    ergebnis = []
    for mid, gruppe in gruppen.items():
        zeilen = sorted(gruppe["zeilen"], key=_katalog_zeile_schluessel)
        eintraege_modell = gruppe["eintraege"]

        je_anbieter: dict[str, dict] = {}
        je_anbieter_alt: dict[str, dict] = {}
        for e in eintraege_modell:
            sku = e.get("sku_id") or ""
            for anbieter, beleg in belege.get(sku, {}).items():
                ziel = (
                    je_anbieter_alt
                    if not geraete_tco_karten.ist_frisch(
                        beleg.get("abgerufen_am", ""), heute
                    )
                    else je_anbieter
                )
                bisher = ziel.get(anbieter)
                if bisher is None or beleg["betrag"] < bisher["betrag"]:
                    ziel[anbieter] = beleg
        auswahl = je_anbieter or je_anbieter_alt
        ab_beleg = min(auswahl.values(), key=lambda b: b["betrag"]) if auswahl else None
        ab_alt = bool(je_anbieter_alt) and not je_anbieter

        spanne: list = []
        if len(auswahl) >= 2 and ab_beleg is not None:
            betraege = [b["betrag"] for b in auswahl.values()]
            von, bis = min(betraege), max(betraege)
            abstand = bis - von
            if abstand >= geraete_vergleich.WESENTLICH_EURO or (
                von > 0 and abstand / von * 100 >= geraete_vergleich.WESENTLICH_PROZENT
            ):
                spanne = [round(von, 2), round(bis, 2)]

        anbieter_mit_buendel = {}
        for z in zeilen:
            if z["preis"] is not None or z["zuzahlung"] is not None:
                continue
            treffer = buendel_je.get(
                (geraete_tco_karten.normalisiere(z["anbieter"] or ""), mid)
            )
            if treffer is None:
                continue
            z["buendel_monat"] = treffer["monat"]
            z["buendel_tarif"] = treffer["tarif"]
            z["buendel_url"] = treffer["quelle_url"]
            z["buendel_abgerufen_am"] = treffer["abgerufen_am"]
            anbieter_mit_buendel[treffer["anbieter"]] = treffer

        buendel_angabe = None
        if ab_beleg is None:
            pool = (
                list(anbieter_mit_buendel.values())
                if anbieter_mit_buendel
                else [v for (_, m), v in buendel_je.items() if m == mid]
            )
            if pool:
                buendel_angabe = min(pool, key=lambda b: b["monat"])

        name = gruppe["modell"]
        if gruppe["speicher"]:
            name = f"{name} {int(gruppe['speicher'])} GB"
        tco_felder = _tco_spalte(tco_je_id.get(mid), heute)

        listen_anbieter = sorted({z["anbieter"] for z in zeilen if z["anbieter"]})
        if not listen_anbieter:
            listen_anbieter = sorted(
                {v["anbieter"] for (_, m), v in buendel_je.items() if m == mid}
            )

        ergebnis.append(
            {
                "schluessel": mid,
                "zr": bool(zr_erlaubt and zr_erlaubt.get(mid)),
                "hat_buendel": mid in buendel_geraete,
                "device_id": gruppe["device_id"],
                "modell": gruppe["modell"],
                "hersteller": gruppe["hersteller"],
                "titel": geraete_tco_karten.titel(gruppe["hersteller"], name),
                "generation": gruppe["generation"],
                "serie": gruppe["serie"],
                "segment": gruppe["segment"],
                "speicher": gruppe["speicher"],
                "ab_preis": ab_beleg["betrag"] if ab_beleg else None,
                "ab_anbieter": ab_beleg["anbieter"] if ab_beleg else None,
                "ab_beleg": ab_beleg,
                "ab_alt": ab_alt,
                "ab_alt_marke": (
                    geraete_tco_karten.alt_marke_fuer(ab_beleg.get("abgerufen_am", ""))
                    if ab_alt and ab_beleg
                    else ""
                ),
                "anbieterzahl": len(listen_anbieter),
                "anbieter": listen_anbieter,
                "farben": sorted({z["farbe"] for z in zeilen if z["farbe"]}),
                "spanne": spanne,
                "nur_buendel": buendel_angabe is not None,
                "buendel_monat": buendel_angabe["monat"] if buendel_angabe else None,
                "buendel_anbieter": (
                    buendel_angabe["anbieter"] if buendel_angabe else None
                ),
                "buendel_tarif": buendel_angabe["tarif"] if buendel_angabe else "",
                "buendel_beleg": (
                    {
                        "quelle_url": buendel_angabe["quelle_url"],
                        "abgerufen_am": buendel_angabe["abgerufen_am"],
                    }
                    if buendel_angabe
                    else None
                ),
                **tco_felder,
                "zeilen": zeilen,
                "listungen": len(zeilen),
            }
        )

    ergebnis = _interleave_modelle_je_hersteller(ergebnis)
    sichtbar_zaehler = 0
    for z in ergebnis:
        z["zeilen_rest"] = sichtbar_zaehler >= KATALOG_SICHTBAR
        if not z["zeilen_rest"]:
            sichtbar_zaehler += 1
    return ergebnis


def _heute_luecke(db: GeraeteDB, name: str, bezugstag, liefert: bool) -> bool:
    """Behauptet der Bestand etwas Gruenes, das heute niemand gemessen hat?

    Zwei Haelften, und beide gehoeren hierher und nicht in die Vorlage -
    sonst steht dieselbe Entscheidung an zwei Stellen (Clean Code 7):

      * WURDE HEUTE GELESEN? Aus derselben Definition, die der Waechter
        benutzt (`GeraeteDB.lesezustand` am Bezugstag). Ein Teillauf
        zaehlt mit - was da ist, ist gesehen worden; ein Lesefehler und
        ein nicht angefasster Anbieter nicht, und ein Anbieter ohne
        Messtag am Bezugstag erst recht nicht.
      * BEHAUPTET DIE ZEILE SONST ETWAS GRUENES? Nur dann ersetzt der
        dritte Zustand sie. "Nicht angebunden" und "angebunden, ohne
        Fund" sind gemessene Dauerzustaende und sagen mehr als ein
        Tagesbefund; ein gruener Punkt fuer einen Anbieter, den der Lauf
        heute nicht erreicht hat, ist dagegen eine Entwarnung, die
        niemand gemessen hat (S2-2).
    """
    if not liefert:
        return False
    return db.lesezustand(name, bezugstag) not in (GELESEN, TEILGELESEN)


def _liefert_heute(satz: dict) -> bool:
    """Steht in der Stand-Spalte dieser Zeile der GRUENE Punkt?

    Die EINE Definition (Clean Code 7), aus der die Vorlage ihren Punkt
    und die Kennzahl "N liefern Geräte" ihre Zahl nimmt. Vorher zaehlte
    die Kennzahl aus dem BESTAND (`liefert`): ueber genau den Zeilen, die
    "heute nicht gelesen" tragen, stand als groesste Zahl des Bereichs
    "10 liefern Geräte" - die Entwarnung, die der Punkt nicht mehr gibt,
    gab die Kennzahl.

    Drei Stufen, dieselbe Reihenfolge wie in der Vorlage: ein Alarm und
    eine heute nicht gemessene Zeile sind kein "liefert".
    """
    if satz.get("abdeckung") or satz.get("heute_luecke"):
        return False
    return bool(satz.get("liefert"))


def _heute_satz(bilanz: dict) -> str:
    """Warum steht in der Stand-Spalte kein gruener Punkt?

    Die gemessene Auskunft und kein Wort mehr: der letzte VOLLSTAENDIGE
    Lauf dieses Anbieters. Er steht da, weil "heute nicht gelesen" allein
    die naechste Frage offen laesst - seit wann? Genau diese Zahl war der
    Befund, mit dem der Waechter angefangen hat (Telekom: letzter
    vollstaendiger Lauf am 15.09., Seite trotzdem gruen).
    """
    letzter = str(bilanz.get("letzter_lauf") or "")
    if letzter:
        return f"zuletzt vollständig gelesen am {tag_de(letzter)}"
    return "bisher kein vollständiger Lauf"


def _tote_satz(bilanz: dict) -> str:
    """Wie viele Adressen dieser Quelle ins Leere zeigen - oder nichts.

    Die Zahl steht auf der Seite und nicht nur im Log, weil sie die
    einzige Erklaerung dafuer ist, dass ein Anbieter mit Luecken trotzdem
    als vollstaendig gelesen gilt (`collect.geraete._einstieg_gelesen`).
    Der Satz entsteht HIER und nicht in der Vorlage - dieselbe Regel wie
    beim Alarm (Clean Code 7).

    `None` heisst "in diesem Lauf wurde keine Produktseite versucht" und 0
    heisst "versucht, keine war tot". Beide sagen nichts Meldenswertes und
    ergeben deshalb keinen Satz; eine Null auf der Seite waere eine
    Angabe, die niemand braucht (Antonios Stil: wenig Text).
    """
    tote = bilanz.get("tote_adressen")
    if not tote:
        return ""
    if int(tote) == 1:
        return "1 verlinkte Produktseite gibt es nicht mehr"
    return f"{int(tote)} verlinkte Produktseiten gibt es nicht mehr"


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
    alarme = {a.anbieter: a.als_dict() for a in db.ausfall_alarme()}
    bezugstag = db.letzter_messtag()
    zeilen, ohne_hardware = [], []
    for a in sorted(quellen.anbieter, key=lambda x: (x.rang, x.name)):
        vermarktung = db.hardware_vermarktung(a.name)
        if a.methode == "kein_hardware":
            vermarktung = "nein"
        satz = {
            "name": a.name,
            "typ": a.typ,
            "netz": a.netz,
            "gruppe": a.gruppe,
            "rang": a.rang,
            "methode": a.methode,
            "eigen": a.eigen,
            "aktiv": a.aktiv,
            "crawlbar": a.crawlbar,
            "grund": a.grund,
            "hinweis": a.hinweis,
            "einstiege": [
                {"url": e.url, "label": e.label, "kind": e.kind}
                for e in a.crawled_einstiege
            ],
            "geraete": sum(1 for e in eintraege if e.get("anbieter") == a.name),
            "liefert": a.name in mit_daten,
            "heute_luecke": _heute_luecke(db, a.name, bezugstag, a.name in mit_daten),
            "hardware_vermarktung": vermarktung,
            "bilanz": db.laufbilanz(a.name),
            "heute_satz": _heute_satz(db.laufbilanz(a.name)),
            "tote_satz": _tote_satz(db.laufbilanz(a.name)),
            "abdeckung": alarme.get(a.name),
        }
        satz["liefert_heute"] = _liefert_heute(satz)
        satz["zustand"] = (
            "liefert"
            if satz["liefert"]
            else "ohne_hardware"
            if vermarktung == "nein"
            else "ohne_daten"
        )
        if vermarktung == "nein":
            ohne_hardware.append(satz)
        else:
            zeilen.append(satz)

    for name in sorted(n for n in mit_daten if n and n not in bekannt):
        fremd = {
            "name": name,
            "typ": "",
            "netz": "",
            "gruppe": "",
            "rang": 999,
            "methode": "nicht konfiguriert",
            "eigen": False,
            "aktiv": False,
            "crawlbar": False,
            "grund": "Steht mit Daten in der Datenbank, aber nicht in "
            "config/geraete_quellen.yaml - umbenannt oder entfernt. "
            "Die Bestandseinträge bleiben, werden aber nicht mehr "
            "aufgefrischt.",
            "hinweis": "",
            "einstiege": [],
            "geraete": sum(1 for e in eintraege if e.get("anbieter") == name),
            "liefert": True,
            "hardware_vermarktung": "ja",
            "heute_luecke": _heute_luecke(db, name, bezugstag, True),
            "zustand": "liefert",
            "bilanz": db.laufbilanz(name),
            "heute_satz": _heute_satz(db.laufbilanz(name)),
            "tote_satz": _tote_satz(db.laufbilanz(name)),
            "abdeckung": alarme.get(name),
        }
        fremd["liefert_heute"] = _liefert_heute(fremd)
        zeilen.append(fremd)

    return {
        "zeilen": zeilen,
        "ohne_hardware": ohne_hardware,
        "liefernd": sum(1 for z in zeilen if z["liefert_heute"]),
        "aufgefuehrt": len(zeilen),
        "liefernd_konfiguriert": sum(
            1 for z in zeilen if z["liefert"] and z["name"] in bekannt
        ),
        "ohne_daten": sum(1 for z in zeilen if z["zustand"] == "ohne_daten"),
        "ohne_hardware_zahl": len(ohne_hardware),
        "nicht_konfiguriert": sum(1 for z in zeilen if z["name"] not in bekannt),
        "konfiguriert": len(quellen.anbieter),
        "unbekannt": [n for n in sorted(mit_daten) if n and n not in bekannt],
        "seiten": quellen.seiten_zahl,
    }


def leer(fehler: str = "") -> dict:
    """Der Notzustand: die Seite entsteht trotzdem und sagt, was los ist.

    Ohne ihn liess ein einziger kaputter Eintrag beide Seiten ganz
    verschwinden - und weil `site/` committet wird, blieb live die Fassung
    der Vorwoche stehen. Ein Totalausfall, der wie ein gruener Lauf aussieht.
    """
    return {
        "hat_daten": False,
        "stand": "",
        "abgerufen_bis": "",
        "abgerufen_ab": "",
        "fenster_tage": FENSTER_TAGE,
        "db_lesbar": not fehler,
        "fehler": fehler,
        "bilanz": {
            "geraete": 0,
            "listungen": 0,
            "skus": 0,
            "anbieter": 0,
            "ausgelistet": 0,
            "preispunkte": 0,
            "hersteller": 0,
            "schwelle_erreicht": False,
        },
        "alarme": geraete_alarme.leer(),
        "segmente": [],
        "segment_label": SEGMENT_LABEL,
        "speicherstufen": [],
        "verlauf": geraete_verlauf.leer(),
        "tco": geraete_tco_view.leer(),
        "zeitreihe": geraete_zeitreihe.leer(),
        "ausfaelle": [],
        "katalog_modelle": [],
        "katalog_ab_preis": None,
        "katalog_sichtbar": KATALOG_SICHTBAR,
        "lifecycle_sichtbar": LIFECYCLE_SICHTBAR,
        "nachfolger_sichtbar": NACHFOLGER_SICHTBAR,
        "auffaellig": {
            "hat_daten": False,
            "saetze": [],
            "bewegungen": [],
            "neu": [],
            "weg": [],
            "kurzer_vorlauf": True,
            "vorlauf_tage": 0,
        },
        "bestand": [],
        "alle_punkte": [],
        "katalog_obj": None,
        "export": {
            "stand": "",
            "aktuell": {"datei": "", "zeilen": 0, "bytes": 0},
            "historie": {"datei": "", "zeilen": 0, "bytes": 0},
        },
        "vergleich": {
            "hat_daten": False,
            "standard": "ohne_vertrag",
            "ohne_vertrag": {
                "zeilen": [],
                "ohne_vodafone": [],
                "hat_daten": False,
                "hat_vodafone": False,
                "mit_vorteil": 0,
                "ohne_vorteil": 0,
                "ohne_vodafone_gesamt": 0,
                "groesste_differenz": None,
                "preisart": "ohne_vertrag",
            },
            "mit_vertrag": {
                "zeilen": [],
                "ohne_vodafone": [],
                "hat_daten": False,
                "hat_vodafone": False,
                "mit_vorteil": 0,
                "ohne_vorteil": 0,
                "ohne_vodafone_gesamt": 0,
                "groesste_differenz": None,
                "preisart": "mit_vertrag",
            },
        },
        "lifecycle": {
            "duenn": True,
            "punkte": 0,
            "wochen": 0,
            "hinweis": "",
            "dauern": [],
            "verfaelle": [],
            "trends": [],
            "nachfolger": [],
            "nachfolger_hinweis": "",
            "portfolio": [],
        },
        "quellenlage": {
            "zeilen": [],
            "ohne_hardware": [],
            "liefernd": 0,
            "aufgefuehrt": 0,
            "konfiguriert": 0,
            "unbekannt": [],
            "seiten": 0,
        },
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
    return (
        pruefung,
        geraete_bereinigung.bereinige(sichtbar),
        geraete_bereinigung.bereinige(pruefung["sauber"]),
    )


def aufbereiten(state_dir: Path, quellen, katalog, heute: str = "") -> dict:
    """Alles fuer /geraete.html und /geraete-quellen.html."""
    state_dir = Path(state_dir)
    db = GeraeteDB(state_dir / "geraete_db.json")
    historie = Preishistorie(state_dir / "geraete_preise.jsonl")
    tco_db = TcoDB(state_dir / "geraete_tco.json")
    tarifbestand = Tarifbestand.aus_datei(state_dir / "tarife.jsonl")
    alle = db.eintraege()
    sichtbar = [e for e in alle if e.get("status") in _SICHTBAR]

    pruefung, bestand, belastbar = bestand_und_belastbar(sichtbar, katalog)

    laden = {a.name: (a.shop or a.name) for a in getattr(quellen, "anbieter", [])}
    anzeige = {a.name: (a.anzeige or a.name) for a in getattr(quellen, "anbieter", [])}
    anzeige.update(
        {
            (a.shop or a.name): (a.anzeige or a.name)
            for a in getattr(quellen, "anbieter", [])
        }
    )

    punkte_ohne_vertrag = []
    for e in belastbar:
        preis = e.get("preis_ohne_vertrag")
        if preis is None:
            continue
        g = katalog.nach_id(e.get("device_id"))
        speicher = e.get("speicher_gb")
        name = e.get("anbieter")
        punkte_ohne_vertrag.append(
            {
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
                "zustand": e.get("zustand") or "neu",
                "verfuegbarkeit": e.get("verfuegbarkeit", "unbekannt"),
                "url": e.get("quelle_url", ""),
                "abgerufen_am": e.get("abgerufen_am", ""),
                "eigen": _ist_eigen(e.get("anbieter", "")),
                "label": f"{g.modell if g else e.get('device_id')}"
                + (f" · {speicher} GB" if speicher else ""),
            }
        )

    for p in punkte_ohne_vertrag:
        p["serie"] = serie_aus_modell(p.get("modell") or "")
    hoechste: dict[tuple, int] = {}
    for p in punkte_ohne_vertrag:
        if p["generation"] is None:
            continue
        schluessel = (p["hersteller"], p["serie"])
        hoechste[schluessel] = max(hoechste.get(schluessel, 0), p["generation"])
    for p in punkte_ohne_vertrag:
        p["aktuelle_generation"] = p["generation"] is not None and p[
            "generation"
        ] == hoechste.get((p["hersteller"], p["serie"]))

    punkte_alle = historie.alle_punkte()
    termine_je_anbieter: dict[str, list] = {}
    laeufe_je_anbieter: dict[str, int] = {}
    for name in {e.get("anbieter") for e in alle if e.get("anbieter")}:
        termine = set(db.messtermine(name))
        termine.update(
            p.get("datum")
            for p in punkte_alle
            if p.get("anbieter") == name and p.get("datum")
        )
        termine_je_anbieter[name] = sorted(termine)
        laeufe_je_anbieter[name] = int(db.laufbilanz(name).get("laeufe") or 0)
    laeufe = max(
        (
            max(len(t), laeufe_je_anbieter.get(n, 0))
            for n, t in termine_je_anbieter.items()
        ),
        default=0,
    )
    auffaellig = _auffaellig(alle, historie, katalog, heute, laeufe=laeufe)
    lifecycle = geraete_lifecycle.auswertung(
        alle,
        punkte_alle,
        katalog,
        heute,
        laeufe_je_anbieter=laeufe_je_anbieter,
        termine_je_anbieter=termine_je_anbieter,
    )
    lifecycle = {
        **lifecycle,
        "nachfolger": _mit_beobachtungsbeleg(lifecycle["nachfolger"]),
        "nachfolger_hinweis": _nachfolger_leer_hinweis(
            alle, katalog, lifecycle["nachfolger"]
        ),
    }

    abrufdaten = sorted(e.get("abgerufen_am") for e in bestand if e.get("abgerufen_am"))

    def _laeden(menge):
        return {laden.get(e.get("anbieter"), e.get("anbieter")) for e in menge}

    def _hersteller(menge):
        return {
            g.hersteller
            for g in (katalog.nach_id(e.get("device_id")) for e in menge)
            if g and g.hersteller
        }

    erreicht = schwelle_erreicht(
        anbieter=len(_laeden(sichtbar)),
        skus=len({e.get("sku_id") for e in sichtbar}),
        hersteller=len(_hersteller(sichtbar)),
    )

    laeden_mit_daten = _laeden(bestand)
    hersteller_mit_daten = _hersteller(bestand)

    vergleich = geraete_vergleich.beide_preisarten(belastbar, katalog, laeden=laden)
    alarme = geraete_alarme.zeilen(
        vergleich["ohne_vertrag"], pruefung.get("auffaellig")
    )

    tco_heute = _spaeterer_tag(heute, tco_db.updated) if heute else ""
    bestand_heute = _spaeterer_tag(heute, db.updated) if heute else ""
    tco = geraete_tco_view.aufbereiten(
        tco_db.buendel(),
        tco_db.referenzen(),
        belastbar,
        katalog,
        lesbar=tco_db.lesbar,
        tarife=tarifbestand.je_id_aktuell,
        anbieter_typen={a.name: a.typ for a in quellen.anbieter},
        tco_historie=tco_db.historie_lage(),
        heute=tco_heute,
    )
    ausfaelle: list[Ausfall] = []
    try:
        zeitreihe = geraete_zeitreihe.aufbereiten(
            state_dir, tco, tarife=tarifbestand.je_id_aktuell, heute=tco_heute
        )
    except Exception as exc:  # noqa: BLE001
        log.error(
            "Zeitreihen-Aufbereitung gescheitert: %s: %s", type(exc).__name__, exc
        )
        zeitreihe = geraete_zeitreihe.leer()
        ausfaelle.append(Ausfall.aus_ausnahme(ZEITREIHE_TEIL, exc))

    zr_erlaubt = {
        k: b
        for k, b in ((zeitreihe.get("daten") or {}).get("erlaubt") or {}).items()
        if b
    }

    katalog_modelle = katalog_modellzeilen(
        bestand,
        katalog,
        (tco or {}).get("modelle"),
        tco_db.buendel() if tco_db.lesbar else _buendel_aus_listungen(bestand),
        zr_erlaubt=zr_erlaubt,
        heute=bestand_heute,
    )
    katalog_ab_preis = katalog_leitzahl(katalog_modelle)

    katalog_neu = []
    for m in katalog_modelle:
        if not m.get("hat_buendel") or m.get("zr"):
            continue
        belege = sorted(
            b.get("abgerufen_am")
            for b in (m.get("ab_beleg"), m.get("buendel_beleg"))
            if b and b.get("abgerufen_am")
        )
        katalog_neu.append(
            {
                "id": m["schluessel"],
                "titel": m["titel"],
                "datum": _neu_seit(belege[0]) if belege else "",
                "iso": belege[0] if belege else "",
            }
        )
    if isinstance((zeitreihe or {}).get("daten"), dict):
        zeitreihe["daten"]["katalog_neu"] = katalog_neu

    return {
        "tco": tco,
        "zeitreihe": zeitreihe,
        "ausfaelle": ausfaelle,
        "verlauf": geraete_verlauf.aufbereiten(belastbar, historie, katalog),
        "katalog_modelle": katalog_modelle,
        "katalog_ab_preis": katalog_ab_preis,
        "katalog_sichtbar": KATALOG_SICHTBAR,
        "lifecycle_sichtbar": LIFECYCLE_SICHTBAR,
        "nachfolger_sichtbar": NACHFOLGER_SICHTBAR,
        "pruefung": pruefung["zahlen"],
        "pruefbefunde": pruefung["befunde"],
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
            "ausgelistet": sum(
                1 for e in alle if e.get("status") == STATUS_AUSGELISTET
            ),
            "ohne_vorlauf": auffaellig["ohne_vorlauf"],
            "preispunkte": historie.punkte_gesamt,
            "hersteller": len(hersteller_mit_daten),
            "schwelle_erreicht": erreicht,
        },
        "alarme": alarme,
        "segmente": sorted({p["segment"] for p in punkte_ohne_vertrag if p["segment"]}),
        "segment_label": SEGMENT_LABEL,
        "speicherstufen": sorted(
            {p["speicher"] for p in punkte_ohne_vertrag if p["speicher"]}
        ),
        "auffaellig": auffaellig,
        "bestand": bestand,
        "alle_punkte": punkte_alle,
        "katalog_obj": katalog,
        "vergleich": vergleich,
        "lifecycle": lifecycle,
        "quellenlage": _quellenlage(quellen, db, bestand),
    }
