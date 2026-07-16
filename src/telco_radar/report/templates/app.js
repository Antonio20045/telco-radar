/* Telco Radar – client-side filtering & search (no dependencies) */
(function () {
  const cards = Array.from(document.querySelectorAll('#cards .card'));
  if (!cards.length) return;

  const search = document.getElementById('f-search');
  const region = document.getElementById('f-region');
  const category = document.getElementById('f-category');
  const relevance = document.getElementById('f-relevance');
  const counter = document.getElementById('signal-count');
  const empty = document.getElementById('empty-filter');

  function apply() {
    const q = (search.value || '').trim().toLowerCase();
    const r = region.value;
    const c = category.value;
    const minRel = parseInt(relevance.value || '0', 10);
    let visible = 0;

    for (const card of cards) {
      const okQ = !q || card.dataset.text.includes(q);
      const okR = !r || card.dataset.region === r;
      const okC = !c || card.dataset.category === c;
      const okRel = !minRel || parseInt(card.dataset.relevance, 10) >= minRel;
      const show = okQ && okR && okC && okRel;
      card.hidden = !show;
      if (show) visible++;
    }
    if (counter) counter.textContent = visible;
    if (empty) empty.hidden = visible !== 0;
  }

  let t;
  search.addEventListener('input', () => { clearTimeout(t); t = setTimeout(apply, 120); });
  for (const el of [region, category, relevance]) el.addEventListener('change', apply);
})();
