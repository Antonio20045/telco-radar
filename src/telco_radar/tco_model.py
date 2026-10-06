"""Was ein Buendel aus Geraet und Tarif wirklich kostet - die Kosten ueber 24 Monate.

Warum es dieses Modul gibt
--------------------------
Die Geraeteseite vergleicht heute Barpreise. Der halbe Markt verkauft aber
kein Geraet, sondern ein Buendel: 1 EUR Zuzahlung, 24 x 30 EUR Geraeterate,
daneben ein Tarif, dazu ein Anschlusspreis und ein Bonus, der nach sechs
Monaten ausgelaufen ist. Wer davon EINE Zahl in eine Preisspalte schreibt,
schreibt eine Meinung. Dieses Modul haelt die Bestandteile getrennt und
rechnet die Kennzahl daraus - jedes Mal neu.

    Kosten über 24 Monate =   Geraetezuzahlung (Anzahlung)
                            + 24 Monate Tarifgrundpreis - phasengewichtet,
                              wenn das Pflichtdokument Preisphasen nennt
                            + ALLE Geraeteraten der eigenen Laufzeit, auch
                              die Restschuld nach Monat 24 (Raten 25-36)
                            + Anschlusspreis

Die Leitzahl ist "Kosten über 24 Monate" (A1 vom 20.09.2026; vorher TCO-24,
Entscheidung E2 vom 03.09.2026), daneben steht Ø/Monat als greifbare
Zweitzahl. Der Horizont von 24 Monaten ist der der Tarifbindung, nicht der
der Geraetefinanzierung - wer 36 Raten waehlt, hat nach 24 Monaten noch
zwoelf offen, und diese Restschuld bleibt GESCHULDET: Sie steht IN der
Kennzahl und zusaetzlich als eigene Zahl daneben (`Tco.restbetrag`).
Bis A1 kappte die Rechnung die Raten bei 24 Monaten und stellte den Rest
daneben - das war die CHECK24-Methodik mit Ausweis, die § 5.4 des
Strategiedokuments verwirft; am echten Bestand vom 20.09.2026 lag dadurch
jedes der 88 scheinbar unter dem Barpreis subventionierten Bündel nur um
seine eigene Restschuld zu niedrig (Messung im Orakel-Test).

Die drei Regeln, die dieses Modul tragen
----------------------------------------
1. **`tco_24` ist eine reine Funktion, keine gespeicherte Zahl.** Ein
   abgelegtes Ergebnis kann seinen Bestandteilen widersprechen; dann steht
   im Datensatz eine Meinung statt einer Messung. Gespeichert werden
   ausschliesslich die Posten - dieselbe Haltung wie bei
   `geraete_model.Ratenzahlung.gesamt`.
2. **Eine fehlende Komponente ist eine LUECKE, keine Null.** Wortgleich aus
   `report/effektivpreis.py`: "Wenn kein Anschlusspreis bekannt ist, heisst
   das nicht kostenlos." Eine TCO mit Luecken wird nie stillschweigend gegen
   eine vollstaendige gestellt (`Tco.belastbar`). 0.0 ist dagegen ein
   GEMESSENER Betrag und keine Luecke - "0 EUR Zuzahlung" ist eine Aussage.
3. **Rabatte werden nie eingerechnet.** Sie stehen benannt und mit ihrer
   Frist daneben (`Rabatt`), und `tco_24` beruehrt sie nicht. Ein Nachlass,
   der in die Kennzahl wandert, macht aus einer Rechnung eine Werbeaussage -
   und aus einem Vergleich eine Rangliste der Marketingphantasie.

Die Felder eines Buendels
-------------------------
    sku_id            welches GERAET (leer = SIM-only, siehe unten)
    anbieter          wer es verkauft
    tarif_name        welcher Tarif - Pflicht. "iPhone fuer 1 Euro" ist ohne
                      den Tarif dahinter eine Zahl ohne Bedeutung (Teil C4,
                      dieselbe Regel wie bei `Listung.zuzahlung`). Der
                      Fremdschluessel auf `tarif_model.Tarif` kommt, sobald
                      es einen gibt (§ 6.2 Nr. 7: Vodafones Nutzlast nennt
                      keinen Tarifnamen); bis dahin IST der Name der
                      Schluessel.
    tarif_monatlich   Grundpreis je Monat, ohne Geraeteanteil
    tarif_phasen      Preisphasen des Tarifs, aus dem Tarifbestand
                      (`tarife.jsonl`) angereichert - wo sie vorliegen,
                      wird der Tarifanteil PHASENGEWICHTET gerechnet statt
                      flach multipliziert. Sie stehen am Objekt und nicht
                      im Store, weil sie zur Tarif-Stammdaten gehoeren und
                      nicht zur Messung des Bündels (A1, 20.09.2026).
                      Anzureichern ist nur ein Blatt OHNE Widerspruch zur
                      Messung (`phasen_fuer_buendel`, QA-Fix 20.09.2026):
                      das Blatt nennt den Tarif ohne Geraetezuschlag,
                      die Karte die gemessene Bündel-Rate.
    geraet_zuzahlung  einmalig bei Vertragsschluss
    geraet_monatsrate die Geraeterate je Monat, NEBEN dem Tarif
    laufzeit_monate   ueber wie viele Monate die Geraeterate laeuft (12,
                      24, 36 und 37 kommen vor) - und `None`, wenn die
                      Quelle das nicht sagt. Es gibt hier KEINE Vorgabe
                      von 24 (P0-B-fix1): die Laufzeit steht im
                      Schluessel, eine geratene verschmilzt den Satz mit
                      dem echten 24-Monats-Angebot
    anschlusspreis    Bereitstellungsentgelt, einmalig
    rabatte           benannt, befristet, separat - nie eingerechnet
    quelle_url        die Seite, auf der DIESE Zahlen stehen
    abgerufen_am      wann sie dort standen

Ein Buendel OHNE Geraet (`sku_id == ""`) ist die SIM-only-Referenz desselben
Tarifs. Sie ist der Grund, warum ein effektiver Geraetepreis ueberhaupt
rechenbar ist: `geraeteanteil()` zieht die eine TCO von der anderen ab, und
was bleibt, ist der Betrag, den der Anbieter fuer das Geraet nimmt - die
Zahl, die auf keiner seiner Seiten steht.

Was dieses Modul bewusst nicht tut
----------------------------------
Es raet nicht. Kein Barpreis wird aus einer Rate geschaetzt (§ 11), keine
Sachleistung bekommt ein Preisschild, und ein Buendel wird nie gegen die
SIM-only-Referenz eines ANDEREN Anbieters oder Tarifs gerechnet - das waere
eine Differenz zweier verschiedener Fragen.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from .geraete_model import Ratenzahlung, normalisiere
from .tarif_model import (
    PREISTYP_DOKUMENT,
    Preisphase,
    vertrag_basis,
)
from .tco_kosten import Kosten as Kosten
from .tco_kosten import kosten_ueber as kosten_ueber
from .tco_kosten import zeitraum as zeitraum

log = logging.getLogger(__name__)

TCO_HORIZONT = 24

_TRENNER = "--"

BUENDEL_SEGMENTE = 5
BUENDEL_SEGMENTE_VOR_B1 = 4

LAUFZEIT_LUECKE = "ohne-laufzeit"

POSTEN_TARIF = "Tarifgrundpreis"
POSTEN_ZUZAHLUNG = "Gerätezuzahlung"
POSTEN_RATE = "Geräterate"
POSTEN_ANSCHLUSS = "Anschlusspreis"
POSTEN_RABATTE = "Boni und Rabatte"
POSTEN_LAUFZEIT = "Ratenlaufzeit"

UNGLEICHER_ZEITRAUM = "Ungleicher Vergleichszeitraum"

_LUECKEN_OHNE_EINFLUSS_AUF_DIE_DIFFERENZ = (POSTEN_RABATTE,)


def laufzeit_in_monaten(laufzeit_monate) -> Optional[int]:
    """Die Ratenlaufzeit als ganze Monatszahl - oder `None` als Luecke.

    DIE EINE STELLE, an der entschieden wird, ob ein Rohwert eine
    Ratenlaufzeit IST (Clean Code 1). `laufzeit_segment` (die ID) und
    `Buendel.__post_init__` (der Datensatz) lesen dasselbe Ergebnis; zwei
    eigene Pruefungen waeren zwei Definitionen derselben Zahl.

    `None` heisst hier immer "keine Ratenlaufzeit", nie "24":
      * fehlt (`None`) - die Quelle nennt keine Dauer,
      * keine Zahl ("ohne Angabe"),
      * kein Ganzes (24,5 Monate gibt es nicht - `int()` hat das bis
        P0-B-fix1 still auf 24 abgeschnitten, und damit war die
        angekuendigte Pruefung "kein Ganzes" eine leere Zusage),
      * null oder negativ - eine Laufzeit von null Monaten ist keine
        Zahlweise,
      * ein Wahrheitswert - `int(True)` waere 1 Monat, und "ja" ist keine
        Dauer.
    Jeder Fall ausser `None` wird protokolliert: ein Rohwert, der keine
    Laufzeit ist, ist eine Nutzlastaenderung und keine Lappalie.
    """
    if laufzeit_monate is None:
        return None
    if isinstance(laufzeit_monate, bool):
        log.warning(
            "Laufzeit %r ist ein Wahrheitswert, keine Monatszahl - "
            "gilt als nicht gemessen",
            laufzeit_monate,
        )
        return None
    try:
        monate = int(laufzeit_monate)
        if monate != float(laufzeit_monate):
            raise ValueError("keine ganze Monatszahl")
    except (TypeError, ValueError):
        log.warning(
            "Laufzeit %r ist keine ganze Monatszahl - gilt als nicht gemessen",
            laufzeit_monate,
        )
        return None
    if monate <= 0:
        log.warning(
            "Laufzeit %r ist keine Ratenlaufzeit - gilt als nicht gemessen",
            laufzeit_monate,
        )
        return None
    return monate


def laufzeit_segment(laufzeit_monate: Optional[int]) -> str:
    """Das Laufzeitsegment der Buendel-ID: `36m` - oder `ohne-laufzeit`.

    Eine fehlende Laufzeit wird BENANNT und nie durch eine 24 ersetzt: eine
    geratene 24 im Schluessel wuerde ein Angebot, dessen Laufzeit die
    Quelle nicht nennt, mit dem echten 24-Monats-Angebot desselben Tarifs
    verschmelzen. Ein nicht bestimmbarer Zustand heisst `unbekannt` und
    wird nie als der Regelfall angenommen (CLAUDE.md, Clean Code 4).

    Was eine Laufzeit sein kann, entscheidet `laufzeit_in_monaten` - hier
    wird nur noch benannt. Diese Funktion WIRFT nicht, auch nicht bei einer
    unmoeglichen Zahl: sie bedient ausser `buendel_id` auch die
    Lesemigration gespeicherter IDs (`buendel_id_aktuell`), und dort darf
    eine einzelne kaputte Altzeile nicht die ganze Zeitreihe kosten. Der
    DATENSATZ ist strenger - `Buendel.__post_init__` weist eine unmoegliche
    Laufzeit als Nutzlastfehler zurueck, statt sie stumm zur Luecke zu
    machen.
    """
    monate = laufzeit_in_monaten(laufzeit_monate)
    return LAUFZEIT_LUECKE if monate is None else f"{monate}m"


def buendel_id(
    sku_id: str, anbieter: str, tarif_name: str, laufzeit_monate: Optional[int]
) -> str:
    """`buendel--<anbieter>--<sku>--<tarif>--<laufzeit>`.

    Ein Buendel ist ein NEUER Datensatz und bekommt eine neue ID. Das ist
    die Lehre aus dem Farbschluessel (`geraete_model.farbe_aus_titel`): eine
    Zuordnung, die bestehende Schluessel neu vergibt, laesst den Altbestand
    als ausgelistet erscheinen und ihn daneben neu entstehen - der Verlauf
    zerfaellt, ohne dass ein Fehler sichtbar wird.

    DIE RATENLAUFZEIT IST SEIT B1 (21.09.2026) TEIL DES SCHLUESSELS. Die
    Anbieter bieten zum SELBEN Tarif mehrere Ratenlaeufe an (Telekom
    6/12/24/36, o2 24/36, congstar 24/36, Vodafone 12/24/36, 1&1 "24+12"
    mit Schlusszahlung). Ohne die Laufzeit im Schluessel ueberschreiben
    sich diese Varianten gegenseitig, und der Bestand zeigt willkuerlich
    eine von ihnen - genau der Grund, aus dem der congstar-Adapter bis
    heute nur die 36er-Zahlweise liefert (`collect/geraete/congstar`).

    Der Altbestand von VOR B1 traegt IDs ohne dieses Segment. Er wird
    nicht umgeschrieben, sondern BEIM LESEN zugeordnet
    (`buendel_id_aktuell`, aufgerufen im Store) - dieselbe Lehre wie oben,
    nur von der anderen Seite.

    Die Namensmengen koennen sich nicht ueberschneiden, und zwar an der
    Form, nicht am Zufall: eine `listung_id` hat ZWEI Bestandteile
    (`o2--apple-iphone-14-128gb-schwarz`), eine Referenz DREI, ein Buendel
    seit B1 FUENF (vorher vier - beides bleibt eindeutig gegen die
    anderen beiden Mengen). Ein Anbieter, der wirklich "Buendel" hiesse,
    ergaebe `buendel--<sku>` - zwei Teile, also weiterhin kein Treffer.

    Fehlt ein Teil, sagt die ID das offen ("ohne-geraet", "ohne-tarif",
    "ohne-laufzeit"), statt ihn wegzulassen - dieselbe Regel wie in
    `sku_id`. Eine ID mit weggelassenem Segment waere kuerzer und damit
    aus der Form gefallen.
    """
    return _TRENNER.join(
        (
            "buendel",
            normalisiere(anbieter) or "ohne-anbieter",
            sku_id or "ohne-geraet",
            normalisiere(tarif_name) or "ohne-tarif",
            laufzeit_segment(laufzeit_monate),
        )
    )


def buendel_id_aktuell(
    gespeicherte_id: str, laufzeit_monate: Optional[int]
) -> Optional[str]:
    """Die heutige Buendel-ID eines GESPEICHERTEN Satzes - Lesemigration B1.

    `data/state/geraete_tco.json` und `geraete_tco_historie.jsonl` tragen
    IDs aus der Zeit vor B1: vier Segmente, ohne Laufzeit. Beide Dateien
    werden NICHT umgeschrieben (CLAUDE.md, harte Regeln 2 und 3) - der
    Altbestand wird beim Lesen demselben Buendel zugeordnet, und zwar aus
    dem Feld, das jede dieser Zeilen ohnehin traegt: `laufzeit_monate`.

    Ohne diese Zuordnung waere jede Zeile von vor B1 einem Buendel
    zugeordnet, das es im Stand nicht mehr gibt: der Altbestand gaelte als
    ausgelistet, entstuende daneben neu, und rund neun Messtage Verlauf
    fielen aus dem Graphen, ohne dass ein Fehler sichtbar wird.

    Gibt `None`, wenn die ID weder die alte noch die neue Form hat - der
    Aufrufer protokolliert sie benannt und verwirft sie nicht still.
    """
    roh = (gespeicherte_id or "").strip()
    if not roh:
        return None
    teile = roh.split(_TRENNER)
    if len(teile) == BUENDEL_SEGMENTE:
        return roh
    if len(teile) != BUENDEL_SEGMENTE_VOR_B1:
        return None
    return _TRENNER.join(teile + [laufzeit_segment(laufzeit_monate)])


def buendel_id_ohne_laufzeit(buendel_id_: str) -> Optional[str]:
    """Die vier Segmente OHNE die Laufzeit - (Anbieter x SKU x Tarif).

    Der gemeinsame Teil aller Laufzeitvarianten eines Angebots. Er ist
    KEIN Bestandsschluessel (zwei Laufzeiten sind zwei Preise, also zwei
    Buendel), sondern nur der Weg zu den laufzeitUNabhaengigen Angaben
    eines Buendels - Anbieter, SKU, Tarifname. Die Zeitreihe braucht ihn,
    wenn eine gemessene Laufzeit im heutigen Stand nicht mehr steht:
    lieber der Punkt mit dem Stamm der Schwestervariante als ein
    verschwiegener Messtag (CLAUDE.md, Fallstricke: "Meldungen werden nie
    gekappt").
    """
    roh = (buendel_id_ or "").strip()
    if not roh:
        return None
    teile = roh.split(_TRENNER)
    if len(teile) not in (BUENDEL_SEGMENTE_VOR_B1, BUENDEL_SEGMENTE):
        return None
    return _TRENNER.join(teile[:BUENDEL_SEGMENTE_VOR_B1])


def sim_only_id(anbieter: str, tarif_name: str) -> str:
    """`simonly--<anbieter>--<tarif>` - drei Bestandteile, siehe oben."""
    return _TRENNER.join(
        (
            "simonly",
            normalisiere(anbieter) or "ohne-anbieter",
            normalisiere(tarif_name) or "ohne-tarif",
        )
    )


@dataclass
class Rabatt:
    """Ein benannter, befristeter Nachlass - und er wird NICHT eingerechnet.

    Er steht im Datensatz, damit die Seite ihn nennen kann ("6 Monate
    10 EUR Wechselbonus"), und er steht ausserhalb der Kennzahl, damit die
    Kennzahl vergleichbar bleibt. Genau daran scheitert die CHECK24-Methodik
    mit ihren "bestenfalls realisierbaren Verguenstigungen" (§ 5.4): wer den
    besten Fall einrechnet, vergleicht Aktionslagen statt Preise.

    Felder:
      name              wie der Anbieter ihn nennt - ohne Namen ist ein
                        Nachlass nicht nachpruefbar, also Pflicht
      betrag_monatlich  Nachlass je Monat innerhalb seiner Frist
      einmalbetrag      einmalige Gutschrift
      von_monat         1-basiert, einschliesslich
      bis_monat         einschliesslich; None = bis zum Horizont
      beleg_url         die Seite, auf der er steht
    """

    name: str
    betrag_monatlich: Optional[float] = None
    einmalbetrag: Optional[float] = None
    von_monat: int = 1
    bis_monat: Optional[int] = None
    beleg_url: str = ""

    def __post_init__(self):
        if not (self.name or "").strip():
            raise ValueError("ein Rabatt ohne Namen ist nicht nachpruefbar")
        self.name = self.name.strip()
        for feld in ("betrag_monatlich", "einmalbetrag"):
            wert = getattr(self, feld)
            if wert is None:
                continue
            wert = float(wert)
            if wert < 0:
                raise ValueError(
                    f"negativer betrag in {feld}: {wert} - ein Rabatt wird "
                    "als positiver Nachlass geschrieben"
                )
            setattr(self, feld, round(wert, 2))
        self.von_monat = int(self.von_monat)
        if self.von_monat < 1:
            raise ValueError(f"von_monat ist 1-basiert: {self.von_monat}")
        if self.bis_monat is not None:
            self.bis_monat = int(self.bis_monat)
            if self.bis_monat < self.von_monat:
                raise ValueError(
                    f"bis_monat vor von_monat: {self.bis_monat} < {self.von_monat}"
                )

    def wert(self, horizont: int = TCO_HORIZONT) -> float:
        """Was dieser Nachlass ueber den Horizont waere - zum ANZEIGEN.

        Keine Rechnung dieses Moduls zieht diesen Betrag ab. Er beantwortet
        die Frage "wie viel Werbung steckt in diesem Angebot", und diese
        Frage gehoert neben die Kennzahl, nicht hinein.
        """
        ende = self.bis_monat if self.bis_monat is not None else horizont
        monate = max(0, min(ende, horizont) - self.von_monat + 1)
        summe = monate * (self.betrag_monatlich or 0.0)
        if self.von_monat <= horizont:
            summe += self.einmalbetrag or 0.0
        return round(summe, 2)


AKTION_TRADE_IN = "trade_in"
AKTION_GERAETERABATT = "geraeterabatt"
AKTION_TARIFRABATT = "tarifrabatt"
AKTION_ANSCHLUSS_ERLASSEN = "anschluss_erlassen"
AKTION_WECHSELBONUS = "wechselbonus"
AKTION_ONLINE_VORTEIL = "online_vorteil"
AKTION_ARTEN = (
    AKTION_TRADE_IN,
    AKTION_GERAETERABATT,
    AKTION_TARIFRABATT,
    AKTION_ANSCHLUSS_ERLASSEN,
    AKTION_WECHSELBONUS,
    AKTION_ONLINE_VORTEIL,
)


@dataclass
class Aktion:
    """Ein Angebotsvorteil mit Bedingung und Quelle (P3-E3).

    Anders als `Rabatt` beschreibt eine Aktion, WORAUS ein Preis besteht
    oder WAS er unter einer Bedingung noch werden kann - sie wird von
    keiner Kennzahl dieses Moduls verrechnet (`tco_24` und `tco_bindung`
    lesen sie nicht):

      eingerechnet=True   der Vorteil steckt schon im gemessenen Preis
                          (congstar: "Bei Abschluss der ANF M ... reduziert
                          sich die monatliche Rate der Hardware"). Er steht
                          hier, damit die Seite sagen kann, woran der Preis
                          haengt - abgezogen wird er kein zweites Mal.
      eingerechnet=False  der Vorteil gilt nur, wenn der Kunde mehr tut als
                          abzuschliessen (Altgeraet eintauschen, Rufnummer
                          mitnehmen). Er bleibt ausserhalb der Leitzahl und
                          erscheint als "bis −X €" daneben.

    Felder:
      art               eine aus `AKTION_ARTEN`
      bedingung         woran der Vorteil haengt, moeglichst im Wortlaut
                        des Anbieters - Pflicht, ohne Bedingung ist es keine
                        pruefbare Aussage
      quelle_url        die Seite, auf der sie steht - Pflicht
      betrag            Vorteil in EUR ueber die ganze Ratenlaufzeit bzw.
                        einmalig; `None` = nicht beziffert
      betrag_monatlich  Vorteil je Monat, wo der Anbieter ihn so nennt
                        (dauerhafter Grundpreisnachlass)
      eingerechnet      siehe oben
      gueltig_bis       ISO-Datum des Aktionsendes, "" = nicht genannt
    """

    art: str
    bedingung: str
    quelle_url: str
    betrag: Optional[float] = None
    betrag_monatlich: Optional[float] = None
    eingerechnet: bool = False
    gueltig_bis: str = ""

    def __post_init__(self):
        if self.art not in AKTION_ARTEN:
            raise ValueError(f"unbekannte Aktionsart: {self.art!r}")
        self.bedingung = (self.bedingung or "").strip()
        if not self.bedingung:
            raise ValueError("eine Aktion ohne Bedingung ist nicht nachpruefbar")
        self.quelle_url = (self.quelle_url or "").strip()
        if not self.quelle_url:
            raise ValueError("eine Aktion ohne Quelle ist nicht nachpruefbar")
        for feld in ("betrag", "betrag_monatlich"):
            wert = getattr(self, feld)
            if wert is None:
                continue
            wert = float(wert)
            if wert < 0:
                raise ValueError(
                    f"negativer Vorteil in {feld}: {wert} - "
                    f"eine Aktion wird als positiver Betrag "
                    f"geschrieben"
                )
            setattr(self, feld, round(wert, 2))
        self.eingerechnet = bool(self.eingerechnet)
        self.gueltig_bis = (self.gueltig_bis or "").strip()

    def gilt_am(self, heute: str) -> bool:
        """Laeuft die Aktion am Tag `heute` ("YYYY-MM-DD") noch? Ohne
        genanntes Ende oder ohne Datum gilt sie - abgelaufen ist nur, was
        der Anbieter selbst befristet hat."""
        return not (self.gueltig_bis and heute and self.gueltig_bis < heute)


def aktionen_aus(rohsaetze) -> list[Aktion]:
    """Aktions-Rohsaetze (dicts aus Adapter oder Speicher) in `Aktion`en.

    Eine kaputte Aktion faellt mit Protokoll weg, die uebrigen und das
    Buendel bleiben - ein unlesbarer Vorteil darf keinen gemessenen Preis
    kosten. Dieselbe Funktion fuer den Sammel- und den Leseweg, damit beide
    dieselben Aktionen als gueltig ansehen."""
    fertig: list[Aktion] = []
    for roh in rohsaetze or []:
        if isinstance(roh, Aktion):
            fertig.append(roh)
            continue
        try:
            fertig.append(Aktion(**roh))
        except (TypeError, ValueError) as exc:
            log.warning("Aktion uebergangen: %s (%r)", exc, roh)
    return fertig


@dataclass
class Buendel:
    """EIN Angebot aus Geraet und Tarif bei EINEM Anbieter.

    Der Schluessel ist (SKU x Anbieter x Tarif x Ratenlaufzeit) - dasselbe
    Geraet beim selben Anbieter zu zwei Tarifen sind zwei Buendel, weil es
    zwei Preise sind, und derselbe Tarif in zwei Zahlweisen (24 und 36
    Raten) ebenfalls. Die Laufzeit steht seit B1 im Schluessel
    (`buendel_id`); vorher ueberschrieben sich die Zahlweisen still. Die
    Feldbedeutungen stehen im Modulkopf.

    Es gibt hier bewusst KEIN `preis_ohne_vertrag`. Der Gesamtbetrag der
    Geraeteraten ist eine Ratenzahlung und keine Kassenzahl; ihn in dasselbe
    Feld zu schreiben wie einen Barpreis war der Befund, mit dem dieses
    Vorhaben angefangen hat (o2, 03.09.2026: 721,00 EUR standen in derselben
    Spalte wie freenets 949,00 EUR Barpreis).
    """

    sku_id: str = ""
    anbieter: str = ""
    tarif_name: str = ""
    tarif_id: str = ""
    tarif_id_guete: str = ""
    tarif_monatlich: Optional[float] = None
    tarif_bindung_monate: Optional[int] = None
    buendel_monatlich: Optional[float] = None
    geraet_zuzahlung: Optional[float] = None
    geraet_monatsrate: Optional[float] = None
    laufzeit_monate: Optional[int] = None
    anschlusspreis: Optional[float] = None
    rabatte: list[Rabatt] = field(default_factory=list)
    aktionen: list[Aktion] = field(default_factory=list)
    quelle_url: str = ""
    abgerufen_am: str = ""
    herleitung: str = ""
    zustand: str = ""
    tarif_phasen: list[Preisphase] = field(default_factory=list)

    def __post_init__(self):
        if not (self.anbieter or "").strip():
            raise ValueError("ein Buendel ohne Anbieter ist keins")
        if not (self.tarif_name or "").strip():
            raise ValueError("ein Buendel ohne Tarif ist keins")
        self.anbieter = self.anbieter.strip()
        self.tarif_name = self.tarif_name.strip()
        self.sku_id = (self.sku_id or "").strip()
        self.zustand = (self.zustand or "").strip().lower()
        for feld in (
            "tarif_monatlich",
            "buendel_monatlich",
            "geraet_zuzahlung",
            "geraet_monatsrate",
            "anschlusspreis",
        ):
            wert = getattr(self, feld)
            if wert is None:
                continue
            wert = float(wert)
            if wert < 0:
                raise ValueError(f"negativer preis in {feld}: {wert}")
            setattr(self, feld, round(wert, 2))
        if self.buendel_monatlich is not None and (
            self.tarif_monatlich is not None or self.geraet_monatsrate is not None
        ):
            raise ValueError(
                "ein Buendelmonatspreis steht ANSTELLE von "
                "Tarifpreis und Geraeterate, nicht daneben"
            )
        if self.tarif_bindung_monate is not None:
            self.tarif_bindung_monate = int(self.tarif_bindung_monate)
            if self.tarif_bindung_monate < 0:
                raise ValueError(f"negative Tarifbindung: {self.tarif_bindung_monate}")
        if self.laufzeit_monate is not None:
            monate = laufzeit_in_monaten(self.laufzeit_monate)
            if monate is None:
                raise ValueError(
                    f"laufzeit_monate ist keine Ratenlaufzeit: {self.laufzeit_monate!r}"
                )
            self.laufzeit_monate = monate
        if not self.sku_id and (
            self.geraet_zuzahlung is not None
            or self.geraet_monatsrate is not None
            or self.buendel_monatlich is not None
        ):
            raise ValueError(
                "Geraetepreis ohne SKU: ein Buendel ohne Geraet "
                "kann keine Zuzahlung und keine Rate tragen"
            )

    @property
    def id(self) -> str:
        return buendel_id(
            self.sku_id, self.anbieter, self.tarif_name, self.laufzeit_monate
        )

    @property
    def ohne_geraet(self) -> bool:
        """Eine SIM-only-Zeile. Ihr FEHLT kein Geraet - sie hat keins."""
        return not self.sku_id

    @property
    def geraeteraten(self) -> Optional[Ratenzahlung]:
        """Die Geraetefinanzierung als eigene Groesse.

        Dieselbe Struktur, die eine Listung fuer ihren Ratengesamtbetrag
        benutzt (`geraete_model.Ratenzahlung`) - eine Zuzahlung mit Rate
        IST ein Teilzahlungsgeschaeft, nur innerhalb eines Vertrags. Damit
        kennt das Buendel den vollen Geraetepreis (`.gesamt`) und seine
        Rechenprobe, ohne beides ein zweites Mal zu rechnen.
        """
        if (
            self.geraet_zuzahlung is None
            or self.geraet_monatsrate is None
            or self.laufzeit_monate is None
        ):
            return None
        return Ratenzahlung(
            anzahlung=self.geraet_zuzahlung,
            monatsrate=self.geraet_monatsrate,
            laufzeit_monate=self.laufzeit_monate,
        )


@dataclass
class SimOnlyReferenz:
    """Derselbe Tarif OHNE Geraet - der Massstab je Anbieter und Tarif.

    Ohne sie ist der Geraeteanteil eines Buendels nicht bestimmbar: 44,99 EUR
    im Monat sagen nichts darueber, was das Telefon kostet, solange niemand
    weiss, was der Tarif allein kostet. Anbieter weisen diese Zahl aus, sie
    steht nur woanders - deshalb ist sie ein eigener Datensatz und keine
    Schaetzung.

    `tarif_sim_only_monatlich` ist der Grundpreis desselben Tarifs ohne
    Hardware. Der Name traegt "sim_only" ausgeschrieben, weil ein blosses
    `monatlich` neben `Buendel.tarif_monatlich` genau die Verwechslung
    einlaedt, gegen die dieser Datensatz gebaut ist.

    `quelle_art` uebernimmt `Tarif.preistyp` (`dokument` | `live_shop`) -
    die Seite braucht sie, um ihren Beleglink richtig zu beschriften:
    "Produktinformationsblatt" fuer ein Pflichtdokument, "Shop-Seite" fuer
    eine Live-Lesart. Der Vorgabewert ist `dokument`, damit ein Satz aus
    der Zeit vor dem 05.09.2026 beim Wiedereinlesen genau das bleibt, was
    er war (dieselbe Ueberlegung wie bei `Tarif.preistyp`).

    `bindung_monate` und `volumen_gb` (seit S-5, 09.09.2026) sind
    Messfelder wie die Preise: sie stehen nur da, wo eine erhobene Quelle
    sie nennt. Die SIM-only-Seite von 1&1 misst das Volumen je Kachel und
    nennt KEINE Bindungsdauer - ihr Referenzsatz traegt also 10.0 GB und
    `bindung_monate=None`, und beides ist die Aussage. Vor S-5 gab es die
    Felder nicht; alte Saetze bleiben ohne sie lesbar (Vorgabe `None`).
    """

    anbieter: str = ""
    tarif_name: str = ""
    tarif_id: str = ""
    tarif_id_guete: str = ""
    tarif_sim_only_monatlich: Optional[float] = None
    anschlusspreis: Optional[float] = None
    rabatte: list[Rabatt] = field(default_factory=list)
    quelle_url: str = ""
    abgerufen_am: str = ""
    quelle_art: str = PREISTYP_DOKUMENT
    bindung_monate: Optional[int] = None
    volumen_gb: Optional[float] = None

    def __post_init__(self):
        if not (self.anbieter or "").strip():
            raise ValueError("eine SIM-only-Referenz ohne Anbieter ist keine")
        if not (self.tarif_name or "").strip():
            raise ValueError("eine SIM-only-Referenz ohne Tarif ist keine")
        self.anbieter = self.anbieter.strip()
        self.tarif_name = self.tarif_name.strip()
        for feld in ("tarif_sim_only_monatlich", "anschlusspreis"):
            wert = getattr(self, feld)
            if wert is None:
                continue
            wert = float(wert)
            if wert < 0:
                raise ValueError(f"negativer preis in {feld}: {wert}")
            setattr(self, feld, round(wert, 2))
        if self.bindung_monate is not None:
            if int(self.bindung_monate) < 0:
                raise ValueError(f"negative bindung_monate: {self.bindung_monate}")
            self.bindung_monate = int(self.bindung_monate)
        if self.volumen_gb is not None:
            if float(self.volumen_gb) < 0:
                raise ValueError(f"negatives volumen_gb: {self.volumen_gb}")
            self.volumen_gb = round(float(self.volumen_gb), 1)

    @property
    def id(self) -> str:
        return sim_only_id(self.anbieter, self.tarif_name)

    def als_buendel(self) -> Buendel:
        """Dieselbe Rechnung, ein Rechenweg.

        Eine SIM-only-Zeile ist ein Buendel ohne Geraet. Sie so zu fuehren
        heisst, dass `tco_24` fuer beide Seiten der Differenz DIESELBE
        Funktion ist - zwei Rechenwege waeren zwei Rechnungen, und ihre
        Differenz waere keine Aussage ueber den Geraetepreis, sondern ueber
        den Unterschied der Wege.
        """
        return Buendel(
            sku_id="",
            anbieter=self.anbieter,
            tarif_name=self.tarif_name,
            tarif_id=self.tarif_id,
            tarif_id_guete=self.tarif_id_guete,
            tarif_monatlich=self.tarif_sim_only_monatlich,
            anschlusspreis=self.anschlusspreis,
            rabatte=list(self.rabatte),
            quelle_url=self.quelle_url,
            abgerufen_am=self.abgerufen_am,
        )


def monatsschnitt(gesamt: Optional[float], monate: Optional[int]) -> Optional[float]:
    """Ø/Monat: eine Summe geteilt durch IHREN eigenen Zeitraum.

    DIE EINE STELLE dieser Division (P0-B-h1, Clean Code 1). Bis hierher
    teilte `tco_24` fest durch `TCO_HORIZONT` - auch die Summe eines
    zusammengelegten Buendelmonatspreises, die 36 Monate traegt. Auf der
    Seite stand daraufhin "Kosten über 36 Monate 2.019,54 € · Ø 84,15
    €/Monat"; 84,15 × 36 = 3.029,40 EUR, eine Zahl, die aus keiner
    Definition dieser Seite folgt. Der Schnitt ueber den ausgewiesenen
    Zeitraum ist 2.019,54 / 36 = 56,10 EUR.

    Die Gegenrechnung, die nach dieser Funktion auf JEDER Zeile aufgeht:
    `Ø × Zeitraum == Summe` (bis auf einen Cent Rundung je Monat).

    `None` ohne Summe und ohne gemessenen Zeitraum - ein Ø ohne bekannte
    Zahl von Monaten ist nicht bestimmbar, und ein Teiler 24 waere
    geraten (Clean Code 3). `monate <= 0` ist kein Zeitraum.
    """
    if gesamt is None or monate is None or monate <= 0:
        return None
    return round(gesamt / monate, 2)


def zeitraum_vergleichbar(monate: Optional[int], andere: Optional[int]) -> bool:
    """Duerfen zwei Leitzahlen gegeneinander gestellt werden?

    Nur bei GLEICHEM Zeitraum. Eine 36-Monats-Summe gegen eine
    24-Monats-Summe ist ein Laufzeitunterschied und kein Preisabstand;
    allein die zwoelf Tarifmonate jenseits des Horizonts (mindestens
    12 × 14,99 = 179,88 EUR nach dem Tarifstamm) sind groesser als jedes
    bisher ausgewiesene Delta.

    Ein unbekannter Zeitraum (`None`) ist NIE gleich - er faellt aus dem
    Vergleich heraus (Clean Code 4). Die EINE Regel dazu: die
    Kartenschicht (`report/geraete_tco_karten.gleicher_horizont`) liest
    die zwei Felder und fragt hier, statt die Regel zu wiederholen.
    """
    return monate is not None and andere is not None and monate == andere


def phasensumme(phasen: list[Preisphase], horizont: int) -> Optional[float]:
    """Die Summe der Monatsentgelte ueber den Horizont - phasengewichtet.

    Der Kern der Tarif-Rechnung, seit A1 (20.09.2026) Teil des Moduls der
    Leitzahl: Leitzahl und Effektivpreis teilen EINE phasengewichtete Summe,
    sonst rechneten zwei Stellen dasselbe Blatt verschieden
    (`report/effektivpreis.py` re-exportiert sie). Eine Phase ohne Ende
    laeuft bis zum Horizont; eine Phase, die darueber hinausreicht, wird
    gekappt; Monate nach der letzten Phase laufen zum letzten bekannten
    Preis weiter - die vorsichtige Annahme: der letzte Preis eines Tarifs
    ist der Normalpreis, nicht der Rabattpreis.
    """
    if not phasen:
        return None
    summe = 0.0
    abgedeckt = 0
    for phase in sorted(phasen, key=lambda p: p.von_monat):
        monate = phase.monate(horizont)
        if monate <= 0:
            continue
        summe += monate * phase.betrag
        abgedeckt += monate
    if abgedeckt <= 0:
        return None
    if abgedeckt < horizont:
        letzter = sorted(phasen, key=lambda p: p.von_monat)[-1]
        summe += (horizont - abgedeckt) * letzter.betrag
    return round(summe, 2)


@dataclass
class Tco:
    """Das Ergebnis einer TCO-Rechnung - mit allem, was ihr fehlt.

    Felder:
      gesamt        die Leitzahl ueber den Horizont, None ohne jeden Posten
                    (seit A1 INKLUSIVE Restschuld, siehe `restbetrag`)
      horizont      der TARIFHORIZONT der Rechnung (24, E2) - wie viele
                    Tarifmonate gezaehlt wurden, nicht der Zeitraum der
                    Leitzahl
      leitzahl_monate
                    DER ZEITRAUM, DEN `gesamt` WIRKLICH TRAEGT, und der
                    Teiler von `monatlich` (P0-B-h1). Bei der aufgeteilten
                    Preisform ist das der Tarifhorizont; bei einem
                    zusammengelegten Buendelmonatspreis (1&1) dessen ganze
                    Laufzeit, weil dieser EINE Betrag Tarif und Geraet
                    ueber alle seine Monate traegt. `None`, wenn die
                    Laufzeit nicht gemessen ist - dann ist die Kennzahl
                    ohnehin unbelastbar (`POSTEN_LAUFZEIT`). Jeder Leser -
                    Etikett, Ø/Monat, Δ-Tor, Export - nimmt den Zeitraum
                    aus DIESEM Feld und rechnet ihn nie nach.
      monatlich     Ø/Monat - die Zweitzahl der Seite, `gesamt` geteilt
                    durch `leitzahl_monate` (`monatsschnitt`)
      bestandteile  Posten -> Betrag, in der Reihenfolge der Rechnung
      luecken       benannte fehlende Komponenten (§ 6.4)
      restbetrag    der Anteil der Leitzahl, der nach Monat 24 noch faellig
                    bleibt (Raten 25-36; 0.0 bei Laufzeit <= 24 ist eine
                    gemessene Aussage, kein fehlender Wert)
      rabatte_offen was an benannten Nachlaessen NICHT abgezogen wurde
    """

    gesamt: Optional[float] = None
    horizont: int = TCO_HORIZONT
    leitzahl_monate: Optional[int] = None
    monatlich: Optional[float] = None
    bestandteile: dict = field(default_factory=dict)
    luecken: list[str] = field(default_factory=list)
    restbetrag: Optional[float] = None
    rabatte_offen: float = 0.0

    @property
    def belastbar(self) -> bool:
        """Ohne Tarifgrundpreis ist die Zahl keine TCO.

        Dieselbe Schwelle wie `effektivpreis.Effektivpreis.belastbar`: die
        uebrigen Luecken machen die Zahl unvollstaendig, diese eine macht
        sie sinnlos. Eine unbelastbare TCO wird nie gegen eine andere
        gestellt.

        Die fehlende RATENLAUFZEIT wirkt genauso (P0-B-fix1): ohne sie
        fehlt der ganze Monatsblock - beim Buendelmonatspreis der Tarif
        MITSAMT Geraet, bei der aufgeteilten Form die Ratensumme. Was
        uebrig bliebe, waeren Zuzahlung und Anschlusspreis, und die saehen
        als "Kosten über 24 Monate" nach einem sehr guenstigen Angebot aus.
        """
        return (
            self.gesamt is not None
            and POSTEN_TARIF not in self.luecken
            and POSTEN_LAUFZEIT not in self.luecken
        )


def tco_24(buendel: Buendel) -> Tco:
    """Die Leitzahl eines Buendels: Kosten ueber 24 Monate.

    Eine REINE Funktion - gleiche Posten, gleiches Ergebnis, kein Zustand,
    nichts gespeichert. Der Horizont steht fest (E2); die Ratenlaufzeit des
    Geraets darf davon abweichen, und was jenseits liegt, bleibt geschuldet:
    Es steht IN der Kennzahl und zusaetzlich in `restbetrag` ausgewiesen
    (A1, 20.09.2026).

    Zwei Preisformen, eine Rechnung
    -------------------------------
    * **aufgeteilt** (o2 u.a.): Tarifgrundpreis und Geraeterate stehen
      getrennt. Der Tarif zaehlt 24 Monate - PHASENGEWICHTET, wenn das
      Bündel Preisphasen traegt ("12 Monate 10 EUR, danach 20 EUR"), sonst
      flach. Die Rate zaehlt ALLE Monate ihrer eigenen Laufzeit, auch die
      nach Monat 24. Wer die Phasen anreichert, sorgt dafuer, dass sie
      die gemessene Monatsrate nicht ueberstimmen (`phasen_fuer_buendel`,
      QA-Fix 20.09.2026): diese Funktion vertraut ihrem Feld.
    * **zusammen** (1&1, `buendel_monatlich`): der Anbieter nennt EINEN
      Monatsbetrag fuer Tarif und Geraet (§ 13.2 der Strategie - ihn
      aufzuteilen waere eine Rechnung dieses Projekts). Er wird als EIN
      Posten ueber seine ganze Laufzeit gefuehrt - und damit traegt die
      Leitzahl DIESEN Zeitraum (`leitzahl_monate`, P0-B-h1) und nicht die
      24 Monate des Tarifhorizonts. Die GERAETEZUZAHLUNG steht daneben
      als ihr eigener Posten (S2-C, 09.09.2026: 1&1 nennt sie je Variante
      in `hwdVariantsOneOffPaymentFees`).

    Der Pflichtfall des Auftrags (A1): congstar Allnet Flat XS zum iPhone
    17 Pro 256 GB - 1 + 24 × 15,00 + 36 × 30,50 + 0 = 1.459,00 EUR. Die
    bis zum 20.09.2026 gueltige gekappte Zahl (1.093,00 EUR) ist genau um
    die Restschuld (366,00 EUR) zu niedrig und darf nie wieder als
    Leitzahl auftauchen (`tests/test_geraete_tco_orakel.py` haelt das am
    echten Bestand fest).
    """
    ergebnis = Tco(horizont=TCO_HORIZONT)
    laufzeit = buendel.laufzeit_monate
    offen_monate = None if laufzeit is None else max(0, laufzeit - TCO_HORIZONT)

    if buendel.buendel_monatlich is not None:
        ergebnis.leitzahl_monate = laufzeit
        if laufzeit is None:
            ergebnis.luecken.append(POSTEN_LAUFZEIT)
        else:
            ergebnis.bestandteile[f"{POSTEN_BUENDEL} über {laufzeit} Monate"] = round(
                buendel.buendel_monatlich * laufzeit, 2
            )
            ergebnis.restbetrag = round(buendel.buendel_monatlich * offen_monate, 2)
        if buendel.geraet_zuzahlung is not None:
            ergebnis.bestandteile[POSTEN_ZUZAHLUNG] = buendel.geraet_zuzahlung
        else:
            ergebnis.luecken.append(POSTEN_ZUZAHLUNG)
    else:
        ergebnis.leitzahl_monate = TCO_HORIZONT
        tarif_summe = (
            phasensumme(buendel.tarif_phasen, TCO_HORIZONT)
            if buendel.tarif_phasen
            else None
        )
        if tarif_summe is not None:
            ergebnis.bestandteile[f"Tarif über {TCO_HORIZONT} Monate"] = tarif_summe
        elif buendel.tarif_monatlich is not None:
            ergebnis.bestandteile[f"Tarif über {TCO_HORIZONT} Monate"] = round(
                buendel.tarif_monatlich * TCO_HORIZONT, 2
            )
        else:
            ergebnis.luecken.append(POSTEN_TARIF)

        if not buendel.ohne_geraet:
            if buendel.geraet_zuzahlung is not None:
                ergebnis.bestandteile[POSTEN_ZUZAHLUNG] = buendel.geraet_zuzahlung
            else:
                ergebnis.luecken.append(POSTEN_ZUZAHLUNG)

            if buendel.geraet_monatsrate is None:
                ergebnis.luecken.append(POSTEN_RATE)
            elif laufzeit is None:
                ergebnis.luecken.append(POSTEN_LAUFZEIT)
            else:
                ergebnis.bestandteile[f"Geräteraten über {laufzeit} Monate"] = round(
                    buendel.geraet_monatsrate * laufzeit, 2
                )
                ergebnis.restbetrag = round(buendel.geraet_monatsrate * offen_monate, 2)

    if buendel.anschlusspreis is not None:
        ergebnis.bestandteile[POSTEN_ANSCHLUSS] = buendel.anschlusspreis
    else:
        ergebnis.luecken.append(POSTEN_ANSCHLUSS)

    if buendel.rabatte:
        ergebnis.rabatte_offen = round(
            sum(r.wert(TCO_HORIZONT) for r in buendel.rabatte), 2
        )
    else:
        ergebnis.luecken.append(POSTEN_RABATTE)

    if ergebnis.bestandteile:
        ergebnis.gesamt = round(sum(ergebnis.bestandteile.values()), 2)
        ergebnis.monatlich = monatsschnitt(ergebnis.gesamt, ergebnis.leitzahl_monate)
    return ergebnis


@dataclass
class Geraeteanteil:
    """Was der Anbieter fuer das GERAET nimmt - und was daran fehlt.

    `betrag` kann negativ sein. Das ist kein Rechenfehler, sondern ein
    subventioniertes Geraet: dann ist das Buendel ueber 24 Monate billiger
    als derselbe Tarif ohne Hardware. Ein Abschneiden bei null waere eine
    stille Korrektur der Marktlage.
    """

    betrag: Optional[float] = None
    horizont: int = TCO_HORIZONT
    tco_buendel: Optional[float] = None
    tco_sim_only: Optional[float] = None
    luecken: list[str] = field(default_factory=list)

    @property
    def belastbar(self) -> bool:
        """Nur eine auf BEIDEN Seiten vollstaendige Rechnung ergibt einen
        Geraetepreis. Fehlt der SIM-only-Grundpreis, enthaelt die Differenz
        den ganzen Tarif und ist um Hunderte Euro zu hoch.

        Dasselbe gilt fuer zwei verschiedene Zeitraeume
        (`UNGLEICHER_ZEITRAUM`, P0-B-h1): die Luecke steht in der Liste
        und macht die Differenz unbelastbar."""
        return self.betrag is not None and not [
            l for l in self.luecken if l not in _LUECKEN_OHNE_EINFLUSS_AUF_DIE_DIFFERENZ
        ]


def geraeteanteil(buendel: Buendel, referenz: SimOnlyReferenz) -> Geraeteanteil:
    """Der effektive Geraetepreis: `tco_24(Buendel) - tco_24(SIM-only)`.

    Die Zahl, die auf keiner Anbieterseite steht, und die einzige, die zwei
    Buendel verschiedener Anbieter vergleichbar macht.

    Beide Seiten muessen DENSELBEN Anbieter und DENSELBEN Tarif betreffen -
    sonst misst die Differenz den Tarifunterschied und nennt ihn
    Geraetepreis. Das ist ein Fehler im Aufruf und keine Datenluecke,
    deshalb faellt er als Ausnahme auf und nicht als Luecke.

    WORAN "DERSELBE TARIF" GEMESSEN WIRD (geaendert am 04.09.2026)
    --------------------------------------------------------------
    Zuerst am `tarif_id`, und nur ersatzweise am Namen. Der Name ist, was
    auf der jeweiligen Seite stand; die ID ist der aufgeloeste
    Fremdschluessel auf `data/state/tarife.jsonl`, und ihn zu haben ist bei
    einem Buendel ohnehin Bedingung (`TcoDB.upsert_buendel`).

    Der Unterschied ist an o2 gemessen: der Geraetekatalog nennt seinen
    Tarif "O2 Mobile on Demand M Plus mit 50 GB+ (24 Mon.)", die
    SIM-only-Kachel desselben Tarifs heisst "O2 Mobile on Demand M". Ueber
    den Namen verglichen sind das zwei Tarife, und der Geraeteanteil - die
    Zahl, wegen der dieses Modul existiert - bliebe fuer JEDES o2-Buendel
    leer. Ueber die ID sind es zwei Fassungen desselben Vertrags, und zwar
    weil o2 das selbst so verlinkt (`tarif_bezug.ueber_slug`).

    Der Namensvergleich bleibt als Rueckfall fuer Saetze OHNE ID stehen -
    und er bleibt eine Ausnahme und keine Luecke: zwei verschiedene Tarife
    gegeneinander zu rechnen ist ein Fehler im Aufruf.

    GEMESSEN WIRD DIE ZEITREIHEN-BASIS (B2, 08.09.2026): der Preistyp-
    Zusatz `#live_shop` unterscheidet zwei Lesarten desselben Tariffs, nicht
    zwei Tarife. Die Telekom-Referenz kommt aus der Shop-Kachel (die
    Dublettenregel in `tarif_referenzen.aus_bestand` laesst die Live-Lesart
    vorn), das Buendel loest auf den PIB-Eintrag - bis hier warf genau
    diese Paarung, und der Auffangboden des Renderers machte daraus fuenf
    leere Reiter statt einen Geraeteanteil.

    Die Luecken beider Seiten werden zusammengefuehrt und WEITERGEREICHT:
    fehlt auf einer Seite der Anschlusspreis, ist die Differenz nur so gut
    wie die schlechtere der zwei Rechnungen.
    """
    if normalisiere(buendel.anbieter) != normalisiere(referenz.anbieter):
        raise ValueError(
            f"Buendel und SIM-only-Referenz gehoeren zu "
            f"verschiedenen Anbietern: {buendel.anbieter!r} / "
            f"{referenz.anbieter!r}"
        )
    ids = ((buendel.tarif_id or "").strip(), (referenz.tarif_id or "").strip())
    if all(ids):
        if vertrag_basis(ids[0]) != vertrag_basis(ids[1]):
            raise ValueError(
                f"Buendel und SIM-only-Referenz gehoeren zu "
                f"verschiedenen Tarifen: {ids[0]!r} / {ids[1]!r}"
            )
    elif normalisiere(buendel.tarif_name) != normalisiere(referenz.tarif_name):
        raise ValueError(
            f"Buendel und SIM-only-Referenz gehoeren zu "
            f"verschiedenen Tarifen: {buendel.tarif_name!r} / "
            f"{referenz.tarif_name!r}"
        )
    if buendel.ohne_geraet:
        raise ValueError("ein Buendel ohne Geraet hat keinen Geraeteanteil")

    mit = tco_24(buendel)
    ohne = tco_24(referenz.als_buendel())
    luecken = list(mit.luecken)
    luecken += [l for l in ohne.luecken if l not in luecken]

    vergleichbar = zeitraum_vergleichbar(mit.leitzahl_monate, ohne.leitzahl_monate)
    if not vergleichbar:
        luecken.append(UNGLEICHER_ZEITRAUM)

    ergebnis = Geraeteanteil(
        horizont=TCO_HORIZONT,
        tco_buendel=mit.gesamt,
        tco_sim_only=ohne.gesamt,
        luecken=luecken,
    )
    if vergleichbar and mit.gesamt is not None and ohne.gesamt is not None:
        ergebnis.betrag = round(mit.gesamt - ohne.gesamt, 2)
    return ergebnis


LEITFRAGE_MONATE = 24

KAT_EINMALIG = "einmalig"
KAT_TARIF = "tarif"
KAT_RATEN = "raten"
KAT_BUENDEL = "buendel"
KAT_BONUS = "bonus"

POSTEN_BUENDEL = "Bündelpreis (Tarif und Gerät zusammen)"
POSTEN_TARIFBINDUNG = "Tarifbindung"
POSTEN_TARIF_FLEX = "Tarif ohne Mindestlaufzeit"


@dataclass
class TcoBindung:
    """Die Kennzahl eines Buendels ueber seine eigene Bindungsdauer.

    Felder:
      bindung          ueber wie viele Monate gerechnet wurde (A5.5:
                       max(Tarifbindung, Ratenlaufzeit))
      tarif_bindung    Mindestlaufzeit des Tarifs, aus dem Tarifbestand
      raten_laufzeit   Laufzeit der Geraeteraten, aus der Anbieternutzlast
      gesamt           die Leitzahl `TCO-<bindung>`
      schnitt_monat    gesamt / bindung - das einzige laufzeituebergreifend
                       zulaessige Vergleichsmass (A5.3)
      gezahlt_nach_24  was der Kunde nach 24 Monaten gezahlt HAT (A5.2)
      offen_nach_24    was danach noch offen ist (A5.2)
      bestandteile     [{name, betrag, kategorie}] in Rechenreihenfolge
      luecken          benannte fehlende Posten - nie als Null gerechnet
      boni             die abgezogenen Nachlaesse, einzeln mit Bedingung
      boni_abzug       ihre Summe (positiv), bereits in `gesamt` abgezogen
    """

    bindung: Optional[int] = None
    tarif_bindung: Optional[int] = None
    raten_laufzeit: Optional[int] = None
    gesamt: Optional[float] = None
    schnitt_monat: Optional[float] = None
    gezahlt_nach_24: Optional[float] = None
    offen_nach_24: Optional[float] = None
    bestandteile: list = field(default_factory=list)
    luecken: list[str] = field(default_factory=list)
    boni: list = field(default_factory=list)
    boni_abzug: float = 0.0

    @property
    def belastbar(self) -> bool:
        """Dieselbe Schwelle wie `Tco.belastbar`, eine Ebene weiter.

        Ohne Bindungsdauer gibt es keine Leitzahl - `TCO-?` ist keine
        Beschriftung (A5.1). Und ohne Tarifanteil ist die Zahl der
        Geraetebetrag und keine TCO.
        """
        return (
            self.gesamt is not None
            and self.bindung is not None
            and POSTEN_TARIF not in self.luecken
            and POSTEN_TARIFBINDUNG not in self.luecken
            and POSTEN_TARIF_FLEX not in self.luecken
            and POSTEN_LAUFZEIT not in self.luecken
        )

    @property
    def label(self) -> str:
        """`TCO-36` - die Laufzeit steht IM Namen (A5.1)."""
        return f"TCO-{self.bindung}" if self.bindung else "TCO"


def tco_bindung(buendel: Buendel) -> TcoBindung:
    """Die Leitzahl eines Buendels ueber seine Bindung - eine reine Funktion.

    Zwei Preisformen, eine Rechnung:

    * **aufgeteilt** (o2): Tarifgrundpreis und Geraeterate stehen getrennt,
      und sie laufen verschieden lang. Der Tarif zaehlt seine
      Mindestlaufzeit, die Rate ihre Ratenlaufzeit, und die Karte fuehrt die
      laengere der beiden (A5.5).
    * **zusammen** (1&1): der Anbieter nennt EINEN Monatsbetrag fuer Tarif
      und Geraet. Ihn aufzuteilen waere eine Rechnung dieses Projekts und
      keine Angabe des Anbieters (§ 13.2 der Strategie) - also wird er als
      ein Posten gefuehrt und als solcher beschriftet.

    Was fehlt, wird als fehlend gefuehrt: eine Luecke ist nie eine Null
    (§ 6.4, wortgleich aus `effektivpreis.py`). 0.0 dagegen IST ein
    gemessener Betrag - "kein Anschlusspreis" und "Anschlusspreis 0 EUR"
    sind zwei verschiedene Auskuenfte.
    """
    e = TcoBindung()

    zusammen = buendel.buendel_monatlich is not None
    e.raten_laufzeit = (
        buendel.laufzeit_monate
        if (zusammen or buendel.geraet_monatsrate is not None)
        else None
    )
    e.tarif_bindung = buendel.tarif_bindung_monate

    if zusammen:
        e.bindung = buendel.laufzeit_monate
    else:
        laengen = [x for x in (e.tarif_bindung, e.raten_laufzeit) if x]
        e.bindung = max(laengen) if laengen else None

    if zusammen and buendel.laufzeit_monate is None:
        e.luecken.append(POSTEN_LAUFZEIT)
    elif zusammen:
        e.bestandteile.append(
            {
                "name": f"{POSTEN_BUENDEL} · {buendel.laufzeit_monate} × "
                f"{buendel.buendel_monatlich:.2f} €".replace(".", ","),
                "betrag": round(buendel.buendel_monatlich * buendel.laufzeit_monate, 2),
                "kategorie": KAT_BUENDEL,
            }
        )
    elif buendel.tarif_monatlich is None:
        e.luecken.append(POSTEN_TARIF)
    elif e.tarif_bindung:
        e.bestandteile.append(
            {
                "name": f"Tarif · {e.tarif_bindung} × "
                f"{buendel.tarif_monatlich:.2f} €".replace(".", ","),
                "betrag": round(buendel.tarif_monatlich * e.tarif_bindung, 2),
                "kategorie": KAT_TARIF,
            }
        )
    elif e.tarif_bindung == 0:
        e.luecken.append(POSTEN_TARIF_FLEX)
    else:
        e.luecken.append(POSTEN_TARIFBINDUNG)

    if not buendel.ohne_geraet and not zusammen:
        if buendel.geraet_zuzahlung is not None:
            e.bestandteile.append(
                {
                    "name": POSTEN_ZUZAHLUNG,
                    "betrag": buendel.geraet_zuzahlung,
                    "kategorie": KAT_EINMALIG,
                }
            )
        else:
            e.luecken.append(POSTEN_ZUZAHLUNG)
        if buendel.geraet_monatsrate is None:
            e.luecken.append(POSTEN_RATE)
        elif buendel.laufzeit_monate is None:
            e.luecken.append(POSTEN_LAUFZEIT)
        else:
            e.bestandteile.append(
                {
                    "name": f"Geräteraten · {buendel.laufzeit_monate} × "
                    f"{buendel.geraet_monatsrate:.2f} €".replace(".", ","),
                    "betrag": round(
                        buendel.geraet_monatsrate * buendel.laufzeit_monate, 2
                    ),
                    "kategorie": KAT_RATEN,
                }
            )

    if buendel.anschlusspreis is not None:
        e.bestandteile.append(
            {
                "name": POSTEN_ANSCHLUSS,
                "betrag": buendel.anschlusspreis,
                "kategorie": KAT_EINMALIG,
            }
        )
    else:
        e.luecken.append(POSTEN_ANSCHLUSS)

    if buendel.rabatte and e.bindung:
        for r in buendel.rabatte:
            wert = r.wert(e.bindung)
            if not wert:
                continue
            e.boni.append({"name": r.name, "betrag": wert, "beleg_url": r.beleg_url})
            e.bestandteile.append(
                {"name": f"Bonus · {r.name}", "betrag": -wert, "kategorie": KAT_BONUS}
            )
        e.boni_abzug = round(sum(b["betrag"] for b in e.boni), 2)
    elif not buendel.rabatte:
        e.luecken.append(POSTEN_RABATTE)

    if not e.bestandteile:
        return e

    e.gesamt = round(sum(p["betrag"] for p in e.bestandteile), 2)
    e.schnitt_monat = monatsschnitt(e.gesamt, e.bindung)

    gezahlt = 0.0
    for p in e.bestandteile:
        if p["kategorie"] == KAT_EINMALIG:
            gezahlt += p["betrag"]
    if zusammen:
        if buendel.laufzeit_monate is not None:
            gezahlt += round(
                buendel.buendel_monatlich
                * min(LEITFRAGE_MONATE, buendel.laufzeit_monate),
                2,
            )
    else:
        if buendel.tarif_monatlich is not None and e.tarif_bindung:
            gezahlt += round(
                buendel.tarif_monatlich * min(LEITFRAGE_MONATE, e.tarif_bindung), 2
            )
        if (
            buendel.geraet_monatsrate is not None
            and buendel.laufzeit_monate is not None
        ):
            gezahlt += round(
                buendel.geraet_monatsrate
                * min(LEITFRAGE_MONATE, buendel.laufzeit_monate),
                2,
            )
    for r in buendel.rabatte:
        gezahlt -= r.wert(min(LEITFRAGE_MONATE, e.bindung or LEITFRAGE_MONATE))
    e.gezahlt_nach_24 = round(gezahlt, 2)
    e.offen_nach_24 = round(e.gesamt - e.gezahlt_nach_24, 2)
    return e


def effektiv_ohne_geraet(
    kennzahl: TcoBindung, barpreis: Optional[float]
) -> Optional[float]:
    """`Ø/Monat − (Geräte-Barpreis ÷ Bindung)` - die Finanztip-Formel.

    Was bleibt, ist der monatliche Preis des TARIFS, wenn man das Geraet zu
    seinem Marktpreis herausrechnet. Sie beantwortet die Frage, die ein
    Buendelpreis verdeckt: zahle ich hier fuer den Tarif oder fuer das
    Telefon?

    Ohne belegten Barpreis gibt es keine Zahl - **nicht** eine mit einem
    geschaetzten Geraetewert. Das ist E1, und es ist der Grund, warum diese
    Funktion ein `None` zurueckgeben darf.
    """
    if barpreis is None or not kennzahl.belastbar or not kennzahl.bindung:
        return None
    return round(kennzahl.schnitt_monat - barpreis / kennzahl.bindung, 2)
