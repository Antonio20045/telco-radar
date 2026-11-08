"""Der Zeitraum einer Kostenzahl in Worten - die EINE Quelle für jedes Etikett.

Die Summe eines Bündels mit 36 Geräteraten enthält 24 Tarifmonate und 36
Geräteraten (Datenkonzept Geräte 5.3). „36 Monate“ allein wäre falsch, denn der
Tarif zählt nur bis zum Ende seiner Bindung. Etikett, Antwortsatz, Graphen,
Rechenweg, Radar und Export lesen ihren Zeitraum alle von hier.
"""

from __future__ import annotations

from ..tco_kosten import ZEITRAUM_OHNE_BINDUNG

NICHT_GEMESSEN = "eine nicht gemessene Laufzeit"


def zeitraum_text(monate: int | None, tarifmonate: int | None = None) -> str:
    """„24 Monate“ - oder „24 Tarifmonate und 36 Geräteraten“, wenn Raten länger laufen.

    Läuft der Tarif so lange wie die Summe (`tarifmonate` >= `monate`), heißt es
    „24 Monate“. Ohne `tarifmonate` gilt `ZEITRAUM_OHNE_BINDUNG`, die Obergrenze
    nach § 56 TKG. Ein nicht gelesener Zeitraum (`None`) wird benannt, nie geraten.
    """
    if monate is None:
        return NICHT_GEMESSEN
    tarif = ZEITRAUM_OHNE_BINDUNG if tarifmonate is None else tarifmonate
    if monate <= tarif:
        return f"{monate} Monate"
    return f"{tarif} Tarifmonate und {monate} Geräteraten"


def zeitraum_wort(monate: list, tarifmonate: int | None = None) -> str:
    """„24 Monate“ / „24 und 36 Monate“ / „24 Tarifmonate und 36 Geräteraten“.

    P0-B-z1: der Titel darf keinen Zeitraum behaupten, der nicht für ALLE Kurven
    gilt. Kommen mehrere vor, nennt er sie; die Zuordnung zur einzelnen Kurve
    steht am Kurvenende. Leere Liste heißt „kein Zeitraum gelesen“ und ergibt
    KEIN Wort (der Aufrufer lässt die Angabe dann weg).
    """
    zahlen = [str(m) for m in monate]
    if not zahlen:
        return ""
    grenze = ZEITRAUM_OHNE_BINDUNG if tarifmonate is None else tarifmonate
    if all(m <= grenze for m in monate):
        if len(zahlen) == 1:
            return f"{zahlen[0]} Monate"
        return f"{', '.join(zahlen[:-1])} und {zahlen[-1]} Monate"
    return " bzw. ".join(zeitraum_text(m, tarifmonate) for m in monate)


def raten_zusatz(monate: list, laufzeit: int | None, trenner: str) -> str:
    """„ · 12 Raten“ - die Ratenzahl neben dem Zeitraum, solange er nur Tarif trägt.

    Über 24 Monate nennt der Zeitraum die Geräteraten schon selbst; die Ratenzahl
    ein zweites Mal wäre dieselbe Angabe doppelt.
    """
    if laufzeit is None or max(monate, default=0) > ZEITRAUM_OHNE_BINDUNG:
        return ""
    return f"{trenner}{laufzeit} Raten"


def zeitraum_der_karte(karte: dict, kurz: bool = True) -> str:
    """Der Zeitraum der Kostenzahl einer Karte, oder "" ohne gelesene Monate.

    `kurz` ist bis 24 Monate die Form „24 Mon.“ neben der Zahl, sonst „24 Monate“.
    """
    monate = karte.get("leitzahl_monate")
    if monate is None:
        return ""
    text = zeitraum_text(monate, karte.get("tarif_monate"))
    return f"{monate} Mon." if kurz and text == f"{monate} Monate" else text


def grund_anderer_zeitraum(
    anbieter: str,
    karte: dict,
    vf_monate: int | None,
    raten: tuple,
    vf_tarifmonate: int | None = None,
) -> str:
    """Der Satz, der eine Zahl mit fremdem Zeitraum benennt (P0-B-h3).

    Er nennt BEIDE Zeitraeume - "nicht vergleichbar" allein liest sich
    wie ein Mangel des Angebots, und der Strich der Prozentspalte hiesse
    "kein Angebot" (A2). Dieselbe Aussage wie an der Buendelzeile
    (`geraete_tco_karten.delta_zustand`), nur an dieser Tabelle in einem
    Satz statt in zwei Feldern. Ein unbekannter Zeitraum wird benannt,
    nicht als 24 geraten (Clean Code 3/4); `raten` nennt beide Ratenlaufzeiten.
    """
    monate = karte.get("leitzahl_monate")
    dieses, gegen = (
        (f"{r} Raten über " if r is not None else "") + zeitraum_text(m, t)
        for r, m, t in zip(
            raten,
            (monate, vf_monate),
            (karte.get("tarif_monate"), vf_tarifmonate),
            strict=True,
        )
    )
    return (
        f"Die Zahl von {anbieter} trägt {dieses}, die Vodafone-Zahl "
        f"{gegen} – über zwei Laufzeiten gibt es keinen Abstand."
    )
