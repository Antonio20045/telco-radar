"""Wichtigkeits-Score fuer einzelne Promo-Angebote ("welche Aktionen sind
gerade am wichtigsten?").

Methodisch ein *composite indicator* im Sinne des OECD/JRC-Handbook on
Constructing Composite Indicators (Nardo/Saisana/Saltelli u. a., 2008):
mehrere einzeln definierte Teilkriterien, jedes auf eine gemeinsame,
FESTE Skala normalisiert, danach gewichtete Summenaggregation (Weighted Sum
Model / SAW). Bewusst kein AHP/TOPSIS - bei einer flachen Kriterienliste
liefern die empirisch praktisch dieselbe Rangfolge bei deutlich mehr
Komplexitaet.

Fuenf Achsen, je 0-3 Punkte mit ausformulierten Ankertexten:

  A lever     Wechselhebel      LLM    bricht das Angebot die Wechselbarriere?
  B depth     Angebotstiefe     LLM    wie substanziell ist der Vorteil?
  C reach     Marktreichweite   Code   Netzbetreiber vs. Online-Discountmarke
  D momentum  Marktbewegung     Code   wie viele andere Marken fahren dieselbe
                                       Mechanik gerade auch?
  E campaign  Kampagnencharakter Code  befristete Aktion vs. Dauerpreis

  Score = 100 * (0.30*A + 0.25*B + 0.20*C + 0.15*D + 0.10*E) / 3

Inhaltliche Herkunft der Achsen (kein fertiger Standard-Score fuer
Promo-Wichtigkeit existiert in der Literatur - die Bausteine schon):

  * A: Kim/Park/Jeong (2004, Telecommunications Policy) zur *switching
    barrier* und Gerpott/Rams/Schindler (2001) zum deutschen Mobilfunkmarkt -
    eine Praemie, die Wechselkosten direkt ausgleicht, ist gefaehrlicher als
    derselbe Betrag als reiner Preisnachlass.
  * B: promotion depth aus der Sales-Promotion-Forschung (Chandon/Wansink/
    Laurent 2000, Journal of Marketing).
  * C/D: Steenkamp/Nijs/Hanssens/Dekimpe (2005, Marketing Science) -
    Markenstaerke des Angreifers und Kategoriedynamik sind die belegten
    Moderatoren dafuer, ob ein Vorstoss ueberhaupt Wirkung entfaltet. Dieselbe
    Studie ist auch der Grund, warum ein hoher Score hier ausdruecklich
    "beobachten" heisst und nicht "kontern": auf Preispromo-Angriffe reagiert
    der Wettbewerb in 53,7 % der Faelle gar nicht, und Leeflang/Wittink (1996)
    zeigen, dass Manager eher ueber- als unterreagieren.

Zwei Konstruktionsentscheidungen, die bewusst so getroffen sind:

1. **Feste Goalposts statt relativer Normalisierung.** Kein Min-Max und kein
   z-Score ueber den jeweiligen Wochenbestand - sonst haette dasselbe Angebot
   je nach Woche einen anderen Score und die Zahl waere ueber die Zeit
   wertlos. Jede Achsenstufe ist absolut definiert (Distance-to-Reference,
   wie beim HDI). Nur so kann die ANZAHL der Highlights ehrlich schwanken,
   statt per Perzentil kuenstlich konstant gehalten zu werden.
2. **Nur A und B kommen vom LLM, 45 % des Scores rechnet der Code.** Absolute
   LLM-Punktvergaben sind nachweislich instabil (Zheng et al. 2023, MT-Bench:
   Positionskonsistenz teils unter 50 %; Haldar/Hockenmaier 2025, "Rating
   Roulette": bei drei identischen Laeufen nur ~61 % identische Urteile;
   selbst temperature=0 ist nicht deterministisch). Deshalb: kleine
   0-3-Skala mit Ankertexten statt einer 0-100-Note, Begruendung und
   woertlicher Beleg VOR der Zahl, und alles, was sich deterministisch
   ausrechnen laesst, wird ausgerechnet statt geschaetzt.

Score-Persistenz (siehe score_all): A und B werden pro Angebot EINMAL
bewertet und eingefroren - neu bewertet wird nur, wenn sich der Angebotstext
aendert, die Rubrik-Version steigt oder das Modell wechselt. C, D und E
rechnet jeder Lauf neu (kostenlos, deterministisch). Damit bleibt ein
Highlight ueber Wochen stehen, statt woechentlich neu gewuerfelt zu werden -
genau das, was der Betrieb hier braucht, weil die Pipeline ohnehin nur
prueft, ob ein Angebot noch laeuft.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime

from .llm import complete, extract_json

log = logging.getLogger(__name__)

# Steigt, wenn sich die Rubrik inhaltlich aendert. Alle gespeicherten
# LLM-Achsen mit kleinerer Version werden dann beim naechsten Lauf neu
# bewertet (und der Sprung ist im Datensatz nachvollziehbar).
# Version 2 (27.07.2026): nach einer zweiten, unabhaengigen Bewertungsrunde
# ueber dieselben 131 echten Angebote gescharft. Die Uebereinstimmung lag bei
# gewichtetem Kappa 0.95 (lever) bzw. 0.92 (depth), aber die verbliebenen
# Abweichungen konzentrierten sich auf drei erklaerbare Faelle: entfallender
# Bereitstellungspreis, Empfehlungspraemie und 1-Euro-Anzahlung. Fuer genau
# die steht jetzt ein verbindlicher Zweifelsfall-Block in der Rubrik.
RUBRIC_VERSION = 2

# Gewichte der fuenf Achsen. Summe muss 1.0 ergeben; ueber
# settings.yaml -> promo_score.weights ohne Codeaenderung drehbar.
DEFAULT_WEIGHTS: dict[str, float] = {
    "lever": 0.30, "depth": 0.25, "reach": 0.20,
    "momentum": 0.15, "campaign": 0.10,
}

# Ein-/Ausstiegsschwelle fuer die Highlight-Sektion (Hysterese-Band, siehe
# apply_hysteresis): rein ab ENTER, raus erst unter EXIT. Verhindert, dass ein
# Angebot direkt an der Grenze von Lauf zu Lauf flackert.
DEFAULT_ENTER = 68
DEFAULT_EXIT = 60

# Geschlossene Mechanik-Liste fuer Achse D. Bewusst klein und trennscharf:
# die Achse zaehlt, wie viele ANDERE Marken gerade dieselbe Mechanik fahren,
# und das funktioniert nur mit einem festen Vokabular. Alles, was nicht
# eindeutig passt, faellt auf "sonstiges" und traegt damit nichts bei.
MECHANICS: dict[str, str] = {
    "wechselpraemie": "Wechsel- oder Altgerätprämie",
    "geraetesubvention": "Gerät vergünstigt",
    "preisnachlass": "Preisnachlass auf den Tarif",
    "datenbonus": "mehr Datenvolumen",
    "gebuehrenerlass": "Gebühren erlassen",
    "zugabe": "Gratis-Zugabe",
    "bindungsfrei": "ohne Bindung",
    "zielgruppe": "Zielgruppentarif",
    "sonstiges": "sonstiges",
}
_DEFAULT_MECHANIC = "sonstiges"

# Achse C: Marktreichweite der Marke. Deterministisch aus der Quellen-
# konfiguration (config/promo_sources.yaml, Feld "reach"), nicht geschaetzt.
# Fallback aus dem Tier, falls das Feld fehlt.
_REACH_FROM_TIER = {1: 3, 2: 2}

# Achse E: ab wie vielen Tagen Restlaufzeit ein Enddatum noch als "akut" gilt.
_URGENT_DAYS = 14

_SCORE_SYSTEM = """\
Du bewertest fuer ein internes Vodafone-Wettbewerbsbriefing, wie stark
einzelne laufende Angebote von {brand} (deutscher Mobilfunkmarkt) sind.

Du bewertest GENAU ZWEI Achsen pro Angebot, jede auf einer festen Skala von
0 bis 3. Die Stufen sind absolut definiert - vergleiche die Angebote NICHT
untereinander, sondern jedes einzeln gegen die Beschreibung der Stufen.

ACHSE "lever" - Wechselhebel: Wie direkt greift das Angebot die Huerde an,
die einen Kunden bisher beim jetzigen Anbieter haelt?
  0 = kein Wechselanreiz (reine Bestandskundenoption, Zubehoerrabatt,
      Angebot ohne Tarifbezug)
  1 = guenstigerer Preis oder mehr Leistung im Tarif (klassischer Rabatt,
      mehr Datenvolumen zum gleichen Preis)
  2 = geldwerte Geraetesubvention oder Hardware-Bundle (Smartphone deutlich
      unter Marktpreis in Verbindung mit einem Vertrag)
  3 = zahlt den Wechsel direkt an: Wechselpraemie, Altgeraete-/Ankaufspraemie,
      Cashback bei Neuabschluss, Abloesung der Restlaufzeit beim alten
      Anbieter, Empfehlungs-/"Freunde werben"-Praemie, Testphase oder
      Kuendbarkeit ohne Mindestlaufzeit

ZWEIFELSFAELLE fuer "lever", verbindlich entschieden:
  - Ein entfallender einmaliger Bereitstellungs-, Anschluss- oder
    Versandpreis ist fuer sich genommen Stufe 1, NICHT Stufe 3. Fast jedes
    Neukundenangebot richtet sich an Wechsler; erst ein zusaetzlicher,
    eigenstaendiger Wechselanreiz hebt es auf Stufe 3.
  - Eine Empfehlungspraemie ("Freunde werben") ist Stufe 3, auch wenn der
    Werber Bestandskunde ist - bezahlt wird das Gewinnen eines NEUEN Kunden.
  - Eine Anzahlung von 1 Euro auf ein Geraet ist Stufe 2 (Geraetesubvention),
    nicht Stufe 3 - erst ein zusaetzlicher Ankaufs-/Eintauschbonus macht 3
    daraus.

ZWEIFELSFALL fuer "depth", verbindlich entschieden:
  - Nennt ein Geraete- oder Tarifangebot nur einen Monatspreis ("ab 27,99
    Euro im Monat"), ohne Streichpreis, Ersparnis oder Vergleichswert, ist
    das Stufe 1. Ohne Referenzwert laesst sich der Vorteil nicht beziffern -
    aber ein beworbener Aktionspreis ist auch nicht nichts. Nicht 0, nicht 2.

ACHSE "depth" - Angebotstiefe: Wie gross ist der bezifferbare wirtschaftliche
Vorteil fuer den Kunden, gemessen an dem, was im Text steht?
  0 = kein bezifferbarer Vorteil erkennbar, reine Werbeaussage
  1 = kleiner Vorteil (Groessenordnung bis etwa 50 Euro Gegenwert oder unter
      etwa 10 Prozent Preisvorteil)
  2 = spuerbarer Vorteil (Groessenordnung etwa 50 bis 200 Euro oder etwa 10
      bis 30 Prozent)
  3 = sehr grosser Vorteil (ueber etwa 200 Euro Gegenwert oder ueber etwa 30
      Prozent, z. B. mehrere hundert Euro Preisvorteil, unbegrenztes
      Datenvolumen ueber die gesamte Laufzeit, Verdopplung der Leistung)

Zusaetzlich ordnest du jedem Angebot GENAU EINE Mechanik zu:
{mechanics}

Vorgehen pro Angebot, in dieser Reihenfolge:
1. "evidence": zitiere WOERTLICH die kuerzeste Stelle aus dem gelieferten
   Angebotstext, die deine Bewertung stuetzt. Kein Text erfunden, keine
   Umformulierung. Findest du keine belegende Stelle, gib "" zurueck.
2. "reason": ein einziger, knapper deutscher Satz fuer einen Manager ohne
   technischen Hintergrund - WARUM ist dieses Angebot beachtenswert (oder
   eben nicht)? Keine Handlungsempfehlung fuer Vodafone, keine Formulierung
   wie "Vodafone sollte" oder "Vodafone koennte". Reine Einordnung.
   Schreibe korrektes Deutsch MIT Umlauten und Eszett (ae/oe/ue/ss nur, wenn
   es wirklich so geschrieben wird) - der Satz steht so auf der Website.
3. "lever", "depth": die Zahlen 0-3.
4. "mechanic": einer der oben genannten Schluessel.

Bewerte nur auf Basis des gelieferten Textes. Erfinde nichts. Bist du
unsicher, waehle die NIEDRIGERE Stufe.

Antworte AUSSCHLIESSLICH mit einem JSON-Array, ein Objekt je geliefertem
Angebot, in derselben Reihenfolge und mit dem mitgelieferten Feld "id":
[{{"id": "...", "evidence": "...", "reason": "...", "lever": 0, "depth": 0,
"mechanic": "..."}}]
"""


# --------------------------------------------------------------------------
# Deterministische Achsen (C, D, E) - kein LLM, exakt reproduzierbar
# --------------------------------------------------------------------------

def reach_axis(source) -> int:
    """Achse C aus der Quellenkonfiguration. *source* ist ein PromoSource
    (oder None, wenn die Marke nicht mehr konfiguriert ist - dann 0, statt
    eine Reichweite zu raten)."""
    if source is None:
        return 0
    explicit = getattr(source, "reach", None)
    if explicit is not None:
        return max(0, min(3, int(explicit)))
    return _REACH_FROM_TIER.get(getattr(source, "tier", 2), 1)


def mechanic_brand_index(entries: list[dict]) -> dict[str, set[str]]:
    """Mechanik -> Menge der Marken, die aktuell ein sichtbares Angebot
    dieser Mechanik fahren. Basis fuer Achse D. Nur nicht-ausgelaufene
    Eintraege zaehlen; "sonstiges" wird bewusst nicht indiziert, weil es
    keine gemeinsame Mechanik beschreibt."""
    index: dict[str, set[str]] = {}
    for e in entries:
        if e.get("status") == "ausgelaufen":
            continue
        mech = e.get("mechanic")
        if not mech or mech == _DEFAULT_MECHANIC:
            continue
        brand = (e.get("brand") or "").strip()
        if brand:
            index.setdefault(mech, set()).add(brand)
    return index


def momentum_axis(mechanic: str | None, brand: str,
                  index: dict[str, set[str]]) -> int:
    """Achse D: wie viele ANDERE Marken fahren gerade dieselbe Mechanik?
    0 andere -> 0, 1 -> 1, 2-3 -> 2, ab 4 -> 3."""
    if not mechanic or mechanic == _DEFAULT_MECHANIC:
        return 0
    others = len(index.get(mechanic, set()) - {(brand or "").strip()})
    if others == 0:
        return 0
    if others == 1:
        return 1
    if others <= 3:
        return 2
    return 3


_DATE_PATTERNS = (
    (re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b"), ("d", "m", "y")),
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), ("y", "m", "d")),
)


def parse_valid_until(text: str | None) -> date | None:
    """Erstes erkennbares Datum aus einem Freitextfeld ("31.08.2026",
    "gueltig bis 2026-08-31"). Gibt None zurueck bei reinen Textangaben wie
    "Nur fuer kurze Zeit" - die werden in campaign_axis als vage Befristung
    behandelt, nicht als hartes Enddatum."""
    if not text:
        return None
    for pattern, order in _DATE_PATTERNS:
        m = pattern.search(str(text))
        if not m:
            continue
        parts = dict(zip(order, m.groups()))
        try:
            return date(int(parts["y"]), int(parts["m"]), int(parts["d"]))
        except ValueError:
            continue
    return None


def campaign_axis(valid_until: str | None, today: str) -> int:
    """Achse E - Kampagnencharakter. Ein unbefristetes Dauerangebot ist
    Hintergrundrauschen, eine befristete Aktion mit hartem Enddatum ist eine
    echte Kampagne:
      0 = kein Enddatum genannt (oder bereits abgelaufen)
      1 = vage Befristung im Text ("nur fuer kurze Zeit")
      2 = konkretes Enddatum, mehr als 14 Tage entfernt
      3 = konkretes Enddatum in den naechsten 14 Tagen"""
    raw = (valid_until or "").strip()
    if not raw:
        return 0
    end = parse_valid_until(raw)
    if end is None:
        return 1
    try:
        now = datetime.fromisoformat(today).date()
    except ValueError:
        return 2
    days = (end - now).days
    if days < 0:
        return 0
    return 3 if days <= _URGENT_DAYS else 2


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------

def normalise_weights(raw: dict | None) -> dict[str, float]:
    """Gewichte aus settings.yaml uebernehmen, fehlende Achsen aus den
    Defaults ergaenzen und auf Summe 1.0 normieren. Unbrauchbare Eingaben
    (nicht-numerisch, alles 0, negativ) fallen sauber auf die Defaults
    zurueck - eine kaputte Konfigurationszeile darf den Lauf nicht kippen."""
    weights = dict(DEFAULT_WEIGHTS)
    for key in DEFAULT_WEIGHTS:
        if not isinstance(raw, dict) or key not in raw:
            continue
        try:
            value = float(raw[key])
        except (TypeError, ValueError):
            continue
        if value >= 0:
            weights[key] = value
    total = sum(weights.values())
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {k: v / total for k, v in weights.items()}


def composite(axes: dict, weights: dict[str, float] | None = None) -> int:
    """Gewichtete Summe der fuenf 0-3-Achsen, skaliert auf 0-100.
    Fehlende Achsen zaehlen als 0 (nie als Fehler)."""
    w = weights or DEFAULT_WEIGHTS
    total = 0.0
    for key, weight in w.items():
        try:
            value = float(axes.get(key) or 0)
        except (TypeError, ValueError):
            value = 0.0
        total += weight * max(0.0, min(3.0, value))
    return int(round(100 * total / 3))


def score_basis(entry: dict) -> str:
    """Fingerabdruck des bewerteten Angebotstextes. Aendert er sich, muessen
    die LLM-Achsen neu bewertet werden - sonst nicht (Score-Caching)."""
    basis = "|".join([
        (entry.get("brand") or "").strip().lower(),
        " ".join((entry.get("headline") or "").lower().split()),
        " ".join((entry.get("description") or "").lower().split()),
    ])
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def needs_judgement(entry: dict, model: str) -> bool:
    """True, wenn die LLM-Achsen fuer diesen Eintrag (neu) bewertet werden
    muessen: noch nie bewertet, Angebotstext geaendert, Rubrik-Version
    gestiegen oder anderes Modell."""
    judged = entry.get("judged") or {}
    if not judged:
        return True
    if judged.get("basis") != score_basis(entry):
        return True
    if int(judged.get("rubric_version") or 0) != RUBRIC_VERSION:
        return True
    return judged.get("model") != model


# --------------------------------------------------------------------------
# LLM-Achsen (A, B)
# --------------------------------------------------------------------------

def _clamp_axis(value) -> int:
    try:
        num = int(round(float(value)))
    except (TypeError, ValueError):
        return 0
    return max(0, min(3, num))


def _normalise_quote(text: str) -> str:
    return " ".join((text or "").lower().split())


def _evidence_supported(evidence: str, entry: dict) -> bool:
    """Der geforderte woertliche Beleg muss tatsaechlich im bewerteten Text
    stehen. Verhindert, dass eine hohe Stufe auf einem frei erfundenen Zitat
    beruht ("evidence-anchored scoring") - ohne Beleg werden die LLM-Achsen
    auf 1 gedeckelt, statt den Eintrag ganz zu verwerfen."""
    quote = _normalise_quote(evidence)
    if len(quote) < 8:
        return False
    haystack = _normalise_quote(
        f"{entry.get('headline') or ''} {entry.get('description') or ''}")
    return quote in haystack


def _offer_payload(entries: list[dict]) -> str:
    return json.dumps([
        {"id": e.get("id"), "titel": e.get("headline") or "",
         "beschreibung": e.get("description") or ""}
        for e in entries], ensure_ascii=False)


def judge_offers(brand: str, entries: list[dict], model: str,
                 max_tokens: int = 12000) -> dict[str, dict]:
    """Bewertet die LLM-Achsen fuer die Angebote EINER Marke in einem Aufruf.

    Warum gebuendelt statt ein Aufruf je Angebot (was fuer die Urteilsqualitaet
    leicht besser waere): der Provider auf diesem Endpunkt ist knapp und hat
    diesen Lauf schon einmal gekippt (siehe settings.yaml, HTTP 503 "Worker
    local total request limit reached"). Ein Aufruf je Angebot waere beim
    Erstlauf ueber 100 Aufrufe und wuerde das Job-Zeitbudget sprengen. Die
    Buendelung ist pro Marke, nie ueber Marken hinweg, und der Prompt weist
    ausdruecklich an, jedes Angebot einzeln gegen die festen Ankertexte zu
    bewerten statt die Angebote untereinander zu vergleichen.

    Failsafe: bei jedem Fehler ein leeres Dict - die betroffenen Eintraege
    bleiben dann schlicht unbewertet (Score None) und werden im naechsten
    Lauf erneut versucht. Nie ein Abbruch."""
    if not entries:
        return {}
    mechanics = "\n".join(f"  {k} = {v}" for k, v in MECHANICS.items())
    system = _SCORE_SYSTEM.format(brand=brand, mechanics=mechanics)
    try:
        raw = complete(system, _offer_payload(entries), model=model,
                       max_tokens=max_tokens)
        parsed = extract_json(raw)
    except Exception as exc:  # noqa: BLE001
        log.warning("Promo-Bewertung (%s) fehlgeschlagen: %s", brand, str(exc)[:140])
        return {}

    by_id = {e.get("id"): e for e in entries}
    out: dict[str, dict] = {}
    for row in parsed if isinstance(parsed, list) else []:
        if not isinstance(row, dict):
            continue
        eid = str(row.get("id") or "").strip()
        entry = by_id.get(eid)
        if entry is None:
            continue
        evidence = str(row.get("evidence") or "").strip()
        lever = _clamp_axis(row.get("lever"))
        depth = _clamp_axis(row.get("depth"))
        supported = _evidence_supported(evidence, entry)
        if not supported:
            lever, depth = min(lever, 1), min(depth, 1)
        mechanic = str(row.get("mechanic") or "").strip().lower()
        if mechanic not in MECHANICS:
            mechanic = _DEFAULT_MECHANIC
        out[eid] = {
            "lever": lever, "depth": depth, "mechanic": mechanic,
            "evidence": evidence if supported else "",
            "evidence_ok": supported,
            "reason": str(row.get("reason") or "").strip(),
            "basis": score_basis(entry), "model": model,
            "rubric_version": RUBRIC_VERSION,
        }
    return out


# --------------------------------------------------------------------------
# Orchestrierung
# --------------------------------------------------------------------------

def apply_hysteresis(entry: dict, score: int, enter: int, exit_: int) -> bool:
    """Highlight-Zustand mit Hysterese-Band fortschreiben: rein ab *enter*,
    raus erst unter *exit_*, dazwischen bleibt der bisherige Zustand stehen.
    Ein ausgelaufenes Angebot ist nie Highlight."""
    if entry.get("status") == "ausgelaufen":
        return False
    if score >= enter:
        return True
    if score < exit_:
        return False
    return bool(entry.get("highlight"))


def score_all(entries: list[dict], sources: list, today: str,
              model: str, use_llm: bool, settings: dict | None = None,
              max_workers: int = 2) -> dict:
    """Bewertet alle nicht-ausgelaufenen Eintraege und schreibt Score,
    Achsen, Begruendung und Highlight-Flag IN die uebergebenen Dicts
    (PromoDB-Eintraege werden also direkt aktualisiert und danach mitgespei-
    chert). Gibt eine Zusammenfassung fuers Protokoll zurueck.

    LLM-Achsen werden nur fuer Eintraege angefragt, bei denen
    needs_judgement() True ist - alle anderen behalten ihre eingefrorene
    Bewertung. Die deterministischen Achsen werden IMMER neu gerechnet, auch
    ohne LLM: dadurch verschiebt sich ein Score sauber, wenn ein Enddatum
    naeher rueckt oder eine Mechanik ploetzlich Marktbreite bekommt."""
    cfg = (settings or {}).get("promo_score") or {}
    weights = normalise_weights(cfg.get("weights"))
    try:
        enter = int(cfg.get("highlight_enter", DEFAULT_ENTER))
        exit_ = int(cfg.get("highlight_exit", DEFAULT_EXIT))
    except (TypeError, ValueError):
        enter, exit_ = DEFAULT_ENTER, DEFAULT_EXIT
    if exit_ > enter:
        exit_ = enter

    # Nur Marken, die aktuell auch konfiguriert sind: die DB haelt Eintraege
    # entfernter Quellen als totes Datum weiter vor (z. B. der 2026 gestrichene
    # Tier-3-Zweig). Die tauchen auf der Seite nirgends auf - sie zu bewerten
    # waere pure LLM-Verschwendung.
    by_name = {getattr(s, "name", ""): s for s in (sources or [])}
    live = [e for e in entries
            if e.get("status") != "ausgelaufen" and e.get("brand") in by_name]

    judged_new = judged_failed = 0
    if use_llm:
        pending: dict[str, list[dict]] = {}
        for e in live:
            if needs_judgement(e, model):
                pending.setdefault(e.get("brand") or "", []).append(e)
        if pending:
            log.info("Promo-Bewertung: %d Angebote in %d Marken zu bewerten",
                     sum(len(v) for v in pending.values()), len(pending))
            with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
                futures = {pool.submit(judge_offers, brand, items, model): (brand, items)
                           for brand, items in pending.items()}
                for fut in as_completed(futures):
                    brand, items = futures[fut]
                    try:
                        verdicts = fut.result()
                    except Exception as exc:  # noqa: BLE001
                        log.warning("Promo-Bewertung (%s) abgebrochen: %s",
                                    brand, str(exc)[:140])
                        verdicts = {}
                    for item in items:
                        verdict = verdicts.get(item.get("id"))
                        if verdict:
                            item["judged"] = verdict
                            judged_new += 1
                        else:
                            judged_failed += 1

    # Achse D braucht die Mechanik ALLER Eintraege, also erst nach der
    # LLM-Runde - sonst wuerde ein frisch bewertetes Angebot seine eigene
    # Marktbreite nicht sehen.
    for e in live:
        judged = e.get("judged") or {}
        if judged.get("mechanic"):
            e["mechanic"] = judged["mechanic"]
    index = mechanic_brand_index(live)

    scored = highlights = 0
    for e in live:
        judged = e.get("judged") or {}
        axes = {
            "lever": _clamp_axis(judged.get("lever")) if judged else None,
            "depth": _clamp_axis(judged.get("depth")) if judged else None,
            "reach": reach_axis(by_name.get(e.get("brand") or "")),
            "momentum": momentum_axis(e.get("mechanic"), e.get("brand") or "", index),
            "campaign": campaign_axis(e.get("valid_until"), today),
        }
        if not judged:
            # Ohne LLM-Achsen waere der Score systematisch zu niedrig und
            # nicht mit bewerteten Angeboten vergleichbar - dann lieber
            # ehrlich "noch nicht bewertet" als eine irrefuehrende Zahl.
            e["score"] = None
            e["score_axes"] = {k: v for k, v in axes.items() if v is not None}
            e["highlight"] = False
            continue
        e["score_axes"] = axes
        e["score"] = composite(axes, weights)
        e["score_reason"] = judged.get("reason") or ""
        e["scored_at"] = today
        e["highlight"] = apply_hysteresis(e, e["score"], enter, exit_)
        scored += 1
        if e["highlight"]:
            highlights += 1

    # Ausgelaufene Eintraege verlieren ihr Highlight sofort - sie sind auf
    # der Seite ohnehin nur noch eine Fussnotenzahl.
    for e in entries:
        if e.get("status") == "ausgelaufen":
            e["highlight"] = False

    return {"scored": scored, "judged_new": judged_new,
            "judged_failed": judged_failed, "highlights": highlights,
            "enter": enter, "exit": exit_, "weights": weights}
