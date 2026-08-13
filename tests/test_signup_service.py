"""Der Signup-Dienst - und vor allem, was er NICHT tut.

Drei Zusicherungen tragen die ganze Konstruktion, und alle drei sind hier
gemessen statt behauptet:

  1. Er **speichert nichts**. Ein Test haelt das Dateisystem dagegen.
  2. Er **verschickt nichts** - kein SMTP, kein Brevo-Aufruf.
  3. Er **verraet nicht**, ob eine Adresse bekannt ist.

Die Tests laufen gegen einen gemockten GitHub-Endpunkt, nie gegen das Netz.
"""
import json
import time
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient          # noqa: E402

from service.signup import app as app_mod          # noqa: E402
from service.signup import tokens                  # noqa: E402
from service.signup.ratelimit import IPBremse      # noqa: E402

KEY = "test-token-key"
PEPPER = "test-pepper"


@pytest.fixture()
def dienst(monkeypatch):
    """Der Dienst mit Testgeheimnissen und ohne Netz."""
    monkeypatch.setattr(app_mod.einstellungen, "token_key", KEY)
    monkeypatch.setattr(app_mod.einstellungen, "pepper", PEPPER)
    monkeypatch.setattr(app_mod.einstellungen, "github_token", "gh-test")
    monkeypatch.setattr(app_mod.einstellungen, "erlaubte_domains", [])
    monkeypatch.setattr(app_mod, "bremse", IPBremse(erlaubt=50))
    gesendet = []
    monkeypatch.setattr(app_mod, "_dispatch",
                        lambda e, n: (gesendet.append((e, n)), True)[1])
    klient = TestClient(app_mod.app)
    klient.gesendet = gesendet
    return klient


def _anmeldung(klient, **kw):
    nonce = klient.get("/form-token").json()["nonce"]
    # Die Nonce hat ein MINDESTALTER von zwei Sekunden. Statt zu warten wird
    # sie mit einem Ausstellungszeitpunkt in der Vergangenheit gebaut.
    nonce = tokens.schreibe(KEY, tokens.ZWECK_NONCE, {},
                            jetzt=time.time() - 30)
    koerper = {"email": "vorname@beispiel.test", "nonce": nonce,
               "consent": True, "website": "",
               "filters": {"regions": ["europa"], "categories": ["tarife"],
                           "keywords": ["Starlink"]}}
    koerper.update(kw)
    return klient.post("/subscribe", json=koerper)


# ==============================================================  Token  ====

def test_ein_verfaelschtes_token_faellt_durch():
    token = tokens.schreibe(KEY, tokens.ZWECK_BESTAETIGUNG, {"email": "a@b.de"})
    koerper, signatur = token.split(".")
    with pytest.raises(tokens.TokenFehler):
        tokens.lies(KEY, tokens.ZWECK_BESTAETIGUNG, f"{koerper}x.{signatur}",
                    max_alter=3600)


def test_ein_fremder_schluessel_faellt_durch():
    token = tokens.schreibe(KEY, tokens.ZWECK_BESTAETIGUNG, {"email": "a@b.de"})
    with pytest.raises(tokens.TokenFehler):
        tokens.lies("anderer", tokens.ZWECK_BESTAETIGUNG, token, max_alter=3600)


def test_eine_nonce_ist_kein_bestaetigungstoken():
    """Ohne Zweck im signierten Teil waere jede Nonce ein gueltiges
    Bestaetigungstoken - dieselbe Signatur, dieselbe Nutzlastform, und der
    Angreifer braeuchte den Schluessel gar nicht."""
    nonce = tokens.schreibe(KEY, tokens.ZWECK_NONCE, {"email": "fremd@b.de"})
    with pytest.raises(tokens.TokenFehler):
        tokens.lies(KEY, tokens.ZWECK_BESTAETIGUNG, nonce, max_alter=3600)


def test_ein_abgelaufenes_token_faellt_durch():
    alt = tokens.schreibe(KEY, tokens.ZWECK_BESTAETIGUNG, {},
                          jetzt=time.time() - tokens.TTL_BESTAETIGUNG - 10)
    with pytest.raises(tokens.TokenFehler):
        tokens.lies(KEY, tokens.ZWECK_BESTAETIGUNG, alt,
                    max_alter=tokens.TTL_BESTAETIGUNG)


def test_das_ablaufdatum_steht_im_signierten_teil():
    """Ein Ablauf neben der Signatur waere frei aenderbar."""
    token = tokens.schreibe(KEY, tokens.ZWECK_BESTAETIGUNG, {},
                            jetzt=time.time() - 1000)
    import base64
    koerper, signatur = token.split(".")
    daten = json.loads(base64.urlsafe_b64decode(koerper + "==").decode())
    daten["iat"] = int(time.time())          # "verlaengern"
    gefaelscht = base64.urlsafe_b64encode(
        json.dumps(daten, sort_keys=True, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    with pytest.raises(tokens.TokenFehler):
        tokens.lies(KEY, tokens.ZWECK_BESTAETIGUNG, f"{gefaelscht}.{signatur}",
                    max_alter=3600)


def test_ein_token_aus_der_zukunft_faellt_durch():
    """Entweder eine verstellte Uhr oder ein Versuch, den Ablauf
    auszuhebeln."""
    with pytest.raises(tokens.TokenFehler):
        tokens.lies(KEY, tokens.ZWECK_BESTAETIGUNG,
                    tokens.schreibe(KEY, tokens.ZWECK_BESTAETIGUNG, {},
                                    jetzt=time.time() + 7200),
                    max_alter=3600)


def test_ein_token_traegt_keine_polsterung():
    """Es steht in einem PFADSEGMENT. "=" ist dort zwar zulaessig, aber jedes
    zweite Gateway macht etwas anderes daraus."""
    for i in range(20):
        token = tokens.schreibe(KEY, tokens.ZWECK_BESTAETIGUNG,
                                {"email": "a" * i + "@b.de"})
        assert "=" not in token
        assert token.count(".") == 1


def test_die_nutzlast_ueberlebt_den_umweg():
    daten = {"email": "a@b.de", "filters": {"regions": ["europa"]},
             "consent_version": "2026-08-11"}
    zurueck = tokens.lies(KEY, tokens.ZWECK_BESTAETIGUNG,
                          tokens.schreibe(KEY, tokens.ZWECK_BESTAETIGUNG, daten),
                          max_alter=3600)
    assert {k: zurueck[k] for k in daten} == daten


# =========================================================  form-token  ====

def test_form_token_liefert_eine_pruefbare_nonce(dienst):
    antwort = dienst.get("/form-token")
    assert antwort.status_code == 200
    nonce = antwort.json()["nonce"]
    daten = tokens.lies(KEY, tokens.ZWECK_NONCE, nonce,
                        max_alter=tokens.NONCE_MAX,
                        jetzt=time.time() + tokens.NONCE_MIN + 1)
    assert "iat" in daten
    assert antwort.headers["Referrer-Policy"] == "no-referrer"


# ==========================================================  subscribe  ====

def test_eine_saubere_anmeldung_loest_send_doi_aus(dienst):
    antwort = _anmeldung(dienst)
    assert antwort.status_code == 202
    assert antwort.json()["message"] == app_mod.NEUTRAL
    ereignisse = [e for e, _ in dienst.gesendet]
    assert ereignisse == ["send_doi"]


def test_die_klaradresse_steht_nicht_im_dispatch_payload(dienst):
    """Ein Dispatch-Payload landet in der Ereignisliste des Repos. Die
    Adresse steckt signiert im Token, und das Token geht an einen privaten
    Workflow."""
    _anmeldung(dienst)
    _ereignis, nutzlast = dienst.gesendet[0]
    roh = json.dumps(nutzlast)
    assert "vorname@beispiel.test" not in roh
    assert set(nutzlast) == {"token", "token_id", "addr_hmac", "confirm_url"}


def test_der_honeypot_antwortet_wie_ein_erfolg(dienst):
    """Eine erkennbare Ablehnung waere eine Bauanleitung."""
    antwort = _anmeldung(dienst, website="http://spam.test")
    assert antwort.status_code == 202
    assert antwort.json()["message"] == app_mod.NEUTRAL
    assert dienst.gesendet == []


def test_ohne_nonce_passiert_nichts_und_es_sieht_normal_aus(dienst):
    antwort = dienst.post("/subscribe", json={
        "email": "a@beispiel.test", "consent": True, "filters": {}})
    assert antwort.status_code == 202
    assert dienst.gesendet == []


def test_eine_zu_frische_nonce_wird_abgewiesen(dienst):
    """Schneller als zwei Sekunden fuellt kein Mensch ein Formular aus."""
    frisch = tokens.schreibe(KEY, tokens.ZWECK_NONCE, {})
    antwort = dienst.post("/subscribe", json={
        "email": "a@beispiel.test", "nonce": frisch, "consent": True,
        "filters": {}})
    assert antwort.status_code == 202
    assert dienst.gesendet == []


def test_ohne_einwilligung_keine_anmeldung(dienst):
    antwort = _anmeldung(dienst, consent=False)
    assert antwort.status_code == 400
    assert "Einwilligung" in " ".join(antwort.json()["fehler"])
    assert dienst.gesendet == []


def test_die_einwilligungsfassung_reist_im_token_mit(dienst):
    """Der Nachweis muss den WORTLAUT von damals belegen, nicht den von
    heute."""
    _anmeldung(dienst)
    _e, nutzlast = dienst.gesendet[0]
    daten = tokens.lies(KEY, tokens.ZWECK_BESTAETIGUNG, nutzlast["token"],
                        max_alter=tokens.TTL_BESTAETIGUNG)
    assert daten["consent_version"]
    assert daten["consent_hash"].startswith("sha256:")


def test_ip_und_browser_reisen_im_token_mit(dienst):
    """Beim Bestaetigen existiert die Anmeldeanfrage nicht mehr. Erst dort
    gebildet, stuende im Protokoll die IP des KLICKS - bei einem Klick vom
    Telefon aus dem Mobilfunknetz also etwas, das mit der Einwilligung
    nichts zu tun hat."""
    _anmeldung(dienst)
    _e, nutzlast = dienst.gesendet[0]
    daten = tokens.lies(KEY, tokens.ZWECK_BESTAETIGUNG, nutzlast["token"],
                        max_alter=tokens.TTL_BESTAETIGUNG)
    assert daten["ip_hmac"] and daten["ua_hmac"] and daten["addr_hmac"]
    # ... und zwar als HMAC mit Pepper, nicht als blanker Hash und erst recht
    # nicht im Klartext. Ein blanker SHA-256 ueber eine IPv4 ist auf einem
    # Notebook in Sekunden zurueckgerechnet.
    import hashlib
    from telco_radar.newsletter.subscription import adress_kennwert
    assert all(len(daten[f]) == 64 for f in ("ip_hmac", "ua_hmac", "addr_hmac"))
    assert daten["addr_hmac"] == adress_kennwert(PEPPER, "vorname@beispiel.test")
    assert daten["addr_hmac"] != hashlib.sha256(
        b"vorname@beispiel.test").hexdigest()
    # Die Adresse selbst steht NUR im Feld `email` - nirgends sonst.
    ohne_email = {k: v for k, v in daten.items() if k != "email"}
    assert "beispiel.test" not in json.dumps(ohne_email)


def test_eine_fehlerhafte_eingabe_nennt_alle_gruende(dienst):
    antwort = _anmeldung(dienst, email="kein-at",
                         filters={"regions": ["mars"], "keywords": ["ab"]})
    assert antwort.status_code == 400
    assert len(antwort.json()["fehler"]) >= 3
    assert dienst.gesendet == []


def test_unbekannte_felder_reisen_nicht_mit(dienst):
    """Ohne das Saeubern landet alles, was jemand ins Formular-JSON
    schreibt, signiert im Token und von dort im Store."""
    _anmeldung(dienst, filters={"regions": ["europa"], "boeses": ["x" * 5000],
                                "keywords": ["Starlink"]})
    _e, nutzlast = dienst.gesendet[0]
    daten = tokens.lies(KEY, tokens.ZWECK_BESTAETIGUNG, nutzlast["token"],
                        max_alter=tokens.TTL_BESTAETIGUNG)
    assert set(daten["filters"]) == {"branches", "regions", "competitors",
                                     "categories", "keywords"}
    assert "boeses" not in json.dumps(daten)


def test_die_ip_bremse_greift(dienst, monkeypatch):
    monkeypatch.setattr(app_mod, "bremse", IPBremse(erlaubt=3))
    codes = [_anmeldung(dienst).status_code for _ in range(6)]
    assert 429 in codes
    assert len(dienst.gesendet) == 3


def test_ein_klemmender_dispatch_wird_zugegeben(dienst, monkeypatch):
    """Ehrlich bleiben: wenn der Weiterreichweg klemmt, kommt keine Mail -
    und der Nutzer wartet sonst vergeblich auf sie."""
    monkeypatch.setattr(app_mod, "_dispatch", lambda e, n: False)
    antwort = _anmeldung(dienst)
    assert antwort.status_code == 503
    assert "noch einmal" in " ".join(antwort.json()["fehler"])


def test_die_domainliste_weist_neutral_ab(dienst, monkeypatch):
    """Sonst waere die Liste von aussen auslesbar."""
    monkeypatch.setattr(app_mod.einstellungen, "erlaubte_domains", ["vodafone.de"])
    antwort = _anmeldung(dienst)
    assert antwort.status_code == 202
    assert antwort.json()["message"] == app_mod.NEUTRAL
    assert dienst.gesendet == []
    assert _anmeldung(dienst, email="wer@vodafone.de").status_code == 202
    assert len(dienst.gesendet) == 1


# ============================================================  confirm  ====

def test_confirm_loest_das_ereignis_aus_und_bestaetigt(dienst):
    _anmeldung(dienst)
    token = dienst.gesendet[0][1]["token"]
    antwort = dienst.get(f"/confirm/{token}")
    assert antwort.status_code == 200
    assert "Angemeldet" in antwort.text
    assert [e for e, _ in dienst.gesendet] == ["send_doi", "confirm"]


def test_confirm_mit_kaputtem_token_sagt_es_freundlich(dienst):
    antwort = dienst.get("/confirm/voellig.kaputt")
    assert antwort.status_code == 200
    assert "nicht mehr gültig" in antwort.text
    assert dienst.gesendet == []


def test_confirm_bestaetigt_auch_wenn_der_dispatch_klemmt(dienst, monkeypatch):
    """Der Workflow ist wiederholbar; ein Nutzer vor einer Fehlerseite
    klickt den Link ein zweites Mal - und DAS erzeugt zwei Abos."""
    _anmeldung(dienst)
    token = dienst.gesendet[0][1]["token"]
    monkeypatch.setattr(app_mod, "_dispatch", lambda e, n: False)
    assert "Angemeldet" in dienst.get(f"/confirm/{token}").text


def test_das_token_steht_im_pfad_und_nicht_in_der_query(dienst):
    """Eine Query-Zeichenkette landet in Render-Zugriffslogs, in der
    Browser-Historie und potenziell im Referer."""
    _anmeldung(dienst)
    url = dienst.gesendet[0][1]["confirm_url"]
    assert "?" not in url and "/confirm/" in url


# ========================================================  unsubscribe  ====

def test_unsubscribe_bestaetigt_sofort(dienst):
    """Der EINZIGE Abmeldeweg - er muss auch im kalten Zustand tragen."""
    token = tokens.schreibe(KEY, tokens.ZWECK_ABMELDUNG,
                            {"sub_id": "sub_1", "addr_hmac": "abc"})
    antwort = dienst.get(f"/unsubscribe/{token}")
    assert antwort.status_code == 200
    assert "Abgemeldet" in antwort.text
    assert dienst.gesendet[-1][0] == "unsubscribe"


def test_es_gibt_keinen_post_endpunkt_fuer_rfc_8058(dienst):
    """Festlegung 5: die maschinelle Ein-Klick-Abmeldung wuerde mit kurzem
    Timeout in den Render-Kaltstart laufen und still fehlschlagen."""
    token = tokens.schreibe(KEY, tokens.ZWECK_ABMELDUNG, {"sub_id": "s"})
    assert dienst.post(f"/unsubscribe/{token}").status_code == 405
    pfade = {(r.path, tuple(sorted(r.methods))) for r in app_mod.app.routes
             if hasattr(r, "methods")}
    assert not any("POST" in m for p, m in pfade if "unsubscribe" in p)


def test_ein_abmeldelink_laeuft_nicht_ab(dienst):
    """Ein abgelaufener Abmeldelink waere das Gegenteil von Widerruf: die
    Mail von vor zwei Jahren muss ihn noch tragen."""
    alt = tokens.schreibe(KEY, tokens.ZWECK_ABMELDUNG, {"sub_id": "s"},
                          jetzt=time.time() - 3 * 365 * 24 * 3600)
    assert "Abgemeldet" in dienst.get(f"/unsubscribe/{alt}").text


# ============================  die drei tragenden Zusicherungen  ===========

def test_der_dienst_schreibt_nichts_auf_die_platte(dienst, tmp_path,
                                                   monkeypatch):
    """Render Free hat ein ephemeres Dateisystem - und die Architektur
    braucht das gar nicht. Gemessen statt behauptet."""
    monkeypatch.chdir(tmp_path)
    vorher = set(tmp_path.rglob("*"))
    _anmeldung(dienst)
    dienst.get(f"/confirm/{dienst.gesendet[0][1]['token']}")
    assert set(tmp_path.rglob("*")) == vorher


def test_der_dienst_kennt_keinen_versandweg():
    """Kein SMTP, kein Brevo-Aufruf, kein API-Key. Der Key soll nicht auf
    einer oeffentlich erreichbaren Instanz liegen."""
    ordner = Path(app_mod.__file__).parent
    for datei in ordner.glob("*.py"):
        quelle = datei.read_text(encoding="utf-8")
        for verboten in ("smtplib", "brevo", "BREVO", "api.brevo.com",
                         "sendmail", "starttls"):
            assert verboten not in quelle, f"{datei.name}: {verboten}"


def test_das_dispatch_ziel_ist_das_leere_inbox_repo():
    """Ein Token mit contents:write auf telco-radar-mail koennte
    scripts/send_digest.py ueberschreiben - genau die Datei, die der Workflow
    danach MIT dem Entschluesselungsschluessel ausfuehrt."""
    assert app_mod.einstellungen.dispatch_repo.endswith("telco-radar-inbox")
    # Geprueft wird der CODE, nicht der Kommentar - im Modulkopf steht die
    # Begruendung, und die muss den Namen nennen duerfen. Also: keine
    # Zeichenkette im Programmtext nennt das Store-Repo.
    import ast
    baum = ast.parse(Path(app_mod.__file__).read_text(encoding="utf-8"))
    # Docstrings sind Dokumentation, kein Programmtext - sie muessen den
    # Namen nennen duerfen, sonst laesst sich die Regel nicht begruenden.
    docs = set()
    for knoten in ast.walk(baum):
        if isinstance(knoten, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                               ast.ClassDef)):
            koerper = getattr(knoten, "body", [])
            if (koerper and isinstance(koerper[0], ast.Expr)
                    and isinstance(koerper[0].value, ast.Constant)
                    and isinstance(koerper[0].value.value, str)):
                docs.add(id(koerper[0].value))
    texte = [k.value for k in ast.walk(baum)
             if isinstance(k, ast.Constant) and isinstance(k.value, str)
             and id(k) not in docs]
    assert texte, "keine Zeichenketten gefunden - der Test prueft nichts"
    assert any("telco-radar-inbox" in t for t in texte), \
        "das Inbox-Repo kommt gar nicht vor - der Test prueft nichts"
    treffer = [t for t in texte if "telco-radar-mail" in t]
    assert not treffer, treffer


def test_alle_antworten_tragen_die_sicherheitskopfzeilen(dienst):
    _anmeldung(dienst)
    token = dienst.gesendet[0][1]["token"]
    for pfad in ("/form-token", f"/confirm/{token}"):
        kopf = dienst.get(pfad).headers
        assert kopf["Referrer-Policy"] == "no-referrer"
        assert kopf["X-Content-Type-Options"] == "nosniff"
        assert kopf["Cache-Control"] == "no-store"


# =========================================================  IP-Bremse  =====

def test_die_bremse_vergisst_nach_dem_fenster():
    b = IPBremse(erlaubt=2, fenster=100)
    assert b.erlaubt_jetzt("a", jetzt=0)
    assert b.erlaubt_jetzt("a", jetzt=1)
    assert not b.erlaubt_jetzt("a", jetzt=2)
    assert b.erlaubt_jetzt("a", jetzt=200)


def test_die_bremse_trennt_die_absender():
    b = IPBremse(erlaubt=1, fenster=100)
    assert b.erlaubt_jetzt("a", jetzt=0)
    assert not b.erlaubt_jetzt("a", jetzt=1)
    assert b.erlaubt_jetzt("b", jetzt=1)


def test_die_bremse_waechst_nicht_unbegrenzt():
    """Ohne Deckel legt eine Flut mit wechselnden Absendern die Instanz
    lahm - dafuer braucht es nicht einmal boese Absicht."""
    b = IPBremse(erlaubt=5, fenster=10, max_absender=50)
    for i in range(500):
        b.erlaubt_jetzt(f"ip-{i}", jetzt=i)
    assert len(b._spuren) <= 50


# ================================================================  CORS  ====
# Die Seite und dieser Dienst liegen auf VERSCHIEDENEN Hosts
# (telco-radar.onrender.com gegen telco-radar-signup.onrender.com). Jeder
# Formularaufruf ist damit cross-origin, und ohne die Middleware ist das
# Formular im Browser tot, waehrend der Dienst per curl korrekt antwortet -
# gemessen am 13.08.2026 auf der Live-Instanz:
#
#   GET  /form-token   -> 200, aber ohne `Access-Control-Allow-Origin`
#   OPTIONS /subscribe -> 405, der Preflight faellt durch
#
# Die drei Tests hier schicken deshalb einen `Origin`-Header und pruefen die
# ANTWORTKOPFZEILEN. Ein Test, der einfach POSTet, ist gruen, egal wie die
# Middleware steht: TestClient spricht denselben Origin und erzwingt CORS
# ueberhaupt nicht. Genau daran ist der Fehler vorbeigekommen.

EIGENE_SEITE = "https://telco-radar.onrender.com"


def test_form_token_traegt_die_cors_freigabe_der_eigenen_seite(dienst):
    """Ohne diesen Kopf verwirft der Browser die Antwort, und das Formular
    kommt nie ueber den ersten Schritt hinaus."""
    antwort = dienst.get("/form-token", headers={"Origin": EIGENE_SEITE})
    assert antwort.status_code == 200
    assert antwort.headers.get("access-control-allow-origin") == EIGENE_SEITE


def test_der_preflight_auf_subscribe_wird_beantwortet(dienst):
    """Ein POST mit `content-type: application/json` loest einen Preflight
    aus. Ohne Middleware antwortet FastAPI darauf mit 405 - der eigentliche
    POST wird dann nie abgeschickt."""
    antwort = dienst.options("/subscribe", headers={
        "Origin": EIGENE_SEITE,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert antwort.status_code == 200, "Preflight abgelehnt"
    assert antwort.headers.get("access-control-allow-origin") == EIGENE_SEITE
    assert "POST" in antwort.headers.get("access-control-allow-methods", "")


def test_eine_fremde_seite_bekommt_keine_freigabe(dienst):
    """Die Gegenprobe - ohne sie belegen die zwei Tests oben nur, dass
    IRGENDEIN Kopf gesetzt wird. Ein '*' wuerde jeder fremden Seite
    erlauben, das Anmeldeformular in ihrem Namen abzuschicken."""
    antwort = dienst.get("/form-token",
                         headers={"Origin": "https://boese.example"})
    freigabe = antwort.headers.get("access-control-allow-origin")
    assert freigabe != "https://boese.example"
    assert freigabe != "*"
