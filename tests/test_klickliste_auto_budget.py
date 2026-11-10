"""Klickliste aus dem Katalog: die Telekom-Tarifseiten passen ins Zeitbudget.

Ein Platz (Gerät und Stufe) hat bei Telekom bis zu fünf Seiten, acht Plätze also bis zu
40. Eine Telekom-Seite braucht bis zu 285 s (Lauf 09.11.2026: ``telekom-2`` 23 Seiten in
6.569 s einschließlich 60 s Seitenabstand), ein Matrix-Job hat 180 min minus 8 min
Reserve minus etwa eine Minute Einrichtung, rund 10.258 s: 40 Seiten (11.400 s) passen
nicht in einen Lauf. Die Liste begrenzt sich darum selbst und rotiert die Plätze nach
dem Alter ihrer Klick-Messung im Bestand, damit jeder Platz unter
``FRISCHEGRENZE_TAGE`` bleibt (Befund Prüfung PR 83, 10.11.2026).

Die neuen Namen werden in den Tests importiert, nicht oben: gegen ``origin/main``
schlägt so jeder Test an seiner Aussage fehl und nicht gemeinsam am Import.
"""

from __future__ import annotations

import json
import shutil
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml

from telco_radar.collect.geraete.klickliste_auto import (
    HOECHSTE_SEITEN_JE_ANBIETER,
    leite_ab,
)
from telco_radar.geraete_config import lade_katalog

WURZEL = Path(__file__).resolve().parents[1]
TAGESDATEI = Path("config") / "klick_tageslauf.yaml"
TARIFE = ("MF_17779", "MF_17785", "MF_17791", "MF_17797", "MF_17803")
SEITE = (
    "https://www.telekom.de/shop/geraet/samsung/{n}/x-256-gb?tariffId={t}"
    "&categoryId=smartphones&forwardTradeInApplied=false"
)
O2_SEITE = (
    "https://www.o2online.de/e-shop/samsung/{n}-256gb-x-details"
    "?ohne-tarif=nein&zielgruppe=privatkunden&ratenzahlung=24&tarif=o2-mobile-m"
)
GERAETE = (
    "samsung-galaxy-s26",
    "samsung-galaxy-s26-plus",
    "samsung-galaxy-s26-ultra",
    "samsung-galaxy-s26-fe",
    "samsung-galaxy-s25",
    "samsung-galaxy-s25-plus",
    "samsung-galaxy-s25-ultra",
    "samsung-galaxy-s25-fe",
    "samsung-galaxy-s24",
    "samsung-galaxy-s24-ultra",
)
JOBBUDGET_S = 10_258
SEITE_S = 285
TAG0 = date(2026, 11, 1)


@pytest.fixture
def wurzel(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    for name in ("geraete_quellen.yaml", "geraete_katalog.yaml"):
        shutil.copy(WURZEL / "config" / name, tmp_path / "config" / name)
    hand = {
        "anbieter": [
            {
                "schluessel": "telekom",
                "name": "Telekom",
                "seiten": [
                    {
                        "geraet": "samsung-galaxy-s26",
                        "speicher_gb": 256,
                        "url": SEITE.format(n="samsung-galaxy-s26", t=TARIFE[2]),
                    }
                ],
            }
        ]
    }
    (tmp_path / TAGESDATEI).write_text(yaml.safe_dump(hand), encoding="utf-8")
    return tmp_path


def _buendel(
    n: str, tarif: str, messung: date | None, art: str = "klick", anbieter="Telekom"
) -> dict:
    eintrag = {
        "anbieter": anbieter,
        "sku_id": f"{n}-256gb-x",
        "quelle_url": SEITE.format(n=n, t=tarif)
        if anbieter == "Telekom"
        else O2_SEITE.format(n=n),
        "quelle_art": art,
        "pruefung": "gueltig",
    }
    if messung is not None:
        eintrag["abgerufen_am"] = messung.isoformat()
    return eintrag


def _bestand(wurzel: Path, buendel: list[dict]) -> None:
    pfad = wurzel / "data" / "state" / "geraete_tco.json"
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps({"buendel": buendel}), encoding="utf-8")


def _acht_plus_geraete(messung: date | None = None) -> list[dict]:
    """Zehn Geräte mit je fünf Tarifen: mehr als die Platzgrenze von acht."""
    assert len(GERAETE) > HOECHSTE_SEITEN_JE_ANBIETER
    return [_buendel(n, tarif, messung) for n in GERAETE for tarif in TARIFE]


def _tarif(url: str) -> str:
    return parse_qs(urlsplit(url).query)["tariffId"][0]


def test_die_liste_passt_in_ein_zeitbudget(wurzel):
    _bestand(wurzel, _acht_plus_geraete())

    seiten = leite_ab(wurzel, lade_katalog(wurzel), set())

    assert len(seiten) * SEITE_S <= JOBBUDGET_S, (
        f"{len(seiten)} Seiten brauchen {len(seiten) * SEITE_S} s, "
        f"ein Job hat {JOBBUDGET_S} s"
    )
    from telco_radar.collect.geraete.klickliste_auto import HOECHSTE_SEITEN_JE_ZIEL

    assert len(seiten) <= HOECHSTE_SEITEN_JE_ZIEL


def test_grenze_haelt_sicherheitsabstand_zum_budget():
    from telco_radar.collect.geraete.klickliste_auto import (
        HOECHSTE_SEITEN_JE_ZIEL,
        LAUFBUDGET_S,
        SEITENZEIT_S,
    )

    assert LAUFBUDGET_S == JOBBUDGET_S
    assert SEITENZEIT_S == SEITE_S
    assert HOECHSTE_SEITEN_JE_ZIEL * SEITENZEIT_S <= 0.85 * LAUFBUDGET_S
    langsamer = HOECHSTE_SEITEN_JE_ZIEL * SEITENZEIT_S * 1.15
    assert langsamer <= LAUFBUDGET_S, "15 % langsamere Seiten sprengen das Budget"


def test_budget_gleicht_dem_tageslauf_und_der_rotation_der_frischegrenze():
    from telco_radar.collect.geraete.klickliste_auto import (
        HOECHSTE_SEITEN_JE_ZIEL,
        LAUFBUDGET_S,
        ROTATIONSTAGE,
    )
    from telco_radar.collect.geraete.klicktageslauf import JOB_FRIST_S, RESERVE_S
    from telco_radar.klick_vertrag import FRISCHEGRENZE_TAGE

    einrichtung_s = 62
    assert JOB_FRIST_S - RESERVE_S - einrichtung_s == LAUFBUDGET_S
    assert ROTATIONSTAGE < FRISCHEGRENZE_TAGE
    plaetze_je_lauf = HOECHSTE_SEITEN_JE_ZIEL // len(TARIFE)
    laeufe = -(-HOECHSTE_SEITEN_JE_ANBIETER // plaetze_je_lauf)
    assert laeufe <= ROTATIONSTAGE


def test_rotation_liest_jeden_platz_innerhalb_der_frischegrenze(wurzel):
    """Zehn Tage: jeden Tag wird gelesen, was die Liste nennt; die Messung steht danach
    im Bestand. Jede Seite wird höchstens alle zwei Tage gelesen."""
    from telco_radar.collect.geraete.klickliste_auto import HOECHSTE_SEITEN_JE_ZIEL
    from telco_radar.klick_vertrag import FRISCHEGRENZE_TAGE

    bestand = _acht_plus_geraete(TAG0 - timedelta(days=1))
    zuletzt: dict[tuple[str, str], date] = {}
    luecke = 0
    for tag in range(10):
        heute = TAG0 + timedelta(days=tag)
        _bestand(wurzel, bestand)
        seiten = leite_ab(wurzel, lade_katalog(wurzel), set())
        assert len(seiten) <= HOECHSTE_SEITEN_JE_ZIEL
        assert len(seiten) * SEITE_S <= JOBBUDGET_S
        gelesen = {(s.geraet, _tarif(s.url)) for s in seiten}
        for eintrag in bestand:
            kennung = (
                eintrag["sku_id"].removesuffix("-256gb-x"),
                _tarif(eintrag["quelle_url"]),
            )
            if kennung in gelesen:
                eintrag["abgerufen_am"] = heute.isoformat()
        for kennung in gelesen:
            if kennung in zuletzt:
                luecke = max(luecke, (heute - zuletzt[kennung]).days)
            zuletzt[kennung] = heute
    plaetze = {k[0] for k in zuletzt}
    assert len(plaetze) == HOECHSTE_SEITEN_JE_ANBIETER, "ein Platz kam nie dran"
    assert len(zuletzt) == HOECHSTE_SEITEN_JE_ANBIETER * len(TARIFE)
    assert 0 < luecke < FRISCHEGRENZE_TAGE
    tag_ende = TAG0 + timedelta(days=9)
    alter = [
        (tag_ende - date.fromisoformat(e["abgerufen_am"])).days
        for e in bestand
        if (e["sku_id"].removesuffix("-256gb-x"), _tarif(e["quelle_url"])) in zuletzt
    ]
    assert max(alter) < FRISCHEGRENZE_TAGE


def test_nie_gemessene_plaetze_kommen_vor_den_gemessenen(wurzel):
    """Sechs gemessene und zwei neue Plätze: die neuen kommen trotz niedrigerem Rang
    sofort dran, die älteste Messung zuletzt."""
    bestand = [
        _buendel(n, tarif, TAG0 + timedelta(days=i))
        for i, n in enumerate(GERAETE[:6])
        for tarif in TARIFE
    ] + [_buendel(n, tarif, None) for n in GERAETE[6:8] for tarif in TARIFE]
    _bestand(wurzel, bestand)

    seiten = leite_ab(wurzel, lade_katalog(wurzel), set())

    geraete = {s.geraet for s in seiten}
    assert set(GERAETE[6:8]) <= geraete
    assert len(seiten) == 30
    assert len(geraete) == 6
    jung = set(GERAETE[:6]) - geraete
    assert jung == set(GERAETE[4:6]), "ausgelassen: die zwei jüngst gemessenen Plätze"


def test_adapter_datum_zaehlt_nicht_als_messung(wurzel):
    """Ein Bündel ohne Klick-Lesung erneuert sein Datum täglich; die Seite wurde damit
    nicht gelesen und darf nicht hinten anstehen."""
    heute = TAG0 + timedelta(days=5)
    bestand = [
        _buendel(n, tarif, heute, art="adapter")
        for n in GERAETE[:6]
        for tarif in TARIFE
    ] + [_buendel(n, tarif, TAG0) for n in GERAETE[6:8] for tarif in TARIFE]
    _bestand(wurzel, bestand)

    seiten = leite_ab(wurzel, lade_katalog(wurzel), set())

    assert {s.geraet for s in seiten} == set(GERAETE[:6]), (
        "zählte das Adapter-Datum, wären die zwei Klick-Plätze die ältesten"
    )


def test_gegenprobe_unter_der_grenze_bleibt_alles(wurzel):
    _bestand(wurzel, [_buendel(n, t, TAG0) for n in GERAETE[:3] for t in TARIFE])

    seiten = leite_ab(wurzel, lade_katalog(wurzel), set())

    assert len(seiten) == 3 * len(TARIFE)
    assert {s.geraet for s in seiten} == set(GERAETE[:3])


def test_gegenprobe_andere_anbieter_haben_keine_seitengrenze(wurzel):
    """Ohne Tarifparameter ist eine Seite ein Platz: acht Plätze bleiben acht Seiten."""
    _bestand(wurzel, [_buendel(n, "", None, anbieter="o2") for n in GERAETE])

    seiten = leite_ab(wurzel, lade_katalog(wurzel), set())

    assert len(seiten) == HOECHSTE_SEITEN_JE_ANBIETER
    assert {s.anbieter for s in seiten} == {"o2"}


def test_kommentar_der_klickliste_nennt_plaetze_und_seitengrenze():
    """Die Config sagte „höchstens 8 Seiten“; gemeint waren Plätze."""
    text = (WURZEL / TAGESDATEI).read_text(encoding="utf-8")
    kopf = text.split("anbieter:", 1)[0]

    assert "höchstens 8 Seiten" not in kopf
    assert "HOECHSTE_SEITEN_JE_ZIEL" in kopf
    assert "FRISCHEGRENZE_TAGE" in kopf


def test_plaetze_der_tarifseiten_bleiben_zusammen(wurzel):
    _bestand(wurzel, _acht_plus_geraete())

    seiten = leite_ab(wurzel, lade_katalog(wurzel), set())

    je_geraet = defaultdict(set)
    for s in seiten:
        je_geraet[s.geraet].add(_tarif(s.url))
    assert all(tarife == set(TARIFE) for tarife in je_geraet.values())
