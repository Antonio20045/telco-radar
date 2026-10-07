"""Der Tarifpreis über die ganze Ratenlaufzeit - nur, wo der Anbieter ihn nennt.

Datenkonzept Geräte 5.3, Regel 8: die 36er-Ansicht rechnet 36 Tarifmonate. Ein
gemessener Tarifpreis ohne Phase ist nur bis zum Ende der Bindung belegt
(`tco_kosten.belegte_phasen`), Monat 25 bis 36 sind dann eine Lücke. Zwei Anbieter
nennen den Preis bis zur letzten Rate selbst:

o2        Der Ratenplan-Hinweis der Konfiguration (`hardware.contents.` +
          `RATENPLAN_HINWEIS`), gemessen am 07.10.2026 beim Galaxy S26 und beim
          iPhone 17 Pro (Klick-Erkundung): "Entscheidest du dich zudem für einen
          passenden Mobilfunktarif, so erhältst du über die gesamte Laufzeit deines
          Geräte-Ratenplans (24 oder 36) einen attraktiven monatlichen Rabatt auf
          deinen Tarif." Belegt ist das nur für einen Tarif, dessen Konfiguration
          die Ratenzahl trägt ("…-hwv-36m-05-00" zu 36 Raten); "…-online-hwv" und
          "…-online-promo" nennen keine.
congstar  Der Tarifpreis ohne Rabattphase (`prices.recurring`: `discounts` leer,
          `listed` gleich `discounted`). Die Produktseite rechnet ihn über alle
          Raten und danach ("Summe 1. bis 36. Monat … Tarif 25,00 €", "Summe ab
          dem 37. Monat 25,00 €", iPhone 17 Pro, Klick-Erkundung 07.10.2026). Ein
          Nachlass, auch ein dauerhafter, ist kein Beleg.

Die Phase reicht von Monat 1 bis zur letzten Rate, nie darüber hinaus, und trägt
ihren Beleg (`tarif_model.Buendelphase`). Ohne Beleg bekommt ein Satz keine.
"""

from __future__ import annotations

import base64
import logging
import re

from .basis import _gleich, _preis

log = logging.getLogger(__name__)

PHASEN = "tarif_phasen"
ZAEHLER_BELEGT = "ratenplan_belegt"
RATENPLAN_HINWEIS = "selectedHardwareRateDurationModal"
_RATENPLAN_TYP = "pdp:HardwareDurationSelectionModal"
_RATENPLAN_SATZ_RE = re.compile(
    r"[^.<>]*über die gesamte Laufzeit deines Geräte-Ratenplans[^.<>]*"
    r"Rabatt auf deinen Tarif\."
)
_TARIF_RATEN_RE = re.compile(r"-hwv-(?P<raten>\d+)m-")


def ganze_ratenlaufzeit(beleg: str | None, laufzeit, betrag) -> list[dict]:
    """Der Tarifpreis als eine Phase von Monat 1 bis `laufzeit` - nur mit Beleg."""
    if beleg is None or laufzeit is None or betrag is None:
        return []
    return [{"von_monat": 1, "bis_monat": laufzeit, "betrag": betrag, "beleg": beleg}]


def ratenplan_satz(pv: dict) -> str | None:
    """Der Satz des o2-Ratenplan-Hinweises, der den Tarifrabatt an die Raten bindet;
    None ohne Hinweis oder ohne diesen Satz."""
    hinweis = ((pv.get("hardware") or {}).get("contents") or {}).get(RATENPLAN_HINWEIS)
    if not isinstance(hinweis, dict) or hinweis.get("@type") != _RATENPLAN_TYP:
        return None
    m = _RATENPLAN_SATZ_RE.search(str(hinweis.get("infoBody") or ""))
    return " ".join(m.group(0).split()) if m else None


def konfiguration(uri: str) -> dict[str, str]:
    """Die Teile der o2-Konfigurations-ID am Ende einer Konfigurationsadresse.

    o2 kodiert "type=…;hardware=o2shop::<Angebot>;tariff=o2shop::<Tarif>;…" in
    Base64; geliefert wird {Teil: Wert ohne "o2shop::"}, leer bei einer Adresse
    ohne lesbare ID.
    """
    kennung = uri.rstrip("/").rsplit("/", 1)[-1]
    try:
        text = base64.b64decode(
            kennung + "=" * (-len(kennung) % 4), validate=True
        ).decode("utf-8")
    except ValueError as exc:
        log.info("o2: Adresse %s ohne lesbare Konfigurations-ID (%s)", uri, exc)
        return {}
    teile: dict[str, str] = {}
    for teil in text.split(";"):
        name, _, wert = teil.partition("=")
        teile[name] = wert.rsplit("::", 1)[-1]
    return teile


def o2_phasen(pv: dict, uri: str, g: dict, betrag: float, zaehler: dict) -> list[dict]:
    """Die Phase eines o2-Satzes: `pv` ist die Konfigurationsantwort, `uri` die
    Adresse seiner Tarifoption, `g` der gemessene Satz der Antwort (`o2._gemessen`).

    Belegt, wenn die Antwort den Satz des Hinweises trägt UND die Konfiguration genau
    dieses Angebot mit einem Tarif für dieselbe Ratenzahl verbindet. Jeder belegte
    Satz wird unter `ZAEHLER_BELEGT` gezählt.
    """
    satz = ratenplan_satz(pv)
    teile = konfiguration(uri)
    tarif = teile.get("tariff", "")
    m = _TARIF_RATEN_RE.search(tarif)
    if (
        satz is None
        or teile.get("hardware") != g["angebot"]
        or not m
        or int(m.group("raten")) != g["laufzeit"]
    ):
        return []
    zaehler[ZAEHLER_BELEGT] = int(zaehler.get(ZAEHLER_BELEGT, 0)) + 1
    beleg = f"{RATENPLAN_HINWEIS}: {satz} Tarif {tarif}"
    return ganze_ratenlaufzeit(beleg, g["laufzeit"], betrag)


def katalog_mit_phasen(katalog: list, tief: list) -> list:
    """Die o2-Katalogsätze, jeder mit den Phasen seines Zwillings aus der Vertiefung.

    Der Katalog trägt den Hinweis nicht. Derselbe Angebotsname mit demselben Tarif-
    Slug ist dasselbe Bündel (`o2.fuehre_zusammen`); übernommen wird nur zum selben
    Tarifpreis, sonst bleibt der Satz, wie er ist.
    """
    tief_je = {(s.get("angebot"), s.get("tarif_slug")): s for s in tief}
    return [_mit_phasen_des_zwillings(s, tief_je) for s in katalog]


def _mit_phasen_des_zwillings(satz: dict, tief_je: dict) -> dict:
    zwilling = tief_je.get((satz.get("angebot"), satz.get("tarif_slug"))) or {}
    preis = satz.get("tarif_monatlich")
    if not zwilling.get(PHASEN) or not _gleich(zwilling.get("tarif_monatlich"), preis):
        return satz
    return {**satz, PHASEN: [{**p, "betrag": preis} for p in zwilling[PHASEN]]}


def congstar_phasen(saetze: list[dict], preis) -> list[dict]:
    """Die congstar-Sätze eines Plans, jeder mit seiner Phase oder ohne.

    `preis` ist `prices.recurring` des Plans, aus dessen `discounted` der Tarifpreis
    jedes Satzes stammt.
    """
    beleg = _ohne_rabattphase(preis)
    for satz in saetze:
        satz[PHASEN] = ganze_ratenlaufzeit(
            beleg, satz.get("laufzeit_monate"), satz.get("tarif_monatlich")
        )
    return saetze


def _ohne_rabattphase(preis) -> str | None:
    if not isinstance(preis, dict) or preis.get("discounts") != []:
        return None
    listed, discounted = _preis(preis.get("listed")), _preis(preis.get("discounted"))
    if listed is None or discounted is None or not _gleich(listed, discounted):
        return None
    betrag = f"{discounted:.2f}".replace(".", ",")
    return (
        f"prices.recurring: listed {betrag} € = discounted {betrag} €, "
        "discounts [] (keine Rabattphase)"
    )
