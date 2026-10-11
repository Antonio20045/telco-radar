"""Schlankes Stylesheet für alle Seiten außer der Geräteseite (11.10.2026)."""

from __future__ import annotations

from pathlib import Path

from telco_radar import stil_seiten

KOPF = '<link rel="stylesheet" href="{}style.css">'

BLATT = (
    ":root{--a:1}\n"
    "body{margin:0}\n"
    ".gr-leit{color:red}\n"
    ".gr-nur{color:blue}\n"
    ".gr-nur,.karte{padding:1px}\n"
    ".karte:not(.gr-nur){margin:1px}\n"
    "@media (max-width:600px){.gr-nur{color:green}.karte{color:black}}\n"
    "@media print{.gx-tafel{display:none}}\n"
)


def _site(tmp_path: Path) -> Path:
    (tmp_path / "style.css").write_text(BLATT, encoding="utf-8")
    (tmp_path / "geraete.html").write_text(
        KOPF.format("") + '<div class="gr-nur gx-tafel"></div>', encoding="utf-8"
    )
    (tmp_path / "index.html").write_text(
        KOPF.format("") + "<p class='gr-leit karte'></p>", encoding="utf-8"
    )
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "w.html").write_text(KOPF.format("../"), encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "f.html").write_text(
        '<i class="gr-nur"></i>', encoding="utf-8"
    )
    stil_seiten.teile_blaetter(tmp_path)
    return tmp_path


def test_nur_die_geraeteseite_laedt_das_volle_blatt(tmp_path):
    site = _site(tmp_path)
    assert (site / "style.css").read_text(encoding="utf-8") == BLATT
    assert 'href="style.css"' in (site / "geraete.html").read_text(encoding="utf-8")
    assert 'href="seiten.css"' in (site / "index.html").read_text(encoding="utf-8")
    assert 'href="../seiten.css"' in (site / "reports/w.html").read_text(
        encoding="utf-8"
    )


def test_seiten_css_verliert_nur_regeln_fuer_fremde_geraeteklassen(tmp_path):
    schlank = (_site(tmp_path) / "seiten.css").read_text(encoding="utf-8")
    assert schlank == (
        ":root{--a:1}\n"
        "body{margin:0}\n"
        ".gr-leit{color:red}\n"
        ".gr-nur,.karte{padding:1px}\n"
        ".karte:not(.gr-nur){margin:1px}\n"
        "@media (max-width:600px){.karte{color:black}}"
    )


def test_eine_verirrte_klammer_verschiebt_keine_folgeregel():
    css = "a{x:1}\n}\n/* k { */ .gr-weg{y:2}\nb{z:3}\n.gr-weg{y:4}\n"
    schlank = stil_seiten.ohne_unbenutzte(css, set())
    assert schlank == "a{x:1}\n}\n/* k { */ .gr-weg{y:2}\nb{z:3}"


def test_zerlegen_verliert_kein_zeichen():
    css = 'a{content:"}"}/* } */b{c:1}@import "x.css";@media x{d{e:1}}'
    assert "".join(stil_seiten.bloecke(css)) == css
