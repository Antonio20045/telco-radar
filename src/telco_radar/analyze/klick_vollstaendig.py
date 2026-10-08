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
  ohne lesbares ``eingerechnet`` hält den Klick-Satz zurück.

Am 08.10.2026 hielten diese beiden Angaben alle 64 congstar-Klick-Sätze zurück.
"""

from __future__ import annotations

from ..tco_kosten import ZEITRAUM_OHNE_BINDUNG

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


def nennt(satz: dict, feld: str) -> bool:
    """Ob ``satz`` in ``feld`` etwas sagt, das seine übrigen Felder nicht sagen."""
    wert = satz.get(feld)
    if feld == AKTIONEN:
        return any(_eingerechnet(a) for a in _liste(wert))
    if feld == PHASEN and _grundpreisphase(satz):
        return False
    return wert is not None and wert != []


def fehlend(klick: dict, adapter: dict) -> list[str]:
    """Die Wertfelder, die der Adaptersatz nennt und der Klick-Satz nicht."""
    return [f for f in WERTFELDER if nennt(adapter, f) and not nennt(klick, f)]


def begleitend(klick: dict, adapter: dict) -> dict:
    """Die nicht eingerechneten Aktionen des Adaptersatzes, nennt der Klick keine."""
    offen = [a for a in _liste(adapter.get(AKTIONEN)) if not _eingerechnet(a)]
    if not offen or _liste(klick.get(AKTIONEN)):
        return {}
    return {AKTIONEN: offen}


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
