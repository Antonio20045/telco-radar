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
    geraet_zuzahlung: Optional[float] = None
    geraet_monatsrate: Optional[float] = None
    laufzeit_monate: int = STANDARD_LAUFZEIT
    anschlusspreis: Optional[float] = None
    rabatte: list[Rabatt] = field(default_factory=list)
    quelle_url: str = ""
    abgerufen_am: str = ""

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
        for feld in ("tarif_monatlich", "geraet_zuzahlung",
                     "geraet_monatsrate", "anschlusspreis"):
            wert = getattr(self, feld)
            if wert is None:
                continue
            wert = float(wert)
            if wert < 0:
                raise ValueError(f"negativer preis in {feld}: {wert}")
            setattr(self, feld, round(wert, 2))
        self.laufzeit_monate = int(self.laufzeit_monate)
        if self.laufzeit_monate <= 0:
            raise ValueError(f"laufzeit_monate muss positiv sein: "
                             f"{self.laufzeit_monate}")
        if not self.sku_id and (self.geraet_zuzahlung is not None
                                or self.geraet_monatsrate is not None):
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
