"""``scripts/gegenprobe_ablegen.py`` (dritte Prüfung zu PR 200): fehlende Teildateien
sind eine benannte Lücke, ein nachgelieferter Teil ersetzt sie, zwei Läufe desselben
Tages zählen beide, dieselbe Teildatei zweimal zählt einmal."""

from __future__ import annotations

import json

from gegenprobe_nacht import satz, zeile
from test_beleg_skripte import lade_skript

from telco_radar import gegenprobe as gp

ABLEGEN = lade_skript("gegenprobe_ablegen")
D = "2026-11-22"


def _wurzel(tmp_path, saetze):
    (tmp_path / "data/state").mkdir(parents=True)
    bestand = json.dumps({"updated": D, "buendel": saetze})
    (tmp_path / "data/state/geraete_tco.json").write_text(bestand, encoding="utf-8")
    return tmp_path


def _teil(ordner, job, zeilen, laeufe):
    ordner.mkdir(parents=True, exist_ok=True)
    gp.schreibe_tag(ordner / f"{job}.jsonl", zeilen)
    (ordner / f"{job}.lauf.json").write_text(json.dumps(laeufe), encoding="utf-8")


def _bilanz(root):
    pfad = root / f"data/state/gegenprobe/bilanz/{D}.json"
    return json.loads(pfad.read_text(encoding="utf-8"))


def _lauf(anbieter, n):
    return [
        {
            "datum": D,
            "anbieter": anbieter,
            "besuche": n,
            "sekunden": 5.0,
            "buendel": n,
            "ausfall": None,
            "zurueckgestellt": 0,
        }
    ]


def test_fehlende_teildatei_ist_none_mit_grund(tmp_path):
    s = satz(1, "o2", first_seen=D)
    t = satz(2, "telekom", first_seen=D)
    root = _wurzel(tmp_path, [s, t])
    q = tmp_path / "teile"
    _teil(q / "o2", "o2", [zeile(s, D, gp.BESTAETIGT)], _lauf("o2", 1))
    argumente = ["--root", str(root), "--quelle", str(q)]
    assert ABLEGEN.main([*argumente, "--erwartet", '["o2","telekom"]']) == 0
    b = _bilanz(root)
    assert b["anbieter"]["telekom"]["besuche"] is None
    assert b["anbieter"]["telekom"]["messung_fehlt"]
    assert b["summe"]["besuche"] is None


def test_zwei_laeufe_gleicher_tag_nichts_verloren(tmp_path):
    s = satz(1, "o2", first_seen=D)
    u = satz(2, "o2", first_seen=D)
    root = _wurzel(tmp_path, [s, u])
    q1, q2 = tmp_path / "t1", tmp_path / "t2"
    _teil(q1 / "o2", "o2", [zeile(s, D, gp.BESTAETIGT)], _lauf("o2", 1))
    _teil(q2 / "o2", "o2", [zeile(u, D, gp.BESTAETIGT)], _lauf("o2", 1))
    ABLEGEN.main(["--root", str(root), "--quelle", str(q1)])
    ABLEGEN.main(["--root", str(root), "--quelle", str(q2)])
    b = _bilanz(root)
    assert b["anbieter"]["o2"]["im_fenster"] == 2
    assert b["anbieter"]["o2"]["besuche"] == 2


def test_nachgelieferter_teil_ersetzt_die_luecke(tmp_path):
    t = satz(2, "telekom", first_seen=D)
    root = _wurzel(tmp_path, [t])
    leer = ["--root", str(root), "--quelle", str(tmp_path / "leer")]
    ABLEGEN.main([*leer, "--erwartet", '["telekom"]'])
    assert _bilanz(root)["anbieter"]["telekom"]["besuche"] is None
    q2 = tmp_path / "t2"
    _teil(q2 / "telekom", "telekom", [zeile(t, D, gp.BESTAETIGT)], _lauf("telekom", 1))
    ABLEGEN.main(["--root", str(root), "--quelle", str(q2)])
    telekom = _bilanz(root)["anbieter"]["telekom"]
    assert (telekom["besuche"], telekom["messung_fehlt"]) == (1, None)


def test_gleiche_teildatei_zweimal_abgelegt_zaehlt_besuche_einmal(tmp_path):
    s = satz(1, "o2", first_seen=D)
    root = _wurzel(tmp_path, [s])
    q = tmp_path / "t1"
    _teil(q / "o2", "o2", [zeile(s, D, gp.BESTAETIGT)], _lauf("o2", 1))
    ABLEGEN.main(["--root", str(root), "--quelle", str(q)])
    ABLEGEN.main(["--root", str(root), "--quelle", str(q)])
    assert _bilanz(root)["anbieter"]["o2"]["besuche"] == 1
