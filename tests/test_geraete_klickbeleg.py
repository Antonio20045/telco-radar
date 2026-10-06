"""Beleg je Klick (Datenkonzept Geräteradar, Abschnitt 10, Schritt 6), ohne Browser.

Die Werte, die Antwort und der Screenshot sind ein BEISPIEL (``tests/belegbau.py``).
"""

from __future__ import annotations

import io
import json
import math
from dataclasses import replace

import pytest
from belegbau import TEXT, ZEIT, antwortkopie, karte, paket, png, quelle
from PIL import Image

from telco_radar.collect.geraete.klickbeleg import (
    GRUND_OHNE_ANTWORT,
    GRUND_OHNE_BILD,
    PNG,
    WEBP,
    baue_beleg,
    beleg_id,
    belegstellen,
    bild_fuer_beleg,
    sha256,
    werte_als_json,
    werte_aus_json,
)
from telco_radar.collect.geraete.klickecho import Variante
from telco_radar.collect.geraete.klickhar import (
    HarFehler,
    har_aus,
    har_eintrag,
    zugangskoepfe,
)
from telco_radar.collect.geraete.klicklauf import (
    BEFUND,
    BELEG_FEHLT,
    BELEGT,
    ERFASST,
    NICHT_ANGEBOTEN,
    OHNE_WERT,
    Kombiergebnis,
    mit_beleg,
)
from telco_radar.collect.geraete.klicktext import (
    Preiswerte,
    fundstellen,
    lies_zusammenfassung,
)
from telco_radar.tarif_model import Preisphase

TEXTE = (
    TEXT,
    "Anzahlung: entfällt\nGerätrate 19,99 €\n36 Raten\nTarif 39,99 €\n"
    "Vertragslaufzeit 24 Monate\nohne Anschlusspreis\nHighspeed-Volumen unbegrenzt",
    "Zuzahlung 1,00 € – 24 x 30,00 €\nGrundgebühr 9,99 € mtl. in den ersten 6 Monaten,"
    " danach 19,99 €\nTarifbindung 24 Monate\nBereitstellung 0,00 €\nDaten 512 MB",
)


def test_beleg_id_ist_sha256_ueber_bild_und_mitschnitt_nie_ueber_den_titel():
    erstes = paket()
    anderer_titel = paket(anbieter="Anderer Name", seite="http://127.0.0.1:8000/x")

    beleg = erstes.beleg
    assert beleg.beleg_id == beleg_id(erstes.bild, erstes.mitschnitt)
    assert len(beleg.beleg_id) == 64
    assert anderer_titel.beleg.beleg_id == beleg.beleg_id
    assert beleg.bild.sha256 == sha256(erstes.bild)
    assert beleg.mitschnitt.sha256 == sha256(erstes.mitschnitt)
    assert beleg.bild.name == f"{beleg.beleg_id}.webp"
    assert beleg.mitschnitt.name == f"{beleg.beleg_id}.har"


def test_anderes_bild_oder_andere_antwort_gibt_eine_andere_beleg_id():
    beleg = paket().beleg

    anderes_bild = paket(screenshot_png=png((10, 200, 10))).beleg
    andere_antwort = paket(antwort=antwortkopie(None, etag="x")).beleg

    assert anderes_bild.beleg_id != beleg.beleg_id
    assert andere_antwort.beleg_id != beleg.beleg_id
    assert beleg_id(b"ab", b"c") != beleg_id(b"a", b"bc")


def test_beleg_traegt_zeit_adresse_status_werte_und_fundstellen():
    beleg = paket().beleg

    assert beleg.zeitpunkt == "2026-10-03T05:00:00Z"
    assert beleg.adresse.endswith("/handy/beispielhandy-x")
    assert (beleg.http_status, beleg.antwort_status) == (200, 200)
    assert beleg.antwort_url.endswith("speicher=256&tarif=S&laufzeit=24")
    assert beleg.variante == {"speicher": "256", "tarif": "S", "laufzeit": 24}
    assert beleg.werte["rate"] == 25.0
    assert beleg.werte["tarifphasen"] == [[1, 24, 29.99], [25, None, 34.99]]
    stellen = {s.feld: s for s in beleg.fundstellen}
    assert set(stellen) == {f for f, w in beleg.werte.items() if w is not None}
    assert stellen["rate"].ausschnitt == "Gerätrate 25,00 €"
    assert stellen["rate"].json_pfad == "preis.rate"
    assert stellen["rate"].selektor == "#preis"
    assert stellen["tarifphasen"].json_pfad == "tarif.phasen[*].{ab,bis,betrag}"


@pytest.mark.parametrize("text", TEXTE)
def test_jeder_ausschnitt_nennt_allein_denselben_wert_wie_der_ganze_text(text):
    ganz = lies_zusammenfassung(text)

    stellen = fundstellen(text)

    gelesen = {f for f in ganz.__dataclass_fields__ if getattr(ganz, f) is not None}
    assert set(stellen) == gelesen
    for feld, ausschnitt in stellen.items():
        assert ausschnitt in text
        assert getattr(lies_zusammenfassung(ausschnitt), feld) == getattr(ganz, feld)


def test_wert_ohne_fundstelle_im_text_gibt_keinen_beleg():
    werte = replace(lies_zusammenfassung(TEXT), anschluss=12.0)
    ohne_zeile = TEXT.replace("Anschlusspreis 39,99 €", "")

    stellen, grund = belegstellen(werte, ohne_zeile, karte())
    gegenprobe, kein_grund = belegstellen(werte, TEXT, karte())

    assert stellen == ()
    assert grund == "Beleg fehlt: anschluss ohne Fundstelle im Text"
    assert kein_grund is None
    assert len(gegenprobe) == 7


@pytest.mark.parametrize(
    ("ersetzt", "grund"),
    [
        ({"screenshot_png": None}, GRUND_OHNE_BILD),
        ({"antwort": None}, GRUND_OHNE_ANTWORT),
        ({"werte": Preiswerte()}, "Beleg fehlt: keine gelesenen Werte"),
    ],
)
def test_ohne_bild_antwort_oder_werte_gibt_es_keinen_beleg(ersetzt, grund):
    fertig, gemeldet = baue_beleg(quelle(**ersetzt), karte(), ZEIT)

    assert fertig is None
    assert gemeldet == grund


def test_erfasster_wert_ohne_beleg_ist_befund_und_nicht_gueltig():
    werte = lies_zusammenfassung(TEXT)
    erfasst = Kombiergebnis(Variante("256", "S", 24), ERFASST, werte=werte)

    ohne = mit_beleg(erfasst, None, GRUND_OHNE_BILD)
    mit = mit_beleg(erfasst, paket(), None)

    assert ohne.status == BEFUND
    assert ohne.beleg_status == BELEG_FEHLT
    assert ohne.befunde[-1].feld == "beleg"
    assert ohne.grund == GRUND_OHNE_BILD
    assert ohne.werte == werte
    assert not ohne.gueltig
    assert mit.status == ERFASST
    assert mit.beleg_status == BELEGT
    assert mit.gueltig


def test_kombination_ohne_werte_braucht_keinen_beleg():
    angeboten = Kombiergebnis(Variante("128", "S", 36), NICHT_ANGEBOTEN, "gesperrt")

    ergebnis = mit_beleg(angeboten, None, "Beleg fehlt: keine gelesenen Werte")

    assert ergebnis.status == NICHT_ANGEBOTEN
    assert ergebnis.beleg_status == OHNE_WERT
    assert ergebnis.befunde == ()
    assert not ergebnis.gueltig


def test_screenshot_wird_verlustfrei_webp_sonst_bleibt_er_png():
    roh = png()

    webp, typ = bild_fuer_beleg(roh)
    behalten, png_typ = bild_fuer_beleg(roh, webp=False)
    kaputt, kaputt_typ = bild_fuer_beleg(b"kein Bild")

    assert typ == WEBP
    assert webp[:4] == b"RIFF"
    assert webp[8:12] == b"WEBP"
    with Image.open(io.BytesIO(webp)) as neu, Image.open(io.BytesIO(roh)) as alt:
        assert neu.convert("RGB").tobytes() == alt.convert("RGB").tobytes()
    assert (behalten, png_typ) == (roh, PNG)
    assert (kaputt, kaputt_typ) == (b"kein Bild", PNG)
    ohne_webp, _ = baue_beleg(quelle(), karte(), ZEIT, webp=False)
    assert ohne_webp is not None
    assert ohne_webp.beleg.bild.typ == PNG
    assert ohne_webp.beleg.bild.name.endswith(".png")


def test_mitschnitt_traegt_nie_cookies_oder_zugangskoepfe():
    kopie = antwortkopie(
        None,
        Cookie="sitzung=geheim123",
        **{"Set-Cookie": "sitzung=geheim123", "Authorization": "Bearer geheim123"},
    )

    har = har_aus(kopie, ZEIT)
    eintrag = json.loads(har)["log"]["entries"][0]

    assert b"geheim123" not in har
    assert zugangskoepfe(har) == []
    assert eintrag["request"]["cookies"] == []
    assert eintrag["response"]["cookies"] == []
    namen = {k["name"].lower() for k in eintrag["response"]["headers"]}
    assert "content-type" in namen
    assert not namen & {"cookie", "set-cookie", "authorization"}


def test_zugangskoepfe_findet_cookies_in_einer_fremden_datei():
    har = json.loads(har_aus(antwortkopie(), ZEIT))
    eintrag = har["log"]["entries"][0]
    eintrag["response"]["headers"].append({"name": "Set-Cookie", "value": "a=b"})
    eintrag["request"]["cookies"] = [{"name": "a", "value": "b"}]

    funde = zugangskoepfe(json.dumps(har).encode())

    assert funde == ["request: Cookies", "response: Kopf set-cookie"]


def test_har_eintrag_gibt_adresse_status_und_koerper_zurueck():
    kopie = replace(antwortkopie(), koerper=b"\x00\xff binaer")

    url, status, koerper = har_eintrag(har_aus(kopie, ZEIT))
    _, _, json_koerper = har_eintrag(har_aus(antwortkopie(), ZEIT))

    assert (url, status, koerper) == (kopie.url, 200, b"\x00\xff binaer")
    assert json.loads(json_koerper)["preis"]["rate"] == 25.0
    with pytest.raises(HarFehler):
        har_eintrag(b'{"log": {"entries": []}}')


def test_werte_gehen_unverlustig_durch_das_manifest():
    werte = Preiswerte(
        anzahlung=0.0,
        rate=19.99,
        ratenzahl=36,
        tarifphasen=(Preisphase(1, 6, 9.99), Preisphase(7, None, 19.99)),
        tarifbindung=24,
        anschluss=None,
        volumen_gb=math.inf,
    )

    daten = werte_als_json(werte)

    assert json.loads(json.dumps(daten)) == daten
    assert daten["volumen_gb"] == "unbegrenzt"
    assert daten["anschluss"] is None
    assert werte_aus_json(daten) == werte
