"""Abnahme der Geräteseite ohne Netz: Stichprobe, Goldliste, Stand (Datenkonzept 11)."""

from __future__ import annotations

import importlib
import json
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import pytest

from telco_radar.analyze import geraete_abnahme as abnahme
from telco_radar.analyze import geraete_goldliste as gold
from telco_radar.analyze.geraete_pruefstatus import satz_zaehlt
from telco_radar.geraete_config import lade_katalog
from telco_radar.geraete_model import Geraet, Katalog
from telco_radar.report import geraete_notbremse as notbremse
from telco_radar.report.geraete_tco_karten import geraet_aus_sku
from telco_radar.tco_model import buendel_id

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL / "scripts"))
abnahme_stand = importlib.import_module("abnahme_stand")
TAG = "2026-10-07"
KATALOG = Katalog(
    geraete=[
        Geraet(hersteller="Apple", modell="iPhone 17 Pro", speicher=[256, 512]),
        Geraet(hersteller="Google", modell="Pixel 11", speicher=[256]),
    ]
)
ABGELAUFEN = {
    "art": "geraeterabatt",
    "bedingung": "Online-Rabatt",
    "quelle_url": "https://example.invalid/aktion",
    "betrag": 50.0,
    "eingerechnet": True,
    "gueltig_bis": "2026-10-01",
}


def _geraet_von(sku: str) -> tuple[str, int | None]:
    return geraet_aus_sku(sku, KATALOG)


def _satz(
    anbieter: str = "o2",
    sku: str = "apple-iphone-17-pro-256gb-silber",
    tarif: str = "Tarif S",
    laufzeit: int | None = 24,
    **mehr: object,
) -> dict:
    return {
        "id": buendel_id(sku, anbieter, tarif, laufzeit),
        "sku_id": sku,
        "anbieter": anbieter,
        "tarif_name": tarif,
        "laufzeit_monate": laufzeit,
        "herleitung": "",
        "aktionen": [],
        **mehr,
    }


def _bestand(anbieter: str = "o2", zahl: int = 40) -> list[dict]:
    return [
        _satz(anbieter, f"google-pixel-11-256gb-farbe{n}", f"Tarif {n % 4}")
        for n in range(zahl)
    ]


def _ids(saetze: list) -> list[str]:
    return [s["id"] for s in saetze]


def _punkt(punkte: list[abnahme.Pruefpunkt], name: str) -> abnahme.Pruefpunkt:
    return next(p for p in punkte if p.name == name)


def _proben(*zeilen: tuple[str, str, str, str]) -> abnahme.Probenprotokoll:
    text = "\n".join(
        json.dumps(
            {"tag": t, "anbieter": a, "buendel": b, "ergebnis": e, "beleg": "s.webp"}
        )
        for t, a, b, e in zeilen
    )
    return abnahme.lies_proben(text)


def _tage(anzahl: int) -> list[str]:
    erster = date(2026, 11, 1)
    return [(erster + timedelta(days=n)).isoformat() for n in range(anzahl)]


def test_stichprobe_ist_deterministisch_und_haengt_am_tag():
    bestand = _bestand()
    erste = abnahme.stichprobe(bestand, "o2", TAG, 10)
    zweite = abnahme.stichprobe(list(reversed(bestand)), "o2", TAG, 10)
    anderer_tag = abnahme.stichprobe(bestand, "o2", "2026-10-08", 10)
    assert _ids(erste) == _ids(zweite)
    assert set(_ids(erste)) != set(_ids(anderer_tag))


def test_stichprobe_zieht_nur_zaehlende_buendel_des_anbieters():
    zaehlend = _bestand(zahl=5)
    fremd = [
        _satz("o2", "google-pixel-11-256gb-a", "Tarif X", herleitung="tarifsumme"),
        _satz("o2", "google-pixel-11-256gb-b", "Tarif X", pruefung="quarantaene 3"),
        _satz("o2", "google-pixel-11-256gb-c", "Tarif X", aktionen=[ABGELAUFEN]),
        *_bestand("Vodafone", 5),
    ]
    gezogen = abnahme.stichprobe(zaehlend + fremd, "o2", TAG, 10)
    assert sorted(_ids(gezogen)) == sorted(_ids(zaehlend))
    vor_dem_ende = abnahme.stichprobe(fremd, "o2", "2026-09-30", 10)
    assert _ids(vor_dem_ende) == [fremd[2]["id"]]


@pytest.mark.parametrize("anzahl", [10, 15, 20])
def test_stichprobe_haelt_die_anzahl_ein(anzahl):
    assert len(abnahme.stichprobe(_bestand(), "o2", TAG, anzahl)) == anzahl
    assert len(abnahme.stichprobe(_bestand(zahl=7), "o2", TAG, anzahl)) == 7


@pytest.mark.parametrize("anzahl", [9, 21])
def test_stichprobe_ausserhalb_der_grenzen_ist_ein_fehler(anzahl):
    with pytest.raises(ValueError, match="Stichprobe"):
        abnahme.stichprobe(_bestand(), "o2", TAG, anzahl)


def test_seite_und_abnahme_zaehlen_dieselben_buendel():
    saetze = [
        _satz(),
        _satz(herleitung="tarifaufschlag"),
        _satz(aktionen=[ABGELAUFEN]),
        _satz(pruefung="gueltig"),
        _satz(pruefung="veraltet 16"),
        _satz(pruefung="unbekannt RuntimeError"),
    ]
    for tag in ("2026-09-30", TAG):
        seite = [notbremse.felder_aus_satz(s, tag)["zaehlt"] for s in saetze]
        assert [satz_zaehlt(s, tag) for s in saetze] == seite
    assert sum(satz_zaehlt(s, TAG) for s in saetze) == 2


def _eintrag(**mehr: object) -> dict:
    return {
        "device_id": "google-pixel-11",
        "speicher_gb": 256,
        "tarif_name": "Tarif S",
        "laufzeit_monate": 24,
        **mehr,
    }


def test_goldliste_hoechstens_zehn_je_anbieter():
    elf = [_eintrag(tarif_name=f"Tarif {n}") for n in range(11)]
    with pytest.raises(gold.GoldlisteFehler, match="1 bis 10"):
        gold.goldliste_aus({"anbieter": {"o2": elf}})
    assert len(gold.goldliste_aus({"anbieter": {"o2": elf[:10]}})) == 10


def test_goldliste_variante_doppelt_ist_ein_fehler():
    doppelt = [_eintrag(farbe="frost"), _eintrag(farbe="schwarz")]
    with pytest.raises(gold.GoldlisteFehler, match="doppelt"):
        gold.goldliste_aus({"anbieter": {"o2": doppelt}})


def test_goldliste_beispielseite_steht_zuerst():
    beispiel = _eintrag(device_id="apple-iphone-17-pro")
    with pytest.raises(gold.GoldlisteFehler, match="Beispielseite"):
        gold.goldliste_aus({"anbieter": {"o2": [_eintrag(), beispiel]}})
    liste = gold.goldliste_aus({"anbieter": {"o2": [beispiel, _eintrag()]}})
    assert [e.beispielseite for e in liste] == [True, False]


@pytest.mark.parametrize(
    "falsch",
    [
        _eintrag(titel="iPhone 17 Pro"),
        _eintrag(speicher_gb="256"),
        _eintrag(laufzeit_monate=48),
        {"device_id": "google-pixel-11", "speicher_gb": 256, "laufzeit_monate": 24},
    ],
)
def test_goldliste_nur_stabile_schluessel(falsch):
    with pytest.raises(gold.GoldlisteFehler):
        gold.goldliste_aus({"anbieter": {"o2": [falsch]}})


def test_goldliste_findet_genau_ein_buendel_oder_benennt_den_befund():
    bestand = [
        _satz("o2", "google-pixel-11-256gb-frost"),
        _satz("o2", "google-pixel-11-256gb-schwarz"),
        _satz("o2", "apple-iphone-17-pro-256gb-silber"),
        _satz("o2", "apple-iphone-17-pro-512gb-silber"),
    ]
    liste = gold.goldliste_aus(
        {
            "anbieter": {
                "o2": [
                    _eintrag(device_id="apple-iphone-17-pro"),
                    _eintrag(laufzeit_monate=36),
                    _eintrag(tarif_name="Tarif M", farbe="frost"),
                    _eintrag(tarif_name="Tarif S"),
                ],
                "Vodafone": [_eintrag(farbe="frost")],
            }
        }
    )
    ergebnis = gold.goldliste_aufloesen(liste, bestand, _geraet_von)
    assert ergebnis[0].buendel is bestand[2]
    assert [a.befund for a in ergebnis[1:3]] == [gold.NICHT_GEFUNDEN] * 2
    assert ergebnis[3].befund == gold.MEHRDEUTIG
    assert ergebnis[3].kandidaten == tuple(sorted(_ids(bestand[:2])))
    assert ergebnis[4].befund == gold.NICHT_GEFUNDEN
    mit_farbe = gold.Goldeintrag("o2", "google-pixel-11", 256, "Tarif S", 24, "frost")
    [treffer] = gold.goldliste_aufloesen([mit_farbe], bestand, _geraet_von)
    assert treffer.buendel is bestand[0]
    assert treffer.befund is None


def test_echte_goldliste_hat_ihre_form(tmp_path):
    liste = gold.lade_goldliste(WURZEL)
    je_anbieter = Counter(e.anbieter for e in liste)
    assert set(je_anbieter) == {"o2", "Vodafone", "1&1", "Telekom", "congstar"}
    assert set(je_anbieter.values()) == {gold.GOLD_JE_ANBIETER}
    assert len({e.variante for e in liste}) == len(liste)
    erste = {e.anbieter: e for e in reversed(liste)}
    assert all(e.beispielseite for e in erste.values())
    (tmp_path / "config").symlink_to(WURZEL / "config", target_is_directory=True)
    katalog = {g.device_id: g for g in lade_katalog(tmp_path).geraete}
    assert {e.device_id for e in liste} <= set(katalog)
    assert all(
        not katalog[e.device_id].speicher
        or e.speicher_gb in katalog[e.device_id].speicher
        for e in liste
    )


def test_beleganteil_zaehlt_nur_belegte_zaehlende_buendel():
    bestand = _bestand(zahl=4)
    punkt = _punkt(abnahme.stand(bestand, TAG), abnahme.PUNKT_BELEG)
    assert (punkt.status, punkt.zahl) == (abnahme.ROT, 0)
    bestand[0] |= {"beleg_id": "a" * 64, "beleg_status": "belegt"}
    bestand[1] |= {"beleg_id": "b" * 64, "beleg_status": "offen"}
    bestand.append(
        _satz(herleitung="x", beleg_id="c" * 64, beleg_status="belegt", tarif="Z")
    )
    punkt = _punkt(abnahme.stand(bestand, TAG), abnahme.PUNKT_BELEG)
    assert (punkt.status, punkt.zahl) == (abnahme.ROT, 25)
    assert punkt.grund.startswith("1 von 4 ")
    for satz in bestand[1:4]:
        satz |= {"beleg_id": "d" * 64, "beleg_status": "belegt"}
    punkt = _punkt(abnahme.stand(bestand, TAG), abnahme.PUNKT_BELEG)
    assert (punkt.status, punkt.zahl) == (abnahme.GRUEN, 100)


def test_anteil_rundet_ab_und_hundert_heisst_alle():
    bestand = _bestand(zahl=200)
    for satz in bestand[:199]:
        satz |= {"beleg_id": "a" * 64, "beleg_status": "belegt"}
    punkt = _punkt(abnahme.stand(bestand, TAG), abnahme.PUNKT_BELEG)
    assert (punkt.status, punkt.zahl) == (abnahme.ROT, 99)
    punkt = _punkt(abnahme.stand(bestand[:3], TAG), abnahme.PUNKT_BELEG)
    assert (punkt.status, punkt.zahl) == (abnahme.GRUEN, 100)
    punkt = _punkt(
        abnahme.stand([*bestand[:2], bestand[199]], TAG), abnahme.PUNKT_BELEG
    )
    assert (punkt.status, punkt.zahl) == (abnahme.ROT, 66)


def test_ohne_daten_ist_nichts_gruen():
    punkte = abnahme.stand([], TAG)
    assert [p.name for p in punkte] == [
        abnahme.PUNKT_BELEG,
        abnahme.PUNKT_WOERTLICH,
        abnahme.PUNKT_VARIANTE,
        abnahme.PUNKT_LAUFZEIT,
        abnahme.PUNKT_STICHPROBE,
        abnahme.PUNKT_GEGENPROBE,
        abnahme.PUNKT_BEISPIEL,
        abnahme.PUNKT_OPTIK,
    ]
    assert {p.status for p in punkte} == {abnahme.OFFEN}
    assert all(p.grund for p in punkte)
    bestand = abnahme.stand(_bestand(zahl=3), TAG)
    offen = [p.name for p in bestand if p.status == abnahme.OFFEN]
    assert abnahme.PUNKT_WOERTLICH in offen
    assert abnahme.PUNKT_VARIANTE in offen
    assert abnahme.GRUEN not in {p.status for p in bestand}


def test_laufzeit_ist_rot_wenn_die_id_eine_andere_laufzeit_traegt():
    bestand = _bestand(zahl=4)
    punkt = _punkt(abnahme.stand(bestand, TAG), abnahme.PUNKT_LAUFZEIT)
    assert (punkt.status, punkt.zahl) == (abnahme.OFFEN, 100)
    bestand[0]["laufzeit_monate"] = 36
    punkt = _punkt(abnahme.stand(bestand, TAG), abnahme.PUNKT_LAUFZEIT)
    assert (punkt.status, punkt.zahl) == (abnahme.ROT, 75)
    bestand[0] = _satz("o2", "google-pixel-11-256gb-x", "Tarif X", 48)
    bestand[1] = _satz("o2", "google-pixel-11-256gb-y", "Tarif X", None)
    punkt = _punkt(abnahme.stand(bestand, TAG), abnahme.PUNKT_LAUFZEIT)
    assert (punkt.status, punkt.zahl) == (abnahme.ROT, 50)
    assert punkt.grund.startswith("2 von 4 ")


def test_fehlendes_protokoll_ist_offen_und_nie_gruen():
    punkt = _punkt(abnahme.stand(_bestand(), TAG), abnahme.PUNKT_STICHPROBE)
    assert (punkt.status, punkt.zahl) == (abnahme.OFFEN, 0)
    assert "30" in punkt.grund


def test_dreissig_fehlerfreie_proben_in_folge_sind_gruen():
    tage = _tage(abnahme.PROBEN_IN_FOLGE)
    neunundzwanzig = _proben(*((t, "o2", "b1", abnahme.OK) for t in tage[1:]))
    punkt = _punkt(
        abnahme.stand(_bestand(), TAG, neunundzwanzig), abnahme.PUNKT_STICHPROBE
    )
    assert (punkt.status, punkt.zahl) == (abnahme.OFFEN, 29)
    dreissig = _proben(*((t, "o2", "b1", abnahme.OK) for t in tage))
    punkt = _punkt(abnahme.stand(_bestand(), TAG, dreissig), abnahme.PUNKT_STICHPROBE)
    assert (punkt.status, punkt.zahl) == (abnahme.GRUEN, 30)
    zwei_anbieter = _bestand() + _bestand("Vodafone", 1)
    punkt = _punkt(
        abnahme.stand(zwei_anbieter, TAG, dreissig), abnahme.PUNKT_STICHPROBE
    )
    assert (punkt.status, punkt.zahl) == (abnahme.OFFEN, 0)


def test_ein_fehler_setzt_die_folge_zurueck():
    tage = _tage(abnahme.PROBEN_IN_FOLGE + 6)
    zeilen = [(t, "o2", "b1", abnahme.OK) for t in tage[:30]]
    zeilen += [(tage[30], "o2", "b2", abnahme.OK), (tage[30], "o2", "b3", "fehler")]
    zeilen += [(t, "o2", "b1", abnahme.OK) for t in tage[31:]]
    punkt = _punkt(
        abnahme.stand(_bestand(), TAG, _proben(*zeilen)), abnahme.PUNKT_STICHPROBE
    )
    assert (punkt.status, punkt.zahl) == (abnahme.ROT, 5)
    folge = abnahme.folgen(_proben(*zeilen).proben)["o2"]
    assert (folge.fehlerfrei, folge.fehler) == (5, 1)


def test_dieselbe_probe_am_selben_tag_zaehlt_einmal_und_der_fehler_gewinnt():
    zeilen = [("2026-11-01", "o2", "b1", abnahme.OK)] * 3
    assert abnahme.folgen(_proben(*zeilen).proben)["o2"].fehlerfrei == 1
    zeilen.append(("2026-11-01", "o2", "b1", abnahme.FEHLER))
    assert abnahme.folgen(_proben(*zeilen).proben)["o2"] == abnahme.Folge(0, 1)


def test_probe_ohne_beleg_oder_unlesbar_zaehlt_nicht():
    text = "\n".join(
        [
            json.dumps({"tag": "2026-11-01", "anbieter": "o2", "buendel": "b1"}),
            json.dumps(
                {
                    "tag": "2026-11-01",
                    "anbieter": "o2",
                    "buendel": "b1",
                    "ergebnis": "vielleicht",
                    "beleg": "s.webp",
                }
            ),
            "kein json",
            "",
        ]
    )
    protokoll = abnahme.lies_proben(text)
    assert (protokoll.proben, protokoll.unlesbar) == ((), 3)
    tage = _tage(abnahme.PROBEN_IN_FOLGE)
    gute = [
        json.dumps(
            {"tag": t, "anbieter": "o2", "buendel": "b", "ergebnis": "ok", "beleg": "x"}
        )
        for t in tage
    ]
    protokoll = abnahme.lies_proben("\n".join([*gute, "kein json"]))
    punkt = _punkt(abnahme.stand(_bestand(), TAG, protokoll), abnahme.PUNKT_STICHPROBE)
    assert (punkt.status, punkt.zahl) == (abnahme.OFFEN, 30)


SKRIPT_KATALOG = (
    "geraete:\n  - {hersteller: Apple, modell: iPhone 17 Pro, speicher: [256]}\n"
)
SKRIPT_GOLDLISTE = {
    "anbieter": {
        "o2": [_eintrag(device_id="apple-iphone-17-pro", farbe="silber")],
        "Vodafone": [_eintrag(device_id="apple-iphone-17-pro")],
    }
}


def _skript_wurzel(tmp_path: Path, saetze: list[dict]) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "geraete_katalog.yaml").write_text(SKRIPT_KATALOG)
    (tmp_path / gold.GOLDLISTE).write_text(json.dumps(SKRIPT_GOLDLISTE))
    (tmp_path / "data" / "state").mkdir(parents=True)
    bestand = {"updated": TAG, "buendel": saetze}
    (tmp_path / "data" / "state" / "geraete_tco.json").write_text(json.dumps(bestand))
    return tmp_path


def test_skript_meldet_rot_mit_exit_null_und_zieht_nur_mit_tag(tmp_path, capsys):
    wurzel = _skript_wurzel(tmp_path, [_satz(), *_bestand(zahl=11)])
    assert abnahme_stand.main(["--wurzel", str(wurzel)]) == 0
    ausgabe = capsys.readouterr().out
    assert f"Tag {TAG}: 12 Bündel, 12 zählend" in ausgabe
    beleg = next(z for z in ausgabe.splitlines() if z.startswith(abnahme.PUNKT_BELEG))
    assert beleg.split()[5:8] == [abnahme.ROT, "0", "%"]
    assert "Goldliste (config/geraete_goldliste.yaml): 1 von 2 gefunden" in ausgabe
    assert f"   1  {_satz()['id']}: zählt, Stand " in ausgabe
    assert f"24 Raten: {gold.NICHT_GEFUNDEN}" in ausgabe
    assert "Stichprobe" not in ausgabe.split("Goldliste")[1]
    assert abnahme_stand.main(["--wurzel", str(wurzel), "--tag", "2026-11-02"]) == 0
    ausgabe = capsys.readouterr().out
    assert "Stichprobe 2026-11-02, je Anbieter 10 zählende Bündel\no2: 10\n" in ausgabe


@pytest.mark.parametrize("falsch", [["--tag", "07.10.2026"], ["--anzahl", "21"]])
def test_skript_weist_falschen_tag_und_anzahl_ab(tmp_path, falsch):
    wurzel = _skript_wurzel(tmp_path, _bestand(zahl=3))
    with pytest.raises(SystemExit) as fehler:
        abnahme_stand.main(["--wurzel", str(wurzel), *falsch])
    assert fehler.value.code == 2
