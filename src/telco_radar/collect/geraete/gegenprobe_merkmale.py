"""Merkmale eines Bündels für das Konfigurationsbild (``gegenprobe_bild``): wo die
Seite sie nennt (``nadeln``), welchen Wert die gewählte Option tragen muss
(``angaben``) und welche Blöcke je Anbieter die Wahl zusammenfassen (``BLOECKE``)."""

from __future__ import annotations

import re
import unicodedata

from .gegenprobe_browser import speicher_aus_sku

GERAET, SPEICHER, TARIF, RATEN, PREIS = "Gerät", "Speicher", "Tarif", "Raten", "Preis"
MERKMALE = (GERAET, SPEICHER, TARIF, RATEN, PREIS)
"""Was ein Konfigurationsbild eines Ratenbündels zeigen soll."""


def modell_text(sku_id: str) -> str | None:
    """„iphone 17 pro“ aus ``apple-iphone-17-pro-256gb-…`` (ohne Marke und Speicher)."""
    vorne = re.split(r"-\d+(?:gb|tb)(?:-|$)", sku_id or "")[0]
    teile = [t for t in vorne.split("-") if t]
    if len(teile) > 1:
        teile = teile[1:]
    return " ".join(teile) or None


def tarif_kern(name: str) -> str | None:
    """Tarifname ohne Zusätze („O2 Mobile L mit 150 GB+ (24 Mon.)“: „O2 Mobile L“)."""
    kern = re.split(r"\s+mit\s+|\s*\(|\s*\+", name or "", maxsplit=1)[0].strip()
    return kern or None


def nadeln(b: dict, nur: tuple[str, ...] = MERKMALE) -> dict[str, list[str]]:
    """Je Merkmal die Texte, an denen die Seite es nennt (aus dem Bestandssatz)."""
    out: dict[str, list[str]] = {}
    modell = modell_text(str(b.get("sku_id") or ""))
    if modell:
        out[GERAET] = [modell]
    speicher = speicher_aus_sku(str(b.get("sku_id") or ""))
    if speicher:
        zahl, einheit = speicher.split()
        out[SPEICHER] = [speicher] + (
            [f"{int(zahl) * 1024} GB"] if einheit == "TB" else []
        )
    tarif = tarif_kern(str(b.get("tarif_name") or ""))
    if tarif:
        out[TARIF] = [tarif]
    n = b.get("laufzeit_monate")
    if n and (b.get("geraet_monatsrate") or b.get("buendel_monatlich") is not None):
        out[RATEN] = [f"x {n}", f"x{n}", f"{n} Raten", f"{n} mtl. Zahlungen"]
        out[RATEN] += [f"{n} Monate"]
    return {k: v for k, v in out.items() if k in nur}


def _worte(text: str) -> list[str]:
    """Kleingeschriebene Wörter wie im Browser (``normw``: NFKC, nur a-z, 0-9, ä…)."""
    return re.findall(r"[a-z0-9äöüß]+", unicodedata.normalize("NFKC", text).lower())


def angaben(b: dict, nur: tuple[str, ...] = MERKMALE) -> dict[str, dict]:
    """Je Merkmal Nadeln (wo die Seite es nennt), den Wert, den die gewählte Option
    tragen muss (``256gb``, ``24``, Tarifstufe ``l``), und beim Tarif die Familie
    (``magentamobil``): „MagentaMobil S“ ist nicht „MagentaMobil Start“."""
    out: dict[str, dict] = {}
    for name, liste in nadeln(b, nur).items():
        out[name] = {"nadeln": liste, "wert": "", "familie": ""}
    sku = str(b.get("sku_id") or "")
    treffer = re.search(r"-(\d+)(gb|tb)(?:-|$)", sku)
    if SPEICHER in out and treffer:
        gb = int(treffer.group(1)) * (1024 if treffer.group(2) == "tb" else 1)
        out[SPEICHER]["wert"] = f"{gb}gb"
    if RATEN in out:
        out[RATEN]["wert"] = str(b.get("laufzeit_monate"))
    worte = _worte(tarif_kern(str(b.get("tarif_name") or "")) or "")
    if TARIF in out and len(worte) > 1:
        out[TARIF]["familie"] = " ".join(worte[:-1])
        out[TARIF]["wert"] = worte[-1]
    return out


BLOECKE: dict[str, tuple[tuple[str, ...], ...]] = {
    "o2": (
        ("Dein Angebot", "einmalig gesamt"),
        ("{geraet}", "mit Vertrag"),
        ("Dein Tarif", "Zu den Tarifdetails"),
    ),
    "telekom": (("Tarif entfernen", "einmalig"),),
    "vodafone": (
        ("Zur Tarifauswahl", "Pro Monat"),
        ("Weiter mit diesem Angebot", "Pro Monat"),
    ),
    "congstar": (("Monatliche Kosten", "Einmalige Kosten"),),
    "1-1": (("Monatliche Gesamtkosten", "Ratenzahlung Hardware"),),
    **{
        f"saturn-mediamarkt-{netz}-netz": (
            ("Ausgewähltes Gerät", "Produktdatenblatt"),
            ("Mein Tarif", "Tarif ändern", "Anschlussgebühr"),
        )
        for netz in ("telekom", "vodafone", "o2")
    },
}
"""Je Anbieter die Blöcke, die die Wahl zusammenfassen (Anker wie die Preisbereiche).
Nur sie zählen, wenn die Seite keine gewählte Option erkennen lässt, und nur, wenn sie
genau EINEN Wert des Merkmals nennen; Datenblätter und Werbetexte nie. ``{geraet}``
steht für das Modell des Bündels (o2: „Apple iPhone 15 Pro Max mit Vertrag O₂ Mobile
L“); Telekom: der Kasten „Unsere Empfehlung … Tarif entfernen“, nicht der Preisbereich
mit seinem Werbetext „ab MagentaMobil S“."""


def bloecke(schluessel: str, b: dict) -> list[list[str]]:
    """Die Anker der Zusammenfassungsblöcke dieses Anbieters für dieses Bündel."""
    modell = modell_text(str(b.get("sku_id") or "")) or ""
    return [
        [a.replace("{geraet}", modell) for a in anker]
        for anker in BLOECKE.get(schluessel, ())
        if modell or not any("{geraet}" in a for a in anker)
    ]
