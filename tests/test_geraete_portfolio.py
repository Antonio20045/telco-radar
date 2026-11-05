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
    assert p["kopf"] == "0 Geräte nur bei Telekom, 0 nur bei Vodafone"
    assert p["kontext"] == (
        "Bisher belegt: 0 Geräte; 2 aktuelle Geräte sind noch nicht gemessen "
        "und werden nicht gezählt."
    )
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


def test_kopfzeile_und_kontext_nennen_die_zahlen_und_den_singular():
    assert pf.kopfzeile("Telekom", 3, 0) == (
        "3 Geräte nur bei Telekom, 0 nur bei Vodafone"
    )
    assert pf.kopfzeile("o2", 1, 2).startswith("1 Gerät nur bei o2, 2 nur bei")
    assert pf.kontext(3, 12) == (
        "Bisher belegt: 3 Geräte; 12 aktuelle Geräte sind noch nicht gemessen "
        "und werden nicht gezählt."
    )
    assert pf.kontext(1, 1) == (
        "Bisher belegt: 1 Gerät; 1 aktuelles Gerät ist noch nicht gemessen "
        "und wird nicht gezählt."
    )


def test_kopfzeilen_zahlen_stimmen_mit_den_listen_ueberein():
    modelle = [
        _modell(S26, _karte("Telekom")),
        _modell(I18, _karte("Telekom"), _karte("Vodafone")),
        _modell(_g("Google", "Pixel 11", 11), _karte("Vodafone"), _karte("Telekom")),
    ]
    belege = _beleg(anbieter="Vodafone", modell=S26.device_id)
    katalog = Katalog(geraete=[S26, I18, _g("Google", "Pixel 11", 11)])
    p = _paar(pf.berechne(modelle, katalog, belege, HEUTE), "Telekom")
    assert (p["n_w"], p["n_v"], p["n_offen"]) == (1, 0, 0)
    assert p["kopf"] == "1 Gerät nur bei Telekom, 0 nur bei Vodafone"
    assert p["kontext"].startswith("Bisher belegt: 1 Gerät; 0 aktuelle Geräte")
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


def test_vorlage_zeigt_kopf_listen_beleglink_und_messluecken_getrennt():
    s = _rendern(_ansicht())
    assert s.select_one("section#portfolio h2").text == "Portfolio gegen Vodafone"
    assert s.select_one("section#portfolio")["data-standard"] == "Telekom"
    assert [b["data-pf"] for b in s.select("#pf-wahl button")] == ["Telekom", "o2"]
    assert s.select_one("#pf-wahl").has_attr("hidden")
    paar = s.select_one('.gr-pf-paar[data-pf="Telekom"]')
    assert paar.select_one(".gr-pf-kopf").text == (
        "1 Gerät nur bei Telekom, 0 nur bei Vodafone"
    )
    liste_w = paar.select_one(".gr-pf-liste--w")
    assert "Galaxy S26" in liste_w.text
    link = liste_w.select_one("a")
    assert link["href"] == "https://beispiel.test/beleg.png"
    offen = paar.select_one("details.gr-pf-offen")
    assert "Messlücke, zählt nicht" in offen.select_one("summary").text
    assert "iPhone 18 Pro" in offen.text and "iPhone 18 Pro" not in liste_w.text
    assert "Galaxy S26" not in offen.text


def test_vorlage_benennt_ausfall_leerzustand_und_fehlenden_schluessel():
    assert "nicht verfügbar: kaputt" in _rendern({"fehler": "kaputt"}).text
    leer = _rendern({"fehler": "", "leer": True})
    assert "Kein Wettbewerber" in leer.text
    assert "nicht berechnet" in _rendern(None).text


def test_vorlage_nennt_eine_leere_liste_und_den_belegausfall():
    a = _ansicht()
    a["hinweis"] = "Belegliste nicht lesbar (OSError): keine Lücke belegt"
    s = _rendern(a)
    assert "Belegliste nicht lesbar" in s.select_one(".gr-pf-hinweis").text
    o2 = s.select_one('.gr-pf-paar[data-pf="o2"]')
    assert "Keine belegte Lücke" in o2.select_one(".gr-pf-liste--v").text


def test_seite_zeigt_den_abschnitt_nach_der_herstellergrafik(tmp_path):
    seite = test_geraete_tco_zustand._baue(tmp_path)
    ids = [e.get("id") for e in seite.select("section[id]")]
    assert ids.index("hersteller") < ids.index("portfolio") < ids.index("preisposition")
    assert seite.select_one("#portfolio .gr-pf-regel").text == pf.REGEL


WAHL = ["Telekom", "o2", "congstar"]
_ZWEI = "2 aktuelle Geräte sind noch nicht gemessen und werden nicht gezählt."
ERWARTET = {
    "Telekom": f"Bisher belegt: 0 Geräte; {_ZWEI}",
    "o2": f"Bisher belegt: 0 Geräte; {_ZWEI}",
    "congstar": (
        "Bisher belegt: 0 Geräte; 1 aktuelles Gerät ist noch nicht gemessen "
        "und wird nicht gezählt."
    ),
}


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


def test_jede_kopfzahl_hat_den_kontextsatz_direkt_daneben_mit_den_echten_zahlen():
    a = _ansicht_drei()
    s = _rendern(a)
    paare = s.select(".gr-pf-paar")
    assert [p["data-pf"] for p in paare] == WAHL
    for p in paare:
        kopf = p.select_one(".gr-pf-kopf")
        satz = kopf.find_next_sibling()
        assert satz.name == "p" and "gr-pf-kontext" in satz["class"]
        assert satz.text == ERWARTET[p["data-pf"]]
        assert p.select_one(".gr-pf-kopf").text.startswith("0 Geräte nur bei")
    assert _paar(a, "Telekom")["n_offen"] == 2 and _paar(a, "congstar")["n_offen"] == 1
    mit = _rendern(_ansicht_drei(_beleg_s26_vodafone()))
    t = mit.select_one('.gr-pf-paar[data-pf="Telekom"] .gr-pf-kontext').text
    assert t.startswith("Bisher belegt: 1 Gerät; 1 aktuelles Gerät ist noch nicht")
    assert "wird nicht gezählt" in t


def test_keine_zahl_nur_bei_ohne_kontext_in_der_ganzen_vorlage():
    s = _rendern(_ansicht_drei())
    for kopf in s.select(".gr-pf-kopf"):
        assert "nur bei Vodafone" in kopf.text
        nach = kopf.find_next_sibling()
        assert "Bisher belegt:" in nach.text and "nicht gezählt" in nach.text
    assert len(s.select(".gr-pf-kontext")) == len(s.select(".gr-pf-kopf")) == 3


def test_messluecken_liste_ist_offen_ohne_belegten_unterschied_sonst_zu():
    s = _rendern(_ansicht_drei())
    for d in s.select("details.gr-pf-offen"):
        assert d.has_attr("open")
    mit = _rendern(_ansicht_drei(_beleg_s26_vodafone()))
    tk = mit.select_one('.gr-pf-paar[data-pf="Telekom"] details.gr-pf-offen')
    o2 = mit.select_one('.gr-pf-paar[data-pf="o2"] details.gr-pf-offen')
    assert not tk.has_attr("open") and not o2.has_attr("open")


def test_messluecken_zeile_nennt_wer_es_fuehrt_und_dass_kein_beleg_vorliegt():
    s = _rendern(_ansicht_drei())
    zeilen = s.select('.gr-pf-paar[data-pf="o2"] details.gr-pf-offen li')
    texte = {
        z.select_one(".gr-pf-geraet").text: z.select_one(".gr-pf-beleg").text
        for z in zeilen
    }
    assert texte["Galaxy S26"] == (
        "o2 führt es (Preis gemessen). Für Vodafone liegt kein Beleg vor."
    )
    assert texte["iPhone 18 Pro"].startswith("o2 führt es")
    a = _ansicht_drei()
    eigen = _paar(a, "Telekom")
    assert eigen["n_offen"] == 2
    modelle = [
        _modell(S26, _karte("Vodafone"), _karte("congstar")),
        _modell(I18, _karte("Vodafone"), _karte("Telekom")),
    ]
    s = _rendern({**pf.berechne(modelle, KATALOG, {}, HEUTE), "hinweis": ""})
    z = s.select_one(
        '.gr-pf-paar[data-pf="Telekom"] details.gr-pf-offen li .gr-pf-beleg'
    )
    assert (
        z.text
        == "Vodafone führt es (Preis gemessen). Für Telekom liegt kein Beleg vor."
    )


def test_abgelaufener_beleg_nennt_gueltigen_beleg_und_den_ablauf():
    modelle = [_modell(S26, _karte("congstar"))]
    abgelaufen = _beleg(bis="2026-11-09", anbieter="Vodafone", modell="*")
    s = _rendern({**pf.berechne(modelle, KATALOG, abgelaufen, HEUTE), "hinweis": ""})
    z = s.select_one("details.gr-pf-offen li .gr-pf-beleg").text
    assert z == (
        "congstar führt es (Preis gemessen). Für Vodafone liegt kein gültiger "
        "Beleg vor: Beleg abgelaufen (bis 09.11.2026)."
    )


def test_satz_zu_1und1_und_haendlern_nennt_den_grund_und_stimmt_mit_den_daten():
    s = _rendern(_ansicht_drei())
    t = s.select_one(".gr-pf-fehlende").text
    assert t.startswith("1&1 und Händler fehlen noch")
    assert "kein frischer, gezählter Preis" in t and "aktuellen Modellen" in t
    modelle = [
        _modell(S26, _karte("Telekom"), _karte("1&1"), _karte("o2"), _karte("congstar"))
    ]
    a = pf.berechne(modelle, KATALOG, {}, HEUTE)
    assert "1&1" in [p["name"] for p in a["paare"]]
    assert a["fehlende"].startswith("Händler fehlt noch")
    modelle = [_modell(S26, _karte("Telekom"), _karte("MediaMarkt"))]
    assert pf.berechne(modelle, KATALOG, {}, HEUTE)["fehlende"].startswith(
        "o2, 1&1 und congstar fehlen"
    )


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
        assert p["offen"][0]["geraete"][0]["grund"] == pf.GRUND_UNZUREICHEND
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


def test_umschalter_hat_alle_paare_und_standard_telekom_im_gerenderten_html():
    s = _rendern(_ansicht_drei())
    tasten = s.select("#pf-wahl button[data-pf]")
    assert [t["data-pf"] for t in tasten] == WAHL
    assert [t["aria-pressed"] for t in tasten] == ["true", "false", "false"]
    assert s.select_one("section#portfolio")["data-standard"] == "Telekom"
    assert [p["data-pf"] for p in s.select(".gr-pf-paar")] == [
        t["data-pf"] for t in tasten
    ]
    assert s.select_one("#pf-wahl").has_attr("hidden")
    assert not any(p.has_attr("hidden") for p in s.select(".gr-pf-paar"))
    modelle = [_modell(S26, _karte("o2"), _karte("congstar"))]
    a = {**pf.berechne(modelle, KATALOG, {}, HEUTE), "hinweis": ""}
    s = _rendern(a)
    assert s.select_one("section#portfolio")["data-standard"] == "o2"
    assert [t["aria-pressed"] for t in s.select("#pf-wahl button")] == ["true", "false"]
