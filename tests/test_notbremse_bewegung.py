"""Notbremse in der Bewegung: Mail, Kachel und Start nur aus Bündeln, die zählen.

Der Bewegungsblock der Mail meldet den Abstand eines Wettbewerbers zu Vodafone; am
Bestand vom 2026-10-06 standen 39 von 95 solchen Abständen auf Schätzungen (Fund des
Prüfers). Eine Messung, deren Bündel nicht zählt (Schätzung, abgelaufene Aktion),
wird nicht gemeldet, sondern als ``ohne_aussage["zaehlt_nicht"]`` gezählt. Ebenso
wählt das Kachel-Delta seinen führenden Anbieter nur unter Bündeln, die zählen, und
Startpaar und Kachelfolge zählen nur Anbieter, die zählen.

Synthetischer Bestand aus ``test_geraete_zeitreihe_ansicht.baue`` über den
öffentlichen Eingang ``geraete_view.aufbereiten``; fester Bezugstag. Orakel der
Kachel- und Startwahl ist derselbe Bestand ohne die Historie der gesperrten Bündel.
"""

from __future__ import annotations

import json

import pytest
from test_geraete_zeitreihe_ansicht import HEUTE, baue

from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import geraete_view

O2, CONGSTAR, VODAFONE, EINS_IPHONE, CONGSTAR_MITTEL, EINS_S26, TELEKOM_S26 = range(7)
"""Indizes in ``_BUENDEL`` des Testbestands."""
IPHONE, BAND = "apple-iphone-17-pro-256", "xs"
SCHAETZUNG = {"herleitung": "tarifsumme_minus_geraeterate"}
ABGELAUFEN = {
    "aktionen": [
        {
            "art": "anschluss_erlassen",
            "bedingung": "Online-Aktion",
            "quelle_url": "https://example.de/o2/aktion",
            "eingerechnet": True,
            "gueltig_bis": "2026-09-15",
        }
    ]
}


def _lies(datei) -> list[dict]:
    return [json.loads(z) for z in datei.read_text().splitlines() if z.strip()]


def _schreib(datei, zeilen: list[dict]) -> None:
    datei.write_text("".join(json.dumps(z) + "\n" for z in zeilen))


def _sperre(state, indizes, felder) -> list[str]:
    """Setzt ``felder`` an den Bündeln ``indizes``; gibt ihre IDs zurück."""
    datei = state / "geraete_tco.json"
    tco = json.loads(datei.read_text())
    for i in indizes:
        tco["buendel"][i].update(felder)
    datei.write_text(json.dumps(tco))
    return [tco["buendel"][i]["id"] for i in indizes]


def _historie_dazu(state, vorlagen: list[tuple[int, str, float]]) -> None:
    """Je (Bündel, Tag, Rate) eine Messung nach dem Muster der ersten Zeile des
    Bündels; ohne Zeile (Telekom) aus dem Bündel selbst."""
    historie = state / "geraete_tco_historie.jsonl"
    zeilen = _lies(historie)
    buendel = json.loads((state / "geraete_tco.json").read_text())["buendel"]
    for i, tag, rate in vorlagen:
        b = buendel[i]
        vorlage = next((z for z in zeilen if z["id"] == b["id"]), None) or {
            k: b[k]
            for k in (
                "id",
                "tarif_id",
                "tarif_monatlich",
                "geraet_zuzahlung",
                "laufzeit_monate",
                "anschlusspreis",
                "quelle_url",
                "zustand",
                "sku_id",
            )
        }
        zeilen.append(
            dict(
                vorlage,
                datum=tag,
                abgerufen_am=tag,
                geraet_monatsrate=rate,
                gesamt=round(1.0 + 24 * 20.0 + 24 * rate, 2),
            )
        )
    _schreib(historie, zeilen)


def _historie_ohne(state, ids: list[str]) -> None:
    historie = state / "geraete_tco_historie.jsonl"
    _schreib(
        historie, [z for z in _lies(historie) if not z["id"].startswith(tuple(ids))]
    )


def _zeitreihe(root, state) -> dict:
    g = geraete_view.aufbereiten(
        state, lade_quellen(root), lade_katalog(root), heute=HEUTE
    )
    return g["zeitreihe"]


def _mit_vergleichstag(tmp_path):
    """Der Bestand mit einem Vergleichstag am 08.09.: o2 war um 3 € Rate teurer
    (24 × 3 = 72 €), Vodafone und congstar unverändert."""
    root, state = baue(tmp_path)
    _historie_dazu(
        state,
        [
            (O2, "2026-09-08", 21.0),
            (VODAFONE, "2026-09-08", 25.75),
            (CONGSTAR, "2026-09-08", 22.0),
        ],
    )
    return root, state


def test_gegenprobe_gemessene_bewegung_wird_gemeldet(tmp_path):
    block = _zeitreihe(*_mit_vergleichstag(tmp_path))["bewegung_woche"]
    assert [(z["anbieter"], z["delta"]) for z in block["zeilen"]] == [("o2", -72.0)]
    assert "zaehlt_nicht" not in block["ohne_aussage"], block["ohne_aussage"]


@pytest.mark.parametrize(
    "felder", [SCHAETZUNG, ABGELAUFEN], ids=["schaetzung", "aktion"]
)
def test_mail_meldet_keinen_abstand_aus_buendeln_die_nicht_zaehlen(tmp_path, felder):
    root, state = _mit_vergleichstag(tmp_path)
    _sperre(state, [O2], felder)
    block = _zeitreihe(root, state)["bewegung_woche"]
    assert block["error"] is None, block
    assert block["zeilen"] == [], (
        f"Mail-Bewegungsblock meldet einen Abstand aus einem Bündel, das nicht zählt: "
        f"{[(z['anbieter'], z['delta']) for z in block['zeilen']]}"
    )
    assert block["ohne_aussage"].get("zaehlt_nicht") == 1, block["ohne_aussage"]
    assert block["geprueft"] == 1, "congstar (gemessen) bleibt geprüft"


def _kachel_delta(zeitreihe: dict) -> str | None:
    kachel = next(k for k in zeitreihe["kacheln"] if k["id"] == IPHONE)
    return kachel["baender"][BAND]["delta_text"]


def _mit_billigem_o2_am_letzten_tag(tmp_path, name: str):
    """o2 ist am 15.09. mit Rate 10 € das günstigste Bündel des Bandes."""
    root, state = baue(tmp_path / name)
    _historie_dazu(state, [(O2, "2026-09-15", 10.0)])
    return root, state


def test_kachel_delta_fuehrt_nur_ein_anbieter_der_zaehlt(tmp_path):
    gemessen = _kachel_delta(
        _zeitreihe(*_mit_billigem_o2_am_letzten_tag(tmp_path, "a"))
    )
    root, state = _mit_billigem_o2_am_letzten_tag(tmp_path, "b")
    _sperre(state, [O2], SCHAETZUNG)
    gesperrt = _kachel_delta(_zeitreihe(root, state))
    root, state = _mit_billigem_o2_am_letzten_tag(tmp_path, "c")
    _historie_ohne(state, _sperre(state, [O2], {}))
    ohne_o2 = _kachel_delta(_zeitreihe(root, state))
    assert gemessen != ohne_o2, f"Fall fehlt: o2 führt die Kachel nicht ({gemessen})"
    assert gesperrt == ohne_o2, (
        f"Kachel-Delta „{gesperrt}“ stammt aus der o2-Schätzung, erwartet „{ohne_o2}“"
    )


def _mit_telekom(tmp_path, name: str):
    """Galaxy S26 im Band XS mit zwei gemessenen Anbietern (1&1, Telekom)."""
    root, state = baue(tmp_path / name)
    _historie_dazu(
        state, [(TELEKOM_S26, "2026-09-12", 19.0), (TELEKOM_S26, "2026-09-13", 19.0)]
    )
    return root, state


def _wahl(zeitreihe: dict) -> tuple:
    return zeitreihe["start"], [k["id"] for k in zeitreihe["kacheln"]]


def test_startpaar_und_kachelfolge_zaehlen_nur_anbieter_die_zaehlen(tmp_path):
    gesperrte = [O2, CONGSTAR, EINS_IPHONE]
    gemessen = _wahl(_zeitreihe(*_mit_telekom(tmp_path, "a")))
    root, state = _mit_telekom(tmp_path, "b")
    _sperre(state, gesperrte, SCHAETZUNG)
    gesperrt = _wahl(_zeitreihe(root, state))
    root, state = _mit_telekom(tmp_path, "c")
    _historie_ohne(state, _sperre(state, gesperrte, {}))
    ohne = _wahl(_zeitreihe(root, state))
    assert gemessen[0] == {"modell": IPHONE, "band": BAND}, gemessen
    assert ohne != gemessen, (
        f"Fall fehlt: die Wahl hängt nicht an den Schätzungen ({ohne})"
    )
    assert gesperrt == ohne, (
        f"Startpaar/Kachelfolge {gesperrt} zählen Schätzungen mit, erwartet {ohne}"
    )
