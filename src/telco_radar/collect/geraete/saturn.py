"""Saturn: der Preis in zwei unabhaengigen, serverseitig gerenderten
Fundstellen derselben Markenseite - ld+json UND dem Apollo-Cache.

Bauanleitung: `outputs/saturn-spike-2026-09-05.md` (Spike vom 05.09.2026,
`scripts/spike_saturn_geraetepreis.py`). Dieser Adapter ist die
Produktivfassung des dort gemessenen Struktur-Funds, kein neuer Fund.

WO DIE ZAHL STEHT
------------------
Jede Markenseite (`/de/brand/<hersteller>/<serie>/<modell>`) traegt in
DERSELBEN HTML-Antwort zwei unabhaengige, standardkonforme Strukturen:

  1. `<script type="application/ld+json">` vom Typ `ItemList` mit einem
     `Product`/`Offer`-Knoten je Variante.
  2. `window.__PRELOADED_STATE__` (Apollo-Normalized-Cache): ein flaches
     Dict, in dem jede Preisinstanz unter `CofrPriceFeature:{"id":
     "Saturn:de:<produktId>",...}` liegt, der Produkttitel unter
     `GraphqlProduct:Saturn:de-DE:<produktId>`.

DER GETEILTE LESEKERN
-----------------------
Die eigentliche Extraktion (Marktplatz-Filter, Dublettenregel, ld+json-
Gegenprobe) steht seit dem MediaMarkt-Auftrag (Brief
`brief-mediamarkt-0511.md`, 05.11.2026) in `ceconomy.py` - MediaMarkt laeuft
auf derselben Plattform, nur mit dem Cache-Praefix "Media" statt "Saturn".
Dieses Modul ist nur noch der Saturn-spezifische Aufruf (Tenant-Praefix,
Fehlertexte, `quelle`-Feld); die private Namensgebung unten (`_lies`-Helfer)
bleibt erhalten, weil `tests/test_geraete_adapter_saturn.py` sie direkt
anspricht.

DIE ZWEI PFLICHTFILTER (Spike §6.4) - Einzelheiten in `ceconomy.py`
---------------------------------------------------------------------
(a) MARKTPLATZ. Nur `isProductOfTypeMarketplace is False` zaehlt, ein
    fehlendes oder unklares Feld (`None`) faellt NICHT durch als
    vermeintlich sicher - fail closed, wie ueberall in diesem Projekt.
(b) DUBLETTEN. Dieselbe `product_id` kann unter zwei Apollo-Schluesseln
    liegen; der vollstaendigere Eintrag (mit Ratenplan) gewinnt.

DIE MARKENSEITE IST IHRE EIGENE NUTZLAST (direkt=True)
--------------------------------------------------------
Wie bei der Telekom-Kategorieseite wird keine Produktseite nachgeladen -
die Markenseite traegt alle Varianten (Farben, Speichergroessen) bereits
serverseitig. Speicher und Farbe stehen nicht als eigene Apollo-Felder, sie
werden aus dem Titel gelesen.

TOTE KATEGORIE-IDS (Spike §3)
-------------------------------
`/de/category/_..._<id>.html` ist NICHT Teil dieses Adapters - die im
urspruenglichen Auftrag genannte ID war eine veraltete, leere Kategorie. Die
stabile Adresse ist die Markenseite.
"""

from __future__ import annotations

from . import ceconomy

_TENANT = "Saturn"
_QUELLE = "saturn_brand"
_MARKENNAME = "Saturn"


def _farbe_aus_saturn_titel(titel: str) -> str:
    return ceconomy.farbe_aus_titel(titel)


def _preloaded_state(html: str) -> dict:
    return ceconomy.preloaded_state(html, _MARKENNAME)


def _preisfeatures(state: dict) -> list[dict]:
    return ceconomy.preisfeatures(state, _TENANT)


def _dedupe_by_product_id(features: list[dict]) -> list[dict]:
    return ceconomy.dedupe_by_product_id(features)


def _ld_json_preisindex(html: str) -> set:
    return ceconomy.ld_json_preisindex(html)


def lies(text: str, url: str = "") -> list[dict]:
    """Eine Markenseite (`/de/brand/<hersteller>/<serie>/<modell>`) in
    Rohsaetze. Sie IST die Nutzlast - keine Produktseite wird nachgeladen
    (`direkt=True` in der Adapter-Registry)."""
    return ceconomy.lies(
        text, url, tenant=_TENANT, quelle=_QUELLE, markenname=_MARKENNAME
    )
