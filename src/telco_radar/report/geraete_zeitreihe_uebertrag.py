"""Der jüngste Messtag einer Linie trägt auch die noch frischen Bündel (A5, 08.11.2026).

Aus `geraete_zeitreihe._messungen` ausgelagert: die Auswahl der besseren Messung
je Tag (`besser`), das Merken der letzten Messung je Bündel (`merke`) und der
Übertrag auf den jüngsten Tag (`gilt_weiter`).
"""

from __future__ import annotations

from ..tco_model import zeitraum_vergleichbar
from . import geraete_notbremse as notbremse
from .geraete_laufzeit import ansicht, zeitraum
from .geraete_tco_karten import ist_frisch


class Messtag(str):
    """Der Tag eines Punkts; `gelesen` ist der Tag, an dem sein Bündel wirklich gelesen
    wurde, wenn das ein früherer ist (übertragener Punkt, A5). Gleicht einem `str`,
    damit Sortierung, Fenster und Rechenweg-Schlüssel unverändert bleiben."""

    gelesen: str = ""


def messtag(tag: str, messung: dict) -> str:
    """`tag`, mit dem Lesetag der Messung vermerkt, wenn er vom Punkt-Tag abweicht."""
    gelesen = (messung.get("satz") or {}).get("datum") or tag
    punkt = Messtag(tag)
    punkt.gelesen = gelesen if gelesen != tag else ""
    return punkt


def gelesen_text(tag: str, tag_monat) -> str:
    """„ · gelesen am 7.11.“ für einen übertragenen Punkt, sonst nichts."""
    gelesen = getattr(tag, "gelesen", "")
    return f" · gelesen am {tag_monat(gelesen)}" if gelesen else ""


def gefuehrt(tco: dict) -> set:
    """Die Bündel, die die Tafel (`band_zeilen`) je Modell, Band und Ratenlaufzeit als
    Zeile führen kann: vergleichbar, belastbar, bepreist, zählend und frisch. Nur
    solche Bündel darf der Übertrag auf den jüngsten Tag setzen - sonst zeichnet die
    Linie weiter, wo der Kopfsatz „kein Bündel im Vergleich“ sagt."""
    return {
        (
            m["id"],
            k["band"],
            ansicht(k),
            k["anbieter"],
            k.get("tarif_id"),
            k.get("sku_id"),
        )
        for m in tco.get("modelle") or []
        for k in m.get("karten") or []
        if k.get("band")
        and k.get("vergleichbar")
        and k.get("belastbar")
        and k.get("gesamt") is not None
        and k.get("frisch", True)
        and notbremse.zaehlt(k)
    }


def besser(messung: dict, alt: dict | None, h: int) -> bool:
    """Löst `messung` die bisherige Messung `alt` desselben Tags ab? Zählende vor
    nicht zählenden (F3), bei gleichem Zeitraum der kleinere Wert (strikt `<`:
    die zuerst gelesene Zeile gewinnt), sonst die mit dem Zeitraum H der Ansicht."""
    if alt is None or notbremse.zaehlt(messung) != notbremse.zaehlt(alt):
        return alt is None or notbremse.zaehlt(messung)
    if zeitraum_vergleichbar(messung["monate"], alt["monate"]):
        return messung["wert"] < alt["wert"]
    return zeitraum_vergleichbar(messung["monate"], h)


def merke(
    letzte_je_buendel: dict, schluessel: tuple, hid: str, datum: str, messung: dict
) -> None:
    """Merkt die jüngste Messung des Bündels `hid` auf der Linie `schluessel`
    (Modell, Band, Laufzeit, Anbieter)."""
    letzte = letzte_je_buendel.setdefault(schluessel, {})
    bisher = letzte.get(hid)
    if bisher is None or datum >= bisher[0]:
        letzte[hid] = (datum, messung)


def gilt_weiter(
    messungen: dict, letzte_je_buendel: dict, heute: str, gefuehrt: set
) -> None:
    """Der jüngste Messtag einer Linie trägt auch die noch frischen Bündel, die an
    einem früheren Tag zuletzt gelesen wurden (Live-Abnahme 08.11.2026, A5).

    Die Tafel (`band_zeilen`) nimmt je Anbieter das günstigste FRISCHE Bündel
    (`geraete_tco_karten.ist_frisch`, `ALT_AB_TAGEN`), gleich an welchem Tag es zuletzt
    gelesen wurde. Die Linie nahm je Tag nur die an DIESEM Tag gelesenen: wurde das
    günstigste Bündel (1&1 All-Net-Flat S, 1.591,66 €) zuletzt gestern gelesen und
    heute nur ein teureres im selben Band (Unlimited on demand S, 1.711,66 €), nannte
    die Legende 1.712 € neben einer Zeile mit 1.591,66 €. Jetzt gilt für den jüngsten
    Tag derselbe Wettbewerb wie in der Tafel; die Messung behält ihren eigenen
    Messtag (`satz["datum"]`), den der Rechenweg des Punkts nennt. Ältere Tage bleiben
    unberührt (eine nicht gelesene Zahl ist dort keine gelesene Preisänderung).

    Übertragen wird nur, was die Tafel für dieselbe Wahl auch führt (`gefuehrt`):
    Legende und Tafel dürfen sich nicht widersprechen. Der Tooltip nennt den Lesetag."""
    for (modell, band, laufzeit, anbieter), je_buendel in letzte_je_buendel.items():
        slot = messungen.get((modell, band, laufzeit), {}).get(anbieter)
        if not slot:
            continue
        jungster = max(slot)
        h = zeitraum(laufzeit)
        for datum, messung in sorted(je_buendel.values(), key=lambda e: e[0]):
            if datum >= jungster or not ist_frisch(datum, heute):
                continue
            stand = messung.get("stand") or {}
            schluessel = (modell, band, laufzeit, anbieter)
            if (
                *schluessel,
                stand.get("tarif_id"),
                stand.get("sku_id"),
            ) not in gefuehrt:
                continue
            if besser(messung, slot[jungster], h):
                slot[jungster] = messung
