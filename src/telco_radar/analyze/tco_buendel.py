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

Zwei Ausnahmen seit dem Geraetelauf vom 07.10.2026 (1056 Saetze verworfen):

* Ein Tarif, den der Anbieter nur mit Geraet fuehrt (o2 "Mobile Special",
  "Unlimited L Plus"), hat kein Tarifblatt und bleibt trotzdem: Tarif-ID aus
  dem Slug des Anbieters, Guete `nur_mit_geraet`, kein SIM-only-Vergleich
  (`ohne_tarifblatt`). Gezaehlt in `nur_mit_geraet`.
* Eine Zusatzkarte (`ZUSATZKARTEN`) ist kein eigenstaendiger Handytarif und
  bleibt draussen, mit eigenem Zaehler statt "ohne aufloesbaren Tarif".

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

from ..collect.tarif_crawler import tarif_id
from ..geraete_model import normalisiere
from ..tarif_bezug import SLUG_ALS_ID_ANBIETER, Bezug, Tarifbestand
from ..tarif_model import NUR_MIT_GERAET, buendelphasen_aus
from ..tco_model import Buendel, aktionen_aus

log = logging.getLogger(__name__)

ZUSATZKARTEN = {"vodafone": ("FamilyCard", "Red+")}
KLICKFELDER = ("quelle_art", "beleg_id", "beleg_status")
"""Kennzeichen eines Klick-Satzes (`klickrohsatz`); ein Adaptersatz hat sie nicht."""
"""Namensanfaenge von Zusatzkarten je Anbieter (normalisierter Name): Vodafone nennt
die FamilyCard selbst "FamilyCard-Zusatzkarte" (Promo-Seite, Hinweis in
`config/geraete_quellen.yaml`), Red+ ist Vodafones Zusatzkartenfamilie. Eine
Zusatzkarte braucht einen Hauptvertrag und ist kein eigenstaendiger Handytarif."""


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
    zusatzkarte: int = 0
    nur_mit_geraet: int = 0
    offene_tarife: dict = field(default_factory=dict)
    zusatzkarten: dict = field(default_factory=dict)
    tarife_nur_mit_geraet: dict = field(default_factory=dict)

    @property
    def verworfen(self) -> int:
        """Alle nicht uebernommenen Saetze, gleich aus welchem Grund."""
        return self.ohne_geraet + self.ohne_tarif + self.ungueltig + self.zusatzkarte


_BEISPIELE = 8


def aus_rohsaetzen(rohsaetze, bestand: Tarifbestand, heute: str) -> Buendelbilanz:
    """Rohsaetze in Buendel verwandeln, soweit ihr Tarif aufloest."""
    bilanz = Buendelbilanz()
    for satz in rohsaetze or []:
        if not isinstance(satz, dict):
            bilanz.ungueltig += 1
            continue
        anbieter = str(satz.get("anbieter") or "").strip()
        tarif_name = str(satz.get("tarif_name") or "").strip()
        sku = str(satz.get("sku_id") or "").strip()
        if not sku:
            bilanz.ohne_geraet += 1
            continue

        if ist_zusatzkarte(anbieter, tarif_name):
            bilanz.zusatzkarte += 1
            _zaehle(bilanz.zusatzkarten, tarif_name)
            continue

        slug = str(satz.get("tarif_slug") or "")
        bezug = bestand.loese(
            anbieter, tarif_name, slug=slug, mit_geraet=True
        ) or ohne_tarifblatt(bestand, anbieter, slug)
        if bezug is None:
            bilanz.ohne_tarif += 1
            _zaehle(bilanz.offene_tarife, tarif_name or slug or "?")
            continue

        try:
            bilanz.buendel.append(
                Buendel(
                    sku_id=sku,
                    anbieter=anbieter,
                    tarif_name=tarif_name,
                    tarif_id=bezug.tarif_id,
                    tarif_id_guete=bezug.guete,
                    tarif_monatlich=satz.get("tarif_monatlich"),
                    tarif_bindung_monate=satz.get("tarif_bindung_monate"),
                    buendel_monatlich=satz.get("buendel_monatlich"),
                    geraet_zuzahlung=satz.get("geraet_zuzahlung"),
                    geraet_monatsrate=satz.get("geraet_monatsrate"),
                    laufzeit_monate=satz.get("laufzeit_monate"),
                    anschlusspreis=satz.get("anschlusspreis"),
                    aktionen=aktionen_aus(satz.get("aktionen")),
                    zustand=str(satz.get("zustand") or ""),
                    quelle_url=str(satz.get("quelle_url") or ""),
                    abgerufen_am=heute,
                    herleitung=str(satz.get("herleitung") or ""),
                    tarif_phasen=buendelphasen_aus(satz.get("tarif_phasen")),
                    quelle_art=str(satz.get("quelle_art") or ""),
                    beleg_id=str(satz.get("beleg_id") or ""),
                    beleg_status=str(satz.get("beleg_status") or ""),
                )
            )
        except (ValueError, TypeError) as exc:
            bilanz.ungueltig += 1
            log.info("Buendel %s/%s verworfen: %s", anbieter, sku, exc)
            continue
        if bezug.guete == NUR_MIT_GERAET:
            bilanz.nur_mit_geraet += 1
            _zaehle(bilanz.tarife_nur_mit_geraet, tarif_name)

    if bilanz.offene_tarife:
        log.warning(
            "Buendel: %d Saetze ohne aufloesbaren Tarif verworfen - im "
            "Tarifbestand fehlen %d Tarife, haeufigste: %s",
            bilanz.ohne_tarif,
            len(bilanz.offene_tarife),
            _haeufigste(bilanz.offene_tarife),
        )
    if bilanz.zusatzkarten:
        log.info(
            "Buendel: %d Saetze mit Zusatzkarte verworfen - kein eigenstaendiger "
            "Handytarif: %s",
            bilanz.zusatzkarte,
            _haeufigste(bilanz.zusatzkarten),
        )
    if bilanz.tarife_nur_mit_geraet:
        log.info(
            "Buendel: %d Saetze mit Tarif ohne Tarifblatt uebernommen (nur mit "
            "Geraet, ohne SIM-only-Vergleich): %s",
            bilanz.nur_mit_geraet,
            _haeufigste(bilanz.tarife_nur_mit_geraet),
        )
    return bilanz


PLUS_SLUG = "-plus"
"""Endung des o2-Slugs der Fassung "Plus" eines Tarifs (nur mit Geraet, Rabatt im
Buendel): `o2-mobile-unlimited-l-plus` zum Grundtarif `o2-mobile-unlimited-l`."""


def ohne_tarifblatt(bestand: Tarifbestand, anbieter: str, slug: str) -> Bezug | None:
    """Ein Buendeltarif ohne Tarifblatt im Bestand - unter dem Slug des Anbieters.

    o2 fuehrt Tarife nur mit Geraet: "O2 Mobile Special" hat keine SIM-only-Kachel,
    und die Kachel "Unlimited L" verlinkt `o2-mobile-unlimited-l` ohne `-plus`.
    `Tarifbestand.loese` loest sie nicht auf, und das bleibt so: "Plus" wird nie auf
    den Tarif ohne "Plus" geraten. Die Tarif-ID ist `tarif_id(anbieter, slug)`.

    Nur, wenn der Bestand o2s Kacheln gelesen hat und den Slug weder als Tarif-ID
    noch als Kachel-Link kennt; "nicht gelesen" ist nicht "nur mit Geraet". Ein
    Plus-Slug zusaetzlich nur, wenn die Kachel seines Grundtarifs gelesen ist und
    einen anderen Slug verlinkt. Fehlt sie (Tarifsammler Mi/Fr, Geraetelauf
    taeglich), bleibt der Satz ohne Tarif, statt spaeter die ID zu wechseln
    (`o2:...-m-plus` zu `o2:...-m`, `ueber_slug`). Ohne `-plus` ist es dieselbe ID,
    die `loese` spaeter findet, wenn das Blatt unter dem Slug steht; verlinkt erst
    eine spaetere Kachel den Slug unter anderem Namen, wechselt sie. Nur fuer den
    Anbieter, dessen Slug als Tarif-ID belegt ist (`SLUG_ALS_ID_ANBIETER`);
    Vodafones Slug ist ein Angebots-Hash, der zwischen Tagen wechselt.
    """
    gesucht = (slug or "").strip().lower()
    if anbieter != SLUG_ALS_ID_ANBIETER or not gesucht:
        return None
    gelesen = any(s.get("buendel_slug") for s in bestand.saetze(anbieter))
    tid = tarif_id(anbieter, gesucht)
    if not gelesen or tid in bestand.je_id_aktuell:
        return None
    if bestand.kacheln_zum_slug(anbieter, gesucht):
        return None
    if gesucht.endswith(PLUS_SLUG):
        basis = tarif_id(anbieter, gesucht.removesuffix(PLUS_SLUG))
        if not (bestand.je_id_aktuell.get(basis) or {}).get("buendel_slug"):
            return None
    return Bezug(
        tarif_id=tid,
        tarif_name="",
        guete=NUR_MIT_GERAET,
        grund=f"Kein Tarifblatt im Bestand; Tarif-ID aus dem Slug {gesucht!r}",
    )


def ist_zusatzkarte(anbieter: str, tarif_name: str) -> bool:
    """Ob der Tarif eine Zusatzkarte ist (`ZUSATZKARTEN`)."""
    name = (tarif_name or "").strip().casefold()
    return any(
        name.startswith(anfang.casefold())
        for anfang in ZUSATZKARTEN.get(normalisiere(anbieter), ())
    )


def _zaehle(zaehler: dict, schluessel: str) -> None:
    zaehler[schluessel] = zaehler.get(schluessel, 0) + 1


def _haeufigste(zaehler: dict) -> str:
    paare = sorted(zaehler.items(), key=lambda p: (-p[1], p[0]))[:_BEISPIELE]
    return ", ".join(f"{name} ({zahl}x)" for name, zahl in paare)
