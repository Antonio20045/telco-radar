import subprocess
import sys
from collections import Counter

import pytest
from test_waechter import projekt, waechter

waechter_leck = sys.modules["waechter_leck"]

SCHLUESSEL = "xkeysib-" + "a1b2c3d4e5f6"
SMTP = "xsmtpsib-" + "Z9y8x7"
ADRESSE = "kunde.mustermann+radar@beispiel-mail.de"

__all__ = ["projekt"]


def _git(wurzel, *argumente):
    subprocess.run(["git", *argumente], cwd=wurzel, check=True, capture_output=True)


def _schreibe(wurzel, pfad, text):
    datei = wurzel / pfad
    datei.parent.mkdir(parents=True, exist_ok=True)
    datei.write_text(text, encoding="utf-8")


def _commit(wurzel, nachricht):
    _git(wurzel, "add", "-A")
    _git(wurzel, "commit", "-q", "-m", nachricht)


@pytest.fixture()
def repo(tmp_path):
    """Ein Git-Repo mit sauberem Bestand unter data/, site/ und src/."""
    wurzel = tmp_path / "repo"
    wurzel.mkdir()
    _git(wurzel, "init", "-q")
    _git(wurzel, "config", "user.email", "t@example.org")
    _git(wurzel, "config", "user.name", "T")
    _schreibe(wurzel, "data/state/seen.jsonl", '{"h": "abc"}\n')
    _schreibe(wurzel, "data/state/geraete_db.json", '{"a": 1}\n')
    _schreibe(wurzel, "site/index.html", "<p>Radar</p>\n")
    _schreibe(wurzel, "src/telco_radar/modul.py", "WERT = 1\n")
    _commit(wurzel, "bestand")
    return wurzel


def _getrackt(wurzel, pfad, text):
    _schreibe(wurzel, pfad, text)
    _git(wurzel, "add", pfad)


def test_sauberer_bestand_ist_gruen(repo):
    assert waechter_leck.lecks(repo) == []


@pytest.mark.parametrize(
    "pfad",
    [
        "data/state/seen.jsonl",
        "data/state/geraete_db.json",
        "site/index.html",
        "site/neu/seite.html",
        "src/telco_radar/modul.py",
        "docs/notiz.md",
        "datei_ohne_endung",
    ],
)
def test_brevo_schluessel_in_jeder_getrackten_datei_ist_rot(repo, pfad):
    _getrackt(repo, pfad, f"wert = {SCHLUESSEL}\n")
    assert waechter_leck.lecks(repo) == [
        f"{pfad}: Brevo-Schlüssel im Repo (gehört in ein Secret)"
    ]


def test_smtp_schluessel_und_binaerdatei_sind_rot(repo):
    _getrackt(repo, "site/bilder/a.png", "\x89PNG\x00\x01" + SMTP)
    assert waechter_leck.lecks(repo) == [
        "site/bilder/a.png: Brevo-Schlüssel im Repo (gehört in ein Secret)"
    ]


def test_die_meldung_nennt_den_schluessel_nicht(repo):
    _getrackt(repo, "site/index.html", SCHLUESSEL)
    assert all(SCHLUESSEL not in zeile for zeile in waechter_leck.lecks(repo))


def test_praefix_ohne_schluessel_ist_gruen(repo):
    _getrackt(repo, "docs/notiz.md", "Brevo-Schlüssel beginnen mit xkeysib- .\n")
    assert waechter_leck.lecks(repo) == []


@pytest.mark.parametrize(
    "pfad", ["data/state/seen.jsonl", "data/state/newsletter_stats.jsonl"]
)
def test_adresse_in_einer_jsonl_unter_data_ist_rot(repo, pfad):
    _getrackt(repo, pfad, f'{{"an": "{ADRESSE}"}}\n')
    assert waechter_leck.lecks(repo) == [f"{pfad}: E-Mail-Adresse in Bot-Daten"]


@pytest.mark.parametrize(
    "pfad", ["data/state/geraete_db.json", "site/a.jsonl", "tests/a.jsonl"]
)
def test_adresse_ausserhalb_der_jsonl_unter_data_ist_gruen(repo, pfad):
    _getrackt(repo, pfad, f'{{"an": "{ADRESSE}"}}\n')
    assert waechter_leck.lecks(repo) == []


def test_erst_die_vorgemerkte_datei_zaehlt(repo):
    _schreibe(repo, "data/state/neu.jsonl", f'{{"an": "{ADRESSE}"}}\n')
    assert waechter_leck.lecks(repo) == []
    _git(repo, "add", "data/state/neu.jsonl")
    assert waechter_leck.lecks(repo) == [
        "data/state/neu.jsonl: E-Mail-Adresse in Bot-Daten"
    ]


def test_ohne_git_ist_die_pruefung_rot(tmp_path):
    assert waechter_leck.lecks(tmp_path) == [
        "Leckprüfung: getrackte Dateien nicht lesbar (git ls-files)"
    ]


def test_der_kommandoweg_endet_rot_und_nennt_die_datei(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    assert waechter_leck.main() == 0
    _getrackt(repo, "data/state/seen.jsonl", f'{{"an": "{ADRESSE}"}}\n')
    assert waechter_leck.main() == 1
    ausgabe = capsys.readouterr().out
    assert ausgabe == "::error::data/state/seen.jsonl: E-Mail-Adresse in Bot-Daten\n"


def test_der_kommandoweg_laeuft_als_eigenes_skript(repo):
    skript = waechter_leck.__file__
    _getrackt(repo, "site/index.html", SCHLUESSEL)
    lauf = subprocess.run(
        [sys.executable, skript], cwd=repo, capture_output=True, text=True
    )
    assert lauf.returncode == 1
    assert "site/index.html: Brevo-Schlüssel" in lauf.stdout


def test_stufe_null_ist_rot_bei_schluessel_und_adresse(projekt):
    assert waechter.pruefe(projekt, Counter())[0] == []
    _schreibe(projekt, "data/state/seen.jsonl", f'{{"an": "{ADRESSE}"}}\n')
    _schreibe(projekt, "site/index.html", SCHLUESSEL)
    _commit(projekt, "bot")
    assert waechter.pruefe(projekt, Counter()) == (
        [
            "data/state/seen.jsonl: E-Mail-Adresse in Bot-Daten",
            "site/index.html: Brevo-Schlüssel im Repo (gehört in ein Secret)",
        ],
        [],
    )


def test_der_vorgemerkte_inhalt_zaehlt_auch_wenn_die_kopie_sauber_ist(repo):
    _getrackt(repo, "data/state/seen.jsonl", f'{{"an": "{ADRESSE}"}}\n')
    _schreibe(repo, "data/state/seen.jsonl", "{}\n")
    _getrackt(repo, "site/index.html", SCHLUESSEL)
    (repo / "site/index.html").unlink()
    assert waechter_leck.lecks(repo) == [
        "data/state/seen.jsonl: E-Mail-Adresse in Bot-Daten",
        "site/index.html: Brevo-Schlüssel im Repo (gehört in ein Secret)",
    ]


def test_nicht_vorgemerkte_aenderung_einer_getrackten_datei_zaehlt(repo):
    _schreibe(repo, "site/index.html", SCHLUESSEL)
    assert waechter_leck.lecks(repo) == [
        "site/index.html: Brevo-Schlüssel im Repo (gehört in ein Secret)"
    ]


def test_ein_symlink_mit_schluessel_als_ziel_ist_rot(repo):
    (repo / "data/k").symlink_to(SCHLUESSEL)
    _git(repo, "add", "data/k")
    assert waechter_leck.lecks(repo) == [
        "data/k: Brevo-Schlüssel im Repo (gehört in ein Secret)"
    ]


def test_bildnamen_mit_at_sind_keine_adresse(repo):
    _getrackt(repo, "data/state/seen.jsonl", '{"bild": "logo@2x.png"}\n')
    assert waechter_leck.lecks(repo) == []


_WORKFLOW = "steps:\n  - run: |\n      git add data/\n{}      git commit -m lauf\n"


def test_ein_workflow_commit_ohne_scan_ist_rot(repo):
    _getrackt(repo, ".github/workflows/lauf.yml", _WORKFLOW.format(""))
    assert waechter_leck.lecks(repo) == [
        ".github/workflows/lauf.yml:4: git commit ohne vorherigen"
        " scripts/waechter_leck.py"
    ]


def test_ein_workflow_commit_nach_dem_scan_ist_gruen(repo):
    scan = "      python scripts/waechter_leck.py\n"
    _getrackt(repo, ".github/workflows/lauf.yml", _WORKFLOW.format(scan))
    assert waechter_leck.lecks(repo) == []


def test_ein_git_add_nach_dem_scan_verlangt_einen_neuen(repo):
    text = _WORKFLOW.format(
        "      python scripts/waechter_leck.py\n      git add site\n"
    )
    _getrackt(repo, ".github/workflows/lauf.yml", text)
    assert waechter_leck.lecks(repo) == [
        ".github/workflows/lauf.yml:6: git commit ohne vorherigen"
        " scripts/waechter_leck.py"
    ]


_OHNE_SCAN = (
    ".github/workflows/lauf.yml:{}: git commit ohne vorherigen scripts/waechter_leck.py"
)


@pytest.mark.parametrize(
    "scan",
    [
        "      # python scripts/waechter_leck.py\n",
        "      python scripts/waechter_leck.py || true\n",
        "      echo scripts/waechter_leck.py\n",
        "      python scripts/waechter_leck.py; true\n",
    ],
)
def test_ein_scheinaufruf_gilt_nicht_als_scan(repo, scan):
    _getrackt(repo, ".github/workflows/lauf.yml", _WORKFLOW.format(scan))
    assert waechter_leck.lecks(repo) == [_OHNE_SCAN.format(5)]


@pytest.mark.parametrize(
    "commit",
    [
        "git -c user.name=bot commit -m lauf",
        "git -C . commit -m lauf",
        "git --no-pager commit -am lauf",
        "git  commit -m lauf",
    ],
)
def test_ein_commit_mit_git_optionen_zaehlt(repo, commit):
    text = f"steps:\n  - run: |\n      git -c a=b add data/\n      {commit}\n"
    _getrackt(repo, ".github/workflows/lauf.yml", text)
    assert waechter_leck.lecks(repo) == [_OHNE_SCAN.format(4)]


def test_ein_commit_ohne_vorheriges_add_braucht_einen_scan(repo):
    text = "steps:\n  - run: git commit -am lauf\n"
    _getrackt(repo, ".github/workflows/lauf.yml", text)
    assert waechter_leck.lecks(repo) == [_OHNE_SCAN.format(2)]
    text = "steps:\n  - run: python scripts/waechter_leck.py\n" + text[7:]
    _getrackt(repo, ".github/workflows/lauf.yml", text)
    assert waechter_leck.lecks(repo) == []
