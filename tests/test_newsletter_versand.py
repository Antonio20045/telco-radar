"""Store, Idempotenz, Limit-Waechter, Bounce-Abgleich.

Zwei Fehler sind hier teurer als alle anderen:

  * **Dieselbe Ausgabe geht zweimal raus.** Nicht rueckgaengig zu machen,
    kostet sofort Vertrauen. Ein Test simuliert deshalb einen Abbruch mitten
    im Versand und belegt, dass der Wiederanlauf nichts wiederholt.
  * **Das Tageslimit wird still gerissen.** Ein Teil der Empfaenger bekommt
    die Ausgabe, der Rest nicht - und zwar stumm. Der Waechter bricht ab,
    statt das zuzulassen.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from telco_radar.newsletter.config import lade_katalog
from telco_radar.newsletter.filters import Eintrag, Filtersatz, Treffer
from telco_radar.newsletter.render import Nachricht
from telco_radar.newsletter.segments import Segment
from telco_radar.newsletter import store as st
from telco_radar.newsletter import subscription as sub
from telco_radar.newsletter import versand as v
from telco_radar.newsletter.transport import Ergebnis, Trockenlauf

WURZEL = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(WURZEL)


def _nachricht(t="Betreff"):
    return Nachricht(betreff=t, html="<p>x</p>", text="x")


def _segment(h, abos, n_treffer=1):
    treffer = [Treffer(eintrag=Eintrag(id=f"e{i}", bereich="marktrecherche",
                                       titel=f"T{i}", text="", url="https://x/1"),
                       grund="filter") for i in range(n_treffer)]
    return Segment(hash=h, filter=Filtersatz(), abo_ids=list(abos),
                   treffer=treffer)


# ==============================================================  Store  ====

def test_eine_kaputte_zeile_kippt_nicht_den_ganzen_verteiler(tmp_path, caplog):
    """Eine halb geschriebene Zeile darf nicht dazu fuehren, dass ein Lauf
    den GANZEN Verteiler fuer leer haelt und ihn neu schreibt."""
    pfad = tmp_path / "subscribers.jsonl"
    pfad.write_text('{"id":"a"}\nKAPUTT{\n{"id":"b"}\n', encoding="utf-8")
    with caplog.at_level("ERROR"):
        zeilen = st.lies_jsonl(pfad)
    assert [z["id"] for z in zeilen] == ["a", "b"]
    # ... und der Inhalt der kaputten Zeile steht NICHT im Log - dort stuende
    # sonst eine Adresse.
    assert "KAPUTT" not in caplog.text


def test_zusammenfuehren_laesst_den_juengeren_satz_gewinnen():
    """Der Ersatz fuer `git pull --rebase`, der eine age-verschluesselte
    Datei nicht mischen kann: jeder Ciphertext ist bei jedem Schreibvorgang
    voellig anders, jeder Konflikt ein Binaerkonflikt."""
    alt = {"id": "s1", "state": "active", "created_at": "2026-08-01T00:00:00Z"}
    neu = {"id": "s1", "state": "unsubscribed", "created_at": "2026-08-01T00:00:00Z",
           "bounce": {"last": "2026-08-10T00:00:00Z"}}
    assert st.zusammenfuehren([alt], [neu])[0]["state"] == "unsubscribed"
    # ... und zwar unabhaengig von der Reihenfolge der Argumente.
    assert st.zusammenfuehren([neu], [alt])[0]["state"] == "unsubscribed"


def test_bei_gleichem_zeitstempel_gewinnt_der_weiter_fortgeschrittene():
    """Sonst haengt ein Widerruf davon ab, welcher Workflow zufaellig zuerst
    gepusht hat - und jemand bekommt nach seiner Abmeldung weiter Post."""
    a = {"id": "s1", "state": "active", "created_at": "2026-08-01T00:00:00Z"}
    b = {"id": "s1", "state": "unsubscribed", "created_at": "2026-08-01T00:00:00Z"}
    assert st.zusammenfuehren([a], [b])[0]["state"] == "unsubscribed"
    assert st.zusammenfuehren([b], [a])[0]["state"] == "unsubscribed"


def test_zusammenfuehren_verliert_kein_abo():
    unsere = [{"id": f"s{i}", "created_at": "2026-08-01T00:00:00Z"}
              for i in range(5)]
    fremde = [{"id": f"s{i}", "created_at": "2026-08-02T00:00:00Z"}
              for i in range(3, 9)]
    zusammen = st.zusammenfuehren(unsere, fremde)
    assert {z["id"] for z in zusammen} == {f"s{i}" for i in range(9)}


def test_zwei_gleichzeitige_bestaetigungen_gehen_nicht_verloren(tmp_path, katalog):
    """Zwei Workflows, die beide vor zwei Minuten gelesen haben: ohne das
    Nachlesen in `speichern()` ueberschreibt der zweite den ersten."""
    pfad = tmp_path / "subscribers.jsonl"
    st.schreibe_jsonl(pfad, [])
    a = st.AboStore(pfad, katalog)
    b = st.AboStore(pfad, katalog)
    a.setze(sub.Abo(id="s1", email="a@t.test", state="active",
                    created_at="2026-08-11T10:00:00Z"))
    b.setze(sub.Abo(id="s2", email="b@t.test", state="active",
                    created_at="2026-08-11T10:00:01Z"))
    a.speichern()
    b.speichern()
    assert {z["id"] for z in st.lies_jsonl(pfad)} == {"s1", "s2"}


def test_ein_abo_ist_ueber_seinen_kennwert_auffindbar(tmp_path, katalog):
    """Der Weg, der eine Abmeldung ueberlebt - danach ist die Adresse weg."""
    pfad = tmp_path / "subscribers.jsonl"
    kennwert = sub.adress_kennwert("p", "weg@t.test")
    st.schreibe_jsonl(pfad, [sub.als_dict(sub.Abo(
        id="s1", email="", email_hmac=kennwert, state="unsubscribed"))])
    store = st.AboStore(pfad, katalog)
    assert store.finde_ueber_kennwert(kennwert).id == "s1"
    assert store.aktive() == []


# =================================  Die 24-Stunden-Sperre (Mailbomben) =====

def test_dieselbe_adresse_bekommt_in_24_stunden_nur_eine_mail(tmp_path):
    """DER Mailbomben-Schutz. Er liegt hier und nicht im Signup-Dienst: dort
    ist der Zaehler nach jedem Spin-down leer, man muesste 16 Minuten
    warten."""
    pfad = tmp_path / "doi_log.jsonl"
    kennwert = "abc123"
    heute = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    assert st.doi_gesperrt(pfad, kennwert, heute=heute) is False
    st.doi_vermerken(pfad, kennwert, zeitpunkt="2026-08-11T09:00:00Z")
    assert st.doi_gesperrt(pfad, kennwert, heute=heute) is True
    # ... und eine ANDERE Adresse ist nicht gesperrt.
    assert st.doi_gesperrt(pfad, "anderer", heute=heute) is False


def test_die_sperre_laeuft_nach_24_stunden_ab(tmp_path):
    pfad = tmp_path / "doi_log.jsonl"
    st.doi_vermerken(pfad, "abc", zeitpunkt="2026-08-09T09:00:00Z")
    assert not st.doi_gesperrt(
        pfad, "abc", heute=datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc))


def test_ohne_kennwert_gibt_es_keine_mail(tmp_path):
    """Fail closed: ein Aufruf ohne Kennwert ist ein Programmfehler, und der
    darf keine Mail ausloesen."""
    assert st.doi_gesperrt(tmp_path / "doi_log.jsonl", "") is True


def test_im_doi_log_steht_keine_adresse(tmp_path):
    pfad = tmp_path / "doi_log.jsonl"
    st.doi_vermerken(pfad, sub.adress_kennwert("p", "wer@beispiel.test"),
                     token_id="t1")
    inhalt = pfad.read_text(encoding="utf-8")
    assert "beispiel.test" not in inhalt
    assert set(json.loads(inhalt.strip())) == {"addr_hmac", "token_id", "at"}


def test_das_doi_log_wird_aufgeraeumt(tmp_path):
    """Es beantwortet EINE Frage ueber 24 Stunden; alles Aeltere ist eine
    Sammlung ohne Zweck - Art. 5 Abs. 1 lit. e DSGVO."""
    pfad = tmp_path / "doi_log.jsonl"
    st.doi_vermerken(pfad, "alt", zeitpunkt="2026-06-01T00:00:00Z")
    st.doi_vermerken(pfad, "neu", zeitpunkt="2026-08-10T00:00:00Z")
    gefallen = st.doi_aufraeumen(
        pfad, tage=30, heute=datetime(2026, 8, 11, tzinfo=timezone.utc))
    assert gefallen == 1
    assert [e["addr_hmac"] for e in st.lies_jsonl(pfad)] == ["neu"]


# ==========================================================  Sendeplan  ====

def test_der_sendeplan_ist_deterministisch():
    """Beim Wiederanlauf muss derselbe Plan herauskommen - sonst haelt der
    Lauf seinen eigenen Plan fuer einen fremden und verschickt alles neu."""
    segmente = [_segment("h2", ["b", "a"]), _segment("h1", ["c"])]
    erste = [str(p.schluessel) for p in v.baue_sendeplan("2026-08-11", segmente)]
    zweite = [str(p.schluessel) for p in
              v.baue_sendeplan("2026-08-11", list(reversed(segmente)))]
    assert erste == zweite
    assert len(erste) == 3


def test_ein_leeres_segment_kommt_nicht_in_den_plan():
    """Zweimal pro Woche eine Mail, in der nichts steht, erzieht zum
    Ignorieren - und zwar nicht nur fuer die leeren Ausgaben."""
    leer = Segment(hash="h", filter=Filtersatz(), abo_ids=["a"], treffer=[])
    assert v.baue_sendeplan("2026-08-11", [leer]) == []


def test_der_schluessel_traegt_datum_segment_und_abo():
    plan = v.baue_sendeplan("2026-08-11", [_segment("hh", ["s1"])])
    assert str(plan[0].schluessel) == "2026-08-11|hh|s1"


# ==========================================================  Idempotenz  ===

def _log(pfad, *posten):
    st.schreibe_jsonl(pfad, [p.as_dict() for p in posten])


def test_ein_wiederanlauf_versendet_nichts_doppelt(tmp_path):
    """Der teuerste denkbare Fehler: 200 Manager bekommen den Bericht zum
    zweiten Mal."""
    log_pfad = tmp_path / "send_log.jsonl"
    plan = v.baue_sendeplan("2026-08-11", [_segment("h", ["a", "b", "c"])])
    nachrichten = {"h": _nachricht()}
    adressen = {i: f"{i}@t.test" for i in "abc"}
    protokoll = []

    def anhaengen(posten):
        protokoll.append(posten.as_dict())
        st.schreibe_jsonl(log_pfad, protokoll)

    erster = v.versende(plan, nachrichten, adressen, Trockenlauf(),
                        log_pfad=log_pfad, datum="2026-08-11",
                        protokollieren=anhaengen, rate_je_minute=0)
    assert erster.zugestellt == 3

    # Der Wiederanlauf: derselbe Plan, dasselbe Log.
    transport = Trockenlauf()
    plan2 = v.baue_sendeplan("2026-08-11", [_segment("h", ["a", "b", "c"])])
    zweiter = v.versende(plan2, nachrichten, adressen, transport,
                         log_pfad=log_pfad, datum="2026-08-11",
                         protokollieren=anhaengen, rate_je_minute=0)
    assert transport.versendet == []
    assert zweiter.zugestellt == 0
    assert zweiter.uebersprungen == 3


def test_ein_abbruch_mitten_im_versand_wird_genau_dort_fortgesetzt(tmp_path):
    """Weder alles noch nichts: die zwei zugestellten bleiben zugestellt,
    die dritte wird nachgeholt."""
    log_pfad = tmp_path / "send_log.jsonl"
    plan = v.baue_sendeplan("2026-08-11", [_segment("h", ["a", "b", "c"])])
    adressen = {i: f"{i}@t.test" for i in "abc"}
    protokoll = []

    def anhaengen(posten):
        protokoll.append(posten.as_dict())
        st.schreibe_jsonl(log_pfad, protokoll)

    class Abbruch(Trockenlauf):
        def send(self, nachricht, an):
            if len(self.versendet) >= 2:
                raise KeyboardInterrupt("Runner weg")
            return super().send(nachricht, an)

    with pytest.raises(KeyboardInterrupt):
        v.versende(plan, {"h": _nachricht()}, adressen, Abbruch(),
                   log_pfad=log_pfad, datum="2026-08-11",
                   protokollieren=anhaengen, rate_je_minute=0)
    assert len(st.lies_jsonl(log_pfad)) == 2

    weiter = Trockenlauf()
    nachher = v.versende(
        v.baue_sendeplan("2026-08-11", [_segment("h", ["a", "b", "c"])]),
        {"h": _nachricht()}, adressen, weiter, log_pfad=log_pfad,
        datum="2026-08-11", protokollieren=anhaengen, rate_je_minute=0)
    assert nachher.zugestellt == 1
    assert nachher.uebersprungen == 2
    assert len(weiter.versendet) == 1


def test_ein_wiederholbarer_fehler_kommt_nicht_ins_log(tmp_path):
    """Genau dafuer ist der Sendeplan da: der naechste Lauf findet den Posten
    als `geplant` ohne Bestaetigung und versucht es erneut."""
    log_pfad = tmp_path / "send_log.jsonl"
    protokoll = []

    class Klemmt(Trockenlauf):
        def send(self, nachricht, an):
            return Ergebnis(ok=False, status=503, dauerhaft=False)

    lauf = v.versende(v.baue_sendeplan("2026-08-11", [_segment("h", ["a"])]),
                      {"h": _nachricht()}, {"a": "a@t.test"}, Klemmt(),
                      log_pfad=log_pfad, datum="2026-08-11",
                      protokollieren=protokoll.append, rate_je_minute=0)
    assert lauf.fehler == 1 and lauf.zugestellt == 0
    assert protokoll == []


def test_ein_dauerhafter_fehler_kommt_ins_log(tmp_path):
    """Sonst versucht ihn jeder Wiederanlauf erneut - und verbrennt
    Tageskontingent an eine tote Adresse."""
    log_pfad = tmp_path / "send_log.jsonl"
    protokoll = []

    class Abgelehnt(Trockenlauf):
        def send(self, nachricht, an):
            return Ergebnis(ok=False, status=400, dauerhaft=True)

    lauf = v.versende(v.baue_sendeplan("2026-08-11", [_segment("h", ["a"])]),
                      {"h": _nachricht()}, {"a": "a@t.test"}, Abgelehnt(),
                      log_pfad=log_pfad, datum="2026-08-11",
                      protokollieren=protokoll.append, rate_je_minute=0)
    assert lauf.dauerhaft_fehl == ["a"]
    assert protokoll[0].status == "dauerhaft_fehl"


def test_ein_abo_ohne_adresse_gilt_als_erledigt(tmp_path):
    """Ein abgemeldetes Abo hat keine Adresse mehr. Kein Fehler - aber es
    gehoert ins Log, sonst versucht es jeder Wiederanlauf."""
    log_pfad = tmp_path / "send_log.jsonl"
    protokoll = []
    lauf = v.versende(v.baue_sendeplan("2026-08-11", [_segment("h", ["weg"])]),
                      {"h": _nachricht()}, {}, Trockenlauf(),
                      log_pfad=log_pfad, datum="2026-08-11",
                      protokollieren=protokoll.append, rate_je_minute=0)
    assert lauf.dauerhaft_fehl == ["weg"]
    assert protokoll[0].status == "dauerhaft_fehl"


# =======================================================  Limit-Waechter  ==

def test_der_waechter_bricht_vor_dem_teilversand_ab(tmp_path):
    """Ein stiller Teilversand, bei dem die halbe Liste die Ausgabe bekommt
    und die andere nicht, ist der schlimmste moegliche Ausgang."""
    log_pfad = tmp_path / "send_log.jsonl"
    with pytest.raises(v.LimitGerissen, match="bricht ab"):
        v.pruefe_limit(400, log_pfad, heute="2026-08-11")


def test_der_waechter_addiert_was_heute_schon_raus_ist(tmp_path):
    """Sonst reisst ein Wiederanlauf oder eine Testausgabe das Limit."""
    log_pfad = tmp_path / "send_log.jsonl"
    st.schreibe_jsonl(log_pfad, [
        {"key": f"k{i}", "status": "gesendet", "at": "2026-08-11T09:00:00Z"}
        for i in range(270)])
    assert v.heute_versendet(log_pfad, heute="2026-08-11") == 270
    v.pruefe_limit(10, log_pfad, heute="2026-08-11")           # 280, passt
    with pytest.raises(v.LimitGerissen):
        v.pruefe_limit(11, log_pfad, heute="2026-08-11")


def test_gestern_zaehlt_nicht_aufs_heutige_kontingent(tmp_path):
    log_pfad = tmp_path / "send_log.jsonl"
    st.schreibe_jsonl(log_pfad, [
        {"key": f"k{i}", "status": "gesendet", "at": "2026-08-10T09:00:00Z"}
        for i in range(299)])
    assert v.heute_versendet(log_pfad, heute="2026-08-11") == 0


def test_gezaehlt_wird_der_zustelltag_nicht_das_ausgabedatum(tmp_path):
    """Ein Wiederanlauf am Folgetag gehoert zum Kontingent des Folgetags."""
    log_pfad = tmp_path / "send_log.jsonl"
    st.schreibe_jsonl(log_pfad, [{"key": "k", "status": "gesendet",
                                  "date": "2026-08-11",
                                  "at": "2026-08-12T09:00:00Z"}])
    assert v.heute_versendet(log_pfad, heute="2026-08-11") == 0
    assert v.heute_versendet(log_pfad, heute="2026-08-12") == 1


def test_die_schwelle_liegt_unter_dem_harten_limit():
    """Die Reserve faengt die Bestaetigungsmails von Neuanmeldungen
    desselben Tages ab - die kommen aus einem anderen Workflow und tauchen
    im Sendeprotokoll gar nicht auf."""
    assert v.SCHWELLE < v.TAGESLIMIT == 300
    assert v.TAGESLIMIT - v.SCHWELLE >= 15


def test_der_abstand_zum_limit_wird_zurueckgegeben(tmp_path):
    """Er steht in jeder Statuszeile - damit sichtbar wird, wann der
    Verteiler an die Grenze waechst."""
    log_pfad = tmp_path / "send_log.jsonl"
    lauf = v.versende(v.baue_sendeplan("2026-08-11", [_segment("h", ["a"])]),
                      {"h": _nachricht()}, {"a": "a@t.test"}, Trockenlauf(),
                      log_pfad=log_pfad, datum="2026-08-11", rate_je_minute=0)
    assert lauf.abstand_zum_limit == v.SCHWELLE - 1


def test_der_waechter_laeuft_vor_der_ersten_zustellung(tmp_path):
    """Sonst waere der Abbruch selbst ein Teilversand."""
    log_pfad = tmp_path / "send_log.jsonl"
    st.schreibe_jsonl(log_pfad, [
        {"key": f"k{i}", "status": "gesendet", "at": "2026-08-11T09:00:00Z"}
        for i in range(279)])
    transport = Trockenlauf()
    plan = v.baue_sendeplan("2026-08-11", [_segment("h", ["a", "b", "c"])])
    with pytest.raises(v.LimitGerissen):
        v.versende(plan, {"h": _nachricht()},
                   {i: f"{i}@t.test" for i in "abc"}, transport,
                   log_pfad=log_pfad, datum="2026-08-11", rate_je_minute=0)
    assert transport.versendet == []


# ==========================================================  Drosselung  ===

def test_der_versand_wird_gedrosselt():
    """Ein gleichmaessiger Strom wird bei Empfaenger-Gateways anders bewertet
    als zweihundert Zustellungen in acht Sekunden."""
    pausen = []
    v.versende(v.baue_sendeplan("2026-08-11", [_segment("h", ["a", "b", "c"])]),
               {"h": _nachricht()}, {i: f"{i}@t.test" for i in "abc"},
               Trockenlauf(), log_pfad=Path("/nonexistent/send_log.jsonl"),
               datum="2026-08-11", rate_je_minute=30,
               schlafen=pausen.append)
    # Zwei Pausen bei drei Zustellungen - nach der letzten wird nicht mehr
    # gewartet.
    assert pausen == [2.0, 2.0]


# =======================================================  Bounce-Abgleich ==

def test_ein_hard_bounce_schaltet_sofort_ab():
    ergebnis = v.werte_ereignisse_aus(
        [{"event": "hard_bounce", "messageId": "m1", "date": "2026-08-11"}],
        {"m1": "sub_1"}, {})
    assert ergebnis.abgeschaltet == ["sub_1"]


def test_eine_beschwerde_schaltet_sofort_ab():
    """Eine steigende Beschwerdequote deaktiviert das Brevo-Free-Konto - und
    zwar ohne Vorwarnung."""
    ergebnis = v.werte_ereignisse_aus(
        [{"event": "complaint", "messageId": "m1"}], {"m1": "sub_1"}, {})
    assert ergebnis.abgeschaltet == ["sub_1"]


def test_ein_einzelner_soft_bounce_schaltet_nicht_ab():
    """Ein volles Postfach ist in drei Tagen wieder leer. Wer dafuer eine
    lebende Adresse wegwirft, verliert einen Leser fuer immer."""
    ergebnis = v.werte_ereignisse_aus(
        [{"event": "soft_bounce", "messageId": "m1"}], {"m1": "sub_1"}, {})
    assert ergebnis.abgeschaltet == []
    assert ergebnis.weich == ["sub_1"]


def test_fuenf_soft_bounces_in_folge_schalten_ab():
    ergebnis = v.werte_ereignisse_aus(
        [{"event": "soft_bounce", "messageId": "m1"}], {"m1": "sub_1"},
        {"sub_1": {"soft": 4}})
    assert ergebnis.abgeschaltet == ["sub_1"]


def test_zugeordnet_wird_ueber_die_message_id_nicht_ueber_die_adresse():
    """Die Adresse steht in den Ereignissen zwar drin, aber sie muesste dann
    durch dieses Modul und ins Log - und im Log darf keine stehen."""
    ergebnis = v.werte_ereignisse_aus(
        [{"event": "hard_bounce", "messageId": "unbekannt",
          "email": "wer@beispiel.test"}], {"m1": "sub_1"}, {})
    assert ergebnis.abgeschaltet == []
    assert ergebnis.unbekannt == 1


def test_der_letzte_zeitpunkt_wird_festgehalten():
    """Damit Ereignisse nicht doppelt laufen - ein zweimal gezaehlter Soft
    Bounce schaltet eine lebende Adresse ab."""
    ergebnis = v.werte_ereignisse_aus(
        [{"event": "soft_bounce", "messageId": "m1", "date": "2026-08-09"},
         {"event": "soft_bounce", "messageId": "m1", "date": "2026-08-11"}],
        {"m1": "sub_1"}, {})
    assert ergebnis.letzter_zeitpunkt == "2026-08-11"


def test_die_zustellquote_rechnet_gegen_die_versuchten():
    lauf = v.Lauf(datum="2026-08-11", geplant=10, uebersprungen=4,
                  zugestellt=5, fehler=1)
    assert v.zustellquote(lauf) == round(5 / 6, 4)
    assert v.zustellquote(v.Lauf(datum="x")) == 1.0


# ==========================  Keine Adresse im oeffentlichen Repo  ==========

def test_keine_jsonl_im_repo_enthaelt_ein_adressmuster():
    """Ein Commit mit einer Adressliste ist ueber Git-Historie und Forks
    dauerhaft oeffentlich - und ein meldepflichtiger Vorfall nach Art. 33
    DSGVO mit 72-Stunden-Frist, kein Bug, den man wegrebased."""
    import re
    muster = re.compile(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", re.I)
    # Die eigene Adresse des Absenders steht bewusst in den Rechtstexten und
    # im Absender - sie ist kein Abonnent.
    erlaubt = {"antonio.fotiadis.francisco@gmail.com", "noreply@anthropic.com"}
    treffer = []
    for pfad in WURZEL.rglob("*.jsonl"):
        if ".git/" in str(pfad):
            continue
        try:
            inhalt = pfad.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        gefunden = {t.lower() for t in muster.findall(inhalt)} - erlaubt
        if gefunden:
            treffer.append((str(pfad.relative_to(WURZEL)), sorted(gefunden)[:3]))
    assert not treffer, f"Adressen in einer JSONL des oeffentlichen Repos: {treffer}"
