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
ZWEI_FUNKTIONEN = (
    "def erste():\n    # Grund\n    return 1\n\n\ndef zweite():\n    return 2\n"
)
GEWANDERT = "def erste():\n    return 1\n\n\ndef zweite():\n    # Grund\n    return 2\n"
WISSEN = "wissen.py"
PFAD = f"src/paket/{WISSEN}"


def _git(ort, *argumente):
    umgebung = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", *argumente], cwd=ort, env=umgebung, check=True)


@pytest.fixture
def repo(tmp_path):
    dateien = {
        PFAD: MIT_WISSEN,
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


def _protokoll(repo, abschnitt="- nichts übernommen: erzählt den Code nach"):
    text = f"# Kommentarwissen\n\n### `{PFAD}`\n{abschnitt}\n"
    (repo / "outputs/kommentarwissen/01-x.md").write_text(text, encoding="utf-8")


def _schreibe(repo, text):
    (repo / PFAD).write_text(text, encoding="utf-8")


def test_nur_dateien_mit_wissenskommentar_brauchen_ein_protokoll(repo):
    assert list(kommentarwissen.kommentierte_dateien(repo)) == [PFAD]


def test_werkzeugschalter_und_shebang_sind_kein_wissen():
    assert kommentarwissen.wissenskommentare(NUR_SCHALTER) == []
    assert kommentarwissen.wissenskommentare("# Grund\nx = 1  # noch ein Grund\n") == [
        "# Grund",
        "# noch ein Grund",
    ]


@pytest.mark.parametrize(
    "kommentar",
    [
        "# noqa: BLE001 - ein Profil darf den Rest nicht kippen",
        "# noqa: F401  # wird dynamisch gebraucht",
        "# pragma: no cover - hängt an der Installation",
        "# noqa: Schleife bleibt einfach",
    ],
)
def test_begruendung_hinter_einem_schalter_ist_wissen(kommentar):
    text = f"import os  {kommentar}\n"
    assert kommentarwissen.wissenskommentare(text) == [kommentar]


def test_kommentar_nach_shebang_ist_wissen():
    text = "#!/usr/bin/env python3\n#!Hinweis in Zeile zwei\n"
    assert kommentarwissen.wissenskommentare(text) == ["#!Hinweis in Zeile zwei"]


def test_datei_ohne_protokollabschnitt_ist_rot(repo):
    assert kommentarwissen.befunde(repo) == [f"ohne Protokoll: {PFAD}"]
    assert kommentarwissen.main(["--wurzel", str(repo)]) == 1


def test_leerer_abschnitt_ist_rot_und_wird_nicht_festgehalten(repo):
    _protokoll(repo, "\n\n")
    assert kommentarwissen.main(["--wurzel", str(repo), "--schreiben"]) == 1
    assert kommentarwissen.befunde(repo) == [f"leerer Abschnitt: {PFAD}"]
    assert kommentarwissen.gespeicherte_abdeckung(repo) == {}


def test_nichts_uebernommen_braucht_einen_grund(repo):
    _protokoll(repo, "- nichts übernommen")
    assert kommentarwissen.befunde(repo) == [f"„nichts übernommen“ ohne Grund: {PFAD}"]


def test_ueberschrift_im_codeblock_zaehlt_nicht(repo):
    text = f"# Vorlage\n\n```\n### `{PFAD}`\n- Wissen\n```\n"
    (repo / "outputs/kommentarwissen/01-x.md").write_text(text, encoding="utf-8")
    assert kommentarwissen.befunde(repo) == [f"ohne Protokoll: {PFAD}"]


def test_naechste_ueberschrift_beendet_den_abschnitt(repo):
    text = f"### `{PFAD}`\n\n## Widersprüche\n- `{PFAD}:2`: Kommentar irrt\n"
    (repo / "outputs/kommentarwissen/01-x.md").write_text(text, encoding="utf-8")
    assert kommentarwissen.befunde(repo) == [f"leerer Abschnitt: {PFAD}"]


def test_protokoll_ohne_festgehaltenen_fingerabdruck_ist_rot(repo):
    _protokoll(repo)
    assert kommentarwissen.befunde(repo) == [
        f"Kommentare seit der Übernahme geändert: {PFAD}"
    ]


def test_festgehaltene_uebernahme_ist_gruen(repo, capsys):
    _protokoll(repo)
    assert kommentarwissen.main(["--wurzel", str(repo), "--schreiben"]) == 0
    assert "1 Dateien festgehalten" in capsys.readouterr().out
    assert kommentarwissen.main(["--wurzel", str(repo)]) == 0


def test_neuer_kommentar_ohne_protokollaenderung_bleibt_rot(repo, capsys):
    _protokoll(repo)
    kommentarwissen.schreibe_abdeckung(repo)
    _schreibe(repo, MIT_WISSEN + "# neues Wissen\n")
    assert kommentarwissen.main(["--wurzel", str(repo), "--schreiben"]) == 1
    ausgabe = capsys.readouterr().out
    assert f"nicht festgehalten, Abschnitt unverändert: {PFAD}" in ausgabe
    assert kommentarwissen.befunde(repo) == [
        f"Kommentare seit der Übernahme geändert: {PFAD}"
    ]


def test_neuer_kommentar_mit_nachgetragenem_protokoll_wird_gruen(repo):
    _protokoll(repo)
    kommentarwissen.schreibe_abdeckung(repo)
    _schreibe(repo, MIT_WISSEN + "# neues Wissen\n")
    _protokoll(repo, "- `GRENZE`: zehn statt sieben; neues Wissen nachgetragen")
    assert kommentarwissen.schreibe_abdeckung(repo) == (1, [])
    assert kommentarwissen.befunde(repo) == []


def test_kommentar_in_eine_andere_funktion_gewandert_ist_rot(repo):
    _schreibe(repo, ZWEI_FUNKTIONEN)
    _protokoll(repo)
    kommentarwissen.schreibe_abdeckung(repo)
    _schreibe(repo, GEWANDERT)
    assert kommentarwissen.befunde(repo) == [
        f"Kommentare seit der Übernahme geändert: {PFAD}"
    ]


def test_codeaenderung_ohne_kommentaraenderung_bleibt_gruen(repo):
    _schreibe(repo, ZWEI_FUNKTIONEN)
    _protokoll(repo)
    kommentarwissen.schreibe_abdeckung(repo)
    _schreibe(repo, ZWEI_FUNKTIONEN.replace("return 2", "return 3"))
    assert kommentarwissen.befunde(repo) == []


def test_geloeschte_kommentare_brauchen_kein_protokoll_mehr(repo):
    _schreibe(repo, "GRENZE = 10\n")
    assert kommentarwissen.befunde(repo) == []


def test_ueberschrift_muss_den_pfad_genau_nennen(repo):
    text = f"### {PFAD}\n- a\n### `paket/{WISSEN}`\n- b\n"
    (repo / "outputs/kommentarwissen/01-x.md").write_text(text, encoding="utf-8")
    assert kommentarwissen.protokollierte(repo) == {f"paket/{WISSEN}"}


def test_unlesbare_datei_nennt_ihren_pfad(repo):
    _schreibe(repo, "x = (\n# offen\n")
    with pytest.raises(kommentarwissen.Unlesbar, match=PFAD):
        kommentarwissen.kommentierte_dateien(repo)
