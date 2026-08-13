"""Der Signup-Dienst: nimmt entgegen, prueft, reicht weiter.

**Dieser Dienst speichert nichts und verschickt nichts.** Das ist keine
Sparsamkeit, sondern die tragende Konstruktion des ganzen Newsletters, und
sie folgt aus den Grenzen von Render Free:

  * ausgehend gesperrt auf 25/465/587 -> er KANN keine Mail senden,
  * ephemeres Dateisystem, Spin-down nach 15 Minuten -> er KANN nichts
    behalten,
  * Free-Postgres verfaellt nach 30 Tagen -> auch keine Datenbank.

Daraus folgt der Zuschnitt: **Versand und Speicherung passieren in GitHub
Actions, dieser Dienst reicht signierte Ereignisse weiter.** Ueber die
Brevo-HTTP-API *koennte* er technisch senden - HTTPS ist offen. Er tut es
trotzdem nicht, aus zwei Gruenden, die unabhaengig von der Portfrage gelten:
der API-Key soll nicht auf einer oeffentlich erreichbaren Instanz liegen,
und die 24-Stunden-Sperre je Adresse braucht ohnehin den Zustand, den nur
Actions sieht.

ZWEI SICHERHEITSENTSCHEIDUNGEN, DIE MAN SPAETER NICHT MEHR NACHZIEHT:

1. **Das GitHub-Token zeigt nur auf ein LEERES Dispatch-Repo**
   (`telco-radar-inbox`), nicht auf den Store. Ein Token mit
   `contents: write` auf `telco-radar-mail` koennte `scripts/send_digest.py`
   ueberschreiben - genau die Datei, die der Workflow danach MIT DEM
   ENTSCHLUESSELUNGSSCHLUESSEL ausfuehrt. Wer den Render-Dienst uebernimmt,
   haette damit Codeausfuehrung im Runner und den entschluesselten
   Verteiler.
2. **Token stehen im PFADSEGMENT, nicht in der Query.** Eine Query-
   Zeichenkette landet in Render-Zugriffslogs, in der Browser-Historie und
   potenziell im `Referer` der naechsten Anfrage. Dazu
   `Referrer-Policy: no-referrer`.

Die Antwort auf `/subscribe` ist IMMER dieselbe neutrale Meldung. Wer daraus
ablesen koennte, ob eine Adresse bekannt ist, haette einen Abfragedienst fuer
fremde Postfaecher.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

# Der Dienst lebt im selben Repo wie die Pipeline, laeuft aber als eigener
# Prozess. Der Pfad macht `telco_radar.newsletter` importierbar, ohne dass
# der Dienst das Paket installieren muss - auf Render ist das Repo einfach
# ausgecheckt.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from telco_radar.newsletter.config import lade_katalog          # noqa: E402
from telco_radar.newsletter import subscription as sub          # noqa: E402
from telco_radar.report import rechtstexte                      # noqa: E402

from . import tokens                                            # noqa: E402
from .ratelimit import IPBremse                                 # noqa: E402

log = logging.getLogger("signup")

WURZEL = Path(__file__).resolve().parents[2]

# Die neutrale Antwort. Ein Satz, der nichts darueber verraet, ob die Adresse
# bekannt ist, ob sie sich schon einmal abgemeldet hat oder ob heute schon
# eine Bestaetigungsmail an sie ging.
#
# Die schuetzende Eigenschaft ist die GLEICHHEIT ueber alle Zweige - Honeypot,
# IP-Bremse, abgelehnte Nonce, Domainliste, Erfolg -, nicht der Konjunktiv.
# Bis zum 13.08.2026 stand hier "Wenn alles stimmt, ist eine Bestaetigungsmail
# unterwegs"; der Vorbehalt las sich fuer den Angemeldeten wie ein Zweifel an
# seiner eigenen Eingabe und half niemandem. Wer hier umformuliert, darf nur
# eines nicht tun: die Antwort vom Ausgang abhaengig machen.
NEUTRAL = ("Gleich kommt eine E-Mail. Klick den Link darin — "
           "erst dann bist du angemeldet.")


def _env(name: str, vorgabe: str = "") -> str:
    return os.environ.get(name, vorgabe)


class Einstellungen:
    """Alles aus der Umgebung. Kein Geheimnis im Code, keins auf der Platte."""

    def __init__(self):
        self.token_key = _env("SIGNUP_TOKEN_KEY")
        self.pepper = _env("SIGNUP_PEPPER")
        self.github_token = _env("GITHUB_DISPATCH_TOKEN")
        # Das LEERE Dispatch-Repo, nicht der Store. Siehe Modulkopf.
        self.dispatch_repo = _env("GITHUB_DISPATCH_REPO",
                                  "Antonio20045/telco-radar-inbox")
        self.basis_url = _env("SITE_BASE_URL",
                              "https://telco-radar.onrender.com").rstrip("/")
        # Die Adresse DIESES Dienstes - nicht die der Website. Der
        # Unterschied ist keine Feinheit: `/confirm/...` und
        # `/unsubscribe/...` sind Routen hier, die Website ist eine Static
        # Site und kennt sie nicht. Bis zum 13.08.2026 baute der
        # Bestaetigungslink auf `SITE_BASE_URL` - jede Bestaetigungsmail
        # fuehrte damit auf ein 404, und die Anmeldung konnte niemand
        # abschliessen.
        self.dienst_url = _env("DIENST_BASE_URL",
                               "https://telco-radar-signup.onrender.com").rstrip("/")
        self.erlaubte_domains = [d for d in _env("ERLAUBTE_DOMAINS", "").split(",")
                                 if d.strip()]

    @property
    def einsatzbereit(self) -> bool:
        return bool(self.token_key and self.pepper and self.github_token)


app = FastAPI(title="Telco Radar - Anmeldung", docs_url=None, redoc_url=None)
einstellungen = Einstellungen()
bremse = IPBremse()
katalog = lade_katalog(WURZEL)

# ------------------------------------------------------------------ CORS ----
# Die Seite liegt auf telco-radar.onrender.com, dieser Dienst auf
# telco-radar-signup.onrender.com. JEDER Aufruf des Formulars ist damit
# cross-origin - und ohne diese Middleware ist das Formular im Browser tot,
# waehrend der Dienst per curl tadellos antwortet:
#
#   GET  /form-token  -> 200, aber ohne `Access-Control-Allow-Origin`;
#                        der Browser verwirft die Antwort.
#   OPTIONS /subscribe -> 405, der Preflight faellt durch, der POST wird
#                        nie abgeschickt.
#
# Nichts davon steht in einem Protokoll: der Dienst hat ja korrekt
# geantwortet. Gefunden am 13.08.2026, nachdem Antonio auf der fertigen
# Seite keine Anmeldemoeglichkeit fand.
#
# Warum kein Test das gesehen hat: FastAPIs TestClient spricht denselben
# Origin und erzwingt CORS ueberhaupt nicht. Ein Test, der einfach POSTet,
# ist deshalb gruen, egal wie die Middleware steht. Der Test dazu schickt
# einen `Origin`-Header und prueft die ANTWORTKOPFZEILEN.
#
# Bewusst kein "*": dieser Dienst nimmt Anmeldungen entgegen, und eine
# fremde Seite soll das Formular nicht in ihrem Namen abschicken koennen.
# Erlaubt ist die eigene Seite - dieselbe Adresse, die auch die
# Bestaetigungslinks traegt, also genau eine Stelle zum Pflegen.
#
# Die Liste traegt NEBEN `SITE_BASE_URL` die bekannte Produktionsadresse.
# Das ist keine Verdopplung, sondern der Schutz gegen den einen Fehler, den
# man von aussen nicht sieht: steht `SITE_BASE_URL` im Render-Dienst falsch
# oder gar nicht, dann greift die Freigabe stillschweigend nicht - der
# Preflight antwortet brav 200, nur eben ohne Kopf, und das Formular ist
# wieder tot. `/gesund` gibt die Liste deshalb aus.
ERLAUBTE_HERKUENFTE = sorted({einstellungen.basis_url,
                              "https://telco-radar.onrender.com"})

app.add_middleware(
    CORSMiddleware,
    allow_origins=ERLAUBTE_HERKUENFTE,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["content-type"],
    # Es gibt weder Cookie noch Auth-Header; alles reist signiert im Token.
    # `allow_credentials=True` waere hier nicht nur unnoetig, sondern wuerde
    # die Herkunftspruefung des Browsers aufweichen.
    allow_credentials=False,
    max_age=3600,
)


# ------------------------------------------------------------- Handwerk ----

def _absender(anfrage: Request) -> str:
    """Die Adresse des Aufrufers - hinter Renders Proxy im Header.

    Genommen wird der ERSTE Eintrag von `X-Forwarded-For`; die weiteren sind
    von jedem Aufrufer frei setzbar."""
    weiter = anfrage.headers.get("x-forwarded-for", "")
    if weiter:
        return weiter.split(",")[0].strip()
    return anfrage.client.host if anfrage.client else "?"


def _sicherheitskopfzeilen(antwort: Response) -> Response:
    # `no-referrer`: sonst reist das Bestaetigungstoken beim naechsten Klick
    # im Referer mit, und dann steht eine Adresse in fremden Zugriffslogs.
    antwort.headers["Referrer-Policy"] = "no-referrer"
    antwort.headers["X-Content-Type-Options"] = "nosniff"
    antwort.headers["Cache-Control"] = "no-store"
    return antwort


def _dispatch(ereignis: str, nutzlast: dict) -> bool:
    """Ein `repository_dispatch` an das leere Inbox-Repo.

    **In der Nutzlast steht NIE eine Klaradresse** - sie steckt signiert im
    Token, und das Token geht an einen privaten Workflow. Ein
    Dispatch-Payload landet in der Ereignisliste des Repos.
    """
    ziel = f"https://api.github.com/repos/{einstellungen.dispatch_repo}/dispatches"
    koerper = json.dumps({"event_type": ereignis,
                          "client_payload": nutzlast}).encode("utf-8")
    anfrage = urllib.request.Request(
        ziel, data=koerper, method="POST",
        headers={"Authorization": f"Bearer {einstellungen.github_token}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(anfrage, timeout=10) as antwort:
            return 200 <= antwort.status < 300
    except urllib.error.HTTPError as fehler:
        log.error("Dispatch %s abgelehnt: HTTP %s", ereignis, fehler.code)
        return False
    except OSError as fehler:
        log.error("Dispatch %s nicht zustellbar: %s", ereignis,
                  type(fehler).__name__)
        return False


def _seite(titel: str, text: str, *, ziel: str = "") -> HTMLResponse:
    """Eine schlichte Antwortseite.

    Bewusst ohne Stylesheet und ohne Skript: sie muss auch dann stehen, wenn
    die Static Site gerade nicht erreichbar ist - sonst haette der Nutzer
    nach dem Bestaetigen eine leere Seite vor sich."""
    import html as h
    weiter = (f'<p><a href="{h.escape(ziel, True)}">Weiter zum Portal</a></p>'
              if ziel else "")
    return HTMLResponse(
        "<!DOCTYPE html><html lang=de><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{h.escape(titel)}</title></head>"
        "<body style='font:16px/1.6 Georgia,serif;max-width:38em;margin:8vh auto;padding:0 1.2em'>"
        f"<h1 style='font-size:1.6em'>{h.escape(titel)}</h1>"
        f"<p>{h.escape(text)}</p>{weiter}</body></html>")


# --------------------------------------------------------- die Endpunkte ---

@app.get("/gesund")
def gesund() -> dict:
    """Ob der Dienst sich fuer einsatzbereit haelt - ohne Geheimnisse.

    `version` und `cors_fuer` stehen hier, weil am 13.08.2026 eine halbe
    Stunde daran verging, zu raten, WELCHER Stand auf Render laeuft. Von
    aussen sieht ein Dienst, der einen alten Commit ausliefert, genauso aus
    wie einer, dessen Deploy noch laeuft - und ein Fehler in der
    Origin-Einstellung ist ueberhaupt nicht sichtbar, er zeigt sich nur als
    fehlender Kopf. Render setzt `RENDER_GIT_COMMIT` von selbst; beides sind
    keine Geheimnisse, sondern genau die zwei Angaben, die eine
    Fehlersuche am Formular zuerst braucht.
    """
    return {"ok": True, "einsatzbereit": einstellungen.einsatzbereit,
            "version": _env("RENDER_GIT_COMMIT", "unbekannt")[:8],
            "cors_fuer": ERLAUBTE_HERKUENFTE}


@app.get("/form-token")
def form_token(antwort: Response) -> dict:
    """Eine signierte Nonce fuer das Formular - und der Weckruf nebenbei.

    Sie ersetzt den naheliegenden, aber wertlosen Client-Zeitstempel: der
    kommt aus einer statischen Seite, ist unsigniert und frei faelschbar.
    Diese Nonce traegt ihre Ausstellungszeit im signierten Teil; `/subscribe`
    nimmt nur Nonces zwischen zwei Sekunden und zwei Stunden Alter an.

    Der Nebeneffekt ist der eigentliche Gewinn: das Formular holt sie beim
    SEITENAUFBAU, also weckt sie die Render-Instanz, waehrend der Nutzer noch
    ausfuellt. Der Kaltstart von rund einer Minute faellt damit in der Praxis
    kaum auf.
    """
    _sicherheitskopfzeilen(antwort)
    return {"nonce": tokens.schreibe(einstellungen.token_key,
                                     tokens.ZWECK_NONCE, {}),
            "min_alter": tokens.NONCE_MIN}


@app.post("/subscribe")
async def subscribe(anfrage: Request) -> JSONResponse:
    """Anmeldung entgegennehmen. Speichert nichts, verschickt nichts."""
    def neutral(status: int = 202) -> JSONResponse:
        return _sicherheitskopfzeilen(
            JSONResponse({"status": "ok", "message": NEUTRAL}, status_code=status))

    try:
        daten = await anfrage.json()
    except (ValueError, TypeError):
        daten = {}
    if not isinstance(daten, dict):
        daten = {}

    # 1. Honeypot. Ein Feld, das kein Mensch ausfuellt, weil er es nicht
    #    sieht. Wer es ausfuellt, bekommt dieselbe neutrale Antwort wie alle
    #    anderen - eine erkennbare Ablehnung waere eine Bauanleitung.
    if str(daten.get("website") or "").strip():
        log.info("Honeypot ausgeloest")
        return neutral()

    # 2. Die IP-Bremse. Erste Bremse, KEINE Schutzmassnahme (siehe
    #    ratelimit.py): der Zaehler ist nach jedem Spin-down leer.
    if not bremse.erlaubt_jetzt(_absender(anfrage)):
        log.info("IP-Bremse hat gegriffen")
        return neutral(429)

    # 3. Die signierte Nonce. Mindestalter zwei Sekunden - schneller fuellt
    #    kein Mensch ein Formular aus.
    try:
        tokens.lies(einstellungen.token_key, tokens.ZWECK_NONCE,
                    str(daten.get("nonce") or ""),
                    max_alter=tokens.NONCE_MAX, min_alter=tokens.NONCE_MIN)
    except tokens.TokenFehler as fehler:
        log.info("Nonce abgelehnt (%s)", fehler)
        return neutral()

    adresse = sub.normalisiere_adresse(str(daten.get("email") or ""))
    filter_roh = daten.get("filters") or {}

    # 4. Form der Eingaben. Fehler kommen als LISTE zurueck, damit jemand mit
    #    drei falschen Stichwoertern das in einem Durchgang erfaehrt.
    fehler = sub.pruefe_anmeldung(adresse, filter_roh, katalog)
    if fehler:
        return _sicherheitskopfzeilen(
            JSONResponse({"status": "fehler", "fehler": fehler}, status_code=400))

    # 5. Die Einwilligung. Ohne Haekchen keine Anmeldung, und die FASSUNG
    #    muss die sein, die das Formular gezeigt hat - eine Zustimmung zu
    #    einem Text, den der Nutzer nie gesehen hat, ist keine.
    fassung = rechtstexte.aktuelle_einwilligung(WURZEL)
    if not daten.get("consent") or fassung is None:
        return _sicherheitskopfzeilen(
            JSONResponse({"status": "fehler",
                          "fehler": ["Ohne Einwilligung keine Anmeldung."]},
                         status_code=400))

    # 6. Die Domain-Allowlist. Steht auf leer (Festlegung 3) und wird
    #    trotzdem ausgewertet, damit das Umschalten eine Zeile bleibt. Ein
    #    Abgewiesener bekommt die NEUTRALE Antwort - sonst waere die Liste
    #    von aussen auslesbar.
    if not sub.erlaubt_nach_domainliste(adresse, einstellungen.erlaubte_domains):
        log.info("Domain nicht in der Allowlist")
        return neutral()

    # 7. Das Token. Hier stecken alle Angaben drin - und NUR hier.
    bestaetigung = tokens.schreibe(
        einstellungen.token_key, tokens.ZWECK_BESTAETIGUNG,
        {"email": adresse,
         "filters": _sauberer_filter(filter_roh),
         "consent_version": fassung.version,
         "consent_hash": fassung.hash,
         # Die Kennwerte reisen MIT. Beim Bestaetigen gibt es die
         # Anmeldeanfrage nicht mehr; erst dort gebildet, stuende im
         # Protokoll die IP des Klicks statt die der Einwilligung.
         "ip_hmac": sub.kennwert(einstellungen.pepper, _absender(anfrage)),
         "ua_hmac": sub.kennwert(einstellungen.pepper,
                                 anfrage.headers.get("user-agent", "")),
         "addr_hmac": sub.adress_kennwert(einstellungen.pepper, adresse)})

    ok = _dispatch("send_doi", {
        "token": bestaetigung,
        "token_id": tokens.token_id(bestaetigung),
        # Der Kennwert reist AUCH ausserhalb des Tokens mit: `doi.yml` prueft
        # damit die 24-Stunden-Sperre, ohne das Token entpacken zu muessen.
        "addr_hmac": sub.adress_kennwert(einstellungen.pepper, adresse),
        "confirm_url": f"{einstellungen.dienst_url}/confirm/{bestaetigung}",
    })
    if not ok:
        # Ehrlich bleiben: wenn der Weiterreichweg klemmt, kommt keine Mail,
        # und der Nutzer wartet sonst vergeblich auf sie.
        return _sicherheitskopfzeilen(JSONResponse(
            {"status": "fehler",
             "fehler": ["Die Anmeldung konnte gerade nicht entgegengenommen "
                        "werden. Bitte in ein paar Minuten noch einmal."]},
            status_code=503))
    return neutral()


@app.get("/confirm/{token:path}")
def confirm(token: str) -> HTMLResponse:
    """Die Bestaetigung. Erst hier entsteht ueberhaupt ein Abonnement."""
    try:
        daten = tokens.lies(einstellungen.token_key, tokens.ZWECK_BESTAETIGUNG,
                            token, max_alter=tokens.TTL_BESTAETIGUNG)
    except tokens.TokenFehler:
        return _sicherheitskopfzeilen(_seite(
            "Dieser Link ist nicht mehr gültig",
            "Bestätigungslinks laufen nach 72 Stunden ab. Melden Sie sich "
            "einfach noch einmal an — es dauert keine Minute.",
            ziel=f"{einstellungen.basis_url}/newsletter.html"))

    _dispatch("confirm", {
        "token": token,
        "token_id": tokens.token_id(token),
        "addr_hmac": daten.get("addr_hmac", ""),
    })
    # Die Seite bestaetigt SOFORT, auch wenn der Dispatch klemmt. Der
    # Workflow ist wiederholbar; ein Nutzer, der vor einer Fehlerseite steht,
    # klickt den Link ein zweites Mal - und das erzeugt dann zwei Abos.
    return _sicherheitskopfzeilen(_seite(
        "Angemeldet",
        "Ihre Anmeldung ist bestätigt. Die nächste Ausgabe erhalten Sie "
        "dienstags oder freitags — aber nur dann, wenn es zu Ihren Themen "
        "wirklich etwas Neues gibt.",
        ziel=f"{einstellungen.basis_url}/index.html"))


@app.get("/unsubscribe/{token:path}")
def unsubscribe(token: str) -> HTMLResponse:
    """Die Abmeldung. Der EINZIGE Weg - also muss er belastbar sein.

    Bestaetigt wird SOFORT, die Verarbeitung laeuft asynchron nach. Wer
    klickt, waehrend der Dienst schlaeft, wartet sonst eine Minute vor einem
    Spinner oder sieht einen Fehler - und haelt sich trotzdem fuer
    abgemeldet.

    Es gibt bewusst KEINEN POST-Endpunkt fuer RFC 8058 (Festlegung 5): die
    maschinelle Ein-Klick-Abmeldung wuerde mit kurzem Timeout in genau
    diesen Kaltstart laufen und still fehlschlagen.
    """
    try:
        daten = tokens.lies(einstellungen.token_key, tokens.ZWECK_ABMELDUNG,
                            token, max_alter=10 * 365 * 24 * 3600)
    except tokens.TokenFehler:
        return _sicherheitskopfzeilen(_seite(
            "Dieser Abmeldelink ist nicht lesbar",
            "Schreiben Sie uns bitte kurz — wir tragen Sie von Hand aus. "
            "Die Adresse steht im Impressum.",
            ziel=f"{einstellungen.basis_url}/impressum.html"))

    _dispatch("unsubscribe", {"token": token,
                              "sub_id": daten.get("sub_id", ""),
                              "addr_hmac": daten.get("addr_hmac", "")})
    return _sicherheitskopfzeilen(_seite(
        "Abgemeldet",
        "Sie bekommen keine weiteren Ausgaben. Ihre E-Mail-Adresse wird "
        "gelöscht.",
        ziel=f"{einstellungen.basis_url}/index.html"))


def _sauberer_filter(roh: dict) -> dict:
    """Nur die bekannten Felder, nur die bekannten Formen.

    Ohne das reist alles mit, was jemand ins Formular-JSON schreibt - und
    landet signiert im Token und von dort im Store."""
    aus: dict = {}
    for feld in ("branches", "regions", "competitors", "categories"):
        aus[feld] = sorted({str(w).strip() for w in (roh.get(feld) or [])
                            if str(w).strip()})[:50]
    stichwoerter = []
    for eintrag in (roh.get("keywords") or [])[:katalog.grenzen.max_stichwoerter]:
        if isinstance(eintrag, str):
            term, mode = eintrag, ""
        elif isinstance(eintrag, dict):
            term, mode = str(eintrag.get("term") or ""), str(eintrag.get("mode") or "")
        else:
            continue
        term = term.strip()[:60]
        if term:
            stichwoerter.append({"term": term,
                                 "mode": mode if mode in ("word", "phrase") else ""})
    aus["keywords"] = stichwoerter
    return aus
