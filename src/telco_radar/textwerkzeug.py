"""Textwerkzeuge, die Anzeige UND Analyse teilen.

Zwei Stellen im Projekt rechnen dasselbe aus, und beide muessen es gleich
ausrechnen:

  * `report/html._faden()` sucht zu jedem Fuehrungssatz des Wochenberichts
    die Meldung, die ihn belegt.
  * `analyze/highlight_topics` sucht Gruppen von Meldungen, die dasselbe
    Ereignis beschreiben.

Beide beantworten die Frage "reden diese zwei Texte von derselben Sache?",
und beide beantworten sie ueber SELTENE gemeinsame Woerter. Ein Abgleich
ueber alle Woerter faende "Netz", "Kunden" und "Milliarden" in jeder zweiten
Meldung; gezaehlt reicht auch nicht, GEWICHTET muss es sein - ein Wort, das
genau zweimal vorkommt, beweist mehr als eines, das siebzehnmal vorkommt.
Deshalb 1/Haeufigkeit (die ausfuehrliche Begruendung mit dem gemessenen
Fehlgriff steht bei `_faden()`).

Der Slug steht aus demselben Grund hier: die Berichtsabschnitte
(`_anchor_headings`) und die Themenseiten (`site/thema/<slug>.html`) muessen
denselben Anker aus demselben Titel erzeugen - zwei Fassungen davon waeren
zwei Fassungen der URLs, die in Mails stehen.

Und aus demselben Grund die Redaktionsregel **"beobachtend statt
empfehlend"**: die Website berichtet, sie beraet nicht (CLAUDE.md §8). Drei
Stellen setzen sie durch, jede mit einer eigenen ANTWORT, aber alle mit
demselben Handwerkszeug (Satztrenner, Abkuerzungsschutz, Vodafone-Muster):

  * `report/html._strip_vodafone_advice` - der Wochenbericht, satzweise.
  * `ohne_vodafone_teil()` - die Notiz der Wettbewerbsseite. Dort verlangt
    der Prompt "the angle for Vodafone" im selben Satz, also faellt JEDE
    Vodafone-Haelfte, auch eine beobachtende.
  * `ohne_vodafone_rat()` - die Begruendungszeile der Differenzierungs-
    Karten. Dort ist der Vodafone-Bezug oft der Befund selbst ("Dies ist ein
    massiver Schlag gegen Vodafone"), also faellt nur, was wirklich raet.

Die drei Antworten sind absichtlich verschieden; das Handwerkszeug ist es
nicht mehr.
"""
from __future__ import annotations

import re

_SLUG_MAP = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
                           "Ä": "ae", "Ö": "oe", "Ü": "ue"})

# Vier Zeichen Mindestlaenge: kuerzer sind im Deutschen fast nur Fuellwoerter
# ("der", "und", "mit"), und die traegt der Haeufigkeitsdeckel ohnehin aus.
WORT_RE = re.compile(r"[\wÄÖÜäöüß][\wÄÖÜäöüß-]{3,}")


def slug(text: str) -> str:
    """Stabiler Anker aus einer Ueberschrift ("Afrika & Naher Osten" ->
    "afrika-naher-osten"). Muss ueber Laeufe hinweg gleich bleiben - die
    Anker landen in Mails."""
    s = (text or "").strip().lower().translate(_SLUG_MAP)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "abschnitt"


def wortmenge(text: str) -> set[str]:
    """Die inhaltstragenden Woerter eines Textes, kleingeschrieben."""
    return {w.lower() for w in WORT_RE.findall(text or "")}


def haeufigkeiten(mengen) -> dict[str, int]:
    """Wie oft jedes Wort in wie vielen der Wortmengen vorkommt."""
    zaehler: dict[str, int] = {}
    for menge in mengen:
        for w in menge:
            zaehler[w] = zaehler.get(w, 0) + 1
    return zaehler


def gewicht(woerter, haeufigkeit: dict[str, int]) -> float:
    """Beweiskraft gemeinsamer Woerter: jeder Treffer zaehlt 1/Haeufigkeit."""
    return round(sum(1.0 / haeufigkeit[w] for w in woerter if haeufigkeit.get(w)), 6)


# ============================================  Begriffe an Wortgrenzen  ====
# Vier Stellen im Projekt suchen einen Begriff im Fliesstext - die CTM-Linse
# (Heimatmarkt-Marken), das Fruehwarn-Board (Indikatoren), die
# Wettbewerbsseite (Aliase) und seit dem 11.08.2026 die Newsletter-Filter
# (Stichwoerter der Abonnenten). Alle vier brauchen dieselbe Antwort auf
# dieselbe Frage, und die Frage ist im Deutschen nicht trivial:
#
#   * "Netzausbau" MUSS in "Glasfaser-Netzausbau" treffen. Ein Bindestrich
#     ist kein Wortzeichen, `(?<!\w)` laesst ihn also von selbst durch.
#   * "Netz" darf NICHT in "Netzwerkkarte" untergehen. Rechts steht ein
#     Wortzeichen, `(?!\w)` verhindert den Treffer.
#   * "spark" darf nicht in "Sparkasse", "globe" nicht in "Globetrotter",
#     "orange" nicht in "Orangensaft" treffen - dieselbe rechte Grenze.
#
# Was diese Regel BEWUSST nicht kann: die deutsche Beugung. "Netzausbaus"
# (Genitiv) trifft nicht. Eine optionale Endung `s|es|n|en` waere schnell
# geschrieben und faengt sich sofort einen neuen Falschtreffer ein -
# "Orange" + "n" ist "Orangen". Erst messen, dann verschaerfen.
#
# `kein_punkt_davor` blendet zusaetzlich Domainnamen aus: ohne das trifft
# "o2" auch in "example.o2" und die Marke steht in jeder Fussnote.

def begriffs_muster(begriffe, *, kein_punkt_davor: bool = False):
    """Ein Muster, das JEDEN der Begriffe an Wortgrenzen findet - oder None.

    Der laengste Begriff steht vorn: bei alternativen Zweigen nimmt die
    Regex-Maschine den ERSTEN passenden, und "Telekom" vor "Deutsche Telekom"
    wuerde die Gruppe auf das kuerzere Ergebnis festlegen.
    """
    teile = [re.escape(b.strip()) for b in (begriffe or []) if (b or "").strip()]
    if not teile:
        return None
    teile.sort(key=len, reverse=True)
    davor = r"(?<![\w.])" if kein_punkt_davor else r"(?<!\w)"
    return re.compile(davor + "(" + "|".join(teile) + r")(?!\w)", re.I)


# ======================================  beobachtend statt empfehlend  ====
# Abkuerzungen, deren Punkt kein Satzende ist. Ohne diesen Schutz zerlegt der
# Satztrenner "z. B. Vodafone kann ..." in zwei Teile und wirft den halben
# Satz weg.
ABKUERZUNGEN = ("z. B.", "z.B.", "d. h.", "d.h.", "u. a.", "u.a.", "u. Ä.",
                "bzw.", "ca.", "ggf.", "inkl.", "Mio.", "Mrd.", "Nr.",
                "Abb.", "evtl.", "sog.", "Prof.", "Dr.")
_SATZ_GRENZE = re.compile(r"(?<=[.!?])\s+(?=[«\"„*\[(A-ZÄÖÜ])")
# Trennzeichen INNERHALB eines Satzes. Ein deutscher Analystensatz stellt
# Befund und Folgerung regelmaessig so gegenueber: "Telkomsel macht seine App
# zur Content-Plattform – ein Trend, den Vodafone beobachten sollte."
_KLAUSEL = re.compile(r"\s*([–—;:])\s+")
# "Vodafone" als eigenes Wort. Der Blick nach LINKS ist der Punkt: er haelt
# "MeinVodafone" heraus (ein Produktname, kein Adressat).
NENNT_VODAFONE = re.compile(r"(?<!\w)vodafone", re.I)
# Wem ein Rat gilt. Neben Vodafone auch das Wir der eigenen Redaktion - im
# Bestand steht "Wir sollten prüfen, ob wir mit anderen Anbietern gemeinsame
# Warnsysteme etablieren", und das ist derselbe Fehler in der ersten Person.
_ADRESSAT = re.compile(r"(?<!\w)(?:vodafones?|wir|uns|unser\w*)(?!\w)", re.I)
# Verben, die man EMPFIEHLT. Bewusst nur die Grundform: "Vodafone bündelt
# bislang nur lose Add-ons" ist eine Feststellung, "bündeln" waere ein Rat.
_RAT_VERBEN = re.compile(
    r"(?<!\w)(?:pr(?:ü|ue)fen|bewerten|evaluieren|erw(?:ä|ae)gen|adaptieren|"
    r"kopieren|(?:ü|ue)bertragen|nachziehen|gegenhalten|kontern|"
    r"einf(?:ü|ue)hren|aufwerten|vermarkten|schn(?:ü|ue)ren|b(?:ü|ue)ndeln|"
    r"beobachten|anpassen|ausrichten|positionieren|nutzen|setzen|aufbauen|"
    r"schaffen|erg(?:ä|ae)nzen)(?!\w)", re.I)
# "Vorlage fuer Vodafone: ..." raet, ohne ein Verb zu brauchen - alle vier
# Faelle im Bestand vom 08.08.2026 haben genau diese Form. Bewusst NICHT das
# blosse "für Vodafone" (so steht es in `_ADVICE_PHRASES` des Wochenberichts):
# "für Vodafone entsteht Druck" ist eine Folge, kein Rat.
_RAT_MARKER = re.compile(
    r"(?<!\w)(?:vorlage|vorbild|modell|blaupause|anregung|impuls|lehre)"
    r"\W+f(?:ü|ue)r\W+vodafones?(?!\w)", re.I)
# Der deutsche Telegrammstil einer Empfehlung: der Satz endet auf dem blossen
# Infinitiv ("Eigene Vodafone-Familie – das Mini-App-Modell nach Europa
# übertragen."). Kein Teilsatz traegt hier Vodafone UND Verb, die Empfehlung
# steht ueber die Trennstelle hinweg.
_RAT_SCHLUSS = re.compile(_RAT_VERBEN.pattern + r"\s*[.!?]?$", re.I)
# Trennzeichen der Wettbewerber-Notiz. Anders als `_KLAUSEL`: ohne
# Doppelpunkt, dafuer mit dem freistehenden Bindestrich ("an - Vodafone") -
# ein Bindestrich ohne Leerzeichen ist keiner ("Wi-Fi-7-Router").
_NOTIZ_TRENNER = re.compile(r"\s*[;–—]\s+|\s+-\s+")


def _geschuetzt(text: str) -> str:
    for i, abk in enumerate(ABKUERZUNGEN):
        text = text.replace(abk, f"\x00{i}\x00")
    return text


def _entschuetzt(text: str) -> str:
    for i, abk in enumerate(ABKUERZUNGEN):
        text = text.replace(f"\x00{i}\x00", abk)
    return text


def saetze(text: str) -> list[str]:
    """Ein Text in seine Saetze, ohne an Abkuerzungen zu zerbrechen."""
    return [_entschuetzt(s) for s in _SATZ_GRENZE.split(_geschuetzt(text or ""))]


def ist_vodafone_rat(teil: str) -> bool:
    """Raet dieser Teilsatz Vodafone etwas - statt etwas zu berichten?

    Beides muss zusammenkommen: der Adressat UND eine Handlung, die man
    empfiehlt. "Vodafone-Afrika-Gesellschaften könnten Marktanteile
    verlieren" nennt Vodafone und ist trotzdem eine Beobachtung; "Vodafone
    sollte prüfen, ob ..." ist es nicht.
    """
    if not _ADRESSAT.search(teil or ""):
        return False
    return bool(_RAT_VERBEN.search(teil) or _RAT_MARKER.search(teil))


def _wieder_zusammen(teile: list[str], trenner: list[str],
                     behalten: list[int]) -> str:
    """Die behaltenen Teilsaetze wieder zu einem Satz.

    Standen sie im Original nebeneinander, bleibt ihr Trennzeichen stehen.
    Ist dazwischen einer weggefallen, beginnt ein neuer Satz - sonst
    entstuende aus zwei Bruchstuecken ein grammatisch falscher.
    """
    text = ""
    vorher = None
    for i in behalten:
        stueck = teile[i].strip()
        if not stueck:
            continue
        if not text:
            # Ein Teilsatz, dem sein Anfang fehlt, ergibt keinen Satz. Nur der
            # erste Teil darf immer stehen; jeder spaetere muss selbst gross
            # anfangen oder hinter einem Doppelpunkt stehen - der kuendigt im
            # Deutschen eine vollstaendige Aussage an. Ohne diese Bedingung
            # blieb von "..., ob ein Produkt - etwa ueber die Vodacom-Gruppe -
            # schnell umsetzbar ist" die Mitte uebrig.
            if i and not (stueck[:1].isupper() or stueck[:1].isdigit()
                          or trenner[i - 1] == ":"):
                continue
            text = stueck[:1].upper() + stueck[1:] if i else stueck
        elif vorher == i - 1:
            zeichen = trenner[i - 1]
            text += (f"{zeichen} {stueck}" if zeichen in ";:"
                     else f" {zeichen} {stueck}")
        else:
            if not text.endswith((".", "!", "?")):
                text = text.rstrip(" ,;:–—") + "."
            text += " " + stueck[:1].upper() + stueck[1:]
        vorher = i
    return text


def ohne_vodafone_rat(text: str) -> str:
    """Der Text ohne die Vodafone-Ratschlaege - satz- und satzteilgenau.

    Gemessen am Bestand vom 08.08.2026 nennen 30 der 71 Karten Vodafone, und
    die Haelfte davon berichtet dabei etwas: "Dies ist ein massiver Schlag
    gegen Vodafone im deutschen TV-Markt", "Vodafone bündelt bislang nur lose
    Add-ons". Wer jeden Vodafone-Satz streicht (so macht es die
    Wettbewerbsseite, aus gutem Grund - siehe `ohne_vodafone_teil`), nimmt
    hier den Befund mit.

    Bleibt nichts Beobachtendes uebrig, kommt "" zurueck; die Karte steht
    dann ohne Zweitzeile. Eine leere Zeile ist besser als eine Empfehlung.
    """
    text = " ".join((text or "").split())
    if not _ADRESSAT.search(text):
        return text
    behalten_saetze = []
    for satz in saetze(text):
        stuecke = _KLAUSEL.split(satz)
        teile, trenner = stuecke[0::2], stuecke[1::2]
        behalten = [i for i, t in enumerate(teile) if not ist_vodafone_rat(t)]
        rest = _wieder_zusammen(teile, trenner, behalten)
        if not rest:
            continue
        # Der Telegrammstil-Rat ueberlebt die Teilsatz-Pruefung, weil er
        # Adressat und Verb auf zwei Teilsaetze verteilt.
        if _ADRESSAT.search(rest) and _RAT_SCHLUSS.search(rest):
            continue
        if not rest.endswith((".", "!", "?", ")", "\"", "“")):
            rest += "."
        behalten_saetze.append(rest)
    return " ".join(behalten_saetze).strip()


def ohne_vodafone_teil(note: str) -> str:
    """Die Notiz der Wettbewerbsseite ohne ihren Vodafone-Teil.

    Strenger als `ohne_vodafone_rat`, und das ist Absicht: der
    Wettbewerber-Prompt verlangt ausdruecklich "what it is and the angle for
    Vodafone" in EINEM Satz, und 82 von 170 Notizen im Archiv nennen
    Vodafone. Was dort hinter der Trennstelle steht, IST der Rat - auch wenn
    es sich als Beobachtung liest ("für Vodafone entsteht Druck").
    Satzweise streichen wuerde die Notiz komplett verwerfen, mitsamt dem
    Befund.

    Steht Vodafone nur hinten, faellt das Hintere weg. Steht der Name auch
    vorn oder gibt es keine Trennstelle, faellt die ganze Notiz - lieber
    keine Einordnung als eine Empfehlung auf einer beobachtenden Seite.
    """
    text = " ".join((note or "").split())
    if "vodafone" not in text.lower():
        return text
    teile = _NOTIZ_TRENNER.split(text)
    kopf = teile[0].strip(" ,;–—-")
    if len(teile) > 1 and "vodafone" not in kopf.lower():
        return kopf if kopf.endswith((".", "!", "?")) else kopf + "."
    return ""
