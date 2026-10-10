"""Rechenweg je Messung der Gerätezeitreihe: Kernzahl und Postenliste aus der Historie.

Aus `geraete_zeitreihe` ausgelagert (Datenkonzept Geräte, Schritt 2): die eine
Baustelle, an der eine Historien-Zeile zum Bündel wird (`_buendel_aus_messung`),
ihre Kernzahl über H Monate (`_messwert`, gerechnet nur in `tco_kosten.kosten_ueber`)
und die gesetzte Postenliste je Messung (`_rechung`, `_rechung_html`,
`_rechenwege_html`). Dazu die kleinen Schreibweisen, die Zeitreihe und Rechenweg
teilen (`_euro`, `_esc`, Datumsformen, `_zeitraum_wort`).
"""

from __future__ import annotations

import logging
from datetime import date

from .. import rechenweise
from ..tarif_model import buendelphasen_aus
from ..tco_kosten import tarifmonate
from ..tco_model import (
    POSTEN_ANSCHLUSS,
    POSTEN_BUENDEL,
    POSTEN_RATE,
    POSTEN_ZUZAHLUNG,
    Buendel,
    kosten_ueber,
)
from .anbieter_farben import stil_fuer
from .geraete_tco_karten import label_der_leitzahl, tarif_anreichern
from .verlauf import MONATE_DE

log = logging.getLogger(__name__)

ANBIETER_FOLGE = ("Telekom", "Vodafone", "o2", "1&1", "congstar")


EIGEN = "Vodafone"

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


def _zr_marker_farbe(anbieter: str) -> str:
    """Die PUNKTfarbe - bei congstar bewusst nicht die Linienfarbe (gelber
    Marker auf schwarzer Linie, sonst waere das Gelb auf hellem Papier die
    einzige Spur des Anbieters)."""
    return stil_fuer(anbieter).marker_farbe


def _euro(betrag) -> str:
    """1.234,56 € - dieselbe Schreibweise wie ueberall auf der Seite."""
    if betrag is None:
        return ""
    return f"{betrag:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".") + " €"


def _datum_kurz(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{d}.{m}.{y}"


def _datum_de(iso: str) -> str:
    """„1. Oktober 2026“ - Monatsname aus fester Liste, nie vom Locale."""
    tag = date.fromisoformat(iso)
    return f"{tag.day}. {MONATE_DE[tag.month - 1]} {tag.year}"


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


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
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
            tarif_phasen=buendelphasen_aus(satz.get("tarif_phasen")),
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
        tarif_anreichern(b, (tarife or {}).get(b.tarif_id) or {})
    return b


def _messwert(
    messung: dict, tarife: dict | None = None
) -> tuple[float | None, int | None]:
    """`(Kosten über H, H in Monaten)` - EINE Messung, EINE Rechnung.

    Gerechnet wird nur in `kosten_ueber` (Datenkonzept Geräte 5.3); H wird
    gelesen, nie angenommen: 12 und 24 Raten 24 Monate, 36 Raten 36, ein Vertrag
    (1&1) seine Laufzeit. Ein fremder Zeitraum sperrt die Kurve nicht (P0-B-z1);
    das Tor wirkt an Rangfolge und Vorzeichen (`_band_zeilen`, `_bewegung`).
    `(None, None)`: keine vollständige Zahl (Clean Code 3/5).
    """
    b = _buendel_aus_messung(messung, tarife)
    if b is None:
        return None, None
    kosten = kosten_ueber(b)
    if kosten.gesamt is None:
        return None, None
    return kosten.gesamt, kosten.monate


def _wert_aus_messung(messung: dict, tarife: dict | None = None) -> float | None:
    """Die HEUTIGE Leitzahl einer Messung (A1), nicht das eingefrorene
    `gesamt` der Historie; `None` heisst nur "nicht vollständig gemessen"."""
    return _messwert(messung, tarife)[0]


def _rechung(messung: dict, tarife: dict | None = None) -> dict | None:
    """Die Postenliste EINER Messung aus der Historien-Zeile.

    Gerechnet wird nur in `kosten_ueber`; hier wird ZERLEGT, der `betrag` je
    Posten kommt aus `Kosten.posten` (Schluessel EXAKT wie dort, sonst fehlt ein
    Posten und die Summe geht nicht auf). Zwei Preisformen: aufgeteilt (Tarif und
    Rate) und zusammen (1&1, ein Bündelbetrag); Boni stehen nicht in der Historie.
    `monate` ist der Zeitraum H der Zahl fuer ihr Etikett.
    """
    satz = messung["satz"]
    b = _buendel_aus_messung(messung, tarife)
    if b is None:
        return None
    kosten = kosten_ueber(b)
    if kosten.gesamt is None:
        return None
    lz, h = b.laufzeit_monate, kosten.monate

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

    _posten(POSTEN_ZUZAHLUNG, kosten.posten.get(POSTEN_ZUZAHLUNG))
    _posten(POSTEN_ANSCHLUSS, kosten.posten.get(POSTEN_ANSCHLUSS))
    if b.buendel_monatlich is not None:
        _posten(
            POSTEN_BUENDEL,
            kosten.posten.get(f"{POSTEN_BUENDEL} über {h} Monate"),
            anzahl=h,
            einzeln=b.buendel_monatlich,
        )
    else:
        t = min(h, tarifmonate(b))
        _posten(
            "Tarif",
            kosten.posten.get(f"Tarif über {t} Monate"),
            anzahl=t,
            einzeln=b.tarif_monatlich,
            klammer="phasengewichtet" if b.tarif_phasen else "",
        )
        _posten(
            POSTEN_RATE,
            kosten.posten.get(f"Geräteraten über {lz} Monate"),
            anzahl=lz,
            einzeln=b.geraet_monatsrate,
        )

    summe = round(sum(p["betrag"] for p in posten), 2)
    if summe != kosten.gesamt:
        log.warning(
            "Rechenweg: Posten von %s am %s ergeben %s, gerechnet "
            "ist %s - die Zerlegung weicht von ihrer Rechnung ab.",
            satz.get("id"),
            satz.get("datum"),
            summe,
            kosten.gesamt,
        )
    return {
        "posten": posten,
        "gesamt": kosten.gesamt,
        "monate": h,
        "datum": satz.get("datum") or "",
        "quelle_url": satz.get("quelle_url") or "",
        "abgerufen_am": satz.get("abgerufen_am") or "",
    }


def _rechung_html(anbieter: str, messung: dict, tarife: dict | None = None) -> str:
    """EINE Messung als fertiger Block - die gesetzte Rechung.

    Struktur (fuer das Klick-Panel, siehe schnittstelle-rechenweg.md):
    Kopf (Anbieter mit Farb-Punkt wie seine Linie im Graphen, Messtag),
    Postenliste (Label, `anzahl × einzeln = betrag`; einmalige Posten ohne
    Faktor; je Posten ein BALKEN in Breite seines Anteils an der Summe -
    P1-Fix Sicht-A2: „nicht nur Zeilen", die Breite ist eine fertige
    Prozentangabe aus dieser einen Rechnung, der Client setzt nichts),
    Summe mit dem Label der Leitzahl und den Beleg mit Abrufdatum DIESES
    Messtags (nicht von heute - das ist der Unterschied zum statischen
    „So gerechnet"-Satz).

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
        saetze = rechenweise.juengste(messungen_paar.get(anbieter) or {})
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
