"""Host-Drosselung der Sammelphase (collect/http.py::HostGate).

Warum das eigene Tests braucht: das Gate ist die Bedingung dafuer, dass
collect_max_workers ueberhaupt auf 64 stehen darf. Faellt es still aus, laeuft
der naechste Lauf mit 64 gleichzeitigen Verbindungen auf dieselbe Domain und
handelt sich 429/403 ein - und zwar erst in Produktion, weil lokal niemand
1000 Quellen abruft. Die Grenze wird deshalb hier gemessen, nicht geglaubt.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from telco_radar.collect.http import HostGate


class Zaehler:
    """Merkt sich, wie viele Threads gleichzeitig im Gate waren."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.jetzt = 0
        self.maximum = 0

    def betreten(self) -> None:
        with self.lock:
            self.jetzt += 1
            self.maximum = max(self.maximum, self.jetzt)

    def verlassen(self) -> None:
        with self.lock:
            self.jetzt -= 1


def _durchlauf(gate: HostGate, urls: list[str], arbeit: float = 0.05) -> Zaehler:
    z = Zaehler()

    def eine(url: str) -> None:
        with gate.slot(url):
            z.betreten()
            time.sleep(arbeit)
            z.verlassen()

    with ThreadPoolExecutor(max_workers=len(urls)) as pool:
        list(pool.map(eine, urls))
    return z


def test_gleicher_host_wird_begrenzt():
    gate = HostGate(max_parallel=2, min_interval=0.0)
    urls = [f"https://beispiel.de/feed/{i}" for i in range(8)]
    assert _durchlauf(gate, urls).maximum <= 2


def test_verschiedene_hosts_laufen_parallel():
    """Die Grenze gilt je Host - sonst waere sie nur ein kleinerer Pool."""
    gate = HostGate(max_parallel=1, min_interval=0.0)
    urls = [f"https://host{i}.de/feed" for i in range(8)]
    assert _durchlauf(gate, urls).maximum == 8


def test_www_zaehlt_als_derselbe_host():
    """https://www.x.de und https://x.de sind derselbe Server - sonst
    umgeht jede Quelle die Grenze durch die Schreibweise ihrer URL."""
    gate = HostGate(max_parallel=1, min_interval=0.0)
    urls = ["https://www.beispiel.de/a", "https://beispiel.de/b",
            "https://www.beispiel.de/c"]
    assert _durchlauf(gate, urls).maximum == 1


def test_mindestabstand_zwischen_zwei_abrufen():
    gate = HostGate(max_parallel=4, min_interval=0.2)
    t0 = time.monotonic()
    _durchlauf(gate, [f"https://beispiel.de/{i}" for i in range(4)], arbeit=0.0)
    # 4 Abrufe, 3 Abstaende a 0,2 s
    assert time.monotonic() - t0 >= 0.55


def test_abstand_gilt_nicht_ueber_hosts_hinweg():
    gate = HostGate(max_parallel=4, min_interval=0.3)
    t0 = time.monotonic()
    _durchlauf(gate, [f"https://host{i}.de/feed" for i in range(4)], arbeit=0.0)
    assert time.monotonic() - t0 < 0.3


def test_slot_wird_auch_bei_fehler_freigegeben():
    """Ohne das haette EIN kaputter Abruf den Host dauerhaft blockiert."""
    gate = HostGate(max_parallel=1, min_interval=0.0)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            with gate.slot("https://beispiel.de/feed"):
                raise RuntimeError("Abruf gescheitert")
    # Wenn das Semaphor leckt, laeuft der naechste Abruf in einen Deadlock.
    with gate.slot("https://beispiel.de/feed"):
        pass


def test_standardgate_drosselt_nicht():
    """Tests und Einzelabrufe sollen ohne Konfiguration laufen wie bisher."""
    from telco_radar.collect.http import active_gate
    assert active_gate().max_parallel > 1000


# ======================================================================== #
# Harte Frist je Quelle.
#
# Im Lauf #75 brauchte EINE tote Quelle (KT, timeout_seconds: 30 mal zwei
# User-Agents mal drei Versuche plus Backoff) 302,6 s - und die gesamte
# Sammelphase dauerte 303,7 s. Gegen den langsamsten Einzelfall hilft keine
# Parallelitaet.
# ======================================================================== #

def test_frist_bricht_die_wiederholungen_ab(monkeypatch):
    import httpx
    from telco_radar.collect import http as http_mod

    versuche = []

    def _langsam(url, **kw):
        versuche.append(url)
        time.sleep(0.15)
        raise httpx.ConnectError("nicht erreichbar")

    monkeypatch.setattr(http_mod.httpx, "get", _langsam)
    # Ohne Frist: 2 User-Agents x 3 Versuche = 6 Abrufe (plus 13 s Backoff)
    with http_mod.deadline(0.3):
        with pytest.raises(httpx.HTTPError):
            http_mod.fetch("https://tot.de/feed", {"timeout_seconds": 1})
    assert len(versuche) <= 3, versuche


def test_ohne_frist_bleibt_die_ausdauer_erhalten(monkeypatch):
    """Fuer eine ausgewaehlte Quelle im Lauf ist die Leiter richtig - ein
    verlorener Abruf kostet dort eine Woche."""
    import httpx
    from telco_radar.collect import http as http_mod

    versuche = []

    def _kaputt(url, **kw):
        versuche.append(url)
        raise httpx.ConnectError("nicht erreichbar")

    monkeypatch.setattr(http_mod.httpx, "get", _kaputt)
    monkeypatch.setattr(http_mod, "_BACKOFF_WAITS", (0.0, 0.0))
    with pytest.raises(httpx.HTTPError):
        http_mod.fetch("https://tot.de/feed", {"timeout_seconds": 1})
    assert len(versuche) == 6


def test_frist_gilt_nur_im_eigenen_thread():
    """threading.local: eine Quelle darf die Frist einer anderen nicht erben."""
    from telco_radar.collect import http as http_mod

    gesehen = []

    def _pruefe():
        gesehen.append(http_mod._frist_abgelaufen())

    with http_mod.deadline(0.001):
        time.sleep(0.01)
        assert http_mod._frist_abgelaufen()
        t = threading.Thread(target=_pruefe)
        t.start()
        t.join()
    assert gesehen == [False]
    assert not http_mod._frist_abgelaufen()
