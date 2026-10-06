"""Was ein Bündel über H Monate kostet: die Kernzahl je Ratenlaufzeit.

Datenkonzept Geräte 5.3 und Entscheidung 1 (die 36er-Ansicht rechnet 36 Tarifmonate):

    Kosten über H Monate = Anzahlung + Anschluss + N Geräteraten
                         + Tarif in jedem Monat 1 bis H zum Preis seiner Phase
    ein Vertrag (1&1):   = Anzahlung + Anschluss + H × Bündelbetrag

H ist der größere Wert aus Ratenlaufzeit N und Tarifbindung (`zeitraum`). Fehlt ein
Posten, ist `Kosten.gesamt` None und die Lücke benannt; Boni und Aktionen gehen nie
ein, eingerechnete Aktionen stecken schon in der gemessenen Rate. Für H = 24 ist es
dieselbe Zahl wie `tco_24`.

`tco_model` reexportiert `Kosten`, `kosten_ueber` und `zeitraum` und lädt dieses Modul
dafür beim eigenen Laden. Die Namen aus `tco_model` liest dieses Modul deshalb erst
beim Aufruf; so geht jede Importreihenfolge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tarif_model import Preisphase
    from .tco_model import Buendel

ZEITRAUM_OHNE_BINDUNG = 24
POSTEN_ZEITRAUM = "Zeitraum"
POSTEN_EINMALZAHLUNG = "Einmalzahlung bei Kündigung"


@dataclass
class Kosten:
    """Die Kosten eines Bündels über `monate` Monate und was ihnen fehlt.

    `gesamt` ist None, sobald `luecken` einen Posten nennt. `monate` ist der Zeitraum
    H, `ratenlaufzeit` die Zahl N der Geräteraten (None ohne Gerät), `monatlich` der
    Schnitt über H, `posten` Name → Betrag in der Reihenfolge von `tco_24`.
    """

    gesamt: float | None = None
    monate: int | None = None
    ratenlaufzeit: int | None = None
    monatlich: float | None = None
    posten: dict[str, float] = field(default_factory=dict)
    luecken: list[str] = field(default_factory=list)


def zeitraum(buendel: Buendel) -> int | None:
    """Der Standardzeitraum H: der größere Wert aus Ratenlaufzeit und Tarifbindung.

    Eine unbekannte Bindung zählt `ZEITRAUM_OHNE_BINDUNG` Monate. None, wenn das
    Bündel ein Gerät hat und seine Ratenlaufzeit fehlt, oder wenn ohne Gerät und ohne
    Mindestlaufzeit kein Monat bleibt.
    """
    bindung = buendel.tarif_bindung_monate
    laengen = [ZEITRAUM_OHNE_BINDUNG if bindung is None else bindung]
    if not buendel.ohne_geraet:
        if buendel.laufzeit_monate is None:
            return None
        laengen.append(buendel.laufzeit_monate)
    groesste = max(laengen)
    return groesste if groesste > 0 else None


def kosten_ueber(buendel: Buendel, monate: int | None = None) -> Kosten:
    """Was `buendel` über `monate` Monate kostet, ohne `monate` über `zeitraum`.

    Getrennte Preisform: der Tarif in jedem Monat 1 bis H, alle N Raten (auch die
    nach Monat H), Anzahlung und Anschluss. Ein Vertrag (`buendel_monatlich`) trägt
    H × Bündelbetrag nur für H = N: davor fehlt die Einmalzahlung bei Kündigung,
    danach der Preis. Ein `monate`, das keine ganze Zahl über null ist, ist ein
    Aufruffehler (ValueError).
    """
    from .tco_model import monatsschnitt

    if monate is not None and (
        isinstance(monate, bool) or not isinstance(monate, int) or monate <= 0
    ):
        raise ValueError(f"kein Zeitraum in ganzen Monaten: {monate!r}")
    h = zeitraum(buendel) if monate is None else monate
    k = Kosten(
        monate=h,
        ratenlaufzeit=None if buendel.ohne_geraet else buendel.laufzeit_monate,
    )
    if h is None:
        k.luecken.append(POSTEN_ZEITRAUM)
    elif buendel.buendel_monatlich is not None:
        _vertrag(k, buendel.buendel_monatlich, buendel.laufzeit_monate, h)
    else:
        _tarif(k, buendel, h)
    _geraet_und_anschluss(k, buendel)
    if not k.luecken:
        k.gesamt = round(sum(k.posten.values()), 2)
        k.monatlich = monatsschnitt(k.gesamt, h)
    return k


def _vertrag(k: Kosten, betrag: float, laufzeit: int | None, h: int) -> None:
    """Ein Monatsbetrag für Tarif und Gerät, belegt für die Vertragslaufzeit N."""
    from .tco_model import POSTEN_BUENDEL, POSTEN_LAUFZEIT

    if laufzeit is None:
        k.luecken.append(POSTEN_LAUFZEIT)
    elif h < laufzeit:
        k.luecken.append(POSTEN_EINMALZAHLUNG)
    elif h > laufzeit:
        k.luecken.append(f"{POSTEN_BUENDEL} Monat {_spanne(laufzeit + 1, h)}")
    else:
        k.posten[f"{POSTEN_BUENDEL} über {h} Monate"] = round(betrag * h, 2)


def _tarif(k: Kosten, buendel: Buendel, h: int) -> None:
    """Der Tarif in jedem Monat 1 bis H: aus den Preisphasen, ohne sie flach.

    Ein Monat ohne genau eine Phase hat keinen bestimmbaren Preis und wird nicht mit
    dem Grundpreis oder der letzten Phase gefüllt.
    """
    from .tco_model import POSTEN_TARIF, phasensumme

    phasen = buendel.tarif_phasen
    monate = range(1, h + 1)
    offen = [m for m in monate if _preise_im_monat(phasen, m) != 1] if phasen else []
    if offen:
        k.luecken += [f"{POSTEN_TARIF} Monat {s}" for s in _spannen(offen)]
        return
    if phasen:
        summe = phasensumme(phasen, h)
    elif buendel.tarif_monatlich is not None:
        summe = round(buendel.tarif_monatlich * h, 2)
    else:
        summe = None
    if summe is None:
        k.luecken.append(POSTEN_TARIF)
    else:
        k.posten[f"Tarif über {h} Monate"] = summe


def _geraet_und_anschluss(k: Kosten, buendel: Buendel) -> None:
    """Anzahlung und, in getrennter Preisform, alle N Raten; dann der Anschluss."""
    from .tco_model import (
        POSTEN_ANSCHLUSS,
        POSTEN_LAUFZEIT,
        POSTEN_RATE,
        POSTEN_ZUZAHLUNG,
    )

    if not buendel.ohne_geraet:
        _posten(k, POSTEN_ZUZAHLUNG, buendel.geraet_zuzahlung)
    if not buendel.ohne_geraet and buendel.buendel_monatlich is None:
        rate, laufzeit = buendel.geraet_monatsrate, buendel.laufzeit_monate
        if rate is None:
            k.luecken.append(POSTEN_RATE)
        elif laufzeit is None:
            k.luecken.append(POSTEN_LAUFZEIT)
        else:
            k.posten[f"Geräteraten über {laufzeit} Monate"] = round(rate * laufzeit, 2)
    _posten(k, POSTEN_ANSCHLUSS, buendel.anschlusspreis)


def _posten(k: Kosten, name: str, betrag: float | None) -> None:
    """Ein gemessener Betrag wird Posten, ein fehlender Lücke; 0,00 € ist gemessen."""
    if betrag is None:
        k.luecken.append(name)
    else:
        k.posten[name] = betrag


def _preise_im_monat(phasen: list[Preisphase], monat: int) -> int:
    """Wie viele Phasen einen Preis für `monat` nennen."""
    return sum(
        p.von_monat <= monat and (p.bis_monat is None or monat <= p.bis_monat)
        for p in phasen
    )


def _spannen(monate: list[int]) -> list[str]:
    """Aufeinanderfolgende Monate als „25–36“, ein einzelner als „25“."""
    spannen: list[list[int]] = []
    for monat in monate:
        if spannen and monat == spannen[-1][1] + 1:
            spannen[-1][1] = monat
        else:
            spannen.append([monat, monat])
    return [_spanne(von, bis) for von, bis in spannen]


def _spanne(von: int, bis: int) -> str:
    return f"{von}–{bis}" if bis > von else f"{von}"
