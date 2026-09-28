"""P4: der Gerätebock in der Mail - Treue, Zahlen, Ausfall, Testversand.

Dieselbe Regel wie der Treue-Test in `test_newsletter_render.py`: jeder
Textblock steht entweder im Bericht-JSON oder ist ein Rahmentext aus
chrome.yaml. Zahlen werden gegen den Block im Bericht gehalten.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from bs4 import BeautifulSoup, Doctype

from telco_radar.newsletter import render as r
from telco_radar.newsletter.filters import Treffer
from telco_radar.newsletter.quelle import aus_bericht

WURZEL = Path(__file__).resolve().parents[1]
BASIS = "https://telco-radar.onrender.com"


def _zeile(anbieter, delta, fremd, eigen, vorher, **kw):
    z = {"modell": "apple-iphone-17-pro-256", "band": "mittel",
         "geraet": "Apple iPhone 17 Pro 256 GB", "band_label": "Mittel",
         "anbieter": anbieter, "abstand_vorher": vorher,
         "abstand_jetzt": round(vorher + delta, 2), "delta": delta,
         "fremd_delta": fremd, "eigen_delta": eigen,
         "fremd_wert": 1400.0, "eigen_wert": 2000.0,
         "quelle_url": f"https://{anbieter.lower()}.test/angebot",
         "eigen_quelle_url": "https://vodafone.test/angebot",
         "link": "geraete.html?modell=apple-iphone-17-pro-256&band=mittel"}
    z.update(kw)
    return z


BLOCK = {"error": None, "stichtag": "2026-09-27",
         "vergleichstag": "2026-09-20",
         "zeilen": [_zeile("o2", -240.0, -240.0, 0.0, -600.0),
                    _zeile("Telekom", 120.0, 0.0, -120.0, 300.0)],
         "weitere": 3, "geprueft": 8,
         "ohne_aussage": {"angebotswechsel": 47, "messung_fehlt": 49},
         "im_newsletter": True}

BERICHT = {"date": "2026-09-30", "geraete_bewegung": BLOCK,
           "regions": {"Europa": {"highlights": [
               {"headline": "Telekom senkt Preise um zehn Prozent",
                "summary": "Die Deutsche Telekom senkt die Preise.",
                "url": "https://fachpresse.test/telekom",
                "operator": "Deutsche Telekom", "category": "Tarif/Pricing",
                "relevance": 3, "ctm_bezug": 3, "source": "Mobile World Live",
                "date": "2026-09-29"}]}}}


def _nachricht(block=BLOCK):
    treffer = [Treffer(eintrag=e, grund="filter")
               for e in aus_bericht(BERICHT, bericht_url=f"{BASIS}/x.html")]
    return r.baue(treffer, datum_de="30. September 2026",
                  bericht_url=f"{BASIS}/index.html",
                  abmelde_url=f"{BASIS}/newsletter-abgemeldet.html",
                  seit_datum="1. September 2026", basis_url=BASIS,
                  bewegung=block)


def _bloecke(html):
    soup = BeautifulSoup(html, "html.parser")
    for weg in soup.select("title, style, script"):
        weg.decompose()
    return [t for k in soup.find_all(string=True)
            if not isinstance(k, Doctype)
            and (t := re.sub(r"\s+", " ", str(k)).strip())]


def _rahmen():
    aus = []
    for satz in r.rahmentexte():
        teile = [re.escape(t) for t in re.split(r"\{[a-z_]+\}", satz)]
        aus.append(re.compile("^" + ".*".join(teile) + "$"))
    return aus


def _rahmen_bewegung():
    """Die Saetze des Geraeteblocks mit ENGEN Platzhaltern. Ein `.*` wie im
    allgemeinen Treue-Test liesse mit „{von} bis {bis}" jeden Satz durch,
    der „ bis " enthaelt."""
    from telco_radar.report import geraete_bewegung as gb
    from telco_radar.report.geraete_zeitreihe import ANBIETER_FOLGE
    texte = r.lade_chrome()["bewegung"]
    euro = r"\d{1,3}(?:\.\d{3})*(?:,\d\d)? €"
    abstand = "(?:" + "|".join(
        re.escape(texte[k]).replace(re.escape("{betrag}"), euro)
        for k in ("abstand_guenstiger", "abstand_teurer", "abstand_gleich")
    ) + ")"
    gruende = "(?:" + "|".join(
        re.escape(g).replace(re.escape("{tag}"), r"\d\d\.\d\d\.\d{4}")
        for g in (gb.AUSFALL_KEINE_MESSUNG, gb.AUSFALL_NICHT_PRUEFBAR,
                  gb.AUSFALL_AUFBEREITUNG, gb.AUSFALL_VERALTET)) + ")"
    platz = {"{von}": r"\d{1,2}\.\d{1,2}\.", "{bis}": r"\d{1,2}\.\d{1,2}\.",
             "{betrag}": euro, "{euro}": euro, "{prozent}": r"\d+(?:,\d+)? %",
             "{anbieter}": "(?:" + "|".join(map(re.escape, ANBIETER_FOLGE))
             + ")", "{abstand}": abstand, "{n}": r"\d+",
             "{geprueft}": r"\d+", "{gesamt}": r"\d+", "{grund}": gruende}
    aus = []
    for satz in texte.values():
        muster = re.escape(satz)
        for name, ersatz in platz.items():
            muster = muster.replace(re.escape(name), ersatz)
        assert "\\{" not in muster, satz   # jeder Platzhalter belegt
        aus.append(re.compile("^" + muster + "$"))
    return aus


def _erfunden(html, bericht):
    quelle = json.dumps(bericht, ensure_ascii=False)
    rahmen = _rahmen() + _rahmen_bewegung()
    unbedenklich = re.compile(r"^(?:[\W\d\s]|https?://|&\w+;)+$")
    aus = []
    for b in _bloecke(html):
        if (unbedenklich.match(b) or b in quelle
                or any(m.match(b) for m in rahmen)):
            continue
        # Zeilen aus mehreren Rahmenteilen, wie im Treue-Test nebenan.
        rest = b
        for m in sorted(rahmen, key=lambda p: -len(p.pattern)):
            rest = re.sub(m.pattern.strip("^$"), " ", rest)
        if not unbedenklich.match(rest or " "):
            aus.append(b)
    return aus


def test_jeder_block_des_geraeteblocks_steht_im_bericht_oder_im_rahmen():
    html = _nachricht().html
    assert "Apple iPhone 17 Pro 256 GB" in html
    assert _erfunden(html, BERICHT) == []


def test_der_treue_test_findet_ein_erfundenes_geraet():
    block = dict(BLOCK, zeilen=[dict(BLOCK["zeilen"][0])])
    html = _nachricht(block).html.replace("Apple iPhone 17 Pro 256 GB",
                                          "Erfundenes Telefon")
    assert "Erfundenes Telefon" in _erfunden(html, BERICHT)


def test_der_treue_test_findet_einen_erfundenen_anbieter():
    html = _nachricht().html.replace("zugunsten von o2",
                                     "zugunsten von Fakefon")
    assert "zugunsten von Fakefon" in _erfunden(html, BERICHT)


def test_die_platzhalter_des_blocks_oeffnen_den_treue_test_nicht():
    """Befund der Diff-Pruefung: „{von} bis {bis}" als `.*` liess jeden Satz
    mit „ bis " als Rahmentext durch - auch in den Meldungen."""
    html = _nachricht().html.replace(
        "Telekom senkt Preise um zehn Prozent",
        "Erfundene Aussage gilt bis Oktober")
    assert "Erfundene Aussage gilt bis Oktober" in _erfunden(html, BERICHT)
    assert not any(m.match("Erfundene Aussage gilt bis Oktober")
                   for m in _rahmen())


def _zahlen(text):
    return re.findall(r"\d[\d.]*(?= €)", text)


def test_die_zahlen_der_zeile_kommen_aus_dem_block():
    soup = BeautifulSoup(_nachricht().html, "html.parser")
    text = soup.get_text(" ")
    # o2: Abstand -600 -> -840, Aenderung 240; Telekom: 300 -> 420, 120.
    for erwartet in ("240 € zugunsten von o2",
                     "vorher 600 € günstiger als Vodafone",
                     "jetzt 840 € günstiger als Vodafone",
                     "o2 hat den Preis geändert",
                     "120 € zugunsten von Vodafone",
                     "vorher 300 € teurer als Vodafone",
                     "jetzt 420 € teurer als Vodafone",
                     "Vodafone hat den Preis geändert",
                     "und 3 weitere auf der Geräteseite"):
        assert erwartet in re.sub(r"\s+", " ", text), erwartet


def test_die_aenderung_ist_die_groesste_schrift_der_zeile():
    soup = BeautifulSoup(_nachricht().html, "html.parser")
    groessen = {}
    for span in soup.find_all("span", style=True):
        m = re.search(r"(\d+)px", span["style"])
        if m:
            groessen[span.get_text(strip=True)] = int(m.group(1))
    assert groessen["240 €"] == max(groessen.values())


def test_jede_zeile_verlinkt_geraeteseite_und_beide_angebote():
    soup = BeautifulSoup(_nachricht().html, "html.parser")
    ziele = [a["href"] for a in soup.find_all("a")]
    assert (f"{BASIS}/geraete.html?modell=apple-iphone-17-pro-256&band=mittel"
            in ziele)
    assert "https://o2.test/angebot" in ziele
    assert "https://telekom.test/angebot" in ziele
    assert ziele.count("https://vodafone.test/angebot") == 2


def test_html_und_text_tragen_dieselben_zahlen():
    n = _nachricht()
    html = BeautifulSoup(n.html, "html.parser").get_text(" ")
    block_html = html[html.index("Geräte:"):html.rindex("Telekom senkt")]
    block_text = n.text[n.text.index("GERÄTE"):n.text.index("Telekom senkt")]
    assert _zahlen(block_html) == _zahlen(block_text)
    assert _zahlen(block_text)


def test_ohne_bewegung_ein_satz_mit_der_pruefbaren_menge():
    n = _nachricht(dict(BLOCK, zeilen=[], weitere=0))
    satz = ("Keine belegte Bewegung über 50 € oder 5 % seit dem 20.9. "
            "(8 von 104 Vergleichen prüfbar).")
    assert satz in n.text
    assert satz in re.sub(r"\s+", " ",
                          BeautifulSoup(n.html, "html.parser").get_text(" "))


def test_ein_ausfall_wird_gesagt_nicht_verschwiegen():
    grund = "die letzte Vodafone-Messung vom 20.09.2026 ist veraltet"
    n = _nachricht({"error": grund, "zeilen": [], "weitere": 0,
                    "geprueft": 0, "ohne_aussage": {},
                    "im_newsletter": True})
    assert ("Der Gerätevergleich ist diesmal ausgefallen: " + grund) in n.text
    assert "Keine belegte Bewegung" not in n.text
    assert _erfunden(n.html, BERICHT) == []


def test_ein_unvollstaendiger_block_ist_ein_ausfall_kein_absturz():
    n = _nachricht({"error": None, "im_newsletter": True})
    assert "Der Gerätevergleich ist diesmal ausgefallen" in n.text


def test_knapp_ueber_der_schwelle_steht_der_cent():
    block = dict(BLOCK, zeilen=[_zeile("o2", -50.4, -50.4, 0.0, -600.0)],
                 weitere=0)
    assert "50,40 € zugunsten von o2" in _nachricht(block).text


def test_der_block_steht_nur_in_der_ersten_ausgabe_der_woche():
    assert "GERÄTE" not in _nachricht(dict(BLOCK, im_newsletter=False)).text
    assert "GERÄTE" not in _nachricht(None).text
    assert "GERÄTE" in _nachricht().text


# ---------------------------------------------------------- Testversand

def _send(tmp_path, *extra, env=None):
    bericht = tmp_path / "bericht.json"
    bericht.write_text(json.dumps(BERICHT, ensure_ascii=False))
    store = tmp_path / "store.jsonl"
    # Ohne GITHUB_ACTIONS: dort gibt das Skript `::add-mask::` aus (eigener
    # Test unten), und der Test haengt nicht davon ab, wo er laeuft.
    umgebung = {k: v for k, v in os.environ.items()
                if k not in ("TEST_EMPFAENGER", "BREVO_API_KEY",
                             "GITHUB_ACTIONS")}
    umgebung.update(env or {}, PYTHONPATH=str(WURZEL / "src"))
    return subprocess.run(
        [sys.executable, str(WURZEL / "scripts/newsletter/send_digest.py"),
         "--bericht", str(bericht), "--store", str(store),
         "--send-log", str(tmp_path / "log.jsonl"),
         "--plan", str(tmp_path / "plan.json"), "--nur-test", *extra],
        capture_output=True, text=True, env=umgebung, cwd=tmp_path)


def test_der_testversand_ohne_adresse_verschickt_nichts(tmp_path):
    lauf = _send(tmp_path)
    assert lauf.returncode == 2 and "TEST_EMPFAENGER" in lauf.stdout


def test_der_testversand_fasst_store_und_protokoll_nicht_an(tmp_path):
    lauf = _send(tmp_path, "--dry-run", "--ausgabe", str(tmp_path / "aus"),
                 env={"TEST_EMPFAENGER": "test@example.invalid"})
    assert lauf.returncode == 0, lauf.stderr
    assert "Testversand: nur gerendert" in lauf.stdout
    assert "zugestellt" not in lauf.stdout
    assert "test@example.invalid" not in lauf.stdout + lauf.stderr
    html = (tmp_path / "aus" / "test.html").read_text(encoding="utf-8")
    assert "240 €" in html and "Telekom senkt Preise" in html
    for datei in ("store.jsonl", "log.jsonl", "plan.json"):
        assert not (tmp_path / datei).exists()


def test_der_testversand_rechnet_den_block_fuer_alte_berichte(tmp_path):
    """Ein Bericht von vor P4 hat keinen Block - der Test rechnet ihn aus
    dem Geraetestand. Welcher Zustand herauskommt (Zeilen, leer, Ausfall),
    haengt vom Stand ab; dass der Block DA ist, nicht."""
    alt = {k: v for k, v in BERICHT.items() if k != "geraete_bewegung"}
    bericht = tmp_path / "alt.json"
    bericht.write_text(json.dumps(alt, ensure_ascii=False))
    umgebung = dict(os.environ, PYTHONPATH=str(WURZEL / "src"))
    lauf = subprocess.run(
        [sys.executable, str(WURZEL / "scripts/newsletter/send_digest.py"),
         "--bericht", str(bericht), "--nur-test", "--dry-run",
         "--ausgabe", str(tmp_path / "aus")],
        capture_output=True, text=True, env=umgebung, cwd=tmp_path)
    assert lauf.returncode == 0, lauf.stderr[-2000:]
    text = (tmp_path / "aus" / "test.txt").read_text(encoding="utf-8")
    assert "GERÄTE: ABSTAND ZU VODAFONE" in text


def test_in_actions_steht_die_adresse_nur_in_der_maskenzeile(tmp_path):
    """Actions verbirgt den Wert einer `::add-mask::`-Zeile in jedem
    spaeteren Protokoll; die Zeile selbst wird nicht angezeigt."""
    lauf = _send(tmp_path, "--dry-run",
                 env={"TEST_EMPFAENGER": "test@example.invalid",
                      "GITHUB_ACTIONS": "true"})
    assert lauf.returncode == 0, lauf.stderr
    zeilen = [z for z in (lauf.stdout + lauf.stderr).splitlines()
              if "test@example.invalid" in z]
    assert zeilen == ["::add-mask::test@example.invalid"]


def _send_modul():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "send_digest_test", WURZEL / "scripts/newsletter/send_digest.py")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.mark.parametrize("trocken, ok, erwartet, code", [
    (False, True, "Testversand: zugestellt", 0),
    (False, False, "Testversand: gescheitert (402)", 1),
    (True, False, "Testversand: gescheitert (402)", 1),
    (True, True, "Testversand: nur gerendert", 0),
])
def test_die_testversand_zeile_sagt_was_geschah(
        tmp_path, monkeypatch, capsys, trocken, ok, erwartet, code):
    """Nur ein echter, erfolgreicher Versand heisst "zugestellt"; ein
    Fehler schlaegt den Trockenlauf-Hinweis."""
    from telco_radar.newsletter.transport import Ergebnis
    modul = _send_modul()

    class Stub:
        def __init__(self, *a, **k):
            pass

        def send(self, nachricht, an):
            return Ergebnis(ok=ok, status=0 if ok else 402)

    monkeypatch.setattr(modul, "BrevoTransport", Stub)
    monkeypatch.setattr(modul, "Trockenlauf", Stub)
    monkeypatch.setenv("TEST_EMPFAENGER", "test@example.invalid")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    bericht = tmp_path / "bericht.json"
    bericht.write_text(json.dumps(BERICHT, ensure_ascii=False))
    argv = ["--bericht", str(bericht), "--nur-test"]
    if trocken:
        argv.append("--dry-run")
    assert modul.main(argv) == code
    aus = capsys.readouterr().out
    assert erwartet in aus
    if erwartet != "Testversand: zugestellt":
        assert "zugestellt" not in aus
