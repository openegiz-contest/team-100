/* Card of one thing (L3): what it is, the issue on it, the main numbers as meters (value, 0…limit, a word),
   2-hour trends, who is responsible; the engineer's part (thing id, type model, revision, run, every
   feature, passport with sources, raw JSON) folded under «Для инженера». Also AKT.trend: the trend chart
   used here and in the line view (norm band, limit as a solid line with its word, last point, crosshair,
   a summary line and a table twin). */
'use strict';
(function () {
  const SVGNS = 'http://www.w3.org/2000/svg';
  const esc = AKT.esc, fmt = AKT.fmt, f1 = AKT.f1;
  const LABEL_RU = { fact: 'отчёт', vendor: 'поставщик', project: 'ОВОС', analog: 'аналог', assumption: 'допущение', calc: 'расчёт' };
  const TREND = { sag: ['power_kw', 'feed_tph'], ball: ['power_kw'], crusher: ['tph', 'lube_kpa'], conveyor: ['tph'], stockpile: ['level_t'],
    line: ['tph', 'recovery'], flot: ['tail_cu', 'recovery'], rougher: ['dose_meas_gt', 'stage_recovery'], cleaner: ['conc_cu'], cyclones: ['p80_um'],
    pebble: ['feed_tph'], thick: ['inventory_t'], filter: ['cake_tph'], 'conc-stock': ['stock_t'], water: ['pond_m3', 'intake_m3h'], power: ['site_mw'],
    site: ['tph', 'cu_tph'], pit: ['mining_tph'], exc: ['tph'], fleet: ['trucks_ready'], crew: [], batch: ['tonnes_left'], issue: ['loss_usd_h'], piezometer: ['kpa'] };
  /* what the thing is, in one line */
  const WHAT = { sag: 'мельница полусамоизмельчения, первая ступень помола линии', ball: 'шаровая мельница, вторая ступень помола',
    pebble: 'пресс дробления гали: дробит крупные куски, которые SAG не домолола, и возвращает их в мельницу', cyclones: 'гидроциклоны: тонкое — на флотацию, крупное — обратно на домол',
    flot: 'флотация: медь всплывает с пеной в концентрат', rougher: 'основная и контрольная флотация', cleaner: 'перечистка: повторная флотация чернового концентрата',
    thick: 'сгуститель: отстаивает воду из концентрата, запас перед фильтрами', filter: 'фильтр-прессы: отжимают воду из концентрата',
    'conc-stock': 'склад концентрата; отгрузка поездом в 06:00 и 18:00', stockpile: 'склад дроблёной руды перед мельницей; пока он есть, остановка дробилки не останавливает линию',
    crusher: 'дробилка у карьера (ЦПД): дробит руду перед конвейером на склад', conveyor: 'конвейер от дробилки к складу руды', line: 'линия фабрики: помол и флотация',
    water: 'хвостохранилище и вода фабрики', power: 'подстанция и ЛЭП 220 кВ', pit: 'карьер', fleet: 'парк самосвалов и экскаваторов карьера',
    exc: 'экскаватор в забое', piezometer: 'пьезометр: давление воды в теле дамбы хвостохранилища', truck: 'самосвал карьера', person: 'человек смены', crew: 'бригада' };
  /* main numbers by type: [feature, limit(name) or null, label, format] */
  const kw = v => v == null ? '—' : `${f1(v / 1000)} МВт`;
  const t0 = v => `${fmt(v)} т/ч`;
  const METERS = {
    sag: [['power_kw', n => AKT.num(n, 'power_limit_kw'), 'мощность', kw], ['feed_tph', null, 'питание', t0], ['load_pct', () => 100, 'загрузка', v => `${f1(v)} %`], ['liner_wear_mm', null, 'износ футеровки', v => `${f1(v)} мм`], ['e_kwh_t', null, 'удельная энергия', v => `${AKT.f2(v)} кВт·ч/т`]],
    ball: [['power_kw', n => (AKT.pass(n, 'drive_mw') || 22) * 1000, 'мощность', kw]],
    pebble: [['feed_tph', n => AKT.num(n, 'limit_tph'), 'питание', t0], ['load_pct', () => 100, 'загрузка', v => `${fmt(v)} %`]],
    stockpile: [['level_t', n => AKT.pass(n, 'live_t'), 'запас', v => `${fmt(v)} т`], ['in_tph', null, 'приход', t0], ['out_tph', null, 'расход', t0]],
    crusher: [['tph', n => AKT.pass(n, 'capacity_tph'), 'производительность', t0], ['lube_kpa', null, 'давление масла', v => `${fmt(v)} кПа`]],
    thick: [['inventory_t', n => AKT.pass(n, 'capacity_t'), 'запас', v => `${fmt(v)} т`]],
    filter: [['cake_tph', n => AKT.num(n, 'limit_tph'), 'кек', v => `${f1(v)} т/ч`], ['presses_on', n => AKT.pass(n, 'presses'), 'прессов в работе', v => fmt(v)]],
    'conc-stock': [['stock_t', n => AKT.pass(n, 'capacity_t'), 'запас', v => `${fmt(v)} т`]],
    flot: [['recovery', null, 'извлечение', v => `${f1(v)} %`], ['tail_cu', () => 0.075, 'медь в хвостах (уставка 0,075 %)', v => `${AKT.f3(v)} %`]],
    power: [['site_mw', () => AKT.num('power', 'grid_limit_mw'), 'нагрузка площадки', v => `${fmt(v)} МВт`]],
    piezometer: [['kpa', n => AKT.num(n, 'sp_kpa') || 150, 'давление воды', v => `${f1(v)} кПа`]],
    cyclones: [['p80_um', null, 'крупность помола', v => `${fmt(v)} мкм`], ['open_count', n => AKT.pass(n, 'units'), 'циклонов в работе', v => fmt(v)]],
    line: [['tph', null, 'руда', t0], ['cu_tph', null, 'медь в концентрат', v => `${f1(v)} т/ч`], ['recovery', null, 'извлечение', v => `${f1(v)} %`]],
    water: [['intake_m3h', n => AKT.num(n, 'intake_cap_m3h'), 'забор свежей воды', v => `${fmt(v)} м³/ч`], ['recycle_m3h', null, 'оборотная вода', v => `${fmt(v)} м³/ч`], ['pond_m3', null, 'пруд', v => `${AKT.f2(v / 1e6)} млн м³`]],
  };

  /* ---------------------------------------------------------------- trend chart */
  AKT.trend = function (container, thing, field, opts) {
    opts = opts || {};
    const dg = opts.digits ?? 1, unit = opts.unit ? ' ' + opts.unit : '';
    const fv = v => AKT.fmt(v, dg) + unit;
    container.innerHTML = `<div class="trend"><div class="tr-h">${esc(opts.title || field)}</div>
<div class="tr-box"><svg viewBox="0 0 400 100" preserveAspectRatio="none" aria-hidden="true"></svg><div class="wait">Загружаю 2 часа истории…</div></div>
<div class="tr-sum" role="status"></div>
<details><summary>Таблица</summary><div class="tr-tab"></div></details></div>`;
    const q = s => container.querySelector(s);
    const box = q('.tr-box'), svg = q('svg');
    let pts = [], timer = null, alive = true, scale = null;
    const mk = (tag, attrs, parent) => { const e = document.createElementNS(SVGNS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); (parent || svg).appendChild(e); return e; };
    const html = (cls, text, style) => { const d = document.createElement('div'); d.className = cls; d.textContent = text; Object.assign(d.style, style || {}); box.appendChild(d); return d; };
    const draw = async () => {
      if (!alive) return;
      try {
        const d = await AKT.history(thing, [field], opts.range || '2h');
        pts = (d.points || []).filter(p => typeof p[field] === 'number' && p[field] !== -1 && typeof p.sim_time === 'number').sort((a, b) => a.sim_time - b.sim_time);
        while (svg.firstChild) svg.removeChild(svg.firstChild);
        box.querySelectorAll('.ylab, .xlab, .splab, .lastdot, .wait').forEach(e => e.remove());
        if (pts.length < 2) { html('wait', 'Данных за 2 часа ещё нет: смена началась в 08:00 или прогон только начался.'); q('.tr-sum').textContent = ''; return; }
        const t0 = pts[0].sim_time, t1 = pts[pts.length - 1].sim_time, span = t1 - t0 || 1;
        const vals = pts.map(p => p[field]);
        let lo = Math.min(...vals), hi = Math.max(...vals);
        for (const v of [opts.limit, opts.normLo, opts.normHi]) if (v != null) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
        if (hi === lo) hi = lo + 1;
        const pad = (hi - lo) * 0.12; lo -= pad; hi += pad;
        const X = t => 400 * (t - t0) / span, Y = v => 100 - 100 * (v - lo) / (hi - lo);
        scale = { X, Y, t0, span };
        if (opts.normLo != null || opts.normHi != null) {
          const a = opts.normHi != null ? opts.normHi : hi, b = opts.normLo != null ? opts.normLo : lo;
          mk('rect', { x: 0, y: Y(a), width: 400, height: Math.max(0, Y(b) - Y(a)), class: 'band' });
        }
        if (opts.limit != null) {
          mk('line', { x1: 0, y1: Y(opts.limit), x2: 400, y2: Y(opts.limit), class: 'sp' });
          const ys = Y(opts.limit);
          html('splab', opts.limitLabel || 'предел', { top: ys < 20 ? `calc(${ys}% + 2px)` : `calc(${ys}% - 20px)` });
        }
        mk('polyline', { points: pts.map(p => `${X(p.sim_time).toFixed(1)},${Y(p[field]).toFixed(1)}`).join(' '), class: 'ln' });
        const last = pts[pts.length - 1];
        html('lastdot', '', { position: 'absolute', width: '8px', height: '8px', borderRadius: '50%', background: 'var(--ink)', left: `calc(${X(last.sim_time) / 4}% - 4px)`, top: `calc(${Y(last[field])}% - 4px)` });
        html('ylab', AKT.fmt(hi - pad, dg), { left: '2px', top: '2px' });
        html('ylab', AKT.fmt(lo + pad, dg), { left: '2px', bottom: '2px' });
        html('xlab', AKT.clock(t0), { left: '40%', bottom: '2px' });
        html('xlab', AKT.clock(t1), { right: '2px', bottom: '2px' });
        const mn = Math.min(...vals), mxv = Math.max(...vals);
        q('.tr-sum').textContent = `Сейчас ${fv(last[field])}${opts.normLabel ? ' · ' + opts.normLabel : ''} · за ${span >= 100 ? '2 ч' : AKT.dur(span)} от ${AKT.fmt(mn, dg)} до ${fv(mxv)}`
          + (opts.limit != null && last[field] > opts.limit ? ' · выше уставки' : '');
        const step = Math.max(1, Math.round(pts.length / 12));
        q('.tr-tab').innerHTML = `<table class="kv"><tr><th>время модели</th><th>${esc(opts.title || field)}</th></tr>${pts.filter((p, i) => i % step === 0 || i === pts.length - 1).map(p => `<tr><td>${AKT.clock(p.sim_time)}</td><td class="n">${AKT.fmt(p[field], dg)}</td></tr>`).join('')}</table>`;
      } catch (e) { q('.tr-sum').textContent = 'История недоступна: ' + e.message; }
    };
    /* crosshair: the value under the pointer */
    let xh = null, tip = null;
    box.addEventListener('pointermove', ev => {
      if (!scale || pts.length < 2) return;
      const r = box.getBoundingClientRect(), fx = (ev.clientX - r.left) / r.width;
      const t = scale.t0 + fx * scale.span;
      let best = pts[0]; for (const p of pts) if (Math.abs(p.sim_time - t) < Math.abs(best.sim_time - t)) best = p;
      if (!xh) xh = mk('line', { class: 'xh', y1: 0, y2: 100 });
      const x = scale.X(best.sim_time); xh.setAttribute('x1', x); xh.setAttribute('x2', x); xh.style.display = '';
      if (!tip) { tip = document.createElement('div'); tip.className = 'tip'; box.appendChild(tip); }
      tip.textContent = `${AKT.clock(best.sim_time)} · ${fv(best[field])}`; tip.style.display = '';
      tip.style.left = Math.min(r.width - tip.offsetWidth - 2, Math.max(2, ev.clientX - r.left + 8)) + 'px';
    });
    box.addEventListener('pointerleave', () => { if (xh) xh.style.display = 'none'; if (tip) tip.style.display = 'none'; xh = null; tip && tip.remove(); tip = null; });
    draw(); timer = setInterval(() => { xh = null; draw(); }, 10000);
    return { stop() { alive = false; clearInterval(timer); } };
  };
  AKT.sparkline = (c, thing, field, opts) => AKT.trend(c, thing, field, Object.assign({}, opts, { limit: opts && opts.setpoint, limitLabel: opts && opts.setpointLabel }));

  /* ---------------------------------------------------------------- card */
  const view = {
    name: '', charts: [], raw: null,
    async build(stage, opts) {
      this.charts.forEach(c => c.stop()); this.charts = [];
      this.name = AKT.name(opts.id || 'site');
      const n = this.name;
      stage.innerHTML = '';
      const doc = document.createElement('div'); doc.className = 'doc'; doc.id = 'card'; stage.appendChild(doc);
      const t = AKT.thing(n);
      if (!t) { doc.innerHTML = `<h2>${esc(n)}</h2><p class="bad">Такой вещи в двойнике нет (или она ещё не создана).</p><p><a href="${AKT.href('?view=tree')}">Состав двойника</a></p>`; return; }
      if (AKT.simOnly(n)) {
        doc.innerHTML = `<h2>${esc(AKT.nameRu(n))}</h2><div class="note">${esc(AKT.typeRu(AKT.type(n)))}</div><p>Признаки этой вещи — ${esc(AKT.SIM_ONLY_NOTE)}.</p><p><a href="${AKT.href('?view=tree')}">Состав двойника</a></p>`;
        return;
      }
      const type = AKT.type(n);
      const def = t.definition || '';
      const defHref = def.replace(/^http:\/\/akt-models\//, `http://${location.hostname}:8092/`);
      const pass = AKT.passport(n), src = AKT.attr(n, 'source') || {};
      const resp = AKT.attr(n, 'responsible') || {};
      const passRows = Object.entries(pass).map(([k, p]) => {
        const v = p && typeof p === 'object' ? p.value : p, u = p && p.unit ? p.unit : '', s = p && p.src ? src[p.src] : null;
        const lab = s ? `${LABEL_RU[s.label] || s.label}` : '';
        const doc_ = s ? `${esc(AKT.srcDoc(p.src, s))}${s.page ? ', с. ' + esc(s.page) : ''}` : '';
        const link = s && s.url ? ` <a href="${esc(s.url)}" target="_blank" rel="noopener">ссылка</a>` : '';
        const val = typeof v === 'number' ? AKT.fmt(v, Number.isInteger(v) ? 0 : (Math.abs(v) < 1 ? 3 : 2)) : (v == null ? '—' : String(v));
        return `<tr><td>${esc(AKT.passKeyRu(k))}</td><td class="n">${esc(val)} ${esc(AKT.unitRu(u))}</td><td>${doc_}${link} <span class="lbl-est">${esc(lab)}${p && p.note ? ' · ' + esc(p.note) : ''}</span></td></tr>`;
      }).join('');
      const feats = Object.keys(t.features || {}).filter(f => !['idSimulationRun', 'sim_time', 'state_ru', 'status_ru'].includes(f));
      const featRows = feats.map(f => `<tr><td>${esc(AKT.featRu(n, f))}</td><td class="n" id="cf-${esc(f)}">—</td></tr>`).join('');
      const trends = (TREND[type] || feats.filter(f => typeof AKT.raw(n, f) === 'number' && !['heartbeat', 'x', 'y', 'lat', 'lon', 'seq'].includes(f)).slice(0, 2)).filter(f => feats.includes(f));
      const also = (resp.also || []).map(a => a && typeof a === 'object' && !Array.isArray(a) ? `${esc(a.name_ru || a.role)}${a.for_ru ? ' (' + esc(a.for_ru) + ')' : ''}` : (Array.isArray(a) ? `${esc(a[0])} (${esc(a[1])})` : esc(a))).join(', ');
      const thingLink = x => `<a href="${AKT.href('?view=unit&id=' + AKT.id(x))}">${esc(AKT.nameRu(x))}</a>`;
      const what = WHAT[type] || WHAT[AKT.cat(n)] || AKT.typeRu(type);
      const lineNo = /[12]/.test(n) ? n.match(/[12]/)[0] : '';
      doc.innerHTML = `
<h2>${esc(AKT.nameRu(n))} <span class="badge st-grey" id="c-state">—</span></h2>
<div class="lead" id="c-what">Что это: ${esc(what)}${lineNo && /^(sag|ball|pebble|cyclones|flot|rougher|cleaner|thick|filter|stockpile|crusher|conveyor)/.test(type) ? ' ' + lineNo : ''}.</div>
<div class="note" id="c-age"></div>
<div id="c-issue"></div>
<h3>Главные показатели</h3><div class="meters" id="c-meters"></div>
<div id="c-trends"></div>
<h3>Кто отвечает</h3>
<div>${esc(resp.name_ru || resp.role || '—')}${resp.arrive_min ? ` · доедет за ${esc(resp.arrive_min[0])}–${esc(resp.arrive_min[1])} мин${AKT.asm()}` : ''}${also ? ` · также: ${also}` : ''}
 <button type="button" id="c-call" title="Запишет вызов в журнал смены">Позвать ${esc(AKT.roleAcc(AKT.roleFirst(resp.name_ru || resp.role || '')) || '')}</button> <span id="c-call-msg" class="p-sub" role="status"></span></div>
<h3>Связи</h3>
<div class="note">питает: ${AKT.feeds(n).map(thingLink).join(', ') || '—'} · питается от: ${AKT.fedBy(n).map(thingLink).join(', ') || '—'} · входит в: ${AKT.parent(n) ? thingLink(AKT.parent(n)) : '—'}</div>
<details><summary>Для инженера: все признаки, паспорт с источниками, служебные данные</summary>
<div class="note" id="c-eng"></div>
<h3>Все признаки</h3><table class="kv"><tr><th>признак</th><th>значение</th></tr>${featRows}</table>
<h3>Паспорт (источники)</h3><table class="kv"><tr><th>поле</th><th>значение</th><th>источник · метка</th></tr>${passRows || '<tr><td colspan="3">нет паспорта</td></tr>'}</table>
<p class="note">${esc(AKT.typeRu(type))} · идентификатор ${esc(t.thingId)} · модель типа: <a href="${esc(defHref)}" target="_blank" rel="noopener">${esc(def || '—')}</a></p>
<details><summary>Сырые данные вещи (только чтение)</summary><pre id="c-raw">загрузка…</pre></details></details>
<p><a href="${AKT.href('?view=plan')}">Обзор</a> · <a href="${AKT.href('?view=diorama&focus=' + encodeURIComponent(n))}">в 3D (диорама)</a>${lineNo ? ` · <a href="${AKT.href('?view=line' + lineNo)}">схема линии ${lineNo}</a>` : ''}</p>`;
      document.getElementById('c-call').addEventListener('click', async () => {
        const iss = AKT.issues().find(i => AKT.issueNode(i) === n);
        if (iss) return AKT.panel.call(iss);
        const msg = document.getElementById('c-call-msg');
        msg.textContent = 'записываю в журнал смены…';
        try {
          await AKT.post('/api/call', { issue: n, role: resp.name_ru || resp.role || '', text: 'Позвать к ' + AKT.nameRu(n) });
          msg.textContent = `записано в ${AKT.clock(AKT.simTime)} модели`; setTimeout(AKT.pollJournal, 1500); setTimeout(AKT.pollJournal, 12000);
        } catch (e) { msg.textContent = 'не записалось: ' + e.message + '. Нажмите ещё раз.'; }
      });
      const tr = document.getElementById('c-trends');
      if (trends.length) {
        tr.innerHTML = '<h3>Последние 2 часа (время модели)</h3>' + trends.map(f => `<div id="c-sp-${f}"></div>`).join('');
        for (const f of trends) {
          const u = AKT.unitRu(AKT.unit(n, f));
          this.charts.push(AKT.trend(document.getElementById('c-sp-' + f), n, f, f === 'tail_cu'
            ? { title: 'Медь в хвостах, %', unit: '%', digits: 3, limit: 0.075, limitLabel: 'уставка 0,075 %', normHi: 0.075, normLabel: 'норма до 0,075 %' }
            : { title: `${AKT.featRu(n, f)}${u ? ', ' + u : ''}`, unit: u, digits: Math.abs(AKT.num(n, f) || 0) < 10 ? 2 : (Math.abs(AKT.num(n, f) || 0) < 100 ? 1 : 0) }));
        }
      }
      AKT.glossify(document.getElementById('c-what'));
      this.loadRaw();
      this.rawTimer = setInterval(() => this.loadRaw(), 10000);
    },
    async loadRaw() {
      const el = document.getElementById('c-raw'); if (!el || !el.closest('details').open) { if (el && el.textContent === 'загрузка…') { /* loaded on open */ } }
      try { const d = await AKT.get('/api/thing?id=' + encodeURIComponent(AKT.id(this.name))); if (el) el.textContent = JSON.stringify(d, null, 2); }
      catch (e) { if (el) el.textContent = 'ошибка: ' + e.message; }
    },
    destroy() { this.charts.forEach(c => c.stop()); this.charts = []; clearInterval(this.rawTimer); },
    update() {
      const n = this.name, t = AKT.thing(n);
      if (!t || !document.getElementById('c-state')) return;
      const st = AKT.st(n), b = document.getElementById('c-state');
      const lv = AKT.levelOf(n);
      b.textContent = (lv ? AKT.LV_GLYPH[lv] + ' ' : '') + AKT.stRu(st, n); b.className = 'badge ' + AKT.lvCls(lv);
      const paused = AKT.st('site') === 'PAUSED' || AKT.num('site', 'speed') === 0;
      const age = document.getElementById('c-age');
      const at = AKT.num(n, 'sim_time');
      const a = paused ? `Модель на паузе — значения не меняются (на ${AKT.clockDay(at)} модели).` : `Значения на ${AKT.clockDay(at)} модели.`;
      if (age.textContent !== a) age.textContent = a;
      const eng = `Данные из Ditto, обновлены ${AKT.ago(AKT.modifiedAge(n))} · ревизия ${t._revision ?? '—'} · прогон ${AKT.val(n, 'idSimulationRun') || '—'}`;
      const ee = document.getElementById('c-eng'); if (ee.textContent !== eng) ee.textContent = eng;
      /* the issue on this node */
      const iss = AKT.issues().filter(i => AKT.issueNode(i) === n || (AKT.nodeKey(AKT.issueNode(i)) === n && AKT.issueNode(i) !== n));
      const ih = iss.map(i => {
        const il = AKT.issueLevel(i), m = AKT.issueMain(i);
        return `<div class="issue-band lv-${il}">${AKT.glyph(il)} <b>${AKT.rankSign(i) || '•'} Беда: ${esc(AKT.issueTitle(i))}</b> · ${esc(m.text)} · ${esc(AKT.issuePrice(i))}
          ${AKT.issueCalled(i) ? ' · позвали' : ` <button type="button" class="primary" data-call="${esc(i)}">Позвать ${esc(AKT.roleAcc(AKT.roleFirst(AKT.issueRole(i))))}</button>`}</div>`;
      }).join('');
      const ie = document.getElementById('c-issue');
      if (ie._raw !== ih) { ie._raw = ih; ie.innerHTML = ih; ie.querySelectorAll('[data-call]').forEach(x => x.addEventListener('click', () => AKT.panel.call(x.dataset.call))); }
      /* meters */
      const spec = METERS[AKT.type(n)] || METERS[AKT.cat(n)] || null;
      let mh = '';
      const rows = spec || Object.keys(t.features || {}).filter(f => typeof AKT.raw(n, f) === 'number' && AKT.raw(n, f) !== -1 && !['sim_time', 'heartbeat', 'seq', 'x', 'y', 'lat', 'lon'].includes(f)).slice(0, 4).map(f => [f, null, AKT.featRu(n, f), () => AKT.valText(n, f)]);
      for (const [f, limF, label, fm] of rows) {
        const v = AKT.num(n, f);
        if (v == null) continue;
        const lim = limF ? limF(n) : null;
        const frac = lim ? v / lim : null;
        const mlv = frac == null ? 0 : frac > 1.0001 ? 1 : frac >= 0.97 ? 2 : 0;
        const word = frac == null ? '' : frac > 1.0001 ? 'выше предела' : frac >= 0.97 ? 'на пределе' : 'в норме';
        mh += `<div class="meter-c lv-${mlv}"><div class="m-l">${esc(label)}</div><div class="m-v">${esc(fm(v))}${lim ? ` <span class="p-sub">из ${esc(fm(lim))}</span>` : ''}</div>`
          + (lim ? `<div class="m-bar" role="img" aria-label="${esc(label)}: ${Math.round(100 * frac)} % от предела"><i style="width:${Math.min(100, 100 * frac).toFixed(1)}%"></i></div><div class="m-w">${mlv ? AKT.LV_GLYPH[mlv] + ' ' : ''}${word}</div>` : '') + '</div>';
      }
      const me = document.getElementById('c-meters');
      if (me._raw !== mh) { me._raw = mh; me.innerHTML = mh || '<div class="empty dash">Чисел для шкал у этой вещи нет — все признаки в разделе «Для инженера».</div>'; }
      for (const f in t.features) {
        const el = document.getElementById('cf-' + f); if (!el) continue;
        const s = AKT.valText(n, f);
        if (el.textContent !== s) el.textContent = s;
      }
    },
  };
  AKT.views.card = view;
})();
