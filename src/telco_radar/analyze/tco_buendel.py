"""Vom Buendel-Rohsatz zum `tco_model.Buendel` - oder zu einem Grund.

WO DIESE STUFE SITZT
--------------------
Der Sammler liest die Buendelnutzlast eines Anbieters und legt die
Rohsaetze in `Anbieterbilanz.buendel` (siehe `collect/geraete/__init__.py`,
`kind: buendel`). Sie tragen Betraege und einen TARIFNAMEN, aber keinen
Fremdschluessel - der steht in `data/state/tarife.jsonl`, und der ist ein
Ergebnis des Tarif-Sammlers, nicht des Geraetesammlers.

Dieses Modul stellt die Verbindung her und ist damit das Gegenstueck zu
`analyze/tarif_referenzen.py`: dort wird aus dem Tarifbestand der MASSSTAB
(SIM-only je Anbieter und Tarif), hier wird aus Geraetenutzlast plus
Tarifbestand das BUENDEL. Beide schreiben in dieselbe Datei, beide laufen
im naechtlichen Geraetelauf, und beide rechnen keine Kennzahl aus - die
rechnet `tco_model.tco_24()`, jedes Mal neu.

DIE EINE REGEL
--------------
**Ein Buendelpreis ohne aufloesbaren Tarif wird verworfen, nicht
gespeichert.** Sie steht schon in `TcoDB.upsert_buendel` und wirft dort;
hier wird sie zur Auswahl, damit ein einziger unaufloesbarer Satz nicht
die ganze Uebergabe kostet. Der Grund wird protokolliert und gezaehlt -
"drei Buendel verworfen, weil ihr Tarif im Bestand fehlt" ist eine
Arbeitsliste fuer `config/tarif_quellen.yaml`, ein stilles Weglassen ist
keine.

WARUM DER SLUG HIER GEBRAUCHT WIRD
----------------------------------
o2 nennt denselben Tarif im Geraetekatalog "O2 Mobile on Demand M Plus mit
50 GB+ (24 Mon.)" und in der SIM-only-Kachel "O2 Mobile on Demand M". Ueber
den Namen loest das nichts auf, und das ist richtig so - "M" und "M Plus"
sind verschiedene Zeichenketten. Was die zwei verbindet, ist der Slug
`o2-mobile-on-demand-m-plus`, den o2 auf BEIDEN Seiten selbst setzt
(`tarif_bezug.ueber_slug`). Ein Rohsatz ohne `tarif_slug` geht deshalb
nicht leer aus: `loese()` versucht weiterhin zuerst den Namen.

WAS HIER NICHT PASSIERT
-----------------------
Es wird kein Betrag umgerechnet und keiner ersetzt. Der Tarifbetrag des
Buendels ist der, den der Anbieter FUER DIESES BUENDEL nennt - bei o2
14,99 EUR, waehrend derselbe Tarif ohne Geraet 19,99 EUR kostet. Die
Differenz ist die Auskunft, um die es geht (`Geraeteanteil` zieht die eine
TCO von der anderen ab); sie hier zu einem `Rabatt` zu erklaeren waere
eine Deutung, die keine Quelle so ausspricht.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from ..tarif_bezug import Tarifbestand
from ..tco_model import Buendel

log = logging.getLogger(__name__)


@dataclass
class Buendelbilanz:
    """Was aus den Rohsaetzen geworden ist - und warum nicht mehr.

    Die Gruende stehen als ZAHL je Grund und nicht als Liste von Saetzen:
    achtzig Zeilen "Tarif nicht aufloesbar" im Protokoll sind keine
    Auskunft. Die Beispiele daneben sind gedeckelt und dienen dem
    Nachschlagen.
    """

    buendel: list = field(default_factory=list)
    ohne_geraet: int = 0
    ohne_tarif: int = 0
    ungueltig: int = 0
    offene_tarife: dict = field(default_factory=dict)

    @property
    def verworfen(self) -> int:
        return self.ohne_geraet + self.ohne_tarif + self.ungueltig


# Wie viele verschiedene unaufloesbare Tarifnamen im Protokoll stehen. Der
# Deckel gilt der LISTE, nicht der Zahl - `offene_tarife` zaehlt weiter.
_BEISPIELE = 8


def aus_rohsaetzen(rohsaetze, bestand: Tarifbestand, heute: str
                   ) -> Buendelbilanz:
    """Rohsaetze in Buendel verwandeln, soweit ihr Tarif aufloest."""
    bilanz = Buendelbilanz()
    for satz in (rohsaetze or []):
        if not isinstance(satz, dict):
            bilanz.ungueltig += 1
            continue
        anbieter = str(satz.get("anbieter") or "").strip()
        tarif_name = str(satz.get("tarif_name") or "").strip()
        sku = str(satz.get("sku_id") or "").strip()
        if not sku:
            # Ohne Geraet waere es die SIM-only-Referenz eines Tarifs, und
            # die entsteht aus dem Tarifbestand, nicht aus einer
            # Geraetenutzlast. Ein Buendel ohne SKU darf nach
            # `Buendel.__post_init__` ausserdem gar keine Zuzahlung tragen.
            bilanz.ohne_geraet += 1
            continue

        bezug = bestand.loese(anbieter, tarif_name,
                              slug=str(satz.get("tarif_slug") or ""))
        if bezug is None:
            bilanz.ohne_tarif += 1
            schluessel = tarif_name or str(satz.get("tarif_slug") or "?")
            bilanz.offene_tarife[schluessel] = \
                bilanz.offene_tarife.get(schluessel, 0) + 1
            continue

        try:
            bilanz.buendel.append(Buendel(
                sku_id=sku, anbieter=anbieter,
                # Der Name bleibt der des ANBIETERS, die ID kommt aus dem
                # Bestand - beides steht im Datensatz, und wenn die zwei
                # auseinanderlaufen, ist genau das die Auskunft
                # (`tco_model.Buendel`).
                tarif_name=tarif_name,
                tarif_id=bezug.tarif_id, tarif_id_guete=bezug.guete,
                tarif_monatlich=satz.get("tarif_monatlich"),
                geraet_zuzahlung=satz.get("geraet_zuzahlung"),
                geraet_monatsrate=satz.get("geraet_monatsrate"),
                laufzeit_monate=int(satz.get("laufzeit_monate") or 0) or 24,
                anschlusspreis=satz.get("anschlusspreis"),
                quelle_url=str(satz.get("quelle_url") or ""),
                abgerufen_am=heute))
        except (ValueError, TypeError) as exc:
            # `Buendel` prueft seine Posten selbst (negative Betraege, eine
            # Laufzeit von null, ein Geraetepreis ohne SKU). Ein Satz, der
            # dort scheitert, ist ein Nutzlastfehler und kostet nicht die
            # uebrigen.
            bilanz.ungueltig += 1
            log.info("Buendel %s/%s verworfen: %s", anbieter, sku, exc)

    if bilanz.offene_tarife:
        haeufigste = sorted(bilanz.offene_tarife.items(),
                            key=lambda p: (-p[1], p[0]))[:_BEISPIELE]
        log.warning(
            "Buendel: %d Saetze ohne aufloesbaren Tarif verworfen - im "
            "Tarifbestand fehlen %d Tarife, haeufigste: %s",
            bilanz.ohne_tarif, len(bilanz.offene_tarife),
            ", ".join(f"{name} ({zahl}x)" for name, zahl in haeufigste))
    return bilanz
