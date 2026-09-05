"""Was ein Buendel aus Geraet und Tarif wirklich kostet - TCO ueber 24 Monate.

Warum es dieses Modul gibt
--------------------------
Die Geraeteseite vergleicht heute Barpreise. Der halbe Markt verkauft aber
kein Geraet, sondern ein Buendel: 1 EUR Zuzahlung, 24 x 30 EUR Geraeterate,
daneben ein Tarif, dazu ein Anschlusspreis und ein Bonus, der nach sechs
Monaten ausgelaufen ist. Wer davon EINE Zahl in eine Preisspalte schreibt,
schreibt eine Meinung. Dieses Modul haelt die Bestandteile getrennt und
rechnet die Kennzahl daraus - jedes Mal neu.

    TCO-24 =   Geraetezuzahlung
             + min(24, Ratenlaufzeit) x Geraeterate
             + 24 x Tarifgrundpreis
             + Anschlusspreis

Die Leitzahl ist TCO-24 (Entscheidung E2 vom 03.09.2026), daneben steht
Ø/Monat als greifbare Zweitzahl. Das ist der Horizont der Tarifbindung, nicht
der der Geraetefinanzierung - und der Unterschied ist der Grund fuer
`Tco.restbetrag`: wer 36 Raten waehlt, hat nach 24 Monaten noch zwoelf offen.
Diese Raten fallen NICHT unter den Tisch, sie stehen als eigene Zahl neben
der Kennzahl. Eine auf 24 Monate gekappte Zahl ohne diesen Ausweis waere die
CHECK24-Methodik, die § 5.4 des Strategiedokuments ausdruecklich verwirft.

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
    geraet_zuzahlung  einmalig bei Vertragsschluss
    geraet_monatsrate die Geraeterate je Monat, NEBEN dem Tarif
    laufzeit_monate   ueber wie viele Monate die Geraeterate laeuft
                      (Standard 24; 12, 36 und 37 kommen vor)
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

from dataclasses import dataclass, field
from typing import Optional

from .geraete_model import Ratenzahlung, normalisiere
from .tarif_model import PREISTYP_DOKUMENT

# Der Horizont der Leitzahl: 24 Monate, die uebliche Tarifmindestlaufzeit.
# Entscheidung E2 vom 03.09.2026 - dieselbe Zahl und dieselbe Begruendung
# wie `report/effektivpreis.VERGLEICHSMONATE` ("ein Vergleich braucht einen
# gemeinsamen Nenner"). Sie steht hier als eigene Konstante, weil ein Tarif
# und ein Geraetebuendel zwei verschiedene Rechnungen sind; wer eine der
# beiden verschiebt, soll nicht ungewollt die andere verschieben.
TCO_HORIZONT = 24

# Die uebliche Ratenlaufzeit, wenn die Quelle keine nennt. Sie ist eine
# Vorgabe, keine Messung - wo eine Quelle 12 oder 36 ausweist, gilt die.
STANDARD_LAUFZEIT = 24

# Der Trenner der IDs dieses Moduls, wie in `geraete_model.listung_id`: er
# kommt in keinem Slug vor, die ID bleibt also eindeutig zerlegbar.
_TRENNER = "--"

# Die Namen der Posten einer TCO. Eine LUECKE traegt den Namen dessen, was
# fehlt - deshalb dieselbe Konstante fuer beides. Sie stehen hier, weil sie
# an zwei Stellen gebraucht werden (beim Rechnen und beim Auswerten) und
# eine Luecke, die sich nur in einer der zwei Schreibweisen findet, waere
# eine stillschweigend uebergangene.
POSTEN_TARIF = "Tarifgrundpreis"
POSTEN_ZUZAHLUNG = "Gerätezuzahlung"
POSTEN_RATE = "Geräterate"
POSTEN_ANSCHLUSS = "Anschlusspreis"
POSTEN_RABATTE = "Boni und Rabatte"

# Luecken, die eine DIFFERENZ zweier TCO nicht verzerren: Rabatte gehen auf
# keiner der beiden Seiten in die Rechnung ein, ihr Fehlen kuerzt sich also
# heraus. Jede andere Luecke steht nur auf einer Seite und verschiebt den
# Abstand - siehe `Geraeteanteil.belastbar`.
_LUECKEN_OHNE_EINFLUSS_AUF_DIE_DIFFERENZ = (POSTEN_RABATTE,)


# --------------------------------------------------------------------------
# IDs - eine eigene Namensmenge, die keine bestehende beruehrt
# --------------------------------------------------------------------------

def buendel_id(sku_id: str, anbieter: str, tarif_name: str) -> str:
    """`buendel--<anbieter>--<sku>--<tarif>`.

    Ein Buendel ist ein NEUER Datensatz und bekommt eine neue ID. Das ist
    die Lehre aus dem Farbschluessel (`geraete_model.farbe_aus_titel`): eine
    Zuordnung, die bestehende Schluessel neu vergibt, laesst den Altbestand
    als ausgelistet erscheinen und ihn daneben neu entstehen - der Verlauf
    zerfaellt, ohne dass ein Fehler sichtbar wird.

    Die Namensmengen koennen sich nicht ueberschneiden, und zwar an der
    Form, nicht am Zufall: eine `listung_id` hat ZWEI Bestandteile
    (`o2--apple-iphone-14-128gb-schwarz`), diese hier VIER. Ein Anbieter,
    der wirklich "Buendel" hiesse, ergaebe `buendel--<sku>` - zwei Teile,
    also weiterhin kein Treffer.

    Fehlt ein Teil, sagt die ID das offen ("ohne-geraet", "ohne-tarif"),
    statt ihn wegzulassen - dieselbe Regel wie in `sku_id`.
    """
    return _TRENNER.join(("buendel", normalisiere(anbieter) or "ohne-anbieter",
                          sku_id or "ohne-geraet",
                          normalisiere(tarif_name) or "ohne-tarif"))


def sim_only_id(anbieter: str, tarif_name: str) -> str:
    """`simonly--<anbieter>--<tarif>` - drei Bestandteile, siehe oben."""
    return _TRENNER.join(("simonly", normalisiere(anbieter) or "ohne-anbieter",
                          normalisiere(tarif_name) or "ohne-tarif"))


# --------------------------------------------------------------------------
# Die Posten
# --------------------------------------------------------------------------

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
                raise ValueError(f"negativer betrag in {feld}: {wert} - ein "
                                 f"Rabatt wird als positiver Nachlass "
                                 f"geschrieben")
            setattr(self, feld, round(wert, 2))
        self.von_monat = int(self.von_monat)
        if self.von_monat < 1:
            raise ValueError(f"von_monat ist 1-basiert: {self.von_monat}")
        if self.bis_monat is not None:
            self.bis_monat = int(self.bis_monat)
            if self.bis_monat < self.von_monat:
                raise ValueError(f"bis_monat vor von_monat: {self.bis_monat} "
                                 f"< {self.von_monat}")

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


@dataclass
class Buendel:
    """EIN Angebot aus Geraet und Tarif bei EINEM Anbieter.

    Der Schluessel ist (SKU x Anbieter x Tarif) - dasselbe Geraet beim
    selben Anbieter zu zwei Tarifen sind zwei Buendel, weil es zwei Preise
    sind. Die Feldbedeutungen stehen im Modulkopf.

    Es gibt hier bewusst KEIN `preis_ohne_vertrag`. Der Gesamtbetrag der
    Geraeteraten ist eine Ratenzahlung und keine Kassenzahl; ihn in dasselbe
    Feld zu schreiben wie einen Barpreis war der Befund, mit dem dieses
    Vorhaben angefangen hat (o2, 03.09.2026: 721,00 EUR standen in derselben
    Spalte wie freenets 949,00 EUR Barpreis).
    """

    sku_id: str = ""
    anbieter: str = ""
    tarif_name: str = ""
    # Der Fremdschluessel auf `data/state/tarife.jsonl` (`tarif_bezug.py`).
    # Er tritt NEBEN den Namen und nicht an seine Stelle: der Name ist, was
    # auf der Produktseite stand, die ID ist, was im Produktinformations-
    # blatt steht. Laufen die zwei auseinander, ist genau das die Auskunft.
    # `tarif_id_guete` sagt, wie die Verbindung zustande kam - "hoch" ueber
    # den Namen, "mittel" ueber den Monatsbetrag (Vodafones Nutzlast nennt
    # keinen Tarifnamen, § 6.2 Nr. 7 der Strategie).
    tarif_id: str = ""
    tarif_id_guete: str = ""
    tarif_monatlich: Optional[float] = None
    # Die Mindestlaufzeit des TARIFS, in Monaten. Sie steht nicht in der
    # Geraetenutzlast, sondern im Tarifbestand (`data/state/tarife.jsonl`,
    # ueber `tarif_id`) - deshalb setzt sie der Aufrufer und nicht der
    # Speicher. o2 bindet den Tarif 24 Monate und finanziert das Geraet
    # ueber 36; wer die zwei gleichsetzt, addiert zwoelf Tarifmonate, die
    # niemand schuldet (A5.5).
    tarif_bindung_monate: Optional[int] = None
    # EIN Monatsbetrag fuer Tarif UND Geraet zusammen - so verkauft 1&1
    # (§ 13.2 der Strategie: `"price": "44.99"` ist der Buendelmonatspreis,
    # einen Barpreis gibt es dort nicht). Er tritt an die Stelle von
    # `tarif_monatlich` PLUS `geraet_monatsrate`; ihn in seine zwei Haelften
    # zu zerlegen waere eine Rechnung dieses Projekts und keine Angabe des
    # Anbieters.
    buendel_monatlich: Optional[float] = None
    geraet_zuzahlung: Optional[float] = None
    geraet_monatsrate: Optional[float] = None
    laufzeit_monate: int = STANDARD_LAUFZEIT
    anschlusspreis: Optional[float] = None
    rabatte: list[Rabatt] = field(default_factory=list)
    quelle_url: str = ""
    abgerufen_am: str = ""
    # DER GERAETEZUSTAND, wie ihn die Listung derselben SKU traegt
    # (`geraete_model.ZUSTAENDE`: neu | refurbished | b-ware | unbekannt).
    # Er ist eine PREISDIMENSION und kein Etikett (CLAUDE.md § 6) - ein
    # erneuertes iPhone 15 fuer 17,00 EUR im Monat ist ein anderes Produkt
    # als das neue fuer 20,00 EUR, kein guenstigeres Angebot. Bis zum
    # 04.09.2026 kannte das Buendel den Zustand nicht, und die Kartenauswahl
    # nahm je (Anbieter, Tarif) die guenstigste Karte: zehn o2-Karten
    # fuehrten erneuerte Geraete unbeschriftet gegen Neugeraete von 1&1 und
    # Vodafone (QA-Befund B1). Leer heisst "nicht belegt" - und unbelegt
    # gilt als `unbekannt`, nie als neu (`geraete_tco_karten.zustand_des_
    # buendels`).
    zustand: str = ""

    def __post_init__(self):
        if not (self.anbieter or "").strip():
            raise ValueError("ein Buendel ohne Anbieter ist keins")
        if not (self.tarif_name or "").strip():
            # Teil C4, hier auf der Buendelebene: eine Zuzahlung ohne ihren
            # Tarif ist eine Zahl ohne Bedeutung.
            raise ValueError("ein Buendel ohne Tarif ist keins")
        self.anbieter = self.anbieter.strip()
        self.tarif_name = self.tarif_name.strip()
        self.sku_id = (self.sku_id or "").strip()
        self.zustand = (self.zustand or "").strip().lower()
        for feld in ("tarif_monatlich", "buendel_monatlich",
                     "geraet_zuzahlung", "geraet_monatsrate",
                     "anschlusspreis"):
            wert = getattr(self, feld)
            if wert is None:
                continue
            wert = float(wert)
            if wert < 0:
                raise ValueError(f"negativer preis in {feld}: {wert}")
            setattr(self, feld, round(wert, 2))
        if self.buendel_monatlich is not None and (
                self.tarif_monatlich is not None
                or self.geraet_monatsrate is not None):
            # Sonst stuende derselbe Monat zweimal in der Summe: einmal als
            # Buendelbetrag und einmal als seine Bestandteile. Wer beides
            # kennt, traegt die Bestandteile ein - sie sagen mehr.
            raise ValueError("ein Buendelmonatspreis steht ANSTELLE von "
                             "Tarifpreis und Geraeterate, nicht daneben")
        if self.tarif_bindung_monate is not None:
            self.tarif_bindung_monate = int(self.tarif_bindung_monate)
            if self.tarif_bindung_monate < 0:
                raise ValueError("negative Tarifbindung: "
                                 f"{self.tarif_bindung_monate}")
        self.laufzeit_monate = int(self.laufzeit_monate)
        if self.laufzeit_monate <= 0:
            raise ValueError(f"laufzeit_monate muss positiv sein: "
                             f"{self.laufzeit_monate}")
        if not self.sku_id and (self.geraet_zuzahlung is not None
                                or self.geraet_monatsrate is not None
                                or self.buendel_monatlich is not None):
            # Sonst haette eine SIM-only-Referenz einen Geraetepreis, und die
            # Differenz aus beiden - der effektive Geraetepreis - zoege ihn
            # von sich selbst ab.
            raise ValueError("Geraetepreis ohne SKU: ein Buendel ohne Geraet "
                             "kann keine Zuzahlung und keine Rate tragen")

    @property
    def id(self) -> str:
        return buendel_id(self.sku_id, self.anbieter, self.tarif_name)

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
        if self.geraet_zuzahlung is None or self.geraet_monatsrate is None:
            return None
        return Ratenzahlung(anzahlung=self.geraet_zuzahlung,
                            monatsrate=self.geraet_monatsrate,
                            laufzeit_monate=self.laufzeit_monate)


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
        return Buendel(sku_id="", anbieter=self.anbieter,
                       tarif_name=self.tarif_name,
                       tarif_id=self.tarif_id,
                       tarif_id_guete=self.tarif_id_guete,
                       tarif_monatlich=self.tarif_sim_only_monatlich,
                       anschlusspreis=self.anschlusspreis,
                       rabatte=list(self.rabatte), quelle_url=self.quelle_url,
                       abgerufen_am=self.abgerufen_am)


# --------------------------------------------------------------------------
# Die Rechnung
# --------------------------------------------------------------------------

@dataclass
class Tco:
    """Das Ergebnis einer TCO-Rechnung - mit allem, was ihr fehlt.

    Felder:
      gesamt        die Leitzahl ueber den Horizont, None ohne jeden Posten
      horizont      ueber wie viele Monate gerechnet wurde (24, E2)
      monatlich     Ø/Monat - die Zweitzahl der Seite
      bestandteile  Posten -> Betrag, in der Reihenfolge der Rechnung
      luecken       benannte fehlende Komponenten (§ 6.4)
      restbetrag    offene Geraeteraten JENSEITS des Horizonts
      rabatte_offen was an benannten Nachlaessen NICHT abgezogen wurde
    """

    gesamt: Optional[float] = None
    horizont: int = TCO_HORIZONT
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
        """
        return self.gesamt is not None and POSTEN_TARIF not in self.luecken


def tco_24(buendel: Buendel) -> Tco:
    """Die Leitzahl eines Buendels: Gesamtkosten ueber 24 Monate.

    Eine REINE Funktion - gleiche Posten, gleiches Ergebnis, kein Zustand,
    nichts gespeichert. Der Horizont steht fest (E2); die Ratenlaufzeit des
    Geraets darf davon abweichen, und was jenseits liegt, steht in
    `restbetrag` statt in der Kennzahl.
    """
    ergebnis = Tco(horizont=TCO_HORIZONT)

    if buendel.tarif_monatlich is not None:
        ergebnis.bestandteile[f"Tarif über {TCO_HORIZONT} Monate"] = \
            round(buendel.tarif_monatlich * TCO_HORIZONT, 2)
    else:
        ergebnis.luecken.append(POSTEN_TARIF)

    if not buendel.ohne_geraet:
        # 0.0 ist ein gemessener Betrag ("keine Zuzahlung"), None ist eine
        # Luecke ("nicht gemessen"). Der Unterschied ist der ganze Punkt.
        if buendel.geraet_zuzahlung is not None:
            ergebnis.bestandteile[POSTEN_ZUZAHLUNG] = buendel.geraet_zuzahlung
        else:
            ergebnis.luecken.append(POSTEN_ZUZAHLUNG)

        if buendel.geraet_monatsrate is not None:
            im_horizont = min(buendel.laufzeit_monate, TCO_HORIZONT)
            ergebnis.bestandteile[f"Geräteraten ({im_horizont} von "
                                  f"{buendel.laufzeit_monate})"] = \
                round(buendel.geraet_monatsrate * im_horizont, 2)
            offen = max(0, buendel.laufzeit_monate - TCO_HORIZONT)
            ergebnis.restbetrag = round(buendel.geraet_monatsrate * offen, 2)
        else:
            ergebnis.luecken.append(POSTEN_RATE)

    if buendel.anschlusspreis is not None:
        ergebnis.bestandteile[POSTEN_ANSCHLUSS] = buendel.anschlusspreis
    else:
        # Wortgleich die Regel aus `effektivpreis.py`: unbekannt ist nicht
        # kostenlos.
        ergebnis.luecken.append(POSTEN_ANSCHLUSS)

    if buendel.rabatte:
        # Berechnet, ausgewiesen, NICHT abgezogen - siehe `Rabatt`.
        ergebnis.rabatte_offen = round(
            sum(r.wert(TCO_HORIZONT) for r in buendel.rabatte), 2)
    else:
        # Kein erfasster Rabatt heisst nicht "es gibt keinen". Boni und
        # Gutschriften stehen bei allen Anbietern im Fliesstext (§ 6.2
        # Nr. 9) und sind bisher bei keinem strukturiert abrufbar.
        ergebnis.luecken.append(POSTEN_RABATTE)

    if ergebnis.bestandteile:
        ergebnis.gesamt = round(sum(ergebnis.bestandteile.values()), 2)
        ergebnis.monatlich = round(ergebnis.gesamt / TCO_HORIZONT, 2)
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
        den ganzen Tarif und ist um Hunderte Euro zu hoch."""
        return self.betrag is not None and not [
            l for l in self.luecken
            if l not in _LUECKEN_OHNE_EINFLUSS_AUF_DIE_DIFFERENZ]


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

    Die Luecken beider Seiten werden zusammengefuehrt und WEITERGEREICHT:
    fehlt auf einer Seite der Anschlusspreis, ist die Differenz nur so gut
    wie die schlechtere der zwei Rechnungen.
    """
    if normalisiere(buendel.anbieter) != normalisiere(referenz.anbieter):
        raise ValueError(f"Buendel und SIM-only-Referenz gehoeren zu "
                         f"verschiedenen Anbietern: {buendel.anbieter!r} / "
                         f"{referenz.anbieter!r}")
    ids = ((buendel.tarif_id or "").strip(), (referenz.tarif_id or "").strip())
    if all(ids):
        if ids[0] != ids[1]:
            raise ValueError(f"Buendel und SIM-only-Referenz gehoeren zu "
                             f"verschiedenen Tarifen: {ids[0]!r} / {ids[1]!r}")
    elif normalisiere(buendel.tarif_name) != normalisiere(referenz.tarif_name):
        raise ValueError(f"Buendel und SIM-only-Referenz gehoeren zu "
                         f"verschiedenen Tarifen: {buendel.tarif_name!r} / "
                         f"{referenz.tarif_name!r}")
    if buendel.ohne_geraet:
        raise ValueError("ein Buendel ohne Geraet hat keinen Geraeteanteil")

    mit = tco_24(buendel)
    ohne = tco_24(referenz.als_buendel())
    luecken = list(mit.luecken)
    luecken += [l for l in ohne.luecken if l not in luecken]

    ergebnis = Geraeteanteil(horizont=TCO_HORIZONT, tco_buendel=mit.gesamt,
                             tco_sim_only=ohne.gesamt, luecken=luecken)
    if mit.gesamt is not None and ohne.gesamt is not None:
        ergebnis.betrag = round(mit.gesamt - ohne.gesamt, 2)
    return ergebnis


# --------------------------------------------------------------------------
# Phase R: die Kennzahl ueber die BINDUNG, nicht ueber einen festen Horizont
# --------------------------------------------------------------------------
#
# Warum es diese zweite Rechnung gibt
# -----------------------------------
# `tco_24` kappt bei 24 Monaten. Das war richtig, solange die Frage lautete
# "was kostet ein Buendel in der ueblichen Tarifmindestlaufzeit". Am
# 04.09.2026 ist der Bestand gemessen worden, und er sagt etwas anderes:
# **jedes** erhobene Buendel ist eine 36-Monats-Geraetefinanzierung (o2
# 62/62, 1&1 35/35), und o2 trennt dabei sogar die Tarifbindung (24 Monate)
# von der Ratenlaufzeit (36). Eine reine 24-Monats-Rangliste waere damit
# entweder leer oder - schlimmer - sie vergliche Ungleiches.
#
# Die Anforderung A5 (ANFORDERUNGEN_TCO_FIRST.md, 04.09.2026) zieht daraus
# fuenf Regeln, und dieses Modul setzt sie um:
#
#   A5.1  Die Leitzahl heisst `TCO-<Bindung>` und traegt ihre Laufzeit IMMER
#         im Namen. Nie unbeschriftet, nie zwei Laufzeiten in einer Rangfolge.
#   A5.2  Antonios Leitfrage wird woertlich beantwortet, auch bei 36 Monaten:
#         `gezahlt_nach_24` und `offen_nach_24` stehen als Pflichtzeile an
#         jeder Karte. Eine auf 24 gekappte Zahl OHNE diesen Ausweis waere
#         die CHECK24-Methodik, die § 5.4 der Strategie verwirft.
#   A5.3  Quervergleichsmass ueber Laufzeiten hinweg ist `schnitt_monat`
#         (Gesamt / Bindung) - und nur dieses.
#   A5.4  Zwei Laufzeitgruppen, zwei Nulllinien (das rechnet die Grafik).
#   A5.5  Bei getrennten Laufzeiten fuehrt die LAENGERE die Karte, und die
#         Aufspaltung steht im Rechenweg.
#
# Der eine Unterschied zu `tco_24`, der bewusst gemacht ist
# ---------------------------------------------------------
# `tco_24` rechnet Rabatte NIE ein (Regel 3 im Modulkopf). Diese Rechnung
# zieht **belegte** Boni ab - so steht es im Terminologie-Katalog D des
# Lastenhefts ("TCO-24 = ... − belegte Boni") und so verlangt es die
# Balkengrafik G1, die den Bonus als eigenes, negatives Segment zeigt. Der
# Widerspruch zu Regel 3 ist keiner: dort ging es um CHECK24s
# "bestenfalls realisierbare Verguenstigungen", also um einen unterstellten
# Bestfall. Hier wird nur abgezogen, was als `Rabatt` mit Namen, Frist und
# Beleg im Datensatz steht, und jeder Abzug erscheint einzeln mit seiner
# Bedingung - "niemals STILL einrechnen" (Katalog D) ist damit erfuellt.
# Im Bestand vom 04.09.2026 traegt kein einziges Buendel einen Rabatt; der
# Unterschied ist heute also null und morgen belegt.

# Der Horizont von Antonios Leitfrage: "was zahlt der Kunde ueber 24 Monate
# gesamt". Er ist NICHT die Bindung - er ist die Frage, die an jeder Karte
# beantwortet wird, egal wie lang die Bindung laeuft.
LEITFRAGE_MONATE = 24

# Die Kategorien der Bestandteile. Die Balkengrafik stapelt nach ihnen, die
# Tabelle liest dieselbe Liste - eine zweite Zuordnung in der Vorlage waere
# eine zweite Rechnung (CLAUDE.md § 6).
KAT_EINMALIG = "einmalig"
KAT_TARIF = "tarif"
KAT_RATEN = "raten"
KAT_BUENDEL = "buendel"
KAT_BONUS = "bonus"

POSTEN_BUENDEL = "Bündelpreis (Tarif und Gerät zusammen)"
POSTEN_TARIFBINDUNG = "Tarifbindung"
# EIN FLEXTARIF IST KEINE LUECKE, SONDERN EINE AUSSAGE. CLAUDE.md § 6:
# "«Keine Mindestlaufzeit» ist 0, nicht None. Eine Aussage, kein fehlender
# Wert." Ueber eine Bindung, die es nicht gibt, ist auch kein Tarifbetrag
# geschuldet - eine TCO ueber die Laufzeit ist fuer diesen Tarif nicht
# definiert, und das ist etwas anderes als "nicht gemessen". Im
# Tarifbestand vom 04.09.2026 tragen 8 von 44 Tarifen die 0 (congstar 5,
# o2 3).
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
        return (self.gesamt is not None and self.bindung is not None
                and POSTEN_TARIF not in self.luecken
                # Ein Grundpreis ohne gemessene Bindung steht in KEINEM
                # Bestandteil - die Summe waere dann der Geraetebetrag
                # allein und saehe wie ein sehr guenstiges Buendel aus.
                # Dasselbe gilt fuer einen Flextarif, nur aus dem
                # umgekehrten Grund: dort ist der Betrag nicht geschuldet.
                and POSTEN_TARIFBINDUNG not in self.luecken
                and POSTEN_TARIF_FLEX not in self.luecken)

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
    e.raten_laufzeit = (buendel.laufzeit_monate
                        if (zusammen or buendel.geraet_monatsrate is not None)
                        else None)
    e.tarif_bindung = buendel.tarif_bindung_monate

    if zusammen:
        # EIN Betrag ueber die Laufzeit, die der Anbieter selbst nennt.
        e.bindung = buendel.laufzeit_monate
    else:
        # Der Tarif laeuft seine Mindestlaufzeit, die Rate ihre eigene.
        # Fehlt die Tarifbindung, ist die Karte nicht rechenbar: sie mit der
        # Ratenlaufzeit gleichzusetzen addierte bei o2 zwoelf Tarifmonate,
        # die niemand schuldet (12 x 19,99 EUR = 239,88 EUR zu viel).
        # `if x` und nicht `is not None`: eine 0 ist keine Laenge. Ein
        # Flextarif bindet nicht, die Geraeteraten schon.
        laengen = [x for x in (e.tarif_bindung, e.raten_laufzeit) if x]
        e.bindung = max(laengen) if laengen else None

    # ---- Tarif ----------------------------------------------------------
    if zusammen:
        e.bestandteile.append({
            "name": f"{POSTEN_BUENDEL} · {buendel.laufzeit_monate} × "
                    f"{buendel.buendel_monatlich:.2f} €".replace(".", ","),
            "betrag": round(buendel.buendel_monatlich
                            * buendel.laufzeit_monate, 2),
            "kategorie": KAT_BUENDEL})
    elif buendel.tarif_monatlich is None:
        e.luecken.append(POSTEN_TARIF)
    elif e.tarif_bindung:
        e.bestandteile.append({
            "name": f"Tarif · {e.tarif_bindung} × "
                    f"{buendel.tarif_monatlich:.2f} €".replace(".", ","),
            "betrag": round(buendel.tarif_monatlich * e.tarif_bindung, 2),
            "kategorie": KAT_TARIF})
    elif e.tarif_bindung == 0:
        # Monatlich kuendbar: der Kunde schuldet den Tarif nicht ueber die
        # Laufzeit, sondern Monat fuer Monat. Ihn ueber 36 Monate zu
        # summieren waere eine Bindung, die der Vertrag nicht kennt.
        e.luecken.append(POSTEN_TARIF_FLEX)
    else:
        # Der Grundpreis steht, aber niemand hat gemessen, wie lange er
        # geschuldet ist. Beides ist eine Luecke, und sie hat einen eigenen
        # Namen - sonst suchte der naechste Leser den Tarifpreis.
        e.luecken.append(POSTEN_TARIFBINDUNG)

    # ---- Geraet ---------------------------------------------------------
    if not buendel.ohne_geraet and not zusammen:
        if buendel.geraet_zuzahlung is not None:
            e.bestandteile.append({"name": POSTEN_ZUZAHLUNG,
                                   "betrag": buendel.geraet_zuzahlung,
                                   "kategorie": KAT_EINMALIG})
        else:
            e.luecken.append(POSTEN_ZUZAHLUNG)
        if buendel.geraet_monatsrate is not None:
            e.bestandteile.append({
                "name": f"Geräteraten · {buendel.laufzeit_monate} × "
                        f"{buendel.geraet_monatsrate:.2f} €".replace(".", ","),
                "betrag": round(buendel.geraet_monatsrate
                                * buendel.laufzeit_monate, 2),
                "kategorie": KAT_RATEN})
        else:
            e.luecken.append(POSTEN_RATE)

    # ---- Anschluss ------------------------------------------------------
    if buendel.anschlusspreis is not None:
        e.bestandteile.append({"name": POSTEN_ANSCHLUSS,
                               "betrag": buendel.anschlusspreis,
                               "kategorie": KAT_EINMALIG})
    else:
        e.luecken.append(POSTEN_ANSCHLUSS)

    # ---- Boni -----------------------------------------------------------
    # Abgezogen wird nur, was benannt und befristet im Datensatz steht, und
    # jeder Abzug erscheint einzeln - siehe der Absatz im Kopf dieses
    # Abschnitts.
    if buendel.rabatte and e.bindung:
        for r in buendel.rabatte:
            wert = r.wert(e.bindung)
            if not wert:
                continue
            e.boni.append({"name": r.name, "betrag": wert,
                           "beleg_url": r.beleg_url})
            e.bestandteile.append({"name": f"Bonus · {r.name}",
                                   "betrag": -wert, "kategorie": KAT_BONUS})
        e.boni_abzug = round(sum(b["betrag"] for b in e.boni), 2)
    elif not buendel.rabatte:
        # Kein erfasster Bonus heisst nicht "es gibt keinen" - dieselbe
        # Regel wie in `tco_24`.
        e.luecken.append(POSTEN_RABATTE)

    if not e.bestandteile:
        return e

    e.gesamt = round(sum(p["betrag"] for p in e.bestandteile), 2)
    if e.bindung:
        e.schnitt_monat = round(e.gesamt / e.bindung, 2)

    # ---- Antonios Leitfrage, woertlich (A5.2) ---------------------------
    # Gezahlt hat der Kunde nach 24 Monaten: alle Einmalposten, den Tarif
    # fuer hoechstens 24 seiner Monate und die Rate fuer hoechstens 24 ihrer
    # Monate. Boni innerhalb der ersten 24 Monate mindern auch diese Zahl -
    # sie werden mit demselben Horizont gerechnet wie der Rest.
    gezahlt = 0.0
    for p in e.bestandteile:
        if p["kategorie"] == KAT_EINMALIG:
            gezahlt += p["betrag"]
    if zusammen:
        gezahlt += round(buendel.buendel_monatlich
                         * min(LEITFRAGE_MONATE, buendel.laufzeit_monate), 2)
    else:
        if buendel.tarif_monatlich is not None and e.tarif_bindung:
            gezahlt += round(buendel.tarif_monatlich
                             * min(LEITFRAGE_MONATE, e.tarif_bindung), 2)
        if buendel.geraet_monatsrate is not None:
            gezahlt += round(buendel.geraet_monatsrate
                             * min(LEITFRAGE_MONATE,
                                   buendel.laufzeit_monate), 2)
    for r in buendel.rabatte:
        # Ueber den kuerzeren der beiden Zeitraeume: laeuft der Vertrag nur
        # zwoelf Monate, gibt es keinen Bonus fuer Monat 13 bis 24. Mit
        # festen 24 stand bei einer 12-Monats-Bindung "noch offen: 120,00 €"
        # da, wo nichts mehr offen ist - die Differenz war allein
        # `wert(24) - wert(12)`.
        gezahlt -= r.wert(min(LEITFRAGE_MONATE, e.bindung or LEITFRAGE_MONATE))
    e.gezahlt_nach_24 = round(gezahlt, 2)
    e.offen_nach_24 = round(e.gesamt - e.gezahlt_nach_24, 2)
    return e


def effektiv_ohne_geraet(kennzahl: TcoBindung,
                         barpreis: Optional[float]) -> Optional[float]:
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
