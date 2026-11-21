"""Ein Seitenbesuch prüft alle gewählten Bündel seiner Seite (``gegenprobe_wege``).

Lauf 21.11.2026 (Actions 44863947277): je Bündel ein eigener Besuch; o2s 452
Änderungen auf 93 Geräteseiten und 1&1s 174 auf wenigen Produktseiten brauchten das
ganze Zeitbudget. Seitdem gruppiert ``seite_von`` die Auswahl nach Seitenbesuch, und
``lies_gruppe`` liest jedes Bündel der Gruppe auf der einmal geöffneten Seite.
"""

from __future__ import annotations

import pytest
from test_beleg_skripte import lade_skript

from telco_radar import gegenprobe as gp
from telco_radar.collect.geraete import gegenprobe_browser as gb
from telco_radar.collect.geraete import gegenprobe_einsundeins as eins
from telco_radar.collect.geraete import gegenprobe_wege as wege
from telco_radar.collect.geraete.gegenprobe_schritte import nach_tarif

SKRIPT = lade_skript("gegenprobe")

EINS_URL = (
    "https://mobile.1und1.de/flow2/mobile/ssc-private/tariffselect?tariffChangeUrl="
    "%2F%2Fmobile.1und1.de%2Fgoogle-pixel-11-pro-fold&optionalPrecedingDocuments="
    "%2F%2Fmobile.1und1.de%2Fgoogle-pixel-11-pro-fold&traceId=99394a07"
)


def _eins(tarif: str, speicher: str = "256gb", raten: int = 24) -> dict:
    return {
        "id": f"buendel--1-1--google-pixel-11-pro-fold-{speicher}-schwarz--{tarif}"
        f"--{raten}m",
        "sku_id": f"google-pixel-11-pro-fold-{speicher}-schwarz",
        "tarif_name": tarif,
        "laufzeit_monate": raten,
        "quelle_url": EINS_URL,
    }


def test_einsundeins_produktseite_aus_der_tarifauswahl():
    assert eins.produktseite(EINS_URL) == (
        "https://mobile.1und1.de/google-pixel-11-pro-fold"
    )
    assert eins.produktseite("https://mobile.1und1.de/iphone-17?x=1") == (
        "https://mobile.1und1.de/iphone-17"
    )


def test_einsundeins_ein_besuch_je_speicher_und_laufzeit():
    s, l_ = _eins("1&1 All-Net-Flat S"), _eins("1&1 All-Net-Flat L")
    assert wege.seite_von("1-1", s) == wege.seite_von("1-1", l_)
    assert wege.seite_von("1-1", s) != wege.seite_von("1-1", _eins("x", raten=36))
    assert wege.seite_von("1-1", s) != wege.seite_von("1-1", _eins("x", "512gb"))


O2 = (
    "https://www.o2online.de/e-shop/apple/apple-iphone-18-pro-256gb-schwarz-details"
    "?ohne-tarif=nein&zielgruppe=privatkunden&ratenzahlung={n}"
    "&vertragsart=ratenzahlung&tarif={t}"
)


def test_o2_ein_besuch_je_geraet_und_tarif():
    def satz(n, t):
        return {"id": f"buendel--o2--x--{t}--{n}m", "quelle_url": O2.format(n=n, t=t)}

    a, b = satz(24, "o2-mobile-s"), satz(36, "o2-mobile-s")
    assert wege.seite_von("o2", a) == wege.seite_von("o2", b)
    assert wege.seite_von("o2", a) != wege.seite_von("o2", satz(24, "o2-mobile-l"))


TK = (
    "https://www.telekom.de/shop/geraet/samsung/samsung-galaxy-s26-plus/black-256-gb"
    "?tariffId={t}&categoryId=smartphones{raten}"
)


def test_telekom_ein_besuch_je_geraet_und_tarif():
    def satz(t, raten=""):
        return {
            "id": f"buendel--telekom--x--{t}{raten}",
            "quelle_url": TK.format(t=t, raten=raten),
        }

    a = satz("MF_1")
    b = satz("MF_1", "&installmentValue=44&instalmentId=36")
    assert wege.seite_von("telekom", a) == wege.seite_von("telekom", b)
    assert wege.seite_von("telekom", a) != wege.seite_von("telekom", satz("MF_2"))


def test_vodafone_ein_besuch_je_speicher_und_raten():
    def satz(tarif, raten=24, sku="apple-iphone-duo-2048gb-nachthimmel"):
        return {
            "id": f"buendel--vodafone--{sku}--{tarif}--{raten}m",
            "sku_id": sku,
            "tarif_name": tarif,
            "laufzeit_monate": raten,
            "quelle_url": "https://www.vodafone.de/privat/handys/iphone-duo.html",
        }

    a = satz("Mobil S")
    assert wege.seite_von("vodafone", a) == wege.seite_von("vodafone", satz("Mobil L"))
    assert wege.seite_von("vodafone", a) != wege.seite_von("vodafone", satz("x", 12))
    farbe = satz("Mobil S", sku="apple-iphone-duo-2048gb-weiss")
    assert wege.seite_von("vodafone", a) == wege.seite_von("vodafone", farbe)


@pytest.mark.parametrize("schluessel", ["congstar", "saturn-mediamarkt-o2-netz"])
def test_ohne_eigene_gruppe_ein_besuch_je_buendel(schluessel):
    a = {"id": f"buendel--{schluessel}--a--t--24m", "quelle_url": "https://x/1"}
    b = {"id": f"buendel--{schluessel}--b--t--24m", "quelle_url": "https://x/1"}
    assert wege.seite_von(schluessel, a) != wege.seite_von(schluessel, b)


def test_farben_teilen_die_lesung_ihres_tarifs():
    gruppe = [_eins("1&1 All-Net-Flat S"), {**_eins("1&1 All-Net-Flat S"), "id": "b"}]
    assert [len(v) for v in nach_tarif(gruppe, str.strip).values()] == [2]


@pytest.mark.parametrize(
    ("text", "tarif", "rate"),
    [
        (
            "Google Pixel 11 Pro Fold\n74,–\xa0€/Mon.\n1&1 All-Net-Flat L\n24,99\xa0€\n"
            "18,99\xa0€/Mon.\n92\n,\n99\n€/Mon.\nMonatliche Gesamtkosten\nWeiter",
            "1&1 All-Net-Flat L",
            74.0,
        ),
        ("36 Monate Fix\n49\n,\n–\n€/Mon.", None, 49.0),
        (
            "Samsung Galaxy S26\n24,50 €/Mon.\n1&1 Unlimited XL\n",
            "1&1 Unlimited XL",
            24.5,
        ),
    ],
)
def test_preisleiste_der_tarifauswahl(text, tarif, rate):
    """Texte der Preisleiste und des Fix-Reiters vom 21.11.2026 (Pixel 11 Pro Fold)."""
    assert eins.leiste_tarif(text) == tarif
    assert eins.leiste_rate(text) == rate


SEITE = """<html><body>
<label><input type="radio" name="r" value="24" checked onclick="w(24)"> 24 Raten</label>
<label><input type="radio" name="r" value="36" onclick="w(36)"> 36 Raten</label>
<div id="preis">Dein Preis <span id="n">24</span> Raten
<span id="b">40,00 €</span></div>
<script>function w(n){document.getElementById('n').textContent=n;
document.getElementById('b').textContent=(n==24?'40,00 €':'30,00 €');}</script>
</body></html>"""


@pytest.fixture
def testweg(monkeypatch):
    """Ein Weg für eine lokale Seite: öffnet einmal, klickt je Bündel die Raten."""
    monkeypatch.setattr(gb, "NACH_LADEN_MS", 0)
    monkeypatch.setattr(gb, "NACH_KLICK_MS", 0)
    monkeypatch.setattr(gb, "RUHEFRIST_MS", 500)
    gesperrt_ab = {"n": None}

    def waehle(seite, gruppe, oeffnen):
        seite.route(
            "http://127.0.0.1:9/**",
            lambda route: route.fulfill(
                body=SEITE, content_type="text/html; charset=utf-8"
            ),
        )
        oeffnen(seite, "http://127.0.0.1:9/geraet")
        for b in gruppe:
            if b["laufzeit_monate"] == gesperrt_ab["n"]:
                raise gb.Gesperrt("Captcha")
            if b["laufzeit_monate"] == 12:
                yield b, gb.NichtPruefbar("Auswahl nicht gefunden: 12 Raten")
                continue
            n = b["laufzeit_monate"]
            gb.klicke(seite, seite.get_by_text(f"{n} Raten", exact=True), f"{n}")
            yield b, f"Gewählt {n}\n"

    weg = wege.Weg(waehle, (("Dein Preis", "Raten"),), ("Dein Preis", "Raten"))
    monkeypatch.setitem(wege.WEGE, "test", weg)
    return gesperrt_ab


def _satz(n):
    return {"id": f"buendel--test--g--t--{n}m", "laufzeit_monate": n}


def test_ein_besuch_liest_jedes_buendel_der_seite(chromium, testweg):
    geladen: list[str] = []
    ergebnis = dict(
        (b["id"], lesung)
        for b, lesung in wege.lies_gruppe(
            chromium, "test", [_satz(24), _satz(36), _satz(12)], None, geladen.append
        )
    )
    assert geladen == ["http://127.0.0.1:9/geraet"]
    assert "24 Raten 40,00 €" in ergebnis[_satz(24)["id"]].text
    assert "36 Raten 30,00 €" in ergebnis[_satz(36)["id"]].text
    assert ergebnis[_satz(36)["id"]].text.startswith("Gewählt 36")
    assert ergebnis[_satz(36)["id"]].bild[:4] == b"RIFF"
    assert str(ergebnis[_satz(12)["id"]]) == "Auswahl nicht gefunden: 12 Raten"


def test_abbruch_gilt_fuer_jedes_noch_offene_buendel(chromium, testweg):
    testweg["n"] = 36
    ergebnis = dict(
        (b["id"], lesung)
        for b, lesung in wege.lies_gruppe(
            chromium, "test", [_satz(24), _satz(36), _satz(48)], None
        )
    )
    assert not isinstance(ergebnis[_satz(24)["id"]], Exception)
    assert isinstance(ergebnis[_satz(36)["id"]], gb.Gesperrt)
    assert isinstance(ergebnis[_satz(48)["id"]], gb.Gesperrt)


def test_robots_verbot_vor_dem_laden_trifft_die_ganze_gruppe(chromium, testweg):
    def verbiete(url):
        raise gb.NichtPruefbar(f"{gp.GRUND_ROBOTS}: Disallow")

    gruppe = [_satz(24), _satz(36)]
    ergebnis = list(wege.lies_gruppe(chromium, "test", gruppe, None, verbiete))
    assert [str(f) for _, f in ergebnis] == [f"{gp.GRUND_ROBOTS}: Disallow"] * 2


def test_vorzeitiges_ende_schliesst_den_kontext(chromium, testweg):
    vorher = len(chromium.contexts)
    lesungen = wege.lies_gruppe(chromium, "test", [_satz(24), _satz(36)], None)
    next(lesungen)
    assert len(chromium.contexts) == vorher + 1
    lesungen.close()
    assert len(chromium.contexts) == vorher


def test_anbieter_ohne_weg_nennt_jedes_buendel(chromium):
    gruppe = [
        {"id": "buendel--fraenk--a--t--24m"},
        {"id": "buendel--fraenk--b--t--24m"},
    ]
    ergebnis = list(wege.lies_gruppe(chromium, "fraenk", gruppe, None))
    assert [str(f) for _, f in ergebnis] == [wege.GRUND_KEIN_WEG] * 2


class _Args:
    aufnehmen = None
    gemessen_um = None


def test_lauf_hoert_nach_der_frist_mitten_im_besuch_auf(monkeypatch):
    """Ist die Frist nach dem ersten Bündel um, endet der Besuch; der Rest bekommt im
    Lauf die Zeile „Zeitbudget“ (``laufe``), nie ein stilles Fehlen."""
    geschlossen = []

    def lies_gruppe(browser, schluessel, gruppe, kennung, vor_laden, aufnehmen):
        try:
            for b in gruppe:
                yield b, gb.NichtPruefbar("Auswahl nicht gefunden: 1 TB")
        finally:
            geschlossen.append(True)

    monkeypatch.setattr(SKRIPT, "lies_gruppe", lies_gruppe)
    saetze = {s["id"]: {**s, "anbieter": "o2"} for s in (_satz(24), _satz(36))}
    lauf = SKRIPT.Lauf(_Args(), None, saetze, "2026-11-21", {}, 0.0, None)
    lauf.besuche([(bid, gp.ANLASS_AENDERUNG) for bid in saetze])
    assert list(lauf.ergebnisse) == [_satz(24)["id"]] and geschlossen == [True]
