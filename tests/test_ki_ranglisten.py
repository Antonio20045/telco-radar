"""Das Band „Modelle“ auf ki.html (Pitch 9, Schnitt 6).

Die Parser lesen echte Abrufe vom 11.10.2026 (``tests/fixtures/ki/``): Artificial
Analysis als Tabelle mit Intelligence Index, Arena als ld+json-Liste. Gezählt
werden nur Modelle aus ``config/ki_modelle.yaml``, die in beiden Listen stehen;
der Platz ist das Mittel der beiden Plätze innerhalb dieser Menge. Gegenproben:
ein Modell nur in einer Liste fällt heraus, eine fehlende Liste steht als
Ausfall auf der Seite, und die Seite zeigt, was im Store steht. Feste Tage.
"""

from __future__ import annotations

import gzip
import json
import re
from datetime import date
from pathlib import Path

import httpx
from bestand_pfad import verlinke_neben_data

from telco_radar import zusatzstufen
from telco_radar.analyze import ki_modelle
from telco_radar.analyze.takt import Takt
from telco_radar.collect import http, ki_ranglisten
from telco_radar.config import load_config
from telco_radar.report.html import render_site

WURZEL = Path(__file__).resolve().parents[1]
FIXTURES = WURZEL / "tests" / "fixtures" / "ki"
GESTERN = date(2026, 10, 10)
HEUTE = date(2026, 10, 11)
AA_URL = "https://artificialanalysis.ai/leaderboards/models"
ARENA_URL = "https://arena.ai/leaderboard/text"
ERWARTET = [
    ("Claude Opus 5.5", 1.0, 2),
    ("Gemini 4 Argon", 4.0, 1),
    ("Claude Fable 5.1", 4.0, 3),
    ("Claude Sonnet 5.5", 2.0, 8),
    ("GPT-6.1 Sol", 6.0, 6),
    ("Muse Spark 1.3", 7.0, 5),
    ("GPT-6 Astra", 4.0, 9),
    ("Gemini 3.8 Flash", 11.0, 4),
    ("Qwen3.8 Max", 9.0, 7),
    ("Grok 4.7", 8.0, 13),
]


def _aa() -> list[dict]:
    roh = gzip.decompress((FIXTURES / "aa_tabelle.html.gz").read_bytes())
    return ki_ranglisten.aa_index(roh.decode("utf-8"))


def _arena() -> list[dict]:
    text = (FIXTURES / "arena_ldjson.html").read_text(encoding="utf-8")
    return ki_ranglisten.arena_plaetze(text)


def _abruf(aa=None, arena=None) -> dict:
    def _quelle(url, eintraege):
        if eintraege is None:
            return {"url": url, "error": "ConnectError: Verbindung abgelehnt"}
        return {"url": url, "eintraege": eintraege}

    return {"aa": _quelle(AA_URL, aa), "arena": _quelle(ARENA_URL, arena)}


def test_parser_lesen_platz_und_index_aus_den_echten_abrufen():
    aa = _aa()
    assert {"name": "Claude Opus 5.5 (max with fallback)", "index": 58.0} in aa
    assert {"name": "Qwen3.8 Max (0902)", "index": 45.0} in aa
    assert not any(z["name"] == "Model" for z in aa)
    arena = _arena()
    assert len(arena) == 414
    assert arena[0] == {"platz": 1, "name": "gemini-4-argon-high"}
    assert {"platz": 90, "name": "grok-4.7-xhigh"} in arena


def test_abruf_fragt_robots_und_laesst_gesperrte_seiten_aus(monkeypatch):
    aa_seite = gzip.decompress((FIXTURES / "aa_tabelle.html.gz").read_bytes())
    seiten = {
        "https://artificialanalysis.ai/robots.txt": b"User-Agent: *\nAllow: /\n",
        "https://arena.ai/robots.txt": b"User-Agent: *\nDisallow: /leaderboard\n",
        AA_URL: aa_seite,
    }
    gefragt: list[str] = []

    def antworte(anfrage: httpx.Request) -> httpx.Response:
        gefragt.append(str(anfrage.url))
        assert anfrage.headers["user-agent"] == http.BOT_UA
        return httpx.Response(200, content=seiten[str(anfrage.url)])

    monkeypatch.setattr(http, "TRANSPORT", httpx.MockTransport(antworte))
    abruf = ki_ranglisten.abrufen({"timeout_seconds": 5})
    assert abruf["aa"]["eintraege"][0]["index"] == 58.0
    assert "error" not in abruf["aa"]
    assert abruf["arena"]["error"].startswith("robots.txt sperrt")
    assert ARENA_URL not in gefragt


def test_zusatzstufe_schreibt_den_store_nur_mit_schalter(tmp_path, monkeypatch):
    seiten = {
        "https://artificialanalysis.ai/robots.txt": b"",
        "https://arena.ai/robots.txt": b"",
        AA_URL: gzip.decompress((FIXTURES / "aa_tabelle.html.gz").read_bytes()),
        ARENA_URL: (FIXTURES / "arena_ldjson.html").read_bytes(),
    }

    def antwort(anfrage: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=seiten[str(anfrage.url)])

    monkeypatch.setattr(http, "TRANSPORT", httpx.MockTransport(antwort))
    verlinke_neben_data(tmp_path)
    takt = Takt(lambda: 0.0, lambda *_: None, lambda f, ausfall: f())
    cfg = load_config(tmp_path)
    cfg.settings["ki_ranglisten_aktiv"] = False
    zusatzstufen._ki_ranglisten(cfg, tmp_path, GESTERN, takt)
    assert ki_modelle.lade(tmp_path / "data" / "state")["stand"] is None
    cfg.settings["ki_ranglisten_aktiv"] = True
    zusatzstufen._ki_ranglisten(cfg, tmp_path, HEUTE, takt)
    store = ki_modelle.lade(tmp_path / "data" / "state")
    assert [m["name"] for m in store["top"]] == [n for n, _, _ in ERWARTET]
    assert store["stand"] == HEUTE.isoformat()
    cfg.settings["ki_ranglisten_aktiv"] = False
    zusatzstufen._ki_ranglisten(cfg, tmp_path, GESTERN, takt)
    assert ki_modelle.lade(tmp_path / "data" / "state")["stand"] == HEUTE.isoformat()


def test_mittel_der_plaetze_ergibt_die_reihenfolge():
    top = ki_modelle.rangliste(ki_modelle.katalog(WURZEL), _aa(), _arena())
    assert [(m["name"], m["aa_platz"], m["arena_platz"]) for m in top] == ERWARTET
    assert [m["platz"] for m in top] == list(range(1, 11))
    assert top[0]["farbe"] == "--ki-anthropic"
    assert top[1]["farbe"] == "--ki-google"


def test_gleichstand_im_mittel_entscheidet_der_aa_index():
    modelle = [
        {"name": n, "kurz": n, "firma": "Meta", "aa": [n], "arena": [n.lower()]}
        for n in ("Eins", "Zwei", "Drei")
    ]
    aa = [{"name": "Eins", "index": 50.0}, {"name": "Zwei (max)", "index": 40.0}]
    aa.append({"name": "Drei", "index": 30.0})
    arena = [{"platz": 7, "name": "drei"}, {"platz": 8, "name": "zwei"}]
    arena.append({"platz": 9, "name": "eins"})
    top = ki_modelle.rangliste(modelle, aa, arena)
    assert [(m["name"], m["mittel"]) for m in top] == [
        ("Eins", 2.0),
        ("Zwei", 2.0),
        ("Drei", 2.0),
    ]


def test_gegenprobe_modell_nur_in_einer_liste_faellt_heraus():
    modelle = ki_modelle.katalog(WURZEL)
    aa = _aa()
    assert any(z["name"].startswith("Claude Haiku 5.5") for z in aa)
    top = ki_modelle.rangliste(modelle, aa, _arena())
    assert "Claude Haiku 5.5" not in [m["name"] for m in top]
    ohne_argon = [z for z in _arena() if z["name"] != "gemini-4-argon-high"]
    top = ki_modelle.rangliste(modelle, aa, ohne_argon)
    namen = [m["name"] for m in top]
    assert "Gemini 4 Argon" not in namen
    assert namen[:2] == ["Claude Opus 5.5", "Claude Fable 5.1"]
    assert top[0]["arena_platz"] == 1


def test_ausfall_einer_liste_behaelt_den_vortag_und_nennt_den_fehler(tmp_path):
    modelle = ki_modelle.katalog(WURZEL)
    ki_modelle.aktualisiere(tmp_path, modelle, _abruf(_aa(), _arena()), GESTERN)
    store = ki_modelle.aktualisiere(tmp_path, modelle, _abruf(_aa(), None), HEUTE)
    assert store["stand"] == GESTERN.isoformat()
    assert store["top"][0]["name"] == "Claude Opus 5.5"
    assert store["quellen"]["arena"]["error"].startswith("ConnectError")
    assert store["quellen"]["arena"]["versucht"] == HEUTE.isoformat()
    assert store["quellen"]["arena"]["abgerufen"] == GESTERN.isoformat()
    assert store["quellen"]["aa"]["error"] is None
    assert ki_modelle.lade(tmp_path) == store


def _ki_seite(tmp_path, store: dict | None) -> str:
    root = tmp_path / "repo"
    berichte = root / "data" / "reports"
    berichte.mkdir(parents=True)
    verlinke_neben_data(root)
    bericht = {"date": HEUTE.isoformat(), "regions": {}}
    (berichte / f"{HEUTE.isoformat()}.json").write_text(json.dumps(bericht))
    if store is not None:
        pfad = root / "data" / "state" / ki_modelle.STORE_NAME
        pfad.parent.mkdir(parents=True)
        pfad.write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")
    site = tmp_path / "site"
    render_site(site, berichte, load_config(root))
    html = (site / "ki.html").read_text(encoding="utf-8")
    return re.search(r'<section[^>]*id="modelle".*?</section>', html, re.S).group(0)


def _store(tmp_path, abrufe: list[tuple[dict, date]]) -> dict:
    ordner = tmp_path / "state-vorher"
    store: dict = {}
    for abruf, tag in abrufe:
        store = ki_modelle.aktualisiere(ordner, ki_modelle.katalog(WURZEL), abruf, tag)
    return store


def _ansage(band: str) -> str:
    h2 = re.search(r"<h2[^>]*>(.*?)</h2>", band, re.S).group(1)
    return " ".join(re.sub(r"<[^>]+>", " ", h2).split())


def test_band_zeigt_zehn_modelle_und_platz_eins_aus_dem_store(tmp_path):
    store = _store(tmp_path, [(_abruf(_aa(), _arena()), HEUTE)])
    band = _ki_seite(tmp_path, store)
    assert _ansage(band) == "Opus 5.5 ist gerade die stärkste KI ."
    namen = re.findall(r'class="ki-rang-name">([^<]+)<', band)
    assert namen == [name for name, _, _ in ERWARTET]
    assert band.count('class="ki-rang-eintrag"') == 10
    assert "var(--ki-anthropic)" in band
    assert f'href="{AA_URL}"' in band and f'href="{ARENA_URL}"' in band
    assert "11.10.2026" in band
    assert "nicht abrufbar" not in band


def test_gegenprobe_anderer_store_andere_seite(tmp_path):
    anderer = {
        "stand": GESTERN.isoformat(),
        "top": [
            {
                "platz": 1,
                "name": "Testmodell X",
                "kurz": "Modell X",
                "farbe": "--ki-meta",
            },
            {
                "platz": 2,
                "name": "Testmodell Y",
                "kurz": "Modell Y",
                "farbe": "--ki-xai",
            },
        ],
        "quellen": {
            "aa": {"url": AA_URL, "error": None, "abgerufen": GESTERN.isoformat()},
            "arena": {
                "url": ARENA_URL,
                "error": None,
                "abgerufen": GESTERN.isoformat(),
            },
        },
    }
    band = _ki_seite(tmp_path, anderer)
    assert _ansage(band) == "Modell X ist gerade die stärkste KI ."
    assert band.count('class="ki-rang-eintrag"') == 2
    assert "10.10.2026" in band
    assert "Opus" not in band


def test_fehlende_liste_steht_als_ausfall_auf_der_seite(tmp_path):
    store = _store(
        tmp_path,
        [(_abruf(_aa(), _arena()), GESTERN), (_abruf(_aa(), None), HEUTE)],
    )
    band = _ki_seite(tmp_path, store)
    assert "Arena am 11.10.2026 nicht abrufbar" in band
    assert "Stand 10.10.2026" in band
    assert band.count('class="ki-rang-eintrag"') == 10


def test_ohne_jeden_abruf_nennt_das_band_den_ausfall(tmp_path):
    store = _store(tmp_path, [(_abruf(None, None), HEUTE)])
    assert store["top"] == []
    band = _ki_seite(tmp_path, store)
    assert "ki-rang-eintrag" not in band
    assert "Artificial Analysis am 11.10.2026 nicht abrufbar" in band
    assert "Arena am 11.10.2026 nicht abrufbar" in band
    leer = _ki_seite(tmp_path / "ohne-store", None)
    assert "noch nicht abgerufen" in leer
