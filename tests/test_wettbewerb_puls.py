from telco_radar.report import wettbewerb_puls as wp


def _laeufe():
    return [
        {"date": "2026-09-02", "ausfall": False},
        {"date": "2026-09-09", "ausfall": True},
        {"date": "2026-09-11", "ausfall": True},
        {"date": "2026-09-23", "ausfall": False},
        {"date": "2026-10-07", "ausfall": False},
    ]


def _daten():
    return {
        "deutsche-telekom": ["2026-09-01", "2026-09-03", "2026-10-06", "2026-10-07"],
        "1-1": ["2026-09-10", "2026-10-08", "2026-05-04"],
    }


def test_wochen_zaehlen_nur_gelesene_laeufe():
    p = wp.puls(_daten(), _laeufe(), "2026-10-07")
    assert len(p["wochen"]) == wp.WOCHEN
    zustand = {w["montag"]: w["zustand"] for w in p["wochen"]}
    assert zustand["2026-08-31"] == wp.GELESEN
    assert zustand["2026-09-07"] == wp.AUSFALL
    assert zustand["2026-09-14"] == wp.OHNE_LAUF
    assert zustand["2026-10-05"] == wp.GELESEN
    telekom = next(r for r in p["reihen"] if r["anker"] == "deutsche-telekom")
    werte = dict(zip([w["montag"] for w in p["wochen"]], telekom["werte"], strict=True))
    assert werte["2026-08-31"] == 2
    assert werte["2026-09-21"] == 0
    assert werte["2026-09-07"] is None
    assert telekom["diese_woche"] == 2
    assert telekom["name"] == "Telekom"


def test_gegenprobe_summe_gleich_eintraege_in_gelesenen_wochen():
    p = wp.puls(_daten(), _laeufe(), "2026-10-07")
    gelesen = {w["montag"] for w in p["wochen"] if w["zustand"] == wp.GELESEN}
    for r in p["reihen"]:
        erwartet = sum(
            1
            for d in _daten()[r["anker"]]
            if wp._montag(wp.date.fromisoformat(d)).isoformat() in gelesen
        )
        assert sum(v for v in r["werte"] if v is not None) == erwartet
    eins = next(r for r in p["reihen"] if r["anker"] == "1-1")
    assert eins["werte"][-1] == 1


def test_ausfall_spanne_und_luecke_im_bild():
    p = wp.puls(_daten(), _laeufe(), "2026-10-07")
    assert p["ausfall"] == {"von": "9.9.", "bis": "11.9."}
    bild = str(wp.svg(p))
    assert "Bewertung ausgefallen" in bild
    assert "9.9. bis 11.9., keine Meldung bewertet" in bild
    assert bild.count('class="puls-luecke"') == 1


def test_ohne_stand_leer():
    assert wp.puls(_daten(), [], "") == {"wochen": [], "reihen": [], "ausfall": None}
    assert str(wp.svg({"wochen": [], "reihen": [], "ausfall": None})) == ""


def test_aus_ansicht_liest_chronik():
    ansicht = {
        "stand": "2026-10-07",
        "wettbewerber": [
            {
                "anker": "telefonica-o2",
                "monate": [
                    {"eintraege": [{"datum": "2026-10-06"}, {"datum": "2026-10-05"}]}
                ],
            }
        ],
    }
    p = wp.aus_ansicht(ansicht, _laeufe())
    assert p["reihen"][0]["diese_woche"] == 2
    assert p["reihen"][0]["klasse"] == "o2"


def test_themen_summieren_auf_alle_eintraege():
    rubriken = ["Tarif"] * 5 + ["Netz"] * 3 + ["KI", "Geräte", "Marke", "Sport"]
    t = wp.themen(rubriken)
    assert [x["name"] for x in t] == ["Tarif", "Netz", "Geräte", "KI", wp.WEITERE]
    assert sum(x["n"] for x in t) == len(rubriken)
    assert t[0]["prozent"] == 42
    assert t[-1]["n"] == 2
    assert wp.themen([]) == []


def test_aus_ansicht_haengt_themen_je_wettbewerber_an():
    ansicht = {
        "stand": "2026-10-07",
        "wettbewerber": [
            {
                "anker": "1-1",
                "monate": [
                    {
                        "eintraege": [
                            {"datum": "2026-10-06", "rubrik": "Netz"},
                            {"datum": "2026-10-05", "rubrik": ""},
                        ]
                    }
                ],
            }
        ],
    }
    t = wp.aus_ansicht(ansicht, _laeufe())["themen"]["1-1"]
    assert {x["name"]: x["n"] for x in t} == {"Netz": 1, "Sonstiges": 1}


def test_gleichstand_am_ende_zeichnet_beide_namen():
    daten = wp.puls(
        {"telefonica-o2": ["2026-10-06"], "1-1": ["2026-10-06"]},
        _laeufe(),
        "2026-10-07",
    )
    bild = str(wp.svg(daten))
    assert "O2 1" in bild and "1&amp;1 1" in bild
