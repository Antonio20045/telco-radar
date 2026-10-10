"""Katalog D auf der TCO-Tafel (QA-Befunde S2, S4, S12 vom 04.09.2026).

Dieselbe Fixture wie `test_geraete_tco_zustand._baue` (geraete_db.json,
geraete_tco.json, tarife.jsonl, geraete_preise.jsonl, drei Konfigdateien in
tmp_path). Gemessen wird am gerenderten HTML, weil die Woerter dort stehen.
"""

from __future__ import annotations

from bs4 import BeautifulSoup
from test_geraete_tco_zustand import _baue, _modell, vorlage_text

from telco_radar.report import geraete_tco_grafik as grafik
from telco_radar.report import geraete_tco_karten as karten


def test_der_hersteller_steht_nicht_zweimal_im_titel():
    assert karten.titel("Xiaomi", "Xiaomi 17 512 GB") == "Xiaomi 17 512 GB"
    assert (
        karten.titel("Nothing", "Nothing Phone (3) 256 GB")
        == "Nothing Phone (3) 256 GB"
    )
    assert karten.titel("Apple", "iPhone 15 128 GB") == "Apple iPhone 15 128 GB"
    assert karten.titel("", "iPhone 15 128 GB") == "iPhone 15 128 GB"
    assert _modell()["titel"] == "Apple iPhone 15 128 GB"


def test_das_euro_delta_steht_am_g1_balken():
    """S4 / C.1: dieselbe Zahl wie auf der Karte, in der Grafik."""
    modell = _modell()
    neu = next(
        k for k in modell["karten"] if k["anbieter"] == "o2" and k["zustand"] == "neu"
    )
    svg = grafik.balken(modell)
    assert neu["delta"]["guenstiger"]
    erwartet = (
        f'<tspan class="gr-g1-delta">−{grafik.euro(neu["delta"]["abstand"])}</tspan>'
    )
    assert erwartet in svg
    assert svg.count("gr-g1-delta") == 1


def test_die_referenzzeile_behauptet_keine_36_monate(tmp_path):
    """Ticket TCO24-1 (08.09.2026): die Leitzahl ist auf der ganzen Seite
    IMMER ueber 24 Monate gerechnet (AUFTRAG_GERAETESEITE.md §3, "Immer
    24 Monate") - kein Angebot traegt mehr eine variable Bindung als
    Vergleichshorizont, und keine Referenzzeile rechnet mehr ueber ein
    fremdes Fenster. Seit A1 (20.09.2026) heisst sie "Kosten über
    24 Monate" und rechnet ALLE Geräteraten hinein.

    O2 (11.09.2026): die Karte ist eine Tabellenzeile - die Zeile führt
    mit der Leitzahl (wie der Graph über ihr), der Gerätepreis ohne
    Vertrag steht in der eigenen Spalte, Ø/Monat und der Rechenweg im
    Aufklapper.

    Datenkonzept Geräte Schritt 2: die o2-Zeile der Fixture trägt 24 Raten,
    gerechnet über H = 24 Monate; eine Restschuld nach Monat 24 gibt es nicht
    mehr, alle Raten liegen im Zeitraum der Zahl.
    """
    s = _baue(tmp_path)
    ref = s.select_one('#tafel-tco .gr-bnd[data-anbieter="Vodafone"]')
    assert ref.select_one(".gr-kk-marke").get_text(strip=True) == "Referenzrechnung"
    assert "1.428,70 €" in ref.select_one(".gr-bnd-tco").get_text()
    assert "Kosten über 24 Monate" in ref.select_one(".gr-bnd-tco").get_text()
    assert "709,90 €" in ref.select_one(".gr-bnd-bar").get_text()
    assert ref["data-laufzeit"] == "24"
    text = vorlage_text(ref)
    assert "Kosten über 24 Monate 1.428,70 €" in text
    assert "36 Monate" not in text
    assert "TCO-36" not in text
    assert "24 Monate Tarifbindung; das Gerät ist bar gekauft und bindet nicht" in text
    o2 = s.select_one('#tafel-tco .gr-bnd[data-anbieter="o2"][data-zustand="neu"]')
    assert "1.120,75 €" in o2.select_one(".gr-bnd-tco").get_text()
    assert "709,00 €" in o2.select_one(".gr-bnd-bar").get_text()
    o2_text = vorlage_text(o2)
    assert "TCO-36" not in o2_text and "36 Monate Bindung" not in o2_text
    assert "24 Monate Bindung" not in o2_text
    assert "Gerechnet über 24 Monate. Enthalten sind" in o2_text
    assert "Kosten der ersten 24 Monate" not in o2_text
    assert "auch alle Geräteraten der eigenen Laufzeit" in o2_text
    assert "offener Betrag" not in o2_text
    assert "danach noch offen" not in o2_text


def test_die_tafel_spricht_katalog_d(tmp_path):
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    antwort = tafel.select_one(".gr-zr-antwort")
    assert antwort is not None, "der Antwort-Satz fehlt"
    assert "Kosten über 24 Monate" in " ".join(
        antwort.get_text(" ", strip=True).split()
    )
    kopie = BeautifulSoup(str(tafel), "html.parser")
    for d in kopie.select("details.gr-zr-rechnung"):
        d.decompose()
    tafel_text = kopie.get_text(" ")
    assert (
        "Kosten über 24 Monate" in tafel_text
        and "TCO-24" not in tafel_text
        and "TCO-36" not in tafel_text
        and "Gesamtkosten" not in tafel_text
    )
    titel = tafel.select_one("#gr-bnd-titel")
    assert titel is not None and "Apple iPhone 15 128 GB" in titel.get_text(strip=True)
    assert tafel.select_one("select[data-sortiere]") is None
    assert tafel.select_one("select[data-anbieterfilter]") is None
    for zelle in tafel.select("#gr-bndliste .gr-bnd-tco"):
        text = zelle.get_text(" ", strip=True)
        assert "€" in text and "Kosten über 24 Monate" in text, text
    o2 = tafel.select_one('.gr-bnd[data-anbieter="o2"][data-zustand="neu"]')
    bau = vorlage_text(o2.select_one(".gr-kk-bau"))
    assert "720,00 € in 24 Raten à 30,00 €" in bau
    assert "(0 %)" not in vorlage_text(tafel)


def test_die_buendelkarte_nennt_die_wahre_dauer_und_die_richtigen_raten(tmp_path):
    """S-Q4 (09.09.2026): die BAU-Zeile einer 1&1-Karte nennt die DAUER der
    Monatszahlung - 36 Monate, vorher stand der Rechnungshorizont 24 darueber
    und las sich als "zahlst du 24 Monate lang". Seit A1 (20.09.2026)
    enthaelt die Leitzahl ALLE 36 Monate - die Kappungsklammer "(24 davon
    in der TCO-24)" ist gefallen, die Pflichtzeile darunter sagt den
    offenen Rest. Was nach 24 Monaten offen ist, sind auf DIESER Karte
    Monatsraten aus Tarif und Geraet zusammen; die aufgeteilt erhobene
    o2-Karte daneben sagt weiterhin Geräteraten.

    Antonio 10.10.2026: 1&1 wird nur über 24 Monate verglichen. Die Bau-Zeile
    nennt weiter die 36 Monate der Monatszahlung, gerechnet sind 24 Beträge
    und die Ablöse danach.

    Datenkonzept Geräte Schritt 2: die Zahl rechnet über H = 36 Monate, einen
    offenen Rest gibt es nicht mehr. Ohne gemessene Gerätezuzahlung und
    Anschlusspreis trägt die 1&1-Zeile keine Zahl, sondern die benannte
    Lücke - deshalb setzt die Fixture beide (Gegenprobe darunter)."""
    s = _baue(tmp_path, eins_und_eins=True, einmalzahlung=360.0, anschlusspreis=39.9)
    eins = s.select_one('#tafel-tco .gr-bnd[data-anbieter="1&1"]')
    assert eins is not None, "die Fixture muss die 1&1-Karte liefern"
    bau = vorlage_text(eins.select_one(".gr-kk-bau"))
    assert bau.startswith("monatlich 44,99 € für Tarif und Gerät zusammen · 36 Monate")
    eins_text = vorlage_text(eins)
    assert "gerechnet 24 Monate, dann Ablöse 360,00 €" in bau
    assert "Gerechnet über 24 Monate" in eins_text
    assert "auch die Ablöse nach Monat 24" in eins_text
    assert "auch alle Monatsraten der eigenen Laufzeit" not in eins_text
    assert "danach noch offen" not in eins_text
    assert "Geräteraten" not in eins_text
    assert "davon in der" not in eins_text, "die Kappungsklammer ist tot"
    o2 = s.select_one('#tafel-tco .gr-bnd[data-anbieter="o2"][data-zustand="neu"]')
    o2_text = vorlage_text(o2)
    assert "danach noch offen" not in o2_text
    assert "auch alle Geräteraten der eigenen Laufzeit" in o2_text

    ohne = _baue(tmp_path / "ohne-einmal", eins_und_eins=True)
    luecke = ohne.select_one('#tafel-tco .gr-bnd[data-anbieter="1&1"]')
    assert "gr-bnd--leer" in luecke["class"] and not luecke.get("data-gesamt")
    assert "Einmalzahlung bei Kündigung" in vorlage_text(
        luecke.select_one(".gr-kk-luecke")
    )


def test_die_buendelkarte_nennt_einmalzahlung_und_bereitstellung(tmp_path):
    """S2-C (09.09.2026): die BAU-Zeile einer 1&1-Karte nennt die Geräte-
    Einmalzahlung und die Bereitstellungsgebühr, wo 1&1 sie bis dahin
    verschwieg - als eigene Posten hinter dem Monatsbetrag, klein und in
    derselben Zeile, kein Redesign. Die Werte sind die der echten
    iPhone-Fixture (360,00/39,90, siehe test_geraete_buendel_einsundeins).

    Die Leitzahl rechnet BEIDE mit - sonst wäre die Zahl neben der Zeile
    eine zweite Rechnung für dieselbe Karte: 36 x 44,99 + 360 + 39,90
    = 2.019,54 € (alle 36 Monate, A1). Seit 10.10.2026 (Antonio: 1&1 nur über
    24 Monate) 24 x 44,99 + 360 Ablöse + 39,90 = 1.479,66 €."""
    s = _baue(tmp_path, eins_und_eins=True, einmalzahlung=360.0, anschlusspreis=39.9)
    eins = s.select_one('#tafel-tco .gr-bnd[data-anbieter="1&1"]')
    assert eins is not None, "die Fixture muss die 1&1-Karte liefern"
    bau = vorlage_text(eins.select_one(".gr-kk-bau"))
    assert bau == (
        "monatlich 44,99 € für Tarif und Gerät zusammen · "
        "36 Monate · "
        "gerechnet 24 Monate, dann Ablöse 360,00 € · Anschlusspreis 39,90 €"
    )
    text = vorlage_text(eins)
    assert "1.479,66 € Kosten über 24 Monate" in text
    assert "Kosten über 36 Monate" not in text


def test_nur_der_barpreis_traegt_das_ohne_vertrag_etikett(tmp_path):
    """28.09.2026: mobil fehlt der Spaltenkopf, deshalb steht vor dem
    Gerätepreis ohne Vertrag sein Name (CSS an `gr-bnd-bar--wert`). Eine
    Finanzierungssumme darf diese Klasse nicht tragen, sonst läse man
    „ohne Vertrag 613,00 € Finanzierung gesamt"."""
    s = _baue(tmp_path)
    zellen = s.select("#tafel-tco .gr-bnd .gr-bnd-bar")
    fin = [z for z in zellen if "Finanzierung gesamt" in z.get_text()]
    bar = [
        z
        for z in zellen
        if "Finanzierung gesamt" not in z.get_text()
        and z.get_text(strip=True).endswith("€")
    ]
    assert fin and bar, [z.get_text(" ", strip=True) for z in zellen]
    assert all("gr-bnd-bar--wert" not in z["class"] for z in fin)
    assert all("gr-bnd-bar--wert" in z["class"] for z in bar)
