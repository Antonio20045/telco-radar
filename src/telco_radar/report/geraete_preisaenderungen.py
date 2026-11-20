"""Die Seite „Preisänderungen“: je Messtag jedes Bündel, dessen Preis sich änderte.

Quelle ist die Preishistorie je Messtag (``data/state/geraete_tco_historie/``). Eine
Zeile zählt nur an dem Tag, an dem sie gemessen ist (``abgerufen_am`` = ``datum``),
und wird mit der letzten Messung desselben Bündels davor verglichen; geändert heißt
``gegenprobe.geaendert`` (ein Wechsel nur der Rechenweise ist keine Preisänderung).
Die Gesamtkosten beider Tage rechnet ``kosten_ueber`` aus den Posten der Messung, wie
die Zeitreihe (``geraete_rechenweg._buendel_aus_messung``); das eingefrorene ``gesamt``
der Historie stammt bis 19.11.2026 aus einer anderen Formel und zählt hier nicht.

Jede Änderung trägt den Beleg beider Tage (``geraete_preisbeleg.beleg``): Quelle,
gelesen am, Rechenweg, Screenshot (Messung des Tages, sonst das Bild der Gegenprobe)
und Gegenprobe des Tages. Fehlt etwas, sagt der Beleg es.
"""

from __future__ import annotations

import csv
import io
import logging
import shutil
from collections.abc import Callable
from pathlib import Path

from .. import gegenprobe as gp
from .. import tco_historie
from ..analyze.beleg_position import lies_buendel
from ..tco_model import kosten_ueber
from . import anbieter_farben
from .geraete_preisbeleg import Gegenproben, angebot, beleg, datum_de
from .geraete_rechenweg import buendel_der_messung
from .geraete_rechnung import zum_lesen
from .geraete_tco_grafik import euro

log = logging.getLogger(__name__)

SEITE = "geraete-preisaenderungen.html"
ORDNER = "preisaenderungen"
NUR_EIN_LAUF = "nur in einem Lauf gesehen"
"""Marke einer Änderung, die die nächste Messung zurücknimmt (A → B → A)."""
ZEILEN_JE_TAG = 200
"""So viele Änderungen eines Tages stehen mit Beleg auf seiner Seite (die größten);
alle stehen mit denselben Angaben im Export des Tages."""
AUSFALL = "Preisänderungen nicht aufbereitet"
CSV_SPALTEN = (
    "Anbieter",
    "Gerät",
    "Tarif",
    "Raten",
    "Datum vorher",
    "Gesamt vorher EUR",
    "Rechenweg vorher",
    "Quelle vorher",
    "Gegenprobe vorher",
    "Screenshot vorher",
    "Datum",
    "Gesamt EUR",
    "Rechenweg",
    "Quelle",
    "Gegenprobe",
    "Screenshot",
    "Änderung EUR",
    "Geänderte Posten",
    "Nur in einem Lauf",
)
HISTORIE = "geraete_tco_historie.jsonl"
BESTAND = "geraete_tco.json"


def _stand(bid: str, bestand: dict[str, dict]) -> dict:
    """Der Bestandssatz zum Bündel, sonst Anbieter, SKU und Tarif aus dem Schlüssel."""
    if bid in bestand:
        return bestand[bid]
    teile = bid.split("--")
    if len(teile) != 5:
        return {}
    return {"anbieter": teile[1], "sku_id": teile[2], "tarif_name": teile[3]}


def _kosten(satz: dict, stand: dict, tarife: dict) -> tuple[float | None, list | None]:
    """(Gesamtkosten, Summanden) einer Messung; (None, None) ohne volle Zahl."""
    b = buendel_der_messung(satz, stand, tarife)
    if b is None:
        return None, None
    kosten = kosten_ueber(b)
    if kosten.gesamt is None:
        return None, None
    return kosten.gesamt, zum_lesen(kosten.rechnung)


def _posten(alt: dict, neu: dict) -> list[str]:
    """„Geräterate 5,00 € → 9,50 €“ je geändertem Posten."""
    out = []
    for feld in gp.FELDER:
        a, n = alt.get(feld), neu.get(feld)
        if a == n or (a is not None and n is not None and gp.gleich(a, n)):
            continue
        name = gp.FELDNAMEN[feld]
        if feld in gp.GANZZAHLFELDER:
            out.append(f"{name} {a if a is not None else '–'} → {n}")
        else:
            out.append(f"{name} {euro(a)} → {euro(n)}")
    return out


def _tag(
    satz: dict,
    stand: dict,
    tarife: dict,
    gegenproben: Gegenproben,
    bild: dict | None,
) -> dict:
    gesamt, schritte = _kosten(satz, stand, tarife)
    datum = satz.get("datum") or ""
    return {
        "datum": datum,
        "datum_de": datum_de(datum),
        "gesamt": gesamt,
        "beleg": beleg(
            quelle_url=satz.get("quelle_url") or "",
            abgerufen_am=satz.get("abgerufen_am") or "",
            schritte=schritte,
            gesamt=gesamt,
            bild=bild,
            gegenprobe=gegenproben.am(satz["id"], datum),
        ),
    }


def aufbereiten(
    state_dir: Path,
    karten: dict[str, dict],
    gegenproben: Gegenproben,
    zeilenbild: Callable[[dict], dict | None],
    tarife: dict | None = None,
) -> list[dict]:
    """Die Tage mit Änderungen, jüngster zuerst; je Tag die Änderungen, größte zuerst.

    ``tarife`` ist der Tarifbestand je Tarif-Schlüssel, wie ihn die Zeitreihe nutzt
    (``geraete_view``: Preisphasen kommen beim Lesen dazu).

    ``karten`` sind die Preiszeilen der Geräteseite je Bündel-Schlüssel (Name,
    Tarif, Raten, Farbe und das Bild der heutigen Messung über ``zeilenbild``).
    """
    bestand = {b["id"]: b for b in lies_buendel(state_dir / BESTAND) if b.get("id")}
    zuletzt: dict = {}
    tage: list[dict] = []
    offen: dict[str, tuple[dict, dict]] = {}
    """Je Bündel die letzte Änderung (Eintrag, Messung davor), bis die nächste Messung
    zeigt, ob sie blieb oder zurückging (``NUR_EIN_LAUF``)."""
    for tag, saetze in tco_historie.tage(state_dir / HISTORIE):
        gemessen = gp.gemessen(saetze, tag)
        for bid, satz in gemessen.items():
            if bid in offen:
                eintrag, davor = offen.pop(bid)
                eintrag["nur_ein_lauf"] = not gp.geaendert(satz, davor)
        aenderungen = []
        for satz, vorher in gp.aenderungen(gemessen, zuletzt):
            eintrag = _aenderung(
                dict(satz),
                dict(vorher),
                bestand,
                karten,
                tarife,
                gegenproben,
                zeilenbild,
            )
            offen[satz["id"]] = (eintrag, dict(vorher))
            aenderungen.append(eintrag)
        zuletzt.update(gemessen)
        if aenderungen:
            aenderungen.sort(key=lambda a: -abs(a["delta"] or 0.0))
            datum = aenderungen[0]["neu"]["datum"]
            tage.append(
                {
                    "datum": datum,
                    "datum_de": datum_de(datum),
                    "aenderungen": aenderungen,
                    "gegenprobe": _bilanz(aenderungen),
                }
            )
    return sorted(tage, key=lambda t: t["datum"], reverse=True)


def _aenderung(satz, vorher, bestand, karten, tarife, gegenproben, zeilenbild) -> dict:
    bid = satz["id"]
    stand = _stand(bid, bestand)
    karte = karten.get(bid) or karten.get(angebot(bid))
    bild = None
    if karte is not None and karte.get("abgerufen_am") == satz.get("datum"):
        gefunden = zeilenbild(karte)
        if gefunden is not None:
            bild = {
                "url": gefunden["url"],
                "datum": gefunden["datum"],
                "art": "Messung",
            }
    alt = _tag(vorher, stand, tarife, gegenproben, None)
    neu = _tag(satz, stand, tarife, gegenproben, bild)
    delta = (
        round(neu["gesamt"] - alt["gesamt"], 2)
        if neu["gesamt"] is not None and alt["gesamt"] is not None
        else None
    )
    anbieter = (karte or {}).get("anbieter") or stand.get("anbieter") or ""
    return {
        "id": bid,
        "anbieter": anbieter,
        "anb_farbe": anbieter_farben.farbe_fuer(anbieter),
        "geraet": (karte or {}).get("geraet") or stand.get("sku_id") or "",
        "tarif": (karte or {}).get("tarif") or stand.get("tarif_name") or "",
        "raten": satz.get("laufzeit_monate"),
        "alt": alt,
        "neu": neu,
        "delta": delta,
        "posten": _posten(vorher, satz),
        "nur_ein_lauf": False,
    }


OFFEN = "offen"
"""Bilanz: Änderungen ohne Gegenprobe, auch die, für die der Lauf keine Zeit hatte."""


def _bilanz(aenderungen: list[dict]) -> dict[str, int]:
    """Wie viele Änderungen des Tages die Gegenprobe bestätigt, nur teilweise
    bestätigt, verwirft, nicht prüfen konnte und wie viele ungeprüft blieben
    (``OFFEN``: ohne Gegenprobe oder mit „Zeitbudget erschöpft“)."""
    out = {status: 0 for status in gp.STATUS}
    out[OFFEN] = 0
    for a in aenderungen:
        g = a["neu"]["beleg"]["gegenprobe"]
        if g is None or g["grund"] == gp.GRUND_ZEITBUDGET:
            out[OFFEN] += 1
        else:
            out[g["status"]] += 1
    return out


def karten_je_id(tco: dict) -> dict[str, dict]:
    """Die Preiszeilen der Geräteseite je Bündel-Schlüssel."""
    out: dict[str, dict] = {}
    for m in tco.get("modelle") or []:
        for k in [*m.get("zeilen_band", []), *m.get("zeilen_ohne_band", [])]:
            if k.get("buendel_id"):
                out.setdefault(k["buendel_id"], k)
                out.setdefault(angebot(k["buendel_id"]), k)
    return out


def csv_text(tag: dict) -> str:
    """Alle Änderungen eines Tages mit den Angaben beider Belege (Export)."""
    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=";")
    schreiber.writerow(CSV_SPALTEN)
    for a in tag["aenderungen"]:
        zeile = [a["anbieter"], a["geraet"], a["tarif"], a["raten"] or ""]
        for t in (a["alt"], a["neu"]):
            b = t["beleg"]
            g = b["gegenprobe"]
            zeile += [
                t["datum"],
                "" if t["gesamt"] is None else f"{t['gesamt']:.2f}",
                (b["rechenweg"] or {}).get("text", ""),
                b["quelle_url"],
                g["wort"] if g else "",
                (b["bild"] or {}).get("url", ""),
            ]
        zeile += [
            "" if a["delta"] is None else f"{a['delta']:.2f}",
            " · ".join(a["posten"]),
            "ja" if a["nur_ein_lauf"] else "",
        ]
        schreiber.writerow(zeile)
    return puffer.getvalue()


def seiten(env, geraete: dict, site_dir: Path) -> dict[Path, str]:
    """Übersicht, je Tag eine Seite (größte ``ZEILEN_JE_TAG`` Änderungen mit Beleg)
    und je Tag ein Export mit allen. Scheitert die Aufbereitung, nennt die Übersicht
    den Ausfall."""
    belege = env.globals.get("preisbelege")
    uebersicht = env.get_template("geraete_preisaenderungen.html.j2")
    tagesseite = env.get_template("geraete_preisaenderungen_tag.html.j2")
    if belege is None:
        return {
            site_dir / SEITE: uebersicht.render(prefix="", tage=[], ausfall=AUSFALL)
        }
    try:
        tage = aufbereiten(
            belege.state_dir,
            karten_je_id(geraete.get("tco") or {}),
            belege.gegenproben,
            belege.zeilenbild,
            geraete.get("tarife") or {},
        )
    except (OSError, ValueError, KeyError, TypeError) as fehler:
        log.error("Preisänderungen nicht aufbereitbar: %s", fehler)
        ausfall = f"{AUSFALL} ({type(fehler).__name__})"
        return {
            site_dir / SEITE: uebersicht.render(prefix="", tage=[], ausfall=ausfall)
        }
    ordner = site_dir / ORDNER
    if ordner.exists():
        shutil.rmtree(ordner)
    ordner.mkdir(parents=True)
    dateien = {
        site_dir / SEITE: uebersicht.render(
            prefix="", tage=tage, ausfall=None, ordner=ORDNER
        )
    }
    for tag in tage:
        dateien[ordner / f"{tag['datum']}.html"] = tagesseite.render(
            prefix="../",
            tag=tag,
            zeilen=tag["aenderungen"][:ZEILEN_JE_TAG],
            zeilen_je_tag=ZEILEN_JE_TAG,
            nur_ein_lauf=NUR_EIN_LAUF,
        )
        dateien[ordner / f"{tag['datum']}.csv"] = csv_text(tag)
    return dateien
