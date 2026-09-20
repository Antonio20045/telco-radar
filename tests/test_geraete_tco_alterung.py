"""Paket A3 (STRATEGIE GERAETE V4, 20.09.2026): Alterung der Bündel.

Ein Angebot (Bündel), dessen `abgerufen_am` älter als `ALT_AB_TAGEN`
Tage ist, fällt aus „ab“-Preis, Delta und Ranking - die Zeile bleibt,
ausgegraut, mit Abrufdatum sichtbar (harte Regel 9: kein „nichts
gefunden“ vortäuschen).

AUFTRAG (Antonio, 20.09.2026): Die Grenze sind 3 Tage - „älter als
3 Tage fällt aus ab-Preis, Delta und Ranking; Tag-3-Grenzfall bleibt
drin“. Die Gegenrede aus der Datenlage bleibt dokumentiert: der
Telekom-Leser misst im 4-6-Tage-Rhythmus (termine 05./06./08./09./
15.09.2026), ElectronicPartner und Medimax im Wochenrhythmus
(06. -> 12. -> 19.09.) - ihre Bündel gelten damit regelmäßig als alt.
Das ist gewollt und der Antrieb für P1 (Telekom täglich): bis dahin
ist der ausgegraute Stand mit Datum die ehrliche Aussage. Dieselbe
Definition gilt für den „ab“-Preis des KATALOGS (Prüfer-Befund 2):
ein alter Barpreis stellt kein „ab“ von heute (gemessene Fälle:
mobilcom-debitel 37 Tage, Medimax 14 Tage gegen ein frisches
ElectronicPartner-Angebot).

Vergleichsbasis ist `abgerufen_am` JE BÜNDEL. Das Datum wird nie
geraten: fehlt es oder ist es unlesbar, ist der Wert „unbekannt“ und
fällt aus Vergleichen (Clean Code 4). Die EINE Frische-Definition
steht in `geraete_tco_karten.ist_frisch` - Auswahl und Anzeige lesen
sie (Clean Code 7), der Deckel ist eine benannte Konstante im Modul
und nie eine Zahl in der Vorlage (Clean Code 8).

Ohne `heute` (leerer String) altert nichts: Tests, die kein Datum
setzen, rechnen weiter wie bisher. Production rendert immer mit dem
Datum der Ausgabe (`render_site` gibt es an `aufbereiten` weiter).

Alle Fixtures setzen ihr Datum selbst (harte Regel 11). HEUTE ist der
20.09.2026; die Pflichtzahl rechnet Vodafone (frisch) gegen ein
BILLIGERES altes o2-Angebot:

    o2 (alt, 16.09.):  1,00 + 24 × 24,99 + 24 × 25,00  = 1.200,76 EUR
    Vodafone (frisch): 1,00 + 24 × 19,99 + 24 × 31,00  = 1.224,76 EUR
    Telekom (frisch):  1,00 + 24 × 29,99 + 24 × 25,00  = 1.320,76 EUR

Das alte Angebot DARF die Antwortzeile nicht mehr führen - genau
dafür ist dieser Fall gebaut (ein frischer Zweiter gegen einen alten
Ersten ist die interessante Richtung, nicht der umgekehrte).
"""
from __future__ import annotations

import pathlib

from telco_radar.geraete_config import lade_katalog
from telco_radar.report import geraete_tco_band
from telco_radar.report import geraete_tco_karten as karten
from telco_radar.report import geraete_tco_view, geraete_view
from telco_radar.report import geraete_zeitreihe
from telco_radar.report.html import _env
from telco_radar.tco_model import Buendel, SimOnlyReferenz

WURZEL = pathlib.Path(__file__).resolve().parents[1]

HEUTE = "2026-09-20"
TAG_3 = "2026-09-17"    # Grenzfall: 3 Tage alt -> noch frisch
TAG_4 = "2026-09-16"    # 4 Tage alt -> alt (jenseits der 3-Tage-Grenze)
SKU = "apple-iphone-17-pro-256gb-schwarz"
BAND_MITTEL = {"o2:l": "mittel", "vf:m": "mittel", "tk:m": "mittel"}

_KATALOG = None


def _katalog():
    global _KATALOG
    if _KATALOG is None:
        _KATALOG = lade_katalog(WURZEL)
    return _KATALOG


def _buendel(anbieter, tarif_id, tarif_name, monat, rate, tag):
    return Buendel(sku_id=SKU, anbieter=anbieter, tarif_name=tarif_name,
                   tarif_id=tarif_id, tarif_monatlich=monat,
                   geraet_zuzahlung=1.0, geraet_monatsrate=rate,
                   laufzeit_monate=24, anschlusspreis=0.0,
                   quelle_url=f"https://{anbieter.lower()}.invalid/x",
                   abgerufen_am=tag)


def _o2(tag=TAG_4):
    return _buendel("o2", "o2:l", "O2 Mobile L", 24.99, 25.0, tag)


def _vodafone(tag=HEUTE):
    return _buendel("Vodafone", "vf:m", "Vodafone Mobil M", 19.99, 31.0, tag)


def _telekom(tag="2026-09-19"):
    return _buendel("Telekom", "tk:m", "MagentaMobil M", 29.99, 25.0, tag)


def _listungen(tag=HEUTE):
    return [{"id": f"{a.lower()}--sku", "sku_id": SKU,
             "device_id": "apple-iphone-17-pro", "anbieter": a,
             "speicher_gb": 256, "zustand": "neu", "status": "aktiv",
             "preis_ohne_vertrag": None, "quelle_url": "",
             "abgerufen_am": tag}
            for a in ("o2", "Vodafone", "Telekom")]


def _standard(o2_tag=TAG_4, heute=HEUTE):
    """o2 alt, Vodafone und Telekom frisch - der Pflichtfall."""
    return karten.modelle([_o2(o2_tag), _vodafone(), _telekom()],
                          _listungen(), [], {}, _katalog(), heute=heute)


def _modell(ergebnis):
    assert len(ergebnis["modelle"]) == 1, "eine Zeile, ein Modell"
    return ergebnis["modelle"][0]


def _karte(modell, anbieter):
    treffer = [k for k in modell["karten"] if k["anbieter"] == anbieter
               and k.get("sku_id")]
    assert treffer, f"{anbieter} hat keine echte Karte"
    return treffer[0]


# --------------------------------------------------------------------------
# Die Grenze selbst
# --------------------------------------------------------------------------

def test_die_grenze_liegt_bei_drei_tagen():
    """TAG_3 ist frisch, TAG_4 ist alt - der Grenzfall des Auftrags.

    Auftrag (Antonio, 20.09.2026): „älter als 3 Tage fällt aus ab-Preis,
    Delta und Ranking; Tag-3-Grenzfall bleibt drin.“ Die Gegenrede aus
    der Datenlage bleibt hier dokumentiert: der Telekom-Leser misst im
    4-6-Tage-Rhythmus, ElectronicPartner/Medimax im Wochenrhythmus (je
    `termine` im Bestand) - sie gelten mit 3 Tagen regelmäßig als alt.
    Das ist der Antrieb für P1 (Telekom täglich), kein Grund für eine
    größere Grenze: bis dahin ist der ausgegraute Stand mit Datum die
    ehrliche Aussage.
    """
    assert karten.ALT_AB_TAGEN == 3
    assert karten.alter_in_tagen(TAG_3, HEUTE) == 3
    assert karten.alter_in_tagen(TAG_4, HEUTE) == 4
    assert karten.ist_frisch(TAG_3, HEUTE) is True
    assert karten.ist_frisch(TAG_4, HEUTE) is False
    # Gegenprobe: null Tage (heute abgerufen) ist frisch.
    assert karten.ist_frisch(HEUTE, HEUTE) is True


def test_fehlendes_oder_kaputtes_datum_ist_unbekannt():
    """Clean Code 4: ein fehlendes Datum wird nie geraten - es fällt aus
    Vergleichen heraus, sobald irgendwo eines gefordert ist."""
    assert karten.alter_in_tagen("", HEUTE) is None
    assert karten.alter_in_tagen("2026-13-99", HEUTE) is None
    assert karten.alter_in_tagen("kein-datum", HEUTE) is None
    assert karten.ist_frisch("", HEUTE) is False
    assert karten.ist_frisch("2026-13-99", HEUTE) is False


def test_ohne_heute_gibt_es_keine_alterung():
    """`heute=""` schaltet die Alterung aus - der Rückwärtskompatibilitäts-
    modus für jeden Aufruf, der kein Datum setzt (und für die alten
    Tests, harte Regel 11)."""
    modell = _modell(_standard(heute=""))
    o2 = _karte(modell, "o2")
    assert o2["frisch"] is True
    assert modell["antwort"]["tarif_anbieter"] == "o2"
    assert modell["antwort"]["tarif_gesamt"] == 1200.76
    assert o2["delta"]["betrag"] == -24.00
    assert modell["spanne"] == [1200.76, 1320.76]


# --------------------------------------------------------------------------
# Der Pflichtfall: alt fällt aus ab, Delta und Ranking, Zeile bleibt
# --------------------------------------------------------------------------

def test_altes_angebot_faellt_aus_ab_delta_und_ranking():
    """DIE PFLICHTZAHL: Vodafone frisch 1.224,76 EUR führt, obwohl das
    ALTE o2-Angebot mit 1.200,76 EUR billiger ist. Die o2-ZEILE bleibt
    stehen (frisch False, Datum sichtbar), aber ohne Delta und ohne
    Platz in der Rangfolge."""
    modell = _modell(_standard())
    o2 = _karte(modell, "o2")
    # Die Zeile bleibt - mit ihrem Datum und ihrer Marke.
    assert o2["belastbar"] and o2["gesamt"] == 1200.76
    assert o2["abgerufen_am"] == TAG_4
    assert o2["frisch"] is False
    assert o2["alt_marke"] == "kein aktueller Stand seit 16.09.2026"
    # ... aber ohne Delta und außerhalb jedes Rankings.
    assert o2["delta"] is None
    assert [k["anbieter"] for k in modell["karten"]] == \
        ["Vodafone", "Telekom", "o2", "1&1"]
    # Die Antwortzeile führt das frische Angebot.
    assert modell["antwort"]["tarif_anbieter"] == "Vodafone"
    assert modell["antwort"]["tarif_gesamt"] == 1224.76
    assert modell["spanne"] == [1224.76, 1320.76]
    assert modell["bundle_anbieter"] == ["Telekom", "Vodafone"]
    # Das Delta der frischen Wettbewerber rechnet weiter - gegen die
    # frische Referenz: 1.320,76 - 1.224,76 = 96,00.
    telekom = _karte(modell, "Telekom")
    assert telekom["frisch"] is True
    assert telekom["delta"]["betrag"] == 96.00
    # Und das Modell ist nicht "alles alt" - der Hinweis bleibt aus.
    assert modell["alles_alt"] is False
    assert modell["alt_hinweis"] == ""


def test_grenzfall_am_modell_drei_tage_bleibt_drin():
    """Noch einmal am ganzen Modell, was der Grenzfall oben an der
    Funktion prüft: 3 Tage alt führt noch - dieselbe Zahl wie ohne
    Alterung (der Tag-3-Grenzfall des Auftrags bleibt drin)."""
    modell = _modell(_standard(o2_tag=TAG_3))
    o2 = _karte(modell, "o2")
    assert o2["frisch"] is True
    assert modell["antwort"]["tarif_anbieter"] == "o2"
    assert modell["antwort"]["tarif_gesamt"] == 1200.76


def test_unbekanntes_datum_faellt_aus_dem_ranking():
    """Ein undatiertes Bündel ist kein frisches - es fällt wie ein altes
    aus der Bewertung, behält aber seine Zeile."""
    ergebnis = karten.modelle([_o2(""), _vodafone(), _telekom()],
                              _listungen(), [], {}, _katalog(), heute=HEUTE)
    modell = _modell(ergebnis)
    o2 = _karte(modell, "o2")
    assert o2["frisch"] is False
    assert o2["delta"] is None
    assert "unbekannt" in o2["alt_marke"]
    assert modell["antwort"]["tarif_anbieter"] == "Vodafone"


# --------------------------------------------------------------------------
# „alles alt“: sichtbar statt „nichts gefunden“
# --------------------------------------------------------------------------

def _alles_alt(o2=TAG_4, vodafone="2026-09-15", telekom=TAG_4):
    return karten.modelle([_o2(o2), _vodafone(vodafone), _telekom(telekom)],
                          _listungen(), [], {}, _katalog(), heute=HEUTE)


def test_alles_alt_nennt_den_letzten_stand_mit_datum():
    """Harte Regel 9: ein ganzes Modell ohne frisches Bündel zeigt den
    letzten Stand MIT Datum, statt „nichts gefunden“ vorzutäuschen."""
    modell = _modell(_alles_alt())
    assert modell["alles_alt"] is True
    # Der letzte Stand ist der späteste Abruf: 16.09.2026 (o2/Telekom),
    # Vodafone ist älter (15.09.) und darf den Satz nicht stellen.
    assert modell["alt_seit"] == TAG_4
    assert "Kein aktueller Bündel-Stand seit dem 16.09.2026" \
        in modell["alt_hinweis"]
    # Alles fällt aus der Bewertung - ohne Zeile zu verlieren.
    assert modell["antwort"]["tarif_gesamt"] is None
    assert modell["antwort"]["tarif_anbieter"] is None
    assert modell["spanne"] == []
    assert modell["bundle_anbieter"] == []
    assert modell["angebote"] == 3
    for anbieter in ("o2", "Vodafone", "Telekom"):
        karte = _karte(modell, anbieter)
        assert karte["frisch"] is False
        assert karte["gesamt"] is not None, f"{anbieter}: Zeile verloren"
        assert karte["delta"] is None
    # Die Marke an der ältesten Zeile nennt ihr Datum.
    assert _karte(modell, "o2")["alt_marke"] == \
        "kein aktueller Stand seit 16.09.2026"
    assert _karte(modell, "Vodafone")["alt_marke"] == \
        "kein aktueller Stand seit 15.09.2026"


def test_alles_alt_ohne_datum_nennt_unbekannt():
    """Clean Code 4 auch hier: ohne Datum heißt es „unbekannt“, nie
    heute."""
    modell = _modell(_alles_alt(o2="", vodafone="", telekom=""))
    assert modell["alles_alt"] is True
    assert modell["alt_seit"] == ""
    assert "unbekannt" in modell["alt_hinweis"]
    for anbieter in ("o2", "Vodafone", "Telekom"):
        assert "unbekannt" in _karte(modell, anbieter)["alt_marke"]


# --------------------------------------------------------------------------
# Band, Balken und Radar: dieselbe Auswahl
# --------------------------------------------------------------------------

def test_band_und_radar_rechnen_nur_mit_frischen_karten():
    """Clean Code 7 an der zweiten Auswahl: Balken-JSON und Radar lesen
    `alle_karten_je_band` - das alte o2-Angebot darf dort nicht als
    günstigste Karte des Bandes auftauchen."""
    modell = _modell(_standard())
    alle = geraete_tco_band.alle_karten_je_band(modell, BAND_MITTEL)
    assert sorted(alle["mittel"]) == ["Telekom", "Vodafone"]
    beste = geraete_tco_band.karten_je_band(modell, BAND_MITTEL)
    assert beste["mittel"]["Vodafone"]["gesamt"] == 1224.76
    # Gegenprobe: der günstigste Wert DES BANDES ist der frische - nicht
    # das alte 1.200,76-Angebot von o2.
    assert min(k["gesamt"] for ks in alle["mittel"].values()
               for k in ks) == 1224.76


def test_katalog_spalte_nennt_den_zustand_wenn_alles_alt_ist():
    """Der Gerätekatalog trägt die TCO-Spalte aus denselben Karten: ohne
    frisches Bündel heißt die Lücke „kein aktueller Bündel-Stand“, nicht
    „kein Bündel gemessen“ (das wäre gelogen - es gibt welche)."""
    alt = _modell(_alles_alt())
    spalte = geraete_view._tco_spalte(alt)
    assert spalte["tco_ab"] is None
    assert spalte["tco_leer"] == geraete_view.TCO_LEER_NUR_ALT
    assert spalte["tco_leer"] == "kein aktueller Bündel-Stand"
    # Gegenprobe am gemischten Modell: die Spalte nimmt das frische
    # Angebot (1.224,76), NICHT das billigere alte (1.200,76).
    gemischt = _modell(_standard())
    assert geraete_view._tco_spalte(gemischt)["tco_ab"] == 1224.76


def test_buendelzeilen_sortieren_alte_nach_hinten():
    """Die Bündel-Tabelle des Vergleichs-Reiters: frische Zeilen vor
    alten - die alte bleibt eine Zeile, ausgegraut, mit Datum."""
    buendel = [{"sku_id": SKU, "anbieter": "o2", "tarif_name": "O2 Mobile L",
                "tarif_id": "o2:l", "tarif_monatlich": 24.99,
                "geraet_zuzahlung": 1.0, "geraet_monatsrate": 25.0,
                "laufzeit_monate": 24, "anschlusspreis": 0.0,
                "quelle_url": "https://o2.invalid/x",
                "abgerufen_am": TAG_4},
               {"sku_id": SKU, "anbieter": "Vodafone",
                "tarif_name": "Vodafone Mobil M", "tarif_id": "vf:m",
                "tarif_monatlich": 19.99, "geraet_zuzahlung": 1.0,
                "geraet_monatsrate": 31.0, "laufzeit_monate": 24,
                "anschlusspreis": 0.0,
                "quelle_url": "https://vodafone.invalid/x",
                "abgerufen_am": HEUTE},
               {"sku_id": SKU, "anbieter": "Telekom",
                "tarif_name": "MagentaMobil M", "tarif_id": "tk:m",
                "tarif_monatlich": 29.99, "geraet_zuzahlung": 1.0,
                "geraet_monatsrate": 25.0, "laufzeit_monate": 24,
                "anschlusspreis": 0.0,
                "quelle_url": "https://telekom.invalid/x",
                "abgerufen_am": "2026-09-19"}]
    tarife = {tid: {"datenvolumen_gb": 30} for tid in BAND_MITTEL}
    ansicht = geraete_tco_view.aufbereiten(buendel, [], _listungen(),
                                           _katalog(), tarife=tarife,
                                           heute=HEUTE)
    modell = ansicht["modelle"][0]
    assert [k["anbieter"] for k in modell["zeilen_band"]] == \
        ["Vodafone", "Telekom", "o2"]
    o2 = next(k for k in modell["zeilen_band"] if k["anbieter"] == "o2")
    assert o2["frisch"] is False
    assert o2["gesamt"] == 1200.76


# --------------------------------------------------------------------------
# Die Zeitreihe: Band bleibt wählbar, Satz und Kachel sagen den Stand
# --------------------------------------------------------------------------

def _tco_dict(modell):
    for k in modell["karten"]:
        tid = (k.get("tarif_id") or "").strip()
        k["band"] = BAND_MITTEL.get(tid)
    return {"modelle": [modell],
            "baender_katalog": [{"key": "mittel", "label": "Mittel",
                                 "bereich": "21 bis 60 GB"}],
            "historie_lage": {"seit": "", "messtage": 0, "buendel": 0}}


def test_zeitreihe_band_mit_nur_alten_angeboten_bleibt_waehlbar(tmp_path):
    """Harte Regel 9 an der Navigation: ein Band, in dem nur alte
    Angebote stehen, bleibt wählbar - mit einem Satz, der den letzten
    Stand nennt, statt „führt kein Anbieter ein Bündel“ zu behaupten."""
    tco = _tco_dict(_modell(_alles_alt()))
    zr = geraete_zeitreihe.aufbereiten(tmp_path / "state", tco)
    mid = tco["modelle"][0]["id"]
    assert zr["daten"]["erlaubt"][mid] == ["mittel"]
    paar = next(p for p in zr["paare"] if p["modell"] == mid)
    assert "kein aktueller Stand" in paar["antwort_html"]
    assert "16.09.2026" in paar["antwort_html"]
    # Die Kachel zeigt keinen „ab“-Preis, sondern den alten Stand.
    kachel = zr["kacheln"][0]["baender"]["mittel"]
    assert kachel["ab"] is None
    assert kachel["alt_text"] == "kein aktueller Stand seit 16.09.2026"
    # Die Lücke nennt die drei Anbieter beim alten Stand; 1&1 und
    # congstar führen das Gerät gar nicht im Bündel (keine Karte).
    assert paar["luecke_text"] is not None
    assert "Kein aktueller Stand: Telekom, Vodafone, o2." \
        in paar["luecke_text"]
    assert "1&1, congstar führen das Gerät gar nicht im Bündel." \
        in paar["luecke_text"]


def test_zeitreihe_gemischtes_band_ignoriert_das_alte_angebot(tmp_path):
    """Gegenprobe: ein frisches Angebot im selben Band führt weiter -
    das alte taucht weder im Satz noch in der Kachel auf."""
    tco = _tco_dict(_modell(_standard()))
    zr = geraete_zeitreihe.aufbereiten(tmp_path / "state", tco)
    mid = tco["modelle"][0]["id"]
    paar = next(p for p in zr["paare"] if p["modell"] == mid)
    assert "führt Vodafone" in paar["antwort_html"]
    assert "1.224,76" in paar["antwort_html"]
    kachel = zr["kacheln"][0]["baender"]["mittel"]
    assert kachel["ab"] == "1.224,76 €"
    assert kachel.get("alt_text") is None
    assert "Kein aktueller Stand: o2." in (paar["luecke_text"] or "")


def test_band_zeilen_trennen_frisch_und_alt():
    """Die EINE Auswahl der Zeitreihe am Modul: `_band_zeilen` hält
    frische Zeilen und alte getrennt - alte verdrängen keine frischen,
    auch nicht beim selben Anbieter."""
    modell = _modell(_standard())
    for k in modell["karten"]:
        k["band"] = BAND_MITTEL.get((k.get("tarif_id") or "").strip())
    saetze = geraete_zeitreihe._band_zeilen(modell)
    satz = saetze["mittel"]
    assert [k["anbieter"] for k in satz["zeilen"]] == ["Vodafone", "Telekom"]
    assert [k["anbieter"] for k in satz["alt"]] == ["o2"]


# --------------------------------------------------------------------------
# Das Markup der Zeile
# --------------------------------------------------------------------------

def test_die_alte_zeile_traegt_marke_und_klasse():
    """Die Vorlage graut die alte Zeile aus und setzt die Marke mit
    Datum - gerendert am echten Makro (nicht am String-Attribut)."""
    modul = _env().get_template("_geraete_buendel.html.j2").make_module()
    alt = _karte(_modell(_standard()), "o2")
    html = modul.buendelzeile(alt)
    assert "gr-bnd--alt" in html
    assert "gr-kk-marke--alt" in html
    assert "kein aktueller Stand seit 16.09.2026" in html
    # Gegenprobe: die frische Zeile trägt keine der beiden.
    frisch = _karte(_modell(_standard()), "Vodafone")
    html = modul.buendelzeile(frisch)
    assert "gr-bnd--alt" not in html
    assert "gr-kk-marke--alt" not in html


def test_die_gruppe_nennt_den_alten_stand_ueber_den_zeilen():
    """„alles alt“ steht als EIN Satz über den Zeilen des Modells - die
    Regel sagt es am Modell, nicht an jeder Zeile einzeln."""
    modul = _env().get_template("_geraete_buendel.html.j2").make_module()
    modell = _modell(_alles_alt())
    modell["zeilen_band"] = [k for k in modell["karten"] if k.get("sku_id")]
    modell["zeilen_ohne_band"] = []
    modell["haendler_ohne_buendel"] = {}
    html = modul.buendelgruppe(modell)
    assert "Kein aktueller Bündel-Stand seit dem 16.09.2026" in html
    # Gegenprobe: das gemischte Modell nennt den Satz nicht.
    gemischt = _modell(_standard())
    gemischt["zeilen_band"] = [k for k in gemischt["karten"]
                               if k.get("sku_id")]
    gemischt["zeilen_ohne_band"] = []
    gemischt["haendler_ohne_buendel"] = {}
    assert "Kein aktueller Bündel-Stand" not in \
        modul.buendelgruppe(gemischt)


# ==========================================================================
# Die VERDRAHTUNG (Prüfer-Befund "hoch", 20.09.2026): Der Bezugstag darf
# nicht der Berichtstag sein. `render_site` gibt das Datum des jüngsten
# RADAR-Berichts als `heute` weiter (Mi/Fr) - aber die Geräteseite rendert
# TÄGLICH (`geraete.yml`, 03:10 UTC) und fasst die Berichte nicht an.
# Produktionsbeweis 20.09.: Bestand `updated=2026-09-20`, jüngster Bericht
# 16.09. - mit ihm als `heute` waren die Telekom-Bündel vom 15.09. "einen
# Tag alt" und führten frisch Antwortzeile und Spanne; die 3-Tage-Regel
# war regelmäßig (So-Mi) wirkungslos. Der Bezug ist deshalb der SPÄTERE
# der beiden Uhren (Berichtstag und `updated` des Bündel-Stores) - derselbe
# Gedanke wie `_auffaellig` ("Als Bezug gilt deshalb der spätere der
# beiden Tage"). Der Test geht durch `render_site`, weil der Fehler in der
# Verdrahtung saß, nicht in der Rechnung: html.py -> aufbereiten ->
# geraete_tco_view -> karten.
# ==========================================================================

REPORT_STAND = "2026-09-16"   # Mi/Fr-Radar: jüngster Bericht am 20.09.
BUENDEL_STAND = "2026-09-20"  # der tägliche Lauf schreibt sein eigenes Datum
# Der Telekom-Abruf muss vom STAND aus alt sein (5 Tage), vom BERICHTSTAG
# aus aber frisch (1 Tag) - nur so prüft der Fall, dass die spätere Uhr
# entscheidet. Der 15.09. ist der ECHTE Telekom-Messtag des Bestands.
TELEKOM_ABRUF = "2026-09-15"

_SKU = "apple-x-256gb-schwarz"


def _buendel_welt(tmp_path):
    """Bericht 16.09., Bündel-Stand 20.09., Telekom billig, aber alt.

    Die Pflichtzahl: Telekom (alt) 1,00 + 24 × 19,99 + 24 × 25,00 =
    1.080,76 EUR - BILLIGER als Vodafone (frisch) 1,00 + 24 × 29,99 +
    24 × 25,00 = 1.320,76 EUR. Unter der alten Verdrahtung (`heute` =
    Berichtstag) wäre Telekom nur 1 Tag alt und damit frisch (3-Tage-
    Grenze) - er würde Antwortzeile und Spanne führen, genau der
    gemeldete Folgeschaden.
    """
    import json

    import yaml

    from telco_radar.geraete_config import lade_katalog, lade_quellen
    root = tmp_path / "verdrahtung"
    (root / "config").mkdir(parents=True)
    (root / "config" / "geraete_katalog.yaml").write_text(
        yaml.safe_dump({"geraete": [
            {"hersteller": "Apple", "modell": "Apple X", "generation": 1,
             "speicher": [256], "segment": "flagship"}]},
            allow_unicode=True, sort_keys=False), encoding="utf-8")
    (root / "config" / "farben.yaml").write_text(
        yaml.safe_dump({"farben": {"schwarz": ["Schwarz"]}},
                       allow_unicode=True, sort_keys=False), encoding="utf-8")
    (root / "config" / "geraete_quellen.yaml").write_text(
        yaml.safe_dump({"anbieter": [
            {"name": "Telekom", "typ": "netzbetreiber", "rang": 1,
             "methode": "ldjson", "basis_url": "https://t.example",
             "einstiege": [{"url": "https://t.example/liste"}]},
            {"name": "Vodafone", "typ": "netzbetreiber", "rang": 2,
             "methode": "ldjson", "basis_url": "https://v.example",
             "einstiege": [{"url": "https://v.example/liste"}]}]},
            allow_unicode=True, sort_keys=False), encoding="utf-8")

    def _listung(anbieter, preis):
        return {"id": f"{anbieter.lower()}--{_SKU}", "sku_id": _SKU,
                "device_id": "apple-x", "anbieter": anbieter,
                "anbieter_typ": "netzbetreiber", "speicher_gb": 256,
                "farbe_roh": "Schwarz", "farbe_normalisiert": "schwarz",
                "zustand": "neu", "first_seen": "2026-09-01",
                "last_verified": BUENDEL_STAND, "status": "aktiv",
                "missed_checks": 0, "preis_ohne_vertrag": preis,
                "zuzahlung": None,
                "quelle_url": f"https://example.de/{_SKU}",
                "abgerufen_am": BUENDEL_STAND, "verfuegbarkeit": "lieferbar"}

    def _buendel(anbieter, tarif, tarif_monat, abgerufen):
        return {"id": f"buendel--{anbieter.lower()}--{_SKU}",
                "sku_id": _SKU, "anbieter": anbieter, "tarif_name": tarif,
                "tarif_id": f"{anbieter.lower()}:m", "tarif_id_guete": "hoch",
                "buendel_monatlich": None, "tarif_monatlich": tarif_monat,
                "geraet_zuzahlung": 1.0, "geraet_monatsrate": 25.0,
                "laufzeit_monate": 24, "anschlusspreis": 0.0,
                "zustand": "neu", "rabatte": [],
                "quelle_url": f"https://example.de/{_SKU}/buendel",
                "abgerufen_am": abgerufen,
                "first_seen": "2026-09-01", "last_verified": abgerufen}

    buendel = [_buendel("Telekom", "MagentaMobil M", 19.99, TELEKOM_ABRUF),
               _buendel("Vodafone", "Vodafone Mobil M", 29.99,
                        BUENDEL_STAND)]
    state = root / "data" / "state"
    state.mkdir(parents=True)
    (state / "geraete_db.json").write_text(json.dumps(
        {"updated": BUENDEL_STAND,
         "anbieter": {n: {"laeufe": 4} for n in ("Telekom", "Vodafone")},
         "listungen": [_listung("Telekom", 1199.0),
                       _listung("Vodafone", 1249.0)]}), encoding="utf-8")
    (state / "geraete_preise.jsonl").write_text("", encoding="utf-8")
    (state / "geraete_tco.json").write_text(json.dumps(
        {"updated": BUENDEL_STAND, "buendel": buendel, "sim_only": []}),
        encoding="utf-8")
    (state / "geraete_tco_historie.jsonl").write_text("", encoding="utf-8")
    (state / "tarife.jsonl").write_text(
        "\n".join(json.dumps(t) for t in (
            {"anbieter": b["anbieter"], "name": b["tarif_name"],
             "tarif_id": b["tarif_id"], "tarif_id_guete": "hoch",
             "grundgebuehr": b["tarif_monatlich"],
             "mindestlaufzeit_monate": 24, "rabattphasen": [],
             "quelle_url": b["quelle_url"], "abgerufen_am": BUENDEL_STAND}
            for b in buendel)) + "\n", encoding="utf-8")
    reports = root / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / f"{REPORT_STAND}.json").write_text(json.dumps(
        {"date": REPORT_STAND, "language": "de",
         "briefing_md": "## Auf einen Blick\n\n- Nichts.\n",
         "stats": {}, "regions": []}), encoding="utf-8")
    (reports / f"{REPORT_STAND}.md").write_text("# B\n", encoding="utf-8")
    # Derselbe `heute`, den `render_site` aus reports[0]["date"] durchreicht
    # (html.py) - der Test stellt die Uhr NICHT freundlicher als Produktion.
    g = geraete_view.aufbereiten(state, lade_quellen(root),
                                 lade_katalog(root), heute=REPORT_STAND)
    return root, g


def _weltsite(root):
    from telco_radar.report.html import render_site
    site = root / "site"
    render_site(site, root / "data" / "reports")
    return (site / "geraete.html").read_text(encoding="utf-8")


def test_spaeterer_tag_liest_nur_lesbare_uhren():
    """Die Bezugregel selbst: der spätere Tag gewinnt, ein unlesbarer
    zählt nicht (Clean Code 4) - er wird nie durch den anderen ersetzt
    und ersetzt nie selbst den anderen."""
    assert geraete_view._spaeterer_tag(REPORT_STAND, BUENDEL_STAND) \
        == BUENDEL_STAND
    # Gegenprobe: ein Bericht NEUER als der Stock (radar.yml läuft, der
    # nächtliche Lauf nicht) - dann altert der Stock ehrlich gegen den
    # Berichtstag.
    assert geraete_view._spaeterer_tag(BUENDEL_STAND, REPORT_STAND) \
        == BUENDEL_STAND
    assert geraete_view._spaeterer_tag(REPORT_STAND, "kaputt") == REPORT_STAND
    assert geraete_view._spaeterer_tag("", BUENDEL_STAND) == BUENDEL_STAND
    assert geraete_view._spaeterer_tag("", "") == ""


def test_berichtstag_allein_macht_kein_angebot_frisch(tmp_path):
    """DIE PFLICHTZAHL der Verdrahtung: Telekom ist mit 1.080,76 EUR am
    billigsten, aber vom 15.09. - fünf Tage vor dem Stand vom 20.09.
    (und nur einer vor dem Berichtstag). Der Berichtstag (16.09.) darf
    die 3-Tage-Regel nicht außer Kraft setzen: die Antwortzeile führt
    Vodafone (frisch, 1.320,76 EUR), Telekom bleibt Zeile mit Datum und
    ohne Delta."""
    _, g = _buendel_welt(tmp_path)
    modell = g["tco"]["modelle"][0]
    telekom = _karte(modell, "Telekom")
    assert telekom["gesamt"] == 1080.76
    assert telekom["frisch"] is False
    assert telekom["alt_marke"] == "kein aktueller Stand seit 15.09.2026"
    assert telekom["delta"] is None
    assert modell["antwort"]["tarif_anbieter"] == "Vodafone"
    assert modell["antwort"]["tarif_gesamt"] == 1320.76
    assert modell["spanne"] == [1320.76, 1320.76]
    assert modell["bundle_anbieter"] == ["Vodafone"]
    # Gegenprobe: das Modell ist NICHT "alles alt" - Vodafone ist frisch.
    assert modell["alles_alt"] is False


def test_render_site_traegt_die_marke_in_die_seite(tmp_path):
    """Harte Regel 10 an der VERDRAHTUNG: durch `render_site` gerendert,
    mit dem Bericht vom 16.09. im reports/-Ordner - so rendert geraete.yml
    täglich. Die Seite trägt die Alt-Marke des Telekom-Bündels, und der
    "alles alt"-Satz bleibt aus (Vodafone ist frisch), solange der
    Berichtstag allein nichts frisch stellen könnte."""
    root, _ = _buendel_welt(tmp_path)
    html = _weltsite(root)
    assert "kein aktueller Stand seit 15.09.2026" in html
    # Gegenprobe im selben Test: der "alles alt"-Satz der Gruppe steht
    # NICHT - die Marke kommt von der einzelnen Zeile, nicht vom
    # Notzustand des Modells.
    assert "Kein aktueller Bündel-Stand" not in html


def test_gleiche_uhren_altern_nicht_ueber_die_grenze(tmp_path):
    """Grenzfall durch die Verdrahtung: Berichtstag und Bündel-Stand
    fallen zusammen (radar.yml am Freitag nach dem nächtlichen Lauf).
    Ein am 17.09. abgerufenes Angebot ist dann 3 Tage alt - noch frisch
    und führt (derselbe Tag-3-Grenzfall wie oben); der Bezug darf nicht
    auf den älteren Berichtstag zurückfallen."""
    import json
    root, _ = _buendel_welt(tmp_path)
    # Beide Uhren auf den 20.09., Telekom auf den 17.09. - Tag 3.
    pfad = root / "data" / "state" / "geraete_tco.json"
    roh = json.loads(pfad.read_text(encoding="utf-8"))
    roh["buendel"][0]["abgerufen_am"] = "2026-09-17"
    pfad.write_text(json.dumps(roh), encoding="utf-8")
    reports = root / "data" / "reports"
    for alt in reports.iterdir():
        alt.unlink()
    (reports / "2026-09-20.json").write_text(json.dumps(
        {"date": "2026-09-20", "language": "de",
         "briefing_md": "## Auf einen Blick\n\n- Nichts.\n",
         "stats": {}, "regions": []}), encoding="utf-8")
    (reports / "2026-09-20.md").write_text("# B\n", encoding="utf-8")
    from telco_radar.geraete_config import lade_katalog, lade_quellen
    g = geraete_view.aufbereiten(root / "data" / "state", lade_quellen(root),
                                 lade_katalog(root), heute="2026-09-20")
    modell = g["tco"]["modelle"][0]
    telekom = _karte(modell, "Telekom")
    assert telekom["frisch"] is True
    assert modell["antwort"]["tarif_anbieter"] == "Telekom"
    assert modell["antwort"]["tarif_gesamt"] == 1080.76


# --------------------------------------------------------------------------
# Der Wettbewerbs-Radar: eine alte Karte ist Beleg, kein Paar
# --------------------------------------------------------------------------

def test_radar_zeigt_alte_karte_als_beleg_nicht_als_paar():
    """A3-Nachbesserung am Radar: `alle_karten_je_band` filtert frisch,
    aber der Band-Mismatch-Belegpfad (`uebrig` -> `_zeile_fuer_anbieter`)
    nicht - am echten Bestand vom 20.09. zeichnete der Radar so sieben
    Telekom-Paarzeilen aus fünf Tage alten Karten. Eine alte Karte trägt
    weiterhin Zeile, Preis und Beleg (Regel 9), aber weder Status
    „vergleichbar" noch Prozent (Vorgabe 1: aus jeder Bewertung)."""
    from telco_radar.report import geraete_radar as radar_modul
    karte = {"belastbar": True, "gesamt": 1080.76,
             "tarif": "MagentaMobil M", "tarif_id": "tk:m",
             "vergleichbar": True, "frisch": False,
             "alt_marke": "kein aktueller Stand seit 15.09.2026",
             "quelle_url": "https://t.invalid/x",
             "abgerufen_am": "2026-09-15"}
    basis = {"gesamt": 1320.76, "tarif": "Mobil M", "naeherung": False,
             "band": "mittel", "band_label": "Mittel (21 bis 60 GB)",
             "quelle_url": "", "abgerufen_am": "",
             "tarif_quelle_url": "", "tarif_abgerufen_am": ""}
    zeile = radar_modul._zeile_fuer_anbieter(
        "Telekom", karte, basis, {"tk:m": "mittel"})
    assert zeile["status"] == radar_modul.STATUS_NICHT_VERGLEICHBAR
    assert zeile["prozent"] is None
    assert zeile["grund"] == "kein aktueller Stand seit 15.09.2026"
    # Der Beleg bleibt: Quelle und Abrufdatum stehen weiter an der Zeile.
    assert zeile["quelle_url"] == "https://t.invalid/x"
    assert zeile["abgerufen_am"] == "2026-09-15"
    # Gegenprobe: dieselbe Karte frisch ist ein Paar MIT Prozent
    # (1.080,76 gegen 1.320,76 = -18,2 % - Telekom billiger).
    frisch = {**karte, "frisch": True, "alt_marke": ""}
    frisch_zeile = radar_modul._zeile_fuer_anbieter(
        "Telekom", frisch, basis, {"tk:m": "mittel"})
    assert frisch_zeile["status"] == radar_modul.STATUS_VERGLEICHBAR
    assert frisch_zeile["prozent"] == -18.2


# ==========================================================================
# Die NACHBESSERUNG "ab-Auswahl" (Prüfer-Befund "hoch", 20.09.2026):
# Dieselbe Frische-Definition (`ist_frisch`, Clean Code 7) gilt für den
# ab-Preis des KATALOGS. Gemessene Fälle der gerenderten Seite:
# "ab 1.299,00 EUR bei mobilcom-debitel, 14. August 2026" (37 Tage,
# status aktiv) und "ab 289,00 EUR bei Medimax, 6. September 2026"
# unterbot das frische ElectronicPartner-Angebot (299,00 EUR vom
# 19.09.). Ein alter Wert fällt aus "ab" und Spanne heraus - oder, wo
# es keinen frischen gibt, trägt die Marke (harte Regel 9).
# ==========================================================================

MEDIMAX_TAG = "2026-09-06"       # 14 Tage - der gemessene Fall
EP_TAG = "2026-09-19"            # 1 Tag - das frische Gegenstück
DEBITEL_TAG = "2026-08-14"       # 37 Tage - der gemessene Pixel-Fall


def _listung_mit_preis(anbieter, preis, tag, sku=SKU,
                       device="apple-iphone-17-pro", speicher=256):
    return {"id": f"{anbieter.lower()}--{sku}", "sku_id": sku,
            "device_id": device, "anbieter": anbieter,
            "speicher_gb": speicher, "zustand": "neu", "status": "aktiv",
            "preis_ohne_vertrag": preis,
            "quelle_url": f"https://{anbieter.lower()}.invalid/x",
            "abgerufen_am": tag}


def _katalogzeilen(listungen, heute=HEUTE):
    return geraete_view.katalog_modellzeilen(listungen, _katalog(),
                                             heute=heute)


def test_katalog_ab_nimmt_den_frischen_beleg_nicht_den_billigeren_alten():
    """DER gemessene Fall (Galaxy A37): Medimax 289 EUR vom 06.09. gegen
    ElectronicPartner 299 EUR vom 19.09. - "ab" führt das FRISCHE Angebot,
    und die Spanne rechnet ohne den alten Anbieter (seine Zeile bleibt im
    Aufklapper stehen, mit Datum)."""
    zeilen = _katalogzeilen([
        _listung_mit_preis("Medimax", 289.0, MEDIMAX_TAG),
        _listung_mit_preis("ElectronicPartner", 299.0, EP_TAG)])
    assert len(zeilen) == 1, "beide Listungen gehören zu EINEM Modell"
    zeile = zeilen[0]
    assert zeile["ab_preis"] == 299.0
    assert zeile["ab_anbieter"] == "ElectronicPartner"
    assert zeile["ab_alt"] is False
    assert zeile["ab_alt_marke"] == ""
    # Nur ein frischer Anbieter -> keine Spanne (keine zweite Zahl von
    # heute), obwohl zwei Händler das Gerät führen.
    assert zeile["spanne"] == []
    assert zeile["anbieterzahl"] == 2
    # Die alte Zeile bleibt im Aufklapper, mit ihrem Datum.
    assert sorted(z["anbieter"] for z in zeile["zeilen"]) == \
        ["ElectronicPartner", "Medimax"]


def test_katalog_ab_ohne_frischen_beleg_zeigt_den_letzten_stand():
    """DER gemessene Pixel-Fall: nur mobilcom-debitel, 37 Tage alt. Das
    "ab" bleibt sichtbar - als LETZTER STAND, ausgegraut, mit Marke und
    Datum - statt "kein Preis gemessen" vorzutäuschen (harte Regel 9).
    Die Leitzahl des Regals nimmt ihn nicht auf."""
    zeile = _katalogzeilen(
        [_listung_mit_preis("mobilcom-debitel", 1299.0, DEBITEL_TAG)])[0]
    assert zeile["ab_preis"] == 1299.0
    assert zeile["ab_anbieter"] == "mobilcom-debitel"
    assert zeile["ab_alt"] is True
    assert zeile["ab_alt_marke"] == "kein aktueller Stand seit 14.08.2026"
    # KEIN Rückfall auf "nur im Bündel" - es GIBT Barpreis-Belege, nur
    # keine frischen.
    assert zeile["nur_buendel"] is False
    assert geraete_view.katalog_leitzahl([zeile]) is None


def test_katalog_leitzahl_nimmt_nur_aktuelle_staende():
    """Die große Zahl über der Katalogtafel: ein billiger LETZTER STAND
    (Galaxy A37, 289 EUR vom 06.09.) darf sie nicht stellen - der
    frische iPhone-Preis (299 EUR vom 19.09.) ist die Leitzahl."""
    frisch = _katalogzeilen([_listung_mit_preis(
        "ElectronicPartner", 299.0, EP_TAG)])[0]
    alt = _katalogzeilen([_listung_mit_preis(
        "Medimax", 289.0, MEDIMAX_TAG, device="samsung-galaxy-a37",
        speicher=128, sku="samsung-galaxy-a37-128gb-schwarz")])[0]
    assert alt["ab_alt"] is True
    assert geraete_view.katalog_leitzahl([alt, frisch]) == 299.0


def test_katalog_ab_grenzfall_tag_drei_fuehrt_tag_vier_nicht():
    """Der Grenzfall an der ab-Auswahl: Tag 3 (noch frisch, der
    Grenzfall des Auftrags) stellt das "ab"; Tag 4 stellt es nicht
    mehr, auch nicht billiger."""
    zeile = _katalogzeilen([
        _listung_mit_preis("Saturn", 899.0, TAG_4),
        _listung_mit_preis("Expert", 999.0, TAG_3)])[0]
    assert zeile["ab_preis"] == 999.0
    assert zeile["ab_anbieter"] == "Expert"
    assert zeile["ab_alt"] is False
    # Gegenprobe: fällt auch der Tag-3-Beleg auf Tag 4, bleibt das "ab"
    # als letzter Stand stehen - mit Marke.
    beides_alt = _katalogzeilen([
        _listung_mit_preis("Saturn", 899.0, TAG_4),
        _listung_mit_preis("Expert", 999.0, TAG_4)])[0]
    assert beides_alt["ab_alt"] is True
    assert beides_alt["ab_preis"] == 899.0
    assert beides_alt["ab_alt_marke"] == "kein aktueller Stand seit 16.09.2026"


def test_katalog_ohne_heute_liest_weiter_den_billigsten():
    """Rückwärtskompatibilität: ohne Uhr (leerer String) altert nichts -
    der alte Aufrufer bekommt weiter den billigsten Beleg, ohne Marke."""
    zeile = _katalogzeilen([
        _listung_mit_preis("Medimax", 289.0, MEDIMAX_TAG),
        _listung_mit_preis("ElectronicPartner", 299.0, EP_TAG)],
        heute="")[0]
    assert zeile["ab_preis"] == 289.0
    assert zeile["ab_anbieter"] == "Medimax"
    assert zeile["ab_alt"] is False


def test_render_site_traegt_die_katalog_marke_in_die_seite(tmp_path):
    """Harte Regel 10 am Markup, durch `render_site`: Sind die Barpreis-
    Belege EINES Modells alle älter als die Grenze, zeigt die Katalog-
    zeile den letzten Stand AUSGEGRAUT mit Marke - und die Leitzahl des
    Regals („günstigster Einzelgerätpreis im Regal“) bleibt weg, statt
    einen 37 Tage alten Preis als großen Tagessatz zu führen."""
    import json
    root, _ = _buendel_welt(tmp_path)
    pfad = root / "data" / "state" / "geraete_db.json"
    roh = json.loads(pfad.read_text(encoding="utf-8"))
    for e in roh["listungen"]:
        e["abgerufen_am"] = DEBITEL_TAG
    pfad.write_text(json.dumps(roh), encoding="utf-8")
    html = _weltsite(root)
    assert "gr-k-ab--alt" in html
    assert "kein aktueller Stand seit 14.08.2026" in html
    # Die Leitzahl des Regals fehlt: ihr Block ist der EINSTE mit der
    # Klasse `gr-leit--katalog` (die Wortwahl "günstigster" allein taugt
    # nicht als Gegenprobe - sie steht auch am Tabellenkopf des Vergleichs).
    assert "gr-leit--katalog" not in html


def test_alters_haendlerpreis_fuehrt_die_antwortzeile_nicht():
    """Dieselbe Definition an der ANTWORTZEILE der Tafel: ein alter
    Saturn-Preis (1199 EUR, Tag 4) ist kein "günstigster Gerätepreis"
    von heute - die frische eigene Vodafone-Zahl (1249 EUR) führt. Ist
    der Saturn-Beleg Tag 3 alt, führt er wie zuvor."""
    listungen = [
        {"id": f"vf-bar--{SKU}", "sku_id": SKU,
         "device_id": "apple-iphone-17-pro", "anbieter": "Vodafone",
         "speicher_gb": 256, "zustand": "neu", "status": "aktiv",
         "preis_ohne_vertrag": 1249.0,
         "quelle_url": "https://vodafone.invalid/x",
         "abgerufen_am": HEUTE},
        {"id": f"saturn--{SKU}", "sku_id": SKU,
         "device_id": "apple-iphone-17-pro", "anbieter": "Saturn",
         "speicher_gb": 256, "zustand": "neu", "status": "aktiv",
         "preis_ohne_vertrag": 1199.0,
         "quelle_url": "https://saturn.invalid/x",
         "abgerufen_am": TAG_4}]
    alt = karten.modelle([_vodafone(), _telekom()], listungen, [], {},
                         _katalog(), heute=HEUTE)["modelle"][0]
    assert alt["antwort"]["geraetepreis"] == 1249.0
    assert alt["antwort"]["geraetepreis_anbieter"] == "Vodafone"
    # Gegenprobe am Grenzfall: Tag 3 ist frisch - Saturn führt (1199).
    listungen[1]["abgerufen_am"] = TAG_3
    frisch = karten.modelle([_vodafone(), _telekom()], listungen, [], {},
                            _katalog(), heute=HEUTE)["modelle"][0]
    assert frisch["antwort"]["geraetepreis"] == 1199.0
    assert frisch["antwort"]["geraetepreis_anbieter"] == "Saturn"


# ==========================================================================
# Die zweite Prüfrunde (diff-reviewer, 21.09.2026): 3×S2 (blockierend)
# und 3×S3. Jeder Test hier war gegen den zurückgewiesenen Stand ROT;
# die Repro-Zahlen des Prüfers stehen in den Fixtures.
# ==========================================================================

VF_BARPREIS_ALT = "2026-09-08"    # 12 Tage vor HEUTE - der S2-1-Repro
TELEKOM_ALT = "2026-09-15"        # 5 Tage: Telekoms altes Klein-Bündel
TELEKOM_FRISCH = "2026-09-19"     # 1 Tag: Telekoms frisches Groß-Bündel


def _telekom_zwei_baender():
    """Telekom ZWEIMAL in verschiedenen Bändern (verschiedene Tarife,
    damit die Angebots-Dedupe in `modelle()` beide lässt - derselbe
    Tarif würde die frische Karte behalten und die alte verwerfen):

        klein, ALT (15.09.):  1,00 + 24 × 4,99 + 24 × 25,00 =   720,76
        gross, FRISCH (19.09.): 1,00 + 24 × 24,99 + 24 × 35,00 = 1.440,76

    Das sind die Repro-Zahlen des Prüfers zu S2-2 (Radar-Beleg) und
    S2-3 (falsche Existenzaussage der Zeitreihe)."""
    return karten.modelle(
        [_buendel("Telekom", "tk:s", "MagentaMobil S", 4.99, 25.0,
                  TELEKOM_ALT),
         _buendel("Telekom", "tk:xl", "MagentaMobil XL", 24.99, 35.0,
                  TELEKOM_FRISCH),
         _vodafone()],
        _listungen(), [], {}, _katalog(), heute=HEUTE)


# ---- S2-1: die Näherung altert über ihre beiden Belege --------------------

def _naeherung_welt():
    """Vodafone OHNE Bündel, dafür ein eigener Barpreis (999,00 EUR vom
    08.09.) und ein SIM-only-Blatt (24,99 EUR/Monat, ebenfalls 08.09.) -
    die Näherung 24 × 24,99 + 999,00 = 1.598,76 EUR ist mit BEIDEN
    Belegen 12 Tage alt. Telekom frisch: 1,00 + 24 × 24,99 + 24 × 35,00
    = 1.440,76 EUR (der S2-1-Repro des Prüfers)."""
    referenzen = [SimOnlyReferenz(
        anbieter="Vodafone", tarif_name="Vodafone Mobil XS",
        tarif_id="vf:xs", tarif_sim_only_monatlich=24.99,
        quelle_url="https://example.de/pib/vf-xs",
        abgerufen_am=VF_BARPREIS_ALT)]
    listungen = [
        {"id": "vf-bar--" + SKU, "sku_id": SKU,
         "device_id": "apple-iphone-17-pro", "anbieter": "Vodafone",
         "speicher_gb": 256, "zustand": "neu", "status": "aktiv",
         "preis_ohne_vertrag": 999.0,
         "quelle_url": "https://vodafone.invalid/barpreis",
         "abgerufen_am": VF_BARPREIS_ALT},
        *[l for l in _listungen() if l["anbieter"] == "Telekom"]]
    return _modell(karten.modelle(
        [_buendel("Telekom", "tk:m", "MagentaMobil M", 24.99, 35.0, HEUTE)],
        listungen, referenzen, {}, _katalog(), heute=HEUTE))


def test_eine_alte_naeherung_ist_keine_zahl_von_heute():
    """S2-1: die Frische der Näherung kommt aus ihren BEIDEN Belegen
    (Tarifblatt und Barpreis), nicht aus einem hartkodierten True. Vor
    dem Fix gewann der 12 Tage alte Barpreis (999,00 EUR) die Antwort-
    zeile („Günstigster Gerätepreis“) ohne Altkennzeichnung, und das
    frische Telekom-Delta rechnete gegen die alte Referenz
    (1.440,76 − 1.598,76 = −158,00 EUR, referenz_datum 2026-09-08)."""
    modell = _naeherung_welt()
    naeherung = next(k for k in modell["karten"] if k.get("naeherung"))
    assert naeherung["gesamt"] == 1598.76
    assert naeherung["frisch"] is False
    assert naeherung["alt_marke"] == "kein aktueller Stand seit 08.09.2026"
    # Die Karte bleibt stehen (Regel 9) - aber der alte Barpreis führt
    # NICHT die Antwortzeile: es gibt keinen frischen Gerätepreis.
    assert modell["antwort"]["geraetepreis"] is None
    assert modell["antwort"]["geraetepreis_anbieter"] is None
    # Und kein frisches Delta rechnet gegen die alte Referenz - der
    # Tarif-Teil der Antwortzeile bleibt, Telekom ist frisch.
    telekom = _karte(modell, "Telekom")
    assert telekom["gesamt"] == 1440.76
    assert telekom["frisch"] is True
    assert telekom["delta"] is None
    assert modell["antwort"]["tarif_gesamt"] == 1440.76
    assert modell["antwort"]["tarif_anbieter"] == "Telekom"


# ---- S2-2: der Radar-Beleg je Anbieter nimmt die FRISCHE Karte -------------

def test_radar_beleg_nimmt_die_frische_karte_nicht_die_alte_billige():
    """S2-2: `_guenstigste_echte_karte_je_anbieter` nahm das Minimum
    über frische UND alte Karten - Telekom alt 720,76 EUR (15.09.)
    verdrängte Telekom frisch 1.440,76 EUR (19.09.) als Beleg des
    Band-Mismatch, und die frische Karte war im Radar unsichtbar.
    Seit dem Fix gilt dieselbe Ordnung wie `_angebot_rang`: Frische vor
    Preis."""
    from telco_radar.report import geraete_radar as radar_modul
    modell = _modell(_telekom_zwei_baender())
    beste = radar_modul._guenstigste_echte_karte_je_anbieter(modell)
    assert set(beste) == {"Telekom"}
    assert beste["Telekom"]["gesamt"] == 1440.76
    assert beste["Telekom"]["abgerufen_am"] == TELEKOM_FRISCH


# ---- S2-3: keine falsche Existenzaussage in der Zeitreihe ------------------

def test_zeitreihe_nennt_den_alten_stand_statt_ein_buendel_abzustreiten(
        tmp_path):
    """S2-3: Telekom führt im Band klein ein (gealtetes) Bündel -
    720,76 EUR vom 15.09. - und im Band groß ein frisches. Vor dem Fix
    prüfte `_luecken` die Frische über ALLE Karten des Anbieters VOR
    der Bandfrage und sagte dann „Kein Bündel in diesem Band: Telekom“,
    obwohl die alte Klein-Karte als alt-Zeile über dem Satz steht - eine
    falsche Existenzaussage (harte Regel 9). Richtig ist der alte Stand
    DES BANDES: „Kein aktueller Stand: Telekom (groß 1.440,76 €)“."""
    modell = _modell(_telekom_zwei_baender())
    band_je = {"tk:s": "klein", "tk:xl": "gross", "vf:m": "mittel"}
    for k in modell["karten"]:
        k["band"] = band_je.get((k.get("tarif_id") or "").strip())
    tco = {"modelle": [modell],
           "baender_katalog": [
               {"key": "klein", "label": "Klein", "bereich": "bis 20 GB"},
               {"key": "mittel", "label": "Mittel",
                "bereich": "21 bis 60 GB"},
               {"key": "gross", "label": "Groß", "bereich": "ab 61 GB"}],
           "historie_lage": {"seit": "", "messtage": 0, "buendel": 0}}
    zr = geraete_zeitreihe.aufbereiten(tmp_path / "state", tco)
    paar = next(p for p in zr["paare"] if p["band"] == "klein")
    assert "Kein aktueller Stand: Telekom" in paar["luecke_text"]
    assert "Kein Bündel in diesem Band: Telekom" not in paar["luecke_text"]
    # Die alte Karte des Bandes bleibt sichtbar: der Satz über den
    # Zeilen nennt den letzten Stand MIT Datum.
    assert "15.09.2026" in paar["antwort_html"]


# ---- S3b: `abgerufen_am: null` ist unbekannt, kein Notzustand --------------

def test_abgerufen_am_none_ist_unbekannt_kein_crash():
    """S3b: ein JSON-null im `abgerufen_am` (Rest eines halben
    Schreibvorgangs) warf in `kurz_datum` einen TypeError - und damit
    die ganze Geräteseite in ihren Notzustand. Unbekannt heißt
    unbekannt: nie Crash, nie geraten (Clean Code 4)."""
    assert karten.kurz_datum(None) == ""
    modell = _modell(karten.modelle([_o2(None), _vodafone(), _telekom()],
                                    _listungen(), [], {}, _katalog(),
                                    heute=HEUTE))
    o2 = _karte(modell, "o2")
    assert o2["frisch"] is False
    assert o2["alt_marke"] == "kein aktueller Stand – Abrufdatum unbekannt"


# ---- S3c: ein Berichts-JSON ohne "date" bringt das Rendern nicht um --------

def test_bericht_ohne_datumfeld_rendert_statt_zu_crashen(tmp_path):
    """S3c: ein gültiges Berichts-JSON ohne „date“ (Rest eines
    abgebrochenen Schreibvorgangs) warf erst die Geräteseite in den
    Notzustand (KeyError, gefangen) und brach anschließend das ganze
    Rendering am Archiv ab (ungefangener KeyError). Das Datum steht im
    Stamm - der Berichtssatz bekommt es von dort, genau wie der
    .md-Fallback in `_load_reports` es ohnehin tut."""
    import json
    root, _ = _buendel_welt(tmp_path)
    reports = root / "data" / "reports"
    for alt in reports.iterdir():
        alt.unlink()
    (reports / f"{REPORT_STAND}.json").write_text(json.dumps(
        {"language": "de",
         "briefing_md": "## Auf einen Blick\n\n- Nichts.\n",
         "stats": {}, "regions": []}), encoding="utf-8")
    html = _weltsite(root)
    assert "1.080,76" in html
    assert "KeyError" not in html


# ---- S3d (Pin): die Wochenkarte hängt an der Berichts-Uhr ------------------

def test_wochenkarte_rechnet_gegen_den_berichtstag(tmp_path):
    """S3d: seit der A3-Verdrahtung rechnet „Was diese Woche auffällt“
    gegen den BERICHTSTAG (und `geraete_lifecycle` über dieselbe Leitung)
    - nicht gegen today(). `first_seen` 13 Tage vor dem Bericht liegt im
    14-Tage-Fenster, 18 Tage vor today() (21.09.) läge außerhalb: Der
    Satz „erstmals erfasst“ stünde also nur, wenn der Bericht die Uhr
    stellt. Die Gegenprobe im selben Test ist der Kompatibilitätsmodus
    ohne Bericht (heute="") - dasselbe Datenbild, keine Uhr, kein Satz."""
    import json
    root, _ = _buendel_welt(tmp_path)
    pfad = root / "data" / "state" / "geraete_db.json"
    roh = json.loads(pfad.read_text(encoding="utf-8"))
    for e in roh["listungen"]:
        e["first_seen"] = "2026-09-03"    # 13 Tage vor REPORT_STAND
    pfad.write_text(json.dumps(roh), encoding="utf-8")
    assert "erstmals erfasst" in _weltsite(root)
    reports = root / "data" / "reports"
    for alt in reports.iterdir():
        alt.unlink()
    assert "erstmals erfasst" not in _weltsite(root)
