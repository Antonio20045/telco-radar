"""O2 (STRATEGIE_GERAETE_OPTIK §3, 11.09.2026): Entrümpelung der
Vergleichsansicht - die Bündel-Karten werden Tabellenzeilen.

Die Abnahmekriterien des O2-Auftrags, hier als statische Messung:
  A2  <details> gesamt im Hauptpfad deutlich unter 100 - Rechenweg-
      Aufklapper je Zeile, "Wie gerechnet?", wenige.
  A6  KEIN DATENVERLUST: jede Information, die vorher auf den Karten stand
      (Rechenweg, Pflichtzeile "nach 24 Monaten gezahlt", Zustand
      "erneuert", Beleglinks, Abrufdatum), steht danach in der Zeile oder
      ihrem Rechenweg-Aufklapper. Der Test zählt die Karten der Aufbereitung
      gegen die Zeilen des gerenderten HTML - vorher (Daten) gegen nachher
      (Seite).

Dazu die Streichungen des Auftrags: keine "Beschaffung läuft"-
Platzhalterkarten (die Legendenzeile aus O1 trägt die Information), keine
Kartenklappe, keine "Alle Bündel als Tabelle" (beide verschmelzen mit der
Zeilen-Tabelle), keine Alarmtabelle und kein "Bei Wettbewerbern gelistet"
auf der Geräteseite (beide stehen auf wettbewerbsradar.html - dort hält
sie `tests/test_wettbewerbsradar_alarme.py` fest).
"""

from __future__ import annotations

import json
import math
import pathlib

import yaml
from bs4 import BeautifulSoup

from tarifleiter_testbestand import mit_leiter
from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import geraete_view
from telco_radar.report.html import render_site
from test_geraete_tco_zustand import HEUTE, _baue, lager, vorlage_text


def _zr_fragment(tmp_path: pathlib.Path) -> list:
    """Die Zeitreihen-Lager des gerenderten Fragments - _baue_ohne_band
    rendert nach <tmp>/ohne_band/site, das Fragment liegt daneben."""
    fragment = tmp_path / "ohne_band" / "site" / "data" / "geraete-zeitreihe.html"
    assert fragment.exists(), "Zeitreihen-Fragment fehlt"
    return BeautifulSoup(fragment.read_text(encoding="utf-8"), "html.parser").select(
        ".gr-zr-lager"
    )


def _lager_ohne_band(tmp_path: pathlib.Path):
    """Die Bündelzeilen des Startmodells aus dem Fragment, das
    `_baue_ohne_band` neben die Seite schreibt (`#gr-bnd-vorgabe`)."""
    pfad = tmp_path / "ohne_band" / "site" / "data" / "geraete-buendel.html"
    assert pfad.exists(), "Bündel-Fragment fehlt"
    vorgabe = BeautifulSoup(pfad.read_text(encoding="utf-8"), "html.parser").select_one(
        "#gr-bnd-vorgabe"
    )
    assert vorgabe is not None, "das Fragment trägt kein Startmodell"
    return vorgabe


WURZEL = pathlib.Path(__file__).resolve().parents[1]


_KATALOG = {
    "geraete": [
        {
            "hersteller": "Apple",
            "modell": "iPhone 17 Pro",
            "generation": 17,
            "marktstart": "2025-09-19",
            "speicher": [256],
            "segment": "premium",
        }
    ]
}
_FARBEN = {"farben": {"schwarz": ["Schwarz"]}}
_QUELLEN = {
    "anbieter": [
        {
            "name": "o2",
            "typ": "netzbetreiber",
            "rang": 2,
            "methode": "ldjson",
            "basis_url": "https://www.o2online.de",
            "einstiege": [{"url": "https://www.o2online.de/handys"}],
        },
        {
            "name": "Vodafone",
            "typ": "netzbetreiber",
            "rang": 1,
            "eigen": True,
            "methode": "ldjson",
            "basis_url": "https://www.vodafone.de",
            "einstiege": [{"url": "https://www.vodafone.de/handys"}],
        },
        {
            "name": "Saturn",
            "typ": "handel",
            "gruppe": "Ceconomy",
            "rang": 2,
            "methode": "saturn_brand",
            "aktiv": True,
            "basis_url": "https://www.saturn.de",
            "einstiege": [{"url": "https://www.saturn.de/handys"}],
        },
    ]
}

SKU = "apple-iphone-17-pro-256gb-schwarz"


def _listung(anbieter, preis):
    return {
        "id": f"{anbieter.lower()}--{SKU}",
        "sku_id": SKU,
        "device_id": "apple-iphone-17-pro",
        "anbieter": anbieter,
        "anbieter_typ": ("handel" if anbieter == "Saturn" else "netzbetreiber"),
        "speicher_gb": 256,
        "farbe_roh": "Schwarz",
        "farbe_normalisiert": "schwarz",
        "zustand": "neu",
        "first_seen": "2026-08-20",
        "last_verified": HEUTE,
        "status": "aktiv",
        "missed_checks": 0,
        "preis_ohne_vertrag": preis,
        "erstpreis": preis,
        "erstpreis_art": "ohne_vertrag",
        "erstpreis_am": "2026-08-20",
        "quelle_url": f"https://example.de/{anbieter.lower()}/{SKU}",
        "abgerufen_am": HEUTE,
        "verfuegbarkeit": "lieferbar",
        "confidence": "hoch",
        "einstiege": ["https://example.de/liste"],
    }


def _buendel(
    anbieter,
    tarif_id,
    tarif_name,
    gb,
    *,
    tarif=24.99,
    rate=20.0,
    laufzeit=24,
    zuzahlung=1.0,
):
    return {
        "id": f"buendel--{anbieter.lower()}--{tarif_id}",
        "sku_id": SKU,
        "anbieter": anbieter,
        "tarif_name": tarif_name,
        "tarif_id": tarif_id,
        "tarif_id_guete": "hoch",
        "tarif_monatlich": tarif,
        "geraet_zuzahlung": zuzahlung,
        "geraet_monatsrate": rate,
        "laufzeit_monate": laufzeit,
        "anschlusspreis": 0.0,
        "zustand": "neu",
        "rabatte": [],
        "quelle_url": f"https://example.de/{anbieter.lower()}/{SKU}",
        "abgerufen_am": HEUTE,
        "first_seen": HEUTE,
        "last_verified": HEUTE,
    }


def _tarif(anbieter, tarif_id, tarif_name, gb):
    return {
        "anbieter": anbieter,
        "name": tarif_name,
        "tarif_id": tarif_id,
        "art": "mobilfunk",
        "grundgebuehr": 24.99,
        "laufzeit_monate": 24,
        "datenvolumen_gb": gb,
        "preisphasen": [{"von_monat": 1, "bis_monat": None, "betrag": 24.99}],
        "dokument_url": f"https://example.de/pib/{tarif_id}",
        "abgerufen_am": HEUTE,
        "confidence": {},
        "fundstellen": {},
    }


def _baue_ohne_band(tmp_path: pathlib.Path) -> BeautifulSoup:
    """Ein Modell in drei Lagern: Band XS (o2 + Vodafone), unbegrenzt
    (o2, ohne Band), kein Tarifbestand (1&1, ohne Band) - dazu Saturn mit
    und Amazon/Expert ohne Händlerpreis."""
    import math

    root = tmp_path / "ohne_band"
    (root / "config").mkdir(parents=True)
    for name, daten in (
        ("geraete_katalog.yaml", _KATALOG),
        ("farben.yaml", _FARBEN),
        ("geraete_quellen.yaml", _QUELLEN),
    ):
        (root / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
    state = root / "data" / "state"
    state.mkdir(parents=True)
    listungen = [
        _listung("o2", 1099.0),
        _listung("Vodafone", 1199.90),
        _listung("Saturn", 1179.0),
    ]
    (state / "geraete_db.json").write_text(
        json.dumps(
            {
                "updated": HEUTE,
                "anbieter": {
                    n: {"laeufe": 4, "funde_gesamt": 1}
                    for n in ("o2", "Vodafone", "Saturn")
                },
                "listungen": listungen,
            }
        ),
        encoding="utf-8",
    )
    (state / "geraete_preise.jsonl").write_text("", encoding="utf-8")
    buendel = [
        _buendel("o2", "o2:klein", "O2 Mobile Klein", 10),
        _buendel("Vodafone", "vf:klein", "Vodafone Mobil XS", 18, rate=26.0),
        _buendel("o2", "o2:unlimited", "O2 Unlimited", math.inf),
        {
            **_buendel("1&1", "", "1&1 All-Net-Flat S", None),
            "tarif_monatlich": None,
            "geraet_monatsrate": None,
            "buendel_monatlich": 44.99,
            "geraet_zuzahlung": 1.0,
            "laufzeit_monate": 36,
        },
    ]
    for b in buendel:
        if b["tarif_id"] == "":
            b.pop("tarif_id")
    (state / "geraete_tco.json").write_text(
        json.dumps({"updated": HEUTE, "buendel": buendel, "sim_only": []}),
        encoding="utf-8",
    )
    tarife = [
        _tarif("o2", "o2:klein", "O2 Mobile Klein", 10),
        _tarif("Vodafone", "vf:klein", "Vodafone Mobil XS", 18),
        _tarif("o2", "o2:unlimited", "O2 Unlimited", math.inf),
    ]
    tarife = mit_leiter(tarife)
    (state / "tarife.jsonl").write_text(
        "\n".join(json.dumps(t) for t in tarife) + "\n", encoding="utf-8"
    )
    reports = root / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / f"{HEUTE}.json").write_text(
        json.dumps(
            {
                "date": HEUTE,
                "language": "de",
                "briefing_md": "## Auf einen Blick\n\n- Nichts Besonderes.\n",
                "stats": {},
                "regions": [],
            }
        ),
        encoding="utf-8",
    )
    (reports / f"{HEUTE}.md").write_text("# Bericht\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    return BeautifulSoup(
        (site / "geraete.html").read_text(encoding="utf-8"), "html.parser"
    )


def _text(el) -> str:
    return " ".join(el.get_text(" ", strip=True).split())


def test_je_buendel_eine_zeile_mit_vier_kernangaben_und_aufklapper(tmp_path):
    """Jedes Bündel des Vorgabemodells ist EINE Zeile: Anbieter, Tarif mit
    Volumen, Kosten über 24 Monate, Δ zur Vodafone-Referenz, Gerät ohne
    Vertrag - und je Zeile EIN schmaler Rechenweg-Aufklapper (Entwurf
    `.bnd`). Das Etikett der Leitzahl heisst seit A1 "Kosten über
    24 Monate" (vorher "TCO-24").

    Seit 10.10.2026 steht die Bündelliste nicht mehr auf der Seite; geprüft
    wird das Fragment."""
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    assert not tafel.select(".gr-bnd"), "Bündelzeilen stehen noch auf der Seite"
    zeilen = lager(tmp_path).select("#gr-bndliste .gr-bnd")
    assert len(zeilen) == 3, "o2 neu, o2 erneuert und die Referenz"
    for z in zeilen:
        summary = z.select_one("summary")
        assert summary is not None, "Zeile ohne summary"
        an = summary.select_one(".gr-bnd-an")
        tarif = summary.select_one(".gr-bnd-tarif")
        tco = summary.select_one(".gr-bnd-tco")
        delta = summary.select_one(".gr-bnd-delta")
        bar = summary.select_one(".gr-bnd-bar")
        for zelle, name in (
            (an, "Anbieter"),
            (tarif, "Tarif"),
            (tco, "Kosten über 24 Monate"),
            (delta, "Δ"),
            (bar, "Gerät"),
        ):
            assert zelle is not None, f"Zeile ohne {name}-Zelle"
        assert "€" in tco.get_text(), "TCO-Zelle ohne Zahl"
        assert "Kosten über 24 Monate" in tco.get_text(), (
            "TCO-Zelle ohne Leitzahl-Etikett"
        )
        assert z.select_one(".gr-bnd-rw") is not None, (
            "Zeile ohne Rechenweg-Montageziel"
        )
        assert z.select_one("template.gr-bnd-rw-vorlage .gr-tposten li") is not None, (
            "Zeile ohne Rechenweg im Vorlagen-Pool"
        )


def test_die_zeilen_stehen_nach_gesamtkosten_sortiert(tmp_path):
    """Der Entwurf sortiert die Bandliste aufsteigend nach TCO-24 - die
    günstigste Zeile zuerst (kein Sortier-Control, §4 Entscheidung 3).

    Seit 10.10.2026 steht die Bündelliste nicht mehr auf der Seite; geprüft
    wird das Fragment."""
    _baue(tmp_path)
    werte = []
    for z in lager(tmp_path).select("#gr-bndliste .gr-bnd"):
        roh = z.get("data-gesamt")
        werte.append(float(roh) if roh else None)
    assert werte, "keine Zeile in der Bandliste - der Test misst nichts"
    assert werte == sorted(werte), werte


def test_keine_karten_und_keine_kartenklappe_mehr(tmp_path):
    """Auftrag 1: Kartenklappe und "Alle Bündel als Tabelle" verschmelzen
    mit der Zeilen-Tabelle - keins der drei alten Gebilde bleibt."""
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    assert tafel.select_one("details.gr-karten-auf") is None, (
        "die Kartenklappe steht noch"
    )
    assert tafel.select_one(".gr-kkarte") is None, "Karten stehen noch"
    assert tafel.select_one(".gr-ksteuer") is None, (
        "Sortierung/Filter der Klappe stehen noch"
    )
    assert tafel.select_one("#gr-tco-tabelle") is None, (
        "'Alle Bündel als Tabelle' steht noch als eigene Tabelle"
    )
    assert tafel.select_one("table.gr-ttab--leit") is None


def _vorgabe_daten(root: pathlib.Path) -> dict:
    geraete = geraete_view.aufbereiten(
        root / "data" / "state", lade_quellen(root), lade_katalog(root), heute=HEUTE
    )
    tco = geraete["tco"]
    modell = next(m for m in tco["modelle"] if m["id"] == tco["modell_vorgabe"])
    return modell


def test_jede_karte_der_aufbereitung_ist_eine_zeile(tmp_path):
    """A6, der Zähltest: die Karten des Vorgabemodells aus der Aufbereitung
    (vorher) und die Zeilen des gerenderten HTML (nachher) sind dieselbe
    Menge - je (Anbieter, Tarif, Gesamt) genau eine Zeile.

    Seit 10.10.2026 steht die Bündelliste nicht mehr auf der Seite; geprüft
    wird das Fragment."""
    _baue(tmp_path)
    modell = _vorgabe_daten(tmp_path / "mit")
    karten = [k for k in modell["karten"] if k["belastbar"]]
    assert len(karten) == 3
    vorgabe = lager(tmp_path)
    assert vorgabe["data-modell"] == modell["id"]
    zeilen = vorgabe.select(".gr-bnd")
    assert len(zeilen) == len(karten), (
        f"{len(karten)} Karten stehen {len(zeilen)} Zeilen gegenüber"
    )
    gesehen = set()
    for k in karten:
        treffer = [
            z
            for z in zeilen
            if z.get("data-anbieter") == k["anbieter"]
            and _text(z.select_one(".gr-bnd-tco")).startswith(_euro(k["gesamt"]))
        ]
        assert len(treffer) == 1, f"{k['anbieter']} {k['tarif']}: {len(treffer)} Zeilen"
        gesehen.add(id(treffer[0]))
    assert len(gesehen) == len(karten), "Zeilen wurden doppelt getroffen"


def _euro(betrag: float) -> str:
    """Dieselbe deutsche Euro-Schreibweise wie der `euro`-Filter der Seite."""
    text = f"{betrag:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")
    return text


def test_jede_zeile_traegt_rechenweg_pflichtzeile_und_belege(tmp_path):
    """A6: Der Rechenweg-Aufklapper einer Zeile trägt, was die Karte trug -
    die Postenliste, den Zeitraum der Zahl, den vollen Delta-Satz mit
    Referenz-Tarif, Beleglink UND Abrufdatum.

    Die Pflichtzeile aus A5.2 ("nach 24 Monaten gezahlt … noch offen") ist mit
    Datenkonzept Geräte Schritt 2 gefallen: die Zahl rechnet alle Raten und
    den Tarif über H Monate, offen bleibt nichts. An ihrer Stelle steht der
    Zeitraum ("Gerechnet über H Monate") - dieselbe Zahl wie das Etikett.

    Seit 10.10.2026 steht die Bündelliste nicht mehr auf der Seite; geprüft
    wird das Fragment."""
    _baue(tmp_path)
    zeilen = lager(tmp_path).select(".gr-bnd")
    assert zeilen
    for z in zeilen:
        rw = z.select_one("template.gr-bnd-rw-vorlage")
        assert rw is not None
        posten = rw.select(".gr-tposten li")
        assert posten, f"{z.get('data-anbieter')}: Rechenweg ohne Posten"
        monate = z.get("data-leitzahl-monate")
        assert monate and f"Gerechnet über {monate} Monate" in vorlage_text(rw), (
            f"{z.get('data-anbieter')}: der Zeitraum der Zahl fehlt im Rechenweg"
        )
        assert "noch offen" not in vorlage_text(rw)
        assert rw.select_one("a[href]") is not None, (
            f"{z.get('data-anbieter')}: kein Beleglink im Rechenweg"
        )
        assert "abgerufen" in _text(rw), (
            f"{z.get('data-anbieter')}: kein Abrufdatum im Rechenweg"
        )


def test_der_zustand_steht_auf_der_zeile(tmp_path):
    """A6: 'erneuert' ist eine Preisdimension - das Etikett steht im
    Anbieter-Feld der Zeile (nicht erst im Rechenweg).

    Seit 10.10.2026 steht die Bündelliste nicht mehr auf der Seite; geprüft
    wird das Fragment."""
    _baue(tmp_path)
    tafel = lager(tmp_path)
    erneuert = tafel.select_one('.gr-bnd[data-zustand="refurbished"]')
    assert erneuert is not None
    assert _text(erneuert.select_one(".gr-bnd-an")).endswith("erneuert")
    assert erneuert.select_one(".gr-kk-marke--zustand") is not None
    neu = tafel.select_one('.gr-bnd[data-anbieter="o2"][data-zustand="neu"]')
    assert neu is not None
    assert neu.select_one(".gr-kk-marke--zustand") is None


def test_die_referenz_nennt_ihre_naehrung_im_rechenweg(tmp_path):
    """F1 Stufe 1 bleibt: die Referenzzeile heißt 'Referenzrechnung' und
    sagt im Rechenweg, dass der eigene Bündelpreis nicht erhoben ist.

    Seit 10.10.2026 steht die Bündelliste nicht mehr auf der Seite; geprüft
    wird das Fragment."""
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    ref = lager(tmp_path).select_one('.gr-bnd[data-anbieter="Vodafone"]')
    assert ref is not None
    assert "Referenzrechnung" in _text(ref.select_one(".gr-bnd-an"))
    rw = vorlage_text(ref.select_one("template.gr-bnd-rw-vorlage"))
    assert "noch nicht erhoben" in rw
    assert "weist zu diesem Gerät keinen Bündelpreis aus" not in tafel.get_text(" ")
    assert "weist zu diesem Gerät keinen Bündelpreis aus" not in rw


def test_beschaffung_laeuft_steht_nicht_mehr_in_der_leseflaeche(tmp_path):
    """E2 (§3.1 + Antonio 9b.7): die 'Beschaffung läuft'-Legende der
    Balkenform ist gefallen - ein Händler ohne Preis ist kein Bündel-
    Anbieter und steht nicht einzeln da. Die Auskunft lebt auf
    geraete-quellen.html; der Katalog zeigt die Listungen."""
    s = _baue_ohne_band(tmp_path)
    kopie = BeautifulSoup(str(s), "html.parser")
    for k in kopie.select("script"):
        k.decompose()
    text = kopie.get_text(" ")
    assert "Beschaffung läuft" not in text
    for name in ("Amazon", "Expert"):
        assert name not in text, f"{name} steht einzeln in der Lesefläche"


def test_keine_leeren_platzhalterkarten_mehr(tmp_path):
    """Leerkarten ('Für dieses Modell ist bei Telekom noch kein Bündelpreis
    erhoben …') fallen - die Legende nennt dieselben Anbieter je Band."""
    s = _baue_ohne_band(tmp_path)
    tafel = s.select_one("#tafel-tco")
    assert not tafel.select(".gr-kkarte--leer")
    assert "noch kein Bündelpreis erhoben" not in tafel.get_text(" ")
    fehlend = tafel.select(".gr-anb-fehlt")
    assert fehlend, "die fehlenden Anbieter stehen nicht als Zeilen da"
    je_ansicht = [
        (z["data-band"], z["data-fehlt-lz"], z["data-anbieter"]) for z in fehlend
    ]
    assert len(je_ansicht) == len(set(je_ansicht)), je_ansicht


def test_fehlende_anbieter_stehen_je_band_und_ansicht_in_der_liste(tmp_path):
    """Antonio 10.10.2026: jeder große Anbieter steht in der Bündelliste, auch
    ohne Bündel. Je Band und Ansicht (12, 24, 36, alle) genau einmal, und nur
    die fünf Bündelanbieter - kein Händler."""
    s = _baue_ohne_band(tmp_path)
    zeilen = s.select("#gr-bnd-gruppe .gr-anb-fehlt")
    assert zeilen, "keine Zeile eines fehlenden Anbieters"
    for z in zeilen:
        assert z["data-fehlt-lz"] in ("12", "24", "36", "alle"), z
        assert z["data-anbieter"] in ("Telekom", "Vodafone", "o2", "1&1", "congstar")
        assert _text(z.select_one(".gr-anb-fehlt-zustand")), z
    ansichten = {z["data-fehlt-lz"] for z in zeilen}
    assert {"24", "alle"} <= ansichten, ansichten


def test_ohne_tarifband_ist_eigene_gruppe_unter_der_bandliste(tmp_path):
    """Unbegrenzte Tarife und Tarife ohne erhobenes Volumen stehen in
    einer klar getrennten Gruppe UNTER der Band-Tabelle - als Zeilen
    derselben Form, nicht heimlich in einem Band.

    Seit 10.10.2026 steht die Bündelliste nicht mehr auf der Seite; geprüft
    wird das Fragment."""
    s = _baue_ohne_band(tmp_path)
    assert s.select_one("#tafel-tco #gr-ohneband") is None
    tafel = _lager_ohne_band(tmp_path)
    gruppe = tafel.select_one("#gr-ohneband")
    assert gruppe is not None, "die Gruppe 'Ohne Tarifband' fehlt"
    ohueberschrift = _text(gruppe.find(["h3", "h4"]))
    assert "Ohne Tarifband" in ohueberschrift
    zeilen = gruppe.select(".gr-bnd")
    assert len(zeilen) == 2, "o2 Unlimited und 1&1 stehen ohne Band"
    tarife = [_text(z.select_one(".gr-bnd-tarif")) for z in zeilen]
    assert any("unbegrenzt" in t for t in tarife), tarife
    assert all(z.get("data-band") is None for z in zeilen)
    reihenfolge = [
        el.get("id") or "gr-bndliste"
        for el in tafel.select("#gr-bndliste, #gr-ohneband")
    ]
    assert reihenfolge == ["gr-bndliste", "gr-ohneband"], reihenfolge


def test_haendler_barpreise_stehen_kompakt_mit_beleg(tmp_path):
    """Händler ohne Tarifbündel: Saturns Barpreis als kompakte Zeile MIT
    Beleg und Abrufdatum (was die Händlerkarte trug) - Amazon und Expert
    ohne Preis stehen NICHT als leere Karten, die Legende nennt sie.

    Seit 10.10.2026 steht die Bündelliste nicht mehr auf der Seite; geprüft
    wird das Fragment."""
    s = _baue_ohne_band(tmp_path)
    gruppe = _lager_ohne_band(tmp_path).select_one("#gr-ohneband")
    zeilen = gruppe.select(".gr-haendlerzeile")
    assert len(zeilen) == 1, "nur Saturn hat einen Preis"
    saturn = _text(zeilen[0])
    assert "Saturn" in saturn and "1.179,00 €" in saturn
    assert "ohne Vertrag" in saturn
    assert zeilen[0].select_one("a[href]") is not None, "ohne Beleglink"
    assert "abgerufen" in saturn
    assert "Amazon" not in _text(gruppe)
    assert "Expert" not in _text(gruppe)
    tafel_text = _text(s.select_one("#tafel-tco"))
    assert "Amazon" not in tafel_text and "Expert" not in tafel_text


def test_die_bandliste_traegt_ihr_band_als_attribut(tmp_path):
    """app.js versteckt Zeilen anderer Bänder - das Band steht als
    data-band AN der Zeile (kein zweiter Gruppierungspfad im DOM).

    Seit 10.10.2026 steht die Bündelliste nicht mehr auf der Seite; geprüft
    wird das Fragment."""
    _baue_ohne_band(tmp_path)
    zeilen = _lager_ohne_band(tmp_path).select("#gr-bndliste .gr-bnd")
    assert zeilen
    for z in zeilen:
        assert z.get("data-band") in ("xs", "m", "l"), z.get("data-band")


def test_deutlich_weniger_als_hundert_aufklapper(tmp_path):
    """A2: <details> gesamt in der Vergleichsansicht deutlich unter 100 -
    Rechenweg je Zeile, 'Wie gerechnet?', Maßstab, Datenlage. Gemessen an
    der Fixture; der ECHTE Bestand misst derselbe Satz in
    `test_geraete_o2_zeilen_browser` (dort mit Vorgabemodell, 19 Zeilen)."""
    s = _baue_ohne_band(tmp_path)
    tafel = s.select_one("#tafel-tco")
    anzahl = len(tafel.select("details"))
    assert anzahl < 100, f"{anzahl} <details> in der Vergleichsansicht"
    assert anzahl <= 4 + 3 * 3, (
        f"{anzahl} Aufklapper - mehr als Wie-gerechnet + Maßstab + "
        "Datenlage + Rest + Rechenwege je Zeile"
    )


def test_keine_alarmtabelle_mehr_auf_der_geraeteseite(tmp_path):
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    assert tafel.select_one("#gr-alarme") is None
    assert tafel.select_one(".gr-chips") is None
    assert tafel.select_one(".gr-a-zeile") is None, (
        "Alarmzeilen stehen noch in der Vergleichsansicht"
    )
    assert "stehen einem Wettbewerber gegenüber" not in tafel.get_text(" ")


def test_kein_bei_wettbewerbern_gelistet_mehr_auf_der_geraeteseite(tmp_path):
    s = _baue(tmp_path)
    assert s.select_one(".gr-vergleich-luecke") is None
    assert "Bei Wettbewerbern gelistet" not in s.get_text(" ")
