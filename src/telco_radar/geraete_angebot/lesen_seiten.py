"""Leser der Modellseiten für o2, 1&1, congstar, Telekom und die Tarifwelt.

Fortsetzung von ``lesen`` (gleiche Regeln: nur was die Seite sichtbar als Auswahl
zeigt, nicht wählbare Optionen getrennt, ``LeserFehler`` statt leerer Liste).
Gelesen am 21.11.2026 an je einer echten Seite (``tests/fixtures/geraete_angebot/``).
"""

from __future__ import annotations

import re

from bs4 import Tag

from ..geraete_tarifschluessel import preis_code
from . import Option
from .lesen import (
    LeserFehler,
    _gruppe,
    _ist_speicher,
    _option,
    _soup,
    _text,
    laufzeit_optionen,
    monate,
    radiogruppen,
)

EINSUNDEINS_TARIFE = {
    "anf-s": "1&1 All-Net-Flat S",
    "anf-m": "1&1 All-Net-Flat M",
    "anf-l": "1&1 All-Net-Flat L",
    "anf-xxl-unlimited-s": "1&1 Unlimited on demand S",
    "anf-xxl-unlimited-m": "1&1 Unlimited on demand M",
    "anf-xxl-unlimited-l": "1&1 Unlimited on demand L",
    "anf-xxl-unlimited-xl": "1&1 Unlimited XL",
}
"""Tarifcodes der 1&1-Tarifauswahl (``tariff-<code>-mvl-…``) und ihre Namen, wie die
Seite sie in der Tarifbeschreibung führt (21.11.2026). Ein unbekannter Code bleibt
als Code stehen und wird damit eine sichtbare Lücke, kein stiller Ausfall."""


def _aria(tag: Tag | None) -> str:
    return str(tag.get("aria-label") or "") if tag is not None else ""


def o2_geraet(html: str) -> dict:
    """Produktseite: Speicher, Tarifkacheln (Name im ``aria-label``), Zahlungsplan."""
    gruppen = radiogruppen(html)
    speicher = _gruppe(gruppen, _ist_speicher)
    tarife: list[Option] = []
    for paare in gruppen.values():
        namen = [str(e_l[1].get("aria-label") or "") if e_l[1] else "" for e_l in paare]
        if paare and all(n.upper().startswith("O2") for n in namen):
            tarife = [
                _option(e, lab, " ".join(n.split()))
                for (e, lab), n in zip(paare, namen, strict=True)
            ]
            break
    plaene = next(
        (
            p
            for p in gruppen.values()
            if p
            and all(lab is not None and lab.get("aria-label") for _, lab in p)
            and any(monate(_aria(lab)) for _, lab in p)
        ),
        [],
    )
    if not speicher or not tarife or not plaene:
        raise LeserFehler("o2: Speicher, Tarife oder Zahlungsplan fehlen")
    roh = [_option(e, lab, _aria(lab)) for e, lab in plaene]
    laufzeiten, ausserhalb = laufzeit_optionen(roh)
    farben = gruppen.get("color") or []
    return {
        "speicher": speicher,
        "tarife": tarife,
        "laufzeiten": laufzeiten,
        "ausserhalb": ausserhalb,
        "farben": [_option(e, lab) for e, lab in farben],
    }


O2_TARIFUEBERSICHT = "https://www.o2online.de/tarife/"


def o2_tarifuebersicht(html: str) -> list[Option]:
    """Tarifübersicht: je Tarifkachel der Link „Handy hinzufügen“ (``/e-shop?tarif=
    <slug>``), ein sichtbarer Kaufweg mit Gerät neben der Produktseite (Befund
    21.11.2026, ``berichte/o2-nicht-plus.md``). Wert ist der Slug, Text ein lesbarer
    Name daraus; die Kachel nennt keinen vollständigen Tarifnamen."""
    gesehen: dict[str, Option] = {}
    for a in _soup(html).find_all("a", href=re.compile(r"[?&]tarif=")):
        if _text(a) != "Handy hinzufügen":
            continue
        treffer = re.search(r"[?&]tarif=([a-z0-9-]+)", str(a.get("href") or ""))
        if treffer:
            slug = treffer.group(1)
            name = " ".join(
                w.upper() if w == "o2" else w.capitalize() for w in slug.split("-")
            )
            gesehen.setdefault(slug, Option(name, slug))
    if not gesehen:
        raise LeserFehler("o2: keine Tarifkachel mit „Handy hinzufügen“")
    return list(gesehen.values())


def einsundeins_geraet(html: str) -> dict:
    """Produktseite: Speicher-Kacheln, je Reiter „24/36 Monate“ die Wahl „Fix“ oder
    „Flex“ (Flex ist eine eigene Zahlweise außerhalb des Vergleichs)."""
    gruppen = radiogruppen(html)
    speicher = next(
        (
            [_option(e, lab) for e, lab in p]
            for n, p in gruppen.items()
            if n.endswith(".storage")
        ),
        [],
    )
    farben = next((p for n, p in gruppen.items() if n.endswith(".color")), [])
    roh = [
        _option(e, lab)
        for n, p in gruppen.items()
        if n.startswith("contract-duration")
        for e, lab in p
    ]
    if not speicher or not roh:
        raise LeserFehler("1&1: keine Speicher- oder Laufzeitauswahl")
    laufzeiten, ausserhalb = laufzeit_optionen(roh)
    return {
        "speicher": speicher,
        "laufzeiten": laufzeiten,
        "ausserhalb": ausserhalb,
        "farben": [_option(e, lab) for e, lab in farben],
    }


def einsundeins_tarife(html: str) -> list[Option]:
    """Tarifauswahl (``tariff-plan``): je Code ein Tarif, Name aus der Tabelle
    ``EINSUNDEINS_TARIFE``."""
    gesehen: dict[str, Option] = {}
    for paar in radiogruppen(html).get("tariff-plan", []):
        wert = str(paar[0].get("value") or "")
        treffer = re.match(r"tariff-(.+?)-mvl", wert)
        code = treffer.group(1) if treffer else wert
        name = EINSUNDEINS_TARIFE.get(code, code)
        gesehen.setdefault(code, Option(name, code, not paar[0].has_attr("disabled")))
    if not gesehen:
        raise LeserFehler("1&1: keine Tarifauswahl")
    return list(gesehen.values())


def _knopf_radios(html: str, pruefe) -> list[Option]:
    knoepfe = []
    for b in _soup(html).find_all(["button", "div"], attrs={"role": "radio"}):
        text = str(b.get("aria-label") or _text(b))
        if pruefe(text):
            aus = (
                b.has_attr("disabled")
                or b.has_attr("data-disabled")
                or "nicht vorhanden" in text
                or "nicht verfügbar" in _text(b.parent)
            )
            knoepfe.append(Option(text.replace(" nicht vorhanden", ""), text, not aus))
    return knoepfe


def congstar_geraet(html: str) -> dict:
    """Produktseite: Speicher-Knöpfe („512 GB nicht vorhanden“), Zahlungen
    („36 mtl. Zahlungen“, „Einmalzahlung“), Tarifkacheln (Volumen) und die Wahl
    „24 Monate Laufzeit“ oder „Ohne Laufzeit“ (eigener Tarif „… Flex“)."""
    speicher = _knopf_radios(html, _ist_speicher)
    gruppen = radiogruppen(html)
    raten = _gruppe(gruppen, lambda t: bool(re.search(r"zahlung", t, re.I)))
    tarife = _gruppe(gruppen, lambda t: bool(re.search(r"\bGB\b.*mtl", t)))
    bindung = _gruppe(gruppen, lambda t: bool(re.search(r"Laufzeit", t)))
    if not speicher or not raten or not tarife:
        raise LeserFehler("congstar: Speicher, Zahlungen oder Tarife fehlen")
    laufzeiten, ausserhalb = laufzeit_optionen(raten)
    return {
        "speicher": speicher,
        "laufzeiten": laufzeiten,
        "ausserhalb": ausserhalb,
        "tarifkacheln": tarife,
        "bindung": bindung,
    }


def congstar_tarifname(html: str) -> str:
    """Name des gewählten Tarifs („Tarifdetails: Allnet Flat S Flex“)."""
    for b in _soup(html).find_all("button"):
        text = _text(b)
        if text.startswith("Tarifdetails:"):
            return text.split(":", 1)[1].strip()
    raise LeserFehler("congstar: kein Tarifname")


def telekom_geraet(html: str) -> dict:
    """Produktseite: Speicher-Chips (``aria-label`` „256 GB“) und Zahlweisen
    („… pro Monat für 36 Monate“, „für 0 Monate“ = Einmalpreis). Zeigt ein Tarif nur
    den Einmalpreis, sind die Laufzeiten leer (kein Fehler, kein Ratenangebot)."""
    speicher = _knopf_radios(html, lambda t: bool(re.fullmatch(r"\d+ (GB|TB)", t)))
    for o in speicher:
        o.waehlbar = True
    zahlweisen = _knopf_radios(html, lambda t: "pro Monat für" in t)
    laufzeiten, ausserhalb = [], []
    for o in zahlweisen:
        n = re.search(r"für (\d+) Monate", o.wert)
        if n and int(n.group(1)) > 0:
            laufzeiten.append(Option(o.text, n.group(1), o.waehlbar))
        else:
            ausserhalb.append("Einmalpreis")
    if not speicher or not zahlweisen:
        raise LeserFehler("Telekom: keine Speicher- oder Zahlweisenauswahl")
    return {"speicher": speicher, "laufzeiten": laufzeiten, "ausserhalb": ausserhalb}


def telekom_gewaehlt(html: str) -> str | None:
    """Die Tarif-ID, die der Dialog „Tarif ändern“ als gewählt zeigt."""
    for eingabe in _soup(html).find_all("input", attrs={"name": "service"}):
        if eingabe.has_attr("checked"):
            return str(eingabe.get("id") or "").removeprefix("service-")
    return None


def telekom_tarife(html: str) -> list[Option]:
    """Dialog „Tarif ändern“: je ``input[name=service]`` der Tarifname (MagentaMobil …)
    aus der Karte, Wert die Tarif-ID aus der Adresse (``service-MF_…``)."""
    tarife = []
    for eingabe in _soup(html).find_all("input", attrs={"name": "service"}):
        knoten: Tag | None = eingabe
        name = ""
        for _ in range(8):
            knoten = knoten.parent if knoten is not None else None
            if knoten is None:
                break
            treffer = re.search(
                r"Magenta\s?Mobil(?:\s+Young)?\s+(?:XS|S|M|L|XL|XXL)\b", _text(knoten)
            )
            if treffer:
                name = treffer.group(0)
                break
        wert = str(eingabe.get("id") or "").removeprefix("service-")
        tarife.append(Option(name or wert, wert, not eingabe.has_attr("disabled")))
    if not tarife:
        raise LeserFehler("Telekom: kein Tarif im Dialog")
    return tarife


def tarifwelt_geraet(html: str) -> dict:
    """Produktseite der Tarifwelt: Speicher-Knöpfe im Feld „Speicher“ (``disabled`` =
    in der vorgewählten Farbe nicht verfügbar) und Farben."""
    soup = _soup(html)
    felder = {}
    for satz in soup.find_all("fieldset"):
        legende = _text(satz.find("legend"))
        felder[legende.split(" ")[0]] = [
            Option(
                str(b.get("value") or _text(b)),
                str(b.get("value") or ""),
                not (b.has_attr("disabled") or b.has_attr("data-disabled")),
            )
            for b in satz.find_all(role="radio")
        ]
    if not felder.get("Speicher"):
        raise LeserFehler("Tarifwelt: keine Speicherauswahl")
    return {"speicher": felder["Speicher"], "farben": felder.get("Farbe", [])}


def tarifwelt_netzzahlen(html: str) -> dict[str, int]:
    """Filter „Netzbetreiber“ im Dialog „Tarif ändern“: die genannte Zahl je Netz."""
    zahlen = {}
    for label in _soup(html).find_all("label", attrs={"for": re.compile(r"carrier_")}):
        treffer = re.search(r"(\d+)\s*$", _text(label))
        if treffer:
            zahlen[str(label["for"]).rsplit("carrier_", 1)[1]] = int(treffer.group(1))
    if not zahlen:
        raise LeserFehler("Tarifwelt: kein Netzfilter im Dialog")
    return zahlen


_TW_GERAET = re.compile(r"Gerätepreis:?\s*([\d.]*\d(?:,\d+)?) Euro")
_TW_MONAT = re.compile(
    r"(?:monatlicher Preis:|Tarif monatlich)\s*([\d.]*\d(?:,\d+)?) Euro"
)


def _euro(treffer: re.Match | None) -> float | None:
    if treffer is None:
        return None
    return float(treffer.group(1).replace(".", "").replace(",", "."))


def tarifwelt_karte(aria: str) -> tuple[str, str]:
    """(Name, Preis-Code) einer Tarifkarte aus ihrem ``aria-label`` („Tarif: Mobile
    Unlimited L Promo , Datenvolumen: …, Gerätepreis: 1 Euro, monatlicher Preis:
    59,99 Euro …“); der Preis unterscheidet gleichnamige Tarife."""
    name = aria[6:].split(", Datenvolumen")[0].strip()
    code = preis_code(_euro(_TW_GERAET.search(aria)), _euro(_TW_MONAT.search(aria)))
    return name, code


def tarifwelt_tarifnamen(
    html: str,
) -> tuple[list[tuple[str, str]], tuple[str, str] | None]:
    """Karten unter dem gesetzten Filter und die Karte des ausgewählten Tarifs
    (eigener Abschnitt), je als (Name, Preis-Code)."""
    soup = _soup(html)
    dialog = (soup.find_all(role="dialog") or [soup])[-1]

    def karten(abschnitt) -> list[tuple[str, str]]:
        if abschnitt is None:
            return []
        return [
            tarifwelt_karte(str(b["aria-label"]))
            for b in abschnitt.find_all(
                "button", attrs={"aria-label": re.compile(r"^Tarif: ")}
            )
        ]

    weitere = karten(
        dialog.find("section", attrs={"aria-label": re.compile(r"^Weitere")})
    )
    gewaehlt = karten(
        dialog.find("section", attrs={"aria-label": re.compile(r"^Aktuell")})
    )
    return weitere, (gewaehlt[0] if gewaehlt else None)
