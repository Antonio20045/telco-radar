"""Das Alter einer Klick-Messung - und was es kostet, wenn sie trotzdem Vorrang
hat.

Befund 13.11.2026 (Lauf 43401542782): congstar verlor 26 von 38 Modellen aus dem
Messtag. Der Klick-Lauf hatte an diesem Tag alle 45 congstar-Produktseiten gelesen
(752 erfasste Kombinationen), seine Sätze durften den Adaptersatz aber nicht
ersetzen - der congstar-Adapter nennt seit dem 12.11.2026 eine EINGERECHNETE Aktion
(``anschluss_erlassen``), die der Klick nicht liest (``klick_vollstaendig``). Damit
blieb kein Klick-Bündel von heute übrig, und die zwei Tage alten Einträge vom
11.11. verdrängten über ``klick_messtag.klickalter`` die frische Adaptermessung: der
Bestandseintrag behielt sein altes ``last_verified``, das Bündel fehlte im Messtag,
und der Bündelwächter wurde rot, ohne dass ein Protokoll den Grund nannte.

Seitdem gilt NUR für congstar (``klick_messtag.ANBIETER_PREISGRENZE`` - der Befund
betraf nur diesen Anbieter): eine Klick-Messung, die NICHT von heute ist, verdrängt
eine heutige Adaptermessung nur, wenn diese ihr widerspricht (``klick_preisgrenze``).
Bei jedem anderen Anbieter verdrängt sie weiterhin unbedingt, wie vor diesem Befund.
Ein congstar-Widerspruch ist kein stiller Verlust mehr, sondern eine Zeile je
Anbieter - ``widerspruch_zeilen`` (CLAUDE.md Clean Code 5 und 6).
"""

from __future__ import annotations

from datetime import date

BEISPIELE = 3


def alter_tage(datum: object, heute: str) -> int | None:
    """Tage von ``datum`` bis ``heute``; ``None``, wenn ``datum`` kein ISO-Datum ist."""
    try:
        return (date.fromisoformat(heute) - date.fromisoformat(str(datum))).days
    except ValueError:
        return None


def widerspruch_zeilen(widerspruch: list[tuple], heute: str) -> list[str]:
    """Je Anbieter eine Protokollzeile: wie viele heute gemessene Bündel einer
    älteren Klick-Messung weichen, weil ihr Preis ihr widerspricht, mit Beispielen.

    ``widerspruch`` ist je Eintrag ``(Bündel, Bestandseintrag, Felder)``. Eine
    Klick-Messung von heute kostet keinen Messtag und steht deshalb nicht darin.
    """
    je_anbieter: dict[str, list[tuple[int, str, list[str]]]] = {}
    for satz, eintrag, felder in widerspruch:
        alter = alter_tage((eintrag or {}).get("abgerufen_am"), heute)
        if not alter:
            continue
        je_anbieter.setdefault(satz.anbieter, []).append((alter, satz.id, felder))
    zeilen = []
    for anbieter, faelle in sorted(je_anbieter.items()):
        beispiele = "; ".join(
            f"{kennung}: {', '.join(felder)}"
            for _, kennung, felder in faelle[:BEISPIELE]
        )
        zeilen.append(
            f"Klick-Widerspruch {anbieter}: {len(faelle)} heute gemessene Bündel "
            f"weichen einer Klick-Messung von vor {max(a for a, _, _ in faelle)} "
            f"Tag(en) und fehlen deshalb im Messtag {heute} - lieber kein Preis als "
            f"ein falscher ({beispiele})"
        )
    return zeilen
