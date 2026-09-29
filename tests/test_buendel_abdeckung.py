"""Der Bündel-Abdeckungswächter: ein Anbieter ohne Bündel, ein fehlendes
Pflichtmodell, verlorene Kombinationen und Preissprünge machen den Lauf rot.

Die Telekom lieferte vom 15.09.2026 an kein Bündel, und kein Lauf wurde rot:
der ältere Wächter vergleicht nur mit dem Vortag. Diese Tests halten fest,
dass die neue Prüfung gegen die Pflichtliste misst.
"""
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
    return {"anbieter": anbieter, "sku_id": sku, "tarif_name": tarif,
            "laufzeit_monate": laufzeit, "last_verified": tag,
            "zustand": "neu"}


def _pflicht(anbieter=("A", "B"), modelle=("apple-iphone-18-pro",),
             luecken=None):
    return {"anbieter": list(anbieter), "modelle": list(modelle),
            "luecken": dict(luecken or {})}


def _hist(anbieter_slug, n, tag, gesamt=1000.0, start=0):
    return [{"id": f"buendel--{anbieter_slug}--sku-{i}--t", "datum": tag,
             "gesamt": gesamt, "zustand": "neu"}
            for i in range(start, start + n)]


def test_modell_und_speicher_aus_sku():
    assert modell_und_speicher("apple-iphone-18-pro-256gb-polar") == \
        ("apple-iphone-18-pro", "256gb")
    assert modell_und_speicher("samsung-galaxy-s26-ultra-1024gb-grau-"
                               "refurbished") == \
        ("samsung-galaxy-s26-ultra", "1024gb")
    assert modell_und_speicher("ohne-speicherangabe") == (None, None)


def test_anbieter_ohne_buendel_ist_rot_auch_ohne_vortag():
    """Der Telekom-Fall: seit Tagen leer, kein Vortag mit Daten."""
    tco = {"updated": TAG, "buendel": [
        _buendel("A", "apple-iphone-18-pro-256gb-polar"),
        # B hat nur ein altes Bündel - am Messtag nichts.
        _buendel("B", "apple-iphone-18-pro-256gb-polar", tag="2026-02-01"),
    ]}
    ergebnis = pruefe(tco, [], _pflicht())
    assert ergebnis.rot
    assert [(b.art, b.anbieter) for b in ergebnis.befunde] == \
        [("anbieter_leer", "B")]


def test_belegte_luecke_ist_kein_befund_und_steht_in_der_matrix():
    tco = {"updated": TAG, "buendel": [
        _buendel("A", "apple-iphone-18-pro-256gb-polar")]}
    pflicht = _pflicht(luecken={("B", "*"): "nicht erreichbar (gemessen)"})
    ergebnis = pruefe(tco, [], pflicht)
    assert not ergebnis.rot
    assert "belegt: nicht erreichbar (gemessen)" in \
        als_markdown(ergebnis, pflicht)


def test_fehlendes_pflichtmodell_ist_rot():
    tco = {"updated": TAG, "buendel": [
        _buendel("A", "apple-iphone-18-pro-256gb-polar"),
        _buendel("A", "samsung-galaxy-s26-256gb-grau"),
        _buendel("B", "samsung-galaxy-s26-256gb-grau")]}
    ergebnis = pruefe(tco, [], _pflicht(
        modelle=("apple-iphone-18-pro", "samsung-galaxy-s26")))
    assert [(b.art, b.anbieter) for b in ergebnis.befunde] == \
        [("modell_fehlt", "B")]
    assert "apple-iphone-18-pro" in ergebnis.befunde[0].text


def test_gebrauchte_geraete_zaehlen_nicht():
    tco = {"updated": TAG, "buendel": [
        _buendel("A", "apple-iphone-18-pro-256gb-polar"),
        dict(_buendel("B", "apple-iphone-18-pro-256gb-polar-refurbished"),
             zustand="refurbished")]}
    ergebnis = pruefe(tco, [], _pflicht())
    assert [(b.art, b.anbieter) for b in ergebnis.befunde] == \
        [("anbieter_leer", "B")]


def test_matrix_zaehlt_speicher_tarife_laufzeiten():
    tco = {"updated": TAG, "buendel": [
        _buendel("A", "apple-iphone-18-pro-256gb-polar", "S", 24),
        _buendel("A", "apple-iphone-18-pro-512gb-polar", "M", 36),
        _buendel("A", "apple-iphone-18-pro-512gb-schwarz", "M", 36)]}
    ergebnis = pruefe(tco, [], _pflicht(anbieter=("A",)))
    zelle = ergebnis.matrix[("apple-iphone-18-pro", "A")]
    assert zelle == {"speicher": {"256gb", "512gb"}, "tarife": {"S", "M"},
                     "laufzeiten": {24, 36}}
    assert ergebnis.anbieter_zahl == {"A": 3}


def _tco_a():
    return {"updated": TAG, "buendel": [
        _buendel("A", "apple-iphone-18-pro-256gb-polar")]}


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
    historie = (_hist("a", 20, "2026-03-01") + _hist("a", 20, TAG))
    ergebnis = pruefe(_tco_a(), historie, _pflicht(anbieter=("A",)))
    assert not ergebnis.rot
    assert ergebnis.vortag == "2026-03-01"


@pytest.mark.parametrize("faktor,rot", [
    (1 + PREISSPRUNG_ANTEIL + 0.01, True),
    (1 + PREISSPRUNG_ANTEIL - 0.01, False),
    (1 - PREISSPRUNG_ANTEIL - 0.01, True),
])
def test_preissprung(faktor, rot):
    historie = _hist("a", 3, VORTAG, 1000.0) + \
        _hist("a", 3, TAG, round(1000.0 * faktor, 2))
    ergebnis = pruefe(_tco_a(), historie, _pflicht(anbieter=("A",)))
    assert ergebnis.rot is rot
    if rot:
        assert ergebnis.befunde[0].art == "preissprung"


def test_anbietername_mit_sonderzeichen_aus_der_id():
    """1&1 steht in der Bündel-ID als `1-1`."""
    verlust = KOMBI_VERLUST_MINDEST + 1
    historie = _hist("1-1", 20, VORTAG) + _hist("1-1", 20 - verlust, TAG)
    tco = {"updated": TAG, "buendel": [
        _buendel("1&1", "apple-iphone-18-pro-256gb-polar")]}
    ergebnis = pruefe(tco, historie, _pflicht(anbieter=("1&1",)))
    assert [(b.art, b.anbieter) for b in ergebnis.befunde] == \
        [("kombis_weg", "1&1")]


def test_config_laedt_und_verlangt_gruende(tmp_path):
    echte = lade_pflicht(Path(__file__).resolve().parents[1] / "config" /
                         "geraete_abdeckung.yaml")
    assert "Telekom" in echte["anbieter"]
    assert "apple-iphone-18-pro" in echte["modelle"]
    kaputt = tmp_path / "a.yaml"
    kaputt.write_text("belegte_luecken:\n  - anbieter: X\n", encoding="utf-8")
    with pytest.raises(ValueError):
        lade_pflicht(kaputt)


def _workflow():
    import yaml
    pfad = Path(__file__).resolve().parents[1] / ".github" / "workflows" / \
        "geraete.yml"
    return yaml.safe_load(pfad.read_text(encoding="utf-8"))


def test_workflow_hat_ersatztermine_und_misst_nur_einmal_am_tag():
    wf = _workflow()
    # `on:` liest YAML als True.
    termine = [t["cron"] for t in wf[True]["schedule"]]
    assert len(termine) >= 3
    schritte = wf["jobs"]["geraete"]["steps"]
    namen = [s.get("name") for s in schritte]
    pruef = namen.index("Heute schon gemessen?")
    for schritt in schritte[pruef + 1:]:
        assert "steps.heute.outputs.fertig != 'true'" in schritt.get("if", ""),\
            schritt.get("name") or schritt.get("uses")


def test_workflow_endet_mit_dem_buendelwaechter():
    schritte = _workflow()["jobs"]["geraete"]["steps"]
    letzter = schritte[-1]
    assert letzter["name"] == "Buendelabdeckung pruefen"
    assert letzter["if"].startswith("always()")
    assert "continue-on-error" not in letzter
    assert "geraete_abdeckungswaechter.py" in letzter["run"]
    # Der Wächter verschickt nichts: keine Mail-Secrets in seiner Umgebung.
    assert not any("SMTP" in k or "MAIL" in k
                   for k in (letzter.get("env") or {}))
