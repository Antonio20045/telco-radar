"""Kanarienvogel der Prüfleiter, nur über ihren Pfad gesammelt.

Die Leiter verlangt, dass der erste Test rot und der zweite grün gemeldet wird. Schreibt
ein Hook oder Plugin Ergebnisse um, fällt das hier zuerst auf. Die drei letzten
greifen auf den Bestand, ins Netz und auf Quelltext und müssen an der Regel aus
``conftest.py`` scheitern.
"""

import socket
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
BESTAND = WURZEL / "data" / "state" / "seen.jsonl"
QUELLTEXT = WURZEL / "src" / "telco_radar" / "models.py"


def test_muss_scheitern():
    raise AssertionError("muss rot sein")


def test_muss_bestehen():
    pass


def test_bestand_muss_scheitern():
    BESTAND.read_bytes()


def test_netz_muss_scheitern():
    socket.getaddrinfo("example.com", 443)


def test_quelltext_muss_scheitern():
    QUELLTEXT.read_bytes()
