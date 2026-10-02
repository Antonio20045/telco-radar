"""Kanarienvogel der Prüfleiter, nur über ihren Pfad gesammelt.

Die Leiter verlangt, dass der erste Test rot und der zweite grün gemeldet wird. Schreibt
ein Hook oder Plugin Ergebnisse um, fällt das hier zuerst auf.
"""


def test_muss_scheitern():
    raise AssertionError("muss rot sein")


def test_muss_bestehen():
    pass
