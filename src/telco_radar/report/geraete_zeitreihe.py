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

from ..tco_model import (Buendel, POSTEN_ANSCHLUSS, POSTEN_BUENDEL,
                         POSTEN_RATE, POSTEN_ZUZAHLUNG, TCO_HORIZONT, tco_24)
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

# E4-Sichtbarkeit: ein AUTO angelegtes Modell wird in der WAHL dieser
# Ansicht erst ab dieser Zahl unterschiedlicher Messtage gefuehrt (der
# Katalog-Reiter zeigt es ab Tag 1, die Listung existiert ab Tag 1).
AUTO_SICHTBAR_AB_MESTAGEN = 2

# P1 (STRATEGIE_GERAETE_V3, 17.09.2026): der Rechenweg je Messung. Der
# Satz des Leerzustands fuer die Vodafone-NAEHERUNG ist WOERTLICH der
# Hinweis aus `_geraete_buendel.html.j2` („gr-kk-hinweis") - nicht neu
# erfunden. Ein Test haelt beide zusammen, denn derselbe Vorbehalt an
# zwei Orten driftet, sobald nur einer geaendert wird.
_NAEHERUNG_SATZ = ("Referenzrechnung, kein Angebot: der Vodafone-Bündelpreis "
                   "zu diesem Gerät ist noch nicht erhoben – gerechnet aus "
                   "dem eigenen Barpreis des Geräts und dem Tarifgrundpreis "
                   "aus dem Produktinformationsblatt")
_NAEHERUNG_KEIN_WEG = (" Für die Näherung gibt es keine Messung je Messtag – "
                       "deshalb steht hier keine Rechung.")


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


def _satz_name(modell: dict) -> str:
    """Der Name im Antwort-Satz: MIT Hersteller, wenn der Katalog ihn kennt.

    `_kurz_name` schneidet den Hersteller fuer Kacheln und Vorschauen ab -
    im Fliesstext liest sich „Beim 17 im Band Mittel" (Xiaomi 17) als Zahl
    ohne Bezug. Der Satz nennt deshalb den Hersteller aus dem Katalog-/Auto-
    Eintrag vor dem Kurznamen. Fehlt er im Eintrag, bleibt der Kurzname
    stehen - geraten wird nichts (Antonios Regel: keine Vermutung, wo der
    Katalog schweigt).
    """
    kurz = _kurz_name(modell)
    hersteller = (modell.get("hersteller") or "").strip()
    if not hersteller or kurz == hersteller or kurz.startswith(
            hersteller + " "):
        return kurz
    return f"{hersteller} {kurz}"


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
    name = _esc(_satz_name(modell))
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
        # E3-Fix (QA 17.09.2026, B1): Die Zeilen stehen AUFSTEIGEND, der
        # Beste liegt also IMMER unter der Referenz, sobald Vodafone nicht
        # selbst fuehrt - die Differenz ist sein Abstand nach UNTEN, und
        # "ueber" war immer falsch gepolt. Dieselbe Richtungssprache wie
        # die Buendel-Karten (S4): unter heisst guenstiger.
        satz += (f" — <b class='gr-zr-zahl'>"
                 f"{_euro(round(eigen['gesamt'] - beste['gesamt'], 2))}"
                 f"</b> unter der Vodafone-Referenz ({_euro(eigen['gesamt'])}"
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
# P1: der Rechenweg EINER Messung - Postenliste und <template>-Bloecke
# --------------------------------------------------------------------------

def _rechung(messung: dict) -> dict | None:
    """Die Postenliste EINER Messung aus der Historien-Zeile.

    Die Rechnung selbst ist `tco_24` - dieselbe reine Funktion, deren
    Ergebnis der Sammellauf als `gesamt` eingefroren hat (alle 2562
    Zeilen des Bestands ergeben sie als reine Summe, nachgerechnet in
    vergleich.md und hier gegen jeden echten Testfall). Dieses Modul
    ZERLEGT sie nur fuer die Anzeige: der `betrag` je Posten kommt aus
    `Tco.bestandteile`, nichts wird hier neu addiert. Es gibt genau zwei
    Preisformen (aufgeteilt: Tarif und Rate getrennt; zusammen: 1&1 nennt
    EINEN Bündelmonatspreis) - Boni und Geraeteanteil stehen nicht in der
    Historie und erscheinen deshalb nicht (kein Posten wird erfunden).

    Die Schluessel von `bestandteile` werden EXAKT konstruiert, wie
    `tco_24` sie schreibt - ein startswith-Praefix wuede eine stille
    Umbenennung dort ueberhoeren; hier fehlt der Posten und die Summe
    geht nicht auf, was der Summen-Test meldet.
    """
    satz, stand = messung["satz"], messung["stand"]
    try:
        b = Buendel(
            sku_id=stand.get("sku_id") or "",
            anbieter=stand.get("anbieter") or "?",
            tarif_name=stand.get("tarif_name") or "",
            tarif_id=satz.get("tarif_id") or "",
            tarif_monatlich=satz.get("tarif_monatlich"),
            tarif_bindung_monate=satz.get("tarif_bindung_monate"),
            buendel_monatlich=satz.get("buendel_monatlich"),
            geraet_zuzahlung=satz.get("geraet_zuzahlung"),
            geraet_monatsrate=satz.get("geraet_monatsrate"),
            laufzeit_monate=int(satz.get("laufzeit_monate") or 24),
            anschlusspreis=satz.get("anschlusspreis"),
            zustand=satz.get("zustand") or "",
            quelle_url=satz.get("quelle_url") or "",
            abgerufen_am=satz.get("abgerufen_am") or "")
    except (ValueError, TypeError) as exc:
        log.warning("Rechenweg: Messung %s am %s nicht als Buendel lesbar "
                    "(%s) - kein Panel fuer diesen Punkt.",
                    satz.get("id"), satz.get("datum"), exc)
        return None
    t = tco_24(b)
    if t.gesamt is None:
        return None
    lz = b.laufzeit_monate
    im = min(lz, TCO_HORIZONT)

    posten: list[dict] = []

    def _posten(label: str, betrag, anzahl=None, einzeln=None, klammer=""):
        if betrag is None:
            return
        posten.append({"label": label, "anzahl": anzahl, "einzeln": einzeln,
                       "betrag": betrag, "klammer": klammer})

    _posten(POSTEN_ZUZAHLUNG, t.bestandteile.get(POSTEN_ZUZAHLUNG))
    _posten(POSTEN_ANSCHLUSS, t.bestandteile.get(POSTEN_ANSCHLUSS))
    if b.buendel_monatlich is not None:
        _posten(POSTEN_BUENDEL,
                t.bestandteile.get(f"{POSTEN_BUENDEL} ({im} von {lz})"),
                anzahl=im, einzeln=b.buendel_monatlich,
                klammer=f"{im} von {lz} Monaten" if lz != im else "")
    else:
        _posten("Tarif", t.bestandteile.get(
                    f"Tarif über {TCO_HORIZONT} Monate"),
                anzahl=TCO_HORIZONT, einzeln=b.tarif_monatlich)
        _posten(POSTEN_RATE, t.bestandteile.get(
                    f"Geräteraten ({im} von {lz})"),
                anzahl=im, einzeln=b.geraet_monatsrate,
                klammer=f"{im} von {lz} Raten" if lz != im else "")

    # Die Gegenprobe: die Posten muessen die eingefrorene Leitzahl ergeben.
    # Tun sie es nicht, ist der DATENSATZ inkonsistent - das Protokoll
    # sagt es, das Panel zeigt trotzdem die Zerlegung dieser einen
    # Rechnung (nichts wird zurechtgebogen).
    summe = round(sum(p["betrag"] for p in posten), 2)
    if summe != round(float(satz.get("gesamt")), 2):
        log.warning("Rechenweg: Posten von %s am %s ergeben %s, eingefroren "
                    "ist %s - der Punkt und das Panel weichen ab.",
                    satz.get("id"), satz.get("datum"), summe,
                    satz.get("gesamt"))
    # P1-Fix (Sicht-A3, 17.09.2026): die Restschuld nach Monat 24 - die
    # Zahl, die den TCO-24 vergleichbar macht. Sie ist KEIN neuer Posten
    # und zaehlt NICHT in die Summe: sie verlaengert dieselbe Rate ueber
    # den Horizont hinaus (lz - 24 Monate), dieselbe Zerlegung wie tco_24,
    # nur den Rest der Laufzeit betraffend. Bei 24 Monaten gibt es sie
    # nicht (None heisst: nichts offen - eine ehrliche Aussage, kein
    # fehlender Wert).
    offen = None
    monatlich = (b.geraet_monatsrate if b.buendel_monatlich is None
                 else b.buendel_monatlich)
    if lz > TCO_HORIZONT and monatlich is not None:
        offen = {"anzahl": lz - TCO_HORIZONT, "einzeln": monatlich,
                 "betrag": round((lz - TCO_HORIZONT) * monatlich, 2)}
    return {"posten": posten, "gesamt": t.gesamt, "offen": offen,
            "datum": satz.get("datum") or "",
            "quelle_url": satz.get("quelle_url") or "",
            "abgerufen_am": satz.get("abgerufen_am") or ""}


def _rechung_html(anbieter: str, messung: dict) -> str:
    """EINE Messung als fertiger Block - die gesetzte Rechung.

    Struktur (fuer das Klick-Panel, siehe schnittstelle-rechenweg.md):
    Kopf (Anbieter mit Farb-Punkt wie seine Linie im Graphen, Messtag),
    Postenliste (Label, `anzahl × einzeln = betrag`; einmalige Posten ohne
    Faktor; je Posten ein BALKEN in Breite seines Anteils an der Summe -
    P1-Fix Sicht-A2: „nicht nur Zeilen", die Breite ist eine fertige
    Prozentangabe aus dieser einen Rechnung, der Client setzt nichts),
    Summe mit dem Label der Leitzahl, die Restschuld nach Monat 24
    (Sicht-A3) und den Beleg mit Abrufdatum DIESES Messtags (nicht von
    heute - das ist der Unterschied zum statischen „So gerechnet"-Satz).
    """
    r = _rechung(messung)
    if r is None or not r["posten"]:
        return ""
    a = _esc(anbieter)
    punkt = (f"<i class='gr-zr-rpunkt' style='background:"
             f"{ANB_FARBE.get(anbieter, '#333333')}' aria-hidden='true'>"
             f"</i>")
    teile = ["<div class='gr-zr-rech'>",
             f"<p class='gr-zr-rkopf'>{punkt}<strong>{a}</strong> · Messung "
             f"vom {_esc(_datum_de(r['datum']))}</p>",
             "<ul class='gr-zr-posten'>"]
    for p in r["posten"]:
        if p["anzahl"] is not None and p["einzeln"] is not None:
            ausdruck = (f"{p['anzahl']} × {_euro(p['einzeln'])} "
                        f"<span class='gr-zr-pg'>= {_euro(p['betrag'])}"
                        f"</span>")
        else:
            ausdruck = _euro(p["betrag"])
        klammer = (f" <span class='gr-zr-pk'>{_esc(p['klammer'])}</span>"
                   if p["klammer"] else "")
        anteil = (f"{p['betrag'] / r['gesamt'] * 100:.1f}%"
                  if r["gesamt"] else "0%")
        teile.append(f"<li class='gr-zr-posten'>"
                     f"<span class='gr-zr-pn'>{_esc(p['label'])}</span>"
                     f"<span class='gr-zr-pbar'><i style='width:{anteil}"
                     f"'></i></span>"
                     f"<span class='gr-zr-pr'>{ausdruck}{klammer}</span>"
                     f"</li>")
    teile.append("</ul>")
    teile.append(f"<p class='gr-zr-rsumme'>= <b>{_euro(r['gesamt'])}</b> "
                 f"<span class='gr-zr-plabel'>TCO-{TCO_HORIZONT}</span></p>")
    if r["offen"] is not None:
        teile.append(f"<p class='gr-zr-roffen'>danach noch offen: "
                     f"{r['offen']['anzahl']} × {_euro(r['offen']['einzeln'])}"
                     f" = {_euro(r['offen']['betrag'])}</p>")
    url = r["quelle_url"]
    link = (f"<a href='{_esc(url)}' target='_blank' rel='noopener'>{a}"
            f"&nbsp;↗</a>" if url else a)
    # Das Abrufdatum in der Kurzform (15.09.2026): der Kopf nennt den
    # Messtag ausgeschrieben, hier zaehlt jede Byte-Wiederholung - das
    # Fragment traegt 1285 dieser Bloecke (PM-6).
    datum_teil = (f", abgerufen {_esc(_datum_kurz(r['abgerufen_am']))}"
                  if r["abgerufen_am"] else "")
    teile.append(f"<p class='gr-zr-rbeleg'>Beleg: {link}{datum_teil}.</p>")
    teile.append("</div>")
    return "".join(teile)


def _naeherung_html() -> str:
    """Der benannte Leerzustand der Vodafone-Naeherung.

    Die Naehrungskarte ist eine gerechnete Referenz (PIB-Tarif plus
    eigener Barpreis), kein Bündel der Historie - es gibt keine Messung
    je Messtag und damit keinen Rechenweg dieses Panels. Der erste Satz
    ist wortgleich der Hinweis von der Bündel-Karte (`_NAEHERUNG_SATZ`),
    nur der Grund des Leerzustands kommt dazu.
    """
    return (f"<div class='gr-zr-rech gr-zr-rech--leer' data-anb='{EIGEN}' "
            f"data-m='naeherung'><p class='gr-zr-rkopf'><strong>{EIGEN}"
            f"</strong> · Referenzrechnung</p>"
            f"<p class='gr-zr-rleer'>{_esc(_NAEHERUNG_SATZ)}"
            f"{_esc(_NAEHERUNG_KEIN_WEG)}</p></div>")


def _rechenwege_html(messungen_paar: dict, zeilen: list) -> str:
    """Je Serie/Messung ein <template data-m=...> unter dem SVG (V1).

    Der Server liefert die fertige Rechung JE MESSUNG als inerte Vorlage;
    der Client setzt sie bei Klick nur noch ein (app.js montiert, es
    rechnet nichts - Regel 1). Der Container ist `hidden`: ohne Klick
    kostet er keinen Platz. Die Naeherung bekommt EINEN Leerzustand-
    Block mit `data-m='naeherung'`, damit jede klickbare Vodafone-Zahl
    dieses Paars eine Antwort findet.
    """
    bloecke: list[str] = []
    for anbieter in ANBIETER_FOLGE:
        saetze = messungen_paar.get(anbieter)
        if not saetze:
            continue
        for datum in sorted(saetze):
            inhalt = _rechung_html(anbieter, saetze[datum])
            if inhalt:
                bloecke.append(f"<template data-anb='{_esc(anbieter)}' "
                               f"data-m='{_esc(datum)}'>{inhalt}</template>")
    if any(z.get("naeherung") for z in zeilen):
        bloecke.append(f"<template data-anb='{EIGEN}' data-m='naeherung'>"
                       f"{_naeherung_html()}</template>")
    if not bloecke:
        return ""
    return ("<div class='gr-zr-rechnungen' hidden>" + "".join(bloecke)
            + "</div>")


# --------------------------------------------------------------------------
# Die Zeitreihe selbst - Serien und SVG
# --------------------------------------------------------------------------

def _messungen(state_dir: Path, tco: dict) -> dict:
    """{(modell, band): {anbieter: {datum: MESSUNG}}} aus der Historie.

    Eine MESSUNG ist das dict `{"satz": <Historien-Zeile>, "stand":
    <Buendel-Eintrag aus geraete_tco.json>}`. Die eingefrorene Leitzahl
    `gesamt` je (buendel_id, datum) ist der Punkt; je (Modell, Band,
    Anbieter, Tag) zaehlt das GUENSTIGSTE Buendel (Farben sind Preis-
    dimensionen). Ein fehlender Tag bleibt fehlend.

    P1 (17.09.2026): die Zeile wird GANZ behalten, nicht nur ihr `gesamt` -
    aus ihren Messfeldern baut `_rechung` die Postenliste. Bei gleichem
    `gesamt` gewinnt die ZEILE, die zuerst gelesen wurde (strikt `<`),
    exakt dieselbe Regel wie vorher nur mit dem Wert.
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

    messungen: dict[tuple, dict] = {}
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
        slot = (messungen.setdefault((modell, band), {})
                .setdefault(b.get("anbieter") or "?", {}))
        alt = slot.get(datum)
        if alt is None or float(gesamt) < float(alt["satz"]["gesamt"]):
            slot[datum] = {"satz": satz, "stand": b}
    return messungen


def _serien_aus(messungen: dict) -> dict:
    """{(modell, band): {anbieter: [[iso, wert], ...]}} - die Punktliste.

    Die reine Ableitung aus `_messungen`: je Datum der eingefrorene Wert.
    Beide Formen entstehen aus EINER Lesung der Historie - zwei Lesungen
    waeren zwei Zeitreihen, sollte die Datei zwischen ihnen wachsen.
    """
    fertig: dict[tuple, dict] = {}
    for schluessel, anbieter_ in messungen.items():
        fertig[schluessel] = {
            an: sorted((d, float(m["satz"]["gesamt"]))
                       for d, m in werte.items())
            for an, werte in anbieter_.items()}
    return fertig


def _serien(state_dir: Path, tco: dict) -> dict:
    """Die Serien in der Form, die der Graph liest (siehe `_serien_aus`)."""
    return _serien_aus(_messungen(state_dir, tco))


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
        serie = anbieter_serien[a]
        for i, (d, wert) in enumerate(serie):
            x, y = x_v(d), y_v(wert)
            ende = i == len(serie) - 1
            einzeln = len(serie) == 1
            # P1: jeder Punkt traegt Anbieter und Messtag - der Rechenweg
            # dieser EINEN Messung steht als <template> unter dem SVG.
            daten = f" data-anb='{_esc(a)}' data-m='{_esc(d)}'"
            # P1-Fix (Sicht 15, 17.09.2026): eine Serie mit EINEM Messtag
            # bekommt einen Halo - „erstmals gemessen". Ein nackter Punkt
            # ohne Linie liest sich sonst wie ein Fehler; kommt der zweite
            # Messtag, wird die Serie zur Linie und der Halo verschwindet
            # (er haengt an der Laenge der Serie, nicht an einem Flag im
            # Store).
            if einzeln:
                teile.append(f"<circle class='gr-zr-halo' cx='{x:.1f}' "
                             f"cy='{y:.1f}' r='9.5' fill='none' "
                             f"stroke='{farbe}'/>")
            teile.append(
                f"<circle class='gr-zr-punkt"
                f"{' gr-zr-ende' if ende else ''}' cx='{x:.1f}' "
                f"cy='{y:.1f}' r='{6 if ende else 4.5}' fill='{farbe}'"
                f"{daten}/>")
            # ... und eine unsichtbare Trefferflaeche darueber (r=12 statt
            # 4,5 - Strategie P1): ein 4,5-px-Kreis ist auf dem Telefon
            # nicht zu treffen. `gr-zr-hit`, NICHT `gr-zr-treffer` - die
            # Klasse gehoert der Suchvorschau (style.css). Das <title>-Kind
            # ist die Hover-Vorschau vor dem Klick (Sicht 11): Anbieter,
            # Messtag und Betrag als fertige Zeichenkette - der Browser
            # zeigt sie als nativen Tooltip, nichts wird im Client gebaut.
            einmal = " · erstmals gemessen" if einzeln else ""
            teile.append(f"<circle class='gr-zr-hit' cx='{x:.1f}' "
                         f"cy='{y:.1f}' r='12' fill='transparent'"
                         f"{daten}><title>{_esc(a)} · {_tag_monat(d)} · "
                         f"{_euro0(wert)}{einmal}</title>"
                         f"</circle>")

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


def _anbieter_punkte(anbieter: list) -> str:
    """P1/F3 (A3): die Punkte-Reihe der Modell-Karte - je Anbieter der
    Zeitreihe EIN Punkt in seiner Hausfarbe (ANB_FARBE, dieselbe Farbe wie
    seine Linie im Graphen). Die Punkte SIND die Anbieterzahl der Karte;
    ein zusaetzlicher Text \"N Anbieter\" waere dieselbe Zahl ein zweites
    Mal am selben Ort (Beruhigungsregel)."""
    return "".join(
        f"<i style='background:{ANB_FARBE.get(a, '#333333')}' "
        f"title='{_esc(a)}'></i>" for a in anbieter)


def _bewegung(serien: dict) -> dict | None:
    """P1/F3 (A3): das Bewegungs-Delta der Karte - PREIS-FRONT am ersten
    gegen letzten Messtag des Leit-Paares.

    Die Front ist der guenstigste Wert je Messtag (Minimum ueber alle
    Anbieter mit Messung an diesem Tag) - dasselbe Mass, das den ab-Preis
    der Karte bestimmt, nur auf Anfang und Ende der Reihe bezogen. Beide
    Betraege stehen eingefroren in der Historie; nichts wird interpoliert
    (Regel 2). Unter zwei Messtagen gibt es keine Bewegung - dann ist das
    Feld None und die Karte zeigt keins."""
    tage = _messtage(serien)
    if len(tage) < 2:
        return None
    spanne = (date.fromisoformat(tage[-1])
              - date.fromisoformat(tage[0])).days
    if spanne < 1:
        return None

    def _front(tag: str) -> float:
        return min(w for punkte in serien.values()
                   for d, w in punkte if d == tag)

    delta = round(_front(tage[-1]) - _front(tage[0]), 2)
    zeit = f"in {spanne} Tag" if spanne == 1 else f"in {spanne} Tagen"
    if delta > 0:
        return {"text": f"↑ +{_euro0(delta)} {zeit}",
                "richtung": "steigt"}
    if delta < 0:
        return {"text": f"↓ −{_euro0(-delta)} {zeit}",
                "richtung": "sinkt"}
    return {"text": f"±0 € {zeit}", "richtung": "gleich"}


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
    messungen_alle = _messungen(state_dir, tco)
    serien_alle = _serien_aus(messungen_alle)
    if messungen_alle:
        log.info("Zeitreihe: %d Messungen gelesen.", sum(
            len(saetze) for pa_ in messungen_alle.values()
            for saetze in pa_.values()))

    # E4-SICHTBARKEIT: ein AUTO angelegtes Modell steht in der WAHL (Such-
    # index, Kacheln, Paare) erst ab 2 Messtagen. Die Listung existiert ab
    # Tag 1 und der KATALOG-Reiter zeigt das Geraet ab Tag 1 - aber die
    # Zeitreihe ist eine TCO-Aussage, und ein Messtag ist noch keine; zwei
    # Naechte Bestand bestätigen ausserdem, dass der strukturierte Name kein
    # Einmal-Fund war. Hand-Eintraege gelten unbegrenzt (der Mensch hat
    # entschieden, dass das Geraet verfolgt wird). KEIN Deckel am Vorrat
    # im Sinne von QA-B1: die Regel ist eine Sichtbarkeitsentscheidung aus
    # der Messlage, keine Auswahl nach Listenposition.
    messtage_je_modell: dict[str, set] = {}
    for (mid, _band), anbieter_serien in serien_alle.items():
        messtage_je_modell.setdefault(mid, set()).update(
            _messtage(anbieter_serien))
    wahl = [m for m in modelle
            if not m.get("auto")
            or len(messtage_je_modell.get(m["id"], ())) >=
            AUTO_SICHTBAR_AB_MESTAGEN]
    wahl_ids = {m["id"] for m in wahl}
    verdeckt = sorted(m.get("titel") or m["id"] for m in modelle
                      if m["id"] not in wahl_ids)
    if verdeckt:
        log.info("Zeitreihe: %d Auto-Modell(e) unter %d Messtagen - noch "
                 "nicht waehlbar: %s", len(verdeckt),
                 AUTO_SICHTBAR_AB_MESTAGEN, ", ".join(verdeckt))

    # Die Paare: jedes (Modell, Band) mit mindestens einer Zeile - auch
    # ohne Historie (dann mit dem ehrlichen Leer-Satz).
    paare: list[dict] = []
    erlaubt: dict[str, list[str]] = {}
    # P1/F3 (A3) + P1-Fix (Sicht-B2/S3-4, 17.09.2026): die Werte der
    # MODELL-KARTEN - JE BAND, nicht ueber alle Bänder gemischt. Bis zur
    # Abnahme kombinierte die Karte den ab-Preis ueber ALLE Bänder mit
    # Bewegung und Punkten des LEIT-Paares (bandunabhaengig): zwei
    # Maßstäbe auf einer Karte und eine Kartenreihe, die auf den
    # Band-Umschalter nicht reagierte. Jetzt trägt JEDES Band des Modells
    # seinen eigenen Satz (bester ECHTER TCO, Ø/Monat, Bewegung, Punkte)
    # - alles aus DEM Band, ein Maßstab. Die Vodafone-NAEHERUNG ist kein
    # Angebot und trägt den ab-Preis nicht (Band ohne echtes Angebot:
    # ab=None -> die Karte zeigt „—").
    karten_baender: dict[str, dict[str, dict]] = {}
    for modell in wahl:
        zeilen_je_band = _band_zeilen(modell)
        bands = [b for b, s in zeilen_je_band.items() if s["zeilen"]]
        erlaubt[modell["id"]] = bands
        for band in bands:
            satz = zeilen_je_band[band]
            zeilen = satz["zeilen"]
            serien = serien_alle.get((modell["id"], band), {})
            punkte = sum(len(v) for v in serien.values())
            eintrag = {"ab": None, "ab_monat": None, "anb": None,
                       "delta_text": None, "delta_richtung": None,
                       "punkte_html": "", "anbieter_text": ""}
            echt = next((z for z in zeilen if not z.get("naeherung")
                         and z.get("gesamt") is not None), None)
            if echt is not None:
                eintrag["ab"] = _euro(echt["gesamt"])
                eintrag["ab_monat"] = _schnitt(echt)
                eintrag["anb"] = echt["anbieter"]
            if serien:
                band_anbieter = [a for a in ANBIETER_FOLGE if serien.get(a)]
                eintrag["punkte_html"] = _anbieter_punkte(band_anbieter)
                eintrag["anbieter_text"] = ", ".join(band_anbieter)
                bew = _bewegung(serien)
                if bew:
                    eintrag["delta_text"] = bew["text"]
                    eintrag["delta_richtung"] = bew["richtung"]
            karten_baender.setdefault(modell["id"], {})[band] = eintrag
            mess = messungen_alle.get((modell["id"], band), {})
            luecken = _luecken(zeilen, modell.get("karten") or [], band)
            beleg_je = {z["anbieter"]: (z.get("quelle_url") or "",
                                        z.get("abgerufen_am") or "")
                        for z in zeilen}
            leer = None
            if not serien:
                seit = tco.get("historie_lage") or {}
                seit_text = (f"seit dem {_datum_de(seit['seit'])}"
                             if seit.get("seit") else "")
                leer = (f"Für {_satz_name(modell)} im Band "
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
                # P1: die fertige Rechung je Messung als <template>-Blöcke
                # unter dem SVG - der Client montiert sie nur noch.
                "rechenweg_html": _rechenwege_html(mess, zeilen),
                "luecke_text": _luecke_text(luecken, band_katalog),
                "leer_text": leer,
                "anbieter": [a for a in ANBIETER_FOLGE if serien.get(a)],
                "punkte": punkte,
            })
        # Bänder OHNE Zeile kommen nicht in die Auswahl - die Band-Wahl
        # deaktiviert sie (Angebot, nicht Existenz der Option).

    # DER STARTZUSTAND: die meisten Anbieter, dann die meisten Punkte -
    # aus den Serien gerechnet, nichts hardcodiert (der Bestand wächst).
    vorlagen = sum(p["rechenweg_html"].count("<template") for p in paare)
    if vorlagen:
        log.info("Zeitreihe: %d Rechenweg-Vorlagen (je Messung) gebaut, "
                 "%d Punkte in den Serien.", vorlagen,
                 sum(p["punkte"] for p in paare))
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
    # P1/F3 (A3) + P1-Fix (Sicht-B2): aus den einzeiligen Chips sind
    # MODELL-KARTEN geworden - der Schnelleingang traegt je Band seinen
    # ab-Preis, die Bewegung und die Anbieter-Punkte (alles aus DEM Band,
    # siehe karten_baender oben). Reihung und Obergrenze bleiben
    # UNVERAENDERT (Anbieterzahl vor Punkten ueber alle Bänder, PM-7;
    # KACHELN_MAX=6). Ein Band ohne echtes Angebot (nur Naeherung) zeigt
    # kein geratenes Feld, sondern den benannten Leerzustand „—" - die
    # Vorlage entscheidet das, hier ist ab einfach None.
    kacheln = []
    for mid in sorted(
            kachel_werte,
            key=lambda m: (-kachel_werte[m][0],
                           -kachel_werte[m][1], m))[:KACHELN_MAX]:
        if mid not in titel_je:
            continue
        kacheln.append({
            "id": mid, "kurz": _kachel_name(mid),
            "titel": titel_je[mid].get("titel") or mid,
            # Reihenfolge wie die Band-Knoepfe (klein, mittel, gross) -
            # nie alphabetisch; band_folge ist unten definiert, deshalb
            # erst nach ihm sortiert (Band-Katalog ist die Quelle).
            "baender": {b: karten_baender.get(mid, {}).get(b)
                        for b in ("klein", "mittel", "gross")
                        if karten_baender.get(mid, {}).get(b)},
        })

    # Der JSON-Knoten fuer den Client: NUR Titel, Zaehlungen und Erlaubnis
    # - keine Betraege (Regel 1). bnd_titel je Band, damit der Titel der
    # Buendel-Tabelle ohne zweite Quelle wechselt.
    daten = {
        "vorgabe": (start or {}).get("modell", ""),
        "start_band": (start or {}).get("band", ""),
        # Die Trefferzahl des Suchfelds meint die WAHL-Menge - nicht die
        # Modellzahl der Hauptansicht (tco.modelle_gesamt): ein Auto-Modell
        # unter der Messtag-Schwelle ist nicht auffindbar und darf nicht
        # mitgezaehlt werden (die Zahl meint die Menge, CLAUDE.md-Regel).
        "modelle_gesamt": len(wahl),
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
