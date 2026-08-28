"""Die Vorsortierung: das billige Modell wirft weg, bevor das teure liest.

Das Problem, das sie loest
--------------------------
Am 27.08.2026 kostete ein Lauf 1,95 $, und rund 90 % davon war der Analyst auf
deepseek-v4-pro: 890 Ereignisse hinein, 362 behalten. Bezahlt wurde also vor
allem das WEGWERFEN - mit dem teuersten Modell der Kette, das je Aufruf ~8-9k
Token Denkspur schreibt. Der Analyst bleibt auf pro (Antonios Entscheidung vom
27.08.2026, gespart wird an den Token, nicht am Urteil); was sich sparen
laesst, ist die Menge dessen, was er ueberhaupt zu sehen bekommt.

Diese Stufe laeuft davor auf dem MECHANIK-Modell (deepseek-v4-flash, ein
Drittel des Preises) und beantwortet je Meldung genau eine Frage: offensichtlich
irrelevant - ja oder nein. Sie bewertet nicht, sie kategorisiert nicht, sie
schreibt keinen Text.

Drei Sicherungen, und jede hat ihren Grund
------------------------------------------
Eine Stufe, die Meldungen entfernt, ist die gefaehrlichste Art von Stufe: ihr
Fehler ist unsichtbar. Was hier faelschlich faellt, sieht hinterher aus wie
eine duenne Nachrichtenwoche - genau das Bild, das die degenerierten
402-Laeufe vom 15. bis 27.08.2026 abgegeben haben.

1. **CTM-DURCHLASS.** Was den Heimatmarkt oder ein Portfoliostichwort aus
   `config/ctm_fokus.yaml` nennt, umgeht die Stufe ganz. Das ist genau die
   Menge, wegen der dieses Portal existiert; sie darf gar nicht erst zur
   Abstimmung stehen.
2. **FEHLER-DURCHLASS.** Scheitert ein Aufruf - Ausnahme, totes Modell,
   unparsebare Antwort -, geht der GANZE Stapel ungefiltert weiter. Ein
   gescheiterter Aufruf darf nie wie "nichts gefunden" aussehen; dieselbe
   Lehre wie bei `PromoExtractionError` (CLAUDE.md §6).
3. **KEIN ABBRUCH DES SCANS.** Jede Meldung wird durchgelassen, geprueft oder
   per Fehler-Durchlass durchgereicht - keine faellt still heraus. Eine
   Meldung, die das Modell in seiner Antwort nicht erwaehnt, gilt als
   behalten. Das ist die Lehre aus `max_produkte` (Geraeteradar) und aus dem
   Uebersetzungsdeckel: ein Deckel, der den SCAN abbricht, ist keine
   Begrenzung, sondern eine Auswahl nach Listenposition.
4. **FRIST-DURCHLASS.** Die Stufe rechnet gegen die RESTZEIT DES JOBS, nicht
   gegen sich selbst - dieselbe Lehre wie `pipeline.geraete_budget()` und
   Lauf 31422689829. Ist die Frist erreicht, gehen die uebrigen Stapel
   ungefiltert weiter. Sie steht VOR dem Analysten, also vor der laengsten
   Stufe und weit vor dem Rendern: eine Vorsortierung, die ihre Zeit
   ueberzieht, kostet nicht ein paar Meldungen, sondern den Bericht.

Verhaeltnis zum Seen-Store
--------------------------
Was hier faellt, gilt als GELESEN und wandert normal in den Seen-Store: es
wurde bewusst verworfen, nicht verpasst. Das ist der Unterschied zum
`_ungelesen`-Mechanismus gescheiterter Analysten-Stapel - dort hat niemand
hingesehen, hier schon. Wer die beiden verwechselt, baut entweder eine
Endlosschleife (verworfene Meldungen kommen jeden Lauf wieder) oder einen
stillen Verlust.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field

from ..models import Item
from .agents import analyst_text
from .ctm import CtmFokus
from .llm import complete, extract_json

log = logging.getLogger(__name__)

# Meldungen je Aufruf. Gross, weil die Aufgabe klein ist: eine Zeile Antwort je
# Meldung. Der Denkspur-Anteil faellt je AUFRUF an - dieselbe Rechnung, die die
# Analysten-Stapel am 27.08.2026 von 15 auf 24 gehoben hat, nur ohne die
# Ausgabelast eines vollen Bewertungsobjekts.
BATCH_SIZE = 50

# Ausgabebudget. 16000 wie bei den anderen Mechanik-Stufen und NICHT knapper:
# auch flash schreibt eine Denkspur, und sie wird als Ausgabe abgerechnet. Ein
# Budget, das vor der Antwort aufgebraucht ist, kostet den ganzen Stapel und
# sieht dabei aus wie eine leere Antwort (Laeufe #83-85, #97).
MAX_TOKENS = 16000

# Wie viel Text je Meldung mitgeht. Der Analyst bekommt 2500 Zeichen, weil er
# Zahlen, Preise und Daten daraus zitiert. Hier geht es nur um die Frage "ist
# das ueberhaupt eine Meldung" - dafuer reicht der Anfang, und 50 x 400 Zeichen
# sind rund 5k Token Eingabe je Aufruf.
TEXT_ZEICHEN = 400

# So viele Aussortierte werden mit Grund festgehalten - fuer den Messauftrag
# aus dem Premortem (Strategie §3.1): nach dem ersten gesunden Lauf eine
# Stichprobe lesen und pruefen, ob eine dabei ist, die in den Bericht gehoert
# haette. Ohne diese Liste im Bericht-JSON ist die Frage nach dem Lauf nicht
# mehr zu beantworten.
STICHPROBE = 20


VORSORTIERER_SYSTEM = """\
Du bist die VORSORTIERUNG eines Wettbewerbsradars fuer einen deutschen
Netzbetreiber. Du bewertest NICHTS und fasst NICHTS zusammen - du entscheidest
nur, ob eine Meldung dem Analysten ueberhaupt vorgelegt wird.

Du bekommst eine nummerierte JSON-Liste (nr, titel, quelle, text). "text" ist
der Anfang des Artikels und kann leer sein.

VERWIRF eine Meldung NUR, wenn sie eindeutig in eine dieser vier Gruppen faellt:
- reines Boilerplate: Personalien, Sponsoring, Auszeichnungen, ESG-,
  Nachhaltigkeits- und Diversity-Prosa, Termin- und Kalenderhinweise
- Kapitalmarkt-Formalia: Hauptversammlung, Stimmrechtsmitteilung,
  Pflichtveroeffentlichung, "8-K Current report", "Monthly Return" - Meldungen
  ohne eigene Aussage
- Zulieferer- oder Agentur-PR ohne erkennbare Marktfolge: Messeauftritte,
  Whitepaper- und Studienwerbung, Lob des eigenen Produkts ohne Kunde,
  Preis oder Datum
- Ratgeber-, SEO- und Blogtexte: "die 10 besten ...", "so richten Sie ...",
  "was ist eigentlich ...", Vergleichs- und Listicle-Seiten

BEHALTEN ist der Standard, und im Zweifel wird BEHALTEN. Behalte insbesondere
alles, was einen Preis, einen Tarif, ein Geraet, einen Marktstart, eine
Uebernahme, eine regulatorische Entscheidung oder eine Netzfunktion nennt, die
ein Endkunde merkt - auch wenn der Absender klein ist oder die Meldung regional
wirkt. OB eine Meldung wichtig ist, entscheidet der Analyst nach dir, nicht du.

Antworte AUSSCHLIESSLICH mit einem JSON-Array, ein Objekt je Meldung:
[{"nr": <Nummer aus der Eingabe>, "behalten": true, "grund": "<3-5 Woerter>"}]
Jede Nummer der Eingabe kommt genau einmal vor. Kein weiterer Text.
"""


class CtmDurchlass:
    """Wer den Heimatmarkt beruehrt, wird nicht vorsortiert.

    Marken kommen aus `CtmFokus` und werden mit dessen eigenem Muster
    geprueft - eine zweite Markenliste waere eine zweite Wahrheit.

    Bei den Stichworten weicht die Rechnung bewusst um eine Kleinigkeit ab:
    `ctm.deterministische_stufe` sucht sie als reine Teilkette, was dort
    ungefaehrlich ist, weil vorher schon eine Heimatmarkt-Marke getroffen haben
    muss. Hier steht das ODER, und ohne Wortanfang wuerde "flat" jede
    "Inflation" durchlassen. Nach RECHTS bleibt es offen: die Liste enthaelt
    Wortstaemme ("vorbestell", "drossel"), die sich fortsetzen duerfen.
    """

    def __init__(self, fokus: CtmFokus) -> None:
        self.fokus = fokus
        worte = [re.escape(w) for w in (fokus.direkte_stichworte or []) if w]
        worte.sort(key=len, reverse=True)
        self._stichworte = (re.compile(r"(?<!\w)(" + "|".join(worte) + ")", re.I)
                            if worte else None)

    def trifft(self, item: Item) -> bool:
        text = " ".join(str(getattr(item, f, "") or "")
                        for f in ("operator", "title", "summary"))
        if self.fokus.trifft_heimatmarkt(text):
            return True
        return bool(self._stichworte and self._stichworte.search(text))


@dataclass
class Bilanz:
    """Was die Stufe getan hat - fuer Protokoll und Bericht-JSON.

    Ohne Zahl im Protokoll laesst sich nach einem Lauf nicht sagen, ob die
    Stufe gegriffen hat oder nur nichts gefunden wurde. Dieselbe Ueberlegung
    wie bei `ctm.veredle`.
    """

    angeboten: int = 0
    durchlass: int = 0       # per CTM-Treffer an der Stufe vorbei
    geprueft: int = 0        # dem Modell wirklich vorgelegt
    verworfen: int = 0
    batches: int = 0
    fehler_batches: int = 0  # Stapel, die ungefiltert durchgereicht wurden
    # Stapel, die wegen der Frist gar nicht mehr gefragt wurden. Eigener
    # Zaehler, nicht zu `fehler_batches` addiert: "der Anbieter antwortete
    # nicht" und "uns lief die Zeit weg" sind zwei verschiedene Befunde, und
    # nur der erste ist ein Grund, an der Quelle nachzusehen.
    frist_batches: int = 0
    stichprobe: list[dict] = field(default_factory=list)

    @property
    def behalten(self) -> int:
        return self.angeboten - self.verworfen

    def dazu(self, other: "Bilanz") -> None:
        self.angeboten += other.angeboten
        self.durchlass += other.durchlass
        self.geprueft += other.geprueft
        self.verworfen += other.verworfen
        self.batches += other.batches
        self.fehler_batches += other.fehler_batches
        self.frist_batches += other.frist_batches
        self.stichprobe = (self.stichprobe + other.stichprobe)[:STICHPROBE]

    def als_dict(self) -> dict:
        return {
            "angeboten": self.angeboten,
            "durchlass": self.durchlass,
            "geprueft": self.geprueft,
            "verworfen": self.verworfen,
            "behalten": self.behalten,
            "batches": self.batches,
            "fehler_batches": self.fehler_batches,
            "frist_batches": self.frist_batches,
            "stichprobe": self.stichprobe,
        }


def ist_eingeschaltet(settings: dict) -> bool:
    """Der eine Schalter. Vorgabe an - eine Zeile schaltet die Stufe ab, falls
    die Stichprobe nach dem ersten Lauf Verluste zeigt."""
    return bool((settings or {}).get("vorsortierung_enabled", True))


def _nutzlast(nummeriert: list[tuple[int, Item]]) -> str:
    return json.dumps(
        [{"nr": nr, "titel": item.title, "quelle": item.source_name,
          "text": analyst_text(item)[:TEXT_ZEICHEN]}
         for nr, item in nummeriert],
        ensure_ascii=False)


# Was als "verwirf das" gilt. Alles andere - auch eine fehlende, leere oder
# unverstaendliche Angabe - behaelt die Meldung. Die Richtung ist Absicht: ein
# Modell, das sich unklar ausdrueckt, darf keine Meldung kosten.
_VERWURF_WORTE = {"false", "nein", "no", "0", "verwerfen", "drop", "raus"}


def _ist_verwurf(wert) -> bool:
    if isinstance(wert, bool):
        return wert is False
    if isinstance(wert, (int, float)):
        return wert == 0
    if isinstance(wert, str):
        return wert.strip().lower() in _VERWURF_WORTE
    return False


def _zeilen(parsed) -> list[dict]:
    """Die Antwortzeilen - als Array oder in einen Umschlag gepackt.

    Ein Modell, das statt `[...]` ein `{"meldungen": [...]}` liefert, hat die
    Aufgabe richtig gemacht und nur das Format verfehlt; das darf keinen
    ganzen Stapel kosten.
    """
    if isinstance(parsed, list):
        return [z for z in parsed if isinstance(z, dict)]
    if isinstance(parsed, dict):
        for wert in parsed.values():
            if isinstance(wert, list):
                return [z for z in wert if isinstance(z, dict)]
    return []


def _ein_stapel(nummeriert: list[tuple[int, Item]], model: str
                ) -> tuple[dict[int, str], bool]:
    """Ein Aufruf. Liefert die Verwuerfe (Nummer -> Grund) und ob er scheiterte.

    Beide Rueckgaben werden gebraucht: ein leeres Ergebnis heisst "nichts
    auszusortieren", ein gescheiterter Aufruf heisst "wir wissen es nicht" -
    und das darf nie dasselbe sein.
    """
    user = (f"{len(nummeriert)} Meldungen:\n"
            + _nutzlast(nummeriert))
    try:
        parsed = extract_json(complete(VORSORTIERER_SYSTEM, user, model=model,
                                       max_tokens=MAX_TOKENS))
    except Exception as exc:  # noqa: BLE001 - Fehler-Durchlass, siehe Modulkopf
        log.warning("Vorsortierung: Stapel mit %d Meldungen gescheitert (%s) - "
                    "alle gehen ungefiltert zum Analysten",
                    len(nummeriert), str(exc)[:160])
        return {}, True

    bekannt = {nr for nr, _ in nummeriert}
    verwuerfe: dict[int, str] = {}
    for zeile in _zeilen(parsed):
        try:
            nr = int(zeile.get("nr"))
        except (TypeError, ValueError):
            continue
        if nr in bekannt and _ist_verwurf(zeile.get("behalten")):
            verwuerfe[nr] = " ".join(str(zeile.get("grund") or "").split())[:80]
    return verwuerfe, False


def sortiere_vor(items: list[Item], *, model: str, fokus: CtmFokus,
                 use_llm: bool = True, deadline: float | None = None
                 ) -> tuple[list[Item], Bilanz]:
    """Die offensichtlich Irrelevanten aussortieren - in der Eingabereihenfolge.

    Die Reihenfolge bleibt erhalten, weil sie traegt: `_interleave_by_source`
    hat sie gesetzt, und `max_items` schneidet spaeter nach ihr.

    `deadline` ist ein `time.monotonic()`-Zeitpunkt. Ist er erreicht, gehen
    die uebrigen Stapel UNGEFILTERT weiter (Frist-Durchlass, siehe Modulkopf)
    - geschnitten wird nie.
    """
    bilanz = Bilanz(angeboten=len(items))
    if not items or not use_llm:
        return list(items), bilanz

    durchlass = CtmDurchlass(fokus)
    zu_pruefen: list[tuple[int, Item]] = []
    for nr, item in enumerate(items):
        if durchlass.trifft(item):
            bilanz.durchlass += 1
        else:
            zu_pruefen.append((nr, item))
    bilanz.geprueft = len(zu_pruefen)

    verwuerfe: dict[int, str] = {}
    for start in range(0, len(zu_pruefen), BATCH_SIZE):
        stapel = zu_pruefen[start:start + BATCH_SIZE]
        bilanz.batches += 1
        if deadline is not None and time.monotonic() >= deadline:
            bilanz.frist_batches += 1
            continue
        teil, gescheitert = _ein_stapel(stapel, model)
        if gescheitert:
            bilanz.fehler_batches += 1
            continue
        verwuerfe.update(teil)

    bilanz.verworfen = len(verwuerfe)
    bilanz.stichprobe = [
        {"titel": items[nr].title[:120], "quelle": items[nr].source_name,
         "grund": grund}
        for nr, grund in sorted(verwuerfe.items())][:STICHPROBE]
    return [item for nr, item in enumerate(items) if nr not in verwuerfe], bilanz


def sortiere_regionen_vor(items_by_region: dict[str, list[Item]], *,
                          model: str, fokus: CtmFokus, workers: int = 1,
                          deadline: float | None = None,
                          ) -> tuple[dict[str, list[Item]], Bilanz]:
    """Die Stufe ueber alle Bereiche - je Region/Themenfeld ein eigener Lauf.

    Bereiche laufen nebenlaeufig, ihre Stapel nacheinander: dieselbe Aufteilung
    wie bei den Analysten, und sie haelt die Zahl gleichzeitiger Aufrufe an
    `llm_max_workers` fest.

    Ein Bereich, aus dem nichts uebrig bleibt, faellt aus der Abbildung. Das
    ist wichtiger, als es aussieht: eine leere Region wuerde sonst als
    analysiert gelten und stuende mit einer leeren Ueberschrift im Bericht.
    """
    gesamt = Bilanz()
    ergebnis: dict[str, list[Item]] = {}

    def _einer(eintrag: tuple[str, list[Item]]) -> tuple[str, list[Item], Bilanz]:
        region_key, region_items = eintrag
        behalten, bilanz = sortiere_vor(region_items, model=model, fokus=fokus,
                                        deadline=deadline)
        return region_key, behalten, bilanz

    eintraege = list(items_by_region.items())
    if workers > 1 and len(eintraege) > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as pool:
            teile = list(pool.map(_einer, eintraege))
    else:
        teile = [_einer(e) for e in eintraege]

    for region_key, behalten, bilanz in teile:
        gesamt.dazu(bilanz)
        if behalten:
            ergebnis[region_key] = behalten

    log.info("Vorsortierung: %d von %d verworfen (CTM-Durchlass: %d, "
             "Fehler-Durchlass: %d von %d Stapeln, Frist-Durchlass: %d)",
             gesamt.verworfen, gesamt.angeboten, gesamt.durchlass,
             gesamt.fehler_batches, gesamt.batches, gesamt.frist_batches)
    for eintrag in gesamt.stichprobe:
        log.info("Vorsortierung verwarf: %s (%s) - %s",
                 eintrag["titel"], eintrag["quelle"], eintrag["grund"])
    return ergebnis, gesamt
