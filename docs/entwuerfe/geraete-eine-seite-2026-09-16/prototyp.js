/* =====================================================================
   prototyp.js — Entwurf v2 „EINE Geräteseite" (16.09.2026, Nacht)
   Nur Reiter-Umschalten (derselbe Mechanismus wie app.js: data-tafel +
   .gr-tafel--aus) und Suchfeld-Live-Vorschau (Verhalten 1:1 aus Entwurf
   v1). Kein Live-app.js. Alle Zahlen aus zahlen.json (Bestand 15.09.2026)
   inklusive Feld `historie` (TCO-Zeitreihe 12.–15.09. aus
   geraete_tco_historie.jsonl, gezogen von historie_sammeln.py), inline
   im HTML eingebettet (id="gr-zahlen") — kein fetch, der Entwurf läuft
   per Doppelklick (file://).

   DER EINE GRAPH ist die TCO-ZEITREIHE (Antonios Entscheidung, 16.09.):
   „Y-Achse ist Euro-Kosten, X-Achse ist das DATUM. Ich möchte die
   verschiedenen Messtage sehen — an welchen Tagen haben sie die Preise
   runtergemacht, an welchen hoch." Kein Formen-Umschalter mehr, keine
   Stapelbalken, keine Band-Kurve. X-Skala ist die ECHTE Datumsdistanz
   (keine ordinale Achse — derselbe Befund, der die alte Live-Grafik
   falsch machte), und eine Linie verbindet nur ECHTE Messungen: fehlt
   einem Anbieter ein Messtag, fehlt der Punkt — nichts interpoliert.
   ===================================================================== */
(function () {
  "use strict";

  var BAND_KURZ = { klein: "Klein", mittel: "Mittel", gross: "Groß" };
  var BAND_BEREICH = null;            // aus zahlen.json (baender_meta)
  var ANB_FARBE = {                   // dieselben Werte wie --anb in style.css
    "Telekom": "#e20074", "Vodafone": "#e60000", "o2": "#0019a5",
    "1&1": "#00589e", "congstar": "#f5a800"
  };
  var ANB_REIHENFOLGE = ["Telekom", "Vodafone", "o2", "1&1", "congstar"];

  var Z = null;
  /* Startzustand nach Koordinator-Regel: die meisten ANBIETER in der
     Historie, bei Gleichstand die meisten PUNKTE. Gemessen von
     historie_sammeln.py über alle (Modell × Band):
       4 Anbieter · 13 Punkte: apple-iphone-17-pro-256 · klein  <- DAS
       4 Anbieter · 10 Punkte: samsung-galaxy-z-fold8-256 · klein
     (13 statt 16 Punkte heißt: ein Anbieter fehlt an Messtagen — genau
     die Aussage, die dieser Graph führen soll.) */
  var zustand = { modell: "apple-iphone-17-pro-256", band: "klein" };

  function $(id) { return document.getElementById(id); }
  function euro(n) {
    return n.toLocaleString("de-DE", { minimumFractionDigits: 2 }) + " €";
  }
  function euro0(n) {
    return n.toLocaleString("de-DE", { maximumFractionDigits: 0 }) + " €";
  }
  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function datumDe(iso) {          // „15. September 2026" (Live-Schreibweise)
    var t = new Date(iso + "T00:00:00");
    return t.getDate() + ". " +
      ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
       "August", "September", "Oktober", "November", "Dezember"][t.getMonth()] +
      " " + t.getFullYear();
  }
  function datumKurz(iso) {        // „15.09.2026" (unter dem Endnamen)
    return iso.slice(8, 10) + "." + iso.slice(5, 7) + "." + iso.slice(0, 4);
  }
  function tagMonat(iso) {         // „12.9." (X-Achsen-Tick, echtes Format)
    return parseInt(iso.slice(8, 10), 10) + "." +
           parseInt(iso.slice(5, 7), 10) + ".";
  }
  function kurzName(mod) {
    // „Apple iPhone 17 Pro 256 GB" → „iPhone 17 Pro"
    return mod.titel
      .replace(mod.hersteller + " ", "")
      .replace(new RegExp(" " + mod.speicher + " GB$"), "");
  }

  /* ---------------- Reiter (Mechanik wie app.js, nur kleiner) -------- */
  function reiterAn() {
    var knoepfe = document.querySelectorAll(".gr-reiter button[data-tafel]");
    function zeige(k) {
      Array.prototype.forEach.call(knoepfe, function (b) {
        var ziel = document.getElementById(b.getAttribute("data-tafel"));
        var aktiv = b === k;
        b.setAttribute("aria-selected", aktiv ? "true" : "false");
        if (ziel) ziel.classList.toggle("gr-tafel--aus", !aktiv);
      });
    }
    Array.prototype.forEach.call(knoepfe, function (b) {
      b.addEventListener("click", function () { zeige(b); });
    });
    var hash = (location.hash || "").replace(/^#/, "");
    var ziel = document.querySelector('.gr-reiter button[data-tafel="' + hash + '"]');
    if (ziel) zeige(ziel);
  }

  /* ---------------- Antwort-Satz (reine Ableitung aus den Zeilen) ---- */
  function antwortSatz(mod, band) {
    var b = mod.baender[band];
    var name = kurzName(mod);
    var bereich = BAND_BEREICH[band] ? " (" + BAND_BEREICH[band] + ")" : "";
    if (!b || b.zeilen.length === 0) {
      var da = Object.keys(mod.baender).filter(function (k) {
        return mod.baender[k] && mod.baender[k].zeilen.length; });
      return "Beim " + name + " im Band " + BAND_KURZ[band] + bereich +
        " führt kein Anbieter ein Bündel." +
        (da.length ? " Bündel stehen in: " +
          da.map(function (k) { return BAND_KURZ[k]; }).join(", ") + "." : "");
    }
    var zeilen = b.zeilen.slice().sort(function (x, y) { return x.tco24 - y.tco24; });
    var best = zeilen[0];
    var vf = b.zeilen.filter(function (z) { return z.referenz; })[0] || null;
    var satz;
    if (best.referenz) {
      var zweit = zeilen[1];
      satz = "Beim " + name + " im Band " + BAND_KURZ[band] + bereich +
        " führt " + (zeilen.length === 1 ? "nur " : "") +
        "Vodafone: <b class='v2-zahl'>" + best.tco24_text +
        "</b> über 24 Monate (TCO-24), Ø <b class='v2-zahl'>" +
        best.schnitt_text.replace(" €/M.", "") + " €/Monat</b> (" +
        best.tarif + (best.gb ? " · " + best.gb : "") + ").";
      if (zweit && zeilen.length > 1) {
        satz += " Nächster Anbieter: " + zweit.anbieter + " (" +
          zweit.tco24_text + ").";
      }
    } else {
      satz = "Beim " + name + " im Band " + BAND_KURZ[band] + bereich +
        " ist " + best.anbieter + " am günstigsten: <b class='v2-zahl'>" +
        best.tco24_text + "</b> über 24 Monate (TCO-24), Ø <b class='v2-zahl'>" +
        best.schnitt_text.replace(" €/M.", "") + " €/Monat</b> (" +
        best.tarif + (best.gb ? " · " + best.gb : "") + ")";
      if (vf) {
        var d = Math.abs(vf.tco24 - best.tco24);
        satz += " — <b class='v2-zahl'>" + euro(d) +
          "</b> unter der Vodafone-Referenz (" + vf.tco24_text + ").";
      } else {
        satz += " — Vodafone führt in diesem Band kein Bündel.";
      }
    }
    return satz;
  }

  /* ---------------- Lücken-Zeile: EIN Satz, keine je-Anbieter-Zeilen - */
  function lueckenSatz(mod, band) {
    var b = mod.baender[band];
    var el = $("v2-luecke");
    if (!b || b.luecken.length === 0) { el.hidden = true; return; }
    var bandWort = { klein: "klein", mittel: "mittel", gross: "groß" };
    var bandLuecke = [], keinBuendel = [];
    b.luecken.forEach(function (l) {
      (l.grund === "kein Bündel in diesem Band" ? bandLuecke : keinBuendel)
        .push(l);
    });
    var teile = [];
    if (bandLuecke.length)
      teile.push("Kein Bündel in diesem Band: " + bandLuecke.map(function (l) {
        var name = l.anbieter;
        if (l.alternativ && l.alternativ.length) {
          name += " (" + l.alternativ.map(function (alt) {
            return bandWort[alt.band] + " " + alt.tco_text;
          }).join(" · ") + ")";
        }
        return name;
      }).join(", ") + ".");
    if (keinBuendel.length)
      teile.push(keinBuendel.map(function (l) { return l.anbieter; }).join(", ") +
        " " + (keinBuendel.length === 1 ? "führt" : "führen") +
        " das Gerät gar nicht im Bündel.");
    el.textContent = teile.join(" ");
    el.hidden = false;
  }

  /* ---------------- Der EINE Graph: TCO-Zeitreihe ----------------------
     Y = TCO-24 in € (Ticks mit Beträgen, Haarlinien-Raster), X = das
     DATUM in echter Distanz. Je Anbieter eine Linie mit PUNKT je
     Messung; Wert-Label am LETZTEN Punkt (groß) und am ersten (klein);
     Vodafone rot mit „unser Angebot"-Etikett; letzte Messung mit
     kräftigerem Punkt. Beleg-Link (↗ + Datum) am Linienende. Breite
     wird am Platzhalter GEMESSEN, die viewBox steht in px und rendert
     1:1. */
  function zeitreihe(mid, mod, band, W) {
    var serienAlle = (Z.historie && Z.historie.serien[mid]) || {};
    var serien = serienAlle[band] || {};
    var anbieter = ANB_REIHENFOLGE.filter(function (a) {
      return serien[a] && serien[a].length;
    });
    if (!anbieter.length) {
      return "<p class='v2-keine-serie'>Für " + esc(kurzName(mod)) +
        " im Band " + BAND_KURZ[band] +
        " liegt erst der Stand vom " + datumDe(Z.stand) +
        " vor — die Zeitreihe wächst mit jedem Messtag (Historie seit dem " +
        (Z.historie && Z.historie.messtage ?
          datumDe(Z.historie.messtage[0]) : "12. September 2026") + ").</p>";
    }
    var mobil = W < 640;

    // Union der Messtage DIESER (Modell, Band)-Serien — die X-Achse zeigt
    // nur Tage, an denen wirklich gemessen wurde.
    var tage = [], gesehen = {};
    anbieter.forEach(function (a) {
      serien[a].forEach(function (p) {
        if (!gesehen[p[0]]) { gesehen[p[0]] = 1; tage.push(p[0]); }
      });
    });
    tage.sort();

    var H = Math.max(mobil ? 340 : 420, Math.round(W * 0.42));
    var L = 58, R = mobil ? 96 : 158, T = 18, B = 46;
    var pw = W - L - R, ph = H - T - B;

    function tMs(iso) { return new Date(iso + "T00:00:00").getTime(); }
    var t0 = tMs(tage[0]), t1 = tMs(tage[tage.length - 1]);
    function X(iso) {
      if (t1 === t0) return L + pw / 2;
      return L + (tMs(iso) - t0) / (t1 - t0) * pw;
    }

    var werte = [];
    anbieter.forEach(function (a) {
      serien[a].forEach(function (p) { werte.push(p[1]); });
    });
    var ymin = Math.min.apply(null, werte), ymax = Math.max.apply(null, werte);
    var span = (ymax - ymin) || Math.max(ymax * 0.05, 1);
    var y0 = Math.max(0, ymin - span * 0.12), y1 = ymax + span * 0.12;
    function Y(v) { return T + (1 - (v - y0) / (y1 - y0)) * ph; }

    // Y-Ticks: „runde" Beträge (1-2-2.5-5-10-Stufen), Beschriftung in €
    function niceStep(r) {
      var p = Math.pow(10, Math.floor(Math.log(r) / Math.LN10));
      var n = r / p;
      return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
    }
    var step = niceStep((y1 - y0) / 4);

    var svg = "<div class='v2-kurve-wrap'><svg viewBox='0 0 " + W + " " + H +
      "' width='" + W + "' role='img' aria-label='TCO-24 je Messtag und Anbieter: " +
      esc(anbieter.join(", ")) + "'>";
    var v = Math.ceil(y0 / step) * step;
    while (v <= y1 + 0.01) {
      var y = Y(v);
      svg += "<line class='v2-kurve-raster' x1='" + L + "' y1='" +
        y.toFixed(1) + "' x2='" + (W - R) + "' y2='" + y.toFixed(1) +
        "'></line>" +
        "<text class='v2-kurve-achse' x='" + (L - 8) + "' y='" +
        (y + 4).toFixed(1) + "' text-anchor='end'>" + euro0(v) + "</text>";
      v += step;
    }
    // X-Ticks: jeder ECHTE Messtag, deutsches Kurzformat „12.9."
    tage.forEach(function (tag) {
      var x = X(tag);
      svg += "<line class='v2-kurve-raster' x1='" + x.toFixed(1) +
        "' y1='" + T + "' x2='" + x.toFixed(1) + "' y2='" + (T + ph) +
        "'></line>" +
        "<text class='v2-kurve-achse' x='" + x.toFixed(1) + "' y='" +
        (H - B + 22) + "' text-anchor='middle'>" + tagMonat(tag) + "</text>";
    });

    // Linien + Punkte (nur echte Messungen; Lücken bleiben Lücken)
    anbieter.forEach(function (a) {
      var farbe = ANB_FARBE[a];
      var pfad = "";
      serien[a].forEach(function (p, i) {
        pfad += (i ? "L" : "M") + X(p[0]).toFixed(1) + " " +
                Y(p[1]).toFixed(1) + " ";
      });
      if (serien[a].length > 1)
        svg += "<path class='v2-kurve-linie' d='" + pfad.trim() +
          "' stroke='" + farbe + "'></path>";
      serien[a].forEach(function (p, i) {
        var letzte = i === serien[a].length - 1;
        svg += "<circle class='v2-kurve-punkt" + (letzte ? " v2-kurve-ende" : "") +
          "' cx='" + X(p[0]).toFixed(1) + "' cy='" + Y(p[1]).toFixed(1) +
          "' r='" + (letzte ? 6 : 4.5) + "' fill='" + farbe + "'></circle>";
      });
    });

    // Wert-Labels: LETZTER Punkt je Anbieter groß (links vom Punkt, im
    // Plotraum — rechts beginnen die Endnamen), ERSTER Punkt klein
    // (rechts daneben). Kollisionsfrei je Tagesspalte: Kandidaten
    // über/unter dem Punkt, gierig die freie Seite — dieselbe Rechnung
    // wie in der alten Band-Kurve, nur jetzt je X-Position.
    function label(liste, klass, dx, ank) {
      var belegt = [];
      liste.sort(function (p, q) { return p.y - q.y; });
      liste.forEach(function (p, i) {
        var drueber = p.y - 11, drunter = p.y + 18;
        var yy = i % 2 === 0 ? drueber : drunter;
        function frei(t) {
          return !belegt.some(function (r) { return Math.abs(r - t) < (mobil ? 15 : 13); });
        }
        if (!frei(yy)) yy = frei(drueber) ? drueber : drunter;
        var s = 0;
        while (!frei(yy) && s < 5) { yy += (yy > p.y ? 15 : -15); s++; }
        belegt.push(yy);
        svg += "<text class='" + klass + "' x='" + (p.x + dx).toFixed(1) +
          "' y='" + yy.toFixed(1) + "' text-anchor='" + ank + "'>" +
          p.text + "</text>";
      });
    }
    var letzteP = [], ersteP = [];
    anbieter.forEach(function (a) {
      var s = serien[a];
      var l = s[s.length - 1], e = s[0];
      letzteP.push({ x: X(l[0]), y: Y(l[1]), text: euro0(l[1]) });
      if (s.length > 1)
        ersteP.push({ x: X(e[0]), y: Y(e[1]), text: euro0(e[1]) });
    });
    label(letzteP, "v2-kurve-wert", -10, "end");
    if (!mobil) label(ersteP, "v2-kurve-wert v2-kurve-wert--erst", 10, "start");

    // Endnamen als Beleg-Link (↗ + Abrufdatum darunter), Vodafone mit
    // „unser Angebot"-Etikett. URL aus der Zeile des Stichtags — derselbe
    // Beleg, den die Tabelle nennt.
    var zeilen = (mod.baender[band] || {}).zeilen || [];
    var urlJe = {};
    zeilen.forEach(function (z) { urlJe[z.anbieter] = z.url; });
    var enden = anbieter.map(function (a) {
      var s = serien[a];
      return { a: a, y: Y(s[s.length - 1][1]), x: X(s[s.length - 1][0]) };
    });
    enden.sort(function (p, q) { return p.y - q.y; });
    var letzteY = -99;
    enden.forEach(function (e) {
      var y = Math.max(e.y, letzteY + 46);
      letzteY = y;
      var url = urlJe[e.a] || "#";
      svg += "<a href='" + esc(url) + "' target='_blank' rel='noopener'" +
        " class='v2-kurve-link' role='link'" +
        " aria-label='Beleg bei " + esc(e.a) + " öffnen'>" +
        "<text class='v2-kurve-name' x='" + (e.x + 12).toFixed(1) +
        "' y='" + (y + 4).toFixed(1) + "' fill='" + ANB_FARBE[e.a] + "'>" +
        e.a + "<tspan class='v2-kurve-pfeil'> ↗</tspan></text></a>" +
        (e.a === "Vodafone" ?
          "<text class='v2-kurve-chip' x='" + (e.x + 12).toFixed(1) +
          "' y='" + (y + 16).toFixed(1) + "'>unser Angebot</text>" : "") +
        "<text class='v2-kurve-datum' x='" + (e.x + 12).toFixed(1) +
        "' y='" + (y + (e.a === "Vodafone" ? 29 : 16)).toFixed(1) + "'>" +
        datumKurz(serien[e.a][serien[e.a].length - 1][0]) + "</text>";
    });
    svg += "</svg></div>";
    svg += "<p class='v2-kurve-hinweis'>TCO-24 je Messtag · ein fehlender Punkt heißt: dieser Anbieter hatte an dem Tag kein Bündel in diesem Band (Linien verbinden nur echte Messungen).</p>";
    return svg;
  }

  /* ---------------- Legende: EINE Zeile über dem Diagramm -------------
     Anbieternamen mit Farb-Punkt, Vodafone rot und benannt. Mobil stehen
     die ERSTEN Werte hier (dort sind die kleinen Erst-Punkte-Labels
     ausgelassen, um Kollisionen auf 390 px zu vermeiden). */
  function legende(mid, band) {
    var serien = ((Z.historie && Z.historie.serien[mid]) || {})[band] || {};
    var anbieter = ANB_REIHENFOLGE.filter(function (a) {
      return serien[a] && serien[a].length;
    });
    if (!anbieter.length) return "";
    var mobil = window.matchMedia("(max-width:640px)").matches;
    return "<div class='v2-legende'>" + anbieter.map(function (a) {
      var zusatz = "";
      if (mobil && serien[a][0])
        zusatz = " <span class='v2-legende-ab'>ab " + euro0(serien[a][0][1]) + "</span>";
      if (a === "Vodafone") zusatz += " <span class='v2-legende-ab'>· unser Angebot</span>";
      return "<span><i style='background:" + ANB_FARBE[a] + "'></i>" +
        a + zusatz + "</span>";
    }).join("") + "</div>";
  }

  /* ---------------- Messtag-Zeile im Graphkopf ------------------------
     Die ECHTE Spanne der Tage, die dieser Graph zeigt. */
  function messtagZeile(mid, band) {
    var serien = ((Z.historie && Z.historie.serien[mid]) || {})[band] || {};
    var tage = [];
    var gesehen = {};
    Object.keys(serien).forEach(function (a) {
      serien[a].forEach(function (p) {
        if (!gesehen[p[0]]) { gesehen[p[0]] = 1; tage.push(p[0]); }
      });
    });
    if (!tage.length) return "";
    tage.sort();
    return "Messtage: " + tagMonat(tage[0]) + " bis " + tagMonat(tage[tage.length - 1]) +
      " (" + tage.length + (tage.length === 1 ? " Messung" : " Messungen") + ")";
  }

  /* ---------------- Render -------------------------------------------- */
  function render() {
    var mod = Z.modelle[zustand.modell];
    $("v2-antwort").innerHTML = antwortSatz(mod, zustand.band);
    lueckenSatz(mod, zustand.band);
    // Der Graph braucht die gerenderte Breite (Platzhalter messen, dann
    // bauen) - die viewBox steht in px und wird 1:1 ausgeliefert.
    $("v2-graph").innerHTML = legende(zustand.modell, zustand.band) +
      "<div class='v2-kurve-wrap'></div>";
    var platz = $("v2-graph").querySelector(".v2-kurve-wrap");
    var w = platz.clientWidth || 960;
    platz.outerHTML = zeitreihe(zustand.modell, mod, zustand.band, w);
    $("v2-messtage").textContent = messtagZeile(zustand.modell, zustand.band);
    history.replaceState(null, "", "?modell=" + encodeURIComponent(zustand.modell) +
      "&band=" + zustand.band);
  }

  /* ---------------- Suchfeld (Verhalten 1:1 aus Entwurf v1) ------------ */
  function treffer(eingabe) {
    var tokens = eingabe.toLowerCase().split(/\s+/).filter(Boolean);
    return Z.suchindex.filter(function (s) {
      var worte = s.titel.toLowerCase().split(/[\s·]+/).filter(Boolean);
      return tokens.every(function (t) {
        return worte.some(function (w) { return w.indexOf(t) === 0; });
      });
    }).slice(0, 8);
  }

  function vorschauZeigen(wert) {
    var box = $("v2-vorschau");
    if (wert.trim().length < 2) { box.innerHTML = ""; return; }
    var liste = treffer(wert.trim());
    $("v2-treffer").textContent = liste.length ? liste.length + " Treffer" : "kein Treffer";
    box.innerHTML = liste.map(function (s) {
      return "<button type='button' role='option' data-id='" + s.id + "'>" +
        "<span class='v2-v-titel'>" + s.titel + "</span>" +
        "<span class='v2-v-meta'>" + (s.speicher ? s.speicher + " GB · " : "") +
        s.anbieter_zahl + " Anbieter · " +
        (s.band_zahl === 1 ? "1 Band" : s.band_zahl + " Bänder") +
        "</span></button>";
    }).join("");
    box.querySelectorAll("button").forEach(function (b) {
      b.addEventListener("mousedown", function (ev) {
        ev.preventDefault();
        waehleModell(b.dataset.id);
      });
    });
  }

  function waehleModell(id) {
    zustand.modell = id;
    $("v2-vorschau").innerHTML = "";
    $("v2-suchfeld").value = Z.modelle[id].titel;
    $("v2-treffer").textContent = Z.modelle[id].anbieter_zahl + " Anbieter";
    // Band mitnehmen, wenn das Modell es führt; sonst erstes verfügbares
    var baelle = Object.keys(Z.modelle[id].baender);
    if (baelle.indexOf(zustand.band) === -1) zustand.band = baelle[0];
    setBandKnopf();
    render();
  }

  function setBandKnopf() {
    document.querySelectorAll("#v2-baender button").forEach(function (b) {
      b.setAttribute("aria-pressed", b.dataset.band === zustand.band ? "true" : "false");
    });
  }

  /* ---------------- Start ---------------------------------------------- */
  function start() {
    BAND_BEREICH = {
      klein: Z.baender_meta.klein.bereich,
      mittel: Z.baender_meta.mittel.bereich,
      gross: Z.baender_meta.gross.bereich
    };
    $("v2-treffer").textContent = Z.kopf.modelle + " Modelle";

    var params = new URLSearchParams(location.search);
    var m = params.get("modell"), b = params.get("band");
    if (m && Z.modelle[m]) zustand.modell = m;
    if (["klein", "mittel", "gross"].indexOf(b) > -1) zustand.band = b;

    $("v2-suchfeld").value = Z.modelle[zustand.modell].titel;
    setBandKnopf();

    $("v2-baender").addEventListener("click", function (ev) {
      var k = ev.target.closest("button[data-band]");
      if (!k) return;
      zustand.band = k.dataset.band;
      setBandKnopf();
      render();
    });

    var feld = $("v2-suchfeld");
    feld.addEventListener("input", function () { vorschauZeigen(feld.value); });
    feld.addEventListener("focus", function () { vorschauZeigen(feld.value); });
    feld.addEventListener("blur", function () {
      setTimeout(function () { $("v2-vorschau").innerHTML = ""; }, 150);
    });
    feld.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape") $("v2-vorschau").innerHTML = "";
      if (ev.key === "Enter") {
        var erster = $("v2-vorschau").querySelector("button");
        if (erster) { ev.preventDefault(); waehleModell(erster.dataset.id); }
      }
    });

    // Die Breite hängt am Viewport: bei Resize neu rechnen (entprellt) -
    // nur die Platzierung, nie die Zahlen.
    var resizeTimer = null;
    window.addEventListener("resize", function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(render, 160);
    });

    render();
  }

  reiterAn();
  // Zahlen liegen inline im Dokument: <script type="application/json"
  // id="gr-zahlen"> VOR diesem Script. Kein fetch — unter file:// blockiert
  // die Same-Origin-Politik fetch(), und der lokale http-Server wird vom
  // System wiederholt gekillt.
  Z = JSON.parse(document.getElementById("gr-zahlen").textContent);
  start();
})();
