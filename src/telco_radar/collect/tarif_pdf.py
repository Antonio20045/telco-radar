"""Aus einem Produktinformationsblatt werden Felder.

Was hier gelesen wird
---------------------
Produktinformationsblaetter nach § 1 TK-Transparenzverordnung und
Vertragszusammenfassungen nach EU-Verordnung 2019/2243. Beide sind
gesetzlich vorgeschrieben, oeffentlich, ohne Login erreichbar und im Aufbau
normiert - und das Normierte ist der Grund, warum hier regulaere Ausdruecke
und nicht ein Modell die Hauptarbeit machen.

Warum Regex zuerst und das Modell nur fuer den Rest
---------------------------------------------------
`pdftotext -layout` liefert bei diesen Dokumenten bereits saubere Tabellen.
Die Feldbezeichner sind vom Verordnungsgeber vorgegeben
("Mindestvertragslaufzeit", "Datenuebertragungsraten", "Entgelt fuer das
Komplettprodukt"). Ein Regex darauf ist nicht nur billiger als ein
Modellaufruf, er ist auch BELEGBAR: er trifft eine Textzeile, und die Zeile
wandert als Fundstelle mit in den Datensatz.

Ein Modell, das "39,99" sagt, ohne dass jemand nachsehen kann, wo es das her
hat, ist in diesem Projekt wertlos - dieselbe Ueberlegung wie beim
Prueflauf gegen den Originaltext (`analyze/faithfulness.py`).

Die Trennung, die diese Datei traegt
------------------------------------
`lies_text()` erwartet TEXT, nicht ein PDF. `text_aus_pdf()` ist die duenne
Schale, die `pdftotext` aufruft. Das ist kein Stilfrage, sondern der Grund,
warum die Testsuite ohne poppler laeuft: die gesamte Extraktionslogik wird
gegen gespeicherte Textfixtures geprueft. Wer nur die Schale nicht testen
kann, verliert einen Test; wer die Logik ans Binary bindet, verliert
achtzig.

Gemessen an vier echten Dokumenten (2x Telekom, 2x o2, Stand 08.08.2026),
die als Fixtures beiliegen.
"""
from __future__ import annotations

import hashlib
import logging
import re
import shutil
import subprocess
from pathlib import Path

from ..tarif_model import (
    HOCH, MITTEL, Geraetepreis, Preisphase, Tarif, normalisiere, zahl,
)

log = logging.getLogger(__name__)

# Ein Dokument, das keinen dieser Saetze traegt, ist kein PIB und keine
# Vertragszusammenfassung.
_KENNZEICHEN = re.compile(
    r"Produktinformationsblatt|Vertragszusammenfassung|TK-Transparenzverordnung",
    re.I)

_GELD = r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}|\d+)\s*(?:€|EUR)"



class PDFNichtLesbar(RuntimeError):
    """pdftotext fehlt, oder die Datei ist kein lesbares PDF."""


def text_aus_pdf(pfad: Path) -> str:
    """Der Textinhalt eines PDF, mit erhaltener Spaltenanordnung.

    `-layout` ist nicht optional: ohne die Anordnung faellt die
    Geraetepreisstaffel (fuenf Betraege in einer Tabellenzeile) in fuenf
    zusammenhanglose Zahlen, und die Zuordnung zur Kategoriezeile darueber
    ist weg.
    """
    if not shutil.which("pdftotext"):
        raise PDFNichtLesbar(
            "pdftotext fehlt (Paket poppler-utils) - PDF nicht lesbar")
    try:
        fertig = subprocess.run(
            ["pdftotext", "-layout", str(pfad), "-"],
            capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise PDFNichtLesbar(f"{pfad}: {exc}") from exc
    if fertig.returncode != 0 and not fertig.stdout:
        raise PDFNichtLesbar(
            f"{pfad}: pdftotext meldet {fertig.returncode}: "
            f"{fertig.stderr.decode('utf-8', 'replace')[:200]}")
    return fertig.stdout.decode("utf-8", "replace")


def ist_tarifdokument(text: str) -> bool:
    return bool(_KENNZEICHEN.search(text or ""))


def dokument_hash(rohdaten: bytes | str) -> str:
    """Der Fingerabdruck des Dokuments.

    Gerechnet ueber den INHALT, nicht ueber die URL: dieselbe Datei unter
    zwei Adressen ist derselbe Tarif, und eine unveraenderte Datei unter
    derselben Adresse darf keinen neuen Datensatz erzeugen.
    """
    if isinstance(rohdaten, str):
        rohdaten = rohdaten.encode("utf-8")
    return hashlib.sha256(rohdaten).hexdigest()[:32]


# --------------------------------------------------------------------------- #
# Die einzelnen Felder
# --------------------------------------------------------------------------- #

def _zeile_mit(text: str, muster: re.Pattern) -> str:
    for zeile in text.splitlines():
        if muster.search(zeile):
            return zeile
    return ""


def _name_und_art(text: str, t: Tarif) -> None:
    """Der Produktname steht als eigene Zeile, meist mit der Art in Klammern.

    Die Klammer kann die Abrechnungsform mitfuehren: congstar schreibt
    "Allnet Flat L (Postpaid Mobilfunk)". Ohne sie im Muster fiel der Name
    in den Rueckfallzweig und trug den Klammerzusatz mit - auf der Seite
    stand dann "Allnet Flat XL mit Upgrade-Versprechen (Postpaid" samt
    offener Klammer, weil die Zeile im PDF umbricht. Die Art blieb dabei
    leer, und ein Tarif ohne Art faellt aus jeder Filterung heraus.
    """
    muster = re.compile(
        r"^(.{3,80}?)\s*\((?:(?:Post|Pre)paid\s+)?(Mobilfunk|Festnetz)\)\s*$",
        re.I)
    for zeile in text.splitlines():
        treffer = muster.match(zeile.strip())
        if treffer:
            t.setze("name", treffer.group(1).strip(), zeile)
            t.setze("art", treffer.group(2).lower(), zeile)
            return
    # Ohne Klammerzusatz: die erste Zeile nach dem Kennzeichen, die kein
    # Fliesstext ist.
    for zeile in text.splitlines():
        z = zeile.strip()
        if (3 < len(z) < 80 and not _KENNZEICHEN.search(z)
                and not z.endswith(".") and re.search(r"[A-Za-zÄÖÜ]", z)):
            # Eine offene Klammer am Ende ist ein Zeilenumbruch im PDF,
            # kein Namensbestandteil: congstars XL-Blatt bricht
            # "(Postpaid Mobilfunk)" um, und auf der Seite stand
            # "Allnet Flat XL mit Upgrade-Versprechen (Postpaid". Der
            # BELEG bleibt die vollstaendige Zeile - abgeschnitten wird
            # der Wert, nicht die Fundstelle.
            t.setze("name", re.sub(r"\s*\([^)]*$", "", z).strip() or z, zeile)
            return


def _laufzeit(text: str, t: Tarif) -> None:
    """Mindestlaufzeit und Kuendigungsfrist.

    Der Flex-Fall ist der wichtigere: "Keine Mindestlaufzeit" MUSS 0 ergeben
    und darf nicht als "nicht gefunden" durchgehen. Ein Tarif ohne Bindung
    ist die Aussage, nicht die Abwesenheit einer Aussage - und der
    Effektivpreis rechnet sonst gegen 24 Monate, die es nicht gibt.
    """
    keine = re.compile(r"(Keine\s+Mindest(?:vertrags)?laufzeit"
                       r"|hat\s+keine\s+Mindestlaufzeit)", re.I)
    zeile = _zeile_mit(text, keine)
    if zeile:
        t.setze("laufzeit_monate", 0, zeile)
    else:
        muster = re.compile(
            r"Mindest(?:vertrags)?laufzeit\D{0,20}?(\d{1,2})\s*Monat", re.I)
        treffer = muster.search(text)
        if treffer:
            t.setze("laufzeit_monate", int(treffer.group(1)),
                    _zeile_mit(text, muster))

    # Kuendigungsfrist. Zwei Satzstellungen kommen vor, und beide muessen
    # getroffen werden:
    #   Telekom: "Kündigungsfrist ein Monat"        - Zahl NACH dem Begriff
    #   o2:      "mit einer Frist von 1 Monat ..."  - Zahl DAVOR
    # Die erste Fassung kannte nur die Telekom-Stellung und liess bei beiden
    # o2-Dokumenten das Feld leer.
    worte = {"einem": 1, "einer": 1, "ein": 1, "zwei": 2, "drei": 3}
    for muster in (
        re.compile(r"Frist\s+von\s+(\d{1,2}|einem|einer|ein)\s*Monat", re.I),
        re.compile(r"Kündigungsfrist\D{0,20}?"
                   r"(\d{1,2}|einem|einer|ein|zwei|drei)\s*Monat", re.I),
        re.compile(r"(\d{1,2}|einem|einer|ein)\s*Monat\D{0,30}?"
                   r"(?:gekündigt|kündbar)", re.I),
    ):
        treffer = muster.search(text)
        if not treffer:
            continue
        roh = treffer.group(1).lower()
        wert = worte.get(roh) or (int(roh) if roh.isdigit() else None)
        if wert is not None:
            t.setze("kuendigungsfrist_monate", wert, _zeile_mit(text, muster))
            break


def _geschwindigkeit(text: str, t: Tarif) -> None:
    """Maximale Uebertragungsrate im Down- und Upload.

    Genommen wird der GROESSTE genannte Maximalwert. Das o2-Festnetzdokument
    beschreibt drei Produktvarianten in einem PDF (175/250/300) - der erste
    Treffer waere die kleinste, und die Positionskarte (A6) zeigte den
    Anbieter dauerhaft zu schwach.
    """
    muster = re.compile(
        r"^(?:Geschätzter\s+Maximalwert|Maximal)\b(.*)$", re.I | re.M)
    unten, oben, beleg = [], [], ""
    for treffer in muster.finditer(text):
        rest = treffer.group(1)
        raten = re.findall(r"(\d+(?:[.,]\d+)?)\s*(MBit/s|GBit/s|KBit/s)", rest,
                           re.I)
        if len(raten) < 1:
            continue
        beleg = beleg or treffer.group(0)
        werte = []
        for wert, einheit in raten[:2]:
            v = zahl(wert)
            if v is None:
                continue
            einheit = einheit.lower()
            if einheit == "gbit/s":
                v *= 1000
            elif einheit == "kbit/s":
                v /= 1000
            werte.append(v)
        if werte:
            unten.append(werte[0])
        if len(werte) > 1:
            oben.append(werte[1])
    if unten:
        t.setze("speed_down_max", max(unten), beleg)
    if oben:
        t.setze("speed_up_max", max(oben), beleg)


def _drossel(text: str, t: Tarif) -> None:
    """Datenvolumen und die Rate danach.

    Der Bezeichner traegt beides: "Ab Verbrauch von 80 GB reduziert auf:
    64 KBit/s 16 KBit/s". Das Volumen aus dieser Zeile zu nehmen ist
    zuverlaessiger als aus dem Marketingtext - hier ist es die Schwelle, ab
    der gedrosselt wird, und die ist rechtlich definiert.
    """
    muster = re.compile(
        r"Ab\s+Verbrauch\s+von\s+(\d+(?:[.,]\d+)?)\s*(GB|MB|TB)", re.I)
    treffer = muster.search(text)
    if not treffer:
        return
    menge = zahl(treffer.group(1))
    einheit = treffer.group(2).upper()
    if menge is not None:
        if einheit == "MB":
            menge /= 1024
        elif einheit == "TB":
            menge *= 1024
        t.setze("datenvolumen_gb", menge, _zeile_mit(text, muster))

    # Die Raten stehen in derselben oder der naechsten Zeile.
    zeilen = text.splitlines()
    for i, zeile in enumerate(zeilen):
        if not muster.search(zeile):
            continue
        block = " ".join(zeilen[i:i + 3])
        raten = re.findall(r"(\d+(?:[.,]\d+)?)\s*(KBit/s|MBit/s)", block, re.I)
        werte = []
        for wert, einheit in raten[:2]:
            v = zahl(wert)
            if v is None:
                continue
            werte.append(v * 1000 if einheit.lower() == "mbit/s" else v)
        if werte:
            t.setze("drossel_down", werte[0], zeile)
        if len(werte) > 1:
            t.setze("drossel_up", werte[1], zeile)
        break


def _volumen_ohne_drossel(text: str, t: Tarif) -> None:
    """Das Datenvolumen, wenn es nicht an einer Drosselschwelle haengt."""
    if t.datenvolumen_gb is not None:
        return
    if re.search(r"\bUnlimited\b|unbegrenzt(?:es)?\s+Datenvolumen", text, re.I):
        # Unlimited ist eine Aussage, kein fehlender Wert. Als None waere der
        # Tarif aus jeder Preis-je-GB-Rechnung gefallen - richtig -, aber auch
        # aus der Positionskarte, und dort gehoert er hin.
        t.setze("datenvolumen_gb", float("inf"),
                _zeile_mit(text, re.compile(r"Unlimited|unbegrenzt", re.I)))
        return
    muster = re.compile(r"(\d+(?:[.,]\d+)?)\s*GB\b(?![^\n]*Verbrauch)", re.I)
    treffer = muster.search(text)
    if treffer:
        t.setze("datenvolumen_gb", zahl(treffer.group(1)),
                _zeile_mit(text, muster), MITTEL)


def _volumen_automatik(text: str, t: Tarif) -> None:
    """"Volumen steigt alle 12 Monate um 5 GB, max. 150 GB".

    Der Fall aus dem Auftrag. Er landet als Satz im Feld, nicht als Zahl:
    die Mechanik ist dreiteilig (Takt, Schrittweite, Deckel) und in eine
    Zahl gepresst waere sie falsch.
    """
    muster = re.compile(
        r"[^\n]{0,80}(?:steigt|erhöht|wächst)[^\n]{0,120}?"
        r"\d+\s*(?:GB|Monate)[^\n]{0,120}", re.I)
    treffer = muster.search(text)
    if treffer:
        t.setze("volumen_automatik", " ".join(treffer.group(0).split())[:250],
                treffer.group(0))


def _flatrates(text: str, t: Tarif) -> None:
    if re.search(r"Allnet[- ]?Flat|Flatrate für Gespräche|Telefonie-?Flat",
                 text, re.I):
        t.setze("allnet_flat", True,
                _zeile_mit(text, re.compile(
                    r"Allnet[- ]?Flat|Flatrate für Gespräche|Telefonie-?Flat",
                    re.I)))
    if re.search(r"SMS[- ]?Flat", text, re.I):
        t.setze("sms_flat", True,
                _zeile_mit(text, re.compile(r"SMS[- ]?Flat", re.I)))


def _preis(text: str, t: Tarif, rohzeilen: list[str] | None = None) -> None:
    """Grundgebuehr und die Geraetepreisstaffel.

    Die Staffel ist der Grund, warum `-layout` Pflicht ist: die fuenf
    Betraege stehen in EINER Tabellenzeile, die Kategorien
    ("ohne Smartphone", "mit Top-Smartphone", ...) ein bis drei Zeilen
    darueber. Ohne Spaltenanordnung ist die Zuordnung verloren.

    Die Grundgebuehr ist dann der KLEINSTE Wert der Staffel - die Stufe
    "ohne Smartphone" ist der Tarifpreis, alles darueber enthaelt eine
    Geraetefinanzierung. Wer den ersten Wert der Zeile nimmt, hat meistens
    recht und manchmal einen um 40 € zu hohen Tarifpreis in der Datenbank.
    """
    zeilen = text.splitlines()

    # 1) Die Staffelzeile: >= 3 Betraege in einer Zeile, unter einem
    #    Entgelt-Bezeichner.
    kopf = None
    for i, zeile in enumerate(zeilen):
        if re.search(r"Entgelt für das\s*(?:Komplettprodukt)?", zeile, re.I):
            kopf = i
            break
    if kopf is not None:
        # Die Staffel wird auf den ROHZEILEN gelesen: die Zuordnung
        # Kategorie -> Betrag haengt an der Zeichenposition, und die ist im
        # normalisierten Text weg.
        roh = rohzeilen if rohzeilen is not None else zeilen
        roh_kopf = _kopfzeile(roh)
        for zeile in roh[roh_kopf:roh_kopf + 12] if roh_kopf is not None else []:
            betraege = re.findall(r"\b(\d{1,3},\d{2})\b", zeile)
            if len(betraege) >= 3:
                kategorien = _kategorien_aus_spalten(roh, roh_kopf, zeile)
                staffel = []
                for nr, betrag in enumerate(betraege):
                    wert = zahl(betrag)
                    if wert is None:
                        continue
                    name = (kategorien[nr] if nr < len(kategorien)
                            else f"Stufe {nr + 1}")
                    staffel.append(Geraetepreis(kategorie=name, betrag=wert))
                if staffel:
                    t.setze("geraetepreisstaffel", staffel, zeile)
                    t.setze("grundgebuehr", min(g.betrag for g in staffel),
                            zeile)
                return

    # 2) Die senkrechte Tabellenform (Vodafone): Zeilen sind Kategorien,
    #    Spalten sind Preisphasen. Sie steht VOR den Einzelbetrags-Mustern,
    #    weil ein "Listenpreis"-Block sonst ueber den erstbesten Betrag der
    #    Seite gelesen wuerde - und der erste Betrag einer Preistabelle ist
    #    nicht ihr Grundpreis, sondern nur ihre erste Zeile.
    if _preis_zeilenweise(text, t):
        return

    # 3) Ein einzelner Betrag unter dem Entgelt-Bezeichner.
    muster = re.compile(r"(?:Entgelt für das|exkl\. Hardware|Monatlich)"
                        r"[^\n]{0,60}?" + _GELD, re.I)
    treffer = muster.search(text)
    if treffer:
        t.setze("grundgebuehr", zahl(treffer.group(1)),
                _zeile_mit(text, muster))
        return

    # 4) Der Entgelt-Bezeichner traegt den PRODUKTNAMEN statt des Wortes
    #    "Komplettprodukt": congstar schreibt "Entgelt Allnet Flat L (ohne
    #    Endgerät) 29,00 € / Monat" (gemessen 04.09.2026). Das Muster
    #    verlangt deshalb die Monatsangabe HINTER dem Betrag - sie ist es,
    #    die aus der Zahl einen Grundpreis macht und sie von einem
    #    einmaligen Entgelt unterscheidet.
    muster = re.compile(r"Entgelt\b[^\n]{0,70}?" + _GELD
                        + r"\s*(?:/|pro|je)\s*Monat", re.I)
    treffer = muster.search(text)
    if treffer:
        t.setze("grundgebuehr", zahl(treffer.group(1)),
                _zeile_mit(text, muster))
        return

    # 5) Ein einzelner Listenpreis ohne Phasenspalten. Vodafones
    #    Prepaid-Blaetter (CallYa) benutzen denselben Bezeichner wie die
    #    Postpaid-Tabelle, nur ohne Zeitachse: "Listenpreis inkl. MwSt.
    #    14,99 €". Das steht bewusst NACH der Tabellenform - dort traegt
    #    die Kopfzeile denselben Bezeichner und keinen Betrag, und wer hier
    #    zuerst suchte, faende in einem Postpaid-Blatt die erste
    #    Tabellenzeile statt des Grundpreises.
    muster = re.compile(r"Listenpreis[^\n]{0,60}?" + _GELD, re.I)
    treffer = muster.search(text)
    if treffer:
        zeile = _zeile_mit(text, muster)
        if not _ABRECHNUNG_IN_WOCHEN.search(zeile):
            t.setze("grundgebuehr", zahl(treffer.group(1)), zeile)
        return
    if kopf is not None:
        for zeile in zeilen[kopf:kopf + 12]:
            treffer = re.search(_GELD, zeile)
            if treffer:
                t.setze("grundgebuehr", zahl(treffer.group(1)), zeile)
                return


def _kopfzeile(zeilen: list[str]) -> int | None:
    """Index der Zeile mit dem Entgelt-Bezeichner."""
    for i, zeile in enumerate(zeilen):
        if re.search(r"Entgelt für das\s*(?:Komplettprodukt)?", zeile, re.I):
            return i
    return None


def _zellen(zeile: str) -> list[tuple[int, str]]:
    """Eine `-layout`-Zeile in ihre Zellen, mit Startspalte.

    Getrennt wird an zwei oder mehr Leerzeichen - das ist die Spaltenluecke,
    die `pdftotext -layout` erzeugt. Ein einzelnes Leerzeichen trennt Woerter
    innerhalb einer Zelle ("mit Top-Smartphone").
    """
    return [(t.start(), t.group().strip())
            for t in re.finditer(r"\S(?:[^\s]|\s(?!\s))*", zeile)]


def _kategorien_aus_spalten(rohzeilen: list[str], kopf: int,
                            preiszeile: str) -> list[str]:
    """Die Spaltenueberschriften der Geraetestaffel, SPALTENWEISE gelesen.

    Der Kopf steht ueber drei Zeilen, und er steht in Spalten:

        Komplettprodukt      ohne         mit        mit Top-   mit Premium- mit Premium-
                          Smartphone   Smartphone   Smartphone   Smartphone   Plus-Smart-
        (Listenpreis)       (EUR)        (EUR)        (EUR)        (EUR)      phone (EUR)

    Wer diese drei Zeilen zu einem Text verkettet und mit einem Regex
    durchsucht, bekommt "mit Premium- mit Premium- Smartphone" - zwei
    verschiedene Spalten zu einer Ueberschrift verschmolzen. Genau das ist
    beim ersten Anlauf passiert.

    Deshalb wird ueber die ZEICHENPOSITION zugeordnet: jede Kopfzelle gehoert
    zu dem Betrag, unter dessen Spalte sie steht. Das ist dieselbe
    Ueberlegung wie die Blockgrenze im Aenderungsradar - ein Etikett darf
    nicht aus der Nachbarspalte stammen.
    """
    anker = [pos for pos, wort in _zellen(preiszeile)
             if re.fullmatch(r"\d{1,3},\d{2}", wort)]
    if not anker:
        return []

    # WORTWEISE der naechstgelegenen Betragsspalte zuordnen. Zwei Fallen
    # liegen hier, und beide sind echt aufgetreten:
    #
    #   * Zellen (Trennung an zwei Leerzeichen) reichen nicht:
    #     "mit Premium- mit Premium-" sind ZWEI Spalten mit genau EINEM
    #     Leerzeichen dazwischen.
    #   * Ein harter Spaltenschnitt an der Zeichenposition reicht auch nicht:
    #     er zerschnitt "Smartphone" zu "Smartphon" und "e".
    #
    # Das Wort als kleinste Einheit loest beides: es wird nie zerschnitten,
    # und seine Mitte sagt eindeutig, unter welcher Spalte es steht.
    # Die Spaltenbreite wird GEMESSEN, nicht geraten. Eine feste Toleranz lag
    # bei den beiden gemessenen Telekom-Dokumenten auf der Kippe: "Hardware"
    # aus der Zeilenbeschriftung stand einmal 15 und einmal 14 Zeichen von der
    # ersten Betragsspalte entfernt, und je nach Schwelle landete es als
    # "ohne Smartphone Hardware" in der ersten Kategorie.
    abstaende = [b - a for a, b in zip(anker, anker[1:])] or [16]
    breite = sorted(abstaende)[len(abstaende) // 2]
    # Alles links der ersten Spalte, um mehr als eine halbe Spaltenbreite, ist
    # die Zeilenbeschriftung ("Komplettprodukt", "zzgl. Einmalpreis Hardware").
    # Sie gehoert zu keiner Spalte - das ist eine Aussage ueber den
    # Tabellenaufbau, keine Schwelle.
    gutter = anker[0] - breite / 2

    namen = []
    for pos in anker:
        teile = []
        for zeile in rohzeilen[kopf:kopf + 8]:
            if zeile.strip() == preiszeile.strip():
                break
            for wort in re.finditer(r"\S+", zeile):
                mitte = wort.start() + len(wort.group()) / 2
                if mitte < gutter:
                    continue
                if min(anker, key=lambda a: abs(a - mitte)) == pos:
                    teile.append(wort.group())
        text = " ".join(teile)
        text = re.sub(r"\(EUR\)|\(Listenpreis\)", "", text, flags=re.I)
        # Zeilenumbruch INNERHALB der Spalte: "mit Premium-" / "Plus-Smart-" /
        # "phone" ist eine Ueberschrift, kein Wortpaar.
        text = re.sub(r"-\s+", "-", text)
        # Trennstrich aus dem Umbruch entfernen, echten Bindestrich behalten:
        # "Smart-phone" -> "Smartphone", "Top-Smartphone" bleibt.
        text = re.sub(r"(?<=[a-zäöüß])-(?=[a-zäöüß])", "", text)
        namen.append(" ".join(text.split()) or f"Spalte {len(namen) + 1}")
    return namen


# --------------------------------------------------------------------------- #
# Die zweite Tabellenform: Zeilen sind Kategorien, Spalten sind PREISPHASEN
#
# Telekom schreibt die Geraetestaffel WAAGERECHT - eine Zeile Betraege unter
# fuenf Spaltenueberschriften (`_kategorien_aus_spalten`). Vodafone schreibt
# dieselbe Auskunft SENKRECHT, und stellt daneben die Zeitachse:
#
#     Listenpreis inkl. MwSt.        Monat 1-24        ab Monat 25
#     ohne Smartphone                  49,95 €           49,95 €
#     mit Basic Phone                  54,95 €           54,95 €
#     mit Top Smartphone               89,95 €           89,95 €
#
# Das ist die einzige Stelle in diesem Projekt, an der ein Anbieter seine
# Preisphasen SELBST auszeichnet - "Monat 1-24" und "ab Monat 25" sind keine
# Auslegung, sondern zwei Spaltenueberschriften. Genau dafuer gibt es
# `tarif_model.Preisphase`, und bis zum 04.09.2026 stand dort in jedem
# Datensatz die Ersatzphase "1 bis Vertragsende" aus `lies_text`.
#
# Gelesen wird auf dem NORMALISIERTEN Text und nicht auf den Rohzeilen: hier
# steht das Etikett am Zeilenanfang und die Betraege dahinter, in
# Leserichtung. Die Zeichenposition, die bei Telekom die Zuordnung traegt,
# wird nicht gebraucht - und wo man sie nicht braucht, ist sie eine
# zusaetzliche Fehlerquelle.
#
# GEMESSEN am 04.09.2026 an den elf aktuell vermarkteten Vodafone-Tarifen
# (VF-Mobil-XS/S/M/L/XL, je mit und ohne Smartphone, plus Smart XS): in
# ALLEN elf tragen "Monat 1-24" und "ab Monat 25" denselben Betrag. Die
# Phasen sind also heute im ganzen Bestand gleich hoch - die Struktur ist
# trotzdem echt, und sie ist der Ort, an dem eine Rabattphase auftauchen
# WIRD.

_BETRAG_MIT_WAEHRUNG = re.compile(r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*(?:€|EUR)")

# Woran eine Zeile als GERAETEstufe erkannt wird. Vodafone stellt in
# dieselbe Tabellenform auch Tarifoptionen ("ohne/mit 5 Jahresversprechen",
# "ohne/mit zusaetzlichem Datenvolumen"). Die als Geraetepreisstaffel
# abzulegen waere eine Falschaussage: niemand bekommt dort ein Telefon.
_GERAETESTUFE = re.compile(r"smartphone|phone|handy|tablet|endger", re.I)

# Der Tabellenkopf. "Listenpreis" allein reicht nicht - erst zusammen mit
# einer Monatsspalte ist es diese Tabelle.
_PREISKOPF = re.compile(r"Listenpreis|Monatlicher Preis|Monatspreis", re.I)

# Ein Preis je VIER WOCHEN ist kein Monatspreis, und `Tarif.grundgebuehr`
# meint einen Monatspreis - `Preisphase` rechnet in Monaten, `tco_24` ueber
# 24 davon. Prepaid rechnet im Vierwochentakt: congstar schreibt "Entgelt
# Prepaid Allnet M (ohne Endgerät) 10,00 € / 4 Wochen", Vodafone bei CallYa
# "Listenpreis inkl. MwSt. 14,99 €" ueber "Vertragslaufszeiten 4 Wochen"
# (gemessen 04.09.2026). Dreizehn Zyklen im Jahr sind nicht zwoelf Monate;
# die Zahl umzurechnen waere eine Rechnung dieses Projekts und keine
# Angabe des Anbieters.
#
# Das Muster fuer die Monatsangabe (Fall 4) verlangt "/ Monat" und faellt
# deshalb von selbst richtig. Der einzelne Listenpreis (Fall 5) braucht die
# Sperre ausdruecklich - ohne sie stand Vodafones CallYa mit 14,99 EUR als
# Monatspreis im Bestand.
_ABRECHNUNG_IN_WOCHEN = re.compile(r"(?:/|pro|je)\s*\d*\s*Woche", re.I)
_MONATSSPALTE = re.compile(r"(ab\s+)?Monat\s*(\d{1,3})(?:\s*[-–]\s*(\d{1,3}))?",
                           re.I)


def _phasenspalten(kopfzeile: str) -> list[tuple[int, int | None]]:
    """Die Monatsspalten einer Preistabelle, in Spaltenreihenfolge.

    "Monat 1-24" -> (1, 24), "ab Monat 25" -> (25, None), "Monat 13" -> (13,
    13). Das offene Ende ist bewusst `None` und nicht die Laufzeit: ein
    Vertrag, der nach der Mindestlaufzeit weiterlaeuft, hat dort kein
    Enddatum, und `Preisphase.monate()` rechnet mit `None` gegen den
    uebergebenen Horizont.
    """
    spalten: list[tuple[int, int | None]] = []
    for treffer in _MONATSSPALTE.finditer(kopfzeile):
        ab, von, bis = treffer.group(1), treffer.group(2), treffer.group(3)
        start = int(von)
        if bis:
            spalten.append((start, int(bis)))
        elif ab:
            spalten.append((start, None))
        else:
            spalten.append((start, start))
    return spalten


def _tabellenzeilen(zeilen: list[str],
                    kopf: int) -> list[tuple[str, list[float], str]]:
    """Die Preiszeilen unter einem Tabellenkopf: (Etikett, Betraege, Zeile).

    Die ZEILE wandert mit, weil sie der Beleg ist. Sie aus Etikett und
    Betraegen wieder zusammenzusetzen waere eine zweite Schreibweise
    derselben Zahl - und `Tarif.fehlende_belege()` prueft die Fundstelle
    gegen den Rohtext: "1.099,00 EUR" zurueckformatiert als "1099,00 €"
    stuende dort nicht, und der Beleg fiele aus.

    Abgebrochen wird bei der ersten Zeile OHNE Betrag, sobald mindestens
    eine Zeile gelesen ist - im normalisierten Text sind die Leerzeilen
    weg, und der Fuss ("Vodafone GmbH - Ferdinand-Braun-Platz 1") ist die
    naechste betragslose Zeile. Ohne diesen Abbruch liest die Tabelle die
    Hausnummer als Preis.
    """
    posten: list[tuple[str, list[float], str]] = []
    for zeile in zeilen[kopf + 1:kopf + 16]:
        treffer = list(_BETRAG_MIT_WAEHRUNG.finditer(zeile))
        if not treffer:
            if posten:
                break
            continue
        etikett = " ".join(zeile[:treffer[0].start()].split())
        betraege = [zahl(t.group(1)) for t in treffer]
        if not etikett or any(b is None for b in betraege):
            continue
        posten.append((etikett, betraege, zeile))
    return posten


def _preis_zeilenweise(text: str, t: Tarif) -> bool:
    """Grundgebuehr, Preisphasen und Geraetestaffel aus der senkrechten Form.

    Gibt zurueck, ob die Tabelle gefunden UND gelesen wurde. Der Aufrufer
    faellt sonst auf die Einzelbetrags-Muster zurueck.

    Die Grundgebuehr ist der KLEINSTE Betrag der ersten Phasenspalte -
    dieselbe Regel wie bei der waagerechten Form (`_preis`), und aus
    demselben Grund: die Stufe ohne Geraet ist der Tarifpreis, jede andere
    enthaelt eine Finanzierung.
    """
    zeilen = text.splitlines()
    for i, zeile in enumerate(zeilen):
        if not _PREISKOPF.search(zeile):
            continue
        spalten = _phasenspalten(zeile)
        if not spalten:
            continue
        posten = _tabellenzeilen(zeilen, i)
        if not posten:
            continue

        _, betraege, basiszeile = min(posten, key=lambda p: p[1][0])
        t.setze("grundgebuehr", betraege[0], basiszeile)

        # Nur wenn Spaltenzahl und Betragszahl zusammenpassen. Passen sie
        # nicht, ist die Zuordnung Phase -> Betrag geraten, und eine
        # geratene Phase ist schlimmer als gar keine: sie sieht aus wie eine
        # Messung. Dann bleibt es bei der Ersatzphase aus `lies_text`.
        if len(spalten) == len(betraege):
            t.setze("preisphasen",
                    [Preisphase(von_monat=von, bis_monat=bis, betrag=betrag)
                     for (von, bis), betrag in zip(spalten, betraege)],
                    zeile)

        staffel = [Geraetepreis(kategorie=name, betrag=werte[0])
                   for name, werte, _z in posten if _GERAETESTUFE.search(name)]
        if len(staffel) >= 2:
            t.setze("geraetepreisstaffel", staffel, zeile)
        return True
    return False


def _anschlusspreis(text: str, t: Tarif) -> None:
    muster = re.compile(
        r"(?:Anschlusspreis|Bereitstellungspreis|einmalige[sn]?\s+Entgelt)"
        r"[^\n]{0,60}?" + _GELD, re.I)
    treffer = muster.search(text)
    if treffer:
        t.setze("anschlusspreis", zahl(treffer.group(1)),
                _zeile_mit(text, muster))


def _versionsstand(text: str, t: Tarif) -> None:
    for muster in (
        re.compile(r"Versionsstand:?\s*([\d.]{6,12})", re.I),
        re.compile(r"Stand\s*:?\s*(\d{2}/\d{2,4})", re.I),
        re.compile(r"Vermarktung seit\s*([\d./]{6,12})", re.I),
    ):
        treffer = muster.search(text)
        if treffer:
            t.setze("versionsstand", treffer.group(1).strip(),
                    _zeile_mit(text, muster))
            return


def _anbieter(text: str, t: Tarif) -> None:
    for name, muster in (
        # congstar steht VOR Telekom, und das ist keine Reihenfolgefrage,
        # sondern eine Korrektheitsfrage: das congstar-PIB traegt im Fuss
        # "congstar - eine Marke der Telekom Deutschland GmbH". Heute rettet
        # nur der Zeilenumbruch mitten in diesem Satz das Ergebnis - stuende
        # er auf einer Zeile, waeren alle congstar-Tarife als Telekom in der
        # Datenbank. Eine Marke ist nicht ihr Mutterkonzern; congstar
        # verkauft eigene Tarife zu eigenen Preisen.
        ("congstar", r"\bcongstar\b"),
        ("Telekom", r"Telekom Deutschland GmbH"),
        ("o2", r"Telefónica Germany"),
        ("1&1", r"1&1 (?:Telecom|Mobilfunk)"),
        ("Vodafone", r"Vodafone GmbH"),
    ):
        if re.search(muster, text, re.I):
            t.setze("anbieter", name, _zeile_mit(text, re.compile(muster, re.I)))
            return


# --------------------------------------------------------------------------- #

def lies_text(text: str, *, url: str = "", hash_: str = "",
              abgerufen_am: str = "") -> Tarif:
    """Ein Tarifdokument als Text in Felder zerlegen.

    Erwartet TEXT, nicht PDF - siehe Modul-Docstring. Der Rohtext bleibt am
    Datensatz: er ist der Beleg, gegen den `pruefe_belege()` rechnet.
    """
    sauber = normalisiere(text or "")
    # Die Rohzeilen behalten ihre Spaltenausrichtung - nur die unsichtbaren
    # Zeichen fliegen raus. Ohne sie ist die Geraetestaffel nicht zuzuordnen.
    rohzeilen = (text or "").replace("​", "").replace("­", "").splitlines()
    t = Tarif(dokument_url=url, dokument_hash=hash_,
              abgerufen_am=abgerufen_am, rohtext=sauber)
    if not sauber:
        return t

    _anbieter(sauber, t)
    _name_und_art(sauber, t)
    _laufzeit(sauber, t)
    _geschwindigkeit(sauber, t)
    _drossel(sauber, t)
    _volumen_ohne_drossel(sauber, t)
    _volumen_automatik(sauber, t)
    _flatrates(sauber, t)
    _preis(sauber, t, rohzeilen)
    _anschlusspreis(sauber, t)
    _versionsstand(sauber, t)

    if t.grundgebuehr is not None and not t.preisphasen:
        # Ein PIB nennt den Listenpreis ohne Rabattphasen. Eine Phase ueber
        # die ganze Laufzeit ist die ehrliche Darstellung - und der
        # Effektivpreis rechnet damit ohne Sonderfall.
        t.preisphasen = [Preisphase(von_monat=1, bis_monat=None,
                                    betrag=t.grundgebuehr)]
    return t


def lies_pdf(pfad: Path, *, url: str = "", abgerufen_am: str = "") -> Tarif:
    """Ein Tarifdokument als Datei. Duenne Schale um `lies_text`."""
    pfad = Path(pfad)
    rohdaten = pfad.read_bytes()
    return lies_text(text_aus_pdf(pfad), url=url,
                     hash_=dokument_hash(rohdaten), abgerufen_am=abgerufen_am)
