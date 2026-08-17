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

# --- Pflege ---------------------------------------------------------------
# Wie viele Suchwoerter eine neue Meldung treffen muss, um einem Thema
# zugeordnet zu werden. Eins reicht nicht: "Samsung" allein zieht jede
# Geraetemeldung des Herstellers in den Launch der Z-Fold-Reihe.
MIND_TREFFER = 2
# Ab wie vielen neuen Meldungen ein Lauf als Zuwachs zaehlt.
MIND_ZUWACHS = 2
MAX_RUNS_OHNE_ZUWACHS = 4
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

_TOKENS = 8000


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
    from datetime import date, timedelta

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


def finde_kandidaten(highlights: list[dict]) -> list[dict]:
    """Gruppen von Meldungen, die dasselbe Ereignis beschreiben koennten.

    Gesucht wird ueber WORTPAARE, nicht ueber eine Verbindungskette: zwei
    Meldungen gelten als verwandt, wenn sie zwei bestimmte seltene Woerter
    TEILEN, und die Gruppe ist genau die Menge der Meldungen mit beiden
    Woertern. Eine Kette ("A und B teilen zwei Woerter, B und C zwei andere")
    ergibt am Bericht vom 07.08.2026 gemessen EINE Gruppe aus 129 der 138
    Meldungen - jede Ausgabe haengt ueber irgendein Wort mit jeder anderen
    zusammen.

    Zurueck kommt je Gruppe: die Meldungen (dringendste zuerst), die
    tragenden Woerter und die Zahl der beteiligten Quellen. Ob das ein
    Ereignis ist, entscheidet der Agent - hier steht nur, dass es
    zusammenhaengt.
    """
    kandidaten_items = [h for h in (highlights or []) if h.get("url")]
    if len(kandidaten_items) < MIND_MELDUNGEN:
        return []

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
        if len(idx) < MIND_MELDUNGEN:
            continue
        quellen = {(kandidaten_items[i].get("source") or "").strip() for i in idx}
        if len(quellen - {""}) < MIND_QUELLEN:
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

    out: list[dict] = []
    for g in gruppen:
        idx = g["idx"]
        items = sorted((kandidaten_items[i] for i in idx), key=_rang, reverse=True)
        quellen = {(h.get("source") or "").strip() for h in items} - {""}
        if len(items) < MIND_MELDUNGEN or len(quellen) < MIND_QUELLEN:
            continue
        # Meldungen ohne _woche sind die des aktuellen Laufs - Archiv-Items
        # tragen ihr Ausgabedatum (siehe _archiv_highlights).
        aktuell = sum(1 for h in items if not h.get("_woche"))
        if aktuell < MIND_AKTUELL:
            continue
        # Die tragenden Woerter der Gruppe: was mindestens ein Drittel ihrer
        # Meldungen teilt, seltenste zuerst. Sie sind der Vorschlag an den
        # Agenten, nicht die spaeteren Suchwoerter - die schreibt er selbst.
        zaehler = haeufigkeiten(selten[i] for i in idx)
        schwelle = max(2, len(idx) // 3)
        tragend = sorted((w for w, n in zaehler.items() if n >= schwelle),
                         key=lambda w: (-zaehler[w], haeufigkeit[w], w))
        out.append({"items": items, "worte": tragend[:8],
                    "quellen": len(quellen),
                    "gewicht": gewicht(g["worte"], haeufigkeit)})
    out.sort(key=lambda g: (-len(g["items"]), -g["gewicht"]))
    return out[:MAX_KANDIDATEN]


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
gefunden) und die bereits laufenden Themen.

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
     'Kunden'.>"]}]
Bei "thema": false dürfen titel, leitsatz und suchwoerter leer bleiben.
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
