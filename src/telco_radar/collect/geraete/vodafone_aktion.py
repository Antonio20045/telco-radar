"""Vodafone: der Aktionspreis des Tarifs als Preisphase (Datenkonzept Geräte, R. 3).

BEFUND 07.10.2026
-----------------
vodafone.de/privat/handys/iphone-17-pro.html, GigaMobil XS mit 24 Raten: „pro Monat
73,45 €“, durchgestrichen 81,45 €. Der Bestand rechnete 31,95 € Tarif + 49,50 € Rate =
81,45 €, weil `vodafone.py` nur `withoutDiscounts` las. Die 8,00 € Unterschied sind der
Online-Vorteil auf den Tarif, und dieselbe Antwort nennt ihn mit Dauer.

RABATTIERT WIRD DER TARIF, NICHT DAS GERÄT
------------------------------------------
`withDiscounts` steht in allen gespeicherten Kompositionen (Fixtures vom 28.08., 05.09.,
29.09. und 07.10.2026) nur unter `priceByComponent.tariff.priceByType.rate.month`, nie
an der Geräterate und nie an einem Einmalbetrag. Die Gesamtrate bestätigt es in jedem
Monat: `totalMonthlyRatePrice.withDiscounts` = Tarifphase + unrabattierte Geräterate
(iPhone 17 Pro, Mobil XS, 36 Raten: 23,95 + 33,00 = 56,95 € in Monat 1–24). Geht diese
Probe nicht auf, ist offen, welcher Posten rabattiert ist.

DIE DAUER STEHT AN DER PHASE
----------------------------
Jede Phase von `withDiscounts` trägt `recurrenceStart` und `recurrenceEnd` (gemessen
1–24; bei 12 Raten 1–12 und 13–24, weil der Ratenzahlungsrabatt mit der letzten Rate
endet). Den Grund nennt die Tarifantwort im Wortlaut (`atomics[].discount.monetary[]`,
Mobil XS: „24 Monate: 25 % Vorteil auf Tarifpreis ohne Hardwarezuzahlung“, −8,00 €).
Der Preis danach ist `withoutDiscounts`, belegt bis zu dessen `recurrenceEnd`; Monate
dahinter nennt die Antwort nicht (ab Monat 25 nur die Geräterate), sie bleiben Lücke
(`tco_kosten.belegte_phasen`).

WAS EINGEHT UND WAS NICHT
-------------------------
Eingerechnet wird, was die Bestellstrecke monatlich ohne Antrag verlangt, also alles in
`month.withDiscounts`: Online-Vorteil, „200 € Hardware-Bonus (Du sparst 8,34 € pro
Monat, 24 Monate lang)“, Ratenzahlungsrabatt. Einmal-Gutschriften („Der Anschlusspreis
wird in Kürze zurückerstattet“) stehen dort nicht und gehen nie ein. Fehlt einer
Rabattphase das Ende oder geht die Probe nicht auf, ist der Tarifpreis eine Lücke
(`tarif_monatlich` None), nie stillschweigend der Listenpreis.
"""

from __future__ import annotations

import logging

from ...tco_model import laufzeit_in_monaten
from .basis import _gleich, _preis

log = logging.getLogger(__name__)

TARIF_MONAT = ("priceByComponent", "tariff", "priceByType", "rate", "month")
GESAMTRATE = "totalMonthlyRatePrice"


class AktionOhneBeleg(ValueError):
    """Ein Aktionspreis, dessen Dauer oder Posten die Antwort nicht belegt."""


def _knoten(nutzlast, *stufen):
    for stufe in stufen:
        nutzlast = nutzlast.get(stufe) if isinstance(nutzlast, dict) else None
    return nutzlast


def _eur(betrag: float) -> str:
    return f"{betrag:.2f} €".replace(".", ",")


def _phase(roh) -> tuple[int, int, float]:
    """(von, bis, Betrag) einer Rabattphase; ohne Anfang, Ende oder Betrag keine."""
    roh = roh if isinstance(roh, dict) else {}
    von = laufzeit_in_monaten(roh.get("recurrenceStart"))
    bis = laufzeit_in_monaten(roh.get("recurrenceEnd"))
    betrag = _preis(roh.get("gross"))
    if von is None or bis is None or betrag is None or bis < von:
        raise AktionOhneBeleg(f"Aktionspreis ohne belegte Dauer: {roh!r}")
    return von, bis, betrag


def _gesamt_im_monat(komposition: dict, monat: int) -> float | None:
    """Die Gesamtrate mit Rabatten in `monat` - None, wo nicht genau eine Phase gilt."""
    treffer = [
        _preis(p.get("gross"))
        for p in _knoten(komposition, GESAMTRATE, "withDiscounts") or []
        if isinstance(p, dict)
        and (laufzeit_in_monaten(p.get("recurrenceStart")) or 0) <= monat
        and monat <= (laufzeit_in_monaten(p.get("recurrenceEnd")) or monat)
    ]
    return treffer[0] if len(treffer) == 1 else None


def _probe(komposition: dict, phase: tuple, rate: float | None, laufzeit) -> None:
    """Tarifphase + Geräterate (solange sie läuft) = Gesamtrate, in jedem Monat."""
    von, bis, betrag = phase
    for monat in range(von, bis + 1):
        geraet = rate if rate is not None and monat <= (laufzeit or 0) else 0.0
        gesamt = _gesamt_im_monat(komposition, monat)
        if not _gleich(gesamt, betrag + geraet):
            raise AktionOhneBeleg(
                f"Monat {monat}: Gesamtrate mit Rabatt {gesamt} ist nicht "
                f"Tarif {betrag} + Geräterate {geraet} - rabattierter Posten offen"
            )


def _listenmonate(liste: dict, belegt: set[int]) -> list[tuple[int, int]]:
    """Die Spannen im Fenster von `withoutDiscounts`, die keine Rabattphase nennt."""
    von = laufzeit_in_monaten(liste.get("recurrenceStart"))
    bis = laufzeit_in_monaten(liste.get("recurrenceEnd"))
    if von is None or bis is None:
        return []
    spannen: list[tuple[int, int]] = []
    for monat in range(von, bis + 1):
        if monat in belegt:
            continue
        if spannen and spannen[-1][1] == monat - 1:
            spannen[-1] = (spannen[-1][0], monat)
        else:
            spannen.append((monat, monat))
    return spannen


def aktionsphasen(
    komposition: dict, rate: float | None, laufzeit: int | None
) -> list[dict]:
    """Die Tarifphasen einer Komposition mit Aktionspreis; [] ohne Aktionspreis.

    `rate` ist die Geräterate, die `vodafone._buendelsatz_aus_komposition` neben dem
    Tarif gefunden hat (None im `sub`-Fall), `laufzeit` ihre Ratenlaufzeit. Wirft
    `AktionOhneBeleg`, wenn eine Rabattphase ohne Dauer ist, Phasen sich überlappen
    oder die Gesamtrate den Rabatt nicht dem Tarif zuordnet.
    """
    rabatt = _knoten(komposition, *TARIF_MONAT, "withDiscounts")
    liste = _knoten(komposition, *TARIF_MONAT, "withoutDiscounts") or {}
    listenpreis = _preis(liste.get("gross"))
    if not rabatt:
        return []
    if not isinstance(rabatt, list):
        raise AktionOhneBeleg(f"withDiscounts ist keine Phasenliste: {rabatt!r}")
    phasen = sorted(_phase(p) for p in rabatt)
    if all(_gleich(betrag, listenpreis) for _, _, betrag in phasen):
        return []
    belegt: set[int] = set()
    for phase in phasen:
        monate = set(range(phase[0], phase[1] + 1))
        if monate & belegt:
            raise AktionOhneBeleg(f"Rabattphasen überlappen: {phasen!r}")
        belegt |= monate
        _probe(komposition, phase, rate, laufzeit)
    statt = "" if listenpreis is None else f" statt {_eur(listenpreis)}"
    geraet = f" + Geräterate {_eur(rate)}" if rate is not None else ""
    out = [
        {
            "von_monat": von,
            "bis_monat": bis,
            "betrag": betrag,
            "beleg": f"Vodafone glados tariff.month.withDiscounts Monat {von}-{bis}: "
            f"{_eur(betrag)}{statt}; {GESAMTRATE}.withDiscounts = Tarif{geraet}",
        }
        for von, bis, betrag in phasen
    ]
    if listenpreis is not None:
        out += [
            {
                "von_monat": von,
                "bis_monat": bis,
                "betrag": listenpreis,
                "beleg": "Vodafone glados tariff.month.withoutDiscounts Monat "
                f"{von}-{bis}: {_eur(listenpreis)} nach dem Aktionspreis",
            }
            for von, bis in _listenmonate(liste, belegt)
        ]
    return sorted(out, key=lambda p: p["von_monat"])


def tarif_mit_aktion(
    komposition: dict,
    tarif: float,
    rate: float | None,
    laufzeit: int | None,
) -> tuple[float | None, list[dict]]:
    """(`tarif_monatlich`, `tarif_phasen`) eines Vodafone-Bündelsatzes.

    `tarif` ist der Listenpreis (`withoutDiscounts`). Ein Aktionspreis ohne Beleg macht
    den Tarifpreis zur Lücke (None, mit Protokoll); ohne Aktionspreis bleibt alles wie
    gemessen.
    """
    try:
        return tarif, aktionsphasen(komposition, rate, laufzeit)
    except AktionOhneBeleg as exc:
        log.warning(
            "Vodafone-Buendel: Komposition %s - Tarifpreis ist eine Luecke: %s",
            komposition.get("offerCoreHash"),
            exc,
        )
        return None, []
