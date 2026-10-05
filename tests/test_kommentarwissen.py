import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
kommentarwissen = importlib.import_module("kommentarwissen")

MIT_WISSEN = "GRENZE = 10\n# Zehn statt sieben: ein ausgefallener Lauf\n"
NUR_SCHALTER = (
    "#!/usr/bin/env python3\n"
    "import os  # noqa: F401\n"
    "x: int = 'a'  # type: ignore[assignment]\n"
    "if x:  # pragma: no cover\n    pass\n"
)


def _git(ort, *argumente):
    umgebung = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", *argumente], cwd=ort, env=umgebung, check=True)


@pytest.fixture
def repo(tmp_path):
    dateien = {
        "src/paket/wissen.py": MIT_WISSEN,
        "src/paket/schalter.py": NUR_SCHALTER,
        "src/paket/leer.py": "WERT = 1\n",
        "data/state/bot.py": "# Bot-Daten zählen nicht\n",
        "site/seite.py": "# gerenderte Seite zählt nicht\n",
    }
    for pfad, inhalt in dateien.items():
        (tmp_path / pfad).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / pfad).write_text(inhalt, encoding="utf-8")
    (tmp_path / "unversioniert.py").write_text("# nie hinzugefügt\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", *dateien)
    (tmp_path / "outputs/kommentarwissen").mkdir(parents=True)
    return tmp_path


def _protokoll(repo, *pfade):
    text = "# Kommentarwissen\n\n" + "".join(
        f"### `{p}`\n- nichts übernommen\n\n" for p in pfade
    )
    (repo / "outputs/kommentarwissen/01-x.md").write_text(text, encoding="utf-8")


def test_nur_dateien_mit_wissenskommentar_brauchen_ein_protokoll(repo):
    assert list(kommentarwissen.kommentierte_dateien(repo)) == ["src/paket/wissen.py"]


def test_werkzeugschalter_und_shebang_sind_kein_wissen():
    assert kommentarwissen.wissenskommentare(NUR_SCHALTER) == []
    assert kommentarwissen.wissenskommentare("# Grund\nx = 1  # noch ein Grund\n") == [
        "# Grund",
        "# noch ein Grund",
    ]


def test_schalter_mit_angehaengter_begruendung_bleibt_schalter():
    text = "import os  # noqa: F401  # wird dynamisch gebraucht\n"
    assert kommentarwissen.wissenskommentare(text) == []


def test_kommentar_nach_shebang_ist_wissen():
    text = "#!/usr/bin/env python3\n#!Hinweis in Zeile zwei\n"
    assert kommentarwissen.wissenskommentare(text) == ["#!Hinweis in Zeile zwei"]


def test_datei_ohne_protokollabschnitt_ist_rot(repo):
    assert kommentarwissen.befunde(repo) == ["ohne Protokoll: src/paket/wissen.py"]
    assert kommentarwissen.main(["--wurzel", str(repo)]) == 1


def test_protokoll_ohne_festgehaltenen_fingerabdruck_ist_rot(repo):
    _protokoll(repo, "src/paket/wissen.py")
    assert kommentarwissen.befunde(repo) == [
        "Kommentare seit der Übernahme geändert: src/paket/wissen.py"
    ]


def test_festgehaltene_uebernahme_ist_gruen(repo, capsys):
    _protokoll(repo, "src/paket/wissen.py")
    assert kommentarwissen.main(["--wurzel", str(repo), "--schreiben"]) == 0
    assert "1 Dateien festgehalten" in capsys.readouterr().out
    assert kommentarwissen.main(["--wurzel", str(repo)]) == 0


def test_neuer_kommentar_nach_der_uebernahme_ist_rot(repo):
    _protokoll(repo, "src/paket/wissen.py")
    kommentarwissen.schreibe_abdeckung(repo)
    datei = repo / "src/paket/wissen.py"
    datei.write_text(MIT_WISSEN + "# neues Wissen\n", encoding="utf-8")
    assert kommentarwissen.befunde(repo) == [
        "Kommentare seit der Übernahme geändert: src/paket/wissen.py"
    ]


def test_geloeschte_kommentare_brauchen_kein_protokoll_mehr(repo):
    (repo / "src/paket/wissen.py").write_text("GRENZE = 10\n", encoding="utf-8")
    assert kommentarwissen.befunde(repo) == []


def test_ueberschrift_muss_den_pfad_genau_nennen(repo):
    text = "### src/paket/wissen.py\n### `paket/wissen.py`\n"
    (repo / "outputs/kommentarwissen/01-x.md").write_text(text, encoding="utf-8")
    assert kommentarwissen.protokollierte(repo) == {"paket/wissen.py"}


def test_unlesbare_datei_nennt_ihren_pfad(repo):
    (repo / "src/paket/wissen.py").write_text("x = (\n# offen\n", encoding="utf-8")
    with pytest.raises(kommentarwissen.Unlesbar, match="src/paket/wissen.py"):
        kommentarwissen.kommentierte_dateien(repo)
