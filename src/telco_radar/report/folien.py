"""Foliensatz-Export: vom Wochenbericht zu vier Folien.

Warum das mehr bringt, als es kostet
------------------------------------
Der Nutzer braucht selten einen Text. Er braucht drei Folien fuer den
Montagstermin. Alles, was zwischen dem fertigen Bericht und dieser Folie
liegt, ist Handarbeit, die jede Woche neu anfaellt - und genau die faellt
hier weg.

Feste Vorlage, feste Platzhalter, NIE frei erzeugtes Layout
-----------------------------------------------------------
Das ist die zentrale Entscheidung. Ein Modell, das Folien "gestaltet",
erzeugt jede Woche ein anderes Deck: mal drei Spalten, mal ein Zitat, mal
eine Tabelle, die unten aus der Folie laeuft. Eine Folie ist 1080 px hoch
und scrollt nicht.

Hier gibt es vier Folien mit festen Plaetzen. Der Text wird eingesetzt, nicht
angeordnet. Was nicht passt, wird GEKUERZT - nicht durchgereicht und nicht
kleiner gesetzt.

Die Zeichengrenzen sind keine Schaetzung: sie stehen in der Design-Spezifikation
des Vodafone-Decks (Abschnitt "Inhaltsbudgets", dort als haeufigste
Korrekturursache benannt) und werden hier im Code erzwungen und im Test
geprueft.

Die Quellenfolie ist Pflicht
----------------------------
Sie laesst sich nicht abschalten. Das ganze Projekt haengt an der
Nachpruefbarkeit jeder Aussage - ein Deck, das die Belege weglaesst, weil
es huebscher aussieht, ist genau das Gegenteil davon. `baue()` hat keinen
Schalter dafuer, und ein Test haelt das fest.
"""
from __future__ import annotations

import html as _html
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Die Budgets. Aus DESIGN_SPEC.md, Abschnitt 11 (Inhaltsbudgets).
# --------------------------------------------------------------------------- #
MAX_TITEL = 68           # Cover-Titel, 2 Zeilen bei 120 px
MAX_KICKER = 42          # Cover-Kicker, UPPERCASE, eine Zeile
MAX_HEADLINE = 62        # Content-Headline, 60 px, hoechstens 2 Zeilen
MAX_PUNKT = 80           # Listenpunkt, eine Zeile
MAX_PUNKTE = 3           # "Was passiert ist" hat drei Punkte
MAX_LEDE = 240           # Fliesstext/Lede je Block
MAX_KONSEQUENZEN = 3
MAX_QUELLEN = 12         # mehr passen nicht auf eine Folie
MAX_QUELLE_TEXT = 84


def kuerze(text: str, grenze: int) -> str:
    """Auf die Grenze kuerzen - an der Wortgrenze, mit Auslassungszeichen.

    Modelltext, der ueberlaeuft, wird NICHT durchgereicht. Eine Folie
    scrollt nicht; ein Satz, der unten herausragt, ist im Termin
    unbrauchbar, und niemand merkt es vor dem Termin.
    """
    s = " ".join(str(text or "").split())
    if len(s) <= grenze:
        return s
    schnitt = s[:grenze - 1]
    if " " in schnitt:
        schnitt = schnitt[:schnitt.rfind(" ")]
    return schnitt.rstrip(" ,;:.–-") + "…"


def _e(text: str) -> str:
    return _html.escape(str(text or ""), quote=True)


def _akzent(headline: str) -> str:
    """Genau EIN rotes Schluesselwort je Headline (Design-Spezifikation).

    Genommen wird das laengste Wort - es traegt in aller Regel die Aussage
    ("Wechselbonus", "Datenvolumen", "Preiserhoehung"). Das ist eine
    Faustregel und ausdruecklich keine Bedeutungsanalyse; sie ist nur besser
    als gar kein Akzent und besser als drei.
    """
    sicher = _e(headline)
    woerter = re.findall(r"[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß-]{5,}", headline or "")
    if not woerter:
        return sicher
    laengstes = max(woerter, key=len)
    return sicher.replace(
        _e(laengstes), f'<span class="accent">{_e(laengstes)}</span>', 1)


@dataclass
class Folienquelle:
    text: str
    url: str


@dataclass
class Foliensatz:
    """Der fertige Inhalt, bevor er HTML wird. Getrennt, damit die
    Zeichengrenzen ohne HTML-Parsen pruefbar sind."""

    titel: str = ""
    kicker: str = ""
    datum: str = ""
    was_passiert: list[str] = field(default_factory=list)
    was_heisst_das: list[str] = field(default_factory=list)
    quellen: list[Folienquelle] = field(default_factory=list)

    def ueberlaeufe(self) -> list[str]:
        """Platzhalter, die ihr Budget reissen. Muss immer leer sein."""
        offen = []
        if len(self.titel) > MAX_TITEL:
            offen.append("titel")
        if len(self.kicker) > MAX_KICKER:
            offen.append("kicker")
        if len(self.was_passiert) > MAX_PUNKTE:
            offen.append("was_passiert (Anzahl)")
        if len(self.was_heisst_das) > MAX_KONSEQUENZEN:
            offen.append("was_heisst_das (Anzahl)")
        if len(self.quellen) > MAX_QUELLEN:
            offen.append("quellen (Anzahl)")
        offen += [f"punkt {i}" for i, p in enumerate(self.was_passiert)
                  if len(p) > MAX_PUNKT]
        offen += [f"konsequenz {i}" for i, k in enumerate(self.was_heisst_das)
                  if len(k) > MAX_LEDE]
        offen += [f"quelle {i}" for i, q in enumerate(self.quellen)
                  if len(q.text) > MAX_QUELLE_TEXT]
        return offen


def _highlights(report: dict) -> list[dict]:
    """Alle Meldungen des Berichts, nach Relevanz und CTM-Bezug sortiert."""
    alle: list[dict] = []
    regionen = report.get("regions") or {}
    if isinstance(regionen, dict):
        for inhalt in regionen.values():
            alle.extend((inhalt or {}).get("highlights") or [])
    elif isinstance(regionen, list):
        for inhalt in regionen:
            alle.extend((inhalt or {}).get("highlights") or [])

    def rang(h: dict) -> tuple:
        def zahl(wert) -> int:
            try:
                return int(wert)
            except (TypeError, ValueError):
                return 0
        return (-zahl(h.get("ctm_bezug")), -zahl(h.get("relevance")))

    return sorted(alle, key=rang)


def inhalt(report: dict, *, titel: str = "") -> Foliensatz:
    """Aus dem Bericht die vier Folien fuellen - gekuerzt, nie ueberlaufend."""
    datum = str(report.get("date") or "")
    meldungen = _highlights(report)

    satz = Foliensatz(
        titel=kuerze(titel or "Was diese Woche im Markt passiert ist",
                     MAX_TITEL),
        kicker=kuerze("Telco Radar · Wochenbericht", MAX_KICKER),
        datum=datum,
    )

    for h in meldungen[:MAX_PUNKTE]:
        zeile = h.get("headline") or h.get("title") or ""
        if zeile:
            satz.was_passiert.append(kuerze(zeile, MAX_PUNKT))

    # "Was das fuer uns heisst" kommt aus dem geprueften CTM-Satz, wenn es
    # einen gibt - er ist bereits gegen den Originaltext geprueft
    # (analyze/faithfulness.py). Sonst aus `why_it_matters`. Erfunden wird
    # hier nichts: gibt es beides nicht, bleibt die Folie kurz.
    for h in meldungen:
        if len(satz.was_heisst_das) >= MAX_KONSEQUENZEN:
            break
        text = (h.get("ctm_satz") or h.get("why_it_matters") or "").strip()
        if text:
            satz.was_heisst_das.append(kuerze(text, MAX_LEDE))

    gesehen: set[str] = set()
    for h in meldungen:
        if len(satz.quellen) >= MAX_QUELLEN:
            break
        url = (h.get("url") or "").strip()
        if not url or url in gesehen:
            continue
        gesehen.add(url)
        beschriftung = (h.get("source") or h.get("operator")
                        or h.get("headline") or url)
        satz.quellen.append(Folienquelle(
            text=kuerze(f"{beschriftung}: {h.get('headline') or h.get('title') or ''}",
                        MAX_QUELLE_TEXT),
            url=url))
    return satz


# --------------------------------------------------------------------------- #
# Die feste Vorlage
# --------------------------------------------------------------------------- #

_KOPF = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{titel}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
  :root {{
    --vf-red:#e60000; --vf-red-deep:#ac1811; --vf-ink:#25282b;
    --vf-mute:#7e7e7e; --vf-canvas:#ffffff; --vf-neutral:#f2f2f2;
    --font-display:'Inter','Helvetica Neue',Arial,sans-serif;
    --slide-w:1920px; --slide-h:1080px;
    --ease:cubic-bezier(0.22,1,0.36,1);
  }}
  *,*::before,*::after{{box-sizing:border-box}}
  html,body{{margin:0;padding:0;width:100%;height:100%;overflow:hidden}}
  body{{background:var(--vf-canvas);color:var(--vf-ink);
    font-family:var(--font-display);font-size:22px}}
  .deck{{position:fixed;inset:0;background:var(--vf-canvas);overflow:hidden}}
  .stage{{position:absolute;width:var(--slide-w);height:var(--slide-h);
    transform-origin:0 0;background:var(--vf-canvas);overflow:hidden}}
  .slide{{position:absolute;inset:0;padding:120px;background:var(--vf-canvas);
    opacity:0;visibility:hidden;transition:opacity 420ms var(--ease);
    display:flex;flex-direction:column;justify-content:center}}
  .slide.active{{opacity:1;visibility:visible}}
  .kicker{{font-size:18px;font-weight:600;letter-spacing:.18em;
    text-transform:uppercase;color:var(--vf-mute);margin:0 0 28px}}
  .cover-title{{font-size:104px;font-weight:800;letter-spacing:-.018em;
    line-height:1.02;margin:0;max-width:1500px}}
  .cover-date{{font-size:20px;color:var(--vf-mute);margin:38px 0 0;
    letter-spacing:.06em}}
  .headline{{font-size:60px;font-weight:800;letter-spacing:-.015em;
    line-height:1.05;margin:0 0 56px;max-width:1500px}}
  .accent{{color:var(--vf-red)}}
  .checklist{{list-style:none;padding:0;margin:0;max-width:1500px}}
  .checklist li{{font-size:30px;font-weight:500;line-height:1.4;
    padding:0 0 26px 52px;position:relative}}
  .checklist li::before{{content:"";position:absolute;left:0;top:16px;
    width:26px;height:3px;background:var(--vf-red)}}
  .lede{{font-size:30px;font-weight:500;line-height:1.4;margin:0 0 26px;
    max-width:1400px}}
  .quellen{{list-style:none;padding:0;margin:0;columns:2;column-gap:70px}}
  .quellen li{{font-size:17px;line-height:1.45;color:var(--vf-ink);
    margin:0 0 15px;break-inside:avoid}}
  .quellen a{{color:var(--vf-mute);text-decoration:none;display:block;
    font-size:14px;word-break:break-all}}
  .fussnote{{font-size:13px;letter-spacing:.06em;text-transform:uppercase;
    color:var(--vf-mute);margin:44px 0 0}}
  .footer{{position:absolute;left:120px;right:120px;bottom:56px;
    display:flex;justify-content:space-between;font-size:14px;
    letter-spacing:.08em;text-transform:uppercase;color:var(--vf-mute)}}
  .progress{{position:fixed;left:0;top:0;height:3px;background:var(--vf-red);
    width:0;transition:width 300ms var(--ease);z-index:9}}
</style>
</head>
<body>
<div class="progress" id="progress"></div>
<div class="deck"><div class="stage" id="stage">
"""

_FUSS = """</div></div>
<script>
(function () {
  var stage = document.getElementById('stage');
  var slides = Array.prototype.slice.call(document.querySelectorAll('.slide'));
  var progress = document.getElementById('progress');
  var current = 0, total = slides.length;
  function fitStage() {
    var vw = window.innerWidth, vh = window.innerHeight;
    var scale = Math.min(vw / 1920, vh / 1080);
    stage.style.left = ((vw - 1920 * scale) / 2) + 'px';
    stage.style.top = ((vh - 1080 * scale) / 2) + 'px';
    stage.style.transform = 'scale(' + scale + ')';
  }
  function show(i) {
    if (i < 0) i = 0;
    if (i > total - 1) i = total - 1;
    slides.forEach(function (s, idx) { s.classList.toggle('active', idx === i); });
    current = i;
    progress.style.width = ((i + 1) / total * 100) + '%';
  }
  document.addEventListener('keydown', function (e) {
    if (e.key === 'ArrowRight' || e.key === ' ') show(current + 1);
    if (e.key === 'ArrowLeft') show(current - 1);
  });
  document.addEventListener('click', function (e) {
    show(current + (e.clientX < window.innerWidth / 3 ? -1 : 1));
  });
  window.addEventListener('resize', fitStage);
  fitStage(); show(0);
})();
</script>
</body>
</html>
"""


def _folie(nummer: int, gesamt: int, inhalt_html: str, datum: str) -> str:
    return (
        f'<section class="slide" data-slide="{nummer}">\n{inhalt_html}\n'
        f'  <div class="footer"><span>Telco Radar{" · " + _e(datum) if datum else ""}</span>'
        f'<span>{nummer:02d} / {gesamt:02d}</span></div>\n</section>\n'
    )


def baue(report: dict, *, titel: str = "") -> str:
    """Der fertige Foliensatz als EINE HTML-Datei.

    Es gibt keinen Schalter, der die Quellenfolie weglaesst. Das ist
    Absicht - siehe Modul-Docstring.
    """
    satz = inhalt(report, titel=titel)
    ueber = satz.ueberlaeufe()
    if ueber:  # pragma: no cover - kuerze() schliesst das aus, aber Vertrauen
        # ist keine Zusicherung: lieber hart abbrechen als eine Folie
        # ausliefern, die im Termin unten herauslaeuft.
        raise ValueError("Platzhalter ueber Budget: " + ", ".join(ueber))

    gesamt = 4
    teile = [_KOPF.format(titel=_e(satz.titel))]

    # 1 Cover
    teile.append(_folie(1, gesamt,
        f'  <p class="kicker">{_e(satz.kicker)}</p>\n'
        f'  <h1 class="cover-title">{_akzent(satz.titel)}</h1>\n'
        + (f'  <p class="cover-date">Stand {_e(satz.datum)}</p>\n'
           if satz.datum else ""), satz.datum))

    # 2 Was passiert ist
    punkte = "".join(f"    <li>{_e(p)}</li>\n" for p in satz.was_passiert)
    teile.append(_folie(2, gesamt,
        f'  <h2 class="headline">{_akzent("Was diese Woche passiert ist")}</h2>\n'
        f'  <ul class="checklist">\n{punkte}  </ul>\n', satz.datum))

    # 3 Was das fuer uns heisst
    if satz.was_heisst_das:
        saetze = "".join(f'  <p class="lede">{_e(k)}</p>\n'
                         for k in satz.was_heisst_das)
    else:
        saetze = ('  <p class="lede">Zu dieser Ausgabe liegt keine geprüfte '
                  'Einordnung vor.</p>\n')
    teile.append(_folie(3, gesamt,
        f'  <h2 class="headline">{_akzent("Was das für uns bedeutet")}</h2>\n'
        + saetze, satz.datum))

    # 4 Quellen - Pflicht.
    zeilen = "".join(
        f'    <li>{_e(q.text)}<a href="{_e(q.url)}">{_e(q.url)}</a></li>\n'
        for q in satz.quellen)
    teile.append(_folie(4, gesamt,
        f'  <h2 class="headline">{_akzent("Quellen zum Nachlesen")}</h2>\n'
        f'  <ul class="quellen">\n{zeilen}  </ul>\n'
        f'  <p class="fussnote">Jede Aussage dieses Foliensatzes steht in '
        f'einer der oben verlinkten Quellen.</p>\n', satz.datum))

    teile.append(_FUSS)
    return "".join(teile)
