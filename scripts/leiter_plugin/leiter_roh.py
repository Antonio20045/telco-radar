"""pytest-Plugin der Prüfleiter: hält fest, wie jede Testfunktion selbst endete.

Je Test entsteht eine Zeile ``ok <nodeid>``, ``fehler <nodeid>`` oder ``fremd <nodeid>``
in einer Datei je Prozess unter dem Ordner aus ``TELCO_LEITER_ROH``. ``fremd`` heißt,
dass die Funktion schon vor der Leiter umhüllt oder ersetzt war: Eine Hülle innerhalb
der Aufzeichnung könnte ein Scheitern schlucken, ohne dass es auffiele. Die Leiter hält
jeden als bestanden gemeldeten Test dagegen und jede fremde Funktion für rot.

Daneben entsteht je Test, dessen Ablauf pytest beginnt, eine Zeile ``lief <nodeid>``
in einer eigenen Datei je Prozess. Die Leiter hält diese Menge gegen die rohe Sammlung
ohne Projekteinstellungen und conftest: Ein Test, der dort steht und hier fehlt, wurde
abgewählt.
"""

import ast
import functools
import os

import pytest

ROH_VARIABLE = "TELCO_LEITER_ROH"


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(items):
    """Umhüllt jede Testfunktion, nachdem alle anderen Plugins gesammelt haben."""
    ordner = os.environ.get(ROH_VARIABLE)
    if not ordner:
        return
    datei = os.path.join(ordner, f"{os.getpid()}.txt")
    for item in items:
        if isinstance(item, pytest.Function):
            art = "ok" if _echt(item) else "fremd"
            item.obj = _aufgezeichnet(item.obj, item.nodeid, datei, art)


def pytest_runtest_logstart(nodeid, location):
    """Hält jeden Test fest, dessen Ablauf pytest beginnt, ob bestanden oder nicht."""
    ordner = os.environ.get(ROH_VARIABLE)
    if ordner:
        _schreibe(os.path.join(ordner, f"{os.getpid()}.lief"), f"lief {nodeid}\n")


def _echt(item):
    """Wahr, wenn ``item.obj`` die Funktion ist, die in der Testdatei steht.

    Verlangt werden ihr Code aus dieser Datei unter ihrem Namen und an der Zeile
    ihres ``def``, die Globalen des Testmoduls und kein ``__wrapped__``.
    """
    funktion = getattr(item.obj, "__func__", item.obj)
    code = getattr(funktion, "__code__", None)
    modul = getattr(item, "module", None)
    return (
        code is not None
        and not hasattr(funktion, "__wrapped__")
        and code.co_name == item.originalname
        and code.co_filename == str(item.path)
        and getattr(funktion, "__globals__", None) is getattr(modul, "__dict__", 0)
        and code.co_firstlineno in _def_zeilen(str(item.path), item.originalname)
    )


@functools.cache
def _def_zeilen(pfad, name):
    with open(pfad, encoding="utf-8") as datei:
        baum = ast.parse(datei.read())
    return {
        min([k.lineno, *(d.lineno for d in k.decorator_list)])
        for k in ast.walk(baum)
        if isinstance(k, ast.FunctionDef | ast.AsyncFunctionDef) and k.name == name
    }


def _aufgezeichnet(funktion, nodeid, datei, art):
    @functools.wraps(funktion)
    def testfunktion(*args, **kwargs):
        try:
            ergebnis = funktion(*args, **kwargs)
        except BaseException:
            _schreibe(datei, f"{'fremd' if art == 'fremd' else 'fehler'} {nodeid}\n")
            raise
        _schreibe(datei, f"{art} {nodeid}\n")
        return ergebnis

    return testfunktion


def _schreibe(datei, zeile):
    kennung = os.open(datei, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(kennung, zeile.encode("utf-8"))
    finally:
        os.close(kennung)
