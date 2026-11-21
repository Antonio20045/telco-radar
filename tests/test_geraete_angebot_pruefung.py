"""Prüfung PR 205: Ehrlichkeit der Angebotszählung (Übersicht belegt, Ist ohne Soll,
Tarifidentität, benennbare Tarifwelt-Lücken, parallele Läufe, später Nachtrag).

Die ersten vier Tests sind die Reproduktionen des Prüfers (``/tmp/pruefer/k205``),
übernommen; sie sind gegen den Stand vor der Nachbesserung rot.
"""

from __future__ import annotations

import test_geraete_angebot as base

from telco_radar import geraete_angebot as ga
from telco_radar import geraete_lauf
from telco_radar.collect.geraete.tarifwelt_merkmale import (
    NAMENSMERKMALE as SAMMLER_MERKMALE,
)
from telco_radar.geraete_angebot import einhaengen as ein
from telco_radar.geraete_angebot.gruende import AUSGESCHLOSSEN, NICHT_EINDEUTIG
from telco_radar.geraete_angebot.konkurrenz import Konkurrenz, NichtPruefbar
from telco_radar.geraete_angebot_nachtrag import trage_nach
from telco_radar.geraete_vollstaendigkeit import (
    UNBENANNT,
    Signale,
    baue,
)
from telco_radar.report import geraete_vollstaendigkeit as seite
from telco_radar.tarif_sonderbedingung import NAMENSMERKMALE, sonderbedingung

TAG = base.TAG
T_NETZ = "Saturn/MediaMarkt · Telekom-Netz"
O2_NETZ = "Saturn/MediaMarkt · o2-Netz"


def _katalog():
    return base.Katalog(geraete=[base.Geraet("Apple", "iPhone 17")])


def _zeile(voll: dict, name: str) -> dict:
    return next(
        x
        for x in seite.zeilen({"vollstaendigkeit": voll}, TAG)["zeilen"]
        if x["name"] == name
    )


def _b(sku, tarif_slug, laufzeit=24, anbieter="o2", **preise):
    return {
        "id": f"buendel--x--{sku}--{tarif_slug}--{laufzeit}m",
        "sku_id": sku,
        "anbieter": anbieter,
        "tarif_id": tarif_slug,
        "laufzeit_monate": laufzeit,
        "abgerufen_am": TAG,
        **preise,
    }


def _tarifwelt(kombinationen, **seite_felder) -> ga.Zaehlung:
    s = ga.Seite(
        "https://tarife.mediamarkt.de/smartphones/apple/iphone-17/",
        "Apple iPhone 17",
        status=ga.GELESEN,
        speicher=[ga.Option("256 GB", "256 GB")],
        kombinationen=kombinationen,
        **seite_felder,
    )
    z = ga.Zaehlung("tarifwelt", TAG, f"{TAG}T23:10:00+00:00", seiten=[s], genannt=1)
    z.kacheln = [ga.Kachel(s.url, s.titel)]
    return z


def _haenge(tmp_path, z, ist, signale=None):
    ga.schreibe(tmp_path, z)
    signale = signale or Signale()
    voll = baue(TAG, f"{TAG}T04:00:00+00:00", ist, {}, signale)
    ein.haenge_ein(voll, tmp_path, TAG, ist, signale, _katalog())
    return {x["name"]: x for x in voll["anbieter"]}, voll


SKU = "apple-iphone-17-256gb-schwarz"


def test_sonderbedingung_kennt_dieselbe_liste_wie_der_sammler():
    assert NAMENSMERKMALE == SAMMLER_MERKMALE
    assert sonderbedingung("Magenta Mobil XL Young 5G").endswith("nicht im Vergleich")
    assert sonderbedingung("Allnet Flat 100GB") is None


def test_tarifwelt_luecke_der_messung_benennt_die_kombination(tmp_path):
    z = _tarifwelt([["256 GB", "Allnet Flat 35 GB", 24, "o2"]])
    luecke = [
        "apple-iphone-17 256 GB o2 Allnet Flat 35 GB",
        "Preis wechselt innerhalb 24 Monaten",
    ]
    signale = Signale(tarifwelt={"luecken_liste": [luecke]})
    zeilen, _ = _haenge(tmp_path, z, [_b(SKU, "mobile-l", anbieter=O2_NETZ)], signale)
    k = zeilen[O2_NETZ]["ebenen"]["kombinationen"]
    assert k["luecken"][0]["grund"] == "Tarifwelt: Preis wechselt innerhalb 24 Monaten"


def test_gleichnamige_tarife_werden_ueber_den_preis_zugeordnet(tmp_path):
    """Zwei „Mobile Unlimited L Promo“: einer mit gleichem Preis (erfasst), einer mit
    anderem Preis – Lücke und Ist ohne Soll heißen „nicht eindeutig zuordenbar“."""
    name = "Mobile Unlimited L Promo"
    z = _tarifwelt(
        [["256 GB", name, 24, "o2", "1-39.99"], ["256 GB", name, 24, "o2", "1-49.99"]]
    )
    ist = [
        _b(
            SKU,
            "mobile-unlimited-l-promo-86c58f",
            anbieter=O2_NETZ,
            geraet_zuzahlung=1.0,
            tarif_monatlich=39.99,
        ),
        _b(
            SKU,
            "mobile-unlimited-l-promo-86c591",
            anbieter=O2_NETZ,
            geraet_zuzahlung=1.0,
            tarif_monatlich=44.99,
        ),
    ]
    zeilen, _ = _haenge(tmp_path, z, ist)
    k = zeilen[O2_NETZ]["ebenen"]["kombinationen"]
    assert (k["soll"], k["erfasst"], k["luecken_zahl"], k["nicht_im_soll_zahl"]) == (
        2,
        1,
        1,
        1,
    )
    assert k["luecken"][0]["grund"] == NICHT_EINDEUTIG
    assert k["nicht_im_soll"][0]["grund"] == NICHT_EINDEUTIG
    assert k["nicht_im_soll_unbenannt"] == 0


def test_ausschluss_der_seite_benennt_den_erfassten_preis(tmp_path):
    z = base._congstar(("256 GB",))
    z.uebersicht_ende = "Seite ohne Nachlade-Knopf, ganz gescrollt"
    s = z.seiten[0]
    s.kombinationen = [
        ["256 GB", t.text, n]
        for t in s.tarife
        for n in (24, 36)
        if not (t.text == "Allnet Flat M" and n == 36)
    ]
    s.ausgeschlossen = [["Allnet Flat M", 36]]
    zeilen, _ = base._voll(tmp_path, [z], _katalog())
    k = zeilen["congstar"]["ebenen"]["kombinationen"]
    grund = AUSGESCHLOSSEN.format(tarif="Allnet Flat M", monate=36)
    benannt = [e for e in k["nicht_im_soll"] if e["grund"] == grund]
    assert [e["grund"] for e in benannt] == [grund, grund]
    assert sorted(e["schluessel"][16:21] for e in benannt) == ["256gb", "512gb"]


def test_uebersicht_ohne_zahl_braucht_den_beleg(tmp_path):
    ohne = base._congstar()
    zeilen, voll = base._voll(tmp_path, [ohne], _katalog())
    assert zeilen["congstar"]["angebot"]["uebersicht"]["vollstaendig"] is False
    assert "vollständig" not in _zeile(voll, "congstar")["marke"]
    mit = base._congstar()
    mit.uebersicht_ende = "Nachladen bis zum Ende (2-mal), danach kein Knopf mehr"
    mit.konkurrenz = "keine parallelen Läufe auf diesem Host"
    zeilen, voll = base._voll(tmp_path, [mit], _katalog())
    assert zeilen["congstar"]["angebot"]["uebersicht"]["vollstaendig"] is True
    assert _zeile(voll, "congstar")["marke"] == "vollständig"
    assert _zeile(voll, "congstar")["satz"] == (
        "congstar: 32 von 32 Angeboten erfasst (1 von 1 Geräten gezählt)"
    )


def test_ungelesene_auswahl_einer_seite_ist_nicht_vollstaendig(tmp_path):
    z = _tarifwelt(
        [["256 GB", "Mobile L", 24, "o2"]],
        unvollstaendig=["256 GB, Netz o2: Seite nennt 2 Tarife, gelesen 1"],
    )
    zeilen, voll = _haenge(tmp_path, z, [_b(SKU, "mobile-l", anbieter=O2_NETZ)])
    assert zeilen[O2_NETZ]["angebot"]["status"] == ga.TEILWEISE
    o2 = _zeile(voll, O2_NETZ)
    assert "Auswahl nicht ganz gelesen" in o2["marke"]
    assert any("Seite nennt 2 Tarife, gelesen 1" in h for h in o2["hinweise"])


def test_paralleler_lauf_auf_demselben_host_wird_abgewartet_oder_benannt():
    uhr = [0.0]
    laeufe = {"klick.yml": 1}

    def abfrage(workflow: str) -> int:
        return laeufe.get(workflow, 0)

    def schlafe(s: float) -> None:
        uhr[0] += s
        if uhr[0] >= 120:
            laeufe.clear()

    k = Konkurrenz(abfrage, "telekom", lambda: uhr[0], schlafe)
    assert k.frei(ende=3600) is None and uhr[0] == 120
    laeufe["gegenprobe.yml"] = 1
    assert k.zwischendurch(ende=3600) is None
    uhr[0] += 400
    k2 = Konkurrenz(lambda w: 1, "congstar", lambda: uhr[0], lambda s: None)
    assert k2.frei(ende=uhr[0] + 60) == "Klick-Lauf läuft"
    tw = Konkurrenz(
        lambda w: 1 if w == "klick.yml" else 0, "tarifwelt", lambda: 0.0, lambda s: None
    )
    assert tw.frei(ende=3600) is None


def test_konkurrenz_ohne_github_ist_benannt():
    lokal = Konkurrenz(None, "o2", lambda: 0.0, lambda s: None)
    assert lokal.frei(ende=100) is None
    assert lokal.vermerk.startswith("Prüfung auf parallele Läufe nicht möglich")

    def kaputt(workflow: str) -> int:
        raise NichtPruefbar("HTTP 401")

    k = Konkurrenz(kaputt, "o2", lambda: 0.0, lambda s: None)
    assert k.frei(ende=100) is None and "HTTP 401" in k.vermerk


def test_spaete_zaehlung_wird_in_die_lauf_datei_nachgetragen(tmp_path):
    signale = Signale()
    ist = base._ist()
    assert trage_nach(tmp_path, TAG, ist, signale, _katalog()) is None
    voll = baue(TAG, f"{TAG}T04:00:00+00:00", ist, {}, signale)
    geraete_lauf.schreibe(tmp_path, TAG, {"bilanz": {"x": 1}, "vollstaendigkeit": voll})
    z = base._congstar()
    z.uebersicht_ende = "Seite ohne Nachlade-Knopf, ganz gescrollt"
    ga.schreibe(tmp_path, z)
    assert trage_nach(tmp_path, TAG, ist, signale, _katalog()) is not None
    lauf = geraete_lauf.lies(tmp_path, TAG)
    assert lauf["bilanz"] == {"x": 1}
    zeilen = {x["name"]: x for x in lauf["vollstaendigkeit"]["anbieter"]}
    assert zeilen["congstar"]["ebenen"]["kombinationen"]["soll"] == 32
    assert zeilen["Telekom"]["angebot"]["status"] == "fehlt"
    assert zeilen["congstar"]["ebenen"]["kombinationen"]["luecken_zahl"] == 0
    assert UNBENANNT not in {
        lu["grund"] for lu in zeilen["congstar"]["ebenen"]["kombinationen"]["luecken"]
    }


def _o2_zaehlung(tarifuebersicht, grund=None) -> ga.Zaehlung:
    s = ga.Seite(
        "https://www.o2online.de/e-shop/apple/apple-iphone-17-256gb-schwarz-details",
        "Apple iPhone 17",
        status=ga.GELESEN,
        speicher=[ga.Option("256 GB", "256 GB")],
        kombinationen=[
            ["256 GB", "O2 Mobile Unlimited M Plus mit 100 MBit/s", n] for n in (24, 36)
        ],
    )
    z = ga.Zaehlung("o2", TAG, f"{TAG}T23:10:00+00:00", seiten=[s], genannt=1)
    z.kacheln = [ga.Kachel(s.url, s.titel)]
    z.tarifuebersicht, z.tarifuebersicht_grund = tarifuebersicht, grund
    return z


def _o2_ist() -> list[dict]:
    url = "https://www.o2online.de/e-shop/apple/apple-iphone-17-256gb-schwarz-details"
    return [
        {
            **_b(SKU, slug, n),
            "tarif_name": name,
            "quelle_url": f"{url}?ratenzahlung={n}&tarif={tarif}",
        }
        for slug, name, tarif in (
            (
                "o2-mobile-unlimited-m-plus-mit-100-mbit-s-24-mon",
                "O2 Mobile Unlimited M Plus mit 100 MBit/s (24 Mon.)",
                "o2-mobile-unlimited-m-plus",
            ),
            (
                "o2-mobile-unlimited-l-mit-300-mbit-s-24-mon",
                "O2 Mobile Unlimited L mit 300 MBit/s (24 Mon.)",
                "o2-mobile-unlimited-l",
            ),
            (
                "o2-mobile-special-24-mon",
                "O2 Mobile Special (24 Mon.)",
                "o2-mobile-special",
            ),
        )
        for n in (24, 36)
    ]


def test_o2_tarifuebersicht_ist_ein_anderer_kaufweg_nicht_soll(tmp_path):
    """Soll kommt allein aus der Produktseite (Prüfung PR 205, Runde 4). „O2 Mobile
    Unlimited L“ (nur über die Tarifübersicht kaufbar) fällt benannt aus dem Vergleich,
    „O2 Mobile Special“ (auf keinem Weg) ist ein Preis, den o2 so nicht anbietet."""
    uebersicht = base.LS.o2_tarifuebersicht(base._html("o2_tarifuebersicht"))
    assert len(uebersicht) == 10
    assert "O2 Mobile Unlimited L" in {o.text for o in uebersicht}
    zeilen, voll = _haenge(tmp_path, _o2_zaehlung(uebersicht), _o2_ist())
    k = zeilen["o2"]["ebenen"]["kombinationen"]
    assert (k["soll"], k["erfasst"], k["luecken_zahl"]) == (2, 2, 0)
    assert {e["schluessel"].split("--")[1] for e in k["nicht_im_soll"]} == {
        "o2-mobile-special"
    }
    assert {e["grund"] for e in k["nicht_im_soll"]} == {
        "Tarif nicht in der Auswahl der Produktseite"
    }
    assert k["nicht_verglichen_zahl"] == 2
    assert {e["grund"] for e in k["nicht_verglichen"]} == {
        "anderer Kaufweg (Tarifübersicht), nicht gezählt"
    }
    herkunft = zeilen["o2"]["angebot"]["herkunft"]
    assert herkunft["tarifuebersicht"]["art"] == "browser_tarifuebersicht"
    assert herkunft["produktseite"]["art"] == "browser_auswahl"
    o2 = _zeile(voll, "o2")
    assert any(s.startswith("Tarifübersicht: 10 Tarife") for s in o2["ebenen_saetze"])
    assert "vollständig" not in o2["marke"]


def test_o2_ohne_tarifuebersicht_gilt_die_produktseite_und_der_ausfall(tmp_path):
    grund = "Tarifübersicht nicht gelesen: Browserfehler: Timeout"
    zeilen, voll = _haenge(tmp_path, _o2_zaehlung(None, grund), _o2_ist())
    k = zeilen["o2"]["ebenen"]["kombinationen"]
    assert (k["soll"], k["erfasst"]) == (2, 2)
    assert zeilen["o2"]["angebot"]["status"] == ga.TEILWEISE
    o2 = _zeile(voll, "o2")
    assert grund in o2["hinweise"] and "vollständig" not in o2["marke"]
