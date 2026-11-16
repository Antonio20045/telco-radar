"""Wann ein Klick-Satz einen Adaptersatz ersetzt (Datenkonzept Geräteradar §7).

Ein Klick-Satz ersetzt einen Adaptersatz nur, wenn er jedes Wertfeld nennt, das der
Adaptersatz nennt (``WERTFELDER``); zwei Messungen werden nie feldweise gemischt. Zwei
Angaben des Adapters sagen dabei nichts über seine übrigen Felder hinaus:

- Eine einzige Preisphase ab Monat 1 zum Grundpreis ``tarif_monatlich`` auf den Cent,
  offen oder bis zum Ende der Bindung (ohne Bindung oder bei 0 Monaten
  ``ZEITRAUM_OHNE_BINDUNG``), ist die Phase, die ``tco_kosten.tarifphasen`` ohne
  Phasen selbst rechnet. Reicht sie über die Bindung hinaus (o2 1–36 bei 24 Monaten
  Bindung) oder nennt der Satz einen anderen Listenpreis (Vodafone: Aktionspreis
  35,86 € statt 61,95 €, Rechenweise 2), ist sie gemessen und hält den Klick-Satz
  zurück; der Listenpreis selbst ist Wertfeld.
- Eine nicht eingerechnete Aktion (Trade-in) ändert keinen Preis. Der Klick liest
  keine Aktionen; der ersetzende Satz trägt die nicht eingerechneten des Adaptersatzes
  weiter (``begleitend``), damit die Seite sie weiter nennt. Eine eingerechnete oder
  ohne lesbares ``eingerechnet`` hält den Klick-Satz zurück - außer sie ist BELEGT
  (``belegt``, siehe unten).

Am 08.10.2026 hielten diese beiden Angaben alle 64 congstar-Klick-Sätze zurück.

Eine belegte eingerechnete Aktion (Befund 16.11.2026)
-----------------------------------------------------
congstar hängt an jeden Bündelsatz den erlassenen Bereitstellungspreis:
``anschluss_erlassen``, Fußnote „Bei Abschluss bis zum 07.12.2026 schenken wir dir den
einmaligen Bereitstellungspreis / die einmaligen Kosten.“, Betrag 15,00 €,
``eingerechnet: true`` - und der Satz selbst trägt ``anschlusspreis: 0.0`` (nachgelesen
am 16.11.2026 an congstar.de/geraete/samsung/samsung-galaxy-s26/ und
…/apple/apple-iphone-14-refurbished-premium/: 32 Rohsätze, jeder mit dieser Aktion).
Dieselbe Null misst der Klick-Crawler auf derselben Seite. Die Aktion sagt also nichts,
was die gemessenen Werte nicht schon sagen, und hielt trotzdem 760 congstar-Klick-Sätze
zurück (Bilanz 15.11.2026: „unvollständig (aktionen 760)“).

Eine eingerechnete Aktion hält den Klick-Satz deshalb nur noch zurück, wenn sie NICHT
belegt ist (``belegt``). Belegt heißt alles davon, sonst bleibt es bewusst eine Lücke -
lieber ein Preis weniger als ein falscher:

1. Fußnote (``bedingung``) und Betrag (``betrag`` oder ``betrag_monatlich``, positiv)
   stehen da; eine Aktion ohne Bedingung ist nicht nachprüfbar.
2. ``gueltig_bis`` ist ein lesbares Datum und am Messtag noch nicht vorbei. Ein leeres
   oder unlesbares Datum ist ``unbekannt`` und fällt aus dem Vergleich (CLAUDE.md Clean
   Code 4). So bleiben die refurbished-Bündel mit der am 29.09.2026 abgelaufenen Aktion
   draußen: eine abgelaufene Aktion ist kein gültiger Preis (CLAUDE.md Regel 10).
3. Die Art gehört zu einem Wertfeld (``AKTIONSFELD``), und BEIDE Sätze nennen dieses
   Feld mit demselben Betrag. Erst das macht die Aktion eindeutig zuordenbar: der Klick
   hat dieselbe Wirkung gemessen wie der Adapter.

Ist sie belegt, ersetzt der Klick-Satz und trägt die Aktion mit (``begleitend``); die
Seite nennt sie weiter, und keine Zahl wandert aus zwei Quellen in einen Satz.
"""

from __future__ import annotations

from datetime import date

from ..tco_kosten import ZEITRAUM_OHNE_BINDUNG
from ..tco_model import (
    AKTION_ANSCHLUSS_ERLASSEN,
    AKTION_GERAETERABATT,
    AKTION_TARIFRABATT,
)

VERGLEICHSFELDER = (
    "geraet_zuzahlung",
    "geraet_monatsrate",
    "tarif_monatlich",
    "buendel_monatlich",
    "anschlusspreis",
    "tarif_bindung_monate",
)
WERTFELDER = (*VERGLEICHSFELDER, "tarif_listenpreis", "tarif_phasen", "aktionen")
"""Was ein Satz zum Bündel beiträgt; ein Klick-Satz muss alle nennen, die der Adapter
nennt, um ihn zu ersetzen."""
CENT = 0.005
GLEICH = 1e-6
PHASEN = "tarif_phasen"
AKTIONEN = "aktionen"
AKTIONSFELD = {
    AKTION_ANSCHLUSS_ERLASSEN: "anschlusspreis",
    AKTION_TARIFRABATT: "tarif_monatlich",
    AKTION_GERAETERABATT: "geraet_monatsrate",
}
"""Das Wertfeld, auf das eine Aktion dieser Art wirkt; andere Arten sind keinem Feld
eindeutig zuzuordnen und bleiben damit unbelegt."""


def nennt(satz: dict, feld: str, gegen: dict | None = None, tag: str = "") -> bool:
    """Ob ``satz`` in ``feld`` etwas sagt, das seine übrigen Felder nicht sagen.

    Bei ``aktionen`` zählen nur eingerechnete Aktionen, die nicht belegt sind
    (``belegt``, Modulkopf); ``gegen`` ist der Satz der anderen Quelle und ``tag`` der
    Messtag. Ohne beide ist keine Aktion belegt - dann gilt die alte, strengere Lesart.
    """
    wert = satz.get(feld)
    if feld == AKTIONEN:
        return any(
            _eingerechnet(a) and not belegt(a, satz, gegen, tag) for a in _liste(wert)
        )
    if feld == PHASEN and _grundpreisphase(satz):
        return False
    return wert is not None and wert != []


def fehlend(klick: dict, adapter: dict, tag: str = "") -> list[str]:
    """Die Wertfelder, die der Adaptersatz nennt und der Klick-Satz nicht."""
    return [
        f
        for f in WERTFELDER
        if nennt(adapter, f, klick, tag) and not nennt(klick, f, adapter, tag)
    ]


def begleitend(klick: dict, adapter: dict, tag: str = "") -> dict:
    """Die Aktionen des Adaptersatzes, die der ersetzende Klick-Satz mitträgt.

    Das sind die nicht eingerechneten (sie ändern keinen Preis) und die belegten
    eingerechneten (``belegt``): sie stehen mit Fußnote, Betrag und Frist da, und
    der Klick hat ihre Wirkung selbst gemessen. Nennt der Klick-Satz eigene Aktionen,
    bleibt es bei seinen - zwei Quellen werden nie feldweise gemischt.
    """
    mit = [
        a
        for a in _liste(adapter.get(AKTIONEN))
        if not _eingerechnet(a) or belegt(a, adapter, klick, tag)
    ]
    if not mit or _liste(klick.get(AKTIONEN)):
        return {}
    return {AKTIONEN: mit}


def belegt(aktion: object, satz: dict, gegen: dict | None, tag: str) -> bool:
    """Ob eine eingerechnete Aktion belegt ist (die drei Punkte im Modulkopf)."""
    if not isinstance(aktion, dict) or gegen is None:
        return False
    if not str(aktion.get("bedingung") or "").strip():
        return False
    betrag = aktion.get("betrag")
    if not _positiv(betrag) and not _positiv(aktion.get("betrag_monatlich")):
        return False
    if not _gilt_noch(aktion.get("gueltig_bis"), tag):
        return False
    feld = AKTIONSFELD.get(str(aktion.get("art") or ""))
    if feld is None or not nennt(satz, feld) or not nennt(gegen, feld):
        return False
    return abs(satz[feld] - gegen[feld]) <= CENT


def _positiv(wert: object) -> bool:
    return isinstance(wert, int | float) and not isinstance(wert, bool) and wert > 0


def _gilt_noch(gueltig_bis: object, tag: str) -> bool:
    """Ob die Aktion am Messtag noch gilt; ein unlesbares Datum belegt nichts."""
    ende, messtag = _datum(gueltig_bis), _datum(tag)
    if ende is None or messtag is None:
        return False
    return ende >= messtag


def _datum(wert: object) -> date | None:
    try:
        return date.fromisoformat(str(wert))
    except (TypeError, ValueError):
        return None


def _eingerechnet(aktion: object) -> bool:
    return not (isinstance(aktion, dict) and aktion.get("eingerechnet") is False)


def _liste(wert: object) -> list:
    return wert if isinstance(wert, list) else []


def _grundpreisphase(satz: dict) -> bool:
    phasen = _liste(satz.get(PHASEN))
    if len(phasen) != 1 or not isinstance(phasen[0], dict):
        return False
    phase = phasen[0]
    bindung = satz.get("tarif_bindung_monate")
    pflicht = ZEITRAUM_OHNE_BINDUNG if bindung in (None, 0) else bindung
    grundpreis = satz.get("tarif_monatlich")
    liste = satz.get("tarif_listenpreis")
    betrag = phase.get("betrag")
    if not isinstance(grundpreis, int | float) or not isinstance(betrag, int | float):
        return False
    if liste is not None and not _gleich(liste, betrag):
        return False
    return (
        phase.get("von_monat") == 1
        and phase.get("bis_monat") in (None, pflicht)
        and _gleich(betrag, grundpreis)
    )


def _gleich(a: object, b: float) -> bool:
    return isinstance(a, int | float) and abs(a - b) < GLEICH
