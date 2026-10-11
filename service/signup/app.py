"""Der Signup-Dienst: nimmt Anmeldungen entgegen, prueft sie, bestaetigt per Mail.

Seit 11.10.2026 (Antonio: ein Repo, Verteiler bei Brevo) laeuft mit
`BREVO_API_KEY` alles direkt ueber Brevo (`telco_radar.newsletter.anmeldung`):
Bestaetigungsmail, Kontakt anlegen, Kontakt loeschen. Ohne den Schluessel
gilt bis zum Abbau der alte Weg ueber das leere Inbox-Repo (`_dispatch`).
Der Schluessel liegt damit auf einer oeffentlich erreichbaren Instanz; er
ist ein eigener, einzeln widerrufbarer Brevo-Schluessel.

Die Regeln, die bleiben:

1. **Token stehen im PFADSEGMENT, nicht in der Query** (Render-Zugriffslogs,
   Browser-Historie, `Referer`). Dazu `Referrer-Policy: no-referrer`.
2. Die Antwort auf `/subscribe` ist IMMER dieselbe neutrale Meldung. Wer daraus
   ablesen koennte, ob eine Adresse bekannt ist, haette einen Abfragedienst
   fuer fremde Postfaecher.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from telco_radar.newsletter.config import lade_katalog  # noqa: E402
from telco_radar.newsletter import anmeldung, subscription as sub  # noqa: E402
from telco_radar.report import rechtstexte  # noqa: E402

from . import tokens  # noqa: E402
from .ratelimit import IPBremse  # noqa: E402

log = logging.getLogger("signup")

WURZEL = Path(__file__).resolve().parents[2]

NEUTRAL = (
    "Gleich kommt eine E-Mail. Erst mit dem Klick auf den Link darin sind Sie "
    "angemeldet."
)

NOCHMAL = (
    "Der Dienst hat gerade nicht geantwortet. Bitte den Link in ein paar "
    "Minuten noch einmal anklicken."
)


def _env(name: str, vorgabe: str = "") -> str:
    return os.environ.get(name, vorgabe)


class Einstellungen:
    """Alles aus der Umgebung. Kein Geheimnis im Code, keins auf der Platte."""

    def __init__(self):
        self.token_key = _env("SIGNUP_TOKEN_KEY")
        self.pepper = _env("SIGNUP_PEPPER")
        self.github_token = _env("GITHUB_DISPATCH_TOKEN")
        self.brevo_key = _env("BREVO_API_KEY")
        self.absender = _env("MAIL_FROM", "antonio.fotiadis.francisco@gmail.com")
        self.dispatch_repo = _env(
            "GITHUB_DISPATCH_REPO", "Antonio20045/telco-radar-inbox"
        )
        self.basis_url = _env(
            "SITE_BASE_URL", "https://telco-radar.onrender.com"
        ).rstrip("/")
        self.dienst_url = _env(
            "DIENST_BASE_URL", "https://telco-radar-signup.onrender.com"
        ).rstrip("/")
        self.erlaubte_domains = [
            d for d in _env("ERLAUBTE_DOMAINS", "").split(",") if d.strip()
        ]

    @property
    def einsatzbereit(self) -> bool:
        return bool(
            self.token_key and self.pepper and (self.brevo_key or self.github_token)
        )


app = FastAPI(title="Telco Radar - Anmeldung", docs_url=None, redoc_url=None)
einstellungen = Einstellungen()
bremse = IPBremse()
katalog = lade_katalog(WURZEL)

ERLAUBTE_HERKUENFTE = sorted(
    {einstellungen.basis_url, "https://telco-radar.onrender.com"}
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ERLAUBTE_HERKUENFTE,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["content-type"],
    allow_credentials=False,
    max_age=3600,
)


def _absender(anfrage: Request) -> str:
    """Die Adresse des Aufrufers - hinter Renders Proxy im Header.

    Genommen wird der ERSTE Eintrag von `X-Forwarded-For`; die weiteren sind
    von jedem Aufrufer frei setzbar."""
    weiter = anfrage.headers.get("x-forwarded-for", "")
    if weiter:
        return weiter.split(",")[0].strip()
    return anfrage.client.host if anfrage.client else "?"


def _sicherheitskopfzeilen(antwort: Response) -> Response:
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
    koerper = json.dumps({"event_type": ereignis, "client_payload": nutzlast}).encode(
        "utf-8"
    )
    anfrage = urllib.request.Request(
        ziel,
        data=koerper,
        method="POST",
        headers={
            "Authorization": f"Bearer {einstellungen.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(anfrage, timeout=10) as antwort:
            return 200 <= antwort.status < 300
    except urllib.error.HTTPError as fehler:
        log.error("Dispatch %s abgelehnt: HTTP %s", ereignis, fehler.code)
        return False
    except OSError as fehler:
        log.error("Dispatch %s nicht zustellbar: %s", ereignis, type(fehler).__name__)
        return False


def _seite(titel: str, text: str, *, ziel: str = "") -> HTMLResponse:
    return HTMLResponse(anmeldung.antwortseite(titel, text, ziel=ziel))


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
    return {
        "ok": True,
        "einsatzbereit": einstellungen.einsatzbereit,
        "version": _env("RENDER_GIT_COMMIT", "unbekannt")[:8],
        "cors_fuer": ERLAUBTE_HERKUENFTE,
    }


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
    return {
        "nonce": tokens.schreibe(einstellungen.token_key, tokens.ZWECK_NONCE, {}),
        "min_alter": tokens.NONCE_MIN,
    }


@app.post("/subscribe")
async def subscribe(anfrage: Request) -> JSONResponse:
    """Anmeldung entgegennehmen. Speichert nichts, verschickt nichts."""

    def neutral(status: int = 202) -> JSONResponse:
        return _sicherheitskopfzeilen(
            JSONResponse({"status": "ok", "message": NEUTRAL}, status_code=status)
        )

    try:
        daten = await anfrage.json()
    except (ValueError, TypeError):
        daten = {}
    if not isinstance(daten, dict):
        daten = {}

    if str(daten.get("website") or "").strip():
        log.info("Honeypot ausgeloest")
        return neutral()

    if not bremse.erlaubt_jetzt(_absender(anfrage)):
        log.info("IP-Bremse hat gegriffen")
        return neutral(429)

    try:
        tokens.lies(
            einstellungen.token_key,
            tokens.ZWECK_NONCE,
            str(daten.get("nonce") or ""),
            max_alter=tokens.NONCE_MAX,
            min_alter=tokens.NONCE_MIN,
        )
    except tokens.TokenFehler as fehler:
        log.info("Nonce abgelehnt (%s)", fehler)
        return neutral()

    adresse = sub.normalisiere_adresse(str(daten.get("email") or ""))
    filter_roh = daten.get("filters") or {}

    fehler = sub.pruefe_anmeldung(adresse, filter_roh, katalog)
    if fehler:
        return _sicherheitskopfzeilen(
            JSONResponse({"status": "fehler", "fehler": fehler}, status_code=400)
        )

    fassung = rechtstexte.aktuelle_einwilligung(WURZEL)
    if not daten.get("consent") or fassung is None:
        return _sicherheitskopfzeilen(
            JSONResponse(
                {"status": "fehler", "fehler": ["Ohne Einwilligung keine Anmeldung."]},
                status_code=400,
            )
        )

    if not sub.erlaubt_nach_domainliste(adresse, einstellungen.erlaubte_domains):
        log.info("Domain nicht in der Allowlist")
        return neutral()

    bestaetigung = tokens.schreibe(
        einstellungen.token_key,
        tokens.ZWECK_BESTAETIGUNG,
        {
            "email": adresse,
            "filters": anmeldung.sauberer_filter(filter_roh, katalog),
            "consent_version": fassung.version,
            "consent_hash": fassung.hash,
            "ip_hmac": sub.kennwert(einstellungen.pepper, _absender(anfrage)),
            "ua_hmac": sub.kennwert(
                einstellungen.pepper, anfrage.headers.get("user-agent", "")
            ),
            "addr_hmac": sub.adress_kennwert(einstellungen.pepper, adresse),
        },
    )

    ok = (
        anmeldung.doi(
            einstellungen.brevo_key,
            adresse,
            absender=einstellungen.absender,
            bestaetigen=f"{einstellungen.dienst_url}/confirm/{bestaetigung}",
            basis=einstellungen.basis_url,
        )
        if einstellungen.brevo_key
        else _dispatch(
            "send_doi",
            {
                "token": bestaetigung,
                "token_id": tokens.token_id(bestaetigung),
                "addr_hmac": sub.adress_kennwert(einstellungen.pepper, adresse),
                "confirm_url": f"{einstellungen.dienst_url}/confirm/{bestaetigung}",
            },
        )
    )
    if not ok:
        return _sicherheitskopfzeilen(
            JSONResponse(
                {
                    "status": "fehler",
                    "fehler": [
                        "Die Anmeldung konnte gerade nicht entgegengenommen "
                        "werden. Bitte in ein paar Minuten noch einmal."
                    ],
                },
                status_code=503,
            )
        )
    return neutral()


@app.get("/confirm/{token:path}")
def confirm(token: str) -> HTMLResponse:
    """Die Bestaetigung. Erst hier entsteht ueberhaupt ein Abonnement."""
    try:
        daten = tokens.lies(
            einstellungen.token_key,
            tokens.ZWECK_BESTAETIGUNG,
            token,
            max_alter=tokens.TTL_BESTAETIGUNG,
        )
    except tokens.TokenFehler:
        return _sicherheitskopfzeilen(
            _seite(
                "Dieser Link ist nicht mehr gültig",
                "Bestätigungslinks laufen nach 72 Stunden ab. Melden Sie sich "
                "einfach noch einmal an — es dauert keine Minute.",
                ziel=f"{einstellungen.basis_url}/newsletter.html",
            )
        )

    if einstellungen.brevo_key:
        if not anmeldung.bestaetigen(
            einstellungen.brevo_key,
            daten,
            katalog,
            token_id=tokens.token_id(token),
            pepper=einstellungen.pepper,
            jetzt=datetime.now(UTC),
        ):
            return _sicherheitskopfzeilen(_seite("Das hat nicht geklappt", NOCHMAL))
    else:
        _dispatch(
            "confirm",
            {
                "token": token,
                "token_id": tokens.token_id(token),
                "addr_hmac": daten.get("addr_hmac", ""),
            },
        )
    return _sicherheitskopfzeilen(
        _seite(
            "Angemeldet",
            "Die nächste Ausgabe kommt nach dem nächsten Radar-Lauf, "
            "wenn es zu Ihren Themen etwas Neues gibt.",
            ziel=f"{einstellungen.basis_url}/index.html",
        )
    )


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
        daten = tokens.lies(
            einstellungen.token_key,
            tokens.ZWECK_ABMELDUNG,
            token,
            max_alter=10 * 365 * 24 * 3600,
        )
    except tokens.TokenFehler:
        return _sicherheitskopfzeilen(
            _seite(
                "Dieser Abmeldelink ist nicht lesbar",
                "Schreiben Sie uns bitte kurz — wir tragen Sie von Hand aus. "
                "Die Adresse steht im Impressum.",
                ziel=f"{einstellungen.basis_url}/impressum.html",
            )
        )

    if einstellungen.brevo_key:
        if not anmeldung.abmelden_ueber_brevo(
            einstellungen.brevo_key,
            str(daten.get("sub_id") or ""),
            str(daten.get("addr_hmac") or ""),
        ):
            return _sicherheitskopfzeilen(_seite("Das hat nicht geklappt", NOCHMAL))
    else:
        _dispatch(
            "unsubscribe",
            {
                "token": token,
                "sub_id": daten.get("sub_id", ""),
                "addr_hmac": daten.get("addr_hmac", ""),
            },
        )
    return _sicherheitskopfzeilen(
        _seite(
            "Abgemeldet",
            "Sie bekommen keine weiteren Ausgaben. Ihre E-Mail-Adresse wird gelöscht.",
            ziel=f"{einstellungen.basis_url}/index.html",
        )
    )
