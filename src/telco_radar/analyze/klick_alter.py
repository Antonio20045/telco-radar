"""Das Alter einer Klick-Messung - und was es kostet, wenn sie trotzdem Vorrang
hat.

Ein Adapterbündel weicht einer Klick-Messung, die jünger als
``FRISCHEGRENZE_TAGE`` ist (`klick_zusammenfuehrung._vorrang`). Ist diese Messung
nicht von HEUTE, behält ihr Bestandseintrag sein altes ``last_verified`` - das
Bündel fehlt dann im Messtag, obwohl der Adapter es heute am Original gesehen
hat. Der Bündelwächter liest genau diesen Messtag und wird rot, ohne dass ein
Protokoll den Grund nennt.

Befund 13.11.2026 (Lauf 43401542782): congstar verlor so 26 von 38 Modellen -
der Klick-Lauf war seit dem 11.11. überfällig, und seine zwei Tage alten
Einträge verdrängten die frische Adaptermessung aller 45 Produktseiten.

Die Lücke bleibt ein Befund des Wächters. Sie wird hier nur BENANNT, statt still
zu bleiben (CLAUDE.md Clean Code 5 und 6).
"""

from __future__ import annotations

from datetime import date


def alter_tage(datum: object, heute: str) -> int | None:
    """Tage von ``datum`` bis ``heute``; ``None``, wenn ``datum`` kein ISO-Datum ist."""
    try:
        return (date.fromisoformat(heute) - date.fromisoformat(str(datum))).days
    except ValueError:
        return None


def vorrang_ohne_messtag(gewichen: list[tuple], heute: str) -> list[str]:
    """Je Anbieter eine Protokollzeile; eine Klick-Messung von heute kostet
    keinen Messtag und steht deshalb nicht darin."""
    je_anbieter: dict[str, list[int]] = {}
    for satz, eintrag in gewichen:
        alter = alter_tage((eintrag or {}).get("abgerufen_am"), heute)
        if not alter:
            continue
        je_anbieter.setdefault(satz.anbieter, []).append(alter)
    return [
        f"Klick-Vorrang {anbieter}: {len(alter)} heute gemessene Bündel weichen "
        f"einer Klick-Messung von vor {max(alter)} Tag(en) und fehlen deshalb im "
        f"Messtag {heute} - der Klick-Lauf dieses Anbieters ist überfällig"
        for anbieter, alter in sorted(je_anbieter.items())
    ]
