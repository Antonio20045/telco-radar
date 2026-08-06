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

  // Ankunft ueber die globale Suche (Topbar) mit ?q=…: Suchfeld vorbelegen,
  // Explorer-Akkordeon oeffnen und sofort filtern - kein zweites Mal tippen.
  //
  // Nur auf Seiten OHNE eigenes Suchfeld (also den Archivwochen unter
  // reports/). Auf meldungen.html uebernimmt die Volltextsuche das ?q=; wuerde
  // der Explorer es zusaetzlich als Wochenfilter lesen, staende ueber einer
  // Trefferliste mit zwoelf Ergebnissen ein leerer Wochen-Explorer - derselbe
  // Begriff, zwei widersprechende Zahlen.
  try {
    var qs = new URLSearchParams(location.search);
    var q = document.getElementById('suche-input') ? null : qs.get('q');
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

/* Gemeinsame Matching-/Snippet-Logik der globalen Suche: durchsucht
   search_index.json - Bericht-Highlights ALLER Wochen PLUS die persistente
   Differenzierungs-Bibliothek, nicht nur die aktuelle Seite. Reines
   Substring-Matching (kein Fuzzy/Scoring), siehe
   claude/suche-marktrecherche-konzept.md. Frueher lebte diese Logik in der
   Topbar-Dropdown-IIFE; seit dem Ausbau (claude/suche-ergebnisseite-
   konzept.md) navigiert die Topbar per nativem <form> direkt zu suche.html,
   das dieselben Funktionen hier nutzt statt sie zu duplizieren. */
var TelcoSearch = (function () {
  'use strict';

  var KIND_LABEL = { bericht: 'Bericht', differenzierung: 'Differenzierung' };
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

  function haystack(it) {
    return [it.title, it.summary, it.operator, it.region, it.category, it.source_label]
      .filter(Boolean).join(' — ').toLowerCase();
  }

  function snippet(it, q) {
    var text = [it.title, it.summary].filter(Boolean).join(' — ');
    var lower = text.toLowerCase();
    var idx = lower.indexOf(q);
    if (idx === -1) {
      return esc(text.slice(0, 150)) + (text.length > 150 ? '…' : '');
    }
    var start = Math.max(0, idx - 55);
    var end = Math.min(text.length, idx + q.length + 85);
    return (start > 0 ? '…' : '') +
      esc(text.slice(start, idx)) +
      '<mark>' + esc(text.slice(idx, idx + q.length)) + '</mark>' +
      esc(text.slice(idx + q.length, end)) +
      (end < text.length ? '…' : '');
  }

  // Deep-Link zum vollen Kontext: Bericht-Treffer haengen ?q= an, damit der
  // Explorer der jeweiligen Woche sofort gefiltert oeffnet (siehe die
  // Explorer-IIFE weiter oben in dieser Datei); Differenzierungs-Treffer
  // springen direkt zum Thema - dort gibt es keinen Suchbegriff-Filter.
  function deepLinkHref(it, q) {
    var p = prefix();
    if (it.kind === 'bericht' && q) {
      return p + it.deep_link + '?q=' + encodeURIComponent(q);
    }
    return p + it.deep_link;
  }

  return {
    KIND_LABEL: KIND_LABEL, esc: esc, prefix: prefix, loadIndex: loadIndex,
    haystack: haystack, snippet: snippet, deepLinkHref: deepLinkHref
  };
})();

/* Suche-Ergebnisseite (suche.html): alle Treffer zu einem Begriff an einem
   Ort statt im 8er-gedeckelten Topbar-Dropdown - bookmarkbar/teilbar ueber
   ?q=<begriff>. Siehe claude/suche-ergebnisseite-konzept.md. */
(function () {
  'use strict';
  var input = document.getElementById('suche-input');
  var resultsEl = document.getElementById('suche-results');
  var countEl = document.getElementById('suche-count');
  var chips = document.querySelectorAll('.suche-filter');
  if (!input || !resultsEl) return;

  var kind = 'all';
  var t;

  function syncUrl(q) {
    try {
      var url = new URL(location.href);
      if (q) url.searchParams.set('q', q); else url.searchParams.delete('q');
      history.replaceState(null, '', url.pathname + url.search + url.hash);
    } catch (e) { /* URL() nicht verfuegbar - stiller Fallback, Seite bleibt nutzbar */ }
  }

  function renderHits(hits, q) {
    if (!q) {
      resultsEl.innerHTML = '<p class="empty-note">Suchbegriff eingeben, um alle Berichte und die ' +
        'Differenzierungs-Bibliothek zu durchsuchen.</p>';
      countEl.textContent = '';
      return;
    }
    if (!hits.length) {
      resultsEl.innerHTML = '<p class="empty-note">Keine Treffer für „' + TelcoSearch.esc(q) + '“.</p>';
      countEl.textContent = '0 Treffer';
      return;
    }
    resultsEl.innerHTML = hits.map(function (it) {
      var meta = [it.operator, it.region, it.date].filter(Boolean).join(' · ');
      var ctxLabel = it.kind === 'bericht' ? 'Im Wochenbericht ansehen' : 'Im Differenzierungs-Thema ansehen';
      return '<article class="suche-card">' +
        '<div class="gs-item-top">' +
          '<span class="gs-kind ' + TelcoSearch.esc(it.kind) + '">' +
            TelcoSearch.esc(TelcoSearch.KIND_LABEL[it.kind] || it.kind) + '</span>' +
          '<span class="gs-item-meta">' + TelcoSearch.esc(meta) + '</span>' +
        '</div>' +
        '<p class="gs-item-title">' + TelcoSearch.esc(it.title) + '</p>' +
        '<p class="gs-item-snip">' + TelcoSearch.snippet(it, q) + '</p>' +
        '<div class="suche-card-links">' +
          '<a class="source-link" href="' + TelcoSearch.esc(it.url) + '" target="_blank" rel="noopener">' +
            'Originalquelle öffnen &nearr;</a>' +
          '<a class="suche-context-link" href="' + TelcoSearch.esc(TelcoSearch.deepLinkHref(it, q)) + '">' +
            ctxLabel + ' &rsaquo;</a>' +
        '</div>' +
      '</article>';
    }).join('');
    countEl.textContent = hits.length + ' Treffer für „' + TelcoSearch.esc(q) + '“';
  }

  function run() {
    var q = (input.value || '').trim().toLowerCase();
    syncUrl(q);
    if (!q) { renderHits([], ''); return; }
    TelcoSearch.loadIndex().then(function (all) {
      var hits = all.filter(function (it) { return TelcoSearch.haystack(it).indexOf(q) !== -1; });
      if (kind !== 'all') hits = hits.filter(function (it) { return it.kind === kind; });
      renderHits(hits, q);
      document.title = 'Suche: ' + q + ' – Vodafone Insights';
    });
  }

  input.addEventListener('input', function () { clearTimeout(t); t = setTimeout(run, 150); });
  chips.forEach(function (btn) {
    btn.addEventListener('click', function () {
      chips.forEach(function (b) { b.classList.remove('on'); });
      btn.classList.add('on');
      kind = btn.dataset.kind || 'all';
      run();
    });
  });

  try {
    var qs = new URLSearchParams(location.search);
    var q0 = qs.get('q');
    if (q0) input.value = q0;
  } catch (e) { /* URLSearchParams nicht verfuegbar - stiller Fallback */ }
  run();
})();


/* Meldungsliste (meldungen.html): filtert die serverseitig gerenderten
   Meldungen. Bewusst KEIN Explorer mit Split-View - die Seite soll gelesen
   werden koennen wie eine Zeitungsseite, nicht bedient wie ein Werkzeug. */
(function () {
  'use strict';
  var input = document.getElementById('meldung-filter');
  var liste = document.getElementById('meldungs-liste');
  var zahl = document.getElementById('meldung-zahl');
  var leer = document.getElementById('meldung-leer');
  if (!input || !liste) return;

  var zeilen = Array.prototype.slice.call(liste.querySelectorAll('.meldung'));
  var t;

  function filtern() {
    var q = (input.value || '').trim().toLowerCase();
    var sichtbar = 0;
    zeilen.forEach(function (z) {
      var treffer = !q || (z.dataset.such || '').indexOf(q) !== -1;
      z.hidden = !treffer;
      if (treffer) sichtbar++;
    });
    if (zahl) {
      zahl.textContent = q ? sichtbar + ' von ' + zeilen.length + ' Meldungen'
                           : zeilen.length + ' Meldungen';
    }
    if (leer) leer.hidden = sichtbar !== 0;
  }

  input.addEventListener('input', function () {
    clearTimeout(t); t = setTimeout(filtern, 110);
  });

  // Ankunft ueber die Topbar-Suche mit ?q=: direkt vorfiltern.
  try {
    var q0 = new URLSearchParams(location.search).get('q');
    if (q0) { input.value = q0; filtern(); }
  } catch (e) { /* stiller Fallback */ }
})();
