"""Die Browser-Seite des Konfigurationsbilds (``gegenprobe_bild``): Skripte, die auf der
offenen Seite laufen. Sie lesen nur und blenden für das eigene Bild Leisten aus; sie
klicken nichts und schicken nichts an den Anbieter.

``SUCHE`` findet den Preisbereich (kleinstes Element mit allen Ankern) und je Merkmal
das Element, das es zeigt. Für Speicher, Tarif und Raten entscheidet zuerst die
GEWÄHLTE Option (``aria-checked``/``aria-selected``/``aria-pressed`` oder ein
``input:checked`` mit seiner Kachel; Telekom ``button[role=radio]``, o2
``tef-choice-item``, congstar, Vodafone, 1&1): trägt sie den Wert des Bündels, ist das
Merkmal gezeigt, sonst nicht („gewählt: …“), und keine Zusammenfassung überstimmt sie.
Nur ohne erkennbare Auswahl zählt ein je Anbieter benannter Block
(``gegenprobe_merkmale.BLOECKE``), der genau EINEN Wert des Merkmals nennt. Werte
vergleicht ``ARTEN`` mit Wortgrenzen („MagentaMobil S“ ist nicht „… Start“, „24“ nicht
„124“, „x24“ wie „x 24“, Mindestlaufzeit zählt nicht als Raten). ``WIDERSPRUCH`` sucht
im Fenster und im fotografierten Ausschnitt einen zweiten, sichtbaren
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
  const normw = s => ' ' + (s || '').normalize('NFKC').toLowerCase()
    .replace(/[^a-z0-9äöüß]+/g, ' ').trim() + ' ';
  const hatWort = (t, n) => t.includes(' ' + n.trim() + ' ');
  const esc = s => s.trim().replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&');
  const ARTEN = {
    Speicher: t => [...t.matchAll(
      /(?<= )((?:32|64|128|256|512|1024|2048) ?gb|[12] ?tb)(?= )/g)]
      .map(m => m[1].replace(/ /g, ''))
      .map(w => w.endsWith('tb') ? (parseInt(w, 10) * 1024) + 'gb' : w),
    Raten: t => [...t.matchAll(new RegExp('(?<= )x ?(\\\\d+)(?= )|(?<!laufzeit )'
      + '(?<= )(\\\\d+) (?:raten|mtl zahlungen|monate)(?= )(?! laufzeit)', 'g'))]
      .map(m => m[1] || m[2]),
    Tarif: (t, fam) => fam ? [...t.matchAll(new RegExp('(?<= )' + esc(fam)
      + ' ([a-z0-9]+)(?= )', 'g'))].map(m => m[1]) : [],
  };
  const alle = [];
  const text = new Map();
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) continue;
    if (getComputedStyle(el).visibility === 'hidden') continue;
    text.set(el, normw(el.innerText));
    alle.push(el);
  }
  const kleinstes = (anker) => {
    let best = null, laenge = Infinity;
    for (const el of alle) {
      const t = text.get(el);
      if (t.length < laenge && anker.every(a => t.includes(a))) {
        best = el;
        laenge = t.length;
      }
    }
    return best;
  };
  const anker = (arg.anker || []).map(a => normw(a).trim());
  const preis = anker.length ? kleinstes(anker) : null;
  const teile = [];
  if (preis) {
    const innen = alle.filter(el => preis.contains(el));
    for (const a of anker) {
      const hat = el => (text.get(el) || '').includes(a);
      const tief = innen.find(el => hat(el) && !Array.from(el.children).some(hat));
      if (tief) teile.push(tief);
    }
  }
  const tiefstes = (wurzel, nadeln) => {
    const hat = el => nadeln.some(n => hatWort(text.get(el) || normw(el.innerText), n));
    let el = wurzel;
    for (;;) {
      const kind = Array.from(el.children).find(hat);
      if (!kind) return el;
      el = kind;
    }
  };
  const traeger = [];
  const WAHL = '[aria-checked="true"],[aria-selected="true"],[aria-pressed="true"],'
    + 'input[type=radio],input[type=checkbox]';
  for (const el of document.querySelectorAll(WAHL)) {
    if (el.matches('input') && !el.checked) continue;
    let k = el;
    if (el.matches('input')) {
      let e = el.parentElement;
      for (let i = 0; i < 6 && e && e !== document.body; i++, e = e.parentElement) {
        const knoepfe = e.querySelectorAll('input[type=radio],input[type=checkbox]');
        if (knoepfe.length > 1) break;
        k = e;
      }
    }
    const r = k.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) continue;
    traeger.push({el: k, t: normw(k.innerText)});
  }
  const bloecke = (arg.bloecke || []).map(a => kleinstes(a.map(x => normw(x).trim())))
    .filter(e => e);
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
  const naechstes = (nadeln) => {
    let bestes = null, wert = Infinity;
    for (const el of alle) {
      const hat = e => nadeln.some(n => hatWort(text.get(e) || '', n));
      if (!hat(el) || Array.from(el.children).some(hat)) continue;
      const r = el.getBoundingClientRect();
      const m = r.top + r.height / 2;
      let d = m > mitte ? (m - mitte) * 1.5 : mitte - m;
      if (!grob(el) || verdeckt(el)) d += 1e6;
      if (d < wert) { wert = d; bestes = el; }
    }
    return bestes;
  };
  const kurz = el => (el.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 40);
  const merkmale = {};
  for (const [name, angabe] of Object.entries(arg.merkmale)) {
    const nadeln = angabe.nadeln.map(n => normw(n).trim()).filter(n => n);
    const art = ARTEN[name];
    if (!art) {
      const el = naechstes(nadeln);
      if (el) merkmale[name] = {el, kachel: el, gewaehlt: true, grund: ''};
      continue;
    }
    const passt = t => art(t, angabe.familie).includes(angabe.wert);
    const explizit = traeger.filter(c => art(c.t, angabe.familie).length);
    if (explizit.length) {
      const treffer = explizit.find(c => passt(c.t));
      merkmale[name] = treffer
        ? {el: tiefstes(treffer.el, nadeln), kachel: treffer.el, gewaehlt: true,
           grund: ''}
        : {el: explizit[0].el, kachel: explizit[0].el, gewaehlt: false,
           grund: 'gewählt: ' + kurz(explizit[0].el)};
      continue;
    }
    for (const block of bloecke) {
      const werte = new Set(art(text.get(block), angabe.familie));
      if (werte.size !== 1) continue;
      if (werte.has(angabe.wert)) {
        const el = tiefstes(block, nadeln);
        merkmale[name] = {el, kachel: el, gewaehlt: true, grund: ''};
      } else {
        merkmale[name] = {el: block, kachel: block, gewaehlt: false,
          grund: 'Übersicht nennt ' + [...werte][0]};
      }
      break;
    }
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
    """(clip) => {"""
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
    if (clip && (r.right < clip.x || r.left > clip.x + clip.width
        || r.bottom < clip.y || r.top > clip.y + clip.height)) continue;
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
    out[name] = m.gewaehlt ? sichtbar(m.el) : (m.grund || 'nicht gewählt');
  }
  const teile = (k.teile || []);
  out['Preis'] = teile.length ? (teile.map(sichtbar).find(g => g) || '') : 'fehlt';
  stil.remove();
  return out;
}"""
