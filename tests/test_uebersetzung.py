"""Wahrheitstests der Volltext-Uebersetzung.

Die Regeln, die hier festgenagelt werden, sind die, an denen das Feature
laut Premortem stirbt - nicht die, die sich leicht pruefen lassen:

  - die Sprache wird auf dem TEXT gemessen, nie auf der Ueberschrift
  - ein Grenzfall wird verworfen, nicht geraten
  - ein zu kurzer Extrakt bekommt keinen Link (absolut, nicht als Faktor)
  - eine Zusammenfassung statt einer Uebersetzung faellt durch
  - die Stufe kostet den Bericht nie
  - der Link zum Original bleibt stehen
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from telco_radar.models import Item
from telco_radar.uebersetzung import sprache as sprache_mod
from telco_radar.uebersetzung import stufe as stufe_mod
from telco_radar.uebersetzung import uebersetzer as u_mod
from telco_radar.uebersetzung import volltext as volltext_mod
from telco_radar.uebersetzung.store import (
    UebersetzungsStore, Uebersetzung, text_hash)


# --------------------------------------------------------------- Fixtures
SPANISCH = (
    "SpaceX ha conseguido algo extraordinariamente dificil, hacer que lanzar "
    "satelites parezca sencillo. La cadencia de lanzamientos de la compania y "
    "su capacidad industrial han cambiado por completo el mercado de las "
    "comunicaciones por satelite en los ultimos anos. Los operadores moviles "
    "observan con atencion como Starlink amplia su oferta directa al cliente "
    "final, algo que hasta ahora dependia de acuerdos con las operadoras "
    "nacionales en cada uno de los mercados donde presta servicio. "
) * 3

ENGLISCH = (
    "The operator said the new network slicing trial will run across three "
    "cities during the second half of the year, with commercial availability "
    "expected once the regulator signs off on the spectrum arrangement. "
    "Analysts noted that the deal follows a similar agreement announced by a "
    "rival carrier earlier this quarter, and that pricing details have not "
    "yet been disclosed to the market. "
) * 3


def _item(**kw):
    basis = dict(title="Titel", url="https://beispiel.test/artikel/1",
                 source_name="Testquelle")
    basis.update(kw)
    return Item(**basis)


# ------------------------------------------------------------- Spracherkennung
def test_spanischer_fliesstext_wird_erkannt():
    fremd, kuerzel, _ = sprache_mod.ist_fremdsprachig(SPANISCH)
    assert fremd is True
    assert kuerzel == "es"


def test_englischer_fliesstext_gilt_als_fremdsprachig():
    """Entscheidung vom 27.08.2026: die Zielgruppe (deutsche Manager ohne
    sicheres Englisch, CLAUDE.md §1) liest Englisch nicht ohnehin. Bis dahin
    stand "en" neben "de" in MUTTERSPRACHEN und 143 von 163 vorgefilterten
    Meldungen des Laufs vom 27.08. waren englisch - keine davon wurde je
    uebersetzt. Gegen den alten Stand faellt dieser Test."""
    fremd, kuerzel, _ = sprache_mod.ist_fremdsprachig(ENGLISCH)
    assert fremd is True
    assert kuerzel == "en"


def test_deutscher_text_bekommt_keine_uebersetzung():
    """Die einzige echte Muttersprache, die uebrig bleibt (E5, 27.08.2026)."""
    text = ("Die Bundesnetzagentur hat am Mittwoch mitgeteilt, dass die "
            "Vergabe der Frequenzen im kommenden Jahr stattfinden soll. Die "
            "Behoerde nannte dabei weder einen genauen Termin noch die "
            "Bedingungen, unter denen die Anbieter mitbieten duerfen. ") * 3
    fremd, kuerzel, _ = sprache_mod.ist_fremdsprachig(text)
    assert fremd is False
    assert kuerzel == "de"


def test_zu_kurzer_text_wird_verworfen_statt_geraten():
    """Unter MINDESTZEICHEN wird gar nicht erst gemessen."""
    kuerzel, sicherheit = sprache_mod.erkenne_sprache("Orange lance sa 5G")
    assert kuerzel == ""
    assert sicherheit == 0.0


def test_die_ueberschrift_allein_entscheidet_nie():
    """Der Kern von Premortem 4, an einem echten Fehlschlag festgenagelt.

    Diese drei Ueberschriften wurden am 13.08.2026 gegen das Berichtsarchiv
    gemessen und dort als Italienisch, Franzoesisch und Spanisch eingestuft
    - alle drei sind englisch. Ein Aufrufer, der nur den Titel uebergibt,
    bekommt hier deshalb IMMER "unbestimmt": der Titel ist kuerzer als
    MINDESTZEICHEN, und damit greift die Enthaltung.
    """
    for titel in (
        "Airtel Africa hires more investment banks for mobile money IPO",
        "AT&T, Ericsson demonstrate drone-sensing 5G capabilities",
        "CMA clears Paramount-WBD deal",
    ):
        fremd, _, _ = sprache_mod.ist_fremdsprachig(titel)
        assert fremd is False, f"{titel!r} wurde faelschlich als fremd erkannt"


def test_titel_verschiebt_das_ergebnis_des_fliesstexts_nicht():
    """Ein englischer Titel ueber spanischem Text bleibt spanisch."""
    fremd, kuerzel, _ = sprache_mod.ist_fremdsprachig(
        SPANISCH, titel="Starlink and the temptation to compete with partners")
    assert (fremd, kuerzel) == (True, "es")


def test_sprachname_faellt_auf_das_kuerzel_zurueck():
    assert sprache_mod.sprachname("tr") == "Türkisch"
    assert sprache_mod.sprachname("xx") == "XX"


# ------------------------------------------------------------------ Volltext
def test_feedvolltext_wird_ohne_abruf_genommen():
    item = _item(volltext="x" * 2000, summary="kurz")
    ergebnis = volltext_mod.hole_volltext(item, {}, artikelabruf=False)
    assert ergebnis.erfolg is True
    assert ergebnis.herkunft == "feed"
    assert ergebnis.status == 0, "es darf kein Abruf stattgefunden haben"


def test_zu_kurzer_extrakt_bekommt_keinen_link(monkeypatch):
    """Premortem 1, am echten Fall digi.no.

    45 Zeichen Teaser, 141 Zeichen Extrakt hinter einer Paywall. Als
    Faktor gerechnet waeren das 3,1x und damit ein Treffer - deshalb ist
    die Schwelle absolut.
    """
    monkeypatch.setattr(volltext_mod, "fetch",
                        lambda *a, **k: SimpleNamespace(status_code=200,
                                                        text="<html/>"))
    monkeypatch.setattr(volltext_mod, "_extrahiere", lambda h: "x" * 141)
    item = _item(summary="x" * 45)
    ergebnis = volltext_mod.hole_volltext(item, {})
    assert ergebnis.erfolg is False
    assert "zu kurz" in ergebnis.grund
    # Gegenprobe: als Faktor gerechnet HAETTE der Fall bestanden.
    assert 141 > volltext_mod.MINDESTFAKTOR * 45


def test_extrakt_der_nur_den_teaser_wiederholt_faellt_durch(monkeypatch):
    monkeypatch.setattr(volltext_mod, "fetch",
                        lambda *a, **k: SimpleNamespace(status_code=200,
                                                        text="<html/>"))
    monkeypatch.setattr(volltext_mod, "_extrahiere", lambda h: "y" * 1400)
    item = _item(summary="y" * 1300)
    ergebnis = volltext_mod.hole_volltext(item, {})
    assert ergebnis.erfolg is False
    assert "Teaser" in ergebnis.grund


def test_sammelseite_wird_verworfen(monkeypatch):
    monkeypatch.setattr(volltext_mod, "fetch",
                        lambda *a, **k: SimpleNamespace(status_code=200,
                                                        text="<html/>"))
    monkeypatch.setattr(volltext_mod, "_extrahiere",
                        lambda h: "z" * (volltext_mod.HOECHSTLAENGE + 1))
    ergebnis = volltext_mod.hole_volltext(_item(), {})
    assert ergebnis.erfolg is False
    assert "zu lang" in ergebnis.grund


def test_gesperrte_seite_nennt_ihren_status(monkeypatch):
    monkeypatch.setattr(volltext_mod, "fetch",
                        lambda *a, **k: SimpleNamespace(status_code=403,
                                                        text=""))
    ergebnis = volltext_mod.hole_volltext(_item(), {})
    assert ergebnis.erfolg is False
    assert ergebnis.status == 403
    assert "403" in ergebnis.grund


def test_abgeschalteter_artikelabruf_ruft_nicht_ab(monkeypatch):
    def _nie(*a, **k):
        raise AssertionError("es darf kein Abruf stattfinden")
    monkeypatch.setattr(volltext_mod, "fetch", _nie)
    ergebnis = volltext_mod.hole_volltext(_item(), {}, artikelabruf=False)
    assert ergebnis.erfolg is False


# ---------------------------------------------------------------- Uebersetzer
def test_zusammenfassung_statt_uebersetzung_faellt_durch(monkeypatch):
    """Der Auftrag lautet vollstaendig, nicht kurz."""
    monkeypatch.setattr(u_mod.llm, "complete", lambda *a, **k: "Zu kurz.")
    with pytest.raises(u_mod.UebersetzungFehlgeschlagen) as exc:
        u_mod.uebersetze("a" * 4000, "es", "modell")
    assert "zusammengefasst" in str(exc.value)


def test_leere_antwort_faellt_durch(monkeypatch):
    monkeypatch.setattr(u_mod.llm, "complete", lambda *a, **k: "")
    with pytest.raises(u_mod.UebersetzungFehlgeschlagen):
        u_mod.uebersetze("a" * 2000, "es", "modell")


def test_absaetze_bleiben_erhalten(monkeypatch):
    monkeypatch.setattr(
        u_mod.llm, "complete",
        lambda system, user, *a, **k: "Erster Absatz. " * 8 + "\n\n"
                                      + "Zweiter Absatz. " * 8)
    _, absaetze = u_mod.uebersetze("kurz " * 40, "es", "modell")
    assert len(absaetze) == 2
    assert absaetze[0].startswith("Erster Absatz.")
    assert absaetze[1].startswith("Zweiter Absatz.")


def test_langer_artikel_wird_abschnittsweise_uebersetzt(monkeypatch):
    """Ein Absatz wird nie zerrissen, und alle Abschnitte gehen hinaus."""
    aufrufe = []

    def _complete(system, user, *a, **k):
        aufrufe.append(user)
        # Wie ein echtes Modell: nur den Artikeltext zurueck, ohne die
        # Kopfzeile und ohne den Abschnittshinweis.
        return user.split(")\n\n", 1)[-1].split(":\n\n", 1)[-1]

    monkeypatch.setattr(u_mod.llm, "complete", _complete)
    absatz = "Satz. " * 200            # ~1200 Zeichen
    text = "\n\n".join([absatz] * 10)  # ~12 000 Zeichen -> mehrere Abschnitte
    _, absaetze = u_mod.uebersetze(text, "es", "modell")
    assert len(aufrufe) > 1, "der Text haette gebuendelt werden muessen"
    assert len(absaetze) == 10, "kein Absatz darf verloren gehen"


def test_vorrede_des_modells_wird_entfernt(monkeypatch):
    monkeypatch.setattr(
        u_mod.llm, "complete",
        lambda *a, **k: "Hier ist die Übersetzung:\n\n" + "Inhalt. " * 60)
    _, absaetze = u_mod.uebersetze("x" * 300, "es", "modell")
    assert not absaetze[0].lower().startswith("hier ist")


def test_gescheiterter_titel_kostet_nicht_die_uebersetzung(monkeypatch):
    """Eine spanische Ueberschrift ist unschoen, eine fehlende Seite schlimmer."""
    def _complete(system, user, *a, **k):
        if system == u_mod.TITEL_SYSTEM:
            raise RuntimeError("Titel kaputt")
        return "Inhalt. " * 60

    monkeypatch.setattr(u_mod.llm, "complete", _complete)
    titel_de, absaetze = u_mod.uebersetze("x" * 300, "es", "modell",
                                          titel="Titulo original")
    assert titel_de == ""
    assert absaetze


# --------------------------------------------------------------------- Store
def test_store_haelt_je_meldung_genau_einen_stand(tmp_path):
    pfad = tmp_path / "u.jsonl"
    store = UebersetzungsStore(pfad)
    for titel in ("erste", "zweite"):
        store.add(Uebersetzung(item_id="abc", quell_hash=text_hash(titel),
                               titel_de=titel, absaetze=["x"]))
    store.speichern()
    assert len(UebersetzungsStore(pfad)) == 1
    assert UebersetzungsStore(pfad).get("abc").titel_de == "zweite"


def test_neuer_textstand_gilt_als_nicht_uebersetzt(tmp_path):
    store = UebersetzungsStore(tmp_path / "u.jsonl")
    store.add(Uebersetzung(item_id="abc", quell_hash=text_hash("alt"),
                           titel_de="t", absaetze=["x"]))
    assert store.hat_aktuelle("abc", "alt") is True
    assert store.hat_aktuelle("abc", "neu") is False


def test_kaputte_zeile_kostet_nicht_den_bestand(tmp_path):
    pfad = tmp_path / "u.jsonl"
    gut = json.dumps(Uebersetzung(item_id="ok", quell_hash="h",
                                  titel_de="t", absaetze=["x"]).to_dict())
    pfad.write_text("{kaputt\n" + gut + "\n", encoding="utf-8")
    assert len(UebersetzungsStore(pfad)) == 1


# --------------------------------------------------------------------- Stufe
def test_budget_rechnet_gegen_die_restzeit_des_jobs():
    """Die Lehre aus Lauf 31422689829 - gegen den JOB, nicht gegen sich selbst."""
    settings = {"job_frist_sekunden": 3000,
                "veroeffentlichung_reserve_sekunden": 420,
                "uebersetzung_frist_sekunden": 600}
    assert stufe_mod.budget(settings, 100) == 600.0
    # Nur noch 380 s bis zur Reserve -> weniger als die eigene Frist.
    assert stufe_mod.budget(settings, 2200) == pytest.approx(380.0)
    # Die Reserve ist angebrochen -> gar nicht erst anfangen.
    assert stufe_mod.budget(settings, 2590) is None


def test_abgeschaltet_heisst_kein_budget():
    assert stufe_mod.budget({"uebersetzung_enabled": False}, 0) is None


def test_ein_kaputter_artikel_kostet_nie_den_lauf(tmp_path, monkeypatch):
    """Die wichtigste Zusicherung der ganzen Stufe."""
    monkeypatch.setattr(stufe_mod, "hole_volltext",
                        lambda *a, **k: (_ for _ in ()).throw(
                            RuntimeError("kaputt")))
    bilanz = stufe_mod.lauf([_item()], tmp_path, {}, "modell",
                            frist_sekunden=30, heute=date(2026, 8, 13))
    assert bilanz["gescheitert"] == 1
    assert bilanz["uebersetzt"] == 0


def test_englischer_artikel_wird_uebersetzt(tmp_path, monkeypatch):
    """Entscheidung vom 27.08.2026 (E5): Englisch ist keine Muttersprache
    mehr. Gegen den alten Stand faellt dieser Test - dort verwarf die
    Vorauswahl den Artikel vor jedem Abruf."""
    monkeypatch.setattr(stufe_mod, "uebersetze",
                        lambda *a, **k: ("Deutscher Titel", ["Ein Absatz."]))
    monkeypatch.setattr(stufe_mod, "hole_volltext",
                        lambda *a, **k: volltext_mod.VolltextErgebnis(
                            text=ENGLISCH, herkunft="feed"))
    item = _item(volltext=ENGLISCH)
    bilanz = stufe_mod.lauf([item], tmp_path, {}, "modell",
                            frist_sekunden=30, heute=date(2026, 8, 13))
    assert bilanz["uebersetzt"] == 1
    assert bilanz["sprachen"]["en"] == 1


def test_spanischer_artikel_landet_im_speicher(tmp_path, monkeypatch):
    monkeypatch.setattr(stufe_mod, "uebersetze",
                        lambda *a, **k: ("Deutscher Titel", ["Ein Absatz."]))
    item = _item(volltext=SPANISCH, title="Titulo")
    bilanz = stufe_mod.lauf([item], tmp_path, {}, "modell",
                            frist_sekunden=30, heute=date(2026, 8, 13))
    assert bilanz["uebersetzt"] == 1
    assert bilanz["aus_feed"] == 1
    gespeichert = UebersetzungsStore(
        tmp_path / "data" / "state" / "uebersetzungen.jsonl")
    assert len(gespeichert) == 1
    u = gespeichert.get(item.id)
    assert u.titel_de == "Deutscher Titel"
    assert u.url == item.url, "der Link zum Original muss erhalten bleiben"
    assert u.sprache == "es"


def test_der_deckel_wird_eingehalten(tmp_path, monkeypatch):
    monkeypatch.setattr(stufe_mod, "uebersetze",
                        lambda *a, **k: ("T", ["Absatz"]))
    items = [_item(url=f"https://beispiel.test/a/{i}", volltext=SPANISCH)
             for i in range(10)]
    bilanz = stufe_mod.lauf(items, tmp_path, {"uebersetzung_max_je_lauf": 3},
                            "modell", frist_sekunden=30,
                            heute=date(2026, 8, 13))
    assert bilanz["uebersetzt"] == 3


def test_schon_uebersetztes_kostet_keinen_zweiten_modellaufruf(tmp_path,
                                                               monkeypatch):
    aufrufe = []
    monkeypatch.setattr(stufe_mod, "uebersetze",
                        lambda *a, **k: (aufrufe.append(1), ("T", ["A"]))[1])
    item = _item(volltext=SPANISCH)
    for _ in range(2):
        stufe_mod.lauf([item], tmp_path, {}, "modell", frist_sekunden=30,
                       heute=date(2026, 8, 13))
    assert len(aufrufe) == 1


def test_protokollzeile_nennt_die_gruende():
    bilanz = stufe_mod.lauf([], Path("/tmp"), {"uebersetzung_enabled": True},
                            "m", frist_sekunden=1, heute=date(2026, 8, 13))
    zeile = stufe_mod.protokollzeile(bilanz)
    assert "Uebersetzung:" in zeile
    assert "uebersetzt" in zeile and "gescheitert" in zeile
