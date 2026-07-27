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

/* Globale Suche (Topbar) - durchsucht search_index.json: alle Bericht-Wochen
   PLUS die persistente Differenzierungs-Bibliothek, nicht nur die aktuelle
   Seite. Reines Substring-Matching (kein Fuzzy/Scoring), siehe
   claude/suche-marktrecherche-konzept.md. */
(function () {
  'use strict';
  const input = document.getElementById('gsearch-input');
  const panel = document.getElementById('gsearch-results');
  if (!input || !panel) return;

  const MAX_SHOWN = 8;
  const KIND_LABEL = { bericht: 'Bericht', differenzierung: 'Differenzierung' };
  let items = null;   // null = noch nicht geladen; [] = geladen, leer
  let loading = null;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  // Der Praefix (z. B. "" auf der Startseite, "../" unter reports/ oder
  // promo/) steckt schon serverseitig im Brand-Link - so muss app.js (eine
  // einzige, seitenunabhaengige Datei) ihn nicht selbst erraten.
  function prefix() {
    const brand = document.querySelector('.topbar .brand');
    const href = brand ? brand.getAttribute('href') || '' : '';
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
    const text = [it.title, it.summary].filter(Boolean).join(' — ');
    const lower = text.toLowerCase();
    const idx = lower.indexOf(q);
    if (idx === -1) {
      return esc(text.slice(0, 150)) + (text.length > 150 ? '…' : '');
    }
    const start = Math.max(0, idx - 55);
    const end = Math.min(text.length, idx + q.length + 85);
    return (start > 0 ? '…' : '') +
      esc(text.slice(start, idx)) +
      '<mark>' + esc(text.slice(idx, idx + q.length)) + '</mark>' +
      esc(text.slice(idx + q.length, end)) +
      (end < text.length ? '…' : '');
  }

  function targetHref(it, q) {
    const p = prefix();
    if (it.kind === 'bericht') {
      return p + it.deep_link + '?q=' + encodeURIComponent(q);
    }
    return p + it.deep_link;
  }

  function render(hits, q) {
    if (!hits.length) {
      panel.innerHTML = '<p class="gs-empty">Keine Treffer für „' + esc(q) + '“.</p>';
      panel.hidden = false;
      return;
    }
    const shown = hits.slice(0, MAX_SHOWN);
    panel.innerHTML = shown.map(function (it) {
      const meta = [it.operator, it.region, it.date].filter(Boolean).join(' · ');
      return '<a class="gs-item" href="' + esc(targetHref(it, q)) + '">' +
        '<div class="gs-item-top">' +
          '<span class="gs-kind ' + esc(it.kind) + '">' + esc(KIND_LABEL[it.kind] || it.kind) + '</span>' +
          '<span class="gs-item-meta">' + esc(meta) + '</span>' +
        '</div>' +
        '<p class="gs-item-snip">' + snippet(it, q) + '</p>' +
        '</a>';
    }).join('') + (hits.length > MAX_SHOWN
      ? '<p class="gs-more">+' + (hits.length - MAX_SHOWN) + ' weitere Treffer – Suchbegriff eingrenzen</p>'
      : '');
    panel.hidden = false;
  }

  function search() {
    const q = input.value.trim().toLowerCase();
    if (!q) { panel.hidden = true; panel.innerHTML = ''; return; }
    loadIndex().then(function (all) {
      const hits = all.filter(function (it) { return haystack(it).indexOf(q) !== -1; });
      render(hits, q);
    });
  }

  let t;
  input.addEventListener('input', function () { clearTimeout(t); t = setTimeout(search, 150); });
  input.addEventListener('focus', function () { if (input.value.trim()) search(); });
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { panel.hidden = true; input.blur(); }
  });
  document.addEventListener('click', function (e) {
    if (!e.target.closest('#gsearch')) panel.hidden = true;
  });
})();
