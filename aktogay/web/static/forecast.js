/* «Прогнозы» (second level) and the forecast of copper inside the copper tile (features 10, 11, 13; В4).
   Data: mod-priority.forecast (Ditto; the module computes it from the plant's own features) and the shift counters
   of the lines (InfluxDB history). Forecast = dashed line and «≈»; the corridor is a pale band; the plan line is an
   orientation (average day of 2025), not a published plan. Nothing here is a measurement. */
'use strict';
(function () {
  const esc = AKT.esc, fmt = AKT.fmt, f1 = AKT.f1;
  const NB = AKT.NB;
  const doc = (stage, id) => { stage.innerHTML = ''; const d = document.createElement('div'); d.className = 'doc'; d.id = id; stage.appendChild(d); return d; };
  const setHtml = (id, html) => { const e = document.getElementById(id); if (e && e._raw !== html) { e._raw = html; e.innerHTML = html; if (AKT.glossify) AKT.glossify(e); } };
  const MIN_SHIFT = 720, SHIFT0 = 480;

  const FC = AKT.fc = {
    /* the forecast of the module; null while it is older than 30 min of model time (module restarting, a run before) */
    data() { const f = AKT.val('mod-priority', 'forecast'); return f && typeof f === 'object' && f.t != null && (AKT.simTime == null || Math.abs(AKT.simTime - f.t) <= 30) ? f : null; },
    /* shift and day clocks of the model (08:00 / 20:00) */
    shiftStart(t) { return Math.floor((t - SHIFT0) / MIN_SHIFT) * MIN_SHIFT + SHIFT0; },
    dayStart(t) { return Math.floor((t - SHIFT0) / 1440) * 1440 + SHIFT0; },
    series: null, seriesAt: 0, seriesRun: '',
    /* copper made: points {t, shift, day} summed over both lines from the history of the shift counters */
    async loadSeries() {
      if (!AKT.run || (FC.seriesRun === AKT.run && Date.now() - FC.seriesAt < 60000)) return;
      FC.seriesAt = Date.now(); FC.seriesRun = AKT.run;
      try {
        const [a, b] = await Promise.all([AKT.history('line-1', ['cum_cu_t', 'cum_cu_t_total'], '30h'), AKT.history('line-2', ['cum_cu_t', 'cum_cu_t_total'], '30h')]);
        const by = {};
        const put = (d, k) => { for (const p of (d.points || [])) { if (typeof p.sim_time !== 'number' || p.sim_time <= 0) continue; const o = by[p.sim_time] = by[p.sim_time] || {}; if (typeof p.cum_cu_t === 'number' && p.cum_cu_t >= 0) o['s' + k] = p.cum_cu_t; if (typeof p.cum_cu_t_total === 'number' && p.cum_cu_t_total >= 0) o['T' + k] = p.cum_cu_t_total; } };
        put(a, 1); put(b, 2);
        const pts = Object.keys(by).map(Number).sort((x, y) => x - y).map(t => ({ t, s: by[t].s1 != null && by[t].s2 != null ? by[t].s1 + by[t].s2 : null, T: by[t].T1 != null && by[t].T2 != null ? by[t].T1 + by[t].T2 : null }));
        FC.series = pts;
      } catch (e) { /* history is optional */ }
      if (AKT.current && AKT.current.update) AKT.current.update();
      if (AKT.panel && AKT.panel.update) AKT.panel.update();
    },
    /* copper of the shift so far: live counters of Ditto */
    shiftNow() { const a = AKT.num('line-1', 'cum_cu_t'), b = AKT.num('line-2', 'cum_cu_t'); return a == null || b == null ? null : a + b; },
    totalNow() { const a = AKT.num('line-1', 'cum_cu_t_total'), b = AKT.num('line-2', 'cum_cu_t_total'); return a == null || b == null ? null : a + b; },
    /* day so far: the total now minus the total at the day start (history); null while the history does not reach it */
    dayNow() {
      const T = FC.totalNow(), t = AKT.simTime, s = FC.series;
      if (T == null || t == null || !s || !s.length) return null;
      const d0 = FC.dayStart(t);
      const p = s.filter(x => x.T != null && x.t >= d0 - 1).sort((x, y) => x.t - y.t)[0];
      if (!p || p.t - d0 > 12) return null;
      return Math.max(0, T - p.T);
    },
    /* forecast numbers for the end of the shift / day: {now, end, lo, hi, plan, endAt} or null */
    cu(kind) {
      const f = FC.data(), c = f && f.copper, t = AKT.simTime;
      if (!c || !(c.rate_tph >= 0) || t == null || AKT.st('site') === 'WARMUP') return null;
      const so = kind === 'day' ? FC.dayNow() : FC.shiftNow();
      if (so == null) return null;
      const endAt = kind === 'day' ? c.day_end_at : c.shift_end_at;
      /* the first poll of a new run (scenario start or cancel) may carry no end time or corridor yet, or the end time of the shift that has just
         ended (then the chart has zero width): no chart, not a chart of NaN or Infinity */
      if (![endAt, c.rate_lo_tph, c.rate_hi_tph].every(Number.isFinite) || !(endAt > (kind === 'day' ? FC.dayStart(t) : FC.shiftStart(t)))) return null;
      const h = Math.max(0, (endAt - t) / 60);
      const plan = kind === 'day' ? c.plan_day_t : c.plan_shift_t;
      return { now: so, end: so + c.rate_tph * h, lo: so + c.rate_lo_tph * h, hi: so + c.rate_hi_tph * h, plan, endAt, h, rate: c.rate_tph, c };
    },
    /* a small chart: history (solid), forecast (dashed), corridor (band), plan tick; w x h in the viewBox */
    cuSvg(kind, W, H, opt) {
      opt = opt || {};
      const k = FC.cu(kind), t = AKT.simTime, s = FC.series;
      if (!k || t == null) return '';
      const t0 = kind === 'day' ? FC.dayStart(t) : FC.shiftStart(t), t1 = k.endAt;
      const base = kind === 'day' ? null : null;
      let hist = [];
      if (s) {
        if (kind === 'day') { const T0 = (s.filter(x => x.T != null && x.t >= t0 - 1).sort((a, b) => a.t - b.t)[0] || {}).T; hist = T0 == null ? [] : s.filter(x => x.T != null && x.t >= t0 - 1 && x.t <= t).map(x => ({ t: x.t, v: Math.max(0, x.T - T0) })); }
        else hist = s.filter(x => x.s != null && x.t >= t0 - 1 && x.t <= t).map(x => ({ t: x.t, v: x.s }));
      }
      hist.push({ t, v: k.now });
      const top = Math.max(k.hi, k.plan || 0, ...hist.map(p => p.v)) * 1.06 || 1;
      const L = opt.pad == null ? 4 : opt.pad, R = L, T = 6, B = opt.axis ? 20 : 4;
      const X = tt => L + (W - L - R) * (tt - t0) / (t1 - t0), Y = v => T + (H - T - B) * (1 - v / top);
      const pl = hist.map(p => `${X(p.t).toFixed(1)},${Y(p.v).toFixed(1)}`).join(' ');
      const band = `${X(t).toFixed(1)},${Y(k.now).toFixed(1)} ${X(t1).toFixed(1)},${Y(k.hi).toFixed(1)} ${X(t1).toFixed(1)},${Y(k.lo).toFixed(1)}`;
      let g = `<polygon class="fc-band" points="${band}"/>`;
      if (k.plan) g += `<line class="fc-plan" x1="${L}" x2="${W - R}" y1="${Y(k.plan).toFixed(1)}" y2="${Y(k.plan).toFixed(1)}"/>`;
      g += `<polyline class="fc-hist" points="${pl}"/>`;
      g += `<line class="fc-dash" x1="${X(t).toFixed(1)}" y1="${Y(k.now).toFixed(1)}" x2="${X(t1).toFixed(1)}" y2="${Y(k.end).toFixed(1)}"/>`;
      g += `<circle class="fc-now" cx="${X(t).toFixed(1)}" cy="${Y(k.now).toFixed(1)}" r="2.6"/>`;
      if (opt.axis) {
        g += `<line class="fc-ax" x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}"/>`;
        for (const [tt, lab] of [[t0, AKT.clock(t0)], [t, 'сейчас'], [t1, AKT.clock(t1)]].filter(x => x[1] !== 'сейчас' || (x[0] - t0) > 0.12 * (t1 - t0))) g += `<text class="fc-tx" x="${X(tt).toFixed(1)}" y="${H - 5}" text-anchor="${tt === t0 ? 'start' : tt === t1 ? 'end' : 'middle'}">${esc(lab)}</text>`;
        g += `<text class="fc-tx" x="${W - R}" y="${Y(k.end).toFixed(1) - 4}" text-anchor="end">≈ ${esc(fmt(k.end))} т</text>`;
        if (k.plan) g += `<text class="fc-tx" x="${L + 2}" y="${Y(k.plan).toFixed(1) - 3}">ориентир ${esc(fmt(k.plan))} т</text>`;
      }
      return `<svg class="fc-svg" viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${esc(opt.label || 'Прогноз меди: факт сплошной линией, прогноз пунктиром с коридором')}">${g}</svg>`;
    },
    /* the line under the copper tile: «≈ 281 т к 20:00 (270–292)» + the small chart */
    tileHtml() {
      const k = FC.cu('shift');
      if (!k) return '';
      return `<span class="fc-line" title="Прогноз меди до конца смены: факт + темп последнего часа × оставшееся время. Коридор: низ — разброс темпа за 3 ч, верх — если закрыть сейчас беды, которые уже теряют медь. Ориентир — средние сутки 2025 г. (факт KAZ Minerals, расчёт).">≈${NB}${fmt(k.end)}${NB}т к${NB}${AKT.clock(k.endAt)}${NB}<span class="fc-r">(${fmt(k.lo)}–${fmt(k.hi)})</span></span>`;
    },
    tileSvg() { return FC.cuSvg('shift', 120, 26, { label: 'Медь за смену: факт и прогноз пунктиром с коридором' }); },
  };

  /* -------------------------------------------------------------- the view */
  const stockSvg = (lines, pek) => {
    const W = 640, row = 46, H = 28 + row * lines.length, L = 92, R = 14, max = Math.max(pek, ...lines.map(r => r.hours || 0)) * 1.04;
    const X = h => L + (W - L - R) * h / max;
    let g = '';
    for (const h of [0, 12, 24, 36, 48]) g += `<line class="fc-grid" x1="${X(h)}" x2="${X(h)}" y1="14" y2="${H - 14}"/><text class="fc-tx" x="${X(h)}" y="${H - 3}" text-anchor="middle">${h} ч</text>`;
    lines.forEach((r, i) => {
      const y = 22 + i * row;
      g += `<text class="fc-tx big" x="${L - 8}" y="${y + 13}" text-anchor="end">Линия ${r.n}</text>`;
      g += `<rect class="fc-pek" x="${L}" y="${y}" width="${(X(pek) - L).toFixed(1)}" height="18" rx="2"/>`;
      if (r.hours != null) {
        g += `<rect class="fc-bar" x="${L}" y="${y}" width="${Math.max(2, X(r.hours) - L).toFixed(1)}" height="18" rx="2"/>`;
        g += `<text class="fc-tx big" x="${(X(r.hours) + 5).toFixed(1)}" y="${y + 13}">≈ ${esc(f1(r.hours))} ч</text>`;
      } else g += `<text class="fc-tx" x="${L + 6}" y="${y + 13}">SAG стоит — склад не расходуется</text>`;
    });
    return `<svg class="fc-svg" viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Часов руды на складе по линиям, если карьер встанет сейчас; пунктир — верхняя граница по ПЭК (48 ч)">${g}</svg>`;
  };

  const linerSvg = (r, curve, n) => {
    const W = 640, H = 190, L = 44, R = 16, T = 14, B = 30;
    const lo = 0.95, hi = 1.05;
    const X = x => L + (W - L - R) * x, Y = e => T + (H - T - B) * (1 - (e - lo) / (hi - lo));
    const past = curve.filter(p => p[0] <= r.share + 1e-9), fut = curve.filter(p => p[0] >= r.share - 1e-9);
    const eta = x => { for (let i = 1; i < curve.length; i++) if (x <= curve[i][0]) { const a = curve[i - 1], b = curve[i]; return a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0]); } return curve[curve.length - 1][1]; };
    const pts = a => a.map(p => `${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join(' ');
    let g = '';
    for (const e of [0.96, 0.98, 1.0, 1.02, 1.04]) g += `<line class="fc-grid" x1="${L}" x2="${W - R}" y1="${Y(e)}" y2="${Y(e)}"/><text class="fc-tx" x="${L - 5}" y="${Y(e) + 3}" text-anchor="end">×${esc(AKT.fmt(e, 2))}</text>`;
    for (const x of [0, 0.25, 0.5, 0.75, 1]) g += `<text class="fc-tx" x="${X(x)}" y="${H - 12}" text-anchor="middle">${Math.round(x * 100)} %</text>`;
    g += `<text class="fc-tx" x="${(L + W - R) / 2}" y="${H - 1}" text-anchor="middle">доля кампании футеровки (30 Мт — допущение)</text>`;
    g += `<polyline class="fc-hist" points="${pts(past)}"/>`;
    g += `<polyline class="fc-dash" fill="none" points="${pts(fut)}"/>`;
    g += `<circle class="fc-now" cx="${X(r.share)}" cy="${Y(eta(r.share))}" r="4"/><text class="fc-tx big" x="${X(r.share) + 6}" y="${Y(eta(r.share)) - 7}">сейчас ×${esc(AKT.fmt(r.eta_now, 3))}</text>`;
    g += `<circle class="fc-mark" cx="${X(0.7)}" cy="${Y(r.eta_peak)}" r="3"/><text class="fc-tx" x="${X(0.7)}" y="${Y(r.eta_peak) - 6}" text-anchor="middle">пик ×${esc(AKT.fmt(r.eta_peak, 2))}</text>`;
    g += `<circle class="fc-mark" cx="${X(1)}" cy="${Y(r.eta_end)}" r="3"/><text class="fc-tx" x="${X(1) - 4}" y="${Y(r.eta_end) + 14}" text-anchor="end">конец ×${esc(AKT.fmt(r.eta_end, 2))}</text>`;
    return `<svg class="fc-svg" viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Линия ${n}: пропускная способность SAG по кампании футеровки; сплошная — пройдено, пунктир — прогноз">${g}</svg>`;
  };

  AKT.views.forecast = {
    build(stage) {
      const d = doc(stage, 'forecast');
      d.innerHTML = `<h2>Прогнозы</h2>
<p class="lead">Здесь всё, что ещё не случилось. Пунктир и «≈» — прогноз модели (оценка на модели), не измерение. На главном экране прогноз появляется только как беда, когда до порога остаётся меньше времени на реакцию.</p>
<h3>Руда на складе, если карьер встанет сейчас</h3><div id="fc-stock"></div>
<h3>Футеровка мельниц SAG</h3><div id="fc-liner"></div>
<h3>Медь до конца смены и суток</h3><div id="fc-cu"></div>
<p class="note" id="fc-note"></p>`;
    },
    update() {
      FC.loadSeries();
      const f = FC.data();
      if (!f) { ['fc-stock', 'fc-liner', 'fc-cu'].forEach(id => setHtml(id, '<p class="empty dash">Модуль «Очередь бед» ещё не посчитал прогноз: он появится через минуту после запуска.</p>')); return; }
      /* 1. stock chain */
      const st = f.stock || {}, lines = Object.keys(st.lines || {}).sort().map(n => Object.assign({ n }, st.lines[n])).map(r => Object.assign(r, { hours: r.hours >= 0 ? r.hours : null }));
      const stages = (st.stages || []).map(s => `<li>${esc(s.stage)}: ${fmt(s.min)} мин</li>`).join('');
      const pit = st.pit_stopped ? `<p class="fc-alert"><b>▲ Карьер стоит.</b> Склад держит фабрику: ${lines.map(r => `линия ${r.n} — ещё ≈ ${r.hours == null ? '—' : AKT.durH(r.hours)}`).join('; ')}.</p>` : '';
      setHtml('fc-stock', pit + (lines.length ? stockSvg(lines, (lines[0] && lines[0].pek_hours) || 48) : '')
        + `<table class="kv"><tr><th>Линия</th><th>Запас на складе</th><th>Руда на пути</th><th>Расход SAG</th><th>Хватит</th><th>Склад кончится</th></tr>${lines.map(r => `<tr><td>${r.n}</td><td class="n">${fmt(r.level_t)} т (${fmt(r.live_pct)} % живой части)</td><td class="n">≈ ${fmt(r.transit_t)} т</td><td class="n">${r.out_tph != null && r.out_tph > 0 ? fmt(r.out_tph) + ' т/ч' : '—'}</td><td class="n">${r.hours == null ? '—' : '≈ ' + AKT.durH(r.hours)}</td><td class="n">${r.run_out_at != null && r.run_out_at > 0 ? '≈ ' + esc(AKT.clockDay(r.run_out_at)) : '—'}</td></tr>`).join('')}</table>`
        + `<p class="p-sub">Цепочка: карьер → откатка → дробилка → лента → склад → SAG. Руда, уже вынутая и едущая, ещё дойдёт (≈ ${fmt(st.lag_min)} мин): ${stages ? '<ul class="chain">' + stages + '</ul>' : ''}Серая полоса — верхняя граница по ПЭК: рабочий объём склада 163 кт = 2 суток измельчения [проект, ПЭК с. 10]. Модель держит живой запас 40 кт на линию (д): остальное — мёртвый запас по бортам.</p>`);
      /* 2. liner */
      const ln = f.liner || {}, cv = ln.curve || [];
      const parts = Object.keys(ln.lines || {}).sort().map(n => {
        const r = ln.lines[n];
        return `<div class="fc-card"><h4>SAG-${n}: наработка ${AKT.fmt(r.ground_mt, 1)} из ${AKT.fmt(r.life_mt, 0)} Мт (${AKT.fmt(100 * r.share, 0)} %)</h4>${cv.length ? linerSvg(r, cv, n) : ''}
<p><b>Планировать перефутеровку через ≈ ${AKT.fmt(r.days_to_end, 0)} сут</b> (при текущем т/ч и готовности линии 92 %) ${r.days_to_peak != null && r.days_to_peak >= 0 ? `· пик пропускной способности через ≈ ${AKT.fmt(r.days_to_peak, 0)} сут` : '· пик пройден'}. К концу кампании т/ч SAG ${AKT.fmt(r.drop_from_peak_pct, 1)} % от пика (${AKT.fmt(r.tph_now)} → ≈ ${AKT.fmt(r.tph_end)} т/ч при той же руде). Остановка на перефутеровку ≈ ${AKT.fmt(r.reline_h)} ч${r.reline_cu_t != null ? ` ≈ ${AKT.fmt(r.reline_cu_t)} т Cu линии` : ''} (длительность — допущение, RME).</p>${AKT.lever && AKT.lever.suggestion(r.lever) ? AKT.lever.btnHtml(r.lever, 'liner-' + n) + (AKT.lever.applied && AKT.lever.applied.ref === 'liner-' + n ? AKT.lever.resultHtml() : '') : ''}</div>`;
      }).join('');
      setHtml('fc-liner', (parts || '<p class="empty dash">Счётчик наработки футеровки ещё не пришёл.</p>')
        + '<p class="p-sub">Факт: перефутеровка SAG в IV кв. 2023 на обеих линиях (переработка −5,3 % и −3,9 % к III кв.) и в III кв. 2025 на линии 2 (отчёты KAZ Minerals). Форма кривой (Powell и др. 2006 — только направление) и длина кампании 30 Мт — допущения стенда; счётчик наработки идёт по норме и не знает скрытого ускоренного износа.</p>');
      /* 3. copper */
      const cs = FC.cu('shift'), cd = FC.cu('day');
      const one = (title, k, kind) => k ? `<div class="fc-card"><h4>${title}: ≈ ${fmt(k.end)} т к ${AKT.clockDay(k.endAt)} <span class="fc-r">(коридор ${fmt(k.lo)}–${fmt(k.hi)} т)</span></h4>${FC.cuSvg(kind, 640, 150, { axis: true, pad: 8 })}<p class="p-sub">Сделано сейчас ${fmt(k.now)} т, темп последнего часа ${f1(k.rate)} т/ч, осталось ${AKT.durH(k.h)}. Ориентир ${fmt(k.plan)} т — средняя смена/сутки 2025 г. вместе с остановками (220,3 кт Cu в концентрате / 365; факт KAZ Minerals, расчёт), не плановое задание.</p></div>` : '';
      setHtml('fc-cu', (one('До конца смены', cs, 'shift') + one('До конца суток (с 08:00)', cd, 'day')) || '<p class="empty dash">Счётчики меди и история ещё копятся.</p>');
      setHtml('fc-note', esc(((f.texts && f.texts.copper) ? f.texts.copper : '').replace(/\s*\[оценка на модели\]/g, ' (≈)')) + ' Прогноз — при текущем темпе, без новых остановок и перефутеровок.');
    },
  };
})();
