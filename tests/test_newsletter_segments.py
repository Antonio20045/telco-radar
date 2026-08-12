"""Segmentbildung, Abo-Datenmodell und die Uebersetzung aus den Quellen.

Der `segment_hash` ist nicht nur eine Buendelung, er ist die Haelfte des
Idempotenzschluessels beim Versand. Ein Hash, der sich aendert, ohne dass
sich die Auswahl geaendert hat, laesst einen Wiederanlauf seinen eigenen
Sendeplan fuer einen fremden halten - und dann geht die Ausgabe zweimal
raus. Das ist der teuerste denkbare Fehler dieses Vorhabens.
"""
import json
from pathlib import Path

import pytest

from telco_radar.newsletter.config import lade_katalog
from telco_radar.newsletter.filters import Eintrag, Filtersatz, Stichwort
from telco_radar.newsletter.quelle import aus_bericht, aus_promo, region_schluessel
from telco_radar.newsletter.segments import (
    Segment, bilde_segmente, normalform, segment_hash)
from telco_radar.newsletter import subscription as sub

WURZEL = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(WURZEL)


def _abo(id_, satz):
    return sub.Abo(id=id_, email=f"{id_}@beispiel.test", filter=satz,
                   state="active")


# ========================================================  segment_hash  ===

def test_der_hash_ist_stabil_gegen_reihenfolge():
    a = Filtersatz(regionen=("europa", "asien"))
    b = Filtersatz(regionen=("asien", "europa"))
    assert segment_hash(a) == segment_hash(b)


def test_der_hash_ist_stabil_gegen_gross_und_kleinschreibung():
    assert segment_hash(Filtersatz(regionen=("Europa",))) == \
        segment_hash(Filtersatz(regionen=("europa",)))


def test_der_hash_unterscheidet_wort_und_phrase():
    """"5G Netz" als Phrase und dieselben zwei Woerter als zwei Stichwoerter
    sind verschiedene Abos - und sie bekommen verschiedene Mails."""
    phrase = Filtersatz(stichwoerter=(Stichwort("5G Netz", "phrase"),))
    wort = Filtersatz(stichwoerter=(Stichwort("5G Netz", "word"),))
    assert segment_hash(phrase) != segment_hash(wort)


def test_verschiedene_auswahl_ergibt_verschiedene_hashes():
    """Die Gegenprobe. Ohne sie belegen die Tests oben nur, dass der Hash
    konstant ist - ein `return "x"` bestuende sie alle."""
    hashes = {segment_hash(f) for f in (
        Filtersatz(),
        Filtersatz(regionen=("europa",)),
        Filtersatz(regionen=("asien",)),
        Filtersatz(regionen=("europa",), kategorien=("tarife",)),
        Filtersatz(stichwoerter=(Stichwort("Starlink"),)),
    )}
    assert len(hashes) == 5


def test_die_normalform_traegt_nur_die_auswahl():
    """Ein Feld, das dem Abo spaeter dazukommt, darf die Buendelung nicht
    veraendern - sonst rendert der naechste Lauf alles neu und der
    Wiederanlauf verschickt alles doppelt."""
    assert set(normalform(Filtersatz())) == {
        "bereiche", "regionen", "wettbewerber", "kategorien", "keywords"}


# =====================================================  Segmentbildung  ====

def test_gleiche_filter_werden_ein_segment(katalog):
    satz = Filtersatz(regionen=("europa",))
    eintraege = [Eintrag(id="e1", bereich="marktrecherche", titel="T", text="",
                         url="https://x.test/1", region="europa",
                         ressort="tarife")]
    segmente = bilde_segmente([_abo("a", satz), _abo("b", satz),
                               _abo("c", Filtersatz(regionen=("asien",)))],
                              eintraege, katalog)
    assert len(segmente) == 2
    gross = [s for s in segmente if len(s.abo_ids) == 2][0]
    assert sorted(gross.abo_ids) == ["a", "b"]
    assert len(gross.treffer) == 1


def test_ein_segment_ohne_treffer_ist_leer(katalog):
    segmente = bilde_segmente([_abo("a", Filtersatz(regionen=("ozeanien",)))],
                              [Eintrag(id="e1", bereich="marktrecherche",
                                       titel="T", text="", url="https://x.test/1",
                                       region="europa", ressort="tarife")],
                              katalog)
    assert segmente[0].leer is True


def test_die_auswahl_wird_je_segment_nur_einmal_gerechnet(katalog, monkeypatch):
    """Der ganze Sinn der Uebung: 200 Abonnenten mit 12 Kombinationen sind
    12 Rechnungen, nicht 200."""
    import telco_radar.newsletter.segments as segmente_mod
    aufrufe = []
    echt = segmente_mod.waehle
    monkeypatch.setattr(segmente_mod, "waehle",
                        lambda *a, **k: (aufrufe.append(1), echt(*a, **k))[1])
    satz = Filtersatz(regionen=("europa",))
    bilde_segmente([_abo(f"a{i}", satz) for i in range(20)], [], katalog)
    assert len(aufrufe) == 1


def test_die_reihenfolge_der_segmente_ist_stabil(katalog):
    """Der Sendeplan wird gepusht und spaeter mit sich selbst verglichen."""
    abos = [_abo("a", Filtersatz(regionen=("europa",))),
            _abo("b", Filtersatz(regionen=("asien",))),
            _abo("c", Filtersatz(kategorien=("netz",)))]
    erste = [s.hash for s in bilde_segmente(abos, [], katalog)]
    zweite = [s.hash for s in bilde_segmente(list(reversed(abos)), [], katalog)]
    assert erste == zweite


# ======================================================  Abo-Datenmodell  ==

def test_kennwerte_sind_hmac_mit_pepper():
    """Ein blanker SHA-256 ueber eine E-Mail-Adresse ist per Brute Force in
    Minuten umkehrbar - das waere keine Pseudonymisierung."""
    import hashlib
    adresse = "vorname.nachname@beispiel.test"
    mit_pepper = sub.adress_kennwert("geheim", adresse)
    blank = hashlib.sha256(adresse.encode()).hexdigest()
    assert mit_pepper != blank
    assert sub.adress_kennwert("anderer", adresse) != mit_pepper
    # ... und derselbe Pepper ergibt denselben Wert (sonst waere die
    # 24-Stunden-Sperre wirkungslos).
    assert sub.adress_kennwert("geheim", adresse) == mit_pepper


def test_die_adresse_wird_nur_kleingeschrieben():
    """KEIN Entfernen von Punkten, KEIN Abschneiden hinter "+" - das ist
    eine Gmail-Eigenheit. Anderswo sind `a.b@` und `ab@` zwei Postfaecher,
    und wer sie zusammenlegt, legt fremde Post zusammen."""
    assert sub.normalisiere_adresse("  A.B+Radar@Beispiel.TEST ") == \
        "a.b+radar@beispiel.test"


def test_die_abmeldung_loescht_die_adresse_und_behaelt_den_kennwert():
    abo = sub.Abo(id="sub_1", email="weg@beispiel.test", state="active",
                  email_hmac=sub.adress_kennwert("p", "weg@beispiel.test"))
    danach = abo.abgemeldet()
    assert danach.email == ""
    assert danach.state == "unsubscribed"
    assert danach.email_hmac == abo.email_hmac
    assert danach.aktiv is False


def test_ein_abo_ueberlebt_den_weg_durch_json(katalog):
    abo = sub.Abo(
        id=sub.neue_id(), email="a@beispiel.test",
        filter=Filtersatz(regionen=("europa",), kategorien=("tarife",),
                          stichwoerter=(Stichwort("Starlink"),
                                        Stichwort("Fixed Wireless", "phrase"))),
        consent=sub.Einwilligungsnachweis(text_version="2026-08-11",
                                          text_hash="sha256:abc",
                                          ip_hmac="x", user_agent_hmac="y"),
        created_at=sub.jetzt(), state="active")
    zurueck = sub.aus_dict(json.loads(json.dumps(sub.als_dict(abo))), katalog)
    assert zurueck.id == abo.id
    assert zurueck.email == abo.email
    assert zurueck.filter.regionen == ("europa",)
    assert {s.term for s in zurueck.filter.stichwoerter} == {
        "Starlink", "Fixed Wireless"}
    assert segment_hash(zurueck.filter) == segment_hash(abo.filter)
    assert zurueck.consent.vollstaendig


def test_ein_nachweis_ohne_wortlaut_gilt_als_unvollstaendig():
    """IP und Browser duerfen fehlen. Der WORTLAUT darf es nicht - er ist
    das, wonach eine Aufsichtsbehoerde fragt."""
    assert not sub.Einwilligungsnachweis(ip_hmac="x").vollstaendig
    assert sub.Einwilligungsnachweis(text_version="2026-08-11",
                                     text_hash="sha256:a").vollstaendig


# ========================================================  Zulaessigkeit  ==

@pytest.mark.parametrize("adresse, gueltig", [
    ("a@b.de", True), ("vorname.nachname@firma.example.com", True),
    ("kein-at", False), ("a@b", False), ("a@@b.de", False),
    ("", False), ("a b@c.de", False),
])
def test_adresspruefung(adresse, gueltig):
    assert sub.ist_adresse(adresse) is gueltig


def test_pruefe_anmeldung_sammelt_alle_fehler(katalog):
    """Wer drei Stichwoerter falsch eingetragen hat, soll das in EINEM
    Durchgang erfahren, nicht in dreien."""
    fehler = sub.pruefe_anmeldung(
        "kein-at", {"regions": ["mars"], "keywords": ["ab", "cd"]}, katalog)
    assert len(fehler) >= 4
    assert any("E-Mail" in f for f in fehler)
    assert any("mars" in f for f in fehler)


def test_eine_saubere_anmeldung_hat_keine_fehler(katalog):
    assert sub.pruefe_anmeldung(
        "a@beispiel.test",
        {"regions": ["europa"], "categories": ["tarife"],
         "keywords": ["Starlink"]}, katalog) == []


def test_die_domainliste_steht_auf_leer_und_erlaubt_alles():
    """Festlegung 3: die Anmeldung ist offen. Gebaut ist die Liste trotzdem,
    damit das Umschalten eine Konfigurationszeile bleibt."""
    assert sub.erlaubt_nach_domainliste("wer@auch.immer", []) is True
    assert sub.erlaubt_nach_domainliste("wer@auch.immer", None) is True


def test_die_domainliste_wirkt_wenn_sie_gefuellt_ist():
    erlaubt = ["vodafone.de"]
    assert sub.erlaubt_nach_domainliste("a@vodafone.de", erlaubt)
    assert sub.erlaubt_nach_domainliste("a@mail.vodafone.de", erlaubt)
    assert not sub.erlaubt_nach_domainliste("a@vodafone.de.beispiel.com", erlaubt)
    assert not sub.erlaubt_nach_domainliste("a@telekom.de", erlaubt)


# ==========================================  Uebersetzung aus den Quellen ==

BERICHT = {
    "date": "2026-08-11",
    "regions": {
        "Europa": {"highlights": [
            {"headline": "Telekom senkt Preise", "title": "Telekom cuts",
             "summary": "Die Telekom senkt die Preise um zehn Prozent.",
             "url": "https://x.test/1", "operator": "Deutsche Telekom",
             "category": "Tarif/Pricing", "relevance": 3, "ctm_bezug": 3,
             "source": "Fachpresse", "date": "2026-08-10"}]},
        "Afrika & Naher Osten": {"highlights": [
            {"headline": "MTN baut aus", "summary": "Neue Standorte.",
             "url": "https://x.test/2", "operator": "kein spezifischer Betreiber",
             "category": "Netz/Technologie", "relevance": 2, "ctm_bezug": 1,
             "source": "Fachpresse"}]},
        "KI-Anbieter": {"highlights": [
            {"headline": "Nvidia liefert", "summary": "Neue Chips.",
             "url": "https://x.test/3", "category": "Sonstiges",
             "relevance": 2, "ctm_bezug": 1, "source": "Fachpresse"}]},
    },
}


def test_aus_bericht_uebersetzt_regionen_in_schluessel():
    eintraege = aus_bericht(BERICHT)
    nach_region = {e.titel: e.region for e in eintraege}
    assert nach_region["Telekom senkt Preise"] == "europa"
    assert nach_region["MTN baut aus"] == "afrika-naher-osten"
    # Ein Themenfeld hat keine Region - es laeuft unter "global", derselben
    # Schublade wie die weltweite Fachpresse.
    assert nach_region["Nvidia liefert"] == "global"


def test_aus_bericht_wirft_die_betreiber_platzhalter_weg():
    """"kein spezifischer Betreiber" ist als Absender keine Angabe, sondern
    eine Ausrede - dieselbe Regel wie in `_flatten`."""
    nach_titel = {e.titel: e for e in aus_bericht(BERICHT)}
    assert nach_titel["MTN baut aus"].betreiber == ""
    assert nach_titel["Telekom senkt Preise"].betreiber == "Deutsche Telekom"


def test_aus_bericht_gewichtet_wie_die_startseite():
    """Die CTM-Stufe VOR der Prioritaet. Eine Rangfolge, die in der Mail
    anders ausfaellt als auf der Seite, ist eine zweite Wahrheit."""
    nach_titel = {e.titel: e for e in aus_bericht(BERICHT)}
    assert nach_titel["Telekom senkt Preise"].gewicht > \
        nach_titel["MTN baut aus"].gewicht


def test_aus_bericht_nimmt_die_id_aus_der_url():
    """Nicht aus dem Titel: Ueberschriften werden umgeschrieben, Adressen
    nicht - dieselbe Lehre wie im Ereignis-Gedaechtnis und im Geraetekatalog."""
    eins = aus_bericht(BERICHT)[0]
    anders = json.loads(json.dumps(BERICHT))
    for region in anders["regions"].values():
        for h in region["highlights"]:
            h["headline"] = h["headline"].upper() + " (aktualisiert)"
    assert aus_bericht(anders)[0].id == eins.id


def test_aus_bericht_uebernimmt_text_woertlich():
    """Hier entsteht kein Text. Das ist die Bedingung dafuer, dass der
    Renderer-Test in N3 jeden Block im Quell-JSON wiederfindet."""
    eintrag = [e for e in aus_bericht(BERICHT) if e.titel.startswith("Telekom")][0]
    assert eintrag.text == "Die Telekom senkt die Preise um zehn Prozent."


PROMO = [
    {"id": "p1", "brand": "1&1 Mobilfunk", "headline": "Sommer-Special",
     "description": "Preisvorteil für Handyverträge.", "status": "aktiv",
     "url": "https://1und1.test/a", "score": 60, "last_verified": "2026-08-11"},
    {"id": "p2", "brand": "otelo", "headline": "Alter Deal", "status": "ausgelaufen",
     "url": "https://otelo.test/b", "score": 90},
]


def test_aus_promo_haelt_ausgelaufene_aktionen_heraus():
    """Eine Mail, die auf ein abgelaufenes Angebot zeigt, ist schlechter als
    eine ohne diesen Eintrag."""
    eintraege = aus_promo(PROMO)
    assert [e.titel for e in eintraege] == ["Sommer-Special"]
    assert len(aus_promo(PROMO, nur_aktiv=False)) == 2


def test_promo_aktionen_tragen_region_und_ressort():
    """Ohne Region waere jede Aktion fuer jeden Regionsfilter unsichtbar -
    also fuer jeden, der Europa gewaehlt hat."""
    eintrag = aus_promo(PROMO)[0]
    assert eintrag.region == "europa"
    assert eintrag.ressort == "tarife"
    assert eintrag.bereich == "promo"


def test_promo_und_meldungen_stehen_auf_einer_gewichtsskala():
    """Der Promo-Score reicht bis 100, das Meldungsgewicht bis 35. Ungeteilt
    verdraengt jede mittelmaessige Aktion jede Meldung."""
    aktion = aus_promo(PROMO)[0]
    beste_meldung = max(aus_bericht(BERICHT), key=lambda e: e.gewicht)
    assert aktion.gewicht <= beste_meldung.gewicht * 2


def test_beide_quellen_lassen_sich_gemeinsam_filtern(katalog):
    """Der Punkt der ganzen Uebersetzung: EIN Filtersatz ueber beide
    Bereiche."""
    from telco_radar.newsletter.filters import waehle
    alle = aus_bericht(BERICHT) + aus_promo(PROMO)
    nur_promo = waehle(alle, Filtersatz(bereiche=("promo",)), katalog)
    assert {t.eintrag.bereich for t in nur_promo} == {"promo"}
    nur_markt = waehle(alle, Filtersatz(bereiche=("marktrecherche",)), katalog)
    assert {t.eintrag.bereich for t in nur_markt} == {"marktrecherche"}
    assert len(waehle(alle, Filtersatz(), katalog)) == 4


def test_die_ids_der_beiden_quellen_kollidieren_nicht():
    ids = {e.id for e in aus_bericht(BERICHT)} | {e.id for e in aus_promo(PROMO)}
    assert len(ids) == 4
    assert all(i.startswith(("markt:", "promo:")) for i in ids)
