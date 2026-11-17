"""Portfolio gegen Vodafone: welche Geräte hat ein Wettbewerber, Vodafone nicht.

Ziel 3 (Antonio, 05.11.2026), gebaut auf 1a: Nur eine BELEGTE Lücke ist eine
Portfolio-Lücke. „Gerät gibt es bei Anbieter X nicht" ist meist falsch, weil
nur die richtige Seite nicht gefunden wurde; ohne Beleg ist es eine Messlücke
und zählt nie als Portfolio-Lücke.

EINTEILUNG je Paar (Wettbewerber W, Vodafone) und aktuellem Gerät
  beide        beide führen einen frischen Preis: kein Unterschied
  nur W        W führt es, Vodafone nicht, und für Vodafone steht eine gültige
               belegte Lücke (`art: nicht_im_portfolio`, `beleg`, heute <= `bis`)
  nur Vodafone dasselbe mit vertauschten Rollen
  nicht gemessen  genau eine Seite führt einen frischen Preis, für die andere
               gibt es keinen gültigen Beleg (nie belegt oder abgelaufen)
  (nichts)     keine Seite führt einen frischen Preis: nicht vergleichbar

„Führt einen Preis": mindestens eine neue, frische, nicht geschätzte Karte mit
Gesamtpreis, egal in welcher Laufzeit und welchem Tarifband. Eine veraltete
Karte widerlegt einen jüngeren Beleg nicht.
Ein Beleg zählt nur mit einer Sortiments-Aussage im `grund` (`BELEG_AUSSAGEN`):
„derzeit nicht verfügbar“ heißt nur „gerade nicht lieferbar“, nicht „nicht im
Portfolio“, und bleibt eine Messlücke. Ohne belegten Unterschied eines Paars
steht dessen Messlücken-Liste offen (`offen_zeigen`). Die Geräte sind die aktuellen
Modelle der Herstellergrafik (`geraete_hersteller.aktuelle_geraete`). Alles
kommt aus dem Seiten-Build (Bündel der Seite, `config/geraete_abdeckung.yaml`);
es gibt keinen Abruf. Ein Ausfall steht als `fehler`, nie als leere Liste.

DARSTELLUNG: Kacheln, Gruppen und Sätze baut
`geraete_portfolio_anzeige.py`; dieses Modul teilt nur ein.

ZWEITE BELEGQUELLE (P2, 13.11.2026): fehlt eine gültige Config-Lücke, zieht
`erfassung_je` die `erfassung`-Sätze eines Modells heran (`klick_erfassung`,
von `geraete_view` je Modell gesetzt) - nur Sätze der Form
`SATZ_NICHT_IM_ANGEBOT`: eine am Tag X ganz gelesene Geräteübersicht, die das
Gerät nicht zeigt. Diese Quelle trägt kein Datum einer befristeten Prüfung und
keinen Screenshot-Link; `_beleg_text` zeigt dafür einen Auszug statt eines
Links, ohne „gültig bis“.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

from ..analyze import buendel_abdeckung
from ..analyze.geraete_bilder import ORDNER as BILD_ORDNER
from ..analyze.geraete_bilder import bilder_pfad, lade_bilder
from ..analyze.klick_erfassung import SATZ_NICHT_IM_ANGEBOT, TRENNER
from . import geraete_hersteller
from .anbieter_farben import legendenname, slug_fuer
from .geraete_hersteller import aktuelle_geraete
from .geraete_hersteller_text import EIGEN
from .geraete_portfolio_anzeige import (
    KACHELN_SICHTBAR,
    beleg_text,
    fehlt_satz,
    gruppiert,
    in_pruefung_satz,
    kacheln,
    kontext,
    kopfzeile,
    rest,
)
from .geraete_rechenweg import ANBIETER_FOLGE
from .geraete_sortiment import abdeckung_pfad, beleg_fuer

log = logging.getLogger(__name__)

BILDER_ORDNER = Path(__file__).parent / "templates" / "static" / BILD_ORDNER
"""Wo die Produktfotos im Repo liegen; von dort spiegelt `statik.kopiere()`."""

_ERFASSUNG_MUSTER = re.compile(
    re.escape(SATZ_NICHT_IM_ANGEBOT)
    .replace(re.escape("{anbieter}"), ".+")
    .replace(re.escape("{datum}"), r"(?P<datum>\d{2}\.\d{2}\.\d{4})")
)

STANDARD = "Telekom"
PREIS, ALT, IN_PRUEFUNG = "preis", "alt", "in_pruefung"
_RANG = {PREIS: 2, IN_PRUEFUNG: 1, ALT: 0}
REGEL = (
    "Als Lücke zählt nur, was am Original belegt ist (Screenshot, geprüft und "
    "befristet); fehlt ein Preis ohne gültigen Beleg, ist das eine Messlücke und "
    "zählt nicht als Portfolio-Lücke."
)


def staende(tco_modelle: list[dict]) -> dict[str, dict[str, str]]:
    """{device_id: {Anbieter: PREIS | IN_PRUEFUNG | ALT}} aus den Karten der Seite.

    PREIS: neue, frische, nicht geschätzte Karte mit Gesamtpreis. IN_PRUEFUNG:
    keine frische Karte, aber eine in Quarantäne (`geraete_preisstand.in_pruefung`)
    - der Anbieter führt das Gerät nachweislich, nur der Preis steht noch nicht
    fest; P3 (13.11.2026): das darf nie als „kein Beleg vor" erscheinen. ALT: es
    gibt Karten, aber keine davon trägt einen frischen Preis oder eine Quarantäne.
    Wiederaufgearbeitete Karten zählen nicht."""
    aus: dict[str, dict[str, str]] = {}
    for modell in tco_modelle or []:
        je = aus.setdefault(modell.get("device_id") or "", {})
        for karte in modell.get("karten") or []:
            if (karte.get("zustand") or "neu") != "neu":
                continue
            anbieter = karte.get("anbieter")
            frisch = (
                karte.get("gesamt") is not None
                and karte.get("frisch", True)
                and not karte.get("naeherung")
                and karte.get("zaehlt", True)
            )
            if frisch:
                stand = PREIS
            elif karte.get("quarantaene"):
                stand = IN_PRUEFUNG
            else:
                stand = ALT
            bisher = je.get(anbieter)
            if bisher is None or _RANG[stand] > _RANG[bisher]:
                je[anbieter] = stand
    return aus


def _erfassung_datum(satz: str):
    """Das Datum aus einem `SATZ_NICHT_IM_ANGEBOT`-Satz, `None` ohne Treffer."""
    treffer = _ERFASSUNG_MUSTER.fullmatch(satz)
    if not treffer:
        return None
    tag, monat, jahr = (int(teil) for teil in treffer["datum"].split("."))
    try:
        return date(jahr, monat, tag)
    except ValueError:
        return None


def erfassung_je(
    tco_modelle: list[dict], erfassung_roh: dict[str, str] | None = None
) -> dict[str, dict[str, dict]]:
    """{device_id: {Anbieter: Beleg}} aus dem UNGEFILTERTEN Erfassungs-Speicher
    (`tco_db.erfassung`; Schlüssel "<Anbieter>|<device_id>" für ein Gerät oder
    nur "<Anbieter>" für alle Geräte dieses Anbieters, siehe
    `klick_erfassung.ohne_karte`).

    Anders als die Gerätekarte (die über `klick_erfassung.ohne_karte` einen
    Erfassungssatz verwirft, sobald irgendeine Karte - auch eine veraltete -
    einen Betrag trägt) zählt der Portfolio-Vergleich Lücken über FRISCHE
    Karten (`staende`, PREIS vs. ALT): eine veraltete Karte mit Betrag darf
    einen Erfassungsbeleg hier nicht verdecken, deshalb wird nicht nach Karten
    gefiltert.

    Nur Sätze der Form `SATZ_NICHT_IM_ANGEBOT` zählen: eine an einem Tag ganz
    gelesene Geräteübersicht, die das Gerät nicht zeigt - dieselbe
    Sortiments-Aussage wie die Belege aus `config/geraete_abdeckung.yaml`, nur
    ohne Screenshot-Link (`_beleg_text` zeigt dann einen Auszug statt eines
    Links). Andere Erfassungsgründe (Seite gesperrt, nur ein Speicher gelesen)
    sagen nichts über das Sortiment und zählen nicht."""
    erfassung_roh = erfassung_roh or {}
    eigene = {a: s for a, s in erfassung_roh.items() if TRENNER not in a}
    aus: dict[str, dict[str, dict]] = {}
    for modell in tco_modelle or []:
        device_id = modell.get("device_id") or ""
        je_anbieter = dict(eigene)
        for schluessel, satz in erfassung_roh.items():
            anbieter, _, geraet = schluessel.partition(TRENNER)
            if geraet and geraet == device_id:
                je_anbieter[anbieter] = satz
        for anbieter, satz in je_anbieter.items():
            geprueft = _erfassung_datum(satz)
            if geprueft is None:
                continue
            aus.setdefault(device_id, {})[anbieter] = {
                "grund": satz,
                "geprueft": geprueft,
            }
    return aus


def wettbewerber_mit_daten(staende_je: dict, geraete: list) -> list[str]:
    """Anbieter außer Vodafone mit mindestens einem frischen Preis bei einem
    aktuellen Gerät: die festen Spalten zuerst, weitere nach Name."""
    ids = {g.device_id for g in geraete}
    da = {
        a
        for d, je in staende_je.items()
        if d in ids
        for a, s in je.items()
        if s == PREIS and a != EIGEN
    }
    fest = [a for a in ANBIETER_FOLGE if a in da]
    return fest + sorted(da - set(fest))


def _paar(
    w: str,
    geraete: list,
    staende_je: dict,
    belege: dict,
    erfassung_je_geraet: dict,
    heute: str,
    bilder: dict[str, str],
) -> dict:
    nur_w: list[dict] = []
    nur_v: list[dict] = []
    offen: list[dict] = []
    beide = 0
    for g in geraete:
        je = staende_je.get(g.device_id, {})
        hat_w, hat_v = je.get(w) == PREIS, je.get(EIGEN) == PREIS
        if hat_w and hat_v:
            beide += 1
        if hat_w == hat_v:
            continue
        fehlt = EIGEN if hat_w else w
        beleg, grund = beleg_fuer(belege, fehlt, g.device_id, heute)
        if beleg is None:
            erfasst = erfassung_je_geraet.get(g.device_id, {}).get(fehlt)
            if erfasst is not None:
                beleg, grund = erfasst, ""
        zeile = {
            "hersteller": g.hersteller,
            "name": g.modell,
            "device_id": g.device_id,
            "bild": bilder.get(g.device_id),
        }
        fuehrt = w if hat_w else EIGEN
        if beleg:
            (nur_w if hat_w else nur_v).append({**zeile, "beleg": beleg_text(beleg)})
        elif je.get(fehlt) == IN_PRUEFUNG:
            offen.append(
                {
                    **zeile,
                    "fehlt": fehlt,
                    "grund": IN_PRUEFUNG,
                    "satz": in_pruefung_satz(fuehrt, fehlt),
                }
            )
        else:
            offen.append(
                {
                    **zeile,
                    "fehlt": fehlt,
                    "grund": grund,
                    "satz": fehlt_satz(fuehrt, fehlt, grund),
                }
            )
    return {
        "name": w,
        "slug": slug_fuer(w),
        "legende": legendenname(w),
        "nur_w": kacheln(nur_w),
        "nur_v": kacheln(nur_v),
        "mehr_w": rest(nur_w),
        "mehr_v": rest(nur_v),
        "offen": gruppiert(offen),
        "n_w": len(nur_w),
        "n_v": len(nur_v),
        "n_offen": len(offen),
        "beide": beide,
        "kopf": kopfzeile(w, len(nur_w), len(nur_v)),
        "kontext": kontext(len(nur_w) + len(nur_v), len(offen)),
        "offen_zeigen": not (nur_w or nur_v),
    }


def fehlende_anbieter(paare: list[dict]) -> str:
    """Satz über Anbieter ohne Paar (1&1, Händler): kein frischer, gezählter
    Preis bei aktuellen Modellen. Leer, wenn keiner fehlt."""
    da = {p["name"] for p in paare}
    namen = [a for a in geraete_hersteller.WETTBEWERBER if a not in da]
    if all(a in ANBIETER_FOLGE for a in da):
        namen.append("Händler")
    if not namen:
        return ""
    wer = namen[0] if len(namen) == 1 else f"{', '.join(namen[:-1])} und {namen[-1]}"
    return (
        f"{wer} {'fehlt' if len(namen) == 1 else 'fehlen'} noch: bei den aktuellen "
        "Modellen liegt dort kein frischer, gezählter Preis vor, daher wird dort "
        "nicht verglichen."
    )


def berechne(
    tco_modelle: list[dict],
    katalog,
    belege: dict,
    heute: str,
    erfassung_roh: dict[str, str] | None = None,
    bilder: dict[str, str] | None = None,
) -> dict:
    """Reine Rechnung: alle Paare gegen Vodafone."""
    geraete = aktuelle_geraete(katalog)
    je = staende(tco_modelle)
    erf = erfassung_je(tco_modelle, erfassung_roh)
    paare = [
        _paar(w, geraete, je, belege, erf, heute, bilder or {})
        for w in wettbewerber_mit_daten(je, geraete)
    ]
    namen = [p["name"] for p in paare]
    return {
        "fehler": "",
        "leer": not paare,
        "stand": heute,
        "paare": paare,
        "grenze": KACHELN_SICHTBAR,
        "standard": STANDARD if STANDARD in namen else (namen[0] if namen else ""),
        "regel": REGEL,
        "fehlende": fehlende_anbieter(paare),
        "geraete": len(geraete),
        "belege": len(belege),
    }


def ansicht(
    state_dir,
    tco: dict,
    katalog,
    heute: str,
    erfassung_roh: dict[str, str] | None = None,
) -> dict:
    """Der Teil-Kontext der Seite; ein Ausfall steht als `fehler`.

    Ist die Belegliste nicht lesbar, ist jede Lücke eine Messlücke - die
    sichere Richtung - und der Ausfall wird genannt."""
    belege: dict = {}
    pfad = abdeckung_pfad(state_dir)
    hinweis = ""
    try:
        belege = buendel_abdeckung.lade_pflicht(pfad)["belege"]
    except (OSError, ValueError, KeyError, AttributeError) as exc:
        log.exception("Belegliste der Portfolio-Ansicht nicht lesbar")
        hinweis = f"Belegliste nicht lesbar ({type(exc).__name__}): keine Lücke belegt"
    bilder = lade_bilder(bilder_pfad(state_dir), BILDER_ORDNER)
    try:
        ergebnis = berechne(
            (tco or {}).get("modelle") or [],
            katalog,
            belege,
            heute,
            erfassung_roh,
            bilder,
        )
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        log.exception("Portfolio-Ansicht nicht aufbereitbar")
        return {"fehler": f"{type(exc).__name__}: {exc}", "leer": False}
    return {**ergebnis, "hinweis": hinweis}


def hersteller(
    state_dir,
    tco: dict,
    katalog,
    tarifbestand,
    heute: str,
    erfassung_roh: dict[str, str] | None = None,
) -> dict:
    """Die Herstellergrafik samt Portfolio-Ansicht (Schlüssel `portfolio`) - ein
    Aufruf für die Seite, damit `geraete_view` nicht wächst."""
    herstellergrafik = geraete_hersteller.ansicht(
        state_dir, tco, katalog, tarifbestand, heute
    )
    return {
        **herstellergrafik,
        "portfolio": ansicht(state_dir, tco, katalog, heute, erfassung_roh),
    }
