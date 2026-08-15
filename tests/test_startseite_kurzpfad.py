"""Der Kurzpfad und die Digest-Spalte: eine Achse, drei Zeilen, kein Auffuellen.

Auftrag vom 09.08.2026, nach einer Pruefung der Live-Seite vom 8. August.
Zwei Befunde, und sie haengen zusammen:

**Der Kurzpfad hat die Titelseite verdraengt.** Er stand mit fuenf
Eintraegen ueber dem Aufmacher, jeder Eintrag ein Absatz plus Belegzeile -
die Schlagzeile der Ausgabe begann erst darunter. Vier der fuenf Saetze
waren reine Konjunktiv-Ableitungen ("koennte pruefen", "muesste
nachschaerfen"), zwei laenger als 20 Woerter. Ein Kasten, der eine
Zeitungstitelseite aus dem ersten Bildschirm draengt, muss dafuer mehr
liefern als fuenf Vermutungen.

**Zwei Module behaupteten beide "das Wichtigste" und widersprachen sich.**
"Was wichtig ist" fuehrte zwei BREKO-Stellungnahmen zur TKG-Novelle
(`ctm_bezug` 2), die im Kasten daneben mit keinem Wort vorkamen - waehrend
alle vier Meldungen mit direktem Portfoliobezug (Stufe 3) in Bildpositionen
ohne Rubriknamen standen.

Die Reihenfolge im Test folgt der des Auftrags: erst die Aufnahme in den
Kurzpfad (`analyze/ctm.py`), dann seine Darstellung, dann die Achse der
Digest-Spalte - zuletzt als Regressionstest gegen die echte Ausgabe vom
8. August, die den Befund ausgeloest hat.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from telco_radar.analyze import ctm
from telco_radar.report import html
from telco_radar.report.html import render_site

REPO = Path(__file__).resolve().parents[1]
AUSGABE = "2026-08-08"


def _h(i: int, *, ctm_bezug: int, satz: str, relevance: int = 3,
       operator: str | None = None, title: str = "", summary: str = "") -> dict:
    return {"title": title or f"Meldung {i}", "summary": summary,
            "url": f"https://example.com/{i}", "operator": operator or f"Sender {i}",
            "relevance": relevance, "ctm_bezug": ctm_bezug, "ctm_satz": satz}


# ---------------------------------------------------------------- Aufnahme

def test_der_kurzpfad_nimmt_hoechstens_drei_zeilen():
    """Fuenf waren es, drei sind es. Die Zahl steht am Aufrufer (html.py),
    nicht in der Voreinstellung: die Mail hat viel Platz und wenig Gewicht,
    der Kasten auf der Titelseite umgekehrt."""
    hs = [_h(i, ctm_bezug=3, satz=f"Drückt unsere Preisuntergrenze um {i}0 Prozent.",
             operator=f"Sender {i}") for i in range(6)]
    assert len(ctm.zwei_minuten(hs, 3)) == 3


def test_stufe_zwei_ohne_zahl_kommt_nicht_hinein():
    """Die Aufnahmeregel. "Koennte das Einsteigersegment dominieren" ist
    weder pruefbar noch widerlegbar und kostet trotzdem die wertvollste
    Zeile der Seite."""
    ohne = _h(1, ctm_bezug=2,
              satz="Das könnte Vodafone zwingen, das eigene Portfolio nachzuschärfen.",
              title="Anbieter startet neuen Tarif",
              summary="Der Anbieter hat einen neuen Tarif angekündigt.")
    assert ctm.zwei_minuten([ohne], 3, nur_belegt=True) == []
    # Ohne die Verschaerfung bleibt es beim alten Verhalten - die Mail
    # nutzt denselben Aufruf und soll sich nicht mitaendern.
    assert ctm.zwei_minuten([ohne], 3) == [ohne]


def test_stufe_zwei_mit_zahl_aus_der_quelle_kommt_hinein():
    mit = _h(1, ctm_bezug=2,
             satz="Über 900 TV-Kanäle setzen unser Content-Bündel unter Druck.",
             title="Anbieter führt Übersicht mit über 900 Diensten an",
             summary="Die Übersicht listet mehr als 900 Kanäle.")
    assert ctm.zwei_minuten([mit], 3, nur_belegt=True) == [mit]


def test_eine_erfundene_zahl_ist_keine_zahl_aus_der_quelle():
    """Fail closed, dieselbe Richtung wie der Prueflauf: eine Zahl, die im
    Originaltext fehlt, macht den Satz nicht aufnahmefaehig, sondern
    unbrauchbar."""
    erfunden = _h(1, ctm_bezug=2,
                  satz="Über 900 TV-Kanäle setzen unser Content-Bündel unter Druck.",
                  title="Anbieter führt Übersicht an",
                  summary="Die Übersicht listet die Kanäle des Anbieters.")
    assert ctm.zwei_minuten([erfunden], 3, nur_belegt=True) == []


def test_eine_ziffer_im_modellnamen_ist_keine_zahl():
    """Der Fehler des ersten Anlaufs, an der echten Ausgabe gemessen: "Das
    Redmi 17C 5G koennte das Einsteigersegment dominieren" kam durch, weil
    "17" zweistellig ist und im Titel steht. Es ist nur keine Zahl, sondern
    ein Modellname - an der Ziffer klebt ein Buchstabe."""
    modell = _h(1, ctm_bezug=2,
                satz="Das Redmi 17C 5G könnte das Einsteigersegment dominieren.",
                title="Redmi 17C 5G vor Europa-Start",
                summary="Das Redmi 17C 5G kommt nach Europa.")
    assert ctm.zwei_minuten([modell], 3, nur_belegt=True) == []


def test_stufe_drei_braucht_keine_zahl():
    """Direkter Portfoliobezug ist die Aufnahme selbst - die Zahl ist die
    Ersatzanforderung fuer die Stufe darunter, nicht eine zweite Huerde."""
    direkt = _h(1, ctm_bezug=3,
                satz="Das trifft unsere Unlimited-Stufe unmittelbar im Heimatmarkt.")
    assert ctm.zwei_minuten([direkt], 3, nur_belegt=True) == [direkt]


def test_ein_zu_langer_satz_wird_verworfen_statt_gekuerzt():
    """Ein auf 20 Woerter geschnittener Folgerungssatz ist ein Halbsatz, und
    ein Halbsatz unter einem Quellenlink behauptet etwas, das die Quelle
    nicht sagt."""
    lang = _h(1, ctm_bezug=3, satz=" ".join(["Wort"] * 21) + ".")
    kurz = _h(2, ctm_bezug=3, satz=" ".join(["Wort"] * 20) + ".")
    assert ctm.zwei_minuten([lang, kurz], 3, max_woerter=20) == [kurz]


def test_kein_auffuellen_wenn_es_nur_einen_eintrag_gibt():
    """Gibt es nur einen, steht einer da. Die drei ist eine Obergrenze, kein
    Soll - aufgefuellt wuerde mit genau dem, was die Regel aussortiert."""
    hs = [_h(1, ctm_bezug=3, satz="Trifft unsere Unlimited-Stufe unmittelbar.")]
    hs += [_h(i, ctm_bezug=2, satz="Könnte uns langfristig betreffen.")
           for i in range(2, 9)]
    assert len(ctm.zwei_minuten(hs, 3, nur_belegt=True)) == 1


def test_ohne_einen_einzigen_eintrag_entfaellt_der_kasten():
    """Seine Abwesenheit ist selbst eine Aussage: diese Woche gab es nichts,
    das direkt ins Portfolio spielt."""
    hs = [_h(i, ctm_bezug=2, satz="Könnte uns langfristig betreffen.")
          for i in range(5)]
    assert ctm.zwei_minuten(hs, 3, nur_belegt=True) == []


# ------------------------------------------------------------- Darstellung

def baue_seite(tmp_path: Path, datum: str = AUSGABE) -> Path:
    """Rendert die ECHTE Ausgabe in einen eigenen Baum und liefert site/.

    Erfundene Meldungen taugen fuer die Aufnahmeregel, nicht fuer die Frage,
    was die Seite daraus macht. Nachgebaut wird deshalb der Pfadaufbau, den
    `render_site` erwartet: den Bildordner sucht es unter
    ``reports_dir.parent.parent/data/state/report_images``. Ohne ihn faende
    die Seite kein einziges Bild, jede Meldung waere gleich hoch - und ein
    Test ueber die Titelseite maesse eine Seite, die so nie ausgeliefert
    wird.

    Der Zustandsordner wird VERKNUEPFT, nicht kopiert: 325 Bilder je Test
    waeren teuer, und `render_site` liest dort nur (das Aufraeumen macht die
    Pipeline, nicht der Renderer). Geschrieben wird ausschliesslich nach
    site/ im tmp-Baum.
    """
    quelle = REPO / "data" / "reports" / f"{datum}.json"
    if not quelle.exists():
        pytest.skip(f"Ausgabe {datum} liegt nicht im Archiv")
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True)
    for endung in (".json", ".md"):
        auch = REPO / "data" / "reports" / f"{datum}{endung}"
        if auch.exists():
            shutil.copy(auch, reports / auch.name)
    (tmp_path / "data" / "state").symlink_to(REPO / "data" / "state")
    site = tmp_path / "site"
    render_site(site, reports, cfg=None)
    return site


def _render(tmp_path: Path, datum: str = AUSGABE) -> BeautifulSoup:
    seite = baue_seite(tmp_path, datum) / "index.html"
    return BeautifulSoup(seite.read_text(encoding="utf-8"), "html.parser")


def _kurzpfad_saetze(soup: BeautifulSoup) -> list[str]:
    saetze = []
    for zeile in soup.select(".kurzpfad-zeile"):
        satz = zeile.select_one(".kurzpfad-satz").get_text(" ", strip=True)
        beleg = zeile.select_one(".kurzpfad-beleg").get_text(" ", strip=True)
        saetze.append(satz.replace(beleg, "").strip())
    return saetze


def test_der_kasten_steht_in_der_spalte_nicht_ueber_der_seite(tmp_path):
    soup = _render(tmp_path)
    assert soup.select_one(".front-wichtig .kurzpfad") is not None
    # ... und nirgends sonst: eine zweite Fassung ausserhalb der Spalte
    # waere genau die Verdopplung, die hier abgeraeumt wurde.
    assert len(soup.select(".kurzpfad")) == 1


def test_jeder_eintrag_ist_eine_zeile_und_kein_absatz(tmp_path):
    soup = _render(tmp_path)
    zeilen = soup.select(".kurzpfad-zeile")
    assert zeilen, "die Ausgabe vom 8.8. hat einen Kurzpfad"
    for zeile in zeilen:
        assert len(zeile.select("p")) == 1
        assert not zeile.select("br")
    for satz in _kurzpfad_saetze(soup):
        assert len(satz.split()) <= 20, satz


def test_hoechstens_drei_eintraege_mit_quellenlink(tmp_path):
    soup = _render(tmp_path)
    zeilen = soup.select(".kurzpfad-zeile")
    assert 1 <= len(zeilen) <= 3
    for zeile in zeilen:
        assert zeile.select_one(".kurzpfad-beleg a")["href"].startswith("http")


def test_die_foliensatz_zeile_steht_am_fuss_des_berichts(tmp_path):
    """Zwischen Subnav und Titelseite las sie sich als achter
    Navigationspunkt - eine Datei zum Mitnehmen, die aussieht wie eine Seite
    zum Hingehen. Und sie kostete den Platz, um den es beim Rueckbau des
    Kurzpfads ging.

    Am Berichtsfuss steht sie ausserdem richtig: wer den Bericht gelesen
    hat, ist der, der ihn am Montag vortraegt."""
    soup = _render(tmp_path)
    zeile = soup.select_one(".folienlink")
    assert zeile is not None
    assert zeile.select_one("a")["href"].endswith(f"folien/{AUSGABE}.html")
    # Im Bericht, nicht davor.
    bericht = soup.select_one("#der-wochenbericht")
    assert bericht is not None and zeile in bericht.find_all(class_="folienlink")
    prosa = soup.select_one(".prose")
    html = str(soup)
    assert html.index(str(prosa)[:60]) < html.index(str(zeile)[:40])


def test_keine_meldung_steht_zweimal_in_der_rechten_spalte(tmp_path):
    """Kurzpfad und Digest-Spalte stehen untereinander und ziehen seit K2 aus
    derselben Sortierung. Ohne Sperre steht die stärkste Meldung als
    Kurzpfad-Zeile 1 und als „Was wichtig ist"-Zeile 1 direkt darunter -
    dasselbe „doppelt gemoppelt", das am 07.08.2026 die Ressortblöcke
    gekostet hat.

    Gebaut wird der Fall, statt auf ihn zu warten: in der Ausgabe vom
    8. August tritt er zufällig nicht auf, weil deren Stufe-3-Meldungen
    keinen geprüften Folgerungssatz mehr tragen.

    Der Aufbau ist der Fall, den es braucht, und er ist nicht beliebig: die
    Meldung mit dem Folgerungssatz hat KEIN Bild, drei andere haben eines.
    Damit besetzen die drei Aufmacher und zweite Reihe, und die vierte fällt
    bis in die Digest-Spalte durch - dort trifft sie auf sich selbst. Mit
    Bild wäre sie Aufmacher geworden, und der darf sie sein (siehe den Test
    darunter). Die Absender heißen bewusst verschieden: „Bild 1/2/3" wären
    dem Absenderdeckel als EIN Absender aufgefallen."""
    hs = []
    for i, name in enumerate(("Alpha", "Beta", "Gamma"), 1):
        h = _h(i, ctm_bezug=1, relevance=5, satz="", operator=name)
        h |= {"image": "b.jpg", "image_w": 1200, "image_h": 675}
        hs.append(h)
    hs.append(_h(9, ctm_bezug=3, relevance=4, operator="Deutsche Telekom",
                 satz="Drückt unsere Preisuntergrenze im Heimatmarkt deutlich."))
    hs += [_h(i, ctm_bezug=1, relevance=2, satz="", operator=f"Sender{i}")
           for i in range(10, 20)]
    for h in hs:
        h.setdefault("category", "Tarif/Pricing")

    gesperrt = [h["url"] for h in ctm.kurzpfad(hs)]
    assert gesperrt, "der Testfall braucht einen belegten Kurzpfad"
    # Die Gegenprobe im selben Test: ohne Sperre steht die Meldung zweimal.
    # Ohne sie wäre nicht zu sehen, ob die Zusicherung greift oder ob der
    # Fall gar nicht erst eintritt - genau so war dieser Test zuerst gebaut,
    # und er war grün, bevor er etwas prüfte.
    ohne = html._titelseite(hs, None)
    assert {h["url"] for h in ohne["wichtig"]} & set(gesperrt), \
        "der Testfall löst die Dublette gar nicht aus"

    front = html._titelseite(hs, None, belegt=gesperrt)
    doppelt = {h["url"] for h in front["wichtig"]} & set(gesperrt)
    assert not doppelt, doppelt


def test_der_aufmacher_darf_seinen_folgerungssatz_behalten():
    """Die Gegenprobe zur Sperre oben, und die Grenze, an der sie endet.

    Aufmacher und Kurzpfad sind zweierlei - der eine zeigt Schlagzeile und
    Bild, der andere den Satz. Sperrte man belegte Meldungen von der ganzen
    Seite statt nur aus der Spalte, könnte die Meldung mit dem besten
    Folgerungssatz nie mehr Aufmacher werden, und die Marke „Was das für uns
    heißt" verschwände. Ein Test in test_seiten_zahlen.py hält sie fest;
    dieser hier hält fest, WARUM die Sperre eng gefasst ist."""
    stark = _h(1, ctm_bezug=3, relevance=5, operator="Deutsche Telekom",
               satz="Drückt unsere Preisuntergrenze im Heimatmarkt deutlich.")
    stark |= {"image": "b.jpg", "image_w": 1200, "image_h": 675,
              "category": "Tarif/Pricing"}
    front = html._titelseite([stark], None, belegt=[stark["url"]])
    assert front["aufmacher"] is not None
    assert front["aufmacher"]["url"] == stark["url"]


def test_mail_und_seite_zeigen_dieselben_zeilen():
    """Eine Mail, die etwas anderes hervorhebt als die Seite, auf die sie
    verlinkt, ist schlimmer als keine Mail - so steht es im Docstring von
    `versand.zwei_minuten_zeilen`.

    Am 09.08.2026 war die Zusicherung kurz gebrochen: die Seite bekam drei
    Zeilen mit Aufnahmeregel, die Mail behielt fünf ohne. Gemessen an der
    Ausgabe vom 8. August stand danach genau EINE der drei Seitenzeilen auch
    in der Mail. Beide holen ihren Zuschnitt jetzt aus `ctm.kurzpfad()`."""
    from telco_radar import versand
    daten = json.loads((REPO / "data" / "reports" / f"{AUSGABE}.json")
                       .read_text(encoding="utf-8"))
    seite = [h["url"] for h in ctm.kurzpfad(html._flatten(daten))]
    mail = [h["url"] for h in versand.zwei_minuten_zeilen(daten)]
    assert seite and mail == seite


# -------------------------------------------------------------- Die Achse

def test_die_digest_spalte_folgt_der_ctm_achse(tmp_path):
    """Dieselbe Achse wie der Kurzpfad: `ctm_bezug` vor Prioritaet.

    Der Schluessel ist `schlagzeile`, und den traegt die Berichtsdatei NICHT
    - sie kennt `headline` und `title`, `_flatten()` rechnet daraus die
    Schlagzeile der Seite. Beim ersten Anlauf stand hier ein Lookup gegen
    die Rohdatei: er traf 0 von 7 Zeilen, `stufen` blieb leer, und
    `[] == sorted([])` ist wahr. Der Test war gruen und pruefte nichts -
    nachgewiesen, indem die Vergabereihenfolge zurueckgedreht wurde und er
    gruen blieb. Die Zeile `assert len(stufen) == len(gezeigt)` ist die
    Lehre daraus: ein Lookup, der ins Leere geht, muss auffallen."""
    soup = _render(tmp_path)
    daten = json.loads((REPO / "data" / "reports" / f"{AUSGABE}.json")
                       .read_text(encoding="utf-8"))
    bezug = {h["schlagzeile"]: int(h.get("ctm_bezug") or 0)
             for h in html._flatten(daten)}
    gezeigt = [z.select_one(".wichtig-titel").get_text(strip=True)
               for z in soup.select(".wichtig-zeile")]
    assert gezeigt, "die Spalte ist leer"
    stufen = [bezug[t] for t in gezeigt if t in bezug]
    assert len(stufen) == len(gezeigt), \
        f"{len(gezeigt) - len(stufen)} Zeilen nicht zugeordnet - falscher Schlüssel?"
    assert stufen == sorted(stufen, reverse=True), list(zip(gezeigt, stufen))


def test_breko_steht_nicht_vor_den_meldungen_mit_hoeherem_ctm_bezug(tmp_path):
    """Der Regressionstest zum Befund, gegen die Ausgabe, die ihn ausgeloest
    hat. Am 08.08.2026 fuehrten die zwei BREKO-Stellungnahmen zur TKG-Novelle
    (Stufe 2) die Spalte an, obwohl vier Meldungen der Stufe 3 in derselben
    Ausgabe standen.

    Geprueft wird die Bedingung, nicht der Name: BREKO darf sehr wohl weit
    oben stehen, sobald die Meldungen mit hoeherem Bezug ihren Platz haben -
    nur nicht DAVOR.

    Seit dem 15.08.2026 haben sie ihn eine Stufe hoeher: die Bildstufen
    ziehen wieder vor der Spalte, und die vier Stufe-3-Meldungen dieser
    Ausgabe stehen damit als Aufmacher, zweite und dritte Reihe oberhalb
    davon - nicht als Textzeile daneben. Was hier bis dahin zusaetzlich
    stand ("nicht zu zweit an der Spitze"), war eine Namenspruefung fuer
    genau diesen Fall und ist entfallen: die zwei Stellungnahmen sind mit
    Prioritaet 5 und 4 die bestbewerteten Meldungen, die uebrig bleiben,
    und der Absenderdeckel (`_MAX_JE_ABSENDER` = 2) laesst zwei zu. Die
    Zusicherung, die den Befund abdeckt, steht darunter und ist strenger
    geworden.

    Gemessen wird an `_titelseite()`, nicht an der gerenderten Datei, und das
    ist kein Bequemlichkeitsschnitt: `render_site()` streicht jeden
    `image`-Verweis, zu dem keine Datei mehr im Bildordner liegt
    (report/html.py). Welche Meldung ein Bild HAT, entscheidet aber, welche
    Gewichtsstufe sie abraeumt - der Test haette also am Inhalt eines
    Ordners gehangen, den ein Aufraeumlauf jederzeit beschneiden darf. Genau
    so ist er beim Schreiben einmal gekippt. Die Bildbreite kommt hier aus
    dem Bericht selbst und ist damit so stabil wie die Ausgabe."""
    daten = json.loads((REPO / "data" / "reports" / f"{AUSGABE}.json")
                       .read_text(encoding="utf-8"))
    highlights = html._flatten(daten)
    front = html._titelseite(
        highlights,
        html._faden(highlights,
                    html._fuehrende_saetze(daten.get("briefing_md") or "")))

    stufe3 = [h for h in highlights if int(h.get("ctm_bezug") or 0) > 2]
    assert stufe3, "ohne Stufe-3-Meldungen prueft dieser Test nichts"

    spalte = front["wichtig"]
    absender = [(h.get("operator") or h.get("source_label") or "")
                for h in spalte]
    titel = [h.get("schlagzeile") or h.get("title") for h in spalte]

    # Der Befund vom 8. August, in seiner strengeren Fassung: keine
    # BREKO-Zeile steht vor einer Meldung mit hoeherem CTM-Bezug.
    stufen = [int(h.get("ctm_bezug") or 0) for h in spalte]
    for platz, ab in enumerate(absender):
        if ab != "BREKO":
            continue
        assert all(s <= stufen[platz] for s in stufen[platz + 1:]), \
            f"BREKO auf Platz {platz + 1} vor {titel[platz + 1:]}"

    # Und der Grund, warum BREKO diese Spalte anfuehren DARF: die Meldungen
    # mit direktem Portfoliobezug stehen nicht daneben, sondern darueber -
    # in den Bildstufen der Hauptspalte. Ohne diese Zeile liesse sich der
    # Test auch dadurch erfuellen, dass die Stufe-3-Meldungen gar nicht
    # mehr auf der Titelseite vorkommen.
    oberhalb = {h.get("url") for h in
                ([front["aufmacher"]] if front["aufmacher"] else [])
                + list(front["zwei"]) + list(front["vier"])}
    fehlt = [h.get("schlagzeile") for h in stufe3
             if h.get("url") not in oberhalb
             and h.get("url") not in {s.get("url") for s in spalte}]
    assert not fehlt, f"Stufe-3-Meldung ohne Platz auf der Titelseite: {fehlt}"
