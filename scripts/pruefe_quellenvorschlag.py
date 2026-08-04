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

Massenbetrieb (Kriterium 10)
----------------------------
Bei 1000 Kandidaten muss der Check drei Dinge koennen, die er bei zwoelf
nicht brauchte:

  * **Wiederaufnahme nach Abbruch.** Jedes Ergebnis wird sofort in den Cache
    geschrieben (`--cache`, Standard `outputs/pruef_cache.json`). Ein zweiter
    Aufruf ueberspringt, was schon geprueft ist - inklusive der
    Collector-Felder im Schluessel, damit ein geaenderter `item_selector`
    wirklich neu geprueft wird.
  * **Dublettenpruefung gegen einen Index** statt gegen Live-Abrufe. Der
    Index wird EINMAL aufgebaut (alle bestehenden Quellen, host-gedrosselt)
    und dann fuer alle Kandidaten benutzt. Vorher kostete jeder Kandidat so
    viele Abrufe, wie sein Betreiber Quellen hat.
  * **Host-Drosselung.** Die Kandidaten laufen ueber denselben Sammelplan wie
    die Pipeline: je Host nacheinander, mit Mindestabstand. Bei 1000
    Kandidaten liegen zwangslaeufig viele auf derselben Domain, und ein
    429-Sturm sieht im Protokoll aus wie 20 tote Quellen.

Exit-Code 0, wenn ALLE Kandidaten bestanden haben, sonst 1.
"""
from __future__ import annotations

import argparse
import json
import hashlib
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telco_radar.collect import collect_source, sammelplan  # noqa: E402
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
    item_urls: list[str] = field(default_factory=list)
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
            "item_urls": self.item_urls,
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
        self.item_index: dict[str, str] = {}    # Meldungs-URL -> Quelle
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

    # ----------------------------------------------------------- Inhaltsindex
    def index_aufbauen(self, cache: Path | None = None,
                       max_alter_stunden: float = 24.0,
                       workers: int = 24) -> dict[str, str]:
        """Meldungs-URL -> Quelle, ueber ALLE bestehenden Quellen.

        Ersetzt die Live-Abrufe der Inhaltsdubletten-Pruefung. Vorher kostete
        jeder Kandidat so viele zusaetzliche Abrufe, wie sein Betreiber
        Quellen hat - bei 1000 Kandidaten waeren das Tausende. Jetzt wird der
        Index einmal gebaut, auf Platte gelegt und wiederverwendet.

        Der Index deckt zudem mehr ab als vorher: die alte Pruefung sah nur
        Quellen DESSELBEN Betreibers, uebersah also denselben Inhalt unter
        einem anderen Betreibernamen (Landesgesellschaft, Konzernmutter).
        """
        if cache and cache.exists():
            try:
                roh = json.loads(cache.read_text(encoding="utf-8"))
                alter = (time.time() - float(roh.get("gebaut_um", 0))) / 3600
                if alter <= max_alter_stunden:
                    self.item_index = dict(roh.get("index") or {})
                    print(f"Inhaltsindex aus {cache} ({len(self.item_index)} "
                          f"Meldungen, {alter:.1f} h alt)", file=sys.stderr)
                    return self.item_index
            except (json.JSONDecodeError, OSError, TypeError, ValueError):
                pass

        quellen = [(src, name) for name, srcs in self.je_operator.items()
                   for src in srcs]
        index: dict[str, str] = {}
        sperre = threading.Lock()

        def _gruppe(gruppe):
            for n, (src, name) in enumerate(gruppe):
                if n:
                    time.sleep(1.0)
                try:
                    items = collect_source(src, "europe", name, "operator",
                                           self.http_cfg)
                except Exception:  # noqa: BLE001 - eine tote Quelle ist kein Fehler
                    continue
                with sperre:
                    for i in items:
                        index.setdefault(normalize_url(i.url),
                                         f"{name} ({src.url})")

        gruppen = sammelplan([(s, n) for s, n in quellen], 1,
                             url_von=lambda j: j[0].url)
        print(f"Inhaltsindex wird gebaut: {len(quellen)} Quellen in "
              f"{len(gruppen)} Host-Gruppen ...", file=sys.stderr)
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            list(pool.map(_gruppe, gruppen))
        self.item_index = index
        print(f"Inhaltsindex: {len(index)} Meldungen", file=sys.stderr)
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(
                {"gebaut_um": time.time(), "index": index},
                ensure_ascii=False), encoding="utf-8")
        return index


def _pruefe_einen(kand: Kandidat, bestand: Bestand, lookback: int,
                  ueberlappung_pruefen: bool, zweimal: bool = False) -> Befund:
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

    # --- Kriterium 1b: derselbe Abruf ein zweites Mal.
    # Am 04.08.2026 teuer gelernt: newswire.ca lieferte im Einzelabruf 23 von
    # 23 Meldungen SAUBER DATIERT und beim naechsten Abruf 30 Meldungen ganz
    # OHNE Datum - dasselbe Kartenlayout, einmal mit und einmal ohne
    # Zeitstempel. Eine undatierte Meldung sortiert ans Ende und wird faktisch
    # nie bewertet; eine Quelle, die das bei jedem zweiten Abruf tut, ist
    # unbrauchbar, besteht aber jeden Check, der nur einmal hinsieht.
    # Nur fuer geparste Seiten sinnvoll - ein RSS-Feed hat das Problem nicht -,
    # und nur auf Wunsch, weil es jeden Abruf verdoppelt.
    if zweimal and kand.type in ("newsroom", "json_api"):
        try:
            zweite = collect_source(kand.als_source(), region,
                                    kand.operator or None, origin, http_cfg)
        except Exception as exc:  # noqa: BLE001
            zweite = []
            b.fehler = f"2. Abruf: {type(exc).__name__}: {str(exc)[:120]}"
        d1 = sum(1 for i in items if i.published)
        d2 = sum(1 for i in zweite if i.published)
        a1 = d1 / len(items) if items else 0.0
        a2 = d2 / len(zweite) if zweite else 0.0
        stabil = (len(zweite) >= MIN_ITEMS
                  and abs(a1 - a2) <= 0.2
                  and a2 >= MIN_DATED_SHARE)
        b.pruefe(1, "zweiter Abruf stabil", stabil,
                 f"1. Abruf {len(items)} Meldungen/{a1:.0%} datiert, "
                 f"2. Abruf {len(zweite)} Meldungen/{a2:.0%} datiert"
                 + ("" if stabil else " - die Seite antwortet wechselhaft"))

    b.n_items = len(items)
    # Die Meldungs-URLs mitnehmen: erst damit lassen sich die Kandidaten am
    # Ende auch GEGENEINANDER auf Dubletten pruefen. Ohne das bestehen zwei
    # Pfade derselben Seite beide - im Lauf vom 04.08.2026 waren das 4 von 15
    # Treffern (Turkcell /rss und /rss.xml, MTN mit und ohne _embed, ...).
    b.item_urls = sorted({normalize_url(i.url) for i in items})[:80]
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

    # --- Kriterium 7b: Inhaltsdublette. Zwei Pfade derselben Seite sind EINE
    # Quelle. Geprueft wird gegen den einmal aufgebauten Inhaltsindex des
    # Bestands - bei 1000 Kandidaten waeren Live-Abrufe je Kandidat Tausende
    # zusaetzliche Anfragen, und der Index sieht ausserdem mehr: nicht nur die
    # Quellen desselben Betreibers, sondern alle.
    if ueberlappung_pruefen and items and bestand.item_index:
        eigene = {normalize_url(i.url) for i in items}
        treffer = [bestand.item_index[u] for u in eigene
                   if u in bestand.item_index]
        ueberlappung = len(treffer) / len(eigene)
        haeufigste = max(set(treffer), key=treffer.count) if treffer else ""
        b.pruefe(7, "keine Inhaltsdublette", ueberlappung <= MAX_ITEM_OVERLAP,
                 f"{ueberlappung:.0%} der Meldungen stehen schon im Bestand"
                 + (f", ueberwiegend aus {haeufigste}" if haeufigste else ""))

    b.bestanden = all(k["ok"] for k in b.kriterien)
    return b


def cache_schluessel(k: Kandidat) -> str:
    """Alles, was das Ergebnis beeinflusst - und nichts sonst.

    Die Collector-Felder gehoeren dazu: ein Vorschlag, der beim zweiten
    Anlauf einen `item_selector` bekommt, ist ein anderer Vorschlag und darf
    nicht aus dem Cache beantwortet werden.
    """
    roh = json.dumps([
        normalize_url(k.url), k.type, k.item_selector, k.link_template,
        k.headers, k.exclude_url_pattern, k.allow_short_titles,
        bool(k.ausnahme_frische), bool(k.ausnahme_domain), k.operator, k.thema,
    ], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(roh.encode("utf-8")).hexdigest()[:16]


class Ergebniscache:
    """Wiederaufnahme nach Abbruch (Kriterium 10).

    Geschrieben wird nach JEDEM Kandidaten, nicht am Ende: ein Lauf ueber
    1000 Kandidaten dauert lang genug, dass er unterwegs abbricht, und ein
    Cache, der das nicht ueberlebt, ist keiner.
    """

    def __init__(self, pfad: Path | None):
        self.pfad = pfad
        self.eintraege: dict[str, dict] = {}
        self._sperre = threading.Lock()
        if pfad and pfad.exists():
            try:
                self.eintraege = json.loads(pfad.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                print(f"Cache {pfad} unlesbar - er wird neu aufgebaut",
                      file=sys.stderr)

    def hole(self, k: Kandidat) -> dict | None:
        return self.eintraege.get(cache_schluessel(k))

    def merke(self, k: Kandidat, ergebnis: dict) -> None:
        if not self.pfad:
            return
        with self._sperre:
            self.eintraege[cache_schluessel(k)] = ergebnis
            self.pfad.parent.mkdir(parents=True, exist_ok=True)
            self.pfad.write_text(
                json.dumps(self.eintraege, ensure_ascii=False), encoding="utf-8")


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
    p.add_argument("--workers", type=int, default=24,
                   help="gleichzeitig bearbeitete HOST-Gruppen")
    p.add_argument("--no-overlap", action="store_true",
                   help="Inhaltsdubletten-Pruefung (Kriterium 7b) ueberspringen "
                        "- spart den Indexaufbau, uebersieht aber zwei Pfade "
                        "derselben Seite")
    p.add_argument("--einmal", action="store_true",
                   help="den zweiten Abruf geparster Seiten weglassen. "
                        "Kriterium 11 macht ihn zur Pflicht - das hier ist "
                        "nur fuer schnelle Zwischenstaende gedacht")
    p.add_argument("--cache", type=Path,
                   default=Path("outputs/pruef_cache.json"),
                   help="Ergebnis-Cache fuer Wiederaufnahme nach Abbruch")
    p.add_argument("--ohne-cache", action="store_true",
                   help="Cache weder lesen noch schreiben")
    p.add_argument("--erneut", action="store_true",
                   help="alles neu pruefen, Cache trotzdem fortschreiben")
    p.add_argument("--index-cache", type=Path,
                   default=Path("outputs/inhaltsindex.json"))
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

    # Inhaltsindex EINMAL - nicht je Kandidat.
    if not args.no_overlap:
        bestand.index_aufbauen(cache=args.index_cache, workers=args.workers)

    cache = Ergebniscache(None if args.ohne_cache else args.cache)
    aus_cache: list[dict] = []
    offen: list[Kandidat] = []
    for k in kandidaten:
        alt = None if args.erneut else cache.hole(k)
        if alt is not None:
            aus_cache.append(alt)
        else:
            offen.append(k)
    if aus_cache:
        print(f"{len(aus_cache)} von {len(kandidaten)} Kandidaten aus dem "
              f"Cache ({args.cache}) - {len(offen)} offen", file=sys.stderr)

    befunde: list[Befund] = []
    ergebnisse: list[dict] = list(aus_cache)

    def _gruppe(gruppe: list[Kandidat]) -> list[Befund]:
        raus: list[Befund] = []
        for n, k in enumerate(gruppe):
            if n:
                time.sleep(1.0)   # Mindestabstand je Host, wie in der Pipeline
            b = _pruefe_einen(k, bestand, lookback, not args.no_overlap,
                              not args.einmal)
            cache.merke(k, b.as_dict())
            raus.append(b)
        return raus

    if offen:
        gruppen = sammelplan([(k,) for k in offen], 1,
                             url_von=lambda j: j[0].url)
        gruppen = [[j[0] for j in g] for g in gruppen]
        print(f"{len(offen)} Kandidaten in {len(gruppen)} Host-Gruppen, "
              f"{args.workers} gleichzeitig", file=sys.stderr)
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            for fut in as_completed([pool.submit(_gruppe, g) for g in gruppen]):
                befunde.extend(fut.result())
        ergebnisse.extend(b.as_dict() for b in befunde)

    reihenfolge = {normalize_url(k.url): n for n, k in enumerate(kandidaten)}
    ergebnisse.sort(key=lambda e: reihenfolge.get(normalize_url(e["url"]), 0))

    # --- Kriterium 7c: die Kandidaten GEGENEINANDER.
    # Der Check vergleicht jeden Vorschlag mit dem Bestand - aber zwei
    # Vorschlaege, die dieselbe Seite unter zwei Pfaden treffen, bestehen
    # beide. Bei 101 mechanisch gefundenen Kandidaten waren das 4 von 15
    # Treffern (Turkcell /rss und /rss.xml, MTN mit und ohne _embed).
    # Laeuft NACH dem Cache, weil das Ergebnis von der ganzen Liste abhaengt.
    angenommen: list[tuple[str, set]] = []
    for e in ergebnisse:
        if not e.get("bestanden"):
            continue
        eigene = set(e.get("item_urls") or [])
        if not eigene:
            angenommen.append((e["url"], eigene))
            continue
        for andere_url, andere in angenommen:
            ueberlappung = len(eigene & andere) / len(eigene)
            if ueberlappung > MAX_ITEM_OVERLAP:
                e["bestanden"] = False
                e.setdefault("kriterien", []).append({
                    "nr": 7, "name": "keine Dublette unter den Kandidaten",
                    "ok": False,
                    "detail": f"{ueberlappung:.0%} gemeinsame Meldungen mit "
                              f"{andere_url} - dieselbe Seite unter zwei "
                              f"Pfaden ist EINE Quelle"})
                break
        else:
            angenommen.append((e["url"], eigene))

    bestanden = [e for e in ergebnisse if e.get("bestanden")]
    print(f"{'ERGEBNIS':9} {'ITEMS':>5} {'DAT':>4} {'FRISCH':>6} {'NEUESTES':>11}  "
          f"{'BEZEICHNUNG':28} URL")
    print("-" * 140)
    for e in ergebnisse:
        if args.nur_bestanden and not e.get("bestanden"):
            continue
        status = "PASS" if e.get("bestanden") else "FAIL"
        print(f"{status:9} {e.get('n_items', 0):>5} {e.get('n_datiert', 0):>4} "
              f"{e.get('n_frisch', 0):>6} {e.get('neuestes') or '-':>11}  "
              f"{str(e.get('bezeichnung', ''))[:28]:28} {e.get('url', '')}")
        if not e.get("bestanden"):
            for k in e.get("kriterien") or []:
                if not k.get("ok"):
                    print(f"          -> K{k['nr']} {k['name']}: {k['detail']}")
        for t in e.get("titelprobe") or []:
            print(f"          | {t[:110]}")
    print("-" * 140)
    print(f"{len(bestanden)}/{len(ergebnisse)} bestanden")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(ergebnisse, ensure_ascii=False, indent=1),
            encoding="utf-8")
        print(f"Ergebnis geschrieben: {args.json}")

    return 0 if len(bestanden) == len(ergebnisse) else 1


if __name__ == "__main__":
    raise SystemExit(main())
