"""E2 (AUFTRAG_GERAETE_EINE_SEITE_V2 §1a, 16.09.2026): die TCO-ZEITREIHE
der Geräteseite - Aufbereitung UND Grafik, beides serverseitig.

Antonios Wortlaut (§1a): „Ich will einen verfickten Graphen haben. Mit
verfickten Punkten und Koordinatensystem. […] Y-Achse ist Euro-Kosten.
Und X-Achse ist das DATUM. Ich möchte dann genau die verschiedenen
Messtage immer sehen." - und nach dem Ansehen des Prototyps: „Den Graphen
finde ich gut." Der Prototyp (Commit 2f40457) ist hier Production geworden.
Drei Regeln tragen dieses Modul:

1. **JEDE ZAHL ENTSTEHT HIER, KEINE IM CLIENT.** Der Browser setzt fertige
   Knoten ein (Antwort-Satz, Messtag-Zeile, beide SVG-Varianten, Lückensatz); er
   rechnet, formatiert und baut keine Zeichenketten. Vorlage und `app.js` sind
   Montage, kein Renderer - dieselbe Regel wie `luecke_text` in `geraete_tco_band`.
2. **Nichts wird interpoliert.** Ein Anbieter ohne Messung an einem Tag
   hat keinen Punkt an diesem Tag; unter zwei Punkten gibt es keinen
   Linienzug. Die Lücke IST die Aussage des Graphen.
3. **Der Startzustand kommt aus den Daten**: das Modell × Band der 24er-Ansicht
   mit den meisten Anbietern, bei Gleichstand den meisten Punkten.

Die Zuordnung der Historie ist die des Sammel-Skripts des Prototyps
(`historie_sammeln.py`, reine Lesearbeit auf data/state):
  buendel_id -> geraete_tco.json (sku_id, anbieter, tarif_id)
  sku_id     -> Modell       (geraete_view/geraete_tco_karten - dieselbe
                              Gruppierung wie die Karten der Seite)
  tarif_id   -> Band         (geraete_tco_band.tarif_baender - dieselbe
                              Logik wie der bisherige Band-Graph)
Je (Modell, Band, Anbieter, Tag) zählt das GÜNSTIGSTE Bündel: Farben sind
Preisdimensionen.

ZWEI SVG-Varianten je Paar (breit/schmal) statt clientseitigem Neu-Rendern bei
Resize: beide fertigen Bilder stehen im Dokument, ein CSS-Mediaquery zeigt genau
eines (`display:none` nimmt das andere aus dem Accessibility-Baum).
"""

from __future__ import annotations

import json
import logging
import math
from datetime import date
from pathlib import Path

from .. import rechenweise, tco_historie
from ..analyze.tco_store import basis_aus_satz, id_aus_satz
from ..band_regel import band_fuer
from ..tco_model import zeitraum_vergleichbar
from . import geraete_bewegung, geraete_sortiment
from . import geraete_notbremse as notbremse
from . import geraete_zeitreihe_auswahl as zeitreihe_auswahl
from . import geraete_zeitreihe_etiketten as etiketten
from . import geraete_zeitreihe_uebertrag as uebertrag
from .anbieter_farben import STRICHMUSTER, stil_fuer
from .geraete_antwort import _antwort_html as _antwort_html
from .geraete_antwort import _leitzahl_html as _leitzahl_html
from .geraete_antwort import _rechnung_html as _rechnung_html
from .geraete_antwort import _satz_name
from .geraete_laufzeit import ALLE_TEXT as ALLE_TEXT
from .geraete_laufzeit import LAUFZEIT_STANDARD, LAUFZEITEN, ansicht, zeitraum
from .geraete_luecken import _alternativen as _alternativen
from .geraete_luecken import _luecken as _luecken
from .geraete_luecken import fehlen_im_paar, haenge_an
from .geraete_rechenweg import _NAEHERUNG_SATZ as _NAEHERUNG_SATZ
from .geraete_rechenweg import ANBIETER_FOLGE as ANBIETER_FOLGE
from .geraete_rechenweg import (
    EIGEN,
    ZEITREIHE_FOLGE,
    _datum_de,
    _esc,
)
from .geraete_rechenweg import _buendel_aus_messung as _buendel_aus_messung
from .geraete_rechenweg import _messwert as _messwert
from .geraete_rechenweg import _rechenwege_html as _rechenwege_html
from .geraete_rechenweg import _rechung as _rechung
from .geraete_rechenweg import _rechung_html as _rechung_html
from .geraete_rechenweg import _wert_aus_messung as _wert_aus_messung
from .geraete_zeitraum_wort import raten_zusatz, zeitraum_wort
from .geraete_zeitreihe_geometrie import (
    LUECKE_TAGE_SCHWELLE as LUECKE_TAGE_SCHWELLE,
)
from .geraete_zeitreihe_geometrie import _linien_laeufe as _linien_laeufe
from .geraete_zeitreihe_geometrie import _stufenpfad as _stufenpfad
from .geraete_zeitreihe_geometrie import (
    _x_marken,
    _xtick_x,
    _y_schritt,
    form_pfad,
)
from .geraete_zeitreihe_legende import _euro0, ohne_alte, ueberholt_html
from .geraete_zeitreihe_legende import legende_html as _legende_html

log = logging.getLogger(__name__)


BREIT_W, BREIT_MIN_H = 1136, 420
SCHMAL_W, SCHMAL_MIN_H = 358, 380
KOPF_FREIRAUM_BREIT, KOPF_FREIRAUM_SCHMAL = 18, 10
MASSSTAB_FREIRAUM_ANTEIL, ACHSENBRUCH_ANTEIL = 0.12, 0.10
TREFFERFLAECHE_RADIUS = 12
AUTO_SICHTBAR_AB_MESTAGEN = 2


def _tag_monat(iso: str) -> str:
    """„12.9." - das X-Achsen-Format des Prototyps (echtes deutsches)."""
    y, m, d = iso.split("-")
    return f"{int(d)}.{int(m)}."


def band_zeilen(modell: dict, laufzeit: int = LAUFZEIT_STANDARD) -> dict:
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
    sind Preisdimensionen; zaehlende vor nicht zaehlenden, F3; ohne B-Ware, F1),
    seit A1 nach der HEUTIGEN Rechnung (`wert`). Ein fehlender Tag bleibt fehlend.

    P1 (17.09.2026): die Zeile wird GANZ behalten, nicht nur ihr `gesamt` -
    aus ihren Messfeldern baut `_rechung` die Postenliste. Bei gleichem
    `wert` gewinnt die ZEILE, die zuerst gelesen wurde (strikt `<`).
    """
    sku_modell: dict[str, str] = {}
    for modell in tco.get("modelle") or []:
        for karte in modell.get("karten") or []:
            if karte.get("sku_id") and karte.get("vergleichbar", True):
                sku_modell[karte["sku_id"]] = modell["id"]

    band_je_tarif = tco.get("band_je_tarif") or {}
    tco_datei = state_dir / "geraete_tco.json"
    buendel: dict[str, dict] = {}
    buendel_basis: dict[str, dict] = {}
    stand_ohne_id = 0
    if tco_datei.exists():
        try:
            roh = json.loads(tco_datei.read_text(encoding="utf-8"))
            for rb in geraete_sortiment.markiere(roh.get("buendel"), state_dir, heute):
                bid = buendel_schluessel(rb)
                if bid is None:
                    stand_ohne_id += 1
                    continue
                buendel[bid] = rb
                basis = basis_aus_satz(rb)
                if basis:
                    buendel_basis.setdefault(basis, rb)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("geraete_tco.json unlesbar fuer die Zeitreihe: %s", exc)

    messungen: dict[tuple, dict] = {}
    letzte_je_buendel: dict[tuple, dict[str, tuple[str, dict]]] = {}
    historie = state_dir / "geraete_tco_historie.jsonl"
    if not tco_historie.vorhanden(historie):
        return {}
    ohne_id = ohne_stand = ueber_basis = ohne_wert = 0
    fremder_zeitraum = fremde_laufzeit = 0
    for zeile in tco_historie.zeilen(historie):
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
        tid = satz.get("tarif_id") or b.get("tarif_id")
        band = band_fuer(band_je_tarif, tid, hid)
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
        if (laufzeit := ansicht({**b, **satz, "raten_laufzeit": laufzeit})) is None:
            fremde_laufzeit += 1
            continue
        h = zeitraum(laufzeit)
        if not zeitraum_vergleichbar(monate, h):
            fremder_zeitraum += 1
        anbieter = b.get("anbieter") or "?"
        slot = messungen.setdefault((modell, band, laufzeit), {}).setdefault(
            anbieter, {}
        )
        messung = {
            "satz": satz,
            "stand": b,
            "wert": wert,
            "monate": monate,
            "laufzeit": laufzeit,
            **notbremse.felder_aus_satz(b, heute),
        }
        if uebertrag.besser(messung, slot.get(datum), h):
            slot[datum] = messung
        uebertrag.merke(
            letzte_je_buendel, (modell, band, laufzeit, anbieter), hid, datum, messung
        )
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
    uebertrag.gilt_weiter(messungen, letzte_je_buendel, heute, uebertrag.gefuehrt(tco))
    zeitreihe_auswahl.ohne_widersprochenen_juengsten(messungen, buendel, sku_modell)
    return messungen


def _serien_aus(messungen: dict, tarife: dict | None = None) -> dict:
    """{(modell, band): {anbieter: [[iso, wert], ...]}} - die Punktliste.

    Die reine Ableitung aus `_messungen`: je Datum die HEUTIGE Leitzahl (`wert`; wird
    sie nicht mitgegeben, rechnet diese Funktion selbst - derselbe Weg ueber
    `_wert_aus_messung`, keine zweite Formel), je Anbieter nur in der juengsten
    Rechenweise (`rechenweise.juengste`): ein Bruch ist keine Stufe. Beide Formen
    entstehen aus EINER Lesung der Historie - zwei Lesungen waeren zwei Zeitreihen.
    """
    fertig: dict[tuple, dict] = {}
    for schluessel, anbieter_ in messungen.items():
        punkte = {}
        for an, werte in anbieter_.items():
            reihe = []
            for d, m in sorted(rechenweise.juengste(werte).items()):
                wert = m.get("wert")
                if wert is None:
                    wert = _wert_aus_messung(m, tarife)
                if wert is not None:
                    reihe.append((uebertrag.messtag(d, m), wert))
            punkte[an] = sorted(reihe)
        fertig[schluessel] = punkte
    return fertig


def _zeitraeume_aus(messungen: dict, tarife: dict | None = None) -> dict:
    """{(modell, band): {anbieter: [Monate, ...]}} - DER ZEITRAUM JE KURVE.

    P0-B-z1: der Zeitraum der Punkte, aus DERSELBEN Lesung der Historie wie die Punkte
    selbst (`_messungen` legt ihn je Messung ab, gelesen aus `Tco.leitzahl_monate`).
    Keine zweite Ableitung, keine Nachrechnung: `_svg` schreibt ihn ans Kurvenende,
    die Wochenbewegung prueft an ihm, ob ein Vorzeichen eine Aussage ist.

    Je Anbieter die VERSCHIEDENEN Zeitraeume seiner Reihe, aufsteigend -
    in der Regel genau einer. Zwei heissen: der Anbieter hat die
    Ratenlaufzeit zwischen zwei Messtagen gewechselt, und dann ist die
    Stufe in der Kurve keine Preisaenderung (die Wochenbewegung schweigt dazu).
    Eine Messung ohne lesbaren Zeitraum steht nicht in der Liste; sie
    wird nie als Horizont ANGENOMMEN (Clean Code 4).
    """
    fertig: dict[tuple, dict] = {}
    for schluessel, anbieter_ in messungen.items():
        je_anbieter: dict[str, list[int]] = {}
        for an, werte in anbieter_.items():
            monate = set()
            for m in rechenweise.juengste(werte).values():
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
    anbieter = [a for a in ZEITREIHE_FOLGE if anbieter_serien.get(a)]
    if not anbieter:
        return ""
    zeitraeume = zeitraeume or {}
    mon_je = {a: [m for m in (zeitraeume.get(a) or [])] for a in anbieter}
    alle_monate = sorted({m for ms in mon_je.values() for m in ms})
    mehrere_zeitraeume = len(alle_monate) > 1
    tage = _messtage(anbieter_serien)
    w = BREIT_W if breit else SCHMAL_W
    min_h = BREIT_MIN_H if breit else SCHMAL_MIN_H
    h = max(
        min_h,
        round(w * 0.42),
        etiketten.mindesthoehe(
            anbieter_serien, anbieter, breit, mon_je, mehrere_zeitraeume
        ),
    )
    links, rechts, oben, unten = (
        58,
        etiketten.rand_rechts(anbieter, breit),
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
    wort = zeitraum_wort(alle_monate)
    kopf = f"Kosten über {wort}" if wort else "Kosten"
    kopf += raten_zusatz(alle_monate, laufzeit, " · ")
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
    beschriftet = _x_marken(tage, x_v, breit)
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
            form = form_pfad(stil.marker, x, y, r) if (breit or ende) else None
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
                f"{daten}><title>{_esc(a)} · {_tag_monat(d)}"
                f"{uebertrag.gelesen_text(d, _tag_monat)} · "
                f"{_euro0(wert)}{einmal}</title></circle>"
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
    teile += etiketten.namensetiketten(
        enden, breit, w, h, beleg_je, mon_je, mehrere_zeitraeume
    )
    teile.append("</svg>")
    return "".join(teile)


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


ZEITFENSTER = {
    "7t": (7, 1),
    "30t": (30, 1),
    "90t": (90, 3),
    "1j": (365, 7),
    "alle": (None, None),
}
ZEITFENSTER_STANDARD = "30t"


def fenster_serien(serien: dict, fenster: str, heute: str = "") -> dict:
    """Wahre Messtage auf ein rollierendes Fenster begrenzen und ausduennen.

    Bei 90 Tagen: letzter Messwert jedes dritten Kalendertags,
    beim Jahr: letzter Messwert je Siebentagesabschnitt.
    Keine Interpolation oder Mittelwertbildung. Die letzte Messung je
    Zeitabschnitt bleibt mit ihrem ECHTEN Datum erhalten.

    Nur die Darstellung, nie die TCO-Rechnung: ein Abschnitt zeigt den LETZTEN
    gemessenen Tag, keinen Mittelwert. Bei ``alle`` gibt es etwa 52 echte Messtage.
    """
    if fenster not in ZEITFENSTER:
        raise ValueError(f"Unbekanntes Zeitfenster: {fenster}")
    tage = _messtage(serien)
    if not tage:
        return {}
    try:
        ende = date.fromisoformat(heute) if heute else date.fromisoformat(tage[-1])
    except ValueError:
        ende = date.fromisoformat(tage[-1])
    tage_anzahl, schritt = ZEITFENSTER[fenster]
    if tage_anzahl is None:
        start = date.fromisoformat(tage[0])
        schritt = max(1, math.ceil(((ende - start).days + 1) / 52))
    else:
        assert schritt is not None, "Fenster mit Tagesanzahl hat einen Schritt"
        start = date.fromordinal(ende.toordinal() - tage_anzahl + 1)
    ergebnis: dict = {}
    for anbieter, serie in serien.items():
        buckets: dict[int, tuple[str, float]] = {}
        for datum, wert in sorted(serie, key=lambda punkt: punkt[0]):
            try:
                tag = date.fromisoformat(datum)
            except ValueError:
                continue
            if not start <= tag <= ende:
                continue
            bucket = (tag - start).days // schritt
            buckets[bucket] = (datum, wert)
        if buckets:
            ergebnis[anbieter] = [buckets[k] for k in sorted(buckets)]
    return ergebnis


def _fenster_html(
    serien: dict, beleg_je: dict, zeitraeume: dict, laufzeit: int, ueberholt: str = ""
) -> str:
    """Fertige Grafik, die app.js unveraendert einhaengt."""
    if not _messtage(serien):
        return (
            "<p class='gr-zr-keine'>Für diesen Zeitraum liegen keine Messungen vor.</p>"
        )
    breit = _svg(serien, True, beleg_je, zeitraeume, laufzeit=laufzeit)
    schmal = _svg(serien, False, beleg_je, zeitraeume, laufzeit=laufzeit)
    legende = _legende_html(serien, zeitraeume, ueberholt)
    return (
        legende
        + '<div class="gr-zr-bild" id="gr-zr-bild" '
        + 'title="Ein fehlender Punkt bedeutet: keine Messung an diesem Tag. '
        + 'Lange Zeiträume zeigen ausgewählte echte Messtage, keine Mittelwerte.">'
        + breit
        + schmal
        + "</div>"
    )


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
    heute: str = "",
) -> dict:
    """Der vorgerenderte Block eines Paares (Modell, Band, Ratenlaufzeit)."""
    zeilen, fremde = satz["zeilen"], satz.get("fremd") or []
    h = zeitraum(laufzeit)
    band_info = band_katalog.get(band, {})
    beleg_je = {
        z["anbieter"]: (z.get("quelle_url") or "", z.get("abgerufen_am") or "")
        for z in zeilen
    }
    leer = None
    kopf = f"Für {_satz_name(modell)} im Band {band_info.get('label', band)}"
    seit = historie_lage.get("seit")
    if not serien:
        leer = notbremse.leersatz(mess, f"{kopf} mit {laufzeit} Raten") or (
            f"{kopf} mit {laufzeit} Raten liegt noch keine Messreihe vor - die "
            f"Zeitreihe beginnt {'seit dem ' + _datum_de(seit) if seit else ''} "
            "und wächst mit jedem Messtag. Der Stand heute steht in den Bündel-"
            "Zeilen darunter."
        )
    ueberholt = ueberholt_html(modell, mess, serien, satz)
    standard_serien = fenster_serien(serien, ZEITFENSTER_STANDARD, heute)
    weitere: list[dict] = []
    schon: dict[tuple, str] = {}
    for fenster in ("7t", "90t", "1j", "alle"):
        ausschnitt = fenster_serien(serien, fenster, heute)
        signatur = tuple(
            (anbieter, tuple(punkte)) for anbieter, punkte in sorted(ausschnitt.items())
        )
        alias = schon.get(signatur)
        if alias:
            weitere.append({"key": fenster, "alias": alias, "html": ""})
        else:
            schon[signatur] = fenster
            weitere.append(
                {
                    "key": fenster,
                    "alias": "",
                    "html": _fenster_html(
                        ausschnitt, beleg_je, zeitraeume, laufzeit, ueberholt
                    ),
                }
            )
    return {
        "modell": modell["id"],
        "band": band,
        "laufzeit": laufzeit,
        "fenster_html": (
            f"<p class='gr-zr-keine'>{_esc(leer)}</p>"
            if not serien and leer
            else _fenster_html(
                standard_serien, beleg_je, zeitraeume, laufzeit, ueberholt
            )
        ),
        "fenster_weitere": weitere,
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
        "legende_html": _legende_html(serien, zeitraeume, ueberholt),
        "graph_beschriftung": f"Kosten über {zeitraum_wort([h])}"
        f"{raten_zusatz([h], laufzeit, ' mit ')} je Messtag und Anbieter",
        "svg_breit": _svg(
            standard_serien, True, beleg_je, zeitraeume, laufzeit=laufzeit
        ),
        "svg_schmal": _svg(
            standard_serien, False, beleg_je, zeitraeume, laufzeit=laufzeit
        ),
        "rechenweg_html": _rechenwege_html(
            ohne_alte(modell, mess, serien), zeilen, tarife
        ),
        "fehlen": fehlen_im_paar(modell, satz, band, laufzeit, band_katalog, h),
        "leer_text": leer,
        "anbieter": [a for a in ZEITREIHE_FOLGE if serien.get(a)],
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
    `heute` stellt die Uhr der Notbremse; das Startpaar (`wahl`) zählt nur
    Messungen, deren Bündel zählt.
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
    for modell in wahl:
        je_laufzeit = {lz: band_zeilen(modell, lz) for lz in _REIHE}
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
            zaehlend = zaehlend_alle.get(schluessel, {})
            zeitraeume = zeitraeume_alle.get(schluessel, {})
            paare.append(
                _paar(
                    modell,
                    band,
                    lz,
                    satz,
                    band_katalog,
                    messungen_alle.get(schluessel, {}),
                    zaehlend,
                    zaehlend,
                    zeitraeume,
                    tarife,
                    tco.get("historie_lage") or {},
                    heute,
                )
            )

    haenge_an(modelle, paare)
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

    daten = {
        "vorgabe": (start or {}).get("modell", ""),
        "start_band": (start or {}).get("band", ""),
        "start_laufzeit": LAUFZEIT_STANDARD,
        "laufzeiten": list(LAUFZEITEN),
        "alle_text": ALLE_TEXT,
        "band_folge": list(band_katalog),
        "modelle_gesamt": len(wahl),
        "suchindex": suchindex,
        "erlaubt": erlaubt,
        "titel": {m["id"]: m.get("titel") or m["id"] for m in modelle},
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
            "alle_text": ALLE_TEXT,
            "modelle_gesamt": 0,
            "suchindex": [],
            "erlaubt": {},
            "titel": {},
            "bnd_titel": {},
            "bnd_titel_ohne": {},
        },
    }
