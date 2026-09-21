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

KEIN BETRAG WIRD UMGERECHNET (zurueckgenommen mit P0-B-fix1, 21.09.2026)
-------------------------------------------------------------------------
Der Tarifbetrag eines Buendels ist der, den der Anbieter FUER DIESES
BUENDEL nennt. Er wird hier nicht ersetzt, nicht hochgerechnet und nicht
gegen die SIM-only-Kachel desselben Tarifs getauscht.

Am 21.09.2026 stand fuer einen Tag das Gegenteil hier: o2s Produktseite
nennt den niedrigeren Buendel-Tarifpreis selbst einen "attraktiven
monatlichen Rabatt auf deinen Tarif" (`collect/geraete/o2.py`, Modulkopf),
und daraus wurde die Regel, den gemessenen Betrag durch die
SIM-only-Grundgebuehr zu ersetzen und die Differenz als `tco_model.Rabatt`
daneben zu legen. Ein Rabatt wird per Definition NICHT eingerechnet - die
Leitzahl stieg damit fuer ALLE 72 o2-Buendel um 120,00 bis 276,00 EUR,
ohne dass sich ein o2-Preis geaendert hatte. Gemessen am Bestand vom
20.09.2026: Galaxy S26 Ultra 256 GB zu "O2 Mobile Unlimited M Plus" von
1.758,76 auf 2.034,76 EUR; ueber alle 72 Buendel von 98.768,16 auf
108.956,16 EUR. Auf der Karte stuende ein Betrag, den mit diesem
Ratenplan niemand zahlt, und der Ausgleich waere unsichtbar
(`report/geraete_tco_karten` setzt `"boni": []` hart, `boni_abzug`
kommt in keiner Vorlage vor). Die Zeitreihe bekaeme obendrein am
Umstellungstag eine Stufe von +120 EUR und `_bewegung` meldete "+120 EUR
in N Tagen" fuer einen Anbieter, der nichts geaendert hat - genau der
Fehler, den Paket A2 behoben hat.

Der Denkfehler war die Gleichsetzung von "der Anbieter sagt Rabatt" mit
"bedingter Nachlass". o2s -5 EUR sind KEIN bedingter Nachlass, sie sind
der Preis: die Strategie sagt es selbst - "o2 backt -5 EUR in den
Buendelpreis" (19,99 statt 24,99 SIM-only). Der gemessene Buendelpreis IST
die Basis der Leitzahl. Ein `Rabatt`, der schon im gemessenen Preis
steckt, wuerde daneben eine Ersparnis ausweisen, die niemand mehr holen
kann - und zugleich die echte Luecke `POSTEN_RABATTE` ("kein Bonus
erfasst") zudecken.

Was der SIM-only-Preis desselben Tarifs leistet, leistet er anderswo: als
MASSSTAB in `analyze/tarif_referenzen.py` und als Geraeteanteil in
`tco_model.geraeteanteil()` - dort steht die Differenz als Differenz und
nicht als Abzug.

Dasselbe gilt fuer die 1&1-Aufspaltung (`collect/geraete/einsundeins.py`,
"Hardware-Rate 45,00 plus Tarif 14,99 waere 59,99, das Buendel kostet aber
44,99"): 1&1 traegt keinen `tarif_monatlich`, nur `buendel_monatlich`
(siehe `tco_model.Buendel`), und eine Aufspaltung ohne Beleg bleibt eine
Erfindung.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

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
                # DER GEMESSENE BETRAG DIESES BUENDELS, unveraendert. Kein
                # Tausch gegen die SIM-only-Kachel desselben Tarifs, kein
                # Rabatt daneben - siehe Modulkopf "KEIN BETRAG WIRD
                # UMGERECHNET".
                tarif_monatlich=satz.get("tarif_monatlich"),
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
                # DIE GEMESSENE RATENLAUFZEIT, ungeraten (P0-B-fix1).
                # Bis hierher stand `int(... or 0) or 24`: ein Rohsatz ohne
                # Laufzeit - 1&1 liefert ihn, wenn die Produktseite keine
                # Dauer nennt - bekam still die ID `...--24m` und verschmolz
                # mit dem ECHTEN 24-Monats-Angebot desselben Tarifs. Jetzt
                # geht der Wert durch, wie er ist: `None` wird zur benannten
                # Luecke (`tco_model.LAUFZEIT_LUECKE` in der ID,
                # `POSTEN_LAUFZEIT` in der Kennzahl), eine unmoegliche Zahl
                # (0, negativ, 24,5) wirft in `Buendel.__post_init__` und
                # landet unten als `ungueltig` im Protokoll.
                laufzeit_monate=satz.get("laufzeit_monate"),
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
