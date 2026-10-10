"""Wo Vodafone bei einem Gerät deutlich teurer ist (Antonio, 10.10.2026).

Zwei Listen für die Geräteseite, je eine für den Umschalter "Mit Tarif" und
"Einzelgerät". Eine Zeile steht in der Liste, wenn der günstigste Wettbewerber
mindestens `SCHWELLE_PROZENT` unter Vodafone liegt, gemessen am Vodafone-Preis.

Mit Tarif liest die fertigen Abstände des Katalogs (`tco_delta`,
`tco_delta_prozent` aus `geraete_tco_karten`): derselbe Vergleich wie in der
Tabelle "Alle Geräte", also dasselbe Band und dieselbe Laufzeit. Einzelgerät
liest den letzten gemessenen Preis je Anbieter aus dem Preisverlauf.
"""

from __future__ import annotations

from .anbieter_farben import slug_fuer

SCHWELLE_PROZENT = 10.0


def mit_tarif(katalog_modelle: list[dict]) -> list[dict]:
    """Modelle, bei denen das Bündel bei Vodafone über der Schwelle teurer ist.

    `tco_delta` ist Wettbewerber minus Vodafone; negativ heißt Vodafone teurer.
    Der Vodafone-Betrag ist die Umkehrung desselben Abstands.
    """
    zeilen = []
    for m in katalog_modelle:
        abstand, prozent, preis = (
            m.get("tco_delta"),
            m.get("tco_delta_prozent"),
            m.get("tco_ab"),
        )
        if abstand is None or prozent is None or preis is None:
            continue
        if abstand >= 0 or prozent < SCHWELLE_PROZENT:
            continue
        zeilen.append(
            {
                "id": m.get("schluessel"),
                "titel": m.get("titel"),
                "anbieter": m.get("tco_anbieter"),
                "klasse": slug_fuer(m.get("tco_anbieter") or ""),
                "preis": preis,
                "vodafone": round(preis - abstand, 2),
                "abstand": round(-abstand, 2),
                "prozent": prozent,
                "band": m.get("tco_band"),
                "band_label": m.get("tco_band_label"),
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
        bester = min(fremd, key=lambda p: p["preis"])
        if not vodafone:
            continue
        prozent = round((vodafone - bester["preis"]) / vodafone * 100, 1)
        if prozent < SCHWELLE_PROZENT:
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
                "prozent": prozent,
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
