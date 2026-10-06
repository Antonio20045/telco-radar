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
from ..tco_model import TCO_HORIZONT, zeitraum_vergleichbar
from . import geraete_bewegung
from . import geraete_notbremse as notbremse
from .anbieter_farben import STRICHMUSTER, stil_fuer
from .geraete_antwort import _antwort_html as _antwort_html
from .geraete_antwort import _kurz_name, _satz_name, _schnitt
from .geraete_antwort import _leitzahl_html as _leitzahl_html
from .geraete_antwort import _rechnung_html as _rechnung_html
from .geraete_laufzeit import LAUFZEIT_STANDARD, LAUFZEITEN, ansicht, zeitraum
from .geraete_luecken import _alternativen as _alternativen
from .geraete_luecken import _luecke_text as _luecke_text
from .geraete_luecken import _luecken as _luecken
from .geraete_rechenweg import _NAEHERUNG_SATZ as _NAEHERUNG_SATZ
from .geraete_rechenweg import (
    ANBIETER_FOLGE,
    EIGEN,
    _datum_de,
    _datum_kurz,
    _esc,
    _euro,
    _zeitraum_wort,
    _zr_marker_farbe,
)
from .geraete_rechenweg import _buendel_aus_messung as _buendel_aus_messung
from .geraete_rechenweg import _messwert as _messwert
from .geraete_rechenweg import _rechenwege_html as _rechenwege_html
from .geraete_rechenweg import _rechung as _rechung
from .geraete_rechenweg import _rechung_html as _rechung_html
from .geraete_rechenweg import _wert_aus_messung as _wert_aus_messung
from .geraete_tco_karten import kurz_datum

log = logging.getLogger(__name__)


def _zr_farbe(anbieter: str) -> str:
    """Die Linienfarbe - fuer Pfad, Achsen-Name und `_anbieter_punkte`."""
    return stil_fuer(anbieter).farbe


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


def _euro0(betrag) -> str:
    if betrag is None:
        return ""
    return f"{betrag:,.0f}".replace(",", ".") + " €"


def _tag_monat(iso: str) -> str:
    """„12.9." - das X-Achsen-Format des Prototyps (echtes deutsches)."""
    y, m, d = iso.split("-")
    return f"{int(d)}.{int(m)}."


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


def _band_zeilen(modell: dict, laufzeit: int = LAUFZEIT_STANDARD) -> dict:
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
    stellt weder Zeile noch Sieger; sie steht benannt in `gesperrt`. Ein
    Bündel ohne vollständigen Preis (`kosten_ueber` nennt eine Lücke) steht in
    `unvollstaendig` - das Band bleibt wählbar und nennt die Lücke.

    Datenkonzept Geräte Schritt 2: je Ansicht `laufzeit` zählen nur Karten
    dieser Ratenlaufzeit (`geraete_laufzeit.ansicht`), ihr Zeitraum ist H =
    `zeitraum(laufzeit)`. 24 Raten stehen nie neben 36.
    """
    h = zeitraum(laufzeit)
    baender: dict[str, dict] = {}
    karten = modell.get("karten") or []
    for karte in karten:
        band = karte.get("band")
        if not band or ansicht(karte) != laufzeit:
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
            k for k in brauchbar if zeitraum_vergleichbar(k.get("leitzahl_monate"), h)
        ]
        fremd = [
            k
            for k in brauchbar
            if k.get("frisch", True)
            and not zeitraum_vergleichbar(k.get("leitzahl_monate"), h)
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
            "unvollstaendig": [
                k
                for k in satz["karten"]
                if k.get("vergleichbar") and k.get("sku_id") and not k.get("belastbar")
            ],
        }
    return fertig


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
    """{(modell, band, laufzeit): {anbieter: {datum: MESSUNG}}} aus der Historie.

    Datenkonzept Geräte Schritt 2: je Ratenlaufzeit eine eigene Reihe - 24
    Raten stehen nie gegen 36. Eine Laufzeit ausserhalb `LAUFZEITEN` hat
    keine Ansicht und wird gezaehlt, nicht gezeichnet.

    Eine MESSUNG ist das dict `{"satz": <Historien-Zeile>, "stand":
    <Buendel-Eintrag aus geraete_tco.json>, "wert": <Leitzahl von HEUTE>}`
    samt der Notbremse ihres Bündels (`felder_aus_satz` am Stand, `zaehlt`).
    Je (Modell, Band, Anbieter, Tag) zaehlt das GUENSTIGSTE Buendel (Farben
    sind Preisdimensionen) - seit A1 nach der HEUTIGEN Rechnung (`wert`,
    nicht dem eingefrorenen `gesamt` der Historie). Ein fehlender Tag
    bleibt fehlend.

    P1 (17.09.2026): die Zeile wird GANZ behalten, nicht nur ihr `gesamt` -
    aus ihren Messfeldern baut `_rechung` die Postenliste. Bei gleichem
    `wert` gewinnt die ZEILE, die zuerst gelesen wurde (strikt `<`).
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
    fremder_zeitraum = fremde_laufzeit = 0
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
        laufzeit = satz.get("laufzeit_monate")
        if laufzeit is None:
            laufzeit = b.get("laufzeit_monate")
        if laufzeit not in LAUFZEITEN:
            fremde_laufzeit += 1
            continue
        h = zeitraum(laufzeit)
        if not zeitraum_vergleichbar(monate, h):
            fremder_zeitraum += 1
        slot = messungen.setdefault((modell, band, laufzeit), {}).setdefault(
            b.get("anbieter") or "?", {}
        )
        alt = slot.get(datum)
        if alt is None:
            besser = True
        elif zeitraum_vergleichbar(monate, alt["monate"]):
            besser = wert < alt["wert"]
        else:
            besser = zeitraum_vergleichbar(monate, h)
        if besser:
            slot[datum] = {
                "satz": satz,
                "stand": b,
                "wert": wert,
                "monate": monate,
                "laufzeit": laufzeit,
                **notbremse.felder_aus_satz(b, heute),
            }
    if (
        ohne_id
        or ohne_stand
        or ueber_basis
        or ohne_wert
        or stand_ohne_id
        or fremder_zeitraum
        or fremde_laufzeit
    ):
        log.info(
            "Zeitreihe: %d Historienzeile(n) ohne jede ID, %d ohne "
            "Buendel im heutigen Stand, %d ueber den laufzeitfreien "
            "Schluessel zugeordnet, %d ohne belastbare Leitzahl "
            "(kein Punkt), %d Punkt(e) mit Leitzahl ueber einen "
            "anderen Zeitraum als ihre Ansicht (Kurve MIT Zeitraum am "
            "Ende), %d mit einer Ratenlaufzeit ausserhalb 12/24/36; "
            "%d Stand-Eintrag/Eintraege ohne ID.",
            ohne_id,
            ohne_stand,
            ueber_basis,
            ohne_wert,
            fremder_zeitraum,
            fremde_laufzeit,
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
    laufzeit: int | None = None,
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
    angenommene (Clean Code 3/4). `laufzeit` ist die Ratenlaufzeit der
    Ansicht; der Kopf des Bildes nennt sie neben dem Zeitraum.
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
    if laufzeit is not None:
        kopf += f" · {laufzeit} Raten"
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


_REIHE = tuple(sorted(LAUFZEITEN, key=lambda lz: lz != LAUFZEIT_STANDARD))
"""Die Laufzeiten in der Reihenfolge der Paare: die Standardansicht zuerst."""


def _ohne_satz() -> dict:
    """Ein Band ohne Karte dieser Laufzeit - die Ansicht nennt die Lücke."""
    return {
        "zeilen": [],
        "karten": [],
        "alt": [],
        "fremd": [],
        "gesperrt": [],
        "unvollstaendig": [],
    }


def _hat_inhalt(satz: dict) -> bool:
    """Trägt das Band in dieser Laufzeit irgendetwas, das die Seite nennt?"""
    return bool(
        satz["zeilen"]
        or satz.get("alt")
        or satz.get("fremd")
        or satz.get("gesperrt")
        or satz.get("unvollstaendig")
    )


def _kachel_eintrag(satz: dict, serien: dict, zaehlend: dict, zeitraeume: dict) -> dict:
    """Die Kachelzeile eines Bandes in EINER Ratenlaufzeit."""
    zeilen, alte, fremde = satz["zeilen"], satz.get("alt") or [], satz.get("fremd")
    eintrag: dict = {
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
        (z for z in zeilen if not z.get("naeherung") and z.get("gesamt") is not None),
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
    return eintrag


def _paar(
    modell: dict,
    band: str,
    laufzeit: int,
    satz: dict,
    band_katalog: dict,
    mess: dict,
    serien: dict,
    zaehlend: dict,
    zeitraeume: dict,
    tarife: dict | None,
    historie_lage: dict,
) -> dict:
    """Der vorgerenderte Block eines Paares (Modell, Band, Ratenlaufzeit)."""
    zeilen, fremde = satz["zeilen"], satz.get("fremd") or []
    h = zeitraum(laufzeit)
    band_info = band_katalog.get(band, {})
    luecken = _luecken(
        zeilen,
        modell.get("karten") or [],
        band,
        fremd=fremde,
        gesperrt=satz.get("gesperrt"),
        laufzeit=laufzeit,
    )
    beleg_je = {
        z["anbieter"]: (z.get("quelle_url") or "", z.get("abgerufen_am") or "")
        for z in zeilen
    }
    leer = None
    if not serien:
        seit_text = (
            f"seit dem {_datum_de(historie_lage['seit'])}"
            if historie_lage.get("seit")
            else ""
        )
        leer = (
            f"Für {_satz_name(modell)} im Band {band_info.get('label', band)} "
            f"mit {laufzeit} Raten liegt noch keine Messreihe vor - die "
            f"Zeitreihe beginnt {seit_text} und wächst mit jedem Messtag. Der "
            f"Stand heute steht in den Bündel-Zeilen darunter."
        )
    return {
        "modell": modell["id"],
        "band": band,
        "laufzeit": laufzeit,
        "antwort_html": _antwort_html(
            modell,
            band,
            zeilen,
            band_info,
            alte=satz.get("alt"),
            fremd=fremde,
            gesperrt=satz.get("gesperrt"),
            unvollstaendig=satz.get("unvollstaendig"),
            laufzeit=laufzeit,
        ),
        "leitzahl_html": _leitzahl_html(zeilen),
        "rechnung_html": _rechnung_html(zeilen, h),
        "legende_html": _legende_html(serien, zeitraeume),
        "graph_beschriftung": f"Kosten über {h} Monate mit {laufzeit} Raten "
        f"je Messtag und Anbieter",
        "svg_breit": _svg(serien, True, beleg_je, zeitraeume, laufzeit=laufzeit),
        "svg_schmal": _svg(serien, False, beleg_je, zeitraeume, laufzeit=laufzeit),
        "rechenweg_html": _rechenwege_html(mess, zeilen, tarife),
        "luecke_text": _luecke_text(luecken, band_katalog, h),
        "leer_text": leer,
        "anbieter": [a for a in ANBIETER_FOLGE if serien.get(a)],
        "punkte": sum(len(v) for v in serien.values()),
        "wahl": (len(zaehlend), sum(map(len, zaehlend.values()))),
    }


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
    for paar, anbieter_serien in serien_alle.items():
        messtage_je_modell.setdefault(paar[0], set()).update(_messtage(anbieter_serien))
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
        je_laufzeit = {lz: _band_zeilen(modell, lz) for lz in _REIHE}
        bands: list[str] = []
        for lz in _REIHE:
            bands += [
                b
                for b, s in je_laufzeit[lz].items()
                if _hat_inhalt(s) and b not in bands
            ]
        erlaubt[modell["id"]] = bands
        for band, lz in ((b, lz) for b in bands for lz in _REIHE):
            satz = je_laufzeit[lz].get(band) or _ohne_satz()
            schluessel = (modell["id"], band, lz)
            serien = serien_alle.get(schluessel, {})
            zaehlend = zaehlend_alle.get(schluessel, {})
            zeitraeume = zeitraeume_alle.get(schluessel, {})
            karten_baender.setdefault(modell["id"], {}).setdefault(band, {})[lz] = (
                _kachel_eintrag(satz, serien, zaehlend, zeitraeume)
            )
            paare.append(
                _paar(
                    modell,
                    band,
                    lz,
                    satz,
                    band_katalog,
                    messungen_alle.get(schluessel, {}),
                    serien,
                    zaehlend,
                    zeitraeume,
                    tarife,
                    tco.get("historie_lage") or {},
                )
            )

    vorlagen = sum(p["rechenweg_html"].count("<template") for p in paare)
    if vorlagen:
        log.info(
            "Zeitreihe: %d Rechenweg-Vorlagen (je Messung) gebaut, "
            "%d Punkte in den Serien.",
            vorlagen,
            sum(p["punkte"] for p in paare),
        )
    kandidaten = [
        (p["modell"], p["band"], *p["wahl"])
        for p in paare
        if p["laufzeit"] == LAUFZEIT_STANDARD
    ]
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
            if start
            and p["modell"] == start["modell"]
            and p["band"] == start["band"]
            and p["laufzeit"] == LAUFZEIT_STANDARD
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
        "start_laufzeit": LAUFZEIT_STANDARD,
        "laufzeiten": list(LAUFZEITEN),
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
            "start_laufzeit": LAUFZEIT_STANDARD,
            "laufzeiten": list(LAUFZEITEN),
            "modelle_gesamt": 0,
            "suchindex": [],
            "erlaubt": {},
            "titel": {},
            "kurz": {},
            "bnd_titel": {},
            "bnd_titel_ohne": {},
        },
    }
