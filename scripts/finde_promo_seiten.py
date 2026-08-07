#!/usr/bin/env python3
"""Mechanische Breitensuche nach WEITEREN Aktionsseiten je Marke.

Das Gegenstueck zu scripts/finde_quellen.py, aber fuer die Promo-Rubrik. Dort
wird nach Feeds gesucht (`rel=alternate`, dann Kandidatenpfade); hier gibt es
keine Feeds - eine Aktionsseite ist eine gewoehnliche HTML-Seite. Gesucht
wird deshalb in zwei Stufen:

  Stufe 1  LINKERNTE. Die schon konfigurierten Seiten der Marke werden
           abgerufen und ihre eigenen Links gelesen. Eine Aktionsuebersicht
           verlinkt fast immer genau das, was ihr fehlt: die einzelnen
           Kampagnen-Landingpages. Das ist kein Raten, sondern die Struktur
           der Seite - dasselbe Prinzip, aus dem finde_quellen.py zuerst
           `rel=alternate` liest und erst danach Pfade probiert.
  Stufe 2  KANDIDATENPFADE. Nur fuer Marken, bei denen Stufe 1 wenig brachte:
           eine feste Liste ueblicher Pfade auf der Markendomain
           (/aktionen, /angebote, /deals, /tarife/aktion, ...).

Bewertet wird jeder Kandidat nach Angebotssignalen im Pfad und im Linktext
(scripts/pruefe_promo_seite.SIGNALE fuer den spaeteren Volltext). Dieses
Skript sagt NUR, WO nachgesehen werden soll. Ob eine Seite taugt, entscheidet
allein scripts/pruefe_promo_seite.py - die Ausgabe hier ist genau dessen
Eingabeformat.

Aufruf
------
    python scripts/finde_promo_seiten.py                    # alle Marken
    python scripts/finde_promo_seiten.py --marke congstar --marke Blau
    python scripts/finde_promo_seiten.py --je-marke 8 --yaml kandidaten.yaml

Sandbox-Hinweis: `kind: js`-Seiten lassen sich lokal nicht rendern (Chromium
kommt durch den Agent-Proxy nicht ins Netz, siehe CLAUDE.md). Dieses Skript
faellt fuer sie automatisch auf reines HTTP zurueck und markiert das im
Protokoll - ein JS-lastiger Anbieter liefert lokal also weniger Kandidaten
als in GitHub Actions, aber nie einen falschen.
"""
from __future__ import annotations

import argparse
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import yaml
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telco_radar.collect.http import fetch  # noqa: E402
from telco_radar.config import load_config  # noqa: E402
from telco_radar.promo_config import _normalize_url, load_promo_config  # noqa: E402

# Woerter, die im PFAD einer URL auf eine Aktionsseite hindeuten. Der Pfad ist
# das verlaesslichere Signal als der Linktext: Linktexte sind Werbesprache
# ("Jetzt zugreifen"), Pfade sind von Redaktionssystemen vergeben und folgen
# der Struktur des Angebots.
PFAD_SIGNALE = {
    "aktion": 3, "aktionen": 3, "angebot": 3, "angebote": 3, "deal": 3,
    "deals": 3, "promo": 3, "kampagne": 3, "sale": 3, "rabatt": 3,
    "sparen": 2, "bonus": 2, "praemie": 2, "prämie": 2, "wechsel": 2,
    "wechselbonus": 3, "wechseln": 2, "neukunden": 2, "black-friday": 3,
    "blackfriday": 3, "weihnachten": 2, "sommer": 1, "winter": 1,
    "tarife": 2, "tarif": 2, "handytarife": 2, "handyvertrag": 2,
    "handys": 2, "smartphones": 2, "handy-mit-vertrag": 3, "prepaid": 2,
    "esim": 1, "young": 2, "jung": 1, "studenten": 2, "familie": 1,
    "vorteile": 1, "specials": 2, "special": 2, "highlights": 1,
    "top-angebote": 3, "guenstig": 1, "günstig": 1,
}
# Woerter im Linktext. Schwaecher gewichtet als der Pfad, aber sie fangen die
# Faelle, in denen der Pfad nur eine Kampagnen-ID ist.
TEXT_SIGNALE = ("aktion", "angebot", "deal", "rabatt", "sparen", "bonus",
                "prämie", "gratis", "kostenlos", "sale", "wechsel", "tarif",
                "%", "€", "gb ")

# Pfade, die NIE eine Aktionsseite sind. Ohne diese Liste erntet Stufe 1 vor
# allem Rechtstexte und Servicebereiche - die tragen dieselben Werbewoerter im
# Fliesstext und wuerden den Check anschliessend teuer beschaeftigen.
PFAD_SPERRE = re.compile(
    r"/(agb|impressum|datenschutz|widerruf|rechtliche|legal|cookie|"
    r"kundencenter|mein[-_]?|login|anmelden|registrier|warenkorb|checkout|"
    r"bestell|hilfe|faq|support|kontakt|karriere|jobs|presse-?kontakt|"
    r"suche|search|sitemap|newsletter|filialen|shops?/|store-?finder|"
    r"netzabdeckung|verfuegbarkeit|störung|stoerung|blog/autor)",
    re.I)
# Dateiendungen, die keine Seite sind.
ENDUNG_SPERRE = re.compile(r"\.(pdf|jpe?g|png|gif|svg|webp|zip|xml|css|js)$", re.I)

# Kandidatenpfade fuer Stufe 2. Reihenfolge = Wahrscheinlichkeit, gemessen an
# den 15 bereits konfigurierten Seiten (dort dominieren /angebote, /aktionen,
# /handytarife und /deals).
KANDIDATENPFADE = (
    "/aktionen", "/angebote", "/deals", "/aktion", "/promotions",
    "/handytarife", "/handytarife/angebote", "/tarife", "/tarife/aktionen",
    "/handys", "/handy-mit-vertrag", "/smartphones", "/prepaid",
    "/wechselbonus", "/wechseln", "/neukunden", "/specials",
    "/unterwegs/aktionen", "/mobilfunk/aktionen", "/mobilfunk/angebote",
    "/handytarife/aktionen", "/angebote/aktionen", "/top-angebote",
)
# Deckel je Marke und Stufe. Ein Kandidat kostet spaeter einen vollen
# Pruefabruf - Breite ist gewollt, Beliebigkeit nicht.
MAX_JE_MARKE = 12


def _saeubere(url: str) -> str:
    """Fragment und Query weg, Schraegstrich vereinheitlicht. Query-Parameter
    auf einer Aktionsseite sind fast immer Tracking oder ein Filterzustand -
    beide erzeugen sonst dutzende Varianten derselben Seite."""
    t = urlsplit(url)
    pfad = t.path or "/"
    if len(pfad) > 1 and pfad.endswith("/"):
        pfad = pfad[:-1]
    return urlunsplit((t.scheme, t.netloc, pfad, "", ""))


def _pfad_punkte(url: str) -> int:
    stuecke = re.split(r"[/\-_]", urlsplit(url).path.lower())
    return sum(PFAD_SIGNALE.get(s, 0) for s in stuecke if s)


def _text_punkte(text: str) -> int:
    low = (text or "").lower()
    return sum(1 for w in TEXT_SIGNALE if w in low)


def _tauglich(url: str, basis_host: str) -> bool:
    t = urlsplit(url)
    if t.scheme not in ("http", "https"):
        return False
    if t.netloc.lower() != basis_host:
        return False
    if PFAD_SPERRE.search(t.path or "") or ENDUNG_SPERRE.search(t.path or ""):
        return False
    # Sehr tiefe Pfade sind fast immer einzelne Produkt-Detailseiten (ein
    # Geraet, eine SKU). Die gehoeren als Tiefenlink an ein Angebot, nicht als
    # eigene Quelle in die Konfiguration.
    return len([s for s in (t.path or "").split("/") if s]) <= 3


def _hole(url: str, http_cfg: dict) -> str:
    return fetch(url, http_cfg).text


def ernte_links(html: str, basis_url: str) -> list[dict]:
    """Stufe 1: Links der Seite, die nach Aktionsseite aussehen.

    Bewusst OHNE das Entfernen von <nav>: die Aktionsuebersichten der grossen
    Anbieter fuehren ihre Kampagnen genau dort, in einer eigenen
    Navigationsleiste. Dafuer sperrt PFAD_SPERRE die Servicebereiche, die
    sonst mit hereinkaemen."""
    basis_host = urlsplit(basis_url).netloc.lower()
    gefunden: dict[str, dict] = {}
    try:
        soup = BeautifulSoup(html or "", "html.parser")
    except Exception:  # noqa: BLE001
        return []
    for a in soup.find_all("a", href=True):
        roh = (a.get("href") or "").strip()
        if not roh or roh.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        url = _saeubere(urljoin(basis_url, roh))
        if not _tauglich(url, basis_host):
            continue
        text = a.get_text(" ", strip=True)[:120]
        punkte = _pfad_punkte(url) + _text_punkte(text)
        if punkte < 3:
            continue
        vorher = gefunden.get(url)
        if vorher is None or punkte > vorher["punkte"]:
            gefunden[url] = {"url": url, "punkte": punkte, "text": text,
                             "stufe": "linkernte"}
    return sorted(gefunden.values(), key=lambda k: -k["punkte"])


def probiere_pfade(basis_url: str, http_cfg: dict, bekannt: set[str],
                   workers: int = 6) -> list[dict]:
    """Stufe 2: feste Kandidatenpfade auf der Markendomain durchprobieren.
    Laeuft nur, wenn Stufe 1 wenig brachte - sie erzeugt echten Traffic auf
    Seiten, die es vermutlich gar nicht gibt."""
    t = urlsplit(basis_url)
    wurzel = f"{t.scheme}://{t.netloc}"
    ziele = [wurzel + p for p in KANDIDATENPFADE
             if _normalize_url(wurzel + p) not in bekannt]

    def einer(url):
        try:
            resp = fetch(url, http_cfg)
        except Exception:  # noqa: BLE001
            return None
        if getattr(resp, "status_code", 0) != 200:
            return None
        # Eine Weiterleitung auf die Startseite ist ein Treffer ohne Inhalt.
        ziel = _saeubere(str(getattr(resp, "url", url)))
        if urlsplit(ziel).path.strip("/") == "":
            return None
        if _normalize_url(ziel) in bekannt:
            return None
        return {"url": ziel, "punkte": _pfad_punkte(ziel) + 2, "text": "",
                "stufe": "pfadprobe"}

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        roh = [r for r in pool.map(einer, ziele) if r]
    entdoppelt: dict[str, dict] = {}
    for r in roh:
        entdoppelt.setdefault(r["url"], r)
    return sorted(entdoppelt.values(), key=lambda k: -k["punkte"])


def suche_fuer_marke(src, http_cfg: dict, je_marke: int,
                     bekannt_global: set[str]) -> dict:
    """Beide Stufen fuer eine Marke. Gibt Kandidaten im Eingabeformat von
    scripts/pruefe_promo_seite.py zurueck."""
    bericht = {"marke": src.name, "seiten_gelesen": 0, "fehler": [],
               "kandidaten": []}
    bekannt = set(bekannt_global) | {_normalize_url(p.url) for p in src.pages}

    treffer: dict[str, dict] = {}
    for page in src.crawled_pages:
        try:
            html = _hole(page.url, http_cfg)
        except Exception as exc:  # noqa: BLE001
            bericht["fehler"].append(f"{page.url}: {type(exc).__name__}")
            continue
        bericht["seiten_gelesen"] += 1
        for k in ernte_links(html, page.url):
            if _normalize_url(k["url"]) in bekannt:
                continue
            vorher = treffer.get(k["url"])
            if vorher is None or k["punkte"] > vorher["punkte"]:
                treffer[k["url"]] = k

    if len(treffer) < je_marke:
        for k in probiere_pfade(src.url, http_cfg, bekannt | set(
                _normalize_url(u) for u in treffer)):
            treffer.setdefault(k["url"], k)

    beste = sorted(treffer.values(), key=lambda k: (-k["punkte"], k["url"]))[:je_marke]
    bericht["kandidaten"] = [
        {"marke": src.name, "url": k["url"],
         # Die Art der Leitseite ist die beste verfuegbare Annahme fuer eine
         # weitere Seite derselben Marke: JS-Rendering ist eine Eigenschaft
         # des Frontends, nicht der einzelnen Seite. Der Abnahme-Check misst
         # danach ohnehin nach, ob unter dieser Annahme Text herauskommt.
         "kind": src.kind,
         "punkte": k["punkte"], "stufe": k["stufe"],
         "begruendung": k["text"] or f"Pfadsignale: {_pfad_punkte(k['url'])}"}
        for k in beste]
    return bericht


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--marke", action="append", default=[],
                   help="nur diese Marke(n); mehrfach angebbar")
    p.add_argument("--je-marke", type=int, default=MAX_JE_MARKE)
    p.add_argument("--yaml", type=Path,
                   help="Kandidaten als Eingabedatei fuer pruefe_promo_seite.py")
    p.add_argument("--workers", type=int, default=4)
    args = p.parse_args()

    root = args.root.resolve()
    promo_cfg = load_promo_config(root)
    http_cfg = load_config(root).settings.get("http", {})
    marken = [s for s in promo_cfg.crawled_sources
              if not args.marke or s.name in args.marke]
    bekannt_global = {_normalize_url(p.url) for s in promo_cfg.sources
                      for p in s.pages}

    print(f"Suche weitere Aktionsseiten fuer {len(marken)} Marke(n) "
          f"(Bestand: {promo_cfg.page_count} Seiten)\n")
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        berichte = list(pool.map(
            lambda s: suche_fuer_marke(s, http_cfg, args.je_marke, bekannt_global),
            marken))

    alle: list[dict] = []
    for b in sorted(berichte, key=lambda b: b["marke"]):
        print(f"{b['marke']:24} {len(b['kandidaten']):>2} Kandidaten "
              f"({b['seiten_gelesen']} Bestandsseite(n) gelesen)"
              + (f"  FEHLER: {'; '.join(b['fehler'])}" if b["fehler"] else ""))
        for k in b["kandidaten"]:
            print(f"      {k['punkte']:>2}  [{k['stufe']:9}] {k['url']}")
        alle.extend(b["kandidaten"])

    print(f"\n{len(alle)} Kandidaten insgesamt.")
    if args.yaml:
        args.yaml.parent.mkdir(parents=True, exist_ok=True)
        args.yaml.write_text(
            yaml.safe_dump({"kandidaten": alle}, allow_unicode=True,
                           sort_keys=False),
            encoding="utf-8")
        print(f"Geschrieben: {args.yaml}")
        print(f"Weiter mit: python scripts/pruefe_promo_seite.py {args.yaml}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
