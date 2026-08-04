#!/usr/bin/env python3
"""Abnahme-Check fuer vorgeschlagene Quellen - maschinell, nicht behauptet.

Warum es dieses Skript gibt
---------------------------
In frueheren Sessions haben Agents Quellen als "verifiziert" gemeldet, die
ueber den echten Projekt-Collector 0 Meldungen lieferten: geprueft wurde mit
einem eigenen Skript, eigenem User-Agent, eigenem Parser. Das ist der
teuerste Fehler in diesem Projekt. Hier laeuft jeder Vorschlag deshalb durch
GENAU den Pfad, den auch die Pipeline nimmt - `telco_radar.collect.
collect_source(...)` - und die Kriterien aus AUFTRAG_QUELLEN_AUSBAU.md
Abschnitt 4 werden im Code geprueft, nicht im Modell.

Ein Modell, das "ich habe es geprueft" sagt, zaehlt nicht. Nur ein PASS hier.

Eingabe
-------
YAML oder JSON, eine Liste von Kandidaten:

    kandidaten:
      - operator: "Deutsche Telekom"        # oder: thema: "ki"
        url: "https://www.telekom.com/..."
        type: rss                            # rss|json_api|newsroom|newsroom_js
        begruendung: "Investor-Relations-Feed ..."
        # optionale Collector-Felder, 1:1 wie in der Watchlist:
        item_selector: "..."
        link_template: "..."
        headers: {...}
        exclude_url_pattern: "..."
        timeout_seconds: 30
        allow_short_titles: true
        # optionale Ausnahmen, jeweils MIT Begruendungstext:
        ausnahme_frische: "IR-Seite, publiziert quartalsweise"
        ausnahme_domain: "Cision ist Telias offizieller Verbreitungsweg"

Aufruf
------
    python scripts/pruefe_quellenvorschlag.py kandidaten.yaml
    python scripts/pruefe_quellenvorschlag.py kandidaten.yaml --json ergebnis.json
    python scripts/pruefe_quellenvorschlag.py --url https://... --type rss \
        --operator "Orange"

Exit-Code 0, wenn ALLE Kandidaten bestanden haben, sonst 1.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telco_radar.collect import collect_source  # noqa: E402
from telco_radar.config import Source, load_config  # noqa: E402
from telco_radar.models import normalize_url  # noqa: E402

# --------------------------------------------------------------------------- #
# Schwellen aus AUFTRAG_QUELLEN_AUSBAU.md Abschnitt 4. Bewusst hier als
# Konstanten und nicht als CLI-Schalter: wer sie senken will, soll das im Diff
# begruenden muessen.
# --------------------------------------------------------------------------- #
MIN_ITEMS = 5           # Kriterium 2
MIN_DATED_SHARE = 0.80  # Kriterium 3
MIN_FRESH = 1           # Kriterium 4
MAX_NAV_SHARE = 0.20    # Kriterium 5: Anteil verdaechtiger "Titel"
# Kriterium 5, zweite Haelfte: Anteil VERSCHIEDENER Titel. Gemessen am
# SEC-EDGAR-Feed von AT&T, der technisch sauber 40 datierte Meldungen liefert -
# alle mit dem Titel "8-K - Current report". Formal Ueberschriften, inhaltlich
# Formularbezeichnungen: der Analyst kann daraus nichts machen und im Bericht
# stuenden 40 identische Zeilen. Die Navigationslabel-Regel greift dort nicht,
# weil so ein Titel weder kurz noch ein Menuepunkt ist.
MIN_DISTINCT_SHARE = 0.60
# Kriterium 7: ab diesem Anteil gemeinsamer Meldungs-URLs gilt eine Quelle als
# derselbe Inhalt unter anderem Pfad - also als Dublette, nicht als zweite Quelle.
MAX_ITEM_OVERLAP = 0.70

# Verbreitungsdienste, die als Fremddomain ausdruecklich erlaubt sind
# (Kriterium 6) - sie sind der offizielle Kanal des Unternehmens, nicht
# Presse-ueber-das-Unternehmen. Trotzdem gehoert die Begruendung ins YAML.
ERLAUBTE_FREMDDOMAINS = {
    "cision.com", "news.cision.com", "businesswire.com", "globenewswire.com",
    "mfn.se", "prnewswire.com", "rns-pdf.londonstockexchange.com",
    "londonstockexchange.com", "otp.tools.investis.com", "investis.com",
    "q4cdn.com", "sec.gov",
}

# Kriterium 5: Navigationslabels, Rubrikenzeilen, Cookie-Banner. Ein "Titel",
# der komplett so aussieht, ist keine Ueberschrift.
_NAV_WORTE = re.compile(
    r"^(mehr( erfahren| anzeigen| lesen)?|weiterlesen|read more|learn more|more"
    r"|news|newsroom|press|presse|pressemitteilungen|media|medien|kontakt"
    r"|contact|impressum|imprint|datenschutz|privacy|cookies?|cookie[- ]?"
    r"(hinweis|banner|einstellungen|settings)|alle anzeigen|show all|view all"
    r"|see all|alle meldungen|archiv|archive|home|startseite|zur ?ueck|back"
    r"|next|weiter|previous|vor|suche|search|login|anmelden|registrieren"
    r"|newsletter|rss|sitemap|karriere|careers|jobs|ueber uns|about( us)?"
    r"|investor relations|investoren|downloads?|mediathek|bilder|videos?"
    r"|teilen|share|drucken|print|pdf|top|nach oben|akzeptieren|accept"
    r"|zustimmen|ablehnen|reject|einstellungen|settings|details)\.?$",
    re.IGNORECASE)
# Reine Datumszeilen ("12.03.2026", "March 12, 2026", "2026-03-12")
_NUR_DATUM = re.compile(
    r"^\W*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2}"
    r"|(jan|feb|m(a|ä)r|apr|ma(i|y)|jun|jul|aug|sep|o(k|c)t|nov|de(z|c))"
    r"[a-zä-ü]*\.?\s+\d{1,2},?\s*\d{0,4}"
    r"|\d{1,2}\.?\s+(jan|feb|m(a|ä)r|apr|ma(i|y)|jun|jul|aug|sep|o(k|c)t|nov|de(z|c))"
    r"[a-zä-ü]*\.?\s*\d{0,4})\W*$",
    re.IGNORECASE)


def _registrable(host: str) -> str:
    """Grobe eTLD+1-Naeherung ohne externe Abhaengigkeit.

    Reicht hier: verglichen wird nur, ob eine Kandidaten-URL auf derselben
    Unternehmensdomain liegt wie die eingetragene Website. Mehrteilige
    Endungen (co.uk, com.br, com.au ...) werden beruecksichtigt, alles
    Weitere braucht dieser Vergleich nicht.
    """
    host = (host or "").lower().strip().removeprefix("www.")
    teile = host.split(".")
    if len(teile) < 3:
        return host
    zweiteilige_endungen = {
        "co", "com", "net", "org", "gov", "edu", "ac", "or", "ne", "go", "in",
    }
    if teile[-2] in zweiteilige_endungen and len(teile[-1]) == 2:
        return ".".join(teile[-3:])
    return ".".join(teile[-2:])


def _host(url: str) -> str:
    return urlsplit(url or "").netloc.lower().removeprefix("www.")


def _ist_navigationslabel(titel: str) -> bool:
    t = " ".join((titel or "").split())
    if not t:
        return True
    if _NAV_WORTE.match(t):
        return True
    if _NUR_DATUM.match(t):
        return True
    # Sehr kurz UND wenige Woerter: typisch fuer Menuepunkte. Der Collector
    # laesst so etwas nur mit allow_short_titles durch - genau dort muss der
    # Check also nochmal hinschauen.
    if len(t) < 25 and len(t.split()) <= 3:
        return True
    return False


@dataclass
class Kandidat:
    url: str
    type: str = "newsroom"
    operator: str = ""
    thema: str = ""
    name: str = ""             # Anzeigename einer Themenquelle ("OpenAI")
    label: str = ""
    begruendung: str = ""
    website: str = ""          # erwartete Unternehmensdomain (Kriterium 6)
    item_selector: str | None = None
    link_template: str | None = None
    headers: dict | None = None
    exclude_url_pattern: str | None = None
    timeout_seconds: float | None = None
    allow_short_titles: bool = False
    ausnahme_frische: str = ""
    ausnahme_domain: str = ""
    # Rein beschreibende Felder. Sie beeinflussen die Pruefung nicht, werden
    # aber mit ins Ergebnis geschrieben, damit aus der bestandenen Liste ohne
    # zweiten Durchgang ein Watchlist-Eintrag werden kann.
    kanal: str = ""            # IR | Technik-Blog | Landesgesellschaft | Produkt
    neuer_betreiber: bool = False
    country: str = ""
    region: str = ""
    aliases: list[str] = field(default_factory=list)

    @property
    def bezeichnung(self) -> str:
        return (self.operator or self.name or self.label or self.thema
                or _host(self.url))

    def als_source(self) -> Source:
        return Source(
            type=self.type,
            url=self.url,
            name=self.bezeichnung,
            item_selector=self.item_selector,
            kind=self.type,
            label=self.label,
            link_template=self.link_template,
            headers=self.headers,
            exclude_url_pattern=self.exclude_url_pattern,
            timeout_seconds=self.timeout_seconds,
            allow_short_titles=self.allow_short_titles,
        )


@dataclass
class Befund:
    kandidat: Kandidat
    bestanden: bool = False
    kriterien: list[dict] = field(default_factory=list)
    n_items: int = 0
    n_datiert: int = 0
    n_frisch: int = 0
    neuestes: str = ""
    titelprobe: list[str] = field(default_factory=list)
    fehler: str = ""

    def pruefe(self, nummer: int, name: str, ok: bool, detail: str = "") -> bool:
        self.kriterien.append({"nr": nummer, "name": name,
                               "ok": bool(ok), "detail": detail})
        return bool(ok)

    @property
    def durchgefallen(self) -> list[str]:
        return [f"K{k['nr']} {k['name']}: {k['detail']}"
                for k in self.kriterien if not k["ok"]]

    def as_dict(self) -> dict:
        return {
            "bezeichnung": self.kandidat.bezeichnung,
            "url": self.kandidat.url,
            "type": self.kandidat.type,
            "operator": self.kandidat.operator,
            "thema": self.kandidat.thema,
            "kanal": self.kandidat.kanal,
            "neuer_betreiber": self.kandidat.neuer_betreiber,
            "country": self.kandidat.country,
            "region": self.kandidat.region,
            "website": self.kandidat.website,
            "aliases": self.kandidat.aliases,
            "item_selector": self.kandidat.item_selector,
            "link_template": self.kandidat.link_template,
            "headers": self.kandidat.headers,
            "exclude_url_pattern": self.kandidat.exclude_url_pattern,
            "timeout_seconds": self.kandidat.timeout_seconds,
            "allow_short_titles": self.kandidat.allow_short_titles,
            "ausnahme_frische": self.kandidat.ausnahme_frische,
            "ausnahme_domain": self.kandidat.ausnahme_domain,
            "begruendung": self.kandidat.begruendung,
            "bestanden": self.bestanden,
            "n_items": self.n_items,
            "n_datiert": self.n_datiert,
            "n_frisch": self.n_frisch,
            "neuestes": self.neuestes,
            "titelprobe": self.titelprobe,
            "kriterien": self.kriterien,
            "fehler": self.fehler,
        }


# --------------------------------------------------------------------------- #
# Bestand: alles, was schon konfiguriert ist. Gegen diesen Index laeuft die
# Dublettenpruefung (Kriterium 7).
# --------------------------------------------------------------------------- #
class Bestand:
    def __init__(self, root: Path):
        self.root = root
        self.nach_url: dict[str, str] = {}      # normalisierte URL -> Beschreibung
        self.je_operator: dict[str, list[Source]] = {}
        try:
            cfg = load_config(root)
        except Exception:  # noqa: BLE001 - der Check soll auch ohne Config laufen
            self.http_cfg: dict = {}
            return
        self.http_cfg = cfg.settings.get("http", {}) or {}
        self.lookback = int(cfg.settings.get("lookback_days", 8))
        for op in cfg.operators:
            for src in op.sources:
                self.nach_url[normalize_url(src.url)] = f"{op.name} ({src.kind})"
                if src.crawlable:
                    self.je_operator.setdefault(op.name, []).append(src)
        for src in cfg.news_sources:
            self.nach_url[normalize_url(src.url)] = f"Fachpresse {src.name}"
        # Themenquellen liegen in einer eigenen Datei (siehe tech_sources.yaml);
        # sie zaehlen fuer die Dublettenpruefung genauso.
        tech = self.root / "config" / "tech_sources.yaml"
        if tech.exists():
            roh = yaml.safe_load(tech.read_text(encoding="utf-8")) or {}
            for thema in (roh.get("themen") or {}).values():
                for eintrag in (thema.get("quellen") or []):
                    if eintrag.get("url"):
                        self.nach_url[normalize_url(eintrag["url"])] = \
                            f"Themenquelle {eintrag.get('name', '')}"

    def kennt(self, url: str) -> str:
        return self.nach_url.get(normalize_url(url), "")


def _pruefe_einen(kand: Kandidat, bestand: Bestand, lookback: int,
                  ueberlappung_pruefen: bool) -> Befund:
    b = Befund(kandidat=kand)
    http_cfg = bestand.http_cfg

    # --- Kriterium 8 zuerst: newsroom_js ist in der Sandbox nicht pruefbar,
    # also auch nicht abnehmbar. Kein Abruf noetig.
    if kand.type == "newsroom_js":
        b.pruefe(8, "kein newsroom_js", False,
                 "newsroom_js ist ohne Netz-Chromium nicht pruefbar und damit "
                 "nicht abnehmbar - erst den statischen Endpunkt suchen "
                 "(__NEXT_DATA__, /wp-json/wp/v2/posts, ?format=feed, /api/...)")
        b.bestanden = False
        return b
    b.pruefe(8, "kein newsroom_js", True, kand.type)

    # --- Kriterium 7a: exakte Dublette gegen den Bestand (URL-normalisiert)
    treffer = bestand.kennt(kand.url)
    if not b.pruefe(7, "keine Dublette", not treffer,
                    f"URL ist bereits konfiguriert: {treffer}" if treffer
                    else "URL neu"):
        b.bestanden = False
        return b

    # --- Kriterium 6: eigene Domain
    kand_host = _host(kand.url)
    kand_dom = _registrable(kand_host)
    erwartet = _registrable(_host(kand.website or ""))
    if not erwartet:
        # Ohne hinterlegte Unternehmenswebsite (Themenquellen) kann nur gegen
        # bekannte Verbreitungsdienste geprueft werden.
        domain_ok = kand_dom not in ERLAUBTE_FREMDDOMAINS or bool(kand.ausnahme_domain)
        detail = (f"{kand_dom} (keine Vergleichs-Website hinterlegt)"
                  if domain_ok else
                  f"{kand_dom} ist ein Verbreitungsdienst - ausnahme_domain fehlt")
    elif kand_dom == erwartet:
        domain_ok, detail = True, kand_dom
    elif kand_dom in ERLAUBTE_FREMDDOMAINS or kand_host in ERLAUBTE_FREMDDOMAINS:
        domain_ok = bool(kand.ausnahme_domain)
        detail = (f"{kand_dom} (erlaubter Verbreitungsdienst): "
                  f"{kand.ausnahme_domain}" if domain_ok else
                  f"{kand_dom} ist ein erlaubter Verbreitungsdienst, aber "
                  f"ausnahme_domain (Kommentar fuers YAML) fehlt")
    else:
        domain_ok = bool(kand.ausnahme_domain)
        detail = (f"{kand_dom} statt {erwartet}: {kand.ausnahme_domain}"
                  if domain_ok else
                  f"{kand_dom} gehoert nicht zu {erwartet} und ist kein "
                  f"erlaubter Verbreitungsdienst")
    b.pruefe(6, "eigene Domain", domain_ok, detail)

    # --- Kriterium 1: Abruf ueber den echten Projekt-Collector
    region = "global" if kand.thema else "europe"
    origin = "tech_watch" if kand.thema else "operator"
    try:
        items = collect_source(kand.als_source(), region,
                               kand.operator or None, origin, http_cfg)
    except Exception as exc:  # noqa: BLE001
        b.fehler = f"{type(exc).__name__}: {str(exc)[:200]}"
        b.pruefe(1, "Abruf ueber collect_source", False, b.fehler)
        b.bestanden = False
        return b
    b.pruefe(1, "Abruf ueber collect_source", True,
             f"{len(items)} Meldungen")

    b.n_items = len(items)
    datiert = [i for i in items if i.published]
    b.n_datiert = len(datiert)
    if datiert:
        b.neuestes = max(i.published for i in datiert).date().isoformat()
    b.n_frisch = sum(1 for i in items
                     if i.age_days() is not None and -1 <= i.age_days() <= lookback)
    b.titelprobe = [i.title for i in items[:3]]

    # --- Kriterium 2: genug Meldungen
    b.pruefe(2, f">= {MIN_ITEMS} Meldungen", len(items) >= MIN_ITEMS,
             f"{len(items)} Meldungen")

    # --- Kriterium 3: Datumsanteil
    anteil = (len(datiert) / len(items)) if items else 0.0
    b.pruefe(3, f">= {MIN_DATED_SHARE:.0%} datiert",
             anteil >= MIN_DATED_SHARE,
             f"{len(datiert)}/{len(items)} = {anteil:.0%}"
             + ("" if anteil >= MIN_DATED_SHARE else
                " - undatierte Meldungen sortieren ans Ende und sind faktisch "
                "unsichtbar"))

    # --- Kriterium 4: Frische ODER belegte Ausnahme
    frisch_ok = b.n_frisch >= MIN_FRESH or bool(kand.ausnahme_frische)
    b.pruefe(4, f">= {MIN_FRESH} im {lookback}-Tage-Fenster", frisch_ok,
             f"{b.n_frisch} frisch, neuestes {b.neuestes or '-'}"
             + (f" | Ausnahme: {kand.ausnahme_frische}"
                if b.n_frisch < MIN_FRESH and kand.ausnahme_frische else ""))

    # --- Kriterium 5: echte Ueberschriften
    verdaechtig = [i.title for i in items if _ist_navigationslabel(i.title)]
    nav_anteil = (len(verdaechtig) / len(items)) if items else 1.0
    b.pruefe(5, "echte Ueberschriften", nav_anteil <= MAX_NAV_SHARE,
             f"{len(verdaechtig)}/{len(items)} verdaechtig ({nav_anteil:.0%})"
             + (f", z. B. {verdaechtig[:3]}" if verdaechtig else ""))

    # --- Kriterium 5b: Titel muessen sich unterscheiden
    verschieden = len({" ".join(i.title.lower().split()) for i in items})
    anteil_verschieden = (verschieden / len(items)) if items else 0.0
    b.pruefe(5, "unterscheidbare Titel",
             anteil_verschieden >= MIN_DISTINCT_SHARE,
             f"{verschieden}/{len(items)} verschieden "
             f"({anteil_verschieden:.0%})"
             + ("" if anteil_verschieden >= MIN_DISTINCT_SHARE else
                " - die Quelle liefert Formularbezeichnungen oder Rubriken "
                "statt Ueberschriften; im Bericht stuenden identische Zeilen"))

    # --- Kriterium 7b: Inhaltsdublette gegen die bestehenden Quellen desselben
    # Betreibers. Zwei Pfade derselben Seite sind EINE Quelle.
    if ueberlappung_pruefen and kand.operator and items:
        eigene = {normalize_url(i.url) for i in items}
        schlimmste = 0.0
        wer = ""
        for src in bestand.je_operator.get(kand.operator, []):
            try:
                andere = {normalize_url(i.url) for i in collect_source(
                    src, region, kand.operator, "operator", http_cfg)}
            except Exception:  # noqa: BLE001
                continue
            if not andere:
                continue
            ueberlappung = len(eigene & andere) / len(eigene)
            if ueberlappung > schlimmste:
                schlimmste, wer = ueberlappung, src.url
        b.pruefe(7, "keine Inhaltsdublette", schlimmste <= MAX_ITEM_OVERLAP,
                 f"{schlimmste:.0%} gemeinsame Meldungen"
                 + (f" mit {wer}" if wer else " (keine Vergleichsquelle)"))

    b.bestanden = all(k["ok"] for k in b.kriterien)
    return b


def lade_kandidaten(pfad: Path, root: Path) -> list[Kandidat]:
    roh = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    if isinstance(roh, list):
        eintraege = roh
    else:
        eintraege = roh.get("kandidaten") or roh.get("candidates") or []

    # Betreiber-Websites aus der Watchlist nachschlagen, damit der
    # Domain-Check (Kriterium 6) auch dann greift, wenn der Vorschlag nur den
    # Betreibernamen nennt.
    websites: dict[str, str] = {}
    try:
        cfg = load_config(root)
        websites = {op.name: op.website for op in cfg.operators}
    except Exception:  # noqa: BLE001
        pass

    out: list[Kandidat] = []
    for e in eintraege:
        felder = {k: v for k, v in e.items()
                  if k in Kandidat.__dataclass_fields__}
        k = Kandidat(**felder)
        if not k.website and k.operator:
            k.website = websites.get(k.operator, "")
        out.append(k)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Prueft Quellenvorschlaege maschinell gegen die "
                    "Abnahmekriterien (AUFTRAG_QUELLEN_AUSBAU.md, Abschnitt 4)")
    p.add_argument("datei", nargs="?", type=Path,
                   help="YAML/JSON mit einer Liste von Kandidaten")
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--url", help="Einzelner Kandidat statt einer Datei")
    p.add_argument("--type", default="newsroom")
    p.add_argument("--operator", default="")
    p.add_argument("--thema", default="")
    p.add_argument("--item-selector", default=None)
    p.add_argument("--lookback", type=int, default=None)
    p.add_argument("--json", type=Path, help="Ergebnis als JSON schreiben")
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--no-overlap", action="store_true",
                   help="Inhaltsdubletten-Pruefung (Kriterium 7b) ueberspringen "
                        "- spart Abrufe, uebersieht aber zwei Pfade derselben Seite")
    p.add_argument("--nur-bestanden", action="store_true",
                   help="Nur die bestandenen Kandidaten ausgeben")
    args = p.parse_args(argv)

    root = args.root.resolve()
    bestand = Bestand(root)
    lookback = args.lookback or getattr(bestand, "lookback", 8)

    if args.url:
        kandidaten = [Kandidat(url=args.url, type=args.type,
                               operator=args.operator, thema=args.thema,
                               item_selector=args.item_selector)]
        if kandidaten[0].operator:
            try:
                cfg = load_config(root)
                kandidaten[0].website = next(
                    (op.website for op in cfg.operators
                     if op.name == kandidaten[0].operator), "")
            except Exception:  # noqa: BLE001
                pass
    elif args.datei:
        kandidaten = lade_kandidaten(args.datei, root)
    else:
        p.error("Entweder eine Kandidatendatei oder --url angeben")

    befunde: list[Befund] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futs = {pool.submit(_pruefe_einen, k, bestand, lookback,
                            not args.no_overlap): k for k in kandidaten}
        for fut in as_completed(futs):
            befunde.append(fut.result())

    reihenfolge = {k.url: n for n, k in enumerate(kandidaten)}
    befunde.sort(key=lambda b: reihenfolge.get(b.kandidat.url, 0))

    bestanden = [b for b in befunde if b.bestanden]
    print(f"{'ERGEBNIS':9} {'ITEMS':>5} {'DAT':>4} {'FRISCH':>6} {'NEUESTES':>11}  "
          f"{'BEZEICHNUNG':28} URL")
    print("-" * 140)
    for b in befunde:
        if args.nur_bestanden and not b.bestanden:
            continue
        status = "PASS" if b.bestanden else "FAIL"
        print(f"{status:9} {b.n_items:>5} {b.n_datiert:>4} {b.n_frisch:>6} "
              f"{b.neuestes or '-':>11}  {b.kandidat.bezeichnung[:28]:28} "
              f"{b.kandidat.url}")
        if not b.bestanden:
            for grund in b.durchgefallen:
                print(f"          -> {grund}")
        for t in b.titelprobe:
            print(f"          | {t[:110]}")
    print("-" * 140)
    print(f"{len(bestanden)}/{len(befunde)} bestanden")

    if args.json:
        args.json.write_text(
            json.dumps([b.as_dict() for b in befunde],
                       ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Ergebnis geschrieben: {args.json}")

    return 0 if len(bestanden) == len(befunde) else 1


if __name__ == "__main__":
    raise SystemExit(main())
