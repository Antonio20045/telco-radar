"""Kennzahl für Baupaket P6 (analyse-abdeckung-1313.md, Abschnitt 5):
"Saturn/MediaMarkt-Zeilen ohne Datensatz UND ohne Beleg", vorher/nachher.

    python scripts/saturn_abdeckung_bericht.py
    python scripts/saturn_abdeckung_bericht.py --vorher-ref origin/main

Basis der 133 Modell-Speicher-Einheiten (89 Modelle): die Export-Zeilen mit
Zustand "neu" in `site/exporte/geraete-tco-24.csv` - dieselbe Zahl wie in der
Analyse (133 Einheiten, 89 Modelle, 8 Anbieterzeilen geprüft). Eine Zelle gilt
als

* "mit Datensatz", wenn mindestens eine Export-Zeile für (Modell, Speicher,
  Anbieter) existiert (unabhängig davon, ob sie einen Preis trägt - das ist
  Klasse (a)/(b)/(c)/(d)/(e) der Analyse, hier zählt nur "Schweigen oder
  nicht"),
* "mit Beleg", wenn `config/geraete_abdeckung.yaml` (`belegte_luecken`) für
  die Anbieterzeile und das Modell (als `device_id`) einen Eintrag trägt -
  entweder für das ganze Modell (`modelle: [...]`) oder für den ganzen
  Anbieter (kein `modelle`-Feld).

"Vorher" liest `config/geraete_abdeckung.yaml` aus einer anderen Git-Referenz
(Default: `origin/main`, siehe `--vorher-ref`), "nachher" den Arbeitsstand.
Die Export-CSV bleibt für beide Seiten dieselbe (der Tageslauf wurde für
dieses Paket nicht neu ausgeführt) - das Skript vergleicht also
ausschließlich, wie viele der heute schon stillen Zellen jetzt einen GRUND
tragen, nicht, ob bereits ein neuer Preis gemessen wurde.

Zwei Modelle stehen nicht im handgepflegten Katalog
(`config/geraete_katalog.yaml`), sondern nur in den Auto-Zusätzen des
Bestands (`data/state/geraete_katalog_auto.json`); den Bestand liest dieses
Skript bewusst nicht (Hermetik-Regel der Testsuite, siehe
`tests/conftest.py`) - ihr Hersteller steht deshalb von Hand in
`_AUTO_HERSTELLER`.

`yaml` und `telco_radar.geraete_model.device_id` werden erst innerhalb der
Funktionen importiert, nicht am Modulanfang: der `src`-Pfad wird erst zur
Laufzeit (nach dem Einhängen von `sys.path`) bekannt, ein Modulkopf-Import
davor würde fehlschlagen und einer danach wäre ein verbotenes `noqa: E402`.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
EXPORT = WURZEL / "site" / "exporte" / "geraete-tco-24.csv"

SATURN_ZEILEN = (
    "Saturn/MediaMarkt · Vodafone-Netz",
    "Saturn/MediaMarkt · Telekom-Netz",
    "Saturn/MediaMarkt · o2-Netz",
)

_AUTO_HERSTELLER = {
    "AirPods 5": "Apple",
    "Galaxy S26 Enterprise Edition": "Samsung",
}


def _katalog_hersteller() -> dict[str, str]:
    """Modellname (wie im Export) -> Hersteller, aus dem Katalog."""
    import yaml

    aus: dict[str, str] = dict(_AUTO_HERSTELLER)
    katalog = yaml.safe_load(
        (WURZEL / "config" / "geraete_katalog.yaml").read_text("utf-8")
    )
    for g in katalog.get("geraete") or []:
        aus.setdefault(g["modell"], g["hersteller"])
    return aus


def _export_zeilen(export_pfad: Path) -> list[dict]:
    with open(export_pfad, encoding="utf-8") as fh:
        zeilen = list(csv.DictReader(fh, delimiter=";"))
    return [z for z in zeilen if z.get("Zustand") == "neu"]


def _einheiten(export_pfad: Path) -> list[tuple[str, str]]:
    """[(Modell, Speicher GB)] der Einheiten (Zustand "neu"; 133 im echten
    Export vom 13.11.2026)."""
    return sorted(
        set((z["Modell"], z["Speicher GB"]) for z in _export_zeilen(export_pfad))
    )


def _mit_datensatz(export_pfad: Path) -> set[tuple[str, str, str]]:
    """{(Modell, Speicher, Anbieter)} mit mindestens einer Export-Zeile."""
    return {
        (z["Modell"], z["Speicher GB"], z["Anbieter"])
        for z in _export_zeilen(export_pfad)
    }


def _belegte_modelle(abdeckung_yaml: str) -> dict[str, set[str]]:
    """Anbieterzeile -> {device_id} (aus `belegte_luecken`; ohne `modelle`
    gilt der Eintrag für ALLE Modelle dieser Zeile, als `"*"` markiert)."""
    import yaml

    daten = yaml.safe_load(abdeckung_yaml) or {}
    aus: dict[str, set[str]] = {z: set() for z in SATURN_ZEILEN}
    for eintrag in daten.get("belegte_luecken") or []:
        anbieter = eintrag.get("anbieter")
        if anbieter not in aus:
            continue
        modelle = eintrag.get("modelle")
        if not modelle:
            aus[anbieter].add("*")
        else:
            aus[anbieter] |= set(modelle)
    return aus


def _ohne_datensatz_und_ohne_beleg(
    abdeckung_yaml: str,
    hersteller_je_modell: dict[str, str],
    export_pfad: Path = EXPORT,
) -> dict[str, int]:
    from telco_radar.geraete_model import device_id

    einheiten = _einheiten(export_pfad)
    datensatz = _mit_datensatz(export_pfad)
    belege = _belegte_modelle(abdeckung_yaml)
    aus: dict[str, int] = {}
    for zeile in SATURN_ZEILEN:
        n = 0
        for modell, speicher in einheiten:
            if (modell, speicher, zeile) in datensatz:
                continue
            hersteller = hersteller_je_modell.get(modell, "")
            did = device_id(hersteller, modell)
            if "*" in belege[zeile] or did in belege[zeile]:
                continue
            n += 1
        aus[zeile] = n
    return aus


def _git_show(ref: str, pfad: str) -> str | None:
    try:
        return subprocess.run(
            ["git", "show", f"{ref}:{pfad}"],
            cwd=WURZEL,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except subprocess.CalledProcessError:
        return None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--vorher-ref",
        default="origin/main",
        help="Git-Referenz für den Stand VOR Baupaket P6 (Default: origin/main)",
    )
    args = p.parse_args(argv)

    hersteller_je_modell = _katalog_hersteller()
    nachher_yaml = (WURZEL / "config" / "geraete_abdeckung.yaml").read_text("utf-8")
    vorher_yaml = _git_show(args.vorher_ref, "config/geraete_abdeckung.yaml")
    if vorher_yaml is None:
        print(
            f"Konnte {args.vorher_ref}:config/geraete_abdeckung.yaml nicht lesen",
            file=sys.stderr,
        )
        return 2

    vorher = _ohne_datensatz_und_ohne_beleg(vorher_yaml, hersteller_je_modell)
    nachher = _ohne_datensatz_und_ohne_beleg(nachher_yaml, hersteller_je_modell)

    print("Saturn/MediaMarkt: Zellen ohne Datensatz UND ohne Beleg (von 133 Einheiten)")
    print(f"{'Zeile':<38}{'vorher':>8}{'nachher':>9}{'Δ':>6}")
    gesamt_vorher = gesamt_nachher = 0
    for zeile in SATURN_ZEILEN:
        v, n = vorher[zeile], nachher[zeile]
        gesamt_vorher += v
        gesamt_nachher += n
        print(f"{zeile:<38}{v:>8}{n:>9}{n - v:>6}")
    delta = gesamt_nachher - gesamt_vorher
    print(f"{'gesamt':<38}{gesamt_vorher:>8}{gesamt_nachher:>9}{delta:>6}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(WURZEL / "src"))
    raise SystemExit(main())
