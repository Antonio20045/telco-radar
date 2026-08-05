"""Zweistufige Redaktion: Bereichsredakteure + Chefredaktion.

Der Bruch, den AUFTRAG_SKALIERUNG_1000.md 3.2 beschreibt: heute sieht der
Editor in EINEM Aufruf alle bewerteten Meldungen, bei 1000 Quellen waeren das
~650. Die zweite Stufe existiert, damit die Eingabe der Chefredaktion an der
Zahl der BEREICHE haengt und nicht an der Zahl der Meldungen. Genau das wird
hier gemessen - zusammen mit den beiden Faellen, die im Betrieb wirklich
vorkommen: ein einzelner Bereich faellt aus, und die Chefredaktion liefert
eine unbrauchbare Gliederung.
"""
from __future__ import annotations

import json

import pytest

from telco_radar.analyze import editor
from telco_radar.analyze.editor import (
    EditorialBriefingError, synthesize_zweistufig, validate_editorial_briefing)
from telco_radar.pipeline import _redaktion_zweistufig


def _highlight(titel: str, betreiber: str, relevanz: int = 4) -> dict:
    return {"title": titel, "operator": betreiber,
            "url": f"https://beispiel.de/{titel.lower().replace(' ', '-')}",
            "category": "Produktlaunch", "relevance": relevanz,
            "summary": f"{betreiber} hat {titel} angekuendigt.",
            "why_it_matters": "Vorlage fuer ein eigenes Angebot."}


def _regional(bereiche: dict[str, int]) -> dict[str, dict]:
    return {
        name: {"region_summary": f"Zusammenfassung {name}.",
               "highlights": [_highlight(f"Meldung {name} {i}", f"Betreiber {i}")
                              for i in range(anzahl)]}
        for name, anzahl in bereiche.items()
    }


BEREICHSANTWORT = """\
{ueberschrift} {bereich}
In {bereich} ging es diese Woche um Tarife. Betreiber 0 hat nachgelegt.

- **Betreiber 0**: hat etwas angekuendigt. [Quelle](https://beispiel.de/a)

===KURZFASSUNG===
{bereich} steht im Zeichen von Tarifen. Betreiber 0 hat nachgelegt.

===TOPICS===
["Betreiber 0: Tarif in {bereich}"]
"""

def _bereichsantwort(user: str) -> str:
    """Antwortet mit der Ueberschriftsebene, die der Auftrag verlangt -
    Themenfelder als H3, Regionen als H2. Ein Fake, der das ignoriert, wuerde
    genau den Montagefehler verdecken, den der Test finden soll."""
    auftrag = json.loads(user)
    return BEREICHSANTWORT.format(
        bereich=auftrag["bereich"],
        ueberschrift="###" if auftrag["ist_themenfeld"] else "##")


CHEFANTWORT = """\
## Auf einen Blick
- Erstens.
- Zweitens.
- Drittens.

## Das Wichtigste
Die Woche stand im Zeichen der Tarife. Betreiber 0 hat in mehreren Maerkten
nachgelegt.

## Die wichtigsten Signale
**Betreiber 0 - Meldung** (Produktlaunch, Dringlichkeit 4/5)
Etwas ist passiert. [Quelle](https://beispiel.de/a)

## Muster der Woche
Mehrere Betreiber buendeln KI-Assistenten in Consumer-Tarife.

===TOPICS===
["Betreiber 0: Tarif"]
"""


@pytest.fixture
def antworten(monkeypatch):
    """Faengt jeden LLM-Aufruf ab und merkt sich, was gefragt wurde."""
    aufrufe: list[dict] = []

    def _complete(system, user, model, max_tokens=None, **kw):
        aufrufe.append({"system": system, "user": user, "model": model,
                        "max_tokens": max_tokens})
        if "You are the chief editor" in system:
            return CHEFANTWORT
        return _bereichsantwort(user)

    monkeypatch.setattr(editor, "complete", _complete)
    return aufrufe


def test_ein_aufruf_je_bereich_plus_chefredaktion(antworten):
    regional = _regional({"Europa": 3, "Asien": 2, "Nordamerika": 1})
    synthesize_zweistufig(regional, [], model="m", workers=3)
    assert len(antworten) == 4  # 3 Bereiche + 1 Chef


def test_chefredaktion_sieht_die_rohliste_nicht(antworten):
    """Der ganze Sinn der zweiten Stufe. Sieht sie doch alles, ist nichts
    gewonnen - dann skaliert die Eingabe wieder mit den Meldungen."""
    regional = _regional({"Europa": 40})
    synthesize_zweistufig(regional, [], model="m")

    chef = [a for a in antworten if "You are the chief editor" in a["system"]][0]
    eingabe = json.loads(chef["user"])
    assert len(eingabe["bereiche"][0]["staerkste_meldungen"]) == 5
    assert "why_it_matters" not in chef["user"]
    assert "Meldung Europa 39" not in chef["user"]


def test_chefeingabe_waechst_mit_bereichen_nicht_mit_meldungen(antworten):
    def chefeingabe(regional):
        antworten.clear()
        synthesize_zweistufig(regional, [], model="m")
        return len([a for a in antworten if "You are the chief editor" in a["system"]][0]["user"])

    klein = chefeingabe(_regional({"Europa": 5}))
    viel_mehr_meldungen = chefeingabe(_regional({"Europa": 60}))
    mehr_bereiche = chefeingabe(_regional({"Europa": 5, "Asien": 5, "Afrika": 5}))

    # zwoelfmal so viele Meldungen, aber die Eingabe waechst hoechstens um die
    # fuenf staerksten je Bereich - Bereiche dagegen schlagen voll durch
    assert viel_mehr_meldungen < klein * 2
    assert mehr_bereiche > klein * 2


def test_bereichsredakteur_bekommt_nur_seinen_bereich(antworten):
    regional = _regional({"Europa": 2, "Asien": 2})
    synthesize_zweistufig(regional, [], model="m")
    europa = [a for a in antworten
              if "You are the chief editor" not in a["system"] and "Europa" in a["system"]][0]
    assert "Meldung Asien" not in europa["user"]


def test_bericht_haelt_die_pflichtgliederung_ein(antworten):
    regional = _regional({"Europa": 2, "Asien": 1})
    markdown, _ = synthesize_zweistufig(regional, [], model="m")
    validate_editorial_briefing(markdown)  # wirft sonst
    for pflicht in ("## Auf einen Blick", "## Das Wichtigste",
                    "## Die wichtigsten Signale", "## Muster der Woche"):
        assert pflicht in markdown


def test_bereichsabschnitte_stehen_vor_den_mustern(antworten):
    """Sonst endet der Bericht mit seinem Fazit, bevor die Belege kommen."""
    regional = _regional({"Europa": 2, "Asien": 1})
    markdown, _ = synthesize_zweistufig(regional, [], model="m")
    assert (markdown.index("## Die wichtigsten Signale")
            < markdown.index("## Europa")
            < markdown.index("## Muster der Woche"))


def test_themenfelder_stehen_gemeinsam_unter_einer_ueberschrift(antworten):
    regional = _regional({"Europa": 2, "KI & Modelle": 2, "Chips & Modems": 1})
    markdown, _ = synthesize_zweistufig(
        regional, [], model="m", themenbereiche=["KI & Modelle", "Chips & Modems"])

    assert "## Technologie, Geräte & Regulierung" in markdown
    # Themenfelder als H3 darunter, Regionen als H2 darueber
    assert "### KI & Modelle" in markdown
    assert "## Europa" in markdown
    assert (markdown.index("## Europa")
            < markdown.index("## Technologie, Geräte & Regulierung")
            < markdown.index("### KI & Modelle"))


def test_ohne_themenfelder_keine_themenueberschrift(antworten):
    markdown, _ = synthesize_zweistufig(_regional({"Europa": 2}), [], model="m")
    assert "Technologie, Geräte & Regulierung" not in markdown


def test_ausgefallener_bereich_kommt_trotzdem_in_den_bericht(monkeypatch):
    """Ein gescheiterter Aufruf darf keinen ganzen Bereich verschwinden lassen:
    die Meldungen sind bewertet, und der Seen-Store merkt sie sich als
    erledigt - sie kaemen nie wieder."""
    def _complete(system, user, model, max_tokens=None, **kw):
        if "You are the chief editor" in system:
            return CHEFANTWORT
        if json.loads(user)["bereich"] == "Asien":
            raise RuntimeError("HTTP 529 overloaded")
        return _bereichsantwort(user)

    monkeypatch.setattr(editor, "complete", _complete)
    markdown, topics = synthesize_zweistufig(
        _regional({"Europa": 2, "Asien": 2}), [], model="m")

    assert "## Asien" in markdown
    assert "nicht redaktionell verdichtet" in markdown
    assert "https://beispiel.de/meldung-asien-0" in markdown
    assert any("Meldung Asien" in t for t in topics)


def test_leere_antwort_eines_bereichs_wird_als_ausfall_behandelt(monkeypatch):
    def _complete(system, user, model, max_tokens=None, **kw):
        if "You are the chief editor" in system:
            return CHEFANTWORT
        return "   "

    monkeypatch.setattr(editor, "complete", _complete)
    markdown, _ = synthesize_zweistufig(_regional({"Europa": 2}), [], model="m")
    assert "## Europa" in markdown
    assert "nicht redaktionell verdichtet" in markdown


def test_chefredaktion_wird_einmal_nachgefasst(monkeypatch):
    versuche = []

    def _complete(system, user, model, max_tokens=None, **kw):
        if "You are the chief editor" not in system:
            return _bereichsantwort(user)
        versuche.append(system)
        if len(versuche) == 1:
            return "## Irgendwas\nText ohne die Pflichtgliederung."
        return CHEFANTWORT

    monkeypatch.setattr(editor, "complete", _complete)
    markdown, _ = synthesize_zweistufig(_regional({"Europa": 2}), [], model="m")
    assert len(versuche) == 2
    assert "WICHTIG" in versuche[1]
    assert "## Auf einen Blick" in markdown


def test_scheiternde_chefredaktion_wirft(monkeypatch):
    """Dann greift der Notfall-Digest der Pipeline - ein halb fertiger
    Wochenbericht ohne Ueberblicksteil waere schlechter als ein klar
    gekennzeichneter Rohbericht."""
    def _complete(system, user, model, max_tokens=None, **kw):
        if "You are the chief editor" in system:
            return "## Irgendwas\nKeine Gliederung."
        return BEREICHSANTWORT.format(bereich=json.loads(user)["bereich"])

    monkeypatch.setattr(editor, "complete", _complete)
    with pytest.raises(EditorialBriefingError):
        synthesize_zweistufig(_regional({"Europa": 2}), [], model="m")


def test_topics_aus_beiden_stufen_ohne_dubletten(antworten):
    _, topics = synthesize_zweistufig(
        _regional({"Europa": 2, "Asien": 1}), [], model="m")
    assert len(topics) == len(set(topics))
    assert any("Europa" in t for t in topics)


def test_bereiche_ohne_meldungen_bekommen_keinen_redakteur(antworten):
    regional = _regional({"Europa": 2})
    regional["Ozeanien"] = {"region_summary": "", "highlights": []}
    synthesize_zweistufig(regional, [], model="m")
    assert len(antworten) == 2  # Europa + Chef, nicht Ozeanien
    assert "## Ozeanien" not in antworten[-1]["user"]


def test_ohne_bewertete_meldungen_wird_geworfen(antworten):
    with pytest.raises(EditorialBriefingError):
        synthesize_zweistufig({"Europa": {"highlights": []}}, [], model="m")


# ------------------------------------------------------------ Modus-Schalter

@pytest.mark.parametrize("settings,bewertete,erwartet", [
    ({}, 36, False),                                    # heutiger Lauf
    ({}, 650, True),                                    # 1000-Quellen-Lauf
    ({"editor_zweistufig_ab_meldungen": 10}, 10, True),  # Schwelle inklusive
    ({"editor_modus": "zweistufig"}, 1, True),
    ({"editor_modus": "einstufig"}, 5000, False),
    ({"editor_modus": "quatsch"}, 36, False),           # faellt auf auto zurueck
])
def test_moduswahl(settings, bewertete, erwartet):
    assert _redaktion_zweistufig(settings, bewertete) is erwartet
