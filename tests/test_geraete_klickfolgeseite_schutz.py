"""Folgeseite der Klick-Erkundung: nur der eine Weiter-Klick schreibt, ohne Netz.

Prüfer-Reproduktionen zum Auftrag DKFOLGE2, angepasst. Das Ziel kommt wie im Betrieb
aus ``config/klick_erkundung.yaml`` mit ``weiter`` (``lade_ziele`` gegen Kopien der
echten Quellen und des Katalogs); nur die Adressen zeigen auf einen lokalen Server mit
BEISPIEL-Seiten, von Hand geschrieben, kein echter Anbieter. Geprüft wird: auf der
Folgeseite keine Klick-Proben und kein zweites schreibendes POST, ab dem Klick
verwirft das Tor alles außer GET und HEAD; eine Kasse, die erst beim Festhalten
erscheint, ist ein Befund; jede Störung des Tors beendet den Anbieter, auch nach einem
Befund und auf einer leeren Seite; Warenkorb- und Sitzungskennungen aus dem
Weiter-Klick stehen in keiner abgelegten Datei, Varianten- und Tarifcodes schon.

Späte Anfragen löst die Seite aus, sobald die Erkundung sie mit einem bestimmten
Selektor abfragt (Feldprüfung oder Inventar), als synchrones XHR: der Zeitpunkt liegt
damit fest nach der letzten Prüfung des Takts, und die Antwort ist da, bevor die
Erkundung weitermacht.
"""

from __future__ import annotations

import gzip
import json
import shutil
import time
from dataclasses import replace
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml
from klickserver import JETZT, Antwort, html, klickserver

from scripts import erkundung_ablegen as ea
from telco_radar.collect.geraete import klicktor
from telco_radar.collect.geraete.klickerkundung import (
    GRUND_NACH_BOT,
    erkunde_anbieter,
)
from telco_radar.collect.geraete.klickziele import Erkundungsziel, lade_ziele

WURZEL = Path(__file__).resolve().parents[1]
OFFEN = "User-agent: *\nDisallow:\n"
TAG = JETZT.date().isoformat()
ANBIETER = "1und1"
KORB_PFAD = "/frontend/cart-facade/add"
UPDATE_PFAD = "/frontend/cart-facade/update"
WEITER = {"selektor": ".weiter-knopf", "text": "Weiter zur Tarifauswahl"}
GERAET = {"geraet": "beispielhandy-x", "speicher": "256"}
AUSGANG = """<!doctype html><html><body>
<h1>Beispielhandy X</h1>
<div id="speicher" aria-label="Speicher">
 <button data-wert="256" aria-pressed="true">256 GB</button>
 <button data-wert="512" aria-pressed="false">512 GB</button>
</div>
<section id="preis"><p>Monatliche Rate <b>35,00 €</b></p></section>
<section id="angebot"><button class="weiter-knopf">Weiter zur Tarifauswahl</button>
</section>
<script>
for (const k of document.querySelectorAll("#speicher button")) {
  k.addEventListener("click", () => {
    for (const j of document.querySelectorAll("#speicher button")) {
      j.setAttribute("aria-pressed", String(j === k));
    }
  });
}
document.querySelector(".weiter-knopf").addEventListener("click", () => {
  fetch("/frontend/cart-facade/add", {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(KOERPER)})
    .then((r) => r.json()).then((d) => { location.href = d.ziel; });
});
</script></body></html>"""
LAUFZEIT = """<!doctype html><html><body>
<h1>Tarifauswahl</h1>
<div id="laufzeit" aria-label="Laufzeit des Geräts">
 <button data-wert="24" aria-pressed="false" EXTRA>24 Monate</button>
 <button data-wert="36" aria-pressed="true" EXTRA>36 Monate</button>
</div>
<section id="preis"><p>Monatlich <span id="rate">offen</span> TEXT</p></section>
<script>
function lade(monate) {
  fetch(`/api/rate?laufzeit=${monate}`).then((r) => r.json()).then((d) => {
    document.getElementById("rate").innerText = `${d.rate},99 €`;
  });
}
for (const k of document.querySelectorAll("#laufzeit button")) {
  k.addEventListener("click", () => {
    for (const j of document.querySelectorAll("#laufzeit button")) {
      j.setAttribute("aria-pressed", String(j === k));
    }
    lade(k.dataset.wert);
    BEIM_KLICK
  });
}
lade("36");
BEIM_LADEN
</script></body></html>"""
SCHREIBE = """fetch("/frontend/cart-facade/update", {method: "POST",
  headers: {"Content-Type": "application/json"}, body: '{"laufzeit": "24"}'});"""


def _folge(
    beim_klick: str = "", beim_laden: str = "", extra: str = "", text: str = ""
) -> str:
    """Laufzeitwahl wie bei 1&1; die Platzhalter tragen je Test Zusätze."""
    ersatz = {
        "BEIM_KLICK": beim_klick,
        "BEIM_LADEN": beim_laden,
        "EXTRA": extra,
        "TEXT": text,
    }
    seite = LAUFZEIT
    for platzhalter, wert in ersatz.items():
        seite = seite.replace(platzhalter, wert)
    return seite


def _spaet(prototyp: str, merkmal: str, tat: str) -> str:
    """Skript: beim ersten ``querySelectorAll`` mit ``merkmal`` tut die Seite
    ``tat``."""
    return f"""<script>
const alt = {prototyp}.prototype.querySelectorAll;
let einmal = false;
{prototyp}.prototype.querySelectorAll = function (wahl) {{
  if (!einmal && String(wahl).includes("{merkmal}")) {{ einmal = true; {tat} }}
  return alt.call(this, wahl);
}};
</script>"""


SYNCHRON_PRUEFUNG = """const x = new XMLHttpRequest();
x.open("GET", "/api/pruefung", false); try { x.send(); } catch (e) {}"""


def _antworte(folge: str, korb: Antwort, koerper: dict = GERAET, **seiten: Antwort):
    def antworte(pfad: str) -> Antwort:
        teile = urlsplit(pfad)
        if teile.path in seiten:
            return seiten[teile.path]
        if teile.path.startswith("/handy/"):
            return html(AUSGANG.replace("KOERPER", json.dumps(koerper)))
        if teile.path == KORB_PFAD:
            return korb
        if teile.path == "/tarife":
            return html(folge)
        if teile.path == "/api/rate":
            monate = parse_qs(teile.query)["laufzeit"][0]
            rate = {"24": 41, "36": 35}[monate]
            return Antwort(200, "application/json", json.dumps({"rate": rate}))
        if teile.path == UPDATE_PFAD:
            return Antwort(200, "application/json", '{"ok": true}')
        return Antwort(404)

    return antworte


def _korb(ziel: str = "/tarife", **mehr) -> Antwort:
    return Antwort(200, "application/json", json.dumps({"ziel": ziel} | mehr))


def _ziel(
    tmp_path: Path, server, *pfade: str, weiter: dict | None = WEITER
) -> Erkundungsziel:
    """Das Ziel aus ``klick_erkundung.yaml`` mit ``weiter``, Adressen lokal."""
    wurzel = tmp_path / "wurzel"
    (wurzel / "config").mkdir(parents=True)
    for name in ("geraete_quellen.yaml", "geraete_katalog.yaml"):
        shutil.copy(WURZEL / "config" / name, wurzel / "config" / name)
    seiten = [
        {
            "geraet": "apple-iphone-17-pro",
            "speicher_gb": 256,
            "url": f"https://mobile.1und1.de{pfad}",
        }
        | ({} if weiter is None else {"weiter": weiter})
        for pfad in pfade
    ]
    eintrag = {"schluessel": ANBIETER, "name": "1&1", "seiten": seiten}
    datei = wurzel / "config" / "klick_erkundung.yaml"
    datei.write_text(yaml.safe_dump({"anbieter": [eintrag]}), encoding="utf-8")
    (ziel,) = lade_ziele(wurzel)
    lokal = tuple(
        replace(seite, adresse=server.adresse(pfad))
        for seite, pfad in zip(ziel.seiten, pfade, strict=True)
    )
    return replace(ziel, seiten=lokal, kennung=None, rate_limit_sekunden=0.0)


def _erkunde(chromium, ziel: Erkundungsziel, ausgabe: Path) -> dict:
    def hole(url: str) -> tuple[int, str]:
        return 200, OFFEN

    ende = time.monotonic() + 600
    return erkunde_anbieter(chromium, ziel, lambda: JETZT, hole, ausgabe, ende)


def _folgeseite(index: dict) -> dict:
    """Die Folgeseite der ersten Seite; rot, wenn die Erkundung keine anlegte."""
    folge_von = [s.get("folge_von") for s in index["seiten"]]
    assert 1 in folge_von, f"keine Folgeseite zu Seite 1: folge_von {folge_von}"
    return index["seiten"][folge_von.index(1)]


def _lies(ordner: Path, name: str):
    return json.loads((ordner / name).read_text(encoding="utf-8"))


def _texte(ordner: Path) -> dict[str, str]:
    texte = {}
    for datei in sorted(ordner.iterdir()):
        roh = datei.read_bytes()
        if datei.name.endswith(".gz"):
            roh = gzip.decompress(roh)
        texte[datei.name] = roh.decode("utf-8", errors="replace")
    return texte


def test_folgeseite_ohne_proben_und_ohne_zweites_post(chromium, tmp_path):
    """Blocker 1: jede Laufzeitwahl schickt ein POST an den Warenkorb; die Folgeseite
    probiert nicht, also geht nach dem Weiter-Klick kein zweites POST hinaus.
    Gegenprobe: die Produktseite probiert wie bisher, die Folgeseite ist gelesen."""
    with klickserver(_antworte(_folge(SCHREIBE), _korb())) as server:
        index = _erkunde(chromium, _ziel(tmp_path, server, "/handy/x"), tmp_path)

    folge = _folgeseite(index)
    assert (folge["status"], folge["grund"]) == ("gelesen", None)
    assert [p for p, _ in server.posts] == [KORB_PFAD]
    assert json.loads(server.posts[0][1]) == GERAET
    ordner = tmp_path / ANBIETER / TAG
    assert _lies(ordner, folge["dateien"]["klicks"])["proben"] == []
    assert [p["text"] for p in _lies(ordner, "klicks-1.json")["proben"]] == ["512 GB"]
    elemente = _lies(ordner, folge["dateien"]["bedienelemente"])["elemente"]
    assert {"24 Monate", "36 Monate"} <= {e["text"] for e in elemente}
    assert server.mit("/api/rate") == ["/api/rate?laufzeit=36"]


def test_tor_verwirft_nach_dem_weiter_klick_jedes_schreiben(chromium, tmp_path):
    """Ein POST der Folgeseite beim Laden geht nicht hinaus; es steht mit Grund in
    ``verworfen``. Gegenprobe: das POST des Weiter-Klicks und GET gehen hinaus."""
    with klickserver(_antworte(_folge(beim_laden=SCHREIBE), _korb())) as server:
        index = _erkunde(chromium, _ziel(tmp_path, server, "/handy/x"), tmp_path)

    folge = _folgeseite(index)
    assert (folge["status"], folge["grund"]) == ("gelesen", None)
    assert server.mit(UPDATE_PFAD) == []
    assert [p for p, _ in server.posts] == [KORB_PFAD]
    assert server.mit("/api/rate") == ["/api/rate?laufzeit=36"]
    verworfen = {"url": server.adresse(UPDATE_PFAD), "grund": klicktor.GRUND_NUR_LESEN}
    assert verworfen in folge["verworfen"]
    erste = index["seiten"][0]
    assert all(v["grund"] != klicktor.GRUND_NUR_LESEN for v in erste["verworfen"])


TARIFE = """<!doctype html><html><body>
<h1>Tarifauswahl</h1>
<div id="tarif" aria-label="Tarif">
 <button aria-pressed="true">GigaMobil S</button>
 <button aria-pressed="false">GigaMobil M</button>
</div>
<section id="preis"><p>Monatlich <b>39,99 €</b></p></section>
<script>
for (const k of document.querySelectorAll("#tarif button")) {
  k.addEventListener("click", () => { location.href = "/shop/kasse.html"; });
}
</script></body></html>"""
KASSE = """<!doctype html><html><body><h1>Kasse</h1>
<form><label>IBAN <input name="iban"></label>
<button type="submit">Zahlungspflichtig bestellen</button></form></body></html>"""


def test_tarifknopf_der_folgeseite_fuehrt_nicht_in_die_kasse(chromium, tmp_path):
    """Blocker 2: die Tarifknöpfe der Folgeseite führen per Skript in die Kasse; ohne
    Klick-Proben lädt die Erkundung sie nie. Gegenprobe: die Tarifknöpfe stehen im
    Inventar, sie wurden nur nicht geklickt."""
    antworte = _antworte(TARIFE, _korb(), **{"/shop/kasse.html": html(KASSE)})
    with klickserver(antworte) as server:
        index = _erkunde(chromium, _ziel(tmp_path, server, "/handy/x"), tmp_path)

    folge = _folgeseite(index)
    assert (folge["status"], folge["grund"]) == ("gelesen", None)
    assert server.mit("/tarife") == ["/tarife"]
    assert server.mit("/shop/") == []
    ordner = tmp_path / ANBIETER / TAG
    elemente = _lies(ordner, folge["dateien"]["bedienelemente"])["elemente"]
    assert {"GigaMobil S", "GigaMobil M"} <= {e["text"] for e in elemente}


KASSENKNOPF = (
    'document.body.insertAdjacentHTML("beforeend",'
    ' "<button>Zahlungspflichtig bestellen</button>");'
)


@pytest.mark.parametrize(
    ("spaet", "status", "grund"),
    [
        (
            _spaet("Element", "menuitemradio", KASSENKNOPF),
            "befund",
            "Folgeseite zeigt Checkout (Knopf „Zahlungspflichtig bestellen“)",
        ),
        ("", "gelesen", None),
    ],
    ids=["kasse-beim-festhalten", "gegenprobe-ohne-kasse"],
)
def test_kasse_erst_beim_festhalten_ist_ein_befund(
    chromium, tmp_path, spaet, status, grund
):
    """Blocker 2: nach Ruhe und Festhalten prüft die Erkundung das Streckenende noch
    einmal; ein Kassenknopf, der erst beim Lesen des Inventars erscheint, ist ein
    Befund."""
    folge_html = _folge().replace("</body>", f"{spaet}</body>")
    with klickserver(_antworte(folge_html, _korb())) as server:
        index = _erkunde(chromium, _ziel(tmp_path, server, "/handy/x"), tmp_path)

    folge = _folgeseite(index)
    assert (folge["status"], folge["grund"]) == (status, grund)
    assert [p for p, _ in server.posts] == [KORB_PFAD]


ANMELDUNG = """<!doctype html><html><body><h1>Anmelden</h1>
<form><input name="nutzer"><input type="password" name="kennwort"></form>
SPAET</body></html>"""


@pytest.mark.parametrize(
    ("pruefung", "bot", "zweite"),
    [
        (Antwort(403, "application/json", '{"fehler": "blockiert"}'), True, False),
        (Antwort(200, "application/json", '{"ok": true}'), False, True),
    ],
    ids=["403-nach-befund", "gegenprobe-200"],
)
def test_bot_schutz_nach_befund_beendet_den_anbieter(
    chromium, tmp_path, pruefung, bot, zweite
):
    """Blocker 3: die Folgeseite ist eine Anmeldung (Befund); während die Erkundung
    sie auf Passwortfelder prüft, fragt sie ``/api/pruefung`` ab, und die Website
    antwortet 403. Danach geht keine Anfrage mehr hinaus."""
    seite = ANMELDUNG.replace(
        "SPAET", _spaet("Document", "password", SYNCHRON_PRUEFUNG)
    )
    seiten = {"/login": html(seite), "/api/pruefung": pruefung}
    with klickserver(_antworte("", _korb("/login"), **seiten)) as server:
        ziel = _ziel(tmp_path, server, "/handy/x", "/handy/y")
        index = _erkunde(chromium, ziel, tmp_path)

    folge = _folgeseite(index)
    assert folge["status"] == "befund"
    assert folge["grund"] == "Folgeseite zeigt Anmeldung (Adresse: login)"
    assert folge["bot_schutz"] is bot
    nach_pruefung = server.abrufe[server.abrufe.index("/api/pruefung") + 1 :]
    zweite_seite = next(s for s in index["seiten"] if s["nummer"] == 2)
    if zweite:
        assert "/handy/y" in nach_pruefung
        assert zweite_seite["status"] == "gelesen"
    else:
        assert server.mit("/api/pruefung") == ["/api/pruefung"]
        assert nach_pruefung == []
        assert (zweite_seite["status"], zweite_seite["grund"]) == (
            "nicht_besucht",
            GRUND_NACH_BOT,
        )


LEER = """<!doctype html><html><body><h1>Beispielhandy X</h1>
<p>Monatliche Rate 35,00 €</p>SPAET</body></html>"""


@pytest.mark.parametrize(
    ("pruefung", "erwartet"),
    [
        (
            Antwort(403, "application/json", '{"fehler": "blockiert"}'),
            ("gestoert", True, "Abruf gestört (HTTP 403 auf {pruefung})"),
        ),
        (
            Antwort(200, "application/json", '{"ok": true}'),
            ("leer", False, "kein Bedienelement"),
        ),
    ],
    ids=["403-auf-leerer-seite", "gegenprobe-200"],
)
def test_bot_schutz_auf_leerer_seite_beendet_den_anbieter(
    chromium, tmp_path, pruefung, erwartet
):
    """Blocker 3, schon auf der Basis: eine leere Seite fragt beim Lesen des Inventars
    ``/api/pruefung`` ab, die Website antwortet 403. Die Seite ist gestört, und der
    Anbieter endet, ohne die zweite Seite abzurufen."""
    leer = html(
        LEER.replace("SPAET", _spaet("Element", "menuitemradio", SYNCHRON_PRUEFUNG))
    )
    seiten = {"/handy/x": leer, "/handy/y": leer, "/api/pruefung": pruefung}
    with klickserver(_antworte("", _korb(), **seiten)) as server:
        ziel = _ziel(tmp_path, server, "/handy/x", "/handy/y", weiter=None)
        index = _erkunde(chromium, ziel, tmp_path)

    erste, zweite = index["seiten"]
    status, bot, grund = erwartet
    grund = grund.format(pruefung=server.adresse("/api/pruefung"))
    assert (erste["status"], erste["bot_schutz"], erste["grund"]) == (
        status,
        bot,
        grund,
    )
    if bot:
        assert server.abrufe == ["/handy/x", "/api/pruefung"]
        assert (zweite["status"], zweite["grund"]) == ("nicht_besucht", GRUND_NACH_BOT)
    else:
        assert server.mit("/handy/") == ["/handy/x", "/handy/y"]
        assert zweite["status"] == "leer"


KORB = "K7q2Wm9Zx4Lp8Tr3"
VORGANG = "B4sk3tW3rt9Q"
SITZUNG = "s1tzungsWert0815abc"
VARIANTE = "P-4356815"
TARIF = "GM-M-24"


def test_kennungen_aus_dem_weiter_klick_stehen_in_keiner_datei(chromium, tmp_path):
    """Blocker 4: das POST trägt eine Vorgangskennung (``basketId``), die Antwort die
    Warenkorb-Kennung (``cartId``), die wieder in der Folgeadresse, unter harmlosen
    Namen (``vorgang``, ``data-korb``) und im Seitentext auftauchen; das
    Sitzungs-Cookie hat einen anderen Wert. Gegenprobe: Varianten- und Tarifcode der
    Antwort bleiben stehen."""
    ziel = f"/tarife?cartId={KORB}&vorgang={VORGANG}"
    antwort = {"cartId": KORB, "warenkorb": {"id": KORB}, "deviceVariantId": VARIANTE}
    korb = Antwort(
        200,
        "application/json",
        json.dumps({"ziel": ziel} | antwort | {"tarifCode": TARIF}),
        {"Set-Cookie": f"sitzung={SITZUNG}; Path=/"},
    )
    koerper = {"deviceVariantId": VARIANTE, "basketId": VORGANG}
    folge_html = _folge(extra=f'data-korb="{KORB}"', text=f"Vorgang {VORGANG}")
    neu = tmp_path / "neu"
    with klickserver(_antworte(folge_html, korb, koerper)) as server:
        index = _erkunde(chromium, _ziel(tmp_path, server, "/handy/x"), neu / "art")

    folge = _folgeseite(index)
    assert (folge["status"], folge["grund"]) == ("gelesen", None)
    assert json.loads(server.posts[0][1]) == koerper
    ordner = neu / "art" / ANBIETER / TAG
    alles = _texte(ordner)
    for kennung in (KORB, VORGANG, SITZUNG):
        assert [n for n, t in alles.items() if kennung in t] == [], kennung
    abgelegt = _folgeseite(_lies(ordner, "index.json"))
    sauber = server.adresse("/tarife?cartId=ENTFERNT&vorgang=[Cookie entfernt]")
    assert (abgelegt["endadresse"], abgelegt["weiter"]["nach"]) == (sauber, sauber)
    mitschnitt = alles[folge["dateien"]["mitschnitt"]]
    assert VARIANTE in mitschnitt and TARIF in mitschnitt
    bedienelemente = alles[folge["dateien"]["bedienelemente"]]
    assert '"data-wert": "24"' in bedienelemente
    assert '"data-korb": "[Cookie entfernt]"' in bedienelemente
    zweig = tmp_path / "zweig"
    assert ea.einsortieren(neu, zweig) == [ANBIETER]
    oeffentlich = _texte(zweig / ANBIETER / TAG)
    assert {f"mitschnitt-{folge['nummer']}.json", "index.json"} <= set(oeffentlich)
    for kennung in (KORB, VORGANG, SITZUNG):
        assert [n for n, t in oeffentlich.items() if kennung in t] == [], kennung
    assert ea.pruefe(zweig) == []
