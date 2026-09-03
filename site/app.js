/* Telco Radar - Explorer (Vanilla JS, kein Framework) */
(function () {
  'use strict';

  const dataEl = document.getElementById('explorer-data');
  if (!dataEl) return;
  let items = [];
  try { items = JSON.parse(dataEl.textContent); } catch (e) { return; }

  const listEl = document.getElementById('ex-list');
  const detailEl = document.getElementById('ex-detail');
  // Wie tief die aktuelle Seite unter site/ liegt. Die Archivwochen stehen
  // in reports/, alles andere direkt darunter.
  function uebPrefix() {
    return location.pathname.indexOf('/reports/') !== -1 ? '../' : '';
  }
  const countEl = document.getElementById('ex-count');
  const fSearch = document.getElementById('f-search');
  const fRegion = document.getElementById('f-region');
  const fCategory = document.getElementById('f-category');
  const fRelevance = document.getElementById('f-relevance');
  const fSort = document.getElementById('f-sort');
  if (!listEl) return;

  const REL_LABEL = { 5: 'Sofort ansehen', 4: 'Wichtig', 3: 'Beobachten', 2: 'Randnotiz', 1: 'Randnotiz', 0: 'Unbewertet' };
  let visible = [];
  let selectedId = null;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function relClass(r) { return 'r' + (r >= 2 ? r : 0); }

  function matches(h) {
    const q = (fSearch.value || '').trim().toLowerCase();
    if (q) {
      const hay = ((h.operator || '') + ' ' + (h.title || '') + ' ' + (h.summary || '') + ' ' + (h.source_label || '')).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    if (fRegion.value && h.region !== fRegion.value) return false;
    if (fCategory.value && h.category !== fCategory.value) return false;
    const minRel = parseInt(fRelevance.value || '0', 10);
    if (minRel && (h.relevance || 0) < minRel) return false;
    return true;
  }

  function sortItems(arr) {
    const mode = fSort.value;
    const copy = arr.slice();
    if (mode === 'date') {
      copy.sort(function (a, b) { return (b.date || '').localeCompare(a.date || '') || b.relevance - a.relevance; });
    } else if (mode === 'operator') {
      copy.sort(function (a, b) { return (a.operator || 'zz').localeCompare(b.operator || 'zz') || b.relevance - a.relevance; });
    } else {
      copy.sort(function (a, b) { return b.relevance - a.relevance || (b.date || '').localeCompare(a.date || ''); });
    }
    return copy;
  }

  function renderList() {
    visible = sortItems(items.filter(matches));
    listEl.innerHTML = visible.map(function (h) {
      return '<div class="ex-row' + (h.id === selectedId ? ' active' : '') + '" data-id="' + h.id + '" role="option" tabindex="0">' +
        '<div class="ex-row-top">' +
          '<span class="ex-dot ' + relClass(h.relevance) + '"></span>' +
          '<span class="ex-op">' + esc(h.operator || h.source_label || '–') + '</span>' +
          '<span class="ex-reg">' + esc(h.region) + (h.date ? ' · ' + esc(h.date) : '') + '</span>' +
        '</div>' +
        '<div class="ex-title">' + esc(h.title) + '</div>' +
      '</div>';
    }).join('');
    countEl.textContent = visible.length + ' von ' + items.length + ' Meldungen' +
      (visible.length < items.length ? ' (gefiltert)' : '');
    if (visible.length && (selectedId === null || !visible.some(function (h) { return h.id === selectedId; }))) {
      select(visible[0].id, false);
    } else if (!visible.length) {
      detailEl.innerHTML = '<p class="ex-detail-empty">Keine Meldung passt zu diesen Filtern.</p>';
    }
  }

  function select(id, scroll) {
    selectedId = id;
    const h = items.find(function (x) { return x.id === id; });
    if (!h) return;
    listEl.querySelectorAll('.ex-row').forEach(function (row) {
      row.classList.toggle('active', parseInt(row.dataset.id, 10) === id);
    });
    const relTxt = h.relevance >= 2 ? h.relevance + '/5 · ' + (REL_LABEL[h.relevance] || '') : 'Unbewertet';
    detailEl.innerHTML =
      '<div class="ex-d-top">' +
        '<span class="rel-badge ' + relClass(h.relevance) + '">' + esc(relTxt) + '</span>' +
        '<span class="chip">' + esc(h.category) + '</span>' +
        '<span class="chip">' + esc(h.region) + '</span>' +
      '</div>' +
      '<h3><a href="' + esc(h.url) + '" target="_blank" rel="noopener">' + esc(h.title) + '</a></h3>' +
      '<p class="ex-d-meta"><b>' + esc(h.operator || '–') + '</b>' +
        (h.date ? ' · ' + esc(h.date) : '') +
        (h.source_label ? ' · Quelle: ' + esc(h.source_label) : '') + '</p>' +
      (h.summary ? '<p class="ex-d-sum">' + esc(h.summary) + '</p>' : '') +
      '<a class="source-link" href="' + esc(h.url) + '" target="_blank" rel="noopener">Originalquelle öffnen (' + esc(h.source_label || 'Link') + ') &nearr;</a>' +
      // Der rote Link zur vollstaendigen Uebersetzung, wenn es eine gibt.
      // Er steht NACH der Originalquelle, nicht an ihrer Stelle: das
      // Original bleibt der Beleg, die Uebersetzung ist das Angebot.
      // `prefix` traegt die Seite als data-Attribut - der Explorer steht
      // auf meldungen.html (prefix "") und unter reports/<datum>.html
      // (prefix "../"), und ein fester Pfad waere an einem der beiden Orte
      // falsch.
      // Die Beschriftung steht WOERTLICH so auch in _uebersetzung.html.j2.
      // Zwei Umsetzungen derselben Sache laufen auseinander - deshalb haelt
      // test_die_beschriftung_ist_an_beiden_orten_dieselbe sie zusammen.
      (h.uebersetzung
        ? '<p class="ueb-link"><a href="' + esc(uebPrefix()) + esc(h.uebersetzung) + '">Übersetzung lesen</a></p>'
        : '');
    if (scroll && window.innerWidth <= 880) detailEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  listEl.addEventListener('click', function (e) {
    const row = e.target.closest('.ex-row');
    if (row) select(parseInt(row.dataset.id, 10), true);
  });
  listEl.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' || e.key === ' ') {
      const row = e.target.closest('.ex-row');
      if (row) { e.preventDefault(); select(parseInt(row.dataset.id, 10), true); }
    }
  });

  let t;
  fSearch.addEventListener('input', function () { clearTimeout(t); t = setTimeout(renderList, 120); });
  [fRegion, fCategory, fRelevance, fSort].forEach(function (el) { el.addEventListener('change', renderList); });

  renderList();

  // Ankunft ueber die Dossier-Seite mit ?q=…: Suchfeld vorbelegen,
  // Explorer-Akkordeon oeffnen und sofort filtern - kein zweites Mal tippen.
  //
  // Der Explorer steht nur auf den Archivwochen unter reports/, und genau
  // dorthin verlinkt ein Dossier-Treffer ("in dieser Ausgabe ansehen"). Bis
  // zum 08.08.2026 stand hier eine Ausnahme fuer meldungen.html, weil dort
  // ein zweites Suchfeld dasselbe ?q= las; das Feld ist weg, die Suche hat
  // ihre eigene Seite.
  try {
    var qs = new URLSearchParams(location.search);
    var q = qs.get('q');
    if (q) {
      fSearch.value = q;
      renderList();
      var det = listEl.closest('details.evidence');
      if (det) { det.open = true; det.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
    }
  } catch (e) { /* URLSearchParams nicht verfuegbar - stiller Fallback */ }
})();

/* Promo Übersicht - Wettbewerber-Board: Tier-Filter (Vanilla JS, kein Framework) */
(function () {
  'use strict';
  const board = document.getElementById('promo-board');
  if (!board) return;
  const buttons = document.querySelectorAll('.promo-filter');
  if (!buttons.length) return;

  buttons.forEach(function (btn) {
    btn.addEventListener('click', function () {
      buttons.forEach(function (b) { b.classList.remove('on'); });
      btn.classList.add('on');
      const tier = btn.dataset.tier;
      board.querySelectorAll('.promo-card').forEach(function (card) {
        card.hidden = tier !== 'all' && card.dataset.tier !== tier;
      });
    });
  });
})();

/* Die Suchmaschine der Seite. Sie durchsucht `search_index.json` - die
   bewerteten Meldungen ALLER Ausgaben, die Differenzierungs-Bibliothek und die
   Promo-Aktionen (report/suchindex.py). Kein Suchserver: der Index ist ein
   JSON-Array, das der Browser einmal laedt und dann filtert.

   Am 08.08.2026 hat diese Schicht zwei Dinge dazubekommen, und beide gehen auf
   denselben Satz zurueck ("wenn ich suche, alle Meldungen super dargestellt,
   dass ich einen Ueberblick habe"):

   1. WORTWEISES SUCHEN STATT EINER ZEICHENKETTE. Vorher musste die Eingabe
      als Ganzes im Text vorkommen; "telekom perplexity" fand nichts, obwohl
      genau diese Kombination der Anlass der Suche war. Jetzt muss JEDES Wort
      vorkommen (UND-Verknuepfung), irgendwo im Eintrag.
   2. EINE RANGFOLGE. Vorher war jeder Treffer gleich viel wert und die Liste
      stand in Indexreihenfolge. Ein Treffer im Absender wiegt jetzt schwerer
      als einer im Fliesstext, und die Dringlichkeit der Meldung geht mit ein -
      sonst fuehrt eine Randnotiz das Dossier an. */
var TelcoSearch = (function () {
  'use strict';

  var KIND_LABEL = { bericht: 'Meldung', differenzierung: 'Differenzierung',
                     promo: 'Aktion' };
  var items = null;   // null = noch nicht geladen; [] = geladen, leer
  var loading = null;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  // Der Praefix (z. B. "" auf der Startseite, "../" unter reports/ oder
  // promo/) steckt schon serverseitig im Brand-Link - so muss app.js (eine
  // einzige, seitenunabhaengige Datei) ihn nicht selbst erraten.
  function prefix() {
    var brand = document.querySelector('.topbar .brand');
    var href = brand ? brand.getAttribute('href') || '' : '';
    return href.slice(0, href.length - 'index.html'.length) || '';
  }

  function loadIndex() {
    if (items !== null) return Promise.resolve(items);
    if (loading) return loading;
    loading = fetch(prefix() + 'search_index.json')
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (data) { items = Array.isArray(data) ? data : []; return items; })
      .catch(function () { items = []; return items; });
    return loading;
  }

  function worte(q) {
    return String(q || '').toLowerCase().split(/\s+/).filter(function (w) {
      return w.length > 0;
    });
  }

  function felder(it) {
    return {
      op: String(it.operator || '').toLowerCase(),
      titel: String(it.title || '').toLowerCase(),
      rest: [it.summary, it.region, it.category, it.source_label]
        .filter(Boolean).join(' — ').toLowerCase()
    };
  }

  /* 0 = kein Treffer. Sonst: je Wort das schwerste Feld, in dem es steht,
     plus die Dringlichkeit der Meldung als Stichentscheid. */
  function score(it, ws) {
    if (!ws.length) return 0;
    var f = felder(it);
    var summe = 0;
    for (var i = 0; i < ws.length; i++) {
      var w = ws[i];
      if (f.op.indexOf(w) !== -1) summe += 8;
      else if (f.titel.indexOf(w) !== -1) summe += 5;
      else if (f.rest.indexOf(w) !== -1) summe += 2;
      else return 0;             // UND-Verknuepfung: ein fehlendes Wort kippt
    }
    return summe + (it.relevance || 0);
  }

  function suche(alle, q) {
    var ws = worte(q);
    if (!ws.length) return [];
    var out = [];
    for (var i = 0; i < alle.length; i++) {
      var s = score(alle[i], ws);
      if (s) out.push({ it: alle[i], score: s });
    }
    return out;
  }

  /* Der Suchbegriff im Text hervorgehoben. Der Text selbst wird NICHT
     gekuerzt - eine Schlagzeile mit "…" am Ende ist ein abgeschnittener Satz,
     und die verbietet diese Codebasis ueberall sonst (CLAUDE.md §5,
     Abnahmekriterium 5). Gekuerzt wird nur der Fliesstext, und dort auch nur
     am Ende. */
  function markiere(text, ws) {
    var roh = String(text || '');
    if (!ws.length) return esc(roh);
    var lower = roh.toLowerCase();
    var stellen = [];
    for (var i = 0; i < ws.length; i++) {
      var von = lower.indexOf(ws[i]);
      while (von !== -1) {
        stellen.push([von, von + ws[i].length]);
        von = lower.indexOf(ws[i], von + ws[i].length);
      }
    }
    if (!stellen.length) return esc(roh);
    stellen.sort(function (a, b) { return a[0] - b[0]; });
    var out = '';
    var pos = 0;
    for (var j = 0; j < stellen.length; j++) {
      if (stellen[j][0] < pos) continue;
      out += esc(roh.slice(pos, stellen[j][0])) +
        '<mark>' + esc(roh.slice(stellen[j][0], stellen[j][1])) + '</mark>';
      pos = stellen[j][1];
    }
    return out + esc(roh.slice(pos));
  }

  // Deep-Link zum vollen Kontext: Meldungen haengen ?q= an, damit der
  // Explorer der jeweiligen Ausgabe sofort gefiltert oeffnet (siehe die
  // Explorer-IIFE weiter oben in dieser Datei); Differenzierung und Aktionen
  // springen direkt zu ihrem Abschnitt - dort gibt es keinen Begriffsfilter.
  function deepLinkHref(it, q) {
    var p = prefix();
    if (it.kind === 'bericht' && q) {
      return p + it.deep_link + '?q=' + encodeURIComponent(q);
    }
    return p + it.deep_link;
  }

  return {
    KIND_LABEL: KIND_LABEL, esc: esc, prefix: prefix, loadIndex: loadIndex,
    worte: worte, score: score, suche: suche, markiere: markiere,
    deepLinkHref: deepLinkHref
  };
})();

/* Die Dossier-Seite (suche.html).

   Sie beantwortet nicht "welche Zeilen enthalten mein Wort", sondern "was
   weiss dieses Portal ueber mein Thema, und wie hat es sich entwickelt".
   Daraus folgt der Aufbau, und zwar in dieser Reihenfolge:

     BILANZ     wie viele Treffer, ueber welchen Zeitraum, aus wie vielen
                Quellen - drei Zahlen, die den Rest einordnen.
     UEBERBLICK Verlauf ueber die Monate, haeufigste Absender, haeufigste
                Ressorts. Das ist die "Entwicklung", nach der Antonio gefragt
                hat, und sie steht VOR der ersten Meldung.
     AUFMACHER  der staerkste Treffer, gross und mit Bild.
     CHRONIK    alle uebrigen nach Monaten, neueste zuerst, mit Bildern -
                die Historie in der Reihenfolge, in der sie passiert ist.

   Alles ausser dem Suchfeld wird hier gebaut; die Vorlage liefert nur die
   Behaelter (templates/suche.html.j2). */
(function () {
  'use strict';
  var input = document.getElementById('dossier-input');
  var trefferEl = document.getElementById('dossier-treffer');
  if (!input || !trefferEl) return;

  var startEl = document.getElementById('dossier-start');
  var titelEl = document.getElementById('dossier-titel');
  var bilanzEl = document.getElementById('dossier-bilanz');
  var analyseEl = document.getElementById('dossier-analyse');
  var filterEl = document.getElementById('dossier-filter');
  var verlaufEl = document.getElementById('dossier-verlauf');
  var werEl = document.getElementById('dossier-wer');
  var worumEl = document.getElementById('dossier-worum');
  var form = document.getElementById('dossier-form');

  var MONATE = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli',
                'August', 'September', 'Oktober', 'November', 'Dezember'];
  // Wie viele Treffer als Bildkarte stehen, bevor der Rest zur Zeile wird.
  // Sechs fuellen zwei Reihen zu dritt; darueber hinaus waere die Chronik
  // wieder eine Kachelwand, und lesbar ist eine Zeile ohnehin schneller.
  var KARTEN_JE_MONAT = 6;
  var bereich = 'all';
  var t;

  var esc = TelcoSearch.esc;

  function datumDe(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '');
    if (!m) return '';
    return parseInt(m[3], 10) + '. ' + MONATE[parseInt(m[2], 10) - 1] + ' ' + m[1];
  }

  function monatDe(schluessel) {
    var m = /^(\d{4})-(\d{2})/.exec(schluessel || '');
    return m ? MONATE[parseInt(m[2], 10) - 1] + ' ' + m[1] : 'Ohne Datum';
  }

  function zaehle(liste, feld) {
    var z = {};
    liste.forEach(function (it) {
      var wert = (it[feld] || '').trim();
      if (wert) z[wert] = (z[wert] || 0) + 1;
    });
    return z;
  }

  /* Gezaehlte Werte als Balken. Dieselbe Bauform wie das Marktbild der
     Differenzierungs-Seite - eine Zahlenreihe, ein Aussehen. */
  function balken(el, zaehler, grenze, reihenfolge) {
    var paare = Object.keys(zaehler).map(function (k) {
      return { name: k, n: zaehler[k] };
    });
    if (reihenfolge === 'name') paare.sort(function (a, b) { return a.name < b.name ? -1 : 1; });
    else paare.sort(function (a, b) { return b.n - a.n || (a.name < b.name ? -1 : 1); });
    if (grenze) paare = paare.slice(0, grenze);
    var hoechste = paare.reduce(function (m, p) { return Math.max(m, p.n); }, 0);
    el.innerHTML = paare.map(function (p) {
      var w = hoechste ? Math.round(100 * p.n / hoechste) : 0;
      return '<li><span class="dz-balken-name">' + esc(p.name) + '</span>' +
        '<span class="dz-balken-spur"><span class="dz-balken-fuell" style="width:' + w + '%"></span></span>' +
        '<span class="dz-balken-n">' + p.n + '</span></li>';
    }).join('');
  }

  function motiv(it) {
    if (it.image) {
      return '<span class="dsk-motiv"><img src="' + esc(TelcoSearch.prefix() + it.image) +
        '" alt=""' + (it.image_w ? ' width="' + it.image_w + '" height="' + it.image_h + '"' : '') +
        ' loading="lazy"></span>';
    }
    // Kein belegtes Bild: die Schriftkachel mit dem Absender. Dieselbe Regel
    // wie auf der Promo-Uebersicht und der Differenzierung - jede Karte
    // traegt ein Motiv, nie einen leeren Kasten.
    return '<span class="dsk-motiv"><span class="dsk-kachel">' +
      esc(it.operator || it.source_label || 'Meldung') + '</span></span>';
  }

  function meta(it, ohneAbsender) {
    var teile = [ohneAbsender ? '' : it.operator, it.region, datumDe(it.date)]
      .filter(Boolean);
    return teile.join(' · ');
  }

  function kontextLabel(it) {
    if (it.kind === 'bericht') return 'In der Ausgabe ansehen';
    if (it.kind === 'promo') return 'Auf der Promo Übersicht ansehen';
    return 'Im Differenzierungs-Hebel ansehen';
  }

  function karte(it, ws, q, stufe) {
    var zeile = stufe === 'zeile';
    var klasse = 'dsk' + (stufe ? ' dsk--' + stufe : '') +
      (it.image ? '' : ' ohne-bild');
    // Traegt die Schriftkachel schon den Absender, faellt er aus der
    // Metazeile - sonst steht derselbe Name zweimal untereinander.
    var ohneAbsender = !it.image && !zeile;
    return '<article class="' + klasse + '">' +
      (zeile ? '' : motiv(it)) +
      '<div class="dsk-text">' +
        '<p class="dsk-kopf">' +
          '<span class="dsk-art ' + esc(it.kind) + '">' +
            esc(TelcoSearch.KIND_LABEL[it.kind] || it.kind) + '</span>' +
          '<span class="dsk-meta">' + esc(meta(it, ohneAbsender)) + '</span>' +
          (it.status ? '<span class="dsk-status">' + esc(it.status) + '</span>' : '') +
        '</p>' +
        '<a class="dsk-titel szl" href="' + esc(it.url) + '" target="_blank" rel="noopener">' +
          TelcoSearch.markiere(it.title, ws) + '</a>' +
        (!zeile && it.summary && it.summary !== it.title
          ? '<p class="dsk-anriss">' + TelcoSearch.markiere(it.summary, ws) + '</p>' : '') +
        '<p class="dsk-fuss">' +
          '<a class="dsk-quelle" href="' + esc(it.url) + '" target="_blank" rel="noopener">' +
            esc(it.source_label || 'Quelle') + ' &nearr;</a>' +
          '<a class="dsk-kontext" href="' + esc(TelcoSearch.deepLinkHref(it, q)) + '">' +
            kontextLabel(it) + ' &rsaquo;</a>' +
        '</p>' +
      '</div>' +
    '</article>';
  }

  function chronik(treffer, ws, q) {
    // Nach Monat, neueste zuerst. Die Chronik IST die Historie - deshalb
    // sortiert sie nach Datum und nicht nach Punktzahl; die Punktzahl
    // entscheidet nur, wer den Aufmacher stellt.
    var monate = [];
    var nachMonat = {};
    treffer.forEach(function (it) {
      var key = (it.date || '').slice(0, 7) || '0000-00';
      if (!nachMonat[key]) { nachMonat[key] = []; monate.push(key); }
      nachMonat[key].push(it);
    });
    monate.sort().reverse();
    return monate.map(function (key) {
      var liste = nachMonat[key];
      var karten = liste.slice(0, KARTEN_JE_MONAT);
      var zeilen = liste.slice(KARTEN_JE_MONAT);
      return '<section class="dossier-monat">' +
        '<div class="rubrik"><h2>' + esc(monatDe(key)) + '</h2>' +
        '<span class="rubrik-zahl">' + liste.length + ' Treffer</span></div>' +
        '<div class="dossier-raster">' +
          karten.map(function (it) { return karte(it, ws, q); }).join('') +
        '</div>' +
        (zeilen.length
          ? '<div class="dossier-zeilen">' +
              zeilen.map(function (it) { return karte(it, ws, q, 'zeile'); }).join('') +
            '</div>'
          : '') +
      '</section>';
    }).join('');
  }

  function bilanz(treffer, q) {
    var mitDatum = treffer.map(function (it) { return it.date; })
      .filter(Boolean).sort();
    var quellen = {};
    treffer.forEach(function (it) { if (it.source_label) quellen[it.source_label] = 1; });
    var teile = [treffer.length + (treffer.length === 1 ? ' Treffer' : ' Treffer')];
    if (mitDatum.length > 1 && mitDatum[0] !== mitDatum[mitDatum.length - 1]) {
      teile.push('von ' + datumDe(mitDatum[0]) + ' bis ' +
                 datumDe(mitDatum[mitDatum.length - 1]));
    } else if (mitDatum.length) {
      teile.push('vom ' + datumDe(mitDatum[0]));
    }
    var n = Object.keys(quellen).length;
    if (n) teile.push(n + (n === 1 ? ' Quelle' : ' Quellen'));
    return teile.join(' · ');
  }

  function filterZeile(alle, ws) {
    // Die Zahl je Bereich steht am Filter, nicht daneben - sie ist der
    // Grund, ihn zu druecken.
    var arten = ['all', 'bericht', 'differenzierung', 'promo'];
    var zaehler = {};
    alle.forEach(function (h) { zaehler[h.it.kind] = (zaehler[h.it.kind] || 0) + 1; });
    filterEl.innerHTML = arten.filter(function (a) {
      return a === 'all' || zaehler[a];
    }).map(function (a) {
      var n = a === 'all' ? alle.length : zaehler[a];
      var label = a === 'all' ? 'Alles' : (TelcoSearch.KIND_LABEL[a] || a);
      return '<button type="button" class="suche-filter' + (a === bereich ? ' on' : '') +
        '" data-kind="' + a + '">' + esc(label) + ' <span class="suche-filter-n">' +
        n + '</span></button>';
    }).join('');
  }

  function zeichne(q) {
    var ws = TelcoSearch.worte(q);
    if (!ws.length) {
      titelEl.textContent = 'Suche im Archiv';
      bilanzEl.textContent = '';
      trefferEl.innerHTML = '';
      analyseEl.hidden = true;
      filterEl.hidden = true;
      if (startEl) startEl.hidden = false;
      document.title = 'Marktrecherche · Suche';
      return;
    }
    if (startEl) startEl.hidden = true;
    titelEl.textContent = q;
    document.title = q + ' · Dossier';

    TelcoSearch.loadIndex().then(function (alleEintraege) {
      var alle = TelcoSearch.suche(alleEintraege, q);
      filterZeile(alle, ws);
      filterEl.hidden = !alle.length;

      var gefiltert = bereich === 'all' ? alle
        : alle.filter(function (h) { return h.it.kind === bereich; });
      var treffer = gefiltert.map(function (h) { return h.it; });

      if (!treffer.length) {
        bilanzEl.textContent = '';
        analyseEl.hidden = true;
        trefferEl.innerHTML = '<p class="empty-note">Keine Treffer für „' +
          esc(q) + '“.</p>';
        return;
      }

      bilanzEl.textContent = bilanz(treffer, q);

      analyseEl.hidden = false;
      var proMonat = {};
      treffer.forEach(function (it) {
        var key = (it.date || '').slice(0, 7);
        if (key) proMonat[monatDe(key)] = (proMonat[monatDe(key)] || 0) + 1;
      });
      balken(verlaufEl, proMonat, 12, 'name');
      balken(werEl, zaehle(treffer, 'operator'), 8);
      balken(worumEl, zaehle(treffer, 'category'), 8);

      // Der Aufmacher: der staerkste Treffer, aber unter gleich starken der
      // mit Bild - eine leere grosse Position ist genau der Zustand, den die
      // Bebilderung gerade behebt.
      var sortiert = gefiltert.slice().sort(function (a, b) {
        return b.score - a.score ||
          (b.it.date || '').localeCompare(a.it.date || '');
      });
      var spitze = sortiert[0].score;
      var kopf = sortiert.filter(function (h) { return h.score === spitze; })
        .sort(function (a, b) { return (b.it.image ? 1 : 0) - (a.it.image ? 1 : 0); })[0].it;

      var rest = treffer.filter(function (it) { return it !== kopf; })
        .sort(function (a, b) {
          return (b.date || '').localeCompare(a.date || '') ||
            (b.relevance || 0) - (a.relevance || 0);
        });

      trefferEl.innerHTML =
        '<section class="dossier-lead">' + karte(kopf, ws, q, 'lead') + '</section>' +
        chronik(rest, ws, q);
    });
  }

  function lauf() {
    var q = (input.value || '').trim();
    try {
      var url = new URL(location.href);
      if (q) url.searchParams.set('q', q); else url.searchParams.delete('q');
      history.replaceState(null, '', url.pathname + url.search + url.hash);
    } catch (e) { /* URL() nicht verfuegbar - stiller Fallback, Seite bleibt nutzbar */ }
    zeichne(q);
  }

  input.addEventListener('input', function () {
    clearTimeout(t); t = setTimeout(lauf, 150);
  });
  if (form) {
    // Ohne das laedt das Formular die Seite neu und die Eingabe verliert den
    // Fokus - der Unterschied zwischen einer Suche und einem Seitenwechsel.
    form.addEventListener('submit', function (ev) { ev.preventDefault(); lauf(); });
  }
  filterEl.addEventListener('click', function (ev) {
    var btn = ev.target.closest ? ev.target.closest('.suche-filter') : null;
    if (!btn) return;
    bereich = btn.dataset.kind || 'all';
    zeichne((input.value || '').trim());
  });

  try {
    var q0 = new URLSearchParams(location.search).get('q');
    if (q0) input.value = q0;
  } catch (e) { /* URLSearchParams nicht verfuegbar - stiller Fallback */ }
  zeichne((input.value || '').trim());
})();

/* Meldungsseite (meldungen.html): die Ressortbloecke sind <details>.

   Der Filter, der hier bis zum 07.08.2026 stand, ist weg (Antonio: "macht
   diesen Filter weg ... das ist unnoetig") - samt der data-such-Attribute,
   die es nur fuer ihn gab. Was bleibt, ist der Weg von der Uebersichtskachel
   in die Tiefe: EINE Geste, nicht drei.

   Ohne dieses Skript funktioniert die Seite weiterhin - <details> klappt
   auch per Klick auf die Rubrikzeile auf. Das Skript erspart nur den
   zweiten Klick nach dem Sprung. */
(function () {
  'use strict';
  var tiefe = document.querySelector('.ressort-tiefe');
  if (!tiefe) return;

  function oeffne(id, scrollen) {
    var el = document.getElementById(id);
    if (!el || el.tagName.toLowerCase() !== 'details') return false;
    el.open = true;
    if (scrollen) {
      // Erst nach dem Aufklappen scrollen, sonst zielt der Browser auf die
      // Position von vorher.
      requestAnimationFrame(function () {
        el.scrollIntoView({ block: 'start', behavior: 'smooth' });
      });
    }
    return true;
  }

  document.addEventListener('click', function (ev) {
    var a = ev.target.closest ? ev.target.closest('[data-oeffnet]') : null;
    if (!a) return;
    if (oeffne(a.getAttribute('data-oeffnet'), true)) ev.preventDefault();
  });

  // Ankunft ueber einen Link von aussen (die Titelseite verlinkt
  // meldungen.html#ressort-netz) oder ueber die Adresszeile.
  function ausHash() {
    var id = (location.hash || '').replace(/^#/, '');
    if (id) oeffne(id, true);
  }
  window.addEventListener('hashchange', ausHash);
  ausHash();
})();

/* ===================================================================== *
 * Frag das Archiv (report/archiv_dossier.py als Browserfassung)
 *
 * Die Website ist eine Static Site OHNE Backend - das ist die Bedingung
 * dafuer, dass sie nie einschlaeft. Ein RAG-Aufbau braeuchte einen Dienst
 * zur Laufzeit, also gibt es hier BM25 im Browser und eine EXTRAKTIVE
 * Antwort: jede Zeile IST ein Archiveintrag, keine Umformulierung. Damit
 * kann eine Fussnote nicht auf etwas zeigen, das die Aussage nicht deckt.
 *
 * Die Konstanten unten muessen mit archiv_dossier.py uebereinstimmen -
 * ein Test haelt sie zusammen (test_archiv_dossier_js_und_python).
 * ===================================================================== */
var TelcoFrage = (function () {
  'use strict';

  var K1 = 1.5, B = 0.75, MIND_SCORE = 1.0, MAX_BELEGE = 8;
  var STOPP = ('der die das den dem des ein eine einen einem einer eines und '
    + 'oder aber auch mit von vom für fuer auf aus bei nach über ueber unter '
    + 'zwischen ist sind war waren wird werden wurde wurden hat haben hatte '
    + 'sich nicht kein keine als wie was wer wo wann warum welche welcher '
    + 'welches sein seine ihr ihre im in an am zu zum zur es sie er wir man '
    + 'mehr sehr schon noch nur dass denn doch so the and for of').split(' ');
  var STOPPSET = {};
  STOPP.forEach(function (w) { STOPPSET[w] = true; });

  function zerlege(text) {
    var treffer = String(text || '').toLowerCase()
      .match(/[a-zäöüßA-ZÄÖÜ0-9]{2,}/g) || [];
    return treffer.filter(function (w) { return !STOPPSET[w]; });
  }

  function baueIndex(items) {
    var docs = items.map(function (it) {
      return zerlege([it.title, it.summary, it.operator, it.category,
                      it.source_label].join(' '));
    });
    var df = {}, gesamt = 0;
    docs.forEach(function (d) {
      gesamt += d.length;
      var gesehen = {};
      d.forEach(function (w) {
        if (!gesehen[w]) { gesehen[w] = true; df[w] = (df[w] || 0) + 1; }
      });
    });
    var tf = docs.map(function (d) {
      var c = {};
      d.forEach(function (w) { c[w] = (c[w] || 0) + 1; });
      return c;
    });
    return { docs: docs, tf: tf, df: df, n: docs.length,
             avg: docs.length ? gesamt / docs.length : 0 };
  }

  function idf(idx, wort) {
    var d = idx.df[wort] || 0;
    return Math.log(1 + (idx.n - d + 0.5) / (d + 0.5));
  }

  function frage(items, text) {
    var worte = zerlege(text);
    if (!worte.length) {
      return { gefunden: false, belege: [],
               begruendung: 'Die Frage enthält keine durchsuchbaren Begriffe.' };
    }
    if (!items || !items.length) {
      return { gefunden: false, belege: [], begruendung: 'Das Archiv ist leer.' };
    }
    var idx = baueIndex(items);
    var einmalig = worte.filter(function (w, i) { return worte.indexOf(w) === i; });
    var bewertet = [];
    for (var i = 0; i < idx.n; i++) {
      if (!idx.docs[i].length) continue;
      var norm = K1 * (1 - B + B * idx.docs[i].length / (idx.avg || 1));
      var score = 0, getroffen = [];
      einmalig.forEach(function (w) {
        var f = idx.tf[i][w] || 0;
        if (!f) return;
        getroffen.push(w);
        score += idf(idx, w) * (f * (K1 + 1)) / (f + norm);
      });
      if (score >= MIND_SCORE) {
        bewertet.push({ score: score, treffer: getroffen, item: items[i] });
      }
    }
    if (!bewertet.length) {
      return { gefunden: false, belege: [], begruendung:
        'Dazu steht nichts im Archiv. Das heißt nicht, dass es nichts gibt — '
        + 'es heißt, dass keine der bisher erfassten Meldungen die Frage berührt.' };
    }
    bewertet.sort(function (a, b) {
      return b.score - a.score
        || String(b.item.date || '').localeCompare(String(a.item.date || ''));
    });
    var gesehen = {}, belege = [];
    for (var j = 0; j < bewertet.length && belege.length < MAX_BELEGE; j++) {
      var key = bewertet[j].item.url || bewertet[j].item.title || '';
      if (key && gesehen[key]) continue;
      gesehen[key] = true;
      belege.push(bewertet[j]);
    }
    return { gefunden: true, belege: belege, begruendung: '' };
  }

  function rendern(ziel, antwort) {
    if (!ziel) return;
    var esc = TelcoSearch.esc;
    if (!antwort.gefunden) {
      ziel.innerHTML = '<h2 class="rubrik">Was das Archiv dazu belegt</h2>'
        + '<p class="fa-leer">' + esc(antwort.begruendung) + '</p>';
      ziel.hidden = false;
      return;
    }
    var zeilen = antwort.belege.map(function (b) {
      var it = b.item;
      return '<li class="fa-beleg">'
        + '<b>' + esc(it.title || '') + '</b>'
        + (it.summary ? '<span>' + esc(it.summary) + '</span>' : '')
        + '<i>' + esc(it.source_label || it.operator || '')
        + (it.date ? ' · ' + esc(it.date) : '') + '</i>'
        + (it.url ? '<a href="' + esc(it.url) + '" rel="noopener">Quelle</a>' : '')
        + '</li>';
    }).join('');
    ziel.innerHTML = '<h2 class="rubrik">Was das Archiv dazu belegt</h2>'
      + '<p class="fa-hinweis">Jede Zeile ist eine erfasste Meldung im '
      + 'Wortlaut, keine Zusammenfassung. Was hier nicht steht, belegt das '
      + 'Archiv nicht.</p><ol class="fa-liste">' + zeilen + '</ol>';
    ziel.hidden = false;
  }

  return { zerlege: zerlege, frage: frage, rendern: rendern,
           K1: K1, B: B, MIND_SCORE: MIND_SCORE, MAX_BELEGE: MAX_BELEGE };
})();

/* Auf der Dossier-Seite: die Antwort steht ueber den Treffern. */
(function () {
  var ziel = document.getElementById('dossier-antwort');
  if (!ziel || typeof TelcoSearch === 'undefined') return;
  var eingabe = document.getElementById('dossier-input');
  function lauf() {
    var q = (eingabe && eingabe.value || '').trim();
    if (!q) { ziel.hidden = true; return; }
    TelcoSearch.loadIndex().then(function (items) {
      TelcoFrage.rendern(ziel, TelcoFrage.frage(items, q));
    });
  }
  lauf();
  if (eingabe) {
    eingabe.form && eingabe.form.addEventListener('submit', function () {
      setTimeout(lauf, 0);
    });
  }
})();

/* ---------------------------------------------------------------------- *
 * Geraeteradar: Reiter, Filter, Zeilenaufklapper.
 *
 * Alle Tafeln stehen fertig im HTML - hier wird nur umgeblendet, nichts
 * nachgeladen und nichts neu gerechnet. Genauso die Filter: sie BLENDEN
 * Zeilen aus, sie sortieren nicht um. Wer ohne JavaScript liest, sieht die
 * erste Tafel vollstaendig; das ist die Tafel, die die Frage der Seite
 * beantwortet.
 *
 * Bis zum 30.08.2026 stand hier der Umschalter der Positionskarte samt
 * Punktfilter. Die Grafik ist geloescht - 114 gedrehte Achsenbeschriftungen,
 * 155 von 164 Punkten ohne Beschriftung -, und mit ihr dieser Code.
 * ---------------------------------------------------------------------- */
(function () {
  var leiste = document.querySelector('.gr-reiter');
  if (!leiste) return;
  var knoepfe = leiste.querySelectorAll('button[data-tafel]');

  Array.prototype.forEach.call(knoepfe, function (knopf) {
    knopf.addEventListener('click', function () {
      Array.prototype.forEach.call(knoepfe, function (k) {
        var ziel = document.getElementById(k.getAttribute('data-tafel'));
        var aktiv = k === knopf;
        k.setAttribute('aria-selected', aktiv ? 'true' : 'false');
        if (ziel) ziel.classList.toggle('gr-tafel--aus', !aktiv);
      });
    });
  });
})();
/* Die Alarmtabelle: Filter, Suche, Zeilenaufklapper, "alle anzeigen".
 *
 * Der Aufklapper einer ausgeblendeten Zeile geht mit; sonst haengt eine
 * Anbieterliste unter einer Zeile, die nicht mehr da ist. Dieselbe Falle
 * wie beim alten Vergleichsfilter, nur an einer neuen Stelle.
 */
/* Seit dem 30.08.2026 traegt diese Mechanik ZWEI Tabellen: die Alarme in
 * Reiter 1 und den flachen Katalog in Reiter 2. Beide haben dieselbe
 * Filterleiste und denselben "alle zeigen"-Knopf; sie unterscheiden sich nur
 * in den Spalten. Eine zweite Kopie dieser Funktion waere eine zweite Stelle,
 * an der die Kaskadenfalle mit `hidden` repariert werden muesste. */
function grFilterleiste(tafelId, mehrId) {
  var tafel = document.getElementById(tafelId);
  if (!tafel) return;
  var tabelle = tafel.querySelector('.gr-alarm');
  if (!tabelle) return;

  var felder = tafel.querySelectorAll('[data-filter]');
  var mehr = document.getElementById(mehrId);
  // Der ganze Absatz, nicht nur der Knopf: ein leeres <p> mit Rand bliebe
  // sonst als Luecke stehen, sobald der Knopf sich versteckt.
  var mehrAbsatz = mehr ? (mehr.closest('p') || mehr) : null;

  /* DER DECKEL FOLGT DEM FILTER (B2/B3, 31.08.2026 - Runde 2 der
     Zurueckweisung).

     Bis dahin klebte `gr-a-rest` an einer POSITION: einmal beim Laden aus
     der SSR-Reihenfolge gesetzt, einmal je Sortierklick neu vergeben
     (`sortiere()`), aber in BEIDEN Faellen unabhaengig davon, ob die Zeile
     an dieser Position ueberhaupt zum aktiven Filter passte. Zwei Klicks
     auf den Spaltenkopf "Zustand" (Reiter 2, Vorbelegung "neu") reichten,
     um elf nicht-passende Zeilen in den Deckel zu schieben und 348
     passende dahinter verschwinden zu lassen - derselbe Fehlertyp wie
     Commit 79085f0, nur ueber einen anderen Ausloeser.

     Jetzt zaehlt `anwenden()` NUR unter den TREFFERN: die ersten `deckel`
     Zeilen, die den aktiven Filter bestehen, bleiben sichtbar (oder alle,
     sobald "alle anzeigen" gedrueckt ist) - unabhaengig davon, an welcher
     Position sie in der aktuellen Sortierung stehen. `sortiere()` muss
     `gr-a-rest` deshalb nicht mehr selbst vergeben; sie ordnet nur noch die
     DOM-Knoten um und ruft danach `anwenden()`.

     Und der Knopf "alle N zeigen" verspricht nur noch, was er wirklich
     liefert: N ist die Zahl der TREFFER unter dem aktiven Filter, nicht die
     serverseitige Gesamtzahl - sonst versprach er bei aktivem "neu"-Filter
     "alle 360 zeigen" und lieferte 349 (B3). Die serverseitige Zahl
     (Ueberschrift, Export) bleibt unveraendert die Gesamtzahl - sie ist
     eine Aussage ueber den BESTAND, kein Versprechen ueber diese Anzeige. */
  var deckel = tabelle.querySelectorAll('.gr-a-zeile.gr-a-rest').length
             ? tabelle.querySelectorAll('.gr-a-zeile').length -
               tabelle.querySelectorAll('.gr-a-zeile.gr-a-rest').length
             : 0;

  function anwenden() {
    var alleZeigen = tabelle.classList.contains('gr-alarm--alle');
    var wahl = {};
    var suche = '';
    Array.prototype.forEach.call(felder, function (f) {
      var name = f.getAttribute('data-filter');
      if (name === 'suche') suche = (f.value || '').trim().toLowerCase();
      else wahl[name] = f.value || '';
      // Ein aktiver Filter ist rot hinterlegt. Er veraendert, was darunter
      // steht, und das muss man sehen, ohne die Auswahl zu lesen.
      var etikett = f.closest('label');
      if (etikett && name !== 'suche') {
        etikett.classList.toggle('gr-filter--an', !!f.value);
      }
    });

    var zeilen = tabelle.querySelectorAll('.gr-a-zeile');
    var treffer = 0;   // wie viele Zeilen ueberhaupt zum Filter passen
    var sichtbar = 0;  // wie viele davon der Deckel wirklich zeigt
    for (var i = 0; i < zeilen.length; i++) {
      var z = zeilen[i];
      var passt = true;
      for (var name in wahl) {
        if (wahl[name] && z.getAttribute('data-' + name) !== wahl[name]) {
          passt = false;
        }
      }
      if (passt && suche) {
        passt = z.textContent.toLowerCase().indexOf(suche) >= 0;
      }
      var auf = document.getElementById(z.getAttribute('data-auf'));
      z.hidden = !passt;
      if (auf) auf.hidden = !passt;
      if (passt) {
        treffer++;
        // P1 (dritte Nachbesserung, 31.08.2026): eine `blockrest`-Zeile
        // (mehr als `BLOCK_SICHTBAR` Zeilen ihres eigenen Geraete-Blocks)
        // bleibt IMMER verborgen, unabhaengig vom Positionsdeckel - sie
        // zaehlt deshalb auch nicht gegen `sichtbar`. Ohne diese
        // Unterscheidung fuellte ein einzelner Block mit sieben
        // Farbvarianten desselben Geraets einen Grossteil der zwoelf
        // sichtbaren Zeilen der GANZEN Tabelle; mit ihr bleiben davon nur
        // die zwei guenstigsten je Anbieter sichtbar (siehe
        // `geraete_view._interleave_je_anbieter_im_block`), der Rest steht
        // direkt dahinter bereit, sobald "alle anzeigen" gedrueckt ist.
        var blockRest = z.getAttribute('data-blockrest') === '1';
        // Siehe Kommentar bei `var deckel` oben: der Positionsdeckel
        // zaehlt nur unter den TREFFERN, nicht nach roher Position.
        var raus = (blockRest && !alleZeigen)
                 || (deckel > 0 && !alleZeigen && sichtbar >= deckel);
        z.classList.toggle('gr-a-rest', raus);
        if (auf) auf.classList.toggle('gr-a-rest', raus);
        if (!raus) sichtbar++;
      }
      // Eine nicht-passende Zeile behaelt ihre `gr-a-rest`-Klasse
      // unveraendert - sie ist ohnehin `hidden`, und wird sie spaeter
      // wieder zum Treffer, rechnet der naechste Lauf dieser Schleife sie
      // frisch ein.
    }
    var leer = tafel.querySelector('.gr-a-leer');
    if (leer) leer.hidden = sichtbar > 0;

    if (mehrAbsatz) {
      mehrAbsatz.hidden = alleZeigen || treffer <= deckel;
      if (mehr) mehr.textContent = 'alle ' + treffer + ' Zeilen zeigen';
    }
  }

  Array.prototype.forEach.call(felder, function (f) {
    f.addEventListener('input', anwenden);
    f.addEventListener('change', anwenden);
  });

  // Klick auf eine Zeile klappt alle Anbieter dieses Geraets auf.
  tabelle.addEventListener('click', function (ev) {
    if (ev.target.closest('a')) return;   // der Quelllink fuehrt hinaus
    var zeile = ev.target.closest ? ev.target.closest('.gr-a-zeile') : null;
    if (!zeile) return;
    var auf = document.getElementById(zeile.getAttribute('data-auf'));
    if (auf) auf.classList.toggle('gr-a-auf--an');
  });
  tabelle.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Enter' && ev.key !== ' ') return;
    // B5 (31.08.2026): derselbe Ausstieg wie im `click`-Handler oben fehlte
    // hier. Ohne ihn ass `preventDefault()` das Enter eines fokussierten
    // Quelllinks: fokussierbar, aber mit der Tastatur nicht auszuloesen -
    // genau die Zugaenglichkeit, mit der B7 begruendet wurde, und B7
    // vergroessert die betroffene Flaeche vom 5-px-Pfeil auf den ganzen
    // Namen.
    if (ev.target.closest('a')) return;
    var zeile = ev.target.closest ? ev.target.closest('.gr-a-zeile') : null;
    if (!zeile) return;
    ev.preventDefault();
    var auf = document.getElementById(zeile.getAttribute('data-auf'));
    if (auf) auf.classList.toggle('gr-a-auf--an');
  });

  /* SORTIEREN NACH SPALTE.

     Zwei Dinge, die hier leicht falsch gehen, und beide sind gemeint:

     1. EINE ZEILE IST ZWEI ZEILEN. Zu jeder `.gr-a-zeile` gehoert ein
        `.gr-a-auf` mit der Anbieterliste. Verschoben werden sie IMMER
        zusammen - sonst haengt eine Anbieterliste unter einem fremden
        Geraet, und zwar ohne dass es auffiele, solange sie zugeklappt ist.

     2. SORTIERT WIRD NACH DEM ROHWERT, nicht nach dem Zelltext. "1.099,90 €"
        ist als Zeichenkette kleiner als "199,00 €"; ein Sortierer, der die
        Zelle liest, stellt den teuersten Preis nach vorn und sieht dabei
        richtig aus.

     Der DECKEL wird hier NICHT mehr vergeben (B2, 31.08.2026) - das
     erledigt `anwenden()` am Ende dieser Funktion, filterbewusst statt
     positionsbewusst. Diese Funktion ordnet nur noch die DOM-Knoten um. */
  var koepfe = tabelle.querySelectorAll('.gr-sort');

  function sortiere(schluessel, art, richtung) {
    var rumpf = tabelle.tBodies[0];
    if (!rumpf) return;
    var paare = [];
    Array.prototype.forEach.call(
      tabelle.querySelectorAll('.gr-a-zeile'), function (z) {
        paare.push({ zeile: z, wert: z.getAttribute('data-s-' + schluessel) || '',
                     auf: document.getElementById(z.getAttribute('data-auf')) });
      });
    var vz = richtung === 'ab' ? -1 : 1;
    paare.sort(function (a, b) {
      if (art === 'zahl') {
        var x = parseFloat(a.wert), yy = parseFloat(b.wert);
        if (isNaN(x)) x = -Infinity;
        if (isNaN(yy)) yy = -Infinity;
        if (x !== yy) return (x - yy) * vz;
        return 0;
      }
      return a.wert.localeCompare(b.wert, 'de') * vz;
    });
    paare.forEach(function (p) {
      rumpf.appendChild(p.zeile);
      if (p.auf) rumpf.appendChild(p.auf);
    });
    anwenden();
  }

  Array.prototype.forEach.call(koepfe, function (k) {
    k.addEventListener('click', function () {
      var schluessel = k.getAttribute('data-sort');
      var art = k.getAttribute('data-art') || 'text';
      // Erster Klick auf eine Zahlenspalte sortiert ABSTEIGEND: wer auf
      // "Unterschied" klickt, will den groessten sehen, nicht den kleinsten.
      // Bei Text ist es umgekehrt.
      var vorher = k.getAttribute('data-vor');
      var richtung;
      if (vorher === 'ab') richtung = 'auf';
      else if (vorher === 'auf') richtung = 'ab';
      else richtung = (art === 'zahl') ? 'ab' : 'auf';
      Array.prototype.forEach.call(koepfe, function (a) {
        a.removeAttribute('data-vor');
        a.removeAttribute('aria-sort');
      });
      k.setAttribute('data-vor', richtung);
      k.setAttribute('aria-sort',
                     richtung === 'ab' ? 'descending' : 'ascending');
      sortiere(schluessel, art, richtung);
    });
  });

  // Einmal beim Laden. Manche Browser stellen Formularwerte beim Reload
  // wieder her; ohne diesen Aufruf zeigt die Tabelle dann ungefiltert an,
  // was das Auswahlfeld daneben nicht sagt.
  anwenden();

  if (mehr) {
    mehr.addEventListener('click', function () {
      tabelle.classList.add('gr-alarm--alle');
      anwenden();
    });
  }
}

grFilterleiste('tafel-alarme', 'gr-mehr');
grFilterleiste('tafel-katalog', 'gr-kmehr');

/* =========================================================================
   NEWSLETTER-ANMELDUNG
   =========================================================================
   Drei Dinge passieren hier, und das erste ist das, das man leicht vergisst.

   1. `GET /form-token` wird beim SEITENAUFBAU geholt, nicht beim Absenden.
      Render Free faehrt den Signup-Dienst nach 15 Minuten ohne Verkehr
      herunter, das Aufwachen dauert rund eine Minute. Wer die Kennung erst
      beim Klick holt, laesst den Nutzer diese Minute vor einem Spinner
      warten. Geholt beim Aufbau, weckt sie die Instanz, waehrend er noch
      ausfuellt.
   2. Die Stichwort-Vorschau zaehlt CLIENTSEITIG gegen
      `data/keyword-index.json`. Sie kann `preview_keyword` nicht aufrufen -
      die Seite ist statisch, und der Signup-Dienst kennt die Berichtsarchive
      nicht. Die Datei schreibt die Pipeline bei jedem Lauf mit, und ein Test
      haelt jedes ihrer Woerter gegen `vorschau()`.
   3. Der Kaltstart wird trotzdem abgefangen: sofort "Wird verarbeitet ...",
      Timeout 90 Sekunden, danach eine verstaendliche Meldung mit
      Wiederholmoeglichkeit. Kein haengender Spinner.
   ====================================================================== */
(function () {
  var form = document.getElementById('nl-form');
  if (!form) return;
  var konfigEl = document.getElementById('nl-config');
  var K = {};
  try { K = JSON.parse(konfigEl ? konfigEl.textContent : '{}'); } catch (e) {}

  var status = document.getElementById('nl-status');
  var submit = document.getElementById('nl-submit');
  var gesperrt = form.getAttribute('data-gesperrt') === '1' || !K.frei || !K.dienst;
  var nonce = '';
  var stichwoerter = [];
  var index = null;

  function sagen(text, art) {
    status.textContent = text || '';
    status.className = 'nl-status' + (art ? ' nl-status--' + art : '');
  }

  /* ---- 1. Die Kennung beim Seitenaufbau holen. Weckt die Instanz. ---- */
  if (!gesperrt) {
    fetch(K.dienst + '/form-token', { method: 'GET' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (d && d.nonce) nonce = d.nonce; })
      .catch(function () { /* still: der Absendeweg faengt es ab */ });
  } else if (K.frei && !K.dienst) {
    sagen('Der Anmeldedienst ist noch nicht eingerichtet.', 'warn');
  }

  /* ---- 2. Stichwoerter: Vorschau gegen den Index ---------------------- */
  function indexLaden() {
    if (index) return Promise.resolve(index);
    return fetch('data/keyword-index.json')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { index = d || { woerter: {}, meldungen: 0 }; return index; })
      .catch(function () { index = { woerter: {}, meldungen: 0 }; return index; });
  }

  /* Dieselbe Rechnung wie `filters.vorschau()`: gezaehlt werden MELDUNGEN,
     die das Wort enthalten, nicht Vorkommen. Fuer eine Phrase laesst sich
     das aus einem Wortindex nur nach oben abschaetzen - dann sagt die
     Vorschau "höchstens N" und behauptet keine Zahl, die sie nicht hat. */
  function schaetzen(term) {
    var teile = term.toLowerCase().split(/\s+/).filter(function (w) {
      return w.length >= (K.min_laenge || 4);
    });
    if (!teile.length) return null;
    var werte = teile.map(function (w) { return index.woerter[w] || 0; });
    var n = Math.min.apply(null, werte);
    return { n: n, genau: teile.length === 1 };
  }

  var feld = document.getElementById('nl-stichwort');
  var vorschau = document.getElementById('nl-stichwort-vorschau');
  var liste = document.getElementById('nl-stichwort-liste');

  function vorschauZeigen() {
    var term = (feld.value || '').trim();
    if (term.length < (K.min_laenge || 4)) { vorschau.textContent = ''; return; }
    indexLaden().then(function () {
      var s = schaetzen(term);
      if (!s) { vorschau.textContent = ''; return; }
      var tage = K.vorschau_tage || 30;
      vorschau.textContent = (s.genau ? '' : 'höchstens ') + s.n +
        ' Meldung' + (s.n === 1 ? '' : 'en') + ' in den letzten ' + tage + ' Tagen';
      vorschau.className = 'nl-vorschau' +
        (s.n >= (K.warnung_ab || 25) ? ' nl-vorschau--warn' : '') +
        (s.n === 0 ? ' nl-vorschau--null' : '');
      if (s.n >= (K.warnung_ab || 25)) {
        vorschau.textContent += ' — das ist viel. Enger fassen?';
      } else if (s.n === 0) {
        vorschau.textContent += ' — dazu kam bisher nichts.';
      }
    });
  }

  feld.addEventListener('input', vorschauZeigen);

  function chipsZeichnen() {
    liste.textContent = '';
    stichwoerter.forEach(function (term, i) {
      var li = document.createElement('li');
      li.className = 'nl-chip';
      li.appendChild(document.createTextNode(term));
      var weg = document.createElement('button');
      weg.type = 'button';
      weg.className = 'nl-chip-weg';
      weg.textContent = '×';
      weg.setAttribute('aria-label', 'Stichwort ' + term + ' entfernen');
      weg.addEventListener('click', function () {
        stichwoerter.splice(i, 1);
        chipsZeichnen();
      });
      li.appendChild(weg);
      liste.appendChild(li);
    });
  }

  document.getElementById('nl-stichwort-add').addEventListener('click', function () {
    var term = (feld.value || '').trim();
    var min = K.min_laenge || 4;
    var laengstes = term.split(/\s+/).reduce(function (a, w) {
      return Math.max(a, w.length);
    }, 0);
    if (laengstes < min) {
      sagen('Stichwörter brauchen mindestens ein Wort mit ' + min +
            ' Zeichen — kurze Begriffe treffen zu viel.', 'warn');
      return;
    }
    if (stichwoerter.length >= (K.max_stichwoerter || 10)) {
      sagen('Höchstens ' + (K.max_stichwoerter || 10) + ' Stichwörter.', 'warn');
      return;
    }
    if (stichwoerter.indexOf(term) < 0) stichwoerter.push(term);
    feld.value = '';
    vorschau.textContent = '';
    sagen('');
    chipsZeichnen();
  });

  feld.addEventListener('keydown', function (ev) {
    if (ev.key === 'Enter') {
      ev.preventDefault();
      document.getElementById('nl-stichwort-add').click();
    }
  });

  /* ---- 3. Absenden, mit Kaltstart-Behandlung -------------------------- */
  function gewaehlt(feldName) {
    return Array.prototype.slice.call(
      form.querySelectorAll('input[name="' + feldName + '"]:checked')
    ).map(function (el) { return el.value; });
  }

  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    if (gesperrt) {
      sagen('Die Anmeldung ist noch nicht freigeschaltet.', 'warn');
      return;
    }
    var email = (document.getElementById('nl-email').value || '').trim();
    if (!email || email.indexOf('@') < 1) {
      sagen('Bitte eine gültige E-Mail-Adresse eintragen.', 'warn');
      return;
    }
    if (!document.getElementById('nl-consent').checked) {
      sagen('Ohne dein Häkchen bei der Einwilligung geht es nicht.', 'warn');
      return;
    }

    var koerper = {
      email: email,
      nonce: nonce,
      consent: true,
      website: (form.querySelector('input[name="website"]') || {}).value || '',
      filters: {
        branches: gewaehlt('branches'),
        regions: gewaehlt('regions'),
        competitors: gewaehlt('competitors'),
        categories: gewaehlt('categories'),
        keywords: stichwoerter.map(function (t) { return { term: t }; })
      }
    };

    submit.disabled = true;
    sagen('Wird verarbeitet …');

    /* 90 Sekunden. Der Kaltstart dauert rund eine Minute, und der Nutzer
       soll danach eine Antwort bekommen - keinen ewigen Spinner. */
    var abbruch = new AbortController();
    var uhr = setTimeout(function () { abbruch.abort(); }, 90000);

    fetch(K.dienst + '/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(koerper),
      signal: abbruch.signal
    }).then(function (r) {
      return r.json().then(function (d) { return { ok: r.ok, daten: d }; });
    }).then(function (a) {
      clearTimeout(uhr);
      submit.disabled = false;
      if (a.ok) {
        sagen(a.daten.message || 'Sieh bitte in dein Postfach.', 'ok');
        form.querySelector('#nl-email').value = '';
        document.getElementById('nl-consent').checked = false;
      } else {
        sagen((a.daten.fehler || ['Das hat nicht geklappt.']).join(' '), 'warn');
      }
    }).catch(function (err) {
      clearTimeout(uhr);
      submit.disabled = false;
      /* Der Dienst schlaeft nach 15 Minuten ohne Verkehr ein. Das ist der
         haeufigste Fall hier - und er ist beim zweiten Versuch weg. */
      sagen(err && err.name === 'AbortError'
        ? 'Der Anmeldedienst antwortet gerade nicht (er wacht nach einer '
          + 'Pause erst auf). Bitte noch einmal auf „Anmelden“ klicken.'
        : 'Verbindung zum Anmeldedienst fehlgeschlagen. Bitte später noch '
          + 'einmal versuchen.', 'warn');
    });
  });
})();

/* ===================================================================
   Geraeteradar, Reiter 3: der Preisverlauf EINES Geraets.

   Das einzige Diagramm der Seite. Es entsteht erst nach einer Auswahl -
   ohne Auswahl steht dort ein Satz und KEIN leeres SVG, weil ein leerer
   Rahmen so aussieht, als seien die Daten weg.

   Gezeichnet wird von Hand: reines SVG, keine Bibliothek, kein CDN. Die
   Reihen kommen fertig gerechnet aus `report/geraete_verlauf.py`; hier
   passiert nur Geometrie.

   DIE ZWEI HARTEN GRENZEN, beide aus dem Auftrag und beide der Grund,
   warum diese Achse lesbar ist, wo die geloeschte Grafik es nicht war:
   hoechstens acht Linien (das rechnet das Python-Modul) und hoechstens
   acht WAAGERECHTE Datumsbeschriftungen (das rechnet `beschriftung()`).
   Weitere Messpunkte werden gezeichnet, nur nicht beschriftet. Kein
   gedrehter Text, keine Schrift unter 12 px, nichts mit "..." gekuerzt.
   =================================================================== */
(function () {
  var daten = document.getElementById('gr-verlaufdaten');
  var feld = document.getElementById('gr-vsuche');
  if (!daten || !feld) return;

  var GERAETE = [];
  try { GERAETE = JSON.parse(daten.textContent) || []; } catch (e) { return; }
  if (!GERAETE.length) return;

  var NS = 'http://www.w3.org/2000/svg';
  var BREITE = 1080, HOEHE = 340;
  var RAND = { oben: 18, rechts: 20, unten: 46, links: 74 };
  var MAX_MARKEN = 8;

  var treffer = document.getElementById('gr-vtreffer');
  var steuer = document.getElementById('gr-vsteuer');
  var kacheln = document.getElementById('gr-vkacheln');
  var leer = document.getElementById('gr-vleer');
  var bild = document.getElementById('gr-vbild');
  var legende = document.getElementById('gr-vlegende');
  var tabelle = document.getElementById('gr-vtabelle');
  var zukurz = document.getElementById('gr-vzukurz');
  var stand = document.getElementById('gr-vstand');
  /* Die zwei Schwellen kommen aus `report/geraete_verlauf.py` und stehen als
     data-Attribute am Satz. Sie hier zu wiederholen waeren zwei Zahlen fuer
     dieselbe Regel - genau der Fehler, den CLAUDE.md 6 fuer die
     Stichwort-Vorschau beschreibt. */
  var AB_TERMINEN = parseInt((stand && stand.dataset.abterminen) || '4', 10);
  /* Zwei Linien, die naeher als das beieinander liegen, sind im Bild eine.
     Anteil der gezeichneten Preisspanne, nicht Euro: 90 Cent sind bei einer
     Spanne von 307 Euro unsichtbar und bei einer von 5 Euro deutlich.

     AUS DEM MODUL, nicht hier hartkodiert. Die erste Fassung schrieb 0.02
     an beide Stellen - `geraete_verlauf.LINIEN_ABSTAND` reiste in den
     View-Dict und wurde von niemandem gelesen. Wer die Python-Konstante
     geaendert haette, haette die Seite nicht geaendert; genau die
     Fehlerklasse, die der Kommentar zu AB_TERMINEN zwei Zeilen weiter oben
     vermeidet (CLAUDE.md §6, Stichwort-Vorschau). */
  var ABSTAND = parseFloat((stand && stand.dataset.abstand) || '0.02');
  var von = document.getElementById('gr-vvon');
  var bis = document.getElementById('gr-vbis');
  var gewaehlt = null, raster = 'woche';

  function euro(n) {
    return n.toLocaleString('de-DE', { minimumFractionDigits: 2,
                                       maximumFractionDigits: 2 }) + ' €';
  }
  function tagDE(iso) {
    var t = iso.split('-');
    return t[2].replace(/^0/, '') + '.' + t[1].replace(/^0/, '') + '.';
  }
  var MONATE = ['Jan','Feb','Mär','Apr','Mai','Jun',
                'Jul','Aug','Sep','Okt','Nov','Dez'];
  /* Die Beschriftung nennt, was das Raster ZUSAMMENFASST. Eine
     "Quartal"-Ansicht mit zwei Tagesmarken behauptet eine Genauigkeit, die
     sie gerade weggerechnet hat. */
  function markeDE(iso, wie) {
    var t = iso.split('-');
    if (wie === 'monat') return MONATE[parseInt(t[1], 10) - 1] + ' ' + t[0];
    if (wie === 'quartal') {
      return 'Q' + Math.ceil(parseInt(t[1], 10) / 3) + ' ' + t[0];
    }
    return tagDE(iso);
  }
  /* Tage seit einem festen Nullpunkt - ohne `new Date()`, damit die Rechnung
     nicht an der Zeitzone des Lesers haengt. */
  function tagNr(iso) {
    var t = iso.split('-').map(Number);
    var a = (t[0] * 12 + (t[1] - 1)) / 12;
    return Math.floor(a * 365.2425) + t[2];
  }

  /* Welche Tage eine Beschriftung bekommen.

     Nie mehr als MAX_MARKEN, und immer der erste und der letzte - eine
     Achse, deren Enden unbeschriftet sind, sagt nicht, welchen Zeitraum
     sie zeigt. Dazwischen wird gleichmaessig ausgeduennt. */
  function beschriftung(tage) {
    if (tage.length <= MAX_MARKEN) return tage.slice();
    var schritt = (tage.length - 1) / (MAX_MARKEN - 1), raus = [];
    for (var i = 0; i < MAX_MARKEN; i++) raus.push(tage[Math.round(i * schritt)]);
    return raus.filter(function (t, i, a) { return a.indexOf(t) === i; });
  }

  /* Die Reihe auf das gewaehlte Raster zusammenfassen.

     Je Zeitfenster bleibt der LETZTE Messpunkt stehen, nicht der
     Mittelwert: ein Mittelwert aus zwei Preisen ist ein Preis, den nie
     jemand verlangt hat. */
  function fassen(punkte, wie) {
    var je = {};
    punkte.forEach(function (p) {
      var t = p.datum.split('-');
      var k;
      if (wie === 'monat') { k = t[0] + '-' + t[1]; }
      else if (wie === 'quartal') {
        k = t[0] + '-Q' + Math.ceil(parseInt(t[1], 10) / 3);
      } else {
        // Woechentlich hiess bis zum 30.08.2026 "gar nicht" - der Knopf gab
        // die Punkte unveraendert zurueck und zeigte damit Rohtage. Jetzt
        // fasst er wirklich je Kalenderwoche zusammen (Montag als Anker,
        // ohne `new Date()`).
        k = String(Math.floor(tagNr(p.datum) / 7));
      }
      if (!je[k] || p.datum > je[k].datum) je[k] = p;
    });
    return Object.keys(je).map(function (k) { return je[k]; })
      .sort(function (a, b) { return a.datum < b.datum ? -1 : 1; });
  }

  function el(name, attrs, text) {
    var n = document.createElementNS(NS, name);
    for (var k in attrs) if (attrs[k] !== null) n.setAttribute(k, attrs[k]);
    if (text !== undefined) n.textContent = text;
    return n;
  }

  /* EINE ZAHL ZUR ZEIT.

     Ohne Auswahl spricht der Satz unter dem Diagramm ueber den ganzen Radar
     ("seit dem 10. August, 5 Messtermine"). Sobald ein Geraet gewaehlt ist,
     spricht er ueber DIESES Geraet - denn daneben steht dann die Kachel mit
     genau dieser Zahl. Am 30.08.2026 standen beide gleichzeitig da, die
     Kachel mit 4 und der Satz mit 5, und beide hatten recht: die eine
     zaehlte die Termine dieses Geraets, die andere die aller Geraete. Zwei
     richtige Zahlen fuer scheinbar dieselbe Sache sind fuer den Leser ein
     Fehler der Seite. */
  function termine(n) {
    return n === 1 ? 'liegt 1 Messtermin' : 'liegen ' + n + ' Messtermine';
  }
  /* `tagDE` endet auf einem Punkt ("30.8."). Ein Satzpunkt dahinter ergibt
     "30.8.." - im ersten Anlauf genau so auf der Seite gestanden, an ZWEI
     Stellen. Deshalb setzt `punkt()` das Satzende, nicht der Aufrufer. */
  function spanne(tage) {
    return 'vom ' + tagDE(tage[0]) + ' bis zum ' + tagDE(tage[tage.length - 1]);
  }
  function punkt(text) {
    return text.charAt(text.length - 1) === '.' ? text : text + '.';
  }

  function satzFuer(g, tage, gezeichnet) {
    if (!stand) return;
    var wochen = stand.dataset.wochen;
    var nachsatz = ' Aussagen zu Preisverfall und Verweildauer ab etwa ' +
                   wochen + ' Wochen.';
    if (!g || !tage || !tage.length) {
      stand.hidden = false;
      stand.textContent = 'Preisverlauf wird seit dem ' +
        stand.dataset.seit + ' erfasst – ' + stand.dataset.alle + ' ' +
        (stand.dataset.alle === '1' ? 'Messtermin' : 'Messtermine') + '.' +
        nachsatz;
      return;
    }
    /* UNTER DEM GATTER SCHWEIGT DIESER SATZ. Der Hinweis an der Stelle des
       Diagramms sagt dann dasselbe, und zwar dort, wo die Frage entsteht -
       beide zusammen waeren dieselbe Zahl zweimal auf einem Bildschirm,
       genau die Beruhigungsregel aus CLAUDE.md 5. */
    if (tage.length < AB_TERMINEN || gezeichnet < AB_TERMINEN) {
      stand.hidden = true; return;
    }
    stand.hidden = false;
    stand.textContent = punkt('Für dieses Gerät ' + termine(tage.length) +
      ' vor, ' + spanne(tage)) + nachsatz;
  }

  function zeichne(g) {
    var vonT = von.value, bisT = bis.value;
    /* EIN MESSTERMIN IST EIN TAG, AN DEM GEMESSEN WURDE - unabhaengig
       davon, welches Raster gerade gewaehlt ist.

       Die erste Fassung zaehlte die Termine NACH `fassen()`, also die
       gefuellten Zeitfenster. Beim Galaxy S25 128 GB standen damit "3
       Messtermine" an der Kachel, obwohl an vier Tagen gemessen wurde -
       zwei davon lagen in derselben Kalenderwoche. Der Umschalter
       "Woechentlich/Monatlich" haette so die Zahl der Messungen veraendert,
       und im Quartalsraster haette JEDES Geraet genau einen Termin gehabt.

       Das Raster formt die LINIE, es formt nicht die Datenlage. Kachel,
       Gatter und Satz rechnen deshalb auf `rohTage`; nur die Achse rechnet
       auf den zusammengefassten Punkten. */
    var gefiltert = g.reihen.map(function (r) {
      return { anbieter: r.anbieter, farbe: r.farbe, eigen: r.eigen,
               roh: r.punkte.filter(function (p) {
                 return (!vonT || p.datum >= vonT) && (!bisT || p.datum <= bisT);
               }) };
    });
    var rohMenge = {};
    gefiltert.forEach(function (r) {
      r.roh.forEach(function (p) { rohMenge[p.datum] = 1; });
    });
    var rohTage = Object.keys(rohMenge).sort();

    var reihen = gefiltert.map(function (r) {
      return { anbieter: r.anbieter, farbe: r.farbe, eigen: r.eigen,
               punkte: fassen(r.roh, raster) };
    }).filter(function (r) { return r.punkte.length; });

    bild.innerHTML = '';
    legende.innerHTML = '';
    tabelle.innerHTML = '';
    if (zukurz) { zukurz.hidden = true; zukurz.textContent = ''; }
    if (!reihen.length) {
      leer.hidden = false;
      leer.textContent = 'Für diesen Zeitraum liegen keine Messpunkte vor.';
      bild.hidden = true; legende.hidden = true; tabelle.hidden = true;
      kacheln.hidden = true;
      // Sonst behaelt der Satz die Zahlen des letzten Zustands, waehrend
      // daneben steht, dass es keine Messpunkte gibt.
      satzFuer(null, null, 0);
      return;
    }
    leer.hidden = true;
    tabelle.hidden = false;
    kacheln.hidden = false;

    var alle = [], tage = {};
    reihen.forEach(function (r) {
      r.punkte.forEach(function (p) { alle.push(p.preis); tage[p.datum] = 1; });
    });
    var tageSort = Object.keys(tage).sort();
    var lo = Math.min.apply(null, alle), hi = Math.max.apply(null, alle);

    /* DIE KACHELN UND DER SATZ GEHOEREN NICHT ZUM DIAGRAMM.

       Sie stehen deshalb hier, vor dem Gatter darunter: auch ein Geraet mit
       zwei Messterminen hat einen niedrigsten und einen hoechsten Preis,
       und die Zahl seiner Termine ist gerade dann die wichtigste Auskunft
       der Seite. */
    document.getElementById('gr-vmin').textContent = euro(lo);
    document.getElementById('gr-vmax').textContent = euro(hi);
    document.getElementById('gr-vanb').textContent = reihen.length;
    /* MESSTERMINE, nicht Preispunkte - dieselbe Menge, die das Gatter zaehlt
       und die der Satz darunter nennt. Vorher stand hier `alle.length`
       (Preispunkte ueber alle Anbieter) unter der Ueberschrift
       "Messpunkte", waehrend zwei Zeilen tiefer eine andere Zahl unter
       "Messtermine" stand. */
    document.getElementById('gr-vpkt').textContent = rohTage.length;
    satzFuer(g, rohTage, tageSort.length);

    /* GATTER: unter AB_TERMINEN Messterminen KEIN Diagramm.

       Zwei Punkte ergeben eine Gerade, und eine Gerade durch zwei Punkte
       sieht aus wie ein Trend. Die Tabelle darunter sagt dasselbe ohne die
       Behauptung, und der Satz sagt, ab wann ein Verlauf entsteht. Ein
       leeres Bild mit Rasterlinien und Legende ist keine ehrlichere
       Darstellung derselben Lage - es ist eine unehrlichere.

       GEZAEHLT WIRD BEIDES: die Messtage (`rohTage`) UND die Punkte, die
       nach der Rasterung wirklich gezeichnet werden (`tageSort`). Der
       erste Anlauf zaehlte nur die Messtage - und damit hob der
       Rasterschalter das Gatter aus: vier Messtage im Monatsraster sind EIN
       Zeitfenster, jede Reihe hat dann genau einen Punkt, und `<path>` wird
       fuer eine Reihe mit einem Punkt gar nicht gezeichnet. Im echten
       Chromium gemessen stand dort ein "Preisverlauf" mit null Linien und
       zwei Punkten in der Bildmitte - genau das, wogegen dieses Gatter
       gebaut ist, nur eine Stufe spaeter.

       Die ZAHL im Satz bleibt die der Messtage: das Raster formt die Linie,
       nicht die Datenlage. Nur ob ueberhaupt gezeichnet wird, haengt auch
       daran, ob nach der Rasterung noch eine Linie uebrig ist. */
    if (rohTage.length < AB_TERMINEN || tageSort.length < AB_TERMINEN) {
      bild.hidden = true; legende.hidden = true;
      if (zukurz) {
        zukurz.hidden = false;
        zukurz.textContent = punkt('Für dieses Gerät ' +
          termine(rohTage.length) + ' vor, ' + spanne(rohTage)) +
          (rohTage.length >= AB_TERMINEN
            ? ' In diesem Raster fallen sie auf ' + tageSort.length +
              ' Punkt' + (tageSort.length === 1 ? '' : 'e') +
              ' zusammen – für einen Verlauf braucht es ' + AB_TERMINEN +
              '. Ein feineres Raster zeigt mehr.'
            : ' Ein Verlauf entsteht ab ' + AB_TERMINEN + '.') +
          ' Bis dahin stehen die Preise als Tabelle darunter.';
      }
      tabelleBauen(reihen);
      return;
    }
    bild.hidden = false; legende.hidden = false;
    // EINE SPANNE VON NULL ist der Normalfall, nicht der Sonderfall: 41 der
    // 89 waehlbaren Geraete haben genau einen Preis. Die erste Fassung schob
    // dafuer `hi` auf `lo + 1` - und beschriftete die vier Hilfslinien aus
    // dem verschobenen Wert. Bei einem einzigen Preis von 999,00 EUR stand
    // dann dreimal "1000 EUR" an der Achse, ein Preis, den es im Datensatz
    // nicht gibt. Auf einer Seite, deren Leitsatz "geschaetzte Preise gibt
    // es hier nicht" lautet, ist das die teuerste Sorte falscher Zahl.
    //
    // Jetzt traegt die Achse in diesem Fall EINE Linie mit dem echten Preis,
    // und die Kurve laeuft auf halber Hoehe. `flach` ist ein eigenes Flag -
    // `hi === lo + 1` als Erkennungsmerkmal traf jede echte Spanne von genau
    // einem Euro.
    var flach = (hi === lo);
    var innenH = HOEHE - RAND.oben - RAND.unten;

    function y(preis) {
      if (flach) return RAND.oben + innenH / 2;
      return RAND.oben + innenH - ((preis - lo) / (hi - lo)) * innenH;
    }

    /* VERDECKTE LINIEN ERKENNEN - VOR der Breitenrechnung.

       `y()` haengt nur an lo/hi und der Hoehe, nicht an der Breite; die
       Erkennung kann deshalb hier stehen und entscheiden, wie viel Platz
       der rechte Rand fuer die Endpunkt-Etiketten braucht. Andersherum
       stuenden die Etiketten ausserhalb des viewBox und waeren unsichtbar -
       ein Etikett, das den Rand nicht bekommt, den es braucht, ist keine
       Loesung fuer eine unsichtbare Linie.

       Am Pixel 10 Pro gemessen: Vodafone 1099,90 EUR, mobilcom-debitel
       1099,00 EUR, Achse von 793 bis 1100 EUR. Neunzig Cent sind auf dieser
       Hoehe weniger als ein Pixel - die Vodafone-Linie stand in der Legende
       und war im Bild nicht da.

       VERSCHOBEN WIRD NICHTS. Die Y-Achse gehoert dem Preis; das ist die
       Lehre aus der geloeschten Positionskarte, deren Etiketten bis zu
       235 px neben ihrem Punkt standen, weil sie einander ausgewichen sind.
       Die verdeckte Linie bekommt eine eigene Strichart und ein Etikett an
       ihrem Ende, beides auf ihrer wahren Hoehe.

       Verglichen wird ueber die GEMEINSAMEN Tage. Zwei Reihen ohne einen
       gemeinsamen Tag koennen einander nicht verdecken - ohne diese
       Bedingung galt ein Anbieter mit einem einzigen Punkt als verdeckt von
       jedem, dessen Kurve zufaellig auf gleicher Hoehe endete. */
    var GRENZE = ABSTAND * innenH;
    var gelegt = [];
    reihen.forEach(function (r) {
      var meine = {};
      r.punkte.forEach(function (p) { meine[p.datum] = y(p.preis); });
      var verdeckt = null;
      for (var i = 0; i < gelegt.length && !verdeckt; i++) {
        var gemeinsam = 0, weit = 0;
        for (var d in meine) {
          if (gelegt[i].ys[d] === undefined) continue;
          gemeinsam++;
          if (Math.abs(meine[d] - gelegt[i].ys[d]) > GRENZE) weit++;
        }
        if (gemeinsam && !weit) verdeckt = gelegt[i].anbieter;
      }
      gelegt.push({ anbieter: r.anbieter, ys: meine });
      r.verdeckt = verdeckt;
    });

    /* Nur wenn wirklich ein Etikett gesetzt wird, kostet es Zeichenflaeche.
       Sonst bleibt die Kurve so breit wie bisher. */
    var mitEtikett = reihen.some(function (r) { return r.verdeckt; });
    var randRechts = mitEtikett ? 210 : RAND.rechts;
    var innenB = BREITE - RAND.links - randRechts;

    // ZEITPROPORTIONAL, nicht ordinal. Die erste Fassung bildete auf
    // `tageSort.indexOf(datum)` ab: bei Messungen am 10.8., 21.8. und 29.8.
    // (Abstaende 11 und 8 Tage) standen die drei Marken gleich weit
    // auseinander, und die Steigung der Kurve war frei erfunden. Dieselbe
    // Fehlerklasse wie die 235-px-Etiketten der geloeschten Grafik, nur auf
    // der anderen Achse.
    var t0 = tagNr(tageSort[0]);
    var t1 = tagNr(tageSort[tageSort.length - 1]);
    function x(datum) {
      if (t1 === t0) return RAND.links + innenB / 2;
      return RAND.links + ((tagNr(datum) - t0) / (t1 - t0)) * innenB;
    }
    var svg = el('svg', {
      viewBox: '0 0 ' + BREITE + ' ' + HOEHE, class: 'gr-vsvg',
      role: 'img', 'aria-label': 'Preisverlauf ' + g.label
    });

    // Waagerechte Hilfslinien und die Preisachse: vier Stufen reichen, um
    // eine Hoehe abzulesen, und halten die Flaeche ruhig.
    var stufen = flach ? [lo]
                       : [0, 1, 2, 3, 4].map(function (i) {
                           return lo + (hi - lo) * (i / 4);
                         });

    /* KEINE ZWEI ACHSENMARKEN MIT DEMSELBEN TEXT.

       `Math.round` reicht, solange die Spanne mehrere Euro breit ist. Bei
       drei Anbietern zwischen 900,00 und 900,20 EUR stand die Achse
       fuenfmal mit "900 €" da - fuenf Hilfslinien, die behaupten, fuenf
       verschiedene Hoehen zu benennen. Das ist dieselbe Fehlerklasse wie
       die drei "1000 €" bei einem Preis von 999,00: eine Achse, der man
       nicht glauben kann.

       Erst wird auf ganze Euro gerundet; sind zwei Marken dann gleich,
       traegt die ganze Achse zwei Nachkommastellen. Bleiben sie auch dann
       gleich, sind es wirklich dieselben Preise, und die doppelte Linie
       faellt weg. Gerundet wird NUR die Beschriftung - die Linie sitzt auf
       dem gerechneten Wert. */
    /* DEUTSCHE SCHREIBWEISE, MIT TAUSENDERTRENNER - wie ueberall sonst auf
       dieser Seite.

       Der erste Anlauf schrieb "1099 €" ohne Trenner, und die Begruendung
       im Kommentar war, dass `test_die_achse_erfindet_keinen_preis` die
       Marken mit `parseFloat` liest und an "1.099" scheitert. Das ist die
       falsche Richtung: damit war die SEITE an einen schwachen Testparser
       angepasst, und die Achse schrieb 1099, waehrend Tooltip, Legende,
       Kacheln und Tabelle desselben Diagramms 1.099,00 schreiben. Der Test
       liest jetzt richtig; die Achse schreibt, was das Portal schreibt. */
    function achsentext(preis, stellen) {
      return preis.toLocaleString('de-DE', { minimumFractionDigits: stellen,
                                             maximumFractionDigits: stellen })
             + ' €';
    }
    var stellen = 0;
    var grob = stufen.map(function (p) { return achsentext(p, 0); });
    if (grob.length !== grob.filter(function (t, i) {
          return grob.indexOf(t) === i; }).length) {
      stellen = 2;
    }
    var gesetzt = {};
    stufen.forEach(function (preis) {
      var text = achsentext(preis, stellen);
      if (gesetzt[text]) return;
      gesetzt[text] = 1;
      var yy = y(preis);
      svg.appendChild(el('line', { x1: RAND.links, x2: RAND.links + innenB,
                                   y1: yy, y2: yy, class: 'gr-vraster' }));
      svg.appendChild(el('text', { x: RAND.links - 10, y: yy + 4,
                                   class: 'gr-vachse', 'text-anchor': 'end' },
                         text));
    });

    // Datumsachse - waagerecht, hoechstens acht Marken.
    var marken = beschriftung(tageSort);
    var gesehen = {};
    marken.forEach(function (t) {
      var text = markeDE(t, raster);
      // Im Monats- und Quartalsraster koennen zwei Tage dieselbe Marke
      // ergeben. Zweimal "Q3 2026" nebeneinander ist keine Achse.
      if (gesehen[text]) return;
      gesehen[text] = 1;
      svg.appendChild(el('text', { x: x(t), y: HOEHE - RAND.unten + 22,
                                   class: 'gr-vachse', 'text-anchor': 'middle' },
                         text));
    });

    reihen.forEach(function (r) {
      var d = r.punkte.map(function (p, i) {
        return (i ? 'L' : 'M') + x(p.datum).toFixed(1) + ' ' + y(p.preis).toFixed(1);
      }).join(' ');
      if (r.punkte.length > 1) {
        var attrs = { d: d, fill: 'none', stroke: r.farbe,
                      'stroke-width': r.eigen ? 3 : 2, class: 'gr-vlinie' };
        if (r.verdeckt) {
          /* MEHR LUECKE ALS STRICH. Mit "7 5" deckte die obenliegende Linie
             immer noch 58 Prozent der Laenge ab; am Pixelbild gemessen
             blieben von der verdeckten Linie darunter 197 von 1400 Pixeln
             uebrig, und die eigene (3 px) ueberdeckte die fremde (2 px)
             vollstaendig. Mit "4 8" liegt zwei Dritteln der Strecke die
             untere Linie frei - beide sind zu sehen, und keine ist
             verschoben. */
          attrs['stroke-dasharray'] = '4 8';
          attrs.class = 'gr-vlinie gr-vlinie--verdeckt';
        }
        svg.appendChild(el('path', attrs));
      }
      r.punkte.forEach(function (p) {
        /* Der Punkt der obenliegenden Linie wird ein RING, wenn er auf einem
           fremden Punkt sitzt: gefuellt verdeckte er ihn ganz, und an den
           Messpunkten - genau dort, wo man den Preis abliest - saehe man nur
           einen Anbieter. Der Ring steht auf derselben Hoehe wie der Punkt
           darunter; verschoben wird auch hier nichts. */
        var k = el('circle', {
          cx: x(p.datum), cy: y(p.preis), r: r.eigen ? 5 : 4,
          fill: r.verdeckt ? 'none' : r.farbe,
          stroke: r.verdeckt ? r.farbe : null,
          class: r.verdeckt ? 'gr-vpunkt gr-vpunkt--ring' : 'gr-vpunkt' });
        k.appendChild(el('title', {}, r.anbieter + ': ' + euro(p.preis) +
                                      ' am ' + tagDE(p.datum)));
        svg.appendChild(k);
      });
      /* Das Endpunkt-Etikett bekommt NUR die verdeckte Linie. An jeder Linie
         waere es die Legende ein zweites Mal, und der rechte Rand reicht fuer
         zwei Namen nebeneinander nicht. */
      if (r.verdeckt) {
        var letzt = r.punkte[r.punkte.length - 1];
        svg.appendChild(el('text', {
          x: Math.min(x(letzt.datum) + 9, BREITE - 6), y: y(letzt.preis) + 4,
          class: 'gr-vetikett', fill: r.farbe, 'text-anchor': 'start'
        }, r.anbieter + ' ' + euro(letzt.preis)));
      }
    });
    bild.appendChild(svg);

    reihen.forEach(function (r) {
      var s = document.createElement('span');
      s.className = 'gr-vlegende-teil';
      var punkt = document.createElement('span');
      punkt.className = 'gr-vlegende-punkt';
      punkt.style.background = r.farbe;
      s.appendChild(punkt);
      s.appendChild(document.createTextNode(r.anbieter));
      legende.appendChild(s);
    });

    tabelleBauen(reihen);
  }

  /* Die Tabelle unter dem Diagramm - und OHNE Diagramm die ganze Antwort.

     Sie steht als eigene Funktion, seit das Gatter darueber sie auch dann
     braucht, wenn kein Bild gezeichnet wird. Zwei Kopien dieser Rechnung
     waeren zwei Meinungen darueber, was "aktueller Preis" heisst. */
  function tabelleBauen(reihen) {
    var t = document.createElement('table');
    t.className = 'src-table gr-tabelle';
    var tb = document.createElement('tbody');
    // AUS DEN GEFILTERTEN REIHEN, nicht aus der vorgerechneten Liste.
    // `g.aktuell` rechnet ueber den vollen Zeitraum; mit einem Von-Datum vom
    // 29.08. nannte die Tabelle einen Anbieter, der im Diagramm daneben gar
    // nicht vorkam, mit einem Datum ausserhalb des gewaehlten Fensters.
    // Zwei Zahlen fuer dieselbe Sache auf einem Bildschirm.
    var zeilen = reihen.map(function (r) {
      var ps = r.punkte;
      var letzt = ps[ps.length - 1];
      var aend = null;
      if (ps.length > 1 && ps[0].preis !== letzt.preis) {
        aend = Math.round((letzt.preis - ps[0].preis) * 100) / 100;
      }
      return { anbieter: r.anbieter, eigen: r.eigen, preis: letzt.preis,
               stand: letzt.datum, veraenderung: aend };
    }).sort(function (a, b) { return a.preis - b.preis; });

    /* EINE SPALTE AUS LAUTER STRICHEN IST KEINE SPALTE.

       "Veraenderung" bleibt leer, solange ein Anbieter nur einen Messpunkt
       hat oder sein Preis sich nicht bewegt hat - beides ist richtig so
       ("-0,00 EUR" waere keine Auskunft). Am Galaxy S25 standen damit drei
       Zeilen mit drei Gedankenstrichen untereinander, und eine Spalte, in
       der nichts steht, liest sich als kaputte Seite und nicht als ruhiger
       Markt. Sie erscheint deshalb nur, wenn wenigstens EIN Wert darin
       steht - dieselbe Regel, mit der "niemand guenstiger" aus der
       Alarmtabelle geflogen ist. */
    var mitAenderung = zeilen.some(function (z) {
      return z.veraenderung !== null;
    });
    t.innerHTML = '<thead><tr><th scope="col">Anbieter</th>' +
      '<th scope="col" class="num">aktueller Preis</th>' +
      (mitAenderung ? '<th scope="col" class="num">Veränderung</th>' : '') +
      '<th scope="col">zuletzt aktualisiert</th></tr></thead>';

    zeilen.forEach(function (z) {
      var tr = document.createElement('tr');
      var d = z.veraenderung === null ? '–'
            : (z.veraenderung > 0 ? '+' : '') + euro(z.veraenderung);
      // `textContent` statt `innerHTML`: der Anbietername ist ein DATENWERT.
      // `_quellenlage` kennt ausdruecklich Anbieter, die nur in der
      // Datenbank stehen und nicht in der Konfiguration - Legende und
      // Trefferliste setzen ihn laengst als Text.
      var werte = mitAenderung
        ? [z.anbieter, euro(z.preis), d, markeDE(z.stand, raster)]
        : [z.anbieter, euro(z.preis), markeDE(z.stand, raster)];
      werte.forEach(function (wert, i) {
        var td = tr.insertCell(-1);
        if (i === 1 || (mitAenderung && i === 2)) td.className = 'num';
        td.textContent = wert;
      });
      if (z.eigen) tr.className = 'gr-veigen';
      tb.appendChild(tr);
    });
    t.appendChild(tb);
    tabelle.appendChild(t);
  }

  function waehle(g) {
    gewaehlt = g;
    feld.value = g.label;
    treffer.hidden = true;
    feld.setAttribute('aria-expanded', 'false');
    steuer.hidden = false;
    zeichne(g);
  }

  feld.addEventListener('input', function () {
    var q = feld.value.trim().toLowerCase();
    treffer.innerHTML = '';
    // Sobald der Leser weitertippt, gilt die alte Auswahl nicht mehr. Ohne
    // diesen Rueckbau stand unter dem Suchwort "zzzz" unveraendert der
    // Verlauf des zuletzt gewaehlten Geraets.
    if (gewaehlt && feld.value !== gewaehlt.label) {
      gewaehlt = null;
      steuer.hidden = true; kacheln.hidden = true;
      bild.hidden = true; legende.hidden = true; tabelle.hidden = true;
      bild.innerHTML = ''; legende.innerHTML = ''; tabelle.innerHTML = '';
      leer.hidden = false;
      leer.textContent = 'Wählen Sie oben ein Gerät – dann steht hier sein '
        + 'Preisverlauf, mit einer Linie je Anbieter.';
      // AUCH DIE ZWEI SAETZE. Ohne das stand unter "Wählen Sie oben ein
      // Gerät" weiter "Für dieses Gerät liegen 2 Messtermine vor, vom 3.8.
      // bis zum 4.8." - ein Satz ueber ein Geraet, das nicht mehr gewaehlt
      // ist -, und die globale Zahl war von der Seite verschwunden, weil
      // `satzFuer` sie beim Gattern ausgeblendet hatte.
      if (zukurz) { zukurz.hidden = true; zukurz.textContent = ''; }
      satzFuer(null, null, 0);
    }
    if (q.length < 2) {
      treffer.hidden = true;
      feld.setAttribute('aria-expanded', 'false');
      return;
    }
    var gefunden = GERAETE.filter(function (g) {
      return g.suchtext.indexOf(q) !== -1;
    }).slice(0, 8);
    gefunden.forEach(function (g) {
      var li = document.createElement('li');
      li.className = 'gr-vtreffer-zeile';
      li.setAttribute('role', 'option');
      li.tabIndex = 0;
      li.textContent = g.label + ' · ' + g.anbieter +
        (g.anbieter === 1 ? ' Anbieter' : ' Anbieter');
      li.addEventListener('click', function () { waehle(g); });
      li.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); waehle(g); }
      });
      treffer.appendChild(li);
    });
    treffer.hidden = !gefunden.length;
    feld.setAttribute('aria-expanded', gefunden.length ? 'true' : 'false');
  });

  Array.prototype.forEach.call(
    document.querySelectorAll('.gr-vknopf'), function (k) {
      k.addEventListener('click', function () {
        Array.prototype.forEach.call(document.querySelectorAll('.gr-vknopf'),
          function (a) { a.classList.remove('is-aktiv'); });
        k.classList.add('is-aktiv');
        raster = k.getAttribute('data-raster');
        if (gewaehlt) zeichne(gewaehlt);
      });
    });
  [von, bis].forEach(function (d) {
    if (d) d.addEventListener('change', function () {
      if (gewaehlt) zeichne(gewaehlt);
    });
  });
})();
