#!/usr/bin/env python3
"""E1-Prototyp „EINE Geräteseite": alle Zahlen des Entwurfs aus dem Bestand.

Schreibt zahlen.json NEBEN diese Datei. Reine Lesearbeit auf data/state,
kein Schreibzugriff auf State, kein Netz, kein Modell — derselbe Aufruf wie
report/html.py (geraete_view.aufbereiten + wettbewerbsradar.radar).

Alle Zahlen des Entwurfs stammen aus dieser Datei; nichts wird im HTML
geschätzt oder geglättet. Heute=2026-09-15 (letzter vollständiger
Tageslauf zum Bauzeitpunkt).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from telco_radar.geraete_config import lade_katalog, lade_quellen  # noqa: E402
from telco_radar.report import geraete_view, wettbewerbsradar  # noqa: E402

HEUTE = "2026-09-15"
BAENDER = ("klein", "mittel", "gross")
# Dieselben fünf, die der Bestand erwartet (ANBIETER_REIHENFOLGE + congstar,
# geraete_tco_band.ERWARTETE_ANBIETER). Anzeigereihenfolge des Entwurfs:
# Netzbetreiber zuerst, Zweitmarke daneben, Discounter ans Ende.
ANBIETER = ("Telekom", "Vodafone", "o2", "1&1", "congstar")


def euro(betrag: float | int | None) -> str:
    if betrag is None:
        return ""
    return f"{betrag:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".") + " €"


def monat(betrag: float | int | None) -> str:
    if betrag is None:
        return ""
    return f"{betrag:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".") + " €/M."


def zeile_aus_karte(k: dict) -> dict:
    einmalig = (k.get("zuzahlung") or 0.0) + (k.get("anschlusspreis") or 0.0)
    # Zwei-Zahlen-Muster: 1&1 nennt EINEN Monatsbetrag für Tarif und Gerät
    # zusammen (§ 13.2) - der steht in buendel_monatlich, monatlich ist None.
    bnd = k.get("monatlich") is None and k.get("buendel_monatlich") is not None
    mon = k.get("monatlich") if not bnd else k.get("buendel_monatlich")
    return {
        "anbieter": k.get("anbieter"),
        "tarif": k.get("tarif") or "",
        "gb": k.get("band_gb_text") or "",
        "tco24": k.get("gesamt"),
        "tco24_text": euro(k.get("gesamt")),
        "schnitt": k.get("schnitt_monat"),
        "schnitt_text": monat(k.get("schnitt_monat")),
        "monatlich": mon,
        "bnd_preis": bnd,
        "einmalig": round(einmalig, 2) if einmalig else 0.0,
        "delta_euro": (k.get("delta") or {}).get("betrag"),
        "delta_text": k.get("delta_kurz") or "",
        "referenz": bool(k.get("eigen")) or bool(k.get("naeherung")),
        "naeherung": bool(k.get("naeherung")),
        "url": k.get("quelle_url") or (k.get("eff_basis") or {}).get("quelle_url") or "",
        "messtermin": k.get("abgerufen_am") or "",
        "zustand": k.get("zustand_etikett") or "",
        "bestandteile": [{"name": b.get("name"), "betrag": b.get("betrag")}
                         for b in (k.get("bestandteile") or [])],
        "gezahlt_nach_24": k.get("gezahlt_nach_24"),
        "offen_nach_24": k.get("offen_nach_24"),
        "offene_raten": k.get("offene_raten"),
        "bindung": k.get("tarif_bindung"),
        "raten_laufzeit": k.get("raten_laufzeit"),
    }


def main() -> None:
    g = geraete_view.aufbereiten(ROOT / "data/state", lade_quellen(ROOT),
                                 lade_katalog(ROOT), heute=HEUTE)
    tco = g["tco"]
    radar = wettbewerbsradar.radar(
        tco, g["vergleich"]["ohne_vertrag"], g["quellenlage"],
        alarme=g["alarme"], portfolio=None)

    # ---- Kernzahlen -------------------------------------------------
    modelle = tco["modelle"]
    baender_je_modell: dict[str, dict[str, list]] = {}
    for m in modelle:
        baender_je_modell[m["id"]] = {}
        for k in m["karten"]:
            band = k.get("band")
            if not band:
                continue
            baender_je_modell[m["id"]].setdefault(band, []).append(k)

    baender_zahl = {b: sum(1 for m in modelle if b in baender_je_modell[m["id"]])
                    for b in BAENDER}
    zellen_paare = sum(baender_zahl.values())            # (Modell,Band) mit >=1 Bündel
    zellen_gesamt = zellen_paare * len(ANBIETER)

    besetzt = kein_buendel = band_luecke = nur_erneuert = 0
    for m in modelle:
        hat_anbieter: dict[str, set] = {}
        for band, karten in baender_je_modell[m["id"]].items():
            for k in karten:
                hat_anbieter.setdefault(k["anbieter"], set()).add(band)
        for band in baender_je_modell[m["id"]]:
            for an in ANBIETER:
                karten = [k for k in baender_je_modell[m["id"]][band]
                          if k["anbieter"] == an]
                vergleichbar = [k for k in karten if k.get("vergleichbar")]
                if vergleichbar:
                    besetzt += 1
                elif karten:
                    nur_erneuert += 1
                elif an in hat_anbieter:
                    band_luecke += 1
                else:
                    kein_buendel += 1

    # Nur KARTEN MIT BÜNDEL (sku_id): die Leerkarten der vier Festanbieter
    # und die Vodafone-Näherung tragen absichtlich keine (geraete_tco_view).
    anbieter_modelle = {an: sum(
        1 for m in modelle
        if any(k["anbieter"] == an and k.get("sku_id") for k in m["karten"]))
        for an in ANBIETER}

    # ---- Modelle für den Prototyp ------------------------------------
    out_modelle = {}
    for m in modelle:
        mid = m["id"]
        baender_out = {}
        for band, karten in baender_je_modell[mid].items():
            zeilen, gesehen = [], set()
            for k in sorted(
                    (k for k in karten
                     if k.get("vergleichbar") and k.get("belastbar")
                     and k.get("gesamt") is not None),
                    key=lambda k: k["gesamt"]):
                if k["anbieter"] in gesehen:
                    continue
                gesehen.add(k["anbieter"])
                zeilen.append(zeile_aus_karte(k))
            # Vodafone-Näherung ergänzen, wenn kein eigenes Bündel im Band
            naeherung = next((k for k in karten if k.get("naeherung")), None)
            if naeherung and "Vodafone" not in gesehen \
                    and naeherung.get("band") == band \
                    and naeherung.get("gesamt") is not None:
                z = zeile_aus_karte(naeherung)
                z["naeherung"] = True
                z["referenz"] = True
                zeilen.append(z)
                gesehen.add("Vodafone")
            luecken = []
            andere = {b for b in baender_je_modell[mid]}
            for an in ANBIETER:
                if an in gesehen:
                    continue
                hat_karten = [k for k in m["karten"] if k["anbieter"] == an]
                if not hat_karten:
                    grund = "kein Bündel erhoben"
                elif any(k.get("band") == band for k in hat_karten):
                    # nur ungleiche/erneuerte Karten in diesem Band
                    grund = "nur erneuerte Geräte" if all(
                        not k.get("vergleichbar") for k in hat_karten
                        if k.get("band") == band) else "kein belastbares Bündel"
                else:
                    grund = "kein Bündel in diesem Band"
                alternativ = []
                for b2 in BAENDER:
                    beste = sorted(
                        (k for k in hat_karten
                         if k.get("band") == b2 and k.get("vergleichbar")
                         and k.get("gesamt") is not None),
                        key=lambda k: k["gesamt"])
                    if beste:
                        alternativ.append({"band": b2,
                                           "tco_text": euro(beste[0]["gesamt"])})
                luecken.append({"anbieter": an, "grund": grund,
                                "alternativ": alternativ})
            # Preis-Sortierung wie der Bestand (_zeilen_rang): TCO-24
            # aufsteigend - die Referenz bekommt ihr Gewicht durch die
            # Hervorhebung, nicht durch die Position.
            zeilen.sort(key=lambda z: z["tco24"] if z["tco24"] is not None
                        else 9e9)
            # DAS DELTA DES BANDES, nicht das der Modell-Karte: die Karte
            # verschweigt Abstände unter der Wesentlichkeitsschwelle
            # (3 %/15 EUR, bewusste Hausregel), der Band-Graph des
            # Bestands nennt sie. Der Entwurf zeigt dieselbe Zeichenkette
            # wie der Live-Graph - gelesen aus m["baender"], nichts neu
            # gerechnet.
            band_block = next((bb for bb in (m.get("baender") or [])
                               if bb.get("key") == band), None) or {}
            balken = {b["anbieter"]: b for b in
                      (band_block.get("balken") or {}).get("zeilen", [])}
            for z in zeilen:
                b = balken.get(z["anbieter"])
                if b and b.get("delta_text"):
                    z["delta_euro"] = b.get("delta_euro")
                    z["delta_text"] = b["delta_text"]
                elif b and b.get("referenz"):
                    z["delta_text"] = ""
            baender_out[band] = {"zeilen": zeilen, "luecken": luecken}

        ohne_band = sum(1 for k in m["karten"]
                        if not k.get("band") and k.get("sku_id"))
        antwort = m.get("antwort") or {}
        # PM-7: deterministische Vorschau-Sortierung. Aktuelle Modelle
        # (größere Bandabdeckung, mehr Anbieter mit Bündel) zuerst,
        # Auslaufware ans Ende - beide Werte aus dem Bestand, nichts
        # geraten. Der JS-Teil filtert nur, er sortiert nicht.
        echts = [k for k in m["karten"] if k.get("sku_id")]
        anbieter_mit = {k["anbieter"] for k in echts}
        out_modelle[mid] = {
            "titel": m.get("titel") or mid,
            "hersteller": m.get("hersteller") or "",
            "speicher": m.get("speicher"),
            "baender": baender_out,
            "ohne_band": ohne_band,
            "anbieter_zahl": len(anbieter_mit),
            "band_zahl": len(baender_out),
            "barpreis": {
                "betrag": antwort.get("geraetepreis"),
                "text": euro(antwort.get("geraetepreis")),
                "anbieter": antwort.get("geraetepreis_anbieter") or "",
            },
        }

    # Suchindex: vorsortiert nach Vorschau-Rang (Bandabdeckung vor
    # Anbieterzahl vor Alphabet) - die Reihenfolge, in der die ≤ 8
    # Treffer der Live-Vorschau erscheinen.
    suchindex = sorted(
        out_modelle.items(),
        key=lambda kv: (-kv[1]["band_zahl"], -kv[1]["anbieter_zahl"],
                        kv[1]["titel"]))
    suchindex = [{
        "id": mid, "titel": v["titel"], "hersteller": v["hersteller"],
        "speicher": v["speicher"], "anbieter_zahl": v["anbieter_zahl"],
        "band_zahl": v["band_zahl"],
    } for mid, v in suchindex]

    # ---- Alarme ------------------------------------------------------
    alarme = g["alarme"]
    alarm_zeilen = [{
        "modell": f"{z['modell']}" + (f" · {z['speicher']} GB" if z.get("speicher") else ""),
        "stufe": z["stufe_name"],
        "unser": z["unser"]["preis"],
        "unser_text": euro(z["unser"]["preis"]),
        "bester": z["bester"]["anbieter"],
        "bester_preis_text": euro(z["bester"]["preis"]),
        "euro_text": euro(z["euro"]),
        "prozent": z["prozent"],
        "url": z["bester"].get("url") or "",
    } for z in (alarme["sichtbar"] + alarme["rest"])[:8]]

    # ---- Abweichungstabelle: 88 Gruppen flach, Δ% aufsteigend --------
    paare = []
    for gruppe in radar["gruppen"]:
        for z in gruppe["zeilen"]:
            if z.get("prozent") is None:
                continue
            paare.append({
                "modell": gruppe["titel"],
                "band": z.get("band_label") or "ohne",
                "anbieter": z["anbieter"],
                "tco_text": euro(z.get("gesamt")),
                "vf_text": euro(z.get("vf_gesamt")),
                "prozent": z["prozent"],
                "url": z.get("quelle_url") or "",
                "tarif": z.get("tarif") or "",
            })
    paare.sort(key=lambda p: p["prozent"])

    daten = {
        "stand": HEUTE,
        "abgerufen_bis": g.get("abgerufen_bis") or HEUTE,
        "kopf": {
            "modelle": len(modelle),
            "baender": baender_zahl,
            "zellen": {"paare": zellen_paare, "gesamt": zellen_gesamt,
                       "besetzt": besetzt},
            "leer": {"kein_buendel": kein_buendel,
                     "band_luecke": band_luecke,
                     "nur_erneuert": nur_erneuert},
            "anbieter_modelle": anbieter_modelle,
        },
        "anbieter": list(ANBIETER),
        "suchindex": suchindex,
        "baender_meta": {
            "klein": {"label": "Klein", "bereich": "bis 20 GB"},
            "mittel": {"label": "Mittel", "bereich": "21 bis 60 GB"},
            "gross": {"label": "Groß", "bereich": "über 60 GB"},
        },
        "modelle": out_modelle,
        "alarme": {
            "kacheln": alarme["kacheln"],
            "gesamt": alarme["gesamt"],
            "zeilen8": alarm_zeilen,
        },
        "abweichung": {"paare_gesamt": len(paare), "zeilen12": paare[:12]},
        "haendler_ohne_buendel": list(
            (__import__("telco_radar.report.geraete_tco_karten",
                        fromlist=["HAENDLER_OHNE_BUENDEL"])
             ).HAENDLER_OHNE_BUENDEL),
    }

    ziel = Path(__file__).resolve().parent / "zahlen.json"
    ziel.write_text(json.dumps(daten, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    print(f"geschrieben: {ziel} ({ziel.stat().st_size/1024:.0f} KB)")
    print("kopf:", json.dumps(daten["kopf"], ensure_ascii=False))


if __name__ == "__main__":
    main()
