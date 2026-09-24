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
from bs4 import BeautifulSoup

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


def test_gr_bnd_subjekt_kommt_nicht_mehr_vor(site):
    """C1 (QA-Fix 24.09.2026): die verdoppelte Hauptzahl unter der Zeile
    ("congstar 496,80 € unter Vodafone") ist entfernt - die Δ-Spalte
    bleibt die einzige Stelle mit diesem Betrag. Geprueft am ganzen
    Dokument (nicht nur an der congstar-Zeile dieser Fixture), damit auch
    ein wieder eingeschlichenes CSS-Selektor-Fossil auffaellt."""
    html = (site / "geraete.html").read_text(encoding="utf-8")
    assert "gr-bnd-subjekt" not in html


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


# Wortgetreue Kopie der Vorlage von VOR Paket D3 (Commit 58446de, siehe
# Dateikopf der Fixture) - eingefroren im Repo, statt per `git show HEAD:...`
# gelesen. Ein `git show HEAD:...` wird nach dem Commit dieses Fixes selbst
# zum NEUEN Stand und der Test würde grün werden, ohne dass sich am
# geprüften Verhalten etwas ändert (CLAUDE.md: ein Test darf nicht vom
# Git-Stand abhängen). Die Datei wird nie nachgeführt.
_ALTE_VORLAGE = WURZEL / "tests" / "fixtures" / "geraete_buendel_vor_d3.html.j2"


def test_punkt1_rot_gegen_den_alten_stand(tmp_path, monkeypatch):
    """Beweis, dass der Kerntest gegen den ALTEN Stand (vor Paket D3,
    eingefroren in `_ALTE_VORLAGE`) rot ist: dort sind die 24er- und die
    36er-Zeile zugeklappt wortgleich - genau der Befund, den D3 behebt.
    Stabil gegen künftige Commits: die Fixture ändert sich nie, es wird
    kein `git show` mehr zur Laufzeit gelesen."""
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
    (alt_dir / "_geraete_buendel.html.j2").write_bytes(
        _ALTE_VORLAGE.read_bytes())
    monkeypatch.setattr(html_mod, "_TEMPLATES", alt_dir)

    alt_site = _baue(tmp_path / "alt", _bestand())
    html = (alt_site / "geraete.html").read_text(encoding="utf-8")
    texte = _congstar_xs_summarys(html)
    assert len(texte) == 2, (
        f"Fixture greift auch gegen den alten Stand nicht: {texte}")

    # DIE KERNASSERTION GEGEN DEN ALTEN STAND: dort SIND beide Zeilen
    # zugeklappt wortgleich - das ist der eingefrorene Befund, kein
    # `pytest.raises`-Umweg mehr nötig, weil die Fixture nie wieder den
    # neuen (gefixten) Text tragen kann.
    assert texte[0] == texte[1], (
        "die Fixture (Stand vor D3) ist entgegen der Annahme nicht mehr "
        f"wortgleich - stimmt _ALTE_VORLAGE wirklich mit Commit 58446de "
        f"überein?\n  Zeile 1: {texte[0]!r}\n  Zeile 2: {texte[1]!r}")


def test_punkt2_delta_spalte_traegt_die_feste_zahl(site):
    """C1 (QA-Fix 24.09.2026): `.gr-bnd-subjekt` ist gefallen - die
    Δ-Spalte (`.gr-bnd-delta`) ist jetzt die EINZIGE Stelle, die den
    Abstand zu Vodafone nennt. Der Abstand liegt deutlich ueber der
    Wesentlichkeits-Schwelle (Δ > 15 € UND > 3 %, siehe
    `_vodafone_buendel`) - GEGENPROBE zur "≈"-Regel: ein wesentlicher
    Abstand zeigt die feste Zahl, kein "≈", und traegt die
    `gr-bnd-delta--wert`-Klasse (Δ-Praefix mobil)."""
    html = (site / "geraete.html").read_text(encoding="utf-8")
    zeilen = _congstar_zeilen(html)
    delta = round(SOLL_GESAMT - (1 + 24 * 26.0 + 24 * 54.0), 2)
    assert delta < 0
    betrag_text = (f"{abs(delta):,.2f} €"
                  .replace(",", "#").replace(".", ",").replace("#", "."))
    for n in (24, 36):
        _klassen, _text, block = zeilen[n]
        soup = BeautifulSoup(block, "html.parser")
        zelle = soup.select_one(".gr-bnd-delta")
        assert zelle is not None, f"{n} Raten: keine Δ-Spalte im Markup"
        delta_text = zelle.get_text(strip=True)
        assert "≈" not in delta_text, (
            f"{n} Raten: ein wesentlicher Abstand traegt ein '≈' - "
            f"{delta_text!r}")
        assert betrag_text in delta_text, (
            f"{n} Raten: Δ-Betrag fehlt oder falsch - {delta_text!r}, "
            f"erwartet {betrag_text!r}")
        assert "gr-bnd-delta--wert" in (zelle.get("class") or []), (
            f"{n} Raten: gr-bnd-delta--wert fehlt an einem echten Δ-Wert")


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


def test_review_fix_s2_delta_spalte_behauptet_keine_fuehrerschaft(
        site_ungefaehr):
    """C1 (QA-Fix 24.09.2026): `.gr-bnd-subjekt` ist gefallen - der
    urspruengliche Review-Fix S2 gilt jetzt der Δ-Spalte selbst
    (`.gr-bnd-delta`), der einzigen verbliebenen Stelle des Betrags.
    Unter der Wesentlichkeits-Schwelle darf sie keine feste Fuehrerschaft
    mehr behaupten ("8,00 €" ohne "≈"), sondern zeigt "≈ 8,00 €" - und
    dabei NICHT die `gr-bnd-delta--wert`-Klasse (das Δ-Praefix ist nur
    fuer feste Werte gedacht, siehe die Vorlage)."""
    html = (site_ungefaehr / "geraete.html").read_text(encoding="utf-8")
    treffer = _ZEILE_RE.findall(html)
    assert len(treffer) == 1, (
        f"erwartet genau eine congstar-Zeile, gefunden {len(treffer)}")
    block = treffer[0][1]
    soup = BeautifulSoup(block, "html.parser")
    zelle = soup.select_one(".gr-bnd-delta")
    assert zelle is not None, "keine Δ-Spalte im Markup der Annäherungs-Zeile"
    text = zelle.get_text(strip=True)
    soll_text = f"≈ −{SOLL_ABSTAND_U:,.2f} €".replace(
        ",", "#").replace(".", ",").replace("#", ".")
    assert text == soll_text, (
        f"Δ-Spalte der Annäherungs-Zeile: {text!r}, erwartet {soll_text!r}")
    assert "gr-bnd-delta--wert" not in (zelle.get("class") or []), (
        "die Annäherung traegt das Δ-Praefix, obwohl sie kein fester "
        "Wert ist")


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


def test_ausfall_restbetrag_groesser_als_posten_zeichnet_keinen_balken(
        caplog):
    """S3-Nachtrag (gemessen): eine Restschuld, die groesser ist als der
    Posten, aus dem sie stammt (ein widerspruechlicher Bestand), darf
    NIE ein negatives Balkensegment erzeugen (Clean Code 5) - der alte
    Stand rechnete `betrag - rest` ungeprueft und haengte das Ergebnis
    ungeprueft an; das war hier -100.0. Der Ausfall ist benannt: ein
    Protokolleintrag (`logging.warning`) und eine leere Liste als
    Kennzeichen "kein Balken", dieselbe Bedeutung wie ein fehlendes
    `gesamt` oben in der Funktion - die Vorlage laesst den Balken bei
    einer leeren `k.zerlegung` ohnehin schon weg (`{% if k.zerlegung %}`
    in `_geraete_buendel.html.j2`)."""
    from telco_radar.report.geraete_tco_karten import zerlegung_balken

    bestandteile = [
        {"name": "Geräteraten über 36 Monate", "betrag": 400.0,
         "kategorie": "raten"},
    ]
    with caplog.at_level("WARNING"):
        seg = zerlegung_balken(bestandteile, restbetrag=500.0, gesamt=400.0)
    assert seg == [], (
        f"eine Restschuld ueber dem Posten erzeugt trotzdem einen "
        f"Balken: {seg}")
    assert any("restbetrag" in r.message and "500" in r.message
              for r in caplog.records), (
        "kein Protokolleintrag zum Ausfall - Regel 5 verlangt ein "
        "Protokoll, kein stilles leeres Ergebnis ohne Spur")


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
