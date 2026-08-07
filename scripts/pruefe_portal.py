#!/usr/bin/env python3
"""Abnahme des Portals - misst, statt zu behaupten.

Die Session, die dem Nachrichtenportal-Auftrag vorausging, ist an einem
Satz gescheitert: "Jetzt sind ueberall Bilder" - tatsaechlich hatten 31 von
193 Meldungen eins. Dieses Skript prueft gegen die WIRKLICH gerenderte
Seite:

  1. Oberhalb der Falz stehen bei 1440 px Breite >= 6 Geschichten.
  2. Mindestens 57 % der Meldungen haben ein Bild.
  3. Kein Bild im Aufmacher oder in der zweiten Reihe ist schmaler als 800 px.
  4. Die Meldungsseite ist nach Ressorts gruppiert und gewichtet.
  5. Keine Schlagzeile endet auf "…".
  6. Kein Bild wird hochskaliert dargestellt (Anzeigebreite > Dateibreite).

Dazu die zwei Kriterien aus AUFTRAG_PORTAL_WELLE2.md §7 (07.08.2026):

  7. Alle Ressorts der Meldungsseite sind ohne Scrollen sichtbar, und alle
     Meldungen sind weiterhin auf der Seite.
  8. Die Promo Uebersicht zeigt >= 10 verschiedene echte Bilder, und keines
     davon ist ein leerer Screenshot.

Kriterium 1, 6 und 7 brauchen einen echten Browser - Chromium liegt unter
/opt/pw-browsers. Ohne Browser laufen die uebrigen trotzdem durch.

    python scripts/pruefe_portal.py                 # rendert nach /tmp und prueft
    python scripts/pruefe_portal.py --site site     # prueft ein fertiges site/
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bs4 import BeautifulSoup                                    # noqa: E402

from telco_radar.report.bilder import (                          # noqa: E402
    MIND_BREITE_GROSS, ist_leer)

# Die Falz: was ein Leser bei 1440x900 ohne Scrollen sieht. 900 ist die
# konservative Annahme - ein 16:9-Notebook mit Browserleisten.
_FALZ = 900
_BREITE = 1440
_MIND_OBEN = 6
# Der Anteil bebilderter Meldungen. Bis zum 07.08.2026 stand hier die
# absolute Zahl 110, kalibriert an der Ausgabe vom 6.8. mit 193 Meldungen
# (= 57 %). Eine kleinere Ausgabe fiel damit durch, obwohl sich nichts
# verschlechtert hatte: die Ausgabe vom 7.8. hatte 107 von 138 mit Bild -
# also 77 %, deutlich BESSER, und trotzdem "durchgefallen". Gemessen wird
# jetzt die Quote, die das Kriterium immer gemeint hat.
_MIND_BILDQUOTE = 57
# Abnahmekriterium 4 des Auftrags vom 07.08.2026: von den 15 vorhandenen
# Screenshots muessen mindestens 10 auf der Promo Uebersicht ankommen. Vorher
# war es genau einer - und der war leer.
_MIND_PROMO_BILDER = 10
_CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


class Bilanz:
    def __init__(self) -> None:
        self.zeilen: list[tuple[bool | None, str]] = []

    def prueft(self, ok: bool | None, text: str) -> None:
        self.zeilen.append((ok, text))

    def ausgeben(self) -> int:
        breite = max(len(t) for _, t in self.zeilen)
        for ok, text in self.zeilen:
            marke = "BESTANDEN" if ok else ("--------- " if ok is None else "DURCHGEFALLEN")
            print(f"  {text.ljust(breite)}   {marke}")
        durchgefallen = sum(1 for ok, _ in self.zeilen if ok is False)
        offen = sum(1 for ok, _ in self.zeilen if ok is None)
        print(f"\n{len(self.zeilen) - durchgefallen - offen} bestanden, "
              f"{durchgefallen} durchgefallen, {offen} nicht pruefbar")
        return 1 if durchgefallen else 0


def _rendern(ziel: Path, root: Path) -> None:
    from telco_radar.config import load_config
    from telco_radar.report.html import render_site
    render_site(ziel, root / "data" / "reports", load_config(root))


def _schlagzeilen(soup: BeautifulSoup) -> list[str]:
    return [e.get_text(" ", strip=True) for e in soup.select(".szl")]


def _browser_messungen(site: Path, b: Bilanz) -> None:
    """Kriterium 1, 4 und 6 - alles, was eine echte Darstellung braucht."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        b.prueft(None, "Browser-Messungen (playwright fehlt)")
        return
    if not Path(_CHROMIUM).exists():
        treffer = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
        if not treffer:
            b.prueft(None, "Browser-Messungen (kein Chromium gefunden)")
            return
        pfad = treffer[-1]
    else:
        pfad = _CHROMIUM

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=pfad)
        seite = browser.new_page(viewport={"width": _BREITE, "height": _FALZ})

        seite.goto((site / "index.html").resolve().as_uri())
        seite.wait_for_timeout(400)
        oben = seite.evaluate(
            """(falz) => [...document.querySelectorAll('.szl')]
                 .filter(e => { const r = e.getBoundingClientRect();
                                return r.top < falz && r.bottom > 0 &&
                                       e.textContent.trim().length > 0; }).length""",
            _FALZ)
        b.prueft(oben >= _MIND_OBEN,
                 f"1. Oberhalb der Falz: {oben} Geschichten (>= {_MIND_OBEN})")

        # Kriterium 6 gilt fuer beide Seiten - ein hochskaliertes Bild ist
        # der sichtbarste Teil des Befunds vom 06.08.2026.
        schlimmster = 0
        wo = ""
        for name in ("index.html", "meldungen.html"):
            seite.goto((site / name).resolve().as_uri())
            seite.wait_for_timeout(600)
            for eintrag in seite.evaluate(
                """() => [...document.images]
                     .filter(i => i.naturalWidth > 0)
                     .map(i => ({dargestellt: Math.round(
                                   i.getBoundingClientRect().width *
                                   window.devicePixelRatio),
                                 datei: i.naturalWidth, src: i.currentSrc}))"""):
                if not eintrag["dargestellt"]:
                    continue
                ueber = eintrag["dargestellt"] - eintrag["datei"]
                if ueber > schlimmster:
                    schlimmster, wo = ueber, f"{name}: {eintrag['src'].split('/')[-1]}"
        b.prueft(schlimmster <= 0,
                 f"6. Groesste Hochskalierung: {schlimmster} px"
                 + (f" ({wo})" if schlimmster > 0 else ""))

        # ---- Kriterium 7: alle Ressorts ohne Scrollen
        # Bis zum 07.08.2026 stand hier "die erste Meldung beginnt vor der
        # Falz" - das war zu wenig. Die Seite war 12 249 px hoch, und wer
        # wissen wollte, was unter "Geld & Uebernahmen" steht, scrollte acht
        # Bildschirmhoehen. Gemessen wird jetzt die Oberkante der LETZTEN
        # Ressortkachel: liegt sie unter der Falz, sieht der Leser die ganze
        # Gliederung, ohne zu scrollen.
        seite.goto((site / "meldungen.html").resolve().as_uri())
        seite.wait_for_timeout(500)
        kacheln = seite.evaluate(
            """() => [...document.querySelectorAll('.rkachel')]
                 .map(e => Math.round(
                      e.getBoundingClientRect().top + window.scrollY))""")
        letzte = max(kacheln) if kacheln else -1
        b.prueft(bool(kacheln) and letzte < _FALZ,
                 f"7. Letztes Ressort beginnt bei {letzte} px "
                 f"({len(kacheln)} Ressorts, < {_FALZ})")
        browser.close()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", default=".", help="Projektwurzel")
    p.add_argument("--site", help="fertiges site/ pruefen statt neu zu rendern")
    args = p.parse_args()

    root = Path(args.root).resolve()
    if args.site:
        site = Path(args.site).resolve()
    else:
        site = Path("/tmp/pruefe_portal_site")
        _rendern(site, root)

    b = Bilanz()

    # ---- Kriterium 2: Bilder je Meldung (aus der Berichtsdatei)
    berichte = sorted(f for f in (root / "data" / "reports").glob("*.json")
                      if re.fullmatch(r"\d{4}-\d{2}-\d{2}", f.stem))
    bericht = json.loads(berichte[-1].read_text(encoding="utf-8"))
    hs = [h for r in (bericht.get("regions") or {}).values()
          for h in r.get("highlights") or []]
    mit_bild = [h for h in hs if h.get("image")]
    quote = 100 * len(mit_bild) // max(1, len(hs))
    b.prueft(quote >= _MIND_BILDQUOTE,
             f"2. Meldungen mit Bild: {len(mit_bild)} von {len(hs)} "
             f"({quote} %, >= {_MIND_BILDQUOTE} %)")
    ohne_mass = [h for h in mit_bild if not h.get("image_w")]
    b.prueft(not ohne_mass,
             f"2b. Bilder ohne gemessene Breite: {len(ohne_mass)}")

    index = BeautifulSoup((site / "index.html").read_text(encoding="utf-8"),
                          "html.parser")
    meldungen = BeautifulSoup((site / "meldungen.html").read_text(encoding="utf-8"),
                              "html.parser")

    # ---- Kriterium 3: keine kleinen Bilder in grossen Positionen
    gross = index.select(".aufmacher-bild img, .reihe-zwei .stueck-bild img")
    zu_klein = [img for img in gross if int(img.get("width") or 0) < MIND_BREITE_GROSS]
    b.prueft(bool(gross) and not zu_klein,
             f"3. Bilder in Aufmacher/zweiter Reihe: {len(gross)}, "
             f"davon unter {MIND_BREITE_GROSS} px: {len(zu_klein)}")

    # ---- Kriterium 4: Ressorts, Gewichtung, und keine verlorene Meldung
    ressorts = meldungen.select(".mressort")
    stufen = all(sec.select(".mlead") for sec in ressorts)
    summe = sum(int(x.get_text(strip=True))
                for x in meldungen.select(".rkachel .count-badge"))
    gerendert = len(meldungen.select(".mressort .meldung"))
    b.prueft(len(ressorts) >= 3 and stufen and summe == len(hs)
             and gerendert == len(hs),
             f"4. Meldungsseite: {len(ressorts)} Ressorts, "
             f"Ressortzahlen {summe}, gerendert {gerendert}, Daten {len(hs)}")

    # ---- Kriterium 5: keine abgeschnittene Schlagzeile
    abgeschnitten = [t for soup in (index, meldungen)
                     for t in _schlagzeilen(soup) if t.endswith("…")]
    alle = len(_schlagzeilen(index)) + len(_schlagzeilen(meldungen))
    b.prueft(not abgeschnitten,
             f"5. Schlagzeilen geprueft: {alle}, abgeschnitten: "
             f"{len(abgeschnitten)}")

    # ---- Kriterium 8: die Promo Uebersicht zeigt echte Bilder
    promo_datei = site / "promo" / "index.html"
    if not promo_datei.exists():
        b.prueft(None, "8. Promo Uebersicht (nicht gerendert)")
    else:
        promo = BeautifulSoup(promo_datei.read_text(encoding="utf-8"),
                              "html.parser")
        verweise = {img["src"] for img in promo.select("img[src]")
                    if "images/" in img["src"] and "logo" not in img["src"]}
        fehlend = [v for v in verweise
                   if not (site / "promo" / v).exists()]
        b.prueft(len(verweise) >= _MIND_PROMO_BILDER and not fehlend,
                 f"8. Promo Uebersicht: {len(verweise)} verschiedene Bilder "
                 f"(>= {_MIND_PROMO_BILDER}), {len(fehlend)} Verweise ins Leere")
        ordner = site / "promo" / "images"
        leer = [p.name for p in ordner.iterdir()
                if p.is_file() and ist_leer(p.read_bytes())] \
            if ordner.exists() else []
        b.prueft(not leer,
                 f"8b. Leere Screenshots ausgeliefert: {len(leer)}"
                 + (f" ({', '.join(leer)})" if leer else ""))

    _browser_messungen(site, b)

    print()
    return b.ausgeben()


if __name__ == "__main__":
    raise SystemExit(main())
