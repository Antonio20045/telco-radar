#!/usr/bin/env python3
"""E1-Prototyp „EINE Geräteseite": TCO-Zeitreihe aus dem Bestand.

Hängt an zahlen.json UND an die inline-Daten (#gr-zahlen) der
entwurf-v2.html das Feld `historie`: je (Modell, Band, Anbieter) eine
Serie [datum, tco24] aus der eingefrorenen Leitzahl `gesamt` der
data/state/geraete_tco_historie.jsonl.

Zuordnung (keine zweite Meinung, alles Live-Code):
  buendel_id -> geraete_tco.json  (sku_id, anbieter, tarif_id)
  sku_id     -> Modell            (geraete_view.aufbereiten - dieselbe
                                   Gruppierung wie die eingebetteten Karten)
  tarif_id   -> Band              (geraete_tco_band.tarif_baender über
                                   Tarifbestand - dieselbe Logik wie der
                                   Live-Band-Graph)

Je (Modell, Band, Anbieter, Datum) zählt das GÜNSTIGSTE Bündel: Farben
sind Preisdimensionen, und zahlen_sammeln.py wählt am Stichtag dieselbe
erste Zeile nach Gesamt-Sortierung. Fehlt ein Messtag für einen Anbieter,
fehlt der Punkt - nichts wird interpoliert.

Reine Lesearbeit auf data/state; zahlen.json selbst wird nicht neu
gerechnet, nur um `historie` ERWEITERT (die Bestandszahlen bleiben
unverändert der Stand von zahlen_sammeln.py).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from telco_radar.geraete_config import lade_katalog, lade_quellen  # noqa: E402
from telco_radar.report import geraete_view  # noqa: E402
from telco_radar.report import geraete_tco_band  # noqa: E402
from telco_radar.tarif_bezug import Tarifbestand  # noqa: E402

HEUTE = "2026-09-15"   # derselbe Stichtag wie zahlen_sammeln.py
BAENDER = ("klein", "mittel", "gross")
ANBIETER = ("Telekom", "Vodafone", "o2", "1&1", "congstar")


def main() -> None:
    ordner = Path(__file__).resolve().parent

    # sku_id -> modell_id: dieselbe Gruppierung wie die Karten des Entwurfs
    g = geraete_view.aufbereiten(ROOT / "data/state", lade_quellen(ROOT),
                                 lade_katalog(ROOT), heute=HEUTE)
    sku_modell: dict[str, str] = {}
    for m in g["tco"]["modelle"]:
        for k in m["karten"]:
            if k.get("sku_id"):
                sku_modell[k["sku_id"]] = m["id"]

    # tarif_id -> Band (Live-Logik, inkl. unbegrenzt/fehlend = kein Band)
    tarife = Tarifbestand.aus_datei(ROOT / "data/state/tarife.jsonl").je_id
    band_je_tarif = geraete_tco_band.tarif_baender(tarife)

    # buendel_id -> (sku_id, anbieter, tarif_id)
    tco = json.loads((ROOT / "data/state/geraete_tco.json").read_text())
    buendel = {b["id"]: b for b in tco.get("buendel", [])}

    # Historie falten: je (modell, band, anbieter, datum) das Minimum
    serien: dict[str, dict[str, dict[str, dict[str, float]]]] = {}
    messtage: set[str] = set()
    ohne_modell = ohne_band = 0
    for zeile in (ROOT / "data/state/geraete_tco_historie.jsonl").read_text(
            encoding="utf-8").splitlines():
        if not zeile.strip():
            continue
        z = json.loads(zeile)
        b = buendel.get(z.get("id"))
        if not b:
            continue
        mid = sku_modell.get(b.get("sku_id"))
        if not mid:
            ohne_modell += 1
            continue
        band = band_je_tarif.get(z.get("tarif_id") or b.get("tarif_id"))
        if not band:
            ohne_band += 1
            continue
        datum, gesamt = z.get("datum"), z.get("gesamt")
        if not datum or gesamt is None:
            continue
        messtage.add(datum)
        slot = (serien.setdefault(mid, {})
                   .setdefault(band, {})
                   .setdefault(b.get("anbieter"), {}))
        alt = slot.get(datum)
        if alt is None or gesamt < alt:
            slot[datum] = float(gesamt)

    tage = sorted(messtage)
    historie = {
        "messtage": tage,
        "serien": {
            mid: {band: {an: [[d, w[d]] for d in sorted(w)]
                         for an, w in anbieter_.items()}
                  for band, anbieter_ in bands.items()}
            for mid, bands in serien.items()
        },
    }

    # ---- zahlen.json erweitern (Bestandszahlen unangetastet) ----------
    zahlen_pfad = ordner / "zahlen.json"
    daten = json.loads(zahlen_pfad.read_text(encoding="utf-8"))
    daten["historie"] = historie
    zahlen_pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=1),
                           encoding="utf-8")

    # ---- inline-Daten der entwurf-v2.html ersetzen ---------------------
    html_pfad = ordner / "entwurf-v2.html"
    html = html_pfad.read_text(encoding="utf-8")
    inline = json.dumps(daten, ensure_ascii=False, separators=(",", ":"))
    neu, n = re.subn(
        r'(<script type="application/json" id="gr-zahlen">).*?(</script>)',
        lambda m: m.group(1) + inline + m.group(2), html, count=1, flags=re.S)
    if n != 1:
        sys.exit("FEHLER: gr-zahlen-Block nicht gefunden")
    html_pfad.write_text(neu, encoding="utf-8")

    # ---- Statistik -----------------------------------------------------
    print("Messtage GESAMT:", len(tage), tage[0], "bis", tage[-1])
    je_modell = {mid: len({d for bands in h.values()
                          for w in bands.values() for d in w})
                 for mid, h in serien.items()}
    print("Modelle mit Historie:", len(serien),
          "| Punkte gesamt:", sum(je_modell.values()))
    print("uebersprungen: ohne Modell-Zuordnung:", ohne_modell,
          "| ohne Band:", ohne_band)
    beste = sorted(
        ((len(bands_k.get(b, {})), sum(len(w) for w in bands_k.get(b, {}).values()), mid, b)
         for mid, bands_k in serien.items() for b in bands_k),
        key=lambda t: (-t[0], -t[1]))
    print("Top (Modell x Band) nach Anbietern, dann Punkten:")
    for an_z, pk, mid, b in beste[:8]:
        titel = daten["modelle"][mid]["titel"]
        print(f"  {an_z} Anbieter, {pk} Punkte: {mid} · {b} ({titel})")


if __name__ == "__main__":
    main()
