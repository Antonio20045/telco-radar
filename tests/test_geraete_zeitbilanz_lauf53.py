"""Nachbau der gemessenen Zeitbilanz von Lauf 53 (24.09.2026, geraete.yml).

BEFUND (aus dem Actions-Log, Sammelphase ab 07:36:08 UTC, `--frist 1500`):
Telekom 07:36-07:37, Saturn+Vodafone bis ~07:45, ElectronicPartner ab
07:45:30, Medimax 07:48:51-07:51:12, mobilcom-debitel 07:52:55-07:57:39,
congstar 07:57:40-07:59:40 mit "56 Produktseiten (180 Preissaetze
gelesen)" und danach `frist` - KEINE der vier Buendel-Tarifseiten
(allnet-flat-*) wurde noch angefragt. Ursache: congstar steht als
`rang: 10` ganz am Ende der Abrufreihenfolge (`collect/geraete/__init__.py`,
`sortiert = sorted(..., key=lambda a: (a.rang, a.name))`), ohne eigene
Zeitreserve - waehrend ElectronicPartner und Medimax seit dem Cron-Fix
(02:17 UTC) real crawlen statt uebersprungen zu werden und dabei echte
Minuten aus demselben Budget verbrauchen.

DIESE DATEI baut die Zeitbilanz nach, NICHT die Netzwerkinhalte: die neun
Anbieter VOR congstar sind Ersatzanbieter (ein Einstieg, eine leere
Kategorieseite), deren einziger Zweck ist, beim Abruf exakt so viel Zeit
zu "kosten" wie am 24.09.2026 gemessen - Name und `rang` sind wortgleich
mit `config/geraete_quellen.yaml`, damit die echte Sortierung
(`(rang, name)`, Bindestrich-/Ziffern-Tiebreak inklusive) unveraendert
nachgebaut wird. congstar selbst laeuft mit dem ECHTEN Adapter
(`congstar_next`) gegen die ECHTE Sitemap-Fixtur (55 Eintraege - fast
wortgleich mit den gemessenen "56 Produktseiten") und die vier ECHTEN
Buendel-Adressen aus der ausgelieferten Konfiguration
(`lade_quellen(root)`).

Frist und Reihenfolge kommen NICHT hartkodiert in diese Datei, sondern
werden aus den echten Dateien gelesen (`.github/workflows/geraete.yml`,
`config/geraete_quellen.yaml`) - der Test haengt so direkt am produktiven
Stand und nicht an einer Kopie, die auseinanderlaufen kann.
"""
import gzip
import re
from datetime import datetime, timezone
from pathlib import Path

from telco_radar.collect.geraete import sammle
import telco_radar.collect.geraete as g
from telco_radar.geraete_config import Anbieter, Einstieg, QuellenConfig, lade_quellen

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_WURZEL = Path(__file__).parent.parent

_ROBOTS_FREI = (200, "User-agent: *\n")
_LEERE_KATEGORIESEITE = "<html><body>keine Links</body></html>"


def _fixture(name: str) -> str:
    pfad = _FIX / name
    if pfad.suffix == ".gz":
        return gzip.open(pfad, "rb").read().decode("utf-8", "replace")
    return pfad.read_text(encoding="utf-8")


def _lies_geraete_frist_aus_workflow() -> float:
    """Der Wert, den `geraete.yml` einem CRON-ausgeloesten Lauf mitgibt -
    also genau der Pfad, ueber den Lauf 52/53 liefen (kein manueller
    `workflow_dispatch`, `github.event.inputs.frist` bleibt leer)."""
    text = (_WURZEL / ".github" / "workflows" / "geraete.yml").read_text(encoding="utf-8")
    treffer = re.search(
        r"--frist\s+\"\$\{\{\s*github\.event\.inputs\.frist\s*\|\|\s*(\d+)\s*\}\}\"",
        text)
    assert treffer, "geraete.yml: die Frist-Fallback-Zeile fehlt oder hat sich geaendert"
    return float(treffer.group(1))


# --------------------------------------------------------------------------
# Die neun Ersatzanbieter VOR congstar - Kosten je Anbieter aus dem Befund
# vom 24.09.2026 (siehe Modulkopf). Wo der Log nur eine Gruppe nennt
# ("Saturn+Vodafone bis ~07:45"), ist die Summe gemessen, die Aufteilung
# zwischen beiden ist eine plausible Naeherung - fuer die Zeitbilanz vor
# congstar zaehlt nur die SUMME.
_FUELLER_KOSTEN = [
    ("Telekom", 1, 52.0),
    ("Saturn", 2, 240.0),
    ("Vodafone", 2, 240.0),
    ("ElectronicPartner", 3, 201.0),   # 07:45:30-07:48:51
    ("Medimax", 3, 141.0),             # 07:48:51-07:51:12
    ("o2", 3, 50.0),
    ("1&1", 4, 53.0),                  # o2+1&1 zusammen 103s (07:51:12-07:52:55)
    ("mobilcom-debitel", 4, 284.0),    # 07:52:55-07:57:39
    ("ALDI TALK", 33, 5.0),            # laeuft NACH congstar, kostet kaum etwas
]


def _fueller_anbieter():
    anbieter, kosten = [], {}
    for name, rang, sekunden in _FUELLER_KOSTEN:
        host = ("https://www.fueller-" +
                re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") +
                ".invalid")
        url = f"{host}/kat"
        anbieter.append(Anbieter(
            name=name, typ="handel", methode="ldjson", rang=rang,
            basis_url=host, rate_limit_sekunden=0,
            einstiege=[Einstieg(url=url, kind="static", pfadmuster="/p/")],
        ))
        kosten[url] = sekunden
    return anbieter, kosten


def _congstar_anbieter() -> Anbieter:
    treffer = [a for a in lade_quellen(_WURZEL).anbieter if a.name == "congstar"]
    assert treffer, "config/geraete_quellen.yaml: congstar-Eintrag fehlt"
    return treffer[0]


# Was EIN Abruf gegen congstar in der Zeitbilanz kostet - etwas oberhalb
# des gemessenen Schnitts (120s / 56 Seiten = 2,14s), damit der Test nicht
# guenstiger rechnet als die Messung.
_KOSTEN_JE_ABRUF_CONGSTAR = 2.2


def _katalog_farben():
    from telco_radar.geraete_config import lade_farben, lade_katalog
    return lade_katalog(_WURZEL), lade_farben(_WURZEL)


def _congstar_bilanz(monkeypatch, frist_sekunden: float):
    """Den Nachbau EINMAL bauen und laufen lassen - beide Tests unten
    unterscheiden sich nur im uebergebenen Budget (G5, keine Dopplung)."""
    uhr = {"t": 0.0}
    monkeypatch.setattr(g.time, "monotonic", lambda: uhr["t"])
    monkeypatch.setattr(g.time, "sleep", lambda s: uhr.__setitem__("t", uhr["t"] + s))

    fueller, fueller_kosten = _fueller_anbieter()
    congstar = _congstar_anbieter()

    sitemap_url = next(e.url for e in congstar.einstiege if e.kind == "sitemap")
    buendel_urls = [e.url for e in congstar.einstiege if e.kind == "buendel"]
    assert len(buendel_urls) == 4, \
        "congstar: die vier Tarifseiten fehlen in der Konfiguration"

    sitemap_text = _fixture("congstar_sitemap_devices.xml")
    produkt_urls = set(re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sitemap_text))
    assert len(produkt_urls) >= 50, "Sitemap-Fixtur: zu wenige Produktseiten"

    produkt_seite = _fixture("congstar_produkt_iphone17.html.gz")
    s_seite = _fixture("congstar_tarifseite_allnet_flat_s.html.gz")
    m_seite = _fixture("congstar_tarifseite_allnet_flat_m.html.gz")
    # xs/l: keine eigenen Fixturen gespeichert - dieselbe Seitenform wie
    # s/m wiederverwendet. `lies_buendel` bekommt die URL als Parameter und
    # liest den Tarifnamen NICHT aus ihr, sondern aus der Nutzlast - siehe
    # test_geraete_buendel_congstar.py.
    buendel_seiten = {buendel_urls[0]: s_seite, buendel_urls[1]: s_seite,
                      buendel_urls[2]: m_seite, buendel_urls[3]: m_seite}

    def hole(url, kopfzeilen=None, user_agent=None):
        if url.endswith("/robots.txt"):
            return _ROBOTS_FREI
        if url in fueller_kosten:
            uhr["t"] += fueller_kosten[url]
            return (200, _LEERE_KATEGORIESEITE)
        if url == sitemap_url:
            uhr["t"] += _KOSTEN_JE_ABRUF_CONGSTAR
            return (200, sitemap_text)
        if url in produkt_urls:
            uhr["t"] += _KOSTEN_JE_ABRUF_CONGSTAR
            return (200, produkt_seite)
        if url in buendel_seiten:
            uhr["t"] += _KOSTEN_JE_ABRUF_CONGSTAR
            return (200, buendel_seiten[url])
        return (404, "")

    quellen = QuellenConfig(anbieter=[*fueller, congstar])
    ergebnis = sammle(quellen, *_katalog_farben(), hole, "2026-09-24",
                      datetime(2026, 9, 24, 7, 36, 8, tzinfo=timezone.utc),
                      frist_sekunden=frist_sekunden)
    bilanz = next(b for b in ergebnis["anbieter"] if b.name == "congstar")
    return bilanz, produkt_urls, buendel_urls


def _erwarte_vollstaendigen_congstar_lauf(bilanz, produkt_urls, buendel_urls):
    assert bilanz.status == "ok", (
        f"congstar verhungert weiterhin: status={bilanz.status!r}, "
        f"grund={bilanz.grund!r}, "
        f"{bilanz.produkte_abgerufen} Produkte, "
        f"{len(bilanz.buendel)} Buendel-Saetze")
    assert bilanz.vollstaendig is True, \
        "ein nicht vollstaendig gelesener congstar darf nicht altern (Regel 6)"

    gelesene_buendel_urls = {s["url"] for s in bilanz.buendel}
    assert gelesene_buendel_urls == set(buendel_urls), (
        "nicht alle vier Tarifseiten wurden gelesen: "
        f"gelesen={gelesene_buendel_urls}, erwartet={set(buendel_urls)}")
    assert bilanz.produkte_abgerufen >= len(produkt_urls), (
        f"nicht alle {len(produkt_urls)} Produktseiten wurden gelesen "
        f"({bilanz.produkte_abgerufen} Produkte extrahiert)")


def test_congstar_bekommt_im_nachbau_von_lauf_53_einen_vollstaendigen_lauf(monkeypatch):
    """End-to-End mit dem AUSGELIEFERTEN Budget (gelesen aus geraete.yml -
    heute 1800s). Deckt beide Teile der Abhilfe zusammen ab: Reihenfolge
    UND groesseres Budget."""
    frist = _lies_geraete_frist_aus_workflow()
    bilanz, produkt_urls, buendel_urls = _congstar_bilanz(monkeypatch, frist)
    _erwarte_vollstaendigen_congstar_lauf(bilanz, produkt_urls, buendel_urls)


def test_die_neue_reihenfolge_allein_reicht_schon_beim_alten_budget(monkeypatch):
    """Isoliert den REIHENFOLGE-Teil der Abhilfe: 1500s war das Budget von
    Lauf 52/53 selbst (siehe Modulkopf), bewusst NICHT aus geraete.yml
    gelesen. congstar muss schon hier vollstaendig durchlaufen - sonst
    haengt die Abhilfe allein am groesseren Budget und waere beim naechsten
    Verzug wieder zu knapp (Antonios Hinweis im Auftrag)."""
    bilanz, produkt_urls, buendel_urls = _congstar_bilanz(monkeypatch, 1500.0)
    _erwarte_vollstaendigen_congstar_lauf(bilanz, produkt_urls, buendel_urls)
