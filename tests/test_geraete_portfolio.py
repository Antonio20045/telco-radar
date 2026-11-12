"""Portfolio gegen Vodafone (Ziel 3): nur eine BELEGTE Lücke ist eine Lücke.

Jeder Fall hat seine Gegenprobe: derselbe Aufbau mit gültigem Beleg ergibt eine
Portfolio-Lücke, ohne Beleg oder mit abgelaufenem Beleg eine Messlücke. Alle
Stichtage sind fest im Test; nichts hängt am heutigen Datum und kein Test ruft
ein Modell auf.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import jinja2
import pytest
import test_geraete_tco_zustand
from bs4 import BeautifulSoup

from telco_radar.analyze.buendel_abdeckung import lade_pflicht
from telco_radar.geraete_model import Geraet, Katalog
from telco_radar.report import geraete_portfolio as pf
from telco_radar.report import geraete_sortiment

VORLAGEN = Path(pf.__file__).parent / "templates"
HEUTE = "2026-11-10"


def _g(hersteller: str, modell: str, generation: int) -> Geraet:
    return Geraet(
        hersteller=hersteller,
        modell=modell,
        generation=generation,
        speicher=[256],
    )


def _karte(anbieter: str, gesamt=1000.0, **besser) -> dict:
    return {
        "anbieter": anbieter,
        "gesamt": gesamt,
        "frisch": True,
        "zaehlt": True,
        "naeherung": False,
        "zustand": "neu",
        **besser,
    }


def _modell(g: Geraet, *karten: dict) -> dict:
    return {
        "id": f"{g.device_id}-256",
        "device_id": g.device_id,
        "karten": list(karten),
    }


def _beleg(bis="2026-11-19", geprueft="2026-11-05", anbieter="congstar", modell="*"):
    return {
        (anbieter, modell): {
            "grund": "Gerät ist nicht in der Geräteliste",
            "geprueft": date.fromisoformat(geprueft),
            "bis": date.fromisoformat(bis),
            "beleg": "https://beispiel.test/beleg.png",
            "original": "https://beispiel.test/original",
        }
    }


S26 = _g("Samsung", "Galaxy S26", 26)
I18 = _g("Apple", "iPhone 18 Pro", 18)
I17AIR = _g("Apple", "iPhone Air", 17)
KATALOG = Katalog(geraete=[S26, I18, _g("Apple", "iPhone 18 Pro Max", 18), I17AIR])


def _rechne(modelle: list[dict], belege: dict | None = None, heute: str = HEUTE):
    return pf.berechne(modelle, KATALOG, belege or {}, heute)


def _paar(r: dict, name: str) -> dict:
    return next(p for p in r["paare"] if p["name"] == name)


def _namen(gruppen: list[dict]) -> list[str]:
    return [g["name"] for gr in gruppen for g in gr["geraete"]]


def test_belegt_nur_beim_wettbewerber_und_nur_bei_vodafone():
    modelle = [
        _modell(S26, _karte("Vodafone"), _karte("congstar")),
        _modell(I18, _karte("congstar")),
        _modell(I17AIR, _karte("congstar")),
    ]
    belege = {**_beleg(anbieter="Vodafone", modell=S26.device_id)}
    belege.update(_beleg(anbieter="Vodafone", modell=I18.device_id))
    p = _paar(_rechne(modelle, belege), "congstar")
    assert _namen(p["nur_w"]) == ["iPhone 18 Pro"]
    assert p["nur_v"] == [] and p["n_v"] == 0
    assert p["beide"] == 1
    modelle = [_modell(S26, _karte("Vodafone"), _karte("Telekom"))]
    modelle.append(_modell(I18, _karte("Vodafone"), _karte("congstar")))
    belege = _beleg(anbieter="congstar", modell=S26.device_id)
    p = _paar(_rechne(modelle, belege), "Telekom")
    assert _namen(p["nur_v"]) == [] and p["n_offen"] == 1
    p = _paar(_rechne(modelle, belege), "congstar")
    assert _namen(p["nur_v"]) == ["Galaxy S26"]
    assert p["nur_v"][0]["geraete"][0]["beleg"]["url"].endswith("beleg.png")


def test_ohne_beleg_ist_es_eine_messluecke_nie_eine_portfolio_luecke():
    modelle = [_modell(S26, _karte("Telekom")), _modell(I18, _karte("Vodafone"))]
    p = _paar(_rechne(modelle), "Telekom")
    assert p["n_w"] == 0 and p["n_v"] == 0 and p["n_offen"] == 2
    assert p["offen"][0]["geraete"][0]["grund"] == pf.GRUND_OHNE
    assert p["namen_w"] == [] and p["namen_v"] == []
    belege = _beleg(anbieter="Vodafone", modell=S26.device_id)
    p = _paar(_rechne(modelle, belege), "Telekom")
    assert p["n_w"] == 1 and p["n_offen"] == 1


def test_abgelaufener_beleg_zaehlt_als_messluecke():
    modelle = [_modell(S26, _karte("congstar"))]
    gueltig = _paar(
        _rechne(modelle, _beleg(bis="2026-11-10", anbieter="Vodafone", modell="*")),
        "congstar",
    )
    assert gueltig["n_w"] == 1 and gueltig["n_offen"] == 0
    abgelaufen = _paar(
        _rechne(modelle, _beleg(bis="2026-11-09", anbieter="Vodafone", modell="*")),
        "congstar",
    )
    assert abgelaufen["n_w"] == 0 and abgelaufen["n_offen"] == 1
    grund = abgelaufen["offen"][0]["geraete"][0]["grund"]
    assert grund == "Beleg abgelaufen (bis 09.11.2026)"


def test_ohne_stichtag_gilt_kein_beleg():
    modelle = [_modell(S26, _karte("congstar"))]
    p = _paar(
        _rechne(modelle, _beleg(anbieter="Vodafone", modell="*"), heute=""),
        "congstar",
    )
    assert p["n_w"] == 0 and p["n_offen"] == 1


def test_beide_fuehren_das_geraet_ist_kein_unterschied():
    modelle = [_modell(S26, _karte("Vodafone"), _karte("congstar"))]
    p = _paar(_rechne(modelle, _beleg(modell=S26.device_id)), "congstar")
    assert (p["n_w"], p["n_v"], p["n_offen"], p["beide"]) == (0, 0, 0, 1)


def test_nicht_aktuelles_modell_zaehlt_nicht():
    modelle = [_modell(I17AIR, _karte("congstar")), _modell(S26, _karte("congstar"))]
    r = _rechne(modelle, _beleg(anbieter="Vodafone", modell="*"))
    assert _namen(_paar(r, "congstar")["nur_w"]) == ["Galaxy S26"]


@pytest.mark.parametrize(
    "besser",
    [
        {"frisch": False},
        {"naeherung": True},
        {"zaehlt": False},
        {"gesamt": None},
        {"zustand": "erneuert"},
    ],
)
def test_nur_ein_frischer_neuer_echter_preis_zaehlt_als_fuehrt(besser):
    modelle = [_modell(S26, _karte("congstar", **besser), _karte("Vodafone"))]
    belege = _beleg(anbieter="congstar", modell="*")
    r = _rechne(modelle, belege)
    assert [p["name"] for p in r["paare"]] == []
    modelle = [_modell(S26, _karte("congstar"), _karte("Vodafone"))]
    assert [p["name"] for p in _rechne(modelle, belege)["paare"]] == ["congstar"]


def test_alte_karte_widerlegt_keinen_beleg_und_wird_nicht_zur_luecke():
    modelle = [
        _modell(S26, _karte("congstar", frisch=False), _karte("Vodafone")),
        _modell(I18, _karte("congstar"), _karte("Telekom")),
    ]
    r = _rechne(modelle, _beleg(anbieter="congstar", modell=S26.device_id))
    p = _paar(r, "congstar")
    assert p["nur_v"] and _namen(p["nur_v"]) == ["Galaxy S26"]


def test_standard_ist_telekom_und_gruppen_haben_die_feste_reihenfolge():
    s = _g("Nothing", "Phone 4", 4)
    katalog = Katalog(geraete=[S26, I18, s])
    modelle = [
        _modell(s, _karte("Telekom")),
        _modell(S26, _karte("Telekom")),
        _modell(I18, _karte("Telekom")),
        _modell(I18, _karte("o2")),
    ]
    belege = _beleg(anbieter="Vodafone", modell="*")
    r = pf.berechne(modelle, katalog, belege, HEUTE)
    assert r["standard"] == "Telekom"
    assert [p["name"] for p in r["paare"]] == ["Telekom", "o2"]
    assert [g["hersteller"] for g in _paar(r, "Telekom")["nur_w"]] == [
        "Apple",
        "Samsung",
        "Nothing",
    ]
    ohne = pf.berechne([_modell(S26, _karte("o2"))], katalog, belege, HEUTE)
    assert ohne["standard"] == "o2"
    assert pf.berechne([], katalog, belege, HEUTE)["leer"] is True


def test_zahlen_stimmen_mit_den_listen_ueberein():
    modelle = [
        _modell(S26, _karte("Telekom")),
        _modell(I18, _karte("Telekom"), _karte("Vodafone")),
        _modell(_g("Google", "Pixel 11", 11), _karte("Vodafone"), _karte("Telekom")),
    ]
    belege = _beleg(anbieter="Vodafone", modell=S26.device_id)
    katalog = Katalog(geraete=[S26, I18, _g("Google", "Pixel 11", 11)])
    p = _paar(pf.berechne(modelle, katalog, belege, HEUTE), "Telekom")
    assert (p["n_w"], p["n_v"], p["n_offen"]) == (1, 0, 0)
    assert [g["name"] for g in p["namen_w"]] == ["Samsung Galaxy S26"]
    assert p["namen_v"] == []
    assert p["beide"] == 2


def _yaml(tmp_path, zusatz: list[str]) -> Path:
    zeilen = [
        "pflicht_anbieter: [A]",
        "pflicht_modelle: [apple-iphone-18-pro]",
        "belegte_luecken:",
        "  - anbieter: A",
        "    modelle: [apple-iphone-18-pro]",
        "    grund: Anbieter führt das Gerät nicht",
        '    geprueft: "2026-11-05"',
        '    bis: "2026-11-19"',
        *zusatz,
    ]
    pfad = tmp_path / "a.yaml"
    pfad.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    return pfad


def test_lader_liefert_belege_nur_fuer_ausnahmen_mit_art_und_link(tmp_path):
    ohne = lade_pflicht(_yaml(tmp_path, []))
    assert ohne["belege"] == {}
    mit = lade_pflicht(
        _yaml(
            tmp_path,
            [
                "    art: nicht_im_portfolio",
                "    beleg: https://beispiel.test/b.png",
                "    original: https://beispiel.test/o",
            ],
        )
    )
    b = mit["belege"][("A", "apple-iphone-18-pro")]
    assert b["beleg"] == "https://beispiel.test/b.png"
    assert b["bis"] == date(2026, 11, 19) and b["geprueft"] == date(2026, 11, 5)
    assert b["original"] == "https://beispiel.test/o"


def test_lader_lehnt_art_ohne_beleg_und_unbekannte_art_ab(tmp_path):
    with pytest.raises(ValueError, match="beleg"):
        lade_pflicht(_yaml(tmp_path, ["    art: nicht_im_portfolio"]))
    with pytest.raises(ValueError, match="art"):
        lade_pflicht(_yaml(tmp_path, ["    art: egal", "    beleg: https://x.test/b"]))


def test_echte_belege_tragen_beleg_geprueft_und_frist():
    wurzel = Path(pf.__file__).parents[3]
    belege = lade_pflicht(wurzel / "config" / "geraete_abdeckung.yaml")["belege"]
    assert belege, "mindestens die congstar-Lücke ist belegt"
    for b in belege.values():
        assert b["beleg"].startswith("https://") and b["geprueft"] <= b["bis"]


def test_unlesbare_belegliste_macht_alles_zur_messluecke(tmp_path):
    (tmp_path / "data" / "state").mkdir(parents=True)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "geraete_abdeckung.yaml").write_text("belegte_luecken: [1]")
    tco = {"modelle": [_modell(S26, _karte("congstar"))]}
    a = pf.ansicht(tmp_path / "data" / "state", tco, KATALOG, HEUTE)
    assert a["hinweis"].startswith("Belegliste nicht lesbar")
    p = _paar(a, "congstar")
    assert p["n_w"] == 0 and p["n_offen"] == 1


def _rendern(ansicht: dict | None) -> BeautifulSoup:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(VORLAGEN), autoescape=True)
    ctx = {"hersteller": {"portfolio": ansicht}} if ansicht is not None else {}
    html = env.get_template("_geraete_portfolio.html.j2").render(geraete=ctx)
    return BeautifulSoup(html, "html.parser")


def _ansicht() -> dict:
    modelle = [
        _modell(S26, _karte("Telekom")),
        _modell(I18, _karte("Telekom")),
        _modell(I18, _karte("o2")),
    ]
    modelle[0]["karten"].append(_karte("o2"))
    belege = _beleg(anbieter="Vodafone", modell=S26.device_id)
    return {**pf.berechne(modelle, KATALOG, belege, HEUTE), "hinweis": ""}


def test_vorlage_benennt_ausfall_leerzustand_und_fehlenden_schluessel():
    assert "nicht verfügbar: kaputt" in _rendern({"fehler": "kaputt"}).text
    leer = _rendern({"fehler": "", "leer": True})
    assert "Kein Wettbewerber" in leer.text
    assert "nicht berechnet" in _rendern(None).text


WAHL = ["Telekom", "o2", "congstar"]


def _ansicht_drei(belege: dict | None = None) -> dict:
    """Drei Paare (Telekom, o2, congstar) ohne Vodafone-Preis bei S26 und I18."""
    modelle = [
        _modell(S26, _karte("Telekom"), _karte("o2"), _karte("congstar")),
        _modell(I18, _karte("Telekom"), _karte("o2")),
        _modell(I17AIR, _karte("Vodafone"), _karte("Telekom")),
    ]
    return {**pf.berechne(modelle, KATALOG, belege or {}, HEUTE), "hinweis": ""}


def _beleg_s26_vodafone() -> dict:
    return _beleg(anbieter="Vodafone", modell=S26.device_id)


def test_tafel_zeigt_jeden_wettbewerber_in_einer_zeile_mit_vier_zahlen():
    """Antonio, 12.12.2026: alles auf einen Blick, kein Umschalter, keine
    Gerätelisten und kein Satz unter der Tabelle."""
    s = _rendern(_ansicht_drei())
    kopf = [th.text for th in s.select(".gr-pf-tafel thead th")]
    assert kopf == ["Anbieter", "beide", "nur dort", "nur Vodafone", "nicht gemessen"]
    zeilen = s.select(".gr-pf-tafel tbody tr")
    assert [z["data-pf"] for z in zeilen] == WAHL
    for z in zeilen:
        assert len(z.select("td")) == 4
    assert s.select_one("#pf-wahl") is None
    assert s.select_one("details.gr-pf-offen") is None
    assert s.select_one(".gr-pf-regel") is None


def test_die_zahlen_der_tafel_sind_die_zahlen_der_rechnung():
    a = _ansicht_drei(_beleg_s26_vodafone())
    s = _rendern(a)
    zeile = s.select_one('.gr-pf-tafel tbody tr[data-pf="Telekom"]')
    p = _paar(a, "Telekom")
    assert [td.contents[0].strip() for td in zeile.select("td")] == [
        str(p["beide"]),
        str(p["n_w"]),
        str(p["n_v"]),
        str(p["n_offen"]),
    ]
    assert (zeile["data-nur-w"], zeile["data-offen"]) == (
        str(p["n_w"]),
        str(p["n_offen"]),
    )


def test_eine_belegte_luecke_steht_mit_geraetenamen_in_ihrer_zelle():
    s = _rendern(_ansicht_drei(_beleg_s26_vodafone()))
    zelle = s.select('.gr-pf-tafel tbody tr[data-pf="Telekom"] td')[1]
    link = zelle.select_one("small a")
    assert link.text == "Samsung Galaxy S26"
    assert link["href"] == "https://beispiel.test/beleg.png"
    ohne = s.select('.gr-pf-tafel tbody tr[data-pf="Telekom"] td')[2]
    assert ohne.select_one("small") is None and "gr-pf-null" in ohne["class"]


def test_ohne_belegte_luecke_steht_dort_nur_die_null():
    s = _rendern(_ansicht_drei())
    for zeile in s.select(".gr-pf-tafel tbody tr"):
        for td in zeile.select("td")[1:3]:
            assert td.text.strip() == "0" and "gr-pf-null" in td["class"]


def test_belegausfall_steht_als_benannte_luecke_ueber_der_tafel():
    a = _ansicht_drei()
    a["hinweis"] = "Belegliste nicht lesbar (OSError): keine Lücke belegt"
    s = _rendern(a)
    assert "Belegliste nicht lesbar" in s.select_one(".gx-leer").text


def test_seite_zeigt_die_tafel_nach_der_herstellergrafik_und_die_regel_im_fuss(
    tmp_path,
):
    seite = test_geraete_tco_zustand._baue(tmp_path)
    ids = [e.get("id") for e in seite.select("section[id]")]
    assert ids.index("hersteller") < ids.index("portfolio")
    assert seite.select_one("#portfolio .gr-pf-tafel") is not None
    fuss = seite.select_one(".dz-foot--stand")
    assert fuss is not None and pf.REGEL in fuss.text
    assert pf.REGEL not in seite.select_one("#portfolio").get_text()


def test_nicht_verfuegbar_ist_kein_beleg_fuer_nicht_im_portfolio():
    modelle = [_modell(S26, _karte("congstar"))]
    gut = _beleg(anbieter="Vodafone", modell="*")
    assert _paar(_rechne(modelle, gut), "congstar")["n_w"] == 1
    for grund in (
        "Gerät derzeit nicht verfügbar",
        "Seite zeigt: nicht lieferbar",
        "Anbieter führt das Gerät nicht",
    ):
        schlecht = {k: {**v, "grund": grund} for k, v in gut.items()}
        p = _paar(_rechne(modelle, schlecht), "congstar")
        assert p["n_w"] == 0 and p["n_offen"] == 1
        assert (
            p["offen"][0]["geraete"][0]["grund"] == geraete_sortiment.GRUND_UNZUREICHEND
        )
    for grund in (
        "nicht im Sortiment",
        "Seite entfernt (404)",
        "nicht in der Geräteliste",
    ):
        ok = {k: {**v, "grund": grund} for k, v in gut.items()}
        assert _paar(_rechne(modelle, ok), "congstar")["n_w"] == 1


def test_echter_congstar_beleg_belegt_die_geraeteliste_nicht_nur_nicht_verfuegbar():
    wurzel = Path(pf.__file__).parents[3]
    belege = lade_pflicht(wurzel / "config" / "geraete_abdeckung.yaml")["belege"]
    b = belege[("congstar", "apple-iphone-17-pro")]
    assert "nicht in der Geräteliste" in b["grund"]
    assert "verfügbar" not in b["grund"]
    gueltig, _ = pf.beleg_fuer(belege, "congstar", "apple-iphone-17-pro", "2026-11-10")
    assert gueltig is not None
    ordner = wurzel / "docs" / "belege" / "congstar-17pro-0511"
    assert (ordner / "3-apple-uebersicht-ganz.png").is_file()
    assert b["beleg"].endswith(
        "/docs/belege/congstar-17pro-0511/3-apple-uebersicht-ganz.png"
    )
    for datei in ("4-apple-uebersicht-links.txt", "5-congstar-sitemap-devices.xml"):
        assert (ordner / datei).is_file()
