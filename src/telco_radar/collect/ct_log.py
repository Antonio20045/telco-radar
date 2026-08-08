"""CT-Radar: was ein Anbieter vorbereitet, bevor er es ankuendigt.

Warum Zertifikatslogs
---------------------
Wer eine Kampagnenseite, eine Zweitmarke oder ein neues Portal startet,
braucht vorher ein TLS-Zertifikat. Seit RFC 6962 landet jedes ausgestellte
Zertifikat in oeffentlichen, append-only Logs, und die Browser verlangen das
- ein Zertifikat, das nicht geloggt ist, gilt als ungueltig. Der Anbieter
kann also nicht vermeiden, dass die Vorbereitung sichtbar wird, ohne die
Seite unbenutzbar zu machen.

Das ist die einzige Signalquelle dieses Projekts, die VOR der
Veroeffentlichung liegt. Presse meldet, wenn es passiert ist; eine
Tarifseite aendert sich, wenn es live ist; ein Zertifikat entsteht, waehrend
es gebaut wird.

Gemessen am 08.08.2026 gegen congstar.de: 79 Zertifikate, 48 verschiedene
DNS-Namen - darunter `jamobil-news.congstar.de` und
`pennymobil.congstarnews.de`, also die Zweitmarken fuer Rewe (ja!mobil) und
Penny. Beide waren ueber keine andere Ebene dieses Radars sichtbar.

Was dieses Modul ausdruecklich NICHT behauptet
----------------------------------------------
Eine neue Subdomain ist ein INDIZ. Sie sagt: hier wurde etwas vorbereitet.
Sie sagt nicht, dass es startet, wann, oder was es ist. Zertifikate entstehen
Wochen vor dem Start, fuer Tests, und fuer Kampagnen, die nie laufen.

Deshalb tragen die Meldungen dieses Moduls `origin="ct_log"`, und ihr Text
sagt den Vorbehalt selbst - nicht als Fussnote, sondern im Satz. Ein Radar,
das Vermutungen wie Tatsachen ausliefert, verbrennt in drei Wochen das
Vertrauen, das die anderen Ebenen sich erarbeitet haben.

Drei Filterstufen, und die Reihenfolge ist der Punkt
----------------------------------------------------
  1. **Grundlinie.** Der erste Abruf einer Domain meldet NIE etwas. Ohne
     diese Regel bestuende die erste Ausgabe aus 48 "neuen" Subdomains, die
     alle seit Jahren existieren. Dieselbe Lehre wie beim Aenderungsradar.
  2. **Rauschen, deterministisch.** `sso`, `mail`, `cdn`, `staging` - die
     Liste steht in `config/ct_domains.yaml`, nicht hier. Verglichen wird
     gegen die LABEL des Namens, nicht gegen die Zeichenkette: als
     Teilkettenfilter haette "ns" aus `news.congstar.de` die interessanteste
     Meldung des Radars geloescht.
  3. **Modell, nur fuer den Rest.** Ein kurzer Aufruf ueber die uebrig
     gebliebenen Namen mit genau einer Frage: Produkt-/Kampagnenname oder
     Infrastruktur? Das Modell darf aussortieren, aber nichts hinzufuegen -
     was die Stufen davor verworfen haben, kommt nicht zurueck.

Ohne Modell laeuft das Modul vollstaendig weiter; dann fehlt nur Stufe 3.
Das ist Absicht: `--no-llm` und der Testlauf duerfen kein Netz brauchen.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

from ..models import Item

log = logging.getLogger(__name__)

API = "https://api.certspotter.com/v1/issuances"

# Die Frist je Domain. Grosse Domains bekommen mehr, aber nicht unbegrenzt -
# certspotter beantwortet telekom.de mit include_subdomains gar nicht.
FRIST_NORMAL = 30.0
FRIST_GROSS = 60.0

# Mehr als das aus einem einzelnen Lauf zu melden, ist keine Frueherkennung
# mehr, sondern ein Umbau der Namensraeume - und dann stimmt vermutlich die
# Grundlinie nicht. Wie bei MAX_AENDERUNGEN_JE_SEITE im Aenderungsradar.
MAX_JE_DOMAIN = 8


class CTFehler(RuntimeError):
    """Basis: der Abruf einer Domain ist nicht zustande gekommen."""


class CTZeitueberschreitung(CTFehler):
    """certspotter hat die Domain nicht in der Frist beantwortet.

    Eigene Klasse, weil der Unterschied zu "keine neuen Subdomains"
    bedeutungstragend ist. Grosse Domains (telekom.de, vodafone.de) laufen
    hier zuverlaessig hinein; das als leeres Ergebnis durchzureichen hiesse,
    eine Falschaussage zu treffen und sie auch noch zu speichern - die
    Grundlinie waere danach leer und der naechste Lauf meldete alles.
    """


@dataclass
class Domain:
    """Eine beobachtete Domain."""

    marke: str
    domain: str
    konzern: str = ""
    gross: bool = False

    @property
    def frist(self) -> float:
        return FRIST_GROSS if self.gross else FRIST_NORMAL


@dataclass
class Fund:
    """Ein neuer Name, der die Filter ueberstanden hat."""

    domain: Domain
    name: str
    zuerst_gesehen: str = ""
    nicht_vor: str = ""
    einschaetzung: str = ""      # vom Modell, leer wenn ohne
    begruendung: str = ""

    def kennung(self) -> str:
        """Stabil ueber Laeufe, verschieden je Name.

        Aus dem DNS-Namen - der ist die Sache selbst und aendert sich nicht.
        Nicht aus einem Titel: denselben Fehler hat der Promo-Zweig schon
        einmal bezahlt (`promo_store.entry_id`), und er kostet jedes Mal die
        Wiedererkennung ueber Laeufe.
        """
        return hashlib.sha256(self.name.encode("utf-8")).hexdigest()[:16]


def lade_domains(root: Path) -> tuple[list[Domain], list[str]]:
    """Domains und Rauschmuster aus der Config."""
    pfad = Path(root) / "config" / "ct_domains.yaml"
    if not pfad.exists():
        return [], []
    daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    domains = [
        Domain(marke=str(d.get("marke") or ""),
               domain=str(d.get("domain") or "").strip().lower(),
               konzern=str(d.get("konzern") or ""),
               gross=bool(d.get("gross")))
        for d in (daten.get("domains") or [])
        if d.get("domain") and d.get("marke")
    ]
    rauschen = [str(r).strip().lower() for r in (daten.get("rauschen") or []) if r]
    return domains, rauschen


def namen_aus_antwort(daten) -> set[str]:
    """Alle DNS-Namen einer certspotter-Antwort.

    Wildcards fliegen raus. `*.congstar.de` ist kein vorbereiteter Dienst,
    sondern ein Sammelzertifikat - es taucht bei jeder Erneuerung auf und
    saehe jedes Mal wie eine Neuigkeit aus.
    """
    if not isinstance(daten, list):
        raise CTFehler(f"unerwartete Antwortform: {type(daten).__name__}")
    namen: set[str] = set()
    for eintrag in daten:
        if not isinstance(eintrag, dict):
            continue
        for name in eintrag.get("dns_names") or []:
            name = str(name).strip().lower().rstrip(".")
            if not name or name.startswith("*."):
                continue
            namen.add(name)
    return namen


def ist_technisch(name: str, rauschen: list[str]) -> bool:
    """Ob der Name nach Infrastruktur aussieht.

    Verglichen wird LABELWEISE. `news.congstar.de` enthaelt "ns" als
    Teilkette; ein Teilkettenfilter haette den Namen verworfen, der dem
    Radar seinen Wert gibt. Die Domain selbst (das letzte und vorletzte
    Label) wird nicht geprueft - `mail.de` als Anbieterdomain waere sonst
    komplett unsichtbar.
    """
    if not rauschen:
        return False
    label = name.split(".")
    # Nur die Praefixe pruefen, nicht die Registrierungsdomain.
    praefixe = label[:-2] if len(label) > 2 else []
    return any(teil in rauschen for teil in praefixe)


def _zuerst(daten, name: str) -> tuple[str, str]:
    """Das aelteste `not_before` zu einem Namen, und der Zeitpunkt der Ausgabe."""
    treffer = [
        str(e.get("not_before") or "")
        for e in daten
        if isinstance(e, dict) and name in {
            str(n).strip().lower().rstrip(".") for n in (e.get("dns_names") or [])
        }
    ]
    treffer = sorted(t for t in treffer if t)
    return (treffer[0] if treffer else ""), (treffer[0][:10] if treffer else "")


class CTSpeicher:
    """Welche Namen schon bekannt sind, je Domain.

    Eine Zeile je Domain, die Namen als sortierte Liste. Das Format ist
    bewusst nicht der Seen-Store: dort steht ein Hash je Zeile, weil es um
    Millionen Meldungen geht. Hier sind es ein paar hundert Namen, und der
    Klartext ist die halbe Diagnose, wenn etwas schiefgeht.
    """

    def __init__(self, pfad: Path) -> None:
        self.pfad = Path(pfad)
        self._daten: dict[str, dict] = {}
        if self.pfad.exists():
            for zeile in self.pfad.read_text(encoding="utf-8").splitlines():
                zeile = zeile.strip()
                if not zeile:
                    continue
                try:
                    satz = json.loads(zeile)
                except json.JSONDecodeError:
                    continue
                if isinstance(satz, dict) and satz.get("domain"):
                    self._daten[str(satz["domain"])] = satz

    def kennt(self, domain: str) -> bool:
        return domain in self._daten

    def namen(self, domain: str) -> set[str]:
        return set(self._daten.get(domain, {}).get("namen") or [])

    def setze(self, domain: str, namen: set[str], stand: str) -> None:
        self._daten[domain] = {"domain": domain, "namen": sorted(namen),
                               "stand": stand}

    def speichern(self) -> None:
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        zeilen = [json.dumps(self._daten[d], ensure_ascii=False)
                  for d in sorted(self._daten)]
        self.pfad.write_text("\n".join(zeilen) + "\n", encoding="utf-8")


def hole(domain: Domain, http_cfg: dict, *, client=None) -> list:
    """Die certspotter-Antwort zu einer Domain.

    Wirft `CTZeitueberschreitung` statt eine leere Liste zurueckzugeben.
    Der Unterschied ist der ganze Punkt der Fehlerklasse.
    """
    params = {"domain": domain.domain, "include_subdomains": "true",
              "expand": "dns_names"}
    kopf = {"User-Agent": http_cfg.get("user_agent", "TelcoRadar/1.0"),
            "Accept": "application/json"}
    try:
        if client is not None:
            antwort = client.get(API, params=params, headers=kopf,
                                 timeout=domain.frist)
        else:
            antwort = httpx.get(API, params=params, headers=kopf,
                                timeout=domain.frist, follow_redirects=True)
    except httpx.TimeoutException as exc:
        raise CTZeitueberschreitung(
            f"{domain.domain} nicht in {domain.frist:.0f}s beantwortet") from exc
    except httpx.HTTPError as exc:
        raise CTFehler(f"{domain.domain}: {exc}") from exc

    if antwort.status_code == 429:
        raise CTFehler(f"{domain.domain}: certspotter drosselt (429)")
    if antwort.status_code != 200:
        raise CTFehler(f"{domain.domain}: HTTP {antwort.status_code}")
    try:
        return antwort.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise CTFehler(f"{domain.domain}: Antwort ist kein JSON") from exc


SYSTEM = (
    "Du beurteilst DNS-Namen, die neu in einem Certificate-Transparency-Log "
    "aufgetaucht sind. Fuer jeden Namen genau eine Frage: sieht er nach einem "
    "Produkt-, Marken- oder Kampagnennamen aus, oder nach technischer "
    "Infrastruktur?\n\n"
    "Antworte als JSON: {\"namen\": [{\"name\": \"...\", \"art\": "
    "\"kampagne\"|\"infrastruktur\"|\"unklar\", \"begruendung\": \"kurz\"}]}\n\n"
    "Regeln:\n"
    "- Marken- und Produktnamen, Aktionsbegriffe, Namen von Zweitmarken, "
    "Wechselaktionen oder Geraetekampagnen sind 'kampagne'.\n"
    "- Zugang, Zustellung, Ueberwachung, Testumgebungen, Auslieferung sind "
    "'infrastruktur'.\n"
    "- Wenn du es nicht entscheiden kannst, 'unklar'. Rate nicht.\n"
    "- Erfinde keine Namen und lasse keinen aus."
)


def bewerte(funde: list[Fund], modell: str, *, komplett=None) -> list[Fund]:
    """Stufe 3: das Modell sortiert Infrastruktur aus.

    Das Modell darf WEGNEHMEN, nicht hinzufuegen. Ein Name, den es nicht
    genannt hat, behaelt seine Einschaetzung "unbewertet" und bleibt drin -
    ein stiller Verlust waere schlimmer als eine Zeile zu viel.
    """
    if not funde:
        return funde
    if komplett is None:  # pragma: no cover - der echte Pfad
        from ..analyze.llm import complete as komplett

    from ..analyze.llm import extract_json

    liste = "\n".join(f"- {f.name}" for f in funde)
    try:
        roh = komplett(SYSTEM, f"Neue Namen:\n{liste}", modell, 8000)
        daten = extract_json(roh) or {}
    except Exception as exc:  # noqa: BLE001
        log.info("CT-Radar: Modellstufe uebersprungen (%s)", str(exc)[:120])
        return funde

    urteil = {}
    for eintrag in (daten.get("namen") or []):
        if isinstance(eintrag, dict) and eintrag.get("name"):
            urteil[str(eintrag["name"]).strip().lower()] = eintrag

    behalten = []
    for f in funde:
        satz = urteil.get(f.name)
        if not satz:
            f.einschaetzung = "unbewertet"
            behalten.append(f)
            continue
        art = str(satz.get("art") or "unklar").lower()
        f.einschaetzung = art
        f.begruendung = str(satz.get("begruendung") or "")[:200]
        if art != "infrastruktur":
            behalten.append(f)
    return behalten


def als_item(f: Fund, stand: datetime) -> Item:
    """Der Fund als Meldung - denselben Weg wie alles andere.

    Der Vorbehalt steht IM Text, nicht als Fussnote daneben. Wer die Zeile
    aus dem Zusammenhang kopiert, kopiert ihn mit.
    """
    zusatz = ""
    if f.einschaetzung == "kampagne":
        zusatz = " Der Name sieht nach einem Produkt- oder Kampagnennamen aus."
    elif f.einschaetzung == "unklar":
        zusatz = " Ob dahinter ein Produkt oder Technik steht, ist offen."
    if f.begruendung:
        zusatz += f" ({f.begruendung})"

    datum = f" vom {f.nicht_vor}" if f.nicht_vor else ""
    return Item(
        title=f"{f.domain.marke}: neue Subdomain {f.name}",
        url=f"https://{f.name}",
        source_name=f"{f.domain.marke} (Zertifikatslog)",
        region="europe",
        operator=f.domain.marke,
        published=stand,
        summary=(
            f"Für {f.name} wurde ein TLS-Zertifikat{datum} ausgestellt. Das "
            f"heißt, dass {f.domain.marke} dort etwas vorbereitet hat — nicht, "
            f"dass es startet oder was es ist. Bedeutung unbestätigt."
            + zusatz
        )[:900],
        origin="ct_log",
        source_url=f"{API}?domain={f.domain.domain}",
        id=f.kennung(),
    )


def sammle(root: Path, http_cfg: dict, *, jetzt: datetime | None = None,
           modell: str = "", komplett=None, client=None
           ) -> tuple[list[Item], dict]:
    """Alle Domains abfragen, neue Namen finden, als Items liefern.

    Der erste Abruf einer Domain legt die Grundlinie und meldet nichts.
    """
    jetzt = jetzt or datetime.now(timezone.utc)
    domains, rauschen = lade_domains(root)
    speicher = CTSpeicher(Path(root) / "data" / "state" / "ct_seen.jsonl")
    bilanz = {"domains": len(domains), "gelesen": 0, "grundlinie": 0,
              "neu_roh": 0, "technisch": 0, "zu_viele": 0,
              "zeitueberschreitung": 0, "fehler": 0, "meldungen": 0}
    funde: list[Fund] = []

    for domain in domains:
        try:
            daten = hole(domain, http_cfg, client=client)
            namen = namen_aus_antwort(daten)
        except CTZeitueberschreitung as exc:
            # Erwartbar bei grossen Domains - und ausdruecklich KEIN leeres
            # Ergebnis. Die Grundlinie bleibt unangetastet.
            bilanz["zeitueberschreitung"] += 1
            log.info("CT-Radar: %s", exc)
            continue
        except CTFehler as exc:
            bilanz["fehler"] += 1
            log.info("CT-Radar: %s", exc)
            continue

        bilanz["gelesen"] += 1
        if not speicher.kennt(domain.domain):
            bilanz["grundlinie"] += 1
            speicher.setze(domain.domain, namen, jetzt.date().isoformat())
            continue

        neu = namen - speicher.namen(domain.domain)
        speicher.setze(domain.domain, namen, jetzt.date().isoformat())
        if not neu:
            continue
        bilanz["neu_roh"] += len(neu)

        gefiltert = [n for n in sorted(neu) if not ist_technisch(n, rauschen)]
        bilanz["technisch"] += len(neu) - len(gefiltert)
        if len(gefiltert) > MAX_JE_DOMAIN:
            # So viele neue Namen auf einmal sind ein Umbau des Namensraums,
            # keine Kampagne.
            bilanz["zu_viele"] += 1
            log.info("CT-Radar: %s meldet %d neue Namen - sieht nach Umbau "
                     "aus, nicht gemeldet", domain.domain, len(gefiltert))
            continue
        for name in gefiltert:
            roh, tag = _zuerst(daten, name)
            funde.append(Fund(domain=domain, name=name, zuerst_gesehen=roh,
                              nicht_vor=tag))

    if funde and modell:
        funde = bewerte(funde, modell, komplett=komplett)

    speicher.speichern()
    items = [als_item(f, jetzt) for f in funde]
    bilanz["meldungen"] = len(items)
    log.info("CT-Radar: %d Domains, %d gelesen, %d Grundlinie, %d neu roh, "
             "%d technisch verworfen, %d Umbau, %d Zeitueberschreitung, "
             "%d Fehler, %d Meldungen",
             bilanz["domains"], bilanz["gelesen"], bilanz["grundlinie"],
             bilanz["neu_roh"], bilanz["technisch"], bilanz["zu_viele"],
             bilanz["zeitueberschreitung"], bilanz["fehler"],
             bilanz["meldungen"])
    return items, bilanz
