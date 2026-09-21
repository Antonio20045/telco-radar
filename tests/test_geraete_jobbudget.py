"""Die Geraetestufe darf die Veroeffentlichung nicht kosten.

Lauf 31422689829 (10.08.2026) ist genau daran gescheitert: der Kernlauf war
nach 44:39 fertig, die Nebenstufe startete mit zehn Minuten eigenem Budget in
einen Job, der noch fuenf Minuten hatte, und das Job-Timeout kam mitten in
ihr. Weil sie VOR dem Rendern und Committen steht, wurde von 45 erfolgreichen
Minuten nichts veroeffentlicht - kein Bericht, keine Website, kein Deploy.
Ein Timeout ist in GitHub ausserdem ein "cancelled", kein "failed".

Ein eigenes Zeitbudget schuetzt also nur, wenn es gegen die verbleibende
JOBZEIT gerechnet wird. Das ist die Regel, die diese Datei festnagelt.
"""
import yaml
from pathlib import Path

from telco_radar.pipeline import _GERAETE_MINDESTBUDGET, geraete_budget

_AN = {"geraete_enabled": True, "geraete_frist_sekunden": 600,
       "job_frist_sekunden": 3000, "veroeffentlichung_reserve_sekunden": 420}


def test_am_anfang_bekommt_die_stufe_ihr_volles_budget():
    assert geraete_budget(_AN, verstrichen=60.0) == 600.0


def test_der_fall_des_gescheiterten_laufs_faengt_gar_nicht_erst_an():
    """44:39 verstrichen, 50 Minuten Job: uebrig bleiben nach Abzug der
    Reserve minus 141 Sekunden. Vorher lief die Stufe hier mit zehn Minuten
    Budget los."""
    verstrichen = 44 * 60 + 39
    assert geraete_budget(_AN, verstrichen) is None
    # Gegenprobe, dass der Fall ohne die Sicherung wirklich eintraete: das
    # eigene Budget der Stufe ist groesser als die ganze Restzeit des Jobs.
    rest_im_job = _AN["job_frist_sekunden"] - verstrichen
    assert _AN["geraete_frist_sekunden"] > rest_im_job


def test_knapp_darueber_bekommt_sie_nur_die_restzeit():
    """Nicht ihr Wunschbudget, sondern was der Job noch hat - und die
    Reserve fuers Rendern bleibt unangetastet."""
    verstrichen = 3000 - 420 - 500
    budget = geraete_budget(_AN, verstrichen)
    assert budget is not None and 499.0 < budget < 501.0
    assert budget < _AN["geraete_frist_sekunden"]


def test_genau_an_der_schwelle_wird_noch_gelaufen():
    verstrichen = 3000 - 420 - _GERAETE_MINDESTBUDGET
    assert geraete_budget(_AN, verstrichen) == _GERAETE_MINDESTBUDGET
    assert geraete_budget(_AN, verstrichen + 1) is None


def test_ausgeschaltet_heisst_ausgeschaltet():
    assert geraete_budget({**_AN, "geraete_enabled": False}, 0.0) is None
    assert geraete_budget({}, 0.0) is None       # Vorgabe ist AUS


def test_die_ausgelieferte_konfiguration_haelt_die_stufe_aus_dem_wochenlauf():
    """Der Wochenlauf rendert und deployt; die Geraetestufe hat mit
    .github/workflows/geraete.yml einen eigenen taeglichen Job, der
    ausserdem im Besuchsfenster von medimax.de und ep.de liegt."""
    s = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "config" / "settings.yaml")
        .read_text(encoding="utf-8"))
    assert s.get("geraete_enabled") is False
    assert geraete_budget(s, 0.0) is None


def test_die_jobfrist_passt_zum_workflow():
    """Wer `timeout-minutes` in radar.yml aendert, muss
    `job_frist_sekunden` mitaendern - sonst rechnet die Sicherung gegen eine
    Grenze, die es nicht mehr gibt, und faellt genau dann nicht auf."""
    wurzel = Path(__file__).resolve().parents[1]
    s = yaml.safe_load((wurzel / "config" / "settings.yaml").read_text(encoding="utf-8"))
    workflow = yaml.safe_load(
        (wurzel / ".github" / "workflows" / "radar.yml").read_text(encoding="utf-8"))
    minuten = workflow["jobs"]["radar"]["timeout-minutes"]
    assert s["job_frist_sekunden"] == minuten * 60


def test_der_nachtlauf_committet_alle_vier_zustandsdateien():
    """Was der Lauf schreibt, muss er auch abliefern.

    `run_geraete_stage` schreibt seit dem 04.09.2026 drei Dateien:
    `geraete_db.json`, `geraete_preise.jsonl` und - neu - `geraete_tco.json`
    mit den SIM-only-Referenzen. Der Workflow addiert sie namentlich (kein
    `git add data/`, sonst naehme er den Seen-Store mit).

    Fehlte die dritte Zeile, entstuende die Seite trotzdem richtig - die
    Datei liegt zur Renderzeit im Runner -, aber im Repo kaeme sie nie an.
    Solange die Referenzen ABGELEITET sind, faellt das nicht auf; sobald
    ein Adapter Buendel liefert (Phase 4), waere jede Nacht die Messung der
    vorigen weg. Dieselbe Fehlerklasse wie der Navigationseintrag vom
    11.08.2026: gebaut, geprueft, und fuer jeden Leser nicht da.

    Die VIERTE Datei (P2, 11.09.2026) verschaerft das: die
    Buendel-Preishistorie `geraete_tco_historie.jsonl` kann KEIN Spaeterer
    Lauf neu erzeugen - ein nicht committeter Messtag ist fuer immer weg.
    """
    text = (Path(__file__).parent.parent / ".github" / "workflows"
            / "geraete.yml").read_text(encoding="utf-8")
    zeile = [z for z in text.splitlines() if "git add data/state" in z]
    assert zeile, "der Workflow addiert keine Zustandsdatei mehr"
    block = text[text.index(zeile[0]):text.index(zeile[0]) + 300]
    for datei in ("geraete_db.json", "geraete_preise.jsonl",
                  "geraete_tco.json", "geraete_tco_historie.jsonl"):
        assert datei in block, datei


# ==========================================================================
# P0-B (21.09.2026): EIN GESCHEITERTER SEITENAUFBAU IST EIN ROTER LAUF
# ==========================================================================
#
# Bis zum 21.09.2026 trugen "Render site" und "Commit site"
# `continue-on-error: true`. Die Begruendung stand daneben und stimmte zur
# Haelfte: der Bestand ist oben schon committet, ein Fehler hier kostet
# keinen Messtag. Die andere Haelfte war der Fehler - ein gescheitertes
# `render_site()` lief weiter in "Commit site" und in den Render-Hook, und
# der Lauf endete GRUEN. Gemessen am 21.09.2026: fuenfzig Laeufe von
# geraete.yml, alle "success", darunter sechs Tage ohne eine einzige
# Telekom-Listung.
#
# Diese Tests halten die Umkehrung fest. Sie sind Texttests auf dem
# Workflow, wie ihre Nachbarn oben - ein Workflow laeuft in der Suite
# nicht, also wird das Einzige geprueft, was hier pruefbar ist: dass die
# Griffe, die den Lauf still machen, nicht zurueckkommen.

def _geraete_workflow() -> dict:
    return yaml.safe_load((Path(__file__).resolve().parents[1]
                           / ".github" / "workflows" / "geraete.yml")
                          .read_text(encoding="utf-8"))


def _schritt(name: str) -> dict:
    schritte = _geraete_workflow()["jobs"]["geraete"]["steps"]
    treffer = [s for s in schritte if s.get("name") == name]
    assert len(treffer) == 1, f"Schritt {name!r} nicht genau einmal gefunden"
    return treffer[0]


def test_seitenaufbau_und_seitencommit_schlucken_keinen_fehler():
    """Ein Renderfehler faellt auf, statt einen gruenen Lauf zu melden."""
    for name in ("Commit state", "Render site", "Commit site"):
        assert _schritt(name).get("continue-on-error") in (None, False), name


def test_der_render_hook_darf_weiter_scheitern():
    """Die Gegenprobe, damit der Test oben nicht einfach "nirgendwo
    continue-on-error" behauptet: der Hook-Aufruf ist die EINE Stelle, an
    der ein Fehlschlag folgenlos bleiben soll - Render zieht sich den
    Stand beim naechsten Deploy ohnehin.
    """
    assert _schritt("Trigger Render deploy").get("continue-on-error") is True


def test_der_neuaufbau_im_wiederholungsweg_bricht_laut_ab():
    """Der Weg NACH einem verlorenen Push-Rennen.

    Dort wird `git reset --hard origin/$BRANCH` gefahren und die Seite neu
    gebaut - gegen den `data/`-Stand von origin, nicht den des Runners.
    Genau dieser Neuaufbau trug bis zum 21.09.2026 ein `|| exit 0`: warf
    `render_site()` hier, war der Schritt gruen, der Job gruen, und der
    Render-Hook veroeffentlichte den Vortagsstand. Nicht einmal die Zeile
    "Seite konnte nicht gepusht werden" wurde erreicht.
    """
    rumpf = _schritt("Commit site")["run"]
    assert "reset --hard" in rumpf, "der Wiederholungsweg ist weg"
    assert "|| exit 0" not in rumpf, \
        "der Neuaufbau verschluckt wieder einen Renderfehler"
    assert "exit 1" in rumpf, \
        "der Neuaufbau bricht nicht mehr laut ab"


def test_das_verlorene_push_rennen_bleibt_gruen():
    """Und die andere Richtung: ein Lauf, der nur das Rennen gegen einen
    zweiten Lauf verliert, ist kein Fehler. Der Bestand ist committet, die
    Seite baut der naechste Lauf.
    """
    rumpf = _schritt("Commit site")["run"]
    assert "Seite konnte nicht gepusht werden" in rumpf
    assert rumpf.rstrip().splitlines()[-1].strip().startswith("echo ")
