"""Die Browser-Seite des Konfigurationsbilds (``gegenprobe_bild``): Skripte, die auf der
offenen Seite laufen. Sie lesen nur und blenden für das eigene Bild Leisten aus; sie
klicken nichts und schicken nichts an den Anbieter.

``SUCHE`` findet den Preisbereich (kleinstes Element mit allen Ankern) und je Merkmal
das sichtbare Element mit seinem Text. Für Speicher, Tarif und Raten zählt nur die
GEWÄHLTE Option (``gewaehlt``): ``aria-checked``/``aria-selected``/``aria-pressed``
oder ``aria-current`` an der Kachel (Telekom: ``button[role=radio]``, congstar
Speicher), genau ein ``input`` der Kachel mit ``checked`` (o2 ``tef-choice-item``,
congstar Raten und Tarif, Vodafone, 1&1), ``aria-description`` „ausgewählt“, eine
Klasse wie ``selected``/``active``; ohne erkennbaren Zustand zählt nur eine
Zusammenfassung („Speicher: 256 GB“, „Ausgewähltes Gerät“ und „Mein Tarif“ bei
Saturn/MediaMarkt, „mit Vertrag …“ und „Dein Tarif“ bei o2, der Preisbereich selbst).
``WIDERSPRUCH`` sucht einen zweiten, sichtbaren
Monatspreis außerhalb des Preisbereichs (Leiste mit anderem Tarif, 1&1 21.11.2026).
``AUSBLENDEN`` versteckt fest stehende und haftende Leisten, die weder Preis noch
Auswahl enthalten (``WIEDER`` stellt sie her). Ein Merkmal kommt mit seiner Karte
(höchstens 700 × 400 px) ins Bild. ``PRUEFE`` misst nach dem Rollen je Merkmal:
Rechteck ganz im Ausschnitt, von keinem Vorfahren mit ``overflow`` beschnitten, an
fünf Punkten trifft ``elementFromPoint`` das Element oder ein Kind
(für die Messung nimmt das Element Zeigerereignisse an: ``pointer-events: none`` auf
Beschriftungen verdeckt nichts).
"""

KERN = """
const norm = s => (s || '').normalize('NFKC').toLowerCase()
  .replace(/[^a-z0-9äöüß]/g, '');
const BETRAG = /\\d{1,4}(?:\\.\\d{3})*,(?:\\d{2}|[–-]{1,2})/g;
const betraege = s => (String(s || '').match(BETRAG) || [])
  .map(b => b.replace(/[–-]+$/, '00'));
const k3 = () => window.__gegenprobeBild || {merkmale: {}};
"""

SUCHE = (
    """(arg) => {"""
    + KERN
    + """
  const AN = /(^|[\\s_-])(active|selected|checked|chosen|current)([\\s_-]|$)/i;
  const AUS = /(un|in|not-?)(selected|active|checked)/i;
  const ZUSAMMEN = new RegExp('^\\\\s*(\\\\d+\\\\s+)?(ausgewählt|gewählt|dein angebot'
    + '|deine auswahl|dein tarif|mein tarif|mit vertrag)', 'i');
  const LABEL = /^\\s*(speicher\\w*|ratenzahlung[\\w ]*|laufzeit|tarif|farbe)\\s*:/i;
  const text = new Map();
  const alle = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) continue;
    if (getComputedStyle(el).visibility === 'hidden') continue;
    text.set(el, norm(el.innerText));
    alle.push(el);
  }
  let preis = null, laenge = Infinity;
  const anker = (arg.anker || []).map(norm);
  if (anker.length) {
    for (const el of alle) {
      const t = text.get(el);
      if (t.length < laenge && anker.every(a => t.includes(a))) {
        preis = el;
        laenge = t.length;
      }
    }
  }
  const teile = [];
  if (preis) {
    const innen = alle.filter(el => preis.contains(el));
    for (const a of anker) {
      const hat = el => (text.get(el) || '').includes(a);
      const tief = innen.find(el => hat(el) && !Array.from(el.children).some(hat));
      if (tief) teile.push(tief);
    }
  }
  const gewaehlt = (el) => {
    let e = el;
    for (let i = 0; i < 7 && e && e !== document.body; i++, e = e.parentElement) {
      for (const a of ['aria-checked', 'aria-selected', 'aria-pressed']) {
        if (e.hasAttribute(a)) return {ok: e.getAttribute(a) === 'true', kachel: e};
      }
      const cur = e.getAttribute('aria-current');
      if (cur && cur !== 'false') return {ok: true, kachel: e};
      const knoepfe = e.matches('input') ? [e]
        : Array.from(e.querySelectorAll('input[type=radio],input[type=checkbox]'));
      if (knoepfe.length === 1) return {ok: knoepfe[0].checked, kachel: e};
      if (knoepfe.length > 1) break;
      const beschreibung = (e.getAttribute('aria-description') || '').toLowerCase();
      if (beschreibung.includes('ausgewählt')) return {ok: true, kachel: e};
      const cls = typeof e.className === 'string' ? e.className : '';
      if (AN.test(cls) && !AUS.test(cls)) return {ok: true, kachel: e};
    }
    return null;
  };
  const zusammenfassung = (el) => {
    if (preis && preis.contains(el)) return true;
    let e = el;
    for (let i = 0; i < 8 && e && e !== document.body; i++, e = e.parentElement) {
      const t = (e.innerText || '').slice(0, 60);
      if (ZUSAMMEN.test(t) || (i < 2 && LABEL.test(t))) return true;
    }
    return false;
  };
  const grob = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) return false;
    for (let e = el; e && e !== document.body; e = e.parentElement) {
      const s = getComputedStyle(e);
      if (s.opacity === '0' || s.clip.startsWith('rect(0')) return false;
      if (e !== el && (s.overflowX !== 'visible' || s.overflowY !== 'visible')) {
        const a = e.getBoundingClientRect();
        if (r.left < a.left - 1 || r.top < a.top - 1 || r.right > a.right + 1
            || r.bottom > a.bottom + 1) return false;
      }
    }
    return true;
  };
  const verdeckt = (el) => {
    const r = el.getBoundingClientRect();
    const x = r.left + r.width / 2, y = r.top + r.height / 2;
    if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) return false;
    const t = document.elementFromPoint(x, y);
    return !t || !el.contains(t);
  };
  const rp = teile.map(el => el.getBoundingClientRect());
  const mitte = rp.length ? (Math.min(...rp.map(r => r.top))
    + Math.max(...rp.map(r => r.bottom))) / 2 : 0;
  const merkmale = {};
  for (const [name, nadeln] of Object.entries(arg.merkmale)) {
    const n = nadeln.map(norm).filter(x => x);
    const hat = el => n.some(x => (text.get(el) || '').includes(x));
    const wahl = arg.wahl.includes(name);
    let bestes = null, wert = Infinity;
    for (const el of alle) {
      if (!hat(el) || Array.from(el.children).some(hat)) continue;
      const r = el.getBoundingClientRect();
      const m = r.top + r.height / 2;
      let d = m > mitte ? (m - mitte) * 1.5 : mitte - m;
      const sel = wahl ? gewaehlt(el) : null;
      const ok = !wahl || (sel ? sel.ok : zusammenfassung(el));
      if (!ok) d += 1e7;
      if (!grob(el) || verdeckt(el)) d += 1e6;
      if (d < wert) {
        wert = d;
        bestes = {el, kachel: sel && sel.ok ? sel.kachel : el, gewaehlt: ok};
      }
    }
    if (bestes) merkmale[name] = bestes;
  }
  const hoch = preis && preis.getBoundingClientRect().height <= arg.preis_hoechstens;
  window.__gegenprobeBild = {preis, teile: hoch ? [preis] : teile, merkmale, aus: []};
  return Object.fromEntries(Object.entries(merkmale).map(([k, v]) => [k, v.gewaehlt]));
}"""
)

PREISTEXT = (
    """() => {"""
    + KERN
    + """
  const p = k3().preis;
  return p && p.isConnected ? p.innerText : null;
}"""
)

KAESTEN = """() => {
  const k = window.__gegenprobeBild || {merkmale: {}};
  const kasten = el => {
    if (!el || !el.isConnected) return null;
    const r = el.getBoundingClientRect();
    return {x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height};
  };
  const teile = (k.teile || []).map(kasten).filter(b => b);
  const x = Math.min(...teile.map(b => b.x)), y = Math.min(...teile.map(b => b.y));
  const preis = teile.length ? {
    x, y,
    w: Math.max(...teile.map(b => b.x + b.w)) - x,
    h: Math.max(...teile.map(b => b.y + b.h)) - y,
  } : null;
  const karte = (el) => {
    let best = el;
    let e = el;
    for (let i = 0; i < 4 && e && e !== document.body; i++, e = e.parentElement) {
      const r = e.getBoundingClientRect();
      if (r.width > 700 || r.height > 400) break;
      best = e;
    }
    return best;
  };
  const out = {preis, merkmale: {}};
  for (const [name, m] of Object.entries(k.merkmale)) {
    const b = kasten(karte(m.kachel));
    if (b) out.merkmale[name] = b;
  }
  return out;
}"""

WIDERSPRUCH = (
    """() => {"""
    + KERN
    + """
  const MONAT = new RegExp('(€\\\\s*/\\\\s*mon|pro monat|monatlich gesamt'
    + '|gesamtpreis monatlich|monatliche gesamtkosten)', 'i');
  const k = k3();
  if (!k.preis) return null;
  const eigene = new Set(betraege(k.preis.innerText));
  for (const el of document.querySelectorAll('body *')) {
    if (k.preis.contains(el) || el.contains(k.preis)) continue;
    const t = el.innerText || '';
    if (!MONAT.test(t) || t.length > 160) continue;
    if (Array.from(el.children).some(c => MONAT.test(c.innerText || ''))) continue;
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0 || r.bottom < 0 || r.top > innerHeight) continue;
    const mx = r.left + r.width / 2, my = r.top + r.height / 2;
    const treffer = document.elementFromPoint(mx, my);
    if (!treffer || !(el.contains(treffer) || treffer.contains(el))) continue;
    const fremd = betraege(t).filter(b => !eigene.has(b));
    if (fremd.length) return t.replace(/\\s+/g, ' ').trim().slice(0, 80);
  }
  return null;
}"""
)

AUSBLENDEN = """(anteil) => {
  const k = window.__gegenprobeBild || {merkmale: {}};
  const behalten = [k.preis, ...(k.teile || []),
    ...Object.values(k.merkmale).map(m => m.kachel)].filter(e => e);
  const flaeche = innerWidth * innerHeight;
  k.aus = k.aus || [];
  const schon = new Set(k.aus.map(([el]) => el));
  for (const el of document.querySelectorAll('body *')) {
    if (schon.has(el)) continue;
    const pos = getComputedStyle(el).position;
    if (pos !== 'fixed' && pos !== 'sticky') continue;
    if (behalten.some(b => el.contains(b) || b.contains(el))) continue;
    const r = el.getBoundingClientRect();
    if (r.width * r.height > anteil * flaeche) continue;
    k.aus.push([el, el.style.visibility]);
    el.style.visibility = 'hidden';
  }
  return k.aus.length;
}"""

WIEDER = """() => {
  const k = window.__gegenprobeBild || {};
  for (const [el, alt] of k.aus || []) el.style.visibility = alt;
  k.aus = [];
}"""

PRUEFE = """(clip) => {
  const k = window.__gegenprobeBild || {merkmale: {}};
  const innen = (a, b) => a.left >= b.left - 1 && a.top >= b.top - 1
    && a.right <= b.right + 1 && a.bottom <= b.bottom + 1;
  const ausschnitt = {left: clip.x, top: clip.y, right: clip.x + clip.width,
    bottom: clip.y + clip.height};
  const stil = document.createElement('style');
  stil.textContent = '[data-gegenprobe-ziel], [data-gegenprobe-ziel] * '
    + '{ pointer-events: auto !important; }';
  document.head.appendChild(stil);
  const sichtbar = (el) => {
    if (!el || !el.isConnected) return 'fehlt';
    el.setAttribute('data-gegenprobe-ziel', '');
    try { return pruefe(el); } finally { el.removeAttribute('data-gegenprobe-ziel'); }
  };
  const pruefe = (el) => {
    const r = el.getBoundingClientRect();
    if (!innen(r, ausschnitt)) return 'nicht ganz im Bild';
    for (let e = el.parentElement; e && e !== document.body; e = e.parentElement) {
      const s = getComputedStyle(e);
      if ((s.overflowX !== 'visible' || s.overflowY !== 'visible')
          && !innen(r, e.getBoundingClientRect())) return 'abgeschnitten';
    }
    const dx = r.width * 0.2, dy = r.height * 0.2;
    const punkte = [[r.left + r.width / 2, r.top + r.height / 2],
      [r.left + dx, r.top + dy], [r.right - dx, r.top + dy],
      [r.left + dx, r.bottom - dy], [r.right - dx, r.bottom - dy]];
    for (const [x, y] of punkte) {
      const t = document.elementFromPoint(x, y);
      if (!t || !el.contains(t)) return 'verdeckt';
    }
    return '';
  };
  const out = {};
  for (const [name, m] of Object.entries(k.merkmale)) {
    out[name] = m.gewaehlt ? sichtbar(m.el) : 'nicht gewählt';
  }
  const teile = (k.teile || []);
  out['Preis'] = teile.length ? (teile.map(sichtbar).find(g => g) || '') : 'fehlt';
  stil.remove();
  return out;
}"""
