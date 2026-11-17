"""Portfolio-Vergleich als Kachelraster mit Foto-Platz (Paket C, 17.11.2026).

Antonio: „der portfolio vergleich ist ne katastrophe … ich will pro modell ein
foto haben schöne cleane darstellung ohne dass ich zwei stunden nach unten
scrollen muss". Geprüft wird: je Gerät eine Kachel mit Foto-Platz, Hersteller
und Modellname; ohne Zuordnung eine Silhouette statt eines kaputten Bildes;
höchstens `KACHELN_SICHTBAR` Kacheln je Liste offen, der Rest in einem
zugeklappten `<details>` - und dass dabei keine Zahl wandert.

Alle Stichtage sind fest; nichts hängt am heutigen Datum.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import jinja2
from bs4 import BeautifulSoup

from telco_radar.analyze import geraete_bilder
from telco_radar.geraete_model import Geraet, Katalog
from telco_radar.report import geraete_portfolio as pf
from telco_radar.report import geraete_portfolio_anzeige as anzeige

VORLAGEN = Path(pf.__file__).parent / "templates"
HEUTE = "2026-11-10"


def _g(hersteller: str, modell: str, generation: int) -> Geraet:
    return Geraet(
        hersteller=hersteller, modell=modell, generation=generation, speicher=[256]
    )


def _karte(anbieter: str) -> dict:
    return {
        "anbieter": anbieter,
        "gesamt": 1000.0,
        "frisch": True,
        "zaehlt": True,
        "naeherung": False,
        "zustand": "neu",
    }


def _modell(g: Geraet, *karten: dict) -> dict:
    return {
        "id": f"{g.device_id}-256",
        "device_id": g.device_id,
        "karten": list(karten),
    }


def _beleg_alle(anbieter: str) -> dict:
    return {
        (anbieter, "*"): {
            "grund": "Gerät ist nicht in der Geräteliste",
            "geprueft": date(2026, 11, 5),
            "bis": date(2026, 11, 19),
            "beleg": "https://beispiel.test/beleg.png",
        }
    }


ACHT = [
    _g("Samsung", "Galaxy XCover7 Pro EE", 7),
    _g("Samsung", "Galaxy Xcover 7 EE", 7),
    _g("Motorola", "edge 70", 70),
    _g("Motorola", "edge 70 fusion", 70),
    _g("Telekom", "T Phone 3", 3),
    _g("Telekom", "T Phone 3 Pro", 3),
    _g("Fairphone", "Fairphone 6 Plus", 6),
    _g("Nothing", "Phone (4a) Pro", 4),
]


def _ansicht(geraete: list[Geraet], bilder: dict[str, str] | None = None) -> dict:
    """Alle Geräte führt Telekom, Vodafone keines; die Vodafone-Lücke ist belegt."""
    katalog = Katalog(geraete=list(geraete))
    modelle = [_modell(g, _karte("Telekom")) for g in geraete]
    rechnung = pf.berechne(
        modelle, katalog, _beleg_alle("Vodafone"), HEUTE, None, bilder
    )
    return {**rechnung, "hinweis": ""}


def _rendern(ansicht: dict) -> BeautifulSoup:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(VORLAGEN), autoescape=True)
    html = env.get_template("_geraete_portfolio.html.j2").render(
        geraete={"hersteller": {"portfolio": ansicht}}
    )
    return BeautifulSoup(html, "html.parser")


def _liste_w(s: BeautifulSoup):
    return s.select_one('.gr-pf-paar[data-pf="Telekom"] .gr-pf-liste--w')


def test_je_geraet_eine_kachel_mit_foto_hersteller_und_modellname():
    """Samsung steht in HERSTELLER_VORAN und damit vor Motorola; die belegte
    Liste trägt keine Hersteller-Zwischenüberschriften mehr."""
    a = _ansicht(ACHT[:3])
    liste = _liste_w(_rendern(a))
    kacheln = liste.select(".gr-pf-kachel")
    assert len(kacheln) == 3 == _paar(a)["n_w"]
    erste = kacheln[0]
    assert erste.select_one(".gr-pf-marke").text == "Samsung"
    assert erste.select_one(".gr-pf-geraet").text == "Galaxy XCover7 Pro EE"
    assert erste.select_one(".gr-pf-foto") is not None
    assert liste.select(".gr-pf-gruppe") == [], (
        "keine Hersteller-Zwischenüberschrift mehr"
    )


def _paar(a: dict) -> dict:
    return next(p for p in a["paare"] if p["name"] == "Telekom")


def test_ohne_zuordnung_steht_eine_silhouette_statt_eines_bildes():
    liste = _liste_w(_rendern(_ansicht(ACHT[:2])))
    assert liste.select("img") == []
    silhouetten = liste.select(".gr-pf-foto .gr-pf-silhouette use")
    assert len(silhouetten) == 2
    assert all(u["href"] == "#pf-geraet" for u in silhouetten)


def test_mit_zuordnung_zeigt_die_kachel_das_foto_aus_dem_eigenen_ordner():
    g = ACHT[2]
    bilder = {g.device_id: "static/geraete/motorola-edge-70.jpg"}
    liste = _liste_w(_rendern(_ansicht([g], bilder)))
    bild = liste.select_one(".gr-pf-foto img")
    assert bild["src"] == "static/geraete/motorola-edge-70.jpg"
    assert bild["alt"] == "Motorola edge 70"
    assert bild["loading"] == "lazy"
    assert liste.select(".gr-pf-silhouette") == []


def test_hoechstens_sechs_kacheln_offen_der_rest_steht_zugeklappt():
    """Gegenprobe zur Kopfzahl: keine Zahl wandert, alle acht Geräte stehen
    weiter im Dokument - nur sechs davon ohne Aufklappen."""
    a = _ansicht(ACHT)
    liste = _liste_w(_rendern(a))
    raster = liste.select(".gr-pf-kacheln")
    assert len(raster[0].select(".gr-pf-kachel")) == anzeige.KACHELN_SICHTBAR == 6
    mehr = liste.select_one("details.gr-pf-mehr")
    assert not mehr.has_attr("open")
    assert mehr.select_one("summary").text == "2 weitere Geräte zeigen"
    assert len(mehr.select(".gr-pf-kachel")) == 2
    assert len(liste.select(".gr-pf-kachel")) == 8 == _paar(a)["n_w"]
    assert _paar(a)["kopf"] == "8 Geräte nur bei Telekom, 0 nur bei Vodafone"


def test_bis_sechs_geraete_gibt_es_keinen_zugeklappten_rest():
    liste = _liste_w(_rendern(_ansicht(ACHT[:6])))
    assert liste.select("details.gr-pf-mehr") == []
    assert len(liste.select(".gr-pf-kachel")) == 6
    assert anzeige.mehr_satz(1) == "1 weiteres Gerät zeigen"


def test_belegkachel_nennt_den_link_und_das_pruefdatum_knapp():
    kachel = _liste_w(_rendern(_ansicht(ACHT[:1]))).select_one(".gr-pf-kachel")
    beleg = kachel.select_one(".gr-pf-beleg")
    assert beleg.select_one("a")["href"] == "https://beispiel.test/beleg.png"
    assert beleg.text.strip() == "Beleg · geprüft 05.11.2026"
    assert kachel["title"] == (
        "Gerät ist nicht in der Geräteliste · geprüft 05.11.2026 · "
        "gültig bis 19.11.2026"
    )


def test_bildzuordnung_ohne_datei_ist_leer_und_meldet_fehlende_bilder(tmp_path, caplog):
    assert geraete_bilder.lade_bilder(tmp_path / "gibtsnicht.yaml", tmp_path) == {}
    pfad = tmp_path / "geraete_bilder.yaml"
    ordner = tmp_path / "geraete"
    ordner.mkdir()
    (ordner / "da.jpg").write_bytes(b"x")
    pfad.write_text(
        "bilder:\n"
        "  motorola-edge-70:\n    datei: da.jpg\n"
        "  apple-iphone-18-pro:\n    datei: fehlt.jpg\n",
        encoding="utf-8",
    )
    with caplog.at_level("WARNING"):
        aus = geraete_bilder.lade_bilder(pfad, ordner)
    assert aus == {"motorola-edge-70": "static/geraete/da.jpg"}
    assert "fehlt.jpg" in caplog.text


def test_unlesbare_bildzuordnung_zeigt_platzhalter_statt_eines_ausfalls(tmp_path):
    pfad = tmp_path / "kaputt.yaml"
    pfad.write_text("bilder: [: :\n", encoding="utf-8")
    assert geraete_bilder.lade_bilder(pfad, tmp_path) == {}


def test_bildzuordnung_liegt_im_config_ordner_neben_data_state(tmp_path):
    state = tmp_path / "data" / "state"
    assert (
        geraete_bilder.bilder_pfad(state) == tmp_path / "config" / "geraete_bilder.yaml"
    )
