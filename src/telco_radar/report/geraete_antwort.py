"""Antwortsatz, Leitzahl und Rechenschaftssatz eines Paar-Blocks der Zeitreihe.

Aus `geraete_zeitreihe` ausgelagert (Datenkonzept Geräte Schritt 2). Seit Teil B
gehört jeder Block zu einer Ratenlaufzeit: der Satz nennt sie („mit 36 Raten“)
und den Zeitraum H, über den seine Zahl läuft (`geraete_laufzeit.zeitraum`).
Gerechnet wird hier nichts - jede Zahl kommt fertig aus den Karten.
"""

from __future__ import annotations

from ..tco_model import TCO_HORIZONT
from . import geraete_notbremse as notbremse
from .geraete_laufzeit import NICHT_ERFASST, ansicht, zeitraum
from .geraete_rechenweg import EIGEN, _datum_de, _esc, _euro
from .geraete_tco_karten import kurz_datum


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


def _ohne_zeilen(
    beginn: str,
    alte: list | None,
    fremd: list | None,
    gesperrt: list | None,
    unvollstaendig: list | None,
    h: int,
) -> str | None:
    """Der Satz eines Blocks ohne Zeile - alt, fremder Zeitraum, gesperrt,
    unvollständig; `None`, wenn nichts davon zutrifft."""
    alte = alte or []
    alt_seit = max(
        (
            k.get("abgerufen_am") or ""
            for k in alte
            if kurz_datum(k.get("abgerufen_am") or "")
        ),
        default="",
    )
    if alte:
        stand = (
            f"die letzte Messung ist vom {kurz_datum(alt_seit)}"
            if alt_seit
            else "das Abrufdatum der letzten Bündel ist unbekannt"
        )
        return f"{beginn} liegt kein aktueller Stand vor – {stand}."
    if fremd:
        beste_fremd = fremd[0]
        monate = beste_fremd.get("leitzahl_monate")
        zeit = (
            f"{monate} Monate"
            if monate is not None
            else "eine nicht gemessene Laufzeit"
        )
        return (
            f"{beginn} führt nur {_esc(beste_fremd['anbieter'])} – und nur über "
            f"{zeit}: <b class='gr-zr-zahl'>{_euro(beste_fremd['gesamt'])}</b> "
            f"({_esc(beste_fremd.get('tarif') or '')}{_gb_teil(beste_fremd)}). "
            f"Über zwei Laufzeiten gibt es keinen Vergleich mit {h} Monaten."
        )
    if gesperrt:
        wer = _esc(", ".join(notbremse.namen(gesperrt)))
        return f"{beginn} steht kein Bündel im Vergleich: {wer}."
    if unvollstaendig:
        wer = _esc(", ".join(dict.fromkeys(k["anbieter"] for k in unvollstaendig)))
        return f"{beginn} hat kein Bündel einen vollständigen Preis: {wer}."
    return None


def _antwort_html(
    modell: dict,
    band: str,
    zeilen: list,
    band_katalog: dict,
    alte: list | None = None,
    fremd: list | None = None,
    gesperrt: list | None = None,
    unvollstaendig: list | None = None,
    laufzeit: int | None = None,
) -> str:
    """Der Antwort-Satz des Paar-Blocks.

    Seit P4/D4 (STRATEGIE_GERAETE_V3, 18.09.2026) traegt er das Delta zur
    Vodafone-Referenz NICHT mehr im Satz - es steht als EIGENE Leitzahl-Zeile
    ueber ihm (`_leitzahl_html`). Der Satz nennt Anbieter, Kosten über H und
    Ø je Monat; seit Datenkonzept Geräte Schritt 2 auch die Ratenlaufzeit der
    Ansicht (`laufzeit`, „mit 36 Raten“) - eine Zahl ohne ihre Laufzeit ist
    über 24 und 36 Raten nicht lesbar.

    A3: steht KEIN frisches Angebot da, aber ein altes, sagt der Satz den
    letzten Stand MIT DATUM (harte Regel 9). P0-B-h3: dieselbe Regel fuer
    einen fremden Zeitraum. Führt in dieser Laufzeit niemand ein Bündel,
    heißt es „nicht erfasst“ - der Sammler kennt kein „nicht angeboten“.
    """
    name = _esc(_satz_name(modell))
    label = band_katalog.get("label", band)
    bereich = band_katalog.get("bereich") or ""
    klammer = f" ({bereich})" if bereich else ""
    ort = f"im Band {label}{klammer}"
    if laufzeit is not None:
        ort += f" mit {laufzeit} Raten"
    h = zeitraum(laufzeit) if laufzeit is not None else TCO_HORIZONT
    beginn = f"Beim {name} {ort}"
    if not zeilen:
        satz = _ohne_zeilen(beginn, alte, fremd, gesperrt, unvollstaendig, h)
        if satz is not None:
            return satz
        if laufzeit is not None:
            return f"{beginn} ist kein Bündel erfasst."
        return f"{beginn} führt kein Anbieter ein Bündel."
    beste = zeilen[0]
    kern = (
        f"<b class='gr-zr-zahl'>{_euro(beste['gesamt'])}</b> Kosten über "
        f"{h} Monate, Ø <b class='gr-zr-zahl'>{_schnitt(beste)}</b> "
        f"({_esc(beste.get('tarif') or '')}{_gb_teil(beste)})"
    )
    if len(zeilen) == 1 and beste["anbieter"] == EIGEN:
        andere = [k for k in gesperrt or [] if k["anbieter"] != EIGEN]
        if andere:
            return (
                f"{beginn} steht nur Vodafone im Vergleich: {kern}. Nicht im "
                f"Vergleich: {_esc(', '.join(notbremse.namen(andere)))}."
            )
        return f"{beginn} führt nur Vodafone: {kern}."
    satz = f"{beginn} ist {_esc(beste['anbieter'])} am günstigsten: {kern}"
    eigen = next((z for z in zeilen if z["anbieter"] == EIGEN), None)
    if eigen is beste:
        zweit = zeilen[1] if len(zeilen) > 1 else None
        satz = f"{beginn} führt Vodafone: {kern}"
        if zweit is not None:
            satz += (
                f" Nächster Anbieter: {_esc(zweit['anbieter'])} "
                f"({_euro(zweit['gesamt'])})."
            )
    elif eigen is None and laufzeit is not None:
        satz += _vodafone_fehlt(modell, band, laufzeit)
    elif eigen is None:
        satz += " — Vodafone führt in diesem Band kein Bündel."
    return satz if satz.endswith(".") else satz + "."


def _vodafone_fehlt(modell: dict, band: str, laufzeit: int) -> str:
    """Der Zusatz, wenn Vodafone in dieser Ansicht keine Zahl stellt.

    „nicht erfasst“ nur, wenn Vodafone in dieser Laufzeit gar kein Bündel hat;
    hat es eines ohne vollständige, aktuelle Zahl, heißt es „ohne Zahl“ - den
    Grund nennt der Lückensatz unter dem Graphen.
    """
    eigene = [
        k
        for k in modell.get("karten") or []
        if k["anbieter"] == EIGEN
        and (k.get("sku_id") or k.get("naeherung"))
        and ansicht(k) == laufzeit
    ]
    if not eigene:
        return f" — Vodafone ist mit {laufzeit} Raten {NICHT_ERFASST}."
    if not any(k.get("band") == band for k in eigene):
        return f" — Vodafone führt in diesem Band kein Bündel mit {laufzeit} Raten."
    return f" — Vodafone mit {laufzeit} Raten ohne Zahl."


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


def _rechnung_html(zeilen: list, h: int = TCO_HORIZONT) -> str:
    """(a) Rechenschaftssatz - EINE Zeile unter dem Antwort-Satz.

    Er nennt die Formel der Leitzahl und den Beleg des besten Angebots
    (Absender, Link, Abrufdatum) - die Transparenz-Forderung aus 9a
    („man kann hier nirgendwo auf den Link drücken") am wichtigsten Ort
    der Tafel. `h` ist der Zeitraum der Ansicht (24 oder 36 Monate).
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
        f"So gerechnet: <code>Kosten über {h} Monate = Anzahlung + "
        f"Tarif über {h} Monate + alle Geräteraten + "
        f"Anschlusspreis</code> — Boni bleiben außerhalb. Beleg des "
        f"günstigsten Angebots: {link}{datum_teil}."
    )
