"""Leser der Angebotszählung: aus dem DOM eines Schnappschusses, was sichtbar ist.

Jeder Leser bekommt das HTML eines Zustands, den der Browser gesehen hat
(``page.content()`` nach Laden, „mehr anzeigen“ oder Klick), und gibt zurück, was ein
Kunde dort wählen kann. Eigener Code, am 21.11.2026 an je einer echten Seite je
Anbieter geschrieben (Fixtures ``tests/fixtures/geraete_angebot/``); kein Selektor
des Sammlers oder der Gegenprobe. Wo möglich, liest er Merkmale, die die Seite für
Screenreader setzt (``role=radio``, ``aria-label``, ``disabled``), nicht Klassennamen.

Ein Leser wirft ``LeserFehler``, wenn der Zustand nicht die erwartete Form hat: eine
leere Auswahl ist kein Ergebnis, sondern ein Fehler (Clean Code 5).
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from . import Kachel, Option


class LeserFehler(ValueError):
    """Der Schnappschuss hat nicht die Form, die der Leser kennt."""


NICHT_SMARTPHONE = re.compile(
    r"\b(watch|kidswatch|imoo|xplora|navee|scooter|tablet|ipad|airpods|buds|"
    r"router|tab)\b",
    re.I,
)
_SPEICHER = re.compile(r"(\d+(?:[.,]\d+)?)\s*(GB|TB)\b", re.I)
_MONATE = re.compile(r"(\d+)\s*(?:Raten|Monate|mtl\.?\s*Zahlungen|Monatsraten)", re.I)


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", "html.parser")


def _attr(tag: Tag, name: str) -> str:
    """Ein Attribut als Text (BeautifulSoup liefert bei ``class`` Listen)."""
    wert = tag.get(name)
    return " ".join(wert) if isinstance(wert, list) else str(wert or "")


def _text(tag: Tag | None) -> str:
    return " ".join(tag.get_text(" ", strip=True).split()) if tag else ""


def speicher_segment(text: str) -> str | None:
    """„256 GB“ -> „256gb“, „1 TB“ -> „1024gb“ (Speichersegment der SKU)."""
    treffer = _SPEICHER.search(text or "")
    if not treffer:
        return None
    zahl = float(treffer.group(1).replace(",", "."))
    if treffer.group(2).upper() == "TB":
        zahl *= 1024
    return f"{int(zahl)}gb"


def monate(text: str) -> int | None:
    """Ratenzahl aus „36 Raten“, „24 Monate“, „36 mtl. Zahlungen“, „mtl. x 24“."""
    treffer = _MONATE.search(text or "") or re.search(r"x\s*(\d+)\b", text or "")
    return int(treffer.group(1)) if treffer else None


_FUELL = frozenset(
    {"shop", "geraet", "geraete", "e-shop", "privat", "handys", "smartphones", "de"}
)
_SCHREIBUNG = {"iphone": "iPhone", "ipad": "iPad"}
_SPEICHERWORT = re.compile(r"^\d+(gb|tb)$")


def name_aus_adresse(url: str) -> str:
    """Lesbarer Gerätename aus einer Produktadresse, wenn keine Kachel einen nennt:
    „…/google-pixel-10a.html“ -> „Google Pixel 10a“, „…/samsung/galaxy-s26/“ ->
    „Samsung Galaxy S26“; Speicher, Farbe und „details“ dahinter fallen weg."""
    pfad = urlsplit(url).path.removesuffix(".html").strip("/").split("/")
    teile = [t for t in pfad if t and t not in _FUELL]
    wahl = next((i for i, t in enumerate(teile) if "-" in t), len(teile) - 1)
    if wahl < 0:
        return url
    woerter = teile[wahl].split("-")
    if wahl > 0 and woerter[0] != teile[wahl - 1]:
        woerter = [teile[wahl - 1], *woerter]
    name: list[str] = []
    for i, w in enumerate(woerter):
        danach = woerter[i + 1] if i + 1 < len(woerter) else ""
        if name and (
            _SPEICHERWORT.match(w) or (w.isdigit() and danach in {"gb", "tb"})
        ):
            break
        name.append(w)
    return " ".join(_SCHREIBUNG.get(w, w[:1].upper() + w[1:]) for w in name)


def ist_smartphone(titel: str) -> bool:
    """Grobe Sperre gegen Uhren, Kinderuhren, Roller und Zubehör in einer Übersicht."""
    return not NICHT_SMARTPHONE.search((titel or "").split(" mit ")[0])


def _kachel(basis: str, href: str, titel: str) -> Kachel:
    teile = urlsplit(urljoin(basis, href))
    url = f"{teile.scheme}://{teile.netloc}{teile.path}"
    return Kachel(url, " ".join(titel.split()), paket=" mit " in f" {titel} ")


def _eindeutig(kacheln: list[Kachel]) -> list[Kachel]:
    gesehen: dict[str, Kachel] = {}
    for k in kacheln:
        gesehen.setdefault(k.url, k)
    if not gesehen:
        raise LeserFehler("keine Kachel in der Übersicht")
    return list(gesehen.values())


def telekom_kacheln(html: str) -> list[Kachel]:
    """Produktkarten (``data-qa`` ``LST_ProductCard…``); Name ist der Text der Karte,
    der mit dem Hersteller aus der Adresse beginnt. Adresse ist die der vorgewählten
    Variante; eine Karte je Modell (``/shop/geraet/<hersteller>/<modell>``)."""
    kacheln: dict[str, Kachel] = {}
    for karte in _soup(html).select('[data-qa^="LST_ProductCard"]'):
        a = karte.find(
            "a", href=re.compile(r"^(https://www\.telekom\.de)?/shop/geraet/")
        )
        if a is None:
            continue
        pfad = urlsplit(_attr(a, "href")).path.split("/")
        hersteller = pfad[3] if len(pfad) > 4 else ""
        titel = next(
            (
                t.strip()
                for t in karte.stripped_strings
                if hersteller and t.lower().startswith(hersteller.lower())
            ),
            " ".join(pfad[4:5]).replace("-", " "),
        )
        kachel = _kachel("https://www.telekom.de", "/".join(pfad), titel)
        kacheln.setdefault("/".join(pfad[:5]), kachel)
    return _eindeutig(list(kacheln.values()))


def vodafone_kacheln(html: str) -> list[Kachel]:
    """Produktkarten der Liste „alle Smartphones“."""
    kacheln = []
    for karte in _soup(html).select(".ws10-product-card-list__item"):
        a = karte.find("a", href=re.compile(r"/privat/handys/[^/]+\.html"))
        if a is not None:
            titel = _text(karte.find(["h2", "h3"]))
            kacheln.append(_kachel("https://www.vodafone.de", _attr(a, "href"), titel))
    return _eindeutig(kacheln)


def o2_kacheln(html: str) -> list[Kachel]:
    """Kacheln des Shops; „… mit AirPods“ ist ein Paket."""
    kacheln = []
    for karte in _soup(html).select("div.hardware-item"):
        a = karte.find("a", href=re.compile(r"-details"))
        titel = _text(karte.select_one(".title"))
        if a is not None and titel:
            kacheln.append(_kachel("https://www.o2online.de", _attr(a, "href"), titel))
    return _eindeutig(kacheln)


def einsundeins_kacheln(html: str) -> list[Kachel]:
    """Kacheln ``form.hardware-box``; Name und Adresse aus der Überschrift."""
    kacheln = []
    for karte in _soup(html).select("form.hardware-box"):
        a = karte.select_one("a.hardware-box__heading, a[href]")
        if a is not None and a.get("href"):
            titel = _text(a).replace(" | ", " ")
            kacheln.append(_kachel("https://mobile.1und1.de", _attr(a, "href"), titel))
    return _eindeutig(kacheln)


def _ueberschrift_ueber(a: Tag, tiefe: int = 6) -> str:
    knoten: Tag | None = a
    for _ in range(tiefe):
        knoten = knoten.parent if knoten is not None else None
        if knoten is None:
            break
        kopf = knoten.find(["h2", "h3"])
        if kopf is not None:
            return _text(kopf)
    return ""


def congstar_kacheln(html: str) -> list[Kachel]:
    """Geräte-Links der Kategorie „Handy“ (``deviceVariantId``)."""
    kacheln = [
        _kachel("https://www.congstar.de", _attr(a, "href"), _ueberschrift_ueber(a))
        for a in _soup(html).find_all("a", href=re.compile(r"deviceVariantId="))
    ]
    return _eindeutig(kacheln)


def tarifwelt_kacheln(html: str) -> list[Kachel]:
    """Produktkarten der Tarifwelt (``/smartphones/<marke>/<modell>/?…``)."""
    muster = re.compile(r"^/smartphones/[^/?]+/[^/?]+/\?")
    kacheln = [
        _kachel(
            "https://tarife.mediamarkt.de", _attr(a, "href"), _ueberschrift_ueber(a)
        )
        for a in _soup(html).find_all("a", href=muster)
    ]
    return _eindeutig(kacheln)


def genannte_zahl(text: str, muster: str) -> int | None:
    """Die Trefferzahl, die die Seite selbst nennt (``muster`` mit einer Gruppe)."""
    treffer = re.search(muster, text or "")
    return int(treffer.group(1)) if treffer else None


def radiogruppen(html: str) -> dict[str, list[tuple[Tag, Tag | None]]]:
    """Alle ``input[type=radio]`` nach ``name`` gruppiert, je mit ihrem Label."""
    soup = _soup(html)
    gruppen: dict[str, list[tuple[Tag, Tag | None]]] = {}
    for eingabe in soup.find_all("input", attrs={"type": "radio"}):
        label = None
        if eingabe.get("id"):
            label = soup.find("label", attrs={"for": eingabe["id"]})
        label = label or eingabe.find_parent("label")
        gruppen.setdefault(str(eingabe.get("name") or ""), []).append((eingabe, label))
    return gruppen


def _option(eingabe: Tag, label: Tag | None, text: str | None = None) -> Option:
    aus = eingabe.has_attr("disabled") or "disabled" in " ".join(
        (label.get("class") or []) if label is not None else []
    )
    return Option(
        text if text is not None else _text(label),
        str(eingabe.get("value") or ""),
        not aus,
    )


def _gruppe(gruppen: dict, pruefe) -> list[Option]:
    for paare in gruppen.values():
        texte = [_text(lab) for _, lab in paare]
        if paare and all(pruefe(t) for t in texte):
            return [_option(e, lab) for e, lab in paare]
    return []


def laufzeit_optionen(optionen: list[Option]) -> tuple[list[Option], list[str]]:
    """Raten-Optionen mit Monatszahl; die übrigen (Einmalzahlung, „Sofort“, Flex) als
    sichtbare Zahlweise außerhalb des Vergleichs."""
    drin, ausserhalb = [], []
    for o in optionen:
        n = monate(o.text)
        if n is None or "flex" in o.text.lower() or "flex" in o.wert.lower():
            ausserhalb.append(o.text)
        else:
            drin.append(Option(o.text, str(n), o.waehlbar))
    return drin, ausserhalb


def _ist_speicher(t: str) -> bool:
    return speicher_segment(t) is not None and len(t) < 40


def vodafone_geraet(html: str) -> dict:
    """Produktseite: Speicher, Raten, Farben (Optionsgruppen der Seite)."""
    gruppen = radiogruppen(html)
    speicher = _gruppe(gruppen, _ist_speicher)
    raten = _gruppe(gruppen, lambda t: bool(re.search(r"Raten|Einmal", t)))
    farben = next((p for n, p in gruppen.items() if "color" in n.lower()), [])
    if not speicher or not raten:
        raise LeserFehler("Vodafone: keine Speicher- oder Ratenauswahl")
    laufzeiten, ausserhalb = laufzeit_optionen(raten)
    return {
        "speicher": speicher,
        "laufzeiten": laufzeiten,
        "ausserhalb": ausserhalb,
        "farben": [_option(e, lab) for e, lab in farben],
    }


def vodafone_tarifoptionen(html: str) -> list[Option]:
    """Tarifauswahl nach „Zur Tarifauswahl“: die Gruppe, deren Name „tariff“ trägt."""
    gruppen = radiogruppen(html)
    paare = next((p for n, p in gruppen.items() if "tariff" in n.lower()), [])
    if not paare:
        raise LeserFehler("Vodafone: keine Tarifauswahl")
    return [_option(e, lab) for e, lab in paare]


def vodafone_tarifname(html: str) -> str:
    """Name des gewählten Tarifs aus der Angebotsübersicht: „Mobil XS“ aus „Mobil XS
    mit 23 GB“ (der Zusatz beschreibt das Volumen, die Kachel nennt den Namen so)."""
    kopf = _soup(html).select_one(
        ".ws10-offer-summary-card h2, .ws10-offer-summary-card h3"
    )
    name = _text(kopf)
    if not name:
        raise LeserFehler("Vodafone: kein Tarifname in der Angebotsübersicht")
    treffer = _VF_NAME.search(name)
    return treffer.group(0) if treffer else name


_VF_NAME = re.compile(r"\bMobil (?:XS|S|M|L|XL)\b")
_VF_GROESSE = r"(?:XS|S|M|L|XL)"
_VF_AUSSCHLUSS = re.compile(
    r"In den Tarifen (?:GigaMobil |Mobil )?"
    rf"({_VF_GROESSE}(?:(?:, | und ){_VF_GROESSE})*)"
    r" kannst Du Dein Smartphone nicht in (\d+) Raten zahlen"
)


def vodafone_tarife_inline(html: str) -> list[Option]:
    """Tarifwahl direkt auf der Produktseite (manche Geräte, z. B. Pixel 10a): die
    Kachel nennt den Namen („23 GB statt 18 GB Mobil XS“); leer, wenn es sie nicht
    gibt (dann führt „Zur Tarifauswahl“ auf eine eigene Seite)."""
    for name, paare in radiogruppen(html).items():
        if "tariff" not in name.lower():
            continue
        optionen = []
        for e, lab in paare:
            treffer = _VF_NAME.search(_text(lab))
            if treffer:
                optionen.append(_option(e, lab, treffer.group(0)))
        if optionen:
            return optionen
    return []


def vodafone_ausschluesse(html: str) -> list[tuple[str, int]]:
    """Was die Seite ausdrücklich ausschließt: „In den Tarifen GigaMobil XS und S
    kannst Du Dein Smartphone nicht in 36 Raten zahlen“ -> [("Mobil XS", 36), …]."""
    paare = set()
    for treffer in _VF_AUSSCHLUSS.finditer(" ".join(_text(_soup(html)).split())):
        for kurz in re.split(r", | und ", treffer.group(1)):
            paare.add((f"Mobil {kurz}", int(treffer.group(2))))
    return sorted(paare)
