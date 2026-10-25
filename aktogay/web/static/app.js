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
  const tot = Math.round(min), h = Math.floor(tot / 60), m = tot % 60;     /* whole minutes first: 119,6 min is 2 ч 00 мин, not «1 ч 60 мин» */
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
const YELLOW = new Set(['COLD', 'CRUD', 'SLOW', 'STARVED', 'LIMITED', 'LIMITED_GRID', 'UPSET', 'LOW', 'HIGH', 'LIMIT', 'SHORT', 'ONE', 'WARN', 'WARNING', 'STALE', 'REPAIR']);
AKT.cls = s => RED.has(s) ? 'st-red' : (YELLOW.has(s) ? 'st-yellow' : 'st-grey');
AKT.LV_CLS = { 0: 'st-grey', 1: 'st-red', 2: 'st-yellow', 3: 'st-soon' };
AKT.LV_GLYPH = { 0: '', 1: '◆', 2: '▲', 3: '△' };
AKT.lvCls = lv => AKT.LV_CLS[lv || 0];
AKT.glyph = lv => lv ? `<span class="lv lv-${lv}" aria-hidden="true">${AKT.LV_GLYPH[lv]}</span>` : '';
const ST_RU = {
  RUN: 'работает', STOP: 'стоит', SLOW: 'медленно', STARVED: 'нет питания', LIMITED_GRID: 'лимит сети', RELINE: 'перефутеровка',
  CRUD: 'краб в отстойнике',
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
/* The comparison with the run without the scenario is open in «Режим проверки модели» and, for a visible cause, in any
   running scenario (a hidden cause stays hidden: the dispatcher has to find it). */
AKT.leverOn = () => AKT.num('site', 'lever_on') === 1;     // what-if levers of the model are on: the base copy runs without them
AKT.cmpOpen = () => {
  const s = AKT.scenario();
  if (!s) return AKT.leverOn();
  return !!s && (AKT.check || !s.split('+').some(p => HIDDEN_KINDS.has(p.split(/[:@=]/)[0])));
};
AKT.hatchOn = () => AKT.check || AKT.cmpOpen();
AKT.baseOk = () => AKT.cmpOpen() && String(AKT.val('baseline', 'idSimulationRun') || '') === AKT.run && !!AKT.run;
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
  if (!AKT.check && !AKT.cmpOpen()) return null;
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
  winter: 'Зима', balls: 'скрытая причина', conc: 'скрытая причина', pitstop: 'Остановка карьера', conveyor: 'Встал конвейер',
  icy: 'Метель и гололёд на откатке', fatigue: 'Усталость водителя (допущение)', oil: 'Загрязнение масла EX01',
  roping: 'скрытая причина', phdrift: 'скрытая причина', hpgr: 'Неравномерное питание ВВД', mantle: 'Замена брони дробилки',
  sample: 'Анализатор отдаёт старые данные' };
const HIDDEN_KINDS = new Set(['dose', 'cyclone', 'liner', 'oxide', 'balls', 'conc', 'roping', 'phdrift']);
AKT.scenarioRu = s => s === 'icy+dust+grid' ? 'Смена с тремя бедами сразу' : s.split('+').filter(Boolean).map(p => {
  const [k, n] = p.split(':');
  return (SCEN_RU[k] || k) + (n && (AKT.check || !HIDDEN_KINDS.has(k)) ? ` (линия ${n})` : '');
}).join(' + ');
AKT.scenarioId = s => AKT.check || !s.split('+').some(p => HIDDEN_KINDS.has(p.split(':')[0])) ? s : 'скрыто';
/* The way of a trouble to the copper: from the nodes of the open issues down by feeds (dispatcher's view);
   the declared chain of the scenario only in «Режим проверки модели». */
AKT.scenarioChain = () => {
  const out = AKT.cmpOpen() && AKT.prop ? AKT.prop.affected() : new Set();
  let keepWater = false;
  const down = start => { const q = [start]; while (q.length) { const n = q.shift(); if (out.has(n)) continue; out.add(n); for (const f of AKT.feeds(n)) q.push(f); } };
  if (!AKT.check) {
    for (const i of AKT.issues()) {
      const node = AKT.issueNode(i);
      if (!node || !AKT.things[node]) continue;
      if (/^(water|piezo)/.test(node) || ['water-trouble', 'piezo'].includes(AKT.cat(node))) keepWater = true;
      down(node);
    }
    if (!keepWater && !(AKT.cmpOpen() && AKT.prop && AKT.prop.has('water'))) out.delete('water');
    if (!(AKT.cmpOpen() && AKT.prop && AKT.prop.has('conc-stock'))) out.delete('conc-stock');
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
  if (!keepWater && !(AKT.cmpOpen() && AKT.prop && AKT.prop.has('water'))) out.delete('water');
  if (!(AKT.cmpOpen() && AKT.prop && AKT.prop.has('conc-stock'))) out.delete('conc-stock');
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
  const idleBelt = t === 'conveyor' && s === 'STOP' && AKT.raw(name, 'fault') === 0;
  if (!(idleBelt || c === 'person' || c === 'crew' || ['issue', 'batch', 'site', 'control', 'journal', 'validation-calib', 'validation-setup', 'validation-sim', 'baseline'].includes(t) || /^mod-/.test(t))) {
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
  shift_supervisor: 'Нач. смены', shift_mechanic: 'Механик', mine_shift_head: 'Нач. карьера', road_service: 'Дорожная',
  grinding_operator: 'Оператор помола' };
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
  'начальник смены карьера': 'начальника смены карьера', 'дорожная служба карьера': 'дорожную службу карьера',
  'сменный механик карьера': 'сменного механика карьера', 'сменный механик': 'сменного механика',
  'оператор пульта измельчения': 'оператора пульта измельчения',
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
  /* only the first letter goes small, abbreviations keep their case («дробилка ЦПД-1», not «дробилка цпд-1») */
  const pl = AKT.placeRu(i.loc), plc = /^[А-ЯЁA-Z]{2}/.test(pl) ? pl : pl.charAt(0).toLowerCase() + pl.slice(1);
  if (i.st === 'FREE' || i.st === 'AVAILABLE') return `свободен, сейчас: ${plc}`;
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
  /* training mode: calls and postponements stay learning (not written to the journal, not in the reports) */
  if (AKT.train && AKT.train.on() && /^\/api\/(call|snooze|remind|mech)\b/.test(url)) {
    AKT.train.record({ title: 'учебный вызов на экране', pick: String((body && (body.role || body.reason)) || ''), right: '', ok: true, url });
    return { ok: true, training: true };
  }
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
  const base = AKT.kindTitle ? AKT.kindTitle(kind, nodeName) : `${nodeName}: ${AKT.kindRu(kind)}`;
  /* one pit stop is one trouble per line: the line is in the text of the module */
  const pl = kind === 'pit_stop' ? /склад линии (\d)/.exec(String(AKT.val(n, 'text') || '')) : null;
  return pl ? `${base} · линия ${pl[1]}` : base;
};
AKT.issueRole = n => String(AKT.val(n, 'responsible') || (AKT.issueNode(n) ? AKT.role(AKT.issueNode(n)) : '') || '');
AKT.issuePerson = n => { const p = AKT.name(String(AKT.val(n, 'person') || '')); return p && AKT.things[p] ? p : ''; };
/* called already: the state of the issue, rank 99 of the module, or a call written from this page */
AKT.calls = {};
AKT.issueCalled = n => ['CALLED', 'IN_WORK'].includes(AKT.st(n)) || (AKT.num(n, 'rank') ?? 0) >= 99 || !!AKT.calls[n + '|' + AKT.run];
AKT.issueSnoozed = n => AKT.st(n) === 'SNOOZED';

/* life cycle of an issue (UI rules, item 4): new -> called -> accepted -> on the way -> on site -> resolved. «принял / в пути /
   на месте» come from the called person's screen (journal.mech, read by the module); marked «(механик)». */
AKT.life = n => {
  const lc = AKT.val(n, 'lifecycle');
  if (!lc || typeof lc !== 'object' || !Array.isArray(lc.steps)) return null;
  const steps = lc.steps.filter(x => x.key !== 'new').map(x => Object.assign({}, x, {
    text: `${x.ru}${typeof x.t === 'number' && x.t >= 0 ? NBSP + AKT.clock(x.t) : ''}${x.src === 'механик' ? ' (механик)' : ''}` }));
  return { stage: lc.stage, stageRu: lc.stage_ru, steps, text: steps.map(x => x.text).join(' → '), help: Number(lc.help) === 1, helpText: lc.help_text || '' };
};
/* price of an issue split into copper, energy, reagents and the buyer's penalty, and what each part stands on (card, «Подробнее») */
AKT.delayHourHtml = n => {
  const x = AKT.exp23;
  if (!x) return '';
  if (!x.data) { x.load(() => {}); return ''; }
  return x.delayFor(String(AKT.val(n, 'kind') || ''));
};
AKT.costHtml = n => {
  const c = AKT.val(n, 'cost');
  const dh = AKT.delayHourHtml(n);
  if (!c || typeof c !== 'object') return dh;
  if (!Array.isArray(c.items) || !c.items.length) return (c.text ? `<p class="note">${AKT.esc(c.text)}</p>` : '') + dh;
  const esc = AKT.esc;
  const lab = (l, k) => l ? `<span class="lbl lbl-${esc(k || 'calc')}">${esc(l)}</span>` : '';
  const sup = a => (a || []).map(x => `<li>${esc(x.what)} ${lab(x.label, x.key)}</li>`).join('');
  const rows = c.items.map(it => `<tr class="${it.usd_h >= 0.5 ? '' : 'zero'}"><td>${esc(it.title)}</td><td class="n">${it.usd_h >= 0.5 ? esc(AKT.approx(it.usd_h)) + '/ч' : 'не входит'}</td>`
    + `<td>${lab(it.label, it.weak)}</td><td>${it.usd_h >= 0.5 ? `<ul class="cost-sup">${sup(it.supports)}</ul>` : ''}</td></tr>`).join('');
  const h = c.horizon || {};
  return `<div class="cost" id="cost-${esc(n)}"><b>Из чего складывается цена</b> <span class="note">≈ расчёт модели, в час, пока потери идут</span>
<table class="kv"><tr><th>Статья</th><th>$ в час</th><th>Держится на</th><th>Опора</th></tr>${rows}</table>
${c.text ? `<p class="note">${esc(c.text)}.</p>` : ''}
${h.usd > 0 ? `<p>За ${AKT.fmt(h.hours)} ч, если никого не звать: <b>${esc(AKT.approx(h.usd))}</b> ${lab(h.label, 'assumption')} <span class="note">— зависит от сроков:</span></p><ul class="cost-sup">${sup(h.supports)}</ul>` : ''}${dh}</div>`;
};
/* the button «Сдать смену»: only in the last handover_btn.lead_min minutes of the shift (the module counts the time) */
AKT.updateHandoverBtn = () => {
  const b = AKT.val('mod-priority', 'handover_btn');
  const fresh = String(AKT.val('mod-priority', 'idSimulationRun') || '') === AKT.run && !!AKT.run;
  const show = !!(b && typeof b === 'object' && Number(b.show) === 1 && fresh && AKT.st('site') !== 'WARMUP');
  let el = document.getElementById('ho-btn');
  if (show && !el) {
    el = document.createElement('a'); el.id = 'ho-btn'; el.className = 'ho-btn'; el.href = AKT.href('?view=handover');
    el.textContent = 'Сдать смену';
    const tools = document.getElementById('tools'); if (tools) tools.insertBefore(el, tools.firstChild);
  }
  if (el) {
    if (!show) { el.remove(); return; }
    el.title = `Смена кончается в ${AKT.clock(b.end)}: лист сдачи уже собран (открыть и передать)`;
  }
};
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
/* «Измерения и возраст данных» (second level of the issue card): every measurement behind the issue with the age of its data.
   age_pub_min: how long ago the thing was published (what the screen shows is this old); age_meas_min: age of the sample itself
   (analyser cycle, grab sample). A row doubted by the instrument state or by its age is marked in words and by a sign, not by colour alone. */
AKT.agoMin = m => m == null ? '—' : (m < 1 ? 'только что' : AKT.dur(m) + NBSP + 'назад');
AKT.evidenceItems = n => { const ev = AKT.val(n, 'evidence'); return ev && Array.isArray(ev.items) ? ev.items : []; };
AKT.evidenceHtml = n => {
  const items = AKT.evidenceItems(n), nt = String(AKT.val(n, 'notify_text') || '');
  if (!items.length && !nt) return '';
  const e = AKT.esc;
  const rows = items.map(i => {
    const flags = [i.suspect ? '▲ под подозрением' : '', i.old ? '⏱ давно' : ''].filter(Boolean).join('; ');
    const unit = i.unit ? NBSP + e(i.unit) : '';
    return `<tr class="${i.suspect ? 'ev-susp' : i.old ? 'ev-old' : ''}"><td>${e(i.label)}</td><td class="n">${e(i.text)}${unit}</td><td>${e(i.where || '')}</td>`
      + `<td>данные ${e(AKT.agoMin(i.age_pub_min))}${i.age_meas_min != null ? `<br>проба ${e(AKT.agoMin(i.age_meas_min))}` : ''}</td><td>${flags ? `<b>${e(flags)}</b>` : '—'}</td></tr>`;
  }).join('');
  return (items.length ? `<h4 class="ev-h">Измерения и возраст данных</h4><table class="kv ev-t"><tr><th>измерение</th><th>значение</th><th>где виден</th><th>возраст данных</th><th>пометка</th></tr>${rows}</table>`
    + `<p class="p-sub">«Данные N мин назад» — сколько времени модели прошло с публикации; «проба» — возраст самого замера (цикл анализатора, ручная проба). ${AKT.evidenceItems(n).some(i => i.suspect) ? '▲ — прибор под подозрением: показание проверить второй пробой.' : ''}</p>` : '')
    + (nt ? `<p class="ev-n"><b>Также сообщить:</b> ${e(nt)}</p>` : '');
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
/* How far the modules are behind the simulator, in model minutes: {name: lag|null}. A module that has not written
   for this run yet has no lag (the stand is warming up). */
AKT.MODS = [['mod-losses', 'Где теряется медь'], ['mod-ore', 'Какая руда идёт'], ['mod-priority', 'Очередь бед']];
AKT.moduleLag = () => {
  const out = {}, t = AKT.simTime;
  for (const [n] of AKT.MODS) {
    const p = AKT.num(n, 'processed_sim_time'), same = String(AKT.val(n, 'idSimulationRun') || '') === AKT.run;
    out[n] = t != null && p != null && p >= 0 && same ? Math.max(0, t - p) : null;
  }
  return out;
};
/* the lag that matters to the dispatcher: the queue of troubles and the loss detector (the ore forecast has a 15-min tact) */
AKT.maxLag = () => { const l = AKT.moduleLag(); const v = [l['mod-losses'], l['mod-priority']].filter(x => x != null); return v.length ? Math.max(...v) : null; };
AKT.LAG_WARN = 20;
/* Live effect of the twin in a scenario with copies of the model: copper of this run minus the copy without the twin
   («Две беды сразу»), otherwise minus the copy without the scenario. Read from baseline.shift_result (Ditto). */
AKT.effect = () => {
  const r = AKT.shiftResult(); if (!r) return null;
  const c = r.copies || {}, ok = k => c[k] && c[k].cu_t >= 0;
  const sg = d => (d > 0.004 ? '+' : d < -0.004 ? '−' : '±') + AKT.f2(Math.abs(d));
  if (ok('fact') && ok('no_twin')) {
    const d = c.fact.cu_t - c.no_twin.cu_t, usd = (c.fact.usd - c.no_twin.usd);
    return { kind: 'twin', d, usd, t: r.t_min, text: `С двойником сейчас ${sg(d)} т Cu против копии без двойника${Math.abs(usd) >= 500 ? ` (≈ ${AKT.money(Math.abs(usd))})` : ''}${Math.abs(d) < 0.005 && AKT.issues().length ? ' · разница появится, когда бригада устранит беду' : ''}`,
      title: 'Две копии одной смены с 08:00: в одной вызовы идут по очереди двойника, в другой тихую потерю на флотации находит лаборатория в 14:00 (допущение). Разница накопленной меди на этот час, оценка на модели.' };
  }
  if (ok('fact') && ok('base')) {
    const d = c.fact.cu_t - c.base.cu_t;
    return { kind: 'scen', d, t: r.t_min, text: `Сценарий к этому часу: ${sg(d)} т Cu против копии без сценария`,
      title: 'Копия «без сценария» — та же смена с 08:00 без беды. Разница накопленной меди на этот час, оценка на модели. Эффект двойника измеряет сценарий «Две беды сразу» и «Повтор смены».' };
  }
  return null;
};
/* hours the ore stock lasts. The published hours_left lags one point behind a stop of the crusher (the first minutes show
   «больше двух суток» while the SAG already takes 3800 t/h from the stock): when nothing comes in, count it from the level. */
AKT.hoursLeft = sp => {
  const h = AKT.num(sp, 'hours_left'), lvl = AKT.num(sp, 'level_t'), inn = AKT.num(sp, 'in_tph'), out = AKT.num(sp, 'out_tph');
  if (lvl != null && lvl >= 0 && out != null && out > 100 && inn != null && inn < 0.1 * out && (h == null || h < 0 || h > lvl / out + 0.5)) return lvl / out;
  return h;
};
/* the note under the ore stockpile: how long it lasts, or that it does not shrink; "2 days" only when the hours left really are above 48 */
AKT.stockNote = sp => {
  const h = AKT.hoursLeft(sp), inn = AKT.num(sp, 'in_tph'), out = AKT.num(sp, 'out_tph');
  if (h != null && h >= 0) return h <= 48 ? { h, text: `кончится через ${AKT.durH(h)}`, short: `хватит на ${AKT.durH(h)}` } : { h, text: 'хватит больше чем на 2 суток', short: 'запас > 2 суток' };
  if (inn != null && out != null && inn >= out) return { h: null, text: 'запас не убывает (приход не меньше расхода)', short: 'запас не убывает' };
  return { h: null, text: 'срок запаса не определён', short: 'срок не определён' };
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
      const money = AKT.lossNow(top) ? ` Теряем ${AKT.approx(AKT.num(top, 'loss_usd_h'))}/ч.` : (from != null ? ` Потерь нет до ${AKT.clockDay(from)}.` : '');
      out.text = `${AKT.rankSign(top) ? AKT.rankSign(top) + ' ' : 'Беда: '}${AKT.issueTitle(top)} — ${who.charAt(0).toLowerCase() + who.slice(1)} ${where}.${money}`
        + (next ? ` Следующее: ${AKT.rankSign(next) || '•'} ${AKT.nameRu(AKT.issueNode(next))} — ${AKT.issuePrice(next)}.` : '');
      if (next) out.btn = { issue: next, label: 'Позвать ' + AKT.roleAcc(AKT.roleFirst(AKT.issueRole(next))) };
      return out;
    }
    /* one price: an hour of delay, or till when to call */
    const dot = s => /\.$/.test(s) ? s : s + '.';
    if (AKT.lossNow(top)) out.text = dot(`Главное: ${sign} ${AKT.issueTitle(top)} — ${AKT.issuePrice(top)}`);
    else {
      const from = AKT.num(top, 'loss_from');
      /* the price may itself say "потерь пока нет": then it is said once */
      const price = AKT.issuePrice(top), tail = price === 'потерь пока нет' ? '' : ` — ${price}`;
      out.text = dot(`${sign} ${AKT.issueTitle(top)}: потерь пока нет${from != null ? ` (запас до ${AKT.clockDay(from)})` : ''}${tail}`);
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
  if (dev.length) { out.text = `Бед в очереди нет, но есть отклонения: ${dev.map(n => `${AKT.LV_GLYPH[AKT.levelOf(n)]} ${AKT.nameRu(n)} — ${AKT.stOf(n)}`).join(', ')}.${(() => { const rl = AKT.roleFirst(AKT.role(dev.find(n => AKT.role(n)) || '')); return rl ? ` Звать ${AKT.roleAcc(rl)} — цена уточняется, двойник считает.` : ' Цена уточняется, двойник считает.'; })()}`; if (dev.length) out.btn = null; return out; }
  out.text = `Бед нет. Фабрика работает в норме и даёт ${AKT.f1(AKT.num('site', 'cu_tph'))} т меди в час.`;
  out.demo = !AKT.scenario() && st === 'RUN';
  return out;
};
AKT.ctxLine = () => {
  const t = AKT.simTime, speed = AKT.num('site', 'speed'), st = AKT.st('site');
  const paused = st === 'PAUSED' || speed === 0;
  const spd = paused ? '⏸ пауза' : (speed ? `▶ ход ×${AKT.fmt(speed)}${speed === 60 ? ' (минута = час)' : ''}` : '');
  const age = AKT.staleSec();
  return `Время модели <b>${AKT.clockDay(t)}</b> · ${spd}${age != null && age > 4 ? ` · данные на ${AKT.clock(t)} модели` : ''} · смена 08:00–20:00${AKT.scenario() ? '' : ' · медный рудник в Казахстане, фабрика в 2 линии'}`;
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
    const eff = document.getElementById('now-eff');
    if (eff) {
      const e = AKT.effect(), lag = AKT.maxLag();
      const html = (e ? `<a class="chip eff" href="${AKT.href('?view=modules')}" title="${AKT.esc(e.title)}">${AKT.esc(e.text)}</a>` : '')
        + (lag != null && lag > AKT.LAG_WARN ? `<span class="chip lag" title="Модули считают с отставанием от симулятора; они берут последнюю готовую точку и пропускают старые.">⏱ модули отстают на ${AKT.esc(AKT.dur(lag))}</span>` : '');
      if (eff._h !== html) { eff._h = html; eff.innerHTML = html; }
    }
    const key = (o.chip || '') + '|' + o.text + '|' + (o.btn ? o.btn.issue + o.btn.label : '') + '|' + (o.demo ? 'demo' : '');
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
    /* nothing open: a small action that runs one catalog scenario («Два сразу», seed 42); it sits in this line, not in a block of its own */
    let dm = act.querySelector('button.now-demo');
    if (o.demo) {
      if (!dm) {
        dm = document.createElement('button'); dm.type = 'button'; dm.className = 'quiet now-demo'; dm.textContent = 'Показать пример смены';
        dm.title = 'Запустит сценарий из каталога «Две беды сразу» с 08:00 (прогон № 42); остановить можно в панели справа';
        act.appendChild(dm);
        dm.addEventListener('click', () => { dm.disabled = true; Panel.scenario('fork', { seed: 42, name: 'Две беды сразу' }); });
      }
    } else if (dm) dm.remove();
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
/* Menu of 4 groups x 3-5 items, depth 2 (UI rules item 7). The count of open troubles sits on «Сейчас». */
const MENU4 = [
  ['now', 'Сейчас', [['plan', 'Обзор'], ['queue', 'Все беды'], ['areas', 'Участки'], ['forecast', 'Прогнозы'], ['copper', 'Путь меди']]],
  ['shift', 'Смена', [['handover', 'Сдача смены'], ['report', 'Отчёт смены'], ['journal', 'Журнал с выгрузкой']]],
  ['analysis', 'Анализ', [['economics', 'Экономика'], ['calib', 'Калибровка'], ['modules', 'Модули'], ['inside', 'Изнутри'], ['replay', 'Повтор смены']]],
  ['learn', 'Обучение и справка', [['howto', 'Как проверить'], ['scenarios', 'Сценарии'], ['train', 'Тренировка'], ['legend', 'Обозначения'], ['tour', 'Как пользоваться']]],
];
/* views that live under another item of the menu (the hub «Участки» lists them) */
const MENU_ALIAS = { ore: 'analysis', levers: 'analysis', line1: 'areas', line2: 'areas', diorama: 'areas', site: 'areas', tree: 'areas', text: 'areas', unit: 'areas' };
AKT.viewName = () => {
  const v = AKT.params.get('view') || 'plan';
  if (v === 'line') return 'line' + (AKT.params.get('n') || '1');
  if (v === 'card') return 'unit';
  if (v === '3d') return 'diorama';
  return v;
};
AKT.buildMenu = function () {
  const cur0 = AKT.viewName(), cur = MENU_ALIAS[cur0] || cur0;
  const nav = document.getElementById('nav');
  nav.innerHTML = MENU4.map(([gid, gname, items]) => {
    const on = items.some(([v]) => v === cur);
    const li = items.map(([v, t]) => (v === 'tour' ? `<a href="#" data-tour="1">${t}</a>` : `<a href="${AKT.href('?view=' + v)}"${v === cur ? ' aria-current="page"' : ''}>${t}${v === 'queue' ? ' <span class="cnt" id="nav-cnt2" hidden></span>' : ''}</a>`)).join('');
    return `<span class="more"><button type="button" data-g="${gid}" aria-expanded="false" aria-haspopup="true" class="${on ? 'cur' : ''}">${gname}${gid === 'now' ? ' <span class="cnt" id="nav-cnt" hidden></span>' : ''} ▾</button><span class="more-menu" id="nav-m-${gid}" hidden>${li}</span></span>`;
  }).join('');
  const menus = [...nav.querySelectorAll('.more-menu')], btns = [...nav.querySelectorAll('button[data-g]')];
  const closeAll = () => { menus.forEach(m => { m.hidden = true; }); btns.forEach(b => b.setAttribute('aria-expanded', 'false')); };
  btns.forEach(b => b.addEventListener('click', ev => {
    ev.stopPropagation();
    const m = document.getElementById('nav-m-' + b.dataset.g), open = m.hidden;
    closeAll(); m.hidden = !open; b.setAttribute('aria-expanded', String(open));
    if (open) m.querySelector('a').focus();
  }));
  nav.querySelectorAll('a[data-tour]').forEach(a => a.addEventListener('click', ev => { ev.preventDefault(); closeAll(); if (AKT.tour) AKT.tour.start(); }));
  document.addEventListener('click', ev => { if (!nav.contains(ev.target)) closeAll(); });
  document.addEventListener('keydown', ev => { if (ev.key === 'Escape') closeAll(); });
};
AKT.updateMenu = () => {
  AKT.updateHandoverBtn();
  const c = document.getElementById('nav-cnt'); if (!c) return;
  const n = AKT.issues().length;
  c.hidden = !n; c.textContent = String(n);
  c.parentNode.setAttribute('aria-label', `Сейчас, бед: ${n}`);
  const c2 = document.getElementById('nav-cnt2'); if (c2) { c2.hidden = !n; c2.textContent = String(n); }
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
  { id: 'crusher:1', name: 'Встала дробилка', what: 'Дробилка ЦПД-1 у карьера встанет сейчас, ремонт ≈ 3 ч (бывает до 5 ч).',
    watch: 'Склад руды 1 начнёт убывать; если он кончится раньше ремонта, линия 1 встанет. Двойник покажет беду и кого звать.' },
  { id: 'grid', name: 'Сеть урезала мощность', what: 'Лимит сети 300 → 218 МВт на 2 ч.', watch: 'Нагрузку площадки против лимита и когда лимит снимут.' },
  { id: 'hard:1', name: 'Твёрдая руда', what: 'На линию 1 идёт блок твёрдой руды (A×b 27): мельница будет молоть медленнее.', watch: 'Когда твёрдая руда дойдёт до мельницы SAG-1.' },
  { id: 'reline:1', name: 'Перефутеровка SAG', what: 'Мельница SAG-1 встаёт на плановую замену футеровки на 84 ч (аналог: кейс Metso, Minera Chinalco Peru).', watch: 'Когда мельница вернётся; линия 1 стоит.' },
  { id: 'fork', name: 'Две беды сразу', what: 'Скрытый сбой на флотации 1 и поломка дробилки 2 в 09:20; дежурный КИПиА один.', watch: 'Кого звать первым — смотрите карточку ①.' },
  { id: 'water', name: 'Беда с водой', what: 'Сбой водовода и забора свежей воды, растёт давление воды в дамбе.', watch: 'Пьезометры дамбы: давление против тревоги 150 кПа.' },
  { id: 'startup:1', name: 'Пуск мельницы при людях внутри', what: 'Шаровая 1A на ремонте по наряду-допуску, механик внутри; через час кто-то включает команду на пуск.', watch: 'Безопасность людей: беда класса S0 идёт первой, пуск надо отменить.' },
  { id: 'dust', name: 'Пыление пляжа хвостохранилища', what: 'Ветер не ниже 11 м/с над сухим пляжем на 6 ч (ветер — типичное событие по ERA5, расчёт).', watch: 'Экологическая беда S1 идёт после людей и перед деньгами.' },
  { id: 'winter', name: 'Зима', what: 'Возврат воды с хвостохранилища снижен (лёд), воздух около −10 °C (аналог: нормы NOAA).', watch: 'Метка «Зима» в шапке; беды с водой дороже и срочнее.' },
  { id: 'pitstop', name: 'Остановка карьера', what: 'Все экскаваторы руды встают на 8 ч (причина не названа: взрыв, погода или поломка).', watch: 'Склад каждой линии: через сколько часов он кончится и SAG встанет. Двойник покажет беду «Карьер (останов)» и кого звать — горного диспетчера.' },
  { id: 'conveyor:1', name: 'Встал конвейер', what: 'Главный конвейер линии 1 отключился; дробилка стоит с пустой лентой, ремонт ≈ 2 ч.', watch: 'Склад линии 1 убывает; двойник покажет беду «Конвейер» и кого звать — механика ЦПД.' },
  { id: 'hpgr_fire', name: 'Пожар на прессе дробления гали', what: 'Пожар на прессе дробления гали: люди рядом, узел остановлен.', watch: 'Безопасность людей: беда класса S0 идёт первой.' },
  { id: 'icy', name: 'Метель и гололёд на откатке', what: 'На 6 ч метель и гололёд: видимость ≈ 120 м, сцепление ≈ 0,3, ветер 11 м/с, воздух −5 °C (по ERA5, расчёт). Пороги опасности (150 м, 0,4) — допущение: KAZ Minerals называет метели и сильный ветер риском ДТП на Актогае, цифр не публикует.',
    watch: 'Беда класса S0 «Зимняя дорога»: ограничить движение — горный диспетчер → начальник смены карьера → дорожная служба. После вызова ограничение введено, откатка идёт медленнее: рядом видна цена этого решения. Переработка фабрики от погоды сама не падает.' },
  { id: 'fatigue', name: 'Усталость водителя (допущение)', what: 'Оповещение об усталости водителя самосвала HT141 и близком сближении техники на 1 ч. Датчика и случаев на Актогае в открытых данных не нашли — это сценарий-допущение.',
    watch: 'Беда класса S0: снять машину с рейса, развести технику. В деньгах не считается.' },
  { id: 'roping:1', name: 'Канатирование циклонов', what: 'Гидроциклоны линии 1 «канатируют»: перелив грубеет, циркулирующая нагрузка и нагрузка шаровой растут (≈ 112 % номинала). Через 1,5 ч без решения флотация теряет ещё ≈ 3 п.п. (на Centinela одна нитка флотации стояла ≈ 6 ч — аналог).',
    watch: 'Беда «Канатирование»: звать оператора пульта измельчения, затем металлурга. Смотрите, как после решения возвращается циркулирующая нагрузка.' },
  { id: 'phdrift:1', name: 'pH-метр врёт', what: 'Электрод pH флотации 1 зарос накипью извести: онлайн-показание держится на уставке, а реальный pH выше на ≈ 0,6. Ручная проба раз в 4 ч покажет расхождение (период и размер — допущения).',
    watch: 'Беда «pH-метр под подозрением» появится после контрольной пробы: онлайн-показание и проба рядом, возраст пробы виден в «Подробнее». Звать дежурного КИПиА.' },
  { id: 'sample:1', name: 'Анализатор отдаёт старые данные', what: 'Пробоотборная линия поточного анализатора линии 1 засорилась: он держит последнее показание, его возраст растёт (цикл 12–16 мин). Засорение линий — типичная проблема анализаторов (Metso Metrics, частот нет); время чистки ≈ 0,5 ч — допущение.',
    watch: 'Через 30 мин анализатор «под подозрением»: в карточках с хвостами, питанием и извлечением у замера виден возраст данных, в листе сдачи — отклонение «Анализатор 1: данные старше…». Дежурный КИПиА прочищает линию, показания возобновляются.' },
  { id: 'hpgr:2', name: 'Неравномерное питание ВВД линии 2', what: 'Питание пресса ВВД линии 2 сегрегирует: перекос валков ≈ 12 %, круг гали ограничен. Если никто не вмешается за 2 ч, металл на валках — металлодетектор остановит пресс на 4 ч (допущения; аналог — блог Metso 2022).',
    watch: 'Беда «Неравномерное питание ВВД»: звать механика фабрики. На «Пути меди» узел ВВД краснеет от перекоса и сигнала металлодетектора.' },
  { id: 'mantle:1', name: 'Замена брони дробилки 1', what: 'Дробилка ЦПД-1 встаёт на плановую замену брони ≈ 60 ч (аналог — рудник La Caridad, Metso). Склад кормит SAG, пока не кончится.',
    watch: 'Часы до остановки SAG-1 и цена после конца склада; дробилка 1 и конвейер стоят, бригада ЦПД работает по наряду-допуску.' },
  { id: 'oil', name: 'Загрязнение масла EX01', what: 'Гидромасло экскаватора EX01 (EX3600) загрязняется: через ≈ 3 ч тревога датчика на машине; если никто не вмешается, через ≈ 8 ч после неё отказ насоса и ремонт ≈ 57 ч (ремонт — аналог другой машины; сроки — допущения).',
    watch: 'Беда «Загрязнение масла» с часами до отказа, потом «Отказ экскаватора». Звать сменного механика карьера. В диспетчерскую сигнал идёт, если подключена опция Global e-Service.' },
];
/* the countdown of a running scenario: {text, lv} (lv 3 when less than an hour is left) */
AKT.scenWatch = scen => {
  const k = scen.split('+')[0].split(':'), kind = k[0], n = k[1] || '1';
  const start = AKT.scenStart();
  const t = AKT.simTime;
  /* constructor: a token with a start (crusher:1@90) begins later than the scenario */
  const ctl = AKT.val('control', 'scenario'), cid = ctl && typeof ctl === 'object' && ctl.id ? String(ctl.id) : '';
  const later = cid.split('+').map(p => /^([a-z_]+)(?::\d+)?@(\d+(?:\.\d+)?)/.exec(p)).filter(Boolean)
    .map(m => ({ kind: m[1], at: (start != null ? start : 480) + Number(m[2]) })).filter(x => t != null && t < x.at).sort((a, b) => a.at - b.at)[0];
  if (later) return { text: `Своя беда начнётся в ${AKT.clock(later.at)}: ${AKT.scenarioRu(later.kind)}`, lv: 0 };
  const left = (min, what, at) => ({ text: `${what} через ${AKT.dur(min)}${at != null ? ` (в ${AKT.clockDay(at)})` : ''}`, lv: min < 60 ? 3 : 0 });
  if (kind === 'crusher') {
    const sp = `stockpile-${n}`, h = AKT.hoursLeft(sp), lvl = AKT.num(sp, 'level_t');
    if (lvl != null && lvl < 50) return { text: `Склад ${n} пуст — линия ${n} стоит`, lv: 1 };
    const cr = AKT.st(`crusher-${n}`);
    const tail = cr && AKT.stopped(cr) ? `дробилка ${n} стоит` : `дробилка ${n} снова работает`;
    if (h != null && h <= 48) return Object.assign(left(h * 60, `Следите: склад ${n} кончится`, t != null ? t + h * 60 : null), { text: `Следите: склад ${n} кончится через ${AKT.durH(h)}${t != null ? ` (в ${AKT.clockDay(t + h * 60)})` : ''} · ${tail}` });
    return { text: `Следите: склад ${n} — ${AKT.fmt(lvl)} т, ${AKT.stockNote(sp).text} · ${tail}`, lv: 0 };
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
  if (kind === 'pitstop') {
    const f = AKT.fc && AKT.fc.data(), L = f && f.stock && f.stock.lines ? Object.keys(f.stock.lines).sort().map(x => f.stock.lines[x]).filter(r => r.hours >= 0) : [];
    return L.length ? { text: `Следите: склад кончится раньше всего через ${AKT.durH(Math.min(...L.map(r => r.hours)))}; потом SAG этой линии встанет`, lv: Math.min(...L.map(r => r.hours)) < 1 ? 3 : 0 } : { text: 'Следите: склады линий и когда карьер снова даст руду', lv: 0 };
  }
  if (kind === 'conveyor') {
    const sp = `stockpile-${n}`, h = AKT.hoursLeft(sp);
    return { text: `Следите: конвейер ${n} ${AKT.stopped(AKT.st(`conveyor-${n}`)) ? 'стоит' : 'снова идёт'}; склад ${n} — ${AKT.fmt(AKT.num(sp, 'level_t'))} т${h != null && h <= 48 ? `, кончится через ${AKT.durH(h)}` : ''}`, lv: h != null && h < 1 ? 3 : 0 };
  }
  if (kind === 'icy') {
    const v = AKT.num('pit', 'visibility_m'), g = AKT.num('pit', 'road_grip'), r = AKT.num('pit', 'road_restrict') === 1;
    return { text: `Следите: видимость ${AKT.fmt(v)} м, сцепление ${AKT.f2(g)}, ограничение движения ${r ? 'введено' : 'не введено'}`, lv: r || v == null || v > 150 ? 0 : 1 };
  }
  if (kind === 'fatigue') {
    const on = AKT.num('fleet', 'fatigue') === 1;
    return { text: on ? `Следите: оповещение у машины ${AKT.val('fleet', 'fatigue_truck') || ''} (допущение) — беда S0` : 'Оповещение погашено', lv: on ? 1 : 0 };
  }
  if (kind === 'roping') {
    const c = AKT.num(`cyclones-${n}`, 'circ_load_pct'), b = AKT.num(`ball-${n}a`, 'power_pct');
    return { text: `Следите: циркулирующая нагрузка ${AKT.fmt(c)} %, нагрузка шаровой ${AKT.fmt(b)} %, P80 ${AKT.fmt(AKT.num(`cyclones-${n}`, 'p80_um'))} мкм`, lv: 0 };
  }
  if (kind === 'phdrift') {
    const ph = `ph-${n}`, a = AKT.num(ph, 'age_min');
    return { text: `Следите: pH онлайн ${AKT.f2(AKT.num(ph, 'ph'))}, ручная проба ${AKT.f2(AKT.num(ph, 'lab_ph'))}${a != null ? ` (${AKT.dur(a)} назад)` : ''}`, lv: 0 };
  }
  if (kind === 'sample') {
    const a = `analyzer-${n}`, age = AKT.num(a, 'age_min');
    return { text: `Следите: возраст показания анализатора ${n} — ${age != null ? AKT.dur(age) : '—'}${AKT.stOf(a) ? ' · ' + AKT.stOf(a) : ''}`, lv: age != null && age > 30 ? 1 : 0 };
  }
  if (kind === 'hpgr') {
    const pb = `pebble-${n === '1' ? '2' : n}`, m = AKT.num(pb, 'metal_alarm') === 1;
    return { text: m ? 'Металлодетектор сработал, пресс остановлен — звать механика фабрики' : `Следите: перекос валков ${AKT.f1(AKT.num(pb, 'hpgr_skew_pct'))} %, разница мощности приводов ${AKT.f1(AKT.num(pb, 'hpgr_kw_diff_pct'))} %`, lv: m ? 1 : 0 };
  }
  if (kind === 'mantle') {
    const left = AKT.num(`crusher-${n}`, 'service_left_h'), h = AKT.hoursLeft(`stockpile-${n}`);
    return { text: `Следите: замена брони ещё ${left != null ? AKT.durH(left) : '—'}; склад ${n} ${h != null && h <= 48 ? 'кончится через ' + AKT.durH(h) : '— ' + AKT.fmt(AKT.num(`stockpile-${n}`, 'level_t')) + ' т'}`, lv: h != null && h < 1 ? 3 : 0 };
  }
  if (kind === 'oil') {
    const p = AKT.num('exc-1', 'oil_pct'), a = AKT.num('exc-1', 'oil_alert') === 1, down = AKT.st('exc-1') === 'DOWN';
    return { text: down ? 'Экскаватор EX01 не работает: отказ насоса, ремонт ≈ 57 ч (аналог)' : `Следите: загрязнение масла EX01 ${AKT.fmt(p)} % от уровня тревоги${a ? ' — тревога на машине' : ''}`, lv: down ? 1 : (a ? 3 : 0) };
  }
  if (kind === 'fork') return { text: 'Следите: кого звать первым — смотрите карточку ① и строку ②', lv: 0 };
  if (kind === 'startup') return { text: 'Следите: команда на пуск при людях внутри мельницы — беда S0, отменить пуск', lv: 1 };
  if (kind === 'dust') return { text: `Следите: ветер ${AKT.fmt(AKT.num('water', 'wind_ms'))} м/с, сухой пляж ${AKT.fmt(AKT.num('water', 'beach_dry_pct'))} %`, lv: 0 };
  if (kind === 'winter') return { text: `Следите: воздух ${AKT.fmt(AKT.num('water', 'air_temp_c'))} °C, возврат воды снижен`, lv: 0 };
  return { text: '', lv: 0 };
};
/* model minute when the running scenario started: the control command of the same scenario */
AKT.scenStart = () => {
  /* a scenario run always starts at 08:00 of the model day (the id of the run says it is a scenario run) */
  if (/-scen-/.test(AKT.run || '') && AKT.scenario()) return 480;
  const c = AKT.val('control', 'scenario');
  const bare = c && typeof c === 'object' && c.id ? String(c.id).split('+').map(p => p.split(/[@=]/)[0]) : [];
  if (c && typeof c === 'object' && c.id && AKT.scenario().split('+').some(p => bare.includes(p) || p === c.id || p.startsWith(String(c.id).split(':')[0])) && typeof c.sim_time === 'number') {
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
  <div id="b-expect" class="b-expect"></div>
  <div id="b-chain" class="b-chain" hidden></div>
  <div class="b-btns" id="b-btns"><button type="button" id="b-stop">Остановить сценарий…</button></div>
  <div class="b-btns" id="b-confirm" hidden><span>Остановить? Фабрика сразу вернётся в состояние, как если бы сценария не было, на то же время модели. Прогон продолжится.</span>
    <button type="button" class="primary" id="b-yes">Да, остановить</button><button type="button" id="b-no">Нет</button></div>
</div>
<div id="p-lever" class="banner" hidden><div class="b-h"><span class="tag-s">Рычаги модели:</span> <span id="lv-b-t"></span></div>
  <div class="p-sub">управление моделью, не фабрикой · ниже плитки и карта показывают ход с рычагами; «база» — копия без них</div>
  <div class="b-btns"><a href="${AKT.href('?view=levers')}">Рычаги модели →</a> <button type="button" id="lv-b-reset">Сбросить рычаги</button></div></div>
<div id="p-check" class="check-note" hidden><b>Режим проверки модели.</b> Показаны журнал симулятора (скрытые причины прогона) и копии модели без сценария; диспетчеру на смене это недоступно.<div id="p-hidden" class="p-sub" hidden></div></div>
<div class="tiles" id="tiles">
  <div class="tile" id="k-loss" role="group"><div class="l">Теряем сейчас</div><div class="v" id="k-loss-v" aria-busy="true">—</div><div class="d" id="k-loss-d"></div></div>
  <div class="tile" id="k-cu" role="group"><div class="l">Медь в концентрат</div><div class="v" id="k-cu-v">—</div><div class="d" id="k-cu-d"></div><div class="fcw" id="k-cu-f"></div></div>
  <div class="tile" id="k-ore" role="group"><div class="l">Руда на фабрику</div><div class="v" id="k-ore-v">—</div><div class="d" id="k-ore-d"></div></div>
  <div class="tile" id="k-rec" role="group"><div class="l"><span class="term" data-term="recovery">Извлечение</span> меди</div><div class="v" id="k-rec-v">—</div><div class="d" id="k-rec-d"></div></div>
  <div class="tile" id="k-mw" role="group"><div class="l">Электросеть</div><div class="v" id="k-mw-v">—</div><div class="d" id="k-mw-d"></div></div>
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
  <div class="lv-card" id="tc-lever" hidden></div>
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
  <details id="tc-more"><summary>Подробнее</summary><div class="full" id="tc-full"></div><div id="tc-cost"></div><div id="tc-evid"></div></details>
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
    <button type="button" data-speed="0">⏸ Пауза</button><button type="button" data-speed="60">×60</button><button type="button" data-speed="300" title="запрос ×300; фактический ход ограничен потоком 20 сообщений/с в Ditto">×300 (запрос)</button><button type="button" data-speed="1200" title="запрос ×1200; фактический ход ограничен потоком 20 сообщений/с в Ditto">×1200 (запрос)</button>
    <span id="sim-lag" class="p-sub"></span>
    <span class="p-sub" id="sim-cap">Потолок хода на этом стенде ≈ ×60–×90 (поток 20 сообщений/с в Ditto): смена с 08:00 до 20:00 идёт ≈ 8–12 мин.</span></div>
  <div class="sim-row"><span class="sim-lbl">Рычаги модели</span><span class="p-sub">подача SAG, помол P80, доза собирателя — управление моделью, не фабрикой</span> <a href="${AKT.href('?view=levers')}">открыть →</a></div>
  <div class="sim-row"><span class="sim-lbl">Учебные сценарии</span><span class="p-sub" id="sim-warm"></span><a href="${AKT.href('?view=scenarios')}">каталог и конструктор беды →</a></div>
  <div class="sc-list" id="sc-list">${AKT.SCENARIOS.map(s => `<div class="sc" data-sc="${s.id}"><span class="sc-n">${AKT.esc(s.name)}</span><span class="sc-d">${AKT.esc(s.what)}</span><button type="button" data-run="${s.id}">Запустить…</button>
    <div class="sc-confirm" hidden><p><b>Что случится:</b> ${AKT.esc(s.what)}</p><p><b>За чем следить:</b> ${AKT.esc(s.watch)} Обратный отсчёт появится вверху панели.</p><p><b>Как отменить:</b> «Остановить сценарий…» в синей рамке вверху панели — фабрика вернётся в состояние без сценария, на то же время модели.</p><p class="p-sub">Скорость: ×60 (минута = час).</p>
    <div class="b"><button type="button" class="primary" data-go="${s.id}">Запустить</button><button type="button" data-no>Отмена</button></div></div></div>`).join('')}</div>
  <div class="sim-row"><span class="sim-lbl">Смена заново</span><label>номер прогона (seed) <input type="number" id="sim-seed" min="1" max="99999" step="1" value="42"></label>
    <button type="button" id="sim-reset">Сбросить 08:00</button>
    <span id="sim-reset-ask" hidden><span class="p-sub">Текущий прогон закончится, смена начнётся с 08:00.</span> <button type="button" class="primary" id="sim-reset-yes">Да, сбросить</button> <button type="button" id="sim-reset-no">Отмена</button></span></div>
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

    const resetAsk = on => { $('sim-reset').hidden = on; $('sim-reset-ask').hidden = !on; $(on ? 'sim-reset-yes' : 'sim-reset').focus(); };
    $('sim-reset').addEventListener('click', () => resetAsk(true));
    $('sim-reset-no').addEventListener('click', () => resetAsk(false));
    $('sim-reset-yes').addEventListener('click', async () => {
      const seed = Math.max(1, Math.round(Number($('sim-seed').value) || 42));
      resetAsk(false);
      const ok = await Panel.cmd('/api/reset', { seed }, `сброс на 08:00, прогон ${seed}`);
      if (ok) AKT.toast(`Сброс на 08:00: прогон № ${seed} начался заново, идёт прогрев модели.`);
    });
    $('chk').addEventListener('change', ev => {
      const q = new URLSearchParams(location.search);
      if (ev.target.checked) q.set('check', '1'); else q.delete('check');
      location.search = q.toString();
    });
    $('lv-b-reset').addEventListener('click', async () => { if (AKT.lever && await AKT.lever.reset()) AKT.toast('Рычаги сброшены: обычный ход фабрики.'); });
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
      const res = await AKT.post(url, body);
      if (res && res.training) { this.msg(`${what}: учебный вызов, в журнал не записан`); AKT.toast('Тренировка: вызов учебный, в журнал и отчёты не идёт.'); return true; }
      this.msg(`${what}: принято в ${AKT.clock(AKT.simTime)} модели`);
      setTimeout(AKT.poll, 300); setTimeout(AKT.pollJournal, 1500); setTimeout(AKT.pollJournal, 12000);
      return true;
    } catch (e) { this.msg(`${what}: не получилось — ${e.message}. Нажмите ещё раз.`); return false; }
  },
  async scenario(id, opts) {
    const body = { id };
    if (opts && opts.seed != null) body.seed = opts.seed;
    if (id === 'fork') { body.preset = 'fork'; body.kip = Number(AKT.params.get('kip') || 1); body.auto = Number(AKT.params.get('auto') ?? 1); }
    if (AKT.params.get('safety')) body.safety = Number(AKT.params.get('safety'));
    if (AKT.params.get('speed')) body.speed = Number(AKT.params.get('speed'));
    const s = AKT.SCENARIOS.find(x => x.id === id);
    const label = opts && opts.name ? opts.name : (s ? s.name : id);
    this.scen = { id, t: AKT.simTime, cu: AKT.num('site', 'cu_tph'), tph: AKT.num('site', 'tph') };
    const ok = await Panel.cmd('/api/scenario', body, 'сценарий «' + label + '»');
    if (ok) AKT.toast(`Сценарий «${label}» запущен. Обратный отсчёт — вверху панели; остановить — там же.`);
    return ok;
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
    set('sim-run', `прогон № ${AKT.fmt(AKT.num('site', 'seed'))} (${AKT.run || '—'}) · данные: Ditto и InfluxDB через сервер стенда${AKT.num('site', 'degraded') ? ' · неповторяемый (были потери сообщений)' : ''}`);
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
      const pl = AKT.cmpOpen() ? AKT.prop.grouped() : [];
      $('b-chain').hidden = !pl.length;
      html('b-chain', pl.length ? `<div class="b-ch-h">Как расходятся последствия (база в ту же минуту модели → факт сейчас, эффект; по ходу процесса):</div><ol class="b-ch">${pl.slice(0, 7).map(c => `<li class="${AKT.prop.fresh(c.thing) ? 'new' : ''}"><a href="${AKT.href('?view=unit&id=' + AKT.id(c.thing))}">${AKT.esc(c.text)}</a></li>`).join('')}</ol>${pl.length > 7 ? `<div class="p-sub">и ещё ${AKT.fmt(pl.length - 7)} узлов — на карте и в диораме они под штриховкой</div>` : ''}` : '');
      if (!AKT.verify.data) AKT.verify.load(() => Panel.update());      /* once: a loaded file calls back at once, and the callback is update() itself */
      html('b-expect', AKT.verify.banner(scen));
      const eff = AKT.scenEffect(scen);
      set('b-before', eff ? eff.text : (b && b.cu != null && start != null ? `До сценария (${AKT.clock(start)}): медь ${AKT.f1(b.cu)} т/ч → сейчас ${AKT.f1(AKT.num('site', 'cu_tph'))} т/ч. Копии без сценария здесь нет: в разнице есть и колебание руды.` : ''));
    }
    $('p-lever').hidden = !AKT.leverOn();
    if (AKT.leverOn() && AKT.lever) set('lv-b-t', AKT.lever.describe());
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
    if (AKT.fc) { AKT.fc.loadSeries(); html('k-cu-f', AKT.fc.tileSvg() + (AKT.fc.tileHtml() ? `<div class="fc-t">${AKT.fc.tileHtml()}</div>` : '')); }
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
      set('p-result-title', res.kind === 'shift' ? `Итог смены (к ${AKT.clockDay(res.t_min)})` : `Итог смены: ход без сценария и со сценарием (к ${AKT.clockDay(res.t_min)})`);
      html('p-result-body', AKT.shiftTable(res) + AKT.verify.compare(res));
    }
    /* journal of the shift: this run, 3 last rows */
    const jr = AKT.shiftJournal().slice(0, 3);
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
    const life = AKT.life(n);
    const lifeBadge = life && ['accepted', 'enroute', 'onsite'].includes(life.stage) ? life.stageRu : '';
    /* where the called person is now: the same source as the line on top (Now), so the badge never says «в пути» while the line says «на месте» */
    const per0 = called ? AKT.issuePerson(n) : null, pi0 = per0 ? AKT.personInfo(per0) : null;
    const posBadge = pi0 ? (pi0.tr ? 'в пути' : /WORK|BUSY/.test(pi0.st) ? 'на месте' : '') : '';
    set('tc-st', AKT.issueSnoozed(n) ? 'отложено' : life && life.help ? 'нужна помощь' : called ? (posBadge || lifeBadge || (AKT.st(n) === 'IN_WORK' ? 'чинят' : 'позвали')) : 'не позвали');
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
      const chain = life && life.steps.length ? life.text.charAt(0).toUpperCase() + life.text.slice(1) : `Позвали${at != null ? ' в ' + AKT.clock(at) : ''}`;
      set('tc-called', `${chain}${life && life.steps.some(x => x.key === 'enroute') ? '' : (pi && pi.tr ? ' · в пути' : '')}${pi && pi.tr ? `, будет ≈ ${AKT.clock(pi.tr.eta)}` : ''}${life && life.help ? ' · нужна помощь' : ''}`);
    }
    const shift = AKT.num(n, 'loss_shift_usd'), adv = AKT.issueAdvice(n);
    /* ore processed in vain = t Cu / (grade x recovery) [calc]: what the copper lost in 12 h would have needed (Г1) */
    const gAvg = (AKT.num('flot-1', 'feed_cu') + AKT.num('flot-2', 'feed_cu')) / 2, rAvg = (AKT.num('line-1', 'recovery') + AKT.num('line-2', 'recovery')) / 2;
    const oreVain = shift != null && shift > 0 && gAvg > 0 && rAvg > 0 ? AKT.cuOfUsd(shift) / ((gAvg / 100) * (rAvg / 100)) : null;
    const full = [adv ? 'Совет модуля: ' + adv : '', shift != null && shift > 0 ? `Если никого не звать, за 12 ч ${AKT.approx(shift)}${oreVain != null ? ` — это ≈ ${AKT.fmt(oreVain)} т руды, переработанной впустую (т меди ÷ (содержание × извлечение), расчёт)` : ''}.` : '',
      AKT.val(n, 'safety_class') ? `Класс безопасности: ${AKT.val(n, 'safety_class')}.` : '', String(AKT.val(n, 'checklist') || ''), String(AKT.val(n, 'closure') || ''), 'Текст модуля целиком:', String(AKT.val(n, 'text') || '—').replace(/\s*\[оценка на модели\]/g, ' (≈)').replace(/\s*\[допущение\]/g, ' (д)')].filter(Boolean).join('\n');
    set('tc-full', full);
    if (AKT.lever) AKT.lever.renderCard(n);
    const eh = AKT.evidenceHtml(n), ee = $('tc-evid');
    if (ee && ee._raw !== eh) { ee._raw = eh; ee.innerHTML = eh; }
    const costH = AKT.costHtml(n), ce2 = $('tc-cost');
    if (ce2 && ce2._raw !== costH) { ce2._raw = costH; ce2.innerHTML = costH; if (AKT.glossify) AKT.glossify(ce2); }
  },
};
/* rows of the journal of this shift: the dispatcher's calls (InfluxDB) and the module's own rows (arrived, late, resolved),
   newest first; the panel, the queue page and the report read this one list */
AKT.shiftJournal = () => {
  const esc = ((AKT.val('mod-priority', 'escalations') || {}).log || []).filter(e => e && (e.action === 'late' || e.action === 'arrived' || e.action === 'resolved'))
    .map(e => ({ sim_time: e.t, action: e.action, issue: e.issue, role: '', text: e.text, run: AKT.run }));
  return (AKT.journal || []).filter(r => !r.run || r.run === AKT.run).concat(esc).sort((a, b) => (b.sim_time || 0) - (a.sim_time || 0));
};
/* a journal row in words */
AKT.journalRu = r => {
  const issueRu = s => AKT.things[s] ? AKT.nameRu(AKT.issueNode(s) || s) : (/^issue-(\d+)$/.test(s || '') ? 'беда ' + s.slice(6) : (s || ''));
  const role = r.role ? AKT.roleAcc(AKT.roleFirst(r.role)) : '';
  if (r.action === 'call') return `позвали ${role}${r.issue ? ' к ' + issueRu(r.issue) : ''}`;
  if (r.action === 'snooze') return `отложили${r.issue ? ' ' + issueRu(r.issue) : ''}: ${r.text || ''}`;
  if (r.action === 'auto_call') return `автовызов ${role}${r.issue ? ' к ' + issueRu(r.issue) : ''}`;
  if (r.action === 'arrived') return `прибыли${r.issue ? ': ' + issueRu(r.issue) : ''}${r.text ? ' — ' + r.text : ''}`;
  if (r.action === 'late') return `не прибыли вовремя${r.issue ? ': ' + issueRu(r.issue) : ''}${r.text ? ' — ' + r.text : ''}`;
  if (r.action === 'resolved') return `беда устранена${r.issue ? ': ' + issueRu(r.issue) : ''}`;
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
/* why there is no table of two runs now */
AKT.noCompareText = () => {
  const sc = AKT.scenario();
  if (sc && !AKT.cmpOpen()) return 'Идёт сценарий со скрытой причиной: сравнение с ходом без него не показывается, пока причину ищет диспетчер (оно открывается в «Режиме проверки модели»).';
  if (sc) return 'Копии модели ещё считают первые минуты сценария: сравнение появится здесь само.';
  return 'Сравнение появляется, когда идёт сценарий: симулятор считает рядом ход без сценария (в свободном ходе сравнивать не с чем). Запустите сценарий в разделе «Сценарии».';
};
AKT.shiftTable = r => {
  const scen = r.kind === 'scenario';
  const names = scen ? [['base', 'без сценария (база)'], ['fact', 'со сценарием'], ['loud', 'очередь «кто громче»'], ['no_twin', 'без двойника']]
    : [['fact', 'как было'], ['base', 'без сценария'], ['loud', 'очередь «кто громче»'], ['no_twin', 'без двойника']];
  const c = r.copies || {};
  const ok = k => c[k] && typeof c[k].cu_t === 'number' && c[k].cu_t >= 0;
  const base = ok('base') ? c.base : null;
  const rows = names.filter(([k]) => ok(k)).map(([k, label]) => {
    const x = c[k];
    const d = base && k !== 'base' ? x.cu_t - base.cu_t : null;
    return `<tr><td>${label}</td><td class="n">${AKT.f1(x.cu_t)}</td><td class="n">${d == null ? '—' : (d > 0 ? '+' : d < 0 ? '−' : '') + AKT.f1(Math.abs(d))}</td>`
      + `<td class="n">${AKT.fmt(x.ore_t)}</td><td class="n">${AKT.fmt(x.energy_mwh)}</td><td class="n">≈ ${AKT.money(x.usd)}</td></tr>`;
  }).join('');
  if (!rows) return '<p class="note">Копии модели ещё считают первые минуты сценария: цифры появятся здесь сами.</p>';
  return `<table class="kv"><tr><th></th><th>Медь, т</th><th>Разница с ходом без сценария</th><th>Руда, т</th><th>Энергия, МВт·ч</th><th>≈ Стоимость</th></tr>${rows}</table>`;
};
/* Effect of a scenario = the fact minus the base copy at the same model minute (the swing of the ore cancels), copper of the line
   named in the scenario, else of the plant. Null when the base copy is not published (free run, hidden cause): the caller keeps
   the pair «before the scenario → now» and says that the swing of the ore is inside it. */
AKT.scenEffect = scen => {
  const m = /:(\d)/.exec(scen || ''), th = m ? `line-${m[1]}` : 'site';
  const b = AKT.base(th, 'cu_tph'), n = AKT.num(th, 'cu_tph');
  if (b == null || n == null || b < 0 || n < 0) return null;
  const d = n - b, sg = d > 0.04 ? '+' : d < -0.04 ? '−' : '±';
  return { base: b, fact: n, effect: d, text: `Медь ${m ? 'линии ' + m[1] : 'фабрики'}: база ${AKT.f1(b)} → факт ${AKT.f1(n)} т Cu/ч, эффект ${sg}${AKT.f1(Math.abs(d))} (разница с копией без сценария в ту же минуту модели; колебание руды вычтено)` };
};
/* Expected result of a scenario, computed beforehand by the same code as the stand: web/static/verify.json, written by
   `python -I aktogay/run.py verify` (sim/verify.py); a test keeps the file equal to the script output. */
AKT.verify = {
  data: null, asked: false, seen: {},
  load(cb) {
    if (this.data) { if (cb) cb(); return; }
    if (cb) (this.cbs = this.cbs || []).push(cb);
    if (this.asked) return;
    this.asked = true;
    fetch('/verify.json', { cache: 'no-store' }).then(r => r.json()).then(d => { this.data = d; (this.cbs || []).forEach(f => f()); this.cbs = []; })
      .catch(() => { this.asked = false; });
  },
  kip() { const k = Number(AKT.params && AKT.params.get('kip')); return k >= 2 ? 2 : 1; },
  run(id, kip) {
    if (!this.data || !id) return null;
    const rs = this.data.runs.filter(r => r.id === id);
    return rs.find(r => r.kip === (id === 'fork' ? kip || this.kip() : 1)) || null;
  },
  sg(d, f) { return (d > 0.00004 ? '+' : d < -0.00004 ? '−' : '±') + f(Math.abs(d)); },
  momentRu(k) {
    const m = /^(stock_empty|sag_off)_(\d)$/.exec(k);
    if (!m) return k;
    return m[1] === 'stock_empty' ? `склад руды линии ${m[2]} кончится` : `SAG-${m[2]} останется без руды или встанет`;
  },
  /* the observation of a moment on the live stand (the things Ditto holds) */
  observed(k) {
    const m = /^(stock_empty|sag_off)_(\d)$/.exec(k);
    if (!m) return false;
    return m[1] === 'stock_empty' ? AKT.st(`stockpile-${m[2]}`) === 'EMPTY' : ['STARVED', 'STOP', 'RELINE'].includes(AKT.st(`sag-${m[2]}`));
  },
  /* status of one moment against the stand: wait / within ±10 min of model time / confirmed at HH:MM / not confirmed */
  status(run, k, start) {
    const key = `${AKT.run}|${run.id}|${k}`, now = AKT.simTime, exp = start != null ? start + run.moments[k].min : null;
    if (this.observed(k) && this.seen[key] == null && now != null) this.seen[key] = now;
    if (this.seen[key] != null) return `подтверждено в ${AKT.clock(this.seen[key])} модели`;
    if (exp == null || now == null) return 'ждём';
    if (this.since == null || this.sinceRun !== AKT.run) { this.since = now; this.sinceRun = AKT.run; }      /* when this page started to look at the run */
    if (now < exp - 10) return 'ждём';
    if (now <= exp + 10) return 'сейчас должно произойти (окно ±10 мин модели)';
    return this.since > exp + 10 ? 'не видно: страница открыта после этого момента' : 'не подтвердилось';
  },
  text(run) {
    const d = run.diff.fact, c = run.copies;
    if (run.fork) {
      const w = c.fact.cu_t - c.no_twin.cu_t, f = c.loud.cu_t - c.no_twin.cu_t, o = c.fact.cu_t - c.loud.cu_t;
      return `двойник («по $») ${this.sg(w, AKT.f2)} т Cu против копии «без двойника»: находка ${this.sg(f, AKT.f2)}, порядок вызова ${this.sg(o, AKT.f2)}`;
    }
    return `${this.sg(d.cu_t, AKT.f2)} т Cu и ${d.usd < 0 ? '−' : '+'}${AKT.money(Math.abs(d.usd))} против копии без сценария`;
  },
  banner(scen) {
    if (!this.data) return '';
    const run = this.run(scen);
    if (!run) return '';
    const seed = AKT.num('site', 'seed');
    const lab = `посчитано заранее тем же кодом, seed ${this.data.seed}, оценка на модели`;
    if (seed != null && seed !== this.data.seed) return `<div class="b-ex"><b>Ожидаемый итог к 20:00</b> заранее посчитан для прогона № ${this.data.seed}, а идёт № ${AKT.fmt(seed)}: сверять нечего. Прогон № ${this.data.seed} — «Сбросить 08:00» в «Пульте модели».</div>`;
    const start = AKT.scenStart();
    const mom = Object.keys(run.moments).map(k => `<li>${AKT.esc(this.momentRu(k))} ≈ ${run.moments[k].clock} · <span class="p-sub">на стенде: ${AKT.esc(this.status(run, k, start))}</span></li>`).join('');
    return `<div class="b-ex"><b>Ожидаемый итог к 20:00</b> — ${lab}: ${AKT.esc(this.text(run))}.${mom ? `<ul class="b-ex-l">${mom}</ul>` : ' Склад руды и SAG из-за сценария за смену не останавливаются.'}</div>`;
  },
  /* the shift result of the stand next to what was computed beforehand */
  compare(res) {
    if (!this.data || !res || res.kind !== 'scenario') return '';
    const run = this.run(AKT.scenario());
    const seed = AKT.num('site', 'seed');
    if (!run || seed !== this.data.seed || res.t_min == null) return '';
    const c = res.copies || {};
    if (!(c.fact && c.base && c.fact.cu_t >= 0 && c.base.cu_t >= 0)) return '';
    const got = c.fact.cu_t - c.base.cu_t, exp = run.diff.fact.cu_t;
    const start = AKT.scenStart();
    const done = start != null && res.t_min >= start + 719;
    if (!done) return `<p class="note">К этому часу получено ${this.sg(got, AKT.f2)} т Cu; к 20:00 по заранее посчитанному (seed ${this.data.seed}, оценка на модели) будет ${this.sg(exp, AKT.f2)} т Cu.</p>`;
    return `<p class="note">Итог к 20:00: получено ${this.sg(got, AKT.f2)} т Cu; заранее посчитано ${this.sg(exp, AKT.f2)} т Cu (seed ${this.data.seed}, оценка на модели) · ${Math.abs(got - exp) <= 0.05 ? 'совпало' : `расходится на ${AKT.f2(Math.abs(got - exp))} т Cu: на стенде вызовы идут в живом времени, а в расчёте заранее — без нажатий`}.</p>`;
  },
  table() {
    if (!this.data) return '<p class="empty dash">Загружаю заранее посчитанные итоги…</p>';
    const d = this.data, cur = AKT.scenario();
    const names = (AKT.SCENARIOS || []).reduce((m, s) => { m[s.id] = s.name; return m; }, {});
    const rows = d.runs.map(r => {
      const c = r.copies, x = r.diff.fact;
      const copies = r.fork
        ? `по $ ${AKT.f2(c.fact.cu_t)} · по громкости ${AKT.f2(c.loud.cu_t)} · без двойника ${AKT.f2(c.no_twin.cu_t)} · база ${AKT.f2(c.base.cu_t)}`
        : `база ${AKT.f2(c.base.cu_t)} · сценарий ${AKT.f2(c.fact.cu_t)}`;
      const usd = r.fork ? `по $ − без двойника: ${this.sg(c.fact.usd - c.no_twin.usd, v => AKT.money(v))}` : `${x.usd < 0 ? '−' : '+'}${AKT.money(Math.abs(x.usd))}`;
      const mom = Object.keys(r.moments).map(k => `${this.momentRu(k)} ≈ ${r.moments[k].clock}`).join('; ') || '—';
      const live = cur === r.id && (r.id !== 'fork' || r.kip === this.kip()) ? (Object.keys(r.moments).map(k => this.status(r, k, AKT.scenStart())).join('; ') || 'идёт') : '';
      const lab = r.fork ? `Две беды сразу, дежурных КИПиА: ${r.kip}` : (names[r.id] || AKT.scenarioRu(r.id));
      return `<tr><td><b>${AKT.esc(lab)}</b> <span class="p-sub"><code>${AKT.esc(r.id)}</code></span><br><span class="p-sub">${AKT.esc(mom === '—' ? 'склад и SAG из-за сценария не останавливаются' : mom)}</span></td><td>${copies}</td><td class="n">${r.fork ? this.sg(c.fact.cu_t - c.no_twin.cu_t, AKT.f2) : this.sg(x.cu_t, AKT.f2)}</td><td>${usd}</td><td>${AKT.esc(live)}</td></tr>`;
    }).join('');
    return `<div style="overflow-x:auto"><table class="kv" id="ht-verify-t"><tr><th>Сценарий и ключевые моменты</th><th>Медь к 20:00, т Cu (копии)</th><th>Разница, т Cu</th><th>Разница, $</th><th>На стенде сейчас</th></tr>${rows}</table></div>
<p class="note">Ожидаемый итог — посчитано заранее тем же кодом, seed ${d.seed}, оценка на модели; код ${AKT.esc(d.code_hash)}. Команда: <code>${AKT.esc(d.command)}</code>. Копия «факт» без нажатий в интерфейсе. У «Две беды сразу» разница считается с копией «без двойника», а копия «по $» идёт по вызовам кода модуля «Очередь бед» (<code>sim/modloop.py</code>, лаг модуля 10 мин), как на стенде. Окно сверки моментов на стенде — ±10 мин модели (модуль считает каждые 5–10 мин). В первой колонке — когда склад руды кончится или SAG останется без руды, если это происходит из-за сценария.</p>`;
  },
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
  if (AKT.train) AKT.train.apply();
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
