"""Kostenvergleich der Geräteseite: eine Frage, eine Rangliste.

Die Frage (Antonio, 29.09.2026): "Was kostet das iPhone 18 Pro mit S-Tarif
über 24 Monate bei jedem Wettbewerber?" Der Leser wählt Gerät, Speicher,
Tarifstufe und Ratenlaufzeit und sieht je Anbieter die Kosten über 24
Monate, günstigste zuerst.

Gerechnet wird hier nichts. Die Zahlen sind die fertigen Karten aus
`geraete_tco_karten.modelle()` (`gesamt` ist `tco_model.tco_24().gesamt`,
`zerlegung` dessen Posten). Dieses Modul wählt je Anbieter die günstigste
Karte einer Auswahl und sortiert. Dieselbe Auswahl läuft im Browser in
`app.js` (`grKosten`); `tests/test_geraete_kosten_browser.py` hält beide
zusammen.
"""
from __future__ import annotations

import re
from typing import Optional

from ..geraete_model import serie_aus_modell
from .anbieter_farben import farbe_fuer
from .geraete_tco_grafik import anbieter_slug

# Reihenfolge der Anbieter ohne Angebot am Ende der Rangliste. Vodafone
# zuerst, weil die Seite für Vodafone gebaut ist.
ANBIETER = ("Vodafone", "Telekom", "o2", "1&1", "congstar")
EIGEN = "Vodafone"

# Die Startauswahl, wenn die Adresse nichts vorgibt.
START_FAMILIE = "apple-iphone-18-pro"
START_SPEICHER = 256
START_STUFE = "s"
RATEN_OPTIONEN = ("alle", 12, 24, 36)
START_RATEN = "alle"

HORIZONT = 24

# So viele Geräte einer Marke stehen zugeklappt in der Auswahl.
FAMILIEN_SICHTBAR = 8
MEHR = "__mehr"

HERSTELLER_FOLGE = ("Apple", "Samsung", "Google", "Xiaomi")
SEGMENT_FOLGE = ("flagship", "premium", "mid", "entry")

# Tarife ohne Volumengrenze fallen in die oberste Stufe. Die Tarifleiter
# (`geraete_tco_band.tarifleiter`) kennt das XL-Volumen erst nach dem
# nächsten Tariflauf; bis dahin bekommen unbegrenzte Tarife dort kein Band.
_UNBEGRENZT = re.compile(r"unlimited|unbegrenzt", re.IGNORECASE)
_SPEICHER_ENDE = re.compile(r"\s+\d+\s*(GB|TB)$")


def speicher_text(gb: Optional[int]) -> str:
    if gb is None:
        return ""
    if gb >= 1024 and gb % 1024 == 0:
        return f"{gb // 1024} TB"
    return f"{gb} GB"


def _stufe(karte: dict, oberste: Optional[str]) -> Optional[str]:
    if karte.get("band"):
        return karte["band"]
    text = f"{karte.get('tarif') or ''} {karte.get('band_gb_text') or ''}"
    if oberste and _UNBEGRENZT.search(text):
        return oberste
    return None


def _familie_id(modell: dict) -> str:
    speicher = modell.get("speicher")
    mid = modell["id"]
    ende = f"-{speicher}"
    return mid[: -len(ende)] if speicher and mid.endswith(ende) else mid


def _familie_name(modell: dict) -> str:
    return _SPEICHER_ENDE.sub("", modell.get("name") or modell["id"])


def _mal(anzahl, betrag) -> str:
    from .geraete_tco_grafik import euro
    return f"{anzahl} × {euro(betrag)}"


def _posten(karte: dict) -> list:
    """Der Rechenweg einer Karte mit kurzen, prüfbaren Namen.

    Die Beträge sind die von `tco_model` (`zerlegung` trennt die
    Restschuld nach Monat 24 ab und lässt 0,00-€-Posten weg; die kommen
    aus `bestandteile` dazu, ein gemessener Anschlusspreis von 0,00 € ist
    eine Aussage). Neu ist nur der Name: "24 × 51,00 €" steht nur dort, wo
    Anzahl mal Monatsbetrag den Posten genau trifft, sonst der Oberbegriff.
    """
    zerlegung = karte.get("zerlegung") or []
    namen = {p["name"] for p in zerlegung}
    roh = [dict(p, offen=bool(p.get("offen"))) for p in zerlegung]
    roh += [dict(p, offen=False) for p in karte.get("bestandteile") or []
            if p["name"] not in namen and (not zerlegung or p["betrag"] == 0)]
    rate, tarif = karte.get("rate"), karte.get("monatlich")
    buendel = karte.get("buendel_monatlich")
    posten = []
    for p in roh:
        art, betrag = p.get("kategorie"), p["betrag"]
        name = p["name"]
        rang = 9
        if art == "tarif":
            # Der Produktname des Tarifs ("Allnet Flat S") steht am Link zum
            # Angebot; hier hieße er unter der Stufe M "S" und verwirrte.
            name, rang = "Tarif", 1
            wert = tarif
        elif art == "raten":
            name, rang = "Geräteraten", 3
            wert = rate
        elif art == "buendel":
            name, rang = "Tarif mit Gerät", 2
            wert = buendel
        elif art == "restschuld":
            name, rang = f"Restschuld nach Monat {HORIZONT}", 4
            wert = rate if rate is not None else buendel
        elif name == "Gerätezuzahlung":
            name, wert, rang = "Anzahlung", None, 0
        else:
            wert = None
        mal = ""
        if wert:
            anzahl = round(betrag / wert)
            if anzahl > 0 and round(anzahl * wert, 2) == round(betrag, 2):
                mal = _mal(anzahl, wert)
        posten.append({"name": name, "mal": mal, "betrag": betrag,
                       "offen": p["offen"], "rang": rang})
    posten.sort(key=lambda p: p["rang"])
    for p in posten:
        del p["rang"]
    return posten


def _angebot(karte: dict, stufe: str) -> dict:
    """Die Felder einer Karte, die Zeile und Rechenweg brauchen."""
    posten = _posten(karte)
    return {
        "anbieter": karte["anbieter"],
        "sku": karte.get("sku_id") or "",
        "stufe": stufe,
        "raten": karte.get("raten_laufzeit"),
        "monate": karte.get("leitzahl_monate"),
        "gesamt": karte["gesamt"],
        "tarif": karte.get("tarif") or "",
        "gb": karte.get("band_gb_text") or "",
        "zuzahlung": karte.get("zuzahlung"),
        "rate": karte.get("rate"),
        "monatlich": karte.get("monatlich"),
        "buendel_monatlich": karte.get("buendel_monatlich"),
        "posten": posten,
        "url": karte.get("quelle_url") or "",
        "stand": karte.get("abgerufen_am") or "",
        "stand_kurz": _datum_kurz(karte.get("abgerufen_am") or ""),
        "frisch": bool(karte.get("frisch")),
    }


def _nur_guenstigste(liste: list) -> list:
    """Je (Anbieter, Stufe, Raten) nur das günstigste Angebot: mehr braucht
    die Rangliste nicht, und die Seite trägt die Daten inline."""
    best: dict[tuple, dict] = {}
    for a in liste:
        schluessel = (a["anbieter"], a["stufe"], a["raten"])
        if schluessel not in best or a["gesamt"] < best[schluessel]["gesamt"]:
            best[schluessel] = a
    return sorted(best.values(), key=lambda a: (a["gesamt"], a["anbieter"]))


def _datum_kurz(iso: str) -> str:
    """"2026-09-15" -> "15.09."; leer, wenn das Datum nicht lesbar ist."""
    m = re.fullmatch(r"\d{4}-(\d{2})-(\d{2})", iso)
    return f"{m.group(2)}.{m.group(1)}." if m else ""


def _brauchbar(karte: dict) -> bool:
    return bool(karte.get("belastbar") and karte.get("vergleichbar")
                and not karte.get("naeherung")
                and karte.get("gesamt") is not None)


def aufbereiten(tco: dict, geraete_katalog=None) -> dict:
    """Geräte, Stufen und Angebote für die Seite und für `app.js`.

    `geraete_katalog` (`geraete_config.lade_katalog`) liefert Generation und
    Segment für die Reihenfolge der Geräte; ohne ihn gilt die Zahl im
    Namen als Generation."""
    katalog = tco.get("baender_katalog") or []
    stufen = [{"key": b["key"], "label": b["label"],
               "gb": b.get("bereich") or ""} for b in katalog]
    oberste = stufen[-1]["key"] if stufen else None
    if stufen and not stufen[-1]["gb"]:
        stufen[-1]["gb"] = "unbegrenzt"

    familien: dict[str, dict] = {}
    angebote: dict[str, list] = {}
    for modell in tco.get("modelle") or []:
        liste = []
        for karte in modell.get("karten") or []:
            if not _brauchbar(karte):
                continue
            stufe = _stufe(karte, oberste)
            if stufe is None:
                continue
            liste.append(_angebot(karte, stufe))
        if not liste:
            continue
        angebote[modell["id"]] = _nur_guenstigste(liste)
        fid = _familie_id(modell)
        fam = familien.setdefault(fid, {
            "id": fid, "name": _familie_name(modell),
            "hersteller": modell.get("hersteller") or "", "speicher": []})
        fam["speicher"].append({"gb": modell.get("speicher"),
                                "text": speicher_text(modell.get("speicher")),
                                "modell": modell["id"]})

    for fam in familien.values():
        fam["speicher"].sort(key=lambda s: s["gb"] or 0)

    hersteller = sorted({f["hersteller"] for f in familien.values()},
                        key=lambda h: (HERSTELLER_FOLGE.index(h)
                                       if h in HERSTELLER_FOLGE
                                       else len(HERSTELLER_FOLGE), h))
    geraete = _geraete_folge(list(familien.values()), hersteller,
                             _katalog_info(geraete_katalog))

    return {
        "hat_daten": bool(angebote),
        "stufen": stufen,
        "raten": list(RATEN_OPTIONEN),
        "anbieter": [{"name": a, "slug": anbieter_slug(a),
                      "farbe": farbe_fuer(a), "eigen": a == EIGEN}
                     for a in ANBIETER],
        "hersteller": hersteller,
        "geraete": geraete,
        "angebote": angebote,
        "horizont": HORIZONT,
        "familien_sichtbar": FAMILIEN_SICHTBAR,
        "mehr": MEHR,
        "start": startwahl(geraete, stufen, angebote),
    }


def _katalog_info(katalog) -> dict:
    """device_id -> (generation, segment) aus dem Gerätekatalog."""
    return {g.device_id: (g.generation, g.segment or "")
            for g in (getattr(katalog, "geraete", None) or [])}


def _geraete_folge(familien: list, hersteller: list, info: dict) -> list:
    """Reihenfolge der Geräte je Marke: zuerst die aktuelle Generation
    jeder Baureihe, Flaggschiffe vorn (Galaxy S26 Ultra vor Z Fold8 vor
    Galaxy A57, iPhone Air neben dem iPhone 18), danach die Vorgänger je
    Baureihe, neueste zuerst."""
    def seg_rang(seg: str) -> int:
        return (SEGMENT_FOLGE.index(seg) if seg in SEGMENT_FOLGE
                else len(SEGMENT_FOLGE))

    def gen(f: dict) -> int:
        g = info.get(f["id"], (None, ""))[0]
        if g is None:
            zahl = re.search(r"\d+", f["name"])
            g = int(zahl.group()) if zahl else 0
        return g

    serie = {f["id"]: (f["hersteller"], serie_aus_modell(f["name"]))
             for f in familien}
    neueste: dict = {}
    serie_seg: dict = {}
    for f in familien:
        k = serie[f["id"]]
        neueste[k] = max(neueste.get(k, 0), gen(f))
        serie_seg[k] = min(serie_seg.get(k, 99),
                           seg_rang(info.get(f["id"], (None, ""))[1]))

    def schluessel(f: dict):
        k = serie[f["id"]]
        # Ohne Segment im Katalog (neue Modelle) gilt das beste der Baureihe.
        seg = seg_rang(info.get(f["id"], (None, ""))[1])
        if seg == len(SEGMENT_FOLGE):
            seg = serie_seg[k]
        aktuell = gen(f) == neueste[k]
        if aktuell:
            rest = (seg, serie_seg[k], k[1], 0, _Absteigend(f["name"]))
        else:
            rest = (serie_seg[k], k[1], -gen(f), seg, _Absteigend(f["name"]))
        return (hersteller.index(f["hersteller"]), not aktuell) + rest

    return sorted(familien, key=schluessel)


class _Absteigend:
    """Natürliche Sortierung, umgekehrt: die neueste Generation und das
    größere Modell stehen vorn ("Z Fold8" vor "Z Fold 7", "18 Pro Max" vor
    "18 Pro" vor "18")."""

    def __init__(self, name: str):
        flach = re.sub(r"\s+(?=\d)", "", name.lower())
        self.teile = [int(t) if t.isdigit() else t
                      for t in re.findall(r"\d+|\D+", flach)]

    def __lt__(self, other: "_Absteigend") -> bool:
        for a, b in zip(self.teile, other.teile):
            if a == b:
                continue
            if type(a) is not type(b):
                return isinstance(a, str)
            if isinstance(a, str) and (a.startswith(b) or b.startswith(a)):
                # "Pro XL" vor "Pro": der längere Zusatz ist das größere
                # Modell.
                return len(a) > len(b)
            return a > b
        return len(self.teile) > len(other.teile)


def startwahl(geraete: list, stufen: list, angebote: dict) -> dict:
    """Das Startgerät in der Stufe, in der die meisten Anbieter ein
    Angebot haben: die Seite öffnet nie mit einer Liste aus Strichen."""
    fam = next((f for f in geraete if f["id"] == START_FAMILIE),
               geraete[0] if geraete else None)
    if fam is None:
        return {}
    sp = next((s for s in fam["speicher"] if s["gb"] == START_SPEICHER),
              fam["speicher"][0])
    keys = [s["key"] for s in stufen]
    je_stufe = {k: {a["anbieter"] for a in angebote.get(sp["modell"], [])
                    if a["stufe"] == k} for k in keys}
    stufe = max(keys, key=lambda k: (len(je_stufe[k]), k == START_STUFE),
                default="")
    return {"familie": fam["id"], "modell": sp["modell"], "stufe": stufe,
            "raten": START_RATEN}


def rangliste(daten: dict, modell: str, stufe: str, raten) -> dict:
    """Je Anbieter die günstigste Karte der Auswahl, sortiert.

    Verglichen wird nur innerhalb eines Zeitraums (`monate`): die Gruppe
    über `HORIZONT` Monate zuerst, danach z. B. ein Bündelmonatspreis über
    36 Monate (1&1) in einer eigenen Gruppe. "günstigste" und der Abstand
    gibt es nur in einer Gruppe mit mindestens zwei Anbietern. Anbieter
    ohne Angebot stehen in `ohne`.
    """
    alle = daten.get("angebote", {}).get(modell) or []
    passend = [a for a in alle if a["stufe"] == stufe
               and (raten == "alle" or a["raten"] == raten)]
    best: dict[str, dict] = {}
    for a in passend:
        alt = best.get(a["anbieter"])
        if alt is None or (a["gesamt"], a["raten"] or 0) < (alt["gesamt"],
                                                             alt["raten"] or 0):
            best[a["anbieter"]] = a
    zeitraeume = sorted({a["monate"] for a in best.values()},
                        key=lambda m: (m != HORIZONT, m or 0))
    gruppen = []
    for monate in zeitraeume:
        liste = sorted((a for a in best.values() if a["monate"] == monate),
                       key=lambda a: (a["gesamt"], a["anbieter"]))
        mehrere = len(liste) > 1
        gruppen.append({"monate": monate, "zeilen": [
            {"anbieter": a["anbieter"], "angebot": a,
             "abstand": round(a["gesamt"] - liste[0]["gesamt"], 2)
             if mehrere else None,
             "sieger": mehrere and a is liste[0]} for a in liste]})
    # Anbieter, die nur der Ratenfilter ausblendet, stehen nicht bei den
    # Lücken, sondern mit ihren Ratenzahlen zum Umschalten.
    andere: dict[str, set] = {}
    for a in alle:
        if (a["stufe"] == stufe and a["anbieter"] not in best
                and a["raten"] is not None):
            andere.setdefault(a["anbieter"], set()).add(a["raten"])
    anders = [{"anbieter": n, "raten": sorted(andere[n])}
              for n in ANBIETER if n in andere]
    ohne = [n for n in ANBIETER if n not in best and n not in andere]
    return {"gruppen": gruppen, "anders": anders, "ohne": ohne}


def _chip(wert, text, an, aus=False, zusatz="") -> dict:
    return {"wert": wert, "text": text, "zusatz": zusatz, "an": an,
            "aus": aus}


def familien_chips(daten: dict, fam: dict, alle: bool) -> list:
    """Die Geräte einer Marke; zugeklappt die ersten `FAMILIEN_SICHTBAR`
    (plus das gewählte), dahinter ein Chip, der den Rest zeigt."""
    liste = [f for f in daten["geraete"] if f["hersteller"] == fam["hersteller"]]
    zeigen = [f for i, f in enumerate(liste)
              if alle or i < FAMILIEN_SICHTBAR or f["id"] == fam["id"]]
    chips = [_chip(f["id"], f["name"], f["id"] == fam["id"]) for f in zeigen]
    if len(liste) > FAMILIEN_SICHTBAR:
        chips.append(_chip(MEHR, "weniger" if alle else
                           f"+{len(liste) - len(zeigen)} ältere", False))
    return chips


def ansicht(daten: dict, wahl: dict, alle_familien: bool = False) -> dict:
    """Alles, was die Seite für eine Auswahl zeigt: Titel, die fünf
    Chip-Reihen und die Rangliste. `app.js` baut dasselbe in `ansicht()`."""
    fam = next(f for f in daten["geraete"] if f["id"] == wahl["familie"])
    sp = next(s for s in fam["speicher"] if s["modell"] == wahl["modell"])
    angebote = daten["angebote"].get(wahl["modell"]) or []
    stufen_mit = {a["stufe"] for a in angebote}
    raten_mit = {a["raten"] for a in angebote if a["stufe"] == wahl["stufe"]}
    reihen = [
        {"name": "hersteller", "label": "Marke",
         "chips": [_chip(h, h, h == fam["hersteller"])
                   for h in daten["hersteller"]]},
        {"name": "familie", "label": "Gerät",
         "chips": familien_chips(daten, fam, alle_familien)},
        {"name": "modell", "label": "Speicher",
         "chips": [_chip(s["modell"], s["text"], s["modell"] == sp["modell"])
                   for s in fam["speicher"]]},
        {"name": "stufe", "label": "Tarif",
         "chips": [_chip(s["key"], s["label"], s["key"] == wahl["stufe"],
                         aus=s["key"] not in stufen_mit, zusatz=s["gb"])
                   for s in daten["stufen"]]},
        {"name": "raten", "label": "Raten",
         "chips": [_chip(r, "alle" if r == "alle" else str(r),
                         r == wahl["raten"],
                         aus=r != "alle" and r not in raten_mit)
                   for r in daten["raten"]]},
    ]
    stil = {a["name"]: a for a in daten["anbieter"]}
    rang = rangliste(daten, wahl["modell"], wahl["stufe"], wahl["raten"])
    for i, gruppe in enumerate(rang["gruppen"]):
        for j, z in enumerate(gruppe["zeilen"]):
            # Die erste Zahl der Seite ist immer die größte, auch wenn
            # nur ein Anbieter da ist und es keinen "günstigsten" gibt.
            z["erste"] = i == 0 and j == 0 and gruppe["monate"] == HORIZONT
            z["stil"] = stil.get(z["anbieter"], {
                "farbe": farbe_fuer(z["anbieter"]), "eigen": False})
    return {"titel": fam["name"], "speicher": sp["text"], "reihen": reihen,
            "gruppen": rang["gruppen"], "anders": rang["anders"],
            "ohne": rang["ohne"],
            "auswahl": auswahl_liste(daten)}


def auswahl_liste(daten: dict) -> list:
    """Alle Geräte je Marke für die Auswahlliste am Telefon."""
    return [{"hersteller": h, "geraete": [f for f in daten["geraete"]
                                          if f["hersteller"] == h]}
            for h in daten["hersteller"]]


def seite(tco: dict, geraete_katalog=None) -> dict:
    """Der Kontext der Vorlage: Daten, Startansicht und die Daten als JSON
    für `app.js`."""
    import json
    daten = aufbereiten(tco, geraete_katalog)
    start = daten["start"]
    return dict(daten,
                ansicht=ansicht(daten, start) if start else None,
                json=json.dumps(daten, ensure_ascii=False,
                                separators=(",", ":")).replace("</", "<\\/"))
