"""Was bekommt wer? Die Verknuepfungsregel und die Stichwortsuche.

Die Verknuepfungsregel steht ausfuehrlich im Kopf von config/newsletter.yaml.
In einem Satz: **UND zwischen den Dimensionen, ODER innerhalb, leer heisst
alles, Stichwoerter sind additiv.**

Der additive Teil ist der, der ueber Nutzen oder Aerger entscheidet. Ein
Stichworttreffer kommt in die Ausgabe, AUCH wenn die uebrigen Filter ihn
ausgeschlossen haetten - sonst passiert Folgendes: jemand waehlt Region
Europa und das Stichwort "Starlink", bekommt nie eine Starlink-Meldung (die
sind global getaggt) und haelt die Stichwortfunktion fuer kaputt. Und weil
ein additiver Treffer sonst unerklaerlich in der Mail steht, traegt er seinen
Grund mit ("Ihr Stichwort: Starlink").

DIE STICHWORTSUCHE IST DER GEFAEHRLICHSTE TEIL DES GANZEN PAKETS. Das Projekt
kennt das Problem aus dem Fachpresse-Tagging: kurze, mehrdeutige Begriffe wie
`spark`, `tim`, `globe` oder `orange` erzeugen ohne Wortgrenzen massenhaft
Falschtreffer. Dort gibt es dagegen eine gepflegte Blockliste
(`collect._AMBIGUOUS_TERMS`). Hier gibt es keine - die Begriffe tippt der
Abonnent, und niemand kuratiert sie. Vier Sicherungen ersetzen die Kuration:

  1. **Mindestens vier Zeichen.** Damit fallen `tim`, `vi` und `au` von
     selbst weg - genau die Faelle, an denen sich das Tagging verschluckt
     hat.
  2. **Wortgrenzen, keine Teilworttreffer** (`textwerkzeug.begriffs_muster`).
     `spark` trifft nicht in "Sparkasse", `globe` nicht in "Globetrotter",
     `orange` nicht in "Orangensaft".
  3. **Nur Ueberschrift und Zusammenfassung**, nie der Volltext. Ein
     Volltexttreffer ist fast immer Rauschen; die Zusammenfassung ist der
     Teil, den ein Analyst geschrieben hat.
  4. **Die Trefferzahl-Vorschau vor dem Absenden** (`vorschau()`). Das ist
     die wirksamste Einzelmassnahme gegen Abo-Muedigkeit, weil sie das
     Problem loest, bevor es Mails erzeugt.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from ..textwerkzeug import begriffs_muster
from .config import DIMENSIONEN, NewsletterKatalog

# ============================================================  Eintraege  ===


@dataclass
class Eintrag:
    """Eine Meldung oder Aktion, aus Sicht des Newsletters.

    Bewusst eine EIGENE, flache Form und nicht das Highlight-dict des
    Berichts: die Filter muessen Meldungen und Promo-Aktionen gleich
    behandeln, und die beiden Quellen haben nicht ein einziges Feld gemeinsam
    benannt (`headline`/`headline`, aber `source`/`brand`, `region`/nichts).
    Die Uebersetzung steht in `quelle.py`, damit sie an EINER Stelle steht.
    """
    id: str
    bereich: str
    titel: str
    text: str
    url: str
    absender: str = ""
    region: str = ""          # Schluessel, nicht Label
    ressort: str = ""
    betreiber: str = ""
    gewicht: int = 0          # groesser = wichtiger; sortiert die Ausgabe
    datum: str = ""
    anker: str = ""           # Sprungziel im Webbericht

    @property
    def suchtext(self) -> str:
        """Was die Stichwortsuche sieht: Ueberschrift und Zusammenfassung.

        Nicht der Volltext (den gibt es hier ohnehin nicht) und nicht der
        Absender - sonst traefe das Stichwort "Telekom" jede Meldung, die
        zufaellig aus einem Telekom-Newsroom stammt."""
        return f"{self.titel}\n{self.text}"


@dataclass
class Treffer:
    """Ein Eintrag samt der Begruendung, warum er in dieser Ausgabe steht."""
    eintrag: Eintrag
    grund: str                       # "filter" | "stichwort"
    stichwort: str = ""              # nur bei grund == "stichwort"

    @property
    def ueber_stichwort(self) -> bool:
        return self.grund == "stichwort"


# ===========================================================  Stichwoerter ==

@dataclass(frozen=True)
class Stichwort:
    term: str
    mode: str = "word"               # "word" | "phrase"

    def muster(self) -> re.Pattern | None:
        if self.mode == "phrase":
            return _phrasen_muster(self.term)
        return begriffs_muster([self.term])

    def trifft(self, text: str) -> bool:
        m = self.muster()
        return bool(m and m.search(text or ""))


def _phrasen_muster(term: str) -> re.Pattern | None:
    """"Fixed Wireless Access" - mit beliebigem Zwischenraum.

    Zwischen den Woertern steht `[\\s-]+`: der Handel schreibt dieselbe Sache
    mal mit Leerzeichen, mal mit Bindestrich, und ein Umbruch im Fliesstext
    macht aus dem Leerzeichen einen Zeilenumbruch. Aussen gelten dieselben
    Wortgrenzen wie beim einzelnen Wort.
    """
    woerter = [re.escape(w) for w in (term or "").split()]
    if not woerter:
        return None
    return re.compile(r"(?<![\w.])" + r"[\s\-]+".join(woerter) + r"(?!\w)",
                      re.I)


def stichwort_fehler(term: str, katalog: NewsletterKatalog) -> str:
    """Warum dieses Stichwort nicht zulaessig ist - oder "".

    Gibt einen Satz zurueck, der so auf dem Formular stehen kann. Die Pruefung
    laeuft an zwei Orten (Browser und Signup-Dienst); dies ist die
    verbindliche Fassung, das Formular ist die bequeme.
    """
    t = (term or "").strip()
    if not t:
        return "Das Stichwort ist leer."
    # Gemessen wird das LAENGSTE Wort, nicht die ganze Eingabe: "5G in
    # Afrika" ist als Phrase lang genug, aber sein kuerzestes Wort ist zwei
    # Zeichen - und die Wortgrenze traegt trotzdem, weil die ganze Phrase
    # zusammen gesucht wird.
    laengstes = max((len(w) for w in t.split()), default=0)
    if laengstes < katalog.grenzen.min_stichwort_laenge:
        return (f"Zu kurz: mindestens ein Wort mit "
                f"{katalog.grenzen.min_stichwort_laenge} Zeichen. Kurze "
                f"Begriffe treffen zu viel - „tim“ steht in „Optimierung“.")
    if len(t) > 60:
        return "Zu lang: höchstens 60 Zeichen."
    return ""


def lies_stichwoerter(roh) -> list[Stichwort]:
    """Aus dem, was im Abo-Datensatz steht, Stichwoerter machen.

    Vertraegt beide Schreibweisen - eine nackte Zeichenkette und das
    ausfuehrliche `{"term": ..., "mode": ...}`. Ein Abo aus der Fruehzeit
    darf nicht daran scheitern, dass spaeter ein Feld dazukam.
    """
    aus: list[Stichwort] = []
    for eintrag in roh or []:
        if isinstance(eintrag, str):
            term, mode = eintrag, ""
        elif isinstance(eintrag, dict):
            term, mode = str(eintrag.get("term") or ""), str(eintrag.get("mode") or "")
        else:
            continue
        term = term.strip()
        if not term:
            continue
        # Die Betriebsart wird abgeleitet, wenn sie fehlt: alles mit
        # Zwischenraum ist eine Phrase. Ein Abonnent, der "Fixed Wireless
        # Access" eintippt, meint nicht drei Stichwoerter.
        if mode not in {"word", "phrase"}:
            mode = "phrase" if " " in term else "word"
        aus.append(Stichwort(term=term, mode=mode))
    return aus


# ==============================================================  Filter  ====

@dataclass
class Filtersatz:
    """Die vier Dimensionen plus Stichwoerter. Leer heisst alles."""
    bereiche: tuple[str, ...] = ()
    regionen: tuple[str, ...] = ()
    wettbewerber: tuple[str, ...] = ()
    kategorien: tuple[str, ...] = ()
    stichwoerter: tuple[Stichwort, ...] = ()

    def werte(self, dimension: str) -> tuple[str, ...]:
        return getattr(self, dimension)

    @property
    def ist_leer(self) -> bool:
        return not any(self.werte(d) for d in DIMENSIONEN) and not self.stichwoerter


def lies_filtersatz(roh: dict, katalog: NewsletterKatalog) -> Filtersatz:
    """Aus dem `filters`-Block eines Abo-Datensatzes einen Filtersatz.

    **Unbekannte Schluessel fallen weg und zaehlen NICHT als "leer".** Das ist
    die heikle Stelle: haette jemand nur `regions: ["europa-alt"]` gewaehlt
    und die Region gaebe es nicht mehr, waere die Dimension nach dem
    Wegwerfen leer - und "leer heisst alles" wuerde ihm die ganze Welt
    schicken. Deshalb bleibt ein unbekannter Schluessel als Schluessel
    stehen; er trifft dann schlicht nichts, und der Abonnent bekommt eine
    leere Ausgabe (die nicht verschickt wird) statt einer falschen.
    """
    from .config import FELD_JE_DIMENSION
    werte = {}
    for dimension in DIMENSIONEN:
        feld = FELD_JE_DIMENSION[dimension]
        gewaehlt = [str(k).strip() for k in (roh.get(feld) or []) if str(k).strip()]
        # Reihenfolge und Doppelungen sind fuer die Auswahl bedeutungslos -
        # und sie duerfen den Segmentschluessel nicht veraendern.
        werte[dimension] = tuple(sorted(set(gewaehlt)))
    return Filtersatz(
        **werte,
        stichwoerter=tuple(lies_stichwoerter(roh.get("keywords"))[
            :katalog.grenzen.max_stichwoerter]))


def _dimension_trifft(dimension: str, gewaehlt: tuple[str, ...],
                      eintrag: Eintrag, katalog: NewsletterKatalog) -> bool:
    if not gewaehlt:                       # leer heisst alles
        return True
    if dimension == "bereiche":
        return eintrag.bereich in gewaehlt
    if dimension == "regionen":
        return eintrag.region in gewaehlt
    if dimension == "kategorien":
        erlaubt: set[str] = set()
        for key in gewaehlt:
            auswahl = katalog.finde("kategorien", key)
            if auswahl:
                erlaubt.update(auswahl.ressorts)
        return eintrag.ressort in erlaubt
    if dimension == "wettbewerber":
        # Betreiberfeld ODER Ueberschrift. Ohne den zweiten Weg waere jede
        # branchenweite Meldung ("Branche", leeres Betreiberfeld) fuer jeden
        # Wettbewerbsfilter unsichtbar - und das sind genau die Meldungen,
        # in denen drei Anbieter gleichzeitig vorkommen.
        heu = f"{eintrag.betreiber}\n{eintrag.titel}"
        for key in gewaehlt:
            auswahl = katalog.finde("wettbewerber", key)
            if auswahl and auswahl.muster and auswahl.muster.search(heu):
                return True
        return False
    return True


def waehle(eintraege, satz: Filtersatz, katalog: NewsletterKatalog,
           *, max_eintraege: int | None = None) -> list[Treffer]:
    """Die Ausgabe fuer EINEN Filtersatz. Sortiert, gedeckelt, begruendet.

    Die Reihenfolge ist: erst alles, was die Filter treffen, dann die
    Stichworttreffer - beide fuer sich nach Gewicht. Ein Stichworttreffer
    steht also NICHT vor der wichtigsten Meldung des Bereichs, den jemand
    ausgewaehlt hat; er ist eine Zugabe, keine Uebernahme.
    """
    deckel = katalog.grenzen.max_eintraege if max_eintraege is None else max_eintraege
    ueber_filter: list[Treffer] = []
    ueber_stichwort: list[Treffer] = []
    gesehen: set[str] = set()

    for eintrag in eintraege:
        if eintrag.id in gesehen:
            continue
        passt = all(_dimension_trifft(d, satz.werte(d), eintrag, katalog)
                    for d in DIMENSIONEN)
        if passt:
            gesehen.add(eintrag.id)
            ueber_filter.append(Treffer(eintrag=eintrag, grund="filter"))
            continue
        # Additiv: was die Filter ausgeschlossen haben, kann ein eigenes
        # Stichwort trotzdem hereinholen - mit Begruendung.
        for stichwort in satz.stichwoerter:
            if stichwort.trifft(eintrag.suchtext):
                gesehen.add(eintrag.id)
                ueber_stichwort.append(Treffer(eintrag=eintrag,
                                               grund="stichwort",
                                               stichwort=stichwort.term))
                break

    def _rang(t: Treffer):
        return (-t.eintrag.gewicht, t.eintrag.datum or "", t.eintrag.titel)

    ueber_filter.sort(key=_rang)
    ueber_stichwort.sort(key=_rang)
    return (ueber_filter + ueber_stichwort)[:deckel]


# ==============================  Trefferzahl-Vorschau und ihr Index  =======
# Die Anmeldeseite ist statisch und kann kein Python aufrufen; der
# Signup-Dienst hat die Berichtsarchive nicht. Die Vorschau zaehlt deshalb im
# BROWSER gegen eine Indexdatei, die die Pipeline bei jedem Lauf mitschreibt.
#
# Der Index bildet `Wort -> Zahl der MELDUNGEN, die es enthalten` ab, nicht
# die Zahl der Vorkommen. Das ist die Zahl, nach der ein Mensch fragt ("wie
# viele Mails bekomme ich davon"), und nur so stimmen Browser und
# `vorschau()` ueberein. Ein Test haelt beide gegeneinander - sonst
# antwortet die Seite anders als der Test und beide sind fuer sich gruen
# (dieselbe Falle wie beim Archiv-Dialog in app.js).


def _bericht_dateien(reports_dir: Path, tage: int, heute: date | None = None):
    heute = heute or date.today()
    grenze = (heute - timedelta(days=tage)).isoformat()
    for pfad in sorted(Path(reports_dir).glob("*.json")):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", pfad.stem):
            continue
        if pfad.stem >= grenze:
            yield pfad


def _texte_aus_berichten(reports_dir: Path, tage: int,
                         heute: date | None = None) -> list[str]:
    """Ueberschrift + Zusammenfassung je Meldung der letzten `tage` Tage.

    Genau die Textmenge, die auch `Eintrag.suchtext` liefert - eine Vorschau,
    die auf einer anderen Textmenge zaehlt als der spaetere Versand, sagt
    eine Zahl voraus, die nie eintritt.
    """
    texte: list[str] = []
    for pfad in _bericht_dateien(reports_dir, tage, heute):
        try:
            bericht = json.loads(pfad.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for region in (bericht.get("regions") or {}).values():
            for h in region.get("highlights") or []:
                titel = h.get("headline") or h.get("title") or ""
                texte.append(f"{titel}\n{h.get('summary') or ''}")
    return texte


def vorschau(term: str, reports_dir: Path, *, tage: int = 30,
             heute: date | None = None, mode: str = "") -> int:
    """Wie viele Meldungen der letzten `tage` Tage haette dieses Stichwort
    getroffen? Die Zahl, die vor dem Absenden auf dem Formular steht."""
    stichwort = lies_stichwoerter([{"term": term, "mode": mode}])
    if not stichwort:
        return 0
    return sum(1 for text in _texte_aus_berichten(reports_dir, tage, heute)
               if stichwort[0].trifft(text))


# Rueckwaertskompatibler englischer Name - so steht er im Konzept (N2).
preview_keyword = vorschau


# Der Tokenizer des Index - und warum es NICHT `textwerkzeug.wortmenge()` ist.
#
# `wortmenge()` laesst den Bindestrich INNERHALB eines Wortes zu
# (`WORT_RE = [\w][\w-]{3,}`): "Tarif-Rabatt" ist dort EIN Wort. Das ist fuer
# den roten Faden richtig - zusammengesetzte Begriffe sind dort das
# aussagekraeftigere Signal.
#
# Der Stichwort-Matcher sieht denselben Text anders: er behandelt den
# Bindestrich als WORTGRENZE, damit "Netzausbau" in "Glasfaser-Netzausbau"
# trifft. Gemessen am 11.08.2026: fuer "tarif" zaehlte der Index 6 Meldungen,
# `vorschau()` fand 13 - die sieben Differenz waren "Tarif-Rabatt",
# "Tarif-Aktion" und Geschwister. Die Vorschau haette also die Haelfte
# unterschlagen, und der Test dagegen waere gruen geblieben, wenn er
# dieselbe Rechnung zweimal gemacht haette.
#
# `\w{4,}` liefert genau die maximalen Wortzeichen-Laeufe - und ein solcher
# Lauf IST ein Wort nach der Grenzdefinition des Matchers. Damit stimmen
# beide Rechnungen ueberein, und ein Test misst das im echten Browser.
_INDEX_WORT = re.compile(r"\w{4,}", re.UNICODE)


def _index_woerter(text: str) -> set[str]:
    return {w.lower() for w in _INDEX_WORT.findall(text or "")}


def baue_stichwort_index(reports_dir: Path, *, tage: int = 30,
                         heute: date | None = None) -> dict:
    """Der Index fuer die clientseitige Vorschau (`site/data/keyword-index.json`).

    Enthaelt nur Woerter ab vier Zeichen - dieselbe Grenze wie
    `min_stichwort_laenge`. Kuerzere kann niemand als Stichwort eintragen,
    sie muessten also gar nicht erst ausgeliefert werden.
    """
    texte = _texte_aus_berichten(reports_dir, tage, heute)
    zaehler: dict[str, int] = {}
    for text in texte:
        for wort in _index_woerter(text):     # Menge: EINE Meldung zaehlt 1
            zaehler[wort] = zaehler.get(wort, 0) + 1
    return {
        "stand": (heute or date.today()).isoformat(),
        "tage": tage,
        "meldungen": len(texte),
        # Sortiert nach Haeufigkeit: die Datei wird von Menschen gelesen,
        # wenn die Vorschau einmal etwas Unerwartetes sagt.
        "woerter": dict(sorted(zaehler.items(), key=lambda kv: (-kv[1], kv[0]))),
    }
