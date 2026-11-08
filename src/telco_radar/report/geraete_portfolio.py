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
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from ..analyze import buendel_abdeckung
from . import geraete_hersteller
from .anbieter_farben import legendenname, slug_fuer
from .geraete_hersteller import HERSTELLER_VORAN, aktuelle_geraete
from .geraete_hersteller_text import EIGEN
from .geraete_rechenweg import ANBIETER_FOLGE

log = logging.getLogger(__name__)

STANDARD = "Telekom"
ABDECKUNG = ("config", "geraete_abdeckung.yaml")
PREIS, ALT = "preis", "alt"
GRUND_OHNE = "ohne Beleg"
GRUND_ABGELAUFEN = "Beleg abgelaufen"
GRUND_UNZUREICHEND = "Beleg zeigt kein fehlendes Sortiment"
BELEG_AUSSAGEN = (
    "nicht im Sortiment",
    "Seite entfernt",
    "nicht in der Geräteliste",
    "nicht mehr in der Geräteliste",
)
FEHLT_SATZ = (
    "{wer} führt es (Preis gemessen). Für {fehlt} liegt kein {beleg} vor{grund}."
)
REGEL = (
    "Als Lücke zählt nur, was am Original belegt ist (Screenshot, geprüft und "
    "befristet); fehlt ein Preis ohne gültigen Beleg, ist das eine Messlücke und "
    "zählt nicht als Portfolio-Lücke."
)


def _datum(text) -> str:
    try:
        d = date.fromisoformat(str(text))
    except ValueError:
        return str(text)
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def staende(tco_modelle: list[dict]) -> dict[str, dict[str, str]]:
    """{device_id: {Anbieter: PREIS | ALT}} aus den Karten der Seite.

    PREIS: neue, frische, nicht geschätzte Karte mit Gesamtpreis. ALT: es gibt
    Karten, aber keine davon trägt einen frischen Preis. Wiederaufgearbeitete
    Karten zählen nicht."""
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
                je[anbieter] = PREIS
            else:
                je.setdefault(anbieter, ALT)
    return aus


def beleg_fuer(
    belege: dict,
    anbieter: str,
    device_id: str,
    heute: str,
    speicher: str | None = None,
) -> tuple[dict | None, str]:
    """(gültiger Beleg, Grund). Ohne gültigen Beleg ist der Grund `GRUND_OHNE` oder
    `GRUND_ABGELAUFEN`; ohne bekannten Stichtag gilt kein Beleg als gültig.
    Mit `speicher` ("512gb") geht eine Lücke genau dieser Stufe vor; ohne ihn
    zählt nie eine Stufenlücke, denn ein fehlender Speicher ist kein fehlendes Gerät."""
    b = (
        (belege.get((anbieter, device_id, speicher)) if speicher else None)
        or belege.get((anbieter, device_id))
        or belege.get((anbieter, "*"))
    )
    if not b:
        return None, GRUND_OHNE
    if not any(a.lower() in str(b.get("grund", "")).lower() for a in BELEG_AUSSAGEN):
        return None, GRUND_UNZUREICHEND
    if not heute or heute > b["bis"].isoformat():
        return None, f"{GRUND_ABGELAUFEN} (bis {_datum(b['bis'].isoformat())})"
    return b, ""


def _beleg_text(b: dict) -> dict:
    return {
        "url": b["beleg"],
        "original": b["original"],
        "geprueft": _datum(b["geprueft"].isoformat()),
        "bis": _datum(b["bis"].isoformat()),
        "grund": b["grund"],
    }


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


def _paar(w: str, geraete: list, staende_je: dict, belege: dict, heute: str) -> dict:
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
        zeile = {"hersteller": g.hersteller, "name": g.modell}
        if beleg:
            (nur_w if hat_w else nur_v).append({**zeile, "beleg": _beleg_text(beleg)})
        else:
            fuehrt = w if hat_w else EIGEN
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
    paare = [
        _paar(w, geraete, je, belege, heute)
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


def abdeckung_pfad(state_dir) -> Path:
    """`config/geraete_abdeckung.yaml` neben `data/state` (Aufbau des Repos)."""
    return Path(state_dir).parents[1].joinpath(*ABDECKUNG)


def lade_belege(state_dir) -> dict:
    """Die Belege der Config (`lade_pflicht()["belege"]`); nicht lesbar heißt
    keine Lücke belegt - die sichere Richtung - und steht im Log."""
    try:
        return buendel_abdeckung.lade_pflicht(abdeckung_pfad(state_dir))["belege"]
    except (OSError, ValueError, KeyError, AttributeError):
        log.exception("Belegliste nicht lesbar")
        return {}


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
