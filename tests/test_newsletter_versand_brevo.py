"""Versand nach dem Radar-Lauf: aus ohne Antonios Go, nie doppelt."""

import importlib.util
import json
from pathlib import Path

import pytest

from telco_radar.newsletter import subscription as sub
from telco_radar.newsletter.brevo_kontakte import Kontakt
from telco_radar.newsletter.config import lade_katalog
from telco_radar.newsletter.transport import Trockenlauf

WURZEL = Path(__file__).resolve().parents[1]
DATUM = "2026-10-10"


def _modul():
    pfad = WURZEL / "scripts" / "newsletter" / "versand_brevo.py"
    spec = importlib.util.spec_from_file_location("versand_brevo", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


class Liste:
    def __init__(self, kontakte):
        self.kontakte = kontakte
        self.vermerkt: list[tuple[str, str]] = []

    def __call__(self, api_key):
        return self

    def liste_id(self):
        return 5

    def alle(self, liste, katalog):
        return self.kontakte

    def ausgabe_vermerken(self, adresse, datum):
        self.vermerkt.append((adresse, datum))
        for k in self.kontakte:
            if k.abo.email == adresse:
                k.letzte_ausgabe = datum


@pytest.fixture()
def lauf(tmp_path, monkeypatch):
    katalog = lade_katalog(WURZEL)
    bericht = {
        "date": DATUM,
        "regions": {
            "Europa": {
                "highlights": [
                    {
                        "url": "https://beispiel.test/telekom-tarif",
                        "title": "Telekom senkt die Preise im MagentaMobil-Tarif",
                        "summary": "Die Telekom senkt die Preise.",
                        "operator": "Deutsche Telekom",
                        "category": "Tarif/Pricing",
                        "relevance": 5,
                        "date": DATUM,
                    }
                ]
            }
        },
    }
    pfad = tmp_path / f"{DATUM}.json"
    pfad.write_text(json.dumps(bericht), encoding="utf-8")

    def abo(name, gesperrt=False):
        roh = {
            "id": f"sub_{name}",
            "email": f"{name}@firma.test",
            "email_hmac": "k" * 64,
            "confirmed_at": "2026-09-25T11:52:00Z",
            "state": "active",
        }
        return Kontakt(
            abo=sub.aus_dict(roh, katalog), letzte_ausgabe="", gesperrt=gesperrt
        )

    liste = Liste([abo("anna"), abo("bert"), abo("carl", gesperrt=True)])
    modul = _modul()
    monkeypatch.setattr(modul, "BrevoKontakte", liste)
    gesendet = Trockenlauf()
    gesendet.trocken = []
    monkeypatch.setattr(
        modul,
        "_transport",
        lambda trocken: gesendet.trocken.append(trocken) or gesendet,
    )
    monkeypatch.chdir(tmp_path)

    def starten(**umgebung):
        umgebung = {"BREVO_API_KEY": "b", "SIGNUP_TOKEN_KEY": "s", **umgebung}
        argv = ["--bericht", str(pfad), "--promo", str(tmp_path / "keine.json")]
        assert modul.main(argv, umgebung) == 0
        return gesendet, liste

    return starten


def test_ohne_go_geht_keine_ausgabe_an_abonnenten(lauf):
    gesendet, liste = lauf()
    gesendet, liste = lauf(NEWSLETTER_AN="vielleicht")
    assert gesendet.trocken == [True, True]
    assert liste.vermerkt == []


def test_mit_go_genau_einmal_an_jeden_nicht_gesperrten(lauf):
    gesendet, liste = lauf(NEWSLETTER_AN="ja")
    assert gesendet.trocken == [False]
    assert sorted(a for a, _ in liste.vermerkt) == [
        "anna@firma.test",
        "bert@firma.test",
    ]
    an = sorted(adresse for adresse, _ in gesendet.versendet)
    assert an == ["anna@firma.test", "bert@firma.test"]
    nachricht = gesendet.versendet[0][1]
    assert "/unsubscribe/" in nachricht.headers["List-Unsubscribe"]
    vorher = len(gesendet.versendet)
    lauf(NEWSLETTER_AN="ja")
    assert len(gesendet.versendet) == vorher


def test_der_schalter_kennt_nur_ja():
    modul = _modul()
    assert modul.scharf({"NEWSLETTER_AN": "ja"})
    assert not modul.scharf({})
    assert not modul.scharf({"NEWSLETTER_AN": "nein"})


def test_ohne_abmeldeschluessel_geht_nichts_raus(lauf):
    with pytest.raises(AssertionError):
        lauf(NEWSLETTER_AN="ja", SIGNUP_TOKEN_KEY="")
    gesendet, liste = lauf(SIGNUP_TOKEN_KEY="")
    assert gesendet.versendet == [] and liste.vermerkt == []
