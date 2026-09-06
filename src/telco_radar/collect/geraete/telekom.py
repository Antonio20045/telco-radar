"""Telekom: die Kategorieseite traegt ihre Preise serverseitig.

WAS SICH SEIT DEM 11.08.2026 GEAENDERT HAT - UND WAS NICHT
----------------------------------------------------------
Der alte `grund` in `geraete_quellen.yaml` bleibt in seinem Kern richtig:
auf der PRODUKTSEITE (`/shop/geraet/...`) traegt
`productDetailed.productDetailsData` je Speicherstufe nur einen
`deltaPrice`, also einen Aufschlag ohne Grundbetrag. Wer dort nach einem
Ladenpreis sucht, findet keinen.

Falsch war nur die Folgerung, dass Telekom deshalb gar nicht anzubinden
sei. Die KATEGORIEseite

    https://www.telekom.de/shop/geraete/smartphones/ohne-vertrag

liefert die absoluten Betraege serverseitig mit. Gemessen am 04.09.2026
(HTTP 200, 2,23 MB, Absender `TelcoRadar/1.0`, ohne Challenge) traegt
`window.__INITIAL_STATE__.productList.data` zehn Geraete, jedes so:

    "name": "Apple iPhone 17 Pro",
    "productSlug": "apple-iphone-17-pro", "variantSlug": "tiefblau-256-gb",
    "price": {"upfrontPrice": 99,
              "installments": [{"numberOfInstallments": 36,
                                "recurringPrice": 30.5,
                                "totalPrice": 1197}]}

DIE ZAHL IST KEIN BARPREIS, UND DAS IST DER GANZE PUNKT
-------------------------------------------------------
`totalPrice` ist der Gesamtbetrag eines Teilzahlungsgeschaefts ueber 36
Monate, kein Kassenpreis: 99 + 36 x 30,50 = 1197,00. Die Rechenprobe ging
am 04.09.2026 bei **10 von 10** Geraeten auf.

Genau das war die Bedingung, die der alte `grund` gestellt hat: "Ein
Adapter kann Telekom deshalb erst liefern, wenn er die Preisform
mitschreibt." Er schreibt sie mit - `anzahlung`, `monatsrate` und
`laufzeit_monate` wandern an die Listung, und `geraete_model.ratenhinweis`
setzt daneben "in 36 Raten". Dieselbe Bauart wie bei o2, dieselbe
Rechenprobe (`probe_geht_auf`), aus demselben Grund: o2s 721,00 EUR standen
bis zum 03.09.2026 in derselben Spalte wie freenets Barpreis von 949,00 EUR.

Geht die Probe NICHT auf, wird die Preisform verworfen und der Satz mit ihr.
Ein Gesamtbetrag, der seinen eigenen Bestandteilen widerspricht, ist keine
Messung - er ist ein geaendertes Nutzlastformat, und das soll auffallen und
nicht als Preis in den Bestand.

`zins_effektiv` bleibt `None`. Die Kategorieseite weist keinen Zinssatz
aus, und `None` heisst "unbekannt", nicht "null Prozent" - o2 bekommt seine
0.0 nur, weil die Produktseite sie woertlich als gesetzlichen
Finanzierungshinweis nennt.

DIE ADRESSE KOMMT AUS DEM HTML, NICHT AUS DEM SLUG
--------------------------------------------------
Aus `brandSlug`, `productSlug` und `variantSlug` liesse sich eine
Produktadresse zusammensetzen. Das waere eine geratene Adresse, und die
Hausregel dieses Projekts kennt dafuer nur eine Antwort. Stattdessen
werden die zehn `<a href="/shop/geraet/...">` der Seite geerntet und dem
Geraet zugeordnet, dessen drei Slugs in der Adresse stehen. Findet sich
keine, traegt der Satz die Kategorieseite als Quelle - sie ist die Seite,
auf der die Zahl wirklich stand.

Abgerufen wird ohnehin NUR die Kategorieseite (`direkt=True`): sie ist die
Nutzlast, keine Produktseite wird nachgeladen. Die geernteten Adressen sind
Beleglinks fuer den Leser, keine weiteren Abrufe.

DIE UMLEITUNGSKETTE
-------------------
`/mobilfunk/geraete/smartphone` und `/mobilfunk/tarife` laufen ueber eine
OAuth-Kette mit `prompt=none` auf die Shop-Adresse. Der Sammler folgt
Umleitungen ohnehin; die Kategorieadresse steht deshalb direkt in der
Konfiguration - eine Kette weniger ist eine Fehlerquelle weniger.

DIE GRENZE, DIE BLEIBT
----------------------
Aus GitHub Actions antwortet telekom.de httpx mit HTTP 202 und rund 2 KB
Challenge-HTML (CLAUDE.md § 6). Dieser Adapter aendert daran nichts und
soll es nicht: ein Fingerprint-Trick waere eine Umgehung, keine Loesung.
Faellt der Abruf so aus, liefert die Nutzlast keine Geraete, und
`sammle_anbieter` fuehrt die Seite als ungelesen - die Bestandsdaten altern
dann NICHT. Genau dafuer ist die Unterscheidung gebaut.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from . import GeraeteAbrufFehler
from ...geraete_model import probe_geht_auf

log = logging.getLogger(__name__)

_STATE_RE = re.compile(r"window\.__INITIAL_STATE__\s*=\s*")

# "tiefblau-256-gb" -> Farbe "tiefblau", Speicher 256.
# Die Einheit steht am Ende und wird gebraucht: "silber-1-tb" ist 1 TB und
# nicht 1 GB, und eine Zahl ohne ihre Einheit zu lesen waere derselbe
# Fehler wie ein Preis ohne seine Preisform.
_VARIANTE_RE = re.compile(r"^(?P<farbe>.+)-(?P<zahl>\d+)-(?P<einheit>gb|tb)$",
                          re.I)


def zustand(html: str) -> dict:
    """`window.__INITIAL_STATE__` als Objekt.

    Der Zustand ist in eine Zuweisung eingebettet und endet nicht am
    Zeilenende - er wird deshalb mit dem JSON-Dekoder gelesen, der das
    Ende selbst findet. Ein Regex bis zum naechsten `;` schnitte beim
    ersten Semikolon in einem Marketingtext ab.
    """
    treffer = _STATE_RE.search(html or "")
    if not treffer:
        raise GeraeteAbrufFehler(
            "Telekom-Kategorieseite ohne window.__INITIAL_STATE__ "
            f"({len(html or '')} Bytes) - Challenge oder neues Format")
    try:
        daten, _ = json.JSONDecoder().raw_decode(html, treffer.end())
    except (json.JSONDecodeError, ValueError) as exc:
        raise GeraeteAbrufFehler(
            f"Telekom-Zustandsobjekt unlesbar: {exc}") from exc
    if not isinstance(daten, dict):
        raise GeraeteAbrufFehler("Telekom-Zustandsobjekt ist kein Objekt")
    return daten


def _produktlinks(html: str, basis_url: str) -> list[str]:
    """Die Produktadressen, die die Seite als echte `<a href>` fuehrt."""
    suppe = BeautifulSoup(html or "", "html.parser")
    gefunden = []
    for anker in suppe.find_all("a", href=True):
        ziel = anker["href"]
        if "/shop/geraet/" in ziel:
            gefunden.append(urljoin(basis_url or "https://www.telekom.de", ziel))
    return gefunden


def _passende_adresse(eintrag: dict, links: list[str]) -> str:
    """Die verlinkte Adresse DIESES Geraets - oder nichts.

    Verglichen werden die drei Slugs, die der Eintrag selbst nennt. Damit
    ist die Zuordnung eine Pruefung und keine Konstruktion: passt keine
    der geernteten Adressen, bleibt das Feld leer und der Satz erbt die
    Kategorieseite.
    """
    teile = [str(eintrag.get(feld) or "").strip()
             for feld in ("brandSlug", "productSlug", "variantSlug")]
    if not all(teile):
        return ""
    for link in links:
        if all(f"/{teil}" in link for teil in teile):
            return link
    return ""


def _variante(slug: str) -> tuple[str, Optional[int]]:
    treffer = _VARIANTE_RE.match((slug or "").strip())
    if not treffer:
        return (slug or "").replace("-", " ").strip(), None
    farbe = treffer.group("farbe").replace("-", " ").strip()
    gb = int(treffer.group("zahl"))
    if treffer.group("einheit").lower() == "tb":
        gb *= 1024
    return farbe, gb


def _preisform(preis: dict) -> Optional[dict]:
    """Anzahlung, Rate, Laufzeit und Gesamtbetrag - nur wenn sie aufgehen."""
    raten = preis.get("installments") or []
    if not isinstance(raten, list) or not raten:
        return None
    erste = raten[0]
    if not isinstance(erste, dict):
        return None
    try:
        anzahlung = float(preis.get("upfrontPrice"))
        monatsrate = float(erste.get("recurringPrice"))
        laufzeit = int(erste.get("numberOfInstallments"))
        gesamt = float(erste.get("totalPrice"))
    except (TypeError, ValueError):
        return None
    if not probe_geht_auf(anzahlung, monatsrate, laufzeit, gesamt):
        return None
    return {"anzahlung": anzahlung, "monatsrate": monatsrate,
            "laufzeit_monate": laufzeit, "gesamt": gesamt}


def lies(text: str, url: str = "") -> list[dict]:
    """Die Kategorieseite in Rohsaetze zerlegen. Sie IST die Nutzlast."""
    daten = zustand(text)
    eintraege = ((daten.get("productList") or {}).get("data") or [])
    if not isinstance(eintraege, list):
        raise GeraeteAbrufFehler("Telekom-Nutzlast: productList.data ist "
                                 "keine Liste")
    links = _produktlinks(text, url)

    out: list[dict] = []
    for eintrag in eintraege:
        if not isinstance(eintrag, dict):
            continue
        name = str(eintrag.get("name") or eintrag.get("productName")
                   or "").strip()
        if not name:
            continue
        form = _preisform(eintrag.get("price") or {})
        if form is None:
            # Kein Etikett heisst hier: kein Satz. Anders als bei o2, wo
            # eine unetikettierte Zahl immer noch ein `totalPrice` ist,
            # gibt es bei der Telekom NUR den Ratengesamtbetrag - ohne
            # seine Bestandteile waere er ein Barpreis, der er nicht ist.
            log.info("Telekom: %r ohne nachrechenbare Ratenform - verworfen",
                     name)
            continue
        farbe, speicher = _variante(str(eintrag.get("variantSlug") or ""))
        out.append({
            "titel": " ".join(x for x in (name,
                                          f"{speicher} GB" if speicher else "",
                                          farbe) if x),
            "preis": form["gesamt"],
            "anzahlung": form["anzahlung"],
            "monatsrate": form["monatsrate"],
            "laufzeit_monate": form["laufzeit_monate"],
            # Die Seite nennt keinen Zinssatz. `None` heisst unbekannt.
            "zins_effektiv": None,
            "waehrung": "EUR",
            "verfuegbarkeit": ("lieferbar"
                               if str(eintrag.get("availabilityStatus")
                                      or "").upper() == "IN_STOCK"
                               else "unbekannt"),
            "sku": str(eintrag.get("id") or "").strip(),
            "ean": "",
            "farbe": farbe,
            "speicher_gb": speicher,
            "url": _passende_adresse(eintrag, links),
            "quelle": "telekom_kategorie",
        })
    return out
