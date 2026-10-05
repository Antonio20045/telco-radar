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
from datetime import datetime
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

BEOBACHTET = (
    "grundgebuehr",
    "anschlusspreis",
    "datenvolumen_gb",
    "laufzeit_monate",
    "kuendigungsfrist_monate",
    "drossel_down",
    "drossel_up",
    "speed_down_max",
    "speed_up_max",
    "volumen_automatik",
    "allnet_flat",
)

KLEINGEDRUCKT = (
    "datenvolumen_gb",
    "drossel_down",
    "drossel_up",
    "kuendigungsfrist_monate",
    "laufzeit_monate",
    "volumen_automatik",
    "speed_down_max",
    "speed_up_max",
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
    "grundgebuehr": "€/Monat",
    "anschlusspreis": "€",
    "datenvolumen_gb": "GB",
    "laufzeit_monate": "Monate",
    "kuendigungsfrist_monate": "Monate",
    "drossel_down": "KBit/s",
    "drossel_up": "KBit/s",
    "speed_down_max": "MBit/s",
    "speed_up_max": "MBit/s",
}


METHODE_DOKUMENTE = "dokumente"
METHODE_LDJSON = "ldjson"
METHODE_KACHELN = "kacheln"
METHODE_TELEKOM_KACHELN = "telekom_kacheln"

_SEITEN_LESARTEN = {
    METHODE_LDJSON: tarif_ldjson.tarife_aus_html,
    METHODE_KACHELN: tarif_kacheln.tarife_aus_html,
    METHODE_TELEKOM_KACHELN: tarif_telekom_kacheln.tarife_aus_html,
}

METHODEN = (METHODE_DOKUMENTE, *sorted(_SEITEN_LESARTEN))


@dataclass
class Quelle:
    anbieter: str
    einstieg: list[str] = field(default_factory=list)
    pfadmuster: list[str] = field(default_factory=list)
    bevorzugt: list[str] = field(default_factory=list)
    ausschliessen: list[str] = field(default_factory=list)
    max_dokumente: int = 5
    methode: str = METHODE_DOKUMENTE
    user_agent: str | None = None


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
        return f"{name}: {_wert(self.alt, einheit)} → {_wert(self.neu, einheit)}"


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
    for q in daten.get("quellen") or []:
        if not q.get("anbieter") or not q.get("einstieg"):
            continue
        quellen.append(
            Quelle(
                anbieter=str(q["anbieter"]),
                einstieg=[str(u) for u in q["einstieg"]],
                pfadmuster=[str(m).lower() for m in (q.get("pfadmuster") or [])],
                bevorzugt=[str(b).lower() for b in (q.get("bevorzugt") or [])],
                ausschliessen=[str(a).lower() for a in (q.get("ausschliessen") or [])],
                max_dokumente=int(q.get("max_dokumente") or 5),
                methode=str(q.get("methode") or METHODE_DOKUMENTE).strip(),
                user_agent=(str(q["user_agent"]) if q.get("user_agent") else None),
            )
        )
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
    name = re.sub(
        r"\((?:(?:Post|Pre)paid\s+)?(?:Mobilfunk|Festnetz)\)", " ", name, flags=re.I
    )
    schlank = re.sub(
        r"[^a-z0-9]+",
        "-",
        name.lower()
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss"),
    ).strip("-")
    marke = re.sub(r"[^a-z0-9]+", "", (anbieter or "").lower())
    return f"{marke}:{schlank}" if schlank else marke


def dokumentlinks(html: str, basis: str, muster: list[str]) -> list[str]:
    """Die VERLINKTEN Tarifdokumente einer Seite, in Seitenreihenfolge.

    Nur echte `<a href>`. Was hier nicht herauskommt, wird nicht abgerufen -
    das ist die technische Fassung der Regel gegen ID-Enumeration.
    """
    return [url for url, _text in _ankerpaare(html, basis, muster)]


def _ankerpaare(html: str, basis: str, muster: list[str]) -> list[tuple[str, str]]:
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
        stamm = url[: url.rfind(treffer.group(0))]
        if stamm not in neueste or treffer.group(1) > neueste[stamm][0]:
            neueste[stamm] = (treffer.group(1), url)
    behalten = {url for _, url in neueste.values()}
    return [
        u
        for u in links
        if not _VERMARKTUNGSDATUM.search(
            urlsplit(u).path.rstrip("/").rsplit("/", 1)[-1]
        )
        or u in behalten
    ]


def _sortiere(
    links: list[str], bevorzugt: list[str], texte: dict[str, str] | None = None
) -> list[str]:
    """Bevorzugte Dokumente nach vorn - alphabetisch waeren es Tarife von 2017.

    Gesucht wird in der Adresse UND in der Linkbeschriftung. Ohne den Text
    ist congstar nicht steuerbar (durchnumerierte Dateinamen), ohne die
    Adresse nicht die Telekom (Beschriftung ist dort ueberall dieselbe).
    """
    if not bevorzugt:
        return links
    texte = texte or {}

    faecher: list[list[str]] = [[] for _ in range(len(bevorzugt) + 1)]
    for url in links:
        klein = url.lower() + " " + texte.get(url, "").lower()
        for i, b in enumerate(bevorzugt):
            if b in klein:
                faecher[i].append(url)
                break
        else:
            faecher[-1].append(url)

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
            satz.pop("zurueckgezogen_am", None)
            satz.pop("zurueckgezogen_grund", None)

    def lies_nach(self, tid: str, satz: dict) -> list[str]:
        """Dasselbe Dokument, besser gelesen: leere Felder des letzten
        Stands bekommen den Wert, den der Extraktor heute findet.

        Nur Luecken werden gefuellt, nie ein Wert ersetzt - ein anderer
        Wert aus demselben Dokument waere kein Tarifwechsel, sondern ein
        Extraktorwechsel, und der gehoert nicht still in die Zeitreihe.
        Keine Meldung, kein neuer Stand. Anlass: Vodafone Mobil XL
        ("Unlimitierte Highspeed-Daten"), dessen Volumen der Extraktor bis
        P3 nicht las - ohne Nachlesen bliebe es leer, bis Vodafone das PDF
        neu hochlaedt. Rueckgabe: die gefuellten Felder.
        """
        vorher = self.letzter(tid)
        if vorher is None:
            return []
        gefuellt = []
        for feld, wert in satz.items():
            if feld in ("confidence", "fundstellen", "abgerufen_am"):
                continue
            if vorher.get(feld) in (None, "", []) and wert not in (None, "", []):
                vorher[feld] = wert
                gefuellt.append(feld)
        for feld in gefuellt:
            for teil in ("confidence", "fundstellen"):
                if feld in (satz.get(teil) or {}):
                    vorher.setdefault(teil, {})[feld] = satz[teil][feld]
        return gefuellt

    def ziehe_zurueck(self, dokument_url: str, wann: str, grund: str) -> list[str]:
        """Der letzte Stand jedes Tarifs aus diesem Dokument gilt als
        zurueckgezogen - der Anbieter verlinkt es noch, verkauft es aber
        nicht mehr (`Quelle.ausschliessen`).

        Kein Loeschen: die Zeitreihe bleibt, nur der juengste Stand traegt
        das Datum. Leser ueberspringen ihn (`tarif_model.ist_zurueckgezogen`).
        Rueckgabe: die betroffenen Tarif-IDs.
        """
        juengste: dict[str, dict] = {}
        for satz in self.staende:
            juengste[satz["tarif_id"]] = satz
        betroffen = []
        for tid, satz in juengste.items():
            if satz.get("dokument_url") != dokument_url:
                continue
            if not satz.get("zurueckgezogen_am"):
                satz["zurueckgezogen_am"] = wann
                satz["zurueckgezogen_grund"] = grund
            betroffen.append(tid)
        return betroffen

    def speichern(self) -> None:
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        self.pfad.write_text(
            "\n".join(json.dumps(s, ensure_ascii=False) for s in self.staende)
            + ("\n" if self.staende else ""),
            encoding="utf-8",
        )


def vergleiche(alt: dict, neu: Tarif) -> list[Feldaenderung]:
    """Was sich zwischen zwei Staenden geaendert hat, feldweise."""
    aenderungen = []
    for feld in BEOBACHTET:
        a = alt.get(feld)
        n = getattr(neu, feld, None)
        a = None if a == "" else a
        n = None if n == "" else n
        if n is None and a is not None:
            continue
        if feld == "datenvolumen_gb" and a is None and n == float("inf"):
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


def als_item(tarif: Tarif, aenderungen: list[Feldaenderung], stand: datetime) -> Item:
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
    quelle_wo = "im Produktinformationsblatt" if dokument else "auf der Shop-Seite"
    quelle_satz = (
        "Quelle ist das gesetzlich vorgeschriebene Produktinformationsblatt."
        if dokument
        else "Quelle sind die strukturierten Daten der Shop-Seite "
        "des Anbieters (schema.org) - der beworbene Preis von "
        "heute, nicht das Pflichtdokument."
    )
    if nur_klein:
        titel = (
            f"{tarif.anbieter} ändert stillschweigend die Konditionen von {tarif.name}"
        )
        einleitung = (
            "Die Konditionen haben sich geändert, ohne dass der "
            "Preis sich bewegt — und ohne Pressemitteilung. "
        )
    elif preis:
        titel = f"{tarif.anbieter} ändert den Preis von {tarif.name}"
        einleitung = f"Der Preis {quelle_wo} hat sich geändert. "
    else:
        titel = f"{tarif.anbieter} ändert {tarif.name}"
        einleitung = (
            "Das Produktinformationsblatt hat sich geändert. "
            if dokument
            else "Die Shop-Seite hat sich geändert. "
        )

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
        origin="tarif_dokument",
        source_url=tarif.dokument_url,
        id=dokument_hash(kennung)[:16],
    )


def uebernimm_stand(
    tarif: Tarif,
    hash_: str,
    herkunft: str,
    *,
    speicher: TarifSpeicher,
    bilanz: dict,
    im_lauf: dict,
    items: list,
    jetzt: datetime,
) -> None:
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

    vorheriger = speicher.letzter(tid)
    if (
        vorheriger is not None
        and vorheriger.get("preistyp", PREISTYP_DOKUMENT) != tarif.preistyp
    ):
        log.info(
            "Tarif %r liegt schon als %r vor - der neue Satz (%s) "
            "bekommt eine eigene Zeitreihe",
            tarif.name,
            vorheriger.get("preistyp", PREISTYP_DOKUMENT),
            tarif.preistyp,
        )
        tid = f"{tid}#{tarif.preistyp}"

    if tid in im_lauf and im_lauf[tid] != herkunft:
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
        gefuellt = speicher.lies_nach(tid, satz)
        if gefuellt:
            bilanz["nachgelesen"] = bilanz.get("nachgelesen", 0) + 1
            log.info(
                "Tarif %s nachgelesen (gleiches Dokument): %s", tid, ", ".join(gefuellt)
            )
        return

    aenderungen = vergleiche(vorher, tarif)
    speicher.ergaenze(satz)
    if not aenderungen:
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
        text = BeautifulSoup(antwort.text, "html.parser").get_text("\n")
    elif "text" in typ:
        text = antwort.text
    else:
        return None
    return text, dokument_hash(rohdaten)


def _sammle_seite(
    quelle: Quelle,
    http_cfg: dict,
    *,
    hole,
    jetzt: datetime,
    speicher: TarifSpeicher,
    bilanz: dict,
    items: list,
    im_lauf: dict,
    besucht: list,
    erlaubt: set,
    extrahiere,
) -> None:
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
            log.info("Tarifquelle %s nicht lesbar: %s", einstieg, str(exc)[:120])
            continue
        bilanz["geholt"] += 1
        gefunden = extrahiere(
            html,
            anbieter=quelle.anbieter,
            seiten_url=einstieg,
            abgerufen_am=jetzt.date().isoformat(),
        )
        if not gefunden:
            bilanz["ohne_links"] += 1
            log.warning(
                "Tarifquelle %s (%s): HTTP %s, %d Bytes, aber KEIN "
                "Tarif in der Nutzlast der Seite",
                einstieg,
                quelle.anbieter,
                getattr(antwort, "status_code", "?"),
                len(getattr(antwort, "content", b"") or b""),
            )
            continue
        for tarif, hash_ in gefunden[: quelle.max_dokumente]:
            if tarif.ist_quarantaene:
                bilanz["quarantaene"] += 1
                log.info(
                    "Tarif %r von %s traegt weder Preis noch Laufzeit - Quarantaene",
                    tarif.name,
                    einstieg,
                )
                continue
            bilanz["gelesen"] += 1
            uebernimm_stand(
                tarif,
                hash_,
                hash_,
                speicher=speicher,
                bilanz=bilanz,
                im_lauf=im_lauf,
                items=items,
                jetzt=jetzt,
            )


def sammle(
    root: Path, http_cfg: dict, *, jetzt: datetime, hole=None
) -> tuple[list[Item], dict]:
    """Alle Quellen crawlen, Dokumente lesen, Aenderungen melden.

    Der erste Lauf je Tarif legt die Grundlinie und meldet nichts - wie bei
    jedem anderen Radar dieses Projekts.
    """
    hole = hole or fetch
    quellen = lade_quellen(root)
    speicher = TarifSpeicher(Path(root) / "data" / "state" / "tarife.jsonl")
    bilanz = {
        "quellen": len(quellen),
        "einstiege": 0,
        "verlinkt": 0,
        "geholt": 0,
        "gelesen": 0,
        "quarantaene": 0,
        "grundlinie": 0,
        "unveraendert": 0,
        "geaendert": 0,
        "kleingedruckt": 0,
        "fehler": 0,
        "ohne_links": 0,
        "ausgeschlossen": 0,
        "meldungen": 0,
    }
    besucht: list[str] = []
    erlaubt: set[str] = set()
    items: list[Item] = []
    im_lauf: dict[str, str] = {}

    for quelle in quellen:
        quelle_cfg = (
            {**http_cfg, "user_agent": quelle.user_agent}
            if quelle.user_agent
            else http_cfg
        )
        if quelle.methode in _SEITEN_LESARTEN:
            _sammle_seite(
                quelle,
                quelle_cfg,
                hole=hole,
                jetzt=jetzt,
                speicher=speicher,
                bilanz=bilanz,
                items=items,
                im_lauf=im_lauf,
                besucht=besucht,
                erlaubt=erlaubt,
                extrahiere=_SEITEN_LESARTEN[quelle.methode],
            )
            continue
        if quelle.methode != METHODE_DOKUMENTE:
            bilanz["fehler"] += 1
            log.warning(
                "Tarifquelle %s: unbekannte methode %r - uebersprungen (bekannt: %s)",
                quelle.anbieter,
                quelle.methode,
                METHODEN,
            )
            continue
        links: list[str] = []
        texte: dict[str, str] = {}
        for einstieg in quelle.einstieg:
            erlaubt.add(einstieg)
            bilanz["einstiege"] += 1
            try:
                besucht.append(einstieg)
                antwort = hole(einstieg, quelle_cfg)
                gefunden = dokumentlinks(antwort.text, einstieg, quelle.pfadmuster)
                for adresse, beschriftung in linktexte(
                    antwort.text, einstieg, quelle.pfadmuster
                ).items():
                    texte.setdefault(adresse, beschriftung)
            except Exception as exc:  # noqa: BLE001
                bilanz["fehler"] += 1
                log.info("Tarifquelle %s nicht lesbar: %s", einstieg, str(exc)[:120])
                continue
            if not gefunden:
                bilanz["ohne_links"] += 1
                log.warning(
                    "Tarifquelle %s (%s): HTTP %s, %d Bytes, aber "
                    "KEIN Dokumentlink zum Muster %s",
                    einstieg,
                    quelle.anbieter,
                    getattr(antwort, "status_code", "?"),
                    len(getattr(antwort, "content", b"") or b""),
                    quelle.pfadmuster or ["(alle)"],
                )
            erlaubt.update(gefunden)
            links.extend(gefunden)

        vor_auswahl = len(links)
        links = juengste_fassung(links)
        if vor_auswahl != len(links):
            log.info(
                "Tarifquelle %s: %d von %d Adressen sind aeltere Vermarktungsfassungen",
                quelle.anbieter,
                vor_auswahl - len(links),
                vor_auswahl,
            )
        if quelle.ausschliessen:
            behalten = []
            for url in links:
                klein = url.lower() + " " + texte.get(url, "").lower()
                if not any(a in klein for a in quelle.ausschliessen):
                    behalten.append(url)
                    continue
                bilanz["ausgeschlossen"] += 1
                for tid in speicher.ziehe_zurueck(
                    url,
                    jetzt.date().isoformat(),
                    "Dokument noch verlinkt, Tarif nicht mehr im "
                    "Sortiment (tarif_quellen.yaml: ausschliessen)",
                ):
                    log.info(
                        "Tarifquelle %s: %s zurueckgezogen (%s)",
                        quelle.anbieter,
                        tid,
                        texte.get(url, url),
                    )
            links = behalten
        bilanz["verlinkt"] += len(links)
        for url in _sortiere(links, quelle.bevorzugt, texte)[: quelle.max_dokumente]:
            try:
                besucht.append(url)
                ergebnis = _hole_dokument(url, quelle_cfg, hole)
            except Exception as exc:  # noqa: BLE001
                bilanz["fehler"] += 1
                log.info("Tarifdokument %s nicht lesbar: %s", url, str(exc)[:120])
                continue
            if ergebnis is None:
                continue
            text, hash_ = ergebnis
            bilanz["geholt"] += 1
            if not ist_tarifdokument(text):
                continue

            tarif = lies_text(
                text, url=url, hash_=hash_, abgerufen_am=jetzt.date().isoformat()
            )
            if not tarif.anbieter:
                tarif.anbieter = quelle.anbieter
            if tarif.ist_quarantaene:
                bilanz["quarantaene"] += 1
                log.info("Tarifdokument %s: unbekanntes Layout - Quarantaene", url)
                continue
            bilanz["gelesen"] += 1

            uebernimm_stand(
                tarif,
                hash_,
                url,
                speicher=speicher,
                bilanz=bilanz,
                im_lauf=im_lauf,
                items=items,
                jetzt=jetzt,
            )

    speicher.speichern()
    bilanz["meldungen"] = len(items)
    bilanz["besucht"] = besucht
    bilanz["nicht_verlinkt"] = sorted(set(besucht) - erlaubt)
    log.info(
        "Tarif-Sammler: %d Quellen, %d verlinkt, %d geholt, %d gelesen, "
        "%d Grundlinie, %d unveraendert, %d geaendert (davon %d nur "
        "Kleingedrucktes), %d Quarantaene, %d Fehler, %d Einstiege ohne "
        "Dokumentlink",
        bilanz["quellen"],
        bilanz["verlinkt"],
        bilanz["geholt"],
        bilanz["gelesen"],
        bilanz["grundlinie"],
        bilanz["unveraendert"],
        bilanz["geaendert"],
        bilanz["kleingedruckt"],
        bilanz["quarantaene"],
        bilanz["fehler"],
        bilanz["ohne_links"],
    )
    return items, bilanz
