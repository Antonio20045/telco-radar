"""Gemeinsamer Lesekern der Ceconomy-Haendlerseiten (Saturn, MediaMarkt) -
derselbe Shop-Unterbau, derselbe Apollo-Cache, nur anderer Domainname und
anderes Tenant-Praefix im Cache-Schluessel.

Herkunft: `saturn.py` (Spike `outputs/saturn-spike-2026-09-05.md`). Der
Auftrag fuer MediaMarkt (Brief `brief-mediamarkt-0511.md`) verlangt
ausdruecklich, sich den Code mit Saturn zu teilen statt ihn zu kopieren -
dieses Modul ist der geteilte Teil, parametrisiert ueber `tenant`
(Cache-Praefix: "Saturn" bzw. "Media") und `quelle`/`markenname`
(Anzeige/Fehlertext). `saturn.py` und `mediamarkt.py` rufen nur noch diese
Funktionen auf; sie importieren sich gegenseitig NICHT (Vertrag
`adapter-unabhaengig` in `.importlinter`).

DIE ZWEI PFLICHTFILTER gelten unveraendert fuer beide Haendler (siehe
Modulkopf von `saturn.py` fuer die ausfuehrliche Herleitung):
(a) MARKTPLATZ ueber `isProductOfTypeMarketplace` - nur `False` zaehlt,
    `None` faellt NICHT durch (fail closed).
(b) DUBLETTEN ueber `product_id` - der Eintrag MIT Ratenplan gewinnt.
"""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import urljoin

from .basis import GeraeteAbrufFehler
from .strukturdaten import produkte_aus_ldjson

log = logging.getLogger(__name__)

_STATE_MARK = "window.__PRELOADED_STATE__ = "

_FARBE_RE = re.compile(
    r"\b\d+\s*(?:GB|TB)\b\s+(?P<farbe>.+?)"
    r"(?:\s+(?:Dual SIM|Single SIM|eSIM))?\s*$",
    re.IGNORECASE,
)


def farbe_aus_titel(titel: str) -> str:
    """Farbe aus einer festen Titelposition (vor "Dual SIM" o.ae.), nicht
    ueber den ASCII-faltenden generischen Fallback - der findet "Weiss" nie
    in einem Titel, der "Weiß" schreibt."""
    treffer = _FARBE_RE.search(titel or "")
    return treffer.group("farbe").strip() if treffer else ""


def preloaded_state(html: str, markenname: str) -> dict:
    """`window.__PRELOADED_STATE__` als Objekt - oder eine ehrliche
    Ausnahme. "Marker fehlt" und "Marker da, aber kaputt" sind zwei
    verschiedene Befunde (Bot-Abwehr bzw. neues Nutzlastformat) und werden
    beide als Messgrenze geworfen, nie still auf ein leeres Ergebnis
    abgebildet."""
    idx = (html or "").find(_STATE_MARK)
    if idx == -1:
        raise GeraeteAbrufFehler(
            f"{markenname}-Seite ohne window.__PRELOADED_STATE__ "
            f"({len(html or '')} Bytes) - neues Format oder Bot-Abwehr"
        )
    start = idx + len(_STATE_MARK)
    end = html.find("</script>", start)
    if end == -1:
        raise GeraeteAbrufFehler(
            f"{markenname}-Zustandsobjekt: kein Skriptende gefunden"
        )
    raw = html[start:end].rstrip()
    if raw.endswith(";"):
        raw = raw[:-1]
    raw = re.sub(r":undefined", ":null", raw)
    try:
        daten = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise GeraeteAbrufFehler(
            f"{markenname}-Zustandsobjekt unlesbar: {exc}"
        ) from exc
    if not isinstance(daten, dict):
        raise GeraeteAbrufFehler(f"{markenname}-Zustandsobjekt ist kein Objekt")
    return daten


def preisfeatures(state: dict, tenant: str) -> list[dict]:
    """Alle `CofrPriceFeature`-Eintraege des Apollo-Caches, UNGEFILTERT -
    der Marktplatz-Filter steht bewusst beim Aufrufer, damit diese Funktion
    fuer Diagnosen (Tests, ein spaeterer Bericht) den vollen Bestand zeigt,
    Marktplatz-Angebote eingeschlossen. `tenant` ist das Cache-Praefix
    ("Saturn" bzw. "Media"), ueber das der Produkttitel nachgeschlagen
    wird."""
    apollo = state.get("apolloState")
    if not isinstance(apollo, dict):
        return []
    out: list[dict] = []
    for key, val in apollo.items():
        if not isinstance(val, dict) or not key.startswith("CofrPriceFeature:"):
            continue
        roh_id = val.get("id")
        produkt_id = roh_id.split(":")[-1] if isinstance(roh_id, str) else None
        produkt = apollo.get(f"GraphqlProduct:{tenant}:de-DE:{produkt_id}", {})
        if not isinstance(produkt, dict):
            produkt = {}
        preis = (val.get("price") or {}).get("amount")
        out.append(
            {
                "apollo_key": key,
                "product_id": str(produkt_id or "").strip(),
                "title": str(produkt.get("title") or "").strip(),
                "product_url": str(produkt.get("url") or "").strip(),
                "amount": preis,
                "currency": val.get("currency"),
                "installment_present": (val.get("price") or {}).get("installment")
                is not None,
                "is_marketplace": val.get("isProductOfTypeMarketplace"),
            }
        )
    return out


def dedupe_by_product_id(features: list[dict]) -> list[dict]:
    """Zwei Apollo-Schluessel koennen dieselbe `product_id` tragen (eine
    Query-Form mit, eine ohne Ratenplan-Unterauswahl, derselbe Betrag). Der
    vollstaendigere Eintrag - der MIT Ratenplan - gewinnt, keine zweite
    Preiszeile fuer dieselbe SKU."""
    gesehen: dict[str, dict] = {}
    for f in features:
        pid = f["product_id"]
        if not pid:
            continue
        vorher = gesehen.get(pid)
        if vorher is None or (
            f["installment_present"] and not vorher["installment_present"]
        ):
            gesehen[pid] = f
    return list(gesehen.values())


def ld_json_preisindex(html: str) -> set:
    """(Titel klein, Preis) je ld+json-`ItemList`-Eintrag - die zweite,
    unabhaengige Struktur derselben Seite. Dient NICHT der Preisextraktion
    (das ld+json traegt kein Verkaeuferfeld), sondern der Gegenprobe."""
    out = set()
    for satz in produkte_aus_ldjson(html):
        titel = (satz.get("titel") or "").strip().lower()
        preis = satz.get("preis")
        if titel and preis is not None:
            out.add((titel, float(preis)))
    return out


def lies(
    text: str, url: str, *, tenant: str, quelle: str, markenname: str
) -> list[dict]:
    """Eine Seite der Ceconomy-Plattform (Saturn-Markenseite oder
    MediaMarkt-Produktseite) in Rohsaetze. Sie IST die Nutzlast - keine
    weitere Seite wird nachgeladen."""
    state = preloaded_state(text, markenname)
    alle = preisfeatures(state, tenant)
    if not alle:
        return []

    eigen = dedupe_by_product_id([f for f in alle if f["is_marketplace"] is False])
    ld_json_index = ld_json_preisindex(text)

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
            log.warning(
                "%s: %r (%.2f EUR) aus dem Apollo-Cache ohne Entsprechung "
                "im ld+json-ItemList derselben Seite (%s)",
                markenname,
                titel,
                preis,
                url,
            )

        out.append(
            {
                "titel": titel,
                "preis": preis,
                "waehrung": "EUR",
                "sku": f["product_id"],
                "farbe": farbe_aus_titel(titel),
                "url": urljoin(url, f["product_url"]) if f["product_url"] else url,
                "quelle": quelle,
            }
        )
    return out
