"""Eine Vodafone-Tarifleiter fuer konstruierte Tarifbestaende in Tests.

Seit P3-E1 (28.09.2026) sind die Tarifbaender der Geraeteseite die
Vodafone-Tarife "mit Smartphone" aus dem Tarifbestand. Ein konstruierter
Bestand ohne sie hat keine Stufe - die Seite zeigt dann ehrlich "Leiter
nicht erhoben". Tests, die Baender pruefen, haengen diese Leiter an.

Die Volumen sind so gewaehlt, dass die Grenzen zwischen den Stufen dort
liegen, wo die alten festen Baender lagen (20/21 und 60/61 GB): XS 5 GB,
M 36 GB, L 85 GB - naechstgelegene Stufe heisst dann bis 20 GB XS, 21 bis
60 GB M, ab 61 GB L. So bleibt die Aussage der bestehenden Fixtures
erhalten, nur die Namen der Stufen sind neu (klein -> xs, mittel -> m,
gross -> l). Die Grundgebuehren sind krumm, damit ein Betrag-Nachschlag
(`Tarifbestand.ueber_betrag`) nie zufaellig hier trifft.
"""
from __future__ import annotations

_STUFEN = (("XS", 5, 29.93), ("M", 36, 49.93), ("L", 85, 59.93))


def _satz(stufe: str, gb: float, grund: float, abgerufen_am: str) -> dict:
    tid = f"vodafone:leiter-{stufe.lower()}-mit-smartphone"
    return {"anbieter": "Vodafone",
            "name": f"Vodafone Mobil {stufe} mit Smartphone",
            "tarif_id": tid, "art": "mobilfunk", "grundgebuehr": grund,
            "laufzeit_monate": 24, "datenvolumen_gb": gb,
            "preisphasen": [{"von_monat": 1, "bis_monat": None,
                             "betrag": grund}],
            "dokument_url": f"https://example.de/pib/{tid}",
            "abgerufen_am": abgerufen_am, "confidence": {},
            "fundstellen": {}}


def leiter_saetze(abgerufen_am: str = "2026-09-28") -> list[dict]:
    """Die drei Saetze der Testleiter (XS, M, L)."""
    return [_satz(s, gb, grund, abgerufen_am) for s, gb, grund in _STUFEN]


def mit_leiter(tarife, abgerufen_am: str = "2026-09-28"):
    """Derselbe Bestand plus Testleiter - als Liste oder als dict je ID,
    je nachdem, was hereinkommt."""
    saetze = leiter_saetze(abgerufen_am)
    if isinstance(tarife, dict):
        return {**tarife, **{s["tarif_id"]: s for s in saetze}}
    return list(tarife) + saetze
