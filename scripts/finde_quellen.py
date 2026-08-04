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
  3. **Musteruebertragung**: liegt ein Betreiber auf einer IR-Plattform,
     liegen Dutzende andere auf derselben. Ein bekanntes Muster auf 50 Firmen
     anzuwenden kostet 50 Abrufe und null Token.

Ausgabe ist eine Kandidatendatei fuer scripts/pruefe_quellenvorschlag.py.
Hier wird NICHTS abgenommen - dieses Skript sammelt nur Adressen, die
ueberhaupt etwas ausliefern. Die Abnahme macht allein der Abnahme-Check.

Massenbetrieb
-------------
Auf 1000 Quellen ausgelegt und deshalb in drei Phasen statt je Ziel:

  A  Startseiten holen (host-gedrosselt) und rel=alternate auswerten
  B  je Ziel die zu probierenden URLs zusammenstellen (kein Netz)
  C  ALLE URLs auf einmal probieren - ueber denselben Sammelplan wie die
     Pipeline, also je Host nacheinander mit Mindestabstand

Vorher probierte jedes Ziel seine ~25 URLs mit acht gleichzeitigen
Verbindungen gegen denselben Host - genau das, was 429/403 provoziert.
Ein Cache haelt jedes Ergebnis fest, damit ein Abbruch nichts kostet.

Aufruf:
    python scripts/finde_quellen.py ziele.yaml --out kandidaten.yaml
    python scripts/finde_quellen.py --aus-watchlist --out kandidaten.yaml
    python scripts/finde_quellen.py --aus-watchlist --muster --out k.yaml

ziele.yaml:
    ziele:
      - operator: "Orange"            # oder thema/name fuer Themenquellen
        slug: "orange"                # optional, fuer die Musteruebertragung
        seiten:
          - "https://www.orange.com/en/newsroom"
          - "https://www.orange.com/en/investors"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
import yaml
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telco_radar.collect import sammelplan  # noqa: E402
from telco_radar.collect.http import BROWSER_UA, fetch  # noqa: E402
from telco_radar.config import load_config  # noqa: E402
from telco_radar.models import normalize_url  # noqa: E402

HTTP_CFG = {"timeout_seconds": 8}

# Pfade, die in dieser Branche ueberdurchschnittlich oft ein Feed sind.
# Reihenfolge = Trefferwahrscheinlichkeit; die Liste bleibt bewusst kurz,
# jeder Eintrag kostet einen Abruf je Ziel.
KANDIDATENPFADE = (
    "/feed", "/rss", "/feed/", "/rss.xml", "/feed.xml", "/atom.xml",
    "/index.xml", "/news/feed", "/news/rss", "/blog/feed", "/blog/rss.xml",
    "/?format=feed&type=rss", "/rss/news", "/en/feed", "/de/feed",
    "/wp-json/wp/v2/posts?per_page=25&_embed=1",
)

# Musteruebertragung. Jedes Muster stammt aus einer Quelle, die im Bestand
# nachweislich funktioniert - hier wird nichts erfunden, sondern uebertragen.
#   {host}  = Host der Unternehmenswebsite (ohne www.)
#   {slug}  = Kurzname der Firma, klein, ohne Leerzeichen
MUSTER_EIGENE_DOMAIN = (
    # Investor Relations auf der eigenen Domain (T-Mobile, Charter, Broadcom)
    "https://investor.{host}/rss/pressrelease.aspx?T=1",
    "https://investors.{host}/rss/pressrelease.aspx?T=1",
    "https://investor.{host}/rss/news-releases.xml",
    "https://investors.{host}/rss/news-releases.xml",
    "https://ir.{host}/rss/news-releases.xml",
    # Newsroom-Subdomains, die eigene Feeds fahren
    "https://newsroom.{host}/feed",
    "https://news.{host}/feed/",
    "https://blog.{host}/feed",
    "https://press.{host}/feed",
    # Joomla (The Fast Mode, Developing Telecoms) und WordPress
    "https://{host}/?format=feed&type=rss",
    "https://{host}/wp-json/wp/v2/posts?per_page=25",
    "https://www.{host}/wp-json/wp/v2/posts?per_page=25",
)
MUSTER_PLATTFORM = (
    # Verbreitungsdienste, die im Bestand bereits als offizieller Kanal
    # eingetragen sind (Telia, Ericsson ueber Cision; China Mobile ueber
    # irasia). Die Domain-Ausnahme muss im YAML trotzdem begruendet werden.
    "https://news.cision.com/{slug}/rss",
    "https://www.irasia.com/cgi-local/news/rss.cgi?id={slug}&loc=hk&t=p",
    "https://mfn.se/all/a/{slug}/rss",
)

_FEED_TYPES = ("application/rss+xml", "application/atom+xml",
               "application/feed+json", "application/json")
_FEED_ANKER = re.compile(r"(rss|feed|atom)", re.I)


# Ein Feed ohne Eintraege ist kein Fund. mfn.se beantwortet JEDEN Firmen-Slug
# mit einem gueltigen, leeren RSS-Dokument (HTTP 200, 654 Byte) - ohne diese
# Schwelle produziert die Musteruebertragung fuer jede Firma der Welt einen
# Kandidaten, den erst der Abnahme-Check wieder wegwirft.
MIN_EINTRAEGE = 3


def _ist_feed_inhalt(text: str, content_type: str) -> str:
    """Liefert den Quellentyp ('rss'/'json_api') oder '' wenn es keiner ist."""
    kopf = text[:2000].lstrip()
    ct = (content_type or "").lower()
    eintraege = text.count("<item") + text.count("<entry")
    if kopf.startswith("<?xml") or "<rss" in kopf[:400].lower() \
            or "<feed" in kopf[:400].lower():
        return "rss" if eintraege >= MIN_EINTRAEGE else ""
    if "xml" in ct and eintraege >= MIN_EINTRAEGE:
        return "rss"
    if kopf.startswith(("[", "{")) and ("json" in ct or True):
        # Nur als json_api melden, wenn ueberhaupt mehrere Datensaetze
        # drinstehen - eine Fehlerseite in JSON ist kein Feed.
        if text.count('"title"') >= 3 or text.count('"headline"') >= 3 \
                or text.count('"link"') >= 3:
            return "json_api"
    return ""


def _pruefe_url(url: str) -> tuple[str, str] | None:
    """Ein Versuch, kurzer Timeout, KEIN Backoff.

    Bewusst nicht ueber collect.http.fetch: das probiert zwei User-Agents
    mit je zwei Backoff-Pausen (4 s und 9 s) und braucht fuer eine URL, die
    es schlicht nicht gibt, bis zu 26 Sekunden. Beim Probieren sind die
    Fehlschlaege aber der Normalfall - von den Kandidatenpfaden trifft
    hoechstens einer. Hier wird nichts abgenommen; wer haengenbleibt, faellt
    einfach raus, und der Abnahme-Check laeuft anschliessend mit dem echten
    Collector ueber die Treffer.
    """
    try:
        resp = httpx.get(url, timeout=HTTP_CFG["timeout_seconds"],
                         follow_redirects=True,
                         headers={"User-Agent": BROWSER_UA,
                                  "Accept": "application/rss+xml,"
                                            "application/xml,text/xml,"
                                            "application/json,*/*"})
        if resp.status_code >= 400:
            return None
    except Exception:  # noqa: BLE001
        return None
    typ = _ist_feed_inhalt(resp.text, resp.headers.get("content-type", ""))
    return (str(resp.url), typ) if typ else None


def _aus_html(seite: str) -> list[str]:
    """Feed-URLs, die die Seite selbst angibt (rel=alternate) oder verlinkt."""
    try:
        resp = fetch(seite, HTTP_CFG)
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


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def zu_probieren(ziel: dict, gefunden_im_html: list[str],
                 mit_mustern: bool) -> list[str]:
    """Phase B: alle URLs eines Ziels - ohne Netz, damit sich der Plan
    vorher zaehlen laesst."""
    seiten = ziel.get("seiten") or []
    urls: list[str] = list(gefunden_im_html)
    basen = {f"{urlsplit(s).scheme}://{urlsplit(s).netloc}" for s in seiten
             if urlsplit(s).netloc}
    for basis in sorted(basen):
        urls.extend(basis + p for p in KANDIDATENPFADE)
    # Auch Unterpfade der genannten Seiten: /en/newsroom -> /en/newsroom/feed
    for seite in seiten:
        stamm = seite.rstrip("/")
        urls.extend([stamm + "/feed", stamm + "/rss",
                     stamm + "?format=feed&type=rss"])
    if mit_mustern:
        hosts = {urlsplit(b).netloc.removeprefix("www.") for b in basen}
        for host in sorted(h for h in hosts if h):
            urls.extend(m.format(host=host) for m in MUSTER_EIGENE_DOMAIN)
        slug = ziel.get("slug") or _slug(ziel.get("operator")
                                         or ziel.get("name") or "")
        if slug:
            urls.extend(m.format(slug=slug) for m in MUSTER_PLATTFORM)
    return list(dict.fromkeys(urls))


def ziele_aus_watchlist(root: Path) -> list[dict]:
    """Jeder Betreiber der Watchlist wird zum Ziel.

    Der billigste Zugewinn ueberhaupt: hier ist kein einziger neuer Betreiber
    zu recherchieren, die Firmen stehen alle schon da - nur eben mit genau
    einem Kanal.
    """
    cfg = load_config(root)
    ziele: list[dict] = []
    for op in cfg.operators:
        seiten = [s.url for s in op.sources]
        if op.website:
            seiten.insert(0, op.website if op.website.startswith("http")
                          else f"https://{op.website}")
        if not seiten:
            continue
        ziele.append({"operator": op.name, "website": op.website,
                      "slug": _slug(op.name), "seiten": seiten})
    return ziele


class Probencache:
    """Was schon einmal probiert wurde, wird nicht noch einmal abgerufen."""

    def __init__(self, pfad: Path | None):
        self.pfad = pfad
        self.eintraege: dict[str, list | None] = {}
        self._sperre = threading.Lock()
        self._seit_speichern = 0
        if pfad and pfad.exists():
            try:
                self.eintraege = json.loads(pfad.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

    def hat(self, url: str) -> bool:
        return normalize_url(url) in self.eintraege

    def hole(self, url: str):
        return self.eintraege.get(normalize_url(url))

    def merke(self, url: str, ergebnis) -> None:
        with self._sperre:
            self.eintraege[normalize_url(url)] = ergebnis
            self._seit_speichern += 1
            # Nicht bei jedem Treffer schreiben: bei 25 000 probierten URLs
            # waere das 25 000-mal die ganze Datei.
            if self.pfad and self._seit_speichern >= 200:
                self._schreiben()

    def _schreiben(self) -> None:
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        self.pfad.write_text(json.dumps(self.eintraege, ensure_ascii=False),
                             encoding="utf-8")
        self._seit_speichern = 0

    def sichern(self) -> None:
        if self.pfad:
            with self._sperre:
                self._schreiben()


def _host_gruppen_abarbeiten(urls: list[str], arbeit, workers: int,
                             abstand: float = 1.0) -> None:
    """URLs host-gedrosselt abarbeiten - derselbe Plan wie in der Pipeline."""
    class _Traeger:
        def __init__(self, url): self.url = url

    gruppen = sammelplan([(_Traeger(u),) for u in urls], 1,
                         url_von=lambda j: j[0].url)

    def _gruppe(gruppe):
        for n, (traeger,) in enumerate(gruppe):
            if n and abstand:
                time.sleep(abstand)
            arbeit(traeger.url)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        list(pool.map(_gruppe, gruppen))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("ziele", nargs="?", type=Path)
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--aus-watchlist", action="store_true",
                   help="alle Betreiber der Watchlist als Ziele nehmen")
    p.add_argument("--muster", action="store_true",
                   help="bekannte IR-/Plattform-Muster mit uebertragen")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--workers", type=int, default=24,
                   help="gleichzeitig bearbeitete HOST-Gruppen")
    p.add_argument("--cache", type=Path, default=Path("outputs/probencache.json"))
    p.add_argument("--ohne-cache", action="store_true")
    p.add_argument("--limit", type=int, default=0,
                   help="nur die ersten N Ziele (fuer Probelaeufe)")
    args = p.parse_args(argv)

    if args.aus_watchlist:
        ziele = ziele_aus_watchlist(args.root.resolve())
    elif args.ziele:
        roh = yaml.safe_load(args.ziele.read_text(encoding="utf-8")) or {}
        ziele = roh.get("ziele") if isinstance(roh, dict) else roh
    else:
        p.error("Entweder eine Zieldatei oder --aus-watchlist angeben")
    if args.limit:
        ziele = ziele[:args.limit]
    print(f"{len(ziele)} Ziele")

    cache = Probencache(None if args.ohne_cache else args.cache)

    # --- Phase A: Startseiten holen, rel=alternate auswerten
    startseiten = list(dict.fromkeys(
        s for z in ziele for s in (z.get("seiten") or [])))
    aus_html: dict[str, list[str]] = {}
    sperre = threading.Lock()

    def _startseite(url: str) -> None:
        treffer = _aus_html(url)
        with sperre:
            aus_html[url] = treffer

    print(f"Phase A: {len(startseiten)} Startseiten auf rel=alternate pruefen")
    _host_gruppen_abarbeiten(startseiten, _startseite, args.workers)

    # --- Phase B: Plan bauen (kein Netz)
    plan: dict[str, list[str]] = {}
    for n, ziel in enumerate(ziele):
        html_treffer = [u for s in (ziel.get("seiten") or [])
                        for u in aus_html.get(s, [])]
        plan[str(n)] = zu_probieren(ziel, html_treffer, args.muster)
    alle_urls = list(dict.fromkeys(u for v in plan.values() for u in v))
    offen = [u for u in alle_urls if not cache.hat(u)]
    print(f"Phase B: {len(alle_urls)} URLs zu probieren, "
          f"{len(alle_urls) - len(offen)} schon im Cache")

    # --- Phase C: probieren, host-gedrosselt
    def _probe(url: str) -> None:
        ergebnis = _pruefe_url(url)
        cache.merke(url, list(ergebnis) if ergebnis else None)

    print(f"Phase C: {len(offen)} Abrufe, {args.workers} Host-Gruppen "
          f"gleichzeitig")
    _host_gruppen_abarbeiten(offen, _probe, args.workers)
    cache.sichern()

    # --- Phase D: Kandidatendatei schreiben
    alle: list[dict] = []
    gesehen: set[str] = set()
    for n, ziel in enumerate(ziele):
        name = ziel.get("operator") or ziel.get("name") or "?"
        treffer = []
        for url in plan[str(n)]:
            ergebnis = cache.hole(url)
            if not ergebnis:
                continue
            echte_url, typ = ergebnis
            schluessel = normalize_url(echte_url)
            if schluessel in gesehen:
                continue
            gesehen.add(schluessel)
            eintrag = {"url": echte_url, "type": typ}
            for feld in ("operator", "thema", "name", "website"):
                if ziel.get(feld):
                    eintrag[feld] = ziel[feld]
            eintrag["begruendung"] = \
                "mechanisch gefunden - noch nicht abgenommen"
            treffer.append(eintrag)
        if treffer:
            print(f"{len(treffer):>3} Kandidat(en)  {name}")
            for g in treffer:
                print(f"       {g['type']:9} {g['url']}")
        alle.extend(treffer)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        yaml.safe_dump({"kandidaten": alle}, allow_unicode=True, sort_keys=False),
        encoding="utf-8")
    print(f"\n{len(alle)} Kandidaten -> {args.out}")
    print("Naechster Schritt: python scripts/pruefe_quellenvorschlag.py "
          f"{args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
