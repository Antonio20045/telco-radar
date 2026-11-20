"""Das Sammelbudget wird je Anbieter aufgeteilt, nicht verfüttert.

BEFUND 16.11.2026 (gemessen aus den Tagesdateien 13.–15.11. und dem Log des
Geräte-Laufs 43698541511): o2 lieferte an drei Tagen 2216, 1012 und 1108 Zeilen
aus einem Katalog von rund 2.500 Preisen. Die Zahl hing nicht an o2, sondern
daran, wie lange die Händler VOR o2 gebraucht hatten: das Budget des
Tageslaufs (``--frist 1500``) war eine gemeinsame Weide, auf der jeder Anbieter
alles nehmen durfte, solange jedem nach ihm noch ``MINDEST_JE_ANBIETER``
blieb. Der späte o2 bekam, was übrig war.

Diese Datei nagelt die Aufteilung fest: jeder crawlende Anbieter hat einen
benannten Anteil (``sammelanteile``) nach seinem Bedarf (``sammelbedarf``),
die Summe der Anteile ist das Gesamtbudget und nie mehr (CLAUDE.md Regel 8),
und o2 bekommt mit großem Katalog mehr als mit kleinem.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from telco_radar.collect.geraete.sammelbudget import (
    MINDEST_JE_ANBIETER,
    sammelanteile,
    sammelbedarf,
)
from telco_radar.geraete_config import Anbieter, Einstieg, lade_quellen

_WURZEL = Path(__file__).resolve().parents[1]
_BUDGET = 1500.0


def _anbieter(name: str, **felder) -> Anbieter:
    return Anbieter(
        name=name,
        methode="ldjson",
        basis_url=f"https://{name}.invalid",
        einstiege=[Einstieg(url=f"https://{name}.invalid/kat", kind="static")],
        **felder,
    )


def test_der_bedarf_waechst_mit_dem_katalog():
    klein = _anbieter("klein", max_produkte=10, rate_limit_sekunden=2)
    gross = _anbieter("gross", max_produkte=500, rate_limit_sekunden=2)

    assert sammelbedarf(gross) > sammelbedarf(klein)
    assert sammelbedarf(klein) >= MINDEST_JE_ANBIETER


def test_die_gemessene_angabe_schlaegt_die_schaetzung():
    """``sammelbedarf_sekunden`` aus der Konfiguration ist gemessen, die
    Schätzung aus ``max_produkte`` ist nur eine Schätzung."""
    geschaetzt = _anbieter("x", max_produkte=60, rate_limit_sekunden=2)
    erklaert = _anbieter(
        "x", max_produkte=60, rate_limit_sekunden=2, sammelbedarf_sekunden=1140
    )

    assert sammelbedarf(geschaetzt) == pytest.approx(122.0)
    assert sammelbedarf(erklaert) == pytest.approx(1140.0)


def test_die_summe_der_anteile_ist_das_gesamtbudget():
    anbieter = [
        _anbieter("a", max_produkte=10),
        _anbieter("b", max_produkte=60, rate_limit_sekunden=10),
        _anbieter("c", max_produkte=500),
    ]

    anteile = sammelanteile(anbieter, _BUDGET)

    assert sum(anteile.values()) == pytest.approx(_BUDGET)
    assert len(anteile) == 3


def test_kein_anbieter_geht_leer_aus():
    """Auch der kleinste bekommt seinen Sockel - ein Anteil von null wäre
    eine stille Abschaltung."""
    anbieter = [_anbieter("winzig", max_produkte=1)] + [
        _anbieter(f"riese{i}", max_produkte=2000) for i in range(5)
    ]

    anteile = sammelanteile(anbieter, _BUDGET)

    assert anteile["winzig"] == pytest.approx(MINDEST_JE_ANBIETER)
    assert min(anteile.values()) > 0


def test_bei_zu_kleinem_budget_teilen_alle_gleich():
    """Reicht das Budget nicht einmal für die Sockel, bekommt jeder denselben
    Bruchteil - und die Summe bleibt das Budget."""
    anbieter = [_anbieter(f"a{i}", max_produkte=60) for i in range(10)]

    anteile = sammelanteile(anbieter, 100.0)

    assert sum(anteile.values()) == pytest.approx(100.0)
    assert set(round(w, 6) for w in anteile.values()) == {10.0}


def test_ohne_budget_gibt_es_keine_anteile():
    assert sammelanteile([_anbieter("a")], 0.0) == {}
    assert sammelanteile([], _BUDGET) == {}


def test_o2_bekommt_mit_grossem_katalog_mehr_als_mit_kleinem():
    """Die Kernaussage des Befunds: der Anteil folgt dem Katalog."""
    andere = [_anbieter(f"haendler{i}", max_produkte=60) for i in range(9)]
    klein = _anbieter("o2", max_produkte=60, rate_limit_sekunden=2)
    gross = _anbieter("o2", sammelbedarf_sekunden=1140, rate_limit_sekunden=2)

    mit_klein = sammelanteile([*andere, klein], _BUDGET)["o2"]
    mit_gross = sammelanteile([*andere, gross], _BUDGET)["o2"]

    assert mit_gross > mit_klein
    assert mit_gross >= MINDEST_JE_ANBIETER


def test_die_ausgelieferte_konfiguration_nennt_o2_bedarf():
    """o2 steht mit seinem gerechneten Bedarf in der Konfiguration; die
    Schätzung aus ``max_produkte`` wäre der Anteil eines Händlers."""
    quellen = lade_quellen(_WURZEL)
    o2 = next(a for a in quellen.anbieter if a.name == "o2")

    assert o2.sammelbedarf_sekunden is not None
    assert sammelbedarf(o2) > (len(o2.crawled_einstiege) + o2.max_produkte) * 2


def test_die_ausgelieferte_konfiguration_nennt_telekom_bedarf():
    """BEFUND 20.11.2026 (arbeit/ursache-telekom-2011.md): die Schaetzung aus
    ``max_produkte`` (15) lag bei rund 176-210 s - das deckt kaum die eigene
    Buendel-Vertiefung (21 Abrufe a 10 s, gemessen 202 s) und liess keine
    Reserve fuer zusaetzliche Pflichtmodell-Seiten je Tarif."""
    quellen = lade_quellen(_WURZEL)
    telekom = next(a for a in quellen.anbieter if a.name == "Telekom")

    assert telekom.sammelbedarf_sekunden is not None
    assert sammelbedarf(telekom) > (len(telekom.crawled_einstiege) + telekom.max_produkte) * telekom.rate_limit_sekunden
    # Telekoms eigener Katalog ist kleiner als o2s - der Anteil bleibt darunter
    # (siehe test_die_ausgelieferten_anteile_bleiben_im_budget).
    o2 = next(a for a in quellen.anbieter if a.name == "o2")
    assert sammelbedarf(telekom) < sammelbedarf(o2)


def test_die_ausgelieferte_konfiguration_nennt_congstar_bedarf():
    """BEFUND 18./19.11.2026 (arbeit/ursache-je-anbieter-1818.md): die
    Schätzung aus ``max_produkte`` × ``rate_limit_sekunden`` lag praktisch auf
    ``MINDEST_JE_ANBIETER`` - zu knapp fuer die reale Seitenzahl, deshalb
    blieben Messungen älter als ``ALT_AB_TAGEN``."""
    quellen = lade_quellen(_WURZEL)
    congstar = next(a for a in quellen.anbieter if a.name == "congstar")

    assert congstar.sammelbedarf_sekunden is not None
    assert sammelbedarf(congstar) > MINDEST_JE_ANBIETER


def test_die_ausgelieferten_anteile_bleiben_im_budget():
    """Gegenprobe an der echten Anbieterliste: kein Anteil über dem Budget,
    die Summe genau das Budget - sonst verspräche der Lauf Zeit, die der Job
    nicht hat (CLAUDE.md Regel 8)."""
    from telco_radar.collect.geraete import ADAPTER

    quellen = lade_quellen(_WURZEL)
    crawler = [
        a
        for a in sorted(quellen.anbieter, key=lambda a: (a.crawl_rang, a.name))
        if a.crawlbar and ADAPTER.get(a.methode) is not None
    ]

    anteile = sammelanteile(crawler, _BUDGET)

    assert len(anteile) == len(crawler)
    assert sum(anteile.values()) == pytest.approx(_BUDGET)
    assert max(anteile.values()) <= _BUDGET
    assert anteile["o2"] == max(anteile.values()), (
        "o2 hat den größten Bedarf und muss den größten Anteil bekommen: "
        f"{sorted(anteile.items(), key=lambda p: -p[1])[:3]}"
    )
