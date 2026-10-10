"""Datenkonzept Geräte, Schritt 2 Teil B: verglichen wird nur innerhalb einer
Ratenlaufzeit.

Ein Bestand für das iPhone 17 Pro 256 GB im Band XS mit allen drei
Ansichten (12, 24 und 36 Raten): Vodafone und congstar je 12/24/36, o2 nur 24,
Telekom nur 36, 1&1 ein Vertrag über 36 Monate. Die Erwartungen stehen als
Rechnung aus den Rohwerten im Test, nicht aus dem Produktcode:

  12 Raten (H 24): congstar 1 + 24 × 15 + 12 × 70 = 1.201,00
                   Vodafone 1 + 24 × 29,95 + 12 × 80 = 1.679,80
  24 Raten (H 24): congstar 1 + 24 × 15 + 24 × 38,25 = 1.279,00
                   o2       1 + 24 × 25 + 24 × 40 = 1.561,00
                   Vodafone 1 + 24 × 29,95 + 24 × 45 = 1.799,80
                   1&1      24 × 42,99 + 340 Ablöse + 39,90 = 1.411,66
  36 Raten (H 36): congstar 1 + 24 × 15 + 36 × 26 = 1.297,00
                   Telekom  1 + 24 × 20 + 36 × 31 = 1.597,00
                   Vodafone 1 + 24 × 29,95 + 36 × 31 = 1.835,80

Der Tarif zählt nur seine 24 Monate, ab Monat 25 nur die Rate; 1&1 (Tarif und
Gerät in einem Betrag über 36 Monate) wird nur über 24 Monate verglichen: 24
Beträge plus Ablöse, in der 24er-Ansicht (Antonio, 10.10.2026).

Vor Teil B stellte die 12er-Karte von congstar den Sieger der 24-Monats-Tafel,
Δ rechnete gegen die günstigste Vodafone-Karte über alle Laufzeiten, und 1&1
trug „andere Laufzeit“. Jeder Test hier ist gegen diesen Stand rot.
"""

from __future__ import annotations

import csv
import io
import json
import pathlib
import re

import pytest
import yaml
from bestand_pfad import lese_wurzel
from tarifleiter_testbestand import mit_leiter

from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import (
    geraete_export,
    geraete_laufzeit,
    geraete_radar,
    geraete_tco_karten,
    geraete_view,
)
from telco_radar.tco_model import Buendel, buendel_id

HEUTE = "2026-10-06"
GESTERN = "2026-10-05"
MODELL = "apple-iphone-17-pro-256"
SKU = "apple-iphone-17-pro-256gb-schwarz"

TARIFE = (
    ("Vodafone", "vf:xs", "Vodafone Mobil XS", 18, 29.95),
    ("congstar", "cs:s", "Allnet Flat S", 10, 15.0),
    ("o2", "o2:s", "O2 Mobile S", 10, 25.0),
    ("Telekom", "tk:s", "MagentaMobil S", 10, 20.0),
    ("1&1", "11:s", "All-Net-Flat S", 10, 14.99),
)

GETRENNT = (
    ("Vodafone", "vf:xs", 12, 80.0),
    ("Vodafone", "vf:xs", 24, 45.0),
    ("Vodafone", "vf:xs", 36, 31.0),
    ("congstar", "cs:s", 12, 70.0),
    ("congstar", "cs:s", 24, 38.25),
    ("congstar", "cs:s", 36, 26.0),
    ("o2", "o2:s", 24, 40.0),
    ("Telekom", "tk:s", 36, 31.0),
)

SOLL = {
    12: {"congstar": 1201.0, "Vodafone": 1679.8},
    24: {"congstar": 1279.0, "o2": 1561.0, "Vodafone": 1799.8, "1&1": 1411.66},
    36: {"congstar": 1297.0, "Telekom": 1597.0, "Vodafone": 1835.8},
}


def _tarif(anbieter, tid, name, gb, betrag):
    return {
        "anbieter": anbieter,
        "name": name,
        "tarif_id": tid,
        "art": "mobilfunk",
        "grundgebuehr": betrag,
        "laufzeit_monate": 24,
        "datenvolumen_gb": gb,
        "preisphasen": [
            {"von_monat": 1, "bis_monat": 24, "betrag": betrag},
            {"von_monat": 25, "bis_monat": None, "betrag": betrag},
        ],
        "dokument_url": f"https://example.de/pib/{tid}",
        "abgerufen_am": HEUTE,
        "confidence": {},
        "fundstellen": {},
    }


def _name(tid):
    return next(t[2] for t in TARIFE if t[1] == tid)


def _getrennt(anbieter, tid, laufzeit, rate, **kw):
    satz = {
        "id": buendel_id(SKU, anbieter, _name(tid), laufzeit),
        "sku_id": SKU,
        "anbieter": anbieter,
        "tarif_name": _name(tid),
        "tarif_id": tid,
        "tarif_id_guete": "hoch",
        "tarif_monatlich": next(t[4] for t in TARIFE if t[1] == tid),
        "tarif_bindung_monate": 24,
        "geraet_zuzahlung": 1.0,
        "geraet_monatsrate": rate,
        "laufzeit_monate": laufzeit,
        "anschlusspreis": 0.0,
        "zustand": "neu",
        "rabatte": [],
        "quelle_url": f"https://example.de/{anbieter.lower()}/{laufzeit}",
        "abgerufen_am": HEUTE,
        "first_seen": GESTERN,
        "last_verified": HEUTE,
    }
    satz.update(kw)
    return satz


def _vertrag():
    return {
        "id": buendel_id(SKU, "1&1", "All-Net-Flat S", 36),
        "sku_id": SKU,
        "anbieter": "1&1",
        "tarif_name": "All-Net-Flat S",
        "tarif_id": "11:s",
        "tarif_id_guete": "hoch",
        "buendel_monatlich": 42.99,
        "geraet_zuzahlung": 340.0,
        "laufzeit_monate": 36,
        "anschlusspreis": 39.9,
        "zustand": "neu",
        "rabatte": [],
        "quelle_url": "https://example.de/1und1/36",
        "abgerufen_am": HEUTE,
        "first_seen": GESTERN,
        "last_verified": HEUTE,
    }


def bestand(ohne=(), aendern=None) -> list[dict]:
    """Die Bündel des Bestands; `ohne` nimmt (Anbieter, Laufzeit) heraus,
    `aendern` ersetzt Felder einer (Anbieter, Laufzeit)."""
    saetze = [_getrennt(*z) for z in GETRENNT] + [_vertrag()]
    saetze = [s for s in saetze if (s["anbieter"], s["laufzeit_monate"]) not in ohne]
    for (anbieter, laufzeit), felder in (aendern or {}).items():
        for s in saetze:
            if (s["anbieter"], s["laufzeit_monate"]) == (anbieter, laufzeit):
                s.update(felder)
    return saetze


def _listung(anbieter, preis):
    return {
        "id": f"{anbieter.lower()}--{SKU}",
        "sku_id": SKU,
        "device_id": "apple-iphone-17-pro",
        "anbieter": anbieter,
        "anbieter_typ": "netzbetreiber",
        "netz": anbieter,
        "speicher_gb": 256,
        "farbe_roh": "Schwarz",
        "farbe_normalisiert": "schwarz",
        "zustand": "neu",
        "first_seen": GESTERN,
        "last_verified": HEUTE,
        "status": "aktiv",
        "missed_checks": 0,
        "preis_ohne_vertrag": preis,
        "erstpreis": preis,
        "erstpreis_art": "ohne_vertrag",
        "erstpreis_am": GESTERN,
        "quelle_url": f"https://example.de/{anbieter.lower()}/geraet",
        "abgerufen_am": HEUTE,
        "verfuegbarkeit": "lieferbar",
        "confidence": "hoch",
        "einstiege": ["https://example.de/l"],
    }


def baue(tmp_path: pathlib.Path, buendel: list[dict] | None = None):
    """Ein State-Baum mit Katalog, Listungen, Bündeln, Tarifen und zwei
    Messtagen Historie je Bündel. Rückgabe: (root, state)."""
    buendel = bestand() if buendel is None else buendel
    root = tmp_path / "laufzeit"
    (root / "config").mkdir(parents=True)
    konfig = {
        "geraete_katalog.yaml": {
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
        },
        "farben.yaml": {"farben": {"schwarz": ["Schwarz"]}},
        "geraete_quellen.yaml": {
            "anbieter": [
                {
                    "name": "Vodafone",
                    "typ": "netzbetreiber",
                    "rang": 1,
                    "eigen": True,
                    "methode": "ldjson",
                    "basis_url": "https://www.vodafone.de",
                    "einstiege": [{"url": "https://www.vodafone.de/handys"}],
                }
            ]
        },
    }
    for name, daten in konfig.items():
        (root / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
    state = root / "data" / "state"
    state.mkdir(parents=True)
    (state / "geraete_db.json").write_text(
        json.dumps(
            {
                "updated": HEUTE,
                "anbieter": {"Vodafone": {"laeufe": 4, "funde_gesamt": 1}},
                "listungen": [_listung("Vodafone", 1199.0), _listung("o2", 1149.0)],
            }
        ),
        encoding="utf-8",
    )
    (state / "geraete_preise.jsonl").write_text("", encoding="utf-8")
    (state / "geraete_tco.json").write_text(
        json.dumps({"updated": HEUTE, "buendel": buendel, "sim_only": []}),
        encoding="utf-8",
    )
    historie = [
        {
            **{
                k: b.get(k)
                for k in (
                    "id",
                    "sku_id",
                    "tarif_id",
                    "tarif_monatlich",
                    "buendel_monatlich",
                    "geraet_zuzahlung",
                    "geraet_monatsrate",
                    "laufzeit_monate",
                    "anschlusspreis",
                    "quelle_url",
                    "zustand",
                )
            },
            "datum": tag,
            "abgerufen_am": tag,
            "gesamt": 1.0,
        }
        for b in buendel
        for tag in (GESTERN, HEUTE)
    ]
    (state / "geraete_tco_historie.jsonl").write_text(
        "\n".join(json.dumps(z) for z in historie) + "\n", encoding="utf-8"
    )
    tarife = mit_leiter([_tarif(*t) for t in TARIFE], HEUTE)
    (state / "tarife.jsonl").write_text(
        "\n".join(json.dumps(t) for t in tarife) + "\n", encoding="utf-8"
    )
    return root, state


def ansicht(tmp_path, buendel=None) -> dict:
    """`geraete_view.aufbereiten` am gebauten Bestand (tco, zeitreihe, radar)."""
    root, state = baue(tmp_path, buendel)
    return geraete_view.aufbereiten(
        state, lade_quellen(root), lade_katalog(root), heute=HEUTE
    )


@pytest.fixture(scope="module")
def g(tmp_path_factory):
    return ansicht(tmp_path_factory.mktemp("lz"))


def _paar(g, laufzeit, band="xs"):
    treffer = [
        p
        for p in g["zeitreihe"]["paare"]
        if p["modell"] == MODELL and p["band"] == band and p["laufzeit"] == laufzeit
    ]
    assert len(treffer) == 1, [
        (p["modell"], p["band"], p.get("laufzeit")) for p in g["zeitreihe"]["paare"]
    ]
    return treffer[0]


def _text(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html or "").split())


def _euro(betrag: float) -> str:
    return f"{betrag:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def _karten(g):
    modell = next(m for m in g["tco"]["modelle"] if m["id"] == MODELL)
    return modell, [k for k in modell["karten"] if k.get("sku_id")]


def _karte(g, anbieter, laufzeit):
    _m, karten = _karten(g)
    return next(
        k
        for k in karten
        if k["anbieter"] == anbieter and geraete_laufzeit.ansicht(k) == laufzeit
    )


def test_die_rechnung_der_fixture_stimmt(g):
    """Gegenprobe der Erwartungen: jede Karte trägt die Zahl aus dem Modulkopf."""
    for laufzeit, soll in SOLL.items():
        for anbieter, betrag in soll.items():
            k = _karte(g, anbieter, laufzeit)
            assert k["gesamt"] == betrag, (anbieter, laufzeit, k["gesamt"])
            assert k["leitzahl_monate"] == max(laufzeit, 24)


@pytest.mark.parametrize("laufzeit", [12, 24, 36])
def test_der_sieger_jeder_ansicht_hat_ihre_ratenlaufzeit(g, laufzeit):
    """Der Sieger der 24er-Ansicht hat 24 Raten - nicht die billigere 12er-Karte."""
    paar = _paar(g, laufzeit)
    sieger_anbieter, sieger_betrag = min(SOLL[laufzeit].items(), key=lambda p: p[1])
    antwort = _text(paar["antwort_html"])
    assert f"ist {sieger_anbieter} am günstigsten: {_euro(sieger_betrag)} €" in (
        antwort
    ), antwort
    for andere, soll in SOLL.items():
        if andere != laufzeit:
            fremd = min(soll.values())
            assert f"{_euro(fremd)} €" not in antwort, (laufzeit, andere, antwort)


def test_ein_36_raten_buendel_steht_nicht_in_der_24er_ansicht(g):
    """Telekom führt nur 36 Raten: in der 24er-Ansicht keine Zahl von Telekom,
    in der 36er-Ansicht steht sie."""
    vierundzwanzig = _paar(g, 24)
    assert "1.597,00" not in vierundzwanzig["antwort_html"]
    assert _rund(1597.0) not in vierundzwanzig["svg_breit"]
    assert "Telekom" not in vierundzwanzig["anbieter"]
    sechsunddreissig = _paar(g, 36)
    assert "Telekom" in sechsunddreissig["anbieter"]
    assert _rund(1597.0) in sechsunddreissig["svg_breit"]


def test_1und1_wird_ueber_24_monate_gegen_vodafone_24_verglichen():
    """?laufzeit=36: Telekom trägt Δ gegen die Vodafone-Karte mit 36 Raten im selben
    Band (1.597,00 − 1.835,80 = −238,80). 1&1 wird nur über 24 Monate verglichen:
    Δ gegen Vodafone mit 24 Raten (1.411,66 − 1.799,80 = −388,14)."""
    k = _karte_aus(bestand(), "Telekom", 36)
    assert k["delta"] is not None, k["delta_zustand"]
    assert k["delta"]["betrag"] == round(1597.0 - 1835.8, 2)
    assert k["delta_zustand"] is None
    eins = _karte_aus(bestand(), "1&1", 24)
    assert eins["delta_zustand"] is None, eins["delta_zustand"]
    assert eins["delta"]["betrag"] == round(1411.66 - 1799.8, 2)
    assert eins["leitzahl_monate"] == 24
    cs12 = _karte_aus(bestand(), "congstar", 12)
    assert cs12["delta"]["betrag"] == round(1201.0 - 1679.8, 2)


def test_ohne_vodafone_36_ist_das_delta_eine_benannte_luecke():
    """Gegenprobe: ohne Vodafone-36er „Vodafone nicht erfasst“, mit einer
    36er-Karte ohne vollständige Zahl „Vodafone ohne Zahl“ - nie ein Δ gegen die
    24er-Karte."""
    ohne = _karte_aus(bestand(ohne={("Vodafone", 36)}), "Telekom", 36)
    assert ohne["delta"] is None
    assert ohne["delta_zustand"]["kurz"] == "Vodafone nicht erfasst"
    assert "36 Raten" in ohne["delta_zustand"]["satz"]
    luecke = _karte_aus(
        bestand(aendern={("Vodafone", 36): {"anschlusspreis": None}}), "Telekom", 36
    )
    assert luecke["delta"] is None
    assert luecke["delta_zustand"]["kurz"] == "Vodafone ohne Zahl"


def _karte_aus(buendel, anbieter, laufzeit):
    """Die Karte aus `modelle()` am echten Katalog, ohne Seite."""
    felder = set(Buendel.__dataclass_fields__)
    objekte = [Buendel(**{k: v for k, v in b.items() if k in felder}) for b in buendel]
    tarife = {t["tarif_id"]: t for t in mit_leiter([_tarif(*t) for t in TARIFE], HEUTE)}
    ergebnis = geraete_tco_karten.modelle(
        objekte,
        [_listung("Vodafone", 1199.0)],
        [],
        tarife,
        lade_katalog(lese_wurzel()),
        heute=HEUTE,
    )
    modell = next(m for m in ergebnis["modelle"] if m["id"] == MODELL)
    return next(
        k
        for k in modell["karten"]
        if k["anbieter"] == anbieter and geraete_laufzeit.ansicht(k) == laufzeit
    )


def test_gleicher_horizont_prueft_die_ratenlaufzeit(g):
    """12 und 24 Raten rechnen beide 24 Monate - verglichen werden sie trotzdem
    nicht: das Tor fragt Ratenlaufzeit UND Zeitraum."""
    cs12 = _karte(g, "congstar", 12)
    vf24 = _karte(g, "Vodafone", 24)
    ref = geraete_tco_karten._referenz_aus_buendel(vf24)
    assert cs12["leitzahl_monate"] == ref["monate"] == 24
    assert geraete_tco_karten.gleicher_horizont(cs12, ref) is False
    assert geraete_tco_karten._delta(cs12, ref) is None
    cs24 = _karte(g, "congstar", 24)
    assert geraete_tco_karten.gleicher_horizont(cs24, ref) is True


@pytest.mark.parametrize("laufzeit", [12, 24, 36])
def test_antwortsatz_und_grafikachse_nennen_die_laufzeit(g, laufzeit):
    paar = _paar(g, laufzeit)
    h = max(laufzeit, 24)
    antwort = _text(paar["antwort_html"])
    assert f"mit {laufzeit} Raten" in antwort, antwort
    assert f"Kosten über {h} Monate" in antwort, antwort
    assert f"Kosten über {h} Monate · {laufzeit} Raten" in paar["svg_breit"]
    assert f"{laufzeit} Raten" in paar["graph_beschriftung"]


def test_telekom_ist_in_der_24er_ansicht_nicht_erfasst(g):
    """Telekom führt nur 36 Raten: in der 24er-Ansicht steht sie benannt als
    „nicht erfasst“ - nicht als „andere Laufzeit“ und nicht stumm. 1&1 steht
    unter 24 mit Zahl und unter 36 mit seinem Grund."""

    def zustand(laufzeit: int) -> dict:
        return {f["anbieter"]: f["kurz"] for f in _paar(g, laufzeit)["fehlen"]}

    vier = zustand(24)
    assert vier["Telekom"].startswith("Mit 24 Raten nicht erfasst"), vier
    assert "1&1" not in vier, vier
    assert not any("andere Laufzeit" in k for k in vier.values()), vier
    zwoelf = zustand(12)
    assert zwoelf["o2"].startswith("Mit 12 Raten nicht erfasst"), zwoelf
    sechsunddreissig = zustand(36)
    assert "Telekom" not in sechsunddreissig, sechsunddreissig
    assert sechsunddreissig["1&1"] == "Nur über 24 Monate verglichen"


def test_spanne_und_kacheln_je_laufzeit(g):
    modell, _ = _karten(g)
    assert modell["spanne_je_laufzeit"] == {
        lz: [min(s.values()), max(s.values())] for lz, s in SOLL.items()
    }
    kachel = next(k for k in g["zeitreihe"]["kacheln"] if k["id"] == MODELL)
    for laufzeit, soll in SOLL.items():
        eintrag = kachel["baender"]["xs"][laufzeit]
        assert eintrag["ab"] == f"{_euro(min(soll.values()))} €", (laufzeit, eintrag)


def _rund(betrag: float) -> str:
    """Das Endetikett einer Linie: volle Euro, wie der Graph es setzt."""
    return f"{betrag:,.0f}".replace(",", ".") + " €"


def test_die_grafik_traegt_je_ansicht_nur_ihre_linien(g):
    for laufzeit, soll in SOLL.items():
        paar = _paar(g, laufzeit)
        assert sorted(paar["anbieter"]) == sorted(soll), (laufzeit, paar["anbieter"])
        for betrag in soll.values():
            assert _rund(betrag) in paar["svg_breit"], (laufzeit, betrag)


def test_der_rechenweg_einer_ansicht_kennt_nur_ihre_messungen(g):
    for laufzeit in SOLL:
        rechenweg = _paar(g, laufzeit)["rechenweg_html"]
        raten = set(re.findall(r"Geräterate\s+(\d+) ×", _text(rechenweg)))
        assert raten == {str(laufzeit)}, (laufzeit, raten)


def test_der_export_gruppiert_zuerst_nach_ratenlaufzeit(g):
    text, _n = geraete_export.tco_csv(g["tco"]["export"])
    zeilen = [
        z
        for z in csv.DictReader(io.StringIO(text.lstrip("﻿")), delimiter=";")
        if z["Art"] == "Bündel"
    ]
    folge = [int(z["Laufzeit Monate"]) for z in zeilen]
    assert folge == sorted(folge), folge
    assert set(folge) == {12, 24, 36}


def test_der_wettbewerbsradar_vergleicht_je_laufzeit(g):
    gruppen = geraete_radar.netzbetreiber_gruppen(
        g["tco"]["modelle"], g["tco"]["band_je_tarif"]
    )
    gruppe = next(x for x in gruppen if x["id"] == MODELL)
    paare = {
        (z["anbieter"], z["laufzeit"]): z
        for z in gruppe["zeilen"]
        if z["status"] == geraete_radar.STATUS_VERGLEICHBAR
    }
    telekom = paare[("Telekom", 36)]
    assert telekom["vf_gesamt"] == 1835.8
    assert telekom["prozent"] == round((1597.0 - 1835.8) / 1835.8 * 100, 1)
    assert ("1&1", 36) not in paare
    assert paare[("1&1", 24)]["vf_gesamt"] == 1799.8
    assert paares_vf(paare, 24) == {1799.8}
    assert paares_vf(paare, 12) == {1679.8}


def paares_vf(paare: dict, laufzeit: int) -> set:
    return {z["vf_gesamt"] for (_a, lz), z in paare.items() if lz == laufzeit}


def _nur_im_buendel(tmp_path, buendel: list[dict]) -> dict:
    """Die Katalogzeile des Modells, wenn kein Laden es ohne Vertrag verkauft."""
    root, state = baue(tmp_path, buendel)
    db = json.loads((state / "geraete_db.json").read_text("utf-8"))
    for e in db["listungen"]:
        e["preis_ohne_vertrag"] = None
        e["erstpreis"] = None
    (state / "geraete_db.json").write_text(json.dumps(db), "utf-8")
    g = geraete_view.aufbereiten(
        state, lade_quellen(root), lade_katalog(root), heute=HEUTE
    )
    zeile = next(m for m in g["katalog_modelle"] if m["schluessel"] == MODELL)
    assert zeile["nur_buendel"], zeile
    return zeile


def test_der_katalog_nennt_den_monatsbetrag_der_standardansicht(tmp_path):
    """Prüfrunde DK23: „nur im Bündel, ab X €/Monat bei Y“ vergleicht nur Bündel
    mit 24 Raten. Vodafone mit 36 Raten (29,95 + 31,00 = 60,95 €) ist billiger je
    Monat als o2 mit 24 (25,00 + 40,00 = 65,00 €), aber mit 24 Raten ist o2
    günstiger als Vodafone (29,95 + 45,00 = 74,95 €). Vorher: 60,95 bei
    Vodafone, ohne Raten."""
    buendel = [s for s in bestand() if s["anbieter"] in ("Vodafone", "o2")]
    zeile = _nur_im_buendel(tmp_path, buendel)
    assert (
        zeile["buendel_anbieter"],
        zeile["buendel_monat"],
        zeile["buendel_raten"],
    ) == ("o2", 65.0, 24)


def test_ohne_24er_nennt_der_katalog_die_raten_des_gezeigten_buendels(tmp_path):
    """Gegenprobe: ohne Bündel mit 24 Raten vergleicht die Zeile innerhalb der
    kürzesten vorhandenen Ratenlaufzeit und nennt sie. o2 führt hier 12 Raten
    (25,00 + 50,00 = 75,00 €) gegen Vodafone 12 Raten (29,95 + 80,00 =
    109,95 €); Vodafones 36er (60,95 €) wäre der kleinere Monatsbetrag, aber
    aus einer anderen Laufzeit."""
    o2_zwoelf = {
        "laufzeit_monate": 12,
        "geraet_monatsrate": 50.0,
        "id": buendel_id(SKU, "o2", "O2 Mobile S", 12),
    }
    buendel = [
        s
        for s in bestand(aendern={("o2", 24): o2_zwoelf})
        if s["anbieter"] in ("Vodafone", "o2") and s["laufzeit_monate"] != 24
    ]
    assert sorted((s["anbieter"], s["laufzeit_monate"]) for s in buendel) == [
        ("Vodafone", 12),
        ("Vodafone", 36),
        ("o2", 12),
    ]
    zeile = _nur_im_buendel(tmp_path, buendel)
    assert (
        zeile["buendel_anbieter"],
        zeile["buendel_monat"],
        zeile["buendel_raten"],
    ) == ("o2", 75.0, 12)
