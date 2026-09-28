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
* **Festnetz** - soweit das Blatt seine Art auszeichnet. Ein
  Festnetztarif ist kein Massstab fuer einen Geraetepreis; o2 fuehrt zwei
  davon im Bestand. ACHTUNG, die Regel greift nur, wo `art` gesetzt ist:
  Vodafones Blaetter tragen die Art gar nicht (alle zehn Saetze im Bestand
  haben `art=""`), dort haelt heute allein die Quellenkonfiguration
  (`bevorzugt: vf-mobil-`) die DSL-Blaetter draussen. Wer dort ein
  Festnetzblatt hereinlaesst, bekommt es als SIM-only-Referenz.
* **Tarife ohne Grundpreis.** Ohne Betrag kein Massstab.
* **Die erste Preisphase ist der Preis.** Traegt ein Tarif mehrere Phasen,
  gilt die, die bei Vertragsschluss laeuft - nicht ihr Durchschnitt. Was
  ueber 24 Monate daraus wird, rechnet `report/effektivpreis.py`, und zwar
  an EINER Stelle.

DIE LIVE-SHOP-LESART SCHLAEGT DAS PFLICHTDOKUMENT (seit 05.09.2026)
--------------------------------------------------------------------
Traegt derselbe Anbieter denselben Tarifnamen ZWEIMAL im Bestand - einmal
als `dokument` (Pflichtblatt), einmal als `live_shop` (Shop-Seite von
heute) -, gewinnt die Live-Lesart die SIM-only-Referenz. Das ist der
Telekom-Fall: sechs ihrer neun Pflichtblaetter stammen aus dem Jahr 2021
(`mobilfunk-magentamobil-s-20211121` u.ae.) und werden bei jedem Lauf nur
neu ANGESEHEN, nie neu AUSGESTELLT - `abgerufen_am` wandert, der Inhalt
nicht. Die Shop-Kacheln (`collect/tarif_telekom_kacheln.py`) tragen
denselben Betrag, aber mit dem Stand von heute und einem Link auf die
Verkaufsseite statt auf ein fuenf Jahre altes PDF.

Das Pflichtdokument bleibt trotzdem im Bestand und in der Zeitreihe stehen
("nichts wird geloescht") - es tritt hier nur als MASSSTAB zurueck, hinter
die aktuellere Messung desselben Betrags. `_bevorzugt_live()` sortiert die
Saetze dafuer VOR der Dublettenpruefung um; die generische Regel darunter
("zwei Saetze, dieselbe Titelzeile, der zweite bleibt draussen") tut den
Rest unveraendert - sie entscheidet dann nur noch, WELCHER der zwei
Saetze zuerst dran ist, nicht ob einer verworfen wird.
"""
from __future__ import annotations

import logging

from ..tarif_bezug import Tarifbestand
from ..tarif_model import (GERAETEBLATT_ZUSATZ, HOCH, PREISTYP_DOKUMENT,
                           PREISTYP_LIVE_SHOP, erster_betrag,
                           ist_geraeteblatt_von)
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
# Die Regel selbst: `tarif_model.ist_geraeteblatt_von`.


def _bevorzugt_live(saetze: list[dict]) -> list[dict]:
    """Live-Shop-Saetze zuerst, sonst die Reihenfolge des Bestands.

    Ein stabiler Sortierschluessel: innerhalb derselben Lesart aendert sich
    nichts. Trifft die Dublettenregel unten auf zwei Saetze mit derselben
    Titelzeile, steht der `live_shop`-Satz jetzt vorn und gewinnt deshalb -
    ohne dass die Regel selbst etwas von Preistypen wissen muesste.
    """
    return sorted(saetze,
                  key=lambda s: s.get("preistyp") != PREISTYP_LIVE_SHOP)


def aus_bestand(bestand: Tarifbestand) -> list[SimOnlyReferenz]:
    """Je Tarif mit belegtem Grundpreis eine SIM-only-Referenz.

    Der Anschlusspreis wandert mit, wenn er belegt ist - fehlt er, bleibt
    er `None` und nicht 0.0. "Kein Anschlusspreis bekannt" heisst nicht
    "kostenlos"; das ist die Regel aus `report/effektivpreis.py`, und die
    TCO fuehrt sie als Luecke.
    """
    saetze = _bevorzugt_live(bestand.saetze())

    # Satz je (Anbieter, Tarifname) - fuer die Dublettenregel unten.
    # Verglichen wird auf Kleinschreibung: der Zusatz steht auf beiden
    # Blaettern gleich, der Name selbst nicht immer.
    je_name: dict[tuple[str, str], dict] = {}
    for satz in saetze:
        je_name[((satz.get("anbieter") or "").strip().lower(),
                 (satz.get("name") or "").strip().lower())] = satz

    referenzen: list[SimOnlyReferenz] = []
    gesehen: dict[str, str] = {}
    for satz in saetze:
        if (satz.get("art") or "").lower() in _UNGEEIGNET:
            continue
        betrag = erster_betrag(satz)
        if betrag is None:
            continue
        anbieter = (satz.get("anbieter") or "").strip()
        name = (satz.get("name") or "").strip()
        if not anbieter or not name:
            continue
        tarifblatt = je_name.get(
            (anbieter.lower(), GERAETEBLATT_ZUSATZ.sub("", name).lower()))
        if tarifblatt is not None and ist_geraeteblatt_von(satz, tarifblatt):
            # Das Buendelblatt desselben Tarifs. Sein Datensatz bleibt im
            # Bestand - nur als MASSSTAB waere er eine Dublette.
            log.debug("SIM-only-Referenz uebersprungen: %r ist das "
                      "Geraeteblatt von %r", name, tarifblatt.get("name"))
            continue
        referenz = SimOnlyReferenz(
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
            quelle_art=satz.get("preistyp") or PREISTYP_DOKUMENT,
        )
        # ZWEI TARIFE MIT DERSELBEN TITELZEILE ergeben eine ID.
        # `SimOnlyReferenz.id` ist (Anbieter, Tarifname) - live gemessen
        # fuehrt o2 `o2-home-l-flex` und `o2-home-l-175-flex` als getrennte
        # PDFs mit derselben Ueberschrift (CLAUDE.md § 6). Der Tarifspeicher
        # trennt sie ueber einen Hash-Zusatz an der `tarif_id`, dieser
        # Schluessel kann das nicht.
        #
        # Ohne die Sperre uebernaehme `TcoDB` den ZWEITEN Satz und behielte
        # dabei den Schluessel des ersten - die Zeile truege dann einen
        # Betrag aus dem einen und einen `tarif_id` aus dem anderen
        # Dokument. Der erste gewinnt und der zweite wird gemeldet: ein
        # Massstab, dessen Beleg auf ein anderes Blatt zeigt, ist schlimmer
        # als ein fehlender.
        if referenz.id in gesehen:
            log.warning("SIM-only-Referenz %s doppelt: %r und %r tragen "
                        "dieselbe Titelzeile - der zweite Satz bleibt "
                        "draussen", referenz.id, gesehen[referenz.id],
                        satz.get("tarif_id"))
            continue
        gesehen[referenz.id] = satz.get("tarif_id", "")
        referenzen.append(referenz)
    return referenzen
