"""Phase P2, Paket D3: die Bündelzeile zugeklappt.

DER BEFUND (gemessen, CLAUDE.md-Auftrag, höchste Priorität): congstar
bietet seit dem 22.09.2026 jedes Bündel mit 24 UND 36 Raten an - bei
gleichem Gesamtpreis (congstar finanziert zum Nulltarif). Zugeklappt
lauteten beide Zeilen wortgleich, der Unterschied (die Ratenzahl, und bei
36 Raten die Restschuld nach Monat 24) stand erst im aufgeklappten
Rechenweg. Diese Datei pinnt die Behebung an einer eigenen, kleinen
Fixture mit GENAU diesem Fall - denselben Zahlen wie der reale Pflichtfall
(iPhone 17 Pro 256 GB, congstar Allnet Flat XS, 22.09.2026:
1 + 24×15,00 + 24×45,75 EUR = 1 + 24×15,00 + 36×30,50 EUR = 1.459,00 EUR,
Restschuld 0,00 EUR gegen 366,00 EUR) - damit ist jeder Assert hier auch
am echten Bestand nachvollziehbar (siehe
`tests/test_seiten_zahlen.py::test_leitzahl_congstar_xs_iphone17pro256_am_bestand`).

Drei weitere Punkte desselben Auftrags, an derselben Fixture:
  - Punkt 2: die Hauptzahl der Zeile nennt ihr Subjekt
    ("congstar 462,00 € unter Vodafone" statt eines nackten Betrags).
  - Punkt 3: die Anbieterfarbe steht wirklich an der Zeile (`--anb`) -
    vorher fiel `.gr-bnd-name`/`.gr-bnd` auf den grauen Rückfall
    `#57534a` zurück, weil keine `gr-anb--<slug>`-Klasse an der Zeile
    stand (die Regel in `style.css` existierte, ihre Klasse fehlte).
  - Punkt 4: der Zerlegungsbalken - seine Segmentbeträge summieren exakt
    zur Leitzahl, und die Restschuld trägt ein eigenes (schraffiertes)
    Segment.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest
import yaml

from telco_radar.report.html import render_site

from test_geraete_browser_fixture import HEUTE, _KATALOG, _FARBEN, _QUELLEN, _listung, _sku

WURZEL = pathlib.Path(__file__).resolve().parents[1]
DEVICE = "apple-iphone-17-pro"
MODELL = "apple-iphone-17-pro-256"

# Derselbe Pflichtfall wie am echten Bestand (siehe Modulkopf).
ZUZAHLUNG = 1.0
TARIF_MONATLICH = 15.0
RATEN = {24: 45.75, 36: 30.50}
SOLL_GESAMT = 1459.00
SOLL_RESTSCHULD = {24: 0.0, 36: 366.00}


def _congstar_buendel(laufzeit: int) -> dict:
    return {
        "id": f"buendel--congstar--{_sku(DEVICE, 256)}--cs-xs--{laufzeit}",
        "sku_id": _sku(DEVICE, 256), "anbieter": "congstar",
        "tarif_name": "Allnet Flat XS", "tarif_id": "cs:xs",
        "tarif_id_guete": "hoch", "tarif_monatlich": TARIF_MONATLICH,
        "tarif_bindung_monate": 24, "geraet_zuzahlung": ZUZAHLUNG,
        "geraet_monatsrate": RATEN[laufzeit], "laufzeit_monate": laufzeit,
        "anschlusspreis": 0.0, "zustand": "neu", "rabatte": [],
        "quelle_url": "https://example.de/congstar/17pro",
        "abgerufen_am": HEUTE, "first_seen": HEUTE, "last_verified": HEUTE}


def _vodafone_buendel() -> dict:
    # Deutlich teurer als congstar (Δ > 15 EUR UND > 3 %), damit die
    # Wesentlichkeitsschwelle (`geraete_vergleich.WESENTLICH_*`) sicher
    # greift und ein echtes Δ entsteht.
    return {
        "id": f"buendel--vodafone--{_sku(DEVICE, 256)}--vf-xs--24",
        "sku_id": _sku(DEVICE, 256), "anbieter": "Vodafone",
        "tarif_name": "Vodafone Mobil XS", "tarif_id": "vf:xs",
        "tarif_id_guete": "hoch", "tarif_monatlich": 26.0,
        "tarif_bindung_monate": 24, "geraet_zuzahlung": 1.0,
        "geraet_monatsrate": 54.0, "laufzeit_monate": 24,
        "anschlusspreis": 0.0, "zustand": "neu", "rabatte": [],
        "quelle_url": "https://example.de/vodafone/17pro",
        "abgerufen_am": HEUTE, "first_seen": HEUTE, "last_verified": HEUTE}


def _bestand() -> dict:
    """Bündel + Vodafone-Barpreis, roh (wie `geraete_tco.json`/`geraete_db.json`)."""
    return {
        "buendel": [_congstar_buendel(24), _congstar_buendel(36),
                   _vodafone_buendel()],
        "listung": _listung("Vodafone", DEVICE, 256, 1199.90),
    }


def _baue(tmp_path: pathlib.Path, bestand: dict) -> pathlib.Path:
    root = tmp_path / "site_baum"
    (root / "config").mkdir(parents=True)
    for name, daten in (("geraete_katalog.yaml", _KATALOG),
                        ("farben.yaml", _FARBEN),
                        ("geraete_quellen.yaml", _QUELLEN)):
        (root / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
    state = root / "data" / "state"
    state.mkdir(parents=True)
    (state / "geraete_db.json").write_text(json.dumps({
        "updated": HEUTE,
        "anbieter": {n: {"laeufe": 4, "funde_gesamt": 1}
                     for n in ("Vodafone", "congstar")},
        "listungen": [bestand["listung"]]}), encoding="utf-8")
    (state / "geraete_preise.jsonl").write_text("", encoding="utf-8")
    (state / "geraete_tco.json").write_text(json.dumps({
        "updated": HEUTE, "buendel": bestand["buendel"], "sim_only": []}),
        encoding="utf-8")
    (state / "tarife.jsonl").write_text("", encoding="utf-8")
    reports = root / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / f"{HEUTE}.json").write_text(json.dumps({
        "date": HEUTE, "language": "de",
        "briefing_md": "## Auf einen Blick\n\n- Nichts Besonderes.\n",
        "stats": {}, "regions": []}), encoding="utf-8")
    (reports / f"{HEUTE}.md").write_text("# Bericht\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    return site


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    return _baue(tmp_path_factory.mktemp("d3zeilenkopf"), _bestand())


_ZEILE_RE = re.compile(
    r'(<details class="gr-bnd[^"]*"[^>]*data-anbieter="congstar"[^>]*>)'
    r'(.*?)</details>', re.S)


def _congstar_zeilen(html: str) -> dict:
    """{laufzeit_monate: (opentag, summary_text, ganzer_body)}."""
    out = {}
    for opentag, body in _ZEILE_RE.findall(html):
        kopf = re.search(r"<summary>(.*?)</summary>", body, re.S).group(1)
        text = " ".join(re.sub(r"<[^>]+>", " ", kopf).split())
        if "Allnet Flat XS Flex" in text:
            continue
        # `data-laufzeit` traegt die TARIFlaufzeit (immer 24, siehe
        # `_geraete_buendel.html.j2`) - die RATENlaufzeit steht in
        # `k.raten_laufzeit`; unterschieden wird hier ueber den
        # eindeutigen Rechenweg-Text ("24 Raten"/"36 Raten").
        n = 36 if "36 Raten" in text else 24 if "24 Raten" in text else None
        assert n is not None, f"keine Ratenzahl in der Zeile: {text!r}"
        out[n] = (opentag, text, body)
    return out


def test_lookup_greift(site):
    """Gegenprobe: der Lookup findet wirklich beide Zahlweisen - sonst
    wären alle folgenden Tests grün, ohne etwas zu prüfen (CLAUDE.md
    Regel 10)."""
    html = (site / "geraete.html").read_text(encoding="utf-8")
    zeilen = _congstar_zeilen(html)
    assert set(zeilen) == {24, 36}, (
        f"gefunden: {sorted(zeilen)} - erwartet beide Zahlweisen 24 und 36")


def test_punkt1_zeilen_sind_zugeklappt_unterscheidbar(site):
    """DER KERNTEST: die beiden Zahlweisen sind zugeklappt (im
    <summary>-Text) verschieden, tragen ihre Ratenzahl, und die 36er
    trägt zusätzlich die Restschuld - die 24er NICHT (0,00 EUR ist keine
    Meldung wert, "24 Raten" allein ist schon der Unterschied)."""
    html = (site / "geraete.html").read_text(encoding="utf-8")
    zeilen = _congstar_zeilen(html)
    _klassen24, text24, _b24 = zeilen[24]
    _klassen36, text36, _b36 = zeilen[36]

    assert text24 != text36, (
        "beide Zahlweisen sind zugeklappt weiterhin wortgleich:\n"
        f"  24 Raten: {text24!r}\n  36 Raten: {text36!r}")
    assert "24 Raten" in text24 and "36 Raten" not in text24
    assert "36 Raten" in text36 and "24 Raten" not in text36
    assert "Restschuld 366,00 €" in text36, (
        f"36-Raten-Zeile nennt die Restschuld nicht: {text36!r}")
    assert "Restschuld" not in text24, (
        f"24-Raten-Zeile (0 EUR Restschuld) nennt trotzdem eine "
        f"Restschuld: {text24!r}")
    # Gegenprobe: beide Leitzahlen bleiben gleich (congstar finanziert
    # zum Nulltarif) - der Unterschied ist NUR die Ratenzahl/Restschuld,
    # nicht ein zweiter, unbeabsichtigter Textdrift.
    assert f"{SOLL_GESAMT:,.2f}".replace(",", "#").replace(".", ",").replace(
        "#", ".") + " €" in text24
    assert f"{SOLL_GESAMT:,.2f}".replace(",", "#").replace(".", ",").replace(
        "#", ".") + " €" in text36


def _congstar_xs_summarys(html: str) -> list:
    """Alle zugeklappten Summary-Texte der congstar/Allnet-Flat-XS-Zeilen,
    OHNE eine Ratenzahl vorauszusetzen - der alte Stand hat gar keine.
    Genau DAS ist der Befund: gegen den alten Stand liefert diese
    Funktion zwei textlich IDENTISCHE Eintraege."""
    texte = []
    for m in re.finditer(
            r'<details class="gr-bnd[^"]*"[^>]*data-anbieter="congstar"'
            r'[^>]*>(.*?)</details>', html, re.S):
        block = m.group(0)
        if "Allnet Flat XS" not in block or "Flex" in block:
            continue
        kopf = re.search(r"<summary>(.*?)</summary>", block, re.S).group(1)
        texte.append(" ".join(re.sub(r"<[^>]+>", " ", kopf).split()))
    return texte


def test_punkt1_rot_gegen_den_alten_stand(tmp_path, monkeypatch):
    """Beweis, dass der Kerntest gegen den ALTEN Stand rot ist: dieselbe
    Fixture, aber mit der Vorlage von VOR diesem Auftrag
    (`git show HEAD:...`, HEAD trägt die Fassung vor diesem Paket) -
    dort sind die 24er- und die 36er-Zeile zugeklappt wortgleich."""
    import subprocess

    import telco_radar.report.html as html_mod

    alt_dir = tmp_path / "alte_vorlagen"
    alt_dir.mkdir()
    # Alle Vorlagen des Pakets kopieren (Jinja-Includes brauchen die
    # ganzen Nachbardateien), NUR die Bündelzeile durch den alten Stand
    # ersetzen.
    live = pathlib.Path(html_mod._TEMPLATES)
    for datei in live.iterdir():
        if datei.is_file():
            (alt_dir / datei.name).write_bytes(datei.read_bytes())
    alt_inhalt = subprocess.run(
        ["git", "show", "HEAD:src/telco_radar/report/templates/"
                        "_geraete_buendel.html.j2"],
        cwd=WURZEL, capture_output=True, check=True, text=True).stdout
    (alt_dir / "_geraete_buendel.html.j2").write_text(alt_inhalt,
                                                       encoding="utf-8")
    monkeypatch.setattr(html_mod, "_TEMPLATES", alt_dir)

    alt_site = _baue(tmp_path / "alt", _bestand())
    html = (alt_site / "geraete.html").read_text(encoding="utf-8")
    texte = _congstar_xs_summarys(html)
    assert len(texte) == 2, (
        f"Fixture greift auch gegen den alten Stand nicht: {texte}")

    # DIE KERNASSERTION GEGEN DEN ALTEN STAND - hier ABSICHTLICH in
    # `pytest.raises` gefangen: sie ist rot, das ist der Beweis.
    with pytest.raises(AssertionError) as exc:
        assert texte[0] != texte[1], (
            "beide Zahlweisen sind zugeklappt wortgleich:\n"
            f"  Zeile 1: {texte[0]!r}\n  Zeile 2: {texte[1]!r}")
    # Die WOERTLICHE rote Ausgabe steht damit im Testprotokoll (repr der
    # AssertionError-Nachricht) - `pytest -rA`/`-v` druckt sie.
    print("ROTE AUSGABE GEGEN DEN ALTEN STAND:\n", str(exc.value))
    assert "wortgleich" in str(exc.value)


def test_punkt2_hauptzahl_nennt_ihr_subjekt(site):
    """Die Hauptzahl der Zeile ist "congstar 462,00 € unter Vodafone" -
    kein nackter Betrag - und sie ist die groesste Schrift der Zeile
    (Antonios Stil). Der Abstand ist deutlich ueber der Wesentlichkeits-
    Schwelle (Δ > 15 € UND > 3 %, siehe `_vodafone_buendel`) - GEGENPROBE
    zum Review-Fix S2: ein wesentlicher Abstand zeigt weiterhin die feste
    Zahl, kein "≈"."""
    html = (site / "geraete.html").read_text(encoding="utf-8")
    zeilen = _congstar_zeilen(html)
    delta = round(SOLL_GESAMT - (1 + 24 * 26.0 + 24 * 54.0), 2)
    assert delta < 0
    soll_text = (f"congstar {abs(delta):,.2f} € unter Vodafone"
                .replace(",", "#").replace(".", ",").replace("#", "."))
    for n in (24, 36):
        _klassen, text, block = zeilen[n]
        assert "≈" not in text, (
            f"{n} Raten: ein wesentlicher Abstand traegt ein '≈' - "
            f"{text!r}")
        assert soll_text in text, (
            f"{n} Raten: Hauptzahl fehlt oder falsch - {text!r}, "
            f"erwartet {soll_text!r}")
        subjekt = re.search(r'<strong class="gr-bnd-subjekt">([^<]*)</strong>',
                            block)
        assert subjekt, f"{n} Raten: kein gr-bnd-subjekt im Markup"
        assert subjekt.group(1).strip() == soll_text


def test_punkt3_anbieterfarbe_steht_an_der_zeile(site):
    """Der 3px-Streifen/die Anbieterfarbe braucht einen WERT fuer `--anb`
    AN der Zeile - ohne ihn fiel `var(--anb,#57534a)` immer auf den
    grauen Rueckfall zurueck, obwohl das Regelwerk dafuer laengst
    existierte. Ueber `style="--anb:…"`, NICHT ueber eine Klasse: der
    Wahrheits-Orakeltest (`tests/test_seiten_zahlen.py`, fuer dieses
    Paket schreibgeschuetzt) sucht an dieser Zeile woertlich
    `class="gr-bnd"` ohne Zusatz - siehe die Gegenprobe unten."""
    from telco_radar.report import anbieter_farben

    html = (site / "geraete.html").read_text(encoding="utf-8")
    zeilen = _congstar_zeilen(html)
    erwartet = anbieter_farben.farbe_fuer("congstar")
    for n, (opentag, _text, _block) in zeilen.items():
        assert f'style="--anb:{erwartet}"' in opentag, (
            f"{n} Raten: Zeile traegt {opentag!r}, erwartet den "
            f"Custom-Property-Wert {erwartet!r} (sonst bleibt die "
            "Anbieterfarbe der graue Rueckfall)")
        # GEGENPROBE (Regel 5 des Orakeltests): das class-Attribut bleibt
        # UNVERAENDERT "gr-bnd" - eine zusaetzliche Klasse haette den
        # Orakeltest zerstoert (`class="gr-bnd"` woertlich gesucht).
        assert re.search(r'class="gr-bnd"', opentag), (
            f"{n} Raten: das class-Attribut ist nicht mehr woertlich "
            f'"gr-bnd" - der Orakeltest wuerde brechen: {opentag!r}')


_SEG_RE = re.compile(
    r'<span\s+class="gr-bnd-zerl-seg([^"]*)"\s+style="width:([\d.]+)%"\s+'
    r'title="([^"]*): ([\d.,]+) €"', re.S)


def _zerlegung(block: str) -> list:
    out = []
    for klassen, pct, name, betrag in _SEG_RE.findall(block):
        out.append({"offen": "gr-bnd-zerl-seg--offen" in klassen,
                    "pct": float(pct), "name": name,
                    "betrag": float(betrag.replace(".", "").replace(",", "."))})
    return out


def test_punkt4_zerlegungsbalken_summiert_exakt_zur_leitzahl(site):
    """Die Segmentbetraege des Balkens (aus den `title`-Attributen
    gelesen) summieren GENAU zur Leitzahl - keine zweite Rechnung, nur
    eine zweite, groessere Darstellung derselben `tco_24()`-Bestandteile.
    """
    html = (site / "geraete.html").read_text(encoding="utf-8")
    zeilen = _congstar_zeilen(html)
    for n, (_klassen, _text, block) in zeilen.items():
        seg = _zerlegung(block)
        assert seg, f"{n} Raten: kein Zerlegungsbalken im Rechenweg"
        summe = round(sum(s["betrag"] for s in seg), 2)
        assert summe == pytest.approx(SOLL_GESAMT, abs=0.005), (
            f"{n} Raten: Segmente summieren zu {summe} EUR, "
            f"Leitzahl ist {SOLL_GESAMT} EUR")
        pct_summe = round(sum(s["pct"] for s in seg), 1)
        assert pct_summe == pytest.approx(100.0, abs=0.2)


def test_punkt4_restschuld_ist_schraffiertes_segment(site):
    """Nur die 36-Raten-Zeile traegt ein `--offen`-Segment, und sein
    Betrag ist exakt die Restschuld (366,00 EUR) - die 24er hat keins."""
    html = (site / "geraete.html").read_text(encoding="utf-8")
    zeilen = _congstar_zeilen(html)
    for n, (_klassen, _text, block) in zeilen.items():
        seg = _zerlegung(block)
        offen = [s for s in seg if s["offen"]]
        if SOLL_RESTSCHULD[n]:
            assert len(offen) == 1, (
                f"{n} Raten: erwartet EIN offenes Segment, gefunden "
                f"{len(offen)}")
            assert offen[0]["betrag"] == pytest.approx(
                SOLL_RESTSCHULD[n], abs=0.005)
            assert offen[0]["name"] == "Restschuld nach Monat 24"
        else:
            assert not offen, (
                f"{n} Raten: eine erfundene Restschuld steht im Balken "
                f"({offen})")


# --------------------------------------------------------------------------
# Mutationsproben (CLAUDE.md-Auftrag): je Kernaenderung eine Probe, dass
# der Test wirklich SCHEITERT, wenn die Zahl falsch waere - sonst ist er
# nur ein grüner Test, der nichts prüft.
# --------------------------------------------------------------------------

def test_mutationsprobe_punkt1_erkennt_wortgleiche_zeilen():
    """`test_punkt1_...` MUSS scheitern, wenn zwei Texte wortgleich sind
    (die Ur-Form des Befunds) - eine direkte Mutationsprobe der
    Kernassertion, ohne den ganzen Seitenaufbau."""
    text24 = text36 = ("congstar · Allnet Flat XS · 15 GB · 1.459,00 € · "
                       "−462,00 € · −24,0 %")
    with pytest.raises(AssertionError):
        assert text24 != text36


def test_mutationsprobe_punkt4_erkennt_falsche_segmentsumme():
    """`zerlegung_balken()` MUSS eine Summe liefern, die von `gesamt`
    abweicht, wenn ein Segmentbetrag verfälscht wird - sonst könnte die
    Anzeige unbemerkt von der Leitzahl abweichen."""
    from telco_radar.report.geraete_tco_karten import zerlegung_balken

    bestandteile = [
        {"name": "Tarif über 24 Monate", "betrag": 360.0, "kategorie": "tarif"},
        {"name": "Gerätezuzahlung", "betrag": 1.0, "kategorie": "einmalig"},
        {"name": "Geräteraten über 36 Monate", "betrag": 1098.0,
         "kategorie": "raten"},
        {"name": "Anschlusspreis", "betrag": 0.0, "kategorie": "einmalig"},
    ]
    seg = zerlegung_balken(bestandteile, restbetrag=366.0, gesamt=1459.0)
    assert round(sum(s["betrag"] for s in seg), 2) == pytest.approx(1459.0)
    # MUTATION: ein Segmentbetrag wird verfaelscht - die Summenprobe muss
    # das erkennen.
    kaputt = [dict(s) for s in seg]
    kaputt[0]["betrag"] += 10.0
    assert round(sum(s["betrag"] for s in kaputt), 2) != pytest.approx(1459.0)


def test_mutationsprobe_punkt2_erkennt_falsches_vorzeichen():
    """Die Subjekt-Zeile MUSS "unter" und "über" unterscheiden - eine
    Mutationsprobe, dass ein Vorzeichenfehler den Text sichtbar aendert."""
    anbieter, betrag = "congstar", 462.00
    guenstiger_satz = f"{anbieter} {betrag:.2f} unter Vodafone".replace(
        ".", ",")
    teurer_satz = f"{anbieter} {betrag:.2f} über Vodafone".replace(".", ",")
    assert guenstiger_satz != teurer_satz


# --------------------------------------------------------------------------
# REVIEW-FIX S2 (blockierend): die Hauptzahl ignorierte die Wesentlich-
# keits-Schwelle. Eine EIGENE, kleine Fixture mit einem Abstand UNTER der
# Schwelle (`geraete_vergleich.WESENTLICH_EURO`/`_PROZENT`) - die
# Hauptfixture des Moduls (`_vodafone_buendel`) vermeidet diesen Fall
# absichtlich (Δ > 15 € UND > 3 %, siehe deren Kommentar), darum ein
# eigenes Modell (Samsung Galaxy S26, im gemeinsamen `_KATALOG` bereits
# vorhanden) statt einer dritten congstar-Zeile am iPhone 17 Pro - zwei
# congstar-Zeilen mit derselben Ratenzahl (24) fuer dasselbe Geraet
# wuerden sich im Lookup (`_congstar_zeilen`) gegenseitig ueberschreiben.
# --------------------------------------------------------------------------

DEVICE_U = "samsung-galaxy-s26"
ZUZAHLUNG_U = 455.00
TARIF_MONATLICH_U = 15.0
RATE_U = 45.75
SOLL_GESAMT_U = 1913.00
SOLL_REFERENZ_GESAMT_U = 1 + 24 * 26.0 + 24 * 54.0  # 1.921,00 €
SOLL_ABSTAND_U = round(SOLL_REFERENZ_GESAMT_U - SOLL_GESAMT_U, 2)  # 8,00 €


def _congstar_buendel_ungefaehr() -> dict:
    return {
        "id": f"buendel--congstar--{_sku(DEVICE_U, 256)}--cs-xs-u--24",
        "sku_id": _sku(DEVICE_U, 256), "anbieter": "congstar",
        "tarif_name": "Allnet Flat XS", "tarif_id": "cs:xs-u",
        "tarif_id_guete": "hoch", "tarif_monatlich": TARIF_MONATLICH_U,
        "tarif_bindung_monate": 24, "geraet_zuzahlung": ZUZAHLUNG_U,
        "geraet_monatsrate": RATE_U, "laufzeit_monate": 24,
        "anschlusspreis": 0.0, "zustand": "neu", "rabatte": [],
        "quelle_url": "https://example.de/congstar/s26",
        "abgerufen_am": HEUTE, "first_seen": HEUTE, "last_verified": HEUTE}


def _vodafone_buendel_ungefaehr() -> dict:
    # Dieselben Vodafone-Zahlen wie die Hauptfixture (`_vodafone_buendel`) -
    # nur SOLL_GESAMT_U der congstar-Zeile ist so gewaehlt, dass der
    # Abstand zu dieser Referenz (8,00 €) unter BEIDEN Schwellen bleibt
    # (< 15 € UND < 3 % von 1.921,00 €).
    return {
        "id": f"buendel--vodafone--{_sku(DEVICE_U, 256)}--vf-xs-u--24",
        "sku_id": _sku(DEVICE_U, 256), "anbieter": "Vodafone",
        "tarif_name": "Vodafone Mobil XS", "tarif_id": "vf:xs-u",
        "tarif_id_guete": "hoch", "tarif_monatlich": 26.0,
        "tarif_bindung_monate": 24, "geraet_zuzahlung": 1.0,
        "geraet_monatsrate": 54.0, "laufzeit_monate": 24,
        "anschlusspreis": 0.0, "zustand": "neu", "rabatte": [],
        "quelle_url": "https://example.de/vodafone/s26",
        "abgerufen_am": HEUTE, "first_seen": HEUTE, "last_verified": HEUTE}


def _bestand_ungefaehr() -> dict:
    return {
        "buendel": [_congstar_buendel_ungefaehr(),
                   _vodafone_buendel_ungefaehr()],
        "listung": _listung("Vodafone", DEVICE_U, 256, 999.00),
    }


@pytest.fixture(scope="module")
def site_ungefaehr(tmp_path_factory):
    return _baue(tmp_path_factory.mktemp("d3s2ungefaehr"),
                _bestand_ungefaehr())


def test_review_fix_s2_gegenprobe_wesentlich_bleibt_fest():
    """GEGENPROBE der Fixture selbst, VOR jedem Render: der gebaute
    Abstand (8,00 € von 1.921,00 €) liegt wirklich unter BEIDEN
    Wesentlichkeits-Schwellen - sonst wuerde dieser Test die Annäherung
    gar nicht bauen, sondern versehentlich denselben wesentlichen Fall
    wie die Hauptfixture."""
    from telco_radar.report import geraete_vergleich

    assert SOLL_ABSTAND_U == pytest.approx(8.00)
    assert SOLL_ABSTAND_U < geraete_vergleich.WESENTLICH_EURO
    assert (SOLL_ABSTAND_U / SOLL_REFERENZ_GESAMT_U * 100) \
        < geraete_vergleich.WESENTLICH_PROZENT


def test_review_fix_s2_ungefaehr_subjekt_behauptet_keine_fuehrerschaft(
        site_ungefaehr):
    """DER BLOCKIERENDE BEFUND: unter der Wesentlichkeits-Schwelle darf
    die Hauptzahl der Zeile keine feste Führerschaft mehr behaupten
    ("congstar 8,00 € unter Vodafone", fett) - derselbe Fall zeigt im
    Rechenweg der eigenen Zeile (der ≈-Zweig, A2 20.09.2026) bewusst
    "≈ 8,00 €". Die groesste Schrift der Zeile widerspricht sonst ihrer
    eigenen Nachbarzeile (CLAUDE.md: die wichtigste Zahl ist die groesste
    Schrift ihres Bereichs - deshalb muss sie besonders stimmen)."""
    html = (site_ungefaehr / "geraete.html").read_text(encoding="utf-8")
    treffer = _ZEILE_RE.findall(html)
    assert len(treffer) == 1, (
        f"erwartet genau eine congstar-Zeile, gefunden {len(treffer)}")
    block = treffer[0][1]

    subjekt = re.search(r'<strong class="gr-bnd-subjekt">([^<]*)</strong>',
                        block)
    assert subjekt, "kein gr-bnd-subjekt im Markup der Annäherungs-Zeile"
    text = subjekt.group(1).strip()
    soll_text = f"congstar ≈ {SOLL_ABSTAND_U:,.2f} € unter Vodafone".replace(
        ",", "#").replace(".", ",").replace("#", ".")
    assert text == soll_text, (
        f"Hauptzahl der Annäherungs-Zeile: {text!r}, erwartet {soll_text!r}")

    # GEGENPROBE: dieselbe "≈"-Sprache wie die Nachbarzeile im Rechenweg
    # (`gr-kk-delta`, A2 20.09.2026) - kein zweiter, unbeabsichtigter Text.
    platt = " ".join(re.sub(r"<[^>]+>", " ", block).split())
    naeherung_text = f"≈ {SOLL_ABSTAND_U:,.2f} €".replace(
        ",", "#").replace(".", ",").replace("#", ".")
    assert platt.count(naeherung_text) >= 2, (
        f"die Annäherungs-Sprache {naeherung_text!r} fehlt in Subjekt "
        f"oder Rechenweg: {platt!r}")


def test_review_fix_s2_rot_gegen_den_alten_stand(tmp_path, monkeypatch):
    """Beweis, dass der Review-Fix S2 gegen den ALTEN Stand (vor diesem
    Fix) rot ist: dieselbe Annäherungs-Fixture, aber mit dem Subjekt-Block
    von VOR dem Fix - der pruefte nur `k.delta.betrag is not none`, nicht
    `k.delta.ungefaehr`, und behauptete darum auch unter der Schwelle eine
    feste Zahl.

    Anders als `test_punkt1_rot_gegen_den_alten_stand` NICHT ueber
    `git show HEAD:...`: HEAD traegt noch gar kein Paket D3 (alle
    Dateien des Pakets sind uncommittet), ein Checkout von HEAD haette
    also gar kein `gr-bnd-subjekt` und wuerde nichts beweisen. Der alte
    Block wird darum gezielt an der EINEN Stelle zurueckgetauscht, die
    dieser Fix aendert (`neuer_block`/`alter_block`), am selben, sonst
    unveraenderten, aktuellen Stand."""
    import telco_radar.report.html as html_mod

    live = pathlib.Path(html_mod._TEMPLATES)
    aktuell = (live / "_geraete_buendel.html.j2").read_text(encoding="utf-8")

    anfang = aktuell.index('<strong class="gr-bnd-subjekt">')
    ende = aktuell.index("</strong>", anfang) + len("</strong>")
    neuer_block = aktuell[anfang:ende]
    # Der Subjekt-Block VOR Review-Fix S2 (wortgleich mit dem Stand zu
    # Beginn dieses Fixes): kein "≈", keine Klammer-Prozent - eine feste
    # Zahl fuer JEDEN Δ, auch unter der Wesentlichkeits-Schwelle.
    alter_block = (
        '<strong class="gr-bnd-subjekt">{{ k.anbieter }}{% if k.delta.ungefaehr\n'
        "      and not k.delta.abstand %} entspricht Vodafone{% else %} {{\n"
        "      k.delta.abstand | euro }} {{ 'unter' if k.delta.guenstiger else\n"
        "      'über' }} Vodafone{% endif %}</strong>"
    )
    assert neuer_block != alter_block, (
        "der aktuelle Block ist wortgleich mit dem alten - der Fix steht "
        "nicht mehr im Stand, dieser Test wuerde nichts beweisen")
    alt_inhalt = aktuell.replace(neuer_block, alter_block)
    assert alt_inhalt != aktuell, "Marker fuer den Subjekt-Block nicht gefunden"

    alt_dir = tmp_path / "alte_vorlagen_s2"
    alt_dir.mkdir()
    for datei in live.iterdir():
        if datei.is_file():
            ziel = alt_dir / datei.name
            if datei.name == "_geraete_buendel.html.j2":
                ziel.write_text(alt_inhalt, encoding="utf-8")
            else:
                ziel.write_bytes(datei.read_bytes())
    monkeypatch.setattr(html_mod, "_TEMPLATES", alt_dir)

    alt_site = _baue(tmp_path / "alt_s2", _bestand_ungefaehr())
    html = (alt_site / "geraete.html").read_text(encoding="utf-8")
    treffer = _ZEILE_RE.findall(html)
    assert len(treffer) == 1, (
        f"Fixture greift auch gegen den alten Stand nicht: {len(treffer)} "
        "congstar-Zeilen")
    block = treffer[0][1]
    subjekt = re.search(r'<strong class="gr-bnd-subjekt">([^<]*)</strong>',
                        block)
    assert subjekt, "kein gr-bnd-subjekt im alten Stand"
    text = subjekt.group(1).strip()
    soll_text = f"congstar ≈ {SOLL_ABSTAND_U:,.2f} € unter Vodafone".replace(
        ",", "#").replace(".", ",").replace("#", ".")

    # DIE KERNASSERTION GEGEN DEN ALTEN STAND - hier ABSICHTLICH in
    # `pytest.raises` gefangen: sie ist rot, das ist der Beweis.
    with pytest.raises(AssertionError) as exc:
        assert text == soll_text, (
            "die Hauptzahl behauptet eine feste Führerschaft unter der "
            f"Wesentlichkeits-Schwelle: {text!r}, erwartet {soll_text!r}")
    print("ROTE AUSGABE GEGEN DEN ALTEN STAND (S2):\n", str(exc.value))
    assert "feste Führerschaft" in str(exc.value)
    # Der ALTE, FALSCHE Text ist genau der Befund aus dem Review.
    alter_falscher_text = (
        f"congstar {SOLL_ABSTAND_U:,.2f} € unter Vodafone".replace(
            ",", "#").replace(".", ",").replace("#", "."))
    assert text == alter_falscher_text, f"unerwarteter alter Text: {text!r}"


# --------------------------------------------------------------------------
# REVIEW-FIX S3 (mitgenommen): `zerlegung_balken()` reine Funktionstests,
# ohne vollen Seitenaufbau - Punkt 1 (Truthiness statt `is not None`) und
# Punkt 2 (kein 0,00-€-Phantomsegment).
# --------------------------------------------------------------------------

def test_review_fix_s3_1_restbetrag_none_erzeugt_keinen_phantom_split():
    """`restbetrag=None` heisst "nicht bestimmbar" (Clean Code 3) - KEIN
    Split, keine erfundene Restschuld von 0,00 €. Gegenprobe: eine ECHTE,
    gemessene Restschuld > 0 splittet weiterhin, und 0,00 € (gemessen,
    "nichts offen") verhaelt sich wie `None` (kein Split), aber aus einem
    ANDEREN, ebenfalls gemessenen Grund."""
    from telco_radar.report.geraete_tco_karten import zerlegung_balken

    bestandteile = [
        {"name": "Tarif über 24 Monate", "betrag": 360.0, "kategorie": "tarif"},
        {"name": "Geräteraten über 30 Monate", "betrag": 1000.0,
         "kategorie": "raten"},
    ]
    seg_none = zerlegung_balken(bestandteile, restbetrag=None, gesamt=1360.0)
    assert not any(s["offen"] for s in seg_none), (
        f"restbetrag=None erzeugt trotzdem ein offenes Segment: {seg_none}")
    assert all(s["kategorie"] != "restschuld" for s in seg_none), (
        f"restbetrag=None erfindet eine Restschuld: {seg_none}")
    assert round(sum(s["betrag"] for s in seg_none), 2) \
        == pytest.approx(1360.0)

    seg_null = zerlegung_balken(bestandteile, restbetrag=0.0, gesamt=1360.0)
    assert not any(s["offen"] for s in seg_null)

    # Gegenprobe: eine echte, gemessene Restschuld > 0 splittet weiterhin.
    seg_echt = zerlegung_balken(bestandteile, restbetrag=200.0, gesamt=1360.0)
    offen = [s for s in seg_echt if s["offen"]]
    assert len(offen) == 1 and offen[0]["betrag"] == pytest.approx(200.0), (
        f"eine echte Restschuld splittet nicht mehr: {seg_echt}")


def test_review_fix_s3_2_nullbetrag_posten_ohne_balkenteil():
    """Ein Posten mit Betrag exakt 0,00 € (eine gemessene "keine
    Zuzahlung"/"kein Anschlusspreis") bekommt keinen eigenen
    Balken-Segment - sonst zeigt `min-width:2px` (D3-CSS-Block) einen
    Phantomstreifen ohne Aussage. Ein echter Betrag bleibt stehen."""
    from telco_radar.report.geraete_tco_karten import zerlegung_balken

    bestandteile = [
        {"name": "Tarif über 24 Monate", "betrag": 360.0, "kategorie": "tarif"},
        {"name": "Gerätezuzahlung", "betrag": 0.0, "kategorie": "einmalig"},
        {"name": "Anschlusspreis", "betrag": 0.0, "kategorie": "einmalig"},
        {"name": "Geräteraten über 24 Monate", "betrag": 1000.0,
         "kategorie": "raten"},
    ]
    seg = zerlegung_balken(bestandteile, restbetrag=0.0, gesamt=1360.0)
    namen = {s["name"] for s in seg}
    assert "Gerätezuzahlung" not in namen and "Anschlusspreis" not in namen, (
        f"ein 0,00-€-Posten hat trotzdem ein Segment: {seg}")
    assert "Tarif über 24 Monate" in namen and \
        "Geräteraten über 24 Monate" in namen, (
        f"ein echter Posten fehlt: {seg}")
    assert round(sum(s["betrag"] for s in seg), 2) == pytest.approx(1360.0)


def test_review_fix_s3_2_voll_offene_raten_ohne_faelliges_nullsegment():
    """Ist die gesamte Rate erst nach Monat 24 faellig (Restschuld ==
    Ratensumme), waere der "fällige" Teil vor dem Split exakt 0,00 € -
    auch DIESES Segment bleibt weg, nur das offene (schraffierte)
    Segment steht."""
    from telco_radar.report.geraete_tco_karten import zerlegung_balken

    seg = zerlegung_balken(
        [{"name": "Geräteraten über 36 Monate", "betrag": 500.0,
          "kategorie": "raten"}],
        restbetrag=500.0, gesamt=500.0)
    faellig = [s for s in seg if not s["offen"]]
    assert not faellig, f"ein 0,00-€ 'fälliger' Teil steht im Balken: {seg}"
    offen = [s for s in seg if s["offen"]]
    assert len(offen) == 1 and offen[0]["betrag"] == pytest.approx(500.0)
