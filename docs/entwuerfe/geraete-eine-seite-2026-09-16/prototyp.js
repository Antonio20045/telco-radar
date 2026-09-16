/* =====================================================================
   prototyp.js — Entwurf v2 „EINE Geräteseite" (16.09.2026)
   Nur Reiter-Umschalten (derselbe Mechanismus wie app.js: data-tafel +
   .gr-tafel--aus), Suchfeld-Live-Vorschau (Verhalten 1:1 aus Entwurf v1,
   Antonios einziger Lob: ab 2 Zeichen, ≤ 8 Treffer, Modellname + GB,
   klickbar vor vollständiger Eingabe), Band-Wahl und Graph-Form-Umschalter.
   Kein Live-app.js. Alle Zahlen aus zahlen.json (Bestand 15.09.2026),
   inline im HTML eingebettet (id="gr-zahlen") — kein fetch, der Entwurf
   läuft per Doppelklick (file://); der Antwort-Satz ist reine Ableitung
   aus denselben Zeilen, die der Graph rendert — keine zweite Rechnung.

   Zentrum-Überarbeitung (16.09.2026, abends): Der Graph ist das größte
   Element der Tafel, nicht ihre Fußnote. Form A = Balkenhöhe 50 px,
   Segmentwerte GEDRUCKT im Segment (zu schmale Segmente tragen ihren
   Betrag über dem Balken, Haarlinie am Segment), TCO-24 in 27-px-Serife
   am Balkenende IM Bild, rote Vodafone-Referenzlinie als EINE vertikale
   Linie durch alle Balkenzeilen mit Label an der Linie. Form B = Spur
   44 px, Monatszahl 26 px am Balken. Form C = SVG in Balkenbreite und
   mindestens 340 px Höhe (die alte Fassung maß 300 px intrinsische
   SVG-Breite — daher die Miniatur). Positionierungen, die von der
   rendered Breite abhängen, misst messeGraph() NACH dem Einfügen
   (offsetWidth) — die Y-Achse gehört dem Preis, die X-Achse hier dem
   Betrag: nichts wird verschoben, nur beschriftet.
   ===================================================================== */
(function () {
  "use strict";

  var BAND_KURZ = { klein: "Klein", mittel: "Mittel", gross: "Groß" };
  var BAND_BEREICH = null;            // aus zahlen.json (baender_meta)
  var ANB_SLUG = {                    // Klassen der Live-CSS (gr-anb--*)
    "Vodafone": "vodafone", "Telekom": "telekom", "o2": "o2",
    "1&1": "1-1", "congstar": "congstar"
  };
  var ANB_FARBE = {                   // dieselben Werte wie --anb in style.css
    "Vodafone": "#e60000", "Telekom": "#e20074", "o2": "#0019a5",
    "1&1": "#00589e", "congstar": "#f5a800"
  };
  var FORMEN = {
    A: "A · Zusammensetzung des TCO-24 je Anbieter",
    B: "B · Ø €/Monat je Anbieter, TCO-24 daneben",
    C: "C · TCO-24 über die drei Bänder je Anbieter"
  };

  var Z = null;
  /* Startzustand = der VOLLSTE Graph des Bestands, damit der erste Blick
     einen Vergleich zeigt, keine Einzelzeile. Gemessen über alle
     (Modell × Band) in #gr-zahlen: Drei Kombinationen haben 4 Zeilen —
     Z Fold8 klein, iPhone 17 klein, iPhone 17 Pro klein (je inkl.
     Vodafone-Referenz). Genommen ist Z Fold8 klein, weil dort die
     Referenzlinie bei 83,9 % MITTENDRIN steht (iPhone 17: 98,2 %,
     iPhone 17 Pro: 99,3 %, also am rechten Rand) und die Balkenlängen
     von 73,8 bis 100 % streuen — ein lesbarer Vergleich. Pixel 11 Pro
     bleibt über Suchfeld + Band erreichbar (2 Handgriffe). */
  var zustand = { modell: "samsung-galaxy-z-fold8-256", band: "klein", form: "A" };

  function $(id) { return document.getElementById(id); }
  function euro(n) {
    return n.toLocaleString("de-DE", { minimumFractionDigits: 2 }) + " €";
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
  function datumKurz(iso) {        // „15.09.2026" (Form C, unter dem Endnamen)
    return iso.slice(8, 10) + "." + iso.slice(5, 7) + "." + iso.slice(0, 4);
  }
  /* Beleg je Graphzeile: nur das Datum, daneben EIN ↗-Link auf die
     Anbieter-/Tarifseite aus zahlen.json (url + messtermin je Zeile). */
  function belegZeile(z) {
    return "<span class='v2-beleg'><span class='v2-beleg-datum'>" +
      datumDe(z.messtermin) + "</span> <a class='v2-beleg-link' href='" +
      esc(z.url) + "' target='_blank' rel='noopener' title='Beleg bei " +
      esc(z.anbieter) + " öffnen' aria-label='Beleg bei " + esc(z.anbieter) +
      " öffnen (abgerufen " + datumDe(z.messtermin) + ")'>↗</a></span>";
  }
  function kurzName(mod) {
    // „Google Pixel 11 Pro 256 GB" → „Pixel 11 Pro" (Antonios Satz sagt Pixel 11 Pro)
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
      if (zweit && !vfNur(zeilen)) {
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
  function vfNur(zeilen) { return zeilen.length === 1; }

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
        // Nur Anbieter MIT Alternativ-Zahl kriegen die Klammer - so bleibt
        // die Leitfrage-Antwort ohne Bandwechsel komplett.
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

  /* ---------------- Bestandteile → Segmente (Form A) ------------------ */
  function segmente(z) {
    var einmalig = 0, raten = 0, tarif = 0, buendel = 0;
    z.bestandteile.forEach(function (p) {
      var n = p.name, v = p.betrag || 0;
      if (n === "Gerätezuzahlung" || n === "Anschlusspreis") einmalig += v;
      else if (n.indexOf("Geräteraten") === 0) raten += v;
      else if (n.indexOf("Bündelpreis") === 0) buendel += v;
      else if (n.indexOf("Tarif über") === 0) tarif += v;
    });
    var posten = [];
    if (einmalig) posten.push(["einmalig", einmalig, "einmalig"]);
    if (raten) posten.push(["Geräteraten bis 24", raten, "raten"]);
    if (tarif) posten.push(["Tarif bis 24", tarif, "tarif"]);
    if (buendel) posten.push(["Bündelbeiträge bis 24", buendel, "buendel"]);
    return { liste: posten, summe: einmalig + raten + tarif + buendel };
  }

  /* ---------------- Form A: gestapelter Balken je Anbieter ------------
     Das Zentrum der Tafel: Balkenhöhe 50 px, volle Spurbreite, Werte im
     Bild. Die Spalten der Zeilen sind FIX (200px · 1fr · 190px), deshalb
     liegt die Spur jeder Zeile pixelgleich — EINE Referenzlinie im
     Container trifft den Balken jeder Zeile am selben Betrag. Die Linie
     sitzt mit width:2px/margin-left:-1px MITTLIG auf ihrer Marke und
     bleibt so auch bei 100 % Spurausnutzung sichtbar innen. */
  function formA(mod, band) {
    var b = mod.baender[band];
    var zeilen = b.zeilen.slice().sort(function (x, y) { return x.tco24 - y.tco24; });
    var vf = b.zeilen.filter(function (z) { return z.referenz; })[0] || null;
    var maxT = Math.max.apply(null, zeilen.map(function (z) { return z.tco24; }));
    var hatBuendel = zeilen.some(function (z) {
      return segmente(z).liste.some(function (s) { return s[2] === "buendel"; });
    });
    var refF = vf ? vf.tco24 / maxT : null;

    var html = "<div class='v2-legende'>" +
      "<span><i class='v2-l-einmalig'></i>einmalig</span>" +
      "<span><i class='v2-l-raten'></i>Geräteraten bis 24</span>" +
      "<span><i class='v2-l-tarif'></i>Tarif bis 24</span>" +
      (hatBuendel ? "<span><i class='v2-l-buendel'></i>Bündelbeiträge bis 24</span>" : "") +
      (vf ? "<span><i class='v2-l-ref'></i>Vodafone-Referenz</span>" : "") +
      "</div><div class='v2-a-liste'" +
      (refF !== null ? " style='--v2-ref-f:" + refF.toFixed(4) + "'" : "") + ">" +
      (refF !== null
        ? "<div class='v2-a-refline' aria-hidden='true'></div>" +
          "<div class='v2-a-reflabel'>Vodafone " + vf.tco24_text + "</div>"
        : "");
    zeilen.forEach(function (z) {
      var seg = segmente(z);
      var pos = 0, segs = "";
      seg.liste.forEach(function (s) {
        var w = s[1] / maxT * 100;
        segs += "<div class='v2-a-seg v2-a-seg--" + s[2] +
          "' style='left:" + pos.toFixed(2) + "%;width:" + w.toFixed(2) + "%'>" +
          "<span class='v2-a-segwert'>" + euro(s[1]) + "</span></div>";
        pos += w;
      });
      var endPct = z.tco24 / maxT * 100;
      segs += "<span class='v2-a-tco v2-zahl' data-end='" + endPct.toFixed(2) +
        "' style='left:" + endPct.toFixed(2) + "%'>" + z.tco24_text + "</span>";
      var delta = z.referenz
        ? "<span class='v2-a-ref'>Referenz</span>"
        : (z.delta_text ? "<span class='v2-a-delta v2-zahl'>" + z.delta_text + "</span>" : "");
      html +=
        "<div class='v2-a-zeile" + (z.referenz ? " v2-a-zeile--eigen" : "") + "'>" +
        "<div class='v2-a-name'>" +
        "<span class='v2-a-anbieter'>" + z.anbieter + "</span>" +
        (z.referenz ? "<span class='v2-a-chip'>unser Angebot</span>" : "") +
        "<span class='v2-a-tarif'>" + z.tarif + (z.gb ? " · " + z.gb : "") +
        "</span></div>" +
        "<div class='v2-a-spur'>" + segs + "</div>" +
        "<div class='v2-a-wert'>" + delta + belegZeile(z) + "</div>" +
        "</div>";
    });
    return html + "</div>";
  }

  /* ---------------- Form B: Ø €/Monat (Live-Klassen .gr-bz) -----------
     Gleiche Größenordnung wie Form A: Spur 44 px hoch, die Monatszahl in
     26-px-Serife am Balkenende im Bild (weiß auf dem Live-Fill; der Fill
     ist 44 px hoch, die Zahl Large-Text-kontrastsicher). */
  function formB(mod, band) {
    var b = mod.baender[band];
    var zeilen = b.zeilen.slice().sort(function (x, y) { return x.tco24 - y.tco24; });
    var maxS = Math.max.apply(null, zeilen.map(function (z) { return z.schnitt; }));
    var html = "<div class='gr-balkenliste'>";
    zeilen.forEach(function (z) {
      var w = Math.max(4, z.schnitt / maxS * 100);
      html +=
        "<div class='gr-bz" + (z.referenz ? " gr-bz--eigen gr-anb--" + ANB_SLUG[z.anbieter] : "") +
        "' data-anbieter='" + z.anbieter + "' data-tco='" + z.tco24 + "'>" +
        "<div class='gr-bz-name'><span class='gr-bz-anbieter'>" + z.anbieter + "</span>" +
        (z.referenz ? "<span class='gr-bz-chip'>unser Angebot</span>" : "") +
        "<span class='gr-bz-tarif'>" + z.tarif + (z.gb ? " · " + z.gb : "") +
        "</span></div>" +
        "<div class='gr-bz-spur'><div class='gr-bz-fill' style='width:" + w + "%'></div>" +
        "<span class='v2-b-zahl v2-zahl' data-end='" + w.toFixed(2) +
        "' style='left:" + w.toFixed(2) + "%'>" +
        z.schnitt_text.replace(" €/M.", "") + " €/M.</span></div>" +
        "<div class='gr-bz-wert'><span class='gr-bz-tco v2-zahl'>TCO-24 " + z.tco24_text + "</span>" +
        (z.referenz ? "<span class='gr-bz-ref'>Referenz</span>"
          : (z.delta_text ? "<span class='gr-bz-delta v2-zahl'>" + z.delta_text + "</span>" : "")) +
        belegZeile(z) + "</div></div>";
    });
    return html + "</div>";
  }

  /* ---------------- Form C: Band-Kurve (SVG, Anbieterfarben live) -----
     Breite wird GEMESSEN (Platzhalter), Höhe = max(340, 40 % der Breite):
     die alte Fassung hatte nur die viewBox (360×330) als intrinsische
     Größe → 300 px breite Miniatur. Schriftgrößen stehen in viewBox-
     Einheiten, die 1:1 gerendert werden. */
  function formC(mod, bandAktiv, W) {
    var bands = ["klein", "mittel", "gross"];
    var anbieter = Object.keys(ANB_FARBE).filter(function (a) {
      return bands.some(function (bk) {
        var b = mod.baender[bk];
        return b && b.zeilen.some(function (z) { return z.anbieter === a; });
      });
    });
    var punkte = {};   // anbieter -> {band: tco24}
    var zeilenC = {};  // anbieter -> {band: zeile} (für Beleg am Linienende)
    var maxT = 0;
    anbieter.forEach(function (a) { punkte[a] = {}; zeilenC[a] = {};
      bands.forEach(function (bk) {
        var b = mod.baender[bk];
        var z = b && b.zeilen.filter(function (x) { return x.anbieter === a; })[0];
        if (z) { punkte[a][bk] = z.tco24; zeilenC[a][bk] = z;
          maxT = Math.max(maxT, z.tco24); }
      });
    });
    var H = Math.max(340, Math.round(W * 0.40));
    var L = 14, R = Math.max(96, Math.round(W * 0.15)), T = 30, B = 64;
    var pw = W - L - R, ph = H - T - B;
    var X = { klein: L + pw * 0.10, mittel: L + pw * 0.50, gross: L + pw * 0.90 };
    var ymax = maxT * 1.08;
    function Y(v) { return T + (1 - v / ymax) * ph; }
    function txt(v) { return v.toLocaleString("de-DE", { maximumFractionDigits: 0 }) + " €"; }

    var svg = "<div class='v2-kurve-wrap'><svg viewBox='0 0 " + W + " " + H +
      "' width='" + W + "' role='img' aria-label='TCO-24 je Tarifband und Anbieter'>";
    // Raster: 4 Haarlinien mit Beschriftung
    for (var g = 0; g <= 3; g++) {
      var v = ymax * g / 3, y = Y(v);
      svg += "<line class='v2-kurve-raster' x1='" + L + "' y1='" + y.toFixed(1) +
        "' x2='" + (W - R) + "' y2='" + y.toFixed(1) + "'></line>";
      if (g > 0)
        svg += "<text class='v2-kurve-achse' x='" + (W - R + 8) + "' y='" +
          (y + 4.5).toFixed(1) + "'>" + txt(v) + "</text>";
    }
    bands.forEach(function (bk) {
      var aktiv = bk === bandAktiv;
      svg += "<text class='v2-kurve-achse" + (aktiv ? " v2-kurve-band--aktiv" : "") +
        "' x='" + X[bk].toFixed(1) +
        "' y='" + (H - B + 26) + "' text-anchor='middle' style='font-weight:700'>" +
        BAND_KURZ[bk] + "</text>" +
        "<text class='v2-kurve-achse' x='" + X[bk].toFixed(1) + "' y='" +
        (H - B + 44) + "' text-anchor='middle'>" + BAND_BEREICH[bk] + "</text>";
      svg += "<line class='v2-kurve-raster" + (aktiv ? " v2-kurve-aktiv" : "") +
        "' x1='" + X[bk].toFixed(1) +
        "' y1='" + T + "' x2='" + X[bk].toFixed(1) + "' y2='" + (T + ph) + "'></line>";
    });
    // Linien + Punkte + Werte; Endnamen mit Mindestabstand -
    // die Lehre von der Positionskarte: das Etikett gehört auf die wahre Höhe.
    var enden = [];
    anbieter.forEach(function (a) {
      var farbe = ANB_FARBE[a];
      var dash = a === "Telekom" ? " stroke-dasharray='3 4'" : "";
      var lastBk = null;
      bands.forEach(function (bk) {
        if (punkte[a][bk] === undefined) return;
        if (lastBk !== null) {
          svg += "<line class='v2-kurve-linie' x1='" + X[lastBk].toFixed(1) + "' y1='" +
            Y(punkte[a][lastBk]).toFixed(1) + "' x2='" + X[bk].toFixed(1) + "' y2='" +
            Y(punkte[a][bk]).toFixed(1) + "' stroke='" + farbe + "'" + dash + "></line>";
        }
        lastBk = bk;
      });
      var letzter = bands.filter(function (bk) { return punkte[a][bk] !== undefined; }).pop();
      enden.push({ a: a, bk: letzter, y: Y(punkte[a][letzter]),
        z: zeilenC[a][letzter] });
    });
    // Werte an den Punkten (immer gedruckt), kollisionsfrei je Spalte:
    // Kandidaten über/unter dem Punkt, gierig die freie Seite gewählt -
    // bei drei nahe beieinander liegenden Preisen einer Spalte reicht
    // ein fester Wechsel nicht (Befund am Pixel-11-Pro-Fall, Band Klein).
    var spalten = {};
    anbieter.forEach(function (a) {
      bands.forEach(function (bk) {
        var v = punkte[a][bk];
        if (v === undefined) return;
        (spalten[bk] = spalten[bk] || []).push({ a: a, v: v, y: Y(v) });
      });
    });
    var werte = [];
    bands.forEach(function (bk) {
      var liste = (spalten[bk] || []).sort(function (p, q) { return p.y - q.y; });
      var belegt = [];
      function frei(yy) {
        return !belegt.some(function (r) {
          return Math.abs(r - yy) < 14;
        });
      }
      liste.forEach(function (p, i) {
        var drueber = p.y - 12, drunter = p.y + 19;
        var yy = i % 2 === 0 ? drueber : drunter;
        if (!frei(yy)) yy = frei(drueber) ? drueber : drunter;
        var schieber = 0;
        while (!frei(yy) && schieber < 4) {
          yy += (yy > p.y ? 14 : -14);
          schieber++;
        }
        belegt.push(yy);
        werte.push({ a: p.a, bk: bk, v: p.v, yy: yy });
      });
    });
    werte.forEach(function (w) {
      var x = X[w.bk];
      svg += "<text class='v2-kurve-wert' x='" + x.toFixed(1) + "' y='" +
        w.yy.toFixed(1) + "' text-anchor='middle'>" +
        w.v.toLocaleString("de-DE", { maximumFractionDigits: 0 }) + "</text>";
    });
    anbieter.forEach(function (a) {
      var farbe = ANB_FARBE[a];
      bands.forEach(function (bk) {
        var v = punkte[a][bk];
        if (v === undefined) return;
        var x = X[bk], y = Y(v);
        svg += "<circle class='v2-kurve-punkt' cx='" + x.toFixed(1) + "' cy='" +
          y.toFixed(1) + "' r='5' fill='" + farbe + "'></circle>";
      });
    });
    // Endnamen als Beleg-Link (der Beleg gehört zum ANBIETER, nicht je
    // Punkt), Abrufdatum darunter - Mindestabstand 28 px für das Zweizeiler-
    // Block, Etikett bleibt auf wahrer Höhe des Linienendes.
    enden.sort(function (p, q) { return p.y - q.y; });
    var letzteY = -99;
    enden.forEach(function (e) {
      var y = Math.max(e.y, letzteY + 28);
      letzteY = y;
      svg += "<a href='" + esc(e.z.url) + "' target='_blank' rel='noopener'" +
        " class='v2-kurve-link' role='link'" +
        " aria-label='Beleg bei " + esc(e.a) + " öffnen'>" +
        "<text class='v2-kurve-name' x='" + (X[e.bk] + 12).toFixed(1) +
        "' y='" + (y + 5).toFixed(1) + "' fill='" + ANB_FARBE[e.a] + "'>" + e.a +
        "<tspan class='v2-kurve-pfeil'> ↗</tspan></text></a>" +
        "<text class='v2-kurve-datum' x='" + (X[e.bk] + 12).toFixed(1) +
        "' y='" + (y + 19).toFixed(1) + "'>" + datumKurz(e.z.messtermin) + "</text>";
    });
    svg += "</svg></div>";
    svg += "<p class='v2-kurve-hinweis'>TCO-24 je Tarifband · ein fehlender Punkt heißt: dieser Anbieter führt das Gerät in dem Band nicht im Bündel (Namen in der Zeile unter dem Graph je gewähltem Band).</p>";
    return svg;
  }

  /* ---------------- Nachmessen: Beschriftung am gerenderten Bild -------
     Alles, was von der Spurbreite abhängt, wird hier NACH dem Einfügen
     entschieden (offsetWidth zwingt das Layout). Nie verschoben wird ein
     Wert von seinem Betrag - die X-Achse gehört dem Betrag wie die Y-Achse
     dem Preis; verschoben wird nur die BESCHRIFTUNG, mit Haarlinie am Ort
     der Wahrheit. */
  function messeGraph() {
    var mobil = window.matchMedia("(max-width:640px)").matches;
    var schwelleSeg = mobil ? 58 : 90;

    /* Form A */
    document.querySelectorAll("#v2-graph .v2-a-zeile").forEach(function (zeile) {
      var spur = zeile.querySelector(".v2-a-spur");
      if (!spur) return;
      var spurW = spur.clientWidth;
      var tco = spur.querySelector(".v2-a-tco");
      var segs = spur.querySelectorAll(".v2-a-seg");
      var letztes = segs.length ? segs[segs.length - 1] : null;
      var tcoW = tco ? tco.offsetWidth : 0;
      var tcoAussen = false;
      // 1) TCO: passt nicht ins letzte Segment → daneben (außen, Ink).
      //    Innen bleibt weiß - das letzte Segment ist immer Tarif oder
      //    Bündel (dunkel); ein helleres letztes Segment gibt es im
      //    Bestand nicht (TCO ohne Tarif-/Bündelanteil ist kein Bündel).
      if (tco && letztes) {
        var endF = parseFloat(tco.dataset.end) / 100;
        if (letztes.offsetWidth < tcoW + 12 &&
            (spurW - spurW * endF) >= tcoW + 10) {
          tco.classList.add("v2-a-tco--aussen");
          tcoAussen = true;
        }
      }
      // 2) Segmentwerte: MINI-Segmente (< 10 px gerendert, z.B. die
      //    1,00-€-Zuzahlung an einem 2.131,66-€-Balken) docken ihr Label
      //    bündig am Segmentanfang an — beim Erstsegment also am
      //    SPURSTART, nie weiter links schwebend — mit kräftiger
      //    Haarlinie zum Segment: der Betrag muss erkennbar zum Balken
      //    gehören. Schmale Segmente (bis zur Schwelle) oder breitere
      //    Beschriftung oder Kollision mit dem TCO im letzten Segment →
      //    Betrag ÜBER dem Balken, Haarlinie am Segmentanfang.
      segs.forEach(function (seg) {
        var wert = seg.querySelector(".v2-a-segwert");
        if (!wert) return;
        var w = seg.offsetWidth;
        if (w < 10) {
          seg.classList.add("v2-a-seg--mini");
        } else {
          var kollidiert = seg === letztes && tco && !tcoAussen &&
            (w - (tcoW + 14) < wert.offsetWidth + 10);
          if (w < schwelleSeg || wert.offsetWidth > w - 8 || kollidiert) {
            seg.classList.add("v2-a-seg--drueber");
            // Beschriftung klemmen: darf die Spur nicht seitlich verlassen
            if (seg.offsetLeft + wert.offsetWidth > spurW - 2)
              seg.classList.add("v2-a-seg--drueber--rechts");
          }
        }
      });
      // 3) Andock-Kontrolle: Ein Label (mini oder drueber) darf weder in
      //    die Namensspalte links ragen noch die Wertspalte rechts
      //    schneiden - die Grid-Spalten trennen sie um 14 px von der
      //    Spur; gemessen statt geglaubt, und im Fall der Fälle dockt
      //    das Label hart am Spurstart an.
      var nameBox = zeile.querySelector(".v2-a-name").getBoundingClientRect();
      var wertBox = zeile.querySelector(".v2-a-wert").getBoundingClientRect();
      spur.querySelectorAll(".v2-a-seg--mini,.v2-a-seg--drueber").forEach(function (seg) {
        var wb = seg.querySelector(".v2-a-segwert").getBoundingClientRect();
        var trifftNamen = wb.left < nameBox.right + 2 &&
          wb.bottom > nameBox.top && wb.top < nameBox.bottom;
        var trifftWert = wb.right > wertBox.left - 2 &&
          wb.bottom > wertBox.top && wb.top < wertBox.bottom;
        if (trifftNamen || trifftWert) {
          seg.querySelector(".v2-a-segwert").style.left = "0px";
          seg.classList.remove("v2-a-seg--drueber--rechts");
        }
      });
    });

    /* Form B */
    document.querySelectorAll("#v2-graph .gr-bz-spur").forEach(function (spur) {
      var zahl = spur.querySelector(".v2-b-zahl");
      var fill = spur.querySelector(".gr-bz-fill");
      if (!zahl || !fill) return;
      var spurW = spur.clientWidth;
      var zahlW = zahl.offsetWidth;
      var endF = parseFloat(zahl.dataset.end) / 100;
      if (fill.offsetWidth < zahlW + 12 &&
          (spurW - spurW * endF) >= zahlW + 10) {
        zahl.classList.add("v2-b-zahl--aussen");
      }
    });
  }

  /* ---------------- Render -------------------------------------------- */
  function render() {
    var mod = Z.modelle[zustand.modell];
    $("v2-antwort").innerHTML = antwortSatz(mod, zustand.band);
    lueckenSatz(mod, zustand.band);
    if (zustand.form === "A") $("v2-graph").innerHTML = formA(mod, zustand.band);
    else if (zustand.form === "B") $("v2-graph").innerHTML = formB(mod, zustand.band);
    else {
      // Form C braucht die gerenderte Breite (Platzhalter messen, dann
      // bauen) - die viewBox steht in px und wird 1:1 ausgeliefert.
      $("v2-graph").innerHTML = "<div class='v2-kurve-wrap'></div>";
      var platz = $("v2-graph").firstElementChild;
      var w = platz.clientWidth || 960;
      platz.innerHTML = formC(mod, zustand.band, w);
    }
    messeGraph();
    $("v2-form-name").textContent = FORMEN[zustand.form];
    document.querySelectorAll("#v2-formwahl .v2-formknopf").forEach(function (b) {
      b.setAttribute("aria-pressed", b.dataset.form === zustand.form ? "true" : "false");
    });
    history.replaceState(null, "", "?modell=" + encodeURIComponent(zustand.modell) +
      "&band=" + zustand.band + "&form=" + zustand.form);
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
    var m = params.get("modell"), b = params.get("band"), f = params.get("form");
    if (m && Z.modelle[m]) zustand.modell = m;
    if (["klein", "mittel", "gross"].indexOf(b) > -1) zustand.band = b;
    if (["A", "B", "C"].indexOf(f) > -1) zustand.form = f;
    var hash = (location.hash || "").replace(/^#form-/, "");
    if (["A", "B", "C"].indexOf(hash) > -1) zustand.form = hash;

    $("v2-suchfeld").value = Z.modelle[zustand.modell].titel;
    setBandKnopf();

    $("v2-baender").addEventListener("click", function (ev) {
      var k = ev.target.closest("button[data-band]");
      if (!k) return;
      zustand.band = k.dataset.band;
      setBandKnopf();
      render();
    });
    $("v2-formwahl").addEventListener("click", function (ev) {
      var k = ev.target.closest("button[data-form]");
      if (!k) return;
      zustand.form = k.dataset.form;
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

    // Die Beschriftung hängt an der gerenderten Breite: bei Resize neu
    // rechnen (entprellt) - nur die Platzierung, nie die Zahlen.
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
  // System wiederholt gekillt. Gleiches Objekt, gleiche Weiterverarbeitung
  // wie vorher im fetch-Pfad (Z = j; start();).
  Z = JSON.parse(document.getElementById("gr-zahlen").textContent);
  start();
})();
