/* Telco Radar – Explorer, Filter, Theme, Ticker (kein Framework) */
(function () {
  'use strict';

  /* ---------- Theme toggle ---------- */
  const toggle = document.getElementById('theme-toggle');
  if (toggle) {
    toggle.addEventListener('click', function () {
      const root = document.documentElement;
      const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
      root.dataset.theme = next;
      try { localStorage.setItem('tr-theme', next); } catch (e) {}
    });
  }

  /* ---------- Ticker: duplicate track for seamless loop ---------- */
  const track = document.getElementById('ticker-track');
  if (track && track.children.length) {
    track.innerHTML += track.innerHTML;
  }

  /* ---------- Explorer ---------- */
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

  const REL_LABEL = { 5: 'Sofort ansehen', 4: 'Wichtig', 3: 'Beobachten', 2: 'Randnotiz', 1: 'Randnotiz', 0: 'Unbewertet' };
  let visible = [];
  let selectedId = null;

  function esc(s) {
    return String(s || '').replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function matches(h) {
    const q = (fSearch.value || '').trim().toLowerCase();
    if (q) {
      const hay = ((h.operator || '') + ' ' + (h.title || '') + ' ' + (h.summary || '') + ' ' + (h.why_it_matters || '')).toLowerCase();
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
      return '<div class="ex-row' + (h.id === selectedId ? ' selected' : '') + '" data-id="' + h.id + '" role="option" tabindex="0">' +
        '<span class="ex-row-rel r' + h.relevance + '">' + (h.relevance ? h.relevance + '/5' : '–') + '</span>' +
        '<span class="ex-row-title">' + esc(h.title) + '</span>' +
        '<span class="ex-row-meta">' + esc(h.operator || h.source_domain || '') + ' · ' + esc(h.region) + (h.date ? ' · ' + esc(h.date) : '') + '</span>' +
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
      row.classList.toggle('selected', parseInt(row.dataset.id, 10) === id);
    });
    detailEl.innerHTML =
      '<div class="ex-d-top">' +
        '<span class="rel-badge r' + h.relevance + '">' + (h.relevance ? h.relevance + '/5 · ' + (REL_LABEL[h.relevance] || '') : 'Unbewertet') + '</span>' +
        '<span class="chip">' + esc(h.category) + '</span>' +
        '<span class="chip">' + esc(h.region) + '</span>' +
      '</div>' +
      '<h3 class="ex-d-title"><a href="' + esc(h.url) + '" target="_blank" rel="noopener">' + esc(h.title) + '</a></h3>' +
      '<p class="ex-d-meta"><strong>' + esc(h.operator || '–') + '</strong>' +
        (h.date ? ' · ' + esc(h.date) : '') +
        (h.source ? ' · gefunden via ' + esc(h.source) : '') + '</p>' +
      (h.summary ? '<div class="ex-d-block"><h4>Was ist passiert?</h4><p>' + esc(h.summary) + '</p></div>' : '') +
      (h.why_it_matters ? '<div class="ex-d-block ex-d-why"><h4>Warum ist das für Vodafone interessant?</h4><p>' + esc(h.why_it_matters) + '</p></div>' : '') +
      '<a class="btn-source" href="' + esc(h.url) + '" target="_blank" rel="noopener">Originalquelle öffnen (' + esc(h.source_domain || 'Link') + ') ↗</a>';
    if (scroll) detailEl.scrollTop = 0;
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
  [fRegion, fCategory, fRelevance, fSort].forEach(function (el) {
    el.addEventListener('change', renderList);
  });

  renderList();
})();
