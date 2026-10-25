/* Plan view («Обзор»): 2D site plan. Geometry from static/plan.json (OpenStreetMap, ODbL, local metres,
   y north); live values from the twins in AKT.things. ISA-101 overview: in the norm the map is grey with
   ten short labels; colour, a glyph (◆ ▲ △) and a word only where something deviates; trouble ① has a
   pulsing ring and a callout with its one price. Layers (Техника, Люди, Руда, Вода и энергия, Датчики)
   add detail on demand; a deviation is shown in any layer state. Machines in repair are counted in one
   summary, not drawn one by one.
   The SVG is built once; a poll changes text, classes and a few attributes. Pixel groups keep a constant
   size on screen; a layout pass moves labels so that no two texts overlap. Motion (trucks along the haul
   roads, ore on the belts at a speed ∝ t/h) runs in one requestAnimationFrame loop that stops while the
   tab is hidden and while the model is paused. */
'use strict';
(function () {
  const SVGNS = 'http://www.w3.org/2000/svg';
  const E = (tag, attrs, parent) => {
    const e = document.createElementNS(SVGNS, tag);
    for (const k in attrs || {}) if (attrs[k] != null) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  };
  const T = (parent, x, y, text, attrs) => { const t = E('text', Object.assign({ x, y }, attrs || {}), parent); t.textContent = text; return t; };
  const P = arr => arr.map(p => `${p[0]},${-p[1]}`).join(' ');
  const NB = ' ';
  const fmt = AKT.fmt, f1 = AKT.f1, f2 = AKT.f2, f3 = AKT.f3;
  const G = lv => lv ? AKT.LV_GLYPH[lv] + ' ' : '';
  const reduced = () => window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* layers: stored per viewer; «Люди» follows the data (on while someone is called) until chosen by hand */
  const LAYERS = [['tech', 'Техника'], ['people', 'Люди'], ['ore', 'Руда'], ['water', 'Вода и энергия'], ['sensors', 'Датчики']];
  const loadLayers = () => { try { return JSON.parse(AKT.store.get('akt-layers') || '{}') || {}; } catch (e) { return {}; } };
  const CAT_LAYER = { truck: 'tech', dozer: 'tech', drill: 'tech', exc: 'tech', face: 'tech', road: 'tech', person: 'people', crew: 'people',
    piezo: 'sensors', sensor: 'sensors', other: 'sensors', 'water-trouble': 'water', hpgr: 'tech', fire: 'tech' };

  /* the label of a line: its state and the reason (first unit of the line that deviates) */
  const UNITS = n => [`sag-${n}`, `pebble-${n}`, `ball-${n}a`, `ball-${n}b`, `cyclones-${n}`, `rougher-${n}`, `cleaner-${n}`, `flot-${n}`, `thick-${n}`, `filter-${n}`];
  const unitReason = u => {
    const s = AKT.st(u), w = AKT.stRu(s, u);
    if (/^pebble/.test(u)) return `дробление гали ${w}${AKT.num(u, 'load_pct') != null ? ` (${fmt(AKT.num(u, 'load_pct'))}${NB}%)` : ''}`;
    if (/^filter/.test(u)) return s === 'ONE' ? 'фильтр: один пресс из двух' : `фильтр ${w}`;
    if (/^sag/.test(u)) return `мельница SAG ${w}`;
    if (/^ball/.test(u)) return `шаровая мельница ${w}`;
    return `${AKT.nameRu(u).toLowerCase()} ${w}`;
  };
  AKT.lineReason = n => {
    const u = UNITS(n).find(x => AKT.things[x] && AKT.cls(AKT.st(x)) !== 'st-grey');
    return u ? { text: unitReason(u), unit: u, lv: AKT.cls(AKT.st(u)) === 'st-red' ? 1 : 2 } : null;
  };
  const lineText = n => {
    const ln = `line-${n}`, lv = AKT.levelOf(ln), r = AKT.lineReason(n);
    const st = AKT.st(ln);
    const dev = st && !['RUN', 'NORMAL'].includes(st);
    return `${G(lv)}Линия ${n}${dev ? ' ' + AKT.stOf(ln) : ''}${dev && r ? ' — ' + r.text : ''} · ${AKT.vsBase(ln, 'tph', fmt, 50)}${NB}т/ч`;
  };
  const stw = (n, normal) => { const s = AKT.st(n); return s && !(normal || ['RUN', 'NORMAL']).includes(s) ? ` ${AKT.stRu(s, n)}` : ''; };
  const LABELS = [
    { id: 'line-1', x: -250, y: 2650, anchor: 'end', to: 'line-1', text: () => lineText(1), title: () => `Линия 1: ${AKT.stOf('line-1')} · ${fmt(AKT.num('line-1', 'tph'))} т/ч руды · ${f1(AKT.num('line-1', 'cu_tph'))} т/ч меди · извлечение ${f1(AKT.num('line-1', 'recovery'))} %`, st: 'line-1', prio: 1 },
    { id: 'line-2', x: 2500, y: 650, to: 'line-2', text: () => lineText(2), title: () => `Линия 2: ${AKT.stOf('line-2')} · ${fmt(AKT.num('line-2', 'tph'))} т/ч руды · ${f1(AKT.num('line-2', 'cu_tph'))} т/ч меди · извлечение ${f1(AKT.num('line-2', 'recovery'))} %`, st: 'line-2', prio: 1 },
    { id: 'crusher-1', x: 3800, y: 1800, to: 'crusher-1', text: () => `${G(AKT.levelOf('crusher-1'))}Дробилка ЦПД-1${stw('crusher-1')} · ${AKT.vsBase('crusher-1', 'tph', fmt, 50)}${NB}т/ч`, title: () => `Дробилка ЦПД-1 у карьера (ЦПД): ${AKT.stOf('crusher-1')} · ${fmt(AKT.num('crusher-1', 'tph'))} т/ч · давление масла ${fmt(AKT.num('crusher-1', 'lube_kpa'))} кПа`, st: 'crusher-1', prio: 2 },
    { id: 'crusher-2', x: 3800, y: 1150, to: 'crusher-2', text: () => `${G(AKT.levelOf('crusher-2'))}Дробилка ЦПД-2${stw('crusher-2')} · ${AKT.vsBase('crusher-2', 'tph', fmt, 50)}${NB}т/ч`, title: () => `Дробилка ЦПД-2 (место — схема): ${AKT.stOf('crusher-2')} · ${fmt(AKT.num('crusher-2', 'tph'))} т/ч · давление масла ${fmt(AKT.num('crusher-2', 'lube_kpa'))} кПа`, st: 'crusher-2', prio: 2 },
    { id: 'power', x: -250, y: 2150, anchor: 'end', to: 'power', text: () => powerText(), title: () => `ЛЭП 220 кВ и подстанция: площадка берёт ${fmt(AKT.num('power', 'site_mw'))} из ${fmt(AKT.num('power', 'grid_limit_mw'))} МВт · мельницы ${f1(AKT.num('power', 'grinding_mw'))} · прочее ${f1(AKT.num('power', 'other_mw'))} · запас ${f1(AKT.num('power', 'headroom_mw'))} МВт`, st: 'power', prio: 2 },
    { id: 'stockpile-1', x: -250, y: 2400, anchor: 'end', to: 'stockpile-1', text: () => stockText('stockpile-1'), title: () => stockTitle('stockpile-1'), st: 'stockpile-1', prio: 3 },
    { id: 'stockpile-2', x: 2500, y: 900, to: 'stockpile-2', text: () => stockText('stockpile-2'), title: () => stockTitle('stockpile-2'), st: 'stockpile-2', prio: 3 },
    { id: 'conveyor-1', x: -250, y: 1900, anchor: 'end', to: [1500, 1245], text: () => beltText('conveyor-1'), title: () => `Конвейер 1: ${AKT.stOf('conveyor-1')} · ${fmt(AKT.num('conveyor-1', 'tph'))} т/ч`, st: 'conveyor-1', prio: 4 },
    { id: 'conveyor-2', x: 3900, y: 1450, to: [2900, 1250], text: () => beltText('conveyor-2'), title: () => `Конвейер 2: ${AKT.stOf('conveyor-2')} · ${fmt(AKT.num('conveyor-2', 'tph'))} т/ч`, st: 'conveyor-2', prio: 4 },
    { id: 'pit', x: 2300, y: 4750, to: [3000, 4400], text: () => `${G(AKT.levelOf('pit'))}Карьер${stw('pit')} · ${fmt(AKT.num('pit', 'mining_tph'))}${NB}т/ч`, title: () => `Карьер: ${AKT.stOf('pit')} · добыча ${fmt(AKT.num('pit', 'mining_tph'))} т/ч · следующий блок ${AKT.val('pit', 'next_block') || '—'} · ${AKT.planRu(AKT.val('pit', 'plan_text') || '')}`, st: 'pit', prio: 5 },
    { id: 'fleet', x: 3466, y: 2150, anchor: 'middle', text: () => fleetText(), title: () => fleetTitle(), st: 'fleet', prio: 6 },
    { id: 'exc-1', x: 900, y: 3650, to: 'exc-1', text: () => excText('exc-1'), title: () => excTitle('exc-1'), st: 'exc-1', prio: 6 },
    { id: 'exc-2', x: 4950, y: 4300, to: 'exc-2', text: () => excText('exc-2'), title: () => excTitle('exc-2'), st: 'exc-2', prio: 6 },
    { id: 'exc-3', x: 4950, y: 2650, to: 'exc-3', text: () => excText('exc-3'), title: () => excTitle('exc-3'), st: 'exc-3', prio: 6 },
    { id: 'exc-4', x: 5000, y: 3900, to: 'exc-4', text: () => excText('exc-4'), title: () => excTitle('exc-4'), st: 'exc-4', prio: 6 },
    { id: 'exc-5', x: 5000, y: 3150, to: 'exc-5', text: () => excText('exc-5'), title: () => excTitle('exc-5'), st: 'exc-5', prio: 6 },
    { id: 'conc-stock', x: 900, y: 60, to: 'conc-stock', text: () => `${G(AKT.levelOf('conc-stock'))}Концентрат · ${AKT.vsBase('conc-stock', 'stock_t', fmt, 50)}${NB}т`, title: () => `Склад концентрата (место — схема): ${AKT.stOf('conc-stock')} · ${fmt(AKT.num('conc-stock', 'stock_t'))} из ${fmt(AKT.pass('conc-stock', 'capacity_t'))} т · приход ${f1(AKT.num('conc-stock', 'in_tph'))} т/ч · отгрузка поездом в 06:00 и 18:00`, st: 'conc-stock', prio: 7 },
    { id: 'leach-1', x: -1500, y: 700, anchor: 'middle', to: 'leach-1', text: () => oxText(), title: () => oxTitle(), st: 'leach-1', prio: 9 },
    { id: 'water', x: 600, y: -1300, to: [1215, -1024], text: () => waterText(), title: () => waterTitle(), st: 'water', prio: 8 },
    { id: 'intake', x: -250, y: 3150, anchor: 'end', layer: 'water', text: () => `водовод ≈ 27${NB}км → скважины · ${AKT.vsBase('water', 'intake_m3h', fmt, 50)}${NB}м³/ч`, title: () => `Водовод ≈ 27 км от скважин (схема): забор свежей воды ${fmt(AKT.num('water', 'intake_m3h'))} м³/ч`, href: '?view=unit&id=kz.aktogay:water', prio: 9 },
  ];
  /* oxide line (heap leach -> SX-EW): the place is a scheme; the label appears only when the pad is cold (UI rule 1), the marker stays */
  const oxText = () => AKT.thing('leach-1') && AKT.st('leach-1') === 'COLD' ? `${G(AKT.levelOf('leach-1'))}Куча: холодное выщелачивание · катод ${f2(AKT.num('sxew-1', 'cathode_tph'))}${NB}т/ч` : '';
  const oxTitle = () => `Окисленная руда: куча выщелачивания → SX-EW → катод (место — схема): ${AKT.stOf('leach-1')} · катод ${f2(AKT.num('sxew-1', 'cathode_tph'))} т/ч при уровне квартала ${f2(AKT.num('sxew-1', 'cathode_level_tph'))} т/ч (квартальный выпуск по отчётам, не замер)`;
  const excText = n => AKT.thing(n) && AKT.deviates(n) ? `${G(AKT.levelOf(n))}Экскаватор ${n.slice(-1)} ${AKT.stOf(n)}` : '';
  const excTitle = n => { const b = AKT.val(n, 'block'); return `${AKT.nameRu(n)} (место — схема): ${AKT.stOf(n)} · ${fmt(AKT.num(n, 'tph'))} т/ч${b ? ' · партия ' + AKT.batchNo(String(b)) : ''}${AKT.val(n, 'bench') != null ? ' · уступ ' + fmt(AKT.num(n, 'bench')) : ''}`; };
  const beltText = n => AKT.stopped(AKT.st(n)) || AKT.levelOf(n) ? `${G(AKT.levelOf(n) || 1)}Конвейер ${n.slice(-1)} ${AKT.stOf(n)} · ${AKT.vsBase(n, 'tph', fmt, 50)}${NB}т/ч` : '';
  const stockText = n => {
    const h = AKT.hoursLeft(n);
    return `${G(AKT.levelOf(n))}Склад ${n.slice(-1)}${stw(n)} · ${AKT.vsBase(n, 'level_t', fmt, 200)}${NB}т${h != null && h <= 48 ? ' · хватит на ' + AKT.durH(h) : ''}`;
  };
  const stockTitle = n => {
    const h = AKT.hoursLeft(n);
    return `Склад руды ${n.slice(-1)} (место — схема): ${AKT.stOf(n)} · ${fmt(AKT.num(n, 'level_t'))} т · приход ${fmt(AKT.num(n, 'in_tph'))} · расход ${fmt(AKT.num(n, 'out_tph'))} т/ч · ${h != null && h >= 0 && h <= 48 ? 'кончится через ' + AKT.durH(h) : AKT.stockNote(n).text}`;
  };
  const powerText = () => {
    const lim = AKT.num('power', 'grid_limit_mw'), shed = AKT.num('power', 'shed_mw');
    return `${G(AKT.levelOf('power'))}ЛЭП · ${AKT.vsBase('power', 'site_mw', fmt, 2)} из ${fmt(lim)}${NB}МВт${shed ? ' · отключено ' + fmt(shed) : ''}${AKT.st('power') === 'LIMITED' ? ' · лимит сети' : ''}`;
  };
  /* machines in repair: one summary at the fleet instead of red icons */
  const repairs = () => {
    const by = {};
    for (const n of Object.keys(AKT.things)) {
      const c = AKT.cat(n);
      if (!AKT.MACHINE_CATS.has(c) || !AKT.stopped(AKT.st(n))) continue;
      (by[c] = by[c] || []).push(n);
    }
    return by;
  };
  const MACH_RU = { truck: ['самосвал', 'самосвала', 'самосвалов'], drill: ['буровой', 'буровых', 'буровых'], dozer: ['бульдозер', 'бульдозера', 'бульдозеров'], exc: ['экскаватор', 'экскаватора', 'экскаваторов'] };
  const plural = (n, w) => { const m = n % 10, h = n % 100; return w[(m === 1 && h !== 11) ? 0 : (m >= 2 && m <= 4 && (h < 12 || h > 14)) ? 1 : 2]; };
  const fleetText = () => {
    const r = repairs(), parts = ['truck', 'drill', 'dozer', 'exc'].filter(c => r[c]).map(c => `${fmt(r[c].length)} ${plural(r[c].length, MACH_RU[c])}`);
    return `самосвалы ${fmt(AKT.num('fleet', 'trucks_ready'))} из ${fmt(AKT.num('fleet', 'trucks_total'))}${parts.length ? ' · ◆ в ремонте: ' + parts.join(', ') : ''}`;
  };
  const fleetTitle = () => {
    const r = repairs();
    const list = Object.keys(r).map(c => `${AKT.CAT_RU[c]}: ${r[c].map(AKT.shortName).join(', ')}`).join('; ');
    return `Парк карьера: самосвалов готово ${fmt(AKT.num('fleet', 'trucks_ready'))} из ${fmt(AKT.num('fleet', 'trucks_total'))} · вывозка ${fmt(AKT.num('fleet', 'haul_tph'))} т/ч · экскаваторов ${fmt(AKT.num('fleet', 'exc_ready'))} из ${fmt(AKT.num('fleet', 'exc_total'))}${list ? ' · в ремонте — ' + list : ''} · места машин на дорогах — схема движения`;
  };
  const waterTroubles = () => {
    const things = Object.keys(AKT.things).filter(n => AKT.cat(n) === 'water-trouble' && AKT.st(n) && !['NORMAL', 'OK', 'RUN', 'RESOLVED'].includes(AKT.st(n)));
    const issues = AKT.issues().filter(n => /water|pipe|intake|pond|piezo|dam/.test(String(AKT.val(n, 'kind') || '')));
    return { things, issues };
  };
  const waterText = () => {
    const w = waterTroubles(), n = w.things.length + w.issues.length;
    const lv = AKT.levelOf('water') || (n ? 2 : 0);
    return `${G(lv)}Хвостохранилище${stw('water')} · ${f2((AKT.num('water', 'pond_m3') || 0) / 1e6)}${NB}млн${NB}м³ (д)${n ? ` · вода: ${n === 1 ? (w.things[0] ? AKT.stOf(w.things[0]) : AKT.kindRu(AKT.val(w.issues[0], 'kind'))) : n + ' беды'}` : ''}`;
  };
  const waterTitle = () => {
    const w = waterTroubles();
    const parts = w.things.map(n => `${AKT.nameRu(n)}: ${AKT.stOf(n)}`).concat(w.issues.map(n => `${AKT.issueTag(n)}: ${AKT.kindRu(AKT.val(n, 'kind'))}`));
    return `Хвостохранилище и вода: ${AKT.stOf('water')} · пруд ${f2((AKT.num('water', 'pond_m3') || 0) / 1e6)} млн м³ · оборотная вода ${fmt(AKT.num('water', 'recycle_m3h'))} м³/ч · забор ${fmt(AKT.num('water', 'intake_m3h'))} м³/ч · давление в дамбе ${fmt(AKT.num('water', 'piezo_kpa'))} кПа${parts.length ? ' · ' + parts.join('; ') : ''}`;
  };
  const XGLYPH = { person: 'person', crew: 'person', piezo: 'piezo', sensor: 'sensor', truck: 'truck', exc: 'exc', face: 'face',
    dozer: 'dozer', drill: 'drill', road: 'dot', hpgr: 'box', 'water-trouble': 'drop', fire: 'fire', other: 'idot', known: 'dot' };
  const XLETTER = { piezo: 'П', 'water-trouble': 'В', fire: '!', hpgr: 'H', sensor: '' };
  const mainNums = (n, max) => {
    const t = AKT.thing(n); if (!t) return [];
    return Object.keys(t.features || {}).filter(f => !['sim_time', 'idSimulationRun', 'x', 'y', 'x_m', 'y_m', 'pos_x', 'pos_y', 'lat', 'lon', 'heartbeat', 'seq', 'alarm', 'age_min', 'total_t'].includes(f))
      .filter(f => typeof AKT.raw(n, f) === 'number' && AKT.raw(n, f) !== -1).slice(0, max || 4)
      .map(f => ({ f, text: `${AKT.featRu(n, f)} ${AKT.valText(n, f)}`, short: AKT.valText(n, f) }));
  };
  /* the one short value next to an instrument */
  const shortVal = n => {
    const c = AKT.cat(n);
    if (c === 'piezo') return `${AKT.nameRu(n).replace(/^Пьезометр дамбы /, '')} · ${fmt(AKT.num(n, 'kpa'))} кПа${AKT.num(n, 'sp_kpa') ? ' (тревога от ' + fmt(AKT.num(n, 'sp_kpa')) + ')' : ''}`;
    const nums = mainNums(n, 1);
    return nums.length ? nums[0].short : (AKT.st(n) ? AKT.stOf(n) : '');
  };

  const LABEL_CANDS = (() => {
    const out = [];
    for (const dx of [0, -60, 60, -120, 120, -200, 200]) for (let i = 0; i <= 9; i++) for (const s of (i ? [-1, 1] : [1])) out.push([dx, s * i * 16]);
    return out.sort((a, b) => (Math.abs(a[1]) + 0.6 * Math.abs(a[0])) - (Math.abs(b[1]) + 0.6 * Math.abs(b[0])));
  })();
  const CALLOUT_CANDS = (() => {
    const out = [];
    for (const dx of [30, -30, 60, -60, 100, -100, 160, -160, 220, -220]) for (const dy of [-50, 30, -80, 60, -110, 90, -140, 120, 0]) out.push([dx, dy]);
    return out.sort((a, b) => Math.hypot(a[0], a[1] * 1.3) - Math.hypot(b[0], b[1] * 1.3));
  })();
  const RING = (() => {
    const out = [];
    for (let dx = -72; dx <= 72; dx += 18) for (let dy = -72; dy <= 72; dy += 18) out.push([dx, dy]);
    return out.sort((a, b) => Math.hypot(a[0], a[1]) - Math.hypot(b[0], b[1]));
  })();
  const LAYER_CANDS = (() => {
    const out = [[22, -46], [22, 8], [-160, -46], [-160, 8], [22, -100], [-160, -100], [22, 60], [-60, 40], [-60, -130]];
    const grid = [];
    for (let dx = -320; dx <= 240; dx += 40) for (let dy = -220; dy <= 200; dy += 20) grid.push([dx, dy]);
    grid.sort((a, b) => Math.hypot(a[0] + 40, a[1] + 20) - Math.hypot(b[0] + 40, b[1] + 20));
    return out.concat(grid);
  })();
  /* a stable pseudo-random number per name (truck phases) */
  const hash = s => { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return ((h >>> 0) % 10000) / 10000; };

  const view = {
    plan: null, svg: null, k: 0.06, vb: { x: 0, y: 0, w: 1, h: 1 }, px: [], labels: {}, nodes: {}, belts: {}, chev: [],
    batches: {}, issues: {}, crews: {}, layers: {}, ins: {}, extras: {}, roads: {}, people: {}, trucks: {}, rings: {}, ro: null, hlTimer: null, satMeta: null,
    lyr: {}, raf: 0, lastTs: 0, callout: null,

    async build(stage, opts) {
      stage.innerHTML = '';
      if (opts && opts.note) { const n = document.createElement('div'); n.className = 'fallback-note'; n.setAttribute('role', 'status'); n.textContent = opts.note; stage.appendChild(n); }
      this.lyr = loadLayers();
      const bar = document.createElement('div'); bar.id = 'plan-bar';
      bar.innerHTML = `<span class="grp" role="group" aria-label="Подложка"><button type="button" id="lay-scheme" aria-pressed="true">Схема</button><button type="button" id="lay-sat" aria-pressed="false">Спутник</button><button type="button" id="lay-3d" aria-pressed="false" title="Открыть диораму: весь рудник макетом в 3D">3D</button></span>
<span class="lyr-l">Слои:</span><span class="grp" role="group" aria-label="Слои карты">${LAYERS.map(([k, t]) => `<button type="button" data-lyr="${k}" aria-pressed="false" title="Показать ${t.toLowerCase()} на карте; отклонения видны всегда">${t}</button>`).join('')}</span>
<span class="key" aria-label="Знаки"><span><span class="lv lv-2">▲</span> отклонение</span><span><span class="lv lv-1">◆</span> стоит / опасно</span><span><span class="lv lv-3">△</span> скоро</span><span><span class="rk" style="font-size:12px">1</span> беда</span><span>≈ расчёт модели</span><a href="${AKT.href('?view=legend')}">Легенда</a></span>`;
      stage.appendChild(bar);
      const wrap = document.createElement('div'); wrap.id = 'plan-wrap'; stage.appendChild(wrap);
      if (!this.plan) this.plan = await AKT.loadPlan();
      this.px = []; this.labels = {}; this.nodes = {}; this.belts = {}; this.chev = []; this.batches = {}; this.issues = {}; this.crews = {}; this.layers = {};
      this.ins = {}; this.extras = {}; this.roads = {}; this.people = {}; this.trucks = {}; this.rings = {}; this.callout = null;
      this.draw(wrap);
      this.resize();
      bar.querySelector('#lay-scheme').addEventListener('click', () => this.setLayer('scheme'));
      bar.querySelector('#lay-sat').addEventListener('click', () => this.setLayer('sat'));
      bar.querySelector('#lay-3d').addEventListener('click', () => { location.search = AKT.href('?view=diorama').slice(1); });
      bar.querySelectorAll('[data-lyr]').forEach(b => b.addEventListener('click', () => {
        const k = b.dataset.lyr; this.lyr[k] = !this.on(k);
        AKT.store.set('akt-layers', JSON.stringify(this.lyr));
        this.update();
      }));
      let want = AKT.params.get('layer');
      if (!want) want = AKT.store.get('akt-plan-layer');
      await this.setLayer(want === 'sat' ? 'sat' : 'scheme', true);
      this.ro = new ResizeObserver(() => { this.resize(); this.update(); });
      this.ro.observe(wrap);
      this.onVis = () => { if (!document.hidden) this.startLoop(); };
      document.addEventListener('visibilitychange', this.onVis);
      this.startLoop();
    },
    destroy() {
      if (this.ro) this.ro.disconnect(); this.ro = null;
      if (this.raf) cancelAnimationFrame(this.raf); this.raf = 0;
      if (this.onVis) document.removeEventListener('visibilitychange', this.onVis);
    },
    /* layer on: the viewer's choice; «Люди» by default while someone is called or on the way */
    on(k) {
      if (k in this.lyr) return !!this.lyr[k];
      if (k === 'people') return AKT.persons().some(n => /TRAVEL|CALLED|WORK|BUSY/.test(AKT.st(n))) || AKT.ofType('crew').some(n => !['FREE', 'OFF', ''].includes(AKT.st(n)));
      return false;
    },

    async setLayer(layer, initial) {
      const sat = layer === 'sat';
      if (sat && !this.satMeta) {
        try { this.satMeta = await AKT.get('/sat/aktogay_s2.json'); }
        catch (e) { document.getElementById('err').textContent = 'снимок недоступен: ' + e.message; return; }
      }
      if (sat && !this.satImg.getAttribute('href')) {
        const s = this.satMeta.svg_image;
        for (const k of ['x', 'y', 'width', 'height']) this.satImg.setAttribute(k, s[k]);
        this.satImg.setAttribute('href', 'sat/' + this.satMeta.image);
        const d = this.satMeta.scene && this.satMeta.scene.acquisition_date;
        this.attrSat.textContent = `${this.satMeta.licence.attribution}${d ? ' · снимок Sentinel-2 ' + d.split('-').reverse().join('.') : ''}`;
        this.attrSatLink.setAttribute('href', this.satMeta.licence.terms_url);
      }
      this.svg.classList.toggle('sat', sat);
      document.getElementById('lay-scheme').setAttribute('aria-pressed', String(!sat));
      document.getElementById('lay-sat').setAttribute('aria-pressed', String(sat));
      this.attrSatLink.style.display = sat ? '' : 'none';
      if (!initial) AKT.store.set('akt-plan-layer', layer);
      this.fitAttr();
      this.layout();
    },

    anchor(name) {
      const ui = AKT.attr(name, 'ui.plan');
      if (ui && typeof ui.x === 'number') return [ui.x, ui.y];
      const a = this.plan.anchors[name];
      if (a) return a.xy ? a.xy : (a.path ? a.path[Math.floor(a.path.length / 2)] : null);
      return AKT.pos(name);
    },
    pxg(parent, x, y, cls, rot) {
      const g = E('g', { class: cls || '' }, parent);
      const rec = { g, x, y, rot: rot || 0, base: [0, 0], dx: 0, dy: 0 };
      this.px.push(rec);
      return rec;
    },
    place(rec) {
      const ox = rec.base[0] + rec.dx, oy = rec.base[1] + rec.dy;
      rec.g.setAttribute('transform', `translate(${rec.x},${-rec.y}) scale(${1 / this.k})${rec.rot ? ` rotate(${rec.rot})` : ''}${ox || oy ? ` translate(${ox},${oy})` : ''}`);
    },
    drop(rec) { rec.g.remove(); this.px = this.px.filter(r => r !== rec); },
    toPx(x, y) { return [(x - this.vb.x) * this.k, (-y - this.vb.y) * this.k]; },
    toM(px, py) { return [this.vb.x + px / this.k, -(this.vb.y + py / this.k)]; },

    draw(wrap) {
      const plan = this.plan, L = plan.layers;
      const svg = this.svg = E('svg', { class: 'plan', role: 'img', 'aria-labelledby': 'map-t map-d' }, wrap);
      E('title', { id: 'map-t' }, svg).textContent = 'План площадки Актогай';
      this.desc = E('desc', { id: 'map-d' }, svg);
      this.satImg = E('image', { class: 'sat', preserveAspectRatio: 'none' }, svg);
      const base = E('g', { class: 'base' }, svg);
      const poly = (items, cls) => items.forEach(it => E('polygon', { points: P(it.pts), class: cls }, base));
      const line = (items, cls) => items.forEach(it => E('polyline', { points: P(it.pts), class: cls }, base));
      poly(L.mine, 'mine'); poly(L.landfill, 'landfill'); poly(L.industrial, 'industrial');
      L.tailings.forEach(it => E('polygon', { points: P(it.pts), class: 'tailings', id: it.id === 'way/773805070' ? 'pond-near' : null }, base));
      poly(L.water, 'water'); poly(L.reservoir, 'water');
      L.quarry.forEach(it => {
        E('polygon', { points: P(it.pts), class: 'quarry' }, base);
        if (it.id !== 'way/773805067') return;
        const cx = it.pts.reduce((s, p) => s + p[0], 0) / it.pts.length, cy = it.pts.reduce((s, p) => s + p[1], 0) / it.pts.length;
        for (const f of [0.74, 0.5, 0.27]) E('polygon', { points: P(it.pts.map(p => [cx + (p[0] - cx) * f, cy + (p[1] - cy) * f])), class: 'bench' }, base);
      });
      line(L.road, 'road'); line(L.road2, 'road'); line(L.rail, 'rail'); line(L.power_line, 'power_line'); line(L.pipeline, 'pipeline');
      poly(L.house, 'house'); poly(L.building, 'building'); poly(L.substation, 'substation');
      /* haul roads of the pit (scheme): trucks move along them */
      for (const r of ['ramp-1', 'ramp-2', 'road-dump']) if (plan.anchors[r] && plan.anchors[r].path) E('polyline', { points: P(plan.anchors[r].path), class: 'haul' }, base);
      /* water main to the wells (scheme): far off the plan, a grey dashed line */
      this.intakeLine = E('polyline', { points: P([[-600, 1250], [-2200, 2200], [-4100, 3000]]), class: 'intake' }, base);
      const defs = E('defs', null, svg);
      const mw = E('marker', { id: 'way-arrow', viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 6, markerHeight: 6, orient: 'auto', markerUnits: 'strokeWidth' }, defs);
      E('path', { d: 'M0,0 L10,5 L0,10 z', fill: '#454b53' }, mw);

      /* the way of trouble ①: a halo under the belts of its chain */
      this.gChain = E('g', { class: 'chain' }, svg);
      const flows = E('g', { class: 'flows' }, svg);
      const addBelt = (n, path, extra) => {
        const halo = E('polyline', { points: P(path), class: 'chain-halo', style: 'display:none' }, this.gChain);
        const belt = E('polyline', { points: P(path), class: 'belt', id: 'belt-' + n }, flows);
        const dash = E('polyline', { points: P(path), class: 'belt-dash', id: 'dash-' + n }, flows);
        this.belts[n] = Object.assign({ belt, dash, halo, path, len: pathLen(path), chev: [], off: 0, v: 0 }, extra || {});
      };
      for (const n of ['conveyor-1', 'conveyor-2']) {
        addBelt(n, plan.anchors[n].path);
        for (const f of [0.25, 0.5, 0.75]) {
          const [x, y, ang] = pointAt(plan.anchors[n].path, f);
          const rec = this.pxg(flows, x, y, 'chev-g', -ang);
          this.belts[n].chev.push(E('polygon', { points: '-5,-5 5,0 -5,5', class: 'chev' }, rec.g));
        }
      }
      for (const n of ['stockpile-1', 'stockpile-2']) addBelt(n, plan.anchors[n].to_sag, { sag: 'sag-' + n.slice(-1) });

      /* ore on the haul roads: dashes run along the road, the width follows t/h of the pit (ramps) or of the waste (dump road) */
      this.hauls = {};
      for (const r of ['ramp-1', 'ramp-2', 'road-dump']) if (plan.anchors[r] && plan.anchors[r].path) {
        const dash = E('polyline', { points: P(plan.anchors[r].path), class: 'haul-flow', id: 'haulflow-' + r }, flows);
        this.hauls[r] = { dash, off: 0, v: 0 };
      }
      const scheme = E('g', { class: 'scheme' }, svg);
      for (const n of ['stockpile-1', 'stockpile-2']) {
        const [x, y] = this.anchor(n);
        E('circle', { cx: x, cy: -y, r: 170, class: 'stock-outline', id: 'stock-out-' + n }, scheme);
        this.nodes[n] = E('circle', { cx: x, cy: -y, r: 100, class: 'stock-fill', id: 'stock-fill-' + n }, scheme);
      }
      /* level rings around the nodes of open issues (under the markers) */
      this.gRings = E('g', { class: 'rings' }, svg);
      this.markers = [];
      const marker = (n, w, h, shape) => {
        const a = this.anchor(n); if (!a) return;
        const rec = this.pxg(scheme, a[0], a[1], 'node-g');
        const link = E('a', { href: `?view=unit&id=${AKT.id(n)}` }, rec.g);
        let el;
        if (shape === 'tri') el = E('polygon', { points: `0,${-h / 2} ${w / 2},${h / 2} ${-w / 2},${h / 2}`, class: 'node', id: 'node-' + n }, link);
        else el = E('rect', { x: -w / 2, y: -h / 2, width: w, height: h, class: 'node', id: 'node-' + n, rx: 2 }, link);
        E('title', null, el).textContent = AKT.nameRu(n) || n;
        this.nodes[n] = el;
        rec.name = n;
        this.markers.push(rec);
        return rec;
      };
      marker('crusher-1', 16, 11); marker('crusher-2', 16, 11); marker('line-1', 22, 22); marker('line-2', 22, 22);
      marker('conc-stock', 16, 11); marker('power', 12, 12); marker('leach-1', 11, 8); marker('sxew-1', 11, 8);
      for (const n of Array.from(new Set(['exc-1', 'exc-2', 'exc-3'].concat(AKT.ofType('exc')))))
        if (plan.anchors[n] || AKT.attr(n, 'ui.plan')) { const r = marker(n, 13, 11, 'tri'); if (r) r.layer = 'tech'; }
      this.gRoads = E('g', { class: 'xroads' }, svg);
      this.gTravel = E('g', { class: 'ways' }, svg);
      this.gLeaders = E('g', { class: 'leaders' }, svg);
      this.gTrucks = E('g', { class: 'trucks' }, svg);
      this.gExtra = E('g', { class: 'extras' }, svg);
      this.gCrew = E('g', { class: 'crews' }, svg);
      this.gBatch = E('g', { class: 'batches' }, svg);
      this.gPeople = E('g', { class: 'people-g' }, svg);
      this.gLayers = E('g', { class: 'layers' }, svg);
      const labels = E('g', { class: 'labels' }, svg);
      for (const lb of LABELS) {
        let to = lb.to;
        if (typeof to === 'string') to = this.anchor(to);
        const leader = to ? E('line', { class: 'leader' }, this.gLeaders) : null;
        const rec = this.pxg(labels, lb.x, lb.y, 'lblg');
        const a = E('a', { href: lb.href || (lb.st ? `?view=unit&id=${AKT.id(lb.st)}` : '?view=plan') }, rec.g);
        const t = T(a, 0, 0, '…', { class: 'lbl', id: 'lbl-' + lb.id, 'text-anchor': lb.anchor || 'start' });
        const tip = E('title', null, a);
        rec.leader = leader; rec.to = to;
        this.labels[lb.id] = { el: t, tip, def: lb, rec, a };
      }
      this.gIssue = E('g', { class: 'issues' }, svg);
      this.gCallout = E('g', { class: 'callouts' }, svg);

      this.furn = E('g', { class: 'px' }, svg);
      this.inset = this.pxg(this.furn, 0, 0, 'inset');
      this.buildInset(this.inset.g);
      this.scale = this.pxg(this.furn, 0, 0, 'scale');
      E('polyline', { points: '0,0 0,6 1000,6 1000,0', class: 'scalebar', id: 'scalebar' }, this.scale.g);
      T(this.scale.g, 0, -3, '1 км', { class: 'small' });
      this.north = this.pxg(this.furn, 0, 0, 'north');
      E('polygon', { points: '0,-14 6,6 0,2 -6,6', fill: '#16191d' }, this.north.g);
      T(this.north.g, 0, 20, 'С', { 'text-anchor': 'middle', 'font-weight': '700' });
      this.attr = this.pxg(this.furn, 0, 0, 'attr');
      E('rect', { class: 'attr-bg', x: 0, y: 0, width: 0, height: 0, rx: 2 }, this.attr.g);
      const al = E('a', { href: plan.license_url, target: '_blank', rel: 'license noopener' }, this.attr.g);
      T(al, 0, 0, `${plan.attribution}, ODbL`, { class: 'small', 'text-decoration': 'underline', 'text-anchor': 'end' });
      this.attrSatLink = E('a', { target: '_blank', rel: 'license noopener', style: 'display:none' }, this.attr.g);
      this.attrSat = T(this.attrSatLink, 0, -16, '', { class: 'small', 'text-decoration': 'underline', 'text-anchor': 'end' });
    },
    fitAttr() {
      try {
        const bg = this.attr.g.querySelector('.attr-bg');
        bg.setAttribute('width', 0);
        const b = this.attr.g.getBBox();
        bg.setAttribute('x', b.x - 3); bg.setAttribute('y', b.y - 1); bg.setAttribute('width', b.width + 6); bg.setAttribute('height', b.height + 2);
      } catch (e) { /* not rendered */ }
    },

    /* the plant inset: «Фабрика», two lines and the concentrate; the units behind «подробно» */
    buildInset(g) {
      const rows = [];
      this.insetBg = E('rect', { x: 0, y: 0, width: 330, height: 10, class: 'inset-bg', rx: 3 }, g);
      const row = (key, text, opts) => {
        opts = opts || {};
        const a = opts.href ? E('a', { href: opts.href }, g) : E('g', null, g);
        let sq = null;
        if (opts.sq) { sq = E('rect', { x: 8, y: -10, width: 9, height: 9, class: 'sq', id: 'ins-sq-' + key }, a); this.ins['sq-' + key] = sq; }
        const t = T(a, opts.sq ? 22 : (opts.indent ? 22 : 8), 0, text, { class: opts.cls || '', id: 'ins-' + key });
        E('title', null, a);
        this.ins[key] = t; rows.push({ key, g: a, t, sq, detail: !!opts.detail, opt: !!opts.opt });
        return t;
      };
      row('title', 'Фабрика', { cls: 'inset-title', href: '?view=line1' });
      for (const n of [1, 2]) {
        row(`line-${n}`, `Линия ${n}`, { cls: 'inset-title', href: `?view=line${n}`, sq: true });
        row(`why-${n}`, '', { href: `?view=line${n}`, indent: true, opt: true });
        row(`sag-${n}`, `SAG-${n}`, { sq: true, href: `?view=unit&id=kz.aktogay:sag-${n}`, detail: true });
        row(`mill-${n}`, 'дробление гали', { sq: true, href: `?view=unit&id=kz.aktogay:pebble-${n}`, detail: true });
        row(`flot-${n}`, `флотация ${n}`, { sq: true, href: `?view=unit&id=kz.aktogay:flot-${n}`, detail: true });
        row(`conc-${n}`, 'сгуститель', { sq: true, href: `?view=unit&id=kz.aktogay:thick-${n}`, detail: true });
        row(`insag-${n}`, 'в мельнице', { href: '?view=ore', detail: true, indent: true });
      }
      row('conc-stock', 'Концентрат', { sq: true, href: '?view=unit&id=kz.aktogay:conc-stock' });
      this.insetRows = rows;
      this.insetBtn = E('g', { class: 'inset-btn', role: 'button', tabindex: 0 }, g);
      this.insetBtnT = T(this.insetBtn, 0, 0, '', { class: 'small', 'text-anchor': 'end' });
      const toggle = () => { this.insetFull = !this.insetFull; AKT.store.set('akt-inset-full', this.insetFull ? '1' : '0'); this.resize(); this.update(); };
      this.insetBtn.addEventListener('click', toggle);
      this.insetBtn.addEventListener('keydown', ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); toggle(); } });
      this.insetFull = AKT.store.get('akt-inset-full') === '1';
      this.stackInset();
    },
    stackInset() {
      const full = !!this.insetFull;
      /* rows follow the type size (0.86rem: 12 px at 1280, 14.5 px at 1920) */
      const fs = Math.max(12, 0.86 * (parseFloat(getComputedStyle(document.documentElement).fontSize) || 14));
      const pitch = Math.round(fs * 1.42);
      let y = Math.round(fs * 1.3);
      for (const r of this.insetRows) {
        const show = (full || !r.detail) && !(r.opt && !r.t.textContent);
        r.g.style.display = show ? '' : 'none';
        if (!show) continue;
        r.t.setAttribute('y', y);
        if (r.sq) r.sq.setAttribute('y', y - Math.round(fs * 0.8));
        y += pitch;
      }
      this.insetH = y - Math.round(pitch / 2);
      this.insetBg.setAttribute('height', this.insetH);
      this.insetBtnT.textContent = full ? 'коротко ▴' : 'подробно ▾';
    },
    fitInset() {
      let w = 200;
      for (const r of this.insetRows) { if (r.g.style.display === 'none') continue; try { const b = r.t.getBBox(); w = Math.max(w, b.x + b.width + 8); } catch (e) { /* not rendered */ } }
      try { const tb = this.insetRows[0].t.getBBox(); w = Math.max(w, tb.x + tb.width + 96); } catch (e) { /* not rendered */ }
      this.insetW = Math.min(w, 0.62 * this.cw);
      this.insetBg.setAttribute('width', this.insetW);
      this.insetBtnT.setAttribute('x', this.insetW - 6); this.insetBtnT.setAttribute('y', 16);
    },

    resize() {
      const wrap = this.svg.parentNode;
      const cw = Math.max(200, wrap.clientWidth), ch = Math.max(200, wrap.clientHeight);
      this.cw = cw; this.ch = ch;
      this.stackInset();
      const [x0, y0, x1, y1] = this.plan.view;
      const k = Math.min(cw / (x1 - x0), ch / (y1 - y0));
      this.k = k;
      const w = cw / k, h = ch / k, cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
      this.vb = { x: cx - w / 2, y: -(cy + h / 2), w, h };
      this.svg.setAttribute('viewBox', `${this.vb.x} ${this.vb.y} ${w} ${h}`);
      this.svg.setAttribute('preserveAspectRatio', 'none');
      const pxu = (px, py) => this.toM(px, py);
      [this.inset.x, this.inset.y] = pxu(6, ch - 6 - this.insetH);
      [this.scale.x, this.scale.y] = pxu(cw - 12 - 1000 * k, ch - 8);
      this.scale.g.querySelector('#scalebar').setAttribute('points', `0,0 0,6 ${1000 * k},6 ${1000 * k},0`);
      [this.north.x, this.north.y] = pxu(cw - 24, 26);
      [this.attr.x, this.attr.y] = pxu(cw - 12, ch - 26);
      for (const rec of this.px) this.place(rec);
      this.fitAttr();
      for (const n in this.belts) {
        const b = this.belts[n];
        b.dash.setAttribute('stroke-dasharray', `${5 / k} ${13 / k}`);
      }
      for (const n in this.hauls) this.hauls[n].dash.setAttribute('stroke-dasharray', `${5 / k} ${15 / k}`);
      for (const n in this.trucks) this.trucks[n].el.setAttribute('r', String(this.truckR() / k));
    },
    truckR() { return this.on('tech') ? 4.2 : 2.8; },

    update() {
      if (!this.svg) return;
      const chain = AKT.scenarioChain();
      const top = this.topIssue();
      const topChain = this.chainOf(top);
      this.svg.classList.toggle('lyr-tech', this.on('tech'));
      document.querySelectorAll('#plan-bar [data-lyr]').forEach(b => b.setAttribute('aria-pressed', String(this.on(b.dataset.lyr))));
      /* labels */
      for (const id in this.labels) {
        const { el, tip, def, rec, a } = this.labels[id];
        let text = def.layer && !this.on(def.layer) ? '' : def.text();
        if (el.textContent !== text) el.textContent = text;
        rec.hidden = !text;
        rec.g.style.display = text ? '' : 'none';
        if (!text && rec.leader) rec.leader.style.display = 'none';
        const tt = (def.title ? def.title() : text) + ' · нажмите — карточка';
        if (tip.textContent !== tt) tip.textContent = tt;
        a.setAttribute('aria-label', tt.replace(/≈/g, 'примерно, по расчёту модели,'));
        const lv = def.st ? (def.st === 'fleet' ? (Object.keys(repairs()).length ? 1 : 0) : AKT.levelOf(def.st)) : 0;
        const cls = `lbl ${AKT.lvCls(lv)}${def.st && chain.has(def.st) && AKT.hatchOn() ? ' scen' : ''}`;
        if (el.getAttribute('class') !== cls) el.setAttribute('class', cls);
      }
      for (const id of ['intake']) this.intakeLine.style.display = this.on('water') ? '' : 'none';
      /* node markers */
      for (const n in this.nodes) {
        const el = this.nodes[n];
        if (n.startsWith('stockpile')) {
          const lvl = AKT.num(n, 'level_t'), live = AKT.pass(n, 'live_t') || 40000;
          el.setAttribute('r', String(170 * Math.sqrt(Math.max(0.04, Math.min(1, (lvl || 0) / live)))));
          const out = this.svg.querySelector('#stock-out-' + n);
          const c = 'stock-outline' + (AKT.hatchOn() && chain.has(n) ? ' scen' : '');
          if (out.getAttribute('class') !== c) out.setAttribute('class', c);
          continue;
        }
        const cls = `node ${AKT.levelCls(n)}${AKT.hatchOn() && chain.has(n) ? ' scen' : ''}${AKT.prop && AKT.prop.fresh(n) ? ' scen-new' : ''}`;
        if (el.getAttribute('class') !== cls) el.setAttribute('class', cls);
        if (AKT.type(n) === 'exc') { const tt = excTitle(n) + ' · нажмите — карточка', te = el.querySelector('title'); if (te && te.textContent !== tt) te.textContent = tt; }
      }
      for (const rec of this.markers) if (rec.layer) rec.g.style.display = this.on(rec.layer) || AKT.levelOf(rec.name) ? '' : 'none';
      /* belts: width by t/h, ore speed by t/h, dashed red when stopped, halo on the way of trouble ① */
      for (const n in this.belts) {
        const b = this.belts[n];
        const tph = b.sag ? (AKT.num(n, 'out_tph') ?? AKT.num(b.sag, 'feed_tph')) : AKT.num(n, 'tph');
        const cap = b.sag ? 4880 : (AKT.pass(n, 'capacity_tph') || 4880);
        const st = b.sag ? AKT.st(b.sag) : AKT.st(n);
        const stopped = AKT.stopped(st) || (tph != null && tph < 1);
        const w = stopped ? 1.5 : (2 + 8 * Math.min(1, (tph || 0) / cap));
        b.belt.setAttribute('stroke-width', w);
        /* red where the open troubles lose copper now (the same numbers as «Путь меди») */
        const lossNow = beltLoss(n, b);
        const cls = 'belt' + (stopped ? ' st-red' : '') + (lossNow ? ' loss' : '');
        if (b.belt.getAttribute('class') !== cls) b.belt.setAttribute('class', cls);
        b.dash.style.display = stopped ? 'none' : '';
        b.dash.setAttribute('stroke-width', Math.max(1.5, w * 0.5));
        const dcls = 'belt-dash' + (lossNow && !stopped ? ' loss' : '');
        if (b.dash.getAttribute('class') !== dcls) b.dash.setAttribute('class', dcls);
        b.v = stopped ? 0 : 14 + 46 * Math.min(1.2, (tph || 0) / cap);     // px per second of the ore on the belt
        const inChain = topChain.has(n) || (b.sag && topChain.has(b.sag));
        b.halo.style.display = inChain ? '' : 'none';
        b.halo.setAttribute('stroke-width', w + 10);
        for (const c of b.chev) c.setAttribute('class', 'chev' + (stopped ? ' st-red' : lossNow ? ' loss' : ''));
      }
      /* haul roads: width and speed from the ore of the pit (Ditto), nothing while the excavators stand */
      const lossBy = AKT.troubleLoss ? AKT.troubleLoss().by : {};
      for (const r in this.hauls) {
        const h = this.hauls[r];
        const tph = r === 'road-dump' ? AKT.num('fleet', 'waste_tph') : (AKT.num('crusher-' + r.slice(-1), 'tph') ?? AKT.num('pit', 'mining_tph'));
        const cap = r === 'road-dump' ? 8000 : 4880;
        const idle = tph == null || tph < 1 || AKT.stopped(AKT.st(r));
        h.dash.style.display = idle ? 'none' : '';
        h.dash.setAttribute('stroke-width', (2 + 7 * Math.min(1, (tph || 0) / cap)).toFixed(1));
        h.v = idle ? 0 : 12 + 40 * Math.min(1.2, (tph || 0) / cap);
        const hc = 'haul-flow' + (r !== 'road-dump' && lossBy[r.slice(-1) + ':0'] > 0 ? ' loss' : '');
        if (h.dash.getAttribute('class') !== hc) h.dash.setAttribute('class', hc);
      }
      this.updateCrews(); this.updateBatches(); this.updateIssues(top); this.updateExtras(chain); this.updatePeople(); this.updateTrucks(); this.updateInset(chain);
      this.stackInset();
      this.updateDesc(top);
      this.layout();
      if (!this.raf) this.startLoop();
    },
    /* trouble ①: S0 first, else rank 1 */
    topIssue() {
      const q = AKT.issues();
      return q.find(i => String(AKT.val(i, 'safety_class') || '') === 'S0' && AKT.rankNo(i) != null) || q.find(i => AKT.rankNo(i) != null) || null;
    },
    chainOf(issue) {
      const out = new Set();
      const node = issue ? AKT.issueNode(issue) : '';
      if (!node) return out;
      /* upstream feeders that starve the node, and the node itself */
      out.add(node);
      const q = [node];
      while (q.length) { const n = q.shift(); for (const f of AKT.feeds(n)) if (!out.has(f) && f !== 'conc-stock') { out.add(f); q.push(f); } }
      return out;
    },
    updateDesc(top) {
      const q = AKT.issues();
      const devs = LABELS.filter(l => l.st && l.st !== 'fleet' && AKT.levelOf(l.st)).map(l => l.title().split(' · ')[0]).filter(Boolean);
      const d = (q.length ? 'Беды: ' + q.slice(0, 3).map(i => `${AKT.rankSign(i) || '•'} ${AKT.nameRu(AKT.issueNode(i))} — ${AKT.issuePrice(i)}`).join('; ') + '. ' : 'Бед нет. ')
        + (devs.length ? 'Отклонения: ' + devs.join('; ') + '.' : 'Отклонений нет.');
      if (this.desc.textContent !== d) this.desc.textContent = d;
    },

    nodeXY(node) {
      if (!node) return null;
      return (this.plan.anchors[AKT.nodeKey(node)] || AKT.attr(node, 'ui.plan')) ? this.anchor(AKT.nodeKey(node)) : AKT.pos(node);
    },
    updatePeople() {
      const top = AKT.topCall(), seen = new Set(), on = this.on('people');
      for (const n of AKT.persons()) {
        const info = AKT.personInfo(n);
        const at = this.nodeXY(info.loc) || this.nodeXY(info.home);
        if (!at) continue;
        const show = on || !!info.tr;
        seen.add(n);
        let rec = this.people[n];
        if (!rec) {
          rec = this.pxg(this.gPeople, at[0], at[1], 'pm');
          const a = E('a', { href: `?view=unit&id=${AKT.id(n)}`, 'data-person': n }, rec.g);
          E('circle', { class: 'pm-h', cx: 0, cy: -4.5, r: 3.2 }, a);
          E('path', { class: 'pm-b', d: 'M-5.5,6 C-5.5,-1.5 5.5,-1.5 5.5,6 Z' }, a);
          rec.t = T(a, 8, 4.5, '', { class: 'pm-t' });
          E('title', null, a);
          rec.leader = E('line', { class: 'leader' }, this.gLeaders);
          rec.way = E('polyline', { class: 'way', 'marker-end': 'url(#way-arrow)' }, this.gTravel);
          this.people[n] = rec;
        }
        rec.hidden = !show;
        rec.g.style.display = show ? '' : 'none';
        if (!show) { rec.leader.style.display = 'none'; rec.way.style.display = 'none'; continue; }
        const from0 = info.tr ? this.nodeXY(info.tr.from) : null;
        let pos = at;
        if (from0 && info.tr.eta > info.tr.start && AKT.simTime != null) {
          const f = Math.max(0, Math.min(0.92, (AKT.simTime - info.tr.start) / (info.tr.eta - info.tr.start)));
          pos = [from0[0] + (at[0] - from0[0]) * f, from0[1] + (at[1] - from0[1]) * f];
        }
        rec.x = pos[0]; rec.y = pos[1]; rec.to = pos;
        const hl = !!(top && top.person === n);
        /* a person who is free and not called is a pictogram with a tooltip, not a text: 13 labels on a 1280 map covered the labels of the deviations (P2-10) */
        const idle = !hl && !info.tr && !/WORK|BUSY|CALLED|TRAVEL/.test(String(info.st || ''));
        const text = idle ? '' : AKT.personLabel(info);
        if (rec.t.textContent !== text) rec.t.textContent = text;
        const cls = `pm${hl ? ' hl' : ''}${info.tr ? ' travel' : ''}`;
        if (rec.g.getAttribute('class') !== cls) rec.g.setAttribute('class', cls);
        const tt = AKT.personTitle(info) + (hl ? ` · ${top.called ? 'позван' : 'его звать'} к беде ①` : '');
        const tEl = rec.g.querySelector('title');
        if (tEl.textContent !== tt) tEl.textContent = tt;
        if (from0 && Math.hypot(from0[0] - at[0], from0[1] - at[1]) > 30) {
          rec.way.setAttribute('points', P([from0, at]));
          rec.way.setAttribute('class', 'way' + (hl ? ' hl' : ''));
          rec.way.style.display = '';
        } else rec.way.style.display = 'none';
      }
      for (const n in this.people) if (!seen.has(n)) { const r = this.people[n]; r.leader.remove(); r.way.remove(); this.drop(r); delete this.people[n]; }
    },

    /* trucks: the state and road from Ditto; the place on the road is interpolated every frame (scheme of motion) */
    updateTrucks() {
      const seen = new Set();
      for (const n of Object.keys(AKT.things).filter(x => AKT.cat(x) === 'truck').sort(AKT.cmpNames)) {
        seen.add(n);
        const st = AKT.st(n), loc = AKT.name(String(AKT.val(n, 'location') || ''));
        let tr = this.trucks[n];
        if (!tr) {
          const el = E('circle', { class: 'truck-dot', r: this.truckR() / this.k }, this.gTrucks);
          E('title', null, el);
          tr = this.trucks[n] = { el, f: hash(n), dir: 1, x: null, y: null };
        }
        tr.st = st; tr.loc = loc;
        tr.path = loc && this.plan.anchors[loc] && this.plan.anchors[loc].path ? this.plan.anchors[loc].path : null;
        tr.at = !tr.path && loc ? (this.anchor(loc) || null) : null;
        if (/HAUL|LOADED/.test(st)) tr.dir = 1; else if (/RETURN/.test(st)) tr.dir = -1;
        tr.trip = Math.max(4, (AKT.num(n, 'cycle_min') || 30) * 0.3);
        tr.down = AKT.stopped(st) || (!tr.path && !tr.at);
        tr.el.style.display = tr.down ? 'none' : '';
        tr.el.setAttribute('class', 'truck-dot' + (/HAUL|LOADED|QUEUE|DUMP/.test(st) ? ' full' : ''));
        tr.el.setAttribute('r', String(this.truckR() / this.k));
        const tt = `${AKT.nameRu(n)}: ${AKT.stOf(n)}${loc ? ' · ' + AKT.placeRu(loc) : ''} · место на дороге — схема движения`;
        const te = tr.el.firstChild; if (te.textContent !== tt) te.textContent = tt;
      }
      for (const n in this.trucks) if (!seen.has(n)) { this.trucks[n].el.remove(); delete this.trucks[n]; }
    },
    startLoop() {
      if (this.raf || !this.svg) return;
      this.lastTs = 0;
      const step = ts => {
        this.raf = 0;
        if (!this.svg || !this.svg.isConnected || document.hidden) return;
        /* 25 frames a second are enough for belts and trucks: a lower load on a machine without a graphics card */
        if (this.lastTs && ts - this.lastTs < 38) { this.raf = requestAnimationFrame(step); return; }
        const dt = this.lastTs ? Math.min(0.1, (ts - this.lastTs) / 1000) : 0;
        this.lastTs = ts;
        this.frame(dt);
        this.raf = requestAnimationFrame(step);
      };
      this.raf = requestAnimationFrame(step);
    },
    frame(dt) {
      const speed = AKT.num('site', 'speed') || 0, paused = AKT.st('site') === 'PAUSED' || !speed || AKT.isStale();
      const still = reduced();
      const mm = paused ? 0 : speed / 60;            // model minutes per real second
      const k = this.k;
      for (const n in this.belts) {
        const b = this.belts[n];
        if (paused || still) continue;
        b.off -= b.v * dt / k;
        b.dash.setAttribute('stroke-dashoffset', String(b.off % (18 / k)));
      }
      for (const n in this.hauls) {
        const h = this.hauls[n];
        if (paused || still || !h.v) continue;
        h.off -= h.v * dt / k;
        h.dash.setAttribute('stroke-dashoffset', String(h.off % (20 / k)));
      }
      const ease = 1 - Math.exp(-dt * 5);
      for (const n in this.trucks) {
        const t = this.trucks[n];
        if (t.down) continue;
        let tx, ty;
        if (t.path) {
          if (!still && mm) {
            if (/QUEUE|DUMP/.test(t.st)) t.f += (0.97 - t.f) * ease * 0.5;
            else if (/LOADING/.test(t.st)) t.f += (0.03 - t.f) * ease * 0.5;
            else {
              /* between two readings from Ditto the truck keeps going along the road in the direction of its state,
                 and waits at the end of the road for the next reading (it does not turn round by itself) */
              const a = AKT.truckAlong(t.f, t.dir, t.st, dt * mm, t.trip);
              t.f = a.f; t.dir = a.dir;
            }
          }
          const p = pointAt(t.path, t.f);
          /* two lanes: loaded on one side, empty on the other */
          const q = pointAt(t.path, Math.min(1, t.f + 0.01));
          const dx = q[0] - p[0], dy = q[1] - p[1], L = Math.hypot(dx, dy) || 1, side = (t.dir > 0 ? 1 : -1) * 18;
          tx = p[0] - dy / L * side; ty = p[1] + dx / L * side;
        } else if (t.at) {
          const a = hash(n) * 6.283, r = 60 + 50 * hash(n + 'r');
          tx = t.at[0] + r * Math.cos(a); ty = t.at[1] + r * Math.sin(a);
        } else continue;
        if (t.x == null || still) { t.x = tx; t.y = ty; } else { t.x += (tx - t.x) * ease; t.y += (ty - t.y) * ease; }
        t.el.setAttribute('cx', t.x.toFixed(1)); t.el.setAttribute('cy', (-t.y).toFixed(1));
      }
    },

    updateExtras(chain) {
      const seen = new Set(), seenRoad = new Set();
      for (const x of AKT.extras()) {
        const n = x.name, st = AKT.st(n);
        if (x.cat === 'person' || x.cat === 'truck') continue;
        const lv = AKT.levelOf(n);
        const layer = CAT_LAYER[x.cat] || 'sensors';
        const machine = AKT.MACHINE_CATS.has(x.cat);
        /* in the norm only in its layer; a deviation always (machines in repair go to the fleet summary) */
        const show = this.on(layer) || (lv > 0 && !machine) || ['fire', 'hpgr'].includes(x.cat) && lv > 0;
        if (x.path) {
          seenRoad.add(n);
          let pl = this.roads[n];
          if (!pl) {
            const a = E('a', { href: `?view=unit&id=${AKT.id(n)}` }, this.gRoads);
            pl = E('polyline', { class: 'xroad' }, a); E('title', null, a);
            this.roads[n] = pl;
          }
          pl.setAttribute('points', P(x.path));
          pl.setAttribute('class', `xroad ${AKT.lvCls(lv)}${AKT.hatchOn() && chain.has(n) ? ' scen' : ''}`);
          pl.parentNode.style.display = show ? '' : 'none';
          pl.parentNode.querySelector('title').textContent = `${AKT.nameRu(n)} (${AKT.typeRu(AKT.type(n))}): ${AKT.stOf(n)}${AKT.num(n, 'trucks_on') != null ? ' · самосвалов на дороге ' + fmt(AKT.num(n, 'trucks_on')) : ''}`;
          if (!x.pos) continue;
          if (x.cat === 'road') continue;
        }
        if (!x.pos) continue;
        seen.add(n);
        let rec = this.extras[n];
        const glyph = XGLYPH[x.cat] || 'dot';
        if (!rec || rec.glyph !== glyph) {
          if (rec) this.drop(rec);
          const pos = machine ? (AKT.machinePos(n) || x.pos) : x.pos;
          rec = this.pxg(this.gExtra, pos[0], pos[1], 'xm');
          rec.glyph = glyph;
          const a = E('a', { href: `?view=unit&id=${AKT.id(n)}` }, rec.g);
          const sh = { person: () => E('circle', { r: 4.5, class: 'xs' }, a),
            sensor: () => E('polygon', { points: '0,-6 6,0 0,6 -6,0', class: 'xs' }, a),
            piezo: () => E('polygon', { points: '-7,-6 7,-6 0,7', class: 'xs' }, a),
            exc: () => E('polygon', { points: '0,-7 7,6 -7,6', class: 'xs' }, a),
            face: () => E('path', { d: 'M-6,-6 L6,6 M-6,6 L6,-6', class: 'xs xline' }, a),
            box: () => E('rect', { x: -8, y: -8, width: 16, height: 16, rx: 2, class: 'xs' }, a),
            drop: () => E('path', { d: 'M0,-9 C5,-2 7,2 7,4 A7,7 0 0 1 -7,4 C-7,2 -5,-2 0,-9 Z', class: 'xs' }, a),
            fire: () => E('path', { d: 'M0,-9 C6,-3 7,1 6,5 A6.5,6.5 0 0 1 -6,5 C-7,1 -3,-1 0,-9 Z', class: 'xs xfire' }, a),
            dozer: () => { E('rect', { x: -5, y: -4, width: 10, height: 8, rx: 1.5, class: 'xs' }, a); E('path', { d: 'M-8,-5 L-8,5', class: 'xs xline' }, a); },
            drill: () => { E('rect', { x: -5, y: 1, width: 10, height: 5, rx: 1, class: 'xs' }, a); E('path', { d: 'M0,1 L0,-9', class: 'xs xline' }, a); },
            dot: () => E('circle', { r: 6, class: 'xs' }, a), idot: () => E('circle', { r: 5, class: 'xs' }, a) };
          (sh[glyph] || sh.dot)();
          const letter = XLETTER[x.cat];
          if (letter) T(a, 0, x.cat === 'piezo' ? 2 : 4, letter, { class: 'xl' });
          rec.val = ['piezo', 'sensor', 'water-trouble', 'fire', 'hpgr', 'other'].includes(x.cat) ? T(a, 10, 4, '', { class: 'xv' }) : null;
          rec.dev = !rec.val && ['dozer', 'drill', 'face', 'road'].includes(x.cat) ? T(a, 10, 4, '', { class: 'xv' }) : null;
          E('title', null, a);
          rec.cat = x.cat;
          this.extras[n] = rec;
        }
        if (machine) { const p = AKT.machinePos(n); if (p) { rec.x = p[0]; rec.y = p[1]; } } else { rec.x = x.pos[0]; rec.y = x.pos[1]; }
        rec.hidden = !show;
        rec.g.style.display = show ? '' : 'none';
        rec.g.setAttribute('class', `xm x-${x.cat} ${AKT.lvCls(lv)}${AKT.hatchOn() && chain.has(n) ? ' scen' : ''}`);
        if (rec.val) {
          /* value on the map: only for a deviation or in the instrument layer */
          const v = lv || this.on(layer) ? (lv ? G(lv) : '') + shortVal(n) : '';
          if (rec.val.textContent !== v) rec.val.textContent = v;
        }
        if (rec.dev) {
          const v = AKT.deviates(n) && !machine ? `${G(lv)}${AKT.shortName(n)} ${AKT.stOf(n)}` : '';
          if (rec.dev.textContent !== v) rec.dev.textContent = v;
        }
        const nums = mainNums(n, 4);
        const tt = `${AKT.nameRu(n)} (${AKT.typeRu(AKT.type(n))})${st ? ': ' + AKT.stOf(n) : ''}${nums.length ? ' · ' + nums.map(o => o.text).join(' · ') : ''} · нажмите — карточка`;
        const tEl = rec.g.querySelector('title');
        if (tEl.textContent !== tt) tEl.textContent = tt;
      }
      for (const n in this.extras) if (!seen.has(n)) { this.drop(this.extras[n]); delete this.extras[n]; }
      for (const n in this.roads) if (!seenRoad.has(n)) { this.roads[n].parentNode.remove(); delete this.roads[n]; }
    },

    updateCrews() {
      const HOME = { 'crew-water': 'water' };
      const on = this.on('people');
      for (const n of AKT.ofType('crew')) {
        const tag = { 'crew-kip': 'КИП', 'crew-cpd': 'ЦПД', 'crew-mill': 'ФАБ', 'crew-water': 'ХВ' }[n] || AKT.nameRu(n).replace(/^Бригада\s+/, '').slice(0, 4);
        if (!this.anchor(n) && !this.anchor(HOME[n] || 'line-1')) continue;
        const task = String(AKT.val(n, 'task') || '');
        const st = AKT.st(n);
        const m = /(kz\.aktogay:)?([a-z]+-[0-9a-z]+|pit|power|water|fleet)/.exec(task);
        let key = m ? m[2] : '';
        const pm = /^(sag|ball|cyclones|flot|rougher|cleaner|thick|filter|pebble)-([12])/.exec(key);
        if (pm) key = 'line-' + pm[2];
        let at = key ? this.anchor(key) : null;
        if (!at || st === 'FREE' || st === 'OFF') at = this.anchor(n) || this.anchor(HOME[n] || 'line-1');
        let rec = this.crews[n];
        if (!rec) {
          rec = this.pxg(this.gCrew, at[0], at[1], 'crew');
          const a = E('a', { href: `?view=unit&id=${AKT.id(n)}` }, rec.g);
          E('rect', { x: -17, y: -9, width: 34, height: 18, rx: 3 }, a);
          T(a, 0, 4, tag, {});
          E('title', null, a);
          rec.base = [14, -14];
          this.crews[n] = rec;
        }
        const show = on;
        rec.hidden = !show;
        rec.g.style.display = show ? '' : 'none';
        rec.x = at[0]; rec.y = at[1];
        rec.g.setAttribute('class', 'crew' + (st === 'TRAVEL' ? ' travel' : ''));
        rec.g.querySelector('title').textContent = `${AKT.nameRu(n)}: ${AKT.stRu(st, n)}${task ? ' · ' + (AKT.things[AKT.name(task)] ? AKT.nameRu(AKT.name(task)) : task) : ''}`;
      }
    },

    updateBatches() {
      const seen = new Set(), on = this.on('ore');
      const beltCount = {}, excCount = {};
      const layersBy = { 'stockpile-1': [], 'stockpile-2': [] };
      for (const n of AKT.batches()) {
        const st = AKT.st(n);
        if (st === 'DONE' || st === 'PLANNED') continue;
        const loc = AKT.name(String(AKT.val(n, 'location') || '')), par = AKT.parent(n) || '';
        const axb = AKT.batchAxb(n);
        let at = null, base = [0, 0];
        if (st === 'IN_STOCK') {
          const sp = /stockpile-[12]/.exec(loc + ' ' + par);
          if (sp) { layersBy[sp[0]].push({ n, t: AKT.num(n, 'tonnes_left') || 0, axb, src: 'ditto' }); }
          continue;
        }
        if (st === 'DIG') {
          const ex = /exc-[1-5]/.exec(loc + ' ' + par);
          const key = ex ? ex[0] : (Object.keys(AKT.things).find(e => /^exc-/.test(e) && AKT.name(String(AKT.val(e, 'block') || '')) === n) || 'pit');
          const c = excCount[key] = (excCount[key] || 0) + 1;
          const a = this.anchor(key) || this.anchor('pit');
          at = [a[0], a[1]]; base = [16 * c, -16];
        } else {
          const cv = /conveyor-[12]/.exec(loc + ' ' + par);
          const key = cv ? cv[0] : (/line-2|stockpile-2|crusher-2/.test(loc + par) ? 'conveyor-2' : 'conveyor-1');
          const c = beltCount[key] = (beltCount[key] || 0) + 1;
          const [x, y] = pointAt(this.belts[key].path, Math.min(0.9, 0.35 + 0.12 * c));
          at = [x, y]; base = [0, -14];
        }
        seen.add(n);
        let rec = this.batches[n];
        if (!rec) {
          rec = this.pxg(this.gBatch, at[0], at[1], 'batch');
          const a = E('a', { href: `?view=unit&id=${AKT.id(n)}` }, rec.g);
          E('circle', { cx: 0, cy: 0, r: 10 }, a);
          T(a, 0, 4, '', {});
          E('title', null, a);
          this.batches[n] = rec;
        }
        rec.x = at[0]; rec.y = at[1]; rec.base = base;
        rec.hidden = !on; rec.g.style.display = on ? '' : 'none';
        rec.g.setAttribute('class', 'batch ' + AKT.oreClass(axb));
        rec.g.querySelector('text').textContent = AKT.batchNo(n) + AKT.oreLetter(axb);
        const pit = AKT.num(n, 'pit_t');
        rec.g.querySelector('title').textContent = `Партия ${AKT.batchNo(n)}: ${AKT.stRu(st, n)} · руда ${AKT.oreWord(axb)}, A×b ${f1(axb)} (≈ по блочной модели)${pit != null && pit > 0 ? ' · в карьере ещё ' + fmt(pit) + ' т' : ''}`;
      }
      for (const n in this.batches) if (!seen.has(n)) { this.drop(this.batches[n]); delete this.batches[n]; }
      for (const sp of ['stockpile-1', 'stockpile-2']) {
        let layers = null, est = false;
        const raw = AKT.val('mod-ore', 'layers_l' + sp.slice(-1));
        if (typeof raw === 'string' && raw.trim().startsWith('[') && String(AKT.val('mod-ore', 'idSimulationRun') || '') === AKT.run) {
          try {
            const arr = JSON.parse(raw).filter(o => Number(o.t ?? 0) >= 1);
            layers = arr.map(o => ({ n: String(o.batch ?? ''), t: Number(o.t ?? 0), axb: Number(o.axb ?? NaN), win: o.window ?? '', sag: Number(o.in_sag ?? 0) >= 0.5 }));
            est = true;
          } catch (e) { layers = null; }
        }
        if (!layers) layers = layersBy[sp];
        this.drawLayers(sp, on ? layers : [], est);
      }
    },
    drawLayers(sp, layers, est) {
      let rec = this.layers[sp];
      if (!rec) {
        const a = this.anchor(sp);
        rec = this.pxg(this.gLayers, a[0], a[1], 'layers'); rec.base = LAYER_CANDS[0].slice(); rec.cands = LAYER_CANDS;
        rec.leader = E('line', { class: 'leader' }, this.gLeaders); rec.to = a;
        this.layers[sp] = rec; this.place(rec);
      }
      const g = rec.g;
      const top = layers.slice().sort((a, b) => (b.sag - a.sag) || (b.t - a.t)).slice(0, 4);
      const sig = top.map(l => `${l.n}|${Math.round(l.t)}|${l.axb}|${l.win || ''}|${l.sag ? 1 : 0}`).join(';') + `|${layers.length}` + (est ? '|est' : '');
      if (g.dataset.sig === sig) return;
      g.dataset.sig = sig;
      while (g.firstChild) g.removeChild(g.firstChild);
      if (!layers.length) return;
      let y = 0;
      const a = E('a', { href: '?view=ore' }, g);
      E('rect', { x: -3, y: -3, width: 10, height: 10, class: 'layers-bg' }, a);
      for (const l of top) {
        const h = Math.max(17, Math.min(22, 20 * (l.t || 0) / 15000));
        const r = E('rect', { x: 0, y: y, width: 22, height: h - 1, class: 'ore-rect' }, a);
        r.setAttribute('fill', `var(--${AKT.oreClass(isFinite(l.axb) ? l.axb : null)})`);
        T(a, 27, y + h / 2 + 4, `${AKT.batchNo(l.n)}${AKT.oreLetter(isFinite(l.axb) ? l.axb : null)} ${fmt(l.t)} т${l.sag ? ' · в мельнице' : ''}`, { class: 'small' });
        y += h;
      }
      T(a, 0, y + 13, (est ? '≈ слои склада' : 'слои склада') + (layers.length > top.length ? ` (ещё ${layers.length - top.length})` : ''), { class: 'small' });
      try { const b = a.getBBox(); const bg = a.querySelector('.layers-bg'); bg.setAttribute('x', b.x - 3); bg.setAttribute('y', b.y - 2); bg.setAttribute('width', b.width + 6); bg.setAttribute('height', b.height + 4); } catch (e) { /* hidden */ }
    },

    /* issues: a neutral numbered disc (no colour: the order is not the colour), a level ring around the node,
       pulsing for ①; ① gets a callout with its one price, ② ③ show it on hover. Rank ≥ 99 (called, in work):
       no number, the ring only. */
    updateIssues(top) {
      const seen = new Set(), seenRing = new Set();
      const count = {};
      for (const n of AKT.issues()) {
        const node = AKT.issueNode(n);
        let a = this.nodeXY(node);
        if (!a) a = this.anchor('line-1');
        if (!a) continue;
        const key = AKT.nodeKey(node) || node;
        const lv = AKT.issueLevel(n);
        /* ring of the node: the worst level of its issues */
        let ring = this.rings[key];
        if (!ring) {
          ring = this.pxg(this.gRings, a[0], a[1], 'ringg');
          ring.fill = E('circle', { r: 17, class: 'ring-fill' }, ring.g);
          ring.pulse = E('circle', { r: 17, class: 'pulse' }, ring.g);
          ring.c = E('circle', { r: 17, class: 'ring' }, ring.g);
          this.rings[key] = ring; ring.lv = 9;
        }
        if (!seenRing.has(key)) { ring.lv = lv; ring.top = false; seenRing.add(key); } else ring.lv = Math.min(ring.lv, lv);
        if (n === top) ring.top = true;
        ring.x = a[0]; ring.y = a[1];
        ring.c.setAttribute('class', 'ring lv-' + ring.lv); ring.fill.setAttribute('class', 'ring-fill lv-' + ring.lv);
        ring.pulse.setAttribute('class', 'pulse lv-' + ring.lv); ring.pulse.style.display = ring.top ? '' : 'none';
        this.place(ring);
        if (AKT.rankNo(n) == null) continue;
        const c = count[key] = (count[key] || 0) + 1;
        seen.add(n);
        let rec = this.issues[n];
        if (!rec) {
          rec = this.pxg(this.gIssue, a[0], a[1], 'issue');
          const g = E('g', { role: 'link', tabindex: 0 }, rec.g);
          E('circle', { cx: 0, cy: 0, r: 12, class: 'rk-d' }, g);
          T(g, 0, 5, '', {});
          E('title', null, g);
          g.addEventListener('click', () => focusRow(n)); g.addEventListener('keydown', ev => { if (ev.key === 'Enter') focusRow(n); });
          this.issues[n] = rec;
        }
        rec.x = a[0]; rec.y = a[1]; rec.base = [16 + 26 * (c - 1), -18];
        rec.g.querySelector('text').textContent = fmt(AKT.rankNo(n));
        const tt = `Беда ${AKT.rankSign(n)}: ${AKT.issueTitle(n)} · ${AKT.issueMain(n).text} · ${AKT.issuePrice(n)} · нажмите — карточка в панели`;
        rec.g.querySelector('title').textContent = tt;
        rec.g.firstChild.setAttribute('aria-label', tt.replace(/≈/g, 'примерно'));
      }
      for (const n in this.issues) if (!seen.has(n)) { this.drop(this.issues[n]); delete this.issues[n]; }
      for (const k in this.rings) if (!seenRing.has(k)) { this.drop(this.rings[k]); delete this.rings[k]; }
      /* callout of ①: "① Фильтр 1 · позвать до 16:22 завтра" */
      if (top) {
        const node = AKT.issueNode(top), a = this.nodeXY(node) || this.anchor('line-1');
        let co = this.callout;
        if (!co) {
          co = this.callout = this.pxg(this.gCallout, a[0], a[1], 'callout');
          const ln = E('a', { href: AKT.href('?view=queue') }, co.g);
          co.rect = E('rect', { x: 0, y: -15, width: 10, height: 22, rx: 3 }, ln);
          co.t = E('text', { x: 7, y: 1 }, ln);
          co.t1 = E('tspan', null, co.t); co.t2 = E('tspan', { class: 'money' }, co.t);
          co.tip = E('title', null, ln);
          co.leader = E('line', { class: 'leader top' }, this.gLeaders);
          co.base = [0, 0];
        }
        co.x = a[0]; co.y = a[1]; co.to = a; co.issue = top;
        const lv = AKT.issueLevel(top);
        co.g.setAttribute('class', 'callout lv-' + lv);
        const t1 = `${AKT.rankSign(top)} ${AKT.nameRu(node)} · `, t2 = AKT.issuePrice(top);
        if (co.t1.textContent !== t1) co.t1.textContent = t1;
        if (co.t2.textContent !== t2) co.t2.textContent = t2;
        co.tip.textContent = `${AKT.issueTitle(top)} · ${AKT.issueMain(top).text} · позвать ${AKT.roleAcc(AKT.roleFirst(AKT.issueRole(top)))} · нажмите — все беды`;
        try { const b = co.t.getBBox(); co.rect.setAttribute('width', b.width + 14); } catch (e) { /* not rendered */ }
        co.g.style.display = ''; co.hidden = false;
      } else if (this.callout) { this.callout.g.style.display = 'none'; this.callout.hidden = true; this.callout.leader.style.display = 'none'; }
    },

    updateInset(chain) {
      const set = (key, text, cls) => {
        const e = this.ins[key]; if (!e) return;
        if (e.textContent !== text) { e.textContent = text; const tt = e.parentNode.querySelector('title'); if (tt) tt.textContent = text + ' · нажмите — подробнее'; }
        if (cls !== undefined) { const c = cls || ''; if ((e.getAttribute('class') || '') !== c) e.setAttribute('class', c); }
      };
      const sq = (key, name) => { const e = this.ins['sq-' + key]; if (!e) return; const c = `sq ${AKT.levelCls(name)}${AKT.hatchOn() && chain.has(name) ? ' scen' : ''}`; if (e.getAttribute('class') !== c) e.setAttribute('class', c); };
      const word = (name, normal) => { const s = AKT.st(name); return s && s !== normal ? ` ${AKT.stRu(s, name)}` : ''; };
      const mw = v => v == null ? '—' : f1(v / 1000);
      for (const n of [1, 2]) {
        const ln = `line-${n}`, sag = `sag-${n}`, peb = `pebble-${n}`, fl = `flot-${n}`, th = `thick-${n}`, fi = `filter-${n}`, cy = `cyclones-${n}`;
        const lv = AKT.levelOf(ln);
        set(ln, `${G(lv)}Линия ${n}${word(ln, 'RUN')} · ${AKT.vsBase(ln, 'tph', fmt, 50)} т/ч руды · ${AKT.vsBase(ln, 'cu_tph', f1, 0.3)} т/ч меди · извлечение ${f1(AKT.num(ln, 'recovery'))} %`, 'inset-title');
        sq(ln, ln);
        const r = AKT.lineReason(n), iss = AKT.nodeIssues(ln)[0];
        set(`why-${n}`, r ? `${G(r.lv)}${r.text}` : (iss ? `${G(AKT.issueLevel(iss))}${AKT.issueTitle(iss)}` : ''), r ? (r.lv === 1 ? 'dev1' : 'dev') : (iss ? 'dev' : ''));
        const shaft = AKT.num(sag, 'power_kw'), lim = AKT.num(sag, 'power_limit_kw');
        set(sag, `SAG-${n}${word(sag, 'RUN')}: ${mw(shaft)} из ${fmt(lim != null ? lim / 1000 : null)} МВт · ${AKT.vsBase(sag, 'feed_tph', fmt, 50)} т/ч`);
        sq(sag, sag);
        const ba = AKT.num(`ball-${n}a`, 'power_kw'), bb = AKT.num(`ball-${n}b`, 'power_kw');
        set(`mill-${n}`, `дробление гали${word(peb, 'RUN')} ${fmt(AKT.num(peb, 'feed_tph'))} из ${fmt(AKT.num(peb, 'limit_tph'))} т/ч · шаровые ${mw(ba)} + ${mw(bb)} МВт · крупность помола ${fmt(AKT.num(cy, 'p80_um'))} мкм`);
        sq(`mill-${n}`, AKT.stopped(AKT.st(`ball-${n}a`)) ? `ball-${n}a` : AKT.stopped(AKT.st(`ball-${n}b`)) ? `ball-${n}b` : peb);
        set(fl, `флотация ${n}${word(fl, 'RUN')}: извлечение ${f1(AKT.num(fl, 'recovery'))} % · медь в хвостах ${f3(AKT.num(fl, 'tail_cu'))} %`);
        sq(fl, fl);
        const hf = AKT.num(th, 'hours_to_full');
        set(`conc-${n}`, `сгуститель${word(th, 'NORMAL')} ${fmt(AKT.num(th, 'inventory_t'))} из ${fmt(AKT.pass(th, 'capacity_t'))} т${hf != null ? ' · полон через ' + AKT.durH(hf) : ''} · фильтр: прессов в работе ${fmt(AKT.num(fi, 'presses_on'))} из ${fmt(AKT.pass(fi, 'presses'))}`);
        sq(`conc-${n}`, AKT.levelOf(fi) ? fi : th);
        set(`insag-${n}`, inSagText(n));
      }
      const cs = 'conc-stock';
      set(cs, `${G(AKT.levelOf(cs))}Концентрат${word(cs, 'NORMAL')}: ${fmt(AKT.num(cs, 'stock_t'))} из ${fmt(AKT.pass(cs, 'capacity_t'))} т · отгрузка поездом в 06:00 и 18:00`);
      sq(cs, cs);
      this.fitInset();
    },

    boxAt(rec, bb, dx, dy) {
      const [ax, ay] = this.toPx(rec.x, rec.y);
      const x0 = ax + rec.base[0] + dx + bb.x, y0 = ay + rec.base[1] + dy + bb.y;
      return { x0, y0, x1: x0 + bb.width, y1: y0 + bb.height };
    },
    layout() {
      if (!this.svg || !this.cw) return;
      const cw = this.cw, ch = this.ch, PAD = 2, M = 3;
      const placed = [];
      const overlap = b => { let s = 0; for (const p of placed) { const w = Math.min(b.x1, p.x1) + PAD - Math.max(b.x0, p.x0), h = Math.min(b.y1, p.y1) + PAD - Math.max(b.y0, p.y0); if (w > 0 && h > 0) s += w * h; } return s; };
      const out = b => Math.max(0, M - b.x0) + Math.max(0, b.x1 - (cw - M)) + Math.max(0, M - b.y0) + Math.max(0, b.y1 - (ch - M));
      const bbox = rec => { if (rec.hidden || rec.g.style.display === 'none') return null; try { const b = rec.g.getBBox(); return b.width || b.height ? b : null; } catch (e) { return null; } };
      const fixed = rec => { const bb = bbox(rec); if (bb) placed.push(this.boxAt(rec, bb, rec.dx, rec.dy)); };
      [this.inset, this.attr, this.scale, this.north].forEach(fixed);
      this.markers.forEach(fixed);
      Object.values(this.rings).forEach(fixed);
      const move = (rec, cands, clamp) => {
        const bb = bbox(rec);
        if (!bb) return null;
        let best = null, bestCost = Infinity;
        const tryAt = (dx, dy) => {
          let b = this.boxAt(rec, bb, dx, dy);
          if (clamp) {
            const sx = b.x0 < M ? M - b.x0 : (b.x1 > cw - M ? (cw - M) - b.x1 : 0);
            const sy = b.y0 < M ? M - b.y0 : (b.y1 > ch - M ? (ch - M) - b.y1 : 0);
            dx += sx; dy += sy; b = this.boxAt(rec, bb, dx, dy);
          }
          const cost = overlap(b) * 10 + out(b) * 1000;
          if (cost < bestCost) { bestCost = cost; best = [dx, dy, b]; }
          return cost === 0;
        };
        if (!(rec.laid && tryAt(rec.dx, rec.dy))) {
          for (const [dx, dy] of cands) if (tryAt(dx, dy)) break;
        }
        rec.dx = best[0]; rec.dy = best[1]; rec.laid = true;
        placed.push(best[2]);
        this.place(rec);
        return best[2];
      };
      /* trouble ① first: its marker and callout never give way */
      Object.values(this.issues).forEach(r => move(r, RING, true));
      if (this.callout && !this.callout.hidden) this.leader(this.callout, move(this.callout, CALLOUT_CANDS, true));
      Object.values(this.crews).forEach(r => move(r, RING, true));
      Object.values(this.people).forEach(r => this.leader(r, move(r, RING, true)));
      Object.values(this.extras).forEach(r => { if (r.hidden) return; if (r.val && r.val.textContent || (r.dev && r.dev.textContent)) move(r, RING, true); else { r.dx = 0; r.dy = 0; this.place(r); } });
      const labs = Object.values(this.labels).sort((a, b) => (a.def.prio || 9) - (b.def.prio || 9));
      const label = L => this.leader(L.rec, move(L.rec, LABEL_CANDS, true));
      labs.filter(L => (L.def.prio || 9) <= 4).forEach(label);
      Object.values(this.layers).forEach(r => {
        r.base = [0, 0];
        const b = r.g.firstChild ? move(r, r.cands, true) : null;
        if (b) this.leader(r, b); else if (r.leader) r.leader.style.display = 'none';
      });
      labs.filter(L => (L.def.prio || 9) > 4).forEach(label);
      Object.values(this.batches).forEach(r => move(r, RING, true));
    },
    leader(rec, b) {
      if (!rec.leader || !rec.to || !b) return;
      const [tx, ty] = this.toPx(rec.to[0], rec.to[1]);
      const px = Math.max(b.x0, Math.min(b.x1, tx)), py = Math.max(b.y0, Math.min(b.y1, ty));
      const far = Math.hypot(px - tx, py - ty) > 8;
      rec.leader.style.display = far ? '' : 'none';
      if (!far) return;
      const [mx, my] = this.toM(px, py);
      rec.leader.setAttribute('x1', mx); rec.leader.setAttribute('y1', -my);
      rec.leader.setAttribute('x2', rec.to[0]); rec.leader.setAttribute('y2', -rec.to[1]);
    },

    highlight(node) {
      if (!node) return;
      const chain = new Set([node]);
      const q = [node];
      while (q.length) { const n = q.shift(); for (const f of AKT.feeds(n)) if (!chain.has(f)) { chain.add(f); q.push(f); } }
      const ids = new Set();
      for (const n of chain) { ids.add(n); const m = /^(sag|ball|cyclones|flot|rougher|cleaner|thick|filter|pebble)-([12])/.exec(n); if (m) ids.add('line-' + m[2]); }
      for (const id in this.labels) this.labels[id].el.style.fontWeight = ids.has(id) ? '700' : '';
      for (const n in this.nodes) this.nodes[n].style.strokeWidth = ids.has(n) ? '3px' : '';
      if (this.hlTimer) clearTimeout(this.hlTimer);
      this.hlTimer = setTimeout(() => {
        for (const id in this.labels) this.labels[id].el.style.fontWeight = '';
        for (const n in this.nodes) this.nodes[n].style.strokeWidth = '';
      }, 5000);
    },
  };

  /* what the SAG grinds now (akt-ore: share of the feed by batch) */
  const inSagText = n => {
    const raw = AKT.val('mod-ore', 'layers_l' + n);
    let now = [];
    if (typeof raw === 'string' && raw.trim().startsWith('[') && String(AKT.val('mod-ore', 'idSimulationRun') || '') === AKT.run) {
      try { now = JSON.parse(raw).filter(o => Number(o.in_sag ?? 0) > 0.02).sort((a, b) => Number(b.in_sag || 0) - Number(a.in_sag || 0)).slice(0, 2); } catch (e) { now = []; }
    }
    if (now.length) return `сейчас в мельнице ≈ ${now.map(o => `партия ${AKT.batchNo(String(o.batch ?? ''))} (${AKT.oreWord(Number(o.axb))})`).join(' и ')}`;
    return 'какая руда в мельнице — модуль руды ещё не посчитал';
  };
  const focusRow = issue => {
    AKT.panel.open = issue;
    AKT.panel.update();
    AKT.focusIssue(issue);
    const card = document.getElementById('topcard');
    if (card) { card.scrollIntoView({ block: 'nearest' }); card.focus(); }
  };
  /* the belt of line N carries copper that the open troubles lose now (stage 1 the belt, 2 the stockpile, 3 the mill) */
  function beltLoss(n, b) {
    if (!AKT.troubleLoss) return false;
    const by = AKT.troubleLoss().by, line = n.slice(-1);
    return b.sag ? (by[line + ':2'] > 0 || by[line + ':3'] > 0) : by[line + ':1'] > 0;
  }
  function pathLen(path) { let s = 0; for (let i = 1; i < path.length; i++) s += Math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1]); return s; }
  function pointAt(path, f) {
    const total = pathLen(path); let d = Math.max(0, Math.min(1, f)) * total;
    for (let i = 1; i < path.length; i++) {
      const seg = Math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1]);
      if (d <= seg || i === path.length - 1) {
        const t = seg ? Math.max(0, Math.min(1, d / seg)) : 0;
        const x = path[i - 1][0] + (path[i][0] - path[i - 1][0]) * t, y = path[i - 1][1] + (path[i][1] - path[i - 1][1]) * t;
        const ang = Math.atan2(path[i][1] - path[i - 1][1], path[i][0] - path[i - 1][0]) * 180 / Math.PI;
        return [x, y, ang];
      }
      d -= seg;
    }
    return [path[0][0], path[0][1], 0];
  }
  AKT.views.plan = view;
})();
