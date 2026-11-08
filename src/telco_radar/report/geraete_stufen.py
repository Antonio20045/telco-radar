"""Hat ein Anbieter in einer Tarifstufe überhaupt einen gemessenen Tarif?

Ein Preis kann in einer Zelle der Tafel aus zwei Gründen fehlen: dem Anbieter
fehlt für dieses Gerät die Messung (echte Lücke), oder er hat in dieser Stufe
gar keinen Tarif (kein Gerät kann dort einen Preis haben). Nur der zweite Fall
bekommt einen eigenen Text, und nur wenn die Zahl der gemessenen Tarife des
Anbieters in der Stufe NULL ist.

Gezählt wird aus zwei gemessenen Listen, zusammen und ohne Doppelzählung:
der Tarifliste (`data/state/tarife.jsonl`, je Tarif das Datenvolumen, die Stufe
kommt aus `band_je_tarif`) und den Bündeln aller Geräte (`karten`, Feld
`band`). Beide ordnen dieselbe Regel (`band_regel.stufe_fuer`, nächstes
Datenvolumen der Vodafone-Tarifleiter) zu. Ein Tarif ohne Stufe (unbegrenzt,
ohne erhobenes Volumen) steht auf der Seite unter „Ohne Tarifband“; er könnte in
jede Stufe fallen. Darum gilt der Anbieter dann als nicht bestimmbar und fehlt im
Bestand: für ihn wird in keiner Stufe „keinen Tarif“ behauptet (fail-closed), ebenso
für einen Anbieter ohne einen einzigen Tarif in irgendeiner Stufe.
"""

from __future__ import annotations

TARIFSTUFEN_REGEL = (
    "Die Tarifstufen XS bis XL teilen alle Tarife nach ihrem Datenvolumen ein, "
    "Maßstab sind die Vodafone-Stufen. Fällt kein Tarif eines Anbieters in eine "
    "Stufe, bleibt sie bei ihm leer, auch wenn er viele Tarife hat."
)
FESTNETZ = "festnetz"
KEIN_TARIF_KURZ = "Hat in dieser Tarifstufe keinen Tarif"
KEIN_TARIF_SATZ = "{anbieter} hat in dieser Tarifstufe keinen Tarif"


def tarife_je_stufe(
    modelle: list, tarife: dict | None, band_je_tarif: dict | None
) -> dict[str, dict[str, int]]:
    """`{Anbieter: {Stufe: Zahl verschiedener gemessener Tarife}}`.

    Nur Stufen mit mindestens einem Tarif stehen darin, nur Anbieter mit
    mindestens einem Tarif in irgendeiner Stufe und ohne Tarif, dessen Stufe
    nicht bestimmbar ist."""
    band_je_tarif = band_je_tarif or {}
    gesehen: dict[str, dict[str, set]] = {}
    unbestimmt: set[str] = set()

    def zaehle(anbieter, stufe, tarif_id) -> None:
        if anbieter and stufe and tarif_id:
            gesehen.setdefault(anbieter, {}).setdefault(stufe, set()).add(tarif_id)
        elif anbieter:
            unbestimmt.add(anbieter)

    for tarif_id, satz in (tarife or {}).items():
        if (satz or {}).get("art") != FESTNETZ:
            zaehle((satz or {}).get("anbieter"), band_je_tarif.get(tarif_id), tarif_id)
    for modell in modelle:
        for karte in modell.get("karten") or []:
            if karte.get("sku_id") or karte.get("naeherung"):
                zaehle(
                    karte.get("anbieter"),
                    karte.get("band"),
                    (karte.get("tarif_id") or karte.get("tarif") or "").strip(),
                )
    return {
        a: {s: len(t) for s, t in je.items()}
        for a, je in gesehen.items()
        if a not in unbestimmt
    }


def haenge_an(modelle: list, tarife: dict | None, band_je_tarif: dict | None) -> None:
    """Gibt jedem Modell denselben Bestand (`modell["stufen"]`)."""
    stufen = tarife_je_stufe(modelle, tarife, band_je_tarif)
    for modell in modelle:
        modell["stufen"] = stufen


def stufe_ohne_tarif(stufen: dict | None, anbieter: str, band: str) -> bool:
    """Wahr nur, wenn der Anbieter gemessen ist und in `band` null Tarife hat.

    Fail-closed: ohne Bestand (`None`), für einen Anbieter ohne gemessenen
    Tarif oder bei einem Tarif in der Stufe ist die Antwort Nein."""
    je_stufe = (stufen or {}).get(anbieter)
    if not je_stufe:
        return False
    return not je_stufe.get(band, 0)
