"""Die Katalogzeile „nur im Bündel, ab X €/Monat“: welches Bündel sie nennt.

Aus `geraete_view` ausgelagert (Riesendatei-Basis). Das Ratenwort hinter dem
Monatsbetrag kommt aus `geraete_laufzeit.monatsangabe_zusatz`, derselben Regel wie
das Etikett der Bündelzeile (1&1 „24 + 12“ heißt „24 Monate + Ablöse“).
"""

from __future__ import annotations

from . import geraete_notbremse as notbremse
from . import geraete_tco_karten
from .geraete_laufzeit import monatsangabe_zusatz, rang_der_monatsangabe


def buendel_je_anbieter_modell(
    buendel: list, eintraege: list, katalog, heute: str = ""
) -> tuple[dict, dict]:
    """Zwei Lesarten derselben Bündel-Aufloesung.

    1. `(Anbieter, modell_schluessel) -> das guenstigste zählende Bündel mit
       Monatspreis` (`geraete_notbremse`) - "nur im Bündel, ab X EUR/Monat"
       braucht einen Beleg aus `geraete_tco.json`, NICHT das
       `preis_mit_vertrag_ab` der Listung (Belegzwang).
    2. `modell_schluessel -> {device_id, speicher}` für JEDES Bündel, dessen
       SKU auf ein Geraet aufloest, auch ohne Monatspreis (P5-Auftrag 1:
       schon EIN Bündel ohne Listung stellt die Katalog-Zeile).

    Die Bündel-SKU loest wie in `geraete_tco_karten.modelle()` auf (erst die
    Listung derselben SKU, dann `geraet_aus_sku`) - eine eigene Aufloesung wuesste
    bald etwas anderes als die TCO-Tafel. Der Monatsbetrag ist die Angabe des
    ANBIETERS: `buendel_monatlich` (1&1, § 13.2), sonst Tarif- plus Geraeterate.
    Verglichen wird nur in einer Ratenlaufzeit, 24 Raten zuerst
    (`rang_der_monatsangabe`); die Angabe nennt ihre `laufzeit`.
    """
    modell_je_sku: dict[str, str] = {}
    geraet_je_sku: dict[str, tuple] = {}
    for e in eintraege:
        sku = e.get("sku_id") or ""
        if sku:
            modell_je_sku[sku] = geraete_tco_karten.modell_schluessel(
                e.get("device_id"), e.get("speicher_gb")
            )
            geraet_je_sku[sku] = (e.get("device_id") or "", e.get("speicher_gb"))
    beste: dict = {}
    geraet_je_mid: dict[str, dict] = {}
    for b in buendel or []:
        sku = b.get("sku_id") or ""
        mid = modell_je_sku.get(sku)
        if mid:
            geraet = geraet_je_sku.get(sku, ("", None))
        else:
            geraet = geraete_tco_karten.geraet_aus_sku(sku, katalog)
            if not geraet[0]:
                continue
            mid = geraete_tco_karten.modell_schluessel(*geraet)
        geraet_je_mid.setdefault(mid, {"device_id": geraet[0], "speicher": geraet[1]})
        if not notbremse.felder_aus_satz(b, heute)["zaehlt"]:
            continue
        monat = b.get("buendel_monatlich")
        if monat is None:
            tarif, rate = b.get("tarif_monatlich"), b.get("geraet_monatsrate")
            if tarif is None or rate is None:
                continue
            monat = round(float(tarif) + float(rate), 2)
        monat, laufzeit = float(monat), b.get("laufzeit_monate")
        rang = (rang_der_monatsangabe(laufzeit), monat)
        schluessel = (geraete_tco_karten.normalisiere(b.get("anbieter", "")), mid)
        bisher = beste.get(schluessel)
        if bisher is None or rang < bisher["rang"]:
            beste[schluessel] = {
                "monat": monat,
                "laufzeit": laufzeit,
                "raten_zusatz": monatsangabe_zusatz(
                    laufzeit, b.get("buendel_monatlich")
                ),
                "rang": rang,
                "anbieter": b.get("anbieter", ""),
                "tarif": (b.get("tarif_name") or "").strip(),
                "quelle_url": b.get("quelle_url", ""),
                "abgerufen_am": b.get("abgerufen_am", ""),
            }
    return beste, geraet_je_mid
