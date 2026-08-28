"""Temporaere Themenseiten: erkennen, wenn viele Meldungen dasselbe meinen.

Antonio am 08.08.2026: "Wenn zu einem Thema/Event viele Meldungen auftreten
(Beispiel: Launch des Samsung Z Fold), will ich eine temporaere
Highlight-Seite zu diesem Thema ... Wenn das Thema nicht mehr relevant ist,
soll die Seite wieder verschwinden."

Das Modul ist bewusst ZWEITEILIG, und die Trennlinie ist die zwischen
Mechanik und Urteil:

  KANDIDATENSUCHE (deterministisch, kein LLM)
      Findet Gruppen von Meldungen, die ueber SELTENE gemeinsame Woerter
      zusammenhaengen - dieselbe 1/Haeufigkeit-Rechnung wie der rote Faden
      der Titelseite (textwerkzeug.py). Sie sagt, WO etwas zusammenhaengt,
      nicht WAS es ist: "Deutsche Telekom" bindet sieben Meldungen zusammen
      und ist trotzdem kein Ereignis, sondern eine Firma.

  THEMEN-AGENT (LLM, eigener Prompt)
      Entscheidet je Kandidat, ob das ein Ereignis ist, das eine eigene
      Seite traegt, gibt ihm einen deutschen Titel, einen Leitsatz fuer
      Laien und die Suchwoerter, mit denen die folgenden Laeufe weitere
      Meldungen zuordnen. Faellt er aus, entstehen KEINE neuen Themen - die
      bestehenden werden trotzdem weiter gepflegt, denn dafuer braucht es
      kein Modell.

Die Alterung ist der Teil, der die Seiten wieder verschwinden laesst: ein
Thema ohne nennenswerten Zuwachs zaehlt einen Lauf hoch, nach vier solchen
Laeufen (rund zwei Wochen bei zwei Laeufen je Woche) gilt es als beendet.
Beendete Themen bleiben im Speicher - als Gedaechtnis, damit derselbe
Samsung-Launch nicht in der uebernaechsten Woche noch einmal als "neu"
entdeckt wird.
"""
from __future__ import annotations

import itertools
import json
import logging
import re
from datetime import date, timedelta
from pathlib import Path

from ..textwerkzeug import gewicht, haeufigkeiten, slug, wortmenge
from .llm import complete, extract_json

log = logging.getLogger(__name__)

STORE_NAME = "highlight_topics.json"

# --- Kandidatensuche ------------------------------------------------------
# Was eine Gruppe sein muss, um ueberhaupt gefragt zu werden. Der Schutz vor
# der einzelnen Redaktion, die nachlegt, liegt bei MIND_QUELLEN - nicht bei
# der Gruppengroesse. MIND_MELDUNGEN stand bis zum 17.08.2026 auf 5, und mit
# dieser Schwelle hat die Mechanik seit ihrem Bau am 07.08. KEIN einziges
# Thema angelegt: der Google-Pixel-11-Launch brachte am 14.08. vier
# Highlights aus vier Quellen (darunter die Prioritaet-5-Meldung der Woche)
# und fiel an 4 < 5. Ein Geraetelaunch erreicht in EINEM Lauf fast nie
# fuenf bewertete Meldungen - er verteilt sich ueber Carrier-Meldungen an
# verschiedenen Tagen. Deshalb 4, und deshalb rechnet die Kandidatensuche
# seitdem ueber das Berichtsarchiv mit (ARCHIV_TAGE unten).
MIND_MELDUNGEN = 4
MIND_QUELLEN = 3
# Wie viele Meldungen einer Gruppe aus dem AKTUELLEN Lauf stammen muessen.
# Das Archiv (unten) verstaerkt nur, was gerade Momentum hat - es soll kein
# Thema aus einer zwei Wochen alten Welle entstehen, zu der diese Woche
# nichts mehr kommt. Zwei, nicht eins: dieselbe Schwelle wie MIND_ZUWACHS,
# denn ein Thema, das nicht einmal den Zuwachs eines BESTEHENDEN Themas
# erreichte, wuerde als frisches sofort zu altern beginnen. Ohne diese
# Bedingung standen am Korpus vom 15.08.2026 gemessen 40 Gruppen an, die
# meisten ohne eine einzige Meldung der laufenden Woche.
MIND_AKTUELL = 2
MIND_GEMEINSAM = 2
# Ein Wort taugt nur als Bindeglied, wenn es in mindestens drei Meldungen
# steht - zwei sind ein Zufall.
MIND_WORTHAEUFIGKEIT = 3
MAX_KANDIDATEN = 6
# Zwei Wortpaare beschreiben oft dieselbe Gruppe ("samsung+galaxy" und
# "galaxy+fold8"). Gerechnet wird gegen die KLEINERE Menge - gegen die
# groessere gerechnet saehe eine Gruppe, die eine andere vollstaendig
# enthaelt, wie eine eigene aus (dieselbe Lehre wie beim Abnahme-Check
# neuer Quellen, CLAUDE.md §6).
UEBERLAPPUNG = 0.6

# --- Spezifitaet ------------------------------------------------------------
# Woerter, die eine wiederkehrende KATEGORIE binden (Quartalsberichte), nicht
# ein EREIGNIS. Gemessen am Korpus vom 27.08.2026: die Gruppe
# worte=['quartal','zweiten', ...] (n=32) und eine reine Namensgruppe
# worte=['deutsche','telekom'] (n=26, kein Wort davon benennt einen Vorgang)
# standen vor der Apple-Keynote-Gruppe worte=['apple','iphone','september',
# 'ultra'] (n=10, 5 Quellen, alle Schwellen erfuellt) - MAX_KANDIDATEN schnitt
# nach roher Groesse, die Apple-Gruppe lag auf Rang 17 von 116 und wurde nie
# vorgelegt. Bewusst OHNE Firmenliste: eine Gruppe mit hoechstens zwei
# Bindewoertern und ganz ohne Ereignis-/Datumssprache ist unspezifisch, egal
# ob die zwei Woerter zufaellig eine Firma buchstabieren oder etwas anderes -
# das faengt _spezifitaet() unten pauschal ab.
RAUSCH_WOERTER = frozenset({
    "quartal", "quartals", "quartalszahlen", "halbjahr", "geschaeftsjahr",
    "umsatz", "umsaetze", "ergebnis", "ergebnisse", "gewinn", "verlust",
    "bilanz", "revenue", "milliarden", "millionen", "prozent",
    "ersten", "zweiten", "dritten", "vierten",
})
# Sprache, die ein Ereignis (statt einer Kategorie) benennt - dieselbe Liste
# traegt den Spezifitaets-Bonus hier UND den Antizipations-Pfad unten
# (_ankuendigungssprache). Monate zaehlen mit: eine Datumsangabe ist so gut
# wie ein Eigenname ein Beleg fuer einen konkreten Vorgang statt einer
# Dauerkategorie.
_MONATE = ("januar", "februar", "märz", "april", "mai", "juni", "juli",
          "august", "september", "oktober", "november", "dezember")
_ANKUENDIGUNG_WOERTER = (
    "keynote", "event", "launch", "vorstellung", "vorgestellt",
    "praesentation", "praesentiert", "ankuendigung", "ankuendigt",
    "erwartet", "vorbestellung", "vorbestellbar", "marktstart", "erscheint",
    "unveil", "unveils", "unveiled", "unveiling",
)
EREIGNIS_WOERTER = frozenset(_MONATE) | frozenset(_ANKUENDIGUNG_WOERTER)

# Ein Bindewort mit einer Ziffer darin ist praktisch immer eine Modell- oder
# Generationsbezeichnung ("pixel-11-serie", "s25", "5g") - also ein
# Eigenname. Traegt den Produktwort-Anteil in `_spezifitaet`.
_PRODUKTWORT = re.compile(r"\d")

# --- Ankuendigungssprache ---------------------------------------------------
# Nur das Vokabular, das nach VORNE zeigt. `vorgestellt`, `praesentiert`,
# `unveils` und `unveiled` stehen bewusst NICHT hier: sie berichten ueber
# etwas, das gerade stattgefunden hat, und das ist das Gegenteil dessen, was
# der Antizipations-Pfad sucht. Am Korpus vom 27.08.2026 gemessen kam
# `vorgestellt` fuer 31 der Treffer auf - mehr als jedes andere Wort und mehr
# als alle Datumsangaben zusammen. Fuer den Spezifitaets-Bonus zaehlen sie
# weiter mit (EREIGNIS_WOERTER oben): dort geht es darum, ob ein Wort einen
# VORGANG benennt, nicht ob er noch bevorsteht.
_VORAUS_WOERTER = tuple(w for w in _ANKUENDIGUNG_WOERTER
                        if w not in {"vorgestellt", "praesentiert",
                                     "unveils", "unveiled"})
_ANKUENDIGUNG_WORTMUSTER = re.compile(
    r"(?<!\w)(?:" + "|".join(_VORAUS_WOERTER) + r")(?!\w)", re.IGNORECASE)

# Eine Monatsangabe MIT Tageszahl, davor oder danach ("9. September" /
# "September 9"). Ohne Tageszahl waere es keine Terminangabe, sondern eine
# Zeitspanne ("im September"), und ein blosses "September 2026" faellt an
# `\d{1,2}\b` ohnehin heraus. Die Gruppen tragen Tag und Monat heraus, denn
# ob der Termin BEVORSTEHT, entscheidet erst `_kuenftige_datumstreffer`.
_DATUM_MUSTER = re.compile(
    r"(?<!\w)(?P<m1>" + "|".join(_MONATE) + r")(?!\w)\s*(?P<t1>\d{1,2})\b"
    r"|\b(?P<t2>\d{1,2})\.\s*(?P<m2>" + "|".join(_MONATE) + r")(?!\w)",
    re.IGNORECASE)

# --- Antizipation -----------------------------------------------------------
# Ein bevorstehendes Ereignis hat VOR dem Termin naturgemaess ein duennes
# Echo - das Gros der Berichterstattung kommt erst MIT dem Ereignis. Deshalb
# eine niedrigere Schwelle als die normale Kandidatensuche; die zusaetzliche
# Bedingung (Ankuendigungssprache, siehe unten) haelt sie trotzdem eng - ohne
# sie waere jede Drei-Meldungen-Gruppe ein Kandidat.
MIND_MELDUNGEN_ANTIZIPATION = 3
MIND_QUELLEN_ANTIZIPATION = 2
# Ein einzelner beilaeufiger Datumstreffer ("... seit September im Handel")
# ist kein bevorstehendes Ereignis - erst ein Muster ueber mehrere Meldungen.
MIND_ANKUENDIGUNGSTREFFER = 2
# Wie viele Antizipations-Gruppen dem Agenten HOECHSTENS zusaetzlich
# vorgelegt werden.
#
# Der Pfad war bis zum 27.08.2026 ungedeckelt, und das ist keine Kleinigkeit:
# am echten Korpus dieses Tages (1023 Meldungen aus vier Ausgaben) lieferte er
# 28 Gruppen, die Nutzlast an den Agenten wuchs auf ueber 64 000 Zeichen, und
# seine Antwort haette ein Objekt je Kandidat tragen muessen. Mit einem
# Denkspur-Modell im Ruecken (~8-9k Token allein fuers Nachdenken) reisst das
# `_TOKENS`, die Antwort bricht mitten im JSON ab, `extract_json` wirft - und
# das Ergebnis ist NULL Themen, also genau das Gegenteil dessen, wofuer der
# Pfad gebaut wurde. Ein Deckel, der die schwaechsten abschneidet, ist hier
# das Gegenteil des `max_produkte`-Fehlers: gescannt und bewertet wird
# vollstaendig, geschnitten wird erst nach der Rangfolge.
MAX_ANTIZIPATION = 3
# Wie weit ein genannter Termin in der Zukunft liegen darf, um noch als
# bevorstehendes Ereignis zu zaehlen. Ein halbes Jahr - danach ist es eine
# Roadmap-Nennung, kein Termin, auf den eine Themenseite wartet.
ANKUENDIGUNG_HORIZONT_TAGE = 180

# --- Pflege ---------------------------------------------------------------
# Wie viele Suchwoerter eine neue Meldung treffen muss, um einem Thema
# zugeordnet zu werden. Eins reicht nicht: "Samsung" allein zieht jede
# Geraetemeldung des Herstellers in den Launch der Z-Fold-Reihe.
MIND_TREFFER = 2
# Ab wie vielen neuen Meldungen ein Lauf als Zuwachs zaehlt.
MIND_ZUWACHS = 2
MAX_RUNS_OHNE_ZUWACHS = 4
# Ein Thema mit `event_datum` altert erst ab diesem Abstand ZUM Termin - ein
# bevorstehendes Ereignis hat vorher naturgemaess wenig Zuwachs, und die
# normale Alterung wuerde es genau dann beenden, wenn es am wichtigsten wird.
EREIGNIS_SCHUTZ_TAGE = 7
# Obergrenze je Thema, damit ein monatelang laufendes Thema die Speicherdatei
# nicht sprengt. Die dringendsten bleiben.
MAX_ITEMS_JE_THEMA = 80

# --- Archivfenster --------------------------------------------------------
# Die Kandidatensuche sieht nicht nur den aktuellen Lauf, sondern auch die
# Highlights der letzten Ausgaben aus data/reports/. Der Grund ist gemessen,
# nicht vermutet: der Pixel-11-Launch stand am 06.08. mit EINER und am
# 14.08. mit VIER Meldungen im Bericht - in keinem einzelnen Lauf genug fuer
# eine Gruppe, ueber beide zusammen locker. Ein Ereignis, das sich ueber
# Laeufe verteilt, ist der Normalfall, nicht die Ausnahme. 14 Tage decken
# bei zwei Laeufen je Woche vier Ausgaben ab - derselbe Horizont wie
# MAX_RUNS_OHNE_ZUWACHS.
ARCHIV_TAGE = 14

_TOKENS = 16000


# ---------------------------------------------------------------- Speicher
def store_pfad(state_dir: Path) -> Path:
    return Path(state_dir) / STORE_NAME


def lade_store(state_dir: Path) -> dict:
    """Der Themenspeicher. Fehlt oder bricht er, faengt der Lauf bei null an -
    ein unlesbarer Speicher darf nie den Lauf kippen."""
    pfad = store_pfad(state_dir)
    if not pfad.exists():
        return {"updated": "", "topics": []}
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.warning("%s unlesbar - beginne mit leerem Themenspeicher", pfad)
        return {"updated": "", "topics": []}
    if not isinstance(daten, dict) or not isinstance(daten.get("topics"), list):
        return {"updated": "", "topics": []}
    return daten


def speichere_store(state_dir: Path, store: dict) -> None:
    pfad = store_pfad(state_dir)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(store, ensure_ascii=False, indent=1),
                    encoding="utf-8")


def aktive_themen(store: dict) -> list[dict]:
    """Die Themen, die eine Seite bekommen - neueste Aktivitaet zuerst."""
    aktiv = [t for t in (store.get("topics") or [])
             if t.get("status") == "aktiv" and t.get("items")]
    return sorted(aktiv, key=lambda t: (t.get("last_active") or "",
                                        len(t.get("items") or [])),
                  reverse=True)


def lade_themen(state_dir: Path) -> list[dict]:
    """Die aktiven Themen zum Rendern. Einziger Einstieg fuer report/."""
    return aktive_themen(lade_store(state_dir))


# ----------------------------------------------------------- Archivzugriff
def _archiv_highlights(reports_dir: Path, heute: str,
                       bekannt: set[str]) -> list[dict]:
    """Highlights der letzten Ausgaben, per URL entdoppelt gegen `bekannt`.

    Jede Meldung traegt ihr Ausgabedatum als `_woche` mit - im Themenspeicher
    soll die Woche stehen, in der sie BERICHTET wurde, nicht die, in der das
    Thema entstand. Ein unlesbares Berichts-JSON wird uebersprungen, nie
    geworfen: das Archiv ist Zugabe, nicht Voraussetzung.
    """
    try:
        grenze = (date.fromisoformat(heute) - timedelta(days=ARCHIV_TAGE)).isoformat()
    except ValueError:
        return []
    out: list[dict] = []
    urls = set(bekannt)
    for pfad in sorted(Path(reports_dir).glob("*.json"), reverse=True):
        datum = pfad.stem
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", datum):
            continue
        if datum > heute or datum < grenze:
            continue
        try:
            daten = json.loads(pfad.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        regionen = daten.get("regions") or {}
        bereiche = regionen.values() if isinstance(regionen, dict) else regionen
        for bereich in bereiche:
            if not isinstance(bereich, dict):
                continue
            for h in bereich.get("highlights") or []:
                url = (h or {}).get("url") or ""
                if not url or url in urls:
                    continue
                urls.add(url)
                out.append(dict(h, _woche=datum))
    return out


# -------------------------------------------------------- Kandidatensuche
def _text(h: dict) -> str:
    return (f"{h.get('headline') or ''} {h.get('operator') or ''} "
            f"{h.get('title') or ''} {h.get('summary') or ''}")


def _rang(h: dict) -> tuple:
    return (int(h.get("relevance") or 0), h.get("date") or "")


def _seltenheitsdeckel(n: int, ausgaben: int = 1) -> int:
    """Ab welcher Haeufigkeit ein Wort nichts mehr bindet.

    Ein Wort, das ein Fuenftel der AUSGABE durchzieht ("mobile", "network",
    "2026"), verbindet nichts - es beschreibt die Branche. Die Untergrenze
    ist doppelt so hoch wie die Mindestgruppe und darf nicht kleiner sein:
    ein Wort, das vier Meldungen bindet, kommt zwangslaeufig viermal vor.
    Mit einem Deckel unterhalb von MIND_MELDUNGEN schloesse die Suche genau
    die Woerter aus, die sie sucht, und faende in einer kleinen Ausgabe
    grundsaetzlich nichts.

    Seit die Kandidatensuche das Berichtsarchiv mitliest, muss der Deckel
    JE AUSGABE rechnen, nicht ueber den zusammengelegten Korpus: an 610
    Meldungen aus vier Ausgaben gemessen (15.08.2026) liesse n // 5 = 122
    sogar "eine" (119x), "2026" (87x) und "ueber" (76x) als Bindewoerter
    durch, und die groessten sechs "Gruppen" waren 57 Meldungen Fuellwort-
    Rauschen, waehrend die echte Pixel-11-Gruppe hinter MAX_KANDIDATEN
    verschwand.

    Am Bericht vom 07.08.2026 (138 Meldungen) gemessen ist der genaue Wert
    unkritisch: zwischen 13 und 34 aendern sich die gefundenen Gruppen von
    vier auf sechs, und keine davon wird groesser als sieben Meldungen. Die
    Arbeit macht die Paarbedingung, nicht der Deckel.
    """
    je_ausgabe = n // max(1, ausgaben)
    return max(2 * MIND_MELDUNGEN, je_ausgabe // 5)


def _gruppen(kandidaten_items: list[dict], *, mind_meldungen: int,
            mind_quellen: int) -> tuple[list[dict], list[list[str]], dict[str, int]]:
    """Wortpaar-Gruppen roh, ohne Aktualitaets- oder Rangfilter jenseits der
    uebergebenen Schwellen - die gemeinsame Mechanik von finde_kandidaten()
    und finde_antizipation(). Nur Gruppengroesse und Quellenzahl unterscheiden
    die beiden Pfade, deshalb Parameter statt Modulkonstanten hier.

    Gesucht wird ueber WORTPAARE, nicht ueber eine Verbindungskette: zwei
    Meldungen gelten als verwandt, wenn sie zwei bestimmte seltene Woerter
    TEILEN, und die Gruppe ist genau die Menge der Meldungen mit beiden
    Woertern. Eine Kette ("A und B teilen zwei Woerter, B und C zwei andere")
    ergibt am Bericht vom 07.08.2026 gemessen EINE Gruppe aus 129 der 138
    Meldungen - jede Ausgabe haengt ueber irgendein Wort mit jeder anderen
    zusammen.
    """
    if len(kandidaten_items) < mind_meldungen:
        return [], [], {}

    mengen = [wortmenge(_text(h)) for h in kandidaten_items]
    haeufigkeit = haeufigkeiten(mengen)
    ausgaben = len({h.get("_woche") or "" for h in kandidaten_items})
    deckel = _seltenheitsdeckel(len(kandidaten_items), ausgaben)
    selten = [sorted(w for w in m
                     if MIND_WORTHAEUFIGKEIT <= haeufigkeit[w] <= deckel)
              for m in mengen]

    paare: dict[tuple[str, ...], list[int]] = {}
    for i, woerter in enumerate(selten):
        for kombination in itertools.combinations(woerter, MIND_GEMEINSAM):
            paare.setdefault(kombination, []).append(i)

    roh: list[tuple[set[int], set[str]]] = []
    for kombination, idx in paare.items():
        if len(idx) < mind_meldungen:
            continue
        quellen = {(kandidaten_items[i].get("source") or "").strip() for i in idx}
        if len(quellen - {""}) < mind_quellen:
            continue
        roh.append((set(idx), set(kombination)))
    # Groesste zuerst: die aufnehmende Gruppe soll die umfassendere sein.
    roh.sort(key=lambda g: (-len(g[0]), sorted(g[1])))

    gruppen: list[dict] = []
    for idx, worte in roh:
        for g in gruppen:
            if len(g["idx"] & idx) / min(len(g["idx"]), len(idx)) >= UEBERLAPPUNG:
                g["idx"] |= idx
                g["worte"] |= worte
                break
        else:
            gruppen.append({"idx": set(idx), "worte": set(worte)})
    return gruppen, selten, haeufigkeit


def _kandidat_aus_gruppe(kandidaten_items: list[dict], idx: set[int],
                         worte: set[str], selten: list[list[str]],
                         haeufigkeit: dict[str, int], *, mind_meldungen: int,
                         mind_quellen: int) -> dict | None:
    """Eine Wortpaar-Gruppe zu Ende geprueft (Groesse, Quellen, Aktualitaet)
    und in die Kandidatenform gebracht - oder None, wenn sie an einer der
    Schwellen scheitert. `worte` traegt nur die Gewichtsrechnung; die
    tragenden Woerter im Ergebnis (`worte` im zurueckgegebenen Dict) sind das,
    was mindestens ein Drittel der Meldungen teilt - der Vorschlag an den
    Agenten, nicht die spaeteren Suchwoerter, die schreibt er selbst.
    """
    items = sorted((kandidaten_items[i] for i in idx), key=_rang, reverse=True)
    quellen = {(h.get("source") or "").strip() for h in items} - {""}
    if len(items) < mind_meldungen or len(quellen) < mind_quellen:
        return None
    # Meldungen ohne _woche sind die des aktuellen Laufs - Archiv-Items tragen
    # ihr Ausgabedatum (siehe _archiv_highlights). MIND_AKTUELL gilt fuer
    # BEIDE Pfade unveraendert - das Archiv verstaerkt nur, es erzeugt nichts.
    aktuell = sum(1 for h in items if not h.get("_woche"))
    if aktuell < MIND_AKTUELL:
        return None
    zaehler = haeufigkeiten(selten[i] for i in idx)
    schwelle = max(2, len(idx) // 3)
    tragend = sorted((w for w, n in zaehler.items() if n >= schwelle),
                     key=lambda w: (-zaehler[w], haeufigkeit[w], w))[:8]
    return {"items": items, "worte": tragend, "quellen": len(quellen),
            "gewicht": gewicht(worte, haeufigkeit),
            "spezifitaet": _spezifitaet(tragend)}


def _spezifitaet(worte) -> float:
    """Wie sehr die Bindewoerter einer Gruppe ein EREIGNIS statt einer
    wiederkehrenden KATEGORIE oder eines blossen NAMENS benennen.

    Kein Urteil - die Zahl steuert nur die Reihenfolge vor dem
    MAX_KANDIDATEN-Schnitt, das eigentliche "ist das ein Ereignis?" bleibt
    beim Agenten. Eine Gruppe, deren Bindewoerter VOLLSTAENDIG aus
    Finanzrauschen bestehen, bindet keinen Vorgang (0.0). Eine Gruppe mit
    hoechstens zwei Bindewoertern und OHNE jede Ereignis-/Datumssprache ist
    ebenfalls unspezifisch (0.1) - ob die zwei Woerter zufaellig eine Firma
    buchstabieren ("deutsche"+"telekom") oder etwas anderes, spielt dabei
    keine Rolle: eine Firmenliste braucht es dafuer nicht (siehe RAUSCH_
    WOERTER oben).

    **Ein ANTEIL, keine Summe.** Bis zum 27.08.2026 wurde `eigen + 2 *
    ereignis` unbeschraenkt aufaddiert, und damit gewann schlicht, wer mehr
    Bindewoerter hatte: am Korpus vom 27.08. trugen fuenf der sechs
    Top-Kandidaten den Wert 10,0 - darunter Gruppen, deren tragende Woerter
    "keine", "text", "your" und "weiteren" lauten. `_kandidat_aus_gruppe`
    liefert bis zu acht Woerter, eine praezise Gruppe kommt oft mit vier aus
    ("apple", "iphone", "september", "ultra"), und die verlor gegen das
    Rauschen. Gerechnet wird deshalb je Bindewort.

    Der Produktwort-Anteil zaehlt mit: ein Bindewort mit einer Ziffer darin
    ("pixel-11-serie", "s25", "5g") ist praktisch immer eine Modell- oder
    Generationsbezeichnung, also ein Eigenname - und Eigennamen benennen
    Vorgaenge, waehrend Allerweltswoerter Kategorien benennen. Grossschreibung
    steht hier nicht zur Verfuegung: `wortmenge` hat sie laengst entfernt.
    """
    woerter = list(worte or [])
    if not woerter:
        return 0.0
    rauschig = sum(1 for w in woerter if w in RAUSCH_WOERTER)
    if rauschig == len(woerter):
        return 0.0
    ereignis = sum(1 for w in woerter if w in EREIGNIS_WOERTER)
    if len(woerter) <= 2 and ereignis == 0:
        return 0.1
    eigen = len(woerter) - rauschig
    produkt = sum(1 for w in woerter if _PRODUKTWORT.search(w))
    return (eigen + 2 * ereignis + produkt) / len(woerter)


def finde_kandidaten(highlights: list[dict]) -> list[dict]:
    """Gruppen von Meldungen, die dasselbe Ereignis beschreiben koennten.

    Zurueck kommt je Gruppe: die Meldungen (dringendste zuerst), die
    tragenden Woerter und die Zahl der beteiligten Quellen. Ob das ein
    Ereignis ist, entscheidet der Agent - hier steht nur, dass es
    zusammenhaengt. Vor dem MAX_KANDIDATEN-Schnitt fuehrt SPEZIFITAET, nicht
    rohe Gruppengroesse (siehe _spezifitaet) - sonst verdraengen grosse
    Finanz- oder Namensgruppen kleinere, aber eindeutige Ereignisgruppen.
    """
    kandidaten_items = [h for h in (highlights or []) if h.get("url")]
    gruppen, selten, haeufigkeit = _gruppen(
        kandidaten_items, mind_meldungen=MIND_MELDUNGEN, mind_quellen=MIND_QUELLEN)

    out: list[dict] = []
    for g in gruppen:
        kandidat = _kandidat_aus_gruppe(
            kandidaten_items, g["idx"], g["worte"], selten, haeufigkeit,
            mind_meldungen=MIND_MELDUNGEN, mind_quellen=MIND_QUELLEN)
        if kandidat is not None:
            out.append(kandidat)
    out.sort(key=lambda g: (-g["spezifitaet"], -len(g["items"]), -g["gewicht"]))
    return out[:MAX_KANDIDATEN]


def _kuenftiger_termin(text: str, heute: date | None) -> bool:
    """Ob im Text ein Tag-und-Monat-Termin steht, der noch BEVORSTEHT.

    Ohne `heute` zaehlt jede Tag-und-Monat-Angabe - dann fehlt schlicht der
    Bezugspunkt, und Raten waere schlechter als das grobe Mass.

    Mit `heute` wird gerechnet, und das aendert viel: am Korpus vom
    27.08.2026 lagen von 40 Datumstreffern 30 in der VERGANGENHEIT
    ("12. August", "2. August", "28. Juli"). Ein Rueckblick ist das Gegenteil
    dessen, was dieser Pfad sucht. Die Jahreszahl fehlt in solchen Angaben
    fast immer; gerechnet wird deshalb gegen das laufende Jahr und, wenn der
    Tag dann schon vorbei ist, gegen das naechste - so bleibt "10. Januar"
    im Dezember ein bevorstehender Termin.
    """
    for treffer in _DATUM_MUSTER.finditer(text or ""):
        monat = (treffer.group("m1") or treffer.group("m2") or "").lower()
        tag = treffer.group("t1") or treffer.group("t2") or ""
        if heute is None:
            return True
        try:
            nummer = _MONATE.index(monat) + 1
            termin = date(heute.year, nummer, int(tag))
        except ValueError:
            continue                     # z.B. "31. Februar"
        if termin < heute:
            try:
                termin = date(heute.year + 1, nummer, int(tag))
            except ValueError:
                continue
        if (termin - heute).days <= ANKUENDIGUNG_HORIZONT_TAGE:
            return True
    return False


def _ankuendigungstreffer(items: list[dict], heute: date | None) -> int:
    """Wie viele Meldungen der Gruppe nach VORNE zeigen - Ankuendigungs-
    vokabular oder ein noch bevorstehender Termin, gemessen auf dem
    FLIESSTEXT (`_text(h)`), nicht auf den seltenen Bindewoertern."""
    return sum(1 for h in items
               if _ANKUENDIGUNG_WORTMUSTER.search(_text(h))
               or _kuenftiger_termin(_text(h), heute))


def _ankuendigungssprache(items: list[dict], heute: date | None = None) -> bool:
    """Ob eine Gruppe ein noch BEVORSTEHENDES Ereignis beschreibt.

    Ein einzelner Treffer reicht nicht: "... seit September im Handel" ist
    eine beilaeufige Datumsnennung, kein Ereignishinweis. Erst ein Muster
    ueber mehrere Meldungen der Gruppe ist eins.
    """
    treffer = _ankuendigungstreffer(items, heute)
    return treffer >= max(MIND_ANKUENDIGUNGSTREFFER, len(items) // 2)


def _ankuendigungsdichte(kandidat: dict, heute: date | None) -> float:
    """Anteil der Meldungen einer Gruppe, die nach vorne zeigen.

    Das Sortierkriterium des Antizipations-Pfades - und ausdruecklich NICHT
    die Gruppengroesse. Nach Groesse sortiert stuenden vor dem Deckel die
    grossen Sammelgruppen, in denen zwei Meldungen zufaellig ein Datum
    tragen; gesucht ist aber die Gruppe, die GESCHLOSSEN ueber einen Termin
    berichtet.
    """
    items = kandidat.get("items") or []
    if not items:
        return 0.0
    return _ankuendigungstreffer(items, heute) / len(items)


def finde_antizipation(highlights: list[dict], heute: str = "") -> list[dict]:
    """Zweiter Erkennungspfad neben finde_kandidaten(): BEVORSTEHENDE
    Ereignisse (eine angekuendigte Keynote, ein Marktstart mit Datum), deren
    Meldungen schon ueber die Ankuendigung berichten, aber noch nicht ueber
    das grosse Echo verfuegen koennen - das kommt erst MIT dem Ereignis.

    Deshalb eine niedrigere Schwelle als finde_kandidaten()
    (MIND_MELDUNGEN_ANTIZIPATION statt MIND_MELDUNGEN) und ein zusaetzliches
    Erfordernis (_ankuendigungssprache), das die niedrigere Schwelle wieder
    einfaengt. Ergebnisse KONKURRIEREN NICHT um MAX_KANDIDATEN - sie werden
    von pflege_highlight_themen() zusaetzlich zu den Top-Kandidaten
    vorgelegt, markiert mit `bevorstehend: True`, hoechstens aber
    MAX_ANTIZIPATION viele: die dichtesten zuerst.

    `heute` entscheidet, ob ein genannter Termin noch bevorsteht. Fehlt es,
    zaehlt jede Tag-und-Monat-Angabe - der aufrufende Lauf gibt es immer mit.
    """
    try:
        stichtag = date.fromisoformat(heute) if heute else None
    except ValueError:
        stichtag = None
    kandidaten_items = [h for h in (highlights or []) if h.get("url")]
    gruppen, selten, haeufigkeit = _gruppen(
        kandidaten_items, mind_meldungen=MIND_MELDUNGEN_ANTIZIPATION,
        mind_quellen=MIND_QUELLEN_ANTIZIPATION)

    out: list[dict] = []
    for g in gruppen:
        kandidat = _kandidat_aus_gruppe(
            kandidaten_items, g["idx"], g["worte"], selten, haeufigkeit,
            mind_meldungen=MIND_MELDUNGEN_ANTIZIPATION,
            mind_quellen=MIND_QUELLEN_ANTIZIPATION)
        if kandidat is not None and _ankuendigungssprache(kandidat["items"],
                                                          stichtag):
            kandidat["bevorstehend"] = True
            out.append(kandidat)
    out.sort(key=lambda g: (-_ankuendigungsdichte(g, stichtag),
                            -len(g["items"]), -g["gewicht"]))
    return out[:MAX_ANTIZIPATION]


# ------------------------------------------------------------ Suchwortlogik
def suchmuster(suchwoerter) -> list[re.Pattern]:
    """Wortgrenzen-Muster je Suchwort - dieselbe Regel wie in
    analyze/competitors.py. Ohne die Grenzen faende "fold" jedes "Foldable"
    und "O2" jedes "CO2"."""
    muster = []
    for w in suchwoerter or []:
        w = " ".join(str(w or "").split())
        if len(w) >= 2:
            muster.append(re.compile(r"(?<!\w)" + re.escape(w.lower()) + r"(?!\w)"))
    return muster


def treffer(text: str, muster: list[re.Pattern]) -> int:
    """Wie viele VERSCHIEDENE Suchwoerter in diesem Text vorkommen."""
    t = (text or "").lower()
    return sum(1 for p in muster if p.search(t))


def _item(h: dict, woche: str) -> dict:
    """Eine Meldung, wie sie im Themenspeicher steht.

    Ohne `why_it_matters`: das ist die interne Einordnung fuer Vodafone, und
    die Themenseite ist oeffentlich - dieselbe Regel wie bei den
    Wochenseiten (`public_highlights` in report/html.py).
    """
    item = {
        "url": h.get("url") or "",
        "title": h.get("title") or "",
        "headline": h.get("headline") or "",
        "summary": h.get("summary") or "",
        "operator": h.get("operator") or "",
        "source": h.get("source") or "",
        "date": h.get("date") or "",
        "week": woche,
        "relevance": h.get("relevance") or 0,
    }
    for feld in ("image", "image_w", "image_h"):
        if h.get(feld):
            item[feld] = h[feld]
    return item


def _einsortieren(thema: dict, highlights: list[dict], woche: str) -> int:
    """Neue Meldungen per Suchwort in ein bestehendes Thema. Zahl der
    aufgenommenen Meldungen zurueck; Dubletten erkennt die URL."""
    muster = suchmuster(thema.get("keywords"))
    if not muster:
        return 0
    bekannt = {i.get("url") for i in thema.get("items") or []}
    neu = 0
    for h in highlights or []:
        url = h.get("url") or ""
        if not url or url in bekannt:
            continue
        if treffer(_text(h), muster) < MIND_TREFFER:
            continue
        thema.setdefault("items", []).append(_item(h, woche))
        bekannt.add(url)
        neu += 1
    if neu:
        thema["items"] = sorted(thema["items"], key=_rang,
                                reverse=True)[:MAX_ITEMS_JE_THEMA]
    return neu


# ------------------------------------------------------------ Themen-Agent
_AGENT_SYSTEM = """\
Du entscheidest, ob eine Gruppe von Nachrichtenmeldungen ein eigenes
EREIGNIS beschreibt, das eine temporäre Themenseite trägt.

Du bekommst Kandidatengruppen (automatisch über gemeinsame seltene Wörter
gefunden) und die bereits laufenden Themen. Ein Kandidat kann als
"bevorstehendes_ereignis" markiert sein: seine Meldungen KÜNDIGEN etwas an
(eine Keynote, einen Marktstart), das zum Zeitpunkt dieses Laufs noch nicht
stattgefunden hat - das darf trotzdem ein Thema sein.

Ein Ereignis ist zum Beispiel: die Vorstellung einer Gerätegeneration, eine
Übernahme, ein Netzausfall, eine Regulierungsentscheidung, ein Markteintritt.
KEIN Ereignis ist: eine Firma („Deutsche Telekom"), eine Technologie („5G",
„KI"), eine Region oder eine Kategorie. Wenn die Meldungen einer Gruppe nur
denselben Absender haben, aber von verschiedenen Dingen handeln, ist das
kein Thema.

Prüfe zuerst, ob die Gruppe zu einem der laufenden Themen gehört. Wenn ja,
nenne dessen slug und entscheide nicht neu.

Antworte AUSSCHLIESSLICH mit einem JSON-Array, ein Objekt je Kandidat:
[{"i": <index>,
  "thema": true|false,
  "gehoert_zu": "<slug eines laufenden Themas oder null>",
  "titel": "<deutscher Titel, höchstens 7 Wörter, kein Doppelpunkt-Kicker>",
  "leitsatz": "<ein Satz, der einer Managerin ohne Technikhintergrund sagt,
     worum es geht und warum es zählt. Keine Fachbegriffe ohne Erklärung.>",
  "suchwoerter": ["<4 bis 8 Wörter, mit denen weitere Meldungen zu genau
     diesem Ereignis erkannt werden. Eigennamen bevorzugt (Produktnamen,
     Firmennamen, Ortsnamen). Keine Allerweltswörter wie 'Netz' oder
     'Kunden'.>"],
  "bevorstehend": true|false,
  "event_datum": "<JJJJ-MM-TT, wenn die Meldungen ein konkretes Datum fuer
     ein noch NICHT stattgefundenes Ereignis nennen, sonst null. Fuer ein
     bereits eingetretenes Ereignis bleibt es null, auch wenn ein Datum in
     der Vergangenheit genannt wird.>"}]
Bei "thema": false duerfen die uebrigen Felder leer bzw. null bleiben.
Kein weiterer Text.
"""


def _agent_payload(kandidaten: list[dict], laufende: list[dict]) -> str:
    return json.dumps({
        "laufende_themen": [
            {"slug": t.get("slug"), "titel": t.get("title"),
             "suchwoerter": t.get("keywords") or []}
            for t in laufende],
        "kandidaten": [
            {"i": i,
             "verbindende_woerter": k["worte"],
             "bevorstehendes_ereignis": bool(k.get("bevorstehend")),
             "meldungen": [
                 {"titel": h.get("headline") or h.get("title") or "",
                  "zusammenfassung": (h.get("summary") or "")[:300],
                  "quelle": h.get("source") or ""}
                 for h in k["items"][:12]]}
            for i, k in enumerate(kandidaten)],
    }, ensure_ascii=False)


def befrage_agent(kandidaten: list[dict], laufende: list[dict],
                  model: str) -> list[dict]:
    """Das Urteil des Themen-Agenten, ein Eintrag je Kandidat.

    max_tokens ist bewusst gross: bei Reasoning-Modellen frisst die Denkspur
    das Budget, und eine leere Antwort sieht dann aus wie "nichts gefunden"
    (CLAUDE.md §6, Laeufe #83-85). 8000 ist die Untergrenze, die sich
    bewaehrt hat.
    """
    roh = complete(_AGENT_SYSTEM, _agent_payload(kandidaten, laufende),
                   model=model, max_tokens=_TOKENS)
    urteile = extract_json(roh)
    if not isinstance(urteile, list):
        raise ValueError("Themen-Agent lieferte kein JSON-Array")
    return [u for u in urteile if isinstance(u, dict)]


# ----------------------------------------------------------------- Pflege
def _freier_slug(titel: str, vergeben: set[str]) -> str:
    basis = slug(titel)
    if basis not in vergeben:
        return basis
    n = 2
    while f"{basis}-{n}" in vergeben:
        n += 1
    return f"{basis}-{n}"


_ISO_DATUM = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Wie weit ein vom Agenten genanntes `event_datum` in der Zukunft liegen darf.
#
# Das Datum setzt die Alterung eines Themas aus (EREIGNIS_SCHUTZ_TAGE), und
# es kommt aus einem Modell. Ein halluziniertes "2028-09-09" ist formal ein
# gueltiger Kalendertag und macht die Themenseite damit fuer ZWEI JAHRE
# unsterblich - sie steht dann im Fokusband der Titelseite, ohne dass je
# wieder eine Meldung dazu kaeme, und keine Alterung holt sie zurueck. Ein
# Quartal ist die Spanne, in der ein Marktstart oder eine Keynote sinnvoll
# angekuendigt wird; alles darueber ist Roadmap, nicht Termin, und wird wie
# ein fehlendes Datum behandelt. Dasselbe gilt fuer ein Datum in der
# VERGANGENHEIT: es kann kein bevorstehendes Ereignis mehr schuetzen.
EVENT_HORIZONT_TAGE = 90


def _valid_iso_datum(wert, heute: str = "") -> str:
    """Ein Datum vom Agenten, geprueft statt geglaubt - ein falsches Format,
    ein ungueltiger Kalendertag oder ein unplausibler Termin bricht die
    Alterung nicht, sondern wird wie ein fehlendes Datum behandelt (leerer
    String).

    Mit `heute` kommt die Plausibilitaetspruefung dazu: nur ein Termin
    zwischen heute und heute + EVENT_HORIZONT_TAGE zaehlt. Ohne `heute` wird
    nur das Format geprueft - die Uhr wird hier nie selbst gelesen, damit ein
    Test nicht die Zeit prueft (CLAUDE.md §6).
    """
    text = str(wert or "").strip()
    if not _ISO_DATUM.match(text):
        return ""
    try:
        termin = date.fromisoformat(text)
    except ValueError:
        return ""
    if heute:
        try:
            stichtag = date.fromisoformat(heute)
        except ValueError:
            return text
        if not (0 <= (termin - stichtag).days <= EVENT_HORIZONT_TAGE):
            return ""
    return text


def _ueberschneidet(a: dict, b: dict) -> bool:
    """Ob zwei Kandidaten im Wesentlichen dieselben Meldungen tragen -
    dieselbe UEBERLAPPUNG-Rechnung wie beim Zusammenlegen zweier Gruppen.
    Haelt den Antizipations-Pfad davon ab, eine Gruppe zusaetzlich
    vorzulegen, die schon unter den Top-Kandidaten steht."""
    urls_a = {h.get("url") for h in a.get("items") or [] if h.get("url")}
    urls_b = {h.get("url") for h in b.get("items") or [] if h.get("url")}
    if not urls_a or not urls_b:
        return False
    return len(urls_a & urls_b) / min(len(urls_a), len(urls_b)) >= UEBERLAPPUNG


def _durch_event_geschuetzt(thema: dict, heute: str) -> bool:
    """Ob die Zuwachs-Alterung fuer dieses Thema noch ausgesetzt ist.

    Ein Thema mit einem bevorstehenden Ereignis (`event_datum`) hat VOR dem
    Termin naturgemaess wenig zu berichten - das Echo kommt erst MIT dem
    Ereignis. Die normale Alterung wuerde es genau dann beenden, wenn es am
    wichtigsten wird. Ohne event_datum (der Regelfall, jedes Bestandsthema)
    gilt diese Sperre nicht - dessen Alterung bleibt exakt wie zuvor.

    **Die Sperre hat eine Obergrenze**, und die ist der Grund, warum hier
    nicht einfach `_valid_iso_datum` genuegt: das Datum kommt aus einem
    Modell, und ein halluziniertes "2028-09-09" ist ein formal gueltiger
    Kalendertag. Es haelt das Thema dann ZWEI JAHRE aktiv - eine Seite im
    Fokusband, zu der nie wieder eine Meldung kommt und die keine Alterung
    mehr erreicht. Jenseits von EVENT_HORIZONT_TAGE gilt das Datum deshalb
    als nicht vorhanden.

    Nach dem Termin laeuft die Sperre wie bisher noch EREIGNIS_SCHUTZ_TAGE
    weiter: das Echo kommt MIT dem Ereignis, und genau dann darf das Thema
    nicht altern.
    """
    event_datum = _valid_iso_datum(thema.get("event_datum"))
    if not event_datum:
        return False
    try:
        termin = date.fromisoformat(event_datum)
        stichtag = date.fromisoformat(heute)
    except ValueError:
        return False
    if (termin - stichtag).days > EVENT_HORIZONT_TAGE:
        return False
    return stichtag < termin + timedelta(days=EREIGNIS_SCHUTZ_TAGE)


def _schon_erfasst(kandidat: dict, laufende: list[dict]) -> bool:
    """Ob ein Kandidat im Wesentlichen aus Meldungen besteht, die ein
    aktives Thema schon traegt.

    Seit die Kandidatensuche das Berichtsarchiv mitliest, findet sie ein
    einmal erkanntes Ereignis in jedem folgenden Lauf erneut. Ohne diesen
    Filter wuerde derselbe Kandidat dem Agenten jedes Mal wieder vorgelegt -
    ein Modellaufruf je Lauf fuer eine laengst beantwortete Frage. Neue
    Meldungen erreichen das Thema weiter ueber die Suchwort-Zuordnung
    (_einsortieren), die kein Modell braucht. Gerechnet mit derselben
    UEBERLAPPUNG wie beim Zusammenlegen zweier Gruppen.
    """
    urls = {h.get("url") for h in kandidat.get("items") or [] if h.get("url")}
    if not urls:
        return True
    for t in laufende:
        bekannt = {i.get("url") for i in t.get("items") or []}
        if len(urls & bekannt) / len(urls) >= UEBERLAPPUNG:
            return True
    return False


def _passendes_thema(suchwoerter, themen: list[dict]) -> dict | None:
    """Ein bestehendes Thema, das dieselben Suchwoerter traegt.

    Der Agent bekommt die laufenden Themen und soll sie selbst wiedererkennen,
    aber verlassen darf sich der Speicher darauf nicht: ein zweites Thema mit
    denselben Suchwoertern wuerde dieselben Meldungen ein zweites Mal
    einsammeln, und auf der Titelseite stuende dasselbe Ereignis zweimal.
    """
    neu = {str(w).lower().strip() for w in suchwoerter or []}
    for t in themen:
        alt = {str(w).lower().strip() for w in t.get("keywords") or []}
        if len(neu & alt) >= MIND_GEMEINSAM:
            return t
    return None


def pflege_highlight_themen(highlights: list[dict], state_dir: Path,
                            heute: str, model: str | None = None,
                            use_llm: bool = False,
                            reports_dir: Path | None = None) -> dict:
    """Ein Lauf Themenpflege. Gibt eine Bilanz fuer das Protokoll zurueck.

    Failsafe an genau einer Stelle: scheitert der Agent, entstehen KEINE
    neuen Themen. Die Pflege der bestehenden laeuft trotzdem - sie kommt
    ohne Modell aus, und ein Aussetzer des Anbieters darf eine laufende
    Themenseite nicht altern lassen, obwohl neue Meldungen da waren.
    """
    state_dir = Path(state_dir)
    store = lade_store(state_dir)
    themen: list[dict] = store.get("topics") or []
    laufende = [t for t in themen if t.get("status") == "aktiv"]
    beendete = [t for t in themen if t.get("status") != "aktiv"]

    zuwachs: dict[str, int] = {}
    for thema in laufende:
        zuwachs[thema["slug"]] = _einsortieren(thema, highlights, heute)

    # Die Kandidatensuche rechnet ueber diesen Lauf PLUS die Highlights der
    # letzten Ausgaben (ARCHIV_TAGE): ein Ereignis verteilt sich ueber
    # Laeufe, und eine zustandslose Suche je Lauf hat deshalb vom 07. bis
    # zum 17.08.2026 kein einziges Thema gefunden. Der Zuwachs bestehender
    # Themen (oben) rechnet weiterhin NUR mit dem aktuellen Lauf - sonst
    # zaehlte jedes Archiv-Item als neue Aktivitaet und kein Thema altert.
    basis = [h for h in (highlights or []) if h.get("url")]
    if reports_dir is not None:
        basis = basis + _archiv_highlights(
            Path(reports_dir), heute, bekannt={h["url"] for h in basis})
    kandidaten = finde_kandidaten(basis)
    # Der Antizipations-Pfad konkurriert nicht um MAX_KANDIDATEN - er wird
    # ZUSAETZLICH vorgelegt, aber nicht fuer eine Gruppe, die schon unter den
    # Top-Kandidaten steht (sonst saehe der Agent dieselbe Gruppe zweimal).
    kandidaten = kandidaten + [
        k for k in finde_antizipation(basis, heute)
        if not any(_ueberschneidet(k, vorhanden) for vorhanden in kandidaten)]
    # Was ein beendetes Thema schon einmal war, wird nicht noch einmal neu
    # entdeckt - genau dafuer bleiben beendete Themen im Speicher. Und was
    # ein AKTIVES Thema schon traegt, wird dem Agenten nicht erneut
    # vorgelegt.
    kandidaten = [k for k in kandidaten
                  if _passendes_thema(k["worte"], beendete) is None
                  and not _schon_erfasst(k, laufende)]

    neu_angelegt: list[str] = []
    agent_fehler = ""
    if kandidaten and use_llm and model:
        try:
            urteile = befrage_agent(kandidaten, laufende, model)
        except Exception as exc:  # noqa: BLE001
            agent_fehler = str(exc)[:200]
            log.warning("Themen-Agent fehlgeschlagen (%s) - dieser Lauf legt "
                        "kein neues Thema an", agent_fehler)
            urteile = []
        vergeben = {t.get("slug") for t in themen}
        for u in urteile:
            try:
                i = int(u.get("i"))
            except (TypeError, ValueError):
                continue
            if not (0 <= i < len(kandidaten)) or not u.get("thema"):
                continue
            kandidat = kandidaten[i]
            suchwoerter = [str(w) for w in (u.get("suchwoerter") or []) if str(w).strip()]
            titel = " ".join(str(u.get("titel") or "").split())
            if not titel or len(suchwoerter) < MIND_GEMEINSAM:
                continue
            # event_datum zaehlt nur zusammen mit "bevorstehend": true - ein
            # Datum an einem bereits eingetretenen Ereignis darf die Alterung
            # nicht aussetzen (der Prompt verlangt das ohnehin, hier zaehlt
            # es doppelt).
            event_datum = (_valid_iso_datum(u.get("event_datum"), heute)
                           if u.get("bevorstehend") else "")

            ziel = next((t for t in laufende
                         if t.get("slug") == (u.get("gehoert_zu") or "")), None)
            ziel = ziel or _passendes_thema(suchwoerter, laufende)
            if ziel is None and slug(titel) in vergeben:
                # Gleicher Titel, andere Suchwoerter: das ist dasselbe Thema
                # unter einem anderen Namen, kein zweites.
                ziel = next((t for t in themen if t.get("slug") == slug(titel)), None)
                if ziel is not None and ziel.get("status") != "aktiv":
                    continue
            if ziel is not None:
                bekannt = {i2.get("url") for i2 in ziel.get("items") or []}
                fuer_ziel = [h for h in kandidat["items"]
                             if h.get("url") and h["url"] not in bekannt]
                ziel.setdefault("items", []).extend(
                    _item(h, h.get("_woche") or heute) for h in fuer_ziel)
                ziel["items"] = sorted(ziel["items"], key=_rang,
                                       reverse=True)[:MAX_ITEMS_JE_THEMA]
                zuwachs[ziel["slug"]] = zuwachs.get(ziel["slug"], 0) + len(fuer_ziel)
                # Ein Bestandsthema behaelt sein Datum - nur ein Thema OHNE
                # eines bekommt hier eines nachgetragen.
                if event_datum and not ziel.get("event_datum"):
                    ziel["event_datum"] = event_datum
                continue

            s = _freier_slug(titel, vergeben)
            vergeben.add(s)
            thema = {
                "slug": s, "title": titel,
                "description": " ".join(str(u.get("leitsatz") or "").split()),
                "keywords": suchwoerter[:8],
                "first_seen": heute, "last_active": heute,
                "runs_ohne_zuwachs": 0, "status": "aktiv",
                "items": [_item(h, h.get("_woche") or heute)
                          for h in kandidat["items"]],
            }
            # event_datum bleibt UNGESETZT (nicht leer), wenn der Agent keins
            # nennt oder das Ereignis schon eingetreten ist - Bestandsthemen
            # ohne dieses Feld verhalten sich in der Alterung unveraendert.
            if event_datum:
                thema["event_datum"] = event_datum
            themen.append(thema)
            laufende.append(thema)
            zuwachs[s] = len(thema["items"])
            neu_angelegt.append(s)

    beendet: list[str] = []
    for thema in laufende:
        n = zuwachs.get(thema["slug"], 0)
        if n >= MIND_ZUWACHS:
            thema["runs_ohne_zuwachs"] = 0
            thema["last_active"] = heute
        elif _durch_event_geschuetzt(thema, heute):
            # Vor einem bevorstehenden Ereignis bleibt das Thema unangetastet
            # aktiv, egal wie viele Laeufe ohne Zuwachs vergehen - siehe
            # _durch_event_geschuetzt. Ein Thema ohne event_datum durchlaeuft
            # diesen Zweig nie.
            continue
        else:
            thema["runs_ohne_zuwachs"] = int(thema.get("runs_ohne_zuwachs") or 0) + 1
            if thema["runs_ohne_zuwachs"] >= MAX_RUNS_OHNE_ZUWACHS:
                thema["status"] = "beendet"
                thema["ended"] = heute
                beendet.append(thema["slug"])

    store["topics"] = themen
    store["updated"] = heute
    speichere_store(state_dir, store)

    bilanz = {
        "kandidaten": len(kandidaten),
        "neu": neu_angelegt,
        "beendet": beendet,
        "aktiv": len(aktive_themen(store)),
        "zuwachs": sum(zuwachs.values()),
    }
    if agent_fehler:
        bilanz["error"] = agent_fehler
    return bilanz
