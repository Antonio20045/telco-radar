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
     `Product`/`Offer`-Knoten je Variante. `strukturdaten.produkte_aus_ldjson`
     liest ihn bereits generisch (der Baum-Scan `_knoten()` findet die
     verschachtelten `item`-Objekte einer `ItemList` ohne Sonderfall) - hier
     wird er WIEDERVERWENDET, nicht neu geschrieben.
  2. `window.__PRELOADED_STATE__` (Apollo-Normalized-Cache): ein flaches
     Dict, in dem jede Preisinstanz unter `CofrPriceFeature:{"id":
     "Saturn:de:<produktId>",...}` liegt, der Produkttitel unter
     `GraphqlProduct:Saturn:de-DE:<produktId>`.

DIE ZWEI PFLICHTFILTER (Spike §6.4)
------------------------------------
(a) MARKTPLATZ. Das ld+json-`ItemList` traegt KEIN Verkaeuferfeld - auf der
    Markenseite `/de/brand/apple/iphone/iphone-17` sind 7 von 12 gelisteten
    Angeboten Drittanbieter (technik-guenstiger, Clevertronic, buyZOXS,
    Media-Reich GmbH, Revalis), mit Preisen von 1.080 EUR bis 2.036 EUR fuer
    dasselbe Geraet, das Saturn selbst fuer 939,99 EUR fuehrt. Das
    Erkennungsmerkmal `isProductOfTypeMarketplace` steht NUR im Apollo-
    Cache, direkt auf dem `CofrPriceFeature`-Objekt. Ein Adapter, der nur
    das ld+json liest, kann Saturn-eigene von Marktplatzpreisen NICHT
    unterscheiden - deshalb ist der Apollo-Cache hier die einzige Quelle,
    aus der ein Preis tatsaechlich uebernommen wird. Gefiltert wird streng:
    nur `isProductOfTypeMarketplace is False` zaehlt, ein fehlendes oder
    unklares Feld (`None`) faellt NICHT durch als vermeintlich sicher -
    fail closed, wie ueberall in diesem Projekt.
(b) DUBLETTEN. Dieselbe `product_id` kann unter zwei Apollo-Schluesseln
    liegen (mit/ohne Ratenplan-Unterauswahl in der urspruenglichen
    GraphQL-Query-Form, gleicher Betrag). `_dedupe_by_product_id` behaelt
    den vollstaendigeren Eintrag (mit Ratenplan). Das ist KEINE Dublette
    ueber Farbvarianten - jede Farbe eines Modells bleibt eine eigene
    Preiszeile, dieselbe Konvention wie bei jedem anderen Adapter dieses
    Zweigs (die `sku_id` traegt die Farbe als eigene Dimension).

DIE GEGENPROBE, DIE HIER NEU IST
----------------------------------
Der Auftrag verlangt Extraktion "ueber ld+json-ItemList UND den
Apollo-Cache" - nicht als zwei gleichwertige Quellen (das waere falsch: nur
der Apollo-Cache traegt den Marktplatz-Filter), sondern als Beleg UND
Gegenprobe. Jeder aus dem Apollo-Cache uebernommene (Titel, Preis) muss sich
auch im UNABHAENGIGEN ld+json-Block derselben Seite wiederfinden - findet
sich keine Entsprechung, ist das ein Befund (moeglicherweise hat sich das
Nutzlastformat geaendert) und wird LAUT gemeldet, aber der Preis bleibt in
der Ausgabe: der Apollo-Cache bleibt die einzige Quelle mit Marktplatz-Feld,
ihn deshalb zu verwerfen waere die Gegenprobe wichtiger zu nehmen als den
eigentlichen Pflichtfilter.

DIE MARKENSEITE IST IHRE EIGENE NUTZLAST (direkt=True)
--------------------------------------------------------
Wie bei der Telekom-Kategorieseite wird keine Produktseite nachgeladen -
die Markenseite traegt alle Varianten (Farben, Speichergroessen) bereits
serverseitig. Speicher und Farbe stehen nicht als eigene Apollo-Felder
(anders als bei Vodafone/o2), sie werden wie beim generischen `ldjson`-Pfad
aus dem Titel gelesen (`geraete_model.speicher_aus_titel`/`farbe_aus_titel`
ueber `lies_listung`) - der Titel selbst nennt beides vollstaendig
("APPLE iPhone 17 Pro 5G 256 GB Tiefblau Dual SIM").

TOTE KATEGORIE-IDS (Spike §3)
-------------------------------
`/de/category/_..._<id>.html` ist NICHT Teil dieses Adapters - die im
urspruenglichen Auftrag genannte ID war eine veraltete, leere Kategorie
(HTTP 200, 0 Artikel, kein Bot-Block). Die stabile, vom Betreiber selbst im
Sitemap-Index gefuehrte Adresse ist die Markenseite.

KEIN BROWSER, KEINE TABU-OPERATION
-------------------------------------
Alles hier gelesene steht bereits in der ersten HTTP-Antwort (siehe Spike
§1/§2) - kein GraphQL-Nachladen fuer den Preis noetig, also auch keine
Beruehrung der zwei robots-gesperrten Operationen `GetPaidBundles`/
`GetFreeBundles`. robots.txt sperrt fuer `/de/brand/...` nichts (Spike §5).
"""
from __future__ import annotations

import json
import logging
import re
from urllib.parse import urljoin

from . import GeraeteAbrufFehler
from .strukturdaten import produkte_aus_ldjson

log = logging.getLogger(__name__)

_STATE_MARK = "window.__PRELOADED_STATE__ = "

# Die Farbe steht in JEDEM beobachteten Titel zwischen der Speicherangabe
# und dem optionalen SIM-Zusatz ("... 256 GB Tiefblau Dual SIM", "... 1 TB
# Himmelblau" ohne Zusatz bei iPhone Air). Sie wird HIER strukturiert
# gelesen und NICHT dem generischen Titel-Rueckfall ueberlassen
# (`geraete_model.farbe_aus_titel`): dessen Mustersuche vergleicht
# ASCII-gefaltete Schreibweisen ("weiss") gegen den UNGEFALTETEN Titeltext
# und findet "Weiß" deshalb nie - ein Befund an echten Daten (fuenf von
# fuenf Farbvarianten der Seite /de/brand/apple/iphone/iphone-17 wurden
# richtig gelesen, "Weiß" fiel auf "ohne-farbe"). Die Farbe hier
# strukturiert weiterzugeben, statt den fehleranfaelligen Rueckfall zu
# durchlaufen, ist dieselbe Rangfolge, die jeder andere Adapter mit einem
# eigenen Farbfeld schon befolgt (Teil C1: strukturierte Daten schlagen
# Textextraktion). `normalisiere_farbe` faltet danach korrekt (ueber
# `geraete_model.normalisiere`, das "ß" -> "ss" abbildet).
_FARBE_RE = re.compile(
    r"\b\d+\s*(?:GB|TB)\b\s+(?P<farbe>.+?)"
    r"(?:\s+(?:Dual SIM|Single SIM|eSIM))?\s*$",
    re.IGNORECASE)


def _farbe_aus_saturn_titel(titel: str) -> str:
    treffer = _FARBE_RE.search(titel or "")
    return treffer.group("farbe").strip() if treffer else ""


def _preloaded_state(html: str) -> dict:
    """`window.__PRELOADED_STATE__` als Objekt - oder eine ehrliche
    Ausnahme. "Marker fehlt" und "Marker da, aber kaputt" sind zwei
    verschiedene Befunde (Bot-Abwehr bzw. neues Nutzlastformat) und werden
    beide als Messgrenze geworfen, nie still auf ein leeres Ergebnis
    abgebildet."""
    idx = (html or "").find(_STATE_MARK)
    if idx == -1:
        raise GeraeteAbrufFehler(
            "Saturn-Markenseite ohne window.__PRELOADED_STATE__ "
            f"({len(html or '')} Bytes) - neues Format oder Bot-Abwehr")
    start = idx + len(_STATE_MARK)
    end = html.find("</script>", start)
    if end == -1:
        raise GeraeteAbrufFehler(
            "Saturn-Zustandsobjekt: kein Skriptende gefunden")
    raw = html[start:end].rstrip()
    if raw.endswith(";"):
        raw = raw[:-1]
    # Die Nutzlast traegt teils das JS-Literal "undefined", das kein
    # gueltiges JSON ist - siehe Spike-Skript, derselbe Kunstgriff.
    raw = re.sub(r":undefined", ":null", raw)
    try:
        daten = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise GeraeteAbrufFehler(
            f"Saturn-Zustandsobjekt unlesbar: {exc}") from exc
    if not isinstance(daten, dict):
        raise GeraeteAbrufFehler("Saturn-Zustandsobjekt ist kein Objekt")
    return daten


def _preisfeatures(state: dict) -> list[dict]:
    """Alle `CofrPriceFeature`-Eintraege des Apollo-Caches, UNGEFILTERT -
    der Marktplatz-Filter steht bewusst in `lies()`, damit diese Funktion
    fuer Diagnosen (Tests, ein spaeterer Bericht) den vollen Bestand zeigt,
    Marktplatz-Angebote eingeschlossen."""
    apollo = state.get("apolloState")
    if not isinstance(apollo, dict):
        return []
    out: list[dict] = []
    for key, val in apollo.items():
        if not isinstance(val, dict) or not key.startswith("CofrPriceFeature:"):
            continue
        roh_id = val.get("id")
        produkt_id = roh_id.split(":")[-1] if isinstance(roh_id, str) else None
        produkt = apollo.get(f"GraphqlProduct:Saturn:de-DE:{produkt_id}", {})
        if not isinstance(produkt, dict):
            produkt = {}
        preis = (val.get("price") or {}).get("amount")
        out.append({
            "apollo_key": key,
            "product_id": str(produkt_id or "").strip(),
            "title": str(produkt.get("title") or "").strip(),
            "product_url": str(produkt.get("url") or "").strip(),
            "amount": preis,
            "currency": val.get("currency"),
            "installment_present":
                (val.get("price") or {}).get("installment") is not None,
            # `None` heisst "die Quelle nennt es nicht" und ist ausdruecklich
            # NICHT dasselbe wie `False` - siehe Modulkopf, fail closed.
            "is_marketplace": val.get("isProductOfTypeMarketplace"),
        })
    return out


def _dedupe_by_product_id(features: list[dict]) -> list[dict]:
    """Zwei Apollo-Schluessel koennen dieselbe `product_id` tragen (Spike
    §2b: eine Query-Form mit, eine ohne Ratenplan-Unterauswahl, derselbe
    Betrag). Der vollstaendigere Eintrag - der MIT Ratenplan - gewinnt,
    keine zweite Preiszeile fuer dieselbe SKU."""
    gesehen: dict[str, dict] = {}
    for f in features:
        pid = f["product_id"]
        if not pid:
            continue
        vorher = gesehen.get(pid)
        if vorher is None or (f["installment_present"]
                              and not vorher["installment_present"]):
            gesehen[pid] = f
    return list(gesehen.values())


def _ld_json_preisindex(html: str) -> set:
    """(Titel klein, Preis) je ld+json-`ItemList`-Eintrag - die zweite,
    unabhaengige Struktur derselben Seite. Dient NICHT der Preisextraktion
    (das ld+json traegt kein Verkaeuferfeld, siehe Modulkopf), sondern der
    Gegenprobe in `lies()`."""
    out = set()
    for satz in produkte_aus_ldjson(html):
        titel = (satz.get("titel") or "").strip().lower()
        preis = satz.get("preis")
        if titel and preis is not None:
            out.add((titel, float(preis)))
    return out


def lies(text: str, url: str = "") -> list[dict]:
    """Eine Markenseite (`/de/brand/<hersteller>/<serie>/<modell>`) in
    Rohsaetze. Sie IST die Nutzlast - keine Produktseite wird nachgeladen
    (`direkt=True` in der Adapter-Registry)."""
    state = _preloaded_state(text)
    alle = _preisfeatures(state)
    if not alle:
        return []

    eigen = _dedupe_by_product_id(
        [f for f in alle if f["is_marketplace"] is False])
    ld_json_index = _ld_json_preisindex(text)

    out: list[dict] = []
    for f in eigen:
        titel = f["title"]
        if not titel or f["amount"] is None:
            continue
        try:
            preis = float(f["amount"])
        except (TypeError, ValueError):
            continue
        waehrung = str(f["currency"] or "EUR").upper()
        if waehrung and waehrung != "EUR":
            continue

        schluessel = (titel.strip().lower(), preis)
        if ld_json_index and schluessel not in ld_json_index:
            # Die Gegenprobe schlaegt fehl: der Apollo-Preis findet keine
            # Entsprechung im UNABHAENGIGEN ld+json-Block derselben Seite.
            # Der Preis bleibt trotzdem in der Ausgabe - der Apollo-Cache
            # ist die einzige Quelle mit dem Marktplatz-Feld, ihn deswegen
            # zu verwerfen waere die Gegenprobe wichtiger zu nehmen als den
            # eigentlichen Pflichtfilter. Der Befund soll aber auffallen.
            log.warning(
                "Saturn: %r (%.2f EUR) aus dem Apollo-Cache ohne "
                "Entsprechung im ld+json-ItemList derselben Seite (%s)",
                titel, preis, url)

        out.append({
            "titel": titel,
            "preis": preis,
            "waehrung": "EUR",
            "sku": f["product_id"],
            "farbe": _farbe_aus_saturn_titel(titel),
            "url": urljoin(url, f["product_url"]) if f["product_url"] else url,
            "quelle": "saturn_brand",
        })
    return out
