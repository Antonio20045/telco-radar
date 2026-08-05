#!/usr/bin/env python3
"""Breitensuche nach zusaetzlichen Quellen - mechanisch, ohne Modell.

Der teuerste Teil eines Quellen-Ausbaus ist nicht das Finden, sondern das
Raten: ein Modell schlaegt eine plausible Feed-URL vor, sie ist 404, und die
Pruefung kostet trotzdem einen Abruf. Dieses Skript dreht die Reihenfolge um -
es probiert erst die Wege, auf denen sich Feeds tatsaechlich finden lassen,
und liefert nur ausgelieferte URLs als Kandidaten:

  1. <link rel="alternate" type="application/rss+xml"> auf den angegebenen
     Seiten (Startseite, Newsroom, Investor Relations, ...)
  2. Kandidatenpfade, die in dieser Branche immer wieder funktionieren
     (/feed, /rss, /news/feed, ?format=feed, /wp-json/wp/v2/posts, ...)
  3. WordPress-REST-Endpunkt, wenn die Seite nach WordPress aussieht

Ausgabe ist eine Kandidatendatei fuer scripts/pruefe_quellenvorschlag.py.
Hier wird NICHTS abgenommen - dieses Skript sammelt nur Adressen, die
ueberhaupt etwas ausliefern. Die Abnahme macht allein der Abnahme-Check.

Massenbetrieb
-------------
Fuer den Ausbau auf 1000 Quellen ist das Skript auf Hunderte Ziele ausgelegt:

  * `--aus-watchlist` baut die Ziele selbst aus config/watchlist.yaml und
    config/tech_sources.yaml. Das ist der billigste Zugewinn ueberhaupt -
    kein einziges Unternehmen muss recherchiert werden, die Firmen stehen
    schon da, und erst 10 von 85 Betreibern haben mehr als einen Kanal.
  * `--firmen firmen.yaml` nimmt eine Liste aus Name + Domain (+ optional
    Region/Land/Thema) und probiert dieselben Wege auf neuen Unternehmen.
  * `--cache` merkt sich gepruefte Adressen; ein Abbruch nach 600 Zielen
    kostet dann nicht den ganzen Durchgang.
  * Bereits konfigurierte URLs werden gar nicht erst vorgeschlagen.

Die Host-Drosselung aus collect/http.py ist dabei eingeschaltet: eine Firma
hat schnell zwanzig Kandidatenpfade, und die alle gleichzeitig gegen denselben
Server zu werfen provoziert genau die 429/403, die den Kandidaten dann faelsch-
licherweise als tot ausweisen wuerden.

Aufruf:
    python scripts/finde_quellen.py ziele.yaml --out kandidaten.yaml
    python scripts/finde_quellen.py --aus-watchlist --out kandidaten.yaml
    python scripts/finde_quellen.py --firmen firmen.yaml --out kandidaten.yaml \
        --cache /tmp/gefunden.json

ziele.yaml:
    ziele:
      - operator: "Orange"            # oder thema/name fuer Themenquellen
        seiten:
          - "https://www.orange.com/en/newsroom"
          - "https://www.orange.com/en/investors"

firmen.yaml:
    firmen:
      - name: "Telenor Norge"
        domain: "telenor.no"
        region: europe                # nur beschreibend, fuer den Eintrag
        country: "NO"
"""
from __future__ import annotations

import argparse
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import yaml
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telco_radar.collect.http import configure_throttle, fetch  # noqa: E402
from telco_radar.config import load_config  # noqa: E402
from telco_radar.models import normalize_url  # noqa: E402

# Kurze Zeitgrenze mit Absicht: in einer Breitensuche sind die meisten
# geprobten Adressen 404, und ein Server, der 8 s fuer eine Feed-Datei
# braucht, wird auch im Lauf zum Problem. Ein Timeout kostet hier das
# Sechsfache eines Treffers (zwei User-Agents x drei Versuche).
HTTP_CFG = {"timeout_seconds": 8}

# Pfade, die in dieser Branche ueberdurchschnittlich oft ein Feed sind.
# Reihenfolge = Trefferwahrscheinlichkeit; die Liste bleibt bewusst kurz,
# jeder Eintrag kostet einen Abruf je Ziel.
KANDIDATENPFADE = (
    "/feed", "/rss", "/feed/", "/rss.xml", "/feed.xml", "/atom.xml",
    "/index.xml", "/news/feed", "/news/rss", "/blog/feed", "/blog/rss.xml",
    "/?format=feed&type=rss", "/rss/news", "/en/feed", "/de/feed",
    "/wp-json/wp/v2/posts?per_page=25&_embed=1",
    # Weitere Muster, die im Bestand nachweislich vorkommen bzw. bei
    # Telco-Newsrooms ueberdurchschnittlich oft treffen. Jeder Eintrag kostet
    # einen Abruf je Ziel - die Liste bleibt deshalb kurz und begruendet.
    "/news/feed/", "/press/feed", "/presse/feed", "/media/feed",
    "/newsroom/feed", "/newsroom/rss", "/news.xml", "/press-releases/feed",
    "/en/rss.xml", "/rss/pressreleases.xml", "/feeds/news.xml",
    "/sitemap-news.xml", "/api/news", "/blog/index.xml",
)

# Unterpfade, die AN DIE GENANNTE SEITE gehaengt werden (nicht an die Domain).
_SEITEN_SUFFIXE = ("/feed", "/rss", "/feed/", "/rss.xml",
                   "?format=feed&type=rss")

# Newsroom-Pfade, die auf einer blossen Domain ueberhaupt erst gesucht werden
# muessen: bei --firmen ist nur "telenor.no" bekannt, nicht wo dort die
# Pressemeldungen liegen. Die rel=alternate-Suche braucht aber eine Seite.
NEWSROOM_PFADE = (
    "", "/news", "/en/news", "/newsroom", "/press", "/media",
)

_FEED_TYPES = ("application/rss+xml", "application/atom+xml",
               "application/feed+json", "application/json")
_FEED_ANKER = re.compile(r"(rss|feed|atom)", re.I)


def _ist_feed_inhalt(text: str, content_type: str) -> str:
    """Liefert den Quellentyp ('rss'/'json_api') oder '' wenn es keiner ist."""
    kopf = text[:2000].lstrip()
    ct = (content_type or "").lower()
    if kopf.startswith("<?xml") or "<rss" in kopf[:400].lower() \
            or "<feed" in kopf[:400].lower():
        return "rss"
    if "xml" in ct and ("<item" in text[:6000] or "<entry" in text[:6000]):
        return "rss"
    if kopf.startswith(("[", "{")) and ("json" in ct or True):
        # Nur als json_api melden, wenn ueberhaupt mehrere Datensaetze
        # drinstehen - eine Fehlerseite in JSON ist kein Feed.
        if text.count('"title"') >= 3 or text.count('"headline"') >= 3 \
                or text.count('"link"') >= 3:
            return "json_api"
    return ""


def _pruefe_url(url: str) -> tuple[str, str] | None:
    try:
        resp = fetch(url, HTTP_CFG, schnell=True)
    except Exception:  # noqa: BLE001
        return None
    typ = _ist_feed_inhalt(resp.text, resp.headers.get("content-type", ""))
    return (str(resp.url), typ) if typ else None


def _aus_html(seite: str) -> list[str]:
    """Feed-URLs, die die Seite selbst angibt (rel=alternate) oder verlinkt."""
    try:
        resp = fetch(seite, HTTP_CFG, schnell=True)
    except Exception:  # noqa: BLE001
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    gefunden: list[str] = []
    for link in soup.find_all("link", rel=True):
        rels = [r.lower() for r in (link.get("rel") or [])]
        typ = (link.get("type") or "").lower()
        if "alternate" in rels and typ in _FEED_TYPES and link.get("href"):
            gefunden.append(urljoin(str(resp.url), link["href"]))
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if _FEED_ANKER.search(href) and not href.startswith(("mailto:", "#")):
            if href.lower().endswith((".xml", "/feed", "/feed/", "/rss")) \
                    or "format=feed" in href.lower():
                gefunden.append(urljoin(str(resp.url), href))
    # Reihenfolge erhalten, Dubletten raus
    return list(dict.fromkeys(gefunden))


def _ziel_bearbeiten(ziel: dict, bekannt: set[str] | None = None) -> list[dict]:
    """Ein Ziel in Stufen abarbeiten, mit Frueh-Abbruch.

    Warum Stufen: die erste Fassung probierte alle Seiten UND alle
    Kandidatenpfade UND alle Suffixe - rund 107 Abrufe je Firma. Da die
    Host-Drosselung (zu Recht) nur zwei gleichzeitige Verbindungen je Server
    zulaesst, brauchte ein einziges Ziel damit ueber eine Minute, acht Ziele
    ueber neun. Bei 112 Zielen ist das keine Breitensuche mehr.

    Die Abkuerzung kostet fast nichts: wenn eine Seite ihren Feed per
    <link rel="alternate"> selbst angibt, sind die Kandidatenpfade ueberfluessig
    - sie wuerden dieselbe Adresse noch einmal finden.

      Stufe 1  rel=alternate auf den genannten Seiten (billig, hohe Trefferrate)
      Stufe 2  nur wenn Stufe 1 leer blieb: die Kandidatenpfade auf der Domain
      Stufe 3  nur wenn beides leer blieb: /feed & Co. an den Seitenpfaden
    """
    seiten = ziel.get("seiten") or []
    if not seiten:
        return []
    bekannt = bekannt or set()
    basen = {f"{urlsplit(s).scheme}://{urlsplit(s).netloc}" for s in seiten}

    def _pruefe_viele(urls: list[str]) -> list[tuple[str, str]]:
        urls = [u for u in dict.fromkeys(urls) if _schluessel(u) not in bekannt]
        if not urls:
            return []
        with ThreadPoolExecutor(max_workers=8) as pool:
            return [r for r in pool.map(_pruefe_url, urls) if r]

    # --- Stufe 1: was die Seiten selbst angeben
    angegeben: list[str] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for gefunden in pool.map(_aus_html, seiten):
            angegeben.extend(gefunden)
    gefunden = _pruefe_viele(angegeben)

    # --- Stufe 2: die ueblichen Pfade auf der Domain
    if not gefunden:
        gefunden = _pruefe_viele([b + p for b in sorted(basen)
                                  for p in KANDIDATENPFADE])

    # --- Stufe 3: /feed & Co. an den genannten Seitenpfaden
    if not gefunden:
        gefunden = _pruefe_viele([s.rstrip("/") + suffix for s in seiten
                                  for suffix in _SEITEN_SUFFIXE])

    treffer: list[dict] = []
    gesehen: set[str] = set()
    for url, typ in gefunden:
        schluessel = _schluessel(url)
        if schluessel in gesehen or schluessel in bekannt:
            continue
        gesehen.add(schluessel)
        eintrag = {"url": url, "type": typ}
        for feld in ("operator", "thema", "name", "website", "country",
                     "region"):
            if ziel.get(feld):
                eintrag[feld] = ziel[feld]
        eintrag["begruendung"] = "mechanisch gefunden - noch nicht abgenommen"
        eintrag["herkunft"] = ziel.get("herkunft", "mechanische Breitensuche")
        treffer.append(eintrag)
    return treffer


def _schluessel(url: str) -> str:
    return normalize_url(url).lower()


def ziele_aus_watchlist(root: Path) -> list[dict]:
    """Zweitkanaele: jede Firma, die schon in der Konfiguration steht.

    Der billigste Zugewinn im ganzen Ausbau (Auftrag Abschnitt 4): kein
    Unternehmen muss recherchiert werden, und erst 10 von 85 Betreibern haben
    ueberhaupt mehr als einen Kanal. Als Suchseiten dienen die bereits
    eingetragenen Quellen-URLs, die Unternehmenswebsite und die ueblichen
    Newsroom-Pfade darauf.
    """
    cfg = load_config(root)
    ziele: list[dict] = []
    for op in cfg.operators:
        seiten: list[str] = []
        for src in op.sources:
            seiten.append(src.url)
        if op.website:
            # Nur die Wurzel, NICHT die geratenen Newsroom-Pfade: die
            # bestehende Quellen-URL zeigt bereits auf den Newsroom, und
            # rel=alternate steht bei fast jedem CMS im <head> jeder Seite.
            # Dreizehn Ratepfade je Firma waren der Grund, warum ein
            # Durchgang ueber 112 Betreiber nicht fertig wurde.
            basis = op.website if op.website.startswith("http") \
                else f"https://www.{op.website}"
            seiten.append(basis.rstrip("/"))
        if seiten:
            ziele.append({"operator": op.name, "website": op.website,
                          "country": op.country, "region": op.region_key,
                          "seiten": list(dict.fromkeys(seiten)),
                          "herkunft": "Zweitkanal (aus Watchlist)"})
    for src in cfg.tech_sources:
        ziele.append({"thema": src.theme.removeprefix("thema:"),
                      "name": src.name, "seiten": [src.url],
                      "herkunft": "Zweitkanal (aus tech_sources)"})
    return ziele


def ziele_aus_firmen(pfad: Path) -> list[dict]:
    """Neue Unternehmen: Name + Domain reichen, die Newsroom-Pfade raten wir."""
    roh = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    firmen = roh.get("firmen") if isinstance(roh, dict) else roh
    ziele: list[dict] = []
    for f in firmen or []:
        domain = str(f.get("domain") or "").strip().rstrip("/")
        if not domain:
            continue
        basis = domain if domain.startswith("http") else f"https://www.{domain}"
        ziel = {"seiten": [basis.rstrip("/") + p for p in NEWSROOM_PFADE],
                "website": domain,
                "herkunft": f.get("herkunft", "Firmenliste")}
        for feld in ("operator", "thema", "name", "country", "region"):
            if f.get(feld):
                ziel[feld] = f[feld]
        if not ziel.get("operator") and not ziel.get("thema") and f.get("name"):
            ziel["operator"] = f["name"]
        ziele.append(ziel)
    return ziele


def bekannte_urls(root: Path) -> set[str]:
    """Alles, was schon konfiguriert ist - das schlaegt niemand noch mal vor."""
    try:
        cfg = load_config(root)
    except Exception:  # noqa: BLE001
        return set()
    urls = {_schluessel(s.url) for op in cfg.operators for s in op.sources}
    urls |= {_schluessel(s.url) for s in cfg.news_sources}
    urls |= {_schluessel(s.url) for s in cfg.tech_sources}
    return urls


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("ziele", type=Path, nargs="?")
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--aus-watchlist", action="store_true",
                   help="Ziele aus der bestehenden Konfiguration bauen "
                        "(Zweitkanaele) - keine Recherche noetig")
    p.add_argument("--firmen", type=Path,
                   help="YAML mit name+domain je Firma (neue Unternehmen)")
    p.add_argument("--cache", type=Path,
                   help="bereits bearbeitete Ziele ueberspringen "
                        "(Wiederaufnahme nach Abbruch)")
    p.add_argument("--limit", type=int, help="nur die ersten N Ziele")
    args = p.parse_args(argv)

    root = args.root.resolve()
    # Ohne Drosselung schlagen bei 16 gleichzeitigen Zielen mal eben 200
    # Verbindungen gleichzeitig los - und mehrere davon auf denselben Server.
    configure_throttle(4, 0.15)

    ziele: list[dict] = []
    if args.ziele:
        roh = yaml.safe_load(args.ziele.read_text(encoding="utf-8")) or {}
        ziele.extend(roh.get("ziele") if isinstance(roh, dict) else roh)
    if args.aus_watchlist:
        ziele.extend(ziele_aus_watchlist(root))
    if args.firmen:
        ziele.extend(ziele_aus_firmen(args.firmen))
    if not ziele:
        p.error("Keine Ziele: Datei angeben, --aus-watchlist oder --firmen")

    bekannt = bekannte_urls(root)
    erledigt: set[str] = set()
    alle: list[dict] = []
    if args.cache and args.cache.exists():
        gespeichert = yaml.safe_load(args.cache.read_text(encoding="utf-8")) or {}
        alle = gespeichert.get("kandidaten") or []
        erledigt = set(gespeichert.get("erledigte_ziele") or [])
        print(f"Cache: {len(erledigt)} Ziele erledigt, "
              f"{len(alle)} Kandidaten bereits gefunden")

    def _kennung(z: dict) -> str:
        return z.get("operator") or z.get("name") or z.get("thema") or \
            (z.get("seiten") or ["?"])[0]

    offen = [z for z in ziele if _kennung(z) not in erledigt]
    if args.limit:
        offen = offen[:args.limit]
    print(f"{len(offen)} Ziele werden bearbeitet "
          f"({len(bekannt)} URLs sind bereits konfiguriert und werden "
          f"uebersprungen)")

    fertig = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futs = {pool.submit(_ziel_bearbeiten, z, bekannt): z for z in offen}
        for fut in as_completed(futs):
            ziel = futs[fut]
            fertig += 1
            try:
                gefunden = fut.result()
            except Exception as exc:  # noqa: BLE001
                print(f"  ! {_kennung(ziel)}: {exc}")
                continue
            erledigt.add(_kennung(ziel))
            if gefunden:
                print(f"{len(gefunden):>3} Kandidat(en)  {_kennung(ziel)}")
                for g in gefunden:
                    print(f"       {g['type']:9} {g['url']}")
            alle.extend(gefunden)
            # Nach jedem Ziel sichern: bei 800 Zielen ist ein Abbruch die
            # Regel, nicht die Ausnahme.
            if args.cache and fertig % 10 == 0:
                args.cache.write_text(yaml.safe_dump(
                    {"kandidaten": alle, "erledigte_ziele": sorted(erledigt)},
                    allow_unicode=True, sort_keys=False), encoding="utf-8")

    # Dubletten unter den Funden selbst (mehrere Ziele finden denselben Feed)
    einmalig: dict[str, dict] = {}
    for k in alle:
        einmalig.setdefault(_schluessel(k["url"]), k)
    alle = list(einmalig.values())

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        yaml.safe_dump({"kandidaten": alle}, allow_unicode=True, sort_keys=False),
        encoding="utf-8")
    if args.cache:
        args.cache.write_text(yaml.safe_dump(
            {"kandidaten": alle, "erledigte_ziele": sorted(erledigt)},
            allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"\n{len(alle)} Kandidaten -> {args.out}")
    print("Naechster Schritt: python scripts/pruefe_quellenvorschlag.py "
          f"{args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
