"""Der Reiter "Was kostet es": `report/geraete_tco_view.py`.

WAS DIESE TESTS FESTHALTEN
---------------------------
Diese Tafel rechnet selbst nichts - sie ruft `tco_model.tco_24()` und
`tco_model.geraeteanteil()` auf und FORMT das Ergebnis. Der ganze Sinn des
Reiters ist eine einzige Unterscheidung: `Tco.gesamt` ist auch dann eine
Zahl, wenn kein Tarifpreis bekannt ist (dann ist es der Geraetebetrag) -
die Tafel zeigt `gesamt`/`monatlich` aber NUR bei `Tco.belastbar`. Jeder
Test hier prueft genau EINE Zusicherung des Moduls.

Die Zahlen stammen, wie in `test_tco_model.py`, aus dem o2-Rechenbeispiel
vom 03.09.2026 (1 EUR Anzahlung, 24 x 30 EUR Rate = 721 EUR).

KEIN NETZ, KEINE UHR, KEIN gemeinsamer Zustand zwischen den Tests.
"""
from telco_radar.geraete_model import Geraet, Katalog, VERGLEICHBARE_ZUSTAENDE
from telco_radar.report.geraete_tco_view import (REFERENZEN_SICHTBAR,
                                                aufbereiten, leer)
from telco_radar.tco_model import (POSTEN_ANSCHLUSS, POSTEN_RABATTE,
                                   POSTEN_TARIF, TCO_HORIZONT, Buendel,
                                   SimOnlyReferenz, geraeteanteil, tco_24)

# Das Rechenbeispiel des Auftrags: 1 EUR + 24 x 30 EUR = 721 EUR.
_ANZAHLUNG, _RATE = 1.0, 30.0
_SKU = "apple-iphone-14-128gb-mitternacht"


def _buendel(**kw) -> Buendel:
    """Ein vollstaendiges Buendel; jeder Test aendert nur, was er misst."""
    felder = dict(sku_id=_SKU, anbieter="o2", tarif_name="o2 Mobile M",
                  tarif_monatlich=29.99, geraet_zuzahlung=_ANZAHLUNG,
                  geraet_monatsrate=_RATE, laufzeit_monate=24,
                  anschlusspreis=39.99,
                  quelle_url="https://www.o2online.de/tarife/mobile-m",
                  abgerufen_am="2026-09-03")
    felder.update(kw)
    return Buendel(**felder)


def _referenz(**kw) -> SimOnlyReferenz:
    felder = dict(anbieter="o2", tarif_name="o2 Mobile M",
                  tarif_sim_only_monatlich=19.99, anschlusspreis=39.99,
                  quelle_url="https://www.o2online.de/tarife/mobile-m-sim",
                  abgerufen_am="2026-09-03")
    felder.update(kw)
    return SimOnlyReferenz(**felder)


# --------------------------------------------------------------------------
# 1/2/3: die Zahl, ihre Bestandteile - und wann es keine Zahl geben darf
# --------------------------------------------------------------------------

def test_ohne_tarifpreis_zeigt_die_zeile_keine_zahl_obwohl_tco_24_eine_liefert():
    """`tco_24` liefert fuer ein Buendel ohne Tarifgrundpreis sehr wohl ein
    `gesamt` (den Geraetebetrag) - Regel 2 des Modulkopfs verlangt, dass die
    Tafel es trotzdem NICHT zeigt. Ohne die erste Zusicherung wuerde dieser
    Test nichts pruefen, deshalb steht sie hier explizit."""
    b = _buendel(tarif_monatlich=None)
    roh = tco_24(b)
    assert roh.gesamt is not None, \
        "sonst beweist der Test nur, dass es keine Zahl gab"
    assert roh.belastbar is False

    ergebnis = aufbereiten([b], [], [], katalog=None)
    zeile = ergebnis["zeilen"][0]
    assert zeile["belastbar"] is False
    assert zeile["gesamt"] is None
    assert zeile["monatlich"] is None


def test_ein_vollstaendiges_buendel_ergibt_leitzahl_und_monatsbetrag():
    b = _buendel()
    roh = tco_24(b)
    assert roh.belastbar is True, "sonst prueft der Test den falschen Fall"

    ergebnis = aufbereiten([b], [], [], katalog=None)
    zeile = ergebnis["zeilen"][0]
    assert zeile["belastbar"] is True
    # Die View rechnet nicht selbst nach - dieselbe Zahl wie `tco_24`.
    assert zeile["gesamt"] == roh.gesamt == 1480.75
    assert zeile["monatlich"] == roh.monatlich == 61.7


def test_die_bestandteile_bleiben_sichtbar_auch_ohne_belastbare_zeile():
    """Was gemessen ist, bleibt sichtbar - es ergibt nur keine Kennzahl."""
    b = _buendel(tarif_monatlich=None)
    zeile = aufbereiten([b], [], [], katalog=None)["zeilen"][0]
    assert zeile["belastbar"] is False

    namen = {p["name"] for p in zeile["bestandteile"]}
    assert namen, "sonst gaebe es nichts zu pruefen"
    assert "Gerätezuzahlung" in namen
    assert any(n.startswith("Geräteraten") for n in namen)
    assert "Anschlusspreis" in namen


def test_jede_luecke_traegt_ihre_phase():
    b = _buendel(tarif_monatlich=None, anschlusspreis=None)
    zeile = aufbereiten([b], [], [], katalog=None)["zeilen"][0]
    assert zeile["luecken"], "sonst wird nichts geprueft"
    for eintrag in zeile["luecken"]:
        assert (eintrag["phase"] or "").strip() != ""


# --------------------------------------------------------------------------
# 5: Restbetrag jenseits des Horizonts
# --------------------------------------------------------------------------

def test_der_restbetrag_steht_nur_jenseits_des_horizonts():
    lang = aufbereiten([_buendel(laufzeit_monate=36)], [], [], katalog=None)
    assert lang["zeilen"][0]["restbetrag"] == 360.0, "12 offene Raten a 30 EUR"

    # 0.0 UND NICHT None: die Raten laufen genau ueber den Horizont, es ist
    # nichts offen - das ist eine Messung. None hiesse "nicht gemessen", und
    # die zwei auseinanderzuhalten ist die Grundregel dieses Zweigs
    # (`tco_model`: "0.0 ist ein GEMESSENER Betrag und keine Luecke").
    kurz = aufbereiten([_buendel(laufzeit_monate=24)], [], [], katalog=None)
    assert kurz["zeilen"][0]["restbetrag"] == 0.0


def test_ohne_gemessene_rate_ist_der_restbetrag_eine_luecke():
    """Die Gegenprobe zum Test darueber: KEINE Rate gemessen heisst None.

    Ohne diesen Fall koennte `restbetrag` dauerhaft 0.0 liefern und der Test
    darueber bliebe gruen - er pruefte dann nur noch, dass eine Konstante
    eine Konstante ist."""
    ohne = aufbereiten([_buendel(geraet_monatsrate=None)], [], [],
                       katalog=None)
    assert ohne["zeilen"][0]["restbetrag"] is None


# --------------------------------------------------------------------------
# 6: das Euro-Delta - nur wenn BEIDE Seiten belastbar sind
# --------------------------------------------------------------------------

def test_delta_mit_zwei_belastbaren_seiten_traegt_die_richtige_differenz():
    vf = _buendel(anbieter="Vodafone", tarif_name="Vodafone Red M",
                  tarif_monatlich=34.99)
    fremd = _buendel(anbieter="o2", tarif_name="o2 Mobile M")
    roh_vf, roh_fremd = tco_24(vf), tco_24(fremd)
    assert roh_vf.belastbar and roh_fremd.belastbar, \
        "sonst prueft der Test den falschen Fall"

    delta = aufbereiten([vf, fremd], [], [], katalog=None)["delta"]
    assert len(delta) == 1
    eintrag = delta[0]
    erwartete_differenz = round(roh_fremd.gesamt - roh_vf.gesamt, 2)
    assert eintrag["differenz"] == erwartete_differenz
    assert eintrag["guenstiger"] == (erwartete_differenz < 0)


def test_delta_bleibt_leer_wenn_die_vodafone_seite_nicht_belastbar_ist():
    vf = _buendel(anbieter="Vodafone", tarif_monatlich=None)
    fremd = _buendel(anbieter="o2")
    ergebnis = aufbereiten([vf, fremd], [], [], katalog=None)
    assert ergebnis["delta"] == []


def test_delta_bleibt_leer_ohne_ein_vodafone_buendel():
    ergebnis = aufbereiten([_buendel(anbieter="o2")], [], [], katalog=None)
    assert ergebnis["delta"] == []


def test_delta_bleibt_leer_bei_verschiedener_sku_id():
    vf = _buendel(anbieter="Vodafone", sku_id="apple-iphone-16-128gb-schwarz")
    fremd = _buendel(anbieter="o2", sku_id=_SKU)
    ergebnis = aufbereiten([vf, fremd], [], [], katalog=None)
    assert ergebnis["delta"] == []


# --------------------------------------------------------------------------
# 7: der Geraeteanteil braucht die passende SIM-only-Referenz
# --------------------------------------------------------------------------

def test_der_geraeteanteil_steht_mit_passender_referenz():
    b, ref = _buendel(), _referenz()
    erwartet = geraeteanteil(b, ref)
    assert erwartet.belastbar is True, "sonst prueft der Test den falschen Fall"

    zeile = aufbereiten([b], [ref], [], katalog=None)["zeilen"][0]
    assert zeile["geraeteanteil"] == erwartet.betrag


def test_der_geraeteanteil_bleibt_leer_ohne_passende_referenz():
    zeile = aufbereiten([_buendel()], [], [], katalog=None)["zeilen"][0]
    assert zeile["geraeteanteil"] is None


# --------------------------------------------------------------------------
# 8/9: vom Speicher zum Datensatz
# --------------------------------------------------------------------------

def test_ein_store_woerterbuch_mit_betriebsfeldern_wird_gelesen():
    """Genau die Form, die `TcoDB.buendel()` liefert: ein dict MIT `id`,
    `first_seen`, `last_verified` - Felder, die keine Felder der
    Datenklasse sind. Dieser Test bricht, wenn jemand auf `Typ(**eintrag)`
    umstellt."""
    satz = {
        "id": "buendel--o2--apple-iphone-14-128gb-mitternacht--o2-mobile-m",
        "sku_id": _SKU, "anbieter": "o2", "tarif_name": "o2 Mobile M",
        "first_seen": "2026-09-01", "last_verified": "2026-09-03",
        "tarif_monatlich": 29.99, "geraet_zuzahlung": _ANZAHLUNG,
        "geraet_monatsrate": _RATE, "laufzeit_monate": 24,
        "anschlusspreis": 39.99,
        "quelle_url": "https://www.o2online.de/x",
        "abgerufen_am": "2026-09-03",
    }
    ergebnis = aufbereiten([satz], [], [], katalog=None)
    assert len(ergebnis["zeilen"]) == 1
    zeile = ergebnis["zeilen"][0]
    assert zeile["belastbar"] is True
    assert zeile["gesamt"] == tco_24(_buendel()).gesamt


def test_ein_kaputter_satz_kostet_keine_tafel():
    """Zwei Saetze rein, einer verletzt `Buendel.__post_init__` (kein
    Anbieter) - eine Zeile raus, der gueltige Nachbar bleibt stehen."""
    kaputt = {"sku_id": _SKU, "tarif_name": "o2 Mobile M",
              "tarif_monatlich": 29.99}
    gueltig = {"sku_id": "apple-iphone-16-128gb-schwarz", "anbieter": "o2",
               "tarif_name": "o2 Mobile M", "tarif_monatlich": 29.99}

    ergebnis = aufbereiten([kaputt, gueltig], [], [], katalog=None)
    assert len(ergebnis["zeilen"]) == 1
    assert ergebnis["zeilen"][0]["sku_id"] == "apple-iphone-16-128gb-schwarz"


# --------------------------------------------------------------------------
# 10: der Geraetename kommt aus dem KATALOG, nie aus der sku_id
# --------------------------------------------------------------------------

def test_der_geraetename_kommt_aus_dem_katalog_nicht_aus_der_sku_id():
    """`apple-iphone-16-128gb-space-grau` traegt eine Farbe MIT Bindestrich -
    ein `sku_id.rsplit("-", 2)` schnitte an der falschen Stelle und faende
    den Katalogeintrag nicht."""
    sku = "apple-iphone-16-128gb-space-grau"
    katalog = Katalog([Geraet(hersteller="Apple", modell="iPhone 16")])
    listung = {"sku_id": sku, "device_id": "apple-iphone-16",
              "speicher_gb": 128}

    zeile = aufbereiten([_buendel(sku_id=sku)], [], [listung],
                        katalog=katalog)["zeilen"][0]
    assert zeile["geraet"] == "iPhone 16 128 GB"


# --------------------------------------------------------------------------
# 11/12: die Bereitschaftstabelle - eine Auskunft ueber die Daten
# --------------------------------------------------------------------------

def test_die_bereitschaft_zaehlt_nur_neugeraete():
    """`VERGLEICHBARE_ZUSTAENDE` schliesst refurbished aus - der Gegentest
    mit `zustand='neu'` zeigt, dass derselbe Satz sonst sehr wohl zaehlt."""
    assert "refurbished" not in VERGLEICHBARE_ZUSTAENDE

    refurb = {"anbieter": "o2", "zustand": "refurbished",
             "preis_ohne_vertrag": 500.0}
    ohne_neugeraet = aufbereiten([], [], [refurb], katalog=None)
    assert ohne_neugeraet["bereitschaft"] == []

    neu = {"anbieter": "o2", "zustand": "neu", "preis_ohne_vertrag": 500.0}
    mit_neugeraet = aufbereiten([], [], [neu], katalog=None)
    assert len(mit_neugeraet["bereitschaft"]) == 1
    assert mit_neugeraet["bereitschaft"][0]["listungen"] == 1


def test_die_ratenprobe_wird_gezaehlt_nicht_geraten():
    passt = {"anbieter": "o2", "zustand": "neu", "anzahlung": _ANZAHLUNG,
             "monatsrate": _RATE, "laufzeit_monate": 24,
             "preis_ohne_vertrag": 721.0}
    satz = aufbereiten([], [], [passt], katalog=None)["bereitschaft"][0]
    assert satz["mit_raten"] == 1
    assert satz["raten_probe_ok"] == 1

    passt_nicht = {"anbieter": "o2", "zustand": "neu",
                   "anzahlung": _ANZAHLUNG, "monatsrate": _RATE,
                   "laufzeit_monate": 24, "preis_ohne_vertrag": 999.0}
    satz2 = aufbereiten([], [], [passt_nicht], katalog=None)["bereitschaft"][0]
    assert satz2["mit_raten"] == 1, "die Ratenzahlung selbst bleibt gezaehlt"
    assert satz2["raten_probe_ok"] == 0, "die Probe geht bei 999 EUR nicht auf"


# --------------------------------------------------------------------------
# 13: der Notzustand traegt jedes Feld, das die Vorlage liest
# --------------------------------------------------------------------------

def test_leer_traegt_jedes_feld_das_aufbereiten_traegt():
    voll = aufbereiten([], [], [], katalog=None)
    assert set(leer().keys()) == set(voll.keys())


# --------------------------------------------------------------------------
# 14: Das Banner belegt beide Seiten
# --------------------------------------------------------------------------

def test_das_delta_traegt_beide_quelllinks():
    """Eine gemeldete Zeile steht nicht zwingend in der Tabelle darunter.

    `_delta` rechnet ueber ALLE Buendel, die Tabelle ist auf `SICHTBAR_MAX`
    gedeckelt. Ohne die zwei Links waere der Deckel eine stille
    Beleglosigkeit - und dieses Portal belegt jede Aussage.
    """
    fremd = _buendel(anbieter="o2", tarif_name="o2 M",
                     quelle_url="https://o2.example/geraet")
    eigen = _buendel(anbieter="Vodafone", tarif_name="GigaMobil M",
                     tarif_monatlich=39.99,
                     quelle_url="https://vodafone.example/geraet")
    d = aufbereiten([fremd, eigen], [], [], katalog=None)

    assert len(d["delta"]) == 1, d["delta"]
    treffer = d["delta"][0]
    assert treffer["quelle_url"] == "https://o2.example/geraet"
    assert treffer["eigen_quelle_url"] == "https://vodafone.example/geraet"


# --------------------------------------------------------------------------
# 15: "Was noch fehlt" wird gerechnet, nicht hingeschrieben
# --------------------------------------------------------------------------

def test_ein_gemessener_posten_steht_nicht_mehr_unter_was_noch_fehlt():
    """Sonst zeigt die Tabelle einen Tarifgrundpreis und der Abschnitt
    darunter behauptet, er fehle - sichtbar falsch, sobald Phase 6 liefert.

    Die Gegenprobe steht im selben Test: OHNE Tarifgrundpreis erscheint er
    sehr wohl. Ohne sie pruefte der Test nur, dass eine leere Menge leer ist.
    """
    voll = aufbereiten([_buendel()], [], [], katalog=None)
    namen = [o["name"] for o in voll["offene_posten"]]
    assert POSTEN_TARIF not in namen, namen
    assert POSTEN_ANSCHLUSS not in namen, namen
    assert POSTEN_RABATTE in namen, "Boni sind bei keinem Anbieter erfasst"

    ohne = aufbereiten([_buendel(tarif_monatlich=None)], [], [], katalog=None)
    assert POSTEN_TARIF in [o["name"] for o in ohne["offene_posten"]]


def test_ohne_buendel_stehen_die_posten_der_leeren_tafel():
    """Aus null Zeilen laesst sich keine Luecke rechnen - dann gilt die
    Liste dessen, was jedem kuenftigen Buendel fehlen wird."""
    leere = aufbereiten([], [], [], katalog=None)
    assert [o["name"] for o in leere["offene_posten"]] == [
        POSTEN_TARIF, POSTEN_ANSCHLUSS, POSTEN_RABATTE]


def test_die_reihenfolge_der_offenen_posten_ist_fest():
    """Eine je Lauf anders sortierte Liste erzeugt bei jedem Rendern einen
    Diff in `site/` - also einen Commit ohne Inhalt."""
    a = aufbereiten([_buendel(tarif_monatlich=None, anschlusspreis=None)],
                    [], [], katalog=None)["offene_posten"]
    b = aufbereiten([_buendel(anschlusspreis=None, tarif_monatlich=None)],
                    [], [], katalog=None)["offene_posten"]
    assert [x["name"] for x in a] == [x["name"] for x in b]


def test_bei_zwei_eigenen_buendeln_gilt_das_guenstigere():
    """Sonst entscheidet die Listenposition, welchen Preis wir gegen uns
    gelten lassen - und die Aussage des Banners haengt an der Reihenfolge
    im Speicher statt an den Zahlen.

    Der Fall wird gestellt: Vodafone fuehrt dasselbe Geraet zu zwei
    Tarifen. Der Test prueft im selben Lauf, dass BEIDE eigenen Zeilen in
    der Tafel stehen - sonst maesse er nur, dass eine davon fehlt.
    """
    teuer = _buendel(anbieter="Vodafone", tarif_name="GigaMobil L",
                     tarif_monatlich=49.99)
    billig = _buendel(anbieter="Vodafone", tarif_name="GigaMobil S",
                      tarif_monatlich=19.99)
    fremd = _buendel(anbieter="o2", tarif_name="o2 M", tarif_monatlich=29.99)

    d = aufbereiten([teuer, billig, fremd], [], [], katalog=None)
    eigene = [z for z in d["zeilen"] if z["eigen"]]
    assert len(eigene) == 2, "beide eigenen Buendel stehen in der Tafel"

    assert len(d["delta"]) == 1, d["delta"]
    # Der guenstigere Tarif: 24 x 19,99 statt 24 x 49,99.
    assert d["delta"][0]["eigen_tarif"] == "GigaMobil S", d["delta"][0]
    assert d["delta"][0]["eigen"] == min(z["gesamt"] for z in eigene)


# --------------------------------------------------------------------------
# Die Befunde des Reviews vom 04.09.2026
# --------------------------------------------------------------------------

def test_eine_listung_mit_raten_ohne_barpreis_kostet_nicht_die_seite():
    """B1. `preis_ohne_vertrag` ist ein EIGENES Optional-Feld.

    Eine Listung mit Ratenform ohne Barpreis ist moeglich - `geraete_store`
    schreibt jedes Preisfeld einzeln - und kommt mit Phase 4 (Zuzahlung mit
    Tarifreferenz statt Kassenpreis). `float(None)` haette hier geworfen,
    `render_site` waere auf `geraete_view.leer()` gefallen, und damit waeren
    ALLE fuenf Reiter leer und der Navigationseintrag "Geraete" von jeder
    Seite verschwunden.
    """
    ohne_barpreis = {"anbieter": "otelo", "zustand": "neu", "sku_id": "a-b-128gb",
                     "device_id": "a-b", "preis_ohne_vertrag": None,
                     "anzahlung": 1.0, "monatsrate": 30.0, "laufzeit_monate": 24}
    d = aufbereiten([], [], [ohne_barpreis], katalog=None)

    zeile = [b for b in d["bereitschaft"] if b["anbieter"] == "otelo"]
    assert len(zeile) == 1, d["bereitschaft"]
    assert zeile[0]["mit_raten"] == 1, "die Ratenform ist erkannt"
    assert zeile[0]["raten_probe_ok"] == 0, (
        "ohne Barpreis gibt es nichts, wogegen die Probe geht")


def test_das_delta_verlangt_mehr_als_belastbar():
    """B2. `Tco.belastbar` verlangt nur den Tarifgrundpreis.

    Eine Zeile ohne gemessene Geraeterate ist damit "belastbar" - und ihre
    Differenz zu einer vollstaendigen Zeile ist der fehlende Geraetepreis,
    kein Preisvorteil. Das Banner haette "760,99 € günstiger als Vodafone"
    geschrieben, weil o2s Geraetepreis nicht gemessen ist.

    Die Gegenprobe steht im selben Test: MIT Rate entsteht das Delta.
    """
    eigen = _buendel(anbieter="Vodafone", tarif_name="GigaMobil M")
    luecke = _buendel(anbieter="o2", tarif_name="o2 M",
                      geraet_zuzahlung=None, geraet_monatsrate=None)
    assert tco_24(luecke).belastbar, "die Zeile gilt sehr wohl als belastbar"

    d = aufbereiten([eigen, luecke], [], [], katalog=None)
    assert d["delta"] == [], (
        "eine Zeile ohne Geraetepreis traegt kein Vorzeichen")

    voll = _buendel(anbieter="o2", tarif_name="o2 M", tarif_monatlich=9.99)
    assert aufbereiten([eigen, voll], [], [], katalog=None)["delta"], (
        "mit vollstaendiger Gegenseite entsteht das Delta sehr wohl")


def test_ein_unwesentlicher_abstand_wird_nicht_gemeldet():
    """B4. Sonst schreibt das lauteste Element des Reiters "0,00 € teurer".

    Dieselbe Schwelle wie in `geraete_vergleich` (3 % ODER 15 €) und aus
    demselben Grund. Die Gegenprobe: ein wesentlicher Abstand wird gemeldet.
    """
    eigen = _buendel(anbieter="Vodafone", tarif_name="GigaMobil M")
    gleich = _buendel(anbieter="o2", tarif_name="o2 M")
    assert aufbereiten([eigen, gleich], [], [], katalog=None)["delta"] == [], (
        "zwei gleich teure Buendel sind keine Meldung")

    deutlich = _buendel(anbieter="o2", tarif_name="o2 M", tarif_monatlich=9.99)
    assert aufbereiten([eigen, deutlich], [], [], katalog=None)["delta"]


def test_eine_unlesbare_datei_ist_nicht_leer():
    """B6. `TcoDB` unterscheidet die zwei ausdruecklich - dieses Modul
    reichte den Zustand aber nicht durch, und die Tafel meldete bei kaputter
    Datei "es fehlen die Tarifpreise"."""
    assert aufbereiten([], [], [], katalog=None)["lesbar"] is True
    assert aufbereiten([], [], [], katalog=None, lesbar=False)["lesbar"] is False


def test_eine_sim_only_referenz_aus_dem_speicher_wird_gelesen():
    """Der Weg Store-dict -> `SimOnlyReferenz`, mit den Betriebsfeldern.

    Fuer `Buendel` gibt es diesen Test schon. Ohne ihn hier liesse ein
    Feldnamen-Tippfehler in `_REFERENZ_FELDER` JEDE Referenz stumm wegfallen:
    `geraeteanteil` waere dauerhaft `None`, und kein Test schluege an.
    """
    b = _buendel(anbieter="o2", tarif_name="o2 M")
    referenz = {"id": "simonly--o2--o2-m", "anbieter": "o2",
                "tarif_name": "o2 M", "tarif_sim_only_monatlich": 19.99,
                "anschlusspreis": 39.99, "quelle_url": "https://o2.example/s",
                "abgerufen_am": "2026-09-03",
                "first_seen": "2026-09-01", "last_verified": "2026-09-03"}
    d = aufbereiten([b], [referenz], [], katalog=None)
    assert d["zeilen"][0]["geraeteanteil"] is not None, (
        "die Referenz ist angekommen und der Geraeteanteil gerechnet")


def test_ein_buendel_ohne_listung_heisst_nicht_fragezeichen():
    """Ein Buendel, dessen SKU in keiner Listung mehr steht, bekam "?" als
    Namen - im Banner wie in der Tabelle. Die SKU benennt das Geraet
    wenigstens."""
    d = aufbereiten([_buendel(sku_id="apple-iphone-99-256gb-blau")], [], [],
                    katalog=None)
    assert d["zeilen"][0]["geraet"] == "apple-iphone-99-256gb-blau"


# --------------------------------------------------------------------------
# Der Massstab aus dem Tarifbestand (Phase 6)
# --------------------------------------------------------------------------

def _ref(anbieter="Telekom", tarif="MagentaMobil L", monatlich=59.95, **kw):
    felder = dict(anbieter=anbieter, tarif_name=tarif,
                  tarif_id="telekom:magentamobil-l", tarif_id_guete="hoch",
                  tarif_sim_only_monatlich=monatlich,
                  quelle_url="https://www.telekom.de/pib/x",
                  abgerufen_am="2026-09-04")
    felder.update(kw)
    return SimOnlyReferenz(**felder)


def test_die_tafel_zeigt_den_tarifpreis_auch_ohne_ein_einziges_buendel():
    """Der Zustand am 04.09.2026: 30 Tarifpreise, null Buendel.

    Die Tafel war bis dahin vollstaendig leer, und der Grund lag eine Ebene
    tiefer - es gab keine Tarifpreise. Jetzt gibt es sie, und der Massstab
    ist genau die Zahl, die auf keiner Werbeseite dieses Marktes steht.
    """
    d = aufbereiten([], [_ref()], [], None)
    assert d["zeilen"] == []
    assert d["referenzen_gesamt"] == 1
    zeile = d["referenzen"][0]
    assert zeile["monatlich"] == 59.95
    # Ueber den Horizont gerechnet - im MODUL, nicht in der Vorlage.
    assert zeile["ueber_horizont"] == round(59.95 * TCO_HORIZONT, 2)
    assert zeile["quelle_url"]


def test_der_tarifgrundpreis_ist_kein_offener_posten_mehr_wenn_er_dasteht():
    """Der Abschnitt "Was der Rechnung noch fehlt" wird GERECHNET.

    Als feste Liste haette er "Tarifgrundpreis fehlt, Phase 6" gemeldet,
    waehrend die Tabelle darunter dreissig Tarifgrundpreise zeigt -
    dieselbe Fehlerklasse, gegen die dieser Abschnitt am 04.09.2026
    ueberhaupt gerechnet statt hingeschrieben wurde.
    """
    ohne = {p["name"] for p in aufbereiten([], [], [], None)["offene_posten"]}
    mit = {p["name"] for p in
           aufbereiten([], [_ref()], [], None)["offene_posten"]}
    assert POSTEN_TARIF in ohne
    assert POSTEN_TARIF not in mit


def test_ein_belegter_anschlusspreis_schliesst_auch_diesen_posten():
    mit = {p["name"] for p in
           aufbereiten([], [_ref(anschlusspreis=39.99)], [], None)
           ["offene_posten"]}
    assert POSTEN_ANSCHLUSS not in mit
    # 0.0 ist ein gemessener Betrag und keine Luecke - dieselbe Regel wie
    # ueberall in diesem Zweig.
    null = {p["name"] for p in
            aufbereiten([], [_ref(anschlusspreis=0.0)], [], None)
            ["offene_posten"]}
    assert POSTEN_ANSCHLUSS not in null


def test_der_massstab_ist_gedeckelt_und_verliert_nichts():
    """Ein Deckel schneidet die Ansicht, nicht den Bestand.

    Die Seite steht unter einem Hoehenbudget je Reiter; was darueber
    hinausgeht, steht zugeklappt darunter und ist NICHT geloescht.
    """
    viele = [_ref(tarif=f"Tarif {i}", monatlich=10.0 + i) for i in range(30)]
    d = aufbereiten([], viele, [], None)
    assert len(d["referenzen"]) == REFERENZEN_SICHTBAR
    assert len(d["referenzen"]) + len(d["referenzen_rest"]) == 30
    assert d["referenzen_gesamt"] == 30


def test_der_eigene_anbieter_steht_oben():
    """Dieselbe Ordnung wie auf jeder anderen Tafel dieser Seite."""
    d = aufbereiten([], [_ref(anbieter="Telekom"),
                         _ref(anbieter="Vodafone", monatlich=99.0)], [], None)
    assert d["referenzen"][0]["anbieter"] == "Vodafone"
    assert d["referenzen"][0]["eigen"] is True


def test_eine_referenz_ohne_preis_steht_nicht_im_massstab():
    """Ein Massstab ohne Zahl ist keiner."""
    d = aufbereiten([], [_ref(tarif_sim_only_monatlich=None)], [], None)
    assert d["referenzen"] == []


def test_der_anschlusspreis_gilt_erst_als_erledigt_wenn_ihn_alle_tragen():
    """"Vereinigung, nicht Durchschnitt" - die Regel der Funktion.

    Mit `any` meldete die Seite den Anschlusspreis als erledigt, sobald
    EIN Tarif von fuenfundzwanzig ihn nennt. Ein Posten, den nur die
    Haelfte der Anbieter ausweist, ist eine offene Baustelle.
    """
    gemischt = aufbereiten([], [_ref(tarif="A", anschlusspreis=39.99),
                                _ref(tarif="B", anschlusspreis=None)],
                           [], None)
    assert POSTEN_ANSCHLUSS in {p["name"] for p in gemischt["offene_posten"]}
    alle = aufbereiten([], [_ref(tarif="A", anschlusspreis=39.99),
                            _ref(tarif="B", anschlusspreis=0.0)], [], None)
    assert POSTEN_ANSCHLUSS not in {p["name"] for p in alle["offene_posten"]}


def test_eine_referenz_ohne_betrag_macht_den_tarifpreis_nicht_erledigt():
    """Gerechnet wird gegen den MASSSTAB, nicht gegen die rohe Liste.

    Eine Referenz ohne Betrag faellt aus der Tabelle heraus. Gegen die rohe
    Liste gerechnet meldete die Seite oben "es fehlen die Tarifpreise" und
    unten "Tarifgrundpreis: erledigt" - genau der Selbstwiderspruch, gegen
    den dieser Abschnitt ueberhaupt gerechnet statt hingeschrieben wird.
    """
    d = aufbereiten([], [_ref(tarif_sim_only_monatlich=None)], [], None)
    assert d["referenzen"] == [] and d["referenzen_gesamt"] == 0
    assert POSTEN_TARIF in {p["name"] for p in d["offene_posten"]}
