"""Klick-Tageslauf je Anbieter (``collect.geraete.klicktageslauf``), ohne Browser.

Die Seiten sind die echten aus ``config/klick_tageslauf.yaml``; der Crawler ist
gefälscht und liefert je Seite einen vorbereiteten Klicklauf, die Uhr ist eine Zahl,
die nur der Crawler weiterstellt. Erfasste Werte stammen aus der echten
o2-Lesung (``tests/klickergebnisse.py``). Geprüft: Rotation (nie gelesen zuerst, dann
die älteste), Zeitbudget gegen die Restzeit des Jobs, Abbruch nach Bot-Schutz und der
Weg der Ergebnisdatei bis zu den Rohsätzen.
"""

from __future__ import annotations

import importlib.util
import json
from dataclasses import replace

import pytest
from bestand_pfad import lese_wurzel
from klickergebnisse import O2_SEITE, WURZEL, erfasst, o2_lesung

from telco_radar.collect.geraete.klickergebnis import (
    SEITE_NICHT_BESUCHT,
    lies_ergebnisse,
    schreibe,
)
from telco_radar.collect.geraete.klickkarte import lade_klickkarte
from telco_radar.collect.geraete.klicklauf import (
    LAUF_GELESEN,
    LAUF_GESPERRT,
    LAUF_GESTOERT,
    Klicklauf,
    abruf_gestoert,
)
from telco_radar.collect.geraete.klickparallel import TAGESLAUF_WORKFLOWS, aus_umgebung
from telco_radar.collect.geraete.klickrohsatz import LUECKE_SEITE, ausbeute
from telco_radar.collect.geraete.klicktageslauf import (
    GRUND_BUDGET,
    GRUND_NACH_STOERUNG,
    GRUND_PARALLEL,
    MINDESTZEIT_SEITE_S,
    RESERVE_S,
    ZEIT_JE_SEITE_S,
    budget_ende,
    fahre,
)
from telco_radar.collect.geraete.klickziele import (
    TAGESDATEI,
    ErkundungszielFehler,
    lade_ziele,
)
from telco_radar.geraete_config import lade_katalog

HEUTE = "2026-09-29"
MINUTE = 60.0
_SKRIPT = WURZEL / "scripts" / "klick_tageslauf.py"


@pytest.fixture(scope="module")
def ziele():
    alle = lade_ziele(lese_wurzel(), TAGESDATEI, hoechste=None)
    return {z.schluessel: z for z in alle}


@pytest.fixture(scope="module")
def o2(ziele):
    return ziele["o2"]


@pytest.fixture(scope="module")
def karte():
    return lade_klickkarte(WURZEL / "config" / "klickkarten" / "o2.yaml")


@pytest.fixture(scope="module")
def gelesen_o2():
    """Eine echte erfasste Kombination (o2, 256 GB, M Plus, 36 Raten)."""
    return erfasst(o2_lesung("256 GB", "O2 Mobile Unlimited M Plus", 36))


class Uhr:
    """Monotone Uhr, die nur der gefälschte Crawler weiterstellt."""

    def __init__(self) -> None:
        self.jetzt = 0.0

    def __call__(self) -> float:
        return self.jetzt


class Crawler:
    """Liest jede Seite in ``dauer`` Sekunden; ``status`` je Adresse, sonst gelesen."""

    def __init__(self, uhr, kombination, dauer=MINUTE, status=None) -> None:
        self.uhr = uhr
        self.kombination = kombination
        self.dauer = dauer
        self.status = status or {}
        self.aufrufe: list[tuple[str, float]] = []

    def __call__(self, seite, ende):
        self.aufrufe.append((seite.adresse, ende))
        self.uhr.jetzt += self.dauer
        status = self.status.get(seite.adresse, LAUF_GELESEN)
        if status == LAUF_GESTOERT:
            return Klicklauf("o2", seite.adresse, status, abruf_gestoert(403), 403)
        if status == LAUF_GESPERRT:
            return Klicklauf("o2", seite.adresse, status, "robots.txt verbietet", None)
        return Klicklauf("o2", seite.adresse, ergebnisse=[self.kombination])


def _fahre(o2, karte, crawler, uhr, ende=10**6, gelesen=None):
    return fahre(
        o2, karte, "o2.yaml", crawler, HEUTE, ende, gelesen=gelesen or {}, uhr=uhr
    )


def test_tagesdatei_hat_alle_anbieter_mit_karte_und_keine_seitengrenze(ziele):
    assert list(ziele) == ["o2", "vodafone", "1und1", "telekom", "congstar"]
    for schluessel in ziele:
        assert (WURZEL / "config" / "klickkarten" / f"{schluessel}.yaml").is_file()
    assert O2_SEITE.adresse in {s.adresse for s in ziele["o2"].seiten}
    assert len(ziele["telekom"].seiten) == 7
    with pytest.raises(ErkundungszielFehler, match="höchstens 2"):
        lade_ziele(lese_wurzel(), TAGESDATEI)


def test_plan_nennt_jeden_anbieter_mit_karte(capsys):
    spec = importlib.util.spec_from_file_location("klick_tageslauf", _SKRIPT)
    skript = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(skript)

    assert skript.main(["--plan", "--root", str(lese_wurzel())]) == 0
    assert json.loads(capsys.readouterr().out) == [
        "o2",
        "vodafone",
        "1und1",
        "telekom",
        "congstar",
    ]
    assert skript.main(["--root", str(lese_wurzel()), "--anbieter", "o2,telekom"]) == 2


def test_rotation_nie_gelesen_zuerst_dann_die_aelteste(o2, karte, gelesen_o2):
    a, b, c, d, e, f = (s.adresse for s in o2.seiten)
    gelesen = {a: "2026-09-28", b: "2026-09-26", c: "2026-09-27", e: "2026-09-25"}
    uhr = Uhr()
    crawler = Crawler(uhr, gelesen_o2)

    daten = _fahre(o2, karte, crawler, uhr, gelesen=gelesen)

    assert [adresse for adresse, _ in crawler.aufrufe] == [d, f, e, b, c, a]
    assert daten["laufstatus"] == LAUF_GELESEN and daten["ueberfaellig"] == []


def test_zeitbudget_rechnet_gegen_die_restzeit_des_jobs(o2, karte, gelesen_o2):
    """Job 60 min, 2 min schon verstrichen, Reserve 8 min: 50 min für Seiten. Jede
    Seite braucht 20 min; die dritte beginnt mit 10 min Rest und endet an der Grenze."""
    ende = budget_ende(60 * MINUTE, 2 * MINUTE, 0.0)
    assert ende == 60 * MINUTE - 2 * MINUTE - RESERVE_S == 50 * MINUTE
    uhr = Uhr()
    crawler = Crawler(uhr, gelesen_o2, dauer=20 * MINUTE)
    gelesen = {s.adresse: "2026-09-25" for s in o2.seiten[3:]}

    daten = _fahre(o2, karte, crawler, uhr, ende, gelesen)

    grenzen = [grenze for _, grenze in crawler.aufrufe]
    assert grenzen == [ZEIT_JE_SEITE_S, 20 * MINUTE + ZEIT_JE_SEITE_S, ende]
    seiten = daten["seiten"]
    assert [s["status"] for s in seiten] == [LAUF_GELESEN] * 3 + [
        SEITE_NICHT_BESUCHT
    ] * 3
    assert {s["grund"] for s in seiten[3:]} == {f"{GRUND_BUDGET}: noch 0 s"}
    assert daten["laufstatus"] == LAUF_GELESEN
    assert (daten["zeitbudget_sekunden"], daten["dauer_sekunden"]) == (3000, 3600.0)
    assert daten["ueberfaellig"] == [s.adresse for s in o2.seiten[3:]]


def test_ohne_mindestzeit_beginnt_keine_seite(o2, karte, gelesen_o2):
    uhr = Uhr()
    crawler = Crawler(uhr, gelesen_o2)

    daten = _fahre(o2, karte, crawler, uhr, ende=MINDESTZEIT_SEITE_S - 1)

    assert crawler.aufrufe == []
    assert daten["laufstatus"] == "nicht_gelesen"
    assert daten["grund"] == f"{GRUND_BUDGET}: noch {MINDESTZEIT_SEITE_S - 1} s"
    assert len(daten["ueberfaellig"]) == len(o2.seiten)


def test_bot_schutz_beendet_den_anbieter(o2, karte, gelesen_o2):
    zweite = o2.seiten[1].adresse
    uhr = Uhr()
    crawler = Crawler(uhr, gelesen_o2, status={zweite: LAUF_GESTOERT})

    daten = _fahre(o2, karte, crawler, uhr)

    assert len(crawler.aufrufe) == 2
    assert daten["laufstatus"] == LAUF_GESTOERT
    assert daten["grund"] == f"{zweite}: Abruf gestört (HTTP 403)"
    rest = daten["seiten"][2:]
    assert {s["status"] for s in rest} == {SEITE_NICHT_BESUCHT}
    assert {s["grund"] for s in rest} == {
        f"{GRUND_NACH_STOERUNG}: Abruf gestört (HTTP 403)"
    }


def test_gesperrte_seite_beendet_den_anbieter_nicht(o2, karte, gelesen_o2):
    uhr = Uhr()
    crawler = Crawler(uhr, gelesen_o2, status={o2.seiten[1].adresse: LAUF_GESPERRT})

    daten = _fahre(o2, karte, crawler, uhr)

    assert len(crawler.aufrufe) == len(o2.seiten)
    assert daten["laufstatus"] == LAUF_GELESEN
    assert daten["ueberfaellig"] == [o2.seiten[1].adresse]


def test_ergebnisdatei_traegt_bis_zu_den_rohsaetzen(o2, karte, gelesen_o2, tmp_path):
    """iPhone 17 Pro gelesen (die echte Lesung gehört zu dieser Seite), die zweite
    Seite gesperrt: ein Rohsatz, eine benannte Lücke."""
    ziel = replace(o2, seiten=o2.seiten[:2])
    assert ziel.seiten[0].adresse == O2_SEITE.adresse
    uhr = Uhr()
    crawler = Crawler(uhr, gelesen_o2, status={o2.seiten[1].adresse: LAUF_GESPERRT})
    datei = tmp_path / "klick-o2" / "o2.json"
    schreibe(datei, _fahre(ziel, karte, crawler, uhr))

    (daten,), unlesbar = lies_ergebnisse(tmp_path)
    aus = ausbeute(daten, lade_katalog(lese_wurzel()))

    assert unlesbar == []
    (satz,) = aus.rohsaetze
    assert (satz["quelle_art"], satz["device_id"], satz["speicher_gb"]) == (
        "klick",
        "apple-iphone-17-pro",
        256,
    )
    assert aus.luecken[LUECKE_SEITE] == 1
    text = datei.read_text("utf-8").lower()
    assert "screenshot" not in text and "cookie" not in text


def test_seitenadressen_ohne_geheimnisse(o2, karte, gelesen_o2):
    seite = replace(o2.seiten[0], adresse=o2.seiten[0].adresse + "&sessionid=abc123")
    uhr = Uhr()

    daten = _fahre(replace(o2, seiten=(seite,)), karte, Crawler(uhr, gelesen_o2), uhr)

    assert "abc123" not in json.dumps(daten)
    assert daten["seiten"][0]["adresse"].endswith("sessionid=ENTFERNT")


def test_paralleler_lauf_verschiebt_den_rest(o2, karte, gelesen_o2):
    meldungen = iter(
        [None, None, "Klick-Erkundung läuft (klick-erkundung.yml, queued)"]
    )
    uhr = Uhr()
    crawler = Crawler(uhr, gelesen_o2)

    daten = fahre(
        o2,
        karte,
        "o2.yaml",
        crawler,
        HEUTE,
        10**6,
        gelesen={},
        laeufe=lambda: next(meldungen),
        uhr=uhr,
    )

    assert len(crawler.aufrufe) == 2
    assert daten["laufstatus"] == LAUF_GELESEN
    assert {s["grund"] for s in daten["seiten"][2:]} == {
        f"{GRUND_PARALLEL}: Klick-Erkundung läuft (klick-erkundung.yml, queued)"
    }
    frei = Uhr()
    alle = Crawler(frei, gelesen_o2)
    fahre(
        o2,
        karte,
        "o2.yaml",
        alle,
        HEUTE,
        10**6,
        gelesen={},
        laeufe=lambda: None,
        uhr=frei,
    )
    assert len(alle.aufrufe) == len(o2.seiten)


def test_tageslauf_fragt_erkundung_und_radar_nicht_sich_selbst():
    gefragt = []

    def holer(url, kopf):
        gefragt.append(url.split("/workflows/")[1].split("/")[0])
        return (200, '{"total_count": 0}')

    laeufe = aus_umgebung(
        {"GITHUB_REPOSITORY": "a/b", "GITHUB_TOKEN": "t"}, TAGESLAUF_WORKFLOWS
    )

    assert replace(laeufe, holer=holer)() is None
    assert set(gefragt) == {"klick-erkundung.yml", "radar.yml"}
    assert aus_umgebung({}, TAGESLAUF_WORKFLOWS)() == (
        "GitHub-API nicht lesbar (GITHUB_REPOSITORY, GITHUB_TOKEN fehlt)"
    )
