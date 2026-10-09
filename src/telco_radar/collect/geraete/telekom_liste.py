"""Telekom-Übersicht aus der Datenantwort ``POST …/productOfferings/listing``.

Der neue Shop rendert die Übersicht clientseitig (Klick-Tageslauf 09.10.2026); die
Preise stehen in der Datenantwort (Zweig klick-erkundung, Commit b335c6ec):
``plan`` (Tarif), ``data[]`` je Gerät mit ``price.upfrontPrice`` und
``price.installments[]``. ``lies_listing`` macht daraus Sätze im Format, das
``klickrohsatz.uebersicht_rohsatz`` liest, jedes Gerät (Produkt und Variante) einmal.

Preise mit „Telekom Rückgabedeal“ (``buyBackPrice``/``buyBackDiscount`` gesetzt: 35
Raten plus Restzahlung) sind nicht vergleichbar und werden die Lücke
``LUECKE_RUECKGABEDEAL``, nie ein Preis. Die Ratenzahl ist ``numberOfInstallments``
oder ``recurringChargeOccurrence``, je nachdem, welche ``upfrontPrice + n ×
recurringPrice == totalPrice`` auf den Cent erfüllt (``probe_geht_auf``); erfüllen
beide oder keine, ist der Plan die Lücke ``LUECKE_RATENZAHL``. Der Produktlink gilt
nur, wenn ``/shop/geraet/<brandSlug>/<productSlug>/<variantSlug>`` so als ``href``
auf der Seite steht; sonst ist die Quelle die Übersicht. Dieses Modul ruft kein Netz.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from html import unescape
from urllib.parse import urljoin, urlsplit

from ...geraete_model import probe_geht_auf

LUECKE_RUECKGABEDEAL = "rueckgabedeal"
LUECKE_RATENZAHL = "ratenzahl_ohne_rechenprobe"
LUECKE_SPEICHER = "speicher_unbekannt"
LUECKE_UNLESBAR = "eintrag_unlesbar"
RUECKGABEFELDER = ("buyBackPrice", "buyBackDiscount")
RATENFELDER = ("numberOfInstallments", "recurringChargeOccurrence")
TB_IN_GB = 1024

_VARIANTE = re.compile(r"-(\d{2,4})-(gb|tb)$", re.I)
_HREF = re.compile(r"""<a\s[^>]*?href=["']([^"']*/shop/geraet/[^"']*)["']""", re.I)


@dataclass
class Listenlesung:
    """Sätze, Zahl der Geräte, je Lücke ihre Zahl und ``resultCount`` der Antworten."""

    saetze: list[dict] = field(default_factory=list)
    geraete: int = 0
    mit_rueckgabedeal: int = 0
    luecken: Counter[str] = field(default_factory=Counter)
    result_count: int | None = None

    def zahlen(self) -> dict:
        """Zahlen für die Diagnose der Seite (``uebersichten[].seiten[].liste``)."""
        return {
            "result_count": self.result_count,
            "geraete": self.geraete,
            "mit_rueckgabedeal": self.mit_rueckgabedeal,
            "ohne_rueckgabedeal": self.geraete - self.mit_rueckgabedeal,
            "luecken": dict(self.luecken),
        }


def lies_listing(nutzlasten: list[object], text: str, adresse: str) -> Listenlesung:
    """Die Sätze aller Antworten ``nutzlasten`` der Übersicht ``adresse``."""
    lesung = Listenlesung()
    links = _links(text, adresse)
    gesehen: set[tuple[str, str]] = set()
    for nutzlast in nutzlasten:
        if not isinstance(nutzlast, dict):
            lesung.luecken[LUECKE_UNLESBAR] += 1
            continue
        anzahl = nutzlast.get("resultCount")
        if isinstance(anzahl, int):
            lesung.result_count = anzahl
        tarif = _tarif(nutzlast.get("plan"))
        for eintrag in nutzlast.get("data") or []:
            if not isinstance(eintrag, dict):
                lesung.luecken[LUECKE_UNLESBAR] += 1
                continue
            schluessel = (
                str(eintrag.get("productSlug")),
                str(eintrag.get("variantSlug")),
            )
            if schluessel in gesehen:
                continue
            gesehen.add(schluessel)
            lesung.geraete += 1
            _lies_geraet(eintrag, tarif, links, adresse, lesung)
    return lesung


def _lies_geraet(
    eintrag: dict,
    tarif: dict,
    links: dict[str, str],
    adresse: str,
    lesung: Listenlesung,
) -> None:
    roh = eintrag.get("price")
    preis: dict = roh if isinstance(roh, dict) else {}
    plaene = [p for p in preis.get("installments") or [] if isinstance(p, dict)]
    if any(p.get(f) is not None for p in plaene for f in RUECKGABEFELDER):
        lesung.mit_rueckgabedeal += 1
        lesung.luecken[LUECKE_RUECKGABEDEAL] += 1
        return
    gb = _speicher(str(eintrag.get("variantSlug") or ""))
    if gb is None:
        lesung.luecken[LUECKE_SPEICHER] += 1
        return
    pfad = "/shop/geraet/" + "/".join(
        str(eintrag.get(f) or "") for f in ("brandSlug", "productSlug", "variantSlug")
    )
    name = " ".join(str(eintrag.get("name") or "").split())
    anzahlung = _betrag(preis.get("upfrontPrice"))
    for plan in plaene or [{}]:
        rate = _betrag(plan.get("recurringPrice"))
        gesamt = _betrag(plan.get("totalPrice"))
        monate = {
            n
            for n in (plan.get(f) for f in RATENFELDER)
            if isinstance(n, int) and probe_geht_auf(anzahlung, rate, n, gesamt)
        }
        if len(monate) != 1:
            lesung.luecken[LUECKE_RATENZAHL] += 1
            continue
        lesung.saetze.append(
            {
                "titel": f"{name} {gb} GB",
                "speicher_gb": gb,
                **tarif,
                "geraet_zuzahlung": anzahlung,
                "geraet_monatsrate": rate,
                "laufzeit_monate": monate.pop(),
                "url": links.get(pfad, adresse),
            }
        )


def _tarif(plan: object) -> dict:
    """Name, ID, Monatspreis und Anschlusspreis des Tarifs; fehlt einer, ``None``."""
    plan = plan if isinstance(plan, dict) else {}
    preise = {
        p.get("priceType"): _betrag(p.get("actualValue"))
        for p in plan.get("prices") or []
        if isinstance(p, dict)
    }
    return {
        "tarif_name": plan.get("name"),
        "tarif_slug": plan.get("id"),
        "tarif_monatlich": preise.get("recurringFee"),
        "anschlusspreis": preise.get("activationFee"),
    }


def _speicher(slug: str) -> int | None:
    treffer = _VARIANTE.search(slug)
    if treffer is None:
        return None
    wert = int(treffer[1])
    return wert * TB_IN_GB if treffer[2].lower() == "tb" else wert


def _betrag(roh: object) -> float | None:
    if isinstance(roh, bool) or not isinstance(roh, int | float):
        return None
    return float(roh)


def _links(text: str, adresse: str) -> dict[str, str]:
    """Je Pfad ``/shop/geraet/…`` das erste ``href`` der Seite, absolut."""
    links: dict[str, str] = {}
    for href in _HREF.findall(text):
        ziel = urljoin(adresse, unescape(href))
        links.setdefault(urlsplit(ziel).path, ziel)
    return links
