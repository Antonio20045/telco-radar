"""Das Datenmodell eines Tarifs - und die Regel, dass jeder Wert einen Beleg hat.

Warum es dieses Modell gibt
---------------------------
§ 54 TKG und die EU-Verordnung 2019/2243 verpflichten jeden Anbieter zu einer
standardisierten Vertragszusammenfassung, die TK-Transparenzverordnung
zusaetzlich zum Produktinformationsblatt. Diese Dokumente sind oeffentlich,
ohne Login, ohne Bot-Schutz, im Aufbau standardisiert - und rechtlich
wahrheitsbewehrt. Kein Marketingtext dieses Marktes hat diese Eigenschaft.

Damit wird aus dem Nachrichtenprodukt ein Analysewerkzeug: nicht "Anbieter X
hat einen neuen Tarif angekuendigt", sondern "Anbieter X verlangt 59,95 € bei
80 GB und drosselt danach auf 64 KBit/s, und vor vier Wochen waren es 100 GB".

Die eine Regel, die das Modell traegt
-------------------------------------
**Kein Feldwert ohne Fundstelle.** Jeder gesetzte Wert traegt die Textzeile,
aus der er stammt, und `pruefe_belege()` erzwingt, dass diese Zeile im
Rohtext wirklich vorkommt. Ohne das waere dieses Modul das Gegenteil dessen,
wofuer das Projekt gebaut ist: eine Zahl ohne Nachweis, huebsch formatiert.

Der Vorlaeufer dieser Regel steht in `analyze/faithfulness.py` und heisst
dort "fail closed" - was nicht geprueft werden konnte, erscheint nicht.

Confidence nach METHODE, nicht nach Gefuehl
-------------------------------------------
`hoch`    Ein regulaerer Ausdruck hat den standardisierten Feldbezeichner
          getroffen. Das Dokument ist normiert; wer "Mindestvertragslaufzeit
          24 Monate" schreibt, meint 24 Monate.
`mittel`  Ein Modell hat den Wert aus dem Rest gelesen.
`niedrig` Nichts gefunden - das Feld bleibt None und faellt aus jeder
          Rechnung heraus.

Ein Dokument, dessen Pflichtfelder alle `niedrig` sind, ist kein Tarif,
sondern ein unbekanntes Layout. Es geht in Quarantaene statt mit falschen
Zahlen in die Datenbank (`ist_quarantaene`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Optional

# Die Felder, ohne die ein Dokument kein auswertbarer Tarif ist. Ein PIB ohne
# Preis UND ohne Laufzeit ist ein Deckblatt, eine AGB-Seite oder ein Layout,
# das dieser Extraktor nicht kennt.
PFLICHTFELDER = ("grundgebuehr", "laufzeit_monate")

HOCH, MITTEL, NIEDRIG = "hoch", "mittel", "niedrig"

# WOHER DER PREIS KOMMT - und warum das ein eigenes Feld ist.
#
# Bis zum 04.09.2026 stammte jeder Satz in `tarife.jsonl` aus einem
# Pflichtdokument nach § 1 TK-TransparenzV. Das ist die belastbarste Quelle
# dieses Marktes, aber nicht die aktuellste: das Blatt traegt den
# Vermarktungsstand, die Shop-Seite den heutigen Aktionspreis. Beide sind
# richtig, und sie duerfen auseinanderlaufen.
#
# Sie in dieselbe Spalte zu schreiben, ohne den Unterschied mitzufuehren,
# waere derselbe Fehler wie o2s Ratengesamtbetrag neben freenets Barpreis
# (`geraete_model.Ratenzahlung`): gleiche Optik, andere Groesse. Deshalb
# traegt jeder Satz, woher seine Zahl kommt.
#
# `dokument`   Produktinformationsblatt / Vertragszusammenfassung. Der
#              Vorgabewert - jeder Bestandssatz aus der Zeit davor ist das.
# `live_shop`  Strukturierte Daten einer Shop-Seite (schema.org). Der Preis,
#              den der Anbieter heute bewirbt, ohne gesetzliche
#              Wahrheitsbewehrung und ohne die Pflichtfelder des Blattes.
PREISTYP_DOKUMENT = "dokument"
PREISTYP_LIVE_SHOP = "live_shop"
PREISTYPEN = (PREISTYP_DOKUMENT, PREISTYP_LIVE_SHOP)


@dataclass
class Preisphase:
    """Ein Abschnitt der Laufzeit mit gleichbleibendem Monatspreis.

    "6 Monate 9,99 €, danach 29,99 €" sind zwei Phasen. Der Effektivpreis
    (A6) rechnet ueber sie - und genau deshalb sind sie ein eigenes Objekt
    und nicht zwei Felder. Ein Tarif mit drei Phasen kommt vor.
    """

    von_monat: int          # 1-basiert, einschliesslich
    bis_monat: Optional[int]  # einschliesslich; None = bis Vertragsende
    betrag: float

    def monate(self, laufzeit: int) -> int:
        ende = self.bis_monat if self.bis_monat is not None else laufzeit
        return max(0, min(ende, laufzeit) - self.von_monat + 1)


@dataclass
class Geraetepreis:
    """Eine Stufe der Geraetepreisstaffel ("mit Top-Smartphone: 44,95 €")."""

    kategorie: str
    betrag: float


@dataclass
class Tarif:
    """Ein Tarif, wie er aus einem PIB oder einer Vertragszusammenfassung faellt."""

    anbieter: str = ""
    name: str = ""
    art: str = ""                      # "mobilfunk" | "festnetz" | ""

    # --- Preis
    grundgebuehr: Optional[float] = None
    grundgebuehr_nach_rabatt: Optional[float] = None
    preisphasen: list[Preisphase] = field(default_factory=list)
    anschlusspreis: Optional[float] = None
    anschlusspreis_nach_erstattung: Optional[float] = None
    geraetepreisstaffel: list[Geraetepreis] = field(default_factory=list)

    # --- Leistung
    datenvolumen_gb: Optional[float] = None
    volumen_automatik: str = ""
    speed_down_max: Optional[float] = None    # MBit/s
    speed_up_max: Optional[float] = None
    drossel_down: Optional[float] = None      # KBit/s
    drossel_up: Optional[float] = None
    allnet_flat: Optional[bool] = None
    sms_flat: Optional[bool] = None

    # --- Vertrag
    laufzeit_monate: Optional[int] = None
    kuendigungsfrist_monate: Optional[int] = None

    # --- Herkunft
    dokument_url: str = ""
    dokument_hash: str = ""
    versionsstand: str = ""
    abgerufen_am: str = ""
    rohtext: str = ""
    # Aus welcher Art Quelle der Preis stammt (siehe PREISTYPEN oben). Der
    # Vorgabewert ist `dokument`, damit jeder Bestandssatz aus der Zeit vor
    # dem 04.09.2026 beim Wiedereinlesen genau das bleibt, was er war.
    preistyp: str = PREISTYP_DOKUMENT

    # --- Nachweis
    confidence: dict = field(default_factory=dict)   # feld -> hoch/mittel/niedrig
    fundstellen: dict = field(default_factory=dict)  # feld -> Textzeile

    # ------------------------------------------------------------------ #

    def setze(self, feld: str, wert, beleg: str, guete: str = HOCH) -> None:
        """Einen Wert MIT Beleg setzen. Der einzige vorgesehene Weg.

        Ohne Beleg passiert nichts - lieber ein fehlendes Feld als eine Zahl,
        die niemand nachschlagen kann.
        """
        if wert is None or not str(beleg).strip():
            return
        setattr(self, feld, wert)
        self.confidence[feld] = guete
        self.fundstellen[feld] = " ".join(str(beleg).split())[:300]

    def fehlende_belege(self) -> list[str]:
        """Felder mit Wert, deren Fundstelle nicht im Rohtext steht.

        Der Rohtext ist normalisiert (Mehrfach-Leerzeichen zusammengezogen),
        die Fundstelle ebenso - sonst scheitert der Vergleich an der
        Spaltenausrichtung von `pdftotext -layout`.
        """
        roh = " ".join(self.rohtext.split())
        offen = []
        for feld, stelle in self.fundstellen.items():
            if getattr(self, feld, None) is None:
                continue
            if stelle and stelle not in roh:
                offen.append(feld)
        return sorted(offen)

    def pruefe_belege(self) -> None:
        """Wirft, wenn ein Wert ohne nachvollziehbare Fundstelle dasteht."""
        offen = self.fehlende_belege()
        if offen:
            raise ValueError(
                "Feldwerte ohne Fundstelle im Rohtext: " + ", ".join(offen))

    @property
    def ist_quarantaene(self) -> bool:
        """Unbekanntes Layout: kein einziges Pflichtfeld gefunden.

        Nicht "irgendein Feld fehlt" - ein Flex-Tarif hat zu Recht keine
        Mindestlaufzeit. Erst wenn NICHTS davon gefunden wurde, ist das
        Dokument kein Tarif, sondern ein Layout, das dieser Extraktor nicht
        kennt.
        """
        return not any(getattr(self, f, None) is not None for f in PFLICHTFELDER)

    @property
    def preis_je_gb(self) -> Optional[float]:
        if not self.grundgebuehr or not self.datenvolumen_gb:
            return None
        return round(self.grundgebuehr / self.datenvolumen_gb, 4)

    def als_dict(self) -> dict:
        d = asdict(self)
        # Der Rohtext ist der Beleg, aber er gehoert nicht in jede Zeile der
        # Zeitreihe - er verdoppelt die Datei und aendert sich mit jedem
        # Zeilenumbruch des Anbieters.
        d.pop("rohtext", None)
        return d


def normalisiere(text: str) -> str:
    """Was `pdftotext -layout` liefert, in eine vergleichbare Form.

    Drei Dinge, und jedes hat einen konkreten Fall dahinter:

    * **Zero-Width-Space (U+200B).** o2 setzt ihn hinter
      "Keine Mindestlaufzeit" - ein Regex auf `Mindestlaufzeit\\b` trifft,
      ein Vergleich auf die Zeichenkette nicht. Er ist unsichtbar, also
      unauffindbar, wenn man ihn nicht kennt.
    * **Weiche Trennstriche und geschuetzte Leerzeichen.** Kommen in beiden
      Anbieterlayouts vor.
    * **Spaltenabstaende.** `-layout` polstert mit bis zu vierzig Leerzeichen;
      ohne Zusammenziehen braeuchte jeder Regex ein `\\s{1,40}`.
    """
    text = (text.replace("​", "")
                .replace("­", "")
                .replace(" ", " ")
                .replace("‑", "-"))
    zeilen = [" ".join(z.split()) for z in text.splitlines()]
    return "\n".join(z for z in zeilen if z)


def zahl(roh: str) -> Optional[float]:
    """Eine deutsche Dezimalzahl als float. "1.234,56" -> 1234.56."""
    if roh is None:
        return None
    s = str(roh).strip().replace(" ", "")
    if not s:
        return None
    s = re.sub(r"[^\d,.\-]", "", s)
    if not s:
        return None
    # Tausenderpunkt nur, wenn danach genau drei Ziffern stehen.
    s = re.sub(r"\.(?=\d{3}(?:\D|$))", "", s)
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None
