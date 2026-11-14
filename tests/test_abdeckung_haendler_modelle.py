"""Wächter: für die Zeilen einer vorbereiteten Händlerquelle (Saturn/MediaMarkt
Tarifwelt) gelten nur die Pflichtmodelle, die ihr Leser erfasst. Die
Netzbetreiber bleiben gegen ALLE Pflichtmodelle geprüft; die Liste kann dort
nichts lockern.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from telco_radar.analyze.buendel_abdeckung import lade_pflicht, pruefe
from telco_radar.collect.geraete.tarifwelt_lauf import MODELL_SLUGS

WURZEL = Path(__file__).resolve().parent.parent
TAG = "2026-11-10"
ZEILE = "Händler · Netz X"


def _config(tmp_path, modelle_block: str, aktiv: bool = True) -> Path:
    (tmp_path / "geraete_abdeckung.yaml").write_text(
        "pflicht_anbieter: [Telekom]\n"
        "pflicht_modelle: [m-a, m-b, m-c]\n"
        f"pflicht_anbieter_wenn_aktiv:\n  Quelle X:\n    - '{ZEILE}'\n" + modelle_block
    )
    (tmp_path / "geraete_quellen.yaml").write_text(
        f"anbieter:\n  - name: Quelle X\n    aktiv: {'true' if aktiv else 'false'}\n"
    )
    return tmp_path / "geraete_abdeckung.yaml"


def _bestand(*paare: tuple[str, str]) -> dict:
    return {
        "updated": TAG,
        "buendel": [
            {
                "anbieter": a,
                "sku_id": f"{m}-256gb-schwarz",
                "tarif_name": "T",
                "laufzeit_monate": 24,
                "last_verified": TAG,
                "zustand": "neu",
            }
            for a, m in paare
        ],
    }


def test_eigene_modellliste_gilt_nur_fuer_die_haendlerzeile(tmp_path):
    pfad = _config(
        tmp_path, "pflicht_modelle_wenn_aktiv:\n  Quelle X:\n    - m-a\n    - m-b\n"
    )
    pflicht = lade_pflicht(pfad)
    assert pflicht["modelle_je_anbieter"] == {ZEILE: ["m-a", "m-b"]}
    tco = _bestand(
        ("Telekom", "m-a"),
        ("Telekom", "m-b"),
        ("Telekom", "m-c"),
        (ZEILE, "m-a"),
        (ZEILE, "m-b"),
    )
    assert pruefe(tco, [], pflicht).befunde == []
    ohne_telekom_c = _bestand(
        ("Telekom", "m-a"), ("Telekom", "m-b"), (ZEILE, "m-a"), (ZEILE, "m-b")
    )
    befunde = pruefe(ohne_telekom_c, [], pflicht).befunde
    assert [(b.art, b.anbieter) for b in befunde] == [("modell_fehlt", "Telekom")]
    ohne_haendler_b = _bestand(
        ("Telekom", "m-a"), ("Telekom", "m-b"), ("Telekom", "m-c"), (ZEILE, "m-a")
    )
    befunde = pruefe(ohne_haendler_b, [], pflicht).befunde
    assert [(b.art, b.anbieter) for b in befunde] == [("modell_fehlt", ZEILE)]
    assert "m-b" in befunde[0].text and "m-c" not in befunde[0].text


def test_ohne_eigene_liste_und_bei_inaktiver_quelle_gelten_alle_pflichtmodelle(
    tmp_path,
):
    pfad = _config(tmp_path, "")
    assert lade_pflicht(pfad)["modelle_je_anbieter"] == {}
    pfad = _config(
        tmp_path, "pflicht_modelle_wenn_aktiv:\n  Quelle X:\n    - m-a\n", aktiv=False
    )
    pflicht = lade_pflicht(pfad)
    assert pflicht["modelle_je_anbieter"] == {}
    assert pflicht["anbieter"] == ["Telekom"]


def test_liste_fuer_die_netzbetreiber_ist_ein_konfigurationsfehler(tmp_path):
    pfad = _config(tmp_path, "pflicht_modelle_wenn_aktiv:\n  Telekom:\n    - m-a\n")
    with pytest.raises(ValueError, match="nur vorbereitete Quellen"):
        lade_pflicht(pfad)


def test_modell_ausserhalb_der_pflichtmodelle_oder_leere_liste_wird_abgelehnt(tmp_path):
    pfad = _config(tmp_path, "pflicht_modelle_wenn_aktiv:\n  Quelle X:\n    - m-z\n")
    with pytest.raises(ValueError, match="m-z"):
        lade_pflicht(pfad)
    pfad = _config(tmp_path, "pflicht_modelle_wenn_aktiv:\n  Quelle X: []\n")
    with pytest.raises(ValueError, match="leer"):
        lade_pflicht(pfad)


def _echt() -> tuple[dict, dict]:
    daten = yaml.safe_load(
        (WURZEL / "config/geraete_abdeckung.yaml").read_text("utf-8")
    )
    return daten, daten["pflicht_modelle_wenn_aktiv"]


def test_echte_config_haendlermodelle_sind_teilmenge_der_erfassten_modelle():
    """Seit Baupaket P6 (13.11.2026) erfasst `MODELL_SLUGS` mehr Modelle, als
    der Wächter für Saturn/MediaMarkt policiert: die CI-Pflichtliste bleibt
    eine TEILMENGE des Lesers (nicht mehr Gleichheit), damit zusätzliche,
    nicht überwachte Modelle nicht automatisch zu einem CI-Gate für ALLE
    Netzbetreiber werden (die über `pflicht_modelle` geprüft werden). Die
    letzten zwei Zeilen prüfen, dass diese zusätzliche, nicht überwachte
    Abdeckung wirklich existiert und bewusst außerhalb der CI-Pflichtliste
    bleibt (siehe Moduldoku `tarifwelt_lauf.py`)."""
    daten, je_quelle = _echt()
    modelle = je_quelle["MediaMarkt/Saturn Tarifwelt"]
    assert set(modelle) <= set(MODELL_SLUGS), (
        "Wächter fordert ein Modell, das der Leser nicht erfasst"
    )
    assert set(modelle) <= set(daten["pflicht_modelle"])
    assert len(modelle) == len(set(modelle))
    assert set(je_quelle) <= set(daten["pflicht_anbieter_wenn_aktiv"])
    assert not set(je_quelle) & set(daten["pflicht_anbieter"])
    zusaetzlich = set(MODELL_SLUGS) - set(modelle)
    assert len(zusaetzlich) >= 20
    assert not zusaetzlich & set(daten["pflicht_modelle"])


def test_echte_config_prueft_drei_netzzeilen_mit_zwei_belegten_luecken(tmp_path):
    for name in ("geraete_abdeckung.yaml", "geraete_quellen.yaml"):
        (tmp_path / name).write_text((WURZEL / "config" / name).read_text("utf-8"))
    pflicht = lade_pflicht(tmp_path / "geraete_abdeckung.yaml")
    zeilen = pflicht["modelle_je_anbieter"]
    assert sorted(zeilen) == sorted(
        z for z in pflicht["anbieter"] if z.startswith("Saturn/MediaMarkt")
    )
    assert len(zeilen) == 3
    assert all(len(m) == 18 for m in zeilen.values())
    assert ("Saturn/MediaMarkt · Telekom-Netz", "apple-iphone-duo") in pflicht["belege"]
    assert (
        "Saturn/MediaMarkt · o2-Netz",
        "samsung-galaxy-z-fold8",
    ) in pflicht["belege"]
    assert "Telekom" not in zeilen and len(pflicht["modelle"]) == 18
    quellen = (tmp_path / "geraete_quellen.yaml").read_text("utf-8")
    kopf, rest = quellen.split("name: MediaMarkt/Saturn Tarifwelt", 1)
    rest = rest.replace("aktiv: true", "aktiv: false", 1)
    (tmp_path / "geraete_quellen.yaml").write_text(
        kopf + "name: MediaMarkt/Saturn Tarifwelt" + rest
    )
    aus = lade_pflicht(tmp_path / "geraete_abdeckung.yaml")
    assert aus["modelle_je_anbieter"] == {}
    assert not any(a.startswith("Saturn/MediaMarkt") for a in aus["anbieter"])
