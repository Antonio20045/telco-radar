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

ALLE VERGLEICHBAREN TARIFE (20.11.2026): je Modell, Speicher und Tarif genau
eine Anfrage, dazu je Modell eine Uebersicht und je Speicher eine Tarifliste.
Frueher kam je Netz und Band nur EIN Tarif dran (vier bis acht Tarife je Netz
und Speicher blieben ungemessen). Vergleichbar heisst: keiner der Gruende aus
`tarifwelt_merkmale.unvergleichbar_grund` (Doppelkarte, Aktion, Young, Kids,
Senioren, Cashback, Preiswechsel vor Monat 25), ein bekanntes Netz und ein Band
der Vodafone-Leiter. Welcher Tarif eines Bandes der Seite gehoert, entscheidet
der Bericht, nicht das Sammeln. Zwischen zwei Anfragen liegt `PAUSE_SEKUNDEN`;
die Laufzeit waechst damit mit der Zahl der Tarife, das Zeitbudget der Stufe
steht in `geraete_tarifwelt` (`stufen_frist`).
Nie `/pks`, nie `/checkout`, keine Konten, kein Warenkorb.

Welches Katalogmodell zu welcher Tarifwelt-Seite gehoert, steht in
`tarifwelt_modelle.MODELL_SLUGS` (ausgelagert, weil die Zuordnungstabelle
allein schon lang ist - dort auch die Erfassungslücke von Baupaket P6).
Datenvolumen: unbegrenzt (`dataVolume: 0`) ist `inf`, wie im Tarifbestand.
Speicher: die Tarifwelt nennt 1 TB "1000 GB" (`KATALOG_SPEICHER`), der Katalog
und die Speicherprüfung des Wächters 1024; in der SKU steht die Katalogstufe,
in den Abrufen der Wert der Schnittstelle.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from ... import tarifwelt_bestand
from ...geraete_model import device_id, normalisiere, sku_id
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
PAUSE_SEKUNDEN = 1.0
"""Abstand Start zu Start zweier Anfragen, gleich `rate_limit_sekunden` der Quelle in
`config/geraete_quellen.yaml` (Test `test_geraete_tarifwelt_abstand_2111`). 1 s seit
dem 20.11.2026: kein Crawl-delay auf tarife.mediamarkt.de (nur Disallow /*/pks und
/*/checkout), tarife-api2.mediamarkt.de ohne robots.txt (404). Bis 21.11.2026 lagen
1 s nach dem Ende und 2 s Schleusen-Standard hintereinander: 2,0 s je Anfrage."""
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


@dataclass(frozen=True)
class Zeile:
    """Eine Zeile, die noch zu lesen ist: ein Tarif eines Speichers. `kern`: der
    Tarif, den die Auswahl vor dem 20.11.2026 allein las (siehe
    `tarifwelt.kern_je_netz_und_band`) - er kommt zuerst dran."""

    modell_id: str
    pfad: str
    geraet: str
    wo: tuple[str, int, str, dict, str]
    kandidat: dict
    zusatz: str
    kern: bool


@dataclass
class Lauf:
    """Ergebnis eines Modells: Buendel, benannte Luecken (Zeile -> Grund) und
    `tarife` (tarif_id "mediamarkt_tarifwelt:<id>" -> Anbieterzeile, Name,
    Datenvolumen, Grundgebuehr) fuer die Band-Zuordnung im Bericht
    (`tarifwelt_bestand`). `nicht_lieferbar`: (device_id, Katalogspeicher) jeder
    Stufe, die die Uebersicht belegt als nicht lieferbar nennt
    (`tarifwelt_lieferbar`). `offen`: Zeilen, die dieser Lauf noch nicht gelesen
    hat (`lies_offene`)."""

    buendel: list[Buendel] = field(default_factory=list)
    luecken: list[tuple[str, str]] = field(default_factory=list)
    abrufe: int = 0
    tarife: dict[str, dict] = field(default_factory=dict)
    nicht_lieferbar: list[tuple[str, int]] = field(default_factory=list)
    offen: list[Zeile] = field(default_factory=list)
    letzter_start: float = 0.0


def _abruf(hole: Callable, url: str, lauf: Lauf, warte: Callable[[float], None]) -> str:
    """EIN Abruf, ohne Wiederholung, `PAUSE_SEKUNDEN` nach dem Start des letzten.
    Schutzantwort: Ausnahme mit `schutz`."""
    if lauf.abrufe:
        warte(max(0.0, PAUSE_SEKUNDEN - (time.monotonic() - lauf.letzter_start)))
    lauf.abrufe += 1
    lauf.letzter_start = time.monotonic()
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


def vergleichbare_tarife(liste: list[dict], leiter_gb) -> list[dict]:
    """ALLE Tarife einer Tarifliste, die fuer den Vergleich taugen - je Netz
    und Speicher nicht mehr nur einer je Band. Es fallen nur weg (Regel,
    unveraendert aus der Zeit der Bandauswahl): unvergleichbare Tarife
    (`tarifwelt_merkmale.unvergleichbar_grund`: Doppelkarte, Aktion, Young,
    Kids, Senioren, Cashback, Preiswechsel vor Monat 25), unbekannte Netze
    und Tarife ohne Band (`tarifwelt.tarife_mit_band`). Reihenfolge: Netz, dann
    Datenvolumen, Monatspreis, ID."""
    brauchbar = [
        s
        for s in liste
        if unvergleichbar_grund(s) is None
        and tarifwelt.anbieter_zeile(s.get("netz")) is not None
    ]
    return sorted(
        tarifwelt.tarife_mit_band(brauchbar, leiter_gb),
        key=lambda s: s["netz"],
    )


def plain_halter(buendel: list[dict]) -> dict[tuple[str, str, str], set[str]]:
    """(Anbieterzeile, SKU, normierter Tarifname) -> Tarif-IDs, die diesen Namen im
    Bestand (`TcoDB.buendel()`) schon OHNE Zusatz tragen. Daran haengt die
    Kontinuitaet: ein frueher gesammelter Tarif behaelt seine Buendel-ID."""
    out: dict[tuple[str, str, str], set[str]] = {}
    for b in buendel:
        tid = str(b.get("tarif_id") or "")
        if tid.startswith(tarifwelt_bestand.PRAEFIX):
            schluessel = (
                str(b.get("anbieter") or ""),
                str(b.get("sku_id") or ""),
                normalisiere(str(b.get("tarif_name") or "")),
            )
            out.setdefault(schluessel, set()).add(tid[len(tarifwelt_bestand.PRAEFIX) :])
    return out


def namenszusaetze(
    tarife: list[dict], sku: str = "", bekannt: dict | None = None
) -> dict[str, str]:
    """tarif_id -> Zusatz hinter dem Tarifnamen ("" oder " (3f7a1c)").

    Die Buendel-ID entsteht aus dem Tarifnamen (`tco_model.buendel_id`), nicht
    aus der Tarif-ID. Fuehrt ein Netz mehrere Tarife unter demselben Namen
    (Telekom "Allnet Flat 50GB" zu 29,99 und 39,99 EUR, o2 "Mobile Unlimited L
    Promo" in fuenf Preisstufen), wuerde das spaetere Buendel das fruehere
    ueberschreiben. Der Zusatz kommt aus der Tarif-ID der Schnittstelle (stabil,
    bei o2 und Telekom ueber Wochen gleich), nie aus dem Preis: ein Preiswechsel
    aendert keine ID. Den Namen ohne Zusatz behaelt, wer ihn im Bestand fuer
    diese SKU schon traegt (`bekannt`, `plain_halter`; bei mehreren der mit der
    kleinsten ID) - so bleiben die IDs frueher gesammelter Tarife gleich. Ohne
    Halter bekommen alle einer Namensgruppe den Zusatz."""
    gruppen: dict[tuple[str, str], list[dict]] = {}
    for tarif in tarife:
        name = tarif.get("name") or tarif.get("tarif_name") or tarif["tarif_id"]
        gruppen.setdefault((tarif["netz"], normalisiere(name)), []).append(tarif)
    out: dict[str, str] = {}
    for (netz, norm), gruppe in gruppen.items():
        ids = [t["tarif_id"] for t in gruppe]
        if len(gruppe) == 1:
            out[ids[0]] = ""
            continue
        anbieter = tarifwelt.anbieter_zeile(netz) or ""
        halter = set(ids) & (bekannt or {}).get((anbieter, sku, norm), set())
        plain = min(halter) if halter else None
        rest = [i for i in ids if i != plain]
        laenge = 6
        while len({i[-laenge:] for i in rest}) < len(rest) and laenge < 64:
            laenge += 2
        for i in ids:
            out[i] = "" if i == plain else f" ({i[-laenge:]})"
    return out


def lies_modell(
    modell_id: str,
    leiter_gb,
    hole: Callable,
    abgerufen_am: str,
    warte: Callable[[float], None] = time.sleep,
    lauf: Lauf | None = None,
    nur_kern: bool = False,
    weiter: Callable[[], bool] = lambda: True,
    bekannt: dict | None = None,
) -> Lauf:
    """Alle Speicher x vergleichbaren Tarife eines Modells (Pflichtmodell oder
    zusaetzliches, nicht ueberwachtes Modell, siehe Moduldoku). Ein mitgegebener
    `lauf` wird gefuellt: was vor einer Schutzantwort gelesen war, bleibt dort.
    Uebersicht und Tarifliste je Speicher werden immer gelesen; die Tarife
    danach (`lies_offene`): mit `nur_kern` zuerst nur der Kern je Netz und Band,
    der Rest bleibt in `lauf.offen`. `weiter()` wird vor jedem Tarif gefragt;
    sagt es nein, bleibt der Tarif offen. `bekannt`: `plain_halter` des Bestands."""
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
    for speicher in uebersicht["belegt_nicht_lieferbar"]:
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
        tarife = vergleichbare_tarife(liste, leiter_gb)
        if not tarife:
            lauf.luecken.append((f"{modell_id} {speicher} GB", "keine Tarife"))
            continue
        sku = sku_id(geraet, KATALOG_SPEICHER.get(speicher, speicher), None)
        zusaetze = namenszusaetze(tarife, sku, bekannt)
        kern = tarifwelt.kern_je_netz_und_band(tarife, leiter_gb)
        for kandidat in tarife:
            variante = (
                f"{modell_id} {speicher} GB {kandidat['netz']} "
                f"{kandidat['tarif_name'] or kandidat['tarif_id']}"
            )
            lauf.offen.append(
                Zeile(
                    modell_id,
                    pfad,
                    geraet,
                    (slug, speicher, variante, ids, api_name),
                    kandidat,
                    zusaetze[kandidat["tarif_id"]],
                    kandidat["tarif_id"] in kern,
                )
            )
    return lies_offene(lauf, hole, abgerufen_am, warte, nur_kern, weiter)


def lies_offene(
    lauf: Lauf,
    hole: Callable,
    abgerufen_am: str,
    warte: Callable[[float], None] = time.sleep,
    nur_kern: bool = False,
    weiter: Callable[[], bool] = lambda: True,
) -> Lauf:
    """Liest die offenen Zeilen des Laufs - eine Anfrage je Tarif und Speicher.
    Mit `nur_kern` nur die Kernzeilen. Was nicht drankommt (`nur_kern`,
    `weiter()` sagt nein), bleibt in `lauf.offen`."""
    rest: list[Zeile] = []
    for stelle, zeile in enumerate(lauf.offen):
        if (nur_kern and not zeile.kern) or not weiter():
            rest.append(zeile)
            continue
        try:
            _lies_zeile(zeile, hole, abgerufen_am, lauf, warte)
        except GeraeteAbrufFehler:
            lauf.offen = [*rest, *lauf.offen[stelle:]]
            raise
    lauf.offen = rest
    return lauf


def _lies_zeile(
    zeile: Zeile,
    hole: Callable,
    abgerufen_am: str,
    lauf: Lauf,
    warte: Callable[[float], None],
) -> None:
    """Eine Zeile lesen: bei Erfolg ein Buendel samt Stammdaten des Tarifs, sonst
    die benannte Luecke aus `_lies_tarif`."""
    slug, speicher, _, ids, _ = zeile.wo
    kandidat = zeile.kandidat
    satz = _lies_tarif(zeile.wo, kandidat, hole, lauf, warte)
    if satz is None:
        return
    tarif_name = (satz["tarif_name"] or satz["tarif_id"]) + zeile.zusatz
    lauf.tarife[f"mediamarkt_tarifwelt:{satz['tarif_id']}"] = {
        "anbieter": tarifwelt.anbieter_zeile(satz["netz"]) or "",
        "name": tarif_name,
        "datenvolumen_gb": kandidat["datenvolumen_gb"],
        "grundgebuehr": satz["grundgebuehr"],
    }
    quelle_url = shop_url(zeile.pfad, slug, speicher, kandidat["tarif_id"], ids)
    lauf.buendel.append(
        Buendel(
            sku_id=sku_id(zeile.geraet, KATALOG_SPEICHER.get(speicher, speicher), None),
            anbieter=tarifwelt.anbieter_zeile(satz["netz"]) or "",
            tarif_name=tarif_name,
            tarif_id=f"mediamarkt_tarifwelt:{satz['tarif_id']}",
            tarif_id_guete="niedrig",
            tarif_monatlich=satz["grundgebuehr"],
            geraet_zuzahlung=satz["geraet_zuzahlung"],
            geraet_monatsrate=satz["geraet_monatsrate"],
            laufzeit_monate=LAUFZEIT_MONATE,
            anschlusspreis=satz["anschlusspreis"],
            quelle_url=quelle_url,
            abgerufen_am=abgerufen_am,
            herleitung="tarifwelt_productdetail",
            zustand="neu",
            aktionen=wechselbonus_aktionen(satz.get("hinweise"), quelle_url),
        )
    )


def _lies_tarif(
    wo: tuple[str, int, str, dict, str],
    tarif: dict,
    hole: Callable,
    lauf: Lauf,
    warte: Callable[[float], None],
) -> dict | None:
    """EIN Tarif, EINE Anfrage: der gelesene Satz oder `None` mit einer
    benannten Luecke. Die Schnittstelle fuehrt Tarife auf, die fuer ein Geraet
    eine leere Huelle liefern (Tarif-ID leer) oder einen anderen Speicher
    antworten - das ist "nicht waehlbar" und steht als Luecke mit diesem
    Grund. Jeder andere Mangel (Abruffehler, Laufzeit, Doppelkarte,
    fehlender Betrag) ist die Luecke dieser Zeile, nie ein Preis. Ein
    Tarif kommt je Speicher genau einmal dran (die Liste ist je `tarif_id`
    eindeutig, `tarifwelt.tarife_mit_band`)."""
    slug, speicher, variante, ids, name = wo
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
    grund, _ = pruefe(satz, tarif, speicher, name, ids["hwi"])
    if grund is None:
        assert satz is not None
        return satz
    lauf.luecken.append((variante, grund))
    return None
