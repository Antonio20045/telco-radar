"""Mehrere Aktionsseiten je Marke - die Schicht, an der die Promo-Rubrik
seit dem 08.08.2026 haengt.

Warum diese Datei existiert: die Umstellung von "eine Marke = eine Seite" auf
"eine Marke = N Seiten" hat drei Stellen, an denen ein Fehler nicht auffaellt,
sondern still Angebote loescht.

  1. Der Snapshot-Schluessel. Waere er weiter die MARKE, wuerde jede Seite den
     Stand der zuletzt abgerufenen ueberschreiben - jede Seite gaelte in jedem
     Lauf als veraendert, und die LLM-Extraktion liefe fuer alles neu.
  2. mark_stale(). Eine Marke mit fuenf Seiten hat pro Lauf typischerweise EINE
     geaenderte. Ohne Einschraenkung auf die wirklich gelesenen Seiten wuerden
     die Angebote der vier unveraenderten jedes Mal einen Schritt Richtung
     "ausgelaufen" ruecken - nach zwei Laeufen waere die Marke leer, obwohl
     sich nichts geaendert hat. DAS ist der teure Fehler, und er sieht im
     Protokoll aus wie ein normal verlaufener Lauf.
  3. Die Rueckwaertskompatibilitaet: Bestandseintraege haben kein source_url,
     und der SnapshotStore hat noch die alten Marken-Schluessel.

Kein Netz, kein LLM.
"""
from __future__ import annotations

import json

from telco_radar.analyze.promo_store import PromoDB, SnapshotStore, snapshot_key
from telco_radar.promo_config import PromoPage, PromoSource, load_promo_config

LEIT = "https://marke.test/aktionen"
ZWEIT = "https://marke.test/handys"


# --------------------------------------------------------------- Konfiguration
def _yaml_schreiben(tmp_path, text: str):
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "promo_sources.yaml").write_text(text, encoding="utf-8")
    return load_promo_config(tmp_path)


def test_marke_ohne_pages_verhaelt_sich_wie_vorher(tmp_path):
    """Der Bestand darf sich durch die Umstellung nicht aendern - kein
    einziger vorhandener YAML-Eintrag musste angefasst werden."""
    cfg = _yaml_schreiben(tmp_path, f"""
brands:
  - name: Marke
    url: {LEIT}
    kind: static
""")
    src = cfg.sources[0]
    assert [p.url for p in src.pages] == [LEIT]
    assert src.crawlable is True
    assert cfg.page_count == 1


def test_pages_kommen_hinter_die_leitseite(tmp_path):
    cfg = _yaml_schreiben(tmp_path, f"""
brands:
  - name: Marke
    url: {LEIT}
    kind: js
    pages:
      - url: {ZWEIT}
        kind: static
        label: Handys
""")
    src = cfg.sources[0]
    assert [p.url for p in src.pages] == [LEIT, ZWEIT]
    # kind gilt je Seite, nicht je Marke: eine statische Unterseite unter einer
    # JS-gerenderten Leitseite ist der Normalfall, kein Sonderfall.
    assert [p.kind for p in src.pages] == ["js", "static"]
    assert src.pages[1].label == "Handys"
    assert cfg.page_count == 2


def test_die_leitseite_wird_nicht_doppelt_abgefragt(tmp_path):
    """Steht die Leitseite versehentlich auch unter pages:, faellt sie raus -
    sonst liefe die LLM-Extraktion zweimal ueber denselben Text und die
    Angebote wuerden doppelt gezaehlt."""
    cfg = _yaml_schreiben(tmp_path, f"""
brands:
  - name: Marke
    url: {LEIT}
    pages:
      - url: {LEIT}/
      - url: {ZWEIT}
""")
    assert [p.url for p in cfg.sources[0].pages] == [LEIT, ZWEIT]


def test_marke_ist_crawlbar_sobald_eine_seite_es_ist(tmp_path):
    """Eine Marke, deren Leitseite ein dokumentierter Sonderfall ist, deren
    Kampagnenseite sich aber abrufen laesst, wird beobachtet - sie darf auf
    der Uebersicht nicht als ungeprueft durchfallen."""
    cfg = _yaml_schreiben(tmp_path, f"""
brands:
  - name: Marke
    url: {LEIT}
    kind: skip
    pages:
      - url: {ZWEIT}
        kind: static
""")
    src = cfg.sources[0]
    assert src.crawlable is True
    assert [p.url for p in src.crawled_pages] == [ZWEIT]
    assert cfg.crawled_sources == [src]


# ----------------------------------------------------------- SnapshotStore
def test_jede_seite_hat_ihren_eigenen_aenderungsstand(tmp_path):
    store = SnapshotStore(tmp_path / "snap.json")
    a, b = snapshot_key("Marke", LEIT), snapshot_key("Marke", ZWEIT)
    store.update(a, "hash-a", "2026-08-08")
    # Die zweite Seite derselben Marke darf davon nichts wissen.
    assert store.changed(b, "hash-b") is True
    store.update(b, "hash-b", "2026-08-08")
    assert store.changed(a, "hash-a") is False
    assert store.changed(b, "hash-b") is False
    # ... und keine der beiden darf die andere ueberschrieben haben.
    assert store.changed(a, "hash-b") is True


def test_alter_markenschluessel_gilt_einmalig_weiter(tmp_path):
    """Ohne diesen Rueckfall wuerde beim ersten Lauf nach der Umstellung jede
    Leitseite grundlos als veraendert gelten - eine komplette
    LLM-Neuextraktion ueber alle Marken, fuer nichts."""
    pfad = tmp_path / "snap.json"
    pfad.write_text(json.dumps({"Marke": {"hash": "alt", "fetched_at": "2026-08-01"}}),
                    encoding="utf-8")
    store = SnapshotStore(pfad)
    key = snapshot_key("Marke", LEIT)
    assert store.changed(key, "alt", legacy_key="Marke") is False
    assert store.changed(key, "neu", legacy_key="Marke") is True
    # Eine ZWEITE Seite darf den alten Markenschluessel nicht erben.
    assert store.changed(snapshot_key("Marke", ZWEIT), "alt") is True


def test_prune_raeumt_alte_und_entfernte_schluessel_weg(tmp_path):
    pfad = tmp_path / "snap.json"
    pfad.write_text(json.dumps({"Marke": {"hash": "alt"}}), encoding="utf-8")
    store = SnapshotStore(pfad)
    key = snapshot_key("Marke", LEIT)
    store.update(key, "neu", "2026-08-08")
    assert store.prune([key]) == 1
    assert store.changed(key, "neu") is False
    assert store.changed(snapshot_key("Marke", LEIT), "alt", legacy_key="Marke") is True


# ---------------------------------------------------------------- mark_stale
def _db_mit_zwei_seiten(tmp_path) -> PromoDB:
    db = PromoDB(tmp_path / "db.json")
    db.upsert([{"brand": "Marke", "headline": "Bonus auf der Leitseite"}],
              "2026-08-01", source_url=LEIT)
    db.upsert([{"brand": "Marke", "headline": "Rabatt auf Geraete"}],
              "2026-08-01", source_url=ZWEIT)
    return db


def test_upsert_haelt_die_herkunftsseite_fest(tmp_path):
    db = _db_mit_zwei_seiten(tmp_path)
    herkunft = {e["headline"]: e["source_url"] for e in db.entries.values()}
    assert herkunft == {"Bonus auf der Leitseite": LEIT, "Rabatt auf Geraete": ZWEIT}


def test_unveraenderte_seite_laesst_ihre_angebote_in_ruhe(tmp_path):
    """Der Kern der Sache: Seite ZWEIT hat sich geaendert und wurde neu
    gelesen, LEIT nicht. Das Angebot von LEIT steht folglich nicht unter den
    wiedergefundenen IDs - altern darf es trotzdem nicht."""
    db = _db_mit_zwei_seiten(tmp_path)
    neu = db.upsert([{"brand": "Marke", "headline": "Rabatt auf Geraete"}],
                    "2026-08-08", source_url=ZWEIT)[1]
    db.mark_stale("Marke", neu, "2026-08-08",
                  gepruefte_seiten={ZWEIT}, leitseite=LEIT)
    status = {e["headline"]: e["status"] for e in db.entries.values()}
    assert status == {"Bonus auf der Leitseite": "aktiv",
                      "Rabatt auf Geraete": "aktiv"}


def test_angebot_der_gelesenen_seite_altert_weiterhin(tmp_path):
    """Die Gegenprobe - die Alterung darf nicht einfach abgeschaltet sein."""
    db = _db_mit_zwei_seiten(tmp_path)
    db.mark_stale("Marke", set(), "2026-08-08",
                  gepruefte_seiten={ZWEIT}, leitseite=LEIT)
    status = {e["headline"]: e["status"] for e in db.entries.values()}
    assert status["Rabatt auf Geraete"] == "evtl. ausgelaufen"
    assert status["Bonus auf der Leitseite"] == "aktiv"
    # zweiter Fehltreffer in Folge -> beendet
    db.mark_stale("Marke", set(), "2026-08-09",
                  gepruefte_seiten={ZWEIT}, leitseite=LEIT)
    assert db.entries and any(e["status"] == "ausgelaufen"
                              for e in db.entries.values())


def test_bestandseintrag_ohne_herkunft_haengt_an_der_leitseite(tmp_path):
    """Eintraege aus der Zeit vor mehreren Seiten haben kein source_url. Sie
    hingen alle an der einzigen damals konfigurierten Seite - der Leitseite.
    Wird die neu gelesen und das Angebot fehlt, altert es korrekt; wird nur
    eine andere Seite gelesen, bleibt es unangetastet."""
    db = PromoDB(tmp_path / "db.json")
    db.entries["alt"] = {"id": "alt", "brand": "Marke", "headline": "Altbestand",
                         "status": "aktiv", "missed_checks": 0}
    db.mark_stale("Marke", set(), "2026-08-08",
                  gepruefte_seiten={ZWEIT}, leitseite=LEIT)
    assert db.entries["alt"]["status"] == "aktiv"
    db.mark_stale("Marke", set(), "2026-08-08",
                  gepruefte_seiten={LEIT}, leitseite=LEIT)
    assert db.entries["alt"]["status"] == "evtl. ausgelaufen"


def test_ohne_seitenangabe_gilt_das_alte_verhalten(tmp_path):
    """Aufrufer, die keine Seiten kennen, bekommen die Bedeutung von vorher -
    sonst waere die Aenderung nicht rueckwaertskompatibel."""
    db = _db_mit_zwei_seiten(tmp_path)
    db.mark_stale("Marke", set(), "2026-08-08")
    assert all(e["status"] == "evtl. ausgelaufen" for e in db.entries.values())


# ------------------------------------------------------------------ Aufmass
def test_die_echte_konfiguration_hat_mehrere_seiten_je_marke():
    """Haelt die Zahl auf der Quellen-Unterseite gegen die Konfiguration. Eine
    Zahl auf der Seite ist erst wahr, wenn ein Test sie gegen die Daten haelt
    (CLAUDE.md) - und diese Rubrik behauptet auf ihrer Quellenseite eine
    Seitenzahl."""
    from pathlib import Path
    cfg = load_promo_config(Path(__file__).resolve().parents[1])
    assert cfg.page_count > len(cfg.sources), (
        "Mindestens eine Marke muss mehr als ihre Leitseite haben - sonst ist "
        "die Rubrik auf dem Stand vor dem 08.08.2026")
    # Kein Duplikat ueber die gesamte Konfiguration: dieselbe URL zweimal
    # abgefragt kostet je Lauf einen LLM-Aufruf und bringt nichts.
    alle = [p.url for s in cfg.sources for p in s.pages]
    assert len(alle) == len(set(alle))
    # Jede Marke traegt eine Leitseite, und die steht vorn.
    for s in cfg.sources:
        assert s.pages[0].url == s.url


def test_promo_source_pages_ist_kein_geteilter_zustand():
    """`pages` baut die Leitseite bei jedem Zugriff neu. Wer die Liste
    veraendert, darf die Quelle nicht veraendern."""
    src = PromoSource(name="M", url=LEIT, extra_pages=[PromoPage(url=ZWEIT)])
    seiten = src.pages
    seiten.append(PromoPage(url="https://marke.test/dritt"))
    assert len(src.pages) == 2
