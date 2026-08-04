"""Zweistufige Redaktion (Auftrag Skalierung 3.2).

Der Punkt des Umbaus ist eine einzige Zahl: die Eingabe der Chefredaktion
haengt an der Zahl der BEREICHE, nicht an der Zahl der Meldungen. Bei 1000
Quellen waeren es sonst ~650 bewertete Meldungen in einem Aufruf - formal
im Kontextfenster, inhaltlich Brei, und ein einziger Fehlschlag kostet den
ganzen Wochenbericht.

Die Tests sichern genau das ab, dazu die Montage und den Notfallweg.
"""
from __future__ import annotations

import json
import threading

from telco_radar.analyze import editor

CHEF = """## Auf einen Blick
- Punkt eins

## Das Wichtigste
Vier Saetze zur Lage.

## Die wichtigsten Signale
**Telekom - Titel** (Netz, Dringlichkeit 4/5)
Detail. [Quelle](https://example.com/a)

## Muster der Woche
Ein Muster.
"""


def _regional(bereiche: dict[str, int]) -> dict:
    """{Bereichsname: Zahl der bewerteten Meldungen}."""
    return {
        name: {
            "region_summary": f"Analystenlage {name}.",
            "highlights": [
                {"title": f"{name} Meldung {i}", "operator": f"Firma{i}",
                 "url": f"https://example.com/{name}/{i}",
                 "relevance": 5 - (i % 4), "summary": "Es passierte etwas.",
                 "why_it_matters": "Deshalb."}
                for i in range(n)
            ],
        }
        for name, n in bereiche.items()
    }


def _bereichsantwort(bereich: str, abschnitt: str | None = None) -> str:
    """Die vier Bloecke, wie ein Bereichsredakteur sie liefert."""
    top = json.dumps([{"title": f"{bereich} Meldung 0", "operator": "Firma0",
                       "url": f"https://example.com/{bereich}/0",
                       "relevance": 5, "warum": "stark"}], ensure_ascii=False)
    return (f"===KURZFASSUNG===\nKurzfassung {bereich}.\n"
            f"===ABSCHNITT===\n"
            f"{abschnitt or f'Abschnitt {bereich}. [Quelle](https://example.com/q)'}\n"
            f"===TOP===\n{top}\n"
            f"===THEMEN===\n[\"{bereich}: Thema\"]\n")


def _aufrufe(monkeypatch, chef: str = CHEF) -> list[dict]:
    """Zeichnet jeden LLM-Aufruf mit Stufe, Modell und Nutzlast auf."""
    protokoll: list[dict] = []
    sperre = threading.Lock()

    def fake_complete(system, user, model, max_tokens=5000):
        ist_bereich = system.startswith("You are the section editor")
        with sperre:
            protokoll.append({"stufe": 1 if ist_bereich else 2,
                              "system": system, "user": user, "model": model,
                              "max_tokens": max_tokens})
        if ist_bereich:
            bereich = system.split('"')[1]
            return _bereichsantwort(bereich)
        return chef

    monkeypatch.setattr(editor, "complete", fake_complete)
    return protokoll


# ------------------------------------------------------- die zentrale Zahl

def test_chefredaktion_sieht_die_rohliste_nicht(monkeypatch):
    protokoll = _aufrufe(monkeypatch)
    editor.synthesize(_regional({"Europa": 40, "Asien": 30}), [], model="chef")

    chef = next(a for a in protokoll if a["stufe"] == 2)
    nutzlast = json.loads(chef["user"])
    assert set(nutzlast) <= {"bereiche", "already_covered_topics", "note"}
    assert [b["bereich"] for b in nutzlast["bereiche"]] == ["Europa", "Asien"]
    for b in nutzlast["bereiche"]:
        assert set(b) == {"bereich", "art", "kurzfassung",
                          "staerkste_meldungen"}
        assert len(b["staerkste_meldungen"]) <= editor.TOP_JE_BEREICH
    # 70 bewertete Meldungen, aber keine einzige davon im Chef-Prompt
    assert "Meldung 12" not in chef["user"]


def test_chef_prompt_waechst_mit_bereichen_nicht_mit_meldungen(monkeypatch):
    protokoll = _aufrufe(monkeypatch)

    editor.synthesize(_regional({"Europa": 5}), [], model="chef")
    klein = len(next(a for a in protokoll if a["stufe"] == 2)["user"])

    protokoll.clear()
    editor.synthesize(_regional({"Europa": 200}), [], model="chef")
    gross = len(next(a for a in protokoll if a["stufe"] == 2)["user"])

    assert gross == klein, "die Chefredaktion haengt noch an der Meldungszahl"


def test_ein_aufruf_je_bereich_mit_inhalt(monkeypatch):
    protokoll = _aufrufe(monkeypatch)
    regional = _regional({"Europa": 3, "Asien": 2})
    regional["Leer"] = {"region_summary": "", "highlights": []}

    editor.synthesize(regional, [], model="chef")

    bereiche = [a for a in protokoll if a["stufe"] == 1]
    assert len(bereiche) == 2, "ein leerer Bereich kostet einen Aufruf"
    assert len([a for a in protokoll if a["stufe"] == 2]) == 1


def test_bereichsredakteure_laufen_parallel(monkeypatch):
    gleichzeitig, hoechststand = 0, 0
    sperre = threading.Lock()

    def fake_complete(system, user, model, max_tokens=5000):
        nonlocal gleichzeitig, hoechststand
        if not system.startswith("You are the section editor"):
            return CHEF
        with sperre:
            gleichzeitig += 1
            hoechststand = max(hoechststand, gleichzeitig)
        threading.Event().wait(0.03)
        with sperre:
            gleichzeitig -= 1
        return _bereichsantwort(system.split('"')[1])

    monkeypatch.setattr(editor, "complete", fake_complete)
    editor.synthesize(_regional({f"B{i}": 2 for i in range(6)}), [],
                      model="chef", bereichs_workers=6)

    assert hoechststand >= 3, f"nur {hoechststand} Redakteure gleichzeitig"


def test_die_beiden_stufen_koennen_verschiedene_modelle_nutzen(monkeypatch):
    """Mengenarbeit auf dem guenstigen, Synthese auf dem teuren Modell."""
    protokoll = _aufrufe(monkeypatch)
    editor.synthesize(_regional({"Europa": 3}), [], model="teuer",
                      bereichs_model="guenstig")

    assert {a["model"] for a in protokoll if a["stufe"] == 1} == {"guenstig"}
    assert {a["model"] for a in protokoll if a["stufe"] == 2} == {"teuer"}


def test_ohne_eigenes_bereichsmodell_bleibt_es_bei_einem(monkeypatch):
    protokoll = _aufrufe(monkeypatch)
    editor.synthesize(_regional({"Europa": 3}), [], model="m")
    assert {a["model"] for a in protokoll} == {"m"}


# ------------------------------------------------------------- Montage

def test_bereiche_stehen_zwischen_signalen_und_mustern(monkeypatch):
    _aufrufe(monkeypatch)
    bericht, _ = editor.synthesize(_regional({"Europa": 2, "Asien": 2}), [],
                                   model="m")

    assert bericht.index("## Die wichtigsten Signale") \
        < bericht.index("## Europa") < bericht.index("## Muster der Woche")
    assert "Abschnitt Europa" in bericht and "Abschnitt Asien" in bericht
    # Die Chefredaktion schreibt die Bereichsabschnitte NICHT selbst -
    # sie werden montiert, nicht neu geschrieben.
    assert bericht.count("## Europa") == 1


def test_ohne_muster_ueberschrift_haengen_die_bereiche_hinten_an(monkeypatch):
    """Kein Textverlust, wenn die Chefredaktion die Marke nicht setzt."""
    _aufrufe(monkeypatch, chef="## Auf einen Blick\n- x\n")
    montiert = editor._montiere("## Auf einen Blick\n- x\n",
                                [("Europa", "Text")], [])
    assert "## Europa" in montiert and montiert.endswith("Text\n")


def test_themen_aus_beiden_stufen_landen_im_gedaechtnis(monkeypatch):
    _aufrufe(monkeypatch, chef=CHEF + "\n===TOPICS===\n[\"Chef: Thema\"]")
    _, themen = editor.synthesize(_regional({"Europa": 2, "Asien": 2}), [],
                                  model="m")

    assert "Chef: Thema" in themen
    assert "Europa: Thema" in themen and "Asien: Thema" in themen


def test_doppelte_themen_werden_zusammengefasst(monkeypatch):
    _aufrufe(monkeypatch, chef=CHEF + "\n===TOPICS===\n[\"Europa: Thema\"]")
    _, themen = editor.synthesize(_regional({"Europa": 2}), [], model="m")
    assert themen.count("Europa: Thema") == 1


# ------------------------------------------------------------ Notfallweg

def test_ausgefallener_bereichsredakteur_verliert_keine_meldung(monkeypatch):
    """Ein Bereich darf nie stumm verschwinden: der Seen-Store hat seine
    Meldungen bereits als erledigt vermerkt, sie kommen kein zweites Mal."""
    def fake_complete(system, user, model, max_tokens=5000):
        if system.startswith("You are the section editor"):
            if "Asien" in system:
                raise RuntimeError("Anbieter ueberlastet")
            return _bereichsantwort("Europa")
        return CHEF

    monkeypatch.setattr(editor, "complete", fake_complete)
    bericht, themen = editor.synthesize(
        _regional({"Europa": 2, "Asien": 3}), [], model="m")

    assert "## Asien" in bericht
    for i in range(3):
        assert f"https://example.com/Asien/{i}" in bericht
    assert "ohne redaktionelle Verdichtung" in bericht
    assert any("Asien Meldung" in t for t in themen)


def test_unbrauchbare_antwort_gilt_als_ausfall(monkeypatch):
    def fake_complete(system, user, model, max_tokens=5000):
        if system.startswith("You are the section editor"):
            return "===KURZFASSUNG===\nda\n===ABSCHNITT===\n   \n"
        return CHEF

    monkeypatch.setattr(editor, "complete", fake_complete)
    bericht, _ = editor.synthesize(_regional({"Europa": 2}), [], model="m")

    assert "ohne redaktionelle Verdichtung" in bericht
    assert "https://example.com/Europa/0" in bericht


def test_notabschnitt_haelt_die_reihenfolge_nach_relevanz():
    daten = {"region_summary": "Lage.", "highlights": [
        {"title": "Schwach", "url": "https://x/1", "relevance": 2,
         "operator": "A", "summary": "s"},
        {"title": "Stark", "url": "https://x/2", "relevance": 5,
         "operator": "B", "summary": "s"}]}

    ergebnis = editor._notabschnitt("Europa", daten)

    assert ergebnis["_notfall"] is True
    assert ergebnis["abschnitt"].index("Stark") \
        < ergebnis["abschnitt"].index("Schwach")
    assert ergebnis["top"][0]["title"] == "Stark"
    assert ergebnis["kurzfassung"] == "Lage."


def test_leerer_lauf_bleibt_ohne_bereichsaufruf(monkeypatch):
    protokoll = _aufrufe(monkeypatch)
    editor.synthesize({}, [], model="m")
    assert [a["stufe"] for a in protokoll] == [2]


def test_ueberschriften_im_bereichsabschnitt_bleiben_unter_ihrer_klammer(monkeypatch):
    """Der Prompt verlangt einen Abschnitt ohne Ueberschrift - ein Modell
    setzt trotzdem gelegentlich eine, und als H2 zerlegte sie die
    Gliederung des ganzen Berichts."""
    def fake_complete(system, user, model, max_tokens=5000):
        if system.startswith("You are the section editor"):
            return _bereichsantwort(
                "X", "## Eigenmaechtige Ueberschrift\nText dazu.")
        return CHEF

    monkeypatch.setattr(editor, "complete", fake_complete)
    bericht, _ = editor.synthesize(
        _regional({"Europa": 2, "KI-Anbieter": 2}), [], model="m",
        themenbereiche=["KI-Anbieter"])

    ebenen = {z.split(" ")[0] for z in bericht.splitlines()
              if z.endswith("Eigenmaechtige Ueberschrift")}
    assert ebenen == {"###", "####"}, ebenen   # unter Region bzw. Themenfeld
    editor.validate_editorial_briefing(
        bericht, frozenset({editor.THEMEN_UEBERSCHRIFT}))
