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

DIE RABATT-BASIS - EINHEITLICH, UND NUR WO BELEGT (B2b, 21.09.2026)
--------------------------------------------------------------------
Bis zum 20.09.2026 stand hier, kein Betrag werde umgerechnet: der
Tarifbetrag des Buendels sei der, den der Anbieter FUER DIESES BUENDEL
nennt - bei o2 14,99 EUR, waehrend derselbe Tarif ohne Geraet 19,99 EUR
kostet, und die Differenz zu einem `Rabatt` zu erklaeren sei eine Deutung,
die keine Quelle so ausspricht.

Fuer o2 spricht seither eine Quelle genau das aus: die Produktseite nennt
den niedrigeren Buendel-Tarifpreis woertlich einen "attraktiven
monatlichen Rabatt auf deinen Tarif" (`collect/geraete/o2.py`,
Modulkopf). Ein ANBIETER, der seinen eigenen Nachlass so nennt, bekommt
`tco_model.Rabatt` - Clean Code 3 gilt hier andersherum: ein Rabatt, der
in den gespeicherten Monatspreis gebacken ist, ist die versteckte Luecke.

**Die Regel ist deshalb EINHEITLICH (eine Rechnung, eine Stelle) und NICHT
automatisch fuer jeden Anbieter:** ein Rohsatz muss `tarif_rabatt_beleg`
setzen (nur o2 tut das, mit Verweis auf seine eigene Quelle im Modulkopf),
UND der Tarifbezug muss ueber Name oder Slug aufgeloest sein (`guete ==
HOCH`) - ein ueber den Betrag gefundener Bezug (`guete == MITTEL`) waere
zirkulaer: er wurde ja gerade ueber Gleichheit der Betraege gefunden.
Trifft beides zu und liegt der SIM-only-Grundpreis DESSELBEN Tarifs
(`Tarifbestand.je_id[bezug.tarif_id]["grundgebuehr"]`) hoeher als der
gemessene Buendelbetrag, wird die Differenz ein `Rabatt` (benannt, mit
Beleg-URL, NICHT eingerechnet - `tco_model.Rabatt.wert()`), und der
GESPEICHERTE `tarif_monatlich` wird der SIM-only-Grundpreis: die Leitzahl
zeigt damit den Preis OHNE den bedingten Nachlass, der Nachlass steht
daneben.

Die 1&1-Aufspaltung (`collect/geraete/einsundeins.py`, "Hardware-Rate
45,00 plus Tarif 14,99 waere 59,99, das Buendel kostet aber 44,99")
bekommt KEIN Rabatt-Feld: 1&1 traegt keinen `tarif_monatlich` (nur
`buendel_monatlich`, siehe `tco_model.Buendel`), das Flag fehlt, und die
15,00/18,00 EUR Differenz ist ohne eigene Anbieteraussage ein
unbenannter Nachlass - eine Aufspaltung ohne Beleg bleibt eine Erfindung.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from ..tarif_bezug import Bezug, Tarifbestand
from ..tarif_model import HOCH
from ..tco_model import Buendel, Rabatt

log = logging.getLogger(__name__)

# Ein Cent ist kein Rabatt, sondern ein Rundungsrest - dieselbe Toleranz
# wie in den Adaptern (`o2._gleich` u.a.).
_RABATT_TOLERANZ = 0.005


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


def _tarif_und_rabatt(satz: dict, bezug: Optional[Bezug],
                      bestand: Tarifbestand
                      ) -> tuple[Optional[float], list[Rabatt]]:
    """Der Tarifbetrag, der in die Leitzahl geht - und ein belegter Rabatt.

    Ohne Beleg (`tarif_rabatt_beleg` fehlt am Rohsatz) oder ohne einen
    ueber Name/Slug aufgeloesten Bezug (`guete == HOCH`) bleibt der
    gemessene Buendelbetrag unangetastet - dieselbe Rueckgabe wie vor
    B2b. Siehe Modulkopf "DIE RABATT-BASIS".
    """
    gemessen = satz.get("tarif_monatlich")
    if gemessen is None or not satz.get("tarif_rabatt_beleg"):
        return gemessen, []
    if bezug is None or bezug.guete != HOCH:
        return gemessen, []
    stamm = bestand.je_id.get(bezug.tarif_id) or {}
    grundgebuehr = stamm.get("grundgebuehr")
    if grundgebuehr is None:
        return gemessen, []
    try:
        grundgebuehr = float(grundgebuehr)
        gemessen = float(gemessen)
    except (TypeError, ValueError):
        return satz.get("tarif_monatlich"), []
    differenz = round(grundgebuehr - gemessen, 2)
    if differenz <= _RABATT_TOLERANZ:
        # Kein Nachlass (oder das Buendel ist teurer als die Kachel) -
        # dann ist die Kachel nicht die richtige Vergleichsbasis und der
        # gemessene Betrag bleibt stehen.
        return gemessen, []
    rabatt = Rabatt(
        name=(f"Tarifrabatt im Gerätebündel (SIM-only "
              f"{grundgebuehr:.2f} € statt {gemessen:.2f} €)"),
        betrag_monatlich=differenz,
        beleg_url=str(satz.get("quelle_url") or ""))
    return grundgebuehr, [rabatt]


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

        tarif_monatlich, rabatte = _tarif_und_rabatt(satz, bezug, bestand)

        try:
            bilanz.buendel.append(Buendel(
                sku_id=sku, anbieter=anbieter,
                # Der Name bleibt der des ANBIETERS, die ID kommt aus dem
                # Bestand - beides steht im Datensatz, und wenn die zwei
                # auseinanderlaufen, ist genau das die Auskunft
                # (`tco_model.Buendel`).
                tarif_name=tarif_name,
                tarif_id=bezug.tarif_id, tarif_id_guete=bezug.guete,
                # Der Preis OHNE bedingten Rabatt (B2b) - ein belegter
                # Nachlass steht daneben in `rabatte`, nie eingerechnet.
                tarif_monatlich=tarif_monatlich,
                rabatte=rabatte,
                # DER KOMBINIERTE MONATSBETRAG (§ 13.2, 1&1 seit B4): er
                # tritt AN DIE STELLE von `tarif_monatlich` und `geraet_
                # monatsrate`, und `Buendel.__post_init__` erzwingt genau
                # das - ein Satz mit beidem wirft. Ohne diese Zeile waere
                # ein 1&1-Satz still preislos durch diese Stufe gegangen
                # (derselbe Fehlertyp wie die Positivliste `_MESSFELDER`
                # im Store: ein Feld, das niemand durchreicht, existiert
                # fuer den Bestand nicht).
                buendel_monatlich=satz.get("buendel_monatlich"),
                geraet_zuzahlung=satz.get("geraet_zuzahlung"),
                geraet_monatsrate=satz.get("geraet_monatsrate"),
                laufzeit_monate=int(satz.get("laufzeit_monate") or 0) or 24,
                anschlusspreis=satz.get("anschlusspreis"),
                zustand=str(satz.get("zustand") or ""),
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
