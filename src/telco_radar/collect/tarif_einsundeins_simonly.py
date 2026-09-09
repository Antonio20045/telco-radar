"""1&1 SIM-only-Referenzen von der SIM-only-Seite des Anbieters.

WARUM ES DIESEN ZWEITEN WEG UEBERHAUPT GIBT (S-5, 09.09.2026)
----------------------------------------------------------------
Die SIM-only-Referenzen fuer 1&1 standen bis heute im Fusstapfen des
Tarif-Sammlers: Sie entstanden aus dem ld+json-Graphen von
`/handytarife` (collect/tarif_ldjson.py) - der Seite MIT Handy. Der
Anbieter traegt denselben Graph zwar auch auf seine SIM-only-Seite,
aber eben NUR den Graphen: Name und Grundgebuehr, keine Phase, kein
Volumen im Datensatz, kein Anschlusspreis. Genau diese Felder stehen
auf `/handytarife-ohne-handy` sichtbar in den Tarifkacheln - und der
Anschlusspreis steht in dem Tarifdetails-Dokument, das die Seite JE
KACHEL selbst verlinkt.

Dieses Modul misst die SIM-only-Seite direkt und vollstaendiger:

* **Monatspreis** aus der Kachel (Kreuzzeug: derselbe Betrag muss im
  ld+json-Graph derselben Seite stehen - stimmen beide nicht ueberein,
  ist die Messung mehrdeutig, und der Tarif bleibt WEG, nicht geraten).
* **Aktionsphase** aus der Kachel ("3 Monate je 9,99 EUR") als `Rabatt`
  mit von/bis-Monat. Der Betrag im Referenzsatz bleibt der Dauerpreis:
  `Rabatt` wird nirgends eingerechnet, und eine Referenz, die fuer 24
  Monate mit einem 3-Monats-Aktionspreis rechnen wuerde, waere falsch.
* **Volumen** aus dem `aria-label` der Kachel ("10 GB pro Monat").
* **Anschlusspreis** aus dem verlinkten Tarifdetails-Dokument, Zeile
  "Einmalige Bereitstellungsgebuehr - Tarif ohne Smartphone" (19,90 EUR;
  Unlimited XL: 39,90 EUR - tarifabhaengig, deshalb EIN Abruf je Tarif).
* **Bindungsdauer: ehrlich leer.** Weder die Seite noch das
  Tarifdetails-Dokument ordnen dem gemessenen Preis eine Laufzeit zu -
  das Dokument beschreibt BEIDE Varianten ("Tarif mit Laufzeit: [...]
  24 Monaten" / "Tarif ohne Laufzeit: keine Mindestvertragslaufzeit")
  ohne Zuordnung, und der Radio-Slug ("mvl"/"ovl") ist eine interne
  Abkuerzung des Anbieters, keine Angabe ueber den gepreissten Tarif.

ROBOTS (09.09.2026 gelesen, Absender TelcoRadar/1.0)
----------------------------------------------------
`www.1und1.de`: `User-agent: *`, gesperrt sind `/.well-known/`, `/france/`,
`/xml/`, `/static/`, `/suche*` und Tracking-Parameter;
`/handytarife-ohne-handy` ist frei. `mobile.1und1.de`: gesperrt sind
`/xml/`, `/static/`, `/modules/` und Bestell-/Bewertungsseiten; der
Tarifdetails-Pfad ist frei. Kein Crawl-delay auf einer der beiden
Domains - `sammle()` haelt trotzdem einen Abstand von 2 Sekunden
zwischen zwei Abrufen ein (dieselbe Zahl wie
`einsundeins._GEBUEHR_ABSTAND` im Geraetezweig) und nimmt ein
Crawl-delay auf, sobald der Anbieter eines schreibt
(`RobotsWaechter.abstand`, derselbe Waechter wie im Geraetezweig).

NUR VERLINKTE ADRESSEN (dieselbe Regel wie beim Tarif-Sammler, § 87b
UrhG): Die Tarifdetails-URL steht im `data-iframe`-Attribut der jeweiligen
Kachel - nichts wird hochgezaehlt oder kombiniert.

DIE GRENZE DIESER MESSUNG
-------------------------
Die Kacheln stehen mehrfach auf der Seite (Hero-Slider, Vergleich,
weitere Sektionen). Gezaehlt wird je Tarif-SLUG genau einmal; ein
zweiter Fund mit abweichendem Preis waere eine Mehrdeutigkeit und
wird gemeldet, nicht gemittelt.
"""
from __future__ import annotations

import html as html_modul
import logging
import re
import time
from typing import Callable, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..tarif_model import HOCH, PREISTYP_LIVE_SHOP, zahl
from ..tco_model import Rabatt, SimOnlyReferenz
from .geraete.robots import RobotsWaechter
from .tarif_crawler import tarif_id
from .tarif_ldjson import tarife_aus_html

log = logging.getLogger(__name__)

SEITEN_URL = "https://www.1und1.de/handytarife-ohne-handy"

# Der Absender dieses Laufs (BRIEF S-5). Er weicht vom Per-Anbieter-
# Override im Geraetezweig nur im Kontakt-Zusatz ab - beide sind
# ehrliche Kennungen im Sinne von `collect.http._ist_ehrliche_kennung`.
USER_AGENT = "TelcoRadar/1.0 (+https://telco-radar.onrender.com/ueber)"

ANBIETER = "1&1"

# Kein Crawl-delay in den robots beider Domains - der Abstand ist unsere
# eigene Zurueckhaltung, dieselbe wie bei der Bereitstellungsgebuehr im
# Geraetezweig (`einsundeins._GEBUEHR_ABSTAND`).
_ABSTAND_SEKUNDEN = 2.0

# "10 GB pro Monat" -> 10.0. "Unlimited pro Monat" trifft das Muster
# nicht - unbegrenztes Volumen ist keine GB-Zahl und wird nicht zu einer
# gemacht (die Referenz traegt dann kein `volumen_gb`).
_VOLUMEN_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*GB\b", re.I)

# "3 Monate je 9,99 €" -> (3, 9.99)
_AKTION_RE = re.compile(r"(\d+)\s*Monate?\s+je\s*([0-9][0-9.,]*)")

# Im Tarifdetails-Dokument (S2-C hat die Zeile "Tarif mit Smartphone"
# schon im Geraetezweig; hier ist die OHNE-Smartphone-Zeile die richtige
# - eine SIM-only-Referenz hat kein Geraet).
_GEBUEHR_RE = re.compile(r"Einmalige Bereitstellungsgebühr")
_OHNE_SMARTPHONE_RE = re.compile(
    r"Tarif ohne Smartphone:?\s*</strong>\s*([^<]{1,40})")
_GEBUEHR_FENSTER = 2000


def anschlusspreis_aus_details(text: str) -> Optional[float]:
    """Die Bereitstellungsgebuehr des Tarifs OHNE Smartphone.

    None, wenn das Dokument die Zeile nicht traegt - ein fehlender
    Betrag wird nie angenommen (Regel E1).
    """
    roh = text or ""
    anfang = _GEBUEHR_RE.search(roh)
    if not anfang:
        return None
    treffer = _OHNE_SMARTPHONE_RE.search(roh, anfang.end(),
                                         anfang.end() + _GEBUEHR_FENSTER)
    if not treffer:
        return None
    return zahl(html_modul.unescape(treffer.group(1)))


def _preisliste_url(kachel) -> str:
    """Die Tarifdetails-Adresse der Kachel - die mit dem Tarif-Slug.

    Eine Kachel traegt MEHRERE `data-iframe`-Verweise (09.09.2026
    gemessen): die Preisliste des Tarifs (`?chosenTariff=<slug>`, am
    Sternchen des Preises) und daneben Erklaer-Lightboxen wie
    `DetailsUnlimited`. Die Gebuehr steht nur in der Preisliste, deshalb
    gewinnt das erste `data-iframe` MIT `chosenTariff=` - der Parameter,
    den der Anbieter selbst setzt, nicht wir. Ohne ihn bleibt die erste
    verlinkte Adresse stehen.
    """
    for knoten in kachel.select("[data-iframe]"):
        adresse = (knoten.get("data-iframe") or "").strip()
        if "chosenTariff=" in html_modul.unescape(adresse):
            return adresse
    erster = kachel.select_one("[data-iframe]")
    return (erster.get("data-iframe") or "").strip() if erster else ""


def _preis_aus_kachel(kachel) -> Optional[float]:
    """Der Monatspreis der Kachel aus ihren Ziffern- und Cent-Spannen.

    1&1 zerlegt den Betrag im Markup in drei Teile ("14" "," "99") - das
    Komma steht in einem EIGENEN Span und wuerde von `get_text` mit
    gelesen, also wird es abgetrennt statt ignoriert. Zusammengesetzt ist
    das derselbe Betrag wie im ld+json, und genau diese Uebereinstimmung
    prueft `referenzen_aus_html` unten als Kreuzzeug.
    """
    ziffern = kachel.select_one(".price__digits")
    dezimal = kachel.select_one(".price__decimals")
    if ziffern is None:
        return None
    roh = "".join(ziffern.stripped_strings).rstrip(",")
    if dezimal is not None:
        roh += f",{dezimal.get_text('', strip=True)}"
    return zahl(roh)


def kacheln(html: str) -> list[dict]:
    """Die Tarifkacheln der Seite, je Tarif-Slug genau einmal.

    Zurueck kommen Rohdiktate mit slug, name, dauerpreis, aktion
    (optional), volumen_gb, dauerhaft und der verlinkten Tarifdetails-
    Adresse. Die Kacheln stehen mehrfach auf der Seite - ein zweiter
    Fund fuer denselben Slug muss denselben Preis nennen, sonst ist die
    Seite in sich mehrdeutig und der Slug bleibt weg.
    """
    suppe = BeautifulSoup(html or "", "html.parser")
    gesehen: dict[str, dict] = {}
    mehrdeutig: set[str] = set()
    for kachel in suppe.select("div.content-box"):
        marke = kachel.select_one("input.toggle-label__radio")
        if marke is None or not (marke.get("value") or "").strip():
            continue
        slug = str(marke["value"]).strip()
        details_url = _preisliste_url(kachel)
        titel = kachel.select_one("[title^='Tarifdetails']")
        name = html_modul.unescape(
            re.sub(r"^Tarifdetails\s*", "", titel.get("title", ""))
        ).strip() if titel else ""
        if not name:
            # Ohne kanonischen Namen keine stabile `sim_only_id` - der
            # Slug allein ist eine interne Abkuerzung, kein Name.
            continue
        preis = _preis_aus_kachel(kachel)
        fußtext = kachel.select_one(".price__bottom-text")
        eintrag = {
            "slug": slug,
            "name": name,
            "dauerpreis": preis,
            "volumen_gb": None,
            "aktion": None,
            # Das Etikett "DAUERHAFT" sagt, dass der Kachelpreis kein
            # befristeter ist. Eine Kachel MIT Aktionsphase traegt es
            # nicht - ihr Dauerpreis steht daneben, die Phase im
            # `text-with-bg-secondary`-Kasten.
            "dauerhaft": fußtext is not None
            and "DAUERHAFT" in fußtext.get_text("", True),
            "details_url": details_url,
        }
        volumen_text = kachel.get("aria-label") or ""
        treffer = _VOLUMEN_RE.search(html_modul.unescape(volumen_text))
        if treffer:
            eintrag["volumen_gb"] = zahl(treffer.group(1))
        aktion_text = kachel.select_one(".text-with-bg-secondary")
        if aktion_text is not None:
            aktion = _AKTION_RE.search(
                html_modul.unescape(aktion_text.get_text(" ", strip=True)))
            if aktion:
                eintrag["aktion"] = (int(aktion.group(1)),
                                     zahl(aktion.group(2)))
        vorher = gesehen.get(slug)
        if vorher is None:
            gesehen[slug] = eintrag
        elif any(vorher.get(f) != eintrag.get(f)
                 for f in ("name", "dauerpreis", "aktion", "volumen_gb")):
            # Der ganze Messwert, nicht nur der Preis: dieselbe Kachel mit
            # einer ANDEREN Aktionsphase oder einem anderen Volumen ist
            # genausowenig eindeutig wie mit einem anderen Preis.
            mehrdeutig.add(slug)
    for slug in mehrdeutig:
        log.warning("1&1 SIM-only: Kachel %s nennt auf der Seite zwei "
                    "unterschiedliche Preise - Tarif bleibt weg", slug)
        gesehen.pop(slug, None)
    return list(gesehen.values())


def _ldjson_zeugen(html: str) -> dict[str, float]:
    """Name -> Grundgebuehr aus dem ld+json-Graphen derselben Seite.

    Das Kreuzzeug dazu: 1&1 traegt denselben Graphen auf mehrere Seiten,
    und der Tarif-Sammler liest ihn auf `/handytarife` bereits. Stimmt
    der Kachelpreis nicht mit dem Graphen ueberein, ist unklar, welcher
    von beiden der Preis ohne Geraet ist - dann bleibt der Tarif weg.
    Gelesen wird mit demselben Parser wie beim Tarif-Sammler
    (`tarif_ldjson.tarife_aus_html`) - ein zweiter ld+json-Leser waere
    eine zweite Rechnung fuer dieselbe Zahl.
    """
    zeugen: dict[str, float] = {}
    for tarif, _hash in tarife_aus_html(html, anbieter=ANBIETER,
                                        seiten_url=SEITEN_URL,
                                        abgerufen_am=""):
        if tarif.grundgebuehr is not None:
            zeugen.setdefault(tarif.name, tarif.grundgebuehr)
    return zeugen


def referenzen_aus_html(html: str, *, seiten_url: str = SEITEN_URL,
                        details: Optional[dict[str, str]] = None,
                        abgerufen_am: str = ""
                        ) -> list[SimOnlyReferenz]:
    """Die SIM-only-Referenzen einer Seitenantwort.

    `details` ordnet je Tarif-Slug den Text des verlinkten
    Tarifdetails-Dokuments zu (oder fehlt/ist leer - dann bleibt der
    Anschlusspreis ehrlich offen). Kein Netz: diese Funktion ist ein
    reiner Text-zu-Daten-Uebersetzer, das Abrufen macht `sammle()`.
    """
    zeugen = _ldjson_zeugen(html)
    referenzen: list[SimOnlyReferenz] = []
    for kachel in kacheln(html):
        name = kachel["name"]
        preis = kachel["dauerpreis"]
        zeuge = zeugen.get(name)
        if preis is None:
            log.info("1&1 SIM-only: Kachel %r nennt keinen Preis - "
                     "bleibt weg", name)
            continue
        if zeuge is None:
            # Das Kreuzzeug ist weg (ld+json-Namen driften von den
            # Kacheltiteln) - der Preis steht dann allein. Er bleibt
            # stehen, aber der Verfall der Gegenprobe wird gemeldet, sonst
            # faelle er erst auf, wenn er laengst nichts mehr absichert.
            log.warning("1&1 SIM-only: kein ld+json-Zeuge fuer %r - "
                        "Kachelpreis ungegengeprobt", name)
        elif abs(zeuge - preis) > 0.005:
            log.warning("1&1 SIM-only: Kachel sagt %s €, ld+json %s € fuer "
                        "%r - mehrdeutig, Tarif bleibt weg",
                        preis, zeuge, name)
            continue
        anschluss = None
        details_text = (details or {}).get(kachel["slug"])
        if details_text:
            anschluss = anschlusspreis_aus_details(details_text)
        rabatte = []
        if kachel["aktion"]:
            monate, betrag = kachel["aktion"]
            rabatte.append(Rabatt(
                name=f"Aktionspreis: {monate} Monate je "
                     f"{betrag:.2f} €".replace(".", ","),
                von_monat=1, bis_monat=monate, beleg_url=seiten_url))
        referenzen.append(SimOnlyReferenz(
            anbieter=ANBIETER,
            tarif_name=name,
            tarif_id=tarif_id(ANBIETER, name),
            tarif_id_guete=HOCH,
            tarif_sim_only_monatlich=preis,
            anschlusspreis=anschluss,
            rabatte=rabatte,
            quelle_url=seiten_url,
            abgerufen_am=abgerufen_am,
            quelle_art=PREISTYP_LIVE_SHOP,
            bindung_monate=None,
            volumen_gb=kachel["volumen_gb"],
        ))
    return referenzen


def sammle(hole: Callable, abgerufen_am: str,
           robots: Optional[RobotsWaechter] = None,
           abstand_sekunden: Optional[float] = None
           ) -> tuple[list[SimOnlyReferenz], dict]:
    """Die ehrliche Messung: Seite je Tarif-Slug einmal, Details je Slug.

    `hole(url, kopfzeilen=None, user_agent=None) -> (status, text)` ist
    dieselbe Bauform wie im Geraetezweig (`geraete_pipeline._hole_fabrik`)
    - inklusive des Per-Aufruf-Absenders, damit diese Messung immer mit
    der ehrlichen Kennung laeuft, egal was in `settings.yaml` steht.

    Ein Misserfolg ist eine dokumentierte Messgrenze: Zurueck kommen die
    Referenzen, die standen (im Zweifel keine), und ein Protokoll mit
    dem Grund - die Funktion wirft nicht, ein Aufrufer darf an ihr keine
    Bestaende verlieren.
    """
    if abstand_sekunden is None:
        # Erst zur LAUFZEIT aufloesen: ein Test, der den Abstand auf 0
        # stellt, tut das am Modul-Attribut - ein Default, der die Zahl
        # zur Definitionszeit einfriert, wuerde das still ignorieren.
        abstand_sekunden = _ABSTAND_SEKUNDEN
    protokoll = {"seite": "", "details": 0, "details_gescheitert": 0,
                 "ohne_details": 0}
    if robots is None:
        robots = RobotsWaechter(lambda url: hole(url, user_agent=USER_AGENT))
    erlaubt, grund = robots.darf(SEITEN_URL)
    if not erlaubt:
        log.warning("1&1 SIM-only: %s nicht abrufbar (%s) - Messgrenze",
                    SEITEN_URL, grund)
        return [], protokoll
    try:
        status, html = hole(SEITEN_URL, user_agent=USER_AGENT)
    except Exception as exc:                        # noqa: BLE001
        log.warning("1&1 SIM-only: Seitenabruf gescheitert (%s) - "
                    "Messgrenze", exc)
        return [], protokoll
    if not (200 <= int(status) < 300):
        log.warning("1&1 SIM-only: Seite mit HTTP %s - Messgrenze", status)
        return [], protokoll
    protokoll["seite"] = f"HTTP {status}, {len(html or '')} Zeichen"

    rohkacheln = kacheln(html)
    details: dict[str, str] = {}
    letzter = 0.0
    for kachel in rohkacheln:
        adresse = kachel["details_url"]
        if not adresse:
            protokoll["ohne_details"] += 1
            continue
        adresse = urljoin(SEITEN_URL, html_modul.unescape(adresse))
        erlaubt, grund = robots.darf(adresse)
        if not erlaubt:
            log.warning("1&1 SIM-only: Tarifdetails %s uebergangen (%s) - "
                        "Anschlusspreis bleibt offen", adresse, grund)
            continue
        warte = robots.abstand(adresse, abstand_sekunden) \
            - (time.monotonic() - letzter)
        if letzter and warte > 0:
            time.sleep(warte)
        letzter = time.monotonic()
        try:
            dstatus, dtext = hole(adresse, user_agent=USER_AGENT)
        except Exception as exc:                    # noqa: BLE001
            protokoll["details_gescheitert"] += 1
            log.info("1&1 SIM-only: Tarifdetails zu %s gescheitert (%s) - "
                     "Anschlusspreis bleibt offen", kachel["slug"], exc)
            continue
        if 200 <= int(dstatus) < 300:
            details[kachel["slug"]] = dtext
            protokoll["details"] += 1
        else:
            protokoll["details_gescheitert"] += 1
            log.info("1&1 SIM-only: Tarifdetails zu %s mit HTTP %s - "
                     "Anschlusspreis bleibt offen", kachel["slug"], dstatus)

    referenzen = referenzen_aus_html(html, details=details,
                                     abgerufen_am=abgerufen_am)
    protokoll["tarife"] = len(referenzen)
    return referenzen, protokoll
