"""Tarifwelt (Saturn/MediaMarkt): der Leser, der aus einem Pflichtmodell
Buendel je Speicher, Netz und Band macht.

ENTSCHEIDUNG "klick-Baukasten erweitern vs. schlanker eigener Leser"
(08.11.2026): schlanker eigener Leser. Der Klick-Baukasten (`klick*`: Tor,
Fristschleuse, Inventar, Kartenproben) ist ein Erkunder fuer Seiten mit
unbekanntem Aufbau; hier ist der Aufbau bekannt und klein. Der Vorgaenger
nahm an, ein bestimmter Tarif (`tfi`) lasse sich nur im Browser lesen, weil
die Seite das `ofi` selbst nachlaedt. Messung 08.11.2026 (Netzmitschnitt der
Seite, dann dieselbe Anfrage ohne Browser): die ERSTE Anfrage der Seite,
`productdetail/<slug>?storage=<GB>&tfi=<id>`, liefert schon die Kosten
dieses Tarifs; `ofi` ist die `offerId` aus ihrer Antwort, und die
Folgeanfrage des Browsers (mit color/ogi/ofi/hwi) liefert dieselben Betraege
centgenau. Der Leser macht deshalb genau diese eine Anfrage je Variante ueber
den vorhandenen Abrufweg `hole(..., einmalig=True)`: ein Versuch, kein
Backoff, keine Weiterleitung ohne Wache, ehrliche Kennung, nie ein Wechsel.

HARTER ABBRUCH: eine Schutzantwort (HTTP 403/406/429 oder eine vom Abrufweg
erkannte Challenge) beendet den GANZEN Lauf mit `GeraeteAbrufFehler` - kein
Wiederholen, kein weiterer Abruf. Alles andere (404, kein JSON, ein anderer
Tarif als verlangt, ein anderer Speicher) macht nur DIESE Variante zur
benannten Luecke, nie zu einem Preis.

Je Variante genau eine Anfrage, dazu je Modell eine Uebersicht und je
Speicher eine Tarifliste. Zwischen zwei Anfragen liegt `PAUSE_SEKUNDEN`.
Nie `/pks`, nie `/checkout`, keine Konten, kein Warenkorb.

`MODELL_SLUGS` ordnet jedes Pflichtmodell (config/geraete_abdeckung.yaml) der
Basisseite in https://tarife.mediamarkt.de/sitemap.xml zu (Stand 08.11.2026);
Seiten mit "-aktion" oder "-online-bonus" sind Aktionen und stehen nie darin.
Tarifwahl: unbegrenzt (`dataVolume: 0`) ist `inf`, wie im Tarifbestand.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from ...geraete_model import device_id, sku_id
from ...tco_model import Buendel
from . import tarifwelt
from .basis import GeraeteAbrufFehler, antwort_text

log = logging.getLogger(__name__)

API = "https://tarife-api2.mediamarkt.de/v1/productdetail"
SEITE = "https://tarife.mediamarkt.de/smartphones"
KENNUNG = "TelcoRadar/1.0 (+https://telco-radar.onrender.com/ueber)"
PAUSE_SEKUNDEN = 2.0
LAUFZEIT_MONATE = 24
MAX_KANDIDATEN = 3

MODELL_SLUGS: dict[str, tuple[str, str, str, str]] = {
    "apple-iphone-18-pro": ("Apple", "iPhone 18 Pro", "apple", "iphone-18-pro"),
    "apple-iphone-18-pro-max": (
        "Apple",
        "iPhone 18 Pro Max",
        "apple",
        "iphone-18-pro-max",
    ),
    "apple-iphone-17": ("Apple", "iPhone 17", "apple", "iphone-17"),
    "apple-iphone-17-pro": ("Apple", "iPhone 17 Pro", "apple", "iphone-17-pro"),
    "apple-iphone-17-pro-max": (
        "Apple",
        "iPhone 17 Pro Max",
        "apple",
        "iphone-17-pro-max",
    ),
    "apple-iphone-17e": ("Apple", "iPhone 17e", "apple", "iphone-17e"),
    "apple-iphone-duo": ("Apple", "iPhone Duo", "apple", "iphone-duo"),
    "apple-iphone-air": ("Apple", "iPhone Air", "apple", "iphone-air"),
    "samsung-galaxy-s26": ("Samsung", "Galaxy S26", "samsung", "galaxy-s26"),
    "samsung-galaxy-s26-plus": (
        "Samsung",
        "Galaxy S26 Plus",
        "samsung",
        "galaxy-s26-plus",
    ),
    "samsung-galaxy-s26-ultra": (
        "Samsung",
        "Galaxy S26 Ultra",
        "samsung",
        "galaxy-s26-ultra",
    ),
    "samsung-galaxy-z-fold8": (
        "Samsung",
        "Galaxy Z Fold8",
        "samsung",
        "galaxy-z-fold-8",
    ),
    "samsung-galaxy-z-flip8": (
        "Samsung",
        "Galaxy Z Flip8",
        "samsung",
        "galaxy-z-flip-8",
    ),
    "samsung-galaxy-a57": ("Samsung", "Galaxy A57", "samsung", "galaxy-a57"),
    "google-pixel-11": ("Google", "Pixel 11", "google", "pixel-11"),
    "google-pixel-11-pro": ("Google", "Pixel 11 Pro", "google", "pixel-11-pro"),
    "google-pixel-11-pro-xl": (
        "Google",
        "Pixel 11 Pro XL",
        "google",
        "pixel-11-pro-xl",
    ),
    "google-pixel-10a": ("Google", "Pixel 10a", "google", "pixel-10a"),
}


@dataclass
class Lauf:
    """Ergebnis eines Modells: Buendel und benannte Luecken (Variante -> Grund)."""

    buendel: list[Buendel] = field(default_factory=list)
    luecken: list[tuple[str, str]] = field(default_factory=list)
    abrufe: int = 0


def _json(text: str):
    try:
        return json.loads(text or "")
    except (json.JSONDecodeError, ValueError):
        return None


def lies_uebersicht(text: str) -> dict | None:
    """Je Speicherstufe Gruppen-ID, Angebots-ID und `hwi` aus der Geraeteantwort
    `productdetail/<slug>`. Jede Speicherstufe hat ihr EIGENES Angebot; die
    Antwort selbst traegt nur das vorgewaehlte (`hardware.variants`), alle
    Stufen stehen in `hardware.variantFilter`. Nur eine lieferbare Variante
    (`available`) zaehlt; eine Stufe ganz ohne sie steht in `nicht_lieferbar`.
    `None`, wenn nichts lesbar ist."""
    daten = _json(text)
    if not isinstance(daten, dict):
        return None
    hardware = daten.get("hardware") or {}
    je_speicher: dict[int, dict] = {}
    vorgewaehlt = (
        daten.get("offerGroupId"),
        daten.get("offerId"),
        hardware.get("id"),
    )
    if all(vorgewaehlt):
        for v in hardware.get("variants") or []:
            if (
                isinstance(v, dict)
                and isinstance(v.get("storage"), int)
                and v.get("ebootisId")
            ):
                je_speicher.setdefault(
                    v["storage"],
                    {
                        "ogi": vorgewaehlt[0],
                        "ofi": vorgewaehlt[1],
                        "hwi": f"{vorgewaehlt[2]}_{v['ebootisId']}",
                    },
                )
    nicht_lieferbar: set[int] = set()
    for v in hardware.get("variantFilter") or []:
        if not isinstance(v, dict) or not isinstance(v.get("storage"), int):
            continue
        ogi, ofi, hwi = v.get("offerGroupId"), v.get("offerId"), v.get("hwi")
        if not (ogi and ofi and hwi):
            continue
        if v.get("available"):
            je_speicher.setdefault(v["storage"], {"ogi": ogi, "ofi": ofi, "hwi": hwi})
        else:
            nicht_lieferbar.add(v["storage"])
    if not je_speicher and not nicht_lieferbar:
        return None
    return {
        "je_speicher": dict(sorted(je_speicher.items())),
        "nicht_lieferbar": sorted(nicht_lieferbar - set(je_speicher)),
    }


def _abruf(hole: Callable, url: str, lauf: Lauf, warte: Callable[[float], None]) -> str:
    """EIN Abruf, ohne Wiederholung. Schutzantwort: Ausnahme mit `schutz`."""
    if lauf.abrufe:
        warte(PAUSE_SEKUNDEN)
    lauf.abrufe += 1
    antwort = hole(url, user_agent=KENNUNG, einmalig=True)
    try:
        return antwort_text(antwort)
    except GeraeteAbrufFehler as fehler:
        if fehler.schutz or fehler.status in (403, 406, 429):
            raise GeraeteAbrufFehler(
                f"Tarifwelt: Schutzantwort (HTTP {fehler.status}) bei {url} - "
                "Lauf abgebrochen, kein Wiederholen",
                status=fehler.status,
                schutz=True,
            ) from fehler
        raise


def rangliste_tarife(liste: list[dict], leiter_gb) -> dict[tuple[str, str], list[dict]]:
    """(Netz, Band) -> Tarife in Reihenfolge der Eignung. Doppelkarten und
    Aktionen fallen weg (`ohne_doppelkarte`; Aktionstarife tragen `Aktion` im
    Namen), ebenso altersgebundene Young-Tarife und unbekannte Netze."""
    brauchbar = [
        s
        for s in tarifwelt.ohne_doppelkarte(liste)
        if "aktion" not in (s.get("tarif_name") or "").lower()
        and "young" not in (s.get("tarif_name") or "").lower()
        and tarifwelt.anbieter_zeile(s.get("netz")) is not None
    ]
    je_netz: dict[str, list[dict]] = {}
    for satz in brauchbar:
        je_netz.setdefault(satz["netz"], []).append(satz)
    out: dict[tuple[str, str], list[dict]] = {}
    for netz, saetze in je_netz.items():
        for band, rang in tarifwelt.rangliste_je_band(saetze, leiter_gb).items():
            out[(netz, band)] = rang
    return out


def waehle_tarife(liste: list[dict], leiter_gb) -> dict[tuple[str, str], dict]:
    """(Netz, Band) -> genau ein Tarif, der erste der Rangliste."""
    return {k: v[0] for k, v in rangliste_tarife(liste, leiter_gb).items()}


def lies_modell(
    modell_id: str,
    leiter_gb,
    hole: Callable,
    abgerufen_am: str,
    warte: Callable[[float], None] = time.sleep,
) -> Lauf:
    """Alle Speicher x Netz x Band eines Pflichtmodells."""
    hersteller, name, pfad, slug = MODELL_SLUGS[modell_id]
    lauf = Lauf()
    uebersicht = lies_uebersicht(_abruf(hole, f"{API}/{slug}", lauf, warte))
    if uebersicht is None:
        lauf.luecken.append((modell_id, "Uebersicht nicht lesbar"))
        return lauf
    geraet = device_id(hersteller, name)
    for speicher in uebersicht["nicht_lieferbar"]:
        lauf.luecken.append((f"{modell_id} {speicher} GB", "nicht lieferbar"))
    for speicher, ids in uebersicht["je_speicher"].items():
        listen_url = f"{API}/{ids['ogi']}/tariff?hwi={ids['hwi']}"
        try:
            liste = tarifwelt.lies_tarifliste(
                _abruf(hole, listen_url, lauf, warte), listen_url
            )
        except GeraeteAbrufFehler as fehler:
            if fehler.schutz:
                raise
            lauf.luecken.append((f"{modell_id} {speicher} GB", f"Tarifliste: {fehler}"))
            continue
        raenge = rangliste_tarife(liste, leiter_gb)
        if not raenge:
            lauf.luecken.append((f"{modell_id} {speicher} GB", "keine Tarife"))
            continue
        for (netz, band), kandidaten in sorted(raenge.items()):
            variante = f"{modell_id} {speicher} GB {netz} {band}"
            gefunden = _lies_variante(
                (slug, speicher, variante, ids), kandidaten, hole, lauf, warte
            )
            if gefunden is None:
                continue
            satz, tarif = gefunden
            lauf.buendel.append(
                Buendel(
                    sku_id=sku_id(geraet, speicher, None),
                    anbieter=tarifwelt.anbieter_zeile(satz["netz"]) or "",
                    tarif_name=satz["tarif_name"] or satz["tarif_id"],
                    tarif_id=f"mediamarkt_tarifwelt:{satz['tarif_id']}",
                    tarif_id_guete="niedrig",
                    tarif_monatlich=satz["grundgebuehr"],
                    geraet_zuzahlung=satz["geraet_zuzahlung"],
                    geraet_monatsrate=0.0,
                    laufzeit_monate=LAUFZEIT_MONATE,
                    anschlusspreis=satz["anschlusspreis"],
                    quelle_url=(
                        f"{SEITE}/{pfad}/{slug}/?speicher={speicher}"
                        f"&tfi={tarif['tarif_id']}"
                    ),
                    abgerufen_am=abgerufen_am,
                    herleitung="tarifwelt_productdetail",
                    zustand="neu",
                )
            )
    return lauf


def _lies_variante(
    wo: tuple[str, int, str, dict],
    kandidaten: list[dict],
    hole: Callable,
    lauf: Lauf,
    warte: Callable[[float], None],
) -> tuple[dict, dict] | None:
    """Der erste WAEHLBARE Tarif der Rangliste, hoechstens `MAX_KANDIDATEN`
    Abrufe. Die Schnittstelle fuehrt Tarife auf, die fuer ein Geraet eine
    leere Huelle liefern (Tarif-ID leer) oder einen anderen Speicher
    antworten - das ist "nicht waehlbar", der naechste Platz der Rangliste
    kommt dran. Jeder andere Mangel (Abruffehler, Laufzeit, Doppelkarte,
    fehlender Betrag) ist sofort die Luecke dieser Variante, nie ein Preis."""
    slug, speicher, variante, ids = wo
    gruende: list[str] = []
    for tarif in kandidaten[:MAX_KANDIDATEN]:
        url = (
            f"{API}/{slug}?storage={speicher}&ogi={ids['ogi']}&ofi={ids['ofi']}"
            f"&tfi={tarif['tarif_id']}&hwi={ids['hwi']}"
        )
        try:
            satz = tarifwelt.lies_produktdetail(_abruf(hole, url, lauf, warte), url)
        except GeraeteAbrufFehler as fehler:
            if fehler.schutz:
                raise
            lauf.luecken.append((variante, str(fehler)))
            return None
        grund, nicht_waehlbar = _pruefe(satz, tarif, speicher)
        if grund is None:
            assert satz is not None
            return satz, tarif
        gruende.append(grund)
        if not nicht_waehlbar:
            break
    lauf.luecken.append((variante, "; ".join(gruende)))
    return None


def _pruefe(satz: dict | None, gewollt: dict, speicher: int) -> tuple[str | None, bool]:
    """(Grund fuer eine Luecke oder `None`, ob der Tarif nur "nicht waehlbar"
    ist). `None` heisst: genau die verlangte Variante."""
    if satz is None:
        return "Tarif fuer dieses Geraet nicht waehlbar (leere Antwort)", True
    if satz["tarif_id"] != gewollt["tarif_id"]:
        return "Antwort traegt einen anderen Tarif", True
    if f"{speicher} GB" not in (satz.get("geraet_label") or ""):
        return f"Tarif nicht fuer {speicher} GB waehlbar (anderer Speicher)", True
    if satz["laufzeit_monate"] != LAUFZEIT_MONATE:
        return f"Laufzeit {satz['laufzeit_monate']} statt {LAUFZEIT_MONATE}", False
    if satz["doppelkarte"]:
        return "Doppelkarte", False
    for feld in ("grundgebuehr", "geraet_zuzahlung", "anschlusspreis"):
        if satz[feld] is None:
            return f"{feld} fehlt", False
    return None, False
