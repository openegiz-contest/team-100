/* Aktogay stand, browser side. Core: twin state from /api/state (Ditto),
   history from /api/history (InfluxDB), routing by ?view=, the status line
   «что это и что делать» and the always-on panel. Views register in AKT.views
   and update in place: elements keep their ids, only text and attributes
   change. No libraries. */
'use strict';

const AKT = window.AKT = {
  NS: 'kz.aktogay',
  things: {},          // name -> thing JSON (attributes, features, _modified)
  now: 0,              // server clock at the last poll (unix s)
  polled: 0,           // browser clock at the last good poll (unix s)
  run: '', simTime: null, err: '',
  journal: [], journalAt: 0,
  params: new URLSearchParams(location.search),
  views: {}, current: null, listeners: new Set(),
  POLL_MS: 2000, JOURNAL_MS: 10000,
};
/* «Режим проверки модели» (?check=1): only then the views show what the simulator alone knows (its journal of
   hidden causes, the copies of the model without the scenario). Off by default. */
AKT.check = AKT.params.get('check') === '1';
AKT.SIM_ONLY_TYPES = new Set(['validation-sim', 'baseline']);
AKT.simOnly = name => !AKT.check && AKT.SIM_ONLY_TYPES.has(String((AKT.things[name] && AKT.things[name].attributes && AKT.things[name].attributes.type) || name));
AKT.SIM_ONLY_NOTE = 'данные симулятора для проверки модели: видны только в «Режиме проверки модели» (в «Пульте модели»), диспетчеру на смене недоступны';

/* ------------------------------------------------------------------ access */
AKT.name = tid => (typeof tid === 'string' && tid.startsWith(AKT.NS + ':')) ? tid.slice(AKT.NS.length + 1) : tid;
AKT.id = name => name.includes(':') ? name : AKT.NS + ':' + name;
AKT.thing = name => AKT.things[name];
AKT.type = name => { const t = AKT.things[name]; return t && t.attributes ? t.attributes.type || '' : ''; };
AKT.raw = (name, f) => {
  const t = AKT.things[name];
  const ft = t && t.features && t.features[f];
  return ft && ft.properties ? ft.properties.value : undefined;
};
/* feature value; -1.0 (number) and '' are "no value" -> null */
AKT.val = (name, f) => {
  const v = AKT.raw(name, f);
  if (v === undefined || v === null || v === '') return null;
  if (typeof v === 'number' && v === -1) return null;
  if (typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length === 0) return null;
  return v;
};
AKT.num = (name, f) => { const v = AKT.val(name, f); return typeof v === 'number' ? v : null; };
AKT.unit = (name, f) => { const t = AKT.things[name]; const ft = t && t.features && t.features[f]; return ft && ft.properties ? (ft.properties.unit || '') : ''; };
AKT.st = name => { const v = AKT.raw(name, 'state'); if (typeof v === 'string' && v) return v; const s = AKT.raw(name, 'status'); return typeof s === 'string' ? s : ''; };
AKT.attr = (name, path) => {
  let o = AKT.things[name] && AKT.things[name].attributes;
  for (const k of path.split('.')) { if (o == null) return undefined; o = o[k]; }
  return o;
};
AKT.nameRu = name => AKT.attr(name, 'name_ru') || AKT.attr(name, 'name') || name;
AKT.feeds = name => (AKT.attr(name, 'feeds') || []).map(AKT.name);
AKT.fedBy = name => (AKT.attr(name, 'fed_by') || []).map(AKT.name);
AKT.parent = name => { const p = AKT.attr(name, '_parents'); return p ? AKT.name(p) : null; };
AKT.ofType = type => Object.keys(AKT.things).filter(n => AKT.type(n) === type).sort(AKT.cmpNames);
AKT.cmpNames = (a, b) => a.localeCompare(b, 'en', { numeric: true });
AKT.passport = name => AKT.attr(name, 'passport') || {};
AKT.pass = (name, key) => { const p = AKT.passport(name)[key]; return p && typeof p === 'object' ? p.value : p; };
AKT.role = name => { const r = AKT.attr(name, 'responsible'); return r ? (r.name_ru || r.role || '') : ''; };
AKT.modifiedAge = name => {
  const t = AKT.things[name];
  if (!t || !t._modified) return null;
  const m = Date.parse(t._modified) / 1000;
  if (!isFinite(m)) return null;
  return Math.max(0, AKT.now + (Date.now() / 1000 - AKT.polled) - m);
};

/* -------------------------------------------------------------- formatting */
const NBSP = ' ';
AKT.NB = NBSP;
AKT.fmt = (v, d = 0) => (v == null || !isFinite(v)) ? '—'
  : new Intl.NumberFormat('ru-RU', { minimumFractionDigits: d, maximumFractionDigits: d }).format(v);
AKT.f1 = v => AKT.fmt(v, 1);
AKT.f2 = v => AKT.fmt(v, 2);
AKT.f3 = v => AKT.fmt(v, 3);
AKT.money = usd => {
  if (usd == null || !isFinite(usd)) return '—';
  const a = Math.abs(usd), s = usd < 0 ? '−' : '';
  if (a >= 1e6) return `${s}$${AKT.fmt(a / 1e6, 2)}${NBSP}млн`;
  if (a >= 1e3) return `${s}$${AKT.fmt(a / 1e3, 1)}${NBSP}тыс.`;
  return `${s}$${AKT.fmt(a, 0)}`;
};
/* money in the dispatcher's words: below $1 000 is "меньше $1 тыс." */
AKT.usd = usd => (usd == null || !isFinite(usd)) ? '—' : (Math.abs(usd) < 1000 ? 'меньше $1' + NBSP + 'тыс.' : AKT.money(Math.abs(usd)));
AKT.approx = usd => (usd != null && isFinite(usd) && Math.abs(usd) < 1000) ? AKT.usd(usd) : '≈' + NBSP + AKT.usd(usd);
AKT.clock = simMin => {
  if (simMin == null || !isFinite(simMin) || simMin < 0) return '—:—';
  const m = Math.floor(simMin) % 1440;
  return String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0');
};
/* clock with the day when it is not today's (model time): "01:23 завтра", "23:40 вчера" */
AKT.clockDay = (simMin, ref) => {
  if (simMin == null || !isFinite(simMin) || simMin < 0) return '—:—';
  const r = ref == null ? AKT.simTime : ref;
  if (r == null || !isFinite(r) || r < 0) return AKT.clock(simMin);
  const d = Math.floor(simMin / 1440) - Math.floor(r / 1440);
  return AKT.clock(simMin) + (d === 0 ? '' : d === 1 ? `${NBSP}завтра` : d === -1 ? `${NBSP}вчера`
    : d === 2 ? `${NBSP}послезавтра` : d > 2 ? `${NBSP}(+${d}${NBSP}сут.)` : `${NBSP}${-d}${NBSP}сут. назад`);
};
AKT.simDate = simMin => {
  if (simMin == null || !isFinite(simMin) || simMin < 0) return null;
  const d0 = AKT.attr('site', 'start_date') || AKT.val('site', 'start_date') || AKT.val('site', 'date');
  let base;
  if (typeof d0 === 'string' && !isNaN(Date.parse(d0))) base = new Date(Date.parse(d0));
  else {
    base = new Date(); base.setHours(12, 0, 0, 0);
    const r = AKT.simTime;
    if (r != null && isFinite(r) && r >= 0) base.setDate(base.getDate() - Math.floor(r / 1440));
  }
  const d = new Date(base.getTime()); d.setDate(d.getDate() + Math.floor(simMin / 1440));
  return d;
};
AKT.clockDate = (simMin, ref) => AKT.clockDay(simMin, ref);
AKT.dur = min => {
  if (min == null || !isFinite(min) || min < 0) return '—';
  const h = Math.floor(min / 60), m = Math.round(min % 60);
  if (h >= 48) return `${Math.floor(h / 24)}${NBSP}сут.${NBSP}${h % 24}${NBSP}ч`;
  return h > 0 ? `${h}${NBSP}ч${NBSP}${String(m).padStart(2, '0')}${NBSP}мин` : `${m}${NBSP}мин`;
};
AKT.durH = h => (h == null || !isFinite(h) || h < 0) ? '—' : AKT.dur(h * 60);
AKT.ago = s => s == null ? '—' : (s < 1 ? 'только что' : `${Math.round(s)}${NBSP}с назад`);
AKT.esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
/* an estimate of the model, not a measurement: "≈" in front of the number (one note in the legend says so) */
AKT.EST = '≈';
AKT.ASSUME = '(д)';
AKT.est = text => `<span class="est" title="Расчёт модели, не измерение">≈${NBSP}${text}</span>`;
AKT.estT = text => `≈${NBSP}${text}`;
AKT.asm = () => '<sup class="asm" title="Допущение: числа нет в открытых источниках">д</sup>';
/* uncertainty in words: "точность низкая" when the error is larger than the value */
AKT.unc = (gap, sigma, unitFmt) => {
  if (sigma == null || gap == null) return '';
  if (sigma >= Math.abs(gap)) return 'точность низкая — возможно, потерь нет';
  if (sigma < Math.abs(gap) / 2) return '';
  return `±${unitFmt ? unitFmt(sigma) : AKT.f1(sigma)}`;
};

/* -------------------------------------------------------- states, levels */
/* ISA-101: grey = works as it should, colour only for the abnormal. Level 1 (P1) — stopped or dangerous,
   level 2 (P2) — deviation or losing now, level 3 (P3) — soon (the buffer still holds). */
const RED = new Set(['STOP', 'DOWN', 'ALARM', 'EMPTY', 'FULL', 'OFF', 'FAILED', 'FIRE', 'FAULT', 'LEAK', 'BROKEN', 'TRIP', 'FLOOD', 'FLOODED', 'CLOSED']);
const YELLOW = new Set(['SLOW', 'STARVED', 'LIMITED', 'LIMITED_GRID', 'UPSET', 'LOW', 'HIGH', 'LIMIT', 'SHORT', 'ONE', 'WARN', 'WARNING', 'STALE', 'REPAIR']);
AKT.cls = s => RED.has(s) ? 'st-red' : (YELLOW.has(s) ? 'st-yellow' : 'st-grey');
AKT.LV_CLS = { 0: 'st-grey', 1: 'st-red', 2: 'st-yellow', 3: 'st-soon' };
AKT.LV_GLYPH = { 0: '', 1: '◆', 2: '▲', 3: '△' };
AKT.lvCls = lv => AKT.LV_CLS[lv || 0];
AKT.glyph = lv => lv ? `<span class="lv lv-${lv}" aria-hidden="true">${AKT.LV_GLYPH[lv]}</span>` : '';
const ST_RU = {
  RUN: 'работает', STOP: 'стоит', SLOW: 'медленно', STARVED: 'нет питания', LIMITED_GRID: 'лимит сети', RELINE: 'перефутеровка',
  NORMAL: 'норма', LOW: 'мало', EMPTY: 'пуст', FULL: 'полон', HIGH: 'высокий', UPSET: 'сбой', LIMIT: 'на пределе', LIMITED: 'ограничена',
  DIG: 'копает', MOVE: 'переезд', IDLE: 'ждёт', DOWN: 'в ремонте', SHORT: 'не хватает', ONE: 'один пресс', FREE: 'свободен',
  TRAVEL: 'в пути', WORK: 'работает', OFF: 'нет', PAUSED: 'пауза', WARMUP: 'прогрев', ALARM: 'тревога',
  OPEN: 'открыта', CALLED: 'позвали', IN_WORK: 'чинят', RESOLVED: 'устранено', SNOOZED: 'отложено',
  PLANNED: 'в плане', BELT: 'в пути к складу', IN_STOCK: 'на складе', DONE: 'готово',
  WAITING: 'ожидание', RUNNING: 'считается', FAILED: 'ошибка',
  BUSY: 'занят', AVAILABLE: 'свободен', ON_WAY: 'в пути', AT_WORK: 'на месте', ON_SITE: 'на месте', ON_SHIFT: 'на смене',
  OFF_SHIFT: 'не на смене', LOADING: 'погрузка', LOAD: 'погрузка', HAULING: 'везёт', HAUL: 'везёт', HAUL_FULL: 'везёт руду', LOADED: 'гружёный',
  DUMPING: 'разгрузка', DUMP: 'разгрузка', RETURNING: 'порожняком', RETURN: 'порожняком', QUEUE: 'в очереди',
  QUEUED: 'в очереди', WAIT: 'ждёт', OK: 'исправен', WARN: 'внимание', WARNING: 'внимание', FAULT: 'неисправен',
  STALE: 'нет связи', FIRE: 'пожар', LEAK: 'утечка', FLOOD: 'подтопление', FLOODED: 'подтоплен', ACTIVE: 'в работе', CLOSED: 'закрыта', REPAIR: 'ремонт',
  MAINT: 'обслуживание', READY: 'готов', BROKEN: 'сломан', TRIP: 'защита', MINED: 'отработан', PLAN: 'в плане', DRILLING: 'бурит', MOVING: 'переезд',
};
const ST_WORD = { TRUCK: 'самосвал', PUMP: 'насос', PIPE: 'водовод', WATER: 'вода', NO: 'нет', DATA: 'данных', LOW: 'низкий',
  HIGH: 'высокий', EMPTY: 'пустой', FULL: 'полный', WAIT: 'ждёт', CREW: 'бригада', FOR: 'для', AT: 'у', TO: 'к', IN: 'в' };
AKT.stRu = (s, name) => {
  if (!s) return '—';
  const byType = name && AKT.stRuType ? AKT.stRuType(s, name) : null;
  if (byType || ST_RU[s]) return byType || ST_RU[s];
  if (typeof s === 'string' && /^[A-Z0-9_]+$/.test(s)) {
    const ru = name ? AKT.raw(name, 'state_ru') || AKT.raw(name, 'status_ru') : null;
    if (typeof ru === 'string' && ru) return ru;
    return s.split('_').map(w => ST_RU[w] || ST_WORD[w] || w.toLowerCase()).join(' ');
  }
  return s;
};
AKT.stOf = name => AKT.stRu(AKT.st(name), name);
AKT.stopped = s => RED.has(s);
AKT.oreClass = axb => axb == null ? 'ore-mid' : (axb >= 38 ? 'ore-soft' : (axb < 30 ? 'ore-hard' : 'ore-mid'));
AKT.oreLetter = axb => axb == null ? '?' : (axb >= 38 ? 'М' : (axb < 30 ? 'Т' : 'С'));
AKT.oreWord = axb => axb == null ? 'неизвестно' : (axb >= 38 ? 'мягкая' : (axb < 30 ? 'твёрдая' : 'средняя'));

/* ------------------------------------------------------- derived numbers */
AKT.cuPrice = () => AKT.pass('site', 'cu_price') || 14539;
AKT.payable = () => (AKT.pass('site', 'payable_share_pct') || 95.5) / 100;
AKT.usdPerH = cuTph => cuTph == null ? null : cuTph * AKT.payable() * AKT.cuPrice();
AKT.cuOfUsd = usd => usd == null ? null : usd / (AKT.payable() * AKT.cuPrice());
AKT.lineShaftMw = n => {
  const sag = AKT.num(`sag-${n}`, 'power_kw');
  const a = AKT.num(`ball-${n}a`, 'power_kw'), b = AKT.num(`ball-${n}b`, 'power_kw');
  if (sag == null && a == null && b == null) return null;
  return ((sag || 0) + (a || 0) + (b || 0)) / 1000;
};
AKT.gridFromShaft = mw => mw == null ? null : mw / 0.96;   // drive efficiency 0.96 (допущение)
AKT.baseOk = () => AKT.check && !!AKT.scenario() && String(AKT.val('baseline', 'idSimulationRun') || '') === AKT.run && !!AKT.run;
AKT.base = (thing, f) => {
  if (!AKT.baseOk()) return null;
  const v = AKT.num('baseline', `${thing}_${f}_base`);
  return v == null ? null : v;
};
AKT.vsBase = (thing, f, format, minAbs) => {
  const v = AKT.num(thing, f), b = AKT.base(thing, f);
  const fm = format || AKT.fmt;
  if (b == null || v == null) return fm(v);
  const d = Math.abs(v - b);
  return d > Math.max(minAbs == null ? 1e-9 : minAbs, 0.02 * Math.abs(b)) ? `${fm(b)}${NBSP}→${NBSP}${fm(v)}` : fm(v);
};
AKT.differs = (thing, f, minAbs) => {
  const v = AKT.num(thing, f), b = AKT.base(thing, f);
  return b != null && v != null && Math.abs(v - b) > Math.max(minAbs || 0, 0.02 * Math.abs(b));
};
AKT.shiftResult = () => {
  if (!AKT.check) return null;
  const r = AKT.val('baseline', 'shift_result');
  if (!r || typeof r !== 'object' || r.run !== AKT.run || !AKT.run) return null;
  if (String(AKT.val('baseline', 'idSimulationRun') || '') !== AKT.run) return null;
  if (!(r.kind === 'scenario' || r.kind === 'shift') || !(typeof r.t_min === 'number' && r.t_min >= 0)) return null;
  return r;
};
AKT.scenario = () => { const s = AKT.val('site', 'scenario'); return typeof s === 'string' ? s.trim() : ''; };
const SCEN_RU = { crusher: 'Встала дробилка', grid: 'Сеть урезала мощность', hard: 'Пришла твёрдая руда', reline: 'Перефутеровка SAG',
  fork: 'Две беды сразу', water: 'Беда с водой', hpgr_fire: 'Пожар на прессе дробления гали', dose: 'скрытая причина', cyclone: 'скрытая причина',
  liner: 'скрытая причина', oxide: 'скрытая причина', startup: 'Пуск мельницы при людях внутри', dust: 'Пыление пляжа',
  winter: 'Зима', balls: 'скрытая причина', conc: 'скрытая причина' };
const HIDDEN_KINDS = new Set(['dose', 'cyclone', 'liner', 'oxide', 'balls', 'conc']);
AKT.scenarioRu = s => s.split('+').filter(Boolean).map(p => {
  const [k, n] = p.split(':');
  return (SCEN_RU[k] || k) + (n && (AKT.check || !HIDDEN_KINDS.has(k)) ? ` (линия ${n})` : '');
}).join(' + ');
AKT.scenarioId = s => AKT.check || !s.split('+').some(p => HIDDEN_KINDS.has(p.split(':')[0])) ? s : 'скрыто';
/* The way of a trouble to the copper: from the nodes of the open issues down by feeds (dispatcher's view);
   the declared chain of the scenario only in «Режим проверки модели». */
AKT.scenarioChain = () => {
  const out = new Set();
  let keepWater = false;
  const down = start => { const q = [start]; while (q.length) { const n = q.shift(); if (out.has(n)) continue; out.add(n); for (const f of AKT.feeds(n)) q.push(f); } };
  if (!AKT.check) {
    for (const i of AKT.issues()) {
      const node = AKT.issueNode(i);
      if (!node || !AKT.things[node]) continue;
      if (/^(water|piezo)/.test(node) || ['water-trouble', 'piezo'].includes(AKT.cat(node))) keepWater = true;
      down(node);
    }
    if (!keepWater) out.delete('water');
    out.delete('conc-stock');
    return out;
  }
  for (const p of AKT.scenario().split('+')) {
    const [k, n] = p.split(':');
    if (k === 'crusher') down(`crusher-${n || 1}`);
    else if (k === 'grid') { out.add('power'); down('ball-2b'); down('sag-2'); out.add('line-2'); }
    else if (k === 'hard') { out.add('pit'); AKT.ofType('exc').forEach(e => out.add(e)); down(`crusher-${n || 1}`); }
    else if (k === 'reline') { down(`sag-${n || 1}`); [`stockpile-${n || 1}`, `conveyor-${n || 1}`, `crusher-${n || 1}`, 'power'].forEach(x => out.add(x)); }
    else if (k === 'water') { keepWater = true; out.add('water'); Object.keys(AKT.things).filter(t => AKT.cat(t) === 'water-trouble' || AKT.cat(t) === 'piezo').forEach(t => out.add(t)); }
    else if (k === 'hpgr_fire') {
      const h = Object.keys(AKT.things).filter(t => AKT.cat(t) === 'hpgr');
      (h.length ? h : (n ? [`pebble-${n}`] : ['pebble-1', 'pebble-2'])).forEach(down);
    }
  }
  if (!keepWater) out.delete('water');
  out.delete('conc-stock');
  return out;
};
AKT.issues = () => AKT.ofType('issue').concat(Object.keys(AKT.things).filter(n => n.startsWith('issue-') && AKT.type(n) !== 'issue'))
  .filter((n, i, a) => a.indexOf(n) === i)
  .filter(n => !['RESOLVED'].includes(AKT.st(n)))
  /* an issue left in Ditto by an earlier run (after «смена заново») is not this shift's trouble */
  .filter(n => { const r = String(AKT.val(n, 'idSimulationRun') || ''); return !r || !AKT.run || r === AKT.run; })
  .sort((a, b) => (AKT.num(a, 'rank') ?? 99) - (AKT.num(b, 'rank') ?? 99) || AKT.cmpNames(a, b));
AKT.batches = () => {
  const all = AKT.ofType('batch').concat(Object.keys(AKT.things).filter(n => n.startsWith('batch-') && AKT.type(n) !== 'batch'))
    .filter((n, i, a) => a.indexOf(n) === i)
    .filter(n => String(AKT.val(n, 'idSimulationRun') || '') === AKT.run && AKT.num(n, 'sim_time') != null);
  const newest = Math.max(-1, ...all.map(n => AKT.num(n, 'sim_time')));
  return all.filter(n => AKT.num(n, 'sim_time') >= newest - 30);
};
AKT.batchAxb = name => { const v = AKT.pass(name, 'est_axb'); return typeof v === 'number' ? v : (AKT.num(name, 'axb_soft')); };
AKT.batchNo = name => { const m = /(\d+)$/.exec(name); return m ? String(parseInt(m[1], 10)) : name; };
/* rank of an issue in the queue of the module; 99 = called already, out of the queue: no number on labels */
AKT.rankNo = n => { const r = AKT.num(n, 'rank'); return r != null && r < 99 ? r : null; };
AKT.RANK_SIGN = ['', '①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨'];
AKT.rankSign = n => { const r = AKT.rankNo(n); return r == null ? '' : (AKT.RANK_SIGN[r] || `№${r}`); };
AKT.issueTag = n => AKT.rankNo(n) != null ? `беда ${AKT.fmt(AKT.rankNo(n))}` : `беда · ${AKT.stRu(AKT.st(n), n)}`;
AKT.issueNode = n => AKT.name(String(AKT.val(n, 'node') || ''));
AKT.issueRanks = () => { const m = {}; AKT.issues().forEach((n, i) => { const node = AKT.issueNode(n); if (node && !(node in m)) m[node] = (AKT.num(n, 'rank') ?? (i + 1)); }); return m; };
/* losses from mod-losses: [{node, gap, usd, sigma, status, roles, loss:boolean}] */
AKT.losses = () => ['sag-1', 'sag-2', 'cyclones-1', 'cyclones-2', 'flot-1', 'flot-2'].map(node => {
  const status = String(AKT.val('mod-losses', `${node}_status`) || '');
  const gap = AKT.num('mod-losses', `${node}_gap_cu_tph`), usd = AKT.num('mod-losses', `${node}_gap_usd_h`);
  const loss = /loss|потер/i.test(status);
  return { node, status, gap, usd, sigma: AKT.num('mod-losses', `${node}_sigma`), roles: AKT.val('mod-losses', `${node}_roles`) || '', loss };
});
/* a loss worth showing: the module calls it a loss and the gap is a loss (not a gain); sure = larger than its error */
AKT.lossShown = l => l.loss && l.gap != null && l.gap > 0.005;
AKT.lossSure = l => AKT.lossShown(l) && (l.sigma == null || l.gap > l.sigma);

/* ------------------------------------------------- things of any type */
AKT.KNOWN_TYPES = new Set(['site', 'pit', 'exc', 'batch', 'crusher', 'conveyor', 'stockpile', 'line', 'sag', 'ball', 'cyclones',
  'flot', 'rougher', 'cleaner', 'water', 'power', 'crew', 'fleet', 'pebble', 'thick', 'filter', 'conc-stock', 'mod-losses',
  'mod-ore', 'mod-priority', 'issue', 'control', 'journal', 'validation-setup', 'validation-sim', 'validation-calib', 'baseline']);
AKT.cat = name => {
  const t = String(AKT.type(name) || '').toLowerCase(), n = String(name).toLowerCase(), s = t || n;
  if (/person|worker|people|staff|employee|operator|human|dispatcher/.test(s)) return 'person';
  if (t === 'crew') return 'crew';
  if (/piezo/.test(s)) return 'piezo';
  if (/sensor|gauge|meter|probe|detector|analyzer|analyser|weigher|scale/.test(s)) return 'sensor';
  if (/truck|hauler|dumper/.test(s)) return 'truck';
  if (/dozer/.test(s)) return 'dozer';
  if (/drill/.test(s)) return 'drill';
  if (t === 'exc' || /excavat|shovel|loader/.test(s)) return 'exc';
  if (/face|zaboy/.test(s)) return 'face';
  if (/road|ramp|haul-route|route/.test(s)) return 'road';
  if (/hpgr/.test(s)) return 'hpgr';
  if (t !== 'water' && /water|pipe|leak|well|pump|flood/.test(s)) return 'water-trouble';
  if (/fire|smoke/.test(s)) return 'fire';
  return AKT.KNOWN_TYPES.has(t) ? 'known' : 'other';
};
AKT.CAT_RU = { person: 'люди', crew: 'бригады', piezo: 'пьезометры', sensor: 'датчики', truck: 'самосвалы', exc: 'экскаваторы',
  dozer: 'бульдозеры', drill: 'буровые станки', face: 'забои', road: 'дороги', hpgr: 'пресс дробления гали', 'water-trouble': 'вода', fire: 'пожар', other: 'прочее' };
/* normal states by category (table 3.0 of the UI spec) */
const NORMAL_ST = { truck: ['LOADING', 'HAUL_FULL', 'QUEUE', 'DUMP', 'RETURN', 'HAUL', 'LOAD', 'WAIT'], exc: ['DIG', 'MOVE'], dozer: ['WORK', 'IDLE'],
  drill: ['DRILLING', 'MOVING', 'IDLE'], face: ['ACTIVE'], road: ['OPEN'], person: null, crew: null, sensor: ['OK', 'NORMAL', 'RUN'], piezo: ['OK', 'NORMAL'] };
AKT.MACHINE_CATS = new Set(['truck', 'exc', 'dozer', 'drill']);
AKT.QUIET_CATS = new Set(['truck', 'exc', 'dozer', 'drill', 'face', 'road', 'sensor', 'other']);
AKT.deviates = n => {
  const s = AKT.st(n), c = AKT.cat(n);
  if (c === 'person' || c === 'crew') return false;
  if (!s || ['RUN', 'NORMAL', 'OK'].includes(s)) return false;
  return !(NORMAL_ST[c] || []).includes(s);
};
/* open issues standing on a thing (a plant unit stands in its line on the plan: line-1 gets the issues of filter-1) */
AKT.nodeIssues = name => AKT.issues().filter(i => { const node = AKT.issueNode(i); return node === name || (node && AKT.nodeKey(node) === name && name !== node); });
/* level of an issue: 1 — people in danger or the node stopped; 2 — losing now; 3 — later (buffer holds) */
AKT.lossNow = n => { const usd = AKT.num(n, 'loss_usd_h'), from = AKT.num(n, 'loss_from'); return usd != null && usd > 0 && from != null && (AKT.simTime == null || from <= AKT.simTime + 1); };
AKT.issueLevel = n => {
  const safety = String(AKT.val(n, 'safety_class') || '');
  if (safety === 'S0') return 1;
  const node = AKT.issueNode(n);
  if (node && RED.has(AKT.st(node))) return 1;
  if (AKT.lossNow(n) || safety === 'S1') return 2;
  return 3;
};
/* level of a thing: its state by category (table 3.0) and the open issues on it */
AKT.levelOf = name => {
  if (!name || !AKT.things[name]) return 0;
  const s = AKT.st(name), c = AKT.cat(name), t = AKT.type(name);
  let lv = 0;
  if (!(c === 'person' || c === 'crew' || ['issue', 'batch', 'site', 'control', 'journal', 'validation-calib', 'validation-setup', 'validation-sim', 'baseline'].includes(t) || /^mod-/.test(t))) {
    if (RED.has(s)) lv = 1;
    else if (c === 'exc' && s === 'IDLE') lv = 2;
    else if (YELLOW.has(s)) lv = 2;
    else if (AKT.QUIET_CATS.has(c) && AKT.deviates(name)) lv = 2;
  }
  for (const i of AKT.nodeIssues(name)) { const il = AKT.issueLevel(i); if (!lv || il < lv) lv = il; }
  return lv;
};
AKT.levelCls = name => AKT.lvCls(AKT.levelOf(name));
AKT.devCls = n => AKT.levelCls(n);
AKT.shortName = n => { const nm = AKT.nameRu(n), m = /\b([A-Z]{2}\d{2,3})\b/.exec(nm); return m ? m[1] : (nm.length > 16 ? nm.slice(0, 15) + '…' : nm); };
AKT.pathLen = path => { let s = 0; for (let i = 1; i < path.length; i++) s += Math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1]); return s; };
AKT.pointAt = (path, f) => {
  let d = Math.max(0, Math.min(1, f)) * AKT.pathLen(path);
  for (let i = 1; i < path.length; i++) {
    const seg = Math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1]);
    if (d <= seg || i === path.length - 1) {
      const t = seg ? Math.max(0, Math.min(1, d / seg)) : 0;
      return [path[i - 1][0] + (path[i][0] - path[i - 1][0]) * t, path[i - 1][1] + (path[i][1] - path[i - 1][1]) * t];
    }
    d -= seg;
  }
  return path[0].slice();
};
let machineCache = { at: -1, map: {} };
AKT.machinePos = name => {
  if (machineCache.at !== AKT.polled) {
    const map = {}, groups = {};
    for (const n of Object.keys(AKT.things).sort(AKT.cmpNames)) {
      if (!['truck', 'dozer', 'drill'].includes(AKT.cat(n))) continue;
      const loc = AKT.name(String(AKT.val(n, 'location') || ''));
      const key = loc && (AKT.things[loc] || (AKT.planData && AKT.planData.anchors[loc])) ? loc : (AKT.parent(n) || 'pit');
      (groups[key] = groups[key] || []).push(n);
    }
    for (const key in groups) {
      const g = groups[key], path = AKT.path(key);
      if (path) { g.forEach((n, i) => { map[n] = AKT.pointAt(path, (i + 0.5) / g.length); }); continue; }
      const c = AKT.pos(key);
      if (!c) continue;
      g.forEach((n, i) => { const r = 110 * Math.sqrt(i + 1), a = 2.39996 * i; map[n] = [c[0] + r * Math.cos(a), c[1] + r * Math.sin(a)]; });
    }
    machineCache = { at: AKT.polled, map };
  }
  return machineCache.map[name] || AKT.pos(name);
};
AKT.planData = null;
AKT.loadPlan = async () => { if (!AKT.planData) AKT.planData = await AKT.get('/plan.json'); return AKT.planData; };
const fin2 = (a, b) => (typeof a === 'number' && typeof b === 'number' && isFinite(a) && isFinite(b) && !(a === -1 && b === -1)) ? [a, b] : null;
AKT.fromLonLat = (lon, lat) => {
  const p = AKT.planData;
  if (!p || typeof lon !== 'number' || typeof lat !== 'number' || !isFinite(lon) || !isFinite(lat) || (lon === -1 && lat === -1)) return null;
  return [(lon - p.origin_lonlat[0]) * p.metres_per_deg[0], (lat - p.origin_lonlat[1]) * p.metres_per_deg[1]];
};
const xyOf = o => {
  if (o == null) return null;
  if (Array.isArray(o)) return fin2(o[0], o[1]);
  if (typeof o === 'object') return fin2(o.x, o.y) || AKT.fromLonLat(o.lon ?? o.lng, o.lat);
  return null;
};
AKT.pos = (name, depth) => {
  depth = depth || 0;
  if (!AKT.things[name] && !(AKT.planData && AKT.planData.anchors[name])) return null;
  const f = k => AKT.val(name, k), a = k => AKT.attr(name, k);
  let p = fin2(f('x_m'), f('y_m')) || fin2(f('x'), f('y')) || fin2(f('pos_x'), f('pos_y')) || xyOf(f('position')) || xyOf(f('pos'))
    || xyOf(f('xy')) || AKT.fromLonLat(f('lon'), f('lat'));
  if (!p) p = xyOf(a('ui.plan')) || xyOf(a('position')) || xyOf(a('geo')) || fin2(a('x'), a('y')) || AKT.fromLonLat(a('lon'), a('lat'));
  if (!p && AKT.planData) {
    const an = AKT.planData.anchors[name];
    if (an) p = an.xy ? an.xy : (an.path ? an.path[Math.floor(an.path.length / 2)] : null);
  }
  if (!p && depth < 2) {
    for (const k of ['location', 'at', 'place', 'node', 'face', 'target', 'task', 'to']) {
      const v = f(k) ?? a(k);
      if (typeof v !== 'string' || !v) continue;
      const m = /(?:kz\.aktogay:)?([a-z][a-z0-9-]*)/.exec(v);
      let ref = m ? m[1] : '';
      if (/^(sag|ball|cyclones|flot|rougher|cleaner|thick|filter|pebble)-[12]/.test(ref)) ref = 'line-' + ref.match(/-([12])/)[1];
      if (ref && ref !== name) { p = AKT.pos(ref, depth + 1); if (p) break; }
    }
    if (!p && AKT.parent(name) && AKT.parent(name) !== 'site') p = AKT.pos(AKT.parent(name), depth + 1);
  }
  return p;
};
AKT.path = name => {
  if (!AKT.things[name]) return null;
  for (const v of [AKT.val(name, 'path'), AKT.attr(name, 'path'), AKT.attr(name, 'ui.path'), AKT.val(name, 'route'), AKT.attr(name, 'route')]) {
    let arr = v;
    if (typeof arr === 'string') { try { arr = JSON.parse(arr); } catch (e) { arr = null; } }
    if (Array.isArray(arr) && arr.length >= 2) { const pts = arr.map(xyOf).filter(Boolean); if (pts.length >= 2) return pts; }
  }
  const an = AKT.planData && AKT.planData.anchors[name];
  return an && Array.isArray(an.path) && an.path.length >= 2 && AKT.cat(name) === 'road' ? an.path : null;
};
AKT.extras = () => Object.keys(AKT.things).filter(n => !AKT.KNOWN_TYPES.has(AKT.type(n)) || ['person', 'piezo', 'sensor', 'truck', 'face', 'road', 'hpgr', 'water-trouble', 'fire'].includes(AKT.cat(n)))
  .filter(n => AKT.type(n) !== 'crew' && AKT.type(n) !== 'exc' && !/^(mod-|validation-)/.test(AKT.type(n)))
  .map(n => ({ name: n, cat: AKT.cat(n), pos: AKT.pos(n), path: AKT.path(n) }))
  .filter(o => o.pos || o.path).sort((a, b) => AKT.cmpNames(a.name, b.name));
AKT.people = () => Object.keys(AKT.things).filter(n => ['person', 'crew'].includes(AKT.cat(n))).sort(AKT.cmpNames).map(n => {
  const s = AKT.st(n);
  const called = /CALLED|ON_WAY|TRAVEL/.test(s) || AKT.val(n, 'called') === true || AKT.num(n, 'called') === 1;
  const kind = called ? 'called' : /FREE|AVAILABLE|IDLE|READY/.test(s) ? 'free' : /OFF/.test(s) ? 'off' : (s ? 'busy' : 'free');
  const r = AKT.attr(n, 'responsible');
  const role = AKT.attr(n, 'role_ru') || AKT.pass(n, 'trade') || AKT.attr(n, 'role') || (r && (r.name_ru || r.role)) || AKT.val(n, 'role') || '';
  const refName = v => { const t = AKT.name(String(v || '')); return AKT.things[t] ? AKT.nameRu(t) : (AKT.kindRu ? AKT.kindRu(String(v || '')) : String(v || '')); };
  const task = AKT.val(n, 'task') || AKT.val(n, 'issue') || AKT.val(n, 'node');
  const where = AKT.val(n, 'location') || AKT.val(n, 'at');
  const free = AKT.num(n, 'free_at') ?? AKT.num(n, 'eta');
  return { name: n, kind, st: s, role: String(role), task: task ? refName(task) : '', where: where ? refName(where) : '', free };
});

/* ------------------------------------------------------------------ people */
const ROLE_SHORT = { crusher_mech: 'Мех. ЦПД', plant_mech: 'Мех. ФАБ', kip: 'КИПиА', mine_dispatcher: 'Диспетчер',
  shift_geologist: 'Геолог', shift_metallurgist: 'Металлург', power_engineer: 'Энергетик', tailings_engineer: 'Технолог',
  shift_supervisor: 'Нач. смены', shift_mechanic: 'Механик' };
AKT.personShort = n => {
  const r = AKT.attr(n, 'responsible.role');
  if (ROLE_SHORT[r]) return ROLE_SHORT[r];
  const nm = AKT.nameRu(n);
  return nm.length > 11 ? nm.split(/[\s(]/)[0].slice(0, 10) + '.' : nm;
};
AKT.persons = () => Object.keys(AKT.things).filter(n => AKT.cat(n) === 'person').sort(AKT.cmpNames);
AKT.placeRu = node => !node ? '—' : (AKT.things[node] ? AKT.nameRu(node) : node);
AKT.nodeKey = node => { const m = /^(sag|ball|cyclones|flot|rougher|cleaner|thick|filter|pebble)-([12])/.exec(node || ''); return m ? 'line-' + m[2] : node; };
/* role in the accusative (who to call): "Механик фабрики" -> "механика фабрики" */
const ROLE_ACC = { 'механик фабрики': 'механика фабрики', 'механик цпд': 'механика ЦПД', 'геолог смены': 'геолога смены',
  'дежурный кипиа': 'дежурного КИПиА', 'металлург смены': 'металлурга смены', 'горный диспетчер': 'горного диспетчера',
  'дежурный энергетик': 'дежурного энергетика', 'технолог хвостов и оборотной воды': 'технолога хвостового хозяйства',
  'начальник смены фабрики': 'начальника смены фабрики', 'оператор пульта': 'оператора пульта',
  'сменный руководитель цуп': 'сменного руководителя ЦУП', 'механик фабрики (мельницы)': 'механика фабрики',
  'бригада кипиа': 'бригаду КИПиА', 'бригада механиков цпд': 'бригаду механиков ЦПД', 'бригада механиков фабрики': 'бригаду механиков фабрики' };
const ROLE_KEYS = Object.keys(ROLE_ACC).sort((a, b) => b.length - a.length);
/* "Механик фабрики и начальник смены фабрики" -> two roles; "Технолог хвостов и оборотной воды" stays one */
AKT.roleParts = role => {
  let s = String(role || '').trim();
  const out = [];
  while (s) {
    const low = s.toLowerCase();
    const k = ROLE_KEYS.find(x => low.startsWith(x) && (low.length === x.length || low.startsWith(x + ' и ')));
    if (!k) { out.push(s); break; }
    out.push(s.slice(0, k.length)); s = s.slice(k.length).replace(/^\s+и\s+/, '');
  }
  return out;
};
AKT.roleAcc = role => AKT.roleParts(role).map(p => ROLE_ACC[p.toLowerCase()] || (p.charAt(0).toLowerCase() + p.slice(1))).join(' и ');
/* the first role: the button names one person */
AKT.roleFirst = role => AKT.roleParts(role)[0] || '';
const travelCache = {};
AKT.travel = n => {
  if (AKT.st(n) !== 'TRAVEL') return null;
  const to = AKT.name(String(AKT.val(n, 'location') || AKT.val(n, 'task') || ''));
  const key = `${n}|${AKT.run}|${to}`;
  let c = travelCache[key];
  if (!c) {
    const home = AKT.name(String(AKT.pass(n, 'home') || ''));
    c = travelCache[key] = { to, from: home, start: AKT.num(n, 'sim_time') ?? AKT.simTime, src: 'poll' };
    AKT.history(n, ['state', 'location'], '12h').then(d => {
      const pts = (d.points || []).filter(p => typeof p.sim_time === 'number');
      let i = pts.length - 1;
      while (i >= 0 && pts[i].state === 'TRAVEL' && AKT.name(String(pts[i].location || '')) === to) i--;
      const first = pts[i + 1], before = i >= 0 ? pts[i] : null;
      if (first) {
        c.start = before ? (before.sim_time + first.sim_time) / 2 : first.sim_time;
        c.src = 'history';
        if (before && before.location && AKT.name(String(before.location)) !== to) c.from = AKT.name(String(before.location));
      }
    }).catch(() => { /* InfluxDB may lag: the poll time stays */ }).finally(() => AKT.notify());
  }
  let start = c.start, src = c.src;
  for (const r of AKT.journal) {
    if ((r.run && r.run !== AKT.run) || !/call/.test(String(r.action || '')) || typeof r.sim_time !== 'number') continue;
    const node = AKT.issueNode(r.issue);
    if (node && node === to && r.sim_time <= (AKT.simTime ?? Infinity) && (src !== 'journal' || r.sim_time > start)) { start = r.sim_time; src = 'journal'; }
  }
  const arr = AKT.attr(n, 'responsible.arrive_min');
  const a0 = Array.isArray(arr) ? Number(arr[0]) : 20, a1 = Array.isArray(arr) ? Number(arr[1]) : 40;
  return { to, from: c.from, start, src, eta0: start + a0, eta1: start + a1, eta: start + (a0 + a1) / 2, a0, a1 };
};
AKT.personInfo = n => {
  const st = AKT.st(n);
  const loc = AKT.name(String(AKT.val(n, 'location') || ''));
  const task = AKT.name(String(AKT.val(n, 'task') || ''));
  const home = AKT.name(String(AKT.pass(n, 'home') || ''));
  const free = AKT.num(n, 'free_at');
  const issues = AKT.issues();
  const job = task ? (issues.find(i => AKT.issueNode(i) === task && AKT.name(String(AKT.val(i, 'person') || '')) === n)
    || issues.find(i => AKT.issueNode(i) === task) || null) : null;
  const role = AKT.pass(n, 'role') || AKT.attr(n, 'responsible.name_ru') || AKT.nameRu(n);
  return { name: n, st, loc, task, home, free, job, role: String(role), crew: AKT.pass(n, 'crew') || '', short: AKT.personShort(n),
    tr: st === 'TRAVEL' ? AKT.travel(n) : null };
};
AKT.topCall = () => {
  const top = AKT.issues()[0];
  if (!top) return null;
  const p = AKT.name(String(AKT.val(top, 'person') || ''));
  if (!p || !AKT.things[p]) return null;
  const node = AKT.issueNode(top);
  const called = AKT.issueCalled(top) || (['TRAVEL', 'WORK'].includes(AKT.st(p)) && AKT.name(String(AKT.val(p, 'task') || '')) === node);
  return { issue: top, person: p, node, called };
};
AKT.wayRu = tr => !tr ? '' : (tr.from && tr.from !== tr.to ? `${AKT.placeRu(tr.from)} → ${AKT.placeRu(tr.to)}` : `→ ${AKT.placeRu(tr.to)}`);
AKT.personLabel = info => info.short + (info.tr ? ` · будет ≈${NBSP}${AKT.clock(info.tr.eta)}` : '');
AKT.personTitle = info => `${AKT.nameRu(info.name)}: ${AKT.stRu(info.st, info.name)} · ${info.tr ? `в пути: ${AKT.wayRu(info.tr)}, будет ≈ ${AKT.clock(info.tr.eta0)}–${AKT.clock(info.tr.eta1)}` : 'где: ' + AKT.placeRu(info.loc)}`
  + `${info.free != null && info.free >= 0 ? ' · освободится ' + AKT.clockDate(info.free) : ''} · нажмите — карточка человека`;
/* availability of a person in words: "свободен, на линии 1" / "занят до 15:20" / "в пути, будет ≈ 14:50" */
AKT.personAvail = n => {
  if (!n || !AKT.things[n]) return '';
  const i = AKT.personInfo(n);
  if (i.tr) return `в пути (${AKT.wayRu(i.tr)}), будет ≈${NBSP}${AKT.clock(i.tr.eta)}`;
  if (i.st === 'FREE' || i.st === 'AVAILABLE') return `свободен, сейчас: ${AKT.placeRu(i.loc).toLowerCase()}`;
  if (i.free != null && i.free >= 0) return `занят до ${AKT.clockDay(i.free)}`;
  return AKT.stRu(i.st, n);
};
const PersonCard = AKT.personCard = {
  el: null, name: '',
  open(name, x, y) {
    if (!this.el) {
      this.el = document.createElement('div'); this.el.id = 'pcard'; this.el.setAttribute('role', 'dialog'); this.el.setAttribute('aria-label', 'Карточка человека');
      document.body.appendChild(this.el);
      document.addEventListener('keydown', ev => { if (ev.key === 'Escape') this.close(); });
      document.addEventListener('pointerdown', ev => { if (this.name && !this.el.contains(ev.target) && !(ev.target.closest && ev.target.closest('[data-person]'))) this.close(); });
    }
    this.name = name; this.el.style.display = 'block'; this.render();
    const w = this.el.offsetWidth, h = this.el.offsetHeight;
    this.el.style.left = Math.max(6, Math.min(window.innerWidth - w - 6, x + 12)) + 'px';
    this.el.style.top = Math.max(36, Math.min(window.innerHeight - h - 6, y + 8)) + 'px';
    const b = this.el.querySelector('button'); if (b) b.focus();
  },
  close() { if (this.el) this.el.style.display = 'none'; this.name = ''; },
  render() {
    const n = this.name;
    if (!n || !this.el) return;
    if (!AKT.things[n]) { this.close(); return; }
    const i = AKT.personInfo(n), top = AKT.topCall(), esc = AKT.esc;
    const where = i.tr ? `в пути: ${esc(AKT.wayRu(i.tr))}` : esc(AKT.placeRu(i.loc));
    const eta = i.tr ? `<tr><td>будет</td><td>≈ ${AKT.clock(i.tr.eta0)}–${AKT.clock(i.tr.eta1)} <span class="lbl-est">вызов ${i.tr.src === 'journal' ? 'в' : '≈'} ${AKT.clock(i.tr.start)} + дорога ${AKT.fmt(i.tr.a0)}–${AKT.fmt(i.tr.a1)} мин${AKT.asm()}</span></td></tr>` : '';
    const free = i.free != null && i.free >= 0 ? AKT.clockDate(i.free) : (i.st === 'FREE' ? 'свободен сейчас' : '—');
    const jobText = i.job ? `${AKT.issueTag(i.job)}: ${esc(AKT.placeRu(AKT.issueNode(i.job)))} — ${esc(AKT.kindRu(AKT.val(i.job, 'kind') || ''))}`
      : (i.task ? esc(AKT.placeRu(i.task)) : 'нет');
    const isTop = top && top.person === n;
    const html = `<div class="pc-h"><span class="pchip${i.tr ? ' travel' : ''}${isTop ? ' hl' : ''}">${esc(i.short)}</span> <b>${esc(AKT.nameRu(n))}</b><button class="pc-x" aria-label="Закрыть">×</button></div>
<table class="kv"><tr><td>роль</td><td>${esc(i.role)}${i.crew ? ` · ${esc(i.crew)}` : ''}</td></tr>
<tr><td>сейчас</td><td>${esc(AKT.stRu(i.st, n))}</td></tr>
<tr><td>где</td><td>${where}</td></tr>${eta}
<tr><td>освободится</td><td>${free}</td></tr>
<tr><td>работа</td><td>${jobText}</td></tr>
${isTop ? `<tr><td>беда ①</td><td class="pc-top">${top.called ? 'позван' : 'его звать первым'}</td></tr>` : ''}</table>
<div class="note">значения на ${AKT.clockDay(AKT.num(n, 'sim_time'))} модели · <a href="?view=unit&id=${AKT.id(n)}">подробно →</a></div>`;
    if (this.el.dataset.html !== html) {
      this.el.dataset.html = html; this.el.innerHTML = html;
      this.el.querySelector('.pc-x').addEventListener('click', () => this.close());
    }
  },
};
AKT.listeners.add(() => PersonCard.render());
AKT.get = async (url) => {
  const r = await fetch(url, { cache: 'no-store' });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status));
  return d;
};
AKT.post = async (url, body) => {
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status));
  return d;
};
AKT.href = h => (AKT.check && typeof h === 'string' && h.startsWith('?') && !/(^|[?&])check=/.test(h)) ? h + '&check=1' : h;
AKT.history = (thing, fields, range, run) => AKT.get(`/api/history?thing=${encodeURIComponent(AKT.name(thing))}&field=${encodeURIComponent(fields.join(','))}&range=${encodeURIComponent(range || '2h')}${run === undefined ? (AKT.run ? '&run=' + encodeURIComponent(AKT.run) : '') : (run ? '&run=' + encodeURIComponent(run) : '')}`);
/* storage is optional (private windows, blocked site data) */
AKT.store = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* optional */ } },
};

/* ------------------------------------------------------------ issues in words */
/* the main money of an issue, one line by its level */
AKT.issueMain = n => {
  const safety = String(AKT.val(n, 'safety_class') || '');
  if (safety === 'S0') return { text: 'Опасно для людей — первым, в деньгах не считаем', small: '', lv: 1 };
  const usd = AKT.num(n, 'loss_usd_h'), from = AKT.num(n, 'loss_from');
  if (usd == null || usd <= 0) return { text: 'Потерь не ждём', small: '', lv: 3 };
  if (from == null) return { text: 'Потерь в ближайшие 12 ч не ждём', small: `если начнутся: ${AKT.approx(usd)}/ч`, lv: 3 };
  const cu = AKT.cuOfUsd(usd);
  if (AKT.simTime != null && from > AKT.simTime + 1) {
    return { text: `Пока без потерь · запас до ${AKT.clockDay(from)}`, small: `(через ${AKT.dur(from - AKT.simTime)}), потом ${AKT.approx(usd)}/ч`, lv: 3 };
  }
  return { text: `Теряем ${AKT.approx(usd)}/ч`, small: cu != null && cu >= 0.05 ? `(≈ ${AKT.f1(cu)} т меди в час)` : '', lv: AKT.issueLevel(n) };
};
/* the second line: what an hour of delay costs, or till when one can wait */
AKT.issueDelay = n => {
  const safety = String(AKT.val(n, 'safety_class') || '');
  if (safety === 'S0') return 'Звать сейчас: беда класса S0, безопасность людей';
  const d = AKT.num(n, 'delay_cost_usd'), cb = AKT.num(n, 'call_by');
  if (d != null && d > 0) return `Час промедления ${AKT.approx(d)}`;
  if (cb != null && AKT.simTime != null && cb > AKT.simTime) return `Можно подождать: позвать до ${AKT.clockDay(cb)}`;
  if (AKT.lossNow(n)) return 'Звать сейчас: потери уже идут';
  return '';
};
/* ONE main price for the header and the map: "час промедления ≈ $X" or "позвать до HH:MM" */
AKT.issuePrice = n => {
  const safety = String(AKT.val(n, 'safety_class') || '');
  if (safety === 'S0') return 'опасно для людей';
  const d = AKT.num(n, 'delay_cost_usd'), cb = AKT.num(n, 'call_by');
  if (d != null && d > 0) return `час промедления ${AKT.approx(d)}`;
  if (cb != null && AKT.simTime != null && cb > AKT.simTime) return `позвать до ${AKT.clockDay(cb)}`;
  const usd = AKT.num(n, 'loss_usd_h');
  if (AKT.lossNow(n)) return `теряем ${AKT.approx(usd)}/ч`;
  return 'потерь пока нет';
};
AKT.issueTitle = n => {
  const node = AKT.issueNode(n);
  const nodeName = node ? AKT.nameRu(node) : '';
  let kind = String(AKT.val(n, 'kind') || '');
  /* a leak below the intake cap: no shortage yet, only the water balance shows it */
  if (kind === 'water_short' && /тихая утечка воды/.test(String(AKT.val(n, 'text') || ''))) kind = 'water_leak';
  return AKT.kindTitle ? AKT.kindTitle(kind, nodeName) : `${nodeName}: ${AKT.kindRu(kind)}`;
};
AKT.issueRole = n => String(AKT.val(n, 'responsible') || (AKT.issueNode(n) ? AKT.role(AKT.issueNode(n)) : '') || '');
AKT.issuePerson = n => { const p = AKT.name(String(AKT.val(n, 'person') || '')); return p && AKT.things[p] ? p : ''; };
/* called already: the state of the issue, rank 99 of the module, or a call written from this page */
AKT.calls = {};
AKT.issueCalled = n => ['CALLED', 'IN_WORK'].includes(AKT.st(n)) || (AKT.num(n, 'rank') ?? 0) >= 99 || !!AKT.calls[n + '|' + AKT.run];
AKT.issueSnoozed = n => AKT.st(n) === 'SNOOZED';
/* "Почему": the first part of the module's text, without its tail and technical notes */
AKT.issueWhy = n => {
  let t = String(AKT.val(n, 'text_plain') || AKT.val(n, 'text') || '');
  if (!t) return '';
  const whole = t;
  t = t.replace(/^\s*\d+\.\s*/, '').split(' · ')[0];
  const semi = t.indexOf(';');
  const head = semi >= 0 ? t.slice(0, semi) : t;
  const lastColon = head.lastIndexOf(': ');
  if (lastColon >= 0 && lastColon < head.length - 4) t = t.slice(lastColon + 2);
  t = t.split(';')[0].replace(/\s*\[оценка на модели\]/g, '').replace(/\s*\[допущение\]/g, '').replace(/\bR (\d)/g, 'извлечение $1');
  const m = /по мощности ([\d,\s  ]+ МВт) и A×b партии ([\d,]+) ожидалось ([\d\s  ]+) т\/ч, измерено ([\d\s  ]+)/.exec(t);
  if (m) t = `при мощности ${m[1].trim()} и руде партии (A×b ${m[2]}) мельница должна давать ${m[3].trim()} т/ч, даёт ${m[4].trim()}`;
  t = t.trim();
  if (/перегруз загрузки/.test(whole)) t += '. Перегруз, крупное питание, износ футеровки или руда твёрже — пока не различить';
  else if (/износ футеровки или руда твёрже/.test(whole)) t += '. Износ футеровки или руда твёрже — пока не различить';
  if (t.length > 220) t = t.slice(0, 218).replace(/\s+\S*$/, '') + '…';
  /* a reason that only repeats the title ("дробилка стоит") says nothing */
  if (t.length < 25) return '';
  return t.charAt(0).toUpperCase() + t.slice(1) + (/[.…]$/.test(t) ? '' : '.');
};
AKT.issueAdvice = n => {
  const t = String(AKT.val(n, 'text') || '');
  const m = /Совет:\s*([^·]+)/.exec(t);
  return m ? m[1].replace(/\s*\[оценка на модели\]/g, '').replace(/\s*\(прибытие и ремонт:[^)]*\)/, '').trim() : '';
};
/* the whole money of the issue before the module's text: losses now, later, none, S0 (old wording kept for tables) */
AKT.issueMoney = n => { const m = AKT.issueMain(n); return m.text + (m.small ? ' ' + m.small : ''); };

/* ------------------------------------------------------------ status line */
/* «Что сейчас и что делать», from the data, rule by rule (spec 2.2) */
AKT.warming = () => {
  const st = AKT.st('site');
  if (st === 'WARMUP') return true;
  const t = AKT.simTime, p = AKT.num('mod-priority', 'processed_sim_time');
  return t != null && t >= 0 && (p == null || String(AKT.val('mod-priority', 'idSimulationRun') || '') !== AKT.run) && !AKT.issues().length;
};
AKT.staleSec = () => AKT.polled ? Date.now() / 1000 - AKT.polled : null;
AKT.isStale = () => {
  const age = AKT.staleSec();
  const speed = AKT.num('site', 'speed');
  return !!AKT.err && (age == null || age > 10) || (age != null && age > 10 && speed);
};
AKT.nowLine = () => {
  const out = { text: '', btn: null, chip: '' };
  const scen = AKT.scenario();
  if (scen) out.chip = 'Учебный сценарий: ' + AKT.scenarioRu(scen);
  /* the season label: only while winter is on (UI rule 1) */
  if (AKT.num('water', 'winter') === 1) out.chip = 'Зима' + (out.chip ? ' · ' + out.chip : '');
  if (!AKT.polled) { out.text = 'Загружаю состояние фабрики…'; return out; }
  if (AKT.isStale()) { out.text = `⚠ Нет связи с двойником ${AKT.fmt(AKT.staleSec())} с — числа ниже последние полученные.`; out.stale = true; return out; }
  const st = AKT.st('site');
  const issues = AKT.issues();
  if (st === 'WARMUP') { out.text = 'Модель прогревается: проходит 06:00 → 08:00, через минуту начнётся смена. Беды появятся через ~1 мин.'; return out; }
  const s0 = issues.find(i => String(AKT.val(i, 'safety_class') || '') === 'S0');
  const top = s0 || issues.find(i => AKT.rankNo(i) != null) || issues[0];
  if (top) {
    const node = AKT.issueNode(top), place = node ? AKT.nameRu(node) : AKT.issueTitle(top);
    const role = AKT.issueRole(top), acc = AKT.roleAcc(AKT.roleFirst(role)) || 'ответственного';
    const sign = AKT.rankSign(top) || '•';
    const called = AKT.issueCalled(top);
    const per = AKT.issuePerson(top);
    if (s0 && !called) {
      out.text = `Опасно для людей: ${sign} ${place} — ${AKT.kindRu(AKT.val(top, 'kind') || '')}. Сначала безопасность: позвать ${acc}.`;
      out.btn = { issue: top, label: 'Позвать ' + acc };
      return out;
    }
    if (called) {
      const pi = per ? AKT.personInfo(per) : null;
      const next = issues.find(i => i !== top && !AKT.issueCalled(i));
      const who = AKT.roleFirst(role) || 'ответственный';
      const where = pi && pi.tr ? `в пути, будет ≈ ${AKT.clock(pi.tr.eta)}` : (pi && /WORK|BUSY/.test(pi.st) ? `на месте, чинит${pi.free != null && pi.free >= 0 ? ' до ' + AKT.clockDay(pi.free) : ''}` : 'позван');
      const from = AKT.num(top, 'loss_from');
      const money = AKT.lossNow(top) ? ` Теряем ${AKT.approx(AKT.num(top, 'loss_usd_h'))}/ч.` : (from != null ? ` Потерь пока нет: запас до ${AKT.clockDay(from)}.` : '');
      out.text = `${AKT.rankSign(top) ? AKT.rankSign(top) + ' ' : 'Беда: '}${AKT.issueTitle(top)} — ${who.charAt(0).toLowerCase() + who.slice(1)} ${where}.${money}`
        + (next ? ` Следующее: ${AKT.rankSign(next) || '•'} ${AKT.nameRu(AKT.issueNode(next))} — ${AKT.issuePrice(next)}.` : ' Других бед нет.');
      if (next) out.btn = { issue: next, label: 'Позвать ' + AKT.roleAcc(AKT.roleFirst(AKT.issueRole(next))) };
      return out;
    }
    /* one price: an hour of delay, or till when to call */
    const dot = s => /\.$/.test(s) ? s : s + '.';
    if (AKT.lossNow(top)) out.text = dot(`Главное: ${sign} ${AKT.issueTitle(top)} — ${AKT.issuePrice(top)}`);
    else {
      const from = AKT.num(top, 'loss_from');
      out.text = dot(`${sign} ${AKT.issueTitle(top)}: потерь пока нет${from != null ? ` (запас до ${AKT.clockDay(from)})` : ''} — ${AKT.issuePrice(top)}`);
    }
    out.btn = { issue: top, label: 'Позвать ' + acc };
    return out;
  }
  if (AKT.warming()) { out.text = 'Модель прогревается: модуль бед ещё не посчитал этот прогон — беда, если есть, появится через ~1 мин.'; return out; }
  const t = AKT.simTime;
  if (st === 'PAUSED' && t != null && Math.round(t) % 1440 >= 1200) { out.text = `Смена закончилась (${AKT.clock(t)}). Бед нет.`; return out; }
  /* no issue in the queue yet, but something deviates: say so (the module counts issues every few model minutes) */
  const KEY = ['crusher-1', 'crusher-2', 'conveyor-1', 'conveyor-2', 'stockpile-1', 'stockpile-2', 'line-1', 'line-2', 'sag-1', 'sag-2', 'pebble-1', 'pebble-2', 'filter-1', 'filter-2', 'power', 'water', 'conc-stock'];
  const dev = KEY.filter(n => AKT.things[n] && AKT.levelOf(n)).sort((a, b) => AKT.levelOf(a) - AKT.levelOf(b)).slice(0, 3);
  if (dev.length) { out.text = `Бед в очереди нет, но есть отклонения: ${dev.map(n => `${AKT.LV_GLYPH[AKT.levelOf(n)]} ${AKT.nameRu(n)} — ${AKT.stOf(n)}`).join(', ')}. Двойник оценит их за несколько минут модели.`; return out; }
  out.text = `Бед нет. Фабрика работает в норме и даёт ${AKT.f1(AKT.num('site', 'cu_tph'))} т меди в час.`;
  return out;
};
AKT.ctxLine = () => {
  const t = AKT.simTime, speed = AKT.num('site', 'speed'), st = AKT.st('site');
  const paused = st === 'PAUSED' || speed === 0;
  const spd = paused ? '⏸ пауза' : (speed ? `▶ ход ×${AKT.fmt(speed)}${speed === 60 ? ' (минута = час)' : ''}` : '');
  const age = AKT.staleSec();
  return `Время модели <b>${AKT.clockDay(t)}</b> · ${spd}${age != null && age > 4 ? ` · данные на ${AKT.clock(t)} модели` : ''} · смена 08:00–20:00 · медный рудник в Казахстане, фабрика в 2 линии`;
};
let toastTimer = null;
AKT.toast = (text, ms) => {
  let el = document.getElementById('toast');
  if (!el) { el = document.createElement('div'); el.id = 'toast'; el.setAttribute('role', 'status'); document.body.appendChild(el); }
  el.textContent = text; el.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { el.hidden = true; }, ms || 6000);
};
const Now = {
  last: '', btnIssue: '',
  update() {
    const sec = document.getElementById('now'); if (!sec) return;
    const ctx = document.getElementById('now-ctx'), line = document.getElementById('now-line'), chip = document.getElementById('now-chip');
    const c = AKT.ctxLine();
    if (ctx.innerHTML !== c) ctx.innerHTML = c;
    const o = AKT.nowLine();
    const key = (o.chip || '') + '|' + o.text + '|' + (o.btn ? o.btn.issue + o.btn.label : '');
    sec.classList.toggle('stale', !!o.stale);
    if (key === this.last) return;
    this.last = key;
    const act = line.parentNode;
    chip.innerHTML = o.chip ? `<span class="chip scen">${AKT.esc(o.chip)}</span>` : '';
    line.textContent = o.text;
    let b = act.querySelector('button.now-call');
    if (o.btn) {
      if (!b) { b = document.createElement('button'); b.type = 'button'; b.className = 'primary now-call'; act.appendChild(b); b.addEventListener('click', () => Panel.call(b.dataset.issue)); }
      b.textContent = o.btn.label; b.dataset.issue = o.btn.issue;
    } else if (b) b.remove();
    let off = document.querySelector('#now .offer');
    if (!AKT.store.get('akt-tour') && !off && AKT.tour) {
      off = document.createElement('span'); off.className = 'offer';
      off.innerHTML = 'Впервые здесь? <button type="button" class="quiet" data-tour>Как пользоваться</button><button type="button" class="quiet" data-tour-close>Закрыть</button>';
      document.getElementById('now-offer').appendChild(off);
      off.querySelector('[data-tour]').addEventListener('click', () => AKT.tour.start());
      off.querySelector('[data-tour-close]').addEventListener('click', () => { AKT.store.set('akt-tour', 'done'); off.remove(); });
    }
    /* title of the tab follows the trouble (P2-3) */
    const top = AKT.issues().find(i => AKT.rankNo(i) != null);
    document.title = top ? `${AKT.rankSign(top)} ${AKT.nameRu(AKT.issueNode(top))} · ${AKT.issuePrice(top)} — Актогай` : 'Актогай — норма';
    document.documentElement.style.setProperty('--now-h', sec.offsetHeight + 'px');
  },
};

/* --------------------------------------------------------------- polling */
AKT.poll = async function () {
  try {
    const d = await AKT.get('/api/state');
    const things = {};
    for (const t of d.things) things[AKT.name(t.thingId)] = t;
    AKT.things = things; AKT.now = d.now; AKT.polled = Date.now() / 1000; AKT.err = '';
    AKT.run = String(AKT.val('site', 'idSimulationRun') || '');
    AKT.simTime = AKT.num('site', 'sim_time');
  } catch (e) {
    AKT.err = 'нет связи: ' + e.message;
  }
  document.getElementById('err').textContent = AKT.err ? 'нет связи с двойником' : '';
  AKT.notify();
};
AKT.notify = function () {
  for (const fn of AKT.listeners) { try { fn(); } catch (e) { console.error(e); } }
  if (AKT.current && AKT.current.update) { try { AKT.current.update(); } catch (e) { console.error(e); } }
};
AKT.pollJournal = async function () {
  try {
    const d = await AKT.get('/api/journal?range=24h');
    AKT.journal = d.rows || []; AKT.journalAt = Date.now();
  } catch (e) { /* journal is optional: InfluxDB may lag or be empty */ }
  AKT.notify();
};

/* --------------------------------------------------------------- routing */
const MENU = [['plan', 'Обзор'], ['diorama', 'Диорама'], ['site', 'Спутник 3D'], ['line1', 'Линия 1'], ['line2', 'Линия 2'], ['queue', 'Беды']];
const MENU_MORE = [['handover', 'Сдача смены'], ['ore', 'Руда'], ['calib', 'Калибровка'], ['tree', 'Состав двойника'], ['text', 'Всё текстом'], ['legend', 'Легенда и словарь']];
AKT.viewName = () => {
  const v = AKT.params.get('view') || 'plan';
  if (v === 'line') return 'line' + (AKT.params.get('n') || '1');
  if (v === 'card') return 'unit';
  if (v === '3d') return 'diorama';
  return v;
};
AKT.buildMenu = function () {
  const cur = AKT.viewName();
  const nav = document.getElementById('nav');
  const curMore = MENU_MORE.find(([v]) => v === cur);
  nav.innerHTML = MENU.map(([v, t]) => `<a href="${AKT.href('?view=' + v)}" class="${v === cur ? 'cur' : ''}"${v === cur ? ' aria-current="page"' : ''}>${t}${v === 'queue' ? ' <span class="cnt" id="nav-cnt" hidden></span>' : ''}</a>`).join('')
    + `<span class="more"><button type="button" id="nav-more" aria-expanded="false" aria-haspopup="true" class="${curMore ? 'cur' : ''}"${curMore ? ` title="Сейчас: ${curMore[1]}"` : ''}>${curMore ? ({ handover: 'Сдача смены', ore: 'Руда', calib: 'Калибровка', tree: 'Состав', text: 'Текстом', legend: 'Легенда' })[curMore[0]] : 'Ещё'} ▾</button><span class="more-menu" id="nav-more-m" hidden>${MENU_MORE.map(([v, t]) => `<a href="${AKT.href('?view=' + v)}">${t}</a>`).join('')}</span></span>`;
  const mb = document.getElementById('nav-more'), mm = document.getElementById('nav-more-m');
  const setOpen = o => { mm.hidden = !o; mb.setAttribute('aria-expanded', String(o)); };
  mb.addEventListener('click', ev => { ev.stopPropagation(); setOpen(mm.hidden); if (!mm.hidden) mm.querySelector('a').focus(); });
  document.addEventListener('click', ev => { if (!mm.hidden && !mm.contains(ev.target)) setOpen(false); });
  document.addEventListener('keydown', ev => { if (ev.key === 'Escape') setOpen(false); });
};
AKT.updateMenu = () => {
  const c = document.getElementById('nav-cnt'); if (!c) return;
  const n = AKT.issues().length;
  c.hidden = !n; c.textContent = String(n);
  c.parentNode.setAttribute('aria-label', `Беды: ${n}`);
};
AKT.onClick = ev => {
  const a = ev.target.closest ? ev.target.closest('a') : null;
  const pe = ev.target.closest ? ev.target.closest('[data-person]') : null;
  if (pe && !ev.ctrlKey && !ev.metaKey && !ev.shiftKey && ev.button === 0) {
    ev.preventDefault();
    AKT.personCard.open(pe.getAttribute('data-person'), ev.clientX, ev.clientY);
    return;
  }
  if (!a || !AKT.check) return;
  const h = a.getAttribute('href');
  if (h && h.startsWith('?') && !/(^|[?&])check=/.test(h)) a.setAttribute('href', h + '&check=1');
};
/* hot keys when the focus is not in a field: 1 Обзор, 2 Линия 1, 3 Линия 2, 4 Диорама, 5 Беды, ? tour, / glossary */
AKT.onKey = ev => {
  const tg = ev.target;
  if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
  if (tg && (/^(INPUT|TEXTAREA|SELECT)$/.test(tg.tagName) || tg.isContentEditable)) return;
  if (tg && tg.closest && tg.closest('#dio-canvas, #s3-canvas')) return;
  const go = v => { location.search = AKT.href('?view=' + v).slice(1); };
  const map = { 1: 'plan', 2: 'line1', 3: 'line2', 4: 'diorama', 5: 'queue' };
  if (map[ev.key]) { ev.preventDefault(); go(map[ev.key]); }
  else if (ev.key === '?') { ev.preventDefault(); if (AKT.tour) AKT.tour.start(); }
  else if (ev.key === '/') { ev.preventDefault(); if (AKT.glossary) AKT.glossary.open(); }
};
AKT.route = async function () {
  const name = AKT.viewName();
  let view = AKT.views[name];
  let opts = {};
  if (/^line[12]$/.test(name)) { view = AKT.views.line; opts.n = name.slice(4); }
  else if (name === 'unit') { view = AKT.views.card; opts.id = AKT.params.get('id') || AKT.NS + ':site'; }
  if (!view) { view = AKT.views.plan; }
  const stage = document.getElementById('stage');
  if (AKT.current && AKT.current.destroy) { try { AKT.current.destroy(); } catch (e) { console.error(e); } }
  AKT.current = view;
  await view.build(stage, opts);
  if (view.update) view.update();
};

/* ------------------------------------------------------------------ panel */
/* training scenarios: what happens, what to watch (with its countdown source), how to undo */
AKT.SCENARIOS = [
  { id: 'crusher:1', name: 'Встала дробилка', what: 'Дробилка 1 у карьера встанет сейчас, ремонт ≈ 3 ч (бывает до 5 ч).',
    watch: 'Склад руды 1 начнёт убывать; если он кончится раньше ремонта, линия 1 встанет. Двойник покажет беду и кого звать.' },
  { id: 'grid', name: 'Сеть урезала мощность', what: 'Лимит сети 300 → 218 МВт на 2 ч.', watch: 'Нагрузку площадки против лимита и когда лимит снимут.' },
  { id: 'hard:1', name: 'Твёрдая руда', what: 'На линию 1 идёт блок твёрдой руды (A×b 27): мельница будет молоть медленнее.', watch: 'Когда твёрдая руда дойдёт до мельницы SAG-1.' },
  { id: 'reline:1', name: 'Перефутеровка SAG', what: 'Мельница SAG-1 встаёт на плановую замену брони на 126 ч.', watch: 'Когда мельница вернётся; линия 1 стоит.' },
  { id: 'fork', name: 'Две беды сразу', what: 'Скрытый сбой на флотации 1 и поломка дробилки 2 в 09:20; дежурный КИПиА один.', watch: 'Кого звать первым — смотрите карточку ①.' },
  { id: 'water', name: 'Беда с водой', what: 'Сбой водовода и забора свежей воды, растёт давление воды в дамбе.', watch: 'Пьезометры дамбы: давление против тревоги 150 кПа.' },
  { id: 'startup:1', name: 'Пуск мельницы при людях внутри', what: 'Шаровая 1A на ремонте по наряду-допуску, механик внутри; через час кто-то включает команду на пуск.', watch: 'Безопасность людей: беда класса S0 идёт первой, пуск надо отменить.' },
  { id: 'dust', name: 'Пыление пляжа хвостохранилища', what: 'Ветер до 14 м/с над сухим пляжем на 6 ч.', watch: 'Экологическая беда S1 идёт после людей и перед деньгами.' },
  { id: 'winter', name: 'Зима', what: 'Возврат воды с хвостохранилища снижен (лёд), воздух около −15 °C.', watch: 'Метка «Зима» в шапке; беды с водой дороже и срочнее.' },
  { id: 'hpgr_fire', name: 'Пожар на прессе дробления гали', what: 'Пожар на прессе дробления гали: люди рядом, узел остановлен.', watch: 'Безопасность людей: беда класса S0 идёт первой.' },
];
/* the countdown of a running scenario: {text, lv} (lv 3 when less than an hour is left) */
AKT.scenWatch = scen => {
  const k = scen.split('+')[0].split(':'), kind = k[0], n = k[1] || '1';
  const start = AKT.scenStart();
  const t = AKT.simTime;
  const left = (min, what, at) => ({ text: `${what} через ${AKT.dur(min)}${at != null ? ` (в ${AKT.clockDay(at)})` : ''}`, lv: min < 60 ? 3 : 0 });
  if (kind === 'crusher') {
    const sp = `stockpile-${n}`, h = AKT.num(sp, 'hours_left'), lvl = AKT.num(sp, 'level_t');
    if (lvl != null && lvl < 50) return { text: `Склад ${n} пуст — линия ${n} стоит`, lv: 1 };
    const cr = AKT.st(`crusher-${n}`);
    const tail = cr && AKT.stopped(cr) ? `дробилка ${n} стоит` : `дробилка ${n} снова работает`;
    if (h != null && h <= 48) return Object.assign(left(h * 60, `Следите: склад ${n} кончится`, t != null ? t + h * 60 : null), { text: `Следите: склад ${n} кончится через ${AKT.durH(h)}${t != null ? ` (в ${AKT.clockDay(t + h * 60)})` : ''} · ${tail}` });
    return { text: `Следите: склад ${n} — ${AKT.fmt(lvl)} т, хватит больше чем на 2 суток · ${tail}`, lv: 0 };
  }
  if (kind === 'grid') {
    const mw = AKT.num('power', 'site_mw'), lim = AKT.num('power', 'grid_limit_mw');
    const rest = start != null && t != null ? start + 120 - t : null;
    return { text: `Следите: нагрузка ${AKT.fmt(mw)} из ${AKT.fmt(lim)} МВт${rest != null && rest > 0 ? ` · лимит снимут через ${AKT.dur(rest)}` : ''}`, lv: rest != null && rest < 60 && rest > 0 ? 3 : 0 };
  }
  if (kind === 'hard') {
    const e = AKT.num('mod-ore', `next_hard_eta_h_l${n}`);
    return e != null ? left(e * 60, `Следите: твёрдая руда в мельнице SAG-${n}`, t != null ? t + e * 60 : null) : { text: 'Следите: модуль руды ещё не видит твёрдую партию в плане на 12 ч', lv: 0 };
  }
  if (kind === 'reline') {
    const until = AKT.num(`sag-${n}`, 'reline_until_min') ?? (start != null ? start + 126 * 60 : null);
    return until != null && t != null ? { text: `Следите: мельница SAG-${n} вернётся через ${AKT.dur(until - t)} (в ${AKT.clockDay(until)})`, lv: 0 } : { text: `Мельница SAG-${n} на перефутеровке`, lv: 0 };
  }
  if (kind === 'water') {
    const ps = Object.keys(AKT.things).filter(x => AKT.cat(x) === 'piezo');
    const top = ps.map(x => [x, AKT.num(x, 'kpa'), AKT.num(x, 'sp_kpa') ?? 150]).filter(x => x[1] != null).sort((a, b) => (b[1] / b[2]) - (a[1] / a[2]))[0];
    return top ? { text: `Следите: ${AKT.nameRu(top[0]).replace(/^Пьезометр дамбы /, 'пьезометр ')} — ${AKT.fmt(top[1])} кПа, тревога от ${AKT.fmt(top[2])}`, lv: top[1] >= top[2] ? 1 : (top[1] >= 0.9 * top[2] ? 3 : 0) } : { text: 'Следите: давление в дамбе и забор воды', lv: 0 };
  }
  if (kind === 'hpgr_fire') {
    const s0 = AKT.issues().find(i => String(AKT.val(i, 'safety_class') || '') === 'S0');
    return s0 ? { text: `Безопасность людей: ${AKT.rankSign(s0) || '•'} ${AKT.issueTitle(s0)} — звать ${AKT.roleAcc(AKT.roleFirst(AKT.issueRole(s0)))} сейчас`, lv: 1 }
      : (Object.keys(AKT.things).some(x => /^pebble/.test(x) && AKT.num(x, 'fire') === 1)
        ? { text: 'Следите: как только двойник увидит пожар, он поставит его первым (класс S0, опасно для людей)', lv: 0 }
        : { text: `Пожар потушен. Следите, когда пресс дробления гали снова заработает: сейчас ${AKT.stOf('pebble-' + n)}`, lv: 0 });
  }
  if (kind === 'fork') return { text: 'Следите: кого звать первым — смотрите карточку ① и строку ②', lv: 0 };
  if (kind === 'startup') return { text: 'Следите: команда на пуск при людях внутри мельницы — беда S0, отменить пуск', lv: 1 };
  if (kind === 'dust') return { text: `Следите: ветер ${AKT.fmt(AKT.num('water', 'wind_ms'))} м/с, сухой пляж ${AKT.fmt(AKT.num('water', 'beach_dry_pct'))} %`, lv: 0 };
  if (kind === 'winter') return { text: `Следите: воздух ${AKT.fmt(AKT.num('water', 'air_temp_c'))} °C, возврат воды снижен`, lv: 0 };
  return { text: '', lv: 0 };
};
/* model minute when the running scenario started: the control command of the same scenario */
AKT.scenStart = () => {
  const c = AKT.val('control', 'scenario');
  if (c && typeof c === 'object' && c.id && AKT.scenario().split('+').some(p => p === c.id || p.startsWith(String(c.id).split(':')[0])) && typeof c.sim_time === 'number') {
    /* a scenario that restarts the shift runs in a new run from 08:00 (the command's time is the old run's clock) */
    if (AKT.simTime != null && c.sim_time > AKT.simTime) return 480;
    return c.sim_time;
  }
  return Panel.scen && Panel.scen.id === AKT.scenario() ? Panel.scen.t : null;
};
const LOSS_NODES = { 'sag-1': 'Мельница SAG-1', 'sag-2': 'Мельница SAG-2', 'cyclones-1': 'гидроциклоны 1', 'cyclones-2': 'гидроциклоны 2', 'flot-1': 'флотация 1', 'flot-2': 'флотация 2' };
const Panel = AKT.panel = {
  built: false, open: '', snoozeFor: '', hist: null, histAt: 0, scen: null, msgTimer: null,
  build() {
    const p = document.getElementById('panel');
    const simOpen = false;      // «Пульт модели» closed by default (open with ?sim=1)
    p.innerHTML = `
<div id="p-banner" class="banner" hidden>
  <div class="b-h"><span class="tag-s">Учебный сценарий:</span> <span id="b-name"></span> · <span id="b-run"></span></div>
  <div class="watch" id="b-watch"></div>
  <div id="b-before"></div>
  <div class="b-btns" id="b-btns"><button type="button" id="b-stop">Остановить сценарий…</button></div>
  <div class="b-btns" id="b-confirm" hidden><span>Остановить? Фабрика сразу вернётся в состояние, как если бы сценария не было, на то же время модели. Прогон продолжится.</span>
    <button type="button" class="primary" id="b-yes">Да, остановить</button><button type="button" id="b-no">Нет</button></div>
</div>
<div id="p-check" class="check-note" hidden><b>Режим проверки модели.</b> Показаны журнал симулятора (скрытые причины прогона) и копии модели без сценария; диспетчеру на смене это недоступно.<div id="p-hidden" class="p-sub" hidden></div></div>
<div class="tiles" id="tiles">
  <div class="tile" id="k-loss" role="group"><div class="l">Теряем сейчас</div><div class="v" id="k-loss-v" aria-busy="true">—</div><div class="d" id="k-loss-d"></div></div>
  <div class="tile" id="k-cu" role="group"><div class="l">Медь в концентрат</div><div class="v" id="k-cu-v">—</div><div class="d" id="k-cu-d"></div></div>
  <div class="tile" id="k-ore" role="group"><div class="l">Руда на фабрику</div><div class="v" id="k-ore-v">—</div><div class="d" id="k-ore-d"></div></div>
  <div class="tile" id="k-rec" role="group"><div class="l"><span class="term" data-term="recovery">Извлечение</span> меди</div><div class="v" id="k-rec-v">—</div><div class="d" id="k-rec-d"></div></div>
  <div class="tile" id="k-mw" role="group"><div class="l">Сеть</div><div class="v" id="k-mw-v">—</div><div class="d" id="k-mw-d"></div></div>
  <div class="tile" id="k-usd" role="group" title="Сколько стоит медь, которую фабрика даёт за час, по цене LME за вычетом платы переработчику"><div class="l">Стоимость меди</div><div class="v" id="k-usd-v">—</div><div class="d" id="k-usd-d">по цене <span class="term" data-term="lme">LME</span></div></div>
</div>
<h3 id="q-h">Беды <span class="h-sub" id="q-hs"></span><a href="${AKT.href('?view=queue')}">все беды →</a></h3>
<article id="topcard" class="topcard" tabindex="-1" aria-labelledby="tc-ttl" hidden>
  <div class="t-head"><span class="rk" id="tc-rk"></span><span id="tc-lv"></span><span class="ttl" id="tc-ttl"></span><span class="badge st-grey" id="tc-st"></span></div>
  <div class="money" id="tc-money"></div>
  <div class="delay" id="tc-delay"></div>
  <div class="who" id="tc-who"></div>
  <div class="who" id="tc-chain" hidden></div>
  <div class="delay" id="tc-choice" hidden></div>
  <div class="why" id="tc-why"></div>
  <div class="acts" id="tc-acts"><button type="button" class="primary" id="tc-call"></button><span class="called-chip" id="tc-called" hidden></span><button type="button" id="tc-snz">Не сейчас…</button><span class="p-sub" id="tc-msg"></span></div>
  <form class="snooze" id="tc-form" hidden>
    <fieldset><legend>Почему не сейчас? Запишется в журнал смены.</legend>
      <label><input type="radio" name="snz" value="Уже занимаемся" checked> Уже занимаемся</label>
      <label><input type="radio" name="snz" value="Некого послать"> Некого послать</label>
      <label><input type="radio" name="snz" value="Считаю, что двойник ошибся"> Считаю, что двойник ошибся</label>
      <label><input type="radio" name="snz" value="Другое"> Другое</label>
      <input type="text" id="tc-other" placeholder="Своими словами (обязательно для «Другое»)" maxlength="200" aria-label="Причина своими словами">
    </fieldset>
    <div class="s-btns"><button type="submit" class="primary">Записать</button><button type="button" id="tc-cancel">Отмена</button><span class="s-err" id="tc-err"></span></div>
  </form>
  <details id="tc-more"><summary>Подробнее</summary><div class="full" id="tc-full"></div></details>
</article>
<div id="tc-empty" class="empty" hidden></div>
<div id="q-more"></div>
<div class="p-sub" id="ask-quick">Спросить двойник:
  <button type="button" class="quiet" data-ask="why_first">почему эта беда первая?</button>
  <button type="button" class="quiet" data-ask="loss">сколько теряем?</button>
  <button type="button" class="quiet" data-ask="who">кого звать?</button>
  <button type="button" class="quiet" data-ask="">ещё вопросы →</button></div>
<h3 id="ppl-h">Люди</h3>
<div id="p-ppl" class="people"></div>
<h3><span class="term" data-term="loss_where">Где теряем медь</span> <span class="h-sub">≈ расчёт модели</span></h3>
<div id="p-losses"></div>
<div id="p-result" hidden><h3 id="p-result-title">Итог смены</h3><div id="p-result-body"></div></div>
<h3>Журнал смены <a href="${AKT.href('?view=queue')}#q-journal">весь журнал →</a></h3>
<ul class="journal" id="p-journal"></ul>
<details id="sim"${simOpen ? ' open' : ''}><summary>Пульт модели <span class="h-sub">— учебная модель фабрики, не диспетчерская</span></summary>
  <div class="sim-row"><span class="sim-lbl">Скорость</span>
    <button type="button" data-speed="0">⏸ Пауза</button><button type="button" data-speed="60">×60</button><button type="button" data-speed="300">×300</button><button type="button" data-speed="1200">×1200 (быстро до 20:00)</button>
    <span id="sim-lag" class="p-sub"></span></div>
  <div class="sim-row"><span class="sim-lbl">Учебные сценарии</span><span class="p-sub" id="sim-warm"></span></div>
  <div class="sc-list" id="sc-list">${AKT.SCENARIOS.map(s => `<div class="sc" data-sc="${s.id}"><span class="sc-n">${AKT.esc(s.name)}</span><span class="sc-d">${AKT.esc(s.what)}</span><button type="button" data-run="${s.id}">Запустить…</button>
    <div class="sc-confirm" hidden><p><b>Что случится:</b> ${AKT.esc(s.what)}</p><p><b>За чем следить:</b> ${AKT.esc(s.watch)} Обратный отсчёт появится вверху панели.</p><p><b>Как отменить:</b> «Остановить сценарий…» в синей рамке вверху панели — фабрика вернётся в состояние без сценария, на то же время модели.</p><p class="p-sub">Скорость: ×60 (минута = час).</p>
    <div class="b"><button type="button" class="primary" data-go="${s.id}">Запустить</button><button type="button" data-no>Отмена</button></div></div></div>`).join('')}</div>
  <div class="sim-row"><span class="sim-lbl">Смена заново</span><label>номер прогона (seed) <input type="number" id="sim-seed" min="1" max="99999" step="1" value="42"></label>
    <button type="button" id="sim-reset">Начать смену заново (08:00)</button></div>
  <div class="sim-row"><label class="chk"><input type="checkbox" id="chk"${AKT.check ? ' checked' : ''}> Режим проверки модели</label><span class="p-sub">— показывает скрытые причины прогона и ход без сценария (диспетчеру недоступно)</span></div>
  <div class="sim-row runid" id="sim-run"></div>
  <div class="sim-row" id="p-msg" role="status" aria-live="polite"></div>
</details>`;
    const $ = id => document.getElementById(id);
    p.querySelectorAll('[data-speed]').forEach(b => b.addEventListener('click', () => Panel.cmd('/api/speed', { value: Number(b.dataset.speed) }, b.dataset.speed === '0' ? 'пауза' : 'скорость ×' + b.dataset.speed)));
    p.querySelectorAll('[data-run]').forEach(b => b.addEventListener('click', () => {
      const card = b.closest('.sc'), box = card.querySelector('.sc-confirm');
      p.querySelectorAll('.sc').forEach(c => { if (c !== card) { c.classList.remove('open'); c.querySelector('.sc-confirm').hidden = true; } });
      box.hidden = !box.hidden; card.classList.toggle('open', !box.hidden);
      if (!box.hidden) box.querySelector('[data-go]').focus();
    }));
    p.querySelectorAll('[data-go]').forEach(b => b.addEventListener('click', () => {
      const card = b.closest('.sc'); card.querySelector('.sc-confirm').hidden = true; card.classList.remove('open');
      Panel.scenario(b.dataset.go);
    }));
    p.querySelectorAll('[data-no]').forEach(b => b.addEventListener('click', () => { const card = b.closest('.sc'); card.querySelector('.sc-confirm').hidden = true; card.classList.remove('open'); card.querySelector('[data-run]').focus(); }));

    let resetArm = null;
    $('sim-reset').addEventListener('click', () => {
      const b = $('sim-reset');
      if (!resetArm) { b.textContent = 'Да, начать заново — текущий прогон закончится'; b.classList.add('primary'); resetArm = setTimeout(() => { resetArm = null; b.textContent = 'Начать смену заново (08:00)'; b.classList.remove('primary'); }, 6000); return; }
      clearTimeout(resetArm); resetArm = null; b.textContent = 'Начать смену заново (08:00)'; b.classList.remove('primary');
      const seed = Math.max(1, Math.round(Number($('sim-seed').value) || 42));
      Panel.cmd('/api/reset', { seed }, `смена заново, прогон ${seed}`);
    });
    $('chk').addEventListener('change', ev => {
      const q = new URLSearchParams(location.search);
      if (ev.target.checked) q.set('check', '1'); else q.delete('check');
      location.search = q.toString();
    });
    $('b-stop').addEventListener('click', () => { $('b-btns').hidden = true; $('b-confirm').hidden = false; $('b-yes').focus(); });
    $('b-no').addEventListener('click', () => { $('b-btns').hidden = false; $('b-confirm').hidden = true; $('b-stop').focus(); });
    $('b-yes').addEventListener('click', async () => {
      $('b-btns').hidden = false; $('b-confirm').hidden = true;
      const ok = await Panel.cmd('/api/cancel', {}, 'остановка сценария');
      if (ok) AKT.toast(`Сценарий остановлен в ${AKT.clock(AKT.simTime)}. Фабрика идёт как без сценария.`);
    });
    $('tc-call').addEventListener('click', () => Panel.call(Panel.cardIssue));
    $('tc-snz').addEventListener('click', () => { $('tc-form').hidden = false; $('tc-err').textContent = ''; $('tc-form').querySelector('input[type=radio]:checked').focus(); });
    $('tc-cancel').addEventListener('click', () => { $('tc-form').hidden = true; $('tc-snz').focus(); });
    $('tc-form').addEventListener('submit', ev => { ev.preventDefault(); Panel.snooze(Panel.cardIssue); });
    p.querySelectorAll('[data-ask]').forEach(b => b.addEventListener('click', () => { if (AKT.ask) AKT.ask.open(b.dataset.ask || ''); }));
    this.built = true;
  },
  msg(text) {
    const m = document.getElementById('p-msg'); if (m) m.textContent = text;
    const tm = document.getElementById('tc-msg'); if (tm && this.cardIssue && /позвали|отложено|ошибка/.test(text)) { tm.textContent = text; clearTimeout(this.msgTimer); this.msgTimer = setTimeout(() => { tm.textContent = ''; }, 8000); }
  },
  async cmd(url, body, what) {
    this.msg(`${what}: отправляю…`);
    try {
      await AKT.post(url, body);
      this.msg(`${what}: принято в ${AKT.clock(AKT.simTime)} модели`);
      setTimeout(AKT.poll, 300); setTimeout(AKT.pollJournal, 1500); setTimeout(AKT.pollJournal, 12000);
      return true;
    } catch (e) { this.msg(`${what}: не получилось — ${e.message}. Нажмите ещё раз.`); return false; }
  },
  async scenario(id) {
    const body = { id };
    if (id === 'fork') { body.preset = 'fork'; body.kip = Number(AKT.params.get('kip') || 1); body.auto = Number(AKT.params.get('auto') ?? 1); }
    if (AKT.params.get('safety')) body.safety = Number(AKT.params.get('safety'));
    if (AKT.params.get('speed')) body.speed = Number(AKT.params.get('speed'));
    const s = AKT.SCENARIOS.find(x => x.id === id);
    this.scen = { id, t: AKT.simTime, cu: AKT.num('site', 'cu_tph'), tph: AKT.num('site', 'tph') };
    const ok = await Panel.cmd('/api/scenario', body, 'сценарий «' + (s ? s.name : id) + '»');
    if (ok) AKT.toast(`Сценарий «${s ? s.name : id}» запущен. Обратный отсчёт — вверху панели; остановить — там же.`);
  },
  async call(issue) {
    if (!issue) return;
    const role = AKT.issueRole(issue), place = AKT.nameRu(AKT.issueNode(issue));
    const chain = AKT.val(issue, 'chain') || {}, via = String(chain.via || '');
    const pick = via ? (chain.items || []).find(x => x.person === chain.pick) : null;
    const acc = pick ? pick.name : AKT.roleAcc(AKT.roleFirst(role));
    const ok = await Panel.cmd('/api/call', { issue, role: pick ? pick.name : role, text: `Позвать ${via === 'deputy' ? 'заместителя: ' : via === 'head' ? 'начальника смены: ' : ''}${acc} к ${place}`, via }, `позвали ${acc}`);
    if (ok) {
      AKT.calls[issue + '|' + AKT.run] = AKT.simTime ?? 0;
      AKT.toast(`Записано в журнал смены: позвали ${acc} к ${place} в ${AKT.clock(AKT.simTime)}.`);
      this.update(); Now.last = ''; Now.update();
    }
  },
  /* «не прибыл»: напомнить вызванному или позвать следующего — запись в журнал смены */
  async remind(issue, next) {
    if (!issue) return;
    const role = AKT.issueRole(issue), place = AKT.nameRu(AKT.issueNode(issue));
    const text = next ? `Не прибыл к ${place}: позвать следующего` : `Не прибыл к ${place}: напомнить`;
    const ok = await Panel.cmd('/api/remind', { issue, role, text, next: !!next }, next ? 'позвали следующего' : 'напомнили');
    if (ok) AKT.toast(`Записано в журнал смены в ${AKT.clock(AKT.simTime)}: ${next ? 'позвали следующего' : 'напомнили'} (${place}).`);
  },
  async snooze(issue) {
    const f = document.getElementById('tc-form');
    const v = (f.querySelector('input[name=snz]:checked') || {}).value || '';
    const other = document.getElementById('tc-other').value.trim();
    if (v === 'Другое' && !other) { document.getElementById('tc-err').textContent = 'Напишите причину в поле выше.'; document.getElementById('tc-other').focus(); return; }
    const reason = v === 'Другое' ? other : (other ? `${v}: ${other}` : v);
    const ok = await Panel.cmd('/api/snooze', { issue, role: AKT.issueRole(issue), reason }, 'отложено');
    if (ok) {
      f.hidden = true; document.getElementById('tc-other').value = '';
      AKT.toast(`Отложено в ${AKT.clock(AKT.simTime)}: ${reason}. Записано в журнал смены.`);
    } else document.getElementById('tc-err').textContent = 'Не записалось. Нажмите «Записать» ещё раз.';
  },
  /* history for the KPI deltas and sparklines: once a minute, no skeleton (old values stay) */
  async loadHist() {
    if (Date.now() - this.histAt < 60000 || !AKT.run) return;
    this.histAt = Date.now();
    try {
      const [s, l1, l2] = await Promise.all([AKT.history('site', ['tph', 'cu_tph', 'power_mw'], '2h'),
        AKT.history('line-1', ['recovery', 'tph'], '2h'), AKT.history('line-2', ['recovery', 'tph'], '2h')]);
      const ok = p => typeof p.sim_time === 'number' && p.sim_time > 0;
      const by = {};
      for (const p of (l1.points || []).filter(ok)) by[p.sim_time] = { r1: p.recovery, t1: p.tph };
      for (const p of (l2.points || []).filter(ok)) Object.assign(by[p.sim_time] = by[p.sim_time] || {}, { r2: p.recovery, t2: p.tph });
      const rec = Object.keys(by).map(Number).sort((a, b) => a - b).map(t => { const o = by[t]; const w = (o.t1 || 0) + (o.t2 || 0); return { t, v: w > 0 && o.r1 != null && o.r2 != null ? (o.r1 * (o.t1 || 0) + o.r2 * (o.t2 || 0)) / w : null }; }).filter(o => o.v != null && o.v > 0);
      const site = (s.points || []).filter(ok).sort((a, b) => a.sim_time - b.sim_time);
      const ser = f => site.filter(p => typeof p[f] === 'number' && p[f] >= 0).map(p => ({ t: p.sim_time, v: p[f] }));
      this.hist = { cu: ser('cu_tph'), tph: ser('tph'), mw: ser('power_mw'), rec };
      this.update();
    } catch (e) { /* history is optional */ }
  },
  update() {
    if (!this.built) return;
    const $ = id => document.getElementById(id);
    const set = (id, text) => { const e = $(id); if (e && e.textContent !== text) e.textContent = text; };
    const html = (id, h) => { const e = $(id); if (e && e._raw !== h) { e._raw = h; e.innerHTML = h; if (AKT.glossify) AKT.glossify(e); } };
    const st = AKT.st('site');
    const speed = AKT.num('site', 'speed'), fact = AKT.num('site', 'speed_fact');
    const warm = st === 'WARMUP';
    this.loadHist();
    AKT.updateMenu();
    /* «Пульт модели» */
    document.querySelectorAll('#sim [data-speed]').forEach(b => {
      const on = ((st === 'PAUSED' || speed === 0) && b.dataset.speed === '0') || (st !== 'PAUSED' && speed !== 0 && Number(b.dataset.speed) === speed);
      b.setAttribute('aria-pressed', String(on)); b.disabled = warm;
    });
    set('sim-lag', fact != null && speed && Math.abs(fact - speed) / speed > 0.15 ? `модель не успевает: реально ×${AKT.fmt(fact)}` : '');
    document.querySelectorAll('#sim [data-run], #sim [data-go]').forEach(b => { b.disabled = warm; });
    set('sim-warm', warm ? 'доступно после 08:00 (модель прогревается)' : '');
    set('sim-run', `прогон ${AKT.run || '—'} · seed ${AKT.fmt(AKT.num('site', 'seed'))} · данные: Ditto и InfluxDB через сервер стенда${AKT.num('site', 'degraded') ? ' · неповторяемый (были потери сообщений)' : ''}`);
    const seedEl = $('sim-seed'); if (seedEl && document.activeElement !== seedEl && AKT.num('site', 'seed') != null && !seedEl.dataset.touched) seedEl.value = String(AKT.num('site', 'seed'));

    /* scenario banner */
    const scen = AKT.scenario();
    $('p-banner').hidden = !scen;
    if (scen) {
      if (!this.scen || this.scen.id !== scen) {
        /* opened during a scenario: "before" from the history at its start */
        this.scen = { id: scen, t: AKT.scenStart(), cu: null, tph: null };
        const s0 = this.scen;
        if (s0.t != null) AKT.history('site', ['cu_tph', 'tph'], '12h').then(d => {
          const pts = (d.points || []).filter(p => typeof p.sim_time === 'number' && p.sim_time <= s0.t && p.cu_tph >= 0).sort((a, b) => b.sim_time - a.sim_time);
          if (pts[0]) { s0.cu = pts[0].cu_tph; s0.tph = pts[0].tph; this.update(); }
        }).catch(() => { /* optional */ });
      }
      const start = AKT.scenStart() ?? this.scen.t;
      set('b-name', AKT.scenarioRu(scen));
      set('b-run', start != null && AKT.simTime != null ? `идёт ${AKT.dur(AKT.simTime - start)}` : 'идёт');
      const w = AKT.scenWatch(scen);
      const we = $('b-watch'); set('b-watch', (w.lv ? '△ ' : '') + w.text); we.className = 'watch' + (w.lv ? ' lv-3' : '');
      const b = this.scen;
      set('b-before', b && b.cu != null && start != null ? `До сценария (${AKT.clock(start)}): медь ${AKT.f1(b.cu)} т/ч → сейчас ${AKT.f1(AKT.num('site', 'cu_tph'))} т/ч` : '');
    }
    $('p-check').hidden = !AKT.check;
    const truth = AKT.check ? AKT.val('validation-sim', 'truth_log') : null;
    $('p-hidden').hidden = !truth;
    set('p-hidden', truth ? 'Скрытые причины прогона (журнал симулятора): ' + truth : '');

    /* six numbers */
    const issues = AKT.issues();
    const tph = AKT.num('site', 'tph'), cu = AKT.num('site', 'cu_tph');
    const g1 = AKT.num('flot-1', 'feed_cu'), g2 = AKT.num('flot-2', 'feed_cu');
    const t1 = AKT.num('line-1', 'tph') || 0, t2 = AKT.num('line-2', 'tph') || 0;
    const grade = (g1 != null || g2 != null) ? ((g1 || 0) * t1 + (g2 || 0) * t2) / ((t1 + t2) || 1) : null;
    const r1 = AKT.num('line-1', 'recovery'), r2 = AKT.num('line-2', 'recovery');
    const rec = (r1 != null || r2 != null) ? ((r1 || 0) * t1 + (r2 || 0) * t2) / ((t1 + t2) || 1) : null;
    const lossNow = issues.filter(AKT.lossNow).reduce((s, i) => s + (AKT.num(i, 'loss_usd_h') || 0), 0);
    const H = this.hist;
    const ago = (ser, v) => { if (!ser || ser.length < 2 || v == null || AKT.simTime == null) return null; const t0 = AKT.simTime - 60; const p = ser.filter(o => o.t <= t0).pop(); return p ? v - p.v : null; };
    const spark = ser => {
      if (!ser || ser.length < 3) return '';
      const pts = ser.slice(-120), lo = Math.min(...pts.map(p => p.v)), hi = Math.max(...pts.map(p => p.v)), t0 = pts[0].t, t1x = pts[pts.length - 1].t;
      const X = t => 2 + 56 * (t1x > t0 ? (t - t0) / (t1x - t0) : 1), Y = v => 14 - 12 * (hi > lo ? (v - lo) / (hi - lo) : 0.5);
      const last = pts[pts.length - 1];
      return `<svg width="60" height="16" viewBox="0 0 60 16" aria-hidden="true"><polyline class="spark-mini" points="${pts.map(p => `${X(p.t).toFixed(1)},${Y(p.v).toFixed(1)}`).join(' ')}"/><circle class="spark-dot" cx="${X(last.t).toFixed(1)}" cy="${Y(last.v).toFixed(1)}" r="2"/></svg>`;
    };
    const delta = (d, f, unit) => d == null ? (H ? 'история копится' : '') : `за час: ${d > 0 ? '↑ +' : d < 0 ? '↓ −' : ''}${f(Math.abs(d))}${unit}`;
    const tile = (id, v, d, aria, lv) => {
      set(id + '-v', v); const e = $(id + '-v'); e.removeAttribute('aria-busy');
      html(id + '-d', d);
      const t = $(id); t.className = 'tile' + (lv ? ' lv-' + lv : ''); t.setAttribute('aria-label', aria);
    };
    tile('k-loss', lossNow > 0 ? `${AKT.approx(lossNow)}/ч` : 'нет', lossNow > 0 ? `${AKT.glyph(2)} идут потери у ${AKT.fmt(issues.filter(AKT.lossNow).length)} бед` : 'потерь сейчас нет',
      `Теряем сейчас: ${lossNow > 0 ? 'примерно, по расчёту модели, ' + AKT.usd(lossNow) + ' в час' : 'нет'}`, lossNow > 0 ? 2 : 0);
    const dcu = ago(H && H.cu, cu);
    tile('k-cu', `${AKT.f1(cu)} т/ч`, `${spark(H && H.cu)}<span>${delta(dcu, AKT.f1, '')}</span>`, `Медь в концентрат: ${AKT.f1(cu)} тонны в час${dcu != null ? ', за час ' + AKT.f1(dcu) : ''}`);
    const dt = ago(H && H.tph, tph);
    tile('k-ore', `${AKT.fmt(tph)} т/ч`, `<span>медь в руде ${AKT.f2(grade)} %</span>`, `Руда на фабрику: ${AKT.fmt(tph)} тонн в час, медь в руде ${AKT.f2(grade)} процента${dt != null ? ', за час ' + AKT.fmt(dt) : ''}`);
    $('k-ore').title = `Руда на обе линии; медь в руде ${AKT.f2(grade)} %${dt != null ? ` · за час ${dt > 0 ? '+' : '−'}${AKT.fmt(Math.abs(dt))} т/ч` : ''}`;
    const drec = ago(H && H.rec, rec);
    tile('k-rec', rec == null ? '—' : `${AKT.f1(rec)} %`, `${spark(H && H.rec)}<span>${drec == null ? (H ? 'история копится' : '') : `за час: ${drec > 0 ? '↑ +' : drec < 0 ? '↓ −' : ''}${AKT.f1(Math.abs(drec))} <span class="term" data-term="pp">п.п.</span>`}</span>`, `Извлечение меди: ${AKT.f1(rec)} процента`);
    const mw = AKT.num('site', 'power_mw') ?? AKT.num('power', 'site_mw'), lim = AKT.num('power', 'grid_limit_mw');
    const limited = AKT.st('power') === 'LIMITED' || (AKT.num('power', 'shed_mw') || 0) > 0;
    tile('k-mw', `${AKT.fmt(mw)} из ${AKT.fmt(lim)} МВт`, `<span class="meter" style="flex:1"><i style="width:${lim ? Math.min(100, 100 * (mw || 0) / lim).toFixed(1) : 0}%"></i></span><span>${limited ? AKT.glyph(2) + ' лимит сети' : `запас ${AKT.fmt((lim || 0) - (mw || 0))} МВт`}</span>`,
      `Сеть: ${AKT.fmt(mw)} из ${AKT.fmt(lim)} мегаватт${limited ? ', лимит сети' : ''}`, limited ? 2 : 0);
    tile('k-usd', `≈ ${AKT.money(AKT.usdPerH(cu))}/ч`, `выручка, по цене <span class="term" data-term="lme">LME</span>`, `Стоимость меди: примерно ${AKT.money(AKT.usdPerH(cu))} в час`);
    $('tiles').classList.toggle('stale', AKT.isStale());

    /* issues: card ① (or the one opened from the list), ② ③ in one line each */
    const shown = issues.slice(0, 4);
    if (!shown.includes(this.open)) this.open = shown[0] || '';
    const n = this.open;
    set('q-hs', issues.length ? `${AKT.fmt(issues.length)} · по порядку, кого звать` : '');
    $('topcard').hidden = !n;
    $('tc-empty').hidden = !!n;
    if (!n) {
      set('tc-empty', AKT.warming() ? 'Модель прогревается: модуль бед ещё не посчитал этот прогон, беда появится через ~1 мин.' : (/отклонени/.test(AKT.nowLine().text) ? 'Бед в очереди нет. Отклонения — в строке сверху и на карте; двойник оценит их за несколько минут модели.' : 'Бед нет. Все участки в норме.'));
      $('tc-empty').className = AKT.warming() ? 'empty dash' : 'empty';
    } else this.card(n);
    const more = $('q-more');
    const rows = shown.filter(i => i !== n).slice(0, 3).map(i => {
      const lv = AKT.issueLevel(i), m = AKT.issueMain(i);
      const called = AKT.issueCalled(i);
      const role = AKT.roleAcc(AKT.roleFirst(AKT.issueRole(i)));
      const cb = AKT.num(i, 'call_by');
      const tail = called ? 'позвали' : (cb != null && AKT.simTime != null && cb > AKT.simTime ? `позвать ${role} до ${AKT.clockDay(cb)}` : `позвать ${role}`);
      return `<div class="qline lv-${lv}" role="button" tabindex="0" data-open="${AKT.esc(i)}"><span class="rk">${AKT.rankNo(i) != null ? AKT.fmt(AKT.rankNo(i)) : '•'}</span>${AKT.glyph(lv)}`
        + `<span class="q-t"><b>${AKT.esc(AKT.issueTitle(i))}</b> · <span class="q-s">${AKT.esc((m.text + (m.small ? ' ' + m.small : '')).replace(/^Пока без потерь · /, 'пока без потерь, '))} · ${AKT.esc(tail)}</span></span>`
        + (called ? '' : `<button type="button" data-callq="${AKT.esc(i)}">Позвать</button>`) + '</div>';
    }).join('') + (issues.length > 4 ? `<a class="all-link" href="${AKT.href('?view=queue')}">ещё ${AKT.fmt(issues.length - 4)} — все беды →</a>` : '');
    if (more._raw !== rows) {
      more._raw = rows; more.innerHTML = rows;
      more.querySelectorAll('[data-open]').forEach(r => {
        const open = () => { this.open = r.dataset.open; document.getElementById('tc-form').hidden = true; this.update(); document.getElementById('topcard').focus(); AKT.focusIssue(this.open); };
        r.addEventListener('click', ev => { if (!ev.target.closest('button')) open(); });
        r.addEventListener('keydown', ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); open(); } });
      });
      more.querySelectorAll('[data-callq]').forEach(b => b.addEventListener('click', () => Panel.call(b.dataset.callq)));
    }
    $('ask-quick').hidden = !issues.length;

    /* people: called, on the way and busy in full lines; the free ones in one line */
    const ppl = AKT.people();
    const persons = ppl.filter(p => AKT.cat(p.name) === 'person'), crews = ppl.filter(p => AKT.cat(p.name) === 'crew');
    set('ppl-h', `Люди: ${AKT.fmt(persons.length)} · Бригады: ${AKT.fmt(crews.length)}`);
    const tc = AKT.topCall(), tcp = tc ? tc.person : '';
    const busy = persons.filter(p => p.kind !== 'free').concat(crews.filter(p => p.kind !== 'free'));
    const pRow = p => {
      const person = AKT.cat(p.name) === 'person';
      const i = person ? AKT.personInfo(p.name) : null;
      const chip = person ? `<a href="?view=unit&id=${AKT.id(p.name)}" data-person="${AKT.esc(p.name)}" class="pchip${i.tr ? ' travel' : ''}${tcp === p.name ? ' hl' : ''}">${AKT.esc(i.short)}</a> ` : '';
      const what = i && i.tr ? `в пути к ${AKT.esc(AKT.placeRu(i.tr.to))}, будет ≈ ${AKT.clock(i.tr.eta)}`
        : `${AKT.esc(AKT.stRu(p.st, p.name))}${p.task ? ' · ' + AKT.esc(p.task) : ''}${p.free != null && p.free >= 0 ? ' · до ' + AKT.esc(AKT.clockDay(p.free)) : ''}`;
      return `<li class="${i && i.tr ? 'travel' : 'busy'}">${chip}${person ? '' : AKT.esc(AKT.nameRu(p.name)) + ' — '}${what}</li>`;
    };
    const freeP = persons.filter(p => p.kind === 'free'), freeC = crews.filter(p => p.kind === 'free');
    const fItem = p => { const person = AKT.cat(p.name) === 'person'; const s = person ? AKT.personShort(p.name) : AKT.nameRu(p.name).replace(/^Бригада\s+/, '').replace(/^механиков\s+/, 'мех. '); return `<a href="?view=unit&id=${AKT.id(p.name)}"${person ? ` data-person="${AKT.esc(p.name)}"` : ''} class="pfree${tcp === p.name ? ' hl' : ''}" title="${AKT.esc(AKT.nameRu(p.name))}${p.where ? ' · ' + AKT.esc(p.where) : ''}">${AKT.esc(s)}</a>`; };
    const ph = (busy.length ? `<ul>${busy.map(pRow).join('')}</ul>` : '<div class="empty">Все на местах, никто не вызван.</div>')
      + (freeP.length || freeC.length ? `<div class="pfree-l">Свободны: ${freeP.map(fItem).join(', ')}${freeC.length ? ` · бригады: ${freeC.map(fItem).join(', ')}` : ''}</div>` : '');
    html('p-ppl', ph);

    /* where copper is lost: only real losses; a gain is not a loss; error larger than the value -> «точность низкая» */
    const L = AKT.losses();
    const shownL = L.filter(AKT.lossShown);
    const rest = L.filter(l => !AKT.lossShown(l) && l.status);
    const lh = (shownL.length ? shownL.map(l => {
      const sure = AKT.lossSure(l), u = AKT.unc(l.gap, l.sigma, AKT.f1);
      return `<div class="loss">${sure ? AKT.glyph(2) : ''}<b>${AKT.esc(LOSS_NODES[l.node] || AKT.nameRu(l.node))}</b> · ≈ ${AKT.f1(l.gap)} т меди/ч · ${AKT.approx(l.usd)}/ч${u ? ` · <span class="${sure ? '' : 'p-sub'}">${AKT.esc(u)}</span>` : ''}</div>`;
    }).join('') : `<div class="empty">${L.some(l => l.status) ? 'Заметных потерь нет: расхождения в пределах точности приборов.' : 'Модуль потерь ещё не считал этот прогон.'}</div>`)
      + (rest.length ? `<div class="p-sub">в пределах точности: ${rest.map(l => AKT.esc(LOSS_NODES[l.node] || l.node)).join(', ')}</div>` : '');
    html('p-losses', lh);

    /* shift result: only in «Режим проверки модели» */
    const res = AKT.shiftResult();
    $('p-result').hidden = !res;
    if (res) {
      set('p-result-title', res.kind === 'shift' ? `Итог смены (к ${AKT.clockDay(res.t_min)})` : 'Сравнение с ходом без сценария');
      html('p-result-body', AKT.shiftTable(res));
    }
    /* journal of the shift: this run, 3 last rows */
    const jr = AKT.journal.filter(r => !r.run || r.run === AKT.run).slice(0, 3);
    const jh = jr.length ? jr.map(r => `<li><span class="jt">${AKT.clock(r.sim_time)}</span> ${AKT.esc(AKT.journalRu(r))}</li>`).join('')
      : '<li class="empty dash">В этой смене действий ещё не было. Запись появится здесь через несколько секунд после нажатия.</li>';
    html('p-journal', jh);
  },
  /* the card of one issue (① or the one opened from the list) */
  card(n) {
    const $ = id => document.getElementById(id);
    const set = (id, text) => { const e = $(id); if (e && e.textContent !== text) e.textContent = text; };
    const lv = AKT.issueLevel(n), m = AKT.issueMain(n);
    if (this.cardIssue !== n) { this.cardIssue = n; $('tc-form').hidden = true; $('tc-more').open = false; }
    $('topcard').className = 'topcard lv-' + lv;
    set('tc-rk', AKT.rankNo(n) != null ? AKT.fmt(AKT.rankNo(n)) : '•');
    $('tc-rk').setAttribute('aria-label', AKT.rankNo(n) != null ? `беда номер ${AKT.fmt(AKT.rankNo(n))}` : 'беда вне очереди');
    const lvH = `${AKT.glyph(lv)}<span class="hidden">${lv === 1 ? 'опасно' : lv === 2 ? 'теряем' : 'скоро'}</span>`;
    if ($('tc-lv')._raw !== lvH) { $('tc-lv')._raw = lvH; $('tc-lv').innerHTML = lvH; }
    set('tc-ttl', AKT.issueTitle(n));
    const called = AKT.issueCalled(n);
    set('tc-st', AKT.issueSnoozed(n) ? 'отложено' : called ? (AKT.st(n) === 'IN_WORK' ? 'чинят' : 'позвали') : 'не позвали');
    const money = `${AKT.esc(m.text)}${m.small ? ` <small>${AKT.esc(m.small)}</small>` : ''}`;
    const me = $('tc-money'); if (me._raw !== money) { me._raw = money; me.innerHTML = money; }
    me.className = 'money lv-' + m.lv;
    set('tc-delay', AKT.issueDelay(n));
    const role = AKT.issueRole(n), per = AKT.issuePerson(n);
    const pi = per ? AKT.personInfo(per) : null;
    const who = called
      ? `Позвали: <b>${AKT.esc(AKT.roleAcc(role) || '—')}</b>${pi ? ` — ${AKT.esc(AKT.personAvail(per))}` : ''}.`
      : `Кого звать: <b>${AKT.esc(AKT.roleAcc(role) || '—')}</b>${pi ? ` — ${AKT.esc(AKT.personAvail(per))}${pi.tr ? '' : ', доедет за 20–40 мин'}` : ''}.`;
    const we = $('tc-who'); if (we._raw !== who) { we._raw = who; we.innerHTML = who; if (AKT.glossify) AKT.glossify(we); }
    /* chain of responsibility / work permit and the price of the choice (shown only when there is something to say) */
    const chT = String(AKT.val(n, 'chain_text') || ''), chO = AKT.val(n, 'chain') || {}, choT = String(AKT.val(n, 'choice_text') || '').replace(/\s*\[оценка на модели\]/g, ' (≈)');
    const chH = chT && !called ? `<b>Цепочка:</b> ${AKT.esc(chT)}${chO.line ? `<br><span class="p-sub">${AKT.esc(chO.line)}</span>` : ''}` : '';
    const ce = $('tc-chain'); if (ce._raw !== chH) { ce._raw = chH; ce.innerHTML = chH; } ce.hidden = !chH;
    const co = $('tc-choice'); if (co.textContent !== choT) co.textContent = choT; co.hidden = !choT || called;
    const why = AKT.issueWhy(n);
    const wh = why ? `Почему: ${AKT.esc(why)}` : '';
    const ye = $('tc-why'); if (ye._raw !== wh) { ye._raw = wh; ye.innerHTML = wh; if (AKT.glossify) AKT.glossify(ye); }
    ye.hidden = !why;
    const cb = $('tc-call'), via = String(chO.via || ''), pickNm = (chO.items || []).find(x => x.person === chO.pick);
    const acc = via && pickNm ? pickNm.name : (AKT.roleAcc(AKT.roleFirst(role)) || 'ответственного');
    set('tc-call', (via === 'deputy' ? 'Позвать заместителя: ' : via === 'head' ? 'Позвать начальника смены: ' : 'Позвать ') + acc);
    cb.title = `Запишет вызов в журнал смены; двойник отправит ${acc} к месту беды`;
    cb.hidden = called;
    $('tc-snz').hidden = called;
    const ch = $('tc-called');
    ch.hidden = !called;
    if (called) {
      const at = AKT.calls[n + '|' + AKT.run];
      set('tc-called', `Позвали${at != null ? ' в ' + AKT.clock(at) : ''}${pi && pi.tr ? ` · в пути, будет ≈ ${AKT.clock(pi.tr.eta)}` : ''}`);
    }
    const shift = AKT.num(n, 'loss_shift_usd'), adv = AKT.issueAdvice(n);
    const full = [adv ? 'Совет модуля: ' + adv : '', shift != null && shift > 0 ? `Если никого не звать, за 12 ч ${AKT.approx(shift)}.` : '',
      AKT.val(n, 'safety_class') ? `Класс безопасности: ${AKT.val(n, 'safety_class')}.` : '', 'Текст модуля целиком:', String(AKT.val(n, 'text') || '—').replace(/\s*\[оценка на модели\]/g, ' (≈)').replace(/\s*\[допущение\]/g, ' (д)')].filter(Boolean).join('\n');
    set('tc-full', full);
  },
};
/* a journal row in words */
AKT.journalRu = r => {
  const issueRu = s => AKT.things[s] ? AKT.nameRu(AKT.issueNode(s) || s) : (/^issue-(\d+)$/.test(s || '') ? 'беда ' + s.slice(6) : (s || ''));
  const role = r.role ? AKT.roleAcc(AKT.roleFirst(r.role)) : '';
  if (r.action === 'call') return `позвали ${role}${r.issue ? ' к ' + issueRu(r.issue) : ''}`;
  if (r.action === 'snooze') return `отложили${r.issue ? ' ' + issueRu(r.issue) : ''}: ${r.text || ''}`;
  if (r.action === 'auto_call') return `автовызов ${role}${r.issue ? ' к ' + issueRu(r.issue) : ''}`;
  return `${r.action || ''} ${issueRu(r.issue)} ${r.text || ''}`.trim();
};
const KEY_RU = {
  t_min: 'время модели', copies: 'копии модели', fact: 'как было', base: 'без сценария', loud: 'очередь «кто громче»',
  no_twin: 'без двойника', diff: 'разница с ходом без сценария', fork: '«Две беды сразу»', cu_t: 'медь, т', ore_t: 'руда, т',
  energy_mwh: 'энергия, МВт·ч', water_m3: 'вода, м³', usd: '≈ стоимость', detection_cu_t: 'вклад обнаружения, т меди',
  order_cu_t: 'вклад порядка, т меди', cum_cu_t_base: 'без сценария: медь за смену, т', cum_mwh_base: 'без сценария: энергия за смену, МВт·ч',
  cum_m3_base: 'без сценария: вода за смену, м³', cum_usd_base: 'без сценария: ≈ стоимость за смену', alt_loud_cum_cu_t: '«кто громче»: медь за смену, т',
  alt_notwin_cum_cu_t: 'без двойника: медь за смену, т', alt_loud_cum_usd: '«кто громче»: ≈ стоимость за смену',
  alt_notwin_cum_usd: 'без двойника: ≈ стоимость за смену',
};
AKT.keyRu = k => KEY_RU[k] || k;
AKT.kvTable = obj => {
  if (obj == null || typeof obj !== 'object') return AKT.esc(obj);
  const cell = (k, v) => k === 't_min' && typeof v === 'number' ? AKT.clock(v)
    : typeof v === 'number' ? AKT.fmt(v, Number.isInteger(v) ? 0 : 2) : AKT.esc(v ?? '');
  if (Array.isArray(obj)) {
    if (obj.length && typeof obj[0] === 'object' && obj[0] !== null) {
      const keys = [...new Set(obj.flatMap(r => Object.keys(r)))];
      return `<table class="kv"><tr>${keys.map(k => `<th>${AKT.esc(AKT.keyRu(k))}</th>`).join('')}</tr>${obj.map(r => `<tr>${keys.map(k => `<td class="${typeof r[k] === 'number' ? 'n' : ''}">${cell(k, r[k])}</td>`).join('')}</tr>`).join('')}</table>`;
    }
    return AKT.esc(obj.join(', '));
  }
  return `<table class="kv">${Object.entries(obj).map(([k, v]) => `<tr><td>${AKT.esc(AKT.keyRu(k))}</td><td class="${typeof v === 'number' ? 'n' : ''}">${v !== null && typeof v === 'object' ? AKT.kvTable(v) : cell(k, v)}</td></tr>`).join('')}</table>`;
};
AKT.shiftTable = r => {
  const names = [['fact', 'как было'], ['base', 'без сценария'], ['loud', 'очередь «кто громче»'], ['no_twin', 'без двойника']];
  const c = r.copies || {};
  const ok = k => c[k] && typeof c[k].cu_t === 'number' && c[k].cu_t >= 0;
  const base = ok('base') ? c.base : null;
  const rows = names.filter(([k]) => ok(k)).map(([k, label]) => {
    const x = c[k];
    const d = base && k !== 'base' ? x.cu_t - base.cu_t : null;
    return `<tr><td>${r.kind === 'shift' ? 'как было' : label}</td><td class="n">${AKT.f1(x.cu_t)}</td><td class="n">${d == null ? '—' : (d > 0 ? '+' : d < 0 ? '−' : '') + AKT.f1(Math.abs(d))}</td>`
      + `<td class="n">${AKT.fmt(x.ore_t)}</td><td class="n">${AKT.fmt(x.energy_mwh)}</td><td class="n">≈ ${AKT.money(x.usd)}</td></tr>`;
  }).join('');
  return `<table class="kv"><tr><th></th><th>Медь, т</th><th>к ходу без сценария</th><th>Руда, т</th><th>Энергия, МВт·ч</th><th>≈ Стоимость</th></tr>${rows}</table>`;
};
AKT.planRu = s => String(s || '').replace(/L(\d)\s*:/g, 'линия $1:').replace(/\b0*(\d+)\s+([MST])\b/g,
  (m, n, c) => `${n}${NBSP}${{ M: 'М', S: 'С', T: 'Т' }[c]}`);
AKT.objText = o => {
  const ks = Object.keys(o || {});
  if (!ks.length) return 'нет';
  return ks.map(k => {
    const v = o[k];
    let s;
    if (v !== null && typeof v === 'object') s = AKT.objText(v);
    else if (k === 'sim_time' && typeof v === 'number') s = AKT.clockDay(v);
    else if (k === 't_wall' && typeof v === 'number') s = new Date(v * 1000).toLocaleTimeString('ru-RU');
    else if (k === 'action') s = v === 'call' ? 'позвали' : v === 'snooze' ? 'отложили' : v === 'auto_call' ? 'автовызов' : v;
    else if ((k === 'issue' || k === 'node') && AKT.things[v]) s = AKT.nameRu(v);
    else if ((k === 'id' || k === 'preset') && typeof v === 'string' && v) s = AKT.scenarioRu(v);
    else s = typeof v === 'number' ? AKT.fmt(v, Number.isInteger(v) ? 0 : 2) : String(v);
    return `${AKT.objKeyRu(k)}: ${s}`;
  }).join('; ');
};
AKT.valText = (name, f) => {
  const v = AKT.raw(name, f);
  const u = AKT.unitRu(AKT.unit(name, f));
  if (typeof v === 'number') {
    if (v === -1) return 'нет данных';
    if (AKT.TIME_FEATS.has(f)) return (['call_by', 'free_at', 'loss_from', 'eta'].includes(f) ? AKT.clockDate(v) : AKT.clockDay(v)) + ' модели';
    if (f === 'heartbeat') return new Date(v * 1000).toLocaleTimeString('ru-RU');
    if (f === 'speed' || f === 'speed_fact') return '×' + AKT.fmt(v);
    if (u === 'кВт' && Math.abs(v) >= 1000) return AKT.f1(v / 1000) + NBSP + 'МВт';
    return AKT.fmt(v, Number.isInteger(v) ? 0 : (Math.abs(v) < 1 ? 3 : 1)) + (u ? NBSP + u : '');
  }
  if (typeof v === 'boolean') return v ? 'да' : 'нет';
  if (Array.isArray(v)) return v.length ? v.map(x => x !== null && typeof x === 'object' ? AKT.objText(x) : (AKT.things[AKT.name(String(x))] ? AKT.nameRu(AKT.name(String(x))) : String(x))).join(', ') : 'нет';
  if (typeof v === 'string') {
    if (!v) return '—';
    if (f === 'state' || f === 'status') return AKT.stRu(v, name);
    if (['location', 'node', 'task', 'block', 'top_node', 'at', 'target', 'face', 'issue', 'exc', 'truck', 'person', 'place', 'from', 'to'].includes(f)) { const t = AKT.name(v); return AKT.things[t] ? AKT.nameRu(t) : v; }
    if (f === 'kind') return AKT.kindRu(v);
    if (/^[A-Z][A-Z0-9_]+$/.test(v) && /(state|status|mode|phase)$/.test(f)) return AKT.stRu(v, name);
    if (/_status$/.test(f)) return AKT.lossStatusRu(v);
    if (f === 'plan_text') return AKT.planRu(v);
    if (f === 'scenario') return AKT.scenarioRu(v);
    if (/^layers_l/.test(f)) { try { return `${JSON.parse(v).length} слоёв (вид «Руда»)`; } catch (e) { return v; } }
    if (f === 'report_json') return `отчёт ${AKT.fmt(v.length)} знаков (вид «Калибровка»)`;
    return v.replace(/\s*\[оценка на модели\]/g, ' (≈)').replace(/\s*\[допущение\]/g, ' (д)');
  }
  if (f === 'shift_result') {
    const r = AKT.shiftResult();
    if (!r) return 'нет итога этого прогона (сравнение — только в режиме проверки модели)';
    const c = r.copies || {}, ok = k => c[k] && c[k].cu_t >= 0;
    const names = { fact: 'как было', base: 'без сценария', loud: '«кто громче»', no_twin: 'без двойника' };
    return `к ${AKT.clockDay(r.t_min)}: ` + Object.keys(names).filter(ok).map(k => `${names[k]} ${AKT.f1(c[k].cu_t)} т меди, ≈ ${AKT.money(c[k].usd)}`).join('; ');
  }
  if (v && typeof v === 'object') return AKT.objText(v);
  return '—';
};
AKT.focusIssue = issue => {
  const node = AKT.issueNode(issue);
  Panel.focusNode = node || null;
  if (AKT.current && AKT.current.highlight) AKT.current.highlight(node);
};

/* ------------------------------------------------------------------ start */
AKT.start = async function () {
  AKT.buildMenu();
  document.addEventListener('click', AKT.onClick, true);
  document.addEventListener('keydown', AKT.onKey);
  Panel.build();
  AKT.listeners.add(() => Panel.update());
  AKT.listeners.add(() => Now.update());
  const sb = document.getElementById('sim-seed'); if (sb) sb.addEventListener('input', () => { sb.dataset.touched = '1'; });
  document.getElementById('btn-ask').addEventListener('click', () => AKT.ask && AKT.ask.open(''));
  document.getElementById('btn-tour').addEventListener('click', () => AKT.tour && AKT.tour.start());
  document.getElementById('btn-gloss').addEventListener('click', () => AKT.glossary && AKT.glossary.open());
  try { await AKT.loadPlan(); } catch (e) { console.error(e); }
  await AKT.poll();
  AKT.pollJournal();
  await AKT.route();
  setInterval(AKT.poll, AKT.POLL_MS);
  setInterval(AKT.pollJournal, AKT.JOURNAL_MS);
  setInterval(() => Now.update(), 1000);
  if (AKT.params.get('issue')) Panel.open = AKT.params.get('issue');     /* ?issue=issue-N opens that issue's card */
  if (AKT.params.get('tour') === '1' && AKT.tour) AKT.tour.start();
  if (AKT.params.has('ask') && AKT.ask) AKT.ask.open(AKT.params.get('ask') || '');
  if (AKT.params.get('sim') === '1') { const d = document.getElementById('sim'); if (d) { d.open = true; d.scrollIntoView({ block: 'start' }); } }
  if (AKT.params.get('run') === '1') {
    const scen = AKT.params.get('scenario'), preset = AKT.params.get('preset');
    const p = new URLSearchParams(location.search); p.delete('run');
    history.replaceState(null, '', location.pathname + (p.toString() ? '?' + p.toString() : ''));
    if (preset === 'fork') Panel.scenario('fork');
    else if (scen) Panel.scenario(scen);
    else if (AKT.params.get('speed')) Panel.cmd('/api/speed', { value: Number(AKT.params.get('speed')) }, 'скорость');
  }
};
