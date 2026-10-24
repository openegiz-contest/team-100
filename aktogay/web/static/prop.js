/* Spread of a scenario through the plant: which nodes differ from the run without the scenario (the copy «base» that
   the simulator publishes on the thing baseline as <thing>_<feature>_base), each with «было → стало», in the order of
   the process (pit -> excavators -> crusher -> belt -> stockpile -> SAG -> ... -> copper in the concentrate).
   Everything is read from Ditto (baseline and the plant things); nothing is computed from the simulator.
   Used by the map, the diorama, the 3D view and the banner of the scenario. */
'use strict';
(function () {
  const root = typeof window !== 'undefined' ? window : globalThis;
  const AKT = root.AKT = root.AKT || {};
  const NB = ' ';
  /* field -> [name, unit, smallest difference that counts, digits] */
  const FIELDS = {
    mining_tph: ['выемка', 'т/ч', 100, 0], tph: ['руда', 'т/ч', 50, 0], feed_tph: ['питание', 'т/ч', 50, 0],
    level_t: ['запас', 'т', 300, 0], stock_t: ['запас', 'т', 100, 0], cu_tph: ['медь', 'т/ч', 0.3, 1], recovery: ['извлечение', '%', 0.5, 1],
    power_kw: ['мощность', 'кВт', 500, 0], site_mw: ['сеть', 'МВт', 2, 0], power_mw: ['сеть', 'МВт', 2, 0], conc_tph: ['концентрат', 'т/ч', 5, 0],
    cake_tph: ['кек', 'т/ч', 5, 0], inventory_t: ['запас', 'т', 100, 0], intake_m3h: ['забор воды', 'м³/ч', 100, 0], water_m3h: ['вода', 'м³/ч', 100, 0],
    p80_um: ['помол', 'мкм', 5, 0], load_pct: ['загрузка', '%', 3, 0], pond_m3: ['пруд', 'м³', 5000, 0], recycle_m3h: ['оборотная вода', 'м³/ч', 100, 0],
    headroom_mw: ['запас сети', 'МВт', 2, 0], grid_limit_mw: ['предел сети', 'МВт', 2, 0],
  };
  /* which feature tells most about a node (the first one that differs) */
  const MAIN = ['mining_tph', 'tph', 'feed_tph', 'level_t', 'stock_t', 'cu_tph', 'power_kw', 'site_mw', 'power_mw', 'conc_tph', 'cake_tph', 'inventory_t',
    'recovery', 'intake_m3h', 'water_m3h', 'p80_um', 'load_pct', 'recycle_m3h', 'pond_m3'];
  const STAGE = [/^pit$/, /^exc-/, /^fleet$/, /^crusher-/, /^conveyor-/, /^stockpile-/, /^sag-/, /^pebble-/, /^ball-/, /^cyclones-/, /^(flot|rougher|cleaner)-/,
    /^thick-/, /^filter-/, /^conc-stock$/, /^line-/, /^site$/, /^power$/, /^water$/];
  const LEVEL_STATES = /^(LOW|EMPTY|FULL|LIMITED|RELINE|STOP|DOWN|FAULT)$/;
  const stage = n => { const i = STAGE.findIndex(r => r.test(n)); return i < 0 ? STAGE.length : i; };
  /* key of the baseline feature: <thing>_<feature>_base, thing = name or name-N[a-z] */
  const KEY = /^(conc-stock|[a-z]+(?:-\d[a-z]?)?)_([a-z0-9_]+)_base$/;

  const fnum = (v, d) => (v == null || !isFinite(v)) ? '—' : (AKT.fmt ? AKT.fmt(v, d) : String(Math.round(v * 10 ** d) / 10 ** d));
  const baseRaw = k => (AKT.val ? AKT.val('baseline', k) : null);

  /* the nodes that differ from the run without the scenario: {thing: {thing, field, base, now, kind, text, short, stage}} */
  function compute(keys) {
    const out = {};
    for (const k of keys) {
      const m = KEY.exec(k);
      if (!m) continue;
      const thing = m[1], f = m[2];
      if (!AKT.things || !AKT.things[thing]) continue;
      const b = baseRaw(k);
      if (f === 'state') {
        const now = AKT.st(thing);
        if (typeof b !== 'string' || !b || !now || b === now) continue;
        const sb = AKT.stopped(b), sn = AKT.stopped(now);
        if (sb === sn && !(LEVEL_STATES.test(now) !== LEVEL_STATES.test(b))) continue;
        const c = { thing, field: 'state', base: b, now, kind: 'state', stage: stage(thing) };
        const tb = AKT.stRu(b, thing), tn = AKT.stRu(now, thing);
        c.short = `${tb}${NB}→${NB}${tn}`;
        c.text = `${AKT.shortName(thing)}: ${c.short}`;
        if (!out[thing] || out[thing].kind !== 'num') out[thing] = c;
        continue;
      }
      const spec = FIELDS[f];
      if (!spec || typeof b !== 'number' || !(b >= 0)) continue;
      const now = AKT.num(thing, f);
      if (now == null) continue;
      if (Math.abs(now - b) <= Math.max(spec[2], 0.05 * Math.abs(b))) continue;
      const pri = MAIN.indexOf(f), cur = out[thing];
      if (cur && cur.kind === 'num' && MAIN.indexOf(cur.field) <= pri) continue;
      out[thing] = {
        thing, field: f, base: b, now, kind: 'num', stage: stage(thing),
        short: `${fnum(b, spec[3])}${NB}→${NB}${fnum(now, spec[3])}${NB}${spec[1]}`,
        text: `${AKT.shortName(thing)}: ${spec[0]} ${fnum(b, spec[3])}${NB}→${NB}${fnum(now, spec[3])}${NB}${spec[1]}`,
      };
    }
    return out;
  }
  const order = changes => Object.values(changes).sort((a, b) => a.stage - b.stage || String(a.thing).localeCompare(String(b.thing), 'en', { numeric: true }));

  const P = AKT.prop = {
    compute, order, FIELDS, KEY,
    memo: null, memoAt: null, memoKey: '', seen: {},
    /* is the comparison with the run without the scenario open now (the simulator keeps the base copy in a scenario run) */
    on() { return typeof AKT.cmpOpen === 'function' && AKT.cmpOpen(); },
    all() {
      if (!P.on() || !AKT.things || !AKT.things.baseline) { P.reset(''); return {}; }
      const key = `${AKT.run}|${AKT.scenario ? AKT.scenario() : ''}`;
      if (key !== P.memoKey) P.reset(key);
      if (P.memo && P.memoAt === AKT.polled && AKT.polled != null) return P.memo;
      const feats = (AKT.things.baseline.features) || {};
      const ch = compute(Object.keys(feats).filter(k => k.endsWith('_base')));
      P.memo = ch; P.memoAt = AKT.polled;
      const nowW = Date.now();
      for (const n in ch) if (!P.seen[n]) P.seen[n] = { sim: AKT.simTime, wall: nowW };
      for (const n in P.seen) if (!ch[n]) delete P.seen[n];
      return ch;
    },
    reset(key) { P.memoKey = key; P.memo = null; P.memoAt = null; P.seen = {}; },
    affected() { return new Set(Object.keys(P.all())); },
    has(n) { return !!P.all()[n]; },
    short(n) { const c = P.all()[n]; return c ? c.short : ''; },
    change(n) { return P.all()[n] || null; },
    list() { return order(P.all()); },
    /* appeared in the last seconds of real time: the wave of the spread on the map */
    fresh(n, ms) { const s = P.seen[n]; return !!s && Date.now() - s.wall < (ms || 9000); },
    firstSeen(n) { return P.seen[n] ? P.seen[n].sim : null; },
    /* the chain for the banner: excavators in one item («Экскаваторы: стоят 3 из 3»), the rest one by one */
    grouped() {
      const l = P.list(), exc = l.filter(c => /^exc-/.test(c.thing));
      if (!exc.length) return l;
      const down = exc.filter(c => AKT.stopped(AKT.st(c.thing))).length;
      const item = { thing: exc[0].thing, stage: exc[0].stage, text: down ? `Экскаваторы: стоят ${down} из ${exc.length}` : `Экскаваторы: ${exc.length} со сменой нагрузки`, short: '' };
      const out = []; let put = false;
      for (const c of l) { if (/^exc-/.test(c.thing)) { if (!put) { out.push(item); put = true; } } else out.push(c); }
      return out;
    },
    /* line for the banner: the chain in the order of the process, at most `max` items */
    chainText(max) {
      const l = P.grouped();
      if (!l.length) return '';
      const m = max || 6, head = l.slice(0, m).map(c => c.text);
      return head.join(' → ') + (l.length > m ? ` → ещё ${l.length - m}` : '');
    },
  };
  /* a window of the last `minutes` of model time out of points [{sim_time}] (the history is asked in wall time,
     and at a fast model it covers the whole shift) */
  AKT.lastWindow = (pts, minutes) => {
    if (!pts || !pts.length) return [];
    const end = Math.max(...pts.map(p => p.sim_time));
    return pts.filter(p => p.sim_time >= end - minutes);
  };
  /* the label of the draft «если сдавать сейчас»: its own model time, and how far behind the clock it is */
  AKT.draftTitle = (draftAt, nowAt, clock) => {
    const c = clock || (v => String(v));
    if (draftAt == null) return 'Если сдавать сейчас';
    if (nowAt == null || nowAt - draftAt < 15) return `Если сдавать сейчас (${c(draftAt)} модели)`;
    return `Если сдавать сейчас (черновик на ${c(draftAt)} модели, сейчас ${c(nowAt)}: обновляется модулем с отставанием)`;
  };
  /* position of a truck on its road between two readings from Ditto: the phase of the reading sets the part of the
     road, the model clock moves it on; a reading of the same phase does not restart the truck */
  AKT.truckAlong = (f, dir, phase, dtMin, tripMin) => {
    let g = f, d = dir;
    if (phase === 'LOADING') return { f: 0.03, dir: 1 };
    if (phase === 'QUEUE' || phase === 'DUMP') return { f: 0.97, dir: 1 };
    d = /RETURN/.test(phase) ? -1 : 1;
    g += d * dtMin / Math.max(1, tripMin);
    return { f: Math.max(0.03, Math.min(0.97, g)), dir: d };
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = P;
})();
