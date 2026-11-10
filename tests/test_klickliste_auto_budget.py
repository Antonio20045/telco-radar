"""Klickliste aus dem Katalog: kein Platz fällt heraus, die Rotation trägt das Budget.

Ein Platz (Gerät und Stufe) hat bei Telekom bis zu fünf Seiten, acht Plätze also bis zu
40. Eine Telekom-Seite braucht bis zu ``SEITENZEIT_S``, ein Matrix-Job hat rund
10.258 s: 40 Seiten passen nicht in einen Lauf, die Rotation des Tageslaufs
(``klicktageslauf``, Lesestand) liest die übrigen am nächsten Tag zuerst. Die Liste
darf dabei keinen Platz verlieren: ein Bündel, das drei Tage nicht gelesen wurde, ist
„veraltet“ und bleibt Quelle seiner Adresse (Prüfung PR 85, 10.11.2026; der Stand
2d15fe31 warf es weg, der Platz kam nie zurück). Nach ``QUELLE_HOECHSTALTER_TAGE``
nicht mehr: ein Gerät, das der Anbieter nicht mehr führt, bliebe sonst ewig. Die Frist
rechnet je Anbieter ab dessen jüngstem Bündel, nicht ab dem des Gesamtbestands; ein
Platz, der herausfällt, steht als Warnung im Log (Nachprüfung PR 85b, S1, S4).

Die Tage laufen mit dem echten ``leite_ab`` und dem echten ``fahre``; Uhr und Crawler
sind Attrappen, die Alterung der Bündel ist die der Prüfstelle (Regel 16,
``FRISCHEGRENZE_TAGE``). Kein Browser, kein Netz. Nach der letzten Seite wartet der Lauf
noch den Seitenabstand und prüft dann erst die Frist: die Uhr endet bis zu 60 s nach
``ende`` (480 s Reserve), darum gilt die Grenze ``ende`` plus Seitenabstand.
"""

from __future__ import annotations

import json
import logging
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
NIE_GELESEN = (len(GERAETE) - HOECHSTE_SEITEN_JE_ANBIETER) * len(TARIFE)
"""Bündel der Geräte jenseits der Platzgrenze: sie stehen in keiner Liste und altern."""
EINRICHTUNG_S = 62
JOBBUDGET_S = JOB_FRIST_S - RESERVE_S - EINRICHTUNG_S
SEITENABSTAND_S = 60.0
SEITENZEIT_S = 330
"""Zeit je Telekom-Seite einschließlich 60 s Seitenabstand (Regelfall). Gemessen als
Dauer des Jobs durch gelesene Seiten (``data/state/klick/telekom-*.json``, 211
Tagesergebnisse seit dem 03.11.2026, ohne den Job mit Übersichten): Mittel 266 s,
95. Perzentil 299 s, schlechtester Job 320,6 s (``telekom-9``, 09.11.2026). Die Dateien
kennen nur die Dauer je Job, nicht je Seite; 330 s liegt darüber."""
SEITENZEITEN_S = (SEITENZEIT_S, 400)
"""Die Budget-Prüfungen laufen mit der gemessenen und mit einer deutlich langsameren
Seite: bei 400 s passen nur 25 Seiten in einen Job, die Rotation trägt trotzdem."""


def seiten_je_lauf(seitenzeit: float) -> int:
    """Seiten, die ganz in einen Job passen (330 s: 31, 400 s: 25); die letzte endet
    vor dem Budget."""
    return int((JOBBUDGET_S - (seitenzeit - SEITENABSTAND_S)) // seitenzeit + 1)


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


@pytest.fixture(params=SEITENZEITEN_S, ids=lambda s: f"{s}s")
def seitenzeit(request) -> int:
    return request.param


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


def _crawler(uhr: Uhr, seitenzeit: float):
    """Jede Seite braucht ``seitenzeit`` mit Abstand; reicht die Grenze nicht, endet
    sie an der Zeitgrenze und gilt nicht als gelesen."""
    dauer = seitenzeit - SEITENABSTAND_S

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

    def __init__(
        self,
        wurzel: Path,
        karte,
        anfang: date,
        seitenzeit: float = SEITENZEIT_S,
        verlorene_messtage: frozenset[date] = frozenset(),
    ):
        """``verlorene_messtage``: Tage, deren Messungen nie im Bestand ankommen. Die
        Lesung selbst gelingt und steht im Lesestand des Tageslaufs, aber das Bündel
        behält sein altes Datum (08.11.: Geräte-Lauf vor Klick-Lauf, die Datei „von
        gestern“ ist für ``klick_zusammenfuehrung`` keine Messung)."""
        self.wurzel, self.karte = wurzel, karte
        self.bestand = _alle_plaetze(anfang)
        self.seitenzeit = seitenzeit
        self.verlorene_messtage = verlorene_messtage
        self.stand: dict[str, str] = {}
        self.listen: list[set[str]] = []
        self.gelesen: list[set[str]] = []
        self.veraltet: list[int] = []
        self.dauer: list[float] = []

    def tag(self, heute: date, ausfall: bool = False) -> set[str]:
        """Ein Tag: Alterung, Liste ableiten, lesen (außer am Ausfalltag)."""
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
            _crawler(uhr, self.seitenzeit),
            heute.isoformat(),
            ende,
            gelesen=self.stand,
            uhr=uhr,
            schlafe=uhr.schlafe,
        )
        assert uhr.jetzt <= ende + SEITENABSTAND_S, "der Lauf überschritt das Budget"
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
        if heute not in self.verlorene_messtage:
            for eintrag in self.bestand:
                if eintrag["quelle_url"] in gelesen:
                    eintrag["abgerufen_am"] = heute.isoformat()
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


def test_rotation_traegt_das_budget_bei_40_seiten(wurzel, karte, seitenzeit):
    """40 Seiten sind mehr als ein Job: jeder Tag liest höchstens ``seiten_je_lauf``
    Seiten und bleibt im Budget (geprüft in ``Verlauf.tag``), jede Seite kommt alle
    zwei Tage dran, bei 330 s wie bei 400 s."""
    je_lauf = seiten_je_lauf(seitenzeit)
    assert ALLE_SEITEN * seitenzeit > JOBBUDGET_S, "dann trüge die Rotation nichts"

    verlauf = Verlauf(wurzel, karte, TAG0 - timedelta(days=1), seitenzeit)
    for tag in range(10):
        verlauf.tag(TAG0 + timedelta(days=tag))

    assert all(len(liste) == ALLE_SEITEN for liste in verlauf.listen)
    assert max(len(g) for g in verlauf.gelesen) == je_lauf
    assert min(len(g) for g in verlauf.gelesen) >= ALLE_SEITEN - je_lauf
    assert len(verlauf.lesetage()) == ALLE_SEITEN, "eine Seite kam nie dran"
    assert verlauf.groesste_luecke() == 2
    assert max(verlauf.dauer) <= JOBBUDGET_S + SEITENABSTAND_S
    assert max(verlauf.veraltet) == NIE_GELESEN, (
        "die Rotation lässt keinen Preis altern"
    )


def test_ausfalltag_verliert_keinen_platz_und_liest_das_aelteste_zuerst(
    wurzel, karte, seitenzeit
):
    """Zwei Tage fallen aus (Job rot): die Bündel werden drei Tage alt und „veraltet“.
    Die Plätze bleiben in der Liste und kommen zuerst dran (Stand 2d15fe31: ab dem
    Folgetag fehlten sie dauerhaft)."""
    verlauf = Verlauf(wurzel, karte, TAG0 - timedelta(days=1), seitenzeit)
    for tag in range(12):
        verlauf.tag(TAG0 + timedelta(days=tag), ausfall=tag in (3, 4))

    assert max(verlauf.veraltet) > 0, "die Alterung auf veraltet wurde nie erreicht"
    assert all(liste == verlauf.listen[0] for liste in verlauf.listen)
    assert len(verlauf.listen[0]) == ALLE_SEITEN
    assert len(verlauf.lesetage()) == ALLE_SEITEN
    assert not verlauf.gelesen[3] and not verlauf.gelesen[4]
    assert verlauf.groesste_luecke() <= 2 + 2, "länger ungelesen als der Ausfall"


def test_fehlender_messtag_im_bestand_laesst_liste_und_rotation_heil(
    wurzel, karte, seitenzeit
):
    """Der echte Fall vom 08.11.: Der Geräte-Lauf lief vor dem Klick-Lauf, die Messungen
    dieses Tages fehlen im Bestand (``klick_zusammenfuehrung`` wertet die Datei „von
    gestern“ nicht als Messung). Der Lesestand des Tageslaufs ist aktuell: die Liste
    bleibt vollständig und die Rotation unberührt. Nicht heil bleiben die Preise: die
    Bündel dieses Tages behalten ihr altes Datum und sind einen Tag früher „veraltet“
    (hier: die Bündel dieses Tages werden vier statt zwei Tage alt)."""
    fehlt = TAG0 + timedelta(days=3)
    ohne = Verlauf(wurzel, karte, TAG0 - timedelta(days=1), seitenzeit)
    mit = Verlauf(
        wurzel, karte, TAG0 - timedelta(days=1), seitenzeit, frozenset({fehlt})
    )
    for tag in range(12):
        ohne.tag(TAG0 + timedelta(days=tag))
    for tag in range(12):
        mit.tag(TAG0 + timedelta(days=tag))

    assert all(len(liste) == ALLE_SEITEN for liste in mit.listen)
    assert len(mit.lesetage()) == ALLE_SEITEN
    assert mit.groesste_luecke() == 2
    assert mit.gelesen == ohne.gelesen, "der Lesestand hängt nicht vom Bestand ab"
    assert max(ohne.veraltet) == NIE_GELESEN
    assert max(mit.veraltet) > NIE_GELESEN, "ohne Messtag altern Preise"


def test_fehlender_messtag_und_ausfall_zusammen(wurzel, karte, seitenzeit):
    verlauf = Verlauf(
        wurzel,
        karte,
        TAG0 - timedelta(days=1),
        seitenzeit,
        frozenset({TAG0 + timedelta(days=2), TAG0 + timedelta(days=3)}),
    )
    for tag in range(14):
        verlauf.tag(TAG0 + timedelta(days=tag), ausfall=tag == 5)

    assert all(len(liste) == ALLE_SEITEN for liste in verlauf.listen)
    assert len(verlauf.lesetage()) == ALLE_SEITEN
    assert verlauf.groesste_luecke() <= 3


def test_alterung_auf_veraltet_nimmt_keine_seite_aus_der_liste(
    wurzel, karte, seitenzeit
):
    """Sieben Tage ohne Lesung: alle Bündel sind „veraltet“, alle 40 Seiten stehen noch
    in der Liste. Der erste Lauf danach liest die ältesten, der zweite den Rest."""
    verlauf = Verlauf(wurzel, karte, TAG0 - timedelta(days=1), seitenzeit)
    for tag in range(2):
        verlauf.tag(TAG0 + timedelta(days=tag))
    for tag in range(2, 9):
        verlauf.tag(TAG0 + timedelta(days=tag), ausfall=True)

    assert verlauf.veraltet[-1] == len(GERAETE) * len(TARIFE)
    assert verlauf.listen[-1] == verlauf.listen[0]
    assert len(verlauf.listen[-1]) == ALLE_SEITEN

    erster = verlauf.tag(TAG0 + timedelta(days=9))
    zweiter = verlauf.tag(TAG0 + timedelta(days=10))

    assert len(erster) == seiten_je_lauf(seitenzeit)
    assert verlauf.listen[-1] - erster <= zweiter, "eine Seite wartete länger als nötig"


def test_ausfall_eines_anbieters_leert_seine_liste_nicht(wurzel, tage):
    """S1: Telekom wird ``tage`` Tage nicht gelesen (Sperre, Strukturbruch), alle
    anderen Anbieter täglich. Die Frist rechnet ab dem jüngsten Bündel der Telekom:
    ihre 40 Seiten bleiben. Mit dem Anker im Gesamtbestand war die Liste ab dem 15. Tag
    leer und kam nie zurück (es gäbe nie wieder ein jüngeres Telekom-Bündel)."""
    telekom = _alle_plaetze(TAG0 - timedelta(days=tage))
    for eintrag in telekom:
        eintrag["pruefung"] = "veraltet 16"
    o2 = [_buendel(n, "", TAG0, "o2") for n in GERAETE[:3]]
    _bestand(wurzel, [*telekom, *o2])

    seiten = leite_ab(wurzel, lade_katalog(wurzel), set())

    assert len([s for s in seiten if s.anbieter == "Telekom"]) == ALLE_SEITEN
    assert len([s for s in seiten if s.anbieter == "o2"]) == 3


@pytest.fixture(params=(15, 16, 40), ids=lambda t: f"{t}tage")
def tage(request) -> int:
    return request.param


def test_herausfallender_platz_steht_als_warnung_im_log(wurzel, caplog):
    """S1: Ein Platz, den die 14-Tage-Grenze entfernt, fällt nicht stumm heraus: das
    Log nennt Anbieter, Gerät und Stufe. Gegenprobe: ohne herausfallenden Platz keine
    Warnung dieser Klickliste."""
    bestand = [
        _buendel(GERAETE[0], TARIFE[0], TAG0),
        _buendel(
            GERAETE[1],
            TARIFE[0],
            TAG0 - timedelta(days=20),
            pruefung="veraltet 16",
        ),
    ]
    _bestand(wurzel, bestand)

    with caplog.at_level(logging.WARNING, logger="telco_radar"):
        seiten = leite_ab(wurzel, lade_katalog(wurzel), set())

    assert {s.geraet for s in seiten} == {GERAETE[0]}
    warnungen = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnungen) == 1
    assert "Telekom" in warnungen[0]
    assert f"{GERAETE[1]} 256 GB" in warnungen[0]
    assert f"{GERAETE[0]} 256 GB" not in warnungen[0]

    caplog.clear()
    _bestand(wurzel, bestand[:1])
    with caplog.at_level(logging.WARNING, logger="telco_radar"):
        leite_ab(wurzel, lade_katalog(wurzel), set())
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_warnung_nennt_keinen_platz_den_ein_anderes_buendel_haelt(wurzel, caplog):
    """Ein altes Bündel desselben Platzes neben einem nutzbaren ist kein Verlust."""
    alt = _buendel(
        GERAETE[1], TARIFE[0], TAG0 - timedelta(days=20), pruefung="veraltet 16"
    )
    neu = _buendel(GERAETE[1], TARIFE[1], TAG0)
    _bestand(wurzel, [alt, neu])

    with caplog.at_level(logging.WARNING, logger="telco_radar"):
        leite_ab(wurzel, lade_katalog(wurzel), set())

    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_frische_stufe_geht_vor_der_kleineren_veralteten_bei_telekom(wurzel):
    """S4: Telekom hat die 256-GB-Seite (5 Tage alt, „veraltet“) und die 512-GB-Seite
    frisch im Bestand. Die Stufenwahl nimmt die kleinste Stufe: das war die tote
    256er-Adresse und verdrängte die frische 512er (main: 512er)."""
    n = GERAETE[0]
    alt = _buendel(n, TARIFE[2], TAG0 - timedelta(days=5), pruefung="veraltet 16")
    frisch = _buendel(n, TARIFE[2], TAG0)
    frisch["sku_id"] = f"{n}-512gb-x"
    frisch["quelle_url"] = SEITE.format(n=n, t=TARIFE[2]).replace("256", "512")
    _bestand(wurzel, [alt, frisch])

    seiten = leite_ab(wurzel, lade_katalog(wurzel), set())

    assert [(s.speicher_gb, s.url) for s in seiten] == [(512, frisch["quelle_url"])]


def test_frische_stufe_geht_vor_der_kleineren_veralteten_bei_gleicher_adresse(wurzel):
    """S4, andere Seite derselben Wahl: Eine Adresse ohne Stufe steht für mehrere
    Stufen (o2). Die frische 512er gilt vor der veralteten 256er, auch wenn die
    kleinere Stufe sonst gewinnt."""
    n = GERAETE[0]
    adresse = "https://www.o2online.de/e-shop/samsung/samsung-galaxy-s26/?tarif=m"
    alt = _buendel(n, "", TAG0 - timedelta(days=5), "o2", "veraltet 16")
    frisch = _buendel(n, "", TAG0, "o2")
    frisch["sku_id"] = f"{n}-512gb-x"
    for eintrag in (alt, frisch):
        eintrag["quelle_url"] = adresse
    _bestand(wurzel, [alt, frisch])

    seiten = leite_ab(wurzel, lade_katalog(wurzel), set())

    assert [(s.speicher_gb, s.url) for s in seiten] == [(512, adresse)]


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
