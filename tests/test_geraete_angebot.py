"""Angebotszählung im Browser (Abnahmekriterium 1, Stufe 2): Leser, Zuordnung,
Lücken, Wächter, Tor und Unabhängigkeit vom Sammler.

Die Leser laufen gegen DOM-Schnappschüsse echter Seiten vom 21.11.2026
(``tests/fixtures/geraete_angebot``, Herkunft in ``_herkunft.json``). Ohne Netz, ohne
Uhr: jede Zeit kommt als Parameter.
"""

from __future__ import annotations

import gzip
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from telco_radar import geraete_angebot as ga
from telco_radar import geraete_soll_waechter as waechter
from telco_radar.geraete_angebot import einhaengen as ein
from telco_radar.geraete_angebot import lesen as L
from telco_radar.geraete_angebot import lesen_seiten as LS
from telco_radar.geraete_angebot.tor import Gesperrt, Regeln, Tor, schutzgrund
from telco_radar.geraete_model import Geraet, Katalog
from telco_radar.geraete_vollstaendigkeit import UNBENANNT, Signale, baue

WURZEL = Path(__file__).resolve().parents[1]
FIX = WURZEL / "tests" / "fixtures" / "geraete_angebot"
IST = WURZEL / "tests" / "fixtures" / "geraete_soll" / "ist_auszug_20261121.json"
TAG = "2026-11-21"


def _html(name: str) -> str:
    return gzip.decompress((FIX / f"{name}.html.gz").read_bytes()).decode("utf-8")


@pytest.fixture(scope="module")
def katalog() -> Katalog:
    return Katalog(
        geraete=[
            Geraet("Apple", "iPhone 17"),
            Geraet("Apple", "iPhone 17 Pro"),
            Geraet("Google", "Pixel 11"),
            Geraet("Samsung", "Galaxy A57"),
        ]
    )


def _ist() -> list[dict]:
    return json.loads(IST.read_text("utf-8"))["buendel"]


@pytest.mark.parametrize(
    ("datei", "leser", "zahl"),
    [
        ("telekom_uebersicht", L.telekom_kacheln, 45),
        ("vodafone_uebersicht", L.vodafone_kacheln, 39),
        ("o2_uebersicht_alle", L.o2_kacheln, 36),
        ("einsundeins_uebersicht", L.einsundeins_kacheln, 41),
        ("congstar_uebersicht", L.congstar_kacheln, 39),
        ("tarifwelt_uebersicht", L.tarifwelt_kacheln, 95),
    ],
)
def test_uebersicht_zaehlt_jede_kachel_einmal(datei, leser, zahl):
    kacheln = leser(_html(datei))
    assert len(kacheln) == zahl
    assert len({k.url for k in kacheln}) == zahl
    assert all(k.titel and k.url.startswith("https://") for k in kacheln)


def test_uebersicht_trennt_pakete_und_nicht_smartphones():
    o2 = L.o2_kacheln(_html("o2_uebersicht_alle"))
    pakete = [k.titel for k in o2 if k.paket]
    assert "Apple iPhone 18 Pro Max mit AirPods Pro 3" in pakete
    assert len(pakete) == 18
    tw = [k.titel for k in L.tarifwelt_kacheln(_html("tarifwelt_uebersicht"))]
    fremd = [t for t in tw if not L.ist_smartphone(t)]
    assert len(fremd) == 8 and all(
        t.split()[0] in {"IMOO", "Xplora", "NAVEE"} for t in fremd
    )
    assert (
        L.genannte_zahl("39 Smartphones sortiert nach", r"(\d+) Smartphones sortiert")
        == 39
    )


def test_telekom_karte_nennt_den_namen_der_seite():
    titel = {k.titel for k in L.telekom_kacheln(_html("telekom_uebersicht"))}
    assert {"Apple iPhone 18 Pro", "Samsung Galaxy S26+", "Google Pixel 10a"} <= titel


def test_vodafone_speicher_raten_und_ausgegraut():
    seite = L.vodafone_geraet(_html("vodafone_pixel10a"))
    assert [(o.text[:6], o.waehlbar) for o in seite["speicher"]] == [
        ("128 GB", True),
        ("256 GB", False),
    ]
    assert [o.wert for o in seite["laufzeiten"]] == ["36", "24", "12"]
    assert seite["ausserhalb"] == ["Einmal 549,90 €"]
    assert len(seite["farben"]) == 3


def test_vodafone_tarife_auf_der_seite_oder_in_der_tarifauswahl():
    inline = L.vodafone_tarife_inline(_html("vodafone_pixel10a"))
    assert [o.text for o in inline] == ["Mobil XS", "Mobil S", "Mobil XL"]
    assert L.vodafone_tarife_inline(_html("vodafone_galaxy_s26")) == []
    auswahl = L.vodafone_tarifoptionen(_html("vodafone_iphone17pro_tarifauswahl"))
    assert [o.wert for o in auswahl] == ["267", "268", "271"]
    assert (
        L.vodafone_tarifname(_html("vodafone_iphone17pro_tarifauswahl")) == "Mobil XL"
    )
    assert L.vodafone_tarifname(_html("vodafone_galaxy_s26_tarif_xs")) == "Mobil XS"


def test_vodafone_ausschluss_der_seite_wird_gelesen():
    assert L.vodafone_ausschluesse(_html("vodafone_galaxy_s26")) == [
        ("Mobil S", 36),
        ("Mobil XS", 36),
    ]


def test_o2_tarifkacheln_und_zahlungsplan():
    seite = LS.o2_geraet(_html("o2_galaxy_s26"))
    assert [o.text for o in seite["speicher"]] == ["256 GB", "512 GB"]
    assert [o.text for o in seite["tarife"]][
        -1
    ] == "O2 Mobile on Demand M Plus mit 50 GB+"
    assert len(seite["tarife"]) == 5
    assert [o.wert for o in seite["laufzeiten"]] == ["36", "24"]
    assert seite["ausserhalb"] == ["Einmalzahlung Gerät"]
    nach = LS.o2_geraet(_html("o2_galaxy_s26_512gb"))
    assert len(nach["tarife"]) == 5


def test_einsundeins_fix_zaehlt_flex_ist_ausserhalb():
    seite = LS.einsundeins_geraet(_html("einsundeins_galaxy_s26"))
    assert [o.wert for o in seite["laufzeiten"]] == ["36", "24"]
    assert len(seite["ausserhalb"]) == 2 and all(
        "Flex" in t for t in seite["ausserhalb"]
    )
    tarife = LS.einsundeins_tarife(_html("einsundeins_galaxy_s26_tarifauswahl"))
    assert [o.text for o in tarife] == list(LS.EINSUNDEINS_TARIFE.values())


def test_congstar_nicht_vorhandener_speicher_und_flex_tarif():
    seite = LS.congstar_geraet(_html("congstar_iphone17"))
    assert [(o.text, o.waehlbar) for o in seite["speicher"]] == [
        ("256 GB", True),
        ("512 GB", False),
    ]
    assert len(seite["tarifkacheln"]) == 4 and len(seite["bindung"]) == 2
    assert LS.congstar_tarifname(_html("congstar_galaxy_s26_xs_flex")) == (
        "Allnet Flat XS Flex"
    )


def test_telekom_tarifdialog_und_einmalpreis_ohne_raten():
    tarife = LS.telekom_tarife(_html("telekom_galaxy_s26_tarifdialog"))
    assert [o.text for o in tarife] == [
        "MagentaMobil XL",
        "MagentaMobil L",
        "MagentaMobil M",
        "MagentaMobil S",
        "MagentaMobil XS",
    ]
    assert LS.telekom_gewaehlt(_html("telekom_galaxy_s26_tarifdialog")) == "MF_17791"
    xs = LS.telekom_geraet(_html("telekom_galaxy_s26_xs"))
    assert [o.wert for o in xs["laufzeiten"]] == ["36", "24"]
    nur_einmal = LS.telekom_geraet(_html("telekom_pixel10a_xl"))
    assert nur_einmal["laufzeiten"] == [] and nur_einmal["ausserhalb"] == [
        "Einmalpreis"
    ]


def test_tarifwelt_netzzahl_ist_die_gegenprobe_der_namen():
    zahlen = LS.tarifwelt_netzzahlen(_html("tarifwelt_iphone17pro_dialog"))
    assert zahlen == {"o2": 7, "telefonica": 0, "telekom": 8, "vodafone": 6}
    weitere, gewaehlt = LS.tarifwelt_tarifnamen(_html("tarifwelt_iphone17pro_dialog"))
    assert len(weitere) + 1 == sum(zahlen.values())
    telekom, _ = LS.tarifwelt_tarifnamen(_html("tarifwelt_iphone17pro_dialog_telekom"))
    assert len(telekom) == zahlen["telekom"]
    assert [n for n, _ in telekom].count("Magenta Mobil L 5G Aktion") == 2
    assert len({code for _, code in telekom}) == len(telekom)
    o2 = LS.tarifwelt_netzzahlen(_html("tarifwelt_galaxy_s26_dialog_256"))
    namen, sel = LS.tarifwelt_tarifnamen(_html("tarifwelt_galaxy_s26_o2_256"))
    assert len(namen) + (1 if sel and o2["o2"] == len(namen) + 1 else 0) == o2["o2"]
    speicher = LS.tarifwelt_geraet(_html("tarifwelt_iphone17pro"))["speicher"]
    assert [(o.text, o.waehlbar) for o in speicher] == [
        ("256 GB", True),
        ("512 GB", False),
        ("1 TB", True),
    ]


def test_leser_wirft_statt_leer_zu_liefern():
    with pytest.raises(L.LeserFehler):
        L.vodafone_kacheln("<html><body>nichts</body></html>")
    with pytest.raises(L.LeserFehler):
        LS.telekom_geraet("<html></html>")
    assert L.speicher_segment("1 TB") == "1024gb" and L.speicher_segment("x") is None


def _congstar(speicher=("256 GB", "512 GB"), status=ga.GELESEN, **seite) -> ga.Zaehlung:
    tarife = [
        f"Allnet Flat {g}{f}" for g in ("XS", "S", "M", "L") for f in ("", " Flex")
    ]
    s = ga.Seite(
        "https://www.congstar.de/geraete/apple/apple-iphone-17/",
        "Apple iPhone 17",
        status=status,
        speicher=[ga.Option(t, t) for t in speicher],
        tarife=[ga.Option(t, t) for t in tarife],
        laufzeiten=[ga.Option("36 mtl. Zahlungen", "36"), ga.Option("24", "24")],
        **seite,
    )
    return ga.Zaehlung(
        "congstar",
        TAG,
        f"{TAG}T00:10:00+00:00",
        f"{TAG}T00:40:00+00:00",
        ga.GELESEN,
        uebersicht="https://www.congstar.de/geraete/handy/",
        kacheln=[ga.Kachel(s.url, s.titel)],
        seiten=[s],
    )


def _voll(tmp_path, zaehlungen, katalog, signale=None):
    for z in zaehlungen:
        ga.schreibe(tmp_path, z)
    signale = signale or Signale()
    voll = baue(TAG, f"{TAG}T04:00:00+00:00", _ist(), {}, signale)
    ein.haenge_ein(voll, tmp_path, TAG, _ist(), signale, katalog)
    return {z["name"]: z for z in voll["anbieter"]}, voll


def test_kreuzprodukt_gegen_den_echten_bestand_ganz_erfasst(tmp_path, katalog):
    zeilen, _ = _voll(tmp_path, [_congstar()], katalog)
    k = zeilen["congstar"]["ebenen"]["kombinationen"]
    assert (k["soll"], k["erfasst"], k["luecken_zahl"]) == (32, 32, 0)
    assert k["quelle"]["art"] == ein.ART_AUSWAHL
    assert zeilen["congstar"]["ebenen"]["modell_speicher"]["erfasst"] == 2
    m = zeilen["congstar"]["ebenen"]["modelle"]
    assert (m["soll"], m["erfasst"]) == (1, 1)
    assert zeilen["congstar"]["soll_quelle"]["gleiche_quelle_wie_sammler"] is False


def test_fehlender_speicher_ohne_signal_ist_unbenannt_und_rot(tmp_path, katalog):
    zeilen, voll = _voll(tmp_path, [_congstar(("256 GB", "512 GB", "1 TB"))], katalog)
    k = zeilen["congstar"]["ebenen"]["kombinationen"]
    assert (k["soll"], k["erfasst"], k["luecken_zahl"]) == (48, 32, 16)
    assert {lu["grund"] for lu in k["luecken"]} == {UNBENANNT}
    assert k["luecken"][0]["name"].startswith("Apple iPhone 17 · 1 TB · Allnet Flat")
    befunde = waechter.pruefe({"datum": TAG, "vollstaendigkeit": voll}, TAG)
    assert any(b.startswith("congstar: ") and "ohne Grund" in b for b in befunde)


def test_vermerk_zum_modell_benennt_die_luecke_waechter_gruen(tmp_path, katalog):
    vermerk = "Bei congstar nur mit 256 GB und 512 GB gelesen (21.11.2026)"
    signale = Signale(erfassung={"congstar|apple-iphone-17": vermerk})
    zeilen, voll = _voll(
        tmp_path, [_congstar(("256 GB", "512 GB", "1 TB"))], katalog, signale
    )
    k = zeilen["congstar"]["ebenen"]["kombinationen"]
    assert {lu["grund"] for lu in k["luecken"]} == {vermerk}
    befunde = waechter.pruefe({"datum": TAG, "vollstaendigkeit": voll}, TAG)
    assert not [b for b in befunde if b.startswith("congstar")]


def test_ausgegrauter_speicher_zaehlt_nicht_ins_soll(tmp_path, katalog):
    z = _congstar(("256 GB", "512 GB", "1 TB"))
    z.seiten[0].speicher[2].waehlbar = False
    zeilen, _ = _voll(tmp_path, [z], katalog)
    assert zeilen["congstar"]["ebenen"]["kombinationen"]["soll"] == 32


def test_ist_ohne_soll_wird_ausgewiesen(tmp_path, katalog):
    zeilen, _ = _voll(tmp_path, [_congstar(("256 GB",))], katalog)
    k = zeilen["congstar"]["ebenen"]["kombinationen"]
    assert (k["soll"], k["erfasst"], k["nicht_im_soll_zahl"]) == (16, 16, 16)
    assert all("512gb" in e["schluessel"] for e in k["nicht_im_soll"])


def test_ungezaehlte_seite_faellt_aus_dem_vergleich(tmp_path, katalog):
    """Telekom: iPhone 17 gezählt, Pixel 11 im Zeitbudget nicht: dessen Ist fällt
    aus dem Vergleich und erscheint nicht als „nicht im Soll“."""
    gelesen = ga.Seite(
        "https://www.telekom.de/shop/geraet/apple/apple-iphone-17/schwarz-256-gb",
        "Apple iPhone 17",
        status=ga.GELESEN,
        speicher=[ga.Option("256 GB", "256 GB"), ga.Option("512 GB", "512 GB")],
        tarife=[ga.Option(f"MagentaMobil {g}", g) for g in ("XS", "S", "M", "L", "XL")],
        laufzeiten=[ga.Option("24", "24")],
    )
    offen = ga.Seite(
        "https://www.telekom.de/shop/geraet/google/google-pixel-11/frost-256-gb",
        "Google Pixel 11",
        status=ga.ZEITGRENZE,
        grund="Zeitbudget des Jobs erschöpft",
    )
    z = ga.Zaehlung("telekom", TAG, f"{TAG}T23:10:00+00:00", seiten=[gelesen, offen])
    z.kacheln = [ga.Kachel(s.url, s.titel) for s in z.seiten]
    zeilen, _ = _voll(tmp_path, [z], katalog)
    angebot = zeilen["Telekom"]["angebot"]
    assert angebot["nicht_gezaehlt_zahl"] == 1
    assert angebot["nicht_gezaehlt"][0]["grund"] == "Zeitbudget des Jobs erschöpft"
    k = zeilen["Telekom"]["ebenen"]["kombinationen"]
    assert k["soll"] == 10
    assert not [e for e in k["nicht_im_soll"] if "pixel-11" in e["schluessel"]]
    assert [e for e in k["nicht_im_soll"] if "galaxy-a57" in e["schluessel"]]


def test_ohne_gezaehlte_seite_fehlt_das_soll_benannt(tmp_path, katalog):
    zeilen, _ = _voll(
        tmp_path, [_congstar(status=ga.ZEITGRENZE, grund="Zeitbudget")], katalog
    )
    k = zeilen["congstar"]["ebenen"]["kombinationen"]
    assert k["soll"] is None
    assert (
        k["soll_grund"] == f"{ein.ANGEBOT_FEHLT}: 1 Seiten nicht gezählt (Zeitbudget)"
    )


def test_abhaengigkeiten_der_seite_statt_kreuzprodukt(tmp_path, katalog):
    """Telekom XS nur mit 256 GB: die Seite nennt die Kombinationen ausdrücklich."""
    z = _congstar()
    z.seiten[0].kombinationen = [
        ["256 GB", "Allnet Flat M", 24],
        ["256 GB", "Allnet Flat M", 36],
        ["512 GB", "Allnet Flat M", 24],
    ]
    zeilen, _ = _voll(tmp_path, [z], katalog)
    k = zeilen["congstar"]["ebenen"]["kombinationen"]
    assert (k["soll"], k["erfasst"]) == (3, 3)


def test_tarifwelt_je_netz_und_vielfachheit(tmp_path, katalog):
    s = ga.Seite(
        "https://tarife.mediamarkt.de/smartphones/apple/iphone-17/",
        "Apple iPhone 17",
        status=ga.GELESEN,
        speicher=[ga.Option("256 GB", "256 GB")],
        kombinationen=[
            ["256 GB", "Mobile Unlimited L Promo", 24, "o2"],
            ["256 GB", "Mobile Unlimited L Promo", 24, "o2"],
            ["256 GB", "Magenta Mobil XL 5G", 24, "telekom"],
        ],
    )
    z = ga.Zaehlung("tarifwelt", TAG, f"{TAG}T23:10:00+00:00", seiten=[s])
    z.kacheln = [ga.Kachel(s.url, s.titel)]
    zeilen, _ = _voll(tmp_path, [z], katalog)
    o2 = zeilen["Saturn/MediaMarkt · o2-Netz"]["ebenen"]["kombinationen"]
    assert o2["soll"] == 2
    vf = zeilen["Saturn/MediaMarkt · Vodafone-Netz"]["ebenen"]
    assert vf["modelle"]["soll"] == 0 and vf["kombinationen"]["soll"] == 0
    assert vf["kombinationen"]["nicht_im_soll_zahl"] == 0


def test_fehlende_zaehlung_ist_benannt_nie_das_ist_als_soll(tmp_path, katalog):
    zeilen, voll = _voll(tmp_path, [], katalog)
    for z in zeilen.values():
        k = z["ebenen"]["kombinationen"]
        assert k["soll"] is None
        assert (
            k["soll_grund"] == f"{ein.ANGEBOT_FEHLT}: keine Zählung für den 21.11.2026"
        )
        assert z["angebot"]["status"] == "fehlt"
    assert waechter.pruefe({"datum": TAG, "vollstaendigkeit": voll}, TAG) == []


def test_veraltete_oder_unlesbare_zaehlung_ist_benannt(tmp_path, katalog):
    alt = _congstar()
    alt.messtag = "2026-11-20"
    ga.schreibe(tmp_path, alt)
    (tmp_path / ga.ORDNER / f"{TAG}-1und1.json").write_text("{kaputt", "utf-8")
    zeilen, _ = _voll(tmp_path, [], katalog)
    assert zeilen["congstar"]["angebot"]["grund"] == (
        "keine Zählung für den 21.11.2026, letzte vom 20.11.2026"
    )
    assert zeilen["1&1"]["angebot"]["grund"].startswith("Zählung nicht lesbar")


def test_gesperrter_anbieter_ohne_ergebnis_ist_benannt(tmp_path, katalog):
    z = ga.Zaehlung("telekom", TAG, f"{TAG}T23:10:00+00:00", laufstatus=ga.GESPERRT)
    z.grund = "Schutzantwort des Anbieters (HTTP 403), nicht umgangen"
    zeilen, _ = _voll(tmp_path, [z], katalog)
    assert zeilen["Telekom"]["ebenen"]["kombinationen"]["soll_grund"] == (
        f"{ein.ANGEBOT_FEHLT}: {z.grund}"
    )


def test_datei_rundweg_und_fremdes_format(tmp_path):
    z = _congstar()
    ziel = ga.schreibe(tmp_path, z)
    assert ziel.name == f"{TAG}-congstar.json"
    assert ga.lies(tmp_path, TAG, "congstar") == z
    ziel.write_text(json.dumps({"format": 99}), "utf-8")
    with pytest.raises(ga.AngebotsdateiFehler):
        ga.lies(tmp_path, TAG, "congstar")


def test_messtag_und_sperrfenster_ohne_uhr():
    spaet = datetime(2026, 11, 21, 23, 5, tzinfo=UTC)
    assert ga.messtag(spaet) == "2026-11-22"
    assert ga.sperre_ab(spaet, ga.KLICK_FENSTER) == datetime(2026, 11, 22, tzinfo=UTC)
    assert ga.sperre_ab(spaet, ga.TARIFWELT_FENSTER) == datetime(
        2026, 11, 22, 2, tzinfo=UTC
    )
    assert (
        ga.sperre_ab(datetime(2026, 11, 22, 1, 30, tzinfo=UTC), ga.KLICK_FENSTER)
        is None
    )


def test_tor_robots_crawl_delay_besuchszeit_und_schutz():
    text = "User-agent: *\nDisallow: /checkout\nCrawl-delay: 7\nVisit-time: 2200-2359\n"
    nacht = datetime(2026, 11, 21, 23, 0, tzinfo=UTC)
    regeln = Regeln(200, text)
    assert regeln.verbot("https://x.de/checkout", nacht).startswith(
        "robots.txt verbietet"
    )
    assert regeln.verbot("https://x.de/handys", nacht) is None
    assert regeln.verbot("https://x.de/handys", datetime(2026, 11, 21, 9, tzinfo=UTC))
    assert regeln.crawl_delay() == 7.0
    assert Regeln(404, "").verbot("https://x.de/a", nacht) is None
    assert "verweigert" in Regeln(403, "").verbot("https://x.de/a", nacht)
    assert "nicht lesbar" in Regeln(0, "").verbot("https://x.de/a", nacht)
    assert schutzgrund(403, "", "") and schutzgrund(200, "Bitte Captcha lösen", "")
    assert schutzgrund(200, "iPhone 17", "Speicher wählen") is None

    uhr = [100.0]
    geschlafen: list[float] = []
    tor = Tor(
        lambda u: (200, text), lambda: nacht, lambda: uhr[0], geschlafen.append, 5.0
    )
    tor.passiere("https://x.de/a")
    uhr[0] += 2.0
    tor.passiere("https://x.de/b")
    assert geschlafen == [5.0]
    with pytest.raises(Gesperrt):
        tor.passiere("https://x.de/checkout")


def test_skript_frist_passt_zu_den_jobminuten():
    sys.path.insert(0, str(WURZEL / "scripts"))
    import angebot_zaehlen as skript

    assert (
        skript.job_frist("telekom")
        == skript.JOB_MINUTEN_STANDARD * 60 - skript.PUFFER_S
    )
    assert skript.job_frist("tarifwelt") == skript.JOB_MINUTEN["tarifwelt"] * 60 - (
        skript.PUFFER_S
    )
    for adresse, name in [
        (
            "https://www.telekom.de/shop/geraet/samsung/samsung-galaxy-s26/weiss-256-gb",
            "Samsung Galaxy S26",
        ),
        (
            "https://www.vodafone.de/privat/handys/google-pixel-10a.html",
            "Google Pixel 10a",
        ),
        (
            "https://tarife.mediamarkt.de/smartphones/samsung/galaxy-s26/",
            "Samsung Galaxy S26",
        ),
        (
            "https://www.o2online.de/e-shop/apple/apple-iphone-17-256gb-schwarz-details",
            "Apple iPhone 17",
        ),
    ]:
        assert L.name_aus_adresse(adresse) == name


def test_zaehler_kennt_den_sammler_und_die_gegenprobe_nicht():
    """Frischer Interpreter: Paket und Skript laden nichts aus ``collect.geraete``,
    keine Gegenprobe, keinen Klick-Lauf."""
    code = (
        "import sys; sys.path.insert(0, 'scripts');"
        "import telco_radar.geraete_angebot.einhaengen,"
        " telco_radar.geraete_angebot.wege,"
        " telco_radar.geraete_angebot.tor, angebot_zaehlen;"
        "print([m for m in sys.modules if m.startswith('telco_radar.collect.geraete')"
        " or 'gegenprobe' in m or 'klick' in m])"
    )
    aus = subprocess.run(
        [sys.executable, "-c", code],
        cwd=WURZEL,
        env={"PYTHONPATH": str(WURZEL / "src"), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=True,
    )
    assert aus.stdout.strip() == "[]"
