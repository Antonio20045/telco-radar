"""„Was wächst, was kippt" (report/verlauf.py).

Die Differenzierungs-Seite sagte "71 Beispiele, Entertainment 17, KI 12" und
nie, ob KI im Juni noch 4 war. Genau diese Ableitung ist der Wert einer
Datenbank, die seit Juli laeuft.

Die Fehler, gegen die diese Datei steht, sind beide Rechenfehler mit
Aussagekraft: absolute Zahlen in einer wachsenden Sammlung zeigen immer
"alles waechst", und ein Anteil aus zwei Beispielen ist eine Rundung.
"""
from __future__ import annotations

from telco_radar.report import verlauf as V

LABELS = {"ki": "KI & Assistenten", "entertainment": "Entertainment",
          "gaming": "Gaming"}


def _bestand(**je_monat):
    """{"2026-06": {"ki": 4, "entertainment": 3}, ...} -> flache Eintraege."""
    out = []
    for monat, themen in je_monat.items():
        monat = monat.replace("_", "-")
        for thema, n in themen.items():
            out.extend({"theme": thema, "first_seen": f"{monat}-15"}
                       for _ in range(n))
    return out


def test_ein_einzelner_monat_ist_kein_verlauf():
    """Lieber nichts zeigen als eine Linie mit einem Punkt."""
    v = V.aufbereiten(_bestand(**{"2026_08": {"ki": 9}}), LABELS)
    assert v["aktiv"] is False


def test_der_verlauf_zeigt_die_monate_in_reihenfolge():
    v = V.aufbereiten(_bestand(**{"2026_06": {"ki": 5},
                                  "2026_07": {"ki": 5},
                                  "2026_08": {"ki": 5}}), LABELS)
    assert [m["label"] for m in v["monate"]] == ["Jun 26", "Jul 26", "Aug 26"]


def test_gerechnet_wird_der_anteil_nicht_die_zahl():
    """Eine wachsende Sammlung zeigt in absoluten Zahlen immer "alles
    waechst" - das ist eine Aussage ueber die Sammelmenge, nicht ueber den
    Markt. Hier verdoppelt KI seine ZAHL und verliert trotzdem Anteil."""
    v = V.aufbereiten(_bestand(**{
        "2026_06": {"ki": 5, "gaming": 5},
        "2026_07": {"ki": 5, "gaming": 5},
        "2026_08": {"ki": 10, "gaming": 40}}), LABELS)
    ki = next(r for r in v["reihen"] if r["key"] == "ki")
    assert ki["punkte"][0]["n"] == 5 and ki["punkte"][-1]["n"] == 10
    assert ki["punkte"][0]["anteil"] > ki["punkte"][-1]["anteil"]
    assert any(e["key"] == "ki" for e in v["kippt"])


def test_ein_duenner_monat_traegt_keine_aussage():
    """Ein "Fintech verdoppelt sich" aus zwei Beispielen ist eine Rundung."""
    v = V.aufbereiten(_bestand(**{"2026_06": {"ki": 10, "gaming": 10},
                                  "2026_07": {"ki": 10, "gaming": 10},
                                  "2026_08": {"gaming": 2}}), LABELS)
    assert "Aug 26" in v["duenne_monate"]
    # Der duenne Monat steht im Gitter ...
    assert [m["label"] for m in v["monate"]][-1] == "Aug 26"
    # ... aber er traegt keine Bewegungsaussage.
    assert v["waechst"] == [] and v["kippt"] == []


def test_gemessen_wird_gegen_den_durchschnitt_nicht_gegen_den_vormonat():
    """Gegen den Vormonat allein gerechnet macht jede Schwankung zur
    Nachricht: ein Ausreisser im Juni erzeugte dann im Juli automatisch eine
    Gegenbewegung derselben Groesse.

    Der Durchschnitt macht das nicht immun - er daempft es. Genau das wird
    hier gemessen: dieselbe Lage, einmal gegen den Vormonat und einmal gegen
    den Durchschnitt gerechnet.
    """
    v = V.aufbereiten(_bestand(**{
        "2026_05": {"ki": 10, "gaming": 10},
        "2026_06": {"ki": 2, "gaming": 18},     # Ausreisser nach unten
        "2026_07": {"ki": 10, "gaming": 10},
        "2026_08": {"ki": 10, "gaming": 10}}), LABELS)
    ki = next(r for r in v["reihen"] if r["key"] == "ki")
    anteile = [p["anteil"] for p in ki["punkte"]]
    gegen_vormonat = abs(anteile[-1] - anteile[-2])
    gemeldet = next((abs(e["delta"]) for e in v["waechst"] + v["kippt"]
                     if e["key"] == "ki"), 0.0)
    # Der Ausreisser liegt zwei Monate zurueck; gegen den Vormonat waere
    # jetzt Ruhe, gegen den Durchschnitt ist der Rueckstand noch sichtbar -
    # und das ist die ehrlichere Aussage.
    assert gegen_vormonat == 0.0
    assert 0 < gemeldet <= 15.0


def test_eine_kleine_verschiebung_ist_keine_bewegung():
    v = V.aufbereiten(_bestand(**{"2026_06": {"ki": 10, "gaming": 10},
                                  "2026_07": {"ki": 10, "gaming": 10},
                                  "2026_08": {"ki": 11, "gaming": 10}}),
                      LABELS)
    assert v["waechst"] == [] and v["kippt"] == []


def test_eine_deutliche_verschiebung_wird_gemeldet():
    v = V.aufbereiten(_bestand(**{"2026_06": {"ki": 15, "gaming": 5},
                                  "2026_07": {"ki": 15, "gaming": 5},
                                  "2026_08": {"ki": 5, "gaming": 15}}),
                      LABELS)
    assert [e["key"] for e in v["waechst"]] == ["gaming"]
    assert [e["key"] for e in v["kippt"]] == ["ki"]


def test_hebel_ohne_eine_einzige_aufnahme_stehen_nicht_im_gitter():
    v = V.aufbereiten(_bestand(**{"2026_07": {"ki": 8}, "2026_08": {"ki": 8}}),
                      LABELS)
    assert [r["key"] for r in v["reihen"]] == ["ki"]


def test_eintraege_ohne_datum_kippen_nichts():
    bestand = _bestand(**{"2026_07": {"ki": 8}, "2026_08": {"ki": 8}})
    bestand += [{"theme": "gaming", "first_seen": ""},
                {"theme": "gaming"},
                {"first_seen": "2026-08-01"}]
    v = V.aufbereiten(bestand, LABELS)
    assert v["aktiv"] is True
    assert [r["key"] for r in v["reihen"]] == ["ki"]


def test_der_verlauf_zeigt_hoechstens_ein_halbes_jahr():
    monate = {f"2026_{m:02d}": {"ki": 9} for m in range(1, 13)}
    v = V.aufbereiten(_bestand(**monate), LABELS)
    assert len(v["monate"]) == V.MAX_MONATE
