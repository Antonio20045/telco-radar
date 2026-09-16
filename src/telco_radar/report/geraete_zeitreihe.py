"""E2 (AUFTRAG_GERAETE_EINE_SEITE_V2 §1a, 16.09.2026): die TCO-ZEITREIHE
der Geräteseite - Aufbereitung UND Grafik, beides serverseitig.

Antonios Wortlaut (§1a): „Ich will einen verfickten Graphen haben. Mit
verfickten Punkten und Koordinatensystem. […] Y-Achse ist Euro-Kosten.
Und X-Achse ist das DATUM. Ich möchte dann genau die verschiedenen
Messtage immer sehen." - und nach dem Ansehen des Prototyps: „Den Graphen
finde ich gut." Der Prototyp (docs/entwuerfe/geraete-eine-seite-2026-09-16,
entwurf-v2.html + prototyp.js, DOM-bewiesen in Commit 2f40457) ist hier
Production geworden. Drei Regeln tragen dieses Modul:

1. **JEDE ZAHL ENTSTEHT HIER, KEINE IM CLIENT.** Der Browser setzt fertige
   Knoten ein (Antwort-Satz, Messtag-Zeile, beide SVG-Varianten,
   Lückensatz); er rechnet, formatiert und baut keine Zeichenketten. Die
   Vorlage und `app.js` sind Montage, kein Renderer - dieselbe Regel wie
   `luecke_text` in `geraete_tco_band`.
2. **Nichts wird interpoliert.** Ein Anbieter ohne Messung an einem Tag
   hat keinen Punkt an diesem Tag; unter zwei Punkten gibt es keinen
   Linienzug. Die Lücke IST die Aussage des Graphen.
3. **Der Startzustand kommt aus den Daten**: das Modell × Band mit den
   meisten Anbietern, bei Gleichstand das mit den meisten Punkten. Nichts
   ist hardcodiert - der Bestand wächst jede Nacht, und der Start darf
   nicht an einem Prototypsstand kleben.

Die Zuordnung der Historie ist die des Sammel-Skripts des Prototyps
(`historie_sammeln.py`, reine Lesearbeit auf data/state):
  buendel_id -> geraete_tco.json (sku_id, anbieter, tarif_id)
  sku_id     -> Modell       (geraete_view/geraete_tco_karten - dieselbe
                              Gruppierung wie die Karten der Seite)
  tarif_id   -> Band         (geraete_tco_band.tarif_baender - dieselbe
                              Logik wie der bisherige Band-Graph)
Je (Modell, Band, Anbieter, Tag) zählt das GÜNSTIGSTE Bündel: Farben sind
Preisdimensionen.

ZWEI SVG-Varianten je Paar (breit/schmal) statt clientseitigem Neu-Rendern
bei Resize: der Prototyp rechnete die Geometrie im Browser neu - hier
stehen beide fertigen Bilder im Dokument, und ein CSS-Mediaquery zeigt
genau eines. `display:none` nimmt das andere aus dem Accessibility-Baum.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date
from pathlib import Path

from .geraete_tco_band import ERWARTETE_ANBIETER

log = logging.getLogger(__name__)

# Die Anzeige-Reihenfolge der Anbieter im Graphen: Netzbetreiber zuerst,
# Zweitmarke daneben, Discounter ans Ende - dieselbe Ordnung wie der
# genehmigte Prototyp (prototyp.js ANB_REIHENFOLGE).
ANBIETER_FOLGE = ("Telekom", "Vodafone", "o2", "1&1", "congstar")

# Dieselben Werte wie --anb in style.css (dort .gr-anb--<slug>): die Farbe
# ist KEINE Grafikentscheidung, sondern die des Anbieters auf der ganzen
# Seite (C.3 der Optik-Strategie).
ANB_FARBE = {"Telekom": "#e20074", "Vodafone": "#e60000", "o2": "#0019a5",
             "1&1": "#00589e", "congstar": "#f5a800"}

EIGEN = "Vodafone"

# Die beiden Bildgrößen. Breit: die Tafel bietet auf dem Schreibtisch rund
# 1138 px Innenbreite (.wrap 1240 - 2*28 - 2*22 - 2*1). Schmal: 390-px-
# Telefon minus Tafelpadding (14) und Rahmen. Die Hoehen folgen dem
# Prototyp (max(420, W*0.42) bzw. max(340, W*0.42)).
BREIT_W, BREIT_MIN_H = 1136, 420
# Schmal: 380 statt 340 - die Endnamen-Kette (je Anbieter Name + Datum,
# Vodafone mit Chip) braucht Platz unter dem Plot; bei 340 ragte sie in
# den Boden. Gemessen am echten Bestand (5 Anbieter).
SCHMAL_W, SCHMAL_MIN_H = 358, 380

# Hoechstens so viele Kacheln als Schnelleingang (§3.2: „4–6 häufigste
# Geräte"); die Zahl ist eine Obergrenze, kein Soll.
KACHELN_MAX = 6


def _euro(betrag) -> str:
    """1.234,56 € - dieselbe Schreibweise wie ueberall auf der Seite."""
    if betrag is None:
        return ""
    return f"{betrag:,.2f}".replace(",", " ").replace(
        ".", ",").replace(" ", ".") + " €"


def _euro0(betrag) -> str:
    if betrag is None:
        return ""
    return f"{betrag:,.0f}".replace(",", ".") + " €"


def _tag_monat(iso: str) -> str:
    """„12.9." - das X-Achsen-Format des Prototyps (echtes deutsches)."""
    y, m, d = iso.split("-")
    return f"{int(d)}.{int(m)}."


def _datum_kurz(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{d}.{m}.{y}"


def _datum_de(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(d)}. {date(int(y), int(m), int(d)).strftime('%B')} {y}"


def _kurz_name(modell: dict) -> str:
    """„Apple iPhone 17 Pro 256 GB" -> „iPhone 17 Pro" (Kachel/Vorschau)."""
    titel = modell.get("titel") or modell.get("id", "")
    hersteller = modell.get("hersteller") or ""
    speicher = modell.get("speicher")
    if hersteller and titel.startswith(hersteller + " "):
        titel = titel[len(hersteller) + 1:]
    if speicher:
        titel = titel.rstrip()
        suffix = f" {speicher} GB"
        if titel.endswith(suffix):
            titel = titel[:-len(suffix)]
    return titel


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# --------------------------------------------------------------------------
# Die Band-Zeilen - der Antwort-Satz und die Luecke lesen sie
# --------------------------------------------------------------------------

def _band_zeilen(modell: dict) -> dict:
    """Je Band des Modells: die Zeilen (beste je Anbieter) und Luecken.

    Dieselbe Auswahl wie der Prototyp (`zahlen_sammeln.py`): vergleichbare,
    belastbare Karten, aufsteigend nach TCO-24, je Anbieter die beste -
    die Vodafone-Näherung ergänzt ein Band, in dem kein eigenes Bündel
    steht. Die Naeherung ist KEIN Angebot, aber der Massstab des Bandes.
    """
    baender: dict[str, dict] = {}
    karten = modell.get("karten") or []
    for karte in karten:
        band = karte.get("band")
        if not band:
            continue
        baender.setdefault(band, {"karten": []})["karten"].append(karte)

    fertig: dict[str, dict] = {}
    for band, satz in baender.items():
        zeilen, gesehen = [], set()
        kandidaten = sorted(
            (k for k in satz["karten"]
             if k.get("vergleichbar") and k.get("belastbar")
             and k.get("gesamt") is not None),
            key=lambda k: k["gesamt"])
        for karte in kandidaten:
            if karte["anbieter"] in gesehen:
                continue
            gesehen.add(karte["anbieter"])
            zeilen.append(karte)
        naeherung = next((k for k in satz["karten"] if k.get("naeherung")
                          and k.get("gesamt") is not None), None)
        if naeherung is not None and EIGEN not in gesehen:
            zeilen.append(naeherung)
            gesehen.add(EIGEN)
        zeilen.sort(key=lambda k: k["gesamt"])
        fertig[band] = {"zeilen": zeilen, "karten": satz["karten"]}
    return fertig


def _alternativen(karten: list, band: str, anbieter: str) -> list[dict]:
    """Die besten Bänder EINES Anbieters, der im gewählten Band fehlt.

    §4.5: „fehlende Anbieter MIT NAMEN und Alternativ-Bändern samt Betrag
    in Klammern" - der Leser sieht nicht nur DASS einer fehlt, sondern wo
    er steht. Nur ECHTE Karten (Bündel mit SKU oder die Näherung) sagen
    etwas darüber, wo ein Anbieter steht; die Leerkarte der Festanbieter
    ist kein Angebot.
    """
    beste: dict[str, float] = {}
    for karte in karten:
        if karte.get("anbieter") != anbieter:
            continue
        if not (karte.get("sku_id") or karte.get("naeherung")):
            continue
        b = karte.get("band")
        if b is None or not karte.get("vergleichbar") \
                or karte.get("gesamt") is None or b == band:
            continue
        g = karte["gesamt"]
        if b not in beste or g < beste[b]:
            beste[b] = g
    return [{"band": b, "tco": v} for b, v in sorted(beste.items())]


def _luecken(zeilen: list, karten: list, band: str) -> list[dict]:
    """Je erwartetem Anbieter ohne Zeile: der Grund, in EINEM Satz zusammen.

    Antonio 9b.7: „Wenn es nichts gibt, dann brauchst du es nicht
    anzuzeigen von den jeweiligen Anbietern" - die Namen stehen im SAMMEL-
    satz, nie als eigene Zeile mit leerem Inhalt.
    """
    gesehen = {z["anbieter"] for z in zeilen}
    luecken = []
    for anbieter in ANBIETER_FOLGE:
        if anbieter in gesehen:
            continue
        eigene = [k for k in karten if k["anbieter"] == anbieter
                  and (k.get("sku_id") or k.get("naeherung"))]
        if not eigene:
            grund = "gar-kein-buendel"
        elif any(k.get("band") == band for k in eigene):
            grund = "kein-belastbares"
        else:
            grund = "anderes-band"
        luecken.append({"anbieter": anbieter, "grund": grund,
                        "alternativ": _alternativen(karten, band, anbieter)})
    return luecken


def _luecke_text(luecken: list, band_labels: dict) -> str | None:
    if not luecken:
        return None
    band_wort = {"klein": "klein", "mittel": "mittel", "gross": "groß"}
    anderes, gar_nicht = [], []
    for l in luecken:
        name = l["anbieter"]
        if l["alternativ"]:
            alt = " · ".join(f"{band_wort.get(a['band'], a['band'])} "
                             f"{_euro(a['tco'])}" for a in l["alternativ"])
            name += f" ({alt})"
        if l["grund"] == "gar-kein-buendel":
            gar_nicht.append(name)
        else:
            anderes.append(name)
    teile = []
    if anderes:
        teile.append("Kein Bündel in diesem Band: " + ", ".join(anderes)
                     + ".")
    if gar_nicht:
        teile.append(", ".join(gar_nicht) + " "
                     + ("führt" if len(gar_nicht) == 1 else "führen")
                     + " das Gerät gar nicht im Bündel.")
    return " ".join(teile) or None


# --------------------------------------------------------------------------
# Der Antwort-Satz und der Rechenschaftssatz
# --------------------------------------------------------------------------

def _antwort_html(modell: dict, band: str, zeilen: list,
                  band_katalog: dict) -> str:
    name = _esc(_kurz_name(modell))
    label = band_katalog.get("label", band)
    bereich = band_katalog.get("bereich") or ""
    klammer = f" ({bereich})" if bereich else ""
    if not zeilen:
        return (f"Beim {name} im Band {label}{klammer} führt kein Anbieter "
                f"ein Bündel.")
    beste = zeilen[0]
    if len(zeilen) == 1 and beste["anbieter"] == EIGEN:
        return (f"Beim {name} im Band {label}{klammer} führt nur Vodafone: "
                f"<b class='gr-zr-zahl'>{_euro(beste['gesamt'])}</b> über "
                f"24 Monate (TCO-24), Ø <b class='gr-zr-zahl'>"
                f"{_schnitt(beste)}</b> ({_esc(beste.get('tarif') or '')}"
                f"{_gb_teil(beste)}).")
    satz = (f"Beim {name} im Band {label}{klammer} ist "
            f"{_esc(beste['anbieter'])} am günstigsten: "
            f"<b class='gr-zr-zahl'>{_euro(beste['gesamt'])}</b> über "
            f"24 Monate (TCO-24), Ø <b class='gr-zr-zahl'>"
            f"{_schnitt(beste)}</b> ({_esc(beste.get('tarif') or '')}"
            f"{_gb_teil(beste)})")
    eigen = next((z for z in zeilen if z["anbieter"] == EIGEN), None)
    if eigen is not None and eigen is not beste:
        satz += (f" — <b class='gr-zr-zahl'>"
                 f"{_euro(round(eigen['gesamt'] - beste['gesamt'], 2))}"
                 f"</b> über der Vodafone-Referenz ({_euro(eigen['gesamt'])}"
                 f"{', Näherung' if eigen.get('naeherung') else ''}).")
    elif eigen is beste:
        zweit = zeilen[1] if len(zeilen) > 1 else None
        satz = (f"Beim {name} im Band {label}{klammer} führt Vodafone: "
                f"<b class='gr-zr-zahl'>{_euro(beste['gesamt'])}</b> über "
                f"24 Monate (TCO-24), Ø <b class='gr-zr-zahl'>"
                f"{_schnitt(beste)}</b> ({_esc(beste.get('tarif') or '')}"
                f"{_gb_teil(beste)})")
        if zweit is not None:
            satz += (f" Nächster Anbieter: {_esc(zweit['anbieter'])} "
                     f"({_euro(zweit['gesamt'])}).")
    elif eigen is None:
        satz += " — Vodafone führt in diesem Band kein Bündel."
    # Der Satzschlusspunkt gehoert GENAU HIERHER - die Anhaengsel oben
    # schliessen ihren Teil teils selbst mit ".". Er wird deshalb nur
    # gesetzt, wenn er nicht schon da ist; ein bedingungsloses "+ ".""
    # machte daraus ").." (Abnahme 17.09.: 133 von 169 Bloecken).
    return satz if satz.endswith(".") else satz + "."


def _schnitt(karte: dict) -> str:
    monat = karte.get("schnitt_monat")
    if monat is None:
        return ""
    return f"{monat:,.2f}".replace(",", " ").replace(
        ".", ",").replace(" ", ".") + " €/Monat"


def _gb_teil(karte: dict) -> str:
    gb = karte.get("band_gb_text")
    return f" · {_esc(gb)}" if gb else ""


def _rechnung_html(zeilen: list) -> str:
    """(a) Rechenschaftssatz - EINE Zeile unter dem Antwort-Satz.

    Er nennt die Formel der Leitzahl und den Beleg des besten Angebots
    (Absender, Link, Abrufdatum) - die Transparenz-Forderung aus 9a
    („man kann hier nirgendwo auf den Link drücken") am wichtigsten Ort
    der Tafel.
    """
    if not zeilen:
        return ""
    beste = zeilen[0]
    url = beste.get("quelle_url") or ""
    link = (f"<a href='{_esc(url)}' target='_blank' rel='noopener'>"
            f"{_esc(beste['anbieter'])}&nbsp;↗</a>" if url
            else _esc(beste["anbieter"]))
    datum = beste.get("abgerufen_am") or ""
    datum_teil = f", abgerufen am {_datum_de(datum)}" if datum else ""
    return (f"So gerechnet: <code>TCO-24 = Zuzahlung + Anschlusspreis + "
            f"24 × Tarifgrundpreis + Geräteraten bis Monat 24</code> — "
            f"Boni bleiben außerhalb. Beleg des günstigsten Angebots: "
            f"{link}{datum_teil}.")


# --------------------------------------------------------------------------
# Die Zeitreihe selbst - Serien und SVG
# --------------------------------------------------------------------------

def _serien(state_dir: Path, tco: dict) -> dict:
    """{(modell, band): {anbieter: [[iso, wert], ...]}} aus der Historie.

    Die eingefrorene Leitzahl `gesamt` je (buendel_id, datum) ist der
    Punkt; je (Modell, Band, Anbieter, Tag) zaehlt das GUENSTIGSTE Buendel
    (Farben sind Preisdimensionen). Ein fehlender Tag bleibt fehlend.
    """
    sku_modell: dict[str, str] = {}
    for modell in tco.get("modelle") or []:
        for karte in modell.get("karten") or []:
            if karte.get("sku_id"):
                sku_modell[karte["sku_id"]] = modell["id"]

    band_je_tarif = tco.get("band_je_tarif") or {}
    tco_datei = state_dir / "geraete_tco.json"
    buendel: dict[str, dict] = {}
    if tco_datei.exists():
        try:
            roh = json.loads(tco_datei.read_text(encoding="utf-8"))
            buendel = {b.get("id"): b for b in roh.get("buendel") or []}
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("geraete_tco.json unlesbar fuer die Zeitreihe: %s",
                        exc)

    serien: dict[tuple, dict] = {}
    historie = state_dir / "geraete_tco_historie.jsonl"
    if not historie.exists():
        return {}
    for zeile in historie.read_text(encoding="utf-8").splitlines():
        if not zeile.strip():
            continue
        try:
            satz = json.loads(zeile)
        except json.JSONDecodeError:
            continue
        b = buendel.get(satz.get("id"))
        if b is None:
            continue
        modell = sku_modell.get(b.get("sku_id"))
        if modell is None:
            continue
        band = band_je_tarif.get(satz.get("tarif_id")
                                 or b.get("tarif_id") or "")
        if not band:
            continue
        datum, gesamt = satz.get("datum"), satz.get("gesamt")
        if not datum or gesamt is None:
            continue
        slot = (serien.setdefault((modell, band), {})
                .setdefault(b.get("anbieter") or "?", {}))
        alt = slot.get(datum)
        if alt is None or float(gesamt) < alt:
            slot[datum] = float(gesamt)

    fertig: dict[tuple, dict] = {}
    for schluessel, anbieter_ in serien.items():
        fertig[schluessel] = {
            an: sorted(werte.items()) for an, werte in anbieter_.items()}
    return fertig


def _messtage(anbieter_serien: dict) -> list[str]:
    """Die Union der Messtage DIESER Serien - die X-Achse zeigt nur Tage,
    an denen wirklich gemessen wurde."""
    tage: set[str] = set()
    for punkte in anbieter_serien.values():
        tage.update(d for d, _w in punkte)
    return sorted(tage)


def _nice_step(spanne: float) -> float:
    if spanne <= 0:
        return 1.0
    potenz = 10 ** math.floor(math.log10(spanne))
    n = spanne / potenz
    stufe = 1 if n <= 1 else 2 if n <= 2 else 2.5 if n <= 2.5 \
        else 5 if n <= 5 else 10
    return stufe * potenz


def _xtick_x(iso: str, t0: date, t1: date, links: float, breite: float,
             tage: list[str]) -> float:
    if t1 == t0:
        return links + breite / 2
    tag = date.fromisoformat(iso)
    return links + (tag - t0).days / max(1, (t1 - t0).days) * breite


def _svg(anbieter_serien: dict, breit: bool,
         beleg_je: dict[str, tuple[str, str]]) -> str:
    """DER EINE Graph - SVG-Koordinatensystem, fertig gerendert.

    Y = TCO-24 in € („runde" Ticks), X = das Datum in echter Distanz mit
    einem Tick je ECHTEM Messtag. Je Anbieter eine Linie mit einem Punkt
    je Messung (unter zwei Punkten: kein Linienzug), Wert am letzten Punkt
    gross und am ersten klein (nur breit), Vodafone rot mit „unser
    Angebot", Beleg-Link mit Abrufdatum am Linienende.
    """
    anbieter = [a for a in ANBIETER_FOLGE
                if anbieter_serien.get(a)]
    if not anbieter:
        return ""
    tage = _messtage(anbieter_serien)
    w = BREIT_W if breit else SCHMAL_W
    min_h = BREIT_MIN_H if breit else SCHMAL_MIN_H
    h = max(min_h, round(w * 0.42))
    links, rechts, oben, unten = 58, (158 if breit else 96), 18, 46
    pw, ph = w - links - rechts, h - oben - unten

    def x_v(iso: str) -> float:
        return _xtick_x(iso, date.fromisoformat(tage[0]),
                        date.fromisoformat(tage[-1]), links, pw, tage)

    werte = [p for serie in anbieter_serien.values() for _d, p in serie]
    ymin, ymax = min(werte), max(werte)
    spanne = (ymax - ymin) or max(ymax * 0.05, 1.0)
    y0 = max(0.0, ymin - spanne * 0.12)
    y1 = ymax + spanne * 0.12

    def y_v(wert: float) -> float:
        return oben + (1 - (wert - y0) / (y1 - y0)) * ph

    teile: list[str] = []
    teile.append(
        f"<svg class='gr-zr gr-zr--{'breit' if breit else 'schmal'}' "
        f"viewBox='0 0 {w} {h}' role='img' aria-label='TCO-24 je Messtag "
        f"und Anbieter: {_esc(', '.join(anbieter))}'>")
    schritt = _nice_step((y1 - y0) / 4)
    wert = math.ceil(y0 / schritt) * schritt
    while wert <= y1 + 0.01:
        y = y_v(wert)
        teile.append(f"<line class='gr-zr-raster' x1='{links}' y1="
                     f"'{y:.1f}' x2='{w - rechts}' y2='{y:.1f}'/>"
                     f"<text class='gr-zr-achse' x='{links - 8}' "
                     f"y='{y + 4:.1f}' text-anchor='end'>"
                     f"{_euro0(round(wert))}</text>")
        wert += schritt
    for tag in tage:
        x = x_v(tag)
        teile.append(f"<line class='gr-zr-raster' x1='{x:.1f}' y1='{oben}' "
                     f"x2='{x:.1f}' y2='{oben + ph}'/>"
                     f"<text class='gr-zr-xtick' x='{x:.1f}' "
                     f"y='{h - unten + 22}' text-anchor='end'>"
                     f"{_tag_monat(tag)}</text>")

    def _punkte(serie):
        return [(x_v(d), y_v(p), p) for d, p in serie]

    # Linien NUR zwischen echten Messungen; ein Ein-Punkt-Anbieter bekommt
    # keinen Pfad (Luecken sind Informationen, nichts wird interpoliert).
    for a in anbieter:
        punkte = _punkte(anbieter_serien[a])
        farbe = ANB_FARBE.get(a, "#333333")
        if len(punkte) > 1:
            pfad = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f} {y:.1f}"
                            for i, (x, y, _p) in enumerate(punkte))
            teile.append(f"<path class='gr-zr-linie' d='{pfad}' "
                         f"stroke='{farbe}'/>")
        for i, (x, y, _p) in enumerate(punkte):
            ende = i == len(punkte) - 1
            teile.append(
                f"<circle class='gr-zr-punkt"
                f"{' gr-zr-ende' if ende else ''}' cx='{x:.1f}' "
                f"cy='{y:.1f}' r='{6 if ende else 4.5}' fill='{farbe}'/>")

    # Wert-Labels: der LETZTE Wert je Anbieter gross (links vom Punkt, im
    # Plotraum - rechts beginnen die Endnamen), der ERSTE klein - je Tag-
    # spalte kollisionsfrei, gierig ueber/unter dem Punkt (die Rechnung des
    # Prototyps, nur nach Python getragen).
    abstand = 15 if not breit else 13

    def _label(kandidaten: list, klasse: str, dx: float, anker: str):
        kandidaten.sort(key=lambda k: k[1])
        belegt: list[float] = []
        for i, (x, y, text) in enumerate(kandidaten):
            # Am schmalen Bild steht der Wert NUR ueber dem Punkt: unter
            # dem Punkt beginnt rechts die Endnamen-Kette, und Wert und
            # Abrufdatum trafen sich in einem Band (gemessen: "1.560 EUR"
            # x "15.09.2026" bei y 943/946). Auf breit bleibt der
            # Prototyp-Wechsel ueber/unter.
            ziel = y - 11 if (i % 2 == 0 or not breit) else y + 18

            def frei(t: float) -> bool:
                return all(abs(b - t) >= abstand for b in belegt)
            if not frei(ziel):
                ziel = y - 11 if frei(y - 11) else y + 18
            schritte = 0
            while not frei(ziel) and schritte < 5:
                ziel += 15 if ziel > y else -15
                schritte += 1
            belegt.append(ziel)
            teile.append(f"<text class='{klasse}' x='{x + dx:.1f}' "
                         f"y='{ziel:.1f}' text-anchor='{anker}'>"
                         f"{_euro0(text)}</text>")

    # _punkte liefert (x, y, wert) - der LETZTE Punkt je Serie traegt
    # seinen Wert, der ERSTE den Anfangsbetrag. Beide NUR auf dem BREITEN
    # Bild: am schmalen kollidierten die Werte mit der Endnamen-Kette (am
    # echten Bestand 4-5 Anbieter, dreifach gemessen: "1.560 EUR" gegen
    # "Telekom ↗" und "15.09.2026"). Dort tragen die Werte die LEGENDE
    # ("ab X · zuletzt Y", per CSS eingeblendet) - eine Zahl je Ort, keine
    # Pixel-Flickschusterei.
    if breit:
        letzte = [_punkte(anbieter_serien[a])[-1] for a in anbieter]
        _label(letzte, "gr-zr-wert", -10, "end")
        mehrere = [a for a in anbieter if len(anbieter_serien[a]) > 1]
        _label([_punkte(anbieter_serien[a])[0] for a in mehrere],
               "gr-zr-wert gr-zr-wert--erst", 10, "start")

    # Die Endnamen: je Anbieter ein Beleg-Link (↗ + Abrufdatum), Vodafone
    # mit „unser Angebot" - untereinander kollisionsfrei, vom teuersten
    # Ende nach unten geordnet (die Reihenfolge des Prototyps: nach y).
    enden = sorted(((_punkte(anbieter_serien[a])[-1][0],
                     _punkte(anbieter_serien[a])[-1][1], a)
                    for a in anbieter), key=lambda e: e[1])
    letzte_y = -99.0
    for x, y, a in enden:
        # Der Stapelabstand richtet sich nach dem BEDARF des Eintrags:
        # Vodafone traegt Name, "unser Angebot" und Datum (drei Zeilen),
        # die anderen Name und Datum (zwei) - am schmalen Bild ohne
        # Wert-Labels ist der Grundabstand etwas enger.
        bedarf = ((56 if not breit else 46) if a == EIGEN else
                  (44 if not breit else 46))
        ty = max(y, letzte_y + bedarf)
        letzte_y = ty
        farbe = ANB_FARBE.get(a, "#333333")
        url, datum = beleg_je.get(a, ("", ""))
        name_html = f"{_esc(a)}<tspan class='gr-zr-pfeil'> ↗</tspan>"
        if url:
            teile.append(
                f"<a class='gr-zr-link' href='{_esc(url)}' "
                f"target='_blank' rel='noopener' aria-label='Beleg bei "
                f"{_esc(a)} öffnen'><text class='gr-zr-name' "
                f"x='{x + 12:.1f}' y='{ty + 4:.1f}' fill='{farbe}'>"
                f"{name_html}</text></a>")
        else:
            teile.append(f"<text class='gr-zr-name' x='{x + 12:.1f}' "
                         f"y='{ty + 4:.1f}' fill='{farbe}'>{_esc(a)}"
                         f"</text>")
        chip = 13 if a == EIGEN else 0
        if a == EIGEN:
            teile.append(f"<text class='gr-zr-chip' x='{x + 12:.1f}' "
                         f"y='{ty + 17:.1f}'>unser Angebot</text>")
        if datum:
            teile.append(f"<text class='gr-zr-datum' x='{x + 12:.1f}' "
                         f"y='{ty + 17 + chip + 0:.1f}'>"
                         f"{_datum_kurz(datum)}</text>")
    teile.append("</svg>")
    return "".join(teile)


def _legende_html(anbieter_serien: dict) -> str:
    """EINE Zeile ueber dem Graphen: Name mit Farb-Punkt, Vodafone rot und
    benannt. Der „ab"-Wert (erster Messbetrag) steht im eigenen Span, der
    auf dem breiten Bild ausgeblendet ist - dort traegt ihn das kleine
    Erst-Label im SVG, und eine Zahl steht je Ort genau EINMAL."""
    eintraege = []
    for anbieter in ANBIETER_FOLGE:
        serie = anbieter_serien.get(anbieter)
        if not serie:
            continue
        # "ab" (erster Messbetrag) und "zuletzt" (letzter): am schmalen
        # Bild stehen die Werte HIER, das SVG bleibt kollisionsfrei; am
        # breiten zeigen sie die Labels im Bild, und der Wert-Span ist
        # ausgeblendet - eine Zahl steht je Ort genau EINMAL.
        zusatz = (f" <span class='gr-zr-leg-wert'>ab {_euro0(serie[0][1])}"
                  f" · zuletzt {_euro0(serie[-1][1])}</span>")
        if anbieter == EIGEN:
            zusatz += " <span class='gr-zr-leg-ab'>· unser Angebot</span>"
        eintraege.append(
            f"<span><i style='background:{ANB_FARBE[anbieter]}'></i>"
            f"{_esc(anbieter)}{zusatz}</span>")
    if not eintraege:
        return ""
    return "<div class='gr-zr-legende'>" + "".join(eintraege) + "</div>"


# --------------------------------------------------------------------------
# Der Einstieg
# --------------------------------------------------------------------------

def aufbereiten(state_dir: Path, tco: dict) -> dict:
    """Alles, was die Hauptansicht braucht.

    `tco` ist die Rueckgabe von `geraete_tco_view.aufbereiten()` - dieselben
    Modell-Karten (inklusive Band und Beleg), die die Buendel-Zeilen der
    Seite tragen. Dieses Modul liest ZUSAETZZLICH die rohe Historie
    (`geraete_tco_historie.jsonl`) und die Buendel-Liste
    (`geraete_tco.json`) - reine Lesearbeit, kein Schreibzugriff.
    """
    state_dir = Path(state_dir)
    modelle = tco.get("modelle") or []
    band_katalog = {b["key"]: b for b in tco.get("baender_katalog") or []}
    serien_alle = _serien(state_dir, tco)

    # Die Paare: jedes (Modell, Band) mit mindestens einer Zeile - auch
    # ohne Historie (dann mit dem ehrlichen Leer-Satz).
    paare: list[dict] = []
    erlaubt: dict[str, list[str]] = {}
    for modell in modelle:
        zeilen_je_band = _band_zeilen(modell)
        bands = [b for b, s in zeilen_je_band.items() if s["zeilen"]]
        erlaubt[modell["id"]] = bands
        for band in bands:
            satz = zeilen_je_band[band]
            zeilen = satz["zeilen"]
            serien = serien_alle.get((modell["id"], band), {})
            punkte = sum(len(v) for v in serien.values())
            luecken = _luecken(zeilen, modell.get("karten") or [], band)
            beleg_je = {z["anbieter"]: (z.get("quelle_url") or "",
                                        z.get("abgerufen_am") or "")
                        for z in zeilen}
            leer = None
            if not serien:
                seit = tco.get("historie_lage") or {}
                seit_text = (f"seit dem {_datum_de(seit['seit'])}"
                             if seit.get("seit") else "")
                leer = (f"Für {_kurz_name(modell)} im Band "
                        f"{band_katalog.get(band, {}).get('label', band)} "
                        f"liegt noch keine Messreihe vor - die Zeitreihe "
                        f"beginnt {seit_text} und wächst mit jedem "
                        f"Messtag. Der Stand heute steht in den Bündel-"
                        f"Zeilen darunter.")
            paare.append({
                "modell": modell["id"], "band": band,
                "antwort_html": _antwort_html(
                    modell, band, zeilen, band_katalog.get(band, {})),
                "rechnung_html": _rechnung_html(zeilen),
                "messtage_text": (f"Messtage: {_tag_monat(tage[0])} bis "
                                  f"{_tag_monat(tage[-1])} "
                                  f"({len(tage)}"
                                  f"{' Messung' if len(tage) == 1
                                     else ' Messungen'})")
                if (tage := _messtage(serien)) else "",
                "legende_html": _legende_html(serien),
                "svg_breit": _svg(serien, True, beleg_je),
                "svg_schmal": _svg(serien, False, beleg_je),
                "luecke_text": _luecke_text(luecken, band_katalog),
                "leer_text": leer,
                "anbieter": [a for a in ANBIETER_FOLGE if serien.get(a)],
                "punkte": punkte,
            })
        # Bänder OHNE Zeile kommen nicht in die Auswahl - die Band-Wahl
        # deaktiviert sie (Angebot, nicht Existenz der Option).

    # DER STARTZUSTAND: die meisten Anbieter, dann die meisten Punkte -
    # aus den Serien gerechnet, nichts hardcodiert (der Bestand wächst).
    kandidaten = [(p["modell"], p["band"], len(p["anbieter"]), p["punkte"])
                  for p in paare]
    start = None
    if kandidaten:
        kandidaten.sort(key=lambda k: (-k[2], -k[3], k[0], k[1]))
        start = {"modell": kandidaten[0][0], "band": kandidaten[0][1]}
    start_block = next((p for p in paare if start and
                        p["modell"] == start["modell"]
                        and p["band"] == start["band"]), None)

    # Der Suchindex: deterministisch vorsortiert (Bandabdeckung vor
    # Auslaufware, dann Anbieterzahl, dann Titel) - PM-7. Der JS-Teil
    # filtert nur, er sortiert nicht.
    # Der Vorrat ist KOMPLETT: jedes Modell mit erlaubtem Band steht im
    # Knoten (am echten Bestand 88, rund 9 KB). Die 8er-Kappung aus §1b
    # („≤ 8 Treffer, kein Dropdown mit Riesenliste") gilt der ANZEIGE und
    # liegt allein in app.js - ein Deckel am Vorrat waere eine Auswahl nach
    # Listenposition und versteckte ganze Marken hinter dem Suchfeld (B1,
    # QA 17.09.2026; dieselbe Fehlerklasse wie der Scan-Deckel der
    # Uebersetzungsstufe, CLAUDE.md §6).
    index_modelle = []
    for modell in modelle:
        bands = erlaubt.get(modell["id"]) or []
        if not bands:
            continue
        echte = [k for k in modell.get("karten") or [] if k.get("sku_id")]
        index_modelle.append({
            "id": modell["id"], "titel": modell.get("titel") or modell["id"],
            "hersteller": modell.get("hersteller") or "",
            "speicher": modell.get("speicher"),
            "anbieter_zahl": len({k["anbieter"] for k in echte}),
            "band_zahl": len(bands),
        })
    index_modelle.sort(key=lambda m: (-m["band_zahl"], -m["anbieter_zahl"],
                                      m["titel"]))
    suchindex = index_modelle

    # Die Kacheln: die haeufigsten Geraete - dasselbe Mass wie der
    # Startzustand (Anbieter, dann Punkte), ueber alle Bänder je Modell.
    kachel_werte: dict[str, tuple] = {}
    for p in paare:
        wert = (len(p["anbieter"]), p["punkte"])
        bisher = kachel_werte.get(p["modell"])
        if bisher is None or wert > bisher:
            kachel_werte[p["modell"]] = wert
    titel_je = {m["id"]: m for m in modelle}
    # Zwei Speicherstufen desselben Geraets heissen kurz dasselbe
    # („iPhone 17 Pro" 256 und 512 GB) - auf einer Kachel waeren es
    # ZWILLINGE. Der Kurzname bekommt die GB-Stufe angehaengt, sobald er
    # im Kachelsatz doppelt vorkommt.
    kurze_namen = [_kurz_name(titel_je[mid]) for mid in kachel_werte]
    def _kachel_name(mid: str) -> str:
        kurz = _kurz_name(titel_je[mid])
        if kurze_namen.count(kurz) > 1:
            speicher = titel_je[mid].get("speicher")
            if speicher:
                return f"{kurz} · {speicher} GB"
        return kurz
    kacheln = [{"id": mid, "kurz": _kachel_name(mid),
                "titel": titel_je[mid].get("titel") or mid,
                # Die Meta-Zeile der Kachel: Anbieter mit Messung - dieselbe
                # Zahl, nach der die Kachel gereiht ist (kein zweites Mass).
                "meta": f"{kachel_werte[mid][0]} Anbieter"}
               for mid in sorted(
                   kachel_werte,
                   key=lambda m: (-kachel_werte[m][0],
                                  -kachel_werte[m][1], m))[:KACHELN_MAX]
               if mid in titel_je]

    # Der JSON-Knoten fuer den Client: NUR Titel, Zaehlungen und Erlaubnis
    # - keine Betraege (Regel 1). bnd_titel je Band, damit der Titel der
    # Buendel-Tabelle ohne zweite Quelle wechselt.
    daten = {
        "vorgabe": (start or {}).get("modell", ""),
        "start_band": (start or {}).get("band", ""),
        "modelle_gesamt": tco.get("modelle_gesamt") or len(modelle),
        "suchindex": suchindex,
        "erlaubt": erlaubt,
        "titel": {m["id"]: m.get("titel") or m["id"] for m in modelle},
        "kurz": {m["id"]: _kurz_name(m) for m in modelle},
        "bnd_titel": {
            m["id"]: {band: f"Alle Bündel im Band "
                            f"{band_katalog.get(band, {}).get('label', band)}"
                            f" – {m.get('titel') or m['id']}"
                    for band in erlaubt.get(m["id"]) or []}
            for m in modelle},
        "bnd_titel_ohne": {m["id"]: f"Alle Bündel – {m.get('titel') or m['id']}"
                           for m in modelle},
    }

    return {
        # hat_daten heisst: es gibt mindestens EINEN Messpunkt - ohne
        # Historie steht der ehrliche Leer-Satz je Paar, aber keine Serie.
        "hat_daten": any(p["punkte"] for p in paare),
        "start": start,
        "start_block": start_block,
        "paare": paare,
        "kacheln": kacheln,
        "baender": band_katalog,
        # Die feste Reihenfolge der Band-Knoepfe: klein, mittel, gross -
        # nie alphabetisch (da stuende "gross" zuerst).
        "band_folge": [b for b in ("klein", "mittel", "gross")
                       if b in band_katalog],
        "suchindex": suchindex,
        "daten": daten,
    }


def leer() -> dict:
    """Der Zustand nach einer gescheiterten Aufbereitung.

    Kein "alles leer und gut": die Vorlage meldet den Ausfall sichtbar
    (hat_daten False, paare leer), die übrigen Reiter der Seite bleiben
    davon unberührt - dieselbe Trennung wie `geraete_tco_view.leer()`.
    """
    return {"hat_daten": False, "start": None, "start_block": None,
            "paare": [], "kacheln": [], "baender": {}, "band_folge": [],
            "suchindex": [], "daten": {"vorgabe": "", "start_band": "",
                                       "modelle_gesamt": 0, "suchindex": [],
                                       "erlaubt": {}, "titel": {},
                                       "kurz": {}, "bnd_titel": {},
                                       "bnd_titel_ohne": {}}}
