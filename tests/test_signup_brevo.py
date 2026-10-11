"""Der Anmeldedienst direkt an Brevo: Anmelden, Bestaetigen, Abmelden."""

import io
import json
import os
import subprocess
import sys
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from service.signup import tokens
from service.signup.ratelimit import IPBremse
from telco_radar.newsletter import anmeldung, transport
from telco_radar.newsletter import brevo_kontakte as bk

KEY = "test-token-key"
PEPPER = "test-pepper"
JETZT = 1_784_000_000.0
ADRESSE = "vorname@beispiel.test"


class _Antwort(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Brevo:
    """Brevo im Speicher: Mailversand, Versandprotokoll, Liste, Kontakte."""

    def __init__(self):
        self.mails: list[dict] = []
        self.kontakte: dict[str, dict] = {}
        self.listen: list[dict] = []
        self.kaputt = False

    def __call__(self, anfrage, timeout=0):
        if self.kaputt:
            raise urllib.error.HTTPError("u", 503, "x", {}, io.BytesIO(b"{}"))
        teile = urlsplit(anfrage.full_url)
        methode = anfrage.get_method()
        koerper = json.loads(anfrage.data) if anfrage.data else {}
        return _Antwort(json.dumps(self._antwort(methode, teile, koerper)).encode())

    def _antwort(self, methode, teile, koerper):
        pfad = teile.path.removeprefix("/v3")
        if pfad == "/smtp/email":
            self.mails.append(koerper)
            return {"messageId": "m"}
        if pfad == "/smtp/statistics/events":
            an = parse_qs(teile.query)["email"][0]
            treffer = [m for m in self.mails if m["to"][0]["email"] == an]
            return {"events": [{"event": "requests"}] if treffer else []}
        if pfad == "/contacts/attributes":
            return {"attributes": [{"name": bk.ATTR_ABO}, {"name": bk.ATTR_LETZTE}]}
        if pfad == "/contacts/lists" and methode == "GET":
            return {"lists": self.listen}
        if pfad == "/contacts/folders" and methode == "GET":
            return {"folders": [{"id": 1, "name": bk.ORDNER}]}
        if pfad == "/contacts/lists":
            self.listen.append({"id": 5, "name": koerper["name"]})
            return {"id": 5}
        if pfad == "/contacts" and methode == "POST":
            self.kontakte[koerper["email"]] = {"attributes": koerper["attributes"]}
            return {}
        if pfad == "/contacts/lists/5/contacts":
            alle = [
                {"email": a, "attributes": k["attributes"]}
                for a, k in self.kontakte.items()
            ]
            return {"contacts": alle, "count": len(alle)}
        adresse = pfad.removeprefix("/contacts/").replace("%40", "@")
        if methode == "DELETE" and adresse in self.kontakte:
            del self.kontakte[adresse]
            return {}
        raise urllib.error.HTTPError("u", 404, "x", {}, io.BytesIO(b"{}"))


@pytest.fixture()
def dienst(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from service.signup import app as app_mod

    monkeypatch.setattr(tokens, "time", SimpleNamespace(time=lambda: JETZT))
    monkeypatch.setattr(app_mod.einstellungen, "token_key", KEY)
    monkeypatch.setattr(app_mod.einstellungen, "pepper", PEPPER)
    monkeypatch.setattr(app_mod.einstellungen, "github_token", "")
    monkeypatch.setattr(app_mod.einstellungen, "brevo_key", "brevo-test")
    monkeypatch.setattr(app_mod.einstellungen, "erlaubte_domains", [])
    monkeypatch.setattr(app_mod, "bremse", IPBremse(erlaubt=50))
    monkeypatch.setattr(anmeldung, "_LISTE", [])
    monkeypatch.setattr(
        app_mod, "_dispatch", lambda *a: pytest.fail("kein GitHub mehr")
    )
    brevo = Brevo()
    monkeypatch.setattr(transport.urllib.request, "urlopen", brevo)
    klient = TestClient(app_mod.app)
    klient.brevo = brevo
    return klient


def _anmelden(klient):
    nonce = tokens.schreibe(KEY, tokens.ZWECK_NONCE, {}, jetzt=JETZT - 30)
    return klient.post(
        "/subscribe",
        json={
            "email": ADRESSE,
            "nonce": nonce,
            "consent": True,
            "website": "",
            "filters": {"competitors": ["telekom"], "keywords": ["Starlink"]},
        },
    )


def _bestaetigungslink(mail):
    text = mail["textContent"]
    return next(z for z in text.splitlines() if "/confirm/" in z)


def test_anmelden_schickt_genau_eine_bestaetigungsmail(dienst):
    assert _anmelden(dienst).status_code == 202
    assert _anmelden(dienst).status_code == 202
    assert len(dienst.brevo.mails) == 1
    mail = dienst.brevo.mails[0]
    assert mail["to"] == [{"email": ADRESSE}]
    assert "telco-radar-doi" in mail["tags"]
    assert dienst.brevo.kontakte == {}


def test_bestaetigen_legt_den_kontakt_an_und_abmelden_loescht_ihn(dienst):
    _anmelden(dienst)
    token = _bestaetigungslink(dienst.brevo.mails[0]).rsplit("/confirm/", 1)[1]
    assert "Angemeldet" in dienst.get(f"/confirm/{token}").text
    assert list(dienst.brevo.kontakte) == [ADRESSE]
    roh = json.loads(dienst.brevo.kontakte[ADRESSE]["attributes"][bk.ATTR_ABO])
    assert roh["filters"]["competitors"] == ["telekom"]
    assert roh["state"] == "active" and "email" not in roh
    abmeldung = tokens.schreibe(KEY, tokens.ZWECK_ABMELDUNG, {"sub_id": roh["id"]})
    assert "Abgemeldet" in dienst.get(f"/unsubscribe/{abmeldung}").text
    assert dienst.brevo.kontakte == {}


def test_brevo_faellt_aus_und_der_dienst_sagt_es(dienst):
    _anmelden(dienst)
    token = _bestaetigungslink(dienst.brevo.mails[0]).rsplit("/confirm/", 1)[1]
    dienst.brevo.kaputt = True
    assert _anmelden(dienst).status_code == 503
    assert "nicht geklappt" in dienst.get(f"/confirm/{token}").text
    abmeldung = tokens.schreibe(KEY, tokens.ZWECK_ABMELDUNG, {"sub_id": "x"})
    assert "nicht geklappt" in dienst.get(f"/unsubscribe/{abmeldung}").text


def test_der_dienst_startet_mit_seinen_eigenen_abhaengigkeiten():
    """Render installiert nur service/signup/requirements.txt - kein jinja2."""
    wurzel = Path(__file__).resolve().parents[1]
    lauf = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys\nsys.modules['jinja2'] = None\n"
            "from service.signup import app\nprint(app.anmeldung.DOI_SCHLAGWORT)",
        ],
        capture_output=True,
        text=True,
        cwd=wurzel,
        env={**os.environ, "PYTHONPATH": str(wurzel)},
        timeout=60,
    )
    assert lauf.returncode == 0, lauf.stderr
    assert "telco-radar-doi" in lauf.stdout
