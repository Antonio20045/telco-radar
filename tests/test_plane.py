import importlib
import json
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL / "tools"))
plane = importlib.import_module("plane")

TEIL = {
    "nr": 1,
    "art": "verhalten",
    "ziel": "Die Kopfzeile der Geräteseite heißt Deutschland · Geräte und Preise",
    "bereich": "src/telco_radar/report/templates/",
    "erwarteteDateien": ["src/telco_radar/report/templates/geraete.html.j2"],
    "vorbild": "src/telco_radar/report/templates/geraete.html.j2",
    "seite": ["geraete.html"],
    "datenquelle": {},
    "abnahme": "tests/test_plan_kopf_neu.py",
    "erwarteterFehler": "Kopfzeile: erwartet Deutschland · Geräte und Preise",
    "abhaengigVon": [],
    "migration": None,
    "wasDarfNiePassieren": {
        "wiederholung": "zweimal gerendert steht dieselbe Kopfzeile da",
        "gleichzeitig": "keine andere Seite ändert ihren Text",
        "zeitueberschreitung": "die Seite rendert ohne Netz",
        "abbruch": "eine fehlende Datenquelle zeigt die Seite mit benannter Lücke",
    },
}
ZWEITER = TEIL | {
    "nr": 2,
    "abnahme": "tests/test_plan_kopf_zwei.py",
    "abhaengigVon": [1],
}
GUELTIG = {"spezifikation": "# Kopfzeile\n\nNeu.", "auftraege": [TEIL, ZWEITER]}

AGENT = """import json, os, sys
from pathlib import Path
ablage = Path(sys.argv[1])
frage = sys.stdin.read()
antworten = json.loads((ablage / "antworten.json").read_text())
nr = len(list(ablage.glob("frage-*.txt")))
(ablage / f"frage-{nr}.txt").write_text(frage)
(ablage / f"rolle-{nr}.txt").write_text(os.environ.get("TELCO_ROLLE", ""))
print(json.dumps({"result": antworten[min(nr, len(antworten) - 1)]}))
"""


def _planen(tmp_path, *antworten, kennung="S9", ordner=None):
    ablage = tmp_path / "agent"
    ablage.mkdir()
    (ablage / "antworten.json").write_text(json.dumps(list(antworten)))
    (ablage / "agent.py").write_text(AGENT)
    ziel = ordner or tmp_path / "plan"
    agent = f"{sys.executable} {ablage / 'agent.py'} {ablage}"
    code = plane.main(
        [kennung, "Kopfzeile neu", "--ordner", str(ziel), "--agent", agent]
    )
    return code, ziel, ablage


def test_gueltiger_plan_wird_zu_auftraegen_mit_eigenen_kennungen(tmp_path):
    antwort = "Hier der Plan:\n```json\n" + json.dumps(GUELTIG) + "\n```"

    code, ordner, ablage = _planen(tmp_path, antwort)

    assert code == plane.Ende.GEPLANT
    assert json.loads((ordner / plane.PLAN).read_text()) == ["S9-1", "S9-2"]
    zweiter = json.loads((ordner / "S9-2.json").read_text())
    assert zweiter["id"] == "S9-2" and zweiter["abhaengigVon"] == ["S9-1"]
    assert "nr" not in zweiter
    assert (ordner / plane.SPEZIFIKATION).read_text() == "# Kopfzeile\n\nNeu.\n"
    assert (ablage / "rolle-0.txt").read_text() == "suchen", "der Planer ändert nichts"
    assert "Kopfzeile neu" in (ablage / "frage-0.txt").read_text()


def test_ungueltiger_plan_bekommt_eine_zweite_runde_mit_befund(tmp_path):
    kaputt = json.dumps(GUELTIG | {"auftraege": [TEIL | {"bereich": "src/fremd/"}]})

    code, ordner, ablage = _planen(tmp_path, kaputt, json.dumps(GUELTIG))

    assert code == plane.Ende.GEPLANT
    assert "bereich ist kein Unterordner" in (ablage / "frage-1.txt").read_text()
    assert (ordner / "S9-2.json").is_file()


def test_zweimal_ungueltig_legt_keinen_auftrag_an(tmp_path):
    vorwaerts = GUELTIG | {"auftraege": [TEIL | {"abhaengigVon": [2]}, ZWEITER]}

    code, ordner, _ = _planen(tmp_path, json.dumps(vorwaerts), "kein JSON")

    assert code == plane.Ende.PLAN_UNGUELTIG
    assert not list(ordner.glob("*.json"))
    assert "keine JSON-Antwort" in (ordner / plane.ROH).read_text()


def test_vorwaerts_abhaengigkeit_und_doppelte_abnahme_sind_ungueltig():
    doppelt = GUELTIG | {
        "auftraege": [
            TEIL | {"abhaengigVon": [2]},
            ZWEITER | {"abnahme": TEIL["abnahme"]},
        ]
    }

    try:
        plane.auftraege(json.dumps(doppelt), "S9", WURZEL)
    except plane.PlanFehler as fehler:
        befund = str(fehler)
    else:
        befund = ""

    assert "abhaengigVon [2] ist keine frühere nr" in befund
    assert "zwei Aufträge teilen eine abnahme" in befund


def test_bestehende_abnahme_ist_ungueltig():
    alt = GUELTIG | {"auftraege": [TEIL | {"abnahme": "tests/test_plane.py"}]}

    try:
        plane.auftraege(json.dumps(alt), "S9", WURZEL)
    except plane.PlanFehler as fehler:
        befund = str(fehler)
    else:
        befund = ""

    assert "abnahme tests/test_plane.py gibt es schon" in befund


def test_ordner_im_repo_oder_nicht_leer_startet_nicht(tmp_path):
    voll = tmp_path / "voll"
    voll.mkdir()
    (voll / "alt.json").write_text("{}")

    assert _planen(tmp_path, json.dumps(GUELTIG), ordner=voll)[0] == 1
    agent = f"{sys.executable} -c pass"
    im_repo = ["S9", "x", "--ordner", str(WURZEL / "outputs"), "--agent", agent]
    assert plane.main(im_repo) == plane.Ende.NICHT_GESTARTET
