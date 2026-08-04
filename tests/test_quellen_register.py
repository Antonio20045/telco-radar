"""Quellenregister und automatische Quarantaene.

Kriterien 12 und 13 des Skalierungs-Auftrags: je Quelle maschinenlesbar,
woher sie kam, wann sie abgenommen wurde und wann sie zuletzt geliefert
hat - und eine Quelle, die dauerhaft nichts liefert, wird stillgelegt und
im Protokoll ausgewiesen.
"""
from __future__ import annotations

import json

from telco_radar.quellen_register import QuellenRegister


def _ergebnis(url: str, status: str = "ok", count: int = 5, **rest) -> dict:
    return {"url": url, "name": rest.pop("name", "Quelle"), "status": status,
            "count": count, "origin": "operator", "region": "europe",
            "kind": "rss", **rest}


def _register(tmp_path, **kw) -> QuellenRegister:
    return QuellenRegister(tmp_path / "register.json", **kw)


def test_erster_lauf_legt_die_quelle_an(tmp_path):
    reg = _register(tmp_path)
    ereignisse = reg.aktualisieren([_ergebnis("https://a.example/feed")],
                                   "2026-08-04")

    e = reg.eintrag("https://a.example/feed")
    assert ereignisse["neu"] == ["https://a.example/feed"]
    assert e["erster_lauf"] == e["letzter_erfolg"] == "2026-08-04"
    assert e["laeufe"] == 1 and e["ok"] == 1


def test_herkunft_und_abnahmedatum_kommen_aus_der_konfiguration(tmp_path):
    reg = _register(tmp_path)
    reg.aktualisieren(
        [_ergebnis("https://a.example/feed")], "2026-08-04",
        {"https://a.example/feed": {"herkunft": "Musteruebertragung q4web",
                                    "abgenommen": "2026-07-30"}})

    e = reg.eintrag("https://a.example/feed")
    assert e["herkunft"] == "Musteruebertragung q4web"
    assert e["abgenommen"] == "2026-07-30"


def test_ohne_gepflegtes_abnahmedatum_gilt_der_erste_lauf(tmp_path):
    reg = _register(tmp_path)
    reg.aktualisieren([_ergebnis("https://a.example/feed")], "2026-08-04")
    assert reg.eintrag("https://a.example/feed")["abgenommen"] == "2026-08-04"


def test_letzter_erfolg_bleibt_am_letzten_erfolg_stehen(tmp_path):
    reg = _register(tmp_path)
    reg.aktualisieren([_ergebnis("https://a.example/feed")], "2026-08-01")
    reg.aktualisieren([_ergebnis("https://a.example/feed", "empty", 0)],
                      "2026-08-04")

    e = reg.eintrag("https://a.example/feed")
    assert e["letzter_erfolg"] == "2026-08-01"
    assert e["letzter_lauf"] == "2026-08-04"
    assert e["serie_ohne_inhalt"] == 1


def test_ein_erfolg_setzt_die_serie_zurueck(tmp_path):
    reg = _register(tmp_path, quarantaene_nach=3)
    for tag in ("01", "02"):
        reg.aktualisieren([_ergebnis("https://a.example/feed", "fail", 0)],
                          f"2026-08-{tag}")
    reg.aktualisieren([_ergebnis("https://a.example/feed")], "2026-08-03")

    assert reg.eintrag("https://a.example/feed")["serie_ohne_inhalt"] == 0
    assert reg.stillgelegt() == set()


# ------------------------------------------------------------ Quarantaene

def test_quelle_wird_nach_n_erfolglosen_laeufen_stillgelegt(tmp_path):
    reg = _register(tmp_path, quarantaene_nach=3)
    for tag in ("01", "02"):
        reg.aktualisieren([_ergebnis("https://tot.example/feed", "empty", 0)],
                          f"2026-08-{tag}")
    assert reg.stillgelegt() == set()

    ereignisse = reg.aktualisieren(
        [_ergebnis("https://tot.example/feed", "fail", 0,
                   error="HTTPStatusError: 403")], "2026-08-03")

    assert ereignisse["stillgelegt"] == ["https://tot.example/feed"]
    e = reg.eintrag("https://tot.example/feed")
    assert e["quarantaene_seit"] == "2026-08-03"
    assert "403" in e["quarantaene_grund"]
    assert reg.stillgelegt() == {"https://tot.example/feed"}


def test_leere_meldungsliste_zaehlt_als_kein_inhalt(tmp_path):
    """status ok mit count 0 kommt vor - und ist kein Erfolg."""
    reg = _register(tmp_path, quarantaene_nach=1)
    reg.aktualisieren([_ergebnis("https://a.example/feed", "ok", 0)],
                      "2026-08-01")
    assert reg.stillgelegt() == {"https://a.example/feed"}


def test_stillgelegte_quelle_bekommt_einen_bewaehrungslauf(tmp_path):
    reg = _register(tmp_path, quarantaene_nach=1, probe_alle=3)
    reg.aktualisieren([_ergebnis("https://tot.example/feed", "empty", 0)],
                      "2026-08-01")           # Lauf 1 -> stillgelegt

    assert reg.stillgelegt() == {"https://tot.example/feed"}   # vor Lauf 2
    reg.aktualisieren([_ergebnis("https://tot.example/feed", "quarantaene", 0)],
                      "2026-08-02")
    assert reg.stillgelegt() == set(), "Lauf 3 ist der Bewaehrungslauf"


def test_ein_bewaehrungslauf_mit_inhalt_hebt_die_quarantaene_auf(tmp_path):
    reg = _register(tmp_path, quarantaene_nach=1, probe_alle=2)
    reg.aktualisieren([_ergebnis("https://a.example/feed", "empty", 0)],
                      "2026-08-01")
    ereignisse = reg.aktualisieren([_ergebnis("https://a.example/feed")],
                                   "2026-08-02")

    assert ereignisse["befreit"] == ["https://a.example/feed"]
    assert "quarantaene_seit" not in reg.eintrag("https://a.example/feed")
    assert reg.stillgelegt() == set()


def test_ein_uebersprungener_lauf_zaehlt_fuer_nichts(tmp_path):
    reg = _register(tmp_path, quarantaene_nach=99)
    reg.aktualisieren([_ergebnis("https://a.example/feed", "quarantaene", 0)],
                      "2026-08-01")

    e = reg.eintrag("https://a.example/feed")
    assert e["laeufe"] == 0 and e["serie_ohne_inhalt"] == 0


def test_quarantaene_abschaltbar(tmp_path):
    reg = _register(tmp_path, quarantaene_nach=0)
    for i in range(20):
        reg.aktualisieren([_ergebnis("https://a.example/feed", "fail", 0)],
                          f"2026-08-{i + 1:02d}")
    assert reg.stillgelegt() == set()


# ---------------------------------------------------------- Bestand/Datei

def test_register_ueberlebt_den_neustart(tmp_path):
    reg = _register(tmp_path, quarantaene_nach=2)
    reg.aktualisieren([_ergebnis("https://a.example/feed", "empty", 0)],
                      "2026-08-01")
    reg.speichern()

    wieder = _register(tmp_path, quarantaene_nach=2)
    assert wieder.lauf_nummer == 1
    assert wieder.eintrag("https://a.example/feed")["serie_ohne_inhalt"] == 1

    wieder.aktualisieren([_ergebnis("https://a.example/feed", "empty", 0)],
                         "2026-08-02")
    assert wieder.stillgelegt() == {"https://a.example/feed"}


def test_kaputte_datei_kostet_den_lauf_nicht(tmp_path):
    (tmp_path / "register.json").write_text("{kein json")
    reg = _register(tmp_path)
    reg.aktualisieren([_ergebnis("https://a.example/feed")], "2026-08-04")
    assert len(reg.quellen) == 1


def test_entfernte_quelle_bleibt_mit_vermerk_stehen(tmp_path):
    reg = _register(tmp_path)
    reg.aktualisieren([_ergebnis("https://alt.example/feed")], "2026-08-01")
    reg.aktualisieren([_ergebnis("https://neu.example/feed")], "2026-08-02")

    alt = reg.eintrag("https://alt.example/feed")
    assert alt["nicht_mehr_konfiguriert_seit"] == "2026-08-02"
    assert alt["ok"] == 1, "die Historie bleibt erhalten"


def test_uebersicht_nennt_stillgelegte_und_nie_erfolgreiche(tmp_path):
    reg = _register(tmp_path, quarantaene_nach=2)
    for tag in ("01", "02", "03"):
        reg.aktualisieren([
            _ergebnis("https://tot.example/feed", "empty", 0, name="Tot"),
            _ergebnis("https://lebt.example/feed", name="Lebt"),
        ], f"2026-08-{tag}")

    u = reg.uebersicht()
    assert u["quellen_gesamt"] == 2 and u["in_quarantaene"] == 1
    assert u["quarantaene"][0]["name"] == "Tot"
    assert [q["name"] for q in u["ohne_erfolg"]] == ["Tot"]


def test_datei_ist_lesbares_json(tmp_path):
    reg = _register(tmp_path)
    reg.aktualisieren([_ergebnis("https://a.example/feed")], "2026-08-04")
    reg.speichern()

    roh = json.loads((tmp_path / "register.json").read_text(encoding="utf-8"))
    assert roh["version"] == 1 and roh["lauf_nummer"] == 1
    assert "https://a.example/feed" in roh["quellen"]
