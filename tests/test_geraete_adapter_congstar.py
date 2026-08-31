"""Der congstar-Adapter: Preis aus dem Next.js-Flight-Payload.

Eine Messrunde vom 31.08.2026 hat congstar als DEN EINEN Anbieter
identifiziert, der echte neue Marktinformation bringt: er liegt im
TELEKOM-NETZ (die Telekom selbst steht wegen ihrer AWS-WAF nicht in dieser
Datenbank) und trifft Apple, Samsung, Google UND Xiaomi - Google fehlte der
Fachabteilung bisher ganz.

JEDE FIXTURE IST EIN GESPEICHERTER ECHTER ABRUF vom 31.08.2026 (siehe
`tests/fixtures/geraete/_herkunft.json` fuer URL, Status und SHA-256) - kein
Bau-Subagent hat sie erfunden oder inhaltlich veraendert. Das ist die Lehre
vom 11.08.2026 (`claude/telco-radar` Handover §6): eine damals erfundene
Fixture wurde erst durch einen zweiten, adversarischen Pruefdurchgang
aufgedeckt.
"""
import gzip
from pathlib import Path

import pytest

from telco_radar.collect.geraete import GeraeteAbrufFehler, ernte_links, sammle_anbieter
from telco_radar.collect.geraete import congstar
from telco_radar.collect.geraete.robots import RobotsWaechter
from telco_radar.geraete_config import Anbieter, Einstieg, lade_farben, lade_katalog, lade_quellen
from telco_radar.geraete_model import lies_listung, zustand_aus_feldern

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_WURZEL = Path(__file__).parent.parent

# Die vier Produktseiten dieses Pakets, mit den vier Preisbeispielen aus dem
# Auftrag - `listed` ist der richtige Wert, `discounted` die Falle (siehe
# Modulkopf von congstar.py).
_PRODUKTE = {
    "congstar_produkt_iphone17.html.gz": {
        "url": "https://www.congstar.de/geraete/apple/apple-iphone-17/",
        "hersteller": "apple",
        # (Speicher, Farbe) -> (listed, discounted)
        "256": (919.0, 811),
    },
    "congstar_produkt_galaxy_s25.html.gz": {
        "url": "https://www.congstar.de/geraete/samsung/samsung-galaxy-s25/",
        "hersteller": "samsung",
        "128": (699.0, 519),
    },
    "congstar_produkt_pixel11.html.gz": {
        "url": "https://www.congstar.de/geraete/google/google-pixel-11/",
        "hersteller": "google",
        "256": (991.0, 757),
    },
    "congstar_produkt_redmi_note_17_pro.html.gz": {
        "url": "https://www.congstar.de/geraete/xiaomi/xiaomi-redmi-note-17-pro/",
        "hersteller": "xiaomi",
        "256": (477.0, 225),
    },
}


def _fixture(name: str) -> str:
    pfad = _FIX / name
    if name.endswith(".gz"):
        with gzip.open(pfad, "rt", encoding="utf-8") as fh:
            return fh.read()
    return pfad.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(_WURZEL)


@pytest.fixture(scope="module")
def farben():
    return lade_farben(_WURZEL)


# ==========================================================================
# Die Sitemap: nur echte, verlinkte Adressen (§ 87b UrhG)
# ==========================================================================

def test_sitemap_liefert_55_geraeteseiten():
    """Es wird ausschliesslich geerntet, was die Sitemap selbst nennt - keine
    hochgezaehlte ID. `ernte_links` ist die generische Funktion, congstar
    braucht dafuer keinen eigenen `ernte`."""
    urls = ernte_links(_fixture("congstar_sitemap_devices.xml"),
                       "https://www.congstar.de/sitemap/devices.xml",
                       pfadmuster="/geraete/", kind="sitemap")
    assert len(urls) == 55
    assert all(u.startswith("https://www.congstar.de/geraete/") for u in urls)
    for eintrag in _PRODUKTE.values():
        assert eintrag["url"] in urls, eintrag["url"]


# ==========================================================================
# Der Preis: `listed`, niemals `discounted`
# ==========================================================================

@pytest.mark.parametrize("dateiname", sorted(_PRODUKTE))
def test_congstar_liest_oneTime_listed_nicht_discounted(dateiname):
    """Die eine Regel, an der dieses Paket scheitern kann. Fuer jede der
    vier Belegdateien muss der gelesene Preis exakt `listed` treffen -
    `discounted` ist ein tarifgebundener Rabatt (Fussnote: "bei Abschluss
    der ANF M") und darf nie als Barpreis gespeichert werden."""
    angaben = _PRODUKTE[dateiname]
    saetze = congstar.lies(_fixture(dateiname), url=angaben["url"])
    assert saetze, f"{dateiname} liefert keine Rohsaetze"

    speicherwerte = {k: v for k, v in angaben.items() if k not in ("url", "hersteller")}

    # Die Rohdatei muss den `discounted`-Wert wirklich enthalten, sonst
    # prueft dieser Test nichts (Fixture ohne die Falle waere nutzlos).
    roh = _fixture(dateiname)
    for speicher, (listed, discounted) in speicherwerte.items():
        # Im Roh-HTML steht die JSON-Nutzlast escapt (\"discounted\":757).
        assert f'\\"discounted\\":{discounted}' in roh, (
            f"{dateiname}: die Fixture muss den discounted-Koeder fuer "
            f"{speicher} GB enthalten, sonst ist die Gegenprobe wirkungslos")

    for speicher, (listed, discounted) in speicherwerte.items():
        treffer = [s for s in saetze if s["speicher_gb"] == int(speicher)]
        assert treffer, f"{dateiname}: kein Rohsatz mit {speicher} GB"
        preise = {s["preis"] for s in treffer}
        assert preise == {listed}, (
            f"{dateiname} ({speicher} GB): erwartet {listed} (oneTime.listed), "
            f"bekommen {preise} - discounted waere {discounted}")
        assert discounted not in preise


def test_discounted_gegenprobe_faellt_bei_der_falschen_zahl_durch():
    """Explizite Gegenprobe ueber alle vier Belegdateien und beide Werte
    zusammen: dieser Test faellt durch, sobald `congstar._einmalpreis`
    `discounted` statt `listed` liefert."""
    erwartete_listed = set()
    verbotene_discounted = set()
    for dateiname, angaben in _PRODUKTE.items():
        for schluessel, wert in angaben.items():
            if schluessel in ("url", "hersteller"):
                continue
            listed, discounted = wert
            erwartete_listed.add(listed)
            verbotene_discounted.add(discounted)  # noqa: keep loop simple

    gefundene_preise = set()
    for dateiname, angaben in _PRODUKTE.items():
        for satz in congstar.lies(_fixture(dateiname), url=angaben["url"]):
            gefundene_preise.add(satz["preis"])

    assert erwartete_listed <= gefundene_preise
    assert not (verbotene_discounted & gefundene_preise), (
        "mindestens ein discounted-Wert steht unter den gelesenen Preisen - "
        "das ist die Falle aus dem Modulkopf")


# ==========================================================================
# Herstellerverteilung und Variantenzahl je Datei
# ==========================================================================

def test_variantenzahl_und_herstellerverteilung():
    """iPhone 17: 7 Varianten (5x 256GB, 2x 512GB); Galaxy S25: 5; Pixel 11:
    4; Redmi Note 17 Pro: 2 - macht 18 Rohsaetze ueber vier Hersteller."""
    erwartet = {
        "congstar_produkt_iphone17.html.gz": 7,
        "congstar_produkt_galaxy_s25.html.gz": 5,
        "congstar_produkt_pixel11.html.gz": 4,
        "congstar_produkt_redmi_note_17_pro.html.gz": 2,
    }
    gesamt = 0
    for dateiname, anzahl in erwartet.items():
        saetze = congstar.lies(_fixture(dateiname), url=_PRODUKTE[dateiname]["url"])
        assert len(saetze) == anzahl, f"{dateiname}: {len(saetze)} statt {anzahl}"
        gesamt += len(saetze)
    assert gesamt == 18


def test_alle_vier_hersteller_treffen_den_katalog(katalog, farben):
    """Google fehlte der Fachabteilung bisher ausdruecklich - dieser Test
    haelt fest, dass er jetzt getroffen wird, zusammen mit den drei anderen."""
    hersteller_ids = set()
    for dateiname, angaben in _PRODUKTE.items():
        for satz in congstar.lies(_fixture(dateiname), url=angaben["url"]):
            listung = lies_listung(
                titel=satz["titel"], anbieter="congstar", anbieter_typ="discount",
                netz="Telekom", quelle_url=satz["url"], abgerufen_am="2026-08-31",
                katalog=katalog, farben=farben,
                verfuegbarkeit=satz["verfuegbarkeit"],
                farbe_roh=satz["farbe"], ean=satz["ean"],
                speicher_gb=satz["speicher_gb"],
                zustand_hinweis=satz.get("zustand_hinweis", ""),
                preis_ohne_vertrag=satz["preis"])
            assert listung is not None, satz["titel"]
            hersteller_ids.add(listung.device_id.split("-")[0])
    assert hersteller_ids == {"apple", "samsung", "google", "xiaomi"}


# ==========================================================================
# Zustand: aus `condition` UND aus dem Titel, ueber zustand_aus_feldern
# ==========================================================================

def test_zustand_hinweis_traegt_das_rohe_condition_feld():
    """Der Adapter selbst schreibt keine zweite Zustandslogik - er reicht
    `condition` unveraendert als `zustand_hinweis` weiter."""
    saetze = congstar.lies(_fixture("congstar_produkt_iphone17.html.gz"),
                           url=_PRODUKTE["congstar_produkt_iphone17.html.gz"]["url"])
    assert all(s["zustand_hinweis"] == "NEW" for s in saetze)
    # Und zustand_aus_feldern() - dieselbe Funktion, die jeder andere
    # Adapter benutzt - liest daraus "neu".
    for s in saetze:
        assert zustand_aus_feldern(s["titel"], s["farbe"], s["zustand_hinweis"],
                                   s["url"]) == "neu"


def test_zustand_refurbished_wird_aus_dem_condition_feld_erkannt():
    """congstars `condition` ist der EINZIGE Traeger des Zustands - anders
    als bei o2 (29.08.2026), wo er in der Farbe stand. Diese Fixture hat
    keine Gebrauchtstrecke; der Fall wird deshalb durch eine Textersetzung
    an der REALEN Nutzlast erzeugt (nur `"condition":"NEW"` ->
    `"condition":"REFURBISHED"`, sonst kein Byte veraendert), um zu belegen,
    dass die Weiterleitung wirklich verdrahtet ist und nicht nur zufaellig
    "neu" ergibt."""
    roh = _fixture("congstar_produkt_iphone17.html.gz")
    assert '\\"condition\\":\\"NEW\\"' in roh, \
        "die Fixture muss condition=NEW im escapten JSON tragen"
    veraendert = roh.replace('\\"condition\\":\\"NEW\\"',
                             '\\"condition\\":\\"REFURBISHED\\"')
    saetze = congstar.lies(veraendert, url="https://www.congstar.de/geraete/apple/apple-iphone-17/")
    assert saetze and all(s["zustand_hinweis"] == "REFURBISHED" for s in saetze)
    for s in saetze:
        assert zustand_aus_feldern(s["titel"], s["farbe"], s["zustand_hinweis"],
                                   s["url"]) == "refurbished"


# ==========================================================================
# Die Geraete-ID kommt aus dem KATALOG, nie aus dem Titel (Teil E)
# ==========================================================================

def test_zwei_titelschreibweisen_ergeben_dieselbe_sku_id(katalog, farben):
    a = {"titel": "Google Pixel 11 256 GB frost", "preis": 991.0,
         "verfuegbarkeit": "lieferbar", "farbe": "frost", "speicher_gb": 256,
         "zustand_hinweis": "NEW",
         "url": "https://www.congstar.de/geraete/google/google-pixel-11/"}
    b = dict(a, titel="Google Pixel 11 5G, 256GB, Frost")

    def _listung(satz):
        return lies_listung(
            titel=satz["titel"], anbieter="congstar", anbieter_typ="discount",
            netz="Telekom", quelle_url=satz["url"], abgerufen_am="2026-08-31",
            katalog=katalog, farben=farben, verfuegbarkeit=satz["verfuegbarkeit"],
            farbe_roh=satz["farbe"], speicher_gb=satz["speicher_gb"],
            zustand_hinweis=satz["zustand_hinweis"], preis_ohne_vertrag=satz["preis"])

    la, lb = _listung(a), _listung(b)
    assert la is not None and lb is not None
    assert la.sku_id == lb.sku_id == "google-pixel-11-256gb-frost"


# ==========================================================================
# Quelllink: absolut, und die abgerufene Seite ist ihr eigener Beleg
# ==========================================================================

@pytest.mark.parametrize("dateiname", sorted(_PRODUKTE))
def test_quelllink_ist_die_absolut_abgerufene_menschenseite(dateiname):
    angaben = _PRODUKTE[dateiname]
    saetze = congstar.lies(_fixture(dateiname), url=angaben["url"])
    assert saetze
    for s in saetze:
        assert s["url"] == angaben["url"]
        assert s["url"].startswith("https://www.congstar.de/geraete/")


# ==========================================================================
# Verfuegbarkeit
# ==========================================================================

def test_verfuegbarkeit_wird_uebersetzt():
    """PRE_MARKETING (iPhone 17, mit Ankuendigung "wieder lieferbar in 5-6
    Wochen") -> nicht_lieferbar; IN_STOCK (die drei anderen) -> lieferbar."""
    iphone = congstar.lies(_fixture("congstar_produkt_iphone17.html.gz"),
                           url=_PRODUKTE["congstar_produkt_iphone17.html.gz"]["url"])
    assert all(s["verfuegbarkeit"] == "nicht_lieferbar" for s in iphone)

    pixel = congstar.lies(_fixture("congstar_produkt_pixel11.html.gz"),
                          url=_PRODUKTE["congstar_produkt_pixel11.html.gz"]["url"])
    assert all(s["verfuegbarkeit"] == "lieferbar" for s in pixel)


# ==========================================================================
# Ein gescheiterter Abruf ist nicht "nichts gefunden"
# ==========================================================================

def test_seite_ohne_next_f_nutzlast_wirft():
    with pytest.raises(GeraeteAbrufFehler):
        congstar.lies("<html><body>Wartungsseite</body></html>")


def test_next_f_nutzlast_ohne_variantenobjekte_wirft():
    kaputt = 'self.__next_f.push([1,"1:\\"$Sreact.fragment\\"\\n"])'
    with pytest.raises(GeraeteAbrufFehler):
        congstar.lies(kaputt)


# ==========================================================================
# Konfiguration: die Methode ist registriert und aktiv
# ==========================================================================

def test_congstar_ist_registriert_und_aktiv_in_der_konfiguration():
    from telco_radar.collect.geraete import ADAPTER
    assert "congstar_next" in ADAPTER
    assert ADAPTER["congstar_next"].lies is congstar.lies

    quellen = lade_quellen(_WURZEL)
    treffer = [a for a in quellen.anbieter if a.name == "congstar"]
    assert treffer, "config/geraete_quellen.yaml muss einen congstar-Eintrag tragen"
    anbieter = treffer[0]
    assert anbieter.methode == "congstar_next"
    assert anbieter.aktiv is True
    assert anbieter.crawlbar is True
    assert anbieter.netz == "Telekom"


# ==========================================================================
# Ende-zu-Ende: robots -> Sitemap -> vier Produktseiten -> Listungen
# ==========================================================================

def test_sammle_anbieter_ende_zu_ende(katalog, farben):
    """Robots-Pruefung, Sitemap-Ernte und Produktabruf im Zusammenspiel.

    Die Sitemap wird auf die vier belegten Adressen VERKUERZT - alle vier
    Zeilen sind woertlich aus der echten 55-Eintraege-Sitemap kopiert
    (`congstar_sitemap_devices.xml`), keine erfunden. Ohne diese Kuerzung
    braeuchte der Test 55 Produktseiten-Fixtures fuer Geraete, die nicht Teil
    dieses Auftrags sind.
    """
    echte_sitemap = _fixture("congstar_sitemap_devices.xml")
    for angaben in _PRODUKTE.values():
        assert f"<loc>{angaben['url']}</loc>" in echte_sitemap, angaben["url"]
    mini_sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset '
        'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
        "".join(f"<url><loc>{a['url']}</loc></url>\n" for a in _PRODUKTE.values()) +
        "</urlset>"
    )

    seiten = {angaben["url"]: dateiname for dateiname, angaben in _PRODUKTE.items()}

    def hole(url, kopfzeilen=None):
        if url.endswith("/robots.txt"):
            return (200, "User-agent: *\n")
        if url == "https://www.congstar.de/sitemap/devices.xml":
            return (200, mini_sitemap)
        if url in seiten:
            return (200, _fixture(seiten[url]))
        return (404, "")

    anbieter = Anbieter(
        name="congstar", typ="discount", netz="Telekom", methode="congstar_next",
        basis_url="https://www.congstar.de", rate_limit_sekunden=0,
        einstiege=[Einstieg(url="https://www.congstar.de/sitemap/devices.xml",
                            kind="sitemap", pfadmuster="/geraete/")])

    from datetime import datetime, timezone
    bilanz = sammle_anbieter(anbieter, katalog, farben, hole, "2026-08-31",
                             RobotsWaechter(hole=hole),
                             datetime(2026, 8, 31, 10, tzinfo=timezone.utc))

    assert bilanz.status == "ok", (bilanz.status, bilanz.grund)
    assert len(bilanz.listungen) == 18, len(bilanz.listungen)
    hersteller = {l.device_id.split("-")[0] for l in bilanz.listungen}
    assert hersteller == {"apple", "samsung", "google", "xiaomi"}
    # Kein einziger discounted-Wert unter den Bilanzpreisen.
    verbotene = {225, 519, 757, 811}
    assert not ({l.preis_ohne_vertrag for l in bilanz.listungen} & verbotene)
