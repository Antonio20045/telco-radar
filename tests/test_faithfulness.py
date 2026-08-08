"""Der Prueflauf gegen den Originaltext (analyze/faithfulness.py).

Solange das System zusammenfasst, ist ein Fehler eine ungenaue Zeile. Sobald
es folgert, klingt ein Fehler plausibel und steht unter einem Quellenlink,
der ihn zu belegen scheint. Diese Datei haelt fest, dass nichts Ungeprueftes
auf die Seite kommt.
"""
from __future__ import annotations

import json

import pytest

from telco_radar.analyze import faithfulness as F


def _h(satz, titel="Telekom senkt Preis der Allnet-Flat auf 34,95 Euro",
       zusammenfassung="Die Deutsche Telekom senkt den Preis ihrer Allnet-Flat "
                       "zum 1. September auf 34,95 Euro."):
    return {"title": titel, "summary": zusammenfassung, "ctm_satz": satz}


def _antwort(urteile):
    return json.dumps({"urteile": urteile})


# ------------------------------------------------- Stufe 1: Zahlen im Code

def test_erfundene_zahl_faellt_ohne_modellaufruf(monkeypatch):
    monkeypatch.setattr(F, "complete", lambda *a, **k: pytest.fail(
        "eine erfundene Zahl darf keinen Modellaufruf kosten"))
    h = _h("Drückt unsere Preisuntergrenze um 12 Euro nach unten.")
    bilanz = F.pruefe([h], model="m", use_llm=True)
    assert "ctm_satz" not in h
    assert bilanz["verworfen"] == 1
    assert "12" in h["ctm_satz_verworfen"]


def test_zahl_aus_der_quelle_ueberlebt(monkeypatch):
    monkeypatch.setattr(F, "complete",
                        lambda *a, **k: _antwort([{"id": 0, "belegt": True}]))
    h = _h("Mit 34,95 Euro drückt das unsere Preisuntergrenze.")
    F.pruefe([h], model="m", use_llm=True)
    assert h.get("ctm_satz")
    assert h.get("ctm_satz_geprueft") is True


def test_gerundete_zahl_gilt_als_gedeckt(monkeypatch):
    """"unter 35 Euro" ueber einer Quelle mit "34,95 Euro" ist keine
    Erfindung, sondern eine Rundung - der Satz soll lesbar bleiben duerfen."""
    monkeypatch.setattr(F, "complete",
                        lambda *a, **k: _antwort([{"id": 0, "belegt": True}]))
    h = _h("Erste Flat unter 35 Euro – drückt unsere Preisuntergrenze.")
    F.pruefe([h], model="m", use_llm=True)
    assert h.get("ctm_satz")


# --------------------------------------- Stufe 3: das Sicherheitswort im Code

def test_sehr_wahrscheinlich_ueber_einer_absicht_faellt(monkeypatch):
    monkeypatch.setattr(F, "complete", lambda *a, **k: pytest.fail(
        "die Uebertreibung faellt schon im Code"))
    h = _h("Sehr wahrscheinlich müssen wir beim Anschlusspreis nachziehen.",
           titel="Telekom prüft Senkung des Anschlusspreises",
           zusammenfassung="Die Telekom erwägt, den Anschlusspreis zu senken.")
    F.pruefe([h], model="m", use_llm=True)
    assert "ctm_satz" not in h
    assert "übertreibt" in h["ctm_satz_verworfen"]


def test_sehr_wahrscheinlich_ueber_einer_entscheidung_bleibt(monkeypatch):
    monkeypatch.setattr(F, "complete",
                        lambda *a, **k: _antwort([{"id": 0, "belegt": True}]))
    h = _h("Sehr wahrscheinlich müssen wir beim Anschlusspreis nachziehen.")
    F.pruefe([h], model="m", use_llm=True)
    assert h.get("ctm_satz")


# ------------------------------------------------------ Stufe 2: das Modell

def test_unbelegter_satz_wird_entfernt_und_begruendet(monkeypatch):
    monkeypatch.setattr(F, "complete", lambda *a, **k: _antwort(
        [{"id": 0, "belegt": False, "grund": "Markt verwechselt"}]))
    h = _h("Zwingt uns zu einer Antwort im österreichischen Markt.")
    bilanz = F.pruefe([h], model="m", use_llm=True)
    assert "ctm_satz" not in h
    assert h["ctm_satz_verworfen"] == "Markt verwechselt"
    assert bilanz["gruende"]["Markt verwechselt"] == 1


# ------------------------------------------------------------- fail closed

def test_ohne_modell_erscheint_kein_folgerungssatz():
    """Fail closed. Ein ungeprueft veroeffentlichter Folgerungssatz ist genau
    das Risiko, gegen das dieser Durchgang steht."""
    h = _h("Drückt unsere Preisuntergrenze deutlich nach unten.")
    bilanz = F.pruefe([h], model="", use_llm=False)
    assert "ctm_satz" not in h
    assert bilanz["verworfen"] == 1


def test_gescheiterter_pruefaufruf_laesst_den_satz_fallen(monkeypatch):
    def kaputt(*a, **k):
        raise RuntimeError("provider overloaded")

    monkeypatch.setattr(F, "complete", kaputt)
    h = _h("Drückt unsere Preisuntergrenze deutlich nach unten.")
    F.pruefe([h], model="m", use_llm=True)
    assert "ctm_satz" not in h
    assert h["ctm_satz_verworfen"] == "Prüfung nicht möglich"


def test_fehlendes_urteil_zaehlt_nicht_als_belegt(monkeypatch):
    monkeypatch.setattr(F, "complete", lambda *a, **k: _antwort([]))
    h = _h("Drückt unsere Preisuntergrenze deutlich nach unten.")
    F.pruefe([h], model="m", use_llm=True)
    assert "ctm_satz" not in h


def test_ohne_saetze_kostet_die_pruefung_keinen_aufruf(monkeypatch):
    monkeypatch.setattr(F, "complete", lambda *a, **k: pytest.fail("kein Satz"))
    assert F.pruefe([{"title": "x", "summary": "y"}],
                    model="m", use_llm=True)["geprueft"] == 0


def test_stapel_bleiben_klein(monkeypatch):
    """Ein zu grosser Stapel laeuft in dieselbe Falle wie die Promo-Stufe:
    das Modell ist mit dem Budget fertig, bevor die Antwort anfaengt."""
    gesehen = []

    def fake(system, user, model=None, max_tokens=None):
        rows = json.loads(user)
        gesehen.append(len(rows))
        return _antwort([{"id": r["id"], "belegt": True} for r in rows])

    monkeypatch.setattr(F, "complete", fake)
    # Ohne Ziffern im Satz - sonst faengt ihn schon die Zahlenpruefung ab,
    # und der Stapel erreicht das Modell gar nicht.
    hs = [_h("Drückt unsere Preisuntergrenze deutlich nach unten, Fall "
             + chr(ord("A") + i)) for i in range(25)]
    F.pruefe(hs, model="m", use_llm=True)
    assert max(gesehen) <= F.STAPEL
    assert sum(gesehen) == 25
