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

from ..analyze import buendel_abdeckung
from ..analyze.klick_erfassung import SATZ_NICHT_IM_ANGEBOT
from . import geraete_hersteller
from .anbieter_farben import legendenname, slug_fuer
from .geraete_hersteller import HERSTELLER_VORAN, aktuelle_geraete
from .geraete_hersteller_text import EIGEN
from .geraete_rechenweg import ANBIETER_FOLGE
from .geraete_sortiment import GRUND_OHNE, abdeckung_pfad, beleg_fuer
from .geraete_sortiment import datum_de as _datum

log = logging.getLogger(__name__)

_ERFASSUNG_MUSTER = re.compile(
    re.escape(SATZ_NICHT_IM_ANGEBOT)
    .replace(re.escape("{anbieter}"), ".+")
    .replace(re.escape("{datum}"), r"(?P<datum>\d{2}\.\d{2}\.\d{4})")
)

STANDARD = "Telekom"
PREIS, ALT, IN_PRUEFUNG = "preis", "alt", "in_pruefung"
_RANG = {PREIS: 2, IN_PRUEFUNG: 1, ALT: 0}
FEHLT_SATZ = (
    "{wer} führt es (Preis gemessen). Für {fehlt} liegt kein {beleg} vor{grund}."
)
IN_PRUEFUNG_SATZ = (
    "{wer} führt es (Preis gemessen). {fehlt} führt es ebenfalls, der Preis "
    "steht noch in Prüfung."
)
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


def erfassung_je(tco_modelle: list[dict]) -> dict[str, dict[str, dict]]:
    """{device_id: {Anbieter: Beleg}} aus den `erfassung`-Sätzen eines Modells
    (`klick_erfassung.fuer_modell`, von `geraete_view` je Modell gesetzt).

    Nur Sätze der Form `SATZ_NICHT_IM_ANGEBOT` zählen: eine an einem Tag ganz
    gelesene Geräteübersicht, die das Gerät nicht zeigt - dieselbe
    Sortiments-Aussage wie die Belege aus `config/geraete_abdeckung.yaml`, nur
    ohne Screenshot-Link (`_beleg_text` zeigt dann einen Auszug statt eines
    Links). Andere Erfassungsgründe (Seite gesperrt, nur ein Speicher gelesen)
    sagen nichts über das Sortiment und zählen nicht."""
    aus: dict[str, dict[str, dict]] = {}
    for modell in tco_modelle or []:
        device_id = modell.get("device_id") or ""
        for anbieter, satz in (modell.get("erfassung") or {}).items():
            geprueft = _erfassung_datum(satz)
            if geprueft is None:
                continue
            aus.setdefault(device_id, {})[anbieter] = {
                "grund": satz,
                "geprueft": geprueft,
            }
    return aus


def _beleg_text(b: dict) -> dict:
    text = {"grund": b["grund"], "geprueft": _datum(b["geprueft"].isoformat())}
    if b.get("beleg"):
        text["url"] = b["beleg"]
    if b.get("original"):
        text["original"] = b["original"]
    if b.get("bis"):
        text["bis"] = _datum(b["bis"].isoformat())
    return text


def _gruppiert(zeilen: list[dict]) -> list[dict]:
    """Nach Hersteller gruppieren: die großen drei zuerst, dann nach Zahl, Name."""
    je: dict[str, list[dict]] = {}
    for z in zeilen:
        je.setdefault(z["hersteller"], []).append(z)
    voran = [h for h in HERSTELLER_VORAN if h in je]
    rest = sorted((h for h in je if h not in voran), key=lambda h: (-len(je[h]), h))
    return [
        {"hersteller": h, "geraete": sorted(je[h], key=lambda z: z["name"])}
        for h in [*voran, *rest]
    ]


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
        zeile = {"hersteller": g.hersteller, "name": g.modell}
        fuehrt = w if hat_w else EIGEN
        if beleg:
            (nur_w if hat_w else nur_v).append({**zeile, "beleg": _beleg_text(beleg)})
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
        "nur_w": _gruppiert(nur_w),
        "nur_v": _gruppiert(nur_v),
        "offen": _gruppiert(offen),
        "n_w": len(nur_w),
        "n_v": len(nur_v),
        "n_offen": len(offen),
        "beide": beide,
        "kopf": kopfzeile(w, len(nur_w), len(nur_v)),
        "kontext": kontext(len(nur_w) + len(nur_v), len(offen)),
        "offen_zeigen": not (nur_w or nur_v),
    }


def _geraete(n: int) -> str:
    return "1 Gerät" if n == 1 else f"{n} Geräte"


def kopfzeile(w: str, n_w: int, n_v: int) -> str:
    """Kopfzahlen je Paar: X nur beim Wettbewerber, Y nur bei Vodafone. Jede
    dieser Zahlen steht in der Vorlage mit `kontext` direkt darunter."""
    return f"{_geraete(n_w)} nur bei {legendenname(w)}, {n_v} nur bei Vodafone"


def kontext(n_belegt: int, n_offen: int) -> str:
    """Der Satz neben den Kopfzahlen: was die Null wirklich bedeutet."""
    offen = (
        "1 aktuelles Gerät ist noch nicht gemessen und wird"
        if n_offen == 1
        else f"{n_offen} aktuelle Geräte sind noch nicht gemessen und werden"
    )
    return f"Bisher belegt: {_geraete(n_belegt)}; {offen} nicht gezählt."


def fehlt_satz(fuehrt: str, fehlt: str, grund: str) -> str:
    """Zeile einer Messlücke: wer das Gerät nachweislich führt (gemessener Preis
    im Bestand) und dass für den anderen Anbieter kein Beleg vorliegt."""
    ohne = grund == GRUND_OHNE
    return FEHLT_SATZ.format(
        wer=legendenname(fuehrt),
        fehlt=legendenname(fehlt),
        beleg="Beleg" if ohne else "gültiger Beleg",
        grund="" if ohne else f": {grund}",
    )


def in_pruefung_satz(fuehrt: str, fehlt: str) -> str:
    """Zeile einer Quarantäne-Lücke (P3, 13.11.2026): `fehlt` führt das Gerät
    nachweislich (eine Karte in Quarantäne ist kein fehlendes Gerät), nur der
    Preis steht noch nicht fest - nie der Satz „liegt kein Beleg vor", der sich
    wie „hat das Gerät nicht" liest."""
    return IN_PRUEFUNG_SATZ.format(wer=legendenname(fuehrt), fehlt=legendenname(fehlt))


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


def berechne(tco_modelle: list[dict], katalog, belege: dict, heute: str) -> dict:
    """Reine Rechnung: alle Paare gegen Vodafone."""
    geraete = aktuelle_geraete(katalog)
    je = staende(tco_modelle)
    erf = erfassung_je(tco_modelle)
    paare = [
        _paar(w, geraete, je, belege, erf, heute)
        for w in wettbewerber_mit_daten(je, geraete)
    ]
    namen = [p["name"] for p in paare]
    return {
        "fehler": "",
        "leer": not paare,
        "stand": heute,
        "paare": paare,
        "standard": STANDARD if STANDARD in namen else (namen[0] if namen else ""),
        "regel": REGEL,
        "fehlende": fehlende_anbieter(paare),
        "geraete": len(geraete),
        "belege": len(belege),
    }


def ansicht(state_dir, tco: dict, katalog, heute: str) -> dict:
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
    try:
        ergebnis = berechne((tco or {}).get("modelle") or [], katalog, belege, heute)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        log.exception("Portfolio-Ansicht nicht aufbereitbar")
        return {"fehler": f"{type(exc).__name__}: {exc}", "leer": False}
    return {**ergebnis, "hinweis": hinweis}


def hersteller(state_dir, tco: dict, katalog, tarifbestand, heute: str) -> dict:
    """Die Herstellergrafik samt Portfolio-Ansicht (Schlüssel `portfolio`) - ein
    Aufruf für die Seite, damit `geraete_view` nicht wächst."""
    herstellergrafik = geraete_hersteller.ansicht(
        state_dir, tco, katalog, tarifbestand, heute
    )
    return {**herstellergrafik, "portfolio": ansicht(state_dir, tco, katalog, heute)}
