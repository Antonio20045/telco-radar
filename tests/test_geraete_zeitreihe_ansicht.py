"""E2 (AUFTRAG_GERAETE_EINE_SEITE_V2 §1a, 16.09.2026): die TCO-ZEITREIHE
als Aufbereitung - `report/geraete_zeitreihe.py`.

Der genehmigte Prototyp (docs/entwuerfe/geraete-eine-seite-2026-09-16,
entwurf-v2.html, DOM-bewiesen) als SERVERSEITIGE Produktion:

  - Y-Achse TCO-24 in EUR mit Ticks, X-Achse das DATUM mit den ECHTEN
    Messtagen als Ticks und echten Datumsabstaenden (keine ordinale Achse).
  - Je Anbieter eine Linie mit einem Punkt je Messung; NICHTS interpoliert
    (unter 2 Punkten: kein Linienzug, nur der Punkt).
  - Wert-Labels am letzten (gross) und ersten (klein) Punkt; Vodafone rot
    mit Etikett "unser Angebot"; Beleg-Link je Anbieter am Linienende.
  - Startzustand = Modell x Band mit den meisten Anbietern, dann Punkten -
    AUS DEN DATEN gerechnet, nichts hardcodiert.
  - Antwort-Satz nennt die Leitzahl beim Namen („Kosten über 24 Monate");
    EIN Lueckensatz mit Namen und Alternativ-Baendern samt Betrag
    (Antonio 9b.7 / §4.5).

Alle Zahlen entstehen in Python; der Client setzt nur fertige Knoten.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from tarifleiter_testbestand import mit_leiter
import yaml

from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import geraete_view, geraete_zeitreihe

HEUTE = "2026-09-16"

_KATALOG = {
    "geraete": [
        {
            "hersteller": "Apple",
            "modell": "iPhone 17 Pro",
            "generation": 17,
            "marktstart": "2025-09-19",
            "speicher": [256],
            "segment": "premium",
        },
        {
            "hersteller": "Samsung",
            "modell": "Galaxy S26",
            "generation": 26,
            "marktstart": "2026-01-30",
            "speicher": [256],
            "segment": "premium",
        },
        {
            "hersteller": "Google",
            "modell": "Pixel 11",
            "generation": 11,
            "marktstart": "2026-08-20",
            "speicher": [128],
            "segment": "premium",
        },
    ]
}
_FARBEN = {"farben": {"schwarz": ["Schwarz"]}}
_QUELLEN = {
    "anbieter": [
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
            "name": "o2",
            "typ": "netzbetreiber",
            "rang": 2,
            "methode": "ldjson",
            "basis_url": "https://www.o2online.de",
            "einstiege": [{"url": "https://www.o2online.de/handys"}],
        },
    ]
}

_BUENDEL = [
    ("apple-iphone-17-pro", 256, "o2", "o2:klein", "O2 Mobile Klein", 10, 18.0),
    ("apple-iphone-17-pro", 256, "congstar", "cs:klein", "Allnet Flat XS", 15, 22.0),
    ("apple-iphone-17-pro", 256, "Vodafone", "vf:klein", "Vodafone Mobil XS", 18, 26.0),
    ("apple-iphone-17-pro", 256, "1&1", "11:klein", "All-Net-Flat S", 8, 15.0),
    ("apple-iphone-17-pro", 256, "congstar", "cs:mittel", "Allnet Flat S", 50, 20.0),
    ("samsung-galaxy-s26", 256, "1&1", "11:klein", "All-Net-Flat S", 10, 15.0),
    ("samsung-galaxy-s26", 256, "Telekom", "tk:klein", "MagentaMobil S", 10, 19.0),
]

_HISTORIE = [
    (0, "", "2026-09-12", 18.0),
    (0, "", "2026-09-13", 17.0),
    (0, "-blau", "2026-09-13", 19.0),
    (0, "", "2026-09-14", 18.0),
    (1, "", "2026-09-12", 22.0),
    (1, "", "2026-09-14", 22.0),
    (1, "", "2026-09-15", 22.0),
    (2, "", "2026-09-12", 26.0),
    (2, "", "2026-09-13", 25.5),
    (2, "", "2026-09-14", 25.75),
    (3, "", "2026-09-12", 15.0),
    (4, "", "2026-09-12", 20.0),
    (4, "", "2026-09-13", 19.5),
    (5, "", "2026-09-12", 15.0),
]


def _sku(device_id, speicher):
    return f"{device_id}-{speicher}gb-schwarz"


def _baue(tmp_path: pathlib.Path):
    root = tmp_path / "zeitreihe"
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

    def _listung(anbieter, device_id, speicher, preis):
        return {
            "id": f"{anbieter.lower()}--{_sku(device_id, speicher)}",
            "sku_id": _sku(device_id, speicher),
            "device_id": device_id,
            "anbieter": anbieter,
            "anbieter_typ": "netzbetreiber",
            "netz": anbieter,
            "speicher_gb": speicher,
            "farbe_roh": "Schwarz",
            "farbe_normalisiert": "schwarz",
            "zustand": "neu",
            "first_seen": "2026-09-01",
            "last_verified": HEUTE,
            "status": "aktiv",
            "missed_checks": 0,
            "preis_ohne_vertrag": preis,
            "erstpreis": preis,
            "erstpreis_art": "ohne_vertrag",
            "erstpreis_am": "2026-09-01",
            "quelle_url": f"https://example.de/{anbieter.lower()}/{device_id}",
            "abgerufen_am": HEUTE,
            "verfuegbarkeit": "lieferbar",
            "confidence": "hoch",
            "einstiege": ["https://example.de/l"],
        }

    (state / "geraete_db.json").write_text(
        json.dumps(
            {
                "updated": HEUTE,
                "anbieter": {
                    "Vodafone": {"laeufe": 4, "funde_gesamt": 1},
                    "o2": {"laeufe": 4, "funde_gesamt": 2},
                },
                "listungen": [
                    _listung("Vodafone", "apple-iphone-17-pro", 256, 1199.90),
                    _listung("o2", "apple-iphone-17-pro", 256, 1099.00),
                    _listung("1&1", "samsung-galaxy-s26", 256, 1049.00),
                    _listung("Telekom", "samsung-galaxy-s26", 256, 1079.00),
                    _listung("o2", "google-pixel-11", 128, 799.00),
                ],
            }
        ),
        encoding="utf-8",
    )
    (state / "geraete_preise.jsonl").write_text("", encoding="utf-8")

    buendel = []
    for i, (device_id, speicher, anbieter, tarif_id, tarif, gb, rate) in enumerate(
        _BUENDEL
    ):
        buendel.append(
            {
                "id": f"buendel--{anbieter.lower()}--{_sku(device_id, speicher)}"
                f"--{tarif_id}",
                "sku_id": _sku(device_id, speicher),
                "anbieter": anbieter,
                "tarif_name": tarif,
                "tarif_id": tarif_id,
                "tarif_id_guete": "hoch",
                "tarif_monatlich": 20.0,
                "geraet_zuzahlung": 1.0,
                "geraet_monatsrate": rate,
                "laufzeit_monate": 24,
                "anschlusspreis": 0.0,
                "zustand": "neu",
                "rabatte": [],
                "quelle_url": f"https://example.de/{anbieter.lower()}/{device_id}",
                "abgerufen_am": HEUTE,
                "first_seen": HEUTE,
                "last_verified": HEUTE,
            }
        )
    (state / "geraete_tco.json").write_text(
        json.dumps({"updated": HEUTE, "buendel": buendel, "sim_only": []}),
        encoding="utf-8",
    )

    zeilen = []
    for idx, suffix, tag, rate in _HISTORIE:
        b = buendel[idx]
        farbe = "schwarz" + suffix
        zeilen.append(
            {
                "id": b["id"] + suffix,
                "datum": tag,
                "tarif_id": b["tarif_id"],
                "tarif_id_guete": "hoch",
                "tarif_monatlich": 20.0,
                "geraet_zuzahlung": 1.0,
                "geraet_monatsrate": rate,
                "laufzeit_monate": 24,
                "anschlusspreis": 0.0,
                "quelle_url": b["quelle_url"],
                "abgerufen_am": tag,
                "zustand": "neu",
                "gesamt": round(1.0 + 24 * 20.0 + 24 * rate, 2),
                "sku_id": b["sku_id"].replace("schwarz", farbe),
            }
        )
    (state / "geraete_tco_historie.jsonl").write_text(
        "\n".join(json.dumps(z) for z in zeilen) + "\n", encoding="utf-8"
    )

    tarife = []
    for device_id, speicher, anbieter, tarif_id, tarif, gb, rate in _BUENDEL:
        tarife.append(
            {
                "anbieter": anbieter,
                "name": tarif,
                "tarif_id": tarif_id,
                "art": "mobilfunk",
                "grundgebuehr": 20.0,
                "laufzeit_monate": 24,
                "datenvolumen_gb": gb,
                "preisphasen": [{"von_monat": 1, "bis_monat": None, "betrag": 20.0}],
                "dokument_url": f"https://example.de/pib/{tarif_id}",
                "abgerufen_am": HEUTE,
                "confidence": {},
                "fundstellen": {},
            }
        )
    tarife = mit_leiter(tarife, HEUTE)
    (state / "tarife.jsonl").write_text(
        "\n".join(json.dumps(t) for t in tarife) + "\n", encoding="utf-8"
    )
    return root, state


baue = _baue
"""Öffentlicher Name des Testbestands für neue Tests (Wächter PLC2701)."""


@pytest.fixture(scope="module")
def ansicht(tmp_path_factory):
    root, state = _baue(tmp_path_factory.mktemp("zr"))
    g = geraete_view.aufbereiten(
        state, lade_quellen(root), lade_katalog(root), heute=HEUTE
    )
    return geraete_zeitreihe.aufbereiten(state, g["tco"])


@pytest.fixture(scope="module")
def ansicht_state(tmp_path_factory):
    """Aufbereitung UND state-Pfad in EINEM Rendern - fuer Wahrheitstests,
    die gegen die rohen JSONL-Dateien gegenrechnen (P1/F3)."""
    root, state = _baue(tmp_path_factory.mktemp("zrstate"))
    g = geraete_view.aufbereiten(
        state, lade_quellen(root), lade_katalog(root), heute=HEUTE
    )
    return geraete_zeitreihe.aufbereiten(state, g["tco"]), state


def _paar(ansicht, modell_band):
    modell, band = modell_band
    for p in ansicht["paare"]:
        if p["modell"] == modell and p["band"] == band:
            return p
    return None


def test_der_startzustand_hat_die_meisten_anbieter_dann_punkte(ansicht):
    assert ansicht["start"] == {"modell": "apple-iphone-17-pro-256", "band": "xs"}


def test_der_startzustand_ist_deterministisch(tmp_path):
    root, state = _baue(tmp_path)
    g = geraete_view.aufbereiten(
        state, lade_quellen(root), lade_katalog(root), heute=HEUTE
    )
    a = geraete_zeitreihe.aufbereiten(state, g["tco"])
    b = geraete_zeitreihe.aufbereiten(state, g["tco"])
    assert a["start"] == b["start"]


def test_der_startblock_ist_das_startpaar(ansicht):
    assert ansicht["start_block"]["modell"] == ansicht["start"]["modell"]
    assert ansicht["start_block"]["band"] == ansicht["start"]["band"]


def test_zwei_buendel_desselben_tages_zaehlen_das_minimum(ansicht):
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "xs"))
    svg = paar["svg_breit"]
    suppe = __import__("bs4").BeautifulSoup(svg, "html.parser")
    werte = {t.get_text(strip=True) for t in suppe.select("text.gr-zr-wert")}
    assert "913 €" in werte
    assert "937 €" not in werte
    o2 = sorted(
        (float(c["cx"]), float(c["cy"]))
        for c in suppe.select("circle.gr-zr-punkt")
        if c.get("fill") == "#0019a5"
    )
    assert len(o2) == 3, "o2 traegt drei Messtage - sonst prueft der Test nichts"
    assert o2[1][1] > o2[0][1], o2


def test_unter_zwei_punkten_gibt_es_keinen_linienzug(ansicht):
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "xs"))
    suppe = __import__("bs4").BeautifulSoup(paar["svg_breit"], "html.parser")
    punkte_1u1 = [
        c for c in suppe.select("circle.gr-zr-punkt") if c.get("fill") == "#2f7fd1"
    ]
    pfade = suppe.select("path.gr-zr-linie")
    assert len(punkte_1u1) == 1
    assert len(pfade) == 3


def test_der_fehlende_messtag_bleibt_punktlos(ansicht):
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "xs"))
    suppe = __import__("bs4").BeautifulSoup(paar["svg_breit"], "html.parser")
    xticks = {
        t.get_text(strip=True): float(t["x"]) for t in suppe.select("text.gr-zr-xtick")
    }
    x13 = xticks["13.9."]
    congstar = [
        c for c in suppe.select("circle.gr-zr-punkt") if c.get("fill") == "#ffed00"
    ]
    assert all(abs(float(c["cx"]) - x13) > 0.5 for c in congstar)


def test_die_x_achse_traegt_die_echten_messtage_als_ticks(ansicht):
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "xs"))
    suppe = __import__("bs4").BeautifulSoup(paar["svg_breit"], "html.parser")
    texte = [t.get_text(strip=True) for t in suppe.select("text.gr-zr-xtick")]
    assert texte == ["12.9.", "13.9.", "14.9.", "15.9."]


def test_die_x_abstaende_sind_datumsabstaende_keine_ordinalachse(ansicht):
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "xs"))
    suppe = __import__("bs4").BeautifulSoup(paar["svg_breit"], "html.parser")
    xticks = {
        t.get_text(strip=True): float(t["x"]) for t in suppe.select("text.gr-zr-xtick")
    }
    eins = xticks["13.9."] - xticks["12.9."]
    zwei = xticks["15.9."] - xticks["13.9."]
    assert zwei == pytest.approx(2 * eins, abs=1.0)


def test_die_y_achse_traegt_betraege_als_ticks(ansicht):
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "xs"))
    suppe = __import__("bs4").BeautifulSoup(paar["svg_breit"], "html.parser")
    texte = [t.get_text(strip=True) for t in suppe.select("text.gr-zr-achse")]
    assert texte and all(t.endswith("€") for t in texte)


def test_der_antwort_satz_nennt_die_leitzahl_beim_namen(ansicht):
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "xs"))
    text = __import__("re").sub(r"<[^>]+>", "", paar["antwort_html"])
    assert "Kosten über 24 Monate" in text, text
    assert "TCO-24" not in text, text


def test_der_antwort_satz_nennt_geraet_band_anbieter_zahl_und_schnitt(ansicht):
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "xs"))
    text = __import__("re").sub(r"<[^>]+>", "", paar["antwort_html"])
    text = text.replace("&amp;", "&").replace("&nbsp;", " ")
    assert "iPhone 17 Pro" in text and "XS" in text
    assert "1&1" in text and "841,00 €" in text
    assert "€/Monat" in text


def test_der_antwort_satz_nennt_die_vodafone_referenz(ansicht):
    """P4/D4 (18.09.2026): das Delta zur Vodafone-Referenz steht nicht
    mehr IM Satz, sondern als EIGENE Leitzahl ueber ihm (DIE ANTWORT IST
    DIE GROESSTE ZAHL) - der Satz nennt Anbieter und TCO-24, die Leitzahl
    den Abstand samt Referenzbetrag. Beides zusammen ist die Antwort."""
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "xs"))
    text = __import__("re").sub(r"<[^>]+>", "", paar["antwort_html"])
    leit = __import__("re").sub(r"<[^>]+>", "", paar["leitzahl_html"] or "")
    assert "Vodafone" in leit and "1.105,00 €" in leit, (text, leit)


def test_der_antwort_satz_polt_den_abstand_zur_referenz_richtig(ansicht):
    """E3-Fix (QA 17.09.2026, B1): Der Anhang nannte den Abstand des
    GÜNSTIGSTEN Angebots immer 'über der Vodafone-Referenz' - die Zeilen
    stehen aufsteigend, die Differenz eigen − beste ist also IMMER positiv,
    und der Beste liegt UNTER der Referenz, sobald ein Wettbewerber führt.
    Dasselbe Δ-Vorzeichen wie die Bündel-Karte desselben Angebots (S4):
    unter heißt günstiger. 1&1 (841,00 €) liegt 264,00 € UNTER der
    Vodafone-Referenz (1.105,00 €) - die Karte darunter sagt genau das.
    P4/D4: der Abstand steht jetzt in der LEITZAHL ueber dem Satz -
    Polarität und Wortlaut unveraendert, nur der Ort ist neu."""
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "xs"))
    text = __import__("re").sub(r"<[^>]+>", "", paar["antwort_html"])
    leit = __import__("re").sub(r"<[^>]+>", "", paar["leitzahl_html"] or "")
    assert "264,00 €" in leit, (text, leit)
    assert "1&amp;1 unter Vodafone (1.105,00 €)" in leit, (text, leit)
    assert "über Vodafone" not in leit, leit
    assert "über der Vodafone-Referenz" not in text, text


def test_der_antwort_satz_endet_auf_genau_einem_punkt(ansicht):
    saetze = {
        f"{p['modell']}/{p['band']}": __import__("re")
        .sub(r"<[^>]+>", "", p["antwort_html"])
        .strip()
        for p in ansicht["paare"]
    }
    assert any(p["leitzahl_html"] for p in ansicht["paare"]), (
        "kein Paar mit Leitzahl - die Fixture prueft den Delta-Fall nicht"
    )
    for schluessel, text in saetze.items():
        assert text.endswith("."), schluessel
        assert not text.endswith(".."), schluessel
        assert ").." not in text, schluessel


_ZEILE = {
    "anbieter": "o2",
    "gesamt": 1000.0,
    "tarif": "O2 Mobile M",
    "schnitt_monat": 41.67,
    "band_gb_text": "30 GB",
}


def _text(html):
    return __import__("re").sub(r"<[^>]+>", "", html)


def test_der_antwort_satz_nennt_den_hersteller_wenn_der_katalog_ihn_kennt():
    modell = {
        "id": "xiaomi-17",
        "titel": "Xiaomi 17",
        "hersteller": "Xiaomi",
        "speicher": None,
    }
    html = geraete_zeitreihe._antwort_html(modell, "m", [dict(_ZEILE)], {"label": "M"})
    assert "Beim Xiaomi 17 im Band M" in _text(html), _text(html)


def test_ohne_katalog_hersteller_bleibt_der_kurzname_geraten_wird_nichts():
    modell = {"id": "17", "titel": "17", "hersteller": "", "speicher": None}
    html = geraete_zeitreihe._antwort_html(modell, "m", [dict(_ZEILE)], {"label": "M"})
    assert "Beim 17 im Band M" in _text(html), _text(html)
    assert "Beim  17" not in _text(html)


def test_der_antwort_satz_mit_hersteller_die_kachel_ohne(ansicht):
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "xs"))
    assert "Beim Apple iPhone 17 Pro im Band XS" in _text(paar["antwort_html"]), _text(
        paar["antwort_html"]
    )
    assert ansicht["daten"]["kurz"]["apple-iphone-17-pro-256"] == "iPhone 17 Pro"


def test_ein_lueckensatz_mit_alternativbaendern_statt_zeilen(ansicht):
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "m"))
    luecke = paar["luecke_text"]
    assert luecke
    assert "Telekom" in luecke and luecke.count("Telekom") == 1
    assert "o2 (XS 913,00 €)" in luecke
    assert "1&1 (XS 841,00 €)" in luecke
    assert "Vodafone (XS 1.105,00 €)" in luecke


def test_der_lueckensatz_nennt_nur_anbieter_ohne_zeile(ansicht):
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "xs"))
    for name in ("1&1", "congstar"):
        assert name not in paar["luecke_text"]


def test_jede_linie_endet_in_einem_beleglink_mit_datum(ansicht):
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "xs"))
    suppe = __import__("bs4").BeautifulSoup(paar["svg_breit"], "html.parser")
    links = suppe.select("a.gr-zr-link")
    assert len(links) == 4
    for a in links:
        href = a.get("href") or ""
        assert href.startswith("https://")
        assert "↗" in a.get_text()


def test_auch_ein_punkt_anbieter_bekommt_ein_endlabel(ansicht):
    """B-Fix (Review 24.09.2026, S1 - ROT vor dem Fix): bis zu diesem Fix
    bekam ein Anbieter mit nur EINEM Messtag KEIN Endlabel - auf dem
    Desktop (>= 701 px, Legende per CSS ausgeblendet) stand sein Punkt
    dann unbeschriftet da (gemessen: Telekom, ein Messtag 15.09., als
    unbeschrifteter magenta Punkt). 1&1 hat hier genau EINEN Messtag und
    ist trotzdem beschriftet - Name, Beleg-Link UND der Punkt (plus Halo)
    bleiben."""
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "xs"))
    suppe = __import__("bs4").BeautifulSoup(paar["svg_breit"], "html.parser")
    namen = {
        t.get_text(strip=True).rstrip("↗ ") for t in suppe.select("text.gr-zr-name")
    }
    assert "1&1" in namen
    einundeins = [
        c for c in suppe.select("circle.gr-zr-punkt") if c.get("fill") == "#2f7fd1"
    ]
    assert len(einundeins) == 1
    assert suppe.select("circle.gr-zr-halo")
    link = next(
        a
        for a in suppe.select("a.gr-zr-link")
        if a.get_text(strip=True).startswith("1&1")
    )
    assert (link.get("href") or "").startswith("https://")


def test_ein_geraet_mit_nur_ein_punkt_serien_ist_trotzdem_beschriftet(ansicht):
    """Das explizite Kriterium des Befunds: ein Modell/Band, dessen
    EINZIGER Anbieter nur einen Messtag traegt (Galaxy S26, Band XS:
    ausschliesslich 1&1, ein Messtag), bekommt trotzdem ein sichtbares
    Endlabel - keine Legende, kein Punkt ohne Namen."""
    paar = _paar(ansicht, ("samsung-galaxy-s26-256", "xs"))
    assert paar is not None
    suppe = __import__("bs4").BeautifulSoup(paar["svg_breit"], "html.parser")
    namen = {
        t.get_text(strip=True).rstrip("↗ ") for t in suppe.select("text.gr-zr-name")
    }
    assert namen == {"1&1"}
    assert suppe.select("circle.gr-zr-punkt")
    assert suppe.select("circle.gr-zr-halo")


def test_vodafone_ist_rot_ohne_zusatzetikett(ansicht):
    """Vodafone erkennt man am Rot und am Namen; das Etikett „unser
    Angebot" unter dem Namen ist am 28.09.2026 gefallen (Antonio: keine
    Unterkommentare)."""
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "xs"))
    suppe = __import__("bs4").BeautifulSoup(paar["svg_breit"], "html.parser")
    vf_punkte = [
        c for c in suppe.select("circle.gr-zr-punkt") if c.get("fill") == "#e60000"
    ]
    assert vf_punkte
    assert "Vodafone" in suppe.get_text(" ")
    assert "unser Angebot" not in paar["svg_breit"]
    assert "unser Angebot" not in paar["svg_schmal"]


def test_kein_beleglink_ohne_echte_url(tmp_path):
    root, state = _baue(tmp_path)
    roh = json.loads((state / "geraete_tco.json").read_text())
    roh["buendel"][0]["quelle_url"] = None
    (state / "geraete_tco.json").write_text(json.dumps(roh), encoding="utf-8")
    g = geraete_view.aufbereiten(
        state, lade_quellen(root), lade_katalog(root), heute=HEUTE
    )
    a = geraete_zeitreihe.aufbereiten(state, g["tco"])
    paar = _paar(a, ("apple-iphone-17-pro-256", "xs"))
    suppe = __import__("bs4").BeautifulSoup(paar["svg_breit"], "html.parser")
    for a_tag in suppe.select("a.gr-zr-link"):
        assert (a_tag.get("href") or "").startswith("https://")


def test_der_suchindex_ist_deterministisch_vorsortiert(ansicht):
    idx = ansicht["suchindex"]
    schluessel = [(-e["band_zahl"], -e["anbieter_zahl"], e["titel"]) for e in idx]
    assert schluessel == sorted(schluessel)
    assert len(idx) == 2


def _erweitere_um_modelle(root, n: int) -> None:
    """Haengt n zusaetzliche EIN-Band-Modelle an den Bestand (B1-Test).

    Jedes bekommt Katalogeintrag, Listung, Bündel und Tarif - es zaehlt
    damit als Modell mit erlaubtem Band und MUSS im Suchindex stehen, egal
    wie weit hinten es sortiert ist."""
    katalog = yaml.safe_load(
        (root / "config" / "geraete_katalog.yaml").read_text(encoding="utf-8")
    )
    db = json.loads(
        (root / "data" / "state" / "geraete_db.json").read_text(encoding="utf-8")
    )
    tco = json.loads(
        (root / "data" / "state" / "geraete_tco.json").read_text(encoding="utf-8")
    )
    tarife = [
        json.loads(z)
        for z in (root / "data" / "state" / "tarife.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if z.strip()
    ]
    for i in range(n):
        device_id = f"samsung-galaxy-x{i}"
        sku = f"{device_id}-256gb-schwarz"
        katalog["geraete"].append(
            {
                "hersteller": "Samsung",
                "modell": f"Galaxy X{i}",
                "generation": i,
                "marktstart": "2026-01-30",
                "speicher": [256],
                "segment": "budget",
            }
        )
        db["listungen"].append(
            {
                "id": f"o2--{sku}",
                "sku_id": sku,
                "device_id": device_id,
                "anbieter": "o2",
                "anbieter_typ": "netzbetreiber",
                "netz": "o2",
                "speicher_gb": 256,
                "farbe_roh": "Schwarz",
                "farbe_normalisiert": "schwarz",
                "zustand": "neu",
                "first_seen": "2026-09-01",
                "last_verified": HEUTE,
                "status": "aktiv",
                "missed_checks": 0,
                "preis_ohne_vertrag": 299.0,
                "erstpreis": 299.0,
                "erstpreis_art": "ohne_vertrag",
                "erstpreis_am": "2026-09-01",
                "quelle_url": f"https://example.de/o2/{device_id}",
                "abgerufen_am": HEUTE,
                "verfuegbarkeit": "lieferbar",
                "confidence": "hoch",
                "einstiege": ["https://example.de/l"],
            }
        )
        tco["buendel"].append(
            {
                "id": f"buendel--o2--{sku}--x{i}:klein",
                "sku_id": sku,
                "anbieter": "o2",
                "tarif_name": f"X{i} Klein",
                "tarif_id": f"x{i}:klein",
                "tarif_id_guete": "hoch",
                "tarif_monatlich": 20.0,
                "geraet_zuzahlung": 1.0,
                "geraet_monatsrate": 15.0,
                "laufzeit_monate": 24,
                "anschlusspreis": 0.0,
                "zustand": "neu",
                "rabatte": [],
                "quelle_url": f"https://example.de/o2/{device_id}",
                "abgerufen_am": HEUTE,
                "first_seen": HEUTE,
                "last_verified": HEUTE,
            }
        )
        tarife.append(
            {
                "anbieter": "o2",
                "name": f"X{i} Klein",
                "tarif_id": f"x{i}:klein",
                "art": "mobilfunk",
                "grundgebuehr": 20.0,
                "laufzeit_monate": 24,
                "datenvolumen_gb": 10,
                "preisphasen": [{"von_monat": 1, "bis_monat": None, "betrag": 20.0}],
                "dokument_url": f"https://example.de/pib/x{i}",
                "abgerufen_am": HEUTE,
                "confidence": {},
                "fundstellen": {},
            }
        )
    (root / "config" / "geraete_katalog.yaml").write_text(
        yaml.safe_dump(katalog, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (root / "data" / "state" / "geraete_db.json").write_text(
        json.dumps(db), encoding="utf-8"
    )
    (root / "data" / "state" / "geraete_tco.json").write_text(
        json.dumps(tco), encoding="utf-8"
    )
    (root / "data" / "state" / "tarife.jsonl").write_text(
        "\n".join(json.dumps(t) for t in tarife) + "\n", encoding="utf-8"
    )


def test_der_suchindex_traegt_jedes_modell_mit_band(tmp_path):
    """B1 (QA 17.09.2026): der Suchindex ist der VORRAT, nicht die Vorschau.

    Bis zum Fix kappte ihn `VORSCHAU_MAX * 4 = 32` Eintraege nach Band- und
    Anbieterzahl - am echten Bestand fehlten 56 von 88 Modellen hinter dem
    genehmigten Suchfeld (ganze Marken, die Galaxy-A-Reihe; 'motorola' ->
    'kein Treffer'). Die 8er-Kappung gilt der ANZEIGE (app.js), nie dem
    Vorrat - derselbe Fehler wie der Scan-Deckel der Uebersetzung (§6).
    2 Bestandsmodelle + 40 gestellte: alle 42 muessen im Knoten stehen,
    auch das alphabetisch letzte."""
    root, state = _baue(tmp_path)
    _erweitere_um_modelle(root, 40)
    g = geraete_view.aufbereiten(
        state, lade_quellen(root), lade_katalog(root), heute=HEUTE
    )
    a = geraete_zeitreihe.aufbereiten(state, g["tco"])
    idx = a["daten"]["suchindex"]
    ids = {e["id"] for e in idx}
    assert len(idx) == 42, f"Suchindex haelt {len(idx)} von 42 Modellen mit Band bereit"
    assert "samsung-galaxy-x39-256" in ids, (
        "das hinterste Modell fehlt - ein Vorratsdeckel waehlt nach Listenposition"
    )


def test_der_client_knoten_traegt_keine_preise(ansicht):
    daten = json.dumps(ansicht["daten"], ensure_ascii=False)
    assert "€" not in daten, "keine Beträge im Client-Knoten"
    assert '"gesamt"' not in daten and '"tco"' not in daten, (
        "keine Preisfelder im Client-Knoten"
    )
    for eintrag in ansicht["daten"]["suchindex"]:
        assert set(eintrag) <= {
            "id",
            "titel",
            "hersteller",
            "speicher",
            "anbieter_zahl",
            "band_zahl",
        }


def test_die_kacheln_sind_die_haeufigsten_geraete_mit_kurznamen(ansicht):
    kacheln = ansicht["kacheln"]
    assert 1 <= len(kacheln) <= 6
    assert kacheln[0]["id"] == ansicht["start"]["modell"]
    assert kacheln[0]["kurz"] == "iPhone 17 Pro"


def test_die_karte_traegt_preis_und_anbieter_punkte(ansicht):
    """P1/F3 (A3) + P1-Fix (Sicht-B2/S3-4): aus dem Chip ist eine KARTE
    geworden, und ihre Werte stehen JE BAND - nicht mehr der ab-Preis über
    alle Bänder neben Bewegung und Punkten des Leit-Paares (zwei
    Maßstäbe). Der Band-Eintrag traegt den ab-Preis des besten ECHTEN
    Angebots DIESES Bandes (mit Ø/Monat und Anbieter) und die Anbieter
    der Zeitreihe DES BANDES als Punkte in ihren HAUSFARBEN."""
    k = ansicht["kacheln"][0]
    assert k["id"] == "apple-iphone-17-pro-256"
    assert set(k["baender"]) == {"xs", "m"}
    klein = k["baender"]["xs"][24]
    assert klein["ab"] == "841,00 €"
    assert klein["ab_monat"] == "35,04 €/Monat"
    assert klein["anb"] == "1&1"
    assert klein["punkte_html"].count("<i") == 4
    assert "#e60000" in klein["punkte_html"], "Vodafone-Punkt in Hausfarbe"
    assert "#0019a5" in klein["punkte_html"], "o2-Punkt in Hausfarbe"
    assert klein["anbieter_text"] == "Vodafone, o2, 1&1, congstar"
    mittel = k["baender"]["m"][24]
    assert mittel["anb"] == "congstar"
    assert mittel["ab"] == "961,00 €"
    assert mittel["punkte_html"].count("<i") == 1
    assert mittel["anbieter_text"] == "congstar"
    assert mittel["delta_text"] == "↓ −12 € in 1 Tag"


def test_das_karten_delta_ist_die_bewegung_des_fuehrenden_anbieters(ansicht_state):
    """Gegenrechnung aus der ROHEN Historie (nicht aus der Aufbereitung),
    JE ANBIETER (A2, 20.09.2026): fuehrend am letzten Messtag des Bandes
    klein ist congstar - die EINZIGE Messung am 15.9. (1.009 EUR) -, und
    congstar stand auch am ersten Messtag (12.9.) bei 1.009 EUR. Die
    Bewegung der Karte ist congstars EIGENE (±0 in 3 Tagen). Die bis A2
    gerechnete Front haette 1&1s 841 EUR (12.9.) gegen congstars 1.009 EUR
    (15.9.) gestellt und "+168 in 3 Tagen" gemeldet - zwei VERSCHIEDENE
    Angebote gegeneinander, ohne dass ein Anbieter seinen Preis geaendert
    hat."""
    ansicht, state = ansicht_state
    k = ansicht["kacheln"][0]
    assert k["id"] == "apple-iphone-17-pro-256"
    tco = json.loads(
        (pathlib.Path(state) / "geraete_tco.json").read_text(encoding="utf-8")
    )
    anbieter_je_id = {b["id"]: b["anbieter"] for b in tco["buendel"]}
    je_anbieter: dict[str, dict[str, float]] = {}
    pfad = pathlib.Path(state) / "geraete_tco_historie.jsonl"
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        satz = json.loads(zeile)
        if not satz["tarif_id"].endswith(":klein"):
            continue
        if satz["id"] not in anbieter_je_id:
            continue
        je = je_anbieter.setdefault(anbieter_je_id[satz["id"]], {})
        if satz["datum"] not in je or satz["gesamt"] < je[satz["datum"]]:
            je[satz["datum"]] = satz["gesamt"]
    tage = sorted({d for je in je_anbieter.values() for d in je})
    assert (tage[0], tage[-1]) == ("2026-09-12", "2026-09-15")
    fuehrend = min(
        (a for a in je_anbieter if tage[-1] in je_anbieter[a]),
        key=lambda a: (je_anbieter[a][tage[-1]], a),
    )
    assert fuehrend == "congstar"
    assert tage[0] in je_anbieter[fuehrend], (
        "ohne Messung am ersten Tag gaebe es keine Bewegung (A2)"
    )
    delta = round(je_anbieter[fuehrend][tage[-1]] - je_anbieter[fuehrend][tage[0]], 2)
    assert delta == 0.0
    assert k["baender"]["xs"][24]["delta_text"] == "±0 € in 3 Tagen"
    assert k["baender"]["xs"][24]["delta_richtung"] == "gleich"


def test_ohne_zwei_messtage_gibt_es_kein_delta(ansicht):
    """Galaxy S26 hat EINEN Messtag (12.9.) - eine Bewegung daraus waere
    geraten. Die Karte zeigt keins (Feld None, kein Pfeil)."""
    k = ansicht["kacheln"][1]
    assert k["id"] == "samsung-galaxy-s26-256"
    for je_laufzeit in k["baender"].values():
        for band in je_laufzeit.values():
            assert band["delta_text"] is None
            assert band["delta_richtung"] is None


def test_bewegung_traegt_alle_richtungen():
    """Die Richtungs-Sprache der Karte: steigen rot, sinken gruen,
    unverändert grau - und gemessen wird die Reihe DES ANBIETERS, der am
    letzten Messtag fuehrt, nie der Wert des ersten Anbieters der
    Schleife."""
    steigt = geraete_zeitreihe._bewegung(
        {"a": [["2026-09-12", 100.0], ["2026-09-14", 120.0]]}
    )
    assert steigt == {"text": "↑ +20 € in 2 Tagen", "richtung": "steigt"}
    sinkt = geraete_zeitreihe._bewegung(
        {"a": [["2026-09-12", 100.0], ["2026-09-13", 90.0]]}
    )
    assert sinkt == {"text": "↓ −10 € in 1 Tag", "richtung": "sinkt"}
    gleich = geraete_zeitreihe._bewegung(
        {"a": [["2026-09-12", 100.0], ["2026-09-13", 100.0]]}
    )
    assert gleich == {"text": "±0 € in 1 Tag", "richtung": "gleich"}
    front = geraete_zeitreihe._bewegung(
        {
            "a": [["2026-09-12", 100.0], ["2026-09-13", 110.0]],
            "b": [["2026-09-13", 90.0]],
        }
    )
    assert front is None
    assert geraete_zeitreihe._bewegung({"a": [["2026-09-12", 100.0]]}) is None


def test_wechselt_der_guenstigste_anbieter_ohne_preisaenderung_gibt_es_keine_bewegung():
    """A2 (20.09.2026), der Befund am iPhone 17 Pro, Band XS: congstar
    am 12.9., 1&1 am 18.9. - KEIN Anbieter hat seinen Preis geaendert, und
    die Karte meldete "+387 EUR in 6 Tagen". Bewegung ist anzeigepflichtig
    nur je ANBIETER: der Fuehrende am letzten Messtag (1&1) fehlt am
    ersten, also gibt es fuer ihn keine Bewegung - keinesfalls die
    Differenz der zwei Angebote."""
    assert (
        geraete_zeitreihe._bewegung(
            {"congstar": [["2026-09-12", 1009.0]], "1&1": [["2026-09-18", 1396.0]]}
        )
        is None
    )
    assert (
        geraete_zeitreihe._bewegung(
            {
                "congstar": [["2026-09-12", 1009.0], ["2026-09-18", 1009.0]],
                "1&1": [["2026-09-18", 900.0]],
            }
        )
        is None
    )


def test_die_bewegung_misst_den_fuehrenden_anbieter_an_beiden_endtagen():
    """Wer am letzten Messtag fuehrt, dessen EIGENE Reihe zwischen erstem
    und letztem Messtag ist die Bewegung - inklusive Gleichstand und
    Gleichstands-Tie-break ueber die Anbieterfolge (deterministisch, kein
    Wuerfeln je Rendern)."""
    steigt = geraete_zeitreihe._bewegung(
        {
            "a": [["2026-09-12", 100.0], ["2026-09-13", 95.0]],
            "b": [["2026-09-12", 90.0], ["2026-09-13", 94.0]],
        }
    )
    assert steigt == {"text": "↑ +4 € in 1 Tag", "richtung": "steigt"}
    gleich = geraete_zeitreihe._bewegung(
        {
            "o2": [["2026-09-12", 100.0], ["2026-09-13", 100.0]],
            "1&1": [["2026-09-12", 80.0]],
        }
    )
    assert gleich == {"text": "±0 € in 1 Tag", "richtung": "gleich"}
    tie = geraete_zeitreihe._bewegung(
        {
            "1&1": [["2026-09-12", 80.0], ["2026-09-13", 100.0]],
            "o2": [["2026-09-12", 120.0], ["2026-09-13", 100.0]],
        }
    )
    assert tie == {"text": "↓ −20 € in 1 Tag", "richtung": "sinkt"}


def test_ohne_historie_gibt_es_den_ehrlichen_leersatz(tmp_path):
    root, state = _baue(tmp_path)
    (state / "geraete_tco_historie.jsonl").write_text("", encoding="utf-8")
    g = geraete_view.aufbereiten(
        state, lade_quellen(root), lade_katalog(root), heute=HEUTE
    )
    a = geraete_zeitreihe.aufbereiten(state, g["tco"])
    assert a["hat_daten"] is False
    paar = _paar(a, ("apple-iphone-17-pro-256", "xs"))
    assert paar["svg_breit"] == ""
    assert "iPhone 17 Pro" in paar["leer_text"]
    assert "XS" in paar["leer_text"]


def test_die_schmalvariante_zeigt_dieselben_werte_weniger_labels(ansicht):
    paar = _paar(ansicht, ("apple-iphone-17-pro-256", "xs"))
    breit = __import__("bs4").BeautifulSoup(paar["svg_breit"], "html.parser")
    schmal = __import__("bs4").BeautifulSoup(paar["svg_schmal"], "html.parser")
    assert len(schmal.select("circle.gr-zr-punkt")) == len(
        breit.select("circle.gr-zr-punkt")
    )
    assert len(schmal.select("text.gr-zr-xtick")) == len(
        breit.select("text.gr-zr-xtick")
    )
    assert len(schmal.select(".gr-zr-wert--erst")) == 0


_AUTO_EINTRAG = {
    "hersteller": "Apple",
    "modell": "iPhone 18 Pro",
    "generation": 18,
    "speicher": [256],
    "auto": "2026-09-15",
}


def _baue_mit_auto(tmp_path: pathlib.Path, messtage: list[str]):
    """_baue plus einem AUTO angelegten iPhone 18 Pro (State, nicht Config -
    der Produktionsweg) mit o2-Buendel im Band XS und N Messtagen."""
    root, state = _baue(tmp_path)

    (state / "geraete_katalog_auto.json").write_text(
        json.dumps({"geraete": [_AUTO_EINTRAG]}, ensure_ascii=False), encoding="utf-8"
    )

    db = json.loads((state / "geraete_db.json").read_text(encoding="utf-8"))
    gid, speicher = "apple-iphone-18-pro", 256
    db["listungen"].append(
        {
            "id": f"o2--{_sku(gid, speicher)}",
            "sku_id": _sku(gid, speicher),
            "device_id": gid,
            "anbieter": "o2",
            "anbieter_typ": "netzbetreiber",
            "netz": "o2",
            "speicher_gb": speicher,
            "farbe_roh": "Schwarz",
            "farbe_normalisiert": "schwarz",
            "zustand": "neu",
            "first_seen": "2026-09-15",
            "last_verified": HEUTE,
            "status": "aktiv",
            "missed_checks": 0,
            "preis_ohne_vertrag": 1199.00,
            "erstpreis": 1199.00,
            "erstpreis_art": "ohne_vertrag",
            "erstpreis_am": "2026-09-15",
            "quelle_url": "https://example.de/o2/iphone-18-pro",
            "abgerufen_am": HEUTE,
            "verfuegbarkeit": "lieferbar",
            "confidence": "hoch",
            "einstiege": ["https://example.de/l"],
        }
    )
    (state / "geraete_db.json").write_text(json.dumps(db), encoding="utf-8")

    tco = json.loads((state / "geraete_tco.json").read_text(encoding="utf-8"))
    buendel_id = f"buendel--o2--{_sku(gid, speicher)}--o2:klein"
    tco["buendel"].append(
        {
            "id": buendel_id,
            "sku_id": _sku(gid, speicher),
            "anbieter": "o2",
            "tarif_name": "O2 Mobile Klein",
            "tarif_id": "o2:klein",
            "tarif_id_guete": "hoch",
            "tarif_monatlich": 20.0,
            "geraet_zuzahlung": 1.0,
            "geraet_monatsrate": 18.0,
            "laufzeit_monate": 24,
            "anschlusspreis": 0.0,
            "zustand": "neu",
            "rabatte": [],
            "quelle_url": "https://example.de/o2/18pro",
            "abgerufen_am": HEUTE,
            "first_seen": "2026-09-15",
            "last_verified": HEUTE,
        }
    )
    (state / "geraete_tco.json").write_text(json.dumps(tco), encoding="utf-8")

    zeilen = (
        (state / "geraete_tco_historie.jsonl").read_text(encoding="utf-8").splitlines()
    )
    for tag in messtage:
        zeilen.append(
            json.dumps(
                {
                    "id": buendel_id,
                    "datum": tag,
                    "tarif_id": "o2:klein",
                    "tarif_id_guete": "hoch",
                    "tarif_monatlich": 20.0,
                    "geraet_zuzahlung": 1.0,
                    "geraet_monatsrate": 18.0,
                    "laufzeit_monate": 24,
                    "anschlusspreis": 0.0,
                    "quelle_url": "https://example.de/o2/18pro",
                    "abgerufen_am": tag,
                    "zustand": "neu",
                    "gesamt": 1600.00,
                    "sku_id": _sku(gid, speicher),
                }
            )
        )
    (state / "geraete_tco_historie.jsonl").write_text(
        "\n".join(z for z in zeilen if z) + "\n", encoding="utf-8"
    )
    return root, state


def test_auto_modell_mit_einem_mestag_steht_nicht_in_der_wahl(tmp_path):
    root, state = _baue_mit_auto(tmp_path, ["2026-09-15"])
    g = geraete_view.aufbereiten(
        state, lade_quellen(root), lade_katalog(root), heute=HEUTE
    )
    a = geraete_zeitreihe.aufbereiten(state, g["tco"])

    ids = {m["id"] for m in a["suchindex"]}
    assert "apple-iphone-18-pro-256" not in ids
    assert all(p["modell"] != "apple-iphone-18-pro-256" for p in a["paare"])
    assert all(k["id"] != "apple-iphone-18-pro-256" for k in a["kacheln"])
    assert a["start"]["modell"] != "apple-iphone-18-pro-256"

    assert any(
        z["modell"] == "iPhone 18 Pro" and z["listungen"] >= 1
        for z in g["katalog_modelle"]
    )

    assert "samsung-galaxy-s26-256" in ids


def test_auto_modell_mit_zwei_mestagen_steht_in_der_wahl(tmp_path):
    root, state = _baue_mit_auto(tmp_path, ["2026-09-15", "2026-09-16"])
    g = geraete_view.aufbereiten(
        state, lade_quellen(root), lade_katalog(root), heute=HEUTE
    )
    a = geraete_zeitreihe.aufbereiten(state, g["tco"])
    ids = {m["id"] for m in a["suchindex"]}
    assert "apple-iphone-18-pro-256" in ids
    assert any(p["modell"] == "apple-iphone-18-pro-256" for p in a["paare"])


def _h3_karte(anbieter, gesamt, monate, band="xs", frisch=True):
    """Eine Kartenzeile in der Form, die `_band_zeilen` liest; seit Teil A
    trägt jede Karte ihre Ratenlaufzeit (hier gleich dem Zeitraum)."""
    return {
        "anbieter": anbieter,
        "gesamt": gesamt,
        "schnitt_monat": round(gesamt / monate, 2),
        "leitzahl_monate": monate,
        "raten_laufzeit": monate,
        "tarif": f"{anbieter} Tarif",
        "band": band,
        "band_gb_text": "15 GB",
        "vergleichbar": True,
        "belastbar": True,
        "frisch": frisch,
        "sku_id": f"sku-{anbieter}",
        "naeherung": False,
        "quelle_url": f"https://x.invalid/{anbieter}",
        "abgerufen_am": HEUTE,
    }


def test_h3_eine_36_monats_karte_ist_keine_zeile_dieser_tafel():
    """Rot gegen den alten Stand: dort stand 1&1 mit 1.299,54 EUR (36
    Monate) als GUENSTIGSTE Zeile vor Vodafones 1.433,80 EUR (24 Monate)
    - der Antwort-Satz nannte sie "Kosten über 24 Monate", und
    `_leitzahl_html` zog die zwei Zahlen voneinander ab.

    Datenkonzept Geräte Schritt 2: die 36-Raten-Karte gehört in die
    36er-Ansicht, nicht als „fremd“ in die 24er."""
    modell = {
        "id": "m",
        "titel": "Testgerät",
        "hersteller": "Test",
        "speicher": 256,
        "karten": [_h3_karte("1&1", 1299.54, 36), _h3_karte("Vodafone", 1433.80, 24)],
    }
    satz = geraete_zeitreihe._band_zeilen(modell)["xs"]
    assert [z["anbieter"] for z in satz["zeilen"]] == ["Vodafone"]
    assert satz["fremd"] == []
    sechsunddreissig = geraete_zeitreihe._band_zeilen(modell, 36)["xs"]
    assert [z["anbieter"] for z in sechsunddreissig["zeilen"]] == ["1&1"]
    assert geraete_zeitreihe._leitzahl_html(satz["zeilen"]) is None
    text = _text(
        geraete_zeitreihe._antwort_html(
            modell, "xs", satz["zeilen"], {"label": "XS"}, fremd=satz["fremd"]
        )
    )
    assert "führt nur Vodafone" in text and "1.433,80 €" in text
    assert "1.299,54" not in text


def test_h3_der_luecken_satz_nennt_anbieter_und_zeitraum():
    """Der Anbieter faellt aus den Zeilen - und wird GENANNT. "Kein
    Bündel in diesem Band" waere gelogen (harte Regel 9). Seit Datenkonzept
    Geräte Schritt 2 heißt der Grund „mit 24 Raten nicht erfasst“."""
    modell = {
        "id": "m",
        "titel": "Testgerät",
        "hersteller": "Test",
        "speicher": 256,
        "karten": [_h3_karte("1&1", 1299.54, 36), _h3_karte("Vodafone", 1433.80, 24)],
    }
    satz = geraete_zeitreihe._band_zeilen(modell)["xs"]
    luecken = geraete_zeitreihe._luecken(
        satz["zeilen"], modell["karten"], "xs", fremd=satz["fremd"], laufzeit=24
    )
    eins = next(l for l in luecken if l["anbieter"] == "1&1")
    assert (eins["grund"], eins["monate"]) == ("nicht-erfasst", None)
    text = geraete_zeitreihe._luecke_text(luecken, {})
    assert "Mit 24 Raten nicht erfasst: 1&1." in text, text
    assert "Kein Bündel in diesem Band: 1&1" not in text


def test_h3_ein_band_mit_nur_fremdem_zeitraum_verschwindet_nicht():
    """Der stille Verlust, den das Tor sonst verursacht: ein Band, dessen
    EINZIGES Angebot 36 Monate traegt, hat keine Zeile - "führt kein
    Anbieter ein Bündel" waere falsch, und das Band ganz aus der Auswahl
    zu nehmen waere ein gemessenes Angebot ohne ein Wort.

    Datenkonzept Geräte Schritt 2: das Angebot steht in der 36er-Ansicht;
    die 24er-Ansicht desselben Bandes nennt 1&1 „nicht erfasst“."""
    modell = {
        "id": "m",
        "titel": "Testgerät",
        "hersteller": "Test",
        "speicher": 256,
        "karten": [_h3_karte("1&1", 2019.54, 36)],
    }
    assert "xs" not in geraete_zeitreihe._band_zeilen(modell)
    satz = geraete_zeitreihe._band_zeilen(modell, 36)["xs"]
    assert [z["anbieter"] for z in satz["zeilen"]] == ["1&1"]
    text = _text(
        geraete_zeitreihe._antwort_html(
            modell, "xs", satz["zeilen"], {"label": "XS"}, laufzeit=36
        )
    )
    assert "mit 36 Raten" in text and "2.019,54 €" in text, text
    leer = _text(
        geraete_zeitreihe._antwort_html(modell, "xs", [], {"label": "XS"}, laufzeit=24)
    )
    assert "führt kein Anbieter ein Bündel" not in leer
    assert "mit 24 Raten ist kein Bündel erfasst" in leer, leer
    luecken = geraete_zeitreihe._luecken([], modell["karten"], "xs", laufzeit=24)
    assert "Mit 24 Raten nicht erfasst: 1&1." in geraete_zeitreihe._luecke_text(
        luecken, {}
    )


def test_z1_die_beschriftung_behauptet_nur_zeitraeume_die_im_bild_stehen(ansicht):
    """P0-B-z1: Graph und Beschriftung sagen dasselbe - ohne Kappung.

    ROT gegen den vorigen Stand (P0-B-h3): der verlangte hier, dass ein
    Anbieter mit fremdem Zeitraum KEINE Kurve traegt, und liess die
    Beschriftung dafuer fest "Kosten über 24 Monate" sagen. Das nahm dem
    Leser ein gemessenes Angebot (harte Regel 9). Jetzt gilt die
    Selbstauskunft des Bildes: nennt die Beschriftung EINEN Zeitraum,
    wiederholt ihn keine Kurve; nennt sie mehrere, traegt JEDE Kurve
    ihren eigenen am Ende.
    """
    paare = ansicht["paare"]
    assert paare, "keine Paare - der Test prueft nichts"
    mit_svg = 0
    for p in paare:
        for bild in (p["svg_breit"], p["svg_schmal"]):
            if not bild:
                continue
            mit_svg += 1
            kopf = re.search(r"aria-label='([^']*)'", bild).group(1)
            kopf = kopf.split(" je Messtag")[0]
            assert kopf.startswith("Kosten"), kopf
            monate = re.findall(r"gr-zr-mon'[^>]*>([^<]*)<", bild)
            kurven = len(set(re.findall(r"data-anb='([^']*)'", bild)))
            if " und " in kopf:
                assert len(monate) == kurven, (
                    f"{p['modell']}/{p['band']}: {kopf!r} nennt mehrere "
                    f"Zeitraeume, aber nur {len(monate)} von {kurven} "
                    f"Kurven tragen ihren"
                )
            else:
                assert not monate, (
                    f"{p['modell']}/{p['band']}: {kopf!r} gilt fuer alle "
                    f"Kurven - das Etikett {monate} steht doppelt"
                )
    assert mit_svg, "kein Graph im Bestand - der Test prueft nichts"


def test_z1_der_alternativ_betrag_nennt_seinen_abweichenden_zeitraum():
    """MITNEHMEN (:371): die Luecken-Zeile nannte einen 36-Monats-Betrag
    als Alternative OHNE seinen Zeitraum - mitten in einem Satz, der von
    24 Monaten spricht. ROT gegen den alten Stand: dort stand nur
    "mittel 2.019,54 €"."""
    karten = [
        _h3_karte("1&1", 2019.54, 36, band="m"),
        _h3_karte("Vodafone", 1433.80, 24, band="xs"),
    ]
    alternativen = geraete_zeitreihe._alternativen(karten, "xs", "1&1")
    assert alternativen == [{"band": "m", "tco": 2019.54, "monate": 36}]
    luecken = geraete_zeitreihe._luecken([{"anbieter": "Vodafone"}], karten, "xs")
    text = geraete_zeitreihe._luecke_text(luecken, {})
    assert "1&1 (M 2.019,54 € über 36 Monate)" in text, text
    karten24 = [
        _h3_karte("1&1", 1700.00, 24, band="m"),
        _h3_karte("Vodafone", 1433.80, 24, band="xs"),
    ]
    text24 = geraete_zeitreihe._luecke_text(
        geraete_zeitreihe._luecken([{"anbieter": "Vodafone"}], karten24, "xs"), {}
    )
    assert "1&1 (M 1.700,00 €)" in text24, text24


def test_z1_die_alternative_vergleicht_nur_innerhalb_eines_zeitraums():
    """Clean Code 1 / Tor: die guenstigste Alternative EINES Bandes darf
    nicht ueber zwei Laufzeiten gewaehlt werden. ROT gegen den alten
    Stand: dort gewann das Minimum (1.200,00 € über 36 Monate) gegen die
    vergleichbare 24-Monats-Zahl."""
    karten = [
        _h3_karte("1&1", 1200.00, 36, band="m"),
        _h3_karte("1&1", 1500.00, 24, band="m"),
        _h3_karte("Vodafone", 1433.80, 24, band="xs"),
    ]
    assert geraete_zeitreihe._alternativen(karten, "xs", "1&1") == [
        {"band": "m", "tco": 1500.00, "monate": 24}
    ]


def test_z1_die_bewegung_geht_nie_ueber_zwei_zeitraeume():
    """Das Tor sitzt am VORZEICHEN, nicht an der Sichtbarkeit (P0-B-z1).

    congstar rechnet ueber 24 Monate und sinkt um 50 €; 1&1s Summe ist
    ZAHLENMAESSIG kleiner, traegt aber 36 Monate. ROT gegen den alten
    Stand: dort waehlte `_bewegung` den Fuehrenden ueber beide Zeitraeume
    (1&1) und meldete dessen ±0 als Bewegung des Bandes.
    """
    serien = {
        "congstar": [("2026-09-12", 1459.0), ("2026-09-15", 1409.0)],
        "1&1": [("2026-09-12", 1299.54), ("2026-09-15", 1299.54)],
    }
    zeitraeume = {"congstar": [24], "1&1": [36]}
    assert geraete_zeitreihe._bewegung(serien, zeitraeume) == {
        "text": "↓ −50 € in 3 Tagen",
        "richtung": "sinkt",
    }
    assert geraete_zeitreihe._bewegung(serien) == {
        "text": "±0 € in 3 Tagen",
        "richtung": "gleich",
    }
    assert (
        geraete_zeitreihe._bewegung(
            {"1&1": [("2026-09-12", 1000.0), ("2026-09-15", 1500.0)]}, {"1&1": [24, 36]}
        )
        is None
    )


def test_z1_der_fremde_zeitraum_hat_sein_eigenes_kachel_feld(tmp_path):
    """MITNEHMEN (:1521): der Zustand lag in `alt_text` - dem Feld des
    ALTEN Stands - und bekam in der Vorlage dessen Beschriftung ("kein
    aktueller Bündel-Stand") ueber einem heute gemessenen Angebot. ROT
    gegen den alten Stand: dort war `alt_text` gesetzt und `fremd_text`
    gab es nicht.

    Seit Datenkonzept Geräte Schritt 2 steht eine 36-Raten-Karte in ihrer
    eigenen Ansicht; fremd ist in der 24er-Ansicht nur noch eine Karte mit
    24 Raten, deren Zahl über einen anderen Zeitraum läuft (Tarif 36 Monate).
    """
    fremd = _h3_karte("1&1", 2019.54, 36)
    fremd["raten_laufzeit"] = 24
    tco = {
        "modelle": [
            {
                "id": "m",
                "titel": "Testgerät 256 GB",
                "hersteller": "Test",
                "speicher": 256,
                "karten": [fremd],
            }
        ],
        "baender_katalog": [{"key": "xs", "label": "XS"}],
        "band_je_tarif": {},
        "historie_lage": {},
    }
    a = geraete_zeitreihe.aufbereiten(tmp_path, tco)
    kachel = a["kacheln"][0]["baender"]["xs"][24]
    assert kachel["fremd_text"] == "nur über 36 Monate"
    assert kachel["alt_text"] is None, "der fremde Zeitraum ist kein alter Stand"
    assert kachel["ab"] is None, "kein Betrag ohne vergleichbaren Zeitraum"


def _p1_zeile(bid, datum, laufzeit, rate):
    return {
        "id": bid,
        "datum": datum,
        "tarif_id": "tarif-x",
        "tarif_monatlich": 20.0,
        "geraet_zuzahlung": 0.0,
        "geraet_monatsrate": rate,
        "laufzeit_monate": laufzeit,
        "anschlusspreis": 0.0,
        "gesamt": 1200.0,
        "quelle_url": "https://example.de/congstar",
        "abgerufen_am": datum,
    }


def _p1_buendel(bid, laufzeit, rate):
    return {
        "id": bid,
        "sku_id": "sku-x",
        "anbieter": "congstar",
        "tarif_name": "Allnet Flat XS",
        "tarif_id": "tarif-x",
        "tarif_id_guete": "hoch",
        "tarif_monatlich": 20.0,
        "geraet_zuzahlung": 0.0,
        "geraet_monatsrate": rate,
        "laufzeit_monate": laufzeit,
        "anschlusspreis": 0.0,
        "zustand": "neu",
        "quelle_url": "https://example.de/congstar",
        "abgerufen_am": "2026-09-22",
    }


def _p1_state(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    id12 = "buendel--congstar--sku-x--tarif-x--12"
    id24 = "buendel--congstar--sku-x--tarif-x--24"
    (state / "geraete_tco.json").write_text(
        json.dumps(
            {"buendel": [_p1_buendel(id12, 12, 60.0), _p1_buendel(id24, 24, 30.0)]}
        ),
        encoding="utf-8",
    )
    zeilen = [
        _p1_zeile(id12, "2026-09-22", 12, 60.0),
        _p1_zeile(id24, "2026-09-22", 24, 30.0),
    ]
    (state / "geraete_tco_historie.jsonl").write_text(
        "\n".join(json.dumps(z) for z in zeilen) + "\n", encoding="utf-8"
    )
    karte = _h3_karte("congstar", 1200.0, 24)
    karte["sku_id"] = "sku-x"
    tco = {
        "modelle": [{"id": "modell-x", "karten": [karte]}],
        "band_je_tarif": {"tarif-x": "xs"},
        "baender_katalog": [{"key": "xs", "label": "XS"}],
    }
    return state, tco


def test_p1_gleichstand_zweier_ratenlaufzeiten_verliert_die_zweite_nicht(tmp_path):
    """ROT vor dem Fix: `besser = wert < alt["wert"]` (strikt) verwarf die
    zweite Zeile still, sobald beide denselben `wert` trugen - welche der
    beiden ueberlebte, entschied nur die Dateireihenfolge, und die
    verworfene Zahlweise verschwand ganz.

    Seit Datenkonzept Geräte Schritt 2 rechnet eine 36-Raten-Zahlweise über
    36 Monate und steht nie im Gleichstand mit einer 24-Monats-Zahl; der Fall
    sind deshalb 12 und 24 Raten (beide über 24 Monate, wie Vodafone):
    24 × 20 + 12 × 60 = 24 × 20 + 24 × 30 = 1.200,00 EUR.

    Seit Teil B hat jede Ratenlaufzeit ihre eigene Reihe: beide Zahlweisen
    bleiben, keine verdrängt die andere.
    """
    state, tco = _p1_state(tmp_path)
    messungen = geraete_zeitreihe._messungen(state, tco)
    for laufzeit in (12, 24):
        slot = messungen[("modell-x", "xs", laufzeit)]["congstar"]["2026-09-22"]
        assert slot["laufzeit"] == laufzeit
        assert slot["wert"] == 1200.0


def test_p1_der_rechenweg_nennt_die_zweite_zahlweise(tmp_path):
    """Seit Teil B steht die zweite Zahlweise in ihrer eigenen Ansicht: der
    Rechenweg jeder Laufzeit nennt genau ihre Raten."""
    state, tco = _p1_state(tmp_path)
    a = geraete_zeitreihe.aufbereiten(state, tco)
    for laufzeit in (12, 24):
        paar = next(
            p
            for p in a["paare"]
            if (p["modell"], p["band"], p["laufzeit"]) == ("modell-x", "xs", laufzeit)
        )
        text = re.sub(r"<[^>]+>", " ", paar["rechenweg_html"])
        assert re.findall(r"Geräterate\s+(\d+) ×", text) == [str(laufzeit)], text
        assert "Restschuld" not in paar["rechenweg_html"]


def test_p1_bei_reihenfolgetausch_bleibt_dieselbe_zahlweise_gewinnen(tmp_path):
    """Die Regel ist FEST (kuerzere Laufzeit gewinnt), nicht von der
    Dateireihenfolge abhaengig - dieselbe Pruefung mit vertauschten Zeilen
    muss dasselbe Ergebnis liefern."""
    state, tco = _p1_state(tmp_path)
    id12 = "buendel--congstar--sku-x--tarif-x--12"
    id24 = "buendel--congstar--sku-x--tarif-x--24"
    zeilen = [
        _p1_zeile(id24, "2026-09-22", 24, 30.0),
        _p1_zeile(id12, "2026-09-22", 12, 60.0),
    ]
    (state / "geraete_tco_historie.jsonl").write_text(
        "\n".join(json.dumps(z) for z in zeilen) + "\n", encoding="utf-8"
    )
    messungen = geraete_zeitreihe._messungen(state, tco)
    for laufzeit in (12, 24):
        slot = messungen[("modell-x", "xs", laufzeit)]["congstar"]["2026-09-22"]
        assert slot["laufzeit"] == laufzeit
