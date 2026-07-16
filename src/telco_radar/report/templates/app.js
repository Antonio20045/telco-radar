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
      const hay = ((h.operator || '') + ' ' + (h.title || '') + ' ' + (h.summary || '') + ' ' + (h.why_it_matters || '') + ' ' + (h.source_label || '')).toLowerCase();
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
      (h.why_it_matters ? '<p class="why"><span class="why-label">Warum das zählt</span>' + esc(h.why_it_matters) + '</p>' : '') +
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
})();
