/* Telco Radar - Explorer (Vanilla JS, kein Framework) */
(function () {
  'use strict';

  const dataEl = document.getElementById('explorer-data');
  if (!dataEl) return;
  let items = [];
  try { items = JSON.parse(dataEl.textContent); } catch (e) { return; }

  const listEl = document.getElementById('ex-list');
  const detailEl = document.getElementById('ex-detail');
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
      '<a class="source-link" href="' + esc(h.url) + '" target="_blank" rel="noopener">Originalquelle öffnen (' + esc(h.source_label || 'Link') + ') &nearr;</a>';
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
 * Geraeteradar: Ansichtsumschalter, Filter, Detailzeile.
 *
 * Beide Ansichten der Positionskarte stehen fertig im HTML - hier wird nur
 * umgeblendet, nichts nachgeladen und nichts neu gerechnet. Genauso die
 * Filter: sie BLENDEN Punkte aus, sie verschieben keine. Das ist Absicht,
 * denn eine Achse, die sich beim Filtern verschiebt, macht zwei Ansichten
 * unvergleichbar - und die Entzerrung der Etiketten kommt aus Python.
 *
 * Auf dem Telefon gibt es kein Hover. Deshalb reagiert jeder Punkt auf Tap
 * und auf Tastatur, und die Einzelheiten stehen in einer Zeile unter der
 * Grafik statt in einer Sprechblase.
 * ---------------------------------------------------------------------- */
(function () {
  var karte = document.getElementById('positionskarte');
  if (!karte) return;

  var knoepfe = karte.querySelectorAll('.gr-knopf');
  var ansichten = karte.querySelectorAll('.gr-ansicht');
  var flaechen = karte.querySelectorAll('.gr-flaeche');
  var detail = document.getElementById('gr-detail');
  var legende = document.getElementById('gr-legende');
  // Der feste Teil der Legende. Der Satz "Ohne Etikett bleiben N Punkte"
  // gilt je FLAECHE und wird unten nachgezogen - stuende er hier mit drin,
  // haenge er beim ersten Umschalten ein zweites Mal daran.
  var legendeRoh = legende
    ? legende.textContent.split('Ohne Etikett bleiben')[0].replace(/\s+$/, '')
    : '';
  var felder = {
    segment: document.getElementById('gr-segment'),
    speicher: document.getElementById('gr-speicher'),
    generation: document.getElementById('gr-generation')
  };

  // Der Zustand ist ein Woerterbuch, kein Sonderfall je Knopf. Ein Knopf
  // sagt ueber `data-schalter`, WELCHE Achse er stellt, und ueber
  // `data-wert`, worauf. Der dritte Schalter ("ohne Vertrag / mit Vertrag")
  // braucht damit keine Zeile JavaScript mehr, nur ein weiteres Attribut.
  var zustand = {ansicht: '', form: ''};
  for (var a = 0; a < ansichten.length; a++) {
    if (ansichten[a].className.indexOf('gr-ansicht--aus') < 0) {
      zustand.ansicht = ansichten[a].getAttribute('data-ansicht');
      break;
    }
  }
  for (var f = 0; f < flaechen.length; f++) {
    if (flaechen[f].className.indexOf('gr-flaeche--aus') < 0) {
      zustand.form = flaechen[f].getAttribute('data-form');
      break;
    }
  }

  function aktiveAnsicht() {
    for (var i = 0; i < ansichten.length; i++) {
      if (ansichten[i].getAttribute('data-ansicht') === zustand.ansicht) return ansichten[i];
    }
    return ansichten[0];
  }

  function blenden() {
    for (var i = 0; i < ansichten.length; i++) {
      ansichten[i].classList.toggle('gr-ansicht--aus',
        ansichten[i].getAttribute('data-ansicht') !== zustand.ansicht);
    }
    for (var j = 0; j < flaechen.length; j++) {
      flaechen[j].classList.toggle('gr-flaeche--aus',
        flaechen[j].getAttribute('data-form') !== zustand.form);
    }
    for (var k = 0; k < knoepfe.length; k++) {
      var achse = knoepfe[k].getAttribute('data-schalter');
      knoepfe[k].classList.toggle('on',
        zustand[achse] === knoepfe[k].getAttribute('data-wert'));
    }
  }

  function leereDetail() {
    // Sonst nennt die Zeile weiter Preis und Anbieter eines Geraets, das
    // gerade ausgeblendet wurde oder in der anderen Ansicht steht.
    if (detail) detail.textContent = '';
  }

  function aktiveFlaeche() {
    return aktiveAnsicht()
      ? aktiveAnsicht().querySelector('.gr-flaeche[data-form="' + zustand.form + '"]')
      : null;
  }

  function filtern() {
    leereDetail();
    var seg = felder.segment ? felder.segment.value : '';
    var sp = felder.speicher ? felder.speicher.value : '';
    var gen = felder.generation ? felder.generation.value : '';
    var sichtbar = 0;
    var flaeche = aktiveFlaeche();
    var alle = karte.querySelectorAll('.gr-punkt');
    for (var i = 0; i < alle.length; i++) {
      var p = alle[i];
      var passt = (!seg || p.getAttribute('data-segment') === seg)
        && (!sp || p.getAttribute('data-speicher') === sp)
        && (!gen || p.getAttribute('data-aktuell') === '1');
      p.classList.toggle('gr-punkt--aus', !passt);
      if (passt && flaeche && p.closest('.gr-flaeche') === flaeche) sichtbar++;
    }
    // Ein Preisband ohne sichtbaren Punkt zeigt eine Spanne, die es gerade
    // nicht mehr gibt. Es verschwindet mit seinen Punkten.
    var baender = karte.querySelectorAll('.gr-band');
    for (var b = 0; b < baender.length; b++) {
      var schluessel = baender[b].getAttribute('data-band');
      var eigene = baender[b].closest('.gr-flaeche')
        .querySelectorAll('.gr-punkt[data-band="' + schluessel + '"]');
      var offen = false;
      for (var e = 0; e < eigene.length; e++) {
        if (eigene[e].className.baseVal.indexOf('gr-punkt--aus') < 0) offen = true;
      }
      baender[b].classList.toggle('gr-band--aus', !offen);
    }
    if (legende && flaeche) {
      // ALLE Zahlen kommen aus der SICHTBAREN Flaeche. Vorher standen hier
      // drei verschiedene Gesamtzahlen: eine aus der Vorlage (alle Punkte),
      // eine gerechnete (Punkte durch Flaechen) und die der jeweils anderen
      // Darstellungsform - keine davon galt fuer das Bild, das man ansah.
      var gesamt = flaeche.getAttribute('data-punkte');
      var ohne = parseInt(flaeche.getAttribute('data-etiketten-verborgen') || '0', 10);
      var zusatz = ohne
        ? ' Ohne Etikett bleiben ' + ohne + ' Punkte – dort ist die Spalte voll;'
          + ' der Punkt steht auf seinem Preis.'
        : '';
      if (seg || sp || gen) {
        zusatz += ' Gefiltert: ' + sichtbar + ' von ' + gesamt + ' sichtbar.';
      }
      legende.textContent = legendeRoh + zusatz;
    }
  }

  for (var i = 0; i < knoepfe.length; i++) {
    knoepfe[i].addEventListener('click', function (ev) {
      var achse = ev.currentTarget.getAttribute('data-schalter');
      if (!achse) return;
      zustand[achse] = ev.currentTarget.getAttribute('data-wert');
      blenden();
      filtern();
    });
  }

  Object.keys(felder).forEach(function (name) {
    if (felder[name]) felder[name].addEventListener('change', filtern);
  });

  // Einmal beim Laden: die Baender der Startflaeche brauchen ihren Zustand,
  // und die Legende ihre Zahl.
  filtern();

  function zeige(el) {
    if (!detail) return;
    var teile = [el.getAttribute('data-modell')];
    if (el.getAttribute('data-speicher-text')) teile.push(el.getAttribute('data-speicher-text') + ' GB');
    // Die Farben stehen jetzt als ZAHL plus Liste da, weil ein Punkt seit
    // der Verdichtung alle Farben einer Speichergroesse vertritt. Genau
    // deshalb liegen keine fuenf Kreise mehr aufeinander.
    var farben = parseInt(el.getAttribute('data-farben') || '0', 10);
    var liste = el.getAttribute('data-farben-liste') || '';
    if (farben === 1 && liste) teile.push(liste);
    else if (farben > 1) teile.push(farben + ' Farben' + (liste ? ' (' + liste + ')' : ''));
    teile.push((el.getAttribute('data-preisart') === 'mit_vertrag' ? 'Zuzahlung ' : '')
      + el.getAttribute('data-preis') + ' €');
    teile.push('bei ' + el.getAttribute('data-anbieter'));
    if (el.getAttribute('data-stand')) teile.push('abgerufen ' + el.getAttribute('data-stand'));
    detail.textContent = teile.join(' · ') + ' ';
    var url = el.getAttribute('data-url');
    if (url) {
      var a = document.createElement('a');
      a.href = url;
      a.rel = 'noopener';
      a.textContent = 'Quelle';
      try { a.title = new URL(url).hostname.replace(/^www\./, ''); } catch (e) {}
      detail.appendChild(a);
    }
  }

  karte.addEventListener('click', function (ev) {
    var punkt = ev.target.closest ? ev.target.closest('.gr-punkt') : null;
    if (punkt) zeige(punkt);
  });
  karte.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Enter' && ev.key !== ' ') return;
    var punkt = ev.target.closest ? ev.target.closest('.gr-punkt') : null;
    if (punkt) { ev.preventDefault(); zeige(punkt); }
  });
})();

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
