"""Die CTM-Linse: nicht "ist das wichtig?", sondern "ist das fuer UNS wichtig?".

Das Problem, das sie loest
--------------------------
Bis zum 08.08.2026 kannte die Bewertung eine einzige Achse - "Prioritaet 1-5",
gemessen an branchenweiter Bedeutung. Fuer ein Team, das Portfolio,
Tarifoptionen und Logistik im deutschen Endkundengeschaeft verantwortet, ist
das der falsche Massstab, und der Beleg steht in der Ausgabe vom 07.08.2026:
die sieben Eintraege der Spalte "Was wichtig ist" waren Turminfrastruktur in
Afrika, zweimal derselbe rumaenische Spamfilter, OpenAI, ein
oesterreichischer Discounter, US-Spektrum und indisches FWA - kein einziger
davon handlungsrelevant. Gleichzeitig stand "Telekom-Flatrate mit
Unlimited-Daten fuer 34,95 Euro bei Freenet" klein in der dritten Reihe.

Die zweite Achse
----------------
    3  DIREKT        deutscher Markt, Endkunde, Preis/Portfolio/Option/Logistik
    2  UEBERTRAGBAR  Consumer-Mechanik in einem vergleichbaren Markt
    1  KONTEXT       Branche, Technik, Regulatorik mit mittelbarer Wirkung
    0  HINTERGRUND   Infrastruktur, B2B, Kapitalmarkt ohne Endkundenbezug

Sortiert wird nach dieser Achse VOR der Prioritaet. Damit landet die
Telekom-Flat oben und der Spamfilter gar nicht erst im Spitzenmodul.

**Stufe 3 rechnet der Code, nicht das Modell.** Dieselbe Bauweise wie beim
Promo-Score, wo 45 % deterministisch gerechnet werden und genau das ihn
stabil macht: ein Modell, das seinen Massstab jeden Lauf neu auslegt, ist als
Sortierkriterium wertlos. Das Modell darf eine Stufe 3 auch nicht wegnehmen -
es darf nur zwischen 0, 1 und 2 unterscheiden, wo der Code nichts weiss.

Der Satz
--------
Jede Meldung ab Stufe 2 bekommt genau EINEN zusaetzlichen Satz: was das fuer
das eigene Portfolio heisst. Er muss eine Konsequenz oder eine Frage
enthalten, nicht die Meldung wiederholen - "Das zeigt den Trend zu Bundles"
ist der Fehlgriff, "Erste 5G-Flat unter 35 Euro im deutschen Markt - drueckt
die Preisuntergrenze fuer unsere Unlimited-Stufe" der Zielzustand.

Verhaeltnis zu "beobachtend statt empfehlend"
---------------------------------------------
CLAUDE.md §8 und `textwerkzeug.ohne_vodafone_rat()` halten die PROSA frei von
Ratschlaegen an Vodafone. Diese Regel bleibt unangetastet: sie gilt dem
Wochenbericht und den Kartenbegruendungen, die sonst wie eine
Beratungsrechnung klingen. Der CTM-Satz ist etwas anderes - ein eigenes,
ausgewiesenes Feld unter einer eigenen Ueberschrift, das genau die Frage
beantwortet, wegen der jemand die Seite ueberhaupt aufschlaegt. Er laeuft
deshalb NICHT durch die Ratschlags-Filter. Wer das dreht, dreht den Auftrag
vom 08.08.2026 zurueck.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Die Zahlenrechnung des Prueflaufs, nicht eine zweite daneben. Ob eine Zahl
# "aus der Quelle" stammt, muss hier dasselbe heissen wie dort - sonst laesst
# der Kasten eine Zeile zu, die die Belegpruefung verworfen haette.
# faithfulness importiert nur `.llm`, also entsteht kein Ringschluss.
from .faithfulness import _zahlen_gedeckt
from ..textwerkzeug import begriffs_muster

log = logging.getLogger(__name__)

DIREKT, UEBERTRAGBAR, KONTEXT, HINTERGRUND = 3, 2, 1, 0

STUFEN_LABEL = {
    3: "Direkt für uns",
    2: "Übertragbar",
    1: "Kontext",
    0: "Hintergrund",
}

STUFEN_ERKLAERUNG = {
    3: "Deutscher Markt, Endkundengeschäft, Preis, Portfolio, Option oder "
       "Logistik – hier ist eine Entscheidung möglich.",
    2: "Eine Endkundenmechanik aus einem vergleichbaren Markt – lässt sich "
       "auf das eigene Portfolio übertragen.",
    1: "Branche, Technik oder Regulierung mit mittelbarer Wirkung.",
    0: "Infrastruktur, Geschäftskunden oder Kapitalmarkt ohne "
       "Endkundenbezug.",
}

# Maximale Laenge des CTM-Satzes in Woertern. Kein Schnitt - ein zu langer
# Satz wird VERWORFEN, nicht gekuerzt. Ein Halbsatz mit "…" ist in dieser
# Codebasis schon zweimal als Fehler benannt worden.
MAX_WOERTER = 28

# Eine Zahl, die als eigenes Wort steht - fuer die Aufnahmeregel des
# Kurzpfads (siehe `hat_zahl_aus_der_quelle`). Die Rechnung des Prueflaufs
# selbst bleibt bewusst weiter gefasst: dort geht es darum, ob eine Ziffer
# erfunden ist, und da zaehlt auch die im Modellnamen.
_ECHTE_ZAHL = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)*(?![\w])")

# Woerter, an denen ein Satz als Wiederholung statt als Konsequenz erkennbar
# ist. Sie sind nicht verboten, sie reichen nur nicht: ein Satz, der KEINES
# der Konsequenzmuster traegt, faellt.
_KONSEQUENZ = re.compile(
    r"(drück|druck|zwing|erfordert?|verlangt|müssen wir|müssten wir|"
    r"brauchen wir|bräuchte|unsere[nrms]?\b|unser\b|eigene[nrms]?\b|"
    r"vorlage|kontern|nachziehen|gleichzieh|antwort|risiko|chance|"
    r"frage|prüfen|offen ist|untergrenze|obergrenze|erwarten|"
    r"werden fragen|verhandl|marge|abwander|wechsel)", re.I)

# Reine Beobachtungssaetze, die nichts fuer das eigene Haus folgern.
_LEERFORMEL = re.compile(
    r"^(das zeigt|dies zeigt|zeigt,? dass|ein weiterer schritt|"
    r"unterstreicht|verdeutlicht|bestätigt den trend|passt in den trend)",
    re.I)


@dataclass
class CtmFokus:
    """Der geladene Zuschnitt aus config/ctm_fokus.yaml."""

    heimatmarkt: list[str] = field(default_factory=list)
    nachbarmarkt: list[str] = field(default_factory=list)
    direkte_kategorien: set[str] = field(default_factory=set)
    direkte_stichworte: list[str] = field(default_factory=list)
    vergleichbare_maerkte: list[str] = field(default_factory=list)
    sicherheitsskala: list[dict] = field(default_factory=list)

    # Vorberechnete Suchmuster. Ein Markenname darf nicht mitten in einem
    # anderen Wort treffen: ohne Wortgrenze fand "O2" jedes "CO2", und "Blau"
    # jedes "blauen Licht". Dieselbe Lehre wie beim Promo-Zweig, wo "EUR" ohne
    # Wortgrenze aus "1 Euro einmalig" die Kachel "1 Eur" schnitt.
    _heimat_re: re.Pattern | None = None
    _nachbar_re: re.Pattern | None = None

    def __post_init__(self) -> None:
        self._heimat_re = _marken_muster(self.heimatmarkt)
        self._nachbar_re = _marken_muster(self.nachbarmarkt)

    def trifft_heimatmarkt(self, text: str) -> bool:
        return bool(self._heimat_re and self._heimat_re.search(text or ""))

    def trifft_nachbarmarkt(self, text: str) -> bool:
        return bool(self._nachbar_re and self._nachbar_re.search(text or ""))


def _marken_muster(marken: list[str]) -> re.Pattern | None:
    """Seit dem 11.08.2026 nur noch ein Aufruf: die Rechnung steht in
    `textwerkzeug.begriffs_muster()`. Sie war hier, in `fruehwarnung.py` und
    in `wettbewerb.py` dreimal getippt - und die Newsletter-Stichwoerter
    waeren die vierte Fassung gewesen."""
    return begriffs_muster(marken, kein_punkt_davor=True)


def lade_fokus(root: Path) -> CtmFokus:
    """Laedt config/ctm_fokus.yaml. Fehlt sie, bleibt die Linse wirkungslos -
    kein Grund, einen Lauf zu kippen."""
    pfad = Path(root) / "config" / "ctm_fokus.yaml"
    if not pfad.exists():
        log.warning("config/ctm_fokus.yaml fehlt - die CTM-Linse bleibt aus")
        return CtmFokus()
    daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    return CtmFokus(
        heimatmarkt=list(daten.get("heimatmarkt_marken") or []),
        nachbarmarkt=list(daten.get("nachbarmarkt_marken") or []),
        direkte_kategorien=set(daten.get("direkte_kategorien") or []),
        direkte_stichworte=[s.lower() for s in
                            (daten.get("direkte_stichworte") or [])],
        vergleichbare_maerkte=list(daten.get("vergleichbare_maerkte") or []),
        sicherheitsskala=list(daten.get("sicherheitsskala") or []),
    )


def deterministische_stufe(h: dict, fokus: CtmFokus) -> int | None:
    """Stufe 3, wenn der Code sie BELEGEN kann - sonst None.

    Belegen heisst: eine Marke des Heimatmarktes kommt vor UND es geht um
    etwas, das ein Endkunde kauft. Beides zusammen, nie eins allein - "Deutsche
    Telekom baut Rechenzentrum" ist Heimatmarkt und trotzdem keine
    Portfoliofrage, "Jio senkt Preise" ist eine Preisfrage und trotzdem nicht
    unser Markt.
    """
    text = " ".join(str(h.get(f) or "") for f in
                    ("operator", "title", "headline", "summary"))
    if not fokus.trifft_heimatmarkt(text):
        return None
    kategorie = (h.get("category") or "").strip()
    if kategorie in fokus.direkte_kategorien:
        return DIREKT
    klein = text.lower()
    if any(wort in klein for wort in fokus.direkte_stichworte):
        return DIREKT
    return None


def _rueckfall_stufe(h: dict, fokus: CtmFokus) -> int:
    """Wenn kein Modellwert da ist: eine begruendbare Stufe statt einer Null.

    Ohne diesen Rueckfall stuenden bei einem Lauf ohne Modell (oder mit
    gescheiterten Stapeln) alle Meldungen auf Stufe 0 und die Sortierung
    waere leer - schlimmer als vorher, weil die Prioritaet dann nichts mehr
    ordnete.
    """
    text = " ".join(str(h.get(f) or "") for f in
                    ("operator", "title", "headline", "summary"))
    kategorie = (h.get("category") or "").strip()
    endkunde = kategorie in fokus.direkte_kategorien
    if fokus.trifft_heimatmarkt(text) or fokus.trifft_nachbarmarkt(text):
        return UEBERTRAGBAR if endkunde else KONTEXT
    if endkunde:
        return UEBERTRAGBAR if (h.get("region") or "") in \
            fokus.vergleichbare_maerkte else KONTEXT
    if kategorie in {"Finanzen", "M&A"}:
        return HINTERGRUND
    return KONTEXT


def satz_taugt(satz: str) -> tuple[bool, str]:
    """Haelt der "Was heisst das fuer uns"-Satz die Regeln ein?

    Der Prompt sagt sie an, aber ein Prompt ist keine Zusicherung. Gemessen
    wird hier, weil ein Satz, der die Meldung nur wiederholt, schlimmer ist
    als keiner: er kostet eine Zeile und liefert nichts.
    """
    s = " ".join((satz or "").split())
    if not s:
        return False, "leer"
    woerter = s.split()
    if len(woerter) > MAX_WOERTER:
        return False, f"zu lang ({len(woerter)} Wörter)"
    if len(woerter) < 4:
        return False, "zu kurz"
    if s.count(".") > 2 or "\n" in satz or s.lstrip().startswith(("-", "•")):
        return False, "kein einzelner Satz"
    if _LEERFORMEL.match(s):
        return False, "Leerformel statt Konsequenz"
    if not _KONSEQUENZ.search(s):
        return False, "keine Konsequenz erkennbar"
    return True, ""


def veredle(highlights: list[dict], fokus: CtmFokus) -> dict:
    """Setzt `ctm_bezug`, `ctm_label` und prueft `ctm_satz` je Meldung.

    Aendert die Meldungen an Ort und Stelle und liefert eine Bilanz fuers
    Laufprotokoll. Der Rueckgabewert ist kein Beiwerk: ohne Zahl im Protokoll
    laesst sich nach einem Lauf nicht sagen, ob die Linse gegriffen hat oder
    nur nichts gefunden wurde.
    """
    bilanz = {"direkt": 0, "uebertragbar": 0, "kontext": 0, "hintergrund": 0,
              "saetze": 0, "saetze_verworfen": 0, "gruende": {}}
    for h in highlights:
        fest = deterministische_stufe(h, fokus)
        if fest is not None:
            stufe = fest
            h["ctm_quelle"] = "regel"
        else:
            roh = h.get("ctm_bezug")
            try:
                stufe = int(roh)
            except (TypeError, ValueError):
                stufe = _rueckfall_stufe(h, fokus)
                h["ctm_quelle"] = "rückfall"
            else:
                stufe = max(HINTERGRUND, min(UEBERTRAGBAR, stufe))
                h["ctm_quelle"] = "modell"
        h["ctm_bezug"] = stufe
        h["ctm_label"] = STUFEN_LABEL[stufe]

        satz = " ".join(str(h.get("ctm_satz") or "").split())
        if stufe >= UEBERTRAGBAR and satz:
            ok, grund = satz_taugt(satz)
            if ok:
                h["ctm_satz"] = satz
                bilanz["saetze"] += 1
            else:
                h.pop("ctm_satz", None)
                bilanz["saetze_verworfen"] += 1
                bilanz["gruende"][grund] = bilanz["gruende"].get(grund, 0) + 1
        else:
            # Unter Stufe 2 gibt es keinen Satz. Nicht aus Sparsamkeit: ein
            # Konsequenzsatz zu einer Meldung ohne Konsequenz ist erfunden.
            h.pop("ctm_satz", None)

        bilanz[{3: "direkt", 2: "uebertragbar", 1: "kontext",
                0: "hintergrund"}[stufe]] += 1
    return bilanz


def hat_zahl_aus_der_quelle(h: dict) -> bool:
    """Nennt der Folgerungssatz eine konkrete Zahl, die in der Quelle steht?

    Die Trennlinie zwischen einer Beobachtung und einer Ableitung. "Ein
    gestaffelter Trade-in-Bonus koennte den Geraetewechsel beschleunigen" ist
    ein Konjunktiv ueber nichts - er laesst sich weder pruefen noch
    widerlegen. "Bis zu 500 Zloty Bonus" ist eine Zahl, die im Originaltext
    steht und die morgen jemand nachschlagen kann.

    Verlangt wird BEIDES: mindestens eine mehrstellige Zahl im Satz, die als
    eigenes Wort steht, und keine einzige Zahl darin, die in Titel oder
    Zusammenfassung fehlt.

    "Als eigenes Wort" ist der Teil, der beim ersten Anlauf gefehlt hat.
    Gegen die Ausgabe vom 08.08.2026 gemessen kam "Das Redmi 17C 5G koennte
    das Einsteigersegment dominieren" durch - "17" ist zweistellig und steht
    im Titel. Es ist nur keine Zahl, sondern ein Modellname. Eine Ziffer, an
    der ein Buchstabe klebt, behauptet nichts, was sich nachschlagen liesse;
    "900 TV-Kanaele" und "300 Dollar" tun es.
    """
    satz = h.get("ctm_satz") or ""
    zahlen = [z for z in _ECHTE_ZAHL.findall(satz)
              if len(z.replace(".", "").replace(",", "")) > 1]
    if not zahlen:
        return False
    quelle = f"{h.get('title') or ''} {h.get('summary') or ''}"
    return _zahlen_gedeckt(satz, quelle) is None


# Der Zuschnitt des Kurzpfads. Er steht HIER und nicht bei seinem Aufrufer,
# weil ihn zwei Aufrufer haben: die Startseite und die Montagsmail. Zwei
# Zahlenpaare an zwei Orten waren am 09.08.2026 kurz davor, aus einer
# Auswahl zwei zu machen - und eine Mail, die etwas anderes hervorhebt als
# die Seite, auf die sie verlinkt, ist schlimmer als keine Mail.
KURZPFAD_ZEILEN = 3
KURZPFAD_WOERTER = 20


def kurzpfad(highlights: list[dict]) -> list[dict]:
    """Die Zeilen, die Startseite UND Mail zeigen - eine Auswahl, ein Ort.

    Bis zum 09.08.2026 waren es fuenf Zeilen ohne Wortgrenze und ohne
    Aufnahmeregel. Sie standen ueber dem Aufmacher und haben die Titelseite
    aus dem ersten Bildschirm gedraengt; vier der fuenf waren reine
    Konjunktiv-Ableitungen.
    """
    return zwei_minuten(highlights, KURZPFAD_ZEILEN, nur_belegt=True,
                        max_woerter=KURZPFAD_WOERTER)


def zwei_minuten(highlights: list[dict], max_zeilen: int = 5, *,
                 nur_belegt: bool = False,
                 max_woerter: int = 0) -> list[dict]:
    """Die Zeilen des Zwei-Minuten-Pfads.

    "Lesezeit ca. 16 Minuten" ist ehrlich und trotzdem das Ende der Nutzung:
    16 Minuten liest kein Bereichsleiter. Ein paar Zeilen mit Konsequenz und
    Quellenlink liest er.

    Genommen wird nur, was Stufe >= 2 UND einen geprueften Satz hat. Lieber
    drei Zeilen als fuenf, von denen zwei die Meldung wiederholen - und ein
    Ort, an dem NICHTS steht, sagt auch etwas: dann gab es diese Woche
    nichts, das direkt ins Portfolio spielt.

    Ein Absender kommt hoechstens einmal vor. Ohne diese Regel stuenden in
    einer Telekom-Woche fuenf Telekom-Zeilen, und der Pfad waere kein
    Ueberblick mehr.

    Die zwei Verschaerfungen sind ABWAEHLBAR und aus gutem Grund nicht der
    Standard: der Kasten auf der Titelseite hat wenig Platz und viel
    Gewicht, die Mail (versand.py) hat viel Platz und wenig Gewicht.

    ``nur_belegt`` ist die Aufnahmeregel vom 09.08.2026. Stufe 3 kommt
    immer hinein; Stufe 2 nur mit einer konkreten Zahl aus der Quelle.
    Anlass war die Ausgabe vom 08.08.: fuenf Zeilen, vier davon reine
    Konjunktiv-Ableitungen ("koennte pruefen", "muesste nachschaerfen"),
    keine einzige mit einer Zahl. Ein Satz, der nichts behauptet, das man
    nachschlagen kann, kostet die wertvollste Zeile der Seite.

    ``max_woerter`` wirft Saetze hinaus, die als EINE Zeile nicht mehr
    lesbar sind. Gekuerzt wird NICHT: ein auf 20 Woerter geschnittener
    Folgerungssatz ist ein Halbsatz, und ein Halbsatz unter einem
    Quellenlink behauptet etwas, das die Quelle nicht sagt.
    """
    out: list[dict] = []
    gesehen: set[str] = set()
    # Warum eine Zeile NICHT dasteht. Ohne diese Zaehler sagt ein leerer
    # Kasten nur "nichts gefunden" - und ob nichts kam oder ob zwanzig
    # Saetze an der Wortgrenze hingen, liesse sich hinterher nicht mehr
    # beantworten. Dieselbe Ueberlegung wie bei `veredle()`, die ihre
    # verworfenen Saetze samt Grund ins Laufprotokoll gibt.
    gefallen = {"zu lang": 0, "ohne Zahl aus der Quelle": 0}

    def zugelassen(h: dict) -> bool:
        stufe = int(h.get("ctm_bezug") or 0)
        if stufe < UEBERTRAGBAR or not h.get("ctm_satz"):
            return False
        if max_woerter and len(str(h["ctm_satz"]).split()) > max_woerter:
            gefallen["zu lang"] += 1
            return False
        if nur_belegt and stufe < DIREKT and not hat_zahl_aus_der_quelle(h):
            gefallen["ohne Zahl aus der Quelle"] += 1
            return False
        return True

    kandidaten = sorted(
        (h for h in highlights if zugelassen(h)),
        key=lambda h: (-int(h.get("ctm_bezug") or 0),
                       -int(h.get("relevance") or 0),
                       -int(h.get("quellenzahl") or 1)))
    for h in kandidaten:
        absender = (h.get("operator") or h.get("source_label") or "").lower()
        if absender and absender in gesehen:
            continue
        gesehen.add(absender)
        out.append(h)
        if len(out) >= max_zeilen:
            break
    if any(gefallen.values()):
        log.info("Kurzpfad: %d Zeilen aus %d Kandidaten; abgewiesen %s",
                 len(out), len(kandidaten),
                 ", ".join(f"{n}x {grund}" for grund, n in gefallen.items() if n))
    return out
