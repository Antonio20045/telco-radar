"""Klick-Karte Format 2 im Lauf: Marken, Werte, feste Dimension, Vorbereitung, Dialog.

Jede Seite ist ein BEISPIEL nach einem Muster der Erkundung vom 07.10.2026 (o2:
Label neben dem Radio, Tarifname mit wechselndem Preis; congstar: Marke je Dimension,
Wert am Input im Label, „36 mtl. Zahlungen“, Rückgabedeal ab Werk an; 1&1: Laufzeit
fest, Zubehör vorgewählt, Gerätename nur im ``aria-label``; Telekom: Preisübersicht
im Dialog; freenet: Klassen-Token ``-active``). Ein lokaler Server liefert Seite und
Antworten; keine Anfrage verlässt den Rechner.
"""

from __future__ import annotations

import pytest
from klickbeispiel import karte, laufe, nach_auswahl, preis, seite

pytestmark = pytest.mark.browser

O2_KOERPER = """
<div id="speicher">
  <div><input type="radio" hidden checked><label>128 GB</label></div>
  <div><input type="radio" hidden><label>256 GB</label></div>
</div>
<div id="tarif">
  <div class="panel"><input type="radio" hidden checked><label data-t="S"></label></div>
  <div class="panel"><input type="radio" hidden><label data-t="M"></label></div>
</div>
<div id="laufzeit">
  <div><input type="radio" hidden checked><label>36 Monate</label></div>
  <div><input type="radio" hidden><label>24 Monate</label></div>
</div>
<section id="preis"></section>"""
O2_SKRIPT = """
const auswahl = {speicher: "128", tarif: "S", laufzeit: "36"};
const RATE = {"128": 30, "256": 35};
const TARIF = {S: 19.99, M: 29.99};
function wert(gruppe, label) {
  return gruppe === "tarif" ? label.dataset.t : label.innerText.split(" ")[0];
}
function beschrifte() {
  for (const l of document.querySelectorAll("#tarif label")) {
    const zuschlag = auswahl.laufzeit === "24" ? 5 : 0;
    const summe = RATE[auswahl.speicher] + zuschlag + TARIF[l.dataset.t];
    l.innerText = "Tarif " + l.dataset.t + " mtl. " + euro(summe);
  }
}
for (const gruppe of ["speicher", "tarif", "laufzeit"]) {
  for (const label of document.querySelectorAll("#" + gruppe + " label")) {
    label.addEventListener("click", () => {
      for (const e of document.querySelectorAll("#" + gruppe + " input")) {
        e.checked = false;
      }
      label.previousElementSibling.checked = true;
      auswahl[gruppe] = wert(gruppe, label);
      beschrifte();
      lade(auswahl);
    });
  }
}
beschrifte();
lade(auswahl);"""
O2_KNOEPFE = {
    "speicher": {"selektor": "#speicher label"},
    "tarif": {"selektor": "#tarif label", "muster": r"^(.*?) +mtl\."},
    "laufzeit": {"selektor": "#laufzeit label"},
    "gewaehlt": {"passt": "input:checked + label"},
}
CONGSTAR_KOERPER = """
<div id="speicher">
  <button type="button" aria-checked="true" aria-label="128 GB">128 GB</button>
  <button type="button" aria-checked="false" aria-label="256 GB">256 GB</button>
</div>
<div id="tarif">
  <label data-selected="true"><input type="radio" name="t" value="540"
    aria-label="Tarifoption Allnet S" hidden checked><span>20 GB 25,00 € mtl.</span>
  </label>
  <label data-selected="false"><input type="radio" name="t" value="541"
    aria-label="Tarifoption Allnet M" hidden><span>50 GB 30,00 € mtl.</span></label>
</div>
<div id="laufzeit">
  <label data-selected="true"><input type="radio" name="l" hidden checked>36 mtl.
    Zahlungen</label>
  <label data-selected="false"><input type="radio" name="l" hidden>24 mtl.
    Zahlungen</label>
</div>
<button type="button" id="rueckgabe" aria-checked="true">Rückgabedeal</button>
<section id="preis"></section>"""
CONGSTAR_SKRIPT = """
const SCHALTER_FEST = @FEST@;
const auswahl = {speicher: "128", tarif: "S", laufzeit: "36", rueckgabe: "ja"};
const schalter = document.getElementById("rueckgabe");
function tarif(l) { return l.querySelector("input").getAttribute("aria-label"); }
function markiere() {
  for (const k of document.querySelectorAll("#speicher button")) {
    const an = k.getAttribute("aria-label") === auswahl.speicher + " GB";
    k.setAttribute("aria-checked", String(an));
  }
  for (const l of document.querySelectorAll("#tarif label")) {
    l.dataset.selected = String(tarif(l).endsWith(" " + auswahl.tarif));
  }
  for (const l of document.querySelectorAll("#laufzeit label")) {
    l.dataset.selected = String(l.innerText.startsWith(auswahl.laufzeit + " "));
  }
  schalter.setAttribute("aria-checked", String(auswahl.rueckgabe === "ja"));
}
for (const k of document.querySelectorAll("#speicher button")) {
  k.addEventListener("click", () => {
    auswahl.speicher = k.getAttribute("aria-label").split(" ")[0];
    markiere(); lade(auswahl);
  });
}
for (const l of document.querySelectorAll("#tarif label")) {
  l.addEventListener("click", (e) => {
    e.preventDefault();
    auswahl.tarif = tarif(l).split(" ").pop();
    markiere(); lade(auswahl);
  });
}
for (const l of document.querySelectorAll("#laufzeit label")) {
  l.addEventListener("click", (e) => {
    e.preventDefault();
    auswahl.laufzeit = l.innerText.split(" ")[0];
    markiere(); lade(auswahl);
  });
}
schalter.addEventListener("click", () => {
  if (SCHALTER_FEST) return;
  auswahl.rueckgabe = auswahl.rueckgabe === "ja" ? "nein" : "ja";
  markiere(); lade(auswahl);
});
markiere();
lade(auswahl);"""
CONGSTAR_KNOEPFE = {
    "speicher": {
        "selektor": "#speicher button",
        "wert": "aria-label",
        "gewaehlt": {"attribut": "aria-checked", "wert": "true"},
    },
    "tarif": {
        "selektor": "#tarif label",
        "wert_in": "input",
        "wert": "aria-label",
        "muster": "^Tarifoption (.+)$",
        "gewaehlt": {"attribut": "data-selected", "wert": "true"},
    },
    "laufzeit": {
        "selektor": "#laufzeit label",
        "muster": r"^(\d+) mtl\. Zahlungen$",
        "gewaehlt": {"passt": '[data-selected="true"]'},
    },
}
RUECKGABE_AUS = [{"klick": "#rueckgabe", "bis": '[aria-checked="false"]'}]
EINSUNDEINS_KOERPER = """
<div id="konfig">
  <label class="kachel" aria-label="Speicherauswahl Beispielhandy X"><input
    type="radio" name="hw.storage" value="128" hidden checked>128 GB</label>
  <label class="kachel" aria-label="Speicherauswahl Beispielhandy X"><input
    type="radio" name="hw.storage" value="256" hidden>256 GB</label>
</div>
<ul id="zubehoer">
  <li><label class="toggle"><input type="radio" name="z" id="mit" hidden
    checked>Kopfhörer für 0,– €/Monat</label></li>
  <li><label class="toggle"><input type="radio" name="z" id="ohne" hidden>Ohne
    Kopfhörer</label></li>
</ul>
<section id="preis"></section>"""
EINSUNDEINS_SKRIPT = """
const auswahl = {speicher: "128", tarif: "S", laufzeit: "36", zubehoer: "ja"};
for (const i of document.querySelectorAll("#konfig input")) {
  i.addEventListener("change", () => { auswahl.speicher = i.value; lade(auswahl); });
}
for (const i of document.querySelectorAll("#zubehoer input")) {
  i.addEventListener("change", () => {
    auswahl.zubehoer = i.id === "mit" ? "ja" : "nein";
    lade(auswahl);
  });
}
lade(auswahl);"""
EINSUNDEINS_KNOEPFE = {
    "speicher": {
        "selektor": "#konfig label.kachel",
        "wert_in": "input",
        "wert": "value",
        "gewaehlt": {"passt": ":has(input:checked)"},
    },
    "tarif": {"fest": "S"},
    "laufzeit": {"fest": 36},
}
EINSUNDEINS_KANARIE = {
    "selektor": "#konfig label.kachel",
    "attribut": "aria-label",
    "enthaelt": "Speicherauswahl {modell}",
}
TELEKOM_KOERPER = """
<div id="speicher">
  <button type="button" class="chip -active" data-wert="128">128 GB</button>
  <button type="button" class="chip" data-wert="256">256 GB</button>
</div>
<button type="button" id="uebersicht">Preisübersicht anzeigen</button>"""
TELEKOM_SKRIPT = """
const auswahl = {speicher: "128", tarif: "S", laufzeit: "36"};
for (const k of document.querySelectorAll("#speicher button")) {
  k.addEventListener("click", () => {
    for (const a of document.querySelectorAll("#speicher button")) {
      a.classList.toggle("-active", a === k);
    }
    auswahl.speicher = k.dataset.wert;
    lade(auswahl);
  });
}
document.getElementById("uebersicht").addEventListener("click", () => {
  const schicht = document.createElement("div");
  schicht.id = "schicht";
  schicht.style.cssText = "position:fixed;inset:0;background:white";
  schicht.innerHTML = '<section id="preis"></section>'
    + '<button id="zu">Schließen</button>';
  document.body.appendChild(schicht);
  zeige(window.letzte);
  document.getElementById("zu").addEventListener("click", () => schicht.remove());
});
lade(auswahl);"""
TELEKOM_KNOEPFE = {
    "speicher": {
        "selektor": "#speicher button",
        "wert": "data-wert",
        "gewaehlt": {"passt": ".-active"},
    },
    "tarif": {"fest": "S"},
    "laufzeit": {"fest": 36},
}
TELEKOM_DIALOG = {"selektor": "#preis", "oeffnen": "#uebersicht", "schliessen": "#zu"}


def _o2(frage: dict) -> dict:
    lz = int(frage["laufzeit"])
    return {
        "auswahl": {
            "speicher": f"{frage['speicher']} GB",
            "tarif": f"Tarif {frage['tarif']}",
            "laufzeit": lz,
        },
        "preis": preis(frage["speicher"], frage["tarif"], lz),
    }


def _congstar(frage: dict) -> dict:
    lz = int(frage["laufzeit"])
    abzug = 6.5 if frage["rueckgabe"] == "ja" else 0.0
    return {
        "auswahl": {
            "speicher": f"{frage['speicher']} GB",
            "tarif": f"Allnet {frage['tarif']}",
            "laufzeit": lz,
        },
        "preis": preis(frage["speicher"], frage["tarif"], lz, abzug),
    }


def _fest_36(frage: dict) -> dict:
    zuschlag = -2.0 if frage.get("zubehoer") == "ja" else 0.0
    return {
        "auswahl": {"speicher": frage["speicher"], "tarif": "S", "laufzeit": 36},
        "preis": preis(frage["speicher"], "S", 36, zuschlag),
    }


def test_o2_marke_am_radio_davor_und_tarifname_ohne_wechselnden_preis(chromium):
    lauf, _ = laufe(
        chromium, seite(O2_KOERPER, O2_SKRIPT), _o2, karte(knoepfe=O2_KNOEPFE)
    )

    ergebnisse = nach_auswahl(lauf)
    assert lauf.status == "gelesen", lauf.grund
    assert len(ergebnisse) == 8
    assert {e.status for e in ergebnisse.values()} == {"erfasst"}
    assert ergebnisse[("256 GB", "Tarif M", 24)].werte.rate == 40.0
    assert ergebnisse[("128 GB", "Tarif S", 36)].werte.volumen_gb == 20.0


def test_o2_mit_marke_am_label_findet_keine_auswahl(chromium):
    knoepfe = {**O2_KNOEPFE, "gewaehlt": {"attribut": "aria-checked", "wert": "true"}}

    lauf, _ = laufe(chromium, seite(O2_KOERPER, O2_SKRIPT), _o2, karte(knoepfe=knoepfe))

    assert lauf.ergebnisse
    assert "erfasst" not in {e.status for e in lauf.ergebnisse}
    assert "Seite zeigt keine Auswahl" in lauf.ergebnisse[0].grund


def test_congstar_marke_je_dimension_wert_im_label_und_rueckgabedeal_aus(chromium):
    html = seite(CONGSTAR_KOERPER, CONGSTAR_SKRIPT.replace("@FEST@", "false"))
    k = karte(knoepfe=CONGSTAR_KNOEPFE, vorbereitung=RUECKGABE_AUS)

    lauf, server = laufe(chromium, html, _congstar, k)

    ergebnisse = nach_auswahl(lauf)
    assert lauf.status == "gelesen", lauf.grund
    assert {e.status for e in ergebnisse.values()} == {"erfasst"}
    speicher, laufzeiten = ("128 GB", "256 GB"), (36, 24)
    assert set(ergebnisse) == {
        (s, f"Allnet {t}", lz) for s in speicher for t in "SM" for lz in laufzeiten
    }
    assert ergebnisse[("128 GB", "Allnet S", 36)].werte.rate == 30.0
    assert "rueckgabe=nein" in server.mit("/api/preis")[1]


def test_congstar_ohne_vorbereitung_liest_den_rueckgabedeal(chromium):
    html = seite(CONGSTAR_KOERPER, CONGSTAR_SKRIPT.replace("@FEST@", "false"))

    lauf, server = laufe(chromium, html, _congstar, karte(knoepfe=CONGSTAR_KNOEPFE))

    ergebnisse = nach_auswahl(lauf)
    assert ergebnisse[("128 GB", "Allnet S", 36)].werte.rate == 23.5
    assert not any("rueckgabe=nein" in a for a in server.mit("/api/preis"))


def test_nicht_erreichte_vorbereitung_stoert_den_lauf(chromium):
    html = seite(CONGSTAR_KOERPER, CONGSTAR_SKRIPT.replace("@FEST@", "true"))
    k = karte(knoepfe=CONGSTAR_KNOEPFE, vorbereitung=RUECKGABE_AUS)

    lauf, _ = laufe(chromium, html, _congstar, k, frist_ms=1000)

    assert lauf.status == "gestoert"
    assert "Vorbereitung: #rueckgabe" in lauf.grund
    assert lauf.ergebnisse == []


def test_fehlendes_element_der_vorbereitung_stoert_den_lauf(chromium):
    html = seite(CONGSTAR_KOERPER, CONGSTAR_SKRIPT.replace("@FEST@", "false"))
    fehlt = [{"klick": "#gibt-es-nicht", "bis": ":checked"}]
    k = karte(knoepfe=CONGSTAR_KNOEPFE, vorbereitung=fehlt)

    lauf, _ = laufe(chromium, html, _congstar, k, frist_ms=1000)

    assert lauf.status == "gestoert"
    assert lauf.grund == "Vorbereitung: #gibt-es-nicht nicht gefunden"


def test_einsundeins_feste_laufzeit_zubehoer_ab_und_kanarie_je_geraet(chromium):
    ohne = {"klick": "#zubehoer label:has(#ohne)", "pruefe": "#ohne", "bis": ":checked"}
    vorbereitung = [ohne]
    k = karte(
        knoepfe=EINSUNDEINS_KNOEPFE,
        vorbereitung=vorbereitung,
        kanarie=EINSUNDEINS_KANARIE,
    )
    html = seite(EINSUNDEINS_KOERPER, EINSUNDEINS_SKRIPT)

    lauf, server = laufe(chromium, html, _fest_36, k, modell="Beispielhandy X")

    ergebnisse = nach_auswahl(lauf)
    assert lauf.status == "gelesen", lauf.grund
    assert set(ergebnisse) == {("128", "S", 36), ("256", "S", 36)}
    assert {e.status for e in ergebnisse.values()} == {"erfasst"}
    assert [ergebnisse[(s, "S", 36)].werte.rate for s in ("128", "256")] == [30.0, 35.0]
    assert lauf.struktur.knoepfe_gesucht == lauf.struktur.knoepfe_gefunden
    assert all("zubehoer=nein" in a for a in server.mit("/api/preis")[1:])


@pytest.mark.parametrize(
    ("modell", "grund"),
    [
        (None, "Kanarienwert braucht den Modellnamen des Geräts ({modell})"),
        (
            "Anderes Handy",
            "Kanarienwert fehlt: #konfig label.kachel [aria-label] ohne"
            " „Speicherauswahl Anderes Handy“",
        ),
    ],
)
def test_kanarie_je_geraet_ohne_passenden_modellnamen_ist_gestoert(
    chromium, modell, grund
):
    k = karte(knoepfe=EINSUNDEINS_KNOEPFE, kanarie=EINSUNDEINS_KANARIE)
    html = seite(EINSUNDEINS_KOERPER, EINSUNDEINS_SKRIPT)

    lauf, _ = laufe(chromium, html, _fest_36, k, frist_ms=1000, modell=modell)

    assert lauf.status == "gestoert"
    assert lauf.grund == grund
    assert lauf.ergebnisse == []


def test_telekom_preisuebersicht_im_dialog_und_klassenmarke(chromium):
    k = karte(knoepfe=TELEKOM_KNOEPFE, zusammenfassung=TELEKOM_DIALOG)

    lauf, _ = laufe(chromium, seite(TELEKOM_KOERPER, TELEKOM_SKRIPT), _fest_36, k)

    ergebnisse = nach_auswahl(lauf)
    assert lauf.status == "gelesen", lauf.grund
    assert {e.status for e in ergebnisse.values()} == {"erfasst"}
    assert ergebnisse[("256", "S", 36)].werte.rate == 35.0


def test_telekom_ohne_oeffnen_findet_keine_zusammenfassung(chromium):
    k = karte(knoepfe=TELEKOM_KNOEPFE)

    lauf, _ = laufe(
        chromium, seite(TELEKOM_KOERPER, TELEKOM_SKRIPT), _fest_36, k, frist_ms=1000
    )

    assert lauf.ergebnisse
    assert {e.status for e in lauf.ergebnisse} == {"nicht_erfasst"}
    assert lauf.ergebnisse[0].grund == "Preiszusammenfassung nicht gefunden (#preis)"
