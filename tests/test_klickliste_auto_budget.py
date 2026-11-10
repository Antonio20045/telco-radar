"""Klickliste aus dem Katalog: kein Platz fällt heraus, die Rotation trägt das Budget.

Ein Platz (Gerät und Stufe) hat bei Telekom bis zu fünf Seiten, acht Plätze also bis zu
40. Eine Telekom-Seite braucht bis zu ``SEITENZEIT_S``, ein Matrix-Job hat rund
10.258 s: 40 Seiten passen nicht in einen Lauf, die Rotation des Tageslaufs
(``klicktageslauf``, Lesestand) liest die übrigen am nächsten Tag zuerst. Die Liste
darf dabei keinen Platz verlieren: ein Bündel, das drei Tage nicht gelesen wurde, ist
„veraltet“ und bleibt Quelle seiner Adresse (Prüfung PR 85, 10.11.2026; der Stand
2d15fe31 warf es weg, der Platz kam nie zurück). Nach ``QUELLE_HOECHSTALTER_TAGE``
nicht mehr: ein Gerät, das der Anbieter nicht mehr führt, bliebe sonst ewig.

Die Tage laufen mit dem echten ``leite_ab`` und dem echten ``fahre``; Uhr und Crawler
sind Attrappen, die Alterung der Bündel ist die der Prüfstelle (Regel 16,
``FRISCHEGRENZE_TAGE``). Kein Browser, kein Netz.
"""

from __future__ import annotations

import json
import shutil
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml

from telco_radar.collect.geraete.klickkarte import lade_klickkarte
from telco_radar.collect.geraete.klicklauf import (
    LAUF_GELESEN,
    LAUF_GESTOERT,
    STOERUNG_ZEIT,
    Klicklauf,
)
from telco_radar.collect.geraete.klickliste_auto import (
    HOECHSTE_SEITEN_JE_ANBIETER,
    leite_ab,
)
from telco_radar.collect.geraete.klicktageslauf import (
    JOB_FRIST_S,
    RESERVE_S,
    budget_ende,
    fahre,
    hat_vorrang,
)
from telco_radar.collect.geraete.klickziele import Erkundungsziel, Seitenziel
from telco_radar.geraete_config import lade_katalog
from telco_radar.klick_vertrag import FRISCHEGRENZE_TAGE, ganz_gelesen

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
ALLE_SEITEN = HOECHSTE_SEITEN_JE_ANBIETER * len(TARIFE)
EINRICHTUNG_S = 62
JOBBUDGET_S = JOB_FRIST_S - RESERVE_S - EINRICHTUNG_S
SEITENABSTAND_S = 60.0
SEITENZEIT_S = 330
"""Vorsichtig: Zeit je Telekom-Seite einschließlich 60 s Seitenabstand. Gemessen als
Dauer des Jobs durch gelesene Seiten (``data/state/klick/telekom-*.json``, 211
Tagesergebnisse seit dem 03.11.2026, ohne den Job mit Übersichten): Mittel 266 s,
95. Perzentil 299 s, schlechtester Job 320,6 s (``telekom-9``, 09.11.2026). Die Dateien
kennen nur die Dauer je Job, nicht je Seite; 330 s liegt darüber."""
SEITEN_JE_LAUF = (JOBBUDGET_S - (SEITENZEIT_S - SEITENABSTAND_S)) // SEITENZEIT_S + 1
"""Seiten, die ganz in einen Job passen (31); die letzte endet vor dem Budget."""
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


@pytest.fixture(scope="module")
def karte():
    return lade_klickkarte(WURZEL / "config" / "klickkarten" / "telekom.yaml")


def _buendel(
    n: str, tarif: str, messung: date, anbieter="Telekom", pruefung="gueltig"
) -> dict:
    return {
        "anbieter": anbieter,
        "sku_id": f"{n}-256gb-x",
        "quelle_url": SEITE.format(n=n, t=tarif)
        if anbieter == "Telekom"
        else O2_SEITE.format(n=n),
        "quelle_art": "klick",
        "pruefung": pruefung,
        "abgerufen_am": messung.isoformat(),
    }


def _bestand(wurzel: Path, buendel: list[dict]) -> None:
    pfad = wurzel / "data" / "state" / "geraete_tco.json"
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps({"buendel": buendel}), encoding="utf-8")


def _alle_plaetze(messung: date) -> list[dict]:
    """Zehn Geräte mit je fünf Tarifen: mehr als die Platzgrenze von acht."""
    assert len(GERAETE) > HOECHSTE_SEITEN_JE_ANBIETER
    return [_buendel(n, tarif, messung) for n in GERAETE for tarif in TARIFE]


def _tarif(url: str) -> str:
    return parse_qs(urlsplit(url).query)["tariffId"][0]


class Uhr:
    def __init__(self) -> None:
        self.jetzt = 0.0

    def __call__(self) -> float:
        return self.jetzt

    def schlafe(self, sekunden: float) -> None:
        self.jetzt += sekunden


def _crawler(uhr: Uhr):
    """Jede Seite braucht ``SEITENZEIT_S`` mit Abstand; reicht die Grenze nicht, endet
    sie an der Zeitgrenze und gilt nicht als gelesen."""
    dauer = SEITENZEIT_S - SEITENABSTAND_S

    def crawle(seite, ende):
        if uhr.jetzt + dauer > ende:
            uhr.jetzt = ende
            lauf = Klicklauf("Telekom", seite.adresse, LAUF_GESTOERT, "Zeitgrenze")
            lauf.stoerung = STOERUNG_ZEIT
            return lauf
        uhr.jetzt += dauer
        return Klicklauf("Telekom", seite.adresse, LAUF_GELESEN, http_status=200)

    return crawle


def _alterung(bestand: list[dict], heute: date) -> None:
    """Wie die Prüfstelle (Regel 16): ab ``FRISCHEGRENZE_TAGE`` „veraltet 16“."""
    for eintrag in bestand:
        alter = (heute - date.fromisoformat(eintrag["abgerufen_am"])).days
        eintrag["pruefung"] = (
            "veraltet 16" if alter >= FRISCHEGRENZE_TAGE else "gueltig"
        )


class Verlauf:
    """Mehrere Tage Klickliste und Tageslauf; hält fest, was die Tage ergaben."""

    def __init__(self, wurzel: Path, karte, anfang: date, verzoegerung: int = 0):
        self.wurzel, self.karte = wurzel, karte
        self.bestand = _alle_plaetze(anfang)
        self.verzoegerung = verzoegerung
        self.stand: dict[str, str] = {}
        self.kommt: dict[str, tuple[date, str]] = {}
        self.listen: list[set[str]] = []
        self.gelesen: list[set[str]] = []
        self.veraltet: list[int] = []
        self.dauer: list[float] = []

    def tag(self, heute: date, ausfall: bool = False) -> set[str]:
        """Ein Tag: Messdaten kommen an, Liste ableiten, lesen (außer am Ausfalltag)."""
        for eintrag in self.bestand:
            ab, am = self.kommt.get(eintrag["quelle_url"], (None, ""))
            if ab is not None and ab <= heute:
                eintrag["abgerufen_am"] = am
                del self.kommt[eintrag["quelle_url"]]
        _alterung(self.bestand, heute)
        self.veraltet.append(sum(e["pruefung"] != "gueltig" for e in self.bestand))
        _bestand(self.wurzel, self.bestand)
        seiten = leite_ab(self.wurzel, lade_katalog(self.wurzel), set())
        self.listen.append({s.url for s in seiten})
        gelesen = set() if ausfall else self._lies(seiten, heute)
        self.gelesen.append(gelesen)
        return gelesen

    def _lies(self, seiten, heute: date) -> set[str]:
        ziel = Erkundungsziel(
            schluessel="telekom-auto",
            name="Telekom",
            seiten=tuple(Seitenziel(s.geraet, s.speicher_gb, s.url) for s in seiten),
            kennung=None,
            rate_limit_sekunden=0.0,
            seitenabstand_sekunden=SEITENABSTAND_S,
        )
        uhr = Uhr()
        ende = budget_ende(JOB_FRIST_S, EINRICHTUNG_S, 0.0)
        vorher = dict(self.stand)
        daten = fahre(
            ziel,
            self.karte,
            "telekom.yaml",
            _crawler(uhr),
            heute.isoformat(),
            ende,
            gelesen=self.stand,
            uhr=uhr,
            schlafe=uhr.schlafe,
        )
        assert uhr.jetzt <= ende, "der Lauf überschritt das Budget"
        self.dauer.append(uhr.jetzt)
        gelesen = {s["adresse"] for s in ganz_gelesen(daten["seiten"])}
        gewoehnlich = {
            s.url for s in seiten if not hat_vorrang(Seitenziel(s.geraet, None, s.url))
        }
        offen = gewoehnlich - gelesen
        if gelesen & gewoehnlich and offen:
            aelteste_offene = min(vorher.get(u, "") for u in offen)
            juengste_gelesene = max(vorher.get(u, "") for u in gelesen & gewoehnlich)
            assert aelteste_offene >= juengste_gelesene, (
                "eine ältere Seite blieb liegen"
            )
        for adresse in gelesen:
            self.stand[adresse] = heute.isoformat()
            ab = heute + timedelta(days=self.verzoegerung)
            self.kommt[adresse] = (ab, heute.isoformat())
        return gelesen

    def lesetage(self) -> dict[str, list[int]]:
        tage: dict[str, list[int]] = {}
        for i, gelesen in enumerate(self.gelesen):
            for adresse in gelesen:
                tage.setdefault(adresse, []).append(i)
        return tage

    def groesste_luecke(self) -> int:
        """Längste Pause zwischen zwei Lesungen derselben Seite, in Tagen."""
        return max(
            b - a
            for tage in self.lesetage().values()
            for a, b in zip(tage, tage[1:], strict=False)
        )


def test_veraltetes_buendel_bleibt_quelle_der_adresse(wurzel):
    """Der Stand 2d15fe31 warf jedes Bündel „veraltet“ weg: kein Platz, keine Seite."""
    bestand = _alle_plaetze(TAG0 - timedelta(days=10))
    for eintrag in bestand:
        eintrag["pruefung"] = "veraltet 16"
    _bestand(wurzel, bestand)

    seiten = leite_ab(wurzel, lade_katalog(wurzel), set())

    assert len(seiten) == ALLE_SEITEN
    assert {_tarif(s.url) for s in seiten} == set(TARIFE)


def test_rotation_traegt_das_budget_bei_40_seiten(wurzel, karte):
    """40 Seiten × 330 s sind mehr als ein Job: jeder Tag liest höchstens 31 Seiten und
    bleibt im Budget (geprüft in ``Verlauf.tag``), jede Seite kommt alle zwei Tage."""
    assert ALLE_SEITEN * SEITENZEIT_S > JOBBUDGET_S, "dann trüge die Rotation nichts"

    verlauf = Verlauf(wurzel, karte, TAG0 - timedelta(days=1))
    for tag in range(10):
        verlauf.tag(TAG0 + timedelta(days=tag))

    assert all(len(liste) == ALLE_SEITEN for liste in verlauf.listen)
    assert max(len(g) for g in verlauf.gelesen) == SEITEN_JE_LAUF
    assert min(len(g) for g in verlauf.gelesen) >= ALLE_SEITEN - SEITEN_JE_LAUF
    assert len(verlauf.lesetage()) == ALLE_SEITEN, "eine Seite kam nie dran"
    assert verlauf.groesste_luecke() == 2
    assert max(verlauf.dauer) <= JOBBUDGET_S


def test_ausfalltag_verliert_keinen_platz_und_liest_das_aelteste_zuerst(wurzel, karte):
    """Zwei Tage fallen aus (Job rot): die Bündel werden drei Tage alt und „veraltet“.
    Die Plätze bleiben in der Liste und kommen zuerst dran (Stand 2d15fe31: ab dem
    Folgetag fehlten sie dauerhaft)."""
    verlauf = Verlauf(wurzel, karte, TAG0 - timedelta(days=1))
    for tag in range(12):
        verlauf.tag(TAG0 + timedelta(days=tag), ausfall=tag in (3, 4))

    assert max(verlauf.veraltet) > 0, "die Alterung auf veraltet wurde nie erreicht"
    assert all(liste == verlauf.listen[0] for liste in verlauf.listen)
    assert len(verlauf.listen[0]) == ALLE_SEITEN
    assert len(verlauf.lesetage()) == ALLE_SEITEN
    assert not verlauf.gelesen[3] and not verlauf.gelesen[4]
    assert verlauf.groesste_luecke() <= 2 + 2, "länger ungelesen als der Ausfall"


def test_ein_tag_verzoegerung_der_messdaten_aendert_nichts(wurzel, karte):
    """Die Messdaten erreichen den Bestand einen Tag nach der Lesung (08.11.: Klick-Lauf
    nach dem Geräte-Lauf). Der Lesestand des Tageslaufs ist schon aktuell: die Liste
    bleibt vollständig, jede Seite wird alle zwei Tage gelesen, nie dieselben zweimal
    hintereinander, während andere warten."""
    verlauf = Verlauf(wurzel, karte, TAG0 - timedelta(days=1), verzoegerung=1)
    for tag in range(12):
        verlauf.tag(TAG0 + timedelta(days=tag))

    assert all(len(liste) == ALLE_SEITEN for liste in verlauf.listen)
    assert len(verlauf.lesetage()) == ALLE_SEITEN
    assert verlauf.groesste_luecke() == 2


def test_verzoegerung_und_ausfall_zusammen(wurzel, karte):
    verlauf = Verlauf(wurzel, karte, TAG0 - timedelta(days=1), verzoegerung=2)
    for tag in range(14):
        verlauf.tag(TAG0 + timedelta(days=tag), ausfall=tag == 5)

    assert all(len(liste) == ALLE_SEITEN for liste in verlauf.listen)
    assert len(verlauf.lesetage()) == ALLE_SEITEN
    assert verlauf.groesste_luecke() <= 3


def test_alterung_auf_veraltet_nimmt_keine_seite_aus_der_liste(wurzel, karte):
    """Sieben Tage ohne Lesung: alle Bündel sind „veraltet“, alle 40 Seiten stehen noch
    in der Liste. Der erste Lauf danach liest die 31 ältesten, der zweite den Rest."""
    verlauf = Verlauf(wurzel, karte, TAG0 - timedelta(days=1))
    for tag in range(2):
        verlauf.tag(TAG0 + timedelta(days=tag))
    for tag in range(2, 9):
        verlauf.tag(TAG0 + timedelta(days=tag), ausfall=True)

    assert verlauf.veraltet[-1] == len(GERAETE) * len(TARIFE)
    assert verlauf.listen[-1] == verlauf.listen[0]
    assert len(verlauf.listen[-1]) == ALLE_SEITEN

    erster = verlauf.tag(TAG0 + timedelta(days=9))
    zweiter = verlauf.tag(TAG0 + timedelta(days=10))

    assert len(erster) == SEITEN_JE_LAUF
    assert verlauf.listen[-1] - erster <= zweiter, "eine Seite wartete länger als nötig"


def test_gegenprobe_sehr_altes_buendel_ist_keine_quelle_mehr(wurzel):
    """Ein Gerät, das der Anbieter nicht mehr führt, bleibt nicht ewig in der Liste:
    ein veraltetes Bündel zählt nur ``QUELLE_HOECHSTALTER_TAGE`` Tage hinter dem
    jüngsten des Bestands (1&1 iPhone 15, 32 Tage, bleibt draußen)."""
    from telco_radar.collect.geraete.klickliste_auto import QUELLE_HOECHSTALTER_TAGE

    jung = TAG0
    grenze = jung - timedelta(days=QUELLE_HOECHSTALTER_TAGE)
    bestand = [_buendel(GERAETE[0], TARIFE[0], jung)]
    bestand += [
        _buendel(GERAETE[1], TARIFE[0], grenze, pruefung="veraltet 16"),
        _buendel(
            GERAETE[2], TARIFE[0], grenze - timedelta(days=1), "Telekom", "veraltet 16"
        ),
    ]
    ohne_datum = _buendel(GERAETE[3], TARIFE[0], jung, pruefung="veraltet 16")
    del ohne_datum["abgerufen_am"]
    _bestand(wurzel, [*bestand, ohne_datum])

    seiten = leite_ab(wurzel, lade_katalog(wurzel), set())

    assert {s.geraet for s in seiten} == {GERAETE[0], GERAETE[1]}


def test_frisches_buendel_geht_vor_dem_veralteten_derselben_stelle(wurzel):
    """Nennt ein veraltetes Bündel eine andere Adresse für denselben Platz als ein
    frisches, gilt die frische (o2 Galaxy S25 Ultra: andere Farbe)."""
    alt = O2_SEITE.format(n="samsung-galaxy-s25-ultra").replace(
        "x-details", "alt-details"
    )
    neu = O2_SEITE.format(n="samsung-galaxy-s25-ultra")
    veraltet = _buendel("samsung-galaxy-s25-ultra", "", TAG0, "o2", "veraltet 16")
    veraltet["quelle_url"] = alt
    frisch = _buendel("samsung-galaxy-s25-ultra", "", TAG0, "o2")
    frisch["quelle_url"] = neu
    _bestand(wurzel, [veraltet, frisch])

    seiten = leite_ab(wurzel, lade_katalog(wurzel), set())

    assert [s.url for s in seiten] == [neu]


def test_gegenprobe_andere_anbieter_haben_keine_seitengrenze(wurzel):
    """Ohne Tarifparameter ist eine Seite ein Platz: acht Plätze bleiben acht Seiten,
    auch mit veralteten Bündeln."""
    _bestand(
        wurzel,
        [_buendel(n, "", TAG0, anbieter="o2", pruefung="veraltet 16") for n in GERAETE],
    )

    seiten = leite_ab(wurzel, lade_katalog(wurzel), set())

    assert len(seiten) == HOECHSTE_SEITEN_JE_ANBIETER
    assert {s.anbieter for s in seiten} == {"o2"}


def test_kommentar_der_klickliste_nennt_plaetze_und_rotation():
    """Die Config sagte „höchstens 8 Seiten“; gemeint waren Plätze."""
    text = (WURZEL / TAGESDATEI).read_text(encoding="utf-8")
    kopf = text.split("anbieter:", 1)[0]

    assert "höchstens 8 Seiten" not in kopf
    assert "8 Plätzen" in kopf
    assert "keine Seitengrenze" in kopf
    assert "veraltetes Bündel" in kopf
