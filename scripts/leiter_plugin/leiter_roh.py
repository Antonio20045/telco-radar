"""pytest-Plugin der Prüfleiter: hält fest, wie jede Testfunktion selbst endete.

Je Test entsteht eine Zeile ``ok <nodeid>`` oder ``fehler <nodeid>`` in einer Datei
je Prozess unter dem Ordner aus ``TELCO_LEITER_ROH``. Die Leiter hält jeden als
bestanden gemeldeten Test dagegen, so fällt ein umgeschriebenes Ergebnis auf.
"""

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
            item.obj = _aufgezeichnet(item.obj, item.nodeid, datei)


def _aufgezeichnet(funktion, nodeid, datei):
    @functools.wraps(funktion)
    def testfunktion(*args, **kwargs):
        try:
            ergebnis = funktion(*args, **kwargs)
        except BaseException:
            _schreibe(datei, f"fehler {nodeid}\n")
            raise
        _schreibe(datei, f"ok {nodeid}\n")
        return ergebnis

    return testfunktion


def _schreibe(datei, zeile):
    kennung = os.open(datei, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(kennung, zeile.encode("utf-8"))
    finally:
        os.close(kennung)
