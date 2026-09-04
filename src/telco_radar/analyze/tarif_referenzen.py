"""Aus dem Tarifbestand werden SIM-only-Referenzen.

Warum das hier steht und nicht im Renderer
-------------------------------------------
`tco_model.SimOnlyReferenz` ist der Massstab, ohne den ein Geraeteanteil
nicht bestimmbar ist: 69,95 EUR im Monat sagen nichts darueber, was das
Telefon kostet, solange niemand weiss, was der Tarif ALLEIN kostet.

Diese Zahl gab es bisher nirgends - `data/state/geraete_tco.json` existierte
nicht. Sie stand aber die ganze Zeit an der besten denkbaren Stelle: im
Produktinformationsblatt nach § 1 TK-TransparenzV, dem einzigen Dokument
dieses Marktes, das rechtlich wahrheitsbewehrt ist. Die Telekom weist sie
als Staffelstufe "ohne Smartphone" aus, Vodafone gleichlautend, congstar
als "Entgelt Allnet Flat L (ohne Endgeraet)". Genau das ist eine
SIM-only-Referenz.

Die Regel, die dieses Modul traegt
----------------------------------
**Es wird nichts gerechnet.** Uebernommen wird der Grundpreis, so wie er
im Blatt steht, mit dem Dokumentlink als Quelle. Kein Mittelwert ueber
Phasen, keine Umrechnung eines Vierwochenpreises, keine Ableitung aus einer
Staffel. Was der Extraktor nicht belegen konnte, hat keine Referenz -
dieselbe Haltung wie in `analyze/faithfulness.py`: was nicht geprueft
werden konnte, erscheint nicht.

Was ausgeschlossen ist, und warum
---------------------------------
* **Festnetz.** Ein Festnetztarif ist kein Massstab fuer einen
  Geraetepreis; o2 fuehrt zwei davon im Bestand.
* **Tarife ohne Grundpreis.** Ohne Betrag kein Massstab.
* **Die erste Preisphase ist der Preis.** Traegt ein Tarif mehrere Phasen,
  gilt die, die bei Vertragsschluss laeuft - nicht ihr Durchschnitt. Was
  ueber 24 Monate daraus wird, rechnet `report/effektivpreis.py`, und zwar
  an EINER Stelle.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from ..tarif_bezug import Tarifbestand
from ..tarif_model import HOCH
from ..tco_model import SimOnlyReferenz

log = logging.getLogger(__name__)

# Ein Festnetzanschluss ist kein Massstab fuer ein Smartphone-Buendel.
_UNGEEIGNET = ("festnetz",)

# Vodafone veroeffentlicht jeden Tarif ZWEIMAL: einmal als reines
# Tarifblatt ("Vodafone Mobil M") und einmal mit der Geraetestaffel
# ("Vodafone Mobil M mit Smartphone"). Beide nennen denselben Preis ohne
# Geraet - es ist derselbe Tarif, zweimal beschrieben.
#
# Als zwei Referenzen stuende derselbe Massstab zweimal untereinander, mit
# demselben Betrag. Das ist keine Auskunft, sondern eine Dublette.
#
# Die Regel ist ENG gefasst, und das ist Absicht: es faellt nur weg, was
# woertlich denselben Namen PLUS einen Hardware-Zusatz traegt UND denselben
# Betrag nennt. "MagentaMobil S" und "MagentaMobil S Flex" haben ebenfalls
# denselben Preis und sind trotzdem zwei Tarife (der eine mit
# Mindestlaufzeit, der andere ohne) - eine Regel ueber Namenspraefixe
# haette den zweiten geloescht.
_HARDWARE_ZUSATZ = re.compile(r"\s+mit\s+(?:Smartphone|Handy|Endger[aä]t)\s*$",
                              re.I)


def _erste_phase(satz: dict) -> Optional[float]:
    """Der Betrag, der bei Vertragsschluss gilt.

    `grundgebuehr` und die erste Preisphase sind bei jedem heute gelesenen
    Dokument dieselbe Zahl - der Extraktor setzt die Phase aus ihr, wo das
    Blatt keine Zeitachse hat. Wo es eine hat (Vodafone: "Monat 1-24" /
    "ab Monat 25"), ist die erste Phase die genauere Angabe, und sobald
    dort einmal eine Rabattphase steht, ist sie die einzige richtige.
    """
    phasen = satz.get("preisphasen") or []
    if phasen:
        erste = min(phasen, key=lambda p: p.get("von_monat", 1))
        if erste.get("betrag") is not None:
            return float(erste["betrag"])
    grund = satz.get("grundgebuehr")
    return None if grund is None else float(grund)


def aus_bestand(bestand: Tarifbestand) -> list[SimOnlyReferenz]:
    """Je Tarif mit belegtem Grundpreis eine SIM-only-Referenz.

    Der Anschlusspreis wandert mit, wenn er belegt ist - fehlt er, bleibt
    er `None` und nicht 0.0. "Kein Anschlusspreis bekannt" heisst nicht
    "kostenlos"; das ist die Regel aus `report/effektivpreis.py`, und die
    TCO fuehrt sie als Luecke.
    """
    # Betrag je (Anbieter, Tarifname) - fuer die Dublettenregel unten.
    # Verglichen wird auf Kleinschreibung: der Zusatz steht auf beiden
    # Blaettern gleich, der Name selbst nicht immer.
    je_name: dict[tuple[str, str], float] = {}
    for satz in bestand.saetze():
        betrag = _erste_phase(satz)
        if betrag is not None:
            je_name[((satz.get("anbieter") or "").strip().lower(),
                     (satz.get("name") or "").strip().lower())] = betrag

    referenzen: list[SimOnlyReferenz] = []
    for satz in bestand.saetze():
        if (satz.get("art") or "").lower() in _UNGEEIGNET:
            continue
        betrag = _erste_phase(satz)
        if betrag is None:
            continue
        anbieter = (satz.get("anbieter") or "").strip()
        name = (satz.get("name") or "").strip()
        if not anbieter or not name:
            continue
        ohne_zusatz = _HARDWARE_ZUSATZ.sub("", name)
        if ohne_zusatz != name and je_name.get(
                (anbieter.lower(), ohne_zusatz.lower())) == betrag:
            # Das Buendelblatt desselben Tarifs. Sein Datensatz bleibt im
            # Bestand - nur als MASSSTAB waere er eine Dublette.
            log.debug("SIM-only-Referenz uebersprungen: %r ist das "
                      "Geraeteblatt von %r", name, ohne_zusatz)
            continue
        referenzen.append(SimOnlyReferenz(
            anbieter=anbieter,
            tarif_name=name,
            # Die Referenz KOMMT aus dem Bestand - ihr Schluessel ist damit
            # der des Datensatzes, nicht das Ergebnis einer Suche. Guete
            # `hoch`: hier wird nichts zugeordnet, hier wird gelesen.
            tarif_id=satz.get("tarif_id", ""),
            tarif_id_guete=HOCH,
            tarif_sim_only_monatlich=betrag,
            anschlusspreis=(None if satz.get("anschlusspreis") is None
                            else float(satz["anschlusspreis"])),
            quelle_url=satz.get("dokument_url", ""),
            abgerufen_am=satz.get("abgerufen_am", ""),
        ))
    return referenzen
