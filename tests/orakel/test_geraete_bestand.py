"""Orakel der Geräteseite am Schnappschuss: jede Leitzahl, Stufe und Exportzeile
der gerenderten Seite gegen eine eigene Rechnung aus den Rohdaten.

Gerendert wird einmal je Worker aus ``tests/fixtures/bestand`` (Fixture ``gw_seite``
in ``conftest.py``). Die Rechnung importiert keinen Baustein des Codes, den sie prüft;
der Vertrag ``orakel`` in ``.importlinter`` hält das fest.
"""

from __future__ import annotations

import csv as _gw_csv
import datetime as _gw_dt
import html as _pr_html
import json
import math as _gw_math
import re
from decimal import ROUND_HALF_EVEN as _gw_HEVEN
from decimal import ROUND_HALF_UP as _gw_HUP
from decimal import Decimal as _gw_Dez
from pathlib import Path

import pytest

_GW_HORIZONT = 24
_GW_SPALTE_24 = "Kosten über 24 Monate EUR"
_GW_SPALTE_LAUFZEIT = "Kosten über die Bündellaufzeit EUR"


def _gw_leitzahl_aus_zeile(zeile: dict) -> str:
    """Die Leitzahl einer Exportzeile aus der Spalte, deren Kopf ihren Zeitraum nennt.

    Die Köpfe stehen hier wörtlich; benennt der Export sie um, wird das Orakel rot."""
    return zeile.get(_GW_SPALTE_24) or zeile.get(_GW_SPALTE_LAUFZEIT) or ""


def gw_cent(wert) -> int:
    """Euro (float/str) -> ganze Cent, kaufmaennisch (HALF_UP)."""
    return int((_gw_Dez(str(wert)) * 100).quantize(_gw_Dez("1"), rounding=_gw_HUP))


def _gw_dezimal(text: str) -> _gw_Dez:
    """'1.459,00' -> Decimal('1459.00') (deutsches Zahlenformat der Seite)."""
    return _gw_Dez(text.replace(".", "").replace(",", "."))


def _gw_rohdaten(bestand: Path) -> tuple[dict, dict, dict]:
    """(tco-store, tarifblaetter je id, geraete_db) aus dem Schnappschuss."""
    tco = json.loads(
        (bestand / "state" / "geraete_tco.json").read_text(encoding="utf-8")
    )
    blaetter: dict[str, list] = {}
    for zeile in (
        (bestand / "state" / "tarife.jsonl").read_text(encoding="utf-8").splitlines()
    ):
        if zeile.strip():
            blatt = json.loads(zeile)
            blaetter.setdefault(blatt["tarif_id"], []).append(blatt)
    db = json.loads((bestand / "state" / "geraete_db.json").read_text(encoding="utf-8"))
    return tco, blaetter, db


def _gw_phasen(buendel: dict, blaetter: dict) -> list[dict]:
    """Blatt-Phasen des Bündels - nur ohne Widerspruch zur Messung.

    Es gilt die AKTUELLE Lesart des Vertrags (`_gw_aktuell`, siehe Kopf): trägt
    sie keine Phasen, gibt es keine, auch wenn ein älteres Blatt oder die
    andere Lesart welche nannte. Die Messung (tarif_monatlich) muss in der
    Preisspanne der Phasen liegen (einschliesslich, Toleranz ein halber Cent);
    sonst gewinnt die Messung flach und die Phasen gelten nicht. Ohne Messung
    gibt es keinen Widerspruch. Eigenbau nach der dokumentierten Regel, nicht
    importiert.
    """
    blatt = _gw_aktuell_gemerkt(blaetter).get(buendel.get("tarif_id") or "") or {}
    phasen = [
        p for p in (blatt.get("preisphasen") or []) if p.get("betrag") is not None
    ]
    messung = buendel.get("tarif_monatlich")
    if not phasen or messung is None:
        return phasen
    betraege = [_gw_Dez(str(p["betrag"])) for p in phasen]
    toleranz = _gw_Dez("0.005")
    if min(betraege) - toleranz <= _gw_Dez(str(messung)) <= max(betraege) + toleranz:
        return phasen
    return []


_GW_AKTUELL_MERKER: dict = {}


def _gw_aktuell_gemerkt(blaetter: dict) -> dict:
    """`_gw_aktuell` je Blattsammlung einmal - die Bestandstests fragen tausendfach."""
    schluessel = id(blaetter)
    if schluessel not in _GW_AKTUELL_MERKER:
        _GW_AKTUELL_MERKER.clear()
        _GW_AKTUELL_MERKER[schluessel] = (blaetter, _gw_aktuell(blaetter))
    return _GW_AKTUELL_MERKER[schluessel][1]


def _gw_cent_oder_luecke(wert) -> int | None:
    """Wie ``gw_cent``; ein nicht erhobener Posten bleibt eine Lücke, nie 0."""
    return None if wert is None else gw_cent(wert)


def _gw_bindung(buendel: dict, blaetter: dict) -> int | None:
    """Die Tarifbindung: aus dem aktuellen Blatt, wenn es eine nennt (0 zählt nicht
    als Angabe), sonst die des Bündels selbst - None, wenn keiner sie kennt."""
    blatt = _gw_aktuell_gemerkt(blaetter).get(buendel.get("tarif_id") or "") or {}
    if blatt.get("laufzeit_monate"):
        return int(blatt["laufzeit_monate"])
    eigene = buendel.get("tarif_bindung_monate")
    return None if eigene is None else int(eigene)


def gw_zeitraum(buendel: dict, blaetter: dict) -> int | None:
    """H der Soll-Definition (Datenkonzept Geräte 5.3): der größere Wert aus
    Ratenlaufzeit und Tarifbindung, eine unbekannte Bindung zählt 24 Monate.
    Ohne Ratenlaufzeit gibt es keinen Zeitraum."""
    laufzeit = buendel.get("laufzeit_monate")
    if laufzeit is None:
        return None
    bindung = _gw_bindung(buendel, blaetter)
    return max(int(laufzeit), _GW_HORIZONT if bindung is None else bindung)


def _gw_nur_grundpreis(phasen: list[dict]) -> bool:
    """Eine einzige Phase ab Monat 1 ohne Ende ist keine Phasentabelle, sondern der
    Grundpreis, wie der Leser eines Produktinformationsblatts ohne Tabelle ihn
    schreibt: sie nennt keinen Monat nach der Bindung."""
    return (
        len(phasen) == 1
        and int(phasen[0].get("von_monat") or 1) == 1
        and phasen[0].get("bis_monat") is None
    )


def _gw_tarif_cent(buendel: dict, blaetter: dict, monate: int) -> int | None:
    """Der Tarif in jedem Monat 1 bis `monate` zum Preis der EINEN Phase, die den
    Monat nennt, in Cent. Ohne Blatt-Phasen gilt der gemessene Preis bis zum Ende
    der Bindung (ohne Bindung 24 Monate), ebenso der Betrag einer einzigen Phase
    ab Monat 1 ohne Ende (`_gw_nur_grundpreis`) - für jeden Anbieter gleich. Ein
    Monat ohne genau eine Phase ist eine Lücke (None), nie der fortgeschriebene
    letzte Preis."""
    phasen = _gw_phasen(buendel, blaetter)
    grundpreis = buendel.get("tarif_monatlich")
    if _gw_nur_grundpreis(phasen):
        grundpreis, phasen = phasen[0]["betrag"], []
    if not phasen:
        if grundpreis is None:
            return None
        bindung = _gw_bindung(buendel, blaetter)
        bis = bindung if bindung else _GW_HORIZONT
        phasen = [{"von_monat": 1, "bis_monat": bis, "betrag": grundpreis}]
    summe = 0
    for monat in range(1, monate + 1):
        nennen = [
            p
            for p in phasen
            if int(p.get("von_monat") or 1) <= monat
            and (p.get("bis_monat") is None or monat <= int(p["bis_monat"]))
        ]
        if len(nennen) != 1:
            return None
        summe += gw_cent(nennen[0]["betrag"])
    return summe


def _gw_leitzahl(buendel: dict, blaetter: dict) -> tuple:
    """(gesamt_cent, H) der Soll-Definition; gesamt None = Lücke.

    Kosten über H Monate = Anzahlung + Anschlusspreis + alle N Geräteraten +
    Tarif in jedem Monat 1 bis H; ein zusammengelegter Bündelbetrag (1&1) trägt
    H × Betrag und gilt nur für H = N. Fehlt ein Posten, gibt es keine Zahl."""
    monate = gw_zeitraum(buendel, blaetter)
    if monate is None:
        return None, None
    laufzeit = int(buendel["laufzeit_monate"])
    if buendel.get("buendel_monatlich") is not None:
        teile = [
            gw_cent(buendel["buendel_monatlich"]) * monate
            if monate == laufzeit
            else None
        ]
    else:
        rate = buendel.get("geraet_monatsrate")
        teile = [
            _gw_tarif_cent(buendel, blaetter, monate),
            None if rate is None else gw_cent(rate) * laufzeit,
        ]
    teile += [
        _gw_cent_oder_luecke(buendel.get("geraet_zuzahlung")),
        _gw_cent_oder_luecke(buendel.get("anschlusspreis")),
    ]
    if any(t is None for t in teile):
        return None, monate
    return sum(teile), monate


_GW_VF_MIT_SMARTPHONE = re.compile(r"^Vodafone Mobil ([A-Z]{1,4}) mit Smartphone$")
_GW_VF_STUFE = re.compile(r"^Vodafone Mobil ([A-Z]{1,4})(?: mit Smartphone)?$")
_GW_LEITER_STAND = (("xs", 15.0), ("s", 30.0), ("m", 60.0), ("l", 120.0), ("xl", None))
_GW_LEITER_STAENDE = (_GW_LEITER_STAND, _GW_LEITER_STAND[:4] + (("xl", float("inf")),))


def _gw_volumen(wert):
    """Datenvolumen als float; None fuer fehlend/unlesbar/NaN, inf bleibt."""
    if wert is None:
        return None
    try:
        zahl = float(wert)
    except (TypeError, ValueError):
        return None
    return None if _gw_math.isnan(zahl) else zahl


def _gw_aktuell(blaetter: dict) -> dict:
    """tarif_id -> aktuelle Lesart des Vertrags (siehe Kopf)."""
    stand = {tid: liste[-1] for tid, liste in blaetter.items() if liste}
    stand = {tid: s for tid, s in stand.items() if not s.get("zurueckgezogen_am")}
    kern_von = {
        tid: tid[: -len("#live_shop")] if tid.endswith("#live_shop") else tid
        for tid in stand
    }
    je_kern: dict = {}
    for tid, satz in stand.items():
        bisher = je_kern.get(kern_von[tid])
        if bisher is None or (
            bisher.get("preistyp") != "live_shop"
            and satz.get("preistyp") == "live_shop"
        ):
            je_kern[kern_von[tid]] = satz
    return {tid: je_kern[kern_von[tid]] for tid in stand} | je_kern


def _gw_leiter(aktuell: dict) -> list:
    """[(key, gb)] der Vodafone-Tarife "mit Smartphone", guenstigste zuerst."""
    stufen: dict = {}
    for satz in aktuell.values():
        if (satz.get("anbieter") or "").strip().lower() != "vodafone":
            continue
        m = _GW_VF_MIT_SMARTPHONE.match((satz.get("name") or "").strip())
        if m and m.group(1).lower() not in stufen:
            stufen[m.group(1).lower()] = (
                _gw_volumen(satz.get("grundgebuehr")),
                _gw_volumen(satz.get("datenvolumen_gb")),
            )
    return [
        (k, stufen[k][1])
        for k in sorted(
            stufen, key=lambda k: (stufen[k][0] is None, stufen[k][0] or 0.0)
        )
    ]


def _gw_band_satz(satz: dict | None, leiter: list) -> str | None:
    """Die Stufe eines Tarifsatzes nach den Regeln im Kopf - oder None."""
    if not satz:
        return None
    if (satz.get("anbieter") or "").strip().lower() == "vodafone":
        m = _GW_VF_STUFE.match((satz.get("name") or "").strip())
        if m and m.group(1).lower() in {k for k, _gb in leiter}:
            return m.group(1).lower()
    gb = _gw_volumen(satz.get("datenvolumen_gb"))
    if gb is None:
        return None
    if _gw_math.isinf(gb):
        return next((k for k, v in leiter if v is not None and _gw_math.isinf(v)), None)
    beste = None
    for key, v in leiter:
        if v is None or _gw_math.isinf(v):
            continue
        rang = (abs(v - gb), -v)
        if beste is None or rang < beste[0]:
            beste = (rang, key)
    return beste[1] if beste else None


def _gw_band(buendel: dict, blaetter: dict) -> str | None:
    """Stufe eines Buendels ueber seine tarif_id - EIGENE Rechnung."""
    aktuell = _gw_aktuell(blaetter)
    return _gw_band_satz(
        aktuell.get(buendel.get("tarif_id") or ""), _gw_leiter(aktuell)
    )


_GW_DATUM_STEM = re.compile(r"\d{4}-\d{2}-\d{2}")


def _gw_heute(tco: dict, berichte: Path) -> str:
    """Der Bezugstag der Auswahl - EIGEN gerechnet, nicht importiert.

    Der SPAETERE von jüngstem Bericht (Stammname in reports/ - das
    Datum, das `render_site` als `heute` durchreicht) und dem `updated`
    des TCO-Stores. ISO-Tage vergleichen lexikographisch korrekt.

    S3a (Diff-Prüfung 21.09.2026): Die Uhr spiegelt die Seiten-Semantik.
    Gezaehlt werden nur Stems, die ein DATUM sind (ein Stray-JSON wie
    "entwurf.json" sortiert lexikalisch hinter jedem Datum und gewann
    vorher das max()), samt der .md-Faelle - deren Berichtsdatum ist der
    Stamm. Und ein unlesbares `updated` zaehlt nicht: Die Seite verwirft
    es ueber `_spaeterer_tag`, der Orakel tut dasselbe, sonst stellte er
    eine Uhr, die die Seite nie hat."""
    bericht = max(
        (
            p.stem
            for p in berichte.glob("*")
            if p.suffix in (".json", ".md") and _GW_DATUM_STEM.fullmatch(p.stem)
        ),
        default="",
    )
    aktualisiert = str(tco.get("updated") or "")
    if not _GW_DATUM_STEM.fullmatch(aktualisiert):
        aktualisiert = ""
    return max(bericht, aktualisiert)


def _gw_frisch(buendel: dict, heute: str) -> bool:
    """EIGENE Frische-Regel der Auswahl (A3): älter als drei Tage
    (dokumentiert in geraete_tco_karten.ALT_AB_TAGEN) führt kein Bündel
    mehr. Ein fehlendes oder unlesbares `abgerufen_am` ist „unbekannt“
    und zählt wie alt (Clean Code 4); ohne Bezugstag altert nichts."""
    if not heute:
        return True
    try:
        alter = (
            _gw_dt.date.fromisoformat(heute)
            - _gw_dt.date.fromisoformat(buendel.get("abgerufen_am") or "")
        ).days
    except ValueError:
        return False
    return alter <= 3


def _gw_zaehlt(buendel: dict, heute: str) -> bool:
    """EIGENE Notbremse (Datenkonzept Geräteradar, Abschnitt 4 Regel 1): ein
    Bündel mit `herleitung` stand so nie beim Anbieter (Schätzung), und eines,
    dessen eingerechnete Aktion vor `heute` endet (`gueltig_bis`), trägt einen
    Preis von gestern. Beide stellen keinen Sieger. Ohne Ende oder ohne
    Bezugstag läuft eine Aktion weiter."""
    if str(buendel.get("herleitung") or "").strip():
        return False
    for aktion in buendel.get("aktionen") or []:
        ende = str(aktion.get("gueltig_bis") or "").strip()
        if (
            aktion.get("eingerechnet")
            and ende
            and heute
            and _gw_dt.date.fromisoformat(ende) < _gw_dt.date.fromisoformat(heute)
        ):
            return False
    return True


def _gw_min_buendel(
    tco: dict,
    blaetter: dict,
    sku_präfix: str,
    band: str,
    anbieter: str = "",
    *,
    heute: str,
):
    """Günstigstes neu-Bündel des Modells im Band nach EIGENER Rechnung.

    Auswahlmenge wie die Seite: Zustand neu (vergleichbar), eine
    belastbare Zahl (ohne Tarifgrundpreis zaehlt ein Bündel nicht), -
    seit A3 - FRISCHE (`_gw_frisch`) und eine Leitzahl ueber 24 Monate
    (kein Bündel mit 36 Raten oder Bündelbetrag über 36 Monate, P0-B-h3 und
    Datenkonzept Geräte 5.3), seit der Notbremse nur Bündel, die zählen
    (`_gw_zaehlt`). Mit `anbieter`
    auf dessen Bündel beschraenkt - die Vodafone-Referenz ist das Minimum UNTER DEN
    EIGENEN frischen Bündeln, nicht der Sieger des Bandes.
    """
    beste = None
    for b in tco["buendel"]:
        if b.get("zustand") != "neu":
            continue
        if anbieter and b["anbieter"] != anbieter:
            continue
        if not b["sku_id"].startswith(sku_präfix):
            continue
        if _gw_band(b, blaetter) != band:
            continue
        if not _gw_frisch(b, heute) or not _gw_zaehlt(b, heute):
            continue
        gesamt, monate = _gw_leitzahl(b, blaetter)
        if gesamt is None or monate != _GW_HORIZONT:
            continue
        if beste is None or gesamt < beste[0]:
            beste = (gesamt, b)
    return beste


def test_gw_heute_liest_nur_datums_stems_und_lesbare_uhren(tmp_path):
    """S3a (Diff-Prüfung 21.09.2026): die Orakel-Uhr spiegelt die
    Seiten-Semantik von `render_site` - nur Stems, die ein Datum sind
    (wie `html._load_reports` filtert, hier eigenständig nachgebaut),
    SAMT der .md-Fälle (deren Datum der Stamm ist), und ein unlesbares
    `updated` zählt nicht (die Seite verwirft es über `_spaeterer_tag`).
    Vor dem Fix gewann ein Stray-JSON ("entwurf.json") das max() über
    die Stems, und ein unlesbares `updated` ("kaputt") die Endsumme -
    die Uhr des Orakels stellte dann ein Datum, das die Seite nie hat."""
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / "entwurf.json").write_text("{}", encoding="utf-8")
    (reports / "2026-09-16.json").write_text("{}", encoding="utf-8")
    (reports / "2026-09-18.md").write_text("# B\n", encoding="utf-8")
    assert _gw_heute({"updated": "kaputt"}, reports) == "2026-09-18"
    assert _gw_heute({"updated": "2026-09-20"}, reports) == "2026-09-20"


def test_gw_zaehlt_sperrt_schaetzung_und_abgelaufene_aktion():
    """Die Notbremse des Orakels: Schätzung und abgelaufene eingerechnete Aktion
    zählen nicht; eine nicht eingerechnete, eine laufende und eine Aktion ohne
    Ende sperren nichts (Gegenprobe)."""

    def aktion(ende: str, eingerechnet: bool = True) -> dict:
        return {"eingerechnet": eingerechnet, "gueltig_bis": ende}

    heute = "2026-10-03"
    assert not _gw_zaehlt({"herleitung": "Tarifsumme minus Geräterate"}, heute)
    assert not _gw_zaehlt({"aktionen": [aktion("2026-09-29")]}, heute)
    assert _gw_zaehlt({"herleitung": " ", "aktionen": []}, heute)
    assert _gw_zaehlt({"aktionen": [aktion("2026-09-29", eingerechnet=False)]}, heute)
    assert _gw_zaehlt({"aktionen": [aktion("2026-10-03"), aktion("")]}, heute)
    assert _gw_zaehlt({"aktionen": [aktion("2050-12-30")]}, heute)
    assert _gw_zaehlt({"aktionen": [aktion("2026-09-29")]}, "")


_GW_ANTWORT_MUSTER = re.compile(
    r"(?:ist (?P<anb1>[^:<]+?) am günstigsten|führt nur (?P<anb2>[^:<]+?)"
    r"|steht nur (?P<anb3>[^:<]+?) im Vergleich)"
    r": <b class='gr-zr-zahl'>(?P<gesamt>[\d.,]+) €</b> "
    r"Kosten über 24 Monate, Ø "
    r"<b class='gr-zr-zahl'>(?P<o>[\d.,]+) €/Monat</b> \((?P<klammer>.*)\)"
)

_GW_LEIT_MUSTER = re.compile(
    r"<b class='gr-leit-zahl'>([\d.,]+) €</b>"
    r"<span class='gr-leit-label'>[^()]*\(([\d.,]+) €(?:, Näherung)?\)"
    r"</span>"
)


def _gw_paar_block(fragment: str, modell: str, band: str) -> str | None:
    """Der div.gr-zr-lager-Block eines (Modell, Band)-Paars."""
    assert fragment, "Fragment ist leer - der Render hat keine Zeitreihe"
    anfang = f'<div class="gr-zr-lager" data-modell="{modell}" data-band="{band}"'
    i = fragment.find(anfang)
    if i < 0:
        return None
    j = fragment.find('<div class="gr-zr-lager"', i + 10)
    return fragment[i : j if j > 0 else len(fragment)]


def _gw_antwort(block: str) -> dict | None:
    assert block, "Paar-Block ist leer - Antwort-Satz nicht lesbar"
    m = _GW_ANTWORT_MUSTER.search(block)
    if not m:
        return None
    return {
        "anb": (m.group("anb1") or m.group("anb2") or m.group("anb3")).strip(),
        "gesamt": _gw_dezimal(m.group("gesamt")),
        "o": _gw_dezimal(m.group("o")),
        "klammer": m.group("klammer"),
    }


def _gw_neueste_vorlage(block: str, anbieter: str) -> tuple:
    """(messtag, inhalt) der neuesten Rechenweg-Vorlage eines Anbieters -
    der Block traegt JEDE Historien-Messung, und aeltere Raten duerfen
    andere sein (gemessen: congstar 29,70 vor dem 30,50 von heute)."""
    vorlagen = re.findall(
        r"<template data-anb='([^']+)' data-m='([^']+)'[^>]*>(.*?)</template>",
        block,
        re.S,
    )
    assert block, "Paar-Block ist leer - kein Rechenweg lesbar"
    eigene = [(m, inhalt) for a, m, inhalt in vorlagen if a == anbieter]
    assert eigene, (
        f"kein {anbieter}-Rechenweg im Paar-Block - ohne ihn "
        "prueft die Restschuld nichts"
    )
    return max(eigene, key=lambda v: v[0])


def gw_vergleiche(ist: _gw_Dez, soll_cent: int, kontext: str) -> None:
    """Der eine Vergleich dieses Abschnitts - Seite gegen eigene Rechnung."""
    assert ist == _gw_Dez(soll_cent) / 100, (
        f"{kontext}: Seite zeigt {ist} €, die eigene Rechnung aus den "
        f"Rohdaten ergibt {_gw_Dez(soll_cent) / 100} €"
    )


def _gw_o_monat(soll_cent: int, monate: int = _GW_HORIZONT) -> set:
    """O/Monat auf Cent gerundet - half-even (Python round der Seite) und
    half-up (kaufmaennisch) als akzeptierte Menge; geteilt durch den Zeitraum H
    der Zahl."""
    genau = _gw_Dez(soll_cent) / (100 * monate)
    return {
        genau.quantize(_gw_Dez("0.01"), rounding=_gw_HEVEN),
        genau.quantize(_gw_Dez("0.01"), rounding=_gw_HUP),
    }


_GW_PFLICHT_SKU = "google-pixel-11-256gb"
_GW_PFLICHT_MODELL = "google-pixel-11-256"
_GW_PFLICHT_TITEL = "Google Pixel 11 256 GB"
_GW_PFLICHT_CSV_MODELL = "pixel-11"
_GW_PFLICHT_SPEICHER = "256"
_GW_PFLICHT_ANBIETER = "congstar"
_GW_PFLICHT_TARIF = "Allnet Flat S"
_GW_PFLICHT_BAND = "m"
_GW_PFLICHT_LEITZAHL = "1.216,00 €"
_GW_PFLICHT_RATEN = {24: 3000, 36: 2000}
_GW_PFLICHT_SOLL = {24: 121600, 36: None}
"""Je Zahlweise die Kosten über H Monate: 1 + 24 × 20,00 + 24 × 30,00 + 15,00; mit
36 Raten (H 36) eine Lücke, weil das Produktinformationsblatt keine Phasentabelle
trägt und den Tarif ab Monat 25 nicht nennt (`_gw_nur_grundpreis`)."""
_GW_LUECKE_AB_25 = "Tarifgrundpreis Monat 25–{} nicht gemessen"


def _gw_ist_startpaar(titel: str) -> bool:
    """Ob der Server-Startblock mit Modell und Stufe des Pflichtfalls beginnt."""
    return (
        _GW_PFLICHT_TITEL in titel
        and f"Band {_GW_PFLICHT_BAND.upper()}" in " ".join(titel.split())
    )


def _gw_pflichtbuendel(tco: dict, blaetter: dict) -> tuple:
    """(soll_cent über 24 Monate, {Laufzeit: Bündel}, {Abruftage}).

    Alle Farben einer Zahlweise rechnen auf dieselbe Zahl; das wird hier
    geprüft, nicht vorausgesetzt. Die Zahl je Zahlweise liefert
    `_gw_pflicht_soll`."""
    kandidaten = [
        b
        for b in tco["buendel"]
        if b["sku_id"].startswith(_GW_PFLICHT_SKU)
        and b["anbieter"] == _GW_PFLICHT_ANBIETER
        and b["tarif_name"] == _GW_PFLICHT_TARIF
        and b.get("zustand") == "neu"
    ]
    assert kandidaten, (
        "Pflichtfall fehlt im Bestand (benannte Lücke, nicht raten): "
        f"kein neu-Bündel {_GW_PFLICHT_ANBIETER}/{_GW_PFLICHT_TARIF} "
        f"zu {_GW_PFLICHT_SKU}"
    )
    for n in {b["laufzeit_monate"] for b in kandidaten}:
        werte = {
            _gw_leitzahl(b, blaetter)[0]
            for b in kandidaten
            if b["laufzeit_monate"] == n
        }
        assert len(werte) == 1, (
            f"Farben des Pflichtfalls mit {n} Raten rechnen verschieden: {werte}"
        )
        assert (None in werte) == (_GW_PFLICHT_SOLL.get(n) is None), (
            f"Pflichtfall mit {n} Raten: eigene Rechnung {werte}, verankert "
            f"{_GW_PFLICHT_SOLL.get(n)}"
        )
    je_laufzeit: dict = {}
    for b in kandidaten:
        vorher = je_laufzeit.setdefault(b["laufzeit_monate"], b)
        assert gw_cent(vorher["geraet_monatsrate"]) == gw_cent(
            b["geraet_monatsrate"]
        ), (
            f"zwei Raten für dieselbe Laufzeit {b['laufzeit_monate']}: "
            f"{vorher['geraet_monatsrate']} gegen {b['geraet_monatsrate']}"
        )
    ist_raten = {
        n: gw_cent(b["geraet_monatsrate"]) for n, b in sorted(je_laufzeit.items())
    }
    assert ist_raten == _GW_PFLICHT_RATEN, (
        f"Zahlweisen des Pflichtfalls sind {ist_raten}, verankert ist "
        f"{_GW_PFLICHT_RATEN} (gemessen 22.09.2026). MEHR: die "
        "Erfassungslücke schliesst sich weiter - nachrechnen und den "
        "Anker samt Datum nachziehen. WENIGER: eine Zahlweise ist "
        "verlorengegangen, das ist ein Fehler und wird behoben."
    )
    baender = {_gw_band(b, blaetter) for b in kandidaten}
    assert baender == {_GW_PFLICHT_BAND}, (
        f"der Pflichttarif liegt nach eigener Leiter-Rechnung in {baender}, "
        f"verankert ist {_GW_PFLICHT_BAND!r} - Leiter oder Volumen haben "
        "sich geaendert, der Anker ist nachzurechnen"
    )
    tage = {b.get("abgerufen_am", "") for b in kandidaten}
    return _gw_leitzahl(je_laufzeit[_GW_HORIZONT], blaetter)[0], je_laufzeit, tage


def _gw_pflicht_soll(je_laufzeit: dict, blaetter: dict) -> dict:
    """{Laufzeit: (Kosten in Cent, H)} je Zahlweise des Pflichtfalls."""
    return {n: _gw_leitzahl(b, blaetter) for n, b in sorted(je_laufzeit.items())}


def _gw_modell_zeilen(gw_seite: dict, modell: str) -> list[str]:
    """Die Bündelzeilen (`<details class="gr-bnd">`, auch die ohne Zahl mit
    `gr-bnd--leer`) eines Modells - aus seinem Block im Nachladefragment, beim
    Startmodell aus `geraete.html`."""
    lager = re.split(r'<div class="gr-bnd-lager" data-modell="', gw_seite["buendel"])
    for block in lager[1:]:
        if block[: block.index('"')] == modell:
            return re.findall(
                r'<details class="gr-bnd(?: gr-bnd--leer)?".*?</details>', block, re.S
            )
    vorgabe = re.search(r'"vorgabe":\s*"([^"]+)"', gw_seite["geraete"])
    if vorgabe and vorgabe.group(1) == modell:
        start = gw_seite["geraete"][gw_seite["geraete"].find('id="gr-bndliste"') :]
        return re.findall(
            r'<details class="gr-bnd(?: gr-bnd--leer)?".*?</details>', start, re.S
        )
    return []


def test_leitzahl_des_pflichtfalls_am_bestand(gw_seite):
    """Der Pflichtfall, in allen Lagen, in denen die Seite ihn trägt:
    Antwort-Satz und Rechenweg im (Modell, Band)-Paar des Fragments -
    das Fragment gehört zum selben Render und trägt ALLE Paare - und,
    wenn der Server-First-Paint gerade mit diesem Paar startet, auch
    dessen Antwort-Satz und Bündelzeile.

    Der Pflichtfall trägt zwei Zahlweisen (24 x 30,00 EUR und 36 x 20,00 EUR).
    Seit Datenkonzept Geräte 5.3 rechnet jede über ihren Zeitraum: 24 Raten
    1.216,00 EUR über 24 Monate; 36 Raten über 36 Monate sind eine benannte
    Lücke, weil das Blatt den Tarif ab Monat 25 nicht nennt (Prüfrunde DK23,
    vorher 1.456,00 EUR). Der Rechenweg der jüngsten Messung nennt die des Horizonts
    (24): die Zeitreihe führt je (Anbieter, Tag) ein Bündel, und bei zwei
    Zeiträumen am selben Tag gewinnt der des Horizonts."""
    tco, blaetter, _db = _gw_rohdaten(gw_seite["bestand"])
    soll_cent, je_laufzeit, _tage = _gw_pflichtbuendel(tco, blaetter)

    assert soll_cent == 121600, (
        f"Pflichtfall-Rechnung ergibt {soll_cent / 100} € - Verankerung "
        "1.216,00 € (1 + 24 × 20,00 + 24 × 30,00 + 15,00) stimmt nicht mehr"
    )
    soll_je = _gw_pflicht_soll(je_laufzeit, blaetter)
    assert {n: c for n, (c, _h) in soll_je.items()} == _GW_PFLICHT_SOLL
    assert {n: h for n, (_c, h) in soll_je.items()} == {24: 24, 36: 36}

    block = _gw_paar_block(gw_seite["fragment"], _GW_PFLICHT_MODELL, _GW_PFLICHT_BAND)
    assert block, f"Paar {_GW_PFLICHT_MODELL}/{_GW_PFLICHT_BAND} fehlt im Fragment"
    antwort = _gw_antwort(block)
    assert antwort, f"Paar ohne Antwort-Satz: {block[:200]!r}"
    assert antwort["anb"] == _GW_PFLICHT_ANBIETER, (
        f"Antwort nennt {antwort['anb']!r}, erwartet congstar"
    )
    gw_vergleiche(
        antwort["gesamt"],
        soll_cent,
        f"Pflichtfall, Antwort-Satz im Paar {_GW_PFLICHT_BAND}",
    )
    assert _GW_PFLICHT_TARIF in antwort["klammer"], antwort["klammer"]
    assert antwort["o"] in _gw_o_monat(soll_cent), (
        f"Ø/Monat im Satz: {antwort['o']} €, erwartet {_gw_o_monat(soll_cent)}"
    )

    messtag, inhalt = _gw_neueste_vorlage(block, _GW_PFLICHT_ANBIETER)
    posten = {}
    for m in re.finditer(
        r"<span class='gr-zr-pn'>([^<]+)</span>.*?"
        r"<span class='gr-zr-pr'>(.*?)</span></li>",
        inhalt,
        re.S,
    ):
        name = m.group(1)
        text = " ".join(re.sub(r"<[^>]+>", " ", m.group(2)).split())
        mal = re.search(r"(\d+) × ([\d.,]+) €\s*=\s*([\d.,]+) €", text)
        posten[name] = (
            (_gw_dezimal(mal.group(3)), int(mal.group(1)), _gw_dezimal(mal.group(2)))
            if mal
            else (_gw_dezimal(re.search(r"([\d.,]+) €", text).group(1)), None, None)
        )
    summe = _gw_dezimal(
        re.search(r"gr-zr-rsumme'>= <b>([\d.,]+) €</b>", inhalt).group(1)
    )
    teile = [_gw_dezimal("0")]
    for _name, (betrag, n, einzeln) in posten.items():
        teile.append(betrag)
        if n is not None:
            assert einzeln * n == betrag, f"Posten {_name}: {n} × {einzeln} != {betrag}"
    assert sum(teile) == summe, (
        f"Rechenweg-Summe {summe} != Summe der Posten {sum(teile)}"
    )
    gw_vergleiche(summe, soll_cent, f"Pflichtfall, Rechenweg-Summe (Messung {messtag})")
    n_raten = posten["Geräterate"][1]
    assert n_raten in je_laufzeit, (
        f"Rechenweg nennt {n_raten} Geräteraten - der Bestand kennt zum "
        f"Pflichtfall nur {sorted(je_laufzeit)}"
    )
    buendel = je_laufzeit[n_raten]
    assert posten["Tarif"][1] == 24 and posten["Tarif"][2] == _gw_Dez(
        str(buendel["tarif_monatlich"])
    )
    assert posten["Geräterate"][2] == _gw_Dez(str(buendel["geraet_monatsrate"])), (
        f"Rechenweg rechnet mit {posten['Geräterate'][2]} € je Rate, der "
        f"Bestand misst {buendel['geraet_monatsrate']} € für "
        f"{n_raten} Raten"
    )
    assert n_raten == _GW_HORIZONT, (
        f"Rechenweg der jüngsten Messung nennt {n_raten} Raten; bei zwei "
        f"Zahlweisen führt die Zeitreihe die über {_GW_HORIZONT} Monate"
    )

    gezeigt, luecken = {}, set()
    for roh in _gw_modell_zeilen(gw_seite, _GW_PFLICHT_MODELL):
        attrs = dict(re.findall(r'data-([a-z-]+)="([^"]*)"', roh.split(">", 1)[0]))
        klar = " ".join(re.sub(r"<[^>]+>", " ", roh).split())
        if (
            attrs.get("anbieter") != _GW_PFLICHT_ANBIETER
            or attrs.get("band") != _GW_PFLICHT_BAND
            or attrs.get("zustand") != "neu"
            or f"{_GW_PFLICHT_TARIF} ·" not in klar
        ):
            continue
        if attrs.get("gesamt") == "":
            n = int(attrs["lz"])
            assert soll_je[n][0] is None, f"{n} Raten: Seite ohne Zahl, Soll {soll_je}"
            assert _GW_LUECKE_AB_25.format(soll_je[n][1]) in klar, klar[:300]
            luecken.add(n)
            continue
        for n, rate in re.findall(r"in (\d+) Raten à ([\d.,]+) €", klar):
            cent, monate = soll_je[int(n)]
            gezeigt[int(n)] = _gw_dezimal(rate)
            gw_vergleiche(
                _gw_Dez(attrs["gesamt"]), cent, f"Pflichtfall, {n} Raten, data-gesamt"
            )
            assert _gw_Dez(attrs["schnitt"]) in _gw_o_monat(cent, monate), attrs
            assert f"Kosten über {monate} Monate" in klar, klar[:200]
            euro = f"{cent // 100:,}".replace(",", ".") + f",{cent % 100:02d} €"
            assert euro in klar, f"{n} Raten: {euro} fehlt wörtlich in der Zeile"
    assert luecken == {n for n, c in _GW_PFLICHT_SOLL.items() if c is None}
    assert gezeigt == {
        n: _gw_Dez(c) / 100
        for n, c in _GW_PFLICHT_RATEN.items()
        if _GW_PFLICHT_SOLL[n] is not None
    }, (
        f"die Seite zeigt zum Pflichtfall die Zahlweisen {gezeigt}, der "
        f"Bestand trägt {_GW_PFLICHT_RATEN}. Eine Zahlweise, die der "
        "Bestand misst und die Seite verschweigt, ist ein Datenverlust"
    )

    titel = re.search(r'class="gr-bnd-titel"[^>]*>([^<]+)<', gw_seite["geraete"])
    if titel and _gw_ist_startpaar(titel.group(1)):
        fp_antwort = _gw_antwort(gw_seite["geraete"])
        assert fp_antwort and fp_antwort["anb"] == _GW_PFLICHT_ANBIETER
        gw_vergleiche(
            fp_antwort["gesamt"], soll_cent, "Pflichtfall, Antwort-Satz im First Paint"
        )


def _gw_pflichttage_ohne_horizont(bestand: Path, tarif_id: str) -> list[str]:
    """Messtage der Historie, an denen der Pflichttarif ohne die Zahlweise des
    Horizonts gemessen wurde."""
    laufzeiten_je_tag: dict = {}
    for z in _pf_historie(bestand):
        if (
            z["id"].startswith(f"buendel--{_GW_PFLICHT_ANBIETER}--{_GW_PFLICHT_SKU}")
            and z.get("tarif_id") == tarif_id
            and z.get("zustand") == "neu"
        ):
            laufzeiten_je_tag.setdefault(z["datum"], set()).add(z["laufzeit_monate"])
    assert laufzeiten_je_tag, "die Historie kennt den Pflichtfall nicht"
    return [t for t, ls in laufzeiten_je_tag.items() if _GW_HORIZONT not in ls]


def test_monatsschnitt_und_restschuld_des_pflichtfalls_am_bestand(gw_seite):
    """Die Zweitzahl (Ø/Monat) und das Ende der Restschuld.

    Bis Datenkonzept Geräte 5.3 trugen beide Zahlweisen des Pflichtfalls
    dieselbe 24-Monats-Zahl, und die 36er wies „davon nach Monat 24 noch zu
    zahlen“ und „danach noch offen“ aus. Seit jede Zahlweise über ihren eigenen
    Zeitraum H rechnet (36 Raten: 36 Monate), liegt jede Rate innerhalb von H:
    eine Restschuld-Zeile wäre eine erfundene Schuld. Geprüft wird je Zahlweise
    Ø/Monat = Kosten ÷ H im Rechenweg der Zeile und im Rechenweg-Panel der
    Zeitreihe, jedes Panel mit dem Etikett seines Zeitraums - und nirgends eine
    Restschuld."""
    tco, blaetter, _db = _gw_rohdaten(gw_seite["bestand"])
    _soll, je_laufzeit, _tage = _gw_pflichtbuendel(tco, blaetter)
    soll_je = _gw_pflicht_soll(je_laufzeit, blaetter)
    assert {
        n: None if c is None else _gw_o_monat(c, h) for n, (c, h) in soll_je.items()
    } == {24: {_gw_Dez("50.67")}, 36: None}

    block = _gw_paar_block(gw_seite["fragment"], _GW_PFLICHT_MODELL, _GW_PFLICHT_BAND)
    vorlagen = re.findall(
        r"<template data-anb='([^']+)' data-m='([^']+)'[^>]*>(.*?)</template>",
        block or "",
        re.S,
    )
    eigene = [(m, roh) for a, m, roh in vorlagen if a == _GW_PFLICHT_ANBIETER]
    assert eigene, "kein congstar-Rechenweg im Paar-Block des Pflichtfalls"
    zahlweisen = set()
    for messtag, roh in eigene:
        n = int(re.search(r"Geräterate</span>.*?(\d+) × ", roh, re.S).group(1))
        assert n in je_laufzeit, f"Rechenweg vom {messtag} nennt {n} Raten"
        zahlweisen.add(n)
        _cent, monate = soll_je[n]
        assert f"Kosten über {monate} Monate" in roh, (messtag, n)
        assert "noch zu zahlen" not in roh and "Restschuld" not in roh, (
            f"Rechenweg vom {messtag} ({n} Raten) weist eine Restschuld aus, "
            f"obwohl alle Raten in {monate} Monaten liegen"
        )
    tage_ohne_horizont = _gw_pflichttage_ohne_horizont(
        gw_seite["bestand"], je_laufzeit[_GW_HORIZONT]["tarif_id"]
    )
    assert (zahlweisen != {_GW_HORIZONT}) == bool(tage_ohne_horizont), (
        f"Rechenwege mit {sorted(zahlweisen)} Raten, die Historie hat "
        f"{len(tage_ohne_horizont)} Tage ohne die {_GW_HORIZONT}-Raten-Zahlweise"
        " - das Fragment hat Messungen verloren oder erfunden"
    )

    geprueft = set()
    for roh in _gw_modell_zeilen(gw_seite, _GW_PFLICHT_MODELL):
        text = " ".join(re.sub(r"<[^>]+>", " ", roh).split())
        raten = re.search(r"in (\d+) Raten à ([\d.,]+) €", text)
        if (
            f'data-anbieter="{_GW_PFLICHT_ANBIETER}"' not in roh
            or f"{_GW_PFLICHT_TARIF} ·" not in text
        ):
            continue
        if 'data-gesamt=""' in roh:
            n = int(re.search(r'data-lz="(\d+)"', roh).group(1))
            assert soll_je[n][0] is None and "Ø" not in text, (n, text[:160])
            assert "noch offen" not in text and "noch zu zahlen" not in text
            geprueft.add(n)
            continue
        assert raten, text[:200]
        n = int(raten.group(1))
        cent, monate = soll_je[n]
        schnitt = re.search(r"Ø ([\d.,]+) €/Monat", text)
        assert schnitt and _gw_dezimal(schnitt.group(1)) in _gw_o_monat(cent, monate)
        assert "noch offen" not in text and "nach 24 Monaten gezahlt" not in text, (
            f"Bündelzeile ({n} Raten) nennt eine Restschuld: {text[:160]!r}"
        )
        geprueft.add(n)
    assert geprueft == set(je_laufzeit), (
        f"Zahlweisen {sorted(geprueft)} geprüft, der Bestand trägt "
        f"{sorted(je_laufzeit)} - eine Bündelzeile des Pflichttarifs fehlt"
    )


_GW_TOR_MODELLE = (
    "apple-iphone-17-pro-256",
    "apple-iphone-17-256",
    "samsung-galaxy-s26-ultra-256",
    "google-pixel-11-256",
)
_GW_TOR_FAELLE = [
    ("apple-iphone-17-pro-256", "xs"),
    ("apple-iphone-17-pro-256", "s"),
    ("apple-iphone-17-pro-256", "m"),
    ("apple-iphone-17-pro-256", "l"),
    ("apple-iphone-17-256", "xs"),
    ("apple-iphone-17-256", "s"),
    ("apple-iphone-17-256", "m"),
    ("apple-iphone-17-256", "l"),
    ("samsung-galaxy-s26-ultra-256", "xs"),
    ("samsung-galaxy-s26-ultra-256", "s"),
    ("samsung-galaxy-s26-ultra-256", "m"),
    ("samsung-galaxy-s26-ultra-256", "l"),
    ("google-pixel-11-256", "xs"),
    ("google-pixel-11-256", "s"),
    ("google-pixel-11-256", "m"),
    ("google-pixel-11-256", "l"),
]


_GW_TOR_FAELLE_XL = [
    ("apple-iphone-17-pro-256", "xl"),
    ("apple-iphone-17-256", "xl"),
    ("samsung-galaxy-s26-ultra-256", "xl"),
    ("google-pixel-11-256", "xl"),
]


def _gw_xl_unbegrenzt(blaetter) -> bool:
    return dict(_gw_leiter(_gw_aktuell(blaetter))).get("xl") == float("inf")


@pytest.mark.parametrize("modell,band", _GW_TOR_FAELLE)
def test_tor_geraete_leitzahl_je_band_am_bestand(gw_seite, modell, band):
    """Je eine Leitzahl der vier Tor-Geräte, je Stufe: die Zahl des
    Antwort-Satzes gegen die EIGENE Minimumsrechnung über alle neu-Bündel
    des Modells in der Stufe - und die Guenstigkeitsbehauptung des Satzes
    ('ist X am guenstigsten' / 'fuehrt nur X' / 'steht nur X im Vergleich',
    Notbremse) gegen dasselbe Minimum.
    Kein Skip: die Faelle sind am Bestand nachgerechnet, ein fehlendes
    Paar oder ein fehlender Satz ist ein Befund."""
    tco, blaetter, _db = _gw_rohdaten(gw_seite["bestand"])
    min_cent, min_buendel = _gw_min_buendel(
        tco,
        blaetter,
        f"{modell}gb",
        band,
        heute=_gw_heute(tco, gw_seite["bestand"] / "reports"),
    ) or (
        None,
        None,
    )
    assert min_buendel is not None, (
        f"die eigene Rechnung findet kein frisches neu-Bündel von {modell} "
        f"in Stufe {band} (Bestand {gw_seite['stand']}) - Tor-Fall neu "
        "nachrechnen, nicht überspringen"
    )
    block = _gw_paar_block(gw_seite["fragment"], modell, band)
    assert block is not None, (
        f"Paar {modell}/{band} fehlt im Fragment, obwohl die eigene "
        f"Rechnung dort {min_buendel['anbieter']} mit "
        f"{_gw_Dez(min_cent) / 100} € findet"
    )
    antwort = _gw_antwort(block)
    assert antwort is not None, f"Paar {modell}/{band} ohne Antwort-Satz"
    gw_vergleiche(
        antwort["gesamt"],
        min_cent,
        f"{modell} Band {band}: Leitzahl des Antwort-Satzes",
    )
    assert antwort["anb"] == min_buendel["anbieter"], (
        f"{modell} Band {band}: Satz nennt {antwort['anb']!r} am günstigsten, "
        f"die eigene Rechnung findet {min_buendel['anbieter']!r} "
        f"mit {_gw_Dez(min_cent) / 100} €"
    )
    assert min_buendel["tarif_name"] in antwort["klammer"], (
        f"Satz nennt Tarif {antwort['klammer']!r}, die Rechnung rechnet "
        f"{min_buendel['tarif_name']!r}"
    )
    assert antwort["o"] in _gw_o_monat(min_cent), (
        f"{modell} Band {band}: Ø/Monat {antwort['o']} € != {_gw_o_monat(min_cent)}"
    )
    for falsch in (antwort["gesamt"] + 1, antwort["gesamt"] - 1):
        with pytest.raises(AssertionError):
            gw_vergleiche(falsch, min_cent, "Gegenprobe")


def _gw_baender_je_modell(tco: dict, blaetter: dict, heute: str) -> tuple[dict, dict]:
    """({modell: Stufen mit irgendeinem neu-Bündel},
    {modell: Stufen mit frischem neu-Bündel und Leitzahl}) - EIGEN."""
    aktuell = _gw_aktuell(blaetter)
    leiter = _gw_leiter(aktuell)
    alle: dict = {}
    frisch: dict = {}
    for b in tco["buendel"]:
        if b.get("zustand") != "neu":
            continue
        band = _gw_band_satz(aktuell.get(b.get("tarif_id") or ""), leiter)
        modell = _pf_modell(b["sku_id"])
        if not band or not modell:
            continue
        alle.setdefault(modell, set()).add(band)
        if _gw_frisch(b, heute) and _gw_leitzahl(b, blaetter)[0] is not None:
            frisch.setdefault(modell, set()).add(band)
    return alle, frisch


def test_tarifleiter_aus_den_rohdaten_ist_die_der_seite(gw_seite):
    """P3-E1: die Stufen der Seite sind die Vodafone-Tarifleiter aus
    tarife.jsonl. EIGENE Ableitung (`_gw_leiter`) gegen die gerenderten
    Stufen-Knöpfe (Etikett, Volumen, Reihenfolge) und gegen `band_folge`
    im Datenknoten - plus der Anker am Bestand vom 25.09.2026."""
    tco, blaetter, _db = _gw_rohdaten(gw_seite["bestand"])
    leiter = _gw_leiter(_gw_aktuell(blaetter))
    assert tuple(leiter) in _GW_LEITER_STAENDE, (
        f"Leiter aus tarife.jsonl ist {leiter}, verankert ist "
        f"{_GW_LEITER_STAENDE} (Stand 25.09.2026) - nachrechnen und den "
        "Anker samt Datum nachziehen"
    )
    seite = gw_seite["geraete"]
    daten = json.loads(
        re.search(
            r'<script type="application/json" id="gr-zeitreihe-daten">(.*?)'
            r"</script>",
            seite,
            re.S,
        ).group(1)
    )
    assert daten["band_folge"] == [k for k, _gb in leiter]
    knoepfe = re.findall(
        r'<button type="button" data-band="([a-z]+)" aria-pressed="[a-z]+">'
        r"([A-Z]+)(?:<small>([^<]*)</small>)?</button>",
        seite,
    )
    assert knoepfe, "keine Stufen-Knöpfe auf der Seite - Lookup ins Leere"
    soll = [
        (
            k,
            k.upper(),
            "" if gb is None else "unbegrenzt" if gb == float("inf") else f"{gb:g} GB",
        )
        for k, gb in leiter
    ]
    assert knoepfe == soll, f"Stufen-Knöpfe der Seite {knoepfe}, eigene Leiter {soll}"
    assert knoepfe != [soll[0], soll[1], soll[3], soll[2], soll[4]]


def test_tor_geraete_zeigen_genau_die_stufen_der_eigenen_rechnung(gw_seite):
    """Je Tor-Gerät: die Stufen, die die Seite als Paar anbietet, sind
    GENAU die, in denen die eigene Rechnung ein neu-Bündel findet (auch
    ein altes - eine Stufe mit nur altem Angebot bleibt wählbar, A3), und
    einen Antwort-Satz trägt ein Paar GENAU dann, wenn die eigene Rechnung
    ein frisches Bündel mit Leitzahl findet. So fallen erfundene Stufen
    (etwa XL ohne ein XL-Bündel) ebenso auf wie verschluckte."""
    tco, blaetter, _db = _gw_rohdaten(gw_seite["bestand"])
    alle, frisch = _gw_baender_je_modell(
        tco, blaetter, _gw_heute(tco, gw_seite["bestand"] / "reports")
    )
    modelle = set(
        re.findall(
            r'<div class="gr-zr-lager" data-modell="([^"]+)"', gw_seite["fragment"]
        )
    )
    assert set(_GW_TOR_MODELLE) <= modelle, "Tor-Geräte fehlen im Fragment"
    for modell in _GW_TOR_MODELLE:
        seite = set(
            re.findall(
                rf'<div class="gr-zr-lager" data-modell="{re.escape(modell)}" '
                r'data-band="([^"]+)"',
                gw_seite["fragment"],
            )
        )
        assert seite == alle.get(modell, set()), (
            f"{modell}: Seite bietet Stufen {sorted(seite)}, die eigene "
            f"Rechnung findet neu-Bündel in {sorted(alle.get(modell, ()))}"
        )
        for band in seite:
            antwort = _gw_antwort(_gw_paar_block(gw_seite["fragment"], modell, band))
            assert (antwort is not None) == (band in frisch.get(modell, ())), (
                f"{modell}/{band}: Antwort-Satz {'da' if antwort else 'fehlt'}"
                f", die eigene Rechnung findet "
                f"{'ein' if band in frisch.get(modell, ()) else 'kein'} "
                "frisches Bündel"
            )
    soll = set(_GW_TOR_FAELLE)
    if _gw_xl_unbegrenzt(blaetter):
        soll |= set(_GW_TOR_FAELLE_XL)
    assert {(m, b) for m in _GW_TOR_MODELLE for b in frisch.get(m, ())} == soll
    leer = 0
    for modell in sorted(modelle):
        for band in alle.get(modell, set()) - frisch.get(modell, set()):
            block = _gw_paar_block(gw_seite["fragment"], modell, band)
            if block is None:
                continue
            leer += 1
            assert _gw_antwort(block) is None, (
                f"{modell}/{band}: Antwort-Satz ohne frisches Bündel"
            )
    assert leer, "kein Paar ohne frisches Angebot - der Leer-Zweig prüft nichts"


def test_jede_stufe_der_seite_ist_von_der_eigenen_rechnung_gedeckt(gw_seite):
    """Alle (Modell, Stufe)-Paare des Fragments gegen die eigene Leiter-
    Zuordnung: keine Stufe ohne neu-Bündel darin, und kein Modell der
    Seite verschweigt eine Stufe, in der es ein neu-Bündel hat."""
    tco, blaetter, _db = _gw_rohdaten(gw_seite["bestand"])
    alle, _frisch = _gw_baender_je_modell(
        tco, blaetter, _gw_heute(tco, gw_seite["bestand"] / "reports")
    )
    paare = set(
        re.findall(
            r'<div class="gr-zr-lager" data-modell="([^"]+)" data-band="([^"]+)"',
            gw_seite["fragment"],
        )
    )
    assert len(paare) >= 200, (
        f"nur {len(paare)} Paare im Fragment - am 27.09.2026 waren es 262"
    )
    modelle = {m for m, _b in paare}
    erfunden = sorted(p for p in paare if p[1] not in alle.get(p[0], ()))
    verschluckt = sorted(
        (m, b) for m in modelle for b in alle.get(m, ()) if (m, b) not in paare
    )
    assert not erfunden, f"Stufen ohne neu-Bündel auf der Seite: {erfunden[:5]}"
    assert not verschluckt, f"Stufen mit neu-Bündel fehlen: {verschluckt[:5]}"


def test_stufe_jeder_exportzeile_gegen_die_eigene_leiter(gw_seite):
    """Die Spalte 'Band' des Exports (Bündel UND SIM-only) gegen die
    eigene Leiter-Zuordnung über die tarif_id des Stores. Ohne Stufe
    (fehlendes oder unbegrenztes Volumen) steht die Zelle LEER - nie eine
    geratene Stufe."""
    tco, blaetter, _db = _gw_rohdaten(gw_seite["bestand"])
    aktuell = _gw_aktuell(blaetter)
    leiter = _gw_leiter(aktuell)
    tarif_id = {
        ("Bündel", b["anbieter"], b["tarif_name"]): b.get("tarif_id")
        for b in tco["buendel"]
    }
    tarif_id.update(
        {
            ("SIM-only", s["anbieter"], s["tarif_name"]): s.get("tarif_id")
            for s in tco.get("sim_only") or []
        }
    )
    zeilen = list(
        _gw_csv.DictReader(gw_seite["csv"].open(encoding="utf-8-sig"), delimiter=";")
    )
    abweich, geprueft, ohne = [], 0, 0
    je_stufe: dict = {}
    for r in zeilen:
        schluessel = (r["Art"], r["Anbieter"], r["Tarif"])
        assert schluessel in tarif_id, (
            f"Exportzeile {schluessel} ohne Store-Satz - Lookup ins Leere"
        )
        band = _gw_band_satz(aktuell.get(tarif_id[schluessel] or ""), leiter)
        soll = band.upper() if band else ""
        geprueft += 1
        ohne += not band
        je_stufe[soll] = je_stufe.get(soll, 0) + 1
        if r["Band"] != soll:
            abweich.append((schluessel, r["Band"], soll))
    assert geprueft >= 900, f"nur {geprueft} Exportzeilen geprüft"
    mindest = 1 if _gw_xl_unbegrenzt(_gw_rohdaten(gw_seite["bestand"])[1]) else 10
    assert ohne >= mindest, "keine Zeile ohne Stufe geprüft - Leer-Zweig greift nicht"
    assert set(je_stufe) == {"XS", "S", "M", "L", "XL", ""}, je_stufe
    assert not abweich, f"{len(abweich)} Exportzeilen mit falscher Stufe: {abweich[:5]}"


def test_vodafone_referenz_und_delta_des_pflichtfalls_am_bestand(gw_seite):
    """Die Leit-Zeile 'X € unter der Vodafone-Referenz (Y €)': die Referenz
    ist die guenstigste EIGENE Karte im selben Band (eine echte Vodafone-
    Bündel-Leitzahl, NICHT die SIM-only-Naeherung aus Blatt und Barpreis).
    Hier nur fuer den Pflichtfall geprueft, und nur wo Vodafone wirklich
    ein neu-Bündel im Band hat - sonst rechnet die Seite eine Naeherung,
    und das ist eine andere Rechnung als diese (benannte Grenze)."""
    tco, blaetter, _db = _gw_rohdaten(gw_seite["bestand"])
    vf = _gw_min_buendel(
        tco,
        blaetter,
        _GW_PFLICHT_SKU,
        _GW_PFLICHT_BAND,
        anbieter="Vodafone",
        heute=_gw_heute(tco, gw_seite["bestand"] / "reports"),
    )
    if vf is None:
        pytest.skip(
            "benannte Lücke: Vodafone ohne neu-Bündel des "
            "Pflichtfalls im Band xs - die Seite rechnet dann "
            "eine Näherung, dieser Test prüft die Bündel-Referenz"
        )
    beste_c, _b, _t = _gw_pflichtbuendel(tco, blaetter)
    soll_ref, soll_delta = vf[0], vf[0] - beste_c

    block = _gw_paar_block(gw_seite["fragment"], _GW_PFLICHT_MODELL, _GW_PFLICHT_BAND)
    leit = _GW_LEIT_MUSTER.search(block or "")
    assert leit, "Leit-Zeile fehlt im Paar des Pflichtfalls"
    gw_vergleiche(_gw_dezimal(leit.group(1)), soll_delta, "Delta zur Vodafone-Referenz")
    gw_vergleiche(
        _gw_dezimal(leit.group(2)), soll_ref, "Vodafone-Referenz der Leit-Zeile"
    )


def test_geraete_tco_csv_gegen_die_eigene_rechnung(gw_seite):
    """site/exporte/geraete-tco.csv desselben Renders: Jede Bündel-Zeile
    aus ihren eigenen Postenspalten nachgerechnet (Zuzahlung + H × Tarif
    + Rate × Laufzeit + Anschluss mit H = 24, bei 36 Raten 36; Bündelform:
    Bündelbetrag × Laufzeit + Zuzahlung + Anschluss), und ihr Zeitraum H
    steht in der Spalte „Leitzahl-Zeitraum Monate“. SIM-only-Zeilen prüft der
    EIGENE Test mit dem fachlichen Soll inklusive Anschlusspreis (P0.8/A4) -
    hier stehen sie nicht, damit dieser Test nur die Bündel scharf hält. Und der heutige
    Stand zusaetzlich gegen den Store: jedes Bündel mit
    abgerufen_am == tco.updated muss als CSV-Zeile mit genau diesen
    Posten stehen und auf dieselbe Zahl rechnen."""
    tco, blaetter, _db = _gw_rohdaten(gw_seite["bestand"])
    zeilen = list(
        _gw_csv.DictReader(gw_seite["csv"].open(encoding="utf-8-sig"), delimiter=";")
    )
    assert zeilen, "Export ohne Zeilen"

    def _n(s):
        return None if s in (None, "") else _gw_Dez(s.replace(",", "."))

    abweich, geprueft = [], 0
    for r in zeilen:
        zu, tarif = _n(r["Zuzahlung EUR"]), _n(r["Tarif/Monat EUR"])
        rate = _n(r["Geräterate EUR"])
        buendel = _n(r["Bündel/Monat EUR"])
        anschluss = _n(r["Anschlusspreis EUR"])
        lz = r["Laufzeit Monate"]
        if r["Art"] == "SIM-only":
            continue
        monate = max(int(lz), _GW_HORIZONT) if lz else None
        if buendel is not None:
            soll = buendel * int(lz) + (zu or 0) + (anschluss or 0)
        elif lz and tarif is not None and rate is not None:
            soll = (zu or 0) + tarif * monate + rate * int(lz) + (anschluss or 0)
        else:
            soll = None
        ist = _n(_gw_leitzahl_aus_zeile(r))
        if soll is None or ist is None:
            continue
        geprueft += 1
        assert r["Leitzahl-Zeitraum Monate"] == str(monate), (r["Anbieter"], lz)
        if soll != ist:
            abweich.append(
                (
                    r["Art"],
                    r["Anbieter"],
                    r["Modell"],
                    r["Tarif"],
                    float(ist),
                    float(soll),
                )
            )
    assert geprueft >= 400, (
        f"nur {geprueft} von {len(zeilen)} Zeilen nachgerechnet - der Test "
        "greift nicht mehr"
    )
    assert not abweich, (
        f"{len(abweich)} CSV-Zeilen widersprechen ihren eigenen Posten: {abweich[:5]}"
    )

    _soll, _pflichtbuendel, tage = _gw_pflichtbuendel(tco, blaetter)
    pflicht = [
        r
        for r in zeilen
        if r["Anbieter"] == _GW_PFLICHT_ANBIETER
        and r["Tarif"] == _GW_PFLICHT_TARIF
        and r["Speicher GB"] == _GW_PFLICHT_SPEICHER
        and r["Modell"].lower().replace(" ", "-") == _GW_PFLICHT_CSV_MODELL
        and r["Abgerufen am"] in tage
    ]
    assert pflicht, f"Pflichtfall fehlt im Export (Stand {gw_seite['stand']})"
    soll_je = _gw_pflicht_soll(_pflichtbuendel, blaetter)
    for zeile in pflicht:
        ist, soll = (
            _n(_gw_leitzahl_aus_zeile(zeile)),
            soll_je[int(zeile["Laufzeit Monate"])][0],
        )
        if soll is None:
            assert ist is None, f"Pflichtfall-Lücke trägt im Export {ist} €"
            continue
        gw_vergleiche(
            ist, soll, f"Pflichtfall im CSV-Export, {zeile['Laufzeit Monate']} Raten"
        )

    treffer = _gw_csv_store_abgleich(zeilen, tco, blaetter, gw_seite["stand"])
    assert treffer >= 200, (
        f"nur {treffer} heute gemessene Bündel im CSV nachgerechnet - der "
        "Store-Abgleich greift nicht mehr"
    )


def _gw_csv_store_abgleich(zeilen: list, tco: dict, blaetter: dict, stand: str) -> int:
    """Jedes am Stand gemessene Bündel steht mit seinen Posten im Export und
    rechnet dort auf dieselbe Zahl; gibt die Zahl der nachgerechneten zurück."""

    def _n(s):
        return None if s in (None, "") else _gw_Dez(s.replace(",", "."))

    stand_zeilen = {
        (
            r["Anbieter"],
            r["Tarif"],
            r["Modell"],
            r["Speicher GB"],
            r["Laufzeit Monate"],
            r["Zustand"],
            r["Zuzahlung EUR"],
            r["Tarif/Monat EUR"],
            r["Geräterate EUR"],
            r["Bündel/Monat EUR"],
            r["Anschlusspreis EUR"],
            _gw_leitzahl_aus_zeile(r),
        ): r
        for r in zeilen
    }
    treffer = 0
    for b in tco["buendel"]:
        if (
            b.get("abgerufen_am") != stand
            or not b["sku_id"]
            or b.get("zustand", "neu") != "neu"
        ):
            continue
        g, _monate = _gw_leitzahl(b, blaetter)
        if g is None:
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", b["sku_id"]).strip("-")
        teile = slug.split("-")
        speicher = next(
            (t for t in teile if t.endswith("gb") and t[:-2].isdigit()), None
        )
        if speicher is None:
            continue
        modell = "-".join(teile[1 : teile.index(speicher)])

        def _eur(wert):
            return "" if wert is None else f"{float(wert):.2f}".replace(".", ",")

        posten = (
            _eur(b.get("geraet_zuzahlung")),
            _eur(b.get("tarif_monatlich")),
            _eur(b.get("geraet_monatsrate")),
            _eur(b.get("buendel_monatlich")),
            _eur(b.get("anschlusspreis")),
        )
        gefunden = [
            schluessel
            for schluessel in stand_zeilen
            if schluessel[0] == b["anbieter"]
            and schluessel[1] == b["tarif_name"]
            and schluessel[2].lower().replace(" ", "-") == modell
            and schluessel[3] == speicher[:-2]
            and schluessel[4] == str(b["laufzeit_monate"])
            and schluessel[6:11] == posten
        ]
        if not gefunden:
            continue
        for schluessel in gefunden:
            ist = _n(schluessel[11])
            assert ist == _gw_Dez(g) / 100, (
                f"CSV-Zeile {schluessel[:4]}: {ist} €, Store-Rechnung "
                f"{_gw_Dez(g) / 100} € (Posten {schluessel[6:11]})"
            )
            treffer += 1
    return treffer


def test_geraete_tco_csv_simonly_mit_anschlusspreis(gw_seite):
    """Der FACHLICHE Soll der SIM-only-Zeilen: 24 × Tarif PLUS
    Anschlusspreis, wo die Zeile ihn trägt (A4, 20.09.2026: die
    SIM-only-Leitzahl ist dieselbe Rechnung wie die der Bündel - Soll-
    Definition der Leitzahl und Konsistenz zu geraeteanteil(), das
    tco_24(als_buendel()) schon immer so rechnete; bis A4 rechnete der
    Export ohne ihn, und der Orakel-Soll war der Bug). Eine LEERE Zelle
    ist die Lücke des Modells (unbekannt ist nicht kostenlos), der
    Orakel-Soll rechnet dann ohne ihn - dieselbe Konvention wie beim
    Bündel-Zweig oben. Zuzahlung und Geräterate werden in SIM-only-Zeilen
    nicht erhoben und stehen leer.

    Auftrag P0.8: "Im SIM-only-Export fehlt der Anschlusspreis" - bis
    P0-A4 (2026-09-20) rechnete die Kennzahl ihn nicht ein; seither ist
    die SIM-only-Leitzahl dieselbe Rechnung wie die der Bündel.
    """
    zeilen = [
        r
        for r in _gw_csv.DictReader(
            gw_seite["csv"].open(encoding="utf-8-sig"), delimiter=";"
        )
        if r["Art"] == "SIM-only"
    ]
    assert zeilen, "Export ohne SIM-only-Zeilen"

    def _z(s):
        return None if s in (None, "") else _gw_Dez(s.replace(",", "."))

    abweich, geprueft, mit_anschluss = [], 0, 0
    for r in zeilen:
        tarif, ist = _z(r["Tarif/Monat EUR"]), _z(_gw_leitzahl_aus_zeile(r))
        anschluss = _z(r["Anschlusspreis EUR"])
        if tarif is None or ist is None:
            continue
        soll = tarif * 24 + (anschluss if anschluss is not None else _gw_Dez(0))
        if anschluss is not None:
            mit_anschluss += 1
        geprueft += 1
        if ist != soll:
            abweich.append((r["Anbieter"], r["Tarif"], float(ist), float(soll)))
    assert geprueft >= 40, (
        f"nur {geprueft} von {len(zeilen)} SIM-only-Zeilen nachgerechnet - "
        "der Test greift nicht mehr"
    )
    assert mit_anschluss >= 5, (
        f"nur {mit_anschluss} SIM-only-Zeilen mit erhobenem Anschlusspreis "
        "- der Soll-Zweig prüfte ins Leere (am Bestand vom 2026-09-20: 16)"
    )
    assert not abweich, (
        f"{len(abweich)} SIM-only-Zeilen ohne ihren Anschlusspreis "
        f"(P0.8/A4): {abweich[:5]}"
    )


def test_mutation_eines_euros_am_pflichtfall_schlaegt_aus(gw_seite):
    """Schärfen-Nachweis des Auftrags: Wird die angezeigte Zahl um 1 €
    verdreht (an der EXTRAHIERTEN Zahl, nicht an den Daten), muss der
    Vergleich dieses Abschnitts rot werden. Ein Test, dessen Lookup ins
    Leere läuft, ist grün und prüft nichts - hier ist die Gegenprobe als
    eigener Test, sie läuft bei jedem Lauf mit.

    Was was belegt: Der AUTOMATISMUS unten (pytest.raises um
    gw_vergleiche) weist nur nach, dass der VERGLEICH bei einer um 1 €
    verdrehten Zahl rot wird - nicht, dass die Extraktion sie findet.
    Die EXTRAKTIONSKETTE (Paar-Block-Wahl, Antwort-Regex, Wahl der
    neuesten Vorlage) belegt der manuelle Nachweis vom 20.09.2026: gegen
    den Render in /tmp wurde die Antwort-Zahl im gerenderten Text selbst
    auf 1.460,00 gesetzt und dieselbe Kette liefen lassen - rot mit
    'Mutation +1: Seite zeigt 1460.00 €, die eigene Rechnung aus den
    Rohdaten ergibt 1459 €' (und '1458.00 €' bei −1 €); unverändert lief
    derselbe Aufruf ohne Fehler."""
    tco, blaetter, _db = _gw_rohdaten(gw_seite["bestand"])
    soll_cent, _b, _t = _gw_pflichtbuendel(tco, blaetter)
    block = _gw_paar_block(gw_seite["fragment"], _GW_PFLICHT_MODELL, _GW_PFLICHT_BAND)
    antwort = _gw_antwort(block)
    assert antwort, "ohne Antwort-Satz prüft die Mutation nichts"
    for mutation in (antwort["gesamt"] + 1, antwort["gesamt"] - 1):
        with pytest.raises(AssertionError):
            gw_vergleiche(_gw_Dez(mutation), soll_cent, "Mutation")
    gw_vergleiche(antwort["gesamt"], soll_cent, "Gegenprobe unverändert")


def test_ein_verfaelschter_schnappschuss_macht_den_pflichtfall_rot(gw_seite, tmp_path):
    """Eine Kopie des Schnappschusses mit einer um 1 Cent verfälschten
    Geräterate des Pflichtfalls: die eigene Rechnung hält ihn nicht mehr am
    Anker. Gegenprobe: die unveränderte Kopie hält ihn."""
    quelle = gw_seite["bestand"] / "state"
    for verfaelscht in (False, True):
        kopie = tmp_path / ("falsch" if verfaelscht else "echt")
        (kopie / "state").mkdir(parents=True)
        for name in ("tarife.jsonl", "geraete_db.json"):
            (kopie / "state" / name).write_bytes((quelle / name).read_bytes())
        tco = json.loads((quelle / "geraete_tco.json").read_text(encoding="utf-8"))
        if verfaelscht:
            treffer = [
                b
                for b in tco["buendel"]
                if b["sku_id"].startswith(_GW_PFLICHT_SKU)
                and b["anbieter"] == _GW_PFLICHT_ANBIETER
                and b["tarif_name"] == _GW_PFLICHT_TARIF
            ]
            assert treffer, "der Pflichtfall fehlt in der Kopie"
            for b in treffer:
                b["geraet_monatsrate"] = round(b["geraet_monatsrate"] + 0.01, 2)
        (kopie / "state" / "geraete_tco.json").write_text(
            json.dumps(tco, ensure_ascii=False), encoding="utf-8"
        )
        tco_kopie, blaetter, _db = _gw_rohdaten(kopie)
        if verfaelscht:
            with pytest.raises(AssertionError, match="Pflichtfall"):
                _gw_pflichtbuendel(tco_kopie, blaetter)
        else:
            assert _gw_pflichtbuendel(tco_kopie, blaetter)[0] == 121600


_PF_MODELL_RE = re.compile(r"^(?P<basis>.+)-(?P<gb>\d+)gb(?:-.*)?$")
_PF_LAGER_RE = re.compile(r'<div class="gr-bnd-lager" data-modell="')
_PF_DETAIL_RE = re.compile(
    r'<details class="gr-bnd(?: gr-bnd--leer)?"(.*?)</details>', re.S
)
_PF_ATTR_RE = re.compile(r'data-([a-z]+)="([^"]*)"')
_PF_TARIF_RE = re.compile(r'gr-bnd-tarif">(.*?)</span>', re.S)
_PF_BAU_RE = re.compile(r'gr-kk-bau">(.*?)</p>', re.S)
_PF_RATEN_RE = re.compile(r"in (\d+) Raten")
_PF_BMONATE_RE = re.compile(r"zusammen · (\d+) Monate")
_PF_KOPFRATEN_RE = re.compile(r'gr-bnd-raten">\s*(\d+) ')

_PF_FAELLE = (
    ("apple-iphone-18-pro-256", "Vodafone", "Mobil XS"),
    ("apple-iphone-17-256", "Vodafone", "Mobil XS"),
    ("apple-iphone-17-256", "Vodafone", "Mobil M"),
    ("apple-iphone-17-256", "1&1", "1&1 All-Net-Flat S"),
    ("samsung-galaxy-s26-ultra-256", "congstar", "Allnet Flat S"),
    ("samsung-galaxy-s26-ultra-256", "Vodafone", "Mobil S"),
    (
        "samsung-galaxy-s26-ultra-256",
        "o2",
        "O2 Mobile Unlimited M Plus mit 100 MBit/s (24 Mon.)",
    ),
    ("google-pixel-11-256", "congstar", "Allnet Flat S"),
    ("google-pixel-11-256", "Vodafone", "Mobil XS"),
    ("google-pixel-11-256", "o2", "O2 Mobile on Demand M Plus mit 50 GB+ (24 Mon.)"),
)
_PF_MINDESTFAELLE = len(_PF_FAELLE)


def _pf_modell(sku_id: str) -> str:
    """`apple-iphone-17-pro-256gb-silber` -> `apple-iphone-17-pro-256`.

    Dieselbe Form, die die Seite als `data-modell` traegt - eigenstaendig
    aus der SKU gebildet, nicht aus `geraete_model` importiert."""
    treffer = _PF_MODELL_RE.match(sku_id or "")
    if treffer is None:
        return ""
    return f"{treffer.group('basis')}-{treffer.group('gb')}"


_PF_HISTORIE_ZEILEN = 2942


def _pf_historie(bestand: Path) -> list[dict]:
    """Alle Zeilen der TCO-Historie - nur lesend, keine Umschreibung."""
    pfad = bestand / "state" / "geraete_tco_historie.jsonl"
    zeilen = [
        json.loads(z)
        for z in pfad.read_text(encoding="utf-8").splitlines()
        if z.strip()
    ]
    assert len(zeilen) == _PF_HISTORIE_ZEILEN, (
        f"{len(zeilen)} Historienzeilen gelesen, der Schnappschuss trägt "
        f"{_PF_HISTORIE_ZEILEN} - ein neuer Schnappschuss verankert sie neu"
    )
    return zeilen


def _pf_anbieter_segment(satz_id: str) -> str:
    """Das Anbietersegment einer Buendel-ID (`buendel--o2--...`)."""
    teile = (satz_id or "").split("--")
    return teile[1] if len(teile) > 2 else ""


def _pf_letzte_messung(
    historie: list[dict],
    modell: str,
    anbieter_slug: str,
    tarif_teil: str,
    laufzeit: int | None = None,
) -> dict:
    """Die JUENGSTE Historienzeile eines neuen Geraets zu (Modell, Anbieter,
    Tarifsegment); refurbished und B-Ware stehen auf der Seite in eigenen Zeilen.

    Der Tarif steckt im letzten ID-Segment, nicht in einem eigenen Feld -
    verglichen wird deshalb auf dem ID-Segment. Mehrere Farben rechnen
    gleich; genommen wird die juengste Messung, bei Gleichstand die mit
    der lexikalisch kleinsten ID (stabil, nie zufaellig)."""
    treffer = []
    for satz in historie:
        satz_id = satz.get("id") or ""
        teile = satz_id.split("--")
        if len(teile) < 4:
            continue
        if _pf_anbieter_segment(satz_id) != anbieter_slug:
            continue
        if _pf_modell(teile[2]) != modell:
            continue
        if teile[3] != tarif_teil:
            continue
        if satz.get("zustand") != "neu":
            continue
        if laufzeit is not None and satz.get("laufzeit_monate") != laufzeit:
            continue
        treffer.append(satz)
    assert treffer, (
        "kein Messpunkt in der Historie fuer "
        f"{anbieter_slug}/{tarif_teil} zu {modell} - der Lookup greift ins "
        "Leere und dieser Test wuerde sonst gruen nichts pruefen"
    )
    return sorted(treffer, key=lambda s: (s.get("datum", ""), s.get("id", "")))[-1]


def pf_leitzahl_cent(satz: dict, blaetter: dict) -> int | None:
    """Die Soll-Leitzahl in Cent - EIGENE Rechnung aus den Posten.

    Rundung: jeder Posten wird einzeln auf ganze Cent gebracht (HALF_UP),
    dann summiert. Multiplikation nach der Rundung, weil die Quellen
    Monatsbetraege in Cent nennen - eine Rate von 30,50 EUR ist 3050
    Cent, nicht 30,4999.

    Eine Luecke ist eine Luecke: fehlt ein Posten, wirft diese Funktion.
    Keine 0, kein `or`-Vorgabewert (CLAUDE.md Clean Code 3). Gerechnet wird
    über den Zeitraum H (`_gw_leitzahl`); nennt das Tarifblatt den Preis eines
    Monats bis H nicht, ist die Antwort None - auch die Seite trägt dann keine
    Zahl."""
    for feld in ("geraet_zuzahlung", "anschlusspreis", "laufzeit_monate"):
        assert satz.get(feld) is not None, (
            f"Posten {feld} fehlt in {satz.get('id')} - eine Leitzahl "
            "daraus waere geraten"
        )
    buendelbetrag = satz.get("buendel_monatlich")
    rate = satz.get("geraet_monatsrate")
    tarif = satz.get("tarif_monatlich")
    if buendelbetrag is not None:
        assert tarif is None and rate is None, (
            f"{satz.get('id')} traegt Buendelbetrag UND getrennte Posten - "
            "welcher gilt, ist dann eine Meinung"
        )
    else:
        assert tarif is not None and rate is not None, (
            f"{satz.get('id')} hat weder Buendelbetrag noch Tarif+Rate"
        )
    return _gw_leitzahl(satz, blaetter)[0]


def pf_seitenzeilen(fragment: str, geraete_html: str = "") -> dict:
    """{modell: [{anbieter, tarif, gesamt_cent, laufzeit_raten, ...}]}

    Gelesen wird das GERENDERTE HTML, nie ein Python-Objekt. Die
    Buendelliste steht je Modell in einem `gr-bnd-lager`-Block des
    Nachladefragments; das STARTMODELL bringt keinen Lager-Block mit -
    seine zwoelf Zeilen stehen inline in geraete.html, und seine Modell-ID
    steht dort als `vorgabe` im JSON-Block `gr-zeitreihe-daten`. Ohne
    diesen Zweig fehlt genau das Geraet, das die Seite zuerst zeigt."""
    zeilen: dict = {}
    for block in _PF_LAGER_RE.split(fragment)[1:]:
        modell = block[: block.index('"')]
        zeilen.setdefault(modell, []).extend(_pf_zeilen_aus_block(block))
    if not geraete_html:
        return zeilen
    daten = re.search(
        r'<script type="application/json" id="gr-zeitreihe-daten">(.*?)'
        r"</script>",
        geraete_html,
        re.S,
    )
    assert daten is not None, (
        "geraete.html ohne JSON-Block gr-zeitreihe-daten - die Modell-ID "
        "der Startansicht ist damit nicht bestimmbar"
    )
    start = json.loads(daten.group(1)).get("vorgabe") or ""
    assert start, "kein `vorgabe`-Modell im JSON-Block der Startansicht"
    inline = _pf_zeilen_aus_block(geraete_html)
    assert inline, (
        f"die Startansicht ({start}) rendert keine einzige Buendelzeile - "
        "der Lookup greift ins Leere"
    )
    zeilen.setdefault(start, []).extend(inline)
    return zeilen


def _pf_zeilen_aus_block(block: str) -> list:
    out = []
    for roh in _PF_DETAIL_RE.findall(block):
        attr = dict(_PF_ATTR_RE.findall(roh))
        if "anbieter" not in attr:
            continue
        tarif = _PF_TARIF_RE.search(roh)
        bau = _PF_BAU_RE.search(roh)
        text = " ".join(_gw_text(bau.group(1)).split()) if bau else ""
        raten = (
            _PF_RATEN_RE.search(text)
            or _PF_BMONATE_RE.search(text)
            or _PF_KOPFRATEN_RE.search(roh)
        )
        out.append(
            {
                "anbieter": _gw_text(attr.get("anbieter", "")),
                "zustand": attr.get("zustand", ""),
                "tarif": " ".join(_gw_text(tarif.group(1)).split()).split(" · ")[0]
                if tarif
                else "",
                "gesamt_cent": gw_cent(attr["gesamt"]) if attr.get("gesamt") else None,
                "laufzeit_raten": int(raten.group(1)) if raten else None,
                "bau": text,
            }
        )
    return out


def _gw_text(roh: str) -> str:
    """HTML-Fragment -> Text (Tags weg, Entities aufgeloest)."""
    import html as _h

    return _h.unescape(re.sub(r"<[^>]+>", " ", roh))


def test_pf_leitzahl_von_zehn_buendeln_gegen_die_historie(gw_seite):
    """Die zweite Rechnung: zehn Leitzahlen der gerenderten Seite gegen
    eine EIGENE Cent-Rechnung aus `geraete_tco_historie.jsonl`.

    Die vier Geraete der Historie im Schnappschuss (iPhone 18 Pro 256,
    iPhone 17 256, Galaxy S26 Ultra 256, Pixel 11 256) x je Anbieter ein
    Buendel, JE RATENLAUFZEIT verglichen (Datenkonzept Geraete 5.5: 24 Raten
    nie gegen 36). Gerechnet wird ueber H = max(Laufzeit, Bindung):
    Anzahlung + Tarif in jedem Monat 1 bis H + Laufzeit x Rate +
    Anschlusspreis, bei 1&1 Anzahlung + H x Buendelbetrag + Anschlusspreis.
    Nennt das Blatt einen Monat bis H nicht, traegt auch die Seite keine Zahl.

    Greift ein Lookup ins Leere (Modell nicht gerendert, Tarif nicht in
    der Historie), ist das rot - nicht uebersprungen. Jeder Fall traegt
    mindestens eine nachgerechnete Zahl."""
    historie = _pf_historie(gw_seite["bestand"])
    _tco, blaetter, _db = _gw_rohdaten(gw_seite["bestand"])
    seite = pf_seitenzeilen(gw_seite["buendel"], gw_seite["geraete"])
    assert seite, "kein einziger Buendelblock im gerenderten HTML"

    slug = {
        "congstar": "congstar",
        "Vodafone": "vodafone",
        "o2": "o2",
        "Telekom": "telekom",
        "1&1": "1-1",
    }
    geprueft, zahlen = [], 0
    for modell, anbieter, tarif in _PF_FAELLE:
        kandidaten = [
            z
            for z in seite.get(modell, [])
            if z["anbieter"] == anbieter
            and z["tarif"] == tarif
            and z["zustand"] == "neu"
        ]
        assert kandidaten, (
            f"Die Seite fuehrt kein neu-Buendel {anbieter}/{tarif} zu "
            f"{modell} - Lookup ins Leere, der Test prueft sonst nichts"
        )
        mit_zahl = 0
        for laufzeit in sorted({z["laufzeit_raten"] for z in kandidaten}):
            assert laufzeit is not None, f"{modell}/{anbieter}: Zeile ohne Ratenzahl"
            satz = _pf_letzte_messung(
                historie,
                modell,
                slug[anbieter],
                re.sub(r"[^a-z0-9]+", "-", tarif.lower()).strip("-"),
                laufzeit,
            )
            soll = pf_leitzahl_cent(satz, blaetter)
            zeilen = [z for z in kandidaten if z["laufzeit_raten"] == laufzeit]
            if soll is None:
                assert all(z["gesamt_cent"] is None for z in zeilen), (
                    f"{modell} / {anbieter} / {tarif} ({laufzeit} Raten): die "
                    "eigene Rechnung findet eine Luecke, die Seite zeigt eine Zahl"
                )
                continue
            ist = min(z["gesamt_cent"] for z in zeilen if z["gesamt_cent"] is not None)
            assert ist == soll, (
                f"{modell} / {anbieter} / {tarif} ({laufzeit} Raten): Seite zeigt "
                f"{ist / 100:.2f} EUR, die eigene Rechnung aus "
                f"{satz['id']} (Messung {satz['datum']}) ergibt {soll / 100:.2f} EUR"
            )
            assert ist + 100 != soll and ist - 100 != soll
            mit_zahl += 1
        assert mit_zahl, f"{modell} / {anbieter} / {tarif}: keine einzige Zahl geprueft"
        zahlen += mit_zahl
        geprueft.append((modell, anbieter, tarif))

    assert len(geprueft) >= _PF_MINDESTFAELLE, (
        f"nur {len(geprueft)} von {_PF_MINDESTFAELLE} Faellen "
        "nachgerechnet - der Test greift nicht mehr"
    )
    assert zahlen > len(geprueft), "keine zweite Ratenlaufzeit nachgerechnet"


_PF_RECHENWEGE_MIT_HISTORIE = 260


def test_pf_die_gezeigte_ratenlaufzeit_ist_eine_gemessene(gw_seite):
    """Jede Laufzeit im Rechenweg der Seite muss im Bestand stehen.

    Die Seite schreibt "720,00 EUR in 36 Raten a 20,00 EUR". Diese 36
    muss die GEMESSENE `laufzeit_monate` eines Buendels desselben
    (Anbieter, Modell, Tarif, Zustand) sein - eine geratene
    Standardlaufzeit im Rechenweg waere eine erfundene Aussage
    (CLAUDE.md Clean Code 3/4).

    Gegenprobe gegen einen leeren Lauf: der Test zaehlt die gepruefte
    Menge und haelt sie exakt am Schnappschuss fest."""
    historie = _pf_historie(gw_seite["bestand"])
    slug_zu_name = {
        "congstar": "congstar",
        "vodafone": "Vodafone",
        "o2": "o2",
        "telekom": "Telekom",
        "1-1": "1&1",
    }
    gemessen: dict = {}
    for satz in historie:
        teile = (satz.get("id") or "").split("--")
        if len(teile) < 4:
            continue
        anbieter = slug_zu_name.get(_pf_anbieter_segment(satz["id"]))
        if anbieter is None:
            continue
        schluessel = (
            anbieter,
            _pf_modell(teile[2]),
            teile[3],
            satz.get("zustand") or "",
        )
        gemessen.setdefault(schluessel, set()).add(satz.get("laufzeit_monate"))

    seite = pf_seitenzeilen(gw_seite["buendel"], gw_seite["geraete"])
    modelle_der_historie = {schluessel[1] for schluessel in gemessen}
    geprueft, fehler, ohne_historie = 0, [], 0
    for modell, zeilen in seite.items():
        if modell not in modelle_der_historie:
            continue
        for z in zeilen:
            if z["laufzeit_raten"] is None:
                continue
            tarifteil = re.sub(r"[^a-z0-9]+", "-", z["tarif"].lower()).strip("-")
            treffer = gemessen.get((z["anbieter"], modell, tarifteil, z["zustand"]))
            if not treffer:
                ohne_historie += 1
                continue
            geprueft += 1
            if z["laufzeit_raten"] not in treffer:
                fehler.append(
                    (
                        modell,
                        z["anbieter"],
                        z["tarif"],
                        f"Seite {z['laufzeit_raten']}, in der "
                        f"Historie {sorted(treffer)}",
                    )
                )
    assert ohne_historie <= 20, (
        f"{ohne_historie} gerenderte Buendel ohne jede Historienzeile - "
        "die Zuordnung Seite/Historie greift nicht mehr"
    )
    assert geprueft == _PF_RECHENWEGE_MIT_HISTORIE, (
        f"{geprueft} Rechenwege gegen die Historie gehalten, am Schnappschuss "
        f"sind es {_PF_RECHENWEGE_MIT_HISTORIE}; der Lookup greift ins Leere"
    )
    assert not fehler, (
        f"{len(fehler)} Rechenwege mit nicht gemessener Laufzeit: {fehler[:5]}"
    )


_PF_STAND_TAG = "2026-10-03"
_PF_STAND_GRUPPEN = 2162
_PF_STAND_MEHRLAUFZEIT = 1649
_PF_STAND_LAUFZEITEN = {
    "1&1": [36],
    "Telekom": [36],
    "Vodafone": [12, 24, 36],
    "congstar": [24, 36],
    "o2": [24, 36],
}


def test_pf_bestand_zaehlt_seine_ratenlaufzeiten_und_haelt_die_luecke_fest(gw_seite):
    """BESTANDSAUSSAGE: welche Ratenlaufzeiten der Schnappschuss trägt.

    Am Schnappschuss vom 2026-10-03 (5941 Bündel): 2162 Gruppen (Anbieter,
    Modell, Tarif, Zustand), davon 1649 mit mehr als einer Laufzeit (o2 814,
    congstar 520, Vodafone 315). 1&1 und Telekom tragen nur 36 Monate, o2 und
    congstar 24 und 36, Vodafone 12, 24 und 36. Die Seite zeigt jede dieser
    Zahlweisen als eigene Bündelzeile; das prüft die Pflichtfall-Gegenprobe
    und `test_pf_beide_ratenlaufzeiten_eines_congstar_abrufs_werden_zwei_zeilen`.

    Mehr Laufzeiten an einem neuen Schnappschuss heißen: die Erfassungslücke
    schließt sich, die Anker werden nachgezogen. Weniger heißen: die
    Mehrfacherfassung ist ausgefallen, das ist ein Fehler. Lücken der
    Erhebung selbst (Telekom und 1&1 nur 36) kann diese Umgebung nicht an
    den Anbieterseiten nachprüfen; der Test hält sie als Zahl fest.
    """
    tco, _blaetter, _db = _gw_rohdaten(gw_seite["bestand"])
    heute = _gw_heute(tco, gw_seite["bestand"] / "reports")
    gruppen: dict = {}
    frische_gruppen: dict = {}
    je_anbieter: dict = {}
    ohne_laufzeit = []
    for b in tco["buendel"]:
        laufzeit = b.get("laufzeit_monate")
        if laufzeit is None:
            ohne_laufzeit.append(b.get("id"))
            continue
        schluessel = (
            b["anbieter"],
            _pf_modell(b["sku_id"]),
            b["tarif_name"],
            b.get("zustand") or "",
        )
        gruppen.setdefault(schluessel, set()).add(laufzeit)
        je_anbieter.setdefault(b["anbieter"], set()).add(laufzeit)
        if _gw_frisch(b, heute):
            frische_gruppen.setdefault(schluessel, set()).add(laufzeit)

    assert len(gruppen) == _PF_STAND_GRUPPEN, (
        f"{len(gruppen)} Gruppen im Bestand vom {heute}, am {_PF_STAND_TAG} "
        f"waren es {_PF_STAND_GRUPPEN}"
    )
    assert not ohne_laufzeit, (
        f"{len(ohne_laufzeit)} Buendel ohne gemessene Ratenlaufzeit "
        f"({ohne_laufzeit[:5]}) - am {_PF_STAND_TAG} war es keines. Eine "
        "fehlende Laufzeit ist eine Luecke, keine 24"
    )

    ist_laufzeiten = {a: sorted(v) for a, v in je_anbieter.items()}
    assert ist_laufzeiten == _PF_STAND_LAUFZEITEN, (
        f"die Ratenlaufzeiten je Anbieter sind {ist_laufzeiten}, am "
        f"{_PF_STAND_TAG} waren es {_PF_STAND_LAUFZEITEN}. MEHR Laufzeiten "
        "oder ein neuer Anbieter: die Erfassungsluecke schliesst sich - "
        "Anker samt Datum im Docstring nachziehen und pruefen, ob die "
        "Seite die zweite Laufzeit zeigt. WENIGER Laufzeiten oder ein "
        "fehlender Anbieter: die Mehrfacherfassung ist ausgefallen - das "
        "ist ein Fehler und wird behoben, nicht umgeschrieben."
    )

    mehrfach = {k: sorted(v) for k, v in gruppen.items() if len(v) > 1}
    frisch_mehrfach = {k: sorted(v) for k, v in frische_gruppen.items() if len(v) > 1}
    assert len(mehrfach) == _PF_STAND_MEHRLAUFZEIT, (
        f"{len(mehrfach)} von {len(gruppen)} Gruppen tragen zwei "
        f"Ratenlaufzeiten, am {_PF_STAND_TAG} waren es genau "
        f"{_PF_STAND_MEHRLAUFZEIT}. MEHR: die "
        "Erfassungsluecke "
        "schliesst sich - Anker mit Datum und Messung hochsetzen. "
        "WENIGER: eine Gruppe hat ihre zweite Laufzeit verloren, das ist "
        f"ein Fehler. Frisch: {len(frisch_mehrfach)} von "
        f"{len(frische_gruppen)}; Beispiele: "
        f"{sorted(mehrfach.items())[:4]}"
    )


def test_pf_simonly_mit_erhobenem_volumen_traegt_sein_band(gw_seite):
    """B3-Gegenprobe: kein SIM-only-Tarif verliert sein Band.

    `tarif_bezug.Tarifbestand.je_id_aktuell` ist AUSSCHLIESSLICH auf den
    baren Schluessel (`tarif_model.zeitreihen_basis`) gefasst. Fuenf
    SIM-only-Referenzen des Bestands tragen aber die Lesart im eigenen
    `tarif_id` (`telekom:magentamobil-l#live_shop`, ebenso s/m/xl und
    `o2:o2-mobile-unlimited-m-flex#live_shop`); ihr Nachschlagen geht
    seit B3 ins Leere. Vorher (HEAD 9999658) stand im TCO-Export
    "MagentaMobil L; Gross", "MagentaMobil M; Mittel", "MagentaMobil S;
    Mittel" - jetzt steht dort nichts.

    Ein erhobener Wert, der zur Luecke wird, ist ein Datenverlust; die
    Zeile faellt zugleich aus jedem Bandraster der Vergleichsansicht."""
    _tco, blaetter, _db = _gw_rohdaten(gw_seite["bestand"])

    def volumen(tarif_id: str):
        for blatt in blaetter.get(tarif_id, []):
            gb = blatt.get("datenvolumen_gb")
            if gb is None:
                continue
            try:
                wert = float(gb)
            except (TypeError, ValueError):
                continue
            if _gw_math.isnan(wert) or _gw_math.isinf(wert):
                continue
            return wert
        return None

    with gw_seite["csv"].open(encoding="utf-8-sig", newline="") as f:
        zeilen = [
            r
            for r in _gw_csv.DictReader(f, delimiter=";")
            if r.get("Art") == "SIM-only"
        ]
    assert zeilen, "Export ohne SIM-only-Zeilen"

    stand = json.loads(
        (gw_seite["bestand"] / "state" / "geraete_tco.json").read_text(encoding="utf-8")
    )
    tarif_je_name = {
        (r["anbieter"], r["tarif_name"]): r.get("tarif_id") or ""
        for r in stand["sim_only"]
    }

    ohne_band, geprueft = [], 0
    for r in zeilen:
        tarif_id = tarif_je_name.get((r["Anbieter"], r["Tarif"]))
        if not tarif_id:
            continue
        gb = volumen(tarif_id)
        if gb is None:
            continue
        geprueft += 1
        if not (r.get("Band") or "").strip():
            ohne_band.append((r["Anbieter"], r["Tarif"], tarif_id, gb))
    assert geprueft >= 20, (
        f"nur {geprueft} SIM-only-Zeilen mit erhobenem Datenvolumen "
        "geprueft - der Lookup greift ins Leere"
    )
    assert not ohne_band, (
        f"{len(ohne_band)} SIM-only-Zeilen mit erhobenem Datenvolumen ohne "
        f"Band: {ohne_band[:6]}"
    )


_PR_DETAIL_RE = re.compile(
    r'<details class="gr-bnd(?: gr-bnd--leer)?"(.*?)</details>', re.S
)
_PR_ATTR_RE = re.compile(r'data-([a-z]+)="([^"]*)"')
_PR_LABEL_RE = re.compile(r'gr-bnd-label">([^<]*)<')
_PR_RWZ_RE = re.compile(r'gr-bnd-rw-z">(.*?)</p>', re.S)
_PR_NAME_RE = re.compile(r'gr-bnd-name">([^<]*)<')
_PR_TARIF_RE = re.compile(r'gr-bnd-tarif">(.*?)</span>', re.S)
_PR_MONATE_RE = re.compile(r"Kosten über (\d+) Monate")
_PR_SCHNITT_RE = re.compile(r"Ø ([\d.]+,\d\d) €/Monat")
_PR_ALARM_RE = re.compile(r'<tr class="gr-a-zeile.*?</tr>', re.S)


def _pr_betrag_cent(text: str) -> int:
    """„1.835,54 €" -> 183554. Eigene Zerlegung, keine Formatierhilfe."""
    roh = (text or "").replace("−", "-").replace("\xa0", " ")
    treffer = re.search(r"-?[\d.]+,\d\d", roh)
    assert treffer, f"kein Betrag in {text!r}"
    zahl = treffer.group(0).replace(".", "").replace(",", ".")
    return int((_gw_Dez(zahl) * 100).to_integral_value(rounding=_gw_HUP))


def _pr_abschnitte(gw_seite: dict) -> list[tuple]:
    """[(modell, quelle, html)] - je Modell der Block mit seinen Zeilen.

    Das Startgeraet steht inline in `geraete.html` (seine ID steht dort im
    JSON-Block als `vorgabe`), alle anderen Modelle in je einem
    `gr-bnd-lager`-Block des Nachladefragments. Der Block wird MIT seinem
    Modell gefuehrt und nicht hinterher ueber den Betrag gesucht: zwei
    Modelle koennen denselben Betrag tragen, und eine Suche nach dem
    ersten Treffer haengt die Zeile dann an das falsche Geraet (eigener
    Fehler, gemessen am 21.09.2026: congstar/Allnet Flat S landete mit
    1.615,00 EUR am Galaxy S26 Ultra)."""
    vorgabe = re.search(r'"vorgabe":\s*"([^"]+)"', gw_seite["geraete"])
    assert vorgabe, "kein `vorgabe`-Modell in geraete.html gefunden"
    stelle = gw_seite["geraete"].find('id="gr-bndliste"')
    assert stelle > 0, "keine Inline-Buendelliste in geraete.html"
    abschnitte = [(vorgabe.group(1), "geraete.html", gw_seite["geraete"][stelle:])]
    for block in re.split(
        r'<div class="gr-bnd-lager" data-modell="', gw_seite["buendel"]
    )[1:]:
        abschnitte.append(
            (block[: block.index('"')], "data/geraete-buendel.html", block)
        )
    assert len(abschnitte) >= 90, (
        f"nur {len(abschnitte)} Modellbloecke gelesen - der Parser greift ins Leere"
    )
    return abschnitte


def _pr_buendelzeilen(gw_seite: dict) -> list[dict]:
    """Alle Buendelzeilen BEIDER Dokumente, je mit ihrem Modell."""
    zeilen = []
    for modell, quelle, text in _pr_abschnitte(gw_seite):
        for treffer in _PR_DETAIL_RE.finditer(text):
            block = treffer.group(1)
            attribute = dict(_PR_ATTR_RE.findall(block))
            etikett = _PR_LABEL_RE.search(block)
            rechenweg = _PR_RWZ_RE.search(block)
            name = _PR_NAME_RE.search(block)
            tarif = _PR_TARIF_RE.search(block)
            zeilen.append(
                {
                    "quelle": quelle,
                    "modell": modell,
                    "attribute": attribute,
                    "etikett": (etikett.group(1) if etikett else ""),
                    "rechenweg": re.sub(
                        r"\s+", " ", re.sub("<[^>]+>", "", rechenweg.group(1))
                    ).strip()
                    if rechenweg
                    else "",
                    "anbieter": (name.group(1) if name else ""),
                    "tarif": re.sub(
                        r"\s+", " ", re.sub("<[^>]+>", " ", tarif.group(1))
                    ).strip()
                    if tarif
                    else "",
                }
            )
    assert len(zeilen) >= 300, (
        f"nur {len(zeilen)} Buendelzeilen gelesen - am 21.09.2026 waren es "
        "375; der Parser greift ins Leere"
    )
    return zeilen


def test_pr_fuenf_leitzahlen_gegen_die_historie_nachgerechnet(gw_seite):
    """Fuenf Bündel je Ratenlaufzeit, EIGENE Rechnung aus der Historie.

    Definition (Datenkonzept Geraete 5.3, Entscheidung 1): Kosten ueber H =
    max(Ratenlaufzeit, Tarifbindung) Monate = Anzahlung + Tarif in jedem Monat
    1 bis H + ALLE Geraeteraten + Anschlusspreis. Bei einem zusammengelegten
    Buendelmonatspreis (1&1) tritt dieser Betrag ueber H an die Stelle von
    Tarif UND Rate. Nennt das Tarifblatt den Preis eines Monats bis H nicht,
    ist die Zahl eine Luecke - auf der Seite steht dann keine.

    Rundung offen benannt: jeder Monatsbetrag wird als ganze Cent gelesen
    und danach multipliziert (eine Rate von 30,50 EUR ist 3050 Cent), die
    Summe bleibt exakt - keine Gleitkommatoleranz.

    Nachgerechnet am Schnappschuss, je juengste Messung der Laufzeit:
      congstar / iPhone 18 Pro 256 / Allnet Flat XS
        24 Raten: 199,00 + 24 x 15,00 + 24 x 49,50 + 15,00  = 1.762,00 EUR
        36 Raten: Blatt ohne Phasentabelle, nichts ab Monat 25 = Luecke
      o2 / iPhone 18 Pro 256 / Unlimited M
        24 Raten: 7,00 + 24 x 24,99 + 24 x 65,00 + 0,00     = 2.166,76 EUR
        36 Raten: Blatt ohne Preis ab Monat 25               = Luecke
      Vodafone / iPhone 18 Pro 256 / Mobil XS
        12 Raten: 0,99 + 24 x 31,95 + 12 x 120,00 + 0,00    = 2.207,79 EUR
        24 Raten: 0,99 + 24 x 31,95 + 24 x 60,00 + 0,00     = 2.207,79 EUR
        36 Raten: Blatt ohne Preis ab Monat 25               = Luecke
      1&1 / iPhone 18 Pro 256 / All-Net-Flat S, Buendelbetrag
        36 Monate: 420,00 + 36 x 49,99 + 39,90              = 2.259,54 EUR
      congstar / Galaxy S26 Ultra 256 / Allnet Flat S
        24 Raten: 119,00 + 24 x 20,00 + 24 x 43,50 + 15,00  = 1.658,00 EUR
        36 Raten: Blatt ohne Phasentabelle, nichts ab Monat 25 = Luecke
    Verglichen wird nur mit der Zeile derselben Ratenlaufzeit.
    """
    historie = _pf_historie(gw_seite["bestand"])
    _tco, blaetter, _db = _gw_rohdaten(gw_seite["bestand"])
    o2_tarif = "o2-mobile-unlimited-m-mit-100-mbit-s-24-mon"
    faelle = (
        ("apple-iphone-18-pro-256", "congstar", "allnet-flat-xs", 24, 176200),
        ("apple-iphone-18-pro-256", "congstar", "allnet-flat-xs", 36, None),
        ("apple-iphone-18-pro-256", "o2", o2_tarif, 24, 216676),
        ("apple-iphone-18-pro-256", "o2", o2_tarif, 36, None),
        ("apple-iphone-18-pro-256", "vodafone", "mobil-xs", 12, 220779),
        ("apple-iphone-18-pro-256", "vodafone", "mobil-xs", 24, 220779),
        ("apple-iphone-18-pro-256", "vodafone", "mobil-xs", 36, None),
        ("apple-iphone-18-pro-256", "1-1", "1-1-all-net-flat-s", 36, 225954),
        ("samsung-galaxy-s26-ultra-256", "congstar", "allnet-flat-s", 24, 165800),
        ("samsung-galaxy-s26-ultra-256", "congstar", "allnet-flat-s", 36, None),
    )
    zeilen = _pr_buendelzeilen(gw_seite)
    geprueft, luecken, fehler = 0, 0, []
    for modell, slug, tarifteil, laufzeit, verankert in faelle:
        satz = _pf_letzte_messung(historie, modell, slug, tarifteil, laufzeit)
        soll = pf_leitzahl_cent(satz, blaetter)
        assert soll == verankert, (
            f"{slug}/{tarifteil} zu {modell} ({laufzeit} Raten): eigene Rechnung "
            f"{soll} Cent gegen verankerte {verankert} Cent"
        )
        treffer = [
            z
            for z in zeilen
            if _pr_anbieter_slug(z["anbieter"]) == slug
            and _pr_tarifteil(z["tarif"]) == tarifteil
            and z["attribute"].get("zustand") == "neu"
            and _pr_ratenzahl(z) in (None, laufzeit)
            and z["modell"] == modell
        ]
        assert treffer, (
            f"keine Buendelzeile {slug}/{tarifteil} ({laufzeit} Raten) zu {modell} "
            "auf der Seite - der Lookup greift ins Leere und dieser Test wuerde "
            "sonst gruen nichts pruefen"
        )
        for zeile in treffer:
            gezeigt = zeile["attribute"].get("gesamt")
            if soll is None:
                luecken += 1
                if gezeigt:
                    fehler.append((modell, slug, laufzeit, gezeigt, "Luecke"))
                continue
            geprueft += 1
            ist = int(
                (_gw_Dez(gezeigt or "0") * 100).to_integral_value(rounding=_gw_HUP)
            )
            if not gezeigt or ist != soll:
                fehler.append((modell, slug, laufzeit, gezeigt, soll))
    assert geprueft >= 6 and luecken >= 4, (
        f"nur {geprueft} Zahlen und {luecken} Luecken geprueft - der Lookup greift "
        "ins Leere"
    )
    assert not fehler, f"Seite gegen eigene Rechnung: {fehler}"


def _pr_ratenzahl(zeile: dict) -> int | None:
    """Die Zahl der Geräteraten aus dem Tarifkopf der Zeile; None in der
    Bündelform, die keine Raten nennt."""
    raten = re.search(r"(\d+) Raten", zeile["tarif"])
    return int(raten.group(1)) if raten else None


def _pr_anbieter_slug(anbieter: str) -> str:
    """„1&1" -> `1-1`, „Vodafone" -> `vodafone` - wie das ID-Segment.

    Die Entities werden ZUERST aufgeloest: `1&amp;1` ergibt sonst
    `1-amp-1`, und der Vergleich zweier Tabellen faellt still ins Leere -
    genau der gruene Test, der nichts prueft."""
    roh = _pr_html.unescape(anbieter or "")
    return re.sub(r"[^a-z0-9]+", "-", roh.lower()).strip("-")


def _pr_tarifteil(tarif: str) -> str:
    """Der Tarifname der Zeile als ID-Segment (ohne „ · 15 GB")."""
    name = _pr_html.unescape(tarif or "").split("·")[0]
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def test_pr_kein_monatsschnitt_teilt_eine_36_monats_summe_durch_24(gw_seite):
    """BEFUND (hoch): Ø/Monat rechnet 36-Monats-Summe / 24 Monate.

    Seit P0-B-fix2 nennt das Etikett den Zeitraum der Zahl
    ("Kosten über 36 Monate"). Der Ø/Monat DERSELBEN Zeile teilt
    weiterhin durch 24 (`tco_model.Tco.monatlich`). Gerendert am
    21.09.2026, 1&1 / iPhone 17 Pro 256 GB:

        "Kosten über 36 Monate 2.019,54 € · Ø 84,15 €/Monat"

    84,15 x 36 = 3.029,40 EUR - die Zeile widerspricht sich selbst. Der
    Monatsbetrag des Angebots ist 44,99 EUR, die Summe ueber ihren
    eigenen Zeitraum ergibt 56,10 EUR je Monat. Betroffen sind 70 Zeilen
    (Seite plus Fragment).

    Geprueft wird die Identitaet, die auf JEDER Zeile gelten muss:
    gezeigter Ø x gezeigte Monate == gezeigte Leitzahl (eine Cent-
    Rundungsspanne je Monat erlaubt)."""
    zeilen = _pr_buendelzeilen(gw_seite)
    geprueft, fehler = 0, []
    for zeile in zeilen:
        monate = _PR_MONATE_RE.search(zeile["etikett"])
        schnitt = _PR_SCHNITT_RE.search(zeile["rechenweg"])
        if monate is None or schnitt is None:
            continue
        geprueft += 1
        n = int(monate.group(1))
        gezeigt = _pr_betrag_cent(schnitt.group(1))
        summe = _pr_betrag_cent(zeile["rechenweg"])
        if abs(gezeigt * n - summe) > n:
            fehler.append(
                (
                    zeile["anbieter"],
                    zeile["tarif"],
                    n,
                    summe / 100,
                    gezeigt / 100,
                    round(summe / n / 100, 2),
                )
            )
    assert geprueft >= 300, (
        f"nur {geprueft} Zeilen mit Etikett UND Ø gelesen - der Parser greift ins Leere"
    )
    assert not fehler, (
        f"{len(fehler)} Zeilen, deren Ø/Monat nicht zu ihrem eigenen "
        f"Zeitraum passt (Anbieter, Tarif, Monate, Summe, Ø gezeigt, "
        f"Ø soll): {fehler[:4]}"
    )


def test_pr_kein_vorzeichen_gegen_vodafone_ueber_zwei_zeitraeume(gw_seite):
    """BEFUND (kritisch): das Delta ist nur in der Buendelzeile entschaerft.

    P0-B-fix2 nimmt der Buendelzeile eines 1&1-Angebots das Euro- und
    Prozent-Delta ("andere Laufzeit", "Kein Abstand zur
    Vodafone-Referenz: diese Zahl trägt 36 Monate, die Referenz 24
    Monate"). Die Alarm-/Radarzeilen desselben Angebots auf derselben
    Seite tragen ihr Vorzeichen weiter (`report/geraete_radar.py:251`
    und `:282` rechnen `prozent` ohne Horizont-Tor), ebenso
    `exporte/wettbewerbsradar.csv` (Status `vergleichbar`, Preisart
    "Kosten über 24 Monate") - gemessen am 21.09.2026: 26 Alarmzeilen mit
    1&1-Prozentzahl, darunter iPhone 17 Pro 256 GB mit +3,3 % gegen eine
    Referenz von 1.955,80 EUR.

    Die 1&1-Zahlen tragen 36 Monate Tarif UND Geraet in EINEM Betrag;
    allein die zwoelf Tarifmonate jenseits des Horizonts (12 x 14,99 EUR
    nach `tarife.jsonl` = 179,88 EUR) sind groesser als jedes hier
    ausgewiesene Delta. Geprueft wird: kein Vorzeichen fuer ein Angebot,
    dessen Buendelzeile den Zeitraum 36 nennt.

    Der Schluessel traegt das Modell: seit die Kernzahl ueber H rechnet
    (Datenkonzept Geraete 5.3), stehen viele 36er-Zeilen auf der Seite, und
    gleiche Betraege verschiedener Geraete sind kein Treffer."""
    zeilen = _pr_buendelzeilen(gw_seite)
    andere_laufzeit = {
        (z["modell"], _pr_anbieter_slug(z["anbieter"]), z["attribute"].get("gesamt"))
        for z in zeilen
        if z["attribute"].get("gesamt")
        and (_PR_MONATE_RE.search(z["etikett"]) or [None, "24"])[1] != "24"
    }
    assert andere_laufzeit, (
        "keine Zeile mit abweichendem Zeitraum auf der Seite - der Test "
        "wuerde sonst gruen nichts pruefen"
    )

    mit_vorzeichen = []
    for treffer in _PR_ALARM_RE.finditer(gw_seite["geraete"]):
        block = treffer.group(0)
        attribute = dict(re.findall(r'data-s-([a-z]+)="([^"]*)"', block))
        anbieter = _pr_anbieter_slug(
            (attribute.get("anbieter") or "").replace("&amp;", "&")
        )
        gesamt = attribute.get("gesamt")
        modell = re.search(r'data-modell="([^"]+)"', block)
        assert modell is not None, "Alarmzeile ohne data-modell - der Schluessel fehlt"
        if not attribute.get("prozent"):
            continue
        if (modell.group(1), anbieter, gesamt) in andere_laufzeit:
            mit_vorzeichen.append(
                (attribute.get("geraet"), anbieter, gesamt, attribute.get("prozent"))
            )
    assert not mit_vorzeichen, (
        f"{len(mit_vorzeichen)} Alarm-/Radarzeilen tragen ein Delta-"
        "Vorzeichen fuer eine Zahl, deren eigene Buendelzeile einen "
        f"anderen Zeitraum nennt: {mit_vorzeichen[:4]}"
    )


_PR_WESENTLICH_EURO = 15


def test_pr_eine_verschwundene_abweichung_traegt_ihren_grund(gw_seite):
    """BEFUND (hoch): 22 Abweichungen sind zum Strich geworden, ohne Grund.

    `report/geraete_view.py:1084` laesst die Luecke der Delta-Spalte
    ausdruecklich leer ("Strich wie die Buendelzeile - die Referenz
    existiert"). Seit P0-B-fix2 trifft das nicht mehr zu: die
    Buendelzeile zeigt dort "andere Laufzeit", die Katalogzeile den
    Strich, und der Strich heisst auf dieser Seite "kein Angebot" (A2).

    Gemessen am 21.09.2026 (gleicher Bestand, zwei Codestaende):
    `exporte/geraete-modell-tco.csv` verlor 22 von 57 Abweichungen
    (2aa7dbd -> ac80e83), und KEINE der 22 Zeilen traegt einen Grund in
    der Statusspalte - z. B. Apple iPhone 17 Pro Max 512 GB (Vodafone
    2.351,80 EUR): vorher "+341,74 € · +14,5 %", jetzt "–".

    Geprueft wird die Zusicherung des Exports selbst
    (`geraete_export.modell_tco_csv`): "Eine Zeile ohne Zahl ODER OHNE
    ABSTAND traegt den benannten Grund in der Statusspalte." Der Abstand ist
    der Euro-Betrag; das Prozent fehlt nur bei einem unwesentlichen Abstand
    (am Schnappschuss: iPhone 18 Pro 2048 GB, 10,95 EUR)."""
    pfad = Path(gw_seite["csv"]).parent / "geraete-modell-tco.csv"
    assert pfad.exists(), f"{pfad} fehlt - der Export wurde nicht gerendert"
    zeilen = list(
        _gw_csv.DictReader(
            pfad.read_text(encoding="utf-8-sig").splitlines(), delimiter=";"
        )
    )
    assert len(zeilen) >= 100, (
        f"nur {len(zeilen)} Modellzeilen im Export - der Lookup greift ins Leere"
    )
    stumm = [
        (
            z["Hersteller"],
            z["Modell"],
            z["Speicher GB"],
            z["Bester Anbieter"],
            z["TCO ab EUR"],
        )
        for z in zeilen
        if z["TCO ab EUR"].strip()
        and not z["Abweichung zu Vodafone EUR"].strip()
        and not (z["Status"] or "").strip()
    ]
    assert not stumm, (
        f"{len(stumm)} Modellzeilen mit Leitzahl, aber ohne Abweichung UND "
        f"ohne Grund in der Statusspalte: {stumm[:6]}"
    )
    ohne_prozent = [
        (z["Modell"], z["Speicher GB"], z["Abweichung zu Vodafone EUR"])
        for z in zeilen
        if z["Abweichung zu Vodafone EUR"].strip() and not z["Abweichung %"].strip()
    ]
    wesentlich_ohne_prozent = [
        z for z in ohne_prozent if abs(_gw_dezimal(z[2])) >= _PR_WESENTLICH_EURO
    ]
    assert not wesentlich_ohne_prozent, (
        f"wesentliche Abstände ohne Prozent: {wesentlich_ohne_prozent[:6]}"
    )


_PZ_TOLERANZ = _gw_Dez("0.01")

_PZ_CSV_ZEITRAUM = "Leitzahl-Zeitraum Monate"


def _pz_soll(b: dict, blaetter: dict) -> tuple:
    """(Leitzahl in Euro, Zeitraum H) aus den ROHFELDERN - oder (None, H).

    Zwei Formen, genau wie die Anbieter sie ausweisen:
      * zusammengelegter Monatsbetrag (`buendel_monatlich`, 1&1): Tarif und
        Geraet in EINER Rate ueber H Monate.
      * getrennt (`tarif_monatlich` + `geraet_monatsrate`): der Tarif in jedem
        Monat 1 bis H, dazu ALLE Geraeteraten der eigenen Laufzeit.
    H ist der groessere Wert aus Ratenlaufzeit und Tarifbindung (Datenkonzept
    Geraete 5.3). Fehlt ein Posten oder der Preis eines Monats, gibt es keine
    Summe (None, nie 0, nie geraten) - dieselbe Rechnung wie `_gw_leitzahl`.
    """
    cent, monate = _gw_leitzahl(b, blaetter)
    if cent is None:
        return None, monate
    return (_gw_Dez(cent) / 100).quantize(_gw_Dez("0.01"), rounding=_gw_HUP), monate


def _pz_zeilen(html: str) -> list[dict]:
    """Die Buendelzeilen eines Dokuments - Attribute und Etikett je Zeile."""
    zeilen = []
    for block in html.split('<details class="gr-bnd')[1:]:
        kopf = block[: block.find("</summary>")]

        def feld(muster, quelle=kopf):
            treffer = re.search(muster, quelle, re.S)
            return treffer.group(1) if treffer else None

        zeilen.append(
            {
                "anbieter": (feld(r'gr-bnd-name">([^<]*)<') or "")
                .replace("&amp;", "&")
                .strip(),
                "gesamt": feld(r'data-gesamt="([^"]*)"'),
                "schnitt": feld(r'data-schnitt="([^"]*)"'),
                "laufzeit_attr": feld(r'data-laufzeit="([^"]*)"'),
                "etikett": feld(r"Kosten über (\d+) Monate"),
            }
        )
    return zeilen


def test_pruefer_jede_leitzahl_der_seite_gegen_eine_eigene_rechnung(gw_seite):
    """Leitzahl, Zeitraum und O/Monat JEDER Buendelzeile, neu gerechnet.

    Gegenprobe gegen einen Test, dessen Lookup ins Leere laeuft: jede
    gerenderte Zeile MUSS im unabhaengig gerechneten Bestand einen
    Betragspartner finden (`ohne_partner` ist ein Fehlschlag, kein
    Ueberspringen), es muessen mehr als 400 Zeilen geprueft werden, und
    beide Zeitraeume des Bestands (24 UND 36) muessen vorkommen - sonst
    prueft der Test die interessante Haelfte nicht.
    """
    stand, blaetter, _db = _gw_rohdaten(gw_seite["bestand"])
    soll: dict[tuple, set] = {}
    for b in stand["buendel"]:
        betrag, monate = _pz_soll(b, blaetter)
        if betrag is None:
            continue
        soll.setdefault((b["anbieter"], betrag), set()).add(monate)
    assert len(soll) > 200, (
        f"nur {len(soll)} eigene Leitzahlen gerechnet - Rohdaten leer?"
    )

    zeilen = _pz_zeilen(gw_seite["buendel"]) + _pz_zeilen(gw_seite["geraete"])
    geprueft = 0
    zeitraeume: set = set()
    ohne_partner, falsches_etikett, falscher_schnitt = [], [], []
    for z in zeilen:
        if not z["gesamt"] or not z["etikett"]:
            continue
        betrag = _gw_Dez(z["gesamt"]).quantize(_gw_Dez("0.01"))
        moeglich = soll.get((z["anbieter"], betrag))
        if not moeglich:
            ohne_partner.append((z["anbieter"], z["gesamt"]))
            continue
        geprueft += 1
        monate = int(z["etikett"])
        zeitraeume.add(monate)
        if monate not in moeglich:
            falsches_etikett.append(
                (z["anbieter"], str(betrag), monate, sorted(moeglich))
            )
        schnitt = _gw_Dez(z["schnitt"] or "0")
        if abs(schnitt * monate - betrag) > _PZ_TOLERANZ * monate:
            falscher_schnitt.append((z["anbieter"], str(betrag), monate, z["schnitt"]))
    assert not ohne_partner, (
        f"{len(ohne_partner)} Buendelzeilen mit einer Summe, die die eigene "
        f"Rechnung nicht kennt: {ohne_partner[:6]}"
    )
    assert geprueft > 400, f"nur {geprueft} Zeilen geprueft - der Lookup greift nicht"
    assert {24, 36} <= zeitraeume, (
        f"nur die Zeitraeume {sorted(zeitraeume)} geprueft, nicht 24 UND 36"
    )
    assert not falsches_etikett, (
        "Etikett nennt einen Zeitraum, den die Summe nicht tragen kann: "
        f"{falsches_etikett[:6]}"
    )
    assert not falscher_schnitt, (
        f"O/Monat x Etikett-Zeitraum != Leitzahl: {falscher_schnitt[:6]}"
    )


def test_pruefer_kein_spaltenkopf_behauptet_24_ueber_einer_36_monats_zahl(gw_seite):
    """Der Spaltenkopf IST eine Aussage ueber jede Zahl unter ihm.

    Geprueft wird die Buendeltafel des Startmodells: nennt der Kopf der
    TCO-Spalte eine Monatszahl, dann muss JEDE Zeile unter ihm genau
    diesen Zeitraum tragen. Der Sortierknopf dieses Kopfes
    (`data-bsort="tco"`, app.js liest `data-gesamt`) stellt alle Summen
    der Spalte in EINEN Rang - ein Kopf, der einen Zeitraum behauptet,
    behauptet ihn damit fuer den ganzen Rang.

    GEMESSEN am 22.09.2026 (echter Render gegen den Bestand vom
    20.09.2026): 19 Buendelzeilen inline, alle 19 mit `data-gesamt` UND
    eigenem Etikett, 18 ueber 24 Monate und 1 ueber 36 (die 1&1-Zeile mit
    `buendel_monatlich`). Der Kopf lautet "nach den Kosten mit Tarif
    sortieren, getrennt nach Zeitraum" und nennt KEINE Monatszahl - das
    ist der Stand nach P0-B-z2 und der gewollte Zustand: der Kopf nennt
    die Spalte, die Zeile ihren Zeitraum.

    WARUM DIE PRUEFUNG SO GEBAUT IST (Befund vom 22.09.2026): vorher
    stand hier `assert not (fremde and behauptet == [_GW_HORIZONT])`.
    Nach z2 ist `behauptet` leer, also ist `behauptet == [24]` fuer immer
    falsch und der Assert konnte nicht mehr fallen - egal was in der
    Spalte steht. Er war ausserdem nur auf die eine Richtung gefasst:
    ein Kopf, der "36 Monate" ueber 24-Monats-Zeilen behauptet, kam
    durch. Geprueft wird jetzt die Aussage selbst, in beide Richtungen,
    mit zwei Gegenproben, die verhindern, dass sie gruen ins Leere
    laeuft: die Spalte muss Zeilen MIT Etikett haben, und sie muss
    MEHRERE Zeitraeume tragen (sonst koennte eine Monatszahl im Kopf
    ueberhaupt nicht widersprechen und der Test prueft nichts).
    """
    seite = gw_seite["geraete"]
    koepfe = re.findall(r'data-bsort="tco"[^>]*aria-label=\s*"([^"]*)"', seite)
    assert koepfe, "Sortierkopf der TCO-Spalte nicht gefunden - Lookup leer"

    spaltenzeilen = [z for z in _pz_zeilen(seite) if z["gesamt"]]
    assert spaltenzeilen, (
        "keine Buendelzeile mit data-gesamt in der Startansicht - der "
        "Lookup greift ins Leere und dieser Test wuerde sonst gruen "
        "nichts pruefen"
    )
    ohne_etikett = [
        (z["anbieter"], z["gesamt"]) for z in spaltenzeilen if not z["etikett"]
    ]
    assert not ohne_etikett, (
        f"{len(ohne_etikett)} von {len(spaltenzeilen)} Zeilen tragen eine "
        f"Summe ohne eigenen Zeitraum: {ohne_etikett[:6]} - am 22.09.2026 "
        "trugen alle 19 ihr Etikett. Ohne Etikett gilt wieder der Kopf "
        "fuer alle"
    )

    etiketten = {int(z["etikett"]) for z in spaltenzeilen}
    assert len(etiketten) > 1, (
        f"die Spalte traegt nur den Zeitraum {sorted(etiketten)}; am "
        "22.09.2026 standen dort 24 UND 36 Monate (18 zu 1). Mit einem "
        "einzigen Zeitraum kann ein Spaltenkopf nicht widersprechen und "
        "dieser Test prueft nichts - die Startansicht ist neu zu waehlen "
        "oder der Anker neu zu setzen, nicht der Assert aufzuweichen"
    )

    behauptet = {int(m) for kopf in koepfe for m in re.findall(r"(\d+) Monate", kopf)}
    widerspruch = sorted(etiketten - behauptet) if behauptet else []
    assert not widerspruch, (
        f"Spaltenkopf {koepfe[0]!r} behauptet {sorted(behauptet)} Monate, "
        f"in derselben Spalte stehen Zeilen mit {widerspruch} Monaten - "
        "und derselbe Knopf sortiert sie gemeinsam nach data-gesamt. Der "
        "Zeitraum gehoert an die Zeile, nicht an den Kopf"
    )


def test_pruefer_der_csv_kopf_widerspricht_nicht_seiner_zeitraum_spalte(gw_seite):
    """`geraete-tco.csv`: Kopf und Zeitraum-Spalte derselben Zeile.

    P0-B-h4 hat die Spalte "Leitzahl-Zeitraum Monate" ergaenzt, den Kopf
    der Wertspalte aber stehen gelassen. Eine Zeile, deren Zeitraum 36
    sagt, traegt ihre Summe damit unter "Kosten über 24 Monate EUR" -
    zwei Zahlen zum selben Zeitraum in derselben Zeile.

    GEPRUEFT WERDEN ALLE "Kosten über"-Spalten, nicht eine.

    Befund vom 22.09.2026: vorher nahm dieser Test
    `next(k for k in zeilen[0] if k.startswith("Kosten über"))` - also die
    ERSTE solche Spalte in Spaltenreihenfolge. Seit z3 gibt es ZWEI:
      * "Kosten über 24 Monate EUR (eigener Zeitraum)" - gefuellt nur
        dort, wo der eigene Zeitraum wirklich 24 ist (763 von 837),
        sonst eine benannte Luecke (74). Diese Spalte ist stimmig.
      * "Kosten über 24 Monate EUR" - fuer JEDE der 837 Zeilen gefuellt,
        auch fuer die 74 mit eigenem Zeitraum 36. z3 hat sie wortgleich
        stehen gelassen, weil `test_geraete_tco_csv_gegen_die_eigene_
        rechnung` sie als Fremdschluessel liest.
    Weil die neue Spalte in der Reihenfolge davor stand, pruefte `next()`
    ab z3 nur noch die stimmige und meldete 0 Widersprueche - waehrend
    dieselbe Datei 74 trug. Ein Lookup, der an der Spaltenreihenfolge
    haengt und am Fehler vorbeigreift, ist kein Nachweis; deshalb pruefen
    wir jetzt JEDE solche Spalte.

    SEIT DEM 22.09.2026 (Lead) gibt es die widersprechende Spalte nicht
    mehr. Der Export legt jede Summe in den Kopf, der fuer sie WAHR ist:
    "Kosten über 24 Monate EUR" nur bei Zeitraum 24 (763 von 837),
    "Kosten über die Bündellaufzeit EUR" bei jedem anderen (74), daneben
    "Leitzahl-Zeitraum Monate". Der Sonderzweig, der den bekannten
    Widerspruch als exakte Gleichheit festhielt, ist damit entfallen -
    genau so, wie er es selbst vorgesehen hatte.

    ZWEI RICHTUNGEN, weil eine allein billig zu erfuellen waere:
      * Kein Kopf, der eine Monatszahl nennt, traegt eine Zahl mit
        anderem Zeitraum.
      * Keine Zeile verliert dabei ihren Wert, und keine traegt ihn unter
        zwei Koepfen. Ohne das waere der erste Punkt auch mit einem
        Export gruen, der die 74 Zahlen einfach weglaesst.

    WAS ZU TUN IST, WENN DIESER TEST FAELLT: Es ist ein Fehler im Export,
    kein Anker, der nachgezogen werden muss. Die Meldung nennt Anbieter
    und Zeitraum der betroffenen Zeilen.
    """
    zeilen = list(
        _gw_csv.DictReader(
            gw_seite["csv"].read_text(encoding="utf-8-sig").splitlines(), delimiter=";"
        )
    )
    assert zeilen, "geraete-tco.csv ist leer - Lookup greift nicht"
    spalten = [k for k in zeilen[0] if k.startswith("Kosten über")]
    assert spalten, (
        f"keine 'Kosten über'-Spalte in {sorted(zeilen[0])} - der Lookup "
        "greift ins Leere und dieser Test wuerde sonst gruen nichts "
        "pruefen"
    )
    assert _PZ_CSV_ZEITRAUM in zeilen[0], (
        f"Spalte {_PZ_CSV_ZEITRAUM!r} fehlt - ohne den Zeitraum JE ZEILE "
        "ist kein Widerspruch zum Kopf messbar"
    )

    fremde_zeilen = [
        z
        for z in zeilen
        if (z[_PZ_CSV_ZEITRAUM] or "").strip()
        and int(z[_PZ_CSV_ZEITRAUM]) != _GW_HORIZONT
    ]
    assert fremde_zeilen, (
        f"keine der {len(zeilen)} Zeilen traegt einen Zeitraum ungleich "
        f"{_GW_HORIZONT}; am 22.09.2026 waren es 74 von 837 (1&1, "
        "Buendelbetrag ueber 36 Monate). Ohne sie prueft dieser Test "
        "nichts - Anker mit Begruendung neu setzen, nicht aufweichen"
    )

    mit_zahl_im_kopf = [k for k in spalten if re.search(r"\d", k)]
    assert mit_zahl_im_kopf, (
        f"keine 'Kosten über'-Spalte nennt eine Monatszahl ({spalten}) - "
        "dann prueft die Schleife nichts; Anker mit Begruendung neu setzen"
    )
    for kopf in mit_zahl_im_kopf:
        kopf_monate = int(re.search(r"(\d+)", kopf).group(1))
        fremd = [
            (z["Anbieter"], z[_PZ_CSV_ZEITRAUM], z[kopf])
            for z in zeilen
            if (z[_PZ_CSV_ZEITRAUM] or "").strip()
            and int(z[_PZ_CSV_ZEITRAUM]) != kopf_monate
            and (z[kopf] or "").strip()
        ]
        assert not fremd, (
            f"{len(fremd)} Zeilen tragen ihre Summe unter dem Kopf "
            f"{kopf!r}, obwohl ihre eigene Zeitraum-Spalte einen anderen "
            f"Wert nennt: {fremd[:4]}"
        )

    stand, blaetter, _db = _gw_rohdaten(gw_seite["bestand"])
    luecke_je_schluessel: dict[tuple, set] = {}
    for b in stand["buendel"]:
        schluessel = (
            b["anbieter"],
            b.get("sku_id") or "",
            b.get("tarif_name") or "",
            str(b.get("laufzeit_monate") or ""),
        )
        luecke_je_schluessel.setdefault(schluessel, set()).add(
            _gw_leitzahl(b, blaetter)[0] is None
        )
    stumm, unbenannt = [], []
    for z in zeilen:
        if not (z[_PZ_CSV_ZEITRAUM] or "").strip() or z["Art"] != "Bündel":
            continue
        if any((z[k] or "").strip() for k in spalten):
            continue
        schluessel = (z["Anbieter"], z["SKU-ID"], z["Tarif"], z["Laufzeit Monate"])
        if luecke_je_schluessel.get(schluessel) != {True}:
            stumm.append((z["Anbieter"], z[_PZ_CSV_ZEITRAUM], z["Tarif"]))
        elif not (z.get("Lücke") or "").strip():
            unbenannt.append((z["Anbieter"], z["Tarif"], z["Status"]))
    assert not stumm, (
        f"{len(stumm)} Zeilen tragen einen Zeitraum, aber in keiner "
        f"'Kosten über'-Spalte eine Zahl, obwohl die eigene Rechnung eine "
        f"kennt: {stumm[:4]}"
    )
    assert not unbenannt, (
        f"{len(unbenannt)} Zeilen ohne Zahl nennen ihre Luecke nicht (Spalte Lücke): "
        f"{unbenannt[:4]}"
    )
    doppelt = [
        (z["Anbieter"], z[_PZ_CSV_ZEITRAUM])
        for z in zeilen
        if sum(1 for k in spalten if (z[k] or "").strip()) > 1
    ]
    assert not doppelt, (
        f"{len(doppelt)} Zeilen tragen dieselbe Summe unter zwei Koepfen "
        f"mit verschiedenem Zeitraum: {doppelt[:4]}"
    )


def test_der_name_der_grafik_nennt_die_zeitraeume_die_darin_liegen(gw_seite):
    """Der zugaengliche Name der Grafik-Sektion gegen ihre Kurven.

    P0-B (22.09.2026): `_geraete_zeitreihe.html.j2` trug den Namen FEST -
    "Kosten über 24 Monate je Messtag und Anbieter" -, auch wenn im Bild
    eine 36-Monats-Kurve lag: wer die Seite sieht, las am Kurvenende "36
    Mon.", wer sie hoert, bekam "Kosten über 24 Monate" (Clean Code 7).

    Anker neu gesetzt mit Datenkonzept Geräte Schritt 2 (Teil B): jede Ansicht
    ist EINE Ratenlaufzeit N und traegt EINEN Zeitraum H = max(N, 24) - zwei
    Zeitraeume in einem Bild gibt es nicht mehr (24 Raten nie neben 36). Der
    Name jeder Grafik nennt deshalb H und N, und kein Kurvenetikett nennt
    einen anderen Zeitraum. Gegenprobe eingebaut: der Bestand traegt Bilder
    mit 24 und mit 36 Raten, sonst prueft der Test nur einen Fall.
    """
    gesehen, falsch = set(), []
    for teil in gw_seite["fragment"].split('<div class="gr-zr-lager"')[1:]:
        kopf = re.match(r'[^>]*data-laufzeit="(\d+)"', teil)
        name = re.search(r'gr-zr-graph"\s+aria-label="([^"]*)"', teil, re.S)
        if kopf is None or name is None or "<svg" not in teil:
            continue
        raten = int(kopf.group(1))
        monate = max(raten, 24)
        genannt = " ".join(name.group(1).split())
        im_bild = {int(z) for z in re.findall(r">(\d+) Mon\.?<", teil)}
        if f"Kosten über {monate} Monate mit {raten} Raten" not in genannt or (
            im_bild - {monate}
        ):
            falsch.append((raten, genannt, sorted(im_bild)))
        gesehen.add(raten)
    assert {24, 36} <= gesehen, (
        f"Bilder nur mit {sorted(gesehen)} Raten - dann prueft dieser Test nur "
        "einen Fall. Anker mit Begruendung neu setzen, nicht aufweichen"
    )
    assert not falsch, (
        f"{len(falsch)} Grafiken nennen einen anderen Zeitraum als ihre Kurven: "
        f"{falsch[:3]}"
    )
