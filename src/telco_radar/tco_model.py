"""Ein Bündel aus Gerät und Tarif: seine gemessenen Posten, nie eine gespeicherte Summe.

Die Gesamtkosten rechnet genau eine Funktion, `tco_kosten.kosten_ueber` (hier
reexportiert); Definition, Posten je Anbieter und Belege stehen in
`docs/geraete/gesamtkosten.md`. Seite, Export, Preishistorie, Regel 11, SIM-only-
Referenz und Belegwahl rufen sie; eine zweite Rechnung gibt es nicht (die früheren
`tco_24`, `tco_bindung` und `geraeteanteil` sind am 20.11.2026 entfallen, weil sie für
dasselbe 1&1-Bündel drei verschiedene Zahlen lieferten).

Die Regeln, die dieses Modul trägt
----------------------------------
1. **Gespeichert werden ausschließlich die Posten.** Eine abgelegte Summe kann ihren
   Bestandteilen widersprechen; die Preishistorie friert nur das Ergebnis von
   `kosten_ueber` zur Auswertung ein.
2. **Eine fehlende Komponente ist eine LÜCKE, keine Null.** 0.0 ist ein GEMESSENER
   Betrag („0 EUR Zuzahlung“ ist eine Aussage).
3. **Rabatte und bedingte Aktionen werden nie eingerechnet** (`Rabatt`, `Aktion` mit
   `eingerechnet=False`); ein eingerechneter Vorteil steckt schon im gemessenen Preis.

Die Felder eines Buendels
-------------------------
    sku_id            welches GERAET (leer = SIM-only, siehe unten)
    anbieter          wer es verkauft
    tarif_name        welcher Tarif - Pflicht. "iPhone fuer 1 Euro" ist ohne den
                      Tarif dahinter eine Zahl ohne Bedeutung (Teil C4).
    tarif_monatlich   Tarifpreis in Monat 1, wie die Seite ihn zeigt, ohne Geraeteanteil
    tarif_listenpreis derselbe ohne Rabatt, wo der Anbieter ihn getrennt nennt
    tarif_phasen      Preisphasen des Tarifs, PHASENGEWICHTET gerechnet. Die des
                      Tarifbestands (`tarife.jsonl`) sind Stammdaten, kommen beim Lesen
                      dazu und stehen nicht im Store (A1, 20.09.2026), nur ohne
                      Widerspruch zur Messung (`phasen_fuer_buendel`, QA-Fix 20.09.2026:
                      das Blatt nennt den Tarif ohne Geraetezuschlag, die Karte die
                      gemessene Bündel-Rate). Nennt der Anbieter den Preis fuer DIESES
                      Buendel selbst, ist die Phase eine Messung mit Beleg
                      (`tarif_model.Buendelphase`): im Store, vor dem Blatt.
    geraet_zuzahlung  einmalig bei Abschluss für das Gerät: Anzahlung, bei der
                      Tarifwelt der einmalige Gerätepreis (Export „Gerät einmalig“)
    geraet_monatsrate die Geraeterate je Monat, NEBEN dem Tarif
    laufzeit_monate   ueber wie viele Monate die Geraeterate laeuft (12, 24, 36
                      und 37 kommen vor) - und `None`, wenn die Quelle das nicht
                      sagt. Es gibt hier KEINE Vorgabe von 24 (P0-B-fix1): die
                      Laufzeit steht im Schluessel, eine geratene verschmilzt
                      den Satz mit dem echten 24-Monats-Angebot
    anschlusspreis    Bereitstellungsentgelt, einmalig
    rabatte           benannt, befristet, separat - nie eingerechnet
    quelle_url        die Seite, auf der DIESE Zahlen stehen
    abgerufen_am      wann sie dort standen
    pruefung          Vermerk der Prüfstelle (`geraete_pruefstatus`), keine Messung
    quelle_art        mit beleg_id, beleg_status nur am Klick-Bündel (`klickrohsatz`)

Ein Buendel OHNE Geraet (`sku_id == ""`) ist die SIM-only-Referenz desselben Tarifs;
sie läuft durch dieselbe Funktion (`SimOnlyReferenz.als_buendel`).

Was dieses Modul bewusst nicht tut
----------------------------------
Es raet nicht. Kein Barpreis wird aus einer Rate geschaetzt (§ 11), keine Sachleistung
bekommt ein Preisschild, und ein Buendel wird nie gegen die SIM-only-Referenz eines
ANDEREN Anbieters oder Tarifs gerechnet - das waere eine Differenz zweier verschiedener
Fragen.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from .geraete_model import Ratenzahlung, normalisiere
from .tarif_model import PREISTYP_DOKUMENT, Preisphase
from .tarif_phasensumme import phasensumme as phasensumme
from .tarifname import pruefe_tarifname
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
    keiner Kennzahl verrechnet (`kosten_ueber` liest sie nicht):

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

    Der Schluessel ist (SKU x Anbieter x Tarif x Ratenlaufzeit) - dasselbe Geraet beim
    selben Anbieter zu zwei Tarifen sind zwei Buendel, weil es zwei Preise sind, und
    derselbe Tarif in zwei Zahlweisen (24 und 36 Raten) ebenfalls. Die Laufzeit steht
    seit B1 im Schluessel (`buendel_id`); vorher ueberschrieben sich die Zahlweisen
    still. Die Feldbedeutungen stehen im Modulkopf.

    Es gibt hier bewusst KEIN `preis_ohne_vertrag`. Der Gesamtbetrag der Geraeteraten
    ist eine Ratenzahlung und keine Kassenzahl; ihn in dasselbe Feld zu schreiben wie
    einen Barpreis war der Befund, mit dem dieses Vorhaben angefangen hat (o2,
    03.09.2026: 721,00 EUR standen in derselben Spalte wie freenets 949,00 EUR
    Barpreis).
    """

    sku_id: str = ""
    anbieter: str = ""
    tarif_name: str = ""
    tarif_id: str = ""
    tarif_id_guete: str = ""
    tarif_monatlich: Optional[float] = None
    tarif_listenpreis: float | None = None
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
    pruefung: str | None = None
    quelle_art: str = ""
    beleg_id: str = ""
    beleg_status: str = ""

    def __post_init__(self):
        if not (self.anbieter or "").strip():
            raise ValueError("ein Buendel ohne Anbieter ist keins")
        pruefe_tarifname(self.tarif_name, "ein Buendel ohne Tarif ist keins")
        self.anbieter = self.anbieter.strip()
        self.tarif_name = self.tarif_name.strip()
        self.sku_id = (self.sku_id or "").strip()
        self.zustand = (self.zustand or "").strip().lower()
        for feld in (
            "tarif_monatlich",
            "tarif_listenpreis",
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
        pruefe_tarifname(self.tarif_name, "eine SIM-only-Referenz ohne Tarif ist keine")
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

    def als_buendel(self, mit_anschluss: bool = True) -> Buendel:
        """Dieselbe Rechnung, ein Rechenweg.

        Eine SIM-only-Zeile ist ein Buendel ohne Geraet. Sie so zu fuehren
        heisst, dass `kosten_ueber` fuer beide Seiten DIESELBE
        Funktion ist - zwei Rechenwege waeren zwei Rechnungen, und ihre
        Differenz waere keine Aussage ueber den Geraetepreis, sondern ueber
        den Unterschied der Wege. Ohne Anschluss: der Tarif allein (F5).
        """
        return Buendel(
            sku_id="",
            anbieter=self.anbieter,
            tarif_name=self.tarif_name,
            tarif_id=self.tarif_id,
            tarif_id_guete=self.tarif_id_guete,
            tarif_monatlich=self.tarif_sim_only_monatlich,
            anschlusspreis=self.anschlusspreis if mit_anschluss else 0.0,
            rabatte=list(self.rabatte),
            quelle_url=self.quelle_url,
            abgerufen_am=self.abgerufen_am,
        )


def monatsschnitt(gesamt: Optional[float], monate: Optional[int]) -> Optional[float]:
    """Ø/Monat: eine Summe geteilt durch IHREN eigenen Zeitraum.

    DIE EINE STELLE dieser Division (P0-B-h1, Clean Code 1). Bis hierher
    teilte die alte 24-Monats-Rechnung fest durch 24 - auch die Summe eines
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


POSTEN_BUENDEL = "Bündelpreis (Tarif und Gerät zusammen)"
