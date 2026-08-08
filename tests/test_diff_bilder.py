"""Tests fuer die Bilder der Differenzierungs-Beispiele (report/diff_bilder.py).

Der Anlass, 08.08.2026: die Seite zeigte 77 Karten und **null** Bilder, waehrend
jede Meldung der Titelseite eins hatte. Antonio: "Keine Bilder, es ist schwer zu
verstehen."

Getestet wird offline. Das Netz kommt nur ueber `report_bilder.og_bild` und
`report_bilder.lade_und_lege_ab` ins Spiel, und beide werden hier ersetzt - was
diese Datei prueft, ist die Buchfuehrung drumherum: erben statt holen, den
Fehlversuch merken, aufraeumen, und die Bilder nur verteilen, wenn die Datei
wirklich ausgeliefert wird.
"""
from __future__ import annotations

import json

from telco_radar.report import diff_bilder


def _eintrag(url: str) -> dict:
    return {"url": url, "operator": "Betreiber", "what": "Ein Beispiel."}


def _bericht(tmp_path, url: str, bild: str = "abc-800.jpg") -> None:
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "2026-08-05.json").write_text(json.dumps({
        "date": "2026-08-05",
        "regions": {"Europa": {"highlights": [
            {"title": "t", "url": url, "image": bild,
             "image_w": 1200, "image_h": 800}]}},
    }), encoding="utf-8")


def test_ein_bild_des_wochenberichts_wird_geerbt_statt_geholt(tmp_path, monkeypatch):
    """Der Presse-Zweig der Bibliothek stammt aus genau denselben Meldungen -
    das Bild ist schon da, gemessen und verkleinert. Kein Netz."""
    _bericht(tmp_path, "https://example.com/a")

    def nie(*args, **kw):  # noqa: ANN002, ANN003
        raise AssertionError("es haette gar nicht gefragt werden duerfen")

    monkeypatch.setattr(diff_bilder.report_bilder, "og_bild", nie)

    bilanz = diff_bilder.beschaffe([_eintrag("https://www.example.com/a/")],
                                   tmp_path, tmp_path / "data" / "reports",
                                   "2026-08-08")
    assert bilanz["aus_bericht"] == 1
    index = diff_bilder.lade_index(tmp_path)
    eintrag = index["https://example.com/a"]
    assert eintrag["image"] == "abc-800.jpg" and eintrag["quelle"] == "bericht"


def test_ohne_bericht_bild_wird_das_og_image_geholt(tmp_path, monkeypatch):
    monkeypatch.setattr(diff_bilder.report_bilder, "og_bild",
                        lambda url, client: "https://example.com/bild.jpg")
    monkeypatch.setattr(diff_bilder.report_bilder, "lade_und_lege_ab",
                        lambda *a, **kw: ("og-800.jpg", 800, 450))

    bilanz = diff_bilder.beschaffe([_eintrag("https://example.com/b")],
                                   tmp_path, tmp_path / "data" / "reports",
                                   "2026-08-08")
    assert bilanz["geladen"] == 1 and bilanz["mit_bild"] == 1
    assert diff_bilder.lade_index(tmp_path)["https://example.com/b"]["image"] \
        == "og-800.jpg"


def test_der_fehlversuch_wird_gemerkt_und_nicht_sofort_wiederholt(tmp_path, monkeypatch):
    """Ohne das fragte jeder Lauf dieselben 40 Seiten erneut ab, die schon
    dreimal kein og:image hatten - bei zwei Laeufen die Woche."""
    versuche = []
    monkeypatch.setattr(diff_bilder.report_bilder, "og_bild",
                        lambda url, client: versuche.append(url) or "")

    for _ in range(2):
        diff_bilder.beschaffe([_eintrag("https://example.com/c")], tmp_path,
                              tmp_path / "data" / "reports", "2026-08-08")
    assert versuche == ["https://example.com/c"]

    # Nach der Frist darf es einen zweiten Anlauf geben - Redaktionssysteme
    # bekommen `og:image` auch nachtraeglich.
    diff_bilder.beschaffe([_eintrag("https://example.com/c")], tmp_path,
                          tmp_path / "data" / "reports", "2026-11-01")
    assert len(versuche) == 2


def test_ein_beispiel_das_die_bibliothek_verlaesst_nimmt_sein_bild_mit(tmp_path,
                                                                       monkeypatch):
    """Sonst waechst der Ordner mit jedem Beispiel, das die Bibliothek jemals
    hatte - und die Bilder werden nach site/images/ gespiegelt."""
    ordner = diff_bilder.bildordner(tmp_path)
    ordner.mkdir(parents=True)
    (ordner / "alt-800.jpg").write_bytes(b"x")
    diff_bilder.schreibe_index(
        tmp_path, {"https://example.com/weg": {"image": "alt-800.jpg"}})
    monkeypatch.setattr(diff_bilder.report_bilder, "og_bild",
                        lambda url, client: "")

    bilanz = diff_bilder.beschaffe([_eintrag("https://example.com/da")], tmp_path,
                                   tmp_path / "data" / "reports", "2026-08-08")
    assert bilanz["geloescht"] == 1
    assert not (ordner / "alt-800.jpg").exists()
    assert "https://example.com/weg" not in diff_bilder.lade_index(tmp_path)


def test_verteile_stempelt_die_felder_in_den_bestand():
    bestand = [_eintrag("https://www.example.com/a/")]
    getroffen = diff_bilder.verteile(bestand, {
        "https://example.com/a": {"image": "x.jpg", "image_w": 800, "image_h": 450}})
    assert getroffen == 1
    assert bestand[0]["image"] == "x.jpg" and bestand[0]["image_w"] == 800


def test_ein_verweis_auf_eine_geloeschte_datei_wird_nicht_verteilt():
    """Ein Bild, das nicht ausgeliefert wird, ist schlimmer als keins - es
    zeigt einen leeren Kasten. Der Fall tritt regelmaessig ein: das geerbte
    Bericht-Bild faellt weg, sobald seine Ausgabe aus dem Aufbewahrungs-
    fenster von `report_bilder.raeume_auf()` rutscht."""
    bestand = [_eintrag("https://example.com/a")]
    getroffen = diff_bilder.verteile(
        bestand, {"https://example.com/a": {"image": "weg.jpg"}},
        vorhandene_bilder={"andere.jpg"})
    assert getroffen == 0 and "image" not in bestand[0]


def test_ein_kaputter_index_kippt_keinen_lauf(tmp_path):
    pfad = diff_bilder.indexdatei(tmp_path)
    pfad.parent.mkdir(parents=True)
    pfad.write_text("{kein json", encoding="utf-8")
    assert diff_bilder.lade_index(tmp_path) == {}
