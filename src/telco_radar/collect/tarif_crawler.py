"""Tarifdokumente holen, versionieren - und melden, was sich geaendert hat.

Was hier passiert
-----------------
Je Anbieter werden die konfigurierten Einstiegsseiten gelesen, die dort
VERLINKTEN Tarifdokumente geholt, durch den Extraktor (`tarif_pdf`) geschickt
und mit dem letzten bekannten Stand verglichen. Gleicher Dokument-Hash: nur
`abgerufen_am` wandert weiter. Neuer Hash: Feld-Diff, und der wird zur
Meldung.

Die Regel, die nicht verhandelbar ist
-------------------------------------
**Keine ID-Enumeration.** Abgerufen wird ausschliesslich, was auf einer
konfigurierten Seite als Link stand. Die o2-Dokumente liegen unter
fortlaufenden Blob-IDs in einem S3-Bucket; sie durchzuzaehlen waere trivial
und ist zu unterlassen. Das ist die Grenze zwischen dem Abrufen
oeffentlicher Pflichtdokumente und dem systematischen Leerraeumen einer
fremden Datenbank, und daran haengt § 87b UrhG.

`besuchte_adressen()` fuehrt Buch darueber, und ein Test prueft die Zusage
maschinell - eine Regel, die nur im Kommentar steht, ist keine.

Warum der Content-Type entscheidet und nicht die Dateiendung
------------------------------------------------------------
Die Telekom liefert ihre Produktinformationsblaetter unter
`/produktinformationsblatt/<slug>` - ohne `.pdf`, mit
`Content-Type: application/pdf`. Wer auf die Endung filtert, findet bei der
Telekom kein einziges Dokument.

Warum die Tarif-ID nicht am Dokument haengt
-------------------------------------------
Der Telekom-Slug traegt das Vermarktungsdatum (`magentamobil-l-20240801`).
Eine neue Fassung bekommt einen NEUEN Slug - eine ID aus der Adresse haette
also nie zwei Staende desselben Tarifs verbunden, und der Diff waere nie
gelaufen. Die ID kommt deshalb aus Anbieter plus bereinigtem Produktnamen:
"O2 Mobile Unlimited M Flex (2026)" und dieselbe Zeile ein Jahr spaeter
ergeben `o2:mobile-unlimited-m-flex`.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import yaml
from bs4 import BeautifulSoup

from ..models import Item
from ..tarif_model import PREISTYP_DOKUMENT, PREISTYP_LIVE_SHOP, Tarif
from .http import fetch
from . import tarif_kacheln, tarif_ldjson, tarif_telekom_kacheln
from .tarif_pdf import dokument_hash, ist_tarifdokument, lies_text, text_aus_pdf

log = logging.getLogger(__name__)

# Felder, deren Aenderung eine Meldung wert ist. Die Reihenfolge ist die
# Reihenfolge im Meldungstext.
BEOBACHTET = (
    "grundgebuehr", "anschlusspreis", "datenvolumen_gb", "laufzeit_monate",
    "kuendigungsfrist_monate", "drossel_down", "drossel_up",
    "speed_down_max", "speed_up_max", "volumen_automatik", "allnet_flat",
)

# Das KLEINGEDRUCKTE (A9): Felder, die sich aendern koennen, ohne dass der
# Preis sich bewegt - und die deshalb sonst niemandem auffallen. Genau das
# ist der Grund fuer diesen Radar: eine Drosselgrenze von 80 GB auf 50 GB bei
# gleichem Preis ist eine Preiserhoehung, die nirgends als solche auftaucht.
KLEINGEDRUCKT = (
    "datenvolumen_gb", "drossel_down", "drossel_up", "kuendigungsfrist_monate",
    "laufzeit_monate", "volumen_automatik", "speed_down_max", "speed_up_max",
)

PREISFELDER = ("grundgebuehr", "anschlusspreis")

LESBAR = {
    "grundgebuehr": "Grundpreis",
    "anschlusspreis": "Anschlusspreis",
    "datenvolumen_gb": "Datenvolumen",
    "laufzeit_monate": "Mindestlaufzeit",
    "kuendigungsfrist_monate": "Kündigungsfrist",
    "drossel_down": "Drosselung (Download)",
    "drossel_up": "Drosselung (Upload)",
    "speed_down_max": "Maximale Downloadrate",
    "speed_up_max": "Maximale Uploadrate",
    "volumen_automatik": "Automatische Volumenerhöhung",
    "allnet_flat": "Allnet-Flat",
}

EINHEIT = {
    "grundgebuehr": "€/Monat", "anschlusspreis": "€", "datenvolumen_gb": "GB",
    "laufzeit_monate": "Monate", "kuendigungsfrist_monate": "Monate",
    "drossel_down": "KBit/s", "drossel_up": "KBit/s",
    "speed_down_max": "MBit/s", "speed_up_max": "MBit/s",
}


# Die zwei Lesarten einer Tarifquelle.
#
# `dokumente`  Der urspruengliche und weiterhin der Regelfall: von der
#              Einstiegsseite werden VERLINKTE Pflichtdokumente geholt und
#              durch `tarif_pdf` gelesen.
# `ldjson`     Die Einstiegsseite IST die Nutzlast: ihre strukturierten
#              Daten nach schema.org tragen die Tarife selbst. Kein Link
#              wird geerntet, keine zweite Adresse abgerufen - dieselbe
#              Bauart wie `direkt=True` im Geraetezweig.
METHODE_DOKUMENTE = "dokumente"
METHODE_LDJSON = "ldjson"
# `kacheln`  Wie `ldjson` - die Einstiegsseite IST die Nutzlast -, nur ohne
#            strukturierte Daten: gelesen werden die Preiskacheln, die der
#            Anbieter selbst als solche auszeichnet. Gebaut fuer o2, dessen
#            Tarifseite genau ein ld+json traegt (eine BreadcrumbList) und
#            dessen uebrige Pflichtblaetter unter `/assets/` liegen - einem
#            Pfad, den die fuer uns gueltige robots-Gruppe sperrt.
METHODE_KACHELN = "kacheln"
# `telekom_kacheln`  Wie `kacheln`, nur fuer ein anderes Markup: die
#            Telekom zeichnet ihre Tarife nicht als strukturiertes
#            Web-Component-Attribut aus (wie o2), sondern als
#            React-CSS-Modul-Klassen (`TariffTileModified_...`). Eigener
#            Extraktor, weil das Muster ein anderes ist - siehe
#            `tarif_telekom_kacheln.py` fuer die Messung und die Regel,
#            warum der DURCHGESTRICHENE Preis zaehlt und nicht der grosse
#            "Ø"-Kombipreis.
METHODE_TELEKOM_KACHELN = "telekom_kacheln"

# Die Lesarten, deren Einstiegsseite selbst die Nutzlast ist: kein Link
# wird geerntet, keine zweite Adresse geholt. Sie teilen sich denselben
# Sammelweg und unterscheiden sich nur im Extraktor.
_SEITEN_LESARTEN = {
    METHODE_LDJSON: tarif_ldjson.tarife_aus_html,
    METHODE_KACHELN: tarif_kacheln.tarife_aus_html,
    METHODE_TELEKOM_KACHELN: tarif_telekom_kacheln.tarife_aus_html,
}

# Die GEBAUTEN Methoden - eine einzige Liste, gegen die sich Konfiguration
# und Test messen. Sie steht hier und nicht im Test, damit eine neu gebaute
# Lesart nicht an zwei Stellen nachgetragen werden muss (und die zweite
# vergessen wird).
METHODEN = (METHODE_DOKUMENTE, *sorted(_SEITEN_LESARTEN))


@dataclass
class Quelle:
    anbieter: str
    einstieg: list[str] = field(default_factory=list)
    pfadmuster: list[str] = field(default_factory=list)
    bevorzugt: list[str] = field(default_factory=list)
    max_dokumente: int = 5
    methode: str = METHODE_DOKUMENTE


@dataclass
class Feldaenderung:
    feld: str
    alt: object
    neu: object

    @property
    def ist_kleingedruckt(self) -> bool:
        return self.feld in KLEINGEDRUCKT

    def lesbar(self) -> str:
        name = LESBAR.get(self.feld, self.feld)
        einheit = EINHEIT.get(self.feld, "")
        return (f"{name}: {_wert(self.alt, einheit)} → "
                f"{_wert(self.neu, einheit)}")


def _wert(v, einheit: str) -> str:
    if v is None:
        return "nicht angegeben"
    if isinstance(v, bool):
        return "ja" if v else "nein"
    if isinstance(v, float):
        if v == float("inf"):
            return "unbegrenzt"
        v = int(v) if v == int(v) else round(v, 2)
    return f"{v} {einheit}".strip()


def lade_quellen(root: Path) -> list[Quelle]:
    pfad = Path(root) / "config" / "tarif_quellen.yaml"
    if not pfad.exists():
        return []
    daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    quellen = []
    for q in (daten.get("quellen") or []):
        if not q.get("anbieter") or not q.get("einstieg"):
            continue
        quellen.append(Quelle(
            anbieter=str(q["anbieter"]),
            einstieg=[str(u) for u in q["einstieg"]],
            pfadmuster=[str(m).lower() for m in (q.get("pfadmuster") or [])],
            bevorzugt=[str(b).lower() for b in (q.get("bevorzugt") or [])],
            max_dokumente=int(q.get("max_dokumente") or 5),
            # Eine unbekannte Methode wird NICHT stillschweigend zur
            # Vorgabe gemacht. Sie faellt in `sammle()` als Fehler auf -
            # ein Tippfehler in der Konfiguration soll nicht dazu fuehren,
            # dass eine Shop-Seite als Dokumentverzeichnis gelesen wird und
            # null Links liefert.
            methode=str(q.get("methode") or METHODE_DOKUMENTE).strip(),
        ))
    return quellen


def tarif_id(anbieter: str, name: str) -> str:
    """Stabil ueber Dokumentversionen und Marketing-Umbenennungen.

    Jahreszahlen und Klammerzusaetze fliegen raus: "O2 Mobile Unlimited M
    Flex (2026)" und dieselbe Zeile im Folgejahr sind derselbe Tarif. Ohne
    das haette der Diff nie zwei Staende verbunden, denn der Telekom-Slug
    traegt das Vermarktungsdatum.
    """
    name = re.sub(r"\((?:19|20)\d{2}\)", " ", name or "")
    name = re.sub(r"\b(?:19|20)\d{2}\b", " ", name)
    # Die Dokumentgattung in Klammern gehoert nicht zum Tarifnamen.
    # congstar schreibt "Allnet Flat L (Postpaid Mobilfunk)", die Telekom
    # "MagentaMobil L (Mobilfunk)" - beides ist eine Einordnung des
    # BLATTES, keine Produktbezeichnung. Ohne "Postpaid"/"Prepaid" in
    # dieser Zeile hiess congstars stabiler Schluessel
    # `congstar:allnet-flat-l-postpaid-mobilfunk`, und eine Tarifangabe
    # "Allnet Flat L" von einer Produktseite traf ihn nie.
    name = re.sub(r"\((?:(?:Post|Pre)paid\s+)?(?:Mobilfunk|Festnetz)\)",
                  " ", name, flags=re.I)
    schlank = re.sub(r"[^a-z0-9]+", "-",
                     name.lower().replace("ä", "ae").replace("ö", "oe")
                     .replace("ü", "ue").replace("ß", "ss")).strip("-")
    marke = re.sub(r"[^a-z0-9]+", "", (anbieter or "").lower())
    return f"{marke}:{schlank}" if schlank else marke


def dokumentlinks(html: str, basis: str, muster: list[str]) -> list[str]:
    """Die VERLINKTEN Tarifdokumente einer Seite, in Seitenreihenfolge.

    Nur echte `<a href>`. Was hier nicht herauskommt, wird nicht abgerufen -
    das ist die technische Fassung der Regel gegen ID-Enumeration.
    """
    return [url for url, _text in _ankerpaare(html, basis, muster)]


def _ankerpaare(html: str, basis: str,
                muster: list[str]) -> list[tuple[str, str]]:
    """Adresse und Linkbeschriftung jedes zulaessigen Dokumentlinks.

    DIE EINE STELLE, die entscheidet, was abgerufen werden darf. Die Regel
    gegen ID-Enumeration haengt daran; zwei Funktionen mit je eigener
    Filterung waeren zwei Regeln, und die zweite driftet beim naechsten
    Umbau. Die erste Fassung von `linktexte` hatte genau das: sie liess
    `mailto:`, `#` und den Selbstlink durch, waehrend `dokumentlinks` sie
    verwarf - bei congstar traegt die Einstiegsseite das Pfadmuster selbst.
    """
    gefunden: list[tuple[str, str]] = []
    gesehen: set[str] = set()
    suppe = BeautifulSoup(html or "", "html.parser")
    for anker in suppe.find_all("a"):
        href = (anker.get("href") or "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        voll = urljoin(basis, href)
        pfad = urlsplit(voll).path.lower()
        if muster and not any(m in pfad for m in muster):
            continue
        # Die Einstiegsseite selbst ist kein Dokument.
        if voll.rstrip("/") == basis.rstrip("/"):
            continue
        if voll not in gesehen:
            gesehen.add(voll)
            gefunden.append((voll, " ".join(anker.get_text().split())))
    return gefunden


def linktexte(html: str, basis: str, muster: list[str]) -> dict[str, str]:
    """Zu jeder Dokumentadresse ihre Linkbeschriftung.

    Warum das gebraucht wird: congstar legt 317 Produktinformationsblaetter
    unter durchnumerierten Dateinamen ab
    (`Produktinformationsblatt_549.pdf`). In der ADRESSE steht kein
    Tarifname - im Linktext steht er ("Produktinformationsblatt congstar
    Allnet Flat L mit Upgrade-Versprechen"). Eine Vorauswahl, die nur die
    Adresse liest, kann dort nur die Seitenreihenfolge nehmen, und die ist
    keine Zusage.

    Beide Funktionen lesen dieselbe Stelle (`_ankerpaare`) - die Regel
    gegen ID-Enumeration haengt daran, dass genau eine entscheidet, was
    abgerufen werden darf. `dokumentlinks` bleibt trotzdem die Funktion,
    die der Sammler fragt: sie beantwortet die Frage "was darf ich holen",
    diese hier nur "wie heisst es".
    """
    return {url: text for url, text in _ankerpaare(html, basis, muster) if text}


# Der Slug eines Telekom-Dokuments endet auf dem Vermarktungsdatum:
# `magentamobil-l-20240801`. Bewusst nur vierstellige Jahre ab 2000 -
# dieselbe Ueberlegung wie beim Datum aus dem Link in `collect/rss.py`:
# ein sechsstelliges Muster faende jede Artikelnummer.
_VERMARKTUNGSDATUM = re.compile(r"-(20\d{6})$")


def juengste_fassung(links: list[str]) -> list[str]:
    """Je Tarif nur die neueste Vermarktungsfassung, in Seitenreihenfolge.

    Die Telekom laesst ALLE Faelle seit 2017 verlinkt stehen: allein
    `magentamobil-l` gibt es in vier Staenden (20170601, 20180831,
    20220701, 20240801). Ohne diese Auswahl bekam der Sammler am
    04.09.2026 genau das - vier Fassungen desselben Tarifs, und weil sie
    alle dieselbe Titelzeile "MagentaMobil L" tragen, bekam die STABILE
    Tarif-ID `telekom:magentamobil-l` den Stand von 2017, waehrend der
    aktuelle unter einem Hash-Zusatz landete. Die Zeitreihe haette also am
    toten Produkt gehangen.

    Adressen ohne Datumsendung (o2, Vodafone, congstar) bleiben unberuehrt.
    Verglichen wird als Zeichenkette - `YYYYMMDD` sortiert von sich aus
    richtig.
    """
    neueste: dict[str, tuple[str, str]] = {}
    for url in links:
        name = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
        treffer = _VERMARKTUNGSDATUM.search(name)
        if not treffer:
            continue
        stamm = url[:url.rfind(treffer.group(0))]
        if stamm not in neueste or treffer.group(1) > neueste[stamm][0]:
            neueste[stamm] = (treffer.group(1), url)
    behalten = {url for _, url in neueste.values()}
    return [u for u in links
            if not _VERMARKTUNGSDATUM.search(
                urlsplit(u).path.rstrip("/").rsplit("/", 1)[-1])
            or u in behalten]


def _sortiere(links: list[str], bevorzugt: list[str],
              texte: dict[str, str] | None = None) -> list[str]:
    """Bevorzugte Dokumente nach vorn - alphabetisch waeren es Tarife von 2017.

    Gesucht wird in der Adresse UND in der Linkbeschriftung. Ohne den Text
    ist congstar nicht steuerbar (durchnumerierte Dateinamen), ohne die
    Adresse nicht die Telekom (Beschriftung ist dort ueberall dieselbe).
    """
    if not bevorzugt:
        return links
    texte = texte or {}

    # Je Wunsch ein Fach, plus eins fuer alles Uebrige. Innerhalb eines
    # Fachs bleibt die SEITENREIHENFOLGE: vorher entschied das Alphabet,
    # und das ist hier keine Ordnung, sondern eine Muenze - congstar stellt
    # seine laufenden Tarife nach oben, und
    # `Produktinformationsblatt_549.pdf` steht alphabetisch vor `_9001.pdf`,
    # ohne dass die Zahl etwas bedeutet.
    faecher: list[list[str]] = [[] for _ in range(len(bevorzugt) + 1)]
    for url in links:
        klein = url.lower() + " " + texte.get(url, "").lower()
        for i, b in enumerate(bevorzugt):
            if b in klein:
                faecher[i].append(url)
                break
        else:
            faecher[-1].append(url)

    # REIHUM, nicht Fach fuer Fach. Der Unterschied ist am 04.09.2026
    # gemessen worden: `magentamobil-s-` trifft neun Dokumente (der Tarif,
    # seine Flex-, Young-, Friends- und Happy-Varianten), und weil sie alle
    # vor dem ersten M-Dokument standen, brachte ein Deckel von zwoelf
    # NEUNMAL MagentaMobil S und kein einziges Mal M, L, XL oder Basic.
    # Ein Wunschzettel, dessen erster Punkt den ganzen Einkauf frisst, ist
    # keiner - dieselbe Ueberlegung wie `_interleave_by_source` in der
    # Pipeline.
    sortiert: list[str] = []
    for runde in range(max((len(f) for f in faecher[:-1]), default=0)):
        for fach in faecher[:-1]:
            if runde < len(fach):
                sortiert.append(fach[runde])
    sortiert.extend(faecher[-1])
    return sortiert


class TarifSpeicher:
    """Die Zeitreihe je Tarif. Eine Zeile je Stand, jsonl."""

    def __init__(self, pfad: Path) -> None:
        self.pfad = Path(pfad)
        self.staende: list[dict] = []
        if self.pfad.exists():
            for zeile in self.pfad.read_text(encoding="utf-8").splitlines():
                zeile = zeile.strip()
                if not zeile:
                    continue
                try:
                    satz = json.loads(zeile)
                except json.JSONDecodeError:
                    continue
                if isinstance(satz, dict) and satz.get("tarif_id"):
                    self.staende.append(satz)

    def letzter(self, tid: str) -> dict | None:
        for satz in reversed(self.staende):
            if satz.get("tarif_id") == tid:
                return satz
        return None

    def ergaenze(self, satz: dict) -> None:
        self.staende.append(satz)

    def beruehre(self, tid: str, wann: str) -> None:
        """Unveraendertes Dokument: kein neuer Datensatz, nur ein Datum.

        Ohne das waechst die Datei jede Woche um den vollstaendigen Bestand,
        und die Zeitreihe besteht zu 99 % aus Wiederholungen.
        """
        satz = self.letzter(tid)
        if satz is not None:
            satz["abgerufen_am"] = wann

    def speichern(self) -> None:
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        self.pfad.write_text(
            "\n".join(json.dumps(s, ensure_ascii=False) for s in self.staende)
            + ("\n" if self.staende else ""), encoding="utf-8")


def vergleiche(alt: dict, neu: Tarif) -> list[Feldaenderung]:
    """Was sich zwischen zwei Staenden geaendert hat, feldweise."""
    aenderungen = []
    for feld in BEOBACHTET:
        # Der leere String ist ein FEHLENDER Wert, kein Wert. `volumen_
        # automatik` faengt als "" an; ohne diese Zeile meldete jeder erste
        # Vergleich eine Aenderung "nicht angegeben -> nicht angegeben".
        a = alt.get(feld)
        n = getattr(neu, feld, None)
        a = None if a == "" else a
        n = None if n == "" else n
        # Ein Feld, das der Extraktor diesmal NICHT gefunden hat, ist keine
        # Aenderung - es ist ein Ausfall. Als "80 GB -> nicht angegeben" zu
        # melden waere die haeufigste Falschmeldung dieses Radars.
        if n is None and a is not None:
            continue
        if a is None and n is None:
            continue
        if isinstance(a, float) and isinstance(n, float):
            if abs(a - n) < 1e-9 or (a == float("inf") and n == float("inf")):
                continue
        elif a == n:
            continue
        aenderungen.append(Feldaenderung(feld=feld, alt=a, neu=n))
    return aenderungen


def als_item(tarif: Tarif, aenderungen: list[Feldaenderung],
             stand: datetime) -> Item:
    """Die Aenderung als Meldung.

    Der Titel unterscheidet den Preis vom Kleingedruckten. Das ist keine
    Kosmetik: "Telekom aendert den Preis" liest jeder, "Telekom halbiert das
    Datenvolumen bei gleichem Preis" ist die Meldung, die es sonst nirgends
    gibt.

    UND DIE MELDUNG NENNT IHRE QUELLENART (seit dem 04.09.2026). Bis dahin
    stand in jeder Meldung "Quelle ist das gesetzlich vorgeschriebene
    Produktinformationsblatt" - ein starker Satz, und fuer einen Shop-Preis
    schlicht falsch. Eine Zahl aus den strukturierten Daten einer
    Werbeseite traegt keine gesetzliche Wahrheitsbewehrung, und sie soll
    sich auch nicht so anfuehlen. `Tarif.preistyp` entscheidet, welcher der
    zwei Saetze darunter steht.
    """
    nur_klein = all(a.ist_kleingedruckt for a in aenderungen)
    preis = [a for a in aenderungen if a.feld in PREISFELDER]
    dokument = tarif.preistyp != PREISTYP_LIVE_SHOP
    quelle_kurz = "Produktinformationsblatt" if dokument else "Shop-Seite"
    # Mit Praeposition, damit beide Saetze deutsch bleiben: "im
    # Produktinformationsblatt" gegen "auf der Shop-Seite".
    quelle_wo = ("im Produktinformationsblatt" if dokument
                 else "auf der Shop-Seite")
    quelle_satz = ("Quelle ist das gesetzlich vorgeschriebene "
                   "Produktinformationsblatt." if dokument else
                   "Quelle sind die strukturierten Daten der Shop-Seite "
                   "des Anbieters (schema.org) - der beworbene Preis von "
                   "heute, nicht das Pflichtdokument.")
    if nur_klein:
        titel = (f"{tarif.anbieter} ändert stillschweigend die Konditionen "
                 f"von {tarif.name}")
        einleitung = ("Die Konditionen haben sich geändert, ohne dass der "
                      "Preis sich bewegt — und ohne Pressemitteilung. ")
    elif preis:
        titel = f"{tarif.anbieter} ändert den Preis von {tarif.name}"
        einleitung = f"Der Preis {quelle_wo} hat sich geändert. "
    else:
        titel = f"{tarif.anbieter} ändert {tarif.name}"
        einleitung = ("Das Produktinformationsblatt hat sich geändert. "
                      if dokument else
                      "Die Shop-Seite hat sich geändert. ")

    liste = " · ".join(a.lesbar() for a in aenderungen[:8])
    kennung = f"{tarif_id(tarif.anbieter, tarif.name)}|{tarif.dokument_hash}"
    return Item(
        title=titel,
        url=tarif.dokument_url,
        source_name=f"{tarif.anbieter} ({quelle_kurz})",
        region="europe",
        operator=tarif.anbieter,
        published=stand,
        summary=(einleitung + liste + ". " + quelle_satz)[:900],
        # `origin` bleibt der Name des ZWEIGS und nicht der der Quellenart:
        # er sagt der Pipeline, welcher Sammler die Meldung erzeugt hat.
        # Ein zweiter Wert waere ein zweiter Zweig, den niemand kennt.
        origin="tarif_dokument",
        source_url=tarif.dokument_url,
        # Aus Tarif UND Dokument-Hash: zwei Aenderungen desselben Tarifs
        # muessen zwei Meldungen sein, sonst haelt der Seen-Store die zweite
        # fuer die schon berichtete erste.
        id=dokument_hash(kennung)[:16],
    )


def uebernimm_stand(tarif: Tarif, hash_: str, herkunft: str, *,
                    speicher: TarifSpeicher, bilanz: dict, im_lauf: dict,
                    items: list, jetzt: datetime) -> None:
    """Einen gelesenen Tarif in die Zeitreihe legen - und melden, was neu ist.

    DIE EINE STELLE, an der ueber Grundlinie, Unveraendertheit und Meldung
    entschieden wird. Sie steht hier als eigene Funktion, seit es ZWEI
    Lesarten gibt (Pflichtdokument und Shop-Seite): zwei Kopien dieser
    Entscheidungskette waeren zwei Delta-Schichten, und die zweite wuerde
    irgendwann anders melden als die erste.

    `herkunft` ist, was den einzelnen Fund identifiziert - bei einem
    Dokument seine Adresse, bei einem ld+json-Knoten sein Fingerabdruck.
    Der Unterschied ist noetig, weil sieben Tarife derselben Seite
    dieselbe Adresse tragen; ohne ihn waeren zwei gleichnamige Knoten
    zwei Fassungen desselben Tarifs statt zweier Produkte.
    """
    tid = tarif_id(tarif.anbieter, tarif.name)

    # ZWEI LESARTEN SIND ZWEI ZEITREIHEN, KEINE ZWEI FASSUNGEN.
    #
    # Live gemessen am 04.09.2026: o2s Produktinformationsblatt und o2s
    # SIM-only-Kachel nennen beide "O2 Mobile Unlimited M Flex" - dieselbe
    # Tarif-ID, zwei voellig verschiedene Quellen. Ohne diese Zeilen wurde
    # der Kachelsatz zur naechsten FASSUNG des Blattes, und `vergleiche`
    # meldete als Tarifaenderung, was in Wahrheit der Unterschied zwischen
    # einem PDF und einer Werbeseite ist (das Blatt nennt eine
    # Mindestlaufzeit, die Flex-Kachel keine).
    #
    # Genau dagegen ist `preistyp` gebaut: "Beide duerfen auseinanderlaufen;
    # die Abweichung ist die Auskunft, nicht der Fehler." Eine gemeinsame
    # Zeitreihe kann das nicht abbilden - in ihr ueberschreibt die eine
    # Lesart die andere.
    #
    # Der Zusatz ist der PREISTYP und nicht ein Hash: er ist je Quelle
    # konstant, also bleibt der Schluessel ueber die Laeufe stabil. Ein
    # Inhaltshash (wie beim Fall darunter) waere hier falsch - er aenderte
    # sich mit jeder Preisaenderung, und die Zeitreihe zerfiele in
    # Einzelsaetze.
    #
    # Wer zuerst da war, behaelt den kurzen Schluessel. Das ist keine
    # Rangfolge, sondern Bestandsschutz: die vorhandene Zeitreihe soll
    # nicht umziehen.
    vorheriger = speicher.letzter(tid)
    if (vorheriger is not None
            and vorheriger.get("preistyp", PREISTYP_DOKUMENT)
            != tarif.preistyp):
        log.info("Tarif %r liegt schon als %r vor - der neue Satz (%s) "
                 "bekommt eine eigene Zeitreihe", tarif.name,
                 vorheriger.get("preistyp", PREISTYP_DOKUMENT),
                 tarif.preistyp)
        tid = f"{tid}#{tarif.preistyp}"

    if tid in im_lauf and im_lauf[tid] != herkunft:
        # ZWEI verschiedene Funde mit derselben Titelzeile im SELBEN Lauf.
        # Live gemessen am 08.08.2026: o2 fuehrt `o2-home-l-flex` und
        # `o2-home-l-175-flex` als getrennte PDFs, beide mit der
        # Ueberschrift "O2 Home L 175/250/300 Flex". Ohne Unterscheidung
        # waere das zweite eine neue Fassung des ersten - und der Diff
        # meldete bei jedem Lauf abwechselnd hin und her.
        #
        # Zwei Staende NACHEINANDER sind eine Versionsfolge, zwei im
        # selben Lauf sind zwei Produkte.
        tid = f"{tid}#{dokument_hash(herkunft)[:8]}"
    im_lauf[tid] = herkunft
    satz = tarif.als_dict()
    satz["tarif_id"] = tid
    vorher = speicher.letzter(tid)

    if vorher is None:
        bilanz["grundlinie"] += 1
        speicher.ergaenze(satz)
        return
    if vorher.get("dokument_hash") == hash_:
        bilanz["unveraendert"] += 1
        speicher.beruehre(tid, jetzt.date().isoformat())
        return

    aenderungen = vergleiche(vorher, tarif)
    speicher.ergaenze(satz)
    if not aenderungen:
        # Neuer Hash, gleiche Werte: der Anbieter hat das Layout
        # angefasst, nicht den Tarif. Keine Meldung.
        bilanz["unveraendert"] += 1
        return
    bilanz["geaendert"] += 1
    if all(a.ist_kleingedruckt for a in aenderungen):
        bilanz["kleingedruckt"] += 1
    items.append(als_item(tarif, aenderungen, jetzt))


def _hole_dokument(url: str, http_cfg: dict, hole) -> tuple[str, str] | None:
    """Ein Dokument abrufen und in Text verwandeln.

    Gibt (Text, Hash) zurueck oder None. Der Content-Type entscheidet, ob
    es ein PDF ist - die Telekom liefert PDFs ohne Dateiendung.
    """
    antwort = hole(url, http_cfg)
    typ = (antwort.headers.get("content-type") or "").lower()
    rohdaten = antwort.content
    if "pdf" in typ or rohdaten[:5] == b"%PDF-":
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as f:
            f.write(rohdaten)
            f.flush()
            text = text_aus_pdf(Path(f.name))
    elif "html" in typ:
        # Manche Anbieter legen die Vertragszusammenfassung als HTML ab.
        text = BeautifulSoup(antwort.text, "html.parser").get_text("\n")
    elif "text" in typ:
        # Reiner Text kommt selten vor, ist aber schon fertig.
        text = antwort.text
    else:
        return None
    return text, dokument_hash(rohdaten)


def _sammle_seite(quelle: Quelle, http_cfg: dict, *, hole, jetzt: datetime,
                  speicher: TarifSpeicher, bilanz: dict, items: list,
                  im_lauf: dict, besucht: list, erlaubt: set,
                  extrahiere) -> None:
    """Eine Quelle, deren Einstiegsseite selbst die Tarife traegt.

    `extrahiere` ist die Lesart (`_SEITEN_LESARTEN`): strukturierte Daten
    nach schema.org oder die Preiskacheln des Anbieters. Der Weg drumherum
    ist derselbe, und er steht deshalb genau einmal hier - zwei Kopien
    waeren zwei Delta-Schichten, und die zweite meldete irgendwann anders
    als die erste.

    Es wird KEIN Link geerntet und keine zweite Adresse geholt: die Seite
    ist die Nutzlast. Damit ist die Regel "nur abrufen, was verlinkt ist"
    hier trivial erfuellt - abgerufen wird ausschliesslich die Adresse, die
    in der Konfiguration steht.

    `geholt` zaehlt die Seite mit, `verlinkt` nicht: es wurde nichts
    verlinkt. Eine Null in einer Spalte, die hier gar nichts messen kann,
    waere eine Falschmeldung im Protokoll.
    """
    for einstieg in quelle.einstieg:
        erlaubt.add(einstieg)
        bilanz["einstiege"] += 1
        try:
            besucht.append(einstieg)
            antwort = hole(einstieg, http_cfg)
            html = antwort.text
        except Exception as exc:  # noqa: BLE001
            bilanz["fehler"] += 1
            log.info("Tarifquelle %s nicht lesbar: %s", einstieg,
                     str(exc)[:120])
            continue
        bilanz["geholt"] += 1
        gefunden = extrahiere(
            html, anbieter=quelle.anbieter, seiten_url=einstieg,
            abgerufen_am=jetzt.date().isoformat())
        if not gefunden:
            # Derselbe Befund wie eine Einstiegsseite ohne Dokumentlink,
            # und er muss genauso laut sein: eine Seite, die 200 und 450 KB
            # liefert und trotzdem keinen Tarif hergibt, hat entweder ihr
            # Format geaendert oder eine Challenge ausgeliefert. Ohne
            # Status und Groesse in der Zeile ist das nicht zu
            # unterscheiden (die Telekom-Lehre vom 04.09.2026).
            bilanz["ohne_links"] += 1
            log.warning("Tarifquelle %s (%s): HTTP %s, %d Bytes, aber KEIN "
                        "Tarif in der Nutzlast der Seite",
                        einstieg, quelle.anbieter,
                        getattr(antwort, "status_code", "?"),
                        len(getattr(antwort, "content", b"") or b""))
            continue
        for tarif, hash_ in gefunden[:quelle.max_dokumente]:
            if tarif.ist_quarantaene:
                bilanz["quarantaene"] += 1
                log.info("Tarif %r von %s traegt weder Preis noch Laufzeit - "
                         "Quarantaene", tarif.name, einstieg)
                continue
            bilanz["gelesen"] += 1
            # Die Herkunft ist hier der Fingerabdruck des Knotens: alle
            # Tarife dieser Seite teilen sich ihre Adresse.
            uebernimm_stand(tarif, hash_, hash_, speicher=speicher,
                            bilanz=bilanz, im_lauf=im_lauf, items=items,
                            jetzt=jetzt)


def sammle(root: Path, http_cfg: dict, *, jetzt: datetime | None = None,
           hole=None) -> tuple[list[Item], dict]:
    """Alle Quellen crawlen, Dokumente lesen, Aenderungen melden.

    Der erste Lauf je Tarif legt die Grundlinie und meldet nichts - wie bei
    jedem anderen Radar dieses Projekts.
    """
    jetzt = jetzt or datetime.now(timezone.utc)
    hole = hole or fetch
    quellen = lade_quellen(root)
    speicher = TarifSpeicher(Path(root) / "data" / "state" / "tarife.jsonl")
    bilanz = {"quellen": len(quellen), "einstiege": 0, "verlinkt": 0,
              "geholt": 0, "gelesen": 0, "quarantaene": 0, "grundlinie": 0,
              "unveraendert": 0, "geaendert": 0, "kleingedruckt": 0,
              "fehler": 0, "ohne_links": 0, "meldungen": 0}
    besucht: list[str] = []
    erlaubt: set[str] = set()
    items: list[Item] = []
    # Welche Tarif-ID in DIESEM Lauf schon von welcher Adresse kam.
    im_lauf: dict[str, str] = {}

    for quelle in quellen:
        if quelle.methode in _SEITEN_LESARTEN:
            _sammle_seite(quelle, http_cfg, hole=hole, jetzt=jetzt,
                          speicher=speicher, bilanz=bilanz, items=items,
                          im_lauf=im_lauf, besucht=besucht, erlaubt=erlaubt,
                          extrahiere=_SEITEN_LESARTEN[quelle.methode])
            continue
        if quelle.methode != METHODE_DOKUMENTE:
            # Eine unbekannte Methode wird laut, nicht still: sonst faellt
            # ein Tippfehler in der Konfiguration erst auf, wenn jemand
            # merkt, dass ein Anbieter seit Wochen nichts mehr liefert.
            bilanz["fehler"] += 1
            log.warning("Tarifquelle %s: unbekannte methode %r - "
                        "uebersprungen (bekannt: %s)", quelle.anbieter,
                        quelle.methode, METHODEN)
            continue
        links: list[str] = []
        texte: dict[str, str] = {}
        for einstieg in quelle.einstieg:
            erlaubt.add(einstieg)
            bilanz["einstiege"] += 1
            try:
                besucht.append(einstieg)
                antwort = hole(einstieg, http_cfg)
                gefunden = dokumentlinks(antwort.text, einstieg,
                                         quelle.pfadmuster)
                # setdefault statt update: innerhalb einer Seite gewinnt
                # der ERSTE Linktext, ueber mehrere Einstiegsseiten soll
                # dasselbe gelten. Mit `update` gewaenne dort der letzte -
                # zwei Regeln fuer dieselbe Frage.
                for adresse, beschriftung in linktexte(
                        antwort.text, einstieg, quelle.pfadmuster).items():
                    texte.setdefault(adresse, beschriftung)
            except Exception as exc:  # noqa: BLE001
                bilanz["fehler"] += 1
                log.info("Tarifquelle %s nicht lesbar: %s", einstieg,
                         str(exc)[:120])
                continue
            if not gefunden:
                # Eine Einstiegsseite ohne einen einzigen Dokumentlink ist
                # der lauteste Befund dieses Sammlers - und er war bis zum
                # 04.09.2026 vollkommen stumm. Genau so ist die Telekom
                # zwei Monate lang als "liefert nichts" gefuehrt worden:
                # ihre Seite antwortet aus GitHub Actions mit einer
                # Challenge (HTTP 202, rund 2 KB), die kein Fehler ist und
                # keinen Link enthaelt. Aus derselben Sandbox heraus
                # liefert dieselbe Adresse 200 und 1114 Links. Ohne Status
                # und Groesse in der Zeile ist das nicht zu unterscheiden.
                bilanz["ohne_links"] += 1
                log.warning("Tarifquelle %s (%s): HTTP %s, %d Bytes, aber "
                            "KEIN Dokumentlink zum Muster %s",
                            einstieg, quelle.anbieter,
                            getattr(antwort, "status_code", "?"),
                            len(getattr(antwort, "content", b"") or b""),
                            quelle.pfadmuster or ["(alle)"])
            erlaubt.update(gefunden)
            links.extend(gefunden)

        # `verlinkt` zaehlt, was nach der Auswahl "juengste Fassung" noch
        # in Frage kommt - nicht, was auf der Seite stand. Die rohe Zahl
        # steht in der Protokollzeile der Einstiegsseite; hier interessiert,
        # aus wie vielen Kandidaten der Deckel schneidet.
        vor_auswahl = len(links)
        links = juengste_fassung(links)
        if vor_auswahl != len(links):
            log.info("Tarifquelle %s: %d von %d Adressen sind aeltere "
                     "Vermarktungsfassungen", quelle.anbieter,
                     vor_auswahl - len(links), vor_auswahl)
        bilanz["verlinkt"] += len(links)
        for url in _sortiere(links, quelle.bevorzugt,
                             texte)[:quelle.max_dokumente]:
            try:
                besucht.append(url)
                ergebnis = _hole_dokument(url, http_cfg, hole)
            except Exception as exc:  # noqa: BLE001
                bilanz["fehler"] += 1
                log.info("Tarifdokument %s nicht lesbar: %s", url,
                         str(exc)[:120])
                continue
            if ergebnis is None:
                continue
            text, hash_ = ergebnis
            bilanz["geholt"] += 1
            if not ist_tarifdokument(text):
                continue

            tarif = lies_text(text, url=url, hash_=hash_,
                              abgerufen_am=jetzt.date().isoformat())
            if not tarif.anbieter:
                # Der Anbieter aus der Config, nicht aus dem Dokument.
                # Deshalb OHNE Fundstelle und bewusst nicht ueber setze():
                # die Belegpflicht gilt fuer das, was im Dokument steht, und
                # dieser Wert steht dort gerade nicht. Ihn mit einer
                # erfundenen Fundstelle zu versehen waere genau die
                # Unehrlichkeit, gegen die pruefe_belege() gebaut ist.
                tarif.anbieter = quelle.anbieter
            if tarif.ist_quarantaene:
                bilanz["quarantaene"] += 1
                log.info("Tarifdokument %s: unbekanntes Layout - Quarantaene",
                         url)
                continue
            bilanz["gelesen"] += 1

            # Die Adresse ist die Herkunft des Dokuments - siehe
            # `uebernimm_stand`.
            uebernimm_stand(tarif, hash_, url, speicher=speicher,
                            bilanz=bilanz, im_lauf=im_lauf, items=items,
                            jetzt=jetzt)

    speicher.speichern()
    bilanz["meldungen"] = len(items)
    bilanz["besucht"] = besucht
    bilanz["nicht_verlinkt"] = sorted(set(besucht) - erlaubt)
    log.info("Tarif-Sammler: %d Quellen, %d verlinkt, %d geholt, %d gelesen, "
             "%d Grundlinie, %d unveraendert, %d geaendert (davon %d nur "
             "Kleingedrucktes), %d Quarantaene, %d Fehler, %d Einstiege ohne "
             "Dokumentlink",
             bilanz["quellen"], bilanz["verlinkt"], bilanz["geholt"],
             bilanz["gelesen"], bilanz["grundlinie"], bilanz["unveraendert"],
             bilanz["geaendert"], bilanz["kleingedruckt"],
             bilanz["quarantaene"], bilanz["fehler"], bilanz["ohne_links"])
    return items, bilanz
