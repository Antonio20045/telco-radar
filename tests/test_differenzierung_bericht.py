"""Tests fuer die Zerlegung des Differenzierungsberichts.

Antonio am 08.08.2026: "Bericht finde ich auch gut, aber nicht einfach so
reinpasten, dieser eine lange Bereich ... das muss intelligent sein."

Die Zerlegung ist die Voraussetzung dafuer, dass die Seite den Bericht an drei
Stellen einsetzen kann statt als Block am Ende. Die zwei Faelle, die hier
zaehlen: die NEUE Gliederung wird korrekt verteilt, und ein ALTER Bericht
(davon liegen Monate in data/reports/differenzierung/) faellt sauber auf den
Aufklapper zurueck, statt eine leere Seite zu hinterlassen.
"""
from telco_radar.report.differenzierung_bericht import zerlegen

LABELS = {"ki": "KI & Assistenten", "entertainment": "Entertainment & Streaming",
          "garantie": "Garantie & Service-Versprechen"}

NEU = """## Das Bild

Die Anbieter legen zunehmend fremde Dienste in den Tarif
[Airtel – croma.com](https://croma.com/a).

## Muster

**Premium-KI als Zugabe** Zwei Anbieter verschenken dieselbe Lizenz
[Airtel](https://croma.com/a), [SK Telecom](https://perplexity.ai/b).

**Garantie statt Rabatt** Mehrjaehrige Preiszusagen ersetzen den Nachlass
[T-Mobile](https://t-mobile.com/c).

## Einordnung

### KI & Assistenten

Indien treibt das Feld: drei der vier groessten Netze bieten eine Lizenz an.

### Garantie & Service-Versprechen

In den USA ist die Preisgarantie zum Standardversprechen geworden.
"""

ALT = """## Konkrete Entwicklungen

**KI und digitale Dienste** Airtel bietet ...; Jio bietet ...

## Quellenbasis

- [Airtel – croma.com](https://croma.com/a) · Asien
"""


def test_die_neue_gliederung_wird_in_drei_teile_zerlegt():
    t = zerlegen(NEU, LABELS)
    assert t["lage"].startswith("Die Anbieter legen")
    assert [m["titel"] for m in t["muster"]] == ["Premium-KI als Zugabe",
                                                 "Garantie statt Rabatt"]
    assert set(t["einordnung"]) == {"ki", "garantie"}
    assert t["einordnung"]["ki"].startswith("Indien treibt das Feld")
    # Nichts bleibt fuer den Aufklapper uebrig - der Bericht steht verteilt
    # auf der Seite, nicht zusaetzlich als Block.
    assert t["alt_md"] == ""


def test_die_einordnung_haengt_am_hebel_namen_nicht_an_der_reihenfolge():
    """Der Redakteur laesst Hebel aus, zu denen ihm nichts einfaellt. Eine
    Zuordnung nach Position haengte dann jeden folgenden Absatz an den
    falschen Hebel - eine falsche Verbindung ist schlimmer als keine."""
    t = zerlegen(NEU, LABELS)
    assert "entertainment" not in t["einordnung"]
    assert t["einordnung"]["garantie"].startswith("In den USA")


def test_eine_unbekannte_h3_wird_verworfen_statt_falsch_zugeordnet():
    md = ("## Das Bild\n\nText.\n\n## Muster\n\nText.\n\n"
          "## Einordnung\n\n### Etwas ganz anderes\n\nSatz.\n")
    assert zerlegen(md, LABELS)["einordnung"] == {}


def test_ein_musterabsatz_ohne_fettes_leitwort_geht_nicht_verloren():
    """Ihn zu verwerfen hiesse, eine Aussage wegen ihrer Formatierung zu
    unterschlagen."""
    md = "## Das Bild\n\nA.\n\n## Muster\n\nEin Muster ohne Leitwort.\n\n## Einordnung\n"
    muster = zerlegen(md, LABELS)["muster"]
    assert muster == [{"titel": "", "text": "Ein Muster ohne Leitwort."}]


def test_ein_alter_bericht_bleibt_als_block_lesbar():
    """Die Berichte in data/reports/differenzierung/ sind Monate alt und
    tragen die alte Gliederung. Kein Lauf muss abgewartet werden, damit die
    Seite steht."""
    t = zerlegen(ALT, LABELS)
    assert t["lage"] == "" and t["muster"] == [] and t["einordnung"] == {}
    assert "Konkrete Entwicklungen" in t["alt_md"]


def test_die_quellenbasis_allein_macht_einen_bericht_nicht_verteilbar():
    """Sie wird uebersprungen (sie fuehrt jede Karte der Seite ein zweites
    Mal auf) - aber ein Bericht, der NUR daraus besteht, gilt trotzdem als
    alt und landet im Aufklapper, statt spurlos zu verschwinden."""
    t = zerlegen("## Quellenbasis\n\n- [A](https://a.example.com/)\n", LABELS)
    assert t["alt_md"].startswith("## Quellenbasis")


def test_leerer_bericht_bricht_nicht():
    assert zerlegen("", LABELS) == {"lage": "", "muster": [], "einordnung": {},
                                    "alt_md": ""}


def test_der_notfall_digest_wird_von_derselben_zerlegung_verstanden():
    """Prompt, `validate_briefing`, `build_digest` und diese Zerlegung
    haengen an EINER Gliederung. Faellt der Redakteur aus, aendert sich der
    Ton der Seite, nicht ihr Aufbau."""
    from telco_radar.analyze.differentiation_editor import build_digest
    eintraege = [
        {"theme": "ki", "operator": op, "region": "Asien", "what": "Etwas.",
         "url": f"https://example.com/{op}", "source": "example.com",
         "first_seen": "2026-07-01", "last_verified": "2026-07-01"}
        for op in ("Airtel", "SK Telecom")]
    t = zerlegen(build_digest(eintraege, LABELS), LABELS)
    assert t["lage"] and t["muster"] and t["einordnung"].get("ki")
    assert t["alt_md"] == ""
