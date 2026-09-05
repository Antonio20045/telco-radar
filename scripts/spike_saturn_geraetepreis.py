#!/usr/bin/env python3
"""SPIKE (nicht produktiv) — kann Saturn.de mit ehrlichen Mitteln einen
Gerätepreis liefern?

Auftrag: BRIEF_SATURN_SPIKE.md (05.09.2026). Dies ist ein Wegwerf-Skript
fuer die Diagnose, KEIN Adapter und KEIN Teil der Pipeline. Es haengt an
keiner Konfiguration und schreibt keinen State (nur /tmp).

Regeln, die dieses Skript einhaelt:
  - Ehrlicher User-Agent: "TelcoRadar/1.0 (+https://telco-radar.onrender.com/ueber)"
    (kein Impersoning eines Browsers).
  - robots.txt strikt: die zwei gesperrten GraphQL-Operationen
    "GetPaidBundles" und "GetFreeBundles" werden aktiv BLOCKIERT
    (page.route -> abort), falls die Seite versucht, sie selbst zu rufen -
    geprueft wird sowohl die URL (GET-Persisted-Queries) als auch ein
    JSON-POST-Body (falls Apollo eine Operation per POST schickt).
    ZUSAETZLICH werden alle anderen fuer uns (User-agent "*") gesperrten
    Pfade der robots.txt aktiv blockiert (page.route -> abort) - nicht nur
    beobachtet -, weil eine passive Seitenlast von sich aus Requests auf
    mehrere dieser Pfade ausloest (Cloudflare-Challenge-Skript, ein
    Chat-Konfig-Ping, ein Tracking-Cookie-Endpunkt - siehe Bericht §5). Nur
    GraphQL-Operationen AUSSER den zwei Tabu-Ops und alle sonst nicht
    gesperrten Requests werden durchgelassen und beobachtet - das Skript
    ruft selbst keine API auf, es laedt eine einzelne erlaubte Produkt-/
    Kategorieseite und sieht zu, was der Browser normalerweise laedt. Jede
    gesehene XHR/Fetch-Antwort (samt Statuscode) landet im Report, damit
    sich "nichts Gesperrtes kam durch" und "keine Fehlerantwort blieb
    unbemerkt" auch nachtraeglich pruefen lassen statt nur behauptet zu
    werden.
  - Zwei Modi: --mode static (reines HTTP, kein Playwright, urllib) und
    --mode browser (Chromium, mit Screenshot-Gegenprobe). Der Vergleich der
    beiden Modi ist der eigentliche Struktur-Fund dieses Spikes: wenn
    "static" bereits den Preis liefert, ist Playwright fuer den Preis selbst
    NICHT erforderlich.
  - Kein Captcha-Bypass, kein Tarnungstrick, kein Retry-Sturm. Ein
    Fehlschlag wird als Messgrenze protokolliert, nicht umgangen.

Usage:
    /opt/homebrew/bin/python3 scripts/spike_saturn_geraetepreis.py \
        --mode static --url "https://www.saturn.de/de/brand/apple/iphone/iphone-17-pro" \
        --tag brand-iphone17pro-static

    /opt/homebrew/bin/python3 scripts/spike_saturn_geraetepreis.py \
        --mode browser --url "https://www.saturn.de/de/brand/apple/iphone/iphone-17-pro" \
        --tag brand-iphone17pro-browser
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from datetime import datetime, timezone

UA = "TelcoRadar/1.0 (+https://telco-radar.onrender.com/ueber)"
DEFAULT_URL = "https://www.saturn.de/de/category/_apple-iphone-17-pro-701440.html"

# Robots.txt (gelesen UND als /tmp/saturn_robots_check.txt gespeichert am
# 05.09.2026, User-agent: *) sperrt fuer uns exakt diese zwei
# GraphQL-Operationen. Nichts sonst auf /de/category/..., /de/brand/... oder
# /de/product/... ist gesperrt. Die Liste unten ist die VOLLSTAENDIGE
# Disallow-Liste der "*"-Gruppe (nicht nur ein Auszug) - Block-Regex UND
# Audit-Funktion lesen aus GENAU dieser einen Liste, damit beide nie
# auseinanderlaufen. Robots-Wildcards ("*") werden zu Regex-".*", der Rest
# wird woertlich (escaped) genommen.
_TABU_OPS = ("GetPaidBundles", "GetFreeBundles")
_ROBOTS_DISALLOW_PATTERNS = (
    "/cdn-cgi/bm/cv/",
    "/cdn-cgi/challenge-platform/",
    "/rde_server/",
    "/api/v1/graphql?operationName=GetPaidBundles",
    "/api/v1/graphql?operationName=GetFreeBundles",
    "/api/v1/msg",
    "/api/v1/mms-sst",
    "/api/v1/partners/",
    "/*shopfallback*",
    "/*MultiChannelMARepairStatusResult*",
    "/Shop/SaturnDE/live/desktop/de/products/catalogentry/component/availability.html*",
    "/*storeId=*",
    "*de/list/*_*",
    "*de/promo-list/*",
    "/mcs/marketinfo/*",
    "*de/search",
    "/public/setCookie/",
    "*/myaccount/auth*",
)


def _pattern_to_regex(pattern: str) -> re.Pattern:
    return re.compile(re.escape(pattern).replace(r"\*", ".*"))


_ROBOTS_DISALLOW_REGEXES = tuple((p, _pattern_to_regex(p)) for p in _ROBOTS_DISALLOW_PATTERNS)

_PRELOADED_STATE_MARK = "window.__PRELOADED_STATE__ = "


def _is_tabu(url: str, post_data: str | None = None) -> str | None:
    haystacks = [url]
    if post_data:
        haystacks.append(post_data)
    for op in _TABU_OPS:
        for hay in haystacks:
            if f"operationName={op}" in hay or re.search(
                r'"operationName"\s*:\s*"' + re.escape(op) + '"', hay
            ):
                return op
    return None


def _matched_disallow(url: str) -> str | None:
    """Prueft EINE URL gegen die volle Disallow-Liste. Wird sowohl vom
    aktiven Blocker (waehrend des Laufs) als auch vom Audit (danach, gegen
    alles was DURCHGELASSEN wurde) benutzt - dieselbe Funktion, damit beide
    garantiert dasselbe pruefen.
    """
    for pattern, rx in _ROBOTS_DISALLOW_REGEXES:
        if rx.search(url):
            return pattern
    return None


def _audit_robots(urls: list[str]) -> list[str]:
    """Prueft eine Liste tatsaechlich beobachteter (durchgelassener)
    Request-URLs gegen die volle Disallow-Liste. Gibt jede URL zurueck, die
    auf ein Disallow-Muster trifft - leer heisst: von dem, was dieser Lauf
    NICHT blockiert hat, war nichts davon eigentlich gesperrt. Deckt nur
    XHR/Fetch-Antworten ab (siehe Aufrufer) - Requests anderer Ressourcen-
    typen werden bereits VOR einer moeglichen Antwort durch denselben
    Blocker abgefangen, tauchen also nie in dieser Liste auf.
    """
    hits = []
    for u in urls:
        hit = _matched_disallow(u)
        if hit:
            hits.append(f"{hit} :: {u}")
    return hits


def _extract_preloaded_state(html: str) -> tuple[dict | None, str | None]:
    """Findet und parst das SSR-Hydration-JSON (window.__PRELOADED_STATE__).

    Das ist KEIN GraphQL-Aufruf des Skripts - es liest nur, was der Server
    selbst schon in die ausgelieferte HTML-Seite geschrieben hat. Die
    Nutzlast enthaelt teils den JS-Literal "undefined", der kein gueltiges
    JSON ist; er wird auf "null" abgebildet, sonst nichts veraendert.

    Gibt (state, fehlergrund) zurueck - "State fehlt" und "State da, aber
    kaputt" sind zwei verschiedene Befunde und werden nicht beide zu None.
    """
    idx = html.find(_PRELOADED_STATE_MARK)
    if idx == -1:
        return None, "marker_not_found"
    start = idx + len(_PRELOADED_STATE_MARK)
    end = html.find("</script>", start)
    if end == -1:
        return None, "script_end_not_found"
    raw = html[start:end].rstrip()
    if raw.endswith(";"):
        raw = raw[:-1]
    raw = re.sub(r":undefined", ":null", raw)
    try:
        return json.loads(raw), None
    except json.JSONDecodeError as exc:
        return None, f"json_decode_error: {exc}"


def _extract_ld_json_itemlist(html: str) -> list[dict]:
    """Liest den zweiten, unabhaengigen Struktur-Fund: ein standardkonformer
    schema.org-Block <script type="application/ld+json"> vom Typ ItemList
    mit Product/Offer je Variante. Existiert NUR auf Marken-/Modellseiten,
    nicht auf der (leeren) Kategorieseite aus dem Auftrag.
    """
    out = []
    for m in re.finditer(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S
    ):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if data.get("@type") != "ItemList":
            continue
        for entry in data.get("itemListElement", []):
            item = entry.get("item", {})
            offers = item.get("offers") or {}
            out.append({
                "name": item.get("name"),
                "price": offers.get("price"),
                "priceCurrency": offers.get("priceCurrency"),
            })
    return out


def _price_features_from_state(state: dict) -> list[dict]:
    """Liest Preis + Produkttitel aus dem Apollo-Normalized-Cache im State.

    Struktur-Fund (05.09.2026): `apolloState` ist ein flaches Dict, in dem
    JEDE Preisinstanz unter einem eigenen Schluessel
    'CofrPriceFeature:{"id":"Saturn:de:<produktId>",...}' liegt, und der
    zugehoerige Produkttitel unter 'GraphqlProduct:Saturn:de-DE:<produktId>'.
    Der reine Geraetepreis steht in price.amount (EUR); price.installment
    ist ein RATENPLAN, kein zweiter Geraetepreis.

    WICHTIG (Review-Befund B1/B2, 05.09.2026): ob ein Preis von SATURN
    SELBST stammt oder von einem Drittanbieter im Marktplatz, steht als
    `isProductOfTypeMarketplace` / `marketplaceSeller` DIREKT AUF DEM
    CofrPriceFeature-Objekt - nicht als Muster in der ID (ein Klammer-Suffix
    wie "165777527[1792976363]" kommt zwar bei Marktplatzangeboten vor,
    ist aber kein verlaessliches Kriterium: Saturn-eigene IDs sind
    ausnahmslos rein numerisch, aber nicht jede Marktplatz-ID traegt eine
    Klammer). Ein Adapter MUSS auf `isProductOfTypeMarketplace is False`
    filtern, sonst landet der guenstigste Drittanbieterpreis in der
    Leitzahl.
    """
    apollo = state.get("apolloState")
    if not isinstance(apollo, dict):
        return []
    out = []
    for key, val in apollo.items():
        if not key.startswith("CofrPriceFeature:"):
            continue
        prod_id = val.get("id", "").split(":")[-1] if isinstance(val.get("id"), str) else None
        product_key = f"GraphqlProduct:Saturn:de-DE:{prod_id}"
        product = apollo.get(product_key, {})
        price = val.get("price") or {}
        seller = val.get("marketplaceSeller") or {}
        out.append({
            "apollo_key": key,
            "product_id": prod_id,
            "title": product.get("title"),
            "product_url": product.get("url"),
            "amount_eur": price.get("amount"),
            "currency": val.get("currency"),
            "strike_price_eur": (val.get("strikePrice") or {}).get("amount"),
            "shipping_cost_eur": price.get("shippingCost"),
            "installment_present": price.get("installment") is not None,
            "is_marketplace": val.get("isProductOfTypeMarketplace"),
            "marketplace_seller_name": seller.get("sellerName"),
            "breadcrumbs": [b.get("name") for b in (product.get("breadcrumbs") or [])],
        })
    return out


def _dedupe_by_product_id(features: list[dict]) -> tuple[list[dict], list[str]]:
    """Zaehlt, wie oft dieselbe product_id unter mehreren Apollo-Schluesseln
    auftaucht (Review-Befund B7: reale, aber seltene Ursache sind zwei
    Query-Formen desselben Produkts - mit/ohne Ratenplan-Unterauswahl).
    Gibt eine nach product_id deduplizierte Liste UND die Liste der
    betroffenen IDs zurueck (leer = keine Dubletten in diesem Abruf).
    """
    seen: dict[str, dict] = {}
    dup_ids: list[str] = []
    for f in features:
        pid = f["product_id"]
        if pid in seen:
            if pid not in dup_ids:
                dup_ids.append(pid)
            # Den Eintrag MIT Ratenplan bevorzugen (das ist die vollstaendigere
            # Fassung derselben Zahl, kein zweiter Preis).
            if f["installment_present"] and not seen[pid]["installment_present"]:
                seen[pid] = f
        else:
            seen[pid] = f
    return list(seen.values()), dup_ids


def _sanitize_tag(tag: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", tag)
    if not cleaned:
        raise SystemExit(f"--tag ergibt nach Bereinigung einen leeren Namen: {tag!r}")
    return cleaned


def run_static(url: str, html_path: str, report_path: str) -> int:
    """Reiner HTTP-GET ohne Playwright - der eigentliche Beweis, dass fuer
    den Preis kein Browser noetig ist. Nutzt urllib (Stdlib), keine
    Tarnung, derselbe ehrliche UA wie im Browser-Modus.
    """
    started = datetime.now(timezone.utc).isoformat()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    fetch_error = None
    html = ""
    status = None
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        fetch_error = f"{type(exc).__name__}: {exc}"

    finished = datetime.now(timezone.utc).isoformat()

    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    state, state_error = _extract_preloaded_state(html) if html else (None, "no_html")
    raw_features = _price_features_from_state(state) if state else []
    features, dup_ids = _dedupe_by_product_id(raw_features)
    ld_json_items = _extract_ld_json_itemlist(html) if html else []

    report = {
        "mode": "static",
        "started_utc": started,
        "finished_utc": finished,
        "url": url,
        "user_agent": UA,
        "http_status": status,
        "fetch_error": fetch_error,
        "html_path": html_path,
        "html_len": len(html),
        "preloaded_state_found": state is not None,
        "preloaded_state_error": state_error,
        "price_features_from_ssr_state": features,
        "duplicate_apollo_keys_for_same_product_id": dup_ids,
        "ld_json_itemlist": ld_json_items,
    }

    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nHTML gespeichert: {html_path}")
    print(f"Report: {report_path}")
    return 0


def run_browser(url: str, screenshot_path: str, network_log_path: str) -> int:
    from playwright.sync_api import sync_playwright

    started = datetime.now(timezone.utc).isoformat()
    blocked_calls: list[str] = []
    graphql_responses: list[dict] = []
    all_xhr: list[dict] = []
    graphql_requests_seen = 0
    console_errors: list[str] = []
    nav_error = None
    idle_error = None
    screenshot_error = None
    html = ""
    title_text = None

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        try:
            page = browser.new_page(
                user_agent=UA,
                viewport={"width": 1440, "height": 1000},
                locale="de-DE",
            )

            def on_route(route):
                nonlocal graphql_requests_seen
                req_url = route.request.url
                if "graphql" in req_url.lower():
                    graphql_requests_seen += 1
                op = _is_tabu(req_url, route.request.post_data)
                if op:
                    blocked_calls.append(f"tabu-op:{op}: {req_url}")
                    route.abort()
                    return
                # Review-Befund (05.09.2026): eine PASSIVE Seitenlast loest im
                # Hintergrund von sich aus Requests auf mehrere disallow'te
                # Pfade aus (Cloudflare-Challenge-Skript, ein Chat-Ping unter
                # /api/v1/msg, ein Tracking-Cookie unter /public/setCookie/) -
                # das ist keine Handlung dieses Skripts, aber es sind Requests
                # UNSERES Clients, also werden sie ebenso abgefangen wie die
                # zwei GraphQL-Tabu-Operationen. "Nur beobachten" reicht nicht,
                # sobald man weiss, dass es sie gibt. _matched_disallow prueft
                # gegen die VOLLE Disallow-Liste, nicht nur einen Auszug.
                hit = _matched_disallow(req_url)
                if hit:
                    blocked_calls.append(f"disallow:{hit}: {req_url}")
                    route.abort()
                    return
                route.continue_()

            # Ein Route-Matcher auf "**/*" loeste unter Playwright 1.61 +
            # Python 3.14 einen internen Fehler in route.continue_() fuer
            # bestimmte Ressourcentypen aus (Bibliotheksfehler, kein
            # Robots-Thema). Deshalb ein enger Regex, gebaut aus GENAU
            # derselben Disallow-Liste wie _matched_disallow() (kein
            # zweiter, von Hand gepflegter Auszug, der auseinanderlaufen
            # koennte) plus "graphql" fuer die zwei benannten Tabu-Ops -
            # nicht jede Schriftart/jedes Bild der Seite.
            _route_alternatives = ["graphql"] + [
                re.escape(p).replace(r"\*", ".*") for p in _ROBOTS_DISALLOW_PATTERNS
            ]
            _route_pattern = re.compile("|".join(_route_alternatives))
            page.route(_route_pattern, on_route)

            def on_response(resp):
                try:
                    ctype = resp.headers.get("content-type", "")
                except Exception:
                    ctype = ""
                rtype = resp.request.resource_type
                is_graphql = "graphql" in resp.url.lower()
                if rtype in ("xhr", "fetch"):
                    all_xhr.append({"url": resp.url, "status": resp.status, "ctype": ctype})
                # GraphQL-Antworten werden UNABHAENGIG vom Resource-Type
                # gezaehlt (Review-Befund: Playwright klassifiziert nicht
                # jeden GraphQL-Aufruf als "xhr"/"fetch"), damit
                # graphql_response_count mit graphql_requests_seen_by_handler
                # zusammenpasst und ein Statuscode != 200 nicht durchrutscht.
                if is_graphql:
                    body_preview = None
                    body_len = None
                    if resp.status == 200:
                        try:
                            body = resp.text()
                            body_len = len(body)
                            body_preview = body[:4000]
                        except Exception as exc:  # noqa: BLE001
                            body_preview = f"<body read failed: {exc}>"
                    graphql_responses.append({
                        "url": resp.url, "status": resp.status, "ctype": ctype,
                        "resource_type": rtype, "body_len": body_len, "body_preview": body_preview,
                    })

            page.on("response", on_response)
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as exc:  # noqa: BLE001
                nav_error = f"{type(exc).__name__}: {exc}"

            # Cookie-Banner: ein paar neutrale Versuche (kein Tarnungstrick,
            # nur die auf der Seite sichtbaren Knoepfe) - ohne Wegklicken
            # bleibt darunterliegender Inhalt teils verdeckt.
            for sel in ("button:has-text('Alle zulassen')", "button:has-text('Alle akzeptieren')",
                       "#onetrust-accept-btn-handler", "button:has-text('Akzeptieren')"):
                try:
                    page.click(sel, timeout=2000)
                    break
                except Exception:
                    continue

            # Netzruhe: aktiv warten statt fest zu schlafen. Wird das
            # 20s-Fenster nicht erreicht (Saturn haelt oft eine Hintergrund-
            # Verbindung offen - Chat/Tracking-Ping), ist das ein ECHTER
            # Befund und wird als solcher im Report festgehalten, nicht
            # stillschweigend durch die Wartezeit unten kaschiert.
            try:
                page.wait_for_load_state("networkidle", timeout=20000)
            except Exception as exc:  # noqa: BLE001
                idle_error = f"{type(exc).__name__}: {exc}"
                page.wait_for_timeout(5000)  # letzte Chance fuer nachlaufende Requests

            page.wait_for_timeout(2000)

            html = page.content()
            title_text = page.title()

            # Screenshot als Gegenprobe-Beleg.
            try:
                page.screenshot(path=screenshot_path, full_page=False)
            except Exception as exc:  # noqa: BLE001
                screenshot_error = f"{type(exc).__name__}: {exc}"

        finally:
            browser.close()

    finished = datetime.now(timezone.utc).isoformat()

    state, state_error = _extract_preloaded_state(html) if html else (None, "no_html")
    raw_features = _price_features_from_state(state) if state else []
    features, dup_ids = _dedupe_by_product_id(raw_features)
    ld_json_items = _extract_ld_json_itemlist(html) if html else []
    robots_audit_hits = _audit_robots([r["url"] for r in all_xhr])
    non_200 = [r for r in (all_xhr + graphql_responses) if r["status"] != 200]
    # Dubletten (eine URL kann in beiden Listen stehen, wenn sie sowohl
    # xhr/fetch typisiert ist als auch "graphql" im Pfad traegt) werden
    # ueber (url, status) entfernt - sonst zaehlt ein einzelner
    # Nicht-200-Request doppelt.
    seen_keys = set()
    non_200_dedup = []
    for r in non_200:
        key = (r["url"], r["status"])
        if key not in seen_keys:
            seen_keys.add(key)
            non_200_dedup.append({"url": r["url"], "status": r["status"]})

    report = {
        "mode": "browser",
        "started_utc": started,
        "finished_utc": finished,
        "url": url,
        "user_agent": UA,
        "nav_error": nav_error,
        "idle_error": idle_error,
        "networkidle_reached": idle_error is None,
        "screenshot_error": screenshot_error,
        "screenshot_path": screenshot_path if not screenshot_error else None,
        "page_title": title_text if not nav_error else None,
        "html_len": len(html) if not nav_error else 0,
        "graphql_requests_seen_by_handler": graphql_requests_seen,
        "blocked_tabu_calls": blocked_calls,
        "xhr_fetch_responses": all_xhr,
        "xhr_fetch_count": len(all_xhr),
        "robots_disallow_audit_hits": robots_audit_hits,
        "graphql_response_count": len(graphql_responses),
        "non_200_responses": non_200_dedup,
        "preloaded_state_found": state is not None,
        "preloaded_state_error": state_error,
        "price_features_from_ssr_state": features,
        "duplicate_apollo_keys_for_same_product_id": dup_ids,
        "ld_json_itemlist": ld_json_items,
        "console_error_sample": console_errors[:10],
        "graphql_responses": graphql_responses,
    }

    with open(network_log_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    print(json.dumps(
        {k: v for k, v in report.items() if k != "graphql_responses"},
        ensure_ascii=False, indent=2,
    ))
    print(f"\nVoller Report (inkl. GraphQL-Bodies): {network_log_path}")
    print(f"Screenshot: {screenshot_path if not screenshot_error else '(fehlgeschlagen: ' + str(screenshot_error) + ')'}")
    if robots_audit_hits:
        print(f"\n!!! ROBOTS-AUDIT: {len(robots_audit_hits)} beobachtete Requests treffen ein "
              f"Disallow-Muster: {robots_audit_hits}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL, help="Zu ladende Saturn-Seite (Produkt-/Kategorie-/Markenpfad)")
    parser.add_argument("--tag", default="default", help="Dateinamens-Suffix fuer Screenshot/Report unter /tmp (nur [A-Za-z0-9_-])")
    parser.add_argument("--mode", choices=("static", "browser"), default="browser",
                       help="static = reines HTTP (urllib, kein Playwright); browser = Chromium + Screenshot")
    args = parser.parse_args()
    tag = _sanitize_tag(args.tag)

    if args.mode == "static":
        html_path = f"/tmp/saturn-spike-2026-09-05-{tag}.html"
        report_path = f"/tmp/saturn-spike-2026-09-05-{tag}-static-report.json"
        return run_static(args.url, html_path, report_path)

    screenshot_path = f"/tmp/saturn-spike-2026-09-05-{tag}.png"
    network_log_path = f"/tmp/saturn-spike-2026-09-05-{tag}-network.json"
    return run_browser(args.url, screenshot_path, network_log_path)


if __name__ == "__main__":
    raise SystemExit(main())
