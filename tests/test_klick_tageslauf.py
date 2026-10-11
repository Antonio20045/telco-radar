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
import re
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
    LAUF_ZEITGRENZE,
    STOERUNG_SEITE,
    STOERUNG_ZEIT,
    Klicklauf,
    abruf_gestoert,
)
from telco_radar.collect.geraete.klickparallel import TAGESLAUF_WORKFLOWS, aus_umgebung
from telco_radar.collect.geraete.klickrohsatz import LUECKE_SEITE, ausbeute
from telco_radar.collect.geraete.klicktageslauf import (
    GRUND_BUDGET,
    GRUND_NACH_STOERUNG,
    GRUND_PARALLEL,
    GRUND_SEITENFORMEN,
    GRUND_ZEITUEBERSCHREITUNGEN,
    HOECHSTE_SEITENFORMEN_IN_FOLGE,
    HOECHSTE_ZEITUEBERSCHREITUNGEN,
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
NICHT_GELADEN = "Seite nach 30000 ms nicht geladen (30000 ms ohne neue Antwort)"
OHNE_SCHALTER = "Vorbereitung: span.dt_switch.forwardTradeInSwitch nicht gefunden"
MINUTE = 60.0
_SKRIPT = WURZEL / "scripts" / "klick_tageslauf.py"


@pytest.fixture(scope="module")
def ziele():
    alle = lade_ziele(lese_wurzel(), TAGESDATEI, hoechste=None)
    return {z.schluessel: z for z in alle}


@pytest.fixture(scope="module")
def o2(ziele):
    """Die ersten sechs o2-Seiten der Tagesdatei: Rotation und Budget unabhängig
    davon, wie viele Seiten die Datei heute nennt."""
    return replace(ziele["o2"], seiten=ziele["o2"].seiten[:6])


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
        if status == STOERUNG_ZEIT:
            lauf = Klicklauf("o2", seite.adresse, LAUF_GESTOERT, NICHT_GELADEN, 200)
            return replace(lauf, stoerung=STOERUNG_ZEIT)
        if status == STOERUNG_SEITE:
            lauf = Klicklauf("o2", seite.adresse, LAUF_GESTOERT, OHNE_SCHALTER, 200)
            return replace(lauf, stoerung=STOERUNG_SEITE)
        if status == LAUF_GESPERRT:
            return Klicklauf("o2", seite.adresse, status, "robots.txt verbietet", None)
        if status == LAUF_ZEITGRENZE:
            erfasst_bis_hier = [self.kombination]
            return Klicklauf("o2", seite.adresse, status, ergebnisse=erfasst_bis_hier)
        return Klicklauf("o2", seite.adresse, ergebnisse=[self.kombination])


def _fahre(o2, karte, crawler, uhr, ende=10**6, gelesen=None):
    return fahre(
        o2, karte, "o2.yaml", crawler, HEUTE, ende, gelesen=gelesen or {}, uhr=uhr
    )


def test_tagesdatei_hat_alle_anbieter_mit_karte_und_keine_seitengrenze(ziele):
    assert list(ziele) == [
        "o2",
        "o2-tarife",
        "o2-tarife-2",
        "vodafone",
        "vodafone-2",
        "vodafone-3",
        "1und1",
        "telekom",
        "telekom-2",
        "telekom-3",
        "telekom-4",
        "telekom-5",
        "telekom-6",
        "telekom-7",
        "telekom-8",
        "telekom-9",
        "telekom-10",
        "telekom-11",
        "congstar",
    ]
    for ziel in ziele.values():
        karte = WURZEL / "config" / "klickkarten" / f"{ziel.kartenschluessel}.yaml"
        assert karte.is_file()
    assert O2_SEITE.adresse in {s.adresse for s in ziele["o2"].seiten}
    telekom = _seiten_von(ziele, "Telekom")
    assert len(telekom) == len(set(telekom)) == 316
    vodafone = _seiten_von(ziele, "Vodafone")
    assert len(vodafone) == len(set(vodafone)) == 42
    with pytest.raises(ErkundungszielFehler, match="höchstens 2"):
        lade_ziele(lese_wurzel(), TAGESDATEI)


def _seiten_von(ziele, name):
    return [s.adresse for z in ziele.values() if z.name == name for s in z.seiten]


def test_telekom_und_vodafone_verteilt_auf_jobs_mit_einer_karte(ziele):
    """Antonio 11.10.2026: alle Geräte jeden Tag; jeder Job hat eigene Seiten, alle
    eine Karte. Vodafone 5–9 min je Seite: höchstens 15. Telekom 200–250 s je Seite
    samt Minute Abstand (Tageslauf 11.10.2026, 41 Seiten), dazu im ersten Job rund
    20 min Übersichten: höchstens 30 Seiten in 10 270 s."""
    for name, karte, jobs, hoechstens in (
        ("Telekom", "telekom", 11, 30),
        ("Vodafone", "vodafone", 3, 15),
    ):
        teile = [z for z in ziele.values() if z.name == name]
        assert len(teile) == jobs
        assert {z.kartenschluessel for z in teile} == {karte}
        assert max(len(z.seiten) for z in teile) <= hoechstens
    assert [
        z.schluessel for z in ziele.values() if z.uebersichten and z.name == "Telekom"
    ] == ["telekom"]


def test_plan_nennt_jeden_anbieter_mit_karte(capsys):
    spec = importlib.util.spec_from_file_location("klick_tageslauf", _SKRIPT)
    skript = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(skript)

    assert skript.main(["--plan", "--root", str(lese_wurzel())]) == 0
    assert json.loads(capsys.readouterr().out) == [
        "o2",
        "o2-tarife",
        "o2-tarife-2",
        "vodafone",
        "vodafone-2",
        "vodafone-3",
        "1und1",
        "telekom",
        "telekom-2",
        "telekom-3",
        "telekom-4",
        "telekom-5",
        "telekom-6",
        "telekom-7",
        "telekom-8",
        "telekom-9",
        "telekom-10",
        "telekom-11",
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


def test_zeitueberschreitung_beendet_den_anbieter_nicht(o2, karte, gelesen_o2):
    """Vodafone 08.10.2026: HTTP 200, Seite lud nicht. Kein Bot-Schutz (CLAUDE.md
    Regel 10): die nächste Seite folgt, gelesene Seiten zählen."""
    erste = o2.seiten[0].adresse
    uhr = Uhr()
    crawler = Crawler(uhr, gelesen_o2, status={erste: STOERUNG_ZEIT})

    daten = _fahre(o2, karte, crawler, uhr)

    assert len(crawler.aufrufe) == len(o2.seiten)
    seite = daten["seiten"][0]
    assert (seite["status"], seite["stoerung"], seite["grund"]) == (
        LAUF_GESTOERT,
        STOERUNG_ZEIT,
        NICHT_GELADEN,
    )
    assert daten["laufstatus"] == LAUF_GELESEN
    assert daten["ueberfaellig"] == [erste]


@pytest.mark.parametrize(
    ("status", "aufrufe", "laufstatus"),
    [
        ((STOERUNG_ZEIT, LAUF_GELESEN, STOERUNG_ZEIT), 3, LAUF_GELESEN),
        ((STOERUNG_ZEIT, STOERUNG_ZEIT), 2, LAUF_GESTOERT),
        ((STOERUNG_ZEIT, LAUF_GESTOERT), 2, LAUF_GESTOERT),
    ],
)
def test_nach_zwei_zeitueberschreitungen_oder_bot_schutz_ist_schluss(
    o2, karte, gelesen_o2, status, aufrufe, laufstatus
):
    """Höchstens zwei Seiten ohne Laden; Gegenprobe: Bot-Schutz nach einer
    Zeitüberschreitung beendet den Anbieter sofort und bestimmt den Grund."""
    adressen = [s.adresse for s in o2.seiten]
    uhr = Uhr()
    crawler = Crawler(uhr, gelesen_o2, status=dict(zip(adressen, status, strict=False)))

    daten = _fahre(o2, karte, crawler, uhr)

    assert len(crawler.aufrufe) == aufrufe
    assert daten["laufstatus"] == laufstatus
    rest = {s["grund"] for s in daten["seiten"][aufrufe:]}
    if status[-1] == LAUF_GESTOERT:
        assert rest == {f"{GRUND_NACH_STOERUNG}: Abruf gestört (HTTP 403)"}
        assert daten["grund"] == f"{adressen[1]}: Abruf gestört (HTTP 403)"
    else:
        zahl = HOECHSTE_ZEITUEBERSCHREITUNGEN
        assert rest == {f"{zahl} {GRUND_ZEITUEBERSCHREITUNGEN}: {NICHT_GELADEN}"}


def test_seite_anderer_form_haelt_die_uebrigen_nicht_an(o2, karte, gelesen_o2):
    """Telekom 11.10.2026: Galaxy A17 ohne Rückgabe-Schalter hielt 53 Seiten an.
    Eine Seite anderer Form ist kein Bot-Schutz: die übrigen werden gelesen, der
    Anbieter gilt als gelesen, die Seite bleibt überfällig."""
    zweite = o2.seiten[1].adresse
    uhr = Uhr()
    crawler = Crawler(uhr, gelesen_o2, status={zweite: STOERUNG_SEITE})

    daten = _fahre(o2, karte, crawler, uhr)

    assert len(crawler.aufrufe) == len(o2.seiten)
    seite = daten["seiten"][1]
    assert (seite["status"], seite["stoerung"], seite["grund"]) == (
        LAUF_GESTOERT,
        STOERUNG_SEITE,
        OHNE_SCHALTER,
    )
    assert daten["laufstatus"] == LAUF_GELESEN
    assert daten["ueberfaellig"] == [zweite]


@pytest.mark.parametrize(
    ("folge", "aufrufe"),
    [
        (
            (STOERUNG_SEITE,) * HOECHSTE_SEITENFORMEN_IN_FOLGE,
            HOECHSTE_SEITENFORMEN_IN_FOLGE,
        ),
        ((STOERUNG_SEITE, STOERUNG_SEITE, LAUF_GELESEN, STOERUNG_SEITE), 6),
    ],
)
def test_seiten_anderer_form_in_folge_beenden_den_anbieter(
    o2, karte, gelesen_o2, folge, aufrufe
):
    """Ändert sich die Form jeder Seite (etwa eine unerkannte Sperrseite), endet der
    Anbieter nach HOECHSTE_SEITENFORMEN_IN_FOLGE Seiten hintereinander; Gegenprobe:
    eine gelesene Seite dazwischen setzt die Folge zurück."""
    adressen = [s.adresse for s in o2.seiten]
    uhr = Uhr()
    status = dict(zip(adressen, folge, strict=False))
    crawler = Crawler(uhr, gelesen_o2, status=status)

    daten = _fahre(o2, karte, crawler, uhr)

    assert len(crawler.aufrufe) == aufrufe
    rest = {s["grund"] for s in daten["seiten"][aufrufe:]}
    if aufrufe < len(adressen):
        zahl = HOECHSTE_SEITENFORMEN_IN_FOLGE
        assert rest == {f"{zahl} {GRUND_SEITENFORMEN}: {OHNE_SCHALTER}"}
        assert daten["laufstatus"] == LAUF_GESTOERT
    else:
        assert daten["laufstatus"] == LAUF_GELESEN


def test_gesperrte_seite_beendet_den_anbieter_nicht(o2, karte, gelesen_o2):
    uhr = Uhr()
    crawler = Crawler(uhr, gelesen_o2, status={o2.seiten[1].adresse: LAUF_GESPERRT})

    daten = _fahre(o2, karte, crawler, uhr)

    assert len(crawler.aufrufe) == len(o2.seiten)
    assert daten["laufstatus"] == LAUF_GELESEN
    assert daten["ueberfaellig"] == [o2.seiten[1].adresse]


@pytest.mark.parametrize(
    ("status", "faellig"), [(LAUF_ZEITGRENZE, 1), (LAUF_GELESEN, 0)]
)
def test_abgeschnittene_seite_bleibt_ueberfaellig(
    o2, karte, gelesen_o2, status, faellig
):
    """Eine an der Zeitgrenze abgeschnittene Seite hat ihre erste Variante erfasst,
    ist aber nicht ganz gelesen: sie bleibt überfällig. Gegenprobe: ganz gelesen."""
    zweite = o2.seiten[1].adresse
    uhr = Uhr()
    crawler = Crawler(uhr, gelesen_o2, status={zweite: status})

    daten = _fahre(o2, karte, crawler, uhr)

    assert daten["seiten"][1]["status"] == status
    assert daten["laufstatus"] == LAUF_GELESEN
    assert daten["ueberfaellig"] == [zweite][:faellig]


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


def test_tageslauf_weicht_geraetelauf_erkundung_und_radar_aus():
    """``klick.yml`` darf ``geraete.yml`` nicht überlappen (CLAUDE.md Regel 4)."""
    gefragt = []

    def holer(url, kopf):
        gefragt.append(url.split("/workflows/")[1].split("/")[0])
        return (200, '{"total_count": 0}')

    laeufe = aus_umgebung(
        {"GITHUB_REPOSITORY": "a/b", "GITHUB_TOKEN": "t"}, TAGESLAUF_WORKFLOWS
    )

    assert replace(laeufe, holer=holer)() is None
    assert set(gefragt) == {"geraete.yml", "klick-erkundung.yml", "radar.yml"}
    assert aus_umgebung({}, TAGESLAUF_WORKFLOWS)() == (
        "GitHub-API nicht lesbar (GITHUB_REPOSITORY, GITHUB_TOKEN fehlt)"
    )


TARIFE = {"MF_17779", "MF_17785", "MF_17791", "MF_17797", "MF_17803"}


def test_telekom_jedes_geraet_je_tarif_eine_seite(ziele):
    """Preisprüfung 11.10.2026: iPhone Air nur in M mit 12 und 24 Raten, weil die
    Telekom-Seite nur den Tarif ihrer Adresse zeigt und nur das 17 Pro alle fünf
    Tarifseiten hatte. Jetzt je Gerät und Tarif genau eine Seite."""
    paare = [
        (s.geraet, re.search(r"tariffId=(MF_\d+)", s.adresse)[1])
        for z in ziele.values()
        if z.name == "Telekom"
        for s in z.seiten
    ]
    assert len(paare) == len(set(paare))
    je_geraet: dict[str, set[str]] = {}
    for geraet, tarif in paare:
        je_geraet.setdefault(geraet, set()).add(tarif)
    for geraet in ("apple-iphone-air", "apple-iphone-17-pro", "samsung-galaxy-s26"):
        assert je_geraet[geraet] == TARIFE
    assert sum(len(t) == 5 for t in je_geraet.values()) >= 50
