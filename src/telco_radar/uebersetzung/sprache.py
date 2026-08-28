"""Spracherkennung - und vor allem: wann sie sich enthaelt.

Die eine Regel, die dieses Modul traegt: **gemessen wird auf dem laengsten
verfuegbaren Text, nie auf der Ueberschrift.** Am 13.08.2026 gegen das
Berichtsarchiv gemessen (810 Meldungen, nur Titel verfuegbar) ergab die
Titelmessung 23,2 % fremdsprachig - und war Ausschuss:

    it  Airtel Africa hires more investment banks for mobile money IPO
    fr  AT&T, Ericsson demonstrate drone-sensing 5G capabilities
    es  CMA clears Paramount-WBD deal

Alle drei sind englisch. Eine Ueberschrift ist kurz und besteht
groesstenteils aus Eigennamen; darauf raet jede Erkennung. Auf Titel plus
echtem Teaser gemessen fiel derselbe Bestand auf 15,2 %, und ueber zwoelf
per Artikelabruf gepruefte Faelle stimmte die Teasersprache in ALLEN zwoelf
mit der Sprache des Volltexts ueberein.

Zweite Regel: **ein Grenzfall wird verworfen, nicht geraten.** Lieber kein
roter Link als einer an einem englischen Artikel - eine Funktion, die
sichtbar danebenliegt, ist schlimmer als eine, die seltener erscheint.
"""
from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

# Sprachen, fuer die es KEINE Uebersetzung gibt: nur noch die Zielsprache
# selbst. Bis zum 27.08.2026 stand hier auch "en" - mit der Annahme, das
# Zielpublikum lese Englisch ohnehin. Gemessen am Lauf vom 27.08.2026 waren
# 143 von 163 vorgefilterten Meldungen englisch; die Zielgruppe (deutsche
# Manager ohne sicheres Englisch, siehe CLAUDE.md §1) ist damit falsch
# geschnitten. Englisch ist jetzt eine Fremdsprache wie jede andere.
MUTTERSPRACHEN = frozenset({"de"})

# Unter so vielen Zeichen wird gar nicht erst gemessen. py3langid liefert
# auch fuer drei Woerter ein Ergebnis - nur eben ein geratenes.
MINDESTZEICHEN = 200

# Wie sicher sich die Erkennung sein muss. py3langid gibt ein normalisiertes
# Mass zwischen 0 und 1 zurueck; darunter gilt der Text als unbestimmt.
MINDESTSICHERHEIT = 0.90

# Anzeigenamen der Sprachen, die in den Messungen vom 13.08.2026 wirklich
# vorkamen, plus die naheliegenden Nachbarn. Eine unbekannte Sprache
# bekommt ihr Kuerzel als Namen - das ist haesslich, aber ehrlich, und es
# faellt beim Lesen der Seite sofort auf.
# Die Liste traegt zwei Saetze auf jeder Uebersetzungsseite ("Maschinelle
# Uebersetzung aus dem ...") UND die Sprachangabe an der Meldungskarte. Ein
# fehlender Code faellt deshalb nicht aus, sondern erscheint als Kuerzel in
# Grossbuchstaben - "aus dem EN".
#
# Genau das war bis zum 27.08.2026 der Regelfall: "en" und "de" fehlten,
# obwohl Englisch die mit Abstand haeufigste Ausgangssprache des Bestands ist
# (die Sprachpruefung laesst eine englische Meldung nur dann bis hierher
# durch, wenn der Leser eine deutsche Fassung bekommt). Ein Code, der nie
# uebersetzt wird, gehoert trotzdem hier hinein: die Namen werden auch fuer
# die reine ANZEIGE der erkannten Sprache gebraucht.
SPRACHNAMEN = {
    "ar": "Arabisch", "bg": "Bulgarisch", "cs": "Tschechisch",
    "da": "Dänisch", "de": "Deutsch", "el": "Griechisch", "en": "Englisch",
    "es": "Spanisch",
    "et": "Estnisch", "fa": "Persisch", "fi": "Finnisch",
    "fr": "Französisch", "he": "Hebräisch", "hi": "Hindi",
    "hr": "Kroatisch", "hu": "Ungarisch", "id": "Indonesisch",
    "it": "Italienisch", "ja": "Japanisch", "ko": "Koreanisch",
    "lt": "Litauisch", "lv": "Lettisch", "ms": "Malaiisch",
    "nb": "Norwegisch", "nl": "Niederländisch", "nn": "Norwegisch",
    "no": "Norwegisch", "pl": "Polnisch", "pt": "Portugiesisch",
    "ro": "Rumänisch", "ru": "Russisch", "sk": "Slowakisch",
    "sl": "Slowenisch", "sr": "Serbisch", "sv": "Schwedisch",
    "th": "Thai", "tr": "Türkisch", "uk": "Ukrainisch",
    "vi": "Vietnamesisch", "zh": "Chinesisch",
}

_MEHRFACH_LEER = re.compile(r"\s+")


def sprachname(code: str) -> str:
    return SPRACHNAMEN.get((code or "").lower(), (code or "").upper())


def sprachname_dativ(code: str) -> str:
    """Die Form, die nach "aus dem" steht.

    "aus dem Spanisch" ist falsch, "aus dem Spanischen" richtig - und der
    Satz steht auf jeder Uebersetzungsseite zweimal. Die Regel ist einfach,
    weil die Sprachnamen es sind: was auf -isch endet, bekommt ein -en
    (Spanisch -> Spanischen, Tuerkisch -> Tuerkischen). Alles andere bleibt,
    wie es ist - "aus dem Hindi" und "aus dem Thai" sind bereits richtig.
    """
    name = sprachname(code)
    return name + "en" if name.endswith("isch") else name


_ERKENNER = None
_ERKENNER_GEPRUEFT = False


def _langid():
    """Der Erkenner mit NORMALISIERTEN Wahrscheinlichkeiten, oder None.

    `py3langid.classify()` gibt eine Log-Wahrscheinlichkeit zurueck (Werte
    wie -53 oder +5), keinen Anteil zwischen 0 und 1. Eine Schwelle wie
    `< 0.90` waere darauf sinnlos: sie wuerde fast alles durchlassen und
    gelegentlich alles verwerfen, je nach Textlaenge. Nur die Instanz mit
    `norm_probs=True` liefert das Mass, das MINDESTSICHERHEIT meint.

    Die Stufe faellt ohne die Bibliothek geschlossen aus: keine Erkennung
    heisst keine Uebersetzung, nicht "alles uebersetzen".
    """
    global _ERKENNER, _ERKENNER_GEPRUEFT
    if _ERKENNER_GEPRUEFT:
        return _ERKENNER
    _ERKENNER_GEPRUEFT = True
    try:
        from py3langid.langid import LanguageIdentifier, MODEL_FILE
        _ERKENNER = LanguageIdentifier.from_pickled_model(
            MODEL_FILE, norm_probs=True)
    except Exception:  # noqa: BLE001 - fehlende Bibliothek ODER Modelldatei
        _ERKENNER = None
    return _ERKENNER


def erkenne_sprache(text: str, titel: str = "") -> tuple[str, float]:
    """(Sprachkuerzel, Sicherheit) - oder ("", 0.0), wenn unbestimmt.

    `titel` wird dem Text nur VORANGESTELLT, wenn es ohnehin genug Text
    gibt. Er ist nie die Grundlage der Messung, sondern hoechstens ihr
    Anfang - siehe Modulkopf.
    """
    text = _MEHRFACH_LEER.sub(" ", text or "").strip()
    if len(text) < MINDESTZEICHEN:
        return "", 0.0
    erkenner = _langid()
    if erkenner is None:
        log.warning("py3langid ist nicht verfuegbar - die Spracherkennung "
                    "enthaelt sich, es wird nichts uebersetzt.")
        return "", 0.0
    probe = f"{titel.strip()}. {text}" if titel.strip() else text
    try:
        kuerzel, wert = erkenner.classify(probe[:4000])
    except Exception as exc:  # noqa: BLE001 - eine Bibliothek darf den Lauf nicht kosten
        log.warning("Spracherkennung fehlgeschlagen: %s", exc)
        return "", 0.0
    sicherheit = float(wert)
    if sicherheit < MINDESTSICHERHEIT:
        return "", sicherheit
    return str(kuerzel).lower(), sicherheit


def ist_fremdsprachig(text: str, titel: str = "") -> tuple[bool, str, float]:
    """(ja/nein, Kuerzel, Sicherheit).

    "Nein" hat zwei verschiedene Bedeutungen, und beide fuehren zum selben
    Ergebnis - kein Link: der Text ist deutsch oder englisch, ODER die
    Erkennung war sich nicht sicher genug.
    """
    kuerzel, sicherheit = erkenne_sprache(text, titel)
    if not kuerzel or kuerzel in MUTTERSPRACHEN:
        return False, kuerzel, sicherheit
    return True, kuerzel, sicherheit
