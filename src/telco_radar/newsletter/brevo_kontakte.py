"""Der Verteiler als Brevo-Liste - die einzige Stelle, an der Adressen liegen.

Seit 11.10.2026 (Antonio: ein Repo statt drei) ersetzt die Liste den
age-verschluesselten Store im privaten Repo. Ein Abonnent ist ein Kontakt in
der Liste `LISTE`; sein ganzer Datensatz ausser der Adresse steht als JSON im
Textattribut `ATTR_ABO` (dieselbe Form wie `subscription.als_dict`, damit
Filter und Einwilligungsnachweis genau eine Schreibweise haben). `ATTR_LETZTE`
haelt das Datum der zuletzt zugestellten Ausgabe: ein Wiederanlauf desselben
Tages schickt nie doppelt.

Abmelden heisst Kontakt loeschen. Brevo vergisst damit die Adresse; ein
spaeterer Anmeldeversuch beginnt wieder mit dem Double-Opt-in.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
from dataclasses import dataclass

from .config import NewsletterKatalog
from .subscription import Abo, als_dict, aus_dict, normalisiere_adresse
from .transport import BrevoFehler, brevo_anfrage

log = logging.getLogger(__name__)

BREVO_KONTAKTE = "https://api.brevo.com/v3/contacts"
LISTE = "Telco Radar Newsletter"
ORDNER = "Telco Radar"
ATTR_ABO = "TR_ABO"
ATTR_LETZTE = "TR_LETZTE"
SEITE = 500


@dataclass
class Kontakt:
    """Ein Abonnent, wie Brevo ihn fuehrt."""

    abo: Abo
    letzte_ausgabe: str
    gesperrt: bool


class BrevoKontakte:
    """Die Liste `LISTE` ueber die Kontakte-API."""

    def __init__(self, api_key: str, *, oeffner=None, timeout: int = 30):
        if not api_key:
            raise BrevoFehler(0, "BREVO_API_KEY fehlt")
        self.api_key = api_key
        self.oeffnen = oeffner
        self.timeout = timeout

    def _anfrage(self, methode: str, pfad: str, koerper: dict | None = None):
        return brevo_anfrage(
            self.api_key,
            methode,
            BREVO_KONTAKTE + pfad,
            koerper,
            oeffner=self.oeffnen,
            timeout=self.timeout,
        )

    def einrichten(self) -> int:
        """Ordner, Liste und Attribute anlegen, falls sie fehlen. Gibt die Listen-ID."""
        vorhandene = {
            a.get("name")
            for a in self._anfrage("GET", "/attributes").get("attributes") or []
        }
        for name in (ATTR_ABO, ATTR_LETZTE):
            if name not in vorhandene:
                self._anfrage("POST", f"/attributes/normal/{name}", {"type": "text"})
        listen = self._anfrage("GET", "/lists?limit=50").get("lists") or []
        for liste in listen:
            if liste.get("name") == LISTE:
                return int(liste["id"])
        ordner = self._anfrage("GET", "/folders?limit=50").get("folders") or []
        ordner_id = next((o["id"] for o in ordner if o.get("name") == ORDNER), None)
        if ordner_id is None:
            ordner_id = self._anfrage("POST", "/folders", {"name": ORDNER})["id"]
        neu = self._anfrage("POST", "/lists", {"name": LISTE, "folderId": ordner_id})
        return int(neu["id"])

    def liste_id(self) -> int | None:
        """Die ID der Liste oder None, solange sie nicht eingerichtet ist."""
        for liste in self._anfrage("GET", "/lists?limit=50").get("lists") or []:
            if liste.get("name") == LISTE:
                return int(liste["id"])
        return None

    def speichern(self, abo: Abo, liste: int) -> None:
        """Anlegen oder aktualisieren. Nur aktive Abos gehoeren in die Liste."""
        if not abo.aktiv:
            raise ValueError("nur aktive Abos gehoeren in die Brevo-Liste")
        datensatz = als_dict(abo)
        datensatz.pop("email", None)
        self._anfrage(
            "POST",
            "",
            {
                "email": abo.email,
                "attributes": {ATTR_ABO: json.dumps(datensatz, ensure_ascii=False)},
                "listIds": [liste],
                "updateEnabled": True,
            },
        )

    def loeschen(self, adresse: str) -> bool:
        """Kontakt loeschen. False, wenn es ihn nicht gab."""
        ziel = "/" + urllib.parse.quote(normalisiere_adresse(adresse), safe="")
        try:
            self._anfrage("DELETE", ziel)
        except BrevoFehler as fehler:
            if fehler.status == 404:
                return False
            raise
        return True

    def ausgabe_vermerken(self, adresse: str, datum: str) -> None:
        """Datum der zugestellten Ausgabe festhalten (gegen Doppelversand)."""
        ziel = "/" + urllib.parse.quote(normalisiere_adresse(adresse), safe="")
        self._anfrage("PUT", ziel, {"attributes": {ATTR_LETZTE: datum}})

    def _seiten(self, liste: int):
        versatz = 0
        while True:
            seite = self._anfrage(
                "GET", f"/lists/{liste}/contacts?limit={SEITE}&offset={versatz}"
            )
            kontakte = seite.get("contacts") or []
            yield from kontakte
            versatz += len(kontakte)
            if not kontakte or versatz >= int(seite.get("count") or 0):
                return

    def adresse_zu_id(self, liste: int, abo_id: str, kennwert: str = "") -> str:
        """Die Adresse zum Abo mit dieser ID oder diesem Kennwert, sonst ''."""
        for k in self._seiten(liste):
            roh = json.loads(str((k.get("attributes") or {}).get(ATTR_ABO) or "{}"))
            if (abo_id and roh.get("id") == abo_id) or (
                kennwert and roh.get("email_hmac") == kennwert
            ):
                return str(k.get("email") or "")
        return ""

    def alle(self, liste: int, katalog: NewsletterKatalog) -> list[Kontakt]:
        """Alle Kontakte der Liste. Ein unlesbarer Datensatz bricht ab."""
        aus: list[Kontakt] = []
        for k in self._seiten(liste):
            attribute = k.get("attributes") or {}
            roh = json.loads(str(attribute.get(ATTR_ABO) or "{}"))
            roh["email"] = k.get("email") or ""
            aus.append(
                Kontakt(
                    abo=aus_dict(roh, katalog),
                    letzte_ausgabe=str(attribute.get(ATTR_LETZTE) or ""),
                    gesperrt=bool(k.get("emailBlacklisted")),
                )
            )
        return aus
