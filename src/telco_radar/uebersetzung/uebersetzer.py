"""Der Modellaufruf - in Abschnitten, mit erhaltenen Absaetzen.

Zwei Dinge unterscheiden diese Stufe von den anderen LLM-Stufen des
Projekts:

1. **Sie gibt keine JSON-Struktur zurueck, sondern Text.** Also gibt es
   auch keinen `json.loads`, der einen leeren String meldet - der Ausfall
   sieht anders aus und muss anders erkannt werden (siehe `_pruefe`).
2. **Sie darf nichts weglassen.** Der Auftrag lautet vollstaendige
   Uebersetzung, nicht Zusammenfassung. Ein Modell, das aus 8000 Zeichen
   1200 macht, hat zusammengefasst - das wird gemessen und verworfen.

Das Token-Budget steht bei 8000 je Abschnitt. Das ist die Untergrenze, die
sich in diesem Projekt bewaehrt hat: die Laeufe #83-85 verloren 15 von 19
Promo-Seiten an Budgets von 1800 bis 3200, weil das Modell seine Denkspur
mitrechnet und fertig ist, bevor die Antwort anfaengt.
"""
from __future__ import annotations

import logging
import re

from ..analyze import llm
from .sprache import sprachname

log = logging.getLogger(__name__)

MAX_TOKENS = 8000

# Wie viele Zeichen Original in EINEN Modellaufruf gehen. Konservativ
# gerechnet: deutscher Text ist rund 15 % laenger als englischer oder
# spanischer, und 6000 Zeichen Original passen mit ihrer Uebersetzung
# bequem in 8000 Tokens.
ABSCHNITT_ZEICHEN = 6000

# Unter diesem Anteil der Originallaenge gilt die Antwort als Zusammen-
# fassung und nicht als Uebersetzung. Deutsch ist eher laenger als kuerzer
# als die Ausgangssprachen dieses Bestands; 55 % lassen Luft fuer eine
# knappe Sprache, schlagen aber bei einer echten Kuerzung an.
MINDESTANTEIL = 0.55

SYSTEM = """Du uebersetzt Nachrichtentexte aus der Telekommunikationsbranche \
ins Deutsche.

Regeln:
- Uebersetze VOLLSTAENDIG. Kein Absatz wird weggelassen, nichts wird \
zusammengefasst, nichts gekuerzt.
- Uebersetze sinngemaess und gut lesbar, nicht woertlich verkrampft.
- Eigennamen, Produktnamen, Tarifnamen und technische Kuerzel bleiben \
unveraendert stehen (Beispiele: Starlink, MagentaTV, eSIM, 5G-SA, RAN, MVNO).
- Waehrungen, Zahlen und Datumsangaben bleiben inhaltlich exakt. Rechne \
keine Betraege um.
- Absatzgrenzen bleiben erhalten: ein Absatz des Originals ist ein Absatz \
der Uebersetzung.
- Ton: sachlich und nuechtern, verstaendlich fuer Fach- und Fuehrungskraefte \
OHNE technischen Hintergrund.
- Gib AUSSCHLIESSLICH die Uebersetzung aus. Keine Vorrede, keine Anmerkung, \
keine Erklaerung, keine Anfuehrungszeichen um den Text."""

TITEL_SYSTEM = """Du uebersetzt Ueberschriften aus der \
Telekommunikationsbranche ins Deutsche.

Gib AUSSCHLIESSLICH die uebersetzte Ueberschrift aus - eine Zeile, ohne \
Anfuehrungszeichen, ohne Vorrede, ohne abschliessenden Punkt. Eigennamen und \
Produktnamen bleiben stehen."""


class UebersetzungFehlgeschlagen(RuntimeError):
    """Die Uebersetzung ist ausgefallen.

    Eigene Klasse, damit ein Ausfall nicht wie "nichts zu tun" aussieht -
    dieselbe Lehre wie bei `PromoExtractionError`: `extract_promos` gab
    fuer beides `[]` zurueck, und eine laufende Aktion verschwand als
    "ausgelaufen".
    """


_ABSATZ = re.compile(r"\n\s*\n")
# Vorreden, die Modelle trotz klarer Anweisung gelegentlich voranstellen.
_VORREDE = re.compile(
    r"^\s*(hier ist|hier die|uebersetzung|übersetzung|translation)\b[^\n]{0,60}?:\s*",
    re.I)


def absaetze(text: str) -> list[str]:
    """Text in Absaetze zerlegen - Leerzeilen zuerst, sonst Zeilenumbrueche."""
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        return []
    teile = [t.strip() for t in _ABSATZ.split(text) if t.strip()]
    if len(teile) <= 1:
        teile = [t.strip() for t in text.split("\n") if t.strip()]
    return teile


def _abschnitte(teile: list[str]) -> list[list[str]]:
    """Absaetze zu Modellaufrufen buendeln, ohne einen Absatz zu zerreissen.

    Ein Absatz, der fuer sich allein zu gross ist, bleibt trotzdem ganz:
    ihn mitten im Satz zu schneiden kostet dem Modell den Zusammenhang,
    und die Naht waere im Ergebnis zu lesen.
    """
    gebuendelt: list[list[str]] = []
    aktuell: list[str] = []
    laenge = 0
    for absatz in teile:
        if aktuell and laenge + len(absatz) > ABSCHNITT_ZEICHEN:
            gebuendelt.append(aktuell)
            aktuell, laenge = [], 0
        aktuell.append(absatz)
        laenge += len(absatz)
    if aktuell:
        gebuendelt.append(aktuell)
    return gebuendelt


def _saeubern(antwort: str) -> str:
    return _VORREDE.sub("", (antwort or "").strip()).strip()


def _pruefe(original: str, deutsch: str) -> None:
    if not deutsch:
        raise UebersetzungFehlgeschlagen("leere Antwort")
    if len(deutsch) < MINDESTANTEIL * len(original):
        raise UebersetzungFehlgeschlagen(
            f"zusammengefasst statt uebersetzt ({len(deutsch)} gegen "
            f"{len(original)} Zeichen)")


def uebersetze_titel(titel: str, sprache: str, modell: str) -> str:
    """Die Ueberschrift. Faellt sie aus, bleibt das Original stehen.

    Kein Grund, die ganze Uebersetzung zu verwerfen: eine deutsche Seite
    mit spanischer Ueberschrift ist unschoen, eine fehlende Seite ist
    schlimmer.
    """
    try:
        antwort = _saeubern(llm.complete(
            TITEL_SYSTEM,
            f"Ueberschrift ({sprachname(sprache)}):\n{titel}",
            modell, max_tokens=1000))
    except Exception as exc:  # noqa: BLE001
        log.debug("Titeluebersetzung fehlgeschlagen: %s", exc)
        return ""
    return antwort.splitlines()[0].strip() if antwort else ""


def uebersetze(text: str, sprache: str, modell: str,
               titel: str = "") -> tuple[str, list[str]]:
    """(deutscher Titel, deutsche Absaetze).

    Wirft `UebersetzungFehlgeschlagen`, wenn ein Abschnitt ausfaellt oder
    das Ergebnis zu kurz ist. Die aufrufende Stufe zaehlt das als
    "gescheitert" und schreibt den Grund ins Protokoll - sie legt KEINE
    halbe Uebersetzung ab.
    """
    teile = absaetze(text)
    if not teile:
        raise UebersetzungFehlgeschlagen("kein Text")

    quelle = sprachname(sprache)
    ergebnis: list[str] = []
    buendel = _abschnitte(teile)
    for nr, abschnitt in enumerate(buendel, 1):
        roh = "\n\n".join(abschnitt)
        hinweis = ""
        if len(buendel) > 1:
            hinweis = (f"\n\n(Dies ist Abschnitt {nr} von {len(buendel)} "
                       f"eines laengeren Artikels. Uebersetze NUR diesen "
                       f"Abschnitt, ohne Einleitung und ohne Schlusssatz.)")
        antwort = _saeubern(llm.complete(
            SYSTEM,
            f"Artikeltext ({quelle}):{hinweis}\n\n{roh}",
            modell, max_tokens=MAX_TOKENS))
        _pruefe(roh, antwort)
        ergebnis.extend(absaetze(antwort))

    if not ergebnis:
        raise UebersetzungFehlgeschlagen("keine Absaetze im Ergebnis")

    titel_de = uebersetze_titel(titel, sprache, modell) if titel else ""
    return titel_de, ergebnis
