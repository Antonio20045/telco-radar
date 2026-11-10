"""Beleg je Preisposition (Zeile), Ziel 1d: ein Bild hängt nur an seiner Zeile.

Die Belegbilder im Manifest tragen Gerät, Anbieter und Tag und, seit der Bildfolge,
die Kennung der Messung (erste Zeichen der ``beleg_id``): sie nennt den Klick-Satz im
Bestand ``geraete_tco.json`` genau. Nur ein altes Bild ohne Kennung folgt der Regel des
Veröffentlichens (Satz mit den niedrigsten Gesamtkosten,
``analyze.beleg_position.position_des_bildes``). Je Paar zählt das neueste Bild, dessen
Messung im Bestand liegt.

Fail-closed: eine Zeile bekommt ihr Bild nur, wenn die Wahl eindeutig ist, Einzelbild
und Schritte der Folge die Kennung ihrer ``beleg_id`` tragen (``fremd_zur_kennung``; ein
Bild einer anderen Messung gibt einen Vermerk statt eines Bilds) und Gerät, Anbieter,
SKU, Tarif und Ratenlaufzeit der Zeile mit dem Bildsatz übereinstimmen (``passt``).
Gleich teure Positionen, ein neuerer Abruf im Paar, fehlende Klick-Messung (Vodafone,
1&1-Sätze ohne ``beleg_id``) oder fehlende Gesamtkosten ergeben kein Bild, nie ein
geratenes. Die Quote zählt Zeilen mit belastbarem Preis (``preis_anzeige``),
je Anbieter, nie Paare.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from ..analyze.beleg_position import Bildposition, position_des_bildes
from ..analyze.geraete_pruefstatus import buendel_aus_satz
from ..beleg_bildfolge import fremd_zur_kennung, kennung_der_adresse
from ..beleg_regeln import KENNUNG_LAENGE, anbieter_schluessel
from ..tarif_model import QUELLE_KLICK
from .geraete_laufzeit import raten_laufzeit
from .geraete_preisstand import anzeige as preis_anzeige
from .geraete_tco_karten import geraet_aus_sku, modell_schluessel

log = logging.getLogger(__name__)

GRUND_FREMD = "Bild gehört zu einer anderen Messung"
GRUND_UNLESBAR = "Bildsatz unlesbar"
GRUND_KENNUNG_FEHLT = "die Messung des Bildes liegt nicht mehr im Bestand"
GRUND_KENNUNG_MEHRFACH = "die Messung des Bildes gehört zu mehreren Positionen"
"""Der Vermerk auf der Seite nennt keine Kennungen und keine Fehlertexte: die stehen im
Log (``log.warning``), die Leser brauchen den Grund, nicht den Schlüssel."""

ZeilenbelegFuer = Callable[[dict], "dict | None"]


@dataclass(frozen=True)
class Zeilenbeleg:
    """Das Bild einer Preisposition mit allem, was die Zeile bestätigen muss."""

    geraet_id: str
    anbieter_id: str
    sku_id: str
    tarif: str
    tarif_id: str | None
    raten_laufzeit: int | None
    beleg_id: str
    datum: str
    gross: bool
    url: str
    bildfolge: tuple[dict[str, str], ...] = ()


def passt(beleg: Zeilenbeleg, karte: dict) -> bool:
    """Gehört das Bild zu dieser Zeile? Jede Abweichung in Gerät, Anbieter, SKU, Tarif
    oder Ratenlaufzeit lehnt ab (kein Bild einer anderen Variante oder eines anderen
    Tarifs)."""
    return (
        bool(beleg.beleg_id)
        and karte.get("beleg_id") == beleg.beleg_id
        and karte.get("modell_id") == beleg.geraet_id
        and anbieter_schluessel(karte.get("anbieter") or "") == beleg.anbieter_id
        and karte.get("sku_id") == beleg.sku_id
        and karte.get("tarif") == beleg.tarif
        and karte.get("tarif_id") == beleg.tarif_id
        and karte.get("raten_laufzeit") == beleg.raten_laufzeit
    )


def _position(saetze: list[dict[str, Any]], bild: dict) -> Bildposition:
    """Die Position, die ``bild`` zeigt. Trägt sein Name die Kennung der Messung
    (``beleg_regeln.folge_dateiname``), ist es der eine Bestandssatz des Paares mit
    dieser ``beleg_id``: die ``beleg_id`` ist der Hash von Screenshot und Mitschnitt,
    die Kennung ihr Anfang, die Zuordnung also exakt und ohne Schluss über Preise.
    Fehlt der Satz (ersetzt oder nie in den Bestand gelangt) oder steht die Kennung
    für mehrere Positionen, gibt es keine Zeile; ein Bild ohne Kennung (alter
    Bestand) folgt der Regel von ``position_des_bildes``."""
    kennung = kennung_der_adresse(bild["url"])
    if kennung is None:
        return position_des_bildes(saetze, bild["datum"])
    treffer = [
        s for s in saetze if str(s.get("beleg_id") or "")[:KENNUNG_LAENGE] == kennung
    ]
    if not treffer:
        return Bildposition(None, GRUND_KENNUNG_FEHLT)
    if len(treffer) > 1:
        return Bildposition(None, GRUND_KENNUNG_MEHRFACH)
    return Bildposition(treffer[0])


def _zeilenbeleg(
    schluessel: tuple[str, str], bild: dict, satz: dict[str, Any]
) -> tuple[Zeilenbeleg | None, str]:
    """Das Bild der Position ``satz`` oder der Grund, warum es nicht gilt."""
    try:
        buendel = buendel_aus_satz(satz)
    except (TypeError, ValueError, KeyError) as fehler:
        log.warning("Zeilenbeleg %s: Bildsatz unlesbar: %s", schluessel, fehler)
        return None, GRUND_UNLESBAR
    folge = bild.get("bildfolge") or ()
    fremd = fremd_zur_kennung(bild["url"], folge, buendel.beleg_id[:KENNUNG_LAENGE])
    if fremd:
        log.warning("Zeilenbeleg %s: %s: %s", schluessel, GRUND_FREMD, fremd)
        return None, GRUND_FREMD
    return (
        Zeilenbeleg(
            geraet_id=schluessel[0],
            anbieter_id=schluessel[1],
            sku_id=buendel.sku_id,
            tarif=buendel.tarif_name,
            tarif_id=buendel.tarif_id,
            raten_laufzeit=raten_laufzeit(buendel),
            beleg_id=buendel.beleg_id,
            datum=bild["datum"],
            gross=bool(bild["gross"]),
            url=bild["url"],
            bildfolge=tuple(folge),
        ),
        "",
    )


def baue_index(
    saetze: Iterable[dict[str, Any]],
    bilder_je_paar: dict[tuple[str, str], list[dict]],
    katalog: Any,
) -> tuple[dict[str, Zeilenbeleg], dict[tuple[str, str], str]]:
    """``beleg_id`` zu ``Zeilenbeleg``; je Paar der Grund, warum keine Zeile belegt ist.

    ``bilder_je_paar`` sind die angezeigten Bilder je (Gerät, Anbieter), neueste zuerst
    (``geraete_belege.sortiert_je_preis``); es zählt das neueste, das einer Position
    des Bestands gehört. Liegt die Messung des neuesten noch nicht im Bestand (der
    Klick-Lauf war später als der Geräte-Lauf), zeigt die Zeile das ältere Bild,
    das zu ihrer eigenen Messung gehört, nie das neuere.
    """
    gruppen: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for satz in saetze:
        if satz.get("quelle_art") != QUELLE_KLICK:
            continue
        geraet, speicher = geraet_aus_sku(str(satz.get("sku_id") or ""), katalog)
        if not geraet:
            continue
        schluessel = (
            modell_schluessel(geraet, speicher),
            anbieter_schluessel(str(satz.get("anbieter") or "")),
        )
        gruppen[schluessel].append(satz)
    index: dict[str, Zeilenbeleg] = {}
    gruende: dict[tuple[str, str], str] = {}
    for schluessel, bilder in bilder_je_paar.items():
        for bild in bilder:
            wahl = _position(gruppen.get(schluessel, []), bild)
            grund = wahl.grund
            if wahl.satz is not None:
                eintrag, grund = _zeilenbeleg(schluessel, bild, wahl.satz)
                if eintrag is not None:
                    index[eintrag.beleg_id] = eintrag
                    gruende.pop(schluessel, None)
                    break
            gruende.setdefault(schluessel, grund)
    return index, gruende


def zeilenbeleg_fuer(index: dict[str, Zeilenbeleg]) -> ZeilenbelegFuer:
    """``karte -> {datum, gross, url, bildfolge}`` oder ``None``: nur bei ``passt``.

    ``bildfolge`` ist leer (ein Bild: ``url``) oder die Schritte des Klickwegs in
    Reihenfolge (``beleg_bildfolge``).
    """

    def finde(karte: dict) -> dict | None:
        beleg = index.get(str(karte.get("beleg_id") or ""))
        if beleg is None or not passt(beleg, karte):
            return None
        return {
            "datum": beleg.datum,
            "gross": beleg.gross,
            "url": beleg.url,
            "bildfolge": list(beleg.bildfolge),
        }

    return finde


def _zeilen(modell: dict) -> list[dict]:
    """Die belastbaren Preiszeilen eines Modells (``preis_anzeige``)."""
    karten = [*modell.get("zeilen_band", []), *modell.get("zeilen_ohne_band", [])]
    return [k for k in karten if preis_anzeige(k).get("belastbar")]


def kombi(karte: dict) -> str:
    """``Band:Laufzeit-Ansicht`` einer Preiszeile, wie die Seite sie blendet.

    Dieselben Felder wie ``data-band`` und ``data-lz`` der Bündelzeile; leer heißt
    „unter jeder Wahl sichtbar“ (``app.js`` ``stelleZeilen``).
    """
    return f"{karte.get('band') or ''}:{karte.get('laufzeit_sichtbar') or ''}"


def ergaenze_paare(
    paare: list[dict],
    modell: dict,
    fuer: ZeilenbelegFuer,
    gruende: dict[tuple[str, str], str] | None = None,
) -> list[dict]:
    """Jedes Paar nennt seine Preiszeilen mit eigenem Bild (Gerät, Tarif, Raten, Preis).

    ``zeilen_mit`` und ``zeilen_gesamt`` zählen die belastbaren Zeilen des Paares,
    ``zeilenbilder`` sind die belegten (je mit ``kombi``), ``kombis`` nennt alle
    Kombinationen (Band:Laufzeit) des Paares, damit die Seite bei der Wahl einer
    Kombination ohne Bild den Vermerk zeigt statt eines anderen Bildes; ohne eine
    belegte Zeile nennt ``zeilen_grund`` (wenn bekannt), warum das Bild des Paares
    keiner Zeile zugeordnet wird.
    """
    gesamt: dict[str, int] = defaultdict(int)
    kombis: dict[str, set[str]] = defaultdict(set)
    bilder: dict[str, list[dict]] = defaultdict(list)
    for karte in _zeilen(modell):
        schluessel = anbieter_schluessel(karte.get("anbieter") or "")
        gesamt[schluessel] += 1
        kombis[schluessel].add(kombi(karte))
        beleg = fuer(karte)
        if beleg:
            bilder[schluessel].append(
                {
                    "geraet": karte.get("geraet"),
                    "tarif": karte.get("tarif"),
                    "raten_text": karte.get("raten_text"),
                    "label": karte.get("label"),
                    "gesamt": karte.get("gesamt"),
                    "kombi": kombi(karte),
                    **beleg,
                }
            )
    ergebnis = []
    for paar in paare:
        schluessel = anbieter_schluessel(paar["anbieter"])
        grund = (gruende or {}).get((modell.get("id", ""), schluessel), "")
        ergebnis.append(
            {
                **paar,
                "zeilen_mit": len(bilder[schluessel]),
                "zeilen_gesamt": gesamt[schluessel],
                "zeilenbilder": bilder[schluessel],
                "kombis": " ".join(sorted(kombis[schluessel])),
                "zeilen_grund": "" if bilder[schluessel] else grund,
            }
        )
    return ergebnis


def _zahl(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def quote(fuer: ZeilenbelegFuer, modelle: list[dict], bestand_ok: bool = True) -> dict:
    """Preiszeilen mit eigenem Bild, je Anbieter und zusammen.

    ``satz`` ist der fertige Text der Seite; ohne Zeile oder bei unlesbarem Bestand
    bleibt er leer (der Ausfall nennt es), statt „0 von N“ zu behaupten.
    """
    je_anbieter: dict[str, list[int]] = {}
    for modell in modelle:
        for karte in _zeilen(modell):
            zaehler = je_anbieter.setdefault(karte.get("anbieter") or "", [0, 0])
            zaehler[1] += 1
            zaehler[0] += 1 if fuer(karte) else 0
    liste: list[dict[str, Any]] = [
        {"anbieter": name, "mit": z[0], "gesamt": z[1]}
        for name, z in sorted(je_anbieter.items(), key=lambda e: e[0].casefold())
    ]
    mit = sum(e["mit"] for e in liste)
    gesamt = sum(e["gesamt"] for e in liste)
    satz = ""
    if gesamt and bestand_ok:
        teile = " · ".join(
            f"{e['anbieter']} {_zahl(e['mit'])} von {_zahl(e['gesamt'])}" for e in liste
        )
        satz = (
            "Preiszeilen mit eigenem Screenshot, Zuordnung über die Messung "
            f"(aus dem Bild allein nicht ablesbar): {teile}; "
            f"zusammen {_zahl(mit)} von {_zahl(gesamt)}."
        )
    return {"mit": mit, "gesamt": gesamt, "je_anbieter": liste, "satz": satz}
