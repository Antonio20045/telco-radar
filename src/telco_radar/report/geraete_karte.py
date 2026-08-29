"""Die Preis-Positionskarte des Geraeteradars, gerechnet statt gezeichnet.

WARUM DIESES MODUL NEU IST. Die erste Fassung stand in `geraete_view._karte`
und hatte einen Fehler, den kein Test gefunden hat, weil ihn niemand ansah:
Etiketten wurden je Spalte sequenziell mit 14 px Mindestabstand nach unten
GESTAPELT, waehrend der Punkt auf seinem Preis stehenblieb. Am ausgelieferten
Stand vom 11.08.2026 gemessen stand "iPhone 17 · 512 GB" 181 px unter seinem
Punkt - auf Hoehe der 175-EUR-Linie, bei einem echten Preis von 1199 EUR. In
der Anbieteransicht waren es 235 px. 87 von 94 Etiketten lagen weiter als drei
Prozent daneben. Wer die Grafik las, wie man Grafiken liest, las um den Faktor
sieben falsch.

DREI REGELN, die das nicht wiederkommen lassen:

1. **Die Y-Achse gehoert dem Preis.** Jede Ausweichbewegung geht nach RECHTS.
   Ein Etikett steht nie weiter als `MAX_VERSATZ` von seinem Punkt; passt es
   dort nicht hin, wird es WEGGELASSEN. Eine Luecke ist ehrlich, eine
   Verschiebung ist eine Falschaussage. Es gibt in diesem Modul keinen
   Codepfad, der `label_y` unabhaengig von `cy` setzt - das ist der
   eigentliche Unterschied zu `ly = max(cy, letzte + 14)`.
2. **Gezeichnet werden Preispunkte, keine SKUs.** Fuenf Farben desselben
   iPhone 17 mit 512 GB kosten alle 1199 EUR und ergaben fuenf deckungsgleiche
   Kreise mit fuenf Etiketten - 60 der 85 Kreise lagen exakt aufeinander, es
   gab nur 25 unterschiedliche Koordinaten. Farbe ist keine Preisdimension;
   sie gehoert in den Tooltip und in die SKU-Matrix.
3. **Was im Zeichenbereich steht, traegt eine Preisaussage** und heisst
   deshalb `gr-etikett`. Beschriftungen UNTER der Achse (Spalten- und
   Bandnamen, `gr-bandname`) tragen keine. Der Abnahmetest rechnet aus jeder
   Etikettenhoehe den Preis zurueck; diese Trennung ist die Voraussetzung
   dafuer, dass er etwas misst - und sie wird BEIDSEITIG geprueft, damit die
   Ausnahme kein Schlupfloch wird.

ZWEI FORMEN, eine Aufbereitung:

- `FORM_BAND` - ein senkrechtes Preisband je Modell, von seinem guenstigsten
  bis zu seinem teuersten Speicher, mit einem Querstrich je Speicherstufe.
  Der Modellname steht UNTER der Achse, gedreht. Die dichteste und ruhigste
  Form: aus 38 Apple-Punkten werden fuenf Baender.
- `FORM_CHIP` - ein Rechteck je (Modell, Speicher) mit dem Text IM Chip, bei
  Ueberlappung waagerecht gepackt. Naeher an der Canalys-Vorlage.

BREITE VOR HOEHE. Die Seite gibt 1184 px Inhaltsbreite her (`--wrap: 1240px`
minus 2x28 px Polster), die alte SVG deckelte bei 980 und verschenkte 200
davon. Gemessen an den echten Daten hebt der Schritt auf 1180 px die Zahl der
Chipbahnen je Spalte von drei auf vier und spart damit 360 px Hoehe - Breite
ist bei diesem Problem das wertvollere Mittel. Deshalb waechst die Hoehe erst,
wenn die Breite ausgereizt ist.

DIE SPALTENREGEL IST FORMABHAENGIG, und das ist gerechnet, nicht Geschmack:
Chips brauchen GLEICH breite Spalten (proportional bekaeme Samsung mit sechs
Punkten nur eine Bahn und braeuchte 1105 px Hoehe), Baender brauchen
PROPORTIONALE (dort zaehlen Schlitze, nicht Punktdichte).
"""
from __future__ import annotations

from ..geraete_model import VERGLEICHBARE_ZUSTAENDE

# Die Zeichenflaeche. 1180 = 1240 (--wrap) - 2x28 (Polster), also auf dem
# Schreibtisch 1:1 ohne Herunterskalieren.
BREITE = 1180
RAND_L, RAND_R, RAND_O = 66, 18, 20
# Baender brauchen unter der Achse Platz fuer den gedrehten Modellnamen.
RAND_U_CHIP, RAND_U_BAND = 70, 148

HOEHE_MIN, HOEHE_MAX = 540, 900

Y_SCHRITT = 200
# Untergrenze der Preisachse. Die Kehrseite der Nullpunkt-Regel: ein Portfolio
# aus reinen Einstiegsgeraeten draengt sich sonst im untersten Zehntel.
Y_MINDEST = 800

# Die Kernregel: so weit darf ein Etikett hoechstens von seinem Punkt stehen.
# Es ist kein Spielraum, sondern ein Budget, das die Grundlinienkorrektur
# fast vollstaendig aufbraucht - genau so ist es gemeint.
MAX_VERSATZ = 12

# Ein SVG-Text sitzt auf seiner GRUNDLINIE. Der Betrag gehoert ins Modul und
# nicht in die Vorlage: im ersten Lauf mit echten Daten stand er dort
# (`y="{{ p.ly + 3 }}"`), waehrend der Deckel hier gegen `ly` rechnete -
# jedes gedeckelte Etikett lag drei Pixel unter der Nulllinie.
BASISLINIE = 3.5

# Schriftgroesse der Etiketten. NIE unter 10: die alte Fassung ging im Media
# Query auf 8 px, was auf einem 390-px-Telefon bei einer auf Containerbreite
# gestauchten SVG real 2,7 CSS-Pixel ergab.
SCHRIFT = 10.0
ZEICHENBREITE = 5.1

CHIP_HOEHE = 15.0
CHIP_LUFT_X, CHIP_LUFT_Y = 6.0, 2.0
CHIP_TEXT_DX, CHIP_POLSTER_R = 11.0, 6.0
CHIP_RAND = 4.0

RADIUS, RADIUS_EIGEN = 4, 6

BAND_STRICH = 6.0
BAND_KAPPE_HALB = 11.0
BAND_KAPPE_DX = 14.0
# Zwei Speicherstufen, die weniger als das auseinanderliegen, werden zu EINEM
# Querstrich verschmolzen - sonst entstuenden wieder deckungsgleiche Punkte.
BAND_STUFE_MIN = 6.0
# Der gedrehte Modellname beginnt UNTER der Spaltenbeschriftung, die bei
# achse_y + 16 sitzt. Wer ihn hoeher setzt, laesst beide uebereinanderliegen.
BAND_NAME_DY = 32.0

FORM_CHIP, FORM_BAND = "chip", "band"
FORMEN = (FORM_BAND, FORM_CHIP)

# Achsenparameter je Preisart. Der Eintrag "mit_vertrag" traegt den dritten
# Schalter, ohne dass an der Geometrie etwas umgebaut werden muss: eine
# Zuzahlung von 49 EUR auf einer 2600-EUR-Achse waere ein Punkt auf der
# Nulllinie.
ACHSE = {
    "ohne_vertrag": {"schritt": 200, "mindest": 800},
    "mit_vertrag": {"schritt": 50, "mindest": 200},
}


def kuerze(text: str, breite_px: float) -> str:
    """Auf den verfuegbaren Platz kuerzen - oder "" fuer "passt nicht".

    Ein Stummel ("iPh…") ist keine Beschriftung. Wer weniger als sechs
    Zeichen unterbringt, bringt nichts unter.
    """
    text = text or ""
    grenze = int(breite_px / ZEICHENBREITE)
    if grenze < 6:
        return ""
    return text if len(text) <= grenze else text[:grenze - 1].rstrip() + "…"


def textbreite(text: str) -> float:
    return len(text or "") * ZEICHENBREITE


def _speicher_kurz(gb) -> str:
    if not gb:
        return ""
    return f"{gb // 1024} TB" if gb >= 1024 and gb % 1024 == 0 else f"{gb}"


def _euro(wert: float) -> str:
    return f"{wert:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")


def aggregiere(punkte: list, preisart: str = "ohne_vertrag") -> list:
    """Aus Listungen werden Preispunkte: (Modell, Speicher, Laden).

    Der niedrigste Preis gewinnt - er ist der, zu dem das Geraet dort wirklich
    zu haben ist. Die Farben verschwinden nicht, sie wandern in `farben_liste`
    und damit in den Tooltip; einzeln stehen sie weiterhin in der SKU-Matrix.

    Geschluesselt wird ueber `shop` und nicht ueber `anbieter`: "freenet" und
    "mobilcom-debitel" sind derselbe Laden, und als zwei Schluessel erzeugten
    sie zwei deckungsgleiche Punkte - dieselbe Krankheit, die die Farben
    verursacht haben, nur an einer anderen Stelle.

    Die Sortierung ist fest. Eine wechselnde Reihenfolge ergaebe bei jedem
    Lauf ein anderes SVG und damit einen Diff, der nichts bedeutet.
    """
    gruppen: dict[tuple, list] = {}
    for p in punkte:
        if p.get("preis") is None:
            continue
        # Dieselbe Regel wie in der Vergleichstabelle (W1.1, 29.08.2026): die
        # Karte zeigt NUR Neugeraete. Sie ordnet Punkte nach Preis auf einer
        # Achse, und die Y-Achse traegt keine Zustandsangabe - ein
        # Gebrauchtpreis liest sich dort wie ein guenstiger Neupreis. Der
        # Zustand bleibt trotzdem im Schluessel unten: er ist die zweite
        # Sicherung, falls diese Zeile jemand lockert.
        if (p.get("zustand") or "neu") not in VERGLEICHBARE_ZUSTAENDE:
            continue
        laden = p.get("shop") or p.get("anbieter") or ""
        # `zustand` MUSS in den Schluessel. Ohne ihn faellt "iPhone 15 256 GB
        # neu, 749 EUR" mit "dasselbe refurbished, 429 EUR" zu einem Punkt
        # zusammen, und weil der niedrigste Preis gewinnt, verschwindet der
        # Neupreis aus der Karte - bei einem Anbieter, der beides fuehrt, die
        # teuerste Sorte falscher Zahl. ALDI TALK listet genau so ein
        # refurbished iPhone.
        gruppen.setdefault(
            (p.get("device_id"), p.get("speicher"), laden,
             p.get("zustand") or "neu"), []).append(p)

    raus = []
    for schluessel, gruppe in gruppen.items():
        gruppe.sort(key=lambda q: (q["preis"], q.get("sku_id") or ""))
        fuehrend = gruppe[0]
        farben = sorted({q.get("farbe") for q in gruppe if q.get("farbe")})
        speicher = fuehrend.get("speicher")
        anzeige = (fuehrend.get("anbieter_anzeige")
                   or fuehrend.get("anbieter") or "")
        raus.append({
            **fuehrend,
            "schluessel": "|".join(str(t) for t in schluessel) + f"|{preisart}",
            "zustand": schluessel[3],
            "shop": schluessel[2],
            "anbieter_anzeige": anzeige,
            "preisart": preisart,
            "farben": len(farben),
            "farben_liste": farben,
            "varianten": len(gruppe),
            "speicher_kurz": _speicher_kurz(speicher),
            "titel": (f"{fuehrend.get('label', '')}"
                      + (f" · {len(farben)} Farben" if len(farben) > 1 else "")
                      + f" · ab {_euro(fuehrend['preis'])} € bei {anzeige}"
                      + (f" (abgerufen {fuehrend.get('abgerufen_am')})"
                         if fuehrend.get("abgerufen_am") else "")),
        })
    raus.sort(key=lambda p: (p.get("hersteller") or "", p.get("modell") or "",
                             p.get("speicher") or 0, p.get("shop") or ""))
    return raus


# --------------------------------------------------------------------------
# Achse, Spalten, Hoehe
# --------------------------------------------------------------------------

def _y_max(punkte: list, preisart: str) -> int:
    regel = ACHSE.get(preisart, ACHSE["ohne_vertrag"])
    hoechster = max(p["preis"] for p in punkte)
    schritt = regel["schritt"]
    return max(regel["mindest"], int((hoechster // schritt + 1) * schritt))


def _kapazitaet(breite_spalte: float, chipbreite: float) -> int:
    """Wie viele Chips nebeneinander in eine Spalte passen."""
    nutzbar = breite_spalte - 2 * CHIP_RAND + CHIP_LUFT_X
    return max(1, int(nutzbar // (chipbreite + CHIP_LUFT_X)))


def _noetige_hoehe(preise: list, kapazitaet: int, y_max: float,
                   fenster: float) -> float:
    """Wie hoch die Zeichenflaeche sein muss, damit nichts uebereinanderliegt.

    In einem Fenster von `fenster` Pixeln duerfen hoechstens `kapazitaet`
    Eintraege liegen. Fuer absteigend sortierte Preise heisst das: der Abstand
    zwischen p_i und p_{i+kapazitaet} muss mindestens `fenster` ergeben.
    """
    preise = sorted(preise, reverse=True)
    noetig = 0.0
    for i in range(len(preise) - kapazitaet):
        luecke = preise[i] - preise[i + kapazitaet]
        if luecke > 0:
            noetig = max(noetig, fenster * y_max / luecke)
    return noetig


# --------------------------------------------------------------------------
# Variante B - Chips
# --------------------------------------------------------------------------

def _chipbreite(text: str) -> float:
    return CHIP_TEXT_DX + textbreite(text) + CHIP_POLSTER_R


# Mindestabstand zweier nackter Marker. Ein Marker DARF einen anderen
# ueberlappen - zwei Punkte auf fast demselben Preis sehen nun einmal so aus.
# Was er nicht darf, ist deckungsgleich auf ihm liegen: genau daraus bestand
# der Befund "60 der 85 Kreise sind derselbe Punkt".
MARKER_ABSTAND = 3.0


def _freier_platz(gesetzt: list, cy: float, halb_y: float, breite: float,
                  luft: float, x_von: float, x_bis: float):
    """Der erste freie Platz LINKS - oder None.

    Gesperrt sind die x-Bereiche aller bereits gesetzten Kaesten, deren
    y-Bereich den eigenen schneidet. Kandidaten fuer die linke Kante sind der
    Spaltenanfang und die rechte Kante jedes gesperrten Bereichs.

    Ausgewichen wird ausschliesslich nach rechts. Es gibt in diesem Modul
    keinen Weg, nach unten auszuweichen - das ist der ganze Unterschied zur
    alten Fassung.
    """
    oben, unten = cy - halb_y, cy + halb_y
    sperren = [g for g in gesetzt
               if not (g["unten"] <= oben or g["oben"] >= unten)]
    for x in [x_von] + sorted(g["x2"] + luft for g in sperren):
        if x + breite > x_bis:
            return None
        if all(x + breite <= g["x1"] or x >= g["x2"] + luft for g in sperren):
            return x
    return None


def _form_chip(punkte: list, spalten: list, py, spaltenfeld: str) -> tuple:
    gezeichnet, verborgen = [], 0
    for spalte in spalten:
        in_spalte = sorted([p for p in punkte if p[spaltenfeld] == spalte["name"]],
                           key=lambda p: (-p["preis"], p.get("modell") or ""))
        x_von = spalte["x0"] + CHIP_RAND
        x_bis = spalte["x0"] + spalte["breite"] - CHIP_RAND

        # EIN Durchgang fuer Chips und Marker, mit EINER Belegungsliste.
        # Zwei Durchgaenge waren der erste Anlauf und ein Rueckfall in genau
        # den Fehler, den dieses Modul behebt: die Marker kannten die
        # gesetzten Chips nicht, fielen bei voller Spalte alle auf dieselbe
        # Startkante zurueck und lagen wieder deckungsgleich aufeinander
        # (gemessen: 400 Punkte, 268 verschiedene Koordinaten).
        gesetzt: list[dict] = []
        for p in in_spalte:
            cy = py(p["preis"])
            # Modell plus Kurzspeicher ist die kompakteste Fassung und passt
            # damit oefter in eine Bahn. `label` ist der Rueckfall fuer
            # Punkte, die nicht durch `aggregiere()` gelaufen sind - ohne ihn
            # bekaemen sie stillschweigend GAR KEIN Etikett, und ein Test,
            # der `karte()` direkt aufruft, waere gruen, ohne etwas zu messen.
            text = f"{p.get('modell') or ''} {p.get('speicher_kurz') or ''}".strip()
            if not text:
                text = p.get("label") or ""
            platz = None
            if text:
                platz = _freier_platz(gesetzt, cy, (CHIP_HOEHE + CHIP_LUFT_Y) / 2,
                                      _chipbreite(text), CHIP_LUFT_X,
                                      x_von, x_bis)
            if platz is not None:
                breite = _chipbreite(text)
                gesetzt.append({"x1": platz, "x2": platz + breite,
                                "oben": cy - (CHIP_HOEHE + CHIP_LUFT_Y) / 2,
                                "unten": cy + (CHIP_HOEHE + CHIP_LUFT_Y) / 2})
                gezeichnet.append(_punkt(
                    p, platz, cy, beschriftet=True, spalte=spalte["name"],
                    label=text, label_x=platz + CHIP_TEXT_DX,
                    chip={"x": round(platz, 1),
                          "y": round(cy - CHIP_HOEHE / 2, 1),
                          "w": round(breite, 1), "h": CHIP_HOEHE}))
                continue

            # Kein Platz fuer den Chip: nackter Marker, in DERSELBEN
            # Belegungsliste. Er braucht nur `MARKER_ABSTAND`, nicht seine
            # volle Breite - zwei Punkte duerfen einander ueberlappen, sie
            # duerfen nur nicht derselbe Punkt sein.
            if text:
                verborgen += 1
            mplatz = _freier_platz(gesetzt, cy, RADIUS_EIGEN + 1,
                                   MARKER_ABSTAND, 0.0, x_von, x_bis)
            if mplatz is None:
                # Selbst dafuer ist kein Platz. Der Punkt wird NICHT
                # gezeichnet und gezaehlt - ihn auf die Startkante zu legen
                # hiesse, ihn deckungsgleich auf einen anderen zu setzen, und
                # das ist die Falschaussage, die diese Karte nicht macht.
                continue
            gesetzt.append({"x1": mplatz, "x2": mplatz + MARKER_ABSTAND,
                            "oben": cy - RADIUS_EIGEN - 1,
                            "unten": cy + RADIUS_EIGEN + 1})
            gezeichnet.append(_punkt(p, mplatz, cy, beschriftet=False,
                                     spalte=spalte["name"]))
    return gezeichnet, [], verborgen


def _punkt(p: dict, cx: float, cy: float, beschriftet: bool, spalte: str,
           label: str = "", label_x: float | None = None,
           chip: dict | None = None) -> dict:
    """Ein Punkt, in BEIDEN Formen mit demselben Schluesselsatz.

    `label_y` wird hier und nur hier gesetzt, und zwar ausschliesslich aus
    `cy`. Damit ist die Kernregel bauartbedingt eingehalten, statt an jeder
    Aufrufstelle wiederholt zu werden.
    """
    return {
        **p,
        "cx": round(cx, 1), "cy": round(cy, 1),
        "r": RADIUS_EIGEN if p.get("eigen") else RADIUS,
        "beschriftet": beschriftet,
        "label_kurz": label if beschriftet else "",
        "label_x": round(label_x, 1) if (beschriftet and label_x is not None) else None,
        "label_y": round(cy + BASISLINIE, 1) if beschriftet else None,
        "label_anker": "start",
        "chip": chip,
        "spalte": spalte,
    }


# --------------------------------------------------------------------------
# Variante A - Preisbaender
# --------------------------------------------------------------------------

def _form_band(punkte: list, spalten: list, py, spaltenfeld: str,
               achse_y: float) -> tuple:
    gezeichnet, baender, verborgen = [], [], 0
    for spalte in spalten:
        in_spalte = [p for p in punkte if p[spaltenfeld] == spalte["name"]]
        modelle = sorted({(p.get("modell") or "", p.get("device_id") or "",
                           p.get("shop") or "") for p in in_spalte})
        schlitz = spalte["breite"] / max(1, len(modelle))
        # Welche Modellnamen kommen in dieser Spalte bei mehr als einem Laden
        # vor? Nur die brauchen den Ladennamen dazu.
        haeufig: dict[str, set] = {}
        for name, _gid, laden in modelle:
            haeufig.setdefault(name, set()).add(laden)
        mehrfach = {n for n, laeden in haeufig.items() if len(laeden) > 1}

        for i, (modell, device_id, shop) in enumerate(modelle):
            gruppe = sorted([p for p in in_spalte
                             if (p.get("device_id") or "") == device_id
                             and (p.get("shop") or "") == shop],
                            key=lambda p: -p["preis"])
            cx = spalte["x0"] + (i + 0.5) * schlitz
            oben, unten = py(gruppe[0]["preis"]), py(gruppe[-1]["preis"])

            # JEDE Stufe ist ein eigener Punkt. Der erste Anlauf verschmolz
            # Stufen, die weniger als sechs Pixel auseinanderlagen - damit
            # verschwanden aus der 120-Punkte-Fixture 90 Punkte aus dem Bild,
            # waehrend die Ueberschrift weiter 120 nannte. Zwei Querstriche
            # drei Pixel uebereinander sind lesbar; eine Zahl, die nicht zu
            # dem passt, was man sieht, ist es nicht.
            #
            # Beschriftet werden Hoechst- und Tiefstpreis des Bandes, und
            # zwar AM PUNKT: als eigene Textknoten neben dem Band waeren sie
            # weder vom Filter noch von Kriterium 11 erfasst - dort stuende
            # dann eine Preiszahl zu einer ausgeblendeten Variante.
            platz = schlitz / 2 - BAND_KAPPE_DX
            beschriften = {id(gruppe[0])}
            if abs(unten - oben) >= CHIP_HOEHE:
                beschriften.add(id(gruppe[-1]))

            for p in gruppe:
                cy = py(p["preis"])
                zahl = f"{p['preis']:,.0f}".replace(",", ".")
                will = id(p) in beschriften
                passt = will and textbreite(zahl) <= platz
                if will and not passt:
                    verborgen += 1
                gezeichnet.append({
                    **_punkt(p, cx, cy, beschriftet=passt,
                             spalte=spalte["name"],
                             label=zahl if passt else "",
                             label_x=cx + BAND_KAPPE_DX if passt else None),
                    "strich_x1": round(cx - BAND_KAPPE_HALB, 1),
                    "strich_x2": round(cx + BAND_KAPPE_HALB, 1),
                    "band": f"{device_id}|{shop}",
                })

            baender.append({
                "schluessel": f"{device_id}|{shop}",
                "modell": modell, "device_id": device_id,
                "spalte": spalte["name"],
                "eigen": bool(gruppe[0].get("eigen")),
                "x": round(cx, 1), "halb": BAND_KAPPE_HALB,
                "breite": BAND_STRICH,
                "y_oben": round(oben, 1), "y_unten": round(unten, 1),
                "hoehe": round(max(0.0, unten - oben), 1),
                "entartet": len(gruppe) < 2,
                "stufen": len(gruppe),
                "preis_min": gruppe[-1]["preis"], "preis_max": gruppe[0]["preis"],
                # Der Modellname steht UNTER der Achse und traegt deshalb
                # keine Preisaussage. Gedreht, weil ein Schlitz von 80 px
                # keinen waagerechten Modellnamen fasst - und eine gedrehte
                # Beschriftung ist lesbar, eine ueberlappende nicht.
                "name_x": round(cx, 1),
                "name_y": round(achse_y + BAND_NAME_DY, 1),
                # In der Herstelleransicht kann dasselbe Modell bei zwei
                # Laeden stehen. Ohne den Ladennamen stuenden dort zwei
                # gleich beschriftete Baender nebeneinander - und genau
                # diese Ansicht wird Standard, sobald mehr als ein Laden
                # liefert.
                "name_kurz": kuerze(modell if modell not in mehrfach
                                    else f"{modell} · {shop}",
                                    RAND_U_BAND - BAND_NAME_DY - 10) or modell,
            })
    return gezeichnet, baender, verborgen


# --------------------------------------------------------------------------
# Einstieg
# --------------------------------------------------------------------------

def _leer(ansicht: str, achsname: str, form: str, preisart: str) -> dict:
    return {"hat_daten": False, "form": form, "ansicht": ansicht,
            "preisart": preisart,
            "id": f"{ansicht}-{form}-{preisart}".replace("_", "-"),
            "punkte": [], "baender": [], "spalten": [], "y_ticks": [],
            "breite": BREITE, "hoehe": HOEHE_MIN, "rand_l": RAND_L,
            "rand_r": RAND_R, "rand_o": RAND_O,
            "rand_u": RAND_U_BAND if form == FORM_BAND else RAND_U_CHIP,
            "achse_y": 0.0, "plot_h": 0.0, "achsname": achsname,
            "achszusatz": "", "anzahl": 0, "spaltenzahl": 0,
            "aggregiert_aus": 0, "etiketten_verborgen": 0, "y_max": 0,
            "schrift": SCHRIFT}


def karte(punkte: list, spaltenfeld: str, achsname: str,
          form: str = FORM_CHIP, preisart: str = "ohne_vertrag",
          anzeige: dict | None = None, hoehe_mindestens: int = 0,
          achszusatz: str = "") -> dict:
    """Eine Zeichenflaeche der Positionskarte.

    `punkte` sind bereits AGGREGIERTE Preispunkte (siehe `aggregiere`).
    `anzeige` bildet einen Spaltennamen auf seine Beschriftung ab - so heisst
    der Laden, der als "mobilcom-debitel" in der Datenbank steht, auf der
    Grafik "freenet (mobilcom-debitel)", ohne dass die Vorlage einen
    Sonderfall kennen muss.

    `hoehe_mindestens` haelt beide Ansichten auf derselben Hoehe: sonst
    springt die Seite beim Umschalten.
    """
    ansicht = "hersteller" if spaltenfeld == "hersteller" else "anbieter"
    brauchbar = [p for p in punkte if p.get("preis") is not None]
    if not brauchbar:
        return _leer(ansicht, achsname, form, preisart)
    anzeige = anzeige or {}

    y_max = _y_max(brauchbar, preisart)
    schritt = ACHSE.get(preisart, ACHSE["ohne_vertrag"])["schritt"]
    rand_u = RAND_U_BAND if form == FORM_BAND else RAND_U_CHIP
    spaltennamen = sorted({p[spaltenfeld] for p in brauchbar})
    innen = BREITE - RAND_L - RAND_R

    # Die Spaltenregel ist formabhaengig, und das ist gerechnet: bei Chips
    # zaehlt die Dichte (gleich breit ist besser), bei Baendern die Zahl der
    # Schlitze (proportional ist besser).
    if form == FORM_BAND:
        gewicht = [max(1, len({(p.get("device_id"), p.get("shop"))
                               for p in brauchbar if p[spaltenfeld] == n}))
                   for n in spaltennamen]
        summe = sum(gewicht) or 1
        breiten = [innen * g / summe for g in gewicht]
    else:
        breiten = [innen / len(spaltennamen)] * len(spaltennamen)

    # Die noetige Zeichenhoehe aus der dichtesten STELLE - und die ist
    # formabhaengig. Bei Chips ist es die dichteste Spalte: dort teilen sich
    # alle Punkte einen Raum. Bei Baendern ist es das dichteste BAND: zwei
    # Modelle stehen in verschiedenen Schlitzen und koennen sich gar nicht in
    # die Quere kommen, egal wie nah ihre Preise beieinanderliegen. Ueber die
    # ganze Spalte gerechnet verlangte die Anbieteransicht 900 px, wo 540
    # reichen - eine Grafik, die ohne Not einen Bildschirm hoch ist.
    noetig = 0.0
    for name, breite_spalte in zip(spaltennamen, breiten):
        in_spalte = [p for p in brauchbar if p[spaltenfeld] == name]
        if form == FORM_BAND:
            gruppen: dict[tuple, list] = {}
            for p in in_spalte:
                gruppen.setdefault((p.get("device_id"), p.get("shop")),
                                   []).append(p["preis"])
            for preise in gruppen.values():
                noetig = max(noetig, _noetige_hoehe(preise, 1, y_max,
                                                    BAND_STUFE_MIN))
        else:
            kap = _kapazitaet(breite_spalte, _chipbreite("x" * 16))
            noetig = max(noetig, _noetige_hoehe([p["preis"] for p in in_spalte],
                                                kap, y_max,
                                                CHIP_HOEHE + CHIP_LUFT_Y))
    zeichenhoehe = min(max(HOEHE_MIN - RAND_O - rand_u, noetig),
                       HOEHE_MAX - RAND_O - rand_u)
    hoehe = max(round(zeichenhoehe + RAND_O + rand_u), hoehe_mindestens)
    plot_h = hoehe - RAND_O - rand_u
    achse_y = float(hoehe - rand_u)

    def py(preis: float) -> float:
        return achse_y - (preis / y_max) * plot_h

    spalten = []
    links = RAND_L
    for name, breite_spalte in zip(spaltennamen, breiten):
        beschriftung = anzeige.get(name, name)
        spalten.append({
            "name": name, "label": kuerze(beschriftung, breite_spalte - 6) or beschriftung,
            "x": round(links + breite_spalte / 2, 1),
            "x0": round(links, 1), "x1": round(links + breite_spalte, 1),
            "breite": round(breite_spalte, 1),
        })
        links += breite_spalte

    if form == FORM_BAND:
        gezeichnet, baender, verborgen = _form_band(
            brauchbar, spalten, py, spaltenfeld, achse_y)
    else:
        gezeichnet, baender, verborgen = _form_chip(
            brauchbar, spalten, py, spaltenfeld)

    return {
        "hat_daten": True,
        "id": f"{ansicht}-{form}-{preisart}".replace("_", "-"),
        "ansicht": ansicht, "form": form, "preisart": preisart,
        "punkte": gezeichnet, "baender": baender, "spalten": spalten,
        "y_max": y_max, "y_schritt": schritt,
        "y_ticks": [{"wert": w, "y": round(py(w), 1)}
                    for w in range(0, y_max + 1, schritt)],
        "breite": BREITE, "hoehe": hoehe,
        "rand_l": RAND_L, "rand_r": RAND_R, "rand_o": RAND_O, "rand_u": rand_u,
        "achse_y": achse_y, "plot_h": plot_h,
        "achsname": achsname, "achszusatz": achszusatz,
        "anzahl": len(gezeichnet), "spaltenzahl": len(spalten),
        "aggregiert_aus": sum(p.get("varianten", 1) for p in brauchbar),
        "etiketten_verborgen": verborgen,
        "schrift": SCHRIFT,
    }


def preis_aus_hoehe(label_y: float, y_max: float, achse_y: float,
                    plot_h: float) -> float:
    """Die Umkehrung der Projektion - der Kern des Abnahmetests.

        cy = achse_y - preis / y_max * plot_h
        label_y = cy + BASISLINIE

    Sie steht hier und nicht im Test, damit Grafik und Pruefung dieselbe
    Rechnung benutzen. Zwei Fassungen waeren zwei Meinungen darueber, wo die
    Nulllinie liegt - und beide fuer sich gruen.
    """
    if plot_h <= 0 or not y_max:
        return 0.0
    return (achse_y - (label_y - BASISLINIE)) * y_max / plot_h


def toleranz(preis: float, y_max: float, plot_h: float) -> float:
    """Wie weit die Rueckrechnung danebenliegen darf.

    Drei Prozent - plus einen Rundungsboden von zwei Pixeln. Ohne den fiele
    die Vertragsansicht durch: drei Prozent einer Zuzahlung von 1 EUR sind
    drei Cent, und `cy` wird auf ein Zehntelpixel gerundet.
    """
    pixel = (y_max / plot_h) if plot_h else 0.0
    return max(0.03 * abs(preis), 2 * pixel)
