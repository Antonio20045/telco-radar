"""Der Verteiler als Brevo-Liste: Hin- und Rueckweg ohne Verlust."""

import io
import json
import urllib.error
from pathlib import Path

import pytest

from telco_radar.newsletter import brevo_kontakte as bk
from telco_radar.newsletter import subscription as sub
from telco_radar.newsletter.config import lade_katalog

WURZEL = Path(__file__).resolve().parents[1]


class _Antwort(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FalschesBrevo:
    """Ein Brevo im Speicher, genug fuer Attribute, Ordner, Listen und Kontakte."""

    def __init__(self):
        self.attribute: list[str] = []
        self.ordner: list[dict] = []
        self.listen: list[dict] = []
        self.kontakte: dict[str, dict] = {}
        self.anfragen: list[tuple[str, str]] = []

    def __call__(self, anfrage, timeout=0):
        methode = anfrage.get_method()
        pfad = anfrage.full_url.removeprefix(bk.BREVO_KONTAKTE)
        koerper = json.loads(anfrage.data) if anfrage.data else {}
        self.anfragen.append((methode, pfad))
        return _Antwort(json.dumps(self._antwort(methode, pfad, koerper)).encode())

    def _fehler(self, code):
        return urllib.error.HTTPError(
            "u", code, "x", {}, io.BytesIO(b'{"message":"a@b.de fehlt"}')
        )

    def _antwort(self, methode, pfad, koerper):
        if pfad == "/attributes":
            return {"attributes": [{"name": n} for n in self.attribute]}
        if pfad.startswith("/attributes/normal/"):
            self.attribute.append(pfad.rsplit("/", 1)[1])
            return {}
        if pfad.startswith("/lists?"):
            return {"lists": self.listen}
        if pfad.startswith("/folders?"):
            return {"folders": self.ordner}
        if pfad == "/folders":
            self.ordner.append({"id": 7, "name": koerper["name"]})
            return {"id": 7}
        if pfad == "/lists":
            self.listen.append({"id": 3, "name": koerper["name"]})
            return {"id": 3}
        if pfad == "" and methode == "POST":
            alt = self.kontakte.get(koerper["email"], {"attributes": {}})
            alt["attributes"].update(koerper["attributes"])
            self.kontakte[koerper["email"]] = alt
            return {}
        if pfad.startswith("/lists/3/contacts"):
            versatz = int(pfad.rsplit("offset=", 1)[1])
            alle = [
                {"email": a, "attributes": k["attributes"], "emailBlacklisted": False}
                for a, k in sorted(self.kontakte.items())
            ]
            return {"contacts": alle[versatz : versatz + 1], "count": len(alle)}
        adresse = pfad.lstrip("/").replace("%40", "@")
        if adresse not in self.kontakte:
            raise self._fehler(404)
        if methode == "DELETE":
            del self.kontakte[adresse]
        if methode == "PUT":
            self.kontakte[adresse]["attributes"].update(koerper["attributes"])
        return {}


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(WURZEL)


def _abo(adresse, katalog):
    roh = {
        "id": f"sub_{adresse[0]}",
        "email": adresse,
        "email_hmac": "k" * 64,
        "created_at": "2026-09-25T11:51:28Z",
        "confirmed_at": "2026-09-25T11:52:00Z",
        "state": "active",
        "consent": {
            "text_version": "2026-08-13",
            "text_hash": "h",
            "ip_hmac": "i",
            "user_agent_hmac": "u",
            "confirm_token_id": "t",
        },
        "filters": {
            "competitors": ["telekom"],
            "keywords": [{"term": "Glasfaser", "mode": "plus"}],
        },
    }
    return sub.aus_dict(roh, katalog)


def test_einrichten_legt_alles_einmal_an():
    brevo = FalschesBrevo()
    kontakte = bk.BrevoKontakte("schluessel", oeffner=brevo)
    assert kontakte.einrichten() == 3
    assert kontakte.einrichten() == 3
    assert sorted(brevo.attribute) == [bk.ATTR_ABO, bk.ATTR_LETZTE]
    assert [e["name"] for e in brevo.listen] == [bk.LISTE]


def test_hin_und_zurueck_ohne_verlust_ueber_mehrere_seiten(katalog):
    brevo = FalschesBrevo()
    kontakte = bk.BrevoKontakte("schluessel", oeffner=brevo)
    liste = kontakte.einrichten()
    abos = [_abo("anna@firma.de", katalog), _abo("bert@firma.de", katalog)]
    for abo in abos:
        kontakte.speichern(abo, liste)
    zurueck = kontakte.alle(liste, katalog)
    assert [sub.als_dict(k.abo) for k in zurueck] == [sub.als_dict(a) for a in abos]
    werte = [v for k in brevo.kontakte.values() for v in k["attributes"].values()]
    assert all("@" not in v for v in werte)


def test_ausgabe_vermerken_und_loeschen(katalog):
    brevo = FalschesBrevo()
    kontakte = bk.BrevoKontakte("schluessel", oeffner=brevo)
    liste = kontakte.einrichten()
    kontakte.speichern(_abo("anna@firma.de", katalog), liste)
    kontakte.ausgabe_vermerken("Anna@Firma.de", "2026-10-11")
    assert kontakte.alle(liste, katalog)[0].letzte_ausgabe == "2026-10-11"
    assert kontakte.loeschen("anna@firma.de") is True
    assert kontakte.loeschen("anna@firma.de") is False
    assert kontakte.alle(liste, katalog) == []


def test_nur_aktive_abos_und_fehler_ohne_adresse(katalog):
    kontakte = bk.BrevoKontakte("schluessel", oeffner=FalschesBrevo())
    abo = _abo("anna@firma.de", katalog)
    abo.state = "pending"
    with pytest.raises(ValueError):
        kontakte.speichern(abo, 3)
    with pytest.raises(bk.BrevoFehler) as fehler:
        kontakte.ausgabe_vermerken("x@y.de", "2026-10-11")
    assert "@" not in str(fehler.value)
    with pytest.raises(bk.BrevoFehler):
        bk.BrevoKontakte("")
