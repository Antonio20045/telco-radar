"""M1 (Prüfung PR #45, arbeit/pruefung-pr45-einsundeins-0511.md): der jüngste
Zeitreihen-Punkt einer 1&1-Linie darf nie einen Wert zeigen, den der HEUTIGE
Gerätestand als „1&1-Wert widersprüchlich, neu messen“ führt.

Befund: Galaxy S26 256 GB, Tarif S, maß die Einmalzahlung nach Monat 24 am
12.09., 07.10. und 03.11. jeweils mit 220 € - damals war das noch der Wert
aller drei Tarife (S/M/L), also kein Widerspruch (Entscheidung 2: diese
älteren Punkte bleiben unverändert sichtbar). Am 05.11. weicht S (220 €) von
M/L (280 €) ab; die Tafel führt S seitdem als benannte Lücke, nicht als Zahl.
Die alte Tages-Regel von `_messungen` sah das nicht, weil sie nur INNERHALB
eines Tages prüft: der 05.11.-Punkt von S allein widerspricht sich nicht
selbst. Die Zeitreihen-Seite zeigte darum weiter 1.051,66 € (24 × 32,99 +
220 € + 39,90) als „zuletzt“, obwohl die aktuelle Tafel diesen Tarif schon als
widersprüchlich führt. Der Fix (`geraete_zeitreihe_auswahl.py`) vergleicht den
JÜNGSTEN Punkt jeder 1&1-Linie zusätzlich gegen den heutigen Gerätestand
(`geraete_tco.json`) und entfernt nur ihn, wenn er dort abweicht.
"""

from __future__ import annotations

import json

from telco_radar.report import geraete_zeitreihe

MODELL = "samsung-galaxy-s26-256"
SKU = "samsung-galaxy-s26-256gb-schwarz"
ANSCHLUSS = 39.9


def _buendel(bid, tarif_id, monatlich, zuzahlung, **extra):
    return {
        "id": bid,
        "sku_id": SKU,
        "anbieter": "1&1",
        "tarif_name": f"1&1 All-Net-Flat {tarif_id[-1].upper()}",
        "tarif_id": tarif_id,
        "tarif_id_guete": "hoch",
        "buendel_monatlich": monatlich,
        "geraet_zuzahlung": zuzahlung,
        "laufzeit_monate": 36,
        "anschlusspreis": ANSCHLUSS,
        "zustand": "neu",
        "quelle_url": f"https://beispiel.test/{tarif_id}",
        "abgerufen_am": "2026-11-05",
        **extra,
    }


def _zeile(bid, tarif_id, datum, monatlich, zuzahlung):
    return {
        "id": bid,
        "datum": datum,
        "tarif_id": tarif_id,
        "buendel_monatlich": monatlich,
        "geraet_zuzahlung": zuzahlung,
        "laufzeit_monate": 36,
        "anschlusspreis": ANSCHLUSS,
        "gesamt": round(24 * monatlich + zuzahlung + ANSCHLUSS, 2),
        "quelle_url": f"https://beispiel.test/{tarif_id}",
        "abgerufen_am": datum,
        "zustand": "neu",
    }


def _karte(sku, band):
    return {
        "anbieter": "1&1",
        "sku_id": sku,
        "band": band,
        "vergleichbar": True,
    }


def _state(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    heute = [
        _buendel("buendel--1-1--s26-256--s", "11-s", 32.99, 220.0),
        _buendel("buendel--1-1--s26-256--m", "11-m", 37.99, 280.0),
        _buendel("buendel--1-1--s26-256--l", "11-l", 42.99, 280.0),
    ]
    (state / "geraete_tco.json").write_text(
        json.dumps({"buendel": heute}), encoding="utf-8"
    )
    tage_frueh = ("2026-09-12", "2026-10-07", "2026-11-03")
    zeilen = []
    for datum in tage_frueh:
        zeilen.append(_zeile("buendel--1-1--s26-256--s", "11-s", datum, 32.99, 220.0))
        zeilen.append(_zeile("buendel--1-1--s26-256--m", "11-m", datum, 37.99, 220.0))
        zeilen.append(_zeile("buendel--1-1--s26-256--l", "11-l", datum, 42.99, 220.0))
    zeilen.append(
        _zeile("buendel--1-1--s26-256--s", "11-s", "2026-11-05", 32.99, 220.0)
    )
    zeilen.append(
        _zeile("buendel--1-1--s26-256--m", "11-m", "2026-11-05", 37.99, 280.0)
    )
    zeilen.append(
        _zeile("buendel--1-1--s26-256--l", "11-l", "2026-11-05", 42.99, 280.0)
    )
    (state / "geraete_tco_historie.jsonl").write_text(
        "\n".join(json.dumps(z) for z in zeilen) + "\n", encoding="utf-8"
    )
    tco = {
        "modelle": [
            {
                "id": MODELL,
                "titel": "Galaxy S26 256 GB",
                "hersteller": "Samsung",
                "speicher": 256,
                "karten": [_karte(SKU, "s"), _karte(SKU, "m"), _karte(SKU, "l")],
            }
        ],
        "band_je_tarif": {"11-s": "s", "11-m": "m", "11-l": "l"},
        "baender_katalog": [],
        "historie_lage": {},
    }
    return state, tco


def test_der_juengste_punkt_der_widerspruechlichen_1und1_linie_faellt_weg(tmp_path):
    state, tco = _state(tmp_path)
    mess = geraete_zeitreihe._messungen(state, tco, heute="2026-11-05")
    s_tage = mess[(MODELL, "s", 24)]["1&1"]
    assert "2026-11-05" not in s_tage, s_tage
    assert set(s_tage) == {"2026-09-12", "2026-10-07", "2026-11-03"}
    alt = round(24 * 32.99 + 220.0 + ANSCHLUSS, 2)
    assert alt == 1051.66
    assert all(m["wert"] == alt for m in s_tage.values())


def test_aeltere_punkte_der_widerspruechlichen_linie_bleiben_unveraendert(tmp_path):
    """Entscheidung 2: 12.09. bis 03.11. waren alle drei Tarife einheitlich bei
    220 € - kein Widerspruch, die Punkte bleiben stehen."""
    state, tco = _state(tmp_path)
    mess = geraete_zeitreihe._messungen(state, tco, heute="2026-11-05")
    s_tage = mess[(MODELL, "s", 24)]["1&1"]
    for datum in ("2026-09-12", "2026-10-07", "2026-11-03"):
        assert datum in s_tage
        assert s_tage[datum]["wert"] == 1051.66


def test_die_m_und_l_linien_behalten_ihren_juengsten_punkt(tmp_path):
    """M und L sind am 05.11. der Mehrheitswert (280 €) - ihr jüngster Punkt
    bleibt stehen, nur S fällt weg."""
    state, tco = _state(tmp_path)
    mess = geraete_zeitreihe._messungen(state, tco, heute="2026-11-05")
    m_tage = mess[(MODELL, "m", 24)]["1&1"]
    l_tage = mess[(MODELL, "l", 24)]["1&1"]
    assert "2026-11-05" in m_tage and "2026-11-05" in l_tage
    assert m_tage["2026-11-05"]["wert"] == round(24 * 37.99 + 280.0 + ANSCHLUSS, 2)
    assert l_tage["2026-11-05"]["wert"] == round(24 * 42.99 + 280.0 + ANSCHLUSS, 2)


def test_gegenprobe_ohne_heutigen_widerspruch_bleibt_der_juengste_punkt(tmp_path):
    """Ändert sich nichts am Gerätestand (alle drei weiter bei 220 €), gibt es
    keinen Widerspruch - der jüngste S-Punkt bleibt stehen."""
    state, tco = _state(tmp_path)
    heute_datei = state / "geraete_tco.json"
    daten = json.loads(heute_datei.read_text(encoding="utf-8"))
    for b in daten["buendel"]:
        b["geraet_zuzahlung"] = 220.0
    heute_datei.write_text(json.dumps(daten), encoding="utf-8")
    mess = geraete_zeitreihe._messungen(state, tco, heute="2026-11-05")
    s_tage = mess[(MODELL, "s", 24)]["1&1"]
    assert "2026-11-05" in s_tage
