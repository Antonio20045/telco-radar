"""Lieferzeit- und Verfuegbarkeits-Radar.

Es existiert **keine oeffentliche Studie, die Lieferzeiten der deutschen
Telko-Anbieter systematisch vergleicht.** Was es gibt, sind Selbstauskuenfte
auf Hilfeseiten, Beschwerdethreads und Launch-Tag-Berichte. Wer das
systematisch erfasst, hat Wissen, das sonst niemand hat.

Die Kaskade - und was von ihr wirklich uebrig bleibt
----------------------------------------------------
Absteigend nach Robustheit:

  1. **JSON-LD** (`Product`/`Offer` mit `OfferShippingDetails`). schema.org
     definiert dort `deliveryTime` aus `handlingTime` und `transitTime` - der
     stabilste und unauffaelligste Weg, weil er ausdruecklich fuer Maschinen
     bereitgestellt wird.
     **GEMESSEN am 08.08.2026: die deutschen Telko-Shops binden das nicht
     ein.** winSIM liefert ein sauberes `Product` samt `Offer`, aber ohne
     `OfferShippingDetails` und ohne `deliveryTime`. Die Stufe bleibt
     trotzdem im Code: sie kostet nichts, sie ist die richtige, und wenn ein
     Shop sie nachruestet, greift sie ohne Aenderung hier.
  2. **Selektor** auf dem gerenderten DOM. Lieferzeit-Bausteine werden
     typischerweise nachgeladen; otelo traegt seine Zustaende in einem
     JavaScript-Woerterbuch mit Platzhaltern ("Lieferzeit ca.
     {DELIVERY_TIME} Tage"). In GitHub Actions rendert Playwright, lokal
     nicht - deshalb `braucht_browser` je Seite.
  3. **Regex auf dem Volltext.** "Lieferung in 2-3 Werktagen", "sofort
     lieferbar", "voraussichtlich ab ...". Das ist die Stufe, die winSIM und
     PremiumSIM heute schon beantwortet.

Warum die Methode mitgespeichert wird
-------------------------------------
Weil sie die Belastbarkeit bestimmt. Eine Zahl aus JSON-LD und eine Zahl aus
einem Regex ueber Fliesstext sind nicht dasselbe, auch wenn beide "3" heissen.
Bei niedriger Belastbarkeit oder einem Ausreisser geht die Beobachtung in
QUARANTAENE statt auf die Seite - derselbe Belegzwang, der bei der
Differenzierung schon gilt.

Frequenz
--------
Zweimal die Woche, im Launch-Fenster eines Flaggschiffs taeglich. Bewusst
niedrig: das schont die Zielsysteme, vermeidet Bot-Abwehr und stuetzt die
Position, falls jemand fragt.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path

import yaml
from bs4 import BeautifulSoup

from .http import fetch

log = logging.getLogger(__name__)

HOCH, MITTEL, NIEDRIG = "hoch", "mittel", "niedrig"

# Mehr als das ist keine Lieferzeit mehr, sondern eine Vorbestellung mit
# offenem Termin oder ein Lesefehler. Solche Werte gehen in Quarantaene.
MAX_PLAUSIBLE_TAGE = 90

# Ab wann ein Sprung als Lagerengpass gilt - das eigentliche Signal, auf das
# es ankommt. "2-3 Werktage" auf "mehrere Wochen" ist die Meldung, nicht die
# absolute Zahl.
ENGPASS_AB_TAGEN = 10
ENGPASS_SPRUNG = 5

# Wie viele Beobachtungen je Produkt und Anbieter aufbewahrt werden. Eine
# Zeitreihe braucht Tiefe, eine JSON-Datei im Repo braucht ein Ende.
MAX_HISTORIE = 120

_ENTFERNEN = ("script", "style", "noscript", "svg", "iframe")

# "1-3 Werktage", "2 bis 4 Werktagen", "ca. 14 Tage"
_SPANNE = re.compile(
    r"(\d{1,3})\s*(?:-|–|bis)\s*(\d{1,3})\s*(Werktage[n]?|Tage[n]?|Wochen?)",
    re.I)
_EINZEL = re.compile(
    r"(?:ca\.?\s*|circa\s*|innerhalb von\s*|in\s*)?(\d{1,3})\s*"
    r"(Werktage[n]?|Tage[n]?|Wochen?)", re.I)
_SOFORT = re.compile(r"sofort (?:lieferbar|versandfertig)|auf Lager", re.I)
_NICHT_LIEFERBAR = re.compile(
    r"(nicht|derzeit nicht|momentan nicht)\s+(lieferbar|verf[üu]gbar)|"
    r"ausverkauft|vorbestell", re.I)

# Der Kontext, in dem eine Zahl ueberhaupt eine Lieferzeit sein KANN. Ohne
# ihn liest der Regex "24 Monate Laufzeit" als Lieferzeit.
_KONTEXT = re.compile(
    r"(liefer|versand|zustell|ankunft|verf[üu]gbar|lager)", re.I)

_TAGE_JE_EINHEIT = {"woche": 7, "wochen": 7}


@dataclass
class Beobachtung:
    """Ein Messpunkt. Absichtlich flach - er wird als JSON abgelegt."""

    produkt_ref: str
    produkt_name: str
    anbieter: str
    url: str
    zeitstempel: str
    verfuegbarkeit: str = ""          # "sofort" | "verzoegert" | "nein" | ""
    lieferzeit_roh: str = ""          # der Originaltext, immer mitgefuehrt
    tage_min: int | None = None
    tage_max: int | None = None
    methode: str = ""                 # jsonld | selektor | text
    belastbarkeit: str = NIEDRIG
    plz: str = ""
    quarantaene: str = ""             # Grund, wenn nicht veroeffentlicht

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Produkt:
    ref: str
    name: str
    variante: str = ""
    typ: str = ""


@dataclass
class AnbieterSeite:
    marke: str
    produkt: str
    url: str
    selector: str = ""
    braucht_browser: bool = False


@dataclass
class Warenkorb:
    test_plz: str = ""
    produkte: list[Produkt] = field(default_factory=list)
    seiten: list[AnbieterSeite] = field(default_factory=list)
    anbieter_meta: dict[str, dict] = field(default_factory=dict)

    def produkt(self, ref: str) -> Produkt | None:
        return next((p for p in self.produkte if p.ref == ref), None)


def lade_warenkorb(root: Path) -> Warenkorb:
    pfad = Path(root) / "config" / "lieferzeit_warenkorb.yaml"
    if not pfad.exists():
        return Warenkorb()
    daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    korb = Warenkorb(test_plz=str(daten.get("test_plz") or ""))
    korb.produkte = [Produkt(ref=str(p.get("ref")), name=str(p.get("name")),
                             variante=str(p.get("variante") or ""),
                             typ=str(p.get("typ") or ""))
                     for p in (daten.get("produkte") or []) if p.get("ref")]
    for a in (daten.get("anbieter") or []):
        marke = str(a.get("marke") or "")
        korb.anbieter_meta[marke] = {
            "ident": str(a.get("ident") or ""),
            "getrennte_sendung": bool(a.get("getrennte_sendung")),
        }
        for s in (a.get("seiten") or []):
            if s.get("url"):
                korb.seiten.append(AnbieterSeite(
                    marke=marke, produkt=str(s.get("produkt") or ""),
                    url=str(s.get("url")),
                    selector=str(s.get("selector") or ""),
                    braucht_browser=bool(s.get("braucht_browser"))))
    return korb


# ------------------------------------------------------------- Extraktion

def aus_jsonld(html: str) -> tuple[str, int | None, int | None] | None:
    """`OfferShippingDetails.deliveryTime` aus schema.org, wenn vorhanden.

    Die robusteste Stufe - und die, die im deutschen Telko-Handel derzeit
    niemand ausliefert (gemessen 08.08.2026). Sie bleibt trotzdem hier: sie
    kostet einen Regex, und wer sie nachruestet, wird ohne Codeaenderung
    gelesen.
    """
    for treffer in re.finditer(
            r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>',
            html or "", re.S | re.I):
        try:
            daten = json.loads(treffer.group(1))
        except (json.JSONDecodeError, TypeError):
            continue
        for knoten in _knoten(daten):
            versand = knoten.get("shippingDetails") or knoten.get(
                "OfferShippingDetails")
            if not isinstance(versand, dict):
                continue
            zeit = versand.get("deliveryTime")
            if not isinstance(zeit, dict):
                continue
            gesamt = _summe_tage(zeit)
            if gesamt:
                return f"schema.org deliveryTime {gesamt[0]}-{gesamt[1]} Tage", \
                    gesamt[0], gesamt[1]
    return None


def _knoten(daten) -> list[dict]:
    """Alle Objekte eines JSON-LD-Baums, flach."""
    out: list[dict] = []
    stapel = [daten]
    while stapel:
        k = stapel.pop()
        if isinstance(k, dict):
            out.append(k)
            stapel.extend(k.values())
        elif isinstance(k, list):
            stapel.extend(k)
    return out


def _summe_tage(zeit: dict) -> tuple[int, int] | None:
    tage_min = tage_max = 0
    gefunden = False
    for feld in ("handlingTime", "transitTime"):
        wert = zeit.get(feld)
        if isinstance(wert, dict):
            try:
                tage_min += int(wert.get("minValue", 0) or 0)
                tage_max += int(wert.get("maxValue", 0) or 0)
                gefunden = True
            except (TypeError, ValueError):
                continue
    return (tage_min, tage_max or tage_min) if gefunden else None


def aus_text(text: str) -> tuple[str, str, int | None, int | None] | None:
    """(Originaltext, Verfuegbarkeit, min, max) aus dem Fliesstext.

    Der Kontexttest ist der Punkt: ohne ihn liest der Regex "24 Monate
    Laufzeit" oder "14 Tage Widerrufsrecht" als Lieferzeit. Gesucht wird
    deshalb nur in Saetzen, die ueberhaupt von Lieferung, Versand,
    Verfuegbarkeit oder Lager sprechen.
    """
    if not text:
        return None
    # Getrennt wird an Zeilen und Trennzeichen, NICHT am Punkt: "Nicht auf
    # Lager (Lieferzeit ca. 14 Tage)" zerfiel dabei am "ca." in zwei Teile,
    # und der erste las sich als "auf Lager" - also als sofort lieferbar,
    # wo das Gegenteil dasteht.
    for satz in re.split(r"[\n]+|\s*[·|]\s*", text):
        if not _KONTEXT.search(satz):
            continue
        roh = " ".join(satz.split())[:160]
        if _NICHT_LIEFERBAR.search(satz):
            return roh, "nein", None, None
        m = _SPANNE.search(satz)
        if m:
            faktor = _TAGE_JE_EINHEIT.get(m.group(3).lower(), 1)
            return (roh, _lage(int(m.group(2)) * faktor),
                    int(m.group(1)) * faktor, int(m.group(2)) * faktor)
        m = _EINZEL.search(satz)
        if m:
            faktor = _TAGE_JE_EINHEIT.get(m.group(2).lower(), 1)
            tage = int(m.group(1)) * faktor
            return roh, _lage(tage), tage, tage
        if _SOFORT.search(satz):
            return roh, "sofort", 0, 0
    return None


def _lage(tage_max: int) -> str:
    """Bis zu drei Tage heisst "sofort" - so nennen es die Anbieter selbst
    ("Sofort lieferbar, Lieferzeit 1-3 Werktage"). Alles darueber ist eine
    Wartezeit, und zwar auch dann, wenn die Seite daneben "sofort" schreibt."""
    return "sofort" if tage_max <= 3 else "verzoegert"


def _text(html: str, selector: str = "") -> str:
    suppe = BeautifulSoup(html or "", "html.parser")
    for tag in suppe.find_all(_ENTFERNEN):
        tag.decompose()
    bereich = suppe.select_one(selector) if selector else None
    return (bereich or suppe).get_text("\n", strip=True)


def beobachte(html: str, seite: AnbieterSeite, produkt: Produkt,
              plz: str, jetzt: datetime) -> Beobachtung:
    """Eine Seite auswerten. Setzt Methode, Belastbarkeit und Quarantaene."""
    b = Beobachtung(
        produkt_ref=produkt.ref, produkt_name=produkt.name,
        anbieter=seite.marke, url=seite.url,
        zeitstempel=jetzt.isoformat(timespec="seconds"), plz=plz)

    treffer = aus_jsonld(html)
    if treffer:
        b.lieferzeit_roh, b.tage_min, b.tage_max = treffer
        b.methode, b.belastbarkeit = "jsonld", HOCH
        b.verfuegbarkeit = "sofort" if (b.tage_max or 0) <= 3 else "verzoegert"
    else:
        quelle = _text(html, seite.selector)
        gelesen = aus_text(quelle)
        if not gelesen:
            b.quarantaene = "keine Lieferzeitangabe gefunden"
            return b
        b.lieferzeit_roh, b.verfuegbarkeit, b.tage_min, b.tage_max = gelesen
        b.methode = "selektor" if seite.selector else "text"
        b.belastbarkeit = MITTEL if seite.selector else NIEDRIG

    if b.tage_max is not None and b.tage_max > MAX_PLAUSIBLE_TAGE:
        b.quarantaene = f"{b.tage_max} Tage - unplausibel"
    # Ein Platzhalter, der durchgerutscht ist, ist keine Messung.
    if "{" in b.lieferzeit_roh or "}" in b.lieferzeit_roh:
        b.quarantaene = "Platzhalter statt Wert (Seite baut per JavaScript auf)"
    return b


# ------------------------------------------------------------------ Speicher

class Lieferzeitspeicher:
    """Die Zeitreihe je Produkt und Anbieter."""

    def __init__(self, pfad: Path):
        self.pfad = pfad
        self.daten: dict = {"reihen": {}}
        if pfad.exists():
            try:
                self.daten = json.loads(pfad.read_text(encoding="utf-8"))
                self.daten.setdefault("reihen", {})
            except json.JSONDecodeError:
                log.warning("lieferzeit.json unlesbar - beginne neu")

    @staticmethod
    def _key(produkt_ref: str, anbieter: str) -> str:
        return f"{produkt_ref}|{anbieter}"

    def reihe(self, produkt_ref: str, anbieter: str) -> list[dict]:
        return self.daten["reihen"].get(self._key(produkt_ref, anbieter)) or []

    def letzte(self, produkt_ref: str, anbieter: str) -> dict | None:
        reihe = [b for b in self.reihe(produkt_ref, anbieter)
                 if not b.get("quarantaene")]
        return reihe[-1] if reihe else None

    def anhaengen(self, b: Beobachtung) -> None:
        key = self._key(b.produkt_ref, b.anbieter)
        reihe = self.daten["reihen"].setdefault(key, [])
        reihe.append(b.to_dict())
        del reihe[:-MAX_HISTORIE]

    def speichern(self, stand: str) -> None:
        self.daten["stand"] = stand
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        self.pfad.write_text(
            json.dumps(self.daten, ensure_ascii=False, indent=1),
            encoding="utf-8")


def ist_engpass(vorher: dict | None, jetzt: Beobachtung) -> bool:
    """Der Sprung, auf den es ankommt: "2-3 Werktage" auf "mehrere Wochen".

    Nicht die absolute Zahl - manche Anbieter liefern grundsaetzlich in zehn
    Tagen, und das ist keine Nachricht. Die Nachricht ist die Veraenderung.
    """
    if jetzt.tage_max is None or jetzt.quarantaene:
        return False
    if jetzt.tage_max < ENGPASS_AB_TAGEN:
        return False
    if not vorher or vorher.get("tage_max") is None:
        return False
    return jetzt.tage_max - int(vorher["tage_max"]) >= ENGPASS_SPRUNG


def sammle(root: Path, http_cfg: dict, *, jetzt: datetime | None = None,
           hole=None) -> dict:
    """Den ganzen Warenkorb messen. Liefert die Bilanz fuers Laufprotokoll.

    `hole` ist der Abrufer - in Tests eine Attrappe, sonst `fetch`.
    """
    jetzt = jetzt or datetime.now(timezone.utc)
    hole = hole or (lambda url: fetch(url, http_cfg).text)
    korb = lade_warenkorb(root)
    speicher = Lieferzeitspeicher(Path(root) / "data" / "state" /
                                  "lieferzeit.json")
    bilanz = {"seiten": len(korb.seiten), "gemessen": 0, "quarantaene": 0,
              "fehler": 0, "engpaesse": []}

    for seite in korb.seiten:
        produkt = korb.produkt(seite.produkt)
        if produkt is None:
            log.warning("Lieferzeit: Seite %s verweist auf unbekanntes "
                        "Produkt %r", seite.url, seite.produkt)
            continue
        try:
            html = hole(seite.url)
        except Exception as exc:  # noqa: BLE001
            bilanz["fehler"] += 1
            log.info("Lieferzeit %s (%s) nicht abrufbar: %s",
                     seite.marke, produkt.name, str(exc)[:110])
            continue
        b = beobachte(html, seite, produkt, korb.test_plz, jetzt)
        vorher = speicher.letzte(produkt.ref, seite.marke)
        if ist_engpass(vorher, b):
            bilanz["engpaesse"].append(
                f"{seite.marke} / {produkt.name}: "
                f"{vorher.get('tage_max')} -> {b.tage_max} Tage")
        speicher.anhaengen(b)
        if b.quarantaene:
            bilanz["quarantaene"] += 1
        else:
            bilanz["gemessen"] += 1

    speicher.speichern(jetzt.date().isoformat())
    log.info("Lieferzeit-Radar: %d Seiten, %d gemessen, %d Quarantaene, "
             "%d Fehler%s", bilanz["seiten"], bilanz["gemessen"],
             bilanz["quarantaene"], bilanz["fehler"],
             (" | ENGPASS: " + "; ".join(bilanz["engpaesse"]))
             if bilanz["engpaesse"] else "")
    return bilanz
