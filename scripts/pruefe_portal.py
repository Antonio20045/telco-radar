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
  8. Die Promo Uebersicht zeigt >= 10 verschiedene echte Bilder, keines
     davon leer, und jede Karte oben traegt entweder ein Bild oder eine
     Schriftkachel - nie einen leeren Kasten.

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
# Abnahmekriterium der Promo Uebersicht: mindestens 10 verschiedene echte
# Bilder. Die Zahl stammt vom 07.08.2026, als 15 Screenshots vorlagen und
# genau EINER auf der Seite ankam - und der war leer. Seit dem Umbau sind es
# keine Screenshots mehr, sondern die Kampagnenmotive der Aktionsseiten
# (promo_bilder.py); die Schwelle bleibt, weil sie dasselbe misst: kommt das,
# was beschafft wurde, auch auf der Seite an?
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
        themenseiten = [f"thema/{p.name}"
                        for p in sorted((site / "thema").glob("*.html"))]
        for name in ("index.html", "meldungen.html", "promo/index.html",
                     *themenseiten):
            seite.goto((site / name).resolve().as_uri())
            seite.wait_for_timeout(600)
            # Erst durchscrollen: die Bilder tragen loading="lazy", und was
            # nie geladen wurde, hat naturalWidth 0 und faellt aus der
            # Messung. Ohne diese Schleife prueft Kriterium 6 genau die
            # Bilder NICHT, die weit unten stehen - auf der Promo Uebersicht
            # ist das die Mehrheit.
            hoehe = seite.evaluate("document.body.scrollHeight")
            for y in range(0, hoehe, _FALZ // 2):
                seite.evaluate(f"window.scrollTo(0,{y})")
                seite.wait_for_timeout(70)
            seite.evaluate("window.scrollTo(0,0)")
            seite.wait_for_timeout(300)
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
    # Die Ressortzahl steht seit dem 08.08.2026 EINMAL je Kachel, im Link in
    # die Tiefe ("alle 29 Meldungen"). Vorher stand sie zusaetzlich als Chip
    # neben der Rubrik - dieselbe Zahl zweimal in einer Kachel.
    summe = sum(int(m.group())
                for x in meldungen.select(".rkachel .rkachel-alle")
                if (m := re.search(r"\d+", x.get_text(" ", strip=True))))
    gerendert = len(meldungen.select(".mressort .meldung"))
    b.prueft(len(ressorts) >= 3 and stufen and summe == len(hs)
             and gerendert == len(hs),
             f"4. Meldungsseite: {len(ressorts)} Ressorts, "
             f"Ressortzahlen {summe}, gerendert {gerendert}, Daten {len(hs)}")

    # ---- Kriterium 5: keine abgeschnittene Schlagzeile
    # Seit dem 08.08.2026 auch auf der Wettbewerbsseite: ihre Chronik zieht
    # Ueberschriften aus zwei Quellen (Meldung und Analysten-Move), und die
    # zweite hat keinen Rueckfall, falls ein Feed gekuerzt liefert.
    # Seit dem 08.08.2026 auch auf den temporaeren Themenseiten: sie ziehen
    # ihre Ueberschriften aus dem Themenspeicher, also aus Meldungen, die
    # mehrere Wochen alt sein koennen - genau dort verschwindet ein Feld
    # unbemerkt.
    # Seit dem 08.08.2026 auch auf der Differenzierungs-Seite: ihre Karten
    # ziehen die Hauptzeile aus zwei Speichern, und der Presse-Zweig liefert
    # rohe Zusammenfassungen - genau dort entsteht ein halber Satz.
    seiten = [index, meldungen]
    for weitere in [site / "wettbewerb.html", site / "differenzierung.html",
                    *sorted((site / "thema").glob("*.html"))]:
        if weitere.exists():
            seiten.append(BeautifulSoup(weitere.read_text(encoding="utf-8"),
                                        "html.parser"))
    abgeschnitten = [t for soup in seiten
                     for t in _schlagzeilen(soup) if t.endswith("…")]
    alle = sum(len(_schlagzeilen(soup)) for soup in seiten)
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
                 f"8b. Leere Bilder ausgeliefert: {len(leer)}"
                 + (f" ({', '.join(leer)})" if leer else ""))
        # 8c: kein leerer Bildkasten. Bis zum 08.08.2026 hiess das "jede
        # Karte traegt ein Motiv" - damals zeigte die Seite oben je Marke
        # genau eine Karte, und die hatte immer eins. Seit dem Markenraster
        # steht jede Aktion als Karte da, und eine kleine ohne belegtes Bild
        # ist eine reine TEXTkarte: das ist die Absicht, kein Mangel (ein
        # Kasten je Zeile waere genau das Rauschen, das der Umbau beseitigt).
        # Geprueft wird deshalb die Sache selbst - (a) die staerkste Aktion
        # jeder Marke traegt ein Motiv, (b) nirgends steht ein Bildkasten
        # ohne Inhalt.
        gross = promo.select(".promo-karten .pkarte--gross")
        ohne_motiv = [k for k in gross if not k.select_one(".pk-bild")]
        leere_kaesten = [kasten for kasten in promo.select(".pk-bild")
                         if not kasten.select_one("img")
                         and "pk-bild--typo" not in (kasten.get("class") or [])]
        b.prueft(bool(gross) and not ohne_motiv and not leere_kaesten,
                 f"8c. Grosse Karten ohne Motiv: {len(ohne_motiv)} von "
                 f"{len(gross)}, leere Bildkaesten: {len(leere_kaesten)}")

    _browser_messungen(site, b)

    print()
    return b.ausgeben()


if __name__ == "__main__":
    raise SystemExit(main())
