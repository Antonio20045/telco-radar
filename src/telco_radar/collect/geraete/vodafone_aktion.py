"""Vodafone: der Aktionspreis des Tarifs als Preisphase (Datenkonzept Geräte, R. 3).

BEFUND 07.10.2026
-----------------
vodafone.de/privat/handys/iphone-17-pro.html, GigaMobil XS mit 24 Raten: „pro Monat
73,45 €“, durchgestrichen 81,45 €. Der Bestand rechnete 31,95 € Tarif + 49,50 € Rate =
81,45 €, weil `vodafone.py` nur `withoutDiscounts` las. Die 8,00 € Unterschied sind der
Online-Vorteil auf den Tarif, und dieselbe Antwort nennt ihn mit Dauer.

EINE DEFINITION DES TARIFPREISES
--------------------------------
`tarif_monatlich` ist wie bei o2 (Tarifrate der Konfiguration), congstar (`discounted`)
und dem Klick-Crawler (Phase ab Monat 1) der Tarifpreis, den die Seite in Monat 1
zeigt: 23,95 €. Den Listenpreis ohne Rabatt (31,95 €) trägt `tarif_listenpreis`.
Karte, Export und Katalog lesen damit dieselbe Zahl, mit der die Kernzahl rechnet;
Regel 3 (Tarif zum SIM-only-Preis) prüft den Listenpreis. Seit dieser Lesart misst
Vodafone in Rechenweise 2 (`rechenweise`): ältere Zeilen sind nicht vergleichbar.

RABATTIERT WIRD DER TARIF, NICHT DAS GERÄT
------------------------------------------
`withDiscounts` steht in allen gespeicherten Kompositionen (Fixtures vom 28.08., 05.09.,
29.09. und 07.10.2026) nur unter `priceByComponent.tariff.priceByType.rate.month`, nie
an der Geräterate und nie an einem Einmalbetrag. Die Gesamtrate bestätigt es in jedem
Monat: `totalMonthlyRatePrice.withDiscounts` = Tarifphase + unrabattierte Geräterate
(iPhone 17 Pro, Mobil XS, 36 Raten: 23,95 + 33,00 = 56,95 € in Monat 1–24). Geht diese
Probe nicht auf, ist offen, welcher Posten rabattiert ist.

DIE DAUER STEHT AN DER PHASE, DER GRUND AM POSTEN
-------------------------------------------------
Jede Phase von `withDiscounts` trägt `recurrenceStart` und `recurrenceEnd` (gemessen
1–24; bei 12 Raten 1–12 und 13–24, weil der Ratenzahlungsrabatt mit der letzten Rate
endet). Der Preis danach ist `withoutDiscounts`, belegt bis zu dessen `recurrenceEnd`;
Monate dahinter nennt die Antwort nicht (ab Monat 25 nur die Geräterate), sie bleiben
Lücke (`tco_kosten.belegte_phasen`). Die Posten nennt nur die Tarifantwort, je Tarif
unter `atomics[].discount.monetary[]` (Mobil XS: „24 Monate: 25 % Vorteil auf
Tarifpreis ohne Hardwarezuzahlung“, −8,00 €); `vodafone._buendel_aus_tarifantwort`
hängt diesen Block unter `RABATTPOSTEN` an jede Komposition des Tarifs.

WAS EINGEHT UND WAS NICHT
-------------------------
Vergleichsgrundlage ist ein Neuvertrag mit Ratenkauf. Es zählen Neukunden-Vorteil,
„200 € Hardware-Bonus (Du sparst 8,34 € pro Monat, 24 Monate lang)“ und
Ratenzahlungsrabatt: die Bestellstrecke zieht sie ohne Antrag ab. Ein Posten mit
Bedingung (`BEDINGTE_POSTEN`: Wechsel, Rufnummernmitnahme, Junge Leute, GigaKombi,
FamilyCard) zählt nie; trägt einer einen Betrag, gilt in jedem Monat der Preis ohne ihn
(`withoutDiscounts` plus die zulässigen Posten), und die Antwort muss ihn belegen: der
Monatspreis mit Rabatt ist dieser Preis oder dieser Preis plus bedingte Posten. Ohne
gelesene Posten (Vorschau der Detailantwort) ist offen, ob ein bedingter darin steckt.
Fehlt einer Rabattphase das Ende, geht eine Probe nicht auf oder fehlen die Posten, ist
der Tarifpreis eine Lücke (`tarif_monatlich` None, mit Warnung), nie stillschweigend
der Listenpreis.

Nicht behoben: der Anschluss. `anschlusspreis` kommt aus `tariff.onetime.
withoutDiscounts` und ist dort schon 0,00 €, also mit der Neukunden-Gutschrift („0 €
statt 39,99 € Anschlusspreis. Der Anschlusspreis wird in Kürze zurückerstattet“).
Datenkonzept §8 „Anschluss aus den Pflichtangaben“ steht aus.
"""

from __future__ import annotations

import logging
from itertools import combinations

from ...tco_model import laufzeit_in_monaten
from .basis import _gleich, _preis

log = logging.getLogger(__name__)

TARIF_MONAT = ("priceByComponent", "tariff", "priceByType", "rate", "month")
GESAMTRATE = "totalMonthlyRatePrice"
RABATTPOSTEN = "discount"
BEDINGTE_POSTEN = (
    "wechsel",
    "rufnummer",
    "junge leute",
    "young",
    "gigakombi",
    "kombi-vorteil",
    "familycard",
)
"""Wortteile im `displayLabel` eines Rabattpostens, die eine Bedingung nennen."""
NICHT_GELESEN = "Rabattposten nicht gelesen (keine Tarifantwort)"
"""Vorschau der Detailantwort: `vodafone.loese_tarifnamen` ersetzt sie durch die
Tarifantwort; nur was bleibt, trägt die Lücke bis zur Seite. Darum INFO."""


class AktionOhneBeleg(ValueError):
    """Ein Aktionspreis, dessen Dauer, Posten oder Posten-Zuordnung unbelegt ist."""


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


def ist_bedingt(posten: dict) -> bool:
    """Nennt der Rabattposten eine Bedingung (`BEDINGTE_POSTEN`)?"""
    text = str(posten.get("displayLabel") or "").lower()
    return any(wort in text for wort in BEDINGTE_POSTEN)


def _posten(komposition: dict) -> tuple[list[float], list[dict]]:
    """(Beträge der zulässigen, bedingte Posten mit Betrag) aus `RABATTPOSTEN`."""
    block = komposition.get(RABATTPOSTEN)
    roh = block.get("monetary") if isinstance(block, dict) else None
    if not isinstance(roh, list):
        raise AktionOhneBeleg(NICHT_GELESEN)
    zulaessig: list[float] = []
    bedingt: list[dict] = []
    for p in roh:
        betrag = _preis(p.get("gross")) if isinstance(p, dict) else None
        if betrag is None:
            raise AktionOhneBeleg(f"Rabattposten ohne Betrag: {p!r}")
        if betrag and ist_bedingt(p):
            bedingt.append(p)
        elif betrag:
            zulaessig.append(betrag)
    return zulaessig, bedingt


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


def _ohne_bedingte(phasen: list, preis: float, bedingt: list[dict]) -> list:
    """Jede Phase zum Preis ohne bedingte Posten, wenn die Antwort ihn belegt."""
    betraege = [float(p["gross"]) for p in bedingt]
    summen = [
        sum(t) for n in range(len(betraege) + 1) for t in combinations(betraege, n)
    ]
    for von, bis, betrag in phasen:
        if not any(_gleich(betrag, preis + s) for s in summen):
            raise AktionOhneBeleg(
                f"Monat {von}-{bis}: {betrag} ist weder {preis} noch {preis} plus "
                f"bedingte Posten {betraege} - Preis ohne Bedingung nicht belegt"
            )
    return [(von, bis, preis) for von, bis, _ in phasen]


def _zusammen(phasen: list) -> list:
    """Aneinandergrenzende Phasen gleichen Preises als eine."""
    out: list = []
    for von, bis, betrag in phasen:
        if out and out[-1][1] == von - 1 and _gleich(out[-1][2], betrag):
            out[-1] = (out[-1][0], bis, out[-1][2])
        else:
            out.append((von, bis, betrag))
    return out


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


def _belegt(phasen: list) -> set[int]:
    belegt: set[int] = set()
    for von, bis, _ in phasen:
        monate = set(range(von, bis + 1))
        if monate & belegt:
            raise AktionOhneBeleg(f"Rabattphasen überlappen: {phasen!r}")
        belegt |= monate
    return belegt


def aktionsphasen(
    komposition: dict, rate: float | None, laufzeit: int | None
) -> list[dict]:
    """Die Tarifphasen einer Komposition mit Aktionspreis; [] ohne Aktionspreis.

    `rate` ist die Geräterate, die `vodafone._buendelsatz_aus_komposition` neben dem
    Tarif gefunden hat (None im `sub`-Fall), `laufzeit` ihre Ratenlaufzeit. Wirft
    `AktionOhneBeleg`, wenn eine Rabattphase ohne Dauer ist, Phasen sich überlappen,
    die Posten fehlen oder eine Probe nicht aufgeht (siehe Modulkopf).
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
    belegt = _belegt(phasen)
    for phase in phasen:
        _probe(komposition, phase, rate, laufzeit)
    zulaessig, bedingt = _posten(komposition)
    quelle = "withDiscounts"
    if bedingt:
        if listenpreis is None:
            raise AktionOhneBeleg("bedingter Rabattposten ohne Listenpreis")
        preis = round(listenpreis + sum(zulaessig), 2)
        phasen = _zusammen(_ohne_bedingte(phasen, preis, bedingt))
        namen = "; ".join(str(p.get("displayLabel") or "") for p in bedingt)
        quelle = f"withoutDiscounts ohne bedingte Posten ({namen})"
    statt = "" if listenpreis is None else f" statt {_eur(listenpreis)}"
    geraet = f" + Geräterate {_eur(rate)}" if rate is not None else ""
    out = [
        {
            "von_monat": von,
            "bis_monat": bis,
            "betrag": betrag,
            "beleg": f"Vodafone glados tariff.month.{quelle} Monat {von}-{bis}: "
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
    listenpreis: float,
    rate: float | None,
    laufzeit: int | None,
) -> tuple[float | None, float, list[dict]]:
    """(`tarif_monatlich`, `tarif_listenpreis`, `tarif_phasen`) eines Bündelsatzes.

    `listenpreis` ist `tariff.month.withoutDiscounts`. `tarif_monatlich` ist der Preis
    in Monat 1: der der Phase, die ihn nennt, ohne Phase der Listenpreis. Ein
    Aktionspreis ohne Beleg macht ihn zur Lücke (None, mit Protokoll).
    """
    try:
        phasen = aktionsphasen(komposition, rate, laufzeit)
    except AktionOhneBeleg as exc:
        log.log(
            logging.INFO if str(exc) == NICHT_GELESEN else logging.WARNING,
            "Vodafone-Buendel: Komposition %s - Tarifpreis ist eine Luecke: %s",
            komposition.get("offerCoreHash"),
            exc,
        )
        return None, listenpreis, []
    if not phasen:
        return listenpreis, listenpreis, []
    erster = [p["betrag"] for p in phasen if p["von_monat"] == 1]
    return (erster[0] if erster else None), listenpreis, phasen
