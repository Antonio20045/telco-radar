#!/usr/bin/env python3
"""Abnahme-Check fuer vorgeschlagene Promo-Seiten - maschinell, nicht behauptet.

Das Gegenstueck zu scripts/pruefe_quellenvorschlag.py, aber fuer die andere
Quellenart: dort Presse-Feeds mit datierten Meldungen, hier Endkunden-
Aktionsseiten ohne jedes Datum (siehe collect/promo_snapshot.py). Die
Kriterien muessen deshalb andere sein - "wie viele Meldungen im
Frischefenster" hat auf einer Aktionsseite keine Bedeutung.

Warum es dieses Skript gibt
---------------------------
Dieselbe Lehre wie im Presse-Zweig: ein Modell, das "ich habe die Seite
angesehen, da laufen Aktionen" sagt, zaehlt nicht. Der Fehler ist hier sogar
billiger zu machen, weil fast jede Anbieterseite irgendwo das Wort "Angebot"
traegt. Eine Seite taugt als Promo-Quelle nur, wenn sie
  (a) ueber GENAU den Pfad der Pipeline abrufbar ist
      (collect.promo_snapshot.fetch_snapshot),
  (b) genug sichtbaren Text hat, damit der Extraktor ueberhaupt etwas sieht,
  (c) konkrete Angebotssignale traegt (Preise, Datenvolumen, Mechanik-Woerter)
      statt reiner Markenprosa,
  (d) Mobilfunk zeigt und nicht Festnetz/Glasfaser (bewusst nicht beobachtet,
      siehe config/promo_sources.yaml),
  (e) auf der Domain der Marke selbst liegt (kein Vergleichsportal - die
      Quellen-Unterseite sagt genau das zu),
  (f) nicht schon konfiguriert ist, und vor allem
  (g) etwas ANDERES zeigt als die bereits konfigurierten Seiten dieser Marke.

(g) ist das Kriterium, um das es hier eigentlich geht. Der Sinn mehrerer
Seiten je Marke ist Abdeckung, nicht Zahl. Eine zweite URL, die denselben
Text liefert wie die erste (/angebote und /angebote/ mit
Weiterleitung, oder eine Sprachvariante), kostet einen LLM-Aufruf je Lauf und
bringt kein einziges zusaetzliches Angebot. Genau dieser Fehler ist in
Session 5 im Presse-Zweig passiert: 15 von 34 "bestandenen" Kandidaten waren
URL-Varianten bereits konfigurierter Quellen. Der Ueberlappungswert rechnet
deshalb gegen die KLEINERE der beiden Wortmengen - eine Seite, die eine
bestehende vollstaendig ENTHAELT, sieht sonst neu aus.

Eingabe
-------
YAML/JSON mit einer Liste von Kandidaten:

    kandidaten:
      - marke: "congstar"                  # muss in config/promo_sources.yaml stehen
        url: "https://www.congstar.de/aktionen/"
        kind: static                        # static|js
        label: "Aktionen"                   # optional, reine Anzeige
        begruendung: "..."                  # optional, reine Doku

Aufruf
------
    python scripts/pruefe_promo_seite.py kandidaten.yaml
    python scripts/pruefe_promo_seite.py kandidaten.yaml --json ergebnis.json
    python scripts/pruefe_promo_seite.py --url https://... --marke congstar
    python scripts/pruefe_promo_seite.py kandidaten.yaml --zweimal

`--zweimal` ruft jede Seite ein zweites Mal ab und verlangt, dass sie beim
zweiten Mal wieder Text und Angebotssignale liefert. Die Lehre stammt aus dem
Presse-Zweig (newswire.ca lieferte einmal 23 datierte Meldungen und beim
naechsten Abruf 30 undatierte) und gilt hier genauso: eine Aktionsseite, die
mal mit und mal ohne gerendertem Inhalt antwortet, ist unbrauchbar, weil ein
leerer Abruf alle ihre Angebote in Richtung "ausgelaufen" schiebt.

Exit-Code 0, wenn ALLE Kandidaten bestanden haben, sonst 1.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from telco_radar.collect.promo_snapshot import fetch_snapshot  # noqa: E402
from telco_radar.config import load_config  # noqa: E402
from telco_radar.promo_config import _normalize_url, load_promo_config  # noqa: E402

# --------------------------------------------------------------- Schwellen
# Sichtbarer Text, ab dem eine Seite dem Extraktor ueberhaupt etwas bietet.
# Gemessen an den 15 Bestandsseiten: die kleinste lieferte rund 1400 Zeichen,
# eine reine Weiterleitungs-/Zustimmungsseite liegt bei unter 300. 500 liegt
# sicher dazwischen und faellt nicht ueber eine schlanke Kampagnen-Landingpage.
MIN_TEXT = 500
# Zahl VERSCHIEDENER Angebotssignale (nicht Treffer - sonst gewinnt eine Seite
# schon dadurch, dass sie das Wort "Angebot" vierzigmal im Menue fuehrt).
MIN_SIGNALE = 4
# Ab hier gilt eine Kandidatenseite als dieselbe wie eine bereits
# konfigurierte. 0.6 ist dieselbe Schwelle wie bei promo_store._same_offer,
# aus demselben Grund gewaehlt: gemessene Umformulierungen derselben Sache
# lagen darueber, unabhaengige Inhalte deutlich darunter.
MAX_UEBERLAPPUNG = 0.6
# Unterhalb dieser Wortzahl ist der Ueberlappungswert Rauschen - zwei kurze
# Seiten teilen sich zwangslaeufig fast nur Allerweltswoerter. Dann gilt der
# Vergleich als NICHT durchfuehrbar, und das ist ein Durchfaller, kein PASS
# (Lehre aus Session 5: "nicht pruefbar" ist kein Bestehen).
MIN_WOERTER_VERGLEICH = 60

# Signale eines konkreten Endkundenangebots. Bewusst grob und deutschsprachig:
# der Check soll Markenprosa und Rechtstexte aussortieren, nicht die Qualitaet
# des Angebots beurteilen - die bleibt Handarbeit, genau wie im Presse-Zweig.
SIGNALE: dict[str, str] = {
    "preis": r"\d+[,.]\d{2}\s*(?:€|eur\b)|\b\d+\s*(?:€|eur)\b",
    "monatlich": r"\bmonatlich|\bpro monat\b|\bmtl\.|\b/\s*monat\b",
    "datenvolumen": r"\b\d+\s*gb\b",
    "rabatt": r"\brabatt|\bstatt\s*\d|\bspar|\breduziert|\b\d{1,2}\s*%",
    "gratis": r"\bgratis\b|\bkostenlos\b|\bgeschenkt\b|\bohne aufpreis\b|\b0\s*€",
    "bonus": r"\bbonus\b|\bstartguthaben\b|\bguthaben\b|\bpr[äa]mie\b|\bcashback\b",
    "aktion": r"\baktion(?:en|spreis|szeitraum)?\b|\bdeal\b|\bkampagne\b|\bangebot\b",
    "frist": r"\bnur bis\b|\bbis zum\s+\d|\bbefristet\b|\bsolange der vorrat\b|"
             r"\bendet am\b|\baktionszeitraum\b",
    "wechsel": r"\bwechsel|\brufnummernmitnahme\b|\bportier|\bneukund",
    "tarif": r"\btarif|\ballnet\s*flat\b|\bflat\b|\bvertrag\b",
}

# Mobilfunk gegen Festnetz. Nicht als Verbot einzelner Woerter - eine
# Mobilfunkseite darf DSL erwaehnen -, sondern als Uebergewicht: eine Seite,
# auf der die Festnetzwoerter dominieren, ist eine Festnetzseite.
MOBIL_WOERTER = (r"\bmobilfunk|\bhandy|\bsmartphone|\bsim\b|\besim\b|\btarif|"
                 r"\ballnet|\blte\b|\b5g\b|\bprepaid|\bmobil(?:es|em)?\s+internet")
FEST_WOERTER = (r"\bdsl\b|\bglasfaser|\bkabel(?:anschluss|internet)?\b|"
                r"\bfestnetz|\bmagentazuhause|\bhomespot|\brouter\b|\bfritz!?box|"
                r"\bfiber\b|\binternet f[üu]r zuhause|\bhausanschluss")

_WORT_RE = re.compile(r"[a-zäöüß0-9]{4,}", re.I)
# Allerweltswoerter, die auf JEDER deutschen Anbieterseite stehen. Sie wuerden
# den Ueberlappungswert kuenstlich hochziehen und zwei voellig verschiedene
# Seiten derselben Marke als Dublette erscheinen lassen.
_STOPP = {
    "auch", "aber", "alle", "allen", "aller", "dass", "dein", "deine", "deinen",
    "deiner", "dich", "diese", "diesem", "diesen", "dieser", "dieses", "durch",
    "eine", "einem", "einen", "einer", "eines", "sich", "sind", "über", "oder",
    "ohne", "nach", "noch", "nicht", "mehr", "kann", "können", "wenn", "wird",
    "werden", "hier", "haben", "unter", "unsere", "unseren", "unserer", "beim",
    "jetzt", "mit", "cookies", "datenschutz", "impressum", "agb", "startseite",
    "weitere", "informationen", "seite", "menü", "suche", "anmelden", "login",
    "kundencenter", "service", "hilfe", "kontakt", "warenkorb",
}


def _registrable(host: str) -> str:
    """Grobe Registrierdomain: die letzten zwei Labels, bei bekannten
    zweistufigen Endungen die letzten drei. Reicht fuer den Zweck hier
    (deutscher Mobilfunkmarkt, fast durchgaengig .de) und spart eine
    Abhaengigkeit auf tldextract."""
    teile = (host or "").lower().strip(".").split(".")
    if len(teile) <= 2:
        return ".".join(teile)
    zweistufig = {"co.uk", "com.de", "co.at"}
    if ".".join(teile[-2:]) in zweistufig and len(teile) >= 3:
        return ".".join(teile[-3:])
    return ".".join(teile[-2:])


def _woerter(text: str) -> set[str]:
    return {w.lower() for w in _WORT_RE.findall(text or "")} - _STOPP


def ueberlappung(text_a: str, text_b: str) -> float:
    """Wortueberlappung zweier Seiten, gerechnet gegen die KLEINERE Menge.

    Gegen die Vereinigung oder gegen die Kandidatenmenge gerechnet sieht eine
    Seite, die eine bestehende vollstaendig enthaelt, faelschlich neu aus -
    genau der Fehler aus Session 5 (siehe CLAUDE.md, Abnahme-Check). Gibt
    -1.0 zurueck, wenn eine der beiden Seiten zu duenn fuer einen sinnvollen
    Vergleich ist; der Aufrufer wertet das als "nicht pruefbar".
    """
    a, b = _woerter(text_a), _woerter(text_b)
    if len(a) < MIN_WOERTER_VERGLEICH or len(b) < MIN_WOERTER_VERGLEICH:
        return -1.0
    return len(a & b) / min(len(a), len(b))


_PREIS_RE = re.compile(r"\b(\d{1,3}(?:[,.]\d{2})?)\s*(?:€|eur\b)", re.I)
_GB_RE = re.compile(r"\b(\d{1,3})\s*gb\b", re.I)


def angebotsbreite(text: str) -> tuple[int, int]:
    """(verschiedene Preise, verschiedene Datenvolumen) im Text.

    Der Messwert, der eine Aktions-/Uebersichtsseite von einer einzelnen
    Produktseite trennt. Eine Seite wie /prepaid/tarife/prepaid-allnet-m
    beschreibt EINEN Tarif und nennt entsprechend ein bis zwei Preise; eine
    Aktionsuebersicht nennt ein Dutzend. Der Unterschied ist wichtig, weil
    Einzeltarifseiten die Promo-Datenbank mit fast gleichlautenden Eintraegen
    fluten wuerden - genau das, wogegen promo_analyst._MAX_ENTRIES_PER_PAGE
    und die Prompt-Anweisung "keine SKU-Liste" gebaut sind.
    """
    return (len(set(_PREIS_RE.findall(text or ""))),
            len(set(_GB_RE.findall(text or ""))))


def signale(text: str) -> list[str]:
    """Welche Angebotssignale traegt der Text - je Signal hoechstens einmal
    gezaehlt."""
    low = (text or "").lower()
    return [name for name, muster in SIGNALE.items()
            if re.search(muster, low, re.I)]


def mobilfunk_uebergewicht(text: str) -> tuple[int, int]:
    low = (text or "").lower()
    return (len(re.findall(MOBIL_WOERTER, low, re.I)),
            len(re.findall(FEST_WOERTER, low, re.I)))


def _pruefungen(kandidat: dict, snap: dict, snap2: dict | None,
                bestand: dict) -> list[dict]:
    """Die eigentliche Kriterienliste. Getrennt vom Abruf, damit die Tests sie
    ohne Netz durchspielen koennen."""
    text = snap.get("text") or ""
    links = snap.get("links") or []
    bilder = snap.get("images") or []
    url = kandidat["url"]
    aus: list[dict] = []

    def kriterium(nr, name, ok, detail):
        aus.append({"nr": nr, "name": name, "ok": bool(ok), "detail": detail})

    kriterium(1, "abrufbar", bool(text.strip()),
              f"{len(text)} Zeichen sichtbarer Text")
    kriterium(2, "genug Text", len(text) >= MIN_TEXT,
              f"{len(text)} >= {MIN_TEXT} Zeichen")

    gefunden = signale(text)
    kriterium(3, "Angebotssignale", len(gefunden) >= MIN_SIGNALE,
              f"{len(gefunden)}/{len(SIGNALE)}: {', '.join(gefunden) or 'keine'}")

    mobil, fest = mobilfunk_uebergewicht(text)
    kriterium(4, "Mobilfunk statt Festnetz", mobil > fest,
              f"{mobil} Mobilfunk- vs. {fest} Festnetz-Treffer")

    marken_host = _registrable(urlsplit(bestand.get("leitseite", "")).netloc)
    kand_host = _registrable(urlsplit(url).netloc)
    kriterium(5, "eigene Domain der Marke",
              bool(marken_host) and kand_host == marken_host,
              f"{kand_host or '?'} gegen {marken_host or '?'}")

    schon_da = _normalize_url(url) in bestand.get("konfiguriert", set())
    kriterium(6, "noch nicht konfiguriert", not schon_da,
              "steht bereits in config/promo_sources.yaml" if schon_da else "neu")

    # 7: gegen JEDE bestehende Seite dieser Marke UND gegen jeden bereits
    # angenommenen Kandidaten derselben Marke - der schlechteste Wert zaehlt.
    # Der zweite Teil ist der wichtigere: der Sucher liefert regelmaessig
    # Geschwisterseiten (prepaid-allnet-s/m/l/xl), die sich vom BESTAND
    # unterscheiden, untereinander aber dasselbe Geruest zeigen. Ohne diesen
    # Vergleich bestuenden alle vier - und die Rubrik haette vier Quellen fuer
    # eine Information.
    vergleiche = dict(bestand.get("seiten") or {})
    vergleiche.update(bestand.get("angenommen") or {})
    if not vergleiche:
        # Unterscheidung, die den Unterschied macht: eine Marke, die noch gar
        # keine Seite hat, ist ein legitimer Erstfall. Eine Marke, deren
        # konfigurierte Seiten sich nur gerade nicht ABRUFEN liessen, ist es
        # nicht - dann ist der Vergleich nicht durchgefuehrt worden, und das
        # gilt hier als Durchfaller. "Nicht pruefbar" ist kein PASS.
        unerreichbar = bestand.get("unerreichbar") or []
        if unerreichbar:
            kriterium(7, "eigenstaendig", False,
                      f"{len(unerreichbar)} konfigurierte Seite(n) dieser Marke "
                      f"nicht abrufbar - Vergleich nicht durchfuehrbar")
        else:
            kriterium(7, "eigenstaendig", True,
                      "keine Vergleichsseite konfiguriert - erste Seite dieser Marke")
    else:
        werte = {u: ueberlappung(text, t) for u, t in vergleiche.items()}
        nicht_pruefbar = [u for u, w in werte.items() if w < 0]
        hoechste = max((w for w in werte.values() if w >= 0), default=None)
        if hoechste is None:
            kriterium(7, "eigenstaendig", False,
                      "kein Vergleich moeglich (Seiten zu duenn) - gilt als "
                      "Durchfaller, nicht als bestanden")
        else:
            schlimmste = max((u for u, w in werte.items() if w >= 0),
                             key=lambda u: werte[u])
            detail = f"max. {hoechste:.2f} gegen {schlimmste} (Grenze {MAX_UEBERLAPPUNG})"
            if nicht_pruefbar:
                detail += f"; {len(nicht_pruefbar)} Seite(n) zu duenn zum Vergleich"
            kriterium(7, "eigenstaendig", hoechste < MAX_UEBERLAPPUNG, detail)

    if snap2 is not None:
        text2 = snap2.get("text") or ""
        gefunden2 = signale(text2)
        kriterium(8, "zweimal stabil",
                  len(text2) >= MIN_TEXT and len(gefunden2) >= MIN_SIGNALE,
                  f"2. Abruf: {len(text2)} Zeichen, {len(gefunden2)} Signale")

    return aus


def hole_kandidat(kandidat: dict, http_cfg: dict, zweimal: bool = False,
                  fetch=fetch_snapshot) -> dict:
    """Nur der Abruf - getrennt von der Bewertung, weil der Abruf nebenlaeufig
    laufen darf, die Bewertung aber nicht: Kriterium 7 vergleicht jeden
    Kandidaten auch gegen die bereits ANGENOMMENEN derselben Marke und haengt
    damit an einer festen Reihenfolge."""
    url, kind = kandidat["url"], kandidat.get("kind", "static")
    aus: dict = {"kandidat": kandidat}
    try:
        aus["snap"] = fetch(url, kind, http_cfg)
    except Exception as exc:  # noqa: BLE001
        aus["fehler"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        return aus
    if zweimal:
        try:
            aus["snap2"] = fetch(url, kind, http_cfg)
        except Exception as exc:  # noqa: BLE001
            aus["snap2"] = {"text": "",
                            "fehler": f"{type(exc).__name__}: {str(exc)[:120]}"}
    return aus


def bewerte_kandidat(geholt: dict, bestand: dict) -> dict:
    """Einen abgerufenen Kandidaten durch alle Kriterien schicken. Wirft nie -
    ein fehlgeschlagener Abruf ist ein Durchfaller mit Begruendung, kein
    Absturz."""
    kandidat = geholt["kandidat"]
    ergebnis = {"marke": kandidat.get("marke", ""), "url": kandidat["url"],
                "kind": kandidat.get("kind", "static"),
                "label": kandidat.get("label", ""),
                "begruendung": kandidat.get("begruendung", "")}
    if "snap" not in geholt:
        ergebnis["pass"] = False
        ergebnis["kriterien"] = [{"nr": 1, "name": "abrufbar", "ok": False,
                                  "detail": geholt.get("fehler", "unbekannt")}]
        return ergebnis
    snap = geholt["snap"]
    kriterien = _pruefungen(kandidat, snap, geholt.get("snap2"), bestand)
    text = snap.get("text") or ""
    preise, gb = angebotsbreite(text)
    ergebnis["kriterien"] = kriterien
    ergebnis["pass"] = all(k["ok"] for k in kriterien)
    ergebnis["zeichen"] = len(text)
    ergebnis["links"] = len(snap.get("links") or [])
    ergebnis["bilder"] = len(snap.get("images") or [])
    # Kennzahlen, KEINE Kriterien. Am 08.08.2026 gemessen: die 15 damals
    # konfigurierten Bestandsseiten streuten von 0 bis 16 verschiedenen
    # Preisen - eine Schwelle daraus haette Seiten aussortiert, die genauso
    # aussehen wie die, die schon drin sind (JS-Seiten liefern ueber reines
    # HTTP weniger). Die Zahlen stehen deshalb als Entscheidungshilfe da,
    # nicht als Urteil: viele Preise = Uebersicht, ein Preis = Einzeltarif.
    ergebnis["preise"] = preise
    ergebnis["volumen"] = gb
    return ergebnis


def sammle_bestand(root: Path, http_cfg: dict, marken: set[str],
                   fetch=fetch_snapshot, statisch: bool = False) -> dict[str, dict]:
    """Fuer jede betroffene Marke: die schon konfigurierten Seiten samt ihrem
    aktuellen Text. Nur so kann Kriterium 7 die Kandidaten gegen den ECHTEN
    Bestand halten statt gegen eine Annahme.

    *statisch*: Bestandsseiten ebenfalls per reinem HTTP holen. Muss dieselbe
    Einstellung sein wie beim Abruf der Kandidaten - sonst waeren bei einer
    js-Marke in der Sandbox alle Bestandsseiten unerreichbar, Kriterium 7
    haette nichts zu vergleichen, und jeder Kandidat kaeme ungeprueft durch.
    """
    promo_cfg = load_promo_config(root)
    alle_urls = {_normalize_url(p.url) for s in promo_cfg.sources for p in s.pages}
    aus: dict[str, dict] = {}
    for src in promo_cfg.sources:
        if marken and src.name not in marken:
            continue
        seiten: dict[str, str] = {}
        unerreichbar: list[str] = []
        for page in src.crawled_pages:
            try:
                text = fetch(page.url, "static" if statisch else page.kind,
                             http_cfg).get("text") or ""
            except Exception as exc:  # noqa: BLE001
                print(f"  ! Bestandsseite nicht abrufbar ({src.name} / "
                      f"{page.url}): {type(exc).__name__}", file=sys.stderr)
                unerreichbar.append(page.url)
                continue
            if text.strip():
                seiten[page.url] = text
            else:
                unerreichbar.append(page.url)
        aus[src.name] = {"leitseite": src.url, "seiten": seiten,
                         "unerreichbar": unerreichbar, "konfiguriert": alle_urls}
    return aus


def _lade_kandidaten(pfad: Path) -> list[dict]:
    roh = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    if isinstance(roh, list):
        return [k for k in roh if isinstance(k, dict) and k.get("url")]
    return [k for k in (roh.get("kandidaten") or [])
            if isinstance(k, dict) and k.get("url")]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("datei", type=Path, nargs="?")
    p.add_argument("--url")
    p.add_argument("--marke", default="")
    p.add_argument("--kind", default="static", choices=["static", "js"])
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--json", type=Path)
    p.add_argument("--zweimal", action="store_true")
    p.add_argument("--statisch", action="store_true",
                   help="jeden Kandidaten als kind=static abrufen, egal was "
                        "in der Eingabe steht")
    p.add_argument("--workers", type=int, default=4)
    args = p.parse_args()

    root = args.root.resolve()
    if args.url:
        kandidaten = [{"marke": args.marke, "url": args.url, "kind": args.kind}]
    elif args.datei:
        kandidaten = _lade_kandidaten(args.datei)
    else:
        p.error("Entweder eine Kandidatendatei oder --url angeben.")
        return 2

    if args.statisch:
        # Zwei Gruende, das zu tun, und beide stehen in CLAUDE.md:
        # (1) In der Sandbox kommt Chromium nicht ins Netz - `kind: js` ist
        #     hier grundsaetzlich nicht pruefbar, und ein ungeprueftes PASS
        #     gibt es nicht.
        # (2) Wichtiger: "In Session 2 waren 6 von 8 angeblich JS-toten
        #     Quellen in Wahrheit statisch abrufbar." Eine Seite, die ueber
        #     reines HTTP genug Text liefert, GEHOERT als static konfiguriert
        #     - das spart je Lauf einen Chromium-Start und macht sie
        #     ueberhaupt erst lokal nachpruefbar.
        for k in kandidaten:
            k["kind"] = "static"
    http_cfg = load_config(root).settings.get("http", {})
    marken = {k.get("marke", "") for k in kandidaten if k.get("marke")}
    print(f"Bestand einlesen ({len(marken)} Marke(n)) ...")
    bestand_je_marke = sammle_bestand(root, http_cfg, marken,
                                      statisch=args.statisch)

    print(f"{len(kandidaten)} Kandidaten abrufen ...")
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        geholt = list(pool.map(
            lambda k: hole_kandidat(k, http_cfg, zweimal=args.zweimal),
            kandidaten))

    # Bewertung SEQUENTIELL, in Eingabereihenfolge (der Sucher liefert nach
    # Punkten sortiert, der beste Kandidat einer Marke steht also vorn). Nur
    # so kann ein angenommener Kandidat den naechsten derselben Marke als
    # Dublette entlarven.
    leer = {"leitseite": "", "seiten": {}, "konfiguriert": set()}
    angenommen: dict[str, dict[str, str]] = {}
    ergebnisse: list[dict] = []
    for g in geholt:
        marke = g["kandidat"].get("marke", "")
        bestand = dict(bestand_je_marke.get(marke, leer))
        bestand["angenommen"] = angenommen.get(marke, {})
        e = bewerte_kandidat(g, bestand)
        if e["pass"]:
            angenommen.setdefault(marke, {})[e["url"]] = g["snap"].get("text") or ""
        ergebnisse.append(e)

    bestanden = [e for e in ergebnisse if e["pass"]]
    for e in sorted(ergebnisse, key=lambda e: (not e["pass"], e["marke"])):
        kopf = "PASS" if e["pass"] else "FAIL"
        print(f"\n[{kopf}] {e['marke'] or '(ohne Marke)'} - {e['url']}")
        for k in e["kriterien"]:
            zeichen = "+" if k["ok"] else "-"
            print(f"   {zeichen} {k['nr']}. {k['name']}: {k['detail']}")
        if e["pass"]:
            print(f"     {e.get('links', 0)} Link-, {e.get('bilder', 0)} "
                  f"Bildkandidaten | {e.get('preise', 0)} verschiedene Preise, "
                  f"{e.get('volumen', 0)} Datenvolumen")

    print(f"\n{len(bestanden)}/{len(ergebnisse)} bestanden.")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(ergebnisse, ensure_ascii=False, indent=1),
                             encoding="utf-8")
        print(f"Details: {args.json}")
    print("\nHinweis: Der Check prueft FORM, nicht WERT. Ob eine Seite wirklich "
          "Aktionen zeigt, die auf keiner anderen Seite dieser Marke stehen, "
          "entscheidet weiterhin ein Blick in den Text.")
    return 0 if len(bestanden) == len(ergebnisse) else 1


if __name__ == "__main__":
    raise SystemExit(main())
