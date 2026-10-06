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

from ..analyze.tco_store import basis_aus_satz, id_aus_satz
from ..tco_model import (
    Buendel,
    POSTEN_ANSCHLUSS,
    POSTEN_BUENDEL,
    POSTEN_RATE,
    POSTEN_ZUZAHLUNG,
    TCO_HORIZONT,
    tco_24,
    zeitraum_vergleichbar,
)
from . import geraete_bewegung
from . import geraete_notbremse as notbremse
from .anbieter_farben import STRICHMUSTER, stil_fuer
from .geraete_tco_band import ERWARTETE_ANBIETER, band_label
from .geraete_tco_karten import kurz_datum, label_der_leitzahl, phasen_fuer_buendel
from .verlauf import MONATE_DE

log = logging.getLogger(__name__)

ANBIETER_FOLGE = ("Telekom", "Vodafone", "o2", "1&1", "congstar")


def _zr_farbe(anbieter: str) -> str:
    """Die Linienfarbe - fuer Pfad, Achsen-Name und `_anbieter_punkte`."""
    return stil_fuer(anbieter).farbe


def _zr_marker_farbe(anbieter: str) -> str:
    """Die PUNKTfarbe - bei congstar bewusst nicht die Linienfarbe (gelber
    Marker auf schwarzer Linie, sonst waere das Gelb auf hellem Papier die
    einzige Spur des Anbieters)."""
    return stil_fuer(anbieter).marker_farbe


EIGEN = "Vodafone"

BREIT_W, BREIT_MIN_H = 1136, 420
SCHMAL_W, SCHMAL_MIN_H = 358, 380
KOPF_FREIRAUM_BREIT, KOPF_FREIRAUM_SCHMAL = 18, 10
MASSSTAB_FREIRAUM_ANTEIL = 0.12
TREFFERFLAECHE_RADIUS = 12

KACHELN_MAX = 6

MIN_XTICK_ABSTAND = 34

ACHSENBRUCH_ANTEIL = 0.10

ENDLABEL_RAND = 6

LUECKE_TAGE_SCHWELLE = 10

AUTO_SICHTBAR_AB_MESTAGEN = 2

_NAEHERUNG_SATZ = (
    "Referenzrechnung, kein Angebot: der Vodafone-Bündelpreis "
    "zu diesem Gerät ist noch nicht erhoben – gerechnet aus "
    "dem eigenen Barpreis des Geräts und dem Tarifgrundpreis "
    "aus dem Produktinformationsblatt"
)
_NAEHERUNG_KEIN_WEG = (
    " Für die Näherung gibt es keine Messung je Messtag – "
    "deshalb steht hier keine Rechung."
)


def _euro(betrag) -> str:
    """1.234,56 € - dieselbe Schreibweise wie ueberall auf der Seite."""
    if betrag is None:
        return ""
    return f"{betrag:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".") + " €"


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
    """„1. Oktober 2026“ - Monatsname aus fester Liste, nie vom Locale."""
    tag = date.fromisoformat(iso)
    return f"{tag.day}. {MONATE_DE[tag.month - 1]} {tag.year}"


def _mon_kurz(monate: list) -> str:
    """„36 Mon." / „24/36 Mon." - das Etikett AN der Kurve (P0-B-z1).

    Kurz, weil es im Bild neben dem Anbieternamen steht (Antonios Stil:
    wenig Text, keine Erklaerzeile). Die Zahlen sind GELESEN
    (`_zeitraeume_aus` -> `Tco.leitzahl_monate`), nicht gerechnet; ohne
    lesbaren Zeitraum steht hier nichts - eine Annahme waere schlimmer
    als die Luecke (Clean Code 4).
    """
    if not monate:
        return ""
    return "/".join(str(m) for m in monate) + " Mon."


def _zeitraum_wort(monate: list) -> str:
    """„24 Monate" / „24 und 36 Monate" - die Beschriftung des Bildes.

    P0-B-z1: der Titel darf keinen Zeitraum behaupten, der nicht fuer
    ALLE Kurven gilt. Kommen mehrere vor, nennt er sie - in wenigen
    Worten; die Zuordnung zur einzelnen Kurve steht am Kurvenende
    (`_mon_kurz`). Leere Liste heisst „kein Zeitraum gelesen" und ergibt
    KEIN Wort (der Aufrufer laesst die Angabe dann weg).
    """
    zahlen = [str(m) for m in monate]
    if not zahlen:
        return ""
    if len(zahlen) == 1:
        return f"{zahlen[0]} Monate"
    return f"{', '.join(zahlen[:-1])} und {zahlen[-1]} Monate"


def _kurz_name(modell: dict) -> str:
    """„Apple iPhone 17 Pro 256 GB" -> „iPhone 17 Pro" (Kachel/Vorschau)."""
    titel = modell.get("titel") or modell.get("id", "")
    hersteller = modell.get("hersteller") or ""
    speicher = modell.get("speicher")
    if hersteller and titel.startswith(hersteller + " "):
        titel = titel[len(hersteller) + 1 :]
    if speicher:
        titel = titel.rstrip()
        suffix = f" {speicher} GB"
        if titel.endswith(suffix):
            titel = titel[: -len(suffix)]
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
    if not hersteller or kurz == hersteller or kurz.startswith(hersteller + " "):
        return kurz
    return f"{hersteller} {kurz}"


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _band_zeilen(modell: dict) -> dict:
    """Je Band des Modells: die Zeilen (beste je Anbieter) und Luecken.

    Dieselbe Auswahl wie der Prototyp (`zahlen_sammeln.py`): vergleichbare,
    belastbare Karten, aufsteigend nach TCO-24, je Anbieter die beste -
    die Vodafone-Näherung ergänzt ein Band, in dem kein eigenes Bündel
    steht. Die Naeherung ist KEIN Angebot, aber der Massstab des Bandes.

    A3 (STRATEGIE GERAETE V4): ALTE Angebote sind keine Zeilen mehr, aber
    auch nicht weg - sie stehen in `alt` (beste je Anbieter, dieselbe
    Wahl), und der Antwort-Satz nennt ihren letzten Stand. Ein altes
    Angebot verdraengt kein frisches, auch nicht beim selben Anbieter:
    die frischen kommen zuerst an die Reihe.

    Notbremse: eine Karte, die nicht zaehlt (Schätzung, abgelaufene Aktion),
    stellt weder Zeile noch Sieger; sie steht benannt in `gesperrt`.
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
        brauchbar = sorted(
            (
                k
                for k in satz["karten"]
                if k.get("vergleichbar")
                and k.get("belastbar")
                and k.get("gesamt") is not None
            ),
            key=lambda k: k["gesamt"],
        )
        gesperrt = [k for k in brauchbar if not notbremse.zaehlt(k)]
        brauchbar = [k for k in brauchbar if notbremse.zaehlt(k)]
        kandidaten = [
            k
            for k in brauchbar
            if zeitraum_vergleichbar(k.get("leitzahl_monate"), TCO_HORIZONT)
        ]
        fremd = [
            k
            for k in brauchbar
            if k.get("frisch", True)
            and not zeitraum_vergleichbar(k.get("leitzahl_monate"), TCO_HORIZONT)
        ]
        zeilen, alt, gesehen = [], [], set()
        for karte in (k for k in kandidaten if k.get("frisch", True)):
            if karte["anbieter"] in gesehen:
                continue
            gesehen.add(karte["anbieter"])
            zeilen.append(karte)
        for karte in (k for k in brauchbar if not k.get("frisch", True)):
            if karte["anbieter"] in gesehen:
                continue
            gesehen.add(karte["anbieter"])
            alt.append(karte)
        naeherung = next(
            (
                k
                for k in satz["karten"]
                if k.get("naeherung") and k.get("gesamt") is not None
            ),
            None,
        )
        if naeherung is not None and EIGEN not in gesehen:
            zeilen.append(naeherung)
            gesehen.add(EIGEN)
        zeilen.sort(key=lambda k: k["gesamt"])
        fertig[band] = {
            "zeilen": zeilen,
            "karten": satz["karten"],
            "alt": alt,
            "fremd": fremd,
            "gesperrt": gesperrt,
        }
    return fertig


def _alternativen(karten: list, band: str, anbieter: str) -> list[dict]:
    """Die besten Bänder EINES Anbieters, der im gewählten Band fehlt.

    §4.5: „fehlende Anbieter MIT NAMEN und Alternativ-Bändern samt Betrag
    in Klammern" - der Leser sieht nicht nur DASS einer fehlt, sondern wo
    er steht. Nur ECHTE Karten (Bündel mit SKU oder die Näherung) sagen
    etwas darüber, wo ein Anbieter steht; die Leerkarte der Festanbieter
    ist kein Angebot. Und seit A3 nur FRISCHE: ein altes Angebot ist keine
    Alternative von heute (`geraete_tco_karten.ist_frisch`, Clean Code 7 -
    dieselbe Definition wie Zeilen und Kacheln). Und nur Karten, die
    zaehlen: eine Schätzung ist auch als Alternative kein Preis.

    P0-B-z1: jede Alternative traegt ihren ZEITRAUM mit
    (`leitzahl_monate`, gelesen). Ohne ihn stand im Luecken-Satz ein
    36-Monats-Betrag als „mittel 2.019,54 €" mitten unter
    24-Monats-Zahlen. Und die Wahl der guenstigsten je Band vergleicht
    nur INNERHALB eines Zeitraums: der Zeitraum des Horizonts zuerst,
    sonst der kuerzeste gemessene - ein Minimum ueber zwei Laufzeiten
    waere dieselbe Rangfolge, die das Tor verbietet.
    """
    beste: dict[str, dict] = {}
    for karte in karten:
        if karte.get("anbieter") != anbieter:
            continue
        if not karte.get("frisch", True) or not notbremse.zaehlt(karte):
            continue
        if not (karte.get("sku_id") or karte.get("naeherung")):
            continue
        b = karte.get("band")
        if (
            b is None
            or not karte.get("vergleichbar")
            or karte.get("gesamt") is None
            or b == band
        ):
            continue
        monate = karte.get("leitzahl_monate")
        rang = (
            0 if zeitraum_vergleichbar(monate, TCO_HORIZONT) else 1,
            monate if monate is not None else 10**6,
            karte["gesamt"],
        )
        if b not in beste or rang < beste[b]["rang"]:
            beste[b] = {"rang": rang, "tco": karte["gesamt"], "monate": monate}
    return [
        {"band": b, "tco": v["tco"], "monate": v["monate"]}
        for b, v in sorted(beste.items())
    ]


def _luecken(
    zeilen: list,
    karten: list,
    band: str,
    fremd: list | None = None,
    gesperrt: list | None = None,
) -> list[dict]:
    """Je erwartetem Anbieter ohne Zeile: der Grund, in EINEM Satz zusammen.

    Antonio 9b.7: „Wenn es nichts gibt, dann brauchst du es nicht
    anzuzeigen von den jeweiligen Anbietern" - die Namen stehen im SAMMEL-
    satz, nie als eigene Zeile mit leerem Inhalt.

    Seit A3 gibt es einen VIERten Grund: der Anbieter führt ein Bündel,
    aber nur mit altem Abruf - „kein Bündel in diesem Band" waere gelogen
    (harte Regel 9), der alte Preis darf aber auch nicht als heutiger
    Alternative-Betrag stehen.

    S2-3 (Diff-Prüfung 21.09.2026): gefragt ist DIESES Band - die
    Frische-Prüfung muss die Karten DES BANDES meinen, nicht alle Karten
    des Anbieters. Vorher gewann der Anbieter-Weitblick: Telekom mit
    einem alten Klein-Bündel (720,76 EUR vom 15.09.) und einem frischen
    Groß-Bündel bekam im Band klein „kein-belastbares" - die Seite sagte
    „Kein Bündel in diesem Band: Telekom", obwohl die alte Klein-Karte
    als alt-Zeile direkt darüber steht. Reihenfolge jetzt: gar kein
    Bündel - kein Bündel in DIESEM Band - nur alter Stand in diesem
    Band - frisch im Band, aber nicht belastbar.

    P0-B-h3 (Befund 3): und als letzter Grund `anderer-zeitraum` - das
    Bündel ist da und belastbar, seine Leitzahl trägt nur einen anderen
    Zeitraum als diese Tafel (1&1, 36 Monate). Er steht ZULETZT, weil er
    die Fälle mit vorhandenem Bündel aufteilt: erst seit P0-B-h3 fällt
    eine solche Karte aus `_band_zeilen` heraus, und "Kein Bündel in
    diesem Band" wäre für sie falsch. `fremd` ist dabei genau der Eimer,
    den das Tor in `_band_zeilen` gefüllt hat - dieselbe Menge, keine
    zweite Ableitung.
    """
    gesehen = {z["anbieter"] for z in zeilen}
    luecken = []
    for anbieter in ANBIETER_FOLGE:
        if anbieter in gesehen:
            continue
        eigene = [
            k
            for k in karten
            if k["anbieter"] == anbieter and (k.get("sku_id") or k.get("naeherung"))
        ]
        namen = notbremse.namen(
            [k for k in gesperrt or [] if k["anbieter"] == anbieter]
        )
        if not eigene:
            grund = "gar-kein-buendel"
        elif not any(k.get("band") == band for k in eigene):
            grund = "anderes-band"
        elif not any(k.get("frisch", True) for k in eigene if k.get("band") == band):
            grund = "nur-alte"
        elif namen:
            grund = "zaehlt-nicht"
        else:
            grund = "kein-belastbares"
        monate = None
        fremde = sorted(
            k["leitzahl_monate"]
            for k in (fremd or [])
            if k["anbieter"] == anbieter and k.get("leitzahl_monate") is not None
        )
        if fremde:
            grund, monate = "anderer-zeitraum", fremde[0]
        luecken.append(
            {
                "anbieter": anbieter,
                "grund": grund,
                "monate": monate,
                "alternativ": _alternativen(karten, band, anbieter),
                "gesperrt": namen,
            }
        )
    return luecken


def _alt_zeitraum(monate) -> str:
    """ " über 36 Monate" - der Zeitraum eines Alternativ-Betrags, oder "".

    Nur bei ABWEICHUNG vom Horizont: eine 24 hinter jeder Zahl in einem
    Satz, der ohnehin von 24 Monaten spricht, waere dieselbe Angabe
    zweimal am selben Ort. Ein unlesbarer Zeitraum wird BENANNT, nie als
    Horizont angenommen (Clean Code 4).
    """
    if zeitraum_vergleichbar(monate, TCO_HORIZONT):
        return ""
    if monate is None:
        return " über eine nicht gemessene Laufzeit"
    return f" über {_zeitraum_wort([monate])}"


def _stufe(band_labels: dict, band: str) -> str:
    """Der Name der Stufe ("XS") aus dem Katalog, sonst aus dem Schluessel."""
    return (band_labels.get(band) or {}).get("label") or band_label(band)


def _luecke_text(luecken: list, band_labels: dict) -> str | None:
    if not luecken:
        return None
    anderes, gar_nicht, nur_alt, fremd, gesperrt = (list[str]() for _ in range(5))
    eimer = {"gar-kein-buendel": gar_nicht, "nur-alte": nur_alt}
    for l in luecken:
        name = l["anbieter"]
        if l["alternativ"]:
            alt = " · ".join(
                f"{_stufe(band_labels, a['band'])} "
                f"{_euro(a['tco'])}"
                f"{_alt_zeitraum(a.get('monate'))}"
                for a in l["alternativ"]
            )
            name += f" ({alt})"
        if l["grund"] == "anderer-zeitraum":
            fremd.append(
                f"{l['anbieter']} ({l['monate']} Monate)"
                if l.get("monate") is not None
                else l["anbieter"]
            )
        elif l["grund"] == "zaehlt-nicht":
            gesperrt += l["gesperrt"]
        else:
            eimer.get(l["grund"], anderes).append(name)
    teile = []
    if anderes:
        teile.append("Kein Bündel in diesem Band: " + ", ".join(anderes) + ".")
    if fremd:
        teile.append(
            f"Nur über eine andere Laufzeit, nicht über "
            f"{TCO_HORIZONT} Monate: " + ", ".join(fremd) + "."
        )
    if gesperrt:
        teile.append("Nicht im Vergleich: " + ", ".join(gesperrt) + ".")
    if nur_alt:
        teile.append("Kein aktueller Stand: " + ", ".join(nur_alt) + ".")
    if gar_nicht:
        teile.append(
            ", ".join(gar_nicht)
            + " "
            + ("führt" if len(gar_nicht) == 1 else "führen")
            + " das Gerät gar nicht im Bündel."
        )
    return " ".join(teile) or None


def _antwort_html(
    modell: dict,
    band: str,
    zeilen: list,
    band_katalog: dict,
    alte: list | None = None,
    fremd: list | None = None,
    gesperrt: list | None = None,
) -> str:
    """Der Antwort-Satz des Paar-Blocks.

    Seit P4/D4 (STRATEGIE_GERAETE_V3, 18.09.2026) traegt er das
    TCO-Delta zur Vodafone-Referenz NICHT mehr im Satz - es steht als
    EIGENE Leitzahl-Zeile ueber ihm (`_leitzahl_html`, DIE ANTWORT IST
    DIE GROESSTE ZAHL, design.md Regel 1). Dieselbe Rechnung, keine
    zweite Stelle: Der Satz nennt Anbieter, TCO-24 und Ø je Monat, die
    Leitzahl den Abstand zur Referenz.

    A3 (STRATEGIE_GERAETE_V4, 20.09.2026): steht in einem Band KEIN
    frisches Angebot, aber ein altes, sagt der Satz den letzten Stand
    MIT DATUM - „führt kein Anbieter ein Bündel" waere gelogen (harte
    Regel 9), und ein Datum wird nie geraten: keines lesbar heisst
    „unbekannt" (Clean Code 4).

    P0-B-h3 (Befund 3): dieselbe Regel fuer den fremden Zeitraum. Ein
    Band, dessen einziges Angebot seine Leitzahl ueber 36 Monate traegt
    (1&1), hat keine Zeile dieser Tafel - „führt kein Anbieter ein
    Bündel" waere dort genauso gelogen. Der Satz nennt Anbieter, Betrag
    und den Zeitraum, den der Betrag traegt. Am Bestand vom 21.09.2026
    traf das 12 (Modell, Band)-Tafeln; ohne diesen Zweig fielen sie ganz
    aus der Auswahl (`aufbereiten`).
    """
    name = _esc(_satz_name(modell))
    label = band_katalog.get("label", band)
    bereich = band_katalog.get("bereich") or ""
    klammer = f" ({bereich})" if bereich else ""
    if not zeilen:
        alte = alte or []
        alt_seit = max(
            (
                k.get("abgerufen_am") or ""
                for k in alte
                if kurz_datum(k.get("abgerufen_am") or "")
            ),
            default="",
        )
        if alte and alt_seit:
            return (
                f"Beim {name} im Band {label}{klammer} liegt kein "
                f"aktueller Stand vor – die letzte Messung ist vom "
                f"{kurz_datum(alt_seit)}."
            )
        if alte:
            return (
                f"Beim {name} im Band {label}{klammer} liegt kein "
                f"aktueller Stand vor – das Abrufdatum der letzten "
                f"Bündel ist unbekannt."
            )
        fremd = fremd or []
        if fremd:
            beste_fremd = fremd[0]
            monate = beste_fremd.get("leitzahl_monate")
            zeit = (
                f"{monate} Monate"
                if monate is not None
                else "eine nicht gemessene Laufzeit"
            )
            return (
                f"Beim {name} im Band {label}{klammer} führt nur "
                f"{_esc(beste_fremd['anbieter'])} – und nur über "
                f"{zeit}: <b class='gr-zr-zahl'>"
                f"{_euro(beste_fremd['gesamt'])}</b> "
                f"({_esc(beste_fremd.get('tarif') or '')}"
                f"{_gb_teil(beste_fremd)}). Über zwei Laufzeiten gibt "
                f"es keinen Vergleich mit {TCO_HORIZONT} Monaten."
            )
        if gesperrt:
            wer = _esc(", ".join(notbremse.namen(gesperrt)))
            return (
                f"Beim {name} im Band {label}{klammer} steht kein Bündel "
                f"im Vergleich: {wer}."
            )
        return f"Beim {name} im Band {label}{klammer} führt kein Anbieter ein Bündel."
    beste = zeilen[0]
    kern = (
        f"<b class='gr-zr-zahl'>{_euro(beste['gesamt'])}</b> Kosten über "
        f"{TCO_HORIZONT} Monate, Ø <b class='gr-zr-zahl'>{_schnitt(beste)}</b> "
        f"({_esc(beste.get('tarif') or '')}{_gb_teil(beste)})"
    )
    if len(zeilen) == 1 and beste["anbieter"] == EIGEN:
        andere = [k for k in gesperrt or [] if k["anbieter"] != EIGEN]
        if andere:
            return (
                f"Beim {name} im Band {label}{klammer} steht nur Vodafone im "
                f"Vergleich: {kern}. Nicht im Vergleich: "
                f"{_esc(', '.join(notbremse.namen(andere)))}."
            )
        return f"Beim {name} im Band {label}{klammer} führt nur Vodafone: {kern}."
    satz = (
        f"Beim {name} im Band {label}{klammer} ist "
        f"{_esc(beste['anbieter'])} am günstigsten: {kern}"
    )
    eigen = next((z for z in zeilen if z["anbieter"] == EIGEN), None)
    if eigen is beste:
        zweit = zeilen[1] if len(zeilen) > 1 else None
        satz = f"Beim {name} im Band {label}{klammer} führt Vodafone: {kern}"
        if zweit is not None:
            satz += (
                f" Nächster Anbieter: {_esc(zweit['anbieter'])} "
                f"({_euro(zweit['gesamt'])})."
            )
    elif eigen is None:
        satz += " — Vodafone führt in diesem Band kein Bündel."
    return satz if satz.endswith(".") else satz + "."


def _leitzahl_html(zeilen: list) -> str | None:
    """P4/D4: das TCO-Delta als EIGENE Leitzahl-Zeile ueber dem Antwort-Satz.

    Bis P4 stand der Abstand zur Vodafone-Referenz als 13-px-<b> mitten
    im Satz (design.md §4: "Die wichtigste Zahl steht in 13 px mitten in
    einem Satz") - die Antwort des Vergleichs-Reiters war damit die
    KLEINSTE wichtigen Zahl der Tafel. Jetzt ist sie die groesste Schrift
    des ersten Viewports (.gr-leit-zahl, clamp 32-60 px); der Satz
    darunter traegt die Umstaende. Die Zahl selbst faellt aus dem SATZ
    (keine Zahl zweimal am selben Ort), der Referenzbetrag steht in der
    Klammer des Labels - unverändert derselbe Wert, keine zweite Rechnung.

    None, wenn es kein Delta gibt: Vodafone fuehrt selbst, fuehrt im
    Band kein Bündel oder ist allein auf der Tafel - dann gibt es keinen
    Abstand, und der Antwort-Satz traegt die Antwort allein."""
    if not zeilen:
        return None
    beste = zeilen[0]
    eigen = next((z for z in zeilen if z["anbieter"] == EIGEN), None)
    if eigen is None or eigen is beste:
        return None
    delta = round(eigen["gesamt"] - beste["gesamt"], 2)
    return (
        f"<b class='gr-leit-zahl'>{_euro(delta)}</b>"
        f"<span class='gr-leit-label'>{_esc(beste['anbieter'])} "
        f"unter Vodafone "
        f"({_euro(eigen['gesamt'])}"
        f"{', Näherung' if eigen.get('naeherung') else ''})</span>"
    )


def _schnitt(karte: dict) -> str:
    monat = karte.get("schnitt_monat")
    if monat is None:
        return ""
    return (
        f"{monat:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
        + " €/Monat"
    )


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
    link = (
        f"<a href='{_esc(url)}' target='_blank' rel='noopener'>"
        f"{_esc(beste['anbieter'])}&nbsp;↗</a>"
        if url
        else _esc(beste["anbieter"])
    )
    datum = beste.get("abgerufen_am") or ""
    datum_teil = f", abgerufen am {_datum_de(datum)}" if datum else ""
    return (
        f"So gerechnet: <code>Kosten über {TCO_HORIZONT} Monate = "
        f"Anzahlung + "
        f"{TCO_HORIZONT} × Tarifgrundpreis + alle Geräteraten + "
        f"Anschlusspreis</code> — Boni bleiben außerhalb. Beleg des "
        f"günstigsten Angebots: {link}{datum_teil}."
    )


def _buendel_aus_messung(messung: dict, tarife: dict | None = None) -> Buendel | None:
    """Das Buendel EINER Messung - aus Historien-Zeile und Stand.

    A1 (20.09.2026): die EINE Baustelle dafuer. `_rechung` (das Panel) und
    `_messungen` (Punkte und Auswahl) bauen denselben Satz - zwei Bauten
    waeren zwei Rechnungen. Die Preisphasen des Tarifs kommen aus dem
    Tarifbestand dazu (`phasen_fuer_buendel`, dieselbe Stelle wie die
    Vodafone-Referenz und die Bündel-Anreicherung der Hauptansicht) - nur
    ohne Widerspruch zur gemessenen Monatsrate (QA-Fix 20.09.2026), sonst
    rechnete die Zeitreihe andere Punkte als die Karte daneben sagt.
    None, wenn sich die Zeile nicht als Buendel lesen laesst.
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
            laufzeit_monate=satz.get("laufzeit_monate"),
            anschlusspreis=satz.get("anschlusspreis"),
            zustand=satz.get("zustand") or "",
            quelle_url=satz.get("quelle_url") or "",
            abgerufen_am=satz.get("abgerufen_am") or "",
        )
    except (ValueError, TypeError) as exc:
        log.warning(
            "Zeitreihe: Messung %s am %s nicht als Buendel lesbar "
            "(%s) - kein Punkt, kein Panel.",
            satz.get("id"),
            satz.get("datum"),
            exc,
        )
        return None
    if b.tarif_id:
        b.tarif_phasen = phasen_fuer_buendel(
            (tarife or {}).get(b.tarif_id) or {}, b.tarif_monatlich
        )
    return b


def _messwert(
    messung: dict, tarife: dict | None = None
) -> tuple[float | None, int | None]:
    """`(Leitzahl, ihr Zeitraum in Monaten)` - EINE Messung, EINE Rechnung.

    Der Zeitraum wird GELESEN (`Tco.leitzahl_monate`), nie angenommen:
    aufgeteilt 24 Monate, 1&1 (ein Bündelbetrag) seine Ratenlaufzeit. Ein
    fremder Zeitraum sperrt die Kurve nicht (P0-B-z1); das Tor wirkt an
    Rangfolge und Vorzeichen (`_band_zeilen`, `_bewegung`).
    `(None, None)`: keine belastbare Zahl (Clean Code 3/5).
    """
    b = _buendel_aus_messung(messung, tarife)
    if b is None:
        return None, None
    t = tco_24(b)
    if not t.belastbar:
        return None, None
    return t.gesamt, t.leitzahl_monate


def _wert_aus_messung(messung: dict, tarife: dict | None = None) -> float | None:
    """Die HEUTIGE Leitzahl einer Messung (A1), nicht das eingefrorene
    `gesamt` der Historie; `None` heisst nur "nicht belastbar gemessen"."""
    return _messwert(messung, tarife)[0]


def _rechung(messung: dict, tarife: dict | None = None) -> dict | None:
    """Die Postenliste EINER Messung aus der Historien-Zeile.

    Gerechnet wird nur in `tco_24` (A1: alle Raten, Tarif phasengewichtet);
    hier wird ZERLEGT, der `betrag` je Posten kommt aus `Tco.bestandteile`
    (Schluessel EXAKT wie dort, sonst fehlt ein Posten und die Summe geht
    nicht auf). Zwei Preisformen: aufgeteilt (Tarif und Rate) und zusammen
    (1&1, ein Bündelbetrag); Boni stehen nicht in der Historie. `monate`
    ist der Zeitraum der Leitzahl (`Tco.leitzahl_monate`) fuer ihr Etikett.
    """
    satz = messung["satz"]
    b = _buendel_aus_messung(messung, tarife)
    if b is None:
        return None
    t = tco_24(b)
    if t.gesamt is None:
        return None
    lz = b.laufzeit_monate

    posten: list[dict] = []

    def _posten(label: str, betrag, anzahl=None, einzeln=None, klammer=""):
        if betrag is None:
            return
        posten.append(
            {
                "label": label,
                "anzahl": anzahl,
                "einzeln": einzeln,
                "betrag": betrag,
                "klammer": klammer,
            }
        )

    _posten(POSTEN_ZUZAHLUNG, t.bestandteile.get(POSTEN_ZUZAHLUNG))
    _posten(POSTEN_ANSCHLUSS, t.bestandteile.get(POSTEN_ANSCHLUSS))
    if b.buendel_monatlich is not None:
        _posten(
            POSTEN_BUENDEL,
            t.bestandteile.get(f"{POSTEN_BUENDEL} über {lz} Monate"),
            anzahl=lz,
            einzeln=b.buendel_monatlich,
        )
    else:
        _posten(
            "Tarif",
            t.bestandteile.get(f"Tarif über {TCO_HORIZONT} Monate"),
            anzahl=TCO_HORIZONT,
            einzeln=b.tarif_monatlich,
            klammer="phasengewichtet" if b.tarif_phasen else "",
        )
        _posten(
            POSTEN_RATE,
            t.bestandteile.get(f"Geräteraten über {lz} Monate"),
            anzahl=lz,
            einzeln=b.geraet_monatsrate,
        )

    summe = round(sum(p["betrag"] for p in posten), 2)
    if summe != t.gesamt:
        log.warning(
            "Rechenweg: Posten von %s am %s ergeben %s, gerechnet "
            "ist %s - die Zerlegung weicht von ihrer Rechnung ab.",
            satz.get("id"),
            satz.get("datum"),
            summe,
            t.gesamt,
        )
    offen = None
    monatlich = (
        b.geraet_monatsrate if b.buendel_monatlich is None else b.buendel_monatlich
    )
    if lz > TCO_HORIZONT and monatlich is not None:
        offen = {
            "anzahl": lz - TCO_HORIZONT,
            "einzeln": monatlich,
            "betrag": round((lz - TCO_HORIZONT) * monatlich, 2),
        }
    return {
        "posten": posten,
        "gesamt": t.gesamt,
        "monate": t.leitzahl_monate,
        "offen": offen,
        "datum": satz.get("datum") or "",
        "quelle_url": satz.get("quelle_url") or "",
        "abgerufen_am": satz.get("abgerufen_am") or "",
        "weitere_laufzeiten": messung.get("weitere_laufzeiten") or [],
    }


def _rechung_html(anbieter: str, messung: dict, tarife: dict | None = None) -> str:
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

    `tarife` reicht der Tarifbestand durch dieselbe wie die Punkte: auch
    das Panel rechnet die HEUTIGE Leitzahl, phasengewichtet wo der Stamm
    Phasen nennt (A1).
    """
    r = _rechung(messung, tarife)
    if r is None or not r["posten"]:
        return ""
    a = _esc(anbieter)
    punkt = (
        f"<i class='gr-zr-rpunkt' style='background:"
        f"{_zr_marker_farbe(anbieter)}' aria-hidden='true'>"
        f"</i>"
    )
    teile = [
        "<div class='gr-zr-rech'>",
        f"<p class='gr-zr-rkopf'>{punkt}<strong>{a}</strong> · Messung "
        f"vom {_esc(_datum_de(r['datum']))}</p>",
        "<ul class='gr-zr-posten'>",
    ]
    for p in r["posten"]:
        if p["anzahl"] is not None and p["einzeln"] is not None:
            ausdruck = (
                f"{p['anzahl']} × {_euro(p['einzeln'])} "
                f"<span class='gr-zr-pg'>= {_euro(p['betrag'])}"
                f"</span>"
            )
        else:
            ausdruck = _euro(p["betrag"])
        klammer = (
            f" <span class='gr-zr-pk'>{_esc(p['klammer'])}</span>"
            if p["klammer"]
            else ""
        )
        anteil = f"{p['betrag'] / r['gesamt'] * 100:.1f}%" if r["gesamt"] else "0%"
        teile.append(
            f"<li class='gr-zr-posten'>"
            f"<span class='gr-zr-pn'>{_esc(p['label'])}</span>"
            f"<span class='gr-zr-pbar'><i style='width:{anteil}"
            f"'></i></span>"
            f"<span class='gr-zr-pr'>{ausdruck}{klammer}</span>"
            f"</li>"
        )
    teile.append("</ul>")
    teile.append(
        f"<p class='gr-zr-rsumme'>= <b>{_euro(r['gesamt'])}</b> "
        f"<span class='gr-zr-plabel'>{label_der_leitzahl(r['monate'])}</span></p>"
    )
    if r["offen"] is not None:
        teile.append(
            f"<p class='gr-zr-roffen'>davon nach Monat "
            f"{TCO_HORIZONT} noch zu zahlen: "
            f"{r['offen']['anzahl']} × {_euro(r['offen']['einzeln'])}"
            f" = {_euro(r['offen']['betrag'])}</p>"
        )
    if r["weitere_laufzeiten"]:
        teile.append(
            f"<p class='gr-zr-rweitere'>Zum selben Betrag auch "
            f"über {_zeitraum_wort(r['weitere_laufzeiten'])} "
            f"erhältlich – dabei bleibt nach Monat {TCO_HORIZONT} "
            f"eine Restschuld offen.</p>"
        )
    url = r["quelle_url"]
    link = (
        f"<a href='{_esc(url)}' target='_blank' rel='noopener'>{a}&nbsp;↗</a>"
        if url
        else a
    )
    datum_teil = (
        f", abgerufen {_esc(_datum_kurz(r['abgerufen_am']))}"
        if r["abgerufen_am"]
        else ""
    )
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
    return (
        f"<div class='gr-zr-rech gr-zr-rech--leer' data-anb='{EIGEN}' "
        f"data-m='naeherung'><p class='gr-zr-rkopf'><strong>{EIGEN}"
        f"</strong> · Referenzrechnung</p>"
        f"<p class='gr-zr-rleer'>{_esc(_NAEHERUNG_SATZ)}"
        f"{_esc(_NAEHERUNG_KEIN_WEG)}</p></div>"
    )


def _rechenwege_html(
    messungen_paar: dict, zeilen: list, tarife: dict | None = None
) -> str:
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
            inhalt = _rechung_html(anbieter, saetze[datum], tarife)
            if inhalt:
                bloecke.append(
                    f"<template data-anb='{_esc(anbieter)}' "
                    f"data-m='{_esc(datum)}'>{inhalt}</template>"
                )
    if any(z.get("naeherung") for z in zeilen):
        bloecke.append(
            f"<template data-anb='{EIGEN}' data-m='naeherung'>"
            f"{_naeherung_html()}</template>"
        )
    if not bloecke:
        return ""
    return "<div class='gr-zr-rechnungen' hidden>" + "".join(bloecke) + "</div>"


def buendel_schluessel(satz: dict) -> str | None:
    """Der Schluessel, unter dem Stand und Historie einander finden.

    DIE EINE STELLE dafuer (Clean Code 1/7). Zuerst die Lesemigration B1
    (`tco_store.id_aus_satz`, vier Segmente -> fuenf); eine unbekannte
    ID-Form ist ein OPAKER Schluessel und bleibt unveraendert (P0-B-fix2),
    sonst fiele das Buendel aus Stand und Historie. `None` heisst: der
    Satz traegt ueberhaupt keine ID.
    """
    migriert = id_aus_satz(satz)
    if migriert is not None:
        return migriert
    roh = str(satz.get("id") or "").strip() if isinstance(satz, dict) else ""
    return roh or None


def _messungen(
    state_dir: Path, tco: dict, tarife: dict | None = None, heute: str = ""
) -> dict:
    """{(modell, band): {anbieter: {datum: MESSUNG}}} aus der Historie.

    Eine MESSUNG ist das dict `{"satz": <Historien-Zeile>, "stand":
    <Buendel-Eintrag aus geraete_tco.json>, "wert": <Leitzahl von HEUTE>}`
    samt der Notbremse ihres Bündels (`felder_aus_satz` am Stand, `zaehlt`).
    Je (Modell, Band, Anbieter, Tag) zaehlt das GUENSTIGSTE Buendel (Farben
    sind Preisdimensionen) - seit A1 nach der HEUTIGEN Rechnung (`wert`,
    nicht dem eingefrorenen `gesamt` der Historie). Ein fehlender Tag
    bleibt fehlend.

    P1 (17.09.2026): die Zeile wird GANZ behalten, nicht nur ihr `gesamt` -
    aus ihren Messfeldern baut `_rechung` die Postenliste. Bei gleichem
    `wert` gewinnt die ZEILE, die zuerst gelesen wurde (strikt `<`),
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
    buendel_basis: dict[str, dict] = {}
    stand_ohne_id = 0
    if tco_datei.exists():
        try:
            roh = json.loads(tco_datei.read_text(encoding="utf-8"))
            for b in roh.get("buendel") or []:
                bid = buendel_schluessel(b)
                if bid is None:
                    stand_ohne_id += 1
                    continue
                buendel[bid] = b
                basis = basis_aus_satz(b)
                if basis:
                    buendel_basis.setdefault(basis, b)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("geraete_tco.json unlesbar fuer die Zeitreihe: %s", exc)

    messungen: dict[tuple, dict] = {}
    historie = state_dir / "geraete_tco_historie.jsonl"
    if not historie.exists():
        return {}
    ohne_id = ohne_stand = ueber_basis = ohne_wert = 0
    fremder_zeitraum = 0
    for zeile in historie.read_text(encoding="utf-8").splitlines():
        if not zeile.strip():
            continue
        try:
            satz = json.loads(zeile)
        except json.JSONDecodeError:
            continue
        hid = buendel_schluessel(satz)
        if hid is None:
            ohne_id += 1
            continue
        b = buendel.get(hid)
        if b is None:
            basis = basis_aus_satz(satz)
            b = buendel_basis.get(basis) if basis else None
            if b is None:
                ohne_stand += 1
                continue
            ueber_basis += 1
        modell = sku_modell.get(b.get("sku_id"))
        if modell is None:
            continue
        band = band_je_tarif.get(satz.get("tarif_id") or b.get("tarif_id") or "")
        if not band:
            continue
        datum, gesamt = satz.get("datum"), satz.get("gesamt")
        if not datum or gesamt is None:
            continue
        wert, monate = _messwert({"satz": satz, "stand": b}, tarife)
        if wert is None:
            ohne_wert += 1
            continue
        if not zeitraum_vergleichbar(monate, TCO_HORIZONT):
            fremder_zeitraum += 1
        slot = messungen.setdefault((modell, band), {}).setdefault(
            b.get("anbieter") or "?", {}
        )
        alt = slot.get(datum)
        laufzeit = satz.get("laufzeit_monate")

        def _gleichstand(kandidat):
            return (
                kandidat is not None
                and kandidat["wert"] == wert
                and zeitraum_vergleichbar(monate, kandidat["monate"])
                and laufzeit != kandidat.get("laufzeit")
            )

        if alt is None:
            besser = True
        elif zeitraum_vergleichbar(monate, alt["monate"]):
            if wert < alt["wert"]:
                besser = True
            elif _gleichstand(alt):
                besser = laufzeit is not None and (
                    alt.get("laufzeit") is None or laufzeit < alt["laufzeit"]
                )
            else:
                besser = False
        else:
            besser = zeitraum_vergleichbar(monate, TCO_HORIZONT)
        if besser:
            weitere = (
                set(alt.get("weitere_laufzeiten") or []) if _gleichstand(alt) else set()
            )
            if _gleichstand(alt) and alt.get("laufzeit") is not None:
                weitere.add(alt["laufzeit"])
            slot[datum] = {
                "satz": satz,
                "stand": b,
                "wert": wert,
                "monate": monate,
                "laufzeit": laufzeit,
                "weitere_laufzeiten": sorted(weitere),
                **notbremse.felder_aus_satz(b, heute),
            }
        elif _gleichstand(alt) and laufzeit is not None:
            bekannt = set(alt.get("weitere_laufzeiten") or [])
            bekannt.add(laufzeit)
            alt["weitere_laufzeiten"] = sorted(bekannt)
    if (
        ohne_id
        or ohne_stand
        or ueber_basis
        or ohne_wert
        or stand_ohne_id
        or fremder_zeitraum
    ):
        log.info(
            "Zeitreihe: %d Historienzeile(n) ohne jede ID, %d ohne "
            "Buendel im heutigen Stand, %d ueber den laufzeitfreien "
            "Schluessel zugeordnet, %d ohne belastbare Leitzahl "
            "(kein Punkt), %d Punkt(e) mit Leitzahl ueber einen "
            "anderen Zeitraum als %d Monate (Kurve MIT Zeitraum am "
            "Ende); %d Stand-Eintrag/Eintraege ohne ID.",
            ohne_id,
            ohne_stand,
            ueber_basis,
            ohne_wert,
            fremder_zeitraum,
            TCO_HORIZONT,
            stand_ohne_id,
        )
    return messungen


def _serien_aus(messungen: dict, tarife: dict | None = None) -> dict:
    """{(modell, band): {anbieter: [[iso, wert], ...]}} - die Punktliste.

    Die reine Ableitung aus `_messungen`: je Datum die HEUTIGE Leitzahl
    (`wert`; wird sie nicht mitgegeben, rechnet diese Funktion selbst -
    derselbe Weg ueber `_wert_aus_messung`, keine zweite Formel). Beide
    Formen entstehen aus EINER Lesung der Historie - zwei Lesungen waeren
    zwei Zeitreihen, sollte die Datei zwischen ihnen wachsen.
    """
    fertig: dict[tuple, dict] = {}
    for schluessel, anbieter_ in messungen.items():
        punkte = {}
        for an, werte in anbieter_.items():
            reihe = []
            for d, m in sorted(werte.items()):
                wert = m.get("wert")
                if wert is None:
                    wert = _wert_aus_messung(m, tarife)
                if wert is not None:
                    reihe.append((d, wert))
            punkte[an] = sorted(reihe)
        fertig[schluessel] = punkte
    return fertig


def _zeitraeume_aus(messungen: dict, tarife: dict | None = None) -> dict:
    """{(modell, band): {anbieter: [Monate, ...]}} - DER ZEITRAUM JE KURVE.

    P0-B-z1: der Zeitraum der Punkte, aus DERSELBEN Lesung der Historie
    wie die Punkte selbst (`_messungen` legt ihn je Messung ab, gelesen
    aus `Tco.leitzahl_monate`). Keine zweite Ableitung, keine
    Nachrechnung: `_svg` schreibt ihn ans Kurvenende, `_bewegung` prueft
    an ihm, ob ein Vorzeichen ueberhaupt eine Aussage ist.

    Je Anbieter die VERSCHIEDENEN Zeitraeume seiner Reihe, aufsteigend -
    in der Regel genau einer. Zwei heissen: der Anbieter hat die
    Ratenlaufzeit zwischen zwei Messtagen gewechselt, und dann ist die
    Stufe in der Kurve keine Preisaenderung (`_bewegung` schweigt dazu).
    Eine Messung ohne lesbaren Zeitraum steht nicht in der Liste; sie
    wird nie als Horizont ANGENOMMEN (Clean Code 4).
    """
    fertig: dict[tuple, dict] = {}
    for schluessel, anbieter_ in messungen.items():
        je_anbieter: dict[str, list[int]] = {}
        for an, werte in anbieter_.items():
            monate = set()
            for m in werte.values():
                wert, mon = (
                    (m.get("wert"), m.get("monate"))
                    if m.get("monate") is not None
                    else _messwert(m, tarife)
                )
                if wert is not None and mon is not None:
                    monate.add(mon)
            je_anbieter[an] = sorted(monate)
        fertig[schluessel] = je_anbieter
    return fertig


def _serien(state_dir: Path, tco: dict, tarife: dict | None = None) -> dict:
    """Die Serien in der Form, die der Graph liest (siehe `_serien_aus`)."""
    return _serien_aus(_messungen(state_dir, tco, tarife), tarife)


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
    stufe = 1 if n <= 1 else 2 if n <= 2 else 2.5 if n <= 2.5 else 5 if n <= 5 else 10
    return stufe * potenz


_NICE_VIELFACH = (1, 2, 2.5, 5, 10)


def _y_schritt(y0: float, y1: float) -> float:
    """Der Y-Achsen-Schritt mit 4-5 RUNDEN Werten.

    `_nice_step((y1-y0)/4)` allein kann kollabieren: bei y0=752/y1=1248
    (Spanne 496) rundet Spanne/4=124 auf die naechste Stufe 200 - und von
    752 bis 1248 passen dann nur DREI Vielfache von 200 (800/1000/1200),
    nicht vier bis fuenf. Diese Funktion sucht stattdessen unter allen
    runden Schritten mehrerer Dekaden denjenigen, dessen TICKZAHL wirklich
    in [4, 5] faellt (bei Gleichstand der naechste an 5 dran) - nur wenn
    keiner der runden Schritte das trifft (seltene Randspannen), faellt
    sie auf die Zahl zurueck, die der Tickzahl 4,5 am naechsten kommt."""
    spanne = y1 - y0
    if spanne <= 0:
        return max(abs(y1), 1.0)
    basis = spanne / 4
    basis_potenz = 10 ** math.floor(math.log10(basis))
    kandidaten = sorted(
        {
            round(m * basis_potenz * (10**dek), 8)
            for dek in range(-3, 4)
            for m in _NICE_VIELFACH
            if m * basis_potenz * (10**dek) > 0
        }
    )
    beste_rang, bester_schritt = None, None
    for schritt in kandidaten:
        erster = math.ceil(y0 / schritt) * schritt
        n, wert = 0, erster
        while wert <= y1 + 0.01 and n < 60:
            n += 1
            wert += schritt
        if n < 2:
            continue
        rang = (0 if 4 <= n <= 5 else 1, abs(n - 4.5))
        if beste_rang is None or rang < beste_rang:
            beste_rang, bester_schritt = rang, schritt
    return bester_schritt if bester_schritt else _nice_step(spanne / 4)


def _xtick_x(
    iso: str, t0: date, t1: date, links: float, breite: float, tage: list[str]
) -> float:
    if t1 == t0:
        return links + breite / 2
    tag = date.fromisoformat(iso)
    return links + (tag - t0).days / max(1, (t1 - t0).days) * breite


def _x_marken(
    tage: list[str], x_v, mindestabstand: float = MIN_XTICK_ABSTAND
) -> set[str]:
    """Welche Messtage eine X-Achsen-BESCHRIFTUNG bekommen (`MIN_XTICK_ABSTAND`).

    Gierig von links: der erste Tag ist immer dabei, jeder weitere nur,
    wenn er `mindestabstand` Einheiten vom zuletzt beschrifteten Tag
    entfernt liegt; der letzte Tag ersetzt noetigenfalls den zuletzt
    gewaehlten, statt zusaetzlich zu kollidieren - eine Achse ohne
    Enddatum sagt nicht, bis wann sie reicht. Die RASTERLINIE bekommt
    trotzdem JEDER Messtag (siehe `_svg`) - nur die Textmarke wird
    ausgeduennt."""
    if len(tage) <= 1:
        return set(tage)
    behalten = [tage[0]]
    letzte_x = x_v(tage[0])
    for tag in tage[1:-1]:
        x = x_v(tag)
        if x - letzte_x >= mindestabstand:
            behalten.append(tag)
            letzte_x = x
    letzter = tage[-1]
    if x_v(letzter) - letzte_x < mindestabstand and len(behalten) > 1:
        behalten[-1] = letzter
    else:
        behalten.append(letzter)
    return set(behalten)


def _stufenpfad(punkte: list[tuple[float, float, float]]) -> str:
    """Der Pfad einer STUFENLINIE (»step-after«) durch die gegebenen
    (x, y, wert)-Punkte: waagerecht zum naechsten X, dann senkrecht zu
    seinem Y. Ein Preis gilt vom Messtag an - er GLEITET nicht zum
    naechsten, er SPRINGT dort, genau am naechsten Messtag."""
    if not punkte:
        return ""
    teile = [f"M{punkte[0][0]:.1f} {punkte[0][1]:.1f}"]
    for i in range(1, len(punkte)):
        y0 = punkte[i - 1][1]
        x1, y1, _wert = punkte[i]
        teile.append(f"L{x1:.1f} {y0:.1f}")
        if y1 != y0:
            teile.append(f"L{x1:.1f} {y1:.1f}")
    return " ".join(teile)


def _linien_laeufe(
    punkte: list[tuple[float, float, float]],
    tage: list[str],
    schwelle_tage: int = LUECKE_TAGE_SCHWELLE,
) -> list[tuple[list[tuple[float, float, float]], bool]]:
    """Zerlegt eine Punktreihe in (Teilstrecke, ist_luecke)-Laeufe.

    `tage` sind die ECHTEN Messtage (isoformat) parallel zu `punkte` -
    Grundlage der Tagesdifferenz. Ueberschreitet der Abstand zweier
    aufeinanderfolgender Punkte `schwelle_tage`, ist die Verbindung
    ZWISCHEN ihnen eine eigene, gepunktete Zweipunkt-Teilstrecke
    (`ist_luecke=True`); alle anderen aufeinanderfolgenden Punkte ohne
    grosse Luecke bilden EINE durchgezogene Teilstrecke. So bleibt jeder
    Lauf entweder ganz durchgezogen oder (bei genau zwei Punkten) ganz
    gepunktet - nie beides im selben `<path>`, dessen `stroke-dasharray`
    nur EIN Muster kennt."""
    if len(punkte) < 2:
        return [(punkte, False)] if punkte else []
    laeufe: list[tuple[list[tuple[float, float, float]], bool]] = []
    lauf: list[tuple[float, float, float]] = [punkte[0]]
    for i in range(1, len(punkte)):
        tag_davor = date.fromisoformat(tage[i - 1])
        tag = date.fromisoformat(tage[i])
        if (tag - tag_davor).days > schwelle_tage:
            if len(lauf) > 1:
                laeufe.append((lauf, False))
            laeufe.append(([punkte[i - 1], punkte[i]], True))
            lauf = [punkte[i]]
        else:
            lauf.append(punkte[i])
    if len(lauf) > 1:
        laeufe.append((lauf, False))
    return laeufe


def _form_pfad(marker: str, x: float, y: float, r: float) -> str | None:
    """Die Zusatzform eines Markers - ODER `None` fuer den Kreis (der
    Punkt TRAEGT die Form schon: `<circle class='gr-zr-punkt'>`) und fuer
    unbekannte Formen. Gezeichnet als OFFENER Umriss (fill='none') UM den
    bestehenden Kreis - keine Kreis-Selektoren aus Tests und `app.js`
    aendern sich damit (D1 hatte das deshalb offen gelassen); die Form
    ist eine reine Zusatzauskunft fuer Farbfehlsicht und Schwarzweiss."""
    if marker in ("kreis", "") or marker not in (
        "quadrat",
        "dreieck",
        "dreieck--runter",
        "raute",
        "sechseck",
        "ring",
        "kreuz",
    ):
        return None
    if marker == "quadrat":
        s = r * 0.86
        return (
            f"<rect x='{x - s:.1f}' y='{y - s:.1f}' width='{2 * s:.1f}' "
            f"height='{2 * s:.1f}'/>"
        )
    if marker == "raute":
        s = r * 1.15
        pkte = (
            f"{x:.1f},{y - s:.1f} {x + s:.1f},{y:.1f} "
            f"{x:.1f},{y + s:.1f} {x - s:.1f},{y:.1f}"
        )
        return f"<polygon points='{pkte}'/>"
    if marker in ("dreieck", "dreieck--runter"):
        s = r * 1.2
        if marker == "dreieck":
            pkte = (
                f"{x:.1f},{y - s:.1f} {x + s:.1f},{y + s * 0.85:.1f} "
                f"{x - s:.1f},{y + s * 0.85:.1f}"
            )
        else:
            pkte = (
                f"{x:.1f},{y + s:.1f} {x + s:.1f},{y - s * 0.85:.1f} "
                f"{x - s:.1f},{y - s * 0.85:.1f}"
            )
        return f"<polygon points='{pkte}'/>"
    if marker == "sechseck":
        pkte = " ".join(
            f"{x + r * 1.1 * math.cos(math.radians(60 * i - 30)):.1f},"
            f"{y + r * 1.1 * math.sin(math.radians(60 * i - 30)):.1f}"
            for i in range(6)
        )
        return f"<polygon points='{pkte}'/>"
    if marker == "ring":
        return f"<circle cx='{x:.1f}' cy='{y:.1f}' r='{r * 1.4:.1f}'/>"
    if marker == "kreuz":
        s = r * 1.15
        return (
            f"<path d='M{x - s:.1f} {y:.1f}L{x + s:.1f} {y:.1f} "
            f"M{x:.1f} {y - s:.1f}L{x:.1f} {y + s:.1f}'/>"
        )
    return None


def _svg(
    anbieter_serien: dict,
    breit: bool,
    beleg_je: dict[str, tuple[str, str]],
    zeitraeume: dict | None = None,
) -> str:
    """DER EINE Graph - SVG-Koordinatensystem, fertig gerendert.

    Y = Kosten in € („runde" Ticks), X = das Datum in echter Distanz mit
    einem Tick je ECHTEM Messtag. Je Anbieter eine Linie mit einem Punkt
    je Messung (unter zwei Punkten: kein Linienzug), Wert am letzten Punkt
    gross und am ersten klein (nur breit), Vodafone rot mit „unser
    Angebot", Beleg-Link mit Abrufdatum am Linienende.

    `zeitraeume` (P0-B-z1) ist `{anbieter: [Monate, ...]}` aus
    `_zeitraeume_aus` - der Zeitraum, den die Punkte DIESER Kurve tragen.
    Er steht AN DER KURVE (bei mehreren Zeitraeumen im Bild, sonst sagt
    ihn der Titel fuer alle), und die Beschriftung behauptet nie einen
    Zeitraum, der nicht fuer alle Kurven gilt. Ohne Angabe (`None`)
    nennt das Bild GAR KEINEN Zeitraum - lieber keine Angabe als eine
    angenommene (Clean Code 3/4).
    """
    anbieter = [a for a in ANBIETER_FOLGE if anbieter_serien.get(a)]
    if not anbieter:
        return ""
    zeitraeume = zeitraeume or {}
    mon_je = {a: [m for m in (zeitraeume.get(a) or [])] for a in anbieter}
    alle_monate = sorted({m for ms in mon_je.values() for m in ms})
    mehrere_zeitraeume = len(alle_monate) > 1
    tage = _messtage(anbieter_serien)
    w = BREIT_W if breit else SCHMAL_W
    min_h = BREIT_MIN_H if breit else SCHMAL_MIN_H
    h = max(min_h, round(w * 0.42))
    links, rechts, oben, unten = (
        58,
        (158 if breit else 96),
        (KOPF_FREIRAUM_BREIT if breit else KOPF_FREIRAUM_SCHMAL),
        46,
    )
    pw, ph = w - links - rechts, h - oben - unten

    def x_v(iso: str) -> float:
        return _xtick_x(
            iso,
            date.fromisoformat(tage[0]),
            date.fromisoformat(tage[-1]),
            links,
            pw,
            tage,
        )

    werte = [p for serie in anbieter_serien.values() for _d, p in serie]
    ymin, ymax = min(werte), max(werte)
    spanne = (ymax - ymin) or max(ymax * 0.05, 1.0)
    y0 = max(0.0, ymin - spanne * MASSSTAB_FREIRAUM_ANTEIL)
    y1 = ymax + spanne * MASSSTAB_FREIRAUM_ANTEIL

    def y_v(wert: float) -> float:
        return oben + (1 - (wert - y0) / (y1 - y0)) * ph

    teile: list[str] = []
    wort = _zeitraum_wort(alle_monate)
    kopf = f"Kosten über {wort}" if wort else "Kosten"
    teile.append(
        f"<svg class='gr-zr gr-zr--{'breit' if breit else 'schmal'}' "
        f"viewBox='0 0 {w} {h}' role='img' aria-label='{_esc(kopf)} "
        f"je Messtag und Anbieter: {_esc(', '.join(anbieter))}'>"
    )
    schritt = _y_schritt(y0, y1)
    wert = math.ceil(y0 / schritt) * schritt
    while wert <= y1 + 0.01:
        y = y_v(wert)
        teile.append(
            f"<line class='gr-zr-raster' x1='{links}' y1="
            f"'{y:.1f}' x2='{w - rechts}' y2='{y:.1f}'/>"
            f"<text class='gr-zr-achse' x='{links - 8}' "
            f"y='{y + 4:.1f}' text-anchor='end'>"
            f"{_euro0(round(wert))}</text>"
        )
        wert += schritt
    if y0 > 0 and ymax > 0 and (ymax - ymin) < ACHSENBRUCH_ANTEIL * ymax:
        by = oben + ph - 9
        teile.append(
            f"<g class='gr-zr-achsenbruch' transform='translate({links},"
            f"{by:.1f})' aria-hidden='true'>"
            f"<rect x='-9' y='-9' width='18' height='18'/>"
            f"<path d='M-5 8 L-1 -4 L2 5 L6 -8'/></g>"
        )
    for tag in tage:
        x = x_v(tag)
        teile.append(
            f"<line class='gr-zr-raster' x1='{x:.1f}' y1='{oben}' "
            f"x2='{x:.1f}' y2='{oben + ph}'/>"
        )
    beschriftet = _x_marken(tage, x_v)
    for tag in tage:
        if tag not in beschriftet:
            continue
        x = x_v(tag)
        teile.append(
            f"<text class='gr-zr-xtick' x='{x:.1f}' "
            f"y='{h - unten + 22}' text-anchor='end'>"
            f"{_tag_monat(tag)}</text>"
        )

    def _punkte(serie):
        return [(x_v(d), y_v(p), p) for d, p in serie]

    for a in anbieter:
        punkte = _punkte(anbieter_serien[a])
        serie = anbieter_serien[a]
        stil = stil_fuer(a)
        farbe, marker_farbe = stil.farbe, stil.marker_farbe
        if len(punkte) > 1:
            tage_a = [d for d, _p in serie]
            for lauf, ist_luecke in _linien_laeufe(punkte, tage_a):
                pfad = _stufenpfad(lauf)
                if ist_luecke:
                    luecken_muster = STRICHMUSTER["gepunktet"]
                    muster = f" stroke-dasharray='{luecken_muster}'"
                    klasse = "gr-zr-linie gr-zr-linie--luecke"
                else:
                    muster = (
                        f" stroke-dasharray='{stil.muster}'"
                        if stil.muster != "none"
                        else ""
                    )
                    klasse = "gr-zr-linie"
                teile.append(
                    f"<path class='{klasse}' d='{pfad}' stroke='{farbe}'{muster}/>"
                )
        for i, (d, wert) in enumerate(serie):
            x, y = x_v(d), y_v(wert)
            ende = i == len(serie) - 1
            einzeln = len(serie) == 1
            r = 6 if ende else 4.5
            daten = f" data-anb='{_esc(a)}' data-m='{_esc(d)}'"
            if einzeln:
                teile.append(
                    f"<circle class='gr-zr-halo' cx='{x:.1f}' "
                    f"cy='{y:.1f}' r='9.5' fill='none' "
                    f"stroke='{marker_farbe}'/>"
                )
            teile.append(
                f"<circle class='gr-zr-punkt"
                f"{' gr-zr-ende' if ende else ''}' cx='{x:.1f}' "
                f"cy='{y:.1f}' r='{r}' fill='{marker_farbe}'"
                f"{daten}/>"
            )
            form = _form_pfad(stil.marker, x, y, r)
            if form:
                teile.append(
                    f"<g class='gr-zr-form gr-zr-form--{stil.marker}' "
                    f"fill='none' stroke='{marker_farbe}' "
                    f"stroke-width='1.4'>{form}</g>"
                )
            einmal = " · erstmals gemessen" if einzeln else ""
            teile.append(
                f"<circle class='gr-zr-hit' cx='{x:.1f}' "
                f"cy='{y:.1f}' r='{TREFFERFLAECHE_RADIUS}' fill='transparent'"
                f"{daten}><title>{_esc(a)} · {_tag_monat(d)} · "
                f"{_euro0(wert)}{einmal}</title>"
                f"</circle>"
            )

    abstand = 15 if not breit else 13

    def _label(kandidaten: list, klasse: str, dx: float, anker: str):
        kandidaten.sort(key=lambda k: k[1])
        belegt: list[float] = []
        for i, (x, y, text) in enumerate(kandidaten):
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
            teile.append(
                f"<text class='{klasse}' x='{x + dx:.1f}' "
                f"y='{ziel:.1f}' text-anchor='{anker}'>"
                f"{_euro0(text)}</text>"
            )

    if breit:
        letzte = [_punkte(anbieter_serien[a])[-1] for a in anbieter]
        _label(letzte, "gr-zr-wert", -10, "end")

    enden = sorted(
        (
            (_punkte(anbieter_serien[a])[-1][0], _punkte(anbieter_serien[a])[-1][1], a)
            for a in anbieter
        ),
        key=lambda e: e[1],
    )
    letzte_y = -99.0
    for x, y, a in enden:
        bedarf = 44 if not breit else 46
        mon_text = _mon_kurz(mon_je.get(a) or []) if mehrere_zeitraeume else ""
        if mon_text:
            bedarf += 13
        ty = max(y, letzte_y + bedarf)
        letzte_y = ty
        farbe = _zr_farbe(a)
        url, datum = beleg_je.get(a, ("", ""))
        lx = w - ENDLABEL_RAND
        name_html = f"{_esc(a)}<tspan class='gr-zr-pfeil'> ↗</tspan>"
        if url:
            teile.append(
                f"<a class='gr-zr-link' href='{_esc(url)}' "
                f"target='_blank' rel='noopener' aria-label='Beleg bei "
                f"{_esc(a)} öffnen'><text class='gr-zr-name' "
                f"x='{lx:.1f}' y='{ty + 4:.1f}' text-anchor='end' "
                f"fill='{farbe}'>{name_html}</text></a>"
            )
        else:
            teile.append(
                f"<text class='gr-zr-name' x='{lx:.1f}' "
                f"y='{ty + 4:.1f}' text-anchor='end' "
                f"fill='{farbe}'>{_esc(a)}</text>"
            )
        mon = 13 if mon_text else 0
        if mon_text:
            teile.append(
                f"<text class='gr-zr-datum gr-zr-mon' "
                f"x='{lx:.1f}' y='{ty + 17:.1f}' "
                f"text-anchor='end'>{_esc(mon_text)}</text>"
            )
        if datum:
            teile.append(
                f"<text class='gr-zr-datum' x='{lx:.1f}' "
                f"y='{ty + 17 + mon:.1f}' "
                f"text-anchor='end'>{_datum_kurz(datum)}</text>"
            )
    teile.append("</svg>")
    return "".join(teile)


def _anbieter_punkte(anbieter: list) -> str:
    """P1/F3 (A3): die Punkte-Reihe der Modell-Karte - je Anbieter der
    Zeitreihe EIN Punkt in seiner Hausfarbe (`anbieter_farben.py`,
    dieselbe Markerfarbe wie seine Punkte im Graphen). Die Punkte SIND
    die Anbieterzahl der Karte; ein zusaetzlicher Text \"N Anbieter\"
    waere dieselbe Zahl ein zweites Mal am selben Ort (Beruhigungsregel)."""
    return "".join(
        f"<i style='background:{_zr_marker_farbe(a)}' title='{_esc(a)}'></i>"
        for a in anbieter
    )


def _bewegung(serien: dict, zeitraeume: dict | None = None) -> dict | None:
    """A2 (20.09.2026): das Bewegungs-Delta der Karte - die EIGENE Reihe
    des fuehrenden Anbieters zwischen erstem und letztem Messtag.

    Bewegung ist anzeigepflichtig nur JE ANBIETER. Die bis A2 gerechnete
    PREIS-FRONT (Minimum ueber alle Anbieter je Messtag) stellte am
    letzten Messtag das Angebot des einen gegen das eines ANDEREN am
    ersten: am iPhone 17 Pro, Band Klein, meldete die Karte "+387 EUR in
    6 Tagen", ohne dass ein Anbieter seinen Preis geaendert hatte
    (congstar am 12.9., 1&1 am 18.9.). Fuehrend ist, wer am LETZTEN
    Messtag den kleinsten Wert hat - Gleichstand bricht die
    ANBIETER_FOLGE, dann der Name (deterministisch, kein Wuerfeln je
    Rendern). Fehlt dem Fuehrenden eine Messung am ERSTEN Messtag, gibt
    es keine Bewegung: die Differenz zweier Angebote ist keine
    Preisaenderung. Unter zwei Messtagen ebenso - das Feld ist None und
    die Karte zeigt keins.

    P0-B-z1: `zeitraeume` (`_zeitraeume_aus`) ist DAS TOR dieses Moduls.
    Die Kurve eines fremden Zeitraums bleibt im Bild; Rangfolge und
    Vorzeichen gehen nie ueber zwei Zeitraeume (siehe unten). Ohne
    Angabe steht kein Zeitraum zur Debatte - `aufbereiten` gibt sie
    IMMER mit, und nur mitgegebene Zeitraeume koennen sich
    widersprechen."""
    tage = _messtage(serien)
    if len(tage) < 2:
        return None
    spanne = (date.fromisoformat(tage[-1]) - date.fromisoformat(tage[0])).days
    if spanne < 1:
        return None

    def _wert(anbieter: str, tag: str) -> float:
        return min(w for d, w in serien[anbieter] if d == tag)

    letzte, erste = tage[-1], tage[0]
    kandidaten = [
        a for a, punkte in serien.items() if any(d == letzte for d, _ in punkte)
    ]
    zeitraeume = zeitraeume or {}
    monate_je = {a: (zeitraeume.get(a) or []) for a in kandidaten}
    if len({m for ms in monate_je.values() for m in ms}) > 1:
        kandidaten = [
            a
            for a in kandidaten
            if any(zeitraum_vergleichbar(m, TCO_HORIZONT) for m in monate_je[a])
        ]
    if not kandidaten:
        return None
    fuehrend = min(
        kandidaten,
        key=lambda a: (
            _wert(a, letzte),
            ANBIETER_FOLGE.index(a) if a in ANBIETER_FOLGE else len(ANBIETER_FOLGE),
            a,
        ),
    )
    if not any(d == erste for d, _ in serien[fuehrend]):
        return None
    if len(monate_je.get(fuehrend) or []) > 1:
        return None
    delta = round(_wert(fuehrend, letzte) - _wert(fuehrend, erste), 2)
    zeit = f"in {spanne} Tag" if spanne == 1 else f"in {spanne} Tagen"
    if delta > 0:
        return {"text": f"↑ +{_euro0(delta)} {zeit}", "richtung": "steigt"}
    if delta < 0:
        return {"text": f"↓ −{_euro0(-delta)} {zeit}", "richtung": "sinkt"}
    return {"text": f"±0 € {zeit}", "richtung": "gleich"}


def _legende_html(anbieter_serien: dict, zeitraeume: dict | None = None) -> str:
    """EINE Zeile ueber dem Graphen: Name mit Farb-Punkt, Vodafone rot und
    benannt. Der „ab"-Wert (erster Messbetrag) steht im eigenen Span, der
    auf dem breiten Bild ausgeblendet ist - dort traegt ihn das kleine
    Erst-Label im SVG, und eine Zahl steht je Ort genau EINMAL.

    P0-B-z1: kommen im Bild mehrere Zeitraeume vor, traegt jeder Eintrag
    seinen - „ab 2.019,54 € · zuletzt 2.019,54 €" ohne Zeitraum liest
    sich sonst als 24-Monats-Betrag. Gelesen wird derselbe Wert wie am
    Kurvenende (`_zeitraeume_aus`), nicht nachgerechnet."""
    zeitraeume = zeitraeume or {}
    vorhanden = sorted(
        {
            m
            for a, ms in zeitraeume.items()
            if anbieter_serien.get(a)
            for m in (ms or [])
        }
    )
    eintraege = []
    for anbieter in ANBIETER_FOLGE:
        serie = anbieter_serien.get(anbieter)
        if not serie:
            continue
        zusatz = (
            f" <span class='gr-zr-leg-wert'>ab {_euro0(serie[0][1])}"
            f" · zuletzt {_euro0(serie[-1][1])}</span>"
        )
        mon_text = (
            _mon_kurz(zeitraeume.get(anbieter) or []) if len(vorhanden) > 1 else ""
        )
        if mon_text:
            zusatz += (
                f" <span class='gr-zr-leg-ab gr-zr-leg-mon'>· {_esc(mon_text)}</span>"
            )
        eintraege.append(
            f"<span><i style='background:{_zr_marker_farbe(anbieter)}'></i>"
            f"{_esc(anbieter)}{zusatz}</span>"
        )
    if not eintraege:
        return ""
    return "<div class='gr-zr-legende'>" + "".join(eintraege) + "</div>"


def aufbereiten(
    state_dir: Path, tco: dict, tarife: dict | None = None, heute: str = ""
) -> dict:
    """Alles, was die Hauptansicht braucht.

    `tco` ist die Rueckgabe von `geraete_tco_view.aufbereiten()` - dieselben
    Modell-Karten (inklusive Band und Beleg), die die Buendel-Zeilen der
    Seite tragen. Dieses Modul liest ZUSAETZZLICH die rohe Historie
    (`geraete_tco_historie.jsonl`) und die Buendel-Liste
    (`geraete_tco.json`) - reine Lesearbeit, kein Schreibzugriff.

    `tarife` (A1, 20.09.2026) ist der Tarifbestand (`Tarifbestand.
    je_id_aktuell`, B3 21.09.2026 - nicht `je_id`, sonst rechnet die
    Historie mit einer stillgelegten Lesart): die Punkte der Historie
    werden mit der HEUTIGEN Leitzahl gerechnet, und deren Tarifanteil ist
    phasengewichtet, wo der Stamm Phasen nennt - dieselben Phasen wie auf
    der Tafel (`phasen_fuer_buendel`, ohne Widerspruch zur Messung).
    `heute` stellt die Uhr der Notbremse; Kachel-Delta, Startpaar und
    Kachelfolge (`wahl`) zählen nur Messungen, deren Bündel zählt.
    """
    state_dir = Path(state_dir)
    modelle = tco.get("modelle") or []
    band_katalog = {b["key"]: b for b in tco.get("baender_katalog") or []}
    messungen_alle = _messungen(state_dir, tco, tarife, heute)
    serien_alle = _serien_aus(messungen_alle, tarife)
    zaehlend_alle = _serien_aus(notbremse.nur_zaehlende(messungen_alle), tarife)
    zeitraeume_alle = _zeitraeume_aus(messungen_alle, tarife)
    if messungen_alle:
        log.info(
            "Zeitreihe: %d Messungen gelesen.",
            sum(
                len(saetze)
                for pa_ in messungen_alle.values()
                for saetze in pa_.values()
            ),
        )

    messtage_je_modell: dict[str, set] = {}
    for (mid, _band), anbieter_serien in serien_alle.items():
        messtage_je_modell.setdefault(mid, set()).update(_messtage(anbieter_serien))
    wahl = [
        m
        for m in modelle
        if not m.get("auto")
        or len(messtage_je_modell.get(m["id"], ())) >= AUTO_SICHTBAR_AB_MESTAGEN
    ]
    wahl_ids = {m["id"] for m in wahl}
    verdeckt = sorted(
        m.get("titel") or m["id"] for m in modelle if m["id"] not in wahl_ids
    )
    if verdeckt:
        log.info(
            "Zeitreihe: %d Auto-Modell(e) unter %d Messtagen - noch nicht waehlbar: %s",
            len(verdeckt),
            AUTO_SICHTBAR_AB_MESTAGEN,
            ", ".join(verdeckt),
        )

    paare: list[dict] = []
    erlaubt: dict[str, list[str]] = {}
    karten_baender: dict[str, dict[str, dict]] = {}
    for modell in wahl:
        zeilen_je_band = _band_zeilen(modell)
        bands = [
            b
            for b, s in zeilen_je_band.items()
            if s["zeilen"] or s.get("alt") or s.get("fremd") or s.get("gesperrt")
        ]
        erlaubt[modell["id"]] = bands
        for band in bands:
            satz = zeilen_je_band[band]
            zeilen = satz["zeilen"]
            alte = satz.get("alt") or []
            fremde = satz.get("fremd") or []
            serien = serien_alle.get((modell["id"], band), {})
            zaehlend = zaehlend_alle.get((modell["id"], band), {})
            zeitraeume = zeitraeume_alle.get((modell["id"], band), {})
            punkte = sum(len(v) for v in serien.values())
            eintrag = {
                "ab": None,
                "ab_monat": None,
                "anb": None,
                "delta_text": None,
                "delta_richtung": None,
                "punkte_html": "",
                "anbieter_text": "",
                "alt_text": None,
                "fremd_text": None,
                "gesperrt_text": None,
            }
            echt = next(
                (
                    z
                    for z in zeilen
                    if not z.get("naeherung") and z.get("gesamt") is not None
                ),
                None,
            )
            if echt is not None:
                eintrag["ab"] = _euro(echt["gesamt"])
                eintrag["ab_monat"] = _schnitt(echt)
                eintrag["anb"] = echt["anbieter"]
            elif alte:
                alt_seit = max(
                    (
                        k.get("abgerufen_am") or ""
                        for k in alte
                        if kurz_datum(k.get("abgerufen_am") or "")
                    ),
                    default="",
                )
                eintrag["alt_text"] = (
                    f"kein aktueller Stand seit {kurz_datum(alt_seit)}"
                    if alt_seit
                    else "kein aktueller Stand"
                )
            elif fremde:
                monate_fremd = fremde[0].get("leitzahl_monate")
                eintrag["fremd_text"] = (
                    f"nur über {monate_fremd} Monate"
                    if monate_fremd is not None
                    else "nur über eine andere Laufzeit"
                )
            elif satz.get("gesperrt"):
                gruende = notbremse.gruende(satz["gesperrt"])
                eintrag["gesperrt_text"] = f"nicht im Vergleich ({gruende})"
            if serien:
                band_anbieter = [a for a in ANBIETER_FOLGE if serien.get(a)]
                eintrag["punkte_html"] = _anbieter_punkte(band_anbieter)
                eintrag["anbieter_text"] = ", ".join(band_anbieter)
                bew = _bewegung(zaehlend, zeitraeume)
                if bew:
                    eintrag["delta_text"] = bew["text"]
                    eintrag["delta_richtung"] = bew["richtung"]
            karten_baender.setdefault(modell["id"], {})[band] = eintrag
            mess = messungen_alle.get((modell["id"], band), {})
            luecken = _luecken(
                zeilen,
                modell.get("karten") or [],
                band,
                fremd=fremde,
                gesperrt=satz.get("gesperrt"),
            )
            beleg_je = {
                z["anbieter"]: (z.get("quelle_url") or "", z.get("abgerufen_am") or "")
                for z in zeilen
            }
            leer = None
            if not serien:
                seit = tco.get("historie_lage") or {}
                seit_text = (
                    f"seit dem {_datum_de(seit['seit'])}" if seit.get("seit") else ""
                )
                leer = (
                    f"Für {_satz_name(modell)} im Band "
                    f"{band_katalog.get(band, {}).get('label', band)} "
                    f"liegt noch keine Messreihe vor - die Zeitreihe "
                    f"beginnt {seit_text} und wächst mit jedem "
                    f"Messtag. Der Stand heute steht in den Bündel-"
                    f"Zeilen darunter."
                )
            paare.append(
                {
                    "modell": modell["id"],
                    "band": band,
                    "antwort_html": _antwort_html(
                        modell,
                        band,
                        zeilen,
                        band_katalog.get(band, {}),
                        alte=satz.get("alt"),
                        fremd=fremde,
                        gesperrt=satz.get("gesperrt"),
                    ),
                    "leitzahl_html": _leitzahl_html(zeilen),
                    "rechnung_html": _rechnung_html(zeilen),
                    "legende_html": _legende_html(serien, zeitraeume),
                    "graph_beschriftung": (
                        f"Kosten über {wort} je Messtag und Anbieter"
                        if (
                            wort := _zeitraum_wort(
                                sorted(
                                    {
                                        m
                                        for liste in zeitraeume.values()
                                        for m in (liste or [])
                                    }
                                )
                            )
                        )
                        else "Kosten je Messtag und Anbieter"
                    ),
                    "svg_breit": _svg(serien, True, beleg_je, zeitraeume),
                    "svg_schmal": _svg(serien, False, beleg_je, zeitraeume),
                    "rechenweg_html": _rechenwege_html(mess, zeilen, tarife),
                    "luecke_text": _luecke_text(luecken, band_katalog),
                    "leer_text": leer,
                    "anbieter": [a for a in ANBIETER_FOLGE if serien.get(a)],
                    "punkte": punkte,
                    "wahl": (len(zaehlend), sum(map(len, zaehlend.values()))),
                }
            )

    vorlagen = sum(p["rechenweg_html"].count("<template") for p in paare)
    if vorlagen:
        log.info(
            "Zeitreihe: %d Rechenweg-Vorlagen (je Messung) gebaut, "
            "%d Punkte in den Serien.",
            vorlagen,
            sum(p["punkte"] for p in paare),
        )
    kandidaten = [(p["modell"], p["band"], *p["wahl"]) for p in paare]
    start = None
    if kandidaten:
        rang = {b: i for i, b in enumerate(band_katalog)}
        kandidaten.sort(
            key=lambda k: (-k[2], -k[3], k[0], rang.get(k[1], len(rang)), k[1])
        )
        start = {"modell": kandidaten[0][0], "band": kandidaten[0][1]}
    start_block = next(
        (
            p
            for p in paare
            if start and p["modell"] == start["modell"] and p["band"] == start["band"]
        ),
        None,
    )

    index_modelle = []
    for modell in modelle:
        bands = erlaubt.get(modell["id"]) or []
        if not bands:
            continue
        echte = [k for k in modell.get("karten") or [] if k.get("sku_id")]
        index_modelle.append(
            {
                "id": modell["id"],
                "titel": modell.get("titel") or modell["id"],
                "hersteller": modell.get("hersteller") or "",
                "speicher": modell.get("speicher"),
                "anbieter_zahl": len({k["anbieter"] for k in echte}),
                "band_zahl": len(bands),
            }
        )
    index_modelle.sort(key=lambda m: (-m["band_zahl"], -m["anbieter_zahl"], m["titel"]))
    suchindex = index_modelle

    kachel_werte: dict[str, tuple] = {}
    for p in paare:
        wert = p["wahl"]
        bisher = kachel_werte.get(p["modell"])
        if bisher is None or wert > bisher:
            kachel_werte[p["modell"]] = wert
    titel_je = {m["id"]: m for m in modelle}
    kurze_namen = [_kurz_name(titel_je[mid]) for mid in kachel_werte]

    def _kachel_name(mid: str) -> str:
        kurz = _kurz_name(titel_je[mid])
        if kurze_namen.count(kurz) > 1:
            speicher = titel_je[mid].get("speicher")
            if speicher:
                return f"{kurz} · {speicher} GB"
        return kurz

    kacheln = []
    for mid in sorted(
        kachel_werte, key=lambda m: (-kachel_werte[m][0], -kachel_werte[m][1], m)
    )[:KACHELN_MAX]:
        if mid not in titel_je:
            continue
        kacheln.append(
            {
                "id": mid,
                "kurz": _kachel_name(mid),
                "titel": titel_je[mid].get("titel") or mid,
                "baender": {
                    b: karten_baender.get(mid, {}).get(b)
                    for b in band_katalog
                    if karten_baender.get(mid, {}).get(b)
                },
            }
        )

    daten = {
        "vorgabe": (start or {}).get("modell", ""),
        "start_band": (start or {}).get("band", ""),
        "band_folge": list(band_katalog),
        "modelle_gesamt": len(wahl),
        "suchindex": suchindex,
        "erlaubt": erlaubt,
        "titel": {m["id"]: m.get("titel") or m["id"] for m in modelle},
        "kurz": {m["id"]: _kurz_name(m) for m in modelle},
        "bnd_titel": {
            m["id"]: {
                band: f"Alle Bündel im Band "
                f"{band_katalog.get(band, {}).get('label', band)}"
                f" – {m.get('titel') or m['id']}"
                for band in erlaubt.get(m["id"]) or []
            }
            for m in modelle
        },
        "bnd_titel_ohne": {
            m["id"]: f"Alle Bündel – {m.get('titel') or m['id']}" for m in modelle
        },
    }

    bewegung_woche = geraete_bewegung.bewegungen(
        messungen_alle, erlaubt, daten["titel"], band_katalog, buendel_schluessel
    )

    return {
        "hat_daten": any(p["punkte"] for p in paare),
        "start": start,
        "start_block": start_block,
        "paare": paare,
        "kacheln": kacheln,
        "baender": band_katalog,
        "band_folge": list(band_katalog),
        "suchindex": suchindex,
        "daten": daten,
        "bewegung_woche": bewegung_woche,
    }


def leer() -> dict:
    """Der Zustand nach einer gescheiterten Aufbereitung.

    Kein "alles leer und gut": die Vorlage meldet den Ausfall sichtbar
    (hat_daten False, paare leer), die übrigen Reiter der Seite bleiben
    davon unberührt - dieselbe Trennung wie `geraete_tco_view.leer()`.
    """
    return {
        "hat_daten": False,
        "start": None,
        "start_block": None,
        "paare": [],
        "kacheln": [],
        "baender": {},
        "band_folge": [],
        "bewegung_woche": geraete_bewegung.ausfall(
            geraete_bewegung.AUSFALL_AUFBEREITUNG
        ),
        "suchindex": [],
        "daten": {
            "vorgabe": "",
            "start_band": "",
            "modelle_gesamt": 0,
            "suchindex": [],
            "erlaubt": {},
            "titel": {},
            "kurz": {},
            "bnd_titel": {},
            "bnd_titel_ohne": {},
        },
    }
