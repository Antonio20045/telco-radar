"""Wo Vodafone bei einem Gerät deutlich teurer ist (Antonio, 10.10.2026).

Zwei Listen für die Geräteseite, je eine für den Umschalter "Mit Tarif" und
"Einzelgerät". Eine Zeile steht in der Liste, wenn Vodafone mindestens
`SCHWELLE_PROZENT` über dem günstigsten Wettbewerber liegt, gemessen am
Wettbewerberpreis (D1, 14.10.2026).

Mit Tarif liest je Band das günstigste fremde Bündel samt Vodafone-Referenz
desselben Bands (`tco_vodafone_teurer` aus `geraete_view`), alle Bänder der
Standardansicht (D3). Einzelgerät
liest den letzten gemessenen Preis je Anbieter aus dem Preisverlauf.
"""

from __future__ import annotations

from .anbieter_farben import slug_fuer
from .geraete_tco_band import band_label

SCHWELLE_PROZENT = 10.0


def prozent(vodafone: float, preis: float) -> float | None:
    """Um wie viel Prozent Vodafone teurer ist - gemessen am Wettbewerberpreis.

    D1 (Antonio, 14.10.2026): "bei Vodafone über 10 % teurer" meint
    wörtlich den Wettbewerberpreis als Basis. Die eine Formel für beide
    Listen.
    """
    if not preis:
        return None
    return round((vodafone - preis) / preis * 100, 1)


def mit_tarif(katalog_modelle: list[dict]) -> list[dict]:
    """Modelle, bei denen das Bündel bei Vodafone über der Schwelle teurer ist.

    Geprüft werden alle Bänder der Standardansicht (D3, 14.10.2026,
    `tco_vodafone_teurer` aus `geraete_view._tco_spalte`): je Band das
    günstigste fremde Bündel gegen Vodafone im selben Band. Liegt das Band des
    insgesamt günstigsten Angebots (`tco_band`) über der Schwelle, zeigt die
    Liste dieses Band wie bisher; sonst das Band mit dem höchsten Prozentsatz.
    """
    zeilen = []
    for m in katalog_modelle:
        kandidaten = []
        for b in m.get("tco_vodafone_teurer") or []:
            p = prozent(b["vodafone"], b["preis"])
            if p is not None and p >= SCHWELLE_PROZENT:
                kandidaten.append((p, b))
        if not kandidaten:
            continue
        p, b = max(
            kandidaten,
            key=lambda pb: (pb[1]["band"] == m.get("tco_band"), pb[0], -pb[1]["preis"]),
        )
        zeilen.append(
            {
                "id": m.get("schluessel"),
                "titel": m.get("titel"),
                "anbieter": b["anbieter"],
                "klasse": slug_fuer(b["anbieter"] or ""),
                "preis": b["preis"],
                "vodafone": b["vodafone"],
                "abstand": round(b["vodafone"] - b["preis"], 2),
                "prozent": p,
                "band": b["band"],
                "band_label": b["band_label"],
            }
        )
    return sorted(zeilen, key=lambda z: (-z["abstand"], z["titel"] or ""))


def einzelgeraet(geraete: list[dict]) -> list[dict]:
    """Geräte, die ohne Vertrag bei Vodafone über der Schwelle teurer sind.

    Verglichen wird der letzte gemessene Preis je Anbieter (`aktuell`); ohne
    Vodafone-Preis fällt das Gerät heraus, es ist nicht vergleichbar.
    """
    zeilen = []
    for g in geraete:
        preise = g.get("aktuell") or []
        eigen = [p for p in preise if p.get("eigen")]
        fremd = [p for p in preise if not p.get("eigen")]
        if not eigen or not fremd:
            continue
        vodafone = eigen[0]["preis"]
        bester = min(fremd, key=lambda p: (p["preis"], p["anbieter"] or ""))
        if not vodafone:
            continue
        anteil = prozent(vodafone, bester["preis"])
        if anteil is None or anteil < SCHWELLE_PROZENT:
            continue
        zeilen.append(
            {
                "id": g.get("id"),
                "titel": g.get("label"),
                "anbieter": bester["anbieter"],
                "klasse": slug_fuer(bester["anbieter"]),
                "preis": bester["preis"],
                "vodafone": vodafone,
                "abstand": round(vodafone - bester["preis"], 2),
                "prozent": anteil,
            }
        )
    return sorted(zeilen, key=lambda z: (-z["abstand"], z["titel"] or ""))


def listen(geraete: dict) -> dict:
    """Beide Listen zur fertigen Geräteansicht."""
    return {
        "tarif": mit_tarif(geraete.get("katalog_modelle") or []),
        "geraet": einzelgeraet(((geraete.get("verlauf") or {}).get("geraete")) or []),
        "schwelle": SCHWELLE_PROZENT,
    }


def je_band(zaehlende: list) -> list[dict]:
    """Je Band das günstigste fremde Bündel, das unter Vodafone liegt.

    D3 (Antonio, 14.10.2026): "Mit Tarif über 10 % teurer" prüft ALLE
    Bänder, nicht nur das Band des insgesamt günstigsten Angebots. Der
    Vodafone-Betrag ist die Referenz derselben Karte (`delta`, gleiches
    Band, gleiche Laufzeit): Kosten minus Abstand.
    """
    je_band: dict[str, dict] = {}
    for k in zaehlende:
        delta = k.get("delta") or {}
        if k.get("eigen") or delta.get("betrag") is None or delta["betrag"] >= 0:
            continue
        bisher = je_band.get(k.get("band"))
        if bisher is None or k["gesamt"] < bisher["preis"]:
            je_band[k.get("band")] = {
                "anbieter": k.get("anbieter"),
                "preis": k["gesamt"],
                "vodafone": round(k["gesamt"] - delta["betrag"], 2),
                "band": k.get("band"),
                "band_label": band_label(k.get("band")),
            }
    return list(je_band.values())
