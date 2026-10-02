import importlib.util
import subprocess
from pathlib import Path

_PFAD = Path(__file__).resolve().parents[1] / "scripts" / "ast_gleich.py"
_spec = importlib.util.spec_from_file_location("ast_gleich", _PFAD)
ast_gleich = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ast_gleich)


def test_umformatierter_code_hat_denselben_baum():
    vorher = "x = {'a':1,\n  'b' : 2}\ndef f( a ):\n    return a\n"
    nachher = 'x = {"a": 1, "b": 2}\n\n\ndef f(a):\n    return a\n'
    assert ast_gleich.baum_dump(vorher) == ast_gleich.baum_dump(nachher)


def test_neu_eingerueckter_docstring_hat_denselben_baum():
    vorher = 'def f():\n    """Kopf.\n\n        Text.   \n    """\n'
    nachher = 'def f():\n    """Kopf.\n\n    Text.\n    """\n'
    assert ast_gleich.baum_dump(vorher) == ast_gleich.baum_dump(nachher)


def test_geaenderter_wert_ergibt_anderen_baum():
    assert ast_gleich.baum_dump("x = 1\n") != ast_gleich.baum_dump("x = 2\n")


def test_geaenderter_text_einer_normalen_zeichenkette_ergibt_anderen_baum():
    vorher = 'def f():\n    x = "a  "\n'
    nachher = 'def f():\n    x = "a"\n'
    assert ast_gleich.baum_dump(vorher) != ast_gleich.baum_dump(nachher)


def test_geaenderter_docstringtext_ergibt_anderen_baum():
    vorher = 'def f():\n    """Kopf."""\n'
    nachher = 'def f():\n    """Anderer Kopf."""\n'
    assert ast_gleich.baum_dump(vorher) != ast_gleich.baum_dump(nachher)


def test_relative_einrueckung_im_docstring_zaehlt():
    vorher = 'def f():\n    """Kopf.\n\n    >>> g()\n          1\n    """\n'
    nachher = 'def f():\n    """Kopf.\n\n    >>> g()\n    1\n    """\n'
    assert ast_gleich.baum_dump(vorher) != ast_gleich.baum_dump(nachher)


def _repo(tmp_path, monkeypatch):
    def git(*argumente):
        subprocess.run(
            ["git", *argumente], cwd=tmp_path, check=True, capture_output=True
        )

    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a b.py").write_text("x = {'a':1}\n", encoding="utf-8")
    (tmp_path / "pkg" / "ä.py").write_text("y = 1\n", encoding="utf-8")
    (tmp_path / "weg.py").write_text("z = 1\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "start")
    monkeypatch.chdir(tmp_path / "pkg")
    return git


def test_umformatierung_aus_unterordner_ist_gleich_und_exit_null(tmp_path, monkeypatch):
    _repo(tmp_path, monkeypatch)
    (tmp_path / "pkg" / "a b.py").write_text('x = {"a": 1}\n', encoding="utf-8")
    assert ast_gleich.vergleiche("HEAD", None) == {"pkg/a b.py": "gleich"}
    assert ast_gleich.main(["HEAD"]) == 0


def test_echte_aenderung_neue_und_entfernte_datei_sind_rot(tmp_path, monkeypatch):
    git = _repo(tmp_path, monkeypatch)
    (tmp_path / "pkg" / "ä.py").write_text("y = 2\n", encoding="utf-8")
    (tmp_path / "weg.py").unlink()
    (tmp_path / "neu.py").write_text("n = 1\n", encoding="utf-8")
    git("add", "-N", "neu.py")
    befund = ast_gleich.vergleiche("HEAD", None)
    assert befund == {"pkg/ä.py": "verschieden", "weg.py": "entfernt", "neu.py": "neu"}
    assert ast_gleich.main(["HEAD"]) == 1


def test_leerer_bereich_ist_kein_nachweis(tmp_path, monkeypatch):
    _repo(tmp_path, monkeypatch)
    assert ast_gleich.main(["HEAD", "HEAD"]) == 1
