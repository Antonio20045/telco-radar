"""1&1: GERAETERATEN gegen MINDESTBINDUNG - die Gegenprobe des Rasters.

Die Geraeteraster (`/smartphones-<tarif>`) bewerben seit dem 20.11.2026
die Flex-Finanzierung: `data-hardware-months="48"` auf JEDER der 41
Kacheln, iPhone 17 Pro 37,99 statt 59,99 (Geraete-Lauf 44728882384).
Diese Zahl ist NICHT die Mindestbindung - die bleibt laut Datalayer der
Geraeteseite (`tariff.contractduration`) 24 - sondern die Zahl der
GERAETERATEN des beworbenen Angebots. Die Gegenprobe in
`einsundeins.ergaenze_tarifstufen` hat sie bis dahin gegen
`laufzeit_monate` des Satzes geprueft und deshalb ALLE 41 Geraete
verworfen ("41 Geraete ohne passende Gegenprobe", keine einzige
hergeleitete Tarifstufe).

Auf der Geraeteseite steht dieselbe Zahl nur mittelbar: als
`hardwareTotalPrice / hardwarePricePerMonth` je Stufe der Preiskarte
("36 + 12 Monate Flex" = 1200,00 / 25,00 = 48 Raten). Genau darueber
laesst sich ein Rasterpreis gegen die Geraeteseite pruefen - und nur
dafuer liest `geraeteraten_preise` auch "flex". VEROEFFENTLICHT wird
weiter allein der Betrag aus `einsundeins._fixpreis` zur Mindestbindung
plus Tarifaufschlag; eine "flex"-Zahl ist hier Beleg, nie Preis
(`gegenwert`).

ANNAHME UND WAECHTER (E1, Pruefung PR 164): der Tarifaufschlag S->M wird
am FLEX-48-Raster gemessen (`ergaenze_tarifstufen` in `einsundeins.py`),
aber auf den FIX-24-Preis des Default-Tarifs aufgeschlagen. Das setzt
voraus, dass der Aufschlag in beiden Finanzierungsstufen gleich hoch
ist - das ist aus einer Geraeteseite NICHT nachpruefbar, sie nennt immer
nur ihren eigenen Standardtarif. `waechter_listenpreis` prueft deshalb
gegen eine zweite, unabhaengige Groesse: die Listenpreise OHNE Geraet
aus der Tarifuebersicht (`listenpreise_je_tarif`, `data-tariff-price-
hint`, Markup seit 20.11.2026). Weicht die Listenpreisdifferenz um mehr
als 1 Cent vom Rasteraufschlag ab, oder nennt die Uebersicht einen der
beiden Tarife nicht, wird dieser Tarif NICHT hergeleitet - lieber kein
Preis als ein fuer alle Geraete gleich falscher. GRENZE: traegt die
Uebersicht das Attribut ueberhaupt nicht (aeltere Fixtures vor dem
20.11.2026 kennen es nicht), gibt es keine belegte Zweitgroesse - der
Waechter laesst dann durch, statt jede Herleitung zu blockieren.
"""

from __future__ import annotations

import html as html_modul
import json
import re

from ...tarif_model import zahl

_STUFEN = ("fix", "flex")

_TARIFHINT_RE = re.compile(r'data-tariff-price-hint="([^"]*)"')


def flache_tarifrate(stufe: dict, monate: int) -> float | None:
    """Die Tarifrate einer Stufe, wenn sie ueber `monate` FLACH belegt ist.

    Belegt heisst: der erste Eintrag von `tariffMonthlyPrices` beginnt in
    Monat 1, nennt denselben Betrag wie `tariffPricePerMonth` und deckt
    mindestens `monate` (`end` 0 oder fehlend = bis auf Weiteres). Sonst
    `None` - lieber keine Zahl als eine 24+12-Zahl (Kopf von
    `einsundeins.py`).
    """
    tarifrate = zahl(str(stufe.get("tariffPricePerMonth")))
    monatspreise = stufe.get("tariffMonthlyPrices")
    if tarifrate is None or not monatspreise:
        return None
    erster = monatspreise[0]
    flach_bis = erster.get("end")
    deckt = flach_bis in (0, None) or flach_bis >= monate
    betrag = round(float(erster.get("amount", -1)), 2)
    if erster.get("begin") != 1 or not deckt or betrag != round(tarifrate, 2):
        return None
    return tarifrate


def _raten(stufe: dict, hardwarerate: float) -> int | None:
    """Die Zahl der Geraeteraten einer Stufe; `None`, wenn sie nicht glatt
    aufgeht (dann ist `hardwareTotalPrice` keine Ratensumme)."""
    gesamt = zahl(str(stufe.get("hardwareTotalPrice")))
    if gesamt is None:
        return None
    raten = gesamt / hardwarerate
    if abs(raten - round(raten)) > 1e-6 or round(raten) <= 0:
        return None
    return int(round(raten))


def geraeteraten_preise(karteneintrag: dict) -> dict:
    """{Zahl der Geraeteraten: Monatsbetrag} EINER Variante der Preiskarte.

    Gelesen werden beide Stufen jeder Finanzierungsdauer, aber nur mit
    ueber ihre eigene Ratenzahl flacher Tarifrate (Modulkopf). Nennen zwei
    Stufen dieselbe Ratenzahl mit verschiedenen Betraegen, ist das
    mehrdeutig - diese Ratenzahl entfaellt ganz, statt die erste gesehene
    zu uebernehmen.
    """
    gesehen: dict = {}
    for stufen in (karteneintrag or {}).values():
        if not isinstance(stufen, dict):
            continue
        for name in _STUFEN:
            stufe = stufen.get(name)
            if not isinstance(stufe, dict):
                continue
            hardwarerate = zahl(str(stufe.get("hardwarePricePerMonth")))
            if not hardwarerate:
                continue
            raten = _raten(stufe, hardwarerate)
            tarifrate = flache_tarifrate(stufe, raten) if raten else None
            if raten is None or tarifrate is None:
                continue
            gesehen.setdefault(raten, set()).add(round(hardwarerate + tarifrate, 2))
    return {
        raten: next(iter(betraege))
        for raten, betraege in gesehen.items()
        if len(betraege) == 1
    }


def listenpreise_je_tarif(text: str) -> dict:
    """{Tarifname: Listenpreis} OHNE Geraet, aus den `data-tariff-price-
    hint`-Attributen einer Tarifuebersicht (Markup seit 20.11.2026; in
    aelteren Uebersichten fehlt das Attribut, dann liefert diese Funktion
    ein leeres Dict).

    Listenpreis ist `tariffDiscount`, wenn gesetzt - die Uebersicht
    traegt dort die Zahl VOR einem Rabatt (All-Net-Flat S ohne Geraet:
    14,99 -> 9,99, `tariffPricePerMonth` ist dann 9,99,
    `tariffDiscount` 14,99). Sonst gilt `tariffPricePerMonth` selbst.
    Nennt dieselbe Tarifbezeichnung innerhalb des Textes widerspruechliche
    Betraege, gilt sie als nicht lesbar und fehlt im Ergebnis.
    """
    gefunden: dict = {}
    for roh in _TARIFHINT_RE.findall(text or ""):
        try:
            hinweis = json.loads(html_modul.unescape(roh))
        except (json.JSONDecodeError, TypeError):
            continue
        name = hinweis.get("tariffName")
        if not name:
            continue
        rabatt = hinweis.get("tariffDiscount")
        preis = rabatt if rabatt is not None else hinweis.get("tariffPricePerMonth")
        if preis is None:
            continue
        preis = round(float(preis), 2)
        bisher = gefunden.get(name, preis)
        gefunden[name] = preis if bisher == preis else None
    return {name: preis for name, preis in gefunden.items() if preis is not None}


def waechter_listenpreis(
    listenpreise: dict, basistarif: str, tarif: str, aufschlaege: dict
) -> dict:
    """Vergleicht den Rasteraufschlag `basistarif` -> `tarif` gegen die
    Differenz der Listenpreise ohne Geraet derselben zwei Tarife - die
    zweite, unabhaengige Groesse aus dem Modulkopf (E1).

    `listenpreise` ist leer, wenn die Tarifuebersicht gar kein
    `data-tariff-price-hint` traegt (Markup vor dem 20.11.2026, siehe
    `listenpreise_je_tarif`) - dann gibt es keine belegte Zweitgroesse,
    gegen die zu pruefen waere, und der Waechter laesst durch (`ok`).
    Traegt die Uebersicht das Attribut, aber nicht fuer `basistarif` oder
    `tarif`, oder weicht ein Aufschlagswert um mehr als 1 Cent von der
    Listenpreisdifferenz ab, kommt `{"ok": False, "grund": ...}` - der
    Aufrufer leitet den Tarif dann nicht her. Sonst
    `{"ok": True, "grund": "", "differenz_cent": ...}`.
    """
    if not listenpreise:
        return {"ok": True, "grund": "", "differenz_cent": None}
    default = listenpreise.get(basistarif)
    ziel = listenpreise.get(tarif)
    if default is None or ziel is None:
        return {
            "ok": False,
            "grund": "Listenpreis nicht lesbar",
            "differenz_cent": None,
        }
    differenz_cent = round((ziel - default) * 100)
    unstimmig = sorted(
        wert for wert in set(aufschlaege.values()) if abs(wert - differenz_cent) > 1
    )
    if unstimmig:
        return {
            "ok": False,
            "grund": (
                f"Rasteraufschlag {unstimmig[0] / 100:.2f} != "
                f"Listenpreisdifferenz {differenz_cent / 100:.2f}"
            ),
            "differenz_cent": differenz_cent,
        }
    return {"ok": True, "grund": "", "differenz_cent": differenz_cent}


def waechter_verwirft(
    log, listenpreise: dict, basistarif: str, tarif: str, aufschlaege: dict
) -> bool:
    """`waechter_listenpreis` plus Protokoll: `True`, wenn `tarif` deshalb
    NICHT hergeleitet werden darf - der Aufrufer ueberspringt ihn dann."""
    if not aufschlaege:
        return False
    urteil = waechter_listenpreis(listenpreise, basistarif, tarif, aufschlaege)
    if urteil["ok"]:
        return False
    log.warning(
        "1&1: %s - Wächter verwirft den Tarif (%s), %d betroffene Geräte - "
        "keine Tarifstufe hergeleitet",
        tarif,
        urteil["grund"],
        len(aufschlaege),
    )
    return True


def lies_uebersichten(
    hole, kopfzeilen, uebersichten, hole_text, raster_adressen_fn, details_fn
):
    """Liest alle Tarifuebersichten: Rasteradressen, Tarifdetails, Listenpreise
    (`tarifraster_adressen`, `tarifdetails_je_tarif`, `listenpreise_je_tarif`)."""
    raster_adressen: list = []
    details: dict = {}
    listenpreise: dict = {}
    for uebersicht in uebersichten:
        text = hole_text(hole, kopfzeilen, uebersicht)
        if text is None:
            continue
        for adresse in raster_adressen_fn(text, uebersicht):
            if adresse not in raster_adressen:
                raster_adressen.append(adresse)
        for name, wert in details_fn(text, uebersicht).items():
            details.setdefault(name, wert)
        listenpreise = {**listenpreise_je_tarif(text), **listenpreise}
    return raster_adressen, details, listenpreise


def gegenwert(vorher: dict | None, raten: int | None) -> float | None:
    """Der Betrag, gegen den ein Rasterpreis zu pruefen ist - oder `None`.

    Zwei Belege, und immer nur EINER von beiden gilt:

    * Nennt die Geraeteseite einen eigenen angezeigten Preis, der von
      ihrem Preiskarten-Betrag ABWEICHT, dann gilt dieser - er enthaelt
      dasselbe wie die Rasterkachel (am 29.09.2026 die Galaxy Buds am
      S26 Ultra: 44,99 angezeigt, 42,99 Buendel).
    * Sonst (seit K1 der Regelfall: `_angezeigter_preis` faellt auf den
      Preiskarten-Betrag zurueck) gilt der Betrag der Preiskarte zu
      GENAU der Ratenzahl der Kachel.
    """
    if not vorher or raten is None:
        return None
    angezeigt = vorher.get("angezeigt_monatlich")
    betrag = vorher.get("buendel_monatlich")
    if angezeigt is None:
        return None
    if betrag is None or round(angezeigt * 100) != round(betrag * 100):
        return angezeigt
    return (vorher.get("raten_preise") or {}).get(raten)
