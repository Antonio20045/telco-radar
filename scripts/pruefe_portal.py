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
     davon leer, und JEDE Karte traegt entweder ein Bild oder eine
     Schriftkachel - nie einen leeren Kasten (seit 08.08.2026 alle Karten,
     vorher nur die grossen; siehe Kriterium 8c im Code).

Dazu die zwei Kriterien der Runde vom 08.08.2026 (Suche und Differenzierung):

  9. Die Differenzierungs-Seite zeigt echte Bilder, und JEDE Karte traegt ein
     Motiv (Bild oder Schriftkachel).
 10. Die Suchseite liefert zu einem echten Begriff Treffer, einen Verlauf und
     bebilderte Karten - gemessen im Browser, weil die Seite ihren Index per
     fetch() laedt.

Dazu das Kriterium des Geraeteradars (10.08.2026):

 11. Der Geraeteradar traegt seine Reiter: kein Diagramm auf der Startansicht,
     keine Reste der geloeschten Preisgrafik, jede Alarmzeile mit Quelllink,
     Abrufdatum und Aufklapper, und die vier Kacheln zaehlen dasselbe wie der
     Satz darunter. Sind noch keine Alarmzeilen erfasst, gilt das Kriterium
     als uebersprungen - die Seite steht dann unter ihrer
     Veroeffentlichungsschwelle.
     Seit E3 Schritt 3 (17.09.2026) steht die Alarmtabelle im Radar-Reiter
     von geraete.html (bis dahin eigene Seite wettbewerbsradar.html, heute
     eine Weiterleitung) - Kriterium 11 liest sie von der EINEN Seite, und
     11b misst deren ALLE Tafeln einschliesslich der Radar-Tafel. Jede Buendelzeile
     mit Zahl nennt „über H Monate“ (5.3); die Verbote der seit 30.08.2026
     geloeschten Positionskarte misst `tests/test_geraete_reiter_browser.py`.

Dazu das Kriterium der Umbenennung (11.08.2026):

 12. Der Zeitungskopf traegt auf 1440 UND auf 390 px den vollen Namen
     "Vodafone Product and Services Insights", steht vollstaendig im Bild,
     erzeugt keinen Seitwaertslauf und sitzt nicht weiter als 90 px aus der
     Mitte. Der laengere Name hat in seiner ersten Fassung alle drei Zahlen
     gerissen: 169 px aus der Mitte und 61 px aus dem Bild heraus.

Kriterium 1, 6, 7, 10 und 12 brauchen einen echten Browser - Chromium liegt
unter /opt/pw-browsers. Ohne Browser laufen die uebrigen trotzdem durch.

**Gemessen wird ueber einen lokalen HTTP-Server, nicht ueber file://.** Der Grund ist
Kriterium 10: `fetch('search_index.json')` ist unter file:// von der Same-Origin-Regel
gesperrt, die Suchseite bliebe leer, und die Pruefung wuerde einen Fehler messen, den es
in Wirklichkeit nicht gibt. Der Server bindet auf 127.0.0.1 und braucht kein Netz.

    python scripts/pruefe_portal.py                 # rendert nach /tmp und prueft
    python scripts/pruefe_portal.py --site site     # prueft ein fertiges site/
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bs4 import BeautifulSoup  # noqa: E402

from telco_radar.report.bilder import (  # noqa: E402
    MIND_BREITE_GROSS,
    ist_leer,
)

_FALZ = 900
_BREITE = 1440
_MIND_OBEN = 6
_MOBIL_BREITE = 390
_MARKE = "Vodafone Product and Services Insights"
_MAX_KOPF_VERSATZ = 90
_MIND_BILDQUOTE = 57
_MIND_PROMO_BILDER = 10
_MIND_DIFF_BILDQUOTE = 25
_MIND_DOSSIER_TREFFER = 5
_CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


class Bilanz:
    def __init__(self) -> None:
        self.zeilen: list[tuple[bool | None, str]] = []

    def prueft(self, ok: bool | None, text: str) -> None:
        self.zeilen.append((ok, text))

    def ausgeben(self) -> int:
        breite = max(len(t) for _, t in self.zeilen)
        for ok, text in self.zeilen:
            marke = (
                "BESTANDEN" if ok else ("--------- " if ok is None else "DURCHGEFALLEN")
            )
            print(f"  {text.ljust(breite)}   {marke}")
        durchgefallen = sum(1 for ok, _ in self.zeilen if ok is False)
        offen = sum(1 for ok, _ in self.zeilen if ok is None)
        print(
            f"\n{len(self.zeilen) - durchgefallen - offen} bestanden, "
            f"{durchgefallen} durchgefallen, {offen} nicht pruefbar"
        )
        return 1 if durchgefallen else 0


def zeitraum_maengel(tafel) -> list[str]:
    """11: jede Buendelzeile mit Zahl nennt „über H Monate“ (H: data-leitzahl)."""
    stumm = sum(
        f"über {z.get('data-leitzahl-monate')} Monate"
        not in " ".join(e.get_text(" ") for e in z.select(".gr-bnd-tco .gr-bnd-label"))
        for z in tafel.select(".gr-bnd[data-gesamt]:not([data-gesamt=''])")
    )
    return [f"{stumm} Bündelzeilen ohne 'über H Monate'"] if stumm else []


def _rendern(ziel: Path, root: Path) -> None:
    from telco_radar.config import load_config
    from telco_radar.report.html import render_site

    render_site(ziel, root / "data" / "reports", load_config(root))


def _schlagzeilen(soup: BeautifulSoup) -> list[str]:
    return [e.get_text(" ", strip=True) for e in soup.select(".szl")]


@contextmanager
def _server(site: Path):
    """Ein lokaler HTTP-Server ueber dem gerenderten `site/`.

    Ohne ihn misst Kriterium 10 einen Fehler, den es nicht gibt: die Suchseite
    laedt ihren Index per `fetch()`, und unter file:// verbietet die
    Same-Origin-Regel das. Bindet auf 127.0.0.1, braucht kein Netz.
    """
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port)],
        cwd=site,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(1.2)
        yield f"http://127.0.0.1:{port}"
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def _haeufigster_absender(site: Path) -> str:
    """Ein Begriff, der im Archiv nachweislich vorkommt - aus dem Index, nicht
    geraten. Ein fest verdrahteter Begriff waere ein Test, der eines Tages
    nur noch belegt, dass diese Firma nicht mehr vorkommt."""
    try:
        index = json.loads((site / "search_index.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    from collections import Counter

    zaehler = Counter(
        e.get("operator") or "" for e in index if e.get("kind") != "promo"
    )
    for name, _ in zaehler.most_common():
        erstes = name.split()[0] if name else ""
        if len(erstes) >= 4:
            return erstes
    return ""


_MAX_REITERHOEHE = 3000

_FLIESSTEXT_DECKEL = {
    "tafel-tco": 6000,
    "tafel-radar": 6000,
    "tafel-verlauf": 2500,
    "tafel-katalog": 2500,
}
_REITER_NAMEN = {
    "tafel-tco": "Vergleich",
    "tafel-radar": "Radar",
    "tafel-verlauf": "Preisverlauf",
    "tafel-katalog": "Katalog",
}
_MAX_ABSATZ_NACH_SVG = 200


def fliesstext_zeichen(tafel) -> int:
    """Fliessttext-Zeichen einer Tafel: alle <p> inklusive Aufklapp-Text.

    Nur <template>-Inhalte zaehen nicht - sie sind nie sichtbar, sondern
    werden per Klick zum DOM montiert (P1-Rechenwege). Whitespace wird
    auf ein Leerzeichen normalisiert, damit Einrueckungen im Quelltext
    die Zahl nicht aufblasen (design.md mass am 17.09. dieselbe Menge:
    18 388 Zeichen im Vergleichs-Reiter).
    """
    return sum(
        len(re.sub(r"\s+", " ", p.get_text(" ", strip=True)))
        for p in tafel.find_all("p")
        if p.get_text(strip=True) and p.find_parent("template") is None
    )


def _sichtbar_initial(el) -> bool:
    """Initialer Zustand ohne Nutzerklick: kein hidden-Attribut, kein
    zugeklapptes <details>, keine JS-Aufklappzeile (.gr-a-auf ohne
    --an), kein <template> - irgendwo in der Vorfahrenkette."""
    knoten = el
    while knoten is not None and getattr(knoten, "name", None):
        if knoten.name == "template" or knoten.has_attr("hidden"):
            return False
        if knoten.name == "details" and not knoten.has_attr("open"):
            return False
        klassen = set(knoten.get("class") or [])
        if "gr-a-auf" in klassen and "gr-a-auf--an" not in klassen:
            return False
        knoten = knoten.parent
    return True


def _vorheriges_element(el):
    """Das naechste ELEMENT-Geschwister vor el (Textknoten uebersprungen).

    previous_element_sibling alleine reicht nicht: unter html.parser ist
    der Pointer nach einem inline-<svg> None, obwohl previous_siblings
    das svg fuehrt - die Elementkette bricht am self-closing Tag. Wer
    hier den Pointer fragt, misst "kein Absatz nach Grafik", wo einer
    steht (gefunden am 18.09.2026 am Mini-Fall der pytest-Fixture).
    """
    for geschwister in el.previous_siblings:
        if getattr(geschwister, "name", None):
            return geschwister
    return None


def max_absatz_nach_svg(tafel) -> tuple[int, str]:
    """Laengster initial sichtbarer <p>-Absatz, der einem <svg> folgt.

    "Folgt" heisst: das vorherige Element-Geschwister ist ein <svg>, oder
    der Absatz ist das erste Element seines Containers und der CONTAINER
    folgt einem <svg> (Graph-Wrapper-Struktur: svg und Absatz stehen
    Geschwister in einem div). Versteckte Absaetze (hidden, zugeklappt)
    zaehen nicht - die Regel misst, was der Leser unter der Grafik sieht.
    Rueckgabe (Zeichen, Anfang des Absatzes fuer die Fehlermeldung).
    """
    best, best_text = 0, ""
    for p in tafel.find_all("p"):
        if not p.get_text(strip=True) or not _sichtbar_initial(p):
            continue
        vorher = _vorheriges_element(p)
        if (
            vorher is None
            and p.parent is not None
            and p.parent.name not in ("td", "th", "li")
        ):
            vorher = _vorheriges_element(p.parent)
        if vorher is None or vorher.name != "svg":
            continue
        text = re.sub(r"\s+", " ", p.get_text(" ", strip=True))
        if len(text) > best:
            best, best_text = len(text), text[:50]
    return best, best_text


def _reiterhoehen(seite, wurzel: str, b: Bilanz) -> None:
    """Jeder Reiter unter drei Bildschirmen - an der ECHTEN Seite gemessen.

    Es gibt dafuer auch einen Browser-Test, aber der laeuft auf einer
    Fixture mit zwanzig Geraeten. Der echte Bestand ist ein Vielfaches davon
    und waechst; genau daran ist der Katalog-Reiter am 30.08.2026 gerissen,
    nachdem der naechtliche Lauf acht Listungen und mit ihnen laengere
    Modellnamen brachte - dieselbe Zeilenzahl wurde hoeher. Ein Deckel in
    ZEILEN ist nur ein Stellvertreter fuer eine Grenze in PIXELN, und dieser
    Punkt hier ist der einzige, der die Pixel wirklich misst.
    """
    seite.goto(f"{wurzel}/geraete.html", wait_until="networkidle")
    if not seite.query_selector(".gr-reiter [data-tafel]"):
        b.prueft(None, "11b. Reiterhoehen (Geraeteseite ohne Reiter)")
        return
    zu_hoch, gemessen = [], []
    for knopf in seite.query_selector_all(".gr-reiter [data-tafel]"):
        tid = knopf.get_attribute("data-tafel")
        knopf.click()
        seite.wait_for_timeout(80)
        hoehe = seite.evaluate("document.documentElement.scrollHeight")
        gemessen.append(f"{tid.replace('tafel-', '')} {hoehe}")
        if hoehe >= _MAX_REITERHOEHE:
            zu_hoch.append(f"{tid} {hoehe} px")
    b.prueft(
        not zu_hoch,
        "11b. Reiterhoehen: "
        + ", ".join(gemessen)
        + " px"
        + (f" - ZU HOCH: {'; '.join(zu_hoch)}" if zu_hoch else ""),
    )

    mobil = seite.context.browser.new_page(
        viewport={"width": _MOBIL_BREITE, "height": 844}
    )
    try:
        mobil.goto(f"{wurzel}/geraete.html", wait_until="load")
        mobil.wait_for_timeout(300)
        box = mobil.evaluate("""() => {
          const a = document.querySelector('#tafel-tco .gr-zr-antwort');
          // Graphkopf = Oberkante des Graph-Abschnitts (die Messtag-Zeile
          // ist am 28.09.2026 gefallen, die Datumsachse traegt die Tage).
          const k = document.querySelector('#tafel-tco .gr-zr-graph');
          if (!a) return null;
          return {antwort: Math.round(a.getBoundingClientRect().bottom),
                  kopf: k ? Math.round(k.getBoundingClientRect().top) : null,
                  quer: Math.max(document.documentElement.scrollWidth,
                                 document.body.scrollWidth)};
        }""")
        if box:
            quer = box["quer"] <= _MOBIL_BREITE + 1
            ok = (
                box["antwort"] <= 844
                and (box["kopf"] is None or box["kopf"] <= 844)
                and quer
            )
            b.prueft(
                ok,
                f"11c. Graphfalz (Telefon {_MOBIL_BREITE}x844): "
                f"Antwort-Satz endet bei {box['antwort']} px, Graphkopf "
                f"bei {box['kopf']} px (Falz 844)"
                + ("" if quer else f", Seite {box['quer']} px breit"),
            )
        else:
            b.prueft(
                None,
                "11c. Graphfalz (Telefon): Hauptansicht ohne "
                "Antwort-Satz (kein Bestand)",
            )
    finally:
        mobil.close()


def _summary_zeiger(seite, b: Bilanz) -> None:
    """P4/D3, Kriterium 15: Klickbarkeit zeigt sich.

    design.md (17.09.): 20 von 22 Aufklappern des Vergleichs-Reiters
    sahen aus wie Tabellenzeilen - cursor:auto, kein Chevron. Gemessen
    wird COMPUTED (das, was der Leser sieht), je Tafel der Geräteseite,
    auch in zugeklappten details: die Regel von style.css gilt fuer die
    ganze Tafel-Flaeche, nicht nur fuer den ersten Bildschirm. Ein
    summary ohne Text ist keins - das Kriterium fragt dieselbe Menge ab,
    die die Vorlage hervorbringt.
    """
    fehler: list[str] = []
    gesamt = 0
    for knopf in seite.query_selector_all(".gr-reiter [data-tafel]"):
        tid = knopf.get_attribute("data-tafel")
        knopf.click()
        seite.wait_for_timeout(80)
        daten = seite.evaluate(
            """(tid) => {
              const t = document.getElementById(tid);
              if (!t) return null;
              return [...t.querySelectorAll('summary')].map(s => ({
                text: s.textContent.replace(/\\s+/g, ' ').trim().slice(0, 40),
                pointer: getComputedStyle(s).cursor === 'pointer',
                caret: (getComputedStyle(s, '::after').content || 'none')
                       !== 'none',
              }));
            }""",
            tid,
        )
        if daten is None:
            fehler.append(f"{tid} fehlt")
            continue
        gesamt += len(daten)
        for d in daten:
            why = []
            if not d["pointer"]:
                why.append("ohne Zeiger")
            if not d["caret"]:
                why.append("ohne Aufklappzeichen")
            if why:
                fehler.append(f"{tid}: „{d['text']}“ {', '.join(why)}")
    if not gesamt and not fehler:
        b.prueft(None, "15. Aufklappzeichen (Geräteseite ohne Aufklapper)")
        return
    b.prueft(
        not fehler,
        f"15. Aufklappzeichen: {gesamt} summaries, alle mit Zeiger "
        f"und Aufklappzeichen"
        + (f" - FEHLEN: {'; '.join(fehler[:6])}" if fehler else ""),
    )


def _browser_messungen(site: Path, b: Bilanz) -> None:
    """Kriterium 1, 6, 7, 10 und 12 - alles, was eine Darstellung braucht."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        b.prueft(None, "Browser-Messungen (playwright fehlt)")
        return
    pfad = None
    if Path(_CHROMIUM).exists():
        pfad = _CHROMIUM
    else:
        treffer = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
        if treffer:
            pfad = treffer[-1]

    begriff = _haeufigster_absender(site)

    with _server(site) as wurzel, sync_playwright() as p:
        try:
            browser = p.chromium.launch(executable_path=pfad)
        except Exception as exc:  # noqa: BLE001
            b.prueft(None, f"Browser-Messungen ({type(exc).__name__})")
            return
        seite = browser.new_page(viewport={"width": _BREITE, "height": _FALZ})
        _reiterhoehen(seite, wurzel, b)
        seite.goto(f"{wurzel}/geraete.html", wait_until="load")
        seite.wait_for_timeout(300)
        _summary_zeiger(seite, b)

        def oeffne(name: str, warte: int = 600) -> None:
            """Seite laden und einmal durchscrollen.

            Das Scrollen gehoert zum Laden: die Bilder tragen loading="lazy",
            und was nie geladen wurde, hat naturalWidth 0 und faellt aus jeder
            Messung. Ohne diese Schleife prueft Kriterium 6 genau die Bilder
            NICHT, die weit unten stehen."""
            seite.goto(f"{wurzel}/{name}")
            seite.wait_for_timeout(warte)
            hoehe = seite.evaluate("document.body.scrollHeight")
            for y in range(0, hoehe, _FALZ // 2):
                seite.evaluate(f"window.scrollTo(0,{y})")
                seite.wait_for_timeout(70)
            seite.evaluate("window.scrollTo(0,0)")
            seite.wait_for_timeout(300)

        seite.goto(f"{wurzel}/index.html")
        seite.wait_for_timeout(400)
        oben = seite.evaluate(
            """(falz) => [...document.querySelectorAll('.szl')]
                 .filter(e => { const r = e.getBoundingClientRect();
                                return r.top < falz && r.bottom > 0 &&
                                       e.textContent.trim().length > 0; }).length""",
            _FALZ,
        )
        b.prueft(
            oben >= _MIND_OBEN,
            f"1. Oberhalb der Falz: {oben} Geschichten (>= {_MIND_OBEN})",
        )

        schlimmster = 0
        wo = ""
        themenseiten = [
            f"thema/{p.name}" for p in sorted((site / "thema").glob("*.html"))
        ]
        for name in (
            "index.html",
            "meldungen.html",
            "promo/index.html",
            "differenzierung.html",
            *([f"suche.html?q={begriff}"] if begriff else []),
            *themenseiten,
        ):
            oeffne(name)
            for eintrag in seite.evaluate(
                """() => [...document.images]
                     .filter(i => i.naturalWidth > 0)
                     .map(i => ({dargestellt: Math.round(
                                   i.getBoundingClientRect().width *
                                   window.devicePixelRatio),
                                 datei: i.naturalWidth, src: i.currentSrc}))"""
            ):
                if not eintrag["dargestellt"]:
                    continue
                ueber = eintrag["dargestellt"] - eintrag["datei"]
                if ueber > schlimmster:
                    schlimmster, wo = ueber, f"{name}: {eintrag['src'].split('/')[-1]}"
        b.prueft(
            schlimmster <= 0,
            f"6. Groesste Hochskalierung: {schlimmster} px"
            + (f" ({wo})" if schlimmster > 0 else ""),
        )

        seite.goto(f"{wurzel}/meldungen.html")
        seite.wait_for_timeout(500)
        kacheln = seite.evaluate(
            """() => [...document.querySelectorAll('.rkachel')]
                 .map(e => Math.round(
                      e.getBoundingClientRect().top + window.scrollY))"""
        )
        letzte = max(kacheln) if kacheln else -1
        b.prueft(
            bool(kacheln) and letzte < _FALZ,
            f"7. Letztes Ressort beginnt bei {letzte} px "
            f"({len(kacheln)} Ressorts, < {_FALZ})",
        )

        if not begriff:
            b.prueft(None, "10. Suchseite (kein Begriff im Index)")
        else:
            oeffne(f"suche.html?q={begriff}", warte=1400)
            gemessen = seite.evaluate(
                """() => ({
                     treffer: document.querySelectorAll('#dossier-treffer .dsk').length,
                     verlauf: document.querySelectorAll('#dossier-verlauf li').length,
                     bilder: document.querySelectorAll('#dossier-treffer .dsk-motiv img').length,
                     ohne_motiv: [...document.querySelectorAll('#dossier-treffer .dsk')]
                        .filter(k => !k.classList.contains('dsk--zeile') &&
                                     !k.querySelector('.dsk-motiv')).length,
                     bilanz: (document.getElementById('dossier-bilanz')||{}).textContent || '',
                     abgeschnitten: [...document.querySelectorAll('#dossier-treffer .szl')]
                        .filter(e => e.textContent.trim().endsWith('\u2026')).length,
                   })"""
            )
            b.prueft(
                gemessen["treffer"] >= _MIND_DOSSIER_TREFFER
                and gemessen["verlauf"] > 0
                and gemessen["bilder"] > 0
                and not gemessen["ohne_motiv"]
                and not gemessen["abgeschnitten"],
                f"10. Dossier \u201e{begriff}\u201c: {gemessen['treffer']} Treffer "
                f"(>= {_MIND_DOSSIER_TREFFER}), {gemessen['verlauf']} Monate im "
                f"Verlauf, {gemessen['bilder']} Bilder, "
                f"{gemessen['ohne_motiv']} Karten ohne Motiv, "
                f"{gemessen['abgeschnitten']} abgeschnittene Schlagzeilen",
            )

        kopf: dict = {}
        for breite, hoehe in ((_BREITE, _FALZ), (_MOBIL_BREITE, 844)):
            klein = browser.new_page(viewport={"width": breite, "height": hoehe})
            klein.goto(f"{wurzel}/index.html")
            klein.wait_for_timeout(400)
            kopf[breite] = klein.evaluate(
                """() => {
                     const n = document.querySelector('.brand-name');
                     const bar = document.querySelector('.topbar-inner');
                     if (!n || !bar) return null;
                     const nb = n.getBoundingClientRect();
                     const bb = bar.getBoundingClientRect();
                     const br = document.querySelector('.brand').getBoundingClientRect();
                     return {name: n.textContent.replace(/\\s+/g, ' ').trim(),
                             links: Math.round(nb.left),
                             rechts: Math.round(nb.right),
                             versatz: Math.round((br.left + br.width / 2) -
                                                 (bb.left + bb.width / 2)),
                             docW: document.documentElement.scrollWidth,
                             winW: window.innerWidth};
                   }"""
            )
            klein.close()
        fehler = []
        for breite, m in kopf.items():
            if not m:
                fehler.append(f"{breite}px: kein Zeitungskopf gefunden")
                continue
            if m["name"] != _MARKE:
                fehler.append(f"{breite}px: Kopf liest „{m['name']}“")
            if m["docW"] > m["winW"]:
                fehler.append(f"{breite}px: Seitwaertslauf {m['docW'] - m['winW']} px")
            if m["links"] < 0 or m["rechts"] > m["winW"]:
                fehler.append(
                    f"{breite}px: Kopf ragt aus dem Bild "
                    f"({m['links']}..{m['rechts']} in {m['winW']})"
                )
            if abs(m["versatz"]) > _MAX_KOPF_VERSATZ:
                fehler.append(
                    f"{breite}px: Kopf {abs(m['versatz'])} px aus der "
                    f"Mitte (max {_MAX_KOPF_VERSATZ})"
                )
        b.prueft(
            not fehler,
            "12. Zeitungskopf: "
            + (
                "; ".join(fehler)
                if fehler
                else ", ".join(
                    f"{breite}px Versatz {int(abs(m['versatz']))} px, "
                    f"Breite {m['rechts'] - m['links']} px"
                    for breite, m in kopf.items()
                    if m
                )
            ),
        )
        browser.close()


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
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

    berichte = sorted(
        f
        for f in (root / "data" / "reports").glob("*.json")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", f.stem)
    )
    bericht = json.loads(berichte[-1].read_text(encoding="utf-8"))
    hs = [
        h
        for r in (bericht.get("regions") or {}).values()
        for h in r.get("highlights") or []
    ]
    mit_bild = [h for h in hs if h.get("image")]
    quote = 100 * len(mit_bild) // max(1, len(hs))
    b.prueft(
        quote >= _MIND_BILDQUOTE,
        f"2. Meldungen mit Bild: {len(mit_bild)} von {len(hs)} "
        f"({quote} %, >= {_MIND_BILDQUOTE} %)",
    )
    ohne_mass = [h for h in mit_bild if not h.get("image_w")]
    b.prueft(not ohne_mass, f"2b. Bilder ohne gemessene Breite: {len(ohne_mass)}")

    index = BeautifulSoup(
        (site / "index.html").read_text(encoding="utf-8"), "html.parser"
    )
    meldungen = BeautifulSoup(
        (site / "meldungen.html").read_text(encoding="utf-8"), "html.parser"
    )

    gross = index.select(".aufmacher-bild img, .reihe-zwei .stueck-bild img")
    zu_klein = [img for img in gross if int(img.get("width") or 0) < MIND_BREITE_GROSS]
    b.prueft(
        bool(gross) and not zu_klein,
        f"3. Bilder in Aufmacher/zweiter Reihe: {len(gross)}, "
        f"davon unter {MIND_BREITE_GROSS} px: {len(zu_klein)}",
    )

    ressorts = meldungen.select(".mressort")
    stufen = all(sec.select(".mlead") for sec in ressorts)
    summe = sum(
        int(m.group())
        for x in meldungen.select(".rkachel .rkachel-alle")
        if (m := re.search(r"\d+", x.get_text(" ", strip=True)))
    )
    gerendert = len(meldungen.select(".mressort .meldung"))
    b.prueft(
        len(ressorts) >= 3 and stufen and summe == len(hs) and gerendert == len(hs),
        f"4. Meldungsseite: {len(ressorts)} Ressorts, "
        f"Ressortzahlen {summe}, gerendert {gerendert}, Daten {len(hs)}",
    )

    seiten = [index, meldungen]
    for weitere in [
        site / "wettbewerb.html",
        site / "differenzierung.html",
        site / "geraete.html",
        *sorted((site / "thema").glob("*.html")),
    ]:
        if weitere.exists():
            seiten.append(
                BeautifulSoup(weitere.read_text(encoding="utf-8"), "html.parser")
            )
    abgeschnitten = [
        t for soup in seiten for t in _schlagzeilen(soup) if t.endswith("…")
    ]
    alle = sum(len(_schlagzeilen(soup)) for soup in seiten)
    b.prueft(
        not abgeschnitten,
        f"5. Schlagzeilen geprueft: {alle}, abgeschnitten: {len(abgeschnitten)}",
    )

    promo_datei = site / "promo" / "index.html"
    if not promo_datei.exists():
        b.prueft(None, "8. Promo Uebersicht (nicht gerendert)")
    else:
        promo = BeautifulSoup(promo_datei.read_text(encoding="utf-8"), "html.parser")
        verweise = {
            img["src"]
            for img in promo.select("img[src]")
            if "images/" in img["src"] and "logo" not in img["src"]
        }
        fehlend = [v for v in verweise if not (site / "promo" / v).exists()]
        b.prueft(
            len(verweise) >= _MIND_PROMO_BILDER and not fehlend,
            f"8. Promo Uebersicht: {len(verweise)} verschiedene Bilder "
            f"(>= {_MIND_PROMO_BILDER}), {len(fehlend)} Verweise ins Leere",
        )
        ordner = site / "promo" / "images"
        leer = (
            [
                p.name
                for p in ordner.iterdir()
                if p.is_file() and ist_leer(p.read_bytes())
            ]
            if ordner.exists()
            else []
        )
        b.prueft(
            not leer,
            f"8b. Leere Bilder ausgeliefert: {len(leer)}"
            + (f" ({', '.join(leer)})" if leer else ""),
        )
        karten = promo.select(".promo-karten .pkarte")
        ohne_motiv = [k for k in karten if not k.select_one(".pk-bild")]
        leere_kaesten = [
            kasten
            for kasten in promo.select(".pk-bild")
            if not kasten.select_one("img") and not kasten.get_text(strip=True)
        ]
        b.prueft(
            bool(karten) and not ohne_motiv and not leere_kaesten,
            f"8c. Karten ohne Motiv: {len(ohne_motiv)} von "
            f"{len(karten)}, leere Bildkaesten: {len(leere_kaesten)}",
        )

    dz_datei = site / "differenzierung.html"
    if not dz_datei.exists():
        b.prueft(None, "9. Differenzierung (nicht gerendert)")
    else:
        dz = BeautifulSoup(dz_datei.read_text(encoding="utf-8"), "html.parser")
        karten = [
            k for k in dz.select(".dzk") if "dzk--zeile" not in (k.get("class") or [])
        ]
        mit_bild = [k for k in karten if k.select_one(".dzk-motiv img")]
        ohne_motiv = [k for k in karten if not k.select_one(".dzk-motiv")]
        leere_kaesten = [
            m
            for m in dz.select(".dzk-motiv")
            if not m.select_one("img") and not m.get_text(strip=True)
        ]
        quote = 100 * len(mit_bild) // max(1, len(karten))
        b.prueft(
            bool(karten)
            and quote >= _MIND_DIFF_BILDQUOTE
            and not ohne_motiv
            and not leere_kaesten,
            f"9. Differenzierung: {len(mit_bild)} von {len(karten)} Karten "
            f"mit Bild ({quote} %, >= {_MIND_DIFF_BILDQUOTE} %), "
            f"{len(ohne_motiv)} ohne Motiv, {len(leere_kaesten)} leere Kaesten",
        )
        marktbild = dz.select_one(".dz-marktbild")
        balken = {
            li.select_one(".dz-balken-name").get_text(strip=True): int(
                li.select_one(".dz-balken-n").get_text(strip=True)
            )
            for li in (
                marktbild.select(".dz-mb-block")[0].select("li") if marktbild else []
            )
        }
        falsch = []
        for abschnitt in dz.select(".dz-hebel"):
            label = abschnitt.select_one("h2").get_text(strip=True)
            if balken.get(label) != len(abschnitt.select(".dzk")):
                falsch.append(label)
        b.prueft(
            bool(balken) and not falsch,
            f"9b. Marktbild gegen die Rubriken: {len(balken)} Hebel, "
            f"{len(falsch)} widersprechen"
            + (f" ({', '.join(falsch)})" if falsch else ""),
        )

    gr_datei = site / "geraete.html"
    if not gr_datei.exists():
        b.prueft(False, "11. Geraeteradar: geraete.html fehlt ganz")
    else:
        gr = BeautifulSoup(gr_datei.read_text(encoding="utf-8"), "html.parser")
        maengel = []

        start = gr.select_one("#tafel-tco")
        if start is None:
            maengel.append("die Hauptansicht 'Vergleich' fehlt")
        for tot in (".gr-flaeche", ".gr-punkt", ".gr-etikett", ".gr-band"):
            if gr.select(tot):
                maengel.append(f"Reste der geloeschten Preisgrafik: {tot}")

        reiter = [k.get("data-tafel") for k in gr.select(".gr-reiter [data-tafel]")]
        erwartet = ["tafel-tco", "tafel-verlauf", "tafel-radar", "tafel-katalog"]
        if reiter != erwartet:
            maengel.append(f"Reiter {reiter} statt {erwartet}")
        if gr.select_one(".gr-reiter a") is not None:
            maengel.append(
                "die Reiterleiste trägt noch einen Link statt "
                "der vier Tafeln (E3: der Radar ist ein Reiter)"
            )
        if gr.select_one("#tafel-radar") is None:
            maengel.append(
                "#tafel-radar fehlt - der Radar-Reiter ohne Tafel wäre ein toter Tab"
            )
        if gr.select_one("#tafel-portfolio") is not None:
            maengel.append(
                "#tafel-portfolio steht noch auf der Geräteseite "
                "- seine Abschnitte gehören auf den Radar (O3)"
            )

        if start is not None and start.select_one("svg.gr-zr") is None:
            maengel.append(
                "die TCO-Zeitreihe (svg.gr-zr) fehlt in der Hauptansicht (E2)"
            )
        if start is not None:
            svg = start.select_one("svg.gr-zr")
            if svg is not None:
                if not svg.select("circle.gr-zr-punkt"):
                    maengel.append("der Zeitreihen-Graph trägt keine Messpunkte")
                if not svg.select("text.gr-zr-xtick"):
                    maengel.append("die X-Achse trägt keine Messtag-Ticks")
            for tot in (
                ".gr-hgraph",
                ".gr-balkenliste",
                ".gr-bz",
                ".gr-msel",
                ".gr-antwort-leit",
            ):
                if start.select(tot):
                    maengel.append(f"Rest der bis E2 ersetzten Form: {tot}")
        verlaufflaeche = gr.select_one("#tafel-verlauf")
        if (
            verlaufflaeche is not None
            and verlaufflaeche.select_one("#gr-verlaufdaten") is None
            and "liegen noch keine Messreihen vor" not in verlaufflaeche.get_text()
        ):
            maengel.append(
                "die Gerätedaten des Preisverlaufs "
                "(#gr-verlaufdaten) fehlen im Verlaufs-Reiter"
            )
        if (
            verlaufflaeche is not None
            and verlaufflaeche.select_one("svg.gr-g2") is not None
        ):
            maengel.append(
                "der G2-Block ist im Verlaufs-Reiter "
                "zurückgekehrt - der Reiter trägt den Modell-"
                "Wähler als alleinige Grafik (F4)"
            )
        if (
            verlaufflaeche is not None
            and verlaufflaeche.select_one("#gr-g0-lager, svg.gr-g0") is not None
        ):
            maengel.append(
                "der G0-Block ist im Verlaufs-Reiter "
                "zurückgekehrt - der Reiter trägt seine eigene "
                "Barpreis-Auswahl (Doppel-Darstellung, §4.6/4.8)"
            )

        maengel += zeitraum_maengel(start) if start is not None else []
        verlauf = gr.select_one("#tafel-verlauf")
        verlauf_leer = (
            verlauf is not None and verlauf.select_one("#gr-verlaufdaten") is None
        )

        for el in gr.find_all(attrs={"transform": True}):
            if "rotate" in (el.get("transform") or ""):
                maengel.append("gedrehte Beschriftung im Dokument")
                break

        radar_seite = gr
        zeilen = radar_seite.select("#wr-alarme .gr-a-zeile")
        if not zeilen:
            if maengel:
                b.prueft(False, "11. Geraeteradar: " + "; ".join(maengel))
            else:
                b.prueft(
                    None,
                    "11. Geraeteradar: noch keine Alarmzeile "
                    "erfasst (Grafik ist weg, Struktur in Ordnung"
                    + (", Preisverlauf noch ohne Messreihen" if verlauf_leer else "")
                    + ")",
                )
        else:
            ohne_beleg = [
                z
                for z in zeilen
                if not (
                    z.select_one("a.gr-a-quelle[href^='http']")
                    and z.select_one(".gr-a-datum")
                )
            ]
            ohne_aufklapper = [
                z for z in zeilen if radar_seite.find(id=z.get("data-auf")) is None
            ]
            if ohne_beleg:
                maengel.append(f"{len(ohne_beleg)} Alarmzeilen ohne Beleg")
            if ohne_aufklapper:
                maengel.append(f"{len(ohne_aufklapper)} Zeilen ohne Aufklapper")

            kacheln = radar_seite.select(".gr-chips .gr-chip b")
            summe = sum(
                int(k.get_text(strip=True))
                for k in kacheln
                if k.get_text(strip=True).isdigit()
            )
            alarm_abschnitt = radar_seite.select_one("#wr-alarme")
            satz = (
                " ".join(alarm_abschnitt.get_text(" ", strip=True).split())
                if alarm_abschnitt is not None
                else ""
            )
            if len(kacheln) != 4:
                maengel.append(f"{len(kacheln)} statt 4 Alarm-Chips")
            elif f"{summe} Modelle mit ihren Speichergrößen" not in satz:
                maengel.append(
                    f"die Kacheln zaehlen {summe}, der Satz darunter etwas anderes"
                )

            b.prueft(
                not maengel,
                f"11. Geraeteradar: {len(zeilen)} Alarmzeilen, "
                f"{len(kacheln)} Chips ueber {summe} Vergleichen, "
                f"die TCO-Zeitreihe steht in der Hauptansicht"
                if not maengel
                else "11. Geraeteradar: " + "; ".join(maengel[:5]),
            )

        werte, zuviel = [], []
        for tid, deckel in _FLIESSTEXT_DECKEL.items():
            tafel = gr.select_one(f"#{tid}")
            if tafel is None:
                zuviel.append(f"{_REITER_NAMEN[tid]}: Tafel {tid} fehlt")
                continue
            n = fliesstext_zeichen(tafel)
            werte.append(f"{_REITER_NAMEN[tid]} {n} Z (max {deckel})")
            if n > deckel:
                zuviel.append(f"{_REITER_NAMEN[tid]} {n} Z > {deckel}")
        b.prueft(
            not zuviel,
            "13. Fliessttext-Deckel: "
            + ", ".join(werte)
            + (f" - ZU VIEL TEXT: {'; '.join(zuviel)}" if zuviel else ""),
        )

        block_max, block_wo = 0, ""
        for tid in _FLIESSTEXT_DECKEL:
            tafel = gr.select_one(f"#{tid}")
            if tafel is None:
                continue
            n, anfang = max_absatz_nach_svg(tafel)
            if n > block_max:
                block_max, block_wo = n, f"{_REITER_NAMEN[tid]}: {anfang}"
        b.prueft(
            block_max <= _MAX_ABSATZ_NACH_SVG,
            f"14. Fliesstblock unter Grafik: laengster Absatz nach "
            f"<svg> {block_max} Z (max {_MAX_ABSATZ_NACH_SVG})"
            + (f" - {block_wo}" if block_max > _MAX_ABSATZ_NACH_SVG else ""),
        )

    _browser_messungen(site, b)

    print()
    return b.ausgeben()


if __name__ == "__main__":
    raise SystemExit(main())
