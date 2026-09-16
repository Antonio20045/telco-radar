"""Katalog D auf der TCO-Tafel (QA-Befunde S2, S4, S12 vom 04.09.2026).

Dieselbe Fixture wie `test_geraete_tco_zustand._baue` (geraete_db.json,
geraete_tco.json, tarife.jsonl, geraete_preise.jsonl, drei Konfigdateien in
tmp_path). Gemessen wird am gerenderten HTML, weil die Woerter dort stehen.
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from telco_radar.geraete_config import lade_katalog
from telco_radar.report import geraete_tco_grafik as grafik
from telco_radar.report import geraete_tco_karten as karten

from test_geraete_tco_zustand import WURZEL, _baue, _modell


def test_der_hersteller_steht_nicht_zweimal_im_titel():
    assert karten.titel("Xiaomi", "Xiaomi 17 512 GB") == "Xiaomi 17 512 GB"
    assert karten.titel("Nothing", "Nothing Phone (3) 256 GB") == "Nothing Phone (3) 256 GB"
    assert karten.titel("Apple", "iPhone 15 128 GB") == "Apple iPhone 15 128 GB"
    assert karten.titel("", "iPhone 15 128 GB") == "iPhone 15 128 GB"
    # Und ein echtes Modell aus dem Katalog traegt den Titel.
    assert _modell()["titel"] == "Apple iPhone 15 128 GB"


def test_das_euro_delta_steht_am_g1_balken():
    """S4 / C.1: dieselbe Zahl wie auf der Karte, in der Grafik."""
    modell = _modell()
    neu = next(k for k in modell["karten"] if k["anbieter"] == "o2"
               and k["zustand"] == "neu")
    svg = grafik.balken(modell)
    assert neu["delta"]["guenstiger"]
    erwartet = f'<tspan class="gr-g1-delta">−{grafik.euro(neu["delta"]["abstand"])}</tspan>'
    assert erwartet in svg
    # Die Referenz selbst und das erneuerte Geraet tragen kein Delta.
    assert svg.count("gr-g1-delta") == 1


def test_die_referenzzeile_behauptet_keine_36_monate(tmp_path):
    """Ticket TCO24-1 (08.09.2026): die Leitzahl ist auf der ganzen Seite
    IMMER TCO-24 (AUFTRAG_GERAETESEITE.md §3, "Immer 24 Monate") - kein
    Angebot traegt mehr eine variable Bindung als Vergleichshorizont, und
    keine Referenzzeile rechnet mehr ueber ein fremdes Fenster.

    O2 (11.09.2026): die Karte ist eine Tabellenzeile - die Zeile führt
    mit TCO-24 (wie der Graph über ihr), der Gerätepreis ohne Vertrag
    steht in der eigenen Spalte, Ø/Monat und der Rechenweg im Aufklapper.
    """
    s = _baue(tmp_path)
    ref = s.select_one('#tafel-tco .gr-bnd[data-anbieter="Vodafone"]')
    assert ref.select_one(".gr-kk-marke").get_text(strip=True) == "Referenzrechnung"
    assert "1.428,70 €" in ref.select_one(".gr-bnd-tco").get_text()
    assert "TCO-24" in ref.select_one(".gr-bnd-tco").get_text()
    # Der Gerätepreis (A-R5) steht in der eigenen Spalte, getrennt (§3).
    assert "709,90 €" in ref.select_one(".gr-bnd-bar").get_text()
    assert ref["data-laufzeit"] == "24"
    text = " ".join(ref.get_text(" ", strip=True).split())
    assert "TCO-24 1.428,70 €" in text
    assert "36 Monate" not in text
    assert "TCO-36" not in text
    assert "24 Monate Tarifbindung; das Gerät ist bar gekauft und bindet nicht" in text
    # Das o2-Angebot daneben rechnet die LEITZAHL ebenfalls ueber 24 Monate -
    # seine Geraeteraten laufen zwar 36 Monate, aber die 12 Raten jenseits
    # des Horizonts stehen als eigener, klar bezeichneter Restbetrag daneben
    # und NICHT in der TCO-Zahl (Abnahmekriterium 2).
    o2 = s.select_one('#tafel-tco .gr-bnd[data-anbieter="o2"][data-zustand="neu"]')
    assert "880,75 €" in o2.select_one(".gr-bnd-tco").get_text()
    assert "709,00 €" in o2.select_one(".gr-bnd-bar").get_text()
    o2_text = " ".join(o2.get_text(" ", strip=True).split())
    assert "TCO-36" not in o2_text and "36 Monate Bindung" not in o2_text
    # S-Q4 (09.09.2026): "Gerechnet über 24 Monate Bindung" war derselbe
    # Widerspruch, nur als Satz - der Rechenweg sagt "Tarif bindet 24,
    # Geräteraten laufen 36". Der Horizont heisst jetzt Horizont, "Bindung"
    # nennen nur noch Tarif und Raten selbst.
    assert "24 Monate Bindung" not in o2_text
    assert ("Gerechnet über 24 Monate – der Tarif bindet 24 Monate, "
            "die Geräteraten laufen 36") in o2_text
    assert "Kosten der ersten 24 Monate" in o2_text
    assert "danach noch offen: 240,00 € (12 Geräteraten)" in o2_text


def test_die_tafel_spricht_katalog_d(tmp_path):
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    # E2: der Graph-Titel ist gefallen - die Etikett-Zusicherung des
    # Katalogs D lebt im ANTWORT-SATZ: er nennt TCO-24 aufgeloest ("über
    # 24 Monate (TCO-24)"), und kein "TCO-36" steht in der Tafel.
    antwort = tafel.select_one(".gr-zr-antwort")
    assert antwort is not None, "der Antwort-Satz fehlt"
    assert "über 24 Monate (TCO-24)" in \
        " ".join(antwort.get_text(" ", strip=True).split())
    kopie = BeautifulSoup(str(tafel), "html.parser")
    for d in kopie.select("details.gr-zr-rechnung"):
        d.decompose()
    tafel_text = kopie.get_text(" ")
    assert "TCO-24" in tafel_text and "TCO-36" not in tafel_text \
        and "Gesamtkosten" not in tafel_text
    # Das Modell nennt der Titel der Bündel-Tabelle (der eigene Modell-
    # Titelblock ist mit der Zeitreihe gefallen).
    titel = tafel.select_one("#gr-bnd-titel")
    assert titel is not None and \
        "Apple iPhone 15 128 GB" in titel.get_text(strip=True)
    # O2 (11.09.2026): Sortier- und Anbieterfilter-Controls sind entfallen
    # (§4 Entscheidung 3: bei 4-7 Zeilen je Bandliste erübrigen sie sich) -
    # die Zeilen stehen serverseitig nach TCO-24.
    assert tafel.select_one("select[data-sortiere]") is None
    assert tafel.select_one("select[data-anbieterfilter]") is None
    # Und Jede Zeile trägt ihr TCO-24-Etikett mit der Zahl.
    for zelle in tafel.select("#gr-bndliste .gr-bnd-tco"):
        text = zelle.get_text(" ", strip=True)
        assert "€" in text and "TCO-24" in text, text
    # Ratenzeile: "X € in 36 Raten" - die Summe aus der Kennzahl.
    o2 = tafel.select_one('.gr-bnd[data-anbieter="o2"][data-zustand="neu"]')
    bau = " ".join(o2.select_one(".gr-kk-bau").get_text(" ", strip=True).split())
    assert "720,00 € in 36 Raten à 20,00 €" in bau
    # Kein "(0 %)" auf einer TCO-Zeile: der Zinssatz ist dort nicht gemessen.
    assert "(0 %)" not in tafel.get_text(" ")


def test_die_buendelkarte_nennt_die_wahre_dauer_und_die_richtigen_raten(tmp_path):
    """S-Q4 (09.09.2026): die BAU-Zeile einer 1&1-Karte nennt die DAUER der
    Monatszahlung - 36 Monate, vorher stand der Rechnungshorizont 24 darueber
    und las sich als "zahlst du 24 Monate lang" - und sagt mit der Leitzahl,
    dass die TCO-24 nur 24 davon enthaelt. Was nach 24 Monaten offen ist,
    sind auf DIESER Karte Monatsraten aus Tarif und Geraet zusammen; die
    aufgeteilt erhobene o2-Karte daneben sagt weiterhin Geräteraten. Der
    Fall `raten_laufzeit < laufzeit` (Klammerteil wuerde Unsinn drucken)
    ist durch die Bedingung `>` im Template ausgeschlossen - hier steht
    er als Gegenprobe: 36 > 24 druckt, und NUR dann."""
    s = _baue(tmp_path, eins_und_eins=True)
    eins = s.select_one('#tafel-tco .gr-bnd[data-anbieter="1&1"]')
    assert eins is not None, "die Fixture muss die 1&1-Karte liefern"
    bau = " ".join(eins.select_one(".gr-kk-bau").get_text(" ", strip=True).split())
    assert bau == ("monatlich 44,99 € für Tarif und Gerät zusammen · "
                   "36 Monate (24 davon in der TCO-24)")
    eins_text = " ".join(eins.get_text(" ", strip=True).split())
    assert "danach noch offen: 539,88 € (12 Monatsraten)" in eins_text
    assert "Geräteraten" not in eins_text
    # Die o2-Karte (tarif_monatlich + geraet_monatsrate getrennt erhoben)
    # behaelt "Geräteraten" - zwei Karten, zwei wahre Woerter.
    o2 = s.select_one('#tafel-tco .gr-bnd[data-anbieter="o2"][data-zustand="neu"]')
    o2_text = " ".join(o2.get_text(" ", strip=True).split())
    assert "danach noch offen: 240,00 € (12 Geräteraten)" in o2_text


def test_die_buendelkarte_nennt_einmalzahlung_und_bereitstellung(tmp_path):
    """S2-C (09.09.2026): die BAU-Zeile einer 1&1-Karte nennt die Geräte-
    Einmalzahlung und die Bereitstellungsgebühr, wo 1&1 sie bis dahin
    verschwieg - als eigene Posten hinter dem Monatsbetrag, klein und in
    derselben Zeile, kein Redesign. Die Werte sind die der echten
    iPhone-Fixture (360,00/39,90, siehe test_geraete_buendel_einsundeins).

    Die Leitzahl rechnet BEIDE mit - sonst wäre die Zahl neben der Zeile
    eine zweite Rechnung für dieselbe Karte: 24 x 44,99 + 360 + 39,90
    = 1.479,66 €."""
    s = _baue(tmp_path, eins_und_eins=True,
              einmalzahlung=360.0, anschlusspreis=39.9)
    eins = s.select_one('#tafel-tco .gr-bnd[data-anbieter="1&1"]')
    assert eins is not None, "die Fixture muss die 1&1-Karte liefern"
    bau = " ".join(eins.select_one(".gr-kk-bau").get_text(" ", strip=True).split())
    assert bau == ("monatlich 44,99 € für Tarif und Gerät zusammen · "
                   "36 Monate (24 davon in der TCO-24) · "
                   "Gerät einmalig 360,00 € · Anschlusspreis 39,90 €")
    text = " ".join(eins.get_text(" ", strip=True).split())
    assert "TCO-24 1.479,66 €" in text
    # Ohne die Felder druckt KEINER von beiden - die Alt-Zeile steht exakt
    # in test_die_buendelkarte_nennt_die_wahre_dauer_und_die_richtigen_raten
    # (derselbe _baue-Aufruf ohne die zwei Parameter); die offene
    # Einmalzahlung steht als benannte Luecke im Rechenweg, nicht als 0,00
    # in der Finanzzeile.
