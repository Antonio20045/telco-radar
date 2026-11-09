"""Legende der Zeitreihe: Name mit Farb-Punkt, Zahlen und überholte Preise.

Aus `geraete_zeitreihe` ausgelagert (Riesendatei-Basis). Die Legende liest nur
fertige Serien; eine belegte Lücke (`geraete_sortiment`, Vermerk `veraltet 17`)
erscheint als eigener Eintrag „frühere Preise überholt“ statt einer Zahl.
"""

from __future__ import annotations

from ..tco_kosten import ZEITRAUM_OHNE_BINDUNG
from . import geraete_notbremse as notbremse
from . import geraete_preisstand as preisstand
from .geraete_rechenweg import ANBIETER_FOLGE, _esc, _zr_marker_farbe


def _euro0(betrag) -> str:
    if betrag is None:
        return ""
    return f"{betrag:,.0f}".replace(",", ".") + " €"


def _mon_kurz(monate: list) -> str:
    """„24 Mon." / „24 Mon./36 Raten" - das Etikett AN der Kurve (P0-B-z1).

    Mehr als 24 Monate sind Geräteraten, kein Tarifzeitraum: der Tarif zählt
    höchstens 24 Monate (`tco_kosten.ZEITRAUM_OHNE_BINDUNG`), danach nur die
    Rate. Darum steht dort „36 Raten“ und nie „36 Mon.“.

    Kurz, weil es im Bild neben dem Anbieternamen steht (Antonios Stil:
    wenig Text, keine Erklaerzeile). Die Zahlen sind GELESEN
    (`_zeitraeume_aus` -> `Tco.leitzahl_monate`), nicht gerechnet; ohne
    lesbaren Zeitraum steht hier nichts - eine Annahme waere schlimmer
    als die Luecke (Clean Code 4).
    """
    if not monate:
        return ""
    return "/".join(
        f"{m} Mon." if m <= ZEITRAUM_OHNE_BINDUNG else f"{m} Raten" for m in monate
    )


def ohne_alte(modell: dict, mess: dict, serien: dict) -> dict:
    """Die Messungen ohne die Anbieter, die eine belegte Lücke überholt hat und die
    keine Reihe mehr haben: ihre Rechenweg-Vorlagen (`<template data-m=…>`) wären
    nicht erreichbar, trügen aber die alte Zahl im HTML."""
    luecken = modell.get("belegte_luecken") or {}
    return {a: m for a, m in mess.items() if serien.get(a) or a not in luecken}


def _worte(karten: list) -> str:
    """Die Wörter der Tafel für Zeilen, die nicht zählen, ohne Wiederholung."""
    worte = dict.fromkeys(preisstand.zeilen_grund(k) for k in karten)
    return ", ".join(w for w in worte if w)


def _satz(anbieter: str, text: str) -> str:
    return (
        f"<span class='gr-zr-leg-ueberholt'><i style='background:"
        f"{_zr_marker_farbe(anbieter)}'></i>{_esc(anbieter)} · {_esc(text)}</span>"
    )


def schaetzung_html(satz: dict | None, mess: dict, serien: dict) -> str:
    """Satz unter der Legende für jeden Anbieter, dessen Legendenzahl die Tafel nicht
    schon trägt. Eine Legendenzahl gilt der letzten zählenden Messung; die Tafel führt
    für die Kombination (Gerät × Speicher × Band × Laufzeit) aber nur zählende Zeilen
    als Preis. Drei Fälle, immer mit den Wörtern der Tafel (`geraete_preisstand`):

    - keine Zeile und keine Karte des Anbieters: „Die Tafel führt hier keinen Preis“
      (sein Bündel steht in anderen Bändern oder wird nicht mehr gelesen);
    - keine zählende Zeile, aber Karten: sie werden benannt (nicht direkt genannt,
      Preis veraltet, nur mit Zweitprodukt);
    - eine zählende Zeile, daneben ein billigerer Preis, der nicht zählt: der Leser
      sieht sonst in der Tafel eine kleinere Zahl als in der Legende.

    Ohne `satz` gibt es keine Tafel zum Vergleich und nichts zu erklären."""
    if satz is None:
        return ""
    zeilen = {z["anbieter"]: z for z in satz.get("zeilen") or []}
    karten = [
        k
        for k in satz.get("karten") or []
        if k.get("sku_id") and (k.get("zustand") or "neu") == "neu"
    ]
    saetze = []
    for anbieter in ANBIETER_FOLGE:
        serie, tage = serien.get(anbieter), mess.get(anbieter)
        if not serie or not tage:
            continue
        if not notbremse.zaehlt(tage.get(serie[-1][0]) or {}):
            continue
        eigene = [k for k in karten if k["anbieter"] == anbieter]
        zahl, zeile = _euro0(serie[-1][1]), zeilen.get(anbieter)
        if zeile is None:
            worte = _worte(eigene)
            nennt = (
                f"Die Tafel nennt hier nur Preise, die nicht zählen ({worte})"
                if worte
                else "Die Tafel führt hier keinen Preis"
            )
            saetze.append(
                _satz(
                    anbieter,
                    f"{nennt}; die Legende zeigt die letzte zählende Messung ({zahl}).",
                )
            )
            continue
        billiger = [
            k
            for k in eigene
            if k.get("vergleichbar")
            and k.get("gesamt") is not None
            and not notbremse.zaehlt(k)
            and preisstand.preis_sichtbar(k)
            and round(k["gesamt"]) < round(zeile["gesamt"])
        ]
        if billiger:
            guenstigste = min(billiger, key=lambda k: k["gesamt"])
            saetze.append(
                _satz(
                    anbieter,
                    f"Die Tafel nennt hier zusätzlich einen billigeren Preis, "
                    f"der nicht zählt ({preisstand.zeilen_grund(guenstigste)}: "
                    f"{_euro0(guenstigste['gesamt'])}); die Legende zeigt die "
                    f"zählende Zeile ({zahl}).",
                )
            )
    return "".join(saetze)


def ueberholt_html(
    modell: dict, mess: dict, serien: dict, satz: dict | None = None
) -> str:
    """Legendeneintrag je Anbieter, dessen Preise eine belegte Lücke überholt hat
    (`geraete_sortiment`, Vermerk `veraltet 17`): gemessen wurde, die Reihe fehlt
    aber, weil der Preis nicht mehr zählt. Ohne den Eintrag fehlte der Anbieter
    in der Grafik kommentarlos; die Zahl bleibt weg (kein „zuletzt 2.001 €“)."""
    luecken = modell.get("belegte_luecken") or {}
    return "".join(
        f"<span class='gr-zr-leg-ueberholt'><i style='background:"
        f"{_zr_marker_farbe(a)}'></i>{_esc(a)} · {_esc(luecken[a]['kurz'])}"
        f", frühere Preise überholt und nicht gezeigt</span>"
        for a in ANBIETER_FOLGE
        if a in luecken and mess.get(a) and not serien.get(a)
    ) + schaetzung_html(satz, mess, serien)


def legende_html(
    anbieter_serien: dict, zeitraeume: dict | None = None, ueberholt: str = ""
) -> str:
    """EINE Zeile ueber dem Graphen: Name mit Farb-Punkt, Vodafone rot und
    benannt. Der „anfangs"-Wert (erster Messbetrag, F9) steht im eigenen Span, der
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
            f" <span class='gr-zr-leg-wert'>anfangs {_euro0(serie[0][1])}"
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
    if not eintraege and not ueberholt:
        return ""
    return "<div class='gr-zr-legende'>" + "".join(eintraege) + ueberholt + "</div>"
