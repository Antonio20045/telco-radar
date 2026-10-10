"""Die Rechnung steht an der Bündelzeile: wie der Preis zustande kommt, ohne Klick.

Antonio, 07.10.2026: „Man sollte direkt erkennen, wie der Preis zustande kommt“ und
„keiner weiß, was du mit Schätzung meinst“. Jede belastbare Zeile zeigt deshalb im
zugeklappten Kopf ``24 × 69,49 € Monatspreis (54,50 € Gerät + 14,99 € Tarif) + … =
1.714,75 €``, den Monatspreis wie beim Anbieter (Antonio, 07.10.2026: Vodafone
nennt nur ihn); die
Schritte kommen aus ``kosten_ueber`` (``Kosten.rechnung``) und ergeben genau die
Kernzahl. Ein vom Anbieter nicht direkt genannter Preis sagt in einem Satz, wie er
berechnet ist, statt „Schätzung“. Gerendert wird der Bestand vom 2026-10-03.
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import json
import re
import threading

import pytest
from bestand_pfad import abbild
from bs4 import BeautifulSoup

from telco_radar.config import load_config
from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import geraete_view
from telco_radar.report.geraete_tco_grafik import euro
from telco_radar.report.html import render_site
from telco_radar.tarif_model import Preisphase
from telco_radar.tco_kosten import monatsschritte
from telco_radar.tco_model import Buendel, kosten_ueber


@contextlib.contextmanager
def _server(site):
    """Ein Server auf 127.0.0.1 für den gerenderten Ordner, kein ``file://``."""
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(site)
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()


def _buendel(**felder) -> Buendel:
    werte = {
        "anbieter": "o2",
        "sku_id": "apple-iphone-17-pro-256gb",
        "tarif_name": "O2 Mobile S",
        "tarif_monatlich": 14.99,
        "geraet_monatsrate": 54.5,
        "laufzeit_monate": 24,
        "geraet_zuzahlung": 7.0,
        "anschlusspreis": 39.99,
        "tarif_bindung_monate": 24,
    }
    werte.update(felder)
    return Buendel(**werte)


def _schritte(kosten) -> list[tuple]:
    return [(s.anzahl, s.betrag, s.art) for s in kosten.rechnung]


def test_rechnung_nennt_jeden_posten_mit_anzahl_und_preis():
    k = kosten_ueber(_buendel())
    assert _schritte(k) == [
        (24, 54.5, "geraet"),
        (24, 14.99, "tarif"),
        (None, 7.0, "anzahlung"),
        (None, 39.99, "anschluss"),
    ]
    assert k.gesamt == 1714.75
    assert round(sum(s.summe for s in k.rechnung), 2) == k.gesamt


def test_geraet_und_tarif_gleich_lang_sind_ein_monatspreis():
    """Vodafone zeigt 81,45 € im Monat, nicht 49,50 € und 31,95 € getrennt."""
    k = kosten_ueber(
        _buendel(anbieter="Vodafone", tarif_monatlich=31.95, geraet_monatsrate=49.5)
    )
    schritte = monatsschritte(k.rechnung)
    assert [(s.art, s.anzahl, s.betrag) for s in schritte] == [
        ("monat", 24, 81.45),
        ("anzahlung", None, 7.0),
        ("anschluss", None, 39.99),
    ]
    assert [(t.art, t.betrag) for t in schritte[0].teile] == [
        ("geraet", 49.5),
        ("tarif", 31.95),
    ]
    assert round(sum(s.summe for s in schritte), 2) == k.gesamt


def test_ungleich_lange_raten_bleiben_getrennt():
    """12 Raten, Tarif 24 Monate: ein gemeinsamer Monatspreis wäre falsch."""
    k = kosten_ueber(_buendel(laufzeit_monate=12, geraet_monatsrate=99.0))
    assert [s.art for s in monatsschritte(k.rechnung)] == [
        "geraet",
        "tarif",
        "anzahlung",
        "anschluss",
    ]


def test_rechnung_teilt_den_tarif_nach_preisphasen():
    """Phasen bis Monat 24 teilen den Tarif; ein Preis ab Monat 25 zählt bei 36
    Raten nicht mit (Antonio, 10.10.2026)."""
    phasen = [
        Preisphase(1, 12, 9.99),
        Preisphase(13, 24, 14.99),
        Preisphase(25, None, 19.99),
    ]
    k = kosten_ueber(_buendel(laufzeit_monate=36, tarif_phasen=phasen))
    tarif = [(s.anzahl, s.betrag) for s in k.rechnung if s.art == "tarif"]
    assert tarif == [(12, 9.99), (12, 14.99)]
    assert round(sum(s.summe for s in k.rechnung), 2) == k.gesamt


def test_rechnung_eines_vertrags_mit_einem_monatsbetrag():
    b = _buendel(
        anbieter="1&1",
        buendel_monatlich=61.99,
        laufzeit_monate=36,
        tarif_monatlich=None,
        geraet_monatsrate=None,
        geraet_zuzahlung=0.0,
        tarif_bindung_monate=24,
    )
    k = kosten_ueber(b)
    assert (24, 61.99, "vertrag") in _schritte(k)
    assert k.gesamt == round(24 * 61.99 + 39.99, 2)
    assert round(sum(s.summe for s in k.rechnung), 2) == k.gesamt


def test_nullbetraege_stehen_nicht_in_der_rechnung():
    k = kosten_ueber(_buendel(anschlusspreis=0.0))
    assert [s.art for s in k.rechnung] == ["geraet", "tarif", "anzahlung"]


def test_ohne_gesamtpreis_nur_die_gemessenen_posten():
    """Gegenprobe: fehlt ein Posten, gibt es keine Kernzahl; die Rechnung nennt
    nur, was gemessen ist, die Lücke steht in `luecken`."""
    k = kosten_ueber(_buendel(geraet_monatsrate=None))
    assert k.gesamt is None
    assert [s.art for s in k.rechnung] == ["tarif", "anzahlung", "anschluss"]
    assert k.luecken == ["Geräterate"]


def test_36_raten_sind_24_monatspreise_und_12_monate_nur_geraet():
    """Antonio, 10.10.2026: Monat 1 bis 24 Tarif und Rate, Monat 25 bis 36 nur die
    Rate. 24 × 69,49 € + 12 × 54,50 € + 7,00 € + 39,99 € = 2.368,75 €."""
    k = kosten_ueber(_buendel(laufzeit_monate=36))
    assert k.gesamt == 2368.75 and k.luecken == []
    schritte = monatsschritte(k.rechnung)
    assert [(s.art, s.anzahl, s.betrag) for s in schritte] == [
        ("monat", 24, 69.49),
        ("nur_geraet", 12, 54.5),
        ("anzahlung", None, 7.0),
        ("anschluss", None, 39.99),
    ]
    assert [(t.art, t.anzahl, t.betrag) for t in schritte[0].teile] == [
        ("geraet", 24, 54.5),
        ("tarif", 24, 14.99),
    ]
    assert round(sum(s.summe for s in schritte), 2) == k.gesamt


@pytest.mark.parametrize(
    "phasen,tarif_summe",
    [
        ([Preisphase(1, 12, 10.0), Preisphase(25, None, 30.0)], 480.0),
        ([Preisphase(25, None, 30.0)], 240.0),
    ],
)
def test_referenzrechnung_ergibt_ihre_tarifsumme(phasen, tarif_summe):
    """Die Summanden der Referenz ergeben genau ihre Tarifsumme, auch wenn die
    Phasen Monate offen lassen."""
    from telco_radar.report.geraete_rechnung import referenz

    ref = {
        "tarif_monate": 24,
        "monatlich": 10.0,
        "geraet_betrag": 1000.0,
        "tarif_summe": tarif_summe,
        "phasen": phasen,
    }
    schritte = referenz(ref)
    summe = sum(s["betrag"] * (s["anzahl"] or 1) for s in schritte)
    assert round(summe, 2) == 1000.0 + tarif_summe


@pytest.fixture(scope="module")
def bestand(tmp_path_factory):
    wurzel = tmp_path_factory.mktemp("rechnung-zeile")
    berichte = abbild(wurzel)
    site = wurzel / "site"
    render_site(site, berichte, load_config(wurzel))
    juengste = sorted(berichte.glob("*.json"))[-1]
    heute = json.loads(juengste.read_text(encoding="utf-8"))["date"]
    tco = geraete_view.aufbereiten(
        wurzel / "data" / "state",
        lade_quellen(wurzel),
        lade_katalog(wurzel),
        heute=heute,
    )["tco"]
    karten = [
        k for m in tco["modelle"] for k in [*m["zeilen_band"], *m["zeilen_ohne_band"]]
    ]
    seiten = "".join(
        (site / p).read_text(encoding="utf-8")
        for p in ("geraete.html", "data/geraete-buendel.html")
    )
    return site, karten, BeautifulSoup(seiten, "html.parser")


def _text(knoten) -> str:
    return re.sub(r"\s+", " ", knoten.get_text(" ", strip=True))


def test_jede_belastbare_zeile_zeigt_ihre_rechnung_im_kopf(bestand):
    _, karten, soup = bestand
    zeilen = soup.select("details.gr-bnd > summary")
    belastbar = [k for k in karten if k["belastbar"]]
    assert len(belastbar) > 20, "Bestand ohne belastbare Zeilen – der Test prüft nichts"
    rechnungen = [z.select_one(".gr-bnd-rechnung") for z in zeilen]
    mit = [_text(r) for r in rechnungen if r is not None and "=" in _text(r)]
    assert len(mit) == len(belastbar), (
        f"{len(mit)} Zeilen mit Summe, {len(belastbar)} belastbare Karten"
    )
    falsch = [t for t in mit if not re.search(r"= [\d.]+,\d\d €$", t)]
    assert not falsch, f"Rechnung ohne Summe am Ende: {falsch[:3]}"
    summen = sorted(t.rsplit("= ", 1)[1] for t in mit)
    assert summen == sorted(euro(k["gesamt"]) for k in belastbar)


def test_o2_zeile_rechnet_wie_die_karte(bestand):
    """Die Zahlen der Rechnung sind die Felder der Karte, die Summe ihre Kernzahl."""
    _, karten, soup = bestand
    o2 = [
        k
        for k in karten
        if k["anbieter"] == "o2"
        and k["belastbar"]
        and k["rate"] is not None
        and k["raten_laufzeit"] == 24
    ]
    assert o2, "Bestand ohne o2-Zeile mit 24 Raten"
    texte = {
        _text(r).replace("( ", "(").replace(" )", ")")
        for r in soup.select(".gr-bnd-rechnung")
    }
    k = o2[0]
    assert k["leitzahl_monate"] == 24
    erwartet = (
        f"24 × {euro(round(k['rate'] + k['monatlich'], 2))} Monatspreis "
        f"({euro(k['rate'])} Gerät + {euro(k['monatlich'])} Tarif) + "
        f"{euro(k['zuzahlung'])} Anzahlung"
    )
    treffer = [
        t
        for t in texte
        if t.startswith(erwartet) and t.endswith(f"= {euro(k['gesamt'])}")
    ]
    assert treffer, f"keine Rechnung für {k['tarif']}: erwartet „{erwartet}…“"


def test_zeile_ohne_kernzahl_nennt_was_fehlt(bestand):
    """Eine Zeile ohne belastbare Zahl zeigt die gemessenen Posten und benennt
    den fehlenden, ohne Summe."""
    _, karten, soup = bestand
    offen = [
        k
        for k in karten
        if not k["belastbar"] and k.get("sku_id") and k.get("rechnung")
    ]
    assert offen, "Bestand ohne Zeile mit Lücke – der Test prüft nichts"
    texte = [_text(r) for r in soup.select(".gr-bnd-rechnung") if "=" not in _text(r)]
    assert texte and all("nicht genannt" in t for t in texte), texte[:3]
    assert any("Ablöse nach Monat 24 nicht genannt" in t for t in texte), texte[:3]
    assert not any("Monat 25–36" in t for t in texte), texte[:3]


def test_kein_wort_schaetzung_auf_der_geraeteseite(bestand):
    site, karten, soup = bestand
    assert any(k.get("schaetzung") for k in karten), "Bestand ohne berechnete Preise"
    assert "Schätzung" not in soup.get_text()
    assert "Schätzung" not in (site / "geraete.html").read_text(encoding="utf-8")


def test_berechneter_preis_sagt_wie(bestand):
    _, karten, soup = bestand
    saetze = [_text(s) for s in soup.select("summary .gr-bnd-herleitung")]
    o2 = [s for s in saetze if s.startswith("o2 nennt den Tarifpreis")]
    assert o2, f"kein Herleitungssatz für o2: {saetze[:3]}"
    berechnet = sum(1 for k in karten if k.get("schaetzung"))
    assert len(saetze) == berechnet
    gemessen = [
        z
        for z in soup.select("details.gr-bnd > summary")
        if z.select_one(".gr-bnd-herleitung") is None
    ]
    assert gemessen, "Gegenprobe: gemessene Zeilen tragen keinen Herleitungssatz"


@pytest.mark.parametrize("breite,hoehe", [(1440, 900), (390, 844)])
def test_rechnung_ist_zugeklappt_sichtbar_ohne_querscroll(
    bestand, chromium, breite, hoehe
):
    site, _, _ = bestand
    with _server(site) as basis:
        seite = chromium.new_page(viewport={"width": breite, "height": hoehe})
        try:
            seite.goto(f"{basis}/geraete.html")
            seite.wait_for_selector("details.gr-bnd .gr-bnd-rechnung", state="attached")
            seite.click(".gx-bnd-auf")
            mass = seite.evaluate(
                """() => {
                  const r = [...document.querySelectorAll(
                    'details.gr-bnd:not([open]) .gr-bnd-rechnung')]
                    .filter(e => e.closest('details').offsetParent !== null);
                  return {
                    n: r.length,
                    unsichtbar: r.filter(e => getComputedStyle(e).display === 'none'
                      || e.getBoundingClientRect().height < 8).length,
                    ueberlauf: r.filter(e => e.scrollWidth > e.clientWidth + 1).length,
                    quer: document.documentElement.scrollWidth > innerWidth + 1,
                  };
                }"""
            )
        finally:
            seite.close()
    assert mass["n"] > 0, "keine sichtbare Zeile mit Rechnung"
    assert mass["unsichtbar"] == 0
    assert mass["ueberlauf"] == 0
    assert not mass["quer"]


def test_tafel_sagt_einmal_ohne_versandkosten(bestand):
    """Versand rechnet bei keinem Anbieter mit; die Tafel sagt es einmal."""
    site, _, _ = bestand
    seite = BeautifulSoup(
        (site / "geraete.html").read_text(encoding="utf-8"), "html.parser"
    )
    vermerke = [_text(v) for v in seite.select(".gr-bnd-versand")]
    assert vermerke == ["ohne Versandkosten"]
