"""MediaMarkt: derselbe Ceconomy-Lesekern wie Saturn (`ceconomy.py`), anderer
Cache-Praefix.

Herkunft: Recherche `arbeit/haendler-weg-0411.md` (Abschnitt 2 und 4.1) und
Brief `brief-mediamarkt-0511.md` (05.11.2026). Jede Seite dieser Plattform
traegt in DERSELBEN Antwort zwei unabhaengige Strukturen:

  1. `<script type="application/ld+json">` (ItemList).
  2. `window.__PRELOADED_STATE__` (Apollo-Cache). Jede Preisinstanz liegt
     unter `CofrPriceFeature:{"id": "Media:de:<produktId>",...}` - bei
     Saturn heisst dasselbe Feld "Saturn:de:<produktId>". Der Produkttitel
     liegt unter `GraphqlProduct:Media:de-DE:<produktId>` (Saturn:
     `GraphqlProduct:Saturn:de-DE:<produktId>`). NUR dieses Praefix
     unterscheidet die beiden Haendler auf Cache-Ebene - deshalb
     `ceconomy.lies(..., tenant="Media")` statt einer Kopie.

DER EINSTIEG: DIE KAMPAGNENSEITE, NICHT DIE PRODUKTSEITE
-------------------------------------------------------------
`config/geraete_quellen.yaml` liest `/de/campaign/angebote-smartphones`
direkt (`direkt=True`, wie Saturns Markenseite) - sie ist bereits zweimal
gemessen (Alt-Eintrag "26 Geraetepreise", Nachmessung 04.11.2026) robots-
erlaubt und captcha-frei. Produktseiten (`/de/product/...`) sind NICHT
konfiguriert, obwohl `lies()` auch sie liest: eine echte Produktseite
(`mm_product_samsung_a57.body.html`, Abruf 04.11.2026) ist die Fixture fuer
den Marktplatz-Pflichttest, weil sie - anders als die Kampagnenseite an
diesem Tag - tatsaechlich Fremdanbieter-Angebote neben MediaMarkt-eigenen
fuehrt (5 von 21 `CofrPriceFeature`-Eintraegen `isProductOfTypeMarketplace
== true`, bis zu 445 EUR fuer ein Geraet, das MediaMarkt selbst fuer
389,99 EUR fuehrt). Der Filter gilt fuer BEIDE Seitentypen gleich - `lies()`
kennt keinen Unterschied zwischen Kampagnen- und Produktseite, beide tragen
dieselbe Apollo-Struktur.
"""

from __future__ import annotations

from . import ceconomy

_TENANT = "Media"
_QUELLE = "mediamarkt_angebote"
_MARKENNAME = "MediaMarkt"


def lies(text: str, url: str = "") -> list[dict]:
    """Eine Seite der MediaMarkt-Plattform (Kampagnen- oder Produktseite)
    in Rohsaetze - nur Angebote mit `isProductOfTypeMarketplace == false`."""
    return ceconomy.lies(
        text, url, tenant=_TENANT, quelle=_QUELLE, markenname=_MARKENNAME
    )
