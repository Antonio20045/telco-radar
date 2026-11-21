"""Bilder der Gegenprobe in Releases (Abnahmekriterium 3): Release je Job und Tag,
Teilung an GitHubs Anhang-Grenze, ein Bild je Inhalt, benannte Lücke statt leerem
Feld, Aufräumen nur nicht mehr verlinkter Bilder. Eine Attrappe ersetzt GitHub; feste
Daten, keine Uhr."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from beleg_attrappe import AttrappeReleases

from telco_radar import gegenprobe as gp
from telco_radar import gegenprobe_ablage as ga
from telco_radar.beleg_regeln import MAX_ANHAENGE_JE_RELEASE
from telco_radar.gegenprobe_belege import MINDEST_TAGE

TAG = "2026-11-22"
O2 = "buendel--o2--apple-iphone-17-256gb-schwarz--o2-mobile-l--24m"
O2_BLAU = "buendel--o2--apple-iphone-17-256gb-blau--o2-mobile-l--24m"
TK = "buendel--telekom--apple-iphone-17-256gb-schwarz--magentamobil-l--24m"
SATURN = "buendel--saturn-mediamarkt-o2-netz--apple-iphone-17-256gb--mobile-l--24m"


def _zeile(bid: str) -> gp.Ergebnis:
    return gp.Ergebnis(
        datum=TAG,
        buendel_id=bid,
        anbieter=gp.anbieter_aus_id(bid),
        status=gp.BESTAETIGT,
        anlass=gp.ANLASS_FENSTER,
    )


def _webp(inhalt: str) -> bytes:
    return b"RIFF" + inhalt.encode()


def test_jeder_job_laedt_in_sein_eigenes_release(tmp_path):
    gh = AttrappeReleases()
    zeilen = [_zeile(O2), _zeile(TK), _zeile(SATURN)]
    bilder = {O2: _webp("a"), TK: _webp("b"), SATURN: _webp("c")}
    bilanz = ga.veroeffentliche(zeilen, bilder, TAG, tmp_path, gh)
    assert sorted(gh.angelegt) == [
        f"gegenprobe-{TAG}-o2",
        f"gegenprobe-{TAG}-saturn-mediamarkt",
        f"gegenprobe-{TAG}-telekom",
    ]
    assert bilanz.fehler == []
    jobs = {O2: "o2", TK: "telekom", SATURN: "saturn-mediamarkt"}
    for e in zeilen:
        tag = ga.release_tag(TAG, jobs[e.buendel_id])
        assert e.bild == ga.url(tag, ga.dateiname(bilder[e.buendel_id]))
        assert e.bild_fehlt is None


def test_gleiches_bild_zweier_farben_liegt_einmal_im_release(tmp_path):
    gh = AttrappeReleases()
    zeilen = [_zeile(O2), _zeile(O2_BLAU)]
    ga.veroeffentliche(zeilen, {O2: _webp("x"), O2_BLAU: _webp("x")}, TAG, tmp_path, gh)
    assert gh.stand[f"gegenprobe-{TAG}-o2"] == [ga.dateiname(_webp("x"))]
    assert zeilen[0].bild == zeilen[1].bild is not None


def test_an_der_anhang_grenze_geht_es_im_naechsten_teil_weiter(tmp_path):
    voll = [f"{i:016x}.webp" for i in range(MAX_ANHAENGE_JE_RELEASE)]
    gh = AttrappeReleases({f"gegenprobe-{TAG}-o2": voll})
    zeile = _zeile(O2)
    ga.veroeffentliche([zeile], {O2: _webp("neu")}, TAG, tmp_path, gh)
    assert gh.angelegt == [f"gegenprobe-{TAG}-o2-t2"]
    assert f"/gegenprobe-{TAG}-o2-t2/" in zeile.bild
    assert len(gh.stand[f"gegenprobe-{TAG}-o2"]) == MAX_ANHAENGE_JE_RELEASE


def test_zweiter_lauf_des_tages_laedt_vorhandenes_nicht_noch_einmal(tmp_path):
    name = ga.dateiname(_webp("x"))
    gh = AttrappeReleases({f"gegenprobe-{TAG}-o2": [name]})
    zeile = _zeile(O2)
    ga.veroeffentliche([zeile], {O2: _webp("x")}, TAG, tmp_path, gh)
    assert gh.hochgeladen == [] and gh.angelegt == []
    assert zeile.bild == ga.url(f"gegenprobe-{TAG}-o2", name)


def test_ohne_restzeit_nennt_die_zeile_den_grund_statt_leer(tmp_path):
    gh = AttrappeReleases()
    zeile = _zeile(O2)
    ga.veroeffentliche([zeile], {O2: _webp("x")}, TAG, tmp_path, gh, 10.0, lambda: 11.0)
    assert zeile.bild is None
    assert zeile.bild_fehlt == ga.GRUND_FRIST
    assert gh.hochgeladen == []


def test_gescheitertes_hochladen_ist_ein_benannter_ausfall(tmp_path):
    gh = AttrappeReleases(scheitern_bei=("hochladen",))
    zeile = _zeile(O2)
    ga.veroeffentliche(
        [zeile], {O2: _webp("x")}, TAG, tmp_path, gh, schlaf=lambda s: None
    )
    assert zeile.bild is None
    assert zeile.bild_fehlt.startswith(ga.GRUND_FEHLER)
    assert "kaputt" in zeile.bild_fehlt


def test_ohne_hochladen_bleibt_das_bild_lokal_und_benannt(tmp_path):
    zeile = _zeile(O2)
    ga.veroeffentliche([zeile], {O2: _webp("x")}, TAG, tmp_path, None)
    datei = tmp_path / ga.dateiname(_webp("x"))
    assert datei.read_bytes() == _webp("x")
    assert zeile.bild is None and str(datei) in zeile.bild_fehlt


def test_release_schema_kennt_alte_und_neue_namen():
    assert ga.datum_des_tags("gegenprobe-2026-11-21") == date(2026, 11, 21)
    assert ga.datum_des_tags(f"gegenprobe-{TAG}-1-1-t2") == date(2026, 11, 22)
    assert not ga.ist_gegenprobe_tag("belege-2026-11-21")
    assert ga.zerlege(ga.url(f"gegenprobe-{TAG}-o2", "a.webp")) == (
        f"gegenprobe-{TAG}-o2",
        "a.webp",
    )


HEUTE = date(2026, 12, 10)
ALT = "gegenprobe-2026-11-22-o2"
JUNG = f"gegenprobe-{(HEUTE - timedelta(days=MINDEST_TAGE - 1)).isoformat()}-o2"


def test_verlinktes_bild_bleibt_unverlinktes_altes_geht():
    anhaenge = {ALT: ["a.webp", "b.webp"], JUNG: ["c.webp"], "belege-2026-11-01": ["x"]}
    plan = ga.plane(anhaenge, {ga.url(ALT, "a.webp")}, HEUTE, MINDEST_TAGE)
    assert plan.dateien == [(ALT, "b.webp")]
    assert plan.releases == []
    assert plan.bleibt[ALT] == ["a.webp"]
    assert plan.bleibt[JUNG] == ["c.webp"]
    assert "belege-2026-11-01" in plan.bleibt


def test_release_ohne_verlinktes_bild_geht_als_ganzes():
    plan = ga.plane({ALT: ["a.webp", "b.webp"]}, set(), HEUTE, MINDEST_TAGE)
    assert plan.releases == [ALT] and plan.dateien == []
    gh = AttrappeReleases({ALT: ["a.webp", "b.webp"]})
    bilanz = ga.raeume_auf(plan, gh, lambda: True)
    assert gh.releases_geloescht == [ALT] and bilanz.fehler == []


def test_juenger_als_die_mindestfrist_wird_nie_geloescht():
    plan = ga.plane({JUNG: ["c.webp"]}, set(), HEUTE, MINDEST_TAGE)
    assert plan.releases == [] and plan.dateien == []


def test_ohne_zeit_bleibt_der_rest_liegen_und_ist_gezaehlt():
    plan = ga.plane(
        {ALT: ["a.webp", "b.webp", "c.webp"]},
        {ga.url(ALT, "a.webp")},
        HEUTE,
        MINDEST_TAGE,
    )
    gh = AttrappeReleases({ALT: ["a.webp", "b.webp", "c.webp"]})
    erlaubt = iter([True, False])
    bilanz = ga.raeume_auf(plan, gh, lambda: next(erlaubt))
    assert bilanz.assets_geloescht == 1 and bilanz.ausgelassen == 1
    assert ga.url(ALT, "a.webp") not in {ga.url(*x) for x in gh.assets_geloescht}


def test_liste_zeigt_nur_aufbewahrte_bilder():
    liste = ga.Liste(HEUTE, frozenset({ga.url(ALT, "a.webp")}))
    assert liste.vorhanden(ga.url(ALT, "a.webp"), MINDEST_TAGE)
    assert not liste.vorhanden(ga.url(ALT, "b.webp"), MINDEST_TAGE)
    assert liste.vorhanden(ga.url(JUNG, "neu.webp"), MINDEST_TAGE)
    assert liste.vorhanden("https://example.de/fremd.webp", MINDEST_TAGE)


def test_abschnitt_im_manifest_wird_wieder_gelesen(tmp_path: Path):
    manifest = tmp_path / "belege_manifest.json"
    manifest.write_text(
        json.dumps(
            {"format": 1, ga.SCHLUESSEL: ga.als_abschnitt(HEUTE, {ALT: ["a.webp"]})}
        ),
        encoding="utf-8",
    )
    liste = ga.liste(manifest)
    assert liste is not None and liste.stand == HEUTE
    assert liste.urls == frozenset({ga.url(ALT, "a.webp")})
    assert ga.liste(tmp_path / "fehlt.json") is None
