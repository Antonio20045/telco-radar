"""Tarifwelt: eine als „nicht lieferbar“ gelesene Speicherstufe zählt nicht weiter.

Befund 13.11.2026: Die Geräteseite zeigte „Samsung Galaxy S26 Ultra 512 GB -
Saturn/MediaMarkt · Telekom-Netz 1.234,70 €“ als günstigsten Wettbewerber. Das
Bündel stammt vom 12.11.; am 13.11. las der Tarifwelt-Lauf die 512-GB-Stufe als
„nicht lieferbar“, die Lücke blieb aber Text im Lauf und erreichte den Bestand nie.

Vertrag (Issue #123):
- Sammeln: `geraete_tarifwelt.stufe` setzt bei allen Tarifwelt-Bündeln desselben
  Geräts und derselben Speicherstufe, die VOR dem Lauftag abgerufen wurden, das
  Feld `nicht_lieferbar_am` (ISO-Datum des Laufs). Nicht gelesen ist nicht
  „nicht lieferbar“; ein Abbruch markiert nur, was vorher gelesen wurde.
- Lesen: `geraete_sortiment.lies` gibt ein Bündel mit `nicht_lieferbar_am` nach
  seinem `abgerufen_am` als Kopie zurück, die in der Notbremse nicht zählt und den
  Zustand „nicht lieferbar“ nennt; jünger gelesene Bündel zählen wieder.

Alle Nutzlasten stehen klein im Test; feste Tage 12.11. und 13.11.2026, kein Netz,
keine Uhr, kein Zugriff auf data/ oder site/.
"""

from __future__ import annotations

import copy
import dataclasses
import json
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from telco_radar import geraete_tarifwelt, tarifwelt_bestand
from telco_radar.analyze.tco_store import TcoDB
from telco_radar.geraete_model import device_id, sku_id
from telco_radar.report import geraete_notbremse, geraete_sortiment
from telco_radar.tarif_bezug import Tarifbestand
from telco_radar.tco_model import Buendel

GESTERN = "2026-11-12"
HEUTE = "2026-11-13"
FELD = "nicht_lieferbar_am"
API = "https://tarife-api2.mediamarkt.de/v1/productdetail"
SHOP = "https://tarife.mediamarkt.de/smartphones"
TELEKOM = "Saturn/MediaMarkt · Telekom-Netz"
O2 = "Saturn/MediaMarkt · o2-Netz"

"""Modell-ID -> (Hersteller, Name, Pfad, Slug), wie in der Tarifwelt-Zuordnung."""
MODELLE = {
    "samsung-galaxy-s26-ultra": (
        "Samsung",
        "Galaxy S26 Ultra",
        "samsung",
        "galaxy-s26-ultra",
    ),
    "samsung-galaxy-s26": ("Samsung", "Galaxy S26", "samsung", "galaxy-s26"),
    "apple-iphone-17": ("Apple", "iPhone 17", "apple", "iphone-17"),
}
ULTRA = "samsung-galaxy-s26-ultra"
S26 = "samsung-galaxy-s26"
IPHONE = "apple-iphone-17"

LEITER = (("xs", 15.0), ("s", 30.0), ("m", 60.0), ("l", 120.0), ("xl", None))


@dataclass
class _Quelle:
    methode: str
    aktiv: bool
    rate_limit_sekunden: float = 0.0


@dataclass
class _Quellen:
    anbieter: list


def _tarifbestand() -> Tarifbestand:
    """Die Vodafone-Leiter „mit Smartphone“; ohne sie ruft die Stufe nichts ab."""
    saetze = []
    for i, (k, gb) in enumerate(LEITER):
        saetze.append(
            {
                "tarif_id": f"vodafone:mobil-{k}",
                "anbieter": "Vodafone",
                "name": f"Vodafone Mobil {k.upper()} mit Smartphone",
                "datenvolumen_gb": gb if gb is not None else float("inf"),
                "grundgebuehr": 20.0 + i * 10,
            }
        )
    return Tarifbestand(saetze)


def _sku(modell: str, speicher_gb: int) -> str:
    hersteller, name, _, _ = MODELLE[modell]
    return sku_id(device_id(hersteller, name), speicher_gb, None)


def _buendel(
    modell: str,
    speicher_gb: int,
    anbieter: str = TELEKOM,
    tarif: str = "allnet50",
    abgerufen_am: str = GESTERN,
    tarif_id: str | None = None,
) -> Buendel:
    """Ein Tarifwelt-Bündel, wie es der Lauf vom 12.11. abgelegt hätte."""
    _, _, pfad, slug = MODELLE[modell]
    return Buendel(
        sku_id=_sku(modell, speicher_gb),
        anbieter=anbieter,
        tarif_name=f"Tarif {tarif}",
        tarif_id=tarif_id or f"{tarifwelt_bestand.PRAEFIX}{tarif}",
        tarif_id_guete="niedrig",
        tarif_monatlich=49.95,
        geraet_zuzahlung=29.99,
        geraet_monatsrate=0.0,
        laufzeit_monate=24,
        anschlusspreis=0.0,
        quelle_url=f"{SHOP}/{pfad}/{slug}/?speicher={speicher_gb}&tfi={tarif}",
        abgerufen_am=abgerufen_am,
        herleitung="tarifwelt_productdetail",
        zustand="neu",
    )


def _congstar(modell: str, speicher_gb: int) -> Buendel:
    """Ein Netzbetreiber-Bündel desselben Geräts: gehört nicht der Tarifwelt."""
    return Buendel(
        sku_id=_sku(modell, speicher_gb),
        anbieter="congstar",
        tarif_name="congstar Allnet Flat M",
        tarif_id="congstar:allnet-m",
        tarif_monatlich=25.0,
        geraet_zuzahlung=1.0,
        geraet_monatsrate=40.0,
        laufzeit_monate=24,
        anschlusspreis=0.0,
        quelle_url="https://www.congstar.de/handys/samsung/galaxy-s26-ultra/",
        abgerufen_am=GESTERN,
        zustand="neu",
    )


def _bestand(tmp_path, buendel: list[Buendel]) -> TcoDB:
    """Echter Bestand in `tmp_path`: abgelegt je Abruftag, gesichert, neu gelesen."""
    pfad = tmp_path / "state" / "geraete_tco.json"
    tco = TcoDB(pfad)
    je_tag: dict[str, list[Buendel]] = {}
    for b in buendel:
        je_tag.setdefault(b.abgerufen_am, []).append(b)
    for tag, liste in sorted(je_tag.items()):
        tco.upsert_buendel(liste, tag)
    assert tco.save(GESTERN)
    return TcoDB(pfad)


def _uebersicht(slug: str, stufen: dict[int, bool]) -> str:
    """Kleinste Geräteübersicht `productdetail/<slug>`: je Speicher eine Farbe,
    `available` sagt, ob die Stufe lieferbar ist."""
    return json.dumps(
        {
            "hardware": {
                "variantFilter": [
                    {
                        "storage": gb,
                        "offerGroupId": f"g-{slug}-{gb}",
                        "offerId": f"o-{slug}-{gb}",
                        "hwi": f"h-{slug}-{gb}",
                        "available": lieferbar,
                    }
                    for gb, lieferbar in stufen.items()
                ]
            }
        }
    )


def _hole(uebersichten: dict[str, tuple[int, str]], tarifliste=(200, "[]")):
    """Antwortet wie die Schnittstelle: robots.txt fehlt (keine Regeln), je Slug die
    Übersicht, jede Tarifliste mit `tarifliste` (Standard: leer = „keine Tarife“)."""
    aufrufe: list[str] = []

    def hole(url, **kw):
        aufrufe.append(url)
        if url.endswith("/robots.txt"):
            return (404, "")
        rest = url.split("/v1/productdetail/", 1)[1]
        if "/tariff?" in rest:
            return tarifliste
        if "?" in rest:
            return (404, "")
        return uebersichten[rest]

    return hole, aufrufe


def _uhr():
    return datetime(2026, 11, 13, 2, 17, tzinfo=UTC)


def _stufe(monkeypatch, tco: TcoDB, hole, modelle: set[str]) -> dict:
    """Der Tageslauf vom 13.11. über den öffentlichen Eingang `stufe`."""
    monkeypatch.setattr(
        geraete_tarifwelt, "pflicht_modelle", lambda: frozenset(modelle)
    )
    monkeypatch.setattr(geraete_tarifwelt.time, "sleep", lambda s: None)
    return geraete_tarifwelt.stufe(
        _Quellen([_Quelle(tarifwelt_bestand.METHODE, True)]),
        _tarifbestand(),
        hole,
        _uhr,
        HEUTE,
        tco.path.parent,
        tco,
    )


def _satz(tco: TcoDB, b: Buendel) -> dict:
    satz = tco.nach_id(b.id)
    assert satz is not None, f"Bündel {b.id} fehlt im Bestand"
    return satz


def _markiert(tco: TcoDB, b: Buendel) -> object:
    return _satz(tco, b).get(FELD)


def test_befund_ultra_512_nicht_lieferbar_zaehlt_danach_nicht_mehr(
    tmp_path, monkeypatch
):
    """Ende zu Ende wie am 13.11.: Bestand vom 12.11., Lauf liest 512 GB als nicht
    lieferbar, die Seite (`lies` + Notbremse) darf den Preis nicht mehr zählen."""
    alt = _buendel(ULTRA, 512)
    tco = _bestand(tmp_path, [alt])
    hole, _ = _hole(
        {"galaxy-s26-ultra": (200, _uebersicht("galaxy-s26-ultra", {512: False}))}
    )
    _stufe(monkeypatch, tco, hole, {ULTRA})

    (gelesen,) = geraete_sortiment.lies(
        tco.buendel(), tmp_path / "data" / "state", HEUTE
    )
    flags = geraete_notbremse.felder_aus_satz(gelesen, HEUTE)
    assert not geraete_notbremse.zaehlt(flags), (
        "nicht lieferbare Stufe zählt weiter: S26 Ultra 512 GB vom 12.11. stellt "
        f"nach dem Lauf vom 13.11. noch einen Preis (Bestand: {FELD}="
        f"{_satz(tco, alt).get(FELD)!r})"
    )


def test_nicht_lieferbare_stufe_markiert_alle_alten_tarifwelt_buendel_dieser_stufe(
    tmp_path, monkeypatch
):
    """512 GB nicht lieferbar, 256 GB lieferbar (ohne Tarife): beide Tarifwelt-Bündel
    der 512-GB-Stufe vom 12.11. tragen danach `nicht_lieferbar_am` = 13.11.; der Lauf
    liefert dabei kein einziges Bündel. Gegenproben im selben Bestand: andere Stufe,
    anderes Gerät (S26 ohne Ultra), anderer Anbieter (congstar) und ein Bündel vom
    Lauftag selbst bleiben ohne Feld."""
    telekom_512 = _buendel(ULTRA, 512, TELEKOM, "allnet50")
    o2_512 = _buendel(ULTRA, 512, O2, "o2-unlimited-m")
    ultra_256 = _buendel(ULTRA, 256, TELEKOM, "allnet50")
    s26_512 = _buendel(S26, 512, TELEKOM, "allnet50")
    congstar_512 = _congstar(ULTRA, 512)
    heute_512 = _buendel(ULTRA, 512, O2, "o2-mobile-l", abgerufen_am=HEUTE)
    tco = _bestand(
        tmp_path, [telekom_512, o2_512, ultra_256, s26_512, congstar_512, heute_512]
    )

    hole, _ = _hole(
        {
            "galaxy-s26-ultra": (
                200,
                _uebersicht("galaxy-s26-ultra", {256: True, 512: False}),
            )
        }
    )
    bilanz = _stufe(monkeypatch, tco, hole, {ULTRA})
    assert bilanz.get("buendel") == 0, bilanz

    for b in (telekom_512, o2_512):
        assert _markiert(tco, b) == HEUTE, (
            f"nicht lieferbare Stufe zählt weiter: {b.anbieter} {b.sku_id} vom "
            f"{b.abgerufen_am} trägt nach dem Lauf vom {HEUTE} kein {FELD} "
            f"(gefunden: {_markiert(tco, b)!r})"
        )
    for b, was in (
        (ultra_256, "andere Speicherstufe"),
        (s26_512, "anderes Gerät"),
        (congstar_512, "anderer Anbieter"),
        (heute_512, "am Lauftag abgerufen"),
    ):
        assert FELD not in _satz(tco, b), f"{was} wurde markiert: {b.id}"


def test_feld_uebersteht_save_und_neues_laden(tmp_path, monkeypatch):
    alt = _buendel(ULTRA, 512)
    tco = _bestand(tmp_path, [alt, _buendel(ULTRA, 256)])
    hole, _ = _hole(
        {"galaxy-s26-ultra": (200, _uebersicht("galaxy-s26-ultra", {512: False}))}
    )
    _stufe(monkeypatch, tco, hole, {ULTRA})
    assert tco.save(HEUTE)

    neu = TcoDB(tco.path)
    assert _markiert(neu, alt) == HEUTE, (
        f"nicht lieferbare Stufe zählt weiter: {FELD} fehlt nach save() und neuem "
        f"Laden (gefunden: {_markiert(neu, alt)!r})"
    )
    roh = json.loads(tco.path.read_text(encoding="utf-8"))
    assert any(s.get(FELD) == HEUTE for s in roh["buendel"]), "Feld nicht in der Datei"


def test_1_tb_der_schnittstelle_trifft_die_katalogstufe_1024(tmp_path, monkeypatch):
    """Die Tarifwelt nennt 1 TB „1000 GB“, die SKU im Bestand trägt 1024 GB."""
    alt = _buendel(ULTRA, 1024)
    tco = _bestand(tmp_path, [alt, _buendel(ULTRA, 512)])
    hole, _ = _hole(
        {
            "galaxy-s26-ultra": (
                200,
                _uebersicht("galaxy-s26-ultra", {512: True, 1000: False}),
            )
        }
    )
    _stufe(monkeypatch, tco, hole, {ULTRA})
    assert _markiert(tco, alt) == HEUTE, (
        f"nicht lieferbare Stufe zählt weiter: 1-TB-Stufe ({alt.sku_id}) ohne {FELD}"
    )
    assert FELD not in _satz(tco, _buendel(ULTRA, 512)), "512 GB wurde markiert"


@pytest.mark.parametrize(
    "tarifliste",
    [(404, "nicht gefunden"), (200, "[]")],
    ids=["luecke_tarifliste_http_404", "luecke_keine_tarife"],
)
def test_nicht_lesbare_tarifliste_ist_nicht_nicht_lieferbar(
    tmp_path, monkeypatch, tarifliste
):
    """256 GB lieferbar, aber ihre Tarifliste bleibt Lücke („Tarifliste: …“ oder
    „keine Tarife“): kein Feld. Dieselbe Übersicht nennt 512 GB nicht lieferbar:
    das Feld (positive Wirkung im selben Lauf)."""
    nicht_gelesen = _buendel(ULTRA, 256)
    nicht_lieferbar = _buendel(ULTRA, 512)
    tco = _bestand(tmp_path, [nicht_gelesen, nicht_lieferbar])
    hole, _ = _hole(
        {
            "galaxy-s26-ultra": (
                200,
                _uebersicht("galaxy-s26-ultra", {256: True, 512: False}),
            )
        },
        tarifliste=tarifliste,
    )
    _stufe(monkeypatch, tco, hole, {ULTRA})
    assert _markiert(tco, nicht_lieferbar) == HEUTE, (
        f"nicht lieferbare Stufe zählt weiter: 512 GB ohne {FELD}"
    )
    assert FELD not in _satz(tco, nicht_gelesen), (
        "nicht gelesene Tarifliste wurde als nicht lieferbar markiert"
    )


def test_unlesbare_uebersicht_ist_nicht_nicht_lieferbar(tmp_path, monkeypatch):
    """iPhone 17: Übersicht nicht lesbar - keins seiner Bündel bekommt das Feld.
    S26 Ultra im selben Lauf: 512 GB nicht lieferbar - das Feld."""
    iphone_256 = _buendel(IPHONE, 256)
    iphone_512 = _buendel(IPHONE, 512)
    ultra_512 = _buendel(ULTRA, 512)
    tco = _bestand(tmp_path, [iphone_256, iphone_512, ultra_512])
    hole, _ = _hole(
        {
            "iphone-17": (200, "kein json"),
            "galaxy-s26-ultra": (200, _uebersicht("galaxy-s26-ultra", {512: False})),
        }
    )
    _stufe(monkeypatch, tco, hole, {IPHONE, ULTRA})
    assert _markiert(tco, ultra_512) == HEUTE, (
        f"nicht lieferbare Stufe zählt weiter: S26 Ultra 512 GB ohne {FELD}"
    )
    for b in (iphone_256, iphone_512):
        assert FELD not in _satz(tco, b), f"unlesbare Übersicht markiert {b.id}"


def test_abbruch_markiert_nur_was_vorher_als_nicht_lieferbar_gelesen_wurde(
    tmp_path, monkeypatch
):
    """iPhone 17 wird zuerst gelesen (512 GB nicht lieferbar), beim S26 Ultra kommt
    eine Schutzantwort (403): der Lauf bricht ab. Das iPhone-Bündel trägt das Feld,
    das nie gelesene S26-Ultra-Bündel nicht."""
    iphone_512 = _buendel(IPHONE, 512)
    ultra_512 = _buendel(ULTRA, 512)
    tco = _bestand(tmp_path, [iphone_512, ultra_512])
    hole, aufrufe = _hole(
        {
            "iphone-17": (200, _uebersicht("iphone-17", {256: True, 512: False})),
            "galaxy-s26-ultra": (403, "Forbidden"),
        }
    )
    bilanz = _stufe(monkeypatch, tco, hole, {IPHONE, ULTRA})
    assert bilanz.get("status") == "abgebrochen", bilanz
    assert aufrufe[-1] == f"{API}/galaxy-s26-ultra", "nach der Schutzantwort kein Abruf"
    assert _markiert(tco, iphone_512) == HEUTE, (
        f"nicht lieferbare Stufe zählt weiter: iPhone 17 512 GB, vor dem Abbruch als "
        f"nicht lieferbar gelesen, ohne {FELD}"
    )
    assert FELD not in _satz(tco, ultra_512), (
        "Abbruch markiert ein nie gelesenes Bündel"
    )


def test_wiederholung_desselben_laufs_ergibt_denselben_bestand(tmp_path, monkeypatch):
    alt = _buendel(ULTRA, 512)
    tco = _bestand(tmp_path, [alt, _buendel(ULTRA, 256), _congstar(ULTRA, 512)])
    uebersicht = {
        "galaxy-s26-ultra": (
            200,
            _uebersicht("galaxy-s26-ultra", {256: True, 512: False}),
        )
    }

    _stufe(monkeypatch, tco, _hole(uebersicht)[0], {ULTRA})
    nach_erstem = copy.deepcopy(tco.buendel())
    _stufe(monkeypatch, tco, _hole(uebersicht)[0], {ULTRA})

    assert _markiert(tco, alt) == HEUTE, (
        f"nicht lieferbare Stufe zählt weiter: kein {FELD}"
    )
    assert tco.buendel() == nach_erstem, "zweiter gleicher Lauf verändert den Bestand"


def _roh(b: Buendel, **zusatz) -> dict:
    """Ein Bündelsatz, wie er in `geraete_tco.json` steht (Prüfstelle: gültig)."""
    return {**dataclasses.asdict(b), "id": b.id, "pruefung": "gueltig", **zusatz}


def _lies(saetze: list[dict], tmp_path) -> dict[str, dict]:
    gelesen = geraete_sortiment.lies(saetze, tmp_path / "data" / "state", HEUTE)
    return {s["id"]: s for s in gelesen}


def test_lies_nimmt_dem_nicht_lieferbaren_buendel_die_zahl_als_kopie(tmp_path):
    satz = _roh(_buendel(ULTRA, 512), **{FELD: HEUTE})
    ohne = _roh(_buendel(ULTRA, 256))
    vorher = copy.deepcopy([satz, ohne])

    gelesen = _lies([satz, ohne], tmp_path)
    flags = geraete_notbremse.felder_aus_satz(gelesen[satz["id"]], HEUTE)
    assert geraete_notbremse.felder_aus_satz(gelesen[ohne["id"]], HEUTE)["zaehlt"], (
        "Gegenprobe: ein Bündel ohne Feld zählt wie bisher"
    )
    assert not flags["zaehlt"], (
        f"nicht lieferbare Stufe zählt weiter: {FELD}={HEUTE} "
        f"nach abgerufen_am={GESTERN}"
    )
    zustand = flags["notbremse"] or {}
    assert "nicht lieferbar" in str(zustand.get("kurz", "")), (
        f"Zustand nennt nicht „nicht lieferbar“: {zustand!r}"
    )
    assert "führt dieses Gerät nicht mehr" not in str(zustand.get("satz", "")), zustand
    assert not flags.get("nicht_im_sortiment"), (
        "nicht lieferbar ist nicht „nicht im Sortiment“"
    )
    assert gelesen[satz["id"]] is not satz, "lies gibt das Bestands-Dict selbst zurück"
    assert [satz, ohne] == vorher, "lies verändert den übergebenen Bestand"


@pytest.mark.parametrize(
    "abgerufen_am", [HEUTE, "2026-11-14"], ids=["gleicher_tag", "juenger"]
)
def test_rueckkehr_nach_nicht_lieferbar_zaehlt_wieder(tmp_path, abgerufen_am):
    """Wieder mit Preis gelesen (abgerufen am oder nach `nicht_lieferbar_am`): zählt.
    Im selben Aufruf zählt das ältere Bündel derselben Stufe nicht (positive
    Wirkung)."""
    zurueck = _roh(_buendel(ULTRA, 512, abgerufen_am=abgerufen_am), **{FELD: HEUTE})
    alt = _roh(_buendel(ULTRA, 512, O2, "o2-unlimited-m"), **{FELD: HEUTE})
    gelesen = _lies([zurueck, alt], tmp_path)
    assert not geraete_notbremse.felder_aus_satz(gelesen[alt["id"]], HEUTE)["zaehlt"], (
        "nicht lieferbare Stufe zählt weiter: altes Bündel vom 12.11."
    )
    assert geraete_notbremse.felder_aus_satz(gelesen[zurueck["id"]], HEUTE)["zaehlt"], (
        f"wieder gelesenes Bündel (abgerufen {abgerufen_am}) zählt nicht"
    )


@pytest.mark.parametrize(
    "wert",
    ["unbekannt", "", None, 20261113, ["2026-11-13"]],
    ids=["text", "leer", "none", "zahl", "liste"],
)
def test_unlesbares_nicht_lieferbar_am_nimmt_keine_zahl_und_wirft_nicht(tmp_path, wert):
    """Ein Feld ohne Datum zählt wie kein Feld; ein lesbares im selben Aufruf wirkt."""
    unlesbar = _roh(_buendel(ULTRA, 512), **{FELD: wert})
    lesbar = _roh(_buendel(ULTRA, 512, O2, "o2-unlimited-m"), **{FELD: HEUTE})
    gelesen = _lies([unlesbar, lesbar], tmp_path)
    assert not geraete_notbremse.felder_aus_satz(gelesen[lesbar["id"]], HEUTE)[
        "zaehlt"
    ], "nicht lieferbare Stufe zählt weiter: lesbares Feld ohne Wirkung"
    assert geraete_notbremse.felder_aus_satz(gelesen[unlesbar["id"]], HEUTE)[
        "zaehlt"
    ], f"unlesbares {FELD}={wert!r} nimmt dem Bündel die Zahl"
