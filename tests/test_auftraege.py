import importlib
import json
import sys
from concurrent.futures import Future
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
auftraege = importlib.import_module("auftraege")

SKRIPT = """import json, sys
from pathlib import Path
auftrag = json.loads(Path(sys.argv[1]).read_text())
ablage = Path(sys.argv[1]).parent
with (ablage / "reihenfolge.txt").open("a") as f:
    f.write(auftrag["id"] + "\\n")
sys.exit(2 if auftrag["ziel"] == "rot" else 0)
"""


def _plan(tmp_path, *teile):
    ordner = tmp_path / "plan"
    ordner.mkdir()
    for kennung, bereich, abhaengig, ziel in teile:
        auftrag = {"id": kennung, "bereich": bereich, "abhaengigVon": abhaengig}
        (ordner / f"{kennung}.json").write_text(json.dumps(auftrag | {"ziel": ziel}))
    (ordner / "plan.json").write_text(json.dumps([t[0] for t in teile]))
    (tmp_path / "skript.py").write_text(SKRIPT)
    return ordner


def _abarbeiten(tmp_path, ordner):
    skript = ["--skript", str(tmp_path / "skript.py"), "--wurzel", str(tmp_path)]
    code = auftraege.main([str(ordner), *skript])
    reihenfolge = (ordner / "reihenfolge.txt").read_text().split()
    return code, reihenfolge, (ordner / auftraege.ERGEBNIS).read_text()


def test_alle_gemergt_in_der_reihenfolge_der_abhaengigkeiten(tmp_path):
    ordner = _plan(
        tmp_path,
        ("S9-1", "src/telco_radar/a/", [], "eins"),
        ("S9-2", "src/telco_radar/b/", ["S9-1"], "zwei"),
    )

    code, reihenfolge, ergebnis = _abarbeiten(tmp_path, ordner)

    assert code == 0
    assert reihenfolge == ["S9-1", "S9-2"]
    assert "- S9-2: gemergt (zwei)" in ergebnis
    assert "git push origin main" in ergebnis


def test_nach_einem_roten_auftrag_startet_keiner_mehr(tmp_path):
    ordner = _plan(
        tmp_path,
        ("S9-1", "src/telco_radar/a/", [], "rot"),
        ("S9-2", "src/telco_radar/a/", [], "zwei"),
        ("S9-3", "src/telco_radar/b/", ["S9-1"], "drei"),
    )

    code, reihenfolge, ergebnis = _abarbeiten(tmp_path, ordner)

    assert code == 2
    assert reihenfolge == ["S9-1"], "S9-2 teilt den Bereich und wartet, S9-3 hängt ab"
    assert "- S9-1: Exit 2, siehe Log (rot)" in ergebnis
    assert "- S9-2: nicht gestartet (zwei)" in ergebnis
    assert "- S9-3: nicht gestartet (drei)" in ergebnis


def _stand(*teile):
    liste = {k: {"bereich": b, "abhaengigVon": a} for k, b, a in teile}
    return auftraege.Stand(liste, list(liste))


def test_hoechstens_zwei_laufen_und_nie_mit_ueberschneidendem_bereich():
    stand = _stand(
        ("A", "src/telco_radar/report/", []),
        ("B", "src/telco_radar/report/templates/", []),
        ("C", "src/telco_radar/analyze/", []),
        ("D", "src/telco_radar/collect/", []),
    )

    assert stand.startbereit() == "A"
    stand.laufend[Future()] = "A"
    assert stand.startbereit() == "C", "B liegt im Bereich von A"
    stand.laufend[Future()] = "C"
    assert stand.startbereit() is None, "zwei laufen schon"


def test_abhaengiger_auftrag_wartet_auf_gemergt():
    stand = _stand(("A", "src/telco_radar/a/", []), ("B", "src/telco_radar/b/", ["A"]))
    stand.laufend[Future()] = "A"

    assert stand.startbereit() is None
    stand.laufend.clear()
    stand.ergebnis["A"] = auftraege.GEMERGT
    assert stand.startbereit() == "B"


def test_unlesbarer_plan_startet_nichts(tmp_path, capsys):
    assert auftraege.main([str(tmp_path / "fehlt")]) == 1
    assert "Plan nicht lesbar" in capsys.readouterr().out


def test_prompt_nennt_die_pfade_der_laufdateien_woertlich():
    format_ = importlib.import_module("auftrag_format")
    auftrag = {"art": "umbau", "abnahme": "tests/test_x.py", "bereich": "src/a/"}
    pfade = {"TELCO_PRUEFER_ORDNER": "/tmp/pruefer-S1-x", "TELCO_AUFTRAG": "/r/a.json"}

    text = format_.prompt("pruefer", auftrag, 400, pfade)

    assert "TELCO_PRUEFER_ORDNER = /tmp/pruefer-S1-x" in text
    assert "TELCO_AUFTRAG = /r/a.json" in text
    assert "Abnahme tests/test_x.py" in text
