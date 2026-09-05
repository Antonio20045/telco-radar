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

from datetime import date, timedelta
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
        f'aria-label="TCO für {_t(name)} je Anbieter, '
        f'nach Bindungsdauer getrennt">',
        f'<title>TCO für {_t(name)} je Anbieter</title>',
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
            # DAS ETIKETT KIPPT NACH LINKS, wenn es sonst aus dem Bild
            # liefe. Die Referenz ist regelmaessig der teuerste Balken -
            # rechtsbuendig gesetzt stand "Vodafone-Referenz 2.278,10 €"
            # zur Haelfte ausserhalb der Zeichenflaeche. Eine Beschriftung,
            # die nicht ganz da ist, ist keine.
            # UND SIE SAGT, WORAUS SIE BESTEHT, wo ihre Bindung nicht die
            # der Gruppe ist (F-R2-2): die Linie steht in der 36-Monats-
            # Gruppe, gerechnet sind Barkauf plus 24 Tarifmonate. Ohne den
            # Zusatz liest sich "Vodafone-Referenz 1.428,70 EUR" unter dem
            # Kopf "36 Monate Bindung" als 36-Monats-Zahl.
            tarif_monate = referenz.get("tarif_monate")
            text = f'Vodafone-Referenz {euro(referenz["gesamt"])}'
            if (tarif_monate and tarif_monate != laufzeit
                    and referenz.get("geraet_betrag") is not None):
                text += f' · Barkauf + {tarif_monate} Monate Tarif'
            # ~6,6 px je Zeichen bei 12 px Grotesk - grosszuegig gerundet,
            # damit der Kipp-Punkt eher zu frueh als zu spaet greift.
            rechts = x + 5 + int(len(text) * 6.6) > BREITE
            teile.append(
                f'<line class="gr-g1-ref" x1="{x:.1f}" y1="{y - 8:.0f}" '
                f'x2="{x:.1f}" y2="{unten:.0f}" />'
                f'<text class="gr-g1-reftext" x="{x - 5 if rechts else x + 5:.1f}" '
                f'y="{y - 12:.0f}"'
                + (' text-anchor="end"' if rechts else '')
                + f'>{_t(text)}</text>')

        for karte in gruppe["karten"]:
            slug = anbieter_slug(karte["anbieter"])
            # DAS ZUSTANDSETIKETT STEHT AM BALKEN, nicht nur an der Karte:
            # der Balken wird fuer sich gelesen, und ein unbeschrifteter
            # kurzer Balken eines erneuerten Geraets liest sich als das
            # guenstigste Angebot (QA-Befund B1, H5).
            etikett = karte.get("zustand_etikett") or ""
            teile.append(
                f'<text class="gr-g1-anbieter" x="0" y="{y + 13:.0f}">'
                f'{_t(karte["anbieter"])}'
                + (' <tspan class="gr-g1-ref-etikett">Referenz</tspan>'
                   if karte.get("naeherung") else '')
                + (f' <tspan class="gr-g1-zustand">{_t(etikett)}</tspan>'
                   if etikett else '')
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
                    f'<title>{_t(karte["anbieter"])}'
                    + (f' ({_t(etikett)})' if etikett else '') + ': '
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
            # S4 / C.1: das Euro-Delta zur Referenz steht IN der Grafik, am
            # Balken - dieselbe Zahl wie auf der Karte (`_delta`), nicht
            # neu gerechnet. Nur bei gleicher Laufzeit gibt es einen
            # Euro-Betrag; sonst bleibt der Balken beim Betrag.
            delta = karte.get("delta") or {}
            delta_text = ""
            if delta.get("betrag") is not None:
                zeichen = "−" if delta.get("guenstiger") else "+"
                delta_text = (f' <tspan class="gr-g1-delta">'
                              f'{zeichen}{_t(euro(delta["abstand"]))}</tspan>')
            teile.append(
                f'<text class="gr-g1-betrag" x="{x + 8:.1f}" '
                f'y="{y + 18:.0f}">{_t(euro(karte["gesamt"]))}{delta_text}</text>')
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
# G0 - die Zeitreihe im Hauptbild (BRIEF_ZEITREIHE, 05.09.2026)
# --------------------------------------------------------------------------
#
# Der Hauptgraph der Hauptansicht: je gewaehltem Geraet eine Linie je
# Anbieter, Gerätepreis ueber die Zeit. Anders als G2 (Marktueberblick
# ueber ALLE Modelle, gedeckelt auf fuenf bewegte Reihen) zeigt dieser Graph
# GENAU EIN Geraet mit ALLEN seinen Anbietern (bis `MAX_LINIEN` aus
# `geraete_verlauf`, Vodafone nie verdraengt) - dieselbe Aufgabenteilung wie
# zwischen G1 (ein Geraet) und der Alarmtabelle (der ganze Markt).

G0_BREITE = 1180
G0_HOEHE = 300
G0_LINKS = 76
G0_UNTEN = 34
G0_OBEN = 16
G0_RECHTS = 210

# Ab wie vielen Tagen zwischen zwei aufeinanderfolgenden Messpunkten
# DERSELBEN Linie aus einer Verbindung eine SAMMELLUECKE wird. Die
# Sammlung laeuft taeglich (der bestaetigte Punkt haengt sich an
# `last_verified` jedes Laufs); ein bestaetigter Preis, der zwei bis fuenf
# Tage keine neue Zeile schreibt, ist normale Kadenz - eine Woche ganz ohne
# jede Bestaetigung ist keine Verzoegerung mehr, sondern ein Ausfall der
# Sammlung. Am gemessenen Bestand (05.09.2026) unterscheidet das die
# echten Luecken (19 Tage) sauber von den kurzen Abstaenden derselben
# Woche (2 bis 5 Tage) - mit jeder Schwelle zwischen zwei und achtzehn
# Tagen waere das Ergebnis heute gleich, aber diese ist die, die eine
# Woche ganz ohne Bestaetigung als das behandelt, was sie ist.
G0_LUECKE_TAGE = 7


def _tage_dieses_geraets(reihen: list) -> list:
    """Alle Tage, an denen IRGENDEIN Anbieter dieses Geraets einen Preis
    zeigt - fuer die Chart-Chrome-Zeile UND die Luecken-Markierung."""
    tage = set()
    for r in reihen:
        for p in r.get("punkte") or []:
            tag = _tag(p.get("datum"))
            if tag is not None:
                tage.add(tag)
    return sorted(tage)


def _luecken(tage: list, schwelle: int = G0_LUECKE_TAGE) -> list:
    """Die Intervalle zwischen zwei Messtagen dieses Geraets, die weiter
    auseinanderliegen als `schwelle` Tage - fuer die Schattierung im Bild."""
    return [(a, b) for a, b in zip(tage, tage[1:])
            if (b - a).days > schwelle]


def zeitreihe(reihen: list) -> dict:
    """G0: Gerätepreis über die Zeit, je Anbieter, fuer EIN gewaehltes
    Geraet - der neue Hauptgraph ueber den Balkenbloecken.

    `reihen` kommt aus `geraete_verlauf.reihen_fuer_listungen()` und ist
    schon auf EIN Geraet eingegrenzt; diese Funktion rechnet nur noch
    Geometrie (Regel 1 des Modulkopfs).

    Die drei Regeln des Auftrags:
      1. Eine Linie nur ab zwei Messpunkten; EIN Punkt bleibt ein Punkt -
         hier wird nichts erfunden, um daraus eine Linie zu machen.
      2. Ehrliche Achse: `von`/`bis` sind der echte erste und letzte
         Messtag DIESES Geraets, proportional zur echten Kalenderzeit -
         eine Sammelluecke bleibt darin leerer Raum. Ueberspringt eine
         Linie selbst eine Luecke (`G0_LUECKE_TAGE`), wird sie NICHT
         durchgezogen: der Lauf endet, ein neuer beginnt.
      3. Kein Fliesstext hier - die Chart-Chrome-Zeile baut die Vorlage aus
         `messtage`/`seit`, dieses Modul liefert nur die zwei Zahlen.
    """
    tage = _tage_dieses_geraets(reihen)
    if not tage:
        return {"svg": "", "hat_daten": False, "messtage": 0, "seit": "",
                "bis": "", "linien": [], "chrome": ""}

    luecken = _luecken(tage)
    von, bis = tage[0], tage[-1]
    spanne_tage = max(1, (bis - von).days)

    alle_preise = [p["preis"] for r in reihen for p in (r.get("punkte") or [])]
    tief, hoch = min(alle_preise), max(alle_preise)
    if hoch <= tief:
        hoch = tief + 1.0
    # Etwas Luft nach oben und unten - dieselbe Rechnung wie G2, damit kein
    # Punkt auf der Achse klebt.
    polster = (hoch - tief) * 0.12
    tief, hoch = tief - polster, hoch + polster

    def x(tag: date) -> float:
        breite = G0_BREITE - G0_LINKS - G0_RECHTS
        return round(G0_LINKS + (tag - von).days / spanne_tage * breite, 1)

    def y(preis: float) -> float:
        hoehe = G0_HOEHE - G0_OBEN - G0_UNTEN
        return round(G0_HOEHE - G0_UNTEN
                     - (preis - tief) / (hoch - tief) * hoehe, 1)

    teile = [
        f'<svg class="gr-g0" viewBox="0 0 {G0_BREITE} {G0_HOEHE}" '
        f'width="100%" height="{G0_HOEHE}" role="img" '
        f'aria-label="Gerätepreis über die Zeit, {len(reihen)} Anbieter, '
        f'{_t(von.isoformat())} bis {_t(bis.isoformat())}">',
        f'<title>Gerätepreis über die Zeit, {_t(von.isoformat())} bis '
        f'{_t(bis.isoformat())}</title>',
    ]

    # Y-Achse: fuenf Marken, dieselbe Rundungsregel wie G2.
    marken = [tief + (hoch - tief) * i / 4 for i in range(5)]
    genau = len({f"{m:.0f}" for m in marken}) < len(marken)
    for marke in marken:
        yy = y(marke)
        beschriftung = (f"{marke:.2f}".replace(".", ",") if genau
                        else f"{marke:.0f}")
        teile.append(f'<line class="gr-g0-raster" x1="{G0_LINKS}" y1="{yy}" '
                     f'x2="{G0_BREITE - G0_RECHTS}" y2="{yy}" />'
                     f'<text class="gr-g0-achse" x="{G0_LINKS - 8}" '
                     f'y="{yy + 4}" text-anchor="end">{beschriftung} €</text>')

    # X-Achse: Wochenraster kurzfristig, Monatsraster ab drei Monaten -
    # dieselbe Regel wie G2.
    schritt = 7 if spanne_tage <= 92 else 30
    marke = von
    gesetzt = []
    while marke <= bis:
        gesetzt.append(marke)
        marke = marke + timedelta(days=schritt)
    if bis not in gesetzt and (bis - gesetzt[-1]).days > schritt // 3:
        gesetzt.append(bis)
    for tag in gesetzt:
        teile.append(f'<line class="gr-g0-raster gr-g0-raster--x" '
                     f'x1="{x(tag)}" y1="{G0_OBEN}" x2="{x(tag)}" '
                     f'y2="{G0_HOEHE - G0_UNTEN}" />'
                     f'<text class="gr-g0-achse" x="{x(tag)}" '
                     f'y="{G0_HOEHE - 12}" text-anchor="middle">'
                     f'{tag.strftime("%d.%m.")}</text>')

    # Die Sammelluecke bekommt ein Feld im Bild - sonst ist der leere Raum
    # zwischen zwei Rasterlinien nicht von einer ruhigen Woche zu
    # unterscheiden.
    for lo, hi in luecken:
        x1, x2 = x(lo), x(hi)
        teile.append(f'<rect class="gr-g0-luecke" x="{x1}" y="{G0_OBEN}" '
                     f'width="{x2 - x1:.1f}" '
                     f'height="{G0_HOEHE - G0_OBEN - G0_UNTEN}">'
                     f'<title>Sammellücke {_t(lo.strftime("%d.%m.%Y"))} bis '
                     f'{_t(hi.strftime("%d.%m.%Y"))} – in dieser Zeit liegt '
                     f'kein Messpunkt vor.</title></rect>')

    linien = []
    for nr, reihe in enumerate(reihen):
        slug = anbieter_slug(reihe["anbieter"])
        punkte = sorted(
            ((t, p["preis"]) for p in (reihe.get("punkte") or [])
             for t in [_tag(p.get("datum"))] if t is not None),
            key=lambda tb: tb[0])
        if not punkte:
            continue

        # In LAEUFE zerlegen: getrennt an jeder Luecke DIESER Linie - Regel
        # 2 des Modulkopfs ("Linien enden und beginnen neu"). Gerechnet wird
        # gegen den Abstand der Linie SELBST, nicht gegen die Luecken des
        # ganzen Geraets: ein Anbieter, der zwischen zwei eigenen Punkten
        # laenger schweigt als `G0_LUECKE_TAGE`, hat fuer diese Spanne
        # keinen Beleg - unabhaengig davon, ob ein anderer Anbieter in der
        # Zwischenzeit gemessen wurde.
        laeufe = [[punkte[0]]]
        for (t0, _), (t1, b1) in zip(punkte, punkte[1:]):
            if (t1 - t0).days > G0_LUECKE_TAGE:
                laeufe.append([])
            laeufe[-1].append((t1, b1))

        for lauf in laeufe:
            if len(lauf) >= 2:
                pfad = " ".join(f"{'M' if i == 0 else 'L'}{x(t)} {y(b)}"
                                for i, (t, b) in enumerate(lauf))
                teile.append(f'<path class="gr-g0-linie gr-anb--{slug}" '
                             f'd="{pfad}" fill="none" />')
            einzeln = len(lauf) == 1
            for t, b in lauf:
                klasse = "gr-g0-punkt" + (" gr-g0-punkt--einzeln"
                                          if einzeln else "")
                teile.append(
                    f'<circle class="{klasse} gr-anb--{slug}" cx="{x(t)}" '
                    f'cy="{y(b)}" r="{"5" if einzeln else "4"}">'
                    f'<title>{_t(reihe["anbieter"])} · '
                    f'{t.strftime("%d.%m.%Y")}: {euro(b)}</title></circle>')
                if einzeln:
                    # KEIN NACKTER PUNKT (BRIEF_FADEN, 05.09.2026): ein
                    # einzelner Messpunkt ohne Beschriftung liest sich als
                    # "keine Werte" - Antonios QA-Befund 3 an Telekoms
                    # Einzelpunkt vom 05.09.2026. Die Beschriftung nennt das
                    # Datum, nicht nur die Existenz einer Serie - derselbe
                    # Belegzwang wie am Tooltip.
                    #
                    # DIE AUSRICHTUNG HAENGT VON DER HAELFTE AB, NICHT VON
                    # EINEM FESTEN "middle": ein Einzelpunkt liegt oft am
                    # rechten Rand (der juengste, oft einzige Messtag), und
                    # "middle" liess die Haelfte des Textes in die
                    # Anbieter-Legende rechts vom Bild laufen. Ein Punkt in
                    # der rechten Haelfte bekommt seine Beschriftung nach
                    # LINKS, einer in der linken Haelfte nach RECHTS - so
                    # bleibt sie innerhalb der Zeichenflaeche.
                    mitte_x = G0_LINKS + (G0_BREITE - G0_LINKS - G0_RECHTS) / 2
                    if x(t) > mitte_x:
                        anker, tx = "end", x(t) - 9
                    else:
                        anker, tx = "start", x(t) + 9
                    teile.append(
                        f'<text class="gr-g0-einzeln gr-anb--{slug}" '
                        f'x="{tx}" y="{y(b) - 10}" text-anchor="{anker}">'
                        f'Serie startet · 1. Messpunkt '
                        f'{_t(t.strftime("%d.%m.%Y"))}</text>')

        teile.append(
            f'<text class="gr-g0-legende gr-anb--{slug}" '
            f'x="{G0_BREITE - G0_RECHTS + 12}" y="{22 + nr * 20}">'
            f'{_t(reihe["anbieter"])}</text>')
        linien.append({"anbieter": reihe["anbieter"], "farbe": reihe["farbe"],
                       "eigen": reihe["eigen"], "punkte": len(punkte),
                       "von": punkte[0][0].isoformat(),
                       "bis": punkte[-1][0].isoformat(),
                       "von_de": punkte[0][0].strftime("%d.%m.%Y"),
                       "bis_de": punkte[-1][0].strftime("%d.%m.%Y")})

    teile.append('</svg>')
    # DIE CHART-CHROME-ZEILE ENTSTEHT HIER UND NICHT IN DER VORLAGE - eine
    # einzige Zeichenkette statt einer Rechnung aus Datumsfiltern im
    # Template, damit kein zweiter Ort je einen abweichenden Wortlaut
    # erzeugen kann (Kriterium 3 des Auftrags: "kein Fliesstext" ausser
    # GENAU diesem einen Satz).
    chrome = (f"Sammlung läuft · {len(tage)} "
             f"{'Messtag' if len(tage) == 1 else 'Messtage'} · "
             f"seit {von.strftime('%d.%m.%Y')}")
    return {"svg": "".join(teile), "hat_daten": True, "messtage": len(tage),
            "seit": von.isoformat(), "bis": bis.isoformat(), "linien": linien,
            "chrome": chrome}


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
# WARUM DIESE SCHWELLE ANDERS IST ALS DIE DES NACHBARN im selben Reiter
# (`geraete_verlauf.DIAGRAMM_AB_TERMINEN`, 4): dort steht die Kurve EINES
# gewaehlten Geraets, und zwei Punkte ergaeben eine Gerade, die wie ein
# Trend aussieht. Hier steht die Uebersicht ueber ALLE Reihen mit mehr als
# einer Messung - sie beantwortet "wo hat sich ueberhaupt etwas bewegt",
# und dafuer ist die zweite Messung genau die Nachricht. C.2 des
# Lastenhefts nennt sie ausdruecklich ("<2 Messpunkte: Empty-State").
# Hoechstens so viele Reihen in einem Bild. Mehr Linien in einem
# Euro-Massstab sind ein Knaeuel, kein Verlauf.
MAX_REIHEN = 5


def _tag(text: str) -> Optional[date]:
    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def _ereignisse(reihe: dict) -> list:
    """Die Preisaenderungen EINER Reihe zwischen aufeinanderfolgenden
    eindeutigen Messtagen - fuer Marker, Fliesstext und Rangfolge.

    Eine Aenderung ist ein Unterschied von mindestens einem Cent zum
    vorigen Messtag. Gerechnet wird EINMAL, hier; wer den Pfeil, den Satz
    oder die Auswahl der gezeichneten Reihen aendern will, aendert diese
    Funktion und nicht eine der drei Stellen.
    """
    punkte = sorted(
        [(t, b) for t, b in ((_tag(p["datum"]), float(p["betrag"]))
                             for p in (reihe.get("punkte") or []))
         if t is not None])
    ereignisse, vorher = [], None
    for t, b in punkte:
        if vorher is not None and abs(b - vorher) >= 0.01:
            delta = round(b - vorher, 2)
            ereignisse.append({
                "name": reihe.get("name", ""),
                "anbieter": reihe.get("anbieter", ""),
                "datum": t.isoformat(), "betrag": b, "delta": delta,
                "richtung": "hoch" if delta > 0 else "runter",
                "quelle_url": reihe.get("quelle_url", "")})
        vorher = b
    return ereignisse


def _reihenrang(reihe: dict) -> tuple:
    """Bewegte Reihen vor flachen, die groesste Bewegung zuerst.

    Erst dann zaehlen die Zahl der Ereignisse und die der Messpunkte, und
    der Name bricht nur noch den Gleichstand. Eine flache Reihe kann damit
    keine bewegte verdraengen - und wo der Deckel greift, faellt zuerst,
    was sich nicht geaendert hat. Der Anbieter steht mit im Schluessel,
    damit zwei gleichnamige Reihen deterministisch stehen.
    """
    ereignisse = reihe.get("ereignisse") or []
    groesste = max((abs(e["delta"]) for e in ereignisse), default=0.0)
    return (not ereignisse, -groesste, -len(ereignisse),
            -len(reihe.get("punkte") or []),
            reihe.get("name", ""), reihe.get("anbieter", ""))


def historie(reihen: list) -> dict:
    """G2: Preisverlauf je Modell x Anbieter, mit Ereignismarkern.

    `reihen` ist eine Liste von
    `{"name","anbieter","punkte":[{"datum","betrag"}],"quelle_url"}`.

    Rueckgabe traegt `svg` (leer, wenn es nichts zu zeichnen gibt),
    `tabelle` (dieselben Zahlen als Text - C.2 verlangt sie ausdruecklich
    fuer Mobilgeraete und Screenreader) und `ereignisse`.
    """
    # ERST PARSEN, DANN ZAEHLEN. Vorher wurde auf der ROHEN Punktzahl
    # gefiltert und erst danach das Datum gelesen: eine Reihe, deren
    # Datumsangaben alle unlesbar sind ("29.08.2026" statt "2026-08-29"),
    # kam mit leerer Punktliste bis `punkte[0]` und riss einen IndexError -
    # und der nimmt ueber `geraete_view.leer()` den Navigationseintrag
    # "Geraete" von JEDER Seite des Portals. Dieselbe Fehlerklasse wie
    # Befund B1 aus Phase 6a, diesmal von einer Datenzeile ausgeloest.
    #
    # ZUSAMMENGEFASST WIRD JE TAG (letzter Stand des Tages): zwei
    # Messungen desselben Tages ergaeben sonst ein senkrechtes Segment,
    # und der Nachbar im selben Reiter zaehlt seit dem 30.08.2026
    # ausdruecklich MESSTAGE statt roher Punkte.
    #
    # UND ZWEI PREISE AN EINEM TAG SIND KEIN PREIS, sondern eine Messluecke
    # (QA-Befund B2, 04.09.2026): dieselbe Regel wie in der interaktiven
    # Grafik, aus derselben Funktion (`geraete_verlauf.messtage`). Bis dahin
    # nahm diese Stelle den LETZTEN Stand des Tages und die interaktive den
    # NIEDRIGSTEN - die Seite widersprach sich selbst, und mit den rohen
    # Punkten davor zeigten 13 von 15 Pfeilen eine Aenderung, die es nie
    # gab. Ein mehrdeutiger Tag faellt aus der Kurve, bekommt keinen Pfeil
    # und keinen Eintrag im Fliesstext; die Reihe NENNT ihn stattdessen
    # (`mehrdeutig`), und eine Reihe, der danach keine zwei Punkte bleiben,
    # steht als `ausgelassen` unter der Grafik - mit Grund.
    from .geraete_verlauf import messtage  # spaet: kein Importkreis
    brauchbar, ausgelassen = [], []
    for reihe in reihen:
        saetze = []
        for punkt in (reihe.get("punkte") or []):
            tag = _tag(punkt.get("datum"))
            if tag is not None:
                saetze.append({"datum": tag.isoformat(),
                               "betrag": punkt.get("betrag")})
        eindeutig, doppelt = messtage(saetze, feld="betrag")
        for m in (reihe.get("mehrdeutig") or []):
            tag = _tag(m.get("datum"))
            if tag is not None:
                doppelt[tag.isoformat()] = list(m.get("betraege") or [])
                eindeutig.pop(tag.isoformat(), None)
        punkte = [{"datum": t, "betrag": b} for t, b in sorted(eindeutig.items())]
        mehrdeutig = [{"datum": t, "betraege": doppelt[t]} for t in sorted(doppelt)]
        if len(punkte) >= MIND_PUNKTE:
            brauchbar.append(dict(reihe, punkte=punkte, mehrdeutig=mehrdeutig))
        elif mehrdeutig:
            ausgelassen.append({
                "name": reihe.get("name", ""),
                "anbieter": reihe.get("anbieter", ""),
                "quelle_url": reihe.get("quelle_url", ""),
                "tage": [m["datum"] for m in mehrdeutig],
                "betraege": {m["datum"]: m["betraege"] for m in mehrdeutig}})
    # S8: die Bildunterschrift sagt "5 von 9 Reihen", nicht "5 Reihen" -
    # der Deckel ist eine Auswahl, und eine Auswahl nennt ihre Grundmenge.
    reihen_gesamt = len(brauchbar)

    # EREIGNIS SCHLAEGT ALPHABET (QA-Befund F-R2-1, 04.09.2026). Bis dahin
    # sortierte der Deckel nach Punktzahl und dann nach NAMEN - und weil
    # alle acht Reihen des Bestands genau zwei Punkte hatten, entschied das
    # Alphabet: "Galaxy ..." schlug "Nothing ..." und "Pixel ...". Gezeichnet
    # wurden drei congstar-Linien ohne jede Aenderung, unsichtbar blieb der
    # groesste Preissprung des ganzen Bestands (o2 Pixel 10 Pro, 793 -> 973
    # EUR am 03.09.). Dieselbe Fehlerklasse wie B2, nur andersherum: dort
    # falsch-positive Pfeile, hier falsch-negative.
    #
    # UND DIE EREIGNISSE DES FLIESSTEXTS KOMMEN AUS DER GRUNDMENGE, nicht aus
    # den gezeichneten Reihen: "Erhoehungen und Senkungen im Messzeitraum"
    # ist ein Satz ueber den Bestand, und er nannte zwei Ereignisse, wo vier
    # existierten - waehrend `gr-verlaufdaten` derselben Seite alle vier
    # kannte. Die Bildunterschrift legt die Kappung offen ("5 von 8
    # Reihen"), der Satz tat es nicht. Die Marker der Grafik entstehen aus
    # DENSELBEN Ereignissen (`je_tag` unten) - eine Rechnung, zwei Orte.
    for reihe in brauchbar:
        reihe["ereignisse"] = _ereignisse(reihe)
    ereignisse = [e for r in brauchbar for e in r["ereignisse"]]
    bewegt = sum(1 for r in brauchbar if r["ereignisse"])
    brauchbar.sort(key=_reihenrang)
    brauchbar = brauchbar[:MAX_REIHEN]
    if not brauchbar:
        return {"svg": "", "tabelle": [], "ereignisse": [], "reihen": 0,
                "reihen_gesamt": 0, "bewegt": 0, "ausgelassen": ausgelassen}

    punkte_alle = [(_tag(p["datum"]), float(p["betrag"]))
                   for r in brauchbar for p in r["punkte"]]
    if len(punkte_alle) < MIND_PUNKTE:
        return {"svg": "", "tabelle": [], "ereignisse": [], "reihen": 0,
                "reihen_gesamt": 0, "bewegt": 0, "ausgelassen": ausgelassen}

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

    # X-ACHSE: WOCHENRASTER KURZFRISTIG, MONATSRASTER AB DREI MONATEN
    # (C.2). Der Abstand der Marken sagt, wie dicht gemessen wurde - eine
    # Achse mit nur zwei Beschriftungen laesst offen, ob dazwischen taeglich
    # oder gar nicht gemessen wurde.
    schritt = 7 if spanne_tage <= 92 else 30
    marke = von
    gesetzt = []
    while marke <= bis:
        gesetzt.append(marke)
        marke = marke + timedelta(days=schritt)
    if bis not in gesetzt and (bis - gesetzt[-1]).days > schritt // 3:
        gesetzt.append(bis)
    for tag in gesetzt:
        teile.append(f'<line class="gr-g2-raster gr-g2-raster--x" '
                     f'x1="{x(tag)}" y1="{G2_OBEN}" x2="{x(tag)}" '
                     f'y2="{G2_HOEHE - G2_UNTEN}" />'
                     f'<text class="gr-g2-achse" x="{x(tag)}" '
                     f'y="{G2_HOEHE - 12}" text-anchor="middle">'
                     f'{tag.strftime("%d.%m.")}</text>')

    tabelle = []
    for nr, reihe in enumerate(brauchbar):
        slug = anbieter_slug(reihe["anbieter"])
        punkte = sorted(
            [(t, b) for t, b in ((_tag(p["datum"]), float(p["betrag"]))
                                 for p in reihe["punkte"]) if t is not None])
        pfad = " ".join(f"{'M' if i == 0 else 'L'}{x(t)} {y(b)}"
                        for i, (t, b) in enumerate(punkte))
        teile.append(f'<path class="gr-g2-linie gr-anb--{slug}" d="{pfad}" '
                     f'fill="none" />')
        # Die Marker kommen aus `_ereignisse`, nicht aus einer zweiten
        # Rechnung in der Schleife - sonst koennten Pfeil und Fliesstext
        # auseinanderlaufen.
        je_tag = {e["datum"]: e for e in reihe["ereignisse"]}
        for t, b in punkte:
            klasse = "gr-g2-punkt"
            titel = f'{reihe["name"]} · {reihe["anbieter"]} · ' \
                    f'{t.strftime("%d.%m.%Y")}: {euro(b)}'
            ereignis = je_tag.get(t.isoformat())
            if ereignis is not None:
                delta = ereignis["delta"]
                klasse += f" gr-g2-punkt--{ereignis['richtung']}"
                zeichen = "+" if delta > 0 else "−"
                titel += f' ({zeichen}{euro(abs(delta))} gegenüber ' \
                         f'dem letzten Messpunkt)'
                teile.append(
                    f'<text class="gr-g2-marker" x="{x(t)}" '
                    f'y="{y(b) - 10}" text-anchor="middle">'
                    f'{"↑" if delta > 0 else "↓"}</text>')
            teile.append(f'<circle class="{klasse} gr-anb--{slug}" '
                         f'cx="{x(t)}" cy="{y(b)}" r="4">'
                         f'<title>{_t(titel)}</title></circle>')
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
            # Die ausgelassenen Tage stehen in der Tabelle - eine Luecke,
            # die niemand nennt, liest sich als "unveraendert".
            "mehrdeutig": reihe.get("mehrdeutig") or [],
        })

    teile.append('</svg>')
    ereignisse.sort(key=lambda e: (e["datum"], e["name"]), reverse=True)
    return {"svg": "".join(teile), "tabelle": tabelle,
            "ereignisse": ereignisse, "reihen": len(brauchbar),
            "reihen_gesamt": reihen_gesamt, "bewegt": bewegt,
            "ausgelassen": ausgelassen,
            "von": von.isoformat(), "bis": bis.isoformat()}
