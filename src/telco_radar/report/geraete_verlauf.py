"""Reiter 3 der Geraeteseite: der Preisverlauf EINES Geraets (B4, 30.08.2026).

Die drei Regeln des Auftrags, und alle drei sind Verbote:

    1. Ein Diagramm zeigt genau EIN Geraet. Man waehlt erst aus, dann wird
       gezeichnet - eine Linie je Anbieter fuer dieses eine Geraet. Niemals
       mehrere Geraete in einem Bild.
    2. Ohne Auswahl steht hier KEIN Diagramm, auch kein leeres.
    3. Hoechstens acht Linien und hoechstens acht WAAGERECHTE
       Datumsbeschriftungen. Weitere Messpunkte werden gezeichnet, nicht
       beschriftet.

Warum die Daten hier entstehen und das SVG im Browser
-----------------------------------------------------
Die Zeitraumschalter (woechentlich / monatlich / Quartal, dazu Von-Bis)
rechnen die Reihe um. Alle Faelle vorzurendern hiesse, fuer 59 Geraete mal
vier Zeitraeume 236 SVGs in eine Seite zu legen, die unter drei
Bildschirmen bleiben soll. Also liefert dieses Modul die REIHEN als Daten,
und `app.js` zeichnet daraus - von Hand, ohne Bibliothek, wie der Auftrag
es verlangt.

Der Preis dieser Entscheidung ist, dass ein statischer Test das Diagramm
nicht sieht. Deshalb misst `tests/test_geraete_reiter_browser.py` es im
echten Chromium, und `scripts/pruefe_portal.py` Kriterium 11 tut dasselbe:
kein gedrehter Text, keine Schrift unter 12 px, hoechstens acht
Datumsbeschriftungen - im GERENDERTEN SVG, nicht im Quelltext.

Der ehrliche Leerzustand
------------------------
Es sind heute VIER Messtermine, und die Zahl entsteht aus zwei Quellen:
`geraete_preise.jsonl` traegt nur AENDERUNGSpunkte (10.08. und 29.08.), dazu
kommen die Tage, an denen ein unveraenderter Preis BESTAETIGT wurde
(`last_verified`). Wer nur die Aenderungsdatei zaehlt, kommt auf zwei und
unterschlaegt damit die halbe Messreihe - dieser Fehler ist beim Bau dieses
Moduls einmal gemacht worden.

Die Zahl wird GERECHNET und nirgends festgeschrieben; steht sie naechste
Woche bei fuenf, sagt die Seite fuenf, ohne dass jemand eine Zeile aendert.
"""
from __future__ import annotations

from ..geraete_model import VERGLEICHBARE_ZUSTAENDE

# Hoechstens acht Linien. Mehr Anbieter als das kann ein Mensch in einem
# Liniendiagramm nicht auseinanderhalten, und die Legende darunter waere
# laenger als das Bild.
MAX_LINIEN = 8

# Hoechstens acht waagerechte Datumsbeschriftungen. Diese Grenze ist der
# Grund, warum die Achse lesbar bleibt: sie ist der Ersatz fuer die 114
# gedrehten Etiketten der geloeschten Grafik. Weitere Messpunkte werden
# GEZEICHNET, nur nicht beschriftet - eine Luecke ist ehrlich, ein gedrehtes
# Etikett ist eine Zumutung.
MAX_DATUMSMARKEN = 8

# Ab wann Aussagen ueber Preisverfall und Verweildauer tragen. Nicht
# gerechnet, sondern gesetzt: bei zwei Messterminen im Abstand von 19 Tagen
# ist jede Steigung eine Gerade durch zwei Punkte.
BELASTBAR_AB_WOCHEN = 12

# Vodafone ist rot, alle anderen neutral und unterscheidbar. Die Reihenfolge
# ist fest, damit derselbe Anbieter ueber zwei Ausgaben dieselbe Farbe
# behaelt - eine Farbe, die je Auswahl wechselt, ist keine Kennzeichnung.
EIGEN_FARBE = "#e60000"
FARBEN = ("#2b5bd7", "#217a3c", "#8a5a00", "#6b3fa0",
          "#0d7c8c", "#a3123a", "#4a5568")


def _eigen(anbieter: str) -> bool:
    return (anbieter or "").strip().lower() == "vodafone"


def _label(geraet, speicher) -> str:
    if not geraet:
        return "?"
    return f"{geraet.modell} {speicher} GB" if speicher else geraet.modell


def _punkte(listungen: list, historie) -> list[dict]:
    """Alle Messpunkte einer Listungsmenge, aelteste zuerst.

    Die Historie traegt nur AENDERUNGSpunkte - ein unveraenderter Preis
    schreibt keine Zeile. Die rechte Kante jeder Kurve ist deshalb nicht der
    letzte Historieneintrag, sondern `last_verified` aus der Datenbank: der
    Tag, an dem der Preis zuletzt BESTAETIGT wurde. Ohne diesen Zusatz endet
    jede Linie am Tag ihrer letzten Aenderung und behauptet damit, das
    Geraet sei seitdem nicht mehr gesehen worden.
    """
    punkte = []
    for e in listungen:
        for satz in historie.reihe(e.get("id") or ""):
            preis = satz.get("preis_ohne_vertrag")
            if preis is None or not satz.get("datum"):
                continue
            punkte.append({"datum": satz["datum"], "anbieter": e.get("anbieter"),
                           "preis": float(preis), "art": "gemessen"})
        letzt = e.get("last_verified")
        preis = e.get("preis_ohne_vertrag")
        if letzt and preis is not None:
            punkte.append({"datum": letzt, "anbieter": e.get("anbieter"),
                           "preis": float(preis), "art": "bestaetigt"})
    # Je (Anbieter, Tag) genau ein Punkt: zwei Farben desselben Geraets sind
    # zwei Listungen, aber EIN Preis auf der Kurve. Der niedrigste gewinnt -
    # das ist der Preis, zu dem der Anbieter das Geraet an dem Tag abgab.
    je_tag: dict[tuple, dict] = {}
    for p in punkte:
        k = (p["anbieter"], p["datum"])
        if k not in je_tag or p["preis"] < je_tag[k]["preis"]:
            je_tag[k] = p
    return sorted(je_tag.values(), key=lambda p: (p["datum"], p["anbieter"]))


def _reihen(punkte: list) -> list[dict]:
    """Eine Reihe je Anbieter, Vodafone zuerst und rot.

    Gedeckelt auf MAX_LINIEN. Verdraengt wird der Anbieter mit den WENIGSTEN
    Messpunkten - eine Linie aus einem einzigen Punkt ist ohnehin keine
    Linie, und der eigene Anbieter ist von der Kappung ausgenommen: eine
    Preisgrafik ohne uns beantwortet die Frage nicht, wegen der sie da ist.
    """
    je_anbieter: dict[str, list] = {}
    for p in punkte:
        je_anbieter.setdefault(p["anbieter"], []).append(p)

    geordnet = sorted(je_anbieter.items(),
                      key=lambda kv: (not _eigen(kv[0]), -len(kv[1]), kv[0]))
    reihen, farbe = [], 0
    for name, ps in geordnet[:MAX_LINIEN]:
        if _eigen(name):
            f = EIGEN_FARBE
        else:
            f = FARBEN[farbe % len(FARBEN)]
            farbe += 1
        reihen.append({
            "anbieter": name, "farbe": f, "eigen": _eigen(name),
            "punkte": [{"datum": p["datum"], "preis": p["preis"]} for p in ps],
        })
    return reihen


def geraete_mit_verlauf(eintraege: list, historie, katalog) -> list[dict]:
    """Je (Modell, Speicher) ein waehlbares Geraet mit seinen Reihen.

    Nur Neugeraete ohne Vertrag: ein Gebrauchtpreis und ein Neupreis in
    derselben Kurve waeren zwei Produkte in einer Linie, und der Sprung
    dazwischen saehe aus wie ein Preissturz.
    """
    gruppen: dict[tuple, list] = {}
    for e in eintraege:
        if (e.get("zustand") or "neu") not in VERGLEICHBARE_ZUSTAENDE:
            continue
        if e.get("preis_ohne_vertrag") is None:
            continue
        gruppen.setdefault((e.get("device_id"), e.get("speicher_gb")), []).append(e)

    geraete = []
    for (gid, speicher), listungen in gruppen.items():
        g = katalog.nach_id(gid) if katalog else None
        reihen = _reihen(_punkte(listungen, historie))
        if not reihen:
            continue
        alle = [p["preis"] for r in reihen for p in r["punkte"]]
        tage = sorted({p["datum"] for r in reihen for p in r["punkte"]})
        geraete.append({
            "id": f"{gid}-{speicher or 0}",
            "label": _label(g, speicher),
            "hersteller": g.hersteller if g else "",
            "speicher": speicher,
            "suchtext": " ".join(filter(None, [
                g.hersteller if g else "", g.modell if g else gid,
                f"{speicher} GB" if speicher else "",
                *sorted({(e.get("farbe_normalisiert") or e.get("farbe_roh") or "")
                         for e in listungen}),
            ])).lower(),
            "reihen": reihen,
            "min": min(alle), "max": max(alle),
            "anbieter": len(reihen),
            "messpunkte": len(alle),
            "tage": tage,
            "aktuell": _aktuell(reihen),
        })
    return sorted(geraete, key=lambda x: (-x["messpunkte"], x["label"]))


def _aktuell(reihen: list) -> list[dict]:
    """Die Tabelle unter dem Diagramm: aktueller Preis je Anbieter.

    `veraenderung` bleibt None, solange ein Anbieter nur EINEN Messpunkt
    hat. "0 Tage" und "-0,00 EUR" sind keine Auskunft, und der Auftrag
    verbietet sie ausdruecklich - eine Zeile, die nichts sagt, kommt nicht
    auf die Seite.
    """
    zeilen = []
    for r in reihen:
        ps = sorted(r["punkte"], key=lambda p: p["datum"])
        if not ps:
            continue
        letzt = ps[-1]
        veraenderung = None
        if len(ps) > 1 and ps[0]["preis"] != letzt["preis"]:
            veraenderung = round(letzt["preis"] - ps[0]["preis"], 2)
        zeilen.append({
            "anbieter": r["anbieter"], "eigen": r["eigen"], "farbe": r["farbe"],
            "preis": letzt["preis"], "stand": letzt["datum"],
            "veraenderung": veraenderung, "messpunkte": len(ps),
        })
    return sorted(zeilen, key=lambda z: z["preis"])


def aufbereiten(eintraege: list, historie, katalog) -> dict:
    """Alles, was Reiter 3 braucht - Daten, kein SVG."""
    geraete = geraete_mit_verlauf(eintraege, historie, katalog)
    tage = sorted({t for g in geraete for t in g["tage"]})
    return {
        "hat_daten": bool(geraete),
        "geraete": geraete,
        "seit": tage[0] if tage else "",
        "bis": tage[-1] if tage else "",
        "messtermine": len(tage),
        "belastbar_ab_wochen": BELASTBAR_AB_WOCHEN,
        "max_linien": MAX_LINIEN,
        "max_datumsmarken": MAX_DATUMSMARKEN,
    }


def leer() -> dict:
    return {"hat_daten": False, "geraete": [], "seit": "", "bis": "",
            "messtermine": 0, "belastbar_ab_wochen": BELASTBAR_AB_WOCHEN,
            "max_linien": MAX_LINIEN, "max_datumsmarken": MAX_DATUMSMARKEN}
