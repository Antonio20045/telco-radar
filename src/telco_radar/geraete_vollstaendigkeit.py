"""Soll/Ist-Vollständigkeit des Geräteradars je Anbieter (Abnahmekriterium 1).

Antonio, 21.11.2026: je Anbieter (Saturn/MediaMarkt je Netz) eine tägliche Zählung,
Soll gegen Ist, jede Differenz eine benannte Lücke mit Grund. Hier wird gerechnet,
genau einmal (Clean Code 1); die Lauf-Datei (``geraete_lauf``) trägt das Ergebnis, die
Seite (``report/geraete_vollstaendigkeit``) und der Wächter
(``geraete_soll_waechter``) lesen nur die fertigen Felder.

**Ist** sind die Bündel des Messtags (``abgerufen_am == datum``) je Anbieter: Bündel,
Modelle (Katalog-ID am Anfang der ``sku_id``), Modell × Speicher, Tarife (``tarif_id``,
ohne sie ``tarif_name``), Laufzeiten und Kombinationen (Modell × Speicher × Tarif ×
Laufzeit, ohne Farbe: ``buendel_angebot.angebot_ohne_farbe``).

**Soll** kommt aus ``geraete_soll`` (eigene Liste des Anbieters, je Ebene). Jede Ebene
(``EBENEN``) trägt ``soll``, ``soll_grund``, ``ist``, ``erfasst``, ``luecken`` (im
Soll, nicht im Ist) und ``nicht_im_soll`` (im Ist, nicht im Soll; ausgewiesen, nicht
verschluckt). Ein Soll, das nicht zu zählen ist, ist ``None`` mit ``soll_grund``.

**Gründe** kommen aus Signalen (``Signale``: Katalog, Paket, Erfassungsvermerke,
Tarifwelt-Stufe); ohne Signal heißt die Lücke ``UNBENANNT`` (Wächter rot). **Stufe 2**
(Browser) hängt sich über ``SichtbareAuswahl``/``haenge_kombinationen_ein`` an.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from .analyze.buendel_angebot import angebot_ohne_farbe, modell_und_speicher
from .geraete_soll import SATURN_NETZE
from .geraete_tarifschluessel import (
    normiert,
    nummeriert,
    preis_code,
    vergleich_eintrag,
)

ERWARTET = ("Telekom", "Vodafone", "o2", "1&1", "congstar", *SATURN_NETZE)
EBENEN = ("modelle", "modell_speicher", "kombinationen")
UNBENANNT = "unbenannt"
GRUND_STUFE2 = "wird in Stufe 2 im Browser aus der sichtbaren Auswahl gezählt"
GRUND_OHNE_LISTE = "für diesen Anbieter ist keine eigene Liste hinterlegt"
GRUND_NICHT_IM_KATALOG = "beim Anbieter gelistet, nicht im Katalog"
GRUND_PAKET = "nur im Paket mit Zubehör angeboten"
GRUND_TW_ZEIT = "Zeitbudget der Tarifwelt-Stufe erschöpft"
GRUND_TW_LISTE = "nicht in der Modellliste der Tarifwelt-Messung"
GRUND_TW_NICHT_LIEFERBAR = "beim Anbieter nicht lieferbar"
GRUND_TW_NETZ = "in diesem Netz kein vergleichbarer Tarif gelesen"
TARIFWELT_AUS = ("aus", "abgebrochen", "keine_leiter")
LISTE_HOECHSTENS = 200
"""Höchstzahl gespeicherter Einträge je Liste; die Zahl steht immer vollständig."""


@dataclass
class Signale:
    """Was der Lauf über Ausfälle weiß. ``tarifwelt_modelle`` ``None`` = unbekannt."""

    erfassung: dict = field(default_factory=dict)
    tarifwelt: dict = field(default_factory=dict)
    tarifwelt_modelle: tuple[str, ...] | None = None
    ausfall: str | None = None


@dataclass
class Ist:
    """Die Mengen des Messtags eines Anbieters."""

    buendel: int = 0
    ohne_modell: int = 0
    modelle: set = field(default_factory=set)
    modell_speicher: set = field(default_factory=set)
    tarife: set = field(default_factory=set)
    laufzeiten: set = field(default_factory=set)
    kombinationen: set = field(default_factory=set)
    kombi_roh: set = field(default_factory=set)

    def zahlen(self) -> dict:
        """Die Zählung als Zahlen."""
        return {
            "buendel": self.buendel,
            "ohne_modell": self.ohne_modell,
            "modelle": len(self.modelle),
            "modell_speicher": len(self.modell_speicher),
            "tarife": len(self.tarife),
            "laufzeiten": len(self.laufzeiten),
            "kombinationen": len(self.kombinationen),
        }


def kombi_schluessel(buendel_id: str) -> str | None:
    """„<modell>-<speicher>--<tarif>--<N>m“ aus der Bündel-ID, ohne Farbe."""
    teile = angebot_ohne_farbe(buendel_id).split("--")
    if len(teile) < 5 or modell_und_speicher(teile[2] + "-")[0] is None:
        return None
    return "--".join(teile[2:])


def _nimm(ist: Ist, b: dict) -> None:
    ist.buendel += 1
    modell, speicher = modell_und_speicher(str(b.get("sku_id") or ""))
    if modell is None:
        ist.ohne_modell += 1
    else:
        ist.modelle.add(modell)
        ist.modell_speicher.add(f"{modell}-{speicher}")
    tarif = b.get("tarif_id")
    ist.tarife.add(tarif if tarif is not None else b.get("tarif_name"))
    if b.get("laufzeit_monate") is not None:
        ist.laufzeiten.add(b["laufzeit_monate"])
    kombi = kombi_schluessel(str(b.get("id") or ""))
    if kombi is not None:
        preis = ""
        if b.get("anbieter") in SATURN_NETZE:
            preis = preis_code(b.get("geraet_zuzahlung"), b.get("tarif_monatlich"))
        ist.kombi_roh.add((kombi, preis))


def ist_zaehlung(buendel: Iterable, datum: str) -> dict[str, Ist]:
    """Die eine Ist-Zählung: Bündel des Messtags ``datum`` je Anbieter."""
    je: dict[str, Ist] = {}
    for b in buendel or ():
        b = b if isinstance(b, dict) else vars(b)
        name = b.get("anbieter")
        if not name or b.get("abgerufen_am") != datum:
            continue
        _nimm(je.setdefault(name, Ist()), b)
    for ist in je.values():
        ist.kombinationen = nummeriert(
            vergleich_eintrag(k, p) for k, p in ist.kombi_roh
        )
    return je


def _tarifwelt_grund(name: str, key: str, signale: Signale, ist_je: dict) -> str:
    tw = signale.tarifwelt
    if tw.get("status") in TARIFWELT_AUS:
        return f"Tarifwelt-Stufe {tw.get('status')}: {tw.get('grund') or ''}".strip()
    if signale.tarifwelt_modelle is not None and key not in signale.tarifwelt_modelle:
        return GRUND_TW_LISTE
    if key in (tw.get("ungelesen") or ()):
        return GRUND_TW_ZEIT
    if any(eintrag[0] == key for eintrag in tw.get("nicht_lieferbar_liste") or ()):
        return GRUND_TW_NICHT_LIEFERBAR
    for schluessel, grund in tw.get("luecken_liste") or ():
        if schluessel == key or str(schluessel).startswith(key + " "):
            return f"Tarifwelt: {grund}"
    andere = (n for n in SATURN_NETZE if n != name and n in ist_je)
    if any(key in ist_je[n].modelle for n in andere):
        return GRUND_TW_NETZ
    return UNBENANNT


def grund_fuer(name: str, modell: dict, signale: Signale, ist_je: dict) -> str:
    """Der Grund, warum ein Soll-Modell im Ist fehlt; ``UNBENANNT`` ohne Signal."""
    if not modell.get("im_katalog"):
        return GRUND_NICHT_IM_KATALOG
    if modell.get("nur_paket"):
        return GRUND_PAKET
    if signale.ausfall:
        return signale.ausfall
    key = modell["schluessel"]
    for vermerk in (f"{name}|{key}", name):
        if signale.erfassung.get(vermerk):
            return str(signale.erfassung[vermerk])
    if name in SATURN_NETZE:
        return _tarifwelt_grund(name, key, signale, ist_je)
    return UNBENANNT


def _luecke(schluessel: str, name: str, url: str, grund: str) -> dict:
    return {
        "schluessel": schluessel,
        "name": name,
        "url": url,
        "grund": grund,
        "benannt": grund != UNBENANNT,
    }


def _ebene(soll: int | None, grund: str | None, ist: int) -> dict:
    return {
        "soll": soll,
        "soll_grund": grund,
        "ist": ist,
        "erfasst": None,
        "luecken": [],
        "luecken_zahl": None,
        "nicht_im_soll": [],
        "nicht_im_soll_zahl": None,
    }


def _modell_ebene(
    name: str, soll: dict | None, ist: Ist, signale: Signale, ist_je, namen
) -> dict:
    modelle = None if soll is None else soll.get("modelle")
    if soll is None or modelle is None:
        grund = GRUND_OHNE_LISTE if soll is None else soll.get("grund")
        return _ebene(None, grund, len(ist.modelle))
    je = {m["schluessel"]: m for m in modelle}
    ebene = _ebene(len(je), None, len(ist.modelle))
    fehlend = sorted(set(je) - ist.modelle)
    luecken = [
        _luecke(
            k, je[k]["name"], je[k]["url"], grund_fuer(name, je[k], signale, ist_je)
        )
        for k in fehlend
    ]
    extra = sorted(ist.modelle - set(je))
    ebene.update(
        erfasst=len(set(je) & ist.modelle),
        luecken=unterscheidbar(luecken),
        luecken_zahl=len(luecken),
        nicht_im_soll=[{"schluessel": k, "name": namen.get(k, k)} for k in extra][
            :LISTE_HOECHSTENS
        ],
        nicht_im_soll_zahl=len(extra),
    )
    return ebene


def unterscheidbar(luecken: list[dict]) -> list[dict]:
    """Zwei Lücken mit gleichem Namen (dasselbe Gerät unter zwei Adressen) bekommen
    den letzten Teil ihrer Adresse in Klammern dazu."""
    zahl: dict[str, int] = {}
    for luecke in luecken:
        zahl[luecke["name"]] = zahl.get(luecke["name"], 0) + 1
    for luecke in luecken:
        if zahl[luecke["name"]] > 1 and luecke["url"]:
            teil = luecke["url"].rstrip("/").rsplit("/", 2)[-2:]
            luecke["name"] = f"{luecke['name']} ({'/'.join(teil)})"
    return luecken


def _unbenannt(zeile: dict) -> int:
    return sum(
        1
        for ebene in zeile["ebenen"].values()
        for luecke in ebene["luecken"]
        if not luecke["benannt"]
    )


def zeile_fuer(name: str, soll: dict | None, ist_je: dict, signale: Signale, namen):
    """Die Zeile eines Anbieters mit allen drei Ebenen."""
    ist = ist_je.get(name, Ist())
    quelle = None
    if soll is not None and soll.get("art") is not None:
        quelle = {
            k: soll.get(k)
            for k in ("art", "quelle", "gleiche_quelle_wie_sammler", "gezaehlt_um")
        }
    speicher_grund = GRUND_OHNE_LISTE if soll is None else soll.get("speicher_grund")
    zeile = {
        "name": name,
        "soll_quelle": quelle,
        "ist": ist.zahlen(),
        "ausfall": signale.erfassung.get(name) or signale.ausfall,
        "ebenen": {
            "modelle": _modell_ebene(name, soll, ist, signale, ist_je, namen),
            "modell_speicher": _ebene(None, speicher_grund, len(ist.modell_speicher)),
            "kombinationen": _ebene(None, GRUND_STUFE2, len(ist.kombinationen)),
        },
    }
    zeile["unbenannt"] = _unbenannt(zeile)
    return zeile


def baue(
    datum: str,
    gezaehlt_um: str,
    buendel: Iterable,
    soll: dict[str, dict | None],
    signale: Signale,
    namen: dict[str, str] | None = None,
) -> dict:
    """``vollstaendigkeit`` der Lauf-Datei: eine Zeile je erwartetem Anbieter (auch
    ohne Bündel und ohne Liste), dazu jeder weitere Anbieter mit Bündel am Messtag."""
    ist_je = ist_zaehlung(buendel, datum)
    reihe = list(ERWARTET) + sorted(n for n in ist_je if n not in ERWARTET)
    return {
        "datum": datum,
        "gezaehlt_um": gezaehlt_um,
        "fehler": None,
        "anbieter": [
            zeile_fuer(n, soll.get(n), ist_je, signale, namen or {}) for n in reihe
        ],
    }


@dataclass(frozen=True)
class SichtbareAuswahl:
    """Schnittstelle für Stufe 2: was ein Browser-Zähler auf EINER Produktseite als
    wählbar sieht (deaktivierte Optionen gehören nicht hinein).

    ``modell`` ist die Katalog-ID, ``speicher`` das Speichersegment der SKU („256gb“),
    ``tarife`` der Tarifschlüssel wie in der Bündel-ID, ``laufzeiten`` Monate. Ist nicht
    jede Kombination wählbar, nennt ``kombinationen`` die wählbaren ausdrücklich
    (Speicher, Tarif, Laufzeit); sonst gilt das Kreuzprodukt."""

    anbieter: str
    modell: str
    seite: str
    speicher: tuple[str, ...]
    tarife: tuple[str, ...]
    laufzeiten: tuple[int, ...]
    gezaehlt_um: str
    kombinationen: tuple[tuple[str, str, int], ...] | None = None

    def schluessel(self) -> set[str]:
        """Die Kombinationen dieser Seite im Format von ``kombi_schluessel``."""
        if self.kombinationen is not None:
            auswahl = self.kombinationen
        else:
            auswahl = tuple(
                (s, t, n)
                for s in self.speicher
                for t in self.tarife
                for n in self.laufzeiten
            )
        return {f"{self.modell}-{s}--{normiert(t)}--{n}m" for s, t, n in auswahl}


def modell_der_kombination(schluessel: str) -> str | None:
    """Katalog-ID am Anfang eines Kombinationsschlüssels."""
    return modell_und_speicher(schluessel.split("--")[0] + "-")[0]


def haenge_kombinationen_ein(
    voll: dict,
    anbieter: str,
    auswahlen: Iterable[SichtbareAuswahl],
    buendel: Iterable,
    signale: Signale,
    grund: Callable[[str], str] | None = None,
    ausgenommen: Iterable[str] = (),
    quelle: dict | None = None,
    grund_extra: Callable[[str], str] | None = None,
    soll_dazu: Iterable[str] = (),
    nicht_verglichen: dict[str, str] | None = None,
) -> dict:
    """Setzt das Kombinations-Soll eines Anbieters aus den Seiten des Browser-Zählers
    (Stufe 2) und rechnet Lücken und ``unbenannt`` neu; Ist aus ``buendel`` wie oben.

    ``grund(k)`` benennt eine Lücke (sonst Ausfallvermerk oder ``UNBENANNT``),
    ``grund_extra(k)`` einen erfassten Preis, den die Seite nicht anbietet (sonst
    ``nicht_im_soll_unbenannt``, Wächter rot). Aus dem Vergleich fallen das Ist der
    Modelle in ``ausgenommen`` (Auswahl nicht gelesen) und die Schlüssel in
    ``nicht_verglichen`` (mit Grund); ``soll_dazu`` sind bestätigte Angebote eines
    zweiten Kaufwegs (``geraete_angebot.kaufwege``)."""
    seiten = [a for a in auswahlen if a.anbieter == anbieter]
    zeile = next(z for z in voll["anbieter"] if z["name"] == anbieter)
    weg, offen = set(ausgenommen), dict(nicht_verglichen or {})
    ist = {
        k
        for k in ist_zaehlung(buendel, voll["datum"]).get(anbieter, Ist()).kombinationen
        if modell_der_kombination(k) not in weg and k not in offen
    }
    soll = set().union(set(soll_dazu), *(a.schluessel() for a in seiten))
    ebene = _ebene(len(soll) if seiten else None, None, len(ist))
    ohne = 0
    if not seiten:
        ebene["soll_grund"] = GRUND_STUFE2
    else:
        vermerk = signale.erfassung.get(anbieter) or signale.ausfall
        fest = str(vermerk) if vermerk else UNBENANNT
        fehlend, extra = sorted(soll - ist), sorted(ist - soll)
        gruende = {k: (grund(k) if grund else fest) for k in fehlend}
        ohne = sum(1 for g in gruende.values() if g == UNBENANNT)
        extras = [
            _luecke(k, k, "", grund_extra(k) if grund_extra else UNBENANNT)
            for k in extra
        ]
        ebene.update(
            erfasst=len(soll & ist),
            luecken=[_luecke(k, k, "", gruende[k]) for k in fehlend][:LISTE_HOECHSTENS],
            luecken_zahl=len(fehlend),
            nicht_im_soll=extras[:LISTE_HOECHSTENS],
            nicht_im_soll_zahl=len(extra),
            nicht_im_soll_unbenannt=sum(1 for e in extras if not e["benannt"]),
            nicht_verglichen=[_luecke(k, k, "", g) for k, g in sorted(offen.items())][
                :LISTE_HOECHSTENS
            ],
            nicht_verglichen_zahl=len(offen),
            quelle=quelle
            or {
                "art": "browser_auswahl",
                "gezaehlt_um": max(a.gezaehlt_um for a in seiten),
            },
        )
    zeile["ebenen"]["kombinationen"] = ebene
    zeile["unbenannt"] = _unbenannt(zeile)
    gelistet = sum(1 for lu in ebene["luecken"] if not lu["benannt"])
    zeile["unbenannt"] += ohne - gelistet
    return voll
