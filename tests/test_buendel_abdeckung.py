"""Der Bündel-Abdeckungswächter: ein Anbieter ohne Bündel, ein fehlendes
Pflichtmodell, verlorene Kombinationen und Preissprünge machen den Lauf rot.

Die Telekom lieferte vom 15.09.2026 an kein Bündel, und kein Lauf wurde rot:
der ältere Wächter vergleicht nur mit dem Vortag. Diese Tests halten fest,
dass die neue Prüfung gegen die Pflichtliste misst.
"""

import json
from datetime import date
from pathlib import Path

import pytest

from telco_radar.analyze.buendel_abdeckung import (
    KOMBI_VERLUST_MINDEST,
    PREISSPRUNG_ANTEIL,
    als_markdown,
    lade_pflicht,
    modell_und_speicher,
    pruefe,
)

TAG = "2026-03-10"
VORTAG = "2026-03-09"


def _buendel(anbieter, sku, tarif="T S", laufzeit=24, tag=TAG):
    return {
        "anbieter": anbieter,
        "sku_id": sku,
        "tarif_name": tarif,
        "laufzeit_monate": laufzeit,
        "last_verified": tag,
        "zustand": "neu",
    }


def _pflicht(anbieter=("A", "B"), modelle=("apple-iphone-18-pro",), luecken=None):
    return {
        "anbieter": list(anbieter),
        "modelle": list(modelle),
        "luecken": dict(luecken or {}),
    }


def _hist(anbieter_slug, n, tag, gesamt=1000.0, start=0):
    return [
        {
            "id": f"buendel--{anbieter_slug}--sku-{i}--t",
            "datum": tag,
            "gesamt": gesamt,
            "zustand": "neu",
        }
        for i in range(start, start + n)
    ]


def test_modell_und_speicher_aus_sku():
    assert modell_und_speicher("apple-iphone-18-pro-256gb-polar") == (
        "apple-iphone-18-pro",
        "256gb",
    )
    assert modell_und_speicher("samsung-galaxy-s26-ultra-1024gb-grau-refurbished") == (
        "samsung-galaxy-s26-ultra",
        "1024gb",
    )
    assert modell_und_speicher("ohne-speicherangabe") == (None, None)


def test_anbieter_ohne_buendel_ist_rot_auch_ohne_vortag():
    """Der Telekom-Fall: seit Tagen leer, kein Vortag mit Daten."""
    tco = {
        "updated": TAG,
        "buendel": [
            _buendel("A", "apple-iphone-18-pro-256gb-polar"),
            _buendel("B", "apple-iphone-18-pro-256gb-polar", tag="2026-02-01"),
        ],
    }
    ergebnis = pruefe(tco, [], _pflicht())
    assert ergebnis.rot
    assert [(b.art, b.anbieter) for b in ergebnis.befunde] == [("anbieter_leer", "B")]


def test_belegte_luecke_ist_kein_befund_und_steht_in_der_matrix():
    tco = {
        "updated": TAG,
        "buendel": [_buendel("A", "apple-iphone-18-pro-256gb-polar")],
    }
    pflicht = _pflicht(luecken={("B", "*"): "nicht erreichbar (gemessen)"})
    ergebnis = pruefe(tco, [], pflicht)
    assert not ergebnis.rot
    assert "belegt: nicht erreichbar (gemessen)" in als_markdown(ergebnis, pflicht)


def test_fehlendes_pflichtmodell_ist_rot():
    tco = {
        "updated": TAG,
        "buendel": [
            _buendel("A", "apple-iphone-18-pro-256gb-polar"),
            _buendel("A", "samsung-galaxy-s26-256gb-grau"),
            _buendel("B", "samsung-galaxy-s26-256gb-grau"),
        ],
    }
    ergebnis = pruefe(
        tco, [], _pflicht(modelle=("apple-iphone-18-pro", "samsung-galaxy-s26"))
    )
    assert [(b.art, b.anbieter) for b in ergebnis.befunde] == [("modell_fehlt", "B")]
    assert "apple-iphone-18-pro" in ergebnis.befunde[0].text


def test_gebrauchte_geraete_zaehlen_nicht():
    tco = {
        "updated": TAG,
        "buendel": [
            _buendel("A", "apple-iphone-18-pro-256gb-polar"),
            dict(
                _buendel("B", "apple-iphone-18-pro-256gb-polar-refurbished"),
                zustand="refurbished",
            ),
        ],
    }
    ergebnis = pruefe(tco, [], _pflicht())
    assert [(b.art, b.anbieter) for b in ergebnis.befunde] == [("anbieter_leer", "B")]


def test_matrix_zaehlt_speicher_tarife_laufzeiten():
    tco = {
        "updated": TAG,
        "buendel": [
            _buendel("A", "apple-iphone-18-pro-256gb-polar", "S", 24),
            _buendel("A", "apple-iphone-18-pro-512gb-polar", "M", 36),
            _buendel("A", "apple-iphone-18-pro-512gb-schwarz", "M", 36),
        ],
    }
    ergebnis = pruefe(tco, [], _pflicht(anbieter=("A",)))
    zelle = ergebnis.matrix[("apple-iphone-18-pro", "A")]
    assert zelle == {
        "speicher": {"256gb", "512gb"},
        "tarife": {"S", "M"},
        "laufzeiten": {24, 36},
    }
    assert ergebnis.anbieter_zahl == {"A": 3}


def _tco_a():
    return {
        "updated": TAG,
        "buendel": [_buendel("A", "apple-iphone-18-pro-256gb-polar")],
    }


def test_verlorene_kombinationen_sind_rot():
    verlust = KOMBI_VERLUST_MINDEST + 1
    historie = _hist("a", 20, VORTAG) + _hist("a", 20 - verlust, TAG)
    ergebnis = pruefe(_tco_a(), historie, _pflicht(anbieter=("A",)))
    assert [b.art for b in ergebnis.befunde] == ["kombis_weg"]
    assert f"{verlust} von 20" in ergebnis.befunde[0].text
    assert ergebnis.vortag == VORTAG


def test_wenige_verlorene_kombinationen_bleiben_gruen():
    """Gegenprobe: unter der Mindestzahl schlägt der Anteil nicht an."""
    verlust = KOMBI_VERLUST_MINDEST - 1
    historie = _hist("a", 20, VORTAG) + _hist("a", 20 - verlust, TAG)
    ergebnis = pruefe(_tco_a(), historie, _pflicht(anbieter=("A",)))
    assert not ergebnis.rot


def test_vergleich_nimmt_den_letzten_frueheren_messtag():
    """Ein Anbieter, der am Vortag nicht lief, wird gegen seinen letzten
    Messtag verglichen - nicht gegen einen leeren Tag."""
    historie = _hist("a", 20, "2026-03-01") + _hist("a", 20, TAG)
    ergebnis = pruefe(_tco_a(), historie, _pflicht(anbieter=("A",)))
    assert not ergebnis.rot
    assert ergebnis.vortag == "2026-03-01"


@pytest.mark.parametrize(
    "faktor,rot",
    [
        (1 + PREISSPRUNG_ANTEIL + 0.01, True),
        (1 + PREISSPRUNG_ANTEIL - 0.01, False),
        (1 - PREISSPRUNG_ANTEIL - 0.01, True),
    ],
)
def test_preissprung(faktor, rot):
    historie = _hist("a", 3, VORTAG, 1000.0) + _hist(
        "a", 3, TAG, round(1000.0 * faktor, 2)
    )
    ergebnis = pruefe(_tco_a(), historie, _pflicht(anbieter=("A",)))
    assert ergebnis.rot is rot
    if rot:
        assert ergebnis.befunde[0].art == "preissprung"


def test_anbietername_mit_sonderzeichen_aus_der_id():
    """1&1 steht in der Bündel-ID als `1-1`."""
    verlust = KOMBI_VERLUST_MINDEST + 1
    historie = _hist("1-1", 20, VORTAG) + _hist("1-1", 20 - verlust, TAG)
    tco = {
        "updated": TAG,
        "buendel": [_buendel("1&1", "apple-iphone-18-pro-256gb-polar")],
    }
    ergebnis = pruefe(tco, historie, _pflicht(anbieter=("1&1",)))
    assert [(b.art, b.anbieter) for b in ergebnis.befunde] == [("kombis_weg", "1&1")]


def test_config_laedt_und_verlangt_gruende(tmp_path):
    echte = lade_pflicht(
        Path(__file__).resolve().parents[1] / "config" / "geraete_abdeckung.yaml"
    )
    assert "Telekom" in echte["anbieter"]
    assert "apple-iphone-18-pro" in echte["modelle"]
    kaputt = tmp_path / "a.yaml"
    kaputt.write_text("belegte_luecken:\n  - anbieter: X\n", encoding="utf-8")
    with pytest.raises(ValueError):
        lade_pflicht(kaputt)


ECHTE_CONFIG = Path(__file__).resolve().parents[1] / "config" / "geraete_abdeckung.yaml"


def _buendel_aller_pflichtmodelle(anbieter, pflicht, ohne=()):
    return [
        _buendel(anbieter, f"{modell}-256gb-schwarz")
        for modell in pflicht["modelle"]
        if modell not in ohne
    ]


def test_echte_config_fuehrt_congstar_iphone_17_pro_als_belegte_luecke():
    """05.11.2026: congstar leitet die 17-Pro-Seite auf die Übersicht um, das
    Gerät fehlt in der Geräteliste (kein „nicht mehr“: seit wann ist nicht belegt).
    Die Lücke steht mit Grund in der echten Config, und nur
    diese eine: kein ganzer Anbieter, kein anderes Modell."""
    pflicht = lade_pflicht(ECHTE_CONFIG)
    assert "apple-iphone-17-pro" in pflicht["modelle"]
    assert (
        "nicht in der Geräteliste"
        in pflicht["luecken"][("congstar", "apple-iphone-17-pro")]
    )
    assert [k for k in pflicht["luecken"] if k[0] == "congstar"] == [
        ("congstar", "apple-iphone-17-pro")
    ]


def test_congstar_ohne_iphone_17_pro_ist_mit_echter_config_gruen():
    pflicht = lade_pflicht(ECHTE_CONFIG)
    nur_congstar = {**pflicht, "anbieter": ["congstar"]}
    buendel = _buendel_aller_pflichtmodelle(
        "congstar", pflicht, ohne=("apple-iphone-17-pro",)
    )
    ergebnis = pruefe({"updated": TAG, "buendel": buendel}, [], nur_congstar)
    assert ergebnis.befunde == []


def test_ohne_die_belegte_luecke_waere_der_congstar_lauf_rot():
    """Gegenprobe zum Fehler vom 05.11.: dieselben Bündel, Lücke nicht erfasst."""
    pflicht = lade_pflicht(ECHTE_CONFIG)
    ohne_luecke = {**pflicht, "anbieter": ["congstar"], "luecken": {}}
    buendel = _buendel_aller_pflichtmodelle(
        "congstar", pflicht, ohne=("apple-iphone-17-pro",)
    )
    ergebnis = pruefe({"updated": TAG, "buendel": buendel}, [], ohne_luecke)
    assert [(b.art, b.anbieter) for b in ergebnis.befunde] == [
        ("modell_fehlt", "congstar")
    ]
    assert ergebnis.befunde[0].text.endswith("apple-iphone-17-pro")


def test_luecke_gilt_weder_fuer_andere_anbieter_noch_fuer_andere_modelle():
    pflicht = lade_pflicht(ECHTE_CONFIG)
    telekom = {**pflicht, "anbieter": ["Telekom"]}
    buendel = _buendel_aller_pflichtmodelle(
        "Telekom", pflicht, ohne=("apple-iphone-17-pro",)
    )
    rot = pruefe({"updated": TAG, "buendel": buendel}, [], telekom)
    assert [b.art for b in rot.befunde] == ["modell_fehlt"]
    congstar = {**pflicht, "anbieter": ["congstar"]}
    buendel = _buendel_aller_pflichtmodelle(
        "congstar", pflicht, ohne=("apple-iphone-17-pro", "apple-iphone-17-pro-max")
    )
    rot = pruefe({"updated": TAG, "buendel": buendel}, [], congstar)
    assert [b.art for b in rot.befunde] == ["modell_fehlt"]
    assert rot.befunde[0].text.endswith("apple-iphone-17-pro-max")


def _luecken_yaml(tmp_path, geprueft="2026-03-01", bis="2026-03-15", mit_bis=True):
    zeilen = [
        "pflicht_anbieter: [A]",
        "pflicht_modelle: [apple-iphone-18-pro]",
        "belegte_luecken:",
        "  - anbieter: A",
        "    modelle: [apple-iphone-18-pro]",
        "    grund: Anbieter führt das Gerät nicht mehr",
        f'    geprueft: "{geprueft}"',
    ]
    if mit_bis:
        zeilen.append(f'    bis: "{bis}"')
    pfad = tmp_path / "a.yaml"
    pfad.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    return pfad


def test_ausnahme_darf_hoechstens_14_tage_gelten(tmp_path):
    pflicht = lade_pflicht(_luecken_yaml(tmp_path, bis="2026-03-15"))
    assert pflicht["bis"][("A", "apple-iphone-18-pro")].isoformat() == "2026-03-15"
    for bis in ("2026-03-16", "2026-02-28"):
        with pytest.raises(ValueError, match="bis"):
            lade_pflicht(_luecken_yaml(tmp_path, bis=bis))


def test_ausnahme_ohne_ablaufdatum_oder_pruefdatum_wird_nicht_geladen(tmp_path):
    with pytest.raises(ValueError, match="'bis'"):
        lade_pflicht(_luecken_yaml(tmp_path, mit_bis=False))
    with pytest.raises(ValueError, match="'geprueft'"):
        lade_pflicht(_luecken_yaml(tmp_path, geprueft="gestern"))


def test_echte_ausnahmen_laufen_hoechstens_14_tage():
    pflicht = lade_pflicht(ECHTE_CONFIG)
    assert pflicht["bis"].keys() == pflicht["luecken"].keys()


def _mit_luecke(bis="2026-03-15"):
    return _pflicht(
        anbieter=("A",),
        luecken={("A", "apple-iphone-18-pro"): "Anbieter führt das Gerät nicht mehr"},
    ) | {"bis": {("A", "apple-iphone-18-pro"): date.fromisoformat(bis)}}


def _tag_mit_buendel(messtag, modell):
    return {
        "updated": messtag,
        "buendel": [_buendel("A", f"{modell}-256gb-x", tag=messtag)],
    }


def test_ausnahme_gilt_bis_zum_ablaufdatum_einschliesslich():
    tco = _tag_mit_buendel("2026-03-15", "samsung-galaxy-s26")
    ergebnis = pruefe(tco, [], _mit_luecke("2026-03-15"))
    assert not ergebnis.rot


def test_abgelaufene_ausnahme_macht_den_lauf_rot_auch_ohne_datum_von_heute():
    tco = _tag_mit_buendel("2026-03-16", "samsung-galaxy-s26")
    ergebnis = pruefe(tco, [], _mit_luecke("2026-03-15"))
    assert [(b.art, b.anbieter) for b in ergebnis.befunde] == [
        ("luecke_abgelaufen", "A")
    ]
    assert "2026-03-15" in ergebnis.befunde[0].text
    assert "apple-iphone-18-pro" in ergebnis.befunde[0].text


def test_ueberholte_ausnahme_warnt_laut_ohne_rot_zu_werden():
    """Bündel für das Gerät mit belegter Lücke ist wieder da: Eintrag streichen."""
    tco = _tag_mit_buendel("2026-03-10", "apple-iphone-18-pro")
    pflicht = _mit_luecke()
    ergebnis = pruefe(tco, [], pflicht)
    assert not ergebnis.rot
    assert [(w.art, w.anbieter) for w in ergebnis.warnungen] == [
        ("luecke_ueberholt", "A")
    ]
    assert "streichen" in ergebnis.warnungen[0].text
    assert "## Warnungen" in als_markdown(ergebnis, pflicht)


def test_gueltige_ausnahme_ohne_buendel_warnt_nicht():
    tco = _tag_mit_buendel("2026-03-10", "samsung-galaxy-s26")
    ergebnis = pruefe(tco, [], _mit_luecke())
    assert ergebnis.warnungen == []
    assert "## Warnungen" not in als_markdown(ergebnis, _mit_luecke())


def test_ueberholte_ausnahme_fuer_ganzen_anbieter_warnt():
    pflicht = _pflicht(anbieter=("A",), luecken={("A", "*"): "nicht erreichbar"})
    pflicht["bis"] = {("A", "*"): date(2026, 3, 15)}
    tco = _tag_mit_buendel("2026-03-10", "samsung-galaxy-s26")
    ergebnis = pruefe(tco, [], pflicht)
    assert [w.art for w in ergebnis.warnungen] == ["luecke_ueberholt"]


def test_waechterskript_meldet_ueberholte_ausnahme_als_warning(tmp_path, capsys):
    from scripts import geraete_abdeckungswaechter as skript

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "geraete_abdeckung.yaml").write_text(
        _luecken_yaml(tmp_path).read_text(encoding="utf-8"), encoding="utf-8"
    )
    zustand = tmp_path / "data" / "state"
    zustand.mkdir(parents=True)
    tco = _tag_mit_buendel("2026-03-10", "apple-iphone-18-pro")
    (zustand / "geraete_tco.json").write_text(json.dumps(tco), encoding="utf-8")
    code = skript.main(["--root", str(tmp_path)])
    ausgabe = capsys.readouterr().out
    assert code == 0
    assert "::warning::A: Ausnahme apple-iphone-18-pro ist überholt" in ausgabe
    assert "::error::" not in ausgabe


def test_kommt_das_iphone_17_pro_bei_congstar_zurueck_warnt_die_echte_config():
    pflicht = lade_pflicht(ECHTE_CONFIG)
    nur_congstar = {**pflicht, "anbieter": ["congstar"]}
    buendel = _buendel_aller_pflichtmodelle("congstar", pflicht)
    ergebnis = pruefe({"updated": TAG, "buendel": buendel}, [], nur_congstar)
    assert ergebnis.befunde == []
    assert [(w.anbieter, w.art) for w in ergebnis.warnungen] == [
        ("congstar", "luecke_ueberholt")
    ]
    assert "apple-iphone-17-pro" in ergebnis.warnungen[0].text
