"""Tarife aus einer congstar-Tarifseite (`/handytarife/allnet-flat-tarife/<tarif>/`).

Warum diese Lesart
------------------
congstar verlinkt seine Produktinformationsblätter weiter, ohne sie neu auszustellen:
Blatt 545 nennt für die Allnet Flat L am 26.10.2026 „29,00 € / Monat“ (Versionsstand 3
vom 30.07.2026), die Tarifseite und jede Bündelzeile 30,00 € (Preisprüfung 26.10.2026).
Die Tarifseite ist serverseitig gerendert (HTTP 200 mit dem Absender TelcoRadar/1.0,
robots.txt sperrt `/handytarife/` nicht) und trägt je Laufzeit einen Auswahlknopf
(`input[type=radio]`, `value` = Nummer des Produktinformationsblatts, `aria-label`
„Mindestlaufzeit von 24 Monaten“ bzw. „… 0 Monaten“), darunter `#<value>-content` mit
„Monatliche Kosten 30,00 €“.

Der Name folgt dem Blatt, damit Live- und Blattzeile dieselbe Titelzeile tragen
(`report/tarife_view`): Überschrift, „ Flex“ für die Variante ohne Laufzeit, dazu der
Zusatz aus `NAMENSZUSATZ`, den auch das Blatt im Namen führt („Allnet Flat S Flex mit
GB+“). „mit Upgrade-Versprechen“ steht nicht im Blattnamen und bleibt weg.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..tarif_model import HOCH, PREISTYP_LIVE_SHOP, Tarif, zahl
from .tarif_pdf import dokument_hash

METHODE = "congstar_seite"
NAMENSZUSATZ = ("mit GB+",)
_LAUFZEIT_RE = re.compile(r"Mindestlaufzeit von (\d+) Monaten")
_PREIS_RE = re.compile(r"Monatliche Kosten\s+([\d.,]+)\s*€")
_VOLUMEN_RE = re.compile(r"mit (\d+) GB")


def _text(knoten) -> str:
    return " ".join(knoten.get_text(" ", strip=True).split()) if knoten else ""


def tarife_aus_html(
    html: str, *, anbieter: str, seiten_url: str, abgerufen_am: str
) -> list[tuple[Tarif, str]]:
    """Je Laufzeit der Seite ein Tarif; gleiche Signatur wie `tarif_kacheln`."""
    suppe = BeautifulSoup(html or "", "html.parser")
    kopf = _text(suppe.find("h1"))
    if not kopf:
        return []
    unter = _text(suppe.find("h2"))
    zusatz = f" {unter}" if unter in NAMENSZUSATZ else ""
    titel = _text(suppe.find("title"))
    volumen = _VOLUMEN_RE.search(titel)
    out: list[tuple[Tarif, str]] = []
    for knopf in suppe.find_all("input", attrs={"type": "radio"}):
        laufzeit = _LAUFZEIT_RE.search(knopf.get("aria-label") or "")
        inhalt = suppe.find(id=f"{knopf.get('value')}-content")
        preis = _PREIS_RE.search(_text(inhalt))
        if not (laufzeit and preis):
            continue
        monate = int(laufzeit.group(1))
        name = f"{kopf}{'' if monate else ' Flex'}{zusatz}"
        rohtext = f"{name} | {laufzeit.group(0)} | {preis.group(0)} | {titel}"
        tarif = Tarif(
            anbieter=anbieter,
            abgerufen_am=abgerufen_am,
            rohtext=rohtext,
            preistyp=PREISTYP_LIVE_SHOP,
            dokument_url=seiten_url,
        )
        tarif.setze("name", name, name, HOCH)
        tarif.setze("grundgebuehr", zahl(preis.group(1)), preis.group(0), HOCH)
        if monate:
            tarif.setze("laufzeit_monate", monate, laufzeit.group(0), HOCH)
        if volumen:
            tarif.setze(
                "datenvolumen_gb", float(volumen.group(1)), volumen.group(0), HOCH
            )
        hash_ = dokument_hash(rohtext)
        tarif.dokument_hash = hash_
        out.append((tarif, hash_))
    return out
