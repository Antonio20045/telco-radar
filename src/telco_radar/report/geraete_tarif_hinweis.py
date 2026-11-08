"""Der Satz im Rechenweg, wenn die Raten länger laufen als der Tarif."""

from __future__ import annotations

from html import escape


def tarif_hinweis(tarifmonate_: int, h: int | None) -> str:
    """Der Absatz (HTML) unter der Postenliste, wenn die Raten den Tarif überdauern.

    Bei 36 Raten steht „Kosten über 36 Monate“ über einer Summe mit nur 24 Tarifmonaten
    (Datenkonzept Geräte 5.3: Tarif höchstens 24 Monate Bindung, § 56 TKG, danach
    monatlich kündbar; der Ratenkauf läuft als eigener Vertrag weiter). Ohne diesen
    Satz läse sich die Summe als 36 Monate Tarif und wäre zu niedrig. Ein Tarif, den
    man behält, kostet ab dem Folgemonat zusätzlich. Gleiche Regel für jeden Anbieter.
    """
    if h is None or h <= tarifmonate_:
        return ""
    von = tarifmonate_ + 1
    satz = (
        f"Der Tarif zählt nur {tarifmonate_} Monate (Mindestlaufzeit, danach monatlich "
        f"kündbar); in Monat {von} bis {h} zählt nur die Geräterate. Wer den Tarif "
        f"behält, zahlt ab Monat {von} zusätzlich den Tarifpreis."
    )
    return f"<p class='gr-zr-roffen'>{escape(satz)}</p>"
