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

Aufruf:
    python scripts/finde_quellen.py ziele.yaml --out kandidaten.yaml

ziele.yaml:
    ziele:
      - operator: "Orange"            # oder thema/name fuer Themenquellen
        seiten:
          - "https://www.orange.com/en/newsroom"
          - "https://www.orange.com/en/investors"
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

from telco_radar.collect.http import fetch  # noqa: E402

HTTP_CFG = {"timeout_seconds": 15}

# Pfade, die in dieser Branche ueberdurchschnittlich oft ein Feed sind.
# Reihenfolge = Trefferwahrscheinlichkeit; die Liste bleibt bewusst kurz,
# jeder Eintrag kostet einen Abruf je Ziel.
KANDIDATENPFADE = (
    "/feed", "/rss", "/feed/", "/rss.xml", "/feed.xml", "/atom.xml",
    "/index.xml", "/news/feed", "/news/rss", "/blog/feed", "/blog/rss.xml",
    "/?format=feed&type=rss", "/rss/news", "/en/feed", "/de/feed",
    "/wp-json/wp/v2/posts?per_page=25&_embed=1",
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
        resp = fetch(url, HTTP_CFG)
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


def _ziel_bearbeiten(ziel: dict) -> list[dict]:
    seiten = ziel.get("seiten") or []
    if not seiten:
        return []
    basen = {f"{urlsplit(s).scheme}://{urlsplit(s).netloc}" for s in seiten}

    zu_pruefen: list[str] = []
    for seite in seiten:
        zu_pruefen.extend(_aus_html(seite))
    for basis in sorted(basen):
        zu_pruefen.extend(basis + p for p in KANDIDATENPFADE)
    # Auch Unterpfade der genannten Seiten: /en/newsroom -> /en/newsroom/feed
    for seite in seiten:
        stamm = seite.rstrip("/")
        zu_pruefen.extend([stamm + "/feed", stamm + "/rss",
                           stamm + "?format=feed&type=rss"])
    zu_pruefen = list(dict.fromkeys(zu_pruefen))

    treffer: list[dict] = []
    gesehen: set[str] = set()
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(_pruefe_url, u): u for u in zu_pruefen}
        for fut in as_completed(futs):
            res = fut.result()
            if not res:
                continue
            url, typ = res
            schluessel = url.rstrip("/").lower()
            if schluessel in gesehen:
                continue
            gesehen.add(schluessel)
            eintrag = {"url": url, "type": typ}
            for feld in ("operator", "thema", "name", "website"):
                if ziel.get(feld):
                    eintrag[feld] = ziel[feld]
            eintrag["begruendung"] = "mechanisch gefunden - noch nicht abgenommen"
            treffer.append(eintrag)
    return treffer


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("ziele", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--workers", type=int, default=4)
    args = p.parse_args(argv)

    roh = yaml.safe_load(args.ziele.read_text(encoding="utf-8")) or {}
    ziele = roh.get("ziele") if isinstance(roh, dict) else roh

    alle: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futs = {pool.submit(_ziel_bearbeiten, z): z for z in ziele}
        for fut in as_completed(futs):
            ziel = futs[fut]
            try:
                gefunden = fut.result()
            except Exception as exc:  # noqa: BLE001
                print(f"  ! {ziel.get('operator') or ziel.get('name')}: {exc}")
                continue
            name = ziel.get("operator") or ziel.get("name") or "?"
            print(f"{len(gefunden):>3} Kandidat(en)  {name}")
            for g in gefunden:
                print(f"       {g['type']:9} {g['url']}")
            alle.extend(gefunden)

    args.out.write_text(
        yaml.safe_dump({"kandidaten": alle}, allow_unicode=True, sort_keys=False),
        encoding="utf-8")
    print(f"\n{len(alle)} Kandidaten -> {args.out}")
    print("Naechster Schritt: python scripts/pruefe_quellenvorschlag.py "
          f"{args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
