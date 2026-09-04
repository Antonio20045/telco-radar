"""Die zwei Pflicht-Grafiken der Geraeteseite, servergerendert als SVG.

Warum servergerendert und ohne Bibliothek
-----------------------------------------
Die Website ist eine Render-Static-Site ohne Backend und ohne CDN-JS. Eine
Chart-Bibliothek waere ein drittes fremdes Skript auf einer Seite, die
heute mit `app.js` auskommt - und eine Grafik, die erst im Browser
entsteht, steht in keinem `curl`, in keinem Test und in keinem Screenshot.
Beide Grafiken hier stehen fertig im HTML.

Die drei Regeln, die dieses Modul tragen
----------------------------------------
1. **Hier wird keine Kennzahl gerechnet.** Die Betraege kommen aus
   `tco_model` ueber `geraete_tco_karten`; dieses Modul rechnet
   ausschliesslich Geometrie. Zwei Rechnungen fuer dieselbe Zahl sind zwei
   Zahlen (CLAUDE.md § 6).
2. **Zwei Laufzeiten, zwei Nulllinien** (A5.4). Ein gemeinsamer Balkenrang
   ueber 24 und 36 Monate vergliche die Laufzeit und nennte es Preis.
3. **Jeder Balken traegt seine Aussage im `<title>`.** Eine Grafik ohne
   Textfassung ist auf einem Screenreader eine leere Flaeche - und beim
   Nachmessen eine Behauptung ohne Beleg.

Was die Grafik NICHT tut
------------------------
Sie zeichnet keine Karte ohne belastbare Zahl. Ein Balken der Laenge null
mit einem Anbieternamen davor sieht aus wie "kostenlos"; der Leerzustand
gehoert in die Karte, wo sein Grund danebensteht.
"""
from __future__ import annotations

from datetime import date
from typing import Optional
from xml.sax.saxutils import escape

# Die Zeichenflaeche. 1180 px ist die Breite, die die Seite hergibt
# (1184 px Satzspiegel) - dieselbe Zahl wie bei der geloeschten
# Positionskarte, und aus demselben Grund gemessen statt geraten.
BREITE = 1180
# Die linke Spalte traegt Anbieter UND Tarifnamen. 300 px, weil der
# laengste Tarif des Bestands ("O2 Mobile on Demand M Plus mit 50 GB+
# (24 Mon.)", 47 Zeichen) bei 10,5 px Schriftgroesse rund 245 px misst.
# Ein Etikett, das nicht passt, wuerde sonst abgeschnitten - und eine
# abgeschnittene Beschriftung ist auf dieser Seite ein Mangel, kein
# Kompromiss.
LINKS = 300
RAND_RECHTS = 30
BALKEN_HOEHE = 26
BALKEN_ABSTAND = 16
GRUPPE_KOPF = 34
GRUPPE_ABSTAND = 18
ACHSE_HOEHE = 26

# Die Deckkraft je Kostenart. Die FARBE gehoert dem Anbieter (CSS-Klasse
# `gr-anb--<slug>`, dieselbe auf Karten, Balken und in der Legende); die
# Kostenart unterscheidet sich in der Deckkraft. So bleibt die
# Anbieterfarbe ueber alle Grafiken und Tabellen der Seite konsistent
# (C.3), ohne dass jede Kombination eine eigene Farbe braucht.
DECKKRAFT = {"einmalig": 1.0, "tarif": 0.62, "raten": 0.34,
             "buendel": 0.5, "bonus": 0.18}

KATEGORIE_NAME = {"einmalig": "einmalig", "tarif": "Tarif",
                  "raten": "Geräteraten", "buendel": "Tarif und Gerät",
                  "bonus": "Bonus"}


def anbieter_slug(anbieter: str) -> str:
    """`1&1` -> `1-1`. Der Slug traegt die Farbe, nicht der Name."""
    erlaubt = [z if (z.isalnum()) else "-" for z in (anbieter or "").lower()]
    return "".join(erlaubt).strip("-") or "ohne"


def euro(betrag: Optional[float]) -> str:
    """Deutsche Schreibweise mit Tausenderpunkt - wie im Rest des Portals."""
    if betrag is None:
        return "–"
    return f"{betrag:,.2f}".replace(",", "#").replace(".", ",") \
        .replace("#", ".") + " €"


def _t(text) -> str:
    return escape(str(text))


# --------------------------------------------------------------------------
# G1 - der TCO-Vergleich
# --------------------------------------------------------------------------

def _gruppen(karten: list) -> list:
    """Die Karten nach Bindungsdauer, laengste Gruppe zuerst gefuellt.

    Eine Gruppe entsteht nur, wenn sie eine belastbare Zahl hat - eine
    Ueberschrift "24 Monate" ueber einer leeren Flaeche ist keine Auskunft.
    """
    nach_laufzeit: dict = {}
    for k in karten:
        if not k.get("belastbar") or k.get("gesamt") is None:
            continue
        nach_laufzeit.setdefault(k["laufzeit"], []).append(k)
    gruppen = []
    for laufzeit in sorted(nach_laufzeit):
        zeilen = sorted(nach_laufzeit[laufzeit],
                        key=lambda k: k["gesamt"])
        gruppen.append({"laufzeit": laufzeit, "karten": zeilen})
    return gruppen


def _skala(betrag: float, hoechst: float) -> float:
    breite = BREITE - LINKS - RAND_RECHTS
    if hoechst <= 0:
        return 0.0
    return round(betrag / hoechst * breite, 1)


def balken(modell: dict) -> str:
    """G1: gestapelte Balken je Anbieter, getrennt nach Laufzeit.

    Rueckgabe ist fertiges SVG-Markup oder ein leerer String - dann zeigt
    die Vorlage ihre Texttafel (C.1: "Wenn <2 Anbieter mit gueltigem TCO:
    Texttafel statt Fake-Grafik").
    """
    gruppen = _gruppen(modell.get("karten") or [])
    zeilen_gesamt = sum(len(g["karten"]) for g in gruppen)
    if zeilen_gesamt < 2:
        return ""

    # Gemessen wird der GEZEICHNETE Balken, nicht die Leitzahl: ein Bonus
    # wird als abgezogenes Stueck AN das Balkenende gezeichnet, der Stapel
    # ist also so lang wie die Summe seiner positiven Posten. Gegen
    # `gesamt` skaliert liefe ein Angebot mit hohem Bonus aus dem Bild.
    hoechst = max(sum(max(0.0, p.get("betrag") or 0.0)
                      for p in (k.get("bestandteile") or []))
                  for g in gruppen for k in g["karten"])
    # Ein bisschen Luft rechts, damit der Betrag hinter dem laengsten
    # Balken noch Platz hat.
    hoechst = hoechst * 1.18
    referenz = modell.get("referenz")

    hoehe = ACHSE_HOEHE
    for g in gruppen:
        hoehe += GRUPPE_KOPF + len(g["karten"]) * (BALKEN_HOEHE
                                                   + BALKEN_ABSTAND)
        hoehe += GRUPPE_ABSTAND
    hoehe = int(hoehe)

    name = modell.get("name") or ""
    teile = [
        f'<svg class="gr-g1" viewBox="0 0 {BREITE} {hoehe}" '
        f'width="100%" height="{hoehe}" role="img" '
        f'aria-label="Gesamtkosten für {_t(name)} je Anbieter, '
        f'nach Bindungsdauer getrennt">',
        f'<title>Gesamtkosten für {_t(name)} je Anbieter</title>',
    ]

    y = 0.0
    for gruppe in gruppen:
        laufzeit = gruppe["laufzeit"]
        teile.append(
            f'<text class="gr-g1-gruppe" x="0" y="{y + 20:.0f}">'
            f'{laufzeit} Monate Bindung</text>')
        # Die eigene Nulllinie der Gruppe (A5.4).
        oben = y + GRUPPE_KOPF - 6
        unten = oben + len(gruppe["karten"]) * (BALKEN_HOEHE
                                                + BALKEN_ABSTAND)
        teile.append(f'<line class="gr-g1-null" x1="{LINKS}" y1="{oben:.0f}" '
                     f'x2="{LINKS}" y2="{unten:.0f}" />')
        y += GRUPPE_KOPF

        # Die Referenzlinie - nur in der Gruppe, deren Laufzeit sie rechnet.
        if referenz and referenz.get("monate") == laufzeit:
            x = LINKS + _skala(referenz["gesamt"], hoechst)
            teile.append(
                f'<line class="gr-g1-ref" x1="{x:.1f}" y1="{y - 8:.0f}" '
                f'x2="{x:.1f}" y2="{unten:.0f}" />'
                f'<text class="gr-g1-reftext" x="{x + 5:.1f}" '
                f'y="{y - 12:.0f}">Vodafone-Referenz '
                f'{_t(euro(referenz["gesamt"]))}</text>')

        for karte in gruppe["karten"]:
            slug = anbieter_slug(karte["anbieter"])
            teile.append(
                f'<text class="gr-g1-anbieter" x="0" y="{y + 13:.0f}">'
                f'{_t(karte["anbieter"])}'
                + (' <tspan class="gr-g1-ref-etikett">Referenz</tspan>'
                   if karte.get("naeherung") else '')
                + '</text>'
                f'<text class="gr-g1-tarif" x="0" y="{y + 25:.0f}">'
                f'{_t(karte["tarif"])}</text>')
            x = float(LINKS)
            for posten in karte.get("bestandteile") or []:
                betrag = posten.get("betrag") or 0.0
                if betrag <= 0:
                    # Ein Bonus ist negativ und wird als eigener Balken
                    # UNTER der Nulllinie gezeichnet - nicht als Luecke im
                    # Stapel, wo er wie ein fehlender Posten aussaehe.
                    continue
                breite = _skala(betrag, hoechst)
                if breite <= 0:
                    continue
                kat = posten.get("kategorie") or "tarif"
                teile.append(
                    f'<rect class="gr-g1-seg gr-anb--{slug}" x="{x:.1f}" '
                    f'y="{y:.0f}" width="{breite:.1f}" '
                    f'height="{BALKEN_HOEHE}" '
                    f'fill-opacity="{DECKKRAFT.get(kat, 0.6)}">'
                    f'<title>{_t(karte["anbieter"])}: '
                    f'{_t(posten.get("name") or KATEGORIE_NAME.get(kat, kat))} '
                    f'{_t(euro(betrag))}</title></rect>')
                x += breite
            for bonus in karte.get("boni") or []:
                breite = _skala(bonus["betrag"], hoechst)
                x -= breite
                teile.append(
                    f'<rect class="gr-g1-bonus" x="{x:.1f}" y="{y:.0f}" '
                    f'width="{breite:.1f}" height="{BALKEN_HOEHE}">'
                    f'<title>Bonus {_t(bonus["name"])} '
                    f'−{_t(euro(bonus["betrag"]))}</title></rect>')
            teile.append(
                f'<text class="gr-g1-betrag" x="{x + 8:.1f}" '
                f'y="{y + 18:.0f}">{_t(euro(karte["gesamt"]))}</text>')
            y += BALKEN_HOEHE + BALKEN_ABSTAND
        y += GRUPPE_ABSTAND

    teile.append('</svg>')
    return "".join(teile)


def legende(modell: dict) -> list:
    """Was in der Grafik steht, als Text daneben - C.3: die Tabelle ist die
    Quelle der Wahrheit, die Grafik ihre Ansicht."""
    arten = []
    gesehen = set()
    for karte in modell.get("karten") or []:
        if not karte.get("belastbar"):
            continue
        for posten in karte.get("bestandteile") or []:
            kat = posten.get("kategorie")
            if kat and kat not in gesehen and (posten.get("betrag") or 0) > 0:
                gesehen.add(kat)
                arten.append({"kategorie": kat,
                              "name": KATEGORIE_NAME.get(kat, kat),
                              "deckkraft": DECKKRAFT.get(kat, 0.6)})
    return arten


# --------------------------------------------------------------------------
# G2 - die Preishistorie
# --------------------------------------------------------------------------

G2_BREITE = 1180
G2_HOEHE = 300
G2_LINKS = 76
G2_UNTEN = 34
G2_OBEN = 16
G2_RECHTS = 210

# Unter zwei Messpunkten gibt es keine Linie - und keine erfundene.
# Dieselbe Schwelle wie im Preisverlauf-Reiter: zwei Punkte ergeben eine
# Gerade, und eine Gerade durch zwei Punkte sieht aus wie ein Trend.
MIND_PUNKTE = 2
# Hoechstens so viele Reihen in einem Bild. Mehr Linien in einem
# Euro-Massstab sind ein Knaeuel, kein Verlauf.
MAX_REIHEN = 5


def _tag(text: str) -> Optional[date]:
    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def historie(reihen: list) -> dict:
    """G2: Preisverlauf je Modell x Anbieter, mit Ereignismarkern.

    `reihen` ist eine Liste von
    `{"name","anbieter","punkte":[{"datum","betrag"}],"quelle_url"}`.

    Rueckgabe traegt `svg` (leer, wenn es nichts zu zeichnen gibt),
    `tabelle` (dieselben Zahlen als Text - C.2 verlangt sie ausdruecklich
    fuer Mobilgeraete und Screenreader) und `ereignisse`.
    """
    brauchbar = [r for r in reihen if len(r.get("punkte") or []) >= MIND_PUNKTE]
    brauchbar.sort(key=lambda r: (-len(r["punkte"]), r["name"]))
    brauchbar = brauchbar[:MAX_REIHEN]
    if not brauchbar:
        return {"svg": "", "tabelle": [], "ereignisse": [], "reihen": 0}

    punkte_alle = [(_tag(p["datum"]), float(p["betrag"]))
                   for r in brauchbar for p in r["punkte"]
                   if _tag(p["datum"]) is not None]
    if len(punkte_alle) < MIND_PUNKTE:
        return {"svg": "", "tabelle": [], "ereignisse": [], "reihen": 0}

    tage = [t for t, _ in punkte_alle]
    betraege = [b for _, b in punkte_alle]
    von, bis = min(tage), max(tage)
    spanne_tage = max(1, (bis - von).days)
    tief, hoch = min(betraege), max(betraege)
    if hoch <= tief:
        hoch = tief + 1.0
    # Etwas Luft nach oben und unten, damit ein Punkt nicht auf der Achse
    # klebt.
    polster = (hoch - tief) * 0.12
    tief, hoch = tief - polster, hoch + polster

    def x(tag: date) -> float:
        breite = G2_BREITE - G2_LINKS - G2_RECHTS
        return round(G2_LINKS + (tag - von).days / spanne_tage * breite, 1)

    def y(betrag: float) -> float:
        hoehe = G2_HOEHE - G2_OBEN - G2_UNTEN
        return round(G2_HOEHE - G2_UNTEN
                     - (betrag - tief) / (hoch - tief) * hoehe, 1)

    teile = [
        f'<svg class="gr-g2" viewBox="0 0 {G2_BREITE} {G2_HOEHE}" '
        f'width="100%" height="{G2_HOEHE}" role="img" '
        f'aria-label="Preisverlauf von {_t(von.isoformat())} bis '
        f'{_t(bis.isoformat())} für {len(brauchbar)} Reihen">',
        f'<title>Preisverlauf, {len(brauchbar)} Reihen, '
        f'{_t(von.isoformat())} bis {_t(bis.isoformat())}</title>',
    ]

    # Y-Achse: fuenf Marken. Zwei Nachkommastellen nur, wenn zwei Marken
    # sonst gleich hiessen - dieselbe Regel wie im Preisverlauf-Reiter.
    marken = [tief + (hoch - tief) * i / 4 for i in range(5)]
    genau = len({f"{m:.0f}" for m in marken}) < len(marken)
    for marke in marken:
        yy = y(marke)
        # Zwei Nachkommastellen NUR, wenn zwei Marken sonst gleich hiessen -
        # sonst stuende fuenfmal "900 EUR" an einer Achse, deren Spanne
        # zwanzig Cent betraegt (Befund vom 30.08.2026). Ohne
        # Tausenderpunkt, damit `parseFloat` im Abnahmetest die Marke liest.
        beschriftung = (f"{marke:.2f}".replace(".", ",") if genau
                        else f"{marke:.0f}")
        teile.append(f'<line class="gr-g2-raster" x1="{G2_LINKS}" y1="{yy}" '
                     f'x2="{G2_BREITE - G2_RECHTS}" y2="{yy}" />'
                     f'<text class="gr-g2-achse" x="{G2_LINKS - 8}" '
                     f'y="{yy + 4}" text-anchor="end">{beschriftung} €</text>')

    # X-Achse: erster und letzter Tag, dazu die Mitte.
    for tag in sorted({von, bis}):
        teile.append(f'<text class="gr-g2-achse" x="{x(tag)}" '
                     f'y="{G2_HOEHE - 12}" text-anchor="middle">'
                     f'{tag.strftime("%d.%m.")}</text>')

    tabelle, ereignisse = [], []
    for nr, reihe in enumerate(brauchbar):
        slug = anbieter_slug(reihe["anbieter"])
        punkte = sorted(
            [(t, b) for t, b in ((_tag(p["datum"]), float(p["betrag"]))
                                 for p in reihe["punkte"]) if t is not None])
        pfad = " ".join(f"{'M' if i == 0 else 'L'}{x(t)} {y(b)}"
                        for i, (t, b) in enumerate(punkte))
        teile.append(f'<path class="gr-g2-linie gr-anb--{slug}" d="{pfad}" '
                     f'fill="none" />')
        vorher = None
        for t, b in punkte:
            klasse = "gr-g2-punkt"
            titel = f'{reihe["name"]} · {reihe["anbieter"]} · ' \
                    f'{t.strftime("%d.%m.%Y")}: {euro(b)}'
            if vorher is not None and abs(b - vorher) >= 0.01:
                richtung = "hoch" if b > vorher else "runter"
                klasse += f" gr-g2-punkt--{richtung}"
                delta = round(b - vorher, 2)
                zeichen = "+" if delta > 0 else "−"
                titel += f' ({zeichen}{euro(abs(delta))} gegenüber ' \
                         f'dem letzten Messpunkt)'
                ereignisse.append({
                    "name": reihe["name"], "anbieter": reihe["anbieter"],
                    "datum": t.isoformat(), "betrag": b, "delta": delta,
                    "richtung": richtung, "quelle_url": reihe.get("quelle_url", "")})
                teile.append(
                    f'<text class="gr-g2-marker" x="{x(t)}" '
                    f'y="{y(b) - 10}" text-anchor="middle">'
                    f'{"↑" if delta > 0 else "↓"}</text>')
            teile.append(f'<circle class="{klasse} gr-anb--{slug}" '
                         f'cx="{x(t)}" cy="{y(b)}" r="4">'
                         f'<title>{_t(titel)}</title></circle>')
            vorher = b
        # Die Legende steht rechts NEBEN dem Bild, nicht darunter: eine
        # Legende unter der Grafik zwingt auf dem Telefon zum Querscrollen.
        teile.append(
            f'<text class="gr-g2-legende gr-anb--{slug}" '
            f'x="{G2_BREITE - G2_RECHTS + 12}" y="{22 + nr * 20}">'
            f'{_t(reihe["name"])} · {_t(reihe["anbieter"])}</text>')
        tabelle.append({
            "name": reihe["name"], "anbieter": reihe["anbieter"],
            "quelle_url": reihe.get("quelle_url", ""),
            "punkte": [{"datum": t.isoformat(), "betrag": b}
                       for t, b in punkte],
            "von": punkte[0][1], "bis": punkte[-1][1],
            "delta": round(punkte[-1][1] - punkte[0][1], 2),
        })

    teile.append('</svg>')
    ereignisse.sort(key=lambda e: (e["datum"], e["name"]), reverse=True)
    return {"svg": "".join(teile), "tabelle": tabelle,
            "ereignisse": ereignisse, "reihen": len(brauchbar),
            "von": von.isoformat(), "bis": bis.isoformat()}
