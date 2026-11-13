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

EIN PREIS GEHOERT ZU SEINER ZEILE (12.11.2026): Jede Antwort muss GENAU die
bestellte Hardware beschreiben - `hardware.variants` traegt sie mit `hwi`,
Speicher, Farbe, Barpreis und Lagerbestand. Geprueft werden Geraetename,
`hwi`, Speicher, Bestand > 0 und die Gleichheit von Zuzahlung und Barpreis
derselben Variante. Die Lieferbarkeit stammt damit aus DERSELBEN Antwort wie
der Preis, nicht nur aus der frueher gelesenen Uebersicht. Der Quelllink
traegt `ogi`, `ofi` und `hwi` (`shop_url`), sonst oeffnet der Shop die
vorgewaehlte Variante statt der Zeile.

HARTER ABBRUCH: eine Schutzantwort (HTTP 403/406/429 oder eine vom Abrufweg
erkannte Challenge) beendet den GANZEN Lauf mit `GeraeteAbrufFehler` - kein
Wiederholen, kein weiterer Abruf. Alles andere (404, kein JSON, ein anderer
Tarif als verlangt, ein anderer Speicher) macht nur DIESE Variante zur
benannten Luecke, nie zu einem Preis.

Je Variante genau eine Anfrage, dazu je Modell eine Uebersicht und je
Speicher eine Tarifliste. Zwischen zwei Anfragen liegt `PAUSE_SEKUNDEN`.
Nie `/pks`, nie `/checkout`, keine Konten, kein Warenkorb.

Welches Katalogmodell zu welcher Tarifwelt-Seite gehoert, steht in
`tarifwelt_modelle.MODELL_SLUGS` (ausgelagert, weil die Zuordnungstabelle
allein schon lang ist - dort auch die Erfassungslücke von Baupaket P6).
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

from ...geraete_model import device_id, sku_id
from ...tco_model import Buendel
from . import tarifwelt
from .basis import GeraeteAbrufFehler, antwort_text
from .tarifwelt_merkmale import unvergleichbar_grund, wechselbonus_aktionen
from .tarifwelt_modelle import MODELL_SLUGS
from .tarifwelt_pruefung import LAUFZEIT_MONATE, pruefe
from .tarifwelt_uebersicht import lies_uebersicht

log = logging.getLogger(__name__)

API = "https://tarife-api2.mediamarkt.de/v1/productdetail"
SEITE = "https://tarife.mediamarkt.de/smartphones"
KENNUNG = "TelcoRadar/1.0 (+https://telco-radar.onrender.com/ueber)"
PAUSE_SEKUNDEN = 2.0
MAX_KANDIDATEN = 3
KATALOG_SPEICHER = {1000: 1024, 2000: 2048}


def shop_url(pfad: str, slug: str, speicher: int, tarif_id: str, ids: dict) -> str:
    """Die Shop-Adresse, die GENAU diese Zeile zeigt. `speicher` und `tfi`
    allein reichen nicht: ohne `ogi`/`ofi`/`hwi` oeffnet der Shop die
    vorgewaehlte Variante (Messung 12.11.2026 im Browser: die alte Adresse
    `?speicher=512&tfi=...` des iPhone 17e zeigte 256 GB Black, "nicht
    verfuegbar", 189,99 EUR - einen anderen Speicher und einen anderen Preis
    als die Zeile). Mit den drei IDs zeigt dieselbe Seite 512 GB Soft Pink,
    419,99 EUR, "Versand in 2-4 Werktagen" - den Wert der Zeile."""
    return (
        f"{SEITE}/{pfad}/{slug}/?speicher={speicher}&tfi={tarif_id}"
        f"&ogi={ids['ogi']}&ofi={ids['ofi']}&hwi={ids['hwi']}"
    )


@dataclass
class Lauf:
    """Ergebnis eines Modells: Buendel, benannte Luecken (Variante -> Grund) und
    `tarife` (tarif_id "mediamarkt_tarifwelt:<id>" -> Anbieterzeile, Name,
    Datenvolumen, Grundgebuehr) fuer die Band-Zuordnung im Bericht
    (`tarifwelt_bestand`). `nicht_lieferbar`: (device_id, Katalogspeicher) jeder
    Stufe, die die Uebersicht als nicht lieferbar nennt (`tarifwelt_lieferbar`)."""

    buendel: list[Buendel] = field(default_factory=list)
    luecken: list[tuple[str, str]] = field(default_factory=list)
    abrufe: int = 0
    tarife: dict[str, dict] = field(default_factory=dict)
    nicht_lieferbar: list[tuple[str, int]] = field(default_factory=list)


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
    lauf: Lauf | None = None,
) -> Lauf:
    """Alle Speicher x Netz x Band eines Pflichtmodells (oder eines der
    zusaetzlichen, nicht ueberwachten Modelle, siehe Moduldoku). Ein mitgegebener
    `lauf` wird gefuellt: was vor einer Schutzantwort gelesen war, bleibt dort."""
    eintrag = MODELL_SLUGS[modell_id]
    hersteller, name, pfad, slug = eintrag[:4]
    api_name = eintrag[4] if len(eintrag) > 4 else name
    lauf = Lauf() if lauf is None else lauf
    uebersicht = lies_uebersicht(_abruf(hole, f"{API}/{slug}", lauf, warte))
    if uebersicht is None:
        lauf.luecken.append((modell_id, "Uebersicht nicht lesbar"))
        return lauf
    geraet = device_id(hersteller, name)
    for speicher in uebersicht["nicht_lieferbar"]:
        lauf.luecken.append((f"{modell_id} {speicher} GB", "nicht lieferbar"))
        lauf.nicht_lieferbar.append((geraet, KATALOG_SPEICHER.get(speicher, speicher)))
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
                (slug, speicher, variante, ids, api_name), kandidaten, hole, lauf, warte
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
            quelle_url = shop_url(pfad, slug, speicher, tarif["tarif_id"], ids)
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
    wo: tuple[str, int, str, dict, str],
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
    slug, speicher, variante, ids, name = wo
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
        grund, nicht_waehlbar = pruefe(satz, tarif, speicher, name, ids["hwi"])
        if grund is None:
            assert satz is not None
            return satz, tarif
        gruende.append(grund)
        if not nicht_waehlbar:
            break
    lauf.luecken.append((variante, "; ".join(gruende)))
    return None
