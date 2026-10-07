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

import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Optional

log = logging.getLogger(__name__)

PFLICHTFELDER = ("grundgebuehr", "laufzeit_monate")

HOCH, MITTEL, NIEDRIG = "hoch", "mittel", "niedrig"
NUR_MIT_GERAET = "nur_mit_geraet"
"""Güte eines Bündeltarifs ohne Tarifblatt im Bestand (`tco_buendel.ohne_tarifblatt`):
Tarif-ID aus dem Slug des Anbieters, kein SIM-only-Maßstab, keine Bindung aus dem
Blatt."""

PREISTYP_DOKUMENT = "dokument"
PREISTYP_LIVE_SHOP = "live_shop"
PREISTYPEN = (PREISTYP_DOKUMENT, PREISTYP_LIVE_SHOP)


def ist_zurueckgezogen(satz: dict) -> bool:
    """Traegt der Stand einen Rueckzug (`TarifSpeicher.ziehe_zurueck`)?

    Ein zurueckgezogener Tarif steht noch in der Zeitreihe, ist aber kein
    aktueller Tarif mehr - jeder Leser, der "was gibt es heute" fragt,
    laesst ihn aus. EINE Stelle fuer diese Frage, damit Tarifseite und
    Geraeteseite nicht zweierlei Bestand sehen.
    """
    return bool((satz or {}).get("zurueckgezogen_am"))


def zeitreihen_basis(tid: str) -> str:
    """Eine Tarif-ID ohne den `#live_shop`-Lesart-Zusatz.

    ZWEI LESARTEN SIND ZWEI ZEITREIHEN, ABER EIN TARIF (B2, 08.09.2026):
    der PIB-Eintrag `telekom:magentamobil-l` und die Shop-Kachel
    `telekom:magentamobil-l#live_shop` sind derselbe Vertrag - der Zusatz
    ist der PREISTYP der Fassung, die `collect.tarif_crawler.uebernimm_stand`
    als ZWEITE fuer denselben Namen sieht, angehaengt genau deshalb, damit
    sich zwei unterschiedliche Lesarten nicht gegenseitig als
    Tarifaenderung melden. Gestrichen wird NUR er: ein Hash-Zusatz (zwei
    gleichnamige, verschiedene Produkte wie o2-home-l-flex und
    -175-flex) bleibt stehen und trennt weiterhin zwei echte Tarife.

    EINE STELLE FUER ZWEI VERWENDER (B3, 21.09.2026): `tco_model.
    geraeteanteil()` vergleicht darueber Buendel und SIM-only-Referenz,
    `tarif_bezug.Tarifbestand` darueber, welcher der zwei Saetze zu
    welchem Vertrag gehoert, wenn er entscheidet, welche Lesart als
    AKTUELL gilt. Vorher stand dieselbe Kuerzung zweimal im Code (einmal
    hier, einmal privat in `tco_model.py`) - zwei Kopien einer
    ID-Umformung laufen sonst irgendwann auseinander.
    """
    zusatz = f"#{PREISTYP_LIVE_SHOP}"
    return tid[: -len(zusatz)] if tid.endswith(zusatz) else tid


GERAETEBLATT_ZUSATZ = re.compile(r"\s+mit\s+(?:Smartphone|Handy|Endger[aä]t)\s*$", re.I)
_GERAETEBLATT_ID = re.compile(r"-mit-(?:smartphone|handy|endgeraet)$")


def erster_betrag(satz: dict) -> Optional[float]:
    """Der Betrag, der bei Vertragsschluss gilt.

    `grundgebuehr` und die erste Preisphase sind bei jedem heute gelesenen
    Dokument dieselbe Zahl - der Extraktor setzt die Phase aus ihr, wo das
    Blatt keine Zeitachse hat. Wo es eine hat (Vodafone: "Monat 1-24" /
    "ab Monat 25"), ist die erste Phase die genauere Angabe, und sobald
    dort einmal eine Rabattphase steht, ist sie die einzige richtige.
    """
    phasen = satz.get("preisphasen") or []
    if phasen:
        erste = min(phasen, key=lambda p: p.get("von_monat", 1))
        if erste.get("betrag") is not None:
            return float(erste["betrag"])
    grund = satz.get("grundgebuehr")
    return None if grund is None else float(grund)


def ist_geraeteblatt_von(blatt: dict, tarif: dict) -> bool:
    """Ist `blatt` das Geraeteblatt des Tarifs `tarif`?

    Eng gefasst: derselbe Anbieter, woertlich derselbe Name plus
    `GERAETEBLATT_ZUSATZ`, UND derselbe Betrag bei Vertragsschluss
    (`erster_betrag`). "MagentaMobil S" und "MagentaMobil S Flex" kosten
    ebenfalls gleich viel und sind trotzdem zwei Tarife - eine Regel ueber
    Namenspraefixe haette sie verschmolzen.
    """
    name = (blatt.get("name") or "").strip()
    ohne = GERAETEBLATT_ZUSATZ.sub("", name)
    if ohne == name:
        return False
    if (blatt.get("anbieter") or "").strip().lower() != (
        tarif.get("anbieter") or ""
    ).strip().lower():
        return False
    if ohne.lower() != (tarif.get("name") or "").strip().lower():
        return False
    a, b = erster_betrag(blatt), erster_betrag(tarif)
    return a is not None and b is not None and abs(a - b) < 0.005


def vertrag_basis(tid: str) -> str:
    """Die ID des Vertrags: ohne Lesart-Zusatz (`zeitreihen_basis`) und
    ohne Geraeteblatt-Zusatz. `vodafone:vodafone-mobil-m-mit-smartphone`
    und `vodafone:vodafone-mobil-m` sind derselbe Vertrag."""
    return _GERAETEBLATT_ID.sub("", zeitreihen_basis(tid or ""))


@dataclass
class Preisphase:
    """Ein Abschnitt der Laufzeit mit gleichbleibendem Monatspreis.

    "6 Monate 9,99 €, danach 29,99 €" sind zwei Phasen. Der Effektivpreis
    (A6) rechnet ueber sie - und genau deshalb sind sie ein eigenes Objekt
    und nicht zwei Felder. Ein Tarif mit drei Phasen kommt vor.
    """

    von_monat: int
    bis_monat: Optional[int]
    betrag: float

    def monate(self, laufzeit: int) -> int:
        ende = self.bis_monat if self.bis_monat is not None else laufzeit
        return max(0, min(ende, laufzeit) - self.von_monat + 1)


BUENDELPHASEN = "tarif_phasen"


@dataclass
class Buendelphase(Preisphase):
    """Eine Preisphase, die der Anbieter fuer genau ein Buendel nennt.

    Die Phasen des Tarifblatts beschreiben den Tarif und kommen beim Lesen dazu
    (`report.geraete_tco_karten.tarif_anreichern`); diese misst der Adapter am
    Buendel (`collect/geraete/ratenlaufzeit.py`), und der Store haelt sie unter
    `BUENDELPHASEN`. `beleg` ist der Wortlaut oder der Antwortpfad, die Adresse
    `Buendel.quelle_url`. Ohne Beleg oder ohne Ende ist sie keine (ValueError).
    """

    beleg: str = ""

    def __post_init__(self):
        self.beleg = " ".join((self.beleg or "").split())
        if not self.beleg:
            raise ValueError("eine Buendelphase ohne Beleg ist nicht nachpruefbar")
        if self.bis_monat is None:
            raise ValueError("eine Buendelphase ohne Ende belegt keinen Monat")
        self.von_monat, self.bis_monat = int(self.von_monat), int(self.bis_monat)
        if not 1 <= self.von_monat <= self.bis_monat:
            raise ValueError(f"keine Monatsspanne: {self.von_monat}-{self.bis_monat}")
        self.betrag = round(float(self.betrag), 2)
        if self.betrag < 0:
            raise ValueError(f"negativer Tarifpreis: {self.betrag}")


def buendelphasen_aus(rohsaetze) -> list[Preisphase]:
    """Phasen-Rohsaetze (dicts aus Adapter oder Store) als `Buendelphase`n.

    Eine unlesbare Phase faellt mit Protokoll weg; das Buendel rechnet dann wie eines
    ohne Beleg. Dieselbe Funktion fuer Sammel- und Leseweg."""
    fertig: list[Preisphase] = []
    for roh in rohsaetze or []:
        try:
            fertig.append(roh if isinstance(roh, Buendelphase) else Buendelphase(**roh))
        except (TypeError, ValueError) as exc:
            log.warning("Buendelphase uebergangen: %s (%r)", exc, roh)
    return fertig


def buendelphasen(phasen) -> list[Preisphase]:
    """Nur die am Buendel gemessenen Phasen; die des Tarifblatts nie."""
    return [p for p in phasen if isinstance(p, Buendelphase)]


def vor_dem_blatt(buendel, blatt: list[Preisphase]) -> list[Preisphase]:
    """Die Preisphasen eines Buendels beim Anreichern: was der Anbieter fuer dieses
    Buendel selbst nennt, geht einem Blatt vor, das nur den Grundpreis nennt (eine
    Phase ab Monat 1 ohne Ende). Eine Phasentabelle des Blatts nennt einzelne Monate
    ausdruecklich und bleibt stehen."""
    nur_grundpreis = all(p.von_monat == 1 and p.bis_monat is None for p in blatt)
    eigene = buendelphasen(buendel.tarif_phasen) if nur_grundpreis else []
    return eigene or blatt


def schreibe_buendelphasen(eintrag: dict, satz) -> None:
    """Die gemessenen Phasen eines Satzes in seinen Store-Eintrag - oder keine.

    Sie gehoeren zur Messung wie die Preise: ohne sie faellt das Feld weg, damit keine
    Phase eines frueheren Laufs neben den Preisen von heute steht. Ein Satz ohne
    Phasen (SIM-only-Referenz) bekommt keine."""
    phasen = [asdict(p) for p in buendelphasen(getattr(satz, "tarif_phasen", []))]
    if phasen:
        eintrag[BUENDELPHASEN] = phasen
    else:
        eintrag.pop(BUENDELPHASEN, None)


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
    art: str = ""

    grundgebuehr: Optional[float] = None
    grundgebuehr_nach_rabatt: Optional[float] = None
    preisphasen: list[Preisphase] = field(default_factory=list)
    anschlusspreis: Optional[float] = None
    anschlusspreis_nach_erstattung: Optional[float] = None
    geraetepreisstaffel: list[Geraetepreis] = field(default_factory=list)

    datenvolumen_gb: Optional[float] = None
    volumen_automatik: str = ""
    speed_down_max: Optional[float] = None
    speed_up_max: Optional[float] = None
    drossel_down: Optional[float] = None
    drossel_up: Optional[float] = None
    allnet_flat: Optional[bool] = None
    sms_flat: Optional[bool] = None

    laufzeit_monate: Optional[int] = None
    kuendigungsfrist_monate: Optional[int] = None
    buendel_slug: str = ""

    dokument_url: str = ""
    dokument_hash: str = ""
    versionsstand: str = ""
    abgerufen_am: str = ""
    rohtext: str = ""
    preistyp: str = PREISTYP_DOKUMENT

    confidence: dict = field(default_factory=dict)
    fundstellen: dict = field(default_factory=dict)

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
                "Feldwerte ohne Fundstelle im Rohtext: " + ", ".join(offen)
            )

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
    text = (
        text.replace("\u200b", "")
        .replace("\xad", "")
        .replace("\xa0", " ")
        .replace("\u2011", "-")
    )
    zeilen = [" ".join(z.split()) for z in text.splitlines()]
    return "\n".join(z for z in zeilen if z)


def zahl(roh: str) -> Optional[float]:
    """Eine deutsche Dezimalzahl als float. "1.234,56" -> 1234.56."""
    if roh is None:
        return None
    s = str(roh).strip().replace("\xa0", "")
    if not s:
        return None
    s = re.sub(r"[^\d,.\-]", "", s)
    if not s:
        return None
    s = re.sub(r"\.(?=\d{3}(?:\D|$))", "", s)
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None
