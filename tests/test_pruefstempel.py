import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

pruefstempel = importlib.import_module("pruefstempel")

_NUTZER = ["-c", "user.name=Mensch", "-c", "user.email=m@example.invalid"]
_BOT = ["-c", f"user.name={pruefstempel.BOT}", "-c", "user.email=b@example.invalid"]


def _git(ort, *argumente, nutzer=_NUTZER):
    umgebung = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    lauf = subprocess.run(
        ["git", *nutzer, *argumente],
        cwd=ort,
        env=umgebung,
        capture_output=True,
        text=True,
        check=True,
    )
    return lauf.stdout.strip()


def _commit(ort, datei, text, nutzer=_NUTZER):
    pfad = ort / datei
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(text, "utf-8")
    _git(ort, "add", "-A")
    _git(ort, "commit", "-q", "-m", datei, nutzer=nutzer)
    return _git(ort, "rev-parse", "HEAD")


@pytest.fixture()
def repo(tmp_path):
    ort = tmp_path / "repo"
    ort.mkdir()
    _git(ort, "init", "-q", "-b", "main")
    _commit(ort, "a.txt", "a\n")
    _commit(ort, pruefstempel.EINFUEHRUNG, "stempel\n")
    return ort


def _baum(ort, commit="HEAD"):
    return _git(ort, "rev-parse", f"{commit}^{{tree}}")


def test_arbeitsbaum_ist_der_baum_von_head_bei_sauberem_stand(repo):
    assert pruefstempel.arbeitsbaum(repo) == _baum(repo)


def test_arbeitsbaum_enthaelt_geaenderte_und_neue_dateien_wie_ihr_commit(repo):
    (repo / "a.txt").write_text("geaendert\n", "utf-8")
    (repo / "neu.txt").write_text("neu\n", "utf-8")
    vorher = pruefstempel.arbeitsbaum(repo)
    assert vorher != _baum(repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "x")
    assert vorher == _baum(repo)


def test_arbeitsbaum_laesst_den_index_unberuehrt(repo):
    (repo / "neu.txt").write_text("neu\n", "utf-8")
    pruefstempel.arbeitsbaum(repo)
    assert _git(repo, "status", "--porcelain") == "?? neu.txt"


def test_ein_fremder_index_aus_dem_hook_lenkt_den_baum_nicht_um(repo, monkeypatch):
    monkeypatch.setenv("GIT_INDEX_FILE", str(repo / "gibt-es-nicht"))
    assert pruefstempel.arbeitsbaum(repo) == _baum(repo)


def test_stempel_liegt_im_gemeinsamen_git_ordner_auch_aus_einem_worktree(
    repo, tmp_path
):
    baum = _baum(repo)
    pruefstempel.stempeln(repo, baum)
    assert (repo / ".git/pruefleiter/gruen" / baum).is_file()
    zweit = tmp_path / "wt"
    _git(repo, "worktree", "add", "-q", "--detach", str(zweit))
    assert pruefstempel.ist_gestempelt(zweit, baum)


def test_ohne_stempel_ist_jeder_commit_seit_der_einfuehrung_ungeprueft(repo):
    einfuehrung = _git(repo, "rev-parse", "HEAD")
    danach = _commit(repo, "b.txt", "b\n")
    befund = pruefstempel.ungestempelte(repo, "main")
    assert befund.commits == [danach, einfuehrung]
    assert not befund.stempel_gefunden


def test_gestempelter_commit_beendet_die_liste(repo):
    pruefstempel.stempeln(repo, _baum(repo))
    neu = _commit(repo, "b.txt", "b\n")
    assert pruefstempel.ungestempelte(repo, "main").commits == [neu]
    pruefstempel.stempeln(repo, _baum(repo))
    befund = pruefstempel.ungestempelte(repo, "main")
    assert befund.commits == []
    assert befund.stempel_gefunden


def test_datenlauf_des_bots_braucht_keinen_stempel_anderer_bot_commit_schon(repo):
    pruefstempel.stempeln(repo, _baum(repo))
    _commit(repo, "data/state/x.jsonl", "{}\n", nutzer=_BOT)
    _commit(repo, "site/index.html", "<p>\n", nutzer=_BOT)
    assert pruefstempel.ungestempelte(repo, "main").commits == []
    code = _commit(repo, "src/x.py", "x = 1\n", nutzer=_BOT)
    assert pruefstempel.ungestempelte(repo, "main").commits == [code]


def test_ohne_einfuehrung_gibt_es_nichts_zu_melden(tmp_path):
    ort = tmp_path / "alt"
    ort.mkdir()
    _git(ort, "init", "-q", "-b", "main")
    _commit(ort, "a.txt", "a\n")
    assert pruefstempel.ungestempelte(ort, "main").commits == []


def test_push_am_hook_vorbei_erscheint_als_ungeprueft(repo, tmp_path):
    ursprung = tmp_path / "ursprung.git"
    _git(tmp_path, "clone", "-q", "--bare", str(repo), str(ursprung))
    _git(repo, "remote", "add", "origin", str(ursprung))
    _git(repo, "fetch", "-q", "origin")
    pruefstempel.stempeln(repo, _baum(repo))
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "pre-push").write_text("#!/bin/sh\nexit 1\n", "utf-8")
    (hooks / "pre-push").chmod(0o755)
    _git(repo, "config", "core.hooksPath", str(hooks))
    roh = _commit(repo, "rot.txt", "rot\n")
    with pytest.raises(subprocess.CalledProcessError):
        _git(repo, "push", "-q", "origin", "HEAD:main")
    _git(repo, "-c", "core.hooksPath=/dev/null", "push", "-q", "origin", "HEAD:main")
    _git(repo, "fetch", "-q", "origin")
    assert pruefstempel.ungestempelte(repo).commits == [roh]


def test_stemple_lauf_stempelt_auch_den_baum_nach_gesenkten_basen(repo):
    vorher = pruefstempel.arbeitsbaum(repo)
    (repo / "a.txt").write_text("gesenkt\n", "utf-8")
    meldung = pruefstempel.stemple_lauf(repo, vorher, ["a.txt"])
    nachher = pruefstempel.arbeitsbaum(repo)
    assert pruefstempel.ist_gestempelt(repo, vorher)
    assert pruefstempel.ist_gestempelt(repo, nachher)
    assert meldung == f"gestempelt {vorher[:12]} und {nachher[:12]}"


def test_fremde_aenderung_waehrend_des_laufs_verhindert_jeden_stempel(repo):
    vorher = pruefstempel.arbeitsbaum(repo)
    (repo / "a.txt").write_text("gesenkt\n", "utf-8")
    (repo / "fremd.txt").write_text("fremd\n", "utf-8")
    meldung = pruefstempel.stemple_lauf(repo, vorher, ["a.txt"])
    assert meldung == "nicht gestempelt: während des Laufs geändert: fremd.txt"
    assert not pruefstempel.ist_gestempelt(repo, vorher)
    assert not pruefstempel.ist_gestempelt(repo, pruefstempel.arbeitsbaum(repo))


def test_unveraenderter_lauf_stempelt_genau_seinen_baum(repo):
    baum = pruefstempel.arbeitsbaum(repo)
    assert pruefstempel.stemple_lauf(repo, baum, []) == f"gestempelt {baum[:12]}"
    assert sorted(p.name for p in pruefstempel.stempel_ordner(repo).iterdir()) == [baum]


def test_stemple_lauf_ohne_baum_meldet_es(repo, tmp_path):
    assert pruefstempel.stemple_lauf(repo, None, []).startswith("nicht gestempelt")
    meldung = pruefstempel.stemple_lauf(tmp_path, "a" * 40, [])
    assert meldung.startswith("nicht gestempelt")


def test_baum_ausserhalb_eines_repos_ist_nichts(tmp_path):
    assert pruefstempel.baum_oder_nichts(tmp_path) is None


def test_nur_loeschungen_brauchen_keine_pruefung():
    leer = "0" * 40
    loeschen = [f"(delete) {leer} refs/heads/alt {'a' * 40}"]
    schieben = [f"refs/heads/main {'b' * 40} refs/heads/main {'a' * 40}"]
    assert pruefstempel.ist_loeschung(loeschen)
    assert not pruefstempel.ist_loeschung(schieben)
    assert not pruefstempel.ist_loeschung(loeschen + schieben)
    assert not pruefstempel.ist_loeschung([])


def _zeile(sha):
    return [f"refs/heads/main {sha} refs/heads/main {'a' * 40}"]


@pytest.fixture()
def mit_ursprung(repo, tmp_path):
    ursprung = tmp_path / "ursprung.git"
    _git(tmp_path, "clone", "-q", "--bare", str(repo), str(ursprung))
    _git(repo, "remote", "add", "origin", str(ursprung))
    return ursprung


def test_vor_push_verlangt_dass_head_gepusht_wird(repo, mit_ursprung):
    kopf = _git(repo, "rev-parse", "HEAD")
    alt = _git(repo, "rev-parse", "HEAD~1")
    assert pruefstempel.vor_push(repo, _zeile(kopf)) is None
    code, meldung = pruefstempel.vor_push(repo, _zeile(alt))
    assert code == 1
    assert meldung.startswith(f"pre-push: gepusht wird nicht HEAD ({alt[:7]})")


@pytest.mark.parametrize("art", ["geaendert", "neu", "vorgemerkt"])
def test_vor_push_verlangt_einen_arbeitsstand_gleich_head(repo, mit_ursprung, art):
    if art == "neu":
        (repo / "neu.py").write_text("x = 1\n", "utf-8")
    else:
        (repo / "a.txt").write_text("anders\n", "utf-8")
    if art == "vorgemerkt":
        _git(repo, "add", "a.txt")
    code, meldung = pruefstempel.vor_push(repo, _zeile(_git(repo, "rev-parse", "HEAD")))
    assert code == 1
    assert meldung.startswith("pre-push: Arbeitsstand weicht von HEAD ab")


def test_vor_push_verlangt_dass_head_origin_main_enthaelt(repo, mit_ursprung, tmp_path):
    ursprung = mit_ursprung
    zeile = _zeile(_git(repo, "rev-parse", "HEAD"))
    assert pruefstempel.vor_push(repo, zeile) is None
    anderer = tmp_path / "anderer"
    _git(tmp_path, "clone", "-q", str(ursprung), str(anderer))
    _commit(anderer, "neu.txt", "neu\n")
    _git(anderer, "push", "-q", "origin", "HEAD:main")
    code, meldung = pruefstempel.vor_push(repo, zeile)
    assert code == 1
    assert "git pull --rebase origin main" in meldung
    loeschen = [f"(delete) {'0' * 40} refs/heads/alt {'a' * 40}"]
    assert pruefstempel.vor_push(repo, loeschen) == (
        0,
        "pre-push: nur Löschungen, keine Prüfung",
    )


def test_vor_push_ohne_origin_ist_rot(repo):
    zeile = _zeile(_git(repo, "rev-parse", "HEAD"))
    code, meldung = pruefstempel.vor_push(repo, zeile)
    assert code == 1
    assert meldung.startswith("pre-push: origin/main nicht abrufbar")
