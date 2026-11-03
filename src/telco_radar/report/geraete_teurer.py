"""Wo Vodafone bei einem Gerät deutlich teurer ist (Antonio, 10.10.2026).

Zwei Listen für die Geräteseite, je eine für den Umschalter "Mit Tarif" und
"Einzelgerät". Eine Zeile steht in der Liste, wenn Vodafone mindestens
`SCHWELLE_PROZENT` über dem günstigsten Wettbewerber liegt, gemessen am
Wettbewerberpreis (D1, 14.10.2026).

Mit Tarif liest das Bündel, das auch das Diagramm "Preispositionierung"
zeigt: Tarif M, 24 Monate, nur geprüfte Preise (`tco_vodafone_teurer` aus
`geraete_view`, Karten von `geraete_preisposition_preise`), das günstigste
fremde Bündel gegen Vodafone. Einzelgerät
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


def vergleich_m(karten: dict[str, dict]) -> dict | None:
    """Vodafone gegen das günstigste fremde Bündel auf der Basis des Diagramms.

    `karten` ist `geraete_preisposition_preise.preise_je_anbieter` (Anbieter ->
    Karte, Tarif M, 24 Monate, geprüft): dieselben Zahlen wie die Punkte des
    Diagramms. Fehlt Vodafone oder jeder Fremde, gibt es keinen Vergleich
    (`None`, eine Lücke, nie eine 0)."""
    eigen = next((k for k in karten.values() if k.get("eigen")), None)
    fremde = [k for k in karten.values() if not k.get("eigen")]
    if eigen is None or not fremde:
        return None
    bester = min(fremde, key=lambda k: (k["gesamt"], k["anbieter"] or ""))
    return {
        "anbieter": bester["anbieter"],
        "preis": bester["gesamt"],
        "vodafone": eigen["gesamt"],
        "band": bester.get("band"),
        "band_label": band_label(bester.get("band")),
    }


def mit_tarif(katalog_modelle: list[dict]) -> list[dict]:
    """Modelle, bei denen das Bündel bei Vodafone über der Schwelle teurer ist.

    Gerechnet wird auf der Basis des Diagramms (`vergleich_m`, Tarif M, 24
    Monate, geprüfte Preise): Betrag, Abstand und Prozent sind dort dieselben
    wie im Diagramm. Ein Modell ohne diesen Vergleich steht nicht in der Liste.
    """
    zeilen = []
    for m in katalog_modelle:
        b = m.get("tco_vodafone_teurer")
        if not b:
            continue
        p = prozent(b["vodafone"], b["preis"])
        if p is None or p < SCHWELLE_PROZENT:
            continue
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
