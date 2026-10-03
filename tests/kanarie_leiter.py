"""Kanarienvogel der Prüfleiter, nur über ihren Pfad gesammelt.

Die Leiter verlangt, dass der erste Test rot und der zweite grün gemeldet wird. Schreibt
ein Hook oder Plugin Ergebnisse um, fällt das hier zuerst auf. Die beiden letzten
greifen auf den Bestand und ins Netz und müssen an der Regel aus ``conftest.py``
scheitern.
"""

import socket
from pathlib import Path

BESTAND = Path(__file__).resolve().parents[1] / "data" / "state" / "seen.jsonl"


def test_muss_scheitern():
    raise AssertionError("muss rot sein")


def test_muss_bestehen():
    pass


def test_bestand_muss_scheitern():
    BESTAND.read_bytes()


def test_netz_muss_scheitern():
    socket.getaddrinfo("example.com", 443)
