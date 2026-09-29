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

Dazu die Kriterien der Geraeteseite, einer Kosten-Rangliste in section#kosten
(die Reiter-Seite mit Tafeln und Zeitreihe ist ersetzt):

 11. Die Rangliste steht: #kosten, #kv-wahl mit den fuenf Auswahlreihen,
     ein lesbarer Datenknoten #kv-daten und mindestens eine Ergebniszeile -
     sonst ein benannter Leerzustand. Keine Reste der Reiter-Seite.
 11b. Die erste Summe endet bei 1440x900 und 390x844 ueber der Falz, und
     auf 390 px laeuft nichts seitwaerts.
 11c. In keiner Ergebniszeile ueberdecken sich Anbieter, Info, Summe und
     Abstand - an der Startansicht und an Adressen aus dem Datenknoten.
 13. Der Text ausserhalb von Zahlen und Chips bleibt unter einem Deckel.
 15. Jedes Aufklappen zeigt Zeiger und Aufklappzeichen.

Dazu das Kriterium der Umbenennung (11.08.2026):

 12. Der Zeitungskopf traegt auf 1440 UND auf 390 px den vollen Namen
     "Vodafone Product and Services Insights", steht vollstaendig im Bild,
     erzeugt keinen Seitwaertslauf und sitzt nicht weiter als 90 px aus der
     Mitte. Der laengere Name hat in seiner ersten Fassung alle drei Zahlen
     gerissen: 169 px aus der Mitte und 61 px aus dem Bild heraus.

Kriterium 1, 6, 7, 10, 11b, 11c, 12 und 15 brauchen einen echten Browser -
Chromium liegt unter /opt/pw-browsers. Ohne Browser laufen die uebrigen trotzdem durch.

**Gemessen wird ueber einen lokalen HTTP-Server, nicht ueber file://.** Der
Grund ist Kriterium 10: `fetch('search_index.json')` ist unter file:// von der
Same-Origin-Regel gesperrt, die Suchseite bliebe leer, und die Pruefung wuerde
einen Fehler messen, den es in Wirklichkeit nicht gibt. Der Server bindet auf
127.0.0.1 und braucht kein Netz.

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

from bs4 import BeautifulSoup, Comment                           # noqa: E402

from telco_radar.report.bilder import (                          # noqa: E402
    MIND_BREITE_GROSS, ist_leer)

# Die Falz: was ein Leser bei 1440x900 ohne Scrollen sieht. 900 ist die
# konservative Annahme - ein 16:9-Notebook mit Browserleisten.
_FALZ = 900
_BREITE = 1440
_MIND_OBEN = 6
# Der Zeitungskopf (Kriterium 12). Die Marke steht hier als EIN String, damit
# eine halb durchgezogene Umbenennung auffaellt - am 11.08.2026 stand sie an
# elf Stellen in den Vorlagen. Der zulaessige Versatz aus der Mitte ist
# gemessen: der Kopf sass schon vor der Umbenennung 38 px links (bei 1440) und
# 68 px bei 1180, weil die rechte Spalte breiter ist als die leere linke. 90
# px lassen dem laengeren Namen Luft, ohne den zweiten Fehlerfall (169 px)
# durchzulassen.
_MOBIL_BREITE = 390
_MOBIL_HOEHE = 844
_MARKE = "Vodafone Product and Services Insights"
_MAX_KOPF_VERSATZ = 90
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
# Abnahme der Differenzierungs-Seite. Gemessen am Bestand vom 08.08.2026
# bekommen 35 von 71 Beispielen ein Bild (5 geerbt aus dem Wochenbericht, 30
# per og:image) - die Schwelle liegt bewusst darunter, weil die Ausbeute an
# fremden Seiten haengt und nicht am Code. Der harte Teil ist die zweite
# Zahl: KEINE Karte ohne Motiv.
_MIND_DIFF_BILDQUOTE = 25
# Abnahme der Suchseite: so viele Treffer muss ein Begriff bringen, der im
# Archiv nachweislich vorkommt (gewaehlt wird der haeufigste Absender).
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
        [sys.executable, "-m", "http.server", str(port)], cwd=site,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
    zaehler = Counter(e.get("operator") or "" for e in index
                      if e.get("kind") != "promo")
    for name, _ in zaehler.most_common():
        # Ein Wort reicht: die Suche verknuepft mehrere Woerter mit UND, und
        # "O2 / Telefónica Deutschland" faende dann nur sich selbst.
        erstes = name.split()[0] if name else ""
        if len(erstes) >= 4:
            return erstes
    return ""


# ---- Geraeteseite: EINE Kosten-Rangliste in section#kosten.
#
# Die fuenf Auswahlreihen in #kv-wahl, in der Reihenfolge der Vorlage. Eine
# fehlende Reihe ist eine Frage, die der Leser nicht mehr stellen kann.
_KV_REIHEN = ("hersteller", "familie", "modell", "stufe", "raten")
# Reste der Reiter-Seite, die nicht zurueckkehren duerfen.
_KV_ALTLASTEN = (".gr-reiter", "[id^=tafel-]", "svg.gr-zr", ".gr-zr-antwort")
# Die vier Teile einer Ergebniszeile, die sich nie ueberdecken duerfen
# (Kriterium 11c). `.kv-info > span` sind mehrere Kaesten je Zeile.
_KV_TEILE = (".kv-anb", ".kv-info > span", ".kv-summe", ".kv-abstand")
# So viele Adressen `?modell=…&band=…&raten=alle` misst 11c zusaetzlich zur
# Startansicht - die Geraete mit den meisten Anbietern, weil dort die
# meisten Zeilen und die laengsten Info-Zeilen stehen.
_KV_ADRESSEN = 4

# ---- Fliesstext-Deckel der Geraeteseite (Kriterium 13). Antonio: "Ich will
# keinen Text sehen." Gezaehlt wird jeder Text in #kosten AUSSER den Zahlen
# und Chips: die Auswahl (#kv-wahl), die Ergebniszeilen samt Rechenweg
# (.kv-zeile), Knoepfe, Datenknoten und <template>. Uebrig bleiben Titel,
# Kopfzeilen, die Zeile der Anbieter ohne Preis, ein Leerzustand und der
# Fuss - zusammen rund 100 Zeichen. 400 lassen einer laengeren Fehlermeldung
# Platz, aber keinem Erklaerabsatz.
_FLIESSTEXT_DECKEL = 400
_FLIESSTEXT_OHNE = ("#kv-wahl", ".kv-zeile", "button", "script", "template")


def fliesstext_zeichen(bereich) -> int:
    """Zeichen des Textes in `bereich`, der weder Zahl noch Chip ist.

    Ausgenommen ist alles unter `_FLIESSTEXT_OHNE`. Leerraum wird auf ein
    Leerzeichen normalisiert, damit Einrueckungen im Quelltext die Zahl
    nicht aufblasen.
    """
    ausgenommen = {id(el) for sel in _FLIESSTEXT_OHNE
                   for el in bereich.select(sel)}
    teile = []
    for s in bereich.find_all(string=True):
        if any(id(v) in ausgenommen for v in s.parents):
            continue
        if isinstance(s, Comment) or s.parent.name in ("script", "template"):
            continue
        if s.strip():
            teile.append(s.strip())
    return len(re.sub(r"\s+", " ", " ".join(teile)))


# Kriterium 15 - EINE Messung, die pruefe_portal an der echten Seite und
# tests/test_geraete_textdeckel.py an Mini-HTML mit der echten style.css
# ausfuehren. Gemessen wird COMPUTED: der Zeiger und ein Aufklappzeichen
# (`.kv-pfeil`, dessen ::before gezeichnet wird), auch in zugeklappten
# details.
SUMMARY_JS = """(wurzel) => {
  const w = wurzel ? document.querySelector(wurzel) : document;
  if (!w) return null;
  return [...w.querySelectorAll('summary')].map(s => {
    const pfeil = s.querySelector('.kv-pfeil');
    return {
      text: s.textContent.replace(/\\s+/g, ' ').trim().slice(0, 40),
      kern: s.classList.contains('kv-kern'),
      pointer: getComputedStyle(s).cursor === 'pointer',
      caret: !!pfeil &&
             (getComputedStyle(pfeil, '::before').content || 'none') !== 'none',
    };
  });
}"""


def _kosten_falz(browser, wurzel: str, b: Bilanz) -> None:
    """11b: die erste Summe steht auf beiden Breiten ueber der Falz.

    Wer die Seite oeffnet, soll ohne Scrollen lesen, was das guenstigste
    Angebot kostet. Gemessen am ECHTEN Bestand, nicht an einer Fixture -
    laengere Modellnamen im Titel schieben die Liste nach unten.
    """
    messungen, fehler = [], []
    for breite, hoehe in ((_BREITE, _FALZ), (_MOBIL_BREITE, _MOBIL_HOEHE)):
        seite = browser.new_page(viewport={"width": breite, "height": hoehe})
        try:
            seite.goto(f"{wurzel}/geraete.html", wait_until="load")
            seite.wait_for_timeout(300)
            m = seite.evaluate("""() => {
              const s = document.querySelector('#kosten .kv-summe');
              return {unten: s ? Math.round(s.getBoundingClientRect().bottom) : null,
                      quer: Math.max(document.documentElement.scrollWidth,
                                     document.body.scrollWidth)};
            }""")
        finally:
            seite.close()
        if m["unten"] is None:
            b.prueft(None, "11b. Kostenfalz (Geraeteseite ohne Ergebniszeile)")
            return
        messungen.append(f"{breite}x{hoehe} Summe endet bei {m['unten']} px")
        if m["unten"] > hoehe:
            fehler.append(f"{breite}px: erste Summe unter der Falz "
                          f"({m['unten']} > {hoehe})")
        if breite == _MOBIL_BREITE and m["quer"] > _MOBIL_BREITE + 1:
            fehler.append(f"{breite}px: Seite {m['quer']} px breit")
    b.prueft(not fehler, "11b. Kostenfalz: " + ", ".join(messungen)
             + (f" - {'; '.join(fehler)}" if fehler else ""))


def _kv_adressen(site: Path) -> list[str]:
    """Adressen fuer 11c aus dem Datenknoten, nicht geraten: je Modell die
    Tarifstufe mit den meisten Anbietern, die Modelle mit den meisten
    Anbietern zuerst."""
    try:
        soup = BeautifulSoup((site / "geraete.html").read_text(encoding="utf-8"),
                             "html.parser")
        daten = json.loads(soup.select_one("#kv-daten").string)
    except (OSError, AttributeError, TypeError, json.JSONDecodeError):
        return []
    kandidaten = []
    for modell, angebote in (daten.get("angebote") or {}).items():
        je_stufe: dict[str, set] = {}
        for a in angebote:
            je_stufe.setdefault(a.get("stufe"), set()).add(a.get("anbieter"))
        if not je_stufe:
            continue
        stufe, anbieter = max(je_stufe.items(),
                              key=lambda kv: (len(kv[1]), str(kv[0])))
        kandidaten.append((len(anbieter), modell, stufe))
    kandidaten.sort(key=lambda k: (-k[0], k[1]))
    return [f"?modell={m}&band={s}&raten=alle"
            for _, m, s in kandidaten[:_KV_ADRESSEN]]


def _kosten_ueberlappung(browser, wurzel: str, site: Path, b: Bilanz) -> None:
    """11c: in keiner Ergebniszeile ueberdecken sich Anbieter, Info, Summe
    und Abstand - auf beiden Breiten, an der Startansicht und an Adressen
    aus dem Datenknoten. Zeilen in zugeklappten Gruppen haben keine Box und
    fallen heraus; gezaehlt wird, was gemessen wurde."""
    adressen = ["", *_kv_adressen(site)]
    gemessen, fehler = 0, []
    for breite, hoehe in ((_BREITE, _FALZ), (_MOBIL_BREITE, _MOBIL_HOEHE)):
        seite = browser.new_page(viewport={"width": breite, "height": hoehe})
        try:
            for adr in adressen:
                seite.goto(f"{wurzel}/geraete.html{adr}", wait_until="load")
                seite.wait_for_timeout(250)
                ergebnis = seite.evaluate(
                    """(teile) => {
                      const aus = [];
                      let n = 0;
                      for (const z of document.querySelectorAll('#kosten .kv-zeile')) {
                        const kaesten = [];
                        for (const sel of teile)
                          for (const el of z.querySelectorAll(sel)) {
                            const r = el.getBoundingClientRect();
                            if (r.width > 0 && r.height > 0)
                              kaesten.push({sel, r});
                          }
                        if (!kaesten.length) continue;
                        n++;
                        for (let i = 0; i < kaesten.length; i++)
                          for (let j = i + 1; j < kaesten.length; j++) {
                            const a = kaesten[i].r, c = kaesten[j].r;
                            const x = Math.min(a.right, c.right) - Math.max(a.left, c.left);
                            const y = Math.min(a.bottom, c.bottom) - Math.max(a.top, c.top);
                            if (x > 0.5 && y > 0.5)
                              aus.push((z.dataset.anbieter || '?') + ': ' +
                                       kaesten[i].sel + ' / ' + kaesten[j].sel);
                          }
                      }
                      return {n, aus};
                    }""", list(_KV_TEILE))
                gemessen += ergebnis["n"]
                fehler += [f"{breite}px {adr or 'Start'} {x}"
                           for x in ergebnis["aus"]]
        finally:
            seite.close()
    if not gemessen:
        b.prueft(None, "11c. Zeilenueberlappung (keine Ergebniszeile)")
        return
    b.prueft(not fehler,
             f"11c. Zeilenueberlappung: {gemessen} Zeilen an "
             f"{len(adressen)} Adressen auf 2 Breiten, {len(fehler)} Ueberdeckungen"
             + (f" - {'; '.join(fehler[:4])}" if fehler else ""))


def _summary_zeiger(seite, b: Bilanz) -> None:
    """Kriterium 15: Klickbarkeit zeigt sich. Jedes summary in #kosten -
    Ergebniszeilen und die zugeklappte Nebengruppe - traegt den Zeiger und
    ein gezeichnetes Aufklappzeichen."""
    daten = seite.evaluate(SUMMARY_JS, "#kosten")
    if not daten:
        b.prueft(None, "15. Aufklappzeichen (Geräteseite ohne Aufklapper)")
        return
    fehler = []
    for d in daten:
        why = [w for w, ok in (("ohne Zeiger", d["pointer"]),
                               ("ohne Aufklappzeichen", d["caret"])) if not ok]
        if why:
            fehler.append(f"„{d['text']}“ {', '.join(why)}")
    kerne = sum(1 for d in daten if d["kern"])
    b.prueft(not fehler and kerne > 0,
             f"15. Aufklappzeichen: {len(daten)} summaries ({kerne} "
             f"Ergebniszeilen), alle mit Zeiger und Aufklappzeichen"
             + (f" - FEHLEN: {'; '.join(fehler[:6])}" if fehler else "")
             + ("" if kerne else " - keine summary.kv-kern"))


def _browser_messungen(site: Path, b: Bilanz) -> None:
    """Kriterium 1, 6, 7, 10, 11b, 11c, 12 und 15 - alles, was eine
    Darstellung braucht."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        b.prueft(None, "Browser-Messungen (playwright fehlt)")
        return
    # Die zwei festen Pfade sind Linux (Sandbox bzw. Runner). Findet keiner
    # etwas, wird Playwright SELBST gefragt, statt die Messung abzusagen:
    # `executable_path=None` heisst "nimm den Browser, den du verwaltest" -
    # genau den, den die Browsertests (`tests/test_falz_browser.py`) benutzen. Ohne
    # diesen Rueckfall meldete das Skript auf einem Mac "kein Chromium
    # gefunden" und uebersprang fuenf Kriterien, waehrend die Browsertests
    # derselben Arbeitskopie liefen. Ein uebersprungenes Kriterium sieht in
    # der Bilanz aus wie ein bestandenes - dieselbe Lehre wie beim
    # Chromium-Schritt in `ci.yml` (09.08.2026).
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
            # Der Grund gehoert in die Bilanz. "Kein Chromium" und "Chromium
            # startet nicht" sind zwei verschiedene Befunde, und der zweite
            # ist ohne seinen Text nicht zu beheben.
            b.prueft(None, f"Browser-Messungen ({type(exc).__name__})")
            return
        seite = browser.new_page(viewport={"width": _BREITE, "height": _FALZ})
        _kosten_falz(browser, wurzel, b)
        _kosten_ueberlappung(browser, wurzel, site, b)
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
            _FALZ)
        b.prueft(oben >= _MIND_OBEN,
                 f"1. Oberhalb der Falz: {oben} Geschichten (>= {_MIND_OBEN})")

        # Kriterium 6 gilt fuer beide Seiten - ein hochskaliertes Bild ist
        # der sichtbarste Teil des Befunds vom 06.08.2026.
        schlimmster = 0
        wo = ""
        themenseiten = [f"thema/{p.name}"
                        for p in sorted((site / "thema").glob("*.html"))]
        # Seit dem 08.08.2026 auch die Differenzierungs- und die Suchseite:
        # beide zeigen seither Bilder, und beide setzen sie in Positionen,
        # die es vorher nicht gab (Hebel-Aufmacher, Dossier-Aufmacher).
        for name in ("index.html", "meldungen.html", "promo/index.html",
                     "differenzierung.html",
                     *([f"suche.html?q={begriff}"] if begriff else []),
                     *themenseiten):
            oeffne(name)
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
        seite.goto(f"{wurzel}/meldungen.html")
        seite.wait_for_timeout(500)
        kacheln = seite.evaluate(
            """() => [...document.querySelectorAll('.rkachel')]
                 .map(e => Math.round(
                      e.getBoundingClientRect().top + window.scrollY))""")
        letzte = max(kacheln) if kacheln else -1
        b.prueft(bool(kacheln) and letzte < _FALZ,
                 f"7. Letztes Ressort beginnt bei {letzte} px "
                 f"({len(kacheln)} Ressorts, < {_FALZ})")

        # ---- Kriterium 10: die Suchseite liefert ein Dossier
        #
        # Sie muss im BROWSER gemessen werden: bis auf das Suchfeld entsteht
        # alles in app.js, nachdem search_index.json geladen ist. Eine
        # statische Pruefung des HTML saehe nur leere Behaelter - genau die
        # Sorte Pruefung, die am 06.08.2026 sechs falsche Zahlen durchgelassen
        # hat.
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
                   })""")
            b.prueft(gemessen["treffer"] >= _MIND_DOSSIER_TREFFER
                     and gemessen["verlauf"] > 0
                     and gemessen["bilder"] > 0
                     and not gemessen["ohne_motiv"]
                     and not gemessen["abgeschnitten"],
                     f"10. Dossier \u201e{begriff}\u201c: {gemessen['treffer']} Treffer "
                     f"(>= {_MIND_DOSSIER_TREFFER}), {gemessen['verlauf']} Monate im "
                     f"Verlauf, {gemessen['bilder']} Bilder, "
                     f"{gemessen['ohne_motiv']} Karten ohne Motiv, "
                     f"{gemessen['abgeschnitten']} abgeschnittene Schlagzeilen")

        # ---- Kriterium 12: der Zeitungskopf traegt den ganzen Namen
        #
        # Gemessen wird auf BEIDEN Breiten, und das ist der Punkt: der Name
        # "Vodafone Product and Services Insights" ist 373 statt 214 px breit,
        # und auf dem Telefon lief er in der ersten Fassung 61 px aus dem
        # Bild - die ganze Seite liess sich seitwaerts schieben. Geprueft
        # wird deshalb dreierlei: der Kopf steht vollstaendig im Bild, die
        # Seite hat keinen Seitwaertslauf, und der Kopf sitzt nicht weiter
        # aus der Mitte als _MAX_KOPF_VERSATZ. Die dritte Zahl ist die, an
        # der eine Schriftvergroesserung zuerst auffaellt.
        kopf: dict = {}
        for breite, hoehe in ((_BREITE, _FALZ), (_MOBIL_BREITE, _MOBIL_HOEHE)):
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
                   }""")
            klein.close()
        fehler = []
        for breite, m in kopf.items():
            if not m:
                fehler.append(f"{breite}px: kein Zeitungskopf gefunden")
                continue
            if m["name"] != _MARKE:
                fehler.append(f"{breite}px: Kopf liest „{m['name']}“")
            if m["docW"] > m["winW"]:
                fehler.append(f"{breite}px: Seitwaertslauf "
                              f"{m['docW'] - m['winW']} px")
            if m["links"] < 0 or m["rechts"] > m["winW"]:
                fehler.append(f"{breite}px: Kopf ragt aus dem Bild "
                              f"({m['links']}..{m['rechts']} in {m['winW']})")
            if abs(m["versatz"]) > _MAX_KOPF_VERSATZ:
                fehler.append(f"{breite}px: Kopf {abs(m['versatz'])} px aus der "
                              f"Mitte (max {_MAX_KOPF_VERSATZ})")
        b.prueft(not fehler,
                 "12. Zeitungskopf: "
                 + ("; ".join(fehler) if fehler else
                    ", ".join(f"{breite}px Versatz {int(abs(m['versatz']))} px, "
                              f"Breite {m['rechts'] - m['links']} px"
                              for breite, m in kopf.items() if m)))
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
    # Die Geraeteseite traegt als Kosten-Rangliste keine `szl` mehr; sie
    # bleibt in der Liste, damit eine zurueckkehrende Schlagzeile dort
    # geprueft wird. Wer eine Seite mit Schlagzeilen
    # ergaenzt und sie hier vergisst, prueft sie nie: genau dieser Zuschnitt
    # hat am 08.08.2026 37 Karten ohne Motiv gedeckt.
    seiten = [index, meldungen]
    for weitere in [site / "wettbewerb.html", site / "differenzierung.html",
                    site / "geraete.html",
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
        # 8c: JEDE Karte traegt ein Motiv - ein Kampagnenbild oder eine
        # Schriftkachel -, und nirgends steht ein leerer Bildkasten.
        #
        # Bis zum 08.08.2026 galt das nur fuer die grossen Karten; die
        # kleinen ohne belegtes Bild waren "reine Textkarten, das ist die
        # Absicht". Gemessen an der Ausgabe vom 8.8. traf das 37 von 77
        # Karten, und weil eine Rasterzeile so hoch ist wie ihre hoechste
        # Karte, stand neben jedem Bild eine handbreite Luecke. Antonio:
        # "da fehlen bei einigen Aktionen die Bilder, das wirkt so richtig
        # scheisse." Die Absicht war falsch, das Kriterium hat sie gedeckt.
        karten = promo.select(".promo-karten .pkarte")
        ohne_motiv = [k for k in karten if not k.select_one(".pk-bild")]
        leere_kaesten = [kasten for kasten in promo.select(".pk-bild")
                         if not kasten.select_one("img")
                         and not kasten.get_text(strip=True)]
        b.prueft(bool(karten) and not ohne_motiv and not leere_kaesten,
                 f"8c. Karten ohne Motiv: {len(ohne_motiv)} von "
                 f"{len(karten)}, leere Bildkaesten: {len(leere_kaesten)}")

    # ---- Kriterium 9: die Differenzierungs-Seite zeigt Bilder, und JEDE
    # Karte traegt ein Motiv.
    #
    # Der Befund vom 08.08.2026: 77 Karten, null Bilder, 9060 px Seitenhoehe.
    # Antonio: "Es ist total unuebersichtlich, sich das anzugucken. Keine
    # Bilder, es ist schwer zu verstehen." Gemessen werden beide Haelften der
    # Antwort - die Ausbeute (haengt an fremden Seiten, deshalb eine Quote)
    # und die Luecke (haengt am Code, deshalb hart auf null).
    dz_datei = site / "differenzierung.html"
    if not dz_datei.exists():
        b.prueft(None, "9. Differenzierung (nicht gerendert)")
    else:
        dz = BeautifulSoup(dz_datei.read_text(encoding="utf-8"), "html.parser")
        # Die Zeilen sind die dritte Gewichtsstufe und tragen bewusst kein
        # Motiv - genau wie die Zeilen der Meldungsseite.
        karten = [k for k in dz.select(".dzk")
                  if "dzk--zeile" not in (k.get("class") or [])]
        mit_bild = [k for k in karten if k.select_one(".dzk-motiv img")]
        ohne_motiv = [k for k in karten if not k.select_one(".dzk-motiv")]
        leere_kaesten = [m for m in dz.select(".dzk-motiv")
                         if not m.select_one("img") and not m.get_text(strip=True)]
        quote = 100 * len(mit_bild) // max(1, len(karten))
        b.prueft(bool(karten) and quote >= _MIND_DIFF_BILDQUOTE
                 and not ohne_motiv and not leere_kaesten,
                 f"9. Differenzierung: {len(mit_bild)} von {len(karten)} Karten "
                 f"mit Bild ({quote} %, >= {_MIND_DIFF_BILDQUOTE} %), "
                 f"{len(ohne_motiv)} ohne Motiv, {len(leere_kaesten)} leere Kaesten")
        # 9b: die Auswertung steht VOR den Beispielen und nennt dieselben
        # Zahlen wie die Rubriken darunter - sonst hat die Seite zwei
        # Wahrheiten (der Fehlertyp vom 06.08.2026).
        marktbild = dz.select_one(".dz-marktbild")
        balken = {li.select_one(".dz-balken-name").get_text(strip=True):
                  int(li.select_one(".dz-balken-n").get_text(strip=True))
                  for li in (marktbild.select(".dz-mb-block")[0].select("li")
                             if marktbild else [])}
        falsch = []
        for abschnitt in dz.select(".dz-hebel"):
            label = abschnitt.select_one("h2").get_text(strip=True)
            if balken.get(label) != len(abschnitt.select(".dzk")):
                falsch.append(label)
        b.prueft(bool(balken) and not falsch,
                 f"9b. Marktbild gegen die Rubriken: {len(balken)} Hebel, "
                 f"{len(falsch)} widersprechen"
                 + (f" ({', '.join(falsch)})" if falsch else ""))

    # ---- Kriterium 11: die Kosten-Rangliste der Geraeteseite
    #
    # Die Seite ist EINE Frage: Geraet, Speicher, Tarifstufe und Raten
    # waehlen, je Anbieter die Kosten ueber 24 Monate sehen. Geprueft wird
    # die Struktur, die diese Frage traegt, und dass die Reiter-Seite nicht
    # zurueckkehrt. Ohne Ergebniszeile ist ein benannter Leerzustand Pflicht
    # (CLAUDE.md, Clean Code 5: Scheitern ist kein leeres Ergebnis).
    gr_datei = site / "geraete.html"
    if not gr_datei.exists():
        # KEIN "uebersprungen": render_site() erzeugt diese Seite immer,
        # notfalls mit ihrem Fehlerzustand. Fehlt sie ganz, ist etwas kaputt.
        b.prueft(False, "11. Geraeteseite: geraete.html fehlt ganz")
    else:
        gr = BeautifulSoup(gr_datei.read_text(encoding="utf-8"), "html.parser")
        maengel = []
        kosten = gr.select_one("#kosten")
        if kosten is None:
            maengel.append("section#kosten fehlt")
        for alt in _KV_ALTLASTEN:
            if gr.select_one(alt) is not None:
                maengel.append(f"Rest der Reiter-Seite: {alt}")

        zeilen = gr.select("#kosten .kv-zeile")
        if zeilen:
            wahl = gr.select_one("#kv-wahl")
            reihen = [r.get("data-wahl")
                      for r in gr.select("#kv-wahl .kv-reihe[data-wahl]")]
            if wahl is None:
                maengel.append("#kv-wahl fehlt")
            elif reihen != list(_KV_REIHEN):
                maengel.append(f"Auswahlreihen {reihen} statt {list(_KV_REIHEN)}")
            for r in gr.select("#kv-wahl .kv-reihe[data-wahl]"):
                gewaehlt = r.select('.kv-chip[aria-checked="true"]')
                if len(gewaehlt) != 1:
                    maengel.append(f"Reihe {r.get('data-wahl')}: "
                                   f"{len(gewaehlt)} gewaehlte Chips statt 1")
            if gr.select_one("select#kv-geraet") is None:
                maengel.append("select#kv-geraet fehlt (Geraetewahl am Telefon)")
            knoten = gr.select_one("script#kv-daten")
            if knoten is None:
                maengel.append("script#kv-daten fehlt")
            else:
                try:
                    daten = json.loads(knoten.string or "")
                except json.JSONDecodeError as exc:
                    maengel.append(f"#kv-daten nicht parsebar ({exc.msg})")
                else:
                    if not (daten.get("angebote") and daten.get("start")):
                        maengel.append("#kv-daten ohne Angebote oder "
                                       "Startauswahl")
            ohne_summe = [z for z in zeilen
                          if not ((s := z.select_one("summary.kv-kern .kv-summe"))
                                  and s.get_text(strip=True))]
            if ohne_summe:
                maengel.append(f"{len(ohne_summe)} Zeilen ohne Summe")
            b.prueft(not maengel,
                     f"11. Geraeteseite: {len(zeilen)} Ergebniszeilen, "
                     f"{len(reihen)} Auswahlreihen, Datenknoten gelesen"
                     if not maengel else
                     "11. Geraeteseite: " + "; ".join(maengel[:5]))
        else:
            nichts = gr.select_one("#kosten .kv-nichts")
            grund = nichts.get_text(" ", strip=True) if nichts else ""
            if not grund:
                maengel.append("keine Ergebniszeile und kein benannter "
                               "Leerzustand (.kv-nichts)")
            b.prueft(not maengel,
                     f"11. Geraeteseite: Leerzustand „{grund[:60]}“"
                     if not maengel else
                     "11. Geraeteseite: " + "; ".join(maengel[:5]))

        # ---- Kriterium 13: Fliesstext-Deckel (Messmenge am Kommentar zu
        # _FLIESSTEXT_DECKEL). Statisch am gerenderten HTML - dieselbe
        # Zaehlfunktion haelt tests/test_geraete_textdeckel.py fest.
        if kosten is not None:
            n = fliesstext_zeichen(kosten)
            b.prueft(n <= _FLIESSTEXT_DECKEL,
                     f"13. Fliesstext-Deckel: {n} Zeichen ausserhalb von "
                     f"Zahlen und Chips (max {_FLIESSTEXT_DECKEL})")

    _browser_messungen(site, b)

    print()
    return b.ausgeben()


if __name__ == "__main__":
    raise SystemExit(main())
