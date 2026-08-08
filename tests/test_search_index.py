"""Tests fuer den siteweiten Suchindex (report/suchindex.py).

Abnahmetest aus claude/suche-marktrecherche-konzept.md: eine Suche nach
"Perplexity" muss die bekannten Treffer der Differenzierungs-Bibliothek finden
(SK Telecom, Deutsche Telekom, ...), auch wenn der Begriff in den Meldungen
dieser Woche gar nicht vorkommt - im Ernstfall lebt genau dieser Begriff fast
ausschliesslich in der Bibliothek, nicht im Wochenbericht.

Seit dem 08.08.2026 traegt der Index einen dritten Bereich (die Promo-Aktionen)
und je Eintrag sein Bild. Beides steht hier unter Test, weil beides der Grund
war, warum die alte Suche als "total bescheuert" empfunden wurde: sie fand die
laufenden Aktionen einer Marke nicht, und was sie fand, zeigte sie als graue
Textzeile.
"""
from telco_radar.report import suchindex


def _woche(ausgabe, **highlight_kw):
    base = {"schlagzeile": "Generic headline", "summary": "Generic summary text.",
            "operator": "X", "url": "http://example.com/a", "relevance": 3,
            "ressort_label": "Netz & Technik", "region": "Europa",
            "date": ausgabe, "source_label": "src"}
    base.update(highlight_kw)
    return {"date": ausgabe, "highlights": [base]}


def _diff_entry(**kw):
    base = {"id": "http://example.com/perplexity", "theme": "ki",
            "operator": "SK Telecom", "region": "Asien",
            "what": "Perplexity Pro 12 Monate gratis fuer alle Kunden.",
            "url": "http://example.com/perplexity", "source": "perplexity.ai",
            "date": "2024-02", "why": "KI-Bundle als Tarif-Bonus.",
            "first_seen": "2026-06-15", "last_verified": "2026-07-21",
            "status": "aktiv"}
    base.update(kw)
    return base


def _aktion(**kw):
    base = {"brand": "congstar", "headline": "Perplexity Pro gratis dazu",
            "description": "Zwoelf Monate ohne Aufpreis.",
            "url": "https://congstar.de/aktion", "first_seen": "2026-08-01",
            "status": "aktiv", "mechanic": "zugabe"}
    base.update(kw)
    return base


def _find(q, items):
    q = q.lower()
    return [i for i in items
            if q in (i["title"] + " " + i.get("summary", "") + " "
                     + i.get("operator", "")).lower()]


def test_bericht_item_is_indexed_with_deep_link_to_its_own_week():
    out = suchindex.bauen([_woche("2026-07-20", schlagzeile="Operator launches something")],
                          [], {})
    bericht_items = [i for i in out if i["kind"] == "bericht"]
    assert len(bericht_items) == 1
    item = bericht_items[0]
    assert item["deep_link"] == "reports/2026-07-20.html"
    assert item["operator"] == "X"


def test_perplexity_findable_via_differentiation_even_absent_from_the_weekly_report():
    diff_entries = [
        _diff_entry(operator="SK Telecom", theme="ki"),
        _diff_entry(id="http://example.com/telekom", operator="Deutsche Telekom",
                    url="http://example.com/telekom",
                    what="Perplexity fest in die MeinMagenta-App integriert."),
    ]
    theme_labels = {"ki": "KI & Assistenten"}
    out = suchindex.bauen([_woche("2026-07-20")], diff_entries, theme_labels)

    hits = _find("perplexity", out)
    assert len(hits) == 2
    assert {h["operator"] for h in hits} == {"SK Telecom", "Deutsche Telekom"}
    assert all(h["kind"] == "differenzierung" for h in hits)
    assert all(h["category"] == "KI & Assistenten" for h in hits)
    assert all(h["deep_link"] == "differenzierung.html#dz-theme-ki" for h in hits)


def test_search_index_is_empty_when_theres_nothing_to_index():
    assert suchindex.bauen([], [], {}) == []


# ------------------------------------------------ was am 08.08.2026 dazukam
def test_die_ueberschrift_ist_die_der_seiten_nicht_der_zusammenfassungssatz():
    """`schlagzeile` ist die Zeile, die der Rest des Portals zeigt
    (html._schlagzeile). Der Index las bis zum 08.08.2026 `de_title` - also
    den Zusammenfassungssatz - und zeigte damit fuer dieselbe Meldung eine
    andere Ueberschrift als jede Seite, auf die er verlinkte."""
    out = suchindex.bauen([_woche("2026-07-20", schlagzeile="Jio bündelt OTT",
                                  de_title="Reliance Jio hat einen Tarif eingeführt, der ...")],
                          [], {})
    assert out[0]["title"] == "Jio bündelt OTT"


def test_die_aktionen_sind_auffindbar_und_verlinken_ihren_markenblock():
    out = suchindex.bauen([], [], {}, promo_aktionen=[_aktion()],
                          mechanik_label={"zugabe": "Zugabe zum Tarif"})
    assert len(out) == 1
    a = out[0]
    assert a["kind"] == "promo"
    assert a["operator"] == "congstar"
    assert a["category"] == "Zugabe zum Tarif"
    assert a["deep_link"] == "promo/index.html#marke-congstar"
    assert not a["status"]


def test_eine_ausgelaufene_aktion_sagt_dass_sie_ausgelaufen_ist():
    """Sie faellt nicht aus dem Index - sie IST die Historie, nach der gesucht
    wird. Aber sie steht in der Rangfolge hinter den laufenden."""
    out = suchindex.bauen([], [], {}, promo_aktionen=[_aktion(status="ausgelaufen")])
    assert out[0]["status"] == "ausgelaufen"
    assert out[0]["relevance"] < suchindex.bauen(
        [], [], {}, promo_aktionen=[_aktion()])[0]["relevance"]


def test_eine_aktion_ohne_schlagzeile_oder_quelle_kommt_nicht_in_den_index():
    assert suchindex.bauen([], [], {}, promo_aktionen=[_aktion(headline="")]) == []
    assert suchindex.bauen([], [], {}, promo_aktionen=[_aktion(url="")]) == []


def test_das_bild_traegt_seinen_ordner_schon_im_index():
    """Damit app.js nicht wissen muss, aus welchem Ordner welche Gattung ihre
    Bilder bezieht - Meldungen aus images/, Aktionen aus promo/images/."""
    out = suchindex.bauen(
        [_woche("2026-07-20", image="a.jpg", image_w=1200, image_h=800)],
        [_diff_entry(image="b.jpg", image_w=800, image_h=450)],
        {"ki": "KI & Assistenten"},
        promo_aktionen=[_aktion(image="c.jpg", image_w=900, image_h=500)])
    nach_art = {e["kind"]: e for e in out}
    assert nach_art["bericht"]["image"] == "images/a.jpg"
    assert nach_art["bericht"]["image_w"] == 1200
    assert nach_art["differenzierung"]["image"] == "images/b.jpg"
    assert nach_art["promo"]["image"] == "promo/images/c.jpg"


def test_ohne_bild_steht_kein_leeres_bildfeld_im_index():
    """Ein leerer String waere im Browser eine Bild-URL auf die Seite selbst -
    also ein Ladefehler statt einer Schriftkachel."""
    out = suchindex.bauen([_woche("2026-07-20")], [], {})
    assert "image" not in out[0]


def test_die_interne_einordnung_verlaesst_den_index_nicht():
    """`why_it_matters` ist die Analystennotiz. Der Index wird vom Browser
    geladen - was hier steht, ist veroeffentlicht."""
    out = suchindex.bauen(
        [_woche("2026-07-20", why_it_matters="Interne Einordnung.")], [], {})
    assert "why_it_matters" not in out[0]
    assert "Interne Einordnung" not in str(out)


def test_der_meldungstermin_schlaegt_den_ausgabetag():
    """Eine Chronik, die nach Ausgabetagen sortiert, zeigt vier Ereignisse
    desselben Tages, die drei Wochen auseinanderliegen."""
    out = suchindex.bauen([_woche("2026-08-07", date="2026-07-02")], [], {})
    assert out[0]["date"] == "2026-07-02"
    ohne = suchindex.bauen([_woche("2026-08-07", date=None)], [], {})
    assert ohne[0]["date"] == "2026-08-07"


def test_der_markenanker_ist_derselbe_wie_auf_der_promo_uebersicht():
    """Der Index schreibt den Link, promo.py setzt den Anker - laufen die
    zwei auseinander, springt die Suche ins Leere."""
    from telco_radar.report.promo import marken_anker as promo_seite
    assert promo_seite("O2 / Telefónica Deutschland") \
        == suchindex.marken_anker("O2 / Telefónica Deutschland")
    assert suchindex.marken_anker("1&1 Mobilfunk") == "marke-1-1-mobilfunk"


def test_meistgenannt_zaehlt_die_redaktionellen_bereiche_nicht_die_aktionen():
    """256 der 1060 Eintraege sind Promo-Aktionen und alle deutsch: gezaehlt
    man sie mit, stuenden dort winSIM und simplytel vor AT&T."""
    index = suchindex.bauen(
        [_woche("2026-07-20", operator="AT&T")], [],
        {}, promo_aktionen=[_aktion(brand="winSIM", url=f"https://w.de/{i}",
                                    headline=f"Aktion {i}")
                            for i in range(5)])
    assert suchindex.haeufigste_absender(index) == ["AT&T"]
