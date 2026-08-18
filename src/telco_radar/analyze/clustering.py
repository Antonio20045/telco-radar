"""Ereignis-Clustering: dieselbe Sache aus drei Quellen ist EINE Meldung.

Warum es das gibt
-----------------
Der Seen-Store (dedupe.py) dedupliziert die normalisierte URL. Das ist genau
richtig fuer seine Aufgabe ("kenne ich diesen Artikel schon?") und genau
falsch fuer die Frage, die der Leser stellt ("was ist passiert?"). Berichtet
dieselbe Sache ueber drei Fachmedien, entstehen drei Items, drei
LLM-Bewertungen und im schlimmsten Fall drei Plaetze auf der Titelseite.

Gemessen an der Ausgabe vom 07.08.2026: sieben erkennbare Ereignis-Cluster mit
17 Meldungen, die auf 7 gehoeren. Der teuerste Fall stand im wichtigsten Modul
der Startseite - "Digi startet kostenlosen Spam-Anrufwarndienst" auf Platz 2
und "Digi startet Spam-Filter fuer unerwuenschte Anrufe" auf Platz 5 von
sieben. Das faellt einem Manager ohne jedes Fachwissen auf und beschaedigt die
Glaubwuerdigkeit der ganzen Seite.

Wie zugeordnet wird
-------------------
Zwei Stufen, damit es billig bleibt:

1. **Deterministischer Vorfilter, kein LLM.** Ein Paar gehoert zusammen, wenn
   Zeitfenster <= 72 h UND ein gemeinsamer Akteur UND eine ausreichende
   Titelaehnlichkeit. Als Aehnlichkeitsmass dienen normalisierte Wortmengen
   (Jaccard ohne Stoppwoerter) plus ein Zahlen-Abgleich: "1-GW", "34,95 EUR",
   "800 Mio." sind extrem starke Signale und billig zu extrahieren. Die
   Indosat-, Zayo- und Starlink-Faelle werden alle drei allein durch Akteur
   plus Zahl erwischt.

2. **LLM nur im Graubereich.** Nur Paare zwischen den Schwellen kommen als
   Ja/Nein-Frage ans Modell. Der Digi-Fall ist genau dieser Grenzfall: gleicher
   Akteur, gleiches Thema, unterschiedliche Sprachen (eine Meldung spanisch,
   eine deutsch), kaum gemeinsame Woerter.

**Stern statt Kette.** Eine Meldung wird mit dem VERTRETER einer Gruppe
verglichen, nie mit einem beliebigen Mitglied. Der transitive Abschluss ueber
Paare ist der Fehler, den highlight_topics.py schon einmal gemacht hat: ueber
einzelne gemeinsame Woerter verband ein Verwandtschafts-Graph 129 von 138
Meldungen zu einer Gruppe. A gleicht B, B gleicht C, und C hat mit A nichts zu
tun.

**Was NICHT kollabieren darf**: zwei echte Folgeereignisse. "Samsung stellt
Galaxy Z Fold8 vor" und "Samsung startet den Verkauf" zwei Wochen spaeter sind
zwei Ereignisse. Dagegen steht das 72-Stunden-Fenster als harte Grenze - es ist
kein Feintuning, sondern die Sicherung.

**Die Gruppen-ID kommt aus der kanonischen URL**, nie aus dem Titeltext. Ein
aus dem Titel gehashter Schluessel ist beim naechsten Lauf ein anderer, sobald
eine Quelle ihre Ueberschrift nachtraeglich aendert - denselben Fehler hat der
Promo-Zweig schon einmal bezahlt.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..models import Item, normalize_url
from .llm import complete, extract_json

log = logging.getLogger(__name__)

# Harte Grenze. Alles darueber sind zwei Ereignisse, auch wenn die Woerter
# uebereinstimmen (Ankuendigung und Verkaufsstart derselben Sache).
ZEITFENSTER_STUNDEN = 72

# Ab hier gilt ein Paar allein ueber die Woerter als dasselbe Ereignis.
SCHWELLE_SICHER = 0.50
# Mit einer geteilten kennzeichnenden Zahl reicht deutlich weniger - eine
# gemeinsame "1 GW" oder "34,95 EUR" ist ein staerkerer Beleg als zehn
# gemeinsame Allerweltswoerter. Gemessen an der Ausgabe vom 07.08.2026: die
# drei Indosat-Meldungen teilen 17 % ihrer Woerter und die Zahl "1 GW".
SCHWELLE_MIT_ZAHL = 0.16
# Darunter beginnt der Graubereich, den das Modell entscheidet. Noch tiefer
# lohnt die Frage nicht: unter 0,12 gemeinsamer Woerter bei verschiedenen
# Sprachen entscheidet das Modell auf gut Glueck.
SCHWELLE_GRAU = 0.12

# Wie viele Zweifelsfaelle je Lauf ans Modell gehen duerfen. Die Stufe soll
# Geld SPAREN; ein Lauf, der 300 Ja/Nein-Fragen stellt, tut das Gegenteil.
MAX_LLM_PRUEFUNGEN = 40

# Ab wie vielen Mitgliedern eine Gruppe keine weiteren mehr aufnimmt. Eine
# echte Ereignis-Gruppe hat drei bis fuenf Quellen; alles darueber ist der
# Verdacht, dass ein zu allgemeiner Akteur ("Nvidia", "KI") gerade alles
# einsammelt.
MAX_MITGLIEDER = 8

_WORT = re.compile(r"[a-z0-9äöüß]+")

# Stoppwoerter in allen Sprachen, in denen die Quellen senden (seit Session 5
# auch fr/es/it/pt). Eine gemeinsame "the" beweist nichts.
_STOPP = {
    # de
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem",
    "eines", "und", "oder", "mit", "fuer", "für", "von", "vom", "auf", "aus",
    "bei", "nach", "ueber", "über", "unter", "zum", "zur", "ist", "sind",
    "wird", "werden", "hat", "haben", "sich", "auch", "neue", "neuen", "neuer",
    "neues", "mehr", "als", "wie", "nicht", "sein", "seine", "seinen", "ihre",
    "ihren", "dass", "durch", "gegen", "beim", "kann", "koennen", "können",
    # en
    "the", "and", "for", "with", "from", "into", "that", "this", "will",
    "has", "have", "are", "was", "were", "its", "new", "more", "than", "over",
    "after", "before", "says", "said", "amid", "plans", "plan", "launches",
    "launch", "announces", "announced", "announcement", "reports", "report",
    # es / pt / it / fr
    "para", "por", "con", "las", "los", "del", "una", "unos", "unas", "que",
    "sus", "sur", "les", "des", "aux", "dans", "pour", "avec", "sul", "nel",
    "della", "delle", "dei", "com", "para", "não", "mais", "sobre",
}

# Wortendungen, die eine Form von ihrer Grundform trennen. Bewusst KEIN echter
# Stemmer: der wuerde eine Abhaengigkeit einziehen und bei Eigennamen
# ("Starlink" -> "Starlin") mehr kaputtmachen als er hilft. Nur die drei
# Endungen, die im Deutschen und Englischen dieselbe Sache verschieden
# aussehen lassen.
_ENDUNGEN = ("en", "es", "er", "s")

# Zahl mit optionaler Einheit. Sie ist der staerkste billige Beleg, den eine
# Ueberschrift hergibt: "1-GW-KI-Fabrik" und "1-GW-Rechenzentrum" meinen
# dasselbe Rechenzentrum, "800 Mio. Dollar" steht in beiden Meldungen ueber
# dieselbe Finanzierung.
_ZAHL = re.compile(
    r"(\d+(?:[.,]\d+)*)\s*[-\s]?\s*"
    r"(gw|mw|kw|tb|gb|mb|gbit|mbit|mhz|ghz|khz|mrd|mio|bn|billion|billionen|"
    r"milliarden|millionen|million|prozent|%|eur|euro|€|usd|dollar|\$)?",
    re.I)

_EINHEIT_GLEICH = {
    "€": "eur", "euro": "eur", "$": "usd", "dollar": "usd",
    "milliarden": "mrd", "millionen": "mio", "million": "mio",
    "billion": "mrd", "billionen": "mrd", "bn": "mrd", "prozent": "%",
}

# Woerter, die als Akteur nichts unterscheiden. Sie stehen in englischen
# Schlagzeilen gross und wandern damit sonst in die Akteursliste - "Zayo Teams
# with NVIDIA" und "AT&T Bets on 5G" saehen ueber "Teams"/"Bets" verwandt aus.
# Die eigentliche Sicherung ist die Seltenheitsrechnung in `gruppiere()`;
# diese Liste faengt die Faelle ab, in denen ein Stapel zu klein ist, als dass
# die Haeufigkeit etwas aussagt (und den Weg ueber `ClusterStore.zuordnen`,
# wo es gar keinen Stapel gibt).
_KEIN_AKTEUR = {
    "team", "teams", "expand", "expands", "launch", "launches", "add", "adds",
    "sign", "signs", "unveil", "unveils", "select", "selects", "bet", "bets",
    "move", "moves", "make", "makes", "put", "puts", "plot", "plots", "eye",
    "eyes", "target", "targets", "boost", "boosts", "cut", "cuts", "rise",
    "rises", "jump", "jumps", "soar", "soars", "help", "helps", "drive",
    "drives", "scale", "achiev", "achieves", "enhanc", "enhances", "enabl",
    "enables", "integrat", "integrates", "partner", "partners", "invest",
    "invests", "network", "networks", "mobile", "telecom", "telecoms", "cloud",
    "market", "report", "reports", "service", "services", "solution",
    "solutions", "business", "group", "internet", "broadband", "data",
    "digital", "wireless", "platform", "technology", "technologies", "global",
    "international", "consumer", "customer", "customers", "revenue", "growth",
    "million", "billion", "industry", "company", "corp", "inc", "gmbh",
    "video", "interview", "news", "update", "week", "year", "first", "next",
    "new", "more", "with", "for", "and", "the", "how", "why", "what",
}


def _stamm(wort: str) -> str:
    if len(wort) <= 4:
        return wort
    for endung in _ENDUNGEN:
        if wort.endswith(endung) and len(wort) - len(endung) >= 4:
            return wort[: -len(endung)]
    return wort


def wortmenge(text: str) -> frozenset[str]:
    """Bedeutungstragende Wortstaemme eines Textes."""
    return frozenset(
        _stamm(w) for w in _WORT.findall((text or "").lower())
        if len(w) >= 3 and w not in _STOPP)


def zahlenmenge(text: str) -> frozenset[str]:
    """Kennzeichnende Zahlen, normalisiert ("1gw", "34,95eur", "800mio").

    Kennzeichnend heisst: mit Einheit, mit Nachkommastelle oder mindestens
    vierstellig. Eine nackte "5" oder "600" ist es NICHT - sie steht in jeder
    zweiten Ueberschrift ("5G", "Q2", "600 Kunden") und wuerde die Schwelle
    SCHWELLE_MIT_ZAHL entwerten, die gerade darauf beruht, dass ein geteilter
    Wert selten ist. Jahreszahlen fallen aus demselben Grund heraus.
    """
    out = set()
    for wert, einheit in _ZAHL.findall(text or ""):
        einheit = _EINHEIT_GLEICH.get(einheit.lower(), einheit.lower())
        blank = wert.replace(".", "").replace(",", "")
        if blank.isdigit() and 1900 <= int(blank) <= 2100 and len(blank) == 4:
            continue
        if not einheit:
            # Ohne Einheit nur, wenn der Wert fuer sich selten ist.
            if ("," not in wert and "." not in wert) and len(blank) < 4:
                continue
        out.add(f"{wert.replace('.', '')}{einheit}")
    return frozenset(out)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    schnitt = len(a & b)
    if not schnitt:
        return 0.0
    # Gegen die KLEINERE Menge, nicht gegen die Vereinigung. Dieselbe Lehre wie
    # beim Abnahme-Check der Quellen (Session 5): eine kurze Schlagzeile, die
    # vollstaendig in einer laengeren steckt, ist dieselbe Meldung - gegen die
    # Vereinigung gerechnet saehe sie nur halb so aehnlich aus.
    return schnitt / min(len(a), len(b))


@dataclass
class _Profil:
    """Was von einer Meldung fuer den Vergleich gebraucht wird."""

    item: Item
    worte: frozenset[str]
    zahlen: frozenset[str]
    akteure: frozenset[str]
    # Der Betreiber aus dem gleichnamigen Feld - der EINE Name, den die
    # Konfiguration verantwortet und nicht der Grossschreibung entnommen ist.
    betreiber: frozenset[str] = frozenset()

    @classmethod
    def von(cls, item: Item, akteure: frozenset[str] | None = None) -> "_Profil":
        # Der Titel traegt das Ereignis, die Zusammenfassung traegt die Zahlen.
        # Beide zusammen fuer die Woerter waere falsch: ein langer Teaser
        # verduennt jede Aehnlichkeit.
        text = item.title
        return cls(
            item=item,
            worte=wortmenge(text),
            zahlen=zahlenmenge(f"{text} {item.summary[:400]}"),
            akteure=akteure if akteure is not None else akteur_kandidaten(item),
            betreiber=_betreiber(item),
        )


def _betreiber(item: Item) -> frozenset[str]:
    return frozenset(
        _stamm(w) for w in _WORT.findall((item.operator or "").lower())
        if len(w) >= 3 and w not in _STOPP and w not in _KEIN_AKTEUR)


def akteur_kandidaten(item: Item) -> frozenset[str]:
    """Wer in der Meldung vorkommen KOENNTE - Betreiberfeld plus Eigennamen.

    Der Betreiber allein reicht nicht: bei Fachpressemeldungen ist das Feld
    oft leer, und gerade dort entstehen die Dubletten. Als Eigenname zaehlt
    ein grossgeschriebenes Wort, das nicht am Satzanfang steht - grob, aber
    es findet "Starlink", "Indosat", "Zayo" und "Nvidia" zuverlaessig.

    "Kandidaten", weil englische Schlagzeilen auch Verben grossschreiben.
    Welche davon wirklich unterscheiden, entscheidet die Seltenheitsrechnung
    in `gruppiere()`; `_KEIN_AKTEUR` faengt die haeufigsten Faelle schon hier.
    """
    namen = set()
    if item.operator:
        namen |= {_stamm(w) for w in _WORT.findall(item.operator.lower())
                  if len(w) >= 3 and w not in _STOPP}
    # Auch das erste Wort. Es sieht nach Satzanfang aus und ist in einer
    # Schlagzeile fast immer der Handelnde: "SpaceX small cell plan ...",
    # "Zayo teams with Nvidia ...", "Indosat launches ...". Solange es
    # uebersprungen wurde, verlor genau die Meldung ihren Akteur, die ihn am
    # deutlichsten nennt. Gegen deutsche Satzanfaenge schuetzen _STOPP und
    # _KEIN_AKTEUR, gegen alles Uebrige die Seltenheitsrechnung.
    worte = re.findall(r"[A-Za-zÄÖÜäöü][\w&.\-]+", item.title or "")
    for w in worte:
        if not w[0].isupper():
            continue
        klein = re.sub(r"[^a-z0-9äöüß]", "", w.lower())
        if len(klein) >= 3 and klein not in _STOPP:
            namen.add(_stamm(klein))
    return frozenset(n for n in namen if n not in _KEIN_AKTEUR)


def _seltene_akteure(kandidaten: list[frozenset[str]]) -> list[frozenset[str]]:
    """Behaelt je Meldung nur die Namen, die im Stapel selten sind.

    Dieselbe Rechnung wie beim roten Faden der Titelseite: ein Name, der in
    jeder achten Meldung steht, unterscheidet nichts. Ohne sie standen im
    Testlauf ueber die Ausgabe vom 07.08.2026 146 Paare im Graubereich - fast
    alle ueber Woerter wie "Networks", "Cloud" oder "Mobile" verbunden, die
    zufaellig grossgeschrieben in einer Schlagzeile standen.

    Die Grenze ist bewusst grosszuegig (ein Achtel, mindestens zwei): drei
    Meldungen ueber dasselbe Ereignis sollen ihren gemeinsamen Namen behalten
    duerfen, auch wenn sie zu dritt sind.
    """
    haeufigkeit: dict[str, int] = {}
    for menge in kandidaten:
        for name in menge:
            haeufigkeit[name] = haeufigkeit.get(name, 0) + 1
    deckel = max(3, len(kandidaten) // 8)
    return [frozenset(n for n in menge if haeufigkeit[n] <= deckel)
            for menge in kandidaten]


def _zeitlich_nah(a: Item, b: Item, stunden: int) -> bool:
    """Liegen zwei Meldungen im selben Zeitfenster?

    Undatierte Meldungen gelten als nah - sie tragen kein Alter, an dem sich
    etwas anderes feststellen liesse, und sie sind in DIESEM Lauf gesammelt
    worden. Die Sicherung gegen Folgeereignisse haengt damit an den datierten
    Meldungen, und das ist die richtige Aufteilung: eine undatierte Meldung
    ist ohnehin schon die schwaechere Quelle.
    """
    if a.published is None or b.published is None:
        return True
    pa, pb = a.published, b.published
    if pa.tzinfo is None:
        pa = pa.replace(tzinfo=timezone.utc)
    if pb.tzinfo is None:
        pb = pb.replace(tzinfo=timezone.utc)
    return abs(pa - pb) <= timedelta(hours=stunden)


def _urteil(a: _Profil, b: _Profil) -> tuple[str, float]:
    """("gleich" | "grau" | "verschieden", Aehnlichkeit) fuer ein Paar.

    Das Betreiberfeld schlaegt die Grossschreibung. Der Grund ist das
    Deutsche: dort steht JEDES Substantiv gross, "Tarif" und "Datenvolumen"
    landen also genauso in der Namensliste wie "Starlink". Bei 138 Meldungen
    faengt die Seltenheitsrechnung das ab, bei einer Handvoll nicht. Wo beide
    Meldungen einen Betreiber tragen - und das tut jede Meldung aus einem
    Betreiber-Newsroom -, entscheidet deshalb ausschliesslich dieses Feld:
    eine Vodafone-Meldung und eine Orange-Meldung sind nie dasselbe Ereignis,
    auch wenn beide Ueberschriften "startet neuen Tarif" lauten.
    """
    if a.betreiber and b.betreiber:
        if not (a.betreiber & b.betreiber):
            return "verschieden", 0.0
    elif not (a.akteure & b.akteure):
        return "verschieden", 0.0
    aehnlich = _jaccard(a.worte, b.worte)
    gemeinsame_zahl = bool(a.zahlen & b.zahlen)
    if aehnlich >= SCHWELLE_SICHER:
        return "gleich", aehnlich
    if gemeinsame_zahl and aehnlich >= SCHWELLE_MIT_ZAHL:
        return "gleich", aehnlich
    if aehnlich >= SCHWELLE_GRAU:
        return "grau", aehnlich
    return "verschieden", aehnlich


def _grau_rang(a: _Profil, b: _Profil, aehnlichkeit: float) -> float:
    """Wie aussichtsreich ein Zweifelsfall ist - danach wird der Deckel gesetzt.

    Nach reiner Wortaehnlichkeit zu sortieren waere falsch: die Paare, fuer
    die sich die Frage ans Modell ueberhaupt lohnt, sind gerade die
    sprachverschiedenen ("Disney+ annonce ..." / "Josh D'Amaro, CEO de
    Disney: ..."), und die teilen per Bauart wenig Woerter. Zwei gemeinsame
    seltene Namen oder eine gemeinsame Zahl wiegen deshalb schwerer als ein
    paar Prozentpunkte Wortdeckung.
    """
    zahl = 0.25 if (a.zahlen & b.zahlen) else 0.0
    namen = 0.10 * max(0, len(a.akteure & b.akteure) - 1)
    return aehnlichkeit + zahl + namen


@dataclass
class Gruppe:
    """Ein Ereignis mit allen Meldungen, die es berichten."""

    vertreter: Item
    mitglieder: list[Item] = field(default_factory=list)
    # Die seltenen Namen des Vertreters. Sie stehen hier, weil der Speicher
    # sie braucht: `zuordnen()` hat beim naechsten Lauf keinen Stapel mehr,
    # ueber den sich Seltenheit berechnen liesse.
    akteure: frozenset[str] = frozenset()

    @property
    def id(self) -> str:
        # Aus der kanonischen URL, nie aus dem Titel - siehe Modulkopf.
        return hashlib.sha256(
            normalize_url(self.vertreter.url).encode("utf-8")).hexdigest()[:16]

    @property
    def quellen(self) -> int:
        return 1 + len(self.mitglieder)

    def belege(self) -> list[dict]:
        """Die weiteren Quellen, wie sie unter der Meldung stehen."""
        return [{"source": m.source_name, "url": m.url, "title": m.title}
                for m in self.mitglieder]


_PRUEF_SYSTEM = """\
Du pruefst, ob zwei Nachrichtenmeldungen DASSELBE EREIGNIS beschreiben.

Dasselbe Ereignis heisst: dieselbe Ankuendigung, derselbe Vertrag, dieselbe
Zahl, derselbe Vorfall - nur von zwei Redaktionen berichtet, moeglicherweise
in verschiedenen Sprachen.

NICHT dasselbe Ereignis sind:
- zwei Schritte derselben Sache (Ankuendigung und Verkaufsstart)
- zwei Meldungen ueber dieselbe Firma zu verschiedenen Themen
- eine Meldung und ein Hintergrundstueck, das sie nur erwaehnt

Antworte mit NUR diesem JSON, ohne Markdown:
{"gleich": true oder false}

Im Zweifel false.
"""


def _frage_modell(a: Item, b: Item, model: str) -> bool:
    user = json.dumps({
        "A": {"titel": a.title, "quelle": a.source_name,
              "auszug": a.summary[:300]},
        "B": {"titel": b.title, "quelle": b.source_name,
              "auszug": b.summary[:300]},
    }, ensure_ascii=False)
    # 8000 ist die Untergrenze, die sich bewaehrt hat: ein kleineres Budget
    # sieht wie eine tote Quelle aus, weil ein denkendes Modell damit fertig
    # ist, bevor die Antwort anfaengt (Laeufe #83-85).
    roh = complete(_PRUEF_SYSTEM, user, model=model, max_tokens=16000)
    return bool(extract_json(roh).get("gleich"))


def _deckel(items: int, vorgabe: int | None) -> int:
    """Wie viele Zweifelsfaelle dieser Lauf ans Modell geben darf.

    Mit der Menge der Meldungen waechst auch die Zahl der Dubletten - ein
    fester Deckel waere an einem 642-Meldungen-Tag (06.08.2026) genau dort zu
    klein, wo er am meisten spart.
    """
    if vorgabe is not None:
        return max(0, vorgabe)
    return max(MAX_LLM_PRUEFUNGEN, min(120, items // 4))


def gruppiere(items: list[Item], *, model: str | None = None,
              use_llm: bool = False,
              zeitfenster_stunden: int = ZEITFENSTER_STUNDEN,
              max_llm_pruefungen: int | None = None) -> list[Gruppe]:
    """Fasst Meldungen zu Ereignis-Gruppen zusammen.

    Die Reihenfolge der Eingabe entscheidet, wer Vertreter wird: die erste
    Meldung eines Ereignisses fuehrt es an. Die Pipeline sortiert vorher nach
    Datum absteigend, der Vertreter ist damit die frischeste Meldung.

    Ohne `use_llm` laeuft nur der deterministische Vorfilter. Das ist kein
    Notbehelf, sondern der Normalfall fuer `--no-llm` und fuer jeden Test:
    die Faelle mit gemeinsamer Zahl (Indosat, Zayo, Starlink) faengt er alle.
    """
    gruppen: list[Gruppe] = []
    profile: list[_Profil] = []
    # (Rang, ZIELGRUPPE, Profil) - die Gruppe als OBJEKT, nicht als Index.
    #
    # Der Index war ein Fehler, und zwar einer, der nur mit Modell auftritt:
    # die Schleife unten loest zusammengelegte Gruppen mit `gruppen.pop(i)`
    # auf, und das verschiebt jeden gespeicherten Index oberhalb von i um
    # eins. Ein spaeterer Zweifelsfall zeigte danach auf die falsche Gruppe -
    # und wenn genug gepoppt war, ins Leere: Lauf #86 ist mit
    # "IndexError: list index out of range" gestorben, nachdem die Stufe
    # lokal nur mit `--no-llm` gelaufen war.
    grau: list[tuple[float, Gruppe, _Profil]] = []

    akteure = _seltene_akteure([akteur_kandidaten(i) for i in items])

    for item, namen in zip(items, akteure):
        p = _Profil.von(item, akteure=namen)
        bestes: tuple[float, int] | None = None
        graubester: tuple[float, int] | None = None
        for idx, g in enumerate(gruppen):
            if len(g.mitglieder) + 1 >= MAX_MITGLIEDER:
                continue
            if not _zeitlich_nah(g.vertreter, item, zeitfenster_stunden):
                continue
            urteil, wert = _urteil(profile[idx], p)
            if urteil == "gleich" and (bestes is None or wert > bestes[0]):
                bestes = (wert, idx)
            elif urteil == "grau" and (graubester is None or wert > graubester[0]):
                graubester = (wert, idx)
        if bestes is not None:
            gruppen[bestes[1]].mitglieder.append(item)
            continue
        if graubester is not None:
            grau.append((_grau_rang(profile[graubester[1]], p, graubester[0]),
                         gruppen[graubester[1]], p))
        gruppen.append(Gruppe(vertreter=item, akteure=namen))
        profile.append(p)

    if use_llm and model and grau:
        # Die aussichtsreichsten Zweifelsfaelle zuerst - der Deckel schneidet
        # dann die schwaechsten ab, nicht die zufaellig letzten.
        grau.sort(key=lambda t: -t[0])
        zusammengelegt = 0
        gefragt = 0
        for wert, ziel, p in grau[:_deckel(len(items), max_llm_pruefungen)]:
            # Die Zielgruppe kann in einer frueheren Runde selbst aufgeloest
            # und in eine andere gehaengt worden sein. Dann ist sie kein
            # gueltiges Ziel mehr - ihr etwas anzuhaengen hiesse, es in eine
            # Gruppe zu legen, die niemand mehr zurueckgibt.
            if not any(g is ziel for g in gruppen):
                continue
            if len(ziel.mitglieder) + 1 >= MAX_MITGLIEDER:
                continue
            try:
                gefragt += 1
                if not _frage_modell(ziel.vertreter, p.item, model):
                    continue
            except (ValueError, RuntimeError, KeyError) as exc:
                log.warning("Ereignis-Pruefung fehlgeschlagen (%s) - die "
                            "beiden Meldungen bleiben getrennt", str(exc)[:120])
                continue
            # Der Zweifelsfall hat oben eine eigene Gruppe bekommen; die wird
            # jetzt aufgeloest und ihr Inhalt umgehaengt.
            for i, g in enumerate(gruppen):
                if g.vertreter.id == p.item.id:
                    ziel.mitglieder.append(g.vertreter)
                    ziel.mitglieder.extend(g.mitglieder)
                    gruppen.pop(i)
                    profile.pop(i)
                    zusammengelegt += 1
                    break
        log.info("Ereignis-Pruefung: %d Zweifelsfaelle gefragt, %d zusammengelegt",
                 gefragt, zusammengelegt)

    return gruppen


class ClusterStore:
    """Gedaechtnis der Ereignisse ueber die Laeufe hinweg.

    Zweck ist NICHT das Unterdruecken: eine Meldung, die ein bereits
    berichtetes Ereignis nachtraeglich aufgreift, wird der bestehenden Gruppe
    zugeschlagen, statt als eigene Meldung ein zweites Mal auf der Titelseite
    zu landen. Ausserhalb des Zeitfensters passiert das nicht - eine
    Entwicklung drei Tage spaeter ist eine neue Nachricht, kein Nachklapp.

    Zeilenweise und append-only wie der Seen-Store, damit git nur den
    angehaengten Block speichert. Beim Laden gewinnt die letzte Zeile je ID.
    """

    def __init__(self, path: Path, max_alter_tage: int = 14):
        self.path = path
        self.max_alter_tage = max_alter_tage
        self.cluster: dict[str, dict] = {}
        if path.exists():
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("cluster_id"):
                        self.cluster[rec["cluster_id"]] = rec

    def __len__(self) -> int:
        return len(self.cluster)

    def _frisch(self, heute: datetime) -> list[dict]:
        grenze = heute - timedelta(days=self.max_alter_tage)
        out = []
        for rec in self.cluster.values():
            try:
                letztes = datetime.fromisoformat(rec.get("letztes_datum") or "")
            except ValueError:
                continue
            if letztes.tzinfo is None:
                letztes = letztes.replace(tzinfo=timezone.utc)
            if letztes >= grenze:
                out.append(rec)
        return out

    def merke(self, gruppen: list[Gruppe], heute: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        neu_angelegt = not self.path.exists() or self.path.stat().st_size == 0
        with open(self.path, "a", encoding="utf-8") as fh:
            if neu_angelegt:
                fh.write("# telco-radar Ereignis-Cluster - eine Gruppe je Zeile\n")
            for g in gruppen:
                alt = self.cluster.get(g.id) or {}
                mitglieder = sorted(set(
                    (alt.get("member_urls") or [])
                    + [normalize_url(m.url) for m in g.mitglieder]))
                rec = {
                    "cluster_id": g.id,
                    "canonical_url": normalize_url(g.vertreter.url),
                    "canonical_title": g.vertreter.title[:200],
                    "member_urls": mitglieder,
                    "akteure": sorted(g.akteure or akteur_kandidaten(g.vertreter))[:8],
                    "erstes_datum": alt.get("erstes_datum") or heute,
                    "letztes_datum": heute,
                    "quellenzahl": 1 + len(mitglieder),
                }
                self.cluster[g.id] = rec
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def zuordnen(self, item: Item, heute: datetime,
                 zeitfenster_stunden: int = ZEITFENSTER_STUNDEN) -> str | None:
        """Gehoert diese Meldung zu einem Ereignis aus einem frueheren Lauf?

        Gleiche Pruefung wie im Lauf selbst, nur gegen den gespeicherten
        Vertreter: gemeinsamer Akteur und Wortaehnlichkeit ueber der sicheren
        Schwelle. Der Graubereich bleibt hier aussen vor - ein Modellaufruf
        gegen einen gespeicherten Titel ohne Zusammenfassung waere geraten.
        """
        p = _Profil.von(item)
        grenze = heute - timedelta(hours=zeitfenster_stunden)
        for rec in self._frisch(heute):
            try:
                letztes = datetime.fromisoformat(rec.get("letztes_datum") or "")
            except ValueError:
                continue
            if letztes.tzinfo is None:
                letztes = letztes.replace(tzinfo=timezone.utc)
            if letztes < grenze:
                continue
            akteure = frozenset(rec.get("akteure") or [])
            if not (akteure & p.akteure):
                continue
            if _jaccard(wortmenge(rec.get("canonical_title") or ""),
                        p.worte) >= SCHWELLE_SICHER:
                return rec["cluster_id"]
        return None
