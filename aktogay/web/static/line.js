/* Line view (L2): one processing line. HTML header (state and its reason, four numbers, the shift), then
   an SVG flowsheet drawn at the real pixel size of its box (viewBox = box width), so no text is ever
   smaller than 13 px: grinding in the top row (stockpile → SAG ⇄ pebble crusher → cyclones ⇄ ball mills),
   flotation to the concentrate in the bottom row. In the norm a node is grey with its name; colour, a
   glyph and the state word only for a deviation; the node of an issue carries its number and price.
   Ore runs along the main flow at a speed ∝ t/h (one requestAnimationFrame loop, off when hidden). */
'use strict';
(function () {
  const SVGNS = 'http://www.w3.org/2000/svg';
  const E = (tag, attrs, parent) => { const e = document.createElementNS(SVGNS, tag); for (const k in attrs || {}) if (attrs[k] != null) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; };
  const T = (parent, x, y, text, attrs) => { const t = E('text', Object.assign({ x, y }, attrs || {}), parent); t.textContent = text; return t; };
  const fmt = AKT.fmt, f1 = AKT.f1, f2 = AKT.f2, f3 = AKT.f3, NB = ' ';
  const G = lv => lv ? AKT.LV_GLYPH[lv] + ' ' : '';
  const hShort = h => h == null ? '—' : h < 1 ? `${Math.round(h * 60)} мин` : h < 10 ? `${f1(h)} ч` : `${fmt(h)} ч`;
  const NH = 46, SUB = 16;

  /* nodes: title, place [row, col] (row 0 grinding, 0.5 its second row, 1 flotation), sub-lines ≤ 22 characters, bar [value, limit] */
  function spec(N) {
    const n = s => s.replace('N', N);
    return {
      [n('stockpile-N')]: { t: 'Склад руды', at: [0, 0], sub: s => { const h = AKT.hoursLeft(s); return [`${fmt(AKT.num(s, 'level_t'))} т`, h != null && h >= 0 && h <= 48 ? `хватит на ${hShort(h)}` : AKT.stockNote(s).short]; }, bar: s => [AKT.num(s, 'level_t'), AKT.pass(s, 'live_t') || 40000], title: s => `Склад руды ${N}: ${fmt(AKT.num(s, 'level_t'))} т · приход ${fmt(AKT.num(s, 'in_tph'))} · расход ${fmt(AKT.num(s, 'out_tph'))} т/ч` },
      [n('sag-N')]: { t: `Мельница SAG-${N}`, at: [0, 1], sub: s => [`${f1(AKT.num(s, 'power_kw') / 1000)} из ${fmt(AKT.num(s, 'power_limit_kw') / 1000)} МВт`, `${fmt(AKT.num(s, 'feed_tph'))} т/ч руды`], bar: s => [AKT.num(s, 'power_kw'), AKT.num(s, 'power_limit_kw')], title: s => `Мельница SAG-${N}: мощность ${f1(AKT.num(s, 'power_kw') / 1000)} из ${fmt(AKT.num(s, 'power_limit_kw') / 1000)} МВт (из сети ≈ ${f1(AKT.gridFromShaft(AKT.num(s, 'power_kw') / 1000))}) · ${fmt(AKT.num(s, 'feed_tph'))} т/ч · загрузка ${f1(AKT.num(s, 'load_pct'))} % · удельная энергия ${f2(AKT.num(s, 'e_kwh_t'))} кВт·ч/т` },
      [n('pebble-N')]: { t: 'Дробление гали', at: [0.5, 1], sub: s => [`${fmt(AKT.num(s, 'feed_tph'))} из ${fmt(AKT.num(s, 'limit_tph'))} т/ч`, `загрузка ${fmt(AKT.num(s, 'load_pct'))} %`], bar: s => [AKT.num(s, 'feed_tph'), AKT.num(s, 'limit_tph')], title: s => `Дробление гали (крупных окатышей, пресс HPGR): ${fmt(AKT.num(s, 'feed_tph'))} из ${fmt(AKT.num(s, 'limit_tph'))} т/ч` },
      [n('cyclones-N')]: { t: 'Гидроциклоны', at: [0, 2], sub: s => [`помол ${fmt(AKT.num(s, 'p80_um'))} мкм`, `в работе ${fmt(AKT.num(s, 'open_count'))} из ${fmt(AKT.pass(s, 'units'))}`], title: s => `Гидроциклоны: крупность помола (P80) ${fmt(AKT.num(s, 'p80_um'))} мкм · циклонов в работе ${fmt(AKT.num(s, 'open_count'))} из ${fmt(AKT.pass(s, 'units'))} · давление ${fmt(AKT.num(s, 'pressure_kpa'))} кПа` },
      [n('ball-Na')]: { t: `Шаровая ${N}A`, at: [0, 3], sub: s => [`${f1(AKT.num(s, 'power_kw') / 1000)} из ${fmt(AKT.pass(s, 'drive_mw'))} МВт`], bar: s => [AKT.num(s, 'power_kw'), (AKT.pass(s, 'drive_mw') || 22) * 1000], title: s => `Шаровая мельница ${N}A: ${f1(AKT.num(s, 'power_kw') / 1000)} из ${fmt(AKT.pass(s, 'drive_mw'))} МВт` },
      [n('ball-Nb')]: { t: `Шаровая ${N}B`, at: [0.5, 3], sub: s => [`${f1(AKT.num(s, 'power_kw') / 1000)} из ${fmt(AKT.pass(s, 'drive_mw'))} МВт`], bar: s => [AKT.num(s, 'power_kw'), (AKT.pass(s, 'drive_mw') || 22) * 1000], title: s => `Шаровая мельница ${N}B: ${f1(AKT.num(s, 'power_kw') / 1000)} из ${fmt(AKT.pass(s, 'drive_mw'))} МВт` },
      [n('rougher-N')]: { t: 'Флотация', at: [1, 0], sub: s => [`извлечение ${f1(AKT.num(s, 'stage_recovery'))} %`, `реагент ${f1(AKT.num(s, 'dose_meas_gt'))} из ${fmt(AKT.num(s, 'dose_sp_gt'))} г/т`], title: s => `Основная и контрольная флотация: извлечение ${f1(AKT.num(s, 'stage_recovery'))} % · собиратель ${f1(AKT.num(s, 'dose_meas_gt'))} из ${fmt(AKT.num(s, 'dose_sp_gt'))} г/т · выход пены ${f1(AKT.num(s, 'mass_pull_pct'))} %` },
      [n('cleaner-N')]: { t: 'Перечистка', at: [1, 1], sub: s => [`извлечение ${f1(AKT.num(s, 'stage_recovery'))} %`, `${f1(AKT.num(s, 'conc_cu'))} % меди`], title: s => `Перечистка: извлечение ${f1(AKT.num(s, 'stage_recovery'))} % · медь в концентрате ${f1(AKT.num(s, 'conc_cu'))} % · ${f1(AKT.num(s, 'conc_tph'))} т/ч` },
      [n('thick-N')]: { t: 'Сгуститель', at: [1, 2], sub: s => [`${fmt(AKT.num(s, 'inventory_t'))} из ${fmt(AKT.pass(s, 'capacity_t'))} т`, AKT.num(s, 'hours_to_full') != null ? `полон через ${hShort(AKT.num(s, 'hours_to_full'))}` : ''], bar: s => [AKT.num(s, 'inventory_t'), AKT.pass(s, 'capacity_t') || 340], title: s => `Сгуститель: ${fmt(AKT.num(s, 'inventory_t'))} из ${fmt(AKT.pass(s, 'capacity_t'))} т · твёрдого ${fmt(AKT.num(s, 'solids_pct'))} %` },
      [n('filter-N')]: { t: 'Фильтр', at: [1, 3], sub: s => [`прессов ${fmt(AKT.num(s, 'presses_on'))} из ${fmt(AKT.pass(s, 'presses'))}`, `${f1(AKT.num(s, 'cake_tph'))} из ${fmt(AKT.num(s, 'limit_tph'))} т/ч`], bar: s => [AKT.num(s, 'cake_tph'), AKT.num(s, 'limit_tph')], title: s => `Фильтр: прессов в работе ${fmt(AKT.num(s, 'presses_on'))} из ${fmt(AKT.pass(s, 'presses'))} · ${f1(AKT.num(s, 'cake_tph'))} из ${fmt(AKT.num(s, 'limit_tph'))} т/ч · влажность ${f1(AKT.num(s, 'moisture_pct'))} %` },
      'conc-stock': { t: 'Склад концентрата', at: [1, 4], sub: s => { const h = AKT.num(s, 'hours_to_full'); return [`${fmt(AKT.num(s, 'stock_t'))} из ${fmt(AKT.pass(s, 'capacity_t'))} т`, h != null && h <= 24 ? `полон через ${hShort(h)}` : 'поезд в 06:00 и 18:00']; }, bar: s => [AKT.num(s, 'stock_t'), AKT.pass(s, 'capacity_t') || 20000], title: s => `Склад концентрата (общий): ${fmt(AKT.num(s, 'stock_t'))} из ${fmt(AKT.pass(s, 'capacity_t'))} т · отгрузка поездом в 06:00 и 18:00` },
    };
  }
  /* edges: [from, to, flow t/h, kind] — kind: '' main flow, 'ret' return to regrind, 'down' row A → row B */
  function edges(N) {
    const n = s => s.replace('N', N);
    const sag = () => AKT.num(n('sag-N'), 'feed_tph');
    return [
      [n('stockpile-N'), n('sag-N'), () => AKT.num(n('stockpile-N'), 'out_tph') ?? sag(), ''],
      [n('sag-N'), n('pebble-N'), () => AKT.num(n('pebble-N'), 'feed_tph'), 'sub'],
      [n('pebble-N'), n('sag-N'), () => AKT.num(n('pebble-N'), 'feed_tph'), 'ret'],
      [n('sag-N'), n('cyclones-N'), sag, ''],
      [n('cyclones-N'), n('ball-Na'), sag, 'sub'],
      [n('cyclones-N'), n('ball-Nb'), sag, 'sub'],
      [n('ball-Na'), n('cyclones-N'), sag, 'ret'],
      [n('ball-Nb'), n('cyclones-N'), sag, 'ret'],
      [n('cyclones-N'), n('rougher-N'), () => AKT.num(n('rougher-N'), 'feed_tph') ?? sag(), 'down'],
      [n('rougher-N'), n('cleaner-N'), () => AKT.num(n('cleaner-N'), 'feed_tph'), ''],
      [n('cleaner-N'), n('thick-N'), () => AKT.num(n('cleaner-N'), 'conc_tph'), ''],
      [n('thick-N'), n('filter-N'), () => AKT.num(n('thick-N'), 'underflow_tph'), ''],
      [n('filter-N'), 'conc-stock', () => AKT.num(n('filter-N'), 'cake_tph'), ''],
    ];
  }
  const BASE_OF = {
    stockpile: ['level_t', fmt, 200], sag: ['feed_tph', fmt, 50], pebble: ['feed_tph', fmt, 20],
    cyclones: ['p80_um', fmt, 3], rougher: ['dose_meas_gt', f1, 0.5], thick: ['inventory_t', fmt, 10],
    filter: ['cake_tph', f1, 1], 'conc-stock': ['stock_t', fmt, 50],
  };

  const view = {
    n: '1', svg: null, nodes: {}, edgeEls: [], ro: null, charts: [], W: 0, raf: 0,
    async build(stage, opts) {
      this.n = String(opts.n || '1');
      stage.innerHTML = '';
      const head = document.createElement('div'); head.id = 'line-head';
      head.innerHTML = `<div class="lh-1" id="lh-1"></div><div id="lh-issue" class="p-sub"></div>
<div class="tiles" id="lh-tiles">
 <div class="tile"><div class="l">Руда</div><div class="v" id="lh-tph">—</div></div>
 <div class="tile"><div class="l">Медь в концентрат</div><div class="v" id="lh-cu">—</div></div>
 <div class="tile"><div class="l">Извлечение</div><div class="v" id="lh-rec">—</div></div>
 <div class="tile"><div class="l">Сеть (мельницы)</div><div class="v" id="lh-mw">—</div></div></div>
<div class="lh-3" id="lh-3"></div>`;
      stage.appendChild(head);
      const wrap = document.createElement('div'); wrap.id = 'line-wrap'; stage.appendChild(wrap);
      const ch = document.createElement('div'); ch.className = 'doc'; ch.id = 'line-charts';
      ch.innerHTML = `<h3>Последние 2 часа (время модели)</h3><div id="ch-tail"></div><div id="ch-rec"></div><p class="note" id="line-note"></p>`;
      stage.appendChild(ch);
      this.wrap = wrap;
      this.draw();
      this.ro = new ResizeObserver(() => { if (Math.abs(wrap.clientWidth - this.W) > 4) { this.draw(); this.update(); } });
      this.ro.observe(wrap);
      this.charts = [
        AKT.trend(document.getElementById('ch-tail'), `flot-${this.n}`, 'tail_cu', { title: `Медь в хвостах флотации ${this.n}, %`, unit: '%', digits: 3, limit: 0.075, limitLabel: 'уставка 0,075 %', normHi: 0.075, normLabel: 'норма до 0,075 %' }),
        AKT.trend(document.getElementById('ch-rec'), `line-${this.n}`, 'recovery', { title: `Извлечение меди, линия ${this.n}, %`, unit: '%', digits: 1, normLo: 85, normHi: 92, normLabel: 'обычно 85–92 %' }),
      ];
      this.onVis = () => { if (!document.hidden) this.loop(); };
      document.addEventListener('visibilitychange', this.onVis);
      this.loop();
    },
    destroy() {
      if (this.ro) this.ro.disconnect(); this.charts.forEach(c => c.stop()); this.charts = [];
      if (this.raf) cancelAnimationFrame(this.raf); this.raf = 0;
      if (this.onVis) document.removeEventListener('visibilitychange', this.onVis);
    },
    draw() {
      const wrap = this.wrap, N = this.n, S = spec(N);
      const W = this.W = Math.max(720, wrap.clientWidth || 800);
      const M = 14, COL = (W - 2 * M) / 5, NW = Math.min(160, COL - 22);
      const xOf = c => M + COL * c + COL / 2;
      const yA = 72, yA2 = yA + NH + 72, yB = yA2 + NH + 112;
      const yOf = r => r === 0 ? yA : r === 0.5 ? yA2 : yB;
      const H = yB + NH / 2 + 100;
      wrap.innerHTML = '';
      const svg = this.svg = E('svg', { class: 'sheet', viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img', 'aria-label': `Схема линии ${N}: помол сверху, флотация снизу` }, wrap);
      svg.style.width = W + 'px'; svg.style.height = H + 'px';
      this.nodes = {}; this.edgeEls = [];
      const defs = E('defs', null, svg);
      const mk = E('marker', { id: 'arr', viewBox: '0 0 10 10', refX: 8, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto', markerUnits: 'userSpaceOnUse' }, defs);
      E('path', { d: 'M0,0 L10,5 L0,10 z', fill: '#3a3f47' }, mk);
      const gE = E('g', { class: 'edges' }, svg), gN = E('g', { class: 'nodes' }, svg);
      /* flotation frame around rougher and cleaner */
      const fx = xOf(0) - NW / 2 - 10, fw = xOf(1) - xOf(0) + NW + 20;
      this.frame = E('rect', { x: fx, y: yB - NH / 2 - 12, width: fw, height: NH + 12 + 50, class: 'frame', rx: 6 }, svg);
      this.frameT = T(svg, fx, yB + NH / 2 + 66, `Флотация ${N}`, { class: 'frame-t' });
      T(svg, M, 18, 'Подача, помол и классификация', { class: 'frame-t' });
      for (const name in S) {
        const sp = S[name];
        const x = xOf(sp.at[1]), y = yOf(sp.at[0]);
        const g = E('g', { class: 'nd st-grey', id: 'nd-' + name }, gN);
        const a = E('a', { href: AKT.href(`?view=unit&id=${AKT.id(name)}`) }, g);
        const tip = E('title', null, a);
        const pulse = E('rect', { x: x - NW / 2, y: y - NH / 2, width: NW, height: NH, rx: 5, class: 'pulse', style: 'display:none' }, a);
        E('rect', { x: x - NW / 2, y: y - NH / 2, width: NW, height: NH, class: 'box' }, a);
        const ttl = T(a, x, y + 5, sp.t, { class: 'ttl', 'text-anchor': 'middle' });
        const st = T(a, x, y + 16, '', { class: 'st', 'text-anchor': 'middle' });
        let bar = null;
        if (sp.bar) {
          E('rect', { x: x - NW / 2 + 6, y: y + NH / 2 + 4, width: NW - 12, height: 5, class: 'bar-bg' }, g);
          bar = E('rect', { x: x - NW / 2 + 6, y: y + NH / 2 + 4, width: 0, height: 5, class: 'bar' }, g);
        }
        const subs = [0, 1].map(i => T(g, x, y + NH / 2 + 24 + SUB * i, '', { class: 'sub', 'text-anchor': 'middle' }));
        const baseT = T(g, x, y + NH / 2 + 24 + SUB * 2, '', { class: 'base-t', 'text-anchor': 'middle' });
        /* above the box: the loss badge or the issue callout */
        const loss = E('g', { class: 'loss', style: 'display:none' }, g);
        const lossR = E('rect', { x: x - NW / 2, y: y - NH / 2 - 28, width: NW, height: 22, rx: 4, class: 'loss-b' }, loss);
        const lossT = T(loss, x, y - NH / 2 - 12, '', { class: 'loss-t', 'text-anchor': 'middle' });
        const rk = E('g', { style: 'display:none' }, g);
        E('circle', { cx: x - NW / 2 + 2, cy: y - NH / 2 + 2, r: 11, class: 'rk-d' }, rk);
        const rkT = T(rk, x - NW / 2 + 2, y - NH / 2 + 7, '', { class: 'rk-t' });
        this.nodes[name] = { g, ttl, st, subs, bar, loss, lossR, lossT, baseT, sp, x, y, NW, tip, rk, rkT, pulse };
      }
      const B = this.nodes;
      for (const [a, b, flow, kind] of edges(N)) {
        const A = B[a], Z = B[b];
        if (!A || !Z) continue;
        let d;
        if (kind === 'sub' && Math.abs(A.x - Z.x) < 2) d = `M${A.x - NW / 2 + 4},${A.y + NH / 2 + 12} L${Z.x - NW / 2 + 4},${Z.y - NH / 2 - 2}`;
        else if (kind === 'ret' && Math.abs(A.x - Z.x) < 2) d = `M${A.x + NW / 2 - 4},${A.y - NH / 2} L${Z.x + NW / 2 - 4},${Z.y + NH / 2 + 12}`;
        else if (kind === 'sub') d = `M${A.x + NW / 2},${A.y + 8} C${A.x + NW / 2 + 30},${A.y + 8} ${Z.x - NW / 2 - 30},${Z.y} ${Z.x - NW / 2 - 2},${Z.y}`;
        else if (kind === 'ret') d = `M${A.x - NW / 2},${A.y - 10} C${A.x - NW / 2 - 24},${A.y - 10} ${Z.x + NW / 2 + 24},${Z.y - 14} ${Z.x + NW / 2 + 2},${Z.y - 14}`;
        else if (kind === 'down') { const ym = Z.y - NH / 2 - 34; d = `M${A.x},${A.y + NH / 2 + 40} L${A.x},${ym} L${Z.x},${ym} L${Z.x},${Z.y - NH / 2 - 2}`; }
        else d = `M${A.x + NW / 2},${A.y} L${Z.x - NW / 2 - 2},${Z.y}`;
        const p = E('path', { d, class: 'edge' + (kind === 'ret' ? ' loop' : ''), 'marker-end': 'url(#arr)' }, gE);
        const fl = kind === 'ret' ? null : E('path', { d, class: 'flow', 'stroke-dasharray': '4 12' }, gE);
        this.edgeEls.push({ p, fl, flow, a, b, kind, off: 0, v: 0 });
      }
      const cy = B[`cyclones-${N}`], ba = B[`ball-${N}a`], peb = B[`pebble-${N}`];
      if (cy && ba) T(svg, (cy.x + ba.x) / 2, cy.y - 22, 'возврат на домол', { class: 'edge-t', 'text-anchor': 'middle' });
      if (peb) T(svg, peb.x + NW / 2, peb.y - NH / 2 - 16, 'возврат', { class: 'edge-t' });
      if (cy) T(svg, cy.x + 8, yB - NH / 2 - 40, 'слив циклонов → флотация', { class: 'edge-t' });
      const fl = B[`rougher-${N}`];
      this.tails = T(svg, fl.x - NW / 2 - 10, yB + NH / 2 + 86, '', { class: 'edge-t' });
      const ta = this.tails;
      ta.style.cursor = 'pointer';
      ta.addEventListener('click', () => { location.search = AKT.href('?view=unit&id=kz.aktogay:water').slice(1); });
    },
    loop() {
      if (this.raf) return;
      let last = 0;
      const step = ts => {
        this.raf = 0;
        if (!this.svg || !this.svg.isConnected || document.hidden) return;
        const dt = last ? Math.min(0.1, (ts - last) / 1000) : 0; last = ts;
        const paused = AKT.st('site') === 'PAUSED' || !AKT.num('site', 'speed') || (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
        if (!paused) for (const e of this.edgeEls) if (e.fl && e.v) { e.off -= e.v * dt; e.fl.setAttribute('stroke-dashoffset', (e.off % 16).toFixed(1)); }
        this.raf = requestAnimationFrame(step);
      };
      this.raf = requestAnimationFrame(step);
    },
    update() {
      if (!this.svg) return;
      const N = this.n, chain = AKT.scenarioChain(), L = AKT.losses();
      const ln = `line-${N}`, $ = id => document.getElementById(id);
      const set = (id, t) => { const e = $(id); if (e && e.textContent !== t) e.textContent = t; };
      const lv = AKT.levelOf(ln), r = AKT.lineReason ? AKT.lineReason(N) : null;
      const st = AKT.st(ln), dev = st && !['RUN', 'NORMAL'].includes(st);
      const lineIss = AKT.nodeIssues(ln)[0];
      /* a trouble on the feed of this line (crusher, conveyor, ore stockpile): the line still runs, but not «в норме» */
      const feedIss = AKT.issues().find(i => [`crusher-${N}`, `conveyor-${N}`, `stockpile-${N}`].includes(AKT.issueNode(i)));
      const h1 = `Линия ${N} — ${dev ? `<span class="lh-st">${G(lv || 2)}${AKT.esc(AKT.stOf(ln))}${r ? ': ' + AKT.esc(r.text) : ''}</span>`
        : lv && lineIss ? `<span class="lh-st">${G(lv)}${AKT.esc(AKT.issueTitle(lineIss))}</span>` : lv && r ? `<span class="lh-st">${G(lv)}${AKT.esc(r.text)}</span>`
        : feedIss ? `<span class="lh-st">${G(AKT.issueLevel(feedIss) || 2)}питание: ${AKT.esc(AKT.issueTitle(feedIss))}</span>` : 'работает в норме'}`;
      if ($('lh-1')._raw !== h1) { $('lh-1')._raw = h1; $('lh-1').innerHTML = h1; }
      $('lh-1').className = 'lh-1 lv-' + (lv || (feedIss ? AKT.issueLevel(feedIss) || 2 : 0));
      const iss = AKT.issues().filter(i => { const nd = AKT.issueNode(i); return nd && (AKT.nodeKey(nd) === ln || nd === ln); });
      const ih = iss.slice(0, 2).map(i => `${AKT.rankSign(i) || '•'} ${AKT.esc(AKT.issueTitle(i))} — ${AKT.esc(AKT.issuePrice(i))}${AKT.issueCalled(i) ? ' (позвали)' : ` · <button type="button" class="primary" data-call="${AKT.esc(i)}">Позвать ${AKT.esc(AKT.roleAcc(AKT.roleFirst(AKT.issueRole(i))))}</button>`}`).join('<br>');
      const ie = $('lh-issue');
      if (ie._raw !== ih) { ie._raw = ih; ie.innerHTML = ih; ie.querySelectorAll('[data-call]').forEach(b => b.addEventListener('click', () => AKT.panel.call(b.dataset.call))); }
      ie.hidden = !ih;
      const shaft = AKT.lineShaftMw(N);
      set('lh-tph', `${AKT.vsBase(ln, 'tph', fmt, 50)} т/ч`);
      set('lh-cu', `${AKT.vsBase(ln, 'cu_tph', f1, 0.3)} т/ч`);
      set('lh-rec', `${AKT.vsBase(ln, 'recovery', f1, 0.5)} %`);
      set('lh-mw', `≈ ${f1(AKT.gridFromShaft(shaft))} МВт`);
      set('lh-3', `За смену: ${AKT.vsBase(ln, 'cum_cu_t', f1, 0.5)} т меди · ≈ ${AKT.money(AKT.num(ln, 'cum_usd'))} · ${fmt(AKT.num(ln, 'cum_mwh'))} МВт·ч · ${fmt(AKT.num(ln, 'cum_m3'))} м³ воды`);
      set('line-note', `Сеть (мельницы) — мощность мельниц на валу ${f1(shaft)} МВт, делённая на КПД привода 0,96 (допущение).` + (AKT.baseOk() ? ' Синие пары «a → b» — та же величина в ходе модели без сценария → сейчас.' : ''));
      const fl = `flot-${N}`;
      this.frameT.textContent = `Флотация ${N} · извлечение ${AKT.vsBase(fl, 'recovery', f1, 0.5)} % · медь в хвостах ${f3(AKT.num(fl, 'tail_cu'))} %`;
      const flv = AKT.levelOf(fl);
      this.frame.setAttribute('stroke', flv === 1 ? '#c62828' : flv ? '#5c4300' : '#5b626b');
      this.tails.textContent = `хвосты флотации → хвостохранилище (пруд ${f2((AKT.num('water', 'pond_m3') || 0) / 1e6)} млн м³) · оборотная вода ${fmt((AKT.num('water', 'recycle_m3h') || 0))} м³/ч`;
      const top = AKT.issues().find(i => AKT.rankNo(i) != null);
      for (const name in this.nodes) {
        const nd = this.nodes[name];
        const s = AKT.st(name);
        const nlv = AKT.levelOf(name);
        const nIss = AKT.issues().filter(i => AKT.issueNode(i) === name);
        const ri = nIss.find(i => AKT.rankNo(i) != null);
        const isTop = ri && ri === top;
        const cls = `nd ${AKT.lvCls(nlv)}${AKT.hatchOn() && chain.has(name) ? ' scen' : ''}${isTop ? ' top' : ''}`;
        if (nd.g.getAttribute('class') !== cls) nd.g.setAttribute('class', cls);
        const devS = s && AKT.cls(s) !== 'st-grey';
        /* a load bar at ≥ 97 % is coloured, so it also gets a glyph and a word (colour never alone); a full ore stockpile is normal */
        const bv = nd.bar ? nd.sp.bar(name) : null, barF = bv && bv[0] != null && bv[1] ? Math.max(0, Math.min(1, bv[0] / bv[1])) : 0;
        const barHot = barF >= 0.97 && !/^stockpile-/.test(name);
        const sw = devS ? G(nlv || 2) + AKT.stRu(s, name) : (nlv && ri ? G(nlv) + 'беда' : barHot ? G(2) + 'на пределе' : '');
        if (nd.st.textContent !== sw) nd.st.textContent = sw;
        nd.ttl.setAttribute('y', sw ? nd.y - 4 : nd.y + 5);
        const subs = AKT.thing(name) ? nd.sp.sub(name) : ['нет данных'];
        nd.subs.forEach((t, i) => { const x = subs[i] || ''; if (t.textContent !== x) t.textContent = x; });
        const tt = (AKT.thing(name) ? nd.sp.title(name) : nd.sp.t) + (devS ? ` · ${AKT.stRu(s, name)}` : '') + ' · нажмите — карточка';
        if (nd.tip.textContent !== tt) nd.tip.textContent = tt;
        const bo = BASE_OF[AKT.type(name)];
        const bt = bo && AKT.differs(name, bo[0], bo[2]) ? `${bo[1](AKT.base(name, bo[0]))} → ${bo[1](AKT.num(name, bo[0]))}` : '';
        if (nd.baseT.textContent !== bt) nd.baseT.textContent = bt;
        if (nd.bar) {
          nd.bar.setAttribute('width', String((nd.NW - 12) * barF));
          nd.bar.setAttribute('class', 'bar' + (barHot ? ' st-yellow' : ''));
        }
        nd.rk.style.display = ri ? '' : 'none';
        if (ri) nd.rkT.textContent = fmt(AKT.rankNo(ri));
        nd.pulse.style.display = isTop ? '' : 'none';
        /* above the box: ① and its price, else a sure loss of mod-losses */
        const loss = L.find(l => l.node === name && AKT.lossSure(l)) || (name === `rougher-${N}` ? L.find(l => l.node === fl && AKT.lossSure(l)) : null);
        let txt = '';
        if (ri) txt = `${AKT.rankSign(ri)} ${AKT.issuePrice(ri)}`;
        else if (loss) txt = `≈ ${f1(loss.gap)} т меди/ч`;
        nd.loss.style.display = txt ? '' : 'none';
        if (txt && nd.lossT.textContent !== txt) {
          nd.lossT.textContent = txt;
          try { const b = nd.lossT.getBBox(); const w = Math.max(nd.NW, b.width + 14); nd.lossR.setAttribute('width', w); nd.lossR.setAttribute('x', nd.x - w / 2); } catch (e) { /* not rendered */ }
        }
      }
      for (const e of this.edgeEls) {
        const tph = e.flow();
        const stopped = AKT.stopped(AKT.st(e.a)) || (tph != null && tph < 0.5);
        const big = !e.kind || e.kind === 'down';
        const w = e.kind === 'ret' ? 1.5 : (stopped ? 1.5 : (big ? 2 + 4 * Math.min(1, (tph || 0) / 4880) : 2));
        e.p.setAttribute('stroke-width', String(w));
        const cls = 'edge' + (e.kind === 'ret' ? ' loop' : '') + (stopped ? ' st-red' : '');
        if (e.p.getAttribute('class') !== cls) e.p.setAttribute('class', cls);
        if (e.fl) { e.fl.setAttribute('stroke-width', String(Math.max(1.5, w * 0.55))); e.fl.style.display = stopped ? 'none' : ''; e.v = stopped ? 0 : 10 + 30 * Math.min(1, (tph || 0) / (big ? 4880 : 1500)); }
      }
    },
  };
  AKT.views.line = view;
})();
