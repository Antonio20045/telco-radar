"""Datenmodell des Geraete- und Preisradars: Geraet, SKU, Listung.

Drei Ebenen, sauber getrennt:

    Geraet   herstellerseitig, haendlerunabhaengig (iPhone 17 Pro Max)
    Sku      die Variante        (... 256 GB, Titan Natur)
    Listung  was EIN Anbieter zu einem Zeitpunkt dafuer verlangt

DIE ID-REGEL, und sie ist nicht verhandelbar
--------------------------------------------
`device_id`, `sku_id` und `listung_id` entstehen aus NORMALISIERTEN FELDERN,
niemals aus dem Produkttitel. Ein Titel-Hash ist der eine Fehler, der dieses
Feature killt: Haendler benennen denselben Artikel staendig um -

    "APPLE iPhone 17 Pro Max 5G 256 GB Titannatur"
    "Apple iPhone 17 Pro Max (256 GB) - Titan Natur"
    "Apple iPhone 17 Pro Max 256GB Natural Titanium"

- und aus einem Titel-Hash wuerden daraus drei angeblich brandneue Geraete,
Woche fuer Woche. Die Listungsdauer waere dann immer eine Woche, der
Preisverfall immer null und die Nachfolger-Analyse waere Muell. Genau diese
Falle steht in `analyze/promo_store.entry_id()` bereits im Repo; dort faengt
eine Fuzzy-Suche ueber die Ueberschriften sie nachtraeglich ab. Hier wird sie
gar nicht erst gebaut: der Titel dient ausschliesslich dazu, den
KATALOGEINTRAG zu finden, und die ID kommt aus dem Katalog.

Die IDs sind Klartext-Slugs, keine Hashes ("apple-iphone-17-pro-max-256gb-
titan-natur"). Dieselbe Begruendung wie bei `data/state/ct_seen.jsonl`: es
sind Hunderte Zeilen, nicht Millionen, und der Klartext ist die halbe
Diagnose - wer in die JSONL sieht, erkennt einen Zuordnungsfehler sofort.

WAS DIESES MODUL BEWUSST NICHT TUT
----------------------------------
Es raet nicht. Ein Geraet, das nicht im Katalog steht, wird nicht erfunden
(`erkenne_geraet` gibt None). Eine Farbe, die die Tabelle nicht kennt, wird
behalten und als `farbe_normalisiert=None` markiert - nicht auf die
naechstaehnliche gebogen. Ein Titel, der ZWEI Speichergroessen nennt, ergibt
keinen Wert statt des groesseren.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

# Verfuegbarkeitsstufen einer Listung.
#
# "ausgelistet" steht bewusst NICHT darunter, obwohl der Auftragstext es in
# derselben Aufzaehlung nennt: Auslistung ist kein Zustand, den eine
# Produktseite meldet, sondern eine Schlussfolgerung aus MEHREREN Laeufen
# (analyze/geraete_store.py, Zwei-Stufen-Logik). Waeren beide dasselbe Feld,
# machte ein "Voruebergehend nicht lieferbar" das Geraet zum Portfolio-Ende -
# und genau davor warnt Teil F des Auftrags.
VERFUEGBARKEITEN = (
    "lieferbar",
    "vorbestellbar",
    "ausverkauft",        # dauerhaft weg beim Haendler, Seite lebt noch
    "nicht_lieferbar",    # voruebergehend, Nachschub angekuendigt
    "unbekannt",
)

ANBIETER_TYPEN = ("handel", "netzbetreiber", "discount")

# Belegstufen, gleiche Skala wie collect/lieferzeit.py:
#   hoch    strukturierte Daten (ld+json, API)
#   mittel  gezielter Selektor / JSON-Endpunkt der Seite
#   niedrig aus dem Fliesstext geklaubt
CONFIDENCE = ("hoch", "mittel", "niedrig")

# Speicherstufen, die es bei Smartphones wirklich gibt. Der Filter ist die
# billigste und zuverlaessigste Abgrenzung gegen den Arbeitsspeicher: "12 GB
# RAM / 512 GB" nennt zwei Zahlen mit derselben Einheit, aber nur eine davon
# ist eine Speicherstufe.
_SPEICHER_STUFEN = (32, 64, 128, 256, 512, 1024, 2048)

_UMLAUTE = str.maketrans({
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "ae", "Ö": "oe", "Ü": "ue",
    "é": "e", "è": "e", "ê": "e", "á": "a", "à": "a", "í": "i", "ó": "o",
    "ú": "u", "ñ": "n", "ç": "c",
})

# Woerter, die einen Titel zu Zubehoer machen. Eine Kategorieseite eines
# Elektronikhaendlers mischt Huellen, Schutzglas und Ladekabel unter die
# Geraete; ohne diesen Filter stuende eine 9,99-Euro-Huelle als Preispunkt
# des iPhone 17 Pro Max in der Positionskarte. Geprueft wird WORTWEISE - ein
# Teilkettenfilter haette "Showcase" zu "Case" gemacht (dieselbe Lehre wie
# beim CT-Rauschfilter, CLAUDE.md §6).
#
# ZWEI LISTEN, und die Trennung ist teuer erkauft. Eine einzige, breite Liste
# hat im Review echte Geraete verworfen:
#     "Apple iPhone 16 Pro Max 256GB Titanschwarz, ohne Netzteil"
#     "Motorola moto g85 5G 256 GB, 5000 mAh Akku"
#     "Xiaomi 15 Ultra 512GB, 6,73 Zoll AMOLED Display"
# "ohne Netzteil" ist im deutschen Handel eine Pflichtangabe, "Akku" und
# "Display" stehen regelmaessig in Mittelklassetiteln. Deshalb:
#
#   _ZUBEHOER_IMMER  Woerter, die in keinem Geraetetitel vorkommen. Sie
#                    verwerfen den Titel, wo immer sie stehen.
#   _ZUBEHOER_DAVOR  Woerter, die ein Geraet BEGLEITEN koennen. Sie verwerfen
#                    nur, wenn sie VOR dem Modellnamen stehen - so heisst
#                    naemlich ein Zubehoertitel ("Ladekabel USB-C fuer
#                    iPhone 17"), waehrend die Beigabe hinten steht
#                    ("iPhone 16 128 GB inkl. Ladekabel").
_ZUBEHOER_IMMER = frozenset("""
huelle huellen huellenset case cases cover schutzhuelle schutzglas panzerglas
displayschutz displayschutzfolie schutzfolie bumper reparaturset zubehoer
""".split())

_ZUBEHOER_DAVOR = frozenset("""
ladekabel ladegeraet netzteil adapter kabel powerbank halterung halter tasche
kopfhoerer headset ohrhoerer armband ladeschale ladestation dockingstation
ersatzakku ersatzdisplay folie aufkleber skin simkarte
""".split())

# Woerter, die aus einem Modellnamen ein ANDERES Modell machen. Steht so ein
# Wort direkt hinter einem Katalogtreffer, ohne selbst dazuzugehoeren, ist die
# Zuordnung nicht belegbar - dann wird nichts zugeordnet.
#
# Der Fall, der das erzwungen hat: "Google Pixel 10 Pro Fold 256 GB" traf den
# Katalogeintrag "Pixel 10 Pro". Beide Geraete beim selben Haendler ergaben
# dieselbe listung_id, und weil sie rund 800 Euro auseinanderliegen, schrieb
# die Preishistorie bei JEDEM Lauf zwei Aenderungspunkte hin und zurueck - eine
# dauerhafte Saegezahnkurve, die wie ein wilder Preiskampf aussieht.
_MODELLZUSATZ = frozenset("""
pro max plus ultra mini air fold flip lite neo note fe edge se xl active
""".split())


# --------------------------------------------------------------------------
# Normalisierung
# --------------------------------------------------------------------------

def normalisiere(text: str) -> str:
    """Vergleichs- und ID-Form: klein, Umlaute gefaltet, alles ausser
    Buchstaben und Ziffern zu einem Bindestrich."""
    t = (text or "").strip().lower().translate(_UMLAUTE)
    t = re.sub(r"[^a-z0-9]+", "-", t)
    return t.strip("-")


def wortmarken(text: str) -> list[str]:
    """Der Titel als Folge von Wortmarken - die Grundlage der Erkennung.

    Zwei Regeln, beide teuer erkauft:

    1. Nach BUCHSTABEN folgende Ziffern werden abgetrennt: "Fold7" -> "fold",
       "7"; "S25" -> "s", "25". Sonst faende der Katalogeintrag
       "Galaxy Z Fold 7" die Haendlerschreibweise "Fold7" nie. Weil beide
       Seiten - Katalog wie Titel - durch dieselbe Funktion laufen, ist die
       Trennung folgenlos, solange sie konsistent ist.

    2. Nach ZIFFERN folgende Buchstaben bleiben kleben: "3a" bleibt "3a",
       "5G" bleibt "5g". Genau daran haengt, dass der Katalogeintrag
       "Nothing Phone 3" nicht auf das "Nothing Phone (3a)" faellt - und
       dass "5G" im Titel nicht als Speichergroesse oder Generationsziffer
       gelesen wird.
    """
    vorbereitet = _binnenmajuskel((text or "").replace("+", " plus "))
    roh = re.sub(r"[^a-z0-9]+", " ", vorbereitet.lower().translate(_UMLAUTE))
    marken: list[str] = []
    for wort in roh.split():
        # Buchstaben->Ziffer trennen, Ziffer->Buchstabe nicht.
        for teil in re.findall(r"[a-z]+|[0-9]+[a-z]*", wort):
            marken.append(teil)
    return marken


# Binnenmajuskel: "ProMax" -> "Pro Max". Der Vorname bleibt ab zwei Zeichen -
# "iPhone" darf NICHT zu "i Phone" zerfallen, sonst faende der Katalog seine
# eigenen Modellnamen nicht mehr. Gilt fuer Katalog und Titel gleichermassen,
# ist also folgenlos, solange sie konsistent ist.
_BINNENMAJUSKEL = re.compile(r"(?<=[a-z]{2})(?=[A-Z][a-z])")


def _binnenmajuskel(text: str) -> str:
    return _BINNENMAJUSKEL.sub(" ", text or "")


# --------------------------------------------------------------------------
# Die IDs
# --------------------------------------------------------------------------

def device_id(hersteller: str, modell: str) -> str:
    """Hersteller + Modell als Slug.

    Traegt der Modellname den Hersteller bereits ("OnePlus 13", "Xiaomi 15"),
    wird er nicht doppelt gesetzt - "oneplus-oneplus-13" waere eine ID, die
    beim Lesen der JSONL nach einem Fehler aussieht.
    """
    h, m = normalisiere(hersteller), normalisiere(modell)
    if h and (m == h or m.startswith(h + "-")):
        return m
    return f"{h}-{m}".strip("-")


def sku_id(geraet_id: str, speicher_gb: Optional[int], farbe: Optional[str],
           zustand: str = "neu") -> str:
    """SKU-ID aus Geraet + Speicher + Farbe (+ Zustand, wenn nicht neu).

    Fehlt ein Teil, sagt die ID das offen ("ohne-speicher", "ohne-farbe")
    statt ihn wegzulassen: sonst waere die SKU eines Angebots ohne
    Farbangabe identisch mit der eines schwarzen Geraets. Was ein Ausfall
    dieser Felder fuer die IDENTITAET bedeutet, faengt der Store ab
    (`GeraeteDB._finde_verwandten`) - hier wird nichts vertuscht.
    """
    sp = f"{int(speicher_gb)}gb" if speicher_gb else "ohne-speicher"
    fb = normalisiere(farbe) if farbe else "ohne-farbe"
    grund = f"{geraet_id}-{sp}-{fb}"
    return grund if zustand in ("", "neu") else f"{grund}-{normalisiere(zustand)}"


def listung_id(sku: str, anbieter: str) -> str:
    """Doppelter Bindestrich als Trenner - er kommt in keinem Slug vor, die
    ID bleibt also eindeutig zerlegbar."""
    return f"{normalisiere(anbieter)}--{sku}"


# --------------------------------------------------------------------------
# Speicher und Farbe aus einem Titel
# --------------------------------------------------------------------------

_SPEICHER_RE = re.compile(r"(\d{1,4})\s*(gb|tb)\b", re.IGNORECASE)
_RAM_WORT = re.compile(r"\b(ram|arbeitsspeicher)\b", re.IGNORECASE)
_ARBEITSSPEICHER_WORT = re.compile(r"\barbeitsspeicher\b", re.IGNORECASE)
# Trennzeichen zwischen zwei Angaben desselben Titels. Nur bis dahin wird
# rueckwaerts nach "Arbeitsspeicher" gesucht - sonst faellt in
# "12 GB RAM / 512 GB" auch die zweite Zahl, weil das RAM davor steht.
_TRENNER = re.compile(r"[/,|·+():\[\]]")


def _ist_arbeitsspeicher(text: str, treffer, ab: int = 0) -> bool:
    """Gehoert diese GB-Angabe zum Arbeitsspeicher?

    Die zwei Richtungen sind NICHT symmetrisch, und das ist der ganze Trick:

      * NACH der Zahl steht "RAM" ("12 GB RAM") - beide Woerter zaehlen.
      * VOR der Zahl steht nur "Arbeitsspeicher" ("Arbeitsspeicher: 12 GB").

    Rueckwaerts nach "RAM" zu suchen war der Fehler: in "12 GB RAM 512 GB"
    steht das RAM der ERSTEN Angabe zwischen beiden Zahlen, und die zweite -
    der echte Speicher - fiel damit durch. Titel schreiben die beiden Werte
    oft ohne Trennzeichen hintereinander, ein Schraegstrich rettet einen also
    nicht.
    """
    nach = text[treffer.end():treffer.end() + 16]
    if _RAM_WORT.match(nach.lstrip(" -:")):
        return True
    vor = text[:treffer.start()]
    letzter = ab
    for t in _TRENNER.finditer(vor):
        if t.end() > letzter:
            letzter = t.end()
    return bool(_ARBEITSSPEICHER_WORT.search(vor[letzter:]))


def speicher_aus_titel(titel: str, erlaubt: Optional[Iterable[int]] = None) -> Optional[int]:
    """Speichergroesse in GB, oder None.

    `erlaubt` (die Speicherstufen des Katalogeintrags) ist eine VORLIEBE, kein
    Filter. Eine im Katalog vergessene Stufe darf den Wert nicht verschlucken:
    "iPhone 17 1 TB" wuerde sonst als `ohne-speicher` gefuehrt und faende sich
    in einem Topf mit jeder anderen Variante, deren Groesse nicht gelesen
    werden konnte.

    Nennt der Titel ZWEI verschiedene gueltige Groessen ("256 GB / 512 GB"),
    ist das eine Sammelseite und kein Artikel - dann wird nichts geraten.
    """
    stufen = set(_SPEICHER_STUFEN)
    bevorzugt = set(int(x) for x in erlaubt) if erlaubt else set()
    gefunden: set[int] = set()
    text = titel or ""
    vorheriges_ende = 0
    for m in _SPEICHER_RE.finditer(text):
        # Die Grenze der Rueckwaertssuche wandert mit JEDER Groessenangabe
        # weiter, auch mit einer verworfenen: "12 GB RAM 512 GB" nennt die
        # zwei Angaben ohne Trennzeichen hintereinander, und ohne diese
        # Grenze faende die zweite das "RAM" der ersten.
        ab, vorheriges_ende = vorheriges_ende, m.end()
        wert = int(m.group(1))
        if m.group(2).lower() == "tb":
            wert *= 1024
        if wert not in stufen:
            continue
        if _ist_arbeitsspeicher(text, m, ab=ab):
            continue
        gefunden.add(wert)
    if len(gefunden) == 1:
        return gefunden.pop()
    # Mehrdeutig: nur die im Katalog gepflegten Stufen zaehlen noch. Bleibt
    # auch dann mehr als eine uebrig, wird nichts geraten.
    eng = gefunden & bevorzugt
    return eng.pop() if len(eng) == 1 else None


def normalisiere_farbe(roh: str, tabelle: dict) -> Optional[str]:
    """Kanonische Farbe, oder None wenn die Tabelle die Schreibweise nicht
    kennt. Es wird NICHT geraten - eine unbekannte Farbe erscheint im
    Farbbericht am Seitenende, damit die Tabelle wachsen kann."""
    if not roh:
        return None
    return tabelle.get(normalisiere(roh))


# Ein Kuerzel am Ende einer Farbschreibweise ist keine eigene Farbe. o2
# fuehrt dasselbe Galaxy S26 FE als "pistachio" und "pistachio bk" - zwei
# Adressen, 144 Euro Abstand, beide ohne Vertrag. Als zwei Farben gelesen ist
# das ein legitimer Farbaufschlag und der Vergleich nimmt kommentarlos die
# 667 Euro; als EINE Farbe gelesen ist es ein Widerspruch, den die
# Doppelpreisregel faengt.
#
# Warum das hier steht und nicht in `config/farben.yaml`: eine neue
# Farbzuordnung aendert die `sku_id`. Der Altbestand gaelte als ausgelistet
# und entstuende als neue Listung - eine Datenwanderung, die Listungsdauer
# und Preisverlauf jedes betroffenen Geraets auf null zuruecksetzt. Der
# Schluessel wird deshalb beim LESEN gerechnet und beruehrt den Store nicht.
_KUERZEL_MAX = 3


def farbschluessel(farbe_normalisiert: Optional[str], farbe_roh: str) -> str:
    """Die Farbe als Vergleichsschluessel - kanonisch, wenn sie bekannt ist.

    Kennt `config/farben.yaml` die Schreibweise, gewinnt die kanonische
    Farbe: "Navy" und "navy blue" sind dann derselbe Schluessel. Kennt sie
    sie nicht, traegt die normalisierte Rohschreibweise den Schluessel, und
    ein angehaengtes Kuerzel von hoechstens `_KUERZEL_MAX` Zeichen faellt
    weg.

    Die Laengengrenze ist der ganze Schutz dieser Regel: sie trennt "bk" von
    "gold". Ohne sie wuerde aus "titan natur" und "titan schwarz" derselbe
    Schluessel, und zwei echte Farben eines Geraets sahen wie ein
    Doppelpreis aus.
    """
    if farbe_normalisiert:
        return normalisiere(farbe_normalisiert)
    teile = [t for t in normalisiere(farbe_roh).split("-") if t]
    if len(teile) > 1 and len(teile[-1]) <= _KUERZEL_MAX:
        teile = teile[:-1]
    return "-".join(teile)


def farbe_aus_titel(titel: str, tabelle: dict) -> tuple[str, Optional[str]]:
    """Rueckfall, wenn die Quelle kein eigenes Farbfeld hat.

    Gibt (Rohschreibweise wie im Titel, kanonische Farbe) zurueck. Gesucht
    wird die Schreibweise mit den MEISTEN Woertern zuerst, damit "Titan
    Natur" nicht als "Titan" durchgeht.

    DER BRUCHSTUECK-WAECHTER. Steht neben dem Treffer ein Wort, das in
    IRGENDEINER Farbschreibweise der Tabelle vorkommt, ist der Treffer ein
    Bruchstueck einer laengeren Farbe und wird verworfen. Ohne ihn wurde aus
    "Titanium Black" die Farbe `schwarz`, waehrend "Black Titanium" -
    dieselbe Farbe, andere Wortstellung - `titan-schwarz` ergab: zwei SKUs
    fuer ein Geraet. "Rose Gold" faellt damit ganz durch, und das ist die
    richtige Antwort: die Tabelle kennt diese Farbe nicht.
    """
    if not titel:
        return ("", None)
    farbwoerter = {w for schreibweise in tabelle for w in schreibweise.split("-") if w}
    kandidaten = sorted(tabelle.items(), key=lambda kv: -len(kv[0].split("-")))
    for schreibweise, kanonisch in kandidaten:
        woerter = [w for w in schreibweise.split("-") if w]
        if not woerter:
            continue
        muster = (r"\b(?P<vor>[A-Za-zÄÖÜäöüß]+)?[\s\-]*"
                  + r"[\s\-]*".join(re.escape(w) for w in woerter)
                  + r"[\s\-]*(?P<nach>[A-Za-zÄÖÜäöüß]+)?\b")
        treffer = re.search(muster, titel, re.IGNORECASE)
        if not treffer:
            continue
        nachbarn = [treffer.group("vor"), treffer.group("nach")]
        if any(n and normalisiere(n) in farbwoerter for n in nachbarn):
            continue          # Bruchstueck einer laengeren Farbe
        kern = re.search(r"[\s\-]*".join(re.escape(w) for w in woerter),
                         titel, re.IGNORECASE)
        return (kern.group(0).strip(), kanonisch)
    return ("", None)


# Ein gebrauchtes Geraet ist nicht dasselbe Produkt wie ein neues, auch wenn
# der Modellname derselbe ist - freenet fuehrt bereits eine eigene
# "-refurbished"-Strecke. Ohne diese Dimension teilten sich beide dieselbe
# listung_id, und der Preisverlauf sprang zwischen Neu- und Gebrauchtpreis.
#
# Mehrwortmuster stehen BINDESTRICHVERBUNDEN ("wie-neu"), weil sie ueber
# `normalisiere` laufen - dort wird jede Folge von Nicht-Alphanumerik zu
# einem Bindestrich. Als "wie neu" geschrieben landete das Muster im
# Einzelwort-Zweig und wurde gegen eine Menge einzelner Wortmarken geprueft,
# in der ein Zwei-Wort-String nie vorkommen kann: die Zeile stand da und
# konnte nicht treffen.
#
# "erneuert" ist am 29.08.2026 dazugekommen und war der teuerste Eintrag der
# Liste. o2 kennzeichnet dieselbe Gebrauchtstrecke in ZWEI Schreibweisen -
# "Apple iPhone 14 (gebraucht) ..." und "Apple iPhone 14 Pro (erneuert) ...".
# Acht von zehn Geraeten trugen "(gebraucht)" und waren richtig erkannt; die
# zwei mit "(erneuert)" liefen als NEUgeraet mit, unterboten mit ihrem
# Gebrauchtpreis den Vodafone-Neupreis und standen als Sieger in der
# Vergleichstabelle. Ein Gebrauchtpreis, der einen Neupreis schlaegt, ist
# dieselbe Fehlerklasse wie die Buendelzahl, die einen Geraetepreis schlaegt.
_ZUSTAENDE = (
    ("refurbished", ("refurbished", "refurb", "generalueberholt", "erneuert",
                     "renewed", "gebraucht", "wie-neu", "second-hand")),
    ("b-ware", ("b-ware", "bware", "vorfuehrgeraet", "vorfuehrer",
                "ausstellungsstueck")),
)


# Kennzeichen, die im deutschen Handel je nach Haendler Verschiedenes heissen.
# Sie auf "refurbished" zu raten waere genauso falsch wie sie als neu zu
# fuehren - beides ist eine Aussage, die die Quelle nicht deckt. Sie ergeben
# deshalb "unbekannt", und "unbekannt" faellt aus Preisvergleich und
# Preisgrafik heraus (siehe VERGLEICHBARE_ZUSTAENDE).
_UNSICHER = ("neuwertig", "retoure", "open-box", "openbox", "zweite-wahl",
             "2-wahl", "geprueft-und-zertifiziert")

# Ab welcher Laenge ein Zustandsmarker auch gebeugt treffen darf. Acht
# Zeichen halten "erneuert" (8) und "gebraucht" (9) drin und "refurb" (6)
# draussen.
_BEUGBAR_AB = 8

# Welche Zustaende in einer Preisaussage GEGENEINANDER stehen duerfen. Neu-,
# Gebraucht- und B-Warenpreis sind drei verschiedene Preise; die Vergleichs-
# tabelle und die Positionskarte zeigen nur den ersten.
VERGLEICHBARE_ZUSTAENDE = ("", "neu")

# Alle gueltigen Werte von `Listung.zustand`. Seit der Zustand ueber die
# SICHTBARKEIT in Vergleich und Preisgrafik entscheidet (fail closed), laesst
# ein Adapter, der "Neu" oder "new" liefert, seine Listungen stillschweigend
# aus beiden Preisaussagen fallen - ohne Log, ohne Befund im Pruefbericht.
# Deshalb wird der Wert geprueft wie `verfuegbarkeit` und `anbieter_typ`.
ZUSTAENDE = ("neu", "refurbished", "b-ware", "unbekannt")


def serie_aus_modell(modell: str) -> str:
    """Die Baureihe eines Modellnamens.

    `Geraet.generation` ist die Nummer INNERHALB einer Baureihe, kein
    vergleichbarer Jahrgang: Samsungs Galaxy A57 traegt 57, die Galaxy S26
    traegt 26, das Galaxy Z Fold8 traegt 8. Je HERSTELLER verglichen gewinnt
    damit die A-Reihe - "nur aktuelle Generation" zeigte am 29.08.2026 drei
    Galaxy A57 und keine einzige S26, also das aktuelle Flaggschiff nicht.
    Aus demselben Grund waeren "Redmi 17", "Redmi Note 17" und "Xiaomi 17T"
    je Hersteller EINE Generation, obwohl es drei Produktlinien sind.

    Eine Generationszahl ist nur innerhalb ihrer Baureihe eine Zahl. Die
    Baureihe endet vor der ersten Zahl; der Buchstabenteil des Zahltokens
    gehoert noch dazu, weil er die Reihe benennt ("Galaxy S26" -> "Galaxy S",
    "Galaxy A57" -> "Galaxy A"). Traegt der Name gar keine Zahl, ist er
    selbst die Reihe ("iPhone Air").
    """
    teile = []
    # Der Bindestrich trennt wie ein Leerzeichen: "Pixel-11 Pro" ergab sonst
    # die Baureihe "Pixel-11 Pro", also eine eigene Reihe je Variante - dann
    # ist jede Variante ihre eigene "aktuelle Generation", der Filter wird
    # zum No-Op und `portfolio_tiefe` zaehlt Varianten als Jahrgaenge.
    for wort in re.split(r"[\s\-]+", (modell or "").strip()):
        if not wort:
            continue
        treffer = re.match(r"^\(?([A-Za-z]*)(\d)", wort)
        if treffer:
            if treffer.group(1):
                teile.append(treffer.group(1))
            break
        teile.append(wort.strip("()"))
    # Faellt nichts ab - ein Name, der mit einer Ziffer beginnt, oder einer
    # ganz ohne Ziffer -, ist der Name SELBST die Reihe. Das ist der ehrliche
    # Rueckfall: eine geratene Reihe wuerde zwei Produktlinien zusammenwerfen,
    # und das ist teurer als eine Reihe je Modell.
    return " ".join(teile).strip() or (modell or "").strip()


def ohne_zustandswort(farbe: str) -> str:
    """Die Farbe ohne das Zustandskennzeichen.

    o2 schreibt den Zustand in die Farbe ("space schwarz erneuert",
    "titanium black gebraucht"). Bleibt das Wort stehen, fuehrt der
    Farbbericht am Fuss von `/geraete.html` Schreibweisen, die keine Farben
    sind, und dieselbe Farbe steht zweimal in der Arbeitsliste.

    Die Zerlegung gehoert hierher und NICHT in die sku_id: der Zustand ist
    dort bereits eine eigene Dimension (`sku_id(..., zustand)`), das Neu-
    und das Gebrauchtgeraet bleiben also weiterhin zwei SKUs.

    Bleibt nach dem Streichen nichts uebrig, wird die Farbe UNVERAENDERT
    zurueckgegeben: eine geleerte Farbe verloere die Dimension, und zwei
    verschiedene Geraete teilten sich eine ID.
    """
    roh = (farbe or "").strip()
    if not roh:
        return roh
    # Auch die UNKLAREN Kennzeichen: "schwarz neuwertig" ergibt zwar
    # `zustand="unbekannt"`, aber "neuwertig" ist trotzdem keine Farbe und
    # hat in der sku_id nichts verloren.
    woerter = [w for _, gruppe in _ZUSTAENDE for w in gruppe] + list(_UNSICHER)
    rest = roh
    for wort in sorted(woerter, key=len, reverse=True):
        # Ein Bindestrich im Muster steht fuer "Bindestrich ODER Leerzeichen"
        # ("wie-neu" trifft auch "wie neu"). `re.escape` maskiert den
        # Bindestrich, deshalb wird die maskierte Form ersetzt; faellt diese
        # Maskierung in einer kuenftigen Python-Fassung weg, greift der
        # zweite Zweig.
        muster = re.escape(wort).replace(r"\-", r"[\s\-]").replace("-", r"[\s\-]")
        rest = re.sub(rf"(?<![a-z0-9]){muster}(?![a-z0-9])", " ", rest,
                      flags=re.IGNORECASE)
    # Was ein gestrichenes Wort an Klammern und Kommas zuruecklaesst, ist
    # keine Farbe: "Schwarz (gebraucht)" wurde sonst zu "Schwarz ( )" - und
    # landete genau so im Farbbericht, den diese Funktion sauber halten soll.
    rest = re.sub(r"\(\s*\)|\[\s*\]", " ", rest)
    rest = re.sub(r"\s+", " ", rest).strip(" -,;/()[]")
    return rest or roh


def zustand_aus_feldern(*felder) -> str:
    """Der Zustand aus ALLEN Signalen, die eine Quelle traegt.

    Titel, Farbfeld, Kategoriepfad, `itemCondition` - ein Kennzeichen zaehlt,
    egal in welcher Spalte es steht. Das ist die Lehre aus dem Fall vom
    29.08.2026: o2 schrieb "erneuert" AUSSCHLIESSLICH in die Farbe, und ein
    Zustand, den nur eine Spalte kennt, ist trotzdem ein Zustand.

    Die Felder werden verbunden statt einzeln geprueft, weil die
    Mehrwortmuster ("wie neu") sonst an einer Feldgrenze zerrissen wuerden.
    """
    return zustand_aus_titel(" ".join(str(f or "") for f in felder))


def zustand_aus_titel(titel: str) -> str:
    """"neu" | "refurbished" | "b-ware" | "unbekannt"."""
    marken = set(wortmarken(titel))
    text = normalisiere(titel)

    def trifft(wort: str) -> bool:
        if "-" in wort:
            return f"-{wort}-" in f"-{text}-"
        if wort in marken:
            return True
        # Gebeugte Formen. Ein Kategoriepfad heisst "Gebrauchte Handys",
        # nicht "gebraucht", und eine Rubrik "Erneuerte Geraete" - seit der
        # Zustand auch aus dem Pfad gelesen wird, gehen sonst genau die
        # Felder leer aus, wegen derer er dort gelesen wird.
        #
        # Angehaengt werden nur die deutschen Endungen, und nur an Marker ab
        # `_BEUGBAR_AB` Zeichen. Ohne die Laengengrenze faenge "refurb" das
        # Wort "refurbe" - und vor allem waere die Regel eine Praefixsuche,
        # die frueher oder spaeter ein harmloses laengeres Wort trifft.
        if len(wort) < _BEUGBAR_AB:
            return False
        return any(f"{wort}{endung}" in marken
                   for endung in ("e", "es", "er", "en", "em"))

    for name, woerter in _ZUSTAENDE:
        for wort in woerter:
            if trifft(wort):
                return name
    # Erst NACH den eindeutigen Kennzeichen: "iPhone 17 neuwertig
    # refurbished" ist refurbished, nicht unbekannt. Eine eindeutige Angabe
    # wird durch eine unklare daneben nicht wieder unklar.
    for wort in _UNSICHER:
        if trifft(wort):
            return "unbekannt"
    return "neu"


# --------------------------------------------------------------------------
# Geraet und Katalog
# --------------------------------------------------------------------------

@dataclass
class Geraet:
    hersteller: str
    modell: str
    marktstart: str = ""          # YYYY-MM-DD, Marktstart des Modells
    generation: Optional[int] = None
    # Modellname des Vorgaengers, wie er im Katalog steht. Das Feld, an dem
    # die ganze Lifecycle-Auswertung haengt: ohne gepflegte Kette gibt es
    # keine Nachfolger-Analyse.
    vorgaenger: str = ""
    segment: str = ""             # flagship | premium | mid | entry
    speicher: list = field(default_factory=list)
    aliase: list = field(default_factory=list)

    @property
    def device_id(self) -> str:
        return device_id(self.hersteller, self.modell)

    @property
    def vorgaenger_device_id(self) -> str:
        """Leer, wenn kein Vorgaenger gepflegt ist. Der Hersteller ist
        derselbe - ein Nachfolger wechselt nicht die Marke."""
        if not self.vorgaenger:
            return ""
        return device_id(self.hersteller, self.vorgaenger)

    @property
    def schreibweisen(self) -> list[str]:
        return [self.modell] + [a for a in self.aliase if a]


@dataclass
class Katalog:
    geraete: list = field(default_factory=list)

    def __post_init__(self):
        gesehen: dict[str, str] = {}
        for g in self.geraete:
            if g.device_id in gesehen:
                raise ValueError(
                    f"Geraet doppelt im Katalog: {g.hersteller} {g.modell} "
                    f"ergibt dieselbe device_id wie {gesehen[g.device_id]}")
            gesehen[g.device_id] = f"{g.hersteller} {g.modell}"
        self._index = {g.device_id: g for g in self.geraete}
        # Erkennungstabelle: Wortmarkenfolge -> Geraet. Laengste zuerst,
        # damit "iPhone 17 Pro Max" vor "iPhone 17 Pro" und "iPhone 17"
        # greift - ohne diese Reihenfolge liefe die ganze Pro-Max-Klasse
        # unter dem kuerzesten Namen.
        muster: list[tuple[list, Geraet]] = []
        belegt: dict[tuple, Geraet] = {}
        for g in self.geraete:
            for s in g.schreibweisen:
                marken = wortmarken(s)
                if not marken:
                    continue
                schluessel = tuple(marken)
                vorher = belegt.get(schluessel)
                if vorher is not None:
                    if vorher.device_id == g.device_id:
                        continue          # derselbe Eintrag, doppelt genannt
                    # Zwei VERSCHIEDENE Geraete mit derselben Wortmarkenfolge:
                    # die Erkennung waere ab hier zufaellig. Genau so ist der
                    # Alias "Galaxy S25+" entstanden - das Pluszeichen
                    # ueberlebt die Normalisierung nicht, und der Alias fiel
                    # mit dem Modell "Galaxy S25" zusammen.
                    raise ValueError(
                        f"Schreibweise {s!r} ist nach der Normalisierung nicht "
                        f"unterscheidbar: {vorher.hersteller} {vorher.modell} "
                        f"und {g.hersteller} {g.modell} ergeben beide "
                        f"{' '.join(marken)}")
                belegt[schluessel] = g
                muster.append((marken, g))
        muster.sort(key=lambda p: -len(p[0]))
        self._muster = muster

    def nach_id(self, gid: str) -> Optional[Geraet]:
        return self._index.get(gid)

    def vorgaenger_von(self, gid: str) -> Optional[Geraet]:
        g = self._index.get(gid)
        if not g or not g.vorgaenger_device_id:
            return None
        return self._index.get(g.vorgaenger_device_id)

    def nachfolger_von(self, gid: str) -> Optional[Geraet]:
        for g in self.geraete:
            if g.vorgaenger_device_id == gid:
                return g
        return None

    @property
    def hersteller(self) -> list[str]:
        return sorted({g.hersteller for g in self.geraete})


def _fundstellen(heuhaufen: list, nadel: list) -> list:
    """Startindizes, an denen *nadel* zusammenhaengend in *heuhaufen* steht.

    Zusammenhaengend, nicht als Menge: eine reine Mengenpruefung wuerde
    "iPhone 17" auch in "iPhone 16 Pro, passend zum 17er" finden.
    """
    n, k = len(heuhaufen), len(nadel)
    if k == 0 or k > n:
        return []
    return [i for i in range(n - k + 1) if heuhaufen[i:i + k] == nadel]


def _ist_zubehoer(marken: list, ab: int = 0) -> bool:
    """Zubehoer? *ab* ist der Index, an dem der Modellname beginnt.

    Woerter aus `_ZUBEHOER_DAVOR` zaehlen nur, wenn sie VOR dem Modellnamen
    stehen - "Ladekabel fuer iPhone 17" ist Zubehoer, "iPhone 16 inkl.
    Ladekabel" ist ein Geraet mit Beigabe.
    """
    if any(m in _ZUBEHOER_IMMER for m in marken):
        return True
    return any(m in _ZUBEHOER_DAVOR for m in marken[:ab])


def erkenne_geraet(titel: str, katalog: Katalog) -> Optional[Geraet]:
    """Welchen KATALOGEINTRAG trifft dieser Haendlertitel?

    Gibt None, wenn keiner passt ODER wenn die Zuordnung nicht belegbar ist.
    Ein Geraet, das nicht im Katalog steht, wird nicht erfunden - der Katalog
    ist die Liste der verfolgten Modelle, nicht des ganzen Marktes.

    Zwei Sperren neben dem Katalogabgleich:
      * Zubehoer (siehe `_ist_zubehoer`),
      * ein Modellzusatz direkt hinter dem Treffer. "Pixel 10 Pro Fold" ist
        nicht "Pixel 10 Pro", und weil beide beim selben Haendler stehen,
        waere die Verwechslung keine Ungenauigkeit, sondern eine erfundene
        Preisbewegung von 800 Euro - in jedem Lauf, hin und zurueck.
    """
    marken = wortmarken(titel)
    if not marken or any(m in _ZUBEHOER_IMMER for m in marken):
        return None
    for nadel, geraet in katalog._muster:   # nach Laenge absteigend sortiert
        for start in _fundstellen(marken, nadel):
            danach = marken[start + len(nadel):]
            if danach and danach[0] in _MODELLZUSATZ:
                continue          # der Titel meint ein anderes Modell
            if _ist_zubehoer(marken, ab=start):
                continue
            return geraet
    return None


# --------------------------------------------------------------------------
# SKU und Listung
# --------------------------------------------------------------------------

@dataclass
class Sku:
    sku_id: str
    device_id: str
    speicher_gb: Optional[int] = None
    farbe_roh: str = ""
    farbe_normalisiert: Optional[str] = None
    ean: str = ""


_DATUM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class Listung:
    """Was EIN Anbieter zu EINEM Zeitpunkt fuer eine SKU verlangt.

    Die Zusicherungen stehen im Konstruktor, nicht im Store: eine Listung
    ohne Quelle und Abrufdatum laesst sich gar nicht erst bauen. Damit kann
    keine Zahl auf die Seite geraten, die niemand nachschlagen kann - das
    Nachpruefbarkeitsversprechen des ganzen Portals.
    """
    sku_id: str
    device_id: str
    anbieter: str
    anbieter_typ: str
    quelle_url: str
    abgerufen_am: str
    netz: str = ""
    preis_ohne_vertrag: Optional[float] = None
    uvp: Optional[float] = None
    preis_mit_vertrag_ab: Optional[float] = None
    zuzahlung: Optional[float] = None
    tarif_referenz: str = ""
    verfuegbarkeit: str = "unbekannt"
    confidence: str = "mittel"
    speicher_gb: Optional[int] = None
    farbe_roh: str = ""
    farbe_normalisiert: Optional[str] = None
    ean: str = ""
    zustand: str = "neu"          # neu | refurbished | b-ware | unbekannt
    titel_roh: str = ""
    # Die Einstiegsseite, auf der dieses Geraet gefunden wurde. Sie ist der
    # Schluessel der Auslistungslogik: gealtert wird nur, was auf einer
    # WIRKLICH GELESENEN Seite fehlte. Ohne dieses Feld ruecken bei jedem
    # Teilausfall die Geraete der ausgefallenen Seite Richtung "ausgelistet"
    # (dieselbe Falle wie promo_store.mark_stale/gepruefte_seiten).
    einstieg_url: str = ""

    def __post_init__(self):
        if not (self.quelle_url or "").strip():
            raise ValueError("Listung ohne quelle_url: ein Preis ohne Beleg "
                             "ist auf diesem Portal keine Zahl")
        if not _DATUM_RE.match((self.abgerufen_am or "").strip()):
            raise ValueError("Listung ohne gueltiges abgerufen_am "
                             "(erwartet YYYY-MM-DD)")
        if self.verfuegbarkeit not in VERFUEGBARKEITEN:
            raise ValueError(f"unbekannte verfuegbarkeit: {self.verfuegbarkeit!r}")
        if self.anbieter_typ not in ANBIETER_TYPEN:
            raise ValueError(f"unbekannter anbieter_typ: {self.anbieter_typ!r}")
        if self.zustand not in ZUSTAENDE:
            raise ValueError(f"unbekannter zustand: {self.zustand!r}")
        if self.confidence not in CONFIDENCE:
            raise ValueError(f"unbekannte confidence: {self.confidence!r}")
        for feld in ("preis_ohne_vertrag", "uvp", "preis_mit_vertrag_ab", "zuzahlung"):
            wert = getattr(self, feld)
            if wert is None:
                continue
            wert = float(wert)
            if wert < 0:
                raise ValueError(f"negativer preis in {feld}: {wert}")
            setattr(self, feld, round(wert, 2))
        # Teil C4: "iPhone fuer 1 Euro" ist ohne den Tarif dahinter eine Zahl
        # ohne Bedeutung. JEDE Buendelzahl braucht ihren Tarif - auch
        # `preis_mit_vertrag_ab`, sonst waere sie das Schlupfloch, durch das
        # der Lockpreis doch auf die Seite kaeme.
        for feld in ("zuzahlung", "preis_mit_vertrag_ab"):
            if getattr(self, feld) is not None and not (self.tarif_referenz or "").strip():
                raise ValueError(f"{feld} ohne tarif_referenz: eine Buendelzahl "
                                 "ohne ihren Tarif ist bedeutungslos")

    @property
    def listung_id(self) -> str:
        return listung_id(self.sku_id, self.anbieter)

    @property
    def preisart(self) -> str:
        """Welche der beiden Preisarten traegt diese Listung?

        Teil C4: Geraetepreis ohne Vertrag und Zuzahlung im Tarifbuendel sind
        nicht dieselbe Zahl und duerfen nie in derselben Spalte der
        Positionskarte landen, ohne gekennzeichnet zu sein. Diese Property
        ist die Kennzeichnung.
        """
        if self.preis_ohne_vertrag is not None:
            return "ohne_vertrag"
        if self.zuzahlung is not None:
            return "buendel"
        return "kein_preis"

    @property
    def preis(self) -> Optional[float]:
        """Der Preis DIESER Preisart. Wer beide Arten mischen will, muss es
        ausdruecklich tun - hier gibt es keinen gemeinsamen Nenner."""
        if self.preisart == "ohne_vertrag":
            return self.preis_ohne_vertrag
        if self.preisart == "buendel":
            return self.zuzahlung
        return None

    def sku(self) -> Sku:
        return Sku(sku_id=self.sku_id, device_id=self.device_id,
                   speicher_gb=self.speicher_gb, farbe_roh=self.farbe_roh,
                   farbe_normalisiert=self.farbe_normalisiert, ean=self.ean)


def lies_listung(*, titel: str, anbieter: str, anbieter_typ: str,
                 quelle_url: str, abgerufen_am: str, katalog: Katalog,
                 farben: dict, netz: str = "",
                 preis_ohne_vertrag: Optional[float] = None,
                 uvp: Optional[float] = None,
                 preis_mit_vertrag_ab: Optional[float] = None,
                 zuzahlung: Optional[float] = None,
                 tarif_referenz: str = "",
                 verfuegbarkeit: str = "unbekannt",
                 confidence: str = "mittel",
                 speicher_gb: Optional[int] = None,
                 farbe_roh: str = "", ean: str = "",
                 zustand_hinweis: str = "",
                 einstieg_url: str = "") -> Optional[Listung]:
    """Die ganze Kette in einem Aufruf - der Einstieg fuer jeden Adapter.

    Titel -> Katalogeintrag -> Speicher -> Farbe -> IDs -> Listung. Gibt
    None, wenn der Titel kein Geraet des Katalogs trifft.

    `speicher_gb` und `farbe_roh` duerfen von der Quelle kommen (ld+json
    traegt beides oft strukturiert); dann wird der Titel dafuer nicht mehr
    befragt. Das ist die Rangfolge aus Teil C1: strukturierte Daten schlagen
    Textextraktion.
    """
    geraet = erkenne_geraet(titel, katalog)
    if geraet is None:
        return None

    if speicher_gb is None:
        speicher_gb = speicher_aus_titel(titel, geraet.speicher or None)
    else:
        speicher_gb = int(speicher_gb)

    kanonisch = None
    if not farbe_roh:
        farbe_roh, kanonisch = farbe_aus_titel(titel, farben)

    gid = geraet.device_id
    # Der Zustand wird aus ALLEN verfuegbaren Signalen abgeleitet, nicht nur
    # aus dem Titel: eine Quelle, die Farbe strukturiert liefert, traegt das
    # Kennzeichen unter Umstaenden NUR dort ("grau erneuert"). Das Farbfeld
    # gehoert deshalb in die Pruefung - ein Zustand, den nur eine Spalte
    # kennt, ist trotzdem ein Zustand. `zustand_hinweis` traegt, was die
    # Quelle sonst noch weiss: `itemCondition` aus dem ld+json, den
    # Kategoriepfad, die Rubrik einer Gebrauchtstrecke.
    zustand = zustand_aus_feldern(titel, farbe_roh, zustand_hinweis, quelle_url)
    # ERST lesen, DANN streichen: die Farbe ist bei manchen Quellen der
    # einzige Traeger des Kennzeichens. Umgekehrt haette die Zerlegung das
    # Signal geloescht, bevor es jemand gelesen hat.
    farbe_roh = ohne_zustandswort(farbe_roh) if farbe_roh else farbe_roh
    kanonisch = normalisiere_farbe(farbe_roh, farben) if farbe_roh else None
    # Unbekannte Farbe: die Rohschreibweise traegt die ID. Der Preis dafuer
    # ist, dass zwei unbekannte Schreibweisen derselben Farbe zwei SKUs
    # ergeben - das ist ehrlicher als sie zusammenzuwerfen, und der
    # Farbbericht am Seitenende sagt, welche Zeile in config/farben.yaml
    # fehlt.
    sid = sku_id(gid, speicher_gb, kanonisch or farbe_roh or None, zustand)

    return Listung(
        sku_id=sid, device_id=gid, anbieter=anbieter, anbieter_typ=anbieter_typ,
        quelle_url=quelle_url, abgerufen_am=abgerufen_am, netz=netz,
        preis_ohne_vertrag=preis_ohne_vertrag, uvp=uvp,
        preis_mit_vertrag_ab=preis_mit_vertrag_ab, zuzahlung=zuzahlung,
        tarif_referenz=tarif_referenz, verfuegbarkeit=verfuegbarkeit,
        confidence=confidence, speicher_gb=speicher_gb, farbe_roh=farbe_roh,
        farbe_normalisiert=kanonisch, ean=ean, zustand=zustand,
        titel_roh=(titel or "").strip(), einstieg_url=einstieg_url)
