"""Wettbewerbs-Radar (RAD-1, 08.09.2026): §2b woertlich.

DIE FRAGE, WEGEN DER DIESE SEITE EXISTIERT
-------------------------------------------
    "Bei welchen Modellen ist Vodafone gerade teurer als der Wettbewerb,
     und um wie viel?" (Antonios Beispiel: "hier ist Vodafone 10 % teurer
     als der Wettbewerber bei dem Modell.")

Leitzahl ist die %-ABWEICHUNG MIT VORZEICHEN, nicht der Absolutpreis:

    (Wettbewerber_TCO24 - Vodafone_TCO24) / Vodafone_TCO24 * 100

positiv = Wettbewerber teurer (gut fuer Vodafone), negativ = Wettbewerber
guenstiger (schlecht fuer Vodafone - "zuungunsten Vodafones", genau der
Fall aus Antonios Beispiel). Sortiert wird deshalb AUFSTEIGEND: die
staerkste Benachteiligung Vodafones (der kleinste, also negativste Wert)
steht zuerst. **Diese Reihenfolge ist eine bewusste Leseentscheidung, kein
Versehen - siehe die Anmerkung am Ende dieses Kopfes.**

WARUM DIESE DATEI KEINE ZWEITE RECHNUNG IST
--------------------------------------------
Gerechnet wird ausschliesslich in `tco_model` (`tco_24()`), gelesen ueber
die fertigen Karten aus `geraete_tco_karten.modelle()` - genau wie
`geraete_tco_band.py` es fuer den Graphen tut. Diese Datei rechnet nur die
EINE zusaetzliche Division (die Abweichung selbst) und vergleicht dafuer
zwei bereits fertige TCO-24-Betraege.

BASIS JE GERAET, BAND ALS SCHRANKE (§2b/§7)
--------------------------------------------
Die Basis ist `modell["referenz"]` - dieselbe EINE Vodafone-Referenz, die
auch die TCO-Hauptansicht und ihr Delta-Banner benutzen (echtes Buendel
schlaegt die gerechnete Naeherung, siehe `geraete_tco_karten._referenzkarte`).
Es gibt also GENAU EINE Vodafone-Basis je Geraet, kein Band-Sammelsurium.

Ein Wettbewerber wird dagegen NUR verglichen, wenn sein Tarif im SELBEN
Tarifband liegt wie der Tarif der Vodafone-Basis (GRAPH-1-Bandlogik,
`geraete_tco_band.tarif_baender`). Liegt er in einem anderen Band oder laesst
sich keins von beiden bestimmen (kein Datenvolumen erhoben, oder
unbegrenzt), heisst die Zeile ehrlich "Band-Mismatch" statt eine Zahl zu
erfinden - AUFTRAG_GERAETESEITE.md §2b: "bei Band-Mismatch ehrlich
benennen, nicht mischen".

WETTBEWERBERKREIS
------------------
Netzbetreiber: Telekom, 1&1, o2 - dieselben drei, die
`geraete_tco_karten.ANBIETER_REIHENFOLGE` neben Vodafone ohnehin auf JEDER
Karte fuehrt (B.2.5: "ein Anbieter, der weggelassen wird, sieht aus wie
einen, den es nicht gibt"). congstar bleibt bewusst draussen - dieselbe
Regel wie auf der Hauptansicht ("eine leere Zeile fuer jede denkbare
Zweitmarke waere eine Wand aus Luecken"), und §2b nennt es nicht.

Haendler (Gerätepreis, eigener Abschnitt): Saturn, mobilcom-debitel, Amazon
- ausdruecklich im Auftrag genannt. Sie vergleichen GERAETEPREIS gegen
GERAETEPREIS (kein Tarif, keine TCO) und benutzen dieselbe %-Formel gegen
Vodafones Gerätepreis. Datenquelle ist die bestehende
`geraete_vergleich.vergleich()` - keine zweite Preisrechnung, nur ein
zweiter Filter (anbieter_typ == "handel").

DIE SORTIERRICHTUNG, AUSGESCHRIEBEN (Widerspruch im Auftrag aufgeloest)
------------------------------------------------------------------------
BRIEF_RAD1.md nennt in der Einleitung "positiv = Wettbewerber teurer,
negativ = günstiger" UND in den Fachlichen Regeln fuer dieselbe Formel den
Klammerzusatz "(d. h. Wettbewerber am teuersten relativ)" fuer die
Sortierung "zuungunsten Vodafones" - das widerspricht sich: bei fester
Vorzeichendefinition ist "Wettbewerber am teuersten" der POSITIVE, fuer
Vodafone GUENSTIGE Fall, nicht der "zuungunsten"-Fall. Die Normen-Quelle
(AUFTRAG_GERAETESEITE.md §2b) loest den Widerspruch mit ihrem woertlichen
Beispiel auf: "hier ist Vodafone 10 % teurer als der Wettbewerber" ist DER
Fall, fuer den die Seite geoeffnet wird, und das ist rechnerisch der
NEGATIVE Wert (Wettbewerber guenstiger). Sortiert wird deshalb aufsteigend
(negativste/"zuungunsten Vodafones"-Werte zuerst) - siehe
`outputs/phase-rad1-2026-09-08.md` fuer die ausgeschriebene Begruendung.
"""
from __future__ import annotations

from typing import Optional

from . import geraete_tco_band, geraete_tco_karten

# Die drei Netzbetreiber-Wettbewerber - dieselbe Menge, die
# `geraete_tco_karten.modelle()` ohnehin immer (mit oder ohne Zahl) neben
# Vodafone fuehrt.
NETZ_WETTBEWERBER = tuple(a for a in geraete_tco_karten.ANBIETER_REIHENFOLGE
                          if a != "Vodafone")

STATUS_VERGLEICHBAR = "vergleichbar"
STATUS_BAND_MISMATCH = "band_mismatch"
STATUS_KEIN_BUENDEL = "kein_buendel"
STATUS_NICHT_VERGLEICHBAR = "nicht_vergleichbar"   # z. B. refurbished

# Wie viele Geraete-Gruppen ohne Aufklappen sichtbar sind. NICHTS wird
# geloescht - der Rest steht im DOM hinter einem <details> (Test c: nicht
# erhebbare/unvergleichbare Zeilen duerfen nie verschwinden, auch nicht
# hinter einer Kappung).
SICHTBAR_MAX = 15
HAENDLER_SICHTBAR_MAX = 20

_BAND_LABEL = {k: l for k, l, _ in geraete_tco_band.BAENDER}


def _band_label(band: Optional[str]) -> str:
    if not band:
        return "nicht bestimmbar"
    return _BAND_LABEL.get(band, band)


def _beleg(quelle_url: str, abgerufen_am: str) -> dict:
    return {"quelle_url": quelle_url or "", "abgerufen_am": abgerufen_am or ""}


def _vodafone_basis(modell: dict, band_je_tarif: dict) -> Optional[dict]:
    """Die EINE Vodafone-Referenz dieses Geraets, mit ihrem Tarifband.

    `ref["aus_buendel"]` steht nur, wenn `_referenz_aus_buendel` sie gebaut
    hat (ein ECHTES eigenes Buendel) - sonst kommt sie aus
    `_vodafone_referenz` (Tarifgrundpreis + Barpreis, C.1-Naeherung).
    """
    ref = modell.get("referenz")
    if not ref or ref.get("gesamt") is None:
        return None
    band = band_je_tarif.get(ref.get("tarif_id") or "")
    return {
        "gesamt": ref["gesamt"],
        "tarif": ref.get("tarif", ""),
        "naeherung": not bool(ref.get("aus_buendel")),
        "band": band,
        "band_label": _band_label(band),
        "quelle_url": ref.get("geraet_quelle_url", "") or ref.get("tarif_quelle_url", ""),
        "abgerufen_am": (ref.get("geraet_abgerufen_am", "")
                         or ref.get("tarif_abgerufen_am", "")),
        "tarif_quelle_url": ref.get("tarif_quelle_url", ""),
        "tarif_abgerufen_am": ref.get("tarif_abgerufen_am", ""),
    }


def _zeile_fuer_anbieter(anbieter: str, karte: Optional[dict],
                         basis: dict, band_je_tarif: dict) -> dict:
    """Eine Zeile des Wettbewerbers gegen die Vodafone-Basis dieses Geraets."""
    grund = "" if karte is None else (karte.get("leer_grund") or "")
    if karte is None or not karte.get("belastbar") or karte.get("gesamt") is None:
        return {"anbieter": anbieter, "status": STATUS_KEIN_BUENDEL,
                "prozent": None, "gesamt": None, "tarif": "", "band": None,
                "band_label": "", "grund": grund or
                f"Für dieses Modell ist bei {anbieter} kein Bündel erhoben.",
                **_beleg("", "")}
    if not karte.get("vergleichbar", True):
        return {"anbieter": anbieter, "status": STATUS_NICHT_VERGLEICHBAR,
                "prozent": None, "gesamt": karte["gesamt"], "tarif": karte.get("tarif", ""),
                "band": None, "band_label": "",
                "grund": (f"{anbieter} führt für dieses Gerät nur ein "
                          f"{karte.get('zustand_etikett') or 'nicht neues'} "
                          "Gerät – kein Vergleich gegen ein Neugerät."),
                **_beleg(karte.get("quelle_url", ""), karte.get("abgerufen_am", ""))}

    band = band_je_tarif.get(karte.get("tarif_id") or "")
    if basis["band"] is None or band is None or band != basis["band"]:
        vf_band = basis["band_label"]
        wb_band = _band_label(band)
        grund = (f"Vodafone vergleicht im Band {vf_band!r}, {anbieter} bietet "
                f"dieses Gerät im Band {wb_band!r} – nicht vergleichbar "
                "(Tarifband-Mismatch).")
        return {"anbieter": anbieter, "status": STATUS_BAND_MISMATCH,
                "prozent": None, "gesamt": karte["gesamt"],
                "tarif": karte.get("tarif", ""), "band": band,
                "band_label": wb_band, "grund": grund,
                **_beleg(karte.get("quelle_url", ""), karte.get("abgerufen_am", ""))}
    prozent = round((karte["gesamt"] - basis["gesamt"]) / basis["gesamt"] * 100, 1)
    return {"anbieter": anbieter, "status": STATUS_VERGLEICHBAR,
            "prozent": prozent, "gesamt": karte["gesamt"],
            "tarif": karte.get("tarif", ""), "band": band,
            "band_label": _band_label(band), "grund": "",
            **_beleg(karte.get("quelle_url", ""), karte.get("abgerufen_am", ""))}


def netzbetreiber_gruppen(modelle: list, band_je_tarif: dict) -> list[dict]:
    """Je Modell eine Zeilengruppe (Aufgabe 3): Vodafone-Basis + drei
    Wettbewerberzeilen, IMMER alle drei genannt (kein_buendel statt
    Weglassen), sortiert aufsteigend nach %-Abweichung."""
    gruppen = []
    for modell in modelle:
        karten_je_anbieter = {k["anbieter"]: k for k in modell.get("karten", [])
                              if k["anbieter"] != "Vodafone"}
        basis = _vodafone_basis(modell, band_je_tarif)
        if basis is None:
            zeilen = [{"anbieter": a, "status": STATUS_KEIN_BUENDEL,
                      "prozent": None,
                      "gesamt": (karten_je_anbieter.get(a) or {}).get("gesamt"),
                      "tarif": (karten_je_anbieter.get(a) or {}).get("tarif", ""),
                      "band": None, "band_label": "",
                      "grund": "", **_beleg("", "")}
                     for a in NETZ_WETTBEWERBER]
            gruppen.append({
                "id": modell["id"], "titel": modell["titel"],
                "hersteller": modell["hersteller"], "speicher": modell["speicher"],
                "vodafone": None,
                "vodafone_grund": ("Kein Vodafone-TCO-24 für dieses Gerät "
                                  "erhoben – kein Bündel und kein eigener "
                                  "Barpreis."),
                "zeilen": zeilen, "rang": float("inf"),
            })
            continue
        zeilen = [_zeile_fuer_anbieter(a, karten_je_anbieter.get(a), basis,
                                       band_je_tarif)
                 for a in NETZ_WETTBEWERBER]
        zeilen.sort(key=lambda z: z["prozent"] if z["prozent"] is not None
                    else float("inf"))
        rang = min((z["prozent"] for z in zeilen if z["prozent"] is not None),
                  default=float("inf"))
        gruppen.append({
            "id": modell["id"], "titel": modell["titel"],
            "hersteller": modell["hersteller"], "speicher": modell["speicher"],
            "vodafone": basis, "vodafone_grund": "",
            "zeilen": zeilen, "rang": rang,
        })
    gruppen.sort(key=lambda g: g["rang"])
    return gruppen


def haendler_zeilen(vergleich_ohne_vertrag: dict) -> list[dict]:
    """Der Händler-Abschnitt (Aufgabe: eigener, klar beschrifteter Bereich).

    Liest `geraete_vergleich.vergleich(..., preisart=OHNE_VERTRAG)["zeilen"]`
    - keine zweite Preisrechnung, nur ein Filter auf `anbieter_typ ==
    "handel"` und dieselbe %-Formel wie bei den Netzbetreibern, hier gegen
    Vodafones GERÄTEPREIS statt TCO-24.
    """
    zeilen = []
    for z in (vergleich_ohne_vertrag or {}).get("zeilen", []):
        vf = z.get("vodafone")
        if not vf or vf.get("preis") is None:
            continue
        for w in list(z.get("guenstiger") or []) + list(z.get("teurer") or []):
            if (w.get("typ") or "") != "handel":
                continue
            if w.get("preis") is None:
                continue
            prozent = round((w["preis"] - vf["preis"]) / vf["preis"] * 100, 1)
            zeilen.append({
                "modell": z.get("modell", ""), "hersteller": z.get("hersteller", ""),
                "speicher": z.get("speicher"),
                "vodafone_preis": vf["preis"], "vodafone_url": vf.get("url", ""),
                "vodafone_abgerufen_am": vf.get("abgerufen_am", ""),
                "anbieter": w.get("laden") or w.get("anbieter", ""),
                "preis": w["preis"], "url": w.get("url", ""),
                "abgerufen_am": w.get("abgerufen_am", ""),
                "prozent": prozent,
            })
    zeilen.sort(key=lambda r: r["prozent"])
    return zeilen


def nicht_erhebbar(quellenlage: dict) -> list[dict]:
    """Händler, die strukturell keine Daten liefern - NAMENTLICH, nie
    stillschweigend weggelassen (Aufgabe 4/Test c). Liest denselben Satz,
    den `geraete-quellen.html` schon zeigt (`methode`/`grund` aus
    config/geraete_quellen.yaml) - keine zweite Einschätzung."""
    out = []
    for z in (quellenlage or {}).get("zeilen", []):
        if (z.get("typ") or "") != "handel":
            continue
        if z.get("zustand") == "liefert":
            continue
        out.append({"anbieter": z.get("name", ""), "aktiv": bool(z.get("aktiv")),
                   "grund": z.get("grund") or "Keine Daten erhoben."})
    out.sort(key=lambda x: x["anbieter"])
    return out


def radar(tco: dict, vergleich_ohne_vertrag: dict, quellenlage: dict) -> dict:
    """Alles fuer wettbewerbsradar.html.

    `gruppen`/`haendler` bleiben die VOLLSTAENDIGEN Listen (Test c: nichts
    wird entfernt); `gruppen_sichtbar`/`gruppen_rest` und
    `haendler_sichtbar`/`haendler_rest` sind nur die Kappung der
    ANSICHT - dieselbe Bauform wie `geraete_alarme.zeilen()`
    (`sichtbar`/`rest`).
    """
    band_je_tarif = tco.get("band_je_tarif") or {}
    gruppen = netzbetreiber_gruppen(tco.get("modelle", []), band_je_tarif)
    haendler = haendler_zeilen(vergleich_ohne_vertrag)
    fehlt = nicht_erhebbar(quellenlage)
    hat_vergleichbare = any(z["prozent"] is not None
                            for g in gruppen for z in g["zeilen"])
    return {
        "gruppen": gruppen,
        "gruppen_sichtbar": gruppen[:SICHTBAR_MAX],
        "gruppen_rest": gruppen[SICHTBAR_MAX:],
        "haendler": haendler,
        "haendler_sichtbar": haendler[:HAENDLER_SICHTBAR_MAX],
        "haendler_rest": haendler[HAENDLER_SICHTBAR_MAX:],
        "nicht_erhebbar": fehlt,
        "hat_daten": bool(gruppen),
        "hat_vergleichbare_zeilen": hat_vergleichbare or bool(haendler),
        "anbieter_erwartet": list(NETZ_WETTBEWERBER),
    }


def leer() -> dict:
    return {"gruppen": [], "gruppen_sichtbar": [], "gruppen_rest": [],
            "haendler": [], "haendler_sichtbar": [], "haendler_rest": [],
            "nicht_erhebbar": [],
            "hat_daten": False, "hat_vergleichbare_zeilen": False,
            "anbieter_erwartet": list(NETZ_WETTBEWERBER)}
