"""Was ein Bündel über H Monate kostet: die Kernzahl je Ratenlaufzeit.

Datenkonzept Geräte 5.3 (Antonio, 10.10.2026: der Tarif endet nach seiner Bindung,
die Raten laufen weiter):

    Kosten über H Monate = Anzahlung + Anschluss + N Geräteraten
                         + Tarif in jedem Monat 1 bis T zum Preis seiner Phase
    ein Vertrag (1&1):   = Anschluss + 24 × Bündelbetrag + Ablöse nach Monat 24

H ist der größere Wert aus Ratenlaufzeit N und Tarifbindung (`zeitraum`), T der
kleinere aus H und den Tarifmonaten (`tarifmonate`, höchstens 24 nach § 56 TKG):
bei 36 Raten zählen Monat 1 bis 24 Tarif und Rate, Monat 25 bis 36 nur die Rate. Ein
gemessener Grundpreis ohne Preisphasen ist nur bis zum Ende der Bindung belegt (ohne
Bindung 24 Monate); die Bestellstrecke nennt ihn nicht für die Monate danach. Dasselbe
gilt für eine einzige Phase ab Monat 1 ohne Ende (`belegte_phasen`). Fehlt
ein Posten oder der Preis eines Monats, ist `Kosten.gesamt` None und die Lücke
benannt; Boni und Aktionen gehen nie ein, eingerechnete Aktionen stecken schon in der
gemessenen Rate. Für H = 24 ist es dieselbe Zahl wie `tco_24`.

Ein Vertrag über mehr als 24 Monate (1&1 „24+12“) wird über 24 Monate gerechnet
(Antonio, 10.10.2026): Tarif nach Monat 24 gekündigt, Gerät behalten. Seine
`geraet_zuzahlung` ist dann die Ablöse nach Monat 24, keine Anzahlung; ohne sie ist
die Zahl die Lücke `POSTEN_EINMALZAHLUNG`.

`tco_model` reexportiert `Kosten`, `kosten_ueber` und `zeitraum` und lädt dieses Modul
dafür beim eigenen Laden. Die Namen aus `tco_model` liest dieses Modul deshalb erst
beim Aufruf; so geht jede Importreihenfolge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .tarif_model import Preisphase

if TYPE_CHECKING:
    from .tco_model import Buendel

ZEITRAUM_OHNE_BINDUNG = 24
POSTEN_ZEITRAUM = "Zeitraum"
POSTEN_EINMALZAHLUNG = "Einmalzahlung bei Kündigung"
SCHRITT_GERAET = "geraet"
SCHRITT_TARIF = "tarif"
SCHRITT_VERTRAG = "vertrag"
SCHRITT_ANZAHLUNG = "anzahlung"
SCHRITT_ANSCHLUSS = "anschluss"
SCHRITT_BARPREIS = "barpreis"
SCHRITT_MONAT = "monat"
SCHRITT_NUR_GERAET = "nur_geraet"
SCHRITT_ABLOESE = "abloese"
REIHENFOLGE_SCHRITTE = (
    SCHRITT_BARPREIS,
    SCHRITT_GERAET,
    SCHRITT_VERTRAG,
    SCHRITT_TARIF,
    SCHRITT_ANZAHLUNG,
    SCHRITT_ABLOESE,
    SCHRITT_ANSCHLUSS,
)


@dataclass(frozen=True)
class Rechenschritt:
    """Ein Summand der Kernzahl, wie die Seite ihn zeigt: `anzahl` × `betrag`.

    `anzahl` ist None bei einem einmaligen Betrag; `summe` ist der Posten, den
    `kosten_ueber` addiert hat (bei Preisphasen ein Teil davon). `teile` nennt
    bei einem Monatspreis die Schritte Gerät und Tarif, aus denen er besteht.
    """

    art: str
    anzahl: int | None
    betrag: float
    summe: float
    teile: tuple[Rechenschritt, ...] = ()


@dataclass
class Kosten:
    """Die Kosten eines Bündels über `monate` Monate und was ihnen fehlt.

    `gesamt` ist None, sobald `luecken` einen Posten nennt. `monate` ist der Zeitraum
    H, `ratenlaufzeit` die Zahl N der Geräteraten (None ohne Gerät), `monatlich` der
    Schnitt über H, `posten` Name → Betrag in der Reihenfolge von `tco_24`.
    `rechnung` sind dieselben Posten als Summanden (Gerät, Tarif, einmalig, ohne
    Nullbeträge); ihre Summe ist `gesamt`. Ohne `gesamt` stehen darin nur die
    gemessenen Posten, die fehlenden nennt `luecken`. `tarifmonate` sind die Monate
    mit Tarif in der Zahl (`tarifmonate`; ein Bündelbetrag läuft über H).
    """

    gesamt: float | None = None
    monate: int | None = None
    ratenlaufzeit: int | None = None
    monatlich: float | None = None
    posten: dict[str, float] = field(default_factory=dict)
    luecken: list[str] = field(default_factory=list)
    rechnung: list[Rechenschritt] = field(default_factory=list)
    tarifmonate: int | None = None


def zeitraum(buendel: Buendel) -> int | None:
    """Der Standardzeitraum H: der größere Wert aus Ratenlaufzeit und Tarifbindung.

    Eine unbekannte Bindung zählt `ZEITRAUM_OHNE_BINDUNG` Monate. None, wenn das
    Bündel ein Gerät hat und seine Ratenlaufzeit fehlt, oder wenn ohne Gerät und ohne
    Mindestlaufzeit kein Monat bleibt.
    """
    if _mit_abloese(buendel, ZEITRAUM_OHNE_BINDUNG):
        return ZEITRAUM_OHNE_BINDUNG
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

    Getrennte Preisform: der Tarif in jedem Monat 1 bis T, alle N Raten (auch die
    nach Monat H), Anzahlung und Anschluss; endet H vor der Tarifbindung, fehlen die
    geschuldeten Tarifmonate danach. Ein Vertrag (`buendel_monatlich`) trägt
    H × Bündelbetrag nur für H = N: davor fehlt die Einmalzahlung bei Kündigung,
    danach der Preis. Ein `monate`, das keine ganze Zahl über null ist, ist ein
    Aufruffehler (ValueError).

    Abweichung von `tco_24`: Nennen die Preisphasen einen Monat bis 24 nicht, ist er
    hier eine Lücke; `tco_24` schreibt über `phasensumme` den letzten Preis fort. Im
    Schnappschuss vom 3. Oktober 2026 kommt keine solche Phasenlücke vor.
    """
    from .tco_model import POSTEN_LAUFZEIT, monatsschnitt

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
        if buendel.buendel_monatlich is not None and buendel.laufzeit_monate is None:
            k.luecken.append(POSTEN_LAUFZEIT)
    elif buendel.buendel_monatlich is not None:
        _vertrag(k, buendel.buendel_monatlich, buendel.laufzeit_monate, h)
    else:
        _tarif(k, buendel, h)
    _geraet_und_anschluss(k, buendel)
    if not k.luecken:
        k.gesamt = round(sum(k.posten.values()), 2)
        k.monatlich = monatsschnitt(k.gesamt, h)
    k.rechnung = sorted(
        (s for s in k.rechnung if s.summe),
        key=lambda s: REIHENFOLGE_SCHRITTE.index(s.art),
    )
    return k


def _vertrag(k: Kosten, betrag: float, laufzeit: int | None, h: int) -> None:
    """Ein Monatsbetrag für Tarif und Gerät, belegt für die Vertragslaufzeit N."""
    from .tco_model import POSTEN_BUENDEL, POSTEN_LAUFZEIT

    k.tarifmonate = h
    if laufzeit is None:
        k.luecken.append(POSTEN_LAUFZEIT)
    elif h > laufzeit:
        k.luecken.append(f"{POSTEN_BUENDEL} Monat {_spanne(laufzeit + 1, h)}")
    else:
        k.posten[f"{POSTEN_BUENDEL} über {h} Monate"] = round(betrag * h, 2)
        k.rechnung.append(
            Rechenschritt(SCHRITT_VERTRAG, h, betrag, round(betrag * h, 2))
        )


def _tarif(k: Kosten, buendel: Buendel, h: int) -> None:
    """Der Tarif in jedem Monat 1 bis T zum Preis der einen Phase, die ihn nennt.

    Ohne Phasen ist der gemessene Grundpreis eine Phase bis zum Ende der Bindung.
    Ein Monat ohne genau eine Phase wird nicht gefüllt, sondern Lücke, ebenso jeder
    geschuldete Tarifmonat der Bindung nach Monat H.
    """
    from .tco_model import POSTEN_TARIF, phasensumme

    pflicht = _pflicht(buendel)
    phasen = tarifphasen(buendel)
    if not phasen:
        k.luecken.append(POSTEN_TARIF)
        return
    t = k.tarifmonate = min(h, tarifmonate(buendel))
    offen = [m for m in range(1, t + 1) if _preise_im_monat(phasen, m) != 1]
    k.luecken += [f"{POSTEN_TARIF} Monat {s}" for s in _spannen(offen)]
    summe = None if offen else phasensumme(phasen, t)
    if summe is not None:
        k.posten[f"Tarif über {t} Monate"] = summe
        k.rechnung += tarifschritte(phasen, t)
    elif not offen:
        k.luecken.append(POSTEN_TARIF)
    elif offen[0] > 1:
        k.rechnung += tarifschritte(phasen, offen[0] - 1)
    if h < pflicht:
        k.luecken.append(f"{POSTEN_TARIF} Monat {_spanne(h + 1, pflicht)}")


def monatsschritte(schritte: list[Rechenschritt]) -> list[Rechenschritt]:
    """Gerät und Tarif im selben Monat als ein Monatspreis, wie der Anbieter ihn
    nennt; Gerät und Tarif bleiben als `teile`. Laufen die Raten länger als der
    Tarif, folgen die übrigen Monate als „nur Gerät“. Sonst unverändert."""
    geraet = [s for s in schritte if s.art == SCHRITT_GERAET]
    tarif = [s for s in schritte if s.art == SCHRITT_TARIF]
    if len(geraet) != 1 or len(tarif) != 1:
        return list(schritte)
    g, t = geraet[0], tarif[0]
    if g.anzahl is None or t.anzahl is None or g.anzahl < t.anzahl:
        return list(schritte)
    zusammen = round(g.betrag * t.anzahl, 2) if g.anzahl > t.anzahl else g.summe
    teil = Rechenschritt(SCHRITT_GERAET, t.anzahl, g.betrag, zusammen)
    neu = [
        Rechenschritt(
            SCHRITT_MONAT,
            t.anzahl,
            round(g.betrag + t.betrag, 2),
            round(zusammen + t.summe, 2),
            (teil, t),
        )
    ]
    if g.anzahl > t.anzahl:
        neu.append(
            Rechenschritt(
                SCHRITT_NUR_GERAET,
                g.anzahl - t.anzahl,
                g.betrag,
                round(g.summe - zusammen, 2),
            )
        )
    return [*neu, *(s for s in schritte if s is not g and s is not t)]


def tarifschritte(phasen: list[Preisphase], h: int) -> list[Rechenschritt]:
    """Je Preisphase ein Summand „Monate × Preis“; gleiche Preise in Folge zusammen.

    Wie `phasensumme` läuft der letzte Preis über Monate weiter, die keine Phase
    nennt; `kosten_ueber` ruft es nur für Monate, die eine Phase nennt (ohne
    Kernzahl für die belegten Monate vor der ersten Lücke).
    """
    paare: list[tuple[int, float]] = []
    for phase in sorted(phasen, key=lambda p: p.von_monat):
        if phase.monate(h) > 0:
            paare.append((phase.monate(h), phase.betrag))
    if paare and sum(m for m, _ in paare) < h:
        letzter = sorted(phasen, key=lambda p: p.von_monat)[-1].betrag
        paare.append((h - sum(m for m, _ in paare), letzter))
    schritte: list[Rechenschritt] = []
    for monate, betrag in paare:
        if schritte and schritte[-1].betrag == betrag:
            monate += schritte.pop().anzahl or 0
        schritte.append(
            Rechenschritt(SCHRITT_TARIF, monate, betrag, round(monate * betrag, 2))
        )
    return schritte


def tarifmonate(buendel: Buendel) -> int:
    """Wie viele Monate der Tarif zählt: seine Mindestlaufzeit, ohne Angabe oder
    ohne Bindung `ZEITRAUM_OHNE_BINDUNG` Monate (§ 56 TKG: höchstens 24).

    Laufen die Raten länger, zahlt man danach nur noch die Rate: der Ratenkauf ist
    ein eigener Vertrag, der Tarif ab dann monatlich kündbar (Antonio, 10.10.2026).
    """
    pflicht = _pflicht(buendel)
    return pflicht if pflicht > 0 else ZEITRAUM_OHNE_BINDUNG


def _pflicht(buendel: Buendel) -> int:
    bindung = buendel.tarif_bindung_monate
    return ZEITRAUM_OHNE_BINDUNG if bindung is None else bindung


def tarifphasen(buendel: Buendel) -> list[Preisphase]:
    """Die Phasen, mit denen `kosten_ueber` den Tarif rechnet: die belegten, sonst der
    gemessene Grundpreis bis zum Ende der Bindung."""
    pflicht = _pflicht(buendel)
    return belegte_phasen(buendel.tarif_phasen, pflicht) or _grundpreis_als_phase(
        buendel.tarif_monatlich, pflicht
    )


def tarifpreis_im_monat(buendel: Buendel, monat: int) -> float | None:
    """Der Tarifpreis in `monat`, wie `kosten_ueber` ihn rechnet - None, wo nicht genau
    eine Phase den Monat nennt (dort rechnet `kosten_ueber` eine Lücke)."""
    treffer = [
        p
        for p in tarifphasen(buendel)
        if p.von_monat <= monat and (p.bis_monat is None or monat <= p.bis_monat)
    ]
    return round(float(treffer[0].betrag), 2) if len(treffer) == 1 else None


def belegte_phasen(phasen: list[Preisphase], bindung: int | None) -> list[Preisphase]:
    """Die Preisphasen, soweit die Quelle ihre Monate wirklich nennt.

    Eine einzige Phase ab Monat 1 ohne Ende ist keine Phasentabelle, sondern der
    Grundpreis: so schreibt ihn der Leser eines Produktinformationsblatts, das keine
    Phasen nennt. Sie gilt wie `_grundpreis_als_phase` nur bis zum Ende der Bindung
    (ohne Bindung 24 Monate). Über die Bindung hinaus trägt nur eine Tabelle, die
    einen späteren Monat ausdrücklich nennt - für jeden Anbieter dieselbe Regel
    (Datenkonzept Geräte 5.3: nennt die Quelle den Preis ab Monat 25 nicht, ist das
    Bündel in der 36er-Ansicht eine Lücke).
    """
    if len(phasen) == 1 and phasen[0].von_monat == 1 and phasen[0].bis_monat is None:
        pflicht = ZEITRAUM_OHNE_BINDUNG if bindung is None else bindung
        return _grundpreis_als_phase(phasen[0].betrag, pflicht)
    return list(phasen)


def _grundpreis_als_phase(preis: float | None, bindung: int) -> list[Preisphase]:
    """Der gemessene Grundpreis als Phase bis zum Ende der Bindung; ohne Bindung
    (0 Monate) gilt er `ZEITRAUM_OHNE_BINDUNG` Monate wie bei unbekannter Bindung."""
    if preis is None:
        return []
    return [Preisphase(1, bindung if bindung > 0 else ZEITRAUM_OHNE_BINDUNG, preis)]


def _geraet_und_anschluss(k: Kosten, buendel: Buendel) -> None:
    """Anzahlung und, in getrennter Preisform, alle N Raten; dann der Anschluss."""
    from .tco_model import (
        POSTEN_ANSCHLUSS,
        POSTEN_LAUFZEIT,
        POSTEN_RATE,
        POSTEN_ZUZAHLUNG,
    )

    if _mit_abloese(buendel, k.monate):
        _posten(k, POSTEN_EINMALZAHLUNG, buendel.geraet_zuzahlung, SCHRITT_ABLOESE)
    elif not buendel.ohne_geraet:
        _posten(k, POSTEN_ZUZAHLUNG, buendel.geraet_zuzahlung, SCHRITT_ANZAHLUNG)
    if not buendel.ohne_geraet and buendel.buendel_monatlich is None:
        rate, laufzeit = buendel.geraet_monatsrate, buendel.laufzeit_monate
        if rate is None:
            k.luecken.append(POSTEN_RATE)
        elif laufzeit is None:
            k.luecken.append(POSTEN_LAUFZEIT)
        else:
            summe = round(rate * laufzeit, 2)
            k.posten[f"Geräteraten über {laufzeit} Monate"] = summe
            k.rechnung.append(Rechenschritt(SCHRITT_GERAET, laufzeit, rate, summe))
    _posten(k, POSTEN_ANSCHLUSS, buendel.anschlusspreis, SCHRITT_ANSCHLUSS)


def _mit_abloese(buendel: Buendel, h: int | None) -> bool:
    """Ein Vertrag, der vor seinem Ende gerechnet wird: die Zuzahlung ist die Ablöse."""
    laufzeit = buendel.laufzeit_monate
    return (
        buendel.buendel_monatlich is not None
        and laufzeit is not None
        and h is not None
        and h < laufzeit
    )


def _posten(k: Kosten, name: str, betrag: float | None, art: str) -> None:
    """Ein gemessener Betrag wird Posten, ein fehlender Lücke; 0,00 € ist gemessen."""
    if betrag is None:
        k.luecken.append(name)
    else:
        k.posten[name] = betrag
        k.rechnung.append(Rechenschritt(art, None, betrag, betrag))


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
