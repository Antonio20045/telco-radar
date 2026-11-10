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

Weiterleitung: jeder Sprung geht vor dem Folgen durch dieselbe
`Abrufschleuse` (robots.txt, Besuchsfenster); `hole_fuer_anbieter` gibt den
Einmal-Abrufen dafuer `vor_weiterleitung` mit.

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
Speicher: die Tarifwelt nennt 1 TB "1000 GB" (`KATALOG_SPEICHER`), der Katalog
und die Speicherprüfung des Wächters 1024; in der SKU steht die Katalogstufe,
in den Abrufen der Wert der Schnittstelle.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from ... import versandkosten
from ...geraete_model import device_id, sku_id
from ...tco_model import Buendel
from . import tarifwelt
from .basis import GeraeteAbrufFehler, antwort_text
from .tarifwelt_merkmale import unvergleichbar_grund, wechselbonus_aktionen
from .tarifwelt_uebersicht import lies_uebersicht

log = logging.getLogger(__name__)

API = "https://tarife-api2.mediamarkt.de/v1/productdetail"
SEITE = "https://tarife.mediamarkt.de/smartphones"
KENNUNG = "TelcoRadar/1.0 (+https://telco-radar.onrender.com/ueber)"
PAUSE_SEKUNDEN = 2.0
LAUFZEIT_MONATE = 24
MAX_KANDIDATEN = 3
MONAT_TOLERANZ = 0.01
KATALOG_SPEICHER = {1000: 1024, 2000: 2048}

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
    """Ergebnis eines Modells: Buendel, benannte Luecken (Variante -> Grund) und
    `tarife` (tarif_id "mediamarkt_tarifwelt:<id>" -> Anbieterzeile, Name,
    Datenvolumen, Grundgebuehr) fuer die Band-Zuordnung im Bericht
    (`tarifwelt_bestand`)."""

    buendel: list[Buendel] = field(default_factory=list)
    luecken: list[tuple[str, str]] = field(default_factory=list)
    abrufe: int = 0
    tarife: dict[str, dict] = field(default_factory=dict)


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
    """(Netz, Band) -> Tarife in Reihenfolge der Eignung. Unvergleichbare Tarife
    fallen weg (`tarifwelt_merkmale.unvergleichbar_grund`: Doppelkarte, Aktion,
    Young, Kids, Senioren, Cashback, Preiswechsel vor Monat 25), ebenso
    unbekannte Netze."""
    brauchbar = [
        s
        for s in liste
        if unvergleichbar_grund(s) is None
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
            lauf.tarife[f"mediamarkt_tarifwelt:{satz['tarif_id']}"] = {
                "anbieter": tarifwelt.anbieter_zeile(satz["netz"]) or "",
                "name": satz["tarif_name"] or satz["tarif_id"],
                "datenvolumen_gb": tarif["datenvolumen_gb"],
                "grundgebuehr": satz["grundgebuehr"],
            }
            quelle_url = (
                f"{SEITE}/{pfad}/{slug}/?speicher={speicher}&tfi={tarif['tarif_id']}"
            )
            lauf.buendel.append(
                Buendel(
                    sku_id=sku_id(
                        geraet, KATALOG_SPEICHER.get(speicher, speicher), None
                    ),
                    anbieter=tarifwelt.anbieter_zeile(satz["netz"]) or "",
                    tarif_name=satz["tarif_name"] or satz["tarif_id"],
                    tarif_id=f"mediamarkt_tarifwelt:{satz['tarif_id']}",
                    tarif_id_guete="niedrig",
                    tarif_monatlich=satz["grundgebuehr"],
                    geraet_zuzahlung=satz["geraet_zuzahlung"],
                    geraet_monatsrate=0.0,
                    laufzeit_monate=LAUFZEIT_MONATE,
                    anschlusspreis=satz["anschlusspreis"],
                    quelle_url=quelle_url,
                    abgerufen_am=abgerufen_am,
                    herleitung="tarifwelt_productdetail",
                    zustand="neu",
                    aktionen=wechselbonus_aktionen(satz.get("hinweise"), quelle_url),
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
    if satz.get("geraeteposten") != 1:
        return f"{satz.get('geraeteposten')} Geraeteposten statt 1", False
    if satz["laufzeit_monate"] != LAUFZEIT_MONATE:
        return f"Laufzeit {satz['laufzeit_monate']} statt {LAUFZEIT_MONATE}", False
    if grund := unvergleichbar_grund(satz):
        return f"nicht vergleichbar: {grund}", False
    for feld in ("grundgebuehr", "geraet_zuzahlung", "anschlusspreis"):
        if satz[feld] is None:
            return f"{feld} fehlt", False
    return _pruefe_kosten(satz)


def _pruefe_kosten(satz: dict) -> tuple[str | None, bool]:
    """Die Antwort muss zu sich selbst und zur Config passen: Monatspreis gleich
    der Summe der monatlichen Posten (hoechstens `MONAT_TOLERANZ` Abweichung),
    Versandposten gleich dem Betrag in `config/versandkosten.yaml` (Abweichung:
    Luecke und Warnung, Config bleibt unveraendert - sie aendert nur eine
    neue Messung)."""
    summe = satz.get("monat_posten")
    if summe is None:
        return "monatliche Kostenposten fehlen", False
    if round(abs(summe - satz["grundgebuehr"]), 2) > MONAT_TOLERANZ:
        return (
            f"Monatspreis {satz['grundgebuehr']} weicht von der Summe der "
            f"Monatsposten {summe} ab",
            False,
        )
    zeile = tarifwelt.anbieter_zeile(satz.get("netz")) or ""
    erwartet = versandkosten.versand_fuer(zeile).betrag
    if erwartet is not None and satz.get("versand") != erwartet:
        grund = (
            f"Versand {satz.get('versand')} weicht von versandkosten.yaml "
            f"({erwartet}) ab"
        )
        log.warning("Tarifwelt: %s: %s - Luecke, neu messen", zeile, grund)
        return grund, False
    return None, False
