"""CT-Radar: laeuft gegen eine gespeicherte certspotter-Antwort, nie gegen Netz.

Das Fixture ist eine ECHTE Antwort vom 08.08.2026 fuer congstar.de, nur um
Dubletten gekuerzt. Es traegt genau die Faelle, an denen dieses Modul scheitern
kann: einen Kampagnennamen (`adventskalender`), eine Zweitmarke
(`jamobil-news`), reine Infrastruktur (`sso`, `cdn`, `mail`) und ein Wildcard
(`*.congstar.de`).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from telco_radar.collect import ct_log
from telco_radar.collect.ct_log import (
    CTFehler, CTSpeicher, CTZeitueberschreitung, Domain, Fund, als_item,
    bewerte, hole, ist_technisch, lade_domains, namen_aus_antwort, sammle,
)

FIXTURE = Path(__file__).parent / "fixtures" / "ct" / "certspotter_congstar.json"
JETZT = datetime(2026, 8, 8, tzinfo=timezone.utc)


@pytest.fixture
def antwort() -> list:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Namen aus der Antwort
# --------------------------------------------------------------------------- #

def test_namen_aus_echter_antwort(antwort):
    namen = namen_aus_antwort(antwort)
    assert "jamobil-news.congstar.de" in namen
    assert "adventskalender.congstar.de" in namen
    # Die Antwort deckt auch Namen ausserhalb der abgefragten Domain ab -
    # genau das macht sie wertvoll (congstar betreibt congstarnews.de).
    assert "pennymobil.congstarnews.de" in namen


def test_wildcards_fliegen_raus(antwort):
    """`*.congstar.de` ist kein vorbereiteter Dienst.

    Es taucht bei jeder Zertifikatserneuerung auf und saehe jedes Mal wie
    eine Neuigkeit aus.
    """
    assert "*.congstar.de" not in namen_aus_antwort(antwort)


def test_namen_werden_kleingeschrieben_und_entpunktet():
    daten = [{"dns_names": ["Shop.Congstar.DE", "news.congstar.de."]}]
    assert namen_aus_antwort(daten) == {"shop.congstar.de", "news.congstar.de"}


def test_unerwartete_antwortform_wirft():
    """Ein Dict statt einer Liste heisst API-Aenderung, nicht 'keine Treffer'."""
    with pytest.raises(CTFehler):
        namen_aus_antwort({"fehler": "nope"})


def test_muell_in_der_liste_wird_uebersprungen():
    assert namen_aus_antwort([None, "x", {"dns_names": ["a.de"]}]) == {"a.de"}


# --------------------------------------------------------------------------- #
# Rauschfilter
# --------------------------------------------------------------------------- #

RAUSCHEN = ["sso", "mail", "cdn", "staging", "test", "api"]


@pytest.mark.parametrize("name", [
    "sso.congstar.de", "mail.congstar.de", "cdn.congstar.de",
    "staging.congstar.de", "api.o2online.de",
])
def test_technische_namen_werden_erkannt(name):
    assert ist_technisch(name, RAUSCHEN)


@pytest.mark.parametrize("name", [
    "jamobil-news.congstar.de", "adventskalender.congstar.de",
    "freundewerben.congstar.de", "handyankauf.congstar.de",
    "pennymobil.congstarnews.de",
])
def test_kampagnennamen_ueberleben_den_filter(name):
    assert not ist_technisch(name, RAUSCHEN)


def test_filter_vergleicht_label_nicht_teilketten():
    """Der Fehler, der die beste Meldung des Radars geloescht haette.

    `news.congstar.de` enthaelt "ns" als Teilkette. Ein Teilkettenfilter mit
    einem Muster "ns" haette den Namen verworfen.
    """
    assert not ist_technisch("news.congstar.de", ["ns"])


def test_registrierungsdomain_wird_nicht_geprueft():
    """`mail.de` als Anbieterdomain waere sonst komplett unsichtbar."""
    assert not ist_technisch("mail.de", ["mail"])
    assert ist_technisch("x.mail.de", ["x"])


def test_leere_rauschliste_filtert_nichts():
    assert not ist_technisch("sso.congstar.de", [])


# --------------------------------------------------------------------------- #
# Speicher und Grundlinie
# --------------------------------------------------------------------------- #

def test_speicher_haelt_ueber_neuladen(tmp_path):
    p = tmp_path / "ct_seen.jsonl"
    s = CTSpeicher(p)
    assert not s.kennt("congstar.de")
    s.setze("congstar.de", {"a.congstar.de", "b.congstar.de"}, "2026-08-08")
    s.speichern()

    zweiter = CTSpeicher(p)
    assert zweiter.kennt("congstar.de")
    assert zweiter.namen("congstar.de") == {"a.congstar.de", "b.congstar.de"}


def test_speicher_ueberliest_kaputte_zeilen(tmp_path):
    p = tmp_path / "ct_seen.jsonl"
    p.write_text('{"domain":"a.de","namen":["x.a.de"]}\nkein json\n\n',
                 encoding="utf-8")
    s = CTSpeicher(p)
    assert s.namen("a.de") == {"x.a.de"}


# --------------------------------------------------------------------------- #
# hole(): der Timeout ist eine eigene Klasse, kein leeres Ergebnis
# --------------------------------------------------------------------------- #

class _Client:
    def __init__(self, wirkung):
        self.wirkung = wirkung
        self.gesehen = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.gesehen.append({"url": url, "params": params, "timeout": timeout})
        if isinstance(self.wirkung, Exception):
            raise self.wirkung
        return self.wirkung


def _antwort(status=200, daten=None, text=None):
    return httpx.Response(
        status_code=status,
        json=daten if text is None else None,
        text=text,
        request=httpx.Request("GET", ct_log.API),
    )


def test_timeout_wirft_eigene_klasse():
    client = _Client(httpx.TimeoutException("zu langsam"))
    with pytest.raises(CTZeitueberschreitung):
        hole(Domain(marke="Telekom", domain="telekom.de", gross=True), {},
             client=client)


def test_timeout_ist_kein_ct_fehler_zufall():
    """Die Unterklasse muss von CTFehler erben - sonst faengt sammle() sie
    im falschen Zweig und zaehlt sie als gewoehnlichen Fehler."""
    assert issubclass(CTZeitueberschreitung, CTFehler)


def test_grosse_domain_bekommt_laengere_frist():
    client = _Client(_antwort(daten=[]))
    hole(Domain(marke="Telekom", domain="telekom.de", gross=True), {},
         client=client)
    assert client.gesehen[0]["timeout"] == ct_log.FRIST_GROSS

    client2 = _Client(_antwort(daten=[]))
    hole(Domain(marke="congstar", domain="congstar.de"), {}, client=client2)
    assert client2.gesehen[0]["timeout"] == ct_log.FRIST_NORMAL


def test_drosselung_wird_als_fehler_gemeldet():
    with pytest.raises(CTFehler, match="429"):
        hole(Domain(marke="x", domain="x.de"), {},
             client=_Client(_antwort(status=429)))


def test_kein_json_wirft():
    with pytest.raises(CTFehler, match="kein JSON"):
        hole(Domain(marke="x", domain="x.de"), {},
             client=_Client(_antwort(text="<html>")))


def test_abfrage_nutzt_subdomains_und_expand():
    """Ohne include_subdomains liefert die API nur die Domain selbst - und
    damit nie eine neue Subdomain, also nie ein Signal."""
    client = _Client(_antwort(daten=[]))
    hole(Domain(marke="congstar", domain="congstar.de"), {}, client=client)
    p = client.gesehen[0]["params"]
    assert p["include_subdomains"] == "true"
    assert p["expand"] == "dns_names"


# --------------------------------------------------------------------------- #
# sammle(): Grundlinie, Delta, Deckel
# --------------------------------------------------------------------------- #

def _repo(tmp_path: Path, domains: str, rauschen: list[str]) -> Path:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "state").mkdir(parents=True, exist_ok=True)
    rausch_yaml = "\n".join(f"  - {r}" for r in rauschen)
    (tmp_path / "config" / "ct_domains.yaml").write_text(
        f"domains:\n{domains}\nrauschen:\n{rausch_yaml}\n", encoding="utf-8")
    return tmp_path


EINE = "  - marke: congstar\n    domain: congstar.de\n    konzern: Telekom\n"


def test_erster_lauf_meldet_nichts_und_legt_grundlinie(tmp_path, antwort):
    """Ohne diese Regel bestuende die erste Ausgabe aus 47 'neuen' Subdomains,
    die alle seit Jahren existieren."""
    root = _repo(tmp_path, EINE, ["sso", "cdn"])
    items, bilanz = sammle(root, {}, jetzt=JETZT,
                           client=_Client(_antwort(daten=antwort)))
    assert items == []
    assert bilanz["grundlinie"] == 1
    assert (root / "data" / "state" / "ct_seen.jsonl").exists()


def test_zweiter_lauf_meldet_nur_den_zuwachs(tmp_path, antwort):
    root = _repo(tmp_path, EINE, ["sso", "cdn", "mail"])
    sammle(root, {}, jetzt=JETZT, client=_Client(_antwort(daten=antwort)))

    plus = antwort + [{"dns_names": ["wechselbonus2027.congstar.de"],
                       "not_before": "2026-08-07T10:00:00Z"}]
    items, bilanz = sammle(root, {}, jetzt=JETZT,
                           client=_Client(_antwort(daten=plus)))
    assert [i.title for i in items] == [
        "congstar: neue Subdomain wechselbonus2027.congstar.de"]
    assert bilanz["neu_roh"] == 1


def test_technischer_zuwachs_wird_unterdrueckt(tmp_path, antwort):
    root = _repo(tmp_path, EINE, ["grafana"])
    sammle(root, {}, jetzt=JETZT, client=_Client(_antwort(daten=antwort)))

    plus = antwort + [{"dns_names": ["grafana.congstar.de"],
                       "not_before": "2026-08-07T10:00:00Z"}]
    items, bilanz = sammle(root, {}, jetzt=JETZT,
                           client=_Client(_antwort(daten=plus)))
    assert items == []
    assert bilanz["technisch"] == 1


def test_zeitueberschreitung_laesst_die_grundlinie_unberuehrt(tmp_path, antwort):
    """Der teuerste denkbare Fehler dieses Moduls: den Timeout als leeres
    Ergebnis speichern. Danach waere die Grundlinie leer, und der naechste
    Lauf meldete alle 47 Namen als neu."""
    root = _repo(tmp_path, EINE, [])
    sammle(root, {}, jetzt=JETZT, client=_Client(_antwort(daten=antwort)))
    vorher = CTSpeicher(root / "data" / "state" / "ct_seen.jsonl").namen(
        "congstar.de")
    assert vorher

    items, bilanz = sammle(root, {}, jetzt=JETZT,
                           client=_Client(httpx.TimeoutException("zu lang")))
    assert items == []
    assert bilanz["zeitueberschreitung"] == 1
    nachher = CTSpeicher(root / "data" / "state" / "ct_seen.jsonl").namen(
        "congstar.de")
    assert nachher == vorher


def test_umbau_wird_nicht_gemeldet(tmp_path, antwort):
    root = _repo(tmp_path, EINE, [])
    sammle(root, {}, jetzt=JETZT, client=_Client(_antwort(daten=antwort)))

    viele = antwort + [{"dns_names": [f"neu{i}.congstar.de"],
                        "not_before": "2026-08-07T10:00:00Z"}
                       for i in range(ct_log.MAX_JE_DOMAIN + 1)]
    items, bilanz = sammle(root, {}, jetzt=JETZT,
                           client=_Client(_antwort(daten=viele)))
    assert items == []
    assert bilanz["zu_viele"] == 1


def test_fehlende_config_ist_kein_absturz(tmp_path):
    items, bilanz = sammle(tmp_path, {}, jetzt=JETZT)
    assert items == []
    assert bilanz["domains"] == 0


def test_lade_domains_liest_gross_flag(tmp_path):
    root = _repo(tmp_path,
                 "  - marke: Telekom\n    domain: telekom.de\n    gross: true\n",
                 ["sso"])
    domains, rauschen = lade_domains(root)
    assert domains[0].gross and domains[0].frist == ct_log.FRIST_GROSS
    assert rauschen == ["sso"]


def test_echte_config_ist_ladbar():
    """Die ausgelieferte Config muss sich laden lassen - sonst faellt der
    Radar im Lauf still aus."""
    domains, rauschen = lade_domains(Path(__file__).resolve().parents[1])
    assert len(domains) >= 10
    assert "sso" in rauschen and "cdn" in rauschen
    assert any(d.domain == "congstar.de" for d in domains)
    # telekom.de MUSS als gross markiert sein, sonst laeuft jeder Lauf in
    # einen vermeidbaren Timeout.
    assert any(d.domain == "telekom.de" and d.gross for d in domains)


# --------------------------------------------------------------------------- #
# Modellstufe
# --------------------------------------------------------------------------- #

def _fund(name: str) -> Fund:
    return Fund(domain=Domain(marke="congstar", domain="congstar.de"), name=name)


def test_modell_sortiert_infrastruktur_aus():
    funde = [_fund("adventskalender.congstar.de"), _fund("acs.congstar.de")]

    def fake(system, user, modell, max_tokens):
        return json.dumps({"namen": [
            {"name": "adventskalender.congstar.de", "art": "kampagne",
             "begruendung": "Aktionsname"},
            {"name": "acs.congstar.de", "art": "infrastruktur",
             "begruendung": "Auto Config Server"},
        ]})

    uebrig = bewerte(funde, "m", komplett=fake)
    assert [f.name for f in uebrig] == ["adventskalender.congstar.de"]
    assert uebrig[0].einschaetzung == "kampagne"


def test_modell_darf_nichts_hinzufuegen():
    """Was die Stufen davor verworfen haben, kommt nicht zurueck."""
    funde = [_fund("a.congstar.de")]

    def fake(system, user, modell, max_tokens):
        return json.dumps({"namen": [
            {"name": "a.congstar.de", "art": "kampagne"},
            {"name": "erfunden.congstar.de", "art": "kampagne"},
        ]})

    assert [f.name for f in bewerte(funde, "m", komplett=fake)] == ["a.congstar.de"]


def test_vom_modell_uebergangener_name_bleibt_drin():
    """Ein stiller Verlust waere schlimmer als eine Zeile zu viel."""
    funde = [_fund("a.congstar.de"), _fund("b.congstar.de")]

    def fake(system, user, modell, max_tokens):
        return json.dumps({"namen": [{"name": "a.congstar.de", "art": "kampagne"}]})

    uebrig = bewerte(funde, "m", komplett=fake)
    assert {f.name for f in uebrig} == {"a.congstar.de", "b.congstar.de"}
    assert [f.einschaetzung for f in uebrig if f.name == "b.congstar.de"] == [
        "unbewertet"]


def test_unklar_bleibt_drin():
    funde = [_fund("xyz.congstar.de")]

    def fake(system, user, modell, max_tokens):
        return json.dumps({"namen": [{"name": "xyz.congstar.de", "art": "unklar"}]})

    assert len(bewerte(funde, "m", komplett=fake)) == 1


def test_gescheitertes_modell_verwirft_nichts():
    """Ein Aussetzer darf nicht wie 'alles war Infrastruktur' aussehen -
    dieselbe Luecke, die extract_promos im Promo-Zweig teuer bezahlt hat."""
    funde = [_fund("a.congstar.de"), _fund("b.congstar.de")]

    def kaputt(system, user, modell, max_tokens):
        raise RuntimeError("529 overloaded")

    assert len(bewerte(funde, "m", komplett=kaputt)) == 2


def test_ohne_modell_laeuft_die_stufe_gar_nicht(tmp_path, antwort):
    root = _repo(tmp_path, EINE, [])
    sammle(root, {}, jetzt=JETZT, client=_Client(_antwort(daten=antwort)))
    plus = antwort + [{"dns_names": ["neu.congstar.de"],
                       "not_before": "2026-08-07T10:00:00Z"}]
    items, _ = sammle(root, {}, jetzt=JETZT, modell="",
                      client=_Client(_antwort(daten=plus)))
    assert len(items) == 1
    assert "unbestätigt" in items[0].summary


# --------------------------------------------------------------------------- #
# Das Item
# --------------------------------------------------------------------------- #

def test_item_traegt_den_vorbehalt_im_text():
    """Nicht als Fussnote daneben - wer die Zeile kopiert, kopiert ihn mit."""
    item = als_item(_fund("jamobil-news.congstar.de"), JETZT)
    assert "unbestätigt" in item.summary
    assert "nicht, dass es startet" in item.summary


def test_item_id_kommt_aus_dem_namen_nicht_aus_dem_titel():
    """Eine ID aus dem Titel ist beim naechsten Lauf eine andere, sobald sich
    die Formulierung dreht - denselben Fehler hat der Promo-Zweig bezahlt."""
    a = als_item(_fund("x.congstar.de"), JETZT)
    b = als_item(_fund("x.congstar.de"), datetime(2027, 1, 1, tzinfo=timezone.utc))
    assert a.id == b.id

    c = als_item(_fund("y.congstar.de"), JETZT)
    assert c.id != a.id


def test_item_traegt_origin_ct_log():
    assert als_item(_fund("x.congstar.de"), JETZT).origin == "ct_log"


def test_item_nennt_das_ausstellungsdatum():
    f = _fund("x.congstar.de")
    f.nicht_vor = "2026-08-07"
    assert "2026-08-07" in als_item(f, JETZT).summary
